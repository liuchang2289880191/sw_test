"""Host-side syntax and analyzer checks, not hardware or target-ABI validation."""
import csv
import importlib.util
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('analyze_pmu', ROOT / 'analyze_pmu.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def write_csv(path, rows):
    with path.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


with tempfile.TemporaryDirectory(prefix='pmu_verify_') as temp:
    root = Path(temp)
    inc = root / 'include'
    (inc / 'sys').mkdir(parents=True)
    (inc / 'athread.h').write_text('''
#define SLAVE_FUN(x) slave_##x
#define athread_spawn(fn,arg) fake_spawn((void (*)(void))slave_##fn,(void *)(arg))
int fake_spawn(void (*fn)(void),void *arg);
int athread_init(void); int athread_join(void); void athread_halt(void);
''')
    (inc / 'slave.h').write_text('''
#define __thread_local __thread
extern int _PEN;
typedef volatile long athread_rply_t;
void athread_dma_get(void *, const void *, unsigned long);
void athread_dma_put(void *, const void *, unsigned long);
void athread_ssync_array(void);
unsigned long athread_stime_cycle(void);
int athread_rma_iput(void *,athread_rply_t *,int,int,void *,athread_rply_t *);
''')
    (inc / 'unistd.h').write_text('''
#include <stddef.h>
unsigned int alarm(unsigned int);
int write(int,const void *,size_t);
void _exit(int);
''')
    (inc / 'signal.h').write_text('#define SIGALRM 14\nvoid (*signal(int,void (*)(int)))(int);\n')
    (inc / 'sys' / 'utsname.h').write_text('struct utsname {char nodename[256],machine[256];};\nint uname(struct utsname *);\n')
    names = re.findall(r'EVENT\((penv_\w+)\)', (ROOT / 'pmu_host.c').read_text())
    assert len(names) == len(set(names)) == 22
    (inc / 'swperf.h').write_text('\n'.join(
        'void {0}_init(void); void {0}_count(unsigned long *);'.format(n) for n in names))
    compiler = shutil.which('gcc')
    if not compiler:
        raise RuntimeError('gcc required for local syntax checks')
    for file in ('pmu_host.c', 'pmu_slave.c'):
        subprocess.run([compiler, '-fsyntax-only', '-std=c99', '-Wall', '-Wextra', '-Werror',
                        '-I' + str(inc), str(ROOT / file)], check=True)
    counters, checks = [], []
    cid = 0
    for mode in ('put', 'local'):
        for n in (0, 64, 256):
            cid += 1
            for cell in range(16):
                delta = 7 + (n * 3 if mode == 'put' and cell == 0 else 0)
                counters.append(dict(case_id=cid, event=names[0], repeat=1, mode=mode,
                    src=0, dst=1, bytes=64, n=n, cell=cell, before=100, after=100+delta,
                    delta=delta, decreased=0))
            for pe in range(64):
                checks.append(dict(case_id=cid, pe=pe, errors=0,
                    local_done=n if mode == 'put' and pe == 0 else 0,
                    remote_done=n if mode == 'put' and pe == 1 else 0,
                    cycles=100, source_addr=128, stack_addr=1024))
    (root / 'RUN_COMPLETE').write_text('cases=6\n')
    write_csv(root / 'counters.csv', counters)
    write_csv(root / 'checks.csv', checks)
    audit = module.analyze(root)
    with (root / 'count_scaling.csv').open() as f:
        slopes = list(csv.DictReader(f))
    assert all(abs(float(row['count_per_operation']) -
        (3 if row['mode'] == 'put' and row['cell'] == '0' else 0)) < 1e-12 for row in slopes)
    # Missing cell, counter decrease, and wrong remote completion must fail.
    for fault in ('missing_cell', 'counter_decrease', 'remote_count'):
        bad_rows = [dict(x) for x in counters]
        bad_checks = [dict(x) for x in checks]
        if fault == 'missing_cell': bad_rows.pop()
        if fault == 'counter_decrease': bad_rows[0]['decreased'] = 1
        if fault == 'remote_count': bad_checks[65]['remote_done'] = 0
        write_csv(root / 'counters.csv', bad_rows)
        write_csv(root / 'checks.csv', bad_checks)
        try:
            module.analyze(root)
        except ValueError:
            pass
        else:
            raise AssertionError('Analyzer accepted ' + fault)
    print(json.dumps(dict(syntax='passed using interface stubs', known_slope='passed',
        malformed_results='3 rejection checks passed', target_compile='not performed',
        hardware='not executed'), indent=2))
