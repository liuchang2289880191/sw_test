"""Seven primary sections aligned with the user-provided baseline PDF."""
from pathlib import Path
import numpy as np
import csv
import json
import zipfile

BASE=Path(__file__).with_name('build_report.py').read_text(encoding='utf-8')
# Reuse its source-grounded table/figure components and the reference typography.
exec(BASE[:BASE.index("p('SW39000 DMA 扩展实验完整分析报告'")])
FIG=OUT/'结构对齐图表'
doc.core_properties.title='SW39000 DMA 扩展实验结果分析'
def take(start,end):return BASE[BASE.index(start):BASE.index(end)]
def emit(text):exec(text,globals())
def cont(title):page();h2(title)

p('SW39000 DMA 扩展实验结果分析','Title')
p('实验日期 2026年10月5日    作业 8420952    队列 q_share')
p('本实验测量一个核组内主存与从核 LDM 之间的 DMA，覆盖 8 B 至 128 KiB 消息、七档负载与多种地址布局。结果表明：128 B 对齐写入的边界显著，偏移代价随并发放大；大消息读取接近吞吐平台，写入则在较高核数下下降。读写开销、对齐条件和核到地址的对应关系应分别进入模型。')
h('1  实验配置与数据复核')
h2('1.1  平台 接口与完整实验矩阵')
p('主核 MPE 负责控制，从核 CPE 执行搬运；日志中的 SPE 也是从核标识。CG 为核组，本实验只使用一个 CG 的 64 个 CPE。LDM 为从核本地存储器；get/iget 将主存 src 读入 LDM，put/iput 将 LDM 写到独立主存 dst。非阻塞接口每次发起后立即等待，四种模式的软件请求窗口均为 W=1。')
table(['项目','本次记录'],[
 ['平台与编译','cpu revision=sw39000  SPE 2250 MHz  MPE 2100 MHz\nswgcc/1473  GCC 7.1.0  目标 sw_64sw6a-sunway-linux-gnu'],
 ['编译选项','主核 -mhost -O2 -g  从核 -mslave -msimd -O2 -g\n链接 -mhybrid -g'],
 ['资源与 LDM','MPE=1  CG=1  CPE=64  请求 -cache_size 0\n静态 LDM 132840 B  共享 LDM 配置及资源独占程度未确认'],
],[3.0,14.4])
table(['阶段','大小数','偏移 B','步长数×排列数','案例数'],[
 ['boundary 边界','9','0 4 64 124','1×1','1008'],
 ['load 负载','30','0 4','1×1','1680'],
 ['mapping 映射','8','0 4','4×4','7168'],
],[3.6,2.0,3.0,4.6,4.2])
p('各阶段均包含 get、put、iget、iput 四种模式和 N=1、2、4、8、16、32、64 七档负载。N 表示计时的活跃核数，ID 固定为 0 至 N−1。边界组大小为 64、96、124、128、132、192、252、256、260 B。负载组的全部大小以 B 列出：8、16、32、64、96、124、128、132、192、252、256、260、384、512、768、1024、1536、2048、3072、4096、6144、8192、12288、16384、24576、32768、49152、65536、98304、131072。映射组大小为 64、128、256、4096、32768、65536、98304、131072 B。')
h2('数据复核')
p('正式案例 9856 项，另有四种模式×1核或64核的 8 项正确性检查，大小 8 B、重复 10 次。独立交叉复核 179076 条活跃核记录与 8448 条扩展比及效率记录，计划、原始数据和汇总一致，errors 均为0，完成标记均记9856。')
p('数据模式为 (tid×17+j×13+7) mod 256。读模式检查最后的 LDM 内容，写模式在 join 后检查主存 dst，计时循环记录接口返回错误。校验覆盖最终内容，未逐轮验证数据时序。q_share 名称本身不证明独占；平台参数也不直接迁移为 SW26010Pro 参数。')

cont('1.2  计时与完成条件')
p('每项先预热 8 次，S<1 KiB 重复 R=10000 次，其余 R=1000 次。各核预热后同步，再用 athread_stime_cycle() 记录本地循环起止周期。计时包含调用、循环、返回码检查与完成等待；屏障、初始化、spawn/join、校验和输出位于计时区外。全部64核启动，非活跃核只参加计时区外的同步和结果回写。')
table(['指标','定义'],[
 ['逐核耗时','Tᵢ=endᵢ−beginᵢ  tᵢ=Tᵢ/R'],
 ['汇总 cycles/op','tmax=max(Tᵢ)/R  取活跃核中最慢均值'],
 ['聚合带宽 B/cycle','BW=N×S×R/max(Tᵢ)=N×S/tmax'],
 ['扩展比与效率','Speedup=BW(N)/BW(1)  Efficiency=Speedup/N'],
 ['偏移耗时比','tmax(offset)/tmax(0)  大于1表示偏移更慢'],
],[4.5,12.9])
p('扩展比匹配模式、大小、偏移、步长与排列。聚合带宽采用最大本地累计周期，不直接相加各核带宽，也未另测全组共同起止时间；各核记录自身经过的周期，不要求绝对计数器起点同步。它是有效载荷吞吐，不含硬件协议及分段流量。')
p(f'示例：boundary 的 128 B、64 核、对齐 put，R=10000，最大累计周期为 {int(row("boundary","put",64,128)["cycles"]):,}，故 cycles/op={cy("boundary","put",64,128):.4f}，BW=64×128/{cy("boundary","put",64,128):.4f}={bw("boundary","put",64,128):.4f} B/cycle。')
h2('单核小消息完成开销')
table(['模式','大小区间','cycles/op 范围','中位数 cycles/op'],[
 [m,'8至64 B',f'{min(cy("load",m,1,s) for s in [8,16,32,64]):.2f} 至 {max(cy("load",m,1,s) for s in [8,16,32,64]):.2f}',f'{np.median([cy("load",m,1,s) for s in [8,16,32,64]]):.2f}'] for m in MODES
],[2.4,3.0,6.4,5.6])
p('以上为 load 阶段、偏移0 B、默认步长和 identity 排列。读取约441 cycles，写入约234至240 cycles；没有扣除空循环，不能视为纯硬件启动延迟。供应方完成表示源 LDM 数据已取走，获取方完成表示目标 LDM 已收到；put/iput 不直接测量每轮最终 DRAM 提交延迟。')
p('KiB=1024 B。原始周期与 B/cycle 为主要结果；仅当计数器按 SPE 2.25 GHz 递增时，ns=cycles÷2.25，十进制 GB/s=BW×2.25。计数器未独立标定，cpuinfo 的 timer frequency 100 Hz 不是此计数器频率。')

emit(take("page();h('4  主存地址槽与核到槽的映射')","page();h('5  计时方法与指标计算')").replace("h('4  主存地址槽与核到槽的映射')","h2('1.3  主存槽布局与执行条件')"))
p('boundary 与 load 固定步长131200 B和 identity；mapping 改变步长与排列。源和目标主存数组一次分配，整个作业内基地址固定；每轮始终复用同一主存槽和 LDM 缓冲。一次作业内按 plan.csv 固定顺序执行三个阶段，shuffle 并未打乱运行顺序。')
p('每核 LDM 数据缓冲为128 KiB、128 B对齐。手册描述 LDM 总容量256 KiB，可划分 Cache、私有和连续共享 LDM；本次 Cache 请求为0，实际共享分配量未知。链接报告静态 LDM 132840 B，未用 -b 搬移栈；本次运行完成不能保证其他内存配置也能容纳。')

page();h('2  DMA 带宽曲线')
p('默认布局下，单核吞吐随消息增大上升，64核大消息吞吐接近平台区。对齐读写表现不同：读取约20.85至20.98 B/cycle，写入约15.38至15.60 B/cycle。以下曲线同时显示1核与64核、主存偏移0 B与4 B，所有条件均来自 load 阶段。')
figure('图1_DMA带宽曲线','图 1  四种 DMA 模式在两档核数与两种主存偏移下的聚合带宽')
p('put/iput 的两个尖峰位于128 B和256 B，已用箭头标明，均为64核、偏移0 B的对齐写入。它们不是128 KiB附近的大消息峰值。横轴为以2为底的对数刻度，等距表示相同倍数，而非相同字节增量。尖峰来自完成耗时的局部低谷，具体硬件原因仍需区分。')
h2('128 KiB 对齐传输的代表结果')
table(['模式','单核 B/cycle','64核 B/cycle','64与1核带宽比','64核条件换算 GB/s'],[
 [m,f'{bw("load",m,1,131072):.3f}',f'{bw("load",m,64,131072):.3f}',f'{bw("load",m,64,131072)/bw("load",m,1,131072):.3f}',f'{bw("load",m,64,131072)*2.25:.2f}'] for m in MODES
],[1.8,3.5,3.5,4.0,4.6])
p(f'64至128 KiB的单核 get 带宽从 {bw("load","get",1,65536):.3f} 增至 {bw("load","get",1,131072):.3f} B/cycle，增幅7.0%；put 增幅3.5%。扩大消息主要摊薄固定开销，未使大消息平台吞吐成倍增长。条件换算不替代频率标定；本结果适用于单核组、W=1、固定槽预热后访问，不代表全芯片峰值。')

page();h('3  并发扩展与共享吞吐')
h2('3.1  消息大小决定并发收益')
p('64核相对单核的带宽比在小消息下较高，随消息增大明显下降。理想线性扩展比为64，图中所有值都低于这一基准。写入还在128 B对齐处出现特殊高点，需要结合第4章的块边界分析。')
figure('图2_并发扩展比','图 2  64核相对单核的聚合带宽比  虚线接口为 iget 与 iput')
table(['消息大小','get 对齐扩展比','put 对齐扩展比'],[
 [f'{s} B' if s<1024 else f'{s//1024} KiB',f'{bw("load","get",64,s)/bw("load","get",1,s):.2f}',f'{bw("load","put",64,s)/bw("load","put",1,s):.2f}'] for s in [8,64,128,1024,4096,16384,32768,65536,131072]
],[4.2,6.6,6.6])
p(f'8 B对齐 get 扩展为 {bw("load","get",64,8)/bw("load","get",1,8):.2f} 倍，128 KiB仅 {bw("load","get",64,131072)/bw("load","get",1,131072):.2f} 倍。128 KiB put 扩展比为 {bw("load","put",64,131072)/bw("load","put",1,131072):.3f}，64核聚合吞吐反而低于单核。效率为扩展比除以64，反映吞吐未随核数线性增长，不是应用计算效率。')

emit(take("page();h('10  中间核数揭示写入的吞吐下降')","page();h('11  槽步长和核到地址排列影响吞吐')").replace("h('10  中间核数揭示写入的吞吐下降')","h2('3.2  七档核数定位饱和与下降区间')").replace('图4_核数与聚合带宽','图3_活跃核数与共享吞吐').replace('图 4  ','图 3  '))

emit(take("page();h('7  写入的大小与偏移边界')","page();h('9  扩展到 128 KiB 的带宽曲线')").replace("h('7  写入的大小与偏移边界')","h('4  主存对齐与 128 B 写入边界')\nh2('4.1  九种尺寸与四种偏移的边界细扫')\np('主存端偏移均满足4 B接口约束，但改变相对于128 B边界的位置；LDM端始终128 B对齐。64核写入在128 B与256 B对齐处出现耗时低谷，相邻部分块尺寸明显较慢。')").replace("h('8  偏移代价随负载放大')","h2('4.2  偏移惩罚随并发放大')").replace('图1_写入边界细扫','图4_写入边界细扫').replace('图2_偏移代价随核数变化','图5_偏移代价与负载').replace('图 1  ','图 4  ').replace('图 2  ','图 5  '))

page();h('5  操作完成耗时与非阻塞接口')
h2('5.1  完成耗时曲线与匹配接口比较')
p('get 的单核小消息完成耗时较平稳；大消息下64核逐次完成耗时受共享吞吐约束。put 在64核、128 B对齐处明显下降，不能对全尺寸使用同一条线性延迟曲线。图中耗时取最慢核平均值，纵轴为对数刻度。')
figure('图6_操作完成耗时','图 6  get 与 put 的完成耗时  对齐与偏移4 B的对照')
table(['核数','带宽比','60组配置的范围','中位数'],[
 [n,f'{a}/{b}',f'{min(bw("load",a,n,s,o)/bw("load",b,n,s,o) for s in sorted({k[3] for k in D if k[0]=="load"}) for o in [0,4]):.4f} 至 {max(bw("load",a,n,s,o)/bw("load",b,n,s,o) for s in sorted({k[3] for k in D if k[0]=="load"}) for o in [0,4]):.4f}',f'{np.median([bw("load",a,n,s,o)/bw("load",b,n,s,o) for s in sorted({k[3] for k in D if k[0]=="load"}) for o in [0,4]]):.4f}']
 for n in [1,64] for a,b in [('iget','get'),('iput','put')]
],[2.0,3.5,7.5,4.4])
p('每核比较包含30种大小×两种偏移。四种模式均逐次等待完成，因此 iget/iput 没有被用作流水线；比值接近1主要说明当前调用方式下差异较小。读写完成边界不同，不能直接把小消息基线差解释为 DRAM 读写物理延迟差。')
h2('测量边界')
p('每配置只有一个独立计时区间，R次循环提高均值稳定性，不是R次独立实验；没有独立重复的置信区间。大消息平台、全尺寸的接口对照和单核小消息固定耗时应分别理解，不能互相替代。')

emit(take("page();h('14  跨阶段复测和接口对照')","page();h('15  结论 实验限制与复现入口')").replace("h('14  跨阶段复测和接口对照')","h2('5.2  同作业跨阶段复测的稳定程度')").replace('图8_阶段一致性与接口对照','图7_阶段复测与接口对照').replace('图 8 ','图 7 '))

emit(take("page();h('12  小消息读取的耗时模式跟随地址槽')","page();h('14  跨阶段复测和接口对照')").replace("h('12  小消息读取的耗时模式跟随地址槽')","h('6  逐核耗时与空间差异')\nh2('6.1  小消息读取的模式跟随地址槽')").replace("h('13  大消息写入保留核位置相关模式')","h2('6.2  大消息写入保留核 ID 相关模式')").replace('图6_读取耗时随地址槽移动','图8_读取空间差异').replace('图7_大消息写入的逐核模式','图9_写入空间差异').replace('图 6  ','图 8  ').replace('图 7  ','图 9  ').replace('第 12 节','第 6.1 节'))
emit(take("page();h('11  槽步长和核到地址排列影响吞吐')","page();h('12  小消息读取的耗时模式跟随地址槽')").replace("h('11  槽步长和核到地址排列影响吞吐')","h2('6.3  槽布局同时改变聚合吞吐')\np('逐核模式相似并不意味着聚合吞吐不变。下面固定64核与128 KiB消息，比较四种步长和四种排列，量化地址配对对整体完成速度的影响。')").replace('图5_槽步长与映射对照','图10_槽布局与聚合吞吐').replace('图 5  ','图 10  '))

page();h('7  初步建模参数与后续实验')
h2('7.1  对齐大消息的分段线性模型')
p('默认步长131200 B、identity、偏移0 B下，拟合 T(S)=α+βS。T为汇总 cycles/op，S为字节数。单核取1至128 KiB的8个倍增点，64核取4至128 KiB的6个倍增点；分别拟合四种模式。表中的斜率吞吐为 N/β，α为区间外推截距，均不是直接测得的硬件常数。')
fits=[]
for m in MODES:
 for n in [1,64]:
    sizes=[2**i for i in range(10 if n==1 else 12,18)]
    x=np.array(sizes,dtype=float); y=np.array([cy('load',m,n,s) for s in sizes])
    beta,alpha=np.polyfit(x,y,1); pred=alpha+beta*x
    r2=1-float(np.sum((y-pred)**2)/np.sum((y-y.mean())**2))
    fits.append(dict(mode=m,active_pes=n,min_bytes=sizes[0],max_bytes=sizes[-1],points=len(sizes),alpha=float(alpha),beta=float(beta),slope_bandwidth=n/float(beta),r_squared=r2,max_relative_fit_error=float(np.max(np.abs(pred/y-1)))))
table(['模式','核数','α cycles','β cycles/B','斜率吞吐 B/cycle','R²'],[
 [r['mode'],r['active_pes'],f'{r["alpha"]:.2f}',f'{r["beta"]:.6f}',f'{r["slope_bandwidth"]:.2f}',f'{r["r_squared"]:.6f}'] for r in fits
],[1.6,1.2,3.2,3.6,4.7,3.1])
p('高 R² 表明所选大消息区间总体接近线性，不说明小消息或其他布局也适用。64核 put/iput 的负截距是区间外推结果，不代表负延迟；α也不应替代读取约441 cycles的小消息平台。β反映当前负载、布局与串行等待下的有效传输斜率，不是单链路理论带宽。模型不能跨过128 B部分块边界直接预测写入。')
table(['核数','get 最大相对拟合误差','put 最大相对拟合误差'],[
 [n]+[f'{100*next(r["max_relative_fit_error"] for r in fits if r["mode"]==m and r["active_pes"]==n):.2f}%' for m in ['get','put']] for n in [1,64]
],[3.0,7.2,7.2])
p('相对误差按 |预测/实测−1| 在拟合点上取最大值，是样本内误差，不是独立验证误差。大消息点主导R²，区间低端仍可能有偏差。模型建议分别保存小消息固定开销、按大小与偏移划分的写入表，以及按核数和槽布局条件化的大消息斜率。')
p('本次关键经验值为：128 B、64核 put 偏移4 B耗时约增至11.79倍；128 KiB对齐 put 的4核观测峰值21.326 B/cycle、64核15.381；同尺寸 get 在8核已接近平台区。逐核相关性支持分开考虑地址槽与核因素，但没有确定具体路由或bank机制。')

cont('7.2  后续实验与数据依据')
h2('已经完成与仍需补充的测量')
table(['实验项目','本次状态','下一步'],[
 ['边界与偏移','9种大小×4种偏移','独立重复关键边界及片段对照'],
 ['中间负载','七档核数','固定可比地址集合轮换活跃核'],
 ['地址布局','4步长×4排列','结合物理地址或硬件事件定位机制'],
 ['独立重复与顺序','单作业固定顺序','多次独立作业并随机化顺序'],
 ['资源与内存配置','Cache请求0  共享程度未知','记录分配、同节点作业与实际LDM划分'],
 ['请求窗口与工作集','W=1  固定地址复用','独立缓冲扫W并轮转主存工作集'],
 ['计数器频率','尚未独立标定','与可信时间基准交叉标定'],
],[4.0,5.8,7.6])
p('先复测写入边界、4核与64核的大消息差异及两类逐核模式，再测请求窗口和轮转工作集。改变槽间距不是工作集轮转，固定种子的shuffle也不是执行顺序随机化。DMA没有发起CPE间RMA，本结果不能生成2×2小簇router参数；后者需要独立RMA拓扑实验。')
h2('数据与手册依据')
p('数据集为 dma_results_20261005_203552_32484：plan.csv和slot_maps.csv定义条件与排列；raw及smoke保留原始记录；study_summary.csv与study_scaling.csv保留汇总和扩展；source为运行版本，build_info.txt、build.log、cpuinfo.txt和job.log为配置依据。所有图表和模型均使用本次数据。')
p('手册依据：《SACA编程指南》v0.62，PDF第59页说明128 B主存请求拆分，第60页定义完成条件，第88页定义从核计数器；《神威众核编程指南》2.4.2、3.4、4.1、4.3节说明内存与接口。分段描述与观测一致，但额外分段不足以单独解释11.79倍惩罚。')
h2('复核与生成入口')
p('远端运行入口为 DMA_MAX_BYTES=131072 bash run_dma_boundary.sh q_share。对已有结果做分析无需提交新作业；在项目根目录执行：')
p('python bench/analyze_dma_study.py dma_results_20261005_203552_32484 --out outputs/dma_study_analysis_20261005_203552_32484')
p('分析目录保存完整性、边界、负载、布局、阶段差异和相关性衍生表。结构对齐版的模型参数另存同目录 model_fits_128k.csv；本报告目录的 _build/draw_aligned_charts.py 和 build_aligned_report.py 生成编号图表与正文。')
p('适用范围为本次SW39000环境、单CG、W=1、固定槽预热后访问。其他Cache/LDM配置、活跃位置、轮转工作集、型号或共享状态下，应复测后再迁移。')

target=OUT/'SW39000_DMA扩展实验分析报告_结构对齐版.docx'
doc.save(target)
(OUT/'DMA扩展实验分析报告_结构对齐版.md').write_text('\n'.join(md).replace('](图表/','](结构对齐图表/'),encoding='utf-8')
with (ANA/'model_fits_128k.csv').open('w',newline='',encoding='utf-8-sig') as f:
 w=csv.DictWriter(f,fieldnames=list(fits[0]));w.writeheader();w.writerows(fits)
with zipfile.ZipFile(OUT/'DMA扩展实验图表_结构对齐版.zip','w',zipfile.ZIP_DEFLATED) as z:
 for path in sorted(FIG.iterdir()):z.write(path,'图表/'+path.name)
print('Saved',target)
