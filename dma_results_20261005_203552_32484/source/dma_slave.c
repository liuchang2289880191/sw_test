#include <slave.h>
#include "bench_common.h"

static __thread_local unsigned char ldm_buf[DMA_MAX_BYTES]
    __attribute__((aligned(128)));
static __thread_local dma_args_t ldm_args;
static __thread_local athread_rply_t ldm_reply;
static __thread_local unsigned long ldm_elapsed;
static __thread_local int ldm_error;

void dma_kernel(dma_args_t *host_arg)
{
    dma_args_t *a = &ldm_args;
    unsigned char *src;
    unsigned char *dst;
    unsigned long begin, end;
    int err = 0, i, j, rc;
    int tid = _PEN;

    athread_dma_get(a, host_arg, sizeof(*a));
    ldm_elapsed = 0;
    src = (unsigned char *)a->src + a->slot_of_pe[tid] * a->slot_stride + a->offset;
    dst = (unsigned char *)a->dst + a->slot_of_pe[tid] * a->slot_stride + a->offset;

    if (a->mode == 1 || a->mode == 3) {
        for (j = 0; j < a->bytes; ++j)
            ldm_buf[j] = (unsigned char)((tid * 17 + j * 13 + 7) & 255);
    }
    athread_ssync_array();
    if (tid < a->active) {
        /* Untimed warm-up. */
        for (i = 0; i < 8; ++i) {
            if (a->mode == 0) athread_dma_get(ldm_buf, src, a->bytes);
            if (a->mode == 1) athread_dma_put(dst, ldm_buf, a->bytes);
            if (a->mode == 2) {
                ldm_reply = 0;
                athread_dma_iget(ldm_buf, src, a->bytes, &ldm_reply);
                athread_dma_wait_value(&ldm_reply, 1);
            }
            if (a->mode == 3) {
                ldm_reply = 0;
                athread_dma_iput(dst, ldm_buf, a->bytes, &ldm_reply);
                athread_dma_wait_value(&ldm_reply, 1);
            }
        }
    }
    athread_ssync_array();
    if (tid < a->active) {
        begin = athread_stime_cycle();
        for (i = 0; i < a->reps; ++i) {
            rc = 0;
            if (a->mode == 0) rc = athread_dma_get(ldm_buf, src, a->bytes);
            if (a->mode == 1) rc = athread_dma_put(dst, ldm_buf, a->bytes);
            if (a->mode == 2) {
                ldm_reply = 0;
                rc = athread_dma_iget(ldm_buf, src, a->bytes, &ldm_reply);
                athread_dma_wait_value(&ldm_reply, 1);
            }
            if (a->mode == 3) {
                ldm_reply = 0;
                rc = athread_dma_iput(dst, ldm_buf, a->bytes, &ldm_reply);
                athread_dma_wait_value(&ldm_reply, 1);
            }
            if (rc != 0) ++err;
        }
        end = athread_stime_cycle();
        ldm_elapsed = end - begin;
        if (a->mode == 0 || a->mode == 2) {
            for (j = 0; j < a->bytes; ++j)
                if (ldm_buf[j] != (unsigned char)((tid * 17 + j * 13 + 7) & 255)) {
                    ++err;
                    break;
                }
        }
    }
    /* Every PE writes a distinct host slot; DMA makes results visible to the host. */
    ldm_error = err;
    athread_dma_put(a->cycles + tid, &ldm_elapsed, sizeof(ldm_elapsed));
    athread_dma_put(a->errors + tid, &ldm_error, sizeof(ldm_error));
}
