#!/usr/bin/env bash
# Login-node work only. Compute node executes a single native suite binary.
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
if [[ ${1:-} == --help || ${1:-} == -h ]]; then
  cat <<'HELP'
Usage: bash run_supplement.sh [QUEUE] [NEW_OUTPUT_DIRECTORY]
Default: quick profile, 5 independent jobs, 2048 measured rounds per case.
TOPO_PROFILE=quick|full; TOPO_REPEATS=1..20; TOPO_REPS=64..16384, multiple of 64.
TOPO_SEED=20261007; TOPO_RESOURCE_NOTE='actual allocation/sharing details'.
TOPO_DIAG_ONLY=1 runs 6 small correctness cases in one job.
TOPO_TRACE=0|1 (default: diagnostic=1, performance=0).
TOPO_WAIT_TIMEOUT_CYCLES=1000000000 bounds reply waits/background stop waits.
TOPO_CASE_TIMEOUT_SECONDS=60 bounds each target kernel (1..3600).
SWCC=swgcc; SW_MODULE=swgcc/1473; PYTHON=python3 (login node only).
No old benchmark, old script, or old results are modified.
HELP
  exit 0
fi
[[ $# -le 2 ]] || die 'Too many arguments'
queue=${1:-q_share}
[[ "$queue" =~ ^[a-zA-Z0-9_.-]+$ ]] || die 'Invalid queue'
profile=${TOPO_PROFILE:-quick}
[[ "$profile" == quick || "$profile" == full ]] || die 'Invalid profile'
repeats=${TOPO_REPEATS:-5}; reps=${TOPO_REPS:-2048}; seed=${TOPO_SEED:-20261007}
[[ "$repeats" =~ ^[1-9][0-9]?$ ]] && ((repeats <= 20)) || die 'Invalid repeat count'
[[ "$reps" =~ ^[1-9][0-9]{1,4}$ ]] && ((reps >= 64 && reps <= 16384 && reps % 64 == 0)) || die 'Invalid reps'
[[ "$seed" =~ ^[1-9][0-9]{0,8}$ ]] || die 'Invalid seed'
diag=${TOPO_DIAG_ONLY:-0}; [[ "$diag" == 0 || "$diag" == 1 ]] || die 'Invalid diagnostic flag'
if [[ "$diag" == 1 ]]; then repeats=1; reps=64; fi
trace=${TOPO_TRACE:-$diag}; [[ "$trace" == 0 || "$trace" == 1 ]] || die 'Invalid trace flag'
wait_cycles=${TOPO_WAIT_TIMEOUT_CYCLES:-1000000000}
[[ "$wait_cycles" =~ ^[1-9][0-9]{4,19}$ ]] || die 'Invalid wait timeout cycles (minimum 10000)'
case_seconds=${TOPO_CASE_TIMEOUT_SECONDS:-60}
[[ "$case_seconds" =~ ^[1-9][0-9]{0,3}$ ]] && ((case_seconds <= 3600)) || die 'Invalid case timeout seconds'
export TOPO_TRACE="$trace" TOPO_WAIT_TIMEOUT_CYCLES="$wait_cycles" TOPO_CASE_TIMEOUT_SECONDS="$case_seconds"
py=${PYTHON:-python3}; swcc=${SWCC:-swgcc}
for tool in bsub tee "$py"; do command -v "$tool" >/dev/null || die "$tool not found"; done
if ! command -v "$swcc" >/dev/null 2>&1; then
  type module >/dev/null 2>&1 || die 'Load the Sunway compiler first'
  module load "${SW_MODULE:-swgcc/1473}"
fi
command -v "$swcc" >/dev/null || die 'Sunway compiler unavailable'
target=$("$swcc" -dumpmachine)
case "$target" in *sw_64*|*sw64*|*sunway*) ;; *) die "Compiler target is $target, not Sunway" ;; esac
out=${2:-"$script_dir/results_$(date '+%Y%m%d_%H%M%S')_$$"}
mkdir -- "$out" || die 'Output directory must be new; parent must exist'
out=$(cd -- "$out" && pwd)
mkdir "$out/source" "$out/build"
for file in topology_host.c topology_slave.c topology_common.h generate_plan.py analyze.py run_supplement.sh DESIGN.md; do
  cp "$script_dir/$file" "$out/source/$file"
done
{
  printf 'queue=%s\ncompiler=%s\ntarget=%s\nprofile=%s\nrepeats=%s\nreps=%s\nseed=%s\n' "$queue" "$swcc" "$target" "$profile" "$repeats" "$reps" "$seed"
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
  rep="$out/repeat_$(printf '%02d' "$repeat")"
  mkdir "$rep" "$rep/raw"
  if [[ "$diag" == 1 ]]; then
    "$py" "$out/source/generate_plan.py" --out "$rep" --profile quick --reps 64 --seed "$seed" --diagnostic
  else
    "$py" "$out/source/generate_plan.py" --out "$rep" --profile "$profile" --reps "$reps" --seed "$((seed+repeat))"
  fi
  # The login host may use another CPU architecture. Even --validate-plan
  # cannot run this target binary there; the native parser checks every case
  # on the allocated compute node, before launching its CPE kernel.
  printf 'Submitting supplemental job %s/%s; %s\n' "$repeat" "$repeats" "$rep"
  bsub -I -q "$queue" -n 1 -cgsp 64 -mpecg 1 -cache_size 0 \
    "$out/rma_topology_bench" --suite "$rep/plan.txt" "$rep" 2>&1 | tee "$rep/job.log"
  [[ -f "$rep/RUN_COMPLETE" ]] || die "Incomplete job: $rep"
done
if [[ "$diag" == 0 ]]; then "$py" "$out/source/analyze.py" "$out"; fi
printf 'completed_jobs=%s\ndiagnostic_only=%s\n' "$repeats" "$diag" > "$out/COMPLETE"
printf 'Supplemental results: %s\n' "$out"
