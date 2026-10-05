#!/usr/bin/env bash
# One-command DMA build, scheduler submission, correctness checks, and sweep.
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

check_capacity() {
  [[ "$1" =~ ^[1-9][0-9]{2,4}$ ]] || die 'BENCH_MAX_BYTES must be 256..65536 and a multiple of 128'
  (( $1 >= 256 && $1 <= 65536 && $1 % 128 == 0 )) || die 'Invalid BENCH_MAX_BYTES'
}

# Validate every PE row as well as the aggregate row before using its timings.
check_csv() {
  awk -F, -v mode="$2" -v bytes="$3" -v reps="$4" -v active="$5" -v offset="$6" '
    NR == 1 {
      sub(/\r$/, "")
      if ($0 != "benchmark,mode,bytes,reps,active_pes,offset,pe,cycles,cycles_per_op,aggregate_bytes_per_cycle,errors") bad=1
      next
    }
    {
      sub(/\r$/, "")
      if (NF != 11 || $1 != "dma" || $2 != mode || $3 != bytes ||
          $4 != reps || $5 != active || $6 != offset ||
          $11 !~ /^[0-9]+$/ || $11+0 != 0 ||
          $8 !~ /^[0-9]+$/ || $8+0 <= 0 || $9+0 <= 0) bad=1
      if ($7 == "aggregate") {
        aggregate++
        if ($10+0 <= 0) bad=1
      } else {
        if ($7 !~ /^[0-9]+$/ || $7+0 >= active || seen[$7]++ || $10 != "") bad=1
        pes++
      }
    }
    END { if (bad || aggregate != 1 || pes != active || NR != active+2) exit 1 }
  ' "$1"
}

collect_results() {
  local out=$1 capacity=$2 mode active offset bytes reps file expected count
  # CSV parsing runs on the login node, which already has the build tools.
  for mode in get put iget iput; do
    for active in 1 64; do
      file="$out/smoke/${mode}_${active}pe.csv"
      check_csv "$file" "$mode" 8 10 "$active" 0 || die "Invalid CSV or nonzero errors: $file"
    done
  done
  expected=0
  for mode in get put iget iput; do
    for active in 1 64; do
      for offset in 0 4; do
        for bytes in 8 16 32 64 128 256 512 1024 2048 4096 8192 16384 32768 65536; do
          if (( bytes > capacity )); then continue; fi
          reps=10000
          if (( bytes >= 1024 )); then reps=1000; fi
          file="$out/raw/dma_${mode}_${active}pe_${bytes}B_offset${offset}.csv"
          check_csv "$file" "$mode" "$bytes" "$reps" "$active" "$offset" || die "Invalid CSV or nonzero errors: $file"
          expected=$((expected+1))
        done
      done
    done
  done

  printf 'mode,bytes,reps,active_pes,offset,cycles,cycles_per_op,aggregate_bytes_per_cycle,errors\n' > "$out/summary.csv"
  for file in "$out"/raw/*.csv; do
    awk -F, '$7 == "aggregate" { print $2 "," $3 "," $4 "," $5 "," $6 "," $8 "," $9 "," $10 "," $11 }' "$file" >> "$out/summary.csv"
  done
  count=$(awk 'END { print NR-1 }' "$out/summary.csv")
  [[ "$count" == "$expected" ]] || die "Summary has $count rows; expected $expected"
  awk -F, '
    NR > 1 {
      key=$1 SUBSEP $2 SUBSEP $5
      if ($4 == 1) single[key]=$8
      else if ($4 == 64) many[key]=$8
    }
    END {
      print "mode,bytes,offset,single_bytes_per_cycle,aggregate64_bytes_per_cycle,bandwidth_ratio64_to1"
      for (key in single) if (key in many) {
        split(key, part, SUBSEP)
        printf "%s,%s,%s,%.9f,%.9f,%.6f\n", part[1],part[2],part[3],single[key],many[key],many[key]/single[key]
      }
    }
  ' "$out/summary.csv" > "$out/scaling.csv"
  {
    printf '# DMA benchmark results\n\n'
    printf 'Capacity per buffer: %s B.\n\n' "$capacity"
    printf 'Passed: 8 correctness cases and %s sweep cases; all reported errors are zero.\n\n' "$count"
    printf 'Modes: get, put, iget, iput. Active PEs: 1, 64. Host offsets: 0, 4 B.\n\n'
    printf 'Each PE has one outstanding request. Eight warm-up transfers are excluded from timing.\n\n'
    printf 'Raw cases: raw/. Aggregate rows: summary.csv. Matched 64-PE/1-PE bandwidth ratios: scaling.csv.\n\n'
    printf 'Timings include the loop, API and completion waits. Repeated transfers reuse the same memory slots.\n\n'
    printf 'GB/s = bytes_per_cycle * actual_CPE_clock_GHz; frequency is not assumed.\n\n'
    printf 'Record actual cache/shared-LDM settings and resource sharing before comparing runs.\n'
  } > "$out/REPORT.md"
  printf 'completed_cases=%s\n' "$count" > "$out/COMPLETE"
  printf 'DMA completed: %s cases. Results: %s\n' "$count" "$out"
}

if [[ ${1:-} == --help || ${1:-} == -h ]]; then
  printf 'Usage: bash run_dma.sh [QUEUE] [NEW_OUTPUT_DIRECTORY]\n'
  printf 'With no QUEUE, display available queues and prompt for a name.\n'
  printf 'Optional environment: DMA_QUEUE, SWCC, SW_MODULE, BENCH_MAX_BYTES (default 65536).\n'
  exit 0
fi
[[ $# -le 2 ]] || die 'Usage: bash run_dma.sh [QUEUE] [NEW_OUTPUT_DIRECTORY]'
queue=${1:-${DMA_QUEUE:-}}
capacity=${BENCH_MAX_BYTES:-65536}
check_capacity "$capacity"

command -v bsub >/dev/null 2>&1 || die 'bsub not found; load the site job-submission environment first'
if [[ -z "$queue" ]]; then
  command -v bqueues >/dev/null 2>&1 || die 'bqueues not found; specify the queue as the first argument'
  bqueues -u "$(id -un)" || bqueues
  [[ -t 0 ]] || die 'Non-interactive shell: specify QUEUE or set DMA_QUEUE'
  read -r -p 'Enter a usable queue name from the list: ' queue
fi
[[ -n "$queue" && "$queue" != *[[:space:]]* ]] || die 'Queue name must be nonempty and contain no whitespace'

swcc=${SWCC:-swgcc}
compiler_module=${SW_MODULE:-swgcc/1473}
if ! command -v "$swcc" >/dev/null 2>&1; then
  type module >/dev/null 2>&1 || die "Compiler not found; run: module load $compiler_module"
  module load "$compiler_module"
  hash -r
fi
command -v "$swcc" >/dev/null 2>&1 || die "Compiler not found: $swcc"
target=$("$swcc" -dumpmachine)
case "$target" in
  *sw_64*|*sw64*|*sunway*) ;;
  *) die "Compiler targets $target; a Sunway compiler is required" ;;
esac

out=${2:-"$script_dir/dma_results_$(date '+%Y%m%d_%H%M%S')_$$"}
mkdir -- "$out" || die 'Output directory must be new and its parent must exist'
out=$(cd -- "$out" && pwd)
mkdir "$out/source" "$out/build" "$out/smoke" "$out/raw"
for file in dma_host.c dma_slave.c bench_common.h; do
  [[ -f "$script_dir/$file" ]] || die "Missing source: $script_dir/$file"
  cp "$script_dir/$file" "$out/source/$file"
done
# Preserve the entry point used for this run.
cp "$script_dir/run_dma.sh" "$out/run_dma.sh"

# Compute-node worker: POSIX shell builtins plus the Sunway executable only.
# Do not submit this Bash entry point: this site has no bash on compute nodes.
cat > "$out/dma_worker.sh" <<'DMA_WORKER'
#!/bin/sh
set -eu
[ "$#" -eq 2 ] || { printf 'Invalid worker arguments\n' >&2; exit 2; }
out=$1
capacity=$2
[ -x "$out/dma_bench" ] || { printf 'Missing DMA executable\n' >&2; exit 2; }
{
  printf 'hostname_environment=%s\n' "${HOSTNAME:-unknown}"
  printf 'job_id_environment=%s\n' "${LSB_JOBID:-unknown}"
  printf 'capacity_bytes=%s\n' "$capacity"
} > "$out/compute.txt"
if [ -r /proc/cpuinfo ]; then
  while IFS= read -r cpu_line || [ -n "$cpu_line" ]; do
    printf '%s\n' "$cpu_line"
  done < /proc/cpuinfo > "$out/cpuinfo.txt"
fi

run_case() {
  printf 'DMA %s bytes=%s reps=%s active=%s offset=%s\n' "$1" "$2" "$3" "$4" "$5"
  if "$out/dma_bench" "$1" "$2" "$3" "$4" "$5" > "$6" 2>> "$out/errors.log"; then
    :
  else
    status=$?
    printf 'ERROR: DMA exited with status %s: %s (see errors.log)\n' "$status" "$6" >&2
    exit "$status"
  fi
}

for mode in get put iget iput; do
  for active in 1 64; do
    run_case "$mode" 8 10 "$active" 0 "$out/smoke/${mode}_${active}pe.csv"
  done
done
printf 'All eight DMA programs returned success. Starting DMA sweep.\n'
expected=0
for mode in get put iget iput; do
  for active in 1 64; do
    for offset in 0 4; do
      for bytes in 8 16 32 64 128 256 512 1024 2048 4096 8192 16384 32768 65536; do
        if [ "$bytes" -gt "$capacity" ]; then continue; fi
        reps=10000
        if [ "$bytes" -ge 1024 ]; then reps=1000; fi
        run_case "$mode" "$bytes" "$reps" "$active" "$offset" \
          "$out/raw/dma_${mode}_${active}pe_${bytes}B_offset${offset}.csv"
        expected=$((expected+1))
      done
    done
  done
done
printf 'completed_cases=%s\n' "$expected" > "$out/RUN_COMPLETE"
printf 'DMA worker finished. CSV validation and summaries run on the login node.\n'
DMA_WORKER
if [[ "$capacity" != 65536 ]]; then
  grep -Eq '^[[:space:]]*#ifndef[[:space:]]+BENCH_MAX_BYTES' "$out/source/bench_common.h" || die 'Update bench_common.h before choosing a non-default capacity'
fi
{
  printf 'queue=%s\ncapacity_bytes=%s\ncompiler=%s\ncompiler_target=%s\n' "$queue" "$capacity" "$(command -v "$swcc")" "$target"
  printf 'host_flags=-mhost -O2\nslave_flags=-mslave -msimd -O2\nlink_flags=-mhybrid\n'
  printf 'small_reps=10000\nlarge_reps=1000\nlarge_threshold_bytes=1024\n'
  printf 'submit_time_utc='; date -u '+%Y-%m-%dT%H:%M:%SZ'
  "$swcc" -v 2>&1
} > "$out/build_info.txt"

compile_object() {
  if [[ "$capacity" == 65536 ]]; then "$swcc" "$@"
  else "$swcc" "-DBENCH_MAX_BYTES=$capacity" "$@"; fi
}
printf 'Building DMA with %s. Output: %s\n' "$swcc" "$out"
{
  compile_object -mhost -O2 -c "$out/source/dma_host.c" -o "$out/build/dma_host.o"
  compile_object -mslave -msimd -O2 -c "$out/source/dma_slave.c" -o "$out/build/dma_slave.o"
  "$swcc" -mhybrid "$out/build/dma_host.o" "$out/build/dma_slave.o" -o "$out/dma_bench"
} 2>&1 | tee "$out/build.log"

printf 'Submitting queue=%s, MPE=1, CG=1, CPE=64.\n' "$queue"
# Keep the scheduler log separate from CSV data. pipefail propagates failures.
if bsub -I -q "$queue" -n 1 -cgsp 64 -mpecg 1 \
  /bin/sh "$out/dma_worker.sh" "$out" "$capacity" 2>&1 | tee "$out/job.log"; then
  :
else
  die "Job failed; inspect $out/job.log and $out/errors.log"
fi
[[ -f "$out/RUN_COMPLETE" ]] || die "Job did not finish the sweep; inspect $out/job.log and errors.log"
collect_results "$out" "$capacity"
printf '\nDone. Results: %s\nSummary: %s/summary.csv\nScaling: %s/scaling.csv\n' "$out" "$out" "$out"
