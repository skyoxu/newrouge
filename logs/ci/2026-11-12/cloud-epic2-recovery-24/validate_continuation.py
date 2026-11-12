"""Check retained real results, immutable business bytes and current packet."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

REPO=Path('/workspace/newrouge');OUT=Path(__file__).resolve().parent
OLD=REPO/'logs/ci/2026-11-12/cloud-epic2-recovery-22'
TARGET=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/work/target-compensation-prepare')
sys.dont_write_bytecode=True;sys.path.insert(0,str(REPO/'scripts/python'))
import _b_route_adoption_review as review
import _b_route_sources as sources

policy,pins=review.policy_observations()
assert policy=='sha256:580ab96f584efecb61e870c1539402d041fcbe3369a293204c6f97f5710da05e' and len(pins)==84
for name,entry in json.loads((OLD/'publication-artifact-manifest.json').read_bytes()).items():
    assert hashlib.sha256((TARGET/name).read_bytes()).hexdigest()==entry['sha256']
base=TARGET/review.location('NativeV15Origin03Compensation01')
for name,entry in json.loads((OLD/'original-records-before.json').read_bytes()).items():
    assert hashlib.sha256((base/name).read_bytes()).hexdigest()==entry['sha256']
assert (base/'segmented/nodes/001/unknown.json').exists()
assert json.loads((base/'segmented/call-limit.json').read_bytes())['model_request_budget']==2
assert json.loads((base/'segmented/review-repair/allowance.json').read_bytes())['cumulative_limit']==3
summary=json.loads((OUT/'windows-actual-summary.json').read_bytes())
run=json.loads((OUT/'windows-final-run-state.json').read_bytes())
assert summary['tests_run']==len(summary['passed_tests'])==4 and summary['status']=='passed'
assert summary['failures']==summary['errors']==summary['skipped']==summary['changed_source_files']==[]
assert run['conclusion']=='success' and run['run_attempt']==1 and run['head_sha']==summary['head']
assert summary['new_model_calls']==0 and summary['real_model_full_chain_qualification'] is False
for name in ['.github/workflows/b-route-runtime-deterministic.yml','scripts/ci/run_b_route_windows_recovery_checks.py']:
    git_bytes=subprocess.check_output(['git','show',run['head_sha']+':'+name],cwd=REPO)
    local=(REPO/name).read_bytes()
    # The repository declares CRLF YAML worktrees and LF Git text blobs.
    assert git_bytes==local.replace(b'\r\n',b'\n') if name.endswith('.yml') else git_bytes==local
clones=json.loads((OUT/'real-clone-observations.json').read_bytes())
assert [v['exit_code'] for v in clones['cases']]==[0,2] and not clones['native_or_review_seams']
assert len(clones['manifest'])==9
for name,entry in clones['manifest'].items():
    raw=(OUT/'published-clone-input'/name).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==entry['sha256']
    assert (TARGET/name).read_bytes()==raw
    assert not name.startswith('logs/')
account=json.loads((OUT/'single-capability-material-result.json').read_bytes())
assert account['exit_code']==0 and account['accounting_complete'] and account['new_model_calls']==0
obs=sources.Observations(REPO)
state,result=sources.load_accounted(obs,account['accounted_ref']);obs.verify()
assert result['accounting_complete'] and result['model_dispatch_count']==0
assert result['source_count']==1 and result['source_block_count']==8 and result['proposal_count']==7
assert (OUT/'singlecap-account.json').is_file()
assert json.loads((OUT/'singlecap-account.json').read_bytes())['exit_code']==1
cap=json.loads((OUT/'single-capability-input/capability.json').read_bytes())
contract=json.loads((OUT/'single-capability-input/planning-contract.pending-audit.json').read_bytes())
assert contract['scope']['kind']=='capability' and contract['scope']['ids']==[cap['capability_id']]
assert not (REPO/contract['audit_ref']).exists()
assert cap['acceptance_context']['historical_completed_item'] is False
assert cap['source']['raw_digest']=='sha256:'+hashlib.sha256((REPO/cap['source']['path']).read_bytes()).hexdigest()
transfer=json.loads((OUT/'artifact-local-transfer-limit.json').read_bytes())
assert transfer['local_materialization_succeeded'] is False and transfer['local_zip_hash_verified'] is False
assert not list((OUT/'windows-artifact').rglob('*.zip')) if (OUT/'windows-artifact').exists() else True
report={'source_policy_unchanged':policy,'source_pins':84,'original34_records_unchanged':True,
    'original10_publication_artifacts_unchanged':True,'old2_plus_additional1_occupied':True,
    'windows_run':run['id'],'windows_head':run['head_sha'],'windows_actual_passed':4,
    'windows_skipped':0,'windows_fixture_upstream':'synthetic','workflow_and_helper_equal_tested_commit':True,
    'genuine_clone_exit_codes':[0,2],'genuine_clone_inputs':9,'fake_native_or_provider_seams':False,
    'current_source_account_complete':True,'current_source_blocks':8,'current_proposals':7,
    'original_account_reference_error_retained':True,'current_independent_audit_complete':False,
    'formal3b_preparation_or_completed_item_minted':False,'new_model_calls':0,
    'local_zip_hash_verified':False,'broad_suite_executed':False,'whole_Epic_acceptance':False}
(OUT/'continuation-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
