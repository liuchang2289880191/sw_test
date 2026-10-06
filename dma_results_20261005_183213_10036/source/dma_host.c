#define _POSIX_C_SOURCE 200112L
#include <athread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "bench_common.h"

extern void SLAVE_FUN(dma_kernel)();
static const char *names[] = {"get", "put", "iget", "iput"};

typedef struct {
    dma_args_t args;
    unsigned char *src, *dst;
    unsigned long *cycles;
    int *errors;
    int initialized;
} dma_context_t;

/* Diagnostics use stderr and execute outside the CPE timed loop. */
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

static int prepare(dma_context_t *ctx)
{
    int rc;
    size_t total = (size_t)BENCH_PES * BENCH_SLOT_BYTES;
    stage("host.allocate.begin");
    if (posix_memalign((void **)&ctx->src, 128, total) ||
        posix_memalign((void **)&ctx->dst, 128, total) ||
        posix_memalign((void **)&ctx->cycles, 128,
                       BENCH_PES * sizeof(*ctx->cycles)) ||
        posix_memalign((void **)&ctx->errors, 128,
                       BENCH_PES * sizeof(*ctx->errors))) {
        fprintf(stderr, "allocation failed\n");
        return 1;
    }
    fprintf(stderr, "DMA_ADDRESSES src=%p dst=%p cycles=%p errors=%p slot_bytes=%d\n",
            (void *)ctx->src, (void *)ctx->dst, (void *)ctx->cycles,
            (void *)ctx->errors, BENCH_SLOT_BYTES);
    fflush(stderr);
    ctx->args.src = ctx->src;
    ctx->args.dst = ctx->dst;
    ctx->args.cycles = ctx->cycles;
    ctx->args.errors = ctx->errors;
    stage("host.allocate.done");
    stage("host.init.begin");
    rc = athread_init();
    if (rc != 0) {
        fprintf(stderr, "athread_init failed: %d\n", rc);
        return 1;
    }
    ctx->initialized = 1;
    stage("host.init.done");
    return 0;
}

static void release(dma_context_t *ctx)
{
    if (ctx->initialized) {
        stage("host.halt.begin");
        athread_halt();
        ctx->initialized = 0;
        stage("host.halt.done");
    }
    stage("host.free.begin");
    free(ctx->src); free(ctx->dst); free(ctx->cycles); free(ctx->errors);
    stage("host.free.done");
}

static int run_one(dma_context_t *ctx, int mode, int bytes, int reps,
                   int active, int offset, FILE *output)
{
    dma_args_t *a = &ctx->args;
    unsigned long max_cycles = 0;
    size_t total = (size_t)BENCH_PES * BENCH_SLOT_BYTES;
    int i, j, rc, failed = 0;
    a->mode = mode; a->bytes = bytes; a->reps = reps;
    a->active = active; a->offset = offset;
    fprintf(stderr, "DMA_CONFIG mode=%s bytes=%d reps=%d active=%d offset=%d args=%p args_size=%lu\n",
            names[mode], bytes, reps, active, offset, (void *)a,
            (unsigned long)sizeof(*a));
    fflush(stderr);

    /* Reset each case so an earlier successful put cannot mask a later failure. */
    memset(ctx->dst, 0, total);
    memset(ctx->cycles, 0, BENCH_PES * sizeof(*ctx->cycles));
    memset(ctx->errors, 0, BENCH_PES * sizeof(*ctx->errors));
    for (i = 0; i < BENCH_PES; ++i)
        for (j = 0; j < bytes; ++j)
            ctx->src[i * BENCH_SLOT_BYTES + offset + j] =
                (unsigned char)((i * 17 + j * 13 + 7) & 255);

    stage("host.spawn.begin");
    rc = athread_spawn(dma_kernel, a);
    if (rc != 0) {
        fprintf(stderr, "athread_spawn failed: %d\n", rc);
        return 1;
    }
    stage("host.spawn.done");
    stage("host.join.begin");
    rc = athread_join();
    if (rc != 0) {
        fprintf(stderr, "athread_join failed: %d\n", rc);
        /* A failed join does not prove that DMA no longer touches the buffers. */
        fflush(stderr);
        exit(1);
    }
    stage("host.join.done");
    if (mode == 1 || mode == 3) {
        for (i = 0; i < active; ++i)
            for (j = 0; j < bytes; ++j)
                if (ctx->dst[i * BENCH_SLOT_BYTES + offset + j] !=
                    (unsigned char)((i * 17 + j * 13 + 7) & 255)) {
                    ++ctx->errors[i];
                    break;
                }
    }
    for (i = 0; i < active; ++i) {
        if (ctx->cycles[i] > max_cycles) max_cycles = ctx->cycles[i];
        if (ctx->errors[i]) failed = 1;
        if (ctx->cycles[i] == 0) failed = 1;
    }
    stage("host.verify.done");
    fprintf(output, "benchmark,mode,bytes,reps,active_pes,offset,pe,cycles,cycles_per_op,aggregate_bytes_per_cycle,errors\n");
    for (i = 0; i < active; ++i)
        fprintf(output, "dma,%s,%d,%d,%d,%d,%d,%lu,%.6f,,%d\n",
                names[mode], bytes, reps, active, offset, i, ctx->cycles[i],
                (double)ctx->cycles[i] / reps, ctx->errors[i]);
    fprintf(output, "dma,%s,%d,%d,%d,%d,aggregate,%lu,%.6f,%.9f,%d\n",
            names[mode], bytes, reps, active, offset, max_cycles,
            (double)max_cycles / reps,
            max_cycles ? (double)bytes * reps * active / max_cycles : 0.0,
            failed);
    if (fflush(output) != 0 || ferror(output)) {
        perror("writing DMA CSV");
        return 1;
    }
    stage("host.print.done");
    return failed ? 1 : 0;
}

static int save_case(dma_context_t *ctx, const char *out, int smoke,
                     int mode, int bytes, int reps, int active, int offset)
{
    size_t capacity = strlen(out) + 128;
    char *path = malloc(capacity);
    FILE *file;
    int rc;
    if (!path) { fprintf(stderr, "path allocation failed\n"); return 1; }
    if (smoke)
        snprintf(path, capacity, "%s/smoke/%s_%dpe.csv", out, names[mode], active);
    else
        snprintf(path, capacity, "%s/raw/dma_%s_%dpe_%dB_offset%d.csv",
                 out, names[mode], active, bytes, offset);
    file = fopen(path, "w");
    if (!file) { perror(path); free(path); return 1; }
    printf("DMA %s bytes=%d reps=%d active=%d offset=%d\n",
           names[mode], bytes, reps, active, offset);
    fflush(stdout);
    rc = run_one(ctx, mode, bytes, reps, active, offset, file);
    if (fclose(file) != 0) { perror(path); rc = 1; }
    if (rc) fprintf(stderr, "DMA_CASE_FAILED %s\n", path);
    free(path);
    return rc;
}

static int metadata(const char *out)
{
    size_t capacity = strlen(out) + 32;
    char *path = malloc(capacity);
    const char *host = getenv("HOSTNAME"), *job = getenv("LSB_JOBID");
    FILE *file, *cpu;
    char buffer[4096];
    size_t n;
    int rc = 0;
    if (!path) return 1;
    snprintf(path, capacity, "%s/compute.txt", out);
    file = fopen(path, "w");
    if (!file) { perror(path); free(path); return 1; }
    if (fprintf(file, "capacity_bytes=%d\nhostname_environment=%s\njob_id_environment=%s\n",
                BENCH_MAX_BYTES, host ? host : "unknown", job ? job : "unknown") < 0)
        rc = 1;
    if (fclose(file) != 0) rc = 1;
    cpu = fopen("/proc/cpuinfo", "r");
    if (cpu) {
        snprintf(path, capacity, "%s/cpuinfo.txt", out);
        file = fopen(path, "w");
        if (!file) { perror(path); fclose(cpu); free(path); return 1; }
        while ((n = fread(buffer, 1, sizeof(buffer), cpu)) != 0)
            if (fwrite(buffer, 1, n, file) != n) { rc = 1; break; }
        if (ferror(cpu)) rc = 1;
        if (fclose(file) != 0) rc = 1;
        if (fclose(cpu) != 0) rc = 1;
    }
    free(path);
    return rc;
}

static int sweep(dma_context_t *ctx, const char *out, int *completed)
{
    static const int sizes[] = {8,16,32,64,128,256,512,1024,2048,4096,
                                8192,16384,32768,65536};
    static const int actives[] = {1,64};
    int mode, ai, offset, si, bytes, reps;
    *completed = 0;
    if (metadata(out)) return 1;
    for (mode = 0; mode < 4; ++mode)
        for (ai = 0; ai < 2; ++ai)
            if (save_case(ctx, out, 1, mode, 8, 10, actives[ai], 0)) return 1;
    printf("All eight correctness checks passed. Starting DMA sweep.\n");
    fflush(stdout);
    for (mode = 0; mode < 4; ++mode)
        for (ai = 0; ai < 2; ++ai)
            for (offset = 0; offset <= 4; offset += 4)
                for (si = 0; si < (int)(sizeof(sizes) / sizeof(sizes[0])); ++si) {
                    bytes = sizes[si];
                    if (bytes > BENCH_MAX_BYTES) continue;
                    reps = bytes < 1024 ? 10000 : 1000;
                    if (save_case(ctx, out, 0, mode, bytes, reps, actives[ai], offset))
                        return 1;
                    ++*completed;
                }
    return 0;
}

static int mark_complete(const char *out, int completed)
{
    size_t capacity = strlen(out) + 32;
    char *path = malloc(capacity);
    FILE *file;
    int rc = 0;
    if (!path) return 1;
    snprintf(path, capacity, "%s/RUN_COMPLETE", out);
    file = fopen(path, "w");
    if (!file) { perror(path); free(path); return 1; }
    if (fprintf(file, "completed_cases=%d\n", completed) < 0) rc = 1;
    if (fclose(file) != 0) rc = 1;
    if (rc) perror(path);
    free(path);
    return rc;
}

int main(int argc, char **argv)
{
    dma_context_t ctx = {0};
    int i, mode = -1, bytes = 0, reps = 0, active = 0, offset = 0;
    int rc, completed = 0;
    int is_sweep = argc == 3 && !strcmp(argv[1], "--sweep");
    stage("host.enter");
    if (!is_sweep) {
        if (argc != 6) {
            fprintf(stderr, "usage: %s get|put|iget|iput bytes reps active_pes(1|64) offset(0|4)\n"
                            "       %s --sweep output_directory\n", argv[0], argv[0]);
            return 2;
        }
        for (i = 0; i < 4; ++i) if (!strcmp(argv[1], names[i])) mode = i;
        bytes = number(argv[2], 4, BENCH_MAX_BYTES);
        reps = number(argv[3], 1, 1000000);
        active = number(argv[4], 1, BENCH_PES);
        offset = number(argv[5], 0, 4);
        if (mode < 0 || bytes < 0 || (bytes & 3) || reps < 0 ||
            (active != 1 && active != 64) || (offset != 0 && offset != 4)) {
            fprintf(stderr, "invalid arguments (bytes must be a multiple of 4)\n");
            return 2;
        }
    }
    rc = prepare(&ctx);
    if (!rc) {
        if (is_sweep) rc = sweep(&ctx, argv[2], &completed);
        else rc = run_one(&ctx, mode, bytes, reps, active, offset, stdout);
    }
    release(&ctx);
    if (!rc && is_sweep) {
        rc = mark_complete(argv[2], completed);
        if (!rc) printf("DMA process completed: %d sweep cases.\n", completed);
    }
    return rc;
}
