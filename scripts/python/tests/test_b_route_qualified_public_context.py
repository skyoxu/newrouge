"""Context/qualified-delivery composition; synthetic service seams, no qualification.

No filesystem fixture, child, native/model call or persisted owner state is used.
The real merged CLI/parser/context predicates execute after Root installs it.
"""
from copy import deepcopy
import json
from types import ModuleType
import sys
import unittest
from unittest.mock import ANY, Mock, patch

try:
    from . import test_b_route_public_context as context_fixture
except ImportError:
    import test_b_route_public_context as context_fixture

cli = context_fixture.cli
codec = context_fixture.codec
dev_cli = context_fixture.dev_cli


class QualifiedPublicContextTests(unittest.TestCase):
    def test_delivery_default_v3_explicit_v4_and_qualified_are_not_rewritten(self):
        deliveries = (None,
            'newrouge.b-route-compensation-review-delivery.v3',
            'newrouge.b-route-compensation-review-delivery.v4',
            'newrouge.b-route-qualified-compensation-review-delivery.v1',
            'newrouge.b-route-qualified-compensation-review-delivery.v3')
        for delivery in deliveries:
            with self.subTest(delivery=delivery):
                service = ModuleType('_b_route_adoption')
                original = context_fixture.operation()
                service.prepare_review = Mock(return_value=original)
                arguments = ['--stage', 'review-prepare', '--operation-id', 'OP-1',
                             '--request', 'logs/ci/request.json']
                if delivery is not None:
                    arguments += ['--compensation-review-delivery', delivery]
                with patch.dict(sys.modules, {service.__name__: service}):
                    code, result = context_fixture.captured(cli.main, arguments)
                self.assertEqual(0, code)
                self.assertEqual(original, result)
                expected = dict(operation_id='OP-1', request_ref='logs/ci/request.json')
                if delivery is not None:
                    expected['compensation_delivery'] = delivery
                self.assertEqual(expected, service.prepare_review.call_args.kwargs)
                service.prepare_review.assert_called_once()
                self.assertNotIn('context', result)
                parsed = dev_cli.build_parser().parse_args(['b-route-adoption', *arguments])
                self.assertEqual(delivery, parsed.compensation_review_delivery)
                self.assertFalse(parsed.context)

    def test_context_rejects_all_mutating_and_origin_routes_before_service_import(self):
        for stage in ('origin-prepare', 'review-prepare', 'review-complete', 'prepare',
                      'reserve', 'apply', 'verify', 'publish', 'recover-inspect', 'recover'):
            with self.subTest(stage=stage):
                arguments = ['--stage', stage, '--operation-id', 'OP-1', '--context']
                if stage in ('review-prepare', 'prepare'):
                    arguments += ['--request', 'logs/ci/request.json',
                                  '--compensation-review-delivery',
                                  'newrouge.b-route-qualified-compensation-review-delivery.v1']
                if stage == 'origin-prepare':
                    arguments += ['--origin-profile', 'original-finite-profile']
                with patch.object(cli.importlib, 'import_module') as imported, \
                     patch.dict(sys.modules, {'_b_route_qualified_origin': None}):
                    code, result = context_fixture.captured(cli.main, arguments)
                self.assertEqual(2, code)
                imported.assert_not_called()
                self.assertNotIn('context', result)
                self.assertEqual('invalid_argument', result['diagnostics'][0]['reason_code'])
                self.assertEqual('--context on inspect/read only', result['diagnostics'][0]['expected'])

    def test_inspect_and_receipt_context_keep_original_identity_and_raw_close(self):
        fake = context_fixture.modules()
        original = deepcopy(fake[0].inspect.return_value)
        with context_fixture.installed(fake):
            code, inspected = context_fixture.captured(cli.main,
                ['--stage', 'inspect', '--operation-id', 'OP-1', '--context'])
        self.assertEqual(0, code)
        self.assertEqual(original, fake[0].inspect.return_value)
        self.assertEqual(original, {k: v for k, v in inspected.items() if k != 'context'})
        self.assertEqual(original['resume_ref'], inspected['context']['resume_ref'])
        receipt = context_fixture.receipt()
        raw = json.dumps(receipt, ensure_ascii=False, indent=2).encode('utf-8')
        with context_fixture.installed(fake), \
             patch.object(codec, 'read_reference_bytes', side_effect=[raw, raw]) as read:
            code, result = context_fixture.captured(cli.main,
                ['--stage', 'read', '--operation-id', 'OP-1', '--context'])
        self.assertEqual(0, code)
        self.assertEqual(2, read.call_count)
        fake[1].read_committed.assert_called_once_with(
            ANY, scope_ids=receipt['scopes'])
        self.assertEqual(receipt['plan_refs'], result['context']['plan_refs'])
        self.assertEqual(codec.raw_digest(raw), result['context']['receipt_ref']['raw_digest'])
        self.assertEqual('unsupported', result['context']['completed_unit_reuse'])

    def test_resolved_read_keeps_q_route_and_context_does_not_invent_receipt(self):
        commit = ModuleType('_b_route_commit')
        resolved = dict(operation_id='OP-1', state='resolved_by', resolved_by='OP-2',
            status='resolved', published=False, noop=True,
            resume_ref='logs/ci/original/OP-2/operation.json', diagnostics=[], **cli.FLAGS)
        commit._resolved_result = Mock(return_value=resolved)
        commit.read_committed = Mock(side_effect=AssertionError('must not read a replacement receipt'))
        journal = ModuleType('_planning_apply_journal')
        journal.operation_state_graph = Mock(return_value={'resolved_by': {'OP-1': 'OP-2'}})
        fake = {commit.__name__: commit, journal.__name__: journal}
        arguments = ['--stage', 'read', '--operation-id', 'OP-1']
        with patch.dict(sys.modules, fake), \
             patch.object(codec, 'read_reference_bytes') as read:
            code, result = context_fixture.captured(cli.main, arguments)
            blocked, diagnostic = context_fixture.captured(cli.main, [*arguments, '--context'])
        self.assertEqual(0, code)
        self.assertEqual(resolved, result)
        self.assertEqual(2, blocked)
        self.assertNotIn('context', diagnostic)
        self.assertEqual(resolved['resume_ref'], diagnostic['diagnostics'][0]['resume_ref'])
        self.assertEqual('resolved_by', diagnostic['diagnostics'][0]['actual'])
        self.assertEqual(2, commit._resolved_result.call_count)
        commit.read_committed.assert_not_called()
        read.assert_not_called()

    def test_delivery_cannot_leak_into_context_or_unknown_public_route(self):
        for stage in ('inspect', 'read'):
            with self.subTest(stage=stage), patch.object(cli.importlib, 'import_module') as imported:
                code, result = context_fixture.captured(cli.main,
                    ['--stage', stage, '--operation-id', 'OP-1', '--context',
                     '--compensation-review-delivery',
                     'newrouge.b-route-qualified-compensation-review-delivery.v1'])
            self.assertEqual(2, code)
            self.assertNotIn('context', result)
            imported.assert_not_called()
            self.assertEqual('delivery selection on compensation review-prepare only',
                             result['diagnostics'][0]['expected'])
        with patch.object(cli.importlib, 'import_module') as imported:
            code, result = context_fixture.captured(cli.main,
                ['--stage', 'review-prepare', '--operation-id', 'OP-1',
                 '--request', 'logs/ci/request.json', '--compensation-review-delivery',
                 'newrouge.b-route-qualified-compensation-review-delivery.v99'])
        self.assertEqual(2, code)
        imported.assert_not_called()
        self.assertNotIn('context', result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
