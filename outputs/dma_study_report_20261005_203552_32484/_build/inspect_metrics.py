import csv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
SRC=ROOT/'dma_results_20261005_203552_32484'
ANA=ROOT/'outputs/dma_study_analysis_20261005_203552_32484'
def read(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
D={(r['phase'],r['mode'],int(r['active_pes']),int(r['bytes']),int(r['offset']),int(r['slot_stride']),r['mapping']):r for r in read(SRC/'study_summary.csv')}
def b(m,n,s,o=0,t=131200,k='identity',p='load'):return float(D[p,m,n,s,o,t,k]['aggregate_bytes_per_cycle'])
print('Full64 mapping fixed-stride correlations representative')
for m,s,o,t in [('get',256,0,131200),('get',128,4,131200),('get',131072,0,131200),('put',64,0,131200),('put',131072,0,131200)]:
    rs=[r for r in read(ANA/'pe_slot_correlations.csv') if r['mode']==m and int(r['bytes'])==s and int(r['offset'])==o and int(r['slot_stride'])==t]
    print(m,s,o,t,*[(r['mapping'],round(float(r['corr_by_pe']),4),round(float(r['corr_by_slot']),4)) for r in rs])
print('Full64 layout representative')
for m in ['get','put','iget','iput']:
    for s in [64,128,256,4096,65536,131072]:
        for o in [0,4]:
            values=[b(m,64,s,o,t,k,'mapping') for t in [131200,131328,135168,262144] for k in ['identity','reverse','transpose','shuffle']]
            if m in ['get','put']:print(m,s,o,round(min(values),4),round(max(values),4),round(max(values)/min(values),4))
print('Mapping full64 128KiB aligned by stride and map')
for m in ['get','put']:
    for t in [131200,131328,135168,262144]:print(m,t,*[round(b(m,64,131072,0,t,k,'mapping'),5) for k in ['identity','reverse','transpose','shuffle']])
print('Peaks by size aligned')
for r in read(ANA/'load_peaks.csv'):
    if r['mode'] in ['get','put'] and int(r['bytes']) in [8,64,128,4096,32768,65536,98304,131072] and r['offset']=='0':print(r)
print('Small single cycles')
for m in ['get','put','iget','iput']:
    print(m,[(s,float(D['load',m,1,s,0,131200,'identity']['cycles_per_op'])) for s in [8,16,32,64,128,256]])
print('Boundary 128/256 offset penalties at N1/64')
for m in ['get','put','iget','iput']:
    for n in [1,64]:
        for s in [128,256]:
            cy=[float(D['boundary',m,n,s,o,131200,'identity']['cycles_per_op']) for o in [0,4,64,124]]
            print(m,n,s,cy,[round(x/cy[0],3) for x in cy])
