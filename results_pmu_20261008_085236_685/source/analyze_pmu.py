#!/usr/bin/env python3
"""Validate pilot output, describe count scaling; never label a route from these counts."""
import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path


def fit(points):
    xs, ys = zip(*points)
    xm, ym = statistics.mean(xs), statistics.mean(ys)
    denom = sum((x - xm) ** 2 for x in xs)
    slope = sum((x - xm) * (y - ym) for x, y in points) / denom
    intercept = ym - slope * xm
    rmse = (sum((y - intercept - slope * x) ** 2 for x, y in points) / len(points)) ** 0.5
    return intercept, slope, rmse


def analyze(root):
    if not (root / 'RUN_COMPLETE').exists():
        raise ValueError('Missing RUN_COMPLETE')
    with (root / 'counters.csv').open(newline='') as f:
        rows = list(csv.DictReader(f))
    with (root / 'checks.csv').open(newline='') as f:
        checks = list(csv.DictReader(f))
    case_cells, case_pes, cases = defaultdict(set), defaultdict(set), {}
    groups = defaultdict(lambda: defaultdict(list))
    for row in rows:
        cid, cell = int(row['case_id']), int(row['cell'])
        if cell in case_cells[cid] or cell not in range(16):
            raise ValueError('Duplicate or invalid counter cell')
        case_cells[cid].add(cell)
        meta = tuple(row[k] for k in ('event', 'repeat', 'mode', 'src', 'dst', 'bytes', 'n'))
        if cid in cases and cases[cid] != meta:
            raise ValueError('Inconsistent case metadata')
        cases[cid] = meta
        if int(row['decreased']) or int(row['after']) - int(row['before']) != int(row['delta']):
            raise ValueError('Counter decreased or inconsistent delta')
        key = tuple(row[k] for k in ('event', 'mode', 'src', 'dst', 'bytes', 'cell'))
        groups[key][int(row['n'])].append(int(row['delta']))
    for row in checks:
        cid, pe = int(row['case_id']), int(row['pe'])
        if cid not in cases or pe not in range(64) or pe in case_pes[cid] or int(row['errors']):
            raise ValueError('Invalid, duplicate, or failing PE result')
        case_pes[cid].add(pe)
        _, _, mode, src, dst, _, n = cases[cid]
        if mode == 'put':
            if pe == int(src) and int(row['local_done']) != int(n):
                raise ValueError('Local completion count mismatch')
            if pe == int(dst) and int(row['remote_done']) != int(n):
                raise ValueError('Remote completion count mismatch')
    expected = int((root / 'RUN_COMPLETE').read_text().strip().split('=')[1])
    if (root / 'runtime.txt').exists():
        runtime = dict(line.split('=', 1) for line in (root / 'runtime.txt').read_text().splitlines() if '=' in line)
        if expected != int(runtime['expected_cases']):
            raise ValueError('Case count differs from requested profile')
    if set(cases) != set(range(1, expected + 1)):
        raise ValueError('Missing cases')
    if any(len(case_cells[c]) != 16 or len(case_pes[c]) != 64 for c in cases):
        raise ValueError('Incomplete counter or PE arrays')
    output = []
    for key, series in sorted(groups.items()):
        if 0 not in series or len(series) < 3:
            raise ValueError('Need zero and at least two positive N values')
        points = [(n, statistics.median(v)) for n, v in sorted(series.items())]
        intercept, slope, rmse = fit(points)
        output.append(dict(zip(('event', 'mode', 'src', 'dst', 'bytes', 'cell'), key),
                           intercept=intercept, count_per_operation=slope, fit_rmse=rmse,
                           zero_median=statistics.median(series[0]),
                           max_repeat_range=max(max(v)-min(v) for v in series.values())))
    with (root / 'count_scaling.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=list(output[0]))
        writer.writeheader()
        writer.writerows(output)
    audit = dict(cases=len(cases), counter_rows=len(rows), pe_checks=len(checks),
                 integrity='passed', hardware_event_validity='requires calibration',
                 cell_mapping='uncalibrated', topology='not inferred',
                 note='One job; repeated windows are not independent jobs. Fit RMSE is not a confidence interval.')
    (root / 'audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    print('Integrity checks passed: {} cases; count_scaling.csv written.'.format(len(cases)))
    print('Counter sensitivity, scope, mapping and path interpretation still require review.')
    return audit


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python3 analyze_pmu.py RESULT_DIRECTORY')
    analyze(Path(sys.argv[1]))
