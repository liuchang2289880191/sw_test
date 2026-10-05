#!/usr/bin/env bash
set -euo pipefail

# Run inside compute resources allocated by the site scheduler.
# BENCH_MAX_BYTES must match the compile-time macro (default: 65536).
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
out=${1:-dma_results}
capacity=${BENCH_MAX_BYTES:-65536}
if [[ ! "$capacity" =~ ^[1-9][0-9]{2,4}$ ]]; then
  echo 'BENCH_MAX_BYTES must be 256..65536 and a multiple of 128' >&2
  exit 2
fi
if (( capacity < 256 || capacity > 65536 || capacity % 128 )); then
  echo 'BENCH_MAX_BYTES must be 256..65536 and a multiple of 128' >&2
  exit 2
fi
if [[ ! -x "$script_dir/dma_bench" ]]; then
  echo "Executable not found: $script_dir/dma_bench" >&2
  exit 2
fi
mkdir -p "$out"

for mode in get put iget iput; do
  for active in 1 64; do
    for offset in 0 4; do
      for bytes in 8 16 32 64 128 256 512 1024 2048 4096 8192 16384 32768 65536; do
        if (( bytes > capacity )); then continue; fi
        reps=10000
        if (( bytes >= 1024 )); then reps=1000; fi
        printf 'DMA mode=%s active=%s offset=%s bytes=%s reps=%s\n' \
          "$mode" "$active" "$offset" "$bytes" "$reps"
        "$script_dir/dma_bench" "$mode" "$bytes" "$reps" "$active" "$offset" \
          > "$out/dma_${mode}_${active}pe_${bytes}B_offset${offset}.csv"
      done
    done
  done
done
