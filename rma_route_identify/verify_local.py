"""Plan/math/launcher and actual-C-kernel protocol checks, never Sunway timing."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import numpy as np
import generate_plan as gen
import analyze as ana
from base_analysis import checked
from design_math import exact_rank,scaled_condition,fit,predict
from local_protocol import ATHREAD,SLAVE,RUNTIME

HERE=Path(__file__).resolve().parent


def run(cmd,ok=True,**kwargs):
    result=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180,**kwargs)
    if ok and result.returncode: raise AssertionError(f'{cmd}: exit {result.returncode}\n{result.stdout}')
    return result


def posix(path):
    p=Path(path).as_posix()
    return '/'+p[0].lower()+p[2:] if len(p)>2 and p[1]==':' else p


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--gcc',default=shutil.which('gcc'))
    ap.add_argument('--bash',default='C:/Program Files/Git/bin/bash.exe');a=ap.parse_args()
    checks=[]
    provenance=json.loads((HERE/'KERNEL_PROVENANCE.json').read_text())
    for item in provenance['files']:
        assert hashlib.sha256((HERE/item['file']).read_bytes()).hexdigest()==item['sha256']
    checks.append('Three kernel files exactly match the successful hardware-run snapshot')
    run([a.bash,'-n',str(HERE/'run_route_identify.sh')]);checks.append('Bash syntax')
    with tempfile.TemporaryDirectory(prefix='route_identify_verify_') as td:
        tmp=Path(td);(tmp/'athread.h').write_text(ATHREAD);(tmp/'slave.h').write_text(SLAVE)
        (tmp/'runtime.c').write_text(RUNTIME);exe=tmp/'protocol.exe'
        run([a.gcc,'-std=c99','-D_WIN32_WINNT=0x0600','-DTOPO_LOCAL_EMULATION=1','-O2','-Wall','-Wextra','-Werror',
             '-I',str(tmp),'-I',str(HERE),str(HERE/'topology_host.c'),str(HERE/'topology_slave.c'),str(tmp/'runtime.c'),'-o',str(exe)])
        checks.append('Actual host/slave sources compile with volatile reply words and warning-as-error in local runtime')
        result=tmp/'matched';result.mkdir();orders=[]
        for seed in (1,2,999):
            p,rt,audit=gen.write_plan(tmp/f'preview_{seed}',64,seed)
            assert len(p)==256 and len(rt)==64
            assert len({r['case_id'] for r in p})==256
            run([str(exe),'--validate-plan',str(tmp/f'preview_{seed}/plan.txt')])
            for r in p:
                assert r['bytes']*r['window']<=32768
                if r['role']=='treatment':assert not set(r['flows'][0])&set(r['flows'][1])
            x=np.array([gen.design_row(r) for r in rt],dtype=float)
            assert np.linalg.matrix_rank(x)==14 and exact_rank(x.tolist())==14
            cond=np.linalg.cond(x/np.linalg.norm(x,axis=0))
            assert abs(cond-scaled_condition(x.tolist()))<1e-8
            beta=np.arange(14)*.123-1;response=x@beta
            recovered=np.array(fit(x.tolist(),response.tolist()))
            assert np.max(np.abs(recovered-beta))<1e-9
            orders.append([r['case_id'] for r in p])
        assert orders[0]!=orders[1]!=orders[2]
        checks.append('3 seeds: 256 cases / 64 groups; native parsing; rank 14 in both directions; stdlib condition/QR agree with NumPy and known signal')
        bad=json.loads(json.dumps(rt))
        for r in bad:r['YX_reply_opposite_direction']=r['XY_forward_same_direction']
        try:gen.audit_design(bad)
        except ValueError:pass
        else:raise AssertionError('Duplicated model column was accepted')
        checks.append('Rank-deficient design is rejected')
        diag=tmp/'diag';diag.mkdir();(diag/'raw').mkdir();pd,_,_=gen.write_plan(diag,64,diagnostic=True)
        run([str(exe),'--suite',str(diag/'plan.txt'),str(diag)])
        assert (diag/'RUN_COMPLETE').read_text().strip()=='completed_cases=4'
        for p in pd:checked(diag,p)
        checks.append('4 new diagonal diagnostics execute the actual kernel on 64 local threads; ready/stop/count/payload checks pass')
        for repn in (1,2):
            rep=result/f'repeat_{repn:02}';rep.mkdir();(rep/'raw').mkdir()
            gen.write_plan(rep,64,repn)
            run([str(exe),'--suite',str(rep/'plan.txt'),str(rep)])
        summary,models=ana.analyze(result)
        assert len(summary)==64 and len(models)==4
        assert all(r['rank']==r['columns'] for r in models)
        checks.append('Two shuffled 64-round local jobs: 512 cases; raw audit, within-job matching, background/sample export and all model reports')
        # Launcher shim enforces that every target execution comes via scheduler.
        shim=tmp/'shim';shim.mkdir()
        compiler='''#!/usr/bin/env bash
set -eu
case ${1:-} in -dumpmachine) echo sw_64_local_protocol_only; exit;; -v) echo LOCAL_PROTOCOL_ONLY; exit;; esac
output=; compile=0
while (($#)); do
 case $1 in -o) output=$2; shift 2;; -c) compile=1; shift;; *) shift;; esac
done
[[ -n "$output" ]]
if ((compile)); then : > "$output"; else
cat > "$output" <<'TARGET'
#!/usr/bin/env bash
set -eu
[[ ${TOPO_LOCAL_COMPUTE:-0} == 1 ]] || { echo 'Target execution on login forbidden' >&2; exit 126; }
exec "$TOPO_LOCAL_EXE" "$@"
TARGET
chmod +x "$output"
fi
'''
        scheduler='''#!/usr/bin/env bash
set -eu
printf '%s\\n' "$*" >> "$TOPO_LOCAL_SUBMISSIONS"
while (($#)); do case $1 in -I) shift;; -q|-n|-cgsp|-mpecg|-cache_size) shift 2;; *) break;; esac; done
TOPO_LOCAL_COMPUTE=1 "$@"
'''
        for name,txt in [('swgcc',compiler),('bsub',scheduler)]:
            (shim/name).write_text(txt,newline='\n')
        env={k:v for k,v in os.environ.items() if not k.startswith(('TOPO_','SWCC','PYTHON','SW_MODULE'))}
        shellpath=run([a.bash,'-c','printf "%s" "$PATH"']).stdout
        env.update(PATH=posix(shim)+':'+shellpath,SWCC='swgcc',PYTHON=posix(sys.executable),
            TOPO_LOCAL_EXE=posix(exe),TOPO_LOCAL_SUBMISSIONS=posix(tmp/'submissions.log'),TOPO_REPEATS='1',TOPO_REPS='64')
        launch=tmp/'launch';run([a.bash,str(HERE/'run_route_identify.sh'),'q_share',posix(launch)],env=env)
        assert (launch/'COMPLETE').exists() and (launch/'analysis/candidate_models.csv').exists()
        diaglaunch=tmp/'diaglaunch';run([a.bash,str(HERE/'run_route_identify.sh'),'q_share',posix(diaglaunch)],env=dict(env,TOPO_DIAG_ONLY='1'))
        assert (diaglaunch/'repeat_01/RUN_COMPLETE').read_text().strip()=='completed_cases=4'
        fail=tmp/'failure';r=run([a.bash,str(HERE/'run_route_identify.sh'),'q_share',posix(fail)],ok=False,
            env=dict(env,TOPO_REPEATS='2',TOPO_MOCK_ERROR_AT='2'))
        assert r.returncode and not (fail/'COMPLETE').exists() and not (fail/'repeat_02').exists()
        checks.append('Launcher: compute-only target execution, one performance job + diagnostics + stop-before-second-job on injected error')
        for k in ('TOPO_MOCK_ERROR_AT','TOPO_MOCK_CAP_AT'):
            d=tmp/k;d.mkdir();(d/'raw').mkdir();gen.write_plan(d,64,diagnostic=True)
            r=run([str(exe),'--suite',str(d/'plan.txt'),str(d)],ok=False,env=dict(os.environ,**{k:'2'}))
            assert r.returncode and not (d/'RUN_COMPLETE').exists()
        checks.append('Injected payload error and capped background reject completion')
    report=dict(passed=True,checks=checks,actual_sunway_compilation=False,actual_sunway_jobs=False,
                note='Local protocol emulation only; mock timing is not hardware performance',design_checks=audit['checks'])
    (HERE/'LOCAL_VERIFICATION.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
