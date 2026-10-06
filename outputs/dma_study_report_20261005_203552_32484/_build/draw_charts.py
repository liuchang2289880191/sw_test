from pathlib import Path
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.colors import LogNorm
from matplotlib.ticker import FuncFormatter

ROOT=Path(__file__).resolve().parents[3]
SRC=ROOT/'dma_results_20261005_203552_32484'
ANA=ROOT/'outputs/dma_study_analysis_20261005_203552_32484'
OUT=Path(__file__).resolve().parents[1]/'图表'
OUT.mkdir(parents=True,exist_ok=True)
FONT=FontProperties(fname='C:/Windows/Fonts/msyh.ttc').get_name()
plt.rcParams.update({'font.family':FONT,'font.size':11,'axes.unicode_minus':False,
    'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':300,'svg.fonttype':'path'})
def read(path):return list(csv.DictReader(path.open(encoding='utf-8-sig')))
D={(r['phase'],r['mode'],int(r['active_pes']),int(r['bytes']),int(r['offset']),int(r['slot_stride']),r['mapping']):r for r in read(SRC/'study_summary.csv')}
MODES=['get','put','iget','iput']; N=[1,2,4,8,16,32,64]
MAPS=['identity','reverse','transpose','shuffle']; T=[131200,131328,135168,262144]
BS=[64,96,124,128,132,192,252,256,260]
LS=sorted({int(r['bytes']) for r in D.values() if r['phase']=='load'})
def row(p,m,n,s,o=0,t=131200,k='identity'):return D[p,m,n,s,o,t,k]
def bw(*a):return float(row(*a)['aggregate_bytes_per_cycle'])
def cy(*a):return float(row(*a)['cycles_per_op'])
def save(fig,name):
    for ext in ['png','svg']:fig.savefig(OUT/(name+'.'+ext),bbox_inches='tight')
    plt.close(fig)
def size_axis(ax):
    ax.set_xscale('log',base=2)
    ax.set_xticks([8,64,128,512,4096,32768,131072],['8 B','64 B','128 B','512 B','4 KiB','32 KiB','128 KiB'])
    ax.tick_params(axis='x',labelrotation=30);ax.set_xlabel('消息大小');ax.grid(alpha=.2)

fig,axs=plt.subplots(2,2,figsize=(10.8,7.0),constrained_layout=True)
for ax,(m,n) in zip(axs.flat,[('put',1),('iput',1),('put',64),('iput',64)]):
    data=np.array([[cy('boundary',m,n,s,o) for s in BS] for o in [0,4,64,124]])
    im=ax.imshow(data,aspect='auto',cmap='YlOrRd',norm=LogNorm(vmin=200,vmax=7000))
    ax.set_xticks(range(9),BS,rotation=35);ax.set_yticks(range(4),[0,4,64,124])
    ax.set_xlabel('消息大小 B');ax.set_ylabel('主存偏移 B');ax.set_title(f'{m}  {n} 个活跃从核')
    for i in range(4):
        for j in range(9):ax.text(j,i,f'{data[i,j]:.0f}',ha='center',va='center',fontsize=8,color='white' if data[i,j]>3400 else 'black')
bar=fig.colorbar(im,ax=axs,shrink=.85);bar.set_label('最慢核平均完成耗时 cycles/op');bar.set_ticks([200,400,1000,2000,4000,7000]);bar.set_ticklabels(['200','400','1000','2000','4000','7000'])
save(fig,'图1_写入边界细扫')

fig,axs=plt.subplots(1,2,figsize=(10.8,4.2),constrained_layout=True)
cols=['#2563eb','#db732d','#16836b']
for ax,s in zip(axs,[128,256]):
    for c,o in zip(cols,[4,64,124]):
        for m in ['put','iput']:
            ax.plot(N,[cy('boundary',m,n,s,o)/cy('boundary',m,n,s,0) for n in N],color=c,marker='o',markersize=4,
                    linestyle='-' if m=='put' else '--',label=f'{m} 偏移{o} B')
    ax.set_xscale('log',base=2);ax.set_xticks(N,N);ax.axhline(1,color='#555',linestyle=':')
    ax.set_ylim(0,13);ax.set_title(f'{s} B 消息');ax.set_xlabel('活跃从核数');ax.set_ylabel('偏移与对齐的耗时比')
    ax.grid(alpha=.2);ax.legend(ncol=2,fontsize=9)
save(fig,'图2_偏移代价随核数变化')

fig,axs=plt.subplots(2,2,figsize=(10.8,7.2),constrained_layout=True)
colors=['#777777','#d68b21','#248969','#3465bd','#923ca9']
for ax,m in zip(axs.flat,MODES):
    for n,c in zip([1,4,8,32,64],colors):ax.plot(LS,[bw('load',m,n,s) for s in LS],color=c,marker='o',markersize=3,label=f'{n} 核')
    ax.set_title(f'{m}  偏移0 B');ax.set_ylabel('聚合带宽 B/cycle');ax.set_ylim(0,23);size_axis(ax);ax.legend(ncol=3,fontsize=9)
save(fig,'图3_消息大小与带宽')

fig,axs=plt.subplots(2,2,figsize=(10.8,7.0),constrained_layout=True)
for ax,(m,o) in zip(axs.flat,[('get',0),('get',4),('put',0),('put',4)]):
    for s,c in zip([128,4096,65536,131072],['#a67b20','#2563eb','#d46938','#16836b']):
        ax.plot(N,[bw('load',m,n,s,o) for n in N],color=c,marker='o',markersize=4,label=f'{s} B' if s<1024 else f'{s//1024} KiB')
    ax.set_xscale('log',base=2);ax.set_xticks(N,N);ax.set_ylim(0,23)
    ax.set_title(f'{m}  偏移{o} B');ax.set_xlabel('活跃从核数');ax.set_ylabel('聚合带宽 B/cycle');ax.grid(alpha=.2);ax.legend(ncol=2,fontsize=10)
save(fig,'图4_核数与聚合带宽')

fig,axs=plt.subplots(2,2,figsize=(10.8,7.3),constrained_layout=True)
for ax,m in zip(axs.flat,MODES):
    data=np.array([[bw('mapping',m,64,131072,0,t,k) for k in MAPS] for t in T])
    im=ax.imshow(data,aspect='auto',cmap='viridis',vmin=13,vmax=21)
    ax.set_xticks(range(4),MAPS,rotation=20);ax.set_yticks(range(4),[f'{t:,}' for t in T])
    ax.set_title(f'{m}  128 KiB  64核  偏移0 B');ax.set_xlabel('核到槽映射');ax.set_ylabel('槽步长 B')
    for i in range(4):
        for j in range(4):ax.text(j,i,f'{data[i,j]:.3f}',ha='center',va='center',color='white' if data[i,j]<17 else 'black',fontsize=11)
fig.colorbar(im,ax=axs,shrink=.9,label='聚合带宽 B/cycle')
save(fig,'图5_槽步长与映射对照')

PE=np.load(ANA/'pe_cycles.npz')['cycles_per_op']
slots={k:np.empty(64,dtype=int) for k in MAPS}
for r in read(SRC/'slot_maps.csv'):slots[r['mapping']][int(r['pe'])]=int(r['slot'])
for m,s,filename in [('get',256,'图6_读取耗时随地址槽移动'),('put',131072,'图7_大消息写入的逐核模式')]:
    arrays=[]
    for k in MAPS:
        r=row('mapping',m,64,s);r=row('mapping',m,64,s,0,131200,k)
        by_pe=PE[int(r['case_id'])-1];by_slot=np.empty(64);by_slot[slots[k]]=by_pe
        arrays.append((by_pe,by_slot))
    lo=min(a.min() for pair in arrays for a in pair);hi=max(a.max() for pair in arrays for a in pair)
    fig,axs=plt.subplots(2,4,figsize=(11.5,6.7),constrained_layout=True)
    for j,k in enumerate(MAPS):
        for i,order in enumerate(['按核 ID 排列','按地址槽号排列']):
            ax=axs[i,j];data=arrays[j][i].reshape(8,8)
            im=ax.imshow(data,cmap='viridis',vmin=lo,vmax=hi,aspect='equal')
            ax.set_title(f'{k}\n{order}',fontsize=11);ax.set_xticks([0,3,7]);ax.set_yticks([0,3,7])
            ax.set_xlabel('编号 % 8');ax.set_ylabel('编号 // 8')
    bar=fig.colorbar(im,ax=axs,shrink=.8,label='逐核平均完成耗时 cycles/op')
    if s>=1024:
        bar.formatter=FuncFormatter(lambda value,position:f'{value/1000:.0f}')
        bar.update_ticks();bar.set_label('逐核平均完成耗时 千cycles/op',labelpad=12)
    save(fig,filename)

fig,axs=plt.subplots(1,2,figsize=(10.8,4.3),constrained_layout=True)
overlap=read(ANA/'phase_overlap_comparisons.csv')
v=[[100*float(r['abs_relative_change']) for r in overlap if r['first_phase']==p] for p in ['boundary','load']]
axs[0].boxplot(v,tick_labels=['boundary→load\n504组','load→mapping\n448组'],showfliers=True,
    flierprops={'marker':'.','markersize':4,'alpha':.5},medianprops={'color':'#df7126'})
axs[0].set_ylabel('同配置带宽绝对相对变化 %');axs[0].set_title('同一作业内的跨阶段复测');axs[0].grid(axis='y',alpha=.2)
ratios=[]
for a,b in [('iget','get'),('iput','put')]:ratios.append([100*(bw('load',a,n,s,o)/bw('load',b,n,s,o)-1) for n in N for s in LS for o in [0,4]])
axs[1].boxplot(ratios,tick_labels=['iget/get\n420组','iput/put\n420组'],showfliers=True,
    flierprops={'marker':'.','markersize':4,'alpha':.5},medianprops={'color':'#16836b'})
axs[1].axhline(0,color='#555',linestyle=':');axs[1].set_ylabel('非阻塞相对阻塞的带宽变化 %');axs[1].set_title('立即等待完成时的接口对照');axs[1].grid(axis='y',alpha=.2)
save(fig,'图8_阶段一致性与接口对照')

(OUT/'图表说明.txt').write_text('8 张中文图表，每张提供 300 dpi PNG 与嵌入字形路径的 SVG。主要单位为 cycles/op 和 B/cycle，未假设计数器频率。图6图7的地址槽8×8排列只是编号的重排展示，不能解释为内存的物理二维拓扑。图8箱线图展示不同配置或匹配复测的分布，不代表独立重复得到的置信区间。\n',encoding='utf-8')
print('Created 8 PNG and 8 SVG figures:',OUT)
