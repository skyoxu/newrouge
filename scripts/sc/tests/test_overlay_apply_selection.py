from __future__ import annotations

import contextlib
import io
import json
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import test_overlay_candidate_cli as fixtures
from _overlay_candidate_store import write_candidate_bundle


class OverlayApplySelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case = fixtures.OverlayCandidateCliTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        shutil.rmtree(self.case.target)
        self.pages = ['_index.md', '08-feature-slice-main-loop.md']
        self.assertEqual(0, self.single('--page-filter', ','.join(self.pages), '--run-suffix', 'inspected'))
        self.source = self.case.root / 'logs/ci/2026-10-07/sc-llm-overlay-gen-prd-test--inspected'
        self.expected = {name: (self.source / 'generated/PRD-TEST/08' / name).read_bytes() for name in self.pages}
        self.assertEqual(0, self.single('--apply', '--candidate-from', str(self.source), '--page-filter', '_index.md'))
        self.case.models.reset_mock()

    def single(self, *extra: str) -> int:
        with contextlib.redirect_stdout(io.StringIO()), patch.object(sys, 'argv', ['overlay', '--prd', 'prd.md', '--prd-id', 'PRD-TEST', *extra]):
            return fixtures.single.main()

    def batch(self, *extra: str) -> int:
        with contextlib.redirect_stdout(io.StringIO()), patch.object(sys, 'argv', ['overlay-batch', '--prd', 'prd.md', '--prd-id', 'PRD-TEST', *extra]):
            return fixtures.batch.main()

    def assert_pages_promoted(self) -> None:
        for name, content in self.expected.items():
            self.assertEqual(content, (self.case.target / name).read_bytes())
        self.case.models.assert_not_called()

    def test_explicit_selection_should_include_missing_candidate_pages_after_partial_apply(self) -> None:
        self.assertEqual(0, self.single('--apply', '--candidate-from', str(self.source), '--page-filter', ','.join(self.pages), '--run-suffix', 'pair'))
        self.assert_pages_promoted()
        summary = json.loads((self.case.root / 'logs/ci/2026-10-07/sc-llm-overlay-gen-prd-test--pair/summary.json').read_text())
        self.assertEqual(self.pages, summary['selected_pages'])
        self.assertEqual(2, summary['success_count'])

    def test_default_selection_should_follow_the_bound_manifest_after_partial_apply(self) -> None:
        self.assertEqual(0, self.single('--apply', '--candidate-from', str(self.source)))
        self.assert_pages_promoted()

    def test_single_family_selection_should_include_candidates_absent_from_disk(self) -> None:
        self.assertEqual(0, self.single('--apply', '--candidate-from', str(self.source), '--page-family', 'feature'))
        self.assert_pages_promoted()

    def test_batch_family_selection_should_include_saved_bundle_pages_absent_from_disk(self) -> None:
        pointer = json.loads((self.source / 'candidate-pointer.json').read_text())
        bundle = self.case.root / 'logs/ci/batch'
        write_candidate_bundle(repo_root=self.case.root, out_dir=bundle, results=[{'page': name, **pointer} for name in self.pages])
        self.assertEqual(0, self.batch('--apply', '--candidate-from', str(bundle), '--page-family', 'feature'))
        self.assert_pages_promoted()

    def test_implicit_selection_should_follow_recorded_candidate_pages_after_partial_apply(self) -> None:
        self.assertEqual(0, self.single('--apply', '--page-filter', ','.join(self.pages)))
        self.assert_pages_promoted()

    def test_unknown_explicit_page_should_block_the_entire_apply_instead_of_being_dropped(self) -> None:
        (self.case.target / '_index.md').unlink()
        missing = '08-feature-unknown.md'
        self.assertEqual(1, self.single('--apply', '--candidate-from', str(self.source), '--page-filter', '_index.md,' + missing, '--run-suffix', 'blocked'))
        self.assertFalse((self.case.target / '_index.md').exists())
        self.assertFalse((self.case.target / missing).exists())
        summary = json.loads((self.case.root / 'logs/ci/2026-10-07/sc-llm-overlay-gen-prd-test--blocked/summary.json').read_text())
        self.assertEqual('candidate_apply_blocked', summary['error'])
        self.assertIn(missing, summary['detail'])
        self.assertEqual(0, summary['success_count'])
        self.case.models.assert_not_called()


if __name__ == '__main__':
    unittest.main()
