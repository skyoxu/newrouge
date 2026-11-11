"""Thin recovery composition; upstream qualification/runner boundaries are fake.

These checks exercise real generation sequencing, hint placement and closed
activation gates. They do not prove actual paid/native/model eligibility.
"""
from contextlib import ExitStack
from copy import deepcopy
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _b_route_planning_runtime as runtime
import _b_route_mvg_synthesis_recovery as recovery
import _mvg_capability_append as append_owner
import _b_route_execution_transition as transition
import _b_route_review_recovery as old_review
from test_b_route_mvg_synthesis_recovery import make_material_fixture


class MvgRecoveryWiringTests(unittest.TestCase):
    def setUp(self):
        self.parent = Path(tempfile.gettempdir()).resolve(strict=True)
        self.name = 'mw19_' + uuid.uuid4().hex[:10]
        self.root = self.parent / self.name
        self.root.mkdir(exist_ok=False)
        self.addCleanup(self.cleanup_owned)

    def cleanup_owned(self):
        result = getattr(getattr(self, '_outcome', None), 'result', None)
        if any(case is self for case, _ in getattr(result, 'errors', []) + getattr(result, 'failures', [])):
            print('Retained failed wiring fixture: ' + str(self.root))
            return
        path = self.root.resolve(strict=True)
        if path.parent != self.parent or path.name != self.name:
            raise AssertionError('Fixture escaped its allocated parent/name')
        shutil.rmtree(path)

    def generation(self, *, recovering):
        state, record, originals, material = make_material_fixture()
        state.update(run_id='m4', runtime_identity='sha256:' + 'c' * 64, runtime_slot='candidate-2', runtime_execution=1,
                     capability_selection={'generation': 1})
        if recovering:
            state['b_route_execution_transition'] = {'schema_version': recovery.MVG_EPOCH_SCHEMA,
                                                    'transition_digest': 'sha256:' + 'd' * 64}
        else:
            state.pop(recovery.REFERENCE)
        frozen = {'transport': {'batches': [{}]}, 'input_identity': 'sha256:' + 'e' * 64}
        seed = material['accepted_seed']
        count = 2 if recovering else 0
        ledger = self.root / 'capability-append/append-ledger.json'
        ledger.parent.mkdir()
        ledger.write_text(json.dumps({'total_invocations': count}), encoding='utf-8')
        invocations, requests, chains, products = [], [], [], []
        action_accounts = []

        def request(_frozen, *, phase, seed_value, prior, issue, context, drafts, batch, delivery, work):
            self.assertIsNotNone(work)
            self.assertIsInstance(work, runtime.compact._EncodingWork)
            action_accounts.append(work)
            requests.append((batch, deepcopy(drafts)))
            return {'phase': phase, 'root_input_identity': frozen['input_identity'],
                    'root_request': {'input': {'stage': 'batch' if batch else 'synthesis',
                        'ordinal': batch or len(drafts) + 1, 'prior_drafts': [
                            {'identity': runtime.canonical_sha(d), 'value': deepcopy(d)} for d in drafts]}},
                    'accepted_seed': seed_value, 'prior_candidate': prior, 'repair_issue': issue,
                    'lineage_context': context}

        def invoke(_factory, _frozen, workspace, number, payload, schema, phase, call, *, state, work):
            self.assertIs(work, action_accounts[-1])
            invocations.append((workspace, number, deepcopy(payload)))
            root_request = payload['root_request']['input']
            draft = {'stage': root_request['stage'], 'ordinal': root_request['ordinal'],
                     'content': {'synthetic': 'new-output'}}
            return draft, {'synthetic_binding': number}

        def original_append(_workspace, **options):
            products.append(options['propose']({'capability_id': 'synthetic-unit'}, seed, None, None, 1, object()))
            return {'status': 'blocked', 'synthetic': 'stop after the control-path probe'}

        with ExitStack() as stack:
            for name, value in (('frozen_input', frozen), ('scopes', [{'capability_id': 'synthetic-unit'}]),
                                ('seed', seed), ('wire_delivery', runtime.wire.CURRENT_SCHEMA), ('issue_account_policy', None),
                                ('lineage_identity', 'sha256:' + 'f' * 64), ('generation_schema', {})):
                stack.enter_context(patch.object(runtime, name, return_value=value))
            stack.enter_context(patch.object(runtime, 'validate_input'))
            stack.enter_context(patch.object(runtime, 'request_payload', side_effect=request))
            stack.enter_context(patch.object(runtime, 'invoke_data', side_effect=invoke))
            stack.enter_context(patch.object(runtime.planning, 'validate_draft_chain',
                side_effect=lambda _frozen, drafts: chains.append(deepcopy(drafts))))
            stack.enter_context(patch.object(append_owner, 'run_capability_append', side_effect=original_append))
            if recovering:
                stack.enter_context(patch.object(recovery, 'resume_generation',
                    return_value=(deepcopy(originals), [{'synthetic_binding': 1}, {'synthetic_binding': 2}])))
                stack.enter_context(patch.object(recovery, 'validate_recovery', return_value=record))
                stack.enter_context(patch.object(recovery, '_check_synthesis_claim'))
            else:
                stack.enter_context(patch.object(recovery, 'resume_generation', side_effect=AssertionError('Legacy must not resume')))
                stack.enter_context(patch.object(recovery, 'decorate_payload', side_effect=AssertionError('Legacy must not decorate')))
            result = runtime.generate_append(self.root, state, self.root,
                invoke_factory=object(), before_call=object(), checkpoint=object())
        self.assertEqual(result['status'], 'blocked')
        return invocations, requests, chains, products, originals

    def test_completed_two_drafts_get_one_ordinal_three_with_full_metadata_before_real_hint(self):
        calls, requests, chains, products, originals = self.generation(recovering=True)
        self.assertEqual(len(calls), 1)
        workspace, local_number, payload = calls[0]
        self.assertEqual(local_number, 3)
        self.assertEqual(workspace, self.root / 'capability-append/m1/c3')
        self.assertEqual(requests, [(None, originals)])
        self.assertEqual(payload['slot'], 'candidate-2')
        self.assertEqual((payload['generation'], payload['execution'], payload['lineage_context']), (1, 1, 1))
        self.assertIn(recovery.HINT_KEY, payload)
        self.assertEqual(payload['root_request']['input']['ordinal'], 3)
        self.assertEqual(chains[0][:2], originals)
        self.assertEqual(products[0]['candidate']['provenance']['draft_chain'], chains[0])
        self.assertEqual(products[0]['generation_calls'][:2], [{'synthetic_binding': 1}, {'synthetic_binding': 2}])

    def test_legacy_generation_keeps_batch_then_synthesis_without_recovery_fields(self):
        calls, requests, chains, _products, _originals = self.generation(recovering=False)
        self.assertEqual([call[1] for call in calls], [1, 2])
        self.assertEqual([call[0] for call in calls], [self.root / 'capability-append/c1', self.root / 'capability-append/c2'])
        self.assertEqual([row[0] for row in requests], [1, None])
        self.assertEqual(len(chains[-1]), 2)
        self.assertTrue(all(recovery.HINT_KEY not in call[2] for call in calls))

    def test_typed_epoch_without_reference_cannot_skip_recovery_before_evidence_io(self):
        frozen = {'synthetic': 'only the old prepared authority boundary is mocked'}
        desc = {'frozen_sha256': runtime.canonical_sha(frozen), 'input_identity': 'synthetic-input'}
        frozen['input_identity'] = desc['input_identity']
        desc['frozen_sha256'] = runtime.canonical_sha(frozen)
        state = {'b_route_execution_transition': {'schema_version': recovery.MVG_EPOCH_SCHEMA}}
        with patch.object(runtime, 'descriptor', return_value=desc), \
             patch.object(transition, 'load_prepared', return_value=frozen), \
             patch.object(recovery.sources, 'checked_path', side_effect=AssertionError('No artifact path before typed ref')), \
             patch.object(recovery.codec, 'read_reference_bytes', side_effect=AssertionError('No evidence IO before typed ref')):
            with self.assertRaisesRegex(ValueError, 'typed_reference'):
                runtime._frozen_input_owned(self.root, state)

    def test_unactivated_hint_is_rejected_before_older_binding_owner(self):
        prompt = self.root / 'prompt.txt'
        prompt.write_text('Synthetic parser material', encoding='utf-8')
        with patch.object(runtime, 'wire_delivery', return_value=runtime.wire.CURRENT_SCHEMA), \
             patch.object(runtime.wire, 'read_prompt', return_value={recovery.HINT_KEY: {'fake': True}}), \
             patch.object(old_review, 'validate_materials_transition', side_effect=AssertionError('Must reject before old owner')):
            with self.assertRaisesRegex(ValueError, 'materials_unactivated'):
                runtime.bound_materials({'prompt_path': str(prompt)}, {}, {})


if __name__ == '__main__':
    unittest.main()
