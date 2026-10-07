"""Offline NumPy selection; the deployed generator itself needs only stdlib.

Keep six previous anchor layouts in each probe direction, then select ten
diagonal backgrounds by geometry information; no measured effect is used.
"""
from pathlib import Path
import json
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
from generate_plan import features,member


def main():
    records=[]; checks=[]
    anchor_sets={(0,15):[(1,2),(2,3),(4,8),(8,12),(1,5),(2,1)],
                 (15,0):[(8,4),(12,8),(2,1),(3,2),(1,2),(1,5)]}
    for probe,anchors in anchor_sets.items():
        candidates=[(s,d) for s in range(16) for d in range(16)
                    if s!=d and not {s,d}&set(probe) and s//4!=d//4 and s%4!=d%4]
        def vector(bg):
            return np.array([1,*features(tuple(map(member,probe)),tuple(map(member,bg))).values()],dtype=float)
        scales=np.linalg.norm(np.stack([vector(bg) for bg in candidates+anchors]),axis=0)
        def score(layouts):
            x=np.stack([vector(bg)/scales for bg in layouts])
            sv=np.linalg.svd(x,compute_uv=False); keep=sv[sv>1e-11]
            return len(keep)*1000+2*np.log(keep).sum()
        chosen=list(anchors)
        while len(chosen)<16:
            best=max((bg for bg in candidates if bg not in chosen),key=lambda bg:score(chosen+[bg]))
            chosen.append(best)
        def condition_score(layouts):
            rows=[]
            for bg in layouts:
                v=vector(bg)
                for large in (0,1): rows.append(np.r_[1,large,v[1:]])
            x=np.stack(rows)
            if np.linalg.matrix_rank(x)!=14: return -1e6
            x=x/np.linalg.norm(x,axis=0)
            return -np.linalg.cond(x)
        # Deterministic exchange to reduce the unit-column-norm condition.
        # Anchors remain fixed. This uses geometry alone, never measured effects.
        for _ in range(12):
            improved=False
            for slot in range(len(anchors),len(chosen)):
                current=condition_score(chosen)
                best=max((bg for bg in candidates if bg not in chosen or bg==chosen[slot]),
                         key=lambda bg:condition_score(chosen[:slot]+[bg]+chosen[slot+1:]))
                proposal=chosen[:slot]+[best]+chosen[slot+1:]
                if condition_score(proposal)>current+1e-9:
                    chosen=proposal; improved=True
            if not improved: break
        x=np.stack([vector(bg) for bg in chosen])
        assert np.linalg.matrix_rank(x)==13
        checks.append(dict(probe_blocks=list(probe),geometry_rank=13,background_layouts=len(chosen)))
        for i,bg in enumerate(chosen):
            records.append(dict(probe_blocks=list(probe),background_blocks=list(bg),
                                anchor=i<len(anchors),selection='previous_anchor' if i<len(anchors) else 'geometry_information'))
    result=dict(layouts=records,checks=checks,selection_uses_measured_effects=False,
                explanation='Six legacy anchors plus ten selected diagonal backgrounds per probe direction; candidate paths only.')
    p=ROOT/'rma_route_identify/layouts.json'
    p.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
