"""Public context routing checks, not native or provider qualification.

Most owner seams are synthetic. The missing-receipt check uses the actual
readers on an empty temporary target, with no native or model dispatch.
"""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.dont_write_bytecode = True
SCRIPTS = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(SCRIPTS), str(SCRIPTS.parent/'sc')]
import b_route_adoption as cli
import _b_route_codec as codec
import dev_cli


def captured(function, arguments):
    output = io.StringIO()
    with redirect_stdout(output):
        code = function(arguments)
    return code, json.loads(output.getvalue())


def operation():
    return dict(operation_id='OP-1', state='reserved', scope_ids=['flow:original'],
        request_digest='sha256:'+'1'*64, frozen_digest='sha256:'+'2'*64,
        allocations={'plan_id': 'Original-Plan', 'plan_revision': 7},
        resume_ref='logs/ci/original/operation.json', diagnostics=[],
        status='inspected', **cli.FLAGS)


def receipt():
    # The record-validator seam is synthetic. Exact typed references/order are
    # intentionally preserved by the CLI consumer rather than reconstructed.
    return dict(operation_id='OP-1', revision=1, operation_digest='sha256:'+'2'*64,
        scopes=['flow:original'],
        plan_refs=[{'path': 'docs/planning/b-route/plans/Original-Plan/7.json',
                    'entity_id': 'Original-Plan', 'revision': 7}], binding_refs=[])


def published():
    return dict(status='committed', scope_ids=['flow:original'],
        formal_adoption=True, readiness=False, runtime_verified=False,
        input_set_digest='sha256:'+'3'*64, catalog_raw_digest='sha256:'+'4'*64,
        formal_paths=['docs/planning/b-route/plans/Original-Plan/7.json',
                      'docs/planning/b-route/commits/OP-1.json'])


def modules(inspected=None, read=None):
    adoption = ModuleType('_b_route_adoption')
    adoption.inspect = Mock(return_value=operation() if inspected is None else inspected)
    commit = ModuleType('_b_route_commit')
    commit.read_committed = Mock(return_value=published() if read is None else read)
    records = ModuleType('_b_route_records')
    records.BASE = 'docs/planning/b-route/'
    records.validate_record = Mock(return_value=SimpleNamespace(ok=True))
    return adoption, commit, records


def installed(fake):
    # Qualified read first asks the original apply-journal graph for resolution.
    # This fake is deliberately empty; receipt/reader seams below remain unchanged.
    journal = ModuleType('_planning_apply_journal')
    journal.operation_state_graph = Mock(return_value={'resolved_by': {}})
    return patch.dict(sys.modules, {**{module.__name__: module for module in fake},
                                    journal.__name__: journal})


class PublicContextTests(unittest.TestCase):
    def test_missing_receipt_keeps_public_resume_path_through_both_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            args = ['--root', directory, '--stage', 'read', '--operation-id', 'MissingReceipt']
            direct = captured(cli.main, args)
            routed = captured(dev_cli.main, ['b-route-adoption', *args])
            self.assertEqual(direct, routed)
            code, result = direct
            self.assertEqual(2, code)
            self.assertTrue(all(result[key] is False for key in cli.FLAGS))
            diagnostic = result['diagnostics'][0]
            self.assertEqual(codec.ReasonCode.FILE_NOT_FOUND.value, diagnostic['reason_code'])
            self.assertEqual('MissingReceipt', diagnostic['entity_id'])
            self.assertEqual('docs/planning/b-route/commits/MissingReceipt.json', diagnostic['resume_ref'])
            self.assertEqual([], list(Path(directory).rglob('*')))

    def test_legacy_inspect_and_read_output_remain_opt_in(self):
        fake = modules()
        raw = json.dumps(receipt()).encode()
        with installed(fake), patch.object(codec, 'read_reference_bytes', return_value=raw) as reader:
            self.assertEqual((0, operation()), captured(cli.main,
                ['--stage', 'inspect', '--operation-id', 'OP-1']))
            self.assertEqual((0, published()), captured(cli.main,
                ['--stage', 'read', '--operation-id', 'OP-1']))
        self.assertEqual(1, reader.call_count)

    def test_inspect_context_same_id_new_session_through_both_entries(self):
        original = operation()
        before = deepcopy(original)
        fake = modules(inspected=original)
        args = ['--stage', 'inspect', '--operation-id', 'OP-1', '--context']
        with installed(fake):
            direct = captured(cli.main, args)
            repeated = captured(cli.main, args)
            routed = captured(dev_cli.main, ['b-route-adoption', *args])
        self.assertEqual(direct, repeated)
        self.assertEqual(direct, routed)
        self.assertEqual(before, original)
        context = direct[1]['context']
        for name in ('operation_id', 'state', 'scope_ids', 'allocations',
                     'resume_ref', 'request_digest', 'frozen_digest'):
            self.assertEqual(original[name], context[name])
        self.assertEqual('unsupported', context['completed_unit_reuse'])
        self.assertEqual('not_established', context['global_planning_completion'])
        self.assertFalse(context['native_resume_performed'])
        self.assertFalse(context['default_B_activated'])

    def test_blocked_owner_diagnostic_and_resume_stay_blocked(self):
        value = operation()
        diagnostic = codec.Diagnostic(codec.ReasonCode.INPUT_STALE,
            expected='original authority', actual='changed source',
            resume_ref=value['resume_ref']).to_dict()
        value.update(status='blocked', diagnostics=[diagnostic])
        with installed(modules(inspected=value)):
            code, result = captured(cli.main,
                ['--stage', 'inspect', '--operation-id', 'OP-1', '--context'])
        self.assertEqual(2, code)
        self.assertEqual([diagnostic], result['diagnostics'])
        self.assertEqual(value['resume_ref'], result['context']['resume_ref'])
        value.update(readiness=True)
        with installed(modules(inspected=value)):
            code, result = captured(cli.main,
                ['--stage', 'inspect', '--operation-id', 'OP-1', '--context'])
        self.assertEqual(2, code)
        self.assertTrue(all(result[key] is False for key in cli.FLAGS))

    def test_context_rejects_writes_and_missing_unit_api_before_service_import(self):
        for stage in ('review-prepare', 'review-complete', 'prepare', 'reserve',
                      'apply', 'verify', 'publish', 'reuse', 'reopen', 'recover'):
            args = ['--stage', stage, '--operation-id', 'OP-1', '--context']
            if stage in ('prepare', 'review-prepare'):
                args += ['--request', 'owned/request.json']
            with self.subTest(stage=stage), patch.object(cli.importlib, 'import_module') as load:
                code, result = captured(cli.main, args)
            self.assertEqual(2, code)
            self.assertTrue(all(result[key] is False for key in cli.FLAGS))
            load.assert_not_called()

    def test_read_uses_exact_original_receipt_and_real_reader_contract(self):
        record = receipt()
        raw = json.dumps(record, ensure_ascii=False, indent=2).encode()
        fake = modules()
        with installed(fake), patch.object(codec, 'read_reference_bytes', return_value=raw) as reader:
            code, result = captured(cli.main,
                ['--stage', 'read', '--operation-id', 'OP-1', '--context'])
        self.assertEqual(0, code)
        path = fake[2].BASE+'commits/OP-1.json'
        self.assertEqual(2, reader.call_count)
        for call in reader.call_args_list:
            self.assertEqual((Path('.').absolute(), path), call.args)
        fake[2].validate_record.assert_called_once_with(raw, path=path)
        fake[1].read_committed.assert_called_once_with(Path('.').absolute(),
                                                       scope_ids=record['scopes'])
        context = result['context']
        self.assertEqual(record['plan_refs'], context['plan_refs'])
        self.assertEqual(record['binding_refs'], context['binding_refs'])
        self.assertEqual({'path': path, 'raw_digest': codec.raw_digest(raw)}, context['receipt_ref'])
        self.assertEqual(7, context['plan_refs'][0]['revision'])
        self.assertTrue(result['formal_adoption'])
        self.assertFalse(result['readiness'])
        self.assertFalse(result['runtime_verified'])

    def test_wrong_operation_or_changed_receipt_cannot_emit_context(self):
        for mode in ('operation', 'drift'):
            record = receipt()
            if mode == 'operation':
                record['operation_id'] = 'OTHER'
            raw = json.dumps(record).encode()
            fake = modules()
            values = [raw, raw+b'\n'] if mode == 'drift' else [raw]
            with self.subTest(mode=mode), installed(fake), patch.object(codec,
                    'read_reference_bytes', side_effect=values):
                code, result = captured(cli.main,
                    ['--stage', 'read', '--operation-id', 'OP-1', '--context'])
            self.assertEqual(2, code)
            self.assertNotIn('context', result)
            self.assertEqual(1 if mode == 'drift' else 0, fake[1].read_committed.call_count)
            expected = codec.ReasonCode.INPUT_STALE if mode == 'drift' else codec.ReasonCode.CONFLICT
            self.assertEqual(expected.value, result['diagnostics'][0]['reason_code'])

    def test_receipt_deleted_during_context_read_retains_resume_path(self):
        for lane in ('direct', 'dev-cli'):
            with self.subTest(lane=lane), tempfile.TemporaryDirectory() as directory:
                relative = 'docs/planning/b-route/commits/OP-1.json'
                target = Path(directory) / relative
                target.parent.mkdir(parents=True)
                target.write_text(json.dumps(receipt()), encoding='utf-8')
                fake = modules()
                def deleted(*args, **kwargs):
                    target.unlink()
                    return published()
                fake[1].read_committed.side_effect = deleted
                args = ['--root', directory, '--stage', 'read', '--operation-id', 'OP-1', '--context']
                with installed(fake):
                    code, result = (captured(cli.main, args) if lane == 'direct' else
                                    captured(dev_cli.main, ['b-route-adoption', *args]))
                self.assertEqual(2, code)
                self.assertNotIn('context', result)
                self.assertTrue(all(result[key] is False for key in cli.FLAGS))
                diagnostic = result['diagnostics'][0]
                self.assertEqual(codec.ReasonCode.FILE_NOT_FOUND.value, diagnostic['reason_code'])
                self.assertEqual(relative, diagnostic['resume_ref'])
                self.assertFalse(target.exists())

    def test_pending_reader_error_preserves_original_diagnostic(self):
        fake = modules()
        diagnostic = codec.Diagnostic(codec.ReasonCode.PENDING,
            expected='no unresolved pending lease', actual='original pending',
            resume_ref='logs/ci/original/commit.pending.json')
        fake[1].read_committed.side_effect = codec.CodecError(diagnostic)
        with installed(fake), patch.object(codec, 'read_reference_bytes',
                                          return_value=json.dumps(receipt()).encode()) as reader:
            code, result = captured(cli.main,
                ['--stage', 'read', '--operation-id', 'OP-1', '--context'])
        self.assertEqual(2, code)
        expected = diagnostic.to_dict()
        expected['entity_id'] = 'OP-1'
        self.assertEqual([expected], result['diagnostics'])
        self.assertEqual(1, reader.call_count)
        self.assertNotIn('context', result)

    def test_new_head_or_different_scope_cannot_replace_original_context(self):
        for mode in ('new-head', 'scope'):
            current = published()
            if mode == 'new-head':
                current['formal_paths'] = ['docs/planning/b-route/plans/Other/8.json']
            else:
                current['scope_ids'] = ['flow:other']
            with self.subTest(mode=mode), installed(modules(read=current)), patch.object(
                    codec, 'read_reference_bytes', return_value=json.dumps(receipt()).encode()):
                code, result = captured(cli.main,
                    ['--stage', 'read', '--operation-id', 'OP-1', '--context'])
            self.assertEqual(2, code)
            self.assertNotIn('context', result)

    def test_help_and_programmatic_dev_parser_share_supported_contract(self):
        help_text = cli.build_parser().format_help()
        self.assertIn('--context', help_text)
        self.assertIn('unsupported', help_text)
        self.assertIn('read', help_text)
        args = dev_cli.build_parser().parse_args(['b-route-adoption', '--stage',
            'inspect', '--operation-id', 'OP-1', '--context'])
        self.assertTrue(args.context)
        with installed(modules()):
            code, result = captured(lambda unused: args.func(args), [])
        self.assertEqual(0, code)
        self.assertEqual('retained_operation', result['context']['kind'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
