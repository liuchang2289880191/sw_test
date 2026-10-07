# RMA 分析文件

主报告：`SW39000_RMA结果分析.md`。

- `figures/`：8 张大图，PNG 用于查看，SVG 用于排版和放大。
- `tables/`：原始文件核对记录、重复统计、逐核数据和模型结果。
- `analysis.json`：分析摘要。

保留本目录结构，主报告中的相对图片链接即可正常显示。所有图表依据 `rma_results_20261006_194029_17374` 的现有结果生成，未修改原始测量文件。

复现脚本位于项目的 `bench/analyze_rma_study.py`。在具备 pandas、numpy、matplotlib 的 Python 环境运行：

```powershell
python bench/analyze_rma_study.py rma_results_20261006_194029_17374 --out outputs/rma_analysis_20261006_194029_17374
```

脚本只读取测量文件并输出分析，不编译或提交硬件测试。
