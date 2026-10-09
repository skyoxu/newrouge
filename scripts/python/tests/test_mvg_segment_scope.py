"""Exercise the real segment dispatcher with a schema-aware model boundary."""
from __future__ import annotations

from copy import deepcopy
import json
import re
from pathlib import Path
import sys
import tempfile
import unittest

PYTHON = Path(__file__).resolve().parents[1]
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))

import plan_mvg
from _planning_skill_common import atomic_json, validate_output_schema


class MvgSegmentScopeTests(unittest.TestCase):
    def _dispatch(self, check, repair_issue=None, *, baseline_only_tests=False, missing_test_evidence=False):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            prepared = run / "analysis-input"
            contract = "Game.Core/Contracts/RunEvent.cs"
            source = "Game.Godot/Scripts/Main.gd"
            flows, tests, views, requirements, capabilities = [], [], [], [], []
            for index, name in enumerate(("new-run", "map-route"), start=1):
                flow_id = name + "-flow"
                test_id = name + "-test"
                rid = f"FR-{index}"
                path = f"Game.Core.Tests/Tasks/Task{index}Tests.cs"
                flows.append({
                    "id": flow_id, "outcome": name, "requirement_ids": [rid],
                    "capability_refs": [f"CAP-{index}"], "task_ids": [index],
                    "source_paths": [source], "test_ids": [test_id],
                    "handoffs": [{"producer_task": index, "consumer_task": index,
                                  "owner_task": index, "contract_ref": contract,
                                  "contract_refs": None, "behavior": name,
                                  "test_ids": [test_id], "from": None, "to": None}],
                })
                tests.append({"id": test_id, "kind": "dotnet",
                              "state": "implemented" if baseline_only_tests else "planned",
                              "path": path, "selector": f"Task{index}Tests",
                              "evidence_level": "domain-integration", "min_tests": 1})
                views.append({"taskmaster_id": index, "semantic_refs": [rid],
                              "test_refs": [] if baseline_only_tests else [path], "source_refs": [source],
                              "contractRefs": [contract]})
                requirements.append({"requirement_id": rid, "statement": name})
                capabilities.append({"capability_id": f"CAP-{index}", "requirement_ids": [rid]})
            manifest = {"schema_version": "newrouge.mvg-integration.v1", "mvg_id": "fixture",
                        "flows": flows, "tests": tests, "coverage": {
                            "mode": "pilot", "scope_id": "fixture", "blocking_task_ids": [],
                            "required_flow_ids": [row["id"] for row in flows],
                            "excluded_claims": ["Runtime evidence remains separate."],
                        }}
            atomic_json(prepared / "existing-manifest.json", manifest)
            atomic_json(prepared / "capabilities.v1.json", {"capabilities": capabilities})
            atomic_json(prepared / "task-views/tasks_back.json", views)
            atomic_json(prepared / "task-views/tasks_gameplay.json", [])
            atomic_json(prepared / "source-manifest.v1.json", {"sources": [{"path": source}]})
            for relative in (source, contract, *(test["path"] for test in tests)):
                if missing_test_evidence and relative in {test["path"] for test in tests}:
                    continue
                target = prepared / "references" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("// Fixture evidence", encoding="utf-8")
            calls = []

            def model(prompt, attempt, *, output_name, output_schema_path, output_schema):
                section = output_schema["properties"]["section"]["const"]
                scope_id = output_schema["properties"]["scope_id"]["const"]
                envelope = {key: output_schema["properties"][key]["const"] for key in (
                    "schema_version", "analysis_identity_sha256", "section", "scope_id")}
                if section == "flows":
                    flow = next(row for row in flows if row["id"] == scope_id)
                    check(section, flow, prompt, output_schema)
                    envelope["flows"] = [deepcopy(flow)]
                elif section == "tests":
                    # A real CLI must choose from the request-local enum, not
                    # from the full manifest. Inspect that exact passed schema.
                    index = int(scope_id.rsplit("-", 1)[1]) - 1
                    flow = sorted(flows, key=lambda row: row["id"])[index]
                    check(section, flow, prompt, output_schema)
                    test = deepcopy(next(row for row in tests if row["id"] in flow["test_ids"]))
                    test.update(flow_id=flow["id"], test_refs=[])
                    envelope["tests"] = [test]
                else:
                    check(section, None, prompt, output_schema)
                    envelope[{"coverage": "coverage_table", "entrypoints": "entrypoints"}[section]] = []
                index = int(Path(output_name).stem.split("-", 1)[0])
                output = (run / "model-workspace" / f"attempt-{attempt}" / "llm-sandbox"
                          / f"attempt-{attempt}" / f"segments-{index:03d}-{section}"
                          / Path(output_name).name)
                atomic_json(output, envelope)
                atomic_json(output_schema_path, output_schema)
                validate_output_schema(output, output_schema_path)
                calls.append(section)
                return output, {"backend": "fixture"}

            output, _ = plan_mvg.invoke_segmented(
                model, run, {"run_id": "fixture", "analysis_identity_sha256": "sha256:fixture"},
                1, "", run / "model-workspace/attempt-1",
                semantics={"requirements": requirements}, task_ids=[1, 2],
                planning_scope=plan_mvg._manifest_planning_scope(manifest),
            )
            self.assertEqual(2, calls.count("tests"))
            self.assertEqual(2, calls.count("flows"))
            if repair_issue:
                calls.clear()
                output, _ = plan_mvg.invoke_segmented(
                    model, run, {"run_id": "fixture", "analysis_identity_sha256": "sha256:fixture"},
                    2, "", run / "model-workspace/attempt-2",
                    semantics={"requirements": requirements}, task_ids=[1, 2],
                    planning_scope=plan_mvg._manifest_planning_scope(manifest),
                    base_proposal=json.loads(output.read_text(encoding="utf-8")),
                    repair_issue=repair_issue,
                )
                self.assertEqual(["coverage"], calls,
                                 "Repair must invoke the affected section and reuse unaffected evidence")
            return json.loads(output.read_text(encoding="utf-8"))

    def test_coverage_repair_reinvokes_model_with_issue_and_current_rows(self):
        issue = {"code": "coverage_deferral_unreviewed:FR-1", "path": "proposal"}

        def check(section, flow, prompt, schema):
            if section == "coverage" and "Focused candidate hard-issue repair" in prompt:
                self.assertIn(issue["code"], prompt)
                self.assertIn('"current_section"', prompt)
                self.assertNotIn('"entrypoints":', prompt)

        self._dispatch(check, repair_issue=issue)

    def test_cli_test_schema_is_flow_local(self):
        def check(section, flow, prompt, schema):
            if section != "tests":
                return
            for item in schema["properties"]["tests"]["items"]["anyOf"]:
                self.assertEqual([flow["id"]], item["properties"]["flow_id"].get("enum"))
                self.assertEqual(flow["test_ids"], item["properties"]["id"].get("enum"))
        self._dispatch(check)

    def test_frozen_implemented_tests_need_not_be_task_view_refs(self):
        def check(section, flow, prompt, schema):
            if section == "tests":
                inline = prompt.split("Inline bounded evidence context:\n", 1)[1]
                evidence, _ = json.JSONDecoder().raw_decode(inline)
                self.assertTrue(evidence["available_test_paths"])

        proposal = self._dispatch(check, baseline_only_tests=True)
        self.assertTrue(all(test["state"] == "implemented" for test in proposal["tests"]))

    def test_frozen_test_manifest_does_not_authorize_missing_evidence(self):
        with self.assertRaisesRegex(ValueError, "segment_test_implemented_unprepared"):
            self._dispatch(lambda *args: None, baseline_only_tests=True, missing_test_evidence=True)

    def test_frozen_baseline_test_segments_remain_reusable_for_coverage_repair(self):
        self._dispatch(lambda *args: None, baseline_only_tests=True,
                       repair_issue={"code": "coverage_deferral_unreviewed:FR-1", "path": "proposal"})

    def test_cli_flow_schema_test_ids_are_flow_local(self):
        def check(section, flow, prompt, schema):
            if section == "flows":
                item = schema["properties"]["flows"]["items"]
                self.assertEqual(flow["test_ids"], item["properties"]["test_ids"]["items"].get("enum"))
        self._dispatch(check)

    def test_prompt_route_and_context_are_flow_local(self):
        def check(section, flow, prompt, schema):
            if section != "tests":
                return
            scope = json.loads(prompt.split("scope is ", 1)[1].split(".\n", 1)[0])
            self.assertEqual([flow["id"]], scope["flow_ids"])
            context = prompt.split("Use these already prepared flow objects as the only flow context:\n", 1)[1]
            rows, _ = json.JSONDecoder().raw_decode(context)
            self.assertEqual([flow["id"]], [row["id"] for row in rows])
            self.assertIn('"test_ids": ' + json.dumps(flow["test_ids"]), prompt)
        self._dispatch(check)

    def test_schema_and_router_reject_foreign_flow_test_id(self):
        def check(section, flow, prompt, schema):
            if section != "tests":
                return
            foreign_id = "new-run-test" if flow["id"] == "map-route-flow" else "map-route-test"
            scope_id = schema["properties"]["scope_id"]["const"]
            value = {key: schema["properties"][key]["const"] for key in (
                "schema_version", "analysis_identity_sha256", "section", "scope_id")}
            value["tests"] = [{
                "id": foreign_id, "flow_id": flow["id"], "test_refs": [],
                "kind": "dotnet", "state": "planned",
                "path": "Game.Core.Tests/Tasks/Task1Tests.cs", "selector": "Task1Tests",
                "evidence_level": "domain-integration", "min_tests": 1,
            }]
            errors = plan_mvg.validate_segment_routing(
                value, section="tests", request={
                    "scope_id": scope_id, "flow_scope_ids": [flow["id"]],
                    "allow_exact_flow_id": True, "allow_exact_test_id": True,
                    "test_ids": flow["test_ids"],
                }, flow_context=[flow],
            )
            self.assertIn("segment_test_id_outside_scope", errors)
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "foreign.json"
                schema_path = Path(directory) / "schema.json"
                atomic_json(output, value)
                atomic_json(schema_path, schema)
                with self.assertRaisesRegex(ValueError, "does not satisfy JSON schema"):
                    validate_output_schema(output, schema_path)
        self._dispatch(check)

    def test_empty_frozen_test_domain_cannot_emit_tests(self):
        schema = plan_mvg.segment_output_schema(
            section="tests", identity="sha256:x", scope_id="tests-01",
            allowed_flow_ids=["new-run-flow"], allowed_test_ids=[],
        )
        self.assertEqual(0, schema["properties"]["tests"].get("maxItems"))

    def test_new_manifest_test_ids_are_cli_prefix_constrained(self):
        schema = plan_mvg.segment_output_schema(
            section="tests", identity="sha256:x", scope_id="tests-01",
        )
        for item in schema["properties"]["tests"]["items"]["anyOf"]:
            pattern = item["properties"]["id"].get("pattern")
            self.assertIsNotNone(pattern)
            self.assertIsNotNone(re.match(pattern, "tests-01-local"))
            self.assertIsNone(re.match(pattern, "tests-02-foreign"))

    def test_coverage_references_are_checked_before_candidate_merge(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared = Path(directory)
            rows = [
                {"requirement_id": "NFR-T0103", "disposition": "deferred",
                 "authority_ref": "NFR-T0103"},
                {"requirement_id": "NFR-T0103", "disposition": "other_verification",
                 "verification_ref": "missing-report.json"},
            ]
            errors = plan_mvg.validate_segment_references(
                {"coverage_table": rows}, section="coverage", prepared=prepared,
                available_source_paths=[], available_contract_paths=[],
            )
            self.assertIn("segment_coverage_authority_unprepared:NFR-T0103", errors)
            self.assertIn("segment_coverage_verification_unprepared", errors)

    def test_coverage_authority_anchor_resolves_only_prepared_file(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared = Path(directory)
            authority = prepared / "sources/docs/gdd/spec.md"
            authority.parent.mkdir(parents=True)
            authority.write_text("# Reviewed boundary", encoding="utf-8")
            errors = plan_mvg.validate_segment_references(
                {"coverage_table": [{"disposition": "deferred",
                                     "authority_ref": "docs/gdd/spec.md#reviewed-boundary"}]},
                section="coverage", prepared=prepared,
                available_source_paths=[], available_contract_paths=[],
            )
            self.assertEqual([], errors)

    def test_coverage_schema_rejects_requirement_id_as_authority(self):
        def check(section, flow, prompt, schema):
            if section != "coverage":
                return
            value = {key: schema["properties"][key]["const"] for key in (
                "schema_version", "analysis_identity_sha256", "section", "scope_id")}
            value["coverage_table"] = [{
                "requirement_id": "FR-1", "flow_id": None, "capability_ref": "CAP-1",
                "task_id": 1, "disposition": "deferred", "rationale": "Fixture invalid reference.",
                "sink_id": None, "verification_ref": None, "authority_ref": "NFR-T0103",
                "authority_review": {"status": "reviewed", "rationale": "Fixture review."},
            }]
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory) / "invalid.json"
                schema_path = Path(directory) / "schema.json"
                atomic_json(output, value)
                atomic_json(schema_path, schema)
                with self.assertRaisesRegex(ValueError, "does not satisfy JSON schema"):
                    validate_output_schema(output, schema_path)
                value["coverage_table"][0]["authority_ref"] = "Game.Godot/Scripts/Main.gd#fixture"
                atomic_json(output, value)
                validate_output_schema(output, schema_path)
        self._dispatch(check)


if __name__ == "__main__":
    unittest.main()
