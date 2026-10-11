"""Cumulative planning can add verification without rewriting old regressions."""
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plan_mvg
from _planning_skill_common import atomic_json, validate_output_schema


class AdditiveVerificationTests(unittest.TestCase):
    def fixture(self):
        flow = {"id": "flow-a", "outcome": "Reward", "requirement_ids": ["FR-1"],
                "capability_refs": ["CAP-A"], "task_ids": [1], "source_paths": ["source.cs"],
                "test_ids": ["test-a"], "handoffs": [{"test_ids": ["test-a"], "behavior": "Confirm"}]}
        test = {"id": "test-a", "kind": "gdunit", "state": "implemented", "path": "Tests.Godot/tests/old.gd"}
        baseline = {"flows": [flow], "tests": [test]}
        extra = {"id": "verify-flow-a-failure", "flow_id": "flow-a", "state": "planned",
                 "kind": "gdunit", "path": "Tests.Godot/tests/Integration/test_reward_failure_plan.gd",
                 "evidence_level": "scene-method", "selector": "test_reward_failure_plan", "min_tests": 1,
                 "test_refs": ["Verify failure signal without writeback."], "owner_task": 1,
                 "requirement_ids": ["FR-1"], "handoff_indexes": [0],
                 "inputs": "Invalid reward pool", "assertions": "Fallback and no duplicate writeback",
                 "implementation_acceptance": "Implement a fixture exercising the actual reward provider."}
        return baseline, extra

    def test_schema_admits_only_planned_scoped_extensions(self):
        baseline, extra = self.fixture()
        schema = plan_mvg.segment_output_schema(section="tests", identity="sha256:input", scope_id="tests-01",
            allowed_flow_ids=["flow-a"], allowed_test_ids=["test-a"],
            allowed_test_paths=["Tests.Godot/tests/old.gd"], allow_planned_verification=True)
        envelope = {"schema_version": plan_mvg.SEGMENT_SCHEMA, "analysis_identity_sha256": "sha256:input",
                    "section": "tests", "scope_id": "tests-01", "tests": [extra]}
        with tempfile.TemporaryDirectory() as directory:
            output, schema_path = Path(directory) / "output.json", Path(directory) / "schema.json"
            atomic_json(schema_path, schema)
            atomic_json(output, envelope)
            validate_output_schema(output, schema_path)
            for field, bad in (("state", "implemented"), ("id", "verify-flow-b-failure")):
                changed = deepcopy(envelope)
                changed["tests"][0][field] = bad
                atomic_json(output, changed)
                with self.assertRaises(ValueError):
                    validate_output_schema(output, schema_path)

    def test_planned_verification_retains_metadata_on_next_planning_round(self):
        baseline, extra = self.fixture()
        baseline["tests"].append(extra)
        schema = plan_mvg.segment_output_schema(section="tests", identity="sha256:input", scope_id="tests-01",
            allowed_flow_ids=["flow-a"], allowed_test_ids=["test-a", extra["id"]],
            allowed_test_paths=["Tests.Godot/tests/old.gd", extra["path"]], allow_planned_verification=True)
        envelope = {"schema_version": plan_mvg.SEGMENT_SCHEMA, "analysis_identity_sha256": "sha256:input",
                    "section": "tests", "scope_id": "tests-01", "tests": [extra]}
        request = {"section": "tests", "scope_id": "tests-01", "flow_scope_ids": ["flow-a"],
                   "allow_exact_flow_id": True, "allow_exact_test_id": True, "allow_planned_verification": True,
                   "test_ids": ["test-a", extra["id"]], "test_paths": ["Tests.Godot/tests/old.gd", extra["path"]],
                   "task_ids": [1]}
        self.assertEqual([], plan_mvg.validate_segment_routing(envelope, section="tests", request=request,
                                                               flow_context=baseline["flows"]))
        with tempfile.TemporaryDirectory() as directory:
            output, schema_path = Path(directory) / "output.json", Path(directory) / "schema.json"
            atomic_json(schema_path, schema)
            atomic_json(output, envelope)
            validate_output_schema(output, schema_path)

    def test_extension_binding_keeps_original_handoff_test_set(self):
        baseline, extra = self.fixture()
        proposal = {"manifest_candidate": deepcopy(baseline), "tests": [deepcopy(baseline["tests"][0]), extra]}
        plan_mvg.bind_planned_verification(proposal, baseline)
        self.assertEqual(["test-a", "verify-flow-a-failure"], proposal["manifest_candidate"]["flows"][0]["test_ids"])
        self.assertEqual(["test-a", "verify-flow-a-failure"], proposal["manifest_candidate"]["flows"][0]["handoffs"][0]["test_ids"])
        self.assertEqual(baseline["tests"][0], proposal["tests"][0])

    def test_append_merge_binds_planned_verification_and_preserves_handoff(self):
        import _mvg_capability_append as append
        baseline, extra = self.fixture()
        base = {"manifest_candidate": deepcopy(baseline), "tests": deepcopy(baseline["tests"])}
        proposal = append.merge_append(base, {"tests": [extra]})
        self.assertIn(extra["id"], proposal["manifest_candidate"]["flows"][0]["handoffs"][0]["test_ids"])
        self.assertEqual([], append.preservation_errors(base, proposal))
        proposal["manifest_candidate"]["flows"][0]["handoffs"][0]["behavior"] = "Changed boundary"
        self.assertTrue(append.preservation_errors(base, proposal))

    def test_flow_schema_allows_its_planned_verification_ids_only(self):
        schema = plan_mvg.segment_output_schema(section="flows", identity="sha256:input", scope_id="flows-01",
            allowed_flow_ids=["flow-a"], allowed_test_ids=["test-a"], allow_planned_verification=True)
        import jsonschema
        test_id_schema = schema["properties"]["flows"]["items"]["properties"]["handoffs"]["items"]["properties"]["test_ids"]["items"]
        self.assertTrue(jsonschema.Draft202012Validator(test_id_schema).is_valid("verify-flow-a-failure"))
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.validate("verify-flow-b-failure", test_id_schema)

    def test_planned_verification_rejects_cross_flow_binding(self):
        baseline, extra = self.fixture()
        extra["flow_id"] = "flow-b"
        self.assertIn("segment_verification_flow_mismatch", plan_mvg.planned_verification_errors(extra, baseline["flows"][0]))

    def test_adding_handoff_verification_does_not_weaken_baseline(self):
        from update_mvg_baseline import _weakens_baseline
        baseline, extra = self.fixture()
        proposal = {"manifest_candidate": deepcopy(baseline), "tests": [deepcopy(baseline["tests"][0]), extra]}
        plan_mvg.bind_planned_verification(proposal, baseline)
        self.assertFalse(_weakens_baseline(baseline["flows"][0], proposal["manifest_candidate"]["flows"][0]))
        weakened = deepcopy(proposal["manifest_candidate"]["flows"][0])
        weakened["handoffs"][0]["test_ids"] = [extra["id"]]
        self.assertTrue(_weakens_baseline(baseline["flows"][0], weakened))

    def test_atomic_evidence_repair_can_add_only_its_own_planned_test(self):
        baseline, extra = self.fixture()
        base = {"manifest_candidate": deepcopy(baseline), "tests": deepcopy(baseline["tests"]),
                "coverage_table": [{"requirement_id": "FR-1", "flow_id": "flow-a"}],
                "entrypoints": [], "change_reviews": []}
        changed = deepcopy(base)
        changed["tests"].append(extra)
        plan_mvg.bind_planned_verification(changed, baseline)
        changed["manifest_candidate"]["tests"] = deepcopy(changed["tests"])
        issue = {"code": "semantic_review_blocked:requirement_reviews:FR-1", "repair_action": "repair_sections"}
        self.assertEqual([], plan_mvg.atomic_repair_errors(base, changed, issue, plan_mvg.canonical_sha(base)))

    def test_extension_validator_rejects_unbound_and_foreign_members(self):
        baseline, extra = self.fixture()
        request = {"section": "tests", "scope_id": "tests-01", "flow_scope_ids": ["flow-a"],
                   "allow_exact_flow_id": True, "allow_exact_test_id": True, "allow_planned_verification": True,
                   "test_ids": ["test-a"], "test_paths": ["Tests.Godot/tests/old.gd"], "task_ids": [1]}
        value = {"tests": [extra]}
        self.assertEqual([], plan_mvg.validate_segment_routing(value, section="tests", request=request,
                                                                flow_context=baseline["flows"]))
        for field, bad in (("owner_task", 2), ("requirement_ids", ["FR-2"]), ("handoff_indexes", [99])):
            changed = deepcopy(value)
            changed["tests"][0][field] = bad
            self.assertTrue(plan_mvg.validate_segment_routing(changed, section="tests", request=request,
                                                              flow_context=baseline["flows"]))


if __name__ == "__main__":
    unittest.main()
