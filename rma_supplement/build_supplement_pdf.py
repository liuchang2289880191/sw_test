"""Render the audited supplement in the original landscape, large-chart style.

Run with the bundled Python runtime (reportlab/Pillow); analysis uses Anaconda.
All scientific values come from the independent audit's JSON/CSV outputs.
"""
from pathlib import Path
from html import escape
from decimal import Decimal, ROUND_HALF_UP
import csv
import json
import statistics as st
from PIL import Image as PILImage
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, Table, TableStyle, Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/rma_supplement_report_20261007'
FIG = OUT / '图表'
PDF = OUT / 'SW39000_RMA补充实验数据报告_大图版.pdf'
D = json.loads((OUT / 'report_data.json').read_text(encoding='utf-8'))
S = {r['group']: r for r in D['summary']}
E = {(r['group'], r['repeat']): r for r in D['effects']}
with (OUT / '分析表/cases.csv').open(encoding='utf-8-sig', newline='') as f:
    CASES = list(csv.DictReader(f))
W, H = landscape(A4)
M = 34
WIDTH = W - 2 * M
NAVY = colors.HexColor('#21435D')
INK = colors.HexColor('#16222C')
PALE = colors.HexColor('#F1F5F8')
GRAY = colors.HexColor('#566472')
pdfmetrics.registerFont(TTFont('YaHei', 'C:/Windows/Fonts/msyh.ttc'))
pdfmetrics.registerFont(TTFont('YaHeiBold', 'C:/Windows/Fonts/msyhbd.ttc'))
pdfmetrics.registerFontFamily('YaHei', normal='YaHei', bold='YaHeiBold', italic='YaHei', boldItalic='YaHeiBold')
STYLES = {
    'body': ParagraphStyle('body', fontName='YaHei', fontSize=11.4, leading=16.5, textColor=INK, wordWrap='CJK'),
    'small': ParagraphStyle('small', fontName='YaHei', fontSize=9.8, leading=14, textColor=GRAY, wordWrap='CJK'),
    'condition': ParagraphStyle('condition', fontName='YaHei', fontSize=10.6, leading=15, textColor=GRAY, wordWrap='CJK'),
    'caption': ParagraphStyle('caption', fontName='YaHei', fontSize=10, leading=14, textColor=INK, wordWrap='CJK', alignment=1),
    'table': ParagraphStyle('table', fontName='YaHei', fontSize=10.5, leading=14, textColor=INK, wordWrap='CJK'),
    'tablehead': ParagraphStyle('tablehead', fontName='YaHeiBold', fontSize=10.5, leading=14, textColor=colors.white, wordWrap='CJK'),
    'sub': ParagraphStyle('sub', fontName='YaHeiBold', fontSize=13, leading=18, textColor=INK, wordWrap='CJK'),
}


def fmt(x, d=3):
    v = Decimal(str(float(x))).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)
    return f'{v:.{d}f}'


def pct(x, d=3):
    return ('+' if x > 0 else '') + fmt(x, d) + '%'


def effect_range(r):
    return f'{pct(r["effect_min"])} 至 {pct(r["effect_max"])}'


def size(x):
    return f'{int(x)} B' if x < 1024 else f'{int(x) // 1024} KiB'


def flows(s):
    return s.replace('->', '→').replace('; ', '；')


def block(pe):
    return (int(pe) // 16) * 4 + int(pe) % 8 // 2


def bgname(r):
    return f'块 {block(r["background_src"])}→{block(r["background_dst"])}'


class Report:
    def __init__(self):
        self.c = canvas.Canvas(str(PDF), pagesize=(W, H), pageCompression=1)
        self.c.setTitle('SW39000 RMA 补充实验数据报告（大图版）')
        self.c.setAuthor('RMA benchmark data analysis')
        self.c.setSubject('完成口径、端点共享、方向共享与持续背景探针；五作业配对分析')
        self.number = 0
        self.y = H - M
        self.metrics = []

    def page(self, title, condition='', first=False):
        if self.number:
            self.end_page()
        self.number += 1
        self.y = H - M
        self.c.bookmarkPage(f'p{self.number}')
        self.c.addOutlineEntry(title, f'p{self.number}', level=0)
        self.c.setFillColor(INK)
        self.c.setFont('YaHeiBold', 23 if first else 18)
        self.c.drawString(M, self.y - (25 if first else 21), title)
        self.y -= 37 if first else 32
        if condition:
            self.p(condition, 'condition', after=9)

    def flow(self, obj, after=6):
        _, height = obj.wrap(WIDTH, self.y - 36)
        if self.y - height < 36:
            raise ValueError(f'Page {self.number} overflow: bottom={self.y-height:.1f}pt, {type(obj).__name__}')
        obj.drawOn(self.c, M, self.y - height)
        self.y -= height + after

    def p(self, text, style='body', after=7):
        self.flow(Paragraph(text, STYLES[style]), after)

    def sub(self, text):
        self.p(text, 'sub', after=6)

    def table(self, heads, rows, widths=None, font=10.5, rowpad=5):
        widths = widths or [1] * len(heads)
        widths = [WIDTH * w / sum(widths) for w in widths]
        ps = ParagraphStyle('cell', parent=STYLES['table'], fontSize=font, leading=font + 3.2)
        hs = ParagraphStyle('head', parent=STYLES['tablehead'], fontSize=font, leading=font + 3.2)
        data = [[Paragraph(escape(str(v)).replace('\n', '<br/>'), hs) for v in heads]]
        data += [[Paragraph(escape(str(v)).replace('\n', '<br/>'), ps) for v in row] for row in rows]
        obj = Table(data, colWidths=widths, hAlign='LEFT')
        obj.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), NAVY),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, PALE]),
            ('GRID', (0, 0), (-1, -1), .35, colors.HexColor('#C7D0D7')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 7), ('RIGHTPADDING', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), rowpad), ('BOTTOMPADDING', (0, 0), (-1, -1), rowpad),
        ]))
        self.flow(obj, after=7)

    def image(self, name, caption, maxheight=235):
        path = FIG / (name + '.png')
        with PILImage.open(path) as im:
            iw, ih = im.size
        scale = min(WIDTH / iw, maxheight / ih)
        obj = Image(str(path), width=iw * scale, height=ih * scale)
        if self.y - obj.drawHeight < 36:
            raise ValueError(f'Page {self.number}: image overflow')
        obj.drawOn(self.c, M + (WIDTH - obj.drawWidth) / 2, self.y - obj.drawHeight)
        self.y -= obj.drawHeight + 4
        self.p(caption, 'caption', after=6)

    def end_page(self):
        self.metrics.append(dict(page=self.number, bottom_content_y=round(self.y, 1)))
        self.c.setFillColor(GRAY)
        self.c.setFont('YaHei', 9.3)
        self.c.drawCentredString(W / 2, 15, f'第 {self.number} 页')
        self.c.showPage()

    def save(self):
        self.end_page()
        self.c.save()
        (OUT / 'layout_metrics.json').write_text(json.dumps(self.metrics, indent=2), encoding='utf-8')


def main():
    r = Report()
    r.page('SW39000 RMA 补充实验数据报告', '大图版；独立补充实验；2026-10-07；结果目录 results_20261007_211507_31272', first=True)
    r.p('目标：在旧实验之外，通过完成口径、端点共享、方向共享和持续背景干扰，进一步约束簇内／簇间 RMA 的性能结构，检验候选片上路径。')
    r.table(['环境／规模', '本次实际记录'], [
        ['计算节点与队列', '5 个独立作业均在 vn043968；q_share；请求 1 MPE、1 CG、64 CPE'],
        ['作业编号', '8452885、8452886、8452887、8452888、8452891'],
        ['实测规模', 'quick 计划：41 个配对组、234 项／作业，共 1170 个原始结果文件、205 个作业内效应'],
        ['计时／统计', '每项 2048 次；组内 ABBA 或 BAAB；先作业内配对，再汇总 5 作业中位数与最小至最大'],
        ['完整性', '原始检查均通过；无错误、超时或背景上限命中；205 个配对结果独立重算一致'],
    ], [1.1, 4.1], font=11)
    r.sub('主要观测')
    r.p('<b>背景干扰具有稳定的位置与方向差异。</b>0→54 探针在部分背景下 RTT 增加约 34%–35%，其他位置约 3%；反向探针部分背景增加约 21%–23%。')
    r.p('<b>端点和方向带宽实验未显示强烈的吞吐塌缩。</b>同一发送 CPE 的两流反而约快 2.97%；同簇／分簇差异较小，不能据此确定端口数量。')
    r.p('<b>实际路由仍未唯一识别。</b>候选模型特征存在重合，完整设计矩阵 14 列、秩 7；XY 与 YX 的去程／回程影响无法分别估计。')
    r.p('口径限制：新内核包含序号检查、屏障指令、带超时的轮询和批次计时，测得约 8000 cycles 的 RTT；不可直接与旧内核约 200 cycles 的 RTT 拼接成硬件延迟模型。详见第 18 页。', 'small')

    r.page('1 测量定义与统计口径', 'KiB=1024 B；RMA 使用 athread_rma_iput；单位保留 cycles 与 B/cycle。')
    r.table(['实验／指标', '计算及含义'], [
        ['E0：完成口径', '控制为批发起后等待本地完成；处理为逐消息往返并检查序号。指标取发起端 send_cycles／2048，处理值是完整 RTT。两套协议不同。'],
        ['E1／E2：聚合带宽', 'BW=数据字节数×2048×流数／活跃核最大本核累计周期。包含发起、轮询及接收等待；不是跨核同步墙钟跨度。'],
        ['窗口 W', '每条流每批发起 W 个消息后等待本地完成；下一批复用槽。本次 E1／E2 和背景流为 4 KiB、W=4；每个接收流独立槽。'],
        ['E3：持续背景探针', '发起端完整往返周期／2048。探针 8 B 或 1 KiB，回信 8 B；背景数据 4 KiB、W=4，直到探针计时结束后才发 stop。'],
        ['归一化效率 η', 'η=并发聚合 BW／各实际流的单流参考 BW 之和；单流参考取本作业内前／后测量中位数。处理与控制分别使用自身流的参考。'],
        ['作业内配对', '控制 C=两次控制中位数；处理 T=两次处理中位数；比值 R=T／C。报告再取五个 R 的中位数与范围。'],
        ['批次样本', '每项 32 个样本，每个样本是连续 64 次 RTT 的均值；不能将其分位数当成单消息 p95／p99。'],
    ], [1.15, 4.6], font=10.5, rowpad=5)
    r.p('比值方向：E1／E2 的 R&gt;1 表示处理布局带宽更高；E3 的 R&gt;1 表示带背景 RTT 更长。柱表中的控制／处理中位数分别汇总，不能用它们相除替代配对比值中位数。')
    r.p('所有图中竖线表示五作业最小至最大，除图 3 的 RTT 范围及图 11 的批次范围有单独说明外；范围不是置信区间。初始化、数组屏障、最终验证与主核 DMA 均在计时外；探针另有 4 次预热。', 'small')

    r.page('1.1 核编号、几何块与实际探针', 'id=8r+c；几何块编号=4 floor(r/2)+floor(c/2)；A／B／C／D 为块内左上／右上／左下／右下。')
    r.image('图01_几何编号', '图 1 16 个 2×2 几何块及各块 A 核；橙框为 E3 探针所在块', maxheight=238)
    r.table(['对象', '核／块', '位置及解释'], [
        ['E3 正／反向探针', 'CPE 0 与 54；块 0 与 15', '0=(0,0)，54=(6,6)，均取块内 A 核；E3 并非 0 与 63。'],
        ['E0 代表核对', '0→1、1→2、0→63', '分别为同块横邻、跨块横邻、远距对角；三组含 8 B 与 1 KiB。'],
        ['E1／E2 中心位置', '块 5：18、19、26、27', 'E1 另用块 6 的 20／22；E2 比较块 5→6 或块 5→9。'],
        ['候选路径名称', 'XY：先列后行；YX：先行后列', '仅按 4×4 几何块网格构造假设；未直接观测物理 router 或实际跳数。'],
    ], [1.25, 1.65, 3.3], font=10.5)
    r.p('计划中的 p0_15、bg1_2 等数字是几何块编号；原始 flows 才是 CPE ID。后文数值表同时保留块与核，避免把块 15 当成 CPE 15。', 'small')

    r.page('2 完成口径：本地完成与逐消息回信', 'E0；W=1；每项 2048 次；控制取发起端发出周期，处理取完整 RTT；回信 8 B。')
    r.image('图02_完成口径', '图 2 六个短回信配置；柱高为五作业中位数', maxheight=213)
    gs = ['g0000', 'g0001', 'g0003', 'g0004', 'g0006', 'g0007']
    r.table(['组／核对', '数据大小', '本地完成', '回信 RTT', '配对增幅', '五作业增幅范围'], [
        [g+' '+flows(S[g]['control_flows']), size(S[g]['bytes']), fmt(S[g]['control_median']), fmt(S[g]['treatment_median']), pct(S[g]['effect_pct']), effect_range(S[g])] for g in gs
    ], [1.35, .8, 1, 1, .9, 1.7], font=10.2, rowpad=4)
    r.p('单位 cycles／数据消息。逐消息回信的协议成本约增加 68%–70%，各组五作业均增加。该增量包含对端检查、回信发起、发起端等待及检查，不能称为纯粹的“远端写入额外延迟”。')
    r.p('8 B 与 1 KiB 的本地完成循环都约 4820 cycles／消息，软件发起和等待开销很大。这组实验用于说明测量口径，不适合从绝对数值恢复簇间跳数。', 'small')

    r.page('2.1 回信大小是否主导协议耗时', 'E0；去程均为 1 KiB；对比 8 B 回信与 1 KiB 回信；W=1。')
    r.image('图03_回信大小', '图 3 完整 RTT；竖线为各配置五个作业内 RTT 中位数的最小至最大', maxheight=235)
    rows = []
    for short, full in [('g0001', 'g0002'), ('g0004', 'g0005'), ('g0007', 'g0008')]:
        ratios = [E[full, j['repeat']]['treatment'] / E[short, j['repeat']]['treatment'] for j in D['jobs']]
        rows.append([short+'／'+full, flows(S[short]['control_flows']), fmt(S[short]['treatment_median']), fmt(S[full]['treatment_median']), pct((st.median(ratios)-1)*100), pct(S[full]['effect_pct'])])
    r.table(['短／长回信组', '核对', '8 B 回信 RTT', '1 KiB 回信 RTT', '长／短回信增幅', '长回信／本地增幅'], rows, [1.25, .7, 1.1, 1.2, 1.1, 1.25], font=10.5)
    r.p('长／短回信按同一作业的处理值配对；两种回信属于不同实验组，未构成同组 ABBA，所以这项增幅属于辅助对照。所有时间单位均为 cycles。')
    r.p('把回信从 8 B 增大到 1 KiB，只改变较小比例的总 RTT；主要耗时仍来自整套往返协议。不能用这三个点推断回程物理链路的峰值带宽。')

    r.page('3 CPE 与簇级端点共享：聚合带宽', 'E1；4 KiB；W=4；两条数据流；几何位置主要围绕块 5；单位 B/cycle。')
    r.image('图04_端点带宽', '图 4 左为控制／处理聚合带宽；右为五作业配对增幅，浅蓝点为逐作业观测', maxheight=206)
    names = ['同源 CPE', '同目标 CPE', '发送端同簇', '接收端同簇']
    gs = ['g0009', 'g0010', 'g0011', 'g0012']
    r.table(['组／因素', '控制流', '处理流', '控制 BW', '处理 BW', '配对变化'], [
        [g+' '+name, flows(S[g]['control_flows']), flows(S[g]['treatment_flows']), fmt(S[g]['control_median'], 6), fmt(S[g]['treatment_median'], 6), pct(S[g]['effect_pct'])] for g, name in zip(gs, names)
    ], [1.2, 1.15, 1.15, .9, .9, .8], font=10.2, rowpad=4)
    r.p('同一发送 CPE 发往两个目标约快 2.97%，五作业范围为 +2.819% 至 +3.025%。该配置改变了发起循环、源缓冲复用与端点分配；这不能证明共享发送端口“更快”。')
    r.p('发送端同簇相对分簇仅 +0.413%，同目标 CPE 与接收端同簇均接近零。这里未看到将端点分散后吞吐成倍恢复的现象；结论限于两流、4 KiB、W=4 和已测位置。', 'small')

    r.page('3.1 按各实际流的单流参考归一化', 'E1；每个并发配置分别使用自身核对的前／后单流参考；η=聚合 BW／单流 BW 之和。')
    r.image('图05_端点归一化', '图 5 归一化扩展效率；η=1 表示达到各实际流单独测量吞吐之和', maxheight=227)
    r.table(['组／因素', '控制 η', '处理 η', '处理／控制 η', 'η 比值五作业范围', '原始效应超过基线漂移'], [
        [g+' '+name, fmt(S[g]['control_efficiency'], 5), fmt(S[g]['treatment_efficiency'], 5), fmt(S[g]['efficiency_ratio'], 6), fmt(S[g]['eff_ratio_min'], 6)+' 至 '+fmt(S[g]['eff_ratio_max'], 6), str(S[g]['effect_gt_drift_jobs'])+'/5 作业'] for g, name in zip(gs, names)
    ], [1.35, .8, .8, 1, 1.6, 1.2], font=10.2)
    r.p('η 约为 0.947–0.983；在本口径下并发吞吐接近两个单流参考之和。同源 CPE 的 +2.97% 优势经归一化仍约 +3.03%，不是只由更换核对的单流差异解释。')
    r.p('同簇发送的归一化差异约 +0.228%，幅度很小；原始效应仅 2/5 作业超过同组两次控制的漂移。此“超过漂移”是描述性核对，不是显著性检验或置信区间。', 'small')

    r.page('4 方向共享与候选共边对照', 'E2；4 KiB；W=4；每项两流；“共边”依几何候选网格定义，未确认真实路由。')
    r.image('图06_方向共享', '图 6 原始带宽变化与归一化效率变化；0% 虚线表示处理与控制相同', maxheight=199)
    names2 = ['横向反向／同向', '纵向反向／同向', '横向共边／分开', '纵向共边／分开']
    gs2 = ['g0013', 'g0015', 'g0014', 'g0016']
    r.table(['组／因素', '控制流', '处理流', 'BW 配对变化', '五作业范围', 'η 配对变化'], [
        [g+' '+name, flows(S[g]['control_flows']), flows(S[g]['treatment_flows']), pct(S[g]['effect_pct']), effect_range(S[g]), pct((S[g]['efficiency_ratio']-1)*100)] for g, name in zip(gs2, names2)
    ], [1.4, 1.08, 1.08, .85, 1.45, .8], font=9.9, rowpad=4)
    r.p('横向反向约低 0.317%，纵向反向约低 1.144%；共边与分开的差异更小，方向并不一致。未出现可据以辨认强半双工瓶颈的吞吐折半现象。')
    r.p('纵向反向五作业均较低，但基线最大漂移达 1.718%；归一化后中位数约低 0.705%。这些小差异不足以单独判断端口数量、独立方向通道或固定路由。', 'small')

    def route_page(src, title, name, start):
        r.page(title, f'E3；探针 {src}→{54 if src==0 else 0}；回信 8 B；背景 4 KiB、W=4；探针每项 2048 RTT。')
        r.image(name, '图 '+('7' if src==0 else '8')+' 各背景位置的探针 RTT 增幅；点为五作业配对中位数，竖线为最小至最大', maxheight=220)
        rows = []
        for n in range(start, start+12, 2):
            a, b = S[f'g{n:04}'], S[f'g{n+1:04}']
            rows.append([f'g{n:04}／g{n+1:04}', bgname(a)+'；CPE '+str(int(a['background_src']))+'→'+str(int(a['background_dst'])), pct(a['effect_pct']), pct(b['effect_pct']), effect_range(b), fmt(b['difference_median'], 1)])
        r.table(['8 B／1 KiB 组', '背景流', '8 B 增幅', '1 KiB 增幅', '1 KiB 五作业范围', '1 KiB 增量 cycles'], rows, [1.25, 1.85, .85, .85, 1.6, 1.05], font=10.1, rowpad=4)
        if src == 0:
            r.p('块 1→2 与块 2→3 都标为 XY 去程同向边，但 1 KiB 探针增幅分别为 35.353% 和 3.471%。块 1→5 没有候选去程同向边，仍增加 35.075%。单纯“去程共边”解释不充分。')
        else:
            r.p('反向探针强干扰约 21%–23%，弱干扰约 4%–7%。与正向结果不同，说明需要保留探针方向与背景位置；但完整 RTT 同时含去程、回程和端点响应，不能把方向差异直接归因于单向链路。')
        r.p('本页 12 个配置均为五作业 RTT 增加，且每个作业的配对增幅都大于同组控制漂移。范围不是置信区间；背景发起速率未在各位置固定。', 'small')

    route_page(0, '5 持续背景探针：0→54', '图07_正向干扰', 17)
    route_page(54, '5.1 持续背景探针：54→0', '图08_反向干扰', 29)

    r.page('5.2 干扰的空间分布与分类边界', '只展示 1 KiB 探针；颜色表示 RTT 增幅；两图使用同一色标；箭头仅表示实测背景流。')
    r.image('图09_背景边空间图', '图 9 将已测背景流放回 4×4 几何块网格；未测背景位置不着色', maxheight=267)
    r.table(['具体对照', '1 KiB 探针增幅', '可以得出的信息'], [
        ['0→54；背景块 1→2 与 2→3', '35.353% 与 3.471%', '同一去程候选类别仍有明显位置差异。'],
        ['0→54；背景块 1→5', '35.075%', '无去程同向边仍强干扰；不能只靠同向共边描述。'],
        ['54→0；背景块 1→2', '21.398%', '该流属于 neither_forward，但可与候选回程同向或去程反向重叠。'],
    ], [2, 1.05, 3.1], font=10.5, rowpad=4)
    r.p('neither_forward 的准确含义是“不与两种候选去程路径同向共边”；它不等于完全不共享链路、节点或回程资源。图上的箭头也不是已经测出的探针实际路径。', 'small')

    r.page('5.3 背景强度、基线漂移与干扰', '背景吞吐=源发送字节数／背景源累计周期；是期间平均注入速率，不是即时物理链路占用。')
    r.image('图10_背景强度与漂移', '图 10 1 KiB 探针；左为背景平均吞吐与 RTT 增幅，右为同组最大控制漂移与增幅', maxheight=209)
    gb = ['g0018', 'g0020', 'g0024', 'g0026', 'g0030', 'g0038']
    r.table(['组／探针', '背景块', '背景 B/cycle', '背景发送条数中位数', 'RTT 增幅', '最大控制漂移'], [
        [g+' '+str(int(S[g]['probe_src']))+'→'+str(int(S[g]['probe_dst'])), bgname(S[g]), fmt(S[g]['bg_B_per_cycle'], 6), fmt(S[g]['bg_count_median'], 0), pct(S[g]['effect_pct']), fmt(S[g]['drift_max'])+'%'] for g in gb
    ], [1.25, .9, 1.1, 1.3, .9, 1.15], font=10.3, rowpad=4)
    r.p('背景吞吐取每组 5 作业×2 次处理共 10 次观测的中位数；10 次不是 10 个独立作业。全部背景观测为 0.893–1.450 B/cycle，最短源计时跨度为探针跨度的 1.00313 倍。')
    r.p('强干扰位置的背景流自身也变慢：正向强干扰约 0.90 B/cycle，弱干扰约 1.41–1.45。负载与干扰共同受资源影响，不能把此平均吞吐当成独立原因做因果归因；本次不是等注入强度的路由扫描。', 'small')

    r.page('5.4 批次时序：干扰是否贯穿测量', 'E3；1 KiB 探针 0→54；每点为连续 64 次 RTT 均值，共 32 批。')
    r.image('图11_批次时序', '图 11 先取作业内两次观测的批均值中位数，再跨五作业取中位数；阴影为五作业最小至最大', maxheight=257)
    r.table(['代表组', '无背景完整 RTT', '带背景完整 RTT', '解释'], [
        [g+' '+bgname(S[g]), fmt(S[g]['control_median'], 1), fmt(S[g]['treatment_median'], 1), note] for g, note in [('g0018', '候选 XY 同向边，强干扰'), ('g0020', '候选 XY 同向边，弱干扰'), ('g0026', '无去程同向边，强干扰')]
    ], [1.3, 1.05, 1.1, 2.8], font=10.5)
    r.p('批次曲线可见：上述强／弱干扰在测量期间持续存在，不能只用一次开头或结束握手解释。批均值曲线不提供单次消息的尾延迟，也不能排除批内短时波动。')
    r.p('ready 在背景首批本地完成后发送；探针收到全部 ready 后预热与计时；stop 与最终发送次数元数据均在探针计时后传输。跨核周期比较仍不是全局同步墙钟证明。', 'small')

    r.page('6 为什么 14 个模型项只能得到秩 7', 'E3；24 个配置=12 个背景布局×2 种探针大小；只包含 0→54 与 54→0 两个探针方向。')
    r.p('完整设计矩阵包含：常数项 1 列、消息大小项 1 列，以及 XY／YX 的去程／回程中，同向共边、反向共边、共享内部节点 12 列。独立重算得到 <b>14 列、秩 7</b>。')
    r.sub('本次实际出现的六对完全相同的特征列')
    r.table(['XY 特征', '与它逐配置完全相同的 YX 特征'], [
        ['去程同向共边', '回程反向共边'], ['去程反向共边', '回程同向共边'],
        ['去程共享内部节点', '回程共享内部节点'], ['回程同向共边', '去程反向共边'],
        ['回程反向共边', '去程同向共边'], ['回程共享内部节点', '去程共享内部节点'],
    ], [1, 1.6], font=11, rowpad=6)
    r.p('直观例子：若两列 A、B 的数值总相同，模型 α+aA+bB 只能确定 a+b。a=3、b=7 与 a=6、b=4 的预测完全一样，因此不能分别说明谁贡献了多少延迟。六对重复使 14 列最多剩 8 种模式；其余线性关系又使本次实际秩降到 7。')
    r.p('五次重复提高观测稳定性，不增加新的几何配置，所以不能消除上述重合。最小二乘仍能计算某个解，但该解中的各路径系数不唯一，不应作为物理路径成本发布。')
    r.p('结构原因：相邻背景流的 XY／YX 路径相同，而 XY 去程的逆序就是 YX 回程。因此只增加探针方向、仍只扫相邻背景边，不能消除这六对重合。具体解决方案见第 16 页。', 'small')

    r.page('6.1 候选描述模型的留出误差', '响应为五作业配对 RTT 增幅（%）；最小二乘描述性拟合；RMSE 单位为百分点。')
    r.image('图12_模型误差', '图 12 两种分组留出验证；同一背景布局的两种大小放在同一折', maxheight=211)
    r.table(['模型（均含常数＋大小）', '列数／秩', '拟合 RMSE', '留出背景布局 RMSE', '留出探针方向 RMSE'], [
        [m['model'], str(m['parameters'])+'/'+str(m['rank']), fmt(m['fit_RMSE_pct_points']), fmt(m['leave_layout_out_RMSE_pct_points']), fmt(m['leave_probe_direction_out_RMSE_pct_points'])] for m in D['models']
    ], [2.3, .8, 1, 1.35, 1.35], font=10.2, rowpad=4)
    r.p('留出背景布局为 12 折；留出整个探针方向为 2 折，均不是跨节点验证。两种“任一无向边”指标在本次配置中完全相同，因此 XY 与 YX 模型的误差完全相同，不能据此选出实际路由。')
    r.p('最佳紧凑模型的留出布局 RMSE 仍约 13.62 个百分点；将 XY／YX 去程项都加入反而使留出误差增大。已测干扰差异尚不能被简单“候选共边＋大小”模型充分解释。', 'small')

    r.page('6.2 如何解决路径项无法分别估计', '本页是离线设计检查与新套件准备结果，不是新增硬件测量；保留原始实验与本轮实测数据。')
    r.sub('先改模型，再增加真正不同的路径配置')
    r.p('现有数据分别比较 XY、YX 候选模型；重复项可合并用于预测，但只能解释为共同影响。用正则化或伪逆选出一个数值解，不等于实验已经识别出每个路径系数。')
    r.table(['设计矩阵', '行数', '列数', '秩', '状态／含义'], [
        ['本次 quick 实测配置', '24', '14', '7', '实测；两个方向、每方向六个相邻背景。'],
        *[[d['design'], d['rows'], d['columns'], d['rank'], '仅离线枚举；未提交、未测量。'] for d in D['diagnostics']['offline_design_checks']],
    ], [2.0, .6, .6, .6, 2.5], font=11, rowpad=6)
    r.p('离线枚举沿用当前生成器的几何特征，并排除背景使用探针端点块。结果表明：仅增加探针方向并扫完相邻边，秩仍只有 8；允许全部非端点背景核对，原来两个探针方向的候选矩阵可以达到秩 14。')
    r.table(['可新增的区分信息', '具体做法'], [
        ['同时跨行、跨列的背景', '例如背景块 1→6：XY 为 1→2→6，YX 为 1→5→6。两种假设不再给出相同背景路径；还需搭配反向流和其他位置。'],
        ['独立改变返回部分', '可设计 A→B→C→A 闭环，固定 A→B、改变 C；每个闭环配无背景对照，仅用 A 的计时器。测整圈成本，并重新构造路径特征。'],
        ['上机前的验收', '先桥接并校准软件开销，再选择配置；检查各候选模型的秩、缩放后条件数及分组留出能力；记录背景实际速率。'],
    ], [1.3, 4.5], font=10.5, rowpad=5)
    r.p('已准备独立 rma_route_identify 套件：保留两个探针方向及每方向六个原背景对照，再各加十个跨行、跨列背景。两种探针大小共 64 组、256 项／作业；联合矩阵秩 14，归一化条件数约 27.18。两个方向各自也达到秩 14；尚未上机。', 'small')
    r.p('满秩只消除当前线性模型中的参数重合，不证明路径假设正确；闭环也不能直接提供纯单向延迟。新套件沿用本轮内核和作业内配对，仍需结合留出误差、背景实际速率与重复性判断候选模型。', 'small')

    r.page('7 五个作业中的效应重复性', '同一计算节点 vn043968；布局组打乱，组内 ABBA／BAAB；表格为逐作业内配对增幅。')
    r.image('图13_作业重复', '图 13 每个点对应一个作业；左右图分别为带宽效应与 1 KiB 探针 RTT 效应', maxheight=207)
    gr = ['g0009', 'g0013', 'g0015', 'g0018', 'g0020', 'g0026', 'g0038']
    r.table(['代表组', *[j['job'] for j in D['jobs']]], [
        [g, *[pct(E[g, j['repeat']]['effect_pct']) for j in D['jobs']]] for g in gr
    ], [1.0, 1, 1, 1, 1, 1], font=10.3, rowpad=4)
    r.p('强背景干扰与弱背景干扰在五作业中保持分离；同源 CPE 的带宽提升也保持同号。小幅方向效应需同时看控制漂移和单流归一化，不能把同号直接等同于硬件机制已经确定。')
    r.p('五个作业都在同一节点，所以这里只评估重复运行的一致性，未评估跨节点泛化、系统独占效果或更多负载状态。', 'small')

    r.page('8 新旧绝对性能不能直接拼接', '旧报告：SW39000_RMA测试数据报告_大图版.pdf；新报告保持旧版排版，但测量内核不同。')
    newbw = st.median([float(c['aggregate_value']) for c in CASES if c['group']=='g0001' and c['role']=='control'])
    r.table(['对照条件', '旧报告', '本次补充', '应如何理解'], [
        ['0→1；8 B；完整往返', '约 196.004 cycles\n（原报告 RTT/2=98.002）', fmt(S['g0000']['treatment_median'])+' cycles', '相同消息和核对，软件协议与计时循环不同。'],
        ['0→1；1 KiB；W=1；单流 BW', '6.605557 B/cycle', fmt(newbw, 6)+' B/cycle', '新循环每消息标记序号；不是同一内核的重复测量。'],
        ['本次 8 B／1 KiB 本地完成', '未按本次协议测量', fmt(S['g0000']['control_median'], 1)+'／'+fmt(S['g0001']['control_median'], 1)+' cycles', '数据量差 128 倍，循环耗时仍接近，提示软件固定成本很大。'],
        ['节点与环境', '旧报告 vn024481', '本次 vn043968', '节点、内核及运行状态差异均未通过同作业桥接对照消除。'],
    ], [1.45, 1.45, 1.3, 2.45], font=11, rowpad=7)
    r.sub('源码中可见的额外工作')
    r.p('新内核 tag／check_tag 处理序号与校验字（通过 4 B memcpy）；wait_counter 进行带上限的轮询并执行 memb；探针每次验证序号，每 64 次计时一次。旧内核的固定数据、等待接口与循环组织不同。')
    r.p('这些差异说明新数值包含显著的软件协议成本，但本轮没有逐项消融或目标汇编计时，<b>尚未确定哪一项贡献了多少开销</b>。不能仅凭源码断言 memcpy 或超时检查是唯一原因，也不能把数千 cycles 解释成 router 延迟。')
    r.p('本报告保留新内核内部的配对效应，并明确其协议成本；后续应在同节点、同作业中桥接旧循环／新循环，分别测序号处理、等待、屏障指令及采样开销，再决定哪些数值适合体系结构建模。', 'small')

    r.page('9 数据支持的结论与尚未确定的问题', '结论仅适用于本次 quick 配置、内核、资源请求及 vn043968；未直接观测 router、端口或真实路由。')
    r.table(['研究问题', '本次证据', '结论边界'], [
        ['簇内／簇间是否存在强共享带宽瓶颈？', '两流端点实验：η 约 0.947–0.983；同簇／分簇差异很小；同源 CPE 反而约 +2.97%。', '未证实此配置下同簇独有的强瓶颈；不能排除其他窗口、消息大小、流数或端点位置。'],
        ['方向是否影响并发吞吐？', '反向／同向：横向约 -0.317%，纵向约 -1.144%；候选共边／分开差异更小。', '存在较小方向效应；不足以识别端口数量或半／全双工结构。'],
        ['背景流能否暴露片上共享资源？', '24 个配置均在五作业中增加 RTT；正向最高中位数 +35.353%，反向强干扰约 +21%–23%。', '支持可重复的干扰与位置差异；尚未区分去程、回程、内部节点及其他共享成本。'],
        ['是否确定 XY 或 YX 实际路由？', '同类候选共边效应不同；无去程同向边也强干扰；14 列秩 7，XY／YX 无向指标相同。', '本轮未唯一识别路由；不能将候选几何边称为已观测的物理链路。'],
    ], [1.5, 2.3, 2.3], font=11, rowpad=7)
    r.sub('建议的下一轮独立补充')
    r.p('先校准软件开销并桥接旧／新协议；再增加四个象限的非对称探针与背景布局，事前检验特征秩；对去程和回程采用可区分的实验口径；记录并尽量控制背景注入强度。')
    r.p('如要识别端口结构，应固定源／目标布局，逐步增加 1、2、3、4 条流并扫窗口，保留每条流吞吐与实际请求数，同时用互不复用端点的对照区分发起循环和共享通信资源。', 'small')

    r.page('10 数据完整性、环境与复现依据', '原始结果保持原样；新图表、分析表、审计清单与报告独立保存在 rma_supplement_report_20261007。')
    r.table(['检查项目', '实际记录'], [
        ['原始文件与计划', '1170 个 raw CSV；每作业 234 项；各作业 RUN_COMPLETE 均为 completed_cases=234；配置相同、种子与顺序不同。'],
        ['家族分布', 'E0 9 组／270 文件；E1 4 组／220 文件；E2 4 组／200 文件；E3 24 组／480 文件。E1／E2 包含前后单流参考。'],
        ['正确性与失败记录', '所有核错误计数、wait_stage、background_limit_hit 为 0；预期发送／接收次数匹配；日志没有超时或失败。'],
        ['独立复核', '从原始 CSV 重算 205 个控制、处理、比值与差值，均与随结果提供的 paired_effects.csv 一致。'],
        ['资源与构建', 'q_share；1 MPE／1 CG／64 CPE；cache_size=0 KiB；独占状态未知；swgcc 7.1.0，工具链 SEA-1473；构建日志无输出。'],
        ['缓冲／计时单位', 'source 与 target 各 32768 B；未配置 shared LDM；周期计数器频率未独立标定，不换算 ns／GB/s。'],
        ['程序完整性', '源与二进制 SHA-256 清单保存在 audit.json；源码快照来自实际结果目录 source；本轮没有重跑硬件或修改实验源码。'],
    ], [1.2, 4.7], font=10.6, rowpad=5)
    r.p('验证范围：每个最终接收槽的序号及其余有效载荷字节均检查；探针逐消息检查 8 B 序号头。中间每一次背景传输的全部字节未逐一验证，完成计数也不能代替全字节正确性证明。')
    r.p('数据文件：分析表/group_summary.csv（41 组）、paired_effects_recomputed.csv（205 配对）、cases.csv（1170 项）、background_load.csv、batch_samples.csv、route_models.csv、jobs.csv。audit.json 包含原始文件哈希；report_data.json 为报告数值来源。', 'small')
    r.p('生成程序：rma_supplement/analyze_report_data.py、make_report_charts.py、build_supplement_pdf.py；图表同时提供 PNG 与 SVG。排版参照原横向 A4 大图版：大图、图下数值表、逐页口径与解释。', 'small')
    r.save()
    print(f'Created {r.number} pages: {PDF}')


if __name__ == '__main__':
    main()
