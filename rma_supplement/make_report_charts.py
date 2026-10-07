"""Scientific figures for the independent supplemental RMA report."""
from pathlib import Path
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager, colors

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/rma_supplement_report_20261007'
FIG=OUT/'图表'
FIG.mkdir(exist_ok=True)
S=pd.read_csv(OUT/'分析表/group_summary.csv').set_index('group')
E=pd.read_csv(OUT/'分析表/paired_effects_recomputed.csv')
B=pd.read_csv(OUT/'分析表/background_load.csv')
T=pd.read_csv(OUT/'分析表/batch_samples.csv')
MODELS=pd.read_csv(OUT/'分析表/route_models.csv')
font_manager.fontManager.addfont('C:/Windows/Fonts/msyh.ttc')
plt.rcParams.update({'font.family':'Microsoft YaHei','font.size':12,'axes.titlesize':14,
                     'axes.labelsize':12,'legend.fontsize':10.5,'axes.unicode_minus':False})
BLUE='#2670AC'; ORANGE='#D86624'; GREEN='#38934B'; NAVY='#21435D'; GRAY='#667B88'


def save(fig,name):
    fig.savefig(FIG/(name+'.png'),dpi=260,bbox_inches='tight',facecolor='white')
    fig.savefig(FIG/(name+'.svg'),bbox_inches='tight',facecolor='white')
    plt.close(fig)


def frame(ax,ylabel):
    ax.set_ylabel(ylabel); ax.grid(axis='y',alpha=.18); ax.set_axisbelow(True)


def paired_bars(ax,groups,labels,columns=('control_median','treatment_median'),names=('控制','处理')):
    x=np.arange(len(groups))
    for j,(col,name,color) in enumerate(zip(columns,names,[BLUE,ORANGE])):
        vals=S.loc[groups,col].to_numpy()
        bars=ax.bar(x+(j-.5)*.32,vals,.32,label=name,color=color)
        ax.bar_label(bars,fmt='%.3f' if vals.max()<100 else '%.0f',padding=3,fontsize=10)
    ax.set_xticks(x,labels); ax.legend(ncol=2)
    ax.margins(y=.17)


def ratio_plot(ax,groups,labels,eff=False):
    row=S.loc[groups]
    mid=row.efficiency_ratio if eff else row.ratio_median
    low=row.eff_ratio_min if eff else row.ratio_min
    high=row.eff_ratio_max if eff else row.ratio_max
    x=np.arange(len(row))
    ax.errorbar(x,(mid-1)*100,yerr=np.vstack([(mid-low)*100,(high-mid)*100]),
                color=ORANGE,marker='o',ls='none',capsize=4,ms=7,label='五作业中位数与范围')
    for k,g in enumerate(groups):
        f=E[E.group==g]
        vals=(f.efficiency_ratio-1)*100 if eff else f.effect_pct
        ax.scatter(np.full(len(f),k)+np.linspace(-.12,.12,len(f)),vals,s=22,c=BLUE,alpha=.55)
    ax.axhline(0,color='#555555',ls='--',lw=1)
    ax.set_xticks(x,labels);frame(ax,'归一化效率变化 (%)' if eff else '处理相对控制变化 (%)')


fig,ax=plt.subplots(figsize=(11.2,3.8),layout='constrained')
for r in range(4):
    for c in range(4):
        bid=4*r+c; pe=16*r+2*c
        rect=plt.Rectangle((c-.45,r-.40),.9,.8,facecolor='#EEF4F8',edgecolor='#859AA9',lw=1)
        ax.add_patch(rect)
        ax.text(c,r-.07,f'块 {bid}',ha='center',va='center',fontsize=12,fontweight='bold')
        ax.text(c,r+.17,f'A 核 {pe}',ha='center',va='center',fontsize=10,color=GRAY)
for p in [(0,0),(3,3)]:
    ax.add_patch(plt.Rectangle((p[0]-.47,p[1]-.42),.94,.84,fill=False,edgecolor=ORANGE,lw=2.5))
ax.set_xlim(-.6,3.6);ax.set_ylim(3.6,-.6);ax.set_xticks(range(4));ax.set_yticks(range(4))
ax.set_xlabel('几何块列');ax.set_ylabel('几何块行');ax.set_aspect('equal')
ax.set_title('E3 探针：块 0 的 A 核 0 与块 15 的 A 核 54')
save(fig,'图01_几何编号')

groups=['g0000','g0001','g0003','g0004','g0006','g0007']
fig,ax=plt.subplots(figsize=(11.2,3.4),layout='constrained')
paired_bars(ax,groups,['0→1\n8 B','0→1\n1 KiB','1→2\n8 B','1→2\n1 KiB','0→63\n8 B','0→63\n1 KiB'],
            names=('只等本地完成','逐消息等待 8 B 回信'))
handles,labels=ax.get_legend_handles_labels();ax.get_legend().remove()
fig.legend(handles,labels,loc='outside upper center',ncol=2)
frame(ax,'发起端 cycles / 数据消息');save(fig,'图02_完成口径')

fig,ax=plt.subplots(figsize=(11.2,3.5),layout='constrained')
ids=[['g0001','g0002'],['g0004','g0005'],['g0007','g0008']]
for j,(name,col,color) in enumerate([('8 B 回信',0,BLUE),('1 KiB 回信',1,ORANGE)]):
    vals=[S.loc[g[col],'treatment_median'] for g in ids]
    ax.bar(np.arange(3)+(j-.5)*.32,vals,.32,label=name,color=color)
    for k,g in enumerate(ids):
        f=E[E.group==g[col]]
        ax.errorbar(k+(j-.5)*.32,np.median(f.treatment),yerr=[[np.median(f.treatment)-f.treatment.min()],
                    [f.treatment.max()-np.median(f.treatment)]],fmt='none',ecolor='#333333',capsize=3)
ax.set_xticks(range(3),['0→1','1→2','0→63']); ax.set_ylim(0,9400);ax.legend(ncol=2)
frame(ax,'完整 RTT (cycles)');save(fig,'图03_回信大小')

groups=['g0009','g0010','g0011','g0012']
labels=['同一发送 CPE','同一接收 CPE','发送端同簇','接收端同簇']
fig,axes=plt.subplots(1,2,figsize=(11.2,3.7),layout='constrained')
paired_bars(axes[0],groups,labels,names=('控制布局','处理布局'))
axes[0].tick_params(axis='x',labelrotation=15); frame(axes[0],'聚合带宽 (B/cycle)')
ratio_plot(axes[1],groups,labels);axes[1].tick_params(axis='x',labelrotation=15)
save(fig,'图04_端点带宽')

fig,axes=plt.subplots(1,2,figsize=(11.2,3.7),layout='constrained')
paired_bars(axes[0],groups,labels,columns=('control_efficiency','treatment_efficiency'),names=('控制 η','处理 η'))
frame(axes[0],'扩展效率 η');axes[0].tick_params(axis='x',labelrotation=15)
axes[0].set_ylim(0,1.14);axes[0].axhline(1,ls='--',lw=1,c='#555555')
ratio_plot(axes[1],groups,labels,eff=True);axes[1].tick_params(axis='x',labelrotation=15)
save(fig,'图05_端点归一化')

groups=['g0013','g0015','g0014','g0016']; labels=['横向反向/同向','纵向反向/同向','横向共边/分开','纵向共边/分开']
fig,axes=plt.subplots(1,2,figsize=(11.2,3.8),layout='constrained')
ratio_plot(axes[0],groups,labels);axes[0].set_title('原始聚合带宽比')
ratio_plot(axes[1],groups,labels,eff=True);axes[1].set_title('按各实际流的单流参考归一化')
for ax in axes: ax.tick_params(axis='x',labelrotation=20)
save(fig,'图06_方向共享')

for src,name in [(0,'图07_正向干扰'),(54,'图08_反向干扰')]:
    f=S[(S.family=='routes') & (S.probe_src==src)]
    layouts=f[f.probe_bytes==8].index.tolist()
    fig,ax=plt.subplots(figsize=(11.2,3.7),layout='constrained')
    for j,(pb,color,mark) in enumerate([(8,BLUE,'o'),(1024,ORANGE,'s')]):
        selected=f[f.probe_bytes==pb]
        mids,low,high=[],[],[]
        for g in layouts:
            a=f.loc[g]
            r=selected[(selected.background_src==a.background_src)&(selected.background_dst==a.background_dst)].iloc[0]
            mids.append(r.effect_pct);low.append(r.effect_pct-r.effect_min);high.append(r.effect_max-r.effect_pct)
        ax.errorbar(np.arange(6)+(j-.5)*.14,mids,yerr=[low,high],fmt=mark,c=color,capsize=4,ms=7,
                    label='8 B 探针' if pb==8 else '1 KiB 探针')
    labels=[]
    for g in layouts:
        a=f.loc[g];bs=int(a.background_src);bd=int(a.background_dst)
        labels.append(f'块 {((bs//8)//2)*4+(bs%8)//2}→{((bd//8)//2)*4+(bd%8)//2}\nCPE {bs}→{bd}')
    ax.set_xticks(range(6),labels,fontsize=11);ax.axhline(0,c='#555555',ls='--',lw=1)
    frame(ax,'带背景 RTT 相对无背景增加 (%)');ax.set_ylim(-1,39)
    handles,legend_labels=ax.get_legend_handles_labels();fig.legend(handles,legend_labels,loc='outside upper center',ncol=2)
    ax.set_title(f'探针 CPE {src}→{54 if src==0 else 0}；每条背景流 4 KiB，W=4')
    save(fig,name)

fig,axes=plt.subplots(1,2,figsize=(11.2,4.0),layout='constrained')
norm=colors.Normalize(vmin=0,vmax=36); cmap=plt.get_cmap('YlOrRd')
for ax,src in zip(axes,[0,54]):
    for r in range(4):
        for c in range(4):
            ax.scatter(c,r,s=420,marker='s',facecolors='#F0F4F7',edgecolors='#B8C4CD',zorder=1)
            ax.text(c,r,str(4*r+c),ha='center',va='center',fontsize=12,color=NAVY)
    for row in S[(S.family=='routes')&(S.probe_src==src)&(S.probe_bytes==1024)].itertuples():
        a,b=int(row.background_src),int(row.background_dst)
        a=((a//8)//2)*4+(a%8)//2;b=((b//8)//2)*4+(b%8)//2
        x0,y0=a%4,a//4;x1,y1=b%4,b//4
        offset=-.065 if (a,b)==(1,2) else (.065 if (a,b)==(2,1) else 0)
        ax.annotate('',xy=(x1,y1+offset),xytext=(x0,y0+offset),arrowprops=dict(arrowstyle='->',lw=3.2,color=cmap(norm(row.effect_pct)),shrinkA=14,shrinkB=14))
        dx=.32 if x0==x1 else 0;dy=-.22 if y0==y1 else 0
        if (a,b)==(2,1):dy=.26
        ax.text((x0+x1)/2+dx,(y0+y1)/2+dy,f'{row.effect_pct:.1f}%',ha='center',va='center',fontsize=11,color='#222222',bbox=dict(facecolor='white',edgecolor='none',pad=.3,alpha=.85))
    ax.set_title('探针 块 0→15' if src==0 else '探针 块 15→0')
    ax.set_xlim(-.35,3.8);ax.set_ylim(3.45,-.4);ax.set_aspect('equal');ax.set_xticks(range(4));ax.set_yticks(range(4))
    ax.set_xlabel('几何块列');ax.set_ylabel('几何块行')
fig.colorbar(plt.cm.ScalarMappable(norm=norm,cmap=cmap),ax=list(axes),label='RTT 增幅 (%)',shrink=.9)
save(fig,'图09_背景边空间图')

fig,axes=plt.subplots(1,2,figsize=(11.2,3.8),layout='constrained')
for src,color,marker,label in [(0,BLUE,'o','探针 0→54'),(54,ORANGE,'s','探针 54→0')]:
    f=S[(S.family=='routes')&(S.probe_src==src)&(S.probe_bytes==1024)]
    axes[0].scatter(f.bg_B_per_cycle,f.effect_pct,c=color,marker=marker,s=58,label=label)
    axes[1].scatter(f.drift_max,f.effect_pct,c=color,marker=marker,s=58)
axes[0].set_xlabel('背景源期间平均吞吐 (B/cycle)');axes[0].legend();axes[0].set_title('负载与干扰共同变化')
axes[1].set_xlabel('同组两次无背景测量的最大漂移 (%)');axes[1].set_title('五作业最大基线漂移')
for ax in axes: frame(ax,'1 KiB 探针 RTT 增幅 (%)')
save(fig,'图10_背景强度与漂移')

fig,axes=plt.subplots(1,3,figsize=(11.2,3.8),layout='constrained')
for ax,g,title in zip(axes,['g0018','g0020','g0026'],['块 1→2；去程 XY 同向','块 2→3；去程 XY 同向','块 1→5；无去程同向边']):
    f=T[T.group==g]
    for role,col,label in [('control',BLUE,'无背景'),('treatment',ORANGE,'带背景')]:
        # Two observations first reduced within job/batch; the five jobs are the range.
        a=f[f.role==role].groupby(['repeat','batch']).RTT_cycles.median().reset_index()
        b=a.groupby('batch').RTT_cycles.agg(['median','min','max'])
        ax.plot(b.index+1,b['median'],c=col,label=label,lw=1.8)
        ax.fill_between(b.index+1,b['min'],b['max'],color=col,alpha=.18)
    ax.set_title(title,fontsize=11);ax.set_xlabel('连续 64 RTT 批次');ax.set_ylim(7700,11600)
    frame(ax,'批均值 RTT (cycles)')
axes[0].legend(ncol=2,fontsize=9);save(fig,'图11_批次时序')

fig,ax=plt.subplots(figsize=(11.2,3.65),layout='constrained')
for j,(col,name,color) in enumerate([('leave_layout_out_RMSE_pct_points','留出一个背景布局',BLUE),
    ('leave_probe_direction_out_RMSE_pct_points','留出整个探针方向',ORANGE)]):
    vals=MODELS[col].to_numpy()
    bars=ax.bar(np.arange(6)+(j-.5)*.34,vals,.34,color=color,label=name)
    ax.bar_label(bars,fmt='%.2f',padding=3,fontsize=10)
ax.set_xticks(range(6),['常数＋大小','XY 去程','YX 去程','XY 无向边','YX 无向边','XY＋YX 去程'],fontsize=11)
ax.set_ylim(0,19);ax.legend(ncol=2);frame(ax,'留出预测 RMSE (百分点)')
save(fig,'图12_模型误差')

groups=['g0009','g0013','g0015','g0018','g0020','g0026','g0038']
labels=['同源 CPE','横向反向','纵向反向','0→54\n背景块1→2','0→54\n背景块2→3','0→54\n背景块1→5','54→0\n背景块1→2']
fig,axes=plt.subplots(1,2,figsize=(11.2,3.8),layout='constrained',gridspec_kw={'width_ratios':[.9,1.4]})
for ax,gs,labs in [(axes[0],groups[:3],labels[:3]),(axes[1],groups[3:],labels[3:])]:
    for j,rep in enumerate(sorted(E.repeat.unique())):
        vals=[E[(E.group==g)&(E.repeat==rep)].effect_pct.iloc[0] for g in gs]
        ax.plot(np.arange(len(gs))+(j-2)*.055,vals,'o',ms=5,label=rep.replace('repeat_','作业 '))
    ax.set_xticks(range(len(gs)),labs,fontsize=10);ax.axhline(0,c='#555555',ls='--',lw=1)
    frame(ax,'处理相对控制变化 (%)')
axes[0].set_title('带宽');axes[1].set_title('1 KiB 探针 RTT')
handles,legend_labels=axes[1].get_legend_handles_labels()
fig.legend(handles,legend_labels,ncol=5,fontsize=9,loc='outside upper center')
save(fig,'图13_作业重复')
print(f'Created {len(list(FIG.glob("*.png")))} figures (PNG and SVG).')
