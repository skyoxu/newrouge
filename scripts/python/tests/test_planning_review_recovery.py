"""Production regressions for Capability alignment and review publication loss."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plan_capabilities as cap
import plan_mvg as mvg
from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json
from planning_acceptance_fixture import build_fixture
from scripts.python.tests.test_planning_audit_repair import selected_cap, prepared_mvg
import scripts.python.tests.test_planning_main_audit_fixes as audit_fixes


class PlanningReviewRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "fixture"
        build_fixture(self.root)

    def test_same_members_multiple_candidates_require_explicit_alignment(self):
        candidate = {"capabilities": [
            {"capability_id": "TMP-CAP-1", "requirement_ids": ["RQ-A"]},
            {"capability_id": "TMP-CAP-2", "requirement_ids": ["RQ-A"]}]}
        old = {"capabilities": [{"capability_id": "CAP-A", "requirement_ids": ["RQ-A"]}]}
        result = cap.build_alignment(candidate, old)
        self.assertFalse(result["resolved"])
        self.assertTrue(all(not d["resolved"] for d in result["decisions"]))

    def test_same_members_multiple_historical_nodes_require_explicit_alignment(self):
        candidate = {"capabilities": [{"capability_id": "TMP-CAP-1", "requirement_ids": ["RQ-A"]}]}
        old = {"capabilities": [{"capability_id": f"CAP-{n}", "requirement_ids": ["RQ-A"]} for n in (1, 2)]}
        result = cap.build_alignment(candidate, old)
        candidate_row = next(r for r in result["decisions"] if r.get("candidate_id"))
        self.assertFalse(candidate_row["resolved"])
        self.assertIsNone(candidate_row["stable_id"])

    def test_duplicate_override_cannot_change_any_formal_file(self):
        run = selected_cap(self.root)
        alignment = cap.preview_alignment(self.root, run_id="repair")
        for row in alignment["decisions"]:
            row["stable_id"] = "CAP-COLLISION"
        override = run / "alignment-override.json"
        atomic_json(override, alignment)
        before = {p: p.read_bytes() for p in (self.root / "docs/planning/semantic-topology").glob("*.json")}
        with self.assertRaisesRegex(ValueError, "duplicate|unique|collision"):
            cap.apply(self.root, run_id="repair", alignment_override=override, confirm=True)
        self.assertEqual(before, {p: p.read_bytes() for p in (self.root / "docs/planning/semantic-topology").glob("*.json")})
        self.assertFalse((run / "apply-journal.json").exists())

    def test_explicit_ambiguous_alignment_applies_legal_multi_membership(self):
        reqs = load_json(self.root / "logs/ci/task-generation/semantic-requirements.v1.json")["requirements"]
        members = [r["requirement_id"] for r in reqs]
        atomic_json(self.root / cap.FORMAL_CAPABILITIES, {"schema_version": "newrouge.capabilities.v1",
            "capabilities": [{"capability_id": f"CAP-OLD-{i}", "title": f"Old {i}",
                "requirement_ids": members} for i in (1, 2)]})
        run = selected_cap(self.root)
        candidate = load_json(run / "candidates/candidate-1.json")
        for node in candidate["capabilities"]:
            node["requirement_ids"] = members
            node["source_block_ids"] = sorted({b for r in reqs for b in r["source_block_ids"]})
            node["boundary_rationale"] = "Both independent navigation views preserve shared obligations."
        candidate["multi_membership_rationales"] = {rid: "Independent navigation views intentionally share this obligation." for rid in members}
        for row in candidate["source_accounting"]:
            if row["disposition"] == "capability":
                row["capability_ids"] = [c["capability_id"] for c in candidate["capabilities"]]
        labels = [f"candidate-{i}" for i in (1, 2, 3)]
        for label in labels:
            atomic_json(run / f"candidates/{label}.json", candidate)
        meta = load_json(run / "review/review.meta.json")
        meta["candidate_sha256"] = {label: file_sha(run / f"candidates/{label}.json") for label in labels}
        atomic_json(run / "review/review.meta.json", meta)
        self.assertFalse(cap.preview_alignment(self.root, run_id="repair")["resolved"])
        decision = lambda cid, action, stable: {"candidate_id": cid, "action": action,
            "stable_id": stable, "resolved": True, "reason": "Reviewed independent navigation and historical ownership."}
        override = run / "alignment-override.json"
        atomic_json(override, {"decisions": [decision("TMP-CAP-1", "reuse", "CAP-OLD-1"),
            decision("TMP-CAP-2", "split", "CAP-ADDITIONAL"),
            decision(None, "retain", "CAP-OLD-1"), decision(None, "retire", "CAP-OLD-2")]})
        master_before = (self.root / ".taskmaster/tasks/tasks.json").read_bytes()
        result = cap.apply(self.root, run_id="repair", alignment_override=override, confirm=True)
        self.assertEqual("applied", result["status"])
        nodes = load_json(self.root / cap.FORMAL_CAPABILITIES)["capabilities"]
        self.assertEqual({"CAP-OLD-1", "CAP-ADDITIONAL"}, {c["capability_id"] for c in nodes})
        self.assertTrue(all(c["requirement_ids"] == sorted(members) for c in nodes))
        self.assertEqual(master_before, (self.root / ".taskmaster/tasks/tasks.json").read_bytes())
        self.assertEqual("passed", load_json(run / "formal-projection-validation.json")["status"])

    def test_override_rejects_unknown_and_duplicate_decisions(self):
        base = {"decisions": [{"candidate_id": "TMP-1", "stable_id": "CAP-A", "resolved": True}]}
        for decisions in ([{"candidate_id": "UNKNOWN"}], [base["decisions"][0]] * 2):
            with self.subTest(decisions=decisions), self.assertRaisesRegex(ValueError, "unknown|duplicate"):
                cap._apply_alignment_override(base, {"decisions": decisions})

    def test_invalid_complete_topology_blocks_before_transaction(self):
        run = selected_cap(self.root)
        path = self.root / cap.FORMAL_EDGES
        doc = load_json(path)
        doc["edges"].append({"source_type": "requirement", "source_id": "RQ-NOT-REAL",
            "target_type": "task", "target_id": "7", "relation": "implemented_by"})
        atomic_json(path, doc)
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "topology|projection"):
            cap.apply(self.root, run_id="repair", alignment_override=None, confirm=True)
        self.assertEqual(before, path.read_bytes())
        self.assertFalse((run / "apply-journal.json").exists())
        self.assertFalse((self.root / cap.FORMAL_CAPABILITIES).exists())

    def _cap_publication(self, *, boundary, no_winner=False, corrections=False, checkpoint_status=None, drift=None):
        run = audit_fixes.PlanningMainAuditFixesTests.candidates(self)
        report = audit_fixes.review_report(run)
        if no_winner:
            report.update(status="no_valid_winner", selected=None)
        if corrections:
            report["corrections"] = [{"op": "replace", "path": "/capabilities/0/title",
                "value": "Reviewed Relay", "reason": "Clearer navigation",
                "evidence_refs": ["analysis-input/source-blocks.v1.json"]}]
        writer = cap.atomic_json
        def invoke(*args, **kwargs):
            atomic_json(kwargs["output_path"], report)
            return {"model": "fixture-model", "model_tools": []}
        def interrupt(path, payload):
            writer(path, payload)
            if path == run / boundary and (checkpoint_status is None or payload.get("status") == checkpoint_status):
                raise KeyboardInterrupt("loss after committed publication write")
        with patch.object(cap, "inspect_isolated_runner", return_value={"model": "fixture-model"}), \
             patch.object(cap, "run_isolated_model", side_effect=invoke) as model:
            with patch.object(cap, "atomic_json", side_effect=interrupt):
                with self.assertRaises(KeyboardInterrupt):
                    cap.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
            budget = deepcopy(load_json(run / "run.json")["budget"])
            if drift:
                drift(run)
                snapshot = {p: p.read_bytes() for p in (run / "review").glob("*.json")}
                with self.assertRaisesRegex(ValueError, "publication.*invalid|identity.*drift"):
                    cap.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
                self.assertEqual(snapshot, {p: p.read_bytes() for p in (run / "review").glob("*.json")})
                self.assertEqual(1, model.call_count)
                self.assertEqual(budget, load_json(run / "run.json")["budget"])
                return run
            result = cap.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
            self.assertTrue(result["reused"])
            self.assertEqual(1, model.call_count)
            self.assertEqual(budget, load_json(run / "run.json")["budget"])
            self.assertEqual("no_valid_winner" if no_winner else "selected", result["status"])
            if corrections:
                self.assertEqual("Reviewed Relay", load_json(run / "review/corrected-candidate.json")["capabilities"][0]["title"])
            cap._read_valid_review(run, load_json(run / "run.json"))
        return run

    def test_capability_final_report_loss_recovers_without_model(self):
        self._cap_publication(boundary="review/review.json")

    def test_capability_metadata_loss_recovers_corrected_candidate(self):
        self._cap_publication(boundary="review/review.meta.json", corrections=True)

    def test_capability_checkpoint_loss_recovers_before_any_final_report(self):
        self._cap_publication(boundary="review/publication.json", checkpoint_status="pending")

    def test_capability_anonymous_map_loss_recovers_original_selection(self):
        self._cap_publication(boundary="review/anonymous-map.json")

    def test_capability_corrected_candidate_loss_recovers_without_model(self):
        self._cap_publication(boundary="review/corrected-candidate.json", corrections=True)

    def test_capability_completed_publication_recovers_run_state(self):
        self._cap_publication(boundary="review/publication.json", checkpoint_status="complete")

    def test_capability_checkpoint_corruption_blocks_without_writes(self):
        def corrupt(run):
            path = run / "review/publication.json"
            payload = load_json(path)
            payload["entries"][0]["payload"] = {"invalid": "unreviewed"}
            atomic_json(path, payload)
        self._cap_publication(boundary="review/review.json", drift=corrupt)

    def test_capability_external_target_edit_blocks_without_overwrite(self):
        self._cap_publication(boundary="review/review.json",
            drift=lambda run: atomic_json(run / "review/review.json", {"external": "edit"}))

    def test_capability_no_winner_publication_recovers_without_model(self):
        self._cap_publication(boundary="review/review.json", no_winner=True)
        with self.assertRaises(ValueError):
            cap.apply(self.root, run_id="repair", alignment_override=None, confirm=True)

    def _mvg_publication(self, boundary, *, blocked=False, malformed=False, draft=False,
                         checkpoint_status=None, revise_pending=False):
        prepared_mvg(self.root)
        run = self.root / "logs/ci/mvg-planning/repair"
        report = load_json(run / "semantic-review.json")
        (run / "semantic-review.json").unlink()
        (run / "semantic-review-execution.json").unlink()
        if blocked:
            report.update(verdict="blocked", findings=["Required recovery ownership is unclear."])
        if malformed:
            report["requirement_reviews"] = []
        if draft:
            proposal = load_json(run / "proposal.json")
            proposal["planning_status"] = "draft"
            atomic_json(run / "proposal.json", proposal)
            report["proposal_sha256"] = canonical_sha(proposal)
        info = {"schema_version": "newrouge.isolated-model-runner.v1", "model": "fixture-model",
            "fresh_session_per_invocation": True, "filesystem_scope": "workspace_only",
            "can_read_outside_workspace": False, "model_tools": []}
        writer = mvg.atomic_json
        def invoke(*args, **kwargs):
            atomic_json(kwargs["output_path"], report)
            return {"model": "fixture-model", "model_tools": []}
        def interrupt(path, payload):
            writer(path, payload)
            checkpoint = boundary == "checkpoint" and path.name.startswith("semantic-review-publication-")
            if (path == run / boundary or checkpoint) and (checkpoint_status is None or payload.get("status") == checkpoint_status):
                raise KeyboardInterrupt("loss after semantic review publication write")
        with patch.object(mvg, "inspect_isolated_runner", return_value=info), \
             patch.object(mvg, "run_isolated_model", side_effect=invoke) as model:
            with patch.object(mvg, "atomic_json", side_effect=interrupt):
                with self.assertRaises(KeyboardInterrupt):
                    mvg.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
            before = deepcopy(load_json(run / "run.json")["semantic_review_attempts"])
            if revise_pending:
                proposal = load_json(run / "proposal.json")
                proposal["manifest_candidate"]["flows"][0]["outcome"] = "Revised outcome while original publication is incomplete."
                atomic_json(run / "proposal.json", proposal)
                with self.assertRaisesRegex(ValueError, "recover the original proposal"):
                    mvg.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
                self.assertEqual(1, model.call_count)
                self.assertEqual(before, load_json(run / "run.json")["semantic_review_attempts"])
                return
            if blocked or malformed:
                with self.assertRaisesRegex(ValueError, "blocked"):
                    mvg.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
            else:
                result = mvg.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
                self.assertEqual("approved", result["status"])
            self.assertEqual(1, model.call_count)
            self.assertEqual(before, load_json(run / "run.json")["semantic_review_attempts"])
            self.assertTrue((run / "semantic-review-execution.json").is_file())
            self.assertEqual("review-blocked" if blocked or malformed else "reviewed", load_json(run / "run.json")["phase"])
        return run, info, report

    def test_mvg_final_report_loss_recovers_without_model(self):
        self._mvg_publication("semantic-review.json")

    def test_mvg_execution_metadata_loss_recovers_without_model(self):
        self._mvg_publication("semantic-review-execution.json")

    def test_mvg_checkpoint_loss_recovers_without_model(self):
        self._mvg_publication("checkpoint", checkpoint_status="pending")

    def test_mvg_completed_publication_recovers_run_state(self):
        self._mvg_publication("checkpoint", checkpoint_status="complete")

    def test_mvg_pending_publication_cannot_be_bypassed_by_revising_proposal(self):
        self._mvg_publication("semantic-review.json", revise_pending=True)

    def test_mvg_external_receipt_edit_blocks_without_model_or_overwrite(self):
        run, info, _ = self._mvg_publication("semantic-review.json")
        target = run / "semantic-review-execution.json"
        receipt = load_json(target)
        receipt["receipt"]["model_tools"] = ["unreviewed-tool"]
        atomic_json(target, receipt)
        snapshot = target.read_bytes()
        attempts = deepcopy(load_json(run / "run.json")["semantic_review_attempts"])
        with patch.object(mvg, "inspect_isolated_runner", return_value=info), \
             patch.object(mvg, "run_isolated_model") as model:
            with self.assertRaisesRegex(ValueError, "identity drift"):
                mvg.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)
            model.assert_not_called()
        self.assertEqual(snapshot, target.read_bytes())
        self.assertEqual(attempts, load_json(run / "run.json")["semantic_review_attempts"])

    def test_mvg_blocked_verdict_publishes_receipt_without_approval_retry(self):
        self._mvg_publication("semantic-review.json", blocked=True)

    def test_mvg_invalid_semantic_accounting_cannot_trigger_approval_retry(self):
        self._mvg_publication("semantic-review.json", malformed=True)

    def test_mvg_draft_review_recovers_without_regeneration_or_formal_apply(self):
        self._mvg_publication("semantic-review.json", draft=True)
        self.assertFalse(mvg.validate(self.root, run_id="repair")["formal_applicable"])

    def test_mvg_revised_proposal_keeps_prior_verdict_and_attempt_budget(self):
        run, info, report = self._mvg_publication("semantic-review.json", blocked=True)
        original = next(run.glob("semantic-review-publication-*.json"))
        original_bytes = original.read_bytes()
        proposal = load_json(run / "proposal.json")
        proposal["manifest_candidate"]["flows"][0]["outcome"] = "Completion signals delivery; failure returns original request to the retry owner."
        atomic_json(run / "proposal.json", proposal)
        report.update(proposal_sha256=canonical_sha(proposal), verdict="approved", findings=[])
        def invoke(*args, **kwargs):
            atomic_json(kwargs["output_path"], report)
            return {"model": "fixture-model", "model_tools": []}
        with patch.object(mvg, "inspect_isolated_runner", return_value=info), \
             patch.object(mvg, "run_isolated_model", side_effect=invoke) as model:
            self.assertEqual("approved", mvg.review(self.root, run_id="repair", runner=Path("fixture"), timeout_sec=10)["status"])
            self.assertEqual(1, model.call_count)
        self.assertEqual(original_bytes, original.read_bytes())
        self.assertEqual(2, len(list(run.glob("semantic-review-publication-*.json"))))
        self.assertEqual(2, len(load_json(run / "run.json")["semantic_review_attempts"]))


if __name__ == "__main__":
    unittest.main()
