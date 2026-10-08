#ifndef PMU_COMMON_H
#define PMU_COMMON_H
#define PMU_PES 64
#define PMU_BYTES 4096
typedef struct {
    unsigned long cycles, local_done, remote_done, source_addr, stack_addr;
    int pe, errors;
} rma_pmu_probe_result_t;
typedef struct {
    int src, dst, bytes, iterations, local_only;
    rma_pmu_probe_result_t *results;
} rma_pmu_probe_args_t;
#endif
