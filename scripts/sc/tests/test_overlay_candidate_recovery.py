from __future__ import annotations

import contextlib
import io
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import test_overlay_candidate_cli as cli_fixtures
import test_overlay_candidate_apply as apply_fixtures
import _overlay_candidate_apply as apply_module


class OverlayCandidateRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case = cli_fixtures.OverlayCandidateCliTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def changed_model(self, **kwargs: object) -> tuple[int, str, list[str]]:
        path = Path(kwargs['out_last_message'])
        name = path.name.removesuffix('.output.json')
        path.write_text(json.dumps({'filename': name, 'update': {'sections': [
            {'heading': 'Directory Role', 'bullets': ['Uninspected second run']},
        ]}}), encoding='utf-8')
        return 0, '', ['codex', 'exec']

    def test_repeated_suffix_should_preserve_the_inspected_single_run(self) -> None:
        self.assertEqual(0, self.case.invoke_single(['--run-suffix', 'reviewed']))
        source = next((self.case.root / 'logs/ci/2026-10-07').glob('*--reviewed'))
        inspected = (source / 'generated/PRD-TEST/08/_index.md').read_bytes()
        pointer = (source / 'candidate-pointer.json').read_bytes()
        self.case.models.side_effect = self.changed_model
        self.assertEqual(0, self.case.invoke_single(['--run-suffix', 'reviewed']))
        self.assertEqual(pointer, (source / 'candidate-pointer.json').read_bytes())
        self.assertEqual(0, self.case.invoke_single(['--apply', '--candidate-from', str(source)]))
        self.assertEqual(inspected, (self.case.target / '_index.md').read_bytes())

    def test_repeated_batch_suffix_should_preserve_the_inspected_bundle_and_children(self) -> None:
        def child(cmd: list[str], **kwargs: object) -> SimpleNamespace:
            with patch.object(cli_fixtures.sys, 'argv', cmd[2:]):
                rc = cli_fixtures.single.main()
            return SimpleNamespace(returncode=rc, stdout='')
        source = self.case.root / 'logs/ci/2026-10-07/sc-llm-overlay-gen-batch-prd-test--reviewed'
        with patch.object(cli_fixtures.batch.subprocess, 'run', side_effect=child):
            self.assertEqual(0, self.case.invoke_batch(['--batch-suffix', 'reviewed']))
            inspected = (source / 'candidate-bundle.json').read_bytes()
            self.case.models.side_effect = self.changed_model
            self.assertEqual(0, self.case.invoke_batch(['--batch-suffix', 'reviewed']))
        self.assertEqual(inspected, (source / 'candidate-bundle.json').read_bytes())
        self.assertEqual(0, self.case.invoke_batch(['--apply', '--candidate-from', str(source)]))
        for page in ['_index.md', 'feature.md']:
            self.assertNotIn('Uninspected second run', (self.case.target / page).read_text())

    def test_successful_apply_should_be_repeatable_without_model_or_replacement(self) -> None:
        self.assertEqual(0, self.case.invoke_single(['--run-suffix', 'reviewed']))
        source = next((self.case.root / 'logs/ci/2026-10-07').glob('*--reviewed'))
        self.assertEqual(0, self.case.invoke_single(['--apply', '--candidate-from', str(source)]))
        self.case.models.reset_mock()
        with patch('_overlay_generator_runtime.os.replace', side_effect=AssertionError('Already applied')):
            self.assertEqual(0, self.case.invoke_single(['--apply', '--candidate-from', str(source)]))
        self.case.models.assert_not_called()


class OverlayApplyReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case = apply_fixtures.OverlayCandidateApplyTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.source, _ = self.case.candidate()
        self.output = self.case.root / 'logs/ci/2026-10-07/apply'

    def run_apply(self) -> int:
        return apply_module.run_candidate_apply(
            repo_root=self.case.root, out_dir=self.output, context=self.case.context(),
            pages=['_index.md'], candidate_from=str(self.source), label='SC_LLM_OVERLAY_GEN',
        )

    def test_summary_failure_after_promotion_should_report_actual_success_and_allow_retry(self) -> None:
        write = apply_module.write_json
        failures = []
        def fail_once(path: Path, payload: dict) -> None:
            if path == self.output / 'summary.json' and not failures:
                failures.append(True)
                raise OSError('Receipt write failed')
            write(path, payload)
        with patch.object(apply_module, 'write_json', side_effect=fail_once):
            self.assertEqual(1, self.run_apply())
        summary = json.loads((self.output / 'summary.json').read_text())
        self.assertEqual('apply_receipt_failed', summary['error'])
        self.assertEqual(1, summary['success_count'])
        self.assertEqual(0, summary['failure_count'])
        self.assertNotIn('simulate', summary['next_action'].lower())
        self.assertEqual(b'Reviewed candidate\r\n', (self.case.target / '_index.md').read_bytes())
        self.assertEqual(0, self.run_apply())

    def test_persistent_summary_failure_should_print_the_actual_promoted_count(self) -> None:
        write = apply_module.write_json
        def fail_summary(path: Path, payload: dict) -> None:
            if path == self.output / 'summary.json':
                raise OSError('Receipt stays unavailable')
            write(path, payload)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), patch.object(apply_module, 'write_json', side_effect=fail_summary):
            self.assertEqual(1, self.run_apply())
        self.assertIn('success_count=1', stdout.getvalue())
        self.assertEqual(b'Reviewed candidate\r\n', (self.case.target / '_index.md').read_bytes())

    def test_report_failure_should_not_replace_success_counts_with_zero(self) -> None:
        write = apply_module.write_text
        def fail_report(path: Path, content: str) -> None:
            if path == self.output / 'report.md':
                raise OSError('Report stays unavailable')
            write(path, content)
        with patch.object(apply_module, 'write_text', side_effect=fail_report):
            self.assertEqual(1, self.run_apply())
        summary = json.loads((self.output / 'summary.json').read_text())
        self.assertEqual('apply_receipt_failed', summary['error'])
        self.assertEqual(1, summary['success_count'])

    def test_mixed_already_applied_and_pending_pages_should_finish_without_rewriting_first_page(self) -> None:
        extra = self.case.target / 'feature.md'
        self.source, _ = self.case.candidate('two-pages', {'_index.md': b'New index', 'feature.md': b'New feature'})
        apply_module.apply_candidate_pages(repo_root=self.case.root, out_dir=self.output, context=self.case.context(), pages=['_index.md'], candidate_from=str(self.source))
        import _overlay_generator_runtime as runtime
        with patch.object(runtime.os, 'replace', wraps=runtime.os.replace) as replacements:
            result = apply_module.apply_candidate_pages(repo_root=self.case.root, out_dir=self.output, context=self.case.context(), pages=['_index.md', 'feature.md'], candidate_from=str(self.source))
        self.assertEqual(2, result['success_count'])
        self.assertEqual(1, replacements.call_count)
        self.assertEqual(b'New feature', extra.read_bytes())


if __name__ == '__main__':
    unittest.main()
