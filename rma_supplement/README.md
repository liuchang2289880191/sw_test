# 独立 RMA 补充实验

阅读 [DESIGN.md](DESIGN.md) 获取完整实验设计、控制变量和判读规则。

不改旧实验。四组：完成口径 E0、CPE/簇级端点共享 E1、方向共享 E2、持续背景下的路由探针 E3。

```bash
cd rma_supplement
TOPO_DIAG_ONLY=1 bash run_supplement.sh q_share
bash run_supplement.sh q_share
```

第一条为 6 项接口/正确性诊断；第二条默认 5 个独立作业，每作业 234 项，2048 次/项。登录节点需要 Python 3、swgcc 和 bsub。计算节点只执行新原生二进制。

完整扫描为 13,234 项/作业，放在 `plans/full/` 供审核，不建议在快速组之前直接提交。实际运行会重新生成种子不同、按组打乱的计划。

本地验证记录见 [LOCAL_VERIFICATION.json](LOCAL_VERIFICATION.json)。它运行新的 CPE 内核及控制握手的线程模拟，时间不是申威数据；尚未在真正申威机器编译/执行。

所有新结果写入新建 `results_时间_进程号/`。`analysis/route_effects.csv` 中比值大于 1 表示探针 RTT 变长；不会自动把 XY/YX 假设称为真实路由。
