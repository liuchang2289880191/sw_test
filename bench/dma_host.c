#define _POSIX_C_SOURCE 200112L
#include <athread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
#include "bench_common.h"

extern void SLAVE_FUN(dma_kernel)();

/* Only stderr is used, so diagnostic stages never enter benchmark CSV. */
static void stage(const char *name)
{
    fprintf(stderr, "DMA_STAGE %s\n", name);
    fflush(stderr);
}

static int number(const char *s, int min, int max)
{
    char *end;
    long v = strtol(s, &end, 10);
    if (!*s || *end || v < min || v > max) return -1;
    return (int)v;
}

int main(int argc, char **argv)
{
    static const char *names[] = {"get", "put", "iget", "iput"};
    dma_args_t a;
    unsigned char *src, *dst;
    unsigned long *cycles, max_cycles = 0;
    int *errors;
    int i, j, mode = -1, failed = 0, rc;
    size_t total = (size_t)BENCH_PES * BENCH_SLOT_BYTES;

    stage("host.enter");
    if (argc != 6) {
        fprintf(stderr, "usage: %s get|put|iget|iput bytes reps active_pes(1|64) offset(0|4)\n", argv[0]);
        return 2;
    }
    for (i = 0; i < 4; ++i) if (!strcmp(argv[1], names[i])) mode = i;
    a.bytes = number(argv[2], 4, BENCH_MAX_BYTES);
    a.reps = number(argv[3], 1, 1000000);
    a.active = number(argv[4], 1, BENCH_PES);
    a.offset = number(argv[5], 0, 4);
    if (mode < 0 || a.bytes < 0 || (a.bytes & 3) || a.reps < 0 ||
        (a.active != 1 && a.active != 64) ||
        (a.offset != 0 && a.offset != 4)) {
        fprintf(stderr, "invalid arguments (bytes must be a multiple of 4)\n");
        return 2;
    }
    a.mode = mode;
    fprintf(stderr, "DMA_CONFIG mode=%s bytes=%d reps=%d active=%d offset=%d args=%p args_size=%lu\n",
            names[mode], a.bytes, a.reps, a.active, a.offset, (void *)&a,
            (unsigned long)sizeof(a));
    fflush(stderr);
    stage("host.allocate.begin");
    if (posix_memalign((void **)&src, 128, total) ||
        posix_memalign((void **)&dst, 128, total) ||
        posix_memalign((void **)&cycles, 128, BENCH_PES * sizeof(*cycles)) ||
        posix_memalign((void **)&errors, 128, BENCH_PES * sizeof(*errors))) {
        fprintf(stderr, "allocation failed\n");
        return 1;
    }
    fprintf(stderr, "DMA_ADDRESSES src=%p dst=%p cycles=%p errors=%p slot_bytes=%d\n",
            (void *)src, (void *)dst, (void *)cycles, (void *)errors,
            BENCH_SLOT_BYTES);
    fflush(stderr);
    stage("host.allocate.done");
    memset(dst, 0, total);
    memset(cycles, 0, BENCH_PES * sizeof(*cycles));
    memset(errors, 0, BENCH_PES * sizeof(*errors));
    for (i = 0; i < BENCH_PES; ++i)
        for (j = 0; j < a.bytes; ++j)
            src[i * BENCH_SLOT_BYTES + a.offset + j] =
                (unsigned char)((i * 17 + j * 13 + 7) & 255);
    a.src = src; a.dst = dst; a.cycles = cycles; a.errors = errors;

    stage("host.init.begin");
    rc = athread_init();
    if (rc != 0) {
        fprintf(stderr, "athread_init failed: %d\n", rc);
        return 1;
    }
    stage("host.init.done");
    stage("host.spawn.begin");
    rc = athread_spawn(dma_kernel, &a);
    if (rc != 0) {
        fprintf(stderr, "athread_spawn failed: %d\n", rc);
        return 1;
    }
    stage("host.spawn.done");
    stage("host.join.begin");
    rc = athread_join();
    if (rc != 0) {
        fprintf(stderr, "athread_join failed: %d\n", rc);
        return 1;
    }
    stage("host.join.done");
    stage("host.halt.begin");
    athread_halt();
    stage("host.halt.done");
    if (mode == 1 || mode == 3) {
        for (i = 0; i < a.active; ++i)
            for (j = 0; j < a.bytes; ++j)
                if (dst[i * BENCH_SLOT_BYTES + a.offset + j] !=
                    (unsigned char)((i * 17 + j * 13 + 7) & 255)) {
                    ++errors[i];
                    break;
                }
    }
    for (i = 0; i < a.active; ++i) {
        if (cycles[i] > max_cycles) max_cycles = cycles[i];
        if (errors[i]) failed = 1;
    }
    stage("host.verify.done");
    printf("benchmark,mode,bytes,reps,active_pes,offset,pe,cycles,cycles_per_op,aggregate_bytes_per_cycle,errors\n");
    for (i = 0; i < a.active; ++i)
        printf("dma,%s,%d,%d,%d,%d,%d,%lu,%.6f,,%d\n", names[mode],
               a.bytes, a.reps, a.active, a.offset, i, cycles[i],
               (double)cycles[i] / a.reps, errors[i]);
    printf("dma,%s,%d,%d,%d,%d,aggregate,%lu,%.6f,%.9f,%d\n",
           names[mode], a.bytes, a.reps, a.active, a.offset, max_cycles,
           (double)max_cycles / a.reps,
           max_cycles ? (double)a.bytes * a.reps * a.active / max_cycles : 0.0,
           failed);
    fflush(stdout);
    stage("host.print.done");
    stage("host.free.begin");
    free(src); free(dst); free(cycles); free(errors);
    stage("host.free.done");
    return failed ? 1 : 0;
}
