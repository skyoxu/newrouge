"""One authorized official source audit; preserve every outcome and occupied permit."""
from pathlib import Path
import datetime
import json
import os
import subprocess
import sys
import time
import tomllib

REPO=Path('/workspace/newrouge');OUT=Path(__file__).resolve().parent
RUN='cloud-singlecap-audit-20261112';SCOPE='controlled-exclusive-resolution-v15'
AUTH_HOME=Path('/workspace/newrouge-tools/codex-login-20261112-JtqMz6')
ACCOUNT='logs/ci/2026-11-12/b-route-sources/cloud-singlecap-source-20261112/account-02/account/report.json'
sys.dont_write_bytecode=True;sys.path.insert(0,str(REPO/'scripts/python'))
import _b_route_sources as sources

config=tomllib.loads((AUTH_HOME/'config.toml').read_text())
assert config['model']=='gpt-6.1-sol' and config['model_reasoning_effort']=='high'
assert config.get('service_tier') is None and (AUTH_HOME/'auth.json').is_file()
existing=list((REPO/'logs/ci').glob('*/b-route-source-audit/'+RUN))
assert not existing,'An existing audit home must be reconciled before any dispatch'
obs=sources.Observations(REPO);_,account=sources.load_accounted(obs,ACCOUNT);obs.verify()
assert account['accounting_complete'] and account['model_dispatch_count']==0
command=[sys.executable,'-B',str(REPO/'scripts/python/dev_cli.py'),'b-route-sources','--root',str(REPO),
    '--stage','audit','--run-id',RUN,'--scope-id',SCOPE,'--attempt-id','audit-01','--accounted',ACCOUNT,
    '--runner','scripts/python/codex_isolated_model_runner.py','--expected-model','openai/gpt-6.1-sol',
    '--citation-guidance','full-block','--request-budget','2','--active-budget-seconds','1500','--timeout-seconds','600']
preflight={'authorization_source':'User instruction 2026-11-12: complete the necessary current independent source audit via existing Codex subscription in the minimum original Story scope',
    'command':command,'prior_audit_homes':0,'prior_logical_occupancy':0,'request_budget':2,
    'active_budget_seconds':1500,'timeout_seconds':600,'model':'gpt-6.1-sol','reasoning_effort':'high',
    'service_tier':None,'auth_mode':'existing official subscription profile; no credential read or copy',
    'automatic_retry':False,'original_compensation_budget_reset':False,
    'started_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
with (OUT/'audit-once-started.json').open('x',encoding='utf-8') as stream:
    json.dump(preflight,stream,indent=2);stream.write('\n')
env=dict(os.environ,CODEX_HOME=str(AUTH_HOME),NEWROGUE_CODEX_REASONING_EFFORT='high')
for name in ['OPENAI_API_KEY','CODEX_API_KEY','OPENAI_API_BASE']:
    env.pop(name,None)
started=time.monotonic()
with (OUT/'public-current-audit.json').open('xb') as stdout,(OUT/'public-current-audit.stderr').open('xb') as stderr:
    process=subprocess.Popen(command,cwd=REPO,env=env,stdout=stdout,stderr=stderr)
    print(json.dumps({'pid':process.pid,'audit_run':RUN,'request_budget':2}),flush=True)
    code=process.wait()
result={'exit_code':code,'elapsed_seconds':time.monotonic()-started,
    'automatic_retry':False,'finished_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
(OUT/'audit-once-result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result),flush=True)
