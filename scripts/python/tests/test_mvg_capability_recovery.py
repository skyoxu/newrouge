"""Offline recovery contracts with independent, narrowly scoped fixtures."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _mvg_capability_recovery as recovery
from _planning_skill_common import atomic_json, load_json


class RecoveryIdentityTests(unittest.TestCase):
    def test_full_individual_content_key_preserves_types_values_and_array_order(self):
        original = {"capability_id": "CAP-a", "nested": {"z": 1, "a": True}, "order": [1, 2], "text": "a b"}
        reordered = {"text": "a b", "order": [1, 2], "nested": {"a": True, "z": 1}, "capability_id": "CAP-a"}
        self.assertEqual(recovery.capability_hash(original), recovery.capability_hash(reordered))
        for key, value in (("order", [2, 1]), ("text", "a  b"), ("nested", {"z": "1", "a": True}),
                           ("nested", {"z": 1, "a": 1})):
            with self.subTest(key=key, value=value):
                self.assertNotEqual(recovery.capability_hash(original),
                                    recovery.capability_hash({**original, key: value}))

    def test_epoch_clear_survives_restart_and_rejects_late_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state = {"run_id": "old"}
            recovery.bind_epoch(root, state)
            audit = root / "logs/ci/mvg-planning/old/audit.json"
            atomic_json(audit, {"charges": 7})
            self.assertEqual(0, state["recovery"]["epoch"])
            result = recovery.clear(root)
            self.assertEqual(0, result["completed"])
            self.assertEqual(1, recovery.registry(root)["epoch"])
            self.assertEqual([], recovery.registry(root)["entries"])
            self.assertEqual({"charges": 7}, load_json(audit))
            with self.assertRaisesRegex(ValueError, "epoch_invalidated"):
                recovery.assert_epoch(root, state)
            fresh = {"run_id": "fresh"}
            recovery.bind_epoch(root, fresh)
            self.assertEqual(1, fresh["recovery"]["epoch"])

    def test_revocation_invalidates_descendants_in_current_epoch_after_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            root, state = Path(folder), {"run_id": "run"}
            recovery.bind_epoch(root, state)
            value = recovery.registry(root)
            value["entries"] = [
                {"transaction_id": "a", "ancestry": ["a"], "epoch": 0},
                {"transaction_id": "b", "ancestry": ["a", "b"], "epoch": 0},
                {"transaction_id": "c", "ancestry": ["b", "c"], "epoch": 0}]
            atomic_json(recovery.store_root(root) / "registry.json", value)
            recovery.revoke(root, state, ["a"])
            self.assertEqual(["a", "b", "c"], recovery.registry(root)["revoked"])
            for entry in value["entries"]:
                with self.assertRaisesRegex(ValueError, "source_revoked"):
                    recovery._eligible(root, state, entry)

    def test_uncommitted_state_cannot_enter_registry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run = root / "logs/ci/mvg-planning/run"
            state = {"run_id": "run"}
            recovery.bind_epoch(root, state)
            atomic_json(run / "run.json", state)
            pending = deepcopy(state)
            pending["capability_selection"] = {"selected": [{"checkpoint": "uncommitted"}]}
            with self.assertRaisesRegex(ValueError, "uncommitted_state"):
                recovery.register_committed(root, run, pending)
            self.assertEqual([], recovery.registry(root)["entries"])


if __name__ == "__main__":
    unittest.main()
