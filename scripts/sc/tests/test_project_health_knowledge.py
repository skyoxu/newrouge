"""Knowledge page SSOT, evidence and HTTP boundary tests."""
import http.client
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'scripts/python'))
from _project_health_tasks import task_details, task_page, attach_task_scenes, scene_bindings
from _project_health_http import handler_factory
from project_health_knowledge import safe_file, load_config, read_json, write_json
from impact_analyzer import ImpactAnalyzer, SymbolIndex
from project_health_knowledge import DEFAULT_CONFIG, scan, base_dir, validate_config
from project_health_knowledge import apply_runtime_eligibility, apply_runtime_results
from project_health_knowledge import status as knowledge_status
from _knowledge_catalog_builder import DirectorySnapshot
from project_health_runtime import _complete, _gameplay_tasks, _run_task, _runtime_inputs_match, verify


class TasksTests(unittest.TestCase):
    def make_scan_source(self, root):
        write_json(root / '.taskmaster/tasks/tasks.json', {
            'master': {'tasks': [{'id': 1, 'title': 'Main task', 'status': 'done'}]}})
        write_json(root / '.taskmaster/tasks/tasks_back.json', [{'taskmaster_id': 1}])
        write_json(root / '.taskmaster/tasks/tasks_gameplay.json', [{'taskmaster_id': 1}])
        write_json(root / 'knowledge/policies/consumer-policies.v1.json', {
            'policy_revision': 'test',
            'policies': [{'consumer': 'repository-session', 'domains': ['delivery'],
                          'statuses': ['active'], 'visibility': ['active'],
                          'exact_paths': [], 'path_prefixes': ['.taskmaster/tasks/']}],
        })
        write_json(root / 'knowledge/policies/source-exclusions.v1.json', {'rules': []})
        write_json(root / 'scripts/python/project_health_knowledge_config.json', {
            'source_paths': ['.taskmaster/tasks'], 'gdd_paths': [],
            'task_scene_bindings': [], 'query_aliases': {},
        })

    def test_git_scan_reads_local_main_without_changing_feature_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_scan_source(root)
            subprocess.run(['git', 'init', '-b', 'main'], cwd=root, check=True, capture_output=True)
            subprocess.run(['git', 'config', 'user.email', 'test@example.invalid'], cwd=root, check=True)
            subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=root, check=True)
            subprocess.run(['git', 'add', '.'], cwd=root, check=True)
            subprocess.run(['git', 'commit', '-m', 'main'], cwd=root, check=True, capture_output=True)
            main_revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
            subprocess.run(['git', 'switch', '-c', 'feature'], cwd=root, check=True, capture_output=True)
            write_json(root / '.taskmaster/tasks/tasks.json', {
                'master': {'tasks': [{'id': 1, 'title': 'Feature task', 'status': 'pending'}]}})
            result = scan(root)
            self.assertEqual(result['revision'], main_revision)
            self.assertEqual(result['summary']['statuses'], {'done': 1})
            self.assertEqual(subprocess.check_output(['git', 'branch', '--show-current'], cwd=root, text=True).strip(), 'feature')

    def test_git_scan_fails_when_local_main_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_scan_source(root)
            subprocess.run(['git', 'init', '-b', 'feature'], cwd=root, check=True, capture_output=True)
            with self.assertRaises(Exception):
                scan(root)

    def test_directory_scan_uses_bounded_sources_and_content_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_scan_source(root)
            write_json(root / 'logs/ignored.json', {'secret': True})
            result = scan(root)
            self.assertEqual(result['branch'], 'directory')
            self.assertTrue(result['revision'].startswith('directory:'))
            self.assertEqual(result['summary']['total'], 1)
            state = read_json(base_dir(root) / 'latest.json')
            self.assertNotIn('logs/ignored.json', state['sources'])

    def test_runtime_candidates_use_scanned_gameplay_view_and_deduplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [
                {'taskmaster_id': 1, 'test_refs': ['Game.Core.Tests/A.cs']},
                {'taskmaster_id': 2, 'test_refs': ['Tests.Godot/tests/test_a.gd']},
                {'taskmaster_id': '2', 'test_refs': ['Tests.Godot/tests/test_duplicate.gd']},
                {'taskmaster_id': 3, 'testStrategy': 'Run GdUnit acceptance'},
                {'taskmaster_id': 4, 'description': 'governance only'},
            ]
            write_json(base_dir(root) / 'latest.json', {
                'revision': 'a' * 40,
                'sources': {'.taskmaster/tasks/tasks_gameplay.json': json.dumps(rows),
                            'Tests.Godot/tests/test_a.gd': 'func test_a(): pass',
                            'Tests.Godot/tests/test_duplicate.gd': 'func test_duplicate(): pass'},
                'tasks': [{'task': {'id': i}, 'godot': {'scenes': []}} for i in range(1, 5)],
            })
            candidates = _gameplay_tasks(root)
            self.assertEqual([str(row['taskmaster_id']) for row in candidates], ['2', '3'])
            self.assertEqual(candidates[0]['runtime_test_refs'], ['Tests.Godot/tests/test_a.gd'])
            self.assertEqual(candidates[1]['runtime_test_refs'], [])
            all_gameplay = _gameplay_tasks(root, include_all=True)
            self.assertEqual([str(row['taskmaster_id']) for row in all_gameplay], ['1', '2', '3', '4'])
            self.assertEqual(all_gameplay[-1]['runtime_test_refs'], [])

    def test_runtime_selection_only_enables_tasks_with_scanned_godot_assertions(self):
        state = {
            'sources': {
                '.taskmaster/tasks/tasks_gameplay.json': json.dumps([
                    {'taskmaster_id': 1, 'test_refs': ['Tests.Godot/tests/test_one.gd']},
                    {'taskmaster_id': 2, 'test_refs': ['Game.Core.Tests/Two.cs']},
                ]),
                'Tests.Godot/tests/test_one.gd': 'func test_one(): pass',
            },
            'tasks': [
                {'task': {'id': 1}, 'godot': {}},
                {'task': {'id': 2}, 'godot': {}},
            ],
        }
        apply_runtime_eligibility(state)
        self.assertTrue(state['tasks'][0]['godot']['runtime_eligible'])
        self.assertFalse(state['tasks'][1]['godot']['runtime_eligible'])

    def test_runtime_candidates_reject_unsafe_or_non_master_task_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [{'taskmaster_id': '../7', 'test_refs': ['Tests.Godot/tests/test_a.gd']}]
            state = {'revision': 'a' * 40,
                     'sources': {'.taskmaster/tasks/tasks_gameplay.json': json.dumps(rows),
                                 'Tests.Godot/tests/test_a.gd': 'pass'},
                     'tasks': [{'task': {'id': 7}, 'godot': {'scenes': []}}]}
            with self.assertRaisesRegex(ValueError, 'canonical positive numeric'):
                _gameplay_tasks(root, state)
            state['sources']['.taskmaster/tasks/tasks_gameplay.json'] = json.dumps([
                {'taskmaster_id': 8, 'test_refs': ['Tests.Godot/tests/test_a.gd']}])
            self.assertEqual(_gameplay_tasks(root, state), [])

    @mock.patch('project_health_runtime.subprocess.run')
    def test_run_task_uses_only_scoped_refs_and_preserves_cleanup_margin(self, run):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run.return_value = subprocess.CompletedProcess([], 0, '', '')
            task = {'taskmaster_id': '7', 'runtime_test_refs': ['Tests.Godot/tests/test_seven.gd'],
                    'static_godot': {'scenes': [{'scene': 'Game.Godot/Scenes/Seven.tscn'}]}}
            result = _run_task(root, task, 'godot.exe', 12, 'a' * 40)
            command = run.call_args.args[0]
            self.assertEqual(run.call_args.kwargs['timeout'], 42)
            self.assertEqual(command[command.index('--add') + 1], 'tests/test_seven.gd')
            self.assertEqual(result['source_revision'], 'a' * 40)
            self.assertEqual(read_json(root / result['evidence_path']), result)

    @mock.patch('project_health_runtime.subprocess.run')
    @mock.patch('project_health_runtime._main_revision', return_value='a' * 40)
    def test_main_snapshot_gate_does_not_inspect_workspace_difference(self, _, run):
        run.side_effect = [subprocess.CompletedProcess([], 1), subprocess.CompletedProcess([], 0, ' M Tests.Godot/a.gd', '')]
        matched, reason = _runtime_inputs_match(Path('C:/repo'), 'a' * 40)
        self.assertTrue(matched)
        self.assertIsNone(reason)
        run.assert_not_called()

    def test_runtime_evidence_requires_task_assertions_and_matching_main(self):
        complete = {'task_id': 2, 'source_revision': 'a' * 40,
                    'test_refs': ['Tests.Godot/tests/test_a.gd'], 'scenes': [],
                    'status': 'passed', 'started_at': 'start', 'finished_at': 'finish',
                    'evidence_path': 'logs/evidence.json'}
        self.assertTrue(_complete(complete))
        self.assertFalse(_complete({**complete, 'test_refs': []}))
        self.assertFalse(_complete({key: value for key, value in complete.items() if key != 'scenes'}))

    def test_runtime_results_merge_with_static_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = {'revision': 'a' * 40, 'tasks': [
                {'task': {'id': 1}, 'godot': {'status': 'static_attached', 'runtime_verified': False}},
                {'task': {'id': 2}, 'godot': {'status': 'candidate', 'runtime_verified': False}},
                {'task': {'id': 3}, 'godot': {'status': 'unmapped', 'runtime_verified': False}},
            ]}
            write_json(base_dir(root) / 'runtime/latest.json', {
                'source_revision': 'a' * 40,
                'tasks': [
                    {'task_id': '1', 'source_revision': 'a' * 40, 'status': 'failed',
                     'reason': 'assertion failed', 'test_refs': ['Tests.Godot/tests/test_one.gd'],
                     'scenes': [], 'started_at': 'start', 'finished_at': 'finish',
                     'evidence_path': 'logs/ci/project-health-knowledge/runtime/one.json',
                     'runtime_verified': False},
                    {'task_id': 2, 'source_revision': 'a' * 40, 'status': 'passed',
                     'test_refs': ['Tests.Godot/tests/test_two.gd'], 'scenes': [],
                     'started_at': 'start', 'finished_at': 'finish',
                     'evidence_path': 'logs/ci/project-health-knowledge/runtime/two.json',
                     'runtime_verified': True},
                ],
            })
            runtime = read_json(base_dir(root) / 'runtime/latest.json')
            for evidence in runtime['tasks']:
                write_json(root / evidence['evidence_path'], evidence)
            apply_runtime_results(root, state)
            self.assertEqual(state['tasks'][0]['godot']['status'], 'runtime_failed_static_attached')
            self.assertEqual(state['tasks'][0]['godot']['runtime_evidence']['reason'], 'assertion failed')
            self.assertEqual(state['tasks'][1]['godot']['status'], 'runtime_verified')
            self.assertEqual(state['tasks'][2]['godot']['status'], 'unmapped')
            self.assertEqual(state['tasks'][2]['godot']['runtime_status'], 'runtime_unverified')

            (root / runtime['tasks'][1]['evidence_path']).unlink()
            fresh = {'revision': 'a' * 40, 'tasks': [
                {'task': {'id': 2}, 'godot': {'status': 'candidate', 'runtime_verified': False}}]}
            apply_runtime_results(root, fresh)
            self.assertFalse(fresh['tasks'][0]['godot']['runtime_verified'])
            self.assertEqual(fresh['tasks'][0]['godot']['status'], 'candidate')

    def test_status_marks_runtime_summary_stale_on_revision_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(base_dir(root) / 'runtime/latest.json', {
                'source_revision': 'b' * 40, 'summary': {'total': 9}})
            result = knowledge_status(root, {'revision': 'a' * 40, 'tasks': [], 'summary': {}})
            self.assertEqual(result['runtime']['total'], 0)
            self.assertTrue(result['runtime']['stale'])

    @mock.patch('project_health_runtime.prepare_snapshot', return_value={'source_revision': 'a' * 40, 'files': {}})
    @mock.patch('project_health_runtime._scan_revision', return_value='a' * 40)
    @mock.patch('project_health_runtime._run_task')
    @mock.patch('project_health_runtime._main_revision', return_value='a' * 40)
    def test_runtime_verify_is_targeted_and_requires_complete_revision_bound_evidence(self, _, run_task, __, ___):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [{'taskmaster_id': 1, 'test_refs': ['Tests.Godot/tests/test_one.gd']},
                    {'taskmaster_id': 2, 'test_refs': ['Tests.Godot/tests/test_two.gd']}]
            write_json(base_dir(root) / 'latest.json', {
                'revision': 'a' * 40,
                'sources': {'.taskmaster/tasks/tasks_gameplay.json': json.dumps(rows),
                            'Tests.Godot/tests/test_one.gd': 'func test_one(): pass',
                            'Tests.Godot/tests/test_two.gd': 'func test_two(): pass'},
                'tasks': [{'task': {'id': i}, 'godot': {'scenes': []}} for i in (1, 2)],
            })
            run_task.return_value = {'task_id': 2, 'source_revision': 'a' * 40,
                                     'test_refs': ['Tests.Godot/tests/test_two.gd'], 'scenes': [],
                                     'status': 'passed', 'started_at': 'start', 'finished_at': 'finish',
                                     'evidence_path': 'logs/evidence.json'}
            result = verify(root, 'godot.exe', 10, task_id='2', global_timeout=60)
            self.assertEqual(run_task.call_count, 1)
            self.assertTrue(result['tasks'][0]['runtime_verified'])

    @mock.patch('project_health_runtime.prepare_snapshot', return_value={'source_revision': 'a' * 40, 'files': {}})
    @mock.patch('project_health_runtime._scan_revision', return_value='a' * 40)
    @mock.patch('project_health_runtime._run_task')
    @mock.patch('project_health_runtime._main_revision', return_value='a' * 40)
    def test_targeted_runtime_merge_preserves_other_task_evidence(self, _, run_task, __, ___):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [{'taskmaster_id': i, 'test_refs': [f'Tests.Godot/tests/test_{i}.gd']} for i in (1, 2)]
            sources = {'.taskmaster/tasks/tasks_gameplay.json': json.dumps(rows),
                       **{f'Tests.Godot/tests/test_{i}.gd': 'pass' for i in (1, 2)}}
            write_json(base_dir(root) / 'latest.json', {'revision': 'a' * 40, 'sources': sources,
                       'tasks': [{'task': {'id': i}, 'godot': {'scenes': []}} for i in (1, 2)]})
            old = {'task_id': '1', 'source_revision': 'a' * 40, 'test_refs': ['Tests.Godot/tests/test_1.gd'],
                   'scenes': [], 'status': 'passed', 'reason': None, 'started_at': 's', 'finished_at': 'f',
                   'evidence_path': 'logs/ci/project-health-knowledge/runtime/old.json', 'runtime_verified': True}
            write_json(base_dir(root) / 'runtime/latest.json', {'source_revision': 'a' * 40, 'tasks': [old], 'summary': {}})
            run_task.return_value = {**old, 'task_id': '2', 'test_refs': ['Tests.Godot/tests/test_2.gd'],
                                     'evidence_path': 'logs/ci/project-health-knowledge/runtime/new.json'}
            result = verify(root, 'godot.exe', 10, task_id='2')
            self.assertEqual({row['task_id'] for row in result['tasks']}, {'1', '2'})

    @mock.patch('project_health_runtime.prepare_snapshot', return_value={'source_revision': 'a' * 40, 'files': {}})
    @mock.patch('project_health_runtime._scan_revision', return_value='a' * 40)
    @mock.patch('project_health_runtime._run_task')
    @mock.patch('project_health_runtime._main_revision', return_value='a' * 40)
    def test_multi_task_runtime_runs_only_selection_and_preserves_other_evidence(self, _, run_task, __, ___):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [{'taskmaster_id': i, 'test_refs': [f'Tests.Godot/tests/test_{i}.gd']} for i in (1, 2, 3)]
            sources = {'.taskmaster/tasks/tasks_gameplay.json': json.dumps(rows),
                       **{f'Tests.Godot/tests/test_{i}.gd': 'pass' for i in (1, 2, 3)}}
            write_json(base_dir(root) / 'latest.json', {'revision': 'a' * 40, 'sources': sources,
                       'tasks': [{'task': {'id': i}, 'godot': {'scenes': []}} for i in (1, 2, 3)]})
            old = {'task_id': '1', 'source_revision': 'a' * 40, 'test_refs': ['Tests.Godot/tests/test_1.gd'],
                   'scenes': [], 'status': 'passed', 'reason': None, 'started_at': 's', 'finished_at': 'f',
                   'evidence_path': 'logs/ci/project-health-knowledge/runtime/old.json', 'runtime_verified': True}
            write_json(base_dir(root) / 'runtime/latest.json', {'source_revision': 'a' * 40,
                       'tasks': [old], 'summary': {}})
            run_task.side_effect = lambda root, task, godot_bin, timeout, revision: {
                **old, 'task_id': task['taskmaster_id'], 'test_refs': task['runtime_test_refs'],
                'evidence_path': f"logs/ci/project-health-knowledge/runtime/{task['taskmaster_id']}.json"}
            result = verify(root, 'godot.exe', 10, task_ids=['2', '3'])
            self.assertEqual(run_task.call_count, 2)
            self.assertEqual({row['task_id'] for row in result['tasks']}, {'1', '2', '3'})

    @mock.patch('project_health_runtime.prepare_snapshot', return_value={'source_revision': 'a' * 40, 'files': {}})
    @mock.patch('project_health_runtime._scan_revision', return_value='b' * 40)
    @mock.patch('project_health_runtime._run_task')
    @mock.patch('project_health_runtime._main_revision', return_value='a' * 40)
    def test_revision_drift_prevents_verified_result(self, _, run_task, __, ___):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [{'taskmaster_id': 1, 'test_refs': ['Tests.Godot/tests/test_1.gd']}]
            write_json(base_dir(root) / 'latest.json', {'revision': 'a' * 40,
                       'sources': {'.taskmaster/tasks/tasks_gameplay.json': json.dumps(rows),
                                   'Tests.Godot/tests/test_1.gd': 'pass'},
                       'tasks': [{'task': {'id': 1}, 'godot': {'scenes': []}}]})
            run_task.return_value = {'task_id': '1', 'source_revision': 'a' * 40,
                                     'test_refs': ['Tests.Godot/tests/test_1.gd'], 'scenes': [],
                                     'status': 'passed', 'reason': None, 'started_at': 's', 'finished_at': 'f',
                                     'evidence_path': 'logs/ci/project-health-knowledge/runtime/drift.json'}
            result = verify(root, 'godot.exe', 10)
            self.assertEqual(result['source_revision'], 'a' * 40)
            self.assertFalse(result['tasks'][0]['runtime_verified'])
            self.assertEqual(result['tasks'][0]['status'], 'runtime_unverified')
            self.assertIn('changed', result['tasks'][0]['reason'])

    @mock.patch('project_health_runtime.prepare_snapshot', return_value={'source_revision': 'a' * 40, 'files': {}})
    @mock.patch('project_health_runtime.time.monotonic', side_effect=[0, 32])
    @mock.patch('project_health_runtime._scan_revision', return_value='a' * 40)
    @mock.patch('project_health_runtime._main_revision', return_value='a' * 40)
    def test_runtime_global_timeout_records_unverified_evidence(self, _, __, ___, ____):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rows = [{'taskmaster_id': 7, 'test_refs': ['Tests.Godot/tests/test_seven.gd']}]
            write_json(base_dir(root) / 'latest.json', {
                'revision': 'a' * 40,
                'sources': {'.taskmaster/tasks/tasks_gameplay.json': json.dumps(rows),
                            'Tests.Godot/tests/test_seven.gd': 'func test_seven(): pass'},
                'tasks': [{'task': {'id': 7}, 'godot': {'scenes': []}}],
            })
            result = verify(root, 'godot.exe', 10, global_timeout=1)
            evidence = result['tasks'][0]
            self.assertEqual(evidence['status'], 'runtime_unverified')
            self.assertIn('Global runtime verification timeout', evidence['reason'])
            self.assertTrue((root / evidence['evidence_path']).is_file())
            self.assertTrue(result['summary']['global_timeout_reached'])

    def test_source_scope_rejects_root_and_disguised_logs(self):
        from project_health_knowledge import DEFAULT_CONFIG, validate_config
        with tempfile.TemporaryDirectory() as tmp:
            for path in ('.', './logs', 'docs/../logs', 'docs//prd', './docs'):
                with self.subTest(path=path):
                    config = {**DEFAULT_CONFIG, 'source_paths': [path]}
                    with self.assertRaises(ValueError):
                        validate_config(Path(tmp), config)

    def test_exploratory_source_bundle_runs_and_cannot_handoff(self):
        analyzer = ImpactAnalyzer.from_exploratory_sources(
            {'Game.Core/A.cs': 'namespace Demo; public class A {}'}, 'directory:abc')
        result = analyzer.explore({'type': 'file', 'id': 'Game.Core/A.cs'})
        self.assertEqual(result['status'], 'exploratory')
        self.assertFalse(result['handoff_eligible'])
        with self.assertRaises(Exception):
            analyzer.analyze({'type': 'file', 'id': 'Game.Core/A.cs'})

    def test_directory_digest_tracks_content_and_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(root / 'docs/a.json', {'a': 1})
            write_json(root / 'logs/noise.json', {'a': 1})
            first = DirectorySnapshot(root, ['docs'])
            write_json(root / 'docs/a.json', {'a': 2})
            second = DirectorySnapshot(root, ['docs'])
            self.assertNotEqual(first.commit, second.commit)
            self.assertEqual(first.paths, ('docs/a.json',))
            self.assertTrue(first.commit.startswith('directory:'))

    def test_directory_snapshot_skips_oversized_sources_before_reading(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / 'docs/oversized.md'
            path.parent.mkdir(parents=True)
            with path.open('wb') as stream:
                stream.truncate(4 * 1024 * 1024 + 1)
            snapshot = DirectorySnapshot(root, ['docs'])
            self.assertNotIn('docs/oversized.md', snapshot.paths)

    def test_invalid_configuration_retains_previous_scan(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_json(base_dir(root) / 'latest.json', {'sentinel': 1})
            write_json(root / 'scripts/python/project_health_knowledge_config.json', {})
            with self.assertRaises(ValueError):
                scan(root)
            self.assertEqual(json.loads((base_dir(root) / 'latest.json').read_text()), {'sentinel': 1})
            self.assertFalse((base_dir(root) / 'scan.lock').exists())

    def test_defaults_and_forbidden_source_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(load_config(root), DEFAULT_CONFIG)
            for path in ('logs', '../secret', 'C:/secret'):
                with self.assertRaises(ValueError):
                    validate_config(root, {**DEFAULT_CONFIG, 'source_paths': [path]})

    def test_feature_recovery_documents_follow_repository_contract(self):
        import validate_recovery_docs as recovery
        root = Path(__file__).resolve().parents[3]
        documents = [
            ('execution-plans/2026-09-07-project-health-knowledge.md', recovery.EXECUTION_PLAN_FIELDS),
            ('decision-logs/2026-09-07-project-health-impact-limits.md', recovery.DECISION_LOG_FIELDS),
        ]
        for relative, fields in documents:
            with self.subTest(path=relative):
                self.assertEqual(recovery.validate_doc(root / relative, fields), [])

    def test_ssot_wins_and_views_remain_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / '.taskmaster/tasks'
            write_json(base / 'tasks.json', {'master': {'tasks': [{'id': 1, 'status': 'done', 'title': 'Primary'}]}})
            write_json(base / 'tasks_back.json', [{'id': 'NG-1', 'taskmaster_id': 1, 'status': 'pending', 'only_view': 7}])
            write_json(base / 'tasks_gameplay.json', [{'id': 'GM-1', 'taskmaster_id': '1', 'title': 'Wrong'}])
            detail = task_details(root)[0]
            self.assertEqual(detail['task']['status'], 'done')
            self.assertEqual(detail['mappings']['tasks_back'], [{'taskmaster_id': 1, 'only_view': 7}])
            self.assertNotIn('title', detail['mappings']['tasks_gameplay'][0])

    def test_pagination_exact_size_and_range(self):
        tasks = [{'task': {'id': i, 'status': 'done' if i % 2 else 'pending'},
                  'godot': {'status': 'candidate' if i % 3 else 'unmapped'}} for i in range(41)]
        self.assertEqual(len(task_page(tasks, 1)['items']), 20)
        self.assertEqual(len(task_page(tasks, 3)['items']), 1)
        done = task_page(tasks, 1, 'task_status', 'done')
        self.assertEqual(done['total'], 20)
        self.assertTrue(all(item['status'] == 'done' for item in done['items']))
        unmapped = task_page(tasks, 1, 'godot_status', 'unmapped')
        self.assertEqual(unmapped['total'], 14)
        self.assertTrue(all(item['godot']['status'] == 'unmapped' for item in unmapped['items']))
        self.assertEqual(task_page([], 1)['pages'], 1)
        with self.assertRaises(ValueError):
            task_page(tasks, 1, 'unknown', 'done')
        for page in (0, 4, -1):
            with self.assertRaises(ValueError): task_page(tasks, page)

    def test_scene_requires_real_assignment_and_witness(self):
        scene = 'Game.Godot/Scenes/Reward.tscn'
        script = 'Game.Godot/Scripts/Reward.gd'
        test = 'Tests.Godot/test_reward.gd'
        sources = {scene: '[ext_resource type="Script" path="res://' + script + '" id="1"]\n[node name="Root" type="Node"]\nscript = ExtResource("1")\n',
                   script: 'func confirm_reward():\n pass', test: 'load("res://' + scene + '")'}
        tasks = [{'task': {'id': 1, 'status': 'done', 'test_refs': [test]}, 'mappings': {}}]
        attach_task_scenes(tasks, sources, [])
        self.assertEqual(tasks[0]['godot']['status'], 'candidate')
        mapping = {'task_id': 1, 'scene': scene, 'node': '.', 'script': script, 'witness': 'func confirm_reward()'}
        attach_task_scenes(tasks, sources, [mapping])
        self.assertEqual(tasks[0]['godot']['status'], 'static_attached')
        self.assertFalse(tasks[0]['godot']['runtime_verified'])
        mapping['witness'] = 'missing'
        attach_task_scenes(tasks, sources, [mapping])
        self.assertEqual(tasks[0]['godot']['status'], 'candidate')
        self.assertEqual(len(tasks[0]['godot']['invalid_declarations']), 1)
        sources[scene] = sources[scene].split('script =')[0]
        self.assertEqual(scene_bindings(sources), [])

    def test_preview_cannot_be_formal_report(self):
        analyzer = object.__new__(ImpactAnalyzer)
        with mock.patch.object(analyzer, '_collect', return_value={'schema_version': 'newrouge.impact-analysis.v1', 'status': 'ok'}):
            preview = analyzer.explore({'type': 'file', 'id': 'a'})
            self.assertFalse(preview['handoff_eligible'])
            self.assertNotEqual(preview['schema_version'], 'newrouge.impact-analysis.v1')
        with mock.patch.object(analyzer, '_collect', return_value={}):
            with self.assertRaises(Exception): analyzer.analyze({'type': 'file', 'id': 'a'})

    def test_paths_reject_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            for path in ('../secret', '/secret', 'C:/secret', 'a\\b'):
                with self.assertRaises(ValueError): safe_file(Path(tmp), path)

    def test_exploration_records_unsupported_methods_without_relaxing_formal_mode(self):
        source = {'Game.Core/Example.cs': 'namespace Demo; public class Example { public void Method(UnknownType input) {} }'}
        with self.assertRaises(Exception): SymbolIndex(source, {})
        index = SymbolIndex(source, {}, exploratory=True)
        self.assertEqual(len(index.skipped_methods), 1)
        self.assertEqual(index.skipped_methods[0]['path'], 'Game.Core/Example.cs')
        analyzer = object.__new__(ImpactAnalyzer)
        analyzer.exploratory = True
        with self.assertRaises(Exception): analyzer.analyze({'type': 'file', 'id': 'Game.Core/Example.cs'})


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_factory(self.root))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.tmp.cleanup()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port)
        connection.request(method, path, body, headers or {})
        response = connection.getresponse()
        status, content = response.status, response.read()
        connection.close()
        return status, content

    def session_headers(self):
        _, session = self.request('GET', '/api/knowledge/session')
        return {'Origin': f'http://127.0.0.1:{self.server.server_port}',
                'Content-Type': 'application/json',
                'X-Project-Health-Token': json.loads(session)['token']}

    def test_runtime_route_requires_godot_bin(self):
        with mock.patch.dict('os.environ', {}, clear=True):
            status, data = self.request('POST', '/api/knowledge/runtime', '{}', self.session_headers())
        self.assertEqual(status, 422)
        self.assertIn('GODOT_BIN', json.loads(data)['reason'])

    @mock.patch('_project_health_http.subprocess.run')
    def test_runtime_route_forwards_task_id_and_uses_runtime_host_timeout(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps({'status': 'ok'}), '')
        with mock.patch.dict('os.environ', {'GODOT_BIN': 'C:/Godot/godot.exe'}):
            status, _ = self.request('POST', '/api/knowledge/runtime', json.dumps({'task_id': 17}),
                                     self.session_headers())
        self.assertEqual(status, 200)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index('--task-id') + 1], '17')
        self.assertEqual(run.call_args.kwargs['timeout'], 3690)

    @mock.patch('_project_health_http.subprocess.run')
    def test_runtime_route_forwards_selected_task_ids(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps({'status': 'ok'}), '')
        with mock.patch.dict('os.environ', {'GODOT_BIN': 'C:/Godot/godot.exe'}):
            status, _ = self.request('POST', '/api/knowledge/runtime',
                                     json.dumps({'task_ids': [17, '23']}), self.session_headers())
        self.assertEqual(status, 200)
        command = run.call_args.args[0]
        self.assertEqual(command[command.index('--task-ids') + 1], '17,23')

    @mock.patch('_project_health_http.subprocess.run')
    def test_runtime_route_forwards_all_gameplay_mode(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, json.dumps({'status': 'ok'}), '')
        with mock.patch.dict('os.environ', {'GODOT_BIN': 'C:/Godot/godot.exe'}):
            status, _ = self.request('POST', '/api/knowledge/runtime',
                                     json.dumps({'all_gameplay': True}), self.session_headers())
        self.assertEqual(status, 200)
        self.assertIn('--all-gameplay', run.call_args.args[0])

    @mock.patch('_project_health_http.subprocess.run')
    def test_operation_endpoint_reports_active_runtime_and_scope(self, run):
        entered, release = threading.Event(), threading.Event()
        def blocked(*args, **kwargs):
            entered.set(); release.wait(2)
            return subprocess.CompletedProcess([], 0, json.dumps({'status': 'ok'}), '')
        run.side_effect = blocked
        headers = self.session_headers()
        result = {}
        def request_runtime():
            with mock.patch.dict('os.environ', {'GODOT_BIN': 'C:/Godot/godot.exe'}):
                result['status'], _ = self.request('POST', '/api/knowledge/runtime',
                                                   json.dumps({'task_ids': [17, 23]}), headers)
        worker = threading.Thread(target=request_runtime)
        worker.start(); self.assertTrue(entered.wait(1))
        status, data = self.request('GET', '/api/knowledge/operation')
        operation = json.loads(data)
        self.assertEqual(status, 200)
        self.assertTrue(operation['active'])
        self.assertEqual(operation['action'], 'runtime')
        self.assertEqual(operation['task_ids'], ['17', '23'])
        release.set(); worker.join(2)
        self.assertEqual(result['status'], 200)
        _, data = self.request('GET', '/api/knowledge/operation')
        self.assertFalse(json.loads(data)['active'])

    def test_host_and_csrf_boundaries(self):
        self.assertEqual(self.request('GET', '/api/knowledge/session', headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.request('POST', '/api/knowledge/scan', '{}')[0], 403)
        status, data = self.request('GET', '/api/knowledge/session')
        self.assertEqual(status, 200)
        token = json.loads(data)['token']
        headers = {'Origin': f'http://127.0.0.1:{self.server.server_port}', 'Content-Type': 'application/json', 'X-Project-Health-Token': token}
        self.assertEqual(self.request('POST', '/api/knowledge/not-allowed', '{}', headers)[0], 404)

    def test_page_is_available_without_scan_and_private_paths_are_blocked(self):
        status, data = self.request('GET', '/knowledge/')
        self.assertEqual(status, 200)
        self.assertIn(b'pager-top', data)
        self.assertIn(b'pager-bottom', data)
        self.assertIn(b'runtime-selected', data)
        self.assertIn(b'operation-lock', data)
        self.assertNotEqual(self.request('GET', '/../project-health-knowledge/latest.json')[0], 200)
        self.assertNotEqual(self.request('GET', '/server.json/../../secret')[0], 200)

    def test_config_save_is_explicit_and_validated(self):
        _, session = self.request('GET', '/api/knowledge/session')
        headers = {'Origin': f'http://127.0.0.1:{self.server.server_port}', 'Content-Type': 'application/json',
                   'X-Project-Health-Token': json.loads(session)['token']}
        config = {'source_paths': ['.taskmaster/tasks'], 'gdd_paths': ['docs/gdd/设计.md'], 'task_scene_bindings': [], 'query_aliases': {}}
        self.assertEqual(self.request('POST', '/api/knowledge/config', json.dumps(config), headers)[0], 200)
        self.assertEqual(load_config(self.root), config)
        config['gdd_paths'] = ['../secret.md']
        self.assertEqual(self.request('POST', '/api/knowledge/config', json.dumps(config), headers)[0], 422)
        self.assertEqual(load_config(self.root)['gdd_paths'], ['docs/gdd/设计.md'])


    def test_config_source_bindings_preserve_empty_categories(self):
        config = {
            'source_paths': ['custom/tasks'],
            'source_path_bindings': {'tasks': 'custom/tasks', 'product_requirements': ''},
            'gdd_paths': [], 'task_scene_bindings': [], 'query_aliases': {}
        }

        validated = validate_config(self.root, config)

        self.assertEqual(validated['source_path_bindings']['product_requirements'], '')
        self.assertEqual(validated['source_paths'], ['custom/tasks'])


if __name__ == '__main__':
    unittest.main()
