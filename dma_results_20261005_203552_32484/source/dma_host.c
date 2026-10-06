#define _POSIX_C_SOURCE 200112L
#include <athread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <errno.h>
#include "bench_common.h"

extern void SLAVE_FUN(dma_kernel)();
static const char *names[] = {"get", "put", "iget", "iput"};

typedef struct {
    dma_args_t args;
    unsigned char *src, *dst;
    unsigned long *cycles;
    int *errors;
    int initialized;
    int alloc_stride, stride, mapping, extended;
    unsigned int mapping_seed;
} dma_context_t;

static const char *mapping_names[] = {"identity", "reverse", "transpose", "shuffle"};

static int max_study_stride(void)
{
    int stride = 2 * DMA_MAX_BYTES;
    return stride > DMA_MAX_BYTES + 4096 ? stride : DMA_MAX_BYTES + 4096;
}

/* Explicit 32-bit arithmetic makes the permutation reproducible across hosts. */
static uint32_t random_step(uint32_t *state)
{
    *state ^= *state << 13;
    *state ^= *state >> 17;
    *state ^= *state << 5;
    return *state;
}

static void configure_slots(dma_context_t *ctx)
{
    int i, j, temp;
    uint32_t state = ctx->mapping_seed;
    ctx->args.slot_stride = ctx->stride;
    for (i = 0; i < BENCH_PES; ++i) {
        if (ctx->mapping == 1) ctx->args.slot_of_pe[i] = 63 - i;
        else if (ctx->mapping == 2) ctx->args.slot_of_pe[i] = (i % 8) * 8 + i / 8;
        else ctx->args.slot_of_pe[i] = i;
    }
    if (ctx->mapping == 3)
        for (i = 63; i > 0; --i) {
            j = (int)(random_step(&state) % (uint32_t)(i + 1));
            temp = ctx->args.slot_of_pe[i];
            ctx->args.slot_of_pe[i] = ctx->args.slot_of_pe[j];
            ctx->args.slot_of_pe[j] = temp;
        }
}

/* Diagnostics use stderr and execute outside the CPE timed loop. */
static void stage(const char *name)
{
    fprintf(stderr, "DMA_STAGE %s\n", name);
    fflush(stderr);
}

static int number(const char *s, int min, int max)
{
    char *end;
    long v;
    errno = 0;
    v = strtol(s, &end, 10);
    if (errno || !*s || *end || v < min || v > max) return -1;
    return (int)v;
}

static int prepare(dma_context_t *ctx)
{
    int rc;
    size_t total = (size_t)BENCH_PES * ctx->alloc_stride;
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
    fprintf(stderr, "DMA_ADDRESSES src=%p dst=%p cycles=%p errors=%p allocation_stride=%d\n",
            (void *)ctx->src, (void *)ctx->dst, (void *)ctx->cycles,
            (void *)ctx->errors, ctx->alloc_stride);
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
    size_t total = (size_t)BENCH_PES * ctx->alloc_stride;
    int i, j, rc, failed = 0;
    a->mode = mode; a->bytes = bytes; a->reps = reps;
    a->active = active; a->offset = offset;
    if (ctx->stride < bytes + offset || ctx->stride % 128 ||
        ctx->stride > ctx->alloc_stride || ctx->mapping < 0 || ctx->mapping > 3) {
        fprintf(stderr, "invalid slot layout\n");
        return 1;
    }
    configure_slots(ctx);
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
            ctx->src[(size_t)a->slot_of_pe[i] * ctx->stride + offset + j] =
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
                if (ctx->dst[(size_t)a->slot_of_pe[i] * ctx->stride + offset + j] !=
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
    fprintf(output, "benchmark,mode,bytes,reps,active_pes,offset,pe,cycles,cycles_per_op,aggregate_bytes_per_cycle,errors");
    if (ctx->extended)
        fprintf(output, ",slot_stride,mapping,mapping_seed,slot,src_address,dst_address");
    fprintf(output, "\n");
    for (i = 0; i < active; ++i) {
        fprintf(output, "dma,%s,%d,%d,%d,%d,%d,%lu,%.6f,,%d",
                names[mode], bytes, reps, active, offset, i, ctx->cycles[i],
                (double)ctx->cycles[i] / reps, ctx->errors[i]);
        if (ctx->extended)
            fprintf(output, ",%d,%s,%u,%d,%p,%p", ctx->stride,
                    mapping_names[ctx->mapping], ctx->mapping_seed, a->slot_of_pe[i],
                    (void *)(ctx->src + (size_t)a->slot_of_pe[i] * ctx->stride + offset),
                    (void *)(ctx->dst + (size_t)a->slot_of_pe[i] * ctx->stride + offset));
        fprintf(output, "\n");
    }
    fprintf(output, "dma,%s,%d,%d,%d,%d,aggregate,%lu,%.6f,%.9f,%d",
            names[mode], bytes, reps, active, offset, max_cycles,
            (double)max_cycles / reps,
            max_cycles ? (double)bytes * reps * active / max_cycles : 0.0,
            failed);
    if (ctx->extended)
        fprintf(output, ",%d,%s,%u,,,", ctx->stride,
                mapping_names[ctx->mapping], ctx->mapping_seed);
    fprintf(output, "\n");
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
                DMA_MAX_BYTES, host ? host : "unknown", job ? job : "unknown") < 0)
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
                    if (bytes > DMA_MAX_BYTES) continue;
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

/* The same enumerator writes the complete plan and executes it later. */
static int study_case(dma_context_t *ctx, const char *out, FILE *plan,
                      const char *phase, int mode, int bytes, int active,
                      int offset, int stride, int mapping, int *count)
{
    int reps = bytes < 1024 ? 10000 : 1000, rc;
    char filename[40];
    char *path;
    FILE *file;
    if (bytes > DMA_MAX_BYTES) return 0;
    ++*count;
    snprintf(filename, sizeof(filename), "case_%06d.csv", *count);
    if (plan)
        return fprintf(plan, "%d,%s,%s,%d,%d,%d,%d,%d,%s,%u,%s\n",
                       *count, phase, names[mode], bytes, reps, active, offset,
                       stride, mapping_names[mapping], ctx->mapping_seed,
                       filename) < 0;
    path = malloc(strlen(out) + 64);
    if (!path) return 1;
    sprintf(path, "%s/raw/%s", out, filename);
    file = fopen(path, "w");
    if (!file) { perror(path); free(path); return 1; }
    ctx->stride = stride;
    ctx->mapping = mapping;
    printf("DMA_STUDY case=%d phase=%s mode=%s bytes=%d active=%d offset=%d stride=%d mapping=%s\n",
           *count, phase, names[mode], bytes, active, offset, stride, mapping_names[mapping]);
    fflush(stdout);
    rc = run_one(ctx, mode, bytes, reps, active, offset, file);
    if (fclose(file)) rc = 1;
    if (rc) fprintf(stderr, "DMA_CASE_FAILED %s\n", path);
    free(path);
    return rc;
}

static int walk_study(dma_context_t *ctx, const char *out, FILE *plan, int *count)
{
    static const int boundary[] = {64,96,124,128,132,192,252,256,260};
    static const int load[] = {8,16,32,64,96,124,128,132,192,252,256,260,384,512,768,
        1024,1536,2048,3072,4096,6144,8192,12288,16384,24576,32768,49152,65536,98304,131072};
    static const int mapped[] = {64,128,256,4096,32768,65536,98304,131072};
    static const int actives[] = {1,2,4,8,16,32,64};
    static const int offsets[] = {0,4,64,124};
    int strides[] = {DMA_SLOT_BYTES, DMA_MAX_BYTES+256, DMA_MAX_BYTES+4096, 2*DMA_MAX_BYTES};
    int phase, mode, ai, oi, si, ti, mi, earlier, duplicate, nsize;
    const int *sizes;
    const char *phases[] = {"boundary", "load", "mapping"};
    *count = 0;
    for (phase = 0; phase < 3; ++phase) {
        sizes = phase == 0 ? boundary : phase == 1 ? load : mapped;
        nsize = phase == 0 ? sizeof(boundary)/sizeof(*boundary) :
                phase == 1 ? sizeof(load)/sizeof(*load) : sizeof(mapped)/sizeof(*mapped);
        for (mode = 0; mode < 4; ++mode)
            for (ai = 0; ai < 7; ++ai)
                for (oi = 0; oi < (phase == 0 ? 4 : 2); ++oi)
                    for (si = 0; si < nsize; ++si)
                        for (ti = 0; ti < (phase == 2 ? 4 : 1); ++ti) {
                            duplicate = 0;
                            for (earlier = 0; earlier < ti; ++earlier)
                                if (strides[earlier] == strides[ti]) duplicate = 1;
                            if (duplicate) continue;
                            for (mi = 0; mi < (phase == 2 ? 4 : 1); ++mi)
                                if (study_case(ctx, out, plan, phases[phase], mode, sizes[si],
                                    actives[ai], offsets[oi], strides[ti], mi, count)) return 1;
                        }
    }
    return 0;
}

static int write_plan(dma_context_t *ctx, const char *path)
{
    int count, rc;
    FILE *file = fopen(path, "w");
    if (!file) { perror(path); return 1; }
    rc = fprintf(file, "case_id,phase,mode,bytes,reps,active_pes,offset,slot_stride,mapping,mapping_seed,filename\n") < 0;
    if (!rc) rc = walk_study(ctx, NULL, file, &count);
    if (fclose(file)) rc = 1;
    if (!rc) printf("DMA study plan: %d cases, capacity=%d B.\n", count, DMA_MAX_BYTES);
    return rc;
}

static int study(dma_context_t *ctx, const char *out, int *completed)
{
    char *path = malloc(strlen(out)+40);
    FILE *file;
    int mode, ai, pe, rc;
    if (!path) return 1;
    sprintf(path, "%s/plan.csv", out);
    rc = write_plan(ctx, path);
    if (rc) { free(path); return rc; }
    sprintf(path, "%s/slot_maps.csv", out);
    file = fopen(path, "w");
    if (!file) { perror(path); free(path); return 1; }
    rc = fprintf(file, "mapping,mapping_seed,pe,slot\n") < 0;
    for (mode = 0; mode < 4; ++mode) {
        ctx->mapping = mode;
        configure_slots(ctx);
        for (pe = 0; pe < BENCH_PES; ++pe)
            if (fprintf(file, "%s,%u,%d,%d\n", mapping_names[mode], ctx->mapping_seed,
                        pe, ctx->args.slot_of_pe[pe]) < 0) rc = 1;
    }
    if (fclose(file)) rc = 1;
    free(path);
    ctx->mapping = 0;
    ctx->stride = DMA_SLOT_BYTES;
    if (rc || metadata(out)) return 1;
    for (mode = 0; mode < 4; ++mode)
        for (ai = 0; ai < 2; ++ai)
            if (save_case(ctx, out, 1, mode, 8, 10, ai ? 64 : 1, 0)) return 1;
    printf("All eight correctness checks passed. Starting DMA study.\n");
    return walk_study(ctx, out, NULL, completed);
}

int main(int argc, char **argv)
{
    dma_context_t ctx = {0};
    int i, mode = -1, bytes = 0, reps = 0, active = 0, offset = 0;
    int rc, completed = 0;
    int is_sweep = argc == 3 && !strcmp(argv[1], "--sweep");
    int is_study = (argc == 3 || argc == 4) && !strcmp(argv[1], "--study");
    int is_plan = (argc == 3 || argc == 4) && !strcmp(argv[1], "--plan-study");
    ctx.alloc_stride = ctx.stride = DMA_SLOT_BYTES;
    ctx.mapping_seed = 20261005;
    stage("host.enter");
    if (is_study || is_plan) {
        if (DMA_MAX_BYTES < 512) { fprintf(stderr, "study requires capacity >= 512 B\n"); return 2; }
        if (argc == 4) {
            i = number(argv[3], 1, 2147483647);
            if (i < 0) { fprintf(stderr, "invalid mapping seed\n"); return 2; }
            ctx.mapping_seed = (unsigned int)i;
        }
        ctx.extended = 1;
        ctx.alloc_stride = max_study_stride();
        if (is_plan) return write_plan(&ctx, argv[2]);
    } else if (!is_sweep) {
        if (argc != 6 && argc != 9) {
            fprintf(stderr, "usage: %s get|put|iget|iput bytes reps active_pes(1..64) offset(0..124) [stride mapping seed]\n"
                            "       %s --sweep output_directory\n"
                            "       %s --study output_directory [seed]\n"
                            "       %s --plan-study plan.csv [seed]\n", argv[0], argv[0], argv[0], argv[0]);
            return 2;
        }
        for (i = 0; i < 4; ++i) if (!strcmp(argv[1], names[i])) mode = i;
        bytes = number(argv[2], 4, DMA_MAX_BYTES);
        reps = number(argv[3], 1, 1000000);
        active = number(argv[4], 1, BENCH_PES);
        offset = number(argv[5], 0, 124);
        if (mode < 0 || bytes < 0 || (bytes & 3) || reps < 0 ||
            active < 0 || offset < 0 || offset % 4) {
            fprintf(stderr, "invalid arguments (bytes must be a multiple of 4)\n");
            return 2;
        }
        if (argc == 9) {
            ctx.stride = number(argv[6], 128, max_study_stride());
            ctx.mapping = -1;
            for (i = 0; i < 4; ++i) if (!strcmp(argv[7], mapping_names[i])) ctx.mapping = i;
            i = number(argv[8], 1, 2147483647);
            if (ctx.stride < bytes + offset || ctx.stride % 128 || ctx.mapping < 0 || i < 0) {
                fprintf(stderr, "invalid stride, mapping or seed\n"); return 2;
            }
            ctx.mapping_seed = (unsigned int)i;
            ctx.alloc_stride = ctx.stride;
            ctx.extended = 1;
        }
    }
    rc = prepare(&ctx);
    if (!rc) {
        if (is_study) rc = study(&ctx, argv[2], &completed);
        else if (is_sweep) rc = sweep(&ctx, argv[2], &completed);
        else rc = run_one(&ctx, mode, bytes, reps, active, offset, stdout);
    }
    release(&ctx);
    if (!rc && (is_sweep || is_study)) {
        rc = mark_complete(argv[2], completed);
        if (!rc) printf("DMA process completed: %d sweep cases.\n", completed);
    }
    return rc;
}
