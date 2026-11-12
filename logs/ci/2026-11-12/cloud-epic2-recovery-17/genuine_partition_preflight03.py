"""Genuine current owner factory/render; no review publication/model/funding."""
from pathlib import Path
import json,sys,traceback
from unittest.mock import patch
sys.dont_write_bytecode=True;sys.path.insert(0,'/workspace/newrouge/scripts/python')
import _b_route_adoption as adoption
import _b_route_adoption_review as review
import _b_route_compensation_segmented_execution as engine
import _b_route_compact_literal as compact
import _b_route_codec as codec
OUT=Path(__file__).absolute().parent
ROOT=Path('/workspace/newrouge-recovery-data/batch03-05f5fbf9/work/target-compensation-prepare')
observations=[]
original_metric,original_spend=compact._metric,compact._EncodingWork.spend
def metric(*args,**kwargs):
 try:return original_metric(*args,**kwargs)
 except ValueError as error:observations.append({'kind':'retention','message':str(error)});raise
def spend(self,amount=1,*,phase=None):
 try:return original_spend(self,amount,phase=phase)
 except ValueError as error:observations.append({'kind':'work','message':str(error),'charged':self.limit-self.remaining});raise
records={}
def observe_prepare(root,derived):
 records['genuine_factory']=True;records['work_before_spec']=derived.work.limit-derived.work.remaining
 spec=engine._spec(derived);plan=engine._plan(derived.subject,derived.packet,spec)
 records.update(work_after_spec=derived.work.limit-derived.work.remaining,work_limit=derived.work.limit,nodes=[])
 for row,node in zip(spec,plan['nodes'],strict=True):
  (OUT/('epoch03-genuine-'+node['node_id']+'-base.txt')).write_bytes(row['base_prompt'].encode())
  try:
   prompt,schema,request,report=engine._request(derived.subject,derived.packet,plan,node,row['base_prompt'],[])
   (OUT/('epoch03-genuine-'+node['node_id']+'-request.txt')).write_bytes(request.encode())
   records['nodes'].append({'node_id':node['node_id'],'status':'literal_ready','measurement':report,'parent_outputs_present':False})
  except codec.CodecError as error:records['nodes'].append({'node_id':node['node_id'],'status':'blocked','diagnostic':error.diagnostic.to_dict()})
 derived.recheck();policy,pins=review.policy_observations();records.update(source_policy=policy,source_pin_count=len(pins),source_pins=pins)
 return {'status':'observed_genuine_offline_spec','formal_adoption':False,'readiness':False,'runtime_verified':False}
try:
 with patch.object(engine,'prepare',side_effect=observe_prepare),patch.object(compact,'_metric',side_effect=metric),patch.object(compact._EncodingWork,'spend',spend):
  result=adoption.segmented_compensation_review(ROOT,operation_id='NativeV15Origin03Compensation01',stage='prepare',request_ref='logs/ci/b-route-requests/native-v15-origin03-compensation-01/request.json')
 report={'completed':True,'result':result,**records}
except Exception:report={'completed':False,'traceback':traceback.format_exc(),**records}
report.update(resource_refusals=observations,publication_performed=False,model_dispatched=False,budget_action=False,scope='real unchanged owner/guard/spec; only persistence callback observed instead of publishing')
(OUT/'genuine-partition-preflight-03.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k not in ('source_pins','traceback')},indent=2))
