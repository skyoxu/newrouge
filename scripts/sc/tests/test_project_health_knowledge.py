"""Knowledge page SSOT, evidence and HTTP boundary tests."""
import http.client
import json
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
from project_health_knowledge import safe_file, load_config, write_json
from impact_analyzer import ImpactAnalyzer, SymbolIndex
from project_health_knowledge import DEFAULT_CONFIG, scan, base_dir, validate_config
from _knowledge_catalog_builder import DirectorySnapshot


class TasksTests(unittest.TestCase):
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
        tasks = [{'task': {'id': i}, 'godot': {}} for i in range(41)]
        self.assertEqual(len(task_page(tasks, 1)['items']), 20)
        self.assertEqual(len(task_page(tasks, 3)['items']), 1)
        self.assertEqual(task_page([], 1)['pages'], 1)
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


if __name__ == '__main__':
    unittest.main()
