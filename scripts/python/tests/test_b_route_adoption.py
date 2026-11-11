"""Real storage/leases/service composition with an explicitly synthetic eligibility seam."""
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_adoption as adoption
import _b_route_codec as codec
import _planning_apply_journal as journal
from test_b_route_records import MatrixFixture, encoded


class AdoptionCompositionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='nr26-', dir=os.environ.get('ADOPTION_TEST_TEMP')))
        self.cases = {}
        self.protected_tasks = []
        self.request = self.case('one', 'OP-one')

    def case(self, run_id, operation_id):
        import test_b_route_candidate as native_tests
        from _b_route_adoption_projection import project_content
        fixture = MatrixFixture()
        plan_path = fixture.add_plan(run_id, 1)
        fixture.add_flow(plan_path)
        fixture.artifacts['evidence/admission.json'] = encoded({'schema_version': 'synthetic.admission.v1'})
        plan = fixture.models[plan_path]
        plan['adoption_proof_refs'] = [fixture.owned('planning_proof', 'evidence/admission.json')]
        handoff = 'evidence/handoff-' + run_id + '.json'
        fixture.artifacts['evidence/protection.json'] = encoded({'schema_version': 'synthetic.protection.v1'})
        requirement = plan['requirements'][0]['requirement_id']
        flow = plan['definitions']['flows'][0]['id']
        fields = ('source_identity', 'requirements', 'definitions', 'logical_references',
                  'requirement_verification', 'requirement_route_memberships', 'requirement_evidence',
                  'evidence_source_refs', 'coverage_table', 'applicability')
        content = {field: deepcopy(plan[field]) for field in fields}
        for row in content['requirements']:
            row['prior_requirement_ids'] = []
        native_flow = native_tests.CandidateTests.flow(SimpleNamespace(proposal={'proposal_id': requirement}), fid=flow)
        native_flow['source_block_ids'] = list(content['requirements'][0]['source_block_ids'])
        content['definitions']['flows'] = [native_flow]
        content.update(out_of_scope_requirement_ids=[], selected_dependencies=[], unresolved=[], implementation_objects=[])
        fixture.artifacts[handoff] = encoded({'schema_version': 'synthetic.handoff.v1', 'proposal': {'content': content}})
        for name, raw in fixture.artifacts.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        placeholder = {'plan_id': 'PLAN-TEMPLATE', 'plan_revision': 123,
            'requirements': {requirement: 'RQ-TEMPLATE'}, 'flows': {flow: 'FLOW-TEMPLATE'}}
        projected = project_content(content, placeholder)
        target_plan = {**deepcopy(plan), **projected, 'plan_id': 'PLAN-TEMPLATE', 'revision': 123,
            'native_candidate_ref': {'owner': 'planning_proof', 'ref': handoff + '#/proposal/content',
                'files': [{'path': handoff, 'raw_digest': codec.raw_digest(fixture.artifacts[handoff])}]}}
        def template(value, key=None):
            if type(value) is dict:
                return {k: template(v, k) for k, v in value.items()}
            if type(value) is list:
                return [template(v, key) for v in value]
            if value == 'PLAN-TEMPLATE':
                return {'$allocation': 'plan_id'}
            if key in ('revision', 'owner_revision') and value == 123:
                return {'$allocation': 'plan_revision'}
            if value == 'RQ-TEMPLATE':
                return {'$allocation': 'requirement:' + requirement}
            if value == 'FLOW-TEMPLATE':
                return {'$allocation': 'flow:' + flow}
            return value
        def ref(name):
            value = codec.strict_json_loads(fixture.artifacts[name])
            return {'path': name, 'schema_version': value['schema_version'],
                    'raw_digest': codec.raw_digest(fixture.artifacts[name])}
        request = {'schema_version': 'newrouge.b-route-adoption-request.v1', 'operation_id': operation_id,
            'material': {'planner': 'mvg', 'run_id': run_id, 'handoff_ref': ref(handoff),
                'protection_ref': ref('evidence/protection.json'), 'authority_refs': [], 'lineage_refs': [],
                'identity_alignment': {'plan': {'mode': 'new'}, 'binding': {'mode': 'none'},
                    'requirements': [{'candidate_id': requirement, 'mode': 'allocate', 'rationale': 'Explicit synthetic correspondence'}],
                    'flows': [{'candidate_id': flow, 'mode': 'allocate', 'rationale': 'Explicit synthetic correspondence'}], 'tasks': []},
                'target_templates': [{'path_template': 'docs/planning/b-route/plans/{plan_id}/{plan_revision}.json',
                    'schema_version': adoption.PLAN, 'before_raw_digest': None,
                    'after_payload': template(target_plan), 'verification_mode': 'immutable_bytes'}]},
            'review_ref': ref('evidence/admission.json')}
        self.cases[run_id] = fixture, content
        return request

    def request_ref(self, request):
        path = self.root / ('request-' + request['operation_id'] + '.json')
        path.write_bytes(encoded(request))
        return path.relative_to(self.root).as_posix()

    @contextmanager
    def synthetic_capture(self, root, material, review_ref):
        fixture, content = self.cases[material['run_id']]
        snapshot = adoption.Snapshot(root)
        for name in fixture.artifacts:
            snapshot.read(name)
        for reference in [material['handoff_ref'], material['protection_ref'], review_ref]:
            snapshot.ref(reference)
        snapshot.handoff = snapshot.ref(material['handoff_ref'])
        snapshot.prepared = {'inputs': {'dependencies': {'files': {name: codec.raw_digest(raw)
                                                for name, raw in fixture.artifacts.items()}}}}
        snapshot.protection = {'tasks': self.protected_tasks}
        snapshot.proof_paths = set(snapshot.files)
        adoption._committed(snapshot)
        yield snapshot

    def prepare(self, request=None):
        request = self.request if request is None else request
        import _b_route_adoption_review as review
        with patch.object(adoption, 'capture_completed', self.synthetic_capture):
            if request.get('host_review_ref', {}).get('path') != review.location(request['operation_id']) + '/review.json':
                request.pop('host_review_ref', None)
                prepared = adoption.prepare_review(self.root, operation_id=request['operation_id'],
                                                   request_ref=self.request_ref(request))
                if prepared['semantic_execution_required']:
                    from fixtures.adoption_review_protocol import completed
                    completed(self.root, request['operation_id'])
                request['host_review_ref'] = adoption.complete_review(self.root, operation_id=request['operation_id'])['host_review_ref']
            return adoption.prepare(self.root, operation_id=request['operation_id'], request_ref=self.request_ref(request))

    def files(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_prepare_replay_reserve_freezes_allocations_and_writes_no_formal_target(self):
        first = self.prepare()
        raw = (self.root / first['resume_ref']).read_bytes()
        reordered = codec.strict_json_loads(encoded(self.request))
        path = self.root / self.request_ref(reordered)
        path.write_text(json.dumps(reordered, sort_keys=True), encoding='utf-8')
        with patch.object(adoption, 'capture_completed', self.synthetic_capture), \
             patch.object(adoption, 'new_identity', side_effect=AssertionError('Replay must not allocate')):
            replay = adoption.prepare(self.root, operation_id='OP-one', request_ref=path.name)
            self.assertEqual(first['allocations'], replay['allocations'])
            self.assertEqual(raw, (self.root / first['resume_ref']).read_bytes())
            reserved = adoption.reserve(self.root, operation_id='OP-one')
            again = adoption.reserve(self.root, operation_id='OP-one')
        self.assertEqual(reserved, again)
        self.assertEqual('reserved', reserved['state'])
        self.assertEqual(first['frozen_digest'], reserved['frozen_digest'])
        self.assertFalse((self.root / 'docs/planning/b-route').exists())
        self.assertEqual({key: False for key in adoption.FLAGS}, {key: reserved[key] for key in adoption.FLAGS})

    def test_same_id_different_complete_request_rejected_without_store_change(self):
        result = self.prepare()
        before = (self.root / result['resume_ref']).read_bytes()
        changed = deepcopy(self.request)
        changed['material']['identity_alignment']['requirements'][0]['rationale'] = 'Different reviewed content'
        with self.assertRaises(codec.CodecError) as caught:
            self.prepare(changed)
        self.assertEqual(codec.ReasonCode.CONFLICT, caught.exception.diagnostic.reason_code)
        self.assertEqual(before, (self.root / result['resume_ref']).read_bytes())

    def test_proof_drift_blocks_reserve_and_preserves_prepared_state(self):
        result = self.prepare()
        before = (self.root / result['resume_ref']).read_bytes()
        (self.root / 'evidence/admission.json').write_bytes(b'{}')
        with patch.object(adoption, 'capture_completed', self.synthetic_capture), self.assertRaises(codec.CodecError):
            adoption.reserve(self.root, operation_id='OP-one')
        self.assertEqual(before, (self.root / result['resume_ref']).read_bytes())

    def test_target_edit_is_reported_and_never_overwritten(self):
        result = self.prepare()
        envelope = journal.read_operation(self.root, operation_id='OP-one')
        target = self.root / envelope['frozen']['targets'][0]['path']
        target.parent.mkdir(parents=True)
        target.write_bytes(b'{"human":"edit"}')
        before = (self.root / result['resume_ref']).read_bytes()
        inspected = adoption.inspect(self.root, operation_id='OP-one')
        self.assertEqual('blocked', inspected['status'])
        with patch.object(adoption, 'capture_completed', self.synthetic_capture), self.assertRaises(codec.CodecError):
            adoption.reserve(self.root, operation_id='OP-one')
        self.assertEqual(b'{"human":"edit"}', target.read_bytes())
        self.assertEqual(before, (self.root / result['resume_ref']).read_bytes())

    def test_different_ids_same_source_requirement_conflict_but_disjoint_scope_can_prepare(self):
        self.prepare()
        overlap = deepcopy(self.request)
        overlap['operation_id'] = 'OP-overlap'
        with self.assertRaises(codec.CodecError) as caught:
            self.prepare(overlap)
        self.assertEqual(codec.ReasonCode.PENDING, caught.exception.diagnostic.reason_code)
        other = self.case('two', 'OP-two')
        second = self.prepare(other)
        self.assertEqual('prepared', second['state'])
        self.assertEqual(2, len(journal.operation_inventory(self.root)))

    def test_unselected_real_native_boundary_rejects_before_operation_or_activity_write(self):
        import _b_route_planning_runtime as runtime
        run = runtime.run_location(self.root, 'mvg', 'one')
        run.mkdir(parents=True)
        (run / 'run.json').write_bytes(encoded({'input_stage': '3b', 'selection_status': 'pending'}))
        path = self.request_ref(self.request)
        before = self.files()
        with self.assertRaises(codec.CodecError) as caught:
            adoption.prepare(self.root, operation_id='OP-one', request_ref=path)
        self.assertEqual(codec.ReasonCode.UNPUBLISHED, caught.exception.diagnostic.reason_code)
        self.assertEqual(before, self.files())
        self.assertFalse((self.root / journal.OPERATION_STORE).exists())

    def test_both_real_cli_inspect_paths_are_read_only_without_B(self):
        self.prepare()
        before = self.files()
        scripts = Path(adoption.__file__).parent
        paths = [str(scripts), str(scripts.parent / 'sc')]
        paths += [p for p in sys.path if 'site-packages' in p or 'story22-tokenizer-deps' in p]
        for entry, prefix in (('b_route_adoption.py', []), ('dev_cli.py', ['b-route-adoption'])):
            command = [sys.executable, '-I', '-S', '-c',
                'import sys,runpy;sys.path[:0]=' + repr(paths) + ';sys.argv=' +
                repr([entry, *prefix, '--root', str(self.root), '--stage', 'inspect', '--operation-id', 'OP-one']) +
                ';runpy.run_path(' + repr(str(scripts / entry)) + ',run_name="__main__")']
            result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', timeout=30)
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual('inspected', json.loads(result.stdout)['status'])
        self.assertEqual(before, self.files())

    def test_locked_native_coordinator_is_metadata_not_a_business_byte_snapshot(self):
        from _mvg_capability_checkpoint import coordinator_lock
        run = self.root / 'native'
        run.mkdir()
        snapshot = adoption.Snapshot(self.root)
        with coordinator_lock(run):
            snapshot.tree('native')
            snapshot.verify()
        self.assertNotIn('native/capability-coordinator.lock', snapshot.files)
        self.assertIn('native/capability-coordinator.lock', snapshot.directories['native'])

    def test_requirement_flow_and_other_definition_id_namespaces_remain_distinct(self):
        from _b_route_adoption_projection import project_content
        source = deepcopy(self.cases['one'][1])
        old = {source['requirements'][0]['requirement_id'], source['definitions']['flows'][0]['id']}
        def same(value):
            if type(value) is dict:
                return {key: same(child) for key, child in value.items()}
            if type(value) is list:
                return [same(child) for child in value]
            return 'X' if type(value) is str and value in old else value
        source = same(source)
        for family in ('commands', 'states'):
            source['definitions'][family] = [{'id': 'X', 'proposed_owner_key': family,
                'requirement_ids': ['X'], 'responsibility': 'Preserve the typed owner', 'uses': []}]
        changed = project_content(source, {'plan_id': 'PLAN-host', 'plan_revision': 1,
            'requirements': {'X': 'RQ-host'}, 'flows': {'X': 'FLOW-host'}})
        self.assertEqual('RQ-host', changed['requirements'][0]['requirement_id'])
        self.assertEqual('FLOW-host', changed['definitions']['flows'][0]['id'])
        for kind in ('commands', 'states'):
            self.assertEqual('X', changed['definitions'][kind][0]['id'])
            self.assertEqual(['RQ-host'], changed['definitions'][kind][0]['requirement_ids'])

    def owner_conflict(self, kind):
        def add(request):
            _, plan = self.cases[request['material']['run_id']]
            rid = plan['requirements'][0]['requirement_id']
            plan['definitions'][kind].append({'id': 'SHARED', 'proposed_owner_key': 'proposal-owner', 'requirement_ids': [rid],
                'responsibility': 'Preserve the shared owner', 'uses': []})
            template = deepcopy(plan['definitions'][kind][0])
            template.pop('proposed_owner_key')
            template['requirement_ids'] = [{'$allocation': 'requirement:' + rid}]
            request['material']['target_templates'][0]['after_payload']['definitions'][kind].append(template)
            handoff = request['material']['handoff_ref']['path']
            fixture = self.cases[request['material']['run_id']][0]
            raw = encoded({'schema_version': 'synthetic.handoff.v1', 'proposal': {'content': plan}})
            fixture.artifacts[handoff] = raw
            (self.root / handoff).write_bytes(raw)
            request['material']['handoff_ref']['raw_digest'] = codec.raw_digest(raw)
            request['material']['target_templates'][0]['after_payload']['native_candidate_ref']['files'][0]['raw_digest'] = codec.raw_digest(raw)
        add(self.request)
        first = self.prepare()
        other = self.case('two', 'OP-two')
        add(other)
        with self.assertRaises(codec.CodecError) as caught:
            self.prepare(other)
        self.assertEqual(codec.ReasonCode.PENDING, caught.exception.diagnostic.reason_code)
        self.assertEqual(['OP-one'], [r['operation_id'] for r in journal.operation_inventory(self.root)])
        self.assertEqual('prepared', first['state'])

    def test_pending_command_owner_collision_is_rejected(self):
        self.owner_conflict('commands')

    def test_pending_state_owner_collision_is_rejected(self):
        self.owner_conflict('states')

    def test_reconstructed_allocation_identity_never_equates_boolean_or_float_revision(self):
        result = self.prepare()
        operation = self.root / result['resume_ref']
        index_path = self.root / journal.OPERATION_STORE / 'pending.json'
        original = codec.strict_json_loads(operation.read_bytes())
        original_index = codec.strict_json_loads(index_path.read_bytes())
        for invalid in (True, 1.0):
            with self.subTest(revision=invalid, type=type(invalid).__name__):
                damaged = deepcopy(original)
                damaged['frozen']['allocations']['plan_revision'] = invalid
                damaged['frozen_digest'] = codec.canonical_digest(damaged['frozen'])
                index = deepcopy(original_index)
                index['operations'][0]['frozen_digest'] = damaged['frozen_digest']
                operation.write_bytes(encoded(damaged))
                index_path.write_bytes(encoded(index))
                before = (operation.read_bytes(), index_path.read_bytes())
                with patch.object(adoption, 'capture_completed', self.synthetic_capture), self.assertRaises(codec.CodecError):
                    adoption.reserve(self.root, operation_id='OP-one')
                self.assertEqual(before, (operation.read_bytes(), index_path.read_bytes()))

    def test_existing_plan_binding_and_task_identity_have_independent_durable_counters(self):
        fixture = MatrixFixture()
        path = 'docs/planning/b-route/plans/p/2.json'
        fixture.add_flow(path)
        binding_path = fixture.add_binding('p', 7, task_id=11)
        output = fixture.render()
        for name, raw in output.items():
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        joined = fixture.join((11,))
        for name, document in (('master', joined.master), ('back', joined.back), ('gameplay', joined.gameplay)):
            target = self.root / adoption.TRIPLET[name]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(encoded(document))
        snapshot = adoption.Snapshot(self.root)
        adoption._committed(snapshot)
        snapshot.protection = {'tasks': [{'task_id': 11, 'definition_digest': snapshot.tasks[11]}]}
        snapshot.prepared = {'inputs': {'dependencies': {'files': {path: codec.raw_digest(output[path]),
                                                                 binding_path: codec.raw_digest(output[binding_path])}}}}
        snapshot.handoff = {'proposal': {'content': fixture.models[path]}}
        def ref(name):
            return {'path': name, 'schema_version': codec.strict_json_loads(output[name])['schema_version'],
                    'raw_digest': codec.raw_digest(output[name])}
        alignment = {'plan': {'mode': 'reuse', 'plan_ref': ref(path)},
            'binding': {'mode': 'revise', 'binding_ref': ref(binding_path)},
            'requirements': [{'candidate_id': 'REQ-p', 'stable_id': 'REQ-p', 'mode': 'reuse',
                              'rationale': 'Retain reviewed identity', 'evidence_ref': ref(path)}],
            'flows': [{'candidate_id': 'flow-p', 'stable_id': 'flow-p', 'mode': 'reuse',
                       'rationale': 'Retain definition owner', 'evidence_ref': ref(path)}],
            'tasks': [{'task_id': 11}]}
        result = adoption.propose_allocations(snapshot, alignment, [])
        adoption.validate_allocations(result)
        self.assertEqual(('p', 3, 8), (result['plan_id'], result['plan_revision'], result['binding_revision']))
        self.assertEqual({'REQ-p': 'REQ-p'}, result['requirements'])
        self.assertEqual({'flow-p': 'flow-p'}, result['flows'])
        self.assertEqual(['11'], list(result['task_definitions']))
        claim = {'operation_id': 'OP-pending', 'frozen': {'allocations': {
            **result, 'plan_revision': 5, 'binding_revision': 12}}}
        next_result = adoption.propose_allocations(snapshot, alignment, [claim])
        self.assertEqual((6, 13), (next_result['plan_revision'], next_result['binding_revision']))
        joined.master['master']['tasks'][0]['status'] = 'done'
        (self.root / adoption.TRIPLET['master']).write_bytes(encoded(joined.master))
        current = adoption.Snapshot(self.root)
        adoption._committed(current)
        current.protection, current.prepared, current.handoff = snapshot.protection, snapshot.prepared, snapshot.handoff
        self.assertEqual(result['task_definitions'],
            adoption.propose_allocations(current, alignment, [])['task_definitions'])

    def test_native_proof_locator_cannot_be_substituted_by_a_valid_owned_reference(self):
        request = deepcopy(self.request)
        proof = request['material']['target_templates'][0]['after_payload']['native_candidate_ref']
        proof['ref'] = request['review_ref']['path']
        proof['files'] = [{'path': request['review_ref']['path'],
                           'raw_digest': request['review_ref']['raw_digest']}]
        with self.assertRaises(codec.CodecError) as caught:
            self.prepare(request)
        self.assertEqual(codec.ReasonCode.IDENTITY_UNPROVABLE, caught.exception.diagnostic.reason_code)
        self.assertFalse((self.root / journal.OPERATION_STORE).exists())

    def test_schema_valid_graph_semantic_edit_cannot_replace_admitted_content(self):
        request = deepcopy(self.request)
        request['material']['target_templates'][0]['after_payload']['definitions']['flows'][0][
            'observable_result'] = 'A different result absent from the admitted native candidate'
        with self.assertRaises(codec.CodecError) as caught:
            self.prepare(request)
        self.assertEqual(codec.ReasonCode.IDENTITY_UNPROVABLE, caught.exception.diagnostic.reason_code)
        self.assertFalse((self.root / journal.OPERATION_STORE).exists())

    def test_binding_reservation_requires_its_complete_target(self):
        request = deepcopy(self.request)
        request['material']['identity_alignment']['binding'] = {'mode': 'new'}
        with self.assertRaises(codec.CodecError):
            self.prepare(request)
        self.assertFalse((self.root / journal.OPERATION_STORE).exists())

    def test_new_plan_cannot_freeze_invented_historical_lineage(self):
        request = deepcopy(self.request)
        flow = request['material']['identity_alignment']['flows'][0]['candidate_id']
        request['material']['target_templates'][0]['after_payload']['lineage']['identity_alignment'] = [
            {'kind': 'flow', 'previous_id': 'never-existed',
             'current_id': {'$allocation': 'flow:' + flow}, 'rationale': 'Invented historical correspondence'}]
        with self.assertRaises(codec.CodecError):
            self.prepare(request)
        self.assertFalse((self.root / journal.OPERATION_STORE).exists())

    def test_retained_lineage_is_complete_typed_and_matches_explicit_correspondence(self):
        definitions = {'flows': [{'id': 'FLOW-stable'}], 'commands': [{'id': 'CMD-stable'}], 'states': []}
        prior = {'definitions': deepcopy(definitions)}
        flow = {'kind': 'flow', 'previous_id': 'FLOW-stable', 'current_id': 'FLOW-stable',
                'rationale': 'The explicitly retained Flow'}
        command = {'kind': 'command', 'previous_id': 'CMD-stable', 'current_id': 'CMD-stable',
                   'rationale': 'The same command owner'}
        value = {'definitions': deepcopy(definitions), 'lineage': {'identity_alignment': [flow, command]}}
        alignment = {'flows': [{'candidate_id': 'FLOW-native', 'stable_id': 'FLOW-stable',
            'mode': 'reuse', 'rationale': flow['rationale']}]}
        allocations = {'flows': {'FLOW-native': 'FLOW-stable'}}
        adoption.validate_lineage(value, alignment, allocations, prior)
        for rows in ([flow], [command], [flow, command, deepcopy(flow)],
                     [{**flow, 'previous_id': 'invented'}, command],
                     [{**flow, 'rationale': 'An unrelated correspondence'}, command]):
            with self.subTest(rows=rows), self.assertRaises(codec.CodecError):
                adoption.validate_lineage({**value, 'lineage': {'identity_alignment': rows}}, alignment, allocations, prior)

    def test_binding_uses_host_derived_plan_reference_and_replays_original_bytes(self):
        fixture, _ = self.cases['one']
        binding_path = fixture.add_binding('one', 1, task_id=11)
        binding = deepcopy(fixture.bindings[binding_path][0])
        rid = self.request['material']['identity_alignment']['requirements'][0]['candidate_id']
        binding.update(plan_id={'$allocation': 'plan_id'}, binding_revision={'$allocation': 'binding_revision'},
                       plan_ref={'$adopted_plan_ref': True})
        binding['task_mappings'][0]['requirement_ids'] = [{'$allocation': 'requirement:' + rid}]
        joined = fixture.join((11,))
        for name, document in (('master', joined.master), ('back', joined.back), ('gameplay', joined.gameplay)):
            path = self.root / adoption.TRIPLET[name]
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(encoded(document))
        snapshot = adoption.Snapshot(self.root)
        adoption._committed(snapshot)
        self.protected_tasks = [{'task_id': 11, 'definition_digest': snapshot.tasks[11]}]
        request = deepcopy(self.request)
        request['material']['identity_alignment']['binding'] = {'mode': 'new'}
        request['material']['identity_alignment']['tasks'] = [{'task_id': 11}]
        # Deliberately precede the plan: derivation cannot depend on request order.
        request['material']['target_templates'].insert(0, {
            'path_template': 'docs/planning/b-route/bindings/{plan_id}/{binding_revision}.json',
            'schema_version': adoption.BINDING, 'before_raw_digest': None,
            'after_payload': binding, 'verification_mode': 'immutable_bytes'})
        first = self.prepare(request)
        envelope = journal.read_operation(self.root, operation_id='OP-one')
        targets = envelope['frozen']['targets']
        self.assertEqual(adoption.adopted_plan_ref(targets[1]), targets[0]['after_payload']['plan_ref'])
        raw = (self.root / first['resume_ref']).read_bytes()
        with patch.object(adoption, 'capture_completed', self.synthetic_capture):
            adoption.reserve(self.root, operation_id='OP-one')
        stored = journal.read_operation(self.root, operation_id='OP-one')
        self.assertEqual(envelope['frozen'], stored['frozen'])
        self.assertEqual(raw, encoded(envelope))
        for field, replacement in (('path', 'docs/planning/b-route/plans/wrong/1.json'),
                                   ('digest', codec.canonical_digest({'different': 'plan'}))):
            damaged = deepcopy(targets)
            damaged[0]['after_payload']['plan_ref'][field] = replacement
            with self.subTest(field=field), self.assertRaises(codec.CodecError):
                adoption.validate_binding_targets(envelope['frozen']['allocations'], damaged)
        with self.assertRaises(codec.CodecError):
            adoption.validate_binding_targets({**envelope['frozen']['allocations'], 'binding_revision': None}, targets)

    def test_selected_marker_cannot_substitute_for_missing_host_adoption_review(self):
        import _b_route_planning_runtime as runtime
        run = runtime.run_location(self.root, 'mvg', 'one')
        run.mkdir(parents=True)
        (run / 'run.json').write_bytes(encoded({'input_stage': '3b', 'selection_status': 'selected'}))
        path = self.request_ref(self.request)
        before = self.files()
        with patch.object(adoption, 'new_identity', side_effect=AssertionError('No allocation before review')), \
             self.assertRaises(codec.CodecError) as caught:
            adoption.prepare(self.root, operation_id='OP-one', request_ref=path)
        self.assertEqual(codec.ReasonCode.DEPENDENCY_UNAVAILABLE, caught.exception.diagnostic.reason_code)
        self.assertEqual('missing host_review_ref', caught.exception.diagnostic.actual)
        self.assertEqual(before, self.files())
        self.assertFalse((self.root / journal.OPERATION_STORE).exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
