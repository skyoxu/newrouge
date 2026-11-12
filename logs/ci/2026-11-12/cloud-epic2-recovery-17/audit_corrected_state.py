"""Read-only final audit; never a provider, fiscal or business operation."""
from pathlib import Path
import json,sys,hashlib
sys.dont_write_bytecode=True;sys.path.insert(0,'/workspace/newrouge/scripts/python')
import _b_route_adoption_review as review
import _b_route_compensation_segmented_execution as engine
import _planning_apply_journal as journal
OUT=Path(__file__).absolute().parent
ROOT=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/work/target-compensation-prepare')
manifest=json.loads((OUT/'superseded-preparation-preservation.json').read_text())
backup=Path(manifest['backup'])
assert all(hashlib.sha256((backup/n).read_bytes()).hexdigest()==r['sha256'] for n,r in manifest['files'].items())
home=ROOT/review.location('NativeV15Origin03Compensation01')
files=sorted(p.relative_to(home).as_posix() for p in home.rglob('*') if p.is_file())
expected={'capability-coordinator.lock'}|set(engine.STATIC)|{'segmented/nodes/000/base-prompt.txt','segmented/nodes/001/base-prompt.txt'}
assert set(files)==expected
assert not any(v['operation_id']=='NativeV15Origin03Compensation01' for v in journal.operation_inventory(ROOT))
resume=json.loads((OUT/'public-segmented-resume-corrected-01.json').read_text())
assert resume['status']=='blocked'
assert resume['diagnostics'][0]['reason_code']=='dependency_unavailable'
assert resume['diagnostics'][0]['actual']=='compensation_budget_owner_unavailable'
assert not (Path('/workspace/newrouge/scripts/python')/'_b_route_compensation_budget_owner.py').exists()
prior=json.loads(Path('logs/ci/2026-11-12/cloud-epic2-recovery-15/published-prepare-actual-02.json').read_text())
critical={name:'sha256:'+hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest
          for name,digest in prior['original_critical_files_before'].items()}
assert all(critical.values())
report={'corrected_preparation_unchanged_after_read_only_resume':True,'current_auxiliary_files':files,'read_only_resume_coordination_file':'capability-coordinator.lock',
        'old_mismeasured_preparation_bytes_preserved':True,'business_operation_exists':False,
        'node_intents_or_execution':False,'review_proof_exists':False,'budget_owner_installed':False,
        'actual_public_resume':resume,'original_critical_files_unchanged':critical,
        'project_model_calls':0,'financial_actions':0,'unknown_replay_or_release':0}
(OUT/'final-state-audit.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
