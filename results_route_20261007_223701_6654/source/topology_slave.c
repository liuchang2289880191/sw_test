#include <slave.h>
#include <string.h>
#include <stdio.h>
#include "topology_common.h"

typedef struct {
    unsigned char source[TOPO_BUFFER_BYTES] __attribute__((aligned(128)));
    unsigned char target[TOPO_BUFFER_BYTES] __attribute__((aligned(128)));
    topo_args_t cfg;
    topo_result_t result;
    unsigned long samples[TOPO_MAX_SAMPLES];
    athread_rply_t local_reply, remote_reply[TOPO_MAX_FLOWS];
    athread_rply_t control_local, ready_reply[TOPO_PES], stop_reply;
    athread_rply_t meta_reply[TOPO_MAX_FLOWS];
    volatile unsigned long totals[TOPO_MAX_FLOWS];
    unsigned long sent_totals[TOPO_MAX_FLOWS], total_value;
    unsigned long long ready_marks[TOPO_PES], control_value, stop_word;
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
#define sent_totals local.sent_totals
#define ready_marks local.ready_marks
#define stop_word local.stop_word
#define control_value local.control_value

/* Stage codes are saved on failure: 1=data local, 2=ready local,
 * 3=probe ready, 4=probe data local, 5=probe receive, 6=stop local,
 * 7=metadata local, 8=metadata receive, 9=data drain, 10=stop receive,
 * 11=RMA API failure. No missing reply can trap a PE in an unbounded wait. */
static void fence(void)
{
#ifdef TOPO_LOCAL_EMULATION
    athread_memory_barrier();
#else
    __asm__ __volatile__("memb" ::: "memory");
#endif
}

static void trace(const char *step, unsigned long count)
{
    if (cfg.trace) {
        printf("TOPO_STAGE pe=%d step=%s count=%lu\n", _PEN, step, count);
        fflush(stdout);
    }
}

static void timeout_record(int stage, unsigned long expected, unsigned long observed)
{
    if (!result.errors) {
        result.wait_stage = stage;
        result.wait_expected = expected;
        result.wait_observed = observed;
    }
    ++result.errors;
    printf("TOPO_TIMEOUT pe=%d stage=%d expected=%lu observed=%lu\n", _PEN, stage, expected, observed);
    fflush(stdout);
}

static int wait_counter(athread_rply_t *reply, unsigned long value, int stage)
{
    unsigned long start, spins = 0, observed = (unsigned long)*reply;
    if (observed >= value) { fence(); return 1; }
    start = athread_stime_cycle();
    do {
        if (!(++spins & 1023UL) && athread_stime_cycle() - start >= cfg.wait_timeout_cycles) {
            timeout_record(stage, value, (unsigned long)*reply); return 0;
        }
        observed = (unsigned long)*reply;
    } while (observed < value);
    fence();
    return 1;
}

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

static int put(const void *src, int bytes, int dst, void *dest,
                athread_rply_t *lr, athread_rply_t *rr)
{
    int rc = athread_rma_iput((void *)src, lr, bytes, dst, dest, rr);
    if (rc) {
        if (!result.errors) { result.wait_stage = 11; result.wait_observed = (unsigned long)rc; }
        ++result.errors;
        printf("TOPO_API_ERROR pe=%d dst=%d bytes=%d rc=%d\n", _PEN, dst, bytes, rc);
        fflush(stdout);
        return 0;
    }
    return 1;
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
            if (!put(source + slot * cfg.bytes, cfg.bytes, cfg.flows[f].dst,
                target + (cfg.flows[f].lane * cfg.window + slot) * cfg.bytes,
                &local_reply, &remote_reply[f])) return (unsigned long)-1;
            ++issued;
            ++sent_totals[f];
        }
    }
    if (!wait_counter(&local_reply, issued, 1)) return (unsigned long)-1;
    return issued;
}

static void receive_bulk(int me, int first_flow, unsigned long begin)
{
    int f, slot;
    for (f = first_flow; f < cfg.nflows; ++f) if (cfg.flows[f].dst == me) {
        unsigned long n;
        if (cfg.mode) {
            trace("wait_metadata", (unsigned long)f);
            if (!wait_counter(&meta_reply[f], 1, 8)) return;
            n = totals[f];
        } else n = (unsigned long)cfg.reps;
        if (!wait_counter(&remote_reply[f], n, 9)) return;
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
            if (issued == (unsigned long)-1) return;
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
        trace("background_start", 0);
        issued = batch(me, 1, rounds, cfg.window, issued);
        if (issued == (unsigned long)-1) goto metadata;
        rounds += cfg.window;
        control_value = 1;
        if (!put(&control_value, 8, cfg.flows[0].src, &ready_marks[me],
            &control_local, &ready_reply[me])) goto metadata;
        if (!wait_counter(&control_local, ++control_count, 2)) goto metadata;
        trace("ready_sent", rounds);
        while (!stop_reply && rounds < (unsigned long)cfg.background_limit) {
            int count = cfg.window;
            if (rounds + count > (unsigned long)cfg.background_limit)
                count = cfg.background_limit - (int)rounds;
            issued = batch(me, 1, rounds, count, issued);
            if (issued == (unsigned long)-1) goto metadata;
            rounds += count;
            if (!(rounds / cfg.window & 63UL) && athread_stime_cycle() - begin >= cfg.wait_timeout_cycles) {
                timeout_record(10, 1, (unsigned long)stop_reply); goto metadata;
            }
        }
        if (!stop_reply) result.background_limit_hit = 1;
        else { fence(); trace("stop_received", rounds); }
metadata:
        result.sent = 0;
        for (f = 1; f < cfg.nflows; ++f) if (cfg.flows[f].src == me) result.sent += sent_totals[f];
        result.send_cycles = athread_stime_cycle() - begin;
        /* Each receiver gets the exact completed count, then drains its replies.
         * Metadata and stop traffic are outside probe timing. */
        for (f = 1; f < cfg.nflows; ++f) if (cfg.flows[f].src == me) {
            total_value = sent_totals[f];
            if (!put(&total_value, sizeof(total_value), cfg.flows[f].dst, (void *)&totals[f],
                &control_local, &meta_reply[f])) break;
            if (!wait_counter(&control_local, ++control_count, 7)) break;
        }
        trace("metadata_sent", result.sent);
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
        memset(seen, 0, sizeof(seen));
        trace("wait_ready", bg_sources);
        for (f = 1; f < cfg.nflows; ++f) if (!seen[cfg.flows[f].src]++)
            if (!wait_counter(&ready_reply[cfg.flows[f].src], 1, 3)) goto stop_background;
        trace("probe_ready", bg_sources);
        for (i = 0; i < cfg.reps + 4; ++i) {
            unsigned long end;
            if (i == 4) begin = athread_stime_cycle();
            if (i >= 4 && (i - 4) % TOPO_SAMPLE_BATCH == 0)
                sample_begin = athread_stime_cycle();
            tag(source, (unsigned int)i, me);
            if (!put(source, cfg.probe_bytes, dst, target, &local_reply, &remote_reply[0])) goto stop_background;
            if (!wait_counter(&local_reply, i + 1, 4)) goto stop_background;
            if (!wait_counter(&remote_reply[0], i + 1, 5)) goto stop_background;
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
        trace("probe_done", cfg.reps);
stop_background:
        memset(seen, 0, sizeof(seen));
        control_value = 1;
        { unsigned long stops = 0;
          for (f = 1; f < cfg.nflows; ++f) if (!seen[cfg.flows[f].src]++)
            if (put(&control_value, 8, cfg.flows[f].src, &stop_word,
                    &control_local, &stop_reply)) ++stops;
          if (stops) wait_counter(&control_local, stops, 6);
          trace("stop_sent", stops);
        }
    } else {
        for (i = 0; i < cfg.reps + 4; ++i) {
            if (i == 4) begin = athread_stime_cycle();
            if (!wait_counter(&remote_reply[0], i + 1, 5)) return;
            if (check_tag(target, (unsigned int)i, src)) ++result.errors;
            tag(source, (unsigned int)i, me);
            if (!put(source, cfg.reply_bytes, src, target, &local_reply, &remote_reply[0])) return;
            if (!wait_counter(&local_reply, i + 1, 4)) return;
        }
        result.cycles = athread_stime_cycle() - begin;
        result.received = result.sent = cfg.reps;
        check_payload(target, cfg.probe_bytes, (unsigned int)(cfg.reps + 3), src, 0);
        trace("responder_done", cfg.reps);
    }
}

void topology_kernel(topo_args_t *host_arg)
{
    int me = _PEN, f, j, active = 0;
    unsigned long begin;
    athread_dma_get(&cfg, host_arg, sizeof(cfg));
    memset(&result, 0, sizeof(result)); memset(sample_buffer, 0, sizeof(sample_buffer));
    /* The installed SDK typedefs reply words as volatile. Use scalar stores
     * rather than passing volatile arrays to memset. All traffic is quiescent. */
    for (f = 0; f < TOPO_MAX_FLOWS; ++f) {
        remote_reply[f] = 0;
        meta_reply[f] = 0;
    }
    for (f = 0; f < TOPO_MAX_FLOWS; ++f) { totals[f] = 0; sent_totals[f] = 0; }
    memset(target, 0, sizeof(target));
    local_reply = control_local = stop_reply = 0;
    for (f = 0; f < TOPO_PES; ++f) ready_reply[f] = 0;
    memset(ready_marks, 0, sizeof(ready_marks));
    stop_word = 0; control_value = 0;
    for (j = 0; j < TOPO_BUFFER_BYTES; ++j) source[j] = pattern(me, j);
    for (f = 0; f < cfg.nflows; ++f)
        if (cfg.flows[f].src == me || cfg.flows[f].dst == me) active = 1;
    athread_ssync_array();
    if (!cfg.mode) {
        int outgoing = 0, count = cfg.reps < cfg.window ? cfg.reps : cfg.window;
        for (f = 0; f < cfg.nflows; ++f) if (cfg.flows[f].src == me) ++outgoing;
        if (outgoing) batch(me, 0, 0, count, 0);
        for (f = 0; f < cfg.nflows; ++f) if (cfg.flows[f].dst == me)
            wait_counter(&remote_reply[f], count, 9);
    }
    athread_ssync_array();
    local_reply = 0;
    for (f = 0; f < TOPO_MAX_FLOWS; ++f) { remote_reply[f] = 0; sent_totals[f] = 0; }
    athread_ssync_array();
    begin = athread_stime_cycle();
    if (active && !result.errors) {
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
