#!/usr/bin/env bash
# Login-node SDK inventory. Does not submit jobs, initialize PMU, or run CPE code.
set -euo pipefail
umask 077
out_parent=${1:-.}
out_dir="$out_parent/swperf_capabilities_$(date +%Y%m%d_%H%M%S)_$$"
mkdir -p -- "$out_parent"
mkdir -- "$out_dir"
exec > >(tee "$out_dir/inventory.txt") 2>&1

printf 'Purpose: SDK inventory only; no hardware counter execution.\n'
printf 'Collected: '; date -Is
printf 'Login host: '; hostname
printf 'System: '; uname -srm
printf '\nCompiler location/version:\n'
if command -v swgcc >/dev/null 2>&1; then
    command -v swgcc
    swgcc --version || true
else
    printf 'swgcc not in PATH; load the usual compiler module before compiling probes.\n'
fi

sdk_prefix=${SWPERF_PREFIX:-/usr/sw/penv}
printf '\nSWPERF_PREFIX=%s\n' "$sdk_prefix"
header="$sdk_prefix/include/swperf.h"
if [[ -r "$header" ]]; then
    cp -- "$header" "$out_dir/swperf.h"
    printf '\nHeader hash:\n'
    if command -v sha256sum >/dev/null 2>&1; then sha256sum -- "$header"; fi
    printf '\nRelevant declarations (full header is also saved):\n'
    pattern='penv_cg_(stn|tbox)|penv_slave[0-9]_.*(rma|cycle)|include|typedef'
    if command -v rg >/dev/null 2>&1; then
        rg -n "$pattern" "$header" || true
    else
        grep -nE "$pattern" "$header" || true
    fi
else
    printf '\nHeader unavailable: %s\n' "$header"
    printf 'Set SWPERF_PREFIX to the installed prefix if different.\n'
fi

printf '\nLibrary files and selected symbols:\n'
shopt -s nullglob
libs=("$sdk_prefix"/lib/libswperf* "$sdk_prefix"/lib64/libswperf*)
if ((${#libs[@]} == 0)); then printf 'No matching libswperf files found.\n'; fi
for library in "${libs[@]}"; do
    [[ -f "$library" ]] || continue
    ls -l -- "$library"
    if command -v sha256sum >/dev/null 2>&1; then sha256sum -- "$library"; fi
    if command -v nm >/dev/null 2>&1; then
        # Failure on a foreign architecture or stripped library is inconclusive.
        case "$library" in
            *.a) nm -g --defined-only "$library" > "$out_dir/$(basename "$library").symbols.txt" 2>&1 || true ;;
            *) nm -D --defined-only "$library" > "$out_dir/$(basename "$library").symbols.txt" 2>&1 || true ;;
        esac
    fi
done

printf '\nUnknown until a compute-node test: event permissions, counter width, array mapping,\n'
printf 'scope/isolation, event compatibility, RMA sensitivity, and path identifiability.\n'
printf 'Output directory: %s\n' "$out_dir"
