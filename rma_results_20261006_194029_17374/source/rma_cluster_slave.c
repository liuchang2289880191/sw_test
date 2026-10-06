#include <slave.h>
#include "bench_common.h"

static __thread_local unsigned char source[BENCH_MAX_BYTES]
    __attribute__((aligned(128)));
static __thread_local unsigned char target[BENCH_MAX_BYTES]
    __attribute__((aligned(128)));
static __thread_local cluster_args_t cfg;
static __thread_local athread_rply_t send_reply;
static __thread_local athread_rply_t recv_reply;
static __thread_local unsigned long matrix_row[BENCH_PES];
static __thread_local int error_row[BENCH_PES];
static __thread_local int peer_error_row[BENCH_PES];
static __thread_local unsigned long flow_cycles;
static __thread_local int flow_errors;

static unsigned char pattern(int tid, int index)
{
    return (unsigned char)((tid * 17 + index * 13 + 7) & 255);
}

static void latency_matrix(void)
{
    int me = _PEN, a, b, i, j, rc;
    unsigned long begin;
    for (j = 0; j < cfg.bytes; ++j) source[j] = pattern(me, j);
    for (b = 0; b < BENCH_PES; ++b) {
        matrix_row[b] = 0;
        error_row[b] = 0;
        peer_error_row[b] = 0;
    }
    athread_ssync_array();
    for (a = 0; a < BENCH_PES; ++a) {
        for (b = 0; b < BENCH_PES; ++b) {
            if (a == b) continue;
            send_reply = 0;
            recv_reply = 0;
            if (me == a || me == b)
                for (j = 0; j < cfg.bytes; ++j) target[j] = 0;
            athread_ssync_array();
            /* Four ping-pongs warm up both directions; no barrier in timing. */
            for (i = 0; i < cfg.reps + 4; ++i) {
                if (i == 4 && me == a) begin = athread_stime_cycle();
                if (me == a) {
                    rc = athread_rma_iput(source, &send_reply, cfg.bytes,
                                          b, target, &recv_reply);
                    if (rc) ++error_row[b];
                    athread_rma_wait_value(&send_reply, i + 1);
                    athread_rma_wait_value(&recv_reply, i + 1);
                } else if (me == b) {
                    athread_rma_wait_value(&recv_reply, i + 1);
                    rc = athread_rma_iput(source, &send_reply, cfg.bytes,
                                          a, target, &recv_reply);
                    if (rc) ++peer_error_row[a];
                    athread_rma_wait_value(&send_reply, i + 1);
                }
            }
            if (me == a) matrix_row[b] = athread_stime_cycle() - begin;
            athread_ssync_array();
            if (me == a || me == b) {
                int expected = me == a ? b : a;
                for (j = 0; j < cfg.bytes; ++j)
                    if (target[j] != pattern(expected, j)) {
                        if (me == a) ++error_row[b];
                        else ++peer_error_row[a];
                        break;
                    }
            }
            athread_ssync_array();
        }
    }
    athread_dma_put(cfg.cycles + me * BENCH_PES,
                    matrix_row, sizeof(matrix_row));
    athread_dma_put(cfg.errors + me * BENCH_PES,
                    error_row, sizeof(error_row));
    athread_dma_put(cfg.peer_errors + me * BENCH_PES,
                    peer_error_row, sizeof(peer_error_row));
}

static void flow_bandwidth(void)
{
    int me = _PEN, f, j, round, sent = 0, incoming = 0, outgoing = 0;
    int first, count, rc;
    unsigned long begin;

    for (j = 0; j < cfg.window * cfg.bytes; ++j)
        source[j] = pattern(me, j);
    for (j = 0; j < BENCH_MAX_BYTES; ++j) target[j] = 0;
    for (f = 0; f < cfg.nflows; ++f) {
        if (cfg.flows[f].src == me) ++outgoing;
        if (cfg.flows[f].dst == me) ++incoming;
    }
    send_reply = 0;
    recv_reply = 0;
    flow_cycles = 0;
    flow_errors = 0;
    athread_ssync_array();
    if (outgoing) {
        for (f = 0; f < cfg.nflows; ++f) {
            if (cfg.flows[f].src != me) continue;
            rc = athread_rma_iput(source, &send_reply, cfg.bytes,
                                  cfg.flows[f].dst,
                                  target + cfg.flows[f].lane * cfg.window * cfg.bytes,
                                  &recv_reply);
            if (rc) ++flow_errors;
        }
        athread_rma_wait_value(&send_reply, outgoing);
    }
    if (incoming) athread_rma_wait_value(&recv_reply, incoming);
    athread_ssync_array();
    send_reply = 0;
    recv_reply = 0;
    athread_ssync_array();
    begin = athread_stime_cycle();
    if (outgoing) for (first = 0; first < cfg.reps; first += cfg.window) {
        count = cfg.reps - first;
        if (count > cfg.window) count = cfg.window;
        for (round = 0; round < count; ++round) {
            int slot = round * cfg.bytes;
            for (f = 0; f < cfg.nflows; ++f) {
                if (cfg.flows[f].src != me) continue;
                rc = athread_rma_iput(source + slot, &send_reply,
                                      cfg.bytes, cfg.flows[f].dst,
                                      target + (cfg.flows[f].lane * cfg.window + round)
                                               * cfg.bytes,
                                      &recv_reply);
                if (rc) ++flow_errors;
                ++sent;
            }
        }
        athread_rma_wait_value(&send_reply, sent);
    }
    if (incoming)
        athread_rma_wait_value(&recv_reply, cfg.reps * incoming);
    if (incoming || outgoing) flow_cycles = athread_stime_cycle() - begin;
    athread_ssync_array();

    if (incoming) {
        int last_count = cfg.reps % cfg.window;
        if (last_count == 0) last_count = cfg.window;
        for (f = 0; f < cfg.nflows; ++f) {
            if (cfg.flows[f].dst != me) continue;
            for (round = 0; round < last_count; ++round) {
                int slot = (cfg.flows[f].lane * cfg.window + round) * cfg.bytes;
                for (j = 0; j < cfg.bytes; ++j)
                    if (target[slot + j] != pattern(cfg.flows[f].src,
                                                     round * cfg.bytes + j)) {
                        ++flow_errors;
                        break;
                    }
            }
        }
    }
    athread_dma_put(cfg.cycles + me, &flow_cycles, sizeof(flow_cycles));
    athread_dma_put(cfg.errors + me, &flow_errors, sizeof(flow_errors));
}

void cluster_kernel(cluster_args_t *host_arg)
{
    athread_dma_get(&cfg, host_arg, sizeof(cfg));
    if (cfg.mode == 0) latency_matrix();
    else flow_bandwidth();
}
