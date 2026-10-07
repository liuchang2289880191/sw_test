"""Small stdlib linear algebra helpers for login nodes without NumPy."""
from fractions import Fraction
import math


def exact_rank(rows):
    a=[[Fraction(v) for v in r] for r in rows]
    if not a: return 0
    rank=0
    for col in range(len(a[0])):
        pivot=next((i for i in range(rank,len(a)) if a[i][col]),None)
        if pivot is None: continue
        a[rank],a[pivot]=a[pivot],a[rank]
        div=a[rank][col]
        a[rank]=[v/div for v in a[rank]]
        for i in range(rank+1,len(a)):
            if a[i][col]:
                div=a[i][col]
                a[i]=[v-div*w for v,w in zip(a[i],a[rank])]
        rank+=1
        if rank==len(a): break
    return rank


def scaled_condition(rows):
    """2-norm condition after each column is normalized to unit Euclidean norm."""
    m=len(rows[0]); norms=[math.sqrt(sum(r[j]*r[j] for r in rows)) for j in range(m)]
    if min(norms)==0: return float('inf')
    a=[[sum(r[i]*r[j] for r in rows)/(norms[i]*norms[j]) for j in range(m)] for i in range(m)]
    for _ in range(200*m*m):
        p,q=max(((i,j) for i in range(m) for j in range(i+1,m)),key=lambda ij:abs(a[ij[0]][ij[1]]))
        if abs(a[p][q])<1e-13: break
        app,aqq,apq=a[p][p],a[q][q],a[p][q]
        angle=.5*math.atan2(2*apq,aqq-app)
        c,s=math.cos(angle),math.sin(angle)
        for k in range(m):
            if k not in (p,q):
                kp,kq=a[k][p],a[k][q]
                a[k][p]=a[p][k]=c*kp-s*kq
                a[k][q]=a[q][k]=s*kp+c*kq
        a[p][p]=c*c*app-2*c*s*apq+s*s*aqq
        a[q][q]=s*s*app+2*c*s*apq+c*c*aqq
        a[p][q]=a[q][p]=0
    vals=[a[i][i] for i in range(m)]
    if min(vals)<=1e-12: return float('inf')
    return math.sqrt(max(vals)/min(vals))


def fit(rows, response):
    """Twice-reorthogonalized modified Gram-Schmidt, with rank rejection."""
    n,m=len(rows),len(rows[0]); cols=list(zip(*rows))
    q=[]; rr=[[0.0]*m for _ in range(m)]
    for j in range(m):
        v=[float(x) for x in cols[j]]
        for _ in range(2):
            for i,qi in enumerate(q):
                part=sum(a*b for a,b in zip(qi,v)); rr[i][j]+=part
                v=[a-part*b for a,b in zip(v,qi)]
        norm=math.sqrt(sum(a*a for a in v))
        if norm<1e-10: raise ValueError('Rank-deficient training fold; coefficients not identified')
        rr[j][j]=norm; q.append([a/norm for a in v])
    z=[sum(a*b for a,b in zip(qi,response)) for qi in q]
    coef=[0.0]*m
    for j in reversed(range(m)):
        coef[j]=(z[j]-sum(rr[j][k]*coef[k] for k in range(j+1,m)))/rr[j][j]
    return coef


def predict(rows,coef):
    return [sum(a*b for a,b in zip(r,coef)) for r in rows]
