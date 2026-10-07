"""Independent route-identifiability plan. Standard library only on HPC login.

Kernel protocol is byte-identical to the successful 2026-10-07 supplement.
All paths below are geometric hypotheses, not observed physical links.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import random
from design_math import exact_rank, scaled_condition

HERE=Path(__file__).resolve().parent
CAPACITY=32768
FEATURE_NAMES=[f'{order}_{phase}_{kind}' for order in ('XY','YX')
               for phase in ('forward','reply')
               for kind in ('same_direction','opposite_direction','shared_internal_nodes')]
MODEL_COLUMNS=['constant','size1024']+FEATURE_NAMES


def member(b):
    return (b//4*2)*8+b%4*2


def block(pe):
    return pe//16*4+pe%8//2


def path(s,d,order):
    r,c=divmod(s,4);rd,cd=divmod(d,4);out=[s]
    for axis in order:
        if axis=='X':
            while c!=cd:
                c+=1 if cd>c else -1;out.append(4*r+c)
        else:
            while r!=rd:
                r+=1 if rd>r else -1;out.append(4*r+c)
    return out


def features(probe,bg):
    ps,pd=map(block,probe);bs,bd=map(block,bg);out={}
    for order in ('XY','YX'):
        bp=path(bs,bd,order);be=set(zip(bp,bp[1:]))
        for phase,ends in [('forward',(ps,pd)),('reply',(pd,ps))]:
            pp=path(*ends,order);pe=set(zip(pp,pp[1:]))
            out[f'{order}_{phase}_same_direction']=len(pe&be)
            out[f'{order}_{phase}_opposite_direction']=len(pe&{(b,a) for a,b in be})
            out[f'{order}_{phase}_shared_internal_nodes']=len((set(pp)-{ps,pd})&set(bp))
    return out


def design_row(r):
    return [1,int(r['probe_bytes']==1024)]+[int(r[c]) for c in FEATURE_NAMES]


def audit_design(routes):
    checks=[]
    for label,selected in [('all',routes)]+[(f'probe_{s}',[r for r in routes if r['probe_src']==s]) for s in (0,54)]:
        x=[design_row(r) for r in selected]
        rank=exact_rank(x);cond=scaled_condition(x)
        if rank!=14 or not cond<100:
            raise ValueError(f'Design rejected: {label}, rank={rank}/14, scaled condition={cond}')
        checks.append(dict(scope=label,rows=len(x),columns=14,exact_rank=rank,
                           unit_column_norm_condition=cond))
    return dict(model_columns=MODEL_COLUMNS,checks=checks,
                routes_are_hypotheses=True,full_rank_does_not_prove_routing=True,
                selection_uses_measured_effects=False)


def build(reps,seed):
    catalogue=json.loads((HERE/'layouts.json').read_text(encoding='utf-8'))
    groups=[];routes=[]
    for li,layout in enumerate(catalogue['layouts']):
        ps,pd=layout['probe_blocks'];bs,bd=layout['background_blocks']
        assert ps!=pd and bs!=bd and not {ps,pd}&{bs,bd}
        if not layout['anchor']:
            assert bs//4!=bd//4 and bs%4!=bd%4
        probe=(member(ps),member(pd));bg=(member(bs),member(bd))
        feat=features(probe,bg)
        for pb in (8,1024):
            gid=f'g{len(groups):04}'
            label=f'p{ps}_{pd}_bg{bs}_{bd}_pb{pb}'
            groups.append(dict(group=gid,label=label,probe=probe,bg=bg,probe_bytes=pb))
            routes.append(dict(group=gid,probe_src=probe[0],probe_dst=probe[1],
                background_src=bg[0],background_dst=bg[1],probe_bytes=pb,reply_bytes=8,
                background_bytes=4096,window=4,category='anchor' if layout['anchor'] else 'diagonal_background',
                layout_id=f'L{li:02}',background_src_block=bs,background_dst_block=bd,
                XY_background_path='_'.join(map(str,path(bs,bd,'XY'))),
                YX_background_path='_'.join(map(str,path(bs,bd,'YX'))),**feat))
    audit=audit_design(routes)
    rng=random.Random(seed);rng.shuffle(groups);plan=[]
    for g in groups:
        order=[0,1,1,0] if rng.randrange(2) else [1,0,0,1]
        for treatment in order:
            role='treatment' if treatment else 'control'
            plan.append(dict(case_id=f'{g["group"]}_{role}_{len(plan):05}',group=g['group'],family='routes',
                label=g['label'],role=role,mode=1,bytes=4096,probe_bytes=g['probe_bytes'],reply_bytes=8,
                reps=reps,window=4,flows=[g['probe'],g['bg']] if treatment else [g['probe']]))
    return plan,routes,audit


def write_plan(out,reps=2048,seed=20261008,diagnostic=False):
    if not 64<=reps<=16384 or reps%64:raise ValueError('reps must be a multiple of 64 in 64..16384')
    plan,routes,audit=build(reps,seed)
    if diagnostic:
        # Both probe orientations, a new diagonal path and a longer reverse path.
        specs=[(0,54,2,20,8),(0,54,22,2,1024),(54,0,2,20,8),(54,0,20,2,1024)]
        plan=[dict(case_id=f'diag_{i:02}',group=f'diag_{i:02}',family='diagnostic',label='route_diag',
                   role='diagnostic',mode=1,bytes=4096,probe_bytes=pb,reply_bytes=8,reps=64,window=4,
                   flows=[(ps,pd),(bs,bd)]) for i,(ps,pd,bs,bd,pb) in enumerate(specs)]
        routes=[]
    out.mkdir(parents=True,exist_ok=True)
    with (out/'plan.txt').open('w',encoding='ascii',newline='\n') as f:
        f.write('# case group family label role mode background_bytes probe_bytes reply_bytes reps window nflows src dst ...\n')
        for p in plan:
            values=[p[k] for k in ('case_id','group','family','label','role','mode','bytes','probe_bytes','reply_bytes','reps','window')]
            values+=[len(p['flows'])]+[i for pair in p['flows'] for i in pair]
            f.write(' '.join(map(str,values))+'\n')
    (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n',encoding='utf-8')
    with (out/'route_features.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(routes[0]) if routes else ['group']);w.writeheader();w.writerows(routes)
    (out/'design_audit.json').write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
    (out/'plan_info.json').write_text(json.dumps(dict(profile='route_identify',seed=seed,reps=reps,
        cases=len(plan),groups=len({p['group'] for p in plan}),diagnostic=diagnostic,
        catalogue_sha256=hashlib.sha256((HERE/'layouts.json').read_bytes()).hexdigest(),buffer_bytes=CAPACITY,
        geometries_fixed_across_jobs=True,only_order_changes_with_seed=True),indent=2)+'\n',encoding='utf-8')
    return plan,routes,audit


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--reps',type=int,default=2048);ap.add_argument('--seed',type=int,default=20261008)
    ap.add_argument('--diagnostic',action='store_true')
    args=ap.parse_args();p,rt,a=write_plan(args.out,args.reps,args.seed,args.diagnostic)
    print(f'Generated {len(p)} cases / {len({r["group"] for r in p})} matched groups; no hardware execution.')
    print('Geometry audit: '+json.dumps(a['checks']))
