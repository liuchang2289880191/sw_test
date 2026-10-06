#!/usr/bin/env bash
# Login-node launcher. The queue executes only the native RMA suite binary.
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
if [[ ${1:-} == --help || ${1:-} == -h ]]; then
  cat <<'HELP'
Usage: bash run_rma.sh [QUEUE] [NEW_OUTPUT_DIRECTORY]
Defaults: full profile, 3 separate jobs, 65536-byte buffers, cache_size=0.
RMA_DIAG_ONLY=1: correctness probes only, one job.
RMA_PROFILE=quick: smaller size/window/cluster sweep (still repeated).
RMA_REPEATS=1..20; RMA_ORDER_SEED=1..1000000000.
BENCH_MAX_BYTES=256..65536, multiple of 128 (RMA only; not DMA_MAX_BYTES).
RMA_LATENCY_REPS=2000; RMA_BW_REPS=2000; RMA_CACHE_SIZE=0 or 32.
RMA_RESOURCE_NOTE='site allocation/sharing information'; SWCC; SW_MODULE.
The script builds fresh sources, submits binaries directly, and stops on errors.
HELP
  exit 0
fi
[[ $# -le 2 ]] || die 'Usage: bash run_rma.sh [QUEUE] [NEW_OUTPUT_DIRECTORY]'
queue=${1:-${RMA_QUEUE:-q_share}}
[[ "$queue" =~ ^[a-zA-Z0-9_.-]+$ ]] || die 'Invalid queue name'
capacity=${BENCH_MAX_BYTES:-65536}
[[ "$capacity" =~ ^[0-9]{3,5}$ ]] && (( capacity >= 256 && capacity <= 65536 && capacity % 128 == 0 )) || die 'Invalid BENCH_MAX_BYTES'
profile=${RMA_PROFILE:-full}
[[ "$profile" == full || "$profile" == quick ]] || die 'RMA_PROFILE must be full or quick'
repeats=${RMA_REPEATS:-3}
[[ "$repeats" =~ ^[1-9][0-9]?$ ]] && (( repeats <= 20 )) || die 'RMA_REPEATS must be 1..20'
seed=${RMA_ORDER_SEED:-20261006}
[[ "$seed" =~ ^[1-9][0-9]{0,9}$ ]] && (( seed <= 1000000000 )) || die 'Invalid RMA_ORDER_SEED'
lat_reps=${RMA_LATENCY_REPS:-2000}
bw_reps=${RMA_BW_REPS:-2000}
[[ "$lat_reps" =~ ^[1-9][0-9]{0,5}$ ]] && (( lat_reps <= 100000 )) || die 'Invalid RMA_LATENCY_REPS'
[[ "$bw_reps" =~ ^[1-9][0-9]{0,6}$ ]] && (( bw_reps <= 1000000 )) || die 'Invalid RMA_BW_REPS'
cache=${RMA_CACHE_SIZE:-0}
[[ "$cache" == 0 || "$cache" == 32 ]] || die 'RMA_CACHE_SIZE must be 0 or 32; two RMA buffers need sufficient LDM'
diag=${RMA_DIAG_ONLY:-0}
[[ "$diag" == 0 || "$diag" == 1 ]] || die 'RMA_DIAG_ONLY must be 0 or 1'
if [[ "$diag" == 1 ]]; then repeats=1; fi
for tool in bsub awk sort cut tee; do command -v "$tool" >/dev/null || die "$tool not found"; done
swcc=${SWCC:-swgcc}
if ! command -v "$swcc" >/dev/null 2>&1; then
  type module >/dev/null 2>&1 || die 'Load the compiler first: module load swgcc/1473'
  module load "${SW_MODULE:-swgcc/1473}"
  hash -r
fi
command -v "$swcc" >/dev/null || die "Compiler not found: $swcc"
target=$("$swcc" -dumpmachine)
case "$target" in *sw_64*|*sw64*|*sunway*) ;; *) die "Compiler targets $target; Sunway required" ;; esac
out=${2:-"$script_dir/rma_results_$(date '+%Y%m%d_%H%M%S')_$$"}
mkdir -- "$out" || die 'Output directory must be new and its parent must exist'
out=$(cd -- "$out" && pwd)
mkdir "$out/source" "$out/build"
for file in rma_cluster_host.c rma_cluster_slave.c rma_cluster_suite.h bench_common.h run_rma.sh collect_rma.awk RMA_RUN.md; do
  cp "$script_dir/$file" "$out/source/$file"
done
{
  printf 'queue=%s\ncompiler=%s\ntarget=%s\nprofile=%s\nrepeats=%s\n' "$queue" "$(command -v "$swcc")" "$target" "$profile" "$repeats"
  printf 'capacity_bytes=%s\ncache_size_kib_requested=%s\norder_seed=%s\nlatency_reps=%s\nbandwidth_reps=%s\n' "$capacity" "$cache" "$seed" "$lat_reps" "$bw_reps"
  printf 'resource_request=MPE:1,CG:1,CPE:64\nresource_exclusivity=unknown\nshared_ldm_configuration=unknown\ncounter_frequency_hz=not_calibrated\n'
  printf 'resource_note=%s\n' "${RMA_RESOURCE_NOTE:-not_provided}"
  printf 'host_flags=-mhost -O2 -g\nslave_flags=-mslave -msimd -O2 -g\nlink_flags=-mhybrid -g\n'
  date -u '+submit_time_utc=%Y-%m-%dT%H:%M:%SZ'
  "$swcc" -v 2>&1
  if type module >/dev/null 2>&1; then module list 2>&1; fi
} > "$out/build_info.txt"
printf 'Building RMA with %s. Output: %s\n' "$swcc" "$out"
{
  "$swcc" -mhost -O2 -g "-DBENCH_MAX_BYTES=$capacity" -c "$out/source/rma_cluster_host.c" -o "$out/build/cluster_host.o"
  "$swcc" -mslave -msimd -O2 -g "-DBENCH_MAX_BYTES=$capacity" -c "$out/source/rma_cluster_slave.c" -o "$out/build/cluster_slave.o"
  "$swcc" -mhybrid -g "$out/build/cluster_host.o" "$out/build/cluster_slave.o" -o "$out/rma_cluster_bench"
} 2>&1 | tee "$out/build.log"

pairs=('0 1' '0 8' '0 9' '1 2' '8 16' '9 18' '0 7' '0 56' '0 63')
cases=(single intra2 split_near2 split_side2 split_far2 incast3 ring4 alltoall4)
lat_sizes=(8 16 32 64 128 256)
bw_sizes=(8 16 32 64 128 256 1024 4096 16384 32768 65536)
windows=(1 2 4 8 16)
clusters=(0 5 10 15)
if [[ "$profile" == quick ]]; then
  lat_sizes=(8); bw_sizes=(8 64 1024 16384 65536); windows=(1 4); clusters=(0 10)
fi
add_case() {
  # Stable ID identifies a configuration regardless of its shuffled order.
  local phase=$1 type=$2 name=$3 src=$4 dst=$5 bytes=$6 reps=$7 window=$8 cluster=$9 id
  id="${type}_${name}_s${src}_d${dst}_b${bytes}_r${reps}_w${window}_c${cluster}"
  printf '%s %s %s %s %s %s %s %s %s %s\n' "$phase" "$id" "$type" "$name" "$src" "$dst" "$bytes" "$reps" "$window" "$cluster"
}
for (( repeat=1; repeat<=repeats; repeat++ )); do
  rep_out="$out/repeat_$(printf '%02d' "$repeat")"
  mkdir "$rep_out" "$rep_out/smoke" "$rep_out/raw"
  {
    for pair in "${pairs[@]}"; do read -r src dst <<< "$pair"; add_case smoke bandwidth pair "$src" "$dst" 8 10 1 0; done
    for case_name in "${cases[@]}"; do add_case smoke contention "$case_name" 0 0 8 10 1 0; done
    add_case smoke latency pingpong_matrix 0 0 8 10 1 0
  } > "$rep_out/plan.txt"
  if [[ "$diag" == 0 ]]; then
    {
      for bytes in "${lat_sizes[@]}"; do add_case raw latency pingpong_matrix 0 0 "$bytes" "$lat_reps" 1 0; done
      for pair in "${pairs[@]}"; do
        read -r src dst <<< "$pair"
        for bytes in "${bw_sizes[@]}"; do
          for window in "${windows[@]}"; do
            if (( bytes * window <= capacity )); then add_case raw bandwidth pair "$src" "$dst" "$bytes" "$bw_reps" "$window" 0; fi
          done
        done
      done
      for cluster in "${clusters[@]}"; do
        for case_name in "${cases[@]}"; do
          incoming=1
          if [[ "$case_name" == incast3 || "$case_name" == alltoall4 ]]; then incoming=3; fi
          for bytes in 64 1024; do
            for window in 1 4; do
              if (( bytes * window * incoming <= capacity )); then add_case raw contention "$case_name" 0 0 "$bytes" "$bw_reps" "$window" "$cluster"; fi
            done
          done
        done
      done
    } > "$rep_out/formal_ordered.txt"
    # Deterministic shuffled formal cases; correctness probes always stay first.
    awk -v seed="$((seed + repeat))" '{seed=(seed*48271)%2147483647; printf "%.0f\t%s\n",seed,$0}' \
      "$rep_out/formal_ordered.txt" | LC_ALL=C sort -n | cut -f2- >> "$rep_out/plan.txt"
  fi
  awk 'BEGIN {print "order,phase,case_id,type,case,src,dst,bytes,reps,window,cluster_index"} {printf "%d",NR; for(i=1;i<=NF;i++) printf ",%s",$i; print ""}' \
    "$rep_out/plan.txt" > "$rep_out/plan.csv"
  printf 'repeat=%s\nshuffle_seed=%s\n' "$repeat" "$((seed + repeat))" > "$rep_out/run_info.txt"
  count=$(awk 'END {print NR}' "$rep_out/plan.txt")
  printf 'Submitting repeat %s/%s: %s cases; queue=%s, MPE=1, CG=1, CPE=64.\n' "$repeat" "$repeats" "$count" "$queue"
  if ! bsub -I -q "$queue" -n 1 -cgsp 64 -mpecg 1 -cache_size "$cache" \
    "$out/rma_cluster_bench" --suite "$rep_out/plan.txt" "$rep_out" 2>&1 | tee "$rep_out/job.log"; then
    die "Job failed; inspect $rep_out/job.log. Subsequent jobs were not submitted."
  fi
  [[ -f "$rep_out/RUN_COMPLETE" ]] || die "Suite did not complete: $rep_out/job.log"
  [[ $(cat "$rep_out/RUN_COMPLETE") == "completed_cases=$count" ]] || die 'Completion count differs from plan'
  awk -v out="$rep_out" -f "$out/source/collect_rma.awk" "$rep_out/plan.csv" || die "CSV validation failed: $rep_out"
  printf 'validated_cases=%s\n' "$count" > "$rep_out/COMPLETE"
done
# Retain independent repeat identity; do not average timings across jobs here.
printf 'repeat,case_id,phase,type,case,src,dst,bytes,reps,window,cluster_index,flows,max_cycles,aggregate_bytes_per_cycle,errors\n' > "$out/summary.csv"
printf 'repeat,case_id,phase,bytes,reps,initiator,peer,same_cluster,row_distance,col_distance,rtt_cycles,latency_cycles,errors\n' > "$out/latency.csv"
for (( repeat=1; repeat<=repeats; repeat++ )); do
  rep_out="$out/repeat_$(printf '%02d' "$repeat")"
  awk -v r="$repeat" 'NR>1 {print r "," $0}' "$rep_out/summary.csv" >> "$out/summary.csv"
  awk -v r="$repeat" 'NR>1 {print r "," $0}' "$rep_out/latency.csv" >> "$out/latency.csv"
done
printf 'validated_repeats=%s\ndiagnostic_only=%s\n' "$repeats" "$diag" > "$out/COMPLETE"
printf '\nDone. Results: %s\nBandwidth/contention: %s/summary.csv\nLatency matrices: %s/latency.csv\n' "$out" "$out" "$out"
