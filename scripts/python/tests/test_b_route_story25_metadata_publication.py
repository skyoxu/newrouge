"""Synthetic retained qualification, real Windows metadata publication/locks.

No model is invoked. Full old source/admission qualification is an explicit
fixture boundary; journal reconstruction, CAS, exclusive rename, append-only
history, finite namespace and reconcile stay real. Root alone executes tests.
"""
from contextlib import contextmanager
from copy import deepcopy
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import sys
import threading
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'scripts/python'))
from scripts.python.tests import test_b_route_story25_review_hardening as fixtures
import _b_route_selector_recovery as recovery
import _b_route_execution_transition as transition
import _mvg_capability_checkpoint as checkpoint
import _b_route_mvg_synthesis_recovery as previous

_REAL_VALIDATE_TRANSITION = transition.validate_transition


class _OwnedDirectory:
    def __init__(self):
        self.parent = Path(os.environ.get('TEMP', r'C:\Windows\TEMP')).resolve()
        self.name = str(self.parent / ('mp27_' + secrets.token_hex(6)))
        Path(self.name).mkdir(exist_ok=False)
        self.keep = False

    def cleanup(self):
        root = Path(self.name)
        if self.keep or not root.exists():
            return
        if root.resolve().parent != self.parent or not re.fullmatch(r'mp27_[0-9a-f]{12}', root.name):
            raise AssertionError('Refuse cleanup outside exact allocated fixture')
        root_info = root.lstat()
        if (not stat.S_ISDIR(root_info.st_mode) or stat.S_ISLNK(root_info.st_mode)
                or getattr(root_info, 'st_file_attributes', 0) & 0x400):
            raise AssertionError('Refuse non-directory or reparse fixture root cleanup')
        for directory, names, files in os.walk(root, followlinks=False):
            for name in [*names, *files]:
                path = Path(directory) / name
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                    raise AssertionError('Refuse reparse cleanup')
                if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                    raise AssertionError('Refuse hardlink cleanup')
        shutil.rmtree(root)


class MetadataPublicationTests(unittest.TestCase):
    @contextmanager
    def case(self):
        owned = _OwnedDirectory()
        fixture = fixtures.SelectorTransactionTests('test_foreign_temporary_still_blocks')
        with patch.object(fixtures.tempfile, 'TemporaryDirectory', return_value=owned):
            fixture.setUp()
        fixture.stack.enter_context(patch.object(previous, 'validate_recovery'))
        capture = recovery.capture_retained_selector(fixture.root)
        try:
            yield fixture, capture
        except BaseException:
            owned.keep = True
            raise
        finally:
            fixture.doCleanups()

    def start(self, fixture, kind, *, row=None, after=None):
        before = (fixture.run / 'run.json').read_bytes()
        if after is None:
            after = recovery._json_bytes(fixture.prepared)
        with checkpoint.coordinator_lock(fixture.run):
            return recovery._start_transaction(fixture.root, kind, fixture.record, before, after, row=row)

    def stage(self, fixture, kind):
        if kind != 'prepare':
            self.start(fixture, 'prepare')
        if kind == 'reservation':
            row, after = fixture.reservation()
            return {'row': row, 'after': recovery._json_bytes(after)}
        if kind == 'unknown':
            row, after = fixture.reservation()
            self.start(fixture, 'reservation', row=row, after=recovery._json_bytes(after))
            after['capability_selection']['calls'][12]['outcome'] = {
                'status': 'unknown', 'error_type': 'metadata_reconcile_dispatch_uncertain'}
            after['capability_selection']['terminal'] = True
            after.update(phase='selection-blocked', selection_status='blocked',
                         selection_block_reason='selector_metadata_reconcile_dispatch_uncertain')
            return {'after': recovery._json_bytes(after)}
        return {}

    def finish(self, fixture, capture, kind, *, images=None):
        result = recovery.reconcile(fixture.root, fixture.run, retained_capture=capture, publication_images=images)
        state = recovery.read(fixture.run, 'run.json')
        ledger = state['capability_selection']
        self.assertEqual(ledger['calls'][:12], fixture.old['capability_selection']['calls'])
        self.assertEqual((fixture.run / 'model-execution.json').read_bytes(), fixture.model)
        self.assertEqual((result['model_calls'], result['released'], result['retry_authorized']), (0, 0, False))
        self.assertEqual(state['b_route_campaign_funding']['released'], 0)
        self.assertEqual(ledger['total_invocations'], 12 if kind == 'prepare' else 13)
        if kind != 'prepare':
            self.assertEqual(len(ledger['calls']), 13)
            self.assertEqual(ledger['calls'][12]['reservation_id'], 'm4:dispatch:13')
            self.assertEqual(ledger['calls'][12]['outcome']['status'], 'unknown')
            self.assertTrue(ledger['terminal'])
            self.assertEqual(state['selection_status'], 'blocked')
            self.assertEqual(state['b_route_campaign_funding']['paid_or_unknown_before_run'] + len(ledger['calls']), 79)
            with self.assertRaisesRegex(ValueError, 'selector_intent_already_reserved'):
                recovery.authorize_selector_reservation(fixture.root, state, phase='selection', candidate=None,
                    request_identity=ledger['calls'][12]['request_identity'], reservation=ledger['calls'][12])
        return result

    def snapshot(self, fixture):
        return {path.relative_to(fixture.root).as_posix(): path.read_bytes()
                for path in fixture.run.rglob('*') if path.is_file()}

    def test_original_witness_closure_failure_precedes_every_recovery_mutation(self):
        with self.case() as (fixture, capture):
            rename = recovery._exclusive_rename
            def material_only(source, destination):
                rename(source, destination)
                if destination.suffix == '.image':
                    raise SystemExit('complete material retained before final publication')
            with patch.object(recovery, '_exclusive_rename', side_effect=material_only):
                with self.assertRaises(SystemExit):
                    self.start(fixture, 'prepare')
            before = self.snapshot(fixture)
            original_root = fixture.root / 'synthetic-original'
            view = {'synthetic': 'unavailable-original-source-boundary'}
            def authenticated_frame(root, state, context):
                # Only the unavailable original frame is synthetic. Keep the
                # actual validate_transition/_validated/transaction entry and
                # deferred _run_original closing behavior, not a validator stub.
                context['request'] = (original_root, fixture.root, view)
                context['expected'] = {'synthetic': 'expected'}
                return 'synthetic-transition-digest', {}
            with patch.object(transition, 'validate_transition', _REAL_VALIDATE_TRANSITION), \
                 patch.object(transition, '_validate_frame', side_effect=authenticated_frame) as frame, \
                 patch.object(transition, '_run_original', side_effect=ValueError('original witness refused at closure')) as witness:
                with self.assertRaisesRegex(ValueError, 'original witness refused at closure'):
                    recovery.reconcile(fixture.root, fixture.run, retained_capture=capture)
                frame.assert_called_once()
                witness.assert_called_once_with(original_root, fixture.root, view)
            self.assertEqual(self.snapshot(fixture), before)
            self.assertFalse((fixture.home / 'prepare-transaction.json').exists())
            self.assertFalse((fixture.home / 'claim.json').exists())
            self.assertIsNone(recovery._PUBLICATION_MATERIALS.get())
            self.assertEqual(recovery.read(fixture.run, 'run.json')['capability_selection']['calls'],
                fixture.old['capability_selection']['calls'])

    def test_original_image_scope_is_root_bound_non_authoritative_and_never_leaks(self):
        with self.case() as (fixture, capture):
            self.start(fixture, 'prepare')
            row, after = fixture.reservation()
            value = recovery._transaction_value('reservation', fixture.record,
                recovery._json_bytes(fixture.prepared), recovery._json_bytes(after), row=row)
            raw = recovery._json_bytes(value)
            _, part, _ = recovery._publication_paths(fixture.home, value, raw)
            part.write_bytes(raw[:19])
            before = self.snapshot(fixture)
            for invalid in ({'other': raw}, {'reservation': 'not raw bytes'}):
                with self.assertRaisesRegex(ValueError, 'closed_original_publication_images'):
                    with recovery._publication_material_scope(fixture.root, invalid):
                        self.fail('Invalid scope must not be entered')
                self.assertIsNone(recovery._PUBLICATION_MATERIALS.get())
            with self.assertRaisesRegex(RuntimeError, 'scope interrupted'):
                with recovery._publication_material_scope(fixture.root, {'reservation': raw}):
                    self.assertEqual(recovery.validate_recovery(fixture.root, fixture.prepared), fixture.record)
                    with self.assertRaisesRegex(ValueError, 'publication_material_root_changed'):
                        recovery._images_for_action(fixture.root / 'different-root', None)
                    with self.assertRaisesRegex(ValueError, 'publication_material_action_changed'):
                        recovery._images_for_action(fixture.root, {'reservation': b'other image'})
                    errors = []
                    def other_thread():
                        try:
                            recovery.validate_recovery(fixture.root, fixture.prepared)
                        except ValueError as error:
                            errors.append(str(error))
                    worker = threading.Thread(target=other_thread)
                    worker.start(); worker.join(timeout=20)
                    self.assertFalse(worker.is_alive())
                    self.assertEqual(len(errors), 1)
                    self.assertIn('publication_material_incomplete_original_image_required', errors[0])
                    raise RuntimeError('scope interrupted')
            self.assertIsNone(recovery._PUBLICATION_MATERIALS.get())
            with self.assertRaisesRegex(ValueError, 'publication_material_incomplete_original_image_required'):
                recovery.validate_recovery(fixture.root, fixture.prepared)
            self.assertEqual(self.snapshot(fixture), before)
        with self.case() as (fixture, capture):
            self.start(fixture, 'prepare')
            row, after = fixture.reservation()
            row['request_identity']['attempt'] = 2
            after['capability_selection']['calls'][12] = deepcopy(row)
            forged = recovery._transaction_value('reservation', fixture.record,
                recovery._json_bytes(fixture.prepared), recovery._json_bytes(after), row=row)
            raw = recovery._json_bytes(forged)
            _, part, _ = recovery._publication_paths(fixture.home, forged, raw)
            part.write_bytes(raw[:19])
            before = self.snapshot(fixture)
            with recovery._publication_material_scope(fixture.root, {'reservation': raw}):
                with self.assertRaisesRegex(ValueError, 'only_one_original_selector_dispatch'):
                    recovery.validate_recovery(fixture.root, fixture.prepared)
            self.assertIsNone(recovery._PUBLICATION_MATERIALS.get())
            self.assertEqual(self.snapshot(fixture), before)

    def test_full_material_survives_each_stage_publication_before_final_name(self):
        for kind in ('prepare', 'reservation', 'unknown'):
            with self.subTest(kind=kind), self.case() as (fixture, capture):
                arguments = self.stage(fixture, kind)
                before = (fixture.run / 'run.json').read_bytes()
                rename = recovery._exclusive_rename
                def interrupt(source, destination):
                    rename(source, destination)
                    if destination.suffix == '.image' and destination.name.startswith(kind + '-publication-'):
                        raise SystemExit('host lost after full material publication')
                with patch.object(recovery, '_exclusive_rename', side_effect=interrupt):
                    with self.assertRaisesRegex(SystemExit, 'after full material'):
                        self.start(fixture, kind, **arguments)
                self.assertEqual((fixture.run / 'run.json').read_bytes(), before)
                self.assertFalse((fixture.home / (kind + '-transaction.json')).exists())
                material = list(fixture.home.glob(kind + '-publication-*.image'))
                self.assertEqual(len(material), 1)
                original_image = material[0].read_bytes()
                self.finish(fixture, capture, kind)
                self.assertEqual((fixture.home / (kind + '-transaction.json')).read_bytes(), original_image)
                after = self.snapshot(fixture)
                self.finish(fixture, capture, kind)
                self.assertEqual(self.snapshot(fixture), after)

    def test_partial_first_material_needs_exact_original_image_not_a_new_identity(self):
        for kind in ('prepare', 'reservation', 'unknown'):
            with self.subTest(kind=kind), self.case() as (fixture, capture):
                arguments = self.stage(fixture, kind)
                before = self.snapshot(fixture)
                append = recovery._append_exact
                original = []
                def interrupt(path, expected):
                    if path.suffix == '.part' and path.name.startswith(kind + '-publication-'):
                        original.append(expected)
                        with path.open('xb') as stream:
                            stream.write(expected[:19]); stream.flush(); os.fsync(stream.fileno())
                        raise SystemExit('partial original publication material')
                    return append(path, expected)
                with patch.object(recovery, '_append_exact', side_effect=interrupt):
                    with self.assertRaises(SystemExit):
                        self.start(fixture, kind, **arguments)
                raw = original[0]
                partial = list(fixture.home.glob(kind + '-publication-*.part'))[0]
                held = partial.read_bytes()
                incomplete = self.snapshot(fixture)
                with self.assertRaisesRegex(ValueError, 'publication_material_incomplete_original_image_required'):
                    recovery.reconcile(fixture.root, fixture.run, retained_capture=capture)
                self.assertEqual(self.snapshot(fixture), incomplete)
                changed = recovery.codec.strict_json_loads(raw)
                changed['nonce'] = 'f' * 32 if changed['nonce'] != 'f' * 32 else 'e' * 32
                changed['transaction_digest'] = recovery.codec.canonical_digest({k: v for k, v in changed.items() if k != 'transaction_digest'})
                with self.assertRaisesRegex(ValueError, 'original_publication_provenance_missing'):
                    recovery.reconcile(fixture.root, fixture.run, retained_capture=capture,
                        publication_images={kind: recovery._json_bytes(changed)})
                self.assertEqual(partial.read_bytes(), held)
                self.assertEqual((fixture.run / 'run.json').read_bytes(), before[recovery.RUN_REF + '/run.json'])
                self.finish(fixture, capture, kind, images={kind: raw})
                value, _ = recovery._journal(fixture.root, kind, fixture.anchor)
                evidence = recovery._prefix_path(fixture.root, value, 'p', raw, held)
                self.assertEqual(evidence.read_bytes(), held)

    def test_repeated_journal_partial_prefixes_a_then_ab_are_both_preserved(self):
        for kind in ('prepare', 'reservation', 'unknown'):
            with self.subTest(kind=kind), self.case() as (fixture, capture):
                arguments = self.stage(fixture, kind)
                append = recovery._append_exact
                def write_prefix(path, expected, count):
                    if path.suffix == '.pending' and path.name.startswith(kind + '-publication-'):
                        old = path.read_bytes() if path.exists() else b''
                        with path.open('ab' if path.exists() else 'xb') as stream:
                            stream.write(expected[len(old):count]); stream.flush(); os.fsync(stream.fileno())
                        raise SystemExit('journal append interrupted')
                    return append(path, expected)
                with patch.object(recovery, '_append_exact', side_effect=lambda p, e: write_prefix(p, e, 17)):
                    with self.assertRaises(SystemExit):
                        self.start(fixture, kind, **arguments)
                value, _ = recovery._journal(fixture.root, kind, fixture.anchor)
                raw = recovery._json_bytes(value)
                with patch.object(recovery, '_append_exact', side_effect=lambda p, e: write_prefix(p, e, 43)):
                    with self.assertRaises(SystemExit):
                        recovery.reconcile(fixture.root, fixture.run, retained_capture=capture)
                self.assertFalse((fixture.home / (kind + '-transaction.json')).exists())
                self.finish(fixture, capture, kind)
                for count in (17, 43):
                    self.assertEqual(recovery._prefix_path(fixture.root, value, 'j', raw, raw[:count]).read_bytes(), raw[:count])
                after = self.snapshot(fixture)
                self.finish(fixture, capture, kind)
                self.assertEqual(self.snapshot(fixture), after)

    def test_reservation_and_unknown_before_after_target_replace_windows(self):
        for kind in ('reservation', 'unknown'):
            targets = ('intent.json', 'run.json', 'reservation-committed.json') if kind == 'reservation' else ('run.json', 'unknown-committed.json')
            for target_name in targets:
                for moment in ('before', 'after'):
                    with self.subTest(kind=kind, target=target_name, moment=moment), self.case() as (fixture, capture):
                        arguments = self.stage(fixture, kind)
                        replace = recovery.os.replace
                        def interrupt(source, destination):
                            if Path(destination).name == target_name and moment == 'before':
                                raise SystemExit('before target replacement')
                            replace(source, destination)
                            if Path(destination).name == target_name:
                                raise SystemExit('after target replacement')
                        with patch.object(recovery.os, 'replace', side_effect=interrupt):
                            with self.assertRaises(SystemExit):
                                self.start(fixture, kind, **arguments)
                        self.finish(fixture, capture, kind)

    def test_repeated_operation_prefixes_and_partial_history_copy_resume_without_overwrite(self):
        for kind in ('reservation', 'unknown'):
            with self.subTest(kind=kind), self.case() as (fixture, capture):
                arguments = self.stage(fixture, kind)
                append = recovery._append_exact
                def write_prefix(path, expected, count):
                    if path.name.startswith('run.json.') and path.suffix == '.tmp':
                        old = path.read_bytes() if path.exists() else b''
                        with path.open('ab' if path.exists() else 'xb') as stream:
                            stream.write(expected[len(old):count]); stream.flush(); os.fsync(stream.fileno())
                        raise SystemExit('target append interrupted')
                    return append(path, expected)
                with patch.object(recovery, '_append_exact', side_effect=lambda p, e: write_prefix(p, e, 23)):
                    with self.assertRaises(SystemExit):
                        self.start(fixture, kind, **arguments)
                value, operations = recovery._journal(fixture.root, kind, fixture.anchor)
                index = next(i for i, row in enumerate(operations) if row[0] == recovery.RUN_REF + '/run.json')
                expected = operations[index][2]
                # Preserve a prior version's deterministic evidence too. Its
                # earlier valid prefix must not be required to equal new AB.
                _, _, legacy = recovery._operation_paths(fixture.root, value, index, operations[index][0])
                legacy.write_bytes(expected[:11])
                with patch.object(recovery, '_append_exact', side_effect=lambda p, e: write_prefix(p, e, 59)):
                    with self.assertRaises(SystemExit):
                        recovery.reconcile(fixture.root, fixture.run, retained_capture=capture)
                first = recovery._prefix_path(fixture.root, value, 'o' + str(index), expected, expected[:23])
                self.assertEqual(first.read_bytes(), expected[:23])
                second = recovery._prefix_path(fixture.root, value, 'o' + str(index), expected, expected[:59])
                def interrupted_evidence_copy(path, data):
                    if path == second:
                        self.assertEqual(data, expected[:59])
                        with path.open('xb') as stream:
                            stream.write(data[:7]); stream.flush(); os.fsync(stream.fileno())
                        raise SystemExit('history copy interrupted before completion')
                    return append(path, data)
                with patch.object(recovery, '_append_exact', side_effect=interrupted_evidence_copy):
                    with self.assertRaisesRegex(SystemExit, 'history copy interrupted'):
                        recovery.reconcile(fixture.root, fixture.run, retained_capture=capture)
                self.assertEqual(first.read_bytes(), expected[:23])
                self.assertEqual(second.read_bytes(), expected[:7])
                # Complete an interrupted first evidence copy, without deleting
                # or truncating either earlier observed prefix.
                self.finish(fixture, capture, kind)
                self.assertEqual(second.read_bytes(), expected[:59])
                self.assertEqual(legacy.read_bytes(), expected[:11])

    def test_third_state_and_nonce_or_prefix_tamper_stop_before_any_recovery_write(self):
        for corruption in ('target', 'nonce', 'prefix'):
            with self.subTest(corruption=corruption), self.case() as (fixture, capture):
                rename = recovery._exclusive_rename
                def interrupt(source, destination):
                    rename(source, destination)
                    if destination.suffix == '.image':
                        raise SystemExit('material only')
                with patch.object(recovery, '_exclusive_rename', side_effect=interrupt):
                    with self.assertRaises(SystemExit):
                        self.start(fixture, 'prepare')
                value, operations = recovery._journal(fixture.root, 'prepare', fixture.anchor)
                if corruption == 'target':
                    (fixture.home / 'committed.json').write_bytes(b'foreign target')
                elif corruption == 'nonce':
                    material = list(fixture.home.glob('prepare-publication-*.image'))[0]
                    changed = value['nonce'][::-1]
                    if changed == value['nonce']:
                        changed = 'f' * 32 if value['nonce'] != 'f' * 32 else 'e' * 32
                    material.rename(material.with_name(material.name.replace(value['nonce'], changed)))
                else:
                    _, temporary, _ = recovery._operation_paths(fixture.root, value, 0, operations[0][0])
                    temporary.write_bytes(b'not a real original prefix')
                before = self.snapshot(fixture)
                with self.assertRaises(ValueError):
                    recovery.reconcile(fixture.root, fixture.run, retained_capture=capture)
                self.assertEqual(self.snapshot(fixture), before)
                self.assertEqual(recovery.read(fixture.run, 'run.json')['capability_selection']['calls'], fixture.old['capability_selection']['calls'])

    def test_missing_or_malformed_legacy_journal_preserves_unknown_evidence(self):
        for legacy in ('missing', 'malformed'):
            with self.subTest(legacy=legacy), self.case() as (fixture, capture):
                with checkpoint.coordinator_lock(fixture.run):
                    pass
                if legacy == 'missing':
                    (fixture.home / 'claim.json').write_bytes(b'{"partial":')
                else:
                    (fixture.home / 'prepare-transaction.json').write_bytes(b'{"schema_version":')
                before = self.snapshot(fixture)
                reason = 'legacy_unjournaled' if legacy == 'missing' else 'published_transaction_malformed_preserved'
                with self.assertRaisesRegex(ValueError, reason):
                    recovery.reconcile(fixture.root, fixture.run, retained_capture=capture)
                self.assertEqual(self.snapshot(fixture), before)

    def test_public_concurrent_prepare_has_one_publisher_and_reconcile_never_adds_fourteenth(self):
        with self.case() as (fixture, capture):
            fixture.home.rmdir()
            barrier = threading.Barrier(2)
            successes, errors = [], []
            def publisher():
                try:
                    barrier.wait(timeout=10)
                    result = recovery.prepare(fixture.root, fixture.run, prior_source_root=fixture.root / 'prior',
                        prior_commit=recovery.PRIOR_COMMIT, original_source_root=fixture.root / 'original',
                        current_commit='f' * 40, retained_capture=capture)
                    successes.append(result)
                except (ValueError, OSError, RuntimeError) as error:
                    errors.append(str(error))
            with patch.object(transition, 'build_mvg_selector_transition', return_value=fixture.state['b_route_execution_transition']):
                workers = [threading.Thread(target=publisher) for _ in range(2)]
                for worker in workers: worker.start()
                for worker in workers: worker.join(timeout=20)
                self.assertTrue(all(not worker.is_alive() for worker in workers))
            self.assertEqual(len(successes), 1)
            self.assertEqual(len(errors), 1)
            self.assertEqual(len(list(fixture.home.glob('prepare-publication-*.image'))), 1)
            fixture.record = recovery.read(fixture.home, 'record.json')
            fixture.prepared = recovery.read(fixture.run, 'run.json')
            self.assertEqual(fixture.prepared[recovery.REFERENCE], successes[0]['record'])
            self.assertEqual(recovery.codec.raw_digest((fixture.home / 'record.json').read_bytes()),
                successes[0]['record']['record_digest'])
            row, after = fixture.reservation()
            self.start(fixture, 'reservation', row=row, after=recovery._json_bytes(after))
            barrier = threading.Barrier(2)
            closings, closing_errors = [], []
            def closer():
                try:
                    barrier.wait(timeout=10)
                    closings.append(recovery.reconcile(fixture.root, fixture.run, retained_capture=capture))
                except (ValueError, OSError, RuntimeError) as error:
                    closing_errors.append(str(error))
            workers = [threading.Thread(target=closer) for _ in range(2)]
            for worker in workers: worker.start()
            for worker in workers: worker.join(timeout=20)
            self.assertTrue(all(not worker.is_alive() for worker in workers))
            self.assertEqual(len(closings) + len(closing_errors), 2)
            self.assertGreaterEqual(len(closings), 1)
            self.assertTrue(all(not value['retry_authorized'] and value['released'] == 0 for value in closings))
            self.assertTrue(all('coordinator_busy' in error for error in closing_errors))
            for _ in range(3):
                self.finish(fixture, capture, 'reservation')
            self.assertEqual(len(recovery.read(fixture.run, 'run.json')['capability_selection']['calls']), 13)


if __name__ == '__main__':
    unittest.main()
