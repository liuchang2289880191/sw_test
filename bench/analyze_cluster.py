#!/usr/bin/env python3
"""Analyze 2x2-cluster hypotheses from one or more ping-pong CSV files."""
import argparse
import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path


def write_svg(path, grid, origin, size):
    vals = list(grid.values())
    low, high = min(vals), max(vals)
    cell, margin = 66, 55
    width = height = margin + 8 * cell + 20
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
             f'height="{height}" viewBox="0 0 {width} {height}">',
             '<rect width="100%" height="100%" fill="white"/>',
             f'<text x="{margin}" y="23" font-size="17">'
             f'origin {origin}, {size} B, RTT/2 cycles</text>']
    for i in range(8):
        parts.append(f'<text x="{margin + i * cell + 28}" y="43" '
                     f'font-size="13">{i}</text>')
        parts.append(f'<text x="23" y="{margin + i * cell + 36}" '
                     f'font-size="13">{i}</text>')
    for dst in range(64):
        x, y = margin + dst % 8 * cell, margin + dst // 8 * cell
        if dst == origin:
            fill, label = '#eeeeee', 'self'
        else:
            value = grid[dst]
            t = (value - low) / (high - low) if high > low else 0.5
            r = round(40 + 210 * t)
            g = round(130 - 75 * t)
            b = round(220 - 185 * t)
            fill, label = f'#{r:02x}{g:02x}{b:02x}', f'{value:.1f}'
        parts.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" '
                     f'fill="{fill}" stroke="white" stroke-width="2"/>')
        parts.append(f'<text x="{x + cell/2}" y="{y + cell/2 + 5}" '
                     f'text-anchor="middle" font-size="13" fill="black">'
                     f'{label}</text>')
    parts.append('</svg>')
    Path(path).write_text('\n'.join(parts), encoding='utf-8')


def solve(a, b):
    n = len(b)
    m = [list(a[i]) + [b[i]] for i in range(n)]
    for c in range(n):
        pivot = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[pivot][c]) < 1e-12:
            return None
        m[c], m[pivot] = m[pivot], m[c]
        div = m[c][c]
        for j in range(c, n + 1):
            m[c][j] /= div
        for r in range(n):
            if r == c:
                continue
            scale = m[r][c]
            for j in range(c, n + 1):
                m[r][j] -= scale * m[c][j]
    return [m[i][n] for i in range(n)]


def fit(rows, features):
    vectors = [[1.0] + [r[key] for key in features] for r in rows]
    ys = [r["latency_cycles"] for r in rows]
    k = len(vectors[0])
    gram = [[sum(v[i] * v[j] for v in vectors) for j in range(k)]
            for i in range(k)]
    rhs = [sum(v[i] * y for v, y in zip(vectors, ys)) for i in range(k)]
    coeff = solve(gram, rhs)
    if coeff is None:
        return None
    sse = sum((y - sum(x * c for x, c in zip(v, coeff))) ** 2
              for v, y in zip(vectors, ys))
    mean = statistics.mean(ys)
    sst = sum((y - mean) ** 2 for y in ys)
    r2 = 1 - sse / sst if sst else 1.0
    bic = len(rows) * math.log(max(sse / len(rows), 1e-30)) + k * math.log(len(rows))
    return coeff, r2, bic


def main():
    p = argparse.ArgumentParser()
    p.add_argument("csv_files", nargs="+")
    p.add_argument("--origin", type=int, default=0)
    p.add_argument("--svg-prefix", help="write an 8x8 SVG for each message size")
    args = p.parse_args()
    if not 0 <= args.origin < 64:
        p.error("--origin must be 0..63")
    rows = []
    per_size = defaultdict(list)
    for path in args.csv_files:
        count = 0
        with open(path, newline="", encoding="utf-8") as f:
            for raw in csv.DictReader(f):
                if raw.get("benchmark") != "rma_pingpong":
                    continue
                r = {key: int(raw[key]) for key in
                     ("bytes", "initiator", "peer", "same_cluster",
                      "row_distance", "col_distance", "errors")}
                r["latency_cycles"] = float(raw["latency_cycles"])
                if r["errors"]:
                    p.error(f"correctness error in {path}")
                r["cross_cluster"] = 1 - r["same_cluster"]
                rows.append(r)
                per_size[r["bytes"]].append(r)
                count += 1
        if count != 64 * 63:
            p.error(f"{path}: expected 4032 non-self pairs, got {count}")

    for size, group in sorted(per_size.items()):
        print(f"\n{size} B: {len(group)} directed initiator/peer measurements")
        for axis, dr, dc in (("horizontal neighbor", 0, 1),
                             ("vertical neighbor", 1, 0)):
            near = [r["latency_cycles"] for r in group
                    if r["row_distance"] == dr and r["col_distance"] == dc
                    and r["same_cluster"]]
            cross = [r["latency_cycles"] for r in group
                     if r["row_distance"] == dr and r["col_distance"] == dc
                     and r["cross_cluster"]]
            print(f"{axis:21} within={statistics.median(near):.2f} "
                  f"across={statistics.median(cross):.2f} "
                  f"delta={statistics.median(cross)-statistics.median(near):+.2f} cycles")
        grid = {r["peer"]: r["latency_cycles"] for r in group
                if r["initiator"] == args.origin}
        print(f"origin={args.origin}, destination grid (RTT/2 cycles):")
        for row in range(8):
            print(" ".join("   self" if row * 8 + col == args.origin else
                           f"{grid[row * 8 + col]:7.1f}" for col in range(8)))
        if args.svg_prefix:
            path = f"{args.svg_prefix}_{size}B.svg"
            write_svg(path, grid, args.origin, size)
            print(f"SVG: {path}")

    size_features = ["bytes"] if len(per_size) > 1 else []
    print("\nDescriptive OLS models (lower BIC is better; topology remains an inference):")
    models = [
        ("size", size_features),
        ("size+cluster", size_features + ["cross_cluster"]),
        ("size+distance", size_features + ["row_distance", "col_distance"]),
        ("size+cluster+distance", size_features +
         ["cross_cluster", "row_distance", "col_distance"]),
    ]
    for name, features in models:
        result = fit(rows, features)
        if result is None:
            print(f"{name:23} singular")
            continue
        coeff, r2, bic = result
        terms = ", ".join(f"{key}={value:.4f}" for key, value in
                          zip(["intercept"] + features, coeff))
        print(f"{name:23} R2={r2:.5f} BIC={bic:.1f}  {terms}")


if __name__ == "__main__":
    main()
