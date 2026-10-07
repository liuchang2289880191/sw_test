#include <slave.h>
#include <string.h>
#include "topology_common.h"

typedef struct {
    unsigned char source[TOPO_BUFFER_BYTES] __attribute__((aligned(128)));
    unsigned char target[TOPO_BUFFER_BYTES] __attribute__((aligned(128)));
    topo_args_t cfg;
    topo_result_t result;
    unsigned long samples[TOPO_MAX_SAMPLES];
    athread_rply_t local_reply, remote_reply[TOPO_MAX_FLOWS];
    athread_rply_t control_local, ready_reply, stop_reply;
    athread_rply_t meta_reply[TOPO_MAX_FLOWS];
    unsigned long totals[TOPO_MAX_FLOWS], total_value;
    unsigned int ready_marks[TOPO_PES];
    volatile unsigned int stop_flag;
    unsigned int control_value;
} topo_local_t;
/* One LDM object also gives the local protocol emulator a stable address map. */
static __thread_local topo_local_t local __attribute__((aligned(128)));
#define source local.source
#define target local.target
#define cfg local.cfg
#define result local.result
#define sample_buffer local.samples
#define local_reply local.local_reply
#define remote_reply local.remote_reply
#define control_local local.control_local
#define ready_reply local.ready_reply
#define stop_reply local.stop_reply
#define meta_reply local.meta_reply
#define totals local.totals
#define total_value local.total_value
#define ready_marks local.ready_marks
#define stop_flag local.stop_flag
#define control_value local.control_value

static unsigned char pattern(int src, int offset)
{
    unsigned int x = (unsigned int)(src + 1) * 0x9e3779b9U + (unsigned int)offset;
    x ^= x >> 16; x *= 0x7feb352dU; x ^= x >> 15;
    return (unsigned char)(x ^ (x >> 8) ^ (x >> 24));
}

static void tag(unsigned char *p, unsigned int seq, int src)
{
    unsigned int magic = seq ^ ((unsigned int)src * 65537U) ^ 0x6b79ac13U;
    memcpy(p, &seq, 4); memcpy(p + 4, &magic, 4);
}

static int check_tag(const unsigned char *p, unsigned int seq, int src)
{
    unsigned int got, magic;
    memcpy(&got, p, 4); memcpy(&magic, p + 4, 4);
    return got != seq || magic != (seq ^ ((unsigned int)src * 65537U) ^ 0x6b79ac13U);
}

static void check_payload(const unsigned char *p, int bytes, unsigned int seq,
                          int src, int source_offset)
{
    int j;
    if (check_tag(p, seq, src)) ++result.errors;
    for (j = 8; j < bytes; ++j) if (p[j] != pattern(src, source_offset + j)) {
        ++result.errors; break;
    }
}

static void put(const void *src, int bytes, int dst, void *dest,
                athread_rply_t *lr, athread_rply_t *rr)
{
    if (athread_rma_iput((void *)src, lr, bytes, dst, dest, rr)) ++result.errors;
}

/* All outflows of one PE share read-only source slots for the same sequence.
 * A slot is tagged again only after cumulative local completion of the batch.
 * Every destination incoming flow has a separate lane and remote reply word. */
static unsigned long batch(int me, int first_flow, unsigned long first, int count,
                           unsigned long issued)
{
    int slot, f;
    for (slot = 0; slot < count; ++slot) {
        tag(source + slot * cfg.bytes, (unsigned int)(first + slot), me);
        for (f = first_flow; f < cfg.nflows; ++f) if (cfg.flows[f].src == me) {
            put(source + slot * cfg.bytes, cfg.bytes, cfg.flows[f].dst,
                target + (cfg.flows[f].lane * cfg.window + slot) * cfg.bytes,
                &local_reply, &remote_reply[f]);
            ++issued;
        }
    }
    athread_rma_wait_value(&local_reply, issued);
    return issued;
}

static void receive_bulk(int me, int first_flow, unsigned long begin)
{
    int f, slot;
    for (f = first_flow; f < cfg.nflows; ++f) if (cfg.flows[f].dst == me) {
        unsigned long n;
        if (cfg.mode) {
            athread_rma_wait_value(&meta_reply[f], 1);
            n = totals[f];
        } else n = (unsigned long)cfg.reps;
        athread_rma_wait_value(&remote_reply[f], n);
        result.received += n;
    }
    if (result.received) result.recv_cycles = athread_stime_cycle() - begin;
    /* Validate after EVERY incoming flow has drained, outside measured time. */
    for (f = first_flow; f < cfg.nflows; ++f) if (cfg.flows[f].dst == me) {
        unsigned long n = cfg.mode ? totals[f] : (unsigned long)cfg.reps;
        for (slot = 0; slot < cfg.window && (unsigned long)slot < n; ++slot) {
            unsigned long last = n - 1 - ((n - 1 - (unsigned long)slot) % cfg.window);
            check_payload(target + (cfg.flows[f].lane * cfg.window + slot) * cfg.bytes,
                          cfg.bytes, (unsigned int)last, cfg.flows[f].src,
                          slot * cfg.bytes);
        }
    }
}

static void bulk(int me, unsigned long begin)
{
    unsigned long first, issued = 0;
    int f, outgoing = 0;
    for (f = 0; f < cfg.nflows; ++f) if (cfg.flows[f].src == me) ++outgoing;
    if (outgoing) {
        for (first = 0; first < (unsigned long)cfg.reps; first += cfg.window) {
            int count = cfg.reps - (int)first;
            if (count > cfg.window) count = cfg.window;
            issued = batch(me, 0, first, count, issued);
        }
        result.sent = issued;
        result.send_cycles = athread_stime_cycle() - begin;
    }
    receive_bulk(me, 0, begin);
    result.cycles = result.send_cycles > result.recv_cycles ? result.send_cycles : result.recv_cycles;
}

static void background(int me, unsigned long begin)
{
    unsigned long rounds = 0, issued = 0, control_count = 0;
    int f, outgoing = 0;
    for (f = 1; f < cfg.nflows; ++f) if (cfg.flows[f].src == me) ++outgoing;
    if (outgoing) {
        /* Mark readiness only after a nonempty traffic batch has completed locally.
         * Keep issuing until the probe initiator sends a stop flag AFTER timing. */
        issued = batch(me, 1, rounds, cfg.window, issued);
        rounds += cfg.window;
        control_value = 1;
        put(&control_value, 4, cfg.flows[0].src, &ready_marks[me],
            &control_local, &ready_reply);
        athread_rma_wait_value(&control_local, ++control_count);
        while (!stop_flag && rounds < (unsigned long)cfg.background_limit) {
            int count = cfg.window;
            if (rounds + count > (unsigned long)cfg.background_limit)
                count = cfg.background_limit - (int)rounds;
            issued = batch(me, 1, rounds, count, issued);
            rounds += count;
        }
        if (!stop_flag) result.background_limit_hit = 1;
        result.sent = issued;
        result.send_cycles = athread_stime_cycle() - begin;
        /* Each receiver gets the exact completed count, then drains its replies.
         * Metadata and stop traffic are outside probe timing. */
        total_value = rounds;
        for (f = 1; f < cfg.nflows; ++f) if (cfg.flows[f].src == me) {
            put(&total_value, sizeof(total_value), cfg.flows[f].dst, &totals[f],
                &control_local, &meta_reply[f]);
            athread_rma_wait_value(&control_local, ++control_count);
        }
    }
    receive_bulk(me, 1, begin);
    result.cycles = result.send_cycles > result.recv_cycles ? result.send_cycles : result.recv_cycles;
}

static void probe(int me)
{
    int i, f, src = cfg.flows[0].src, dst = cfg.flows[0].dst;
    int bg_sources = 0, seen[TOPO_PES] = {0};
    unsigned long begin = 0, sample_begin = 0;
    for (f = 1; f < cfg.nflows; ++f) if (!seen[cfg.flows[f].src]++) ++bg_sources;
    if (me == src) {
        if (bg_sources) athread_rma_wait_value(&ready_reply, bg_sources);
        for (i = 0; i < cfg.reps + 4; ++i) {
            unsigned long end;
            if (i == 4) begin = athread_stime_cycle();
            if (i >= 4 && (i - 4) % TOPO_SAMPLE_BATCH == 0)
                sample_begin = athread_stime_cycle();
            tag(source, (unsigned int)i, me);
            put(source, cfg.probe_bytes, dst, target, &local_reply, &remote_reply[0]);
            athread_rma_wait_value(&local_reply, i + 1);
            athread_rma_wait_value(&remote_reply[0], i + 1);
            if (check_tag(target, (unsigned int)i, dst)) ++result.errors;
            if (i >= 4 && (i - 3) % TOPO_SAMPLE_BATCH == 0) {
                end = athread_stime_cycle();
                sample_buffer[(i - 4) / TOPO_SAMPLE_BATCH] = end - sample_begin;
            }
        }
        result.cycles = athread_stime_cycle() - begin;
        result.send_cycles = result.cycles;
        result.sent = result.received = cfg.reps;
        check_payload(target, cfg.reply_bytes, (unsigned int)(cfg.reps + 3), dst, 0);
        memset(seen, 0, sizeof(seen));
        control_value = 1;
        for (f = 1; f < cfg.nflows; ++f) if (!seen[cfg.flows[f].src]++)
            put(&control_value, 4, cfg.flows[f].src, (void *)&stop_flag,
                &control_local, &stop_reply);
        if (bg_sources) athread_rma_wait_value(&control_local, bg_sources);
    } else {
        for (i = 0; i < cfg.reps + 4; ++i) {
            if (i == 4) begin = athread_stime_cycle();
            athread_rma_wait_value(&remote_reply[0], i + 1);
            if (check_tag(target, (unsigned int)i, src)) ++result.errors;
            tag(source, (unsigned int)i, me);
            put(source, cfg.reply_bytes, src, target, &local_reply, &remote_reply[0]);
            athread_rma_wait_value(&local_reply, i + 1);
        }
        result.cycles = athread_stime_cycle() - begin;
        result.received = result.sent = cfg.reps;
        check_payload(target, cfg.probe_bytes, (unsigned int)(cfg.reps + 3), src, 0);
    }
}

void topology_kernel(topo_args_t *host_arg)
{
    int me = _PEN, f, j, active = 0;
    unsigned long begin;
    athread_dma_get(&cfg, host_arg, sizeof(cfg));
    memset(&result, 0, sizeof(result)); memset(sample_buffer, 0, sizeof(sample_buffer));
    memset(remote_reply, 0, sizeof(remote_reply)); memset(meta_reply, 0, sizeof(meta_reply));
    memset(totals, 0, sizeof(totals)); memset(target, 0, sizeof(target));
    local_reply = control_local = ready_reply = stop_reply = 0;
    memset(ready_marks, 0, sizeof(ready_marks));
    stop_flag = 0; control_value = 0;
    for (j = 0; j < TOPO_BUFFER_BYTES; ++j) source[j] = pattern(me, j);
    for (f = 0; f < cfg.nflows; ++f)
        if (cfg.flows[f].src == me || cfg.flows[f].dst == me) active = 1;
    athread_ssync_array();
    if (!cfg.mode) {
        int outgoing = 0, count = cfg.reps < cfg.window ? cfg.reps : cfg.window;
        for (f = 0; f < cfg.nflows; ++f) if (cfg.flows[f].src == me) ++outgoing;
        if (outgoing) batch(me, 0, 0, count, 0);
        for (f = 0; f < cfg.nflows; ++f) if (cfg.flows[f].dst == me)
            athread_rma_wait_value(&remote_reply[f], count);
    }
    athread_ssync_array();
    local_reply = 0; memset(remote_reply, 0, sizeof(remote_reply));
    athread_ssync_array();
    begin = athread_stime_cycle();
    if (active) {
        if (!cfg.mode) bulk(me, begin);
        else if (me == cfg.flows[0].src || me == cfg.flows[0].dst) probe(me);
        else background(me, begin);
    }
    /* All timing ends before this barrier, validation was already performed.
     * No DMA or host work runs concurrently with any measured traffic. */
    athread_ssync_array();
    athread_dma_put(cfg.results + me, &result, sizeof(result));
    if (cfg.mode && me == cfg.flows[0].src)
        athread_dma_put(cfg.samples, sample_buffer, cfg.reps / TOPO_SAMPLE_BATCH * sizeof(sample_buffer[0]));
}
