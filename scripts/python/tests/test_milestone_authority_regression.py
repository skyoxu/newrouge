"""Regress master lifecycle precedence and event payload bindings."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/python'))
import milestone_incremental_handoff as m
import chapter5_semantic_reconciliation as c
from _chapter5_contract_bindings import resolve_contract


class AuthorityTests(unittest.TestCase):
    def test_done_master_overrides_pending_view_for_numeric_and_view_ids(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            taskdir = root / '.taskmaster/tasks'
            taskdir.mkdir(parents=True)
            (taskdir / 'tasks.json').write_text(json.dumps({'master': {'tasks': [{'id': 67, 'status': 'done'}]}}))
            (taskdir / 'tasks_gameplay.json').write_text(json.dumps([{'id': 'GM-0167', 'taskmaster_id': 67, 'status': 'pending'}]))
            for identity in ['67', 'GM-0167']:
                plan = {'schema_version': m.CHANGE_PLAN_SCHEMA, 'source_identity': {'source_revision': 'sim'}, 'changes': [{
                    'change_id': 'extend-shop', 'action': 'extend', 'target_task_id': identity, 'owner_task_id': identity,
                    'reason': 'New behavior', 'impact': {'tasks': [identity]}, 'verification': {'planned_tests': ['shop-filter']}}]}
                self.assertIn('extend-shop:done_target_requires_change_owner_or_explicit_reopen', m.validate_change_plan(root, plan))
                plan['changes'][0]['reopen_task'] = True
                self.assertEqual([], m.validate_change_plan(root, plan))

    def test_actual_shop_event_binds_payload_and_acceptance_only_ref(self):
        ref = 'core.shop.item.purchased'
        binding = resolve_contract(ROOT, ref)
        paths = {x['path'] for x in binding['bindings']}
        self.assertIn('Game.Core/Contracts/Events/ShopItemPurchasedEvent.cs', paths)
        self.assertIn('Game.Core/Contracts/EventTypes.cs', paths)
        scope = c.augment_authority_scope_from_acceptance_links(ROOT, {}, {'acceptance_links': [{'authority_refs': [ref]}]})
        self.assertEqual(binding, scope['contracts'][0])
        self.assertNotIn('Game.Core/Contracts/Events/ShopCurseRemovedEvent.cs', paths)


if __name__ == '__main__':
    unittest.main()
