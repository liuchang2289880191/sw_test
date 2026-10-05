#define _POSIX_C_SOURCE 200112L
#include <athread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "bench_common.h"

extern void SLAVE_FUN(bcast_kernel)();

static int number(const char *s, int min, int max)
{
    char *end;
    long v = strtol(s, &end, 10);
    if (!*s || *end || v < min || v > max) return -1;
    return (int)v;
}

int main(int argc, char **argv)
{
    bcast_args_t a;
    unsigned long *cycles, max_cycles = 0;
    int *errors, i, failed = 0;
    const char *name;
    if (argc != 5) {
        fprintf(stderr, "usage: %s row|col|array bytes reps root\n", argv[0]);
        return 2;
    }
    name = argv[1];
    a.scope = !strcmp(name, "row") ? 0 : !strcmp(name, "col") ? 1 :
              !strcmp(name, "array") ? 2 : -1;
    a.bytes = number(argv[2], 4, BENCH_MAX_BYTES);
    a.reps = number(argv[3], 1, 100000);
    a.root = number(argv[4], 0, a.scope == 2 ? 63 : 7);
    if (a.scope < 0 || a.bytes < 0 || (a.bytes & 3) ||
        a.reps < 0 || a.root < 0) {
        fprintf(stderr, "invalid arguments\n");
        return 2;
    }
    if (posix_memalign((void **)&cycles, 128, BENCH_PES * sizeof(*cycles)) ||
        posix_memalign((void **)&errors, 128, BENCH_PES * sizeof(*errors))) {
        fprintf(stderr, "allocation failed\n");
        return 1;
    }
    a.cycles = cycles; a.errors = errors;
    if (athread_init() != 0 ||
        athread_spawn(bcast_kernel, &a) != 0 ||
        athread_join() != 0) {
        fprintf(stderr, "athread launch failed\n");
        return 1;
    }
    athread_halt();
    printf("benchmark,scope,bytes,reps,root,pe,cycles,cycles_per_op,logical_bytes_per_cycle,errors\n");
    for (i = 0; i < BENCH_PES; ++i) {
        if (cycles[i] > max_cycles) max_cycles = cycles[i];
        if (errors[i]) failed = 1;
        printf("rma_bcast,%s,%d,%d,%d,%d,%lu,%.6f,,%d\n", name,
               a.bytes, a.reps, a.root, i, cycles[i],
               (double)cycles[i] / a.reps, errors[i]);
    }
    printf("rma_bcast,%s,%d,%d,%d,aggregate,%lu,%.6f,%.9f,%d\n",
           name, a.bytes, a.reps, a.root, max_cycles,
           (double)max_cycles / a.reps,
           max_cycles ? (double)a.bytes * a.reps * 64 / max_cycles : 0.0,
           failed);
    free(cycles); free(errors);
    return failed ? 1 : 0;
}
