# 2×2 小簇 RMA benchmark：实验设计与运行

## 研究问题

目标是检验 **2×2 小簇边界是否在 RMA 性能中可测**，并比较它与消息大小、水平/垂直距离及同时运行的 flow 数量的关系。公开的 [SWSPH 论文](https://www.researchgate.net/publication/373350951_SWSPH_A_Massively_Parallel_SPH_Implementation_for_Hundred-Billion-Particle_Simulation_on_New_Sunway_Supercomputer)描述了 SW26010Pro 的 8×8 从核阵列及每四个相邻从核共享含 router 的局部管理部件；[软件学报论文](https://jos.org.cn/html/2024/6/7098.htm)描述了核组内 LDM/SPM 之间的 RMA。它们支持实验动机，但**没有规定用户态 RMA 请求的逐跳路径**。本测试只能推断性能结构，不能直接证明物理布线或路由算法。

本目录中的《SACA编程指南-v0.62.pdf》说明 `athread_rma_iput()`、本地/远端回答字、`athread_rma_wait_value()`、`athread_stime_cycle()` 和 `athread_ssync_array()` 的用法（PDF 73–75、48、88–89 页）。手册声明其处理器参数以 SW39000 为背景；在 SW26010Pro 上构建时，应以该机器安装的 `slave.h`/运行库为最终 API 准据。

几何编号采用 `id=8*row+col`，`row,col∈[0,7]`。2×2 小簇编号为 `cluster=(row/2)*4+col/2`，其中除法为整除。cluster 0 的四核是 `{0,1,8,9}`。完整阵列共有 16 个几何小簇。

## 一、ping-pong latency matrix

```sh
make -C bench
bsub -I -q QUEUE -n 1 -cgsp 64 -mpecg 1 \
  ./bench/rma_cluster_bench latency 8 2000 > pingpong_8B.csv
python3 bench/analyze_cluster.py pingpong_8B.csv --origin 0 --svg-prefix heatmap_origin0
```

对 64×63 个非自身有向 `(initiator,peer)`，仅两核通信。A 对 B `iput` 并等待本地 reply；B 等待远端 reply 后对 A `iput`；A 等待回信。每对先做 4 次预热，再连续计时 `reps` 次往返。**循环中没有阵列 barrier**；阵列同步仅在应答字清零之后、计时前和每对结束后。输出 `latency_cycles = RTT_cycles/(2*reps)`。需要比较完整小消息区间时单独运行 8、16、32、64、128、256 B。

RTT/2 不依赖两个从核的周期计数器同步，但它混合了正反两个方向的传输与 B 的响应开销。因此 64×64 表里的 `(A,B)` 是“由 A 发起的往返估计”，不是纯 `A→B` 单程延迟；正反方向可能接近重复。原有 `rma_bench put|get` 保留单向完成周期矩阵，可作为方向性补充，但其值也包含发起端 API/reply 等待开销。

先比较相邻的一步：

| 对照 | 簇内 | 跨簇 | 控制变量 |
|---|---|---|---|
| 横向 | 0↔1 | 1↔2 | 坐标距离均为 1 |
| 纵向 | 0↔8 | 8↔16 | 坐标距离均为 1 |
| 对角 | 0↔9 | 9↔18 | 坐标距离均为 (1,1) |

再看远端同行 `0↔7`、同列 `0↔56`、远对角 `0↔63`。`--svg-prefix` 会写出可直接插入论文草稿的 8×8 SVG；建议重点画源核 0、9、18、27、36，并对整个矩阵按坐标距离配对。颜色只在当前图内按最小/最大值缩放，跨图比较请看数字；只凭一组 pair 不能确认小簇效应。

## 二、pair bandwidth 与 outstanding window

```sh
bsub -I -q QUEUE -n 1 -cgsp 64 -mpecg 1 \
  ./bench/rma_cluster_bench bandwidth 0 1 1024 1000 1 > bw_0_1_1024_w1.csv
bsub -I -q QUEUE -n 1 -cgsp 64 -mpecg 1 \
  ./bench/rma_cluster_bench bandwidth 0 1 1024 1000 8 > bw_0_1_1024_w8.csv
```

每次使用 `athread_rma_iput`。`window=1` 是发一条、等本地完成一条的串行传输；`window=W` 时连续发最多 W 条，再等累计本地 reply。远端等待累计远端 reply。不同 outstanding 请求写入 **不同 LDM slot**，避免同址覆盖影响结论；重复批次复用 slot。测量区外有 1 批预热，计时区内没有 barrier。输出 `aggregate_bytes_per_cycle = bytes*reps/max(active_PE_cycles)`，单 flow 即该 pair 的有效 payload 带宽。`reps` 是每条 flow 的传输次数。

推荐消息大小 `8,16,32,64,128,256,1024,4096,16384,65536 B`，window `1,2,4,8,16`。容量条件为 `bytes*window*目标核入流数 <= 65536`；大消息不一定能测大 window。缓冲各 64 KiB，不能在 LDM 剩余空间不足时盲目增大到 128 KiB。

关键 pair：`0→1` 簇内横向、`0→8` 簇内纵向、`0→9` 簇内对角、`1→2` 跨簇横向、`8→16` 跨簇纵向、`9→18` 跨簇对角、`0→7` 远同行、`0→56` 远同列、`0→63` 远对角。

## 三、contention：共享小簇与分散小簇

```sh
bsub -I -q QUEUE -n 1 -cgsp 64 -mpecg 1 \
  ./bench/rma_cluster_bench contention intra2 1024 2000 4 0 > intra2.csv
bsub -I -q QUEUE -n 1 -cgsp 64 -mpecg 1 \
  ./bench/rma_cluster_bench contention split_near2 1024 2000 4 0 > split_near2.csv
bsub -I -q QUEUE -n 1 -cgsp 64 -mpecg 1 \
  ./bench/rma_cluster_bench contention split_far2 1024 2000 4 0 > split_far2.csv
python3 bench/analyze_contention.py intra2.csv split_near2.csv split_far2.csv
```

命令末尾的 `cluster_index` 可选，取 0–15，默认 0。下面以 cluster 0 为例。所有 case 先预热，阵列 barrier 后同时开始；每个活跃核记录自身历时，aggregate 用最大历时。**计时区没有 barrier**。

| case | 同时运行的 flow | 目的 |
|---|---|---|
| `single` | `0→1` | 单流基准 |
| `intra2` | `0→1`, `8→9` | 两个独立 flow 同处一个 2×2 |
| `split_near2` | `0→1`, `16→17` | 两个相同局部几何 flow 位于纵向相邻小簇 |
| `split_side2` | `0→1`, `2→3` | 两个 flow 位于横向相邻小簇 |
| `split_far2` | `0→1`, `32→33` | 两个 flow 位于远离的小簇 |
| `incast3` | `1→0`, `8→0`, `9→0` | 同簇三源入一个目的核 |
| `ring4` | `0→1→9→8→0` | 四条同时工作的环形 flow |
| `alltoall4` | 四核互发，共 12 条 flow | 簇内高争用 |

三个 `split` case 的第二簇会随 `cluster_index` 平移，局部源/目的位置保持一致。每个目的核的不同入流写不同 lane，且每个 outstanding 请求有独立 slot。`incast3` 与 `alltoall4` 因入流数为 3，容量上限更严格：`3*bytes*window <= 65536`。

比较 **同样两条 flow** 的 `intra2`、`split_near2`、`split_side2`、`split_far2` 聚合 B/cycle；再比较它们与 `single` 的扩展比。若 `intra2` 在多个位置、消息大小和独立作业中稳定更慢，小簇共享资源是合理的解释。也要检查远近分散小簇的差别；若相邻分散的小簇仍慢而远端分散小簇快，可能是相邻区域共享路径，而不只是 2×2 内部资源。`incast3` 主要探测目标端口/LDM 写入争用，不能与独立目的核的两个 flow 直接归因比较。

## 四、由结果推断片上通信结构

```sh
python3 bench/analyze_cluster.py pingpong_8B.csv pingpong_16B.csv pingpong_64B.csv --origin 9
python3 bench/analyze_contention.py cluster_results/cont_*.csv
```

`analyze_cluster.py` 给出相邻一步的 **同簇 vs 跨簇** 中位数、源核 8×8 heatmap，并拟合四个描述性线性模型：`size`、`size+cluster`、`size+row/col distance`、`size+cluster+distance`。它报告 R² 与 BIC；BIC 较低只表示该数据下的拟合与复杂度折中，不是路由机制的证明。带宽与争用的模式作为独立证据。可出现的解释包括：

1. 跨簇一步有稳定延迟台阶，且 `intra2` 聚合带宽低于各 `split` 对照：支持显式小簇层次。
2. 延迟主要随坐标距离平滑增长，跨簇指标帮助很小：距离/mesh 模型更合适。
3. 行列差异显著，甚至大于 2×2 边界：需要把 row/column fabric 单独建模。
4. 空闲延迟差异很小，但同簇并发流量显著降速：小簇主要表现为共享吞吐资源。

实际路由路径、router 数量、队列深度不能只靠这些宏观周期值唯一反演。若有可用的硬件事件计数器或管理员提供的网络拓扑/调度说明，可与这些结果交叉验证；本 benchmark 本身不声称能读取 router 内部状态。

## 五、批量运行与记录

```sh
bsub -I -q QUEUE -n 1 -cgsp 64 -mpecg 1 bash bench/run_cluster_sweep.sh cluster_results
```

脚本生成 8 B ping-pong 矩阵、代表性 pair 的 bandwidth-window 曲线，以及 0/5/10/15 号小簇上的争用对照。机器时间有限时，先执行：8 B 矩阵；`0→1` 与 `1→2` 的 `8 B–64 KiB, W=1`；`single/intra2/split_near2/split_side2/split_far2` 的 `1024 B, W=4`，再平移到至少两个其他小簇。

每项至少在相同配置下重复 3 次并保存原始 CSV。记录 CPU 型号、核组号、从核频率、编译器/运行库版本、D-cache/LDM 配置、作业队列与是否独占、`bytes/reps/window/cluster_index`。有 `errors>0`、编译接口不匹配或资源配置不满足 64 从核的结果应先修复，不能用于结构推断。本工程未在 SW 平台编译或运行。
