from pathlib import Path
import csv
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / 'dma_results_20261005_183213_10036'
OUT = Path(__file__).resolve().parents[1] / '图表'
OUT.mkdir(parents=True, exist_ok=True)
FONT = FontProperties(fname='C:/Windows/Fonts/msyh.ttc').get_name()
plt.rcParams.update({'font.family': FONT, 'font.size': 12, 'axes.unicode_minus': False,
                     'axes.spines.top': False, 'axes.spines.right': False,
                     'savefig.dpi': 300, 'svg.fonttype': 'path'})
with (SRC/'summary.csv').open() as f:
    D = {(r['mode'],int(r['active_pes']),int(r['offset']),int(r['bytes'])):r
         for r in csv.DictReader(f)}
S = [2**n for n in range(3,17)]
MODES = ('get','put','iget','iput')
COLORS = dict(zip(MODES, ['#2563eb','#df7126','#13846f','#a545aa']))
def bw(m,n,o,s): return float(D[m,n,o,s]['aggregate_bytes_per_cycle'])
def cy(m,n,o,s): return float(D[m,n,o,s]['cycles_per_op'])
def axes(ax):
    ax.set_xscale('log',base=2)
    ax.set_xticks([8,32,128,512,2048,8192,32768,65536],
                  ['8 B','32 B','128 B','512 B','2 KiB','8 KiB','32 KiB','64 KiB'])
    ax.tick_params(axis='x',labelrotation=35)
    ax.grid(alpha=.18)
    ax.set_xlabel('消息大小')
def save(fig,name):
    for ext in ['png','svg']:
        fig.savefig(OUT/(name+'.'+ext),bbox_inches='tight')
    plt.close(fig)

fig,axs=plt.subplots(2,2,figsize=(10.2,7.4),constrained_layout=True)
for ax,(n,o) in zip(axs.flat,[(1,0),(1,4),(64,0),(64,4)]):
    for m in MODES:
        ax.plot(S,[bw(m,n,o,s) for s in S],color=COLORS[m],marker='o',markersize=4,
                linestyle='--' if m.startswith('i') else '-',label=m)
    ax.set_title(f'{n} 个活跃从核  主存偏移 {o} B',fontsize=13)
    ax.set_ylabel('聚合带宽  B/cycle')
    ax.set_ylim(bottom=0)
    axes(ax); ax.legend(ncol=2,fontsize=11)
save(fig,'图1_DMA带宽曲线')

fig,axs=plt.subplots(1,2,figsize=(10.2,4.0),constrained_layout=True)
for ax,o in zip(axs,[0,4]):
    for m in MODES:
        ax.plot(S,[bw(m,64,o,s)/bw(m,1,o,s) for s in S],color=COLORS[m],marker='o',
                markersize=4,linestyle='--' if m.startswith('i') else '-',label=m)
    ax.axhline(1,color='#555555',linestyle=':',label='与单核相同')
    ax.set_title(f'主存偏移 {o} B',fontsize=13)
    ax.set_ylabel('64 核与单核的聚合带宽比')
    ax.set_ylim(bottom=0)
    axes(ax); ax.legend(ncol=2,fontsize=10)
save(fig,'图2_DMA并发扩展比')

fig,axs=plt.subplots(1,2,figsize=(10.2,4.0),constrained_layout=True)
for ax,n in zip(axs,[1,64]):
    for m in MODES:
        ax.plot(S,[cy(m,n,4,s)/cy(m,n,0,s) for s in S],color=COLORS[m],marker='o',
                markersize=4,linestyle='--' if m.startswith('i') else '-',label=m)
    ax.axhline(1,color='#555555',linestyle=':')
    ax.set_title(f'{n} 个活跃从核',fontsize=13)
    ax.set_ylabel('偏移 4 B 与对齐的耗时比')
    ax.set_yscale('log',base=2)
    ax.set_yticks([.5,1,2,4,8,16],['0.5','1','2','4','8','16'])
    axes(ax); ax.legend(ncol=2,fontsize=11)
save(fig,'图3_DMA主存对齐影响')

fig,axs=plt.subplots(1,2,figsize=(10.2,4.0),constrained_layout=True)
for ax,m in zip(axs,['get','put']):
    for n in [1,64]:
        for o in [0,4]:
            ax.plot(S,[cy(m,n,o,s) for s in S],marker='o',markersize=4,
                    linestyle='--' if o else '-',label=f'{n} 核  偏移 {o} B')
    ax.set_title(m,fontsize=14)
    ax.set_ylabel('最大逐核完成耗时  cycles/op')
    ax.set_yscale('log')
    axes(ax); ax.legend(fontsize=10)
save(fig,'图4_DMA操作完成耗时')

fig,axs=plt.subplots(2,2,figsize=(9.2,7.8),constrained_layout=True)
for ax,(m,o) in zip(axs.flat,[('get',0),('get',4),('put',0),('put',4)]):
    with (SRC/'raw'/f'dma_{m}_64pe_128B_offset{o}.csv').open() as f:
        vals=np.array([float(r['cycles_per_op']) for r in csv.DictReader(f)
                       if r['pe']!='aggregate']).reshape(8,8)
    im=ax.imshow(vals,cmap='viridis')
    for r in range(8):
        for c in range(8):
            frac=(vals[r,c]-vals.min())/(vals.max()-vals.min())
            ax.text(c,r,f'{vals[r,c]:.0f}',ha='center',va='center',fontsize=10,
                    color='white' if frac<.5 else 'black')
    ax.set_title(f'{m}  128 B  偏移 {o} B',fontsize=13)
    ax.set_xticks(range(8)); ax.set_yticks(range(8))
    ax.set_xlabel('从核编号 mod 8')
    ax.set_ylabel('从核编号整除 8')
    fig.colorbar(im,ax=ax,shrink=.75,label='cycles/op')
save(fig,'图5_DMA逐核耗时热图')
print('Created 5 Chinese figures, each in PNG and SVG format.')
