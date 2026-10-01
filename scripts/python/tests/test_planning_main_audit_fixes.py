"""Production-entry counterexamples for the merged-main planning audit."""
from __future__ import annotations

import sys
import tempfile
import unittest
from copy import deepcopy
import shutil
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.python.tests.test_planning_audit_repair import prepare_cap, selected_cap, prepared_mvg, milestone_plan
from planning_acceptance_fixture import build_fixture
from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json
from _mvg_obligations import check_task_obligations
from _mvg_manifest import manifest_sha256
import plan_capabilities as cap
import plan_mvg as mvg


def review_report(run):
    return {"schema_version": cap.REVIEW_SCHEMA, "status": "selected", "selected": "A",
        "source_fidelity_findings": ["All launch and delivery source obligations are preserved."],
        "cohesion_findings": [], "boundary_findings": [], "multi_membership_findings": [],
        "navigation_findings": [], "tradeoffs": ["A preserves the same scope with clearer boundaries than B/C."],
        "evidence_refs": ["analysis-input/source-blocks.v1.json", "candidates/A.json"],
        "corrections": [], "rationale": "Select the full source-faithful proposal."}


class PlanningMainAuditFixesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = (Path(self.temp.name) / "fixture").resolve()
        build_fixture(self.root)

    def candidates(self):
        run = selected_cap(self.root)
        candidate = load_json(run / "candidates/candidate-1.json")
        shutil.rmtree(run / "review")
        state = load_json(run / "run.json")
        state.update(phase="prepared", review_status=None, selected_candidate=None, final_candidate_path=None)
        state.pop("actual_model", None)
        atomic_json(run / "run.json", state)
        def invoke(*args, **kwargs):
            atomic_json(kwargs["output_path"], candidate)
            return {"model": "fixture-model", "model_tools": []}
        with patch.object(cap, "inspect_isolated_runner", return_value={"model": "fixture-model"}), \
             patch.object(cap, "run_isolated_model", side_effect=invoke):
            cap.generate(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
        return run

    def test_unprepared_implemented_test_blocks_formal_apply(self):
        path = self.root / "Game.Core.Tests/Tasks/OutsideTests.cs"
        path.write_text("public class OutsideTests { }\n", encoding="utf-8")
        _, proposal, destination = prepared_mvg(self.root)
        run = self.root / "logs/ci/mvg-planning/repair"
        proposal["manifest_candidate"]["tests"][0].update(state="implemented",
            path=path.relative_to(self.root).as_posix(), selector="OutsideTests")
        atomic_json(run / "proposal.json", proposal)
        result = mvg.validate(self.root, run_id="repair")
        self.assertTrue(any("not_prepared" in e for e in result["errors"]), result)
        with self.assertRaises(ValueError):
            mvg.apply(self.root, run_id="repair", confirm=True)
        self.assertFalse(destination.exists())

    def test_explicit_existing_test_is_prepared_and_drift_blocks(self):
        _, proposal, destination = prepared_mvg(self.root)
        path = self.root / "Game.Core.Tests/Tasks/OutsideTests.cs"
        path.write_text("public class OutsideTests { public void Journey() {} }\n", encoding="utf-8")
        state = mvg.prepare(self.root, run_id="with-proof", capabilities_path=self.root / cap.FORMAL_CAPABILITIES,
            task_ids=["7", "42"], manifest_path=destination, allow_unready=False,
            evidence_refs=[path.relative_to(self.root).as_posix()])
        proposal = deepcopy(proposal)
        proposal["analysis_identity_sha256"] = state["analysis_identity_sha256"]
        proposal["manifest_candidate"]["tests"][0].update(state="implemented",
            path=path.relative_to(self.root).as_posix(), selector="OutsideTests")
        self.assertEqual("passed", mvg.validate_proposal(self.root, state, proposal)["status"])
        run = self.root / "logs/ci/mvg-planning/with-proof"
        atomic_json(run / "proposal.json", proposal)
        review = load_json(self.root / "logs/ci/mvg-planning/repair/semantic-review.json")
        review.update(analysis_identity_sha256=state["analysis_identity_sha256"], proposal_sha256=canonical_sha(proposal))
        atomic_json(run / "semantic-review.json", review)
        execution = load_json(self.root / "logs/ci/mvg-planning/repair/semantic-review-execution.json")
        execution.update(analysis_identity_sha256=state["analysis_identity_sha256"], proposal_sha256=canonical_sha(proposal))
        atomic_json(run / "semantic-review-execution.json", execution)
        self.assertTrue(mvg.validate(self.root, run_id="with-proof")["formal_applicable"])
        path.write_text("public class OutsideTests { /* changed proof */ }\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "drift"):
            mvg.apply(self.root, run_id="with-proof", confirm=True)
        self.assertFalse(destination.exists())

    def test_candidate_interruption_consumes_attempt_and_budget_before_resume(self):
        prepare_cap(self.root)
        run = self.root / "logs/ci/capability-planning/repair"
        observed = []
        def invoke(*args, **kwargs):
            state = load_json(run / "run.json")
            record = state["candidate_attempts"]["candidate-1"]["attempts"][-1]
            self.assertEqual("running", record["status"])
            self.assertGreater(state["budget"]["activity_reserved_sec"], 0)
            observed.append(record["attempt"])
            raise KeyboardInterrupt("operator interrupt")
        with patch.object(cap, "inspect_isolated_runner", return_value={"model": "fixture"}), \
             patch.object(cap, "run_isolated_model", side_effect=invoke):
            for _ in range(2):
                with self.assertRaises(KeyboardInterrupt):
                    cap.generate(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
        state = load_json(run / "run.json")
        self.assertEqual([1, 2], observed)
        self.assertEqual(2, state["budget"]["runner_invocations"])
        self.assertGreater(state["budget"]["activity_sec"], 0)
        self.assertTrue(all(a["status"] == "interrupted" for a in state["candidate_attempts"]["candidate-1"]["attempts"]))

    def test_process_loss_keeps_reservation_and_consumes_attempt(self):
        prepare_cap(self.root)
        run = self.root / "logs/ci/capability-planning/repair"
        saved = cap.atomic_json
        def lose_process(path, payload):
            saved(path, payload)
            attempts = (payload.get("candidate_attempts") or {}).get("candidate-1", {}).get("attempts", [])
            if path == run / "run.json" and attempts and attempts[-1].get("status") == "running":
                raise SystemExit("lost immediately after durable reservation")
        with patch.object(cap, "inspect_isolated_runner", return_value={"model": "fixture"}), \
             patch.object(cap, "atomic_json", side_effect=lose_process), patch.object(cap, "run_isolated_model") as invoke:
            with self.assertRaises(SystemExit):
                cap.generate(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
            invoke.assert_not_called()
        first = load_json(run / "run.json")
        with patch.object(cap, "inspect_isolated_runner", return_value={"model": "fixture"}), \
             patch.object(cap, "run_isolated_model", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                cap.generate(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
        state = load_json(run / "run.json")
        self.assertEqual(2, len(state["candidate_attempts"]["candidate-1"]["attempts"]))
        self.assertGreater(first["budget"]["activity_reserved_sec"], 0)
        self.assertEqual(first["budget"]["activity_reserved_sec"], state["budget"]["activity_reserved_sec"])
        self.assertEqual("process_lost_before_settlement", state["candidate_attempts"]["candidate-1"]["attempts"][0]["error"])

    def test_unknown_request_outcome_keeps_conservative_candidate_cap(self):
        prepare_cap(self.root)
        run = self.root / "logs/ci/capability-planning/repair"
        state = load_json(run / "run.json")
        state["budget"]["request_limit"] = 3
        atomic_json(run / "run.json", state)
        runner = {"model": "fixture", "request_accounting": "exact_per_runner_invocation"}
        with patch.object(cap, "inspect_isolated_runner", return_value=runner), \
             patch.object(cap, "run_isolated_model", side_effect=KeyboardInterrupt) as invoke:
            with self.assertRaises(KeyboardInterrupt):
                cap.generate(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
            with self.assertRaisesRegex(ValueError, "request estimate exceeds budget"):
                cap.generate(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
            self.assertEqual(1, invoke.call_count)
        budget = load_json(run / "run.json")["budget"]
        self.assertEqual(0, budget["model_requests_observed"])
        self.assertEqual(1, budget["model_requests_reserved"])
        self.assertFalse(budget["request_count_complete"])

    def test_review_success_is_reused_without_more_cost(self):
        run = self.candidates()
        def invoke(*args, **kwargs):
            atomic_json(kwargs["output_path"], review_report(run))
            return {"model": "fixture-model", "model_tools": []}
        with patch.object(cap, "inspect_isolated_runner", return_value={"model": "fixture-model"}), \
             patch.object(cap, "run_isolated_model", side_effect=invoke) as invocation:
            first = cap.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
            before = load_json(run / "run.json")["budget"]
            for _ in range(3):
                result = cap.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
                self.assertEqual(first["selected_candidate"], result["selected_candidate"])
            self.assertEqual(1, invocation.call_count)
            self.assertEqual(before, load_json(run / "run.json")["budget"])

    def test_cached_review_rejects_changed_evidence_without_new_invocation(self):
        run = self.candidates()
        def invoke(*args, **kwargs):
            atomic_json(kwargs["output_path"], review_report(run))
            return {"model": "fixture-model", "model_tools": []}
        with patch.object(cap, "inspect_isolated_runner", return_value={"model": "fixture-model"}), \
             patch.object(cap, "run_isolated_model", side_effect=invoke) as model:
            cap.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
            files = [run / "review/review.json", run / "candidates/candidate-2.json",
                run / "analysis-input/source-blocks.v1.json", run / "review/review.meta.json"]
            for path in files:
                with self.subTest(path=path.name):
                    original = path.read_bytes()
                    payload = load_json(path)
                    if path.name == "review.meta.json":
                        payload["receipt"]["model"] = "auto"
                    else:
                        payload["audit_tamper"] = "changed after review"
                    atomic_json(path, payload)
                    with self.assertRaises(ValueError):
                        cap.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
                    with self.assertRaises(ValueError):
                        cap.apply(self.root, run_id="repair", alignment_override=None, confirm=True)
                    path.write_bytes(original)
            self.assertEqual(1, model.call_count)

            meta_path = run / "review/review.meta.json"
            original_meta = meta_path.read_bytes()
            meta_path.unlink()
            with self.assertRaises(ValueError):
                cap.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
            meta_path.write_bytes(original_meta)
            self.assertEqual(1, model.call_count)

    def test_corrected_candidate_is_bound_and_reused(self):
        run = self.candidates()
        def invoke(*args, **kwargs):
            report = review_report(run)
            report["corrections"] = [{"op": "replace", "path": "/capabilities/0/title", "value": "Relay launch",
                "reason": "Clarify the source-defined launch boundary.",
                "evidence_refs": ["analysis-input/source-blocks.v1.json"]}]
            atomic_json(kwargs["output_path"], report)
            return {"model": "fixture-model", "model_tools": []}
        with patch.object(cap, "inspect_isolated_runner", return_value={"model": "fixture-model"}), \
             patch.object(cap, "run_isolated_model", side_effect=invoke) as model:
            cap.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
            self.assertTrue(cap.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)["reused"])
            corrected = run / "review/corrected-candidate.json"
            original = corrected.read_bytes()
            payload = load_json(corrected)
            payload["capabilities"][0]["title"] = "Unreviewed title"
            atomic_json(corrected, payload)
            with self.assertRaisesRegex(ValueError, "corrected.*identity"):
                cap.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
            corrected.write_bytes(original)
            state = load_json(run / "run.json")
            state["final_candidate_path"] = "candidates/candidate-2.json"
            atomic_json(run / "run.json", state)
            with self.assertRaisesRegex(ValueError, "final candidate path"):
                cap.apply(self.root, run_id="repair", alignment_override=None, confirm=True)
            self.assertEqual(1, model.call_count)

    def test_no_valid_winner_is_reused_and_cannot_apply(self):
        run = self.candidates()
        def invoke(*args, **kwargs):
            report = review_report(run)
            report.update(status="no_valid_winner", selected=None)
            atomic_json(kwargs["output_path"], report)
            return {"model": "fixture-model", "model_tools": []}
        with patch.object(cap, "inspect_isolated_runner", return_value={"model": "fixture-model"}), \
             patch.object(cap, "run_isolated_model", side_effect=invoke) as model:
            cap.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
            result = cap.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
            self.assertEqual("no_valid_winner", result["status"])
            self.assertTrue(result["reused"])
            self.assertEqual(1, model.call_count)
        with self.assertRaisesRegex(ValueError, "selected independent review"):
            cap.apply(self.root, run_id="repair", alignment_override=None, confirm=True)

    def test_review_process_loss_reservation_blocks_exhausted_resume(self):
        run = self.candidates()
        state = load_json(run / "run.json")
        state["budget"]["total_budget_sec"] = state["budget"]["activity_sec"] + 10.01
        atomic_json(run / "run.json", state)
        saved = cap.atomic_json
        def lose_process(path, payload):
            saved(path, payload)
            attempts = payload.get("review_attempts") or []
            if path == run / "run.json" and attempts and attempts[-1].get("status") == "running":
                raise SystemExit("lost after durable review reservation")
        with patch.object(cap, "inspect_isolated_runner", return_value={"model": "fixture-model"}), \
             patch.object(cap, "atomic_json", side_effect=lose_process), patch.object(cap, "run_isolated_model") as model:
            with self.assertRaises(SystemExit):
                cap.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
            model.assert_not_called()
        first = load_json(run / "run.json")
        with patch.object(cap, "inspect_isolated_runner", return_value={"model": "fixture-model"}), \
             patch.object(cap, "run_isolated_model") as model:
            with self.assertRaisesRegex(ValueError, "active-time budget"):
                cap.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
            model.assert_not_called()
        resumed = load_json(run / "run.json")
        self.assertEqual(first["budget"]["activity_reserved_sec"], resumed["budget"]["activity_reserved_sec"])
        self.assertEqual(first["budget"]["activity_sec"], resumed["budget"]["activity_sec"])
        self.assertEqual(1, len(resumed["review_attempts"]))
        self.assertEqual("interrupted", resumed["review_attempts"][0]["status"])

    def test_existing_manifest_implementation_is_copied_by_prepare(self):
        _, proposal, destination = prepared_mvg(self.root)
        evidence = self.root / "Game.Core.Tests/Tasks/OutsideTests.cs"
        evidence.write_text("public class OutsideTests {}\n", encoding="utf-8")
        proposal["manifest_candidate"]["tests"][0].update(state="implemented",
            path=evidence.relative_to(self.root).as_posix(), selector="OutsideTests")
        atomic_json(destination, proposal["manifest_candidate"])
        state = mvg.prepare(self.root, run_id="baseline-proof", capabilities_path=self.root / cap.FORMAL_CAPABILITIES,
            task_ids=["7", "42"], manifest_path=destination, allow_unready=False)
        proposal["analysis_identity_sha256"] = state["analysis_identity_sha256"]
        self.assertEqual("passed", mvg.validate_proposal(self.root, state, proposal)["status"])
        copied = self.root / "logs/ci/mvg-planning/baseline-proof/analysis-input/references" / evidence.relative_to(self.root)
        self.assertEqual(evidence.read_bytes(), copied.read_bytes())

    def test_incomplete_or_unresolvable_review_cannot_select(self):
        run = self.candidates()
        values = [review_report(run), review_report(run)]
        values[0].pop("source_fidelity_findings")
        values[1]["evidence_refs"] = ["analysis-input/not-present.md"]
        def invoke(*args, **kwargs):
            atomic_json(kwargs["output_path"], values.pop(0))
            return {"model": "fixture-model", "model_tools": []}
        with patch.object(cap, "inspect_isolated_runner", return_value={"model": "fixture-model"}), \
             patch.object(cap, "run_isolated_model", side_effect=invoke):
            with self.assertRaisesRegex(ValueError, "review_|evidence"):
                cap.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
        self.assertNotEqual("selected", load_json(run / "run.json").get("review_status"))

    def test_review_interruption_is_recorded_and_cannot_reset_budget(self):
        run = self.candidates()
        with patch.object(cap, "inspect_isolated_runner", return_value={"model": "fixture-model"}), \
             patch.object(cap, "run_isolated_model", side_effect=KeyboardInterrupt) as invoke:
            for _ in range(2):
                with self.assertRaises(KeyboardInterrupt):
                    cap.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
            try:
                with self.assertRaisesRegex(ValueError, "budget"):
                    cap.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
            except KeyboardInterrupt:
                self.fail("review restarted an exhausted interrupted attempt")
        self.assertEqual(2, invoke.call_count)
        self.assertEqual(2, len(load_json(run / "run.json")["review_attempts"]))

    def test_manifest_and_milestone_checkout_eol_keep_binding_but_real_edit_blocks(self):
        _, proposal, destination = prepared_mvg(self.root)
        mvg.apply(self.root, run_id="repair", confirm=True)
        mvg.rebind_handoff(self.root, run_id="repair", task_id="7", change_plan_path=None, out_path=None)
        before = manifest_sha256(destination.read_bytes())
        destination.write_bytes(destination.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(before, manifest_sha256(destination.read_bytes()))
        self.assertTrue(check_task_obligations(self.root, "7")[0])
        plan = milestone_plan(self.root, proposal, destination)
        handoff = self.root / "docs/planning/milestones/task-7-handoff.json"
        mvg.rebind_handoff(self.root, run_id="repair", task_id="7", change_plan_path=plan, out_path=handoff)
        for path in (plan, handoff):
            path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        self.assertTrue(check_task_obligations(self.root, "7")[0])
        changed = load_json(destination)
        changed["flows"][0]["outcome"] = "Different obligation"
        atomic_json(destination, changed)
        self.assertFalse(check_task_obligations(self.root, "7")[0])


if __name__ == "__main__":
    unittest.main()
