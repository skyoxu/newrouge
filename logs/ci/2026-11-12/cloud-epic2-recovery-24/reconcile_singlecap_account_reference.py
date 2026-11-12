"""Correct only the caller's typed prepared reference in a new known attempt."""
from pathlib import Path
import json
import subprocess
import sys
import time

REPO=Path('/workspace/newrouge');OUT=Path(__file__).resolve().parent
prepared=json.loads((OUT/'singlecap-prepare.json').read_bytes())
failed=json.loads((OUT/'singlecap-account.json').read_bytes())
assert failed['exit_code']==1 and failed['termination_reason']=='blocked'
assert failed['model_dispatch_count']==0
candidate_path=OUT/'single-capability-input/candidate.from-original-proposals.json'
candidate=json.loads(candidate_path.read_bytes())
fixed=json.loads(json.dumps(candidate))
fixed['prepared_ref']=prepared['prepared_ref']
assert {k:v for k,v in fixed.items() if k!='prepared_ref'}=={k:v for k,v in candidate.items() if k!='prepared_ref'}
path=OUT/'single-capability-input/candidate.with-current-prepared-ref.json'
with path.open('x',encoding='utf-8') as stream:
    json.dump(fixed,stream,ensure_ascii=False,indent=2);stream.write('\n')
command=[sys.executable,'-B',str(REPO/'scripts/python/dev_cli.py'),'b-route-sources','--root',str(REPO),
    '--stage','account','--run-id',prepared['run_id'],'--scope-id',prepared['scope_id'],'--attempt-id','account-02',
    '--prepared',prepared['prepared_ref']['path'],'--candidate',path.relative_to(REPO).as_posix()]
start=time.monotonic()
with (OUT/'singlecap-account-02.json').open('xb') as stdout,(OUT/'singlecap-account-02.stderr').open('xb') as stderr:
    result=subprocess.run(command,cwd=REPO,stdout=stdout,stderr=stderr)
value=json.loads((OUT/'singlecap-account-02.json').read_bytes())
report={'command':command,'exit_code':result.returncode,'elapsed_seconds':time.monotonic()-start,
    'prepared_ref':prepared['prepared_ref'],'accounted_ref':value['output_ref']+'/report.json',
    'accounting_complete':value['accounting_complete'],'original_failed_attempt_retained':True,
    'correction':'typed prepared_ref only; original business proposals unchanged',
    'new_model_calls':0,'registry_written':False,'native_run_created':False,
    'formal3b_preparation_complete':False,'current_independent_audit_complete':False}
(OUT/'single-capability-material-result.json').write_text(json.dumps(report,indent=2)+'\n')
assert result.returncode==0 and value['accounting_complete'],value
print(json.dumps(report,indent=2))
