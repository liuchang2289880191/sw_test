/* Native batch driver: no compute-node shell or child executable. */
#ifndef RMA_CLUSTER_SUITE_H
#define RMA_CLUSTER_SUITE_H
#include <ctype.h>
#include <time.h>
#ifndef _WIN32
#include <unistd.h>
#endif

static int capture_resources(const char *out)
{
    char path[4096], line[512];
    FILE *f, *cpu;
    if (snprintf(path, sizeof(path), "%s/resource_runtime.txt", out) >= (int)sizeof(path)) return 1;
    f = fopen(path, "w");
    if (!f) { perror(path); return 1; }
    fprintf(f, "start_time_epoch=%ld\n", (long)time(NULL));
#ifndef _WIN32
    {
        char host[256] = {0};
        if (!gethostname(host, sizeof(host)-1)) fprintf(f, "compute_hostname=%s\n", host);
    }
#endif
    fprintf(f, "resource_exclusivity=unknown\nactual_cache_ldm_configuration=not_detected\n");
    cpu = fopen("/proc/cpuinfo", "r");
    if (cpu) {
        fprintf(f, "\n[compute_node_cpuinfo]\n");
        while (fgets(line, sizeof(line), cpu)) fputs(line, f);
        fclose(cpu);
    } else fprintf(f, "cpuinfo=unavailable\n");
    { int status = ferror(f); if (fclose(f)) status = 1; return status; }
}

static int safe_id(const char *s)
{
    if (!*s) return 0;
    for (; *s; ++s)
        if (!isalnum((unsigned char)*s) && *s != '_') return 0;
    return 1;
}

static int run_suite(const char *plan_path, const char *out)
{
    FILE *plan = fopen(plan_path, "r"), *csv, *done;
    char line[512], phase[16], id[64], type[16], name[32], extra;
    char path[4096], num[6][24], *args[8];
    int src, dst, bytes, reps, window, cluster, argc, status, count = 0;
    if (!plan) { perror(plan_path); return 1; }
    if (capture_resources(out)) { fclose(plan); return 1; }
    while (fgets(line, sizeof(line), plan)) {
        if (line[0] == '#') continue;
        if (!strchr(line, '\n') && !feof(plan)) goto invalid;
        if (sscanf(line, "%15s %63s %15s %31s %d %d %d %d %d %d %c",
                   phase, id, type, name, &src, &dst, &bytes, &reps,
                   &window, &cluster, &extra) != 10) goto invalid;
        if ((strcmp(phase, "smoke") && strcmp(phase, "raw")) || !safe_id(id)) goto invalid;
        snprintf(num[0], 24, "%d", src); snprintf(num[1], 24, "%d", dst);
        snprintf(num[2], 24, "%d", bytes); snprintf(num[3], 24, "%d", reps);
        snprintf(num[4], 24, "%d", window); snprintf(num[5], 24, "%d", cluster);
        args[0] = "rma_cluster_bench"; args[1] = type;
        if (!strcmp(type, "latency")) {
            args[2] = num[2]; args[3] = num[3]; argc = 4;
        } else if (!strcmp(type, "bandwidth")) {
            args[2] = num[0]; args[3] = num[1]; args[4] = num[2];
            args[5] = num[3]; args[6] = num[4]; argc = 7;
        } else if (!strcmp(type, "contention")) {
            args[2] = name; args[3] = num[2]; args[4] = num[3];
            args[5] = num[4]; args[6] = num[5]; argc = 7;
        } else goto invalid;
        if (snprintf(path, sizeof(path), "%s/%s/%s.csv", out, phase, id) >= (int)sizeof(path)) goto invalid;
        csv = fopen(path, "w");
        if (!csv) { perror(path); fclose(plan); return 1; }
        fprintf(stderr, "RMA_CASE %d %s %s %s bytes=%d reps=%d window=%d cluster=%d time=%ld\n",
                count + 1, phase, id, type, bytes, reps, window, cluster, (long)time(NULL));
        fflush(stderr);
        status = run_case(argc, args, csv);
        if (fclose(csv) != 0) status = 1;
        if (status) {
            fprintf(stderr, "RMA_FAILED %s; stopped before subsequent cases\n", id);
            fclose(plan); return status;
        }
        ++count;
    }
    status = ferror(plan); fclose(plan);
    if (status || !count) { fprintf(stderr, "empty/unreadable RMA plan\n"); return 2; }
    if (runtime_ready) { athread_halt(); runtime_ready = 0; }
    if (snprintf(path, sizeof(path), "%s/RUN_COMPLETE", out) >= (int)sizeof(path)) return 2;
    done = fopen(path, "w");
    if (!done) { perror(path); return 1; }
    status = fprintf(done, "completed_cases=%d\n", count) < 0;
    if (fclose(done) != 0) status = 1;
    fprintf(stderr, "RMA process completed: %d cases.\n", count);
    return status;
invalid:
    fprintf(stderr, "invalid RMA plan after %d cases: %s", count, line);
    fclose(plan); return 2;
}
#endif
