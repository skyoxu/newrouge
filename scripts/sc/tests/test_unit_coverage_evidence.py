from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import test_unit_evidence_recovery as fixtures
import _unit_metrics
import run_dotnet


OLD_COVERAGE = '<coverage lines-covered="100" lines-valid="100" branches-covered="100" branches-valid="100"/>'
CURRENT_COVERAGE = '<coverage lines-covered="84" lines-valid="100" branches-covered="80" branches-valid="100"/>'


class UnitCoverageEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.case = fixtures.UnitEvidenceRecoveryTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def current_unit(self, *, restore_rc: int = 0) -> dict:
        def execute(cmd: list[str], **kwargs: object) -> tuple[int, str]:
            directory = Path(cmd[cmd.index('--out-dir') + 1])
            selected = self.case.root / 'Game.Core.Tests/TestResults/current/coverage.cobertura.xml'
            selected.parent.mkdir(parents=True)
            selected.write_text(CURRENT_COVERAGE)
            (directory / 'coverage.cobertura.xml').write_text(OLD_COVERAGE)
            (directory / 'summary.json').write_text(json.dumps({
                'restore_rc': restore_rc, 'test_rc': 0, 'threshold_ok': True,
                'coverage': {'line_pct': 84.0, 'branch_pct': 80.0},
                'artifacts_selected': {'coverage': str(selected)},
                'artifacts_detected': {'coverage_paths': [str(selected)]},
            }))
            return 0, 'RUN_DOTNET status=ok'
        return self.case.run_unit(execute)

    def test_compile_failure_should_not_archive_or_report_retained_coverage(self) -> None:
        old = self.case.root / 'Game.Core.Tests/TestResults/old/coverage.cobertura.xml'
        old.parent.mkdir(parents=True)
        old.write_text(OLD_COVERAGE)
        def execute(cmd: list[str], **kwargs: object) -> tuple[int, str]:
            cwd = Path.cwd()
            output = io.StringIO()
            os.chdir(self.case.root)
            try:
                with contextlib.redirect_stdout(output), patch.object(run_dotnet, 'run_cmd', side_effect=[(0, 'Restore succeeded'), (1, 'error CS1002: ; expected')]), patch.object(run_dotnet, '_best_effort_cleanup_testhosts'):
                    rc = run_dotnet.main(cmd[3:])
            finally:
                os.chdir(cwd)
            return rc, output.getvalue()
        unit = self.case.run_unit(execute)
        saved = Path(unit['artifacts_dir'])
        self.assertEqual(1, unit['rc'])
        self.assertFalse((saved / 'coverage.cobertura.xml').exists())
        metrics = _unit_metrics._collect_unit_metrics_from_dir(saved)
        self.assertIsNone(metrics['coverage']['line_pct'])
        self.assertFalse(metrics['threshold_ok'])
        self.assertIsNone(metrics['coverage_cobertura'])
        self.assertIn('CS1002', self.case.render(unit))

    def test_legacy_live_metrics_should_reject_a_fallback_coverage_selection(self) -> None:
        directory = self.case.root / 'logs/unit/day'
        directory.mkdir(parents=True)
        old = directory / 'coverage.cobertura.xml'
        old.write_text(OLD_COVERAGE)
        (directory / 'summary.json').write_text(json.dumps({
            'restore_rc': 0, 'test_rc': 1, 'threshold_ok': True,
            'coverage': {'line_pct': 100.0, 'branch_pct': 100.0},
            'artifacts_selected': {'coverage': str(old)},
            'artifacts_detected': {'coverage_paths': []},
        }))
        metrics = _unit_metrics._collect_unit_metrics_from_dir(directory)
        self.assertIsNone(metrics['coverage']['line_pct'])
        self.assertFalse(metrics['threshold_ok'])

    def test_current_coverage_should_be_copied_from_its_emitted_source_and_survive_source_deletion(self) -> None:
        unit = self.current_unit()
        saved = Path(unit['artifacts_dir'])
        self.assertEqual(CURRENT_COVERAGE, (saved / 'coverage.cobertura.xml').read_text())
        (self.case.root / 'Game.Core.Tests/TestResults/current/coverage.cobertura.xml').unlink()
        metrics = _unit_metrics._collect_unit_metrics_from_dir(saved)
        self.assertEqual(84.0, metrics['coverage']['line_pct'])
        self.assertTrue(metrics['threshold_ok'])
        self.assertEqual(str(saved / 'coverage.cobertura.xml'), metrics['coverage_cobertura'])

    def test_missing_archived_coverage_should_not_fall_back_to_the_live_source(self) -> None:
        unit = self.current_unit()
        saved = Path(unit['artifacts_dir'])
        (saved / 'coverage.cobertura.xml').unlink()
        metrics = _unit_metrics._collect_unit_metrics_from_dir(saved)
        self.assertIsNone(metrics['coverage']['line_pct'])
        self.assertFalse(metrics['threshold_ok'])
        self.assertIsNone(metrics['coverage_cobertura'])

    def test_restore_failure_should_reject_coverage_even_when_paths_match(self) -> None:
        unit = self.current_unit(restore_rc=1)
        saved = Path(unit['artifacts_dir'])
        self.assertFalse((saved / 'coverage.cobertura.xml').exists())
        self.assertFalse(_unit_metrics._collect_unit_metrics_from_dir(saved)['threshold_ok'])


if __name__ == '__main__':
    unittest.main()
