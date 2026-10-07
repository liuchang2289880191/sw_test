"""Generate a standalone Sunway plan and route hypotheses; stdlib only.

No access to the old benchmark or results. Coordinates describe hypotheses,
not observed hardware routes. Run this on the login node or this workstation.
"""
import argparse
import csv
import json
from pathlib import Path
import random

CAPACITY = 32768


def member(block, local=0):
    return (block // 4 * 2 + local // 2) * 8 + block % 4 * 2 + local % 2


def block(pe):
    return (pe // 8 // 2) * 4 + pe % 8 // 2


def path(src, dst, order):
    r, c = divmod(src, 4)
    rd, cd = divmod(dst, 4)
    nodes = [src]
    for axis in order:
        if axis == "X":
            while c != cd:
                c += 1 if cd > c else -1
                nodes.append(4 * r + c)
        else:
            while r != rd:
                r += 1 if rd > r else -1
                nodes.append(4 * r + c)
    return nodes


def features(probe, bg):
    ps, pd = map(block, probe)
    bs, bd = map(block, bg)
    result = {}
    for order in ("XY", "YX"):
        bp = path(bs, bd, order)
        be = set(zip(bp, bp[1:]))
        for name, ends in (("forward", (ps, pd)), ("reply", (pd, ps))):
            pp = path(*ends, order)
            pe = set(zip(pp, pp[1:]))
            result[f"{order}_{name}_same_direction"] = len(pe & be)
            result[f"{order}_{name}_opposite_direction"] = len(pe & {(b, a) for a, b in be})
            result[f"{order}_{name}_shared_internal_nodes"] = len((set(pp) - {ps, pd}) & set(bp))
    return result


def capacity_ok(flows, size, window, mode):
    backgrounds = flows[1:] if mode else flows
    incoming = {}
    for src, dst in backgrounds:
        incoming[dst] = incoming.get(dst, 0) + 1
    return size * window <= CAPACITY and size * window * max(incoming.values(), default=1) <= CAPACITY


def build(profile, reps, seed):
    groups = []
    route_rows = []
    def add(family, label, control, treatment, size, window, mode=0,
            reply=0, control_mode=None, control_reply=None):
        if not all(capacity_ok(f, size, window, mode) for f in (control, treatment)):
            return
        if mode and treatment[1:]:
            probe_endpoints = set(treatment[0])
            assert all(not (set(f) & probe_endpoints) for f in treatment[1:])
        gid = f"g{len(groups):04d}"
        cm = mode if control_mode is None else control_mode
        cr = reply if control_reply is None else control_reply
        variants = [dict(role="control", mode=cm, reply=cr, flows=control),
                    dict(role="treatment", mode=mode, reply=reply, flows=treatment)]
        groups.append(dict(group=gid, family=family, label=label, size=size,
                           window=window, variants=variants))
        return gid

    # E0: compare local-completion throughput with per-message reply protocols.
    pairs = [(0, 1), (1, 2), (0, 63)]
    for s, d in pairs:
        for size in ([8, 1024] if profile == "quick" else [8, 64, 1024, 4096]):
            for reply in sorted({8, size}):
                add("completion", f"s{s}_d{d}_reply{reply}", [(s, d)], [(s, d)],
                    size, 1, mode=1, reply=reply, control_mode=0, control_reply=0)

    # E1: CPE vs cluster sharing. All bulk combinations have their own solo references.
    sizes = [1024, 4096] if profile == "full" else [4096]
    windows = [1, 4, 8] if profile == "full" else [4]
    origins = [5, 10] if profile == "full" else [5]
    for origin in origins:
        remote = [b for b in (0, 3, 12, 15) if b != origin]
        for n in ([2, 4] if profile == "full" else [2]):
            same_src = [(member(origin, i), member(remote[i])) for i in range(n)]
            shared_src = [(member(origin), member(remote[i])) for i in range(n)]
            split_src = [(member(remote[i]), member(origin, i)) for i in range(n)]
            same_dst = [(d, s) for s, d in same_src]
            shared_dst = [(d, member(origin)) for s, d in same_src]
            # Separate clusters necessarily alter geometry; solo normalization is required.
            spread_sources = [(member((origin + i + 1) % 16), d)
                              for i, (s, d) in enumerate(same_src)]
            if any(s == d for s, d in spread_sources):
                spread_sources = [(member((origin + i + 5) % 16), d)
                                  for i, (s, d) in enumerate(same_src)]
            spread_destinations = [(d, s) for s, d in spread_sources]
            comparisons = [("source_cpe", same_src, shared_src),
                           ("destination_cpe", same_dst, shared_dst),
                           ("source_cluster", spread_sources, same_src),
                           ("destination_cluster", spread_destinations, split_src)]
            for size in sizes:
                for w in windows:
                    for kind, control, treatment in comparisons:
                        add("ports", f"{kind}_b{origin}_n{n}", control, treatment, size, w)

    # E2: separate cores, same geometric edge: co-direction / opposite-direction / separate edge.
    for a, b, c, d in [(5, 6, 9, 10), (5, 9, 6, 10)]:
        p = (member(a), member(b))
        for size in sizes:
            for w in windows:
                add("directions", f"opposed_b{a}_b{b}", [p, (member(a, 1), member(b, 1))],
                    [p, (member(b, 1), member(a, 1))], size, w)
                add("directions", f"shared_edge_b{a}_b{b}", [p, (member(c), member(d))],
                    [p, (member(a, 1), member(b, 1))], size, w)

    # E3: active probe and sustained background; background never uses probe endpoint blocks.
    probes = [(0, 15), (3, 12), (12, 3), (15, 0)] if profile == "full" else [(0, 15), (15, 0)]
    probe_sizes = [8, 64, 1024] if profile == "full" else [8, 1024]
    bg_sizes = [1024, 4096] if profile == "full" else [4096]
    bg_windows = [1, 4, 8] if profile == "full" else [4]
    for ps, pd in probes:
        probe = (member(ps), member(pd))
        categories = {"XY_forward": [], "YX_forward": [], "neither_forward": []}
        for bs in range(16):
            for bd in range(16):
                if bs == bd or {bs, bd} & {ps, pd}:
                    continue
                if abs(bs // 4 - bd // 4) + abs(bs % 4 - bd % 4) != 1:
                    continue
                bg = (member(bs), member(bd))
                f = features(probe, bg)
                x, y = f["XY_forward_same_direction"], f["YX_forward_same_direction"]
                cat = "XY_forward" if x and not y else "YX_forward" if y and not x else "neither_forward" if not x and not y else None
                if cat:
                    categories[cat].append((bg, f))
        for category, options in categories.items():
            # Both row and column positions where possible; all options in full profile.
            chosen = options if profile == "full" else options[:2]
            for bg, f in chosen:
                for probe_size in probe_sizes:
                    for bg_size in bg_sizes:
                        for w in bg_windows:
                            # Probe and background payload sizes are independently recorded.
                            label = f"p{ps}_{pd}_bg{block(bg[0])}_{block(bg[1])}_{category}_pb{probe_size}"
                            gid = add("routes", label, [probe], [probe, bg], bg_size, w,
                                      mode=1, reply=8)
                            if gid:
                                groups[-1]["probe_bytes"] = probe_size
                                route_rows.append(dict(group=gid, probe_src=probe[0], probe_dst=probe[1],
                                                       background_src=bg[0], background_dst=bg[1],
                                                       probe_bytes=probe_size, reply_bytes=8,
                                                       background_bytes=bg_size, window=w, category=category, **f))

    rng = random.Random(seed)
    rng.shuffle(groups)  # Entire matched groups, not individual cases.
    plan = []
    for g in groups:
        variants = g["variants"]
        order = [0, 1, 1, 0] if rng.randrange(2) else [1, 0, 0, 1]
        # Solo references for each distinct bulk flow, immediately before and after its group.
        solos = sorted(set(f for v in variants if v["mode"] == 0 for f in v["flows"]))
        def emit(role, mode, reply, flows):
            case_id = f"{g['group']}_{role}_{len(plan):05d}"
            plan.append(dict(case_id=case_id, group=g["group"], family=g["family"], label=g["label"],
                             role=role, mode=mode, bytes=g["size"], probe_bytes=g.get("probe_bytes", g["size"]),
                             reply_bytes=reply, reps=reps, window=g["window"], flows=flows))
        for f in solos:
            emit(f"solo_s{f[0]}_d{f[1]}_before", 0, 0, [f])
        for v in order:
            item = variants[v]
            emit(item["role"], item["mode"], item["reply"], item["flows"])
        for f in reversed(solos):
            emit(f"solo_s{f[0]}_d{f[1]}_after", 0, 0, [f])
    return plan, route_rows


def write_plan(out, profile="quick", reps=2048, seed=20261007, diagnostic=False):
    if not 64 <= reps <= 16384 or reps % 64:
        raise ValueError("reps must be a multiple of 64 in 64..16384")
    out.mkdir(parents=True, exist_ok=True)
    plan, route_rows = build(profile, reps, seed)
    if diagnostic:
        specifications = [(0, 8, 8, 0, 1, [(0, 1)]),
                          (0, 64, 64, 0, 4, [(0, 1), (8, 1)]),
                          (0, 4096, 4096, 0, 4, [(0, 1), (8, 9)]),
                          (1, 8, 8, 8, 1, [(0, 63)]),
                          (1, 1024, 1024, 8, 1, [(0, 1)]),
                          (1, 1024, 64, 8, 4, [(0, 63), (2, 4), (8, 16)])]
        plan = [dict(case_id=f"diag_{i:02d}", group=f"diag_{i:02d}", family="diagnostic", label="correctness",
                     role="diagnostic", mode=m, bytes=b, probe_bytes=pb, reply_bytes=rb, reps=64, window=w, flows=flows)
                for i, (m, b, pb, rb, w, flows) in enumerate(specifications)]
        route_rows = []
    with (out / "plan.txt").open("w", encoding="ascii", newline="\n") as f:
        f.write("# case group family label role mode background_or_bulk_bytes probe_bytes reply_bytes reps window nflows src dst ...\n")
        for p in plan:
            values = [p[k] for k in ("case_id", "group", "family", "label", "role", "mode", "bytes", "probe_bytes", "reply_bytes", "reps", "window")]
            values += [len(p["flows"])] + [i for pair in p["flows"] for i in pair]
            f.write(" ".join(map(str, values)) + "\n")
    (out / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    with (out / "route_features.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(route_rows[0]) if route_rows else ["group"])
        w.writeheader(); w.writerows(route_rows)
    (out / "plan_info.json").write_text(json.dumps(dict(profile=profile, reps=reps, seed=seed,
        groups=len({p["group"] for p in plan}), cases=len(plan), buffer_bytes=CAPACITY,
        routes_are_hypotheses=True), indent=2) + "\n", encoding="utf-8")
    return plan, route_rows


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--profile", choices=["quick", "full"], default="quick")
    ap.add_argument("--reps", type=int, default=2048)
    ap.add_argument("--seed", type=int, default=20261007)
    ap.add_argument("--diagnostic", action="store_true")
    a = ap.parse_args()
    p, r = write_plan(a.out, a.profile, a.reps, a.seed, a.diagnostic)
    print(f"Generated {len(p)} cases / {len({x['group'] for x in p})} matched groups; no hardware execution.")
