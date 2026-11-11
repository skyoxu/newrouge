"""Offline host-review composition. Candidate eligibility and protocol are synthetic.

The actual review owner, schema, protocol replay, storage and leases are used.
No process/model/credential/session access occurs in these fixtures.
"""
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import _b_route_adoption as adoption
import _b_route_adoption_review as review
import _b_route_codec as codec
import _b_route_operation_scope as scopes
import _planning_apply_journal as journal
import test_b_route_adoption as composition
from fixtures.adoption_review_protocol import completed


class HostAdoptionReviewTests(unittest.TestCase):
    def setUp(self):
        self.fx = composition.AdoptionCompositionTests('test_prepare_replay_reserve_freezes_allocations_and_writes_no_formal_target')
        self.fx.setUp()
        self.root, self.request = self.fx.root, self.fx.request

    def stage(self, *, seal=False):
        with patch.object(adoption, 'capture_completed', self.fx.synthetic_capture):
            if seal:
                return adoption.complete_review(self.root, operation_id='OP-one')
            return adoption.prepare_review(self.root, operation_id='OP-one', request_ref=self.fx.request_ref(self.request))

    def semantic(self):
        from test_b_route_records import encoded
        fixture, _ = self.fx.cases['one']
        joined = fixture.join((11,))
        for name, document in (('master', joined.master), ('back', joined.back), ('gameplay', joined.gameplay)):
            path = self.root / adoption.TRIPLET[name]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(encoded(document))
        snapshot = adoption.Snapshot(self.root)
        adoption._committed(snapshot)
        self.fx.protected_tasks = [{'task_id': 11, 'definition_digest': snapshot.tasks[11]}]
        self.request['material']['identity_alignment']['tasks'] = [{'task_id': 11}]
        result = self.stage()
        self.assertTrue(result['semantic_execution_required'])
        return result

    def approved(self):
        self.stage()
        self.request['host_review_ref'] = self.stage(seal=True)['host_review_ref']

    def prepare(self):
        with patch.object(adoption, 'capture_completed', self.fx.synthetic_capture):
            return adoption.prepare(self.root, operation_id='OP-one', request_ref=self.fx.request_ref(self.request))

    def test_lock_namespace_initialization_has_no_operation_claim_and_inspection_stays_read_only(self):
        def paths():
            return {path.relative_to(self.root).as_posix() for path in self.root.rglob('*')}
        before_paths, before_files = paths(), self.fx.files()
        self.assertEqual([], journal.operation_inventory(self.root))
        with self.assertRaises(codec.CodecError):
            adoption.inspect(self.root, operation_id='OP-missing')
        self.assertEqual(before_paths, paths())
        fixed = ('logs', 'logs/ci', scopes.STORE, scopes.STORE + '/locks',
                 scopes.STORE + '/locks/metadata', scopes.STORE + '/locks/scopes')
        expected = {name for name in fixed if not (self.root / name).exists()}
        metadata, scope_root = scopes.initialize_lock_namespace(self.root)
        self.assertEqual(self.root / scopes.STORE / 'locks/metadata', metadata)
        self.assertEqual(self.root / scopes.STORE / 'locks/scopes', scope_root)
        self.assertEqual(expected, paths() - before_paths)
        self.assertEqual(before_files, self.fx.files())
        initialized = paths()
        scopes.initialize_lock_namespace(self.root)
        self.assertEqual([], journal.operation_inventory(self.root))
        with self.assertRaises(codec.CodecError):
            adoption.inspect(self.root, operation_id='OP-missing')
        self.assertEqual(initialized, paths())
        self.assertFalse((self.root / scopes.STORE / 'operations').exists())
        self.assertFalse((self.root / scopes.STORE / 'pending.json').exists())

    def test_review_capture_starts_after_fixed_lock_namespace_initialization(self):
        self.assertFalse((self.root / scopes.STORE).exists())
        self.assertFalse((self.root / review.BASE).exists())
        observed = []
        @contextmanager
        def checked_capture(root, material, review_ref):
            self.assertTrue((root / scopes.STORE / 'locks/metadata').is_dir())
            self.assertTrue((root / scopes.STORE / 'locks/scopes').is_dir())
            self.assertFalse((root / scopes.STORE / 'operations').exists())
            self.assertFalse((root / scopes.STORE / 'pending.json').exists())
            self.assertTrue((root / review.BASE).is_dir())
            self.assertEqual([], list((root / review.BASE).iterdir()))
            self.assertFalse((root / review.location('OP-one')).exists())
            observed.append(True)
            with self.fx.synthetic_capture(root, material, review_ref) as snapshot:
                yield snapshot
        reference = self.fx.request_ref(self.request)
        with patch.object(adoption, 'capture_completed', checked_capture):
            result = adoption.prepare_review(self.root, operation_id='OP-one', request_ref=reference)
        self.assertEqual('review_prepared', result['status'])
        self.assertEqual([True], observed)
        self.assertEqual([], journal.operation_inventory(self.root))

    def test_review_namespace_initialization_creates_only_base_without_claims_or_review_artifacts(self):
        def paths():
            return {path.relative_to(self.root).as_posix() for path in self.root.rglob('*')}
        before_paths, before_files = paths(), self.fx.files()
        fixed = ('logs', 'logs/ci', review.BASE)
        expected = {name for name in fixed if not (self.root / name).exists()}
        base = review.initialize_namespace(self.root)
        self.assertEqual(self.root / review.BASE, base)
        self.assertEqual([], list(base.iterdir()))
        self.assertEqual(expected, paths() - before_paths)
        self.assertEqual(before_files, self.fx.files())
        initialized = paths()
        review.initialize_namespace(self.root)
        self.assertEqual([], journal.operation_inventory(self.root))
        with self.assertRaises(codec.CodecError):
            adoption.inspect(self.root, operation_id='OP-missing')
        self.assertEqual(initialized, paths())
        self.assertFalse((self.root / scopes.STORE).exists())
        self.assertFalse((self.root / review.location('OP-one')).exists())

    def test_prepare_and_reserve_initialize_namespace_before_each_capture(self):
        self.approved()
        reference = self.fx.request_ref(self.request)
        original_initialize = scopes.initialize_lock_namespace
        for stage in ('prepare', 'reserve'):
            initialized, captured = [], []
            def initialize(root):
                value = original_initialize(root)
                initialized.append(Path(root).resolve())
                return value
            @contextmanager
            def checked_capture(root, material, review_ref):
                self.assertEqual([self.root.resolve()], initialized)
                captured.append(True)
                with self.fx.synthetic_capture(root, material, review_ref) as snapshot:
                    yield snapshot
            with self.subTest(stage=stage), patch.object(scopes, 'initialize_lock_namespace', initialize), \
                 patch.object(adoption, 'capture_completed', checked_capture):
                if stage == 'prepare':
                    result = adoption.prepare(self.root, operation_id='OP-one', request_ref=reference)
                    self.assertEqual('prepared', result['state'])
                else:
                    result = adoption.reserve(self.root, operation_id='OP-one')
                    self.assertEqual('reserved', result['state'])
            self.assertEqual([True], captured)

    def test_machine_owner_binds_complete_preview_and_assigns_only_after_review(self):
        result = self.stage()
        self.assertEqual('new_plan_exact_native_projection', result['machine_preservation'])
        self.assertEqual({'NEWROGUE_CODEX_REASONING_EFFORT': 'high'}, result['required_environment'])
        self.assertEqual([], journal.operation_inventory(self.root))
        self.assertFalse((self.root / 'docs/planning/b-route').exists())
        from openai_isolated_model_runner import workspace_payload
        w = review.path(self.root, review.location('OP-one') + '/w')
        subject = review.read_subject(self.root, 'OP-one')
        self.assertEqual(review.request_payload(subject), workspace_payload(w, prompt_path=w / 'prompt.txt', output_path=w / 'output.json'))
        self.request['host_review_ref'] = self.stage(seal=True)['host_review_ref']
        with patch.object(adoption, 'new_identity', side_effect=AssertionError('Reviewed IDs must be reused')):
            first = self.prepare()
        self.assertEqual(subject['preview']['allocations'], first['allocations'])
        with patch.object(adoption, 'capture_completed', self.fx.synthetic_capture):
            reserved = adoption.reserve(self.root, operation_id='OP-one')
        self.assertEqual('reserved', reserved['state'])
        self.assertFalse(reserved['formal_adoption'])

    def test_changed_alignment_or_target_cannot_reuse_review(self):
        self.approved()
        for part in ('alignment', 'target'):
            original = deepcopy(self.request)
            if part == 'alignment':
                self.request['material']['identity_alignment']['flows'][0]['rationale'] = 'A changed semantic mapping'
            else:
                self.request['material']['target_templates'][0]['after_payload']['lineage']['change_summary'] = 'A changed delta'
            with self.subTest(part=part), self.assertRaises(codec.CodecError):
                self.prepare()
            self.request = original
        self.assertEqual([], journal.operation_inventory(self.root))

    def test_tampered_support_and_caller_approval_boolean_are_not_reviews(self):
        self.approved()
        proof_path = review.path(self.root, self.request['host_review_ref']['path'])
        original = proof_path.read_bytes()
        value = codec.strict_json_loads(original)
        value['approved'] = True
        proof_path.write_bytes(review.raw(value))
        self.request['host_review_ref']['raw_digest'] = codec.raw_digest(proof_path.read_bytes())
        with self.assertRaises(codec.CodecError):
            self.prepare()
        proof_path.write_bytes(original)
        self.request['host_review_ref']['raw_digest'] = codec.raw_digest(original)
        review.path(self.root, review.location('OP-one') + '/w/prompt.txt').write_bytes(b'abridged')
        with self.assertRaises(codec.CodecError):
            self.prepare()
        self.assertEqual([], journal.operation_inventory(self.root))

    def test_changed_policy_cannot_relabel_old_review_current(self):
        self.approved()
        with patch.object(review, 'policy_identity', return_value=codec.canonical_digest({'different': 'policy'})), \
             self.assertRaises(codec.CodecError):
            self.prepare()
        self.assertEqual([], journal.operation_inventory(self.root))

    def test_review_cannot_replace_actual_native_eligibility(self):
        self.approved()
        import _b_route_planning_runtime as runtime
        run = runtime.run_location(self.root, 'mvg', 'one')
        run.mkdir(parents=True)
        (run / 'run.json').write_bytes(review.raw({'input_stage': '3b', 'selection_status': 'selected'}))
        with patch.object(adoption, 'new_identity', side_effect=AssertionError('No allocation')), \
             self.assertRaises(codec.CodecError):
            adoption.prepare(self.root, operation_id='OP-one', request_ref=self.fx.request_ref(self.request))
        self.assertEqual([], journal.operation_inventory(self.root))

    def test_semantic_owner_replays_complete_high_official_protocol(self):
        self.semantic()
        completed(self.root, 'OP-one')
        self.request['host_review_ref'] = self.stage(seal=True)['host_review_ref']
        proof = codec.strict_json_loads(review.path(self.root, self.request['host_review_ref']['path']).read_bytes())
        self.assertEqual('semantic', proof['mode'])
        self.assertEqual('high', proof['evidence']['runtime_configuration']['reasoning_effort'])
        self.assertEqual('unknown', proof['evidence']['provider_actual_model'])
        self.assertEqual('unknown', proof['evidence']['physical_requests'])
        self.assertEqual('prepared', self.prepare()['state'])

    def test_semantic_absence_low_tools_incomplete_wrong_input_and_findings_fail_closed(self):
        self.semantic()
        with self.assertRaises(codec.CodecError):
            self.stage(seal=True)
        for label, options in [('low', {'effort': 'low'}), ('tools', {'tool': True}),
                               ('incomplete', {'incomplete': True}), ('input', {'prompt_override': 'truncated'}),
                               ('blocked', {'blocked': True})]:
            completed(self.root, 'OP-one', **options)
            with self.subTest(label=label), self.assertRaises(codec.CodecError):
                self.stage(seal=True)
            self.assertFalse(review.path(self.root, review.location('OP-one') + '/review.json').exists())
        self.assertEqual([], journal.operation_inventory(self.root))

    def test_semantic_review_must_use_a_different_native_thread(self):
        fixture, _ = self.fx.cases['one']
        name = 'evidence/native.app-server.jsonl'
        data = b'{"direction":"server","message":{"result":{"thread":{"id":"independent-review-thread"}}}}\n'
        fixture.artifacts[name] = data
        (self.root / name).write_bytes(data)
        self.semantic()
        completed(self.root, 'OP-one')
        with self.assertRaises(codec.CodecError):
            self.stage(seal=True)

    def test_verdict_denominator_unknown_fields_and_hidden_findings_are_rejected(self):
        self.semantic()
        subject = review.read_subject(self.root, 'OP-one')
        _, _, value = completed(self.root, 'OP-one')
        for kind in ('missing', 'duplicate', 'unknown', 'hidden'):
            changed = deepcopy(value)
            if kind == 'missing':
                changed['checks'].pop()
            elif kind == 'duplicate':
                changed['checks'][-1] = changed['checks'][0]
            elif kind == 'unknown':
                changed['approved'] = True
            else:
                changed['findings'] = ['A hidden unresolved defect']
            with self.subTest(kind=kind), self.assertRaises(codec.CodecError):
                review.check_verdict(subject, changed)

    def test_review_is_revalidated_at_the_persistence_lease_boundary(self):
        self.approved()
        import _b_route_operation_scope as scopes
        original = scopes.scope_guard
        @contextmanager
        def tamper(root, scope_ids, *, prepare_under_lease, **kwargs):
            def changed():
                review.path(self.root, review.location('OP-one') + '/w/schema.json').write_bytes(b'{}')
                return prepare_under_lease()
            with original(root, scope_ids, prepare_under_lease=changed, **kwargs) as result:
                yield result
        with patch.object(scopes, 'scope_guard', tamper), self.assertRaises(codec.CodecError):
            self.prepare()
        self.assertEqual([], journal.operation_inventory(self.root))

    def test_retained_partial_unselected_history_keeps_raw_identity_without_invalidating_native_owner(self):
        fixture, _ = self.fx.cases['one']
        name = 'evidence/failed.app-server.jsonl'
        data = (b'{"direction":"server","message":{"result":{"thread":{"id":"prior-failed-thread"}}}}\n'
                b'{"direction":"server","message":{"result":{"thread":null,"turn":null}}}\n{"partial"')
        fixture.artifacts[name] = data
        (self.root / name).write_bytes(data)
        self.approved()
        subject = review.read_subject(self.root, 'OP-one')
        self.assertIn('prior-failed-thread', subject['native_threads'])
        self.assertTrue(any(row['path'] == name and row['raw_digest'] == codec.raw_digest(data)
                            for row in subject['preview']['authority_refs']))
        self.assertEqual('prepared', self.prepare()['state'])

    def test_review_support_hardlink_alias_is_rejected(self):
        self.approved()
        target = review.path(self.root, review.location('OP-one') + '/w/schema.json')
        os.link(target, self.root / 'synthetic-schema-alias.json')
        with self.assertRaises(codec.CodecError) as caught:
            self.prepare()
        self.assertEqual(codec.ReasonCode.UNSAFE_PATH, caught.exception.diagnostic.reason_code)
        self.assertEqual([], journal.operation_inventory(self.root))

    def test_status_only_task_change_preserves_reviewed_definition_identity(self):
        self.semantic()
        completed(self.root, 'OP-one')
        self.request['host_review_ref'] = self.stage(seal=True)['host_review_ref']
        master = self.root / adoption.TRIPLET['master']
        value = codec.strict_json_loads(master.read_bytes())
        value['master']['tasks'][0]['status'] = 'done'
        master.write_bytes(review.raw(value))
        self.assertEqual('prepared', self.prepare()['state'])

    def binding_only_snapshot(self, *, separate_admission=False):
        """A real validated formal catalog unit, not a native admission fixture."""
        from test_b_route_records import MatrixFixture, encoded
        fixture = MatrixFixture()
        plan = 'docs/planning/b-route/plans/p/2.json'
        fixture.add_flow(plan)
        binding = fixture.add_binding('p', 7, task_id=11)
        if separate_admission:
            fixture.artifacts['evidence/legacy-admission.json'] = fixture.artifacts.pop('evidence/admission.json')
            fixture.models[plan]['adoption_proof_refs'] = [fixture.owned('planning_proof', 'evidence/legacy-admission.json')]
        fixture.hooks[adoption.CATALOG] = lambda value: value['scope_heads'][0].update(plan_refs=[])
        output = fixture.render()
        for name, data in output.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        joined = fixture.join((11,))
        for name, document in (('master', joined.master), ('back', joined.back), ('gameplay', joined.gameplay)):
            path = self.root / adoption.TRIPLET[name]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(encoded(document))
        snapshot = adoption.Snapshot(self.root)
        adoption._committed(snapshot)  # includes actual validate_bundle / TaskJoin
        snapshot.handoff = {'proposal': {'content': fixture.models[plan]}}
        snapshot.prepared = {'inputs': {'dependencies': {'files': {
            plan: codec.raw_digest(output[plan]), binding: codec.raw_digest(output[binding])}}}}
        snapshot.protection = {'tasks': [{'task_id': 11, 'definition_digest': snapshot.tasks[11]}]}
        def ref(name):
            return {'path': name, 'schema_version': codec.strict_json_loads(output[name])['schema_version'],
                    'raw_digest': codec.raw_digest(output[name])}
        return snapshot, plan, binding, ref

    def test_binding_only_head_retains_current_plan_identity_and_its_own_revision(self):
        snapshot, plan, _, ref = self.binding_only_snapshot()
        alignment = {'plan': {'mode': 'reuse', 'plan_ref': ref(plan)}, 'binding': {'mode': 'none'},
            'requirements': [{'candidate_id': 'REQ-p', 'stable_id': 'REQ-p', 'mode': 'reuse',
                              'rationale': 'Same source requirement', 'evidence_ref': ref(plan)}],
            'flows': [{'candidate_id': 'flow-p', 'stable_id': 'flow-p', 'mode': 'reuse',
                       'rationale': 'Same retained Flow', 'evidence_ref': ref(plan)}], 'tasks': []}
        value = adoption.propose_allocations(snapshot, alignment, [])
        self.assertEqual(('p', 3), (value['plan_id'], value['plan_revision']))
        self.assertIn(plan, adoption._current_plan_refs(snapshot))

    def test_binding_only_head_is_in_complete_affected_review_context(self):
        from _b_route_operation_scope import resource_scopes
        snapshot, plan, binding, _ = self.binding_only_snapshot()
        context = review.make_subject(snapshot, self.request, {'request': self.request,
            'allocations': {'plan_id': 'p'}, 'scope_ids': list(resource_scopes(plan_ids=['p'], task_ids=[11])),
            'authority_refs': [], 'targets': []})
        self.assertEqual(1, len(context['affected_catalog']['scope_heads']))
        self.assertEqual([], context['affected_catalog']['scope_heads'][0]['plan_refs'])
        self.assertEqual(7, context['affected_catalog']['scope_heads'][0]['binding_refs'][0]['revision'])
        self.assertIn(plan, context['related_records'])
        self.assertIn(binding, context['related_records'])
        self.assertIn('11', context['task_definitions'])

    def test_public_replan_reuses_existing_ids_and_independent_revisions_without_formal_writes(self):
        snapshot, plan, binding, ref = self.binding_only_snapshot(separate_admission=True)
        fixture, _ = self.fx.cases['one']
        for name in (plan, binding, 'evidence/legacy-admission.json'):
            fixture.artifacts[name] = (self.root / name).read_bytes()
        self.fx.protected_tasks = snapshot.protection['tasks']
        request = deepcopy(self.request)
        alignment = request['material']['identity_alignment']
        rid, fid = alignment['requirements'][0]['candidate_id'], alignment['flows'][0]['candidate_id']
        alignment.update(plan={'mode': 'reuse', 'plan_ref': ref(plan)},
                         binding={'mode': 'revise', 'binding_ref': ref(binding)}, tasks=[{'task_id': 11}])
        alignment['requirements'][0].update(mode='reuse', stable_id='REQ-p', evidence_ref=ref(plan))
        alignment['flows'][0].update(mode='reuse', stable_id='flow-p', evidence_ref=ref(plan))
        lineage = request['material']['target_templates'][0]['after_payload']['lineage']
        lineage.update(previous_plan_ref={'path': plan, 'schema_version': adoption.PLAN, 'entity_id': 'p',
            'revision': 2, 'digest': ref(plan)['raw_digest'], 'verification_mode': 'raw', 'codec_version': None},
            change_summary='Explicit reviewed replan with retained identities',
            identity_alignment=[{'kind': 'flow', 'previous_id': 'flow-p', 'current_id': 'flow-p',
                                 'rationale': alignment['flows'][0]['rationale']}])
        body = deepcopy(dict(snapshot.committed)[binding])
        body.update(plan_id={'$allocation': 'plan_id'}, binding_revision={'$allocation': 'binding_revision'},
                    plan_ref={'$adopted_plan_ref': True})
        request['material']['target_templates'].append({'path_template':
            'docs/planning/b-route/bindings/{plan_id}/{binding_revision}.json', 'schema_version': adoption.BINDING,
            'before_raw_digest': None, 'after_payload': body, 'verification_mode': 'immutable_bytes'})
        def formal_bytes():
            return {path.relative_to(self.root).as_posix(): path.read_bytes()
                    for path in (self.root / 'docs/planning/b-route').rglob('*') if path.is_file()}
        before = formal_bytes()
        first = self.fx.prepare(request)
        allocation = first['allocations']
        self.assertEqual(('p', 3, 8), (allocation['plan_id'], allocation['plan_revision'], allocation['binding_revision']))
        self.assertEqual({rid: 'REQ-p'}, allocation['requirements'])
        self.assertEqual({fid: 'flow-p'}, allocation['flows'])
        self.assertEqual(['11'], list(allocation['task_definitions']))
        with patch.object(adoption, 'new_identity', side_effect=AssertionError('No reallocation')):
            self.assertEqual(first['frozen_digest'], self.fx.prepare(request)['frozen_digest'])
        with patch.object(adoption, 'capture_completed', self.fx.synthetic_capture):
            reserved = adoption.reserve(self.root, operation_id='OP-one')
        self.assertEqual('reserved', reserved['state'])
        self.assertEqual(first['frozen_digest'], reserved['frozen_digest'])
        self.assertEqual(before, formal_bytes())


if __name__ == '__main__':
    unittest.main(verbosity=2)
