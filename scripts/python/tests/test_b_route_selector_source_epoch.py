"""Selector source/runtime boundaries with an explicit synthetic Root anchor.

The original source/native collector and unavailable actual Root anchor provider
are fixture boundaries only. Epoch/history/raw pins and the new capture closer
execute their real production bodies. No fixture claims native acceptance.
"""
from contextlib import ExitStack
from copy import deepcopy
import base64
import json
from pathlib import Path
import sys
import unittest
import uuid
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _b_route_codec as codec
import _b_route_execution_transition as transition
import _b_route_planning_runtime as runtime
import _b_route_selector_recovery as recovery
import _b_route_mvg_synthesis_recovery as m1
import _b_route_compact_literal as compact
import _b_route_planning_wire as wire
import _mvg_capability_selection as selection
import test_b_route_mvg_source_epoch as fixture


class SelectorSourceEpochTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.outer_name = 'se22-' + uuid.uuid4().hex[:10]
        self.outer = fixture.BASE.resolve(strict=True) / self.outer_name
        self.outer.mkdir()
        self.fx = fixture.MvgSourceEpochTests(
            'test_distinct_mvg_epoch_preserves_exact_seven_paid_raw_and_clock_without_writes')
        with patch.object(fixture, 'BASE', self.outer):
            self.fx.setUp()
        # Forward failure retention to the outer test rather than deleting a
        # failed child fixture whose TestCase was not itself run.
        self.fx._cleanups = [entry for entry in self.fx._cleanups if entry[0].__name__ != 'cleanup_fixture']
        self.addCleanup(self.cleanup_fixture)
        self.root, self.run = self.fx.root, self.fx.run
        self.r19, self.r22 = self.fx.new_root, self.root / 'r22'
        self.r22.mkdir()
        self.commit = '2' * 40
        self.fx.new_commit = transition.SELECTOR_PRIOR_COMMIT
        frozen = {'schema_version': 'newrouge.b-route-planning-input.v1',
            'inputs': {'contexts': [], 'contract': {'scope': {'scope_id': 'whole-source'}}, 'closure': {},
                       'dependencies': {'files': {}, 'globs': []}}, 'transport': {'batches': [{'ordinal': 1}]}}
        frozen['input_identity'] = codec.canonical_digest(frozen['inputs'])
        self.fx.frozen = frozen
        self.fx.prepared_raw = self.fx.raw(frozen)
        self.fx.put(self.root / self.fx.prepared_ref, frozen)
        self.fx.put(self.run / 'analysis-input/b-route-prepared.json', frozen)
        descriptor = self.fx.descriptor
        descriptor.update(schema_version=runtime.PROFILE, frozen_sha256=codec.canonical_digest(frozen),
            input_identity=frozen['input_identity'], limits={'request_limit': 192}, wire_delivery=wire.CURRENT_SCHEMA)
        identity = codec.canonical_digest(descriptor)
        self.fx.base.update(original_runtime_identity=identity, frozen_sha256=codec.canonical_digest(frozen),
                            prepared_raw_digest=codec.raw_digest(self.fx.prepared_raw))
        self.fx.prior = self.fx.envelope(self.fx.old_root, transition.MVG_PRIOR_COMMIT)
        self.fx.state.update(planning_runtime=deepcopy(descriptor), runtime_identity=identity,
            analysis_identity_sha256=frozen['input_identity'], b_route_execution_transition=self.fx.prior)
        self.fx.proof['execution_source_transition'] = deepcopy(self.fx.prior)
        self.fx.put(self.run / self.fx.state['capability_selection']['current']['admissions']['candidate-1']['proof_path'], self.fx.proof)
        self.fx.put(self.run / 'run.json', self.fx.state)
        original = self.fx.active()
        original.update(phase='selection-blocked', selection_status='blocked')
        original['b_route_mvg_synthesis_recovery'] = {'schema_version': m1.SCHEMA,
            'record_ref': recovery.RUN_REF + '/recovery/m1/record.json', 'record_digest': codec.raw_digest(b'fixture-m1'),
            'artifact_root': str(self.root)}
        patterns = (('candidate-2', 'generate', 3, True), ('candidate-2', 'semantic', 4, False),
                    ('candidate-3', 'generate', 1, False), ('candidate-3', 'generate', 2, True),
                    ('candidate-3', 'semantic', 3, False))
        for number, (slot, phase, attempt, synthesis) in enumerate(patterns, 8):
            relative = 'candidates/' + slot + '/scope-1/capability-append/m1/c' + str(attempt)
            binding = {'output_path': (self.run / relative / 'r.json').as_posix(), 'fixture_paid': number}
            request = {'execution_binding_path': relative + '/binding.json', 'output_path': relative + '/r.json',
                       'attempt': attempt, 'synthesis': synthesis}
            original['capability_selection']['calls'].append({'number': number, 'reservation_id': 'm4:dispatch:' + str(number),
                'candidate': slot, 'phase': phase, 'generation': 1, 'execution': 1, 'request_identity': request,
                'outcome': {'status': 'completed', 'active_elapsed_seconds': 1.0}})
            self.fx.put(self.run / request['execution_binding_path'], binding)
        ledger, current = original['capability_selection'], original['capability_selection']['current']
        ledger.update(total_invocations=12, lineage_invocations={'candidate-1': 5, 'candidate-2': 4, 'candidate-3': 3})
        current.update(stage='selection-preparing', aliases={'A': 'candidate-2', 'B': 'candidate-3', 'C': 'candidate-1'})
        for slot, count in (('candidate-1', 5), ('candidate-2', 4), ('candidate-3', 3)):
            admission = current['admissions'].setdefault(slot, {})
            admission.update(candidate=slot, status='admitted', total_invocations=count, retryable=False,
                append_terminal=False, lineage=slot + '-r1', generation=1, execution=1,
                workspace='candidates/' + slot + '/scope-1')
            if slot != 'candidate-1':
                for kind, suffix in (('proposal', 'proposal.json'), ('proof', 'admission-review.json'), ('execution', 'admission-execution.json')):
                    value = {'fixture': kind + '-' + slot}
                    if kind == 'proof':
                        value['execution_source_transition'] = deepcopy(original['b_route_execution_transition'])
                    path = 'candidates/' + slot + '/scope-1/' + suffix
                    self.fx.put(self.run / path, value)
                    admission[kind + '_path'] = path
            for kind in ('proposal', 'proof', 'execution'):
                admission[kind + '_sha256'] = codec.raw_digest((self.run / admission[kind + '_path']).read_bytes())
        self.scopes = runtime.scopes(original, self.run / 'analysis-input')
        self.seed = runtime.seed(original, self.run / 'analysis-input')
        current.update(capability_id=self.scopes[0]['capability_id'], base_sha256=codec.canonical_digest(self.seed))
        current['input_identity'] = selection.selection_identity(original, self.scopes[0], 0, self.seed,
            current['admissions'], current['aliases'])
        current['input_sha256'] = codec.canonical_digest(current['input_identity'])
        original['active_elapsed_seconds'] += 300
        self.fx.put(self.run / 'run.json', original)
        self.fx.put(self.run / 'model-execution.json', {'fixture': 'retained projection'})
        self.fx.put(self.run / 'recovery/m1/record.json', {'fixture': 'old immutable m1 record'})
        (self.run / 'capability-selection').mkdir(exist_ok=True)
        self.original = deepcopy(original)
        self.original_raw = (self.run / 'run.json').read_bytes()
        files = {p.relative_to(self.root).as_posix(): codec.raw_digest(p.read_bytes())
                 for p in self.run.rglob('*') if p.is_file()}
        directories = [p.relative_to(self.root).as_posix() for p in (self.run, *self.run.rglob('*')) if p.is_dir()]
        marker = self.r19 / 'fixture_source.py'; marker.write_bytes(b'original checked source fixture\n')
        bridge = self.outer / 'continue_story25_mvg_synthesis_recovery_v17.py'
        bridge.write_bytes(b'offline synthetic original verifier bridge\n')
        admissions = {}
        for slot, admission in current['admissions'].items():
            admissions[slot] = {'admission': deepcopy(admission), 'canonical_digests': {
                kind: codec.canonical_digest(codec.strict_json_loads((self.run / admission[kind + '_path']).read_bytes()))
                for kind in ('proposal', 'proof', 'execution')}}
        self.anchor = {'schema_version': recovery.CAPTURE_SCHEMA, 'utc': 'fixture-only', 'artifact_root': str(self.root),
            'source': {'root': str(self.r19), 'commit': transition.SELECTOR_PRIOR_COMMIT,
                'verifier_bridge_sha256': codec.raw_digest(bridge.read_bytes()), 'source_hashes': {'sources': {
                str(self.r19): {'manifest': {'fixture_source.py': {'raw_digest': codec.raw_digest(marker.read_bytes())}}}}}},
            'run_ref': recovery.RUN_REF, 'original_run_raw_digest': codec.raw_digest(self.original_raw),
            'original_state': deepcopy(original), 'manifest': {'files': files, 'directories': directories},
            'runtime_binding': deepcopy(descriptor), 'selection': {'scopes': self.scopes, 'accepted_seed': self.seed,
                'records': [], 'aliases': current['aliases'], 'input_identity': current['input_identity'], 'input_sha256': current['input_sha256']},
            'admissions': admissions, 'budget': deepcopy(original['b_route_campaign_funding']), 'terminal_controls': {},
            'helper_sha256': recovery.HELPER_DIGEST, 'original_m1_ref': original['b_route_mvg_synthesis_recovery'],
            'scope': self.scopes[0], 'actual_model_dispatches': 0}
        # This is the only simulated anchor-authority boundary. Core capture
        # type, projection, file/membership/source closers are not patched.
        self.stack.enter_context(patch.object(recovery, '_trusted_anchor', side_effect=lambda root: deepcopy(self.anchor)))
        self.stack.enter_context(patch.object(recovery, 'ORIGINAL_RUN_DIGEST', codec.raw_digest(self.original_raw)))
        self.stack.enter_context(patch.object(recovery, 'ANCHOR_DIGEST', codec.canonical_digest(self.anchor)))
        self.stack.enter_context(patch.object(recovery, 'CAPTURE_EXIT_DIGEST', codec.raw_digest(b'synthetic held OS0 boundary')))
        self.stack.enter_context(patch.object(transition, '_collect', side_effect=self.collect))
        self.stack.enter_context(patch.object(transition, '_SOURCE_ROOT', self.r22))
        self.capture = recovery.capture_retained_selector(self.root)

    def cleanup_fixture(self):
        self.stack.close()
        self.fx.doCleanups()
        result = getattr(getattr(self, '_outcome', None), 'result', None)
        if any(case is self for case, _ in getattr(result, 'errors', []) + getattr(result, 'failures', [])):
            print('Retained failed selector source fixture: ' + str(self.root))
            return
        import shutil
        target = self.root.resolve(strict=True)
        if target.parent != self.outer.resolve(strict=True) or target.name != self.fx.fixture_name:
            raise AssertionError('Fixture escaped original owned TEMP parent/name')
        shutil.rmtree(target)
        outer = self.outer.resolve(strict=True)
        if outer.parent != fixture.BASE.resolve(strict=True) or outer.name != self.outer_name:
            raise AssertionError('Outer fixture escaped owned TEMP parent/name')
        shutil.rmtree(outer)

    def collect(self, root, state, original_root, current_commit, *, current_root=None):
        source = Path(current_root) if current_root is not None else self.r22
        expected = {self.fx.old_root: transition.MVG_PRIOR_COMMIT, self.r19: transition.SELECTOR_PRIOR_COMMIT, self.r22: self.commit}
        if source not in expected or current_commit != expected[source]:
            raise transition.TransitionError('explicit fixture source mismatch')
        if (self.root / self.fx.prepared_ref).read_bytes() != self.fx.prepared_raw:
            raise transition.TransitionError('fixture original prepared bytes changed')
        value = self.fx.envelope(source, current_commit); value.pop('transition_digest')
        return value, deepcopy(self.fx.frozen)

    def active(self):
        epoch = transition.build_mvg_selector_transition(self.root, self.original, self.fx.original_root,
            self.commit, self.r19, transition.SELECTOR_PRIOR_COMMIT, retained_capture=self.capture)
        state = deepcopy(self.original)
        state['b_route_execution_transition'] = epoch
        state['b_route_execution_history'] = {**state['b_route_execution_history'],
            self.original['b_route_execution_transition']['transition_digest']: self.original['b_route_execution_transition']}
        state[recovery.REFERENCE] = {'schema_version': recovery.SCHEMA, 'record_ref': recovery.RUN_REF + '/recovery/s1/record.json',
                                  'record_digest': codec.raw_digest(b'fixture typed reference; not dispatch authority'), 'artifact_root': str(self.root)}
        return state

    def test_selector_epoch_preserves_real_r19_frame_m1_and_r10_history_without_writes(self):
        state = self.active()
        self.assertEqual(self.original_raw, (self.run / 'run.json').read_bytes())
        self.assertEqual(transition.SELECTOR_EPOCH_SCHEMA, state['b_route_execution_transition']['schema_version'])
        transition.validate_transition(self.root, state)
        previous = transition.historical_state(self.root, state, self.original['b_route_execution_transition']['transition_digest'])
        self.assertEqual(self.original, previous)
        self.assertEqual(self.original['b_route_mvg_synthesis_recovery'], previous['b_route_mvg_synthesis_recovery'])
        r10 = transition.historical_state(self.root, state, self.fx.prior['transition_digest'])
        self.assertNotIn('b_route_mvg_synthesis_recovery', r10)
        self.assertEqual(self.fx.prior, r10['b_route_execution_transition'])

    def test_missing_reference_is_not_a_fallback_to_m1(self):
        for value in (None, {}):
            state = self.active(); state[recovery.REFERENCE] = value
            with self.subTest(value=value), patch.object(m1, 'validate_recovery', side_effect=AssertionError('No m1 fallback')):
                with self.assertRaises(ValueError):
                    runtime.selector_recovery_active(state)
                with self.assertRaises(ValueError):
                    transition.validate_transition(self.root, state)
                with self.assertRaises(ValueError):
                    runtime.generation_call_root(state, self.run, 1, 'candidate-1')

    def test_new_frozen_input_routes_to_selector_owner_not_m1(self):
        state = self.active()
        class SelectedOwnerReached(ValueError):
            pass
        # Dependency marker establishes dispatch routing, not a fake success
        # from a patched verifier. All source/capture closing before it is real.
        with (patch.object(recovery, 'validate_recovery', side_effect=SelectedOwnerReached('selector owner reached')),
                patch.object(m1, 'validate_recovery', side_effect=AssertionError('Wrong original frame'))):
            with self.assertRaises(SelectedOwnerReached):
                runtime.frozen_input(self.root, state)

    def test_source_history_anchor_raw_and_admission_drift_fail_closed(self):
        state = self.active()
        variants = []
        value = deepcopy(state); value['b_route_execution_history'].pop(self.fx.prior['transition_digest']); variants.append(value)
        value = deepcopy(state); value['b_route_execution_transition']['selector_anchor_identity']['anchor_raw_digest'] = codec.raw_digest(b'caller'); variants.append(value)
        value = deepcopy(state); value['capability_selection']['current']['admissions']['candidate-3']['proposal_sha256'] = codec.raw_digest(b'changed'); variants.append(value)
        for index, value in enumerate(variants):
            epoch = value['b_route_execution_transition']
            epoch['transition_digest'] = codec.canonical_digest({k: v for k, v in epoch.items() if k != 'transition_digest'})
            with self.subTest(index=index), self.assertRaises(ValueError):
                transition.validate_transition(self.root, value)
        path = self.r19 / 'fixture_source.py'; path.write_bytes(b'changed original source')
        with self.assertRaises(ValueError):
            transition.validate_transition(self.root, state)

    def test_exact_twelve_budget_unknown_and_json_type_changes_are_rejected(self):
        state = self.active()
        variants = []
        value = deepcopy(state); value['capability_selection']['calls'][11]['outcome']['status'] = 'unknown'; variants.append(value)
        value = deepcopy(state); value['capability_selection']['calls'][0]['generation'] = True; variants.append(value)
        value = deepcopy(state); value['capability_selection']['calls'][0]['execution'] = 1.0; variants.append(value)
        value = deepcopy(state); value['mvg.run_invocation_limit'] = 193; variants.append(value)
        value = deepcopy(state); value['b_route_campaign_funding']['released'] = 1; variants.append(value)
        value = deepcopy(state); value['active_elapsed_seconds'] -= 1; variants.append(value)
        value = deepcopy(state); value['b_route_mvg_synthesis_recovery'] = {}; variants.append(value)
        for index, value in enumerate(variants):
            with self.subTest(index=index), self.assertRaises(ValueError):
                transition.validate_transition(self.root, value)

    def test_only_one_selection_reservation_can_extend_prefix_not_generation(self):
        state = self.active()
        row = {'number': 13, 'reservation_id': 'm4:dispatch:13', 'phase': 'selection', 'candidate': None,
            'generation': 1, 'execution': 1, 'request_identity': {'attempt': 1,
                'selector_transport_policy': compact.ATOM_SCHEMA,
                'selection_input_sha256': self.original['capability_selection']['current']['input_sha256']}}
        state['capability_selection']['calls'].append(row)
        state['capability_selection']['total_invocations'] = 13
        transition.validate_transition(self.root, state)
        for phase, candidate in (('generate', 'candidate-2'), ('selection', 'candidate-1')):
            value = deepcopy(state); value['capability_selection']['calls'][12].update(phase=phase, candidate=candidate)
            with self.subTest(phase=phase), self.assertRaises(ValueError):
                transition.validate_transition(self.root, value)
        state['capability_selection']['calls'].append({**row, 'number': 14, 'reservation_id': 'm4:dispatch:14'})
        state['capability_selection']['total_invocations'] = 14
        with self.assertRaises(ValueError):
            transition.validate_transition(self.root, state)

    def test_selector_v3_does_not_change_old_global_v2_or_allow_generation(self):
        state = self.active()
        self.assertEqual(compact.CURRENT_SCHEMA, state['b_route_input_compact_policy'])
        old = {'phase': 'generation', 'wire_delivery': wire.CURRENT_SCHEMA, 'input_compact_policy': compact.CURRENT_SCHEMA}
        self.assertEqual(compact.CURRENT_SCHEMA, runtime.input_compact_policy(old))
        current = {'phase': 'selection', 'wire_delivery': wire.CURRENT_SCHEMA,
                   'input_compact_policy': compact.ATOM_SCHEMA, 'selector_transport_policy': compact.ATOM_SCHEMA}
        self.assertEqual(compact.ATOM_SCHEMA, runtime.input_compact_policy(current))
        for phase in ('generation', 'independent_admission'):
            with self.subTest(phase=phase), self.assertRaises(ValueError):
                runtime.input_compact_policy({**current, 'phase': phase})
        with self.assertRaises(ValueError):
            runtime.generation_call_root(state, self.run, 3, 'candidate-2')
        with self.assertRaises(ValueError):
            runtime.generate_append(self.root, state, self.run, invoke_factory=None, before_call=None, checkpoint=None)

    def test_caller_dictionary_is_not_a_capture_or_source_transition_authority(self):
        with self.assertRaises(ValueError):
            transition.build_mvg_selector_transition(self.root, self.original, self.fx.original_root,
                self.commit, self.r19, transition.SELECTOR_PRIOR_COMMIT,
                retained_capture={'anchor_identity': self.capture['anchor_identity']})
        with self.assertRaises(ValueError):
            recovery.verify_retained_selector_capture(self.root, {'approved': True}, current_state=self.original)


if __name__ == '__main__':
    unittest.main(verbosity=2)
