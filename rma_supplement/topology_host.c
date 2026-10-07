#define _POSIX_C_SOURCE 200112L
#include <athread.h>
#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifndef _WIN32
#include <unistd.h>
#endif
#include "topology_common.h"
extern void SLAVE_FUN(topology_kernel)();

static int safe(const char *s)
{
    if (!*s) return 0;
    for (; *s; ++s) if (!isalnum((unsigned char)*s) && *s != '_') return 0;
    return 1;
}

static int valid(topo_args_t *a)
{
    int incoming[64] = {0}, i, j, first = a->mode ? 1 : 0;
    if (a->mode < 0 || a->mode > 1 || a->nflows < 1 || a->nflows > TOPO_MAX_FLOWS ||
        a->bytes < 8 || a->bytes % 4 || a->window < 1 || a->window > 16 ||
        a->reps < TOPO_SAMPLE_BATCH || a->reps > TOPO_MAX_REPS || a->reps % TOPO_SAMPLE_BATCH ||
        (long long)a->bytes * a->window > TOPO_BUFFER_BYTES) return 0;
    if (a->mode && (a->probe_bytes < 8 || a->probe_bytes % 4 || a->probe_bytes > TOPO_BUFFER_BYTES ||
                   a->reply_bytes < 8 || a->reply_bytes % 4 || a->reply_bytes > TOPO_BUFFER_BYTES)) return 0;
    if (!a->mode && a->reply_bytes) return 0;
    for (i = 0; i < a->nflows; ++i) {
        topo_flow_t *f = &a->flows[i];
        if (f->src < 0 || f->src > 63 || f->dst < 0 || f->dst > 63 || f->src == f->dst) return 0;
        for (j = 0; j < i; ++j)
            if (f->src == a->flows[j].src && f->dst == a->flows[j].dst) return 0;
        if (i >= first) f->lane = incoming[f->dst]++;
        if (a->mode && i && (f->src == a->flows[0].src || f->src == a->flows[0].dst ||
                            f->dst == a->flows[0].src || f->dst == a->flows[0].dst)) return 0;
    }
    for (i = 0; i < 64; ++i)
        if ((long long)incoming[i] * a->bytes * a->window > TOPO_BUFFER_BYTES) return 0;
    a->background_limit = 2000000;
    return 1;
}

static int parse(char *line, topo_args_t *a, char *id)
{
    char group[32], family[32], label[128], role[64], extra;
    int used = 0, i, n;
    char *p;
    memset(a, 0, sizeof(*a));
    n = sscanf(line, "%63s %31s %31s %127s %63s %d %d %d %d %d %d %d %n",
               id, group, family, label, role, &a->mode, &a->bytes, &a->probe_bytes,
               &a->reply_bytes, &a->reps, &a->window, &a->nflows, &used);
    if (n != 12 || !safe(id) || !safe(group) || !safe(family) || !safe(label) || !safe(role) ||
        a->nflows < 1 || a->nflows > TOPO_MAX_FLOWS) return 0;
    p = line + used;
    for (i = 0; i < a->nflows; ++i) {
        used = 0;
        if (sscanf(p, " %d %d %n", &a->flows[i].src, &a->flows[i].dst, &used) != 2) return 0;
        p += used;
    }
    if (sscanf(p, " %c", &extra) == 1) return 0;
    return valid(a);
}

static int resources(const char *out)
{
    char path[4096], line[1024];
    FILE *f, *cpu;
    if (snprintf(path, sizeof(path), "%s/resource_runtime.txt", out) >= (int)sizeof(path)) return 1;
    f = fopen(path, "w"); if (!f) return 1;
    fprintf(f, "start_epoch=%ld\nresource_exclusivity=unknown\ncounter_frequency=not_calibrated\n", (long)time(NULL));
#ifndef _WIN32
    { char host[256] = {0}; if (!gethostname(host, sizeof(host)-1)) fprintf(f, "hostname=%s\n", host); }
#endif
    cpu = fopen("/proc/cpuinfo", "r");
    if (cpu) { while (fgets(line, sizeof(line), cpu)) fputs(line, f); fclose(cpu); }
    else fputs("cpuinfo=unavailable\n", f);
    { int status = ferror(f); if (fclose(f)) status = 1; return status; }
}

static int write_result(FILE *csv, const topo_args_t *a)
{
    int i, f, failed = 0, first = a->mode ? 1 : 0;
    unsigned long max_cycles = 0, sent = 0, received = 0;
    fprintf(csv, "record,pe,cycles,send_cycles,recv_cycles,sent,received,errors,background_limit_hit,value\n");
    for (i = 0; i < TOPO_PES; ++i) {
        int active = 0, outgoing = 0, incoming = 0;
        const topo_result_t *r = a->results + i;
        for (f = 0; f < a->nflows; ++f)
            if (a->flows[f].src == i || a->flows[f].dst == i) active = 1;
        if (!active) continue;
        for (f = first; f < a->nflows; ++f) {
            if (a->flows[f].src == i) ++outgoing;
            if (a->flows[f].dst == i) ++incoming;
        }
        if (!r->cycles || r->errors || r->background_limit_hit) failed = 1;
        if (outgoing && (!r->send_cycles || !r->sent)) failed = 1;
        if (incoming && (!r->recv_cycles || !r->received)) failed = 1;
        if (!a->mode && (r->sent != (unsigned long)(a->reps * outgoing) ||
                        r->received != (unsigned long)(a->reps * incoming))) failed = 1;
        if (r->cycles > max_cycles) max_cycles = r->cycles;
        if (!(a->mode && (i == a->flows[0].src || i == a->flows[0].dst))) {
            sent += r->sent; received += r->received;
        }
        fprintf(csv, "pe,%d,%lu,%lu,%lu,%lu,%lu,%d,%d,\n", i, r->cycles,
                r->send_cycles, r->recv_cycles, r->sent, r->received, r->errors, r->background_limit_hit);
    }
    if (sent != received) failed = 1;
    if (a->mode) {
        const topo_result_t *r = a->results + a->flows[0].src;
        max_cycles = r->cycles;
        if (r->sent != (unsigned long)a->reps || r->received != (unsigned long)a->reps) failed = 1;
        fprintf(csv, "aggregate,probe,%lu,0,0,%d,%d,%d,0,%.9f\n", max_cycles,
                a->reps, a->reps, failed, (double)max_cycles / a->reps);
        for (i = 0; i < a->reps / TOPO_SAMPLE_BATCH; ++i) {
            if (!a->samples[i]) failed = 1;
            fprintf(csv, "sample,%d,%lu,0,0,0,0,0,0,%.9f\n", i, a->samples[i],
                    (double)a->samples[i] / TOPO_SAMPLE_BATCH);
        }
    } else fprintf(csv, "aggregate,bulk,%lu,0,0,%lu,%lu,%d,0,%.9f\n", max_cycles,
                   sent, received, failed, max_cycles ? (double)a->bytes * a->reps * a->nflows / max_cycles : 0.0);
    if (fflush(csv) || ferror(csv)) failed = 1;
    return failed;
}

int main(int argc, char **argv)
{
    static topo_args_t args __attribute__((aligned(128)));
    char line[2048], id[64], path[4096];
    FILE *plan, *csv;
    int status = 0, count = 0, validate = 0, initialized = 0;
    topo_result_t *results = NULL;
    unsigned long *samples = NULL;
    if (argc == 3 && !strcmp(argv[1], "--validate-plan")) validate = 1;
    else if (argc != 4 || strcmp(argv[1], "--suite")) {
        fprintf(stderr, "usage: %s --suite plan.txt NEW_OUTPUT_DIR | --validate-plan plan.txt\n", argv[0]); return 2;
    }
    plan = fopen(argv[2], "r"); if (!plan) { perror(argv[2]); return 1; }
    if (!validate) {
        if (resources(argv[3]) || posix_memalign((void **)&results, 128, TOPO_PES * sizeof(*results)) ||
            posix_memalign((void **)&samples, 128, TOPO_MAX_SAMPLES * sizeof(*samples))) { status = 1; goto end; }
        if (athread_init()) { status = 1; goto end; }
        initialized = 1;
    }
    while (fgets(line, sizeof(line), plan)) {
        if (line[0] == '#') continue;
        if ((!strchr(line, '\n') && !feof(plan)) || !parse(line, &args, id)) {
            fprintf(stderr, "invalid plan at case %d\n", count + 1); status = 2; break;
        }
        ++count;
        if (validate) continue;
        memset(results, 0, TOPO_PES * sizeof(*results));
        memset(samples, 0, TOPO_MAX_SAMPLES * sizeof(*samples));
        args.results = results; args.samples = samples;
        fprintf(stderr, "TOPO_CASE %d %s mode=%d bytes=%d probe=%d reply=%d window=%d flows=%d\n",
                count, id, args.mode, args.bytes, args.probe_bytes, args.reply_bytes, args.window, args.nflows);
        if (athread_spawn(topology_kernel, &args) || athread_join()) { status = 1; break; }
        if (snprintf(path, sizeof(path), "%s/raw/%s.csv", argv[3], id) >= (int)sizeof(path)) { status = 2; break; }
        csv = fopen(path, "w"); if (!csv) { perror(path); status = 1; break; }
        status = write_result(csv, &args);
        if (fclose(csv)) status = 1;
        if (status) { fprintf(stderr, "FAILED %s; stopping subsequent cases\n", id); break; }
    }
    if (ferror(plan) || !count) status = 1;
end:
    fclose(plan);
    if (initialized) athread_halt();
    free(results); free(samples);
    if (!status && !validate) {
        if (snprintf(path, sizeof(path), "%s/RUN_COMPLETE", argv[3]) >= (int)sizeof(path)) return 2;
        csv = fopen(path, "w"); if (!csv) return 1;
        if (fprintf(csv, "completed_cases=%d\n", count) < 0) status = 1;
        if (fclose(csv)) status = 1;
    }
    if (!status && validate) printf("valid_cases=%d\n", count);
    return status;
}
