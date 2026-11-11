"""Reconstruct old policy DATA from an exact handed-off build string and pinned bytes."""
import ast
import datetime
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
REPO=Path('/workspace/newrouge');sys.path.insert(0,str(REPO/'scripts/python'))
import _b_route_codec as codec
OUT=Path(__file__).absolute().parent
BASE=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9')
source_report=json.loads((REPO/'logs/ci/2026-11-11/cloud-epic2-recovery-11/policy-preimages-restoration.json').read_bytes())
ROOT=Path(source_report['output_data_directory'])
VERSION='3.12.10 (tags/v3.12.10:0cc8128, Apr  8 2025, 12:21:36) [MSC v.1943 64 bit (AMD64)]'
provenance={'schema':'newrouge.historical-policy-input-handoff.v1',
 'value':VERSION,'field':'/python_version',
 'reported_original_source':r'C:\Users\Administrator\Documents\Codex\2026-11-05\task\r62\scripts\python\qualified-historical-owner-authority.v2.json',
 'receipt_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'source_kind':'Exact original file field provided in trusted parent delegation after bounded original-side read-only recovery',
 'whole_original_resource_received':False,'whole_original_resource_raw_digest':None,
 'current_sys_version_used':False,'fresh_original_interpreter_observation':False,
 'owner_or_compensation_authority_granted':False}
(OUT/'historical-python-version-input.json').write_text(json.dumps(provenance,indent=2)+'\n')
raws={}
checks=[]
for row in source_report['files']:
 raw=(ROOT/row['relative_path']).read_bytes();h=hashlib.sha256(raw).hexdigest()
 assert h==row['restored_raw_sha256']==row['recorded_Host3_sha256']
 raws[row['relative_path']]=raw
 checks.append({'relative_path':row['relative_path'],'bytes':len(raw),'sha256':h})
assert len(raws)==51
# Read only literal lists in the retained policy; never compile or execute old code.
review=ast.parse(raws['scripts/python/_b_route_adoption_review.py'].decode('utf-8-sig'))
def assigned(tree,name):
 for node in tree.body:
  if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets):return ast.literal_eval(node.value)
 raise KeyError(name)
def names(fn):return assigned(next(n for n in review.body if isinstance(n,ast.FunctionDef) and n.name==fn),'names')
base_names=names('policy_identity');v3_names=names('policy_identity_v3')
schemas=ast.parse(raws['scripts/python/_b_route_schema_resources.py'].decode('utf-8-sig'))
schema_names=assigned(schemas,'FORMAL')+assigned(schemas,'AUXILIARY')
base={'python':VERSION,'sources':{name:codec.raw_digest(raws['scripts/python/'+name]) for name in base_names},
 'schemas':{**{name:codec.raw_digest(raws['docs/planning/b-route/schemas/'+name+'.schema.json']) for name in schema_names},
 'commit-intent.schema.json':codec.raw_digest(raws['docs/planning/b-route/schemas/commit-intent.schema.json'])}}
base_digest=codec.canonical_digest(base)
v3={'schema_version':'newrouge.b-route-adoption-review-policy.v3','review_profile':'expanded-semantics.v3',
 'base_policy':base_digest,'v3_sources':{name:codec.raw_digest(raws['scripts/python/'+name]) for name in v3_names}}
actual=codec.canonical_digest(v3)
H='98aa98a912402629817c45fc29be487f6e15f97460110c8527694fcf1a9c4659'
review_home=BASE/'data/target/logs/ci/b-route-adoption-reviews'/H
subject=codec.strict_json_loads((review_home/'subject.json').read_bytes())
proof=codec.strict_json_loads((review_home/'review.json').read_bytes())
host=codec.strict_json_loads((BASE/'data/task/story29-host3-allocation-Root-01/config.json').read_bytes())
binding=codec.strict_json_loads((BASE/'data/target/logs/ci/b-route-retained-executions'/H/'binding.json').read_bytes())
commit_path=BASE/'data/target/logs/ci/b-route-operations/operations'/H/'commit.json'
commit=codec.strict_json_loads(commit_path.read_bytes())
base_matches=commit['policy_identity']==base_digest
expected={'original_subject':subject['policy_identity'],'original_proof':proof['policy_identity'],
 'original_Host3_binding':host['binding']['policy_identity'],'original_retained_binding':binding['consumer_policy_identity']}
matches={name:value==actual for name,value in expected.items()}
report={'schema':'newrouge.original-policy-reconstruction-data.v1','input_provenance':'historical-python-version-input.json',
 'original_source_snapshot':source_report['source_snapshot'],'source_schema_inputs':checks,
 'base_policy_preimage':base,'base_policy_digest':base_digest,'v3_policy_preimage':v3,'v3_policy_digest':actual,
 'recorded_policy_identities':expected,'matches':matches,'original_policy_data_reconstructed':all(matches.values()),
 'base_policy_matches_original_commit':{'recorded_policy_identity':commit['policy_identity'],
     'matches':base_matches,'path':str(commit_path)},
 'original_owner_execution_authenticated':False,'original_native_execution_authenticated':False,
 'cloud_authority_installed':False,'new_authority_granted':False,'old_code_executed':False,
 'old_interpreter_executed':False,'current_interpreter_identity_substituted':False,
 'new_project_model_calls':0,'financial_writes':0,
 'remaining12_originals_status':'Original-side existence/hash matches reported by parent; public upload rejected by risk review and awaiting specific file-risk confirmation. Bytes not received in Cloud; no transfer retry or alternate channel.',
 'qualification':'Exact reconstruction of recorded policy DATA preimage/digest only. No full authority resource or old-owner execution identity is authenticated or installed; no compensation eligibility is granted.'}
(OUT/'original-policy-reconstruction.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'base_policy_digest':base_digest,'v3_policy_digest':actual,'matches':matches,
 'original_policy_data_reconstructed':all(matches.values()),'original_owner_execution_authenticated':False,
 'new_authority_granted':False},indent=2))
assert all(matches.values()) and base_matches,'Reconstructed policy must match every original recorded identity; never substitute or install on mismatch.'
