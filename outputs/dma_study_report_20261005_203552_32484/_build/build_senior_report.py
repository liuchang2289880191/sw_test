"""Landscape data report for research discussion; no plans or running instructions."""
from pathlib import Path
import numpy as np
import csv
import zipfile

BASE=Path(__file__).with_name('build_report.py').read_text(encoding='utf-8')
exec(BASE[:BASE.index("p('SW39000 DMA 扩展实验完整分析报告'")])
FIG=OUT/'汇报大图'
sec.page_width=Cm(29.7);sec.page_height=Cm(21)
sec.top_margin=Cm(1.1);sec.bottom_margin=Cm(1.1);sec.left_margin=Cm(1.2);sec.right_margin=Cm(1.2);sec.footer_distance=Cm(.45)
for name,size in [('Normal',12),('Title',24),('Heading 1',17),('Heading 2',14),('Caption',10.5)]:
 st=doc.styles[name];st.font.size=Pt(size);st.paragraph_format.space_after=Pt(4)
 st.paragraph_format.space_before=Pt(0)
doc.styles['Normal'].paragraph_format.line_spacing=1.08
doc.core_properties.title='SW39000 DMA 测试数据报告'
oldtable=table
def table(headers,rows,widths):
 oldtable(headers,rows,widths)
 t=doc.tables[-1]
 for r in t.rows:
  for cell in r.cells:
   for para in cell.paragraphs:
    for run in para.runs:run.font.size=Pt(11)
 spacer=doc.paragraphs[-1]
 spacer.paragraph_format.space_after=Pt(3)
 spacer.paragraph_format.line_spacing=Pt(2)
 spacer.paragraph_format.keep_with_next=True
def big(name,caption):figure(name,caption,width=27.3)
def start(title,condition):
 level=2 if '.' in title.split()[0] else 1
 para=doc.add_heading(title,level=level)
 para.paragraph_format.page_break_before=True
 md.append(('### ' if level==2 else '## ')+title+'\n')
 p(condition)
def fmt_size(s):return f'{s} B' if s<1024 else f'{s//1024} KiB'
LS=sorted({k[3] for k in D if k[0]=='load'})

p('SW39000 DMA 测试数据报告','Title')
p('实验日期 2026年10月5日    作业8420952    数据集 dma_results_20261005_203552_32484')
h('1  测试条件与指标')
p('测量一个核组内主存与从核本地存储器 LDM 之间的搬运。get/iget 为主存 → LDM；put/iput 为 LDM → 主存。四种模式均逐次等待完成，软件未完成请求窗口 W=1。')
table(['条件','取值'],[
 ['平台与编译','cpu revision=sw39000；swgcc/1473；主核 -mhost -O2 -g，从核 -mslave -msimd -O2 -g，链接 -mhybrid -g'],
 ['资源与内存','1个MPE、1个CG、64个CPE；q_share；Cache请求0；共享LDM和实际独占程度未记录'],
 ['活跃核','N=1、2、4、8、16、32、64；活跃ID=0至N−1'],
 ['数据缓冲','LDM数据缓冲128 KiB，128 B对齐；静态LDM132840 B；主存源、目标数组各16 MiB'],
 ['计时','8次预热；S<1 KiB重复10000次，其余1000次；屏障、初始化、校验、输出不计时'],
 ['默认布局','主存槽步长131200 B；identity映射；每轮复用同一主存槽与LDM缓冲'],
],[4.0,23.3])
table(['实验分组','消息大小数量','主存偏移 B','步长×映射数量','案例数'],[
 ['边界细扫','9','0、4、64、124','1×1','1008'],
 ['负载扫描','30','0、4','1×1','1680'],
 ['槽布局对照','8','0、4','4×4','7168'],
],[5.0,4.5,5.0,6.0,6.8])
p('共9856个正式案例、8个正确性检查；179076条活跃核记录，原始与汇总数据一致，errors均为0。')
p('主要结果：128 B、64核 put 偏移4 B的耗时为对齐的11.79倍；128 KiB对齐 put 在4核为21.326 B/cycle、64核为15.381；128 KiB get 的64核带宽受槽布局影响，步长翻倍后下降21.5%。')

start('1.1  消息大小 地址布局与单位','KiB=1024 B。偏移仅作用于主存端，LDM起点始终128 B对齐。')
p('边界细扫：64、96、124、128、132、192、252、256、260 B。负载扫描：8、16、32、64、96、124、128、132、192、252、256、260、384、512、768、1024、1536、2048、3072、4096、6144、8192、12288、16384、24576、32768、49152、65536、98304、131072 B。槽布局对照：64、128、256 B及4、32、64、96、128 KiB。')
table(['布局参数','定义'],[
 ['槽步长','131200、131328、135168、262144 B；每槽可容纳最大消息和偏移，各核槽不重叠'],
 ['identity','slot=tid'],['reverse','slot=63−tid'],
 ['transpose','slot=(tid mod 8)×8+floor(tid/8)'],
 ['shuffle','种子20261005的固定随机排列；改变核到槽的对应，不改变运行顺序'],
 ['主存地址','address=base+slot×stride+offset；src基址0x500001406000，dst基址0x500002408000'],
],[4.5,22.8])
table(['指标','计算方式'],[
 ['完成耗时 cycles/op','核i累计周期Tᵢ；重复次数R；汇总耗时t=max(Tᵢ)/R'],
 ['聚合带宽 B/cycle','BW=N×消息字节数/t；采用活跃核中最慢本地累计周期'],
 ['扩展比','相同模式、大小、偏移、布局下，BW(N)/BW(1)'],
 ['偏移耗时比','t(offset)/t(0)；大于1表示偏移更慢'],
],[5.0,22.3])
p('计数器未独立标定，报告保留cycles与B/cycle。get完成表示数据已进入目标LDM；put完成表示源LDM数据已取走。耗时包含接口、循环与等待开销。当前数据为同一作业内固定顺序测量，不提供独立重复的置信区间。')

start('2  DMA 读取带宽','负载扫描；默认布局；30种消息大小；蓝色为1核，橙色为64核，虚线为主存偏移4 B。')
big('图01_读取带宽','图 1  get 与 iget 的读取吞吐  横轴采用对数刻度，各刻度明确标注B或KiB')
table(['模式','64KiB单核','128KiB单核','64KiB 64核','128KiB 64核','128KiB扩展比'],[
 [m]+[f'{bw("load",m,n,s):.3f}' for n,s in [(1,65536),(1,131072),(64,65536),(64,131072)]]+[f'{bw("load",m,64,131072)/bw("load",m,1,131072):.3f}'] for m in ['get','iget']
],[2.8,4.9,4.9,4.9,4.9,4.9])
p('表中带宽单位均为B/cycle。64核 get 在32至128 KiB约20.85至20.98 B/cycle；单核 get 从64至128 KiB增加7.0%。')

start('2.1  DMA 写入带宽','负载扫描；默认布局；两个标注峰值位于128 B与256 B。128 KiB是最右端的大消息测点。')
big('图02_写入带宽','图 2  put 与 iput 的写入吞吐  峰值尺寸直接用箭头标注')
table(['模式','128B 64核','256B 64核','128KiB单核','128KiB 64核','128KiB扩展比'],[
 [m]+[f'{bw("load",m,n,s):.3f}' for n,s in [(64,128),(64,256),(1,131072),(64,131072)]]+[f'{bw("load",m,64,131072)/bw("load",m,1,131072):.3f}'] for m in ['put','iput']
],[2.8,4.9,4.9,4.9,4.9,4.9])
p('表中带宽单位均为B/cycle。put在124、128、132 B的完成耗时为3570.67、433.75、2731.73 cycles/op；128 B局部耗时低谷形成带宽高峰。')

start('3  并发扩展与共享吞吐','负载扫描；64核聚合带宽除以单核带宽；get与put分色，虚线水平参考值为1。')
big('图03_并发扩展比','图 3  64核相对单核的带宽收益  左为偏移0 B，右为偏移4 B')
table(['大小','get对齐扩展比','put对齐扩展比','get偏移4 B','put偏移4 B'],[
 [fmt_size(s)]+[f'{bw("load",m,64,s,o)/bw("load",m,1,s,o):.2f}' for m,o in [('get',0),('put',0),('get',4),('put',4)]] for s in [8,128,1024,4096,65536,131072]
],[3.3,6.0,6.0,6.0,6.0])
p('小消息 get 的对齐扩展约24.77倍，128 KiB为1.25倍；128 KiB put 为0.85倍，即64核聚合吞吐低于单核。理想线性扩展值为64。')

start('3.1  七档活跃核数的聚合带宽','负载扫描；128 KiB；主存偏移0 B；默认槽布局；活跃ID为0至N−1。')
big('图04_七档核数吞吐','图 4  128 KiB的get与put吞吐  每个柱顶直接标出B/cycle')
table(['活跃核数','get 4KiB','get 64KiB','get 128KiB','put 4KiB','put 64KiB','put 128KiB'],[
 [n]+[f'{bw("load",m,n,s):.3f}' for m in ['get','put'] for s in [4096,65536,131072]] for n in N
],[3.3,4.0,4.0,4.0,4.0,4.0,4.0])
p('表中单位为B/cycle。128 KiB put 在4核为21.326，64核下降至15.381，降低27.9%；get在8核为20.918，接近32核的21.361。4核ID为0、1、2、3。')

for n,title,name in [(1,'4  主存对齐与写入边界','图05_单核写入边界'),(64,'4.1  64核写入边界','图06_64核写入边界')]:
 start(title,f'边界细扫；{n}个活跃核；9种尺寸×4种主存偏移；默认槽布局。')
 big(name,f'图 {5 if n==1 else 6}  {n}核put与iput完成耗时  格内数值为cycles/op，四舍五入到整数；'+('色标为对数刻度' if n==64 else '色标为线性刻度'))
 table(['模式','消息 B','偏移0 B','偏移4 B','偏移64 B','偏移124 B'],[
  [m,s]+[f'{cy("boundary",m,n,s,o):.2f}' for o in [0,4,64,124]] for m in ['put','iput'] for s in [128,256]
 ],[3.3,3.2,5.2,5.2,5.2,5.2])
 p('表中为cycles/op。128 B和256 B的对齐写入明显快于相邻部分块尺寸；64核时偏移惩罚放大，put和iput呈现一致的边界。' if n==64 else '表中为cycles/op。单核128 B put 偏移4 B后从241.00增至385.34，约1.60倍；256 B由252.15增至371.84，约1.47倍。')

start('4.2  偏移惩罚随活跃核数变化','边界细扫；128 B与256 B；耗时比取同模式、同大小、同核数下的偏移值除以对齐值。')
big('图07_偏移惩罚随核数变化','图 7  写入偏移耗时比  颜色对应偏移，实线put、虚线iput')
table(['模式与核数','大小 B','偏移4 B耗时比','偏移64 B耗时比','偏移124 B耗时比'],[
 [f'{m} · {n}核',s]+[f'{cy("boundary",m,n,s,o)/cy("boundary",m,n,s):.3f}' for o in [4,64,124]] for m,n,s in [('put',1,128),('put',64,128),('put',64,256),('get',64,128)]
],[5.0,3.1,6.4,6.4,6.4])
p('128 B、64核 put 偏移4 B耗时增至11.79倍，带宽下降91.5%；同尺寸 get 为1.39倍。单个128 B块内的不同起点与片段大小也会影响写入，不能仅按覆盖块数解释。')

start('5  操作完成耗时与非阻塞接口','负载扫描；默认布局；1核与64核；偏移0 B与4 B；纵轴为对数刻度。')
big('图08_操作完成耗时','图 8  get与put的完成耗时  单位cycles/op，取活跃核中最慢平均值')
table(['模式','单核8至64B最小值','单核8至64B中位数','单核8至64B最大值'],[
 [m,f'{min(cy("load",m,1,s) for s in [8,16,32,64]):.2f}',f'{np.median([cy("load",m,1,s) for s in [8,16,32,64]]):.2f}',f'{max(cy("load",m,1,s) for s in [8,16,32,64]):.2f}'] for m in MODES
],[3.3,8.0,8.0,8.0])
p('表中条件为主存对齐，单位cycles/op。单核小消息读取约441，put约240，iput约234；包含循环和等待开销，完成语义不等同于最终DRAM写入延迟。')

start('5.1  阻塞与非阻塞接口的匹配数据','每档核数匹配30种大小×两种偏移，共60组。iget与iput每次发起后立即等待，W=1。')
table(['核数','iget/get最小','iget/get中位数','iget/get最大','iput/put最小','iput/put中位数','iput/put最大'],[
 [n]+[f'{f([bw("load",a,n,s,o)/bw("load",b,n,s,o) for s in LS for o in [0,4]]):.4f}' for a,b in [('iget','get'),('iput','put')] for f in [min,np.median,max]] for n in N
],[2.7,4.1,4.1,4.1,4.1,4.1,4.1])
p('带宽比大于1表示非阻塞接口更快。全部420组的iget/get中位数为1.0006，iput/put为1.0005；当前逐次等待方式下，两类接口的整体吞吐接近。')
h2('同配置跨阶段的带宽变化')
ov=V['overlap_stats']
table(['阶段对照','匹配配置数','绝对变化中位数','绝对变化P90','绝对变化最大值'],[
 [name,ov[key]['n']]+[f'{ov[key][x]*100:.3f}%' for x in ['median','p90','max']] for name,key in [('boundary → load','boundary_to_load'),('load → mapping','load_to_mapping')]
],[6.3,4.5,5.5,5.5,5.5])
p('绝对变化=|BW后/BW前−1|；匹配模式、大小、核数、偏移和默认布局。该表比较同一作业的不同阶段，不是独立作业重复的误差条。')

for m,s,title,name,number in [('get',256,'6  逐核耗时与空间差异','图09_读取逐核模式',9),('put',131072,'6.1  大消息写入的逐核差异','图10_写入逐核模式',10)]:
 start(title,f'槽布局对照；{m}；{fmt_size(s)}；64核；偏移0 B；步长131200 B。三个面板使用相同色标。')
 big(name,f'图 {number}  identity与reverse的逐核模式  前两图按核ID排列，第三图按实际地址槽重排')
 rs=[r for r in C if r['mode']==m and int(r['bytes'])==s and int(r['offset'])==0 and int(r['slot_stride'])==131200]
 table(['相对identity的映射','按核ID相关系数r','按地址槽相关系数r'],[
  [r['mapping'],f'{float(r["corr_by_pe"]):.4f}',f'{float(r["corr_by_slot"]):.4f}'] for r in rs
 ],[8.3,9.5,9.5])
 p('读取256 B时，换核访问同一槽后，按槽的快慢模式保持一致，r=0.9996至0.9999；按核ID模式改变。' if m=='get' else '写入128 KiB时，换槽后按核ID的快慢模式仍相近，r=0.9760至0.9998；按槽重排后的相关性明显减弱。')
 p('r为64项耗时的Pearson线性相关系数；槽的8×8排列是编号展示，不表示内存物理拓扑。写入色标单位为千cycles/op。' if m=='put' else 'r为64项耗时的Pearson线性相关系数；槽的8×8排列是编号展示，不表示内存物理拓扑。')

start('6.2  槽步长和核到槽排列的吞吐差异','槽布局对照；128 KiB；64核；偏移0 B。固定步长时，四种排列使用相同地址集合。')
big('图11_槽布局与吞吐','图 11  get与put在16种槽布局下的聚合带宽  格内数值及色标单位均为B/cycle')
table(['模式','131200 B identity','131200 B transpose','262144 B identity','16布局最大/最小'],[
 [m,f'{bw("mapping",m,64,131072):.3f}',f'{bw("mapping",m,64,131072,0,131200,"transpose"):.3f}',f'{bw("mapping",m,64,131072,0,262144):.3f}',f'{max(bw("mapping",m,64,131072,0,t,k) for t in T for k in MAPS)/min(bw("mapping",m,64,131072,0,t,k) for t in T for k in MAPS):.3f}'] for m in MODES
],[2.7,6.3,6.3,6.3,5.7])
p('get的identity步长由131200增至262144 B，吞吐由20.848降至16.376，降低21.5%；同一步长改为transpose后降低11.2%。虚拟地址布局影响吞吐，但未确定物理bank或路由机制。')

start('7  大消息拟合参数','默认布局；偏移0 B；模型T(S)=α+βS，T为cycles/op，S为B；斜率吞吐=N/β。')
fits=read(ANA/'model_fits_128k.csv')
table(['模式','核数','拟合大小区间','点数','α cycles','β cycles/B','N/β B/cycle','R²','最大相对误差'],[
 [r['mode'],r['active_pes'],f'{int(r["min_bytes"])//1024}至128 KiB',r['points'],f'{float(r["alpha"]):.2f}',f'{float(r["beta"]):.6f}',f'{float(r["slope_bandwidth"]):.2f}',f'{float(r["r_squared"]):.6f}',f'{float(r["max_relative_fit_error"])*100:.2f}%'] for r in fits
],[2.1,1.8,4.0,1.5,3.6,3.7,3.8,3.5,3.3])
p('单核采用1、2、4、8、16、32、64、128 KiB；64核采用4、8、16、32、64、128 KiB。最大相对误差为拟合点上的|预测/实测−1|。')
p('64核put/iput负截距是大消息区间外推结果，不是负物理延迟。该线性模型描述对齐大消息；128 B和256 B附近的边界需要保留各尺寸与偏移的实测数据。')
h2('代表数据')
table(['测量条件','get','put','单位'],[
 ['单核8至64 B固定耗时','约441','约240','cycles/op'],
 ['128 KiB、1核、对齐',f'{bw("load","get",1,131072):.3f}',f'{bw("load","put",1,131072):.3f}','B/cycle'],
 ['128 KiB、4核、对齐',f'{bw("load","get",4,131072):.3f}',f'{bw("load","put",4,131072):.3f}','B/cycle'],
 ['128 KiB、64核、对齐',f'{bw("load","get",64,131072):.3f}',f'{bw("load","put",64,131072):.3f}','B/cycle'],
 ['128 B、64核、偏移4 B/对齐',f'{cy("boundary","get",64,128,4)/cy("boundary","get",64,128):.3f}',f'{cy("boundary","put",64,128,4)/cy("boundary","put",64,128):.3f}','耗时比'],
],[10.3,5.7,5.7,5.6])

target=OUT/'SW39000_DMA测试数据报告_大图版.docx'; doc.save(target)
(OUT/'DMA测试数据报告_大图版.md').write_text('\n'.join(md).replace('](图表/','](汇报大图/'),encoding='utf-8')
data_dir=OUT/'汇报数据';data_dir.mkdir(exist_ok=True)
allrows=read(SRC/'study_summary.csv')
for name,rows in [('负载扫描.csv',[r for r in allrows if r['phase']=='load']),('边界细扫.csv',[r for r in allrows if r['phase']=='boundary']),('槽布局对照.csv',[r for r in allrows if r['phase']=='mapping'])]:
 with (data_dir/name).open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
for name,rows in [('逐核相关性.csv',C),('大消息拟合.csv',fits)]:
 with (data_dir/name).open('w',newline='',encoding='utf-8-sig') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
with zipfile.ZipFile(OUT/'DMA汇报大图与数据.zip','w',zipfile.ZIP_DEFLATED) as z:
 for directory in [FIG,data_dir]:
  for path in sorted(directory.iterdir()):z.write(path,directory.name+'/'+path.name)
print('Saved:',target)
