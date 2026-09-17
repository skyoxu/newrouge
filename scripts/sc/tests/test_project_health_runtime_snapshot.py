"""Real Git snapshots and separate workspace evidence (ADR-0035)."""
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts/python'))
from _project_health_runtime_snapshot import prepare_snapshot
from project_health_runtime import verify
from project_health_knowledge import base_dir, write_json, apply_runtime_results


class SnapshotTests(unittest.TestCase):
    def test_excluded_import_paths_still_reject_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL).decode().strip()

            git('init', '-b', 'main')
            cache = root / 'Tests.Godot/addons/gdUnit4/cache.png.import'
            cache.parent.mkdir(parents=True)
            cache.write_text('generated', encoding='utf-8')
            git('add', '.')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'initial')
            revision = git('rev-parse', 'HEAD')
            (root / '.git/info/exclude').write_text('logs/\n', encoding='utf-8')

            with patch('_project_health_runtime_snapshot.stat.S_ISLNK', return_value=True):
                with self.assertRaisesRegex(ValueError, 'tracked symlinks'):
                    prepare_snapshot(root, root / 'logs/main/source', revision, 'main', time.monotonic() + 30)
            source = MagicMock()
            source.is_symlink.return_value = True
            with patch('_project_health_runtime_snapshot.safe_file', return_value=source):
                with self.assertRaisesRegex(ValueError, 'workspace symlinks'):
                    prepare_snapshot(root, root / 'logs/workspace/source', revision, 'workspace', time.monotonic() + 30)

    def test_snapshots_exclude_only_gdunit_plugin_import_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL).decode().strip()

            git('init', '-b', 'main')
            excluded = root / 'Tests.Godot/addons/gdUnit4/icons/test.png.import'
            plugin_file = root / 'Tests.Godot/addons/gdUnit4/scripts/gdunit.gd'
            retained = root / 'Game.Godot/Assets/player.png.import'
            excluded.parent.mkdir(parents=True)
            plugin_file.parent.mkdir(parents=True)
            retained.parent.mkdir(parents=True)
            excluded.write_text('plugin-cache', encoding='utf-8')
            plugin_file.write_text('plugin-binary', encoding='utf-8')
            retained.write_text('project-import', encoding='utf-8')
            git('add', '.')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'initial')
            revision = git('rev-parse', 'HEAD')
            (root / '.git/info/exclude').write_text('logs/\n', encoding='utf-8')

            for mode in ('main', 'workspace'):
                snapshot = root / f'logs/{mode}/source'
                manifest = prepare_snapshot(root, snapshot, revision, mode, time.monotonic() + 30)
                self.assertFalse((snapshot / excluded.relative_to(root)).exists())
                self.assertNotIn(excluded.relative_to(root).as_posix(), manifest['files'])
                self.assertEqual((snapshot / plugin_file.relative_to(root)).read_text(encoding='utf-8'), 'plugin-binary')
                self.assertIn(plugin_file.relative_to(root).as_posix(), manifest['files'])
                self.assertEqual((snapshot / retained.relative_to(root)).read_text(encoding='utf-8'), 'project-import')
                self.assertIn(retained.relative_to(root).as_posix(), manifest['files'])

    def test_main_run_remains_verified_when_only_excluded_import_is_regenerated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL).decode().strip()

            git('init', '-b', 'main')
            ref = 'Tests.Godot/tests/example.gd'
            excluded_path = 'Tests.Godot/addons/gdUnit4/icons/test.png.import'
            (root / ref).parent.mkdir(parents=True)
            (root / ref).write_text('extends Node\n', encoding='utf-8')
            excluded = root / excluded_path
            excluded.parent.mkdir(parents=True)
            excluded.write_text('before-run', encoding='utf-8')
            git('add', '.')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'initial')
            revision = git('rev-parse', 'HEAD')
            (root / '.git/info/exclude').write_text('logs/\n', encoding='utf-8')
            write_json(base_dir(root) / 'latest.json', {'revision': revision, 'sources': {
                '.taskmaster/tasks/tasks_gameplay.json': json.dumps([{'taskmaster_id': 18, 'test_refs': [ref]}]),
                ref: 'pass'}, 'tasks': [{'task': {'id': 18}, 'godot': {}}]})

            def passing_run(run_root, task, godot_bin, timeout, source_revision):
                generated = Path(task['_execution_root']) / excluded_path
                generated.parent.mkdir(parents=True, exist_ok=True)
                generated.write_text('regenerated', encoding='utf-8')
                return {'task_id': '18', 'source_revision': source_revision, 'test_refs': [ref], 'scenes': [],
                        'status': 'passed', 'reason': None, 'started_at': 's', 'finished_at': 'f',
                        'evidence_path': 'logs/ci/project-health-knowledge/runtime/task.json', 'exit_code': 0,
                        'runtime_verified': False}

            with patch('project_health_runtime._run_task', side_effect=passing_run):
                result = verify(root, 'godot.exe', 10, task_id='18', mode='main')
            task = result['tasks'][0]
            self.assertEqual(task['status'], 'passed')
            self.assertTrue(task['runtime_verified'])

    def test_main_run_becomes_unverified_when_retained_plugin_file_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL).decode().strip()

            git('init', '-b', 'main')
            ref = 'Tests.Godot/tests/example.gd'
            retained_path = 'Tests.Godot/addons/gdUnit4/scripts/gdunit.gd'
            (root / ref).parent.mkdir(parents=True)
            (root / ref).write_text('extends Node\n', encoding='utf-8')
            retained = root / retained_path
            retained.parent.mkdir(parents=True)
            retained.write_text('before-run', encoding='utf-8')
            git('add', '.')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'initial')
            revision = git('rev-parse', 'HEAD')
            (root / '.git/info/exclude').write_text('logs/\n', encoding='utf-8')
            write_json(base_dir(root) / 'latest.json', {'revision': revision, 'sources': {
                '.taskmaster/tasks/tasks_gameplay.json': json.dumps([{'taskmaster_id': 18, 'test_refs': [ref]}]),
                ref: 'pass'}, 'tasks': [{'task': {'id': 18}, 'godot': {}}]})

            def passing_run(run_root, task, godot_bin, timeout, source_revision):
                changed = Path(task['_execution_root']) / retained_path
                changed.write_text('changed-during-run', encoding='utf-8')
                return {'task_id': '18', 'source_revision': source_revision, 'test_refs': [ref], 'scenes': [],
                        'status': 'passed', 'reason': None, 'started_at': 's', 'finished_at': 'f',
                        'evidence_path': 'logs/ci/project-health-knowledge/runtime/task.json', 'exit_code': 0,
                        'runtime_verified': False}

            with patch('project_health_runtime._run_task', side_effect=passing_run):
                result = verify(root, 'godot.exe', 10, task_id='18', mode='main')
            task = result['tasks'][0]
            self.assertEqual(task['status'], 'runtime_unverified')
            self.assertFalse(task['runtime_verified'])

    def test_main_run_becomes_unverified_when_retained_project_import_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.DEVNULL).decode().strip()

            git('init', '-b', 'main')
            ref = 'Tests.Godot/tests/example.gd'
            retained_path = 'Game.Godot/Assets/player.png.import'
            (root / ref).parent.mkdir(parents=True)
            (root / ref).write_text('extends Node\n', encoding='utf-8')
            retained = root / retained_path
            retained.parent.mkdir(parents=True)
            retained.write_text('before-run', encoding='utf-8')
            git('add', '.')
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'initial')
            revision = git('rev-parse', 'HEAD')
            (root / '.git/info/exclude').write_text('logs/\n', encoding='utf-8')
            write_json(base_dir(root) / 'latest.json', {'revision': revision, 'sources': {
                '.taskmaster/tasks/tasks_gameplay.json': json.dumps([{'taskmaster_id': 18, 'test_refs': [ref]}]),
                ref: 'pass'}, 'tasks': [{'task': {'id': 18}, 'godot': {}}]})

            def passing_run(run_root, task, godot_bin, timeout, source_revision):
                changed = Path(task['_execution_root']) / retained_path
                changed.write_text('changed-during-run', encoding='utf-8')
                return {'task_id': '18', 'source_revision': source_revision, 'test_refs': [ref], 'scenes': [],
                        'status': 'passed', 'reason': None, 'started_at': 's', 'finished_at': 'f',
                        'evidence_path': 'logs/ci/project-health-knowledge/runtime/task.json', 'exit_code': 0,
                        'runtime_verified': False}

            with patch('project_health_runtime._run_task', side_effect=passing_run):
                result = verify(root, 'godot.exe', 10, task_id='18', mode='main')
            task = result['tasks'][0]
            self.assertEqual(task['status'], 'runtime_unverified')
            self.assertFalse(task['runtime_verified'])

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
