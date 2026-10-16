"""Read retained real-worker evidence and exercise isolated machine recovery guards.

Run explicitly with --completed-fixture and --changed-fixture. This is an
acceptance evidence consumer, not a test-discovery dependency on local logs.
"""
from copy import deepcopy
from pathlib import Path
import argparse
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import _mvg_capability_recovery as recovery
import _mvg_global_audit as audit
import _mvg_capability_selection as selection
import plan_mvg as pm
from _mvg_capability_checkpoint import load_checkpoint
from _mvg_capability_generation import seed_proposal
from _mvg_capability_selection import frozen_scopes
from _planning_skill_common import atomic_json, file_sha, load_json
from scripts.python.tests import test_mvg_global_audit as audit_fixture


class RetainedRecoveryTests(unittest.TestCase):
    completed_fixture: Path
    changed_fixture: Path
    reopen_faults = ("before", "after", "before_revoke", "after_revoke")

    def test_adopted_reopen_history_and_same_plan_transaction_recovery(self):
        for failure in self.reopen_faults:
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "project"
                shutil.copytree(self.completed_fixture, root)
                run = root / "logs/ci/mvg-planning/reused"
                state = load_json(run / "run.json")
                state["recovery"]["store"] = str(root / "logs/ci/mvg-recovery")
                state.pop("applied", None)
                (run / "apply-journal.json").unlink()
                shutil.copyfile(run / "analysis-input/existing-manifest.json", root / state["manifest_path"])
                atomic_json(run / "run.json", state)
                report = audit_fixture.GlobalAuditTests().report(run, capability="CAP-7", flow="journey-7")
                report_path = root / "logs/conflict.json"
                atomic_json(report_path, report)
                receipt = audit.operate(root, run_id="reused", operation="audit",
                    conflict_report=str(report_path), conflict_report_sha256=file_sha(report_path))
                plan = audit.operate(root, run_id="reused", operation="reopen-plan",
                    audit_path=receipt["path"], audit_sha256=receipt["sha256"])
                args = {"plan_path": plan["path"], "plan_sha256": plan["sha256"]}
                before = load_json(run / "run.json")
                def writer(path, value):
                    if failure == "after":
                        atomic_json(path, value)
                    raise OSError("fixture_commit_failure")
                real_revoke = recovery.revoke
                def failed_revoke(*args, **kwargs):
                    if failure == "after_revoke":
                        real_revoke(*args, **kwargs)
                    raise OSError("fixture_revoke_failure")
                with patch.object(pm, "run_isolated_model") as model:
                    with self.assertRaisesRegex(OSError, "fixture_"):
                        if failure in {"before_revoke", "after_revoke"}:
                            with patch.object(recovery, "revoke", side_effect=failed_revoke):
                                audit.operate(root, run_id="reused", operation="reopen", **args)
                        else:
                            audit.operate(root, run_id="reused", operation="reopen", writer=writer, **args)
                    transactions = list((run / "reopen-transactions").glob("*.json"))
                    self.assertEqual(1, len(transactions), "Reopen intent must survive every commit fault")
                    if failure != "after":
                        self.assertEqual(before, load_json(run / "run.json"))
                    with self.assertRaisesRegex(ValueError, "pending_reopen_same_plan_recovery_required"):
                        pm._load_run(root, "reused")
                    with self.assertRaises(ValueError):
                        audit.operate(root, run_id="reused", operation="reopen",
                            plan_path=args["plan_path"], plan_sha256="sha256:wrong")
                    result = audit.operate(root, run_id="reused", operation="reopen", **args)
                    self.assertEqual("reopened", result["status"])
                    pending = load_json(run / "run.json")
                    selection.verified_prefix(root, run, pending)
                    self.assertEqual([], pending["capability_selection"]["selected"])
                    revoked = recovery.registry(root, pending)["revoked"]
                    for step in before["capability_selection"]["selected"]:
                        self.assertIn(step["adoption"]["source_transaction_id"], revoked)
                    self.assertEqual(result, audit.operate(root, run_id="reused", operation="reopen", **args))
                    self.assertEqual(before["capability_selection"].get("calls", []),
                        pending["capability_selection"].get("calls", []))
                    pm._load_run(root, "reused")
                    model.assert_not_called()

    def test_current_delta_conflict_never_advances_and_adoption_revocation_cascades(self):
        source_root = self.completed_fixture
        original = source_root / "logs/ci/mvg-planning/original"
        source_registry = load_json(source_root / "logs/ci/mvg-recovery/registry.json")
        reused = source_root / "logs/ci/mvg-planning/reused"
        state = load_json(reused / "run.json")
        scope = frozen_scopes(state, reused / "analysis-input")[0]
        source_entry = next(entry for entry in source_registry["entries"]
            if entry["capability_id"] == scope["capability_id"])
        payload = load_checkpoint(original, source_entry["checkpoint"])
        before_source = {path: file_sha(path) for path in source_root.rglob("*.json")}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "logs/ci/mvg-planning/reused"
            shutil.copytree(reused / "analysis-input", run / "analysis-input")
            pending = deepcopy(state)
            pending["recovery"]["store"] = str(root / "isolated-registry")
            atomic_json(recovery.store_root(root, pending) / "registry.json", source_registry)
            atomic_json(run / "run.json", pending)
            committed_before = (run / "run.json").read_bytes()
            base = seed_proposal(pending, run / "analysis-input")
            # Current accepted authority already owns this Requirement with a
            # different binding. Replaying the old delta cannot overwrite it.
            conflict = deepcopy(payload["delta"]["requirement_verification"][0])
            conflict["rationale"] = "Current accepted conflicting authority"
            base["requirement_verification"].append(conflict)
            with patch("plan_mvg.run_isolated_model") as model:
                adopted = recovery.try_adopt(root, run, pending, scope, 0, base)
                self.assertIsNone(adopted)
                model.assert_not_called()
            lookup = load_json(run / "recovery-lookups/scope-1.json")
            self.assertEqual("generate_fresh", lookup["status"])
            self.assertTrue(any("append_requirement_verification_outside_new_scope" in row["reason"]
                for row in lookup["failures"]), lookup)
            self.assertEqual(committed_before, (run / "run.json").read_bytes())
            self.assertEqual(state["capability_selection"]["selected"],
                pending["capability_selection"]["selected"])
            self.assertFalse((run / "adoptions").exists())

            # Use the actual interrupted/adopted/fresh-successor registry before
            # its clear. The successor ancestry includes the adoption and source.
            changed = self.changed_fixture
            before_clear = load_json(changed / "logs/ci/mvg-recovery/clears/epoch-0.json")
            next_run = changed / "logs/ci/mvg-planning/next"
            chain = load_json(next_run / "run.json")
            chain["recovery"]["store"] = pending["recovery"]["store"]
            atomic_json(recovery.store_root(root, chain) / "registry.json", before_clear)
            steps = chain["capability_selection"]["selected"]
            adopted_step, successor = steps
            self.assertEqual("adoption", adopted_step["kind"])
            source_transaction = adopted_step["adoption"]["source_transaction_id"]
            adoption_transaction = adopted_step["checkpoint"]["transaction_id"]
            successor_transaction = successor["checkpoint"]["transaction_id"]
            recovery.revoke(root, chain, [adoption_transaction, source_transaction])
            after_restart = recovery.registry(root, chain)
            self.assertTrue({source_transaction, adoption_transaction, successor_transaction}
                <= set(after_restart["revoked"]))
            for entry in before_clear["entries"]:
                if {source_transaction, adoption_transaction} & set(entry["ancestry"]):
                    with self.assertRaisesRegex(ValueError, "recovery_source_revoked"):
                        recovery._eligible(root, chain, entry)
            with self.assertRaisesRegex(ValueError, "recovery_source_revoked"):
                recovery.assert_active_chain(root, chain, next_run)
        self.assertEqual(before_source, {path: file_sha(path) for path in source_root.rglob("*.json")})

    def test_changed_individual_content_has_fresh_real_workers_and_unchanged_item_adopts(self):
        root = self.changed_fixture
        old_run = root / "logs/ci/mvg-planning/interrupted"
        next_run = root / "logs/ci/mvg-planning/next"
        old_caps = load_json(old_run / "analysis-input/capabilities.v1.json")["capabilities"]
        new_caps = load_json(next_run / "analysis-input/capabilities.v1.json")["capabilities"]
        self.assertEqual(recovery.capability_hash(old_caps[0]), recovery.capability_hash(new_caps[0]))
        self.assertNotEqual(recovery.capability_hash(old_caps[1]), recovery.capability_hash(new_caps[1]))
        state = load_json(next_run / "run.json")
        steps = state["capability_selection"]["selected"]
        self.assertEqual("adoption", steps[0]["kind"])
        self.assertNotIn("kind", steps[1])
        workers = list(next_run.rglob("process.json"))
        self.assertEqual(3, len(workers))
        self.assertEqual(3, len({load_json(path)["pid"] for path in workers}))
        for label, admission in steps[1]["admissions"].items():
            self.assertEqual("admitted", admission["status"])
            candidate = next_run / admission["workspace"]
            job = load_json(candidate / "lifecycle/job.json")
            self.assertEqual(1, job["input"]["scope_index"])
            self.assertEqual(new_caps[1]["capability_id"],
                job["input"]["state"]["capability_selection"]["order"][1])
            self.assertEqual(new_caps[1],
                load_json(candidate / "analysis-input/capabilities.v1.json")["capabilities"][1])
        self.assertEqual(7, state["capability_selection"]["total_invocations"])
        self.assertEqual(9, load_json(old_run / "run.json")["capability_selection"]["total_invocations"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--completed-fixture", type=Path, required=True)
    parser.add_argument("--changed-fixture", type=Path, required=True)
    parser.add_argument("--reopen-fault", choices=RetainedRecoveryTests.reopen_faults)
    args = parser.parse_args()
    RetainedRecoveryTests.completed_fixture = args.completed_fixture.resolve(strict=True)
    RetainedRecoveryTests.changed_fixture = args.changed_fixture.resolve(strict=True)
    if args.reopen_fault:
        RetainedRecoveryTests.reopen_faults = (args.reopen_fault,)
    unittest.main(argv=[sys.argv[0], "-v"])
