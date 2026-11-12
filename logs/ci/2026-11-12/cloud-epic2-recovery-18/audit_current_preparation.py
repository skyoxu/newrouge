"""Read-only current preparation audit after no-limit execute; no fiscal owner."""
from pathlib import Path
import json,hashlib,sys,subprocess
sys.dont_write_bytecode=True;sys.path.insert(0,'/workspace/newrouge/scripts/python')
import _b_route_adoption_review as review
import _b_route_compensation_segmented_execution as engine
import _b_route_qualified_compensation_review_v2 as qualified
import _planning_apply_journal as journal
OUT=Path(__file__).absolute().parent
ROOT=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/work/target-compensation-prepare')
subject=qualified.read_subject(ROOT,'NativeV15Origin03Compensation01');home,plan,packet=engine._saved(ROOT,subject)
actual=json.loads((OUT/'public-execute-without-limit-01.json').read_text())
assert actual['status']=='blocked' and actual['reason']=='authorization_required'
assert actual['required_lifetime_logical_calls']==2 and not actual['model_dispatched']
assert not engine._exists(ROOT,home+'/'+engine.ADMISSION)
expected=set(engine.STATIC)|{'segmented/nodes/000/base-prompt.txt','segmented/nodes/001/base-prompt.txt','capability-coordinator.lock'}
files={p.relative_to(ROOT/home).as_posix() for p in (ROOT/home).rglob('*') if p.is_file()};assert files==expected
assert not any(v['operation_id']=='NativeV15Origin03Compensation01' for v in journal.operation_inventory(ROOT))
prepared=json.loads((OUT/'public-prepare-01.json').read_text());nodes=[]
for node,saved in zip(plan['nodes'],prepared['nodes'],strict=True):
 base=engine._read(ROOT,engine._dir(home,node)+'/base-prompt.txt').decode()
 prompt,schema,request,report=engine._request(subject,packet,plan,node,base,[])
 assert report==saved['measurement']
 nodes.append({'node':node['node_id'],'checks':node['check_ids'],'full_rpc_bytes':report['request_bytes'],'counter':report['token_counter'],'actual_parent_outputs_present':False})
policy,pins=review.policy_observations();assert subject['policy_identity']==policy
old=json.loads(Path('logs/ci/2026-11-12/cloud-epic2-recovery-15/published-prepare-actual-02.json').read_text())
critical={name:'sha256:'+hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest for name,digest in old['original_critical_files_before'].items()};assert all(critical.values())
backup=json.loads((OUT/'previous-preparation-preservation.json').read_text());preserved=all(hashlib.sha256((Path(backup['backup'])/n).read_bytes()).hexdigest()==r['sha256'] for n,r in backup['files'].items());assert preserved
(OUT/'actual-plan.json').write_bytes(review.raw(plan));(OUT/'actual-source-pins.json').write_bytes(review.raw(pins))
report={'current_preparation_and_no_limit_execute_verified':True,'actual_execute':actual,'node_count':len(nodes),'nodes':nodes,
        'source_policy':policy,'source_pin_count':len(pins),'all_current_source_pins_match':all('sha256:'+hashlib.sha256(Path(p).read_bytes()).hexdigest()==d for p,d in pins.items()),
        'no_admission_or_intent_or_execution_or_review_proof':True,'new_business_operation_exists':False,'budget_factory_module_deleted':not Path('scripts/python/_b_route_compensation_segment_funding.py').exists(),
        'original_critical_files_unchanged':critical,'previous_preparation_bytes_preserved':preserved,
        'workflow_raw_equal_HEAD':Path('workflow.md').read_bytes()==subprocess.check_output(['git','show','HEAD:workflow.md']),
        'real_project_model_calls':0,'financial_actions':0,'unknown_replay_or_release':0}
(OUT/'actual-state-audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
