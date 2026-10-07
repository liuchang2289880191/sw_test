"""Audit the 2026-10-07 supplement and derive report tables without editing inputs."""
from pathlib import Path
import csv
import hashlib
import json
import math
import re
import statistics as st
import sys
import numpy as np
import pandas as pd
from analyze import checked
from inspect_route_identifiability import matrix as design_matrix

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'outputs/results_20261007_211507_31272'
OUT = ROOT / 'outputs/rma_supplement_report_20261007'
TABLES = OUT / '分析表'


def read(path):
    with path.open(encoding='utf-8', newline='') as f:
        return list(csv.DictReader(f))


def block(pe):
    return (pe // 8 // 2) * 4 + pe % 8 // 2


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    OUT.mkdir(exist_ok=True)
    TABLES.mkdir(exist_ok=True)
    manifest = [{'file': p.relative_to(SRC).as_posix(), 'sha256': sha(p)}
                for p in sorted(SRC.rglob('*')) if p.is_file()]
    cases, effects, background, samples, jobs, variants = [], [], [], [], [], {}
    supplied = pd.read_csv(SRC / 'analysis/paired_effects.csv').set_index(['repeat', 'group'])
    signature = None
    for rep in sorted(SRC.glob('repeat_*')):
        plan = json.loads((rep / 'plan.json').read_text(encoding='utf-8'))
        assert len(plan) == 234
        assert (rep / 'RUN_COMPLETE').read_text().strip() == 'completed_cases=234'
        assert {p.name for p in (rep / 'raw').glob('*.csv')} == {p['case_id']+'.csv' for p in plan}
        sig = sorted(json.dumps({k:v for k,v in p.items() if k != 'case_id'}, sort_keys=True) for p in plan)
        if signature is None: signature = sig
        else: assert sig == signature
        resource = dict(line.split('=', 1) for line in (rep / 'resource_runtime.txt').read_text().splitlines() if '=' in line)
        joblog = (rep / 'job.log').read_text(encoding='utf-8')
        assert 'TOPO_TIMEOUT' not in joblog and 'TOPO_CASE_TIMEOUT' not in joblog and 'FAILED' not in joblog
        ids = re.findall(r'Job <(\d+)>', joblog)
        jobs.append(dict(repeat=rep.name, job=ids[0] if ids else '', node=resource['hostname'],
                         seed=json.loads((rep/'plan_info.json').read_text())['seed'], cases=len(plan)))
        groups = {}
        features = {p['group']:p for p in read(rep/'route_features.csv')}
        for p in plan:
            val, audit = checked(rep, p)
            raw = read(rep/'raw'/(p['case_id']+'.csv'))
            assert all(int(r['wait_stage']) == 0 for r in raw)
            pe = {int(r['pe']):r for r in raw if r['record']=='pe'}
            aggregate = next(r for r in raw if r['record']=='aggregate')
            source = pe[p['flows'][0][0]]
            item = dict(repeat=rep.name, **p, value=val, aggregate_value=float(aggregate['value']),
                        source_cycles_per_data=int(source['send_cycles'])/p['reps'],
                        sha256=audit['sha256'], raw_file_bytes=audit['bytes'])
            cases.append(item)
            groups.setdefault(p['group'], []).append((p, val, item))
            if p['role'] in ('control','treatment'):
                variants.setdefault(p['group'], {})[p['role']] = p
            if p['family']=='routes':
                if p['role']=='treatment':
                    s,d = p['flows'][1]
                    assert int(pe[s]['sent']) == int(pe[d]['received'])
                    background.append(dict(repeat=rep.name, group=p['group'], case_id=p['case_id'],
                        probe_src=p['flows'][0][0], probe_dst=p['flows'][0][1], probe_bytes=p['probe_bytes'],
                        bg_src=s, bg_dst=d, bg_src_block=block(s), bg_dst_block=block(d),
                        sent=int(pe[s]['sent']), source_cycles=int(pe[s]['send_cycles']),
                        source_B_per_cycle=p['bytes']*int(pe[s]['sent'])/int(pe[s]['send_cycles']),
                        probe_cycles=int(source['cycles']), RTT_cycles=val,
                        bg_duration_over_probe=int(pe[s]['send_cycles'])/int(source['cycles'])))
                for r in raw:
                    if r['record']=='sample':
                        samples.append(dict(repeat=rep.name, group=p['group'], role=p['role'],
                                            case_id=p['case_id'], batch=int(r['pe']), RTT_cycles=float(r['value'])))
        for g, items in groups.items():
            cp = [v for p,v,x in items if p['role']=='control']
            tp = [v for p,v,x in items if p['role']=='treatment']
            assert len(cp)==len(tp)==2
            c,t = st.median(cp), st.median(tp)
            p = variants[g]['treatment']
            e = dict(repeat=rep.name, group=g, family=p['family'], label=p['label'], bytes=p['bytes'],
                     probe_bytes=p['probe_bytes'], reply_bytes=p['reply_bytes'], window=p['window'],
                     control=c, treatment=t, ratio=t/c, effect_pct=(t/c-1)*100,
                     difference=t-c, control_range_pct=(max(cp)-min(cp))/c*100,
                     treatment_range_pct=(max(tp)-min(tp))/t*100)
            solos = {}
            for q,v,x in items:
                if q['role'].startswith('solo_'): solos.setdefault(tuple(q['flows'][0]),[]).append(v)
            if not p['mode']:
                for role, val in [('control',c),('treatment',t)]:
                    denominator = sum(st.median(solos[tuple(f)]) for f in variants[g][role]['flows'])
                    e[role+'_efficiency'] = val/denominator
                e['efficiency_ratio'] = e['treatment_efficiency']/e['control_efficiency']
            old = supplied.loc[(rep.name,g)]
            for k,new in [('control',c),('treatment',t),('treatment_over_control',t/c),('difference',t-c)]:
                assert math.isclose(float(old[k]),new,rel_tol=1e-10,abs_tol=1e-7)
            if g in features:
                e.update({k: (int(v) if k not in ('group','category') else v) for k,v in features[g].items()})
            effects.append(e)
    df = pd.DataFrame(effects)
    cf = pd.DataFrame(cases)
    bg = pd.DataFrame(background)
    sf = pd.DataFrame(samples)
    summaries = []
    for g,f in df.groupby('group',sort=True):
        p = variants[g]['treatment']
        row = dict(group=g,family=p['family'],label=p['label'],bytes=p['bytes'],probe_bytes=p['probe_bytes'],
                   reply_bytes=p['reply_bytes'],window=p['window'],
                   control_flows='; '.join(f'{s}->{d}' for s,d in variants[g]['control']['flows']),
                   treatment_flows='; '.join(f'{s}->{d}' for s,d in p['flows']),
                   control_median=f.control.median(), treatment_median=f.treatment.median(),
                   ratio_median=f.ratio.median(), ratio_min=f.ratio.min(),ratio_max=f.ratio.max(),
                   effect_pct=f.effect_pct.median(),effect_min=f.effect_pct.min(),effect_max=f.effect_pct.max(),
                   difference_median=f.difference.median(), drift_max=f.control_range_pct.max(),
                   larger_jobs=int((f.ratio>1).sum()),effect_gt_drift_jobs=int((f.effect_pct.abs()>f.control_range_pct).sum()))
        if p['family'] in ('ports','directions'):
            row.update(control_efficiency=f.control_efficiency.median(), treatment_efficiency=f.treatment_efficiency.median(),
                       efficiency_ratio=f.efficiency_ratio.median(),eff_ratio_min=f.efficiency_ratio.min(),eff_ratio_max=f.efficiency_ratio.max())
        if p['family']=='routes':
            feat = features[g]
            row.update({k:(int(v) if k not in ('group','category') else v) for k,v in feat.items()})
            b = bg[bg.group==g]
            row.update(bg_B_per_cycle=b.source_B_per_cycle.median(), bg_B_min=b.source_B_per_cycle.min(),
                       bg_B_max=b.source_B_per_cycle.max(),bg_count_median=b.sent.median(),
                       bg_count_min=int(b.sent.min()),bg_count_max=int(b.sent.max()),bg_duration_min=b.bg_duration_over_probe.min())
        summaries.append(row)
    summary = pd.DataFrame(summaries)
    route = summary[summary.family=='routes'].copy()
    route['layout'] = [f'{int(r.probe_src)}_{int(r.probe_dst)}_{int(r.background_src)}_{int(r.background_dst)}' for r in route.itertuples()]
    route['size1024'] = (route.probe_bytes==1024).astype(int)
    route['XY_any'] = route[[c for c in route if c.startswith('XY_') and 'direction' in c]].sum(axis=1).clip(upper=1)
    route['YX_any'] = route[[c for c in route if c.startswith('YX_') and 'direction' in c]].sum(axis=1).clip(upper=1)
    models=[]
    specs=[('常数＋消息大小',[]),('XY 去程同向边',['XY_forward_same_direction']),
           ('YX 去程同向边',['YX_forward_same_direction']),('XY 任一无向边',['XY_any']),
           ('YX 任一无向边',['YX_any']),('XY＋YX 去程同向边',['XY_forward_same_direction','YX_forward_same_direction'])]
    y = route.effect_pct.to_numpy()
    for name,cols in specs:
        x=np.column_stack([np.ones(len(route)),route.size1024,*[route[c] for c in cols]])
        rank=np.linalg.matrix_rank(x)
        coef=np.linalg.lstsq(x,y,rcond=None)[0]
        pred=x@coef
        lo,dirpred=np.empty_like(y),np.empty_like(y)
        for v in route.layout.unique():
            mask=(route.layout==v).to_numpy()
            lo[mask]=x[mask]@np.linalg.lstsq(x[~mask],y[~mask],rcond=None)[0]
        for v in route.probe_src.unique():
            mask=(route.probe_src==v).to_numpy()
            dirpred[mask]=x[mask]@np.linalg.lstsq(x[~mask],y[~mask],rcond=None)[0]
        models.append(dict(model=name,parameters=x.shape[1],rank=int(rank),
                           fit_RMSE_pct_points=float(np.sqrt(np.mean((pred-y)**2))),
                           leave_layout_out_RMSE_pct_points=float(np.sqrt(np.mean((lo-y)**2))),
                           leave_probe_direction_out_RMSE_pct_points=float(np.sqrt(np.mean((dirpred-y)**2)))))
    fullcols=[c for c in route if (c.startswith('XY_') or c.startswith('YX_')) and c not in ('XY_any','YX_any')]
    fullx=np.column_stack([np.ones(len(route)),route.size1024,*[route[c] for c in fullcols]])
    diagnostics=dict(route_groups=len(route),route_layouts=route.layout.nunique(), probe_directions=2,
                     full_feature_columns=fullcols,full_parameters=fullx.shape[1],full_rank=int(np.linalg.matrix_rank(fullx)),
                     duplicate_feature_pairs=[(a,b) for i,a in enumerate(fullcols) for b in fullcols[i+1:] if np.array_equal(route[a],route[b])])
    diagnostics['offline_design_checks'] = []
    for name, probes, adjacent in [
        ('两个方向，全部相邻背景', [(0,15),(15,0)], True),
        ('四个方向，全部相邻背景', [(0,15),(3,12),(12,3),(15,0)], True),
        ('两个方向，全部背景核对', [(0,15),(15,0)], False),
    ]:
        candidate = design_matrix(probes, adjacent)
        diagnostics['offline_design_checks'].append(dict(design=name, rows=int(candidate.shape[0]),
                                                        columns=int(candidate.shape[1]), rank=int(np.linalg.matrix_rank(candidate))))
    for name,frame in [('cases',cf.drop(columns=['flows'])),('paired_effects_recomputed',df),('group_summary',summary),
                       ('background_load',bg),('batch_samples',sf),('route_models',pd.DataFrame(models)),('jobs',pd.DataFrame(jobs))]:
        frame.to_csv(TABLES/(name+'.csv'),index=False,encoding='utf-8-sig')
    integrity=dict(raw_files=len(cases),groups=len(summary),effects=len(effects),
                   source_manifest=manifest,source_binary_sha256=sha(SRC/'rma_topology_bench'),
                   all_errors_zero=True, all_wait_stages_zero=True, configurations_match=True,
                   independently_recomputed_effects_match=True, jobs=jobs, family_cases=cf.groupby('family').size().to_dict(),
                   family_groups=summary.groupby('family').size().to_dict(), models=diagnostics,
                   max_baseline_drift_pct=float(df.control_range_pct.max()),
                   background_duration_ratio_min=float(bg.bg_duration_over_probe.min()))
    (OUT/'audit.json').write_text(json.dumps(integrity,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'report_data.json').write_text(json.dumps(dict(summary=summary.fillna('').to_dict('records'),
        effects=df.fillna('').to_dict('records'),jobs=jobs,models=models,diagnostics=diagnostics,
        background=bg.to_dict('records'),samples=sf.to_dict('records'),integrity={k:v for k,v in integrity.items() if k!='source_manifest'}),
        ensure_ascii=False,indent=2),encoding='utf-8')
    print(summary[['group','family','effect_pct','drift_max','larger_jobs','effect_gt_drift_jobs']].to_string(index=False))
    print(pd.DataFrame(models).to_string(index=False))
    print(json.dumps(diagnostics,ensure_ascii=False))
    print('background rates / durations:',bg.source_B_per_cycle.min(),bg.source_B_per_cycle.max(),bg.bg_duration_over_probe.min())


if __name__=='__main__': main()
