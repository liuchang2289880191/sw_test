#!/usr/bin/env python3
"""Compare aggregate bandwidth in single-, shared- and split-cluster runs."""
import argparse
import csv
from collections import defaultdict
from statistics import median


def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv_files", nargs="+")
    args = p.parse_args()
    values = defaultdict(list)
    for path in args.csv_files:
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("benchmark") != "rma_flow" or row.get("pe") != "aggregate":
                    continue
                if int(row["errors"]):
                    p.error(f"correctness error in {path}")
                key = (int(row["bytes"]), int(row["window"]),
                       int(row["cluster_index"]), row["case"])
                values[key].append(float(row["aggregate_bytes_per_cycle"]))
    if not values:
        p.error("no rma_flow aggregate rows")
    for size, window, cluster in sorted({key[:3] for key in values}):
        print(f"\nbytes={size} window={window} cluster={cluster} "
              "(aggregate payload B/cycle)")
        base = values.get((size, window, cluster, "single"))
        base_bw = median(base) if base else None
        for case in ("single", "intra2", "split_near2", "split_side2",
                     "split_far2",
                     "incast3", "ring4", "alltoall4"):
            v = values.get((size, window, cluster, case))
            if not v:
                continue
            bw = median(v)
            factor = f"{bw/base_bw:.3f}x single" if base_bw else ""
            print(f"{case:14} {bw:12.6f}  {factor}")
        intra = values.get((size, window, cluster, "intra2"))
        for split in ("split_near2", "split_side2", "split_far2"):
            other = values.get((size, window, cluster, split))
            if intra and other:
                print(f"{split}/intra2 = {median(other)/median(intra):.3f}")


if __name__ == "__main__":
    main()
