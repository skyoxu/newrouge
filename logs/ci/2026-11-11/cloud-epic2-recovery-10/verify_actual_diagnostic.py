"""Recheck the known pre-dispatch failure after its diagnostic-only repair."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

REPO=Path('/workspace/newrouge')
OUT=Path(__file__).absolute().parent
TARGET=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/work/target-compensation-prepare')
def tree(root):
 return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file()}
reuse='--reuse-output' in sys.argv
before=tree(Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/data/target') if reuse else TARGET)
command=[sys.executable,'-B',str(REPO/'scripts/python/dev_cli.py'),'b-route-adoption',
 '--root',str(TARGET),'--stage','review-prepare','--operation-id','NativeV15Origin03Compensation01',
 '--request','logs/ci/b-route-requests/native-v15-origin03-compensation-01/request.json',
 '--compensation-review-delivery','newrouge.b-route-qualified-compensation-review-delivery.v2']
if reuse:
 # Attempt01 passed its process-exit assertion before the incorrect entity assertion.
 exit_code=json.loads((OUT/'verification-attempt01.json').read_bytes())['public_process_exit_code']
 stdout=(OUT/'actual-uninstalled-owner.stdout').read_bytes()
 elapsed=None
else:
 started=time.monotonic()
 result=subprocess.run(command,cwd=REPO,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
 elapsed=time.monotonic()-started
 (OUT/'actual-uninstalled-owner.stdout').write_bytes(result.stdout)
 (OUT/'actual-uninstalled-owner.stderr').write_bytes(result.stderr)
 exit_code=result.returncode
 stdout=result.stdout
after=tree(TARGET)
value=json.loads(stdout)
diagnostic=value['diagnostics'][0]
assert exit_code==2 and value['status']=='blocked'
assert diagnostic['reason_code']=='dependency_unavailable'
assert diagnostic['entity_id']=='NativeV15Origin03'
assert diagnostic['actual']['historical_evidence_checked'] is False
assert diagnostic['resume_ref']==str(REPO/'scripts/python/qualified-historical-owner-authority.v2.json')
assert all(value[name] is False for name in ('formal_adoption','readiness','runtime_verified'))
assert before==after
report={'command':command,'exit_code':exit_code,'elapsed_seconds':elapsed,
 'verification_uses_retained_actual_output':reuse,'process_repeated_for_harness_correction':False,
 'diagnostic':diagnostic,'target_files_unchanged':True,'new_model_calls':0,'financial_writes':0,
 'original_operation_replayed':False,'qualification':'Actual blocked public prepare with verified original request, before any historical worker release. Diagnostic repair only; not a compensation or capacity acceptance.'}
(OUT/'actual-uninstalled-owner.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
