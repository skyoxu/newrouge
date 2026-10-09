"""Exercise the real segment dispatcher with a schema-aware model boundary."""
from __future__ import annotations

from copy import deepcopy
import json
import re
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


class MvgSegmentScopeTests(unittest.TestCase):
    def _dispatch(self, check, repair_issue=None, *, baseline_only_tests=False, missing_test_evidence=False,
                  change_flows=False, omit_reviews="never", legacy_flow_metadata=False,
                  flow_attempts=None):
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
            baseline_flows = deepcopy(flows)
            if legacy_flow_metadata:
                for key in ("requirement_ids", "capability_refs"):
                    baseline_flows[1].pop(key)
            manifest = {"schema_version": "newrouge.mvg-integration.v1", "mvg_id": "fixture",
                        "flows": baseline_flows, "tests": tests, "coverage": {
                            "mode": "pilot", "scope_id": "fixture", "blocking_task_ids": [],
                            "required_flow_ids": [row["id"] for row in flows],
                            "excluded_claims": ["Runtime evidence remains separate."],
                        }}
            atomic_json(prepared / "existing-manifest.json", manifest)
            atomic_json(prepared / "capabilities.v1.json", {"capabilities": capabilities})
            atomic_json(prepared / "task-views/tasks_back.json", views)
            atomic_json(prepared / "task-views/tasks_gameplay.json", [])
            atomic_json(prepared / "source-manifest.v1.json", {"sources": [{"path": source}]})
            authority = prepared / "sources/docs/gdd/spec.md"
            authority.parent.mkdir(parents=True, exist_ok=True)
            authority.write_text("# Journey\nThe revised journey preserves the delivered behavior.", encoding="utf-8")
            for relative in (source, contract, *(test["path"] for test in tests)):
                if missing_test_evidence and relative in {test["path"] for test in tests}:
                    continue
                target = prepared / "references" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("// Fixture evidence", encoding="utf-8")
            calls = []
            flow_calls = flow_attempts if flow_attempts is not None else {}

            def model(prompt, attempt, *, output_name, output_schema_path, output_schema):
                section = output_schema["properties"]["section"]["const"]
                scope_id = output_schema["properties"]["scope_id"]["const"]
                envelope = {key: output_schema["properties"][key]["const"] for key in (
                    "schema_version", "analysis_identity_sha256", "section", "scope_id")}
                if section == "flows":
                    flow_calls[scope_id] = flow_calls.get(scope_id, 0) + 1
                    flow = next(row for row in flows if row["id"] == scope_id)
                    check(section, flow, prompt, output_schema)
                    envelope["flows"] = [deepcopy(flow)]
                    if change_flows:
                        envelope["flows"][0]["outcome"] += " revised"
                        self.assertIn("change_reviews", output_schema["properties"])
                        self.assertIn('"incumbent_flow"', prompt)
                        self.assertIn("The revised journey preserves", prompt)
                    if "change_reviews" in output_schema["properties"]:
                        envelope["change_reviews"] = ([{
                            "id": flow["id"], "reason": "Clarify the same journey outcome.",
                            "authority_ref": "docs/gdd/spec.md#journey",
                            "authority_review": {"status": "reviewed", "rationale": "The specification preserves the delivered behavior."},
                        }] if change_flows or (legacy_flow_metadata and flow["id"] == "map-route-flow") else [])
                        if omit_reviews == "always" or (omit_reviews == "once" and flow_calls[scope_id] == 1):
                            envelope["change_reviews"] = []
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
                planning_scope=plan_mvg._manifest_planning_scope(manifest, views),
            )
            self.assertEqual(2, calls.count("tests"))
            changed_flow_count = 2 if change_flows else int(legacy_flow_metadata)
            self.assertEqual(2 + (changed_flow_count if omit_reviews == "once" else 0), calls.count("flows"))
            if repair_issue:
                calls.clear()
                output, _ = plan_mvg.invoke_segmented(
                    model, run, {"run_id": "fixture", "analysis_identity_sha256": "sha256:fixture"},
                    2, "", run / "model-workspace/attempt-2",
                    semantics={"requirements": requirements}, task_ids=[1, 2],
                    planning_scope=plan_mvg._manifest_planning_scope(manifest, views),
                    base_proposal=json.loads(output.read_text(encoding="utf-8")),
                    repair_issue=repair_issue,
                )
                expected_repair_sections = [
                    "flows" if str(repair_issue.get("code", "")).startswith("segment_flow_")
                    else "coverage"
                ]
                self.assertEqual(expected_repair_sections, calls,
                                 "Repair must invoke the affected section and reuse unaffected evidence")
            proposal = json.loads(output.read_text(encoding="utf-8"))
            from update_mvg_baseline import apply_delta
            apply_delta(manifest, plan_mvg.build_delta(manifest, proposal), root=prepared / "sources")
            return proposal

    def test_frozen_flow_change_reviews_reach_delta_apply(self):
        proposal = self._dispatch(lambda *args: None, change_flows=True)
        self.assertEqual(2, len(proposal["change_reviews"]))
        self.assertTrue(all(flow["outcome"].endswith(" revised")
                            for flow in proposal["manifest_candidate"]["flows"]))

    def test_missing_change_reviews_retry_only_the_routed_segment(self):
        proposal = self._dispatch(lambda *args: None, change_flows=True, omit_reviews="once")
        self.assertEqual(2, len(proposal["change_reviews"]))

    def test_persistent_missing_change_reviews_never_assemble_proposal(self):
        with self.assertRaisesRegex(ValueError, "segment_flow_change_review_missing"):
            self._dispatch(lambda *args: None, change_flows=True, omit_reviews="always")

    def test_added_legacy_flow_metadata_retries_only_affected_flow_and_preserves_review(self):
        flow_attempts = {}

        def check(section, flow, prompt, schema):
            if section == "flows" and flow["id"] == "map-route-flow" and flow_attempts[flow["id"]] > 1:
                self.assertIn("segment_flow_change_review_missing:map-route-flow", prompt)

        proposal = self._dispatch(check, legacy_flow_metadata=True, omit_reviews="once",
                                  flow_attempts=flow_attempts)
        self.assertEqual({"new-run-flow": 1, "map-route-flow": 2}, flow_attempts)
        self.assertEqual(["map-route-flow"], [row["id"] for row in proposal["change_reviews"]])
        self.assertEqual("docs/gdd/spec.md#journey", proposal["change_reviews"][0]["authority_ref"])
        flow = next(row for row in proposal["manifest_candidate"]["flows"] if row["id"] == "map-route-flow")
        self.assertEqual(["FR-2"], flow["requirement_ids"])
        self.assertEqual(["CAP-2"], flow["capability_refs"])

    def test_added_legacy_flow_metadata_without_review_exhausts_local_budget_before_merge(self):
        flow_attempts = {}
        with patch.object(plan_mvg, "merge_planning_segments", wraps=plan_mvg.merge_planning_segments) as merge, \
                patch.object(plan_mvg, "run_admission_semantic_gate") as semantic_gate:
            with self.assertRaisesRegex(ValueError, "segment_flow_change_review_missing:map-route-flow"):
                self._dispatch(lambda *args: None, legacy_flow_metadata=True, omit_reviews="always",
                               flow_attempts=flow_attempts)
            merge.assert_not_called()
            semantic_gate.assert_not_called()
        self.assertEqual({"new-run-flow": 1, "map-route-flow": 3}, flow_attempts)

    def test_added_legacy_flow_metadata_with_review_merges_without_retry(self):
        flow_attempts = {}
        proposal = self._dispatch(lambda *args: None, legacy_flow_metadata=True, flow_attempts=flow_attempts)
        self.assertEqual({"new-run-flow": 1, "map-route-flow": 1}, flow_attempts)
        self.assertEqual(["map-route-flow"], [row["id"] for row in proposal["change_reviews"]])

    def test_flow_reviews_survive_unrelated_coverage_repair(self):
        proposal = self._dispatch(lambda *args: None, change_flows=True,
                                 repair_issue={"code": "coverage_deferral_unreviewed:FR-1", "path": "proposal"})
        self.assertEqual(2, len(proposal["change_reviews"]))

    def test_repaired_flow_clears_stale_change_review(self):
        base = {"manifest_candidate": {"flows": [{"id": "old-flow", "outcome": "old"}]},
                "change_reviews": [{"id": "old-flow", "authority_ref": "obsolete.md"},
                                   {"id": "other-flow", "authority_ref": "keep.md"}]}
        proposal = plan_mvg.merge_planning_segments(base, [
            {"flows": [{"id": "old-flow", "outcome": "old"}], "change_reviews": []}])
        self.assertEqual([{"id": "other-flow", "authority_ref": "keep.md"}], proposal["change_reviews"])
        self.assertEqual(2, len(base["change_reviews"]))

    def test_frozen_flow_review_schema_is_routed_and_prepared(self):
        def check(section, flow, prompt, schema):
            if section != "flows":
                return
            self.assertIn("change_reviews", schema["required"])
            review = schema["properties"]["change_reviews"]["items"]
            self.assertEqual([flow["id"]], review["properties"]["id"]["enum"])
            self.assertEqual("reviewed", review["properties"]["authority_review"]["properties"]["status"]["const"])
            pattern = review["properties"]["authority_ref"]["pattern"]
            self.assertIsNotNone(re.match(pattern, "docs/gdd/spec.md#journey"))
            self.assertIsNone(re.match(pattern, "docs/gdd/missing.md"))
            value = {key: schema["properties"][key]["const"] for key in (
                "schema_version", "analysis_identity_sha256", "section", "scope_id")}
            value.update(flows=[deepcopy(flow)], change_reviews=[{
                "id": flow["id"], "reason": "Fixture review.", "authority_ref": "docs/gdd/spec.md",
                "authority_review": {"status": "unreviewed", "rationale": "Not reviewed."},
            }])
            with tempfile.TemporaryDirectory() as directory:
                output, schema_file = Path(directory) / "output.json", Path(directory) / "schema.json"
                atomic_json(output, value)
                atomic_json(schema_file, schema)
                with self.assertRaisesRegex(ValueError, "does not satisfy JSON schema"):
                    validate_output_schema(output, schema_file)
        self._dispatch(check)

    def test_change_review_missing_foreign_and_duplicate_are_rejected(self):
        baseline = {"id": "old-flow", "outcome": "old", "requirement_ids": ["FR-1"],
                    "capability_refs": ["CAP-1"], "task_ids": [1], "handoffs": []}
        request = {"scope_id": "old-flow", "allow_exact_flow_id": True,
                   "incumbent_flow": baseline, "requirement_ids": ["FR-1"],
                   "task_ids": [1], "capabilities": [{"capability_id": "CAP-1"}]}
        value = {"flows": [{**baseline, "outcome": "revised"}], "change_reviews": []}
        errors = plan_mvg.validate_segment_routing(value, section="flows", request=request)
        self.assertIn("segment_flow_change_review_missing:old-flow", errors)
        review = {"id": "foreign-flow", "reason": "Updated", "authority_ref": "docs/gdd/spec.md",
                  "authority_review": {"status": "reviewed", "rationale": "Specification evidence."}}
        value["change_reviews"] = [review]
        self.assertIn("segment_change_review_outside_scope", plan_mvg.validate_segment_routing(
            value, section="flows", request=request))
        review["id"] = "old-flow"
        value["change_reviews"] = [review, deepcopy(review)]
        self.assertIn("segment_change_review_duplicate", plan_mvg.validate_segment_routing(
            value, section="flows", request=request))
        value["change_reviews"] = [review]
        review["authority_review"]["status"] = "unreviewed"
        self.assertIn("segment_change_review_invalid", plan_mvg.validate_segment_routing(
            value, section="flows", request=request))

    def test_flow_segment_rejects_duplicate_requirement_routes(self):
        flow = lambda flow_id: {
            "id": flow_id, "outcome": flow_id, "requirement_ids": ["FR-1"],
            "capability_refs": ["CAP-1"], "task_ids": [1],
            "source_paths": ["Game.Godot/Scripts/Main.gd"],
            "handoffs": [{"producer_task": 1, "consumer_task": 1, "owner_task": 1,
                          "contract_ref": "Game.Core/Contracts/Run/RunTransition.cs",
                          "behavior": "Route the request.", "test_ids": ["test-a"]}],
            "test_ids": ["test-a"],
        }
        value = {"flows": [flow("scope-a-first"), flow("scope-a-second")], "change_reviews": []}
        errors = plan_mvg.validate_segment_routing(value, section="flows", request={
            "scope_id": "scope-a", "requirement_ids": ["FR-1"], "task_ids": [1],
            "capabilities": [{"capability_id": "CAP-1"}],
        })
        self.assertIn("segment_flow_requirement_multiple_routes:FR-1", errors)

    def test_flow_metadata_presence_and_value_change_matrix(self):
        absent = object()
        for key, old_id, new_id in (("requirement_ids", "FR-1", "FR-2"),
                                    ("capability_refs", "CAP-1", "CAP-2")):
            cases = (
                ("add_nonempty", absent, [old_id], True),
                ("add_empty", absent, [], True),
                ("remove_nonempty", [old_id], absent, True),
                ("remove_empty", [], absent, True),
                ("modify", [old_id], [new_id], True),
                ("clear", [old_id], [], True),
                ("unchanged_nonempty", [old_id], [old_id], False),
                ("unchanged_empty", [], [], False),
                ("unchanged_absent", absent, absent, False),
            )
            for name, before, after, changed in cases:
                with self.subTest(key=key, case=name):
                    baseline = {"id": "old-flow", "outcome": "old", "requirement_ids": ["FR-1"],
                                "capability_refs": ["CAP-1"], "task_ids": [1], "handoffs": []}
                    candidate = deepcopy(baseline)
                    for row, metadata in ((baseline, before), (candidate, after)):
                        if metadata is absent:
                            row.pop(key)
                        else:
                            row[key] = metadata
                    request = {"scope_id": "old-flow", "allow_exact_flow_id": True,
                               "incumbent_flow": baseline, "requirement_ids": ["FR-1", "FR-2"],
                               "task_ids": [1], "capabilities": [
                                   {"capability_id": "CAP-1"}, {"capability_id": "CAP-2"}]}
                    value = {"flows": [candidate], "change_reviews": []}
                    errors = plan_mvg.validate_segment_routing(value, section="flows", request=request)
                    self.assertEqual(changed, "segment_flow_change_review_missing:old-flow" in errors)
                    if changed:
                        value["change_reviews"] = [{
                            "id": "old-flow", "reason": "Align metadata with prepared specification.",
                            "authority_ref": "docs/gdd/spec.md#journey",
                            "authority_review": {"status": "reviewed", "rationale": "Specification evidence."},
                        }]
                        reviewed_errors = plan_mvg.validate_segment_routing(value, section="flows", request=request)
                        self.assertNotIn("segment_flow_change_review_missing:old-flow", reviewed_errors)
                        self.assertEqual(errors, sorted(set(reviewed_errors + ["segment_flow_change_review_missing:old-flow"])))

    def test_change_review_unprepared_authority_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            errors = plan_mvg.validate_segment_references(
                {"flows": [], "change_reviews": [{"id": "old-flow", "authority_ref": "docs/gdd/missing.md"}]},
                section="flows", prepared=Path(directory), available_source_paths=[], available_contract_paths=[])
            self.assertIn("segment_change_review_authority_unprepared:old-flow", errors)

    def test_coverage_repair_reinvokes_model_with_issue_and_current_rows(self):
        issue = {"code": "coverage_deferral_unreviewed:FR-1", "path": "proposal"}

        def check(section, flow, prompt, schema):
            if section == "coverage" and "Focused candidate hard-issue repair" in prompt:
                self.assertIn(issue["code"], prompt)
                self.assertIn('"current_section"', prompt)
                self.assertNotIn('"entrypoints":', prompt)

        self._dispatch(check, repair_issue=issue)

    def test_flow_change_review_repair_reinvokes_only_named_flow(self):
        issue = {"code": "segment_flow_change_review_missing:map-route-flow",
                 "path": "segment.flows"}
        calls = []

        def check(section, flow, prompt, schema):
            if section == "flows":
                if flow["id"] == "map-route-flow" and "Focused candidate hard-issue repair" in prompt:
                    calls.append(flow["id"])
                    self.assertIn(issue["code"], prompt)

        self._dispatch(check, repair_issue=issue)
        self.assertEqual(["map-route-flow"], calls)

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
