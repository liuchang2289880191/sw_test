# DMA benchmark results

Capacity per buffer: 65536 B.

Passed: 8 correctness cases and 224 sweep cases; all reported errors are zero.

Modes: get, put, iget, iput. Active PEs: 1, 64. Host offsets: 0, 4 B.

Each PE has one outstanding request. Eight warm-up transfers are excluded from timing.

Raw cases: raw/. Aggregate rows: summary.csv. Matched 64-PE/1-PE bandwidth ratios: scaling.csv.

Timings include the loop, API and completion waits. Repeated transfers reuse the same memory slots.

GB/s = bytes_per_cycle * actual_CPE_clock_GHz; frequency is not assumed.

Record actual cache/shared-LDM settings and resource sharing before comparing runs.
