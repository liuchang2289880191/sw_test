# DMA 边界、核数和主存映射实验

这套实验针对旧结果中 put/iput 在 128 B 附近的跃变与偏移敏感性，以及逐核位置差异。默认最大消息为 64 KiB，支持可选的 128 KiB 模式。新代码尚待神威平台编译、运行验证；本地模拟校验不提供硬件性能结果。

## 1. 一键运行

将以下文件一并同步到服务器 `bench/`：`dma_host.c`、`dma_slave.c`、`bench_common.h`、`run_dma.sh`、`run_dma_boundary.sh`、`collect_dma_study.awk`、`DMA_BOUNDARY.md`。同步后在登录节点执行：

```sh
cd ~/liuchang/sw_test/bench
module load swgcc/1473
bash run_dma_boundary.sh q_share
```

扩大到 **128 KiB**：

```sh
DMA_MAX_BYTES=131072 bash run_dma_boundary.sh q_share
```

两种模式均默认显式提交 `-cache_size 0`，使跨容量比较使用相同的 Cache 请求配置；`build_info.txt` 记录该选项。128 KiB 模式可能出现静态 LDM 超过 128 KB 的链接警告。必须确认实际**私有 LDM**能容纳 128 KiB 数据缓冲、参数、应答字和运行库数据；不能仅凭总容量 256 KiB 或编译成功判断安全。《神威众核编程指南》2.4.2、4.1、4.3 节说明 Cache 和连续共享段均会占用 LDM；本脚本未设置共享段，也不使用 `-b` 将栈搬入 LDM。若现场配置不满足条件，使用默认 64 KiB 模式。

`DMA_CACHE_SIZE=32` 可请求 32 KiB Cache；大于 64 KiB 的数据缓冲禁止选择 128 KiB Cache。配置与旧作业不同会影响比较，应随结果保存实际 Cache/共享 LDM 设置。`q_share` 名称不代表独占；本实验申请 1 MPE、1 CG、64 CPE，活跃负载在从核程序内控制。

脚本保留已跑通的方式：调度器**直接启动一个二进制**；在该进程内完成分配、athread 初始化、逐项 spawn/join、最终 halt/free。计算节点不需要 Bash、Python 或派生进程。登录节点使用 awk 校验和汇总。每次新建结果目录，任一数据校验失败即停止；只有完整复核后才出现 `COMPLETE`。

原入口 `bash run_dma.sh q_share` 仍运行旧的 224 项扫描（默认容量）。

## 2. 实验矩阵

所有组均测 get、put、iget、iput，活跃核数为 **1、2、4、8、16、32、64**；物理活跃 ID 固定为 `0..N-1`。

| 组（phase） | 消息大小 | 主存偏移 | 槽步长和映射 |
|---|---|---|---|
| boundary | 64、96、124、128、132、192、252、256、260 B | 0、4、64、124 B | `capacity+128`，identity |
| load | 下列全部带宽扫描尺寸 | 0、4 B | `capacity+128`，identity |
| mapping | 64、128、256 B；4、32、64、96、128 KiB | 0、4 B | 4 种步长 × 4 种映射 |

带宽扫描尺寸（B）：

```text
8 16 32 64 96 124 128 132 192 252 256 260 384 512 768
1024 1536 2048 3072 4096 6144 8192 12288 16384 24576
32768 49152 65536 98304 131072
```

自动跳过超过编译容量的消息。64 KiB 模式有 **7952** 项正式测量（1008 boundary + 1568 load + 5376 mapping），128 KiB 模式有 **9856** 项（1008 + 1680 + 7168）；两者另有 8 项小规模正确性检查。这里的每项只有一个计时间隔；循环次数不是独立重复。

小于 1 KiB 的消息每项循环 10000 次，其余循环 1000 次；预热 8 次。iget/iput 每次立即等待完成，仍是 **single-outstanding**，没有引入队列窗口。同步、主存初始化、逐字节校验、CSV 和日志均在计时区外。

## 3. 槽步长与映射

设容量为 `C`，扫描步长为 `C+128`、`C+256`、`C+4096`、`2C` B。例如 64 KiB 时为 **65664、65792、69632、131072 B**。若某容量使两个步长相等，自动去重。所有步长为 128 B 整数倍，能够容纳最大消息及 124 B 偏移，不会使两个槽重叠。

| mapping | `slot_of_pe[tid]` | 用途 |
|---|---|---|
| identity | `tid` | 顺序基准 |
| reverse | `63-tid` | 对换低、高地址槽 |
| transpose | `(tid%8)*8+tid/8` | 行列转置排列 |
| shuffle | 64 槽 Fisher–Yates 排列 | 打散核 ID 与地址关联 |

shuffle 使用显式 uint32 xorshift，默认种子 `20261005`。相同种子在整个作业内得到相同排列；可用 `DMA_MAPPING_SEED=12345` 更换。随机的是**槽映射**，运行顺序仍固定，不能将其解释为随机执行顺序或独立重复。

src/dst 各分配 `64 × max(2C,C+4096)` B，所有案例复用这两个固定基地址。实际地址为：

```text
src_address = src_base + slot_of_pe[tid] * slot_stride + offset
dst_address = dst_base + slot_of_pe[tid] * slot_stride + offset
```

源数据和 put 校验的模式始终绑定 **tid**，因此换槽不会降低正确性检查的辨别能力。逐核 CSV 保存槽号和两端主存地址，汇总器还会检查槽排列、地址基准是否固定、每核应答、最大耗时和聚合带宽是否一致。

64 核下，每种排列使用同一组 64 个主存地址，适合判断差异更倾向于随核还是随地址移动。核数小于 64 时，换映射也会改变活跃地址子集；部分核实验不能单独区分这两者。只记录虚拟地址，尚未控制或确认物理页、内存 bank/channel 映射；本实验也没有扫描不同的物理活跃核集合。

## 4. 输出与如何比较

| 文件 | 内容 |
|---|---|
| `plan.csv` | 完整测量清单、执行序号、分组、参数与文件名 |
| `slot_maps.csv` | 四种映射的全部 64 核→槽关系 |
| `raw/case_XXXXXX.csv` | 每项逐核数据及 aggregate 行 |
| `study_summary.csv` | 每项聚合周期、cycles/op、bytes/cycle 与布局参数 |
| `study_scaling.csv` | 相同组、消息、偏移、步长、映射下，2–64 核相对 1 核的带宽比和效率 |
| `source/`、`build_info.txt`、`build.log` | 代码与编译器/选项快照 |
| `compute.txt`、`cpuinfo.txt`、`job.log` | 节点信息与执行日志 |
| `RUN_COMPLETE`、`COMPLETE` | 程序测完 / 登录节点完整复核成功 |

新 raw CSV 在旧 11 列末尾追加 `slot_stride,mapping,mapping_seed,slot,src_address,dst_address`。单项旧命令和 `--sweep` 的 CSV 格式保持原样。旧 `analyze_dma_results.py` 针对 224 项基线设计，不能直接解析新实验。

建议按以下顺序读结果：

1. **边界：**固定 mode、N、stride、mapping，画大小×偏移的 cycles/op 和带宽热图，重点比较 124/128/132、252/256/260 B。可以计算覆盖的 128 B 地址块数量 `ceil(((address mod 128)+S)/128)`，但不能直接断言它等于硬件事务数。若阈值随偏移平移而非固定在消息长度上，优先考虑地址边界相关解释。
2. **负载：**固定 mode、S、offset，画 N–聚合带宽曲线。扩展比为 `BW(N)/BW(1)`，并行效率为该比值除以 N。比较小消息与大消息的饱和位置。
3. **映射：**固定 S、N、offset，先比较步长，再比较排列。逐核异常若随相同地址槽移动，支持主存地址关联；若持续跟随物理 tid，支持位置关联；两者都有则需联合建模。对 64 核的固定地址集合对照给予更高权重。
4. **大消息：**观察 32、48、64、96、128 KiB 是否进入平台区。用 bytes/cycle 比较；计数器频率未标定前不直接报告 GB/s。put 完成等待按手册表明源 LDM 数据已被取走，不能单独当作主存持久写入时间。

这些测量可以定位性能转折和映射敏感性，但共享资源、运行顺序与单次波动仍可能影响结果；下一轮独立重复后再估计置信区间。

## 5. 单项复核与只生成清单

例如 16 核、132 B、124 B 偏移、69632 B 步长、转置映射：

```sh
bsub -I -q q_share -n 1 -cgsp 64 -mpecg 1 -cache_size 0 \
  /本次结果目录/dma_bench put 132 10000 16 124 69632 transpose 20261005
```

参数中的 bytes 必须为 4 B 整数倍，offset 为 0..124 的 4 B 整数倍，stride 为 128 B 整数倍且至少为 bytes+offset。扩展参数必须一起提供。

只生成清单（不初始化 athread、不发 DMA）：

```sh
bsub -I -q q_share -n 1 -cgsp 64 -mpecg 1 \
  /本次结果目录/dma_bench --plan-study /共享目录/plan_preview.csv 20261005
```

这是神威二进制，登录节点为 x86 时仍需经调度器启动。正常运行会自动生成同一份清单，无需先执行预览。
