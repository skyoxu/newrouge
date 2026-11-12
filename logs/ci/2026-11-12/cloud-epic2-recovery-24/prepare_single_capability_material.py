"""Prepare/account genuine current sources for a new single-item input, no model."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time

REPO=Path('/workspace/newrouge');OUT=Path(__file__).resolve().parent
SCOPE='controlled-exclusive-resolution-v15'
RUN='cloud-singlecap-source-20261112'
SOURCE='docs/testing/story-2-5-controlled-acceptance/exclusive-resolution-v15.md'
INPUT=OUT/'single-capability-input'
INPUT.mkdir(exist_ok=False)
def write(name,value):
    target=INPUT/name
    with target.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n')
    return target.relative_to(REPO).as_posix()
raw=(REPO/SOURCE).read_bytes()
source_digest='sha256:'+hashlib.sha256(raw).hexdigest()
source_set=write('source-set.json',{'schema_version':'chapter3.source-set.v1',
    'active_patterns':[SOURCE],'active_sources':[SOURCE],'retirements':[]})
capability_ref=write('capability.json',{'capability_id':SCOPE,
    'title':'Complete exclusive reward resolution controlled planning input',
    'source':{'path':SOURCE,'raw_digest':source_digest,'coverage':'entire original file; no excluded blocks'},
    'acceptance_context':{'purpose':'A new explicit single-Capability input for original Story2.9 controlled acceptance',
        'historical_completed_item':False,'existing_m4_scope_unchanged':True,
        'contract':'Preserve every obligation and delegated choice in the complete source; no Task or implementation is supplied'}})
contract_ref=write('planning-contract.pending-audit.json',{'schema_version':'newrouge.b-route-planning-contract.v1',
    'input_stage':'3b','audit_ref':'logs/ci/2026-11-12/b-route-source-audit/cloud-singlecap-audit-20261112/audit-01/report.json',
    'scope':{'scope_id':SCOPE,'kind':'capability','ids':[SCOPE]},
    'constraints':[{'path':SOURCE,'format':'text'}],
    'contexts':[{'kind':'capability','path':capability_ref,'required':True,'format':'json','absence':None}],
    'limits':{'max_bytes':1048576,'max_input_tokens':96000,'reserved_tokens':2000}})
rows=[]
def run(stage,attempt,*args):
    command=[sys.executable,'-B',str(REPO/'scripts/python/dev_cli.py'),'b-route-sources',
        '--root',str(REPO),'--stage',stage,'--run-id',RUN,'--scope-id',SCOPE,'--attempt-id',attempt,*args]
    start=time.monotonic()
    with (OUT/f'singlecap-{stage}.json').open('xb') as stdout,(OUT/f'singlecap-{stage}.stderr').open('xb') as stderr:
        result=subprocess.run(command,cwd=REPO,stdout=stdout,stderr=stderr)
    value,end=json.JSONDecoder().raw_decode((OUT/f'singlecap-{stage}.json').read_text())
    rows.append({'stage':stage,'command':command,'exit_code':result.returncode,'elapsed_seconds':time.monotonic()-start})
    assert result.returncode==0,value
    return value
prepare=run('prepare','prepare-01','--source-set',source_set)
prepared_ref=prepare['output_ref']+'/prepared.json'
prepared_path=REPO/prepared_ref
if not prepared_path.is_file():
    candidates=[p for p in (REPO/'logs/ci/2026-11-12/b-route-sources'/RUN).rglob('prepared.json')]
    assert len(candidates)==1
    prepared_path=candidates[0];prepared_ref=prepared_path.relative_to(REPO).as_posix()
old=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/data/nx/logs/ci/2026-11-06/b-route-planning-input/i4/ca51aa929b8a29089c302f08eb9c0a7bfd0876026b31d5d7b2dee9b7c939fb48/prepared.json')
original=json.loads(old.read_bytes())['inputs']['global_proof']['candidate']
current=json.loads((prepared_path.parent/'candidate.json').read_bytes())
assert {v['block_id'] for v in original['block_results']}=={v['block_id'] for v in current['block_results']}
proposal=json.loads(json.dumps(original))
proposal['prepared_ref']=prepare['prepared_ref']
candidate_ref=write('candidate.from-original-proposals.json',proposal)
account=run('account','account-01','--prepared',prepared_ref,'--candidate',candidate_ref)
assert account['accounting_complete'] is True
report={'source_path':SOURCE,'current_source_raw_digest':source_digest,'source_bytes':len(raw),
    'new_capability_input_ref':capability_ref,'contract_pending_current_audit':contract_ref,
    'source_set':source_set,'prepared_ref':prepared_ref,'accounted_ref':account['output_ref']+'/report.json',
    'original_first_projection_reused_as_unreviewed_candidate':True,
    'candidate_business_fields_changed':False,'current_block_identity_set_matches_original':True,
    'new_model_calls':0,'new_native_run_created':False,'registry_written':False,
    'historical_m4_relabelled':False,'current_independent_audit_complete':False,
    'formal_3b_preparation_complete':False,'stages':rows}
(OUT/'single-capability-material-result.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
