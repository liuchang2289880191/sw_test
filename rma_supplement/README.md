# 独立 RMA 补充实验

阅读 [DESIGN.md](DESIGN.md) 获取完整实验设计、控制变量和判读规则。

不改旧实验。四组：完成口径 E0、CPE/簇级端点共享 E1、方向共享 E2、持续背景下的路由探针 E3。

2026-10-07 修订：目标二进制仅由 bsub 在计算节点启动；登录节点不执行 `--validate-plan`。回答字按目标 SDK 的 volatile 类型逐项清零，消除初始化警告。旧版在登录节点的「无法执行二进制文件」发生于提交前，不是 CPE 诊断运行失败。

同日针对第 6 项 `diag_05` 长时间未返回，补充了阶段日志、带上限的回答字等待和主核单项 60 秒超时。ready 改为每个背景源一个独立回答字，8 B 控制消息；stop 按远端完成回答字判断；最终次数按实际成功发起的请求分别记录，并在完成后读取 volatile 元数据。现有服务器日志没有阶段信息，尚不能确定该次卡住的具体位置，也不能用本地模拟通过声称真实硬件问题已解决。

```bash
cd rma_supplement
TOPO_DIAG_ONLY=1 TOPO_TRACE=1 bash run_supplement.sh q_share
bash run_supplement.sh q_share
```

第一条为 6 项接口/正确性诊断；第二条默认 5 个独立作业，每作业 234 项，2048 次/项。登录节点需要 Python 3、swgcc 和 bsub。计算节点只执行新原生二进制。

更新时必须同时覆盖 `topology_common.h`、`topology_host.c`、`topology_slave.c` 和 `run_supplement.sh`；主从核共用结构体已经改变，不能只更新从核文件。诊断正常时应出现 `TOPO_RETURN diag_05` 和最终完成路径；有 `TOPO_TIMEOUT` / `TOPO_CASE_TIMEOUT` 时保留 `repeat_01/job.log`，不继续正式扫描。具体阶段编号见 [DESIGN.md](DESIGN.md#卡住时的诊断)。

`TOPO_WAIT_TIMEOUT_CYCLES` 默认 1,000,000,000 cycles；没有标定频率，不能直接换算秒。`TOPO_CASE_TIMEOUT_SECONDS` 默认 60 秒，可设 1–3600。性能运行默认关闭 `TOPO_TRACE`；诊断日志会扰动背景流，诊断数据不用于性能结论。

完整扫描为 13,234 项/作业，放在 `plans/full/` 供审核，不建议在快速组之前直接提交。实际运行会重新生成种子不同、按组打乱的计划。

本地验证记录见 [LOCAL_VERIFICATION.json](LOCAL_VERIFICATION.json)。它运行新的 CPE 内核及控制握手的线程模拟，时间不是申威数据；尚未在真正申威机器编译/执行。

所有新结果写入新建 `results_时间_进程号/`。`analysis/route_effects.csv` 中比值大于 1 表示探针 RTT 变长；不会自动把 XY/YX 假设称为真实路由。
