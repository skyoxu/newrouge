"""Offline recovery contracts with independent, narrowly scoped fixtures."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _mvg_capability_recovery as recovery
import _mvg_global_audit as global_audit
from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json
from unittest.mock import patch


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
            state = {"run_id": "run", "checkpoint_strategy": recovery.CHECKPOINT_STRATEGY}
            recovery.bind_epoch(root, state)
            atomic_json(run / "run.json", state)
            pending = deepcopy(state)
            pending["capability_selection"] = {"selected": [{"checkpoint": "uncommitted"}]}
            with self.assertRaisesRegex(ValueError, "uncommitted_state"):
                recovery.register_committed(root, run, pending)
            self.assertEqual([], recovery.registry(root)["entries"])

    def test_verify_source_rejects_out_of_root_run_id_state_hash_and_cross_route(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            state = {"run_id": "current-run", "checkpoint_strategy": recovery.CHECKPOINT_STRATEGY}
            recovery.bind_epoch(root, state)

            def register_entry(entry):
                reg = recovery.registry(root, state)
                reg["entries"] = [entry]
                atomic_json(recovery.store_root(root, state) / "registry.json", reg)

            base_entry = {
                "epoch": 0,
                "transaction_id": "sha256:" + "a" * 64,
                "ancestry": ["sha256:" + "a" * 64],
                "order_index": 0,
                "checkpoint": {"transaction_id": "sha256:" + "a" * 64},
                "state_path": "completed-recovery/snap.json",
                "state_sha256": "sha256:" + "0" * 64,
            }

            outside = {**base_entry, "run_dir": str((root / "outside/run-1").resolve()), "run_id": "run-1"}
            register_entry(outside)
            with self.assertRaisesRegex(ValueError, "recovery_source_path_outside_canonical_root"):
                recovery.verify_source(root, state, outside)

            src_dir = root / "logs/ci/mvg-planning/run-a"
            atomic_json(src_dir / "run.json", {"run_id": "run-a"})
            mismatch = {**base_entry, "run_dir": str(src_dir), "run_id": "run-b"}
            register_entry(mismatch)
            with self.assertRaisesRegex(ValueError, "recovery_source_run_id_mismatch"):
                recovery.verify_source(root, state, mismatch)

            snap_path = src_dir / "completed-recovery/snap.json"
            atomic_json(snap_path, {
                "schema_version": "newrouge.b-route-planning-run.v1",
                "input_stage": "3b",
                "run_id": "run-a",
            })
            tampered_hash = {**base_entry, "run_dir": str(src_dir), "run_id": "run-a",
                "state_sha256": "sha256:" + "f" * 64}
            register_entry(tampered_hash)
            with self.assertRaisesRegex(ValueError, "recovery_source_state_changed"):
                recovery.verify_source(root, state, tampered_hash)

            cross_route = {**base_entry, "run_dir": str(src_dir), "run_id": "run-a",
                "state_sha256": file_sha(snap_path)}
            register_entry(cross_route)
            with self.assertRaisesRegex(ValueError, "recovery_source_route_incompatible"):
                recovery.verify_source(root, state, cross_route)

    def test_verify_adoption_record_and_active_chain_reject_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            run_dir = root / "logs/ci/mvg-planning/run-adopt"
            state = {
                "run_id": "run-adopt",
                "analysis_identity_sha256": "sha256:" + "1" * 64,
                "checkpoint_strategy": recovery.CHECKPOINT_STRATEGY,
            }
            recovery.bind_epoch(root, state)
            scope = {"capability_id": "CAP-a", "capability": {"capability_id": "CAP-a"}}
            base = {"seed": True}
            proposal = {"accepted": True}
            receipt_rel = "adoptions/receipt.json"
            receipt_path = run_dir / receipt_rel
            receipt = {
                "schema_version": recovery.ADOPTION,
                "run_id": "wrong-run",
                "analysis_identity_sha256": state["analysis_identity_sha256"],
                "epoch": 0,
                "capability_sha256": recovery.capability_hash(scope["capability"]),
                "base_sha256": canonical_sha(base),
                "result_sha256": canonical_sha(proposal),
                "source": {"transaction_id": "sha256:" + "b" * 64, "ancestry": [], "epoch": 0},
            }
            record = {"adoption": {"path": receipt_rel, "sha256": "sha256:" + "0" * 64}, "delta": {}}
            with self.assertRaisesRegex(ValueError, "adoption_receipt_changed"):
                recovery.verify_adoption_record(root, state, run_dir / "analysis-input", scope, base, proposal, record)

            atomic_json(receipt_path, receipt)
            with self.assertRaisesRegex(ValueError, "adoption_receipt_changed"):
                recovery.verify_adoption_record(root, state, run_dir / "analysis-input", scope, base, proposal, record)

            record["adoption"]["sha256"] = file_sha(receipt_path)
            with self.assertRaisesRegex(ValueError, "adoption_identity_changed"):
                recovery.verify_adoption_record(root, state, run_dir / "analysis-input", scope, base, proposal, record)

            state["capability_selection"] = {"selected": [{
                "kind": "adoption",
                "checkpoint": {"transaction_id": "sha256:" + "c" * 64},
                "receipt_path": receipt_rel,
                "receipt_sha256": "sha256:" + "0" * 64,
                "adoption": {"source_transaction_id": "sha256:" + "b" * 64},
            }]}
            with self.assertRaisesRegex(ValueError, "adoption_receipt_changed"):
                recovery.assert_active_chain(root, state, run_dir)

            state["capability_selection"]["selected"][0]["receipt_sha256"] = file_sha(receipt_path)
            state["capability_selection"]["selected"][0]["adoption"]["source_transaction_id"] = "sha256:" + "d" * 64
            with self.assertRaisesRegex(ValueError, "adoption_identity_changed"):
                recovery.assert_active_chain(root, state, run_dir)

    def test_verified_audit_accepts_blocked_receipt_with_unresolved_reopened_conflicts(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            run_dir = root / "logs/ci/mvg-planning/reopen-audit"
            plan_rel = "reopen-plans/plan.json"
            plan_path = run_dir / plan_rel
            plan = {
                "replacement_order": ["CAP-a"],
                "earliest_order_index": 0,
                "conflicts": [{"id": "hard-a"}],
                "conflict_resolution_boundaries": {"hard-a": 0},
            }
            atomic_json(plan_path, plan)
            plan_pointer = {"path": plan_rel, "sha256": file_sha(plan_path)}
            state = {
                "run_id": "reopen-audit",
                "global_audit": {"path": "global-audits/receipt.json", "sha256": ""},
                "reopen_history": [{"generation": 2, "plan": plan_pointer}],
                "capability_selection": {"order": ["CAP-a"], "selected": []},
            }
            unresolved_gap = {
                "code": "unresolved_reopened_conflicts",
                "plan": plan_pointer,
                "conflict_ids": ["hard-a"],
                "replacement_checkpoints": [],
                "gaps": [{"capability_id": "CAP-a", "reason": "replacement_not_selected"}],
            }
            receipt = {
                "schema_version": global_audit.AUDIT_SCHEMA,
                "binding": {},
                "conflict_report": None,
                "hard_conflicts": [],
                "resolved_reopened_conflicts": [],
                "evidence_gaps": [{"code": "selected_chain_incomplete"}, unresolved_gap],
                "runtime_verified": False,
                "status": "blocked",
                "complete_chain": False,
            }
            receipt_path = run_dir / state["global_audit"]["path"]
            atomic_json(receipt_path, receipt)
            state["global_audit"]["sha256"] = file_sha(receipt_path)
            proposal = {"manifest_candidate": {"flows": []}, "coverage_table": []}
            with patch.object(global_audit, "chain_identity", return_value={}):
                verified = global_audit.verified_audit(
                    root, run_dir, state, prefix=([{"capability_id": "CAP-a"}], proposal, []))
            self.assertEqual("blocked", verified["status"])
            self.assertFalse(verified["runtime_verified"])

            omitted = deepcopy(receipt)
            omitted["evidence_gaps"] = [{"code": "selected_chain_incomplete"}]
            atomic_json(receipt_path, omitted)
            state["global_audit"]["sha256"] = file_sha(receipt_path)
            with patch.object(global_audit, "chain_identity", return_value={}), \
                 self.assertRaisesRegex(ValueError, "reopen_resolutions_changed"):
                global_audit.verified_audit(
                    root, run_dir, state, prefix=([{"capability_id": "CAP-a"}], proposal, []))

            bad_runtime = deepcopy(receipt)
            bad_runtime["runtime_verified"] = True
            atomic_json(receipt_path, bad_runtime)
            state["global_audit"]["sha256"] = file_sha(receipt_path)
            with patch.object(global_audit, "chain_identity", return_value={}), \
                 self.assertRaisesRegex(ValueError, "planned_obligations_changed"):
                global_audit.verified_audit(
                    root, run_dir, state, prefix=([{"capability_id": "CAP-a"}], proposal, []))


if __name__ == "__main__":
    unittest.main()
