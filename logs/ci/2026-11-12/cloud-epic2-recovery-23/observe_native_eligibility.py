"""Read original native DATA and current eligibility without registering it."""
from pathlib import Path
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time

REPO = Path('/workspace/newrouge')
OUT = Path(__file__).resolve().parent
ROOT = Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/data/nx')
sys.dont_write_bytecode = True
sys.path.insert(0,str(REPO/'scripts/python'))
import _b_route_completed_reuse as reuse
import _planning_skill_common as common

def sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            digest.update(chunk)
    return digest.hexdigest()

run_path=ROOT/'logs/ci/mvg-planning/m4/run.json'
registry_path=ROOT/'logs/ci/mvg-recovery/registry.json'
before={str(p.relative_to(ROOT)):sha(p) for p in (run_path,registry_path)}
state=json.loads(run_path.read_bytes())
registry=json.loads(registry_path.read_bytes())
selected=state['capability_selection']['selected']
assert len(selected)==1
scope=selected[0]['record']['scope']
assert scope['scope']['kind']=='all'
assert registry['epoch']==0 and registry['entries']==[]
prepared_path=ROOT/state['planning_runtime']['prepared_ref']
prepared_fact={'path':str(prepared_path.relative_to(ROOT)),'exists':prepared_path.is_file()}
if prepared_path.is_file():
    raw=prepared_path.read_bytes()
    prepared_fact.update(raw_digest='sha256:'+hashlib.sha256(raw).hexdigest(),bytes=len(raw))
    frozen=json.loads(raw)
    assert common.canonical_sha(frozen)==state['planning_runtime']['frozen_sha256']
    assert frozen['inputs']['contract']['scope']==scope['scope']
    target=OUT/'original-native-binding-input/b-route-prepared.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        assert target.read_bytes()==raw
    else:
        with target.open('xb') as stream:
            stream.write(raw)
    try:
        reuse.binding(target.parent,scope)
    except ValueError as error:
        prepared_fact['actual_binding_result']={'status':'not_eligible','reason':str(error)}
        assert str(error)=='b_route_recovery_requires_single_capability_target'
    else:
        raise AssertionError('Original all-scope DATA must not become a single Capability')

command=[sys.executable,'-B',str(REPO/'scripts/python/dev_cli.py'),'plan-mvg',
         '--repo-root',str(ROOT),'--stage','status','--run-id','m4','--input-stage','3b',
         '--prepared-ref',state['planning_runtime']['prepared_ref'],'--planning-profile','3b-mvg-v1']
started=time.monotonic()
if (OUT/'original-native-public-status.json').exists():
    # The first observation completed before this reporter rejected dev-cli's
    # trailing command trace. Preserve it and do not repeat the public command.
    result_code=None
    result_note='Original stdout retained; child exit was not saved before reporter parse error'
else:
    with (OUT/'original-native-public-status.json').open('xb') as stdout,(OUT/'original-native-public-status.stderr').open('xb') as stderr:
        result=subprocess.run(command,cwd='/tmp',stdout=stdout,stderr=stderr)
    result_code=result.returncode
    result_note='Fresh original observation'
    (OUT/'original-native-public-status-exit.json').write_text(json.dumps({'exit_code':result_code})+'\n')
stdout_text=(OUT/'original-native-public-status.json').read_text()
payload,decoded_end=json.JSONDecoder().raw_decode(stdout_text)
assert payload['status']=='blocked'
assert result_code in (None,2)
assert all(sha(ROOT/name)==digest for name,digest in before.items())
unchanged=[]
for name in ['_b_route_completed_reuse.py','_mvg_capability_recovery.py','_mvg_capability_checkpoint.py',
             '_mvg_capability_selection.py','_mvg_global_audit.py','_b_route_planning_runtime.py','plan_mvg.py',
             'tests/test_b_route_completed_reuse.py']:
    path='scripts/python/'+name
    original=subprocess.check_output(['git','show','f94847e2b7b4d5092984294b46a2905212528f30:'+path],cwd=REPO)
    assert original==(REPO/path).read_bytes()
    unchanged.append({'path':path,'sha256':hashlib.sha256(original).hexdigest()})
report={'native_root':str(ROOT),'original_files_before_and_after':before,
    'run_id':'m4','phase':state['phase'],'selection_status':state['selection_status'],
    'selected_items':len(selected),'original_scope':scope['scope'],
    'checkpoint':selected[0]['checkpoint'],'registry_epoch':registry['epoch'],
    'registry_entries':0,'prepared':prepared_fact,'registration_attempted':False,
    'partial_or_all_scope_relabelled':False,'original_inputs_modified':False,
    'historical_campaign_limit':state.get('b_route_campaign_funding',{}).get('campaign_limit'),
    'old_native_logical_calls':state['capability_selection']['total_invocations'],
    'old_native_calls_are_not_new_allowance':True,'new_model_calls':0,
    'public_status':{'command':command,'cwd':'/tmp','exit_code':result_code,'exit_observation':result_note,
        'postprocessing_elapsed_seconds':time.monotonic()-started,'output':payload,
        'trailing_command_trace_retained':bool(stdout_text[decoded_end:].strip()),'command_repeated':False},
    'environment':{'os_name':os.name,'system':platform.system(),'release':platform.release(),
        'wine':shutil.which('wine'),'qemu':shutil.which('qemu-system-x86_64'),
        'kvm':Path('/dev/kvm').exists(),'pwsh':shutil.which('pwsh'),'powershell':shutil.which('powershell')},
    'native_initialization_current_contract':'_b_route_planning_runtime._publish_new_run requires os.name == nt',
    'native_Source_tests_unchanged_since_original_checkpoint':unchanged,
    'qualification':'Original DATA eligibility and actual blocked public observation; no current native authentication, positive reuse or Windows acceptance claim'}
(OUT/'native-eligibility-observation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k not in {'native_Source_tests_unchanged_since_original_checkpoint','checkpoint'}},indent=2))
