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
from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json, text_sha
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
    for label in ("candidate-1", "candidate-2", "candidate-3"):
        atomic_json(run / f"candidates/{label}.json", candidate)
    state["runner"] = {"model": "fixture-reviewer"}
    state["actual_model"] = "fixture-reviewer"
    _, mapping = cap._anonymous_candidates(state)
    selected = next(alias for alias, label in mapping.items() if label == "candidate-1")
    # Deterministic consumer fixture; no real model execution is claimed.
    atomic_json(run / "review/review.json", {"schema_version": cap.REVIEW_SCHEMA,
        "status": "selected", "selected": selected, "corrections": [],
        "source_fidelity_findings": ["Relay launch and delivery obligations are preserved."],
        "cohesion_findings": [], "boundary_findings": [], "multi_membership_findings": [],
        "navigation_findings": [], "tradeoffs": ["Equivalent scope; choose the first source-faithful fixture."],
        "evidence_refs": ["analysis-input/source-blocks.v1.json", f"candidates/{selected}.json"],
        "rationale": "Select the full relay delivery proposal."})
    atomic_json(run / "review/review.meta.json", {
        "analysis_identity_sha256": state["analysis_identity_sha256"],
        "prompt_sha256": text_sha(cap.REVIEW_PROMPT), "runner_contract_model": "fixture-reviewer",
        "runner": state["runner"], "model": "fixture-reviewer",
        "output_sha256": file_sha(run / "review/review.json"),
        "candidate_sha256": {label: file_sha(run / f"candidates/{label}.json") for label in mapping.values()},
        "anonymous_mapping_sha256": canonical_sha(mapping),
        "receipt": {"model": "fixture-reviewer", "model_tools": []}})
    state.update(phase="reviewed", review_status="selected", selected_candidate="candidate-1")
    atomic_json(run / "run.json", state)
    return run


def prepared_mvg(root):
    selected_cap(root)
    cap.apply(root, run_id="repair", alignment_override=None, confirm=True)
    dest = root / "docs/testing/mvg/repair.json"
    state = mvg.prepare(root, run_id="repair", capabilities_path=root / cap.FORMAL_CAPABILITIES,
        task_ids=["7", "42"], manifest_path=dest, allow_unready=False)
    # This helper constructs historical whole-proposal review evidence. New
    # Capability-local runs are exercised by the public append fixture.
    state['generation_strategy'] = 'independent-candidates-single'
    index_path = root / 'logs/ci/mvg-planning/repair/analysis-input/analysis-index.json'
    index = load_json(index_path)
    index.pop('generation_strategy', None)
    canonical_index = {key: value for key, value in index.items()
                       if key not in {'analysis_identity_sha256', 'repository_identity'}}
    index['analysis_identity_sha256'] = canonical_sha(canonical_index)
    state['analysis_identity_sha256'] = index['analysis_identity_sha256']
    atomic_json(index_path, index)
    atomic_json(root / 'logs/ci/mvg-planning/repair/run.json', state)
    caps = load_json(root / cap.FORMAL_CAPABILITIES)["capabilities"]
    reqs = [c["requirement_ids"][0] for c in caps]
    gameplay = load_json(root / ".taskmaster/tasks/tasks_gameplay.json")
    requirement_tasks = {
        str(requirement): int(row["taskmaster_id"])
        for row in gameplay
        for requirement in row.get("semantic_refs", [])
        if str(requirement) in reqs
    }
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
            "task_id": requirement_tasks[rid], "flow_id": "relay-delivery",
            "coverage": "Launch or resolve relay", "rationale": "Fixture requirement is observed by its owning task."}
            for i, rid in enumerate(reqs)],
        "entrypoints": [{"status": "planned", "owner_task": tid, "path": f"Game.Core/Tasks/Relay{tid}.cs",
            "symbol": f"Relay{tid}.Run", "inputs": ["route"], "state": "cargo transfer",
            "assertions": ["accepted or retry visible"], "implementation_acceptance": ["relay journey"]}
            for tid in (7, 42)]}
    run = root / "logs/ci/mvg-planning/repair"
    atomic_json(run / "proposal.json", proposal)
    # Reviewed fixture evidence tests deterministic consumers; no model execution is claimed.
    review = {"schema_version": "newrouge.mvg-semantic-review.v1",
        "analysis_identity_sha256": state["analysis_identity_sha256"], "proposal_sha256": canonical_sha(proposal),
        "verdict": "approved", "findings": [], "requirement_reviews": [
            {"requirement_id": row["requirement_id"], "verdict": "covered",
             "rationale": "Relay launch and delivery remain observable.",
             "disposition": "flow", "flow_id": row["flow_id"], "sink_id": None,
             "verification_ref": None, "authority_ref": None}
            for row in proposal["coverage_table"]
            ], "flow_reviews": [{"flow_id": "relay-delivery", "verdict": "sound",
                "rationale": "Real contract connects both tasks; planned tests claim no runtime pass."}]}
    atomic_json(run / "semantic-review.json", review)
    atomic_json(run / "semantic-review-execution.json", {
        "analysis_identity_sha256": state["analysis_identity_sha256"], "proposal_sha256": canonical_sha(proposal),
        "semantic_review_sha256": canonical_sha(review),
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
    coverage_by_task = {
        str(task_id): next(row for row in proposal["coverage_table"] if str(row["task_id"]) == str(task_id))
        for task_id in (7, 42)
    }
    plan = {"schema_version": "newrouge.milestone-change-plan.v1",
        "source_identity": {"source_revision": ledger["source_revision"]},
        "baseline_manifest": dest.relative_to(root).as_posix(),
        "source_block_reviews": [{"block_id": b["block_id"], "content_hash": b["content_hash"],
            "disposition": "requirement" if by_block[b["block_id"]] else "context",
            "requirement_ids": by_block[b["block_id"]], "reason": "Source coverage reviewed.",
            "non_delivery_rationale": "Heading context."} for b in ledger["blocks"]],
        "changes": [{"change_id": f"relay-{tid}", "action": "reuse", "target_task_id": str(tid),
            "owner_task_id": str(tid), "reason": "Owns milestone integration acceptance.",
            "requirement_ids": [coverage_by_task[str(tid)]["requirement_id"]],
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
        self.root = (Path(self.temp.name) / "fixture").resolve()
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
                root = (Path(self.temp.name) / f"drift-{i}").resolve()
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
                root = (Path(self.temp.name) / f"interrupt-{i}").resolve()
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
            with self.assertRaisesRegex(ValueError, "resolve.*findings|semantic-review.*identity drift"):
                mvg.review(self.root, run_id="repair", runner=Path("fixture-runner"), timeout_sec=1)
            invoke.assert_not_called()

    def test_semantic_block_never_switches_to_next_ranked_candidate(self):
        state, proposal, _dest = prepared_mvg(self.root)
        run = self.root / "logs/ci/mvg-planning/repair"
        candidate_one = deepcopy(proposal)
        candidate_one["notes"] = ["candidate one"]
        candidate_two = deepcopy(proposal)
        candidate_two["notes"] = ["candidate two"]
        candidate_three = deepcopy(proposal)
        candidate_three["notes"] = ["candidate three"]
        for label, candidate in (("candidate-1", candidate_one),
                                 ("candidate-2", candidate_two),
                                 ("candidate-3", candidate_three)):
            atomic_json(run / "candidates" / f"{label}.json", candidate)
        atomic_json(run / "proposal.json", candidate_one)
        selection = {
            "candidate_reviews": [
                {"label": "A", "verdict": "viable", "rank": 1},
                {"label": "B", "verdict": "viable", "rank": 2},
                {"label": "C", "verdict": "viable", "rank": 3},
            ]
        }
        atomic_json(run / "selection-review.json", selection)
        state.update(selected_candidate="candidate-1", selection_anonymous_mapping={
            "A": "candidate-1", "B": "candidate-2", "C": "candidate-3",
        }, candidate_attempts={label: {
            "status": "valid", "proposal_sha256": mvg.file_sha(run / "candidates" / f"{label}.json"),
            "validation": {"status": "passed", "formal_applicable": True},
        } for label in ("candidate-1", "candidate-2", "candidate-3")})
        atomic_json(run / "run.json", state)
        for path in run.glob("semantic-review-publication-*.json"):
            path.unlink()
        for filename in ("semantic-review.json", "semantic-review-execution.json"):
            path = run / filename
            if path.exists():
                path.unlink()

        runner_info = {
            "schema_version": "newrouge.isolated-model-runner.v1",
            "model": "fixture-reviewer", "fresh_session_per_invocation": True,
            "filesystem_scope": "workspace_only", "can_read_outside_workspace": False,
            "model_tools": [],
        }
        reviewed: list[tuple[Path, str]] = []

        def review_candidate(*_args, **kwargs):
            candidate_path = kwargs["workspace"] / "proposal.json"
            current = load_json(candidate_path)
            reviewed.append((kwargs["workspace"], canonical_sha(current)))
            report = {
                "schema_version": "newrouge.mvg-semantic-review.v1",
                "analysis_identity_sha256": state["analysis_identity_sha256"],
                "proposal_sha256": canonical_sha(current),
                "verdict": "blocked" if len(reviewed) == 1 else "approved",
                "findings": ["Selected proposal has a semantic gap."] if len(reviewed) == 1 else [],
                "requirement_reviews": [{
                    "requirement_id": row["requirement_id"], "verdict": "covered",
                    "rationale": "The proposal route is accounted for.",
                    "disposition": "flow", "flow_id": row["flow_id"], "sink_id": None,
                    "verification_ref": None, "authority_ref": None,
                } for row in current["coverage_table"]],
                "flow_reviews": [{"flow_id": "relay-delivery", "verdict": "sound",
                                  "rationale": "The route has observable boundaries."}],
            }
            atomic_json(kwargs["output_path"], report)
            return {"model": "fixture-reviewer", "model_tools": []}

        with patch.object(mvg, "inspect_isolated_runner", return_value=runner_info), \
             patch.object(mvg, "run_isolated_model", side_effect=review_candidate):
            with self.assertRaisesRegex(ValueError, "semantic review blocked"):
                mvg.review(self.root, run_id="repair", runner=Path("fixture-runner"), timeout_sec=1)

        self.assertEqual(1, len(reviewed))
        self.assertEqual(canonical_sha(candidate_one), canonical_sha(load_json(run / "proposal.json")))
        self.assertEqual("candidate-1", load_json(run / "run.json")["selected_candidate"])

    def test_selected_admission_proof_content_drift_blocks_without_new_model_call(self):
        state, proposal, _dest = prepared_mvg(self.root)
        run = self.root / "logs/ci/mvg-planning/repair"
        proof = run / "selected-admission-proof.json"
        execution = run / "selected-admission-execution.json"
        atomic_json(proof, load_json(run / "semantic-review.json"))
        atomic_json(execution, load_json(run / "semantic-review-execution.json"))
        state.update(
            phase="generated",
            selection_status="selected",
            selected_candidate="candidate-1",
            selected_admission_review={
                "path": proof.relative_to(self.root).as_posix(),
                "execution_path": execution.relative_to(self.root).as_posix(),
                "proposal_sha256": canonical_sha(proposal),
                "proof_sha256": file_sha(proof),
                "execution_sha256": file_sha(execution),
            },
        )
        atomic_json(run / "run.json", state)
        changed = load_json(proof)
        changed["rationale"] = "tampered proof"
        atomic_json(proof, changed)
        with patch.object(mvg, "inspect_isolated_runner") as inspect, \
             patch.object(mvg, "run_isolated_model") as invoke:
            with self.assertRaisesRegex(ValueError, "proof identity"):
                mvg.review(self.root, run_id="repair", runner=Path("fixture-runner"), timeout_sec=1)
        inspect.assert_not_called()
        invoke.assert_not_called()

    def test_selected_run_without_admission_proof_cannot_use_legacy_review(self):
        state, _proposal, _dest = prepared_mvg(self.root)
        run = self.root / "logs/ci/mvg-planning/repair"
        state.update(phase="generated", selection_status="selected", selected_candidate="candidate-1")
        state.pop("selected_admission_review", None)
        atomic_json(run / "run.json", state)
        with patch.object(mvg, "inspect_isolated_runner") as inspect, \
             patch.object(mvg, "run_isolated_model") as invoke:
            with self.assertRaisesRegex(ValueError, "no valid hash-bound admission proof"):
                mvg.review(self.root, run_id="repair", runner=Path("fixture-runner"), timeout_sec=1)
        inspect.assert_not_called()
        invoke.assert_not_called()

    def test_generation_execution_budget_survives_stage_retry(self):
        prepared_mvg(self.root)
        with patch.object(mvg, "inspect_isolated_runner", return_value={"available": True}), \
             patch.object(mvg, "run_isolated_model", side_effect=RuntimeError("missing actual model identity")) as invoke:
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, "attempt budget exhausted"):
                    mvg.generate(self.root, run_id="repair", timeout_sec=1, llm_backend="copilot-cli", segmented=False)
            self.assertEqual(3, invoke.call_count)
        state = load_json(self.root / "logs/ci/mvg-planning/repair/run.json")
        self.assertEqual(3, len(state["generation_attempts"]))

    def test_mvg_review_execution_failures_use_ten_attempts_and_record_error_type(self):
        _state, _proposal, _dest = prepared_mvg(self.root)
        run = self.root / "logs/ci/mvg-planning/repair"
        (run / "semantic-review.json").unlink()
        (run / "semantic-review-execution.json").unlink()
        runner_info = load_json(run / "run.json").get("runner_info") or {
            "schema_version": "newrouge.isolated-model-runner.v1",
            "model": "fixture-reviewer",
            "fresh_session_per_invocation": True,
            "filesystem_scope": "workspace_only",
            "can_read_outside_workspace": False,
            "model_tools": [],
        }
        with patch.object(mvg, "inspect_isolated_runner", return_value=runner_info), \
             patch.object(mvg, "run_isolated_model", side_effect=RuntimeError(
                 "isolated model runner failed: Input exceeds the maximum length of 1048576 characters"
             )):
            with self.assertRaisesRegex(ValueError, "attempts=10"):
                mvg.review(self.root, run_id="repair", runner=Path("fixture-runner"), timeout_sec=1)
        state = load_json(run / "run.json")
        attempts = state["semantic_review_attempts"]
        self.assertEqual(10, state["semantic_review_attempt_limit"])
        self.assertEqual(10, len(attempts))
        self.assertTrue(all(row["error_type"] == "runner_input_too_large" for row in attempts))
        self.assertTrue(all(len(row["error"]) < 2000 for row in attempts))

    def test_mvg_review_workspace_is_compacted_before_runner_invocation(self):
        _state, _proposal, _dest = prepared_mvg(self.root)
        run = self.root / "logs/ci/mvg-planning/repair"
        report = load_json(run / "semantic-review.json")
        proposal = load_json(run / "proposal.json")
        proposal["manifest_candidate"]["flows"][0]["handoffs"][0]["contract_refs"] = None
        atomic_json(run / "proposal.json", proposal)
        report["proposal_sha256"] = canonical_sha(proposal)
        atomic_json(run / "semantic-review.json", report)
        (run / "semantic-review.json").unlink()
        (run / "semantic-review-execution.json").unlink()
        # An unreferenced prepared evidence file must not consume the Codex
        # turn budget merely because it is present in the immutable bundle.
        # Unregistered files are rejected inside the immutable input bundle;
        # keep this compression fixture outside the bundle so it represents
        # unrelated workspace noise rather than hidden evidence.
        noise = run / "unused-large-evidence.txt"
        noise.write_text("x" * 1_100_000, encoding="utf-8")
        observed_sizes = []

        def invoke(*args, **kwargs):
            observed_sizes.append(sum(path.stat().st_size for path in kwargs["workspace"].rglob("*")
                                      if path.is_file() and path != kwargs["output_path"]))
            atomic_json(kwargs["output_path"], report)
            return {"model": "fixture-reviewer", "model_tools": []}

        runner_info = load_json(run / "semantic-review-execution.json") if (run / "semantic-review-execution.json").is_file() else {
            "schema_version": "newrouge.isolated-model-runner.v1", "model": "fixture-reviewer",
            "fresh_session_per_invocation": True, "filesystem_scope": "workspace_only",
            "can_read_outside_workspace": False, "model_tools": [],
        }
        with patch.object(mvg, "inspect_isolated_runner", return_value=runner_info), \
             patch.object(mvg, "run_isolated_model", side_effect=invoke):
            mvg.review(self.root, run_id="repair", runner=Path("fixture-runner"), timeout_sec=1)
        self.assertLess(observed_sizes[0], 900_000)

    def test_mvg_review_retries_structurally_invalid_output_before_semantic_verdict(self):
        _state, _proposal, _dest = prepared_mvg(self.root)
        run = self.root / "logs/ci/mvg-planning/repair"
        report = load_json(run / "semantic-review.json")
        (run / "semantic-review.json").unlink()
        (run / "semantic-review-execution.json").unlink()
        for path in run.glob("semantic-review-publication-*.json"):
            path.unlink()
        for path in (run / "semantic-review-workspace").glob("attempt-*"):
            import shutil
            shutil.rmtree(path)
        journal = load_json(run / "run.json")
        journal["semantic_review_attempts"] = []
        atomic_json(run / "run.json", journal)
        info = {
            "schema_version": "newrouge.isolated-model-runner.v1", "model": "fixture-reviewer",
            "fresh_session_per_invocation": True, "filesystem_scope": "workspace_only",
            "can_read_outside_workspace": False, "model_tools": [],
        }
        calls = []

        def invoke(*args, **kwargs):
            calls.append(kwargs.get("output_schema"))
            atomic_json(kwargs["output_path"], {"schema_version": "wrong"} if len(calls) == 1 else report)
            return {"model": "fixture-reviewer", "model_tools": []}

        with patch.object(mvg, "inspect_isolated_runner", return_value=info), \
             patch.object(mvg, "run_isolated_model", side_effect=invoke):
            result = mvg.review(self.root, run_id="repair", runner=Path("fixture-runner"), timeout_sec=1)
        self.assertEqual("approved", result["status"])
        self.assertEqual(2, len(calls))
        self.assertTrue(all(path is not None for path in calls))

    def test_mvg_review_projection_keeps_only_proposal_task_views(self):
        _state, proposal, _dest = prepared_mvg(self.root)
        run = self.root / "logs/ci/mvg-planning/repair"
        for name in ("tasks_back.json", "tasks_gameplay.json"):
            path = run / "analysis-input/task-views" / name
            rows = load_json(path)
            rows.extend({"taskmaster_id": index, "id": index, "title": "unused"}
                        for index in range(9000, 9050))
            atomic_json(path, rows)
        workspace = run / "semantic-review-workspace/projection-test"
        mvg._prepare_review_workspace(run, workspace, proposal)
        projected = load_json(workspace / "analysis-input/task-views/tasks_gameplay.json")
        self.assertTrue(projected)
        self.assertTrue(all(row.get("taskmaster_id") in {7, 42} for row in projected))
        self.assertFalse(any(row.get("taskmaster_id") == 9000 for row in projected))

    def test_mvg_review_input_size_failure_does_not_burn_ten_model_attempts(self):
        _state, _proposal, _dest = prepared_mvg(self.root)
        run = self.root / "logs/ci/mvg-planning/repair"
        (run / "semantic-review.json").unlink()
        (run / "semantic-review-execution.json").unlink()
        info = {
            "schema_version": "newrouge.isolated-model-runner.v1", "model": "fixture-reviewer",
            "fresh_session_per_invocation": True, "filesystem_scope": "workspace_only",
            "can_read_outside_workspace": False, "model_tools": [],
        }
        with patch.object(mvg, "inspect_isolated_runner", return_value=info), \
             patch.object(mvg, "run_isolated_model") as invoke, \
             patch.object(mvg, "_prepare_review_workspace",
                          side_effect=ValueError("bounded MVG review workspace exceeds 850000 bytes: 912461")):
            with self.assertRaisesRegex(ValueError, "runner_input_too_large"):
                mvg.review(self.root, run_id="repair", runner=Path("fixture-runner"), timeout_sec=1)
        invoke.assert_not_called()
        attempts = load_json(run / "run.json").get("semantic_review_attempts", [])
        self.assertEqual(0, len(attempts))

    def test_mvg_review_projection_adapts_large_evidence_excerpts(self):
        _state, proposal, _dest = prepared_mvg(self.root)
        run = self.root / "logs/ci/mvg-planning/repair"
        references = run / "analysis-input/references"
        names = [f"large-evidence-{index}.txt" for index in range(8)]
        for name in names:
            (references / name).parent.mkdir(parents=True, exist_ok=True)
            (references / name).write_text("evidence-line\n" * 12000, encoding="utf-8")
        with patch.object(mvg, "_review_reference_paths", return_value=set(names)):
            workspace = run / "semantic-review-workspace/adaptive-test"
            mvg._prepare_review_workspace(run, workspace, proposal)
        size = sum(path.stat().st_size for path in workspace.rglob("*") if path.is_file())
        self.assertLess(size, mvg.MVG_REVIEW_WORKSPACE_LIMIT)
        evidence = load_json(workspace / "analysis-input/review-evidence.json")
        self.assertEqual(names, [row["path"] for row in evidence["files"]])
        self.assertTrue(all(row["sha256"] for row in evidence["files"]))
        self.assertTrue(all(row["excerpt_truncated"] for row in evidence["files"]))

    def test_mvg_generation_normalizes_dotnet_selector_from_test_class(self):
        _state, proposal, _dest = prepared_mvg(self.root)
        proposal["manifest_candidate"]["tests"][0]["selector"] = "RelayTests*"
        path = self.root / "Game.Core.Tests/Tasks/RelayTests.cs"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("namespace Fixture; public class RelayTests { }\n", encoding="utf-8")
        proposal["manifest_candidate"]["tests"][0]["test_refs"] = [path.relative_to(self.root).as_posix()]
        errors = mvg.validate_proposal(
            self.root,
            load_json(self.root / "logs/ci/mvg-planning/repair/run.json"),
            proposal,
        )
        self.assertTrue(any("relay-contract: selector must be a class name" in value for value in errors["errors"]))
        changed = mvg.normalize_dotnet_selectors(self.root, proposal)
        self.assertEqual(1, changed)
        self.assertEqual("RelayTests", proposal["manifest_candidate"]["tests"][0]["selector"])

    def test_mvg_generation_does_not_guess_selector_when_test_file_has_multiple_classes(self):
        _state, proposal, _dest = prepared_mvg(self.root)
        proposal["manifest_candidate"]["tests"][0]["selector"] = "Relay*"
        path = self.root / "Game.Core.Tests/Tasks/RelayTests.cs"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("public class RelayTests { } public class RelayFixture { }\n", encoding="utf-8")
        changed = mvg.normalize_dotnet_selectors(self.root, proposal)
        self.assertEqual(0, changed)
        self.assertEqual("Relay*", proposal["manifest_candidate"]["tests"][0]["selector"])

    def test_capability_transport_failure_does_not_pin_auto_as_actual_model(self):
        run = selected_cap(self.root)
        candidate = load_json(run / "candidates/candidate-1.json")
        state = load_json(run / "run.json")
        state.pop("actual_model")  # Exercise fresh generation, not the synthetic review fixture.
        atomic_json(run / "run.json", state)
        calls = []
        def invoke(*args, **kwargs):
            calls.append(kwargs["workspace"])
            if len(calls) == 1:
                raise RuntimeError("actual model identity not exposed")
            atomic_json(kwargs["output_path"], candidate)
            model = "different-model" if len(calls) == 3 else "fixture-model"
            return {"model": model, "model_tools": []}
        with patch.object(cap, "inspect_isolated_runner", return_value={"model": "auto"}), \
             patch.object(cap, "run_isolated_model", side_effect=invoke):
            result = cap.generate(self.root, run_id="repair", runner=Path("fixture-runner"), timeout_sec=1)
        self.assertEqual("complete", result["status"])
        self.assertEqual(5, len(calls))
        state = load_json(run / "run.json")
        self.assertEqual("fixture-model", state["actual_model"])
        self.assertEqual("", state["candidate_attempts"]["candidate-1"]["attempts"][0]["model"])
        self.assertIn("actual_model_mismatch:different-model!=fixture-model",
            state["candidate_attempts"]["candidate-2"]["attempts"][0]["validation_errors"])
        self.assertEqual({"fixture-model"},
            {row["final_meta"]["model"] for row in state["candidate_attempts"].values()})

    def test_capability_missing_actual_receipt_cannot_accept_configured_model(self):
        run = selected_cap(self.root)
        candidate = load_json(run / "candidates/candidate-1.json")
        state = load_json(run / "run.json")
        state.pop("actual_model")  # Exercise fresh generation without an accepted receipt.
        atomic_json(run / "run.json", state)
        def invoke(*args, **kwargs):
            atomic_json(kwargs["output_path"], candidate)
            return {}
        with patch.object(cap, "inspect_isolated_runner", return_value={"model": "configured-model"}), \
             patch.object(cap, "run_isolated_model", side_effect=invoke):
            with self.assertRaisesRegex(ValueError, "actual_model_identity_missing"):
                cap.generate(self.root, run_id="repair", runner=Path("fixture-runner"), timeout_sec=1)
        self.assertNotIn("actual_model", load_json(run / "run.json"))

    def test_candidate_deterministic_failure_reuses_previous_candidate_as_repair_seed(self):
        run = selected_cap(self.root)
        candidate = load_json(run / "candidates/candidate-1.json")
        state = load_json(run / "run.json")
        state.update(phase="prepared", review_status=None, selected_candidate=None, final_candidate_path=None)
        state.pop("actual_model", None)
        atomic_json(run / "run.json", state)
        invalid = deepcopy(candidate)
        invalid["capabilities"][0]["requirement_ids"] = []
        calls = []

        def invoke(*args, **kwargs):
            calls.append(kwargs["workspace"])
            atomic_json(kwargs["output_path"], invalid if len(calls) == 1 else candidate)
            return {"model": "fixture-model", "model_tools": []}

        with patch.object(cap, "inspect_isolated_runner", return_value={"model": "fixture-model"}), \
             patch.object(cap, "run_isolated_model", side_effect=invoke):
            result = cap.generate(self.root, run_id="repair", runner=Path("fixture-runner"), timeout_sec=1)
        self.assertEqual("complete", result["status"])
        seed = run / "candidates/attempts/candidate-1-attempt-1.json"
        retry_workspace = run / "isolated-workspaces/candidate-1/attempt-2"
        self.assertEqual(invalid, load_json(seed))
        self.assertEqual(invalid, load_json(retry_workspace / "previous-candidate.json"))
        self.assertIn("previous-candidate.json", (retry_workspace / "prompt.txt").read_text(encoding="utf-8"))
        attempts = load_json(run / "run.json")["candidate_attempts"]["candidate-1"]["attempts"]
        self.assertEqual("clean", attempts[0]["retry_mode"])
        self.assertEqual("repair", attempts[1]["retry_mode"])
        self.assertTrue(attempts[1]["repair_seed_path"].endswith("candidate-1-attempt-1.json"))

    def test_candidate_runner_failure_uses_clean_retry_without_previous_seed(self):
        run = selected_cap(self.root)
        candidate = load_json(run / "candidates/candidate-1.json")
        state = load_json(run / "run.json")
        state.update(phase="prepared", review_status=None, selected_candidate=None, final_candidate_path=None)
        state.pop("actual_model", None)
        atomic_json(run / "run.json", state)
        calls = []

        def invoke(*args, **kwargs):
            calls.append(kwargs["workspace"])
            if len(calls) == 1:
                raise RuntimeError("runner timed out")
            atomic_json(kwargs["output_path"], candidate)
            return {"model": "fixture-model", "model_tools": []}

        with patch.object(cap, "inspect_isolated_runner", return_value={"model": "fixture-model"}), \
             patch.object(cap, "run_isolated_model", side_effect=invoke):
            result = cap.generate(self.root, run_id="repair", runner=Path("fixture-runner"), timeout_sec=1)
        self.assertEqual("complete", result["status"])
        retry_workspace = run / "isolated-workspaces/candidate-1/attempt-2"
        self.assertFalse((retry_workspace / "previous-candidate.json").exists())
        attempts = load_json(run / "run.json")["candidate_attempts"]["candidate-1"]["attempts"]
        self.assertEqual("clean", attempts[0]["retry_mode"])
        self.assertEqual("clean", attempts[1]["retry_mode"])
        self.assertIsNone(attempts[1]["repair_seed_path"])

    def test_generation_corrects_structural_error_with_restricted_patch(self):
        _, proposal, _ = prepared_mvg(self.root)
        prompts = []
        def invoke(*args, **kwargs):
            prompts.append(kwargs["prompt_path"].read_text())
            if len(prompts) == 1:
                value = deepcopy(proposal)
                value["manifest_candidate"]["flows"][0]["outcome"] = ""
            else:
                value = {"flow_updates": [{"id": "relay-delivery",
                                            "outcome": "Cargo arrives or retry is visible."}]}
            atomic_json(kwargs["output_path"], value)
            return {"model": "fixture-generator", "model_tools": []}
        with patch.object(mvg, "inspect_isolated_runner", return_value={"available": True}), \
             patch.object(mvg, "run_isolated_model", side_effect=invoke):
            mvg.generate(self.root, run_id="repair", timeout_sec=1, llm_backend="copilot-cli", segmented=False)
        self.assertEqual(2, len(prompts))
        self.assertIn("relay-delivery: outcome, sources and handoffs are required", prompts[1])
        self.assertIn("Return a JSON patch only", prompts[1])

    def test_segmented_generation_runner_failure_is_not_retired_as_semantic_issue(self):
        prepared_mvg(self.root)
        calls = 0
        def invoke(*args, **kwargs):
            nonlocal calls
            calls += 1
            raise RuntimeError("fixture runner unavailable")
        with patch.object(mvg, "inspect_isolated_runner", return_value={"available": True}), \
             patch.object(mvg, "run_isolated_model", side_effect=invoke), \
             patch("_mvg_capability_generation.generate_append", side_effect=RuntimeError("fixture runner unavailable")) as worker:
            with self.assertRaisesRegex(ValueError, "selection_blocked_insufficient_admitted_candidates"):
                mvg.generate(self.root, run_id="repair", timeout_sec=1,
                             llm_backend="copilot-cli", segmented=True)
        state = load_json(self.root / "logs/ci/mvg-planning/repair/run.json")
        self.assertEqual("selection-blocked-insufficient-admitted-candidates", state["phase"])
        self.assertEqual("blocked", state["selection_status"])
        self.assertEqual("selection_blocked_insufficient_admitted_candidates", state["selection_block_reason"])
        self.assertEqual(0, state.get("replacement_rounds_used", 0))
        self.assertTrue(all(row["append_terminal"] for row in state["candidate_admissions"].values()))
        self.assertTrue(all(row["admission_status"] == "execution-failed"
                            for row in state["candidate_attempts"].values()))
        self.assertTrue(state["admission_events"])
        self.assertTrue(all(row["event"] != "admission-issue"
                            for row in state["admission_events"]))
        self.assertTrue(any(row["event"] == "admission-execution-failed"
                            for row in state["admission_events"]))
        self.assertFalse(any(row["event"] == "candidate-retired"
                             for row in state["admission_events"]))
        self.assertEqual(3, worker.call_count)
        self.assertEqual(0, calls)

    def test_generation_pins_task_status_during_full_structural_correction(self):
        _, proposal, _ = prepared_mvg(self.root)
        prompts = []
        def invoke(*args, **kwargs):
            prompts.append(kwargs["prompt_path"].read_text())
            # The isolated model workspace is intentionally segment-local and
            # does not mount analysis-input. Task status is supplied through
            # the bounded prompt contract instead.
            self.assertIn('"7": "done"', prompts[-1])
            self.assertIn('"42": "done"', prompts[-1])
            if len(prompts) == 1:
                value = deepcopy(proposal)
                value["manifest_candidate"]["flows"][0]["outcome"] = ""
            elif len(prompts) == 2:
                value = {"flow_updates": [{"id": "relay-delivery", "outcome": ""}]}
            else:
                value = {"flow_updates": [{"id": "relay-delivery",
                                            "outcome": "Cargo arrives or retry is visible."}]}
            atomic_json(kwargs["output_path"], value)
            return {"model": "fixture-generator", "model_tools": []}
        with patch.object(mvg, "inspect_isolated_runner", return_value={"available": True}), \
             patch.object(mvg, "run_isolated_model", side_effect=invoke):
            result = mvg.generate(self.root, run_id="repair", timeout_sec=1, llm_backend="copilot-cli", segmented=False)
        self.assertEqual(3, result["attempt_count"])
        self.assertIn("relay-delivery: outcome, sources and handoffs are required", prompts[1])
        self.assertIn("Return a JSON patch only", prompts[2])
        for prompt in prompts:
            self.assertIn('"7": "done"', prompt)
            self.assertIn('"42": "done"', prompt)
            self.assertIn("The only known non-done Taskmaster IDs are: []", prompt)
            self.assertIn("coverage.blocking_task_ids MUST be []", prompt)
            self.assertIn("source-specified producer/consumer system roles", prompt)
            self.assertIn("roles share a task", prompt)
            self.assertIn("planned test scenarios/assertions", prompt)
            self.assertIn('coverage_table rows require a nonempty "rationale" string', prompt)
        final = load_json(self.root / "logs/ci/mvg-planning/repair/proposal.json")
        self.assertEqual([], final["manifest_candidate"]["coverage"]["blocking_task_ids"])
        self.assertEqual("Cargo arrives or retry is visible.", final["manifest_candidate"]["flows"][0]["outcome"])


if __name__ == "__main__":
    unittest.main()
