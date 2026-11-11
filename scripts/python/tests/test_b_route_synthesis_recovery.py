"""Focused synthetic recovery boundaries, never real model acceptance evidence.

Transaction files are real isolated temporary files. Runtime execution replay is
explicitly mocked; only the owning native real run can prove model acceptance.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_synthesis_recovery as recovery


def raw_json(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def retained_fixture():
    calls = []
    for number in range(1, 7):
        calls.append({'number': number, 'candidate': 'candidate-1' if number <= 4 else 'candidate-2',
                      'phase': 'semantic' if number in (3, 4) else 'generate', 'generation': 1, 'execution': 1,
                      'reservation_id': 'c4:dispatch:' + str(number),
                      'request_identity': {'attempt': number if number <= 4 else number - 4,
                                           'synthesis': number in (2, 6)},
                      'outcome': {'status': 'failed' if number == 6 else 'completed', 'active_elapsed_seconds': 1.0}})
    admitted = {'status': 'admitted', 'original_proof': 'synthetic-immutable-proof'}
    current = {'order_index': 0, 'execution': 1, 'selection_attempts': [],
               'admissions': {'candidate-1': admitted, 'candidate-2': {'status': 'blocked'}}}
    state = {'run_id': 'c4', 'capability_selection': {'calls': calls, 'total_invocations': 6,
              'lineage_invocations': {'candidate-1': 4, 'candidate-2': 2},
              'selected': [], 'terminal': True, 'current': current},
             'selection_status': 'blocked', 'selection_block_reason': 'selection_blocked_insufficient_admitted_candidates',
             'active_elapsed_seconds': 8.0, 'mvg.run_invocation_limit': 96,
             'b_route_campaign_funding': {'paid_or_unknown_before_run': 55, 'campaign_limit': 290,
                  'subsequent_full_reservation': 192, 'maximum_native_charges': 43, 'released': 0},
             'b_route_review_recovery': {'original': 'review-reference'},
             'b_route_execution_transition': {'transition_digest': 'previous-transition'}}
    append = {'status': 'blocked', 'total_invocations': 2,
              'calls': [{'reservation_id': 'c4:dispatch:5', 'number': 1, 'context': 1, 'phase': 'generate'},
                        {'reservation_id': 'c4:dispatch:6', 'number': 2, 'context': 1, 'phase': 'generate'}],
              'completed': [], 'records': [], 'current': {'context': 1, 'issue': None, 'proposal': None, 'delta': None},
              'binding': 'synthetic-original-binding', 'errors': [{'code': 'retained-provider-rejection'}]}
    return state, append


class SynthesisRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get('SYNTHESIS_RECOVERY_TEST_TEMP'))
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.run_ref = 'logs/ci/capability-planning/c4'
        self.run = self.root / self.run_ref
        self.workspace = self.run / recovery.WORKSPACE
        self.home = self.run / 'recovery/synthesis-1'
        self.old_state, self.old_append = retained_fixture()
        self.binding_ref = recovery.WORKSPACE + '/capability-append/c1/execution-binding-1-r.json'
        self.draft_ref = recovery.WORKSPACE + '/capability-append/c1/canonical-draft.json'
        self.binding = {'retained': 'original synthetic execution binding'}
        self.draft = {'stage': 'batch', 'ordinal': 1, 'content': {'kept': 'original paid content'}}
        self.write(self.run / self.binding_ref, self.binding)
        self.write(self.run / self.draft_ref, self.draft)
        self.protected = self.run / 'candidate-1-original-proof.json'
        self.write(self.protected, {'proof': 'must remain byte-identical'})
        transition = {'transition_digest': 'synthetic-new-transition'}
        history = {'previous-transition': self.old_state['b_route_execution_transition']}
        self.record = {'schema_version': recovery.SCHEMA, 'run_id': 'c4', 'run_ref': self.run_ref,
                       'previous_run': recovery.image(raw_json(self.old_state)),
                       'previous_append': recovery.image(raw_json(self.old_append)),
                       'immutable_files': {path.relative_to(self.run).as_posix(): recovery.codec.raw_digest(path.read_bytes())
                                           for path in (self.protected, self.run / self.binding_ref, self.run / self.draft_ref)},
                       'transition': transition, 'history': history, 'output_schema_policy': 'synthetic-provider-policy',
                       'completed_binding_ref': self.binding_ref, 'completed_draft_ref': self.draft_ref,
                       'completed_binding_digest': recovery.canonical_sha(self.binding),
                       'completed_draft_digest': recovery.canonical_sha(self.draft),
                       'retained_slots': 6, 'released': 0, 'next_native_dispatch': 7,
                       'next_local_dispatch': 3, 'maximum_new_synthesis_attempts': 1}
        self.state = deepcopy(self.old_state)
        self.state.update(b_route_execution_transition=transition, b_route_execution_history=history,
                          b_route_output_schema_policy='synthetic-provider-policy', runtime_slot='candidate-2',
                          runtime_execution=1, selection_status='pending')
        self.state['capability_selection']['terminal'] = False
        self.state.pop('selection_block_reason')
        self.persist_record()
        local = deepcopy(self.old_append)
        local['status'] = 'generating'
        self.local_path = self.workspace / 'capability-append/append-ledger.json'
        self.write(self.local_path, local)
        self.write(self.run / 'run.json', self.state)
        self.accepted = {'original': 'accepted seed'}
        self.expected_root = {'complete': 'original request material'}
        self.materials = {'phase': 'generation', 'slot': 'candidate-2', 'generation': 1, 'execution': 1,
                          'lineage_context': 1, 'root_request': self.expected_root, 'accepted_seed': self.accepted,
                          'prior_candidate': None, 'repair_issue': None, 'lineage_identity': 'original-lineage'}
        self.runtime = SimpleNamespace(
            verify_reserved_call=Mock(return_value=deepcopy(self.binding)),
            verify_call=Mock(return_value={'carrier': 'original'}),
            decode_generation_carrier=Mock(return_value=deepcopy(self.draft)),
            same_json=lambda left, right: recovery.canonical_sha(left) == recovery.canonical_sha(right),
            bound_materials=Mock(return_value=self.materials),
            request_attempt=Mock(return_value={'payload': json.dumps(self.expected_root)}),
            wire_delivery=Mock(return_value='synthetic-wire'),
            lineage_identity=Mock(return_value='original-lineage'),
            planning=SimpleNamespace(validate_draft_chain=Mock(return_value=['original-draft-identity'])))

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw_json(value))

    def persist_record(self):
        path = self.home / 'record.json'
        self.write(path, self.record)
        reference = {'schema_version': recovery.SCHEMA, 'record_ref': path.relative_to(self.root).as_posix(),
                     'record_digest': recovery.codec.raw_digest(path.read_bytes()), 'artifact_root': str(self.root)}
        self.state['b_route_synthesis_recovery'] = reference
        self.write(self.home / 'committed.json', {'record_digest': reference['record_digest'],
                                                'transition_digest': self.record['transition']['transition_digest']})

    def snapshot(self):
        return {path.relative_to(self.root).as_posix(): path.read_bytes()
                for path in self.root.rglob('*') if path.is_file()}

    def assert_validation_rejects_without_writes(self, state, reason):
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, reason):
            recovery.validate_recovery(self.root, state)
        self.assertEqual(before, self.snapshot())

    def resume(self, state=None, **changes):
        parameters = {'workspace': self.workspace, 'frozen': {'synthetic': 'frozen'}, 'accepted': self.accepted,
                      'prior': None, 'issue': None, 'context': 1}
        parameters.update(changes)
        with patch.dict(sys.modules, {'_b_route_planning_runtime': self.runtime}):
            return recovery.resume_generation(self.root, self.state if state is None else state, **parameters)

    def test_retained_shape_accepts_exact_known_failed_prefix_without_mutation(self):
        before = (raw_json(self.old_state), raw_json(self.old_append))
        self.assertIsNone(recovery.retained_shape(self.old_state, self.old_append))
        self.assertEqual(before, (raw_json(self.old_state), raw_json(self.old_append)))

    def test_retained_shape_rejects_unknown_or_relabelled_failed_calls(self):
        cases = ('unknown', 'last-completed', 'earlier-failed', 'wrong-phase', 'wrong-attempt', 'new-execution')
        for case in cases:
            with self.subTest(case=case):
                state, append = retained_fixture()
                calls = state['capability_selection']['calls']
                if case == 'unknown':
                    calls[-1]['outcome']['status'] = 'unknown'
                elif case == 'last-completed':
                    calls[-1]['outcome']['status'] = 'completed'
                elif case == 'earlier-failed':
                    calls[4]['outcome']['status'] = 'failed'
                elif case == 'wrong-phase':
                    calls[-1]['phase'] = 'semantic'
                elif case == 'wrong-attempt':
                    calls[-1]['request_identity']['attempt'] = 1
                else:
                    calls[-1]['execution'] = 2
                with self.assertRaises(ValueError):
                    recovery.retained_shape(state, append)

    def test_retained_shape_rejects_counter_clock_and_budget_changes(self):
        for case in ('total', 'number', 'lineage', 'time', 'native-cap', 'campaign', 'headroom', 'refund', 'old-paid', 'mvg-cap'):
            with self.subTest(case=case):
                state, append = retained_fixture()
                ledger, funding = state['capability_selection'], state['b_route_campaign_funding']
                if case == 'total':
                    ledger['total_invocations'] = 5
                elif case == 'number':
                    ledger['calls'][5]['number'] = 5
                elif case == 'lineage':
                    ledger['lineage_invocations']['candidate-2'] = 1
                elif case == 'time':
                    state['active_elapsed_seconds'] = 5.0
                elif case == 'native-cap':
                    state['mvg.run_invocation_limit'] = 95
                else:
                    key, value = {'campaign': ('campaign_limit', 291), 'headroom': ('maximum_native_charges', 44),
                                  'refund': ('released', 1), 'old-paid': ('paid_or_unknown_before_run', 54),
                                  'mvg-cap': ('subsequent_full_reservation', 191)}[case]
                    funding[key] = value
                with self.assertRaises(ValueError):
                    recovery.retained_shape(state, append)

    def test_validate_accepts_committed_record_and_monotonic_time_without_writes(self):
        state = deepcopy(self.state)
        state['active_elapsed_seconds'] += 1
        before = self.snapshot()
        self.assertEqual(self.record, recovery.validate_recovery(self.root, state))
        self.assertEqual(before, self.snapshot())

    def test_validate_rejects_missing_or_mismatched_commit_marker_without_repair(self):
        path = self.home / 'committed.json'
        original = path.read_bytes()
        path.unlink()
        before = self.snapshot()
        with self.assertRaises(OSError):
            recovery.validate_recovery(self.root, self.state)
        self.assertEqual(before, self.snapshot())
        path.write_bytes(original)
        self.write(path, {'record_digest': 'wrong', 'transition_digest': 'synthetic-new-transition'})
        self.assert_validation_rejects_without_writes(self.state, 'partial_transaction')

    def test_validate_rejects_original_file_tamper_and_funding_or_counter_refund(self):
        raw = self.protected.read_bytes()
        self.protected.write_bytes(b'actual later edit')
        self.assert_validation_rejects_without_writes(self.state, 'retained_file_changed')
        self.protected.write_bytes(raw)
        for case in ('refund', 'time', 'prefix', 'total', 'lineage', 'native-cap', 'admitted'):
            with self.subTest(case=case):
                state = deepcopy(self.state)
                ledger = state['capability_selection']
                if case == 'refund':
                    state['b_route_campaign_funding']['released'] = 1
                elif case == 'time':
                    state['active_elapsed_seconds'] = 7.0
                elif case == 'prefix':
                    ledger['calls'][5]['outcome']['status'] = 'unknown'
                elif case == 'total':
                    ledger['total_invocations'] = 5
                elif case == 'lineage':
                    ledger['lineage_invocations']['candidate-2'] = 1
                elif case == 'native-cap':
                    state['mvg.run_invocation_limit'] = 95
                else:
                    ledger['current']['admissions']['candidate-1']['original_proof'] = 'changed'
                self.assert_validation_rejects_without_writes(state,
                    'source_or_funding_changed|retained_charge_or_clock_changed|admitted_candidate_changed')

    def test_worker_view_revalidates_actual_coordinator_admission(self):
        worker = deepcopy(self.state)
        worker['capability_selection']['current'] = None
        self.assertEqual(self.record, recovery.validate_recovery(self.root, worker))
        owner = deepcopy(self.state)
        owner['capability_selection']['current']['admissions']['candidate-1']['original_proof'] = 'changed'
        self.write(self.run / 'run.json', owner)
        self.assert_validation_rejects_without_writes(worker, 'admitted_candidate_changed')

    def native_selected_fixture(self):
        # These identifiers were unnecessary for the existing current-only
        # fixtures. Add them only for native selected-step shape coverage.
        scope = {'capability_id': 'synthetic-scope-0', 'base_sha256': recovery.canonical_sha(self.accepted)}
        self.old_state['capability_selection']['current'].update(scope)
        self.record['previous_run'] = recovery.image(raw_json(self.old_state))
        self.state['capability_selection']['current'].update(scope)
        self.persist_record()
        selected = {'status': 'completed', 'attempt': 1, 'selected_candidate': 'candidate-2',
                    'input_identity': {**scope, 'order_index': 0},
                    'admissions': deepcopy(self.state['capability_selection']['current']['admissions'])}
        selected['admissions']['candidate-2']['status'] = 'admitted'
        state = deepcopy(self.state)
        state['capability_selection'].update(selected=[selected], current=None)
        return state

    def test_native_selected_prefix_without_top_level_order_index_is_accepted(self):
        state = self.native_selected_fixture()
        selected = state['capability_selection']['selected'][0]
        self.assertNotIn('order_index', selected)
        self.assertEqual(0, selected['input_identity']['order_index'])
        before = self.snapshot()
        self.assertEqual(self.record, recovery.validate_recovery(self.root, state))
        self.assertEqual(before, self.snapshot())

    def test_native_selected_prefix_rejects_wrong_identity_and_duplicate_current(self):
        original = self.native_selected_fixture()
        for field, value in (('order_index', 1), ('capability_id', 'different-scope'),
                             ('base_sha256', 'changed-base')):
            with self.subTest(field=field):
                state = deepcopy(original)
                state['capability_selection']['selected'][0]['input_identity'][field] = value
                self.assert_validation_rejects_without_writes(state, 'selected_scope_identity_changed')
        state = deepcopy(original)
        state['capability_selection']['selected'][0]['status'] = 'failed'
        self.assert_validation_rejects_without_writes(state, 'selected_scope_identity_changed')
        state = deepcopy(original)
        state['capability_selection']['current'] = deepcopy(self.state['capability_selection']['current'])
        self.assert_validation_rejects_without_writes(state, 'admitted_candidate_changed')

    def test_worker_owner_native_selected_prefix_is_accepted_and_identity_rechecked(self):
        owner = self.native_selected_fixture()
        self.write(self.run / 'run.json', owner)
        worker = deepcopy(self.state)
        worker['capability_selection']['current'] = None
        self.assertEqual([], worker['capability_selection']['selected'])
        before = self.snapshot()
        self.assertEqual(self.record, recovery.validate_recovery(self.root, worker))
        self.assertEqual(before, self.snapshot())
        owner['capability_selection']['selected'][0]['input_identity']['base_sha256'] = 'changed-base'
        self.write(self.run / 'run.json', owner)
        self.assert_validation_rejects_without_writes(worker, 'selected_scope_identity_changed')

    def test_resume_returns_original_completed_prefix_and_checks_runtime_boundary(self):
        before = self.snapshot()
        self.assertEqual(([self.draft], [self.binding]), self.resume())
        self.runtime.verify_reserved_call.assert_called_once_with(self.run, self.state['capability_selection']['calls'][4])
        self.runtime.verify_call.assert_called_once_with(self.binding)
        self.runtime.planning.validate_draft_chain.assert_called_once_with({'synthetic': 'frozen'}, [self.draft])
        self.assertEqual(before, self.snapshot())

    def test_resume_refuses_consumed_attempt_wrong_context_and_wrong_workspace(self):
        state = deepcopy(self.state)
        extra = deepcopy(state['capability_selection']['calls'][-1])
        extra.update(number=7, phase='generate')
        state['capability_selection']['calls'].append(extra)
        state['capability_selection']['total_invocations'] = 7
        state['capability_selection']['lineage_invocations']['candidate-2'] = 3
        with self.assertRaisesRegex(ValueError, 'synthesis_attempt_already_consumed'):
            self.resume(state)
        for changes in ({'context': 2}, {'prior': {'candidate': 'new'}}, {'issue': {'repair': 'new'}}):
            with self.subTest(changes=changes):
                self.assertIsNone(self.resume(**changes))
        with self.assertRaisesRegex(ValueError, 'workspace_changed'):
            self.resume(workspace=self.root / 'wrong-workspace')
        self.runtime.verify_call.assert_not_called()

    def test_resume_rejects_changed_retained_draft_and_wrong_request_lineage(self):
        self.runtime.decode_generation_carrier.return_value = {'different': 'output'}
        with self.assertRaisesRegex(ValueError, 'raw_draft_changed'):
            self.resume()
        self.runtime.decode_generation_carrier.return_value = deepcopy(self.draft)
        self.runtime.bound_materials.return_value = {**self.materials, 'lineage_identity': 'wrong-lineage'}
        with self.assertRaisesRegex(ValueError, 'retained_generation_inputs_changed'):
            self.resume()


if __name__ == '__main__':
    unittest.main(verbosity=2)
