#!/usr/bin/env python3
"""Analyze saved DMA CSVs; does not compile or execute a Sunway benchmark."""
import argparse
import csv
import hashlib
import itertools
import json
from pathlib import Path
import statistics

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

MODES = ("get", "put", "iget", "iput")
SIZES = [2 ** n for n in range(3, 17)]
COLORS = dict(zip(MODES, ("#2563eb", "#dc6b20", "#0b8f78", "#a34dbb")))


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def key(r):
    return r["mode"], int(r["active_pes"]), int(r["offset"]), int(r["bytes"])


def num(r, name):
    return float(r[name])


def validate(root):
    summary = read_csv(root / "summary.csv")
    data = {key(r): r for r in summary}
    expected = set(itertools.product(MODES, (1, 64), (0, 4), SIZES))
    assert len(summary) == len(data) == 224 and set(data) == expected
    assert len(list((root / "raw").glob("*.csv"))) == 224
    assert len(list((root / "smoke").glob("*.csv"))) == 8
    for marker in ("COMPLETE", "RUN_COMPLETE"):
        assert (root / marker).read_text().strip() == "completed_cases=224"
    pe_rows = 0
    raw = {}
    digests = {}
    cases = [(root / "raw" / f"dma_{m}_{n}pe_{s}B_offset{o}.csv",
              (m, n, o, s), 10000 if s < 1024 else 1000)
             for m, n, o, s in sorted(expected)]
    cases += [(root / "smoke" / f"{m}_{n}pe.csv", (m, n, 0, 8), 10)
              for m, n in itertools.product(MODES, (1, 64))]
    for path, k, reps in cases:
        rows = read_csv(path)
        pes = [r for r in rows if r["pe"] != "aggregate"]
        aggs = [r for r in rows if r["pe"] == "aggregate"]
        assert len(rows) == k[1] + 1 and len(aggs) == 1
        assert [int(r["pe"]) for r in pes] == list(range(k[1]))
        assert all(key(r) == k and int(r["reps"]) == reps
                   and int(r["errors"]) == 0 and int(r["cycles"]) > 0
                   and r["benchmark"] == "dma" for r in rows)
        for r in rows:
            assert abs(num(r, "cycles_per_op") - int(r["cycles"]) / reps) <= 0.0000006
        agg = aggs[0]
        assert int(agg["cycles"]) == max(int(r["cycles"]) for r in pes)
        bw = k[3] * reps * k[1] / int(agg["cycles"])
        assert abs(num(agg, "aggregate_bytes_per_cycle") - bw) <= 0.0000000006
        if path.parent.name == "raw":
            assert all(data[k][name] == agg[name] for name in data[k])
            raw[k] = pes
        pe_rows += len(pes)
        digests[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    scaling = read_csv(root / "scaling.csv")
    seen = set()
    for r in scaling:
        k = r["mode"], int(r["offset"]), int(r["bytes"])
        assert k not in seen
        seen.add(k)
        one = num(data[k[0], 1, k[1], k[2]], "aggregate_bytes_per_cycle")
        many = num(data[k[0], 64, k[1], k[2]], "aggregate_bytes_per_cycle")
        assert abs(num(r, "single_bytes_per_cycle") - one) <= 1e-9
        assert abs(num(r, "aggregate64_bytes_per_cycle") - many) <= 1e-9
        assert abs(num(r, "bandwidth_ratio64_to1") - many / one) <= 1e-6
    assert len(scaling) == len(seen) == 112
    for name in ("summary.csv", "scaling.csv", "cpuinfo.txt", "build_info.txt",
                 "source/dma_slave.c", "source/dma_host.c", "source/bench_common.h"):
        digests[name] = hashlib.sha256((root / name).read_bytes()).hexdigest()
    return data, raw, {"sweep_cases": 224, "smoke_cases": 8,
                       "scaling_pairs": 112, "per_pe_rows": pe_rows,
                       "all_reported_errors_zero": True,
                       "summary_matches_raw": True,
                       "scaling_matches_summary": True,
                       "source_sha256": digests}


def table(headers, rows):
    return "\n".join(["| " + " | ".join(headers) + " |",
                      "| " + " | ".join(["---"] * len(headers)) + " |"]
                     + ["| " + " | ".join(map(str, r)) + " |" for r in rows])


def analyze(root, out):
    data, raw, checks = validate(root)
    out.mkdir(parents=True, exist_ok=True)
    bw = lambda m, n, o, s: num(data[m, n, o, s], "aggregate_bytes_per_cycle")
    cy = lambda m, n, o, s: num(data[m, n, o, s], "cycles_per_op")
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "savefig.dpi": 180})

    def xaxis(ax):
        ax.set_xscale("log", base=2)
        ax.set_xticks([8, 32, 128, 512, 2048, 8192, 32768, 65536],
                      ["8 B", "32 B", "128 B", "512 B", "2 KiB", "8 KiB", "32 KiB", "64 KiB"])
        ax.tick_params(axis="x", labelrotation=35)
        ax.grid(alpha=.18)
        ax.set_xlabel("Message size")

    def save(fig, stem):
        fig.savefig(out / (stem + ".png"), bbox_inches="tight")
        fig.savefig(out / (stem + ".svg"), bbox_inches="tight")
        plt.close(fig)

    fig, axs = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    for ax, (n, o) in zip(axs.flat, itertools.product((1, 64), (0, 4))):
        for m in MODES:
            ax.plot(SIZES, [bw(m, n, o, s) for s in SIZES],
                    marker="o", markersize=4, color=COLORS[m],
                    linestyle="--" if m.startswith("i") else "-", label=m)
        ax.set_title(f"{n} active CPE(s), host offset {o} B")
        ax.set_ylabel("Aggregate payload bandwidth (B/cycle)")
        ax.set_ylim(bottom=0)
        xaxis(ax)
        ax.legend(ncol=2)
    fig.suptitle("DMA bandwidth: one outstanding request per CPE")
    save(fig, "bandwidth")

    fig, axs = plt.subplots(1, 2, figsize=(13, 4.8), constrained_layout=True)
    for ax, o in zip(axs, (0, 4)):
        for m in MODES:
            ax.plot(SIZES, [bw(m, 64, o, s) / bw(m, 1, o, s) for s in SIZES],
                    marker="o", markersize=4, color=COLORS[m], label=m,
                    linestyle="--" if m.startswith("i") else "-")
        ax.axhline(1, color="#444444", linestyle=":", label="Same as 1 CPE")
        ax.set_title(f"Host offset {o} B")
        ax.set_ylabel("64-CPE / 1-CPE aggregate bandwidth")
        ax.set_ylim(bottom=0)
        xaxis(ax)
        ax.legend(ncol=2)
    fig.suptitle("DMA scaling (ideal linear scaling would be 64)")
    save(fig, "scaling")

    fig, axs = plt.subplots(1, 2, figsize=(13, 4.8), constrained_layout=True)
    for ax, n in zip(axs, (1, 64)):
        for m in MODES:
            ax.plot(SIZES, [cy(m, n, 4, s) / cy(m, n, 0, s) for s in SIZES],
                    marker="o", markersize=4, color=COLORS[m], label=m,
                    linestyle="--" if m.startswith("i") else "-")
        ax.axhline(1, color="#444444", linestyle=":")
        ax.set_title(f"{n} active CPE(s)")
        ax.set_ylabel("Offset 4 B / aligned cycles per operation")
        ax.set_yscale("log", base=2)
        ax.set_yticks([.5, 1, 2, 4, 8, 16], ["0.5", "1", "2", "4", "8", "16"])
        xaxis(ax)
        ax.legend(ncol=2)
    fig.suptitle("Host address alignment penalty (greater than 1 means slower)")
    save(fig, "alignment")

    fig, axs = plt.subplots(1, 2, figsize=(13, 4.8), constrained_layout=True)
    for ax, m in zip(axs, ("get", "put")):
        for n in (1, 64):
            for o in (0, 4):
                ax.plot(SIZES, [cy(m, n, o, s) for s in SIZES], marker="o", markersize=4,
                        linestyle="--" if o else "-", label=f"{n} CPE(s), offset {o} B")
        ax.set_title(m)
        ax.set_ylabel("Cycles / op (maximum over active CPEs)")
        ax.set_yscale("log")
        xaxis(ax)
        ax.legend(fontsize=9)
    fig.suptitle("DMA completion time: 128 B is a strong boundary for 64-CPE writes")
    save(fig, "completion_time")

    fig, axs = plt.subplots(2, 3, figsize=(13, 8), constrained_layout=True)
    for ax, (m, s, o) in zip(axs.flat, [("get", 8, 0), ("get", 128, 0),
                                      ("get", 128, 4), ("put", 64, 0),
                                      ("put", 128, 0), ("put", 128, 4)]):
        values = np.array([num(r, "cycles_per_op") for r in raw[m, 64, o, s]]).reshape(8, 8)
        im = ax.imshow(values, cmap="viridis")
        for r, c in itertools.product(range(8), repeat=2):
            frac = (values[r, c] - values.min()) / (values.max() - values.min())
            ax.text(c, r, f"{values[r, c]:.0f}", ha="center", va="center",
                    fontsize=7, color="white" if frac < .5 else "black")
        ax.set_title(f"{m}, {s} B, offset {o} B")
        ax.set_xlabel("CPE ID % 8")
        ax.set_ylabel("CPE ID // 8")
        fig.colorbar(im, ax=ax, shrink=.75, label="cycles/op")
    fig.suptitle("Per-CPE DMA timings under 64-CPE load (each panel has its own color scale)")
    save(fig, "per_cpe")

    fits = []
    for m in MODES:
        for n in (1, 64):
            sizes = [s for s in SIZES if s >= (1024 if n == 1 else 4096)]
            x = np.array(sizes)
            y = np.array([cy(m, n, 0, s) for s in sizes])
            beta, alpha = np.polyfit(x, y, 1)
            pred = alpha + beta * x
            r2 = 1 - sum((pred - y) ** 2) / sum((y - y.mean()) ** 2)
            fits.append(dict(mode=m, active_pes=n, host_offset_bytes=0,
                             min_message_bytes=min(sizes), max_message_bytes=max(sizes),
                             alpha_cycles=float(alpha), beta_cycles_per_byte=float(beta),
                             effective_aggregate_bytes_per_cycle=float(n / beta),
                             r_squared=float(r2),
                             max_relative_residual=float(max(abs((pred - y) / y)))))
    checks["fits"] = fits
    checks["source_directory"] = str(root.resolve())
    (out / "verification_and_fits.json").write_text(
        json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")

    latency_rows = []
    for m in MODES:
        rng = [s for s in SIZES if s <= (128 if m in ("get", "iget") else 64)]
        vals = [cy(m, 1, 0, s) for s in rng]
        latency_rows.append([m, f"8–{max(rng)} B", f"{min(vals):.2f}–{max(vals):.2f}",
                             f"{statistics.median(vals) / 2.25:.2f}"])
    bw_rows = [[m, f"{bw(m,1,0,65536):.3f}", f"{bw(m,64,0,65536):.3f}",
                f"{bw(m,64,0,65536)/bw(m,1,0,65536):.3f}×",
                f"{bw(m,64,0,65536)*2.25:.2f}"] for m in MODES]
    scale_rows = [[f"{s} B" if s < 1024 else f"{s//1024} KiB"] +
                  [f"{bw(m,64,0,s)/bw(m,1,0,s):.2f}×" for m in ("get", "put")]
                 for s in (8, 64, 128, 1024, 4096, 16384, 32768, 65536)]
    align_rows = []
    for m, s in (("get",128),("get",4096),("get",65536),
                 ("put",64),("put",128),("put",256),("put",4096),("put",65536)):
        factor = cy(m,64,4,s)/cy(m,64,0,s)
        align_rows.append([m, str(s), f"{bw(m,64,0,s):.3f}", f"{bw(m,64,4,s):.3f}",
                           f"{factor:.2f}×", f"{(1-1/factor)*100:.1f}%"])
    async_rows = []
    for n in (1,64):
        for sync, async_ in (("get","iget"),("put","iput")):
            ratios = [bw(async_,n,0,s)/bw(sync,n,0,s) for s in SIZES]
            async_rows.append([str(n), f"{async_}/{sync}",
                               f"{min(ratios):.4f}–{max(ratios):.4f}",
                               f"{statistics.median(ratios):.4f}"])
    fit_rows = [[f["mode"], str(f["active_pes"]),
                 "1–64 KiB" if f["active_pes"] == 1 else "4–64 KiB",
                 f"{f['alpha_cycles']:.2f}", f"{f['beta_cycles_per_byte']:.6f}",
                 f"{f['effective_aggregate_bytes_per_cycle']:.2f}",
                 f"{f['r_squared']:.6f}"] for f in fits]
    pe_rows = []
    for m, s in (("get",8),("get",4096),("put",64),("put",128),("put",65536)):
        v = [num(r,"cycles_per_op") for r in raw[m,64,0,s]]
        pe_rows.append([m,str(s),f"{min(v):.2f}",f"{statistics.median(v):.2f}",
                        f"{max(v):.2f}", f"{statistics.pstdev(v)/statistics.mean(v)*100:.2f}%"])
    report = f"""# DMA 实测结果分析

数据集：`{root.name}`；作业 8419757，队列 `q_share`，2026-10-05。分析不编译、不提交或执行神威程序。

## 1. 结论

1. 数据完整：8 项正确性检查、224 项正式扫描、112 组扩展比均通过独立复核。共检查 {checks['per_pe_rows']} 条逐核记录，所有报告的错误为 0，汇总值与原始 CSV 一致。
2. 大消息下，64 核读取聚合带宽在约 20.5–21.3 B/cycle，写入在约 15–16.3 B/cycle。单核带宽随消息增大逐渐接近共享资源的有效吞吐上限，增加核数的收益随之缩小。
3. 最强的边界是 **128 B 对齐写入**：64 核 put 从对齐 64 B 的 {bw('put',64,0,64):.3f} B/cycle，跳到对齐 128 B 的 {bw('put',64,0,128):.3f} B/cycle。地址加 4 B 后，128 B 写入吞吐降到 {bw('put',64,4,128):.3f} B/cycle，耗时约为对齐时的 {cy('put',64,4,128)/cy('put',64,0,128):.2f} 倍。
4. iget 与 get 基本一致，iput 与 put 的差别也很小。这套实现中每次非阻塞操作之后立即等待，未测试流水化或计算通信重叠。
5. **平台识别：**本次 `cpuinfo.txt` 报告 `cpu revision: sw39000`，SPE 频率 2250 MHz。记录应标为该运行环境报告的 SW39000，不能直接作为 SW26010Pro 的性能参数。

## 2. 数据来源、单位和测量口径

主要数据来自 `summary.csv`，并逐项追溯 `raw/*.csv`；`scaling.csv` 的 112 个比值也重新计算。测试口径依据本次结果目录的 `source/dma_slave.c`、`source/dma_host.c` 和 `source/bench_common.h`，而非当前可能已修改的源码。环境依据 `build_info.txt`、`compute.txt`、`cpuinfo.txt`。

- get/iget：主存 → 本核 LDM；put/iput：本核 LDM → 主存。
- 消息 8 B–64 KiB，1 或 64 个活跃从核，主存偏移 0/4 B。偏移 4 B 仍满足 4 B 对齐，不满足 128 B 对齐；LDM 缓冲始终 128 B 对齐。
- 每核仅一个未完成请求，8 次预热不计时；小于 1 KiB 的消息重复 10000 次，其余重复 1000 次。屏障在计时循环外；计时不含主核初始化、spawn/join、校验、CSV 输出。
- 每次传输复用该核同一主存槽和同一 LDM 缓冲。槽间距 65664 B，64 核使用互不重叠的区域；每个主存分配约 4.008 MiB。这是预热后重复访问模式，未扫描更大的轮转工作集。
- `cycles_per_op` 在 summary 中是 **64 核中最大累计周期 / reps**，不是 64 核平均耗时。聚合带宽为 `S × reps × active / max(cycles)`，以计时前共同屏障后的各核局部区间近似整体吞吐。
- SACA 手册 PDF 第 60 页对供应方完成的定义是“数据已从本从核的 LDM 取走”。因此 put/iput 计时的完成边界不应额外解释成每次物理 DRAM 写入都已落地；主核的最终内容校验在 join 之后完成。

原始单位保留 **cycles、B/cycle**。`cpuinfo.txt` 的 `spe frequency [MHz]: 2250` 允许提供条件换算：如果该计数器按报告的 2.25 GHz SPE 频率递增，则 `ns = cycles / 2.25`，`GB/s = B/cycle × 2.25`（十进制）。手册 PDF 第 88 页称该接口为本从核周期计数器，但本次没有进行计数器频率独立标定；以下 ns/GB/s 均依此条件换算，图表使用原始单位。

## 3. 单核小消息：操作完成开销

对齐情况下，小消息的完成耗时有明显平台区间：

{table(['模式','取值区间','cycles/op 范围','区间中位数换算 ns（按 2.25 GHz）'],latency_rows)}

读取约 441 cycles，写入约 234–240 cycles。两者含循环、模式判断、接口和应答等待开销，可作为当前 API 实现下的微基准基线，不等同于纯硬件启动延迟。先前 10 次诊断得到 1258 cycles/op，本次正式小消息扫描为 10000 次，应以正式扫描值描述这个测试配置。

![完成耗时曲线](completion_time.png)

## 4. 带宽曲线和并发扩展

64 KiB、主存对齐时：

{table(['模式','单核 B/cycle','64 核聚合 B/cycle','64/1 带宽比','64 核 GB/s（按 2.25 GHz）'],bw_rows)}

64 核读取在 4–64 KiB 的范围约 20.50–21.34 B/cycle，形成较平的吞吐区间。64 核写入在 8–64 KiB 约 15.89–16.30 B/cycle。它们是本次单核组、单未完成请求、固定槽访问条件下的有效载荷吞吐，不代表全芯片或理论主存峰值。

![带宽曲线](bandwidth.png)

对齐时的代表性扩展比：

{table(['消息','get：64/1','put：64/1'],scale_rows)}

小消息能通过并发隐藏每核请求开销，但没有达到 64 倍扩展。大消息时，单核已经接近该访问模式下的共享吞吐上限，64 核读取只比单核高约 35%。64 KiB 写入的聚合带宽反而低于单核约 9%，符合争用与请求调度开销的表现；仅凭这组数据无法区分内存控制器、DMA 注入、互连、缓存一致性或特定地址映射各自的贡献。

![扩展比](scaling.png)

## 5. 128 B 边界及主存偏移

64 核、阻塞接口的对照：

{table(['模式','消息 B','对齐 B/cycle','偏移 4 B：B/cycle','偏移/对齐耗时','带宽下降'],align_rows)}

最值得建模的是写入的非线性边界：

- 对齐 64 B → 128 B：传输量加倍，最大 cycles/op 却从 {cy('put',64,0,64):.2f} 降到 {cy('put',64,0,128):.2f}，聚合带宽增加约 {bw('put',64,0,128)/bw('put',64,0,64):.2f} 倍。
- 128 B 写入、偏移 4 B：带宽下降约 {(1-bw('put',64,4,128)/bw('put',64,0,128))*100:.1f}%；iput 同样呈现约 12.67 倍耗时，两个接口表现吻合。
- 读取的偏移影响小得多：64 核 get 在 128 B 时耗时增加约 42.9%，带宽下降约 30.0%；4 KiB 及以上影响通常很小。
- 写入偏移影响随消息变大整体减弱，但并非严格单调；64 KiB put 的带宽仍下降约 6.5%。单核 put/iput 的小中消息偏移代价也很明显。

SACA 手册 PDF 第 59 页明确说明：DMA 主存访问会拆成 128 B 请求，不对界地址会拆出更多请求。这与本次读写的边界现象相符。额外分段可以解释一部分偏移代价，但 **仅靠多一个分段不能充分解释 128 B 写入约 12.7 倍耗时**。部分块写入的处理方式、共享资源争用等是后续待区分的机制；本次结果不能证明具体内部路径，也不能将手册中针对从核 cache 写回的读改写说明直接套到 DMA。

![地址偏移代价](alignment.png)

## 6. 阻塞与非阻塞接口

以下比值使用主存对齐的 14 种消息大小：

{table(['活跃核数','带宽比','14 个点的范围','14 个点的中位数'],async_rows)}

get/iget 差异基本在约 1% 内。单核 iput 相对 put 通常高约 1–2%，64 核两者仍很接近。由于每次 iget/iput 后立即等待，不能据此得出异步 DMA 没有价值；这组数据只说明 **单未完成请求、立即等待** 时接口本身的差别很小。各配置只有一次独立计时区间，不给这些微小差异赋予统计显著性。

## 7. 逐核差异

64 核、主存对齐的逐核平均 cycles/op：

{table(['模式','消息 B','最小','中位数','最大','核间变异系数'],pe_rows)}

小消息核间差异明显，例如 get 8 B 的最大值约为最小值的 1.89 倍。put 的 64 B 与 128 B 在核编号上都有重复的带状差异。get 4 KiB 时逐核耗时则十分接近，符合大消息受共同瓶颈约束的表现。

热图仅将编号按 `id=8r+c` 排列。每个格子是该核全部重复操作的平均值，不是逐次采样的延迟分位数；核间变异系数也不是测量误差或置信区间。地址按固定步长随编号变化，物理内存映射、请求调度和从核位置可能混在一起，**不能把这些 DMA 图当作 RMA 的 2×2 router 拓扑证据**。

![逐核耗时](per_cpe.png)

## 8. 可用于后续模拟器的初步参数

在主存 128 B 对齐条件下，对大消息区域拟合 `T(S)=alpha+beta*S`，T 单位为 cycles/op，S 单位为 B。单核选 1–64 KiB 的 7 个点，64 核选 4–64 KiB 的 5 个点；不混合两种活跃核数或两种偏移。64 核使用 summary 中的最大逐核完成耗时，斜率对应的聚合有效带宽为 `64/beta`。

{table(['模式','核数','拟合消息区间','alpha cycles','beta cycles/B','斜率对应聚合 B/cycle','R²'],fit_rows)}

这些拟合用于近似本次配置内的大消息趋势。读取单核的拟合截距约 490 cycles，略高于小消息平台约 441 cycles；64 核 iput 的截距接近零，是有限区间线性拟合的结果，不能解释成物理启动延迟为零。模型应分开保存小消息基线、对齐状态和负载条件，尤其不能用一个 alpha/beta 覆盖写入的 128 B 跃迁。

建议当前先保留三个要素：**单核小消息完成开销、1/64 核的大消息吞吐、128 B 对齐与部分块写入代价**。本次仅有 1/64 核两个负载端点，尚不足以确定吞吐随活跃核数变化的完整函数。

## 9. 数据的适用范围与后续测量

本次结果已能描述当前平台的 DMA 性能结构。用于论文或模拟器校准前，仍需补齐：

1. 每个配置的多次独立测量和运行顺序变化；目前循环重复次数较多，但不是多次独立实验，没有跨运行置信区间。`q_share` 队列名称本身不能证明独占或共享程度。
2. 64/96/124/128/132/192/252/256/260 B 的细粒度尺寸，以及 0/4/64/124 B 主存偏移，定位 128 B 写入边界。所有大小和偏移继续满足手册的 4 B 限制。
3. 活跃核数 1/2/4/8/16/32/64，确定共享吞吐何时饱和；改变主存槽步长或随机化槽与核的对应关系，区分位置与地址映射。
4. iget/iput 的独立缓冲流水化、多个未完成请求窗口，以及轮转主存工作集，分别测队列能力和更大的主存访问范围。
5. 保存实际 cache/LDM 配置、资源分配及计数器频率标定。若研究目标仍为 SW26010Pro，先确认当前机器型号与该目标的关系，再决定能否迁移参数。

以上是后续实验建议，本次分析未执行任何新的神威测试。
"""
    (out / "DMA分析报告.md").write_text(report, encoding="utf-8")
    print(json.dumps({"output_directory": str(out.resolve()),
                      "verified_sweep_cases": 224, "verified_smoke_cases": 8,
                      "verified_pe_rows": checks["per_pe_rows"],
                      "figure_count": 5}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    analyze(args.results, args.output)
