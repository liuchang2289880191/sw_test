# Structure alignment contract

Reference: outputs/dma_report_20261005/SW39000_DMA微基准分析报告_最终版.pdf.
This reference PDF remains unchanged. It has 7 pages and 7 primary sections.
The new report analyzes only dma_results_20261005_203552_32484 and must be self-contained.

Primary headings in reference order:
1. 实验配置与数据复核
2. DMA 带宽曲线
3. 并发扩展与共享吞吐
4. 主存对齐与 128 B 写入边界
5. 操作完成耗时与非阻塞接口
6. 逐核耗时与空间差异
7. 初步建模参数与后续实验

Extensions remain numbered subsections of those headings. Section 1 contains full matrix,
DMA terminology, completion semantics, timing, metrics, small-message baseline and layout.
Section 3 adds intermediate active-core loads; section 4 adds boundary fine scans;
section 5 adds phase overlap comparisons; section 6 adds mapping controls;
section 7 recalculates fits for the new data and separates completed and future experiments.
Page count may expand to accommodate complete current experiment conditions.

Reference typography and components: A4 portrait; margins top 1.8, bottom 1.7, left/right 1.8 cm;
Arial Latin, 宋体 body, 黑体 headings; black title 22 pt, primary heading 15 pt,
secondary heading 12 pt, body 10.5 pt with 1.16 line spacing, captions 9 pt.
Tables use #24445E headers with white text, #D9D9D9 borders and alternating light rows;
inline figures precede captions and supporting tables. Footer is centered page number.

Fidelity gate: exactly 7 primary headings in the sequence above; numerical content recalculated;
figures sequentially numbered 1–10; no requirement to read the reference report; render and
inspect every final page, with no clipped text, orphaned headings or broken tables.
