"""Authenticated HTTP jobs, concurrency and generated-data publication boundaries."""
from __future__ import annotations

import http.client
import json
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/python'))
import _project_health_planning as planning
from _planning_skill_common import atomic_json
from _project_health_http import handler_factory, run_mvg_manifest
from _project_health_planning_inputs import git, main_revision
from planning_acceptance_fixture import build_fixture
from project_health_knowledge import base_dir, write_json


class ProjectHealthPlanningHttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'repo'
        build_fixture(self.root)
        (self.root / '.gitignore').write_text('logs/\n', encoding='utf-8')
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-m', 'fixture: committed inputs')
        git(self.root, 'branch', '-M', 'main')
        self.revision = main_revision(self.root)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_factory(self.root))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.temp.cleanup()

    def request(self, path, body=None, authenticated=True):
        headers = {}
        if body is not None:
            headers['Content-Type'] = 'application/json'
            if authenticated:
                _, session = self.request('/api/knowledge/session')
                headers.update(Origin=f'http://127.0.0.1:{self.server.server_port}',
                               **{'X-Project-Health-Token': session['token']})
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        connection.request('POST' if body is not None else 'GET', path,
                           json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse()
        code, raw = response.status, response.read()
        connection.close()
        return code, json.loads(raw)

    def test_post_requires_session_and_fixed_request_fields(self):
        with patch('_project_health_planning_http.run_job') as worker:
            self.assertEqual(403, self.request('/api/knowledge/planning', {'action': 'capability'}, False)[0])
            self.assertEqual(422, self.request('/api/knowledge/planning', {'action': 'capability', 'revision': 'HEAD'})[0])
            self.assertEqual(422, self.request('/api/knowledge/planning', {'action': 'arbitrary-command'})[0])
        worker.assert_not_called()
        self.assertEqual(422, self.request('/api/knowledge/planning?job_id=../../outside')[0])
        self.assertFalse(self.request('/api/knowledge/operation')[1]['active'])

    def test_async_job_locks_other_actions_and_polls_compact_failure(self):
        started, release, finished = threading.Event(), threading.Event(), threading.Event()

        def execute(root, job):
            started.set()
            release.wait(5)
            job.update(status='failed', message='Capability failed (prepare): Chapter 5 readiness is missing')
            atomic_json(planning.job_path(root, job['job_id']), job)
            finished.set()

        try:
            with patch('_project_health_planning_http.run_job', side_effect=execute) as worker:
                code, result = self.request('/api/knowledge/planning', {'action': 'capability'})
                self.assertEqual(202, code)
                self.assertTrue(started.wait(2))
                operation = self.request('/api/knowledge/operation')[1]
                self.assertTrue(operation['active'])
                self.assertEqual(result['job_id'], operation['planning_job_id'])
                self.assertEqual(409, self.request('/api/knowledge/planning', {'action': 'mvg'})[0])
                self.assertEqual(409, self.request('/api/knowledge/scan', {})[0])
                self.assertEqual(409, self.request('/api/knowledge/mvg-clear', {})[0])
                self.assertEqual(200, self.request('/api/knowledge/mvg-progress')[0])
                self.assertEqual(200, self.request('/api/knowledge/planning?job_id=' + result['job_id'])[0])
                release.set(); self.assertTrue(finished.wait(2))
                code, result = self.request('/api/knowledge/planning?job_id=' + result['job_id'])
                self.assertEqual('failed', result['status'])
                self.assertIn('Chapter 5 readiness', result['message'])
                self.assertNotIn('checkout', result)
                worker.assert_called_once()
        finally:
            release.set()

    def test_completed_click_starts_new_worker(self):
        job = planning.create_job(self.root, 'capability')
        job.update(status='completed', stage='complete', count=2, message='Capability generated: 2 capabilities')
        atomic_json(planning.job_path(self.root, job['job_id']), job)
        with patch('_project_health_planning_http.generated_view', return_value={'available': True}) as view, \
             patch('_project_health_planning_http.run_job') as worker:
            code, payload = self.request('/api/knowledge/planning', {'action': 'capability'})
        self.assertEqual(202, code)
        self.assertNotEqual(job['job_id'], payload['job_id'])
        view.assert_not_called()
        worker.assert_called_once()

    def test_clear_is_authenticated_persistent_and_does_not_remove_audit_or_baseline(self):
        from _mvg_capability_recovery import registry, bind_epoch, assert_epoch
        state = {'run_id': 'old'}
        bind_epoch(self.root, state)
        audit = self.root / 'logs/ci/mvg-planning/old/audit.json'
        atomic_json(audit, {'charges': 9})
        baseline = self.root / 'docs/testing/mvg/formal.json'
        atomic_json(baseline, {'formal': True})
        self.assertEqual(403, self.request('/api/knowledge/mvg-clear', {}, False)[0])
        self.assertEqual(422, self.request('/api/knowledge/mvg-clear', {'run_id': 'old'})[0])
        self.assertEqual(0, registry(self.root)['epoch'])
        code, result = self.request('/api/knowledge/mvg-clear', {})
        self.assertEqual(200, code)
        self.assertEqual(1, result['epoch'])
        self.assertEqual(0, result['completed'])
        self.assertEqual(1, registry(self.root)['epoch'])
        self.assertEqual(0, self.request('/api/knowledge/mvg-progress')[1]['completed'])
        self.assertTrue(audit.is_file())
        self.assertTrue(baseline.is_file())
        with self.assertRaisesRegex(ValueError, 'epoch_invalidated'):
            assert_epoch(self.root, state)

    def test_each_click_is_fresh_even_with_identical_inputs(self):
        finished = threading.Event()

        def execute(root, job):
            job.update(status='completed', stage='complete')
            atomic_json(planning.job_path(root, job['job_id']), job)
            finished.set()

        with patch('_project_health_planning_http.run_job', side_effect=execute):
            for action in ('capability', 'mvg'):
                identifiers = []
                for _ in range(2):
                    finished.clear()
                    code, result = self.request('/api/knowledge/planning', {'action': action})
                    self.assertEqual(202, code)
                    self.assertTrue(finished.wait(2))
                    identifiers.append(result['job_id'])
                    self.assertEqual(self.revision, result['revision'])
                self.assertNotEqual(*identifiers)

    def test_recoverable_alignment_result_is_reported_without_losing_the_job(self):
        job = planning.create_job(self.root, 'capability')
        job.update(status='recoverable', stage='align', recoverable_stage='align',
                   message='Capability alignment needs retry: fixture rejection')
        atomic_json(planning.job_path(self.root, job['job_id']), job)
        code, payload = self.request('/api/knowledge/planning?job_id=' + job['job_id'])
        self.assertEqual(200, code)
        self.assertEqual('recoverable', payload['status'])
        self.assertEqual('align', payload['recoverable_stage'])
        self.assertIn('retry', payload['message'])

    def test_active_planning_job_can_be_cancelled_without_releasing_operation_lock(self):
        started, release = threading.Event(), threading.Event()

        def execute(root, job):
            started.set()
            release.wait(5)

        try:
            with patch('_project_health_planning_http.run_job', side_effect=execute):
                code, created = self.request('/api/knowledge/planning', {'action': 'capability'})
                self.assertEqual(202, code)
                self.assertTrue(started.wait(2))
                code, cancelled = self.request('/api/knowledge/planning-cancel', {'job_id': created['job_id']})
                self.assertEqual(202, code)
                self.assertEqual('cancelling', cancelled['status'])
                self.assertTrue(cancelled['cancel_requested'])
                self.assertTrue(self.request('/api/knowledge/operation')[1]['active'])
                self.assertEqual(409, self.request('/api/knowledge/planning', {'action': 'mvg'})[0])
        finally:
            release.set()

    def test_cancel_rejects_completed_or_unknown_jobs(self):
        self.assertEqual(422, self.request('/api/knowledge/planning-cancel', {'job_id': 'planning-' + 'f' * 32})[0])
        job = planning.create_job(self.root, 'capability')
        job.update(status='completed', stage='complete')
        atomic_json(planning.job_path(self.root, job['job_id']), job)
        self.assertEqual(422, self.request('/api/knowledge/planning-cancel', {'job_id': job['job_id']})[0])

    def test_generated_views_refresh_while_same_revision_gdd_navigation_is_retained(self):
        old_version = {'id': 'existing-version'}
        write_json(base_dir(self.root) / 'latest.json', {'revision': self.revision,
            'semantic_topology': {'status': 'old'},
            'mvg_overview': {'revision': self.revision, 'versions': [old_version], 'manifests': []}})
        topology = {'available': True, 'status': 'generated_from_main', 'nodes': {'capabilities': [{'capability_id': 'CAP-NEW'}]}}
        overview = {'revision': self.revision, 'planning_result': True, 'versions': [], 'manifests': []}
        with patch('_project_health_http.generated_view', side_effect=lambda root, action: topology if action == 'capability' else overview):
            self.assertEqual('CAP-NEW', self.request('/api/knowledge/topology')[1]['nodes']['capabilities'][0]['capability_id'])
            payload = self.request('/api/knowledge/mvg-overview')[1]
            self.assertEqual([old_version], payload['versions'])
            self.assertTrue(payload['planning_result'])

    def test_failure_keeps_previous_scanned_data_and_runtime_cannot_run_generated_scope(self):
        write_json(base_dir(self.root) / 'latest.json', {'revision': self.revision,
            'semantic_topology': {'status': 'previous-success', 'nodes': {'capabilities': [{'capability_id': 'CAP-OLD'}]}}})
        self.assertEqual('previous-success', self.request('/api/knowledge/topology')[1]['status'])
        with patch('_project_health_http.selected_result', return_value={'manifest': 'docs/testing/mvg/m1-full.json'}):
            with self.assertRaisesRegex(ValueError, 'Commit the generated'):
                run_mvg_manifest(self.root, self.revision, 'fixture.exe', 'docs/testing/mvg/m1-full.json')


if __name__ == '__main__':
    unittest.main()
