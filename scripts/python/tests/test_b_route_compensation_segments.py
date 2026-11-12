"""Offline segmentation boundaries; fixtures never establish model authority."""
from copy import deepcopy
import unittest
from unittest.mock import patch
import tempfile
from pathlib import Path
from types import SimpleNamespace

import b_route_adoption as cli
import _b_route_codec as codec
import _b_route_compact_literal as compact
import _b_route_qualified_compensation_materials_v2 as materials
import _b_route_compensation_segments as segments
import _capability_input_integrity as integrity
import _b_route_compensation_review_materials as accounting
import _b_route_adoption_review as review
from _b_route_compensation_review_profiles import PUBLISHED
from _b_route_segmented_requests import _measurement


class SegmentInputTests(unittest.TestCase):
    def packet(self):
        values=[{'exact':['中文',True,1,1.0,-0.0,{'ordered':2,'first':1}]},{}]
        texts=[materials.raw(v).decode() for v in values]
        texts+=['{this is ordinary non-JSON source text}', '{"compact":true}\n']
        return {'materials':{'documents':[{'raw_digest':codec.raw_digest(t.encode()),
            'raw_bytes':len(t.encode()),'text':t} for t in texts]}}

    def test_json_views_preserve_every_original_byte_and_type(self):
        packet=self.packet();work=compact._work(None)
        envelope=materials._json_views(deepcopy(packet),work)
        self.assertEqual([0,1],[v['document'] for v in envelope['views']])
        body,restored=compact.produce_canonical_roundtrip(envelope,schema=compact.RESIDUAL_SCHEMA,work=work)
        self.assertTrue(body)
        self.assertEqual(materials.ordered(packet),materials.ordered(materials._restore_json_views(restored,work)))
        self.assertLess(work.limit-work.remaining,work.limit)

    def test_missing_duplicate_wrong_digest_and_placeholder_reject(self):
        for change in ('missing','duplicate','digest','placeholder'):
            w=compact._work(None);envelope=materials._json_views(self.packet(),w)
            if change=='missing':envelope['views'].pop()
            elif change=='duplicate':envelope['views'].append(deepcopy(envelope['views'][0]))
            elif change=='digest':envelope['packet_core']['materials']['documents'][0]['raw_digest']='sha256:'+'0'*64
            else:envelope['packet_core']['materials']['documents'][1]['text']={'json2_view':True}
            with self.subTest(change=change),self.assertRaises((codec.CodecError,ValueError,TypeError)):
                materials._restore_json_views(envelope,w)

    def test_resource_refusal_is_not_treated_as_literal_prose(self):
        with patch.object(compact,'_syntax_preflight',side_effect=ValueError('Compact syntax exceeds resource policy')):
            with self.assertRaisesRegex(ValueError,'Compact syntax exceeds'):
                materials._json_views(self.packet(),compact._work(None))

    def test_restoration_accounts_for_prior_complete_texts(self):
        work=compact._work(None);envelope=materials._json_views(self.packet(),work)
        original=accounting._json2;held=[]
        def observe(source,w,metrics=(),buffers=()):
            held.append(tuple(buffers));return original(source,w,metrics,buffers)
        with patch.object(accounting,'_json2',side_effect=observe):
            materials._restore_json_views(envelope,work)
        self.assertEqual(0,held[0][-1]);self.assertGreater(held[1][-1],0)

    def test_cold_reader_rejects_alternate_view_selection(self):
        packet=self.packet();packet['schema_version']=PUBLISHED.name('packet')
        envelope=materials._json_views(deepcopy(packet),compact._work(None))
        first=envelope['views'].pop(0)
        envelope['packet_core']['materials']['documents'][first['document']]['text']=packet['materials']['documents'][0]['text']
        envelope['packet_core']['materials']['documents'][1]['text']={'json2_view':0}
        prompt=materials._header(PUBLISHED,True)+'\n'+compact.dumps(envelope,schema=compact.RESIDUAL_SCHEMA)
        with self.assertRaises(codec.CodecError) as caught:
            materials.read_segment_input(prompt)
        self.assertIn('deterministic JSON2 view selection',caught.exception.diagnostic.expected)

    def test_resume_recomputes_state_instead_of_trusting_ready_flag(self):
        # DATA archive plumbing, not a genuine owner derivation or model proof.
        packet=self.packet();packet['presentation']={'required_checks':['all-original-checks']}
        packet['roles']={};packet['materials']['frames']=[]
        subject={'operation_id':'OfflineData','policy_identity':'sha256:'+'1'*64}
        schema={'type':'object'};prompt='DATA only';request=review._runner_frame(prompt,schema)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);home='logs/ci/segment-data'
            report={'token_counter':'DATA blocked'}
            # Make a real byte-counter refusal with a complete archived request.
            prompt='x'*70001;request=review._runner_frame(prompt,schema)
            with patch.dict('sys.modules',{'tiktoken':None}):
                report=integrity.request_measurement(request,max_bytes=1048576,max_input_tokens=96000,reserved_tokens=2000)
            packet_bytes=(materials.ordered(packet)+'\n').encode()
            plan=segments._plan(subject,packet,home,subject['policy_identity'],request,codec.raw_digest(packet_bytes))
            state=segments._state(report,request)
            values={'packet.json':packet_bytes,'plan.json':review.raw(plan),'source-pins.json':review.raw({}),
                'nodes/000/w/prompt.txt':prompt.encode(),'nodes/000/w/schema.json':review.raw(schema),
                'nodes/000/request.txt':request.encode(),'nodes/000/measurement.json':review.raw(report)}
            state['files']={name:codec.raw_digest(data) for name,data in values.items()}
            state['blocked']=False
            for name,data in {**values,'state.json':review.raw(state)}.items():
                p=root/home/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
            d=SimpleNamespace(packet=packet,subject=subject,recheck=lambda:None,
                              work=compact._work(None),private_metrics=lambda:([],[]))
            with patch('_b_route_qualified_compensation_review_v2.verdict_schema',return_value=schema), \
                    patch.object(review,'policy_observations',return_value=(subject['policy_identity'],{})), \
                    patch.dict('sys.modules',{'tiktoken':None}),self.assertRaises(codec.CodecError):
                segments._resume(root,home,d,prompt)

    def test_per_segment_input_and_context_are_separate_limits(self):
        with patch.dict('sys.modules',{'tiktoken':None}):
            report=integrity.request_measurement('x'*70000,max_bytes=1048576,
                max_input_tokens=96000,reserved_tokens=2000)
            _measurement(report,'x'*70000,2000)
            over=integrity.request_measurement('x'*70001,max_bytes=1048576,
                max_input_tokens=96000,reserved_tokens=2000)
            with self.assertRaisesRegex(ValueError,'input_over_70000'):_measurement(over,'x'*70001,2000)
            with self.assertRaisesRegex(ValueError,'input_plus_output_over_96000'):
                report=integrity.request_measurement('x'*70000,max_bytes=1048576,
                    max_input_tokens=96000,reserved_tokens=26001)
                _measurement(report,'x'*70000,26001)
            with self.assertRaisesRegex(ValueError,'runner_context_budget_exceeded'):
                integrity.measure_request('x'*70000,max_bytes=1048576,max_input_tokens=70000,reserved_tokens=2000)

    def test_old_marker_is_not_a_segment_marker(self):
        with self.assertRaises(codec.CodecError):
            materials.read_segment_input(materials.DELIVERY+' old proof\n{}')

    def test_cli_preflight_routes_to_offline_service_only(self):
        args=cli.build_parser().parse_args(['--stage','review-segmented-preflight','--operation-id','Case',
            '--request','request.json','--compensation-review-delivery',
            'newrouge.b-route-qualified-compensation-review-delivery.v3'])
        import _b_route_adoption as owner
        result={'status':'blocked','stage':'review-segmented-preflight','model_dispatched':False}
        with patch.object(owner,'preflight_segmented_compensation',return_value=result) as preflight, \
                patch.object(owner,'prepare_review',side_effect=AssertionError('one-shot path entered')):
            value=cli._execute(args)
        self.assertFalse(value['model_dispatched']);preflight.assert_called_once()


if __name__=='__main__':unittest.main()
