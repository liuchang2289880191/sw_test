"""Local address/layout and launcher checks using a fake runtime; no Sunway execution.

Run with Python 3, a local GCC and Bash/awk:
  python bench/tests/verify_dma_study.py --gcc /path/to/gcc --bash /path/to/bash
All generated binaries and synthetic timings live in a temporary directory.
"""
import argparse
import csv
import os
from pathlib import Path
import subprocess
import tempfile

BENCH = Path(__file__).resolve().parents[1]
HEADER = r'''
#ifndef MOCK_ATHREAD_H
#define MOCK_ATHREAD_H
#include <stdlib.h>
#include <stddef.h>
#define SLAVE_FUN(x) x
void *mock_malloc(size_t);
void mock_free(void *);
int mock_posix_memalign(void **, size_t, size_t);
#define malloc mock_malloc
#define free mock_free
#define posix_memalign mock_posix_memalign
int athread_init(void);
int athread_halt(void);
int athread_spawn(void (*)(), void *);
int athread_join(void);
#endif
'''
SLAVE_HEADER = r'''
#include "athread.h"
#define __thread_local
typedef volatile unsigned long athread_rply_t;
extern int mock_tid;
#define _PEN mock_tid
int athread_dma_get(void *, const void *, size_t);
int athread_dma_put(void *, const void *, size_t);
int athread_dma_iget(void *, const void *, size_t, athread_rply_t *);
int athread_dma_iput(void *, const void *, size_t, athread_rply_t *);
void athread_dma_wait_value(athread_rply_t *, unsigned long);
void athread_ssync_array(void);
unsigned long athread_stime_cycle(void);
'''
RUNTIME = r'''
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#ifdef _WIN32
#include <malloc.h>
#endif
#include "bench_common.h"
#include "slave.h"
#undef malloc
#undef free
#undef posix_memalign
void *mock_malloc(size_t n) {
#ifdef _WIN32
    return _aligned_malloc(n,128);
#else
    void *p=NULL; if(posix_memalign(&p,128,n)) return NULL; return p;
#endif
}
void mock_free(void *p) {
#ifdef _WIN32
    _aligned_free(p);
#else
    free(p);
#endif
}
int mock_posix_memalign(void **p,size_t align,size_t n) {
    if(align!=128) abort(); *p=mock_malloc(n); return !*p;
}
int mock_tid, initialized, spawns;
static unsigned long ticks;
int athread_init(void) { if(initialized++) abort(); return 0; }
int athread_halt(void) { if(initialized!=1) abort(); initialized=0; return 0; }
int athread_join(void) { return 0; }
int athread_dma_get(void *d,const void *s,size_t n) { memcpy(d,s,n); ticks++; return 0; }
int athread_dma_put(void *d,const void *s,size_t n) { memcpy(d,s,n); ticks++; return 0; }
int athread_dma_iget(void *d,const void *s,size_t n,athread_rply_t *r) { memcpy(d,s,n); (*r)++; ticks++; return 0; }
int athread_dma_iput(void *d,const void *s,size_t n,athread_rply_t *r) { memcpy(d,s,n); (*r)++; ticks++; return 0; }
void athread_dma_wait_value(athread_rply_t *r,unsigned long n) { if(*r!=n) abort(); }
void athread_ssync_array(void) { }
unsigned long athread_stime_cycle(void) { return ticks; }
int athread_spawn(void (*kernel)(),void *v) {
    dma_args_t *a=v;
    int i,j,seen[64]={0}; unsigned char expected,*src,*dst;
    char *fail=getenv("MOCK_DMA_FAIL_AT");
    if(initialized!=1 || a->active<1 || a->active>64 ||
       a->slot_stride<a->bytes+a->offset || a->slot_stride%128) abort();
    ++spawns;
    for(i=0;i<64;i++) {
        if(a->slot_of_pe[i]<0 || a->slot_of_pe[i]>=64 || seen[a->slot_of_pe[i]]++) abort();
        src=(unsigned char *)a->src+(size_t)a->slot_of_pe[i]*a->slot_stride+a->offset;
        dst=(unsigned char *)a->dst+(size_t)a->slot_of_pe[i]*a->slot_stride+a->offset;
        for(j=0;j<a->bytes;j++) {
            expected=(unsigned char)((i*17+j*13+7)&255);
            if(src[j]!=expected) abort();
            if(i<a->active && (a->mode==1 || a->mode==3) && !getenv("MOCK_REAL_SLAVE")) dst[j]=expected;
        }
        if(getenv("MOCK_REAL_SLAVE")) { mock_tid=i; kernel(a); }
        else { a->cycles[i]=i<a->active?a->reps*(100+i):0; a->errors[i]=0; }
    }
    if(fail && spawns==atoi(fail)) a->errors[0]=1;
    return 0;
}
'''


def rows(path):
    with path.open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gcc", required=True)
    parser.add_argument("--bash", default="bash")
    args = parser.parse_args()
    env = os.environ.copy()
    env["PATH"] = str(Path(args.gcc).parent) + os.pathsep + env.get("PATH", "")
    for key in ("DMA_PROFILE", "DMA_MAX_BYTES", "BENCH_MAX_BYTES", "DMA_MAPPING_SEED", "DMA_CACHE_SIZE", "DMA_DIAG_ONLY", "MOCK_DMA_FAIL_AT", "MOCK_REAL_SLAVE"):
        env.pop(key, None)

    def run(cmd, *, expect=0, extra=None):
        result = subprocess.run(list(map(str, cmd)), env=dict(env, **(extra or {})),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != expect:
            raise AssertionError(f"{cmd}: exit {result.returncode}\n{result.stdout[-2000:]}\n{result.stderr[-2000:]}")
        return result

    with tempfile.TemporaryDirectory(prefix="dma_local_mock_") as temp:
        root = Path(temp)
        (root / "athread.h").write_text(HEADER, encoding="utf-8")
        (root / "slave.h").write_text(SLAVE_HEADER, encoding="utf-8")
        (root / "runtime.c").write_text(RUNTIME, encoding="utf-8")
        executables = {}
        for cap in (512, 4096, 65536, 131072):
            exe = root / f"mock_{cap}.exe"
            run([args.gcc, "-std=c99", "-O2", "-Wall", "-Wextra", f"-DDMA_MAX_BYTES={cap}",
                 "-I", root, "-I", BENCH, BENCH / "dma_host.c", BENCH / "dma_slave.c", root / "runtime.c", "-o", exe])
            executables[cap] = exe
            plan = root / f"plan_{cap}.csv"
            run([exe, "--plan-study", plan])
            data = rows(plan)
            expected = {512:4480, 4096:4816, 65536:7952, 131072:9856}[cap]
            assert len(data) == expected
            assert len({tuple(d.values())[1:-1] for d in data}) == expected
            assert max(int(d["bytes"]) for d in data) == cap
            assert {int(d["active_pes"]) for d in data} == {1,2,4,8,16,32,64}
        print("PASS: syntax and study plans at 512 B, 4/64/128 KiB; unique cases and capacity filtering")

        # Exercise the actual slave address calculation and byte validation through fake memcpy APIs.
        for mode in ("get", "put", "iget", "iput"):
            for mapping in ("identity", "reverse", "transpose", "shuffle"):
                result = run([executables[131072], mode, 131072, 3, 2, 124, 262144, mapping, 20261005], extra={"MOCK_REAL_SLAVE":"1"})
                assert "aggregate" in result.stdout
                assert result.stdout.splitlines()[-1].split(",")[10] == "0"
        legacy = run([executables[65536], "get", 8, 10, 1, 0], extra={"MOCK_REAL_SLAVE":"1"})
        assert len(legacy.stdout.splitlines()[0].split(",")) == 11
        run([executables[65536], "put", 128, 10, 2, 124, 128, "identity", 1], expect=2)
        print("PASS: actual DMA slave code with mocked transfers; four modes, four maps, 128 KiB+124 B; legacy schema")

        def study_dir(name):
            out = root / name
            out.mkdir()
            (out/"raw").mkdir(); (out/"smoke").mkdir()
            return out

        out = study_dir("study")
        run([executables[512], "--study", out])
        assert len(list((out/"raw").glob("*.csv"))) == 4480
        collector = [args.bash, "-c", 'awk -v out="$1" -v capacity=512 -v seed=20261005 -f "$2" "$1/plan.csv"', "mock", out.as_posix(), (BENCH/"collect_dma_study.awk").as_posix()]
        run(collector)
        assert len(rows(out/"study_summary.csv")) == 4480
        assert len(rows(out/"study_scaling.csv")) == 3840
        assert (out/"COMPLETE").exists()
        # A corrupt address must be rejected before marking the result complete.
        corrupt = out / "raw/case_000001.csv"
        original = corrupt.read_text()
        lines = original.splitlines()
        fields = lines[1].split(","); fields[15] = "0x1"; lines[1] = ",".join(fields)
        corrupt.write_text("\n".join(lines)+"\n")
        (out/"COMPLETE").unlink()
        run(collector, expect=1)
        assert not (out/"COMPLETE").exists()
        corrupt.write_text(original)
        # Failure in the first formal case stops and leaves no completion marker.
        failed_out = study_dir("failed")
        run([executables[512], "--study", failed_out], expect=1, extra={"MOCK_DMA_FAIL_AT":"9"})
        assert len(list((failed_out/"raw").glob("*.csv"))) == 1
        assert not (failed_out/"RUN_COMPLETE").exists()
        print("PASS: complete 4480-case mocked host study, aggregation, address-corruption rejection and stop-on-error")

        for name in ("run_dma.sh", "run_dma_boundary.sh"):
            run([args.bash, "-n", BENCH/name])
        # Fake compiler/scheduler run only on the local PC, with explicit mock names.
        shim = root / "bin"; shim.mkdir()
        compiler = shim / "mock_swgcc"
        compiler.write_text('#!/usr/bin/env bash\nset -e\ncase "$1" in\n-dumpmachine) echo sw_64_mock_only;;\n-v) echo "LOCAL MOCK COMPILER";;\n*) last="${@: -1}"; if [[ "$last" == *.o ]]; then touch "$last"; else cp "$MOCK_EXE" "$last"; fi;;\nesac\n')
        scheduler = shim / "bsub"
        scheduler.write_text('#!/usr/bin/env bash\nset -e\n[[ "$1" == -I ]]; shift\nwhile [[ "$1" == -* ]]; do shift 2; done\nexec "$@"\n')
        compiler.chmod(0o755); scheduler.chmod(0o755)
        wrapper_out = root/"wrapper_study"
        bash_path = run([args.bash, "-c", "printf '%s' \"$PATH\""]).stdout
        mock_env = {"PATH":shim.as_posix()+":"+bash_path, "SWCC":"mock_swgcc", "DMA_MAX_BYTES":"512", "MOCK_EXE":executables[512].as_posix()}
        run([args.bash, BENCH/"run_dma_boundary.sh", "mock_queue", wrapper_out.as_posix()], extra=mock_env)
        assert (wrapper_out/"COMPLETE").exists()
        assert len(rows(wrapper_out/"study_summary.csv")) == 4480
        baseline_out = root/"wrapper_baseline"
        run([args.bash, BENCH/"run_dma.sh", "mock_queue", baseline_out.as_posix()], extra=mock_env)
        assert len(rows(baseline_out/"summary.csv")) == 112
        print("PASS: both launchers through fake compiler and scheduler; no Sunway job was submitted")


if __name__ == "__main__":
    main()
