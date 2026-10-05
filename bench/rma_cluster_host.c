#define _POSIX_C_SOURCE 200112L
#include <athread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "bench_common.h"

extern void SLAVE_FUN(cluster_kernel)();

static int number(const char *s, int min, int max)
{
    char *end;
    long v = strtol(s, &end, 10);
    if (!*s || *end || v < min || v > max) return -1;
    return (int)v;
}

static int cluster_of(int tid)
{
    return (tid / 8 / 2) * 4 + (tid % 8 / 2);
}

static int member(int cluster, int local)
{
    return (cluster / 4 * 2 + local / 2) * 8 +
           cluster % 4 * 2 + local % 2;
}

static void add_flow(cluster_args_t *a, int src, int dst)
{
    int i, lane = 0;
    for (i = 0; i < a->nflows; ++i)
        if (a->flows[i].dst == dst) ++lane;
    a->flows[a->nflows].src = src;
    a->flows[a->nflows].dst = dst;
    a->flows[a->nflows].lane = lane;
    ++a->nflows;
}

static int make_case(cluster_args_t *a, const char *name)
{
    int members[4], near, side, far, i, j;
    for (i = 0; i < 4; ++i) members[i] = member(a->cluster_index, i);
    near = a->cluster_index / 4 == 3 ? a->cluster_index - 4 :
           a->cluster_index + 4;
    side = a->cluster_index % 4 == 3 ? a->cluster_index - 1 :
           a->cluster_index + 1;
    far = ((a->cluster_index / 4 + 2) % 4) * 4 + a->cluster_index % 4;
    if (!strcmp(name, "single")) add_flow(a, members[0], members[1]);
    else if (!strcmp(name, "intra2")) {
        add_flow(a, members[0], members[1]);
        add_flow(a, members[2], members[3]);
    } else if (!strcmp(name, "split_near2")) {
        add_flow(a, members[0], members[1]);
        add_flow(a, member(near, 0), member(near, 1));
    } else if (!strcmp(name, "split_side2")) {
        add_flow(a, members[0], members[1]);
        add_flow(a, member(side, 0), member(side, 1));
    } else if (!strcmp(name, "split_far2")) {
        add_flow(a, members[0], members[1]);
        add_flow(a, member(far, 0), member(far, 1));
    } else if (!strcmp(name, "incast3")) {
        add_flow(a, members[1], members[0]);
        add_flow(a, members[2], members[0]);
        add_flow(a, members[3], members[0]);
    } else if (!strcmp(name, "ring4")) {
        add_flow(a, members[0], members[1]);
        add_flow(a, members[1], members[3]);
        add_flow(a, members[3], members[2]);
        add_flow(a, members[2], members[0]);
    } else if (!strcmp(name, "alltoall4")) {
        for (i = 0; i < 4; ++i)
            for (j = 0; j < 4; ++j)
                if (i != j) add_flow(a, members[i], members[j]);
    } else return -1;
    return 0;
}

static int valid_capacity(const cluster_args_t *a)
{
    int incoming[BENCH_PES] = {0};
    int f, max_in = 0;
    for (f = 0; f < a->nflows; ++f)
        ++incoming[a->flows[f].dst];
    for (f = 0; f < BENCH_PES; ++f)
        if (incoming[f] > max_in) max_in = incoming[f];
    return (long long)a->bytes * a->window * max_in <= BENCH_MAX_BYTES;
}

int main(int argc, char **argv)
{
    cluster_args_t a;
    unsigned long *cycles, max_cycles = 0;
    int *errors, *peer_errors, i, j, failed = 0;
    const char *case_name;
    memset(&a, 0, sizeof(a));
    if (argc >= 2 && !strcmp(argv[1], "latency") && argc == 4) {
        a.mode = 0;
        a.bytes = number(argv[2], 4, 256);
        a.reps = number(argv[3], 1, 100000);
        a.window = 1;
        case_name = "pingpong_matrix";
    } else if (argc >= 2 && !strcmp(argv[1], "bandwidth") && argc == 7) {
        int src = number(argv[2], 0, 63);
        int dst = number(argv[3], 0, 63);
        a.mode = 1;
        a.bytes = number(argv[4], 4, BENCH_MAX_BYTES);
        a.reps = number(argv[5], 1, 1000000);
        a.window = number(argv[6], 1, 32);
        if (src < 0 || dst < 0 || src == dst) {
            fprintf(stderr, "invalid pair\n"); return 2;
        }
        add_flow(&a, src, dst);
        case_name = "pair";
    } else if (argc >= 2 && !strcmp(argv[1], "contention") &&
               (argc == 6 || argc == 7)) {
        a.mode = 1;
        case_name = argv[2];
        a.bytes = number(argv[3], 4, BENCH_MAX_BYTES);
        a.reps = number(argv[4], 1, 1000000);
        a.window = number(argv[5], 1, 32);
        a.cluster_index = argc == 7 ? number(argv[6], 0, 15) : 0;
        if (a.cluster_index < 0) return 2;
        if (make_case(&a, case_name)) {
            fprintf(stderr, "case: single|intra2|split_near2|split_side2|split_far2|incast3|ring4|alltoall4\n");
            return 2;
        }
    } else {
        fprintf(stderr, "usage:\n  %s latency bytes reps\n  %s bandwidth src dst bytes reps window\n  %s contention case bytes reps window [cluster_index]\n", argv[0], argv[0], argv[0]);
        return 2;
    }
    if (a.bytes < 0 || (a.bytes & 3) || a.reps < 0 || a.window < 0 ||
        (a.mode == 1 && !valid_capacity(&a))) {
        fprintf(stderr, "invalid size/window: require bytes*window*max_incoming <= %d\n",
                BENCH_MAX_BYTES);
        return 2;
    }
    if (posix_memalign((void **)&cycles, 128, BENCH_PES * BENCH_PES * sizeof(*cycles)) ||
        posix_memalign((void **)&errors, 128, BENCH_PES * BENCH_PES * sizeof(*errors)) ||
        posix_memalign((void **)&peer_errors, 128,
                       BENCH_PES * BENCH_PES * sizeof(*peer_errors))) {
        fprintf(stderr, "allocation failed\n"); return 1;
    }
    memset(cycles, 0, BENCH_PES * BENCH_PES * sizeof(*cycles));
    memset(errors, 0, BENCH_PES * BENCH_PES * sizeof(*errors));
    memset(peer_errors, 0, BENCH_PES * BENCH_PES * sizeof(*peer_errors));
    a.cycles = cycles; a.errors = errors; a.peer_errors = peer_errors;
    if (athread_init() != 0 || athread_spawn(cluster_kernel, &a) != 0 ||
        athread_join() != 0) {
        fprintf(stderr, "athread launch failed\n"); return 1;
    }
    athread_halt();
    if (a.mode == 0) {
        printf("benchmark,bytes,reps,initiator,peer,same_cluster,row_distance,col_distance,rtt_cycles,latency_cycles,errors\n");
        for (i = 0; i < BENCH_PES; ++i)
            for (j = 0; j < BENCH_PES; ++j) {
                int idx = i * BENCH_PES + j;
                int err, dr, dc;
                if (i == j) continue;
                err = errors[idx] + peer_errors[j * BENCH_PES + i];
                if (err) failed = 1;
                dr = abs(i / 8 - j / 8);
                dc = abs(i % 8 - j % 8);
                printf("rma_pingpong,%d,%d,%d,%d,%d,%d,%d,%lu,%.6f,%d\n",
                       a.bytes, a.reps, i, j, cluster_of(i) == cluster_of(j),
                       dr, dc, cycles[idx], (double)cycles[idx] / (2 * a.reps), err);
            }
    } else {
        printf("benchmark,case,cluster_index,bytes,reps,window,flows,pe,cycles,aggregate_bytes_per_cycle,errors\n");
        for (i = 0; i < BENCH_PES; ++i) {
            int active = 0;
            for (j = 0; j < a.nflows; ++j)
                if (a.flows[j].src == i || a.flows[j].dst == i) active = 1;
            if (!active) continue;
            if (cycles[i] > max_cycles) max_cycles = cycles[i];
            if (errors[i]) failed = 1;
            printf("rma_flow,%s,%d,%d,%d,%d,%d,%d,%lu,,%d\n",
                   case_name, a.cluster_index, a.bytes, a.reps,
                   a.window, a.nflows,
                   i, cycles[i], errors[i]);
        }
        printf("rma_flow,%s,%d,%d,%d,%d,%d,aggregate,%lu,%.9f,%d\n",
               case_name, a.cluster_index, a.bytes, a.reps,
               a.window, a.nflows, max_cycles,
               max_cycles ? (double)a.bytes * a.reps * a.nflows / max_cycles : 0.0,
               failed);
    }
    free(cycles); free(errors); free(peer_errors);
    return failed ? 1 : 0;
}
