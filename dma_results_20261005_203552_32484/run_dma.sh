#!/usr/bin/env bash
# One-command DMA build, scheduler submission, correctness checks, and sweep.
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }

check_capacity() {
  [[ "$1" =~ ^[1-9][0-9]{2,5}$ ]] || die 'DMA capacity must be 256..131072 and a multiple of 128'
  (( $1 >= 256 && $1 <= 131072 && $1 % 128 == 0 )) || die 'Invalid DMA capacity'
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
  printf 'DMA_PROFILE=study runs boundary, 7-load and slot-mapping experiments.\n'
  printf 'DMA_MAX_BYTES overrides DMA capacity only; study supports up to 131072 B.\n'
  printf 'DMA_MAPPING_SEED defaults to 20261005. DMA_CACHE_SIZE optionally adds -cache_size.\n'
  printf 'DMA_DIAG_ONLY=1 submits one 8-byte case directly, without a compute-node shell.\n'
  exit 0
fi
[[ $# -le 2 ]] || die 'Usage: bash run_dma.sh [QUEUE] [NEW_OUTPUT_DIRECTORY]'
queue=${1:-${DMA_QUEUE:-}}
capacity=${DMA_MAX_BYTES:-${BENCH_MAX_BYTES:-65536}}
check_capacity "$capacity"
profile=${DMA_PROFILE:-baseline}
[[ "$profile" == baseline || "$profile" == study ]] || die 'DMA_PROFILE must be baseline or study'
mapping_seed=${DMA_MAPPING_SEED:-20261005}
[[ "$mapping_seed" =~ ^[1-9][0-9]{0,9}$ ]] && (( mapping_seed <= 2147483647 )) || die 'DMA_MAPPING_SEED must be 1..2147483647'
if [[ "$profile" == study ]]; then
  (( capacity >= 512 )) || die 'The boundary study requires capacity >= 512 B'
else
  (( capacity <= 65536 )) || die 'Use DMA_PROFILE=study for capacities above 64 KiB'
fi
cache_size=${DMA_CACHE_SIZE:-}
if [[ "$profile" == study && -z "$cache_size" ]]; then cache_size=0; fi
cache_flags=()
if [[ -n "$cache_size" ]]; then
  [[ "$cache_size" == 0 || "$cache_size" == 32 || "$cache_size" == 128 ]] || die 'DMA_CACHE_SIZE must be 0, 32 or 128 (KiB)'
  if (( capacity > 65536 )) && [[ "$cache_size" == 128 ]]; then
    die '128 KiB Cache leaves too little LDM for a >64 KiB DMA buffer and control variables'
  fi
  cache_flags=(-cache_size "$cache_size")
fi
diag_only=${DMA_DIAG_ONLY:-0}
[[ "$diag_only" == 0 || "$diag_only" == 1 ]] || die 'DMA_DIAG_ONLY must be 0 or 1'
[[ "$profile" != study || "$diag_only" == 0 ]] || die 'Use the baseline entry point for DMA_DIAG_ONLY'

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
if [[ "$profile" == study ]]; then
  cp "$script_dir/collect_dma_study.awk" "$out/collect_dma_study.awk"
  cp "$script_dir/run_dma_boundary.sh" "$out/run_dma_boundary.sh"
  cp "$script_dir/DMA_BOUNDARY.md" "$out/DMA_BOUNDARY.md"
fi

# The compiled host program performs the entire sweep in one scheduler task.
grep -Eq '^[[:space:]]*#ifndef[[:space:]]+DMA_MAX_BYTES' "$out/source/bench_common.h" || die 'Update bench_common.h for the new DMA capacity option'
{
  printf 'queue=%s\ncapacity_bytes=%s\ncompiler=%s\ncompiler_target=%s\n' "$queue" "$capacity" "$(command -v "$swcc")" "$target"
  printf 'host_flags=-mhost -O2 -g\nslave_flags=-mslave -msimd -O2 -g\nlink_flags=-mhybrid -g\n'
  printf 'diagnostic_only=%s\n' "$diag_only"
  printf 'profile=%s\nmapping_seed=%s\ncache_size_kib=%s\n' "$profile" "$mapping_seed" "${cache_size:-site_default_unknown}"
  printf 'shared_ldm_configuration=not_changed_unknown\nresource_exclusivity=not_established_by_queue_name\n'
  printf 'small_reps=10000\nlarge_reps=1000\nlarge_threshold_bytes=1024\n'
  printf 'submit_time_utc='; date -u '+%Y-%m-%dT%H:%M:%SZ'
  "$swcc" -v 2>&1
} > "$out/build_info.txt"

compile_object() {
  "$swcc" "-DDMA_MAX_BYTES=$capacity" "$@"
}
printf 'Building DMA with %s. Output: %s\n' "$swcc" "$out"
{
  compile_object -mhost -O2 -g -c "$out/source/dma_host.c" -o "$out/build/dma_host.o"
  compile_object -mslave -msimd -O2 -g -c "$out/source/dma_slave.c" -o "$out/build/dma_slave.o"
  "$swcc" -mhybrid -g "$out/build/dma_host.o" "$out/build/dma_slave.o" -o "$out/dma_bench"
} 2>&1 | tee "$out/build.log"

if [[ "$diag_only" == 1 ]]; then
  printf 'Submitting a direct 8-byte DMA diagnostic (no compute-node shell).\n'
  if bsub -I -q "$queue" -n 1 -cgsp 64 -mpecg 1 "${cache_flags[@]}" \
    "$out/dma_bench" get 8 10 1 0 2>&1 | tee "$out/probe.log"; then
    :
  else
    die "Direct DMA diagnostic failed; share $out/probe.log"
  fi
  # Scheduler messages and stderr stage logs stay in probe.log.
  awk '/^benchmark,/ || /^dma,/' "$out/probe.log" > "$out/smoke/get_1pe.csv"
  check_csv "$out/smoke/get_1pe.csv" get 8 10 1 0 || die "Invalid diagnostic CSV; share $out/probe.log"
  printf 'Direct DMA diagnostic passed. Log: %s/probe.log\n' "$out"
  exit 0
fi

printf 'Submitting queue=%s, MPE=1, CG=1, CPE=64.\n' "$queue"
run_args=(--sweep "$out")
if [[ "$profile" == study ]]; then run_args=(--study "$out" "$mapping_seed"); fi
# Keep the scheduler log separate from CSV data. pipefail propagates failures.
if bsub -I -q "$queue" -n 1 -cgsp 64 -mpecg 1 "${cache_flags[@]}" \
  "$out/dma_bench" "${run_args[@]}" 2>&1 | tee "$out/job.log"; then
  :
else
  die "Job failed; inspect $out/job.log (includes DMA stage logs)"
fi
[[ -f "$out/RUN_COMPLETE" ]] || die "Job did not finish the sweep; inspect $out/job.log"
if [[ "$profile" == study ]]; then
  expected=$(awk 'END {print NR-1}' "$out/plan.csv")
  raw_files=("$out"/raw/*.csv)
  [[ ${#raw_files[@]} == "$expected" ]] || die 'Raw case count differs from plan.csv'
  awk -v out="$out" -v capacity="$capacity" -v seed="$mapping_seed" \
      -f "$out/collect_dma_study.awk" "$out/plan.csv" || die "Study validation failed; inspect $out"
  cp "$out/DMA_BOUNDARY.md" "$out/REPORT.md"
  printf '\nDone. Results: %s\nSummary: %s/study_summary.csv\nScaling: %s/study_scaling.csv\n' "$out" "$out" "$out"
else
  collect_results "$out" "$capacity"
  printf '\nDone. Results: %s\nSummary: %s/summary.csv\nScaling: %s/scaling.csv\n' "$out" "$out" "$out"
fi
