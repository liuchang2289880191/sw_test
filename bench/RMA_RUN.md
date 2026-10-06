# RMA 一键测试

## 1. 在服务器上启动

将更新后的 `bench` 目录同步到服务器，在登录节点执行：

```bash
cd ~/liuchang/sw_test/bench
module load swgcc/1473
bash run_rma.sh q_share
```

脚本会重新编译，直接向队列提交 `rma_cluster_bench --suite`，在同一 MPE 进程中依次完成各项测试。计算节点不需要 Bash，也不需要启动子程序。默认顺序提交 **3 个独立作业**；每个作业先做 18 项正确性检查，通过后做 548 项正式配置。正式配置的运行顺序按不同种子打乱，检查失败立即停止，并取消后续提交。

在登录节点保留终端，等待交互作业结束。结果目录默认创建在 `bench/rma_results_日期_时间_PID/`，不会覆盖已有目录。

第一次想先检查环境，可以执行：

```bash
RMA_DIAG_ONLY=1 bash run_rma.sh q_share
```

这会提交 **1 个作业，仅运行 18 项检查**，不进入正式扫描。检查覆盖 9 个代表核对、8 种争用配置，以及 8 B 的完整 ping-pong 矩阵；每项重复 10 次。

需要较短的正式测试：

```bash
RMA_PROFILE=quick RMA_REPEATS=1 bash run_rma.sh q_share
```

quick 模式仍包含延迟矩阵、9 对核的带宽曲线及全部争用类型，但减少消息大小、窗口和小簇位置。

## 2. 默认正式测试内容

### 2.1 Ping-pong 延迟矩阵

- 消息大小：**8、16、32、64、128、256 B**。
- 每种大小扫描 **64×63=4032 个有向核对**，跳过自身通信。
- 每对先预热 4 次，再计时 2000 次往返；输出 `latency_cycles=总往返周期/(2×reps)`。
- 计时区不包含阵列 barrier；计时只用发起核的本地计数器。

`RTT/2` 是两方向与收发握手共同决定的半往返耗时，不等同于测得了某一方向的纯链路延迟。两个发起方向的行均保留，不能将它们当作独立的单向物理延迟。

### 2.2 代表核对的带宽与窗口

坐标约定为 `id=8×row+col`；几何小簇为对齐的 2×2 块。

| 核对 | 坐标 | 对照用途 |
|---|---|---|
| 0→1 | (0,0)→(0,1) | 同块横向 |
| 0→8 | (0,0)→(1,0) | 同块纵向 |
| 0→9 | (0,0)→(1,1) | 同块对角 |
| 1→2 | (0,1)→(0,2) | 跨块横向一步 |
| 8→16 | (1,0)→(2,0) | 跨块纵向一步 |
| 9→18 | (1,1)→(2,2) | 两维跨块 |
| 0→7 | (0,0)→(0,7) | 远距离同行 |
| 0→56 | (0,0)→(7,0) | 远距离同列 |
| 0→63 | (0,0)→(7,7) | 远距离对角 |

- 大小：**8、16、32、64、128、256、1024、4096、16384、32768、65536 B**。
- 每条流窗口 `W=1、2、4、8、16`，每项 2000 次传输。
- 每个窗口槽使用独立的源和目标 LDM 地址；下一批复用这些地址。窗口按批次发起并等待，不是滑动窗口。
- 只生成 `bytes×W≤BENCH_MAX_BYTES` 的配置，共 **414 项**。64 KiB 只测 W=1；32 KiB 最多 W=2。
- 带宽是 RMA put payload 吞吐；默认入口的带宽扫描没有 RMA get。

### 2.3 小簇争用对照

每块四核按以下几何位置命名：

```text
A B
C D
```

| 配置名 | 通信模式 | 流数 |
|---|---|---:|
| single | A→B | 1 |
| intra2 | A→B，C→D | 2 |
| split_near2 | 当前块 A→B；相邻纵向块内部 A→B | 2 |
| split_side2 | 当前块 A→B；相邻横向块内部 A→B | 2 |
| split_far2 | 当前块 A→B；相隔两块行的块内部 A→B | 2 |
| incast3 | B、C、D→A | 3 |
| ring4 | A→B→D→C→A | 4 |
| alltoall4 | 四核之间所有非自身有向流 | 12 |

小簇编号为 `4×floor(row/2)+floor(col/2)`。默认测试块 **0、5、10、15**；每种模式测 **64 B、1024 B** 和 **W=1、4**，共 **128 项**。边缘块的相邻块选向阵列内部的一侧。

`split_*2` 中两条流都在各自块内部，考察共享资源的空间分布；跨块单流通信由 2.2 中的核对覆盖。没有预设 2×2 块就是本机实际 router 边界。

W 是**每条流的窗口**。alltoall4 中每核有 3 条出流，最多同时发起 3W 个请求；每核收到 3 条入流，目标缓冲需要 `3×bytes×W`。脚本自动跳过超过容量的配置。

## 3. 容量与运行参数

默认编译：主核 `-mhost -O2 -g`，从核 `-mslave -msimd -O2 -g`，链接 `-mhybrid -g`；提交请求为 `-n 1 -cgsp 64 -mpecg 1 -cache_size 0`。

两个 RMA 缓冲各为 64 KiB，再加控制变量，链接器仍可能提示静态 LDM 超过 128 KiB。该告警不能单独证明运行失败，也不能证明空间足够；默认请求 cache=0。若需要减少静态占用：

```bash
BENCH_MAX_BYTES=32768 bash run_rma.sh q_share
```

这会重新编译为两个 32 KiB 缓冲，并自动缩小扫描范围。**DMA 的 128 KiB 消息设置不能用于此 RMA 内核**，`DMA_MAX_BYTES` 不控制本脚本。

| 环境变量 | 默认值 | 含义 |
|---|---|---|
| RMA_PROFILE | full | full 或 quick |
| RMA_REPEATS | 3 | 独立提交次数，1～20 |
| RMA_DIAG_ONLY | 0 | 1 表示仅检查，固定一次提交 |
| RMA_LATENCY_REPS | 2000 | 每对的计时往返次数，1～100000 |
| RMA_BW_REPS | 2000 | 每条流的计时传输次数，1～1000000 |
| RMA_ORDER_SEED | 20261006 | 可复现的顺序种子，每次重复加上重复编号 |
| BENCH_MAX_BYTES | 65536 | 单个 RMA 缓冲容量，256～65536，128 的倍数 |
| RMA_CACHE_SIZE | 0 | 请求的 cache KiB，支持 0、32 |
| RMA_RESOURCE_NOTE | not_provided | 从管理员或分配记录获知的共享/独占信息 |
| SWCC / SW_MODULE | swgcc / swgcc/1473 | 编译器及缺失时加载的 module |

例如：

```bash
RMA_RESOURCE_NOTE='管理员确认的分配情况：在此填写' \
RMA_REPEATS=3 bash run_rma.sh q_share
```

队列名 `q_share` 不证明资源独占程度。脚本记录资源请求、用户补充说明、计算节点 hostname、可读取的 `/proc/cpuinfo` 和完整调度日志；无法读取的实际 cache/LDM 配置、资源共享和计数器频率明确记为未知。不同提交可能落在同一节点，不能视为保证换机器。

## 4. 结果文件

```text
rma_results_.../
  build_info.txt           编译器、参数、module 和资源说明
  build.log                编译和链接日志
  source/                  此次测试的源码与脚本快照
  rma_cluster_bench         此次编译的可执行文件
  summary.csv              带宽/争用汇总，保留 repeat 和 phase
  latency.csv              合并的延迟矩阵，保留 repeat 和 phase
  COMPLETE                 所有重复通过采集校验后才生成
  repeat_01/               repeat_02、repeat_03 同结构
    plan.txt / plan.csv    实际运行顺序与完整核对、窗口、消息配置
    job.log                调度消息、进度、错误；不混入数据 CSV
    run_info.txt           重复编号与顺序种子
    resource_runtime.txt   计算节点资源记录
    smoke/                 正确性检查原始 CSV
    raw/                   正式测试原始 CSV
    RUN_COMPLETE           原生程序完成标记
    COMPLETE               登录节点逐文件校验通过标记
    summary.csv / latency.csv
```

正式结果筛选 **`phase=raw`**。smoke 的 10 次检查不应混入性能统计。`case_id` 用于跨重复匹配同一配置；同一重复的 `order` 在 plan.csv 中查询。

带宽：`aggregate_bytes_per_cycle=bytes×reps×flows/max_active_PE_cycles`，包含发起循环及本地/远端完成等待。逐核耗时使用本核计数器差；聚合量以活跃核中最大耗时计算，不使用跨核绝对时间。若有校准的 CPE GHz，`GB/s=B/cycle×GHz`，脚本不猜频率。

正确性包含 reply 等待和最终目标数据检查；不是逐次 payload 校验。采集器要求每个矩阵有 4032 行、每条活跃核记录及聚合记录齐全、周期数为正、所有 errors=0，并核对派生指标。缺少 COMPLETE 的目录属于未完成结果，应先检查对应 job.log。

## 5. 其它已有 RMA 程序

本入口聚焦小簇研究的三组测试。既有 `rma_bench` 的单向 put/get 矩阵和 `rma_bcast_bench` 的 row/col/array 广播仍可按 README 单独提交；它们未加入本轮自动扫描。

旧的 `run_cluster_sweep.sh` 会在计算节点启动 Bash 和多个子程序，不适用于当前环境。使用本文件的 `run_rma.sh` 入口。

新增启动方式仅做本地模拟和静态检查；本仓库尚无真实 RMA 运行结果。
