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
    SEGMENT_SCHEMA, segment_prompt, validate_segment_identity, merge_planning_segments,
    build_manifest_skeleton, build_flow_scopes, load_reusable_segment, segment_output_schema,
    bind_manifest_test_ids, preserve_frozen_manifest_baseline,
    _contract_candidates,
    validate_segment_references, validate_segment_routing,
    validate_review_shape, _list_field,
    normalize_proposal_format,
    backfill_review_error_types,
    mvg_selection_output_schema, validate_mvg_selection,
)
from update_mvg_baseline import apply_delta
from _planning_skill_common import atomic_json


class MvgPlanningContractTests(unittest.TestCase):
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
        self.assertIn("mvg_selection_blocked_winner", validate_mvg_selection(
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
        self.assertEqual([], validate_mvg_selection(
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
                {"label": "D", "verdict": "blocked", "rationale": "Not applicable.", "rank": 4},
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
