#!/usr/bin/env python3
from __future__ import annotations

import json
import concurrent.futures
import sys
import tempfile
import threading
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
    SEGMENT_SCHEMA, segment_prompt, validate_segment_identity, merge_planning_segments,
    build_manifest_skeleton, build_flow_scopes, load_reusable_segment, segment_output_schema,
    bind_manifest_test_ids, preserve_frozen_manifest_baseline,
    _contract_candidates,
    validate_segment_references, validate_segment_routing,
    validate_review_shape, _list_field,
    normalize_proposal_format,
    backfill_review_error_types,
    mvg_selection_output_schema, validate_mvg_selection,
    validate_selection_execution_receipt,
    MVG_REPAIR_ATTEMPT_LIMIT, admission_issue_id, advance_admission_state,
    fresh_replacement_lineage,
    run_admission_semantic_gate,
    _latest_attempt_artifact,
    restore_admission_checkpoint,
    candidate_attempt_numbers, reserve_replacement_round,
    build_selection_input_identity,
    candidate_resume_attempt_numbers,
    reserve_candidate_model_invocation,
    _block_selection_for_insufficient_admitted_candidates,
)
from update_mvg_baseline import apply_delta
from _planning_skill_common import atomic_json


class MvgPlanningContractTests(unittest.TestCase):

    def admission_fixture(self, folder):
        """Build a valid public proposal with a sealed legacy prepared bundle."""
        root = self._root(folder)
        run = root / 'logs/ci/mvg-planning/contract'
        prepared = run / 'analysis-input'
        semantic = {'requirements': [{'requirement_id': 'R1'}]}
        capabilities = {'schema_version': 'newrouge.capabilities.v1',
                        'capabilities': [{'capability_id': 'CAP-A', 'requirement_ids': ['R1']}]}
        for name, value in (('semantic-requirements.v1.json', semantic), ('capabilities.v1.json', capabilities)):
            atomic_json(prepared / name, value)
        index = plan_mvg.load_json(prepared / 'analysis-index.json')
        for name in ('semantic-requirements.v1.json', 'capabilities.v1.json'):
            index['files'][name] = plan_mvg.file_sha(prepared / name)
        identity = plan_mvg.canonical_sha(index)
        index['analysis_identity_sha256'] = identity
        atomic_json(prepared / 'analysis-index.json', index)
        state = {'schema_version': plan_mvg.RUN_SCHEMA, 'run_id': 'contract',
                 'analysis_identity_sha256': identity,
                 'capabilities_path': 'docs/planning/semantic-topology/capabilities.v1.json'}
        value = {'schema_version': plan_mvg.PROPOSAL_SCHEMA, 'analysis_identity_sha256': identity,
                 'planning_status': 'ready_for_validation', 'gaps': [],
                 'manifest_candidate': self.manifest(), **self.accounting()}
        value['manifest_candidate']['flows'][0]['requirement_ids'] = ['R1']
        value['coverage_table'][0].update(requirement_id='R1', disposition='flow', verification_ref=None)
        atomic_json(run / 'run.json', state)
        self.assertEqual([], plan_mvg.candidate_admission_errors(root, state, value))
        return root, run, state, value

    def test_selection_blocks_explicitly_when_three_admitted_candidates_are_unavailable(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp) / "run"
            run_dir.mkdir(parents=True)
            state = {"run_id": "selection-block", "selected_candidate": "candidate-3",
                     "selection_input_candidates": ["candidate-1", "candidate-2", "candidate-3"],
                     "selection_input_sha256": "stale", "selected_admission_review": {"stale": True},
                     "admission_stop_reason": "replacement_round_budget_exhausted",
                     "candidate_attempts": {"candidate-2": {"error": "transport failed"}}}
            atomic_json(run_dir / "model-execution.json", {
                "backend": "codex-cli", "audit": "preserve", "selected_candidate": "candidate-3", "selected_alias": "A"})
            results = [
                {"label": "candidate-1", "admitted": True},
                {"label": "candidate-2", "admitted": False},
                {"label": "candidate-3", "admitted": False},
            ]
            with self.assertRaisesRegex(
                ValueError, "selection_blocked_insufficient_admitted_candidates"
            ):
                _block_selection_for_insufficient_admitted_candidates(run_dir, state, results)
            self.assertEqual("blocked", state["selection_status"])
            self.assertEqual(
                "selection_blocked_insufficient_admitted_candidates",
                state["selection_block_reason"],
            )
            self.assertEqual(["candidate-1"], state["admitted_candidates"])
            self.assertNotIn("selection_input_candidates", state)
            self.assertNotIn("selected_candidate", state)
            self.assertNotIn("selection_input_sha256", state)
            self.assertNotIn("selected_admission_review", state)
            receipt = json.loads((run_dir / "model-execution.json").read_text(encoding="utf-8"))
            self.assertEqual(
                "selection_blocked_insufficient_admitted_candidates",
                receipt["selection_error"],
            )
            self.assertEqual("preserve", receipt["audit"])
            self.assertEqual("codex-cli", receipt["backend"])
            self.assertEqual(state["candidate_attempts"], receipt["candidate_attempts"])
            self.assertNotIn("selected_candidate", receipt)
            self.assertNotIn("selected_alias", receipt)
            self.assertEqual("replacement_round_budget_exhausted", state["admission_stop_reason"])

    def test_generate_terminal_append_failures_block_before_selection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = root / "logs/ci/mvg-planning/terminal"
            (run_dir / "analysis-input").mkdir(parents=True)
            state = {"run_id": "terminal", "formal_ready": True,
                     "analysis_identity_sha256": "sha256:fixture", "task_scope": []}
            baseline = root / "docs/testing/mvg/baseline.json"
            atomic_json(baseline, {"untouched": True})
            before = baseline.read_bytes()
            with patch.object(plan_mvg, "_load_run", return_value=(run_dir / "run.json", state)), \
                 patch.object(plan_mvg, "_validate_input_freshness"), \
                 patch.object(plan_mvg, "inspect_isolated_runner", return_value={}), \
                 patch.object(plan_mvg, "_task_ids", return_value=set()), \
                 patch.object(plan_mvg, "_task_view_rows", return_value=[]), \
                 patch("_mvg_capability_generation.generate_append", return_value={
                     "status": "blocked", "errors": [{"code": "fixture_hard_issue"}]}) as append, \
                 patch.object(plan_mvg, "run_isolated_model") as model:
                with self.assertRaisesRegex(ValueError, "selection_blocked_insufficient_admitted_candidates"):
                    plan_mvg.generate(root, run_id="terminal", timeout_sec=1, llm_backend="codex-cli")
            self.assertEqual(3, append.call_count)
            model.assert_not_called()
            self.assertFalse((run_dir / "selection-workspace").exists())
            self.assertEqual(before, baseline.read_bytes())
            saved = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            receipt = json.loads((run_dir / "model-execution.json").read_text(encoding="utf-8"))
            self.assertEqual("blocked", saved["selection_status"])
            self.assertEqual("codex-cli", receipt["backend"])
            self.assertEqual(3, len(receipt["candidate_failures"]))

    def test_corrupt_execution_receipt_cannot_prevent_selection_block(self):
        with tempfile.TemporaryDirectory() as temp:
            run_dir = Path(temp)
            (run_dir / "model-execution.json").write_text("{broken", encoding="utf-8")
            state = {"model_backend": "codex-cli", "selected_candidate": "candidate-1"}
            with self.assertRaisesRegex(ValueError, "selection_blocked_insufficient_admitted_candidates"):
                _block_selection_for_insufficient_admitted_candidates(run_dir, state, [])
            saved = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            receipt = json.loads((run_dir / "model-execution.json").read_text(encoding="utf-8"))
            self.assertEqual("blocked", saved["selection_status"])
            self.assertNotIn("selected_candidate", saved)
            self.assertIn("previous_receipt_error", receipt)

    def test_blocked_selection_cannot_review_validate_or_apply_historical_winner(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = root / "logs/ci/mvg-planning/stale-winner"
            state = {"schema_version": plan_mvg.RUN_SCHEMA, "run_id": "stale-winner",
                     "selection_status": "blocked",
                     "selection_block_reason": "selection_blocked_insufficient_admitted_candidates"}
            atomic_json(run_dir / "run.json", state)
            for name in ("proposal.json", "semantic-review.json", "semantic-review-execution.json", "apply-journal.json"):
                atomic_json(run_dir / name, {"historical": "preserve"})
            before = {path.name: path.read_bytes() for path in run_dir.iterdir() if path.is_file()}
            with patch.object(plan_mvg, "run_isolated_model") as model, \
                 patch("_planning_apply_journal.resume_journal") as resume, \
                 patch.object(plan_mvg, "validate_proposal") as validator:
                for operation in (
                    lambda: plan_mvg.review(root, run_id="stale-winner", runner=Path("fixture"), timeout_sec=1),
                    lambda: plan_mvg.validate(root, run_id="stale-winner"),
                    lambda: plan_mvg.apply(root, run_id="stale-winner", confirm=True),
                ):
                    with self.assertRaisesRegex(ValueError, "selection_blocked_insufficient_admitted_candidates"):
                        operation()
                model.assert_not_called()
                resume.assert_not_called()
                validator.assert_not_called()
            self.assertEqual(before, {path.name: path.read_bytes() for path in run_dir.iterdir() if path.is_file()})

    def test_atomic_generation_rejects_pollution_then_accepts_a_with_b_remaining(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = root / "logs/ci/mvg-planning/atomic"
            (run_dir / "analysis-input").mkdir(parents=True)
            state = {"run_id": "atomic", "formal_ready": True,
                     "generation_strategy": "independent-candidates-segmented",
                     "analysis_identity_sha256": "sha256:fixture", "task_scope": []}
            original = {"manifest_candidate": {"flows": [], "tests": []}, "coverage_table": [
                {"requirement_id": "FR-1", "rationale": "broken"},
                {"requirement_id": "FR-2", "rationale": "broken"}], "entrypoints": []}
            seeds = {}
            def errors(proposal):
                return [{"code": "coverage_missing:" + row["requirement_id"], "path": "coverage"}
                        for row in proposal.get("coverage_table", []) if row["rationale"] == "broken"]
            def validation(_root, _state, proposal):
                issues = errors(proposal)
                return {"status": "blocked" if issues else "passed", "formal_applicable": not issues,
                        "errors": [issue["code"] for issue in issues]}
            def segment(invoke, candidate_root, candidate_state, attempt, prompt, workspace, **kwargs):
                from copy import deepcopy
                base = kwargs.get("base_proposal")
                seeds.setdefault(candidate_root.name, []).append(deepcopy(base))
                value = deepcopy(original if base is None else base)
                if attempt in (2, 3):
                    value["coverage_table"][0]["rationale"] = "fixed"
                if attempt == 2:
                    value["coverage_table"][1]["rationale"] = "pollution"
                output = workspace / "proposal.json"
                atomic_json(output, value)
                return output, {}
            with patch.object(plan_mvg, "_load_run", return_value=(run_dir / "run.json", state)), \
                 patch.object(plan_mvg, "_validate_input_freshness"), \
                 patch.object(plan_mvg, "inspect_isolated_runner", return_value={}), \
                 patch.object(plan_mvg, "_task_ids", return_value=set()), \
                 patch.object(plan_mvg, "_task_view_rows", return_value=[]), \
                 patch.object(plan_mvg, "invoke_segmented", side_effect=segment), \
                 patch.object(plan_mvg, "validate_proposal", side_effect=validation), \
                 patch.object(plan_mvg, "candidate_admission_errors", side_effect=lambda _r, _s, p, *_: errors(p)), \
                 patch.object(plan_mvg, "run_admission_semantic_gate") as reviewer, \
                 patch.object(plan_mvg, "MVG_REPLACEMENT_ROUND_LIMIT", 0):
                with self.assertRaisesRegex(ValueError, "replacement budget exhausted"):
                    plan_mvg.generate(root, run_id="atomic", timeout_sec=1, llm_backend="codex-cli")
            reviewer.assert_not_called()
            self.assertEqual("selection-blocked-insufficient-admitted-candidates", state["phase"])
            self.assertEqual("selection_blocked_insufficient_admitted_candidates", state["selection_block_reason"])
            self.assertEqual("replacement_round_budget_exhausted", state["admission_stop_reason"])
            receipt = json.loads((run_dir / "model-execution.json").read_text(encoding="utf-8"))
            self.assertEqual("selection_blocked_insufficient_admitted_candidates", receipt["selection_error"])
            self.assertEqual("codex-cli", receipt["backend"])
            self.assertEqual(3, len(receipt["candidate_failures"]))
            for label, values in seeds.items():
                self.assertEqual(original, values[2], "Rejected proposal must never become the next seed")
                self.assertEqual("fixed", values[3]["coverage_table"][0]["rationale"])
                self.assertEqual("broken", values[3]["coverage_table"][1]["rationale"])
                marker = json.loads((run_dir / "candidates" / label / "proposal-attempt-2-acceptance.json").read_text(encoding="utf-8"))
                self.assertEqual("rejected", marker["status"])

    def test_failed_slot_is_replaced_before_initial_siblings_finish(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = root / "logs/ci/mvg-planning/immediate"
            (run_dir / "analysis-input").mkdir(parents=True)
            state = {"run_id": "immediate", "formal_ready": True,
                     "generation_strategy": "independent-candidates-segmented",
                     "analysis_identity_sha256": "sha256:fixture", "task_scope": []}
            replacement_started = threading.Event()
            observed = []
            def segment(invoke, candidate_root, candidate_state, attempt, prompt, workspace, **kwargs):
                if "--candidate-1-r2" in candidate_root.name:
                    self.assertIsNone(kwargs.get("base_proposal"))
                    self.assertIsNone(kwargs.get("repair_issue"))
                    replacement_started.set()
                elif candidate_root.name in {"candidate-2", "candidate-3"}:
                    observed.append(replacement_started.wait(3))
                raise RuntimeError("Fixture execution stops")
            with patch.object(plan_mvg, "_load_run", return_value=(run_dir / "run.json", state)), \
                 patch.object(plan_mvg, "_validate_input_freshness"), \
                 patch.object(plan_mvg, "inspect_isolated_runner", return_value={}), \
                 patch.object(plan_mvg, "_task_ids", return_value=set()), \
                 patch.object(plan_mvg, "_task_view_rows", return_value=[]), \
                 patch.object(plan_mvg, "invoke_segmented", side_effect=segment), \
                 patch.object(plan_mvg, "MVG_REPLACEMENT_ROUND_LIMIT", 1):
                with self.assertRaisesRegex(ValueError, "replacement budget exhausted"):
                    plan_mvg.generate(root, run_id="immediate", timeout_sec=1, llm_backend="codex-cli")
            self.assertEqual([True, True], observed)
            self.assertEqual(1, state["replacement_rounds_used"])

    def test_semantic_atomic_repair_requires_fresh_gate_before_seed_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = root / "logs/ci/mvg-planning/semantic-atomic"
            (run_dir / "analysis-input").mkdir(parents=True)
            state = {"run_id": "semantic-atomic", "formal_ready": True,
                     "generation_strategy": "independent-candidates-segmented",
                     "analysis_identity_sha256": "sha256:fixture", "task_scope": []}
            seeds, reviews = {}, {}
            base = {"manifest_candidate": {"flows": [], "tests": []}, "entrypoints": [], "coverage_table": [
                {"requirement_id": "FR-1", "rationale": "broken"},
                {"requirement_id": "FR-2", "rationale": "broken"}]}
            def segment(invoke, candidate_root, candidate_state, attempt, prompt, workspace, **kwargs):
                from copy import deepcopy
                proposal = deepcopy(kwargs.get("base_proposal") or base)
                seeds.setdefault(candidate_root.name, []).append(deepcopy(proposal))
                if attempt == 2:
                    proposal["coverage_table"][0]["rationale"] = "fixed"
                output = workspace / "proposal.json"
                atomic_json(output, proposal)
                return output, {}
            def gate(_root, _state, proposal, workspace, **kwargs):
                reviews.setdefault(workspace.parent.name, []).append(plan_mvg.canonical_sha(proposal))
                return {"proposal_sha256": plan_mvg.canonical_sha(proposal), "issues": [
                    {"code": "semantic_review_blocked:coverage_reviews:" + row["requirement_id"],
                     "path": "coverage_reviews"} for row in proposal["coverage_table"] if row["rationale"] == "broken"]}
            with patch.object(plan_mvg, "_load_run", return_value=(run_dir / "run.json", state)), \
                 patch.object(plan_mvg, "_validate_input_freshness"), \
                 patch.object(plan_mvg, "inspect_isolated_runner", return_value={}), \
                 patch.object(plan_mvg, "_task_ids", return_value=set()), \
                 patch.object(plan_mvg, "_task_view_rows", return_value=[]), \
                 patch.object(plan_mvg, "invoke_segmented", side_effect=segment), \
                 patch.object(plan_mvg, "validate_proposal", return_value={"status": "passed", "formal_applicable": True, "errors": []}), \
                 patch.object(plan_mvg, "candidate_admission_errors", side_effect=lambda _r, _s, _p, review=None: (review or {}).get("issues", [])), \
                 patch.object(plan_mvg, "run_admission_semantic_gate", side_effect=gate), \
                 patch.object(plan_mvg, "MVG_REPLACEMENT_ROUND_LIMIT", 0):
                with self.assertRaisesRegex(ValueError, "replacement budget exhausted"):
                    plan_mvg.generate(root, run_id="semantic-atomic", timeout_sec=1, llm_backend="codex-cli")
            for label, rows in seeds.items():
                self.assertGreaterEqual(len(rows), 2)
                self.assertGreaterEqual(len(rows), 3)
                self.assertEqual("fixed", rows[2]["coverage_table"][0]["rationale"])
                self.assertEqual("broken", rows[2]["coverage_table"][1]["rationale"])
                self.assertNotEqual(reviews[label][0], reviews[label][1])


    def test_delta_failure_does_not_invoke_semantic_reviewer(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = root / "logs/ci/mvg-planning/delta-first"
            (run_dir / "analysis-input").mkdir(parents=True)
            state = {"run_id": "delta-first", "formal_ready": True,
                     "generation_strategy": "independent-candidates-segmented",
                     "analysis_identity_sha256": "sha256:fixture", "task_scope": []}

            def segment(invoke, candidate_root, candidate_state, attempt, prompt, workspace, **kwargs):
                output = workspace / "proposal.json"
                atomic_json(output, {"manifest_candidate": {"flows": []}})
                return output, {}

            with patch.object(plan_mvg, "_load_run", return_value=(run_dir / "run.json", state)), \
                 patch.object(plan_mvg, "_validate_input_freshness"), \
                 patch.object(plan_mvg, "inspect_isolated_runner", return_value={}), \
                 patch.object(plan_mvg, "_task_ids", return_value=set()), \
                 patch.object(plan_mvg, "_task_view_rows", return_value=[]), \
                 patch.object(plan_mvg, "invoke_segmented", side_effect=segment), \
                 patch.object(plan_mvg, "validate_proposal", return_value={"status": "passed"}), \
                 patch.object(plan_mvg, "candidate_admission_errors", return_value=[{
                     "code": "delta_validation_blocked", "path": "manifest", "detail": "Missing authority."}]), \
                 patch.object(plan_mvg, "run_admission_semantic_gate", return_value={}) as reviewer, \
                 patch.object(plan_mvg, "MVG_REPLACEMENT_ROUND_LIMIT", 0):
                with self.assertRaisesRegex(ValueError, "replacement budget exhausted"):
                    plan_mvg.generate(root, run_id="delta-first", timeout_sec=1, llm_backend="codex-cli")
            reviewer.assert_not_called()

    def test_execution_failed_sibling_does_not_stop_other_candidates(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = root / "logs/ci/mvg-planning/stop-siblings"
            (run_dir / "analysis-input").mkdir(parents=True)
            state = {"run_id": "stop-siblings", "formal_ready": True,
                     "generation_strategy": "independent-candidates-segmented",
                     "analysis_identity_sha256": "sha256:fixture", "task_scope": []}
            failed = threading.Event()

            def write(path, value):
                atomic_json(path, value)
                if path == run_dir / "run.json" and any(
                    row.get("event") == "admission-execution-failed"
                    for row in value.get("admission_events", [])):
                    failed.set()

            def segment(invoke, candidate_root, candidate_state, attempt, prompt, workspace, **kwargs):
                if candidate_root.name == "candidate-1":
                    raise ValueError("Fixture runner output schema failure")
                self.assertTrue(failed.wait(3), "Execution failure was not published")
                output, execution = invoke("Sibling must not run", attempt, output_name="segments/flow.json")
                return output, execution

            def runner(_runner, *, output_path, **kwargs):
                atomic_json(output_path, {})
                return {"model": "fixture", "model_tools": []}

            with patch.object(plan_mvg, "_load_run", return_value=(run_dir / "run.json", state)), \
                 patch.object(plan_mvg, "_validate_input_freshness"), \
                 patch.object(plan_mvg, "inspect_isolated_runner", return_value={}), \
                 patch.object(plan_mvg, "_task_ids", return_value=set()), \
                 patch.object(plan_mvg, "_task_view_rows", return_value=[]), \
                 patch.object(plan_mvg, "atomic_json", side_effect=write), \
                 patch.object(plan_mvg, "invoke_segmented", side_effect=segment), \
                 patch.object(plan_mvg, "validate_proposal", return_value={"status": "blocked", "errors": ["bad"]}), \
                 patch.object(plan_mvg, "run_isolated_model", side_effect=runner) as model:
                with self.assertRaisesRegex(ValueError, "replacement budget exhausted"):
                    plan_mvg.generate(root, run_id="stop-siblings", timeout_sec=1, llm_backend="codex-cli")
            self.assertGreaterEqual(model.call_count, 2)
            self.assertEqual("blocked", state["selection_status"])

    def test_recovered_delta_failure_does_not_invoke_semantic_reviewer(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = root / "logs/ci/mvg-planning/recovered-delta"
            (run_dir / "analysis-input").mkdir(parents=True)
            state = {"run_id": "recovered-delta", "formal_ready": True,
                     "generation_strategy": "independent-candidates-segmented",
                     "analysis_identity_sha256": "sha256:fixture", "task_scope": [],
                     "candidate_attempts": {}}
            proposal = {"manifest_candidate": {"flows": []}}
            for label in plan_mvg.MVG_CANDIDATE_LABELS:
                atomic_json(run_dir / "candidates" / label / "proposal-attempt-1.json", proposal)
                state["candidate_attempts"][label] = {"attempts": [{"attempt": 1, "status": "completed"}]}

            def segment(invoke, candidate_root, candidate_state, attempt, prompt, workspace, **kwargs):
                output = workspace / "proposal.json"
                atomic_json(output, proposal)
                return output, {}

            with patch.object(plan_mvg, "_load_run", return_value=(run_dir / "run.json", state)), \
                 patch.object(plan_mvg, "_validate_input_freshness"), \
                 patch.object(plan_mvg, "inspect_isolated_runner", return_value={}), \
                 patch.object(plan_mvg, "_task_ids", return_value=set()), \
                 patch.object(plan_mvg, "_task_view_rows", return_value=[]), \
                 patch.object(plan_mvg, "invoke_segmented", side_effect=segment), \
                 patch.object(plan_mvg, "validate_proposal", return_value={"status": "passed", "formal_applicable": True}), \
                 patch.object(plan_mvg, "candidate_admission_errors", return_value=[{
                     "code": "delta_validation_blocked", "path": "manifest", "detail": "Missing authority."}]), \
                 patch.object(plan_mvg, "run_admission_semantic_gate", return_value={}) as reviewer, \
                 patch.object(plan_mvg, "MVG_REPLACEMENT_ROUND_LIMIT", 0):
                with self.assertRaisesRegex(ValueError, "replacement budget exhausted"):
                    plan_mvg.generate(root, run_id="recovered-delta", timeout_sec=1, llm_backend="codex-cli")
            reviewer.assert_not_called()

    def test_running_sibling_call_finishes_independently(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = root / "logs/ci/mvg-planning/inflight-sibling"
            (run_dir / "analysis-input").mkdir(parents=True)
            state = {"run_id": "inflight-sibling", "formal_ready": True,
                     "generation_strategy": "independent-candidates-segmented",
                     "analysis_identity_sha256": "sha256:fixture", "task_scope": []}
            started, failed = threading.Event(), threading.Event()
            calls = []

            def write(path, value):
                atomic_json(path, value)
                if path == run_dir / "run.json" and any(
                    row.get("candidate") == "candidate-1" and row.get("event") == "admission-execution-failed"
                    for row in value.get("admission_events", [])):
                    failed.set()

            def segment(invoke, candidate_root, candidate_state, attempt, prompt, workspace, **kwargs):
                if candidate_root.name == "candidate-1":
                    self.assertTrue(started.wait(3))
                    raise ValueError("Fixture transport failed")
                if candidate_root.name == "candidate-3":
                    self.assertTrue(failed.wait(3))
                output, execution = invoke("In-flight fixture", attempt, output_name="segments/flow.json")
                return output, execution

            def runner(_runner, *, workspace, output_path, **kwargs):
                calls.append(workspace)
                started.set()
                self.assertTrue(failed.wait(3))
                atomic_json(output_path, {"manifest_candidate": {"flows": []}})
                return {"model": "fixture", "model_tools": []}

            with patch.object(plan_mvg, "_load_run", return_value=(run_dir / "run.json", state)), \
                 patch.object(plan_mvg, "_validate_input_freshness"), \
                 patch.object(plan_mvg, "inspect_isolated_runner", return_value={}), \
                 patch.object(plan_mvg, "_task_ids", return_value=set()), \
                 patch.object(plan_mvg, "_task_view_rows", return_value=[]), \
                 patch.object(plan_mvg, "atomic_json", side_effect=write), \
                 patch.object(plan_mvg, "invoke_segmented", side_effect=segment), \
                 patch.object(plan_mvg, "validate_proposal", return_value={"status": "passed"}), \
                 patch.object(plan_mvg, "run_isolated_model", side_effect=runner), \
                 patch.object(plan_mvg, "run_admission_semantic_gate") as reviewer:
                with self.assertRaisesRegex(ValueError, "replacement budget exhausted"):
                    plan_mvg.generate(root, run_id="inflight-sibling", timeout_sec=1, llm_backend="codex-cli")
            self.assertGreaterEqual(len(calls), 2)
            self.assertTrue((calls[0] / "flow.json").is_file(), "Running call evidence must be retained")
            self.assertGreater(reviewer.call_count, 0)
            self.assertNotEqual("candidate_sibling_execution_failed",
                                (state["candidate_admissions"].get("candidate-2") or {}).get("execution_error", {}).get("error_type"))
            self.assertEqual("blocked", state["selection_status"])

    def test_deterministic_retirement_creates_clean_replacement_without_review_proof(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = root / "logs/ci/mvg-planning/retirement"
            (run_dir / "analysis-input").mkdir(parents=True)
            state = {"run_id": "retirement", "formal_ready": True,
                     "generation_strategy": "independent-candidates-segmented",
                     "analysis_identity_sha256": "sha256:fixture", "task_scope": []}
            starts = []

            def segment(invoke, candidate_root, candidate_state, attempt, prompt, workspace, **kwargs):
                if attempt == 1:
                    starts.append((candidate_root.name, kwargs.get("base_proposal"),
                                   kwargs.get("repair_issue")))
                output = workspace / "proposal.json"
                atomic_json(output, {"schema_version": plan_mvg.PROPOSAL_SCHEMA,
                                     "analysis_identity_sha256": "sha256:fixture"})
                return output, {}

            with patch.object(plan_mvg, "_load_run", return_value=(run_dir / "run.json", state)), \
                 patch.object(plan_mvg, "_validate_input_freshness"), \
                 patch.object(plan_mvg, "inspect_isolated_runner", return_value={}), \
                 patch.object(plan_mvg, "_task_ids", return_value=set()), \
                 patch.object(plan_mvg, "_task_view_rows", return_value=[]), \
                 patch.object(plan_mvg, "invoke_segmented", side_effect=segment), \
                 patch.object(plan_mvg, "validate_proposal", return_value={
                     "status": "blocked", "formal_applicable": False, "errors": ["coverage_bad"]}), \
                 patch.object(plan_mvg, "MVG_REPLACEMENT_ROUND_LIMIT", 1):
                with self.assertRaisesRegex(ValueError, "replacement budget exhausted"):
                    plan_mvg.generate(root, run_id="retirement", timeout_sec=1,
                                      llm_backend="codex-cli")
            self.assertEqual(6, len(starts))
            self.assertEqual(3, sum("--candidate-" in name for name, _, _ in starts))
            self.assertTrue(all(base is None and issue is None for _, base, issue in starts))
            for admission in state["candidate_admissions"].values():
                self.assertEqual("retired", admission["status"])
                self.assertIsNone(admission["execution_error"])
                self.assertEqual([3], list(admission["issue_attempts"].values()))

    def test_segment_schema_is_inside_actual_model_sandbox(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = root / "logs/ci/mvg-planning/schema-boundary"
            (run_dir / "analysis-input").mkdir(parents=True)
            atomic_json(run_dir / "analysis-input" / "large-auxiliary.json",
                        {"unrelated": "x" * 1100000})
            state = {"run_id": "schema-boundary", "formal_ready": True,
                     "generation_strategy": "independent-candidates-segmented",
                     "analysis_identity_sha256": "sha256:fixture", "task_scope": []}
            boundaries = []
            schema = {"type": "object", "additionalProperties": False,
                      "properties": {}, "required": []}

            def segment(invoke, candidate_root, candidate_state, attempt, prompt, workspace, **kwargs):
                invoke("Fixture section", attempt, output_name="segments/flow.json",
                       output_schema_path=workspace / "segment-schemas/flow.json",
                       output_schema=schema)

            def runner(_runner, *, workspace, output_schema, **kwargs):
                boundaries.append((workspace.resolve(), output_schema.resolve(),
                                   json.loads(output_schema.read_text(encoding="utf-8"))))
                self.assertFalse((workspace / "analysis-input").exists(),
                                 "Inline segment context must not include the full prepared bundle")
                raise RuntimeError("Fixture stops before any model invocation")

            with patch.object(plan_mvg, "_load_run", return_value=(run_dir / "run.json", state)), \
                 patch.object(plan_mvg, "_validate_input_freshness"), \
                 patch.object(plan_mvg, "inspect_isolated_runner", return_value={}), \
                 patch.object(plan_mvg, "_task_ids", return_value=set()), \
                 patch.object(plan_mvg, "_task_view_rows", return_value=[]), \
                 patch.object(plan_mvg, "invoke_segmented", side_effect=segment), \
                 patch.object(plan_mvg, "run_isolated_model", side_effect=runner), \
                 patch.object(plan_mvg, "MVG_REPLACEMENT_ROUND_LIMIT", 0):
                with self.assertRaisesRegex(ValueError, "replacement budget exhausted"):
                    plan_mvg.generate(root, run_id="schema-boundary", timeout_sec=1,
                                      llm_backend="codex-cli")
            self.assertEqual(3, len(boundaries))
            for workspace, schema_path, actual in boundaries:
                self.assertTrue(schema_path.is_relative_to(workspace),
                                f"Schema {schema_path} escapes model sandbox {workspace}")
                self.assertEqual(schema, actual)

    def test_selection_receipt_requires_bound_runner_and_output_identity(self):
        state = {"analysis_identity_sha256": "sha256:analysis"}
        selection = {"selected": "A", "status": "selected"}
        receipt = {
            "schema_version": "newrouge.mvg-selection-execution-receipt.v1",
            "analysis_identity_sha256": "sha256:analysis",
            "attempt": 1,
            "selection_input_sha256": "sha256:inputs",
            "output_sha256": "sha256:output",
            "runner_info": {
                "schema_version": "newrouge.isolated-model-runner.v1",
                "model": "fixture-model", "filesystem_scope": "workspace_only",
                "fresh_session_per_invocation": True, "can_read_outside_workspace": False,
                "model_tools": [],
            },
            "runner_receipt": {"model": "fixture-model", "model_tools": []},
        }
        errors = validate_selection_execution_receipt(
            state, selection, receipt,
            selection_input_sha256="sha256:inputs",
            output_sha256="sha256:actual-output",
        )
        self.assertIn("selection_output_identity_invalid", errors)

    def test_selection_receipt_rejects_runner_model_or_tools_drift(self):
        state = {"analysis_identity_sha256": "sha256:analysis"}
        selection = {"selected": "A", "status": "selected"}
        receipt = {
            "schema_version": "newrouge.mvg-selection-execution-receipt.v1",
            "analysis_identity_sha256": "sha256:analysis",
            "attempt": 1,
            "selection_input_sha256": "sha256:inputs",
            "output_sha256": "sha256:output",
            "runner_info": {
                "schema_version": "newrouge.isolated-model-runner.v1",
                "model": "fixture-model", "filesystem_scope": "workspace_only",
                "fresh_session_per_invocation": True, "can_read_outside_workspace": False,
                "model_tools": [],
            },
            "runner_receipt": {"model": "other-model", "model_tools": ["shell"]},
        }
        errors = validate_selection_execution_receipt(
            state, selection, receipt,
            selection_input_sha256="sha256:inputs",
            output_sha256="sha256:output",
        )
        self.assertIn("selection_runner_identity_invalid", errors)

    def test_selection_receipt_allows_environment_default_runner_model(self):
        receipt = {
            "schema_version": "newrouge.mvg-selection-execution-receipt.v1",
            "analysis_identity_sha256": "sha256:analysis", "attempt": 1,
            "selection_input_sha256": "sha256:inputs", "output_sha256": "sha256:output",
            "runner_info": {
                "schema_version": "newrouge.isolated-model-runner.v1",
                "model": "auto", "filesystem_scope": "workspace_only",
                "fresh_session_per_invocation": True, "can_read_outside_workspace": False,
                "model_tools": [],
            },
            "runner_receipt": {"model": "gpt-6-sol", "model_tools": []},
        }
        self.assertEqual([], validate_selection_execution_receipt(
            {"analysis_identity_sha256": "sha256:analysis"},
            {"selected": "A", "status": "selected"}, receipt,
            selection_input_sha256="sha256:inputs", output_sha256="sha256:output",
            expected_attempt=1))

    def test_selection_receipt_malformed_runner_payload_is_recoverable_error(self):
        state = {"analysis_identity_sha256": "sha256:analysis"}
        errors = validate_selection_execution_receipt(
            state, {"selected": "A", "status": "selected"},
            {
                "schema_version": "newrouge.mvg-selection-execution-receipt.v1",
                "analysis_identity_sha256": "sha256:analysis",
                "attempt": 1,
                "selection_input_sha256": "sha256:inputs",
                "output_sha256": "sha256:output",
                "runner_info": ["bad"],
                "runner_receipt": "not-an-object",
            },
            selection_input_sha256="sha256:inputs",
            output_sha256="sha256:output",
        )
        self.assertIn("selection_runner_description_invalid", errors)
        self.assertIn("selection_runner_identity_invalid", errors)
    def test_attempt_budget_does_not_expand_on_resume(self):
        self.assertEqual([], list(candidate_attempt_numbers(64, segmented=True)))
        self.assertEqual([3], list(candidate_attempt_numbers(2, segmented=False)))

    def test_resume_scans_persisted_attempts_before_allocating_new_attempts(self):
        self.assertEqual([1, 2, 3], candidate_resume_attempt_numbers(2, segmented=False))
        self.assertEqual(list(range(1, 65)), candidate_resume_attempt_numbers(64, segmented=True))

    def test_candidate_invocation_budget_is_durable_and_bounded(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for _ in range(3):
                self.assertEqual(_, reserve_candidate_model_invocation(root, "candidate-1", "candidate-1-r1") - 1)
            state = json.loads((root / "lineage-execution.json").read_text(encoding="utf-8"))
            self.assertEqual(3, state["model_invocation_count"])
            atomic_json(root / "lineage-execution.json", {
                "candidate": "candidate-1", "lineage": "candidate-1-r1",
                "model_invocation_count": plan_mvg.MVG_CANDIDATE_INVOCATION_LIMIT,
            })
            with self.assertRaisesRegex(plan_mvg.MVGCandidateInvocationBudgetError, "64 model invocations"):
                reserve_candidate_model_invocation(root, "candidate-1", "candidate-1-r1")

    def test_candidate_repair_overflow_is_rejected_by_lineage_stop_loss(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for _ in range(plan_mvg.MVG_CANDIDATE_INVOCATION_LIMIT):
                reserve_candidate_model_invocation(root, "candidate-1", "candidate-1-r1")
            with self.assertRaisesRegex(plan_mvg.MVGCandidateInvocationBudgetError, "64 model invocations"):
                reserve_candidate_model_invocation(root, "candidate-1", "candidate-1-r1")

    def test_candidate_has_unfinished_repair_stops_at_three_attempts(self):
        issue = {"code": "semantic_review_not_approved", "path": "semantic-review"}
        issue_id = admission_issue_id(issue["code"], issue["path"])
        state = {"candidate_admissions": {"candidate-1": {
            "status": "repairing", "issues": [issue], "current_issue": issue,
            "issue_attempts": {issue_id: 2},
        }}}
        self.assertTrue(plan_mvg.candidate_has_unfinished_repair(state, "candidate-1"))
        state["candidate_admissions"]["candidate-1"]["issue_attempts"][issue_id] = 3
        self.assertFalse(plan_mvg.candidate_has_unfinished_repair(state, "candidate-1"))

    def test_repair_reservation_is_shared_durable_and_per_stable_issue(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = {"code": "segment_flow_change_review_missing:flow-a", "path": "segment.flows"}
            second = {"code": "segment_flow_requirement_missing:flow-a", "path": "segment.flows"}
            reserve = getattr(plan_mvg, "reserve_issue_repair", None)
            self.assertTrue(callable(reserve), "shared repair reservation is missing")
            self.assertEqual([1, 2, 3], [reserve(root, first) for _ in range(3)])
            self.assertIsNone(reserve(root, first))
            self.assertEqual(1, reserve(root, second))
            self.assertIsNone(reserve(Path(str(root)), first), "resume must not reset reservations")

    def test_checkpoint_does_not_charge_pre_reserved_repair_twice(self):
        issue = {"code": "bad-route", "path": "routing"}
        key = admission_issue_id(issue["code"], issue["path"])
        result = advance_admission_state(
            {"issues": [issue], "issue_attempts": {key: 1}}, [issue],
            repaired=False, count_repair=False)
        self.assertEqual(1, result["issue_attempts"][key])

    def test_candidate_invocation_reservations_are_atomic_under_segment_concurrency(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
                reservations = list(executor.map(
                    lambda _: reserve_candidate_model_invocation(root, "candidate-1", "candidate-1-r1"),
                    range(32),
                ))
            self.assertEqual(list(range(1, 33)), sorted(reservations))
            state = json.loads((root / "lineage-execution.json").read_text(encoding="utf-8"))
            self.assertEqual(32, state["model_invocation_count"])

    def test_candidate_admission_artifacts_must_stay_inside_candidate_workspace(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_dir = root / "logs/ci/mvg-planning/run-1"
            candidate = run_dir / "candidates/candidate-1"
            candidate.mkdir(parents=True)
            for name in ("admission-review.json", "admission-execution.json"):
                (candidate / name).write_text("{}", encoding="utf-8")
            record = {
                "workspace": "candidates/candidate-1",
                "review_path": (candidate / "admission-review.json").relative_to(root).as_posix(),
                "review_execution_path": (candidate / "admission-execution.json").relative_to(root).as_posix(),
            }
            proposal, proof, execution = plan_mvg._bound_admission_artifacts(root, run_dir, record)
            self.assertEqual(candidate / "proposal.json", proposal)
            self.assertEqual(candidate / "admission-review.json", proof)
            record["review_path"] = (run_dir.parent / "outside.json").as_posix()
            with self.assertRaisesRegex(ValueError, "escapes its workspace"):
                plan_mvg._bound_admission_artifacts(root, run_dir, record)

    def test_selected_incumbent_keeps_workspace_bound_for_idempotent_generation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_id = "incumbent-idempotent"
            run_dir = root / "logs/ci/mvg-planning" / run_id
            incumbent = run_dir / "incumbent-admission"
            incumbent.mkdir(parents=True)
            proposal = {"schema_version": plan_mvg.PROPOSAL_SCHEMA,
                        "analysis_identity_sha256": "sha256:analysis",
                        "manifest_candidate": {"flows": []}}
            atomic_json(run_dir / "proposal.json", proposal)
            atomic_json(incumbent / "proposal.json", proposal)
            proof = incumbent / "semantic-review.json"
            execution = incumbent / "gate-incumbent/semantic-review-execution.json"
            atomic_json(proof, {"verdict": "approved"})
            atomic_json(execution, {})
            admission = {"candidate": "incumbent", "lineage": "incumbent-r1",
                         "status": "admitted", "workspace": "incumbent-admission",
                         "proposal_sha256": plan_mvg.canonical_sha(proposal),
                         "review_path": proof.relative_to(root).as_posix(),
                         "review_execution_path": execution.relative_to(root).as_posix(),
                         "proof_sha256": plan_mvg.file_sha(proof),
                         "execution_sha256": plan_mvg.file_sha(execution)}
            state = {"run_id": run_id, "formal_ready": True,
                     "analysis_identity_sha256": "sha256:analysis",
                     "selection_status": "selected", "selected_candidate": "incumbent",
                     "selected_admission_review": {
                         "path": admission["review_path"],
                         "execution_path": admission["review_execution_path"],
                         "proposal_sha256": admission["proposal_sha256"],
                         "proof_sha256": admission["proof_sha256"],
                         "execution_sha256": admission["execution_sha256"],
                     },
                     "candidate_admissions": {"incumbent": admission}}
            run_path = run_dir / "run.json"
            with patch.object(plan_mvg, "_load_run", return_value=(run_path, state)), \
                 patch.object(plan_mvg, "_validate_input_freshness"), \
                 patch.object(plan_mvg, "validate_proposal", return_value={
                     "status": "passed", "formal_applicable": True}), \
                 patch.object(plan_mvg, "candidate_admission_errors", return_value=[]), \
                 patch("_mvg_planning_review.review_execution_errors", return_value=[]):
                result = plan_mvg.generate(root, run_id=run_id, timeout_sec=1, llm_backend="codex-cli")
            self.assertEqual("incumbent", result["selected"])

    def test_replacement_round_budget_is_persisted_and_bounded(self):
        state = {}
        self.assertEqual(1, reserve_replacement_round(state))
        self.assertEqual(2, reserve_replacement_round(state))
        self.assertEqual(3, reserve_replacement_round(state))
        self.assertIsNone(reserve_replacement_round(state))
        self.assertEqual(3, state["replacement_rounds_used"])

    def test_latest_attempt_artifact_uses_numeric_attempt_order(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            early = root / "attempt-2" / "semantic-review-execution.json"
            late = root / "attempt-10" / "semantic-review-execution.json"
            early.parent.mkdir(parents=True)
            late.parent.mkdir(parents=True)
            early.write_text("{}", encoding="utf-8")
            late.write_text("{}", encoding="utf-8")
            self.assertEqual(late, _latest_attempt_artifact([early, late]))

    def test_admission_execution_discovery_uses_review_key_and_numeric_attempt(self):
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "admission-review"
            expected = workspace / "gate-attempt-10" / "semantic-review-execution.json"
            stale = workspace / "gate-attempt-10" / "attempt-10" / "semantic-review-execution.json"
            expected.parent.mkdir(parents=True)
            stale.parent.mkdir(parents=True)
            expected.write_text("{}", encoding="utf-8")
            stale.write_text("{}", encoding="utf-8")

            discover = getattr(plan_mvg, "_admission_execution_artifact", None)
            self.assertTrue(callable(discover), "admission execution discovery helper is missing")
            self.assertEqual(expected, discover(workspace, "attempt-10"))

    def test_execution_failed_event_restores_execution_failure(self):
        restored = restore_admission_checkpoint({}, [{
            "candidate": "candidate-1", "lineage": "candidate-1-r1",
            "event": "admission-execution-failed", "error": {"error_type": "runner_timeout"},
        }], candidate="candidate-1", lineage="candidate-1-r1")
        self.assertEqual("execution-failed", restored.get("status"))
        self.assertEqual("runner_timeout", restored["execution_error"]["error_type"])

    def test_admission_execution_receipt_is_bound_to_semantic_output(self):
        from _mvg_planning_review import review_execution_errors
        proposal = {"manifest_candidate": {"flows": []}}
        review = {"verdict": "approved"}
        state = {"analysis_identity_sha256": "sha256:analysis"}
        execution = {
            "analysis_identity_sha256": "sha256:analysis", "proposal_sha256": plan_mvg.canonical_sha(proposal),
            "runner_info": {"schema_version": "newrouge.isolated-model-runner.v1", "model": "fixture",
                "filesystem_scope": "workspace_only", "fresh_session_per_invocation": True,
                "can_read_outside_workspace": False, "model_tools": []},
            "receipt": {"model": "fixture", "model_tools": []},
            "semantic_review_sha256": "sha256:other-review",
        }
        self.assertIn("independent_semantic_review_output_identity_invalid",
                      review_execution_errors(state, proposal, execution, review))

    def test_selector_input_identity_changes_when_any_scored_proposal_changes(self):
        candidates = {"A": "sha256:a1", "B": "sha256:b1", "C": "sha256:c1"}
        lineages = {"candidate-1": "candidate-1-r1", "candidate-2": "candidate-2-r1",
                    "candidate-3": "candidate-3-r1"}
        _, original = build_selection_input_identity(
            "sha256:analysis", candidates, lineages, incumbent_present=False)
        replacement_candidates = dict(candidates, A="sha256:a2")
        _, replacement = build_selection_input_identity(
            "sha256:analysis", replacement_candidates, lineages, incumbent_present=False)
        self.assertNotEqual(original, replacement)

        incumbent = dict(candidates, D="sha256:d1")
        _, original_with_incumbent = build_selection_input_identity(
            "sha256:analysis", incumbent, lineages, incumbent_present=True)
        changed_incumbent = dict(incumbent, D="sha256:d2")
        _, changed_incumbent_identity = build_selection_input_identity(
            "sha256:analysis", changed_incumbent, lineages, incumbent_present=True)
        self.assertNotEqual(original_with_incumbent, changed_incumbent_identity)

    def test_admission_checkpoint_restores_issue_attempts_from_event_journal(self):
        prior = {"candidate": "candidate-1", "lineage": "candidate-1-r1",
                 "status": "repairing", "issues": [], "issue_attempts": {}}
        restored = restore_admission_checkpoint(prior, [{
            "candidate": "candidate-1", "lineage": "candidate-1-r1",
            "event": "admission-issue", "issue": {"code": "bad-flow", "path": "flows[0]"},
            "issue_attempts": {"bad-flow@flows[0]": 2}, "status": "repairing",
        }], candidate="candidate-1", lineage="candidate-1-r1")
        self.assertEqual(2, restored["issue_attempts"]["bad-flow@flows[0]"])
        self.assertEqual("bad-flow", restored["issues"][0]["code"])

    def test_retired_checkpoint_is_not_reopened_by_restore(self):
        prior = {"candidate": "candidate-1", "lineage": "candidate-1-r1",
                 "status": "repairing", "issues": [], "issue_attempts": {}}
        restored = restore_admission_checkpoint(prior, [{
            "candidate": "candidate-1", "lineage": "candidate-1-r1",
            "event": "admission-issue", "issue": {"code": "bad-flow", "path": "flows[0]"},
            "issue_attempts": {"bad-flow@flows[0]": 3}, "status": "retired",
        }], candidate="candidate-1", lineage="candidate-1-r1")
        self.assertEqual("retired", restored["status"])

    def test_candidate_retired_event_restores_terminal_state(self):
        prior = {"candidate": "candidate-1", "lineage": "candidate-1-r1",
                 "status": "repairing", "issues": [], "issue_attempts": {}}
        restored = restore_admission_checkpoint(prior, [{
            "candidate": "candidate-1", "lineage": "candidate-1-r1",
            "event": "candidate-retired", "issues": [{"code": "bad-flow", "path": "proposal"}],
            "issue_attempts": {"bad-flow@proposal": 3},
            "retirement_reason": "repair_attempt_limit_exhausted",
        }], candidate="candidate-1", lineage="candidate-1-r1")
        self.assertEqual("retired", restored["status"])
        self.assertEqual("repair_attempt_limit_exhausted", restored["retirement_reason"])
        self.assertEqual(3, restored["issue_attempts"]["bad-flow@proposal"])

    def test_admission_gate_uses_bounded_projection_and_publication_with_fake_runner(self):
        with tempfile.TemporaryDirectory() as temp:
            root, run_dir, state, proposal = self.admission_fixture(temp)
            calls = []

            def fake_invoke(prompt, attempt, *, output_name=None, output_schema_path=None,
                            output_schema=None):
                calls.append(attempt)
                target = root / "fake-runner" / f"attempt-{attempt}.json"
                atomic_json(target, {
                    "schema_version": "newrouge.mvg-semantic-review.v1",
                    "analysis_identity_sha256": state['analysis_identity_sha256'],
                    "proposal_sha256": plan_mvg.canonical_sha(proposal),
                    "verdict": "approved", "findings": [],
                    "requirement_reviews": [{**proposal['coverage_table'][0], "requirement_id": "R1", "verdict": "covered",
                                              "rationale": "Flow covers the requirement."}],
                    "flow_reviews": [{"flow_id": "flow-a", "verdict": "sound",
                                      "rationale": "Boundary is observable."}],
                })
                return target, {"receipt": {"model": "fake", "model_tools": []}}

            result = run_admission_semantic_gate(
                root, state, proposal, run_dir / "candidate-admission",
                runner=None, timeout_sec=5, invoke=fake_invoke)
            self.assertEqual("approved", result["verdict"])
            publication = list((run_dir / "candidate-admission").rglob("semantic-review-publication-*.json"))
            self.assertEqual(1, len(publication))
            checkpoint = json.loads(publication[0].read_text(encoding="utf-8"))
            self.assertEqual("complete", checkpoint["status"])
            self.assertTrue((run_dir / "candidate-admission" / "gate-default" / "attempt-1" / "analysis-input" / "review-evidence.json").is_file())

            isolated = run_admission_semantic_gate(
                root, state, proposal, run_dir / "candidate-admission",
                runner=None, timeout_sec=5, invoke=fake_invoke, review_key="attempt-2")
            self.assertEqual("approved", isolated["verdict"])
            self.assertEqual([1, 1], calls)
            default_publications = list(
                (run_dir / "candidate-admission" / "gate-default").glob(
                    "semantic-review-publication-*.json"))
            isolated_publications = list(
                (run_dir / "candidate-admission" / "gate-attempt-2").glob(
                    "semantic-review-publication-*.json"))
            self.assertEqual(1, len(default_publications))
            self.assertEqual(1, len(isolated_publications))
            self.assertNotEqual(default_publications[0], isolated_publications[0])

    def test_admission_gate_rejects_empty_prepared_requirements_before_model_call(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_id = "admission-empty-requirements"
            run_dir = root / "logs/ci/mvg-planning" / run_id
            analysis = run_dir / "analysis-input"
            analysis.mkdir(parents=True)
            atomic_json(analysis / "semantic-requirements.v1.json", {"requirements": []})
            state = {"run_id": run_id, "analysis_identity_sha256": "sha256:analysis"}
            invoke = unittest.mock.Mock()
            with self.assertRaisesRegex(ValueError, "prepared semantic requirements snapshot"):
                run_admission_semantic_gate(
                    root, state, {"manifest_candidate": {"flows": []}}, run_dir / "admission",
                    runner=None, timeout_sec=5, invoke=invoke,
                )
            invoke.assert_not_called()

    def _exercise_accounting_echo_retry(self, *, verdict="approved", always_invalid=False,
                                       before_invoke=None):
        with tempfile.TemporaryDirectory() as temp:
            root, run_dir, state, proposal = self.admission_fixture(temp)
            calls = []

            def invoke(prompt, attempt, **kwargs):
                calls.append(attempt)
                review = {
                    "schema_version": "newrouge.mvg-semantic-review.v1",
                    "analysis_identity_sha256": state['analysis_identity_sha256'],
                    "proposal_sha256": plan_mvg.canonical_sha(proposal),
                    "verdict": verdict, "findings": [] if verdict == "approved" else ["Missing executable boundary."],
                    "requirement_reviews": [{"requirement_id": "R1", "verdict": "covered" if verdict == "approved" else "blocked",
                        "rationale": "The journey covers the requirement.", "disposition": "flow",
                        "flow_id": "flow-a", "sink_id": None, "authority_ref": None,
                        "verification_ref": "test-id" if attempt == 1 or always_invalid else None,
                        "route": "flow"}],
                    "flow_reviews": [{"flow_id": "flow-a", "verdict": "sound" if verdict == "approved" else "blocked", "rationale": "Boundary review."}],
                }
                output = root / f"review-{attempt}.json"
                atomic_json(output, review)
                return output, {"receipt": {"model": "fixture", "model_tools": []}}

            original_hash = plan_mvg.canonical_sha(proposal)
            if always_invalid:
                with self.assertRaises(plan_mvg.MVGReviewAttemptBudgetError):
                    run_admission_semantic_gate(root, state, proposal, run_dir / "admission",
                                                runner=None, timeout_sec=1, invoke=invoke)
                self.assertEqual(list(range(1, plan_mvg.MVG_REVIEW_ATTEMPT_LIMIT + 1)), calls)
                gate = run_dir / "admission/gate-default"
                attempts = json.loads((gate / "semantic-review-attempts.json").read_text(encoding="utf-8"))["attempts"]
                self.assertEqual(10, len(attempts))
                self.assertTrue(all(row["error_type"].startswith("runner_") for row in attempts))
                self.assertFalse(list(gate.glob("semantic-review-publication-*.json")))
                self.assertEqual(original_hash, plan_mvg.canonical_sha(proposal))
                return
            if before_invoke:
                with self.assertRaises(plan_mvg.MVGGenerationStoppedError):
                    run_admission_semantic_gate(root, state, proposal, run_dir / "admission",
                                                runner=Path("fixture-runner.py"), timeout_sec=1,
                                                before_invoke=before_invoke)
                self.assertEqual([], calls)
                return
            review = run_admission_semantic_gate(root, state, proposal, run_dir / "admission",
                                                runner=None, timeout_sec=1, invoke=invoke)
            self.assertEqual([1, 2], calls)
            self.assertIsNone(review["requirement_reviews"][0]["verification_ref"])
            self.assertEqual(verdict, review["verdict"])
            self.assertEqual(original_hash, plan_mvg.canonical_sha(proposal))

    def test_admission_retries_accounting_echo_error_without_regenerating_proposal(self):
        self._exercise_accounting_echo_retry()

    def test_admission_format_repair_preserves_real_semantic_block(self):
        self._exercise_accounting_echo_retry(verdict="blocked")

    def test_admission_persistent_echo_error_exhausts_review_only(self):
        self._exercise_accounting_echo_retry(always_invalid=True)

    def test_admission_stop_signal_does_not_consume_review_retry_budget(self):
        def stop():
            raise plan_mvg.MVGGenerationStoppedError("Sibling execution failed")

        with patch.object(plan_mvg, "inspect_isolated_runner", return_value={}):
            self._exercise_accounting_echo_retry(before_invoke=stop)

    def test_admission_cli_schema_binds_echo_but_not_semantic_verdict(self):
        from _planning_skill_common import validate_output_schema
        state = {"analysis_identity_sha256": "sha256:analysis"}
        proposal = {"manifest_candidate": {"flows": [{"id": "flow-a"}]},
                    "coverage_table": [{"requirement_id": "R1", "disposition": "flow",
                                        "flow_id": "flow-a", "verification_ref": None}]}
        review = {
            "schema_version": "newrouge.mvg-semantic-review.v1",
            "analysis_identity_sha256": "sha256:analysis",
            "proposal_sha256": plan_mvg.canonical_sha(proposal),
            "verdict": "blocked", "findings": ["Missing boundary."],
            "requirement_reviews": [{"requirement_id": "R1", "verdict": "blocked",
                "rationale": "Missing boundary.", "disposition": "flow", "flow_id": "flow-a",
                "sink_id": None, "authority_ref": None, "verification_ref": None,
                "route": "flow", "repair_action": "repair_sections"}],
            "flow_reviews": [{"flow_id": "flow-a", "verdict": "blocked", "rationale": "Missing boundary."}],
        }
        with tempfile.TemporaryDirectory() as temp:
            output, schema = Path(temp) / "review.json", Path(temp) / "schema.json"
            atomic_json(schema, plan_mvg.semantic_review_output_schema(state=state, proposal=proposal))
            atomic_json(output, review)
            validate_output_schema(output, schema)
            review["requirement_reviews"][0]["verification_ref"] = "test-id"
            atomic_json(output, review)
            with self.assertRaisesRegex(ValueError, "does not satisfy JSON schema"):
                validate_output_schema(output, schema)

    def test_admission_repairs_one_issue_before_advancing_to_next(self):
        state = {"candidate": "candidate-1", "lineage": "candidate-1-r1",
                 "issues": [{"code": "missing-owner", "path": "flows[0]"},
                            {"code": "bad-test", "path": "tests[0]"}],
                 "issue_attempts": {}}
        for attempt in range(1, MVG_REPAIR_ATTEMPT_LIMIT + 1):
            state = advance_admission_state(state,
                                             ["bad-test"] if attempt == MVG_REPAIR_ATTEMPT_LIMIT
                                             else ["missing-owner", "bad-test"],
                                             repaired=(attempt == MVG_REPAIR_ATTEMPT_LIMIT))
        self.assertEqual("bad-test", state["current_issue"]["code"])
        self.assertEqual(0, state["issue_attempts"][admission_issue_id("bad-test", "tests[0]")])

    def test_initial_hard_issue_does_not_consume_repair_budget(self):
        state = {"candidate": "candidate-1", "lineage": "candidate-1-r1",
                 "issues": [], "issue_attempts": {}}
        state = advance_admission_state(state, ["missing-owner"], repaired=False)
        self.assertEqual(0, state["issue_attempts"][admission_issue_id("missing-owner")])

    def test_issue_reordering_does_not_mark_previous_issue_repaired(self):
        state = {"candidate": "candidate-1", "lineage": "candidate-1-r1",
                 "issues": [{"code": "missing-owner", "path": "flows[0]"},
                            {"code": "bad-test", "path": "tests[0]"}],
                 "issue_attempts": {}}
        result = advance_admission_state(
            state, [{"code": "bad-test", "path": "tests[0]"},
                    {"code": "missing-owner", "path": "flows[0]"}], repaired=True)
        self.assertEqual("missing-owner", result["current_issue"]["code"])
        self.assertIn(admission_issue_id("missing-owner", "flows[0]"),
                      {admission_issue_id(row["code"], row["path"]) for row in result["issues"]})
        self.assertEqual(1, result["issue_attempts"][admission_issue_id("missing-owner", "flows[0]")])

    def test_resumed_admission_preserves_current_issue_details_and_order(self):
        state = {"candidate": "candidate-1", "lineage": "candidate-1-r1",
                 "issues": [{"code": "missing-owner", "path": "flows[0]",
                             "detail": "producer and consumer system roles are not explicit"},
                            {"code": "bad-test", "path": "tests[0]",
                             "detail": "selector is not a class name"}],
                 "current_issue": {"code": "missing-owner", "path": "flows[0]",
                                   "detail": "producer and consumer system roles are not explicit"},
                 "issue_attempts": {}}
        build_prompt = getattr(plan_mvg, "admission_repair_prompt", None)
        self.assertTrue(callable(build_prompt), "admission recovery prompt helper is missing")
        prompt = build_prompt("BASE", "CONTRACT", state)
        self.assertTrue(prompt.startswith("BASE\nCONTRACT\n"))
        self.assertIn("missing-owner:flows[0]: producer and consumer system roles are not explicit", prompt)
        self.assertNotIn("bad-test:tests[0]", prompt)

    def test_segment_route_identity_failure_is_candidate_local_repair_issue(self):
        error = plan_mvg.MVGSegmentRoutingError(
            "MVG segment flows identity invalid: "
            "segment_flow_change_review_missing:combat-reward-return"
        )
        issues = plan_mvg.segment_route_validation_issues(error)
        self.assertEqual([{
            "code": "segment_flow_change_review_missing:combat-reward-return",
            "path": "segment.flows",
            "detail": "segment_flow_change_review_missing:combat-reward-return",
        }], issues)
        self.assertNotEqual("runner_identity_invalid", plan_mvg.classify_review_error(error))

    def test_unparseable_segment_failure_remains_execution_failure(self):
        error = ValueError("MVG segment flows failed after retries: output schema mismatch")
        self.assertEqual([], plan_mvg.segment_route_validation_issues(error))
        self.assertNotEqual("candidate_segment_route_invalid", plan_mvg.classify_review_error(error))

    def test_issue_queue_preserves_focused_semantic_detail_after_reordering(self):
        current = {"code": "missing-owner", "path": "flows[0]", "detail": "Name the receiving system."}
        result = advance_admission_state(
            {"issues": [current], "issue_attempts": {}},
            [{"code": "bad-test", "path": "tests[0]"}, current], repaired=False)
        self.assertEqual(current, result["current_issue"])

    def test_admission_retires_after_three_failed_repairs_and_replacement_is_clean(self):
        state = {"candidate": "candidate-1", "lineage": "candidate-1-r1",
                 "issues": [{"code": "missing-owner", "path": "flows[0]"}],
                 "issue_attempts": {}}
        result = state
        for _ in range(MVG_REPAIR_ATTEMPT_LIMIT):
            result = advance_admission_state(result, ["missing-owner"], repaired=False)
        self.assertEqual("retired", result["status"])
        replacement = fresh_replacement_lineage(result, "candidate-1")
        self.assertNotEqual(result["lineage"], replacement["lineage"])
        self.assertEqual({}, replacement["issue_attempts"])
        self.assertNotIn("proposal", replacement)
        self.assertNotIn("findings", replacement)

    def test_semantic_blocked_verdict_is_not_a_format_failure(self):
        from _mvg_planning_review import semantic_review_errors
        state = {"analysis_identity_sha256": "sha256:analysis"}
        proposal = {"manifest_candidate": {"flows": [{"id": "flow-a"}]}}
        review = {
            "schema_version": "newrouge.mvg-semantic-review.v1",
            "analysis_identity_sha256": "sha256:analysis",
            "proposal_sha256": plan_mvg.canonical_sha(proposal),
            "verdict": "blocked", "findings": ["Owner evidence is missing."],
            "requirement_reviews": [{"requirement_id": "FR-1", "verdict": "blocked",
                                     "rationale": "Owner evidence is missing."}],
            "flow_reviews": [{"flow_id": "flow-a", "verdict": "blocked",
                              "rationale": "Owner evidence is missing."}],
        }
        self.assertEqual([], validate_review_shape(
            state, proposal, review, requirement_ids={"FR-1"}, flow_ids={"flow-a"}))
        errors = semantic_review_errors(
            state, proposal, review, {"requirements": [{"requirement_id": "FR-1"}]})
        self.assertIn("semantic_review_not_approved", errors)
        self.assertNotIn("semantic_review_invalid_verdict:requirement_reviews", errors)
        self.assertNotIn("semantic_review_invalid_verdict:flow_reviews", errors)
        self.assertIn("semantic_review_blocked:requirement_reviews:FR-1", errors)
        self.assertIn("semantic_review_blocked:flow_reviews:flow-a", errors)

    def test_semantic_review_accounting_must_match_proposal_route_and_evidence(self):
        from _mvg_planning_review import semantic_review_errors
        state = {"analysis_identity_sha256": "sha256:analysis"}
        proposal = {
            "manifest_candidate": {"flows": [{"id": "flow-a"}]},
            "coverage_table": [{"requirement_id": "FR-1", "flow_id": "flow-a",
                                 "disposition": "other_verification", "sink_id": "sink-a",
                                 "verification_ref": "logs/report.json", "rationale": "verified"}],
        }
        review = {
            "schema_version": "newrouge.mvg-semantic-review.v1",
            "analysis_identity_sha256": "sha256:analysis",
            "proposal_sha256": plan_mvg.canonical_sha(proposal),
            "verdict": "approved", "findings": [],
            "requirement_reviews": [{"requirement_id": "FR-1", "verdict": "covered",
                "rationale": "covered", "disposition": "flow", "flow_id": "flow-b",
                "sink_id": "sink-b", "verification_ref": "logs/other.json",
                "authority_ref": None}],
            "flow_reviews": [{"flow_id": "flow-a", "verdict": "sound", "rationale": "sound"}],
        }
        errors = semantic_review_errors(
            state, proposal, review, {"requirements": [{"requirement_id": "FR-1"}]})
        self.assertIn("semantic_review_accounting_disposition_mismatch:FR-1", errors)
        self.assertIn("semantic_review_accounting_flow_mismatch:FR-1", errors)
        self.assertIn("semantic_review_accounting_sink_mismatch:FR-1", errors)
        self.assertIn("semantic_review_accounting_evidence_mismatch:FR-1", errors)
    def test_review_shape_requires_complete_requirement_and_flow_rows(self):
        state = {"analysis_identity_sha256": "sha256:analysis"}
        proposal = {"schema_version": "newrouge.mvg-planning-proposal.v1",
                    "manifest_candidate": {"flows": [{"id": "flow-a"}]}}
        review = {
            "schema_version": "newrouge.mvg-semantic-review.v1",
            "analysis_identity_sha256": "sha256:analysis",
            "proposal_sha256": plan_mvg.canonical_sha(proposal),
            "verdict": "approved",
            "findings": [],
            "requirement_reviews": [],
            "flow_reviews": [],
        }
        errors = validate_review_shape(
            state, proposal, review, requirement_ids={"FR-1"}, flow_ids={"flow-a"}
        )
        self.assertIn("semantic_review_incomplete:requirement_reviews", errors)
        self.assertIn("semantic_review_incomplete:flow_reviews", errors)

    def test_review_output_schema_is_strict_and_identity_fields_are_required(self):
        schema = plan_mvg.semantic_review_output_schema()
        self.assertTrue(schema["additionalProperties"] is False)
        self.assertIn("proposal_sha256", schema["required"])
        self.assertEqual("object", schema["type"])
        self.assertEqual("approved", schema["properties"]["verdict"]["enum"][0])

    def test_normalize_proposal_format_repairs_only_unambiguous_scalars(self):
        proposal = {
            "manifest_candidate": {
                "flows": [{"id": "flow-a", "task_ids": ["7"], "handoffs": [
                    {"producer_task": "7", "consumer_task": "7", "owner_task": "7"}
                ], "test_ids": "test-a"}],
                "tests": [{"id": "test-a", "min_tests": "1"}],
                "coverage": {"required_flow_ids": ["wrong"]},
            }
        }
        changed = normalize_proposal_format(proposal)
        self.assertGreater(changed, 0)
        self.assertEqual([7], proposal["manifest_candidate"]["flows"][0]["task_ids"])
        self.assertEqual(1, proposal["manifest_candidate"]["tests"][0]["min_tests"])
        self.assertEqual(["flow-a"], proposal["manifest_candidate"]["coverage"]["required_flow_ids"])

    def test_backfill_review_error_types_is_idempotent(self):
        state = {"semantic_review_attempts": [{
            "status": "execution-failed",
            "error": "isolated model runner failed: Input exceeds the maximum length",
        }]}
        self.assertTrue(backfill_review_error_types(state))
        self.assertEqual("runner_input_too_large", state["semantic_review_attempts"][0]["error_type"])
        self.assertFalse(backfill_review_error_types(state))

    def test_coverage_skeleton_accounts_for_every_delivery_requirement(self):
        semantics = {"requirements": [
            {"requirement_id": "FR-1", "delivery_relevant": True, "status": "active", "source_block_ids": ["SB-1"]},
            {"requirement_id": "NFR-1", "delivery_relevant": True, "status": "active", "source_block_ids": ["SB-2"]},
        ]}
        views = [{"taskmaster_id": 7, "semantic_refs": ["FR-1", "NFR-1"], "capability_refs": ["CAP-A"]}]
        result = build_coverage_skeleton(semantics, views)
        self.assertEqual(["FR-1", "NFR-1"], [row["requirement_id"] for row in result])
        self.assertTrue(all(row["disposition"] == "flow" for row in result))

    def test_entrypoint_skeleton_does_not_invent_runtime_apis_from_task_ids(self):
        result = build_entrypoint_skeleton([7, 42])
        self.assertEqual([], result)

    def test_flow_evidence_tasks_do_not_require_runtime_entrypoints(self):
        from _mvg_planning_review import coverage_errors
        proposal = {"manifest_candidate": self.manifest(), **self.accounting()}
        proposal["manifest_candidate"]["flows"][0]["task_ids"].extend([44, 103])
        with tempfile.TemporaryDirectory() as folder:
            errors = coverage_errors(Path(folder), proposal,
                {"requirements": [{"requirement_id": "RQ-1"}]},
                {"capabilities": [{"capability_id": "CAP-A", "requirement_ids": ["RQ-1"]}]}, [])
        self.assertEqual([], errors)

    def test_coverage_allows_multiple_routes_but_rejects_duplicate_authority_rows(self):
        from _mvg_planning_review import coverage_errors
        first = {"id": "flow-a", "requirement_ids": ["RQ-1"],
                 "capability_refs": ["CAP-A"], "task_ids": [7], "handoffs": []}
        second = {"id": "flow-b", "requirement_ids": ["RQ-1"],
                  "capability_refs": ["CAP-A"], "task_ids": [7], "handoffs": []}
        coverage = {"requirement_id": "RQ-1", "disposition": "flow", "flow_id": "flow-a",
                    "capability_ref": "CAP-A", "task_id": 7, "rationale": "Covered."}
        proposal = {"manifest_candidate": {"flows": [first, second]},
                    "coverage_table": [coverage, dict(coverage)], "entrypoints": []}
        with tempfile.TemporaryDirectory() as folder:
            errors = coverage_errors(
                Path(folder), proposal,
                {"requirements": [{"requirement_id": "RQ-1"}]},
                {"capabilities": [{"capability_id": "CAP-A", "requirement_ids": ["RQ-1"]}]},
                [],
            )
        self.assertNotIn("flow_requirement_multiple_routes:RQ-1", errors)
        self.assertIn("coverage_requirement_duplicate:RQ-1", errors)

    def test_candidate_repair_routes_to_affected_requirement_and_flow_sections(self):
        requests = [
            {"section": "flows", "scope_id": "flow-a", "requirement_ids": ["RQ-1"]},
            {"section": "flows", "scope_id": "flow-b", "requirement_ids": ["RQ-2"]},
            {"section": "coverage", "requirement_ids": ["RQ-1", "RQ-2"]},
            {"section": "coverage", "requirement_ids": ["RQ-3"]},
            {"section": "entrypoints", "flow_scope_ids": ["flow-a"]},
            {"section": "tests", "flow_scope_ids": ["flow-a"]},
            {"section": "tests", "flow_scope_ids": ["flow-b"]},
        ]
        proposal = {"manifest_candidate": {"flows": [
            {"id": "flow-a", "requirement_ids": ["RQ-1"]},
            {"id": "flow-b", "requirement_ids": ["RQ-2"]},
        ]}}
        indexes = plan_mvg.route_candidate_repair_requests(
            requests, {"code": "semantic_review_blocked:requirement_reviews:RQ-1"}, proposal)
        self.assertEqual({1, 3, 5, 6}, indexes)
        flow_indexes = plan_mvg.route_candidate_repair_requests(
            requests, {"code": "semantic_review_blocked:flow_reviews:flow-b"}, proposal)
        self.assertEqual({2, 7}, flow_indexes)

    def test_entrypoint_prompt_is_driven_by_flow_boundaries_not_task_count(self):
        prompt = segment_prompt(section="entrypoints", identity="sha256:x",
            requirements=[], task_ids=[44, 103], flow_context=[])
        self.assertIn("Task IDs are evidence owners, not runtime API obligations", prompt)
        self.assertIn("test or governance task", prompt)

    def test_flow_scope_rejects_requirement_membership_outside_selected_capability(self):
        with self.assertRaisesRegex(ValueError, "selected Capability"):
            build_flow_scopes({"requirements": [{"requirement_id": "RQ-1",
                "capability_ids": ["CAP-STALE"]}]}, {"capabilities": []}, [], [])

    def test_entrypoint_flow_context_preserves_handoffs_and_implementation_paths(self):
        flow = self.manifest()["flows"][0]
        summary = plan_mvg._flow_summaries([flow])[0]
        self.assertEqual(flow["handoffs"], summary.get("handoffs"))
        self.assertEqual(flow["source_paths"], summary.get("source_paths"))

    def test_data_contract_cannot_be_used_as_runtime_entrypoint(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self._root(folder)
            proposal = {"schema_version": plan_mvg.PROPOSAL_SCHEMA,
                "analysis_identity_sha256": "sha256:x", "planning_status": "ready_for_validation",
                "manifest_candidate": self.manifest(), "gaps": [], **self.accounting()}
            proposal["entrypoints"][0]["path"] = "Game.Core/Contracts/Save/ContinueMetadata.cs"
            result = validate_proposal(root, {"run_id": "contract",
                "analysis_identity_sha256": "sha256:x",
                "capabilities_path": "docs/planning/semantic-topology/capabilities.v1.json"}, proposal)
        self.assertIn("entrypoint_non_executable_evidence:Game.Core/Contracts/Save/ContinueMetadata.cs",
            result["errors"])

    def test_runtime_flow_cannot_borrow_an_unrelated_flow_entrypoint(self):
        from _mvg_planning_review import coverage_errors
        proposal = {"manifest_candidate": self.manifest(), **self.accounting()}
        proposal["entrypoints"] = [{"owner_task": 99}]
        with tempfile.TemporaryDirectory() as folder:
            errors = coverage_errors(Path(folder), proposal,
                {"requirements": [{"requirement_id": "RQ-1"}]},
                {"capabilities": [{"capability_id": "CAP-A", "requirement_ids": ["RQ-1"]}]}, [])
        self.assertIn("flow_runtime_entrypoint_missing:flow-a", errors)

    def test_incumbent_without_legacy_entrypoints_remains_comparable(self):
        from _mvg_planning_review import coverage_errors
        proposal = {"manifest_candidate": self.manifest(), **self.accounting(),
                    "entrypoints": [], "notes": ["Current MVG incumbent projected for comparative evaluation."]}
        with tempfile.TemporaryDirectory() as folder:
            errors = coverage_errors(Path(folder), proposal,
                {"requirements": [{"requirement_id": "RQ-1"}]},
                {"capabilities": [{"capability_id": "CAP-A", "requirement_ids": ["RQ-1"]}]}, [])
        self.assertEqual([], errors)

    def test_test_segment_requests_are_one_flow_and_use_its_frozen_test_ids(self):
        requests = plan_mvg.build_test_segment_requests(
            [{"scope_id": "flow-a", "task_ids": [7]}, {"scope_id": "flow-b", "task_ids": [8]}],
            {"test_ids": ["a-test", "b-test"], "test_paths": ["Tests.Godot/tests/a.gd", "Tests.Godot/tests/b.gd"]},
            {"flows": [
                {"id": "flow-a", "test_ids": ["a-test"]},
                {"id": "flow-b", "test_ids": ["b-test"]},
            ]},
        )
        self.assertEqual(["flow-a", "flow-b"], [row["flow_scope_ids"][0] for row in requests])
        self.assertEqual([["a-test"], ["b-test"]], [row["test_ids"] for row in requests])

    def test_frozen_handoff_schema_uses_same_test_domain_as_flow(self):
        schema = plan_mvg.segment_output_schema(
            section="flows", identity="sha256:x", scope_id="map-node-owned-flow",
            allowed_test_ids=["map-route-domain", "map-route-scene"],
        )
        flow_item = schema["properties"]["flows"]["items"]
        self.assertEqual(
            ["map-route-domain", "map-route-scene"],
            flow_item["properties"]["test_ids"]["items"]["enum"],
        )
        handoff_item = flow_item["properties"]["handoffs"]["items"]
        self.assertEqual(
            ["map-route-domain", "map-route-scene"],
            handoff_item["properties"]["test_ids"]["items"].get("enum"),
        )

    def test_tests_prompt_forbids_cross_flow_and_cross_test_copying(self):
        prompt = plan_mvg.segment_prompt(
            section="tests", identity="sha256:x", requirements=[], task_ids=[7],
            flow_context=[{"id": "flow-a", "task_ids": [7]}], scope_id="tests-01",
            allow_exact_flow_id=True, allow_exact_test_id=True,
        )
        self.assertIn("exactly one flow", prompt)
        self.assertIn("Never emit a test for another flow", prompt)

    def test_correction_prompt_requests_restricted_patch(self):
        prompt = correction_prompt(["coverage_requirement_missing:FR-1"])
        self.assertIn("patch", prompt.lower())
        self.assertIn("coverage_additions", prompt)
        self.assertNotIn("completely corrected FULL proposal", prompt)

    def test_generation_prompt_mentions_non_droppable_skeleton(self):
        self.assertIn("coverage-skeleton.json", plan_mvg.PROMPT)
        self.assertIn("must not delete", plan_mvg.PROMPT)
        self.assertIn("exclusive Capability SSoT", plan_mvg.PROMPT)

    def test_mvg_selection_requires_all_candidates_and_allows_incumbent(self):
        schema = mvg_selection_output_schema(incumbent_present=True)
        self.assertEqual("newrouge.mvg-selection-review.v1", schema["properties"]["schema_version"]["const"])
        valid = {
            "schema_version": plan_mvg.MVG_SELECTION_SCHEMA,
            "selected": "D", "status": "selected",
            "candidate_reviews": [
                {"label": label, "verdict": "viable", "rationale": "Reviewed.", "rank": rank}
                for rank, label in enumerate(("D", "A", "B", "C"), 1)
            ],
            "tradeoffs": ["The incumbent preserves cumulative obligations."],
            "evidence_refs": ["analysis-input/capabilities.v1.json"],
            "rationale": "Retain the incumbent because the new proposals add no justified value.",
        }
        self.assertEqual([], validate_mvg_selection(valid,
            candidate_labels={"candidate-1", "candidate-2", "candidate-3"}, incumbent_present=True))
        invalid = dict(valid, candidate_reviews=valid["candidate_reviews"][:-1])
        self.assertIn("mvg_selection_review_incomplete", validate_mvg_selection(
            invalid, candidate_labels={"candidate-1", "candidate-2", "candidate-3"}, incumbent_present=True))

    def test_mvg_selection_prompt_routes_frozen_scope(self):
        prompt = plan_mvg.mvg_selection_prompt(
            incumbent_present=True,
            planning_scope={
                "scope_id": "m1-player-loop",
                "requirement_ids": ["FR-1"],
                "excluded_claims": ["Full M1 remains outside this manifest."],
            },
        )
        self.assertIn("Only the immutable planning scope is required", prompt)
        self.assertIn("must not be penalized", prompt)
        self.assertIn("FR-1", prompt)

    def test_frozen_manifest_preserves_existing_flows_and_tests(self):
        baseline = {
            "flows": [{"id": "flow-a", "handoffs": [{"producer_task": 1}],
                       "source_paths": ["Game.Core/A.cs"]}],
            "tests": [{"id": "test-a", "state": "implemented", "min_tests": 2,
                       "path": "Tests.Godot/tests/test_a.gd"}],
        }
        proposal = {"manifest_candidate": {
            "flows": [{"id": "flow-a", "handoffs": [{"producer_task": 9}]}],
            "tests": [{"id": "test-a", "state": "planned", "min_tests": 1}],
        }, "tests": [{"id": "test-a", "state": "planned", "min_tests": 1}]}
        result = preserve_frozen_manifest_baseline(
            proposal, baseline, {"flow_ids": ["flow-a"], "test_ids": ["test-a"]})
        self.assertEqual(baseline["flows"], result["manifest_candidate"]["flows"])
        self.assertEqual(baseline["tests"], result["manifest_candidate"]["tests"])
        self.assertEqual(baseline["tests"], result["tests"])

    def test_frozen_manifest_keeps_requirement_ownership_without_review(self):
        baseline = {"flows": [{"id": "flow-a", "requirement_ids": ["RQ-1"],
                               "capability_refs": ["CAP-A"], "task_ids": [7]}], "tests": []}
        scope = {"flow_ids": ["flow-a"], "test_ids": []}
        proposal = {"manifest_candidate": {"flows": [{
            "id": "flow-a", "requirement_ids": ["RQ-1", "RQ-2"],
            "capability_refs": ["CAP-A", "CAP-B"], "task_ids": [7],
        }], "tests": []}, "change_reviews": []}
        result = preserve_frozen_manifest_baseline(proposal, baseline, scope)
        flow = result["manifest_candidate"]["flows"][0]
        self.assertEqual(["RQ-1"], flow["requirement_ids"])
        self.assertEqual(["CAP-A"], flow["capability_refs"])

    def test_frozen_manifest_allows_explicitly_reviewed_requirement_ownership_change(self):
        baseline = {"flows": [{"id": "flow-a", "requirement_ids": ["RQ-1"],
                               "capability_refs": ["CAP-A"], "task_ids": [7]}], "tests": []}
        scope = {"flow_ids": ["flow-a"], "test_ids": []}
        proposal = {"manifest_candidate": {"flows": [{
            "id": "flow-a", "requirement_ids": ["RQ-1", "RQ-2"],
            "capability_refs": ["CAP-A", "CAP-B"], "task_ids": [7],
        }], "tests": []}, "change_reviews": [{
            "id": "flow-a", "reason": "Prepared specification changes the route ownership.",
            "authority_ref": "docs/gdd/spec.md#route",
            "authority_review": {"status": "reviewed", "rationale": "Source-backed review."},
        }]}
        result = preserve_frozen_manifest_baseline(proposal, baseline, scope)
        flow = result["manifest_candidate"]["flows"][0]
        self.assertEqual(["RQ-1", "RQ-2"], flow["requirement_ids"])
        self.assertEqual(["CAP-A", "CAP-B"], flow["capability_refs"])

    def test_mvg_selection_cannot_choose_blocked_candidate(self):
        result = {
            "schema_version": plan_mvg.MVG_SELECTION_SCHEMA,
            "selected": "A", "status": "selected",
            "candidate_reviews": [
                {"label": "A", "verdict": "blocked", "rationale": "Missing handoff evidence.", "rank": 1},
                {"label": "B", "verdict": "viable", "rationale": "Complete.", "rank": 2},
                {"label": "C", "verdict": "viable", "rationale": "Complete.", "rank": 3},
            ],
            "tradeoffs": ["B and C remain viable."],
            "evidence_refs": ["analysis-input/capabilities.v1.json"],
            "rationale": "The evaluator selected A despite its blocked verdict.",
        }
        self.assertIn("mvg_selection_review_verdict_invalid:A", validate_mvg_selection(
            result, candidate_labels={"candidate-1", "candidate-2", "candidate-3"}, incumbent_present=False))

    def test_mvg_selection_rejects_formally_inapplicable_candidate(self):
        result = {
            "schema_version": plan_mvg.MVG_SELECTION_SCHEMA,
            "selected": "A", "status": "selected",
            "candidate_reviews": [
                {"label": label, "verdict": "viable", "rationale": "Reviewed.", "rank": rank}
                for rank, label in enumerate(("A", "B", "C"), 1)
            ],
            "tradeoffs": ["A is preferred."],
            "evidence_refs": ["analysis-input/capabilities.v1.json"],
            "rationale": "Complete comparison.",
        }
        errors = validate_mvg_selection(
            result, candidate_labels={"candidate-1", "candidate-2", "candidate-3"},
            incumbent_present=False, viable_labels={"candidate-2", "candidate-3"},
        )
        self.assertIn("mvg_selection_selected_candidate_not_formally_applicable:A", errors)

    def test_mvg_selection_requires_unique_stable_ranked_reviews(self):
        result = {
            "schema_version": plan_mvg.MVG_SELECTION_SCHEMA,
            "selected": "B", "status": "selected",
            "candidate_reviews": [
                {"label": "B", "verdict": "viable", "rationale": "First choice.", "rank": 1},
                {"label": "A", "verdict": "viable", "rationale": "Second choice.", "rank": 2},
                {"label": "C", "verdict": "blocked", "rationale": "Incomplete.", "rank": 3},
            ],
            "tradeoffs": ["B is complete."], "evidence_refs": ["analysis-input/capabilities.v1.json"],
            "rationale": "B is the highest ranked viable proposal.",
        }
        self.assertIn("mvg_selection_review_verdict_invalid:C", validate_mvg_selection(
            result, candidate_labels={"candidate-1", "candidate-2", "candidate-3"},
            incumbent_present=False))
        duplicate_rank = json.loads(json.dumps(result))
        duplicate_rank["candidate_reviews"][2]["rank"] = 2
        self.assertIn("mvg_selection_review_rank_invalid", validate_mvg_selection(
            duplicate_rank, candidate_labels={"candidate-1", "candidate-2", "candidate-3"},
            incumbent_present=False))

    def test_mvg_selection_does_not_require_reviews_array_sorted_by_rank(self):
        result = {
            "schema_version": plan_mvg.MVG_SELECTION_SCHEMA,
            "selected": "B", "status": "selected",
            "candidate_reviews": [
                {"label": "A", "verdict": "viable", "rationale": "Viable.", "rank": 3},
                {"label": "B", "verdict": "viable", "rationale": "Preferred.", "rank": 1},
                {"label": "C", "verdict": "viable", "rationale": "Viable.", "rank": 2},
                {"label": "D", "verdict": "viable", "rationale": "Complete but lower ranked.", "rank": 4},
            ],
            "tradeoffs": ["B is preferred."],
            "evidence_refs": ["analysis-input/capabilities.v1.json"],
            "rationale": "B is the highest-ranked viable proposal.",
        }
        self.assertEqual([], validate_mvg_selection(
            result, candidate_labels={"candidate-1", "candidate-2", "candidate-3"},
            incumbent_present=True))

    def test_mvg_selection_rejects_non_object_review_rows_without_throwing(self):
        result = {
            "schema_version": plan_mvg.MVG_SELECTION_SCHEMA,
            "selected": None, "status": "no_valid_winner",
            "candidate_reviews": [None, None, None],
            "tradeoffs": ["No candidate is formally applicable."],
            "evidence_refs": ["analysis-input/capabilities.v1.json"],
            "rationale": "All candidate rows are malformed.",
        }
        errors = validate_mvg_selection(
            result, candidate_labels={"candidate-1", "candidate-2", "candidate-3"},
            incumbent_present=False)
        self.assertIn("mvg_selection_review_invalid", errors)

    def test_semantic_fallback_uses_ranked_viable_candidate_after_top_level_block(self):
        self.assertEqual(["candidate-3"], plan_mvg.ranked_semantic_fallback_candidates(
            {"candidate_reviews": [
                {"label": "C", "verdict": "viable", "rank": 2},
                {"label": "A", "verdict": "viable", "rank": 1},
                {"label": "B", "verdict": "blocked", "rank": 3},
            ]}, {"A": "candidate-1", "B": "candidate-2", "C": "candidate-3"},
            selected="candidate-1"))

    def test_incumbent_projection_keeps_current_capability_membership(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self._root(folder)
            manifest_path = root / "docs/testing/mvg/current.json"
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(json.dumps(self.manifest()), encoding="utf-8")
            run_dir = root / "logs/ci/mvg-planning/incumbent"
            prepared = run_dir / "analysis-input"
            prepared.mkdir(parents=True)
            for name in ("capabilities.v1.json", "semantic-requirements.v1.json"):
                source = (root / "docs/planning/semantic-topology/capabilities.v1.json"
                          if name.startswith("capabilities")
                          else root / "logs/ci/task-generation/semantic-requirements.v1.json")
                (prepared / name).write_bytes(source.read_bytes())
            semantics_path = prepared / "semantic-requirements.v1.json"
            semantics = json.loads(semantics_path.read_text(encoding="utf-8"))
            semantics["requirements"].append({"requirement_id": "RQ-OUTSIDE",
                "statement": "Outside frozen pilot scope.", "delivery_relevant": True,
                "status": "active"})
            atomic_json(semantics_path, semantics)
            atomic_json(prepared / "existing-manifest.json", self.manifest())
            atomic_json(prepared / "entrypoint-skeleton.json", {"rows": []})
            state = {"analysis_identity_sha256": "sha256:test",
                     "planning_scope": {"requirement_ids": ["RQ-1"]}}
            incumbent = plan_mvg._build_incumbent_proposal(
                root, run_dir, state, self.manifest(),
            )
            self.assertEqual(["RQ-1"], [row["requirement_id"] for row in incumbent["coverage_table"]])
            self.assertTrue(all(
                row.get("capability_ref") in {"CAP-A"}
                for row in incumbent["coverage_table"]
                if row.get("disposition") == "flow"
            ))
            self.assertIn("no Capability membership was inferred", " ".join(incumbent["notes"]))

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

    def test_segment_prompt_is_bounded_and_identity_bound(self):
        prompt = segment_prompt(section="coverage", identity="sha256:x", requirements=["FR-1"], task_ids=[7])
        self.assertIn(SEGMENT_SCHEMA, prompt)
        self.assertIn("FR-1", prompt)
        self.assertIn("return JSON only", prompt)
        self.assertNotIn("Read every file under analysis-input", prompt)
        self.assertIn("inline", prompt.lower())
        self.assertIn("Do not call shell/tools", prompt)
        self.assertIn("available_*_paths", prompt)
        self.assertIn("report a gap", prompt)

    def test_segment_prompt_requires_flow_assignment_for_coverage(self):
        prompt = segment_prompt(section="coverage", identity="sha256:x", requirements=["FR-1"],
                                task_ids=[7], flow_context=[{"id": "run-entry"}])
        self.assertIn("run-entry", prompt)
        self.assertIn("other_verification and deferred rows must leave flow_id null", prompt)

    def test_segment_identity_rejects_wrong_section_or_run(self):
        value = {"schema_version": SEGMENT_SCHEMA, "analysis_identity_sha256": "sha256:x", "section": "flows",
                 "flows": []}
        value["scope_id"] = "flow-a"
        self.assertEqual([], validate_segment_identity(value, section="flows", identity="sha256:x", scope_id="flow-a"))
        self.assertIn("segment_section_mismatch", validate_segment_identity(value, section="coverage", identity="sha256:x"))
        self.assertIn("segment_analysis_identity_mismatch", validate_segment_identity(value, section="flows", identity="sha256:y"))
        self.assertIn("segment_scope_mismatch", validate_segment_identity(value, section="flows", identity="sha256:x", scope_id="flow-b"))

    def test_segment_schema_binds_route_and_payload(self):
        schema = segment_output_schema(section="tests", identity="sha256:x", scope_id="tests-01")
        self.assertEqual(["schema_version", "analysis_identity_sha256", "section", "scope_id", "tests"],
                         schema["required"])
        self.assertEqual("tests-01", schema["properties"]["scope_id"]["const"])
        self.assertEqual("tests", schema["properties"]["section"]["const"])
        self.assertEqual("string", schema["properties"]["section"]["type"])
        self.assertEqual(2, len(schema["properties"]["tests"]["items"]["anyOf"]))
        self.assertTrue(all(item["type"] == "object" for item in schema["properties"]["tests"]["items"]["anyOf"]))
        self.assertTrue(all(item["additionalProperties"] is False
                            for item in schema["properties"]["tests"]["items"]["anyOf"]))
        self.assertTrue(schema["additionalProperties"] is False)

    def test_segment_schema_binds_manifest_value_domains(self):
        coverage = segment_output_schema(section="coverage", identity="sha256:x", scope_id="coverage-01")
        coverage_item = coverage["properties"]["coverage_table"]["items"]
        self.assertEqual(
            ["flow", "other_verification", "deferred"],
            coverage_item["properties"]["disposition"]["enum"],
        )
        self.assertEqual("string", coverage_item["properties"]["rationale"]["type"])

        entrypoints = segment_output_schema(section="entrypoints", identity="sha256:x", scope_id="entrypoints-01")
        entrypoint_item = entrypoints["properties"]["entrypoints"]["items"]
        self.assertEqual(["planned", "existing_verified"], entrypoint_item["properties"]["status"]["enum"])

        tests = segment_output_schema(section="tests", identity="sha256:x", scope_id="tests-01")
        test_item = tests["properties"]["tests"]["items"]
        self.assertEqual(2, len(test_item["anyOf"]))
        self.assertTrue(all(item["additionalProperties"] is False for item in test_item["anyOf"]))

        flow_item = segment_output_schema(section="flows", identity="sha256:x", scope_id="flow-01")[
            "properties"]["flows"]["items"]
        handoff_item = flow_item["properties"]["handoffs"]["items"]
        self.assertEqual("object", handoff_item["type"])
        self.assertEqual("string", handoff_item["properties"]["contract_ref"]["type"])
        self.assertEqual("array", handoff_item["properties"]["test_ids"]["type"])

    def test_segment_schema_binds_prepared_source_and_contract_paths(self):
        schema = segment_output_schema(
            section="flows", identity="sha256:x", scope_id="flow-01",
            available_source_paths=["docs/gdd/spec.md"],
            available_contract_paths=["Game.Core/Contracts/EventTypes.cs"],
        )
        flow_item = schema["properties"]["flows"]["items"]
        handoff_item = flow_item["properties"]["handoffs"]["items"]
        self.assertEqual(["docs/gdd/spec.md"], flow_item["properties"]["source_paths"]["items"]["enum"])
        self.assertEqual(["Game.Core/Contracts/EventTypes.cs"], handoff_item["properties"]["contract_ref"]["enum"])

    def test_segment_identity_rejects_invalid_manifest_value_domains(self):
        value = {
            "schema_version": SEGMENT_SCHEMA,
            "analysis_identity_sha256": "sha256:x",
            "section": "coverage",
            "scope_id": "coverage-01",
            "coverage_table": [{
                "requirement_id": "FR-1", "flow_id": "flow-a", "capability_ref": "CAP-A",
                "task_id": 7, "disposition": "covered", "rationale": "ok",
            }],
        }
        self.assertIn("segment_disposition_invalid", validate_segment_identity(
            value, section="coverage", identity="sha256:x", scope_id="coverage-01"))

    def test_bind_manifest_test_ids_uses_test_flow_routes(self):
        proposal = {"manifest_candidate": {"flows": [
            {"id": "flow-a", "test_ids": ["stale-a"], "handoffs": [{"test_ids": ["stale-a"]}]},
            {"id": "flow-b", "test_ids": [], "handoffs": []},
        ], "tests": []}}
        proposal["tests"] = [
            {"id": "test-a", "flow_id": "flow-a"},
            {"id": "test-b", "flow_id": "flow-b"},
        ]
        bind_manifest_test_ids(proposal)
        self.assertEqual(["test-a"], proposal["manifest_candidate"]["flows"][0]["test_ids"])
        self.assertEqual(["test-a"], proposal["manifest_candidate"]["flows"][0]["handoffs"][0]["test_ids"])
        self.assertEqual(["test-b"], proposal["manifest_candidate"]["flows"][1]["test_ids"])

    def test_bind_manifest_test_ids_preserves_unrouted_cumulative_baseline_flows(self):
        proposal = {"manifest_candidate": {"flows": [
            {"id": "baseline-flow", "test_ids": ["baseline-test"],
             "handoffs": [{"test_ids": ["baseline-test"]}]},
            {"id": "new-flow", "test_ids": ["model-only-test"], "handoffs": [{
                "test_ids": ["model-only-test"]
            }]},
        ]}, "tests": [{"id": "baseline-test"}]}
        proposal["tests"].append({"id": "new-test", "flow_id": "new-flow"})
        bind_manifest_test_ids(proposal, preserve_flow_ids={"baseline-flow"})
        flows = proposal["manifest_candidate"]["flows"]
        self.assertEqual(["baseline-test"], flows[0]["test_ids"])
        self.assertEqual(["baseline-test"], flows[0]["handoffs"][0]["test_ids"])
        self.assertEqual(["new-test"], flows[1]["test_ids"])

    def test_segment_merge_keeps_required_flow_ids_in_final_flow_order(self):
        merged = merge_planning_segments(
            {"manifest_candidate": {
                "coverage": {"required_flow_ids": ["baseline-flow"]},
                "flows": [{"id": "baseline-flow"}],
            }},
            [{"flows": [{"id": "new-flow"}]}],
        )
        self.assertEqual(
            ["baseline-flow", "new-flow"],
            merged["manifest_candidate"]["coverage"]["required_flow_ids"],
        )

    def test_delta_application_rebases_required_flow_order_to_applied_flow_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self._root(folder)
            existing = self.manifest()
            second_flow = json.loads(json.dumps(existing["flows"][0]))
            second_flow["id"] = "flow-b"
            existing["flows"].append(second_flow)
            existing["coverage"]["required_flow_ids"].append("flow-b")
            desired = json.loads(json.dumps(existing))
            desired["flows"] = list(reversed(desired["flows"]))
            desired["coverage"]["required_flow_ids"] = [
                row["id"] for row in desired["flows"]
            ]
            proposal = {
                "manifest_candidate": desired,
                "change_reviews": [],
                "retirement_reviews": [],
                "coverage_review": {},
            }
            delta = build_delta(existing, proposal)
            updated = apply_delta(existing, delta, root=root, validate_final=True)
            self.assertEqual(
                [row["id"] for row in updated["flows"]],
                updated["coverage"]["required_flow_ids"],
            )
            self.assertEqual(["flow-b", "flow-a"], desired["coverage"]["required_flow_ids"])
            self.assertEqual(["flow-a", "flow-b"], existing["coverage"]["required_flow_ids"])

    def test_delta_order_normalization_does_not_hide_missing_duplicate_or_unknown_flows(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self._root(folder)
            existing = self.manifest()
            second = json.loads(json.dumps(existing["flows"][0]))
            second["id"] = "flow-b"
            existing["flows"].append(second)
            existing["coverage"]["required_flow_ids"].append("flow-b")
            for required in (["flow-a"], ["flow-a", "flow-b", "flow-b"],
                             ["flow-a", "unknown-flow"]):
                with self.subTest(required=required):
                    desired = json.loads(json.dumps(existing))
                    desired["coverage"]["required_flow_ids"] = required
                    proposal = {"manifest_candidate": desired, "coverage_review": {
                        "authority_ref": "docs/gdd/spec.md",
                        "authority_review": {"status": "reviewed", "rationale": "Fixture only."},
                    }}
                    with self.assertRaises(ValueError):
                        apply_delta(existing, build_delta(existing, proposal), root=root, validate_final=True)

    def test_delta_order_normalization_handles_added_flow_without_changing_baseline_order(self):
        with tempfile.TemporaryDirectory() as folder:
            root = self._root(folder)
            existing = self.manifest()
            desired = json.loads(json.dumps(existing))
            added = json.loads(json.dumps(existing["flows"][0]))
            added["id"] = "flow-b"
            desired["flows"].insert(0, added)
            desired["coverage"]["required_flow_ids"] = ["flow-b", "flow-a"]
            updated = apply_delta(existing, build_delta(existing, {"manifest_candidate": desired}),
                                  root=root, validate_final=True)
            self.assertEqual(["flow-a", "flow-b"], updated["coverage"]["required_flow_ids"])
            self.assertEqual(["flow-a", "flow-b"], [row["id"] for row in updated["flows"]])

    def test_cumulative_baseline_tests_are_seeded_into_proposal_top_level(self):
        existing = {
            "flows": [{"id": "baseline-flow", "test_ids": ["baseline-test"],
                       "handoffs": [{"test_ids": ["baseline-test"]}]}],
            "tests": [{"id": "baseline-test"}],
            "coverage": {"required_flow_ids": ["baseline-flow"]},
        }
        seeded = merge_planning_segments(
            {"manifest_candidate": existing},
            [],
        )
        self.assertEqual(
            ["baseline-test"],
            [row["id"] for row in seeded["tests"]],
        )

    def test_contract_candidates_fall_back_to_real_paths_when_refs_are_event_ids(self):
        self.assertEqual(
            ["Game.Core/Contracts/EventTypes.cs"],
            _contract_candidates({"core.combat.started"}, ["Game.Core/Contracts/EventTypes.cs"]),
        )

    def test_segment_references_reject_unprepared_contract_and_existing_symbol(self):
        with tempfile.TemporaryDirectory() as folder:
            prepared = Path(folder)
            contract = prepared / "references/Game.Core/Contracts/EventTypes.cs"
            contract.parent.mkdir(parents=True)
            contract.write_text("class EventTypes {}", encoding="utf-8")
            value = {
                "flows": [{"source_paths": ["docs/gdd/spec.md"], "handoffs": [
                    {"contract_ref": "GAP: missing", "behavior": "x", "test_ids": ["t"]}
                ]}],
                "entrypoints": [{"status": "existing_verified", "path": "Tests.Godot/tests/test.gd",
                                 "symbol": "MissingSymbol"}],
            }
            errors = validate_segment_references(value, section="flows", prepared=prepared,
                                                 available_source_paths=["docs/gdd/spec.md"],
                                                 available_contract_paths=["Game.Core/Contracts/EventTypes.cs"])
            self.assertIn("segment_handoff_contract_unprepared", errors)
            errors = validate_segment_references(value, section="entrypoints", prepared=prepared,
                                                 available_source_paths=[], available_contract_paths=[])
            self.assertIn("segment_entrypoint_existing_unprepared", errors)

    def test_segment_routing_rejects_cross_scope_tasks_and_flow_file_refs(self):
        flow = {
            "id": "cap-a-01-flow",
            "requirement_ids": ["RQ-1"],
            "capability_refs": ["CAP-A"],
            "task_ids": [1, 2],
            "handoffs": [{
                "producer_task": 7,
                "consumer_task": 2,
                "owner_task": 2,
                "contract_ref": "Game.Core/Contracts/EventTypes.cs",
                "behavior": "handoff",
                "test_ids": ["test-a"],
            }],
        }
        errors = validate_segment_routing(flow | {"flows": [flow]}, section="flows", request={
            "scope_id": "cap-a-01", "requirement_ids": ["RQ-1"], "task_ids": [1, 2],
            "capabilities": [{"capability_id": "CAP-A"}],
        })
        self.assertIn("segment_handoff_tasks_outside_flow", errors)

        coverage = {
            "coverage_table": [{
                "requirement_id": "RQ-1", "flow_id": "cap-a-01-flow",
                "capability_ref": "CAP-A", "task_id": 1,
                "disposition": "flow", "rationale": "covered",
                "verification_ref": "task001-acceptance",
            }],
        }
        errors = validate_segment_routing(coverage, section="coverage", request={
            "scope_id": "coverage-01", "requirement_ids": ["RQ-1"], "task_ids": [1],
            "requirements": [{"requirement_id": "RQ-1", "capability_refs": ["CAP-A"]}],
        }, flow_context=[{"id": "cap-a-01-flow"}])
        self.assertIn("segment_coverage_flow_file_refs_forbidden", errors)

    def test_segment_routing_rejects_coverage_that_misses_flow_membership(self):
        coverage = {
            "coverage_table": [{
                "requirement_id": "RQ-1", "flow_id": "flow-a",
                "capability_ref": "CAP-A", "task_id": 1,
                "disposition": "flow", "rationale": "covered",
                "verification_ref": None, "authority_ref": None,
                "authority_review": None,
            }],
        }
        errors = validate_segment_routing(coverage, section="coverage", request={
            "scope_id": "coverage-01", "requirement_ids": ["RQ-1"],
            "task_ids": [1], "requirements": [{
                "requirement_id": "RQ-1", "capability_refs": ["CAP-A"],
            }],
        }, flow_context=[{
            "id": "flow-a", "requirement_ids": ["RQ-2"],
            "capability_refs": ["CAP-B"], "task_ids": [2],
        }])
        self.assertIn("segment_coverage_flow_membership_invalid", errors)

    def test_nullable_task_view_lists_are_treated_as_empty(self):
        self.assertEqual([], _list_field({"source_refs": None}, "source_refs"))
        self.assertEqual([], _list_field({"test_refs": "not-a-list"}, "test_refs"))

    def test_reusable_segment_rejects_valid_json_from_wrong_route(self):
        with tempfile.TemporaryDirectory() as folder:
            run_dir = Path(folder)
            output = run_dir / "model-workspace/attempt-1/llm-sandbox/attempt-1/segments-001-flows/001-flows.json"
            output.parent.mkdir(parents=True)
            output.write_text(json.dumps({
                "schema_version": SEGMENT_SCHEMA,
                "analysis_identity_sha256": "sha256:x",
                "section": "flows",
                "scope_id": "cap-a-01",
                "flows": [{
                    "id": "cap-a-01-flow", "outcome": "x",
                    "requirement_ids": ["RQ-1"], "capability_refs": ["CAP-A"],
                    "task_ids": [2], "source_paths": [], "handoffs": [], "test_ids": ["t"],
                }],
            }), encoding="utf-8")
            self.assertIsNone(load_reusable_segment(
                run_dir, current_attempt=2, index=1, section="flows",
                identity="sha256:x", scope_id="cap-a-01",
                routing_request={"scope_id": "cap-a-01", "requirement_ids": ["RQ-1"],
                                 "task_ids": [1], "capabilities": [{"capability_id": "CAP-A"}]},
            ))

    def test_reusable_segment_requires_matching_route_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            run_dir = Path(folder)
            output = run_dir / "model-workspace/attempt-1/llm-sandbox/attempt-1/segments-001-flows/001-flows.json"
            output.parent.mkdir(parents=True)
            output.write_text(json.dumps({
                "schema_version": SEGMENT_SCHEMA,
                "analysis_identity_sha256": "sha256:x",
                "section": "flows",
                "scope_id": "flow-a",
                "flows": [],
            }), encoding="utf-8")
            self.assertIsNotNone(load_reusable_segment(
                run_dir, current_attempt=2, index=1, section="flows",
                identity="sha256:x", scope_id="flow-a"))
            self.assertIsNone(load_reusable_segment(
                run_dir, current_attempt=2, index=1, section="flows",
                identity="sha256:x", scope_id="flow-b"))

    def test_segment_merge_preserves_existing_rows(self):
        base = {
            "manifest_candidate": {"flows": [{"id": "flow-a", "outcome": "old"}]},
            "coverage_table": [{"requirement_id": "FR-1", "flow_id": "flow-a"}],
            "entrypoints": [{"owner_task": 7}],
            "tests": [{"id": "test-a"}],
        }
        merged = merge_planning_segments(base, [{
            "flows": [{"id": "flow-a", "outcome": "updated"}, {"id": "flow-b"}],
            "coverage_table": [{"requirement_id": "FR-2", "flow_id": "flow-b"}],
            "entrypoints": [{"owner_task": 8}],
            "tests": [{"id": "test-b"}],
        }])
        self.assertEqual("updated", merged["manifest_candidate"]["flows"][0]["outcome"])
        self.assertEqual(["flow-a", "flow-b"], [row["id"] for row in merged["manifest_candidate"]["flows"]])
        self.assertEqual(["FR-1", "FR-2"], [row["requirement_id"] for row in merged["coverage_table"]])
        self.assertEqual([7, 8], [row["owner_task"] for row in merged["entrypoints"]])

    def test_segment_schema_forbids_file_refs_on_flow_coverage(self):
        import jsonschema
        schema = segment_output_schema(section="coverage", identity="sha256:x", scope_id="coverage-01",
            allowed_requirement_ids=["RQ-1"], available_reference_paths=["docs/gdd.md", "Tests.Godot/test.gd"])
        value = {"schema_version": SEGMENT_SCHEMA, "analysis_identity_sha256": "sha256:x",
                 "section": "coverage", "scope_id": "coverage-01", "coverage_table": [{
                     "requirement_id": "RQ-1", "flow_id": "flow-1", "capability_ref": "CAP-A",
                     "task_id": 1, "disposition": "flow", "rationale": "route", "sink_id": None,
                     "verification_ref": "Tests.Godot/test.gd", "authority_ref": "docs/gdd.md",
                     "authority_review": {"status": "accepted", "rationale": "reviewed"}}]}
        self.assertFalse(jsonschema.Draft202012Validator(schema).is_valid(value))

    def test_segment_schema_limits_existing_verified_entrypoint_to_prepared_paths(self):
        import jsonschema
        schema = segment_output_schema(section="entrypoints", identity="sha256:x", scope_id="entrypoints-01",
            available_reference_paths=["Game.Core/Services/SaveService.cs"],
            available_entrypoint_paths=["Game.Core/Services/SaveService.cs"])
        value = {"schema_version": SEGMENT_SCHEMA, "analysis_identity_sha256": "sha256:x",
                 "section": "entrypoints", "scope_id": "entrypoints-01", "entrypoints": [{
                     "status": "existing_verified", "flow_ids": ["flow-1"], "owner_task": 1,
                     "path": "Game.Core/Services/Missing.cs", "symbol": "Missing",
                     "inputs": None, "state": None, "assertions": None, "implementation_acceptance": None}]}
        self.assertFalse(jsonschema.Draft202012Validator(schema).is_valid(value))

    def test_reference_schema_stays_bounded_for_large_prepared_bundles(self):
        import jsonschema
        paths = [f"docs/evidence/{index:04d}/source.md" for index in range(2000)]
        schema = segment_output_schema(section="coverage", identity="sha256:x", scope_id="coverage-01",
            available_reference_paths=paths)
        self.assertLess(len(json.dumps(schema, ensure_ascii=False)), 150000)
        ref = schema["properties"]["coverage_table"]["items"]["properties"]["authority_ref"]
        self.assertTrue(jsonschema.Draft202012Validator(ref).is_valid(paths[10]))
        self.assertFalse(jsonschema.Draft202012Validator(ref).is_valid("docs/evidence/missing.md"))

    def test_segment_merge_preserves_multiple_runtime_boundaries_for_one_owner(self):
        base = {"entrypoints": [{"owner_task": 7, "path": "Game.Core/Services/Start.cs", "symbol": "Start"}]}
        merged = merge_planning_segments(base, [{"entrypoints": [
            {"owner_task": 7, "path": "Game.Core/Services/Resume.cs", "symbol": "Resume"}]}])
        self.assertEqual(["Start", "Resume"], [row["symbol"] for row in merged["entrypoints"]])

    def test_segment_merge_updates_skeleton_placeholders(self):
        merged = merge_planning_segments(
            {"coverage_table": [{"requirement_id": "FR-1", "flow_id": None, "rationale": "pending"}]},
            [{"coverage_table": [{"requirement_id": "FR-1", "flow_id": "flow-a", "rationale": "assigned"}]}],
        )
        self.assertEqual("flow-a", merged["coverage_table"][0]["flow_id"])
        self.assertEqual("assigned", merged["coverage_table"][0]["rationale"])

    def test_manifest_skeleton_has_required_envelope_and_real_blockers(self):
        flows = [{"id": "flow-a", "task_ids": [1, 2], "handoffs": [{
            "producer_task": 1, "consumer_task": 2, "owner_task": 2,
        }]}]
        result = build_manifest_skeleton("Run-ID", flows, {"1": "done", "2": "pending"})
        self.assertEqual("newrouge.mvg-integration.v1", result["schema_version"])
        self.assertEqual("run-id", result["mvg_id"])
        self.assertEqual([2], result["coverage"]["blocking_task_ids"])
        self.assertEqual(["flow-a"], result["coverage"]["required_flow_ids"])

    def test_flow_scopes_use_prepared_capability_membership_and_bound_tasks(self):
        semantics = {"requirements": [
            {"requirement_id": "RQ-1", "statement": "foundation", "capability_ids": ["CAP-OLD"],
             "delivery_relevant": True, "status": "active"},
            {"requirement_id": "RQ-2", "statement": "runtime", "capability_ids": ["CAP-OLD"],
             "delivery_relevant": True, "status": "active"},
            {"requirement_id": "RQ-3", "statement": "inactive", "capability_ids": ["CAP-A"],
             "delivery_relevant": False, "status": "active"},
        ]}
        capabilities = {"capabilities": [
            {"capability_id": "CAP-A", "title": "A", "description": "a",
             "requirement_ids": ["RQ-1"], "boundary_rationale": "shared"},
            {"capability_id": "CAP-B", "title": "B", "description": "b",
             "requirement_ids": ["RQ-2"], "boundary_rationale": "runtime"},
        ]}
        views = [
            {"taskmaster_id": 7, "semantic_refs": ["RQ-1"]},
            {"taskmaster_id": 8, "semantic_refs": ["RQ-2"]},
            {"taskmaster_id": 99, "semantic_refs": ["RQ-1"]},
        ]
        scopes = build_flow_scopes(semantics, capabilities, views, [7, 8], batch_size=16)
        self.assertEqual(["cap-a-01", "cap-b-01"], [scope["scope_id"] for scope in scopes])
        self.assertEqual([["RQ-1"], ["RQ-2"]], [scope["requirement_ids"] for scope in scopes])
        self.assertEqual([[7], [8]], [scope["task_ids"] for scope in scopes])
        self.assertEqual([["CAP-A"], ["CAP-B"]], [
            [row["capability_id"] for row in scope["capabilities"]] for scope in scopes])

    def test_flow_scopes_partition_each_active_requirement_once(self):
        requirements = [{"requirement_id": f"RQ-{index}", "delivery_relevant": True,
                         "status": "active", "capability_ids": ["CAP-A"]}
                        for index in range(5)]
        scopes = build_flow_scopes(
            {"requirements": requirements},
            {"capabilities": [{"capability_id": "CAP-A", "requirement_ids": [f"RQ-{i}" for i in range(5)]}]},
            [], [], batch_size=2)
        ids = [rid for scope in scopes for rid in scope["requirement_ids"]]
        self.assertEqual([f"RQ-{index}" for index in range(5)], ids)
        self.assertEqual(3, len(scopes))

    def test_existing_manifest_scope_is_explicit_and_rejects_widening(self):
        manifest = self.manifest()
        scope = plan_mvg._manifest_planning_scope(manifest)
        self.assertEqual(["flow-a"], scope["flow_ids"])
        self.assertEqual(["RQ-1"], scope["requirement_ids"])
        self.assertEqual([1, 2], scope["task_ids"])
        self.assertEqual(["test-a"], scope["test_ids"])
        legacy_manifest = json.loads(json.dumps(manifest))
        legacy_manifest["flows"][0].pop("requirement_ids")
        legacy_manifest["flows"][0].pop("capability_refs")
        legacy_scope = plan_mvg._manifest_planning_scope(
            legacy_manifest,
            [{"taskmaster_id": 1, "semantic_refs": ["RQ-1"], "capability_refs": ["CAP-A"]}],
        )
        self.assertEqual(["RQ-1"], legacy_scope["requirement_ids"])
        self.assertEqual(["CAP-A"], legacy_scope["capability_refs"])
        with tempfile.TemporaryDirectory() as folder:
            root = self._root(folder)
            state = {
                "run_id": "contract",
                "analysis_identity_sha256": "sha256:x",
                "capabilities_path": "docs/planning/semantic-topology/capabilities.v1.json",
                "planning_scope": scope,
            }
            proposal = {
                "schema_version": "newrouge.mvg-planning-proposal.v1",
                "analysis_identity_sha256": "sha256:x",
                "planning_status": "ready_for_validation",
                "manifest_candidate": json.loads(json.dumps(manifest)),
                "coverage_table": self.accounting()["coverage_table"],
                "entrypoints": self.accounting()["entrypoints"],
                "gaps": [],
            }
            proposal["manifest_candidate"]["flows"][0]["requirement_ids"].append("RQ-OUTSIDE")
            result = validate_proposal(root, state, proposal)
            self.assertIn("manifest_scope_violation:requirement:RQ-OUTSIDE", result["errors"])

    def test_frozen_flow_route_accepts_incumbent_id_without_generated_prefix(self):
        flow = {
            "schema_version": SEGMENT_SCHEMA,
            "analysis_identity_sha256": "sha256:x",
            "section": "flows",
            "scope_id": "reward-claim-and-return",
            "flows": [{
                "id": "reward-claim-and-return",
                "outcome": "return",
                "requirement_ids": ["RQ-1"],
                "capability_refs": ["CAP-A"],
                "task_ids": [1],
                "source_paths": ["Game.Core/Services/Reward.cs"],
                "handoffs": [],
                "test_ids": ["reward-core"],
            }],
        }
        request = {
            "scope_id": "reward-claim-and-return",
            "requirement_ids": ["RQ-1"],
            "task_ids": [1],
            "capabilities": [{"capability_id": "CAP-A"}],
            "allow_exact_flow_id": True,
        }
        self.assertNotIn("segment_flow_id_outside_scope",
                         validate_segment_routing(flow, section="flows", request=request))

    def test_frozen_segment_routes_reject_noncanonical_flow_and_test_ids(self):
        value = {
            "flows": [{
                "id": "reward-claim-and-return-journey",
                "requirement_ids": ["RQ-1"], "capability_refs": ["CAP-A"],
                "task_ids": [1], "source_paths": [], "handoffs": [], "test_ids": ["tests-01-reward-core"],
            }],
        }
        errors = plan_mvg.validate_segment_routing(
            value, section="flows", request={"scope_id": "reward-claim-and-return",
                                               "allow_exact_flow_id": True},
        )
        self.assertIn("segment_flow_id_outside_scope", errors)

        tests = {"tests": [{"id": "tests-01-reward-core", "flow_id": "reward-claim-and-return"}]}
        errors = plan_mvg.validate_segment_routing(
            tests, section="tests", request={"scope_id": "tests-01", "flow_scope_ids": ["reward-claim-and-return"],
                                               "allow_exact_flow_id": True, "allow_exact_test_id": True,
                                               "test_ids": ["reward-core"]},
            flow_context=[{"id": "reward-claim-and-return"}],
        )
        self.assertIn("segment_test_id_outside_scope", errors)

    def test_dotnet_selector_filter_is_reduced_to_declared_class_name(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "Game.Core.Tests/Services/CombatServiceTests.cs"
            source.parent.mkdir(parents=True)
            source.write_text("public sealed class CombatServiceTests {}", encoding="utf-8")
            proposal = {"manifest_candidate": {"tests": [{
                "kind": "dotnet", "path": "Game.Core.Tests/Services/CombatServiceTests.cs",
                "selector": "FullyQualifiedName~CombatServiceTests", "test_refs": [],
            }]}}
            self.assertEqual(1, plan_mvg.normalize_dotnet_selectors(root, proposal))
            self.assertEqual("CombatServiceTests", proposal["manifest_candidate"]["tests"][0]["selector"])

    def test_dotnet_selector_filter_is_reduced_for_append_top_level_tests(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "Game.Core.Tests/Services/SaveServiceTests.cs"
            source.parent.mkdir(parents=True)
            source.write_text("public sealed class SaveServiceTests {}", encoding="utf-8")
            proposal = {"manifest_candidate": {"tests": []}, "tests": [{
                "kind": "dotnet", "path": "Game.Core.Tests/Services/SaveServiceTests.cs",
                "selector": "FullyQualifiedName~SaveServiceTests", "test_refs": [],
            }]}
            self.assertEqual(1, plan_mvg.normalize_dotnet_selectors(root, proposal))
            self.assertEqual("SaveServiceTests", proposal["tests"][0]["selector"])
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
        self.assertIn('llm_workspace = workspace / "llm-sandbox"', source)
        self.assertIn('prompt_path = llm_workspace / f"prompt-{attempt}-{prompt_stem}.txt"', source)
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

    def test_proposal_does_not_fallback_to_live_capability_when_snapshot_is_frozen(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = self._root(folder)
            state = {
                "run_id": "contract",
                "analysis_identity_sha256": "sha256:x",
                "capabilities_path": "docs/planning/semantic-topology/capabilities.v1.json",
                "capabilities_sha256": "sha256:frozen",
            }
            proposal = {
                "schema_version": "newrouge.mvg-planning-proposal.v1",
                "analysis_identity_sha256": "sha256:x",
                "planning_status": "ready_for_validation",
                "manifest_candidate": self.manifest(),
                "coverage_table": [],
                "entrypoints": [],
                "gaps": [],
            }
            result = validate_proposal(root, state, proposal)
            self.assertIn("prepared_capability_snapshot_missing", result["errors"])

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

        source = inspect.getsource(plan_mvg._generate)
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

    def test_selector_validation_explains_exact_class_name_requirement(self) -> None:
        source = Path(__import__("_mvg_manifest").__file__).read_text(encoding="utf-8")
        self.assertIn("selector must be a class name for", source)
        self.assertIn("no *, method filters, or wildcards", source)

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


    def test_semantic_flow_change_requires_reviewed_authority(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = self._root(folder)
            manifest = self.manifest()
            for field, value in (("outcome", "different result"),
                                 ("requirement_ids", ["RQ-2"]),
                                 ("capability_refs", ["CAP-B"])):
                with self.subTest(field=field):
                    delta = {
                        "schema_version": "newrouge.mvg-baseline-delta.v1",
                        "expected_manifest_sha256": plan_mvg.canonical_sha(manifest),
                        "flow_operations": [{
                            "id": "flow-a", "action": "update", "reason": f"change {field}",
                            "field_updates": {field: value},
                        }],
                        "test_operations": [],
                    }
                    with self.assertRaisesRegex(ValueError, "authority_ref"):
                        apply_delta(manifest, delta, root=root)

if __name__ == "__main__":
    unittest.main()
