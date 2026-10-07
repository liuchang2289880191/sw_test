"""Copy the successful immutable kernel snapshot and package the independent suite."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import zipfile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
SRC=ROOT/'outputs/results_20261007_211507_31272/source'


def prepare():
    copied=[]
    for name in ('topology_host.c','topology_slave.c','topology_common.h'):
        shutil.copyfile(SRC/name,HERE/name)
        copied.append(dict(file=name,source=str((SRC/name).relative_to(ROOT)),
                           sha256=hashlib.sha256((HERE/name).read_bytes()).hexdigest()))
    shutil.copyfile(SRC/'analyze.py',HERE/'base_analysis.py')
    emulator=(ROOT/'rma_supplement/verify_local.py').read_text(encoding='utf-8').split('\ndef run(')[0]
    (HERE/'local_protocol.py').write_text(emulator,encoding='utf-8',newline='\n')
    (HERE/'KERNEL_PROVENANCE.json').write_text(json.dumps(dict(copied_from_successful_hardware_run=True,
        source_result='results_20261007_211507_31272',kernel_bytes_unchanged=True,files=copied),indent=2)+'\n',encoding='utf-8')
    print('Prepared three unchanged kernel files and the base validator.')


def package():
    verification=json.loads((HERE/'LOCAL_VERIFICATION.json').read_text(encoding='utf-8'))
    assert verification['passed']
    provenance=json.loads((HERE/'KERNEL_PROVENANCE.json').read_text(encoding='utf-8'))
    assert all(hashlib.sha256((HERE/x['file']).read_bytes()).hexdigest()==x['sha256'] for x in provenance['files'])
    files=[p for p in sorted(HERE.rglob('*')) if p.is_file() and '__pycache__' not in p.parts]
    output=ROOT/'outputs/rma_route_identify_20261007.zip'
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p,'rma_route_identify/'+p.relative_to(HERE).as_posix())
    with zipfile.ZipFile(output) as z:
        assert z.testzip() is None
        assert len(z.namelist())==len(files)
        assert all(z.read('rma_route_identify/'+p.relative_to(HERE).as_posix())==p.read_bytes() for p in files)
    print('Bundle integrity and current source match: '+str(len(files))+' files')
    print(str(output))


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--prepare',action='store_true');a=ap.parse_args()
    prepare() if a.prepare else package()
