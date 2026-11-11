"""Inspect a disposable copy using current public services, without replay."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
ROOT=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9')
REPO=Path('/workspace/newrouge')
OUT=REPO/'logs/ci/2026-11-11/cloud-epic2-recovery-09'
TARGET=ROOT/'work/target-public-inspect'
TARGET.parent.mkdir(exist_ok=True)
shutil.copytree(ROOT/'data/target', TARGET)
def tree(root):
    return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
before=tree(TARGET)
results=[]
for stage,context in [('inspect',True),('recover-inspect',False),('read',True)]:
    command=[sys.executable,'-B',str(REPO/'scripts/python/b_route_adoption.py'),'--root',str(TARGET),'--stage',stage,'--operation-id','NativeV15Origin03']
    if context: command.append('--context')
    start=time.monotonic()
    result=subprocess.run(command,cwd=REPO,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
    label='actual-'+stage
    (OUT/(label+'.stdout')).write_bytes(result.stdout)
    (OUT/(label+'.stderr')).write_bytes(result.stderr)
    results.append({'stage':stage,'context':context,'command':command,'exit_code':result.returncode,'elapsed_seconds':time.monotonic()-start,'stdout':label+'.stdout','stderr':label+'.stderr'})
    print(stage, result.returncode, result.stdout.decode('utf-8','replace')[:2500],flush=True)
after=tree(TARGET)
report={'target_copy':str(TARGET),'commands':results,'added_files':sorted(after.keys()-before.keys()),'removed_files':sorted(before.keys()-after.keys()),'changed_existing_files':sorted(k for k in before.keys()&after.keys() if before[k]!=after[k]),'archive_originals_used_as_code':False,'model_calls':0,'operation_transitions_requested':False,'qualification':'Current public inspection on copied raw historical data; not a new native, provider or Story qualification.'}
(OUT/'actual-public-inspection.json').write_text(json.dumps(report,indent=2)+'\n')
