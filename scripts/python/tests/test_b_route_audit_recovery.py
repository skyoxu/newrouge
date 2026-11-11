"""Recovery preconditions only; these do not qualify synthetic model evidence."""
from copy import deepcopy
from pathlib import Path
import unittest

import _b_route_codec as codec
import _b_route_audit_recovery as recovery


class AuditRecoveryPreconditionTests(unittest.TestCase):
    def identities(self):
        old = {'expected_model': 'openai/gpt-6.1-sol', 'expected_reasoning_effort': 'high',
            'rules': {'revision': 1}, 'schema_identity': 'schema1', 'prompt_identity': 'prompt1',
            'packages': {'tiktoken': 'fixed'}, 'python': {'executable': 'same'},
            'tools': {path: pair[0] for path, pair in recovery.HOST_REPAIR.items()}}
        old['tools']['scripts/python/_b_route_source_audit.py'] = 'sha256:' + 'a'*64
        new = deepcopy(old)
        for path, pair in recovery.HOST_REPAIR.items():
            new['tools'][path] = pair[1]
        return old, new

    def test_only_pinned_transport_change_is_compatible_and_inputs_are_unchanged(self):
        old, new = self.identities(); before = deepcopy((old, new))
        result = recovery.compatible_phase_identities(old, new)
        self.assertEqual(set(recovery.HOST_REPAIR), set(result['host_changes']))
        self.assertTrue(result['semantic_identity_unchanged'])
        self.assertEqual('unknown', result['provider_actual_reasoning'])
        self.assertEqual(before, (old, new))

    def test_semantic_environment_domain_low_and_unreviewed_code_changes_block(self):
        for mode in ['low', 'prompt', 'rules', 'packages', 'domain', 'unknown-code', 'wrong-host', 'python']:
            with self.subTest(mode=mode):
                old, new = self.identities()
                if mode == 'low': new['expected_reasoning_effort'] = 'low'
                elif mode == 'prompt': new['prompt_identity'] = 'changed'
                elif mode == 'rules': new['rules']['revision'] = 2
                elif mode == 'packages': new['packages']['tiktoken'] = 'other'
                elif mode == 'python': new['python']['executable'] = 'other'
                elif mode == 'domain': new['tools']['extra.py'] = 'other'
                elif mode == 'unknown-code': new['tools']['scripts/python/_b_route_source_audit.py'] = 'other'
                else: new['tools']['scripts/python/_codex_app_server.py'] = 'other'
                with self.assertRaises(ValueError):
                    recovery.compatible_phase_identities(old, new)

    def test_one_comparison_preserves_unknown_and_full_native_caps_at_exact_boundary(self):
        for actual, permitted, total, topup in [(0, True, 247, 7), (43, True, 290, 50),
                                                (44, False, 291, 51), (96, False, 343, 103)]:
            with self.subTest(actual=actual):
                plan = recovery.successor_budget(capability_actual=actual)
                self.assertEqual((permitted, total, topup),
                    (plan['full_mvg_fundable'], plan['full_mvg_campaign_ceiling'], plan['required_topup']))
                self.assertEqual((55, 96, 192), (plan['paid_or_unknown_after_ceiling'],
                    plan['native_capability_ceiling'], plan['native_mvg_ceiling']))
                self.assertFalse(plan['old_unknown_released'])
                self.assertFalse(plan['new_dispatch_authority'])

    def test_fallback_is_stricter_and_invalid_or_coerced_counts_are_rejected(self):
        self.assertTrue(recovery.successor_budget(new_requests=2, capability_actual=42)['full_mvg_fundable'])
        self.assertFalse(recovery.successor_budget(new_requests=2, capability_actual=43)['full_mvg_fundable'])
        for kwargs in [dict(new_requests=0), dict(new_requests=3), dict(new_requests=True),
                       dict(capability_actual=True), dict(capability_actual=-1), dict(capability_actual=97)]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                recovery.successor_budget(**kwargs)

    def test_v4_transition_preserves_actual_cross_root_paths_and_rejects_other_code(self):
        old, _ = self.identities()
        old['tools'].update(recovery.ORIGINAL_COORDINATOR)
        root = Path(recovery.__file__).resolve().parents[2]
        new = deepcopy(old); new['tools'] = {}
        for path,digest in old['tools'].items():
            if path in recovery.HOST_REPAIR:
                actual = recovery.HOST_REPAIR[path][1]
            elif path in recovery.ORIGINAL_COORDINATOR:
                actual = codec.raw_digest((root/path).read_bytes())
            else:
                actual = digest
            new['tools'][str(root/path)] = actual
        helper = 'scripts/python/_b_route_audit_recovery.py'
        new['tools'][str(root/helper)] = codec.raw_digest((root/helper).read_bytes())
        unchanged = 'scripts/python/unchanged-fixture.py'
        old['tools'][unchanged] = new['tools'][str(root/unchanged)] = 'sha256:'+'b'*64
        new['tools'][unchanged] = old['tools'][unchanged]
        runner='logs/ci/v4/runner/codex_isolated_model_runner.py'
        new['tools'][runner] = 'sha256:'+'c'*64
        result=recovery.coordinator_transition(old,new,runner_ref=runner)
        self.assertEqual(new['tools'],result['actual_current_tools'])
        for change in ['wrong-copy','extra-module','low']:
            bad=deepcopy(new)
            if change=='wrong-copy':bad['tools'][unchanged]='sha256:'+'d'*64
            elif change=='extra-module':bad['tools'][str(root/'scripts/python/unreviewed.py')]='sha256:'+'e'*64
            else:bad['expected_reasoning_effort']='low'
            with self.subTest(change=change),self.assertRaises(ValueError):
                recovery.coordinator_transition(old,bad,runner_ref=runner)
