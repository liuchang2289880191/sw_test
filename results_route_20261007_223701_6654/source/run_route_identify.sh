#!/usr/bin/env bash
# Standalone extension; never runs a Sunway binary on the login host.
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
if [[ ${1:-} == --help || ${1:-} == -h ]]; then
  cat <<'HELP'
Usage: bash run_route_identify.sh [QUEUE] [NEW_OUTPUT_DIRECTORY]
Default: 64 matched groups / 256 cases per job; 5 jobs; 2048 RTT per case.
TOPO_DIAG_ONLY=1: four new diagonal-background correctness cases in one job.
TOPO_REPEATS=1..20; TOPO_REPS=64..16384, multiple of 64; TOPO_SEED=20261008.
TOPO_TRACE=0|1 (default diagnostic=1, performance=0).
TOPO_WAIT_TIMEOUT_CYCLES=1000000000; TOPO_CASE_TIMEOUT_SECONDS=60.
PYTHON=python3 (stdlib only); SWCC=swgcc; SW_MODULE=swgcc/1473.
Every performance plan must pass exact rank 14/14 for both probe directions.
Original experiments/results are not changed. Candidate geometry is not routing proof.
HELP
  exit 0
fi
[[ $# -le 2 ]] || die 'Too many arguments'
queue=${1:-q_share}; [[ "$queue" =~ ^[a-zA-Z0-9_.-]+$ ]] || die 'Invalid queue'
repeats=${TOPO_REPEATS:-5}; reps=${TOPO_REPS:-2048}; seed=${TOPO_SEED:-20261008}
[[ "$repeats" =~ ^[1-9][0-9]?$ ]] && ((repeats<=20)) || die 'Invalid repeats'
[[ "$reps" =~ ^[1-9][0-9]{1,4}$ ]] && ((reps>=64 && reps<=16384 && reps%64==0)) || die 'Invalid reps'
[[ "$seed" =~ ^[1-9][0-9]{0,8}$ ]] || die 'Invalid seed'
diag=${TOPO_DIAG_ONLY:-0}; [[ "$diag" == 0 || "$diag" == 1 ]] || die 'Invalid diagnostic flag'
if [[ "$diag" == 1 ]]; then repeats=1; reps=64; fi
trace=${TOPO_TRACE:-$diag}; [[ "$trace" == 0 || "$trace" == 1 ]] || die 'Invalid trace'
wait_cycles=${TOPO_WAIT_TIMEOUT_CYCLES:-1000000000}
[[ "$wait_cycles" =~ ^[1-9][0-9]{4,19}$ ]] || die 'Invalid wait timeout'
case_seconds=${TOPO_CASE_TIMEOUT_SECONDS:-60}
[[ "$case_seconds" =~ ^[1-9][0-9]{0,3}$ ]] && ((case_seconds<=3600)) || die 'Invalid case timeout'
export TOPO_TRACE="$trace" TOPO_WAIT_TIMEOUT_CYCLES="$wait_cycles" TOPO_CASE_TIMEOUT_SECONDS="$case_seconds"
py=${PYTHON:-python3}; swcc=${SWCC:-swgcc}
for tool in bsub tee "$py"; do command -v "$tool" >/dev/null || die "$tool unavailable"; done
if ! command -v "$swcc" >/dev/null 2>&1; then
  type module >/dev/null 2>&1 || die 'Load the Sunway compiler first'
  module load "${SW_MODULE:-swgcc/1473}"
fi
command -v "$swcc" >/dev/null || die 'Compiler unavailable'
target=$("$swcc" -dumpmachine)
case "$target" in *sw_64*|*sw64*|*sunway*) ;; *) die "Not a Sunway target: $target" ;; esac
out=${2:-"$script_dir/results_route_$(date '+%Y%m%d_%H%M%S')_$$"}
mkdir -- "$out" || die 'Output directory must be new; parent must exist'
out=$(cd -- "$out" && pwd)
mkdir "$out/source" "$out/build"
for file in topology_host.c topology_slave.c topology_common.h generate_plan.py analyze.py base_analysis.py design_math.py layouts.json run_route_identify.sh README.md KERNEL_PROVENANCE.json; do
  cp "$script_dir/$file" "$out/source/$file"
done
{
  printf 'queue=%s\ncompiler=%s\ntarget=%s\nprofile=route_identify\nrepeats=%s\nreps=%s\nseed=%s\n' "$queue" "$swcc" "$target" "$repeats" "$reps" "$seed"
  printf 'resource_request=MPE:1,CG:1,CPE:64\ncache_size_kib_requested=0\nresource_exclusivity=unknown\n'
  printf 'buffer_bytes_each=32768\ncounter_frequency=not_calibrated\nresource_note=%s\n' "${TOPO_RESOURCE_NOTE:-not_provided}"
  printf 'trace=%s\nwait_timeout_cycles=%s\ncase_timeout_seconds=%s\n' "$trace" "$wait_cycles" "$case_seconds"
  date -u '+submit_time_utc=%Y-%m-%dT%H:%M:%SZ'
  "$swcc" -v 2>&1
} > "$out/build_info.txt"
{
  "$swcc" -mhost -O2 -g -c "$out/source/topology_host.c" -o "$out/build/host.o"
  "$swcc" -mslave -msimd -O2 -g -c "$out/source/topology_slave.c" -o "$out/build/slave.o"
  "$swcc" -mhybrid -g "$out/build/host.o" "$out/build/slave.o" -o "$out/rma_topology_bench"
} 2>&1 | tee "$out/build.log"
for ((repeat=1; repeat<=repeats; repeat++)); do
  rep="$out/repeat_$(printf '%02d' "$repeat")"; mkdir "$rep" "$rep/raw"
  if [[ "$diag" == 1 ]]; then
    "$py" "$out/source/generate_plan.py" --out "$rep" --reps 64 --seed "$seed" --diagnostic
  else
    "$py" "$out/source/generate_plan.py" --out "$rep" --reps "$reps" --seed "$((seed+repeat))"
  fi
  printf 'Submitting route-identifiability job %s/%s; %s\n' "$repeat" "$repeats" "$rep"
  bsub -I -q "$queue" -n 1 -cgsp 64 -mpecg 1 -cache_size 0 \
    "$out/rma_topology_bench" --suite "$rep/plan.txt" "$rep" 2>&1 | tee "$rep/job.log"
  [[ -f "$rep/RUN_COMPLETE" ]] || die "Incomplete job: $rep"
done
if [[ "$diag" == 0 ]]; then "$py" "$out/source/analyze.py" "$out"; fi
printf 'completed_jobs=%s\ndiagnostic_only=%s\n' "$repeats" "$diag" > "$out/COMPLETE"
printf 'Route-identifiability results: %s\n' "$out"
