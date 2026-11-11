"""Targeted R25 synthetic disk/resource/error checks; no real model qualification."""
import ast
from copy import deepcopy
from contextlib import ExitStack
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_execution_transition as transition
import _b_route_compact_literal as compact
import _b_route_selector_recovery as recovery
import _b_route_planning_runtime as runtime
import _mvg_capability_checkpoint as checkpoint
import _mvg_capability_worker as worker
import _mvg_capability_selection as selection
import _planning_skill_common as common
from scripts.python.tests.test_b_route_selector_recovery import retained_fixture, selector_row


class SemanticClosureTests(unittest.TestCase):
    def roots(self, helper="return flows, blocks", key="return row['namespace'], row['block']"):
        names = ('review_schema', 'review_issues', 'machine', 'generation_schema', 'generation_schemas', 'generation_target')
        return ("def semantic_domain(flows, blocks):\n    " + helper + "\n"
                + "def source_key(row):\n    return key_helper(row)\n"
                + "def key_helper(row):\n    " + key + "\n"
                + "def obligations(flows, blocks):\n    return semantic_domain(flows, blocks)\n"
                + "def qualified_sources(row):\n    return source_key(row)\n"
                + '\n'.join('def ' + name + '():\n    return "original"\n' for name in names))

    def compare(self, original, current):
        with tempfile.TemporaryDirectory() as temp:
            roots = [Path(temp) / name for name in ('old', 'new')]
            for root, source in zip(roots, (original, current)):
                path = root / 'scripts/python/_b_route_planning_runtime.py'
                path.parent.mkdir(parents=True)
                path.write_text(source, encoding='utf-8')
            return transition._semantic_unchanged(*roots)

    def test_unchanged_helper_closure_and_two_flow_contract_remain_bound(self):
        result = self.compare(self.roots(), self.roots())
        self.assertIn('scripts/python/_b_route_planning_runtime.py:semantic_domain', result)
        self.assertIn('scripts/python/_b_route_planning_runtime.py:key_helper', result)

    def test_helper_only_two_flow_truncation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'canonical_semantics_changed'):
            self.compare(self.roots(), self.roots(helper='return flows[:1], blocks'))

    def test_source_namespace_helper_only_mutation_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'canonical_semantics_changed'):
            self.compare(self.roots(), self.roots(key="return row['block']"))

    def test_module_attribute_helper_mutation_is_rejected(self):
        """Bind actual helpers behind module aliases, beyond their import statements."""
        with tempfile.TemporaryDirectory() as temp:
            roots = [Path(temp) / name for name in ('old', 'new')]
            for index, root in enumerate(roots):
                directory = root / 'scripts/python'
                directory.mkdir(parents=True)
                source = 'import _planning_skill_common as common\n' + self.roots(helper='return common.semantic_helper(flows, blocks)')
                (directory / '_b_route_planning_runtime.py').write_text(source, encoding='utf-8')
                (directory / '_planning_skill_common.py').write_text(
                    'def semantic_helper(flows, blocks):\n    return ' + ('flows' if index == 0 else 'flows[:1]') + ', blocks\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'canonical_semantics_changed'):
                transition._semantic_unchanged(*roots)

    def test_common_host_fault_boundary_does_not_allow_other_helpers(self):
        with tempfile.TemporaryDirectory() as temp:
            old, new = Path(temp) / 'old', Path(temp) / 'new'
            original = 'def canonical_sha(value):\n    return value\ndef run_isolated_model():\n    return 1\n'
            for root, text in ((old, original), (new, original.replace('return 1', 'return 2'))):
                path = root / transition._HOST_FAULT_MODULE
                path.parent.mkdir(parents=True)
                path.write_text(text, encoding='utf-8')
            transition._host_fault_boundary(old, new)
            (new / transition._HOST_FAULT_MODULE).write_text(original.replace('return value', 'return None'), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'outside_failure_boundary'):
                transition._host_fault_boundary(old, new)


class CompactResourceTests(unittest.TestCase):
    def packet(self):
        return {'schema_version': compact.CURRENT_SCHEMA, 'keysets': [], 'strings': [], 'shared': [],
                'value': {}, 'sha256': 'sha256:' + '0' * 64}

    def test_small_shared_dag_fanout_rejects_before_any_deepcopy(self):
        packet = self.packet()
        packet['shared'] = [[]] + [[(False, n - 1), (False, n - 1)] for n in range(1, 30)]
        packet['value'] = {'x': (False, 29)}
        with patch.object(compact, '_unshare', side_effect=AssertionError('allocation reached')):
            with self.assertRaisesRegex(ValueError, 'expansion exceeds'):
                compact.loads(compact._literal(packet))

    def test_small_phrase_fanout_rejects_before_join_or_base64(self):
        packet = self.packet()
        packet.update(schema_version=compact.ATOM_SCHEMA, phrases=['a' * 64] +
                      [(compact._TEXT_CONCAT, [(compact._TEXT_PHRASE, n - 1)] * 2) for n in range(1, 30)])
        packet['value'] = {'x': (compact._TEXT_BASE64, (compact._TEXT_PHRASE, 29))}
        with patch.object(compact, '_unpack_text', side_effect=AssertionError('allocation reached')):
            with self.assertRaisesRegex(ValueError, 'expansion exceeds'):
                compact.loads(compact._atom_literal(packet))

    def test_reference_chain_depth_rejects_before_subtree_copy(self):
        packet = self.packet()
        packet['shared'] = [[]] + [(False, n - 1) for n in range(1, 18)]
        packet['value'] = {'x': (False, 17)}
        with patch.object(compact, 'MAX_DEPTH', 12), patch.object(compact, '_unshare', side_effect=AssertionError('allocation reached')):
            with self.assertRaisesRegex(ValueError, 'expansion exceeds'):
                compact.loads(compact._literal(packet))

    def test_expanded_exact_boundary_and_encoded_budget_are_distinct(self):
        packet = self.packet()
        packet['value'] = {'x': 'a' * 10}
        # Corrected weighted cost: 62 value + 10 key/colon/comma + 2 braces.
        # The earlier 72-byte result omitted braces; retain it as historical evidence.
        with patch.object(compact, 'MAX_EXPANDED_BYTES', 74):
            compact._expanded_preflight(packet, compact.CURRENT_SCHEMA)
            compact._json_preflight(packet['value'])
        with patch.object(compact, 'MAX_EXPANDED_BYTES', 73):
            with self.assertRaisesRegex(ValueError, 'expansion exceeds'):
                compact._expanded_preflight(packet, compact.CURRENT_SCHEMA)
            with self.assertRaisesRegex(ValueError, 'input exceeds'):
                compact._json_preflight(packet['value'])
        with patch.object(compact, 'MAX_ENCODED_BYTES', 5):
            with self.assertRaisesRegex(ValueError, 'encoded bytes'):
                compact.loads(compact._literal(packet))

    def test_large_signed_integer_rejects_before_restore_or_input_copy(self):
        for integer in (10 ** 300, -(10 ** 300)):
            for shared in (False, True):
                with self.subTest(negative=integer < 0, shared=shared):
                    packet = self.packet()
                    packet['value'] = {'n': integer}
                    if shared:
                        packet['shared'] = [[integer]]
                        packet['value'] = {'a': (False, 0), 'b': (False, 0)}
                    with patch.object(compact, 'MAX_EXPANDED_BYTES', 200), \
                         patch.object(compact, '_unshare', side_effect=AssertionError('restore reached')), \
                         patch.object(compact, '_copy_aliased', side_effect=AssertionError('input copy reached')):
                        with self.assertRaisesRegex(ValueError, 'expansion exceeds'):
                            compact.loads(compact._literal(packet))
                        with self.assertRaisesRegex(ValueError, 'input exceeds'):
                            compact.dumps({'n': integer}, schema=compact.CURRENT_SCHEMA)

    def test_empty_container_cost_rejects_before_restore_or_input_copy(self):
        for value, limit in (({}, 1), ({'x': []}, 13), ({'empty': [{}, []] * 50}, 200)):
            with self.subTest(limit=limit):
                packet = self.packet()
                packet['value'] = value
                with patch.object(compact, 'MAX_EXPANDED_BYTES', limit), \
                     patch.object(compact, '_unshare', side_effect=AssertionError('restore reached')), \
                     patch.object(compact, '_copy_aliased', side_effect=AssertionError('input copy reached')):
                    with self.assertRaisesRegex(ValueError, 'expansion exceeds'):
                        compact.loads(compact._literal(packet))
                    with self.assertRaisesRegex(ValueError, 'input exceeds'):
                        compact.dumps(value, schema=compact.CURRENT_SCHEMA)

    def test_oversized_string_weight_rejects_before_utf8_encoding(self):
        # Encoding this small surrogate string would raise UnicodeEncodeError;
        # the resource error proves the cheap character bound ran first.
        for value in ({'x': '\ud800' * 40}, {'\ud800' * 40: 'x'}):
            packet = self.packet()
            packet['value'] = value
            with patch.object(compact, 'MAX_EXPANDED_BYTES', 200), \
                 patch.object(compact, '_unshare', side_effect=AssertionError('restore reached')), \
                 patch.object(compact, '_copy_aliased', side_effect=AssertionError('input copy reached')):
                with self.assertRaisesRegex(ValueError, 'expansion exceeds'):
                    compact.loads(compact._literal(packet))
                with self.assertRaisesRegex(ValueError, 'input exceeds'):
                    compact.dumps(value, schema=compact.CURRENT_SCHEMA)

    def test_repetitive_prefix_work_stops_deterministically(self):
        value = {'a': 'a' * 2048 + 'x', 'b': 'a' * 2048 + 'y'}
        with patch.object(compact, 'MAX_ENCODING_WORK', 20_000):
            with self.assertRaisesRegex(ValueError, 'encoding work exceeds'):
                compact.dumps(value, schema=compact.ATOM_SCHEMA)

    def test_literal_matcher_matches_escaped_regex_order_unicode_and_overlap(self):
        cases = [(['ab', 'a'], 'ababa'), (['a', 'ab'], 'ababa'),
                 (['aa', 'a'], 'aaaaa'), (['a', 'aa'], 'aaaaa'),
                 (['bc', 'abcd', 'ab'], 'zabcdabc'), (['aba', 'bab'], 'abababa'),
                 (['ab', 'ab', 'b'], 'zabb'), (['ba', 'a', 'aba'], 'ababa'),
                 (['a.b', 'a', '[x]', '\\', '|', '*', '+', '?'], 'a.b a[x]\\|*+?a.b'),
                 (['a\nb', '\r\n', '\t', 'a'], 'a\nb\r\na\t'),
                 (['\U0001f600x', '\U0001f600', '\u4e2d\u6587', '\u4e2d', 'e\u0301'],
                  '\U0001f600x\U0001f600\u4e2d\u6587\u4e2de\u0301'), (['x'], ''), ([], 'abc')]
        for choices, text in cases:
            with self.subTest(choices=choices, text=text):
                expected = [(match.start(), match.end(), match.group()) for match in
                    re.compile('|'.join(re.escape(phrase) for phrase in choices)).finditer(text)] if choices else []
                actual = list(compact._LiteralMatcher(choices, compact._EncodingWork()).finditer(text))
                self.assertEqual(actual, expected)

    def test_literal_matcher_small_exhaustive_differential(self):
        from itertools import product
        alternatives = ('a', 'b', 'aa', 'ab', 'ba')
        texts = [''.join(chars) for size in range(5) for chars in product('ab', repeat=size)]
        for choices in product(alternatives, repeat=2):
            oracle = re.compile('|'.join(re.escape(phrase) for phrase in choices))
            matcher = compact._LiteralMatcher(choices, compact._EncodingWork())
            for text in texts:
                with self.subTest(choices=choices, text=text):
                    self.assertEqual(list(matcher.finditer(text)),
                        [(match.start(), match.end(), match.group()) for match in oracle.finditer(text)])

    def test_literal_matcher_build_and_scan_stop_on_the_shared_work_budget(self):
        with patch.object(compact, 'MAX_ENCODING_WORK', 16):
            with self.assertRaisesRegex(ValueError, 'encoding work exceeds'):
                compact._LiteralMatcher(['a' * 64], compact._EncodingWork())
        work = compact._EncodingWork()
        matcher = compact._LiteralMatcher(['ab', 'b'], work)
        work.spend(work.remaining - 3)
        with self.assertRaisesRegex(ValueError, 'encoding work exceeds'):
            list(matcher.finditer('ab' * 32))

    def test_small_all_versions_keep_exact_canonical_roundtrip(self):
        value = {'unicode': '\u4e2d\u6587\r\n', 'typed': [False, 0, None], 'rows': [{'same_key': 'complete'}] * 3}
        for schema in (compact.SCHEMA, compact.CURRENT_SCHEMA, compact.ATOM_SCHEMA):
            with self.subTest(schema=schema):
                raw = compact.dumps(value, schema=schema)
                self.assertEqual(compact.loads(raw), value)
                with self.assertRaisesRegex(ValueError, 'Noncanonical'):
                    compact.loads(raw.replace("'value':", "'value': ", 1))


class SelectorTransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.run = self.root / recovery.RUN_REF
        self.run.mkdir(parents=True)
        for name in ('candidates', 'analysis-input', 'capability-selection', 'recovery/m1'):
            (self.run / name).mkdir(parents=True)
        old, state, anchor = retained_fixture()
        for value in (old, state, anchor['original_state']):
            value['capability_selection']['current']['capability_id'] = 'synthetic'
        self.old, self.state, self.anchor = old, state, anchor
        raw = recovery._json_bytes(old)
        self.model = b'{"retained":true}\n'
        (self.run / 'run.json').write_bytes(raw)
        (self.run / 'model-execution.json').write_bytes(self.model)
        anchor['manifest']['files'] = {recovery.RUN_REF + '/run.json': recovery.codec.raw_digest(raw),
                                      recovery.RUN_REF + '/model-execution.json': recovery.codec.raw_digest(self.model)}
        anchor['manifest']['directories'] = [p.relative_to(self.root).as_posix() for p in self.run.rglob('*') if p.is_dir()]
        self.stack = self.enterContext(ExitStack())
        self.stack.enter_context(patch.object(recovery, 'ORIGINAL_RUN_DIGEST', recovery.codec.raw_digest(raw)))
        self.stack.enter_context(patch.object(recovery, '_trusted_anchor', return_value=anchor))
        # Only unavailable original source/proof qualification is synthetic;
        # metadata publication, prefix history, CAS and original locks stay real.
        self.stack.enter_context(patch.object(recovery, '_close_sources'))
        self.stack.enter_context(patch.object(transition, 'validate_transition'))
        self.home = self.run / 'recovery/s1'
        self.home.mkdir()
        self.record = {'schema_version': recovery.SCHEMA, 'run_id': 'm4', 'run_ref': recovery.RUN_REF,
            'anchor_identity': recovery._anchor_identity(), 'previous_run': recovery.image(raw),
            'model_execution_preimage': recovery.image(self.model), 'transition': state['b_route_execution_transition'],
            'history': state['b_route_execution_history'], 'selector_transport_policy': recovery._POLICY,
            'retained_calls': 12, 'maximum_selector_dispatches': 1, 'released': 0}
        reference = {'schema_version': recovery.SCHEMA, 'record_ref': recovery.RUN_REF + '/recovery/s1/record.json',
                     'record_digest': recovery.codec.raw_digest(recovery._json_bytes(self.record)), 'artifact_root': str(self.root)}
        self.prepared = recovery._prepared_state(old, self.record, reference)

    def prepare(self):
        recovery._start_transaction(self.root, 'prepare', self.record,
            recovery._json_bytes(self.old), recovery._json_bytes(self.prepared))

    def test_each_prepare_disk_commit_window_is_idempotently_completed(self):
        # Each subtest uses a distinct on-disk transaction, actual fsync/replace.
        for target in ('claim.json', 'record.json', 'run.json', 'committed.json'):
            with self.subTest(target=target), tempfile.TemporaryDirectory() as temp:
                fixture = SelectorTransactionTests('test_foreign_temporary_still_blocks')
                fixture.setUp()
                try:
                    replace = recovery.os.replace
                    def crash(source, destination):
                        replace(source, destination)
                        if Path(destination).name == target:
                            raise SystemExit('synthetic crash after ' + target)
                    with patch.object(recovery.os, 'replace', side_effect=crash):
                        with self.assertRaises(SystemExit):
                            fixture.prepare()
                    value, operations = recovery._journal(fixture.root, 'prepare', fixture.anchor)
                    recovery._apply_transaction(fixture.root, value, operations)
                    recovery._apply_transaction(fixture.root, value, operations)
                    self.assertEqual(recovery.read(fixture.run, 'run.json'), fixture.prepared)
                    self.assertTrue((fixture.home / 'committed.json').exists())
                    self.assertEqual((fixture.run / 'model-execution.json').read_bytes(), fixture.model)
                finally:
                    fixture.doCleanups()

    def test_public_prepare_disk_validation_and_reconcile_share_one_journal(self):
        """Exercise the public owner with real metadata, CAS, locks and namespace checks."""
        import _b_route_mvg_synthesis_recovery as previous
        for interrupted in (False, True):
            with self.subTest(interrupted=interrupted):
                fixture = SelectorTransactionTests('test_foreign_temporary_still_blocks')
                fixture.setUp()
                try:
                    # setUp's synthetic anchor pin replaces unavailable retained
                    # capture provenance. Its empty namespace is not a prepared run.
                    fixture.home.rmdir()
                    original_run = (fixture.run / 'run.json').read_bytes()
                    epoch = deepcopy(fixture.state['b_route_execution_transition'])
                    # Only unavailable original source/proof and epoch authentication
                    # are synthetic. Current capture validation, prepare/validate/
                    # reconcile, journal operations, raw CAS and FS closure stay real.
                    with patch.object(recovery, '_close_sources'), \
                         patch.object(previous, 'validate_recovery') as original_proof, \
                         patch.object(transition, 'build_mvg_selector_transition', return_value=epoch) as build_epoch, \
                         patch.object(transition, 'validate_transition'):
                        capture = recovery.capture_retained_selector(fixture.root)
                        arguments = dict(prior_source_root=fixture.root / 'synthetic-prior-source',
                            prior_commit=recovery.PRIOR_COMMIT,
                            original_source_root=fixture.root / 'synthetic-original-source',
                            current_commit='f' * 40, retained_capture=capture)
                        if interrupted:
                            replace = recovery.os.replace
                            def crash_before_commit(source, destination):
                                if Path(destination) == fixture.home / 'committed.json':
                                    raise SystemExit('synthetic crash before prepare commit rename')
                                return replace(source, destination)
                            with patch.object(recovery.os, 'replace', side_effect=crash_before_commit):
                                with self.assertRaisesRegex(SystemExit, 'before prepare commit'):
                                    recovery.prepare(fixture.root, fixture.run, **arguments)
                            self.assertFalse((fixture.home / 'committed.json').exists())
                        else:
                            result = recovery.prepare(fixture.root, fixture.run, **arguments)
                            self.assertEqual(result['status'], 'selector-recovery-prepared')
                            self.assertEqual((result['model_calls'], result['released']), (0, 0))
                        build_epoch.assert_called_once_with(fixture.root, fixture.old,
                            arguments['original_source_root'], arguments['current_commit'],
                            arguments['prior_source_root'], recovery.PRIOR_COMMIT, retained_capture=capture)
                        journal_path = fixture.home / 'prepare-transaction.json'
                        journal_raw = journal_path.read_bytes()
                        journal = recovery.read(fixture.home, journal_path.name)
                        self.assertEqual(journal['schema_version'], recovery.TRANSACTION_SCHEMA)
                        self.assertEqual(journal['kind'], 'prepare')
                        self.assertEqual(recovery.image_bytes(journal['before']), original_run)
                        self.assertEqual(recovery.image_bytes(journal['after']), (fixture.run / 'run.json').read_bytes())
                        record_raw = (fixture.home / 'record.json').read_bytes()
                        record_digest = recovery.codec.raw_digest(record_raw)
                        self.assertEqual(recovery.read(fixture.home, 'record.json'), journal['record'])
                        self.assertEqual(recovery.read(fixture.home, 'claim.json'), {
                            'schema_version': recovery.SCHEMA, 'record_digest': record_digest,
                            'retained_calls': 12, 'maximum_selector_dispatches': 1})
                        for _ in range(2):
                            result = recovery.reconcile(fixture.root, fixture.run, retained_capture=capture)
                            self.assertEqual((result['logical_reserved_calls'], result['model_calls'], result['released']), (12, 0, 0))
                            self.assertFalse(result['retry_authorized'])
                            state = recovery.read(fixture.run, 'run.json')
                            self.assertEqual(recovery.validate_recovery(fixture.root, state), journal['record'])
                            self.assertEqual(journal_path.read_bytes(), journal_raw)
                            self.assertEqual((fixture.run / 'run.json').read_bytes(), recovery.image_bytes(journal['after']))
                            self.assertEqual((fixture.run / 'model-execution.json').read_bytes(), fixture.model)
                            self.assertEqual(state['capability_selection']['calls'], fixture.old['capability_selection']['calls'])
                        self.assertEqual(recovery.read(fixture.home, 'committed.json'), {
                            'record_digest': record_digest, 'transition_digest': epoch['transition_digest'],
                            'prepared_run_digest': recovery.codec.raw_digest(recovery.image_bytes(journal['after']))})
                        self.assertEqual(original_proof.call_args.args, (fixture.root, fixture.old))
                        if interrupted:
                            committed_raw = (fixture.home / 'committed.json').read_bytes()
                            self.assertEqual(recovery._prefix_path(fixture.root, journal, 'o3',
                                committed_raw, committed_raw).read_bytes(), committed_raw)
                finally:
                    fixture.doCleanups()

    def test_owned_full_and_partial_temporary_bytes_are_preserved(self):
        value = recovery._transaction_value('prepare', self.record, recovery._json_bytes(self.old), recovery._json_bytes(self.prepared))
        recovery._durable(self.home / 'prepare-transaction.json', value, exclusive=True)
        _, operations = recovery._journal(self.root, 'prepare', self.anchor)
        for index in (0, 2):
            target, temporary, evidence = recovery._operation_paths(self.root, value, index, operations[index][0])
            partial = operations[index][2][:17] if index == 0 else operations[index][2]
            temporary.write_bytes(partial)
        recovery._apply_transaction(self.root, value, operations)
        for index in (0, 2):
            _, temporary, _legacy = recovery._operation_paths(self.root, value, index, operations[index][0])
            self.assertFalse(temporary.exists())
            partial = operations[index][2][:17] if index == 0 else operations[index][2]
            evidence = recovery._prefix_path(self.root, value, 'o' + str(index), operations[index][2], partial)
            self.assertEqual(evidence.read_bytes(), partial)
        recovery._old_files_close(self.root, self.anchor, self.prepared)

    def test_foreign_temporary_still_blocks(self):
        self.prepare()
        (self.run / 'run.json.unknown.tmp').write_bytes(b'harmless synthetic bytes')
        with self.assertRaisesRegex(ValueError, 'unknown_new_file'):
            recovery._old_files_close(self.root, self.anchor, self.prepared)

    def test_journal_owned_temporary_tampering_and_preimage_drift_block(self):
        self.prepare()
        value, operations = recovery._journal(self.root, 'prepare', self.anchor)
        _, temporary, _ = recovery._operation_paths(self.root, value, 0, operations[0][0])
        temporary.write_bytes(b'not the intended journal bytes')
        with self.assertRaisesRegex(ValueError, 'temporary_bytes_changed'):
            recovery._journal_artifacts(self.root, self.anchor)
        # No deletion or replacement of the unknown temporary is attempted.
        self.assertTrue(temporary.exists())
        (self.run / 'run.json').write_bytes(b'{"foreign":true}')
        with self.assertRaises(ValueError):
            recovery._apply_transaction(self.root, value, operations)

    def reservation(self):
        row = selector_row(self.anchor)
        row.update(run_id='m4', status='reserved', capability_id='synthetic', lineage=None, reserved_at_utc='synthetic')
        row['request_identity']['workspace'] = 's1/attempt-1/llm-sandbox/attempt-1/selection'
        after = deepcopy(self.prepared)
        after['capability_selection']['total_invocations'] = 13
        after['capability_selection']['calls'].append(row)
        return row, after

    def test_intent_before_parent_row_recovers_as_unknown_without_release(self):
        self.prepare()
        row, after = self.reservation()
        replace = recovery.os.replace
        def crash(source, destination):
            replace(source, destination)
            if Path(destination).name == 'intent.json':
                raise SystemExit('synthetic intent-parent crash')
        with patch.object(recovery.os, 'replace', side_effect=crash), self.assertRaises(SystemExit):
            recovery._start_transaction(self.root, 'reservation', self.record,
                recovery._json_bytes(self.prepared), recovery._json_bytes(after), row=row)
        self.assertEqual(recovery.read(self.run, 'run.json')['capability_selection']['total_invocations'], 12)
        capture = recovery._RetainedSelectorCapture(recovery._SEAL, self.root, self.anchor, recovery._anchor_identity())
        # Only original-source/qualification seams are synthetic; all journal
        # reads, raw CAS, writes, locks and unknown charging below are real disk.
        with patch.object(recovery, '_close_sources'), patch.object(transition, 'validate_transition'), \
             patch.object(recovery, 'validate_recovery', return_value=self.record):
            result = recovery.reconcile(self.root, self.run, retained_capture=capture)
        state = recovery.read(self.run, 'run.json')
        self.assertEqual(result['logical_reserved_calls'], 13)
        self.assertEqual(result['released'], 0)
        self.assertFalse(result['retry_authorized'])
        self.assertEqual(state['capability_selection']['calls'][12]['outcome']['status'], 'unknown')
        self.assertTrue(state['capability_selection']['terminal'])
        self.assertEqual(state['capability_selection']['calls'][:12], self.old['capability_selection']['calls'])

    def test_parent_row_missing_does_not_authorize_new_intent(self):
        self.prepare()
        row, _ = self.reservation()
        with patch.object(recovery, 'validate_recovery', return_value=self.record):
            recovery.authorize_selector_reservation(self.root, self.prepared, phase='selection', candidate=None,
                request_identity=row['request_identity'], reservation=row)
            with self.assertRaises(ValueError):
                recovery.authorize_selector_reservation(self.root, self.prepared, phase='selection', candidate=None,
                    request_identity=row['request_identity'], reservation=row)
        self.assertEqual(recovery.read(self.run, 'run.json')['capability_selection']['total_invocations'], 13)

    def test_simultaneous_reconcile_uses_original_coordinator_lock(self):
        self.prepare()
        capture = recovery._RetainedSelectorCapture(recovery._SEAL, self.root, self.anchor, recovery._anchor_identity())
        with checkpoint.coordinator_lock(self.run):
            with self.assertRaisesRegex(ValueError, 'coordinator_busy'):
                recovery.reconcile(self.root, self.run, retained_capture=capture)

    def test_legacy_partial_preparation_has_no_invented_journal(self):
        (self.home / 'claim.json').write_bytes(b'{"partial":')
        capture = recovery._RetainedSelectorCapture(recovery._SEAL, self.root, self.anchor, recovery._anchor_identity())
        with self.assertRaisesRegex(ValueError, 'legacy_unjournaled'):
            recovery.reconcile(self.root, self.run, retained_capture=capture)
        self.assertFalse((self.home / 'prepare-transaction.json').exists())


class FailureEvidenceTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows capture construction boundary')
    def test_capture_constructor_error_terminates_fake_child_and_persists_original_bytes(self):
        """Constructor failure still uses actual cleanup and disk evidence owners."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            log = root / 'host.json'
            events = []
            partial = b'original partial output\xff\r\n'
            failure = RuntimeError('capture constructor failed')
            class FakeProcess:
                args = ['synthetic-runner']
                pid = 12345
                returncode = None
                def poll(self):
                    return self.returncode
                def kill(self):
                    events.append('kill')
                    self.returncode = -9
                def communicate(self, timeout):
                    if self.returncode is None:
                        raise AssertionError('Cleanup must terminate before draining output')
                    events.append('communicate')
                    return partial, None
            process = FakeProcess()
            # Only process creation, the failing constructor, and the external
            # taskkill command are fake. Cleanup and persistence execute normally.
            with patch.object(common.subprocess, 'Popen', return_value=process) as launch, \
                 patch.object(common.subprocess, 'run', return_value=SimpleNamespace(returncode=1)) as taskkill, \
                 patch.object(common, '_WindowsRunnerOutput', side_effect=failure) as construct:
                with self.assertRaises(RuntimeError) as error:
                    common.run_isolated_model(root / 'runner.py', workspace=root, prompt_path=root / 'prompt',
                        output_path=root / 'output', timeout_sec=1, execution_log=log)
            self.assertIs(error.exception, failure)
            launch.assert_called_once()
            construct.assert_called_once_with(process)
            taskkill.assert_called_once_with(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                stdout=common.subprocess.DEVNULL, stderr=common.subprocess.DEVNULL, timeout=15, check=False)
            self.assertEqual(events, ['kill', 'communicate'])
            value = common.load_json(log)
            self.assertEqual(value['status'], 'interrupted')
            self.assertEqual(value['original_error'], {'type': 'RuntimeError', 'detail': str(failure)})
            self.assertEqual(value['cleanup_errors'], [])
            self.assertEqual(common.base64.b64decode(value['stdout_base64']), partial)
            self.assertEqual(value['runner_dispatch_count'], 1)
            self.assertEqual(value['returncode'], -9)
            self.assertGreaterEqual(value['active_elapsed_seconds'], 0)

    @unittest.skipUnless(os.name == 'nt', 'Windows capture cleanup boundary')
    def test_cancel_error_preserves_original_failure_partial_bytes_and_elapsed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            log = root / 'host.json'
            proc = SimpleNamespace(returncode=None, args=['synthetic'])
            capture = SimpleNamespace(parts=[b'original partial output'],
                communicate=lambda timeout: (_ for _ in ()).throw(KeyboardInterrupt('original interruption')),
                cancel=lambda: (_ for _ in ()).throw(RuntimeError('cleanup failed')))
            with patch.object(common.subprocess, 'Popen', return_value=proc), \
                 patch.object(common, '_WindowsRunnerOutput', return_value=capture), \
                 patch.object(common, '_terminate_process_tree'):
                with self.assertRaisesRegex(KeyboardInterrupt, 'original interruption'):
                    common.run_isolated_model(root / 'runner.py', workspace=root, prompt_path=root / 'prompt',
                        output_path=root / 'output', timeout_sec=1, execution_log=log)
            value = common.load_json(log)
            self.assertEqual(value['stdout'], 'original partial output')
            self.assertEqual(value['original_error']['type'], 'KeyboardInterrupt')
            self.assertEqual(value['cleanup_errors'][0]['detail'], 'cleanup failed')
            self.assertEqual(value['runner_dispatch_count'], 1)
            self.assertGreaterEqual(value['active_elapsed_seconds'], 0)

    def test_missing_or_invalid_host_elapsed_is_unknown_and_reserved_time_stays_charged(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'missing.json'
            self.assertIsNone(worker.failure_elapsed(path))
            for elapsed in (None, False, -1, 'unknown'):
                common.atomic_json(path, {'active_elapsed_seconds': elapsed})
                self.assertIsNone(worker.failure_elapsed(path))
            common.atomic_json(path, {'active_elapsed_seconds': 0})
            self.assertEqual(worker.failure_elapsed(path), 0)
        desc = {'planner': 'capabilities', 'limits': {'total_budget_sec': 100, 'candidate_budget_sec': 80,
                                                   'synthesis_budget_sec': 20}}
        state = {'capability_selection': {'calls': [{'candidate': 'candidate-1',
            'request_identity': {'timeout_sec': 30}, 'outcome': {'status': 'failed', 'active_elapsed_seconds': None}}]}}
        with patch.object(runtime, 'descriptor', return_value=desc):
            self.assertEqual(selection.remaining_time(state), 70)
            self.assertEqual(selection.remaining_time(state, 'candidate-1'), 50)


if __name__ == '__main__':
    unittest.main(verbosity=2)
