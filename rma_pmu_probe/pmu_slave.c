#include <slave.h>
#include <string.h>
#include <stdint.h>
#include "pmu_common.h"
static __thread_local struct {
    unsigned char source[PMU_BYTES] __attribute__((aligned(128)));
    volatile unsigned char target[PMU_BYTES] __attribute__((aligned(128)));
    pmu_args cfg;
    pmu_result result;
    athread_rply_t local_reply, remote_reply;
} state __attribute__((aligned(128)));

static void fence(void) { __asm__ __volatile__("memb" ::: "memory"); }
static int wait_for(athread_rply_t *p, unsigned long n)
{
    unsigned long start = athread_stime_cycle(), spins = 0;
    while ((unsigned long)*p < n) {
        if (!(++spins & 1023UL) && athread_stime_cycle() - start > 1000000000UL)
            return 0;
    }
    fence();
    return 1;
}
static unsigned char pattern(int src, int j)
{
    unsigned int x = (unsigned int)(src + 1) * 0x9e3779b9U + (unsigned int)j;
    x ^= x >> 16; x *= 0x7feb352dU; x ^= x >> 15;
    return (unsigned char)(x ^ (x >> 8) ^ (x >> 24));
}
void pmu_kernel(pmu_args *host)
{
    int me = _PEN, i, j;
    unsigned long start;
    athread_dma_get(&state.cfg, host, sizeof(state.cfg));
    memset(&state.result, 0, sizeof(state.result));
    state.result.pe = me;
    state.result.source_addr = (unsigned long)(uintptr_t)state.source;
    state.result.stack_addr = (unsigned long)(uintptr_t)&j;
    state.local_reply = state.remote_reply = 0;
    for (j = 0; j < state.cfg.bytes; ++j) {
        state.source[j] = pattern(me, j);
        state.target[j] = 0;
    }
    athread_ssync_array();
    start = athread_stime_cycle();
    if (me == state.cfg.src) {
        for (i = 0; i < state.cfg.iterations; ++i) {
            if (state.cfg.local_only) {
                /* A real volatile local operation; not an exact cost-matched RMA surrogate. */
                for (j = 0; j < state.cfg.bytes; ++j) state.target[j] = state.source[j];
                fence();
            } else {
                int rc = athread_rma_iput(state.source, &state.local_reply,
                    state.cfg.bytes, state.cfg.dst, (void *)state.target, &state.remote_reply);
                if (rc || !wait_for(&state.local_reply, (unsigned long)i + 1)) {
                    ++state.result.errors; break;
                }
            }
        }
    } else if (me == state.cfg.dst && !state.cfg.local_only) {
        if (!wait_for(&state.remote_reply, state.cfg.iterations)) ++state.result.errors;
    }
    state.result.cycles = athread_stime_cycle() - start;
    /* Drain both endpoints before validation or host DMA. No application reply per PUT. */
    athread_ssync_array();
    state.result.local_done = (unsigned long)state.local_reply;
    state.result.remote_done = (unsigned long)state.remote_reply;
    if (state.cfg.iterations &&
        (me == (state.cfg.local_only ? state.cfg.src : state.cfg.dst))) {
        for (j = 0; j < state.cfg.bytes; ++j)
            if (state.target[j] != pattern(state.cfg.src, j)) { ++state.result.errors; break; }
    }
    athread_ssync_array();
    athread_dma_put(state.cfg.results + me, &state.result, sizeof(state.result));
}
