#include <slave.h>
#include "bench_common.h"

static __thread_local unsigned char rma_src[BENCH_MAX_BYTES]
    __attribute__((aligned(128)));
static __thread_local unsigned char rma_dst[BENCH_MAX_BYTES]
    __attribute__((aligned(128)));
static __thread_local athread_rply_t local_reply;
static __thread_local athread_rply_t remote_reply;
static __thread_local rma_args_t ldm_args;
static __thread_local unsigned long row_cycles[BENCH_PES];
static __thread_local int row_errors[BENCH_PES];
static __thread_local int row_receiver_errors[BENCH_PES];

static unsigned char pattern(int tid, int index)
{
    return (unsigned char)((tid * 17 + index * 13 + 7) & 255);
}

void rma_kernel(rma_args_t *host_arg)
{
    rma_args_t *a = &ldm_args;
    int me = _PEN, initiator, peer, i, j, rc, err;
    unsigned long begin, end;

    athread_dma_get(a, host_arg, sizeof(*a));
    for (j = 0; j < a->bytes; ++j) rma_src[j] = pattern(me, j);
    for (peer = 0; peer < BENCH_PES; ++peer) {
        row_cycles[peer] = 0;
        row_errors[peer] = 0;
        row_receiver_errors[peer] = 0;
    }
    athread_ssync_array();

    for (initiator = 0; initiator < BENCH_PES; ++initiator) {
        for (peer = 0; peer < BENCH_PES; ++peer) {
            if (initiator == peer) continue; /* self-transfer is not a network hop */
            local_reply = 0;
            remote_reply = 0;
            if (me == initiator || me == peer)
                for (j = 0; j < a->bytes; ++j) rma_dst[j] = 0;
            /* Reply reset must precede the first remote increment. */
            athread_ssync_array();

            if (me == initiator) {
                /* Four completed operations warm up the route. */
                for (i = 0; i < 4; ++i) {
                    if (a->op == 0)
                        rc = athread_rma_iput(rma_src, &local_reply, a->bytes,
                                              peer, rma_dst, &remote_reply);
                    else
                        rc = athread_rma_iget(rma_dst, &local_reply, a->bytes,
                                              peer, rma_src, &remote_reply);
                    if (rc) ++row_errors[peer];
                    athread_rma_wait_value(&local_reply, i + 1);
                }
                begin = athread_stime_cycle();
                for (i = 0; i < a->reps; ++i) {
                    if (a->op == 0)
                        rc = athread_rma_iput(rma_src, &local_reply, a->bytes,
                                              peer, rma_dst, &remote_reply);
                    else
                        rc = athread_rma_iget(rma_dst, &local_reply, a->bytes,
                                              peer, rma_src, &remote_reply);
                    if (rc) ++row_errors[peer];
                    athread_rma_wait_value(&local_reply, i + 5);
                }
                end = athread_stime_cycle();
                row_cycles[peer] = end - begin;
            }
            if (me == peer)
                athread_rma_wait_value(&remote_reply, a->reps + 4);
            athread_ssync_array();
            if (a->op == 0 && me == peer) {
                err = 0;
                for (j = 0; j < a->bytes; ++j)
                    if (rma_dst[j] != pattern(initiator, j)) { err = 1; break; }
                row_receiver_errors[initiator] += err;
            }
            if (a->op == 1 && me == initiator) {
                for (j = 0; j < a->bytes; ++j)
                    if (rma_dst[j] != pattern(peer, j)) {
                        ++row_errors[peer];
                        break;
                    }
            }
            athread_ssync_array();
        }
    }
    athread_dma_put(a->cycles + me * BENCH_PES, row_cycles,
                    sizeof(row_cycles));
    athread_dma_put(a->errors + me * BENCH_PES, row_errors,
                    sizeof(row_errors));
    athread_dma_put(a->receiver_errors + me * BENCH_PES,
                    row_receiver_errors, sizeof(row_receiver_errors));
}
