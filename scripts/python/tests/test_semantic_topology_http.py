from __future__ import annotations

import http.client
import json
import sys
import tempfile
import threading
import unittest
from unittest import mock
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/python"))

from _project_health_http import handler_factory, run_mvg_manifest
from project_health_knowledge import base_dir, write_json


class SemanticTopologyHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(self.root))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def request(self, path: str) -> tuple[int, bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        connection.request("GET", path)
        response = connection.getresponse()
        status, body = response.status, response.read()
        connection.close()
        return status, body

    def post(self, path: str, body: dict, authenticated: bool = True) -> tuple[int, bytes]:
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        headers = {'Content-Type': 'application/json'}
        if authenticated:
            _, session = self.request('/api/knowledge/session')
            headers.update({'Origin': f'http://127.0.0.1:{self.server.server_port}',
                            'X-Project-Health-Token': json.loads(session)['token']})
        connection.request('POST', path, json.dumps(body), headers)
        response = connection.getresponse()
        status, payload = response.status, response.read()
        connection.close()
        return status, payload

    def test_mvg_run_route_is_authenticated_and_uses_selected_manifest(self):
        status, _ = self.post('/api/knowledge/mvg-run', {}, authenticated=False)
        self.assertEqual(403, status)
        with mock.patch('_project_health_http.run_mvg_manifest', return_value=(200, {'status': 'passed'})) as run:
            with mock.patch.dict('os.environ', {'GODOT_BIN': 'C:/Godot/godot.exe'}):
                status, body = self.post('/api/knowledge/mvg-run', {'revision': 'a' * 40,
                    'manifest': 'docs/testing/mvg/reward-pilot.json'})
        self.assertEqual(200, status)
        self.assertEqual('passed', json.loads(body)['status'])
        run.assert_called_once_with(self.root, 'a' * 40, 'C:/Godot/godot.exe', 'docs/testing/mvg/reward-pilot.json')

    def test_mvg_runner_rejects_stale_revision_before_execution(self):
        with mock.patch('_project_health_http.subprocess.run') as run:
            run.return_value = mock.Mock(returncode=0, stdout='b' * 40 + '\n', stderr='')
            with self.assertRaisesRegex(ValueError, 'revision'):
                run_mvg_manifest(self.root, 'a' * 40, 'C:/Godot/godot.exe', 'docs/testing/mvg/reward-pilot.json')
        self.assertEqual(1, run.call_count)

    def test_mvg_runner_uses_selected_manifest_in_commit_command(self):
        revision = 'a' * 40
        write_json(base_dir(self.root) / 'latest.json', {'revision': revision,
            'mvg_overview': {'revision': revision, 'manifests': [
                {'path': 'docs/testing/mvg/reward-pilot.json', 'tests': [{'challenge': 'disconnect-reward-input'}]}]}})
        def execute(command, **kwargs):
            if command[:1] == ['git']:
                output = '' if command[-2:] == ['status', '--porcelain'] else revision + '\n'
                return mock.Mock(returncode=0, stdout=output, stderr='')
            return mock.Mock(returncode=0, stdout=json.dumps({'status': 'passed', 'summary': 'logs/ci/mvg-acceptance/run/summary.json'}), stderr='')
        with mock.patch('_project_health_http.subprocess.run', side_effect=execute) as run:
            code, payload = run_mvg_manifest(self.root, revision, 'C:/Godot/godot.exe',
                                             'docs/testing/mvg/reward-pilot.json')
        self.assertEqual(200, code)
        self.assertEqual('passed', payload['status'])
        command = run.call_args.args[0]
        self.assertIn('run-mvg-acceptance', command)
        self.assertEqual('docs/testing/mvg/reward-pilot.json', command[command.index('--manifest') + 1])
        self.assertEqual('run', command[command.index('--mode') + 1])
        self.assertEqual('commit', command[command.index('--snapshot') + 1])
        self.assertEqual('HEAD', command[command.index('--revision') + 1])
        self.assertEqual('C:/Godot/godot.exe', command[command.index('--godot-bin') + 1])
        self.assertIn('--challenge-input', command)

    def test_mvg_runner_rejects_manifest_outside_scanned_main_scope(self):
        revision = 'a' * 40
        write_json(base_dir(self.root) / 'latest.json', {'revision': revision,
            'mvg_overview': {'revision': revision, 'manifests': [
                {'path': 'docs/testing/mvg/m1-critical.json', 'tests': []}]}})
        with mock.patch('_project_health_http.subprocess.run') as run:
            run.return_value = mock.Mock(returncode=0, stdout=revision + '\n', stderr='')
            with self.assertRaisesRegex(ValueError, 'manifest'):
                run_mvg_manifest(self.root, revision, 'C:/Godot/godot.exe',
                                 'docs/testing/mvg/reward-pilot.json')

    def test_topology_page_is_available_without_generated_topology(self):
        status, body = self.request("/knowledge/topology")
        self.assertEqual(200, status)
        self.assertIn(b"Design", body)
        status, body = self.request("/api/knowledge/topology?mode=main")
        self.assertEqual(200, status)
        payload = json.loads(body)
        self.assertFalse(payload["available"])
        self.assertEqual("legacy_unmapped", payload["status"])
        self.assertEqual("main", payload["identity"]["kind"])

    def test_mvg_view_requires_matching_scan_and_serves_main_snapshot_only(self):
        status, body = self.request('/api/knowledge/mvg-overview')
        self.assertEqual(409, status)
        write_json(base_dir(self.root) / 'latest.json', {
            'revision': 'a' * 40, 'mvg_overview': {'revision': 'b' * 40, 'versions': [], 'manifests': []},
        })
        status, body = self.request('/api/knowledge/mvg-overview')
        self.assertEqual(409, status)
        write_json(base_dir(self.root) / 'latest.json', {
            'revision': 'a' * 40, 'mvg_overview': {'revision': 'a' * 40, 'versions': [], 'manifests': []},
        })
        status, body = self.request('/api/knowledge/mvg-overview')
        self.assertEqual(200, status)
        self.assertEqual('a' * 40, json.loads(body)['revision'])
        status, body = self.request('/knowledge/scenes')
        self.assertEqual(200, status)
        self.assertIn(b'mvg-version-select', body)

    def test_workspace_stabilized_view_is_addressable(self):
        write_json(base_dir(self.root) / "topology/workspace-latest-stabilized.json", {
            "schema_version": "newrouge.semantic-topology-view.v1",
            "available": True,
            "fresh": True,
            "identity": {"kind": "workspace", "revision": "workspace:chapter5", "trigger_run_id": "ch5"},
            "status": "fresh",
            "nodes": {"source_blocks": [], "requirements": [], "capabilities": [], "tasks": [], "acceptance": []},
            "edges": [], "task_trace": {}, "summary": {}, "problems": [],
        })
        status, body = self.request("/api/knowledge/topology?mode=workspace&view=stabilized")
        self.assertEqual(200, status)
        payload = json.loads(body)
        self.assertEqual("stabilized", payload["workspace_view"])
        self.assertEqual("ch5", payload["identity"]["trigger_run_id"])

    def test_workspace_preview_is_separate_from_main(self):
        write_json(base_dir(self.root) / "topology/workspace-latest.json", {
            "schema_version": "newrouge.semantic-topology-view.v1",
            "available": True,
            "fresh": True,
            "identity": {"kind": "workspace", "revision": "workspace:test"},
            "status": "fresh",
            "nodes": {
                "source_blocks": [], "requirements": [], "capabilities": [],
                "tasks": [], "acceptance": [],
            },
            "edges": [],
            "task_trace": {},
            "summary": {},
            "problems": [],
        })
        status, body = self.request("/api/knowledge/topology?mode=workspace")
        self.assertEqual(200, status)
        workspace = json.loads(body)
        self.assertEqual("workspace", workspace["identity"]["kind"])
        self.assertEqual("workspace:test", workspace["identity"]["revision"])

        status, body = self.request("/api/knowledge/topology?mode=main")
        self.assertEqual(200, status)
        main = json.loads(body)
        self.assertEqual("main", main["identity"]["kind"])
        self.assertNotEqual(workspace["identity"], main["identity"])


if __name__ == "__main__":
    unittest.main()
