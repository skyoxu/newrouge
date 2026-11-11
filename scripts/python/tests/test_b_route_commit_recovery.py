"""Recovery uses actual commit storage and leases; no model/native dispatch."""
from copy import deepcopy
from contextlib import contextmanager, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_adoption as adoption
import _b_route_codec as codec
import _b_route_commit as commit
import _b_route_operation_scope as scope
import _b_route_records as records
import _planning_apply_journal as journal
from test_b_route_commit import CommitFixture
from test_b_route_records import encoded


def legacy(root, kind='capabilities', *, marker=True):
    prefix = scope._ROOTS[kind] + '/old'
    home = root / prefix
    home.mkdir(parents=True, exist_ok=True)
    (home / 'run.json').write_bytes(encoded({'schema_version': scope._SCHEMAS[kind],
        'run_id': 'old', 'phase': 'prepared', 'applied': False}))
    path = home / 'apply-journal.json'
    journal.create_journal(root, path, {root / 'ordinary/old.json': {'original': True}}, {}, {'status': 'applied'})
    if marker:
        target = root / scope.CAP_PENDING
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(encoded({'run_id': 'old', 'journal_path': prefix + '/apply-journal.json'}))
    return path


def assert_boundary_drift_rejected(case, operation_id, execute, kind, timing):
    """Inject only after the second verify pass has validated its original reads."""
    envelope = journal.read_operation(case.root, operation_id=operation_id)
    source = 'sources/input.md' if kind.startswith('source') else envelope['frozen']['request']['host_review_ref']['path']
    target = case.root / source
    unknown = b'Unknown concurrent source or support edit; retain these exact bytes.\n'
    intent_path = case.root / commit._paths(operation_id)[0]
    marker_path = case.root / commit._paths(operation_id)[1]
    receipt_path = case.root / records.BASE / 'commits' / (operation_id + '.json')
    intent_before, marker_before = intent_path.read_bytes(), marker_path.read_bytes()
    operation_before = (case.root / journal._operation_ref(operation_id)).read_bytes()
    index_before = (case.root / journal.OPERATION_STORE / 'pending.json').read_bytes()
    formal_before = case.formal()
    original = commit._capture_boundary
    original_writer = scope.writer_boundary
    calls, armed = [], []
    original_source = target.read_bytes()
    def mutate():
        if kind.endswith('delete'):
            target.unlink()
        else:
            target.write_bytes(unknown)
    def inject(repository, current_envelope, intent, verified):
        calls.append(current_envelope['operation_id'])
        selected = current_envelope['operation_id'] == operation_id and len(calls) == 2
        if selected and timing in ('before_install', 'aba'):
            mutate()
        value = original(repository, current_envelope, intent, verified)
        if selected and timing == 'after_install':
            mutate()
        if selected and timing == 'aba':
            # A pre-pin/recheck reorder would observe unknown -> original ->
            # unknown and authorize the last unknown value. Only the bytes
            # actually validated against the original intent may be expected.
            target.write_bytes(original_source)
            armed.append(True)
        return value
    @contextmanager
    def writer(repository, *, recheck):
        if armed:
            mutate()
        with original_writer(repository, recheck=recheck) as value:
            yield value
    with patch.object(commit, '_capture_boundary', side_effect=inject), \
            patch.object(scope, 'writer_boundary', side_effect=writer), case.assertRaises(codec.CodecError) as caught:
        execute()
    case.assertEqual(codec.ReasonCode.INPUT_STALE, caught.exception.diagnostic.reason_code)
    case.assertEqual([operation_id, operation_id], calls)
    case.assertFalse(receipt_path.exists())
    case.assertEqual(intent_before, intent_path.read_bytes())
    case.assertEqual(marker_before, marker_path.read_bytes())
    case.assertEqual(operation_before, (case.root / journal._operation_ref(operation_id)).read_bytes())
    case.assertEqual(index_before, (case.root / journal.OPERATION_STORE / 'pending.json').read_bytes())
    case.assertEqual(formal_before, case.formal())
    if kind.endswith('delete'):
        case.assertFalse(target.exists())
    else:
        case.assertEqual(unknown, target.read_bytes())


class RecoveryTests(CommitFixture, unittest.TestCase):
    def resume(self, operation='OP-one'):
        with patch.object(adoption, 'capture_completed', self.fx.synthetic_capture):
            return commit.recover(self.root, operation_id=operation)

    def test_inspection_is_read_only_and_does_not_grant_initial_admission(self):
        original = self.prepare()
        before = self.fx.files()
        facts = commit.inspect_recovery(self.root, operation_id='OP-one')
        self.assertEqual(('untouched', 'apply'), (facts['physical_state'], facts['next_stage']))
        self.assertFalse(facts['formal_adoption'])
        self.assertEqual(before, self.fx.files())
        self.assertEqual(original, journal.read_operation(self.root, operation_id='OP-one'))

    def test_verified_source_support_rewrite_or_delete_never_becomes_a_new_boundary_expectation(self):
        for kind in ('source_rewrite', 'source_delete', 'support_rewrite', 'support_delete'):
            for timing in ('before_install', 'after_install', 'aba'):
                with self.subTest(kind=kind, timing=timing):
                    self.prepare(); self.step('apply')
                    assert_boundary_drift_rejected(self, 'OP-one', lambda: self.step('verify'), kind, timing)

    def test_policy_owner_returns_same_read_pins_for_every_original_policy_resource(self):
        import _b_route_adoption_review as review
        identity, files = review.policy_observations()
        self.assertEqual(identity, review.policy_identity())
        for name in ('_planning_execution_binding.py', '_codex_app_server.py', '_planning_skill_common.py',
                     'openai_isolated_model_runner.py', 'codex_isolated_model_runner.py'):
            path = Path(review.__file__).resolve().with_name(name)
            self.assertEqual(codec.raw_digest(path.read_bytes()), files[str(path)])
        self.prepare(); self.step('apply')
        envelope = journal.read_operation(self.root, operation_id='OP-one')
        intent = commit.validate_local(self.root, envelope)
        original = Path.read_bytes
        changed = Path(review.__file__).resolve().with_name('_planning_execution_binding.py')
        def drift(path):
            data = original(path)
            return data + b'\n# Synthetic concurrent policy change\n' if path == changed else data
        with patch.object(Path, 'read_bytes', drift), self.assertRaises(codec.CodecError) as caught:
            commit._validated_policy_facts(intent, commit._VerifiedFacts())
        self.assertEqual(codec.ReasonCode.INPUT_STALE, caught.exception.diagnostic.reason_code)

    def test_policy_resource_outside_old_glob_cannot_drift_at_boundary_installation(self):
        import _b_route_adoption_review as review
        for timing in ('before_install', 'after_install'):
            with self.subTest(timing=timing):
                self.prepare(); self.step('apply')
                intent_path = self.root / commit._paths('OP-one')[0]
                intent_before = intent_path.read_bytes()
                changed = Path(review.__file__).resolve().with_name('_planning_execution_binding.py')
                read_bytes = Path.read_bytes
                capture = commit._capture_boundary
                enabled, calls = [], []
                def drift(path):
                    data = read_bytes(path)
                    return data + b'\n# Synthetic boundary policy drift\n' if enabled and path == changed else data
                def inject(repository, envelope, intent, verified):
                    calls.append(envelope['operation_id'])
                    if len(calls) == 2 and timing == 'before_install':
                        enabled.append(True)
                    value = capture(repository, envelope, intent, verified)
                    if len(calls) == 2 and timing == 'after_install':
                        enabled.append(True)
                    return value
                with patch.object(Path, 'read_bytes', drift), \
                        patch.object(commit, '_capture_boundary', side_effect=inject), self.assertRaises(codec.CodecError) as caught:
                    self.step('verify')
                self.assertEqual(codec.ReasonCode.INPUT_STALE, caught.exception.diagnostic.reason_code)
                self.assertEqual(2, len(calls))
                self.assertEqual(intent_before, intent_path.read_bytes())
                self.assertFalse((self.root / records.BASE / 'commits/OP-one.json').exists())
                self.assertTrue((self.root / commit._paths('OP-one')[1]).exists())

    def test_recover_advances_only_missing_stages_and_retains_original_operation_index(self):
        self.prepare()
        operation = self.root / journal._operation_ref('OP-one')
        index = self.root / journal.OPERATION_STORE / 'pending.json'
        original = operation.read_bytes(), index.read_bytes()
        result = self.resume()
        self.assertTrue(result['published'])
        self.assertEqual(original, (operation.read_bytes(), index.read_bytes()))
        self.assertTrue(commit.read_committed(self.root)['formal_adoption'])
        before = self.fx.files()
        with patch.object(commit, '_write', side_effect=AssertionError('Completed side effects must not repeat')):
            self.assertTrue(self.resume()['noop'])
        self.assertEqual(before, self.fx.files())

    def test_fixed_fault_matrix_recovers_exact_known_images_without_mixed_reads(self):
        boundaries = [('pending_durable', 'apply'), ('intent_durable', 'apply'),
            ('before_target:0', 'apply'), ('after_target:0', 'apply'),
            ('after_target:1', 'apply'), ('after_target:2', 'apply'), ('applied_durable', 'apply'),
            ('receipt_durable', 'verify'), ('verified_durable', 'verify'),
            ('catalog_intent_durable', 'publish'), ('catalog_replaced', 'publish'),
            ('published_durable', 'publish'), ('before_pending_cleanup', 'publish')]
        for label, stage in boundaries:
            with self.subTest(boundary=label):
                self.prepare()
                if stage in ('verify', 'publish'): self.step('apply')
                if stage == 'publish': self.step('verify')
                with self.fail_at(label), self.assertRaises(codec.CodecError): self.step(stage)
                with self.assertRaises(codec.CodecError): commit.read_committed(self.root)
                self.assertTrue(self.resume()['published'])
                self.assertEqual([], journal.active_operation_inventory(self.root))
                self.assertTrue(commit.read_committed(self.root)['formal_adoption'])

    def test_partial_after_is_skipped_and_unknown_post_edit_stops_without_writes(self):
        envelope = self.prepare()
        with self.fail_at('after_target:0'), self.assertRaises(codec.CodecError): self.step('apply')
        target = envelope['frozen']['targets'][0]['path']
        actual = (self.root / target).read_bytes()
        facts = commit.inspect_recovery(self.root, operation_id='OP-one')
        self.assertEqual('partial', facts['physical_state'])
        calls = []
        original_write = commit._write
        def record(repository, path, data):
            calls.append(path)
            return original_write(repository, path, data)
        with patch.object(commit, '_write', side_effect=record): self.resume()
        self.assertNotIn(target, calls)
        self.assertEqual(actual, (self.root / target).read_bytes())
        self.prepare(); self.step('apply')
        target = journal.read_operation(self.root, operation_id='OP-one')['frozen']['targets'][0]['path']
        (self.root / target).write_bytes(b'{"human":"keep"}')
        before = self.fx.files()
        with self.assertRaises(codec.CodecError): self.resume()
        self.assertEqual(before, self.fx.files())

    def test_related_source_rule_and_receipt_damage_remain_blocked_with_evidence(self):
        for kind in ('source', 'rules', 'receipt'):
            with self.subTest(kind=kind):
                self.prepare(); self.step('apply'); self.step('verify')
                if kind == 'source':
                    (self.root / 'sources/input.md').write_bytes(b'Changed relevant source')
                elif kind == 'rules':
                    path = self.root / commit._paths('OP-one')[0]
                    value = codec.strict_json_loads(path.read_bytes())
                    value['policy_identity'] = 'sha256:' + '0' * 64
                    path.write_bytes(encoded(commit._seal(value)))
                else:
                    (self.root / records.BASE / 'commits/OP-one.json').write_bytes(b'{"damaged":true}')
                before = self.fx.files()
                with self.assertRaises(codec.CodecError): self.resume()
                self.assertEqual(before, self.fx.files())

    def test_missing_marker_does_not_grant_completion_but_proved_missing_steps_can_continue(self):
        self.prepare(); self.step('apply')
        (self.root / commit._paths('OP-one')[1]).unlink()
        self.assertEqual('targets_after_unpublished',
            commit.inspect_recovery(self.root, operation_id='OP-one')['physical_state'])
        with self.assertRaises(codec.CodecError): commit.read_committed(self.root)
        self.assertTrue(self.resume()['published'])

    def test_long_review_preflight_holds_no_shared_writer_and_unrelated_scope_can_enter(self):
        self.prepare(); self.step('apply')
        entered = []
        def probe(name):
            if name == 'recovery_before_review':
                with scope.scope_guard(self.root, ['synthetic:unrelated'],
                        prepare_under_lease=lambda: entered.append('entered')):
                    pass
        with patch.object(commit, '_checkpoint', side_effect=probe):
            commit.inspect_recovery(self.root, operation_id='OP-one')
        self.assertEqual(['entered'], entered)

    def test_actual_unrelated_formal_publication_progresses_during_long_recovery_check(self):
        self.prepare(); self.publish()
        request_two = self.relocate_proofs(self.fx.case('two', 'OP-two'))
        self.fx.prepare(request_two)
        with patch.object(adoption, 'capture_completed', self.fx.synthetic_capture):
            adoption.reserve(self.root, operation_id='OP-two')
        self.step('apply', 'OP-two'); self.step('verify', 'OP-two')
        # A third prepared operation is admitted before the second publishes.
        # Its long initial validation deliberately pauses while the second
        # executes actual shared-engine publication, not a mocked lock probe.
        request_three = self.relocate_proofs(self.fx.case('three', 'OP-three'))
        self.fx.prepare(request_three)
        with patch.object(adoption, 'capture_completed', self.fx.synthetic_capture):
            adoption.reserve(self.root, operation_id='OP-three')
        original = commit.projection.catalog_for_receipt
        progressed = []
        def interleave(*args, **kwargs):
            if kwargs['receipt']['operation_id'] == 'OP-three' and not progressed:
                progressed.append(self.step('publish', 'OP-two'))
            return original(*args, **kwargs)
        with patch.object(commit.projection, 'catalog_for_receipt', side_effect=interleave):
            try:
                self.step('apply', 'OP-three')
            except codec.CodecError as error:
                self.assertIn(error.diagnostic.reason_code, (codec.ReasonCode.INPUT_STALE, codec.ReasonCode.CONFLICT))
        self.assertTrue(progressed[0]['published'])
        current = codec.strict_json_loads((self.root / records.CATALOG_PATH).read_bytes())
        self.assertTrue(any(head['receipt_ref']['entity_id'] == 'OP-two' for head in current['scope_heads']))

    def test_source_change_during_inspection_is_reported_before_any_recovery_write(self):
        self.prepare(); self.step('apply')
        def edit(name):
            if name == 'recovery_inspected':
                (self.root / 'sources/input.md').write_bytes(b'Concurrent source edit')
        with patch.object(commit, '_checkpoint', side_effect=edit), self.assertRaises(codec.CodecError):
            commit.inspect_recovery(self.root, operation_id='OP-one')
        self.assertTrue((self.root / commit._paths('OP-one')[1]).exists())

    def test_legacy_route_blocks_recover_without_executing_old_apply_or_deleting_marker(self):
        self.prepare()
        legacy(self.root)
        before = self.fx.files()
        facts = commit.inspect_recovery(self.root, operation_id='OP-one')
        self.assertEqual('plan_capabilities.apply', facts['legacy_routes'][0]['owner_api'])
        with self.assertRaises(codec.CodecError) as caught: self.resume()
        self.assertEqual(codec.ReasonCode.PENDING, caught.exception.diagnostic.reason_code)
        self.assertEqual(before, self.fx.files())

    def test_cleanup_after_unrelated_publication_preserves_later_catalog_bytes(self):
        self.prepare(); self.step('apply'); self.step('verify')
        with self.fail_at('before_pending_cleanup'), self.assertRaises(codec.CodecError): self.step('publish')
        request = self.relocate_proofs(self.fx.case('two', 'OP-two'))
        self.fx.prepare(request)
        with patch.object(adoption, 'capture_completed', self.fx.synthetic_capture):
            adoption.reserve(self.root, operation_id='OP-two')
        for stage in ('apply', 'verify', 'publish'): self.step(stage, 'OP-two')
        before = self.formal()
        facts = commit.inspect_recovery(self.root, operation_id='OP-one')
        self.assertEqual('published_pending_cleanup', facts['physical_state'])
        self.assertTrue(self.resume()['published'])
        self.assertEqual(before, self.formal())
        self.assertEqual([], journal.active_operation_inventory(self.root))

    def test_explicit_publish_cleanup_preserves_later_unrelated_publication(self):
        self.prepare(); self.step('apply'); self.step('verify')
        with self.fail_at('before_pending_cleanup'), self.assertRaises(codec.CodecError):
            self.step('publish')
        request = self.relocate_proofs(self.fx.case('two', 'OP-two'))
        self.fx.prepare(request)
        with patch.object(adoption, 'capture_completed', self.fx.synthetic_capture):
            adoption.reserve(self.root, operation_id='OP-two')
        for stage in ('apply', 'verify', 'publish'):
            self.step(stage, 'OP-two')
        before = self.formal()
        self.assertEqual('published_pending_cleanup',
                         commit.inspect_recovery(self.root, operation_id='OP-one')['physical_state'])
        self.assertTrue(self.step('publish')['published'])
        self.assertFalse((self.root / commit._paths('OP-one')[1]).exists())
        self.assertEqual(before, self.formal())
        self.assertEqual([], journal.active_operation_inventory(self.root))

    def test_public_recovery_stages_share_service_and_keep_inspection_claims_false(self):
        import b_route_adoption as cli
        self.prepare()
        for stage in ('recover-inspect', 'recover'):
            output = io.StringIO()
            with patch.object(adoption, 'capture_completed', self.fx.synthetic_capture), redirect_stdout(output):
                code = cli.main(['--root', str(self.root), '--stage', stage, '--operation-id', 'OP-one'])
            self.assertEqual(0, code, output.getvalue())
            value = json.loads(output.getvalue())
            self.assertIs(stage == 'recover', value['formal_adoption'])
            self.assertFalse(value['readiness']); self.assertFalse(value['runtime_verified'])
            self.assertFalse(value['default_b_enabled'])


class LegacyRecoveryRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nr28-legacy-', dir=os.environ.get('ADOPTION_TEST_TEMP'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_marker_and_orphan_mvg_journal_return_original_routes_without_side_effects(self):
        legacy(self.root)
        legacy(self.root, 'mvg', marker=False)
        before = {str(path): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        routes = scope.legacy_recovery_routes(self.root)
        self.assertEqual({'plan_capabilities.apply', 'plan_mvg.apply'}, {row['owner_api'] for row in routes})
        self.assertTrue(all(row['scope'] == 'unknown' and row['requires_original_confirmation'] for row in routes))
        self.assertEqual(before, {str(path): path.read_bytes() for path in self.root.rglob('*') if path.is_file()})

    def test_null_marker_and_changed_original_journal_are_retained_and_rejected(self):
        path = legacy(self.root)
        marker = self.root / scope.CAP_PENDING
        marker.write_bytes(b'null')
        with self.assertRaises(codec.CodecError): scope.legacy_recovery_routes(self.root)
        self.assertEqual(b'null', marker.read_bytes())
        marker.write_bytes(encoded({'run_id': 'old', 'journal_path': path.relative_to(self.root).as_posix()}))
        value = codec.strict_json_loads(path.read_bytes())
        value['entries'][0]['after_sha256'] = 'sha256:' + '0' * 64
        path.write_bytes(encoded(value))
        with self.assertRaises(codec.CodecError): scope.legacy_recovery_routes(self.root)
        self.assertEqual(encoded(value), path.read_bytes())


@unittest.skipUnless(os.name == 'nt', 'Actual Windows process recovery evidence')
class WindowsRecoveryTests(CommitFixture, unittest.TestCase):
    def child(self, mode):
        helper = Path(__file__).parent / 'fixtures/b_route_commit_process.py'
        dependencies = [value for value in sys.path if 'site-packages' in value or 'story22-tokenizer-deps' in value]
        environment = dict(os.environ)
        environment.setdefault('ADOPTION_TEST_TEMP', str(self.root.parent))
        return subprocess.run([sys.executable, '-I', '-S', '-B', str(helper), str(self.root), mode,
            json.dumps(dependencies)], capture_output=True, timeout=120, env=environment,
            creationflags=subprocess.CREATE_NO_WINDOW)

    def test_fixed_process_crash_then_public_recover_completes_without_replaying_after(self):
        self.prepare()
        failed = self.child('crash-after-target')
        self.assertEqual(73, failed.returncode, failed.stderr)
        result = self.child('recover')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(json.loads(result.stdout)['published'])
        before = self.formal()
        result = self.child('recover')
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertTrue(json.loads(result.stdout)['noop'])
        self.assertEqual(before, self.formal())
