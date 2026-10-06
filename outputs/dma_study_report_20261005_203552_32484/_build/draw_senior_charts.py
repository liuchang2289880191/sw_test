"""Large scientific figures for the data report; no benchmark execution."""
from pathlib import Path
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.colors import LogNorm
from matplotlib.lines import Line2D

OUT=Path(__file__).resolve().parents[1]
ROOT=OUT.parents[1]; SRC=ROOT/'dma_results_20261005_203552_32484'
ANA=ROOT/'outputs/dma_study_analysis_20261005_203552_32484'
FIG=OUT/'汇报大图'; FIG.mkdir(exist_ok=True)
def read(p):return list(csv.DictReader(p.open(encoding='utf-8-sig')))
ROWS=read(SRC/'study_summary.csv')
D={(r['phase'],r['mode'],int(r['active_pes']),int(r['bytes']),int(r['offset']),int(r['slot_stride']),r['mapping']):r for r in ROWS}
S=sorted({int(r['bytes']) for r in ROWS if r['phase']=='load'})
N=[1,2,4,8,16,32,64]; BS=[64,96,124,128,132,192,252,256,260]
MAPS=['identity','reverse','transpose','shuffle']; STRIDES=[131200,131328,135168,262144]
def row(p,m,n,s,o=0,t=131200,k='identity'):return D[p,m,n,s,o,t,k]
def bw(*a):return float(row(*a)['aggregate_bytes_per_cycle'])
def cy(*a):return float(row(*a)['cycles_per_op'])
BLUE='#2166ac'; ORANGE='#c75b12'; GREEN='#14806b'; PURPLE='#82489b'
plt.rcParams.update({'font.family':FontProperties(fname='C:/Windows/Fonts/msyh.ttc').get_name(),
 'font.size':16,'axes.titlesize':19,'axes.labelsize':17,'xtick.labelsize':15,'ytick.labelsize':15,
 'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':300,'svg.fonttype':'path'})
def pair(height=4.8):
    fig,axs=plt.subplots(1,2,figsize=(14,height))
    fig.subplots_adjust(left=.07,right=.98,bottom=.31,top=.90,wspace=.27)
    return fig,axs
def save(fig,name):
    for ext in ['png','svg']:fig.savefig(FIG/(name+'.'+ext),bbox_inches='tight',facecolor='white')
    plt.close(fig)
def sizes(ax):
    ax.set_xscale('log',base=2)
    ax.set_xticks([8,128,1024,8192,32768,131072],['8 B','128 B','1 KiB','8 KiB','32 KiB','128 KiB'])
    ax.tick_params(axis='x',labelrotation=20);ax.set_xlabel('消息大小（对数刻度）');ax.grid(alpha=.18)
handles=[Line2D([0],[0],color=c,ls=ls,lw=2.5,marker='o',label=f'{n}核 · 偏移{o} B')
         for n,c in [(1,BLUE),(64,ORANGE)] for o,ls in [(0,'-'),(4,'--')]]
for modes,name in [(['get','iget'],'图01_读取带宽'),(['put','iput'],'图02_写入带宽')]:
    fig,axs=pair()
    for ax,m in zip(axs,modes):
        for n,c in [(1,BLUE),(64,ORANGE)]:
            for o,ls in [(0,'-'),(4,'--')]:
                ax.plot(S,[bw('load',m,n,s,o) for s in S],color=c,ls=ls,lw=2.5,marker='o',ms=4)
        ax.set_title(m);ax.set_ylabel('聚合带宽（B/cycle）');ax.set_ylim(0,23);sizes(ax)
        if m in ['put','iput']:
            for s,x,y in [(128,26,21.1),(256,550,20.4)]:
                ax.annotate(f'{s} B',xy=(s,bw('load',m,64,s)),xytext=(x,y),color=ORANGE,fontweight='bold',fontsize=16,
                            arrowprops={'arrowstyle':'->','color':ORANGE,'lw':1.5})
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.53,-.01),ncol=4,fontsize=15,frameon=False)
    save(fig,name)

fig,axs=pair()
for ax,o in zip(axs,[0,4]):
    for m,c in [('get',BLUE),('put',ORANGE)]:
        ax.plot(S,[bw('load',m,64,s,o)/bw('load',m,1,s,o) for s in S],color=c,lw=2.6,marker='o',ms=4,label=m)
    ax.axhline(1,color='#555',ls=':',lw=1.7);ax.set_title(f'主存偏移 {o} B')
    ax.set_ylabel('64核 / 单核 聚合带宽比');ax.set_ylim(0,38);sizes(ax);ax.legend(fontsize=16,frameon=False)
save(fig,'图03_并发扩展比')

fig,axs=pair(4.4)
for ax,m,c in zip(axs,['get','put'],[BLUE,ORANGE]):
    v=[bw('load',m,n,131072) for n in N]
    bars=ax.bar(range(7),v,color=c,width=.65,zorder=3)
    ax.bar_label(bars,labels=[f'{x:.2f}' for x in v],padding=5,fontsize=15)
    ax.set_xticks(range(7),N);ax.set_title(f'{m} · 128 KiB · 偏移0 B')
    ax.set_ylim(0,24);ax.set_xlabel('活跃核数');ax.set_ylabel('聚合带宽（B/cycle）');ax.grid(axis='y',alpha=.18,zorder=0)
save(fig,'图04_七档核数吞吐')

for n,name in [(1,'图05_单核写入边界'),(64,'图06_64核写入边界')]:
    fig,axs=plt.subplots(1,2,figsize=(14,4.4));fig.subplots_adjust(left=.06,right=.91,bottom=.21,top=.86,wspace=.20)
    for ax,m in zip(axs,['put','iput']):
        v=np.array([[cy('boundary',m,n,s,o) for s in BS] for o in [0,4,64,124]])
        im=ax.imshow(v,aspect='auto',cmap='YlOrRd',norm=LogNorm(350,7000) if n==64 else None,
                     vmin=None if n==64 else 230,vmax=None if n==64 else 460)
        ax.set_xticks(range(9),BS,rotation=35);ax.set_yticks(range(4),[0,4,64,124]);ax.set_xlabel('消息大小（B）')
        ax.set_ylabel('主存偏移（B）');ax.set_title(f'{m} · {n}核')
        for i in range(4):
            for j in range(9):ax.text(j,i,f'{v[i,j]:.0f}',ha='center',va='center',fontsize=15,
                                    color='white' if v[i,j]>(3000 if n==64 else 365) else 'black')
    cb=fig.colorbar(im,cax=fig.add_axes([.93,.28,.018,.48]));cb.set_label('完成耗时（cycles/op）',fontsize=16)
    if n==64:cb.set_ticks([400,1000,2000,4000,7000]);cb.set_ticklabels(['400','1000','2000','4000','7000'])
    save(fig,name)

fig,axs=pair()
for ax,s in zip(axs,[128,256]):
    for o,c in [(4,BLUE),(64,ORANGE),(124,GREEN)]:
        for m,ls in [('put','-'),('iput','--')]:
            ax.plot(range(7),[cy('boundary',m,n,s,o)/cy('boundary',m,n,s) for n in N],color=c,ls=ls,lw=2.5,marker='o',ms=5)
    ax.set_xticks(range(7),N);ax.set_title(f'{s} B 消息');ax.set_xlabel('活跃核数')
    ax.set_ylabel('偏移 / 对齐 完成耗时比');ax.set_ylim(0,13);ax.axhline(1,color='#555',ls=':');ax.grid(alpha=.18)
    ax.annotate(f'{cy("boundary","put",64,s,4)/cy("boundary","put",64,s):.2f}倍',
                xy=(6,cy('boundary','put',64,s,4)/cy('boundary','put',64,s)),xytext=(4.6,12.3 if s==128 else 9.2),color=BLUE,
                arrowprops={'arrowstyle':'->','color':BLUE},fontsize=16)
hnd=[Line2D([0],[0],color=c,lw=2.5,label=f'偏移{o} B') for o,c in [(4,BLUE),(64,ORANGE),(124,GREEN)]]
hnd += [Line2D([0],[0],color='#555',lw=2.5,ls=ls,label=m) for m,ls in [('put','-'),('iput','--')]]
fig.legend(handles=hnd,loc='lower center',bbox_to_anchor=(.53,-.01),ncol=5,frameon=False,fontsize=15)
save(fig,'图07_偏移惩罚随核数变化')

fig,axs=pair()
for ax,m in zip(axs,['get','put']):
    for n,c in [(1,BLUE),(64,ORANGE)]:
        for o,ls in [(0,'-'),(4,'--')]:
            ax.plot(S,[cy('load',m,n,s,o) for s in S],color=c,ls=ls,lw=2.5,marker='o',ms=4)
    ax.set_title(m);ax.set_yscale('log');ax.set_ylabel('完成耗时（cycles/op）');sizes(ax)
fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.53,-.01),ncol=4,fontsize=15,frameon=False)
save(fig,'图08_操作完成耗时')

PE=np.load(ANA/'pe_cycles.npz')['cycles_per_op']
slots=np.empty(64,dtype=int)
for r in read(SRC/'slot_maps.csv'):
    if r['mapping']=='reverse':slots[int(r['pe'])]=int(r['slot'])
for m,s,name in [('get',256,'图09_读取逐核模式'),('put',131072,'图10_写入逐核模式')]:
    ref=PE[int(row('mapping',m,64,s)['case_id'])-1]
    rev=PE[int(row('mapping',m,64,s,0,131200,'reverse')['case_id'])-1]
    ordered=np.empty(64);ordered[slots]=rev
    values=[ref,rev,ordered]; scale=1000 if s>1024 else 1
    lo=min(x.min()/scale for x in values);hi=max(x.max()/scale for x in values)
    fig,axs=plt.subplots(1,3,figsize=(14,5.3));fig.subplots_adjust(left=.05,right=.92,bottom=.22,top=.82,wspace=.25)
    for ax,v,title in zip(axs,values,['identity · 按核ID','reverse · 按核ID','reverse · 按地址槽']):
        im=ax.imshow(v.reshape(8,8)/scale,vmin=lo,vmax=hi,cmap='viridis',aspect='equal')
        ax.set_title(title,fontsize=17);ax.set_xticks([0,3,7]);ax.set_yticks([0,3,7]);ax.set_xlabel('编号 mod 8');ax.set_ylabel('编号 div 8')
    cb=fig.colorbar(im,cax=fig.add_axes([.945,.29,.015,.39]));cb.set_label('耗时（千cycles/op）' if scale==1000 else '耗时（cycles/op）')
    save(fig,name)

fig,axs=plt.subplots(1,2,figsize=(14,4.9));fig.subplots_adjust(left=.09,right=.91,bottom=.22,top=.85,wspace=.26)
for ax,m in zip(axs,['get','put']):
    v=np.array([[bw('mapping',m,64,131072,0,t,k) for k in MAPS] for t in STRIDES])
    im=ax.imshow(v,aspect='auto',cmap='viridis',vmin=13,vmax=21)
    ax.set_title(f'{m} · 128 KiB · 64核');ax.set_xticks(range(4),MAPS,rotation=15);ax.set_yticks(range(4),[f'{t:,}' for t in STRIDES])
    ax.set_xlabel('核到槽的排列');ax.set_ylabel('槽步长（B）')
    for i in range(4):
        for j in range(4):ax.text(j,i,f'{v[i,j]:.3f}',ha='center',va='center',fontsize=18,color='white' if v[i,j]<17 else 'black')
cb=fig.colorbar(im,cax=fig.add_axes([.93,.28,.018,.47]));cb.set_label('带宽（B/cycle）')
save(fig,'图11_槽布局与吞吐')
print('Created 11 large figures:',FIG)
