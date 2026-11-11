"""Check real published identity across a clean clone and prepare one new review."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode=True
ROOT=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9')
REPO=Path('/workspace/newrouge')
OUT=REPO/'logs/ci/2026-11-11/cloud-epic2-recovery-09'
CLONE=ROOT/'work/target-no-history-logs'
COMP=ROOT/'work/target-compensation-prepare'
shutil.copytree(ROOT/'data/target',CLONE,ignore=shutil.ignore_patterns('logs'))
shutil.copytree(ROOT/'data/target',COMP)
def tree(root):
 return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
before_clone=tree(CLONE);before_comp=tree(COMP)
command=[sys.executable,'-B',str(REPO/'scripts/python/dev_cli.py'),'b-route-adoption','--root',str(CLONE),'--stage','read','--operation-id','NativeV15Origin03','--context']
start=time.monotonic();proc=subprocess.run(command,cwd=REPO,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
(OUT/'actual-clone-read.stdout').write_bytes(proc.stdout);(OUT/'actual-clone-read.stderr').write_bytes(proc.stderr)
clone={'command':command,'exit_code':proc.returncode,'elapsed_seconds':time.monotonic()-start}
if proc.returncode==0:
 first=json.loads((OUT/'actual-read.stdout').read_bytes());second=json.loads(proc.stdout)
 fields=['operation_id','receipt_ref','plan_refs','binding_refs','receipt_revision','operation_digest','catalog_raw_digest','input_set_digest']
 clone['same_context_fields']={k:first['context'].get(k)==second['context'].get(k) for k in fields}
 clone['same_formal_paths']=first['formal_paths']==second['formal_paths']
 clone['formal_adoption']=second['formal_adoption'];clone['context']=second['context']
after_clone=tree(CLONE)
clone['changed_existing_files']=[p for p in before_clone if after_clone.get(p)!=before_clone[p]]
clone['added_files']=sorted(after_clone.keys()-before_clone.keys())
(OUT/'actual-clone-read.json').write_text(json.dumps(clone,indent=2)+'\n')
print('clone-read',proc.returncode,'same-context',clone.get('same_context_fields'),flush=True)

sys.path.insert(0,str(REPO/'scripts/python'))
import _b_route_adoption as adoption
start=time.monotonic()
prepare={'root':str(COMP),'operation_id':'NativeV15Origin03Compensation01','request_ref':'logs/ci/b-route-requests/native-v15-origin03-compensation-01/request.json','delivery':'newrouge.b-route-qualified-compensation-review-delivery.v2','entrypoint':'_b_route_adoption.prepare_review (same public owner used by CLI)'}
try:
 prepare['result']=adoption.prepare_review(COMP,operation_id=prepare['operation_id'],request_ref=prepare['request_ref'],compensation_delivery=prepare['delivery'])
 prepare['status']='returned'
except Exception as error:
 prepare['status']='blocked';prepare['error_type']=type(error).__name__;prepare['error']=str(error)
 prepare['exception_chain']=[]
 current=error
 while current is not None:
  prepare['exception_chain'].append({'type':type(current).__name__,'message':str(current)})
  current=current.__cause__ or current.__context__
 (OUT/'actual-compensation-prepare.traceback.txt').write_text(traceback.format_exc(),encoding='utf-8')
after_comp=tree(COMP)
prepare['elapsed_seconds']=time.monotonic()-start
prepare['changed_existing_files']=[p for p in before_comp if after_comp.get(p)!=before_comp[p]]
prepare['added_files']=sorted(after_comp.keys()-before_comp.keys())
prepare['model_calls']=0;prepare['old_operation_replayed']=False
(OUT/'actual-compensation-prepare.json').write_text(json.dumps(prepare,indent=2)+'\n')
print('compensation-prepare',prepare['status'],prepare.get('exception_chain'),flush=True)
