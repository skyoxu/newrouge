"""Real-file tests for auxiliary prepared/reserved operation persistence."""
import base64
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_codec as codec
import _planning_apply_journal as journal
import _planning_skill_common as common
from _planning_skill_common import atomic_json


class AdoptionJournalTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get('ADOPTION_TEST_TEMP'))
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.target = self.root / 'data/target.json'
        self.target.parent.mkdir()
        self.target.write_bytes(b'{"old":true}\n')
        ref = {'path': 'proof/input.json', 'schema_version': 'fixture.v1',
               'raw_digest': codec.raw_digest(b'original')}
        self.request = {'schema_version': 'newrouge.b-route-adoption-request.v1',
            'operation_id': 'OP-1', 'material': {'planner': 'mvg', 'run_id': 'fixture',
                'handoff_ref': ref, 'protection_ref': ref, 'authority_refs': [ref],
                'identity_alignment': {'plan': {}, 'binding': {}, 'requirements': [], 'flows': [], 'tasks': []},
                'target_templates': [{'payload': {'preserve': [True, 1, '1']}}], 'lineage_refs': []},
            'review_ref': ref}
        self.raw = (json.dumps(self.request, ensure_ascii=False, indent=2) + '\n').encode()
        payload = {'new': True, 'text': '\u03c0'}
        self.frozen = {'request': deepcopy(self.request), 'allocations': {'plan_id': 'PLAN-1', 'revision': 1},
            'scope_ids': ['plan:PLAN-1'], 'authority_refs': [ref], 'targets': [{
                'path': 'data/target.json', 'schema_version': 'fixture.v1',
                'before_raw_digest': codec.raw_digest(self.target.read_bytes()), 'after_payload': payload,
                'after_raw_digest': codec.raw_digest((json.dumps(payload, ensure_ascii=False, indent=2) + '\n').encode()),
                'verification_mode': 'immutable_bytes'}]}

    def prepare(self):
        return journal.prepare_operation(self.root, operation_id='OP-1', request_raw=self.raw,
                                         frozen=deepcopy(self.frozen))

    def operation_path(self):
        key = codec.raw_digest(b'OP-1').split(':')[1]
        return self.root / 'logs/ci/b-route-operations/operations' / key / 'operation.json'

    def index_path(self):
        return self.root / 'logs/ci/b-route-operations/pending.json'

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def assert_reject_unchanged(self, function, *args, **kwargs):
        before = self.snapshot()
        with self.assertRaises(codec.CodecError):
            function(*args, **kwargs)
        self.assertEqual(before, self.snapshot())

    def test_empty_inspection_and_full_prepare_replay_preserve_original_bytes(self):
        (self.root / 'logs/ci/b-route-operations/locks/metadata').mkdir(parents=True)
        (self.root / 'logs/ci/b-route-operations/locks/metadata/capability-coordinator.lock').write_bytes(b'0')
        self.assertEqual([], journal.operation_inventory(self.root))
        self.assert_reject_unchanged(journal.read_operation, self.root, operation_id='OP-1')
        self.assertFalse((self.root / 'logs/ci/b-route-operations/operations').exists())
        target_before = self.target.read_bytes()
        result = self.prepare()
        self.assertEqual('prepared', result['state'])
        self.assertEqual(self.raw, base64.b64decode(result['request_raw_base64']))
        old = self.snapshot()
        equivalent = json.dumps(self.request, separators=(',', ':'), sort_keys=True).encode()
        replacement = deepcopy(self.frozen)
        replacement['allocations']['plan_id'] = 'MUST-NOT-ALLOCATE-AGAIN'
        self.assertEqual(result, journal.prepare_operation(self.root, operation_id='OP-1',
            request_raw=equivalent, frozen=replacement))
        self.assertEqual(old, self.snapshot())
        self.assertEqual(target_before, self.target.read_bytes())
        self.assertEqual([result], journal.operation_inventory(self.root))

    def test_same_id_changed_complete_request_and_unsafe_freeze_reject_before_write(self):
        self.prepare()
        changed = deepcopy(self.request)
        changed['material']['target_templates'][0]['payload']['preserve'].reverse()
        self.assert_reject_unchanged(journal.prepare_operation, self.root, operation_id='OP-1',
            request_raw=json.dumps(changed).encode(), frozen=self.frozen)
        for path in ('../outside.json', 'data/CON.json', 'data/bad.json.', 'C:/outside.json'):
            with self.subTest(path=path):
                frozen = deepcopy(self.frozen)
                frozen['targets'][0]['path'] = path
                frozen['request']['operation_id'] = 'OP-2'
                self.assert_reject_unchanged(journal.prepare_operation, self.root, operation_id='OP-2',
                    request_raw=self.raw.replace(b'OP-1', b'OP-2'), frozen=frozen)

    def test_existing_tampered_envelopes_are_never_rebuilt(self):
        original = self.prepare()
        for key, value in (('request_raw_digest', 'sha256:' + '0' * 64),
                           ('request_digest', 'sha256:' + '0' * 64),
                           ('frozen_digest', 'sha256:' + '0' * 64),
                           ('codec_version', 'unknown'), ('state', 'complete'),
                           ('request_raw_base64', 'not-base64!')):
            with self.subTest(field=key):
                tampered = deepcopy(original)
                tampered[key] = value
                atomic_json(self.operation_path(), tampered)
                self.assert_reject_unchanged(journal.read_operation, self.root, operation_id='OP-1')
                self.assert_reject_unchanged(journal.prepare_operation, self.root, operation_id='OP-1',
                    request_raw=self.raw, frozen=self.frozen)
                atomic_json(self.operation_path(), original)

    def test_index_missing_or_mismatched_and_orphan_directory_block_inventory(self):
        self.prepare()
        index = self.index_path().read_bytes()
        self.index_path().unlink()
        self.assert_reject_unchanged(journal.operation_inventory, self.root)
        self.index_path().write_bytes(index)
        value = codec.strict_json_loads(index)
        value['operations'][0]['state'] = 'reserved'
        atomic_json(self.index_path(), value)
        self.assert_reject_unchanged(journal.operation_inventory, self.root)
        self.index_path().write_bytes(index)
        orphan = self.operation_path().parent.parent / ('f' * 64)
        orphan.mkdir()
        self.assert_reject_unchanged(journal.operation_inventory, self.root)

    def test_reserve_is_monotone_byte_stable_and_never_applies_targets(self):
        before = self.prepare()
        target_before = self.target.read_bytes()
        result = journal.reserve_operation(self.root, operation_id='OP-1')
        self.assertEqual({**before, 'state': 'reserved'}, result)
        snapshot = self.snapshot()
        self.assertEqual(result, journal.reserve_operation(self.root, operation_id='OP-1'))
        self.assertEqual(snapshot, self.snapshot())
        self.assertEqual(target_before, self.target.read_bytes())

    def test_index_write_failure_is_retained_and_blocks_later_replay(self):
        original_write = journal.atomic_json
        def fail_index(path, payload):
            if path == self.index_path():
                raise OSError('controlled index failure')
            return original_write(path, payload)
        with patch.object(journal, 'atomic_json', side_effect=fail_index):
            with self.assertRaises(codec.CodecError):
                self.prepare()
        self.assertTrue(self.operation_path().is_file())
        self.assertFalse(self.index_path().exists())
        self.assert_reject_unchanged(journal.prepare_operation, self.root, operation_id='OP-1',
            request_raw=self.raw, frozen=self.frozen)

    def test_reserved_envelope_with_old_index_is_not_silently_repaired(self):
        original = self.prepare()
        original_write = journal.atomic_json
        def fail_index(path, payload):
            if path == self.index_path():
                raise OSError('controlled reserve index failure')
            return original_write(path, payload)
        with patch.object(journal, 'atomic_json', side_effect=fail_index):
            with self.assertRaises(codec.CodecError):
                journal.reserve_operation(self.root, operation_id='OP-1')
        actual = codec.strict_json_loads(self.operation_path().read_bytes())
        self.assertEqual({**original, 'state': 'reserved'}, actual)
        self.assert_reject_unchanged(journal.reserve_operation, self.root, operation_id='OP-1')

    def test_long_windows_operation_root_rejects_before_creating_store(self):
        root = self.root / ('long-fixture-' + 'x' * 100)
        root.mkdir()
        before = list(root.iterdir())
        with self.assertRaises(codec.CodecError):
            journal.prepare_operation(root, operation_id='OP-1', request_raw=self.raw, frozen=self.frozen)
        self.assertEqual(before, list(root.iterdir()))

    def test_92_character_target_prepares_and_reserves_with_short_unique_temporary(self):
        # Same absolute root length as the real target, in a NEW neutral fixture.
        units = len(str(self.root).encode('utf-16-le')) // 2
        padding = 92 - units - 1
        self.assertGreater(padding, 0, 'ADOPTION_TEST_TEMP must be a Root-owned short fixture parent')
        root = self.root / ('t' * padding)
        root.mkdir()
        target = root / 'data/target.json'
        target.parent.mkdir()
        before = self.target.read_bytes()
        target.write_bytes(before)
        operation = root / journal._operation_ref('OP-1')
        self.assertGreaterEqual(len(str(operation)) + 69, 259)
        self.assertTrue(common.atomic_json_win32_paths_fit(operation))
        prepared = journal.prepare_operation(root, operation_id='OP-1', request_raw=self.raw,
                                             frozen=deepcopy(self.frozen))
        self.assertEqual(prepared['state'], 'prepared')
        self.assertEqual(self.raw, base64.b64decode(prepared['request_raw_base64']))
        reserved = journal.reserve_operation(root, operation_id='OP-1')
        self.assertEqual(reserved, {**prepared, 'state': 'reserved'})
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse(list(root.rglob('.atomic-*.tmp')))

    def test_frozen_digest_scope_order_target_alias_and_after_bytes_are_checked(self):
        for mutation in ('unsorted', 'duplicate_scope', 'target_alias', 'target_case_alias', 'after_digest', 'unknown_field'):
            with self.subTest(mutation=mutation):
                value = deepcopy(self.frozen)
                if mutation == 'unsorted':
                    value['scope_ids'] = ['z', 'a']
                elif mutation == 'duplicate_scope':
                    value['scope_ids'] *= 2
                elif mutation == 'target_alias':
                    value['targets'].append({**value['targets'][0], 'path': 'data/./target.json'})
                elif mutation == 'target_case_alias':
                    value['targets'].append({**value['targets'][0], 'path': 'DATA/TARGET.JSON'})
                elif mutation == 'after_digest':
                    value['targets'][0]['after_raw_digest'] = 'sha256:' + '0' * 64
                else:
                    value['new_private_interpretation'] = True
                self.assert_reject_unchanged(journal.prepare_operation, self.root, operation_id='OP-1',
                    request_raw=self.raw, frozen=value)

    def test_hardlinked_record_and_aliased_formal_target_are_not_accepted(self):
        self.prepare()
        alias = self.root / 'record-alias.json'
        os.link(self.operation_path(), alias)
        self.assert_reject_unchanged(journal.read_operation, self.root, operation_id='OP-1')
        alias.unlink()
        os.link(self.target, self.root / 'data/alias.json')
        request = deepcopy(self.request)
        request['operation_id'] = 'OP-2'
        frozen = deepcopy(self.frozen)
        frozen['request'] = request
        frozen['targets'].append({**frozen['targets'][0], 'path': 'data/alias.json'})
        self.assert_reject_unchanged(journal.prepare_operation, self.root, operation_id='OP-2',
            request_raw=json.dumps(request).encode(), frozen=frozen)

    def test_digest_with_final_newline_rejects_before_any_store_write(self):
        for ordinal, field in enumerate(('before', 'authority_ref', 'request_ref'), start=1):
            with self.subTest(field=field):
                operation_id = 'OP-DIGEST-' + str(ordinal)
                request = deepcopy(self.request)
                request['operation_id'] = operation_id
                frozen = deepcopy(self.frozen)
                if field == 'before':
                    frozen['targets'][0]['before_raw_digest'] += '\n'
                elif field == 'authority_ref':
                    frozen['authority_refs'][0]['raw_digest'] += '\n'
                else:
                    request['material']['handoff_ref']['raw_digest'] += '\n'
                frozen['request'] = request
                self.assert_reject_unchanged(journal.prepare_operation, self.root,
                    operation_id=operation_id, request_raw=json.dumps(request).encode(), frozen=frozen)
        self.assertFalse((self.root / 'logs').exists())


class AtomicJSONPathTests(unittest.TestCase):
    """Real owned files/threads; faults never import a native/model owner."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(dir=os.environ.get('ADOPTION_TEST_TEMP'))
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).absolute()

    def test_exact_old_json_bytes_and_fsync_before_same_directory_replace(self):
        target = self.root / 'state.json'
        old = b'{"old":true}\n'
        target.write_bytes(old)
        payload = {'unicode': '雪\r\n', 'typed': [True, 1, -0.0], 'ordered': {'b': 2, 'a': 1}}
        expected = (json.dumps(payload, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        events = []
        real_fsync, real_replace = common.os.fsync, Path.replace
        def fsync(fd):
            events.append(('fsync', os.fstat(fd).st_ino))
            return real_fsync(fd)
        def replace(source, destination):
            self.assertEqual(source.parent, target.parent)
            self.assertEqual(Path(destination), target)
            self.assertRegex(source.name, r'^\.atomic-[0-9a-f]{32}\.tmp$')
            self.assertEqual(len(source.name), 44)
            self.assertEqual(source.read_bytes(), expected)
            self.assertEqual(target.read_bytes(), old)
            self.assertIn(('fsync', source.stat().st_ino), events)
            events.append(('replace', source.name))
            return real_replace(source, destination)
        with patch.object(common.os, 'fsync', fsync), patch.object(Path, 'replace', replace):
            common.atomic_json(target, payload)
        self.assertEqual(target.read_bytes(), expected)
        self.assertFalse(list(self.root.glob('.atomic-*.tmp')))

    def test_capacity_covers_absolute_relative_utf16_nul_final_and_temporary(self):
        base_units = len(str(self.root).encode('utf-16-le')) // 2
        # 213 parent units + separator + 44-char temporary + NUL = 259.
        parent = self.root / ('p' * (213 - base_units - 1))
        target = parent / 'a.json'
        temporary = common.atomic_json_temp_path(target, '0' * 32)
        self.assertEqual(len(str(temporary).encode('utf-16-le')) // 2 + 1, 259)
        self.assertTrue(common.atomic_json_win32_paths_fit(target))
        non_bmp_parent = parent.with_name(parent.name[:-1] + '\U0001f600')
        self.assertEqual(len(str(non_bmp_parent)), len(str(parent)))
        self.assertFalse(common.atomic_json_win32_paths_fit(non_bmp_parent / 'a.json'))
        # A short temporary never licenses an overlong final basename/path.
        self.assertFalse(common.atomic_json_win32_paths_fit(parent / ('f' * 80 + '.json')))
        self.assertFalse(common.atomic_json_win32_paths_fit(self.root / '\ud800.json'))
        for nonce in ('', 'a' * 31, 'G' * 32, '../' + 'a' * 29):
            with self.assertRaises(ValueError):
                common.atomic_json_temp_path(target, nonce)
        deep = self.root / ('d' * (238 - base_units - 1))
        deep.mkdir()
        previous = Path.cwd()
        try:
            os.chdir(deep)
            self.assertLess(len('a.json'), 20)
            self.assertFalse(common.atomic_json_win32_paths_fit(Path('a.json')))
            if os.name == 'nt':
                with self.assertRaises(OSError):
                    common.atomic_json(Path('a.json'), {'must': 'not write'})
                self.assertEqual(list(deep.iterdir()), [])
        finally:
            os.chdir(previous)

    def test_uuid_collision_and_same_destination_never_delete_or_partially_create(self):
        target = self.root / 'state.json'
        old = b'{"old":true}\n'
        target.write_bytes(old)
        foreign = common.atomic_json_temp_path(target, 'a' * 32)
        foreign.write_bytes(b'other writer owns this temporary')
        with patch.object(common.uuid, 'uuid4', return_value=SimpleNamespace(hex='a' * 32)) as nonce:
            with self.assertRaises(FileExistsError):
                common.atomic_json(target, {'new': 1})
        self.assertEqual(nonce.call_count, 1)
        self.assertEqual(foreign.read_bytes(), b'other writer owns this temporary')
        self.assertEqual(target.read_bytes(), old)
        same = self.root / ('.atomic-' + 'b' * 32 + '.tmp')
        with patch.object(common.uuid, 'uuid4', return_value=SimpleNamespace(hex='b' * 32)) as nonce:
            with self.assertRaisesRegex(OSError, 'equals destination'):
                common.atomic_json(same, {'cannot': 'appear partially'})
        self.assertEqual(nonce.call_count, 1)
        self.assertFalse(same.exists())
        if os.name == 'nt':
            same = self.root / ('.ATOMIC-' + 'C' * 32 + '.TMP')
            with patch.object(common.uuid, 'uuid4', return_value=SimpleNamespace(hex='c' * 32)):
                with self.assertRaisesRegex(OSError, 'equals destination'):
                    common.atomic_json(same, {'case': 'same Windows file'})
            self.assertFalse(same.exists())

    def test_parallel_writers_keep_distinct_closed_temps_and_complete_atomic_results(self):
        """Unserialized real replaces may fail; failure never becomes success."""
        import traceback
        target = self.root / 'state.json'
        old = b'{"old":true}\n'
        target.write_bytes(old)
        payloads = [{'writer': i, 'values': list(range(32)), 'typed': [True, 1, -0.0]} for i in range(4)]
        expected = [(json.dumps(p, ensure_ascii=False, indent=2) + '\n').encode('utf-8') for p in payloads]
        barrier, lock = threading.Barrier(4), threading.Lock()
        names, ready, records = [], [], []
        attempts, recorded_errors = [0] * 4, {}
        real_replace = Path.replace
        def error_record(error):
            return {'type': type(error).__name__, 'errno': getattr(error, 'errno', None),
                    'winerror': getattr(error, 'winerror', None), 'message': str(error),
                    'filename': getattr(error, 'filename', None),
                    'filename2': getattr(error, 'filename2', None),
                    'traceback': ''.join(traceback.format_exception(type(error), error, error.__traceback__))}
        def replace(source, destination):
            # Inspect the real caller's handle state, not just an assumed close.
            frame = sys._getframe(1)
            self.assertIs(frame.f_code, common.atomic_json.__code__)
            self.assertTrue(frame.f_locals['stream'].closed)
            del frame
            self.assertEqual(source.parent, target.parent)
            self.assertEqual(Path(destination), target)
            self.assertRegex(source.name, r'^\.atomic-[0-9a-f]{32}\.tmp$')
            raw = source.read_bytes()
            self.assertIn(raw, expected)
            writer = expected.index(raw)
            # All actual complete temporary files exist before any final rename.
            self.assertEqual(target.read_bytes(), old)
            with lock:
                attempts[writer] += 1
                names.append(source.name)
                ready.append(raw)
            barrier.wait(timeout=10)
            record = {'writer': writer, 'source': str(source), 'destination': str(destination),
                      'source_bytes': len(raw), 'source_digest': codec.raw_digest(raw),
                      'writer_handle_closed': True, 'stage': 'original_Path.replace'}
            try:
                result = real_replace(source, destination)  # No lock, retry or injected error.
            except BaseException as error:
                record.update(status='raised', error=error_record(error))
                with lock:
                    recorded_errors[writer] = error  # Preserve exact exception identity.
                    records.append(record)
                raise
            else:
                record.update(status='returned')
                with lock:
                    records.append(record)
                return result
        succeeded, observed_failed_closed, unexpected = [], [], []
        with patch.object(Path, 'replace', replace), ThreadPoolExecutor(max_workers=4) as pool:
            futures = [pool.submit(common.atomic_json, target, p) for p in payloads]
            for writer, future in enumerate(futures):
                try:
                    value = future.result(timeout=15)
                except PermissionError as error:
                    # Admit only this writer's observed real Windows replace
                    # error. A different cleanup/open/fsync/harness error fails.
                    matching = next((r for r in records if r['writer'] == writer and r['status'] == 'raised'), None)
                    if (os.name == 'nt' and getattr(error, 'winerror', None) == 5
                            and recorded_errors.get(writer) is error and matching is not None
                            and isinstance(error.filename, str) and isinstance(error.filename2, str)
                            and os.path.normcase(error.filename) == os.path.normcase(matching['source'])
                            and os.path.normcase(error.filename2) == os.path.normcase(matching['destination'])):
                        observed_failed_closed.append(writer)
                    else:
                        unexpected.append((writer, error))
                except Exception as error:
                    unexpected.append((writer, error))
                else:
                    if value is None:
                        succeeded.append(writer)
                    else:
                        unexpected.append((writer, AssertionError('atomic_json must return None')))
        # Emit every original API failure into the real TestResult stream even
        # when the concurrency safety property succeeds. No OS failure is hidden.
        receipt = {'schema_version': 'atomic-json.concurrent-observation.v1',
                   'writers': 4, 'attempts_by_writer': attempts,
                   'api_success_writers': sorted(succeeded),
                   'actual_WinError5_failed_closed_writers': sorted(observed_failed_closed),
                   'unexpected': [{'writer': i, 'error': error_record(e)} for i, e in unexpected],
                   'replace_observations': sorted(records, key=lambda row: row['writer']),
                   'all_api_writes_succeeded': len(succeeded) == 4,
                   'retry_observed': any(count > 1 for count in attempts),
                   'WinError5_unique_cause': 'not established'}
        stream = getattr(getattr(getattr(self, '_outcome', None), 'result', None), 'stream', None)
        message = '\nATOMIC_CONCURRENCY_OBSERVATION ' + json.dumps(receipt, ensure_ascii=False, sort_keys=True) + '\n'
        if stream is not None:
            stream.write(message)
            stream.flush()
        else:
            print(message, end='', flush=True)
        if unexpected:
            raise unexpected[0][1]
        self.assertEqual(attempts, [1, 1, 1, 1])
        self.assertEqual(len(set(names)), 4)
        self.assertCountEqual(ready, expected)
        self.assertEqual(len(records), 4)
        self.assertEqual(len(succeeded) + len(observed_failed_closed), 4)
        self.assertGreaterEqual(len(succeeded), 1, 'At least one real original replace/API must succeed')
        self.assertTrue(set(succeeded) <= {r['writer'] for r in records if r['status'] == 'returned'})
        self.assertIn(target.read_bytes(), [expected[i] for i in succeeded])
        self.assertFalse(list(self.root.glob('.atomic-*.tmp')))

    def test_serialization_partial_write_fsync_and_replace_failures_keep_old_bytes(self):
        target = self.root / 'state.json'
        old = b'{"old":true}\n'
        target.write_bytes(old)
        with self.assertRaises(TypeError):
            common.atomic_json(target, {'not_json': object()})
        self.assertEqual(target.read_bytes(), old)
        self.assertFalse(list(self.root.glob('.atomic-*.tmp')))
        real_open = Path.open
        class PartialWrite:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.stream.close()
            def fileno(self):
                return self.stream.fileno()
            def write(self, text):
                self.stream.write(text[:9])
                self.stream.flush()
                raise OSError('controlled partial temporary write')
        def open_partial(path, mode='r', *args, **kwargs):
            stream = real_open(path, mode, *args, **kwargs)
            return PartialWrite(stream) if mode == 'x' and path.name.startswith('.atomic-') else stream
        with patch.object(Path, 'open', open_partial):
            with self.assertRaisesRegex(OSError, 'partial temporary'):
                common.atomic_json(target, {'new': list(range(10))})
        self.assertEqual(target.read_bytes(), old)
        self.assertFalse(list(self.root.glob('.atomic-*.tmp')))
        for owner, name in ((common.os, 'fsync'), (Path, 'replace')):
            with self.subTest(failure=name), patch.object(owner, name, side_effect=OSError('controlled ' + name)):
                with self.assertRaises(OSError):
                    common.atomic_json(target, {'new': name})
            self.assertEqual(target.read_bytes(), old)
            self.assertFalse(list(self.root.glob('.atomic-*.tmp')))

    def test_failure_or_success_never_cleans_foreign_replacement_of_old_temp_name(self):
        real_replace = Path.replace
        payload = {'new': 'complete'}
        expected = (json.dumps(payload, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
        for index, mode in enumerate(('before-replace', 'after-replace-error', 'after-replace-success')):
            with self.subTest(mode=mode):
                target = self.root / ('state' + str(index) + '.json')
                target.write_bytes(b'old')
                foreign = self.root / ('foreign' + str(index))
                foreign.write_bytes(b'foreign inode, must survive')
                names = []
                def replace(source, destination):
                    names.append(source)
                    if mode != 'before-replace':
                        real_replace(source, destination)
                    real_replace(foreign, source)  # Pre-existing distinct inode.
                    if mode != 'after-replace-success':
                        raise OSError('controlled ambiguous replacement outcome')
                    return Path(destination)
                with patch.object(Path, 'replace', replace):
                    if mode == 'after-replace-success':
                        common.atomic_json(target, payload)
                    else:
                        with self.assertRaisesRegex(OSError, 'ambiguous replacement'):
                            common.atomic_json(target, payload)
                self.assertEqual(len(names), 1)
                self.assertEqual(names[0].read_bytes(), b'foreign inode, must survive')
                self.assertEqual(target.read_bytes(), b'old' if mode == 'before-replace' else expected)

    def test_unknown_file_identity_retains_unpublished_temp_instead_of_guessing_ownership(self):
        target = self.root / 'state.json'
        target.write_bytes(b'old')
        real_fstat = common.os.fstat
        def unknown_identity(fd):
            info = real_fstat(fd)
            return SimpleNamespace(st_dev=info.st_dev, st_ino=0)
        with patch.object(common.os, 'fstat', unknown_identity), \
             patch.object(common.os, 'fsync', side_effect=OSError('controlled failure with unknown identity')):
            with self.assertRaises(OSError):
                common.atomic_json(target, {'unpublished': True})
        self.assertEqual(target.read_bytes(), b'old')
        self.assertEqual(len(list(self.root.glob('.atomic-*.tmp'))), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
