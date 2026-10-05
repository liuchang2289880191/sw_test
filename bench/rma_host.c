#define _POSIX_C_SOURCE 200112L
#include <athread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "bench_common.h"

extern void SLAVE_FUN(rma_kernel)();

static int number(const char *s, int min, int max)
{
    char *end;
    long v = strtol(s, &end, 10);
    if (!*s || *end || v < min || v > max) return -1;
    return (int)v;
}

int main(int argc, char **argv)
{
    rma_args_t a;
    unsigned long *cycles;
    int *errors, *receiver_errors, src, dst, failed = 0;
    const char *op;
    if (argc != 4 || (strcmp(argv[1], "put") && strcmp(argv[1], "get"))) {
        fprintf(stderr, "usage: %s put|get bytes reps\n", argv[0]);
        return 2;
    }
    op = argv[1];
    a.op = !strcmp(op, "get");
    a.bytes = number(argv[2], 4, BENCH_MAX_BYTES);
    a.reps = number(argv[3], 1, 100000);
    if (a.bytes < 0 || (a.bytes & 3) || a.reps < 0) {
        fprintf(stderr, "bytes must be 4..65536 and a multiple of 4; reps 1..100000\n");
        return 2;
    }
    if (posix_memalign((void **)&cycles, 128,
                       BENCH_PES * BENCH_PES * sizeof(*cycles)) ||
        posix_memalign((void **)&errors, 128,
                       BENCH_PES * BENCH_PES * sizeof(*errors)) ||
        posix_memalign((void **)&receiver_errors, 128,
                       BENCH_PES * BENCH_PES * sizeof(*receiver_errors))) {
        fprintf(stderr, "allocation failed\n");
        return 1;
    }
    memset(cycles, 0, BENCH_PES * BENCH_PES * sizeof(*cycles));
    memset(errors, 0, BENCH_PES * BENCH_PES * sizeof(*errors));
    memset(receiver_errors, 0, BENCH_PES * BENCH_PES * sizeof(*receiver_errors));
    a.cycles = cycles; a.errors = errors; a.receiver_errors = receiver_errors;
    if (athread_init() != 0 ||
        athread_spawn(rma_kernel, &a) != 0 ||
        athread_join() != 0) {
        fprintf(stderr, "athread launch failed\n");
        return 1;
    }
    athread_halt();
    printf("benchmark,operation,bytes,reps,initiator,peer,initiator_row,initiator_col,peer_row,peer_col,relation,cycles,cycles_per_op,errors\n");
    for (src = 0; src < BENCH_PES; ++src) {
        for (dst = 0; dst < BENCH_PES; ++dst) {
            int idx = src * BENCH_PES + dst;
            int sr = src / 8, sc = src % 8, dr = dst / 8, dc = dst % 8;
            const char *relation = src == dst ? "self_skipped" :
                sr == dr ? "same_row" :
                sc == dc ? "same_col" :
                abs(sr - dr) == abs(sc - dc) ? "diagonal" : "other";
            int err = errors[idx];
            if (!a.op && src != dst)
                err += receiver_errors[dst * BENCH_PES + src];
            if (err) failed = 1;
            printf("rma,%s,%d,%d,%d,%d,%d,%d,%d,%d,%s,%lu,%.6f,%d\n",
                   op, a.bytes, a.reps, src, dst, sr, sc, dr, dc,
                   relation, cycles[idx],
                   src == dst ? 0.0 : (double)cycles[idx] / a.reps, err);
        }
    }
    free(cycles); free(errors); free(receiver_errors);
    return failed ? 1 : 0;
}
