"""Independent CSV audit and Chinese large-format PDF report for the first PMU run."""
from pathlib import Path
from collections import defaultdict, Counter
from fractions import Fraction
from itertools import product
from statistics import median
from html import escape
import csv
import hashlib
import json
import re
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Table, TableStyle
from reportlab.graphics.shapes import Drawing, String
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics import renderPDF

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'results_pmu_20261008_085236_685'
OUT = ROOT / 'outputs/rma_pmu_report_20261008'
OUT.mkdir(parents=True, exist_ok=True)
PDF = OUT / 'SW39000_RMA硬件计数器验证结果分析报告_大图版.pdf'

def read(name):
    with (SRC / name).open(newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))

raw, checks, saved = read('counters.csv'), read('checks.csv'), read('count_scaling.csv')
events = list(dict.fromkeys(x['event'] for x in raw))
assert len(events) == 7
case_rows, pe_rows, grouped = defaultdict(list), defaultdict(list), defaultdict(list)
for x in raw:
    case_rows[int(x['case_id'])].append(x)
    assert int(x['decreased']) == 0
    assert int(x['after']) - int(x['before']) == int(x['delta'])
    grouped[(x['event'], int(x['src']), int(x['dst']), x['mode'], int(x['n']), int(x['cell']))].append(int(x['delta']))
for x in checks:
    pe_rows[int(x['case_id'])].append(x)
assert set(case_rows) == set(pe_rows) == set(range(1, 169))
seen = []
for cid, rows in case_rows.items():
    assert len(rows) == 16 and {int(x['cell']) for x in rows} == set(range(16))
    meta = lambda x: (x['event'], int(x['repeat']), x['mode'], int(x['src']), int(x['dst']), int(x['bytes']), int(x['n']))
    assert len({meta(x) for x in rows}) == 1
    seen.append(meta(rows[0]))
    pr = pe_rows[cid]
    assert len(pr) == 64 and {int(x['pe']) for x in pr} == set(range(64))
    c = rows[0]
    for x in pr:
        assert int(x['errors']) == 0
        expected_l = int(c['n']) if c['mode'] == 'put' and x['pe'] == c['src'] else 0
        expected_r = int(c['n']) if c['mode'] == 'put' and x['pe'] == c['dst'] else 0
        assert int(x['local_done']) == expected_l and int(x['remote_done']) == expected_r
expected = [(e,r,m,s,d,64,n) for e,r,m,(s,d),n in product(events,[1,2],['put','local'],[(0,1),(1,2)],[0,64,256])]
assert Counter(seen) == Counter(expected)
assert (SRC/'RUN_COMPLETE').read_text().strip() == 'cases=168'
job = (SRC/'job.log').read_text()
assert list(map(int,re.findall(r'^PMU_CASE (\d+) ',job,re.M))) == list(range(1,169))
assert len(re.findall(r'^PMU_RETURN \d+ errors=0 decreased_cells=0$',job,re.M)) == 168
assert 'Job 8461857 has been finished.' in job
assert all(len(v) == 2 and v[0] == v[1] for v in grouped.values())
assert all(int(x['delta']) == 0 for x in raw if x['mode'] == 'local' or x['n'] == '0')

# Recompute least squares with rational arithmetic and compare all supplied fit rows.
slopes = {}
for e, m, (s,d), cell in product(events,['put','local'],[(0,1),(1,2)],range(16)):
    pts = [(Fraction(n), Fraction(median(grouped[e,s,d,m,n,cell]))) for n in [0,64,256]]
    xm, ym = sum(x for x,y in pts)/3, sum(y for x,y in pts)/3
    b = sum((x-xm)*(y-ym) for x,y in pts)/sum((x-xm)**2 for x,y in pts)
    a = ym-b*xm
    assert all(y == a+b*x for x,y in pts)
    slopes[e,m,s,d,cell] = (a,b)
assert len(saved) == len(slopes) == 448
for x in saved:
    a,b = slopes[x['event'],x['mode'],int(x['src']),int(x['dst']),int(x['cell'])]
    assert float(x['intercept']) == a and float(x['count_per_operation']) == b
    assert float(x['fit_rmse']) == float(x['zero_median']) == int(x['max_repeat_range']) == 0

summary=[]
for e in events:
    for s,d in [(0,1),(1,2)]:
        active=[i for i in range(16) if slopes[e,'put',s,d,i][1]]
        summary.append(dict(event=e,src=s,dst=d,active_cells=','.join(map(str,active)) or 'none',
            count_per_put=sum(slopes[e,'put',s,d,i][1] for i in range(16)),
            total_N64=sum(median(grouped[e,s,d,'put',64,i]) for i in range(16)),
            total_N256=sum(median(grouped[e,s,d,'put',256,i]) for i in range(16))))
with (OUT/'event_summary.csv').open('w',newline='',encoding='utf-8-sig') as f:
    w=csv.DictWriter(f,fieldnames=list(summary[0])); w.writeheader(); w.writerows(summary)
timing=[]
for s,d in [(0,1),(1,2)]:
    for n in [64,256]:
        for m in ['put','local']:
            vals=[int(p['cycles']) for cid,rows in case_rows.items() for p in pe_rows[cid]
                if (int(rows[0]['src']),int(rows[0]['dst']),rows[0]['mode'],int(rows[0]['n']))==(s,d,m,n)
                and int(p['pe'])==s]
            timing.append(dict(src=s,dst=d,n=n,mode=m,count=len(vals),min=min(vals),median=median(vals),max=max(vals)))
assert len(raw)==2688 and len(checks)==10752
audit=dict(cases=168,counter_rows=len(raw),pe_checks=len(checks),event_count=7,
    parameter_grid_complete=True,all_completion_and_final_payload_flags_pass=True,
    negative_or_decreased_counts=0,positive_counter_rows=sum(int(x['delta'])>0 for x in raw),
    zero_before_all=all(int(x['before'])==0 for x in raw),
    zero_N0_and_local=True,repeat_vectors_identical=True,recomputed_fits=448,
    all_fit_rmse_zero=True,independent_jobs=1,node='vn043675',job_id='8461857',
    cell_mapping='not calibrated',routing='not identified',timing=timing,
    source_addr=sorted({int(x['source_addr']) for x in checks}),
    stack_addr=sorted({int(x['stack_addr']) for x in checks}))
(OUT/'independent_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
sources=['counters.csv','checks.csv','count_scaling.csv','job.log','runtime.txt','build_info.txt','swperf.h',
    'source/pmu_host.c','source/pmu_slave.c','source/pmu_common.h','source/run_pmu_probe.sh','RUN_COMPLETE']
(OUT/'source_hashes.sha256').write_text(''.join(hashlib.sha256((SRC/p).read_bytes()).hexdigest()+'  '+p+'\n' for p in sources),encoding='utf-8')

pdfmetrics.registerFont(TTFont('CN','C:/Windows/Fonts/msyh.ttc'))
pdfmetrics.registerFont(TTFont('CNB','C:/Windows/Fonts/msyhbd.ttc'))
pdfmetrics.registerFontFamily('CN',normal='CN',bold='CNB',italic='CN',boldItalic='CNB')
W,H=landscape(A4); M=36; WIDTH=W-2*M
INK=colors.HexColor('#172C3B'); BLUE=colors.HexColor('#245B82'); LIGHT=colors.HexColor('#EAF1F5'); GRAY=colors.HexColor('#596B78')
body=ParagraphStyle('body',fontName='CN',fontSize=12,leading=19,wordWrap='CJK',textColor=INK)
small=ParagraphStyle('small',parent=body,fontSize=10,leading=15,textColor=GRAY)
cellstyle=ParagraphStyle('cell',parent=body,fontSize=10.5,leading=15)
headstyle=ParagraphStyle('head',parent=cellstyle,fontName='CNB',textColor=colors.white)
c=canvas.Canvas(str(PDF),pagesize=(W,H)); c.setTitle('SW39000 RMA 硬件计数器验证结果分析报告'); c.setAuthor('RMA 实验数据分析')
md=['# SW39000 RMA 硬件计数器验证结果分析报告\n\n数据批次 results_pmu_20261008_085236_685；分析日期 2026-10-08。\n']
page=0
def begin(title,sub):
    global page
    if page: c.showPage()
    page+=1
    c.setFillColor(INK); c.setFont('CNB',22); c.drawString(M,H-47,title)
    c.setFont('CN',10); c.setFillColor(GRAY); c.drawString(M,H-70,sub)
    c.setStrokeColor(colors.HexColor('#D5DFE7')); c.line(M,36,W-M,36)
    c.setFont('CN',9); c.drawString(M,22,'SW39000 RMA 硬件计数器验证  |  2026-10-08  |  作业 8461857')
    c.drawRightString(W-M,22,f'{page} / 7')
    md.append('\n## '+title+'\n\n'+sub+'\n')
def para(text,top,x=M,width=WIDTH,style=body,record=True):
    p=Paragraph(text,style); _,h=p.wrap(width,H); assert top-h>43,(page,text,top,h)
    p.drawOn(c,x,top-h)
    if record: md.append('\n'+re.sub('<[^>]+>','',text)+'\n')
    return top-h-10
def table(rows,widths,top):
    data=[[Paragraph(escape(str(v)),headstyle if ri==0 else cellstyle) for v in row] for ri,row in enumerate(rows)]
    t=Table(data,colWidths=widths)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),BLUE),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,LIGHT]),
        ('GRID',(0,0),(-1,-1),.5,colors.HexColor('#D5DFE7')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('LEFTPADDING',(0,0),(-1,-1),8)]))
    _,h=t.wrap(WIDTH,H); assert top-h>44,(page,h,top); t.drawOn(c,M,top-h)
    md.append('\n'+'\n'.join('| '+' | '.join(map(str,row))+' |'+ ('\n|'+' --- |'*len(row) if ri==0 else '') for ri,row in enumerate(rows))+'\n')
    return top-h-15

begin('RMA 硬件计数器验证结果','已获得可重复的 RMA 计数响应与同块跨块差异，尚未识别完整拓扑和路由')
y=para('本轮证明：在节点 <b>vn043675</b> 的本次作业中，若干硬件计数事件能够准确跟随受控 RMA 操作变化。跨块通信比同块通信多出一个 E 端口事件读数，为后续识别片上连接提供了直接观测线索。',H-95)
y=table([['主要发现','实际观测','能支持的判断'],
 ['操作数','TBOX 描述符增量 = N','选定事件准确响应 PUT 次数'],
 ['传输量','TBOX 传输量增量 = 16N','64 B 数据对应 16 个 4 B 计量单位'],
 ['共同响应','两个核对均有 L 事件 cell 0 = 6N','存在共同的请求上网计数特征'],
 ['空间差异','仅 1→2 有 E 事件 cell 1 = 6N','事件读数能区分本次同块与跨块配置']], [105,280,WIDTH-385],y)
y=para('<b>核心结论：</b>硬件计数器这条观测路线已具备继续标定的条件；当前只测两个核对、一个消息大小，不能据此断言采用 XY 或 YX，也不能把 cell 1 直接认作几何块 1。',y)
para('全部 168 个测试返回，2688 条计数记录与 10752 条从核检查记录完整。两次重复来自同一个作业，不能替代跨作业稳定性验证。',y,style=small)

begin('1 测试范围与计数口径','单核组内 CPE 间单向 RMA PUT，64 B，W=1；事件逐个配置并分别运行')
y=table([['项目','本次设置'],['节点和作业','vn043675；8461857；q_share；资源请求 MPE 1、CG 1、CPE 64'],
 ['核对','0→1 为同一几何 2×2 块；1→2 为横向相邻的两个几何块'],
 ['模式与次数','PUT 与 local；N=0、64、256；每个组合重复 2 次'],
 ['规模','7 事件 × 2 核对 × 2 模式 × 3 次数 × 2 重复 = 168 次内核调用'],
 ['计数区间','主核 before 读数 → spawn/join 内核 → after 读数；ΔC=after-before']], [135,WIDTH-135],H-95)
y=para('PUT 模式每次发起后等待本地完成，接收核等待 N 次远端完成。没有逐条应用层回包，但硬件完成通知仍存在。local 模式只在源核进行逐字节本地缓冲复制，作为非 RMA 对照。',y)
y=para('计数区间覆盖内核启动、配置 DMA、初始化、同步、传输、最终数据校验和结果 DMA。N=0 用于检查固定活动；local 用于检查循环相关的非 RMA 活动。它们不是与 PUT 等耗时、等指令数的对照。',y)
para('几何编号只用于实验分类：核 id=8r+c，几何块=4 floor(r/2)+floor(c/2)。计数数组的 cell 编号是 SDK 返回的下标，本轮未完成它与几何块的映射。',y,style=small)

begin('2 计数与传输次数的关系','图 1 两次重复完全重合；连线仅连接三个实测次数，不表示测试了其他次数')
def lineplot(x,title,series,maxy,step):
    d=Drawing(238,222)
    lp=LinePlot(); lp.x=44; lp.y=42; lp.width=180; lp.height=148
    lp.data=[[(n,v) for n,v in zip([0,64,256],vals)] for vals in series]
    lp.xValueAxis.valueMin=0; lp.xValueAxis.valueMax=256; lp.xValueAxis.valueSteps=[0,64,256]
    lp.yValueAxis.valueMin=0; lp.yValueAxis.valueMax=maxy; lp.yValueAxis.valueStep=step
    for ax in [lp.xValueAxis,lp.yValueAxis]: ax.labels.fontName='CN'; ax.labels.fontSize=9
    for i in range(len(series)):
        lp.lines[i].strokeColor=BLUE if i==0 else colors.HexColor('#B75338'); lp.lines[i].strokeWidth=2
    d.add(lp); d.add(String(120,209,title,fontName='CNB',fontSize=12,textAnchor='middle'))
    d.add(String(130,13,'发送次数 N',fontName='CN',fontSize=10,textAnchor='middle'))
    renderPDF.draw(d,c,x,275)
lineplot(M,'描述符计数',[[0,64,256]],256,64)
lineplot(M+259,'传输量计数 4 B 单位',[[0,1024,4096]],4096,1024)
lineplot(M+518,'L 事件 FLIT 计数',[[0,384,1536]],1536,384)
y=table([['计数项','N=0','N=64','N=256','每次 PUT 增量'],['描述符 cell 0',0,64,256,1],
 ['传输量 cell 0',0,1024,4096,16],['L 事件 cell 0',0,384,1536,6]], [225,95,95,95,WIDTH-510],275)
y=para('以上三个计数项在 0→1 与 1→2 上完全相同。传输量换算为 4ΔC 字节：N=256 时，4096×4=16384 B，等于 256×64 B。手册将该 TBOX 事件定义为 4 B 粒度传输量。',y)
para('448 个逐事件、模式、核对、cell 拟合结果均与原始记录重新计算一致，截距与拟合 RMSE 均为 0。这是当前三个 N 水平的精确线性关系，不代表所有消息大小或负载下均如此。',y,style=small)

begin('3 同块与跨块的空间响应','图 2 数字为每次 64 B PUT 的 FLIT 增量；横轴是计数下标，不是已标定的物理位置')
ports=[('L',events[2]),('S',events[3]),('N',events[4]),('W',events[5]),('E',events[6])]
def grid(s,d,top):
    c.setFont('CNB',12); c.setFillColor(INK); c.drawString(M,top,f'{s}→{d}   '+('同一几何块' if s==0 else '跨几何块'))
    x0=M+60; cw=(WIDTH-75)/16; ch=24
    c.setFont('CN',9)
    for j in range(16): c.drawCentredString(x0+(j+.5)*cw,top-21,str(j))
    for i,(label,e) in enumerate(ports):
        y=top-30-(i+1)*ch
        c.setFillColor(INK); c.drawString(M+15,y+8,label)
        for j in range(16):
            v=int(slopes[e,'put',s,d,j][1]); c.setFillColor(BLUE if v else LIGHT)
            c.setStrokeColor(colors.white); c.rect(x0+j*cw,y,cw,ch,fill=1,stroke=1)
            c.setFillColor(colors.white if v else GRAY); c.drawCentredString(x0+(j+.5)*cw,y+8,str(v))
grid(0,1,H-103); grid(1,2,H-286)
y=para('同块与跨块都在 L 事件 cell 0 出现 6N；只有跨块 1→2 在 E 事件 cell 1 出现额外 6N。两次重复、N=64 与 256 均一致。其他 cell 及 S/N/W 的本次所选事件均为 0。',H-463)
para('这说明跨块配置伴随额外的端口事件活动。由于只读取 req_p1up_flit，且 cell/端口方向未标定，不能把零读数解释为没有链路，也不能把 E cell 1 直接解释为源块向东发出的端口。',y,style=small)
md.append('\n空间矩阵的非零项：0→1 为 L cell 0=6；1→2 为 L cell 0=6、E cell 1=6；其余所选端口事件/cell 为 0。\n')

begin('4 原始记录与质量检查','独立核对原始 CSV、运行日志和随作业保存的源码；没有改写原始结果')
y=table([['检查项目','核对结果'],['覆盖与日志','参数网格完整；168 个 CASE 与 168 个 RETURN 一一对应；作业已结束'],
 ['计数数组','每例 16 个 cell，共 2688 行；after-before 全部一致；无下降标记'],
 ['从核结果','每例 64 个核，共 10752 行；errors 全为 0；所有完成次数符合配置'],
 ['空白与本地对照','全部 N=0 与全部 local 配置的所选事件增量均为 0'],
 ['两次重复','每个事件、核对、模式、N 的 16 维计数向量完全相同'],
 ['原有拟合表','重新核算全部 448 行，斜率、截距、RMSE 与原表一致']], [145,WIDTH-145],H-95)
y=para('<b>校验覆盖：</b>程序检查最终接收缓冲的每个字节，并核对本地与远端完成数。因为每次发送相同内容，不能证明每一次中间传输的所有字节都单独校验过。',y)
y=para('<b>对照含义：</b>零读数说明本次选中的事件未观察到这些对照活动，不代表启动、DMA 或主存流量不存在，也不保证在其他事件选择或节点上仍为零。',y)
para('运行记录为一个节点、一个作业、每配置两次重复。q_share 资源请求未证明计数器独占；数组顺序、事件完整覆盖、位宽与权限适用范围仍需继续标定。',y,style=small)

begin('5 与旧结果的关系及解释边界','本轮新增的是硬件事件证据；循环耗时仍不是纯单向链路延迟')
y=para('旧实验测得“等待多久”和“背景流让探针慢多少”。本轮进一步看到：RMA 描述符和传输量计数随操作数精确变化，同块和跨块在所选端口事件上存在可重复差异。这使后续路径识别不再只能依赖总耗时。',H-95)
y=table([['问题','本轮答案'],['计数接口能否用于继续实验','可以继续标定；4 类事件至少在一种配置下出现预期线性响应'],
 ['是否已经知道一条完整物理路径','没有；只观察到两个核对在少量事件上的计数分布'],
 ['是否证明采用 XY 或 YX','没有；两个核对均仅横向相邻，无法区分先横后纵与先纵后横'],
 ['6 FLIT 是否等于六跳或六个包','不是；这里是事件累计单位，FLIT 字节宽度、包头与协议开销未分离'],
 ['所有核对是否有相同路径与代价','不能外推；本轮只测 0→1 和 1→2，且两源核处于同一几何块']], [225,WIDTH-225],y)
y=para('辅助时间记录：N=256 时，两核对发送端循环的中位数均为 25632.5 cycles（每核对汇集 7 个事件轮次×2 次重复）。这包含发起、循环和本地完成等待，并非 RTT/2 或远端单向到达延迟，不能直接与旧报告的 98/102 cycles 比较。',y)
para('缓冲地址记录为 0x480，栈变量地址为 0x40000001ffc0。地址空间的确切含义及栈访问开销仍需 SDK/反汇编验证，不能只凭地址数值断言这就是旧实验耗时差异的原因。',y,style=small)

begin('6 下一步与数据依据','先标定端口和 cell 的含义，再扩大到多跳路径；保留本轮作为功能验证基线')
y=table([['顺序','补充内容','要解决的问题'],['1','增加 2→1、2→3、0→8、8→16 等反向、同块和纵向核对','E cell 1 随哪个端点或方向移动；纵向事件能否响应'],
 ['2','遍历不同源块及 A/B/C/D 成员，结合 TBOX 和运行时编号','建立 CPE、几何块与计数 cell 的映射'],
 ['3','扩展 req/res、up/down 和必要的 p0、pack 事件；扫 64 B 与 4 KiB','分离数据、请求和完成通知，标定计量单位'],
 ['4','标定后扫描相邻与远距离核对，含同时跨行跨列的通信','推断可见连接和候选路径，用留出核对验证规则'],
 ['5','重复独立作业，核实隔离；再加入经过已观测资源的背景流','验证稳定性、共享资源与负载下路径是否改变']], [45,360,WIDTH-405],H-95)
y=para('现有 calibrate 配置可先覆盖 22 个事件、8 个核对、两种消息大小和更大 N，但它还不包含上述全部反向核对、全 cell 映射、p0/pack 扫描或跨作业验证。运行扩展标定不等于完成拓扑识别。',y)
y=para('<b>数据依据：</b>results_pmu_20261008_085236_685 中的 counters.csv、checks.csv、count_scaling.csv、job.log、runtime.txt、build_info.txt、swperf.h、RUN_COMPLETE 与 source 内源码。独立复算摘要和源文件 SHA256 随报告保存。',y,style=small)
para('<b>接口定义依据：</b>《神威高性能计算机性能工具用户手册 V1.4》第 6 章（16 项数组），第 6.3、6.9 节（L/E 事件），第 6.16 节、印刷页 50（RMA PUT 传输量按 4 B 计量）。原始事件全名与逐核对统计见附带 event_summary.csv。',y,style=small)
c.save()
md.append('\n## 原始事件全名与汇总\n')
for e in events:
    md.append('\n`'+e+'`\n')
    for row in summary:
        if row['event']==e: md.append(f"\n- {row['src']}→{row['dst']}：非零 cell={row['active_cells']}；每次 PUT 增量={row['count_per_put']}；N=64 总增量={row['total_N64']}；N=256 总增量={row['total_N256']}。\n")
(OUT/'SW39000_RMA硬件计数器验证结果分析报告.md').write_text('\n'.join(md),encoding='utf-8')
print(json.dumps(audit,ensure_ascii=False,indent=2))
print(PDF)
