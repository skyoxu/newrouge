"""Regression tests for production planning boundaries and interrupted apply."""
from __future__ import annotations

import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plan_capabilities as cap
import plan_mvg as mvg
from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json
from planning_acceptance_fixture import build_fixture, GDD_PATH, CONTRACT_PATH
from chapter5_semantic_reconciliation import load_task_readiness

GDD_PATH = GDD_PATH.as_posix()
CONTRACT_PATH = CONTRACT_PATH.as_posix()


def prepare_cap(root, tasks=("7", "42")):
    return cap.prepare(root, run_id="repair", task_ids=list(tasks), allow_unready=False,
        source_manifest=root / "logs/ci/task-generation/source-manifest.v1.json",
        ledger=root / "logs/ci/task-generation/source-blocks.v1.json",
        semantics=root / "logs/ci/task-generation/semantic-requirements.v1.json",
        model_batch_char_budget=12000, candidate_retry_limit=1, review_retry_limit=1,
        candidate_budget_sec=1800, total_budget_sec=7200, request_limit=50)


def selected_cap(root):
    state = prepare_cap(root)
    run = root / "logs/ci/capability-planning/repair"
    ledger = load_json(run / "analysis-input/source-blocks.v1.json")
    semantics = load_json(run / "analysis-input/semantic-requirements.v1.json")
    caps = [{"capability_id": f"TMP-CAP-{i}", "title": f"Relay {i}",
        "description": req["statement"], "boundary_rationale": "Distinct source obligation.",
        "requirement_ids": [req["requirement_id"]], "source_block_ids": req["source_block_ids"]}
        for i, req in enumerate(semantics["requirements"], 1)]
    candidate = {"schema_version": cap.CANDIDATE_SCHEMA,
        "analysis_identity_sha256": state["analysis_identity_sha256"], "capabilities": caps,
        "ungrouped_requirements": [], "questions": [], "generation_notes": [],
        "source_accounting": [{"block_id": b["block_id"],
            "disposition": "capability" if any(b["block_id"] in c["source_block_ids"] for c in caps) else "context",
            "capability_ids": [c["capability_id"] for c in caps if b["block_id"] in c["source_block_ids"]],
            "rationale": "Source obligation or heading context."} for b in ledger["blocks"]]}
    atomic_json(run / "candidates/candidate-1.json", candidate)
    atomic_json(run / "review/review.json", {"schema_version": cap.REVIEW_SCHEMA, "corrections": []})
    state.update(phase="reviewed", review_status="selected", selected_candidate="candidate-1")
    atomic_json(run / "run.json", state)
    return run


def prepared_mvg(root):
    selected_cap(root)
    cap.apply(root, run_id="repair", alignment_override=None, confirm=True)
    dest = root / "docs/testing/mvg/repair.json"
    state = mvg.prepare(root, run_id="repair", capabilities_path=root / cap.FORMAL_CAPABILITIES,
        task_ids=["7", "42"], manifest_path=dest, allow_unready=False)
    caps = load_json(root / cap.FORMAL_CAPABILITIES)["capabilities"]
    reqs = [c["requirement_ids"][0] for c in caps]
    proposal = {"schema_version": mvg.PROPOSAL_SCHEMA,
        "analysis_identity_sha256": state["analysis_identity_sha256"],
        "planning_status": "ready_for_validation", "gaps": [],
        "manifest_candidate": {"schema_version": "newrouge.mvg-integration.v1", "mvg_id": "repair",
            "coverage": {"mode": "pilot", "scope_id": "relay", "required_flow_ids": ["relay-delivery"],
                "blocking_task_ids": [], "excluded_claims": ["Runtime experience"]},
            "flows": [{"id": "relay-delivery", "outcome": "Cargo arrives or retry is visible",
                "task_ids": [7, 42], "source_paths": [GDD_PATH], "requirement_ids": reqs,
                "capability_refs": [c["capability_id"] for c in caps], "test_ids": ["relay-contract"],
                "handoffs": [{"producer_task": 7, "consumer_task": 42, "owner_task": 42,
                    "contract_ref": CONTRACT_PATH, "behavior": "Deliver or retry", "test_ids": ["relay-contract"]}]}],
            "tests": [{"id": "relay-contract", "kind": "dotnet", "state": "planned",
                "path": "Game.Core.Tests/Tasks/RelayTests.cs", "selector": "RelayTests",
                "evidence_level": "domain-integration", "min_tests": 1}]},
        "coverage_table": [{"requirement_id": rid, "capability_ref": caps[i]["capability_id"],
            "task_id": tid, "flow_id": "relay-delivery", "coverage": "Launch or resolve relay"}
            for i, (rid, tid) in enumerate(zip(reqs, (7, 42)))],
        "entrypoints": [{"status": "planned", "owner_task": tid, "path": f"Game.Core/Tasks/Relay{tid}.cs",
            "symbol": f"Relay{tid}.Run", "inputs": ["route"], "state": "cargo transfer",
            "assertions": ["accepted or retry visible"], "implementation_acceptance": ["relay journey"]}
            for tid in (7, 42)]}
    run = root / "logs/ci/mvg-planning/repair"
    atomic_json(run / "proposal.json", proposal)
    # Reviewed fixture evidence tests deterministic consumers; no model execution is claimed.
    atomic_json(run / "semantic-review.json", {"schema_version": "newrouge.mvg-semantic-review.v1",
        "analysis_identity_sha256": state["analysis_identity_sha256"], "proposal_sha256": canonical_sha(proposal),
        "verdict": "approved", "findings": [], "requirement_reviews": [
            {"requirement_id": rid, "verdict": "covered", "rationale": "Relay launch and delivery remain observable."}
            for rid in reqs], "flow_reviews": [{"flow_id": "relay-delivery", "verdict": "sound",
                "rationale": "Real contract connects both tasks; planned tests claim no runtime pass."}]})
    atomic_json(run / "semantic-review-execution.json", {
        "analysis_identity_sha256": state["analysis_identity_sha256"], "proposal_sha256": canonical_sha(proposal),
        "runner_info": {"schema_version": "newrouge.isolated-model-runner.v1", "model": "fixture-reviewer",
            "fresh_session_per_invocation": True, "filesystem_scope": "workspace_only",
            "can_read_outside_workspace": False, "model_tools": []},
        "receipt": {"model": "fixture-reviewer", "model_tools": []}})
    return state, proposal, dest


def milestone_plan(root, proposal, dest):
    ledger = load_json(root / "logs/ci/task-generation/source-blocks.v1.json")
    semantics = load_json(root / "logs/ci/task-generation/semantic-requirements.v1.json")
    by_block = {bid: [r["requirement_id"] for r in semantics["requirements"] if bid in r["source_block_ids"]]
        for bid in [b["block_id"] for b in ledger["blocks"]]}
    test_ids = [t["id"] for t in proposal["manifest_candidate"]["tests"]]
    plan = {"schema_version": "newrouge.milestone-change-plan.v1",
        "source_identity": {"source_revision": ledger["source_revision"]},
        "baseline_manifest": dest.relative_to(root).as_posix(),
        "source_block_reviews": [{"block_id": b["block_id"], "content_hash": b["content_hash"],
            "disposition": "requirement" if by_block[b["block_id"]] else "context",
            "requirement_ids": by_block[b["block_id"]], "reason": "Source coverage reviewed.",
            "non_delivery_rationale": "Heading context."} for b in ledger["blocks"]],
        "changes": [{"change_id": f"relay-{tid}", "action": "reuse", "target_task_id": str(tid),
            "owner_task_id": str(tid), "reason": "Owns milestone integration acceptance.",
            "requirement_ids": [proposal["coverage_table"][i]["requirement_id"]],
            "impact": {"tasks": ["7", "42"], "contracts": [CONTRACT_PATH]},
            "verification": {"required_regressions": test_ids, "planned_tests": test_ids}}
            for i, tid in enumerate((7, 42))]}
    path = root / "docs/planning/milestones/relay.json"
    atomic_json(path, plan)
    return path


class PlanningAuditRepairTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "fixture"
        build_fixture(self.root)

    def test_crlf_workspace_uses_ledger_text_hash_and_detects_real_edit(self):
        from _semantic_topology import _validate_source_hashes
        from _knowledge_catalog_builder import DirectorySnapshot
        ledger = load_json(self.root / "logs/ci/task-generation/source-blocks.v1.json")
        path = self.root / GDD_PATH
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        problems = []
        _validate_source_hashes(DirectorySnapshot(self.root, [GDD_PATH]), ledger["blocks"], problems)
        self.assertEqual([], problems)
        path.write_bytes(path.read_bytes() + b"changed\r\n")
        _validate_source_hashes(DirectorySnapshot(self.root, [GDD_PATH]), ledger["blocks"], problems)
        self.assertTrue(problems)

    def test_partial_round_cannot_hide_second_task(self):
        with self.assertRaisesRegex(ValueError, "scope|round"):
            prepare_cap(self.root, ("7",))

    def test_mvg_prepare_also_checks_complete_round(self):
        selected_cap(self.root)
        cap.apply(self.root, run_id="repair", alignment_override=None, confirm=True)
        with self.assertRaisesRegex(ValueError, "scope|readiness"):
            mvg.prepare(self.root, run_id="partial", capabilities_path=self.root / cap.FORMAL_CAPABILITIES,
                task_ids=["7"], manifest_path=self.root / "docs/testing/mvg/partial.json", allow_unready=False)

    def test_round_scope_allows_non_task_sink_and_ignores_unrelated_historical_source(self):
        from _planning_scope import round_scope
        ledger_path = self.root / "logs/ci/task-generation/source-blocks.v1.json"
        semantics_path = self.root / "logs/ci/task-generation/semantic-requirements.v1.json"
        semantics = load_json(semantics_path)
        rid = semantics["requirements"][1]["requirement_id"]
        semantics["requirements"][1]["non_task_sinks"] = [{"type": "quality_gate", "id": "relay-audit"}]
        semantics["requirements"].append({"requirement_id": "RQ-OLD", "status": "active",
            "delivery_relevant": True, "source_block_ids": ["SB-OLD"]})
        atomic_json(semantics_path, semantics)
        ledger = load_json(ledger_path)
        ledger["blocks"].append({"block_id": "SB-OLD", "source_path": "docs/gdd/old.md"})
        atomic_json(ledger_path, ledger)
        path = self.root / cap.TASK_VIEWS[1]
        rows = load_json(path)
        for row in rows:
            row["semantic_refs"] = [r for r in row.get("semantic_refs", row.get("requirement_ids", [])) if r != rid]
        rows.append({"taskmaster_id": 99, "semantic_refs": ["RQ-OLD"]})
        atomic_json(path, rows)
        scope = round_scope(self.root, ["7"], ledger_path, semantics_path)
        self.assertEqual([], scope["errors"])
        self.assertEqual(["7"], scope["required_task_ids"])
        self.assertEqual("relay-audit", scope["non_task_sinks"][0]["id"])

    def test_empty_mvg_accounting_and_entrypoints_block(self):
        state, proposal, _ = prepared_mvg(self.root)
        proposal["coverage_table"] = []
        proposal["entrypoints"] = []
        for flow in proposal["manifest_candidate"]["flows"]:
            flow["requirement_ids"] = []
            flow["capability_refs"] = []
        result = mvg.validate_proposal(self.root, state, proposal)
        self.assertFalse(result["formal_applicable"])

    def test_stale_source_blocks_before_manifest_write(self):
        _, _, dest = prepared_mvg(self.root)
        path = self.root / GDD_PATH
        path.write_text(path.read_text() + "\nNew retry obligation.\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "drift|changed|stale"):
            mvg.apply(self.root, run_id="repair", confirm=True)
        self.assertFalse(dest.exists())

    def test_other_authority_and_new_manifest_drift_block_before_write(self):
        paths = [".taskmaster/tasks/tasks.json", cap.TASK_VIEWS[1].as_posix(), CONTRACT_PATH,
            "Game.Core.Tests/Tasks/PlanningAcceptanceTests.cs", "logs/ci/task-generation/semantic-requirements.v1.json",
            "logs/ci/chapter5/readiness/task-7.json", "docs/testing/mvg/repair.json"]
        for i, rel in enumerate(paths):
            with self.subTest(path=rel):
                root = Path(self.temp.name) / f"drift-{i}"
                build_fixture(root)
                _, _, dest = prepared_mvg(root)
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((target.read_bytes() if target.is_file() else b"{}") + b"\n")
                original = target.read_bytes()
                with self.assertRaisesRegex(ValueError, "drift"):
                    mvg.apply(root, run_id="repair", confirm=True)
                self.assertEqual(original, target.read_bytes())
                if target != dest:
                    self.assertFalse(dest.exists())

    def test_missing_or_stale_independent_review_cannot_apply(self):
        _, proposal, dest = prepared_mvg(self.root)
        review_path = self.root / "logs/ci/mvg-planning/repair/semantic-review.json"
        review = load_json(review_path)
        review_path.unlink()
        self.assertFalse(mvg.validate(self.root, run_id="repair")["formal_applicable"])
        review["proposal_sha256"] = "sha256:old"
        atomic_json(review_path, review)
        self.assertFalse(mvg.validate(self.root, run_id="repair")["formal_applicable"])
        with self.assertRaisesRegex(ValueError, "formally applicable"):
            mvg.apply(self.root, run_id="repair", confirm=True)
        self.assertFalse(dest.exists())

    def test_coverage_rejects_false_capability_membership(self):
        state, proposal, _ = prepared_mvg(self.root)
        proposal["coverage_table"][0]["capability_ref"] = proposal["coverage_table"][1]["capability_ref"]
        self.assertIn("coverage_flow_membership_invalid:" + proposal["coverage_table"][0]["requirement_id"],
            mvg.validate_proposal(self.root, state, proposal)["errors"])

    def test_pending_mvg_obligations_block_chapter6_route(self):
        from chapter6_route import route_chapter6
        prepared_mvg(self.root)
        mvg.apply(self.root, run_id="repair", confirm=True)
        with patch("chapter6_route.build_resume_payload", return_value=(0, {
            "run_id": "existing-valid-run", "inspection": {}, "candidate_commands": {}})):
            rc, route = route_chapter6(repo_root=self.root, task_id="7")
        self.assertNotEqual(0, rc)
        self.assertFalse(route.get("execution_allowed"))
        self.assertEqual("mvg_obligations", route.get("blocked_by"))

    def test_single_task_lane_cannot_omit_milestone_flag_to_bypass_guard(self):
        import run_single_task_chapter6_lane as lane
        prepared_mvg(self.root)
        mvg.apply(self.root, run_id="repair", confirm=True)
        out = self.root / "logs/ci/lane-probe"
        with patch.object(lane, "_repo_root", return_value=self.root), patch.object(sys, "argv", [
            "lane", "--task-id", "7", "--godot-bin", "fixture-godot", "--self-check", "--out-dir", str(out)]):
            self.assertEqual(2, lane.main())
        self.assertEqual("mvg_obligations", load_json(out / "summary.json")["blocked_by"])

    def test_ordinary_binding_and_real_milestone_handoff_open_then_drift_closes_gate(self):
        from _mvg_obligations import check_task_obligations
        from milestone_incremental_handoff import validate_task_handoff
        _, proposal, dest = prepared_mvg(self.root)
        mvg.apply(self.root, run_id="repair", confirm=True)
        mvg.rebind_handoff(self.root, run_id="repair", task_id="7", change_plan_path=None, out_path=None)
        self.assertTrue(check_task_obligations(self.root, "7")[0])
        plan = milestone_plan(self.root, proposal, dest)
        self.assertFalse(check_task_obligations(self.root, "7")[0])
        with self.assertRaisesRegex(ValueError, "milestone"):
            mvg.rebind_handoff(self.root, run_id="repair", task_id="7", change_plan_path=None, out_path=None)
        handoff = self.root / "docs/planning/milestones/task-7-handoff.json"
        mvg.rebind_handoff(self.root, run_id="repair", task_id="7", change_plan_path=plan, out_path=handoff)
        self.assertTrue(check_task_obligations(self.root, "7")[0])
        self.assertEqual(file_sha(dest), load_json(handoff)["baseline_manifest_sha256"])
        import run_single_task_chapter6_lane as lane
        validator = lane.validate_task_handoff
        with patch.object(lane, "_repo_root", return_value=self.root), patch.object(sys, "argv", [
            "lane", "--task-id", "7", "--godot-bin", "fixture-godot", "--self-check",
            "--out-dir", str(self.root / "logs/ci/bound-lane")]), patch.object(lane, "validate_task_handoff", wraps=validator) as consumed:
            self.assertEqual(0, lane.main())
            consumed.assert_called_with(self.root, handoff, "7")
        dest.write_bytes(dest.read_bytes() + b"\n")
        self.assertFalse(validate_task_handoff(self.root, handoff, "7")[0])
        self.assertFalse(check_task_obligations(self.root, "7")[0])

    def test_interrupted_capability_apply_resumes_and_is_idempotent(self):
        selected_cap(self.root)
        original = cap.atomic_json
        def interrupt(path, payload):
            original(path, payload)
            if path == self.root / cap.TASK_VIEWS[1]:
                raise SystemExit("process terminated")
        with patch.object(cap, "atomic_json", side_effect=interrupt):
            with self.assertRaises(SystemExit):
                cap.apply(self.root, run_id="repair", alignment_override=None, confirm=True)
        first = cap.apply(self.root, run_id="repair", alignment_override=None, confirm=True)
        self.assertEqual("applied", first["status"])
        self.assertTrue(load_task_readiness(self.root, "42")[0])
        self.assertEqual(first, cap.apply(self.root, run_id="repair", alignment_override=None, confirm=True))

    def test_recovery_never_overwrites_external_task_edit(self):
        selected_cap(self.root)
        original = cap.atomic_json
        def interrupt(path, payload):
            original(path, payload)
            if path == self.root / cap.TASK_VIEWS[1]:
                raise SystemExit("terminated")
        with patch.object(cap, "atomic_json", side_effect=interrupt), self.assertRaises(SystemExit):
            cap.apply(self.root, run_id="repair", alignment_override=None, confirm=True)
        path = self.root / cap.TASK_VIEWS[1]
        rows = load_json(path)
        rows[0]["acceptance"].append("A subsequent user edit.")
        atomic_json(path, rows)
        edited = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "target drift"):
            cap.apply(self.root, run_id="repair", alignment_override=None, confirm=True)
        self.assertEqual(edited, path.read_bytes())
        self.assertFalse(load_task_readiness(self.root, "7")[0])

    def test_recovery_covers_readiness_and_topology_replacements(self):
        checkpoints = [cap.FORMAL_CAPABILITIES, cap.FORMAL_SELECTION, cap.FORMAL_EDGES, cap.FORMAL_MANIFEST,
            Path("logs/ci/chapter5/reconciliation/task-7.json"), Path("logs/ci/chapter5/readiness/task-7.json")]
        for i, rel in enumerate(checkpoints):
            with self.subTest(checkpoint=str(rel)):
                root = Path(self.temp.name) / f"interrupt-{i}"
                build_fixture(root)
                selected_cap(root)
                master = (root / ".taskmaster/tasks/tasks.json").read_bytes()
                original = cap.atomic_json
                def interrupt(path, payload):
                    original(path, payload)
                    if path == root / rel:
                        raise SystemExit("terminated at durable replacement")
                with patch.object(cap, "atomic_json", side_effect=interrupt), self.assertRaises(SystemExit):
                    cap.apply(root, run_id="repair", alignment_override=None, confirm=True)
                self.assertFalse(load_task_readiness(root, "7")[0])
                result = cap.apply(root, run_id="repair", alignment_override=None, confirm=True)
                self.assertEqual("applied", result["status"])
                self.assertTrue(load_task_readiness(root, "7")[0])
                self.assertTrue(load_task_readiness(root, "42")[0])
                self.assertEqual(master, (root / ".taskmaster/tasks/tasks.json").read_bytes())

    def test_completed_capability_run_cannot_clear_another_pending_owner(self):
        selected_cap(self.root)
        cap.apply(self.root, run_id="repair", alignment_override=None, confirm=True)
        pending = self.root / "docs/planning/semantic-topology/capability-apply.pending.json"
        atomic_json(pending, {"run_id": "another-run"})
        with self.assertRaisesRegex(ValueError, "another Capability"):
            cap.apply(self.root, run_id="repair", alignment_override=None, confirm=True)
        self.assertEqual("another-run", load_json(pending)["run_id"])

    def test_mvg_apply_recovers_manifest_write_and_preserves_final_binding(self):
        from _mvg_obligations import check_task_obligations
        _, _, dest = prepared_mvg(self.root)
        original = mvg.atomic_json
        def interrupt(path, payload):
            original(path, payload)
            if path == dest:
                raise SystemExit("terminated after manifest write")
        with patch.object(mvg, "atomic_json", side_effect=interrupt), self.assertRaises(SystemExit):
            mvg.apply(self.root, run_id="repair", confirm=True)
        self.assertFalse(check_task_obligations(self.root, "7")[0])
        result = mvg.apply(self.root, run_id="repair", confirm=True)
        self.assertEqual("applied", result["status"])
        mvg.rebind_handoff(self.root, run_id="repair", task_id="7", change_plan_path=None, out_path=None)
        self.assertEqual(result, mvg.apply(self.root, run_id="repair", confirm=True))
        self.assertTrue(check_task_obligations(self.root, "7")[0])

    def test_review_retries_execution_only_and_reuses_approved_evidence(self):
        prepared_mvg(self.root)
        run = self.root / "logs/ci/mvg-planning/repair"
        result = load_json(run / "semantic-review.json")
        info = load_json(run / "semantic-review-execution.json")["runner_info"]
        (run / "semantic-review.json").unlink()
        (run / "semantic-review-execution.json").unlink()
        calls = []
        def invoke(*args, **kwargs):
            calls.append(kwargs["workspace"])
            if len(calls) == 1:
                raise RuntimeError("model identity not exposed")
            atomic_json(kwargs["output_path"], result)
            return {"model": "fixture-reviewer", "model_tools": []}
        with patch.object(mvg, "inspect_isolated_runner", return_value=info), patch.object(mvg, "run_isolated_model", side_effect=invoke):
            mvg.review(self.root, run_id="repair", runner=Path("fixture-runner"), timeout_sec=1)
            mvg.review(self.root, run_id="repair", runner=Path("fixture-runner"), timeout_sec=1)
        self.assertEqual(2, len(calls))
        self.assertNotEqual(calls[0], calls[1])
        self.assertEqual(2, len(load_json(run / "run.json")["semantic_review_attempts"]))
        result["verdict"] = "blocked"
        result["findings"] = ["Resolve a semantic gap."]
        atomic_json(run / "semantic-review.json", result)
        with patch.object(mvg, "inspect_isolated_runner", return_value=info), patch.object(mvg, "run_isolated_model") as invoke:
            with self.assertRaisesRegex(ValueError, "resolve its findings"):
                mvg.review(self.root, run_id="repair", runner=Path("fixture-runner"), timeout_sec=1)
            invoke.assert_not_called()


if __name__ == "__main__":
    unittest.main()
