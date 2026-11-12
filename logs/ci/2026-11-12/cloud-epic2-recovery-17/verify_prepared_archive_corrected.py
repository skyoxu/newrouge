"""Read-only genuine prepared archive verification; no issuer or model action."""
import json,hashlib,sys,subprocess
from pathlib import Path
sys.dont_write_bytecode=True;sys.path.insert(0,'/workspace/newrouge/scripts/python')
import _b_route_codec as codec
import _b_route_adoption_review as review
import _b_route_qualified_compensation_review_v2 as qualified
import _b_route_compensation_segmented_execution as engine
import _b_route_compensation_segment_funding as funding
OUT=Path(__file__).absolute().parent;ROOT=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/work/target-compensation-prepare')
subject=qualified.read_subject(ROOT,'NativeV15Origin03Compensation01');home,plan,packet=engine._saved(ROOT,subject)
prepared=json.loads((OUT/'public-segmented-prepare-corrected-01.json').read_text());rows=[]
for node,previous in zip(plan['nodes'],prepared['nodes'],strict=True):
 directory=engine._dir(home,node);base=engine._read(ROOT,directory+'/base-prompt.txt').decode()
 prompt,schema,request,measurement=engine._request(subject,packet,plan,node,base,[])
 assert previous['measurement']==measurement
 (OUT/('corrected-prepared-'+node['node_id']+'-literal-request.txt')).write_bytes(request.encode())
 rows.append({'node_id':node['node_id'],'complete_literal_request_bytes':measurement['request_bytes'],'measurement_matches_actual_public_prepare':True,'actual_parent_outputs_present':False,
              'intent_exists':engine._exists(ROOT,directory+'/intent.json'),'execution_exists':engine._exists(ROOT,directory+'/execution.json')})
try:
 funding.capture(ROOT,plan,read_only=True)
 budget={'status':'unexpected_issuer_available'}
except codec.CodecError as error:
 budget={'status':'dependency_unavailable','diagnostic':error.diagnostic.to_dict(),'read_only':True}
old=json.loads(Path('logs/ci/2026-11-12/cloud-epic2-recovery-15/published-prepare-actual-02.json').read_text())
raw=lambda data:'sha256:'+hashlib.sha256(data).hexdigest()
critical={name:raw((ROOT/name).read_bytes())==digest for name,digest in old['original_critical_files_before'].items()}
policy,pins=review.policy_observations();assert subject['policy_identity']==policy
(OUT/'corrected-prepared-plan.json').write_bytes(review.raw(plan));(OUT/'corrected-prepared-source-pins.json').write_bytes(review.raw(pins))
report={'prepared_actual':True,'node_count':len(plan['nodes']),'required_checks_total':sum(len(n['check_ids']) for n in plan['nodes']),'nodes':rows,
 'source_policy':policy,'source_pin_count':len(pins),'all_current_source_pins_match':all(raw(Path(n).read_bytes())==d for n,d in pins.items()),
 'original_critical_files_unchanged':critical,'budget_dependency':budget,'new_real_model_calls':0,'new_financial_actions':0,
 'workflow_raw_equal_HEAD':Path('workflow.md').read_bytes()==subprocess.check_output(['git','show','HEAD:workflow.md']),
 'publication_scope':'auxiliary review subject/plan only; no business journal, host_review_ref or semantic approval'}
(OUT/'corrected-prepared-archive-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
