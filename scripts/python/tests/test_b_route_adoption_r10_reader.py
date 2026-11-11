"""Frozen-reader contract tests with explicitly mocked native witnesses only."""
from contextlib import contextmanager, nullcontext
from copy import deepcopy
import hashlib
import io
import json
import os
import importlib.util
from pathlib import Path
import subprocess
import py_compile
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_frozen_native_reader as reader


def raw(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


class AdoptionR10ReaderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('FROZEN_READER_TEST_TEMP'))
        self.addCleanup(self.temp.cleanup)
        self.task = Path(self.temp.name)
        self.root = self.task / 'artifact'
        self.source = self.task / 'r10'
        self.source.mkdir()
        self.root.mkdir()
        self.patch = patch.multiple(reader, TASK_ROOT=self.task, SOURCE_ROOT=self.source)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.dependencies = patch.object(reader, '_dependencies', return_value=[])
        self.dependencies.start()
        self.addCleanup(self.dependencies.stop)
        # Explicit fake checked-loader context; real source transport has
        # separate owned-child tests and is never authenticated by this fixture.
        self.authentication = patch.object(reader, '_adoption_source_digest',
            reader.digest(reader.READER.read_bytes()), create=True)
        self.authentication.start()
        self.addCleanup(self.authentication.stop)
        self.run = self.root / 'logs/ci/capability-planning/synthetic'
        self.prepared = {'input_identity': 'synthetic-input', 'inputs': {'dependencies': {'files': {}, 'globs': []}}}
        self.state = {'schema_version': 'newrouge.b-route-planning-run.v2', 'input_stage': '3b',
            'selection_status': 'selected', 'run_id': 'synthetic',
            'planning_runtime': {'planner': 'capabilities', 'input_identity': 'synthetic-input',
                'frozen_sha256': reader.digest(reader.canonical(self.prepared)), 'prepared_ref': 'preparation/prepared.json'},
            'b_route_execution_transition': {'current_source_root': str(self.source), 'current_commit': reader.SOURCE_COMMIT},
            'b_route_execution_history': {'r7': {'retained': 'r7'}, 'r8': {'retained': 'r8'}, 'r9': {'retained': 'r9'}},
            'b_route_partial_generation_recovery': {'retained': 'original partial'},
            'b_route_input_path_recovery': {'retained': 'p1'},
            'runner_configuration': {'backend': 'isolated-runner', 'backend_info': {'requested_reasoning_effort': 'high'},
                'runner': str(self.task / 'r5/scripts/python/codex_isolated_model_runner.py')},
            'capability_selection': {'total_invocations': 9, 'calls': [{'number': i,
                'request_identity': {'execution_binding_path': 'binding-' + str(i) + '.json'},
                'outcome': {'status': 'failed' if i == 6 else 'completed'}} for i in range(1, 10)],
                'selected': [{'admissions': {'candidate-1': {'synthetic': True}, 'candidate-2': {'synthetic': True}}}]}}
        self.handoff = {'schema_version': 'newrouge.b-route-planning-handoff.v1', 'run_id': 'synthetic',
            'proposal': {'synthetic': 'complete original proposal'}, 'provider_model': 'unknown', 'provider_dispatches': 'unknown'}
        self.write(self.run / 'run.json', self.state)
        self.write(self.run / 'handoff.json', self.handoff)
        self.write(self.root / 'preparation/prepared.json', self.prepared)
        self.source_file = self.source / 'scripts/python/native_source.py'
        self.write(self.source_file, {'synthetic': 'frozen source'})
        self.external = self.task / 'external-3a/proof.json'
        self.write(self.external, {'synthetic': 'external current proof'})
        self.request = {'source_root': str(self.source), 'source_commit': reader.SOURCE_COMMIT, 'artifact_root': str(self.root),
            'planner': 'capabilities', 'run_id': 'synthetic', 'expected_run_raw_digest': reader.digest((self.run / 'run.json').read_bytes()),
            'expected_handoff_ref': {'path': 'logs/ci/capability-planning/synthetic/handoff.json',
                'schema_version': self.handoff['schema_version'], 'raw_digest': reader.digest((self.run / 'handoff.json').read_bytes())},
            'dependency_paths': [], 'reader_path': str(reader.READER), 'reader_raw_digest': reader.digest(reader.READER.read_bytes())}

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw(value))

    def fake_witness(self, request, state, audit):
        self.assertEqual(self.state, state)
        for path in (self.source_file, self.external, self.root / 'preparation/prepared.json', self.root / 'optional-absent.json'):
            audit._pin_file(path)
        for path in (self.source_file.parent, self.external.parent, self.run):
            audit._pin_directory(path)
        return deepcopy(self.handoff), deepcopy(self.prepared)

    def capture(self):
        audit = reader._Audit([self.root, self.source])
        with patch.object(reader, '_native_witness', side_effect=self.fake_witness):
            return reader._capture_request(reader._request(reader.canonical(self.request)), audit)

    def test_full_original_handoff_prepared_raw_identity_and_external_closure_are_returned(self):
        result = self.capture()
        self.assertEqual(self.handoff, result['handoff'])
        self.assertEqual(self.prepared, result['prepared'])
        self.assertEqual(self.request['expected_run_raw_digest'], result['run_identity']['raw_digest'])
        self.assertEqual('failed', self.state['capability_selection']['calls'][5]['outcome']['status'])
        self.assertEqual(9, len(self.state['capability_selection']['calls']))
        self.assertIn(str(self.external), result['files'])
        self.assertIsNone(result['files'][str(self.root / 'optional-absent.json')])
        with patch.object(reader.subprocess, 'run', side_effect=AssertionError('cheap verifier must not launch a child')):
            reader.verify_capture(self.root, result)

    def test_closed_stdin_duplicate_fields_bad_source_commit_dependency_and_handoff_ref_rejected(self):
        for name, value in [('unknown', True), ('source_root', str(self.task / 'r11')), ('source_commit', '0' * 40),
                            ('dependency_paths', [str(self.task)]), ('expected_handoff_ref', {'approved': True})]:
            request = deepcopy(self.request)
            request[name] = value
            with self.subTest(name=name), self.assertRaises(ValueError):
                reader._request(reader.canonical(request))
        with self.assertRaisesRegex(ValueError, 'duplicate_json_key'):
            reader._request(b'{"source_root":"x","source_root":"y"}')
        with self.assertRaisesRegex(ValueError, 'non_finite_json'):
            reader.strict_json(b'{"bad":NaN}')

    def test_low_unknown_cardinality_and_relabelled_source_fail_before_native_witness(self):
        for case in ('low', 'unknown6', 'unknown9', 'two-vs-three', 'ancestor-root', 'ancestor-commit', 'v1'):
            changed = deepcopy(self.state)
            if case == 'low': changed['runner_configuration']['backend_info']['requested_reasoning_effort'] = 'low'
            elif case.startswith('unknown'): changed['capability_selection']['calls'][int(case[7:]) - 1]['outcome']['status'] = 'unknown'
            elif case == 'two-vs-three': changed['capability_selection']['selected'][0]['admissions']['candidate-3'] = {}
            elif case == 'ancestor-root': changed['b_route_execution_transition']['current_source_root'] = str(self.task / 'r9')
            elif case == 'ancestor-commit': changed['b_route_execution_transition']['current_commit'] = '1' * 40
            else: changed['schema_version'] = 'newrouge.b-route-planning-run.v1'
            with self.subTest(case=case), self.assertRaises(ValueError):
                reader._eligibility(changed, 'capabilities', 'synthetic')
        reader._eligibility(self.state, 'capabilities', 'synthetic')
        mvg = deepcopy(self.state)
        mvg['planning_runtime']['planner'] = 'mvg'
        mvg['capability_selection']['selected'][0]['admissions']['candidate-3'] = {}
        reader._eligibility(mvg, 'mvg', 'synthetic')

    def test_external_source_absence_membership_and_raw_run_drift_rejected_at_persistence(self):
        for case in ('external', 'source', 'absent', 'source-member', 'run'):
            result = self.capture()
            path = {'external': self.external, 'source': self.source_file, 'absent': self.root / 'optional-absent.json',
                    'source-member': self.source_file.parent / 'new-production.py', 'run': self.run / 'run.json'}[case]
            original = path.read_bytes() if path.is_file() else None
            path.write_bytes(b'changed')
            with self.subTest(case=case), self.assertRaises(ValueError):
                reader.verify_capture(self.root, result)
            if original is None:
                path.unlink()
            else:
                path.write_bytes(original)

    def test_native_witness_uses_original_read_only_order_without_locks_or_repair(self):
        @contextmanager
        def transaction(): yield
        calls = []
        state = deepcopy(self.state)
        state.update(checkpoint_strategy='synthetic-checkpoints', recovery={'store': str(self.root / 'logs/ci/mvg-recovery')})
        self.write(self.root / 'logs/ci/mvg-recovery/registry.json', {'epoch': 1, 'revoked': []})
        for name in ('r5', 'r7', 'r8', 'r9'):
            (self.task / name).mkdir()
        for row in state['capability_selection']['calls']:
            if row['outcome']['status'] == 'completed':
                self.write(self.run / row['request_identity']['execution_binding_path'], {'runner_info': {'requested_reasoning_effort': 'high'}})
        def event(name, value=None):
            def execute(*args, **kwargs):
                calls.append((name, kwargs))
                return value
            return execute
        observations = SimpleNamespace(read=Mock(), watch=Mock(), verify=Mock())
        modules = {
            '_b_route_execution_transition': SimpleNamespace(_verification_transaction=transaction,
                _source_manifest=Mock(return_value={'synthetic': 'native source manifest'})),
            '_b_route_planning_runtime': SimpleNamespace(validate_input=event('validate'),
                frozen_input=event('frozen', self.prepared), handoff=event('handoff', self.handoff),
                sources=SimpleNamespace(Observations=Mock(return_value=observations))),
            '_mvg_capability_selection': SimpleNamespace(verified_prefix=event('prefix', ('scopes', 'proposal', 'records')),
                verify_published_chain=event('published')),
            '_mvg_capability_recovery': SimpleNamespace(CHECKPOINT_STRATEGY='synthetic-checkpoints', assert_active_chain=event('active'))}
        for name, module in modules.items():
            module.__name__, module.__file__ = name, str(self.source / 'scripts/python' / (name + '.py'))
        with patch.dict(sys.modules, modules), patch.object(reader, '_source_commands', return_value=[]), \
                patch.object(reader, '_independent_source', return_value={'synthetic': 'independent frozen source witness'}), \
                patch.object(reader, '_install_source_only'), \
                patch.object(reader, '_authenticated_original_code', return_value='synthetic unchanged original code'), \
                patch.object(reader, '_original_transport', side_effect=lambda *args: nullcontext()) as transport:
            # This method isolates native ordering; separate owned-child cases
            # exercise the real source-authenticated transport boundary.
            for name in list(sys.modules):
                if (name.startswith(('_b_route_', '_mvg_', '_planning_'))
                        and name != reader.__name__ and name not in modules):
                    del sys.modules[name]
            result = reader._native_witness(self.request, state, reader._Audit([self.root]))
            self.assertEqual((self.handoff, self.prepared), result)
            transport.assert_called_once_with('synthetic unchanged original code', [], self.source)
            self.assertEqual('prefix', calls[0][0])
            self.assertEqual({'verify_history': True, 'recover_counters': False, 'check_originals': True}, calls[0][1])
            self.assertEqual(['prefix', 'validate', 'published', 'active', 'frozen', 'handoff'], [row[0] for row in calls])
            calls.clear()
            modules['_mvg_capability_selection'].verified_prefix = Mock(side_effect=ValueError('missing native counter'))
            with self.assertRaisesRegex(ValueError, 'missing native counter'):
                reader._native_witness(self.request, state, reader._Audit([self.root]))
            self.assertEqual([], calls)
            modules['_b_route_planning_runtime'].__file__ = str(self.task / 'r11/scripts/python/_b_route_planning_runtime.py')
            with self.assertRaisesRegex(ValueError, 'native_module_origin_changed'):
                reader._native_witness(self.request, state, reader._Audit([self.root]))

    def test_independent_source_check_precedes_import_and_rejects_raw_or_membership_drift(self):
        name = self.source_file.relative_to(self.source).as_posix()
        content = b'synthetic_frozen_source = True\n'
        blob = hashlib.sha1(b'blob ' + str(len(content)).encode('ascii') + b'\0' + content).hexdigest()
        tree = ('100644 blob ' + blob + '\t' + name).encode() + b'\0'
        def attributes(eol):
            values = {'text': 'set', 'eol': eol, 'filter': 'unspecified', 'working-tree-encoding': 'unspecified', 'ident': 'unspecified'}
            return b''.join(name.encode() + b'\0' + key.encode() + b'\0' + value.encode() + b'\0' for key, value in values.items())
        for case in ('valid-lf', 'valid-explicit-crlf', 'unproven-crlf', 'raw-change', 'head-member', 'untracked'):
            self.source_file.write_bytes(content.replace(b'\n', b'\r\n') if 'crlf' in case else b'changed' if case == 'raw-change' else content)
            values = [reader.SOURCE_COMMIT.encode() + b'\n', tree, tree + (b'100644 blob ' + blob.encode() + b'\tnew.py\0' if case == 'head-member' else b''),
                      attributes('crlf' if case == 'valid-explicit-crlf' else 'lf'), b'extra.py\0' if case == 'untracked' else b'']
            results = [SimpleNamespace(returncode=0, stdout=value, stderr=b'') for value in values]
            with self.subTest(case=case), patch.object(reader.shutil, 'which', return_value='git'), \
                    patch.object(reader.subprocess, 'run', side_effect=results) as invoke:
                if case.startswith('valid'):
                    manifest = reader._independent_source(reader._Audit([]))
                    self.assertEqual({name: reader.digest(self.source_file.read_bytes())}, manifest)
                    self.assertEqual(5, invoke.call_count)
                else:
                    with self.assertRaises(ValueError): reader._independent_source(reader._Audit([]))

    def test_audit_actual_child_denies_write_and_unapproved_process_without_side_effects(self):
        target = self.task / 'must-not-exist.txt'
        code = ('import pathlib,sys,json;sys.path.insert(0,' + repr(str(reader.READER.parent)) + ');'
                'import _b_route_frozen_native_reader as r; a=r._Audit([]);sys.addaudithook(a.check);'
                'p=pathlib.Path(sys.argv[1]);results=[]\n'
                'for action in (lambda:p.write_bytes(b"forbidden"),lambda:r.subprocess.run([sys.executable,"--version"])):\n'
                ' try: action();results.append(False)\n'
                ' except ValueError: results.append(True)\n'
                'print(json.dumps(results))')
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code, str(target)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
        self.assertEqual(0, result.returncode, result.stderr.decode(errors='replace'))
        self.assertEqual([True, True], json.loads(result.stdout))
        self.assertFalse(target.exists())
        audit = reader._Audit([])
        for event, arguments in [('socket.connect', (None,)), ('os.mkdir', (str(target),)),
                                  ('open', (str(self.task / 'sessions/fake.json'), 'r', 0))]:
            with self.subTest(event=event), self.assertRaises(ValueError): audit.check(event, arguments)

    def test_parent_uses_closed_isolated_child_and_refuses_malformed_or_failed_output(self):
        capture = self.capture()
        response = SimpleNamespace(returncode=0, stdout=raw(capture), stderr=b'')
        with patch.object(reader, '_run_reader', return_value=response) as invoke:
            result = reader.capture_completed(self.root, planner='capabilities', run_id='synthetic',
                state_raw=(self.run / 'run.json').read_bytes(), expected_handoff_ref=self.request['expected_handoff_ref'])
            self.assertEqual(capture, result)
            arguments, kwargs = invoke.call_args
            self.assertEqual(['-X', 'dev', '-I', '-S', '-B', '-c'], arguments[0][1:7])
            self.assertEqual(reader._REQUEST_FIELDS, set(reader.strict_json(kwargs['input'])))
            self.assertIn('reader_source_changed_before_execution', arguments[0][-1])
            self.assertNotIn('import _b_route_frozen_native_reader as r', arguments[0][-1])
            self.assertNotIn('shell', kwargs)
        for response in (SimpleNamespace(returncode=1, stdout=b'', stderr=b'explicit synthetic refusal'),
                         SimpleNamespace(returncode=0, stdout=b'{"approved":true}', stderr=b'')):
            with patch.object(reader, '_run_reader', return_value=response), self.assertRaises(ValueError):
                reader.capture_completed(self.root, planner='capabilities', run_id='synthetic',
                    state_raw=(self.run / 'run.json').read_bytes(), expected_handoff_ref=self.request['expected_handoff_ref'])

    def test_drift_during_native_witness_and_rewritten_result_cannot_substitute_originals(self):
        def changed(request, state, audit):
            result = self.fake_witness(request, state, audit)
            (self.run / 'run.json').write_bytes(b'changed')
            return result
        with patch.object(reader, '_native_witness', side_effect=changed), self.assertRaisesRegex(ValueError, 'original_run_drift'):
            reader._capture_request(self.request, reader._Audit([]))
        self.write(self.run / 'run.json', self.state)
        capture = self.capture()
        capture['handoff'] = {'approved': True}
        capture['result_digest'] = reader.digest(reader.canonical({k: v for k, v in capture.items() if k != 'result_digest'}))
        with self.assertRaisesRegex(ValueError, 'captured_handoff_changed'):
            reader.verify_capture(self.root, capture)

    def poison_cache(self, source, original, poisoned, mode):
        """Create a valid adversarial cache in this synthetic fixture only."""
        self.assertEqual(len(original), len(poisoned))
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(poisoned)
        os.utime(source, (1700000000, 1700000000))
        py_compile.compile(str(source), doraise=True, invalidation_mode=mode)
        source.write_bytes(original)
        os.utime(source, (1700000000, 1700000000))
        return Path(importlib.util.cache_from_source(str(source)))

    def run_synthetic_child(self, code):
        return subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code], stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=30, check=False)

    def test_bootstrap_executes_verified_reader_source_despite_valid_poisoned_caches(self):
        source = self.task / 'bootstrap-fixture/reader_fixture.py'
        original = b'def _main():\n print("GOOD")\n'
        poisoned = b'def _main():\n print("EVIL")\n'
        for mode in (py_compile.PycInvalidationMode.UNCHECKED_HASH, py_compile.PycInvalidationMode.TIMESTAMP):
            cache = self.poison_cache(source, original, poisoned, mode)
            baseline = self.run_synthetic_child('import sys;sys.path.insert(0,' + repr(str(source.parent)) + ');import reader_fixture;r=reader_fixture;r._main()')
            self.assertEqual(0, baseline.returncode, baseline.stderr.decode(errors='replace'))
            self.assertEqual(b'EVIL', baseline.stdout.strip(), 'control proves -B still reads the poisoned cache')
            actual = self.run_synthetic_child(reader._reader_bootstrap(source, reader.digest(original)))
            self.assertEqual(0, actual.returncode, actual.stderr.decode(errors='replace'))
            self.assertEqual(b'GOOD', actual.stdout.strip())
            self.assertEqual(original, source.read_bytes())
            self.assertTrue(cache.is_file(), 'the reader must not remove or repair cache files')
        wrong = self.run_synthetic_child(reader._reader_bootstrap(source, 'sha256:' + '0' * 64))
        self.assertNotEqual(0, wrong.returncode)
        self.assertNotIn(b'GOOD', wrong.stdout)

    def test_source_only_finder_ignores_native_transitive_caches_and_refuses_sourceless_code(self):
        folder = self.task / 'native-source-fixture'
        source = folder / 'transitive.py'
        original, poisoned = b'VALUE="GOOD"\n', b'VALUE="EVIL"\n'
        (folder).mkdir()
        (folder / 'native_entry.py').write_text('import transitive\nVALUE=transitive.VALUE\n', encoding='utf-8')
        for mode in (py_compile.PycInvalidationMode.UNCHECKED_HASH, py_compile.PycInvalidationMode.TIMESTAMP):
            self.poison_cache(source, original, poisoned, mode)
            baseline = self.run_synthetic_child('import sys;sys.path.insert(0,' + repr(str(folder)) + ');import native_entry;print(native_entry.VALUE)')
            self.assertEqual(b'EVIL', baseline.stdout.strip())
            code = reader._SOURCE_ONLY_BOOTSTRAP + '\nimport json\nseen=[]\n' + (
                'sys.addaudithook(lambda event,args: seen.append(str(args[0])) if event=="open" and str(args[0]).startswith('
                + repr(str(folder)) + ') and str(args[0]).endswith(".pyc") else None)\n'
                'sys.path.insert(0,' + repr(str(folder)) + ')\nimport native_entry\nprint(json.dumps([native_entry.VALUE,seen]))')
            actual = self.run_synthetic_child(code)
            self.assertEqual(0, actual.returncode, actual.stderr.decode(errors='replace'))
            self.assertEqual(['GOOD', []], json.loads(actual.stdout))
        clean = folder / 'clean.py'
        clean.write_text('VALUE="SOURCE"\n', encoding='utf-8')
        result = self.run_synthetic_child(reader._SOURCE_ONLY_BOOTSTRAP + '\nsys.path.insert(0,' + repr(str(folder)) + ');import clean;print(clean.VALUE)')
        self.assertEqual(0, result.returncode, result.stderr.decode(errors='replace'))
        self.assertEqual(b'SOURCE', result.stdout.strip())
        lonely = folder / 'lonely.py'
        lonely.write_text('print("EVIL-SOURCELESS")\n', encoding='utf-8')
        py_compile.compile(str(lonely), cfile=str(folder / 'lonely.pyc'), doraise=True)
        lonely.unlink()
        result = self.run_synthetic_child(reader._SOURCE_ONLY_BOOTSTRAP + '\nsys.path.insert(0,' + repr(str(folder)) + ');import lonely')
        self.assertNotEqual(0, result.returncode)
        self.assertIn(b'sourceless_bytecode_forbidden', result.stderr)
        self.assertNotIn(b'EVIL-SOURCELESS', result.stdout)

    def test_original_child_source_only_envelope_preserves_stdin_flags_and_rejects_unwrapped_or_modified_argv(self):
        folder = self.task / 'r5/scripts/python'
        original_source, poisoned = b'VALUE="GOOD"\n', b'VALUE="EVIL"\n'
        source = folder / 'original_transitive.py'
        self.poison_cache(source, original_source, poisoned, py_compile.PycInvalidationMode.UNCHECKED_HASH)
        original_code = ('import json,pathlib,sys\nsys.path.insert(0,' + repr(str(folder))
            + ')\nimport original_transitive\nprint(json.dumps({"value":original_transitive.VALUE,"stdin":json.loads(sys.stdin.buffer.read())}))\n')
        original_argv = [sys.executable, '-I', '-S', '-B', '-c', original_code]
        payload = b'{"unchanged_stdin":{"ordinal":8,"high":true}}'
        baseline = subprocess.run(original_argv, input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual('EVIL', json.loads(baseline.stdout)['value'])
        wrapped = reader._original_argv(original_code, [])
        result = subprocess.run(wrapped, input=payload, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertEqual(0, result.returncode, result.stderr.decode(errors='replace'))
        self.assertEqual({'value': 'GOOD', 'stdin': json.loads(payload)}, json.loads(result.stdout))
        self.assertEqual(original_argv[:5], wrapped[:5])
        self.assertIn(repr(original_code), wrapped[-1])
        self.assertIn(reader.digest(original_code.encode()), wrapped[-1])
        self.assertLess(len(subprocess.list2cmdline(wrapped)), 30000)
        audit = reader._Audit([])
        audit.commands = [wrapped]
        audit.check('subprocess.Popen', (None, wrapped, None, None))
        audit.check('subprocess.Popen', (None, subprocess.list2cmdline(wrapped), None, None))
        for bad in (original_argv, wrapped[:-1] + [wrapped[-1] + '\nprint("EVIL")'], wrapped[:1] + wrapped[2:]):
            with self.subTest(command=bad[:5]), self.assertRaisesRegex(ValueError, 'native_dispatch_forbidden'):
                audit.check('subprocess.Popen', (None, bad, None, None))
        with patch.object(reader.subprocess, 'Popen', return_value='synthetic-process') as launch:
            with reader._original_transport(original_code, []):
                self.assertEqual('synthetic-process', reader.subprocess.Popen(original_argv, stdin=subprocess.PIPE))
            self.assertEqual(wrapped, launch.call_args.args[0])
            self.assertEqual({'stdin': subprocess.PIPE}, launch.call_args.kwargs)
        with self.assertRaisesRegex(ValueError, 'source_only_child_command_too_long'):
            reader._original_argv('x' * 40000, [])

    def test_original_child_code_must_match_independent_source_and_describe_cache_guard_fails_closed(self):
        path = self.source / 'scripts/python/_b_route_execution_transition.py'
        original_code = 'print("UNCHANGED")\n'
        path.write_text('_CHILD = ' + repr(original_code) + '\n', encoding='utf-8')
        audit = reader._Audit([])
        transition = SimpleNamespace(_CHILD=original_code)
        with self.assertRaisesRegex(ValueError, 'not_independently_authenticated'):
            reader._authenticated_original_code(transition, audit)
        audit._pin_file(path)
        self.assertEqual(original_code, reader._authenticated_original_code(transition, audit))
        with self.assertRaisesRegex(ValueError, 'original_child_code_changed'):
            reader._authenticated_original_code(SimpleNamespace(_CHILD='replaced'), audit)
        unrelated = self.task / 'r7/scripts/python/unrelated_fixture.py'
        self.poison_cache(unrelated, b'VALUE="GOOD"\n', b'VALUE="EVIL"\n', py_compile.PycInvalidationMode.UNCHECKED_HASH)
        reader._describe_cache_guard([])  # An unused ancestor's cache grants or blocks nothing.
        original = self.task / 'r5/scripts/python/original_fixture.py'
        self.poison_cache(original, b'VALUE="GOOD"\n', b'VALUE="EVIL"\n', py_compile.PycInvalidationMode.UNCHECKED_HASH)
        runner = self.task / 'r5/scripts/python/codex_isolated_model_runner.py'
        runner.write_text('print("MUST-NOT-EXECUTE")\n', encoding='utf-8')
        describe = [sys.executable, '-B', str(runner), '--describe']
        with patch.object(reader.subprocess, 'Popen', side_effect=AssertionError('describe must be refused before process creation')):
            with reader._original_transport(original_code, []), self.assertRaisesRegex(ValueError, 'describe_unverified_bytecode_forbidden'):
                reader.subprocess.Popen(describe)
        nested_code = 'import subprocess,sys\nsubprocess.run(' + repr(describe) + ',check=True)\n'
        result = subprocess.run(reader._original_argv(nested_code, []), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        self.assertNotEqual(0, result.returncode)
        self.assertIn(b'describe_unverified_bytecode_forbidden', result.stderr)
        self.assertNotIn(b'MUST-NOT-EXECUTE', result.stdout)


class OwnedStdinPipeAuditTests(unittest.TestCase):
    """Real Windows stdin pipes and toy Git only; no native/model process."""
    def setUp(self):
        self.assertEqual('nt', os.name, 'These pipe ownership regressions require actual Windows')
        self.temp = tempfile.TemporaryDirectory(dir=os.environ.get('FROZEN_READER_TEST_TEMP'))
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    @contextmanager
    def hooked(self, audit, before=None, after=None):
        # Python hooks cannot be removed. Deactivate only this test-owned relay;
        # no platform/runner/production hook is replaced, suppressed or removed.
        active = [True]
        def hook(event, args):
            if active[0]:
                if before is not None: before(event, args)
                audit.check(event, args)
                if after is not None: after(event, args)
        sys.addaudithook(hook)
        try:
            yield
        finally:
            active[0] = False

    def git_command(self):
        import shutil
        git = shutil.which('git')
        self.assertIsNotNone(git, 'The explicit toy Git stdin regression requires installed Git')
        (self.root / '.gitattributes').write_bytes(b'*.txt text\n')
        environment = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                           GIT_CONFIG_COUNT='0', GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0')
        prefix = [git, '--no-optional-locks', '-c', 'core.hooksPath=' + os.devnull,
                  '-c', 'core.fsmonitor=false', '-C', str(self.root)]
        initialized = subprocess.run(prefix + ['init', '-q'], env=environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, check=False)
        self.assertEqual(0, initialized.returncode, initialized.stderr.decode(errors='replace'))
        return prefix + ['check-attr', '--stdin', '-z', 'text'], environment

    def test_owned_windows_pipe_and_toy_git_stdin_preserve_transport(self):
        command, environment = self.git_command()
        audit = reader._Audit([]); audit.commands = [command]
        original = subprocess.Popen
        with self.hooked(audit), audit.subprocesses():
            checked = subprocess.run(command, input=b'one.txt\0', stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=15, check=False, env=environment)
        self.assertIs(subprocess.Popen, original)
        self.assertEqual([], audit._pipe_tickets)
        self.assertEqual(0, checked.returncode, checked.stderr.decode(errors='replace'))
        self.assertEqual(b'one.txt\0text\0set\0', checked.stdout)

    def test_unowned_writable_fds_and_stdio_or_process_overrides_reject_before_launch(self):
        import io
        target = self.root / 'unchanged.bin'
        target.write_bytes(b'original')
        fd = os.open(target, os.O_RDWR)
        stream = io.open(fd, 'r+b', closefd=False)
        unowned_read, unowned_write = os.pipe()
        command = [sys.executable, '--version']  # Declared only; every attempt below must reject.
        audit = reader._Audit([]); audit.commands = [command]
        events = []
        def observed(event, args):
            if event == 'subprocess.Popen': events.append(args[1])
        try:
            with self.hooked(audit, before=observed), audit.subprocesses():
                for descriptor in (fd, unowned_write):
                    with self.subTest(descriptor=descriptor), self.assertRaisesRegex(ValueError, 'native_reader_write_forbidden'):
                        io.open(descriptor, 'wb', closefd=False)
                with self.assertRaisesRegex(ValueError, 'native_reader_write_forbidden'):
                    target.write_bytes(b'forbidden')
                for options in ({'stdin':unowned_read}, {'stdout':fd}, {'stderr':fd},
                                {'stdin':stream}, {'stdout':stream}, {'shell':True},
                                {'executable':sys.executable}, {'close_fds':False},
                                {'pass_fds':(unowned_read,)}, {'start_new_session':True},
                                {'process_group':0}, {'creationflags':0x01000000}):
                    with self.subTest(options=options), self.assertRaisesRegex(ValueError, 'native_(?:existing_stdio|process_override)_forbidden'):
                        subprocess.Popen(command, **options)
                with self.assertRaisesRegex(ValueError, 'native_dispatch_forbidden'):
                    subprocess.Popen([sys.executable, '--help'], stdin=subprocess.PIPE)
                for event, arguments in (('socket.connect', (None,)), ('os.system', ('never executed',))):
                    with self.subTest(event=event), self.assertRaisesRegex(ValueError, 'network_or_process_forbidden'):
                        audit.check(event, arguments)
        finally:
            stream.close()
            os.close(fd); os.close(unowned_read); os.close(unowned_write)
        self.assertEqual([], events)
        self.assertEqual([], audit._pipe_tickets)
        self.assertEqual(b'original', target.read_bytes())

    def test_live_constructor_ticket_is_thread_bound_single_use_and_handles_errors(self):
        import io
        import msvcrt
        import stat
        import threading
        command, environment = self.git_command()
        audit = reader._Audit([]); audit.commands = [command]
        other_read, other_write = os.pipe()
        checks = []
        def before(event, args):
            if event != 'open' or type(args[0]) is not int or args[1] not in ('w','wb'): return
            fd, mode, flags = args
            result = []
            worker = threading.Thread(target=lambda:result.append(audit._owned_pipe_open(fd,mode,flags)))
            worker.start(); worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual([False], result)
            self.assertIs(False, audit._owned_pipe_open(other_write,mode,flags))
            self.assertIs(False, audit._owned_pipe_open(-1,mode,flags))
            self.assertIs(False, audit._owned_pipe_open(fd,'a',flags))
            self.assertIs(False, audit._owned_pipe_open(fd,mode,os.O_RDWR))
            with patch.object(os, 'fstat', return_value=SimpleNamespace(st_mode=stat.S_IFREG)):
                self.assertIs(False, audit._owned_pipe_open(fd,mode,flags))
            with patch.object(os, 'fstat', side_effect=OSError('synthetic fstat refusal')):
                self.assertIs(False, audit._owned_pipe_open(fd,mode,flags))
            with patch.object(msvcrt, 'get_osfhandle', side_effect=OSError('synthetic invalid CRT handle')):
                self.assertIs(False, audit._owned_pipe_open(fd,mode,flags))
            with patch.object(msvcrt, 'get_osfhandle', return_value=-1):
                self.assertIs(False, audit._owned_pipe_open(fd,mode,flags))
            checks.append('before')
        def after(event, args):
            if event == 'open' and type(args[0]) is int and args[1] in ('w','wb'):
                self.assertIs(False, audit._owned_pipe_open(*args))
                checks.append('consumed')
        try:
            with self.hooked(audit, before=before, after=after), audit.subprocesses():
                process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, env=environment)
                try:
                    self.assertEqual([], audit._pipe_tickets)
                    # Still-live owned pipe has no authority after __init__.
                    with self.assertRaisesRegex(ValueError, 'native_reader_write_forbidden'):
                        io.open(process.stdin.fileno(), 'wb', closefd=False)
                    output, errors = process.communicate(b'one.txt\0', timeout=15)
                finally:
                    if process.poll() is None: process.kill()
                    process.communicate(timeout=15)
        finally:
            os.close(other_read); os.close(other_write)
        self.assertEqual(['before', 'consumed', 'before'], checks)
        self.assertEqual(0, process.returncode, errors.decode(errors='replace'))
        self.assertEqual(b'one.txt\0text\0set\0', output)
        self.assertEqual([], audit._pipe_tickets)

    def test_constructor_error_revokes_ticket_and_fd_reuse_has_no_write_permission(self):
        import io
        command, environment = self.git_command()
        audit = reader._Audit([]); audit.commands = [command]
        original = subprocess.Popen
        wrapped = []
        def observed(event, args):
            if event == 'open' and type(args[0]) is int and args[1] in ('w','wb'):
                wrapped.append(args[0])
        failure = FileNotFoundError('synthetic launch refusal')
        with self.hooked(audit, after=observed), patch.object(original, '_execute_child', side_effect=failure), audit.subprocesses():
            with self.assertRaises(FileNotFoundError) as caught:
                subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, env=environment)
            self.assertIs(failure, caught.exception)
            self.assertEqual([], audit._pipe_tickets)
            self.assertEqual(1, len(wrapped))
            expired = wrapped[0]
            with self.assertRaises(OSError): os.fstat(expired)
            read_fd, write_fd = os.pipe()
            try:
                if write_fd != expired: os.dup2(write_fd, expired)
                with self.assertRaisesRegex(ValueError, 'native_reader_write_forbidden'):
                    io.open(expired, 'wb', closefd=False)
            finally:
                for fd in {read_fd, write_fd, expired}:
                    try: os.close(fd)
                    except OSError: pass
        self.assertIs(subprocess.Popen, original)
        self.assertEqual([], audit._pipe_tickets)

class BoundedReaderDiagnosticsTests(unittest.TestCase):
    def test_phase_records_are_bounded_payload_free_and_stdout_untouched(self):
        clock = [0.0]
        errors, output = io.StringIO(), io.StringIO()
        with patch.object(reader.time, 'monotonic', side_effect=lambda: clock[0]), \
                patch.object(reader.sys, 'stderr', errors), patch.object(reader.sys, 'stdout', output):
            diagnostics = reader._Diagnostics('reader')
            with diagnostics.phase('prefix'):
                diagnostics.hashed_read(123)
                clock[0] = 29.0
                diagnostics.scanned_directory()
                self.assertEqual(1, diagnostics.records)
                clock[0] = 30.0
                diagnostics.hashed_read(456)
                self.assertEqual(2, diagnostics.records)
                clock[0] = 59.0
                diagnostics.scanned_directory()
                self.assertEqual(2, diagnostics.records)
            with self.assertRaisesRegex(ValueError, 'closed_diagnostic_phase_required'):
                with diagnostics.phase('private-payload-must-never-be-logged'):
                    self.fail('Unrecognized phases cannot enter')
            for _ in range(100):
                with diagnostics.phase('handoff'):
                    pass
            parent = reader._Diagnostics('parent')
            for _ in range(100):
                with parent.phase('reader_child'):
                    pass
        rows = [json.loads(line) for line in errors.getvalue().splitlines()]
        self.assertEqual(64, len(rows))
        self.assertEqual(60, sum(row['scope'] == 'reader' for row in rows))
        self.assertEqual(4, sum(row['scope'] == 'parent' for row in rows))
        self.assertEqual('', output.getvalue())
        self.assertNotIn('private-payload', errors.getvalue())
        fields = {'schema_version', 'scope', 'phase', 'event', 'elapsed_ms', 'phase_elapsed_ms',
                  'hashed_reads', 'hashed_bytes', 'directory_scans'}
        for row in rows:
            self.assertEqual(fields, set(row))
            self.assertEqual('newrouge.b-route-reader-diagnostic.v1', row['schema_version'])
            self.assertIn(row['phase'], reader._DIAGNOSTIC_PHASES)
            self.assertIn(row['event'], {'start', 'end', 'progress'})
            for field in fields - {'schema_version', 'scope', 'phase', 'event'}:
                self.assertIs(type(row[field]), int)
                self.assertGreaterEqual(row[field], 0)
        self.assertEqual('progress', rows[1]['event'])
        self.assertEqual((2, 579, 1), tuple(rows[1][key] for key in
            ('hashed_reads', 'hashed_bytes', 'directory_scans')))
        self.assertEqual([], diagnostics.active)
        self.assertEqual([], parent.active)

    def test_diagnostic_oserror_does_not_mask_validation_failure_or_leave_phase_active(self):
        errors = Mock()
        errors.write.side_effect = OSError('synthetic broken diagnostic pipe')
        validation_failure = ValueError('synthetic validation failure')
        close_observations = []
        with patch.object(reader.sys, 'stderr', errors):
            diagnostics = reader._Diagnostics('reader')
            # Successful validation remains successful even when its start
            # record cannot be written.
            with diagnostics.phase('prefix'):
                result = 'validated'
            self.assertEqual('validated', result)
            with self.assertRaises(ValueError) as caught:
                with diagnostics.phase('handoff'):
                    raise validation_failure
            self.assertIs(validation_failure, caught.exception)
            self.assertEqual([], diagnostics.active)

            @contextmanager
            def original_transaction():
                try:
                    yield
                finally:
                    close_observations.append(diagnostics.active[-1][0])
                    raise validation_failure

            with self.assertRaises(ValueError) as caught:
                with reader.ExitStack() as closing:
                    with original_transaction():
                        try:
                            pass
                        finally:
                            closing.enter_context(diagnostics.phase('transaction_close'))
            self.assertIs(validation_failure, caught.exception)
        self.assertEqual(['transaction_close'], close_observations)
        self.assertEqual([], diagnostics.active)
        self.assertFalse(diagnostics.enabled)
        self.assertEqual(1, errors.write.call_count)


if __name__ == '__main__':
    unittest.main(verbosity=2)
