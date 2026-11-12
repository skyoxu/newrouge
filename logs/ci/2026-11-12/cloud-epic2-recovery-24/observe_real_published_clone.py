"""Read genuine receipt-sealed clones without local historical logs or seams."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time

REPO=Path('/workspace/newrouge')
OUT=Path(__file__).resolve().parent
ORIGINAL=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/work/target-compensation-prepare')
HOME=Path('/workspace/newrouge-tools/clones/epic2-continuation24')
OP='NativeV15Origin03Compensation01'
prior=json.loads((REPO/'logs/ci/2026-11-12/cloud-epic2-recovery-22/public-compensation-read.json').read_bytes())
receipt=json.loads((ORIGINAL/prior['context']['receipt_ref']['path']).read_bytes())
paths=sorted(set(prior['formal_paths'])|{p['path'] for p in receipt['authority'] if not p['path'].startswith('logs/')})
raws={name:(ORIGINAL/name).read_bytes() for name in paths}
manifest={name:{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()} for name,raw in raws.items()}
results=[]
for name in ('exact','changed-plan'):
    root=HOME/name
    root.mkdir(parents=True,exist_ok=False)
    for path,raw in raws.items():
        target=root/path;target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as stream:stream.write(raw)
    assert not (root/'logs').exists()
    if name=='changed-plan':
        plan=root/prior['context']['plan_refs'][0]['path']
        with plan.open('ab') as stream:stream.write(b'\n')
    before={p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths}
    command=[sys.executable,'-B',str(REPO/'scripts/python/b_route_adoption.py'),'--root',str(root),
             '--stage','read','--operation-id',OP,'--context']
    started=time.monotonic()
    with (OUT/f'clone-{name}.json').open('xb') as stdout,(OUT/f'clone-{name}.stderr').open('xb') as stderr:
        process=subprocess.run(command,cwd='/tmp',stdout=stdout,stderr=stderr)
    payload=json.loads((OUT/f'clone-{name}.json').read_bytes())
    assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==digest for p,digest in before.items())
    assert all((ORIGINAL/p).read_bytes()==raw for p,raw in raws.items())
    assert not list(root.rglob('auth.json'))
    row={'case':name,'root':str(root),'command':command,'cwd':'/tmp','exit_code':process.returncode,
         'elapsed_seconds':time.monotonic()-started,'output':f'clone-{name}.json',
         'formal_and_nonlog_source_bytes_unchanged_by_reader':True,'historical_logs_copied':False,
         'new_auxiliary_files':[str(p.relative_to(root)) for p in (root/'logs').rglob('*') if p.is_file()]}
    results.append(row)
    (OUT/'real-clone-observations.json').write_text(json.dumps({'manifest':manifest,'cases':results,
         'new_model_calls':0,'native_or_review_seams':False,'original_published_root_unchanged':True},indent=2)+'\n')
    if name=='exact':
        assert process.returncode==0 and payload['formal_adoption'] is True, payload
        assert payload['context']['receipt_ref']==prior['context']['receipt_ref']
        assert payload['context']['plan_refs']==prior['context']['plan_refs']
    else:
        assert process.returncode==2 and payload['formal_adoption'] is False,payload
        assert payload['diagnostics']
    print(json.dumps(row),flush=True)
