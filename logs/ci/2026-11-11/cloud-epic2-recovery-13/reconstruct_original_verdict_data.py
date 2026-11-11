"""Re-derive saved verdict schema/accounting as DATA without loading the old owner."""
import ast
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
REPO=Path('/workspace/newrouge');sys.path.insert(0,str(REPO/'scripts/python'))
import _b_route_codec as codec
OUT=Path(__file__).absolute().parent
policy=json.loads((OUT/'original-policy-reconstruction.json').read_bytes())
assert policy['original_policy_data_reconstructed']
source=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/work/policy-preimages-reconstructed/scripts/python/_b_route_adoption_review.py')
source_raw=source.read_bytes()
source_pin=next(r['sha256'] for r in policy['source_schema_inputs'] if r['relative_path']=='scripts/python/_b_route_adoption_review.py')
assert hashlib.sha256(source_raw).hexdigest()==source_pin
tree=ast.parse(source_raw.decode('utf-8-sig'))
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='obligations')
values=next(ast.literal_eval(n.value) for n in fn.body if isinstance(n,ast.Assign)
 and any(isinstance(t,ast.Name) and t.id=='values' for t in n.targets))
extra=next(ast.literal_eval(n.value) for branch in fn.body if isinstance(branch,ast.If)
 for n in branch.body if isinstance(n,ast.AugAssign) and isinstance(n.target,ast.Name) and n.target.id=='values')
H='98aa98a912402629817c45fc29be487f6e15f97460110c8527694fcf1a9c4659'
home=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/data/target/logs/ci/b-route-adoption-reviews')/H
subject=codec.strict_json_loads((home/'subject.json').read_bytes())
assert subject['schema_version']=='newrouge.b-route-adoption-review-subject.v3'
assert subject['policy_identity']==policy['v3_policy_digest']
# Original v3 branch, target indexes and explicit identity-alignment families.
values+=extra
values+=['target:'+str(i) for i,_ in enumerate(subject['preview']['targets'])]
for family in ('requirements','flows'):
 values += [family+':'+row['candidate_id'] for row in subject['request']['material']['identity_alignment'][family]]
values=sorted(values)
fields={'schema_version':{'type':'string','const':'newrouge.b-route-adoption-review-verdict.v3'},
 'subject_digest':{'type':'string','const':codec.canonical_digest(subject)},
 'verdict':{'type':'string','enum':['approved','blocked']},
 'findings':{'type':'array','items':{'type':'string','minLength':1}},
 'checks':{'type':'array','minItems':len(values),'maxItems':len(values),
  'items':{'type':'object','additionalProperties':False,'properties':{
   'id':{'type':'string','enum':values},'verdict':{'type':'string','enum':['approved','blocked']},
   'rationale':{'type':'string','minLength':1}},'required':['id','verdict','rationale']}}}
schema={'type':'object','additionalProperties':False,'properties':fields,'required':list(fields)}
raw=(json.dumps(schema,ensure_ascii=False,allow_nan=False,indent=2)+'\n').encode('utf-8')
saved=(home/'w/schema.json').read_bytes()
assert raw==saved,'Exact original schema bytes must match; no adaptive rewriting.'
output=codec.strict_json_loads((home/'w/output.json').read_bytes())
import jsonschema
jsonschema.Draft202012Validator(schema).validate(output)
checks=output['checks']
assert len({r['id'] for r in checks})==len(checks) and {r['id'] for r in checks}==set(values)
assert all(r['rationale'].strip() for r in checks)
blocked=[r['rationale'] for r in checks if r['verdict']=='blocked']
assert len(set(output['findings']))==len(output['findings']) and set(output['findings'])==set(blocked)
assert (output['verdict']=='blocked')==bool(blocked)
assert not blocked and output['verdict']=='approved'
report={'schema':'newrouge.original-verdict-schema-accounting-data.v1','source_raw_sha256':source_pin,
 'original_policy_digest':policy['v3_policy_digest'],'source_read_mode':'AST literals plus explicit original data formula; old module not compiled/imported/executed',
 'saved_schema_exact_raw_match':True,'saved_schema_bytes':len(saved),'saved_schema_raw_digest':codec.raw_digest(saved),
 'rederived_required_check_count':len(values),'rederived_required_check_ids':values,
 'recorded_verdict':output['verdict'],'check_accounting_matches_original_rule':True,'unresolved_findings':len(blocked),
 'original_prompt_or_public_semantics_rederived':False,'original_owner_execution_authenticated':False,
 'original_native_execution_authenticated':False,'new_authority_granted':False,'new_model_calls':0,
 'qualification':'Exact original verdict schema and saved-check denominator/accounting DATA only; not a new semantic review, old-owner execution or compensation authentication.'}
(OUT/'original-verdict-schema-accounting.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({k:report[k] for k in ('saved_schema_exact_raw_match','saved_schema_bytes','rederived_required_check_count','recorded_verdict','unresolved_findings','original_owner_execution_authenticated','new_authority_granted')},indent=2))
