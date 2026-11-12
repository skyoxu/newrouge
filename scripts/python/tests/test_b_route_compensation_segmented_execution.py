"""Synthetic DATA tests, not original-owner/model/fiscal qualification.

Only the unavailable business partition/material and genuine budget factories
are replaced. The finite consumer, durable files, request counter, schema,
App Server replay, execution proof and continuation paths run their real code.
No external model, account, credentials or original ledger is accessed.
"""
import base64
from copy import deepcopy
from contextlib import ExitStack
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
import os
from unittest.mock import patch

import _b_route_compensation_segmented_execution as engine
import _b_route_compensation_segment_funding as funding
import _b_route_adoption_review as review
import _b_route_qualified_compensation_review_v2 as qualified
import _b_route_codec as codec
import _b_route_compact_literal as compact
import _codex_app_server as transport
from _b_route_compensation_review_profiles import PUBLISHED
from fixtures.codex_app_server_protocol import protocol,encoded


class DataBudget:
    def __init__(self):
        self.rows={};self.reserves=[];self.completed=[];self.unknowns=[]
        self.limit=3;self.reserve_fault=False;self.complete_fault=False
    def recheck(self,root,plan):pass
    def reserve(self,key,identity,remaining):
        if len(self.rows)+remaining>self.limit:raise ValueError('DATA budget cannot fund finite remainder')
        if key in self.rows:raise ValueError('DATA duplicate reservation')
        ref={'path':'DATA/ledger/'+key[7:],'schema_version':'DATA.reservation','raw_digest':key}
        self.rows[key]={'ref':ref,'identity':deepcopy(identity),'outcome':None,'state':'reserved'}
        self.reserves.append(key)
        if self.reserve_fault:raise RuntimeError('DATA reserve result unknown after original write')
        return ref
    def inspect(self,key,identity):return self.rows.get(key)
    def verify(self,ref,key,identity,outcome):
        row=self.rows[key]
        if row['ref']!=ref or row['identity']!=identity:raise ValueError('DATA wrong original reservation')
        if outcome is not None and (row['state']!='completed' or row['outcome']!=outcome):
            raise ValueError('DATA original outcome not completed')
    def complete(self,ref,key,identity,outcome):
        self.verify(ref,key,identity,None)
        self.rows[key].update(state='completed',outcome=deepcopy(outcome));self.completed.append(key)
        if self.complete_fault:raise RuntimeError('DATA completion published but caller interrupted')
    def unknown(self,ref,key,identity,reason):
        self.unknowns.append(key)
        if key in self.rows and self.rows[key]['state']!='completed':self.rows[key]['state']='unknown'


class SegmentedExecutionDataTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        policy,_pins=review.policy_observations()
        self.subject={'schema_version':PUBLISHED.name('subject'),'producer':'compensation','operation_id':'DATA-Multi',
            'request':{'operation_id':'DATA-Multi','schema_version':'newrouge.b-route-compensation-request.v2','producer':'compensation'},
            'preview':{'targets':[{}]},'policy_identity':policy,
            'native_threads':['ancestor-thread'],'native_turns':['ancestor-turn']}
        p={'schema_version':PUBLISHED.name('presentation'),'claim':PUBLISHED.claim,
            'full_subject_digest':codec.canonical_digest(self.subject),'policy_identity':policy,
            'required_checks':review.obligations(self.subject),'materials_digest':'sha256:'+'1'*64,
            'roles_digest':'sha256:'+'2'*64,'historical_auth_digest':'sha256:'+'3'*64}
        self.packet={'schema_version':PUBLISHED.name('packet'),'presentation':p,'roles':{},
                     'materials':{'components':{'A':{'meaning':'complete A'},'B':{'meaning':'complete B'}},
                                  'interaction':{'left':'A','right':'B','rule':'preserve both'}}}
        checks=review.obligations(self.subject)
        self.spec=[{'node_id':name,'dependencies':parents,'check_ids':checks[i*3:(i+1)*3],
            'source_paths':paths,'base_prompt':'Complete DATA originals '+review.text(body)}
            for i,(name,parents,paths,body) in enumerate([
                ('A',[],['/materials/components/A'],self.packet['materials']['components']['A']),
                ('B',[],['/materials/components/B'],self.packet['materials']['components']['B']),
                ('joint',['A','B'],['/materials'],self.packet['materials'])])]
        self.derived=engine.materials.Derived(engine.materials._MINT,self.packet,
            {'scope':'DATA only; not historical authentication'},self.subject,[],compact._work(None),None)
        self.budget=DataBudget();self.calls=[];self.failure=None;self.reused_thread=False;self.reused_turn=False
        self.rationale='DATA only';self.ancestor_thread=False;self.ancestor_turn=False
        self.stack=ExitStack();self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(engine,'_spec',side_effect=lambda d:deepcopy(self.spec)))
        self.stack.enter_context(patch.object(engine.materials,'validate',side_effect=lambda p,**kw:p))
        self.stack.enter_context(patch.object(qualified,'read_subject',side_effect=lambda root,operation_id:deepcopy(self.subject)))
        self.stack.enter_context(patch.object(qualified,'model_packet',side_effect=lambda *a,**kw:self.derived))
        self.stack.enter_context(patch.object(funding,'capture',side_effect=lambda root,plan,read_only=False:
            funding.BudgetSession(funding._KEY,self.budget,root,plan,read_only)))
        self.stack.enter_context(patch.object(engine,'run_isolated_model',side_effect=self.dispatch))
        self.stack.enter_context(patch.dict('sys.modules',{'tiktoken':None}))

    def prepare(self):return engine.prepare(self.root,self.derived)

    def test_outer_rpc_escaping_is_admitted_before_any_reservation(self):
        plan=engine._plan(self.subject,self.packet,self.spec)
        node=plan['nodes'][0];base='"'*35000
        schema=engine._schema(self.subject,self.packet,plan,node,engine._prefix([]))
        self.assertLess(len(engine._frame(base,schema).encode()),70000)
        with self.assertRaises(codec.CodecError):
            engine._request(self.subject,self.packet,plan,node,base,[])
        self.assertEqual([],self.calls);self.assertEqual([],self.budget.reserves)

    def test_execute_saved_validation_keeps_genuine_factory_account(self):
        self.prepare()
        seen=[]
        def refuse(packet,*,work=None):
            seen.append((packet,work))
            work.spend(work.remaining+1,phase='DATA.shared.saved_validation')
        with patch.object(engine.materials,'validate',side_effect=refuse),self.assertRaises(ValueError):
            engine.execute(self.root,'DATA-Multi',derived=self.derived)
        self.assertIs(self.packet,seen[0][0]);self.assertIs(self.derived.work,seen[0][1])
        self.assertEqual([],self.calls);self.assertEqual([],self.budget.reserves)

    def dispatch(self,runner,*,workspace,prompt_path,output_path,output_schema,execution_log,**kwargs):
        self.assertEqual('high',kwargs['reasoning_effort']);self.assertEqual(1,kwargs['model_request_budget'])
        number=len(self.calls)+1;self.calls.append(workspace)
        if self.failure==number:raise TimeoutError('DATA interrupted response')
        schema=json.loads(output_schema.read_text());verdict={k:v['const'] for k,v in schema['properties'].items() if 'const' in v}
        verdict.update(verdict='approved',findings=[],checks=[{'id':key,'verdict':'approved','rationale':self.rationale}
            for key in schema['properties']['checks']['items']['properties']['id']['enum']])
        output=review.text(verdict)
        request=engine._frame(prompt_path.read_text(),schema)
        from openai_isolated_model_runner import workspace_payload
        self.assertEqual(request,workspace_payload(workspace,prompt_path=prompt_path,
            output_path=output_path,max_bytes=1048576))
        # The quota/archive includes the outer RPC JSON and output schema;
        # App Server runtime proof still binds the actual model-visible prompt.
        archived=(workspace.parent/'request.txt').read_text()
        self.assertEqual(review.text({'prompt':request,'output_schema':schema}),archived)
        report=json.loads((workspace.parent/'measurement.json').read_text())
        self.assertEqual(len(archived.encode('utf-8')),report['request_bytes'])
        rows=protocol(workspace,prompt=request,output=output,schema=schema,provider='openai')
        def rename(v):
            if type(v) is dict:return {k:rename(x) for k,x in v.items()}
            if type(v) is list:return [rename(x) for x in v]
            if v=='fresh-thread':return 'ancestor-thread' if self.ancestor_thread else 'DATA-thread-'+str(1 if self.reused_thread else number)
            if v=='fresh-turn':return 'ancestor-turn' if self.ancestor_turn else 'DATA-turn-'+str(1 if self.reused_turn else number)
            return v
        for row in rows:
            if row['direction']=='client' and row['message'].get('method')=='thread/start':
                row['message']['params']['config']['model_reasoning_effort']='high'
            row['message']=rename(row['message'])
        text,evidence=transport.replay(encoded(rows),prompt=request,schema=schema)
        receipt={'schema_version':'newrouge.isolated-model-runner-receipt.v1','model':evidence['model'],
            'model_provider':'openai','model_identity':'openai/'+evidence['model'],'model_identity_source':transport.SOURCE,
            'model_identity_scope':'runtime_configuration','evidence_policy':transport.POLICY,
            'runtime_identity_verified':True,'model_identity_verified':False,'provider_identity_verified':False,
            'provider_reported_model':None,'provider_dispatch_count':'unknown','model_identity_evidence':[evidence],
            'model_tools':[],'request_count_observable':True,'model_request_count':1,'runner_invocations':1,
            'workspace':workspace.as_posix(),'output_chars':len(text)}
        stdout=review.text(receipt)+'\n'
        execution={'command':engine._command(workspace),'status':'completed','returncode':0,
            'runner_dispatch_count':1,'active_elapsed_seconds':0.01,'stdout':stdout,
            'stdout_base64':base64.b64encode(stdout.encode()).decode()}
        output_path.write_bytes(text.encode());execution_log.write_bytes(review.raw(execution))

    def test_three_nodes_real_replay_proof_and_no_second_dispatch(self):
        self.prepare();result=engine.execute(self.root,'DATA-Multi',derived=self.derived)
        self.assertEqual(3,result['completed_nodes']);self.assertEqual(3,len(self.calls))
        proof,saved,_=engine.produce_proof(self.root,'DATA-Multi')
        self.assertEqual(engine.PROOF,proof['schema_version']);self.assertEqual(3,len(proof['evidence']['nodes']))
        self.assertEqual(3,len({e['thread_id'] for e in proof['evidence']['nodes']}))
        repeated=engine.execute(self.root,'DATA-Multi',derived=self.derived)
        self.assertFalse(repeated['model_dispatched']);self.assertEqual(0,repeated['runner_dispatch_attempts'])
        self.assertEqual(3,len(self.calls));self.assertEqual(3,len(self.budget.reserves))
        ref=review.seal(self.root,'DATA-Multi',proof)
        subject,refs=review.verify_saved(self.root,{**self.subject['request'],'host_review_ref':ref})
        self.assertEqual(self.subject,subject);self.assertEqual(engine.PROOF,ref['schema_version'])

    def test_unknown_stops_and_resume_does_not_retry_or_refund(self):
        self.prepare();self.failure=2
        with self.assertRaises(TimeoutError):engine.execute(self.root,'DATA-Multi',derived=self.derived)
        self.assertEqual(2,len(self.calls));self.assertEqual(2,len(self.budget.reserves))
        result=engine.execute(self.root,'DATA-Multi',publication_only=True,derived=self.derived)
        self.assertEqual('blocked',result['status']);self.assertEqual(2,len(self.calls))
        self.assertEqual('unknown',list(self.budget.rows.values())[-1]['state'])

    def test_reserve_unknown_keeps_intent_without_second_reserve(self):
        self.prepare();self.budget.reserve_fault=True
        with self.assertRaises(RuntimeError):engine.execute(self.root,'DATA-Multi',derived=self.derived)
        result=engine.execute(self.root,'DATA-Multi',publication_only=True,derived=self.derived)
        self.assertEqual('blocked',result['status']);self.assertEqual(1,len(self.budget.reserves));self.assertEqual([],self.calls)

    def test_completed_owner_outcome_repairs_publication_without_dispatch(self):
        self.prepare();self.budget.complete_fault=True
        with self.assertRaises(RuntimeError):engine.execute(self.root,'DATA-Multi',derived=self.derived)
        self.budget.complete_fault=False
        result=engine.execute(self.root,'DATA-Multi',publication_only=True,derived=self.derived)
        self.assertEqual('ready',result['status']);self.assertEqual('B',result['next_node'])
        self.assertEqual(1,len(self.calls));self.assertEqual(1,len(self.budget.reserves))
        result=engine.execute(self.root,'DATA-Multi',derived=self.derived)
        self.assertEqual(3,result['completed_nodes']);self.assertEqual(3,len(self.calls))

    def test_finite_budget_refusal_prevents_dispatch(self):
        self.prepare();self.budget.limit=2
        with self.assertRaises(ValueError):engine.execute(self.root,'DATA-Multi',derived=self.derived)
        self.assertEqual([],self.calls);self.assertEqual([],self.budget.reserves)

    def check_reused_identity(self,kind):
        setattr(self,'reused_'+kind,True);self.prepare()
        with self.assertRaises(codec.CodecError):engine.execute(self.root,'DATA-Multi',derived=self.derived)
        self.assertEqual(2,len(self.calls))

    def test_reused_thread_rejects_no_next_node(self):self.check_reused_identity('thread')
    def test_reused_turn_rejects_no_next_node(self):self.check_reused_identity('turn')

    def test_changed_prefix_and_low_measurement_reject_before_dispatch(self):
        self.prepare();self.failure=2
        with self.assertRaises(TimeoutError):engine.execute(self.root,'DATA-Multi',derived=self.derived)
        home=review.location('DATA-Multi');path=self.root/home/'segmented/nodes/000/measurement.json'
        report=json.loads(path.read_text());report['input_token_estimate']=0;path.write_bytes(review.raw(report))
        with self.assertRaises(codec.CodecError):engine.execute(self.root,'DATA-Multi',derived=self.derived)
        self.assertEqual(2,len(self.calls))

    def test_missing_actual_issuer_and_caller_dict_cannot_dispatch(self):
        self.prepare();home,plan,_packet=engine._saved(self.root,self.subject)
        self.stack.close()
        with self.assertRaises(codec.CodecError) as caught:funding.capture(self.root,plan)
        self.assertEqual(codec.ReasonCode.DEPENDENCY_UNAVAILABLE,caught.exception.diagnostic.reason_code)
        with self.assertRaises(codec.CodecError):funding.require_session({'approved':True})

    def test_modified_proof_cannot_mint_before_view_context(self):
        self.prepare();engine.execute(self.root,'DATA-Multi',derived=self.derived)
        proof,_saved,_=engine.produce_proof(self.root,'DATA-Multi')
        proof['requests_digest']='sha256:'+'0'*64
        with self.assertRaises(codec.CodecError):qualified._inputs(self.root,self.subject,proof=proof)

    def test_output_reserve_is_not_a_new_output_size_cap(self):
        self.rationale='DATA rationale '+('x'*1000)
        self.prepare();result=engine.execute(self.root,'DATA-Multi',derived=self.derived)
        self.assertEqual(3,result['completed_nodes'])
        self.assertTrue(all((w/'output.json').stat().st_size>2000 for w in self.calls))

    def test_full_parent_outputs_are_remeasured_before_next_reservation(self):
        self.rationale='DATA '+('x'*15000)
        self.prepare()
        with self.assertRaises(codec.CodecError) as caught:engine.execute(self.root,'DATA-Multi',derived=self.derived)
        actual=caught.exception.diagnostic.actual
        self.assertEqual('joint',actual['node_id']);self.assertEqual('utf8_byte_upper_bound',actual['measurement']['token_counter'])
        self.assertGreater(actual['measurement']['request_bytes'],70000)
        self.assertEqual(2,len(self.calls));self.assertEqual(2,len(self.budget.reserves))

    def test_owner_partition_cannot_be_replaced_by_a_caller_rehash(self):
        self.prepare();home=review.location('DATA-Multi');plan_path=self.root/home/engine.MARKER
        plan=json.loads(plan_path.read_text());base=self.root/home/'segmented/nodes/000/base-prompt.txt'
        base.write_text('caller summary');plan['nodes'][0]['base_prompt_digest']=codec.raw_digest(base.read_bytes())
        core={k:v for k,v in plan.items() if k!='plan_digest'};plan['plan_digest']=codec.canonical_digest(core)
        plan_path.write_bytes(review.raw(plan))
        with self.assertRaises(codec.CodecError):engine.execute(self.root,'DATA-Multi',derived=self.derived)
        self.assertEqual([],self.calls);self.assertEqual([],self.budget.reserves)

    def test_high_is_set_only_in_child_environment_before_launch(self):
        import _planning_skill_common as common
        with patch.dict(os.environ,{'NEWROGUE_CODEX_REASONING_EFFORT':'low'}), \
                patch.object(common.subprocess,'Popen',side_effect=OSError('DATA launch stopped')) as child:
            with self.assertRaises(OSError):common.run_isolated_model(
                Path(__file__).parents[1]/'codex_isolated_model_runner.py',workspace=self.root,
                prompt_path=self.root/'prompt.txt',output_path=self.root/'output.json',timeout_sec=1,reasoning_effort='high')
            self.assertEqual('high',child.call_args.kwargs['env']['NEWROGUE_CODEX_REASONING_EFFORT'])
            self.assertEqual('low',os.environ['NEWROGUE_CODEX_REASONING_EFFORT'])

    def test_saved_history_routes_all_node_roles_and_ancestor_identities(self):
        self.prepare();engine.execute(self.root,'DATA-Multi',derived=self.derived)
        proof,_saved,_=engine.produce_proof(self.root,'DATA-Multi')
        ref=review.seal(self.root,'DATA-Multi',proof)
        saved=engine.inputs(self.root,self.subject,proof=proof)
        operation={'operation_id':'DATA-Multi','schema_version':'newrouge.b-route-compensation-operation.v2',
            'frozen':{'request':{**self.subject['request'],'host_review_ref':ref}},'frozen_digest':'sha256:'+'a'*64}
        operation_raw=review.raw(operation)
        import _planning_apply_journal as journal
        path=self.root/journal._operation_ref('DATA-Multi');path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(operation_raw)
        history=qualified.SavedHistory(qualified._MINT,self.root,operation,operation_raw,saved,self.derived)
        snapshot=SimpleNamespace(root=self.root,read=lambda name:(self.root/name).read_bytes(),_qualified_history_handles=[])
        with patch.object(qualified,'history',return_value=history):
            support=review.verified_historical_support(self.root,operation)
            threads,turns=qualified.original_review(snapshot,operation,profile=PUBLISHED)
        self.assertEqual(set(support['files']),set(support['roles']))
        self.assertIn('segmented_requests_digest',history.binding())
        self.assertTrue({'DATA-thread-1','DATA-thread-2','DATA-thread-3'}<=set(threads))
        self.assertTrue({'DATA-turn-1','DATA-turn-2','DATA-turn-3'}<=set(turns))


if __name__=='__main__':unittest.main()
