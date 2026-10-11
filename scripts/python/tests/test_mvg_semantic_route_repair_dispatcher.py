"""Exercise semantic Requirement rerouting through the real segment dispatcher."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PYTHON = Path(__file__).resolve().parents[1]
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))

import plan_mvg
from _planning_skill_common import atomic_json, validate_output_schema


class SemanticRouteRepairDispatcherTests(unittest.TestCase):
    def test_pending_route_never_overwrites_committed_route_until_promoted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            committed = {"schema_version": plan_mvg.SEGMENT_SCHEMA,
                         "analysis_identity_sha256": "sha256:old",
                         "section": "routing", "scope_id": "candidate-routing",
                         "routes": [{"requirement_id": "FR-1", "disposition": "flow",
                                     "flow_id": "flow-a", "rationale": "old"}]}
            pending = deepcopy(committed)
            pending["analysis_identity_sha256"] = "sha256:new"
            atomic_json(root / "candidate-routing.json", committed)
            atomic_json(root / "candidate-routing.pending.json", pending)

            loaded = plan_mvg.load_json(root / "candidate-routing.json", None)
            self.assertEqual("sha256:old", loaded["analysis_identity_sha256"])
            plan_mvg.discard_candidate_routing_pending(root)
            self.assertEqual("sha256:old", plan_mvg.load_json(root / "candidate-routing.json", None)[
                "analysis_identity_sha256"])
            self.assertFalse((root / "candidate-routing.pending.json").exists())

            atomic_json(root / "candidate-routing.pending.json", pending)
            promoted = plan_mvg.promote_candidate_routing(root)
            self.assertTrue(promoted)
            self.assertEqual(pending, plan_mvg.load_json(root / "candidate-routing.json", None))
            self.assertFalse((root / "candidate-routing.pending.json").exists())

    def test_semantic_requirement_review_can_move_only_target_to_evidenced_flow(self):
        self._exercise_semantic_repair("reassign_route")

    def test_missing_verification_repairs_current_journey_without_routing_call(self):
        self._exercise_semantic_repair("repair_sections")

    def _exercise_semantic_repair(self, repair_action):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            prepared = run / "analysis-input"
            reqs = [{"requirement_id": "FR-1", "statement": "Start a run"},
                    {"requirement_id": "FR-2", "statement": "Navigate the map"},
                    {"requirement_id": "FR-3", "statement": "Resume a run"}]
            task_views = [
                {"taskmaster_id": 1, "semantic_refs": ["FR-1"], "capability_refs": ["CAP-SHARED"],
                 "source_refs": ["Game.Godot/Scripts/Main.gd"], "contractRefs": ["Game.Core/Contracts/RunEvent.cs"]},
                {"taskmaster_id": 2, "semantic_refs": ["FR-2"], "capability_refs": ["CAP-SHARED"],
                 "source_refs": ["Game.Godot/Scripts/Main.gd"], "contractRefs": ["Game.Core/Contracts/RunEvent.cs"]},
                {"taskmaster_id": 3, "semantic_refs": ["FR-3"], "capability_refs": ["CAP-SHARED"],
                 "source_refs": ["Game.Godot/Scripts/Main.gd"], "contractRefs": ["Game.Core/Contracts/RunEvent.cs"]},
            ]
            flows = [
                {"id": "flow-a", "outcome": "Start and resume", "requirement_ids": ["FR-1", "FR-3"], "capability_refs": ["CAP-SHARED"],
                 "task_ids": [1, 3], "source_paths": ["Game.Godot/Scripts/Main.gd"], "test_ids": ["test-a"],
                 "handoffs": [{"producer_task": 1, "consumer_task": 3, "owner_task": 1,
                               "contract_ref": "Game.Core/Contracts/RunEvent.cs", "contract_refs": None,
                               "behavior": "Start and resume", "test_ids": ["test-a"], "from": None, "to": None}]},
                {"id": "flow-b", "outcome": "Map", "requirement_ids": ["FR-2"], "capability_refs": ["CAP-SHARED"],
                 "task_ids": [1, 2], "source_paths": ["Game.Godot/Scripts/Main.gd"], "test_ids": ["test-b"],
                 "handoffs": [{"producer_task": 1, "consumer_task": 2, "owner_task": 1,
                               "contract_ref": "Game.Core/Contracts/RunEvent.cs", "contract_refs": None,
                               "behavior": "Map navigation", "test_ids": ["test-b"], "from": None, "to": None}]},
            ]
            manifest = {"schema_version": "newrouge.mvg-integration.v1", "mvg_id": "fixture",
                        "flows": deepcopy(flows), "tests": [], "coverage": {"mode": "pilot", "scope_id": "fixture",
                        "required_flow_ids": ["flow-a", "flow-b"], "blocking_task_ids": [],
                        "excluded_claims": ["Runtime evidence remains separate."]}}
            atomic_json(prepared / "existing-manifest.json", manifest)
            atomic_json(prepared / "capabilities.v1.json", {"capabilities": [
                {"capability_id": "CAP-SHARED", "requirement_ids": ["FR-1", "FR-2", "FR-3"]}]})
            atomic_json(prepared / "task-views/tasks_back.json", task_views)
            atomic_json(prepared / "task-views/tasks_gameplay.json", [])
            atomic_json(prepared / "source-manifest.v1.json", {"sources": [{"path": "Game.Godot/Scripts/Main.gd"}]})
            authority = prepared / "sources/docs/gdd/spec.md"
            authority.parent.mkdir(parents=True, exist_ok=True)
            authority.write_text("# Route authority\nFR-1 belongs to the map journey.", encoding="utf-8")
            for rel in ("Game.Godot/Scripts/Main.gd", "Game.Core/Contracts/RunEvent.cs"):
                dest = prepared / "references" / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text("// evidence", encoding="utf-8")

            identity = "sha256:fixture"
            old_routes = [
                {"requirement_id": "FR-1", "disposition": "flow", "flow_id": "flow-a", "rationale": "Start", "sink_id": None, "verification_ref": None, "authority_ref": None},
                {"requirement_id": "FR-2", "disposition": "flow", "flow_id": "flow-b", "rationale": "Map", "sink_id": None, "verification_ref": None, "authority_ref": None},
                {"requirement_id": "FR-3", "disposition": "flow", "flow_id": "flow-a", "rationale": "Resume", "sink_id": None, "verification_ref": None, "authority_ref": None},
            ]
            atomic_json(run / "candidate-routing.json", {"schema_version": plan_mvg.SEGMENT_SCHEMA,
                "analysis_identity_sha256": identity, "section": "routing", "scope_id": "candidate-routing", "routes": old_routes})
            base = {"manifest_candidate": deepcopy(manifest), "coverage_table": [
                {"requirement_id": "FR-1", "disposition": "flow", "flow_id": "flow-a"},
                {"requirement_id": "FR-2", "disposition": "flow", "flow_id": "flow-b"},
                {"requirement_id": "FR-3", "disposition": "flow", "flow_id": "flow-a"}],
                "tests": [], "entrypoints": [], "change_reviews": []}
            seen = []

            def model(prompt, attempt, *, output_name, output_schema_path, output_schema):
                section = output_schema["properties"]["section"]["const"]
                scope_id = output_schema["properties"]["scope_id"]["const"]
                value = {key: output_schema["properties"][key]["const"] for key in (
                    "schema_version", "analysis_identity_sha256", "section", "scope_id")}
                if "proposal_sha256" in output_schema["properties"]:
                    value["proposal_sha256"] = output_schema["properties"]["proposal_sha256"]["const"]
                seen.append((section, scope_id))
                if section == "routing":
                    self.assertIn("Focused semantic routing repair", prompt)
                    value["routes"] = [dict(old_routes[0], flow_id="flow-b"), deepcopy(old_routes[1]), deepcopy(old_routes[2])]
                elif section == "flows":
                    incumbent = next(row for row in flows if row["id"] == scope_id)
                    revised = deepcopy(incumbent)
                    if repair_action == "repair_sections":
                        revised = deepcopy(incumbent)
                    elif scope_id == "flow-a":
                        revised["requirement_ids"] = ["FR-3"]
                    else:
                        revised["requirement_ids"] = ["FR-1", "FR-2"]
                    value["flows"] = [revised]
                    if "change_reviews" in output_schema["properties"]:
                        value["change_reviews"] = [] if repair_action == "repair_sections" else [{"id": scope_id, "reason": "Correct the requirement route.",
                            "authority_ref": "docs/gdd/spec.md", "authority_review": {
                                "status": "reviewed", "rationale": "The specification assigns FR-1 to this journey."}}]
                elif section == "coverage":
                    value["coverage_table"] = [{"requirement_id": "FR-1", "disposition": "flow",
                        "flow_id": "flow-b" if repair_action == "reassign_route" else "flow-a",
                        "capability_ref": "CAP-SHARED", "task_id": 1, "rationale": "The map journey owns this behavior.",
                        "sink_id": None, "verification_ref": None, "authority_ref": None, "authority_review": None}]
                elif section == "tests":
                    value["tests"] = []
                else:
                    value["entrypoints"] = []
                output = run / "responses" / output_name
                atomic_json(output, value)
                atomic_json(output_schema_path, output_schema)
                validate_output_schema(output, output_schema_path)
                return output, {"backend": "fixture"}

            with patch.object(plan_mvg, "validate_segment_references", return_value=[]):
                output, _ = plan_mvg.invoke_segmented(model, run,
                    {"run_id": "fixture", "analysis_identity_sha256": identity}, 2, "",
                    run / "model-workspace/attempt-2", semantics={"requirements": reqs}, task_ids=[1, 2, 3],
                    base_proposal=base,
                    planning_scope=plan_mvg._manifest_planning_scope(manifest, task_views),
                    repair_issue={"code": "semantic_review_blocked:requirement_reviews:FR-1", "path": "proposal",
                                  "repair_action": repair_action})

            proposal = json.loads(output.read_text(encoding="utf-8"))
            committed_routes = plan_mvg.load_json(run / "candidate-routing.json", {})["routes"]
            if repair_action == "repair_sections":
                self.assertEqual(old_routes, committed_routes)
                self.assertNotIn(("routing", "candidate-routing"), seen)
                self.assertNotIn(("flows", "flow-b"), seen)
                self.assertEqual(base["manifest_candidate"], proposal["manifest_candidate"])
                self.assertEqual("flow-a", proposal["coverage_table"][0]["flow_id"])
                self.assertFalse(plan_mvg.atomic_repair_errors(base, proposal,
                    {"code": "semantic_review_blocked:requirement_reviews:FR-1",
                     "repair_action": repair_action}, plan_mvg.canonical_sha(base)))
                return
            pending_routes = plan_mvg.load_json(run / "candidate-routing.pending.json", {})["routes"]
            self.assertEqual(old_routes, committed_routes)
            self.assertEqual("flow-b", next(row["flow_id"] for row in pending_routes
                                             if row["requirement_id"] == "FR-1"))
            self.assertEqual(("routing", "candidate-routing"), seen[0])
            self.assertCountEqual([("flows", "flow-a"), ("flows", "flow-b")], seen[1:3])
            coverage = {row["requirement_id"]: row["flow_id"] for row in proposal["coverage_table"]}
            self.assertEqual({"FR-1": "flow-b", "FR-2": "flow-b", "FR-3": "flow-a"}, coverage)
            revised = {row["id"]: row for row in proposal["manifest_candidate"]["flows"]}
            self.assertEqual(["FR-3"], revised["flow-a"]["requirement_ids"])
            self.assertEqual(["FR-1", "FR-2"], revised["flow-b"]["requirement_ids"])
            self.assertEqual(["flow-a", "flow-b"], [row["id"] for row in proposal["change_reviews"]])


if __name__ == "__main__":
    unittest.main()
