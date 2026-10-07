"""Validate standalone raw results and calculate matched within-job effects.

Positive route ratios mean LONGER RTT (worse), unlike bandwidth ratios.
Stdlib only. Refuses missing, corrupt, zero-time, or capped-background results.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics as st


def rows(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def csv_write(path, values):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(values[0]) if values else ["group"])
        w.writeheader(); w.writerows(values)


def checked(rep, p):
    path = rep / "raw" / (p["case_id"] + ".csv")
    data = rows(path)
    aggregate = [x for x in data if x["record"] == "aggregate"]
    if len(aggregate) != 1:
        raise ValueError(f"{path}: missing or duplicate aggregate")
    pe = {int(x["pe"]): x for x in data if x["record"] == "pe"}
    if len(pe) != sum(x["record"] == "pe" for x in data):
        raise ValueError(f"{path}: duplicate PE")
    active = {i for pair in p["flows"] for i in pair}
    if set(pe) != active:
        raise ValueError(f"{path}: active PE set mismatch")
    for x in data:
        if x["record"] not in {"pe", "aggregate", "sample"}:
            raise ValueError(f"{path}: unknown row")
        if int(x["errors"]) or int(x["background_limit_hit"]) or int(x["cycles"]) <= 0:
            raise ValueError(f"{path}: errors, zero timing, or background did not cover probe")
    a = aggregate[0]
    value = float(a["value"])
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{path}: invalid metric")
    if p["mode"]:
        source = pe[p["flows"][0][0]]
        expected = int(source["cycles"]) / p["reps"]
        if int(a["cycles"]) != int(source["cycles"]):
            raise ValueError(f"{path}: wrong probe initiator")
        sample = [x for x in data if x["record"] == "sample"]
        if len(sample) != p["reps"] // 64 or {int(x["pe"]) for x in sample} != set(range(p["reps"] // 64)):
            raise ValueError(f"{path}: sample count/index mismatch")
        for x in sample:
            if not math.isclose(float(x["value"]), int(x["cycles"]) / 64, rel_tol=1e-8):
                raise ValueError(f"{path}: sample value mismatch")
        if int(source["sent"]) != p["reps"] or int(source["received"]) != p["reps"]:
            raise ValueError(f"{path}: probe count mismatch")
        bg = [x for i, x in pe.items() if i not in p["flows"][0]]
        if sum(int(x["sent"]) for x in bg) != sum(int(x["received"]) for x in bg):
            raise ValueError(f"{path}: background sent/received mismatch")
        for src, dst in p["flows"][1:]:
            if not int(pe[src]["sent"]) or not int(pe[src]["send_cycles"]) or not int(pe[dst]["received"]):
                raise ValueError(f"{path}: missing background traffic")
    else:
        if any(x["record"] == "sample" for x in data):
            raise ValueError(f"{path}: unexpected samples")
        max_cycles = max(int(x["cycles"]) for x in pe.values())
        expected = p["bytes"] * p["reps"] * len(p["flows"]) / max_cycles
        if int(a["cycles"]) != max_cycles:
            raise ValueError(f"{path}: max PE timing mismatch")
        for i, x in pe.items():
            out = sum(s == i for s, d in p["flows"])
            inc = sum(d == i for s, d in p["flows"])
            if int(x["sent"]) != out * p["reps"] or int(x["received"]) != inc * p["reps"]:
                raise ValueError(f"{path}: payload count mismatch")
    if not math.isclose(value, expected, rel_tol=1e-8, abs_tol=1e-8):
        raise ValueError(f"{path}: aggregate formula mismatch")
    if p["family"] == "completion":
        source = pe[p["flows"][0][0]]
        value = int(source["send_cycles"]) / p["reps"]
    return value, dict(case_id=p["case_id"], sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                       bytes=path.stat().st_size)


def analyze(root):
    effects, audit, route_effects = [], [], []
    reps = sorted(root.glob("repeat_*"))
    if not reps:
        raise ValueError("No repeat_* directories")
    canonical = None
    for rep in reps:
        plan = json.loads((rep / "plan.json").read_text(encoding="utf-8"))
        complete = (rep / "RUN_COMPLETE").read_text().strip()
        if complete != f"completed_cases={len(plan)}":
            raise ValueError(f"{rep}: incomplete job")
        expected_files = {p["case_id"] + ".csv" for p in plan}
        if {p.name for p in (rep / "raw").glob("*.csv")} != expected_files:
            raise ValueError(f"{rep}: raw file set differs from plan")
        groups = {}
        for p in plan:
            value, item = checked(rep, p)
            audit.append(dict(repeat=rep.name, **item))
            groups.setdefault(p["group"], []).append((p, value))
        signature = {g: [(p["family"], p["label"], p["role"], p["mode"], p["bytes"],
                          p["probe_bytes"], p["reply_bytes"], p["reps"], p["window"], p["flows"])
                         for p, v in sorted(items, key=lambda x: (x[0]["role"], x[0]["case_id"]))]
                     for g, items in groups.items()}
        # Ignore randomized case order/IDs; retain every configuration dimension.
        normalized = {g: sorted((json.dumps(x, sort_keys=True) for x in s)) for g, s in signature.items()}
        if canonical is None: canonical = normalized
        elif canonical != normalized: raise ValueError("Configurations differ between jobs")
        for g, items in groups.items():
            control = [v for p, v in items if p["role"] == "control"]
            treatment = [v for p, v in items if p["role"] == "treatment"]
            if len(control) != 2 or len(treatment) != 2:
                raise ValueError(f"{g}: expected ABBA/BAAB four cases")
            p = next(p for p, v in items if p["role"] == "treatment")
            c, t = st.median(control), st.median(treatment)
            unit = "sender_cycles_per_data" if p["family"] == "completion" else "RTT_cycles" if p["mode"] else "B_per_cycle"
            effect = dict(repeat=rep.name, group=g, family=p["family"], label=p["label"],
                bytes=p["bytes"], probe_bytes=p["probe_bytes"], reply_bytes=p["reply_bytes"], window=p["window"],
                metric=unit, control=c, treatment=t, treatment_over_control=t/c, difference=t-c,
                control_range_pct=(max(control)-min(control))/c*100,
                treatment_range_pct=(max(treatment)-min(treatment))/t*100,
                control_efficiency="", treatment_efficiency="", efficiency_ratio="")
            if not p["mode"]:
                solos = {}
                for q, v in items:
                    if q["role"].startswith("solo_"):
                        solos.setdefault(tuple(q["flows"][0]), []).append(v)
                variants = [next(q for q, v in items if q["role"] == role) for role in ("control", "treatment")]
                eff = []
                for q, val in zip(variants, (c, t)):
                    denominator = sum(st.median(solos[tuple(f)]) for f in q["flows"])
                    eff.append(val / denominator)
                effect.update(control_efficiency=eff[0], treatment_efficiency=eff[1], efficiency_ratio=eff[1]/eff[0])
            effects.append(effect)
        feature_by_group = {r["group"]: r for r in rows(rep / "route_features.csv")}
        for e in effects:
            if e["repeat"] == rep.name and e["family"] == "routes":
                route_effects.append(dict(**e, **{k:v for k,v in feature_by_group[e["group"]].items() if k not in e}))
    out = root / "analysis"
    out.mkdir(exist_ok=True)
    csv_write(out / "paired_effects.csv", effects)
    csv_write(out / "route_effects.csv", route_effects)
    csv_write(out / "raw_audit.csv", audit)
    grouped = {}
    for e in effects: grouped.setdefault(e["group"], []).append(e)
    summary = []
    for g, es in sorted(grouped.items()):
        ratios = [e["treatment_over_control"] for e in es]
        summary.append(dict(group=g, family=es[0]["family"], label=es[0]["label"], metric=es[0]["metric"],
            jobs=len(es), ratio_median=st.median(ratios), ratio_min=min(ratios), ratio_max=max(ratios),
            difference_median=st.median(e["difference"] for e in es),
            max_control_range_pct=max(e["control_range_pct"] for e in es),
            jobs_treatment_larger=sum(x > 1 for x in ratios),
            efficiency_ratio_median=st.median(e["efficiency_ratio"] for e in es) if es[0]["efficiency_ratio"] != "" else ""))
    csv_write(out / "summary.csv", summary)
    (out / "READ_ME.txt").write_text(
        "Validated all planned files, active PEs, payload counts and metric formulas.\n"
        "routes: treatment/control > 1 means LONGER RTT; bulk: > 1 means HIGHER bandwidth.\n"
        "completion compares different protocols; it is not a hardware one-way latency ratio.\n"
        "sample rows are means of 64 consecutive RTTs, not individual-message tail latencies.\n"
        "min/max are observed job ranges, not confidence intervals.\n"
        "XY/YX edges are hypotheses on the 4x4 geometric block grid, not measured physical links.\n"
        "Fit/compare hypotheses only after checking effect reproducibility and route identifiability.\n",
        encoding="utf-8")
    print(f"Validated {len(audit)} files; {len(effects)} within-job effects; output: {out}")
    return effects


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("results", type=Path)
    analyze(ap.parse_args().results)
