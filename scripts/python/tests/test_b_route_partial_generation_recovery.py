"""Synthetic repair-continuation guards; not actual model or native acceptance."""
from copy import deepcopy
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_partial_generation_recovery as recovery
import _mvg_capability_append as append_owner


def raw(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def fixture():
    issue = {'code': 'b_route_machine:fixture', 'path': 'candidate:observations-to-audit',
             'detail': {'entity_id': 'observations-to-audit', 'expected': 'handoff corresponds to declared graph edge'}}
    prior = {'content': 'original invalid complete synthesis7'}
    delta = {'candidate': prior, 'generation_calls': [{'old': 5}, {'old': 7}], 'lineage': {'context': 1}}
    durations = [186.297, 429.969, 159.265, 84.093, 251.25, 408.219, 409.625, 405.625]
    phases = ['generate', 'generate', 'semantic', 'semantic', 'generate', 'generate', 'generate', 'repair']
    calls = [{'number': i, 'candidate': 'candidate-1' if i <= 4 else 'candidate-2',
              'generation': 1, 'execution': 1, 'phase': phases[i - 1], 'reservation_id': 'c4:dispatch:' + str(i),
              'request_identity': {'attempt': i if i <= 4 else i - 4,
                                   'synthesis': i in (2, 6, 7)},
              'outcome': {'status': 'failed' if i == 6 else 'completed', 'active_elapsed_seconds': durations[i - 1]}}
             for i in range(1, 9)]
    state = {'run_id': 'c4', 'runtime_identity': 'original-runtime', 'active_elapsed_seconds': 4882.767,
             'planning_runtime': {'limits': {'request_limit': 96, 'candidate_budget_sec': 2700,
                                 'synthesis_budget_sec': 1200, 'total_budget_sec': 13500}},
             'mvg.run_invocation_limit': 96, 'selection_status': 'blocked',
             'selection_block_reason': 'selection_blocked_insufficient_admitted_candidates',
             'b_route_execution_transition': {'transition_digest': 'r8', 'current_commit': recovery.PRIOR_COMMIT},
             'b_route_execution_history': {'r7': {'transition_digest': 'r7'}},
             'b_route_review_recovery': {'original': 'review'}, 'b_route_synthesis_recovery': {'original': 'synthesis'},
             'b_route_campaign_funding': {'schema_version': 'newrouge.story25-native-funding.v1',
                 'paid_or_unknown_before_run': 55, 'campaign_limit': 290, 'subsequent_full_reservation': 192,
                 'maximum_native_charges': 43, 'released': 0},
             'capability_selection': {'calls': calls, 'total_invocations': 8,
                 'lineage_invocations': {'candidate-1': 4, 'candidate-2': 4}, 'terminal': True, 'selected': [],
                 'current': {'order_index': 0, 'execution': 1, 'selection_attempts': [],
                     'admissions': {'candidate-1': {'status': 'admitted'}, 'candidate-2': {'status': 'blocked'}}}}}
    scopes, seed, identity = [{'capability_id': 'scope'}], {}, 'original-runtime'
    local = {'binding': recovery.canonical_sha({'identity': identity, 'scopes': scopes, 'seed': seed}),
             'status': 'blocked', 'total_invocations': 4, 'completed': [], 'records': [], 'accepted': {},
             'order': ['scope'], 'restarts': [],
             'calls': [{'number': i, 'phase': 'repair' if i == 4 else 'generate', 'context': 1,
                        'capability_id': 'scope', 'reservation_id': 'c4:dispatch:' + str(i + 4)} for i in range(1, 5)],
             'current': {'capability_id': 'scope', 'context': 1, 'issue': issue,
                         'issue_attempts': {append_owner.issue_key(issue): 1}, 'proposal': prior, 'delta': delta, 'issues': [issue]},
             'errors': [{'code': 'append_input_preparation_failed',
                         'detail': 'runner_context_budget_exceeded:estimated_input_tokens=94657;continuation_reserve=2000;limit=96000'}]}
    return state, local, scopes, seed, identity


class PartialRepairTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get('PARTIAL_REPAIR_TEST_TEMP'))
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.run_ref = 'logs/ci/capability-planning/c4'
        self.run = self.root / self.run_ref
        self.workspace = self.run / recovery.WORKSPACE
        self.home = self.run / 'recovery/input-budget-recovery-1'
        self.old, self.append, self.scopes, self.seed, self.identity = fixture()
        self.binding_ref = recovery.WORKSPACE + '/capability-append/c4/execution-binding-4-r.json'
        self.draft_ref = recovery.WORKSPACE + '/capability-append/c4/canonical-draft.json'
        self.binding, self.draft = {'original': 'binding8'}, {'stage': 'batch', 'ordinal': 1, 'content': {'original': 'repair batch8'}}
        self.write(self.run / self.binding_ref, self.binding)
        self.write(self.run / self.draft_ref, self.draft)
        self.failed = self.workspace / 'capability-append/c5'
        self.write(self.failed / 'output-schema.json', {'original': 'unreserved schema'})
        self.write(self.failed / 'llm-sandbox/attempt-5/r/runner-input-integrity.json', {'status': 'capacity blocked'})
        self.write(self.failed / 'llm-sandbox/attempt-5/r/prompt-5-r.txt', {'full': 'old rejected request'})
        self.protected = self.run / 'original-eight-proof.json'
        self.write(self.protected, {'unchanged': True})
        self.record = {'schema_version': recovery.SCHEMA, 'run_id': 'c4', 'run_ref': self.run_ref,
                       'previous_run': recovery.image(raw(self.old)), 'previous_append': recovery.image(raw(self.append)),
                       'immutable_files': {path.relative_to(self.run).as_posix(): recovery.codec.raw_digest(path.read_bytes())
                                           for path in (self.protected, self.run / self.binding_ref, self.run / self.draft_ref)},
                       'failed_preparation': recovery._files(self.failed),
                       'transition': {'transition_digest': 'r9'}, 'history': {**self.old['b_route_execution_history'], 'r8': self.old['b_route_execution_transition']},
                       'output_schema_policy': 'r9-policy', 'input_compact_policy': recovery.compact.CURRENT_SCHEMA,
                       'original_current': deepcopy(self.append['current']),
                       'original_local_calls': deepcopy(self.append['calls']), 'completed_binding_ref': self.binding_ref,
                       'completed_draft_ref': self.draft_ref, 'completed_binding_digest': recovery.canonical_sha(self.binding),
                       'completed_draft_digest': recovery.canonical_sha(self.draft), 'retained_slots': 8, 'released': 0,
                       'maximum_prefix_resumes': 1, 'candidate_model_used': recovery.model_used(self.old),
                       'candidate_model_remaining': 3900 - recovery.model_used(self.old), 'global_active_elapsed_seconds': self.old['active_elapsed_seconds']}
        self.state = deepcopy(self.old)
        self.state.update(b_route_execution_transition=self.record['transition'], b_route_execution_history=self.record['history'],
                          b_route_output_schema_policy='r9-policy', b_route_input_compact_policy=recovery.compact.CURRENT_SCHEMA,
                          runtime_slot='candidate-2', runtime_execution=1)
        self.home.mkdir(parents=True)
        self.persist_record()
        self.local_path = self.workspace / 'capability-append/append-ledger.json'
        self.local = deepcopy(self.append)
        self.local.update(status='generating', errors=[])
        self.write(self.local_path, self.local)
        self.write(self.run / 'run.json', self.state)
        self.previous = SimpleNamespace(validate_recovery=Mock(return_value={'old_epoch': 'verified boundary'}))
        self.runtime = SimpleNamespace(verify_reserved_call=Mock(return_value=self.binding), verify_call=Mock(return_value={'carrier': 8}),
            decode_generation_carrier=Mock(return_value=self.draft), same_json=recovery.same,
            bound_materials=Mock(return_value={'phase': 'generation', 'slot': 'candidate-2', 'generation': 1, 'execution': 1,
                'lineage_context': 1, 'root_request': {'batch': 1}, 'accepted_seed': self.seed,
                'prior_candidate': self.append['current']['proposal'], 'repair_issue': self.append['current']['issue'],
                'lineage_identity': 'original-lineage'}), request_attempt=Mock(return_value={'payload': '{"batch":1}'}),
            wire_delivery=Mock(return_value='fixture'), lineage_identity=Mock(return_value='original-lineage'),
            planning=SimpleNamespace(validate_draft_chain=Mock(return_value=['draft8'])))

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw(value))

    def persist_record(self):
        self.write(self.home / 'record.json', self.record)
        digest = recovery.codec.raw_digest((self.home / 'record.json').read_bytes())
        self.state[recovery.REFERENCE] = {'schema_version': recovery.SCHEMA,
            'record_ref': (self.home / 'record.json').relative_to(self.root).as_posix(), 'record_digest': digest, 'artifact_root': str(self.root)}
        self.write(self.home / 'claim.json', {'schema_version': recovery.SCHEMA, 'record_digest': digest, 'retained_slots': 8})
        self.write(self.home / 'committed.json', {'record_digest': digest, 'transition_digest': 'r9'})

    @contextmanager
    def boundary(self):
        with patch.dict(sys.modules, {'_b_route_synthesis_recovery': self.previous, '_b_route_planning_runtime': self.runtime}):
            yield

    def snapshot(self):
        return {path.relative_to(self.root).as_posix(): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}

    def test_exact_old8_and_model_clocks_are_retained(self):
        recovery.retained_shape(self.old, self.append)
        with self.boundary():
            self.assertEqual(self.record, recovery.validate_recovery(self.root, self.state))
        self.previous.validate_recovery.assert_called_once_with(self.root, self.old)
        self.assertAlmostEqual(1474.719, self.record['candidate_model_used'])
        self.assertAlmostEqual(2425.281, self.record['candidate_model_remaining'])
        self.assertEqual(1, self.append['current']['issue_attempts'][append_owner.issue_key(self.append['current']['issue'])])

    def test_unknown_changed_outcome_issue_attempt_or_refund_fails_closed(self):
        for case in ('unknown8', 'failed8', 'calls7', 'issue-count-reset', 'changed-issue', 'refund', 'clock-refund'):
            with self.subTest(case=case):
                state, local, *_ = fixture()
                if case == 'unknown8': state['capability_selection']['calls'][7]['outcome']['status'] = 'unknown'
                elif case == 'failed8': state['capability_selection']['calls'][7]['outcome']['status'] = 'failed'
                elif case == 'calls7': state['capability_selection']['total_invocations'] = 7
                elif case == 'issue-count-reset': local['current']['issue_attempts'] = {}
                elif case == 'changed-issue': local['current']['issue']['path'] = 'different'
                elif case == 'refund': state['b_route_campaign_funding']['released'] = 1
                else: state['active_elapsed_seconds'] = 0
                with self.assertRaises(ValueError): recovery.retained_shape(state, local)

    def test_partial_transaction_old_c5_membership_and_source_frame_tamper(self):
        marker = self.home / 'committed.json'
        marker_raw = marker.read_bytes()
        marker.unlink()
        with self.boundary(), self.assertRaises((OSError, ValueError)): recovery.validate_recovery(self.root, self.state)
        self.assertFalse(marker.exists())
        marker.write_bytes(marker_raw)
        self.write(self.failed / 'extra-old-preparation.json', {'must': 'not add to old c5'})
        with self.boundary(), self.assertRaisesRegex(ValueError, 'failed_c5_preparation_changed'):
            recovery.validate_recovery(self.root, self.state)
        (self.failed / 'extra-old-preparation.json').unlink()
        state = deepcopy(self.state)
        state['b_route_execution_transition'] = {'transition_digest': 'different'}
        with self.boundary(), self.assertRaisesRegex(ValueError, 'source_frame_changed'):
            recovery.validate_recovery(self.root, state)

    def test_once_claim_preserves_actual_batch8_and_refuses_second_or_unknown_attempt(self):
        before_c5 = recovery._files(self.failed)
        with self.boundary():
            self.assertTrue(recovery.resume_propose_attempt(self.root, self.state, self.workspace, self.local['current'], self.local))
            actual = recovery.resume_generation(self.root, self.state, self.workspace, {}, self.seed,
                self.append['current']['proposal'], self.append['current']['issue'], 1)
            self.assertEqual(([self.draft], [self.binding]), actual)
            self.runtime.verify_reserved_call.assert_called_once_with(self.run, self.state['capability_selection']['calls'][7])
            with self.assertRaises(FileExistsError):
                recovery.resume_propose_attempt(self.root, self.state, self.workspace, self.local['current'], self.local)
        self.assertEqual(before_c5, recovery._files(self.failed))
        self.assertEqual(8, self.state['capability_selection']['total_invocations'])
        self.assertEqual(4, self.local['total_invocations'])
        self.assertTrue((self.home / 'resume-claim.json').exists())

    def test_partial_claim_and_new_unknown_call_cannot_be_resumed(self):
        (self.home / 'resume-claim.json').write_bytes(b'{"partial":')
        with self.boundary(), self.assertRaises(ValueError):
            recovery.resume_generation(self.root, self.state, self.workspace, {}, self.seed,
                self.append['current']['proposal'], self.append['current']['issue'], 1)
        state = deepcopy(self.state)
        new = deepcopy(state['capability_selection']['calls'][7])
        new.update(number=9)
        new['outcome'] = {'status': 'unknown'}
        state['capability_selection']['calls'].append(new)
        state['capability_selection']['total_invocations'] = 9
        state['capability_selection']['lineage_invocations']['candidate-2'] = 5
        with self.boundary(), self.assertRaisesRegex(ValueError, 'owner_cannot_refund_private_snapshot'):
            recovery.resume_propose_attempt(self.root, state, self.workspace, self.local['current'], self.local)

    def test_new_call_root_keeps_old_unreserved_c5_and_old_sources_in_default_layout(self):
        expected = self.workspace / 'capability-append/input-budget-recovery-1/c5'
        self.assertEqual(expected, recovery.call_root(self.state, self.workspace, 5, 'candidate-2'))
        self.assertEqual(self.workspace / 'capability-append/c4', recovery.call_root(self.state, self.workspace, 4, 'candidate-2'))
        self.assertEqual(self.workspace / 'capability-append/c5', recovery.call_root(self.old, self.workspace, 5, 'candidate-2'))
        self.assertEqual(self.workspace / 'capability-append/c5', recovery.call_root(self.state, self.workspace, 5, 'candidate-1'))
        self.assertTrue(self.failed.exists())

    def test_typed_reference_and_boolean_repair_counter_are_rejected(self):
        for reference in ('untyped', {**self.state[recovery.REFERENCE], 'unknown_field': True}):
            state = deepcopy(self.state)
            state[recovery.REFERENCE] = reference
            with self.boundary(), self.assertRaisesRegex(ValueError, 'typed_reference'):
                recovery.validate_recovery(self.root, state)
        local = deepcopy(self.append)
        local['current']['issue_attempts'][append_owner.issue_key(local['current']['issue'])] = True
        with self.assertRaisesRegex(ValueError, 'original_business_issue_or_attempt_changed'):
            recovery.retained_shape(self.old, local)

    def test_immutable_archive_is_scoped_and_rejects_hardlinked_old_artifacts(self):
        relative = self.protected.relative_to(self.run).as_posix()
        mutable = {self.local_path.relative_to(self.run).as_posix()}
        manifest = recovery._immutable(self.run, mutable)
        self.assertEqual(recovery.codec.raw_digest(self.protected.read_bytes()), manifest[relative])
        self.assertNotIn(self.local_path.relative_to(self.run).as_posix(), manifest)
        alias = self.run / 'hardlink-alias.json'
        os.link(self.protected, alias)
        with self.assertRaisesRegex(ValueError, 'old_artifact_hardlink'):
            recovery._immutable(self.run, mutable)

    def test_wrong_partial_inputs_cannot_silently_restart_the_paid_batch(self):
        with self.boundary():
            recovery.resume_propose_attempt(self.root, self.state, self.workspace, self.local['current'], self.local)
            for prior, issue, context in (({'changed': 'proposal'}, self.append['current']['issue'], 1),
                                          (self.append['current']['proposal'], {'changed': 'issue'}, 1),
                                          (self.append['current']['proposal'], self.append['current']['issue'], 2)):
                with self.subTest(context=context, prior=prior), self.assertRaisesRegex(ValueError, 'unproven_changed_partial_inputs'):
                    recovery.resume_generation(self.root, self.state, self.workspace, {}, self.seed, prior, issue, context)
        self.runtime.verify_call.assert_not_called()

    def test_append_resume_hook_does_not_increment_already_paid_repair_attempt(self):
        observed = []
        def before_call(phase, **kwargs):
            number = self.state['capability_selection']['total_invocations'] + 1
            row = deepcopy(self.state['capability_selection']['calls'][7])
            row.update(number=number, phase=phase)
            self.state['capability_selection']['calls'].append(row)
            self.state['capability_selection']['total_invocations'] = number
            self.state['capability_selection']['lineage_invocations']['candidate-2'] += 1
            return {'reservation_id': 'c4:dispatch:' + str(number)}
        def propose(scope, accepted, prior, issue, context, call):
            current = json.loads(self.local_path.read_bytes())['current']
            observed.append(deepcopy(current['issue_attempts']))
            self.assertEqual(([self.draft], [self.binding]), recovery.resume_generation(
                self.root, self.state, self.workspace, {}, accepted, prior, issue, context))
            call('repair')
            return {'candidate': {'fixed': True}, 'generation_calls': [self.binding, {'new': 9}]}
        def semantic(scope, accepted, proposal, call, context):
            call('semantic')
            return {'issues': [], 'proof': {'synthetic': True}, 'execution': {'synthetic': True}}
        with self.boundary():
            result = append_owner.run_capability_append(self.local_path.parent, scopes=self.scopes, seed=self.seed,
                identity=self.identity, propose=propose, machine=lambda *_: [], semantic=semantic, final_machine=lambda *_: [],
                merge=lambda accepted, delta, scope: deepcopy(delta['candidate']), preserve=lambda *_: [], before_call=before_call,
                resume_propose_attempt=lambda current, ledger: recovery.resume_propose_attempt(
                    self.root, self.state, self.workspace, current, ledger))
        self.assertEqual('admitted', result['status'])
        self.assertEqual([self.append['current']['issue_attempts']], observed)
        self.assertEqual(self.append['calls'], result['calls'][:4])
        self.assertEqual(6, result['total_invocations'])
        self.assertEqual(10, self.state['capability_selection']['total_invocations'])

    def test_legacy_default_hook_still_increments_normal_repair_once(self):
        observed = []
        def propose(scope, accepted, prior, issue, context, call):
            observed.append(json.loads(self.local_path.read_bytes())['current']['issue_attempts'])
            call('repair')
            return {'candidate': {'fixed': True}}
        result = append_owner.run_capability_append(self.local_path.parent, scopes=self.scopes, seed=self.seed,
            identity=self.identity, propose=propose, machine=lambda *_: [],
            semantic=lambda *args: {'issues': [], 'proof': {}, 'execution': {}}, final_machine=lambda *_: [],
            merge=lambda accepted, delta, scope: deepcopy(delta['candidate']), preserve=lambda *_: [])
        self.assertEqual('admitted', result['status'])
        self.assertEqual([{append_owner.issue_key(self.append['current']['issue']): 2}], observed)

    def successor_fixture(self):
        """Synthetic native-shaped owner/output; mocked verifiers are not real AC."""
        frozen = {'input_identity': 'synthetic-frozen'}
        self.old['planning_runtime'].update(frozen_sha256=recovery.canonical_sha(frozen), input_identity=frozen['input_identity'])
        self.state['planning_runtime'] = deepcopy(self.old['planning_runtime'])
        self.record['previous_run'] = recovery.image(raw(self.old))
        self.persist_record()
        self.write(self.run / 'run.json', self.state)
        self.write(self.run / 'analysis-input/b-route-prepared.json', frozen)
        with self.boundary():
            self.assertTrue(recovery.resume_propose_attempt(self.root, self.state, self.workspace, self.local['current'], self.local))
        owner = deepcopy(self.state)
        row = deepcopy(owner['capability_selection']['calls'][7])
        row.update(number=9, reservation_id='c4:dispatch:9')
        row['request_identity'] = {'attempt': 5, 'synthesis': True}
        row['outcome'] = {'status': 'completed', 'active_elapsed_seconds': 10}
        owner['capability_selection']['calls'].append(row)
        owner['capability_selection']['total_invocations'] = 9
        owner['capability_selection']['lineage_invocations']['candidate-2'] = 5
        owner['active_elapsed_seconds'] += 10
        draft = {'stage': 'synthesis', 'content': {'synthetic': 'new completed synthesis9'}}
        drafts = [self.draft, draft]
        proposal = {'schema_version': 'synthetic-candidate', 'input_stage': '3b', 'input_identity': frozen['input_identity'],
            'provenance': {'kind': 'model_draft', 'declaration': 'Complete original model draft chain; execution separately replayed',
                'upstream_model_history': 'declared_model', 'draft_chain': drafts, 'final_draft_identity': recovery.canonical_sha(draft)},
            'content': deepcopy(draft['content'])}
        local = deepcopy(self.local)
        local['total_invocations'] = 5
        local['calls'].append({'number': 5, 'phase': 'repair', 'context': 1, 'capability_id': 'scope', 'reservation_id': 'c4:dispatch:9'})
        local['current'].update(proposal=proposal, delta={'candidate': proposal}, issue={'code': 'new-business-issue'})
        materials = {'phase': 'generation', 'slot': 'candidate-2', 'generation': 1, 'execution': 1, 'lineage_context': 1,
            'root_request': {'input': {'prior_drafts': [{'value': self.draft}]}}, 'accepted_seed': {},
            'prior_candidate': self.append['current']['proposal'], 'repair_issue': self.append['current']['issue'],
            'lineage_identity': 'original-lineage'}
        self.runtime.verify_reserved_call.return_value = {'synthetic': 'verified binding9'}
        self.runtime.bound_materials.return_value = materials
        self.runtime.decode_generation_output = Mock(return_value=draft)
        self.runtime.candidate = SimpleNamespace(SCHEMA='synthetic-candidate')
        self.runtime.preservation = Mock(return_value=[])
        self.runtime.machine = Mock(return_value=[])
        self.write(self.run / 'run.json', owner)
        self.write(self.local_path, local)
        return owner, local, materials

    def assert_normal_continuation(self, local):
        with self.boundary():
            self.assertFalse(recovery.resume_propose_attempt(self.root, self.state, self.workspace, local['current'], local))
            self.assertIsNone(recovery.resume_generation(self.root, self.state, self.workspace, {}, self.seed,
                local['current']['proposal'], local['current']['issue'], local['current']['context']))
        self.assertEqual(8, self.state['capability_selection']['total_invocations'])

    def test_stale_worker_uses_verified_completed_owner_synthesis_without_reusing_batch(self):
        owner, local, _ = self.successor_fixture()
        original_private = raw(self.state)
        self.assert_normal_continuation(local)
        self.assertEqual(original_private, raw(self.state))
        self.runtime.verify_reserved_call.assert_called_with(self.run, owner['capability_selection']['calls'][8])
        self.assertEqual(1, self.local['current']['issue_attempts'][append_owner.issue_key(self.local['current']['issue'])])

    def test_stale_owner_unknown_failed_none_and_wrong_binding_do_not_authorize_progress(self):
        owner, local, materials = self.successor_fixture()
        for status in ('unknown', 'failed', 'none', 'wrong-binding', 'wrong-output', 'changed-prefix', 'changed-clock'):
            with self.subTest(status=status):
                changed = deepcopy(owner)
                self.runtime.bound_materials.return_value = deepcopy(materials)
                self.runtime.decode_generation_output.return_value = {'stage': 'synthesis', 'content': {'synthetic': 'new completed synthesis9'}}
                if status in ('unknown', 'failed'): changed['capability_selection']['calls'][8]['outcome']['status'] = status
                elif status == 'none': changed = deepcopy(self.state)
                elif status == 'wrong-binding': self.runtime.bound_materials.return_value['lineage_identity'] = 'wrong'
                elif status == 'wrong-output': self.runtime.decode_generation_output.return_value['content'] = {'tampered': True}
                elif status == 'changed-prefix': changed['capability_selection']['calls'][0]['number'] = 0
                else: changed['active_elapsed_seconds'] = 0
                self.write(self.run / 'run.json', changed)
                with self.boundary(), self.assertRaises(ValueError):
                    recovery.resume_propose_attempt(self.root, self.state, self.workspace, local['current'], local)
        self.write(self.run / 'run.json', owner)
        (self.home / 'resume-claim.json').unlink()
        with self.boundary(), self.assertRaises((OSError, ValueError)):
            recovery.resume_propose_attempt(self.root, self.state, self.workspace, local['current'], local)

    def test_native_rejected_repair_fallback_requires_actual_new_issue_and_exact_rejection(self):
        owner, local, _ = self.successor_fixture()
        local['current'] = deepcopy(self.append['current'])
        local['rejected_repairs'] = [{'capability_id': 'scope', 'context': 1, 'invocations': 5, 'errors': ['repair_new_machine_issue']}]
        self.runtime.machine.side_effect = lambda root, state, proposal: ([] if proposal == self.append['current']['proposal']
            else [{'code': 'synthetic-new-machine', 'path': 'new'}])
        self.write(self.local_path, local)
        self.assert_normal_continuation(local)
        for case in ('wrong-attempt', 'wrong-context', 'no-rejection', 'no-new-issue', 'changed-delta'):
            changed = deepcopy(local)
            self.runtime.machine.side_effect = lambda root, state, proposal: ([] if proposal == self.append['current']['proposal']
                else [{'code': 'synthetic-new-machine', 'path': 'new'}])
            if case == 'wrong-attempt': changed['rejected_repairs'][0]['invocations'] = 4
            elif case == 'wrong-context': changed['rejected_repairs'][0]['context'] = 2
            elif case == 'no-rejection': changed['rejected_repairs'] = []
            elif case == 'no-new-issue': self.runtime.machine.side_effect = None; self.runtime.machine.return_value = []
            else: changed['current']['delta'] = {'changed': True}
            self.write(self.local_path, changed)
            with self.subTest(case=case), self.boundary(), self.assertRaisesRegex(ValueError, 'unproven_changed_repair'):
                recovery.resume_propose_attempt(self.root, self.state, self.workspace, changed['current'], changed)

    def test_native_context_replacement_needs_authoritative_reservation_and_three_repairs(self):
        owner, local, _ = self.successor_fixture()
        key = append_owner.issue_key(self.append['current']['issue'])
        event = {'candidate': 'candidate-2', 'context': 2, 'scope_id': 'scope', 'issue_id': key, 'round': 1, 'event_number': 1}
        owner['capability_selection'].update(replacement_events=[event], replacement_depths={'candidate-2': 1})
        local['replacement_reservations'] = [deepcopy(event)]
        local['restarts'] = [{'capability_id': 'scope', 'context': 1, 'issue_id': key, 'repair_attempts': 3}]
        local['current'] = {'capability_id': 'scope', 'context': 2, 'issue': None, 'proposal': None, 'delta': None, 'issue_attempts': {}}
        self.write(self.run / 'run.json', owner)
        self.write(self.local_path, local)
        self.assert_normal_continuation(local)
        for case in ('local-only', 'wrong-reservation', 'two-repairs', 'round4', 'changed-seed'):
            altered, changed = deepcopy(owner), deepcopy(local)
            if case == 'local-only': altered['capability_selection']['replacement_events'] = []
            elif case == 'wrong-reservation': changed['replacement_reservations'][0]['issue_id'] = 'wrong'
            elif case == 'two-repairs': changed['restarts'][0]['repair_attempts'] = 2
            elif case == 'round4': altered['capability_selection']['replacement_depths']['candidate-2'] = 4
            else: changed['accepted'] = {'changed': True}
            self.write(self.run / 'run.json', altered)
            self.write(self.local_path, changed)
            with self.subTest(case=case), self.boundary(), self.assertRaises(ValueError):
                recovery.resume_generation(self.root, self.state, self.workspace, {}, self.seed, None, None, 2)

    def test_prepare_binds_current_compact_policy_without_changing_archived_old_state(self):
        # A new temporary synthetic namespace, never the live c4 or native source.
        with tempfile.TemporaryDirectory(dir=os.environ.get('PARTIAL_REPAIR_TEST_TEMP')) as directory:
            root = Path(directory)
            run = root / self.run_ref
            old = deepcopy(self.old)
            old['b_route_execution_transition']['current_source_root'] = str(root / 'r8')
            self.write(run / 'run.json', old)
            old_raw = (run / 'run.json').read_bytes()
            self.write(run / recovery.WORKSPACE / 'capability-append/append-ledger.json', self.append)
            self.write(run / self.binding_ref, self.binding)
            self.write(run / self.draft_ref, self.draft)
            self.write(run / recovery.WORKSPACE / 'capability-append/c5/output-schema.json', {'unreserved': True})
            self.runtime.PROVIDER_SCHEMA_POLICY = 'r9-policy'
            self.runtime.seed = Mock(return_value=self.seed)
            transition = SimpleNamespace(build_successor_transition=Mock(return_value={'transition_digest': 'r9'}),
                load_prepared=Mock(return_value={}))
            @contextmanager
            def lock(_): yield
            with self.boundary(), patch.dict(sys.modules, {'_b_route_execution_transition': transition,
                    '_mvg_capability_checkpoint': SimpleNamespace(coordinator_lock=lock)}):
                recovery.prepare(root, run, original_source_root=root / 'r5', current_commit='synthetic-r9', prior_source_root=root / 'r8')
                state = json.loads((run / 'run.json').read_bytes())
                record = recovery.validate_recovery(root, state)
                self.assertEqual(recovery.compact.CURRENT_SCHEMA, state['b_route_input_compact_policy'])
                self.assertEqual(recovery.compact.CURRENT_SCHEMA, record['input_compact_policy'])
                self.assertEqual(old_raw, recovery.image_bytes(record['previous_run']))
                self.assertNotIn('b_route_input_compact_policy', old)
                for policy in (None, 'old-v1'):
                    changed = deepcopy(state)
                    changed['b_route_input_compact_policy'] = policy
                    with self.assertRaisesRegex(ValueError, 'source_frame_changed'):
                        recovery.validate_recovery(root, changed)


if __name__ == '__main__':
    unittest.main(verbosity=2)
