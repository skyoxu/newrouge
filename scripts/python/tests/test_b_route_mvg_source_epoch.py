"""Offline MVG epoch boundaries; original source/native collector is mocked.

All seven paid artifacts are private fixture bytes, not actual m4 evidence.
This tests the real epoch/history/path/raw-pin logic without any native/model,
Git/source-policy subprocess or project access. Failure fixtures are retained.
"""
from copy import deepcopy
import base64
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch
import uuid

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_codec as codec
import _b_route_execution_transition as transition

BASE = Path('C:/Windows/TEMP') if os.name == 'nt' else Path('/tmp')


class MvgSourceEpochTests(unittest.TestCase):
    def setUp(self):
        self.fixture_name = 'me19-' + uuid.uuid4().hex[:12]
        self.root = BASE.resolve(strict=True) / self.fixture_name
        self.root.mkdir()
        self.addCleanup(self.cleanup_fixture)
        self.old_root, self.new_root, self.original_root = [self.root / name for name in ('r10', 'r19', 'r5')]
        for path in (self.old_root, self.new_root, self.original_root):
            path.mkdir()
        self.run = self.root / 'logs/ci/mvg-planning/m4'
        self.run.mkdir(parents=True)
        self.new_commit = '9' * 40
        self.frozen = {'fixture': 'original frozen input; never native acceptance'}
        self.prepared_raw = self.raw(self.frozen)
        self.prepared_ref = 'fixture/prepared.json'
        self.put(self.root / self.prepared_ref, self.frozen)
        self.descriptor = {'planner': 'mvg', 'profile': '3b-mvg-v1', 'prepared_ref': self.prepared_ref,
            'input_identity': codec.canonical_digest('fixture-input'), 'frozen_sha256': codec.canonical_digest(self.frozen),
            'rules': {'fixture': 'mock original collector'}}
        self.base = {'schema_version': transition.SCHEMA, 'original_source_root': str(self.original_root),
            'original_commit': transition.ORIGINAL_COMMIT, 'artifact_root': str(self.root),
            'original_run_schema': transition.ORIGINAL_RUN_SCHEMA, 'prepared_ref': self.prepared_ref,
            'prepared_raw_digest': codec.raw_digest(self.prepared_raw), 'frozen_sha256': codec.canonical_digest(self.frozen),
            'original_runtime_identity': codec.canonical_digest(self.descriptor), 'original_runtime_rules': self.descriptor['rules'],
            'original_tracked_sources': {'original.py': {'fixture': True}}}
        self.prior = self.envelope(self.old_root, transition.MVG_PRIOR_COMMIT)
        self.state = {'schema_version': transition.CURRENT_RUN_SCHEMA, 'run_id': 'm4', 'input_stage': '3b',
            'b_route_execution_transition': self.prior, 'active_elapsed_seconds': 4882.767,
            'runtime_identity': self.base['original_runtime_identity'], 'planning_runtime': deepcopy(self.descriptor),
            'analysis_identity_sha256': self.descriptor['input_identity'], 'mvg.run_invocation_limit': 192,
            'mvg.run_invocation_limit_source': 'profile_default', 'selection_status': 'blocked',
            'b_route_campaign_funding': {'fixture_paid_or_unknown': 73, 'limit': 290, 'released': 0},
            'checkpoint_strategy': 'capability-selected-checkpoint.v1', 'checkpoint_schema_version': 'fixture-checkpoint',
            'recovery': {'store': str(self.root / 'logs/ci/mvg-recovery'), 'epoch': 4},
            'b_route_output_schema_policy': 'newrouge.b-route-provider-output-schema.v1',
            'b_route_input_compact_policy': 'newrouge.b-route-compact-literal.v2',
            'capability_selection': {'calls': [], 'total_invocations': 7, 'lineage_invocations':
                {'candidate-1': 5, 'candidate-2': 2, 'candidate-3': 0}, 'selected': [], 'terminal': True,
                'current': {'order_index': 0, 'execution': 1, 'selection_attempts': [], 'admissions': {
                    'candidate-1': {'status': 'admitted', 'total_invocations': 5},
                    'candidate-2': {'status': 'blocked', 'total_invocations': 2}}}}}
        self.bindings = []
        patterns = (('candidate-1', 'generate', 1, False), ('candidate-1', 'generate', 2, True),
                    ('candidate-1', 'repair', 3, False), ('candidate-1', 'repair', 4, True),
                    ('candidate-1', 'semantic', 5, False), ('candidate-2', 'generate', 1, False),
                    ('candidate-2', 'generate', 2, True))
        for number, (label, phase, attempt, synthesis) in enumerate(patterns, 1):
            relative = 'candidates/' + label + '/scope-1/capability-append/c' + str(attempt)
            binding = {'output_path': (self.run / relative / 'output.json').as_posix(),
                       'fixture_original_completed_paid_binding': number}
            request = {'execution_binding_path': relative + '/binding.json', 'output_path': relative + '/output.json',
                       'attempt': attempt, 'synthesis': synthesis}
            self.state['capability_selection']['calls'].append({'number': number, 'reservation_id': 'm4:dispatch:' + str(number),
                'candidate': label, 'phase': phase, 'generation': 1, 'execution': 1, 'request_identity': request,
                'outcome': {'status': 'completed', 'active_elapsed_seconds': float(number)}})
            self.bindings.append(binding)
            self.put(self.run / request['execution_binding_path'], binding)
        self.proof = {'execution_source_transition': deepcopy(self.prior), 'fixture': 'original admitted candidate-1 proof'}
        admission = self.state['capability_selection']['current']['admissions']['candidate-1']
        for field, name, value in (('proof_path', 'admission-review.json', self.proof),
                                   ('proposal_path', 'proposal.json', {'fixture': 'original admitted proposal'}),
                                   ('execution_path', 'admission-execution.json', {'fixture': 'original paid five'})):
            relative = 'candidates/candidate-1/scope-1/' + name
            admission[field] = relative
            self.put(self.run / relative, value)
        self.put(self.run / 'run.json', self.state)
        self.patches = [patch.object(transition, '_collect', side_effect=self.collect),
            patch.object(transition, '_SOURCE_ROOT', self.new_root),
            patch.object(subprocess, 'Popen', side_effect=AssertionError('No native/Git/model subprocess')),
            patch.object(socket.socket, 'connect', side_effect=AssertionError('No network'))]
        for guard in self.patches:
            guard.start()
            self.addCleanup(guard.stop)

    @staticmethod
    def raw(value):
        return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()

    def put(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.raw(value))

    def cleanup_fixture(self):
        outcome = getattr(self, '_outcome', None)
        result = getattr(outcome, 'result', None)
        if any(case is self for case, _ in getattr(result, 'errors', []) + getattr(result, 'failures', [])):
            print('Retained failed offline MVG source fixture: ' + str(self.root))
            return
        target = self.root.resolve(strict=True)
        if target.parent != BASE.resolve(strict=True) or target.name != self.fixture_name:
            raise AssertionError('Fixture escaped its owned TEMP parent/name')
        shutil.rmtree(target)

    def envelope(self, root, commit):
        body = {**deepcopy(self.base), 'current_source_root': str(root), 'current_commit': commit,
                'current_tracked_sources': {'runtime.py': {'fixture_commit': commit}}}
        return {**body, 'transition_digest': codec.canonical_digest(body)}

    def collect(self, root, state, original_root, current_commit, *, current_root=None):
        actual_root = Path(current_root) if current_root is not None else self.new_root
        expected = transition.MVG_PRIOR_COMMIT if actual_root == self.old_root else self.new_commit
        if actual_root not in (self.old_root, self.new_root) or current_commit != expected:
            raise transition.TransitionError('fixture_source_drift')
        if (self.root / self.prepared_ref).read_bytes() != self.prepared_raw:
            raise transition.TransitionError('fixture_prepared_raw_drift')
        value = self.envelope(actual_root, current_commit)
        value.pop('transition_digest')
        return value, deepcopy(self.frozen)

    def active(self):
        value = transition.build_mvg_synthesis_transition(self.root, self.state, self.original_root,
            self.new_commit, self.old_root, transition.MVG_PRIOR_COMMIT)
        result = deepcopy(self.state)
        result['b_route_execution_transition'] = value
        result['b_route_execution_history'] = {self.prior['transition_digest']: deepcopy(self.prior)}
        return result

    def test_distinct_mvg_epoch_preserves_exact_seven_paid_raw_and_clock_without_writes(self):
        original = (self.run / 'run.json').read_bytes()
        state = self.active()
        value = state['b_route_execution_transition']
        self.assertEqual(transition.MVG_EPOCH_SCHEMA, value['schema_version'])
        self.assertNotIn(value['schema_version'], (transition.EPOCH_SCHEMA, transition.EPOCH_V2_SCHEMA))
        self.assertEqual(original, base64.b64decode(value['previous_run']['bytes_base64']))
        self.assertEqual(self.state['capability_selection']['calls'], state['capability_selection']['calls'])
        self.assertEqual(4882.767, state['active_elapsed_seconds'])
        self.assertEqual(original, (self.run / 'run.json').read_bytes())
        self.assertEqual(value['transition_digest'], transition.validate_transition(self.root, state))
        self.assertEqual(self.prior, transition.historical_state(self.root, state, self.prior['transition_digest'])['b_route_execution_transition'])
        self.assertEqual(self.state, transition.source_state_for_proof(self.root, state, self.proof))

    def test_mvg_historical_materials_use_actual_as_posix_paid_binding_not_capability_root(self):
        state = self.active()
        material = {'execution_source_transition': self.prior['transition_digest']}
        actual = transition.source_state_for_materials(self.root, state, material, self.bindings[6])
        self.assertEqual(self.state, actual)
        wrong = deepcopy(self.bindings[6])
        wrong['output_path'] = wrong['output_path'].replace('/mvg-planning/', '/capability-planning/')
        with self.assertRaises(transition.TransitionError):
            transition.source_state_for_materials(self.root, state, material, wrong)
        wrong = deepcopy(self.bindings[6]); wrong['caller_rewritten'] = True
        with self.assertRaises(transition.TransitionError):
            transition.source_state_for_materials(self.root, state, material, wrong)

    def test_unknown_duplicate_counter_stage_and_planner_prefixes_are_rejected(self):
        changes = []
        value = deepcopy(self.state); value['capability_selection']['calls'][6]['outcome']['status'] = 'unknown'; changes.append(value)
        value = deepcopy(self.state); value['capability_selection']['calls'][6]['reservation_id'] = 'm4:dispatch:6'; changes.append(value)
        value = deepcopy(self.state); value['capability_selection']['lineage_invocations']['candidate-2'] = 1; changes.append(value)
        value = deepcopy(self.state); value['capability_selection']['calls'][6]['request_identity']['synthesis'] = False; changes.append(value)
        value = deepcopy(self.state); value['capability_selection']['calls'][6]['execution'] = 2; changes.append(value)
        value = deepcopy(self.state); value['planning_runtime']['planner'] = 'capabilities'; changes.append(value)
        value = deepcopy(self.state); value['capability_selection']['selected'] = [{'caller': 'admitted'}]; changes.append(value)
        for index, value in enumerate(changes):
            with self.subTest(index=index), self.assertRaises(transition.TransitionError):
                transition._closed_mvg_paid_prefix(value)

    def test_later_calls_remain_charged_and_old_prefix_funding_clock_cannot_change(self):
        state = self.active()
        future = deepcopy(state['capability_selection']['calls'][-1])
        future.update(number=8, reservation_id='m4:dispatch:8')
        state['capability_selection']['calls'].append(future)
        state['capability_selection']['total_invocations'] = 8
        state['capability_selection']['lineage_invocations']['candidate-2'] = 3
        state['active_elapsed_seconds'] += 23.5
        transition.validate_transition(self.root, state)
        variants = []
        value = deepcopy(state); value['capability_selection']['calls'][0]['outcome']['active_elapsed_seconds'] = 0; variants.append(value)
        value = deepcopy(state); value['capability_selection']['total_invocations'] = 7; variants.append(value)
        value = deepcopy(state); value['capability_selection']['lineage_invocations']['candidate-2'] = 2; variants.append(value)
        value = deepcopy(state); value['active_elapsed_seconds'] = self.state['active_elapsed_seconds'] - 0.1; variants.append(value)
        value = deepcopy(state); value['b_route_campaign_funding']['released'] = 1; variants.append(value)
        value = deepcopy(state); value['mvg.run_invocation_limit'] = 193; variants.append(value)
        for index, value in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(transition.TransitionError):
                transition.validate_transition(self.root, value)

    def test_old_admitted_proof_and_paid_binding_tamper_are_not_reinterpreted(self):
        state = self.active()
        paths = [self.run / self.state['capability_selection']['calls'][6]['request_identity']['execution_binding_path'],
                 self.run / self.state['capability_selection']['current']['admissions']['candidate-1']['proof_path']]
        for path in paths:
            raw = path.read_bytes(); path.write_bytes(b'{"tampered":true}')
            with self.subTest(path=path.name), self.assertRaises(transition.TransitionError):
                transition.validate_transition(self.root, state)
            path.write_bytes(raw)

    def test_canonical_json_types_survive_valid_resealed_epoch_and_history(self):
        state = self.active()
        for field in ('number', 'generation', 'execution'):
            for replacement in (True, 1.0):
                current = deepcopy(state)
                # Keep archived originals unchanged and retain a valid epoch
                # digest: this must fail on paid-prefix JSON identity itself.
                current['capability_selection']['calls'][0][field] = replacement
                envelope = current['b_route_execution_transition']
                envelope['transition_digest'] = codec.canonical_digest({k: v for k, v in envelope.items() if k != 'transition_digest'})
                self.assertEqual(state['b_route_execution_transition']['transition_digest'], envelope['transition_digest'])
                with self.subTest(field=field, replacement=repr(replacement)), self.assertRaises(transition.TransitionError):
                    transition.validate_transition(self.root, current)
                # A separately resealed archived image cannot change the
                # original integer into a boolean/float at the entry gate.
                current = deepcopy(state)
                envelope = current['b_route_execution_transition']
                previous = transition._previous_state(envelope)
                previous['capability_selection']['calls'][0][field] = replacement
                raw = self.raw(previous)
                envelope['previous_run'] = {'raw_digest': codec.raw_digest(raw),
                    'bytes_base64': base64.b64encode(raw).decode('ascii')}
                envelope['transition_digest'] = codec.canonical_digest({k: v for k, v in envelope.items() if k != 'transition_digest'})
                current['capability_selection']['calls'][0][field] = replacement
                with self.subTest(archive_field=field, replacement=repr(replacement)), self.assertRaises(transition.TransitionError):
                    transition.validate_transition(self.root, current)
        for key, replacement in (('mvg.run_invocation_limit', 192.0), ('recovery', {**state['recovery'], 'epoch': 4.0}),
                ('b_route_campaign_funding', {**state['b_route_campaign_funding'], 'fixture_paid_or_unknown': 73.0})):
            current = deepcopy(state); current[key] = replacement
            with self.subTest(identity=key), self.assertRaises(transition.TransitionError):
                transition.validate_transition(self.root, current)
        current = deepcopy(state)
        current['b_route_execution_history'][self.prior['transition_digest']]['original_tracked_sources']['original.py']['fixture'] = 1
        with self.assertRaises(transition.TransitionError):
            transition.validate_transition(self.root, current)

    def test_parent_source_history_archive_and_cycles_fail_closed(self):
        state = self.active()
        for key, replacement in (('current_commit', '8' * 40), ('current_source_root', str(self.original_root))):
            value = deepcopy(state)
            value['b_route_execution_transition'][key] = replacement
            with self.subTest(key=key), self.assertRaises(transition.TransitionError):
                transition.validate_transition(self.root, value)
        value = deepcopy(state); value['b_route_execution_history'].clear()
        with self.assertRaises(transition.TransitionError):
            transition.validate_transition(self.root, value)
        value = deepcopy(state); value['b_route_execution_transition']['previous_run']['raw_digest'] = codec.raw_digest(b'wrong')
        body = value['b_route_execution_transition']; body['transition_digest'] = codec.canonical_digest({k: v for k, v in body.items() if k != 'transition_digest'})
        with self.assertRaises(transition.TransitionError):
            transition.validate_transition(self.root, value)
        value = deepcopy(state); value['b_route_execution_transition']['prior_transition'] = value['b_route_execution_transition']
        with self.assertRaises((transition.TransitionError, RecursionError, codec.CodecError)):
            transition.validate_transition(self.root, value)

    def test_old_cap_six_eight_gate_is_not_the_mvg_seven_gate(self):
        with self.assertRaises(transition.TransitionError):
            transition._closed_paid_prefix(self.state)
        for count, schema in ((6, transition.SCHEMA), (8, transition.EPOCH_V2_SCHEMA)):
            cap = {'b_route_execution_transition': {'schema_version': schema}, 'active_elapsed_seconds': 100,
                'capability_selection': {'total_invocations': count, 'calls': [
                    {'number': number, 'reservation_id': 'c4:dispatch:' + str(number),
                     'outcome': {'status': 'failed' if number == 6 else 'completed'}} for number in range(1, count + 1)]}}
            self.assertEqual(count, len(transition._closed_paid_prefix(cap)))
            with self.assertRaises(transition.TransitionError):
                transition._closed_mvg_paid_prefix(cap)

    def test_mvg_entry_cannot_reuse_wrong_prior_or_cap_builder_and_live_run_must_match(self):
        with self.assertRaises(transition.TransitionError):
            transition.build_successor_transition(self.root, self.state, self.original_root, self.new_commit,
                self.old_root, transition.MVG_PRIOR_COMMIT)
        with self.assertRaises(transition.TransitionError):
            transition.build_mvg_synthesis_transition(self.root, self.state, self.original_root, self.new_commit,
                self.old_root, '8' * 40)
        self.put(self.run / 'run.json', {'caller_changed_live_run': True})
        with self.assertRaises(transition.TransitionError):
            self.active()


if __name__ == '__main__':
    unittest.main(verbosity=2)
