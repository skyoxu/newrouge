from __future__ import annotations

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO_ROOT / 'scripts/sc'), str(REPO_ROOT / 'scripts/python')]
import _sc_test_steps
import _repair_guidance
import run_dotnet
import _unit_metrics


TRX = '<TestRun><Results><UnitTestResult testName="{name}" outcome="Failed"><Output><ErrorInfo><Message>Recorded failure</Message></ErrorInfo></Output></UnitTestResult></Results></TestRun>'


class UnitEvidenceRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.out = self.root / 'logs/ci/sc-test'
        self.out.mkdir(parents=True)

    def run_unit(self, execute: object) -> dict:
        with patch.object(_sc_test_steps, 'repo_root', return_value=self.root), patch.object(_sc_test_steps, 'task_scoped_cs_refs', return_value=[]), patch.object(_sc_test_steps, 'run_cmd', side_effect=execute):
            return _sc_test_steps.run_unit(self.out, 'Game.sln', 'Debug', run_id='new-run', task_id='7')

    def render(self, unit: dict, *, snapshot: Path | None = None) -> str:
        snapshot = snapshot or self.out
        summary_path = snapshot / 'summary.json'
        summary_path.write_text(json.dumps({'task_id': '7', 'run_id': 'new-run', 'steps': [unit]}), encoding='utf-8')
        summary = {'status': 'fail', 'run_id': 'new-run', 'steps': [{
            'name': 'sc-test', 'status': 'fail', 'summary_file': str(summary_path),
            'cmd': ['py', '-3', 'scripts/sc/test.py', '--task-id', '7'],
        }]}
        with patch.object(_repair_guidance, 'repo_root', return_value=self.root):
            guide = _repair_guidance.build_repair_guide(summary, task_id='7', out_dir=self.root / 'logs/ci/pipeline')
        return _repair_guidance.render_repair_guide_markdown(guide)

    def test_compile_failure_should_report_current_error_instead_of_retained_trx(self) -> None:
        old = self.root / 'Game.Core.Tests/TestResults/attempt-1/tests.trx'
        old.parent.mkdir(parents=True)
        old.write_text(TRX.format(name='UnrelatedOldFailure'), encoding='utf-8')
        def execute(cmd: list[str], **kwargs: object) -> tuple[int, str]:
            cwd = Path.cwd()
            output = io.StringIO()
            os.chdir(self.root)
            try:
                with contextlib.redirect_stdout(output), patch.object(run_dotnet, 'run_cmd', side_effect=[(0, 'Restore succeeded'), (1, 'error CS1002: ; expected in Game.Core/NewCode.cs')]), patch.object(run_dotnet, '_best_effort_cleanup_testhosts'):
                    rc = run_dotnet.main(cmd[3:])
            finally:
                os.chdir(cwd)
            return rc, output.getvalue()
        text = self.render(self.run_unit(execute))
        self.assertNotIn('UnrelatedOldFailure', text)
        self.assertIn('CS1002', text)

    def test_saved_unit_evidence_should_survive_live_report_replacement_and_deletion(self) -> None:
        def execute(cmd: list[str], **kwargs: object) -> tuple[int, str]:
            directory = Path(cmd[cmd.index('--out-dir') + 1])
            directory.mkdir(parents=True, exist_ok=True)
            selected = str(self.root / 'Game.Core.Tests/TestResults/attempt-1/tests.trx')
            Path(selected).parent.mkdir(parents=True, exist_ok=True)
            Path(selected).write_text(TRX.format(name='CurrentFailure'), encoding='utf-8')
            payload = {'restore_rc': 0, 'test_rc': 1, 'artifacts_detected': {'trx_paths': [selected]}, 'artifacts_selected': {'trx': selected}}
            (directory / 'summary.json').write_text(json.dumps(payload), encoding='utf-8')
            (directory / 'tests.trx').write_text(TRX.format(name='RetainedCanonicalFailure'), encoding='utf-8')
            return 1, 'RUN_DOTNET status=tests_failed'
        unit = self.run_unit(execute)
        self.assertTrue(Path(unit['artifacts_dir']).is_relative_to(self.out))
        snapshot = self.root / 'logs/ci/pipeline/child-artifacts/sc-test'
        shutil.copytree(self.out, snapshot)
        shutil.rmtree(self.out)
        live = self.root / 'logs/unit' / _sc_test_steps.today_str()
        live.mkdir(parents=True, exist_ok=True)
        (live / 'run_id.txt').write_text('other-run', encoding='utf-8')
        (live / 'tests.trx').write_text(TRX.format(name='OtherTaskFailure'), encoding='utf-8')
        text = self.render(unit, snapshot=snapshot)
        self.assertIn('CurrentFailure', text)
        self.assertNotIn('OtherTaskFailure', text)
        self.assertNotIn('RetainedCanonicalFailure', text)

    def test_failed_dotnet_start_should_not_reuse_a_previous_daily_summary(self) -> None:
        live = self.root / 'logs/unit' / _sc_test_steps.today_str()
        live.mkdir(parents=True)
        selected = live / 'old.trx'
        selected.write_text(TRX.format(name='PreviousDayFailure'), encoding='utf-8')
        (live / 'summary.json').write_text(json.dumps({
            'restore_rc': 0, 'test_rc': 1, 'artifacts_selected': {'trx': str(selected)},
            'artifacts_detected': {'trx_paths': [str(selected)]},
        }), encoding='utf-8')
        text = self.render(self.run_unit(lambda *args, **kwargs: (1, 'error: dotnet failed to start')))
        self.assertNotIn('PreviousDayFailure', text)
        self.assertIn('dotnet failed to start', text)

    def test_unit_metrics_should_use_archived_counters_after_the_live_trx_changes(self) -> None:
        def execute(cmd: list[str], **kwargs: object) -> tuple[int, str]:
            directory = Path(cmd[cmd.index('--out-dir') + 1])
            selected = self.root / 'Game.Core.Tests/TestResults/tests.trx'
            selected.parent.mkdir(parents=True)
            selected.write_text('<TestRun><Counters total="2" failed="1" /></TestRun>')
            (directory / 'summary.json').write_text(json.dumps({
                'restore_rc': 0, 'test_rc': 1, 'artifacts_selected': {'trx': str(selected)},
                'artifacts_detected': {'trx_paths': [str(selected)]},
            }))
            return 1, 'RUN_DOTNET status=tests_failed'
        unit = self.run_unit(execute)
        selected = self.root / 'Game.Core.Tests/TestResults/tests.trx'
        selected.write_text('<TestRun><Counters total="99" passed="99" /></TestRun>')
        directory = Path(unit['artifacts_dir'])
        metrics = _unit_metrics._collect_unit_metrics_from_dir(directory)
        self.assertEqual(2, metrics['tests']['total'])
        self.assertEqual(str(directory / 'tests.trx'), metrics['trx'])
        (directory / 'tests.trx').unlink()
        self.assertIsNone(_unit_metrics._collect_unit_metrics_from_dir(directory)['tests'])


if __name__ == '__main__':
    unittest.main()
