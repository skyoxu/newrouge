"""Check actual saved DATA; never execute/mint an original owner or authorize apply."""
import ast
import hashlib
import json
from pathlib import Path, PureWindowsPath
import subprocess
import sys

sys.dont_write_bytecode=True
REPO=Path('/workspace/newrouge')
sys.path.insert(0,str(REPO/'scripts/python'))
import _b_route_codec as codec
import _planning_apply_journal as journal
from _b_route_qualified_historical_v3_protocol import SAVED_SUPPORT, check_saved_review_bindings

OUT=Path(__file__).absolute().parent
ROOT=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9')
DATA=ROOT/'data'
TARGET=DATA/'target'
OP='NativeV15Origin03'
KEY=hashlib.sha256(OP.encode()).hexdigest()
HOME='logs/ci/b-route-adoption-reviews/'+KEY
observed={}
def read_target(name):
 raw=codec.read_reference_bytes(TARGET,name)
 observed[name]=raw
 return raw
operation=journal.read_operation(TARGET,operation_id=OP)
read_target(journal._operation_ref(OP))
buffers={name:read_target(HOME+'/'+name) for name in (*SAVED_SUPPORT,'review.json')}
report=check_saved_review_bindings(operation,buffers)
subject=codec.strict_json_loads(buffers['subject.json'])
st=TARGET.stat()
report['historical_target_identity_recorded']=subject['origin_capsule']['target_identity']
report['current_target_identity']={'path':str(TARGET),'device':st.st_dev,'inode':st.st_ino}
report['checked_current_buffers']=[{'path':name,'raw_digest':codec.raw_digest(raw),'bytes':len(raw)} for name,raw in observed.items()]
report['current_replay_sources']={name:codec.raw_digest((REPO/'scripts/python'/name).read_bytes()) for name in (
 '_b_route_qualified_historical_v3_protocol.py','_planning_execution_binding.py','_codex_app_server.py','_b_route_codec.py')}
report['old_code_executed']=False
report['model_dispatched']=False
report['compensation_integration_changed']=False
for name,raw in observed.items(): assert codec.read_reference_bytes(TARGET,name)==raw
report['observed_original_buffers_unchanged']=True
(OUT/'actual-saved-review-data.json').write_text(json.dumps(report,indent=2)+'\n')

# Literal source inspection and Git blob reads only, never an old module import.
REF='origin/migration/newrogue-20261111/r56-frozen-story27'
def git_bytes(name):return subprocess.check_output(['git','show',f'{REF}:{name}'],cwd=REPO)
def literals(tree,keys):
 result={}
 for node in tree.body:
  if isinstance(node,ast.Assign):
   for target in node.targets:
    if isinstance(target,ast.Name) and target.id in keys:result[target.id]=ast.literal_eval(node.value)
 return result
review_tree=ast.parse(git_bytes('scripts/python/_b_route_adoption_review.py').decode('utf-8-sig'))
selected=[]
for fn_name in ('policy_identity','policy_identity_v3'):
 fn=next(n for n in review_tree.body if isinstance(n,ast.FunctionDef) and n.name==fn_name)
 selected.extend(literals(fn,{'names'})['names'])
schema_tree=ast.parse(git_bytes('scripts/python/_b_route_schema_resources.py').decode('utf-8-sig'))
schemas=literals(schema_tree,{'FORMAL','AUXILIARY'})
needed={f'scripts/python/{n}' for n in selected}
needed.update(f'docs/planning/b-route/schemas/{n}.schema.json' for n in schemas['FORMAL']+schemas['AUXILIARY'])
needed.add('docs/planning/b-route/schemas/commit-intent.schema.json')
config=json.loads((DATA/'task/story29-host3-allocation-Root-01/config.json').read_bytes())['binding']
source_root=PureWindowsPath(config['source_root'])
pins={PureWindowsPath(row['path']).relative_to(source_root).as_posix():row['sha256'] for row in config['source_files']}
checks=[]
for name in sorted(needed):
 actual=hashlib.sha256(git_bytes(name)).hexdigest()
 checks.append({'relative_path':name,'actual_snapshot_sha256':actual,'recorded_Host3_sha256':pins.get(name),'matches':actual==pins.get(name)})
index=json.loads((ROOT/'transport/FILE_INDEX.json').read_bytes())
by_source={row['source_task_relative']:row for row in index['original_files']}
by_digest={}
for row in index['original_files']:by_digest.setdefault(row['sha256'],[]).append(row['archive_path'])
fixed=json.loads((REPO/'logs/ci/2026-11-11/cloud-epic2-recovery-07/historical-producer-fixed-inputs.json').read_bytes())
controls=[]
for row in fixed['original_fixed_inputs']:
 found=by_source.get(row['task_relative_path'])
 controls.append({'task_relative_path':row['task_relative_path'],'expected_raw_sha256':row['expected_raw_sha256'],
  'indexed_source_mapping':found['archive_path'] if found else None,
  'same_raw_bytes_at_indexed_paths':by_digest.get(row['expected_raw_sha256'],[])})
closure={'original_R56_source_snapshot':subprocess.check_output(['git','rev-parse',REF],cwd=REPO,text=True).strip(),
 'policy_source_schema_files_checked':len(checks),'policy_source_schema_matches_recorded_Host3':sum(v['matches'] for v in checks),
 'source_schema_checks':checks,'recorded_policy_identity':config['policy_identity'],
 'original_policy_reconstructed':False,'unresolved_policy_input':{
  'field':'original full sys.version string','used_by':'original R56 _b_route_adoption_review.policy_identity',
  'known_resource':'original populated r62/scripts/python/qualified-historical-owner-authority.v2.json:/python_version',
  'current_migrated_resource':'intentional null template','substitution_allowed':False,
  'meaning':'A recorded policy digest, executable path/hash or numeric3.12.10 alone is not that original string; do not guess it or use current Python.'},
 'old_producer_controls':controls,'control_resolution_scope':'Required fixed reads of the selected R56 _original_controls/_execution route, not a general Story prerequisite. Check covers FILE_INDEX source mappings and all indexed raw digests; it does not claim to have searched every encoded nested payload.',
 'original_owner_execution_authenticated':False,'new_authority_granted':False,
 'outcome':'Available review DATA is consistent, but neither full original policy nor actual original-owner/native execution authentication is established. Do not replace the old history handle or grant compensation.'}
(OUT/'actual-policy-control-closure.json').write_text(json.dumps(closure,indent=2)+'\n')
print(json.dumps({'saved_review_bindings':'passed','original_owner_execution_authenticated':False,
 'new_authority_granted':False,'policy_source_schema_files_checked':len(checks),
 'policy_source_schema_matches_recorded_Host3':closure['policy_source_schema_matches_recorded_Host3'],
 'fixed_controls_with_index_mapping':sum(v['indexed_source_mapping'] is not None for v in controls),
 'fixed_controls_with_other_indexed_raw_match':sum(bool(v['same_raw_bytes_at_indexed_paths']) for v in controls)},indent=2))
