"""Real Git and planner consumers; model responses are explicit deterministic fixtures."""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
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
        (self.root / '.gitignore').write_text('logs/\n.serena/\n', encoding='utf-8')
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-m', 'fixture: committed planning inputs')
        git(self.root, 'branch', '-M', 'main')
        self.revision = main_revision(self.root)

    def _write_admitted_mvg_candidate(self, run_dir, workspace, label='candidate-1'):
        from plan_mvg import PROPOSAL_SCHEMA

        candidate_root = run_dir / workspace
        candidate_root.mkdir(parents=True, exist_ok=True)
        proposal = {'schema_version': PROPOSAL_SCHEMA,
                    'analysis_identity_sha256': 'sha256:current',
                    'manifest_candidate': {'flows': []}}
        candidate = candidate_root / 'proposal.json'
        atomic_json(candidate, proposal)
        analysis = run_dir / 'analysis-input/semantic-requirements.v1.json'
        atomic_json(analysis, {'requirements': []})
        proof_payload = {'schema_version': 'newrouge.mvg-semantic-review.v1',
            'analysis_identity_sha256': 'sha256:current', 'proposal_sha256': canonical_sha(proposal),
            'verdict': 'approved', 'findings': [], 'requirement_reviews': [], 'flow_reviews': []}
        proof = candidate_root / 'admission-review.json'
        atomic_json(proof, proof_payload)
        execution = candidate_root / 'admission-execution.json'
        atomic_json(execution, {'analysis_identity_sha256': 'sha256:current',
            'proposal_sha256': canonical_sha(proposal), 'semantic_review_sha256': canonical_sha(proof_payload),
            'runner_info': RUNNER, 'receipt': {'model': RUNNER['model'], 'model_tools': []}})
        return proposal, candidate, proof, execution

    def test_checkout_reads_latest_main_and_ignores_dirty_feature_files(self):
        git(self.root, 'config', 'core.autocrlf', 'true')
        original = (self.root / GDD_PATH).read_text(encoding='utf-8')
        git(self.root, 'checkout', '-b', 'feature')
        (self.root / GDD_PATH).write_text('Uncommitted replacement', encoding='utf-8')
        (self.root / 'docs/gdd/untracked.md').write_text('Untracked source', encoding='utf-8')
        checkout = self.root / 'logs/ci/test-checkout'
        prepare_checkout(self.root, checkout, self.revision)
        self.assertEqual(original, (checkout / GDD_PATH).read_text(encoding='utf-8'))
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

    def test_evidence_hydration_accepts_logical_source_manifest_hash(self):
        topology_path = self.root / 'docs/planning/semantic-topology/topology-manifest.v1.json'
        topology = load_json(topology_path)
        source_manifest = load_json(self.root / 'logs/ci/task-generation/source-manifest.v1.json')
        topology['source_manifest_sha256'] = source_manifest['manifest_sha256']
        atomic_json(topology_path, topology)
        git(self.root, 'add', topology_path.as_posix())
        git(self.root, 'commit', '-m', 'fixture: bind topology to logical source manifest')
        self.revision = main_revision(self.root)

        prepare_checkout(self.root, self.root / 'logs/ci/logical-hash-checkout', self.revision)

    def test_mismatched_existing_checkout_is_rebuilt_for_selected_revision(self):
        checkout = self.root / 'logs/ci/test-checkout'
        prepare_checkout(self.root, checkout, self.revision)
        git(self.root, 'commit', '--allow-empty', '-m', 'fixture: checkout revision advance')
        revision = main_revision(self.root)
        prepare_checkout(self.root, checkout, revision)
        self.assertEqual(revision, git(checkout, 'rev-parse', 'HEAD'))
        validate_checkout(self.root, checkout, revision)

    def test_no_git_has_no_snapshot_fallback_but_branch_name_is_irrelevant(self):
        with self.assertRaisesRegex(ValueError, 'committed main'):
            main_revision(Path(self.temp.name))
        git(self.root, 'branch', '-m', 'other')
        job = planning.create_job(self.root, 'capability')
        self.assertEqual('queued', job['status'])

    def test_uncommitted_chapter3_semantics_are_rejected(self):
        path = self.root / 'logs/ci/task-generation/semantic-requirements.v1.json'
        doc = load_json(path); doc['requirements'][0]['statement'] = 'Uncommitted semantics'
        atomic_json(path, doc)
        with self.assertRaisesRegex(ValueError, 'local authoritative inputs'):
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

    def test_mvg_attempt_is_not_reused_after_selected_capability_changes(self):
        old_capability = 'planning-' + 'a' * 32
        current_capability = 'planning-' + 'b' * 32
        prior = {
            'schema_version': 'newrouge.knowledge-planning-job.v1',
            'job_id': 'planning-' + 'c' * 32,
            'action': 'mvg', 'revision': self.revision,
            'manifest': 'docs/testing/mvg/m1-full.json',
            'checkout_job_id': old_capability,
            'capabilities_sha256': 'sha256:old',
            'stage': 'review', 'status': 'recoverable',
        }
        atomic_json(planning.job_path(self.root, prior['job_id']), prior)
        atomic_json(self.root / planning.JOB_ROOT / 'mvg-attempt.json', {'job_id': prior['job_id']})
        selected = {
            'job_id': current_capability,
            'output_hashes': {
                'docs/planning/semantic-topology/capabilities.v1.json': 'sha256:current',
            },
        }
        with patch.object(planning, 'selected_result', return_value=selected):
            job = planning.create_job(self.root, 'mvg')
        self.assertNotEqual(prior['job_id'], job['job_id'])
        self.assertEqual(current_capability, job['checkout_job_id'])
        self.assertEqual('sha256:current', job['capabilities_sha256'])

    def test_mvg_recovery_reuses_only_hash_bound_formal_candidates(self):
        run_dir = self.root / 'logs/ci/mvg-planning/recovery'
        _proposal, candidate, proof, execution = self._write_admitted_mvg_candidate(
            run_dir, 'candidates/candidate-1')
        state = {'analysis_identity_sha256': 'sha256:current', 'candidate_attempts': {'candidate-1': {
            'status': 'valid', 'proposal_sha256': planning.file_sha(candidate),
            'validation': {'status': 'passed', 'formal_applicable': True},
        }}, 'candidate_admissions': {'candidate-1': {
            'status': 'admitted', 'workspace': 'candidates/candidate-1',
            'review_path': proof.relative_to(self.root).as_posix(),
            'review_execution_path': execution.relative_to(self.root).as_posix(),
            'proof_sha256': planning.file_sha(proof),
            'execution_sha256': planning.file_sha(execution),
        }}}
        self.assertEqual(['candidate-1'], planning._mvg_valid_candidates(run_dir, state))
        candidate.write_text('{"analysis_identity_sha256":"sha256:changed"}', encoding='utf-8')
        self.assertEqual([], planning._mvg_valid_candidates(run_dir, state))

    def test_mvg_recovery_rejects_envelope_drift_before_candidate_reuse(self):
        run_dir = self.root / 'logs/ci/mvg-planning/envelope-recovery'
        _proposal, candidate, proof, execution = self._write_admitted_mvg_candidate(
            run_dir, 'candidates/candidate-1')
        atomic_json(run_dir / 'analysis-input/analysis-index.json', {
            'input_envelope': {'schema_version': 'newrouge.mvg-input-envelope.v1'},
        })
        state = {'run_id': 'envelope-recovery', 'analysis_identity_sha256': 'sha256:current',
            'candidate_attempts': {'candidate-1': {
                'status': 'valid', 'proposal_sha256': planning.file_sha(candidate),
                'validation': {'status': 'passed', 'formal_applicable': True},
            }}, 'candidate_admissions': {'candidate-1': {
                'status': 'admitted', 'workspace': 'candidates/candidate-1',
                'review_path': proof.relative_to(self.root).as_posix(),
                'review_execution_path': execution.relative_to(self.root).as_posix(),
                'proof_sha256': planning.file_sha(proof),
                'execution_sha256': planning.file_sha(execution),
            }}}
        with patch('_mvg_input_envelope.validate_envelope', side_effect=ValueError('drift')):
            self.assertEqual([], planning._mvg_valid_candidates(run_dir, state))

    def test_mvg_recovery_missing_envelope_does_not_fallback_to_legacy(self):
        run_dir = self.root / 'logs/ci/mvg-planning/missing-envelope'
        _proposal, candidate, proof, execution = self._write_admitted_mvg_candidate(
            run_dir, 'candidates/candidate-1')
        analysis = run_dir / 'analysis-input'
        atomic_json(analysis / 'analysis-index.json', {
            'files': {},
            'authority_inputs': {},
        })
        state = {'run_id': 'missing-envelope', 'input_envelope_sha256': 'sha256:frozen',
            'analysis_identity_sha256': 'sha256:current', 'candidate_attempts': {'candidate-1': {
                'status': 'valid', 'proposal_sha256': planning.file_sha(candidate),
                'validation': {'status': 'passed', 'formal_applicable': True},
            }}, 'candidate_admissions': {'candidate-1': {
                'status': 'admitted', 'workspace': 'candidates/candidate-1',
                'review_path': proof.relative_to(self.root).as_posix(),
                'review_execution_path': execution.relative_to(self.root).as_posix(),
                'proof_sha256': planning.file_sha(proof),
                'execution_sha256': planning.file_sha(execution),
            }}}
        with patch('_mvg_input_envelope.validate_envelope', side_effect=ValueError('input envelope missing')) as validator:
            self.assertEqual([], planning._mvg_valid_candidates(run_dir, state))
        validator.assert_called_once()

    def test_mvg_recovery_null_envelope_hash_does_not_fallback(self):
        run_dir = self.root / 'logs/ci/mvg-planning/schema-only-envelope'
        analysis = run_dir / 'analysis-input'
        analysis.mkdir(parents=True)
        atomic_json(analysis / 'analysis-index.json', {'files': {}, 'authority_inputs': {}})
        state = {'schema_version': mvg.RUN_SCHEMA, 'input_envelope_sha256': None,
                 'run_id': 'schema-only-envelope',
                 'candidate_attempts': {}, 'candidate_admissions': {}}
        with patch('_mvg_input_envelope.validate_envelope', side_effect=ValueError('input envelope missing')) as validator:
            self.assertEqual([], planning._mvg_valid_candidates(run_dir, state))
        validator.assert_called_once()

    def test_mvg_recovery_reads_nested_candidate_proposals(self):
        run_dir = self.root / 'logs/ci/mvg-planning/nested-recovery'
        _proposal, candidate, proof, execution = self._write_admitted_mvg_candidate(
            run_dir, 'candidates/candidate-1')
        state = {'schema_version': mvg.RUN_SCHEMA,
            'analysis_identity_sha256': 'sha256:current', 'candidate_attempts': {'candidate-1': {
            'status': 'valid', 'proposal_sha256': planning.file_sha(candidate),
            'validation': {'status': 'passed', 'formal_applicable': True},
        }}, 'candidate_admissions': {'candidate-1': {
            'status': 'admitted', 'workspace': 'candidates/candidate-1',
            'review_path': proof.relative_to(self.root).as_posix(),
            'review_execution_path': execution.relative_to(self.root).as_posix(),
            'proof_sha256': planning.file_sha(proof),
            'execution_sha256': planning.file_sha(execution),
        }}}
        self.assertEqual(['candidate-1'], planning._mvg_valid_candidates(run_dir, state))
        atomic_json(run_dir / 'run.json', state)
        with patch('_mvg_input_envelope.validate_envelope') as validator:
            self.assertEqual(['candidate-1'], planning._mvg_valid_candidates(
                run_dir, {'analysis_identity_sha256': 'sha256:stale', 'candidate_attempts': {}}))
        validator.assert_not_called()
        state['input_envelope_sha256'] = 'sha256:envelope'
        atomic_json(run_dir / 'run.json', state)
        (candidate.parent / 'analysis-input').mkdir()
        with patch('_mvg_input_envelope.validate_envelope') as validator:
            self.assertEqual(['candidate-1'], planning._mvg_valid_candidates(
                run_dir, {'analysis_identity_sha256': 'sha256:stale', 'candidate_attempts': {}}))
        self.assertEqual(2, validator.call_count)
        for call in validator.call_args_list:
            self.assertEqual(state, call.args[2])
        state['candidate_admissions']['candidate-1']['status'] = 'retired'
        atomic_json(run_dir / 'run.json', state)
        self.assertEqual([], planning._mvg_valid_candidates(run_dir, {'candidate_attempts': {}}))

    def test_mvg_envelope_validation_does_not_replace_current_source_freshness(self):
        run_dir = self.root / 'logs/ci/mvg-planning/source-freshness'
        job = {'job_id': 'source-freshness', 'action': 'mvg'}
        index = {'input_envelope': {},
                 'authority_inputs': {GDD_PATH.as_posix(): planning.normalized_file_sha(self.root / GDD_PATH)}}
        atomic_json(run_dir / 'analysis-input/analysis-index.json', index)
        atomic_json(run_dir / 'run.json', {'input_envelope_sha256': 'sha256:envelope'})
        with patch.object(planning, 'execution_root', return_value=self.root), \
             patch('_mvg_input_envelope.validate_envelope'):
            self.assertTrue(planning._planning_input_fresh(self.root, job))
            (self.root / GDD_PATH).write_text('Changed local source', encoding='utf-8')
            self.assertFalse(planning._planning_input_fresh(self.root, job))
            index['authority_inputs'] = {}
            atomic_json(run_dir / 'analysis-input/analysis-index.json', index)
            self.assertFalse(planning._planning_input_fresh(self.root, job))

    def test_mvg_recovery_reads_admitted_replacement_workspace(self):
        run_dir = self.root / 'logs/ci/mvg-planning/replacement-recovery'
        _proposal, candidate, proof, execution = self._write_admitted_mvg_candidate(
            run_dir, 'candidates/candidate-1--candidate-1-r2')
        state = {'analysis_identity_sha256': 'sha256:current',
            'candidate_attempts': {'candidate-1': {
                'status': 'valid', 'proposal_sha256': planning.file_sha(candidate),
                'validation': {'status': 'passed', 'formal_applicable': True},
            }},
            'candidate_admissions': {'candidate-1': {
                'status': 'admitted', 'workspace': 'candidates/candidate-1--candidate-1-r2',
                'review_path': proof.relative_to(self.root).as_posix(),
                'review_execution_path': execution.relative_to(self.root).as_posix(),
                'proof_sha256': planning.file_sha(proof),
                'execution_sha256': planning.file_sha(execution),
            }}}
        self.assertEqual(['candidate-1'], planning._mvg_valid_candidates(run_dir, state))

    def test_mvg_recovery_does_not_fallback_to_retired_workspace(self):
        run_dir = self.root / 'logs/ci/mvg-planning/replacement-no-fallback'
        _proposal, _current, _proof, _execution = self._write_admitted_mvg_candidate(
            run_dir, 'candidates/candidate-1--candidate-1-r2')
        (run_dir / 'candidates/candidate-1--candidate-1-r2/proposal.json').unlink()
        stale = run_dir / 'candidates/candidate-1/proposal.json'
        stale.parent.mkdir(parents=True)
        proposal = {'schema_version': mvg.PROPOSAL_SCHEMA,
                    'analysis_identity_sha256': 'sha256:current',
                    'manifest_candidate': {'flows': []}}
        atomic_json(stale, proposal)
        proof = run_dir / 'candidates/candidate-1/admission-review.json'
        execution = run_dir / 'candidates/candidate-1/admission-execution.json'
        atomic_json(proof, {'schema_version': 'newrouge.mvg-semantic-review.v1',
            'analysis_identity_sha256': 'sha256:current', 'proposal_sha256': canonical_sha(proposal),
            'verdict': 'approved', 'findings': [], 'requirement_reviews': [], 'flow_reviews': []})
        atomic_json(execution, {'analysis_identity_sha256': 'sha256:current',
            'proposal_sha256': canonical_sha(proposal), 'semantic_review_sha256': canonical_sha(load_json(proof)),
            'runner_info': RUNNER, 'receipt': {'model': RUNNER['model'], 'model_tools': []}})
        state = {'analysis_identity_sha256': 'sha256:current',
            'candidate_attempts': {'candidate-1': {
                'status': 'valid', 'proposal_sha256': planning.file_sha(stale),
                'validation': {'status': 'passed', 'formal_applicable': True},
            }},
            'candidate_admissions': {'candidate-1': {
                'status': 'admitted', 'workspace': 'candidates/candidate-1--candidate-1-r2',
                'review_path': proof.relative_to(self.root).as_posix(),
                'review_execution_path': execution.relative_to(self.root).as_posix(),
                'proof_sha256': planning.file_sha(proof), 'execution_sha256': planning.file_sha(execution),
            }}}
        self.assertEqual([], planning._mvg_valid_candidates(run_dir, state))

    def test_mvg_recovery_rejects_candidate_with_stale_analysis_identity(self):
        run_dir = self.root / 'logs/ci/mvg-planning/identity-recovery'
        candidate = run_dir / 'candidates/candidate-1.json'
        candidate.parent.mkdir(parents=True)
        candidate.write_text('{"analysis_identity_sha256":"sha256:old"}', encoding='utf-8')
        state = {'analysis_identity_sha256': 'sha256:current', 'candidate_attempts': {'candidate-1': {
            'status': 'valid', 'proposal_sha256': planning.file_sha(candidate),
            'validation': {'status': 'passed', 'formal_applicable': True},
        }}}
        self.assertEqual([], planning._mvg_valid_candidates(run_dir, state))

    def test_mvg_recovery_rejects_candidate_when_run_identity_is_missing(self):
        run_dir = self.root / 'logs/ci/mvg-planning/recovery-missing-identity'
        candidate = run_dir / 'candidates/candidate-1.json'
        candidate.parent.mkdir(parents=True)
        candidate.write_text('{"analysis_identity_sha256":"sha256:any"}', encoding='utf-8')
        state = {'candidate_attempts': {'candidate-1': {
            'status': 'valid', 'proposal_sha256': planning.file_sha(candidate),
            'validation': {'status': 'passed', 'formal_applicable': True},
        }}}
        self.assertEqual([], planning._mvg_valid_candidates(run_dir, state))

    def test_mvg_run_rejects_prepared_capability_identity_drift(self):
        job_id = 'planning-' + 'd' * 32
        capability_id = 'planning-' + 'e' * 32
        job = {
            'job_id': job_id, 'action': 'mvg', 'checkout_job_id': capability_id,
            'capabilities_sha256': 'sha256:expected',
        }
        checkout = self.root / 'logs/ci/mvg-checkout'
        run_dir = checkout / 'logs/ci/mvg-planning' / job_id / 'analysis-input'
        run_dir.mkdir(parents=True)
        atomic_json(run_dir / 'analysis-index.json', {
            'capabilities_sha256': 'sha256:actual',
        })
        with self.assertRaisesRegex(ValueError, 'Capability identity mismatch'):
            planning.validate_mvg_capability_binding(self.root, checkout, job)

    def test_mvg_recovery_preserves_selected_prefix_without_current_candidates(self):
        import _mvg_capability_selection as selection

        prepared_mvg(self.root)
        git(self.root, 'add', '.')
        git(self.root, 'commit', '-m', 'fixture: reviewed capabilities for prefix recovery')
        invoke, invocations = self._production_consumers()
        worker = selection.generate_append

        def interrupt_current_scope(*args, **kwargs):
            if kwargs.get('scope_index') == 1:
                raise OSError('Fixture interrupted before current candidates')
            return worker(*args, **kwargs)

        with patch.object(planning, 'invoke', side_effect=invoke), \
             patch.object(planning, 'runner_path', return_value=Path('fixture')), \
             patch.dict(os.environ, {'SC_KNOWLEDGE_MVG_BACKEND': 'openai-api'}):
            job = planning.create_job(self.root, 'mvg')
            with patch.object(selection, 'generate_append', side_effect=interrupt_current_scope):
                result = planning.run_job(self.root, job)
            self.assertEqual('failed', result['status'], result)
            self.assertEqual('generate', result['stage'])
            stored = planning.read_job(self.root, job['job_id'])
            checkout = planning.execution_root(self.root, stored)
            run_dir = checkout / 'logs/ci/mvg-planning' / job['job_id']
            state = load_json(run_dir / 'run.json')
            self.assertEqual(1, len(state['capability_selection']['selected']))
            self.assertEqual([], planning._mvg_valid_candidates(run_dir, state))
            self.assertTrue(selection.recovery_available(checkout, run_dir, state))
            resumed = planning.create_job(self.root, 'mvg')
            self.assertEqual(job['job_id'], resumed['job_id'])
            before = len(invocations)
            result = planning.run_job(self.root, resumed)
            self.assertEqual('completed', result['status'], result)
            self.assertEqual(3, sum(path.endswith('capability-append.json')
                                    for path in invocations[before:]))
            fresh = planning.create_job(self.root, 'mvg', fresh=True)
            self.assertNotEqual(job['job_id'], fresh['job_id'])
            state['capability_selection']['terminal'] = True
            atomic_json(run_dir / 'run.json', state)
            atomic_json(planning.job_path(self.root, job['job_id']), stored)
            atomic_json(self.root / planning.JOB_ROOT / 'mvg-attempt.json', {'job_id': job['job_id']})
            self.assertFalse(selection.recovery_available(checkout, run_dir, state))
            replacement = planning.create_job(self.root, 'mvg')
            self.assertNotEqual(job['job_id'], replacement['job_id'])

    def test_new_main_commit_with_unchanged_inputs_allows_publication(self):
        job = planning.create_job(self.root, 'capability')
        git(self.root, 'commit', '--allow-empty', '-m', 'fixture: new main')
        invoke, _ = self._production_consumers()
        with patch.object(planning, 'invoke', side_effect=invoke), \
             patch.object(planning, 'runner_path', return_value=Path('fixture')):
            result = planning.run_job(self.root, job)
        self.assertEqual('completed', result['status'])
        self.assertIsNotNone(planning.generated_view(self.root, 'capability'))

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
            invocations.append(str(kwargs['output_path']))
            prompt = Path(kwargs['prompt_path']).read_text(encoding='utf-8')
            transport_schema = load_json(kwargs.get('output_schema'), {}) if kwargs.get('output_schema') else {}
            schema_version = transport_schema.get('properties', {}).get('schema_version', {}).get('const')
            if schema_version in {'newrouge.mvg-capability-append.v1', 'newrouge.mvg-semantic-review.v1'} and 'segments' in str(workspace):
                context = json.loads(prompt.split('\n', 1)[1])
                if schema_version == 'newrouge.mvg-capability-append.v1':
                    scope = context['scope']
                    fid = 'routing-' + scope['capability_id'].lower()
                    tid = fid + '-test'
                    accepted_entrypoints = context['accepted_proposal'].get('entrypoints', [])
                    prior_flow_ids = [ref for row in accepted_entrypoints if row.get('owner_task') == 42
                                      for ref in row.get('flow_ids', [])]
                    payload = {key: prop['const'] for key, prop in transport_schema['properties'].items() if 'const' in prop}
                    payload.update(flows=[{'id': fid, 'outcome': 'Relay delivers or exposes retry.',
                        'requirement_ids': scope['new_requirement_ids'], 'capability_refs': [scope['capability_id']],
                        'task_ids': [7, 42], 'source_paths': [GDD_PATH.as_posix()], 'test_ids': [tid],
                        'handoffs': [{'producer_task': 7, 'consumer_task': 42, 'owner_task': 42,
                            'contract_ref': 'Game.Core/Contracts/RelayHandoff.cs', 'contract_refs': None,
                            'behavior': 'Deliver or preserve retry state.', 'test_ids': [tid], 'from': None, 'to': None}]}],
                        coverage_table=[{'requirement_id': rid, 'capability_ref': scope['capability_id'],
                            'task_id': next(row['taskmaster_id'] for row in context['task_views'] if rid in row.get('semantic_refs', [])),
                            'flow_id': fid, 'disposition': 'flow', 'rationale': 'Owned observable relay behavior.',
                            'sink_id': None, 'verification_ref': None, 'authority_ref': None, 'authority_review': None}
                            for rid in scope['new_requirement_ids']],
                        tests=[{'id': tid, 'kind': 'dotnet', 'state': 'planned', 'flow_id': fid, 'test_refs': [],
                            'path': 'Game.Core.Tests/Tasks/PlanningAcceptanceTests.cs', 'selector': 'PlanningAcceptanceTests',
                            'evidence_level': 'domain-integration', 'min_tests': 1}],
                        entrypoints=[{'status': 'planned', 'flow_ids': prior_flow_ids + [fid], 'owner_task': 42,
                            'path': 'Game.Core/Tasks/Relay42.cs', 'symbol': 'Run', 'inputs': 'Request',
                            'state': 'Ready', 'assertions': 'Delivery or retry visible',
                            'implementation_acceptance': 'Implement both outcomes'}], change_reviews=[], gaps=[], notes=[])
                else:
                    proposal = context['proposal']
                    payload = {'schema_version': schema_version,
                        'analysis_identity_sha256': proposal['analysis_identity_sha256'], 'proposal_sha256': canonical_sha(proposal),
                        'verdict': 'approved', 'findings': [], 'requirement_reviews': [
                            {'requirement_id': row['requirement_id'], 'verdict': 'covered', 'rationale': 'Owned observable behavior.',
                             'repair_action': 'none', 'disposition': row['disposition'], 'route': row['disposition'],
                             'flow_id': row['flow_id'], 'sink_id': None, 'verification_ref': None, 'authority_ref': None}
                            for row in proposal['coverage_table']], 'flow_reviews': [
                            {'flow_id': flow['id'], 'verdict': 'sound', 'rationale': 'Owned contract and test obligation.'}
                            for flow in proposal['manifest_candidate']['flows']]}
                atomic_json(kwargs['output_path'], payload)
                return {'model': RUNNER['model'], 'model_tools': []}
            if transport_schema.get('properties', {}).get('section', {}).get('const') == 'routing':
                context, _ = json.JSONDecoder().raw_decode(prompt.split('\n', 1)[1].lstrip())
                routes = []
                for index, row in enumerate(context['requirements'].values(), 1):
                    rid = row['requirement_id']
                    allowed = context['permitted_flow_scopes'][rid]
                    flow_id = allowed[0] if isinstance(allowed, list) else f'routing-relay-{index}'
                    routes.append({'requirement_id': rid, 'disposition': 'flow', 'flow_id': flow_id,
                                   'rationale': 'Fixture source-backed journey', 'sink_id': None,
                                   'verification_ref': None, 'authority_ref': None})
                atomic_json(kwargs['output_path'], {'schema_version': mvg.SEGMENT_SCHEMA,
                    'analysis_identity_sha256': transport_schema['properties']['analysis_identity_sha256']['const'],
                    'section': 'routing', 'scope_id': 'candidate-routing', 'routes': routes})
                return {'model': RUNNER['model'], 'model_tools': []}
            if 'Capability identity alignment reviewer' in prompt:
                base = json.loads(prompt.split('BASE_ALIGNMENT=', 1)[1].split('\nCANDIDATE=', 1)[0])
                decisions = []
                for row in base['decisions']:
                    item = dict(row)
                    if item.get('candidate_id') is not None:
                        item.update(action='add', stable_id='CAP-' + str(item['candidate_id']).removeprefix('TMP-CAP-'), resolved=True,
                                    reason='Fixture alignment decision')
                    else:
                        item.update(action='retire', resolved=True, reason='Fixture historical retirement')
                    decisions.append(item)
                atomic_json(kwargs['output_path'], {'decisions': decisions})
                return {'model': RUNNER['model'], 'model_tools': []}
            # MVG generation uses a deliberately empty, segment-local model
            # workspace.  Consume the bounded context embedded in the prompt
            # instead of assuming the immutable analysis bundle is mounted
            # inside that sandbox.
            segment_match = re.search(r"section must be '([^']+)'", prompt)
            if segment_match:
                section = segment_match.group(1)
                identity = re.search(
                    r"analysis_identity_sha256 must be exactly '([^']+)'", prompt
                ).group(1)
                scope_id = re.search(r"scope_id must be '([^']+)'", prompt).group(1)
                scope_match = re.search(r"scope is (\{[^\n]+\})", prompt)
                scope = json.loads(scope_match.group(1)) if scope_match else {}
                context = {}
                context_marker = '\nInline bounded evidence context:\n'
                if context_marker in prompt:
                    context_text = prompt.split(context_marker, 1)[1].lstrip()
                    context, _ = json.JSONDecoder().raw_decode(context_text)
                flow_context = []
                flow_marker = '\nUse these already prepared flow objects as the only flow context:\n'
                if flow_marker in prompt:
                    flow_text = prompt.split(flow_marker, 1)[1].lstrip()
                    flow_context, _ = json.JSONDecoder().raw_decode(flow_text)
                requirements = context.get('requirements', [])
                requirement_ids = [str(value) for value in scope.get('requirement_ids', [])]
                task_ids = [int(value) for value in scope.get('task_ids', [])]
                capabilities = context.get('capabilities', [])
                capability_by_requirement = {
                    str(requirement): str(row.get('capability_id'))
                    for row in capabilities
                    for requirement in row.get('requirement_ids', [])
                    if str(row.get('capability_id') or '').strip()
                }
                source_paths = context.get('available_source_paths') or [GDD_PATH.as_posix()]
                contract_paths = context.get('available_contract_paths') or [
                    'Game.Core/Contracts/RelayHandoff.cs'
                ]
                envelope = {
                    'schema_version': mvg.SEGMENT_SCHEMA,
                    'analysis_identity_sha256': identity,
                    'section': section,
                    'scope_id': scope_id,
                }
                if section == 'flows':
                    scoped_requirements = [
                        str(row.get('requirement_id')) for row in requirements
                        if isinstance(row, dict) and row.get('requirement_id')
                    ] or requirement_ids
                    scoped_capabilities = [
                        str(row.get('capability_id')) for row in capabilities
                        if isinstance(row, dict) and row.get('capability_id')
                    ] or [capability_by_requirement.get(rid, '') for rid in scoped_requirements]
                    scoped_capabilities = [value for value in scoped_capabilities if value]
                    scoped_tasks = task_ids or [7, 42]
                    envelope['flows'] = [{
                        'id': scope_id,
                        'outcome': 'Relay delivery completes or exposes a retryable failure.',
                        'requirement_ids': scoped_requirements,
                        'capability_refs': scoped_capabilities,
                        'task_ids': scoped_tasks,
                        'source_paths': [str(source_paths[0]).replace('\\', '/')],
                        'handoffs': [{
                            'producer_task': scoped_tasks[0],
                            'consumer_task': scoped_tasks[-1],
                            'owner_task': scoped_tasks[-1],
                            'contract_ref': str(contract_paths[0]).replace('\\', '/'),
                            'contract_refs': None,
                            'behavior': 'Deliver the transfer result or preserve a retryable failure state.',
                            'test_ids': [f'{scope_id}-test'],
                            'from': None,
                            'to': None,
                        }],
                        'test_ids': [f'{scope_id}-test'],
                    }]
                elif section == 'coverage':
                    flow_ids = [str(row.get('id')) for row in flow_context
                                if isinstance(row, dict) and row.get('id')]
                    rows = []
                    for row in requirements:
                        if not isinstance(row, dict) or not row.get('requirement_id'):
                            continue
                        rid = str(row['requirement_id'])
                        matching_flow = next((flow for flow in flow_context
                                              if isinstance(flow, dict)
                                              and rid in {str(value) for value in flow.get('requirement_ids', [])}), None)
                        flow_id = str(matching_flow.get('id')) if matching_flow else (flow_ids[0] if flow_ids else None)
                        matching_tasks = (matching_flow or {}).get('task_ids') or task_ids
                        rows.append({
                            'requirement_id': rid,
                            'flow_id': flow_id,
                            'capability_ref': (row.get('capability_refs') or
                                               [capability_by_requirement.get(rid)])[0],
                            'task_id': matching_tasks[0] if matching_tasks else None,
                            'disposition': 'flow',
                            'rationale': 'The fixture flow observes this delivery requirement.',
                            'sink_id': None,
                            'verification_ref': None,
                            'authority_ref': None,
                            'authority_review': None,
                        })
                    envelope['coverage_table'] = rows
                elif section == 'entrypoints':
                    envelope['entrypoints'] = [{
                        'status': 'planned',
                        'flow_ids': [str(flow['id']) for flow in flow_context if task_id in flow.get('task_ids', [])],
                        'owner_task': task_id,
                        'path': f'Game.Core/Tasks/Relay{task_id}.cs',
                        'symbol': f'Relay{task_id}.Run',
                        'inputs': ['route'],
                        'state': 'cargo transfer',
                        'assertions': ['accepted or retry visible'],
                        'implementation_acceptance': ['relay journey'],
                    } for task_id in task_ids]
                elif section == 'tests':
                    flow_ids = [str(row.get('id')) for row in flow_context
                                if isinstance(row, dict) and row.get('id')]
                    envelope['tests'] = [{
                        'id': f'{scope_id}-{index:02d}',
                        'flow_id': flow_id,
                        'test_refs': [],
                        'kind': 'dotnet',
                        'state': 'planned',
                        'path': 'Game.Core.Tests/Tasks/PlanningAcceptanceTests.cs',
                        'selector': 'PlanningAcceptanceTests',
                        'evidence_level': 'domain-integration',
                        'min_tests': 1,
                    } for index, flow_id in enumerate(flow_ids, 1)]
                else:
                    raise AssertionError(f'Unexpected MVG segment section: {section}')
                atomic_json(kwargs['output_path'], envelope)
                return {'model': RUNNER['model'], 'model_tools': []}
            index = load_json(workspace / 'analysis-input/analysis-index.json')
            if (workspace / 'selection-output-schema.json').exists() or (workspace / 'A.json').exists():
                labels = ['A', 'B', 'C'] + (['D'] if (workspace / 'D.json').exists() else [])
                payload = {
                    'schema_version': mvg.MVG_SELECTION_SCHEMA,
                    'selected': 'A',
                    'status': 'selected',
                    'candidate_reviews': [
                        {'label': label, 'verdict': 'viable', 'rationale': 'Fixture candidate is structurally valid.',
                         'rank': rank}
                        for rank, label in enumerate(labels, 1)
                    ],
                    'tradeoffs': ['Candidate A is selected by the fixture evaluator.'],
                    'evidence_refs': ['analysis-input/capabilities.v1.json'],
                    'rationale': 'Fixture selection keeps one complete candidate without merging proposals.',
                }
            elif (workspace / 'candidates/A.json').exists():
                payload = review_report(workspace)
            elif (workspace / 'proposal.json').exists():
                proposal = load_json(workspace / 'proposal.json')
                payload = deepcopy(review_template)
                payload.update(analysis_identity_sha256=index['analysis_identity_sha256'], proposal_sha256=canonical_sha(proposal))
                requirement_ids = {
                    str(row.get('requirement_id'))
                    for row in proposal.get('coverage_table', [])
                    if isinstance(row, dict) and row.get('requirement_id')
                }
                payload['requirement_reviews'] = [
                    {'requirement_id': row['requirement_id'],
                     'verdict': {'flow': 'covered', 'other_verification': 'other_verification',
                                 'deferred': 'deferred'}.get(row.get('disposition', 'flow'), 'covered'),
                     'rationale': 'The fixture proposal accounts for this requirement.',
                     'repair_action': 'none',
                     'disposition': row.get('disposition', 'flow'),
                     'flow_id': row.get('flow_id'), 'sink_id': row.get('sink_id'),
                     'verification_ref': row.get('verification_ref'),
                     'authority_ref': row.get('authority_ref')}
                    for row in proposal.get('coverage_table', [])
                    if row.get('requirement_id') in requirement_ids
                ]
                flow_rows = proposal.get('manifest_candidate', {}).get('flows', [])
                payload['flow_reviews'] = [
                    {'flow_id': str(row.get('id')), 'verdict': 'sound',
                     'rationale': 'The fixture flow has a prepared contract and planned test.'}
                    for row in flow_rows if isinstance(row, dict) and row.get('id')
                ]
            elif (workspace / 'analysis-input/capabilities.v1.json').exists():
                payload = deepcopy(proposal_template)
                payload['analysis_identity_sha256'] = index['analysis_identity_sha256']
                formal = load_json(workspace / 'analysis-input/capabilities.v1.json')
                actual_ids = [str(row['capability_id']) for row in formal.get('capabilities', [])]
                req_to_cap = {
                    str(requirement): str(row['capability_id'])
                    for row in formal.get('capabilities', [])
                    for requirement in row.get('requirement_ids', [])
                }
                for flow in payload.get('manifest_candidate', {}).get('flows', []):
                    flow['capability_refs'] = actual_ids
                for row in payload.get('coverage_table', []):
                    row['capability_ref'] = req_to_cap.get(str(row['requirement_id']), actual_ids[0] if actual_ids else '')
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
            return {'model': RUNNER['model'], 'model_tools': [],
                    'output_sha256': planning.file_sha(kwargs['output_path'])}

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
            self.assertEqual(5, len(invocations))
            topology = planning.generated_view(self.root, 'capability')
            self.assertEqual(2, len(topology['nodes']['capabilities']))
            self.assertEqual(self.revision, topology['identity']['revision'])
            self.assertEqual('local_generated', topology['publication_state'])
            mvg_job = planning.create_job(self.root, 'mvg')
            self.assertEqual(cap_job['job_id'], mvg_job['checkout_job_id'])
            mvg_checkout = planning.execution_root(self.root, mvg_job)
            cap_checkout = planning.execution_root(self.root, cap_job)
            self.assertNotEqual(cap_checkout, mvg_checkout)
            result = planning.run_job(self.root, mvg_job)
            ledger = load_json(mvg_checkout / 'logs/ci/mvg-planning' / mvg_job['job_id'] /
                               'candidates/candidate-1/scope-1/capability-append/append-ledger.json', {})
            self.assertEqual('completed', result['status'], (result, ledger.get('issue_events', [])[:2]))
            self.assertEqual(self.revision, git(mvg_checkout, 'rev-parse', 'HEAD'))
            self.assertEqual(
                (cap_checkout / 'docs/planning/semantic-topology/capabilities.v1.json').read_bytes(),
                (mvg_checkout / 'docs/planning/semantic-topology/capabilities.v1.json').read_bytes(),
            )
            # Capability uses five model calls. Each MVG scope generates and
            # admits three independent increments before comparative selection.
            # Final admission-proof verification is local and invokes no model.
            generated_invocation_count = len(invocations)
            self.assertEqual(6, sum(path.endswith('capability-append.json') for path in invocations))
            admission_state = load_json(mvg_checkout / 'logs/ci/mvg-planning' / mvg_job['job_id'] / 'run.json')
            self.assertTrue(all(row['status'] == 'admitted' for row in admission_state['candidate_admissions'].values()))
            overview = planning.generated_view(self.root, 'mvg')
            self.assertIsNotNone(overview)
            self.assertEqual(1, len(overview['manifests']))
            self.assertEqual('docs/testing/mvg/m1-full.json', overview['manifests'][0]['path'])
            self.assertFalse(overview['runtime_verified'])
            self.assertIsNotNone(planning.generated_view(self.root, 'capability'))
            (self.root / GDD_PATH).write_text('Dirty source must not appear in preview', encoding='utf-8')
            self.assertIsNone(planning.generated_view(self.root, 'capability'))
            with self.assertRaisesRegex(ValueError, 'Generated topology changed'):
                planning.planning_source(self.root, cap_job['job_id'], GDD_PATH.as_posix())
            git(self.root, 'restore', GDD_PATH.as_posix())
            self.assertIsNotNone(planning.generated_view(self.root, 'capability'))
            with self.assertRaisesRegex(ValueError, 'not in the generated topology'):
                planning.planning_source(self.root, cap_job['job_id'], '.git/config')
            self.assertEqual(before, git(self.root, 'status', '--porcelain'))
            self.assertFalse((self.root / cap.FORMAL_CAPABILITIES).exists())
            self.assertFalse((self.root / mvg_job['manifest']).exists())
            reused = planning.create_job(self.root, 'capability')
            self.assertEqual('completed', reused['status'])
            self.assertEqual(cap_job['job_id'], reused['job_id'])
            self.assertEqual(generated_invocation_count, len(invocations))
        git(self.root, 'commit', '--allow-empty', '-m', 'fixture: later main')
        self.assertIsNotNone(planning.generated_view(self.root, 'capability'))
        self.assertIsNotNone(planning.generated_view(self.root, 'mvg'))

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
        self.assertEqual(6, sum(path.endswith('capability-append.json') for path in invocations))
        self.assertEqual(main_revision(self.root), planning.generated_view(self.root, 'mvg')['revision'])
        stored = planning.read_job(self.root, job['job_id'])
        checkout = planning.execution_root(self.root, stored)
        run = checkout / 'logs/ci/mvg-planning' / job['job_id']
        state = load_json(run / 'run.json')
        self.assertTrue(planning._planning_input_fresh(self.root, stored))
        for path in (checkout / job['manifest'],
                     checkout / 'logs/ci/chapter5/readiness/task-7.json',
                     run / 'analysis-input/capabilities.v1.json'):
            original = path.read_bytes()
            try:
                path.write_bytes(original + b'\nFixture unauthorized edit.\n')
                self.assertFalse(planning._planning_input_fresh(self.root, stored), str(path))
            finally:
                path.write_bytes(original)
        journal_path = run / 'apply-journal.json'
        journal = load_json(journal_path)
        changed = deepcopy(journal)
        next(row for row in changed['entries'] if row['path'] == state['manifest_path'])['after_sha256'] = 'sha256:foreign'
        atomic_json(journal_path, changed)
        self.assertFalse(planning._planning_input_fresh(self.root, stored))
        atomic_json(journal_path, journal)
        self.assertTrue(planning._planning_input_fresh(self.root, stored))
        manifest_path = checkout / job['manifest']
        original = manifest_path.read_bytes()
        try:
            manifest_path.unlink()
            self.assertFalse(planning._planning_input_fresh(self.root, stored))
            manifest_path.mkdir()
            self.assertFalse(planning._planning_input_fresh(self.root, stored))
        finally:
            if manifest_path.is_dir():
                manifest_path.rmdir()
            manifest_path.write_bytes(original)
        self.assertTrue(planning._planning_input_fresh(self.root, stored))

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
            first = planning.run_job(self.root, job)
            self.assertEqual('recoverable', first['status'])
            self.assertEqual('review', first['stage'])
            self.assertEqual(3, len(invocations))
            resumed = planning.create_job(self.root, 'capability')
            self.assertEqual(job['job_id'], resumed['job_id'])
            result = planning.run_job(self.root, resumed)
        self.assertEqual('completed', result['status'], result)
        self.assertEqual(5, len(invocations))

    def test_alignment_failure_is_recoverable_and_resume_starts_at_alignment(self):
        invoke, invocations = self._production_consumers()
        stage_calls = []
        fail_alignment_once = True

        def alignment_interrupt(checkout, script, args, log):
            nonlocal fail_alignment_once
            stage_calls.append(args[0])
            if args[0] == 'align' and fail_alignment_once:
                fail_alignment_once = False
                raise ValueError('Fixture alignment output rejected')
            return invoke(checkout, script, args, log)

        with patch.object(planning, 'invoke', side_effect=alignment_interrupt), \
             patch.object(planning, 'runner_path', return_value=Path('fixture')):
            job = planning.create_job(self.root, 'capability')
            first = planning.run_job(self.root, job)
            self.assertEqual('recoverable', first['status'], first)
            self.assertEqual('align', first['stage'])
            self.assertIn('retry', first['message'].lower())
            self.assertEqual(['prepare', 'generate', 'review', 'align'], stage_calls)

            resumed = planning.create_job(self.root, 'capability')
            self.assertEqual(job['job_id'], resumed['job_id'])
            second = planning.run_job(self.root, resumed)

        self.assertEqual('completed', second['status'], second)
        self.assertEqual(['prepare', 'generate', 'review', 'align', 'align', 'apply'], stage_calls)
        # The resumed run must not pay for candidate generation or independent review again.
        self.assertEqual(5, len(invocations))

    def test_apply_failure_is_recoverable_and_resume_starts_at_apply(self):
        invoke, invocations = self._production_consumers()
        stage_calls = []
        fail_apply_once = True

        def apply_interrupt(checkout, script, args, log):
            nonlocal fail_apply_once
            stage_calls.append(args[0])
            if args[0] == 'apply' and fail_apply_once:
                fail_apply_once = False
                raise ValueError('Fixture apply publication interruption')
            return invoke(checkout, script, args, log)

        with patch.object(planning, 'invoke', side_effect=apply_interrupt), \
             patch.object(planning, 'runner_path', return_value=Path('fixture')):
            job = planning.create_job(self.root, 'capability')
            first = planning.run_job(self.root, job)
            self.assertEqual('recoverable', first['status'], first)
            self.assertEqual('apply', first['stage'])
            self.assertEqual(['prepare', 'generate', 'review', 'align', 'apply'], stage_calls)

            resumed = planning.create_job(self.root, 'capability')
            self.assertEqual(job['job_id'], resumed['job_id'])
            second = planning.run_job(self.root, resumed)

        self.assertEqual('completed', second['status'], second)
        self.assertEqual(['prepare', 'generate', 'review', 'align', 'apply', 'apply'], stage_calls)
        self.assertEqual(5, len(invocations))

    def test_unresolved_alignment_apply_failure_recovers_from_alignment(self):
        invoke, invocations = self._production_consumers()
        stage_calls = []
        fail_apply_once = True

        def apply_interrupt(checkout, script, args, log):
            nonlocal fail_apply_once
            stage_calls.append(args[0])
            if args[0] == 'apply' and fail_apply_once:
                fail_apply_once = False
                atomic_json(
                    checkout / 'logs/ci/capability-planning' / current_job['job_id'] /
                    'alignment-preview.json',
                    {'resolved': False},
                )
                raise ValueError('Fixture unresolved alignment')
            return invoke(checkout, script, args, log)

        with patch.object(planning, 'invoke', side_effect=apply_interrupt), \
             patch.object(planning, 'runner_path', return_value=Path('fixture')):
            current_job = planning.create_job(self.root, 'capability')
            first = planning.run_job(self.root, current_job)
            self.assertEqual('recoverable', first['status'], first)
            self.assertEqual('align', first['stage'])

            resumed = planning.create_job(self.root, 'capability')
            second = planning.run_job(self.root, resumed)

        self.assertEqual('completed', second['status'], second)
        self.assertEqual(['prepare', 'generate', 'review', 'align', 'apply', 'align', 'apply'], stage_calls)
        self.assertEqual(6, len(invocations))

    def test_review_interruption_after_candidates_is_recoverable(self):
        invoke, invocations = self._production_consumers()
        stage_calls = []
        fail_review_once = True

        def review_interrupt(checkout, script, args, log):
            nonlocal fail_review_once
            stage_calls.append(args[0])
            if args[0] == 'review' and fail_review_once:
                fail_review_once = False
                raise ValueError('Fixture review transport interruption')
            return invoke(checkout, script, args, log)

        with patch.object(planning, 'invoke', side_effect=review_interrupt), \
             patch.object(planning, 'runner_path', return_value=Path('fixture')):
            job = planning.create_job(self.root, 'capability')
            first = planning.run_job(self.root, job)
            self.assertEqual('recoverable', first['status'], first)
            self.assertEqual('review', first['stage'])
            self.assertEqual(['prepare', 'generate', 'review'], stage_calls)

            resumed = planning.create_job(self.root, 'capability')
            self.assertEqual(job['job_id'], resumed['job_id'])
            second = planning.run_job(self.root, resumed)

        self.assertEqual('completed', second['status'], second)
        self.assertEqual(['prepare', 'generate', 'review', 'review', 'align', 'apply'], stage_calls)
        self.assertEqual(5, len(invocations))

    def test_error_is_compact_and_unstarted_prepare_attempt_can_be_retried(self):
        job = planning.create_job(self.root, 'capability')
        with patch.object(planning, 'runner_path', side_effect=ValueError('Useful reason\n' + 'x' * 2000)):
            result = planning.run_job(self.root, job)
        self.assertLessEqual(len(result['message']), 370)
        retried = planning.create_job(self.root, 'capability')
        self.assertNotEqual(job['job_id'], retried['job_id'])

    def test_prepare_failure_creates_a_fresh_attempt_on_retry(self):
        failed = planning.create_job(self.root, 'capability')
        failed.update(status='failed', stage='prepare', message='Git checkout failed')
        atomic_json(planning.job_path(self.root, failed['job_id']), failed)

        retried = planning.create_job(self.root, 'capability')

        self.assertNotEqual(failed['job_id'], retried['job_id'])
        self.assertEqual('queued', retried['status'])
        self.assertEqual(self.revision, retried['revision'])

    def test_api_backend_follows_configured_credentials(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'fixture-only', 'SC_KNOWLEDGE_MVG_BACKEND': 'openai-api'}, clear=True):
            self.assertEqual('openai-api', planning.mvg_backend())
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual('codex-cli', planning.mvg_backend())
        with patch.dict(os.environ, {'SC_KNOWLEDGE_MVG_BACKEND': 'shell'}, clear=True):
            with self.assertRaisesRegex(ValueError, 'Unsupported'):
                planning.mvg_backend()

    def test_failed_cli_json_reports_only_the_specific_reason(self):
        self.assertEqual('Readiness expired', planning.compact_error('{"status":"blocked","reason":"Readiness expired"}'))

    def test_selected_result_recovers_completed_attempt_when_latest_pointer_is_missing(self):
        job_id = 'planning-' + ('a' * 32)
        job_dir = self.root / planning.JOB_ROOT / job_id
        job_dir.mkdir(parents=True)
        result_path = job_dir / 'result.json'
        atomic_json(result_path, {'topology': {'nodes': {'capabilities': []}}})
        job = {
            'schema_version': 'newrouge.knowledge-planning-job.v1',
            'job_id': job_id,
            'action': 'capability',
            'status': 'completed',
            'result_sha256': planning.file_sha(result_path),
        }
        atomic_json(job_dir / 'job.json', job)
        atomic_json(self.root / planning.JOB_ROOT / 'capability-attempt.json', {'job_id': job_id})

        with patch.object(planning, '_planning_input_fresh', return_value=True):
            selected = planning.selected_result(self.root, 'capability')

        self.assertIsNotNone(selected)
        self.assertEqual(job_id, selected['job_id'])

    def test_dependent_mvg_job_uses_its_own_revision_checkout(self):
        capability = {
            'job_id': 'planning-' + ('a' * 32),
            'revision': '1' * 40,
        }
        mvg = {
            'job_id': 'planning-' + ('b' * 32),
            'revision': '2' * 40,
            'checkout_job_id': capability['job_id'],
        }

        self.assertNotEqual(
            planning.execution_root(self.root, capability),
            planning.execution_root(self.root, mvg),
        )

    def test_failed_cli_json_preserves_error_type_and_attempt_budget(self):
        message = planning.compact_error(json.dumps({
            "status": "blocked",
            "reason": "MVG independent review execution attempt budget exhausted; upstream proposal is preserved",
            "error_type": "runner_input_too_large",
            "attempts_used": 10,
            "attempt_limit": 10,
        }))
        self.assertIn("error_type=runner_input_too_large", message)
        self.assertIn("attempts=10/10", message)


if __name__ == '__main__':
    unittest.main()
