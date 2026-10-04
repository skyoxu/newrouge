#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PYTHON = ROOT / "scripts" / "python"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))

import plan_mvg

from plan_mvg import (
    SUPPORTED_LLM_BACKENDS, build_delta, rebind_handoff, validate_proposal,
    build_coverage_skeleton, build_entrypoint_skeleton, correction_prompt,
    apply_restricted_patch, is_restricted_patch, validate_restricted_patch_identity,
)
from update_mvg_baseline import apply_delta


class MvgPlanningContractTests(unittest.TestCase):
    def test_coverage_skeleton_accounts_for_every_delivery_requirement(self):
        semantics = {"requirements": [
            {"requirement_id": "FR-1", "delivery_relevant": True, "status": "active", "source_block_ids": ["SB-1"]},
            {"requirement_id": "NFR-1", "delivery_relevant": True, "status": "active", "source_block_ids": ["SB-2"]},
        ]}
        views = [{"taskmaster_id": 7, "semantic_refs": ["FR-1", "NFR-1"], "capability_refs": ["CAP-A"]}]
        result = build_coverage_skeleton(semantics, views)
        self.assertEqual(["FR-1", "NFR-1"], [row["requirement_id"] for row in result])
        self.assertTrue(all(row["disposition"] == "flow" for row in result))

    def test_entrypoint_skeleton_has_one_owner_per_flow_task(self):
        result = build_entrypoint_skeleton([7, 42])
        self.assertEqual([7, 42], [row["owner_task"] for row in result])
        self.assertTrue(all(row["status"] == "planned" for row in result))

    def test_correction_prompt_requests_restricted_patch(self):
        prompt = correction_prompt(["coverage_requirement_missing:FR-1"])
        self.assertIn("patch", prompt.lower())
        self.assertIn("coverage_additions", prompt)
        self.assertNotIn("completely corrected FULL proposal", prompt)

    def test_generation_prompt_mentions_non_droppable_skeleton(self):
        self.assertIn("coverage-skeleton.json", plan_mvg.PROMPT)
        self.assertIn("must not delete", plan_mvg.PROMPT)

    def test_restricted_patch_preserves_existing_flow_and_adds_coverage(self):
        base = {"coverage_table": [{"requirement_id": "FR-1", "flow_id": "flow-a"}],
                "manifest_candidate": {"flows": [{"id": "flow-a"}]},
                "entrypoints": []}
        patched = apply_restricted_patch(base, {
            "coverage_additions": [{"requirement_id": "FR-2", "flow_id": "flow-a"}],
            "flow_updates": [], "handoff_updates": [], "entrypoint_additions": []})
        self.assertEqual(["flow-a"], [row["id"] for row in patched["manifest_candidate"]["flows"]])
        self.assertEqual(["FR-1", "FR-2"], [row["requirement_id"] for row in patched["coverage_table"]])

    def test_correction_attempt_rejects_full_replacement_shape(self):
        self.assertTrue(is_restricted_patch({"coverage_additions": []}))
        self.assertTrue(is_restricted_patch({"schema_version": "newrouge.mvg-planning-proposal.v1",
                                             "analysis_identity_sha256": "sha256:x",
                                             "coverage_additions": []}))
        self.assertFalse(is_restricted_patch({"schema_version": "newrouge.mvg-planning-proposal.v1"}))

    def test_restricted_patch_identity_is_bound_to_prepared_run(self):
        state = {"analysis_identity_sha256": "sha256:expected"}
        self.assertEqual([], validate_restricted_patch_identity({
            "schema_version": "newrouge.mvg-planning-proposal.v1",
            "analysis_identity_sha256": "sha256:expected"}, state))
        self.assertIn("restricted_patch_analysis_identity_mismatch",
                      validate_restricted_patch_identity({"analysis_identity_sha256": "sha256:other"}, state))
    def _root(self, folder: str) -> Path:
        root = Path(folder)
        tasks = root / ".taskmaster/tasks"
        tasks.mkdir(parents=True)
        (tasks / "tasks.json").write_text(json.dumps({"master": {"tasks": [
            {"id": 1, "status": "done"}, {"id": 2, "status": "done"}
        ]}}), encoding="utf-8")
        (root / "docs/gdd").mkdir(parents=True)
        (root / "docs/gdd/spec.md").write_text("spec\n", encoding="utf-8")
        (root / "docs/contracts").mkdir(parents=True)
        (root / "docs/contracts/handoff.md").write_text("contract\n", encoding="utf-8")
        bundle = root / "logs/ci/mvg-planning/contract/analysis-input"
        files, authorities = {}, {}
        for rel, prefix in (("docs/gdd/spec.md", "sources"), ("docs/contracts/handoff.md", "references")):
            target = bundle / prefix / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((root / rel).read_bytes())
            files[f"{prefix}/{rel}"] = plan_mvg.file_sha(target)
            authorities[rel] = plan_mvg.file_sha(root / rel)
        plan_mvg.atomic_json(bundle / "analysis-index.json", {"files": files, "authority_inputs": authorities})
        (root / "docs/planning/semantic-topology").mkdir(parents=True)
        (root / "docs/planning/semantic-topology/capabilities.v1.json").write_text(json.dumps({
            "schema_version": "newrouge.capabilities.v1",
            "capabilities": [{"capability_id": "CAP-A", "title": "A", "requirement_ids": ["RQ-1"]}]
        }), encoding="utf-8")
        (root / "logs/ci/task-generation").mkdir(parents=True)
        (root / "logs/ci/task-generation/semantic-requirements.v1.json").write_text(json.dumps({
            "schema_version": "newrouge.semantic-requirements.v1",
            "requirements": [{"requirement_id": "RQ-1"}]
        }), encoding="utf-8")
        return root

    def manifest(self) -> dict:
        return {
            "schema_version": "newrouge.mvg-integration.v1",
            "mvg_id": "fixture",
            "coverage": {
                "mode": "pilot",
                "scope_id": "fixture",
                "required_flow_ids": ["flow-a"],
                "blocking_task_ids": [],
                "excluded_claims": ["manual experience"],
            },
            "flows": [{
                "id": "flow-a",
                "outcome": "result",
                "task_ids": [1, 2],
                "source_paths": ["docs/gdd/spec.md"],
                "handoffs": [{
                    "producer_task": 1,
                    "consumer_task": 2,
                    "owner_task": 1,
                    "contract_ref": "docs/contracts/handoff.md",
                    "behavior": "handoff",
                    "test_ids": ["test-a"],
                }],
                "test_ids": ["test-a"],
                "requirement_ids": ["RQ-1"],
                "capability_refs": ["CAP-A"],
            }],
            "tests": [{
                "id": "test-a",
                "kind": "dotnet",
                "state": "planned",
                "path": "Game.Core.Tests/Tasks/FixtureTests.cs",
                "selector": "Fixture.Tests",
                "evidence_level": "domain-integration",
                "min_tests": 1,
            }],
        }

    def accounting(self) -> dict:
        return {"coverage_table": [{"requirement_id": "RQ-1", "capability_ref": "CAP-A", "task_id": 1,
            "flow_id": "flow-a", "coverage": "Observable result through the real contract"}],
            "entrypoints": [{"status": "planned", "owner_task": tid,
                "path": f"Game.Core/Tasks/Fixture{tid}.cs", "symbol": "Run", "inputs": ["request"],
                "state": "result", "assertions": ["result visible"], "implementation_acceptance": ["flow-a"]}
                for tid in (1, 2)]}

    def test_llm_backend_module_is_resolved_from_tool_installation_not_target_repo(self) -> None:
        source = Path(plan_mvg.__file__).read_text(encoding="utf-8")
        self.assertIn('Path(__file__).resolve().parents[1] / "sc"', source)
        self.assertNotIn('str(root / "scripts/sc")', source)

    def test_openai_api_generation_routes_through_text_only_workspace_runner(self) -> None:
        source = Path(plan_mvg.__file__).read_text(encoding="utf-8")
        self.assertIn("run_isolated_model(", source)
        self.assertIn("openai_isolated_model_runner.py", source)
        self.assertIn('prompt_path = workspace / f"prompt-attempt-{attempt}.txt"', source)
        self.assertIn('"proposal-attempt-{attempt}.json"', source)

    def test_copilot_cli_is_a_supported_real_planning_backend(self) -> None:
        self.assertIn("copilot-cli", SUPPORTED_LLM_BACKENDS)

    def test_openai_api_is_a_supported_real_planning_backend(self) -> None:
        self.assertIn("openai-api", SUPPORTED_LLM_BACKENDS)
        self.assertIn("codex-cli", SUPPORTED_LLM_BACKENDS)

    def test_draft_or_unresolved_gaps_cannot_be_formally_applied(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = self._root(folder)
            state = {
                "run_id": "contract",
                "analysis_identity_sha256": "sha256:x",
                "capabilities_path": "docs/planning/semantic-topology/capabilities.v1.json",
            }
            base = {
                "schema_version": "newrouge.mvg-planning-proposal.v1",
                "analysis_identity_sha256": "sha256:x",
                "manifest_candidate": self.manifest(),
                "entrypoints": [],
                "gaps": [],
                **self.accounting(),
            }
            draft = dict(base, planning_status="draft")
            result = validate_proposal(root, state, draft)
            self.assertEqual("passed", result["status"])
            self.assertFalse(result["formal_applicable"])
            self.assertIn("planning_status_not_ready", result["formal_blockers"])

            gap = dict(
                base,
                planning_status="ready_for_validation",
                gaps=[{"kind": "missing_owner"}],
            )
            result = validate_proposal(root, state, gap)
            self.assertEqual("passed", result["status"])
            self.assertFalse(result["formal_applicable"])
            self.assertIn("unresolved_gaps", result["formal_blockers"])

            ready = dict(base, planning_status="ready_for_validation")
            result = validate_proposal(root, state, ready)
            self.assertTrue(result["formal_applicable"])

    def test_openai_generation_state_does_not_depend_on_codex_command_variable(self) -> None:
        source = Path(plan_mvg.__file__).read_text(encoding="utf-8")
        self.assertIn('"runner": runner.as_posix()', source)
        self.assertIn('"attempt_count": len(attempts)', source)
        self.assertNotIn('state["model_command"] = cmd', source)

    def test_proposal_rejects_unknown_capability(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = self._root(folder)
            state = {
                "run_id": "contract",
                "analysis_identity_sha256": "sha256:x",
                "capabilities_path": "docs/planning/semantic-topology/capabilities.v1.json",
            }
            manifest = self.manifest()
            manifest["flows"][0]["capability_refs"] = ["CAP-MISSING"]
            proposal = {
                "schema_version": "newrouge.mvg-planning-proposal.v1",
                "analysis_identity_sha256": "sha256:x",
                "planning_status": "ready_for_validation",
                "manifest_candidate": manifest,
                "entrypoints": [],
                "gaps": [],
            }
            result = validate_proposal(root, state, proposal)
            self.assertIn("unknown_capability_ref:CAP-MISSING", result["errors"])

    def test_handoff_rebind_requires_applied_manifest_and_reuses_existing_contract(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = self._root(folder)
            manifest_path = root / "docs/testing/mvg/fixture.json"
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(json.dumps(self.manifest()), encoding="utf-8")
            run_dir = root / "logs/ci/mvg-planning/run-1"
            run_dir.mkdir(parents=True)
            run_state = {
                "schema_version": "newrouge.mvg-planning-run.v1",
                "run_id": "run-1",
                "applied": True,
                "manifest_path": "docs/testing/mvg/fixture.json",
                "applied_manifest_sha256": __import__("plan_mvg").file_sha(manifest_path),
                "involved_task_ids": ["1", "2"],
                "handoff_bindings": {},
            }
            (run_dir / "run.json").write_text(json.dumps(run_state), encoding="utf-8")
            readiness_path = root / "logs/ci/chapter5/readiness/task-1.json"
            readiness_path.parent.mkdir(parents=True)
            readiness_path.write_text(json.dumps({"schema_version": "newrouge.chapter5-readiness.v1"}), encoding="utf-8")
            change_plan = root / "logs/change-plan.json"
            change_plan.parent.mkdir(parents=True, exist_ok=True)
            change_plan.write_text(json.dumps({"baseline_manifest": "docs/testing/mvg/fixture.json"}), encoding="utf-8")
            trace = root / "docs/testing/mvg/planning/run-1.json"
            trace.parent.mkdir(parents=True)
            trace.write_text(json.dumps({"applied_manifest_sha256": run_state["applied_manifest_sha256"]}), encoding="utf-8")
            out = root / "logs/handoff.json"
            handoff = {"schema_version": "newrouge.milestone-task-handoff.v1", "task_id": "1"}

            with patch("chapter5_semantic_reconciliation.load_task_readiness", return_value=(True, {"readiness": "READY"}, "ready")), \
                 patch("milestone_incremental_handoff.build_task_handoff", return_value=handoff), \
                 patch("milestone_incremental_handoff.validate_task_handoff", return_value=(True, "valid", handoff)):
                result = rebind_handoff(
                    root,
                    run_id="run-1",
                    task_id="1",
                    change_plan_path=change_plan,
                    out_path=out,
                )
            self.assertEqual("bound", result["status"])
            self.assertTrue(result["chapter6_handoff_ready"])
            self.assertFalse(result["runtime_verified"])
            state = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            self.assertEqual("valid", state["handoff_bindings"]["1"]["status"])
            self.assertEqual(run_state["applied_manifest_sha256"], state["handoff_bindings"]["1"]["manifest_sha256"])

    def test_model_correction_contract_mentions_numeric_task_ids_and_required_manifest_shape(self) -> None:
        import inspect
        import plan_mvg

        source = inspect.getsource(plan_mvg.generate)
        self.assertIn("task_ids and every handoff", source)
        self.assertIn("JSON integers", source)
        self.assertIn("coverage is mandatory", source)
        self.assertIn("correction_prompt(errors)", source)
        self.assertIn("apply_restricted_patch", source)
        self.assertIn("Known Taskmaster IDs for this planning input", source)
        self.assertIn("Declared authoritative source paths", source)
        self.assertIn("Existing reviewed contract refs", source)
        self.assertIn("Existing test refs", source)
        self.assertIn("for attempt in (1, 2, 3)", source)

    def test_delta_preserves_unchanged_rows(self) -> None:
        existing = self.manifest()
        proposal = {
            "manifest_candidate": self.manifest(),
            "change_reviews": [],
            "retirement_reviews": [],
            "coverage_review": {},
        }
        delta = build_delta(existing, proposal)
        self.assertEqual("retain", delta["flow_operations"][0]["action"])
        self.assertEqual("retain", delta["test_operations"][0]["action"])

    def test_delta_retirement_without_review_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = self._root(folder)
            existing = self.manifest()
            desired = self.manifest()
            desired["flows"] = []
            desired["coverage"]["required_flow_ids"] = []
            proposal = {
                "manifest_candidate": desired,
                "change_reviews": [],
                "retirement_reviews": [],
                "coverage_review": {},
            }
            delta = build_delta(existing, proposal)
            with self.assertRaisesRegex(ValueError, "authority_ref"):
                apply_delta(existing, delta, root=root)


if __name__ == "__main__":
    unittest.main()
