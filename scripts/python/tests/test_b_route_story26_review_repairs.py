"""Deterministic repair contracts; native qualification remains explicitly synthetic."""
from contextlib import redirect_stdout
from copy import deepcopy
import ast
import importlib.machinery
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SCRIPTS), str(SCRIPTS / 'tests'), str(SCRIPTS.parent / 'sc')]
import _b_route_adoption as adoption
import _b_route_adoption_review as review
import _b_route_codec as codec
import _b_route_frozen_native_reader as reader
import _b_route_records as records
import _b_route_schema_resources as schemas
import b_route_adoption as cli
import test_b_route_adoption_projection as projections
import test_b_route_adoption_r10_reader as synthetic_reader


def retained_fixture(case):
    case.setUp()
    # Preserve these newly composed failure sites. Stop patches, not evidence.
    if hasattr(case, 'temp'):
        case.temp._finalizer.detach()
        case._cleanups = [entry for entry in case._cleanups
                          if getattr(entry[0], '__self__', None) is not case.temp]
    return case


class Story26RepairContracts(unittest.TestCase):
    def test_target_templates_accept_only_original_simple_allocation_fields(self):
        allocations = {'plan_id': 'PLAN-1', 'plan_revision': 2, 'binding_revision': None}
        self.assertEqual('docs/planning/b-route/plans/PLAN-1/2.json', adoption._target_path(
            'docs/planning/b-route/plans/{plan_id}/{plan_revision}.json', allocations))
        self.assertEqual('literal-{brace}-PLAN-1', adoption._target_path('literal-{{brace}}-{plan_id}', allocations))
        self.assertEqual(adoption._target_path('{plan_id}', allocations),
                         adoption._target_path('{plan_id:}', allocations))
        invalid = ('{plan_id[999999]}', '{plan_id.no_such_attribute}', '{plan_id!s}', '{plan_id!r}',
                   '{plan_id:1000000000}', '{plan_revision:{plan_revision}}', '{}', '{unknown}', '{',
                   '{plan_revision.real}', '{plan_revision[0]}')
        for template in invalid:
            with self.subTest(template=template), self.assertRaises(codec.CodecError) as caught:
                adoption._target_path(template, allocations)
            self.assertEqual(codec.ReasonCode.INVALID_REFERENCE, caught.exception.diagnostic.reason_code)

    def test_cli_non_ascii_success_and_blocked_json_survive_cp1252(self):
        for failed in (False, True):
            fake = ModuleType('_b_route_adoption')
            def inspect(root, *, operation_id):
                if failed:
                    raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.FILE_NOT_FOUND,
                        entity_id=operation_id, actual='missing original operation'))
                return {'operation_id': operation_id, 'state': 'prepared', **cli.FLAGS}
            fake.inspect = inspect
            output = io.BytesIO()
            stream = io.TextIOWrapper(output, encoding='cp1252', errors='strict')
            with patch.dict(sys.modules, {'_b_route_adoption': fake}), redirect_stdout(stream):
                code = cli.main(['--stage', 'inspect', '--operation-id', '\u4fdd\u7559-\u00e9'])
            stream.flush()
            encoded = output.getvalue()
            self.assertTrue(encoded.isascii())
            self.assertEqual('\u4fdd\u7559-\u00e9', json.loads(encoded)['operation_id'])
            self.assertEqual(2 if failed else 0, code)

    def test_outer_timeout_is_a_common_codec_diagnostic_through_cli(self):
        fx = retained_fixture(synthetic_reader.AdoptionR10ReaderTests())
        self.addCleanup(fx.doCleanups)
        @adoption.public
        def inspect(root, *, operation_id):
            return reader.capture_completed(fx.root, planner='capabilities', run_id='synthetic',
                state_raw=(fx.run / 'run.json').read_bytes(), expected_handoff_ref=fx.request['expected_handoff_ref'])
        fake = ModuleType('_b_route_adoption')
        fake.inspect = inspect
        secret = 'REQUEST-AND-BOOTSTRAP-MUST-NOT-LEAK'
        refusal = subprocess.TimeoutExpired(['python', secret], 3600, output=b'partial', stderr=secret.encode())
        output = io.StringIO()
        with patch.object(reader, '_run_reader', side_effect=refusal), \
                patch.dict(sys.modules, {'_b_route_adoption': fake}), redirect_stdout(output):
            code = cli.main(['--root', str(fx.root), '--stage', 'inspect', '--operation-id', 'OP-timeout'])
        value = json.loads(output.getvalue())
        self.assertEqual(2, code)
        detail = value['diagnostics'][0]['actual']
        self.assertEqual(('timeout', 'unconfirmed', 3600),
                         (detail['outcome'], detail['cleanup'], detail['host_timeout_seconds']))
        self.assertEqual(len(b'partial'), detail['stdout']['byte_count'])
        self.assertEqual(codec.raw_digest(secret.encode()), detail['stderr']['raw_digest'])
        self.assertNotIn(secret, output.getvalue())
        self.assertTrue(all(value[key] is False for key in cli.FLAGS))

    def test_native_failure_metadata_is_bounded_structural_and_payload_free(self):
        original = {'schema_version': 'newrouge.b-route-native-rejection.v1',
                    'phase': 'active_chain', 'exception_type': 'ValueError', 'reason': 'checkpoint_revoked'}
        raw = (json.dumps(original) + '\n').encode() * 10
        raw += b'full bootstrap REQUEST_SECRET\n' + json.dumps({**original, 'reason': 'REQUEST_SECRET/path'}).encode()
        raw += b'\n' + json.dumps({**original, 'phase': []}).encode()
        error = reader.NativeReaderError('native_rejected', stderr=raw, stdout=b'invalid',
                                          cleanup='confirmed_empty', exit_code=2)
        detail = error.reader_diagnostic
        self.assertEqual([original] * 4, detail['native'])
        self.assertEqual(codec.raw_digest(raw), detail['stderr']['raw_digest'])
        self.assertNotIn('REQUEST_SECRET', json.dumps(detail))
        self.assertEqual('execution_transition_original_native_verifier_failed', reader._safe_reason(
            ValueError('execution_transition_original_native_verifier_failed:1:REQUEST_SECRET')))

    def test_policy_identity_binds_real_source_protection_and_transport_dependencies(self):
        home = Path(tempfile.mkdtemp(prefix='newrouge-policy-freshness-'))
        node = next(n for n in ast.parse((SCRIPTS / '_b_route_adoption_review.py').read_text(encoding='utf-8')).body
                    if isinstance(n, ast.FunctionDef) and n.name == 'policy_identity')
        assignment = next(n for n in node.body if isinstance(n, ast.Assign)
                          and any(isinstance(t, ast.Name) and t.id == 'names' for t in n.targets))
        names = ast.literal_eval(assignment.value)
        for name in names:
            (home / name).write_bytes((SCRIPTS / name).read_bytes())
        required = ('_b_route_sources.py', '_b_route_protection.py', '_b_route_inventory.py',
                    '_b_route_reader_lifetime.py', '_mvg_worker_lifetime.py', '_b_route_flow_graph.py')
        self.assertTrue(set(required) <= set(names))
        with patch.object(review, '__file__', str(home / '_b_route_adoption_review.py')):
            original = review.policy_identity()
            subject = {key: {} for key in ('request', 'preview', 'native_content', 'prepared', 'protection',
                'related_records', 'task_definitions', 'authority_files', 'target_before_files',
                'affected_catalog', 'native_threads', 'native_turns')}
            subject.update(schema_version=review.SUBJECT, operation_id='OP-policy', policy_identity=original)
            original_subject = review.raw(subject)
            for name in required:
                path = home / name
                before = path.read_bytes()
                path.write_bytes(before + b'\n# changed installed owner\n')
                self.assertNotEqual(original, review.policy_identity(), name)
                with patch.object(review, 'path', return_value=SimpleNamespace(read_bytes=lambda: original_subject)):
                    with self.assertRaises(codec.CodecError):
                        review.read_subject(home, 'OP-policy')
                path.write_bytes(before)
            self.assertEqual(original, review.policy_identity())

    def test_observable_extension_import_enters_closure_and_changed_bytes_reject(self):
        fx = retained_fixture(synthetic_reader.AdoptionR10ReaderTests())
        self.addCleanup(fx.doCleanups)
        extension = fx.root / ('observed' + importlib.machinery.EXTENSION_SUFFIXES[0])
        extension.write_bytes(b'toy extension bytes; not executable')
        original_witness = fx.fake_witness
        def witness(request, state, audit):
            result = original_witness(request, state, audit)
            audit.check('import', ('observed_extension', str(extension), None, None, None))
            return result
        with patch.object(reader, '_native_witness', side_effect=witness):
            capture = reader._capture_request(fx.request, reader._Audit([]))
        self.assertEqual(reader.digest(extension.read_bytes()), capture['files'][str(extension)])
        reader.verify_capture(fx.root, capture)
        extension.write_bytes(b'drifted extension')
        with self.assertRaisesRegex(ValueError, 'closure_file_changed'):
            reader.verify_capture(fx.root, capture)

    def test_real_new_stdlib_extension_import_is_observed_without_claiming_dll_closure(self):
        code = ('import sys,json;sys.path.insert(0,' + repr(str(SCRIPTS)) + ');'
                'import _b_route_frozen_native_reader as r;'
                'a=r._Audit([]);sys.addaudithook(a.check);import _queue;'
                'print(json.dumps({"extension":_queue.__file__,"files":a.files}))')
        result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', code],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20, check=False)
        self.assertEqual(0, result.returncode, result.stderr.decode(errors='replace'))
        value = json.loads(result.stdout)
        self.assertEqual(reader.digest(Path(value['extension']).read_bytes()), value['files'][value['extension']])

    def test_maintained_gate_includes_complete_adoption_operation_and_native_modules(self):
        from test_b_route_runtime_ci import selector_names
        selected = set(selector_names())
        required = {'test_b_route_candidate', 'test_b_route_records',
            'test_b_route_adoption', 'test_b_route_adoption_cli', 'test_b_route_adoption_concurrency',
            'test_b_route_adoption_journal', 'test_b_route_adoption_projection', 'test_b_route_adoption_r10_capture',
            'test_b_route_adoption_r10_reader', 'test_b_route_adoption_r19_reader', 'test_b_route_adoption_review',
            'test_b_route_operation_content', 'test_b_route_operation_leases',
            'test_b_route_operation_scope', 'test_b_route_inventory', 'test_b_route_protection',
            'test_b_route_reader_lifetime', 'test_b_route_story26_review_repairs'}
        self.assertTrue({'scripts.python.tests.' + name for name in required} <= selected)
        r22 = 'scripts.python.tests.test_b_route_frozen_native_reader_r22'
        self.assertIn(r22 + '.FrozenNativeReaderTransportTests', selected)
        closing = ('test_cheap_close_refuses_source_input_registry_and_recovery_raw_drift',
                   'test_cheap_close_refuses_r19_member_glob_and_absence_drift',
                   'test_capture_cannot_be_rehashed_as_r19_or_rewrite_old_admission',
                   'test_r22_native_order_retains_original_checks_flags_and_both_source_directories')
        self.assertTrue({r22 + '.FrozenNativeReaderR22Tests.' + name for name in closing} <= selected)
        self.assertNotIn(r22, selected, 'Standalone CI must not require a private sibling R22 checkout')


class FormalGraphRepairContracts(unittest.TestCase):
    def setUp(self):
        self.fx = projections.NativePlanProjectionTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.plan = self.fx.plan(self.fx.project())

    def test_valid_graph_and_legacy_text_plan_keep_existing_validation_paths(self):
        self.assertTrue(records.validate_record(self.plan).ok)
        legacy = projections.MatrixFixture().models
        # MatrixFixture stores the original text-only models without graph data.
        text = next(value for value in legacy.values() if value.get('schema_version') == codec.PLAN_SCHEMA)
        self.assertTrue(records.validate_record(text).ok)

    def test_schema_valid_graph_relations_reject_dangling_duplicate_boundary_and_cycle_gaps(self):
        def dangling(flow):
            flow['graph']['edges'][0]['to']['node_id'] = 'unknown-node'
        def duplicate(flow):
            row = deepcopy(flow['graph']['nodes'][0])
            row['responsibility'] += ' changed text'
            flow['graph']['nodes'].append(row)
        def boundary(flow):
            next(row for row in flow['graph']['boundaries'] if row['kind'] == 'entry')['required'] = False
        def loop(flow):
            flow['graph']['loops'].clear()
        def branch(flow):
            flow['branches'][0]['boundary_ids'] = ['missing-boundary']
        for mutate in (dangling, duplicate, boundary, loop, branch):
            plan = deepcopy(self.plan)
            mutate(plan['definitions']['flows'][0])
            schemas.validate(plan, codec.PLAN_SCHEMA)
            with self.subTest(mutation=mutate.__name__):
                self.assertFalse(records.validate_record(plan).ok)

    def test_applicable_ui_and_human_responsibilities_are_not_skipped_with_source_checks(self):
        for name in ('ui', 'human_verification'):
            plan = deepcopy(self.plan)
            value = plan['definitions']['flows'][0][name]
            value['applicability'] = 'applicable'
            value['responsibilities'] = []
            schemas.validate(plan, codec.PLAN_SCHEMA)
            self.assertFalse(records.validate_record(plan).ok, name)

    def test_local_graph_lacks_ledger_context_but_bundle_source_checks_real_flow_membership(self):
        plan = deepcopy(self.plan)
        plan['definitions']['flows'][0]['source_block_ids'] = ['unknown-source-block']
        self.assertTrue(records.validate_record(plan).ok)
        source = plan['source_identity']
        manifest = {'source_revision': source['source_revision'], 'manifest_sha256': source['source_manifest_digest']}
        blocks = {block for row in plan['requirements'] for block in row['source_block_ids']}
        ledger = {'source_revision': source['source_revision'], 'source_manifest_sha256': source['source_manifest_digest'],
                  'blocks': [{'block_id': block} for block in blocks]}
        documents = {source['manifest_ref']['ref'].partition('#')[0]: reader.canonical(manifest),
                     source['ledger_ref']['ref'].partition('#')[0]: reader.canonical(ledger)}
        owner = SimpleNamespace(bytes=SimpleNamespace(read=documents.__getitem__))
        with self.assertRaises(codec.CodecError):
            records._Bundle.source(owner, plan, 'formal-plan.json')
        plan['definitions']['flows'][0]['source_block_ids'] = sorted(blocks)
        records._Bundle.source(owner, plan, 'formal-plan.json')


if __name__ == '__main__':
    unittest.main()
