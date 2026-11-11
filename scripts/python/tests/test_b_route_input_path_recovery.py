"""Synthetic path-recovery boundaries; no model/native acceptance evidence."""
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _b_route_input_path_recovery as path_recovery
import _b_route_partial_generation_recovery as partial
import test_b_route_partial_generation_recovery as prior_tests


class PathRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.outer = tempfile.TemporaryDirectory(dir=os.environ.get('PARTIAL_REPAIR_TEST_TEMP'))
        self.addCleanup(self.outer.cleanup)
        outer = Path(self.outer.name)
        suffix = Path('logs/ci/capability-planning/c4') / partial.WORKSPACE / 'capability-append' / partial.NAMESPACE / 'c5/llm-sandbox/attempt-5/r'
        self.failed_name = 'runner-input-integrity.json.6240.8916.4cb263e1578c4080856fa606f9aeab09.tmp'
        base = outer / ('x' * (263 - len(str(outer / 'x' / 'tmp12345678' / suffix / self.failed_name)) + 1))
        base.mkdir()
        self.h = prior_tests.PartialRepairTests('test_exact_old8_and_model_clocks_are_retained')
        with patch.dict(os.environ, {'PARTIAL_REPAIR_TEST_TEMP': str(base)}):
            self.h.setUp()
        self.addCleanup(self.h.doCleanups)
        h = self.h
        h.record['transition'].update(current_commit=path_recovery.PRIOR_COMMIT, current_source_root=str(h.root / 'r9'))
        h.state['b_route_execution_transition'] = deepcopy(h.record['transition'])
        h.persist_record()
        h.write(h.home / 'resume-claim.json', partial._marker(h.record, h.state))
        self.old_claim_raw = (h.home / 'resume-claim.json').read_bytes()
        failed_parent = h.run / suffix.relative_to('logs/ci/capability-planning/c4')
        h.write(failed_parent / 'output-schema.json', {'synthetic': 'old unreserved schema'})
        h.write(failed_parent / 'prompt-5-r.txt', {'synthetic': 'complete old request'})
        self.failed_path = failed_parent / self.failed_name
        self.assertEqual(263, len(str(self.failed_path)))
        h.local.update(status='blocked', errors=[{'code': 'append_input_preparation_failed',
            'detail': str(FileNotFoundError(2, 'No such file or directory', str(self.failed_path)))}])
        h.write(h.local_path, h.local)
        h.write(h.run / 'run.json', h.state)
        self.old_run_raw = (h.run / 'run.json').read_bytes()
        self.old_local_raw = h.local_path.read_bytes()
        self.transition = SimpleNamespace(build_successor_transition=Mock(return_value={
            'transition_digest': 'r10', 'current_commit': 'synthetic-r10', 'current_source_root': str(h.root / 'r10')}),
            validate_transition=Mock(side_effect=lambda root, state: state['b_route_execution_transition']['transition_digest']))

    @contextmanager
    def boundary(self):
        @contextmanager
        def lock(_): yield
        with self.h.boundary(), patch.dict(sys.modules, {'_b_route_execution_transition': self.transition,
                '_mvg_capability_checkpoint': SimpleNamespace(coordinator_lock=lock)}):
            yield

    def prepare(self):
        h = self.h
        with self.boundary():
            result = path_recovery.prepare(h.root, h.run, original_source_root=h.root / 'r5',
                current_commit='synthetic-r10', prior_source_root=h.root / 'r9')
        self.state = json.loads((h.run / 'run.json').read_bytes())
        self.local = json.loads(h.local_path.read_bytes())
        return result

    def test_preparation_retains_exact_failure_claims_budgets_and_shortens_only_new_paths(self):
        h = self.h
        before = partial._files(h.run / partial.WORKSPACE / 'capability-append' / partial.NAMESPACE)
        result = self.prepare()
        self.assertEqual(0, result['model_calls'])
        self.assertEqual(8, result['retained_logical_calls'])
        with self.boundary():
            record = path_recovery.validate_recovery(h.root, self.state)
            self.assertEqual(h.record, partial.validate_recovery(h.root, self.state))
        self.assertEqual(self.old_run_raw, partial.image_bytes(record['previous_run']))
        self.transition.validate_transition.assert_called_with(h.root, h.state)
        self.assertEqual(self.old_local_raw, partial.image_bytes(record['previous_append']))
        self.assertEqual(self.old_claim_raw, (h.home / 'resume-claim.json').read_bytes())
        self.assertEqual(before, partial._files(h.run / partial.WORKSPACE / 'capability-append' / partial.NAMESPACE))
        self.assertEqual(h.state[partial.REFERENCE], self.state[partial.REFERENCE])
        self.assertEqual(h.state['active_elapsed_seconds'], self.state['active_elapsed_seconds'])
        self.assertEqual(h.state['b_route_campaign_funding'], self.state['b_route_campaign_funding'])
        new = partial.call_root(self.state, h.workspace, 5, 'candidate-2')
        self.assertEqual(h.workspace / 'capability-append/p1/c5', new)
        self.assertEqual(h.workspace / 'capability-append/input-budget-recovery-1/c5', partial.call_root(h.state, h.workspace, 5, 'candidate-2'))
        self.assertEqual(h.workspace / 'capability-append/c4', partial.call_root(self.state, h.workspace, 4, 'candidate-2'))
        self.assertLess(len(str(new / 'llm-sandbox/attempt-5/r' / self.failed_name)), 260)

    def test_new_exclusive_claim_reuses_original_batch_once_without_counter_reset(self):
        h = self.h
        self.prepare()
        with self.boundary():
            self.assertTrue(partial.resume_propose_attempt(h.root, self.state, h.workspace, self.local['current'], self.local))
            self.assertEqual(([h.draft], [h.binding]), partial.resume_generation(h.root, self.state, h.workspace, {}, h.seed,
                self.local['current']['proposal'], self.local['current']['issue'], 1))
            with self.assertRaises(FileExistsError):
                partial.resume_propose_attempt(h.root, self.state, h.workspace, self.local['current'], self.local)
        self.assertEqual(self.old_claim_raw, (h.home / 'resume-claim.json').read_bytes())
        self.assertTrue((h.run / 'recovery/p1/resume-claim.json').is_file())
        self.assertEqual(h.state['capability_selection']['calls'], self.state['capability_selection']['calls'])
        self.assertEqual(8, self.state['capability_selection']['total_invocations'])
        self.assertEqual(4, self.local['total_invocations'])
        self.assertEqual(h.local['current']['issue_attempts'], self.local['current']['issue_attempts'])

    def test_missing_or_partial_new_claim_unknown_owner_and_changed_issue_fail_closed(self):
        h = self.h
        self.prepare()
        with self.boundary(), self.assertRaises((OSError, ValueError)):
            partial.resume_generation(h.root, self.state, h.workspace, {}, h.seed,
                self.local['current']['proposal'], self.local['current']['issue'], 1)
        new_claim = h.run / 'recovery/p1/resume-claim.json'
        new_claim.write_bytes(b'{"partial":')
        with self.boundary(), self.assertRaises(ValueError):
            partial.resume_generation(h.root, self.state, h.workspace, {}, h.seed,
                self.local['current']['proposal'], self.local['current']['issue'], 1)
        with self.boundary(), self.assertRaises(FileExistsError):
            partial.resume_propose_attempt(h.root, self.state, h.workspace, self.local['current'], self.local)
        self.assertEqual(b'{"partial":', new_claim.read_bytes())
        owner = deepcopy(self.state)
        row = deepcopy(owner['capability_selection']['calls'][7])
        row.update(number=9)
        row['outcome'] = {'status': 'unknown'}
        owner['capability_selection']['calls'].append(row)
        owner['capability_selection']['total_invocations'] = 9
        owner['capability_selection']['lineage_invocations']['candidate-2'] = 5
        h.write(h.run / 'run.json', owner)
        with self.boundary(), self.assertRaisesRegex(ValueError, 'unproven_changed_repair'):
            partial.resume_propose_attempt(h.root, self.state, h.workspace, self.local['current'], self.local)
        h.write(h.run / 'run.json', self.state)
        changed = deepcopy(self.local['current'])
        changed['issue_attempts'] = {}
        with self.boundary(), self.assertRaisesRegex(ValueError, 'unproven_changed_repair'):
            partial.resume_propose_attempt(h.root, self.state, h.workspace, changed, self.local)

    def test_archive_tamper_refund_source_change_and_partial_commit_are_rejected(self):
        h = self.h
        self.prepare()
        self.transition.validate_transition.side_effect = None
        self.transition.validate_transition.return_value = 'wrong-source'
        with self.boundary(), self.assertRaisesRegex(ValueError, 'archived_source_frame_changed'):
            path_recovery.validate_recovery(h.root, self.state)
        self.transition.validate_transition.side_effect = lambda root, state: state['b_route_execution_transition']['transition_digest']
        for field, value in (('active_elapsed_seconds', 0), ('b_route_campaign_funding', {'released': 1}),
                             ('b_route_execution_transition', {'transition_digest': 'wrong'})):
            changed = deepcopy(self.state)
            changed[field] = value
            with self.subTest(field=field), self.boundary(), self.assertRaises(ValueError):
                path_recovery.validate_recovery(h.root, changed)
        old_file = h.run / partial.WORKSPACE / 'capability-append' / partial.NAMESPACE / 'c5/llm-sandbox/attempt-5/r/prompt-5-r.txt'
        original = old_file.read_bytes()
        old_file.write_bytes(b'changed old request')
        with self.boundary(), self.assertRaisesRegex(ValueError, 'failed_namespace_changed'):
            path_recovery.validate_recovery(h.root, self.state)
        old_file.write_bytes(original)
        committed = h.run / 'recovery/p1/committed.json'
        committed.unlink()
        with self.boundary(), self.assertRaises((OSError, ValueError)):
            path_recovery.validate_recovery(h.root, self.state)
        self.assertFalse(committed.exists())

    def test_prepare_refuses_any_new_reservation_or_changed_failure_before_writes(self):
        h = self.h
        original_error = deepcopy(h.local['errors'])
        h.local['errors'][0]['detail'] = 'other failure'
        h.write(h.local_path, h.local)
        before = h.snapshot()
        with self.boundary(), self.assertRaisesRegex(ValueError, 'not_known_path_failure'):
            path_recovery.prepare(h.root, h.run, original_source_root=h.root / 'r5',
                current_commit='synthetic-r10', prior_source_root=h.root / 'r9')
        self.assertEqual(before, h.snapshot())
        self.transition.build_successor_transition.assert_not_called()
        h.local['errors'] = original_error
        h.write(h.local_path, h.local)
        state = deepcopy(h.state)
        row = deepcopy(state['capability_selection']['calls'][7])
        row.update(number=9)
        row['outcome'] = {'status': 'unknown'}
        state['capability_selection']['calls'].append(row)
        state['capability_selection']['total_invocations'] = 9
        state['capability_selection']['lineage_invocations']['candidate-2'] = 5
        h.write(h.run / 'run.json', state)
        before = h.snapshot()
        with self.boundary(), self.assertRaisesRegex(ValueError, 'not_exact_known_eight_call_failure'):
            path_recovery.prepare(h.root, h.run, original_source_root=h.root / 'r5',
                current_commit='synthetic-r10', prior_source_root=h.root / 'r9')
        self.assertEqual(before, h.snapshot())


if __name__ == '__main__':
    unittest.main(verbosity=2)
