"""Local launcher/CSV/failure checks. Synthetic timings; no Sunway execution.

python bench/tests/verify_rma_launcher.py --gcc /path/to/gcc --bash /path/to/bash
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
int mock_posix_memalign(void **,size_t,size_t);
void mock_free(void *);
#define posix_memalign mock_posix_memalign
#define free mock_free
int athread_init(void);
void athread_halt(void);
int athread_spawn(void (*)(),void *);
int athread_join(void);
#endif
'''
RUNTIME = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <malloc.h>
#endif
#include "bench_common.h"
static int initialized,spawns;
int mock_posix_memalign(void **p,size_t align,size_t n) {
#ifdef _WIN32
    *p=_aligned_malloc(n,align); return !*p;
#else
    return posix_memalign(p,align,n);
#endif
}
void mock_free(void *p) {
#ifdef _WIN32
    _aligned_free(p);
#else
    free(p);
#endif
}
int athread_init(void) {if(initialized++) abort(); return 0;}
void athread_halt(void) {if(initialized!=1) abort(); initialized=0;}
int athread_join(void) {return 0;}
void cluster_kernel(void) {}
int athread_spawn(void (*kernel)(),void *v) {
    cluster_args_t *a=v;
    int i,j,f,incoming[64]={0},active[64]={0};
    char *fail=getenv("MOCK_RMA_FAIL_AT"),*zero=getenv("MOCK_RMA_ZERO_AT");
    (void)kernel;
    if(initialized!=1 || (size_t)v%128 || a->reps<1) abort();
    spawns++;
    if(a->mode==0) {
        for(i=0;i<64;i++) for(j=0;j<64;j++) if(i!=j)
            a->cycles[i*64+j]=2UL*a->reps*(100+abs(i/8-j/8)+abs(i%8-j%8));
        if(fail && spawns==atoi(fail)) a->peer_errors[64]=1;
        if(zero && spawns==atoi(zero)) a->cycles[1]=0;
    } else {
        for(f=0;f<a->nflows;f++) {
            int src=a->flows[f].src,dst=a->flows[f].dst;
            if(src<0 || src>63 || dst<0 || dst>63 || src==dst ||
               a->flows[f].lane!=incoming[dst]++) abort();
            active[src]=active[dst]=1;
        }
        for(i=0;i<64;i++) {
            if((long long)incoming[i]*a->bytes*a->window>BENCH_MAX_BYTES) abort();
            if(active[i]) a->cycles[i]=1000UL+(unsigned long)a->bytes*a->reps+i;
        }
        for(i=0;i<64;i++) if(active[i]) {
            if(fail && spawns==atoi(fail)) a->errors[i]=1;
            if(zero && spawns==atoi(zero)) a->cycles[i]=0;
            break;
        }
    }
    return 0;
}
'''

def run(args, *, env=None, ok=True):
    result = subprocess.run(args, env=env, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=180)
    if ok and result.returncode:
        raise AssertionError(result.stdout)
    return result

def rows(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gcc", required=True)
    parser.add_argument("--bash", required=True)
    args = parser.parse_args()
    run([args.bash, "-n", str(BENCH / "run_rma.sh")])
    with tempfile.TemporaryDirectory(prefix="rma_launcher_") as tmp:
        root = Path(tmp)
        (root / "athread.h").write_text(HEADER, encoding="utf-8")
        (root / "runtime.c").write_text(RUNTIME, encoding="utf-8")
        exe = root / "mock_rma.exe"
        run([args.gcc, "-std=c99", "-Wall", "-Wextra", "-Werror", "-I", str(root),
             "-I", str(BENCH), str(BENCH / "rma_cluster_host.c"),
             str(root / "runtime.c"), "-o", str(exe)])
        shim = root / "shim"
        shim.mkdir()
        compiler = r'''#!/usr/bin/env bash
set -eu
case ${1:-} in -dumpmachine) echo sw_64_mock_only; exit;; -v) echo LOCAL_MOCK_ONLY; exit;; esac
output=; compile=0
while (($#)); do
  case $1 in -o) output=$2; shift 2;; -c) compile=1; shift;; *) shift;; esac
done
[[ -n "$output" ]]
if ((compile)); then : > "$output"; else cp "$MOCK_RMA_EXE" "$output"; chmod +x "$output"; fi
'''
        scheduler = r'''#!/usr/bin/env bash
set -eu
printf '%s\n' "$*" >> "$MOCK_SUBMISSIONS"
while (($#)); do
  case $1 in -I) shift;; -q|-n|-cgsp|-mpecg|-cache_size) shift 2;; *) break;; esac
done
[[ $1 != bash && $1 != sh && $1 != /bin/bash ]]
echo 'Job <LOCAL_MOCK_ONLY> submitted; synthetic data, no Sunway job.'
"$@"
'''
        for name, body in (("swgcc", compiler), ("bsub", scheduler)):
            path = shim / name
            path.write_text(body, encoding="utf-8", newline="\n")
            path.chmod(0o755)
        bash_path = run([args.bash, "-c", 'printf "%s" "$PATH"']).stdout
        env = {k: v for k, v in os.environ.items() if not k.startswith(("RMA_", "BENCH_", "SWCC", "SW_MODULE"))}
        env.update(PATH=shim.as_posix()+":"+bash_path, SWCC="swgcc",
                   MOCK_RMA_EXE=exe.as_posix(), MOCK_SUBMISSIONS=(root/"submissions.log").as_posix())

        def launch(label, **settings):
            out = root / label
            local = dict(env, **settings)
            result = run([args.bash, str(BENCH / "run_rma.sh"), "q_share", out.as_posix()], env=local, ok=False)
            return out, result, local

        full, result, local = launch("full")
        assert result.returncode == 0, result.stdout
        assert (full/"COMPLETE").exists()
        orders = []
        for i in range(1, 4):
            rep = full/f"repeat_{i:02d}"
            plan = rows(rep/"plan.csv")
            assert len(plan) == 566
            assert sum(r["phase"]=="smoke" for r in plan)==18
            assert sum(r["type"]=="latency" and r["phase"]=="raw" for r in plan)==6
            assert sum(r["type"]=="bandwidth" and r["phase"]=="raw" for r in plan)==414
            assert sum(r["type"]=="contention" and r["phase"]=="raw" for r in plan)==128
            orders.append([r["case_id"] for r in plan if r["phase"]=="raw"])
            assert (rep/"resource_runtime.txt").exists()
        assert set(orders[0])==set(orders[1])==set(orders[2])
        assert orders[0]!=orders[1]!=orders[2]
        assert len(rows(full/"latency.csv"))==3*7*4032
        assert len(rows(full/"summary.csv"))==3*(566-7)
        submissions=(root/"submissions.log").read_text().splitlines()
        assert len(submissions)==3 and all("--suite" in s and "-cache_size 0" in s for s in submissions)

        diag, result, _ = launch("diag", RMA_DIAG_ONLY="1")
        assert result.returncode==0, result.stdout
        assert len(rows(diag/"repeat_01"/"plan.csv"))==18
        assert not (diag/"repeat_02").exists()
        smaller, result, _ = launch("small", RMA_PROFILE="quick", RMA_REPEATS="1", BENCH_MAX_BYTES="32768")
        assert result.returncode==0, result.stdout
        for row in rows(smaller/"repeat_01"/"plan.csv"):
            if row["type"]!="latency":
                incoming=3 if row["case"] in ("incast3","alltoall4") else 1
                assert int(row["bytes"])*int(row["window"])*incoming<=32768
        for key in ("MOCK_RMA_FAIL_AT", "MOCK_RMA_ZERO_AT"):
            failed, result, _ = launch(key, **{key:"2"})
            assert result.returncode!=0
            assert not (failed/"COMPLETE").exists() and not (failed/"repeat_02").exists()
            assert len(list((failed/"repeat_01"/"smoke").glob("*.csv")))==2

        # A truncated or corrupted raw file must be rejected by the collector.
        raw=next((diag/"repeat_01"/"smoke").glob("bandwidth*.csv"))
        raw.write_text(raw.read_text().replace(",0\n", ",1\n", 1), encoding="utf-8", newline="\n")
        check=run([args.bash,"-c", 'awk -v out="$1" -f "$2" "$1/plan.csv"', "check",
                   (diag/"repeat_01").as_posix(), (BENCH/"collect_rma.awk").as_posix()], env=env, ok=False)
        assert check.returncode!=0
        bad, result, _=launch("bad_capacity", BENCH_MAX_BYTES="131072")
        assert result.returncode!=0 and not bad.exists()
        print("PASS: shell syntax; mock C build; 3 full jobs (566 cases each); shuffled orders;")
        print("      diagnostic; 32-KiB plan filtering; data/zero-timing failure stops; CSV rejection.")
        print("Synthetic timings only. No real Sunway compilation or scheduler submission.")

if __name__=="__main__":
    main()
