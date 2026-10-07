"""Windows local verification of plan/host/CPE protocol; NO Sunway timing.

The actual topology_slave.c runs on 64 local threads with TLS-address-translated
memory copies and reply counters. This checks protocol/data logic, not hardware.
"""
import argparse
import csv
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent

ATHREAD = r'''
#ifndef LOCAL_ATHREAD_H
#define LOCAL_ATHREAD_H
#include <stddef.h>
#define SLAVE_FUN(x) x
int mock_posix_memalign(void **, size_t, size_t);
void mock_free(void *);
#define posix_memalign mock_posix_memalign
#define free mock_free
int athread_init(void);
void athread_halt(void);
int athread_spawn(void (*)(), void *);
int athread_join(void);
#endif
'''
SLAVE = r'''
#ifndef LOCAL_SLAVE_H
#define LOCAL_SLAVE_H
#include <stddef.h>
#define __thread_local __thread
typedef volatile long athread_rply_t;
extern __thread int _PEN;
void athread_dma_get(void *, const void *, size_t);
void athread_dma_put(void *, const void *, size_t);
void athread_ssync_array(void);
unsigned long athread_stime_cycle(void);
int athread_rma_iput(void *, athread_rply_t *, int, int, void *, athread_rply_t *);
void athread_rma_wait_value(athread_rply_t *, unsigned long);
void athread_memory_barrier(void);
#endif
'''
RUNTIME = r'''
#include <windows.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <malloc.h>
#include "slave.h"
#include "topology_common.h"
__thread int _PEN;
static uintptr_t anchors[64];
static HANDLE threads[64];
static CRITICAL_SECTION barrier_lock;
static CONDITION_VARIABLE barrier_cond;
static int arrived, generation, initialized, cases;
static int dropped_ready, dropped_stop;
static void (*kernel_function)();
static topo_args_t *argument;
int mock_posix_memalign(void **p, size_t a, size_t n) { *p=_aligned_malloc(n,a); return !*p; }
void mock_free(void *p) { _aligned_free(p); }
int athread_init(void) {
    if(initialized++) abort();
    InitializeCriticalSection(&barrier_lock); InitializeConditionVariable(&barrier_cond);
    return 0;
}
void athread_halt(void) { if(initialized!=1) abort(); DeleteCriticalSection(&barrier_lock); initialized=0; }
static DWORD WINAPI worker(LPVOID i) { _PEN=(int)(intptr_t)i; kernel_function(argument); return 0; }
int athread_spawn(void (*f)(),void *p) {
    int i; if(initialized!=1 || (uintptr_t)p%128) abort();
    argument=p; kernel_function=f; arrived=generation=0; dropped_ready=dropped_stop=0; ++cases;
    for(i=0;i<64;i++) { threads[i]=CreateThread(NULL,0,worker,(LPVOID)(intptr_t)i,0,NULL); if(!threads[i]) abort(); }
    return 0;
}
int athread_join(void) {
    int i; char *fail=getenv("TOPO_MOCK_ERROR_AT"), *cap=getenv("TOPO_MOCK_CAP_AT");
    if(WaitForMultipleObjects(64,threads,TRUE,120000)!=WAIT_OBJECT_0) abort();
    for(i=0;i<64;i++) CloseHandle(threads[i]);
    if(fail && atoi(fail)==cases) argument->results[argument->flows[0].src].errors=1;
    if(cap && atoi(cap)==cases) argument->results[argument->flows[0].src].background_limit_hit=1;
    return 0;
}
void athread_dma_get(void *d,const void *s,size_t n) { memcpy(d,s,n); anchors[_PEN]=(uintptr_t)d; }
void athread_dma_put(void *d,const void *s,size_t n) { memcpy(d,s,n); }
void athread_ssync_array(void) {
    int g; EnterCriticalSection(&barrier_lock); g=generation;
    if(++arrived==64) { arrived=0; generation++; WakeAllConditionVariable(&barrier_cond); }
    else while(g==generation) if(!SleepConditionVariableCS(&barrier_cond,&barrier_lock,120000)) abort();
    LeaveCriticalSection(&barrier_lock);
}
unsigned long athread_stime_cycle(void) { LARGE_INTEGER n; QueryPerformanceCounter(&n); return (unsigned long)n.QuadPart; }
int athread_rma_iput(void *s,athread_rply_t *lr,int n,int pe,void *d,athread_rply_t *rr) {
    uintptr_t remote_d,remote_r; int drop=0;
    char *ready=getenv("TOPO_MOCK_DROP_READY_PE"), *stop=getenv("TOPO_MOCK_DROP_STOP_PE");
    if(pe<0 || pe>63 || n<4 || n%4 || !anchors[pe]) abort();
    remote_d=anchors[pe]+(uintptr_t)d-anchors[_PEN];
    remote_r=anchors[pe]+(uintptr_t)rr-anchors[_PEN];
    memcpy((void *)remote_d,s,(size_t)n);
    if(argument->mode && argument->nflows>1 && n==8) {
        if(ready && _PEN==atoi(ready) && pe==argument->flows[0].src && !dropped_ready++) drop=1;
        if(stop && _PEN==argument->flows[0].src && pe==atoi(stop) && !dropped_stop++) drop=1;
    }
    if(!drop) InterlockedIncrement((LONG *)remote_r);
    InterlockedIncrement((LONG *)lr);
    return 0;
}
void athread_memory_barrier(void) { MemoryBarrier(); }
void athread_rma_wait_value(athread_rply_t *p,unsigned long value) {
    while((unsigned long)InterlockedCompareExchange((LONG *)p,0,0)<value) SwitchToThread();
}
'''


def run(cmd, ok=True, **kw):
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, timeout=180, **kw)
    if ok and r.returncode:
        raise AssertionError(f"exit={r.returncode}\n{r.stdout}")
    return r


def module(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gcc", required=True); ap.add_argument("--bash", required=True)
    ap.add_argument("--report", type=Path)
    a = ap.parse_args()
    gen, ana = module("generate_plan"), module("analyze")
    checks = []
    run([a.bash, "-n", str(HERE / "run_supplement.sh")]); checks.append("bash syntax")
    with tempfile.TemporaryDirectory(prefix="topology_verify_") as td:
        tmp = Path(td)
        (tmp / "athread.h").write_text(ATHREAD)
        (tmp / "slave.h").write_text(SLAVE)
        (tmp / "runtime.c").write_text(RUNTIME)
        exe = tmp / "local_topology.exe"
        run([a.gcc, "-std=c99", "-D_WIN32_WINNT=0x0600", "-DTOPO_LOCAL_EMULATION=1", "-O2", "-Wall", "-Wextra", "-Werror", "-I", str(tmp), "-I", str(HERE),
             str(HERE / "topology_host.c"), str(HERE / "topology_slave.c"), str(tmp / "runtime.c"), "-o", str(exe)])
        checks.append("host and actual slave C compile with volatile reply typedef and -Wall -Wextra -Werror (local runtime)")
        generated = {}
        for profile in ("quick", "full"):
            plan, features = gen.write_plan(tmp / profile, profile, 64)
            run([str(exe), "--validate-plan", str(tmp / profile / "plan.txt")])
            assert len({p["case_id"] for p in plan}) == len(plan)
            for p in plan:
                assert gen.capacity_ok(p["flows"], p["bytes"], p["window"], p["mode"])
                if p["family"] == "routes":
                    assert not ({gen.block(i) for i in p["flows"][0]} &
                                {gen.block(i) for f in p["flows"][1:] for i in f})
            generated[profile] = len(plan)
            checks.append(f"{profile} plan: {len(plan)} cases, capacities/endpoints/unique IDs/native parsing")
        f = gen.features((gen.member(0), gen.member(15)), (gen.member(1), gen.member(2)))
        assert f["XY_forward_same_direction"] == 1 and f["YX_forward_same_direction"] == 0
        f = gen.features((gen.member(0), gen.member(15)), (gen.member(13), gen.member(14)))
        assert f["YX_forward_same_direction"] == 1 and f["XY_forward_same_direction"] == 0
        checks.append("XY/YX discriminator examples and reverse-path features")

        diag = tmp / "diagnostic"; diag.mkdir(); (diag / "raw").mkdir()
        gen.write_plan(diag, reps=64, diagnostic=True)
        run([str(exe), "--suite", str(diag / "plan.txt"), str(diag)])
        assert (diag / "RUN_COMPLETE").read_text().strip() == "completed_cases=6"
        for p in json.loads((diag / "plan.json").read_text()): ana.checked(diag, p)
        checks.append("64-thread actual CPE kernel: all 6 diagnostic cases, independent incast lanes, sequence/full final payload checks, ready-stop-drain")
        # Cover all 41 quick groups with only 64 rounds: two jobs, different ABBA orders.
        result = tmp / "matched"
        result.mkdir()
        orders = []
        for repeat in (1, 2):
            rep = result / f"repeat_{repeat:02d}"; rep.mkdir(); (rep / "raw").mkdir()
            plan, _ = gen.write_plan(rep, "quick", 64, 20261007 + repeat)
            orders.append([p["case_id"] for p in plan])
            run([str(exe), "--suite", str(rep / "plan.txt"), str(rep)])
        assert orders[0] != orders[1]
        effects = ana.analyze(result)
        assert len(effects) == 82
        assert (result / "analysis" / "route_effects.csv").exists()
        checks.append("2 shuffled quick jobs: 468 actual-kernel cases; paired analysis, solo normalization, metric formula/data-count audit")
        for env_key in ("TOPO_MOCK_ERROR_AT", "TOPO_MOCK_CAP_AT"):
            fail = tmp / env_key; fail.mkdir(); (fail / "raw").mkdir()
            gen.write_plan(fail, diagnostic=True)
            r = run([str(exe), "--suite", str(fail / "plan.txt"), str(fail)], ok=False,
                    env=dict(os.environ, **{env_key: "2"}))
            assert r.returncode != 0 and not (fail / "RUN_COMPLETE").exists()
            assert len(list((fail / "raw").glob("*.csv"))) == 2
        checks.append("data-error and capped-background failures stop subsequent cases")
        for env_key, stage in (("TOPO_MOCK_DROP_READY_PE", 3), ("TOPO_MOCK_DROP_STOP_PE", 10)):
            fail = tmp / env_key; fail.mkdir(); (fail / "raw").mkdir()
            gen.write_plan(fail, diagnostic=True)
            r = run([str(exe), "--suite", str(fail / "plan.txt"), str(fail)], ok=False,
                    env=dict(os.environ, TOPO_WAIT_TIMEOUT_CYCLES="1000000", **{env_key:"2"}))
            assert r.returncode != 0 and not (fail / "RUN_COMPLETE").exists(), r.stdout
            assert f"stage={stage}" in r.stdout, r.stdout
            assert (fail / "raw" / "diag_05.csv").exists(), r.stdout
        checks.append("missing ready and stop completion notifications: bounded exit with exact stage/counter diagnostic, no completion marker")
        # Reject bad plans before any launch.
        valid = (diag / "plan.txt").read_text().splitlines()[1]
        fields = valid.split()
        for label, mutate in (("self", lambda f: f.__setitem__(13, f[12])),
                              ("capacity", lambda f: (f.__setitem__(6, "32768"), f.__setitem__(10, "4"))),
                              ("extra", lambda f: f.append("unexpected"))):
            f = fields.copy(); mutate(f)
            bad = tmp / f"bad_{label}.txt"; bad.write_text(" ".join(f)+"\n")
            assert run([str(exe), "--validate-plan", str(bad)], ok=False).returncode != 0
        checks.append("self-pair, excessive capacity, and trailing input rejected")
        rep = result / "repeat_01"
        p = json.loads((rep / "plan.json").read_text())[0]
        raw = rep / "raw" / (p["case_id"] + ".csv")
        original = raw.read_text()
        lines = original.splitlines()
        fields = lines[1].split(","); fields[7] = "1"; lines[1] = ",".join(fields)
        raw.write_text("\n".join(lines)+"\n")
        try: ana.checked(rep, p)
        except ValueError: pass
        else: raise AssertionError("corrupt CSV accepted")
        raw.write_text(original)
        checks.append("corrupt raw CSV rejected")
        # Exercise the untouched standalone launcher with a local compiler/scheduler shim.
        shim = tmp / "shim"; shim.mkdir()
        compiler = r'''#!/usr/bin/env bash
set -eu
case ${1:-} in -dumpmachine) echo sw_64_local_protocol_only; exit;; -v) echo LOCAL_PROTOCOL_ONLY; exit;; esac
output=; compile=0
while (($#)); do
  case $1 in -o) output=$2; shift 2;; -c) compile=1; shift;; *) shift;; esac
done
[[ -n "$output" ]]
if ((compile)); then
  : > "$output"
else
  # Model a target binary that is unusable on the login host, even for validation.
  cat > "$output" <<'TARGET'
#!/usr/bin/env bash
set -eu
if [[ ${TOPO_LOCAL_COMPUTE:-0} != 1 ]]; then
  echo 'Cannot execute target binary on login host' >&2
  printf 'blocked\n' >> "$TOPO_LOCAL_FORBIDDEN_LOG"
  exit 126
fi
exec "$TOPO_LOCAL_EXE" "$@"
TARGET
  chmod +x "$output"
fi
'''
        scheduler = r'''#!/usr/bin/env bash
set -eu
printf '%s\n' "$*" >> "$TOPO_LOCAL_SUBMISSIONS"
while (($#)); do
  case $1 in -I) shift;; -q|-n|-cgsp|-mpecg|-cache_size) shift 2;; *) break;; esac
done
[[ $1 != bash && $1 != sh && $1 != /bin/bash ]]
echo 'LOCAL PROTOCOL EMULATION ONLY: no actual scheduler submission.'
TOPO_LOCAL_COMPUTE=1 "$@"
'''
        for name, text in (("swgcc", compiler), ("bsub", scheduler)):
            f = shim / name; f.write_text(text, newline="\n"); f.chmod(0o755)
        def posix(p):
            q = Path(p).as_posix()
            return "/" + q[0].lower() + q[2:] if len(q) > 2 and q[1] == ":" else q
        bash_path = run([a.bash, "-c", 'printf "%s" "$PATH"']).stdout
        env = {k:v for k,v in os.environ.items() if not k.startswith(("TOPO_", "SWCC", "PYTHON", "SW_MODULE"))}
        env.update(PATH=posix(shim)+":"+posix(Path(a.bash).parent)+":"+bash_path, SWCC="swgcc", PYTHON=posix(sys.executable),
                   TOPO_LOCAL_EXE=posix(exe), TOPO_LOCAL_SUBMISSIONS=posix(tmp / "submissions.log"),
                   TOPO_LOCAL_FORBIDDEN_LOG=posix(tmp / "forbidden.log"))
        launch = tmp / "launch"
        run([a.bash, str(HERE / "run_supplement.sh"), "q_share", posix(launch)],
            env=dict(env, TOPO_REPS="64", TOPO_REPEATS="2"))
        assert (launch / "COMPLETE").exists()
        assert len((tmp / "submissions.log").read_text().splitlines()) == 2
        assert (launch / "analysis" / "summary.csv").exists()
        assert not (tmp / "forbidden.log").exists()
        # Confirm the wrapper really rejects direct login-host execution.
        blocked = run([a.bash, posix(launch / "rma_topology_bench"), "--validate-plan", posix(launch / "repeat_01" / "plan.txt")],
                      env=env, ok=False)
        assert blocked.returncode == 126 and (tmp / "forbidden.log").read_text().splitlines() == ["blocked"]
        checks.append("standalone launcher: target execution forbidden on login; two compute-only mock jobs, shuffled plans, analysis, COMPLETE")
        launch_fail = tmp / "launch_failure"
        r = run([a.bash, str(HERE / "run_supplement.sh"), "q_share", posix(launch_fail)], ok=False,
                env=dict(env, TOPO_MOCK_ERROR_AT="2"))
        assert r.returncode and not (launch_fail / "COMPLETE").exists() and not (launch_fail / "repeat_02").exists()
        launch_diag = tmp / "launch_diag"
        run([a.bash, str(HERE / "run_supplement.sh"), "q_share", posix(launch_diag)],
            env=dict(env, TOPO_DIAG_ONLY="1"))
        assert (launch_diag / "COMPLETE").exists() and not (launch_diag / "repeat_02").exists()
        assert (tmp / "forbidden.log").read_text().splitlines() == ["blocked"]
        checks.append("launcher: error stops later jobs; 6-case diagnostic succeeds as one job")
    report = dict(status="PASS", checks=checks, generated_cases=generated,
                  actual_sunway_compilation=False, actual_sunway_jobs=False,
                  note="Local threaded protocol emulation only; timings are NOT Sunway data.")
    if a.report:
        a.report.write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
