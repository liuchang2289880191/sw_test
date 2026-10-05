#!/usr/bin/env bash
set -euo pipefail

out=${1:-cluster_results}
# Match the BENCH_MAX_BYTES value used to compile this executable.
capacity=${BENCH_MAX_BYTES:-65536}
if [[ ! "$capacity" =~ ^[0-9]+$ ]]; then
  echo 'BENCH_MAX_BYTES must be an integer' >&2; exit 2
fi
if (( capacity < 256 || capacity > 65536 || capacity % 128 )); then
  echo 'BENCH_MAX_BYTES must be 256..65536 and a multiple of 128' >&2; exit 2
fi
mkdir -p "$out"

# Small-message RTT/2 matrix. Repeat the whole job to assess run-to-run noise.
./bench/rma_cluster_bench latency 8 2000 > "$out/pingpong_8B.csv"

# Geometry controls: same 2x2, one-step boundary crossings, long row/column.
pairs=("0 1" "0 8" "0 9" "1 2" "8 16" "9 18" "0 7" "0 56" "0 63")
for pair in "${pairs[@]}"; do
  read -r src dst <<< "$pair"
  for bytes in 8 16 32 64 128 256 1024 4096 16384 32768 65536; do
    for window in 1 2 4 8 16; do
      if (( bytes * window > capacity )); then continue; fi
      ./bench/rma_cluster_bench bandwidth "$src" "$dst" "$bytes" 1000 "$window" \
        > "$out/bw_${src}_${dst}_${bytes}B_w${window}.csv"
    done
  done
done

# Matched contention cases at two sizes and two windows.
for bytes in 64 1024; do
  for window in 1 4; do
    for cluster in 0 5 10 15; do
      for case in single intra2 split_near2 split_side2 split_far2 incast3 ring4 alltoall4; do
        incoming=1
        if [[ "$case" == incast3 || "$case" == alltoall4 ]]; then incoming=3; fi
        if (( bytes * window * incoming > capacity )); then continue; fi
        ./bench/rma_cluster_bench contention "$case" "$bytes" 2000 "$window" "$cluster" \
          > "$out/cont_${case}_c${cluster}_${bytes}B_w${window}.csv"
      done
    done
  done
done
