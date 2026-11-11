"""Synthetic storage boundaries plus real Windows write-lease regressions."""
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SCRIPTS), str(SCRIPTS.parent / 'sc')]
import _b_route_operation_scope as scope
import _b_route_codec as codec
from _mvg_capability_checkpoint import coordinator_lock
from _planning_apply_journal import create_journal
from _planning_skill_common import atomic_json, load_json


class OperationScopeTests(unittest.TestCase):
    def setUp(self):
        # Intentionally retained on success or failure for Root-owned evidence.
        # The fixture never creates or deletes product-checkout sq-* directories.
        self.root = Path(tempfile.mkdtemp(prefix='newrouge-operation-scope-')).resolve()
        self.calls = []
        self.inventory = patch.object(scope, '_operation_inventory', return_value=[])
        self.inventory_mock = self.inventory.start()
        self.addCleanup(self.inventory.stop)

    def guard(self, scopes=('task:1',), **kwargs):
        return scope.scope_guard(self.root, scopes,
            prepare_under_lease=kwargs.pop('prepare_under_lease', lambda: self.calls.append('called')),
            **kwargs)

    def pending(self, identity, scopes):
        return {'operation_id': identity, 'state': 'prepared', 'frozen': {'scope_ids': list(scopes)}}

    def assert_blocked(self, reason, scopes=('task:1',), **kwargs):
        self.calls.clear()
        with self.assertRaises(codec.CodecError) as caught:
            with self.guard(scopes, **kwargs):
                self.fail('Blocked guard yielded')
        self.assertEqual(reason, caught.exception.diagnostic.reason_code)
        self.assertEqual([], self.calls)

    def owner(self, kind, run_id):
        base = 'mvg' if kind == 'mvg-rebind' else kind
        return {'kind': kind, 'run_id': run_id,
                'journal_path': scope._ROOTS[base] + '/' + run_id + '/apply-journal.json'}

    def legacy(self, kind, run_id='old', *, completed=False):
        prefix = scope._ROOTS[kind] + '/' + run_id
        run_dir = self.root / prefix
        run_dir.mkdir(parents=True)
        state = {'schema_version': scope._SCHEMAS[kind], 'run_id': run_id,
                 'phase': 'prepared', 'applied': False}
        if kind == 'capabilities':
            target = self.root / 'docs/planning/semantic-topology/capabilities.v1.json'
            payload = {'capabilities': []}
            digest = codec.raw_digest((json.dumps(payload, ensure_ascii=False, indent=2) + '\n').encode())
            targets = {target: payload}
            result = {'status': 'applied', 'run_id': run_id, 'capabilities_sha256': digest}
            state['applied_capabilities_sha256'] = digest
        else:
            manifest = 'docs/testing/mvg/synthetic.json'
            trace = 'docs/testing/mvg/planning/' + run_id + '.json'
            payload = {'flows': []}
            digest = codec.raw_digest((json.dumps(payload, ensure_ascii=False, indent=2) + '\n').encode())
            targets = {self.root / manifest: payload, self.root / trace:
                {'applied_manifest_path': manifest, 'applied_manifest_sha256': digest}}
            result = {'status': 'applied', 'manifest_path': manifest, 'manifest_sha256': digest,
                      'trace_path': trace}
            state.update(manifest_path=manifest, applied_manifest_sha256=digest)
        path = run_dir / 'apply-journal.json'
        journal = create_journal(self.root, path, targets, {}, result)
        if completed:
            journal['status'] = 'complete'
            state.update(phase='applied', applied=True)
            atomic_json(path, journal)
            atomic_json(run_dir / 'apply-summary.json', result)
        atomic_json(run_dir / 'run.json', state)
        return path, state, journal

    def probe(self, mode, scopes=()):
        value = subprocess.run([sys.executable, '-I', '-S', '-B', __file__, '--probe', mode,
            str(self.root), json.dumps(list(scopes))], capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        self.assertEqual(value.returncode, 0, value.stderr)
        return value.stdout.strip()

    def test_resource_scopes_preserve_types_and_windows_alias_identity(self):
        self.assertEqual(scope.resource_scopes(target_paths=['Docs/A/../B.json']),
                         scope.resource_scopes(target_paths=['docs/b.json']))
        original = scope.resource_scopes(plan_ids=['Plan-A'], requirement_ids=['RQ-1'],
            flow_ids=['flow-1'], task_ids=[1, 2, 1])
        self.assertEqual(original, tuple(sorted(set(original))))
        self.assertNotEqual(scope.resource_scopes(plan_ids=['Plan-A']),
                            scope.resource_scopes(plan_ids=['plan-a']))
        for bad in (True, '1', 0):
            with self.subTest(task=bad), self.assertRaises(codec.CodecError):
                scope.resource_scopes(task_ids=[bad])
        with self.assertRaises(codec.CodecError):
            scope.resource_scopes(target_paths=['../outside'])

    def test_disjoint_pending_allowed_overlap_and_unknown_block_before_callback(self):
        self.inventory_mock.return_value = [self.pending('other', ['task:2'])]
        with self.guard():
            self.assertEqual(['called'], self.calls)
        self.inventory_mock.return_value = [self.pending('other', ['task:1'])]
        self.assert_blocked(codec.ReasonCode.PENDING)
        self.inventory_mock.return_value = [{'operation_id': 'other', 'state': 'prepared', 'frozen': {}}]
        self.assert_blocked(codec.ReasonCode.PENDING)

    def test_same_operation_requires_same_complete_scopes_and_unknown_legacy_blocks(self):
        self.inventory_mock.return_value = [self.pending('same', ['task:1'])]
        with self.guard(operation_id='same'):
            pass
        self.assert_blocked(codec.ReasonCode.INPUT_STALE, ('task:2',), operation_id='same')
        self.legacy('capabilities')
        self.assert_blocked(codec.ReasonCode.PENDING, (), legacy_owner=self.owner('capabilities', 'old'))

    def test_metadata_released_but_writer_blocks_other_scope_until_exit(self):
        with self.guard():
            self.assertEqual('available', self.probe('metadata'))
            self.assertEqual('busy', self.probe('guard', ('task:2',)))
        self.assertEqual('available', self.probe('guard', ('task:2',)))

    def test_callback_failure_releases_all_leases(self):
        def failed():
            raise RuntimeError('fixture failure')
        with self.assertRaisesRegex(RuntimeError, 'fixture failure'):
            with self.guard(prepare_under_lease=failed):
                pass
        self.assertEqual('available', self.probe('metadata'))
        self.assertEqual('available', self.probe('guard', ('task:1',)))

    def test_capability_marker_only_exact_owned_resume_is_exempt(self):
        path, state, journal = self.legacy('capabilities')
        owner = self.owner('capabilities', 'old')
        atomic_json(self.root / scope.CAP_PENDING, {'run_id': 'old', 'journal_path': owner['journal_path']})
        self.assert_blocked(codec.ReasonCode.PENDING)
        with self.guard((), legacy_owner=owner):
            pass
        wrong = dict(owner, journal_path='logs/ci/capability-planning/other/apply-journal.json')
        self.assert_blocked(codec.ReasonCode.CONFLICT, (), legacy_owner=wrong)
        marker = load_json(self.root / scope.CAP_PENDING)
        marker['journal_path'] = wrong['journal_path']
        atomic_json(self.root / scope.CAP_PENDING, marker)
        self.assert_blocked(codec.ReasonCode.CONFLICT, (), legacy_owner=owner)

    def test_orphan_legacy_journals_block_without_marker_and_rebind_cannot_resume(self):
        self.legacy('mvg')
        self.assert_blocked(codec.ReasonCode.PENDING)
        with self.guard((), legacy_owner=self.owner('mvg', 'old')):
            pass
        self.assert_blocked(codec.ReasonCode.PENDING, (), legacy_owner=self.owner('mvg-rebind', 'old'))
        self.legacy('capabilities', 'orphan')
        self.assert_blocked(codec.ReasonCode.PENDING, (), legacy_owner=self.owner('mvg', 'old'))

    def test_complete_journal_requires_owned_run_and_summary_not_current_target_bytes(self):
        path, state, journal = self.legacy('mvg', completed=True)
        target = self.root / journal['result']['manifest_path']
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b'Later legitimate operation changed the formal target')
        with self.guard():
            pass
        state['applied'] = False
        atomic_json(path.parent / 'run.json', state)
        self.assert_blocked(codec.ReasonCode.PENDING)

    def test_malformed_original_images_rejected_even_for_own_resume(self):
        path, state, journal = self.legacy('capabilities')
        journal['entries'][0]['before_sha256'] = 'sha256:' + 'a' * 64
        journal['entries'][0]['before_base64'] = '!!!'
        atomic_json(path, journal)
        self.assert_blocked(codec.ReasonCode.DIGEST_MISMATCH, (), legacy_owner=self.owner('capabilities', 'old'))

    def test_existing_null_or_malformed_marker_is_not_absence(self):
        path = self.root / scope.CAP_PENDING
        path.parent.mkdir(parents=True)
        for payload in (b'null', b'[]', b'{"run_id":"old"}',
                        b'{"run_id":"old","run_id":"other","journal_path":"x"}'):
            with self.subTest(payload=payload):
                path.write_bytes(payload)
                with self.assertRaises(codec.CodecError):
                    with self.guard():
                        self.fail('Malformed marker yielded')
                self.assertEqual([], self.calls)

    def test_complete_capability_history_uses_original_binding_not_later_formal_bytes(self):
        path, state, journal = self.legacy('capabilities', completed=True)
        target = self.root / 'docs/planning/semantic-topology/capabilities.v1.json'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'Later operation')
        with self.guard():
            pass
        summary = path.parent / 'apply-summary.json'
        value = load_json(summary)
        value['capabilities_sha256'] = 'sha256:' + 'a' * 64
        atomic_json(summary, value)
        self.assert_blocked(codec.ReasonCode.PENDING)

    def test_public_capability_wrapper_checks_pending_and_holds_writer(self):
        import plan_capabilities
        path, state, journal = self.legacy('capabilities')
        self.inventory_mock.return_value = [self.pending('new-op', ['task:99'])]
        with patch.object(plan_capabilities, '_apply_impl') as implementation:
            with self.assertRaises(codec.CodecError):
                plan_capabilities.apply(self.root, run_id='old', alignment_override=None, confirm=True)
            implementation.assert_not_called()
        self.inventory_mock.return_value = []
        def implementation(*args, **kwargs):
            self.assertEqual('available', self.probe('metadata'))
            self.assertEqual('busy', self.probe('guard', ('task:99',)))
            return {'synthetic': 'capability'}
        with patch.object(plan_capabilities, '_apply_impl', side_effect=implementation):
            self.assertEqual({'synthetic': 'capability'}, plan_capabilities.apply(
                self.root, run_id='old', alignment_override=None, confirm=True))

    def test_public_mvg_apply_and_rebind_hold_original_activity_before_writer(self):
        import plan_mvg
        path, state, journal = self.legacy('mvg', completed=True)
        def implementation(*args, **kwargs):
            self.assertEqual('available', self.probe('metadata'))
            self.assertEqual('busy', self.probe('guard', ('task:99',)))
            self.assertEqual('busy', self.probe('activity'))
            return {'synthetic': 'mvg'}
        with patch.dict(os.environ, {'SC_MVG_RECOVERY_ROOT': str(self.root / 'private-recovery')}):
            with patch.object(plan_mvg, '_apply_impl', side_effect=implementation):
                self.assertEqual({'synthetic': 'mvg'}, plan_mvg.apply(self.root, run_id='old', confirm=True))
            with patch.object(plan_mvg, '_rebind_handoff_impl', side_effect=implementation):
                self.assertEqual({'synthetic': 'mvg'}, plan_mvg.rebind_handoff(self.root, run_id='old',
                    task_id='1', change_plan_path=None, out_path=None))

    def test_original_owner_reload_happens_under_metadata_before_pending_exemption(self):
        self.legacy('capabilities')
        original = scope._owner
        def checked(*args):
            self.assertEqual('busy', self.probe('metadata'))
            return original(*args)
        with patch.object(scope, '_owner', side_effect=checked):
            with self.guard((), legacy_owner=self.owner('capabilities', 'old')):
                pass


def probe(mode, root, scopes):
    try:
        if mode == 'metadata':
            with coordinator_lock(root / scope.STORE / 'locks/metadata'):
                pass
        elif mode == 'activity':
            from _mvg_capability_recovery import operation_lock
            with operation_lock(root):
                pass
        else:
            with patch.object(scope, '_operation_inventory', return_value=[]):
                with scope.scope_guard(root, scopes, prepare_under_lease=lambda: None):
                    pass
    except (codec.CodecError, ValueError) as error:
        if isinstance(error, codec.CodecError):
            assert error.diagnostic.reason_code == codec.ReasonCode.CONFLICT
        else:
            assert str(error) == 'capability_coordinator_busy'
        print('busy')
    else:
        print('available')


if __name__ == '__main__':
    if sys.argv[1:2] == ['--probe']:
        probe(sys.argv[2], Path(sys.argv[3]), json.loads(sys.argv[4]))
    else:
        with patch.object(socket.socket, 'connect', side_effect=AssertionError('Offline test only')):
            unittest.main(verbosity=2)
