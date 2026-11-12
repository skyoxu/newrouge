"""Synthetic DATA factories; real durable files, official protocol replay and proof paths.

The original-source and business factories are explicitly synthetic. No account,
network, model or historical owner authority is exercised by these unit checks.
"""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import json
import unittest
from unittest.mock import patch

import _b_route_adoption_review as review
import _b_route_codec as codec
import _b_route_compensation_partition as partition
import _b_route_compensation_review_repair as repair
import _b_route_compensation_segmented_execution as engine
import _b_route_qualified_compensation_review_v2 as qualified
from test_b_route_compensation_segmented_execution import SegmentedExecutionDataTests


class FormalRepairDataTests(unittest.TestCase):
    def setUp(self):
        self.owner=SegmentedExecutionDataTests();self.owner.setUp();self.addCleanup(self.owner.doCleanups)
        o=self.owner;self.root=o.root
        checks=review.obligations(o.subject)
        o.subject['private_files']={}
        o.packet['presentation']['full_subject_digest']=codec.canonical_digest(o.subject)
        o.spec=[{'node_id':name,'dependencies':parents,'check_ids':ids,'source_paths':['/'],
            'base_prompt':partition.HEADER+'\n'+review.text({'DATA_complete_original':name})}
            for name,parents,ids in [('business',[],checks[:2]),('governance-joint',['business'],checks[2:])]]
        o.derived._auth={'schema_version':'DATA.auth','full_subject_digest':codec.canonical_digest(o.subject),
            'histories':{'DATA':{'current_verifier_policy':o.subject['policy_identity'],'meaning':'DATA only'}}}
        o.packet['presentation']['historical_auth_digest']=codec.canonical_digest(o.derived._auth)
        o.blocked_call=2;o.prepare()
        with self.assertRaises(codec.CodecError):o.execute(model_request_budget=2)
        self.assertEqual(2,len(o.calls))
        self.base=review.location('DATA-Multi');self.home=self.root/self.base
        self.original={str(p.relative_to(self.home)):p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        self.source={Path(p).relative_to(Path(repair.__file__).resolve().parents[2]).as_posix():Path(p).read_bytes()
            for p in review.policy_observations()[1]}
        self.patches=[]
        def use(p):
            self.patches.append(p);return p.start()
        self.addCleanup(lambda:[p.stop() for p in reversed(self.patches)])
        use(patch.object(repair,'LEGACY_POLICY',o.subject['policy_identity']))
        use(patch.object(repair,'_source_epoch',side_effect=lambda *a,**kw:dict(self.source)))
        use(patch.object(repair,'derived_root',return_value=self.root))
        use(patch.object(repair,'run_isolated_model',side_effect=o.dispatch))
        self.derived=o.derived

    def prepare(self):return repair.prepare(self.root,self.derived,self.root)
    def execute(self,**kw):
        kw.setdefault('model_request_budget',1);kw.setdefault('authorization_source','DATA explicit subscription continuation')
        return repair.execute(self.root,self.derived,**kw)
    def old_unchanged(self):
        for name,data in self.original.items():self.assertEqual(data,(self.home/name).read_bytes(),name)

    def test_completed_refusal_adds_one_formal_review_and_proof_without_reset(self):
        self.prepare();result=self.execute()
        self.assertEqual(3,result['cumulative_logical_calls']);self.assertEqual(3,len(self.owner.calls))
        proof,saved,_=repair.produce_proof(self.root,'DATA-Multi')
        self.assertEqual(repair.PROOF,proof['schema_version']);self.assertEqual(3,proof['cumulative_logical_limit'])
        self.assertEqual('retained_exact_business_closure',proof['evidence']['nodes'][0]['scope'])
        self.assertEqual('fresh_current_governance_closure',proof['evidence']['nodes'][1]['scope'])
        ref=review.seal(self.root,'DATA-Multi',proof)
        subject,refs=review.verify_saved(self.root,{**self.owner.subject['request'],'host_review_ref':ref})
        self.assertEqual(self.owner.subject,subject);self.assertGreater(len(refs),len(self.original))
        verified,derived=repair.verify_saved_private(self.root,{**self.owner.subject['request'],'host_review_ref':ref})
        self.assertNotIn('segmented/nodes/000/execution.json',verified.buffers)
        operation={'operation_id':'DATA-Multi','schema_version':'newrouge.b-route-compensation-operation.v2',
            'frozen_digest':'sha256:'+'4'*64,'request_raw_digest':'sha256:'+'5'*64,
            'frozen':{'request':{**self.owner.subject['request'],'host_review_ref':ref}}}
        history=qualified.SavedHistory(qualified._MINT,self.root,operation,review.raw(operation),verified,derived)
        files=history.files();roles=history.roles()
        self.assertTrue({r['path'] for r in verified.refs}<=set(files))
        self.assertEqual(set(files),set(roles))
        old_execution=self.home/'segmented/nodes/000/execution.json';exact=old_execution.read_bytes()
        old_execution.write_bytes(exact+b' ')
        with self.assertRaises(codec.CodecError):history.files()
        old_execution.write_bytes(exact)
        self.assertFalse(self.execute()['model_dispatched']);self.assertEqual(3,len(self.owner.calls))
        self.assertTrue((self.home/'segmented/nodes/001/unknown.json').exists());self.old_unchanged()

    def test_original_unknown_or_incomplete_protocol_never_enters_repair(self):
        p=self.home/'segmented/nodes/001/execution.json';before=p.read_bytes();p.unlink()
        with self.assertRaises(OSError):self.prepare()
        self.assertFalse((self.home/repair.LANE).exists());self.assertEqual(2,len(self.owner.calls));p.write_bytes(before)

    def test_original_complete_marker_or_tampered_prefix_refuses(self):
        p=self.home/'segmented/nodes/000/completed.json';p.write_text('{}')
        with self.assertRaises(codec.CodecError):self.prepare()
        self.assertFalse((self.home/repair.LANE).exists());self.assertEqual(2,len(self.owner.calls))

    def test_original_historical_auth_top_subject_digest_is_not_rebound_by_manifest(self):
        p=self.home/'historical-auth.json';auth=json.loads(p.read_bytes())
        auth['full_subject_digest']='sha256:'+'0'*64;p.write_bytes(review.raw(auth))
        with self.assertRaises(codec.CodecError):self.prepare()
        self.assertFalse((self.home/repair.LANE).exists());self.assertEqual(2,len(self.owner.calls))

    def test_same_body_with_changed_historical_decoder_is_not_equivalent(self):
        name='scripts/python/_b_route_compensation_partition.py'
        self.source[name]=self.source[name].replace(b'Canonical Python DATA literal only',b'Changed Python DATA literal only')
        with self.assertRaises(codec.CodecError):self.prepare()
        self.assertEqual(2,len(self.owner.calls));self.assertFalse((self.home/repair.LANE).exists())

    def test_current_semantic_change_is_not_a_source_only_transition(self):
        self.owner.subject['request']['changed_business']='not permitted'
        with self.assertRaises(codec.CodecError):self.prepare()
        self.assertEqual(2,len(self.owner.calls));self.assertFalse((self.home/repair.LANE).exists())

    def test_partial_manifest_cannot_select_or_fall_back_to_original(self):
        directory=self.home/repair.LANE;directory.mkdir()
        self.assertTrue(repair.selected(self.root,'DATA-Multi'))
        with self.assertRaises(OSError):repair.read_subject(self.root,'DATA-Multi')

    def test_additional_limit_is_one_and_requires_provenance_before_intent(self):
        self.prepare()
        for limit,source in [(2,'DATA'),(True,'DATA'),(1,None),(1,'')]:
            with self.subTest(limit=limit,source=source),self.assertRaises(codec.CodecError):
                self.execute(model_request_budget=limit,authorization_source=source)
        self.assertEqual(2,len(self.owner.calls));self.assertFalse((self.home/repair.LANE/'intent.json').exists())
        self.old_unchanged()

    def test_new_failure_permanently_occupies_repair_and_cannot_repeat_prepare(self):
        self.prepare();self.owner.failure=3
        with self.assertRaises(TimeoutError):self.execute()
        result=self.execute();self.assertEqual('blocked',result['status']);self.assertEqual(3,len(self.owner.calls))
        with self.assertRaises(codec.CodecError):self.prepare()
        self.assertTrue((self.home/repair.LANE/'unknown.json').exists());self.old_unchanged()

    def test_interruption_after_repair_intent_never_dispatches_on_reentry(self):
        self.prepare();original=repair.write
        def stop(root,name,value):
            original(root,name,value)
            if name.endswith('/intent.json'):raise OSError('DATA after durable repair intent')
        with patch.object(repair,'write',side_effect=stop),self.assertRaises(OSError):self.execute()
        result=self.execute();self.assertEqual('blocked',result['status']);self.assertEqual(2,len(self.owner.calls))
        self.old_unchanged()

    def test_complete_output_without_completion_marker_is_not_published(self):
        self.prepare();original=repair.write
        def stop(root,name,value):
            if name.endswith('/completed.json'):raise OSError('DATA before completion marker')
            return original(root,name,value)
        with patch.object(repair,'write',side_effect=stop),self.assertRaises(OSError):self.execute()
        self.assertEqual('blocked',self.execute()['status']);self.assertEqual(3,len(self.owner.calls))

    def test_new_review_cannot_reuse_rejected_previous_thread(self):
        self.prepare();self.owner.reused_thread=True;self.owner.reused_thread_number=2
        with self.assertRaises(codec.CodecError):self.execute()
        self.assertEqual('blocked',self.execute()['status']);self.assertEqual(3,len(self.owner.calls))

    def test_new_review_cannot_reuse_rejected_previous_turn(self):
        self.prepare();self.owner.reused_turn=True;self.owner.reused_turn_number=2
        with self.assertRaises(codec.CodecError):self.execute()
        self.assertEqual('blocked',self.execute()['status']);self.assertEqual(3,len(self.owner.calls))

    def test_altered_proof_cannot_mint_saved_before_scope(self):
        self.prepare();self.execute();proof,_saved,_=repair.produce_proof(self.root,'DATA-Multi')
        proof['files']=[]
        with self.assertRaises(codec.CodecError):repair.inputs(self.root,self.owner.subject,proof=proof)
        self.old_unchanged()

    def test_only_explicit_new_version_routes_to_published_owner(self):
        import _b_route_qualified_compensation_dispatch as dispatch
        import _b_route_published_compensation_review as published
        operation={'schema_version':'newrouge.b-route-compensation-operation.v2','frozen':{'request':{'host_review_ref':{'schema_version':repair.PROOF}}}}
        self.assertIs(published,dispatch.for_operation(operation));self.assertTrue(qualified.selected(operation))

    def test_same_home_preparation_is_exclusive_and_existing_records_are_not_replaced(self):
        self.prepare()
        with self.assertRaises(codec.CodecError):self.prepare()
        self.old_unchanged();self.assertEqual(2,len(self.owner.calls))

class RepairCliRouteTests(unittest.TestCase):
    def test_legacy_compatibility_allows_only_truthful_context_graph_accounting(self):
        old=b'class Derived:\n def private_metrics(self):\n  if self.context is not None:\n   graphs.append(self.context.proof)\n  return graphs\n'
        new=old.replace(b'   graphs.append(self.context.proof)\n',b'   graphs.append(self.context.proof)\n   graphs.extend([self.context.refs,self.context.evidence])\n')
        self.assertTrue(repair._retention_only_change(old,new))
        self.assertFalse(repair._retention_only_change(old,new.replace(b'return graphs',b'return []')))
        self.assertFalse(repair._retention_only_change(old,new.replace(b'self.context.evidence',b'self.context.unknown')))

    def test_public_parser_forwards_explicit_additional_call_and_provenance(self):
        import b_route_adoption as cli
        import _b_route_adoption as adoption
        args=cli.build_parser().parse_args(['--root','DATA','--stage','review-segmented-repair-execute',
            '--operation-id','DATA-Multi','--model-request-budget','1','--review-authorization-source','DATA user authorization'])
        with patch.object(adoption,'repair_segmented_compensation_review',return_value={'status':'DATA-only'}) as call:
            cli._execute(args)
        self.assertEqual('execute',call.call_args.kwargs['stage'])
        self.assertEqual(1,call.call_args.kwargs['model_request_budget'])
        self.assertEqual('DATA user authorization',call.call_args.kwargs['authorization_source'])

    def test_repair_source_and_provenance_flags_do_not_leak_to_regular_stages(self):
        import b_route_adoption as cli
        for extra in (['--original-source-root','DATA-source'],['--review-authorization-source','DATA']):
            args=cli.build_parser().parse_args(['--root','DATA','--stage','inspect','--operation-id','DATA-Multi',*extra])
            with self.subTest(extra=extra),self.assertRaises(codec.CodecError):cli._execute(args)

if __name__=='__main__':unittest.main()
