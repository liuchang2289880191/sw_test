"""Create a landscape research report from the already audited RMA results."""
from pathlib import Path
from html import escape
from decimal import Decimal, ROUND_HALF_UP
import json
import math
import sys
import numpy as np
import pandas as pd
from PIL import Image as PILImage
CHARTS_ONLY = '--charts-only' in sys.argv
if not CHARTS_ONLY:
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Table, TableStyle, Image

ROOT = Path(__file__).resolve().parents[1]
ANA = ROOT/'outputs/rma_analysis_20261006_194029_17374'
OUT = ROOT/'outputs/rma_report_20261006'
FIG = OUT/'图表'
OUT.mkdir(exist_ok=True); FIG.mkdir(exist_ok=True)
PDF = OUT/'SW39000_RMA测试数据报告_大图版.pdf'
if not CHARTS_ONLY:
    W, H = landscape(A4)
    M = 34
    WIDTH = W-2*M
    NAVY = colors.HexColor('#21435D')
    INK = colors.HexColor('#16222C')
    PALE = colors.HexColor('#F1F5F8')
    GRAY = colors.HexColor('#566472')
    pdfmetrics.registerFont(TTFont('YaHei','C:/Windows/Fonts/msyh.ttc'))
    pdfmetrics.registerFont(TTFont('YaHeiBold','C:/Windows/Fonts/msyhbd.ttc'))
    pdfmetrics.registerFontFamily('YaHei', normal='YaHei', bold='YaHeiBold', italic='YaHei', boldItalic='YaHeiBold')
    STYLES = {
    'body': ParagraphStyle('body',fontName='YaHei',fontSize=11.4,leading=16.5,textColor=INK,wordWrap='CJK'),
    'small': ParagraphStyle('small',fontName='YaHei',fontSize=9.8,leading=14,textColor=GRAY,wordWrap='CJK'),
    'condition': ParagraphStyle('condition',fontName='YaHei',fontSize=10.6,leading=15,textColor=GRAY,wordWrap='CJK'),
    'caption': ParagraphStyle('caption',fontName='YaHei',fontSize=10,leading=14,textColor=INK,wordWrap='CJK',alignment=1),
    'table': ParagraphStyle('table',fontName='YaHei',fontSize=10.5,leading=14,textColor=INK,wordWrap='CJK'),
    'tablehead': ParagraphStyle('tablehead',fontName='YaHeiBold',fontSize=10.5,leading=14,textColor=colors.white,wordWrap='CJK'),
    'sub': ParagraphStyle('sub',fontName='YaHeiBold',fontSize=13,leading=18,textColor=INK,wordWrap='CJK'),
}

def read(name): return pd.read_csv(ANA/'tables'/name)
lm=read('latency_repeats.csv')
bw=read('bandwidth_repeats.csv')
cont=bw[bw.type=='contention'].copy()
pair=bw[bw.type=='bandwidth'].copy()
ratios=read('paired_contention_ratios.csv')
models=read('models.csv')
adjacent=read('adjacent_boundary_latency.csv')
lat_sizes=read('latency_sizes.csv')
replat=read('representative_latency.csv')
variation=read('repeat_variation.csv')
block=read('contention_by_block.csv')
rep_intra=read('intra2_1024B_W1_by_repeat.csv')
p01=read('pair_0_1_bandwidth.csv').set_index('bytes')
CASES=['single','intra2','split_near2','split_side2','split_far2','incast3','ring4','alltoall4']
SHORT=['单流','同块2流','纵邻块2流','横邻块2流','隔行块2流','3流汇入','4流环','12流全互连']
PAIRS=[(0,1),(0,8),(0,9),(1,2),(8,16),(9,18),(0,7),(0,56),(0,63)]
LABELS=['同块横向 0→1','同块纵向 0→8','同块对角 0→9','跨块横向 1→2','跨块纵向 8→16','跨块对角 9→18','远距同行 0→7','远距同列 0→56','远距对角 0→63']

def fmt(x,d=3):
    rounded=Decimal(str(float(x))).quantize(Decimal(1).scaleb(-d),rounding=ROUND_HALF_UP)
    return f'{rounded:.{d}f}'
def size(x): return f'{int(x)} B' if x<1024 else f'{int(x)//1024} KiB'

def make_charts():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    font_manager.fontManager.addfont('C:/Windows/Fonts/msyh.ttc')
    plt.rcParams.update({'font.family':'Microsoft YaHei','font.size':12,'axes.titlesize':14,'axes.labelsize':12,'axes.unicode_minus':False,'legend.fontsize':10.5})
    palette=['#2670AC','#D86624','#38934B','#BD4646','#8961AD','#8B6556','#BF71A6','#667B88','#A7A61C']
    def save(fig,name):
        if '--chart-filter' in sys.argv and name not in sys.argv[sys.argv.index('--chart-filter')+1].split(','):
            plt.close(fig); return
        fig.savefig(FIG/(name+'.png'),dpi=260,bbox_inches='tight',facecolor='white')
        fig.savefig(FIG/(name+'.svg'),bbox_inches='tight',facecolor='white')
        plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11.2,3.7),layout='constrained')
    for (a,b),label,col in zip(PAIRS,LABELS,palette):
        f=pair[(pair.src==a)&(pair.dst==b)&(pair.window==1)].sort_values('bytes')
        axes[0].plot(f.bytes,f['median'],'o-',label=label,ms=3,color=col,lw=1.6)
    axes[0].set_title('W=1；九个代表核对'); axes[0].legend(ncol=2,fontsize=9.3)
    for w,col in zip([1,2,4,8,16],palette):
        f=pair[(pair.src==0)&(pair.dst==1)&(pair.window==w)].sort_values('bytes')
        axes[1].plot(f.bytes,f['median'],'o-',label=f'W={w}',ms=4,color=col)
        axes[1].fill_between(f.bytes,f['min'],f['max'],color=col,alpha=.15)
    axes[1].set_title('0→1；不同请求窗口');axes[1].legend(ncol=2)
    for ax in axes:
        ax.set_xscale('log',base=2);ax.set_xticks([8,64,256,1024,4096,16384,65536],labels=['8 B','64 B','256 B','1 KiB','4 KiB','16 KiB','64 KiB'],rotation=20)
        ax.set_xlabel('消息大小');ax.set_ylabel('有效载荷带宽 (B/cycle)');ax.grid(alpha=.18)
    save(fig,'图01_点对点带宽')

    fig,axes=plt.subplots(1,3,figsize=(11.2,3.4),layout='constrained')
    for s,ax in zip([8,1024,4096],axes):
        for (a,b),label,col in zip(PAIRS,LABELS,palette):
            f=pair[(pair.src==a)&(pair.dst==b)&(pair.bytes==s)].sort_values('window')
            ax.plot(f.window,f['median'],'o-',label=label,color=col,ms=4)
        ax.set_title(size(s));ax.set_xlabel('每条流窗口 W');ax.set_ylabel('带宽 (B/cycle)');ax.grid(alpha=.18)
        ax.set_xscale('log',base=2);ax.set_xticks([1,2,4,8,16],labels=['1','2','4','8','16'])
    h,l=axes[0].get_legend_handles_labels();fig.legend(h,l,loc='outside lower center',ncol=3,fontsize=9.8)
    save(fig,'图02_窗口吞吐')

    for s in [64,1024]:
        fig,axes=plt.subplots(1,2,figsize=(11.2,3.25),layout='constrained')
        for ax,w in zip(axes,[1,4]):
            for j,c in enumerate([0,5,10,15]):
                f=cont[(cont.bytes==s)&(cont.window==w)&(cont.cluster_index==c)].set_index('case').reindex(CASES)
                ax.bar(np.arange(8)+(j-1.5)*.19,f['median'],.19,color=palette[j],label=f'块 {c}',yerr=np.vstack([f['median']-f['min'],f['max']-f['median']]),capsize=2)
            ax.set_xticks(range(8),SHORT,rotation=27,ha='right',fontsize=9.5);ax.set_title(f'W={w}');ax.set_ylabel('聚合带宽 (B/cycle)');ax.grid(axis='y',alpha=.16)
        axes[0].legend(ncol=4,fontsize=9)
        save(fig,f'图0{3 if s==64 else 4}_{s}B争用')

    fig,axes=plt.subplots(1,2,figsize=(11.2,3.8),layout='constrained')
    for ax,w in zip(axes,[1,4]):
        for j,case in enumerate(CASES[2:5]):
            for k,s in enumerate([64,1024]):
                f=ratios[(ratios.window==w)&(ratios.bytes==s)&(ratios.split_case==case)].groupby('cluster_index').split_over_intra.agg(['min','median','max'])
                ax.errorbar(np.arange(4)+(j-1)*.13+(k-.5)*.03,f['median'],yerr=np.vstack([f['median']-f['min'],f['max']-f['median']]),marker='o' if s==64 else 's',ls='none',color=palette[j],capsize=3,label=f'{SHORT[j+2]}，{size(s)}')
        ax.axhline(1,color='#444444',ls='--',lw=1);ax.set_xticks(range(4),['0','5','10','15']);ax.set_xlabel('起始几何块编号');ax.set_ylabel('分散 / 同块 带宽比');ax.set_title(f'W={w}');ax.grid(alpha=.16)
    h,l=axes[0].get_legend_handles_labels();fig.legend(h,l,loc='outside lower center',ncol=3,fontsize=10.5)
    save(fig,'图05_分散相对同块')

    fig,ax=plt.subplots(figsize=(11.2,3.2),layout='constrained')
    for j,repeat in enumerate(['1','2','3']):
        vals=rep_intra[repeat]
        bars=ax.bar(np.arange(4)+(j-1)*.23,vals,.23,label=f'作业 {repeat}',color=palette[j])
        ax.bar_label(bars,labels=[fmt(v,3) for v in vals],padding=3,fontsize=10)
    ax.axhline(11.376451,color='#555555',ls='--',lw=1,label='分散2流，约 11.376')
    ax.set_ylim(0,12.5);ax.set_xticks(range(4),['块 0','块 5','块 10','块 15']);ax.set_ylabel('聚合带宽 (B/cycle)');ax.grid(axis='y',alpha=.16)
    handles,labels=ax.get_legend_handles_labels();fig.legend(handles,labels,loc='outside upper center',ncol=4,fontsize=10)
    save(fig,'图06_逐次逐块争用')

    eight=lm[lm.bytes==8]
    matrix=eight.pivot(index='initiator',columns='peer',values='median').reindex(index=range(64),columns=range(64)).to_numpy()
    def member(c,i):return (c//4*2+i//2)*8+c%4*2+i%2
    order=[member(c,i) for c in range(16) for i in range(4)]
    fig,axes=plt.subplots(1,2,figsize=(11.2,4.1),layout='constrained')
    for ax,mat,title in zip(axes,[matrix,matrix[np.ix_(order,order)]],['按原核 ID 排列','按 2×2 块重排，每块四核']):
        im=ax.imshow(mat,vmin=98,vmax=124,cmap='viridis',interpolation='nearest')
        ax.set_title(title);ax.set_xlabel('目标核 ID' if ax==axes[0] else '目标核重排序号');ax.set_ylabel('发起核 ID' if ax==axes[0] else '发起核重排序号')
        if ax==axes[1]:
            for edge in np.arange(3.5,63,4):ax.axhline(edge,color='white',lw=.3,alpha=.5);ax.axvline(edge,color='white',lw=.3,alpha=.5)
    fig.colorbar(im,ax=list(axes),label='RTT/2 (cycles)',shrink=.9)
    save(fig,'图07_延迟矩阵')

    for sources in [(0,9),(18,27),(36,63)]:
        fig,axes=plt.subplots(1,2,figsize=(11.2,4.1),layout='constrained')
        for src,ax in zip(sources,axes):
            mat=matrix[src].reshape(8,8)
            im=ax.imshow(mat,vmin=98,vmax=124,cmap='viridis',interpolation='nearest')
            ax.set_title(f'源核 {src}，坐标 ({src//8},{src%8})');ax.set_xticks(range(8));ax.set_yticks(range(8));ax.tick_params(labelsize=11)
            ax.set_xlabel('目标列');ax.set_ylabel('目标行')
            for r in range(8):
                for c in range(8):
                    v=mat[r,c];ax.text(c,r,'自身' if np.isnan(v) else fmt(v,1),ha='center',va='center',fontsize=10.5,color='black' if np.isnan(v) or v>111 else 'white')
            for e in [1.5,3.5,5.5]:ax.axhline(e,color='white',lw=.85);ax.axvline(e,color='white',lw=.85)
        fig.colorbar(im,ax=list(axes),label='RTT/2 (cycles)',shrink=.9)
        save(fig,f'图08_多源空间热图_{sources[0]}_{sources[1]}')

    fig,axes=plt.subplots(1,2,figsize=(11.2,4.05),layout='constrained')
    near=lm[(lm.hx+lm.hy)==1]
    for same,label,col in [(1,'同块相邻',palette[0]),(0,'跨块相邻',palette[1])]:
        f=near[near.same_cluster==same].groupby('bytes')['median'].agg(['min','median','max'])
        axes[0].plot(f.index,f['median'],'o-',label=label,color=col);axes[0].fill_between(f.index,f['min'],f['max'],alpha=.15,color=col)
    axes[0].legend();axes[0].set_title('单核 Manhattan 距离固定为一格')
    for (a,b),label,col in zip(PAIRS,LABELS,palette):
        f=lm[(lm.initiator==a)&(lm.peer==b)].sort_values('bytes')
        axes[1].plot(f.bytes,f['median'],'o-',label=label,color=col,ms=3)
    axes[1].set_title('九个代表核对')
    handles,labels=axes[1].get_legend_handles_labels();fig.legend(handles,labels,loc='outside lower center',ncol=3,fontsize=9.8)
    for ax in axes:
        ax.set_xscale('log',base=2);ax.set_xticks([8,16,32,64,128,256],labels=['8','16','32','64','128','256']);ax.set_xlabel('消息大小 (B)');ax.set_ylabel('RTT/2 (cycles)');ax.grid(alpha=.18)
    save(fig,'图09_边界与消息大小')

    fig,ax=plt.subplots(figsize=(11.2,3.35),layout='constrained')
    labels=['常数/大小','跨块指示','单核距离','跨块＋\n单核距离','小簇距离','跨块＋\n小簇距离','异行/异列']
    for j,(scope,label) in enumerate([('8B','仅 8 B'),('all','全部六种大小')]):
        f=models[models.scope==scope]
        bars=ax.bar(np.arange(7)+(j-.5)*.34,f.cv_rmse_cycles,.34,label=label,color=palette[j])
        ax.bar_label(bars,labels=[fmt(v,2) for v in f.cv_rmse_cycles],padding=3,fontsize=10)
    ax.set_xticks(range(7),labels,fontsize=11);ax.set_ylabel('五折交叉验证 RMSE (cycles)');ax.legend();ax.grid(axis='y',alpha=.18);ax.set_ylim(0,6.35)
    save(fig,'图10_模型误差对照')


class Report:
    def __init__(self):
        self.c=canvas.Canvas(str(PDF),pagesize=(W,H),pageCompression=1)
        self.c.setTitle('SW39000 RMA 测试数据报告');self.c.setAuthor('RMA benchmark data analysis')
        self.number=0;self.y=H-M;self.metrics=[]
    def page(self,title,condition='',first=False):
        if self.number:self.end_page()
        self.number+=1;self.y=H-M
        self.c.bookmarkPage(f'p{self.number}');self.c.addOutlineEntry(title,f'p{self.number}',level=0)
        self.c.setFillColor(INK);self.c.setFont('YaHeiBold',23 if first else 18)
        self.c.drawString(M,self.y-(25 if first else 21),title)
        self.y-=37 if first else 32
        if condition:self.p(condition,'condition',after=9)
    def flow(self,f,after=6):
        _,h=f.wrap(WIDTH,self.y-36)
        if self.y-h<36:raise ValueError(f'Page {self.number} overflow: {self.y-h:.1f} pt, object={type(f).__name__}')
        f.drawOn(self.c,M,self.y-h);self.y-=h+after
    def p(self,text,style='body',after=7):self.flow(Paragraph(text,STYLES[style]),after)
    def sub(self,text):self.p(text,'sub',after=6)
    def table(self,heads,rows,widths=None,font=10.5,rowpad=5):
        if widths is None:widths=[1]*len(heads)
        widths=[WIDTH*w/sum(widths) for w in widths]
        ps=ParagraphStyle('cell',parent=STYLES['table'],fontSize=font,leading=font+3.2)
        hs=ParagraphStyle('head',parent=STYLES['tablehead'],fontSize=font,leading=font+3.2)
        data=[[Paragraph(escape(str(v)),hs) for v in heads]]
        for row in rows:data.append([Paragraph(escape(str(v)),ps) for v in row])
        t=Table(data,colWidths=widths,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PALE]),('GRID',(0,0),(-1,-1),.35,colors.HexColor('#C7D0D7')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),rowpad),('BOTTOMPADDING',(0,0),(-1,-1),rowpad)]))
        self.flow(t,after=7)
    def image(self,name,caption,maxheight=275):
        path=FIG/(name+'.png')
        with PILImage.open(path) as im: iw,ih=im.size
        scale=min(WIDTH/iw,maxheight/ih)
        image=Image(str(path),width=iw*scale,height=ih*scale)
        _,height=image.wrap(WIDTH,self.y)
        if self.y-height<36:raise ValueError('Image overflow')
        image.drawOn(self.c,M+(WIDTH-image.drawWidth)/2,self.y-height)
        self.y-=height+4;self.p(caption,'caption',after=6)
    def end_page(self):
        self.metrics.append({'page':self.number,'bottom_content_y':round(self.y,1)})
        self.c.setFillColor(GRAY);self.c.setFont('YaHei',9.3)
        self.c.drawCentredString(W/2,15,f'第 {self.number} 页')
        self.c.showPage()
    def save(self):
        self.end_page();self.c.save()
        (OUT/'layout_audit.json').write_text(json.dumps(self.metrics,ensure_ascii=False,indent=2),encoding='utf-8')


def make_report():
    r=Report()
    r.page('SW39000 RMA 测试数据报告','实验日期 2026年10月6日    作业 8433994 / 8433995 / 8433997    队列 q_share',first=True)
    r.sub('1  测试条件与数据复核')
    r.p('本次测量一个核组内从核 LDM 之间的 RMA 通信：全核对 ping-pong 延迟、代表核对 iput 带宽、未完成请求窗口，以及多流争用。报告只使用正式阶段 raw，先匹配同一配置，再统计三次作业结果。')
    r.table(['条件','本次记录'],[
        ['平台与编译','cpu revision=sw39000；swgcc/1473；target=sw_64sw6a-sunway-linux-gnu'],
        ['资源与节点','1 MPE、1 CG、64 CPE；三次均为 vn024481；cache 请求为 0 KiB'],
        ['实际共享状态','实际独占程度、实际 cache/LDM 和共享 LDM 未确认；q_share 名称不能证明独占'],
        ['缓冲与频率','源/目标 RMA LDM 缓冲各 64 KiB；静态 LDM 133736 B 告警；计数器频率未独立标定'],
        ['重复与顺序','三次独立提交；正式配置集合相同、顺序不同；每次 548 个正式案例和 18 个 smoke'],
    ],[1.3,8.7])
    r.table(['实验分组','扫描内容','每次正式配置','三次数据记录'],[
        ['全核对延迟','4032 个有向核对 × 6 种消息大小','6','72576 条核对记录'],
        ['点对点带宽','9 个核对 × 合法的大小/窗口组合','414','1242 条聚合记录'],
        ['争用对照','8 模式 × 2 大小 × 2 窗口 × 4 起始块','128','384 条聚合记录'],
    ],[1.6,4.9,1.5,2])
    r.p('共复核 1698 个原始 CSV，errors 均为 0；核对集合、活跃核集合、原始与汇总数据以及聚合带宽公式一致。数据目录：rma_results_20261006_194029_17374。','small')
    r.p('<b>主要结果：</b>8 B 同块延迟 98.002 cycles，跨边界相邻核中位数 102.003；64 KiB 点对点带宽约 24.499 B/cycle；1 KiB 的 W=1→16 提升约 2.27 倍；分散两条流在 W=4 时基本没有吞吐收益。')

    r.page('1.1  测量定义、消息大小与流量布局','KiB=1024 B。RMA 带宽测试使用 iput；延迟是往返耗时 RTT 的一半。')
    r.table(['指标/参数','计算与含义'],[
        ['延迟 L，cycles','L=总 RTT 周期/(2×重复次数)。4 次预热后计时 2000 次 ping-pong；包含接口、reply 等待和对端响应。'],
        ['带宽 BW，B/cycle','BW=消息字节数×2000×流数/活跃核最大累计周期。每条流预热一次；包含发起循环、本地与远端等待。'],
        ['窗口 W','每条流每批发起 W 次再等待本地完成；窗口槽独立，下一批复用。alltoall4 每核 3 条出流，最多 3W 个请求。'],
        ['核与几何块','id=8r+c；块编号=4 floor(r/2)+floor(c/2)。A/B/C/D 分别为块内左上/右上/左下/右下。'],
    ],[1.5,8.5],font=10.6,rowpad=4)
    r.p('延迟消息：8、16、32、64、128、256 B。带宽消息：8、16、32、64、128、256 B及1、4、16、32、64 KiB；W=1、2、4、8、16，仅测 bytes×W≤64 KiB 的组合。争用：64 B、1 KiB；W=1、4；起始块 0、5、10、15。','body')
    r.table(['模式','有向流数','布局定义'],[
        ['single','1','A→B'],['intra2','2','同块 A→B 与 C→D'],
        ['split_near2','2','两条块内 A→B，分布于纵向相邻块'],
        ['split_side2','2','两条块内 A→B，分布于横向相邻块'],
        ['split_far2','2','两条块内 A→B，分布于相隔两行的几何块'],
        ['incast3','3','B/C/D→A'],['ring4','4','A→B→D→C→A'],['alltoall4','12','四核两两有向通信，每核 3 条出流'],
    ],[2.2,.9,6.9],font=10.2,rowpad=3)
    r.p('屏障在计时外。带宽以本核周期差的最大值汇总，并非跨核同步测得的全局墙钟跨度。RTT/2 混合双向成本，不能直接视为纯单向链路延迟。几何块与距离用于数据分类，不代表已观测到物理 router 或路由。','small')

    r.page('2  RMA 点对点带宽','正式带宽阶段；九个代表核对；每条流 2000 次；柱表和曲线均采用三次作业中位数。')
    r.image('图01_点对点带宽','图 1  左：W=1 的空间对照；右：0→1 的窗口扫描，阴影为三次最小至最大',maxheight=282)
    rows=[]
    for s in [1024,4096,16384,65536]:
        vals=[p01.loc[s,str(w)] for w in [1,4,16]]
        rows.append([size(s)]+['未测' if pd.isna(v) else fmt(v) for v in vals])
    r.table(['消息大小','0→1，W=1','0→1，W=4','0→1，W=16'],rows,[1.7,2.7,2.7,2.7],rowpad=4)
    r.p('带宽单位为 B/cycle。64 KiB、W=1 九个核对均为 24.499247；全部测试配置的最高中位数约 24.508。同一大小和窗口下，九个核对的最大空间带宽差异仅 0.552%，大消息曲线基本重合。')
    r.p('“未测”由缓冲容量限制产生，不表示带宽为零。此结果是单核组内点对点有效载荷吞吐，不能外推为全芯片理论带宽。','small')

    r.page('2.1  未完成请求窗口与小消息吞吐','W 是每条流的批内请求数；九个核对采用相同颜色；横轴为对数刻度。')
    r.image('图02_窗口吞吐','图 2  8 B、1 KiB、4 KiB 的窗口扫描；曲线重叠为测量现象',maxheight=294)
    rows=[]
    for s in [8,1024,4096]:
        vals=[p01.loc[s,str(w)] for w in [1,2,4,8,16]]
        rows.append([size(s)]+[fmt(v,4) for v in vals]+[fmt(vals[-1]/vals[0],3)+' 倍'])
    r.table(['0→1 大小','W=1','W=2','W=4','W=8','W=16','W16/W1'],rows,[1.6,1.4,1.4,1.4,1.4,1.4,1.5],font=10.4,rowpad=5)
    r.p('表中带宽单位 B/cycle。8 B 的窗口增益为 1.853 倍；1 KiB 为 2.271 倍；4 KiB 由 14.948 提高到 24.342。窗口影响明显大于九个核对间的空间差异。')
    r.p('增加 W 可分摊发起和等待开销，但本次采用批量发起后等待，且 W≤16；这些测点不能单独确定硬件队列深度或最大 outstanding 数。','small')

    agg=block.groupby(['bytes','window'])[CASES].median()
    for s,title,fig,num in [(64,'3  多流争用与共享吞吐','图03_64B争用',3),(1024,'3.1  1 KiB 的多流聚合带宽','图04_1024B争用',4)]:
        r.page(title,f'消息 {size(s)}；起始块 0、5、10、15；左 W=1，右 W=4；柱高为三次中位数，误差线为最小至最大。')
        r.image(fig,f'图 {num}  八种流量模式的逐位置聚合带宽；模式定义见第 2 页',maxheight=232)
        rows=[]
        for name,label in zip(CASES,SHORT):
            v1=agg.loc[(s,1),name];v4=agg.loc[(s,4),name]
            rows.append([name+' / '+label, {'single':1,'intra2':2,'split_near2':2,'split_side2':2,'split_far2':2,'incast3':3,'ring4':4,'alltoall4':12}[name],fmt(v1),fmt(v4),fmt(v4/v1,3)+' 倍'])
        r.table(['模式','有向流数','W=1，B/cycle','W=4，B/cycle','W4/W1'],rows,[3.5,.8,1.7,1.7,1.5],font=10.4,rowpad=2)
        r.p('表中先取各位置三次中位数，再跨四个位置取中位数。' + ('64 B 同块两流与分散两流接近；增加窗口同时提高各模式吞吐。多流缩放未达到流数的理想线性值。' if s==64 else 'W=4 同块两流约 18.785，是单流 11.974 的 1.569 倍；分散两流也约 18.785。全互连共有 12 条流，吞吐约 23.948，并非单流的 12 倍。'),'body',after=4)

    r.page('3.2  分散两条流是否缓解同块争用','每个比值匹配同一作业、消息大小、窗口和起始块；比值大于 1 表示分散流量更快。')
    r.image('图05_分散相对同块','图 5  点为三次比值中位数，误差线为最小至最大；两面板纵轴范围不同',maxheight=275)
    rows=[]
    for s,w in [(64,1),(64,4),(1024,1),(1024,4)]:
        f=ratios[(ratios.bytes==s)&(ratios.window==w)]
        med=f.groupby('split_case').split_over_intra.median()
        rows.append([size(s),w]+[fmt(med[c],6) for c in CASES[2:5]]+[f'{f.split_over_intra.min():.6f} 至 {f.split_over_intra.max():.6f}'])
    r.table(['大小','W','纵邻块 / 同块','横邻块 / 同块','隔行块 / 同块','全部配对范围'],rows,[.9,.4,1.7,1.7,1.7,2.4],font=10.1,rowpad=4)
    r.p('每类中位数包含三次×四位置共 12 个配对比值；范围不是置信区间。64 B、W=1 分散约快 0.38%；1 KiB、W=1 的汇总中位数约快 2.1%，但收益不是所有位置一致。1 KiB、W=4 的比值中位数接近 1.0000。')
    r.p('分散流量未使两流吞吐成倍恢复，不能仅从多流缩放不足归因于同簇 router 独有的瓶颈。流量模式还改变端点复用、发起循环与每核请求数。','small')

    r.page('3.3  位置差异与作业间切换','intra2；1 KiB；W=1；每条流 2000 次。三个独立作业均运行在 vn024481。')
    r.image('图06_逐次逐块争用','图 6  同块两流的逐次逐位置带宽；虚线为分散两流约 11.376 B/cycle',maxheight=255)
    r.table(['起始块','作业 8433994','作业 8433995','作业 8433997','三次带宽极差/中位数'],[
        [int(row.cluster_index),fmt(row['1'],6),fmt(row['2'],6),fmt(row['3'],6),fmt((max(row['1'],row['2'],row['3'])-min(row['1'],row['2'],row['3']))/np.median([row['1'],row['2'],row['3']])*100,3)+'%'] for _,row in rep_intra.iterrows()
    ],[1,2.2,2.2,2.2,2.5],font=10.5)
    r.p('单位 B/cycle。同块两流存在约 10.899 和 11.376 两个观测水平。块 0 三次接近分散结果；块 5 三次约低 4.2%（分散/同块约提高 4.38%）；块 10、15 在不同作业中切换。因此，这些差异不能全部解释为固定核位置属性。')
    r.p('从四位置的中位数汇总得到的约 2.1% 收益，会掩盖近零收益和约 4.38% 收益并存的情况。此页保留每次观测；W=4 时对应的分散收益基本消失。')

    r.page('4  全核对延迟矩阵','8 B；64×63 个有向核对；每核对为三次作业中位数；自身通信未测量，留白。')
    r.image('图07_延迟矩阵','图 7  原核 ID 顺序与几何 2×2 分块重排；两图使用同一色标',maxheight=312)
    e=lm[lm.bytes==8]
    r.table(['8 B 分组','有向核对数','最小值','中位数','最大值'],[
        [label,len(f),fmt(f['median'].min()),fmt(f['median'].median()),fmt(f['median'].max())] for same,label in [(1,'同一几何块'),(0,'不同几何块')] for f in [e[e.same_cluster==same]]
    ],[2,1.5,2,2,2])
    r.p('单位 cycles，口径 RTT/2。同块全部 192 个核对均为 98.002；跨块包含多种远近距离，不能把跨块整体中位数与同块的差值当成纯边界惩罚。按块重排呈现清晰的低延迟对角块。')

    for j,sources in enumerate([(0,9),(18,27),(36,63)]):
        r.page(f'4.{j+1}  空间延迟分布：源核 {sources[0]} 与 {sources[1]}','8 B；目标按 id=8r+c 排列；白线为几何 2×2 块界；三页使用同一色标。')
        r.image(f'图08_多源空间热图_{sources[0]}_{sources[1]}',f'图 8{chr(97+j)}  格内值为 RTT/2，单位 cycles；自身通信留白',maxheight=306)
        rows=[]
        for src in sources:
            for same,label in [(1,'同块目标'),(0,'跨块目标')]:
                f=lm[(lm.bytes==8)&(lm.initiator==src)&(lm.same_cluster==same)]
                rows.append([src,label,len(f),fmt(f['median'].min()),fmt(f['median'].median()),fmt(f['median'].max())])
        r.table(['源核','目标分组','目标数','最小 cycles','中位数 cycles','最大 cycles'],rows,[.7,1.6,.9,2,2,2],font=10.5,rowpad=4)
        r.p('低延迟区随源核所在小簇移动，远处总体更慢；同行、同列成本并不完全相同。几何图展示测量位置，未直接观测路由、端口或共享管理部件。','small',after=0)

    r.page('4.4  固定距离的 2×2 边界对照','同块相邻与跨块相邻的单核 Manhattan 距离均为一格；右图同时保留九个代表核对。')
    r.image('图09_边界与消息大小','图 9  左图阴影为不同核对三次中位数的空间最小至最大，不是重复误差；右图为代表核对',maxheight=265)
    rows=[]
    for same,rd,label in [(1,0,'同块横向'),(0,0,'跨块横向'),(1,1,'同块纵向'),(0,1,'跨块纵向')]:
        row=adjacent[(adjacent.bytes==8)&(adjacent.same_cluster==same)&(adjacent.row_distance==rd)].iloc[0]
        rows.append([label,int(row['count'])]+[fmt(row[k],4) for k in ['min','median','mean','max']])
    r.table(['8 B，相邻核','核对数','最小','中位数','均值','最大'],rows,[1.7,.8,1.7,1.7,1.7,1.7],font=10.5,rowpad=4)
    r.p('单位 cycles。同块相邻均为 98.002；跨块相邻中位数 102.0025，增加 4.0005 cycles，约 4.08%。跨块不同位置可达 105.002，说明“4 cycles”是中位数差，不是所有边界统一的精确固定代价。')

    r.page('5  消息大小与操作完成耗时','下表均为三次作业中位数；延迟是 RTT/2，单位 cycles。延迟矩阵扫描至 256 B。')
    r.sub('九个代表核对')
    rows=[]
    for i,row in replat.iterrows():
        rows.append([LABELS[i]]+[fmt(row[str(s)],3) for s in [8,16,32,64,128,256]])
    r.table(['核对/几何关系','8 B','16 B','32 B','64 B','128 B','256 B'],rows,[2.65,1,1,1,1,1,1],font=10.5,rowpad=3)
    r.sub('全矩阵分布：每种大小含 4032 个核对')
    r.table(['大小','最小值','中位数','均值','最大值'],[
        [size(row.bytes)]+[fmt(row[k],3) for k in ['min','median','mean','max']] for _,row in lat_sizes.iterrows()
    ],[1.4,2.1,2.1,2.1,2.1],font=10.5,rowpad=3)
    r.p('8-32 B 整体分布接近；64-256 B 随消息增大总体上升。同块对角 0→9 的 8 B 延迟也为 98.002，与横向和纵向相邻核一致。远距离 0→63 的 8 B 为 123.002。')
    r.p('个别核对并不严格随大小单调增加，例如 8→16 核对的 32 B 为 105.002、64 B 为 102.006。统一 α+βS 不能精确解释每个点，也不能将局部下降换算成负的字节传输代价。','small')

    r.page('5.1  同配置跨作业变化与数据一致性','极差百分比=(三次最大值-最小值)/三次中位数×100%；统计单位为匹配配置。')
    names={'latency':'延迟：大小×有向核对','bandwidth_pair':'点对点带宽','contention':'争用带宽'}
    r.table(['指标','匹配配置数','极差中位数','极差 P90','极差最大值'],[
        [names[row.metric],int(row.configurations)]+[fmt(row[k],6)+'%' for k in ['median_range_pct','p90_range_pct','max_range_pct']] for _,row in variation.iterrows()
    ],[2.9,1.3,1.8,1.8,1.8],font=11,rowpad=7)
    r.sub('延迟矩阵的原始文件完全一致')
    r.p('8、16、32、64、128、256 B 的正式延迟矩阵，三次对应原始 CSV 均逐字节相同，每种大小的唯一 SHA-256 哈希数均为 1。这不是中位数汇总或显示舍入造成的相同，而是输入文件中实际存在的现象。')
    r.p('因此，这批输入不能给出非零的作业间延迟散布估计；零观测极差不能证明硬件没有噪声。现有数据也不能确定矩阵完全一致的具体原因。三个作业全部在 vn024481，且提交时间紧邻。')
    r.sub('争用带宽中波动最大的配置')
    highest=cont.sort_values('range_pct',ascending=False).head(5)
    r.table(['模式','大小 / W / 块','最小 B/cycle','最大 B/cycle','极差/中位数'],[
        [row['case'],f'{size(row.bytes)} / {int(row.window)} / {int(row.cluster_index)}',fmt(row['min'],6),fmt(row['max'],6),fmt(row.range_pct,3)+'%'] for _,row in highest.iterrows()
    ],[1.5,2.2,2.2,2.2,1.7],font=10.5,rowpad=5)
    r.p('误差线均为观测最小至最大，不是置信区间。点对点带宽跨作业极差很小，争用最大极差约 4.374%；报告没有把循环内 2000 次操作当成 2000 个独立实验。','small')

    r.page('6  延迟描述模型的误差对照','最小二乘拟合；按无向核对分五折，同一核对的两方向及所有大小均放在同一折。')
    r.image('图10_模型误差对照','图 10  核对分组交叉验证 RMSE，数值越小表示留出核对预测更接近',maxheight=245)
    m8=models[models.scope=='8B'].reset_index(drop=True)
    names=['常数基线','仅跨块指示','单核行列距离','跨块＋单核距离','小簇行列距离','跨块＋小簇距离','异行/异列指示']
    r.table(['8 B 模型','参数数','R²','拟合 RMSE','五折 RMSE'],[
        [names[i],int(row.parameters),fmt(row.r2,4),fmt(row.rmse_cycles,4),fmt(row.cv_rmse_cycles,4)] for i,row in m8.iterrows()
    ],[3.1,.8,1.6,1.8,1.8],font=10.5,rowpad=2)
    r.p('RMSE 单位 cycles。小簇距离模型的五折 RMSE≈1.067，单核距离模型≈2.339；只区分是否跨块的模型≈5.132。单个固定跨块惩罚不足以解释跨块核对的远近差异。','body',after=3)
    r.p('该交叉验证评估留出核对，不是跨节点验证；联合六种大小模型额外加入线性消息大小项。','small',after=0)

    r.page('6.1  模型参数、代表数据与结论','本页参数适用于本次 SW39000 环境、内核和资源请求；几何距离不能直接称为物理跳数。')
    r.p('定义：bx=|floor(cs/2)-floor(cd/2)|；by=|floor(rs/2)-floor(rd/2)|；cross=不同小簇的指示量。单核距离 hx=|cs-cd|、hy=|rs-rd|；cs/cd 是源/目标列坐标，rs/rd 是行坐标。')
    r.table(['消息范围 / 模型','经验公式，L 单位 cycles','五折 RMSE'],[
        ['8 B，小簇距离','L≈98.480+3.965 bx+4.355 by','1.067'],
        ['8 B，跨块＋小簇距离','L≈98.002+0.611 cross+3.924 bx+4.315 by','1.061'],
        ['8-256 B，大小＋小簇距离','L≈97.977+0.035456 S+3.974 bx+4.033 by；S 为 B','1.154'],
    ],[2.1,6.2,1.2],font=11,rowpad=7)
    r.p('加入 cross 后，8 B RMSE 从约 1.067 降至 1.061，改善很小。较有效的描述是近端基线加小簇行列距离项；完整系数、拟合误差及联合模型保存在 models.csv。')
    r.sub('代表测量结果')
    r.table(['测量条件','结果','单位'],[
        ['8 B，同块全部 192 个核对','98.002','cycles，RTT/2'],
        ['8 B，跨块相邻核中位数','102.0025','cycles，RTT/2'],
        ['64 KiB，九个代表核对，W=1','24.499247','B/cycle'],
        ['1 KiB，0→1，W=1 / W=16','6.605557 / 14.999048','B/cycle'],
        ['1 KiB，同块2流 / 分散2流，W=4','约 18.785 / 约 18.785','B/cycle'],
    ],[5.1,2.7,2.2],font=10.8,rowpad=5)
    r.p('<b>数据支持的结论：</b>小消息延迟应保留 2×2 几何层次；点对点带宽主要受消息大小与窗口影响；本轮没有证实同簇 router 独有的强带宽瓶颈。实际路由和端口结构未被直接测量。')
    r.p('<b>数据依据：</b>summary.csv、latency.csv、三次 plan.csv、全部 raw/smoke CSV、资源与构建记录，以及随结果保存的主从核源码。最终缓冲校验使用每 256 B 重复的数据模式，不能证明每次中间传输的所有字节均已验证。报告保留 cycles/B/cycle，未用未标定频率换算 ns 或 GB/s。','small',after=0)
    r.save()
    print(f'Saved: {PDF}; pages={r.number}')

if __name__=='__main__':
    if '--report-only' not in sys.argv:make_charts()
    if not CHARTS_ONLY:make_report()
