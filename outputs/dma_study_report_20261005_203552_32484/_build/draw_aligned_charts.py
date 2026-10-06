"""Plots for the seven-section report, computed only from the new dataset."""
from pathlib import Path
import csv
import shutil
import sys
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

OUT=Path(__file__).resolve().parents[1]
FIG=OUT/'结构对齐图表'; FIG.mkdir(exist_ok=True)
ROOT=OUT.parents[1]
SRC=ROOT/'dma_results_20261005_203552_32484'
D={(r['phase'],r['mode'],int(r['active_pes']),int(r['bytes']),int(r['offset']),int(r['slot_stride']),r['mapping']):r
   for r in csv.DictReader((SRC/'study_summary.csv').open(encoding='utf-8-sig'))}
S=sorted({k[3] for k in D if k[0]=='load'})
M=['get','put','iget','iput']
plt.rcParams.update({'font.family':FontProperties(fname='C:/Windows/Fonts/msyh.ttc').get_name(),
 'font.size':11,'axes.unicode_minus':False,'axes.spines.top':False,'axes.spines.right':False,
 'savefig.dpi':300,'svg.fonttype':'path'})
def val(m,n,s,o,field):return float(D['load',m,n,s,o,131200,'identity'][field])
def axis(ax):
    ax.set_xscale('log',base=2)
    ax.set_xticks([8,64,128,512,4096,32768,131072],['8 B','64 B','128 B','512 B','4 KiB','32 KiB','128 KiB'])
    ax.tick_params(axis='x',labelrotation=30);ax.set_xlabel('消息大小');ax.grid(alpha=.2)
def save(fig,name):
    for ext in ['png','svg']:fig.savefig(FIG/(name+'.'+ext),bbox_inches='tight')
    plt.close(fig)

fig,axs=plt.subplots(2,2,figsize=(10.8,7),constrained_layout=True)
for ax,m in zip(axs.flat,M):
    for n,c in [(1,'#2563eb'),(64,'#d97725')]:
        for o,ls in [(0,'-'),(4,'--')]:
            ax.plot(S,[val(m,n,s,o,'aggregate_bytes_per_cycle') for s in S],color=c,linestyle=ls,
                    marker='o',markersize=3,label=f'{n}核 偏移{o} B')
    ax.set_title(m);ax.set_ylabel('聚合带宽 B/cycle');ax.set_ylim(0,23);axis(ax)
    if m in ['put','iput']:
        ax.set_xticks([8,128,1024,8192,32768,131072],['8 B','128 B','1 KiB','8 KiB','32 KiB','128 KiB'])
        for s,tx,ty in [(128,24,21.2),(256,480,20.5)]:
            ax.annotate(f'{s} B',xy=(s,val(m,64,s,0,'aggregate_bytes_per_cycle')),xytext=(tx,ty),
                        fontsize=10,color='#a54d12',fontweight='bold',
                        arrowprops={'arrowstyle':'->','color':'#a54d12','lw':1})
        ax.legend(fontsize=9,ncol=2,loc='lower right')
    else:ax.legend(fontsize=9,ncol=2)
save(fig,'图1_DMA带宽曲线')
if '--bandwidth-only' in sys.argv:
    print('Updated annotated bandwidth figure:',FIG)
    sys.exit(0)

fig,axs=plt.subplots(1,2,figsize=(10.8,4.3),constrained_layout=True)
for ax,o in zip(axs,[0,4]):
    for m,c in zip(M,['#2563eb','#d97725','#15866c','#923ca9']):
        ax.plot(S,[val(m,64,s,o,'aggregate_bytes_per_cycle')/val(m,1,s,o,'aggregate_bytes_per_cycle') for s in S],
                color=c,linestyle='--' if m.startswith('i') else '-',marker='o',markersize=3,label=m)
    ax.axhline(1,color='#555',linestyle=':',label='与单核相同');ax.set_title(f'主存偏移{o} B')
    ax.set_ylabel('64核与单核的聚合带宽比');ax.set_ylim(0,38);axis(ax);ax.legend(fontsize=9,ncol=2)
save(fig,'图2_并发扩展比')

fig,axs=plt.subplots(1,2,figsize=(10.8,4.3),constrained_layout=True)
for ax,m in zip(axs,['get','put']):
    for n,c in [(1,'#2563eb'),(64,'#d97725')]:
        for o,ls in [(0,'-'),(4,'--')]:
            ax.plot(S,[val(m,n,s,o,'cycles_per_op') for s in S],color=c,linestyle=ls,
                    marker='o',markersize=3,label=f'{n}核 偏移{o} B')
    ax.set_title(m);ax.set_ylabel('最慢核平均完成耗时 cycles/op');ax.set_yscale('log');axis(ax);ax.legend(fontsize=9,ncol=2)
save(fig,'图6_操作完成耗时')

copies={
 '图4_核数与聚合带宽':'图3_活跃核数与共享吞吐',
 '图1_写入边界细扫':'图4_写入边界细扫',
 '图2_偏移代价随核数变化':'图5_偏移代价与负载',
 '图8_阶段一致性与接口对照':'图7_阶段复测与接口对照',
 '图6_读取耗时随地址槽移动':'图8_读取空间差异',
 '图7_大消息写入的逐核模式':'图9_写入空间差异',
 '图5_槽步长与映射对照':'图10_槽布局与聚合吞吐',
}
for old,new in copies.items():
    for ext in ['png','svg']:shutil.copy2(OUT/'图表'/(old+'.'+ext),FIG/(new+'.'+ext))
(FIG/'说明.txt').write_text('图表由本次 dma_results_20261005_203552_32484 数据生成。PNG 为300dpi，SVG为矢量。图号按结构对齐版正文顺序排列。\n',encoding='utf-8')
print('Saved 10 numbered figures:',FIG)
