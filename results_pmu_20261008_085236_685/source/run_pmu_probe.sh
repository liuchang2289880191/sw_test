#!/usr/bin/env bash
set -euo pipefail
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
if [[ ${1:-} == --help ]]; then
    cat <<'HELP'
Usage: bash run_pmu_probe.sh [QUEUE] [NEW_OUTPUT_DIRECTORY]
PMU_PROFILE=smoke (default): 7 events, 2 pairs, 64 B, N=0/64/256,
  PUT/local controls, 2 repeats, 168 kernel calls in ONE job.
PMU_PROFILE=calibrate: 22 events, 8 pairs, 64 B/4 KiB,
  N=0/256/1024/4096, PUT/local controls, 3 repeats, 8448 kernel calls.
PMU_BUILD_ONLY=1 builds and records SDK, but does not submit a job.
SWCC=swgcc; SW_MODULE=swgcc/1473; SWPERF_PREFIX=/usr/sw/penv;
SWPERF_LIBDIR defaults to $SWPERF_PREFIX/lib; PYTHON=python3.
No target binary is executed on the login host. Old experiments stay untouched.
HELP
    exit 0
fi
[[ $# -le 2 ]] || die 'Too many arguments'
queue=${1:-q_share}; profile=${PMU_PROFILE:-smoke}; build_only=${PMU_BUILD_ONLY:-0}
[[ "$queue" =~ ^[a-zA-Z0-9_.-]+$ ]] || die 'Invalid queue'
[[ "$profile" == smoke || "$profile" == calibrate ]] || die 'Invalid PMU_PROFILE'
[[ "$build_only" == 0 || "$build_only" == 1 ]] || die 'Invalid PMU_BUILD_ONLY'
swcc=${SWCC:-swgcc}; py=${PYTHON:-python3}; prefix=${SWPERF_PREFIX:-/usr/sw/penv}
libdir=${SWPERF_LIBDIR:-"$prefix/lib"}
if ! command -v "$swcc" >/dev/null 2>&1; then
    type module >/dev/null 2>&1 || die 'Load the Sunway compiler module first'
    module load "${SW_MODULE:-swgcc/1473}"
fi
command -v "$swcc" >/dev/null || die 'Sunway compiler not available'
command -v "$py" >/dev/null || die 'Python 3 not available'
if [[ "$build_only" == 0 ]]; then command -v bsub >/dev/null || die 'bsub unavailable'; fi
[[ -r "$prefix/include/swperf.h" && -r "$libdir/libswperf.a" ]] || die 'swperf header/static library missing'
target=$("$swcc" -dumpmachine)
case "$target" in *sw_64*|*sw64*|*sunway*) ;; *) die "Compiler target is $target, not Sunway" ;; esac
out=${2:-"$script_dir/results_pmu_$(date '+%Y%m%d_%H%M%S')_$$"}
mkdir -- "$out" || die 'Output directory must be new, with an existing parent'
out=$(cd -- "$out" && pwd)
mkdir "$out/source" "$out/build"
for file in pmu_common.h pmu_host.c pmu_slave.c run_pmu_probe.sh analyze_pmu.py README.md; do
    cp "$script_dir/$file" "$out/source/$file"
done
cp "$prefix/include/swperf.h" "$out/swperf.h"
{
    printf 'queue=%s\nprofile=%s\ncompiler=%s\ntarget=%s\n' "$queue" "$profile" "$swcc" "$target"
    printf 'resource_request=MPE:1,CG:1,CPE:64\nresource_exclusivity=unknown\n'
    printf 'resource_note=%s\nstack_placement=not_forced_recorded_addresses_only\n' "${PMU_RESOURCE_NOTE:-not_provided}"
    printf 'swperf_prefix=%s\nlibdir=%s\n' "$prefix" "$libdir"
    date -Is
    "$swcc" -v 2>&1
    sha256sum "$prefix/include/swperf.h" "$libdir/libswperf.a"
} > "$out/build_info.txt"
{
    "$swcc" -mhost -O2 -g -I"$prefix/include" -c "$out/source/pmu_host.c" -o "$out/build/host.o"
    "$swcc" -mslave -msimd -O2 -g -c "$out/source/pmu_slave.c" -o "$out/build/slave.o"
    "$swcc" -mhybrid -g "$out/build/host.o" "$out/build/slave.o" -L"$libdir" -lswperf -o "$out/pmu_probe"
} 2>&1 | tee "$out/build.log"
if [[ "$build_only" == 1 ]]; then printf 'Build only: %s\n' "$out"; exit 0; fi
printf 'Submitting PMU %s job; results: %s\n' "$profile" "$out"
bsub -I -q "$queue" -n 1 -cgsp 64 -mpecg 1 -cache_size 0 \
    "$out/pmu_probe" "$out" "$profile" 2>&1 | tee "$out/job.log"
[[ -f "$out/RUN_COMPLETE" ]] || die 'Job incomplete; preserve output and inspect last PMU_CASE/PMU_STAGE'
"$py" "$out/source/analyze_pmu.py" "$out"
printf 'PMU results: %s\n' "$out"
