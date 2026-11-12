"""Preserve only this session's unexecuted mismeasured auxiliary preparation."""
import json,hashlib,sys
from pathlib import Path
sys.dont_write_bytecode=True;sys.path.insert(0,'/workspace/newrouge/scripts/python')
import _planning_apply_journal as journal
import _b_route_adoption_review as review
import _b_route_compensation_segmented_execution as engine
ROOT=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/work/target-compensation-prepare')
OUT=Path(__file__).absolute().parent
home=ROOT/review.location('NativeV15Origin03Compensation01')
expected=set(engine.STATIC)|{'segmented/nodes/000/base-prompt.txt','segmented/nodes/001/base-prompt.txt'}
actual={p.relative_to(home).as_posix() for p in home.rglob('*') if p.is_file()}
assert actual==expected
assert not any(v['operation_id']=='NativeV15Origin03Compensation01' for v in journal.operation_inventory(ROOT))
assert not (home/'review.json').exists()
rows={name:{'bytes':(home/name).stat().st_size,'sha256':hashlib.sha256((home/name).read_bytes()).hexdigest()} for name in sorted(actual)}
backup=ROOT.parent/'superseded-unexecuted-segmented-preparation-17a'
assert not backup.exists();home.rename(backup)
assert all(hashlib.sha256((backup/n).read_bytes()).hexdigest()==r['sha256'] for n,r in rows.items())
report={'action':'relocated own auxiliary preparation to immutable evidence backup','original_namespace':str(home),'backup':str(backup),
 'reason':'previous ready used workspace prompt instead of complete prompt/output_schema JSON; not accepted as final admission',
 'files':rows,'original_business_operation_exists':False,'any_node_intent_or_execution':False,'host_review_ref_exists':False,
 'model_calls':0,'budget_actions':0,'unknown_released':False,'new_operation_id_created':False,'same_id_can_be_prepared_with_correct_contract':True}
(OUT/'superseded-preparation-preservation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='files'},indent=2))
