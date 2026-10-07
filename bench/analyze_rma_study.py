"""Analyze recorded RMA suite data only; never build or execute the benchmark."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

CASES = ['single', 'intra2', 'split_near2', 'split_side2', 'split_far2',
         'incast3', 'ring4', 'alltoall4']
PAIRS = [(0,1),(0,8),(0,9),(1,2),(8,16),(9,18),(0,7),(0,56),(0,63)]
LABELS = ['同块横向 0→1','同块纵向 0→8','同块对角 0→9','跨块横向 1→2',
          '跨块纵向 8→16','跨块对角 9→18','远距离同行 0→7','远距离同列 0→56','远距离对角 0→63']

def member(c, i):
    return (c//4*2+i//2)*8+c%4*2+i%2

def flows(row):
    c = int(row.cluster_index)
    a,b,d,e = [member(c,i) for i in range(4)]
    name = row.case
    if row.type == 'bandwidth': return [(int(row.src),int(row.dst))]
    if name == 'single': return [(a,b)]
    if name == 'intra2': return [(a,b),(d,e)]
    if name.startswith('split_'):
        other = {'split_near2':c-4 if c//4==3 else c+4,
                 'split_side2':c-1 if c%4==3 else c+1,
                 'split_far2':((c//4+2)%4)*4+c%4}[name]
        return [(a,b),(member(other,0),member(other,1))]
    if name == 'incast3': return [(b,a),(d,a),(e,a)]
    if name == 'ring4': return [(a,b),(b,e),(e,d),(d,a)]
    if name == 'alltoall4': return [(s,t) for s in (a,b,d,e) for t in (a,b,d,e) if s!=t]
    raise ValueError(name)

def check_data(source):
    summary = pd.read_csv(source/'summary.csv')
    latency = pd.read_csv(source/'latency.csv')
    assert (summary.errors==0).all() and (latency.errors==0).all()
    assert (summary.max_cycles>0).all() and (latency.rtt_cycles>0).all()
    assert not summary.duplicated(['repeat','case_id']).any()
    assert not latency.duplicated(['repeat','case_id','initiator','peer']).any()
    np.testing.assert_allclose(summary.aggregate_bytes_per_cycle,
                               summary.bytes*summary.reps*summary.flows/summary.max_cycles,
                               rtol=0,atol=0.5001e-9)
    np.testing.assert_allclose(latency.latency_cycles,latency.rtt_cycles/(2*latency.reps),rtol=0,atol=0.5001e-6)
    records=[]; pe_rows=[]; case_sets=[]; order_sets=[]
    expected_pairs={(i,j) for i in range(64) for j in range(64) if i!=j}
    for repeat in (1,2,3):
        root=source/f'repeat_{repeat:02d}'
        assert (root/'COMPLETE').read_text().strip()=='validated_cases=566'
        assert (root/'RUN_COMPLETE').read_text().strip()=='completed_cases=566'
        plan=pd.read_csv(root/'plan.csv')
        assert len(plan)==566 and plan.case_id.is_unique
        assert (plan.iloc[:18].phase=='smoke').all() and (plan.iloc[18:].phase=='raw').all()
        case_sets.append(set(plan.case_id)); order_sets.append(list(plan.iloc[18:].case_id))
        assert len(list((root/'smoke').glob('*.csv')))==18
        assert len(list((root/'raw').glob('*.csv')))==548
        sub=summary[summary['repeat']==repeat].set_index('case_id')
        lat=latency[latency['repeat']==repeat]
        assert set(sub.index)|set(lat.case_id)==set(plan.case_id)
        for row in plan.itertuples(index=False):
            path=root/row.phase/(row.case_id+'.csv')
            raw=pd.read_csv(path)
            assert (raw.errors==0).all(), str(path)
            if row.type=='latency':
                assert len(raw)==4032
                assert set(zip(raw.initiator,raw.peer))==expected_pairs
                assert (raw.bytes==row.bytes).all() and (raw.reps==row.reps).all()
                a=raw.initiator.to_numpy(); b=raw.peer.to_numpy()
                np.testing.assert_array_equal(raw.same_cluster, (a//8//2==b//8//2)&(a%8//2==b%8//2))
                np.testing.assert_array_equal(raw.row_distance,abs(a//8-b//8))
                np.testing.assert_array_equal(raw.col_distance,abs(a%8-b%8))
                saved=lat[lat.case_id==row.case_id].sort_values(['initiator','peer'])
                assert (saved.phase==row.phase).all()
                assert (raw.benchmark=='rma_pingpong').all()
                columns=[c for c in raw.columns if c!='benchmark']
                pd.testing.assert_frame_equal(raw[columns].reset_index(drop=True),saved[columns].reset_index(drop=True))
            else:
                edges=flows(row); active=set(sum(([a,b] for a,b in edges),[]))
                assert len(raw)==len(active)+1
                assert set(raw[raw.pe!='aggregate'].pe.astype(int))==active
                assert (raw.flows==len(edges)).all() and (raw['case']==row.case).all()
                for col in ('bytes','reps','window','cluster_index'):
                    assert (raw[col]==getattr(row,col)).all()
                p=raw[raw.pe!='aggregate'].copy(); agg=raw[raw.pe=='aggregate'].iloc[0]
                assert (p.cycles>0).all() and agg.cycles==p.cycles.max()
                saved=sub.loc[row.case_id]
                assert saved.phase==row.phase and saved.max_cycles==agg.cycles
                assert abs(saved.aggregate_bytes_per_cycle-agg.aggregate_bytes_per_cycle)<1e-12
                if row.phase=='raw':
                    p['repeat']=repeat; p['case_id']=row.case_id
                    p['type']=row.type; p['src']=row.src; p['dst']=row.dst
                    p['cycles_per_payload_round']=p.cycles/row.reps
                    pe_rows.append(p)
            records.append({'path':str(path.relative_to(source)), 'sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    assert case_sets[0]==case_sets[1]==case_sets[2]
    assert order_sets[0]!=order_sets[1] and order_sets[1]!=order_sets[2]
    assert len(summary)==1677 and len(latency)==84672
    return summary[summary.phase=='raw'].copy(),latency[latency.phase=='raw'].copy(),pd.concat(pe_rows),records

def aggregate(df, keys, value):
    result=df.groupby(keys)[value].agg(['median','min','max','std']).reset_index()
    result['range_pct']=(result['max']-result['min'])/result['median']*100
    return result

def table(df, columns=None, digits=3):
    df=df[columns] if columns else df
    lines=['| '+' | '.join(map(str,df.columns))+' |','| '+' | '.join(['---']*len(df.columns))+' |']
    for row in df.itertuples(index=False,name=None):
        lines.append('| '+' | '.join(f'{x:.{digits}f}' if isinstance(x,(float,np.floating)) else str(x) for x in row)+' |')
    return '\n'.join(lines)

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('source',type=Path); parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--stats-only',action='store_true'); parser.add_argument('--plots-only',action='store_true')
    parser.add_argument('--report-only',action='store_true')
    args=parser.parse_args(); out=args.out; out.mkdir(parents=True,exist_ok=True)
    (out/'figures').mkdir(exist_ok=True); (out/'tables').mkdir(exist_ok=True)
    if args.report_only:
        make_report(out,args.source); return
    if args.plots_only:
        lm=pd.read_csv(out/'tables/latency_repeats.csv'); bw=pd.read_csv(out/'tables/bandwidth_repeats.csv')
        make_figures(out,lm,bw,bw[bw.type=='contention'],pd.read_csv(out/'tables/paired_contention_ratios.csv'),pd.read_csv(out/'tables/models.csv'))
        return
    s,l,p,audit=check_data(args.source)
    pd.DataFrame(audit).to_csv(out/'tables/raw_file_audit.csv',index=False)
    p.to_csv(out/'tables/active_pe_timings.csv',index=False)
    keys=['type','case','src','dst','bytes','window','cluster_index']
    bw=aggregate(s,keys,'aggregate_bytes_per_cycle')
    lm=aggregate(l,['bytes','initiator','peer','same_cluster','row_distance','col_distance'],'latency_cycles')
    lm['cross']=1-lm.same_cluster
    lm['hx']=lm.col_distance; lm['hy']=lm.row_distance
    lm['bx']=abs((lm.initiator%8)//2-(lm.peer%8)//2)
    lm['by']=abs(lm.initiator//16-lm.peer//16)
    lm['other_row']=(lm.hy!=0).astype(int); lm['other_col']=(lm.hx!=0).astype(int)
    bw.to_csv(out/'tables/bandwidth_repeats.csv',index=False)
    lm.to_csv(out/'tables/latency_repeats.csv',index=False)
    stats=lm.groupby('bytes')['median'].agg(['min','median','mean','max'])
    stats.to_csv(out/'tables/latency_sizes.csv')
    local=lm.groupby(['bytes','same_cluster'])['median'].agg(['count','min','median','mean','max']).reset_index()
    local.to_csv(out/'tables/local_vs_remote_latency.csv',index=False)
    adjacent=lm[(lm.hx+lm.hy)==1].groupby(['bytes','same_cluster','row_distance'])['median'].agg(['count','min','median','mean','max']).reset_index()
    adjacent.to_csv(out/'tables/adjacent_boundary_latency.csv',index=False)
    representative=lm[(lm.initiator.astype(str)+'-'+lm.peer.astype(str)).isin([f'{a}-{b}' for a,b in PAIRS])]
    representative=representative.pivot(index=['initiator','peer'],columns='bytes',values='median').reindex(PAIRS)
    representative.to_csv(out/'tables/representative_latency.csv')
    models={'size':['bytes'],'size_cluster':['bytes','cross'],'size_mesh':['bytes','hx','hy'],
            'size_cluster_mesh':['bytes','cross','hx','hy'],
            'size_block_distance':['bytes','bx','by'],
            'size_cluster_block':['bytes','cross','bx','by'],
            'size_rowcol':['bytes','other_row','other_col']}
    fitted=[]
    # Model held-out samples group both directions and every size of a pair.
    low=np.minimum(lm.initiator,lm.peer); high=np.maximum(lm.initiator,lm.peer)
    fold=(low*17+high)%5
    for scope,frame in [('all',lm),('8B',lm[lm.bytes==8])]:
        y=frame['median'].to_numpy()
        for name,features in models.items():
            fs=[f for f in features if scope=='all' or f!='bytes']
            X=np.column_stack([np.ones(len(frame))]+[frame[f].to_numpy() for f in fs])
            coef=np.linalg.lstsq(X,y,rcond=None)[0]; predicted=X@coef
            heldout=np.empty(len(frame))
            ff=fold.loc[frame.index].to_numpy()
            for k in range(5):
                train=ff!=k; test=~train
                heldout[test]=X[test]@np.linalg.lstsq(X[train],y[train],rcond=None)[0]
            fitted.append({'scope':scope,'model':name,'parameters':len(coef),
                'r2':1-np.sum((y-predicted)**2)/np.sum((y-y.mean())**2),
                'rmse_cycles':np.sqrt(np.mean((y-predicted)**2)),
                'cv_rmse_cycles':np.sqrt(np.mean((y-heldout)**2)),
                'coefficients':json.dumps(dict(zip(['alpha']+fs,coef.tolist())))})
    models_df=pd.DataFrame(fitted); models_df.to_csv(out/'tables/models.csv',index=False)
    cont=bw[bw.type=='contention'].copy()
    contwide=cont.pivot(index=['bytes','window','cluster_index'],columns='case',values='median')
    ratio_records=[]
    perrepeat=s[s.type=='contention'].pivot(index=['repeat','bytes','window','cluster_index'],columns='case',values='aggregate_bytes_per_cycle')
    for split in ['split_near2','split_side2','split_far2']:
        ratios=(perrepeat[split]/perrepeat.intra2).rename('split_over_intra').reset_index()
        ratios['split_case']=split; ratio_records.append(ratios)
    ratios=pd.concat(ratio_records); ratios.to_csv(out/'tables/paired_contention_ratios.csv',index=False)
    efficiency=contwide.div(contwide.single,axis=0)
    for case in CASES: efficiency[case]/={'single':1,'intra2':2,'split_near2':2,'split_side2':2,'split_far2':2,'incast3':3,'ring4':4,'alltoall4':12}[case]
    efficiency.to_csv(out/'tables/contention_scaling_efficiency.csv')
    repeatstats=pd.DataFrame([{'metric':name,'configurations':len(frame),'median_range_pct':frame.range_pct.median(),
                              'p90_range_pct':frame.range_pct.quantile(.9),'max_range_pct':frame.range_pct.max()}
                             for name,frame in [('latency',lm),('bandwidth_pair',bw[bw.type=='bandwidth']),('contention',cont)]])
    repeatstats.to_csv(out/'tables/repeat_variation.csv',index=False)
    skew=[]
    for size,frame in lm.groupby('bytes'):
        mat=frame.pivot(index='initiator',columns='peer',values='median').to_numpy()
        diff=abs(mat-mat.T); finite=diff[np.isfinite(diff)]
        skew.append({'bytes':size,'median_reverse_difference_cycles':np.median(finite),'max_reverse_difference_cycles':np.max(finite)})
    pd.DataFrame(skew).to_csv(out/'tables/pingpong_reverse_difference.csv',index=False)
    important={'latency_size_stats':stats.to_dict(),'adjacent':adjacent.to_dict('records'),
               'repeat_variation':repeatstats.to_dict('records'),
               'representative_latency':representative.reset_index().to_dict('records'),
               'models':models_df.to_dict('records'),
               'contention':contwide.reset_index().to_dict('records'),
               'ratios':ratios.groupby(['bytes','window','split_case']).split_over_intra.agg(['min','median','max']).reset_index().to_dict('records'),
               'best_pair_bw':bw[bw.type=='bandwidth'].sort_values('median',ascending=False).head(10).to_dict('records')}
    (out/'analysis.json').write_text(json.dumps(important,ensure_ascii=False,indent=2),encoding='utf-8')
    print('VALIDATED: 1698 raw files; all repeats, geometry, rows, aggregate timing and merged CSV match.')
    print('Adjacent 8B:'); print(adjacent[adjacent.bytes==8].to_string(index=False))
    print('Representative latency:'); print(representative.to_string())
    print('Models 8B:'); print(models_df[models_df.scope=='8B'].to_string(index=False))
    print('Repeat ranges:'); print(repeatstats.to_string(index=False))
    print('Contention ratios:'); print(ratios.groupby(['bytes','window','split_case']).split_over_intra.agg(['min','median','max']).to_string())
    make_report(out,args.source)
    if not args.stats_only: make_figures(out,lm,bw,cont,ratios,models_df)

def make_report(out,source):
    lm=pd.read_csv(out/'tables/latency_repeats.csv')
    bw=pd.read_csv(out/'tables/bandwidth_repeats.csv')
    variation=pd.read_csv(out/'tables/repeat_variation.csv')
    models=pd.read_csv(out/'tables/models.csv')
    ratios=pd.read_csv(out/'tables/paired_contention_ratios.csv')
    cont=bw[bw.type=='contention']
    latency_sizes=pd.read_csv(out/'tables/latency_sizes.csv')
    reps=pd.read_csv(source/'summary.csv'); reps=reps[(reps.phase=='raw')&(reps.type=='contention')]
    # Each ratio is paired within one submitted job and one block, before summarizing.
    ratio_blocks=ratios.groupby(['bytes','window','cluster_index','split_case']).split_over_intra.agg(['min','median','max']).reset_index()
    ratio_blocks.to_csv(out/'tables/contention_ratios_by_block.csv',index=False)
    wide=cont.pivot(index=['bytes','window','cluster_index'],columns='case',values='median').reset_index()
    wide.to_csv(out/'tables/contention_by_block.csv',index=False)
    print('Contention by block:\n'+wide.to_string(index=False))
    print('Largest repeat variations:\n'+cont.sort_values('range_pct',ascending=False).head(6).to_string(index=False))
    audit=pd.read_csv(out/'tables/raw_file_audit.csv')
    hashes=audit[audit.path.str.replace('\\','/',regex=False).str.contains('/raw/latency_')].copy()
    hashes['file']=hashes.path.map(lambda x:Path(x).name)
    checks=hashes.groupby('file').sha256.nunique()
    assert len(checks)==6
    assert (checks==1).all()
    hashes.to_csv(out/'tables/repeated_latency_file_hashes.csv',index=False)
    cpu=[]
    for i in (1,2,3):
        text=(source/f'repeat_{i:02d}/resource_runtime.txt').read_text()
        cpu.append({line.split('=',1)[0]:line.split('=',1)[1] for line in text.splitlines() if '=' in line})
    adjacent=pd.read_csv(out/'tables/adjacent_boundary_latency.csv')
    eight=lm[lm.bytes==8]
    local=eight[eight.same_cluster==1]['median']
    remote=eight[eight.same_cluster==0]['median']
    pairs=bw[bw.type=='bandwidth']
    pairtable=pairs[(pairs.src==0)&(pairs.dst==1)].pivot(index='bytes',columns='window',values='median')
    pairtable.to_csv(out/'tables/pair_0_1_bandwidth.csv')
    windowgain=pairtable[16]/pairtable[1]
    best=pairs.loc[pairs['median'].idxmax()]
    spread=pairs.groupby(['bytes','window'])['median'].agg(['min','max'])
    spread['spread_pct']=(spread['max']/spread['min']-1)*100
    spread.to_csv(out/'tables/pair_spatial_bandwidth_spread.csv')
    representative=pd.read_csv(out/'tables/representative_latency.csv')
    groups=ratios.groupby(['bytes','window','split_case']).split_over_intra.agg(['min','median','max']).reset_index()
    aggregate=cont.groupby(['bytes','window','case'])['median'].median().unstack().reindex(columns=CASES)
    intrarepeats=reps[(reps['case']=='intra2')&(reps.bytes==1024)&(reps.window==1)].pivot(index='cluster_index',columns='repeat',values='aggregate_bytes_per_cycle')
    intrarepeats.to_csv(out/'tables/intra2_1024B_W1_by_repeat.csv')
    efficiency=pd.read_csv(out/'tables/contention_scaling_efficiency.csv')
    model8=models[models.scope=='8B'].copy()
    model8['model']=model8.model.map({'size':'常数','size_cluster':'跨块指示量','size_mesh':'单核坐标距离',
        'size_cluster_mesh':'跨块＋单核距离','size_block_distance':'小簇坐标距离',
        'size_cluster_block':'跨块＋小簇距离','size_rowcol':'是否同行/同列'})
    contents=f'''# SW39000 RMA 微基准结果分析

数据目录：`{source.name}`。以下性能统计只使用 `phase=raw`，先对同一配置取三次作业中位数。

## 1. 主要结果

1. **小消息延迟出现可测的 2×2 几何边界。**8 B 同块的 192 个有向核对全部为 {local.median():.3f} cycles。核距同为一格时，同块相邻为 98.002 cycles，跨块相邻的中位数为 102.0025 cycles，增加约 4.0005 cycles（4.08%）。这控制了单核 Manhattan 距离，较直接地支持 2×2 分块与延迟的关联。
2. **距离效应主要体现在小簇坐标尺度。**8 B 用小簇行列距离拟合的 R²=0.9649，核对分组交叉验证 RMSE=1.067 cycles；单核行列距离模型 R²=0.8314、RMSE=2.339 cycles。数据支持在描述性延迟模型中保留小簇层次，但没有直接测量物理路由。
3. **点对点带宽差异很小。**九个核对在 64 KiB、W=1 时均为 24.499 B/cycle；测试范围内最高中位数约 {best['median']:.3f} B/cycle。同块、跨块和远距离在这组带宽测试中没有明显惩罚。
4. **窗口带来的增益比核对位置差异大。**0→1，1024 B 从 W=1 的 {pairtable.loc[1024,1]:.3f} 增至 W=16 的 {pairtable.loc[1024,16]:.3f} B/cycle，约 {windowgain.loc[1024]:.2f} 倍。
5. **本轮没有出现分散两条流后吞吐成倍恢复的现象。**W=4、1024 B 时，分散/同块带宽比中位数接近 1；W=1 的 1024 B 有位置相关差异，不能仅用跨位置汇总的约 2.1% 增益概括全部小簇。

## 2. 平台、测试范围和数据核对

| 项目 | 本次记录 |
|---|---|
| CPU | `/proc/cpuinfo`：sw39000 |
| 编译器 | swgcc/1473；target=sw_64sw6a-sunway-linux-gnu |
| 三次计算节点 | {', '.join(x.get('compute_hostname','unknown') for x in cpu)} |
| 作业 | 8433994、8433995、8433997，顺序提交，正式配置顺序打乱 |
| 资源请求 | 1 MPE、1 CG、64 CPE；cache=0 KiB |
| 实际独占、共享 LDM、实际 cache/LDM | 未确认，q_share 名称不能证明 |
| 缓冲容量 | 两个 RMA LDM 缓冲各 65536 B；静态 LDM 133736 B 告警 |
| 频率记录 | spe=2250 MHz，mpe=2100 MHz；RMA 计数器频率未独立标定 |
| 正式配置 | 每次 548 项，三次共 1644 项；另有每次 18 项 smoke |

已逐文件核对 1698 个原始 CSV：检查行数、完整核对集合、几何分类、活跃核集合、错误数，以及原始数据与顶层汇总的一致性。4032 个非自身有向核对×6 种大小×3 次=**72576 条正式延迟记录**；542 项带宽/争用配置×3 次=**1626 条正式聚合记录**。所有现有校验的 errors 为 0，计时为正，聚合指标与逐核最大耗时一致。

正确性检查等待 reply 并检查最终缓冲，源数据模式每 256 B 重复。它不能证明每次中间传输的每个字节均已验证。报告保留 cycles 和 B/cycle；不把 cpuinfo 的 2250 MHz 直接当作已校准计数器频率，也不把 linux 的 timer frequency=100 Hz 当作 CPE 计数器频率。

### 测量定义

- **延迟**：4 次预热后计时 2000 次 ping-pong，L=总 RTT 周期/(2×2000)，包括 RMA 接口、reply 等待和对端响应。阵列 barrier 在计时外。RTT/2 混合两个方向的性能，不能作为纯单向链路延迟。
- **带宽**：RMA iput；一轮预热后，每条流传输 2000 次。BW=bytes×reps×flows/活跃核最大周期数。包含发起循环、本地和远端完成等待。多流各核计时区始于共同 barrier 后，但读取本核周期差，取最大周期差不等同于跨核同步测得全局墙钟跨度。
- **窗口**：每条流每批发起 W 次，再等本地完成；独立窗口槽在下一批复用。alltoall4 每核有 3 条出流，最多 3W 个请求；目标为各入流分配独立 lane。每个目标满足 bytes×W×入流数≤65536。
- **几何**：id=8r+c，簇编号=4 floor(r/2)+floor(c/2)。此处“同块/跨块”是几何分组；router、共享管理部件和物理跳数未直接观测。

## 3. 延迟矩阵和小簇边界

### 3.1 全矩阵与多源热图

![8 B 延迟全矩阵](figures/01_latency_matrix.png)

左图保持核 ID 顺序，右图把同一 2×2 块的四核放在一起。自身通信留白。每个像素是该有向核对三次作业中位数，而不是行/列平均值。

![多源热图](figures/02_source_heatmaps.png)

六个源核使用同一色标。白线标出几何块界。源位于不同位置时，低延迟区随源的几何小簇移动；较远位置总体耗时增加。

### 3.2 固定单核距离的一格边界对照

{table(adjacent[adjacent.bytes==8],digits=4)}

same_cluster=1 为同块，0 为跨块；row_distance=0 为横向，1 为纵向。count 是不同有向核对数，不是独立作业数。每核对先取三次中位数。

同块相邻横向和纵向均为 98.002 cycles。跨块相邻两类的中位数相同，为 102.0025 cycles，但均值与最大值不同，说明不同边界位置仍有差异。跨块样本最高到 105.002 cycles，不能给所有边界统一指定 4-cycle 的精确代价。

8 B 全部跨块核对的中位数为 {remote.median():.3f} cycles。这包含更远距离，不能直接将其与同块的差值解释成纯边界惩罚。

![延迟消息大小与边界对照](figures/03_latency_boundary_sizes.png)

左图阴影表示不同核对三次中位数的空间最小值至最大值，不是独立重复的误差区间。

### 3.3 消息大小与代表核对

{table(latency_sizes)}

上表分布来自 4032 个核对的三次中位数。8～32 B 整体分布接近；64～256 B 逐步上升。代表核对如下，单位为 cycles：

{table(representative,digits=3)}

0→1、0→8、0→9 在 8 B 下均为 98.002 cycles，同块对角也没有额外代价。1→2 为 102.003；9→18 为 105.506；0→7、0→56、0→63 分别为 109.002、112.002、123.002 cycles。行列不能完全互换。个别核对在增大消息后耗时反而稍降，例如 8→16 的 32 B 为 105.002、64 B 为 102.006；这说明简单的统一 α+βS 不会精确解释每个测点，不能把变化直接换算成负的字节传输代价。

## 4. 点对点带宽和请求窗口

![带宽曲线](figures/04_bandwidth_curves.png)

左图仅 W=1，右图给出 0→1 的窗口曲线。只画实际运行过的容量合法配置，64 KiB 没有 W>1 测点。曲线重叠是数据现象，没有为了展示而人为错开。

0→1 的三次中位数如下，单位 B/cycle。空白表示容量限制下未测量：

{table(pairtable.reset_index().fillna('未测'),digits=4)}

64 KiB、W=1 九个核对均为 24.499247 B/cycle。九个核对在相同消息与窗口下的最大空间差异为 {spread.spread_pct.max():.3f}%，与小消息延迟约 4-cycle 的边界差异形成两种不同测量结果。点对点曲线不能直接外推为全 CG 或全芯片理论总带宽。

![窗口扫描](figures/05_windows.png)

8 B 的 W=1→16 增益为 {windowgain.loc[8]:.3f} 倍，1024 B 为 {windowgain.loc[1024]:.3f} 倍。4096 B 的窗口同样提高吞吐。窗口增大把发起/等待开销分摊到多次传输，但当前窗口有限，数据不能单独确定硬件队列深度或绝对 outstanding 上限。

## 5. 小簇争用与流量分散

A/B/C/D 为 2×2 块中左上、右上、左下、右下。single：A→B；intra2：A→B 与 C→D；split 三类：两条流分别位于不同块内部；incast3：B/C/D→A；ring4：A→B→D→C→A；alltoall4：四核之间 12 条有向流。split 不是一条跨块流，与跨块单流核对测试的意义不同。

![争用模式对照](figures/06_contention.png)

以下表先对各配置取三次中位数，再跨四个块取中位数，单位 B/cycle。它用于概览，不把 4 个位置当作增加的独立作业重复：

{table(aggregate.reset_index(),digits=4)}

两条流相对 single 不达到理想的 2 倍，例如 1024 B、W=4 时 single≈11.974、intra2≈18.785，为约 1.569 倍。但是分散流量也约为 18.785，说明“两条流缩放不足”本身不能归因于同一小簇 router 独有的共享瓶颈。发起循环、端点路径或更大范围共享资源都可能参与，当前数据不能将它们分开。

### 5.1 同块两条流与不同块两条流

![分散与同块带宽比](figures/07_split_vs_intra.png)

每个比值先匹配同一作业、大小、W 和起始块，再计算 split/intra2。下表的 min/max 跨三次与四个位置共 12 个配对比值，**不是置信区间**：

{table(groups,digits=6)}

64 B、W=1 分散约快 0.38%；1024 B、W=1 的汇总中位数约快 2.1%，范围从略低于 1 到约 1.044。W=4、1024 B 的中位数接近 1.0000，部分重复略低。应保留位置与重复，不应把约 2.1% 写成所有小簇的一致收益。

下表保留 1024 B、W=1 的逐块绝对带宽，单位 B/cycle：

{table(wide[(wide.bytes==1024)&(wide.window==1)].drop(columns=['bytes','window']),digits=6)}

intra2 存在约 10.899 和 11.376 B/cycle 两个观测水平；同一块在不同作业中也可能切换，不能将跨位置差异完全看作固定空间结构。下面保留每次作业的数据：

{table(intrarepeats.reset_index(),digits=6)}

split 三类较接近。原始逐核耗时已保存到 `tables/active_pe_timings.csv`；这些模式同时改变端点位置和流组合，不能仅从吞吐比反推出一个物理 router 的端口结构。

### 5.2 incast、ring、all-to-all

在 1024 B、W=4 的跨块位置概览中，incast3≈22.490、ring4≈22.801、alltoall4≈23.948 B/cycle。alltoall4 的流数为 12，不是 4；其吞吐约为 single 的 2 倍，远低于理想 12 倍。各模式的端点复用、发起循环次数和每核 outstanding 数也不同，不能将这些比值当作严格只改变流数的等条件扩展实验。

## 6. 重复性与描述模型

### 6.1 三次观测的变化

range_pct=(最大值−最小值)/中位数×100%，统计单位是匹配配置。延迟匹配每个大小和有向核对，带宽匹配所有计划参数。

{table(variation,digits=6)}

六个大小的正式延迟矩阵在三次作业中不仅数值相同，原始文件 SHA-256 也分别完全相同（每种大小的唯一哈希数均为 1）。这是输入文件中的事实。它使这批数据无法提供非零的作业间延迟散布估计，不能据此证明单次测量无噪声或所有机器都稳定。三次均在 vn024481，且提交紧邻，只代表该节点这一短时间范围。

点对点带宽匹配配置的跨作业极差很小。争用的最大跨作业极差约 4.374%，因此要同时查看逐块和逐次结果。最大波动的配置见下表：

{table(cont.sort_values('range_pct',ascending=False).head(6),['case','bytes','window','cluster_index','median','min','max','range_pct'],digits=6)}

### 6.2 8 B 模型对照

定义 hx=|cs−cd|，hy=|rs−rd|；bx=|floor(cs/2)−floor(cd/2)|，by=|floor(rs/2)−floor(rd/2)|。bx/by 是小簇坐标距离，不能未经验证称作物理 hop。cross=不同小簇指示量。

{table(model8,['model','parameters','r2','rmse_cycles','cv_rmse_cycles'],digits=4)}

对 4032 个有向核对的三次中位数做最小二乘拟合。交叉验证按无向核对划为五折，同一核对的两方向及所有大小留在同一折；它测试留出核对的预测误差，不是跨节点验证。所有模型细节及 6 种大小联合线性模型保存在 `tables/models.csv`。

小簇坐标距离模型：

```text
L_8B ≈ 98.480 + 3.965 bx + 4.355 by       (cycles)
```

加入跨块指示量后：

```text
L_8B ≈ 98.002 + 0.611 cross + 3.924 bx + 4.315 by
```

后者 RMSE≈1.060 cycles，比前者≈1.067 改善很小。只用 cross 的模型解释力很弱（R²≈0.188），因为它把所有跨块远近关系压成同一类。最有用的结构描述是小簇坐标尺度上的距离，加上近端基线；单个固定的“跨簇惩罚”不足以描述完整矩阵。

![模型对照](figures/08_model_comparison.png)

## 7. 对“小簇是否应进入模型”的回答

**延迟层面有数据依据。**同核距的边界对照、随源移动的热图和小簇距离模型共同支持显式保留 2×2 几何层次。可从约 98-cycle 的同块小消息基线和以小簇坐标计算的距离项开始描述本次测量。

**带宽和共享资源层面的证据较弱。**九个代表核对的大消息吞吐接近，分散两条流没有带来明显的大幅恢复。可报告 W=1 条件下的小幅位置差异及 W=4 近乎相同的结果；不能把“文档中的共享部件”直接变成一个本次已确认的强带宽瓶颈。

**物理片上通信路径尚未确定。**这些 microbenchmark 约束了成本随几何距离、消息大小、窗口和流组合如何变化，未观测实际路由或端口。报告中的模型是本机、本内核和本次配置下的经验描述。

## 8. 图表和数据依据

- `figures/`：8 张 PNG 大图及 SVG 矢量图。
- `tables/latency_repeats.csv`：全部核对的三次中位数、最小、最大、极差。
- `tables/bandwidth_repeats.csv`：全部带宽与争用配置的三次统计。
- `tables/paired_contention_ratios.csv`、`contention_ratios_by_block.csv`：逐作业配对及逐块对照。
- `tables/models.csv`：描述模型系数和留出预测误差。
- `tables/raw_file_audit.csv`：逐原始 CSV 的 SHA-256；源结果文件未修改。

分析依据包括顶层 summary.csv/latency.csv、各 repeat 的 plan.csv、全部 raw/smoke CSV、资源记录、build_info.txt 及随结果保存的主从核源码。
'''
    (out/'SW39000_RMA结果分析.md').write_text(contents,encoding='utf-8')

def make_figures(out,lm,bw,cont,ratios,models):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    for name in ['Microsoft YaHei','SimHei','Noto Sans CJK SC']:
        if name in {f.name for f in font_manager.fontManager.ttflist}:
            plt.rcParams['font.sans-serif']=[name,'DejaVu Sans']; break
    plt.rcParams.update({'font.size':13,'axes.titlesize':16,'axes.labelsize':14,'axes.unicode_minus':False})
    def save(fig,name):
        fig.savefig(out/'figures'/f'{name}.png',dpi=170,bbox_inches='tight')
        fig.savefig(out/'figures'/f'{name}.svg',bbox_inches='tight'); plt.close(fig)
    eight=lm[lm.bytes==8]
    matrix=eight.pivot(index='initiator',columns='peer',values='median').reindex(index=range(64),columns=range(64)).to_numpy()
    fig,axes=plt.subplots(1,2,figsize=(17,7),layout='constrained')
    order=[member(c,i) for c in range(16) for i in range(4)]
    for ax,mat,title in zip(axes,[matrix,matrix[np.ix_(order,order)]],['原核 ID 顺序','按几何 2×2 块重排，每块 4 核']):
        im=ax.imshow(mat,vmin=98,vmax=124,cmap='viridis',origin='upper',interpolation='nearest')
        ax.set_title(title); ax.set_xlabel('目标核 / 重排后序号'); ax.set_ylabel('发起核 / 重排后序号')
        if ax==axes[1]:
            for edge in np.arange(3.5,63,4): ax.axhline(edge,color='white',lw=.35,alpha=.5); ax.axvline(edge,color='white',lw=.35,alpha=.5)
    fig.colorbar(im,ax=axes,label='RTT/2 (cycles)',shrink=.9)
    fig.suptitle('8 B 延迟矩阵：每个核对取三次作业中位数；自身通信留白',fontsize=18)
    save(fig,'01_latency_matrix')
    fig,axes=plt.subplots(2,3,figsize=(16,10),layout='constrained')
    for src,ax in zip([0,9,18,27,36,63],axes.flat):
        mat=matrix[src].reshape(8,8)
        im=ax.imshow(mat,vmin=98,vmax=124,cmap='viridis')
        ax.set_title(f'源核 {src} = ({src//8},{src%8})'); ax.set_xticks(range(8)); ax.set_yticks(range(8))
        ax.set_xlabel('目标列'); ax.set_ylabel('目标行')
        for r in range(8):
            for c in range(8):
                v=mat[r,c]
                ax.text(c,r,'自身' if np.isnan(v) else f'{v:.1f}',ha='center',va='center',fontsize=10,color='black' if v>111 or np.isnan(v) else 'white')
        for edge in [1.5,3.5,5.5]: ax.axhline(edge,color='white',lw=1); ax.axvline(edge,color='white',lw=1)
    fig.colorbar(im,ax=list(axes.flat),label='RTT/2 (cycles)',shrink=.85)
    fig.suptitle('8 B 多源边界扫描；白线标出几何 2×2 分块',fontsize=18)
    save(fig,'02_source_heatmaps')
    fig,axes=plt.subplots(1,2,figsize=(16,6),layout='constrained')
    adjacent=lm[(lm.hx+lm.hy)==1]
    for same,label,color in [(1,'同块相邻','tab:blue'),(0,'跨块相邻','tab:orange')]:
        frame=adjacent[adjacent.same_cluster==same].groupby('bytes')['median'].agg(['min','median','max'])
        axes[0].plot(frame.index,frame['median'],'o-',label=label,color=color)
        axes[0].fill_between(frame.index,frame['min'],frame['max'],alpha=.15,color=color)
    axes[0].set_xscale('log',base=2); axes[0].set_xticks([8,16,32,64,128,256],labels=['8','16','32','64','128','256'])
    axes[0].set_xlabel('消息大小 (B)'); axes[0].set_ylabel('RTT/2 (cycles)'); axes[0].legend(); axes[0].set_title('相同 Manhattan 距离=1 的边界对照')
    for (a,b),label in zip(PAIRS,LABELS):
        row=lm[(lm.initiator==a)&(lm.peer==b)].sort_values('bytes')
        axes[1].plot(row.bytes,row['median'],'o-',label=label,ms=4)
    axes[1].set_xscale('log',base=2); axes[1].set_xlabel('消息大小 (B)'); axes[1].set_ylabel('RTT/2 (cycles)'); axes[1].set_title('9 个代表核对'); axes[1].legend(fontsize=9,ncol=2)
    axes[1].set_xticks([8,16,32,64,128,256],labels=['8','16','32','64','128','256'])
    for ax in axes: ax.grid(alpha=.2)
    save(fig,'03_latency_boundary_sizes')
    pairs=bw[bw.type=='bandwidth']
    fig,axes=plt.subplots(1,2,figsize=(16,6),layout='constrained')
    for (a,b),label in zip(PAIRS,LABELS):
        frame=pairs[(pairs.src==a)&(pairs.dst==b)&(pairs.window==1)].sort_values('bytes')
        axes[0].plot(frame.bytes,frame['median'],'o-',label=label,ms=4)
    axes[0].set_xscale('log',base=2); axes[0].set_title('W=1，9 个核对曲线基本重合'); axes[0].legend(fontsize=9,ncol=2)
    for w in [1,2,4,8,16]:
        frame=pairs[(pairs.src==0)&(pairs.dst==1)&(pairs.window==w)].sort_values('bytes')
        axes[1].plot(frame.bytes,frame['median'],'o-',label=f'W={w}')
        axes[1].fill_between(frame.bytes,frame['min'],frame['max'],alpha=.1)
    axes[1].set_xscale('log',base=2); axes[1].set_title('0→1 的窗口扫描；阴影为三次最小至最大'); axes[1].legend()
    for ax in axes:
        ax.set_xticks([8,64,256,1024,4096,16384,65536],labels=['8 B','64 B','256 B','1 KiB','4 KiB','16 KiB','64 KiB'])
        ax.set_xlabel('消息大小'); ax.set_ylabel('payload 带宽 (B/cycle)'); ax.grid(alpha=.2)
    save(fig,'04_bandwidth_curves')
    fig,axes=plt.subplots(1,3,figsize=(17,6),layout='constrained')
    for size,ax in zip([8,1024,4096],axes):
        for (a,b),label in zip(PAIRS,LABELS):
            frame=pairs[(pairs.src==a)&(pairs.dst==b)&(pairs.bytes==size)].sort_values('window')
            ax.plot(frame.window,frame['median'],'o-',label=label)
        ax.set_title(f'{size} B'); ax.set_xlabel('每条流窗口 W'); ax.set_ylabel('payload 带宽 (B/cycle)'); ax.set_xscale('log',base=2); ax.set_xticks([1,2,4,8,16],labels=['1','2','4','8','16']); ax.grid(alpha=.2)
    axes[2].legend(fontsize=9)
    fig.suptitle('增加未完成请求窗口提高小、中消息吞吐',fontsize=18)
    save(fig,'05_windows')
    fig,axes=plt.subplots(2,2,figsize=(17,10),layout='constrained')
    for ax,(size,w) in zip(axes.flat,[(64,1),(64,4),(1024,1),(1024,4)]):
        frame=cont[(cont.bytes==size)&(cont.window==w)]
        xx=np.arange(len(CASES)); width=.18
        for j,c in enumerate([0,5,10,15]):
            rr=frame[frame.cluster_index==c].set_index('case').reindex(CASES)
            ax.bar(xx+(j-1.5)*width,rr['median'],width,label=f'块 {c}',yerr=np.vstack([rr['median']-rr['min'],rr['max']-rr['median']]),capsize=2)
        ax.set_xticks(xx,CASES,rotation=30,ha='right',fontsize=10); ax.set_ylabel('聚合 payload 带宽 (B/cycle)'); ax.set_title(f'{size} B，W={w}'); ax.grid(axis='y',alpha=.2)
    axes[0,0].legend(ncol=4,fontsize=11)
    fig.suptitle('8 种争用模式；柱高为三次中位数，误差线为最小至最大',fontsize=18)
    save(fig,'06_contention')
    fig,axes=plt.subplots(1,2,figsize=(16,6),layout='constrained')
    for ax,w in zip(axes,[1,4]):
        for j,case in enumerate(['split_near2','split_side2','split_far2']):
            frame=ratios[(ratios.window==w)&(ratios.split_case==case)]
            for k,size in enumerate([64,1024]):
                selected=frame[frame.bytes==size].groupby('cluster_index').split_over_intra.agg(['median','min','max'])
                xx=np.arange(4)+(j-1)*.12+(k-.5)*.035
                ax.errorbar(xx,selected['median'],yerr=np.vstack([selected['median']-selected['min'],selected['max']-selected['median']]),marker='o' if size==64 else 's',ls='none',color=['tab:blue','tab:orange','tab:green'][j],label=f'{case}, {size} B',capsize=3)
        ax.axhline(1,color='black',ls='--',lw=1); ax.set_xticks(range(4),['0','5','10','15']); ax.set_xlabel('几何小簇编号'); ax.set_ylabel('分散两条流 / 同块两条流 带宽比'); ax.set_title(f'W={w}'); ax.grid(alpha=.2)
    handles,labels=axes[0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='outside lower center',fontsize=11,ncol=3)
    fig.suptitle('逐作业配对比值：点为三次中位数，误差线为最小至最大；两个面板纵轴不同',fontsize=16)
    save(fig,'07_split_vs_intra')
    fig,ax=plt.subplots(figsize=(14,6),layout='constrained')
    for scope,label in [('8B','仅 8 B'),('all','全部 6 种大小')]:
        frame=models[models.scope==scope]
        ax.plot(frame.model,frame.cv_rmse_cycles,'o-',label=label)
    ax.set_ylabel('核对分组五折交叉验证 RMSE (cycles)'); ax.set_xlabel('描述性线性模型'); ax.legend(); ax.grid(alpha=.2); ax.tick_params(axis='x',rotation=20)
    ax.set_title('拓扑描述模型对照；两方向及所有大小的同一核对在同一折')
    ax.set_xticks(range(7),labels=['大小/常数','大小＋跨块','大小＋单核距离','大小＋跨块＋单核距离','大小＋小簇距离','大小＋跨块＋小簇距离','大小＋异行/异列'])
    save(fig,'08_model_comparison')

if __name__=='__main__': main()
