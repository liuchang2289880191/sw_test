#ifndef PMU_COMMON_H
#define PMU_COMMON_H
#define PMU_PES 64
#define PMU_BYTES 4096
typedef struct {
    unsigned long cycles, local_done, remote_done, source_addr, stack_addr;
    int pe, errors;
} pmu_result;
typedef struct {
    int src, dst, bytes, iterations, local_only;
    pmu_result *results;
} pmu_args;
#endif
