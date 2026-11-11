"""Real current-chain compensation IO; independent review uses synthetic protocol.

No native/model execution or runtime qualification is granted by these tests.
"""
from copy import deepcopy
from contextlib import redirect_stdout
import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_adoption as adoption
import _b_route_adoption_review as review
import _b_route_codec as codec
import _b_route_commit as commit
import _b_route_commit_projection as projection
import _b_route_compensation as compensation
import _b_route_compensation_review_materials as materials
import _b_route_operation_scope as scope
import _b_route_records as records
import _planning_apply_journal as journal
from test_b_route_commit import CommitFixture
from test_b_route_records import MatrixFixture, encoded, CATALOG, ORIGINS
from fixtures.adoption_review_protocol import completed
from test_b_route_commit_recovery import assert_boundary_drift_rejected


class CompensationTests(CommitFixture, unittest.TestCase):
    def baseline(self, *, bound=False, task_status='done'):
        original = self.prepare()
        self.publish()
        if bound:
            # A standalone, internally valid later formal chain with a completed
            # existing Task. The old local claim has no publication path into
            # this catalog and remains pending; no old history is rewritten.
            matrix = MatrixFixture()
            matrix.models.clear()
            old_path = original['frozen']['targets'][0]['path']
            payload = deepcopy(original['frozen']['targets'][0]['after_payload'])
            payload['revision'] = 2
            payload['requirements'][0]['acceptance_intent'] += ' Preserve a later legitimate clarification.'
            payload['lineage']['previous_plan_ref'] = projection.reference(old_path, (self.root / old_path).read_bytes())
            payload['lineage']['change_summary'] = 'Later legitimate current formal clarification'
            for child in records._walk(payload):
                if child.get('owner_plan_id') == payload['plan_id'] and 'owner_revision' in child:
                    child['owner_revision'] = 2
            path = records._managed_path(payload)
            matrix.models[path] = payload
            matrix.current_plans = [path]
            # Unlike MatrixFixture's simple default plans, this native graph
            # contains typed logical uses. Freeze their actual current owners
            # in the synthetic seed receipt, including the new revision/ref.
            uses = [child for child in records._walk(payload)
                    if set(child) == {'kind', 'definition_id', 'owner_plan_id', 'owner_revision'}]
            for use in uses:
                self.assertEqual((payload['plan_id'], payload['revision']),
                                 (use['owner_plan_id'], use['owner_revision']))
            matrix.resolved = sorted({(use['kind'], use['definition_id'], path) for use in uses})
            matrix.operation_id = 'existing-bound-chain'
            matrix.add_binding(payload['plan_id'], 1, path)
            files = matrix.render()
            origins = codec.strict_json_loads(files[ORIGINS])
            origins['revision'] = 2
            origins['frozen_legacy_refs'] = [matrix.owned('source_manifest', 'sources/manifest.json')]
            files[ORIGINS] = encoded(origins)
            receipt_path = records.BASE + 'commits/existing-bound-chain.json'
            receipt = codec.strict_json_loads(files[receipt_path])
            receipt['authority'] = deepcopy(commit.validate_local(self.root, original)['receipt']['authority'])
            for row in receipt['targets']:
                if row['path'] == ORIGINS:
                    row['after_digest'] = row['projection_digest'] = codec.raw_digest(files[ORIGINS])
            files[receipt_path] = encoded(receipt)
            catalog = codec.strict_json_loads(files[CATALOG])
            catalog['revision'] = 2
            catalog['origins_ref'] = projection.reference(ORIGINS, files[ORIGINS])
            catalog['scope_heads'][0]['receipt_ref'] = projection.reference(receipt_path, files[receipt_path])
            files[CATALOG] = encoded(catalog)
            for name, raw in files.items():
                if name.startswith(records.BASE):
                    target = self.root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(raw)
            joined = matrix.join()
            joined.master['master']['tasks'][0].update(status=task_status,
                acceptance=['Keep this existing acceptance'],
                history=[{'action': 'completed' if task_status == 'done' else 'created'}])
            for document in (joined.back, joined.gameplay):
                document[0]['status'] = task_status
            for name, document in (('master', joined.master), ('back', joined.back), ('gameplay', joined.gameplay)):
                target = self.root / adoption.TRIPLET[name]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(encoded(document))
            # Validate the complete seed through the unmodified formal reader
            # before exercising compensation review or any fault injection.
            records.published_bundle(self.root,
                task_join=adoption._task_context(adoption.Snapshot(self.root)))
        catalog = codec.strict_json_loads((self.root / CATALOG).read_bytes())
        self.original = journal.read_operation(self.root, operation_id='OP-one')
        self.comp_request = {'schema_version': journal.COMPENSATION_REQUEST, 'producer': 'compensation',
            'operation_id': 'COMP-one', 'compensates': compensation.relation_for(self.original),
            'selection': {'plan_ref': catalog['scope_heads'][0]['plan_refs'][0],
                'binding_ref': next(iter(catalog['scope_heads'][0]['binding_refs']), None)},
            'reason': 'Retain the current formally published meaning and resolve the exact stale claim'}
        return self.comp_request

    def approve(self, *, delivery=None):
        request = self.comp_request
        delivery_kwargs = {} if delivery is None else {'compensation_delivery': delivery}
        result = adoption.prepare_review(self.root, operation_id=request['operation_id'],
                                        request_ref=self.fx.request_ref(request), **delivery_kwargs)
        self.assertTrue(result['semantic_execution_required'])
        self.assertIsNone(result['machine_preservation'])
        completed(self.root, request['operation_id'], thread_id='compensation-independent-' + request['operation_id'],
                  delivery=delivery)
        request['host_review_ref'] = adoption.complete_review(self.root,
            operation_id=request['operation_id'])['host_review_ref']

    def allocate(self):
        request = self.comp_request
        adoption.prepare(self.root, operation_id=request['operation_id'], request_ref=self.fx.request_ref(request))
        adoption.reserve(self.root, operation_id=request['operation_id'])
        return journal.read_operation(self.root, operation_id=request['operation_id'])

    def test_complete_reviewed_compensation_uses_new_id_and_shared_commit(self):
        self.baseline()
        old_raw = (self.root / journal._operation_ref('OP-one')).read_bytes()
        self.approve()
        envelope = self.allocate()
        self.assertEqual(journal.COMPENSATION_SCHEMA, envelope['schema_version'])
        self.assertNotIn('material', envelope['frozen']['request'])
        self.assertEqual(2, envelope['frozen']['allocations']['plan_revision'])
        result = commit.recover(self.root, operation_id='COMP-one')
        self.assertTrue(result['published'])
        self.assertEqual(old_raw, (self.root / journal._operation_ref('OP-one')).read_bytes())
        self.assertEqual('COMP-one', journal.operation_state_graph(self.root)['resolved_by']['OP-one'])
        self.assertEqual([], journal.active_operation_inventory(self.root))
        self.assertTrue(commit.read_committed(self.root)['formal_adoption'])
        before = self.fx.files()
        self.assertTrue(commit.recover(self.root, operation_id='COMP-one')['noop'])
        self.assertEqual(before, self.fx.files())

    def test_compensation_source_support_rewrite_or_delete_cannot_advance_verified_phase(self):
        for kind in ('source_rewrite', 'source_delete', 'support_rewrite', 'support_delete'):
            for timing in ('before_install', 'after_install', 'aba'):
                with self.subTest(kind=kind, timing=timing):
                    self.baseline(bound=True)
                    self.approve(); self.allocate()
                    commit.execute(self.root, operation_id='COMP-one', stage='apply')
                    assert_boundary_drift_rejected(self, 'COMP-one',
                        lambda: commit.execute(self.root, operation_id='COMP-one', stage='verify'), kind, timing)

    def test_real_owner_partial_pending_with_task_status_authority_drift_is_precisely_resolved(self, *, delivery=materials.MULTIVIEW_DELIVERY):
        # Only the initial bound formal chain is a synthetic seed. Each tested
        # pending marker, intent, fault, status progression and successor uses
        # the actual review/storage/commit owners, without rewriting old state.
        self.baseline(bound=True, task_status='pending')
        self.approve(delivery=delivery); self.allocate()
        commit.recover(self.root, operation_id='COMP-one')
        def next_request(operation_id, previous):
            catalog = codec.strict_json_loads((self.root / CATALOG).read_bytes())
            head = catalog['scope_heads'][0]
            self.comp_request = {'schema_version': journal.COMPENSATION_REQUEST, 'producer': 'compensation',
                'operation_id': operation_id, 'compensates': compensation.relation_for(previous),
                'selection': {'plan_ref': head['plan_refs'][0], 'binding_ref': head['binding_refs'][0]},
                'reason': 'Preserve current Task progress and resolve this exact partial pending claim'}
        next_request('COMP-pending', journal.read_operation(self.root, operation_id='COMP-one'))
        self.approve(delivery=delivery); self.allocate()
        with self.fail_at('after_target:0'), self.assertRaises(codec.CodecError):
            commit.execute(self.root, operation_id='COMP-pending', stage='apply')
        pending = journal.read_operation(self.root, operation_id='COMP-pending')
        intent_ref, marker_ref = commit._paths('COMP-pending')
        preserved = {name: (self.root / name).read_bytes()
                     for name in (journal._operation_ref('COMP-pending'), intent_ref, marker_ref,
                                  pending['frozen']['targets'][0]['path'])}
        self.assertEqual('intent', commit.validate_local(self.root, pending)['phase'])
        index_ref = self.root / journal.OPERATION_STORE / 'pending.json'
        def index_row_raw(data):
            text = data.decode('utf-8')
            position = text.index('"operation_id": "COMP-pending"')
            start = text.rfind('{', 0, position)
            row, end = json.JSONDecoder().raw_decode(text, start)
            self.assertEqual('COMP-pending', row['operation_id'])
            return text[start:end].encode('utf-8')
        old_index_raw = index_row_raw(index_ref.read_bytes())
        for label, name in adoption.TRIPLET.items():
            value = codec.strict_json_loads((self.root / name).read_bytes())
            row = value['master']['tasks'][0] if label == 'master' else value[0]
            self.assertEqual('pending', row['status'])
            row['status'] = 'done'
            (self.root / name).write_bytes(encoded(value))
        tasks = {name: (self.root / name).read_bytes() for name in adoption.TRIPLET.values()}
        origins = codec.strict_json_loads((self.root / ORIGINS).read_bytes())
        with self.assertRaises(codec.CodecError) as caught:
            commit.inspect_recovery(self.root, operation_id='COMP-pending')
        self.assertEqual(codec.ReasonCode.INPUT_STALE, caught.exception.diagnostic.reason_code)
        next_request('COMP-successor', pending)
        self.approve(delivery=delivery)
        subject = review.read_subject(self.root, 'COMP-successor')
        packet = review.model_packet(self.root, subject)
        self.assertEqual({'OP-one', 'COMP-one', 'COMP-pending', 'COMP-successor'},
                         {frame['operation_id'] for frame in packet['materials']['frames']})
        self.assertEqual(review.COMPENSATION_PROOF, self.comp_request['host_review_ref']['schema_version'])
        for name, data in tasks.items():
            root_rows = [row for row in packet['roles']['files']
                        if row['subject_digest'] == codec.canonical_digest(subject) and row['path'] == name]
            self.assertEqual([codec.raw_digest(data)], [row['document_ref'] for row in root_rows])
        self.allocate()
        self.assertNotIn('COMP-pending', journal.operation_state_graph(self.root)['resolved_by'])
        commit.recover(self.root, operation_id='COMP-successor')
        self.assertEqual(preserved, {name: (self.root / name).read_bytes() for name in preserved})
        self.assertEqual(tasks, {name: (self.root / name).read_bytes() for name in tasks})
        self.assertEqual(old_index_raw, index_row_raw(index_ref.read_bytes()))
        after = codec.strict_json_loads((self.root / ORIGINS).read_bytes())
        self.assertEqual(origins['frozen_legacy_refs'], after['frozen_legacy_refs'])
        self.assertEqual([row['source_refs'] for row in origins['tasks']], [row['source_refs'] for row in after['tasks']])
        self.assertEqual('COMP-successor', journal.operation_state_graph(self.root)['resolved_by']['COMP-pending'])
        self.assertEqual('COMP-successor', commit.recover(self.root, operation_id='COMP-pending')['resolved_by'])
        self.assertTrue(commit.read_committed(self.root)['formal_adoption'])

    def test_stale_pending_bound_task_done_history_sources_and_later_edits_are_retained(self):
        self.baseline(bound=True)
        self.assertIn('OP-one', [row['operation_id'] for row in journal.active_operation_inventory(self.root)])
        with self.assertRaises(codec.CodecError):
            commit.read_committed(self.root)
        tasks = {name: (self.root / name).read_bytes() for name in adoption.TRIPLET.values()}
        origins_before = codec.strict_json_loads((self.root / ORIGINS).read_bytes())
        old = (self.root / journal._operation_ref('OP-one')).read_bytes()
        old_index_row = codec.strict_json_loads((self.root / journal.OPERATION_STORE / 'pending.json').read_bytes())['operations'][0]
        self.approve()
        self.allocate()
        self.assertNotIn('OP-one', journal.operation_state_graph(self.root)['resolved_by'])
        with self.assertRaises(codec.CodecError):
            commit.read_committed(self.root)
        commit.recover(self.root, operation_id='COMP-one')
        self.assertEqual(tasks, {name: (self.root / name).read_bytes() for name in adoption.TRIPLET.values()})
        origins_after = codec.strict_json_loads((self.root / ORIGINS).read_bytes())
        self.assertEqual(origins_before['tasks'][0]['source_refs'], origins_after['tasks'][0]['source_refs'])
        self.assertEqual(origins_before['frozen_legacy_refs'], origins_after['frozen_legacy_refs'])
        self.assertEqual(2, origins_after['tasks'][0]['binding_refs'][0]['revision'])
        self.assertEqual(old, (self.root / journal._operation_ref('OP-one')).read_bytes())
        index = codec.strict_json_loads((self.root / journal.OPERATION_STORE / 'pending.json').read_bytes())
        self.assertIn(old_index_row, index['operations'])
        self.assertEqual('COMP-one', commit.inspect_recovery(self.root, operation_id='OP-one')['resolved_by'])
        result = commit.recover(self.root, operation_id='OP-one')
        self.assertFalse(result['published'])
        self.assertFalse(result['formal_adoption'])
        self.assertEqual('COMP-one', result['resolved_by'])
        self.assertTrue(commit.read_committed(self.root)['formal_adoption'])

    def test_missing_or_tampered_review_current_before_and_original_identity_reject_before_writes(self):
        for kind in ('missing_review', 'old_id', 'frozen', 'raw', 'effects', 'current_before', 'review_support'):
            with self.subTest(kind=kind):
                self.baseline(bound=True)
                if kind != 'missing_review':
                    self.approve()
                if kind in ('old_id', 'frozen', 'raw', 'effects'):
                    key = {'old_id': 'operation_id', 'frozen': 'frozen_digest',
                        'raw': 'request_raw_digest', 'effects': 'effects_digest'}[kind]
                    self.comp_request['compensates'][key] = 'wrong' if kind == 'old_id' else 'sha256:' + '0' * 64
                elif kind == 'current_before':
                    name = adoption.TRIPLET['master']
                    value = codec.strict_json_loads((self.root / name).read_bytes())
                    value['master']['tasks'][0]['acceptance'].append('A later edit must remain')
                    (self.root / name).write_bytes(encoded(value))
                elif kind == 'review_support':
                    (self.root / review.location('COMP-one') / 'w/prompt.txt').write_bytes(b'changed')
                request_ref = self.fx.request_ref(self.comp_request)
                before = self.fx.files()
                with self.assertRaises(codec.CodecError):
                    adoption.prepare(self.root, operation_id='COMP-one', request_ref=request_ref)
                self.assertEqual(before, self.fx.files())

    def test_closed_versioned_protocol_rejects_booleans_unknown_fields_versions_and_self_compensation(self):
        self.baseline()
        for field, value in (('approved', True), ('producer', 'adoption'), ('schema_version', 'unknown.v3')):
            request = deepcopy(self.comp_request)
            request[field] = value
            with self.subTest(field=field), self.assertRaises(codec.CodecError):
                journal.validate_operation_request(request)
        self.comp_request['compensates']['operation_id'] = 'COMP-one'
        with self.assertRaises(codec.CodecError):
            compensation.build(self.root, self.comp_request)

    def test_dropped_b_mapping_or_new_unpublished_semantic_selection_is_rejected(self):
        self.baseline(bound=True)
        request = deepcopy(self.comp_request)
        request['selection']['binding_ref'] = None
        with self.assertRaises(codec.CodecError):
            compensation.build(self.root, request)
        ref = request['selection']['plan_ref']
        payload = codec.strict_json_loads((self.root / ref['path']).read_bytes())
        payload['revision'] = 99
        path = records._managed_path(payload)
        (self.root / path).write_bytes(encoded(payload))
        request['selection']['plan_ref'] = projection.reference(path, encoded(payload))
        with self.assertRaises(codec.CodecError):
            compensation.build(self.root, request)

    def test_other_overlapping_pending_claim_is_never_exempt(self):
        self.baseline(bound=True)
        self.approve()
        old = deepcopy(self.original)
        request = deepcopy(old['frozen']['request'])
        request['operation_id'] = 'OTHER-pending'
        frozen = deepcopy(old['frozen'])
        frozen['request'] = request
        value = journal.draft_operation(self.root, request_raw=encoded(request), frozen=frozen, state='reserved')
        journal._operation_write(self.root, value, journal.operation_inventory(self.root))
        request_ref = self.fx.request_ref(self.comp_request)
        before = self.fx.files()
        with self.assertRaises(codec.CodecError) as caught:
            adoption.prepare(self.root, operation_id='COMP-one', request_ref=request_ref)
        self.assertEqual(codec.ReasonCode.PENDING, caught.exception.diagnostic.reason_code)
        # Only normal empty lock metadata may have appeared.
        self.assertEqual({k: v for k, v in before.items() if '/locks/' not in k},
                         {k: v for k, v in self.fx.files().items() if '/locks/' not in k})

    def test_fault_after_each_actual_compensation_write_restarts_and_preserves_old_history(self):
        for boundary in ('pending_durable', 'intent_durable', 'after_target:0', 'after_target:1',
                         'after_target:2', 'receipt_durable', 'catalog_replaced', 'before_pending_cleanup'):
            with self.subTest(boundary=boundary):
                self.baseline(bound=True)
                self.approve()
                self.allocate()
                old = (self.root / journal._operation_ref('OP-one')).read_bytes()
                with self.fail_at(boundary), self.assertRaises(codec.CodecError):
                    commit.recover(self.root, operation_id='COMP-one')
                with self.assertRaises(codec.CodecError):
                    commit.read_committed(self.root)
                self.assertTrue(commit.recover(self.root, operation_id='COMP-one')['published'])
                self.assertEqual(old, (self.root / journal._operation_ref('OP-one')).read_bytes())
                self.assertEqual('COMP-one', journal.operation_state_graph(self.root)['resolved_by']['OP-one'])

    def test_unknown_target_post_edit_retains_pending_and_all_unknown_bytes(self):
        self.baseline(bound=True)
        self.approve()
        envelope = self.allocate()
        with self.fail_at('after_target:0'), self.assertRaises(codec.CodecError):
            commit.execute(self.root, operation_id='COMP-one', stage='apply')
        name = envelope['frozen']['targets'][0]['path']
        (self.root / name).write_bytes(b'{"external":"keep exactly"}')
        before = self.fx.files()
        with self.assertRaises(codec.CodecError):
            commit.recover(self.root, operation_id='COMP-one')
        self.assertEqual(before, self.fx.files())
        self.assertNotIn('OP-one', journal.operation_state_graph(self.root)['resolved_by'])

    def test_wrong_scope_and_fabricated_terminal_never_release_original_pending(self):
        for kind in ('scope', 'terminal'):
            with self.subTest(kind=kind):
                self.baseline(bound=True)
                self.approve()
                envelope = self.allocate()
                if kind == 'scope':
                    frozen = deepcopy(envelope['frozen'])
                    frozen['scope_ids'] = ['self:declared']
                    with self.assertRaises(codec.CodecError):
                        compensation.authorize_claim(self.root, 'COMP-one', frozen)
                else:
                    commit.execute(self.root, operation_id='COMP-one', stage='apply')
                    commit.execute(self.root, operation_id='COMP-one', stage='verify')
                    intent = commit.validate_local(self.root, envelope)
                    # A caller-written phase is not proof of catalog publication.
                    forged = commit._seal({**intent, 'phase': 'complete'})
                    (self.root / commit._paths('COMP-one')[0]).write_bytes(encoded(forged))
                    (self.root / commit._paths('COMP-one')[1]).unlink()
                self.assertNotIn('OP-one', journal.operation_state_graph(self.root)['resolved_by'])
                with self.assertRaises(codec.CodecError):
                    commit.read_committed(self.root)

    def test_conflicting_successor_claim_is_rejected_without_releasing_either(self):
        self.baseline(bound=True)
        self.approve()
        envelope = self.allocate()
        frozen = deepcopy(envelope['frozen'])
        request = deepcopy(frozen['request'])
        request['operation_id'] = 'COMP-conflict'
        frozen['request'] = request
        value = journal.draft_operation(self.root, request_raw=encoded(request), frozen=frozen, state='reserved')
        journal._operation_write(self.root, value, journal.operation_inventory(self.root))
        with self.assertRaises(codec.CodecError):
            journal.operation_state_graph(self.root)
        with self.assertRaises(codec.CodecError):
            commit.read_committed(self.root)

    def test_short_writer_is_absent_during_real_semantic_and_bundle_checks(self):
        self.baseline()
        self.approve()
        self.allocate()
        entered = []
        original = records.validate_compensation_sources
        def probe(*args, **kwargs):
            with scope.scope_guard(self.root, ['unrelated:probe'], prepare_under_lease=lambda: entered.append(True)):
                pass
            return original(*args, **kwargs)
        with patch.object(records, 'validate_compensation_sources', side_effect=probe):
            self.assertTrue(commit.recover(self.root, operation_id='COMP-one')['published'])
        self.assertGreaterEqual(len(entered), 2)

    def material_subject(self):
        self.baseline(bound=True)
        adoption.prepare_review(self.root, operation_id='COMP-one', request_ref=self.fx.request_ref(self.comp_request))
        return review.read_subject(self.root, 'COMP-one')

    def test_materials_preserve_full_subject_and_every_semantic_byte_with_exact_runner_wire(self):
        from openai_isolated_model_runner import workspace_payload
        import _b_route_compact_literal as compact
        with patch.object(materials, '_produce_transport_roundtrip', wraps=materials._produce_transport_roundtrip) as encoded, \
             patch.object(materials, 'read_prompt', side_effect=AssertionError('cold decode in warm render')):
            subject = self.material_subject()
        accounts = [call.kwargs['work'] for call in encoded.call_args_list
                    if type(call.args[0]) is dict and call.args[0].get('schema_version') == materials.PACKET]
        self.assertEqual(len(accounts), 1)  # One genuine local canonical producer, no cold witness API.
        self.assertTrue(all(account is accounts[0] for account in accounts))
        self.assertEqual(100000000, accounts[0].limit)
        self.assertGreaterEqual(accounts[0].remaining, 0)
        home = review.path(self.root, review.location('COMP-one'))
        before = {name: base64.b64decode(data, validate=True) for name, data in subject['current_files'].items()}
        subject_raw = (home / 'subject.json').read_bytes()
        packet = review.model_packet(self.root, subject)
        self.assertEqual(subject_raw, review.raw(subject))
        root_digest = codec.canonical_digest(subject)
        rows = {row['path']: row for row in packet['roles']['files'] if row['subject_digest'] == root_digest}
        self.assertEqual(set(before), set(rows))
        documents = {row['raw_digest']: row for row in packet['materials']['documents']}
        self.assertEqual(len(documents), len(packet['materials']['documents']))
        for name, data in before.items():
            self.assertEqual((codec.raw_digest(data), len(data)), (rows[name]['raw_digest'], rows[name]['raw_bytes']))
            if set(rows[name]['roles']) & materials.SEMANTIC_ROLES:
                self.assertEqual(data, documents[rows[name]['document_ref']]['text'].encode('utf-8'))
        for frame in packet['materials']['frames']:
            expected = subject if frame['operation_id'] == 'COMP-one' else review.read_subject(self.root, frame['operation_id'])
            self.assertEqual({name: value for name, value in expected.items() if name != 'current_files'},
                             frame['semantic_fields'])
        prompt = (home / 'w/prompt.txt').read_text(encoding='utf-8')
        self.assertEqual(packet, materials.read_prompt(prompt))
        self.assertEqual((home / 'request.txt').read_text(encoding='utf-8'),
                         workspace_payload(home / 'w', prompt_path=home / 'w/prompt.txt', output_path=home / 'w/output.json'))
        self.assertEqual(before, {name: (self.root / name).read_bytes() for name in before})
        self.assertEqual(subject_raw, (home / 'subject.json').read_bytes())

    def test_material_roles_reject_unknown_missing_conflicting_and_unverified_support(self):
        subject = self.material_subject()
        verified = review.verified_historical_support(self.root, subject['original_operation'])
        support = next(iter(verified['files']))
        for kind in ('unknown_path', 'missing_support', 'unverified_bytes', 'unknown_role', 'missing_role'):
            changed, owner = deepcopy(subject), deepcopy(verified)
            if kind == 'unknown_path':
                changed['current_files']['logs/ci/b-route-adoption-reviews/fake/execution.json'] = base64.b64encode(b'{}').decode()
            elif kind == 'missing_support':
                del changed['current_files'][support]
            elif kind == 'unverified_bytes':
                owner['files'][support] += b'\n'
            elif kind == 'unknown_role':
                owner['roles'][support] = 'host:unknown'
            else:
                del owner['roles'][support]
            with self.subTest(kind=kind), self.assertRaises(codec.CodecError):
                # Pure material adapter negatives; all business/receipt gates
                # were exercised by the actual owner before these mutations.
                materials.derive(changed, verify_review=lambda original: owner, checks=review.obligations(changed))
        # A test-only conflicting adapter label cannot hide a real semantic
        # record. Production's saved owner never derives this extra label.
        owner = deepcopy(verified)
        owner['files'][CATALOG] = base64.b64decode(subject['current_files'][CATALOG], validate=True)
        owner['roles'][CATALOG] = 'host:prompt'
        packet = materials.derive(subject, verify_review=lambda original: owner, checks=review.obligations(subject))
        row = next(row for row in packet['roles']['files'] if row['path'] == CATALOG)
        self.assertIn('host:prompt', row['roles'])
        self.assertIn('semantic:catalog_graph', row['roles'])
        self.assertEqual(row['raw_digest'], row['document_ref'])

    def test_complete_warm_frame_rejects_long_single_line_utf8_instruction_at_original_byte_cap(self):
        import _b_route_compact_literal as compact
        subject = self.material_subject()
        packet = review.model_packet(self.root, subject)
        original = review.raw(packet)
        # Four UTF-8 bytes per scalar reaches the actual frame byte ceiling
        # without spending the ASCII instruction's fourfold character budget.
        # Every actual packet field/source remains present and unchanged.
        instruction = '\U00010000' * (compact.MAX_ENCODED_BYTES // 4 + 1)
        self.assertNotIn('\n', instruction)
        self.assertGreater(len(instruction.encode('utf-8')), compact.MAX_ENCODED_BYTES)
        work = compact._EncodingWork()
        self.assertEqual(100000000, work.limit)
        with self.assertRaises(codec.CodecError) as caught:
            materials.render(instruction, packet, work=work)
        self.assertIn('Compact encoded bytes exceed ', caught.exception.diagnostic.actual)
        self.assertGreaterEqual(work.remaining, 0)
        self.assertEqual(original, review.raw(packet))

    def test_materials_bind_task_history_sources_effects_and_every_scope_field(self):
        subject = self.material_subject()
        original = review.model_packet(self.root, subject)
        owner = review.verified_historical_support(self.root, subject['original_operation'])
        for kind in ('task_acceptance', 'task_history', 'current_scope', 'old_scope', 'new_scope', 'source_bytes', 'effects'):
            changed = deepcopy(subject)
            if kind.startswith('task_'):
                name = adoption.TRIPLET['master']
                value = codec.strict_json_loads(base64.b64decode(changed['current_files'][name]))
                field = 'acceptance' if kind == 'task_acceptance' else 'history'
                value['master']['tasks'][0][field] = []
                changed['current_files'][name] = base64.b64encode(encoded(value)).decode()
            elif kind == 'source_bytes':
                changed['current_files']['sources/input.md'] = base64.b64encode(b'Lost source meaning\n').decode()
            elif kind == 'effects':
                changed['original_effects'] = []
            elif kind == 'new_scope':
                changed['preview']['scope_ids'] = []
            else:
                changed['preview']['compensation']['current_scope_ids' if kind == 'current_scope' else 'old_scope_ids'] = []
            with self.subTest(kind=kind):
                try:
                    packet = materials.derive(changed, verify_review=lambda original: owner, checks=review.obligations(changed))
                except codec.CodecError:
                    continue
                self.assertNotEqual(original['materials'], packet['materials'])
                self.assertNotEqual(original['presentation'], packet['presentation'])

    def test_legacy_compensation_proof_uses_exact_original_request_and_never_new_packet(self):
        subject = self.material_subject()
        home = review.path(self.root, review.location('COMP-one'))
        # Explicit synthetic archive under today's policy, not a claim that an
        # old-policy historical proof has become current or was real history.
        legacy = {'w/prompt.txt': review._legacy_prompt(subject).encode('utf-8'),
                  'w/schema.json': review.raw(review._legacy_verdict_schema(subject)),
                  'request.txt': review._legacy_request_payload(subject).encode('utf-8')}
        for name, data in legacy.items():
            (home / name).write_bytes(data)
        completed(self.root, 'COMP-one', legacy=True, thread_id='synthetic-legacy-review')
        evidence = review._legacy_verify_semantic(self.root, subject)
        proof = {'schema_version': review.PROOF, 'operation_id': 'COMP-one',
            'subject_digest': codec.canonical_digest(subject), 'policy_identity': subject['policy_identity'],
            'mode': 'semantic', 'evidence': evidence, 'files': [
                {'path': review.location('COMP-one') + '/' + name, 'schema_version': 'raw.bytes.v1',
                 'raw_digest': codec.raw_digest((home / name).read_bytes())} for name in review.support_names('semantic')]}
        request = deepcopy(self.comp_request)
        request['host_review_ref'] = review.seal(self.root, 'COMP-one', proof)
        with patch.object(review, 'model_packet', side_effect=AssertionError('v1 must use exact original owner')):
            self.assertEqual(subject, review.verify_saved(self.root, request)[0])
        for name in ('w/prompt.txt', 'w/schema.json', 'request.txt', 'execution.json', 'w/output.json', 'subject.json'):
            target, data = home / name, (home / name).read_bytes()
            try:
                target.write_bytes(data + b' ' if name != 'subject.json' else data.replace(
                    subject['policy_identity'].encode(), b'sha256:' + b'0' * 64))
                with self.subTest(name=name), self.assertRaises((codec.CodecError, ValueError)):
                    review.verify_saved(self.root, request)
            finally:
                target.write_bytes(data)
        self.assertEqual(review.PROOF, request['host_review_ref']['schema_version'])

    def test_versioned_review_rejects_material_wire_schema_output_and_proof_identity_drift(self):
        self.baseline(bound=True)
        self.approve()
        subject = review.read_subject(self.root, 'COMP-one')
        packet = review.model_packet(self.root, subject)
        home = review.path(self.root, review.location('COMP-one'))
        _, _, verdict = completed(self.root, 'COMP-one', thread_id='compensation-independent-COMP-one')
        for name in ('materials.json', 'roles.json', 'presentation.json', 'w/prompt.txt', 'request.txt',
                     'w/schema.json', 'execution.json', 'w/output.json'):
            target, data = home / name, (home / name).read_bytes()
            try:
                target.write_bytes(data + b' ')
                with self.subTest(name=name), self.assertRaises((codec.CodecError, ValueError)):
                    review.verify_saved(self.root, self.comp_request)
            finally:
                target.write_bytes(data)
        for field in ('schema_version', 'subject_digest', 'materials_digest', 'roles_digest', 'presentation_digest', 'claim'):
            value = deepcopy(verdict)
            value[field] = 'changed'
            with self.subTest(field=field), self.assertRaises(codec.CodecError):
                review.check_verdict(subject, value, root=self.root, packet=packet)
        proof_path = home / 'review.json'
        saved = proof_path.read_bytes()
        for field in ('schema_version', 'mode', 'claim', 'request_raw_digest', 'unknown'):
            value = codec.strict_json_loads(saved)
            value[field] = 'unknown'
            data = review.raw(value)
            try:
                proof_path.write_bytes(data)
                request = deepcopy(self.comp_request)
                request['host_review_ref']['raw_digest'] = codec.raw_digest(data)
                with self.subTest(proof_field=field), self.assertRaises(codec.CodecError):
                    review.verify_saved(self.root, request)
            finally:
                proof_path.write_bytes(saved)

    def test_material_proof_pins_same_validated_support_buffers_before_short_writer(self):
        self.material_subject()
        completed(self.root, 'COMP-one', thread_id='compensation-independent-COMP-one')
        home = review.path(self.root, review.location('COMP-one'))
        original = review.verify_semantic
        execution_raw = (home / 'execution.json').read_bytes()
        captured = []
        def drift_after_validation(*args, **kwargs):
            evidence = original(*args, **kwargs)
            captured.append(dict(kwargs['buffers']))
            (home / 'execution.json').write_bytes(execution_raw + b' ')
            return evidence
        before = journal.operation_inventory(self.root)
        with patch.object(review, 'verify_semantic', side_effect=drift_after_validation), self.assertRaises(codec.CodecError):
            adoption.complete_review(self.root, operation_id='COMP-one')
        self.assertEqual(execution_raw, captured[0]['execution.json'])
        self.assertEqual(execution_raw + b' ', (home / 'execution.json').read_bytes())
        self.assertFalse((home / 'review.json').exists())
        self.assertEqual(before, journal.operation_inventory(self.root))

    def test_material_packet_closed_shapes_and_resource_limits_fail_before_review_persistence(self):
        import _b_route_compact_literal as compact
        import _capability_input_integrity as capacity
        import _codex_app_server as appserver
        subject = self.material_subject()
        packet = review.model_packet(self.root, subject)
        prompt = (self.root / review.location('COMP-one') / 'w/prompt.txt').read_text(encoding='utf-8')
        header, body = prompt.split('\n', 1)
        mixed = compact.dumps({'schema_version': 'newrouge.b-route-complete-materials-wire.v2',
                               'materials': packet}, schema=compact.ATOM_SCHEMA)
        for kind, changed in (
                ('unknown_marker', prompt.replace(materials.DELIVERY, 'unknown.delivery', 1)),
                ('legacy_marker', prompt.replace(materials.DELIVERY, 'newrouge.b-route-complete-materials-wire.v2', 1)),
                ('mixed_decoder', header.replace(compact.RESIDUAL_SCHEMA, compact.CURRENT_SCHEMA, 1) + '\n' + body),
                ('unknown_body_version', header + '\n' + body.replace(compact.RESIDUAL_SCHEMA, 'unknown.literal', 1)),
                ('mixed_body_delivery', header + '\n' + mixed),
                ('noncanonical_body', prompt + ' '),
                ('truncated_body', prompt[:-1])):
            with self.subTest(delivery=kind), self.assertRaises(codec.CodecError):
                materials.read_prompt(changed)
        for operation in ('render', 'read'):
            work = compact._EncodingWork()
            work.spend(work.remaining - 1)
            with self.subTest(exhausted_account=operation), self.assertRaises(codec.CodecError):
                if operation == 'render':
                    materials.render('Review every complete semantic material.', packet, work=work)
                else:
                    materials.read_prompt(prompt, work=work)
            self.assertLessEqual(work.remaining, 1)
        for kind in ('unknown_packet', 'unknown_role', 'missing_document', 'missing_frame', 'digest', 'cycle'):
            changed = deepcopy(packet)
            if kind == 'unknown_packet':
                changed['unknown'] = True
            elif kind == 'unknown_role':
                changed['roles']['files'][0]['roles'] = ['host:unknown']
            elif kind == 'missing_document':
                changed['materials']['documents'].pop()
            elif kind == 'missing_frame':
                changed['materials']['frames'].pop()
            elif kind == 'digest':
                changed['presentation']['full_subject_digest'] = 'sha256:' + '0' * 64
            else:
                frame = changed['materials']['frames'][0]
                frame['previous_subject'] = frame['subject_digest']
            if kind in ('unknown_role', 'missing_document', 'missing_frame', 'cycle'):
                changed['presentation']['materials_digest'] = codec.canonical_digest(changed['materials'])
                changed['presentation']['roles_digest'] = codec.canonical_digest(changed['roles'])
            with self.subTest(kind=kind), self.assertRaises(codec.CodecError):
                materials.validate(changed)
        self.assertEqual((1048576, 96000, 33554432, 100000000),
                         (capacity.CODEX_MAX_TURN_BYTES, capacity.DEFAULT_MAX_INPUT_TOKENS,
                          appserver.MAX_TRANSCRIPT_BYTES, compact.MAX_ENCODING_WORK))
        _, pins = review.policy_observations()
        for name in ('_b_route_compensation_review_materials.py', '_b_route_planning_wire.py',
                     '_b_route_compact_literal.py', '_mvg_lossless_context.py', '_mvg_evidence_transport.py',
                     '_mvg_structured_context.py', '_capability_input_integrity.py'):
            self.assertIn(str(Path(review.__file__).resolve().with_name(name)), pins)
        self.baseline(bound=True)
        old_operation = (self.root / journal._operation_ref('OP-one')).read_bytes()
        home = self.root / review.location('COMP-one')
        with patch.dict(os.environ, {'SC_CAPABILITY_MAX_INPUT_TOKENS': '1'}), self.assertRaises(codec.CodecError):
            adoption.prepare_review(self.root, operation_id='COMP-one', request_ref=self.fx.request_ref(self.comp_request))
        self.assertFalse(home.exists())
        self.assertEqual(old_operation, (self.root / journal._operation_ref('OP-one')).read_bytes())
        self.assertEqual(['OP-one'], [row['operation_id'] for row in journal.operation_inventory(self.root)])

    def test_direct_and_dev_cli_share_producer_and_resolution_read_contract(self):
        import b_route_adoption as cli
        import dev_cli
        self.baseline()
        self.approve()
        self.allocate()
        commit.recover(self.root, operation_id='COMP-one')
        for entry, prefix in ((cli.main, []), (dev_cli.main, ['b-route-adoption'])):
            output = io.StringIO()
            with redirect_stdout(output):
                code = entry([*prefix, '--root', str(self.root), '--stage', 'read', '--operation-id', 'OP-one'])
            self.assertEqual(0, code, output.getvalue())
            value = json.loads(output.getvalue())
            self.assertEqual('COMP-one', value['resolved_by'])
            self.assertFalse(value['published'])
            self.assertFalse(value['formal_adoption'])


    def test_scoped_published_ancestor_recovery_preserves_global_pending_and_unknown_claims(self):
        # Smaller real owner regression for the applied-origins/catalog-last gap.
        # A12 separately retains the partial-pending/Task-done/four-frame case.
        self.baseline(bound=True)
        self.approve(delivery=materials.MULTIVIEW_DELIVERY)
        self.allocate()
        commit.recover(self.root, operation_id='COMP-one')
        previous = journal.read_operation(self.root, operation_id='COMP-one')
        catalog = codec.strict_json_loads((self.root / CATALOG).read_bytes())
        head = catalog['scope_heads'][0]
        self.comp_request = {'schema_version': journal.COMPENSATION_REQUEST, 'producer': 'compensation',
            'operation_id': 'COMP-scoped', 'compensates': compensation.relation_for(previous),
            'selection': {'plan_ref': head['plan_refs'][0], 'binding_ref': head['binding_refs'][0]},
            'reason': 'Retain actual reviewed existing semantics across owned after-images'}
        self.approve(delivery=materials.MULTIVIEW_DELIVERY)
        envelope = self.allocate()
        old_paths = [name for identity in ('OP-one', 'COMP-one') for name in
            (journal._operation_ref(identity), commit._paths(identity)[0], records.BASE + 'commits/' + identity + '.json')]
        history = {name: (self.root / name).read_bytes() for name in old_paths}
        index = self.root / journal.OPERATION_STORE / 'pending.json'
        index_before = index.read_bytes()
        commit.execute(self.root, operation_id='COMP-scoped', stage='apply')
        self.assertEqual('applied', commit.validate_local(self.root, envelope)['phase'])
        # Global classification must remain conservative; only this recovery
        # gets a scoped permission rooted in its reviewed exact before image.
        graph = journal.operation_state_graph(self.root)
        self.assertNotIn('COMP-one', graph['terminals'])
        self.assertNotIn('OP-one', graph['resolved_by'])
        self.assertIn('OP-one', {row['operation_id'] for row in journal.active_operation_inventory(self.root)})
        with self.assertRaises(codec.CodecError):
            records.published_bundle(self.root,
                task_join=adoption._task_context(adoption.Snapshot(self.root)))
        origins = self.root / ORIGINS
        owned_after = origins.read_bytes()
        try:
            origins.write_bytes(owned_after + b' ')
            before = self.fx.files()
            with self.assertRaises(codec.CodecError):
                commit.recover(self.root, operation_id='COMP-scoped')
            self.assertEqual(before, self.fx.files())
        finally:
            origins.write_bytes(owned_after)
        receipt = self.root / (records.BASE + 'commits/COMP-one.json')
        original_receipt = receipt.read_bytes()
        try:
            receipt.write_bytes(original_receipt + b' ')
            before = self.fx.files()
            with self.assertRaises(codec.CodecError):
                commit.recover(self.root, operation_id='COMP-scoped')
            self.assertEqual(before, self.fx.files())
        finally:
            receipt.write_bytes(original_receipt)
        self.assertTrue(commit.recover(self.root, operation_id='COMP-scoped')['published'])
        self.assertEqual(history, {name: (self.root / name).read_bytes() for name in history})
        self.assertEqual(index_before, index.read_bytes())
        self.assertEqual([], journal.active_operation_inventory(self.root))
        # An unrelated overlapping pending claim remains pending even beside
        # a complete published chain. Recovery must not repair/delete its bytes.
        original = journal.read_operation(self.root, operation_id='OP-one')
        request = deepcopy(original['frozen']['request'])
        request['operation_id'] = 'OTHER-ancestor'
        frozen = deepcopy(original['frozen'])
        frozen['request'] = request
        unknown = journal.draft_operation(self.root, request_raw=encoded(request), frozen=frozen, state='reserved')
        journal._operation_write(self.root, unknown, journal.operation_inventory(self.root))
        before = self.fx.files()
        with self.assertRaises(codec.CodecError) as caught:
            commit.recover(self.root, operation_id='COMP-scoped')
        self.assertEqual(codec.ReasonCode.PENDING, caught.exception.diagnostic.reason_code)
        self.assertEqual('OTHER-ancestor', caught.exception.diagnostic.entity_id)
        self.assertEqual(before, self.fx.files())

    def test_protected_read_blocks_related_pending_under_valid_catalog_label_alias(self):
        self.baseline(bound=True)
        def stable_files():
            return {name: raw for name, raw in self.fx.files().items() if '/locks/' not in name}
        for label in ('scope-main', 'scope-masked'):
            catalog = codec.strict_json_loads((self.root / CATALOG).read_bytes())
            old_label = catalog['scope_heads'][0]['scope_id']
            receipt_path = catalog['scope_heads'][0]['receipt_ref']['path']
            receipt = codec.strict_json_loads((self.root / receipt_path).read_bytes())
            receipt['scopes'] = [label if value == old_label else value for value in receipt['scopes']]
            receipt['result']['scope_ids'] = [label if value == old_label else value for value in receipt['result']['scope_ids']]
            (self.root / receipt_path).write_bytes(encoded(receipt))
            catalog['scope_heads'][0]['scope_id'] = label
            catalog['scope_heads'][0]['receipt_ref'] = projection.reference(receipt_path, encoded(receipt))
            (self.root / CATALOG).write_bytes(encoded(catalog))
            public = records.published_bundle(self.root,
                task_join=adoption._task_context(adoption.Snapshot(self.root)))
            self.assertEqual([label], public['scope_ids'])
            self.assertNotIn('_protection_scope_ids', public)
            before = stable_files()
            with self.subTest(label=label), self.assertRaises(codec.CodecError) as caught:
                commit.read_committed(self.root, scope_ids=[label])
            self.assertEqual(codec.ReasonCode.PENDING, caught.exception.diagnostic.reason_code)
            self.assertEqual('OP-one', caught.exception.diagnostic.entity_id)
            self.assertEqual(before, stable_files())
        self.approve(); self.allocate()
        with self.fail_at('after_target:0'), self.assertRaises(codec.CodecError):
            commit.execute(self.root, operation_id='COMP-one', stage='apply')
        before = stable_files()
        with self.assertRaises(codec.CodecError) as caught:
            commit.read_committed(self.root)
        self.assertEqual(codec.ReasonCode.PENDING, caught.exception.diagnostic.reason_code)
        self.assertEqual('COMP-one', caught.exception.diagnostic.entity_id)
        self.assertEqual(before, stable_files())
        # Unknown bytes remain unknown; neither a valid label nor local intent
        # supplies permission to read or repair a changed formal target.
        catalog = codec.strict_json_loads((self.root / CATALOG).read_bytes())
        plan = self.root / catalog['scope_heads'][0]['plan_refs'][0]['path']
        plan.write_bytes(plan.read_bytes() + b' ')
        before = stable_files()
        with self.assertRaises(codec.CodecError):
            commit.read_committed(self.root)
        self.assertEqual(before, stable_files())


    def test_protected_read_allows_unrelated_scope_despite_retained_other_pending_and_task_progress(self):
        from test_b_route_records import mixed_scope_bytes
        self.baseline(bound=True)
        old = {name: (self.root / name).read_bytes() for name in
            (journal._operation_ref('OP-one'), commit._paths('OP-one')[0],
             journal.OPERATION_STORE + '/pending.json')}
        # An independent valid formal fixture gives q its own unrelated plan
        # and state definition. OP-one remains the real original local claim.
        for name, raw in mixed_scope_bytes().items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        self.assertIn('OP-one', {row['operation_id'] for row in journal.active_operation_inventory(self.root)})
        before = commit.read_committed(self.root, scope_ids=['scope-q'])
        self.assertTrue(before['formal_adoption'])
        self.assertNotIn('_protection_scope_ids', before)
        master = self.root / adoption.TRIPLET['master']
        value = codec.strict_json_loads(master.read_bytes())
        value['master']['tasks'][0]['history'].append({'action': 'unrelated-debug-progress'})
        master.write_bytes(encoded(value))
        after = commit.read_committed(self.root, scope_ids=['scope-q'])
        self.assertEqual(before['input_set_digest'], after['input_set_digest'])
        self.assertEqual(old, {name: (self.root / name).read_bytes() for name in old})




@unittest.skipUnless(os.name == 'nt', 'Actual Windows process compensation recovery')
class WindowsCompensationTests(CommitFixture, unittest.TestCase):
    baseline = CompensationTests.baseline
    approve = CompensationTests.approve
    allocate = CompensationTests.allocate

    def child(self, mode):
        helper = Path(__file__).parent / 'fixtures/b_route_commit_process.py'
        dependencies = [value for value in sys.path if 'site-packages' in value or 'story22-tokenizer-deps' in value]
        environment = dict(os.environ, ADOPTION_TEST_TEMP=str(self.root.parent))
        return subprocess.run([sys.executable, '-I', '-S', '-B', str(helper), str(self.root), mode,
            json.dumps(dependencies)], capture_output=True, timeout=120, env=environment,
            creationflags=subprocess.CREATE_NO_WINDOW)

    def deny_delete(self, name):
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        api.CreateFileW.restype = wintypes.HANDLE
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        api.CloseHandle.restype = wintypes.BOOL
        handle = api.CreateFileW(str(self.root / name), 0x80000000, 3, None, 3, 0x80, None)
        self.assertNotEqual(ctypes.c_void_p(-1).value, handle)
        return api, handle

    def test_process_exit_and_restart_derive_resolution_from_retained_formal_evidence(self):
        self.baseline(bound=True)
        self.approve()
        self.allocate()
        result = self.child('compensate-crash-after-target')
        self.assertEqual(73, result.returncode, result.stderr)
        result = self.child('compensate-recover')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(json.loads(result.stdout)['published'])
        result = self.child('resolved-inspect')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual('COMP-one', json.loads(result.stdout)['resolved_by'])

    def test_actual_windows_origins_sharing_refusal_and_release_resume(self):
        self.baseline(bound=True)
        self.approve()
        self.allocate()
        original = (self.root / ORIGINS).read_bytes()
        api, handle = self.deny_delete(ORIGINS)
        try:
            result = self.child('compensate-recover')
            self.assertEqual(2, result.returncode, result.stderr)
            self.assertEqual(original, (self.root / ORIGINS).read_bytes())
            self.assertNotIn('OP-one', journal.operation_state_graph(self.root)['resolved_by'])
            with self.assertRaises(codec.CodecError):
                commit.read_committed(self.root)
        finally:
            api.CloseHandle(handle)
        result = self.child('compensate-recover')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(json.loads(result.stdout)['published'])

    def test_actual_windows_pending_delete_refusal_retains_block_until_cleanup(self):
        self.baseline(bound=True)
        self.approve()
        self.allocate()
        commit.execute(self.root, operation_id='COMP-one', stage='apply')
        commit.execute(self.root, operation_id='COMP-one', stage='verify')
        pending = commit._paths('COMP-one')[1]
        api, handle = self.deny_delete(pending)
        try:
            result = self.child('compensate-recover')
            self.assertEqual(2, result.returncode, result.stderr)
            self.assertTrue((self.root / pending).exists())
            self.assertNotIn('OP-one', journal.operation_state_graph(self.root)['resolved_by'])
        finally:
            api.CloseHandle(handle)
        self.assertEqual(0, self.child('compensate-recover').returncode)
        self.assertEqual('COMP-one', journal.operation_state_graph(self.root)['resolved_by']['OP-one'])
