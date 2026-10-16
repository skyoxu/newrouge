"""Discovered, self-contained offline recovery/reopen tests for ADR-0039."""
from copy import deepcopy
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import _mvg_capability_recovery as recovery
import _mvg_capability_selection as selection
import _mvg_capability_worker as worker
import _mvg_global_audit as audit
import plan_mvg as pm
from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json
from scripts.python.tests import test_mvg_capability_worker as fixture
from scripts.python.tests import test_mvg_global_audit as audit_fixture


def reopen(root, run, index):
    state = load_json(run / "run.json")
    scope = selection.frozen_scopes(state, run / "analysis-input")[index]
    cid = scope["capability_id"]
    flow = next(row for row in load_json(run / "proposal.json")["manifest_candidate"]["flows"]
                if cid in row["capability_refs"])
    report = audit_fixture.GlobalAuditTests().report(run, capability=cid, flow=flow["id"])
    report_path = root / "logs/conflict.json"
    atomic_json(report_path, report)
    receipt = audit.operate(root, run_id=state["run_id"], operation="audit",
        conflict_report=str(report_path), conflict_report_sha256=file_sha(report_path))
    plan = audit.operate(root, run_id=state["run_id"], operation="reopen-plan",
        audit_path=receipt["path"], audit_sha256=receipt["sha256"])
    audit.operate(root, run_id=state["run_id"], operation="reopen",
        plan_path=plan["path"], plan_sha256=plan["sha256"])
    return load_json(run / "run.json")


class RecoveryReviewIntegrationTests(unittest.TestCase):
    def test_same_run_restarts_unfinished_scope_and_projects_retained_reopened_prefix(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                "SC_KNOWLEDGE_PLANNING_RUNNER": str(fixture.RUNNER.resolve())}):
            root = Path(directory)
            refs = fixture.build_project(root)
            fixture.prepare(root, "resume", refs)
            run = root / "logs/ci/mvg-planning/resume"
            real_worker = worker.run_candidate
            def interrupted(job_dir, data, **kwargs):
                result = real_worker(job_dir, data, **kwargs)
                if data["scope_index"] == 1:
                    raise KeyboardInterrupt("Offline interruption after admitted unfinished candidate")
                return result
            with patch.object(worker, "run_candidate", side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
                pm.generate(root, run_id="resume", timeout_sec=10, llm_backend="codex-cli")
            before = load_json(run / "run.json")
            self.assertEqual(9, before["capability_selection"]["total_invocations"])
            old_ledger = run / "candidates/candidate-1/scope-2/capability-append/append-ledger.json"
            old_bytes = old_ledger.read_bytes()
            pm.generate(root, run_id="resume", timeout_sec=10, llm_backend="codex-cli")
            completed = load_json(run / "run.json")
            self.assertEqual(2, len(completed["capability_selection"]["selected"]))
            self.assertEqual(16, completed["capability_selection"]["total_invocations"])
            self.assertEqual(before["capability_selection"]["calls"], completed["capability_selection"]["calls"][:9])
            self.assertEqual(old_bytes, old_ledger.read_bytes(), "Old model evidence is immutable audit")
            for admission in completed["capability_selection"]["selected"][1]["admissions"].values():
                self.assertEqual(2, admission["execution"])
                self.assertIn("execution-2", admission["workspace"])
            scopes = selection.frozen_scopes(completed, run / "analysis-input")
            seed = selection.seed_proposal(completed, run / "analysis-input")
            entry = recovery.registry(root)["entries"][0]
            with patch.object(pm, "run_isolated_model", side_effect=AssertionError("Replay cannot dispatch")):
                recovery.replay(root, run, completed, scopes[0], seed, entry)
                changed_seed = deepcopy(seed)
                handoff = deepcopy(changed_seed["manifest_candidate"]["flows"][0]["handoffs"][0])
                handoff["behavior"] = "Reset consumer state before observing outcome"
                changed_seed["manifest_candidate"]["flows"][0]["handoffs"].append(handoff)
                with self.assertRaisesRegex(ValueError, "current_dependencies_incompatible"):
                    recovery.replay(root, run, completed, scopes[0], changed_seed, entry)
            reopened = reopen(root, run, 1)
            before_reads = {p: file_sha(p) for p in run.rglob("*.json")}
            with patch.object(pm, "run_isolated_model", side_effect=AssertionError("Progress cannot dispatch")):
                projected = recovery.progress(root, run, reopened)
            self.assertEqual(before_reads, {p: file_sha(p) for p in run.rglob("*.json")})
            self.assertEqual(1, projected["completed"])
            self.assertFalse(projected["runtime_verified"])
            self.assertEqual(16, load_json(run / "run.json")["capability_selection"]["total_invocations"])

    def test_adopted_reopen_revokes_original_source_and_successors_after_reload(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
                "SC_KNOWLEDGE_PLANNING_RUNNER": str(fixture.RUNNER.resolve())}):
            root = Path(directory)
            refs = fixture.build_project(root)
            fixture.prepare(root, "source", refs)
            pm.generate(root, run_id="source", timeout_sec=10, llm_backend="codex-cli")
            source = root / "logs/ci/mvg-planning/source"
            original = load_json(source / "run.json")
            tokens = [row["checkpoint"]["transaction_id"] for row in original["capability_selection"]["selected"]]
            fixture.prepare(root, "adopted", refs, run_invocation_limit=1)
            with patch.object(pm, "run_isolated_model", side_effect=AssertionError("Reuse cannot dispatch")):
                pm.generate(root, run_id="adopted", timeout_sec=10, llm_backend="codex-cli")
            run = root / "logs/ci/mvg-planning/adopted"
            adopted = load_json(run / "run.json")
            self.assertEqual(["adoption", "adoption"], [row["kind"] for row in adopted["capability_selection"]["selected"]])
            self.assertEqual(0, adopted["capability_selection"]["total_invocations"])
            entries = deepcopy(recovery.registry(root)["entries"])
            reopened = reopen(root, run, 0)
            revoked = recovery.registry(root)["revoked"]
            self.assertTrue(set(tokens) <= set(revoked), "Actual adopted reopen must revoke original sources and descendants")
            fixture.prepare(root, "next", refs)
            next_run = root / "logs/ci/mvg-planning/next"
            next_state = load_json(next_run / "run.json")
            scopes = selection.frozen_scopes(next_state, next_run / "analysis-input")
            base = selection.seed_proposal(next_state, next_run / "analysis-input")
            with patch.object(pm, "run_isolated_model", side_effect=AssertionError("Lookup cannot dispatch")):
                for index, scope in enumerate(scopes):
                    self.assertIsNone(recovery.try_adopt(root, next_run, next_state, scope, index, base))
                for entry in entries:
                    with self.assertRaisesRegex(ValueError, "source_revoked"):
                        recovery._eligible(root, next_state, entry)
            self.assertEqual([], reopened["capability_selection"]["selected"])
            self.assertEqual(canonical_sha(original), canonical_sha(load_json(source / "run.json")))


if __name__ == "__main__":
    unittest.main()
