"""One authorized deterministic CLI execution, with no automatic retry."""
from pathlib import Path
import datetime
import json
import os
import subprocess
import sys
import time

REPO = Path('/workspace/newrouge')
OUT = Path(__file__).resolve().parent
ROOT = Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/work/target-compensation-prepare')
HOME = Path('/workspace/newrouge-tools/codex-login-20261112-JtqMz6')
command = [sys.executable, '-B', str(REPO/'scripts/python/dev_cli.py'),
    'b-route-adoption', '--root', str(ROOT), '--stage', 'review-segmented-execute',
    '--operation-id', 'NativeV15Origin03Compensation01', '--model-request-budget', '2']
record = {'command':command, 'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'operation_lifetime_logical_call_limit':2, 'model':'gpt-6.1-sol',
    'reasoning_effort':'high', 'service_tier':None, 'automatic_retry':False}
with (OUT/'execute-once-started.json').open('x',encoding='utf-8') as f:
    json.dump(record,f,indent=2);f.write('\n')
env = {**os.environ, 'CODEX_HOME':str(HOME)}
started=time.monotonic()
with (OUT/'public-execute-01.json').open('xb') as stdout, (OUT/'public-execute-01.stderr').open('xb') as stderr:
    proc=subprocess.Popen(command,cwd=REPO,env=env,stdout=stdout,stderr=stderr)
    print(json.dumps({'pid':proc.pid,'status':'started','automatic_retry':False}),flush=True)
    code=proc.wait()
report={**record,'exit_code':code,'elapsed_seconds':time.monotonic()-started,
    'finished_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
(OUT/'execute-once-result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps({'exit_code':code,'elapsed_seconds':report['elapsed_seconds']}),flush=True)
