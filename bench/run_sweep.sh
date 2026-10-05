#!/usr/bin/env bash
set -euo pipefail

out=${1:-results}
mkdir -p "$out"

for mode in get put iget iput; do
  for active in 1 64; do
    for bytes in 4 32 128 1024 8192 65536; do
      reps=1000
      if [ "$bytes" -ge 8192 ]; then reps=200; fi
      ./bench/dma_bench "$mode" "$bytes" "$reps" "$active" 0 > "$out/dma_${mode}_${active}pe_${bytes}B.csv"
    done
  done
done

# The full directed matrix is generated separately for each transfer size.
for op in put get; do
  for bytes in 4 64 1024 16384; do
    reps=100
    ./bench/rma_bench "$op" "$bytes" "$reps" > "$out/rma_${op}_${bytes}B.csv"
  done
done

for scope in row col array; do
  for bytes in 4 64 1024 16384; do
    ./bench/rma_bcast_bench "$scope" "$bytes" 200 0 > "$out/rma_bcast_${scope}_${bytes}B.csv"
  done
done
