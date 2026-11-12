"""Consume a real sealed repair proof through the existing public commit owner."""
from pathlib import Path
import datetime
import json
import subprocess
import sys
import time

REPO=Path('/workspace/newrouge');OUT=Path(__file__).resolve().parent
ROOT=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/work/target-compensation-prepare')
OP='NativeV15Origin03Compensation01'
executed=json.loads((OUT/'public-repair-execute.json').read_bytes())
sealed=json.loads((OUT/'public-review-complete.json').read_bytes())
assert executed['status']=='review_repair_executed' and executed['new_logical_calls']==1
assert sealed['status']=='reviewed' and sealed['host_review_ref']['schema_version']=='newrouge.b-route-compensation-segmented-proof.v2'
request_ref='logs/ci/b-route-requests/native-v15-origin03-compensation-01/request.with-reviewed-repair.json'
request=json.loads((ROOT/'logs/ci/b-route-requests/native-v15-origin03-compensation-01/request.json').read_bytes())
assert 'host_review_ref' not in request
request['host_review_ref']=sealed['host_review_ref']
with (ROOT/request_ref).open('x',encoding='utf-8') as stream:
    json.dump(request,stream,ensure_ascii=False,indent=2);stream.write('\n')
rows=[];started=time.monotonic()
for stage in ('prepare','reserve','apply','verify','publish','read'):
    command=[sys.executable,'-B',str(REPO/'scripts/python/dev_cli.py'),'b-route-adoption',
        '--root',str(ROOT),'--stage',stage,'--operation-id',OP]
    if stage=='prepare':command+=['--request',request_ref]
    if stage=='read':command+=['--context']
    mark=time.monotonic()
    with (OUT/('public-compensation-'+stage+'.json')).open('xb') as stdout, \
         (OUT/('public-compensation-'+stage+'.stderr')).open('xb') as stderr:
        process=subprocess.Popen(command,cwd=REPO,stdout=stdout,stderr=stderr)
        print(json.dumps({'stage':stage,'pid':process.pid,'model_dispatch':False}),flush=True)
        code=process.wait()
    row={'stage':stage,'command':command,'exit_code':code,'elapsed_seconds':time.monotonic()-mark}
    rows.append(row)
    (OUT/'compensation-progress.json').write_text(json.dumps({'stages':rows,'model_calls':0},indent=2)+'\n')
    print(json.dumps({'stage':stage,'exit_code':code,'elapsed_seconds':row['elapsed_seconds']}),flush=True)
    if code:break
report={'operation_id':OP,'stages':rows,'all_public_stages_succeeded':len(rows)==6 and all(r['exit_code']==0 for r in rows),
    'elapsed_seconds':time.monotonic()-started,'model_calls':0,'automatic_retry':False,
    'observed_at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
(OUT/'compensation-result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report),flush=True)
