"""Verify current evidence/state/source invariants without domain actions."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

REPO=Path('/workspace/newrouge')
OUT=Path(__file__).resolve().parent
OLD=REPO/'logs/ci/2026-11-12/cloud-epic2-recovery-22'
ROOT=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/work/target-compensation-prepare')
sys.dont_write_bytecode=True
sys.path.insert(0,str(REPO/'scripts/python'))
import _b_route_adoption_review as review

policy,pins=review.policy_observations()
assert policy==json.loads((OLD/'final-state-audit.json').read_bytes())['source_policy']
assert len(pins)==84
publication=json.loads((OLD/'publication-artifact-manifest.json').read_bytes())
for name,expected in publication.items():
    raw=(ROOT/name).read_bytes()
    assert len(raw)==expected['bytes'] and hashlib.sha256(raw).hexdigest()==expected['sha256']
base=ROOT/review.location('NativeV15Origin03Compensation01')
original=json.loads((OLD/'original-records-before.json').read_bytes())
for name,expected in original.items():
    assert hashlib.sha256((base/name).read_bytes()).hexdigest()==expected['sha256']
assert json.loads((base/'segmented/call-limit.json').read_bytes())['model_request_budget']==2
assert (base/'segmented/nodes/001/unknown.json').is_file()
assert json.loads((base/'segmented/review-repair/allowance.json').read_bytes())['cumulative_limit']==3
observations=json.loads((OUT/'real-public-entry-observations.json').read_bytes())
assert [row['exit_code'] for row in observations['cases']]==[0,2,0]
assert observations['new_model_calls']==observations['business_transitions']==0
payloads={}
for row in observations['cases']:
    text=(OUT/row['output']).read_text()
    value,end=json.JSONDecoder().raw_decode(text)
    assert not text[end:].strip()
    payloads[row['case']]=value
read=payloads['fresh-direct-compensation-read']
resolved=payloads['fresh-dev-original-resolution-read']
inspected=payloads['fresh-dev-compensation-recovery-inspect']
assert read['formal_adoption'] and not any(read[k] for k in ['readiness','runtime_verified','default_b_enabled'])
assert resolved['diagnostics'][0]['actual']=='resolved_by' and resolved['diagnostics'][0]['resume_ref'].endswith('/commit.json')
assert inspected['state']=='complete' and inspected['next_stage'] is None
assert inspected['formal_adoption'] is False
assert not (ROOT/inspected['resume_ref']).with_name('commit.pending.json').exists()
plan=json.loads((ROOT/read['context']['plan_refs'][0]['path']).read_bytes())
assert plan['revision']==2 and len(plan['requirements'])==7
assert {k:len(v) for k,v in plan['definitions'].items()}=={'flows':1,'commands':6,'states':3}
parts=plan['definitions']['flows'][0]['parts']
assert len(parts)==4 and len({part['kind'] for part in parts})==4
policy_record=json.loads((ROOT/'docs/planning/b-route/policy.v1.json').read_bytes())
origins=json.loads((ROOT/'docs/planning/b-route/task-origins.v1.json').read_bytes())
assert origins['tasks']==[] and policy_record['switch_boundary']['default_route']=='A'
native=json.loads((OUT/'native-eligibility-observation.json').read_bytes())
assert native['registry_entries']==0 and native['original_scope']['kind']=='all'
assert native['prepared']['actual_binding_result']['reason']=='b_route_recovery_requires_single_capability_target'
assert native['public_status']['exit_code'] is None and native['public_status']['command_repeated'] is False
for name,digest in native['original_files_before_and_after'].items():
    assert hashlib.sha256((Path(native['native_root'])/name).read_bytes()).hexdigest()==digest
valid_json=0
raw_capture_with_trace=[]
for p in OUT.rglob('*.json'):
    raw=p.read_text()
    value,end=json.JSONDecoder().raw_decode(raw)
    if raw[end:].strip():
        assert p.name=='original-native-public-status.json'
        assert raw[end:].strip().startswith('[dev_cli] running: ')
        raw_capture_with_trace.append(p.name)
    else:
        valid_json+=1
commit='76d3282359a931b2cd249f8dd41250d36c2bbaff'
audited=json.loads((OUT/'commit-input-audit.json').read_bytes())
for name,expected in audited['identities'].items():
    if not name.startswith('logs/'):
        continue
    raw=subprocess.check_output(['git','show',commit+':'+name],cwd=REPO)
    assert hashlib.sha256(raw).hexdigest()==expected['sha256']
report={'first_commit':commit,'branch':'build/cloud-epic2-recovery-20261111',
    'source_policy_unchanged':policy,'source_pins':84,'original34_review_records_unchanged':True,
    'protected10_publication_artifacts_unchanged':True,'old2_plus_additional1_still_occupied':True,
    'new_model_calls':0,'business_transitions':0,'actual_public_exit_codes':[0,2,0],
    'same_receipt_and_plan_revision2':True,'original_resolved_route_preserved':True,
    'recovery_state_complete_next_stage_null':True,'pending_marker_absent':True,
    'formal_zero_Task_chain':True,'default_route':'A','logical_parts':[part['kind'] for part in parts],
    'native_original_inputs_unchanged':True,'native_registry_entries':0,
    'raw_native_status_child_exit_unknown_preserved':True,'json_documents_valid':valid_json,
    'raw_stdout_capture_with_retained_trace':raw_capture_with_trace,
    'old_logged_git_blobs_equal_original_raw_bytes':True,'targeted_tests_reused':56,
    'new_full_suite_or_provider_test':False,'whole_Epic_acceptance':'pending target Windows and real single-Capability native scope'}
(OUT/'continuation-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
