"""Append the real full-rank route experiment to the existing report design."""
import statistics as st


def append_route_pages(r,D,fmt,pct):
    S={v['group']:v for v in D['summary']};J=D['jobs'];I=D['integrity']
    M={m['model']:m for m in D['models']}
    def group(g):return 'R-'+g
    def bg(v):return f"{v['background_src_block']}→{v['background_dst_block']}"
    def flow(v):return f"{v['background_src']}→{v['background_dst']}"
    def probe(v):return f"{v['probe_src']}→{v['probe_dst']}"
    def bounds(v):return pct(v['effect_pct_min'])+' 至 '+pct(v['effect_pct_max'])
    def by(src,pb=1024):return [v for v in S.values() if v['probe_src']==src and v['probe_bytes']==pb]
    def selected(src):
        rows=by(src);diagonal=[v for v in rows if v['category']=='diagonal_background']
        anchor=next(v for v in rows if v['category']=='anchor')
        second=next(v for v in rows if v['category']=='anchor' and v['effect_pct_median']<10)
        return [anchor,second,max(diagonal,key=lambda v:v['effect_pct_median']),min(diagonal,key=lambda v:v['effect_pct_median'])]

    r.page('11 跨行、跨列背景：实际运行与满秩检查', '新增结果：results_route_20261007_223701_6654；2026-10-07；独立补充，保留前述 quick 数据。')
    r.p('保留 0→54 和 54→0；每方向 6 个原背景＋10 个跨行、跨列背景。每布局测 8 B、1 KiB 探针，均回复 8 B；背景 4 KiB、W=4。64 组以 ABBA／BAAB 测无背景／有背景，每项 2048 RTT，共 256 项／作业、5 作业。')
    r.table(['作业', '节点', '随机种子', '实际完成项'], [[j['job'],j['node'],j['seed'],j['cases']] for j in J], [1,1.3,1.1,1],font=10.7,rowpad=4)
    r.table(['实际候选矩阵', '行数', '列数', '精确秩', '列范数归一化条件数'], [
        [dict(all='两个方向合计',probe_0='仅 0→54',probe_54='仅 54→0')[c['scope']],c['rows'],c['columns'],c['exact_rank'],fmt(c['unit_column_norm_condition'],3)]
        for c in I['design_audit']['checks']], [1.5,.55,.55,.7,1.6],font=10.8,rowpad=4)
    r.p('<b>原来“14 列只有秩 7”的参数重合已经消除。</b>实际计划的列包括常数、消息大小指示量和 12 个 XY／YX 去程／回程重叠特征。背景块 1→6 在 XY 下为 1→2→6，在 YX 下为 1→5→6，增加了可区分的信息。')
    r.p('1280 个原始 CSV、320 个作业内配对均独立复核通过；源码三文件与 quick 成功运行快照逐字相同。满秩只保证当前线性模型的最小二乘系数可唯一估计，模型预测和物理解释仍需另外检验。', 'small')
    r.p('本章以 R-gxxxx 标识新实验组，对应本轮 CSV 中的 gxxxx；前 20 页组号保持原样。周期未标定为时间；本章全部延迟为完整协议 RTT。', 'small')

    for src,title,num in [(0,'11.1 0→54：原背景与新增背景',14),(54,'11.2 54→0：原背景与新增背景',15)]:
        r.page(title,'每方向 16 个背景布局；点为五作业内配对增幅中位数；横线为最小至最大，不是置信区间。')
        r.image(f'图{num}_路径补充方向{src}',f'图 {num} 原对照与新增跨行、跨列背景；两种探针大小，背景均为 4 KiB、W=4',maxheight=268)
        r.table(['1 KiB 代表组','背景块／CPE','类型','RTT 增幅','五作业范围'],[
            [group(v['group']),bg(v)+' / '+flow(v),'原对照' if v['category']=='anchor' else '跨行、跨列',pct(v['effect_pct_median']),bounds(v)]
            for v in selected(src)],[1.05,1.6,1.2,1,1.85],font=10.4,rowpad=4)
        ds=[v for v in by(src) if v['category']=='diagonal_background'];lo=min(ds,key=lambda v:v['effect_pct_median']);hi=max(ds,key=lambda v:v['effect_pct_median'])
        r.p(f"1 KiB 新增背景中的中位数从块 {bg(lo)} 的 {pct(lo['effect_pct_median'])} 到块 {bg(hi)} 的 {pct(hi['effect_pct_median'])}。同时跨行、跨列仍有强弱差异；不能只凭是否跨两维或路径长短确定干扰。",'small')

    r.page('11.3 满秩之后：模型的留出预测仍不足', '响应为 64 组五作业配对 RTT 增幅（%）；最小二乘独立重算；RMSE 单位为百分点。')
    r.image('图16_路径补充模型留出误差','图 16 同一有向背景核对的两种大小与两探针方向合并留出；所有训练折均满秩',maxheight=205)
    names={'constant_size':'常数＋消息大小','XY':'XY：去程＋回程','YX':'YX：去程＋回程','combined_descriptive':'XY＋YX 联合描述'}
    r.table(['模型','列数／秩','条件数','拟合 RMSE','留出布局 RMSE','留出方向 RMSE'],[
        [names[m['model']],str(m['columns'])+'/'+str(m['rank']),fmt(m['unit_column_norm_condition']),fmt(m['fit_RMSE_pct_points']),
         fmt(m['background_layout_RMSE_pct_points']),fmt(m['probe_direction_RMSE_pct_points'])] for m in D['models']],
        [1.65,.7,.9,1,1.1,1.1],font=10.6,rowpad=5)
    r.p('留出背景布局为 23 折，留出探针方向为 2 折。YX 的误差低于 XY，但两者都高于常数＋大小基线。联合模型的拟合 RMSE 最低，留出误差却最高，增加这些项未改善未见布局的预测。')
    r.p('本轮模型有 8 或 14 个参数；与前页 quick 紧凑模型的参数数和布局集合不同，不能直接用两个实验的 RMSE 大小选路由。这里的交叉验证留出的是核对／方向，没有将计算节点作为独立验证折。', 'small')

    r.page('11.4 同一组特征，为什么仍有不同干扰', '同探针、同消息大小；下列每对背景的全部 14 项输入完全相同。')
    r.image('图17_路径特征相同但干扰不同','图 17 实测柱与联合模型拟合值；每对背景的模型预测必须相同',maxheight=215)
    pairs=[('g0001','g0003'),('g0005','g0007'),('g0033','g0035')]
    r.table(['探针','背景 A／B','A 的增幅','B 的增幅','差额（百分点）'],[
        [probe(S[a]),bg(S[a])+' / '+bg(S[b]),pct(S[a]['effect_pct_median']),pct(S[b]['effect_pct_median']),
         fmt(abs(S[a]['effect_pct_median']-S[b]['effect_pct_median']))] for a,b in pairs],
        [1,1.3,1.05,1.05,1.5],font=11,rowpad=6)
    r.p('<b>“列独立”与“特征足够”是两个问题。</b>满秩消除了不同系数产生相同拟合值的歧义；但是模型只记重叠边／节点的数量，没有记具体是哪一条边、发生在路径哪个位置，以及更多端点／协议状态。')
    r.p('例如同为 0→54、1 KiB，背景块 1→2 与 2→3 的输入向量相同，增幅却为 34.961% 与 3.543%。仅调整这 14 项线性系数无法同时解释这组差异。这直接说明当前特征压缩掉了有用信息；不能仅把误差归为矩阵秩不足。', 'small')

    r.page('11.5 联合模型系数及其解释边界', '拟合 64 组中位数；系数单位为 RTT 增幅的百分点，不是 cycles／跳或端口延迟。')
    labels={'constant':'常数','size1024':'1 KiB 大小指示量'}
    for order in ('XY','YX'):
        for phase,ch in [('forward','去程'),('reply','回程')]:
            for kind,kh in [('same_direction','同向边'),('opposite_direction','反向边'),('shared_internal_nodes','探针内部节点重叠')]:
                labels[f'{order}_{phase}_{kind}']=f'{order} {ch} {kh}'
    coeff=[c for c in D['coefficients'] if c['model']=='combined_descriptive'];rows=[]
    for c in coeff:
        vals=[j['coefficient_pct_points'] for j in D['job_coefficients'] if j['feature']==c['feature']]
        rows.append([labels[c['feature']],fmt(c['coefficient_pct_points']),fmt(min(vals)),fmt(max(vals)),str(sum(v>0 for v in vals))+'/5'])
    r.table(['模型项','联合拟合系数','逐作业最小','逐作业最大','正号作业数'],rows,[2.3,1,1,1,1],font=10.5,rowpad=4)
    r.p(f"联合模型拟合 R²={fmt(M['combined_descriptive']['R2'],4)}，仍有约 {fmt(M['combined_descriptive']['fit_RMSE_pct_points'])} 个百分点的拟合误差。多项系数为负，表示这个线性拟合的条件关系；不能解释成共享链路消除了延迟或硬件有负成本。",'small')
    r.p('逐作业符号／范围只检查同一模型估计是否稳定，不能修复遗漏因素。XY 与 YX 是两种候选假设；联合表只作描述性诊断，不表示机器同时采用两条路径，也不能据此确定 router 或端口。', 'small')

    r.page('11.6 背景实际速率与计时覆盖', '只画 1 KiB 的 32 个背景布局；背景数据均为 4 KiB、W=4，实际发送速率由运行状态共同决定。')
    r.image('图18_路径补充背景速率','图 18 背景源期间吞吐与探针配对增幅；竖线为五作业增幅范围',maxheight=220)
    bgrows=[S['g0021'],S['g0049'],min(by(0),key=lambda v:v['effect_pct_median']),min(by(54),key=lambda v:v['effect_pct_median'])]
    r.table(['组／探针','背景块','RTT 增幅','背景中位吞吐 B/cycle','背景吞吐范围'],[
        [group(v['group'])+' / '+probe(v),bg(v),pct(v['effect_pct_median']),fmt(v['bg_B_per_cycle_median'],6),
         fmt(v['bg_B_per_cycle_min'],6)+' 至 '+fmt(v['bg_B_per_cycle_max'],6)] for v in bgrows],
        [1.8,.7,1.05,1.5,1.9],font=10.5,rowpad=5)
    r.p('同样的背景消息大小与窗口不意味着等注入强度。背景吞吐较低与探针 RTT 较长同时出现，可能都是共享资源／协议交互的结果；不能从相关性断言背景速率单向造成干扰。')
    r.p(f"640 次带背景测量的源端运行周期／探针周期最小为 {fmt(I['minimum_background_duration_ratio'],6)}。ready 后才测探针，计时后发 stop，接收端按实际元数据排空；周期比是各自本核跨度，不是跨核同步测得的全局墙钟。",'small')

    r.page('11.7 两个计算节点上的五作业观测', '作业 01／02：vn027164；作业 03／04／05：vn027140；随机顺序，组内 ABBA／BAAB。')
    r.image('图19_路径补充逐作业重复','图 19 每个点对应一个作业；代表 1 KiB 配置的强弱差异在本轮观测中持续存在',maxheight=215)
    gids=['g0001','g0003','g0021','g0049','g0061']
    r.table(['1 KiB 组／背景块',*[j['job'] for j in J]],[
        [group(g)+' / '+bg(S[g]),*[pct(next(e['effect_pct'] for e in D['effects'] if e['group']==g and e['repeat']==j['repeat'])) for j in J]] for g in gids],
        [1.5,1,1,1,1,1],font=10.2,rowpad=5)
    r.p(f"全部 {I['groups_positive_all_jobs']} 个配置在五作业中均增加 RTT；{I['groups_effect_exceeds_control_drift_all_jobs']} 个配置的每次增幅都超过对应两次控制的极差。最大控制漂移为 {fmt(I['maximum_baseline_drift_pct'])}%。这些记录支持干扰的重复性。")
    r.p('节点由调度器分配，节点与作业次序没有独立随机化；两节点五作业不是覆盖整个系统的节点泛化实验。本轮模型以五作业中位数为响应，报告的留出误差仍是布局／方向验证。', 'small')

    r.page('11.8 原背景锚点复测：与上一轮对照', '复测同一内核下的 12 个原背景布局、两种探针大小；上一轮 vn043968，本轮 vn027164／vn027140。')
    r.image('图20_路径补充历史锚点','图 20 1 KiB 锚点效应变化；数值为本轮中位数减 quick 中位数',maxheight=140)
    anchors=[a for a in D['anchors'] if a['probe_bytes']==1024]
    r.table(['本轮组／探针','背景块','quick 增幅','本轮增幅','变化（百分点）'],[
        [group(a['new_group'])+' / '+str(a['probe_src'])+'→'+str(54 if a['probe_src']==0 else 0),
         str(a['background_src_block'])+'→'+str(a['background_dst_block']),pct(a['old_effect_pct']),pct(a['new_effect_pct']),fmt(a['change_pct_points'])] for a in anchors],
        [1.9,.75,1.1,1.1,1.45],font=10.2,rowpad=3)
    delta=max(abs(a['change_pct_points']) for a in D['anchors'])
    r.p(f"全部 24 个大小／布局锚点的两轮增幅差绝对值最大约 {fmt(delta)} 个百分点，原有强弱模式复现。比较的是各轮内部 T/C 效应，不是直接把两个节点的绝对 RTT 相减来提取硬件开销。",'small')

    r.page('11.9 新结果回答了什么，仍缺少什么', '本轮已经上机；解决设计矩阵的线性重合，但未确定实际路由与物理端口结构。')
    r.table(['问题','本轮实际证据','解释'],[
        ['14 列系数是否能唯一估计？','全矩阵及两个探针方向均为 14／14；全部留出训练折满秩。','在当前线性模型下可以；不再需要伪逆任选一个解。'],
        ['背景干扰是否存在且可重复？','64 组均在五作业中增加 RTT；最大中位增幅 +38.085%；覆盖两个节点。','支持观测到的干扰与位置差异，未分离所有硬件与软件共享因素。'],
        ['能据此选出 XY 或 YX 吗？','YX 留出布局误差 15.605 pp，XY 17.232 pp；基线仅 13.891 pp。','YX 相对较低，但两者均未改善基线预测，不足以确定实际路由。'],
        ['联合路径项能解释所有差异吗？','联合拟合 R² 约 0.181；留出布局 RMSE 21.372 pp；相同特征可差 31.417 pp。','重叠计数遗漏了位置或其他状态；满秩不代表模型正确。'],
    ],[1.5,2.1,2.5],font=10.8,rowpad=6)
    r.sub('后续应优先分离的因素')
    r.p('对同特征、不同效应的背景边做具体边位置与端点对照，并控制／记录背景实际负载；再独立改变返回部分与探针象限。保留同作业内控制，先校准协议开销，避免把序号、等待、接收响应成本拟合成物理跳数。')
    r.p('复核依据：1280 raw 文件、320 配对、640 背景记录、40960 条连续 64 RTT 批均值。错误、wait_stage、背景上限均为 0，次数与最终数据检查通过；仍未逐一验证每次中间背景传输的全部字节。', 'small')
    r.p('本轮分析表保存于 分析表/路径补充；route_audit.json 保存新原始文件 SHA-256；route_report_data.json 为本章数值来源。原始结果目录及前述 quick 数据不改写，采样不代表单消息 p95／p99。', 'small')

    for src in (0,54):
        for pb in (8,1024):
            rows=by(src,pb);size='8 B' if pb==8 else '1 KiB'
            r.page(f'附表：{src}→{54 if src==0 else 0}；{size} 全部 16 背景布局','C／T 为五作业内控制／处理中位数的中位数；增幅先作业内取 T/C，再取五作业中位数。')
            r.table(['本轮组','背景块','背景 CPE','C RTT cycles','T RTT cycles','增幅','五作业增幅范围','背景 B/cycle'],[
                [group(v['group']),bg(v),flow(v),fmt(v['control_RTT_median'],1),fmt(v['treatment_RTT_median'],1),
                 pct(v['effect_pct_median']),bounds(v),fmt(v['bg_B_per_cycle_median'],4)] for v in rows],
                [1.1,.7,.8,.95,.95,.85,1.8,.85],font=10.0,rowpad=4)
            r.p('前六行复测原背景，其余十行新增跨行、跨列背景。背景固定 4 KiB、W=4，探针回信均为 8 B。范围是五个已观测作业内效应的最小至最大，不是置信区间。', 'small')
            r.p('完整候选 XY／YX 背景路径、12 个重叠特征与模型预测见分析表/路径补充/summary.csv、predictions.csv；对应实际计划和 route_features.csv 一并保留在原结果目录。', 'small')
