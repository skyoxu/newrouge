"""Qualified-v2 resource lifecycle checks, never provider qualification.

Small original legacy fixtures exercise the real derive/codec/validation path.
Explicit DATA instances below only test storage accounting, not authentication.
"""
from copy import deepcopy
import json
import inspect
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import _b_route_adoption_review as review
import _b_route_adoption as adoption
import _b_route_codec as codec
import _b_route_compact_literal as compact
import _b_route_compensation_review_materials as accounting
import _b_route_qualified_compensation_materials_v2 as materials
import _b_route_qualified_compensation_review_v2 as qualified


class QualifiedCapacityDiagnosticTests(unittest.TestCase):
    """Boundary DATA plumbing only; no native subject or authority is minted."""

    def test_capacity_refusal_preserves_reason_and_details_through_public_boundary(self):
        subject={'operation_id':'QualifiedCapacityCase'}
        packet=object()
        schema={'type':'object','additionalProperties':False,'properties':{}}
        text='complete original material'
        def invoke(root, *, operation_id):
            return qualified.artifacts(root,subject,packet=packet)
        public=adoption.public(invoke)
        for failure in ('runner_context_budget_exceeded:estimated_input_tokens=101371;continuation_reserve=2000;limit=70000',
                        'runner_input_too_large:complete_request_bytes=1048577;limit=1048576'):
            with self.subTest(failure=failure), \
                    patch.object(qualified,'verdict_schema',return_value=schema), \
                    patch.object(qualified,'prompt',return_value=text), \
                    patch('_capability_input_integrity.configured_input_limit',return_value=70000), \
                    patch('_capability_input_integrity.measure_request',side_effect=ValueError(failure)) as measure, \
                    patch.object(qualified,'_auth_raw',side_effect=AssertionError('auth minted after refusal')) as auth:
                with self.assertRaises(codec.CodecError) as caught:
                    public(None,operation_id=subject['operation_id'])
                diagnostic=caught.exception.diagnostic
                self.assertEqual(codec.ReasonCode.INVALID_ARGUMENT,diagnostic.reason_code)
                self.assertEqual(subject['operation_id'],diagnostic.entity_id)
                self.assertEqual('complete qualified materials within byte/token budget',diagnostic.expected)
                self.assertEqual(failure,diagnostic.actual)
                measure.assert_called_once_with(review._runner_frame(text,schema),max_bytes=1048576,
                    max_input_tokens=70000,reserved_tokens=qualified.OUTPUT_RESERVE_TOKENS)
                auth.assert_not_called()

    def test_admitted_capacity_keeps_the_existing_artifact_path(self):
        subject={'operation_id':'QualifiedCapacityCase'}
        packet=SimpleNamespace(packet={'materials':{},'roles':{},'presentation':{}})
        schema={'type':'object','properties':{}}
        text='complete original material'
        with patch.object(qualified,'verdict_schema',return_value=schema), \
                patch.object(qualified,'prompt',return_value=text), \
                patch('_capability_input_integrity.configured_input_limit',return_value=70000), \
                patch('_capability_input_integrity.measure_request',return_value={}) as measure, \
                patch.object(qualified,'_auth_raw',return_value=b'DATA auth') as auth:
            values=qualified.artifacts(None,subject,packet=packet)
        request=review._runner_frame(text,schema)
        measure.assert_called_once_with(request,max_bytes=1048576,max_input_tokens=70000,
            reserved_tokens=qualified.OUTPUT_RESERVE_TOKENS)
        auth.assert_called_once_with(packet,request,schema)
        self.assertEqual(text.encode('utf-8'),values['w/prompt.txt'])
        self.assertEqual(request.encode('utf-8'),values['request.txt'])
        self.assertEqual(b'DATA auth',values['historical-auth.json'])


class AuthStorageDataTests(unittest.TestCase):
    def derived(self, *, work=None, context=None):
        auth={'schema_version':materials.AUTH,'full_subject_digest':'sha256:'+'1'*64,
              'histories':{'DATA':{'complete':'full private content', 'values':[True,1,1.0,-0.0]}}}
        return materials.Derived(materials._MINT,{},auth,{},[],compact._work(work),context)

    def test_full_original_auth_bytes_replace_the_retained_graph_once(self):
        d=self.derived()
        auth=d._auth
        expected=(materials.ordered(auth)+'\n').encode('utf-8')
        self.assertEqual(d.freeze_auth(),expected)
        self.assertIsNone(d._auth)
        self.assertEqual(json.loads(d.auth_bytes),auth)
        remaining=d.work.remaining
        self.assertIs(d.freeze_auth(),d.auth_bytes)
        self.assertEqual(d.work.remaining,remaining)
        metrics,buffers=d.private_metrics()
        self.assertEqual(len(metrics),1)  # subject only, not the released auth
        self.assertEqual(buffers,[len(expected)])

    def test_saved_context_and_its_full_buffers_remain_charged(self):
        class Context:
            proof={'complete':'saved proof'}
            buffers={'support':b'full captured bytes'}
        d=self.derived(context=Context())
        d.freeze_auth()
        metrics,buffers=d.private_metrics()
        self.assertEqual(len(metrics),2)
        self.assertEqual(buffers,[len(d.auth_bytes),len(Context.buffers['support'])])

    def test_failed_freeze_keeps_original_graph_and_exhausted_account(self):
        d=self.derived()
        auth=d._auth
        d.work.remaining=1
        with self.assertRaises(ValueError):
            d.freeze_auth()
        self.assertIs(d._auth,auth)
        self.assertIsNone(d.auth_bytes)
        self.assertLessEqual(d.work.remaining,1)

    def test_auth_storage_data_boundary_rejects_before_publishing_bytes(self):
        sizes=[]
        actual_live=accounting._live
        def live(work,phase,metrics=(),buffers=()):
            sizes.append(sum(m[0] for m in metrics)+sum(buffers))
            return actual_live(work,phase,metrics,buffers)
        with patch.object(accounting,'_live',side_effect=live):
            self.derived().freeze_auth()
        peak=max(sizes)
        with patch.object(compact,'MAX_EXPANDED_BYTES',peak):
            self.assertIsInstance(self.derived().freeze_auth(),bytes)
        rejected=self.derived()
        with patch.object(compact,'MAX_EXPANDED_BYTES',peak-1):
            with self.assertRaises(ValueError):
                rejected.freeze_auth()
        self.assertIsNone(rejected.auth_bytes)
        self.assertIsNotNone(rejected._auth)


class QualifiedWarmLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from test_b_route_compensation import CompensationTests
        cls.case=CompensationTests(methodName='runTest')
        cls.case.setUp()
        try:
            cls.subject=cls.case.material_subject()
            cls.subject['schema_version']=materials.SUBJECT
            cls.subject['private_files']={}
        except BaseException:
            cls.case.tearDown()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.case.tearDown()

    def derived(self):
        subject=deepcopy(self.subject)
        return materials.derive(self.case.root,subject,checks=review.obligations(subject))

    def test_small_original_fixture_preserves_full_canonical_wire_and_auth(self):
        d=self.derived()
        expected_auth=(materials.ordered(d._auth)+'\n').encode('utf-8')
        packet=deepcopy(d.packet)
        expected_body=compact.dumps(packet,schema=compact.RESIDUAL_SCHEMA)
        text=materials.render(d)
        header=materials.DELIVERY+' '+materials.INSTRUCTION+' '+compact.instruction(compact.RESIDUAL_SCHEMA)
        self.assertEqual(text,header+'\n'+expected_body)
        self.assertEqual(d.auth_bytes,expected_auth)
        self.assertIsNone(d._auth)
        self.assertEqual(materials.read_prompt(text),packet)
        self.assertEqual(qualified._auth_raw(d,'full request',{'type':'object'}),expected_auth)

    def test_frame_reservation_and_released_temporaries_follow_actual_phases(self):
        d=self.derived()
        actual_live=accounting._live
        observed={}
        producer=compact._ATOMIC_PRODUCER
        producer_context=[]
        def produced(value,*,schema,work):
            producer_context.append(work._residual_retained)
            return producer(value,schema=schema,work=work)
        def live(work,phase,metrics=(),buffers=()):
            if phase in ('qualified.atomic.live','qualified.decode.live','qualified.frame.live'):
                frame=inspect.currentframe().f_back
                while frame is not None and frame.f_code is not materials._render.__code__:
                    frame=frame.f_back
                self.assertIsNotNone(frame)
                result=actual_live(work,phase,metrics,buffers)
                observed[phase]=(tuple(buffers),set(frame.f_locals),result)
                return result
            return actual_live(work,phase,metrics,buffers)
        with patch.object(accounting,'_live',side_effect=live), \
                patch.object(compact,'_ATOMIC_PRODUCER',side_effect=produced):
            materials.render(d)
        self.assertEqual(observed['qualified.atomic.live'][0][-1],compact.MAX_ENCODED_BYTES)
        admitted=observed['qualified.atomic.live'][2]
        self.assertEqual([(admitted[0]-compact.MAX_ENCODED_BYTES,admitted[1]-1,admitted[2])],producer_context)
        self.assertNotIn('snapshot',observed['qualified.decode.live'][1])
        for name in ('snapshot','restored','original','text'):
            self.assertNotIn(name,observed['qualified.frame.live'][1])

    def test_producer_errors_bad_body_and_current_mutation_fail_closed(self):
        producer=compact._ATOMIC_PRODUCER
        for kind in ('value-error','memory-error','truncated','current-order'):
            d=self.derived()
            previous=(1,1,1)
            d.work._residual_retained=previous
            def changed(value,*,schema,work):
                if kind=='value-error':raise ValueError('original producer error')
                if kind=='memory-error':raise MemoryError('original producer error')
                body=producer(value,schema=schema,work=work)
                if kind=='truncated':return body[:-1]
                d.packet['presentation']=dict(reversed(list(d.packet['presentation'].items())))
                return body
            with self.subTest(kind=kind),patch.object(compact,'_ATOMIC_PRODUCER',side_effect=changed):
                with self.assertRaises((codec.CodecError,ValueError,MemoryError)):
                    materials.render(d)
            self.assertIs(d.work._residual_retained,previous)
            self.assertLess(d.work.remaining,d.work.limit)

    def test_json_shaped_semantic_corruption_rejects_after_full_real_roundtrip(self):
        d=self.derived()
        d.packet['unregistered_field']='not valid qualified semantics'
        with patch.object(compact,'_ATOMIC_PRODUCER',wraps=compact._ATOMIC_PRODUCER) as producer, \
                patch.object(compact,'_decode_complete',wraps=compact._decode_complete) as decoder:
            with self.assertRaises(codec.CodecError):
                materials.render(d)
        self.assertEqual(producer.call_count,1)
        self.assertEqual(decoder.call_count,1)


if __name__=='__main__':
    unittest.main()
