from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / 'scripts' / 'sc'))
sys.path.insert(0, str(REPO_ROOT / 'scripts' / 'python'))

import _repair_guidance
import resume_task


def write_doc(root: Path, name: str, task: str, run: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'# Recovery\n- Related task id(s): `{task}`\n- Related run id: `{run}`\n', encoding='utf-8')
    return path


def execution_context(root: Path) -> dict:
    with mock.patch.object(_repair_guidance, 'repo_root', return_value=root), mock.patch.object(_repair_guidance, '_run_git', return_value=''):
        return _repair_guidance.build_execution_context(
            task_id='7', requested_run_id='run-7', run_id='run-7', out_dir=root / 'logs' / 'pipeline',
            delivery_profile='fast-ship', security_profile='host-safe', llm_review_context={}, summary={'status': 'ok', 'steps': []},
        )


class RecoveryDocBindingTests(unittest.TestCase):
    def test_producer_and_resume_select_the_same_task_and_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for directory in ['execution-plans', 'decision-logs']:
                expected = write_doc(root, f'{directory}/2026-10-01-current.md', '7', 'run-7')
                other = write_doc(root, f'{directory}/2026-10-07-other.md', '99', 'run-99')
                os.utime(expected, (10, 10))
                os.utime(other, (100, 100))
            context = execution_context(root)
            for directory, field in [('execution-plans', 'latest_execution_plan'), ('decision-logs', 'latest_decision_log')]:
                related = resume_task._find_related_docs(root, directory, task_id='7', run_id='run-7', latest_rel='')
                self.assertEqual([f'{directory}/2026-10-01-current.md'], related)
                self.assertEqual(str(root / related[0]), context['paths'][field])

    def test_no_binding_leaves_pointers_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_doc(root, 'execution-plans/README.md', '7', 'run-7')
            write_doc(root, 'execution-plans/TEMPLATE.md', '7', 'run-7')
            write_doc(root, 'decision-logs/unrelated.md', '99', 'run-99')
            context = execution_context(root)
            self.assertEqual('', context['paths']['latest_execution_plan'])
            self.assertEqual('', context['paths']['latest_decision_log'])

    def test_explicit_other_task_cannot_match_by_run_or_pointer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = write_doc(root, 'execution-plans/other.md', '99', 'run-7')
            with path.open('a', encoding='utf-8') as stream:
                stream.write('- Related latest.json: `logs/ci/day/sc-review-pipeline-task-7/latest.json`\n')
            self.assertEqual([], resume_task._find_related_docs(
                root, 'execution-plans', task_id='7', run_id='run-7', latest_rel='logs/ci/day/sc-review-pipeline-task-7/latest.json',
            ))

    def test_exact_run_precedes_task_history_and_order_ignores_checkout_mtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            current = write_doc(root, 'execution-plans/2026-10-01-current.md', '7', 'run-7')
            history = write_doc(root, 'execution-plans/2026-10-07-history.md', '7', 'old-run')
            os.utime(current, (1, 1))
            os.utime(history, (100, 100))
            first = resume_task._find_related_docs(root, 'execution-plans', task_id='7', run_id='run-7', latest_rel='')
            os.utime(current, (200, 200))
            os.utime(history, (1, 1))
            self.assertEqual(first, resume_task._find_related_docs(root, 'execution-plans', task_id='7', run_id='run-7', latest_rel=''))
            self.assertEqual('execution-plans/2026-10-01-current.md', first[0])
            self.assertEqual(str(current), execution_context(root)['paths']['latest_execution_plan'])

    def test_equal_bindings_are_reproducible_and_unbound_files_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = write_doc(root, 'execution-plans/2026-10-01-a.md', '7', 'run-7')
            second = write_doc(root, 'execution-plans/2026-10-02-b.md', '7', 'run-7')
            unbound = root / 'execution-plans/2026-10-07-global.md'
            unbound.write_text('# No explicit binding\n', encoding='utf-8')
            os.utime(first, (200, 200))
            os.utime(second, (1, 1))
            related = resume_task._find_related_docs(root, 'execution-plans', task_id='7', run_id='run-7', latest_rel='')
            self.assertEqual(['execution-plans/2026-10-02-b.md', 'execution-plans/2026-10-01-a.md'], related)
            self.assertEqual(str(second), execution_context(root)['paths']['latest_execution_plan'])


if __name__ == '__main__':
    unittest.main()
