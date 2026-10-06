"""Compare sampling density using the same measured values; no hardware run."""
from pathlib import Path
import csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parents[1]/'对照图'
OUT.mkdir(exist_ok=True)
def read(p): return list(csv.DictReader(p.open(encoding='utf-8-sig')))
old=read(ROOT/'dma_results_20261005_183213_10036'/'summary.csv')
new=read(ROOT/'dma_results_20261005_203552_32484'/'study_summary.csv')
old={(r['mode'],int(r['bytes'])):float(r['aggregate_bytes_per_cycle']) for r in old
     if r['active_pes']=='64' and r['offset']=='0'}
new={(r['mode'],int(r['bytes'])):float(r['aggregate_bytes_per_cycle']) for r in new
     if r['phase']=='load' and r['active_pes']=='64' and r['offset']=='0'}
plt.rcParams.update({'font.family':FontProperties(fname='C:/Windows/Fonts/msyh.ttc').get_name(),
 'font.size':17,'axes.titlesize':20,'axes.labelsize':18,'axes.unicode_minus':False,
 'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'path'})
fig,axs=plt.subplots(1,2,figsize=(16,6))
fig.subplots_adjust(left=.07,right=.98,bottom=.31,top=.83,wspace=.21)
coarse=[64,128,256,512]
fine=sorted(s for m,s in new if m=='get' and 64<=s<=512)
for ax,m in zip(axs,['get','put']):
 ax.plot(coarse,[old[m,s] for s in coarse],color='#777777',lw=2.2,marker='s',ms=6,
         label='旧实验：倍增测点')
 ax.plot(fine,[new[m,s] for s in fine],color='#c75b12',lw=2.6,marker='o',ms=6,
         label='新实验：全部测点')
 ax.plot(coarse,[new[m,s] for s in coarse],color='#2166ac',lw=2.4,ls='--',marker='o',ms=9,
         markerfacecolor='white',markeredgewidth=2,label='新实验：仅保留旧测点')
 ax.set_xscale('log',base=2);ax.set_xticks(coarse,[str(x) for x in coarse])
 ax.set_ylim(0,21);ax.set_xlabel('消息大小（B，对数刻度）');ax.set_ylabel('聚合带宽（B/cycle）')
 ax.set_title(m);ax.grid(alpha=.18)
 if m=='put':
  for s,xy in [(128,(96,20)),(132,(165,6)),(256,(295,20)),(260,(340,7))]:
   ax.annotate(f'{s} B',xy=(s,new[m,s]),xytext=xy,fontsize=15,color='#c75b12',
               arrowprops={'arrowstyle':'->','color':'#c75b12','lw':1.3})
fig.suptitle('64核  主存偏移0 B  实线点之间连线仅用于展示',fontsize=19,y=.98)
handles,labels=axs[0].get_legend_handles_labels()
fig.legend(handles,labels,loc='lower center',bbox_to_anchor=(.52,.05),ncol=3,frameon=False,fontsize=17)
for ext in ['png','svg']:
 fig.savefig(OUT/f'旧新实验采样密度对照.{ext}',dpi=300,bbox_inches='tight',facecolor='white')
plt.close(fig)
print(OUT)
