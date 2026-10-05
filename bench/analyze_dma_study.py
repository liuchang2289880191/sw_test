"""Independently validate DMA study records and derive reproducible comparisons.

Only reads measured data; never builds, submits or executes a Sunway benchmark.
Usage: python bench/analyze_dma_study.py RESULTS --out OUTPUT_DIRECTORY
"""
import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
import numpy as np

MODES = ("get", "put", "iget", "iput")
ACTIVES = (1, 2, 4, 8, 16, 32, 64)
MAPS = ("identity", "reverse", "transpose", "shuffle")
BOUNDARY = (64,96,124,128,132,192,252,256,260)
LOAD = (8,16,32,64,96,124,128,132,192,252,256,260,384,512,768,1024,1536,
        2048,3072,4096,6144,8192,12288,16384,24576,32768,49152,65536,98304,131072)
MAPPED = (64,128,256,4096,32768,65536,98304,131072)
RAW_FIELDS = "benchmark,mode,bytes,reps,active_pes,offset,pe,cycles,cycles_per_op,aggregate_bytes_per_cycle,errors,slot_stride,mapping,mapping_seed,slot,src_address,dst_address".split(",")

def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))

def write_csv(path, rows):
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer=csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)

def key(r):
    return (r["phase"],r["mode"],int(r["active_pes"]),int(r["bytes"]),int(r["offset"]),int(r["slot_stride"]),r["mapping"])

def stats(values):
    v=np.asarray(values, dtype=float)
    return {"n":len(v), "min":float(v.min()), "median":float(np.median(v)),
            "p90":float(np.quantile(v,.9)), "max":float(v.max())}

def permutation(seed):
    a=list(range(64)); state=seed
    for i in range(63,0,-1):
        state ^= (state<<13)&0xffffffff; state ^= state>>17; state ^= (state<<5)&0xffffffff
        j=state%(i+1); a[i],a[j]=a[j],a[i]
    return a

def analyze(source, out):
    info=dict(line.split("=",1) for line in (source/"build_info.txt").read_text().splitlines() if "=" in line)
    cap=int(info["capacity_bytes"]); seed=int(info["mapping_seed"]); base_stride=cap+128
    strides=list(dict.fromkeys([base_stride,cap+256,cap+4096,2*cap]))
    maps={"identity":list(range(64)), "reverse":list(reversed(range(64))),
          "transpose":[(i%8)*8+i//8 for i in range(64)], "shuffle":permutation(seed)}
    slot_data=read_csv(source/"slot_maps.csv")
    assert len(slot_data)==256
    seen=set()
    for r in slot_data:
        pair=r["mapping"],int(r["pe"])
        assert pair not in seen; seen.add(pair)
        assert int(r["mapping_seed"])==seed and int(r["slot"])==maps[pair[0]][pair[1]]
    plan=read_csv(source/"plan.csv"); summary=read_csv(source/"study_summary.csv")
    expected=set()
    for phase,sizes,offs in (("boundary",BOUNDARY,(0,4,64,124)),("load",LOAD,(0,4)),("mapping",MAPPED,(0,4))):
        for m in MODES:
            for n in ACTIVES:
                for s in sizes:
                    if s>cap: continue
                    for o in offs:
                        for t in strides if phase=="mapping" else (base_stride,):
                            for k in MAPS if phase=="mapping" else ("identity",):
                                expected.add((phase,m,n,s,o,t,k))
    assert len(plan)==len(summary)==len(expected)
    assert {key(r) for r in plan}==expected
    assert {key(r) for r in summary}==expected
    assert {r["filename"] for r in plan}=={p.name for p in (source/"raw").glob("*.csv")}
    for marker in ("RUN_COMPLETE","COMPLETE"):
        assert (source/marker).read_text().strip()==f"completed_cases={len(expected)}"
    S={int(r["case_id"]):r for r in summary}
    assert len(S)==len(summary)
    pe_cycles=np.full((len(plan),64),np.nan)
    common_bases=None; raw_pes=0
    digest=hashlib.sha256()

    def validate(path, config, case_id=None):
        nonlocal common_bases, raw_pes
        digest.update(path.name.encode()); digest.update(path.read_bytes())
        with path.open(encoding="utf-8-sig",newline="") as f:
            reader=csv.DictReader(f); assert reader.fieldnames==RAW_FIELDS, path
            rr=list(reader)
        n=int(config["active_pes"]); s=int(config["bytes"]); o=int(config["offset"])
        t=int(config["slot_stride"]); reps=int(config["reps"]); mapping=config["mapping"]
        assert len(rr)==n+1
        assert t%128==0 and t>=s+o
        actual={}; aggregate=None
        for r in rr:
            assert r["benchmark"]=="dma" and r["mode"]==config["mode"]
            for col in ("bytes","reps","active_pes","offset","slot_stride","mapping_seed"):
                assert int(r[col])==int(config[col]), (path,col)
            assert r["mapping"]==mapping and int(r["errors"])==0
            cycles=int(r["cycles"]); assert cycles>0
            assert math.isclose(float(r["cycles_per_op"]),cycles/reps,abs_tol=1.01e-6,rel_tol=0)
            if r["pe"]=="aggregate":
                assert aggregate is None; aggregate=r
                assert not any(r[x] for x in ("slot","src_address","dst_address"))
            else:
                pe=int(r["pe"]); assert pe not in actual and 0<=pe<n
                slot=int(r["slot"]); assert slot==maps[mapping][pe]
                bases=tuple(int(r[c],16)-slot*t-o for c in ("src_address","dst_address"))
                if common_bases is None: common_bases=bases
                assert bases==common_bases and all(b%128==0 for b in bases)
                assert r["aggregate_bytes_per_cycle"]==""
                actual[pe]=cycles
                if case_id: pe_cycles[case_id-1,pe]=cycles/reps
        assert set(actual)==set(range(n)) and aggregate is not None
        worst=max(actual.values()); assert int(aggregate["cycles"])==worst
        assert math.isclose(float(aggregate["aggregate_bytes_per_cycle"]),s*reps*n/worst,abs_tol=1.01e-9,rel_tol=0)
        if case_id:
            sr=S[case_id]; assert key(sr)==key(config)
            for col in ("cycles","cycles_per_op","aggregate_bytes_per_cycle","errors"):
                assert sr[col]==aggregate[col], (path,col)
        raw_pes+=n

    for i,r in enumerate(plan,1):
        assert int(r["case_id"])==i and r["filename"]==f"case_{i:06d}.csv"
        assert int(r["mapping_seed"])==seed
        assert int(r["reps"])==(10000 if int(r["bytes"])<1024 else 1000)
        validate(source/"raw"/r["filename"],r,i)
    assert len(list((source/"smoke").glob("*.csv")))==8
    for m in MODES:
        for n in (1,64):
            validate(source/"smoke"/f"{m}_{n}pe.csv",dict(mode=m,active_pes=n,bytes=8,offset=0,slot_stride=base_stride,reps=10,mapping="identity",mapping_seed=seed))
    D={key(r):r for r in summary}
    def row(phase,m,n,s,o=0,t=base_stride,k="identity"): return D[phase,m,n,s,o,t,k]
    def bw(*args): return float(row(*args)["aggregate_bytes_per_cycle"])
    def cy(*args): return float(row(*args)["cycles_per_op"])
    scaling=read_csv(source/"study_scaling.csv")
    expected_scaling=set()
    for r in summary:
        if int(r["active_pes"])!=1: expected_scaling.add(key(r))
    assert len(scaling)==len(expected_scaling) and {key(r) for r in scaling}==expected_scaling
    for r in scaling:
        phase,m,n,s,o,t,k=key(r)
        one=bw(phase,m,1,s,o,t,k); many=bw(phase,m,n,s,o,t,k)
        for name,target,tolerance in (("single_bytes_per_cycle",one,1.01e-9),("aggregate_bytes_per_cycle",many,1.01e-9),
                                     ("bandwidth_ratio_to1",many/one,1.1e-6),("parallel_efficiency",many/one/n,1.1e-6)):
            assert math.isclose(float(r[name]),target,abs_tol=tolerance,rel_tol=0), r

    boundaries=[]
    for m in MODES:
        for n in ACTIVES:
            for s in BOUNDARY:
                for o in (0,4,64,124):
                    boundaries.append(dict(mode=m,active_pes=n,bytes=s,offset=o,cycles_per_op=cy("boundary",m,n,s,o),
                        aggregate_bytes_per_cycle=bw("boundary",m,n,s,o),slowdown_to_offset0=cy("boundary",m,n,s,o)/cy("boundary",m,n,s,0),
                        host_128B_blocks=(o+s+127)//128))
    loads=[]
    for m in MODES:
        for s in LOAD:
            if s>cap: continue
            for o in (0,4):
                vals=[bw("load",m,n,s,o) for n in ACTIVES]; peak=max(vals); peak_n=ACTIVES[vals.index(peak)]
                loads.append(dict(mode=m,bytes=s,offset=o,peak_active_pes=peak_n,peak_bytes_per_cycle=peak,
                    smallest_n_at_95pct_observed_peak=next(n for n,v in zip(ACTIVES,vals) if v>=.95*peak),
                    single_bytes_per_cycle=vals[0],aggregate64_bytes_per_cycle=vals[-1],ratio64_to1=vals[-1]/vals[0],
                    loss64_to_observed_peak=1-vals[-1]/peak))
    layout=[]
    for m in MODES:
        for n in ACTIVES:
            for s in MAPPED:
                if s>cap: continue
                for o in (0,4):
                    rr=[row("mapping",m,n,s,o,t,k) for t in strides for k in MAPS]
                    lo=min(rr,key=lambda r:float(r["aggregate_bytes_per_cycle"])); hi=max(rr,key=lambda r:float(r["aggregate_bytes_per_cycle"]))
                    identity_vals=[bw("mapping",m,n,s,o,t) for t in strides]
                    layout.append(dict(mode=m,active_pes=n,bytes=s,offset=o,
                        best_bw=float(hi["aggregate_bytes_per_cycle"]),worst_bw=float(lo["aggregate_bytes_per_cycle"]),
                        layout_max_to_min=float(hi["aggregate_bytes_per_cycle"])/float(lo["aggregate_bytes_per_cycle"]),
                        best_stride=int(hi["slot_stride"]),best_mapping=hi["mapping"],worst_stride=int(lo["slot_stride"]),worst_mapping=lo["mapping"],
                        identity_stride_max_to_min=max(identity_vals)/min(identity_vals),
                        max_mapping_ratio_at_fixed_stride=max(max(bw("mapping",m,n,s,o,t,k) for k in MAPS)/min(bw("mapping",m,n,s,o,t,k) for k in MAPS) for t in strides)))
    overlaps=[]
    for first,second,sizes in (("boundary","load",BOUNDARY),("load","mapping",MAPPED)):
        for m in MODES:
            for n in ACTIVES:
                for s in sizes:
                    if s>cap: continue
                    for o in (0,4):
                        a=row(first,m,n,s,o); b=row(second,m,n,s,o)
                        ratio=float(b["aggregate_bytes_per_cycle"])/float(a["aggregate_bytes_per_cycle"])
                        overlaps.append(dict(first_phase=first,second_phase=second,mode=m,active_pes=n,bytes=s,offset=o,
                            first_case_id=int(a["case_id"]),second_case_id=int(b["case_id"]),first_bw=float(a["aggregate_bytes_per_cycle"]),
                            second_bw=float(b["aggregate_bytes_per_cycle"]),bw_ratio_second_to_first=ratio,abs_relative_change=abs(ratio-1)))
    correlations=[]
    for m in MODES:
        for s in MAPPED:
            if s>cap: continue
            for o in (0,4):
                for t in strides:
                    r0=row("mapping",m,64,s,o,t); reference=pe_cycles[int(r0["case_id"])-1]
                    for k in MAPS[1:]:
                        r=row("mapping",m,64,s,o,t,k); physical=pe_cycles[int(r["case_id"])-1]
                        byslot=np.empty(64); byslot[np.asarray(maps[k])]=physical
                        correlations.append(dict(mode=m,bytes=s,offset=o,slot_stride=t,mapping=k,
                            corr_by_pe=float(np.corrcoef(reference,physical)[0,1]),corr_by_slot=float(np.corrcoef(reference,byslot)[0,1]),
                            reference_cv=float(np.std(reference)/np.mean(reference)),mapped_cv=float(np.std(physical)/np.mean(physical))))
    result=dict(source=str(source.resolve()),capacity_bytes=cap,mapping_seed=seed,phase_counts=dict(Counter(r["phase"] for r in summary)),
        formal_cases=len(plan),smoke_cases=8,validated_pe_rows=raw_pes,scaling_rows=len(scaling),all_errors_zero=True,
        fixed_src_base=hex(common_bases[0]),fixed_dst_base=hex(common_bases[1]),raw_content_sha256=digest.hexdigest(),
        source_sha256={name:hashlib.sha256((source/name).read_bytes()).hexdigest() for name in
            ("plan.csv","slot_maps.csv","study_summary.csv","study_scaling.csv","build_info.txt","cpuinfo.txt",
             "source/dma_host.c","source/dma_slave.c","source/bench_common.h")},
        cache_size_kib=info.get("cache_size_kib"),resource_exclusivity=info.get("resource_exclusivity"),
        overlap_stats={f"{a}_to_{b}":stats([r["abs_relative_change"] for r in overlaps if r["first_phase"]==a and r["second_phase"]==b]) for a,b in (("boundary","load"),("load","mapping"))},
        sync_async_ratios={f"{async_}/{sync}":stats([bw("load",async_,n,s,o)/bw("load",sync,n,s,o) for n in ACTIVES for s in LOAD if s<=cap for o in (0,4)]) for sync,async_ in (("get","iget"),("put","iput"))},
        layout64_stats={m:stats([r["layout_max_to_min"] for r in layout if r["mode"]==m and r["active_pes"]==64]) for m in MODES},
        correlation64_stats={m:dict(corr_by_pe=stats([r["corr_by_pe"] for r in correlations if r["mode"]==m]),corr_by_slot=stats([r["corr_by_slot"] for r in correlations if r["mode"]==m])) for m in MODES})
    out.mkdir(parents=True,exist_ok=True)
    for name,data in (("boundary_comparisons",boundaries),("load_peaks",loads),("layout_comparisons",layout),("phase_overlap_comparisons",overlaps),("pe_slot_correlations",correlations)):
        write_csv(out/(name+".csv"),data)
    np.savez_compressed(out/"pe_cycles.npz",cycles_per_op=pe_cycles)
    (out/"verification.json").write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))
    print("BOUNDARY64 put size and cycles for offsets 0 4 64 124")
    for s in BOUNDARY: print(s,*[round(cy("boundary","put",64,s,o),2) for o in (0,4,64,124)])
    print("LOAD large aligned: mode N and bandwidth for 4 32 64 96 128 KiB")
    for m in MODES:
        for n in ACTIVES: print(m,n,*[round(bw("load",m,n,s),4) for s in (4096,32768,65536,98304,131072) if s<=cap])
    print("Top full64 layout contrasts")
    for r in sorted((r for r in layout if r["active_pes"]==64),key=lambda r:r["layout_max_to_min"],reverse=True)[:8]: print(r)
    print("Largest phase overlaps")
    for r in sorted(overlaps,key=lambda r:r["abs_relative_change"],reverse=True)[:8]: print(r)

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results",type=Path); parser.add_argument("--out",required=True,type=Path)
    args=parser.parse_args(); analyze(args.results,args.out)
