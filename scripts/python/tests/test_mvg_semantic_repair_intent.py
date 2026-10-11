"""Keep semantic evidence repairs distinct from Requirement ownership repairs."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plan_mvg
from _planning_skill_common import atomic_json


class SemanticRepairIntentTests(unittest.TestCase):
    def test_missing_verification_can_repair_current_flow_without_reassignment(self):
        base = {"manifest_candidate": {"flows": [{"id": "flow-a", "requirement_ids": ["FR-1"],
                    "task_ids": [1], "source_paths": ["source.cs"], "test_ids": ["test-a"],
                    "outcome": "Reward confirmation", "handoffs": []}], "tests": []},
                "coverage_table": [{"requirement_id": "FR-1", "flow_id": "flow-a",
                                    "rationale": "Reward confirmation"}],
                "tests": [], "entrypoints": [], "change_reviews": []}
        changed = deepcopy(base)
        changed["coverage_table"][0]["rationale"] = "Reward confirmation with explicit failure verification."
        issue = {"code": "semantic_review_blocked:requirement_reviews:FR-1",
                 "repair_action": "repair_sections", "detail": "Missing failure verification."}
        self.assertEqual([], plan_mvg.atomic_repair_errors(base, changed, issue, plan_mvg.canonical_sha(base)))

    def test_reassignment_is_required_only_for_explicit_route_repair(self):
        issue = {"code": "semantic_review_blocked:requirement_reviews:FR-1",
                 "repair_action": "repair_sections"}
        self.assertEqual("", plan_mvg.requirement_route_repair_id(issue))
        self.assertEqual("FR-1", plan_mvg.requirement_route_repair_id(dict(issue, repair_action="reassign_route")))
        self.assertEqual("", plan_mvg.requirement_route_repair_id({"code": issue["code"]}))

    def test_review_schema_requires_structured_repair_intent(self):
        schema = plan_mvg.semantic_review_output_schema()
        row = schema["properties"]["requirement_reviews"]["items"]
        self.assertIn("repair_action", row["required"])
        self.assertEqual({"none", "repair_sections", "reassign_route"},
                         set(row["properties"]["repair_action"]["enum"]))

    def test_durable_admission_queue_preserves_repair_intent_on_recheck(self):
        issue = {"code": "semantic_review_blocked:requirement_reviews:FR-1", "path": "semantic-review",
                 "repair_action": "reassign_route", "detail": "Wrong journey owner.", "findings": "Source assigns another owner."}
        state = plan_mvg.advance_admission_state({"issues": [], "issue_attempts": {}}, [issue], repaired=False)
        self.assertEqual(issue, state["current_issue"])
        refreshed = dict(issue, repair_action="repair_sections", detail="Now only failure verification is missing.")
        state = plan_mvg.advance_admission_state(state, [refreshed], repaired=False)
        self.assertEqual(refreshed, state["current_issue"])

    def test_admission_issue_keeps_its_own_rationale_and_repair_intent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = {"run_id": "intent", "analysis_identity_sha256": "sha256:fixture"}
            atomic_json(root / "logs/ci/mvg-planning/intent/analysis-input/semantic-requirements.v1.json",
                        {"requirements": [{"requirement_id": "FR-1"}]})
            review = {"findings": ["Do not claim the fixture proves the failure branch."],
                      "requirement_reviews": [{"requirement_id": "FR-1", "verdict": "blocked",
                          "rationale": "Failure branch needs a planned verification obligation.",
                          "repair_action": "repair_sections"}], "flow_reviews": []}
            with patch.object(plan_mvg, "validate_proposal", return_value={"status": "passed", "errors": []}), \
                 patch("_mvg_planning_review.semantic_review_errors", return_value=[
                     "semantic_review_not_approved", "semantic_review_blocked:requirement_reviews:FR-1"]):
                issues = plan_mvg.candidate_admission_errors(root, state, {}, review)
            self.assertEqual(1, len(issues))
            self.assertEqual("repair_sections", issues[0].get("repair_action"))
            self.assertIn("Failure branch needs", issues[0].get("detail", ""))
            self.assertIn("Do not claim", issues[0].get("findings", ""))


if __name__ == "__main__":
    unittest.main()
