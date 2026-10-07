"""Strict within-job comparisons plus identifiable candidate model diagnostics.

Stdlib only. Full-rank coefficients are descriptive, not physical route proof.
"""
import argparse
import csv
import json
import math
from pathlib import Path
import statistics as st
from base_analysis import analyze as analyze_base, rows, csv_write
from generate_plan import audit_design, design_row, MODEL_COLUMNS, FEATURE_NAMES
from design_math import exact_rank, scaled_condition, fit, predict


def analyze(root):
    effects=analyze_base(root)
    out=root/'analysis';route_rows=None;background=[];batches=[]
    for rep in sorted(root.glob('repeat_*')):
        rr=rows(rep/'route_features.csv')
        for r in rr:
            for k in ['probe_src','probe_dst','background_src','background_dst','probe_bytes','reply_bytes','background_bytes','window',*FEATURE_NAMES]:
                r[k]=int(r[k])
        audit=audit_design(rr)
        if route_rows is None: route_rows=rr
        elif route_rows!=rr: raise ValueError('Route features differ between jobs')
        plan=json.loads((rep/'plan.json').read_text(encoding='utf-8'))
        for p in plan:
            raw=rows(rep/'raw'/(p['case_id']+'.csv'))
            if any(int(r['wait_stage']) for r in raw):raise ValueError('Unexpected wait failure stage')
            pe={int(r['pe']):r for r in raw if r['record']=='pe'}
            for r in raw:
                if r['record']=='sample':
                    batches.append(dict(repeat=rep.name,group=p['group'],role=p['role'],case_id=p['case_id'],
                                        batch=int(r['pe']),RTT_cycles=float(r['value'])))
            if p['role']=='treatment':
                s,d=p['flows'][1];probe=p['flows'][0][0]
                if int(pe[s]['sent'])!=int(pe[d]['received']):raise ValueError('Background pair count mismatch')
                background.append(dict(repeat=rep.name,group=p['group'],case_id=p['case_id'],bg_src=s,bg_dst=d,
                    sent=int(pe[s]['sent']),source_cycles=int(pe[s]['send_cycles']),
                    B_per_cycle=p['bytes']*int(pe[s]['sent'])/int(pe[s]['send_cycles']),
                    source_duration_over_probe=int(pe[s]['send_cycles'])/int(pe[probe]['cycles'])))
    grouped={}
    for e in effects: grouped.setdefault(e['group'],[]).append(e)
    summary=[]
    for r in route_rows:
        es=grouped[r['group']];changes=[(e['treatment_over_control']-1)*100 for e in es]
        bg=[b for b in background if b['group']==r['group']]
        summary.append(dict(**r,jobs=len(es),control_RTT_median=st.median(e['control'] for e in es),
            treatment_RTT_median=st.median(e['treatment'] for e in es),
            effect_pct_median=st.median(changes),effect_pct_min=min(changes),effect_pct_max=max(changes),
            max_control_drift_pct=max(e['control_range_pct'] for e in es),
            larger_jobs=sum(v>0 for v in changes),
            bg_B_per_cycle_median=st.median(b['B_per_cycle'] for b in bg),
            bg_B_per_cycle_min=min(b['B_per_cycle'] for b in bg),bg_B_per_cycle_max=max(b['B_per_cycle'] for b in bg)))
    csv_write(out/'route_summary.csv',summary);csv_write(out/'background_load.csv',background)
    csv_write(out/'batch_samples.csv',batches)
    full=[design_row(r) for r in summary];y=[r['effect_pct_median'] for r in summary]
    models=[];coefficients=[];predictions=[dict(group=r['group'],observed_effect_pct=v) for r,v in zip(summary,y)]
    specs=[('constant_size',[0,1]),('XY',[0,1,*range(2,8)]),('YX',[0,1,*range(8,14)]),('combined_descriptive',list(range(14)))]
    for name,indices in specs:
        x=[[r[k] for k in indices] for r in full];rank=exact_rank(x)
        if rank!=len(indices): raise ValueError('Model columns not identified')
        coef=fit(x,y);pred=predict(x,coef)
        for j,c in enumerate(coef):coefficients.append(dict(model=name,feature=MODEL_COLUMNS[indices[j]],coefficient_pct_points=c,
            interpretation='descriptive_only_not_physical_cost'))
        for p,v in zip(predictions,pred):p[name+'_predicted_effect_pct']=v
        metrics=dict(model=name,columns=len(indices),rank=rank,unit_column_norm_condition=scaled_condition(x),
                     fit_RMSE_pct_points=math.sqrt(st.mean((a-b)**2 for a,b in zip(pred,y))))
        for kind in ('background_layout','probe_direction'):
            keys=[(r['background_src'],r['background_dst']) if kind=='background_layout' else r['probe_src'] for r in summary]
            cvpred=[None]*len(y);rejected=[]
            for key in sorted(set(keys)):
                test=[i for i,k in enumerate(keys) if k==key];train=[i for i,k in enumerate(keys) if k!=key]
                tx=[x[i] for i in train]
                if exact_rank(tx)!=len(indices):
                    rejected.append(str(key));continue
                tc=fit(tx,[y[i] for i in train])
                for i,v in zip(test,predict([x[i] for i in test],tc)): cvpred[i]=v
            metrics[kind+'_rejected_folds']=len(rejected)
            metrics[kind+'_RMSE_pct_points']='' if rejected else math.sqrt(st.mean((a-b)**2 for a,b in zip(cvpred,y)))
            metrics[kind+'_rejection_reason']='rank_deficient_training' if rejected else ''
        models.append(metrics)
    csv_write(out/'candidate_models.csv',models);csv_write(out/'candidate_coefficients.csv',coefficients)
    csv_write(out/'candidate_predictions.csv',predictions)
    (out/'design_audit.json').write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
    (out/'MODEL_READ_ME.txt').write_text(
        'The geometry matrix is full rank; this does not establish actual routing.\n'
        'Coefficients describe paired protocol RTT increase, in percentage points.\n'
        'Compare XY/YX held-out errors and reject unsupported models; neither is assumed true.\n'
        'Combined model is a descriptive diagnostic, not evidence both routes coexist.\n'
        'Grouped CV holds both sizes and both probes for the same directed background pair together.\n'
        'Rank-deficient training folds are rejected instead of silently using a pseudoinverse.\n'
        'Background rate is observed and affected by contention; it is not a controlled independent load.\n'
        'No cycle-frequency calibration, per-message tail latency, cross-node generalization, or overhead subtraction.\n',encoding='utf-8')
    print('Full rank verified in actual plans; candidate diagnostics: '+str(out/'candidate_models.csv'))
    return summary,models


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('results',type=Path);a=ap.parse_args();analyze(a.results)
