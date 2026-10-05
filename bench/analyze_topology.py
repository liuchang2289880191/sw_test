#!/usr/bin/env python3
"""Summarize one rma_bench CSV without third-party packages."""
import argparse
import csv
import statistics
from collections import defaultdict


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_file")
    parser.add_argument("--origin", type=int, default=0,
                        help="initiator shown as an 8x8 destination map (default: 0)")
    args = parser.parse_args()
    if not 0 <= args.origin < 64:
        parser.error("--origin must be 0..63")

    rows = []
    with open(args.csv_file, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row.get("benchmark") != "rma" or row.get("relation") == "self_skipped":
                continue
            row["initiator"] = int(row["initiator"])
            row["peer"] = int(row["peer"])
            row["cycles_per_op"] = float(row["cycles_per_op"])
            row["errors"] = int(row["errors"])
            rows.append(row)
    if len(rows) != 64 * 63:
        parser.error(f"expected 4032 non-self pairs, got {len(rows)}")
    if any(r["errors"] for r in rows):
        parser.error("correctness errors in CSV; do not interpret timing")

    first = rows[0]
    print(f"operation={first['operation']} bytes={first['bytes']} reps={first['reps']}")
    grouped = defaultdict(list)
    distances = defaultdict(list)
    matrix = {}
    for r in rows:
        s, d = r["initiator"], r["peer"]
        v = r["cycles_per_op"]
        grouped[r["relation"]].append(v)
        distances[abs(s // 8 - d // 8) + abs(s % 8 - d % 8)].append(v)
        if s == args.origin:
            matrix[d] = v
    print("\nRelation        pairs  median cycles/op  min       max")
    for name in ("same_row", "same_col", "diagonal", "other"):
        v = grouped[name]
        print(f"{name:15} {len(v):5} {statistics.median(v):16.2f} "
              f"{min(v):8.2f} {max(v):8.2f}")
    print("\nManhattan hops  pairs  median cycles/op")
    for hops, v in sorted(distances.items()):
        print(f"{hops:14} {len(v):5} {statistics.median(v):16.2f}")
    print(f"\nInitiator {args.origin} to destination [row][col] (cycles/op):")
    for row in range(8):
        print(" ".join("   self" if row * 8 + col == args.origin else
                       f"{matrix[row * 8 + col]:7.1f}" for col in range(8)))


if __name__ == "__main__":
    main()
