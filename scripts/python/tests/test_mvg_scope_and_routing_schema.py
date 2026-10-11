import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import plan_mvg
from _planning_skill_common import validate_output_schema


class MvgScopeAndRoutingSchemaTests(unittest.TestCase):
    def test_routed_test_segments_preserve_frozen_handoff_bindings(self):
        flow = {"id": "flow-a", "test_ids": ["test-a", "test-b"], "handoffs": [
            {"test_ids": ["test-a"], "behavior": "First boundary."},
            {"test_ids": ["test-b"], "behavior": "Second boundary."}]}
        proposal = {"manifest_candidate": {"flows": [copy.deepcopy(flow)]}, "tests": [
            {"id": "test-a", "flow_id": "flow-a"},
            {"id": "test-b", "flow_id": "flow-a"}]}
        plan_mvg.bind_manifest_test_ids(proposal, preserve_flow_ids={"flow-a"})
        self.assertEqual(flow, proposal["manifest_candidate"]["flows"][0])

    def test_explicit_flow_membership_does_not_expand_from_evidence_owners(self):
        manifest = {"flows": [{"id": "resume", "task_ids": [87, 103],
                               "requirement_ids": ["FR-87"], "capability_refs": ["CAP-RUNTIME"]}]}
        views = [{"taskmaster_id": 87, "semantic_refs": ["FR-87"], "capability_refs": ["CAP-RUNTIME"]},
                 {"taskmaster_id": 103, "semantic_refs": ["NFR-103"], "capability_refs": ["CAP-GOVERNANCE"]}]
        scope = plan_mvg._manifest_planning_scope(manifest, views)
        self.assertEqual(["FR-87"], scope["requirement_ids"])
        self.assertEqual(["CAP-RUNTIME"], scope["capability_refs"])
        self.assertEqual([87, 103], scope["task_ids"])

    def test_mixed_manifest_retains_only_missing_flow_membership(self):
        manifest = {"flows": [
            {"id": "explicit", "task_ids": [1], "requirement_ids": ["FR-1"], "capability_refs": ["CAP-A"]},
            {"id": "legacy", "task_ids": [2]},
        ]}
        views = [{"taskmaster_id": 1, "semantic_refs": ["FR-1", "NFR-OWNER"], "capability_refs": ["CAP-A", "CAP-OWNER"]},
                 {"taskmaster_id": 2, "semantic_refs": ["FR-2"], "capability_refs": ["CAP-B"]}]
        scope = plan_mvg._manifest_planning_scope(manifest, views)
        self.assertEqual(["FR-1", "FR-2"], scope["requirement_ids"])
        self.assertEqual(["CAP-A", "CAP-B"], scope["capability_refs"])

    def test_explicit_empty_membership_is_not_legacy(self):
        scope = plan_mvg._manifest_planning_scope(
            {"flows": [{"id": "evidence", "task_ids": [1], "requirement_ids": [], "capability_refs": []}]},
            [{"taskmaster_id": 1, "semantic_refs": ["NFR-1"], "capability_refs": ["CAP-GOVERNANCE"]}])
        self.assertEqual([], scope["requirement_ids"])
        self.assertEqual([], scope["capability_refs"])

    def test_routing_cli_schema_rejects_incompatible_disposition_fields(self):
        schema = plan_mvg.candidate_routing_schema("sha256:input", {"FR-1": {"flow-a"}})
        base = {"schema_version": plan_mvg.SEGMENT_SCHEMA, "analysis_identity_sha256": "sha256:input",
                "section": "routing", "scope_id": "candidate-routing", "routes": [{
                    "requirement_id": "FR-1", "disposition": "flow", "flow_id": "flow-a",
                    "sink_id": None, "verification_ref": None, "authority_ref": None,
                    "rationale": "Verified route."}]}
        with tempfile.TemporaryDirectory() as folder:
            schema_path = Path(folder) / "schema.json"
            output_path = Path(folder) / "output.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            output_path.write_text(json.dumps(base), encoding="utf-8")
            validate_output_schema(output_path, schema_path)
            for field in ("sink_id", "verification_ref", "authority_ref"):
                with self.subTest(field=field):
                    changed = copy.deepcopy(base)
                    changed["routes"][0][field] = "unexpected"
                    output_path.write_text(json.dumps(changed), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        validate_output_schema(output_path, schema_path)
                    errors = plan_mvg.validate_candidate_routing(
                        changed["routes"], {"FR-1": {"flow-a"}}, {"FR-1": {"non_task_sinks": []}}, None)
                    self.assertIn("routing_flow_refs_forbidden:FR-1", errors)
            changed = copy.deepcopy(base)
            changed["routes"][0]["flow_id"] = None
            output_path.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(ValueError):
                validate_output_schema(output_path, schema_path)
            for disposition in ("other_verification", "deferred", "source_gap"):
                with self.subTest(disposition=disposition):
                    changed = copy.deepcopy(base)
                    changed["routes"][0]["disposition"] = disposition
                    output_path.write_text(json.dumps(changed), encoding="utf-8")
                    with self.assertRaises(ValueError):
                        validate_output_schema(output_path, schema_path)
                    errors = plan_mvg.validate_candidate_routing(
                        changed["routes"], {"FR-1": {"flow-a"}}, {"FR-1": {"non_task_sinks": []}}, None)
                    self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
