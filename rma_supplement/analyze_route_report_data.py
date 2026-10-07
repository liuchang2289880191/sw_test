"""Independently audit real full-rank route results, keeping every input immutable."""
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

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'results_route_20261007_223701_6654'
OUT=ROOT/'outputs/rma_supplement_report_20261007'
TABLE=OUT/'分析表/路径补充'
sys.path.insert(0,str(ROOT/'rma_route_identify'))
from base_analysis import checked
from generate_plan import features, design_row, MODEL_COLUMNS, FEATURE_NAMES, audit_design


def read(path):
    with path.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def cv(x,y,keys):
    pred=np.zeros(len(y)); ranks=[]
    for k in sorted(set(keys)):
        test=np.array([v==k for v in keys]); train=~test
        rank=int(np.linalg.matrix_rank(x[train]));ranks.append(rank)
        assert rank==x.shape[1]
        coef=np.linalg.lstsq(x[train],y[train],rcond=None)[0]
        pred[test]=x[test]@coef
    return float(np.sqrt(np.mean((pred-y)**2))),pred,ranks


def main():
    TABLE.mkdir(parents=True,exist_ok=True)
    manifest=[dict(file=p.relative_to(SRC).as_posix(),sha256=sha(p)) for p in sorted(SRC.rglob('*')) if p.is_file()]
    assert (SRC/'COMPLETE').read_text().strip()=='completed_jobs=5\ndiagnostic_only=0'
    oldsrc=ROOT/'outputs/results_20261007_211507_31272/source'
    kernel=[dict(file=n,sha256=sha(SRC/'source'/n),unchanged_from_quick=sha(SRC/'source'/n)==sha(oldsrc/n))
            for n in ('topology_host.c','topology_slave.c','topology_common.h')]
    assert all(k['unchanged_from_quick'] for k in kernel)
    supplied=pd.read_csv(SRC/'analysis/paired_effects.csv').set_index(['repeat','group'])
    cases=[];effects=[];background=[];samples=[];jobs=[];canonical=None;routes=None
    for rep in sorted(SRC.glob('repeat_*')):
        plan=json.loads((rep/'plan.json').read_text()); assert len(plan)==256
        assert (rep/'RUN_COMPLETE').read_text().strip()=='completed_cases=256'
        assert {p.name for p in (rep/'raw').glob('*.csv')}=={p['case_id']+'.csv' for p in plan}
        sig=sorted(json.dumps({k:v for k,v in p.items() if k!='case_id'},sort_keys=True) for p in plan)
        if canonical is None:canonical=sig
        else:assert sig==canonical
        rr=read(rep/'route_features.csv')
        numeric=['probe_src','probe_dst','background_src','background_dst','probe_bytes','reply_bytes',
                 'background_bytes','window','background_src_block','background_dst_block',*FEATURE_NAMES]
        for r in rr:
            for k in numeric:r[k]=int(r[k])
            assert features((r['probe_src'],r['probe_dst']),(r['background_src'],r['background_dst']))=={k:r[k] for k in FEATURE_NAMES}
        audit=audit_design(rr)
        if routes is None:routes=rr
        else:assert routes==rr
        rt={r['group']:r for r in rr}
        resource=dict(line.split('=',1) for line in (rep/'resource_runtime.txt').read_text().splitlines() if '=' in line)
        log=(rep/'job.log').read_text()
        assert not re.search('TOPO_TIMEOUT|TOPO_CASE_TIMEOUT|FAILED|ERROR',log)
        job=re.search(r'Job <(\d+)>',log).group(1);assert f'Job {job} has been finished.' in log
        info=json.loads((rep/'plan_info.json').read_text());assert info['catalogue_sha256']==sha(SRC/'source/layouts.json')
        jobs.append(dict(repeat=rep.name,job=job,node=resource['hostname'],seed=info['seed'],cases=len(plan)))
        grouped={}
        for p in plan:
            assert p['reps']==2048 and p['mode']==1 and p['window']==4 and p['reply_bytes']==8 and p['bytes']==4096
            value,item=checked(rep,p);raw=read(rep/'raw'/(p['case_id']+'.csv'))
            assert all(int(x['wait_stage'])==0 for x in raw)
            pe={int(x['pe']):x for x in raw if x['record']=='pe'}
            r=rt[p['group']];assert p['flows'][0]==[r['probe_src'],r['probe_dst']] and p['probe_bytes']==r['probe_bytes']
            assert p['flows']==([p['flows'][0],[r['background_src'],r['background_dst']]] if p['role']=='treatment' else [p['flows'][0]])
            cases.append(dict(repeat=rep.name,group=p['group'],role=p['role'],value=value,**item))
            grouped.setdefault(p['group'],[]).append((p,value))
            if p['role']=='treatment':
                s,d=p['flows'][1];source=pe[s];assert int(source['sent'])==int(pe[d]['received'])
                background.append(dict(repeat=rep.name,group=p['group'],case_id=p['case_id'],bg_src=s,bg_dst=d,
                    sent=int(source['sent']),source_cycles=int(source['send_cycles']),
                    B_per_cycle=p['bytes']*int(source['sent'])/int(source['send_cycles']),
                    source_duration_over_probe=int(source['send_cycles'])/int(pe[r['probe_src']]['cycles'])))
            samples.extend(dict(repeat=rep.name,group=p['group'],role=p['role'],case_id=p['case_id'],
                                batch=int(x['pe']),RTT_cycles=float(x['value'])) for x in raw if x['record']=='sample')
        for g,items in grouped.items():
            c=[v for p,v in items if p['role']=='control'];t=[v for p,v in items if p['role']=='treatment']
            assert len(c)==len(t)==2
            cm,tm=st.median(c),st.median(t)
            e=dict(repeat=rep.name,group=g,control=cm,treatment=tm,treatment_over_control=tm/cm,
                   difference=tm-cm,control_range_pct=(max(c)-min(c))/cm*100,
                   treatment_range_pct=(max(t)-min(t))/tm*100,effect_pct=(tm/cm-1)*100)
            for k in ('control','treatment','treatment_over_control','difference','control_range_pct','treatment_range_pct'):
                assert math.isclose(e[k],float(supplied.loc[(rep.name,g),k]),rel_tol=1e-10,abs_tol=1e-9)
            effects.append(e)
    assert len(cases)==1280 and len(effects)==320 and len(background)==640 and len(samples)==40960
    summary=[]
    for r in routes:
        es=[e for e in effects if e['group']==r['group']];bg=[b for b in background if b['group']==r['group']]
        vals=[e['effect_pct'] for e in es]
        summary.append(dict(**r,jobs=len(es),control_RTT_median=st.median(e['control'] for e in es),
            treatment_RTT_median=st.median(e['treatment'] for e in es),effect_pct_median=st.median(vals),
            effect_pct_min=min(vals),effect_pct_max=max(vals),max_control_drift_pct=max(e['control_range_pct'] for e in es),
            larger_jobs=sum(v>0 for v in vals),effect_gt_drift_jobs=sum(abs(e['effect_pct'])>e['control_range_pct'] for e in es),
            difference_median=st.median(e['difference'] for e in es),
            bg_B_per_cycle_median=st.median(b['B_per_cycle'] for b in bg),
            bg_B_per_cycle_min=min(b['B_per_cycle'] for b in bg),bg_B_per_cycle_max=max(b['B_per_cycle'] for b in bg)))
    df=pd.DataFrame(summary); provided=pd.read_csv(SRC/'analysis/route_summary.csv').set_index('group')
    for r in summary:
        for k in ('control_RTT_median','treatment_RTT_median','effect_pct_median','effect_pct_min','effect_pct_max',
                  'max_control_drift_pct','larger_jobs','bg_B_per_cycle_median','bg_B_per_cycle_min','bg_B_per_cycle_max'):
            assert math.isclose(r[k],provided.loc[r['group'],k],rel_tol=1e-10,abs_tol=1e-9)
    x=np.array([design_row(r) for r in summary]);y=df.effect_pct_median.to_numpy()
    layoutkeys=[(r['background_src'],r['background_dst']) for r in summary];directionkeys=[r['probe_src'] for r in summary]
    models=[];coeffs=[];predictions=[];jobcoeffs=[]
    suppliedmodels=pd.read_csv(SRC/'analysis/candidate_models.csv').set_index('model')
    suppliedcoef=pd.read_csv(SRC/'analysis/candidate_coefficients.csv').set_index(['model','feature'])
    specs=[('constant_size',[0,1]),('XY',[0,1,*range(2,8)]),('YX',[0,1,*range(8,14)]),('combined_descriptive',list(range(14)))]
    denom=float(np.sum((y-y.mean())**2))
    for name,idx in specs:
        xx=x[:,idx];coef=np.linalg.lstsq(xx,y,rcond=None)[0];pred=xx@coef
        rmse,cvpred,ranks=cv(xx,y,layoutkeys);drmse,dpred,dranks=cv(xx,y,directionkeys)
        condition=float(np.linalg.cond(xx/np.linalg.norm(xx,axis=0)))
        m=dict(model=name,columns=len(idx),rank=int(np.linalg.matrix_rank(xx)),unit_column_norm_condition=condition,
               fit_RMSE_pct_points=float(np.sqrt(np.mean((pred-y)**2))),
               background_layout_RMSE_pct_points=rmse,probe_direction_RMSE_pct_points=drmse,
               layout_folds=len(ranks),minimum_layout_train_rank=min(ranks),minimum_direction_train_rank=min(dranks),
               R2=1-float(np.sum((pred-y)**2))/denom)
        for k in ('fit_RMSE_pct_points','background_layout_RMSE_pct_points','probe_direction_RMSE_pct_points','unit_column_norm_condition'):
            assert math.isclose(m[k],float(suppliedmodels.loc[name,k]),rel_tol=1e-9,abs_tol=1e-8)
        for feature,c in zip([MODEL_COLUMNS[i] for i in idx],coef):
            assert math.isclose(c,float(suppliedcoef.loc[(name,feature),'coefficient_pct_points']),rel_tol=1e-9,abs_tol=1e-8)
            coeffs.append(dict(model=name,feature=feature,coefficient_pct_points=float(c)))
        for r,a,b,c in zip(summary,pred,cvpred,dpred):
            predictions.append(dict(group=r['group'],model=name,observed=r['effect_pct_median'],fitted=float(a),
                held_layout=float(b),held_direction=float(c)))
        models.append(m)
    for job in jobs:
        yy=np.array([next(e['effect_pct'] for e in effects if e['repeat']==job['repeat'] and e['group']==r['group']) for r in summary])
        c=np.linalg.lstsq(x,yy,rcond=None)[0]
        jobcoeffs.extend(dict(repeat=job['repeat'],feature=f,coefficient_pct_points=float(v)) for f,v in zip(MODEL_COLUMNS,c))
    alias=[]
    for key,items in df.groupby(['probe_src','probe_bytes',*FEATURE_NAMES],sort=False):
        if len(items)>1:
            lo=items.loc[items.effect_pct_median.idxmin()];hi=items.loc[items.effect_pct_median.idxmax()]
            alias.append(dict(groups=items.group.tolist(),probe_src=int(lo.probe_src),probe_bytes=int(lo.probe_bytes),
                low_group=lo.group,high_group=hi.group,low_effect=float(lo.effect_pct_median),
                high_effect=float(hi.effect_pct_median),spread=float(hi.effect_pct_median-lo.effect_pct_median)))
    alias.sort(key=lambda a:a['spread'],reverse=True)
    old=pd.read_csv(OUT/'分析表/group_summary.csv');old=old[old.family=='routes'];anchors=[]
    for r in summary:
        if r['category']!='anchor':continue
        match=old[(old.probe_src==r['probe_src'])&(old.probe_bytes==r['probe_bytes'])&
                  (old.background_src==r['background_src'])&(old.background_dst==r['background_dst'])]
        assert len(match)==1;oldr=match.iloc[0]
        anchors.append(dict(new_group=r['group'],old_group=oldr.group,probe_src=r['probe_src'],probe_bytes=r['probe_bytes'],
                            background_src_block=r['background_src_block'],background_dst_block=r['background_dst_block'],
                            old_effect_pct=float(oldr.effect_pct),new_effect_pct=r['effect_pct_median'],
                            change_pct_points=r['effect_pct_median']-float(oldr.effect_pct)))
    integrity=dict(raw_files=len(cases),groups=64,effects=len(effects),background_records=len(background),
        batch_records=len(samples),all_errors_wait_stages_zero=True,matched_results_agree=True,
        configurations_match=True,kernel_provenance=kernel,source_manifest=manifest,
        source_binary_sha256=sha(SRC/'rma_topology_bench'),jobs=jobs,design_audit=audit,
        maximum_baseline_drift_pct=max(e['control_range_pct'] for e in effects),
        minimum_background_duration_ratio=min(b['source_duration_over_probe'] for b in background),
        nodes=sorted({j['node'] for j in jobs}),model_checks_agree=True,
        groups_positive_all_jobs=sum(r['larger_jobs']==5 for r in summary),
        groups_effect_exceeds_control_drift_all_jobs=sum(r['effect_gt_drift_jobs']==5 for r in summary),
        positive_coefficients=sum(c['coefficient_pct_points']>0 for c in coeffs if c['model']=='combined_descriptive'),
        negative_coefficients=sum(c['coefficient_pct_points']<0 for c in coeffs if c['model']=='combined_descriptive'))
    for n,v in [('summary',summary),('effects',effects),('cases',cases),('background',background),('samples',samples),
                ('models',models),('coefficients',coeffs),('job_coefficients',jobcoeffs),('predictions',predictions),('anchors',anchors),('jobs',jobs)]:
        pd.DataFrame(v).to_csv(TABLE/(n+'.csv'),encoding='utf-8-sig',index=False)
    (OUT/'route_audit.json').write_text(json.dumps(integrity,ensure_ascii=False,indent=2),encoding='utf-8')
    (OUT/'route_report_data.json').write_text(json.dumps(dict(summary=summary,effects=effects,models=models,coefficients=coeffs,
        job_coefficients=jobcoeffs,aliases=alias,anchors=anchors,jobs=jobs,
        integrity={k:v for k,v in integrity.items() if k!='source_manifest'}),ensure_ascii=False,indent=2),encoding='utf-8')
    print(pd.DataFrame(models).to_string(index=False))
    print('Alias examples:',json.dumps(alias[:5],ensure_ascii=False))
    print('Effect range:',df.effect_pct_median.min(),df.effect_pct_median.max(),'; baseline drift:',integrity['maximum_baseline_drift_pct'])
    print('Jobs:',json.dumps(jobs));print('Anchors maximum change (pp):',max(abs(a['change_pct_points']) for a in anchors))
    print('Strongest diagonal:',df[df.category=='diagonal_background'].nlargest(4,'effect_pct_median')[
        ['group','probe_src','probe_bytes','background_src_block','background_dst_block','effect_pct_median','effect_pct_min','effect_pct_max']].to_string(index=False))


if __name__=='__main__':main()
