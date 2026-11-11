"""Legacy partial progress and actual Windows producer-path regression controls."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / 'scripts/python'), str(ROOT)]
import _b_route_planning_runtime as runtime
import _mvg_capability_append as append
from _mvg_capability_generation import repair_scope_errors
from _mvg_requirement_accounting import VERIFICATION, EVIDENCE
from _mvg_requirement_routes import FIELD


class CompatibilityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def drive_legacy(self, *, unrelated=False):
        observed = []
        def propose(scope, base, prior, issue, context, call):
            call('generate')
            observed.append(deepcopy(prior))
            if prior is None:
                return {'manifest_candidate': {'flows': [
                    {'id': 'FLOW', 'revision': 0}, {'id': 'OTHER', 'revision': 0}]},
                    'coverage_table': [], 'tests': [], 'entrypoints': [],
                    FIELD: [], VERIFICATION: [], EVIDENCE: []}
            revised = deepcopy(prior)
            revised['manifest_candidate']['flows'][0]['revision'] += 1
            if unrelated:
                revised['manifest_candidate']['flows'][1]['revision'] = 99
            return revised
        def semantic(scope, base, proposal, call, context):
            call('semantic')
            revision = proposal['manifest_candidate']['flows'][0]['revision']
            return {'issues': [] if revision >= 2 else [
                {'code': 'needs-two-improvements:FLOW', 'path': 'semantic-review'}],
                'proof': {}, 'execution': {}}
        result = append.run_capability_append(self.root / 'append',
            scopes=[{'capability_id': 'C'}], seed={}, identity='legacy-partial-progress-control',
            propose=propose, machine=lambda *_: [], semantic=semantic,
            final_machine=lambda _: [], invocation_limit=12,
            merge=lambda base, delta, scope: delta, preserve=lambda *_: [],
            repair_check=repair_scope_errors)
        return result, observed

    def test_actual_legacy_scope_callback_keeps_partial_progress_until_final_semantic_pass(self):
        result, observed = self.drive_legacy()
        self.assertEqual(result['status'], 'admitted')
        self.assertEqual([None if p is None else p['manifest_candidate']['flows'][0]['revision']
                          for p in observed], [None, 0, 1])
        self.assertEqual(result['accepted']['manifest_candidate']['flows'][0]['revision'], 2)
        self.assertEqual(result['accepted']['manifest_candidate']['flows'][1]['revision'], 0)
        self.assertEqual(result['total_invocations'], 6)
        self.assertFalse(result.get('rejected_repairs'))
        self.assertFalse(result.get('restarts'))

    def test_partial_progress_does_not_allow_unrelated_legacy_flow_changes(self):
        result, observed = self.drive_legacy(unrelated=True)
        self.assertNotEqual(result['status'], 'admitted')
        self.assertFalse(result['records'])
        self.assertLessEqual(result['total_invocations'], 12)
        self.assertTrue(any('repair_unrelated_flow_changed:OTHER' in row['errors']
                            for row in result['rejected_repairs']))
        self.assertTrue(all(p is None or p['manifest_candidate']['flows'][1]['revision'] == 0
                            for p in observed))

    def test_public_run_capacity_covers_actual_integrity_temporary_names_before_mutation(self):
        admitted, rejected = 0, 0
        for padding in ('', 'x' * 20, 'x' * 40, '\U00010000' * 20):
            root = self.root if not padding else self.root / padding
            root.mkdir(exist_ok=True)
            for width in (1, 30):
                run_id = 'r' * width
                with self.subTest(padding_units=len(padding.encode('utf-16-le')) // 2, width=width):
                    try:
                        location = runtime.run_location(root, 'capabilities', run_id)
                    except ValueError as error:
                        self.assertIn('b_route_runtime_path_capacity', str(error))
                        rejected += 1
                    else:
                        # This is the real first-call integrity writer's shortest
                        # name, independent of the guard's worst-case inventory.
                        actual = location / ('candidates/candidate-1/scope-1/capability-append/'
                            'c1/llm-sandbox/attempt-1/r') / (
                            'runner-input-integrity.json.1.1.' + 'f' * 32 + '.tmp')
                        self.assertLessEqual(len(str(actual).encode('utf-16-le')) // 2, 259)
                        admitted += 1
                    self.assertFalse((root / 'logs').exists())
        self.assertGreater(admitted, 0)
        self.assertGreater(rejected, 0)


if __name__ == '__main__':
    unittest.main()
