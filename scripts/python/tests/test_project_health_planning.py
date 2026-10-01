"""Real Git and planner consumers; model responses are explicit deterministic fixtures."""
from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/python'))
import _project_health_planning as planning
import plan_capabilities as cap
import plan_mvg as mvg
from _planning_skill_common import atomic_json, canonical_sha, load_json
from _project_health_planning_inputs import MainCheckout, git, main_revision, prepare_checkout, validate_checkout
from planning_acceptance_fixture import build_fixture, GDD_PATH
from scripts.python.tests.test_planning_audit_repair import prepared_mvg
from scripts.python.tests.test_planning_main_audit_fixes import review_report

RUNNER = {'schema_version': 'newrouge.isolated-model-runner.v1', 'model': 'deterministic-fixture',
          'filesystem_scope': 'workspace_only', 'fresh_session_per_invocation': True,
          'can_read_outside_workspace': False, 'model_tools': []}


class ProjectHealthPlanningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'repo'
        build_fixture(self.root)
        (self.root / '.gitignore').write_text('logs/\n', encoding='utf-8')
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-m', 'fixture: committed planning inputs')
        git(self.root, 'branch', '-M', 'main')
        self.revision = main_revision(self.root)

    def test_checkout_reads_latest_main_and_ignores_dirty_feature_files(self):
        original = (self.root / GDD_PATH).read_bytes()
        git(self.root, 'checkout', '-b', 'feature')
        (self.root / GDD_PATH).write_text('Uncommitted replacement', encoding='utf-8')
        (self.root / 'docs/gdd/untracked.md').write_text('Untracked source', encoding='utf-8')
        checkout = self.root / 'logs/ci/test-checkout'
        prepare_checkout(self.root, checkout, self.revision)
        self.assertEqual(original, (checkout / GDD_PATH).read_bytes())
        self.assertFalse((checkout / 'docs/gdd/untracked.md').exists())
        validate_checkout(self.root, checkout, self.revision)

    def test_evidence_hydration_accepts_relative_repository_root(self):
        checkout = self.root / 'logs/ci/test-checkout'
        with contextlib.chdir(self.temp.name):
            prepare_checkout(Path('repo'), checkout, self.revision)
            validate_checkout(Path('repo'), checkout, self.revision)
        for family in ('readiness', 'reconciliation'):
            evidence = Path(f'logs/ci/chapter5/{family}/task-7.json')
            self.assertTrue((checkout / evidence).is_file())
            self.assertEqual((self.root / evidence).read_bytes(), (checkout / evidence).read_bytes())

    def test_no_git_or_main_has_no_snapshot_fallback(self):
        with self.assertRaisesRegex(ValueError, 'committed main'):
            main_revision(Path(self.temp.name))
        git(self.root, 'branch', '-m', 'other')
        with self.assertRaisesRegex(ValueError, 'committed main'):
            planning.create_job(self.root, 'capability')

    def test_uncommitted_chapter3_semantics_are_rejected(self):
        path = self.root / 'logs/ci/task-generation/semantic-requirements.v1.json'
        doc = load_json(path); doc['requirements'][0]['statement'] = 'Uncommitted semantics'
        atomic_json(path, doc)
        with self.assertRaisesRegex(ValueError, 'committed main'):
            prepare_checkout(self.root, self.root / 'logs/ci/test-checkout', self.revision)

    def test_stale_source_manifest_is_rejected(self):
        path = self.root / 'logs/ci/task-generation/source-manifest.v1.json'
        doc = load_json(path); doc['sources'][0]['sha256'] = '0' * 64
        atomic_json(path, doc)
        with self.assertRaisesRegex(ValueError, 'stale or uncommitted'):
            prepare_checkout(self.root, self.root / 'logs/ci/test-checkout', self.revision)

    def test_missing_chapter5_blocks_before_any_model_invocation(self):
        (self.root / 'logs/ci/chapter5/readiness/task-7.json').unlink()
        job = planning.create_job(self.root, 'capability')
        with patch.object(planning, 'runner_path', return_value=Path('fixture')):
            result = planning.run_job(self.root, job)
        self.assertEqual('failed', result['status'])
        self.assertIn('Chapter 5', result['message'])
        self.assertFalse((planning.job_path(self.root, job['job_id']).parent / 'generate.log').exists())

    def test_manifest_selection_cannot_escape_committed_scope(self):
        for manifest in ('../../outside.json', 'docs/testing/mvg/unknown.json', 'x;echo bad'):
            with self.subTest(manifest=manifest), self.assertRaises(ValueError):
                planning.create_job(self.root, 'mvg', manifest)

    def test_new_main_during_execution_blocks_publication(self):
        job = planning.create_job(self.root, 'capability')
        git(self.root, 'commit', '--allow-empty', '-m', 'fixture: new main')
        result = planning.run_job(self.root, job)
        self.assertEqual('failed', result['status'])
        self.assertIn('Main changed', result['message'])
        self.assertFalse((self.root / planning.JOB_ROOT / 'capability-latest.json').exists())

    def test_unowned_checkout_edits_are_rejected(self):
        checkout = self.root / 'logs/ci/test-checkout'
        prepare_checkout(self.root, checkout, self.revision)
        (checkout / GDD_PATH).write_text('Edited after prepare', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Uncommitted input'):
            validate_checkout(self.root, checkout, self.revision)

    def _production_consumers(self):
        template_root = Path(self.temp.name) / 'template'
        build_fixture(template_root)
        _, proposal_template, _ = prepared_mvg(template_root)
        review_template = load_json(template_root / 'logs/ci/mvg-planning/repair/semantic-review.json')
        invocations = []

        def model(_runner, **kwargs):
            workspace = kwargs['workspace']
            invocations.append(str(workspace))
            index = load_json(workspace / 'analysis-input/analysis-index.json')
            if (workspace / 'candidates/A.json').exists():
                payload = review_report(workspace)
            elif (workspace / 'proposal.json').exists():
                proposal = load_json(workspace / 'proposal.json')
                payload = deepcopy(review_template)
                payload.update(analysis_identity_sha256=index['analysis_identity_sha256'], proposal_sha256=canonical_sha(proposal))
            elif (workspace / 'analysis-input/capabilities.v1.json').exists():
                payload = deepcopy(proposal_template)
                payload['analysis_identity_sha256'] = index['analysis_identity_sha256']
            else:
                reqs = load_json(workspace / 'analysis-input/semantic-requirements.v1.json')['requirements']
                blocks = load_json(workspace / 'analysis-input/source-blocks.v1.json')['blocks']
                nodes = [{'capability_id': f'TMP-CAP-{i}', 'title': f'Relay {i}', 'description': req['statement'],
                          'boundary_rationale': 'Distinct source obligation', 'requirement_ids': [req['requirement_id']],
                          'source_block_ids': req['source_block_ids']} for i, req in enumerate(reqs, 1)]
                payload = {'schema_version': cap.CANDIDATE_SCHEMA, 'analysis_identity_sha256': index['analysis_identity_sha256'],
                           'capabilities': nodes, 'ungrouped_requirements': [], 'questions': [], 'generation_notes': [],
                           'source_accounting': [{'block_id': b['block_id'], 'disposition': 'capability' if any(b['block_id'] in n['source_block_ids'] for n in nodes) else 'context',
                             'capability_ids': [n['capability_id'] for n in nodes if b['block_id'] in n['source_block_ids']],
                             'rationale': 'Source obligation or heading'} for b in blocks]}
            atomic_json(kwargs['output_path'], payload)
            return {'model': RUNNER['model'], 'model_tools': []}

        def invoke(checkout, script, args, log):
            module = cap if script == 'plan_capabilities.py' else mvg
            output = io.StringIO()
            with contextlib.redirect_stdout(output), patch.object(module, 'inspect_isolated_runner', return_value=RUNNER), \
                 patch.object(module, 'run_isolated_model', side_effect=model):
                code = module.main(['--repo-root', str(checkout), *args])
            text = output.getvalue(); log.write_text(text, encoding='utf-8')
            if code:
                raise ValueError(planning.compact_error(text))
            return json.loads(text)
        return invoke, invocations

    def test_new_untracked_input_in_checkout_is_rejected(self):
        checkout = self.root / 'logs/ci/test-checkout'
        prepare_checkout(self.root, checkout, self.revision)
        (checkout / 'docs/gdd/untracked.md').write_text('Uncommitted input', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'Uncommitted input'):
            validate_checkout(self.root, checkout, self.revision)

    def test_crlf_checkout_preserves_chapter3_text_identity(self):
        (self.root / '.gitattributes').write_text('*.md text eol=crlf\n', encoding='utf-8')
        git(self.root, 'add', '.gitattributes'); git(self.root, 'commit', '-m', 'fixture: CRLF checkouts')
        revision = main_revision(self.root)
        checkout = self.root / 'logs/ci/test-checkout'
        prepare_checkout(self.root, checkout, revision)
        self.assertIn(b'\r\n', (checkout / GDD_PATH).read_bytes())
        source = load_json(checkout / 'logs/ci/task-generation/source-manifest.v1.json')['sources'][0]
        self.assertEqual(source['sha256'], MainCheckout(checkout, revision).digest(GDD_PATH.as_posix()))

    def test_capability_then_mvg_use_actual_planner_stages_without_mutating_main(self):
        invoke, invocations = self._production_consumers()
        before = git(self.root, 'status', '--porcelain')
        with patch.object(planning, 'invoke', side_effect=invoke), \
             patch.object(planning, 'runner_path', return_value=Path('fixture')), \
             patch.dict(os.environ, {'SC_KNOWLEDGE_MVG_BACKEND': 'openai-api'}):
            cap_job = planning.create_job(self.root, 'capability')
            result = planning.run_job(self.root, cap_job)
            self.assertEqual('completed', result['status'], result)
            self.assertEqual(4, len(invocations))
            topology = planning.generated_view(self.root, 'capability')
            self.assertEqual(2, len(topology['nodes']['capabilities']))
            self.assertEqual(self.revision, topology['identity']['revision'])
            self.assertEqual('local_generated', topology['publication_state'])
            mvg_job = planning.create_job(self.root, 'mvg')
            self.assertEqual(cap_job['job_id'], mvg_job['checkout_job_id'])
            result = planning.run_job(self.root, mvg_job)
            self.assertEqual('completed', result['status'], result)
            self.assertEqual(6, len(invocations))
            overview = planning.generated_view(self.root, 'mvg')
            self.assertEqual(1, len(overview['manifests']))
            self.assertEqual('docs/testing/mvg/m1-full.json', overview['manifests'][0]['path'])
            self.assertFalse(overview['runtime_verified'])
            self.assertIsNotNone(planning.generated_view(self.root, 'capability'))
            (self.root / GDD_PATH).write_text('Dirty source must not appear in preview', encoding='utf-8')
            preview = planning.planning_source(self.root, cap_job['job_id'], GDD_PATH.as_posix())
            self.assertNotIn('Dirty source', preview['content'])
            self.assertEqual(self.revision, preview['revision'])
            git(self.root, 'restore', GDD_PATH.as_posix())
            with self.assertRaisesRegex(ValueError, 'not in the generated topology'):
                planning.planning_source(self.root, cap_job['job_id'], '.git/config')
            self.assertEqual(before, git(self.root, 'status', '--porcelain'))
            self.assertFalse((self.root / cap.FORMAL_CAPABILITIES).exists())
            self.assertFalse((self.root / mvg_job['manifest']).exists())
            reused = planning.create_job(self.root, 'capability')
            self.assertEqual('completed', reused['status'])
            self.assertEqual(cap_job['job_id'], reused['job_id'])
            self.assertEqual(6, len(invocations))
        git(self.root, 'commit', '--allow-empty', '-m', 'fixture: later main')
        self.assertIsNone(planning.generated_view(self.root, 'capability'))
        self.assertIsNone(planning.generated_view(self.root, 'mvg'))

    def test_mvg_consumes_capabilities_already_committed_in_main(self):
        prepared_mvg(self.root)
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-m', 'fixture: existing reviewed capabilities')
        invoke, invocations = self._production_consumers()
        with patch.object(planning, 'invoke', side_effect=invoke), \
             patch.object(planning, 'runner_path', return_value=Path('fixture')), \
             patch.dict(os.environ, {'SC_KNOWLEDGE_MVG_BACKEND': 'openai-api'}):
            job = planning.create_job(self.root, 'mvg')
            self.assertNotIn('checkout_job_id', job)
            result = planning.run_job(self.root, job)
        self.assertEqual('completed', result['status'], result)
        self.assertEqual(2, len(invocations))
        self.assertEqual(main_revision(self.root), planning.generated_view(self.root, 'mvg')['revision'])

    def test_resume_reuses_generated_candidates_and_original_attempt(self):
        invoke, invocations = self._production_consumers()
        interrupted = False

        def disconnect(checkout, script, args, log):
            nonlocal interrupted
            result = invoke(checkout, script, args, log)
            if args[0] == 'generate' and not interrupted:
                interrupted = True
                raise ValueError('Fixture interruption after persisted generation')
            return result

        with patch.object(planning, 'invoke', side_effect=disconnect), \
             patch.object(planning, 'runner_path', return_value=Path('fixture')):
            job = planning.create_job(self.root, 'capability')
            self.assertEqual('failed', planning.run_job(self.root, job)['status'])
            self.assertEqual(3, len(invocations))
            resumed = planning.create_job(self.root, 'capability')
            self.assertEqual(job['job_id'], resumed['job_id'])
            result = planning.run_job(self.root, resumed)
        self.assertEqual('completed', result['status'], result)
        self.assertEqual(4, len(invocations))

    def test_error_is_compact_and_same_attempt_is_retained(self):
        job = planning.create_job(self.root, 'capability')
        with patch.object(planning, 'runner_path', side_effect=ValueError('Useful reason\n' + 'x' * 2000)):
            result = planning.run_job(self.root, job)
        self.assertLessEqual(len(result['message']), 370)
        self.assertEqual(job['job_id'], planning.create_job(self.root, 'capability')['job_id'])

    def test_api_backend_follows_configured_credentials(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'fixture-only'}, clear=True):
            self.assertEqual('openai-api', planning.mvg_backend())
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual('copilot-cli', planning.mvg_backend())
        with patch.dict(os.environ, {'SC_KNOWLEDGE_MVG_BACKEND': 'shell'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'Unsupported'):
                planning.mvg_backend()

    def test_failed_cli_json_reports_only_the_specific_reason(self):
        self.assertEqual('Readiness expired', planning.compact_error('{"status":"blocked","reason":"Readiness expired"}'))


if __name__ == '__main__':
    unittest.main()
