"""Preserve our own unexecuted previous-policy preparation, never an unknown."""
import json,hashlib,sys
from pathlib import Path
sys.dont_write_bytecode=True;sys.path.insert(0,'/workspace/newrouge/scripts/python')
import _b_route_adoption_review as review
import _b_route_compensation_segmented_execution as engine
import _planning_apply_journal as journal
OUT=Path(__file__).absolute().parent
ROOT=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/work/target-compensation-prepare')
home=ROOT/review.location('NativeV15Origin03Compensation01')
expected=set(engine.STATIC)|{'segmented/nodes/000/base-prompt.txt','segmented/nodes/001/base-prompt.txt','capability-coordinator.lock'}
files={p.relative_to(home).as_posix():p for p in home.rglob('*') if p.is_file()}
assert set(files)==expected
assert not any(v['operation_id']=='NativeV15Origin03Compensation01' for v in journal.operation_inventory(ROOT))
rows={n:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for n,p in sorted(files.items())}
backup=ROOT.parent/'superseded-unexecuted-segmented-preparation-18a';assert not backup.exists()
home.rename(backup)
assert all(hashlib.sha256((backup/n).read_bytes()).hexdigest()==v['sha256'] for n,v in rows.items())
report={'action':'preserve own known-unexecuted auxiliary data before new policy preparation','original':str(home),'backup':str(backup),'files':rows,
        'business_operation_exists':False,'any_intent_execution_proof_or_call_limit':False,'unknown_released':False,
        'reason':'replace added fixed issuer design with explicit logical limit; original epoch17 pass/failure evidence retained'}
(OUT/'previous-preparation-preservation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='files'},indent=2))
