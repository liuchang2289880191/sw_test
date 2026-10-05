# 神威 DMA / RMA benchmark（含 SW26010Pro 2×2 小簇实验）

本工程依据目录中的《SACA编程指南-v0.62.pdf》编写 Athread 接口代码，使用 **单个 8×8 从核阵列（64 个从核）**。该手册以 SW39000 为背景；新增的 2×2 小簇实验以 SW26010Pro 为研究目标。提供源代码、构建命令、测量定义和结果分析脚本；用户已在神威平台完成 DMA 完整扫描并通过校验，正式性能曲线尚待汇总 CSV 分析，RMA 尚待运行验证。目标机器的运行库/编译器版本若与手册不同，应先核对 `slave.h` 中的接口声明。

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

用户在 `sw_hpc_78` 上提供的 `module avail` 已确认有 `swgcc/1432`、`swgcc/1449`、`swgcc/1456`、`swgcc/1473`；当时没有加载任何模块。该站点可先使用 `swgcc/1473`。如果当前目录已经是 `~/liuchang/sw_test/bench`，执行：

```sh
module load swgcc/1473
hash -r
command -v swgcc
swgcc -v
make SWCC=swgcc SLAVE_FLAGS="-mslave -msimd" dma_bench
```

这一步加载编译器并构建 DMA 程序，不提交 benchmark 作业。用户已确认 `swgcc/1473` 的目标为 `sw_64sw6a-sunway-linux-gnu`。该版本的 `slave.h` 引入 `crts2ath.h`，DMA 接口在未启用 SIMD 时报告 `Please use -msimd option!!!`，因此从核编译必须加 `-msimd`。更新后的 Makefile 已将 `SLAVE_FLAGS` 默认设为 `-mslave -msimd`，适用于全部 DMA/RMA 从核源文件。

若服务器仍使用将 `-mslave` 写死的旧 Makefile，传入 `SLAVE_FLAGS` 不会改变其命令。此时可先直接编译和链接：

```sh
swgcc -mhost -O2 -c dma_host.c -o dma_host.o
swgcc -mslave -msimd -O2 -c dma_slave.c -o dma_slave.o
swgcc -mhybrid dma_host.o dma_slave.o -o dma_bench
```

用户已在 `sw_hpc_78` 的 `swgcc/1473` 环境确认四个目标均编译、链接成功：`dma_bench`、`rma_bench`、`rma_bcast_bench`、`rma_cluster_bench`。三个 RMA 目标报告静态 LDM 用量超过 128 KB 的警告，具体见下面的说明。DMA 已在作业 8419757 中完成 8 项正确性检查和 224 项正式扫描，所有数据校验及登录节点 CSV 复核均通过；三个 RMA 目标仍仅确认编译、链接成功。

在同一 `bench` 目录继续编译 RMA 程序：

```sh
make SWCC=swgcc SLAVE_FLAGS="-mslave -msimd" rma_bench rma_bcast_bench rma_cluster_bench
```

`command -v swgcc` 应打印路径；若模块加载失败或之后仍找不到命令，保留加载错误和 `module show swgcc/1473` 输出以核对配置。从项目根目录编译则在命令中添加 `-C bench`；编译全部程序可去掉目标名称。

以下是其他站点或环境仍未配置时的检查方法。

先在登录节点检查实际工具链。不同站点不一定把 `swgcc` 放进 PATH；下面的脚本仅查询命令路径、机器架构与 module，不编译或运行测试。请从项目根目录执行：

```sh
bash bench/check_toolchain.sh
```

也可直接查询：

```sh
command -v gcc swgcc swcc sw5cc sw9cc sw9gcc mpicc
gcc -dumpmachine
gcc -v
type module
```

这些名字只是查找候选项，不表示每个编译器都支持当前源码。如果有 `module`，用 `module list`、`module avail` 查看站点配置，并按站点说明加载对应工具链；不要猜测 module 名称。若没有工具链路径，需要站点提供环境初始化脚本或已成功编译 Athread 程序的命令。

直接执行 `gcc` 时出现“没有输入文件”是正常的，但只能说明命令存在。站点可能将申威定制编译器安装为 `gcc`；需根据 `gcc -v` 的配置、目标架构及站点接口说明判断。如果确认该 `gcc` 支持当前 SACA 的 `-mhost/-mslave/-mhybrid` 选项，从项目根目录用 `make -C bench SWCC=gcc dma_bench`；若已经位于 `bench` 目录，则用 `make SWCC=gcc dma_bench`。普通 x86/ARM GCC 无法据此生成神威主从核程序。

用户提供的系统 `gcc` 为 **Red Hat GCC 4.8.5，目标 `x86_64-redhat-linux`**，不能使用上述 `SWCC=gcc` 分支；此站点应加载开头列出的 `swgcc` 模块。若其他站点没有可见的工具链或 module，请管理员提供神威主核/从核编译器路径、环境初始化命令，以及一个成功编译 Athread 程序的示例。`Makefile` 已对名为 `gcc` 且报告 x86/ARM 目标的情况提前停止并提示。

确认编译器版本、主核/从核/混合链接选项，以及新一代 DMA/RMA 接口头文件之后再构建。仅当实际工具链是手册所述的 `swgcc` 接口时，执行：

```sh
swgcc -v
make -C bench SWCC=swgcc
```

编译成功后得到 `bench/dma_bench`、`bench/rma_bench`、`bench/rma_bcast_bench`、`bench/rma_cluster_bench`。`Makefile` 的 `SWCC`、`HOST_FLAGS`、`SLAVE_FLAGS`、`LINK_FLAGS` 均可覆盖；默认分别为 `-mhost`、`-mslave -msimd`、`-mhybrid`。主从核及混合链接选项依据当前目录手册，`-msimd` 同时依据 `swgcc/1473` 的实际 DMA 编译诊断补入。`CPPFLAGS`、`LDFLAGS`、`LDLIBS` 可补充站点要求的头文件和库配置。

例如确认安装的是兼容这些选项的 `swgcc`，但未在 PATH 中，可用 `make -C bench SWCC=/实际安装路径/swgcc`。其他工具链可能采用不同选项：[无锡中心的旧版编译手册](https://www.nsccwx.cn/Upload/%E7%BC%96%E8%AF%91%E7%94%A8%E6%88%B7%E6%89%8B%E5%86%8C-f6641a5d3e914849b424558571a7430e.pdf)使用 `sw5cc -host/-slave/-hybrid`，这不能证明它支持本工程使用的新一代 RMA API、`__thread_local` 或 LDM 容量。不要仅替换编译器名称后直接套用；应先核对实际版本、目标 CPU 和 `slave.h`。

### 静态 LDM 超过 128 KB 的警告

用户提供的成功链接日志如下；这些数字是链接器报告的静态用量，不包含后续可能需要的动态 LDM 或 LDM 栈空间。

| 目标 | 静态 LDM 用量 |
|---|---:|
| `rma_bench` | 133608 B（约 130.48 KiB） |
| `rma_bcast_bench` | 132584 B（约 129.48 KiB） |
| `rma_cluster_bench` | 133736 B（约 130.60 KiB） |

主要来源是每核两个 64 KiB 缓冲，再加应答字、参数、统计及运行库数据。`WARN: LDM static space is more than 128KB` 表示超过静态用量告警阈值，不能据此推断物理 LDM 总容量仅为 128 KiB。目录中 SACA 手册 PDF 第 13–14 页列出总容量 256 KiB、默认 D-cache 32 KiB：若目标机器确实使用此配置且没有共享 LDM，名义上剩余 224 KiB，当前静态用量小于该值。若 D-cache 为 128 KiB，则名义剩余仅 128 KiB，当前三个 RMA 镜像均超出；共享 LDM 还会减少私有空间。必须核对实际配置，链接成功本身不验证运行时容量。

**可选 32 KiB 配置：**更新服务器的 `bench_common.h` 及相关文件后，在 `bench` 目录执行：

```sh
make -B SWCC=swgcc SLAVE_FLAGS="-mslave -msimd" CPPFLAGS="-DBENCH_MAX_BYTES=32768" all
```

`-B` 强制重编译主核和从核对象，避免复用旧容量的目标文件。此配置将两个缓冲总量从 128 KiB 降至 64 KiB；静态用量预期减少约 64 KiB，具体以新的链接日志为准。消息大小及 `bytes*window*max_incoming` 的上限变为 32768 B；8–256 B 延迟矩阵与常用争用对照仍可测，64 KiB 消息需恢复默认配置后测量。恢复方法是在同一目录执行 `make -B SWCC=swgcc SLAVE_FLAGS="-mslave -msimd" all`，并去掉其他来源中同一宏的覆盖。

32 KiB 可选配置尚未在神威平台编译验证。按此配置批量测试时，从项目根目录将 `BENCH_MAX_BYTES=32768` 传给扫描脚本（例如在已分配的计算资源内使用 `BENCH_MAX_BYTES=32768 bash bench/run_cluster_sweep.sh cluster_results_32k`），让脚本跳过容量不允许的规模；该环境变量不改变已编译二进制的容量。测试记录需保留编译时的容量宏。

## 4. 单项运行

### DMA 一键运行入口

将更新后的 `run_dma.sh` 与 `dma_host.c` 同步到服务器的 `bench` 目录，与 `dma_slave.c` 和 `bench_common.h` 放在一起。新版入口要求主核代码支持 `--sweep`，需同时更新这两个文件；不依赖 `run_dma_sweep.sh` 或 Python。

```sh
cd ~/liuchang/sw_test/bench
bash run_dma.sh
```

未指定队列时，脚本用 `bqueues -u` 列出当前用户队列，提示输入一个可用队列名；队列必须由用户选择。已知队列时可直接 `bash run_dma.sh 实际队列名`，也可预先设置 `DMA_QUEUE`。这是执行命令，**会编译并提交一个真实作业**；本地交付时未实际提交。

入口自动检查 `swgcc`；命令不存在且 `module` 可用时加载 `swgcc/1473`，随后核对编译目标。它复制 DMA 源文件到新结果目录，按已经验证过的 `-mhost`、`-mslave -msimd`、`-mhybrid` 命令（加 `-O2 -g` 编译、`-g` 链接）生成独立二进制，保存编译器版本及日志。然后以 `bsub -I -q 队列名 -n 1 -cgsp 64 -mpecg 1 /结果目录/dma_bench --sweep /结果目录` 直接启动一个 DMA 进程。全部案例在该进程内循环运行，athread 初始化、缓冲分配和最终释放各执行一次，每项单独 spawn/join；无需计算节点 shell 或派生子进程。结果目录均预先在登录节点创建。

作业内先执行四模式 × 两种活跃核数的 8 个小规模正确性检查，再扫描四模式、1/64 核、主存偏移 0/4 B 和 8 B–64 KiB 的消息大小，共 224 项。小于 1 KiB 时重复 10000 次，其余规模重复 1000 次。每项重新清空目的缓冲和结果槽，避免之前的传输数据掩盖本次错误；数据校验失败时保留该项 CSV 并停止。正常释放资源后写入 `RUN_COMPLETE`。作业结束后，登录节点用 awk 复核每项 CSV 结构、活跃核数量和所有 `errors`，生成汇总；仅完整通过复核后写入 `COMPLETE`。

用户在 `q_share` 的旧作业 8419325 因计算节点找不到 Bash，尚未启动 DMA；随后 POSIX 节点脚本作业 8419400 在第一个 `get 8 10 1 0` 程序上以状态 139 退出。最终直接启动诊断作业 8419534 已成功完成同一小规模检查，所有主核阶段均结束、`errors=0`。该单项测得总计 12580 cycles、平均 1258 cycles/op，但仅重复 10 次，不作为稳定延迟或峰值带宽结论。基于直接启动的成功验证，新版完整扫描也直接提交 DMA 二进制，原有段错误的具体底层原因尚未确定。

新版 `dma_host.c` 在标准错误中记录主核进入、内存分配及地址、athread 初始化、spawn、join、halt、输出和释放阶段，并分别报告运行库返回码；所有阶段日志均在 DMA 计时区外，普通扫描的阶段和错误输出全部进入 `job.log`。新增的单进程完整扫描已在模拟 SACA 运行库下验证案例数、重复启动、校验失败停止与汇总流程。

**神威平台完整运行验证（2026-10-05）：**用户执行 `bash run_dma.sh q_share`，作业 8419757 正常结束。四模式 × 1/64 核的 8 项正确性检查，以及四模式 × 两种核数 × 两种偏移 × 14 种消息大小的 224 项正式扫描均通过，所有 `errors=0`；最终 halt/free 及登录节点 CSV 复核也完成。结果目录为 `dma_results_20261005_183213_10036/`，已生成 `summary.csv` 和 `scaling.csv`。当前收到的终端日志仅展示进度和校验成功，尚未取得这两个汇总文件中的正式性能数据，因此暂不据此给出延迟、带宽或扩展性结论。

如需重新检查最小单项，在 `bench` 目录只做一次直接诊断：

```sh
DMA_DIAG_ONLY=1 bash run_dma.sh q_share
```

此模式编译后以 `bsub ... /结果目录/dma_bench get 8 10 1 0` 直接启动程序，不经过计算节点 shell，也不执行全套扫描。完整终端信息及阶段日志存入 `probe.log`。最后一个 `DMA_STAGE` 可帮助划分主核内存分配、运行库初始化、从核启动/等待或后处理问题；未出现 `host.enter` 时还需检查程序入口之前的加载/运行环境。直接诊断通过而节点脚本内失败时，需要进一步检查子进程获取从核资源的条件，不能立即认定具体原因。诊断模式通过仅验证该单项，不生成完整扫描的 `COMPLETE` 标记。

默认结果存入 `bench/dma_results_时间_进程号/`，每次使用新目录。第二个位置参数可指定一个尚不存在且父目录已存在的结果目录：`bash run_dma.sh 实际队列名 新结果目录`。目录包括：

| 文件 | 内容 |
|---|---|
| `source/`, `dma_bench`, `run_dma.sh` | 本次源代码、二进制及入口快照 |
| `build_info.txt`, `build.log` | 编译器版本、容量、选项和编译日志 |
| `job.log` | 调度器、扫描进度、阶段日志及程序错误输出 |
| `compute.txt`, `cpuinfo.txt`（若可读） | 节点环境变量、容量及 CPU 信息（环境变量可能不可用） |
| `smoke/`, `raw/` | 8 项正确性检查和正式扫描原始 CSV |
| `summary.csv` | 各正式扫描的聚合吞吐和完成周期 |
| `scaling.csv` | 相同模式、大小、对齐条件下的 64 核／单核带宽比 |
| `REPORT.md`, `RUN_COMPLETE`, `COMPLETE` | 测量说明、节点扫描结束标记及登录节点复核成功标记 |

可选 32 KiB 容量用 `BENCH_MAX_BYTES=32768 bash run_dma.sh 实际队列名`，需使用支持宏覆盖的新 `bench_common.h`。该配置只编译本次作业的独立 DMA 镜像，正式扫描为 208 项。脚本保留 B/cycle，不假设从核频率；cache、共享 LDM、资源共享情况与实际频率需随实验记录。入口为交互作业，会一直等到完成，保持提交终端开启即可。

### 手动提交单项

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

`bytes` 必须是 4 B 的整数倍，默认范围 4–65536 B；可选容量配置以上限 `BENCH_MAX_BYTES` 为准。`dma_bench` 的 `active_pes` 为 1 或 64；`offset` 为 0（128 B 对齐）或 4（仅 4 B 对齐），用于比较未按 128 B 对齐的 DMA 影响。RMA `put|get` 的 `initiator` 表示发起核，`peer` 表示远端核。广播的 `root` 对 `row` 是列号、对 `col` 是行号（0–7），对 `array` 是从核号（0–63）。

以下历史全套扫描示例要求计算节点可调用 Bash。用户当前 `q_share` 已报告找不到 Bash；DMA 请使用上述直接提交二进制的一键入口。其他站点若支持 Bash，可在项目根目录提交一个作业，以免每项重新排队：

```sh
bsub -I -q QUEUE -n 1 -cgsp 64 -mpecg 1 bash bench/run_sweep.sh results
```

脚本把每项结果存到 `results/`。脚本运行前可按论文需要修改消息大小和重复次数。单项程序返回非零代表参数错误、启动失败或数据校验失败；不要把有 `errors>0` 的性能结果用于结论。

## 5. 测量定义

### DMA

只扫描 DMA 时，在 `bench` 目录使用 `bash run_dma.sh q_share`，构建、提交和汇总方法见上面的一键入口说明。早期的 `run_dma_sweep.sh` 使用 Bash，仅适用于计算节点确实提供 Bash 的环境，当前 `q_share` 请使用新版入口。

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
- RMA 和广播从核默认各使用两个 64 KiB 静态 LDM 缓冲。按上面的告警说明确认 cache、共享 LDM 和栈设置；需要减小容量时可用 `CPPFLAGS="-DBENCH_MAX_BYTES=32768"` 强制重新编译。
- RMA 远端指针依赖所有从核的 `__thread_local` 对象具有相同 LDM 布局；它们由同一个从核程序镜像生成，符合手册示例的用法。
- 手册给出的是 SW39000 环境。若目标为另一代申威处理器，首先核对 RMA API、LDM 大小、从核编号映射、广播 `root` 语义和作业参数。
- 本工程包含 RMA 单对单、ping-pong、小簇多流争用与集合广播；RMA 多播掩码、共享 LDM 模式、跨核组通信和 DMA 跨步传输不是本轮实验的一部分。
