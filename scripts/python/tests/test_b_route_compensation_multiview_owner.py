"""Author-static R55 owner integration tests for Root; never original qualification.

Uses unchanged full compensation fixtures. Root alone chooses owned TEMP and runs.
Protocol fixtures are explicitly synthetic; no model, native, subprocess or network.
"""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

import _b_route_adoption as adoption
import _b_route_adoption_review as review
import _b_route_codec as codec
import _b_route_compensation_review_materials as materials
import _capability_input_integrity as capacity
import _planning_apply_journal as journal
import b_route_adoption as cli
import dev_cli
import test_b_route_compensation as composition
from fixtures.adoption_review_protocol import completed

V3 = 'newrouge.b-route-compensation-review-delivery.v3'
V4 = 'newrouge.b-route-compensation-review-delivery.v4'


class MultiViewOwnerIntegrationTests(unittest.TestCase):
    def prepare(self, *, selected=V4):
        self.case = composition.CompensationTests('test_complete_reviewed_compensation_uses_new_id_and_shared_commit')
        self.case.baseline(bound=True)
        self.root = self.case.root
        kwargs = {} if selected is None else {'compensation_delivery': selected}
        self.result = adoption.prepare_review(self.root, operation_id='COMP-one',
            request_ref=self.case.fx.request_ref(self.case.comp_request), **kwargs)
        self.home = review.path(self.root, review.location('COMP-one'))
        self.subject = review.read_subject(self.root, 'COMP-one')
        return self.result

    def approve(self, *, selected=V4):
        self.prepare(selected=selected)
        actual = V3 if selected is None else selected
        completed(self.root, 'COMP-one', thread_id='synthetic-multiview-owner-COMP-one', delivery=actual)
        self.request = deepcopy(self.case.comp_request)
        self.request['host_review_ref'] = adoption.complete_review(self.root, operation_id='COMP-one')['host_review_ref']
        return review.verify_saved(self.root, self.request)

    def test_public_optin_binds_full_packet_real_wrapper_and_original_runner(self):
        from openai_isolated_model_runner import workspace_payload
        self.prepare()
        prompt = (self.home / 'w/prompt.txt').read_text(encoding='utf-8')
        self.assertTrue(prompt.startswith(V4 + ' '))
        packet = review.model_packet(self.root, self.subject)
        restored = materials.read_prompt_multi_view(prompt)
        self.assertEqual(review.text(restored), review.text(packet))
        self.assertEqual((self.home / 'subject.json').read_bytes(), review.raw(self.subject))
        for name in ('materials', 'roles', 'presentation'):
            self.assertEqual((self.home / (name + '.json')).read_bytes(), review.raw(packet[name]))
        self.assertEqual((self.home / 'request.txt').read_text(encoding='utf-8'),
            workspace_payload(self.home / 'w', prompt_path=self.home / 'w/prompt.txt', output_path=self.home / 'w/output.json'))
        self.assertEqual(self.result['runner_command'], review.runner_command(self.root, 'COMP-one'))
        self.assertNotIn('--compensation-review-delivery', self.result['runner_command'])
        self.assertFalse(self.result['model_dispatched'])
        self.assertFalse(self.result['formal_adoption'])

    def test_default_v3_same_policy_proof_replays_its_original_artifacts(self):
        subject, refs = self.approve(selected=None)
        self.assertEqual(subject, self.subject)
        self.assertTrue((self.home / 'w/prompt.txt').read_bytes().startswith((V3 + ' ').encode()))
        self.assertEqual(materials.DELIVERY, V3)
        self.assertEqual(self.request['host_review_ref']['schema_version'], review.COMPENSATION_PROOF)
        self.assertTrue(refs)

    def test_v4_same_policy_proof_hashes_exact_validated_request_bytes(self):
        subject, refs = self.approve()
        proof = codec.strict_json_loads((self.home / 'review.json').read_bytes())
        self.assertEqual(proof['request_raw_digest'], codec.raw_digest((self.home / 'request.txt').read_bytes()))
        self.assertEqual(proof['schema_version'], review.COMPENSATION_PROOF)
        self.assertEqual(proof['claim'], materials.CLAIM)
        self.assertEqual(subject, self.subject)
        self.assertEqual({row['path'] for row in refs},
            {review.location('COMP-one') + '/' + name for name in [*review.support_names(review.MATERIAL_MODE), 'review.json']})

    def test_unknown_marker_and_mixed_known_marker_never_fall_back(self):
        self.approve()
        target = self.home / 'w/prompt.txt'
        original = target.read_bytes()
        for marker in ('unknown.delivery', V3, materials.LEGACY_DELIVERY, materials.V2_DELIVERY):
            try:
                target.write_bytes(original.replace(V4.encode(), marker.encode(), 1))
                with self.subTest(marker=marker), self.assertRaises(codec.CodecError):
                    review.verify_saved(self.root, self.request)
            finally:
                target.write_bytes(original)
        self.assertEqual(review.verify_saved(self.root, self.request)[0], self.subject)

    def test_real_saved_schema_request_output_and_host_protocol_drift_reject(self):
        self.approve()
        for name in ('materials.json', 'roles.json', 'presentation.json', 'w/prompt.txt',
                     'w/schema.json', 'request.txt', 'execution.json', 'w/output.json'):
            target = self.home / name
            original = target.read_bytes()
            try:
                target.write_bytes(original + b' ')
                with self.subTest(name=name), self.assertRaises((codec.CodecError, ValueError)):
                    review.verify_saved(self.root, self.request)
            finally:
                target.write_bytes(original)

    def test_old_runtime_request_cannot_approve_v4_saved_prompt(self):
        self.prepare()
        old_request = review.request_payload(self.subject, root=self.root, delivery=V3)
        completed(self.root, 'COMP-one', delivery=V4, prompt_override=old_request,
                  thread_id='synthetic-mixed-old-request')
        with self.assertRaises((codec.CodecError, ValueError)):
            adoption.complete_review(self.root, operation_id='COMP-one')
        self.assertFalse((self.home / 'review.json').exists())
        self.assertTrue((self.home / 'w/prompt.txt').read_bytes().startswith((V4 + ' ').encode()))

    def test_request_digest_tampering_cannot_be_hidden_by_new_proof_reference(self):
        self.approve()
        target = self.home / 'review.json'
        original = target.read_bytes()
        value = codec.strict_json_loads(original)
        value['request_raw_digest'] = codec.raw_digest(b'other request')
        modified = review.raw(value)
        request = deepcopy(self.request)
        request['host_review_ref']['raw_digest'] = codec.raw_digest(modified)
        try:
            target.write_bytes(modified)
            with self.assertRaises(codec.CodecError):
                review.verify_saved(self.root, request)
        finally:
            target.write_bytes(original)

    def test_cross_policy_v4_subject_still_rejects_before_material_replay(self):
        self.approve()
        target = self.home / 'subject.json'
        original = target.read_bytes()
        value = deepcopy(self.subject)
        value['policy_identity'] = codec.raw_digest(b'old unavailable policy')
        try:
            target.write_bytes(review.raw(value))
            with patch.object(review, 'model_packet', side_effect=AssertionError('cross-policy must stop first')):
                with self.assertRaises(codec.CodecError):
                    review.verify_saved(self.root, self.request)
        finally:
            target.write_bytes(original)

    def test_original_proof_v1_exact_replay_and_original_negative_matrix(self):
        case = composition.CompensationTests('test_legacy_compensation_proof_uses_exact_original_request_and_never_new_packet')
        case.test_legacy_compensation_proof_uses_exact_original_request_and_never_new_packet()

    def test_capacity_refusal_is_before_any_compensation_review_persistence(self):
        case = composition.CompensationTests('test_complete_reviewed_compensation_uses_new_id_and_shared_commit')
        case.baseline(bound=True)
        before = journal.operation_inventory(case.root)
        with patch.object(capacity, 'measure_request', side_effect=ValueError('complete unchanged byte/token capacity refusal')):
            with self.assertRaises(codec.CodecError):
                adoption.prepare_review(case.root, operation_id='COMP-one', request_ref=case.fx.request_ref(case.comp_request),
                                        compensation_delivery=V4)
        self.assertFalse((case.root / review.location('COMP-one') / 'subject.json').exists())
        self.assertEqual(journal.operation_inventory(case.root), before)

    def test_existing_v4_review_cannot_be_replaced_with_default_v3(self):
        self.prepare()
        before = {p.relative_to(self.home).as_posix(): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        with self.assertRaises(codec.CodecError):
            adoption.prepare_review(self.root, operation_id='COMP-one', request_ref=self.case.fx.request_ref(self.case.comp_request))
        after = {p.relative_to(self.home).as_posix(): p.read_bytes() for p in self.home.rglob('*') if p.is_file()}
        self.assertEqual(after, before)

    def test_original_adoption_cannot_select_compensation_delivery(self):
        with self.assertRaises(codec.CodecError):
            review.prompt({'producer': 'adoption'}, delivery=V4)

    def test_v4_same_validated_buffer_drift_blocks_original_short_writer(self):
        self.prepare()
        completed(self.root, 'COMP-one', delivery=V4, thread_id='synthetic-v4-buffer-drift')
        original = review.verify_semantic
        execution = self.home / 'execution.json'
        saved = execution.read_bytes()
        captured = []
        def drift(*args, **kwargs):
            result = original(*args, **kwargs)
            captured.append(dict(kwargs['buffers']))
            execution.write_bytes(saved + b' ')
            return result
        before = journal.operation_inventory(self.root)
        with patch.object(review, 'verify_semantic', side_effect=drift), self.assertRaises(codec.CodecError):
            adoption.complete_review(self.root, operation_id='COMP-one')
        self.assertEqual(captured[0]['execution.json'], saved)
        self.assertEqual(execution.read_bytes(), saved + b' ')
        self.assertFalse((self.home / 'review.json').exists())
        self.assertEqual(journal.operation_inventory(self.root), before)



class MultiViewOwnerCliTests(unittest.TestCase):
    def test_both_public_entries_forward_explicit_v4_only_on_review_prepare(self):
        fake = ModuleType('_b_route_adoption')
        fake.prepare_review = Mock(return_value={'status': 'review_prepared', **cli.FLAGS})
        argv = ['--root', '.', '--operation-id', 'COMP-one', '--stage', 'review-prepare',
                '--request', 'request.json', '--compensation-review-delivery', V4]
        with patch.dict(sys.modules, {'_b_route_adoption': fake}):
            for main, prefix in ((cli.main, []), (dev_cli.main, ['b-route-adoption'])):
                with redirect_stdout(io.StringIO()):
                    code = main(prefix + argv)
                self.assertEqual(code, 0)
                fake.prepare_review.assert_called_with(Path('.').absolute(), operation_id='COMP-one',
                    request_ref='request.json', compensation_delivery=V4)
        self.assertEqual(fake.prepare_review.call_count, 2)

    def test_selector_on_wrong_stage_or_unknown_version_stops_before_service(self):
        fake = ModuleType('_b_route_adoption')
        fake.complete_review = Mock()
        fake.prepare_review = Mock()
        for main, prefix in ((cli.main, []), (dev_cli.main, ['b-route-adoption'])):
            for tail in (['--stage', 'review-complete', '--compensation-review-delivery', V4],
                         ['--stage', 'review-prepare', '--request', 'request.json', '--compensation-review-delivery', 'unknown']):
                with patch.dict(sys.modules, {'_b_route_adoption': fake}), redirect_stdout(io.StringIO()):
                    self.assertEqual(main(prefix + ['--operation-id', 'COMP-one'] + tail), 2)
        fake.prepare_review.assert_not_called()
        fake.complete_review.assert_not_called()
