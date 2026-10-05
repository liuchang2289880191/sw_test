#include <slave.h>
#include "bench_common.h"

static __thread_local unsigned char source[BENCH_MAX_BYTES]
    __attribute__((aligned(128)));
static __thread_local unsigned char target[BENCH_MAX_BYTES]
    __attribute__((aligned(128)));
static __thread_local bcast_args_t ldm_args;
static __thread_local unsigned long ldm_elapsed;
static __thread_local int ldm_error;

static int broadcast(const bcast_args_t *a)
{
    if (a->scope == 0)
        return athread_rma_row_bcast_coll(target, source, a->bytes, a->root);
    if (a->scope == 1)
        return athread_rma_col_bcast_coll(target, source, a->bytes, a->root);
    return athread_rma_bcast_coll(target, source, a->bytes, a->root);
}

void bcast_kernel(bcast_args_t *host_arg)
{
    bcast_args_t *a = &ldm_args;
    unsigned long begin;
    int me = _PEN, expected, i, j, err = 0;
    athread_dma_get(a, host_arg, sizeof(*a));
    for (j = 0; j < a->bytes; ++j)
        source[j] = (unsigned char)((me * 17 + j * 13 + 7) & 255);
    athread_ssync_array();
    for (i = 0; i < 4; ++i) if (broadcast(a)) ++err;
    athread_ssync_array();
    begin = athread_stime_cycle();
    for (i = 0; i < a->reps; ++i) if (broadcast(a)) ++err;
    ldm_elapsed = athread_stime_cycle() - begin;
    athread_ssync_array();
    expected = a->scope == 0 ? (me / 8) * 8 + a->root :
               a->scope == 1 ? a->root * 8 + me % 8 : a->root;
    for (j = 0; j < a->bytes; ++j)
        if (target[j] != (unsigned char)((expected * 17 + j * 13 + 7) & 255)) {
            ++err;
            break;
        }
    ldm_error = err;
    athread_dma_put(a->cycles + me, &ldm_elapsed, sizeof(ldm_elapsed));
    athread_dma_put(a->errors + me, &ldm_error, sizeof(ldm_error));
}
