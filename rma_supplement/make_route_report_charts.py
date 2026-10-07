"""Additional scientific charts for the real route-identifiability experiment."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/rma_supplement_report_20261007'
FIG=OUT/'图表'
D=json.loads((OUT/'route_report_data.json').read_text(encoding='utf-8'))
S=pd.DataFrame(D['summary']).set_index('group')
E=pd.DataFrame(D['effects']);M=pd.DataFrame(D['models'])
P=pd.read_csv(OUT/'分析表/路径补充/predictions.csv')
font_manager.fontManager.addfont('C:/Windows/Fonts/msyh.ttc')
plt.rcParams.update({'font.family':'Microsoft YaHei','font.size':13,'axes.titlesize':14,
                     'axes.labelsize':13,'legend.fontsize':11.5,'axes.unicode_minus':False})
BLUE='#2670AC';ORANGE='#D86624';GRAY='#667B88';GREEN='#38934B'


def save(fig,name):
    fig.savefig(FIG/(name+'.png'),dpi=280,bbox_inches='tight',facecolor='white')
    fig.savefig(FIG/(name+'.svg'),bbox_inches='tight',facecolor='white');plt.close(fig)


def bg(r):return f"{int(r['background_src_block'])}→{int(r['background_dst_block'])}"


def directions():
    for src,number in [(0,14),(54,15)]:
        subset=S[S.probe_src==src]
        layouts=subset[subset.probe_bytes==8].index.tolist();labels=[]
        fig,ax=plt.subplots(figsize=(11.2,5.45),layout='constrained')
        y=np.arange(len(layouts))
        for pb,offset,color,marker,label in [(8,-.14,BLUE,'o','8 B 探针'),(1024,.14,ORANGE,'s','1 KiB 探针')]:
            rows=[]
            for g in layouts:
                r=subset.loc[g];rows.append(subset[(subset.layout_id==r.layout_id)&(subset.probe_bytes==pb)].iloc[0])
            mid=np.array([r.effect_pct_median for r in rows]);lo=np.array([r.effect_pct_min for r in rows]);hi=np.array([r.effect_pct_max for r in rows])
            ax.errorbar(mid,y+offset,xerr=np.vstack([mid-lo,hi-mid]),color=color,marker=marker,ls='none',
                        capsize=3,ms=5,label=label)
        for g in layouts:
            r=subset.loc[g];labels.append(bg(r)+('  原对照' if r.category=='anchor' else '  新增'))
        ax.set_yticks(y,labels,fontsize=12);ax.invert_yaxis();ax.set_xlim(0,41)
        ax.set_ylabel('背景流（几何块）');ax.set_xlabel('带背景相对无背景的 RTT 增幅 (%)')
        ax.grid(axis='x',alpha=.18);ax.set_axisbelow(True)
        ax.axhline(5.5,color=GRAY,ls='--',alpha=.5)
        fig.legend(*ax.get_legend_handles_labels(),loc='outside upper center',ncol=2)
        save(fig,f'图{number}_路径补充方向{src}')


def model_errors():
    fig,axes=plt.subplots(1,2,figsize=(11.2,3.2),layout='constrained')
    names=['常数＋大小','XY','YX','联合 14 项']
    for ax,key,title in zip(axes,['background_layout_RMSE_pct_points','probe_direction_RMSE_pct_points'],['留出有向背景布局：23 折','留出整个探针方向：2 折']):
        bars=ax.bar(range(4),M[key],color=[GRAY,BLUE,GREEN,ORANGE],width=.6)
        ax.bar_label(bars,fmt='%.2f',padding=4,fontsize=12)
        ax.set_xticks(range(4),names,fontsize=11);ax.set_title(title);ax.set_ylabel('预测 RMSE (百分点)')
        ax.set_ylim(0,25);ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
    save(fig,'图16_路径补充模型留出误差')


def same_features():
    pairs=[['g0001','g0003'],['g0005','g0007'],['g0033','g0035']]
    fig,ax=plt.subplots(figsize=(11.2,3.15),layout='constrained')
    labels=[]
    for k,pair in enumerate(pairs):
        xs=[k*3,k*3+1];rs=S.loc[pair];mid=rs.effect_pct_median.to_numpy()
        ax.bar(xs,mid,color=[ORANGE,BLUE],width=.58)
        ax.errorbar(xs,mid,yerr=np.vstack([mid-rs.effect_pct_min,rs.effect_pct_max-mid]),fmt='none',ecolor='#333',capsize=4)
        for x,v in zip(xs,mid):ax.text(x,v+.8,f'{v:.2f}%',ha='center',fontsize=12)
        pred=P[(P.model=='combined_descriptive')&P.group.isin(pair)].sort_values('group').fitted.to_numpy()
        assert abs(pred[0]-pred[1])<1e-9
        ax.plot(xs,pred,color='#222222',ls='--',marker='D',ms=4,label='联合模型：相同特征给出相同预测' if k==0 else None)
        for g in pair:
            r=S.loc[g];labels.append(f'{int(r.probe_src)}→{int(r.probe_dst)}\n背景块 {bg(r)}')
    ax.set_xticks([k*3+j for k in range(3) for j in range(2)],labels,fontsize=11.5)
    ax.set_ylim(0,40);ax.set_ylabel('1 KiB 探针 RTT 增幅 (%)');ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
    fig.legend(*ax.get_legend_handles_labels(),loc='outside upper center')
    save(fig,'图17_路径特征相同但干扰不同')


def background():
    fig,ax=plt.subplots(figsize=(11.2,3.1),layout='constrained')
    for src,color,marker in [(0,BLUE,'o'),(54,ORANGE,'s')]:
        rows=S[(S.probe_src==src)&(S.probe_bytes==1024)]
        mid=rows.effect_pct_median.to_numpy()
        ax.errorbar(rows.bg_B_per_cycle_median,mid,yerr=np.vstack([mid-rows.effect_pct_min,rows.effect_pct_max-mid]),
                    fmt=marker,ls='none',color=color,capsize=3,label=f'探针 {src}→{54 if src==0 else 0}')
    for g in ['g0021','g0049','g0003','g0035']:
        r=S.loc[g]
        target={'g0021':(.956,32),'g0049':(.897,41),'g0003':(1.465,12),'g0035':(1.335,12)}[g]
        ax.annotate('背景块 '+bg(r),(r.bg_B_per_cycle_median,r.effect_pct_median),xytext=target,
                    fontsize=11,color='#333333',arrowprops=dict(arrowstyle='-',color=GRAY,lw=.8))
    ax.set_xlim(.86,1.56);ax.set_ylim(0,43);ax.set_xlabel('背景源期间平均吞吐 (B/cycle)')
    ax.set_ylabel('1 KiB 探针 RTT 增幅 (%)');ax.grid(alpha=.18);ax.set_axisbelow(True)
    fig.legend(*ax.get_legend_handles_labels(),loc='outside upper center',ncol=2)
    save(fig,'图18_路径补充背景速率')


def anchors():
    a=pd.DataFrame(D['anchors']);a=a[a.probe_bytes==1024]
    fig,ax=plt.subplots(figsize=(11.2,2.8),layout='constrained')
    xs=np.arange(len(a));ax.scatter(xs,a.change_pct_points,s=52,c=BLUE,zorder=3)
    ax.set_xticks(xs,[f'{r.probe_src}→{54 if r.probe_src==0 else 0}\n块 {r.background_src_block}→{r.background_dst_block}' for r in a.itertuples()],fontsize=11)
    ax.axhline(0,color='#555',ls='--');ax.set_ylim(-.46,.46)
    ax.set_ylabel('本轮减上一轮 (百分点)');ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
    save(fig,'图20_路径补充历史锚点')


def jobs():
    groups=['g0001','g0003','g0021','g0049','g0061']
    fig,ax=plt.subplots(figsize=(11.2,3.0),layout='constrained')
    for k,j in enumerate(D['jobs']):
        vals=[E[(E.repeat==j['repeat'])&(E.group==g)].effect_pct.iloc[0] for g in groups]
        ax.scatter(np.arange(len(groups))+(k-2)*.09,vals,s=38,label=j['job']+' / '+j['node'])
    ax.set_xticks(range(len(groups)),[f'{int(S.loc[g].probe_src)}→{int(S.loc[g].probe_dst)}\n背景块 {bg(S.loc[g])}' for g in groups],fontsize=12)
    ax.set_ylim(0,43);ax.set_ylabel('1 KiB 探针 RTT 增幅 (%)');ax.grid(axis='y',alpha=.18);ax.set_axisbelow(True)
    fig.legend(*ax.get_legend_handles_labels(),loc='outside upper center',ncol=3,fontsize=10)
    save(fig,'图19_路径补充逐作业重复')


if __name__=='__main__':
    directions();model_errors();same_features();background();anchors();jobs()
    # Remove only the four superseded, generated chart files from this operation.
    for stem in ('图19_路径补充历史锚点','图20_路径补充逐作业重复'):
        for suffix in ('.png','.svg'):
            p=FIG/(stem+suffix)
            assert p.parent.resolve()==FIG.resolve()
            if p.exists():p.unlink()
    print('Created 7 additional route figures (PNG and SVG).')
