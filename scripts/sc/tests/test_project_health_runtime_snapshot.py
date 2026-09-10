"""Real Git snapshots and separate workspace evidence (ADR-0035)."""
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts/python'))
from _project_health_runtime_snapshot import prepare_snapshot
from project_health_runtime import verify
from project_health_knowledge import base_dir, write_json, apply_runtime_results


class SnapshotTests(unittest.TestCase):
    def test_failed_report_exposes_assertion_counts(self):
        import project_health_runtime as runtime
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp)
            write_json(report / 'run-summary.json', {'results': {'tests': 87, 'failures': 2, 'errors': 0}})
            self.assertTrue(hasattr(runtime, '_report_counts'))
            self.assertEqual(runtime._report_counts(report), {'tests': 87, 'failures': 2, 'errors': 0})
            self.assertEqual(runtime._report_counts(report / 'missing'), {})

    def test_main_uses_commit_and_workspace_uses_dirty_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL).decode().strip()
            git('init', '-b', 'main')
            source = root / 'game.txt'
            source.write_text('committed', encoding='utf-8')
            git('add', '.')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'initial')
            revision = git('rev-parse', 'HEAD')
            source.write_text('edited', encoding='utf-8')
            (root / 'new.txt').write_text('new', encoding='utf-8')
            baseline = git('status', '--porcelain')
            # Output must not become an untracked input in the workspace fixture.
            (root / '.git/info/exclude').write_text('logs/\n', encoding='utf-8')
            main = root / 'logs/main/source'
            work = root / 'logs/workspace/source'
            prepare_snapshot(root, main, revision, 'main', time.monotonic() + 30)
            self.assertEqual((main / 'game.txt').read_text(), 'committed')
            self.assertFalse((main / 'new.txt').exists())
            manifest = prepare_snapshot(root, work, revision, 'workspace', time.monotonic() + 30)
            self.assertEqual((work / 'game.txt').read_text(), 'edited')
            self.assertEqual((work / 'new.txt').read_text(), 'new')
            self.assertTrue(manifest['source_revision'].startswith('workspace:'))
            self.assertEqual(git('status', '--porcelain'), baseline)

    def test_workspace_pass_does_not_replace_main_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ref = 'Tests.Godot/tests/example.gd'
            revision = 'a' * 40
            write_json(base_dir(root) / 'latest.json', {'revision': revision, 'sources': {
                '.taskmaster/tasks/tasks_gameplay.json': json.dumps([{'taskmaster_id': 18, 'test_refs': [ref]}]), ref: 'pass'},
                'tasks': [{'task': {'id': 18}, 'godot': {}}]})
            main_index = {'source_revision': revision, 'tasks': []}
            write_json(base_dir(root) / 'runtime/latest.json', main_index)
            evidence = {'task_id': '18', 'source_revision': 'workspace:hash', 'status': 'passed',
                        'test_refs': [ref], 'scenes': [], 'started_at': 's', 'finished_at': 'f',
                        'evidence_path': 'logs/ci/project-health-knowledge/runtime/task.json'}
            with patch('project_health_runtime.prepare_snapshot', return_value={'source_revision': 'workspace:hash', 'files': {}}), patch('project_health_runtime._run_task', return_value=evidence):
                result = verify(root, 'godot.exe', 10, task_id='18', mode='workspace')
            self.assertFalse(result['tasks'][0]['runtime_verified'])
            self.assertTrue(result['tasks'][0]['workspace_verified'])
            self.assertEqual(json.loads((base_dir(root) / 'runtime/latest.json').read_text()), main_index)
            self.assertFalse((base_dir(root) / 'runtime/batch.lock').exists())
            state = {'revision': revision, 'tasks': [{'task': {'id': 18}, 'godot': {'status': 'candidate', 'runtime_verified': False}}]}
            apply_runtime_results(root, state)
            self.assertFalse(state['tasks'][0]['godot']['runtime_verified'])
            self.assertEqual(state['tasks'][0]['godot']['workspace_evidence']['status'], 'passed')


if __name__ == '__main__':
    unittest.main()
