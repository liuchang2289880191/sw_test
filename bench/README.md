# 神威 DMA / RMA benchmark（含 SW26010Pro 2×2 小簇实验）

本工程依据目录中的《SACA编程指南-v0.62.pdf》编写 Athread 接口代码，使用 **单个 8×8 从核阵列（64 个从核）**。该手册以 SW39000 为背景；新增的 2×2 小簇实验以 SW26010Pro 为研究目标。提供源代码、构建命令、测量定义和结果分析脚本；本文档未包含实测数字。目标机器的运行库/编译器版本若与手册不同，应先核对 `slave.h` 中的接口声明。

针对 SW26010Pro **2×2 小簇边界**的 ping-pong、流水化带宽和争用对照，见 [RMA_CLUSTER.md](RMA_CLUSTER.md)。该部分以实测判断小簇是否进入性能模型；不会预设簇内通信必然更快。

## 1. 手册依据与测试边界

| 内容 | 手册位置（PDF 页） | 本工程中的使用 |
|---|---:|---|
| 8×8 从核编号，`_PEN`/`_ROW`/`_COL` | SACA 21、48 | `tid = row*8 + col`，64×64 有向矩阵 |
| LDM 256 KB、默认从核 D-cache 32 KB；一致性注意事项 | SACA 13–15 | 源/目的缓冲均置于 LDM；DMA 主存缓冲 128 B 对齐 |
| `swgcc -mhost/-mslave/-mhybrid` | SACA 16–17 | `Makefile` 分别编译、混合链接 |
| DMA get/put、非阻塞应答及 4 B 对齐 | SACA 57–61 | 四种 DMA 模式、每次操作完成后计时 |
| RMA get/put、远端应答及 4 B 对齐 | SACA 72–75 | 单对单完整有向拓扑矩阵 |
| RMA 行/列/全阵列集合广播 | SACA 76–81 | 三种广播域的并发测试 |
| 从核周期计数器 | SACA 88–89 | `athread_stime_cycle()` |
| 作业提交 `-n/-cgsp/-mpecg` | 《作业与资源管理用户手册》11–12 | 单主核、单核组、64 从核 |

这里的 **RMA 拓扑** 指单核组内部通信关系。RMA API 的 `r_tid` 限于同一核组，跨核组或跨节点拓扑不在此测试范围内。行/列关系按 `tid/8` 和 `tid%8` 计算；如果平台报告的实际编号映射不同，应以 `_ROW/_COL` 校对后修改分析代码。手册的 RMA 行/列广播示例有明显复制文字问题，本工程使用接口原型和 `root` 参数说明实现。

## 2. 文件

| 文件 | 用途 |
|---|---|
| `dma_host.c`, `dma_slave.c` | DMA get、put、iget、iput；1 或 64 从核 |
| `rma_host.c`, `rma_slave.c` | RMA put/get 的 64×64 有向矩阵；跳过自通信 |
| `bcast_host.c`, `bcast_slave.c` | RMA 行、列、全阵列集合广播 |
| `analyze_topology.py` | 分类统计、曼哈顿距离统计、8×8 目的核图 |
| `run_sweep.sh` | 批量生成 CSV 文件 |
| `rma_cluster_host.c`, `rma_cluster_slave.c` | 小簇 ping-pong 矩阵、pair 带宽、并发 flow |
| `RMA_CLUSTER.md`, `run_cluster_sweep.sh` | 小簇实验设计和批量脚本 |
| `analyze_cluster.py`, `analyze_contention.py` | 边界/距离模型和争用对照 |

## 3. 在神威平台上构建

从项目根目录执行：

```sh
swgcc -v
make -C bench
```

得到 `bench/dma_bench`、`bench/rma_bench`、`bench/rma_bcast_bench`、`bench/rma_cluster_bench`。`Makefile` 使用手册所示的 `-mhost`、`-mslave` 和 `-mhybrid`。如果站点将编译器安装为其他名字，可用 `make -C bench SWCC=/path/to/swgcc`。本地目录没有神威工具链，本工程未在该平台编译或执行；第一轮使用时应先根据实际编译报错核对本机头文件/库版本。

## 4. 单项运行

将 `QUEUE` 替换为站点的真实队列名。下面用交互作业，一次只占用一个主核和一个完整核组：

```sh
bsub -I -q QUEUE -n 1 -cgsp 64 -mpecg 1 ./bench/dma_bench get 1024 1000 1 0 > dma_get_1pe_1024B.csv
bsub -I -q QUEUE -n 1 -cgsp 64 -mpecg 1 ./bench/dma_bench put 65536 200 64 0 > dma_put_64pe_65536B.csv
bsub -I -q QUEUE -n 1 -cgsp 64 -mpecg 1 ./bench/rma_bench put 64 100 > rma_put_64B.csv
bsub -I -q QUEUE -n 1 -cgsp 64 -mpecg 1 ./bench/rma_bcast_bench row 1024 200 0 > rma_bcast_row_1024B.csv
```

作业管理系统可能把提交信息写进标准输出。若 CSV 首行不是 `benchmark,...`，删掉前面的调度器行再分析，或按站点习惯使用 `bsub -o` 输出到文件。可先直接运行最小规模的四个命令检查编译和正确性：

```sh
bsub -I -q QUEUE -n 1 -cgsp 64 -mpecg 1 ./bench/dma_bench get 4 10 1 0
bsub -I -q QUEUE -n 1 -cgsp 64 -mpecg 1 ./bench/dma_bench put 4 10 64 0
bsub -I -q QUEUE -n 1 -cgsp 64 -mpecg 1 ./bench/rma_bench put 4 1
bsub -I -q QUEUE -n 1 -cgsp 64 -mpecg 1 ./bench/rma_bcast_bench array 4 10 0
```

`bytes` 必须是 4 B 的整数倍，范围 4–65536 B。`dma_bench` 的 `active_pes` 为 1 或 64；`offset` 为 0（128 B 对齐）或 4（仅 4 B 对齐），用于比较未按 128 B 对齐的 DMA 影响。RMA `put|get` 的 `initiator` 表示发起核，`peer` 表示远端核。广播的 `root` 对 `row` 是列号、对 `col` 是行号（0–7），对 `array` 是从核号（0–63）。

全套扫描可在项目根目录提交一个作业，以免每项重新排队：

```sh
bsub -I -q QUEUE -n 1 -cgsp 64 -mpecg 1 bash bench/run_sweep.sh results
```

脚本把每项结果存到 `results/`。脚本运行前可按论文需要修改消息大小和重复次数。单项程序返回非零代表参数错误、启动失败或数据校验失败；不要把有 `errors>0` 的性能结果用于结论。

## 5. 测量定义

### DMA

每个活跃从核使用独立的主存槽位和 LDM 缓冲，主存槽位起始地址 128 B 对齐。先执行 8 次预热，再计时 `reps` 次。`get/put` 为阻塞接口；`iget/iput` 每次发起后立刻等待本地 reply 达到 1，因此它们测量的是 **单请求非阻塞接口的完成开销**，不是多请求流水化峰值。计时不包含 `athread_spawn/join`、缓冲初始化或最终校验。

CSV 逐核给出周期数，`aggregate` 行用 64 核中最大的周期数计算并发吞吐：

```text
cycles_per_op = max_PE_cycles / reps
aggregate_bytes_per_cycle = bytes * reps * active_pes / max_PE_cycles
GiB/s = aggregate_bytes_per_cycle * core_clock_MHz * 1e6 / 2^30
```

频率未从手册假设，请在平台上记录实际从核频率后换算。重复传同一槽位是稳定的局部负载；若要测更大工作集，需要扩展主存槽位和轮转地址。

### RMA 单对单拓扑

遍历所有 64×63 个非自身有向对 `(initiator, peer)`。每次只有这一对从核参与传输，其他从核只参加阵列同步。每对先执行 4 次预热，再计时 `reps` 次 `athread_rma_iput` 或 `athread_rma_iget`，**每次等待本地 reply**；远端等待累计 reply 后校验数据。两个数组同步位于计时区外。因此 CSV 的 `cycles_per_op` 是该方向该大小的 **发起核完成周期/次**，包含接口与 reply 等待，不是单程物理链路延迟。不同从核计时器无需跨核同步，因为每项只读取发起核的本地周期差。

`same_row`、`same_col`、`diagonal`、`other` 分组直接体现 8×8 阵列位置；曼哈顿距离是坐标描述符，不能直接当作硬件跳数。矩阵可用于发现行/列非对称、边缘和热点。自通信标记 `self_skipped`，不纳入统计。`get` 与 `put` 的方向语义都是“发起核→被访问核”；实际 payload 对 `get` 是反向流动，应分别解释两张矩阵。

### RMA 广播

`row` 在 8 行同时各做一个 8 核广播；`col` 在 8 列同时各做一个 8 核广播；`array` 在 64 核做一个全阵列广播。4 次预热后计时 `reps` 次集合阻塞接口，记录所有核的周期并取最大值。`logical_bytes_per_cycle` 按 64 个接收核各收到 `bytes` 计算，是逻辑交付量，不应解释为物理网络字节数。

## 6. 拓扑分析与实验记录

```sh
python3 bench/analyze_topology.py results/rma_put_64B.csv --origin 0
python3 bench/analyze_topology.py results/rma_get_64B.csv --origin 27
```

分析器打印同行/同列/对角/其他关系的中位数与范围、曼哈顿距离分组中位数，以及指定发起核到各目的核的 8×8 周期图。论文中建议至少保留以下元数据：机器/分区、CPU 型号与核组号、编译器和运行库版本、编译选项、从核频率和 D-cache/LDM 配置、队列/独占情况、消息大小、重复次数、每项原始 CSV、重复作业次数及其波动。建议每个规模至少独立提交 3 次，汇报中位数与离散范围。

## 7. 限制与适配点

- 默认使用单个完整核组；少于 64 个从核会使 `athread_ssync_array()` 无法正确配对。
- RMA 和广播从核各使用两个 64 KiB 静态 LDM 缓冲。手册的默认 D-cache 为 32 KiB；若站点将 D-cache 设为 128 KiB 或启用较大的共享 LDM，需要缩小 `BENCH_MAX_BYTES` 并重新编译，以免局存空间不足。
- RMA 远端指针依赖所有从核的 `__thread_local` 对象具有相同 LDM 布局；它们由同一个从核程序镜像生成，符合手册示例的用法。
- 手册给出的是 SW39000 环境。若目标为另一代申威处理器，首先核对 RMA API、LDM 大小、从核编号映射、广播 `root` 语义和作业参数。
- 本工程仅测 RMA 单对单与集合广播；RMA 多播掩码、共享 LDM 模式、跨核组通信和 DMA 跨步传输不是本轮结果的一部分。
