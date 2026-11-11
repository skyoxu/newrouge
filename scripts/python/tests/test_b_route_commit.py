"""Actual commit/storage/locks; only native eligibility uses a synthetic capture.

No provider, original qualification, native worker or model is invoked. Windows
child tests use only the fixed owned-TEMP commit fixture, never Python -c.
"""
from copy import deepcopy
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_adoption as adoption
import _b_route_codec as codec
import _b_route_commit as commit
import _b_route_records as records
import _planning_apply_journal as journal
import test_b_route_adoption as composition
from test_b_route_records import POLICY, ORIGINS, CATALOG, MatrixFixture, encoded


class CommitFixture:
    def fixture(self):
        fx = composition.AdoptionCompositionTests('test_prepare_replay_reserve_freezes_allocations_and_writes_no_formal_target')
        fx.setUp()
        (fx.root / '.synthetic-story27-fixture').write_bytes(b'owned synthetic commit fixture\n')
        self.fx, self.root = fx, fx.root
        return fx

    def relocate_proofs(self, request):
        fixture, _ = self.fx.cases[request['material']['run_id']]
        # Native admission remains explicitly synthetic; the subsequent real
        # activity/coordinator locks use owned local directories and state.
        run_id = request['material']['run_id']
        relative = 'logs/ci/mvg-planning/' + run_id + '/run.json'
        store = self.root / 'logs/ci/mvg-recovery'
        store.mkdir(parents=True, exist_ok=True)
        state = encoded({'schema_version': 'synthetic.native-lock-fixture.v1', 'run_id': run_id,
                         'recovery': {'store': str(store)}})
        fixture.artifacts[relative] = state
        target = self.root / relative; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(state)
        mapping = {name: 'logs/proof/' + name.removeprefix('evidence/')
                   for name in list(fixture.artifacts) if name.startswith('evidence/')}
        for old, new in mapping.items():
            data = fixture.artifacts.pop(old)
            fixture.artifacts[new] = data
            target = self.root / new
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            (self.root / old).unlink()
        def move(value):
            if isinstance(value, dict):
                return {key: move(item) for key, item in value.items()}
            if isinstance(value, list):
                return [move(item) for item in value]
            if isinstance(value, str):
                for old, new in mapping.items():
                    if value == old or value.startswith(old + '#'):
                        return new + value[len(old):]
            return value
        return move(request)

    def prepare(self, *, existing_policy=False, empty_triplet=False):
        self.fixture()
        request = self.relocate_proofs(deepcopy(self.fx.request))
        fixture, _ = self.fx.cases['one']
        if empty_triplet:
            for name, value in [('.taskmaster/tasks/tasks.json', {'master': {'tasks': []}}),
                                ('.taskmaster/tasks/tasks_back.json', []),
                                ('.taskmaster/tasks/tasks_gameplay.json', [])]:
                target = self.root / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(encoded(value))
        policy = deepcopy(fixture.policy)
        before = None
        if existing_policy:
            target = self.root / POLICY
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(encoded(policy))
            before = codec.raw_digest(target.read_bytes())
            policy['policy_revision'] = 2
        origins = {'schema_version': 'newrouge.b-route-origins.v1', 'origins_id': 'task-origins',
                   'revision': 1, 'tasks': [], 'frozen_legacy_refs': []}
        for path, payload, image in [(POLICY, policy, before), (ORIGINS, origins, None)]:
            request['material']['target_templates'].append({'path_template': path,
                'schema_version': payload['schema_version'], 'before_raw_digest': image,
                'after_payload': payload, 'verification_mode': 'immutable_bytes'})
        self.request = request
        self.fx.prepare(request)
        with patch.object(adoption, 'capture_completed', self.fx.synthetic_capture):
            adoption.reserve(self.root, operation_id='OP-one')
        return journal.read_operation(self.root, operation_id='OP-one')

    def step(self, stage, operation_id='OP-one'):
        with patch.object(adoption, 'capture_completed', self.fx.synthetic_capture):
            return commit.execute(self.root, operation_id=operation_id, stage=stage)

    def publish(self):
        self.step('apply'); self.step('verify')
        return self.step('publish')

    def formal(self, root=None):
        root = self.root if root is None else root
        base = root / records.BASE
        return {path.relative_to(root).as_posix(): path.read_bytes() for path in base.rglob('*') if path.is_file()}

    def fail_at(self, label):
        def failure(actual):
            if actual == label:
                raise OSError('synthetic interruption at fixed commit boundary')
        return patch.object(commit, '_checkpoint', side_effect=failure)

class PublicCommitTests(CommitFixture, unittest.TestCase):
    def test_bootstrap_accepts_complete_empty_triplet_without_creating_task_or_witness(self):
        self.prepare(empty_triplet=True)
        before = {name: (self.root / name).read_bytes() for name in adoption.TRIPLET.values()}
        self.publish()
        self.assertEqual(before, {name: (self.root / name).read_bytes() for name in before})
        self.assertTrue(commit.read_committed(self.root)['formal_adoption'])
        self.assertFalse((self.root / 'logs/ci/chapter5').exists())

    def test_bootstrap_apply_verify_publish_and_replay_noop_preserve_formal_bytes(self):
        envelope = self.prepare()
        self.assertFalse((self.root / '.taskmaster').exists())
        for stage in ('apply', 'verify'):
            result = self.step(stage)
            self.assertFalse(result['formal_adoption'])
            self.assertFalse((self.root / records.CATALOG_PATH).exists())
        result = self.step('publish')
        self.assertTrue(result['published'])
        before = self.formal()
        with patch.object(commit, '_write', side_effect=AssertionError('No completed side effect may be rewritten')):
            for stage in ('apply', 'verify', 'publish'):
                result = self.step(stage)
                self.assertTrue(result['noop'])
        self.assertEqual(before, self.formal())
        self.assertEqual(1, len(journal.operation_inventory(self.root)))
        self.assertEqual([], journal.active_operation_inventory(self.root))
        self.assertEqual(envelope, journal.read_operation(self.root, operation_id='OP-one'))
        self.assertEqual([], codec.strict_json_loads(before[ORIGINS])['tasks'])
        self.assertEqual('A', codec.strict_json_loads(before[POLICY])['switch_boundary']['default_route'])
        self.assertFalse((self.root / '.taskmaster').exists())

    def test_after_target_is_skipped_and_unknown_edit_is_never_overwritten(self):
        envelope = self.prepare()
        with self.fail_at('after_target:0'), self.assertRaises(codec.CodecError):
            self.step('apply')
        plan = self.root / envelope['frozen']['targets'][0]['path']
        original = plan.read_bytes()
        calls = []
        write = commit._write
        def observed(root, relative, raw):
            calls.append(relative)
            return write(root, relative, raw)
        with patch.object(commit, '_write', side_effect=observed):
            self.step('apply')
        self.assertNotIn(plan.relative_to(self.root).as_posix(), calls)
        self.assertEqual(original, plan.read_bytes())
        plan.write_bytes(b'{"human":"preserve"}')
        with self.assertRaises(codec.CodecError): self.step('verify')
        self.assertEqual(b'{"human":"preserve"}', plan.read_bytes())
        self.assertFalse((self.root / records.CATALOG_PATH).exists())

    def test_related_source_drift_blocks_unfinished_stage_and_keeps_journal(self):
        self.prepare(); self.step('apply')
        intent = self.root / commit._paths('OP-one')[0]
        before = intent.read_bytes()
        (self.root / 'sources/input.md').write_bytes(b'Changed source definition')
        with self.assertRaises(codec.CodecError): self.step('verify')
        self.assertEqual(before, intent.read_bytes())
        self.assertTrue((self.root / commit._paths('OP-one')[1]).is_file())

    def test_receipt_is_not_publication_and_reader_rejects_unpublished_state(self):
        self.prepare(); self.step('apply'); self.step('verify')
        self.assertTrue((self.root / records.BASE / 'commits/OP-one.json').is_file())
        with self.assertRaises(codec.CodecError): commit.read_committed(self.root)
        self.assertFalse((self.root / records.CATALOG_PATH).exists())

    def test_complete_catalog_payload_is_durable_before_last_replace(self):
        self.prepare(); self.step('apply'); self.step('verify')
        observed = []
        def checkpoint(name):
            if name == 'catalog_intent_durable':
                value = commit.validate_local(self.root, journal.read_operation(self.root, operation_id='OP-one'))
                self.assertEqual('publishing', value['phase'])
                self.assertIsNotNone(value['catalog_after'])
                self.assertFalse((self.root / records.CATALOG_PATH).exists())
                observed.append(value['catalog_after'])
        with patch.object(commit, '_checkpoint', side_effect=checkpoint): self.step('publish')
        self.assertEqual([commit._encode((self.root / records.CATALOG_PATH).read_bytes())], observed)

    def test_fault_matrix_keeps_active_pending_and_blocks_consumption(self):
        phases = [('pending_durable', 'apply'), ('intent_durable', 'apply'),
                  ('before_target:0', 'apply'), ('after_target:0', 'apply'),
                  ('after_target:1', 'apply'), ('after_target:2', 'apply'), ('applied_durable', 'apply'),
                  ('receipt_durable', 'verify'), ('verified_durable', 'verify'),
                  ('catalog_intent_durable', 'publish'), ('catalog_replaced', 'publish'),
                  ('published_durable', 'publish'), ('before_pending_cleanup', 'publish')]
        for label, stage in phases:
            with self.subTest(boundary=label):
                self.prepare()
                if stage in ('verify', 'publish'): self.step('apply')
                if stage == 'publish': self.step('verify')
                with self.fail_at(label), self.assertRaises(codec.CodecError): self.step(stage)
                self.assertTrue((self.root / commit._paths('OP-one')[1]).is_file())
                self.assertEqual(1, len(journal.active_operation_inventory(self.root)))
                with self.assertRaises(codec.CodecError): commit.read_committed(self.root)

    def test_failed_pending_unlink_blocks_even_after_complete_intent(self):
        self.prepare(); self.step('apply'); self.step('verify')
        pending = self.root / commit._paths('OP-one')[1]
        unlink = Path.unlink
        def fail_marker(path, *args, **kwargs):
            if path == pending: raise PermissionError('synthetic sharing refusal')
            return unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', fail_marker), self.assertRaises(codec.CodecError): self.step('publish')
        self.assertEqual('complete', commit.validate_local(self.root,
            journal.read_operation(self.root, operation_id='OP-one'))['phase'])
        with self.assertRaises(codec.CodecError): commit.read_committed(self.root)
        before = self.formal()
        self.step('publish')  # Explicit owned cleanup, not automatic recovery.
        self.assertEqual(before, self.formal())
        self.assertTrue(commit.read_committed(self.root)['formal_adoption'])

    def test_clone_without_logs_requires_actual_receipt_sealed_proof_closure(self):
        self.prepare(); self.publish()
        clone = Path(tempfile.mkdtemp(prefix='nr27-clone-', dir=os.environ.get('ADOPTION_TEST_TEMP')))
        for name in ('docs', 'sources'):
            shutil.copytree(self.root / name, clone / name)
        self.assertFalse((clone / 'logs').exists())
        result = commit.read_committed(clone)
        self.assertTrue(result['formal_adoption'])
        self.assertFalse(result['runtime_verified'])
        # Default candidate validation remains strict and still requires logs.
        self.assertFalse(records.validate_bundle({}, root=clone).ok)
        receipt_path = records.BASE + 'commits/OP-one.json'
        raw = (clone / receipt_path).read_bytes()
        receipt = codec.strict_json_loads(raw)
        receipt['authority'] = [row for row in receipt['authority'] if not row['path'].startswith('logs/')]
        (clone / receipt_path).write_bytes(encoded(receipt))
        catalog = codec.strict_json_loads((clone / records.CATALOG_PATH).read_bytes())
        for head in catalog['scope_heads']:
            head['receipt_ref']['digest'] = codec.raw_digest(encoded(receipt))
        (clone / records.CATALOG_PATH).write_bytes(encoded(catalog))
        with self.assertRaises(codec.CodecError): commit.read_committed(clone)

    def test_catalog_reread_and_related_source_changes_invalidate_consumption(self):
        self.prepare(); self.publish()
        original = (self.root / records.CATALOG_PATH).read_bytes()
        def edit(name):
            if name == 'reader_before_catalog_close':
                value = codec.strict_json_loads(original); value['revision'] += 1
                (self.root / records.CATALOG_PATH).write_bytes(encoded(value))
        with patch.object(commit, '_checkpoint', side_effect=edit), self.assertRaises(codec.CodecError):
            commit.read_committed(self.root)
        (self.root / records.CATALOG_PATH).write_bytes(original)
        (self.root / 'sources/input.md').write_bytes(b'Changed relevant source')
        with self.assertRaises(codec.CodecError): commit.read_committed(self.root)

    def test_unrelated_publication_preserves_selected_semantic_identity(self):
        envelope = self.prepare(); self.publish()
        selected = envelope['frozen']['scope_ids']
        before = commit.read_committed(self.root, scope_ids=selected)['input_set_digest']
        request = self.relocate_proofs(self.fx.case('two', 'OP-two'))
        self.fx.prepare(request)
        with patch.object(adoption, 'capture_completed', self.fx.synthetic_capture):
            adoption.reserve(self.root, operation_id='OP-two')
        for stage in ('apply', 'verify', 'publish'): self.step(stage, 'OP-two')
        self.assertEqual(before, commit.read_committed(self.root, scope_ids=selected)['input_set_digest'])

    def test_unknown_intent_version_and_extra_namespace_are_not_repaired(self):
        self.prepare(); self.step('apply')
        path = self.root / commit._paths('OP-one')[0]
        original = path.read_bytes(); value = codec.strict_json_loads(original)
        value['schema_version'] = 'newrouge.b-route-commit-intent.v999'
        path.write_bytes(encoded(value))
        with self.assertRaises(codec.CodecError): self.step('verify')
        self.assertEqual(encoded(value), path.read_bytes())
        path.write_bytes(original)
        extra = path.with_name('unknown.json'); extra.write_bytes(b'{}')
        with self.assertRaises(codec.CodecError): self.step('verify')
        self.assertEqual(b'{}', extra.read_bytes())

    def test_resigned_intent_cannot_delete_reviewed_required_source_observation(self):
        self.prepare(); self.step('apply')
        path = self.root / commit._paths('OP-one')[0]
        value = codec.strict_json_loads(path.read_bytes())
        del value['files'][str(self.root / 'sources/input.md')]
        changed = encoded(commit._seal(value)); path.write_bytes(changed)
        with self.assertRaises(codec.CodecError): self.step('verify')
        self.assertEqual(changed, path.read_bytes())

    def test_resealed_frozen_allocation_cannot_bypass_independent_review_on_resume(self):
        envelope = self.prepare(); self.step('apply')
        intent = commit.validate_local(self.root, envelope)
        changed = deepcopy(envelope)
        changed['frozen']['allocations']['plan_revision'] += 1
        changed['frozen_digest'] = codec.canonical_digest(changed['frozen'])
        before = self.formal()
        with self.assertRaises(codec.CodecError) as failure:
            commit._verify_observations(self.root, changed, intent)
        self.assertEqual(codec.ReasonCode.INPUT_STALE, failure.exception.diagnostic.reason_code)
        self.assertEqual(before, self.formal())

    def test_resigned_complete_phase_cannot_claim_an_unpublished_catalog_image(self):
        envelope = self.prepare(); self.publish()
        original_formal = self.formal()
        path = self.root / commit._paths('OP-one')[0]
        value = codec.strict_json_loads(path.read_bytes())
        catalog = codec.strict_json_loads((self.root / records.CATALOG_PATH).read_bytes())
        value['publication_base'] = commit._encode(encoded(catalog))
        catalog['revision'] += 1
        value['catalog_after'] = commit._encode(encoded(catalog))
        path.write_bytes(encoded(commit._seal(value)))
        # The current formal chain is valid and still selects the same receipt;
        # the invented later publication was nevertheless never made visible.
        self.assertFalse(commit.terminal_valid(self.root, envelope))
        self.assertEqual(1, len(journal.active_operation_inventory(self.root)))
        with self.assertRaises(codec.CodecError): commit.read_committed(self.root)
        self.assertEqual(original_formal, self.formal())

    def test_missing_pending_marker_alone_does_not_complete_an_applied_operation(self):
        self.prepare(); self.step('apply')
        marker = self.root / commit._paths('OP-one')[1]
        marker.unlink()
        self.assertEqual(1, len(journal.active_operation_inventory(self.root)))
        with self.assertRaises(codec.CodecError): commit.read_committed(self.root)
        self.assertFalse((self.root / records.CATALOG_PATH).exists())

    def test_unrelated_publication_between_verify_and_publish_is_preserved(self):
        self.prepare(); self.publish()
        def reserve(name, operation):
            request = self.relocate_proofs(self.fx.case(name, operation))
            self.fx.prepare(request)
            with patch.object(adoption, 'capture_completed', self.fx.synthetic_capture):
                adoption.reserve(self.root, operation_id=operation)
        reserve('two', 'OP-two')
        self.step('apply', 'OP-two'); self.step('verify', 'OP-two')
        reserve('three', 'OP-three')
        for stage in ('apply', 'verify', 'publish'): self.step(stage, 'OP-three')
        before = codec.strict_json_loads((self.root / records.CATALOG_PATH).read_bytes())
        unrelated = {row['scope_id']: row for row in before['scope_heads']}
        second = journal.read_operation(self.root, operation_id='OP-two')
        self.step('publish', 'OP-two')
        after = codec.strict_json_loads((self.root / records.CATALOG_PATH).read_bytes())
        heads = {row['scope_id']: row for row in after['scope_heads']}
        for scope, head in unrelated.items():
            if scope not in second['frozen']['scope_ids']:
                self.assertEqual(head, heads[scope])
        self.assertEqual(before['revision'] + 1, after['revision'])
        intent = commit.validate_local(self.root, second)
        self.assertTrue(intent['catalog_attempts'])

    def test_public_cli_dispatches_commit_and_preserves_adoption_stage_flags(self):
        import b_route_adoption as cli
        self.prepare()
        with patch.object(adoption, 'capture_completed', self.fx.synthetic_capture):
            for stage in ('apply', 'verify', 'publish', 'read'):
                output = io.StringIO()
                with redirect_stdout(output):
                    code = cli.main(['--root', str(self.root), '--stage', stage, '--operation-id', 'OP-one'])
                self.assertEqual(0, code, output.getvalue())
                value = json.loads(output.getvalue())
                self.assertIs(stage in ('publish', 'read'), value['formal_adoption'])
                self.assertFalse(value['readiness']); self.assertFalse(value['runtime_verified'])
        output = io.StringIO()
        with redirect_stdout(output): cli.main(['--root', str(self.root), '--stage', 'inspect', '--operation-id', 'OP-one'])
        self.assertFalse(json.loads(output.getvalue())['formal_adoption'])

    def test_replan_publishes_all_old_heads_and_preserves_original_revision(self):
        first = self.prepare(); self.publish()
        old_target = first['frozen']['targets'][0]
        old_path = old_target['path']; old_raw = (self.root / old_path).read_bytes()
        previous = {'path': old_path, 'schema_version': adoption.PLAN, 'raw_digest': codec.raw_digest(old_raw)}
        fixture, _ = self.fx.cases['one']
        fixture.artifacts[old_path] = old_raw  # Explicit synthetic prepared dependency.
        request = deepcopy(self.request)
        request['operation_id'] = 'OP-replan'; request.pop('host_review_ref', None)
        request['material']['target_templates'] = request['material']['target_templates'][:1]
        alignment = request['material']['identity_alignment']
        alignment['plan'] = {'mode': 'reuse', 'plan_ref': previous}
        for family in ('requirements', 'flows'):
            for row in alignment[family]:
                row.update(mode='reuse', stable_id=first['frozen']['allocations'][family][row['candidate_id']],
                           evidence_ref=previous)
        flow_id = next(iter(first['frozen']['allocations']['flows'].values()))
        lineage = request['material']['target_templates'][0]['after_payload']['lineage']
        lineage.update(previous_plan_ref=commit.projection.reference(old_path, old_raw),
            change_summary='Explicit unchanged semantic replan', identity_alignment=[{
                'kind': 'flow', 'previous_id': flow_id, 'current_id': flow_id,
                'rationale': alignment['flows'][0]['rationale']}])
        self.fx.prepare(request)
        with patch.object(adoption, 'capture_completed', self.fx.synthetic_capture):
            adoption.reserve(self.root, operation_id='OP-replan')
        replan = journal.read_operation(self.root, operation_id='OP-replan')
        self.assertLess(first['frozen']['allocations']['plan_revision'], replan['frozen']['allocations']['plan_revision'])
        self.assertLessEqual(set(first['frozen']['scope_ids']), set(replan['frozen']['scope_ids']))
        for stage in ('apply', 'verify'): self.step(stage, 'OP-replan')
        with self.fail_at('before_pending_cleanup'), self.assertRaises(codec.CodecError):
            self.step('publish', 'OP-replan')
        self.assertEqual(['OP-replan'], [row['operation_id'] for row in journal.active_operation_inventory(self.root)])
        with self.assertRaises(codec.CodecError): commit.read_committed(self.root)
        self.step('publish', 'OP-replan')
        catalog = codec.strict_json_loads((self.root / records.CATALOG_PATH).read_bytes())
        for head in catalog['scope_heads']:
            self.assertEqual('OP-replan', head['receipt_ref']['entity_id'])
        self.assertEqual(old_raw, (self.root / old_path).read_bytes())
        self.assertEqual(first, journal.read_operation(self.root, operation_id='OP-one'))
        self.assertEqual([], journal.active_operation_inventory(self.root))
        with patch.object(commit, '_write', side_effect=AssertionError('Prior complete publication must remain no-op')):
            self.assertTrue(self.step('publish', 'OP-one')['noop'])


class CommittedTaskProjectionTests(unittest.TestCase):
    def test_existing_declared_task_projection_allows_status_but_rejects_definition_edits(self):
        root = Path(tempfile.mkdtemp(prefix='nr27-tasks-', dir=os.environ.get('ADOPTION_TEST_TEMP')))
        fixture = MatrixFixture(); fixture.add_binding()
        output = fixture.render(); joined = fixture.join()
        documents = {'.taskmaster/tasks/tasks.json': joined.master,
            '.taskmaster/tasks/tasks_back.json': joined.back, '.taskmaster/tasks/tasks_gameplay.json': joined.gameplay}
        receipt_path = records.BASE + 'commits/operation-1.json'
        receipt = codec.strict_json_loads(output[receipt_path])
        for name, value in documents.items():
            data = encoded(value); output[name] = data
            row = {'path': name, 'before_digest': codec.raw_digest(data), 'after_digest': codec.raw_digest(data),
                   'verification_mode': 'task_definition_projection', 'codec_version': codec.PROJECTION_CODEC,
                   'projection_digest': records.task_document_digest(name, data)}
            receipt['targets'].append(row); receipt['result']['target_paths'].append(name)
            receipt['authority'].append({key: row[key] for key in ('path', 'before_digest', 'after_digest')})
        output[receipt_path] = encoded(receipt)
        catalog = codec.strict_json_loads(output[CATALOG])
        for head in catalog['scope_heads']: head['receipt_ref']['digest'] = codec.raw_digest(output[receipt_path])
        output[CATALOG] = encoded(catalog)
        for name, data in output.items():
            target = root / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        before = commit.read_committed(root)['input_set_digest']
        documents['.taskmaster/tasks/tasks.json']['master']['tasks'][0]['status'] = 'done'
        documents['.taskmaster/tasks/tasks_back.json'][0]['status'] = 'done'
        for name, value in documents.items(): (root / name).write_bytes(encoded(value))
        self.assertEqual(before, commit.read_committed(root)['input_set_digest'])
        documents['.taskmaster/tasks/tasks_back.json'][0]['acceptance'] = ['Changed acceptance']
        (root / '.taskmaster/tasks/tasks_back.json').write_bytes(encoded(documents['.taskmaster/tasks/tasks_back.json']))
        with self.assertRaises(codec.CodecError): commit.read_committed(root)


@unittest.skipUnless(os.name == 'nt', 'Required actual Windows commit evidence')
class WindowsCommitTests(CommitFixture, unittest.TestCase):
    def test_windows_sharing_refusal_preserves_before_and_partial_pending(self):
        import ctypes
        from ctypes import wintypes
        envelope = self.prepare(existing_policy=True)
        raw = (self.root / POLICY).read_bytes()
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
            wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        api.CreateFileW.restype = wintypes.HANDLE
        api.CloseHandle.argtypes = [wintypes.HANDLE]; api.CloseHandle.restype = wintypes.BOOL
        handle = api.CreateFileW(str(self.root / POLICY), 0x80000000, 1, None, 3, 0x80, None)
        self.assertNotEqual(ctypes.c_void_p(-1).value, handle)
        try:
            with self.assertRaises(codec.CodecError): self.step('apply')
            self.assertEqual(raw, (self.root / POLICY).read_bytes())
            self.assertEqual(1, len(journal.active_operation_inventory(self.root)))
        finally:
            api.CloseHandle(handle)
        self.step('apply'); self.step('verify'); self.step('publish')
        self.assertTrue(commit.read_committed(self.root)['formal_adoption'])

    def child(self, mode):
        helper = Path(__file__).parent / 'fixtures/b_route_commit_process.py'
        dependencies = [value for value in sys.path if 'site-packages' in value or 'story22-tokenizer-deps' in value]
        environment = dict(os.environ)
        environment.setdefault('ADOPTION_TEST_TEMP', str(self.root.parent))
        return subprocess.run([sys.executable, '-I', '-S', '-B', str(helper), str(self.root), mode,
                               json.dumps(dependencies)], capture_output=True, timeout=90, env=environment,
                              creationflags=subprocess.CREATE_NO_WINDOW)

    def test_real_process_crash_restart_preserves_partial_and_postpublish_pending(self):
        self.prepare()
        # The fresh child reconstructs only the explicit synthetic capture seam;
        # real commit admission, journal, scope leases and IO run in that child.
        result = self.child('crash-after-target')
        self.assertEqual(73, result.returncode, result.stderr)
        self.assertEqual(1, len(journal.active_operation_inventory(self.root)))
        self.assertFalse((self.root / records.CATALOG_PATH).exists())
        result = self.child('apply')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(0, self.child('verify').returncode)
        self.assertEqual(73, self.child('crash-after-catalog').returncode)
        result = self.child('read')
        self.assertEqual(2, result.returncode, result.stdout)
        before = self.formal()
        result = self.child('publish')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, self.formal())
        self.assertEqual(0, self.child('read').returncode)
