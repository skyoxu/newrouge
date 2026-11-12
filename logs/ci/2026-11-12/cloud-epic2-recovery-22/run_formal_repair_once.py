"""One user-authorized formal repair CLI invocation; never retry an intent."""
from pathlib import Path
import datetime
import json
import os
import subprocess
import sys
import time

REPO=Path('/workspace/newrouge');OUT=Path(__file__).resolve().parent
ROOT=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/work/target-compensation-prepare')
SOURCE='User instruction 2026-11-12: ongoing Epic2 Codex subscription reviews; one necessary formal repair review, original2 retained plus additional1, cumulative3.'
command=[sys.executable,'-B',str(REPO/'scripts/python/dev_cli.py'),'b-route-adoption','--root',str(ROOT),
    '--stage','review-segmented-repair-execute','--operation-id','NativeV15Origin03Compensation01',
    '--model-request-budget','1','--review-authorization-source',SOURCE]
record={'command':command,'authorization_source':SOURCE,'original_logical_calls_occupied':2,
    'new_logical_allowance':1,'cumulative_logical_limit':3,'automatic_retry':False,
    'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
with (OUT/'formal-repair-started.json').open('x',encoding='utf-8') as f:
    json.dump(record,f,indent=2);f.write('\n')
env={**os.environ,'CODEX_HOME':'/workspace/newrouge-tools/codex-login-20261112-JtqMz6'}
started=time.monotonic()
with (OUT/'public-repair-execute.json').open('xb') as stdout,(OUT/'public-repair-execute.stderr').open('xb') as stderr:
    process=subprocess.Popen(command,cwd=REPO,env=env,stdout=stdout,stderr=stderr)
    print(json.dumps({'pid':process.pid,'purpose':'formal repair; not diagnostic','automatic_retry':False}),flush=True)
    code=process.wait()
record.update(exit_code=code,elapsed_seconds=time.monotonic()-started,
    finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
(OUT/'formal-repair-result.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'exit_code':code,'elapsed_seconds':record['elapsed_seconds']}),flush=True)
