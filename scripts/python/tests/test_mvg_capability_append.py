"""Offline tests for Capability-local generation and admission."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import os
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _mvg_capability_append as append
import _mvg_capability_generation as generation
import plan_mvg
from _planning_skill_common import atomic_json, file_sha, canonical_sha, RUNNER_SCHEMA


class CapabilityAppendTests(unittest.TestCase):
    def test_append_schema_uses_only_scope_prepared_evidence_paths(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            prepared = Path(folder)
            (prepared / "references").mkdir()
            paths = [f"docs/reference/{index:04d}.md" for index in range(1500)]
            for ref in paths:
                path = prepared / "references" / ref
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("evidence", encoding="utf-8")
            atomic_json(prepared / "capabilities.v1.json", {"capabilities": [{"capability_id": "CAP-A"}]})
            state = {"analysis_identity_sha256": "sha256:identity", "planning_scope": None}
            scope = {"capability_id": "CAP-A", "requirement_ids": ["FR-A"],
                     "new_requirement_ids": ["FR-A"], "cumulative_requirement_ids": ["FR-A"]}
            base = {"manifest_candidate": {"flows": []}}
            schema = generation.append_output_schema(state, scope, base, prepared,
                evidence_paths=["Game.Core/Services/SaveService.cs", "Tests.Godot/test_save.gd"])
            encoded = json.dumps(schema, ensure_ascii=False)
            self.assertLess(len(encoded), 30000)
            self.assertNotIn(paths[0], encoded)
            self.assertNotIn('"pattern"', encoded)

    def test_append_schema_falls_back_to_local_path_gate_for_large_evidence_sets(self):
        with tempfile.TemporaryDirectory() as folder:
            prepared = Path(folder)
            (prepared / "references").mkdir()
            atomic_json(prepared / "capabilities.v1.json", {"capabilities": [{"capability_id": "CAP-A"}]})
            state = {"analysis_identity_sha256": "sha256:identity", "planning_scope": None}
            scope = {"capability_id": "CAP-A", "requirement_ids": ["FR-A"],
                     "new_requirement_ids": ["FR-A"], "cumulative_requirement_ids": ["FR-A"]}
            base = {"manifest_candidate": {"flows": []}}
            paths = [f"docs/reference/{index:04d}.md" for index in range(2000)]
            schema = generation.append_output_schema(state, scope, base, prepared, evidence_paths=paths)
            self.assertLess(len(__import__("json").dumps(schema)), 30000)

    def run_engine(self, *, propose=None, machine=None, semantic=None, final=None,
                   limit=64, scopes=None):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        seen = []
        scopes = scopes or [{"capability_id": "CAP-A", "requirement_ids": ["FR-A"]},
                            {"capability_id": "CAP-B", "requirement_ids": ["FR-B"]}]
        seed = {"manifest_candidate": {"flows": [], "tests": []},
                "coverage_table": [], "entrypoints": [], "tests": []}

        def generate(scope, base, prior, issue, context, call):
            seen.append((scope["capability_id"], deepcopy(base), deepcopy(prior), issue, context))
            call("generate")
            if propose:
                return propose(scope, base, prior, issue, context)
            return {"flows": [], "coverage_table": [
                {"requirement_id": rid, "rationale": "Scoped evidence"}
                for rid in scope["requirement_ids"]], "entrypoints": [], "tests": [], "change_reviews": []}

        def check(scope, base, proposal, call, context):
            call("semantic")
            issues = semantic(scope, proposal) if semantic else []
            return {"issues": issues, "proof": {"approved": not issues}, "execution": {"model": "fixture"}}

        result = append.run_capability_append(
            Path(directory.name), scopes=scopes, seed=seed, identity="fixture",
            propose=generate, machine=machine or (lambda *args: []), semantic=check,
            final_machine=final or (lambda proposal: []), invocation_limit=limit)
        return result, seen

    def test_order_and_accepted_base_are_preserved(self):
        result, seen = self.run_engine()
        self.assertEqual(["CAP-A", "CAP-B"], [row[0] for row in seen])
        self.assertEqual("FR-A", seen[1][1]["coverage_table"][0]["requirement_id"])
        self.assertEqual(4, result["total_invocations"])
        self.assertEqual("admitted", result["status"])

    def test_three_repairs_then_clean_restart_same_capability(self):
        calls = 0

        def propose(scope, base, prior, issue, context):
            nonlocal calls
            calls += 1
            return {"flows": [], "coverage_table": [{"requirement_id": "FR-A", "bad": calls < 5}],
                    "tests": [], "entrypoints": [], "change_reviews": []}

        result, seen = self.run_engine(propose=propose,
            scopes=[{"capability_id": "CAP-A", "requirement_ids": ["FR-A"]}],
            machine=lambda scope, base, proposal: [{"code": "bad", "path": "row"}]
                if proposal["coverage_table"][0]["bad"] else [])
        self.assertEqual(5, len(seen))
        self.assertTrue(all(row[0] == "CAP-A" for row in seen))
        self.assertIsNone(seen[4][2])
        self.assertIsNone(seen[4][3])
        self.assertNotEqual(seen[0][4], seen[4][4])
        self.assertEqual(3, result["restarts"][0]["repair_attempts"])

    def test_budget_counts_generation_and_semantic_calls(self):
        result, _ = self.run_engine(limit=3)
        self.assertEqual("retired", result["status"])
        self.assertEqual(3, result["total_invocations"])
        self.assertEqual(["CAP-A"], result["completed"])

    def test_failed_final_machine_never_invokes_another_semantic_review(self):
        result, _ = self.run_engine(final=lambda proposal: [{"code": "global_handoff_gap"}])
        self.assertEqual("blocked", result["status"])
        self.assertEqual(4, result["total_invocations"])
        self.assertIsNone(result.get("proof"))

    def test_semantic_block_has_same_three_repair_limit(self):
        count = 0

        def review(scope, proposal):
            nonlocal count
            count += 1
            return [{"code": "semantic-gap", "path": "FR-A"}] if count < 5 else []

        result, seen = self.run_engine(semantic=review,
            scopes=[{"capability_id": "CAP-A", "requirement_ids": ["FR-A"]}])
        self.assertEqual(10, result["total_invocations"])
        self.assertIsNone(seen[4][2])
        self.assertIsNone(seen[4][3])

    def test_cannot_overwrite_accepted_coverage_or_test(self):
        base = {"manifest_candidate": {"flows": [], "tests": []},
                "coverage_table": [{"requirement_id": "FR-A", "flow_id": "flow-a"}],
                "tests": [{"id": "test-a", "selector": "Original"}], "entrypoints": []}
        revised = deepcopy(base)
        revised["coverage_table"][0]["flow_id"] = "flow-b"
        revised["tests"][0]["selector"] = "Weakened"
        errors = append.preservation_errors(base, revised)
        self.assertTrue(any("coverage_table" in error["code"] for error in errors))
        self.assertTrue(any("tests" in error["code"] for error in errors))

    def test_shared_flow_can_extend_without_losing_existing_handoff(self):
        flow = {"id": "shared", "outcome": "Journey", "requirement_ids": ["FR-A"],
                "capability_refs": ["CAP-A"], "handoffs": [{"behavior": "A to B"}],
                "task_ids": [1], "source_paths": ["a.cs"], "test_ids": ["test-a"]}
        base = {"manifest_candidate": {"flows": [flow]}, "coverage_table": [], "tests": [], "entrypoints": []}
        revised = deepcopy(base)
        revised["manifest_candidate"]["flows"][0]["requirement_ids"].append("FR-B")
        self.assertEqual([], append.preservation_errors(base, revised))
        revised["manifest_candidate"]["flows"][0]["handoffs"] = []
        self.assertTrue(append.preservation_errors(base, revised))

    def test_new_project_blockers_follow_prepared_master_statuses(self):
        base = {"manifest_candidate": {"flows": [], "tests": [], "coverage": {}}, "coverage_table": []}
        delta = {"flows": [{"id": "runtime", "task_ids": [1, 2, 3], "handoffs": [
            {"producer_task": 1, "consumer_task": 2, "owner_task": 3}]}]}
        result = append.merge_append(base, delta, {"task_statuses": {"1": "done", "2": "pending", "3": "pending"}})
        self.assertEqual([2], result["manifest_candidate"]["coverage"]["blocking_task_ids"])

    def test_shared_runtime_entrypoint_can_add_flow_without_weakening_assertions(self):
        base = {"manifest_candidate": {"flows": []}, "entrypoints": [{"owner_task": 1, "path": "runtime.cs",
            "symbol": "Run", "flow_ids": ["a"], "assertions": ["Preserve recovery"]}]}
        revised = deepcopy(base)
        revised["entrypoints"][0]["flow_ids"].append("b")
        revised["entrypoints"][0]["assertions"].append("Observe new consumer")
        self.assertEqual([], append.preservation_errors(base, revised))
        revised["entrypoints"][0]["assertions"].pop(0)
        self.assertTrue(append.preservation_errors(base, revised))

    def test_issue_reordering_does_not_reset_repair_counter(self):
        count = 0

        def machine(scope, base, proposal):
            nonlocal count
            count += 1
            a, b = {"code": "A"}, {"code": "B"}
            if count < 8:
                return [a, b] if count % 2 else [b, a]
            return []

        result, seen = self.run_engine(machine=machine,
            scopes=[{"capability_id": "CAP-A", "requirement_ids": ["FR-A"]}])
        self.assertEqual(5, len(seen))
        self.assertEqual("A", seen[3][3]["code"])
        self.assertIsNone(seen[4][3])

    def test_input_preflight_failure_stops_without_looping_or_spending_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            def invalid(*args):
                raise ValueError("missing immutable source")
            result = append.run_capability_append(Path(directory), scopes=[{"capability_id": "CAP-A"}],
                seed={"manifest_candidate": {"flows": []}}, identity="fixture", propose=invalid,
                machine=invalid, semantic=invalid, final_machine=invalid)
            self.assertEqual("blocked", result["status"])
            self.assertEqual(0, result["total_invocations"])

    def test_shared_requirement_has_one_primary_coverage_assignment(self):
        scopes = generation.capability_scopes({"capabilities": [
            {"capability_id": "CAP-A", "requirement_ids": ["FR-A"]},
            {"capability_id": "CAP-B", "requirement_ids": ["FR-A", "FR-B"]}]},
            {"requirements": [{"requirement_id": "FR-A"}, {"requirement_id": "FR-B"}]}, None)
        self.assertEqual(["FR-B"], scopes[1]["new_requirement_ids"])
        self.assertEqual(["FR-A", "FR-B"], scopes[1]["requirement_ids"])

    def test_oversized_complete_request_is_rejected_without_truncation(self):
        with self.assertRaisesRegex(ValueError, "runner_input_too_large"):
            generation.bounded_request("x" * 850001, {"type": "object"})

    def test_token_preflight_blocks_append_without_spending_invocations(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"SC_CAPABILITY_MAX_INPUT_TOKENS": "100"}):
            def propose(scope, base, prior, issue, context, call):
                generation.bounded_request("evidence " * 500, {"type": "object"})
                call("generate")
                self.fail("Deterministic preflight must not start a model")
            result = append.run_capability_append(Path(directory), scopes=[{"capability_id": "CAP-A"}],
                seed={"manifest_candidate": {"flows": []}}, identity="fixture", propose=propose,
                machine=lambda *args: [], semantic=lambda *args: None, final_machine=lambda *args: [])
            self.assertEqual("blocked", result["status"])
            self.assertEqual(0, result["total_invocations"])
            self.assertIn("runner_context_budget_exceeded", result["errors"][0]["detail"])

    def test_repair_execution_failure_preserves_hard_issue_and_pending_proposal(self):
        seen = []
        def propose(scope, base, prior, issue, context):
            seen.append((deepcopy(prior), deepcopy(issue)))
            if len(seen) == 2:
                raise RuntimeError("Fixture repair transport failed")
            return {"flows": [], "tests": [], "coverage_table": [{"requirement_id": "FR-A", "bad": len(seen) < 3}]}
        result, _ = self.run_engine(propose=propose, scopes=[{"capability_id": "CAP-A", "requirement_ids": ["FR-A"]}],
            machine=lambda scope, base, proposal: [{"code": "broken:FR-A", "path": "coverage_table"}]
                if proposal["coverage_table"][0]["bad"] else [])
        self.assertEqual("admitted", result["status"])
        self.assertEqual(seen[1], seen[2], "A transport error must not replace a pending hard problem")
        self.assertEqual(1, len(result["execution_errors"]))
        self.assertEqual(1, result["issue_events"][-1]["issue_attempts"]["broken:FR-A@coverage_table"])
        self.assertEqual(4, result["total_invocations"])

    def test_repeated_repair_execution_failure_still_restarts_after_three_attempts(self):
        def propose(scope, base, prior, issue, context):
            if issue:
                raise RuntimeError("Fixture repair transport failed")
            return {"flows": [], "tests": [], "coverage_table": [{"requirement_id": "FR-A", "bad": context == 1}]}
        result, seen = self.run_engine(propose=propose,
            scopes=[{"capability_id": "CAP-A", "requirement_ids": ["FR-A"]}],
            machine=lambda scope, base, proposal: [{"code": "broken:FR-A", "path": "coverage_table"}]
                if proposal["coverage_table"][0]["bad"] else [])
        self.assertEqual("admitted", result["status"])
        self.assertEqual(5, len(seen))
        self.assertEqual(3, len(result["execution_errors"]))
        self.assertEqual("broken:FR-A@coverage_table", result["restarts"][0]["issue_id"])
        self.assertEqual(6, result["total_invocations"])

    def test_failed_semantic_review_of_repair_keeps_last_reviewed_proposal(self):
        seen, reviews = [], []
        def propose(scope, base, prior, issue, context):
            seen.append((deepcopy(prior), deepcopy(issue)))
            return {"flows": [], "tests": [], "coverage_table": [{"requirement_id": "FR-A", "revision": len(seen)}]}
        def semantic(scope, proposal):
            reviews.append(proposal["coverage_table"][0]["revision"])
            if len(reviews) == 2:
                raise RuntimeError("Fixture review transport failed")
            return [{"code": "semantic-gap:FR-A", "path": "semantic-review"}] if len(reviews) == 1 else []
        result, _ = self.run_engine(propose=propose, semantic=semantic,
            scopes=[{"capability_id": "CAP-A", "requirement_ids": ["FR-A"]}])
        self.assertEqual("admitted", result["status"])
        self.assertEqual(3, len(seen), "Failed repair review must retry the hard issue")
        self.assertEqual(seen[1], seen[2], "Unreviewed repair must not become the next repair input")
        self.assertEqual([1, 2, 3], reviews)
        self.assertEqual(6, result["total_invocations"])

    def test_route_repair_allows_source_destination_dependencies_only(self):
        old = {"manifest_candidate": {"flows": [
            {"id": "source", "requirement_ids": ["FR-A", "FR-B"], "test_ids": ["test-source"]},
            {"id": "destination", "requirement_ids": ["FR-C"], "test_ids": ["test-destination"]}]},
            "coverage_table": [{"requirement_id": "FR-A", "flow_id": "source"},
                               {"requirement_id": "FR-B", "flow_id": "source"},
                               {"requirement_id": "FR-C", "flow_id": "destination"}],
            "tests": [{"id": "test-source"}, {"id": "test-destination"}]}
        new = deepcopy(old)
        new["coverage_table"][0]["flow_id"] = "destination"
        new["manifest_candidate"]["flows"][0]["requirement_ids"].remove("FR-A")
        new["manifest_candidate"]["flows"][1]["requirement_ids"].append("FR-A")
        new["tests"][1]["assertions"] = "Verify moved requirement"
        issue = {"code": "semantic_review_blocked:requirement_reviews:FR-A", "repair_action": "reassign_route"}
        self.assertEqual([], generation.repair_scope_errors(old, new, issue))
        new["coverage_table"][1]["flow_id"] = "destination"
        self.assertIn("repair_unrelated_coverage_changed:FR-B", generation.repair_scope_errors(old, new, issue))

    def test_structured_cumulative_issue_targets_exact_flow_and_test(self):
        old = {"manifest_candidate": {"flows": [{"id": "flow-a", "test_ids": ["test-a"]},
            {"id": "flow-b", "test_ids": ["test-b"]}]}, "coverage_table": [],
            "tests": [{"id": "test-a"}, {"id": "test-b"}]}
        revised = deepcopy(old)
        revised["tests"][0]["assertions"] = "Fixed"
        issue = {"code": "append_cumulative_delta_invalid", "path": "manifest",
                 "detail": {"errors": [{"code": "test_invalid", "flow_id": "flow-a", "test_id": "test-a"}]}}
        self.assertEqual([], generation.repair_scope_errors(old, revised, issue))
        revised["tests"][1]["assertions"] = "Unrelated"
        self.assertIn("repair_unrelated_test_changed:test-b", generation.repair_scope_errors(old, revised, issue))
        self.assertIn("repair_target_unresolved", generation.repair_scope_errors(old, revised,
            {"code": "append_cumulative_delta_invalid", "path": "manifest", "detail": "Unspecified failure"}))

    def test_semantic_explanation_cannot_authorize_unrelated_requirement_changes(self):
        old = {"manifest_candidate": {"flows": []}, "coverage_table": [
            {"requirement_id": "FR-A", "rationale": "broken"}, {"requirement_id": "FR-B", "rationale": "valid"}], "tests": []}
        revised = deepcopy(old)
        revised["coverage_table"][0]["rationale"] = "fixed"
        revised["coverage_table"][1]["rationale"] = "collateral"
        issue = {"code": "semantic_review_blocked:requirement_reviews:FR-A", "path": "semantic-review",
                 "detail": "Compare FR-B as context", "findings": ["FR-B is already valid"]}
        self.assertIn("repair_unrelated_coverage_changed:FR-B", generation.repair_scope_errors(old, revised, issue))

    def test_route_repair_can_create_new_target_flow_without_authorizing_other_mapping(self):
        old = {"manifest_candidate": {"flows": [{"id": "source", "requirement_ids": ["FR-A"], "test_ids": ["test-source"]}]},
            "coverage_table": [{"requirement_id": "FR-A", "flow_id": "source"}], "tests": [{"id": "test-source"}]}
        revised = deepcopy(old)
        revised["coverage_table"][0]["flow_id"] = "new-destination"
        revised["manifest_candidate"]["flows"][0]["requirement_ids"] = []
        revised["manifest_candidate"]["flows"].append({"id": "new-destination", "requirement_ids": ["FR-A"], "test_ids": ["test-new"]})
        revised["tests"].append({"id": "test-new", "flow_id": "new-destination"})
        self.assertEqual([], generation.repair_scope_errors(old, revised,
            {"code": "semantic_review_blocked:requirement_reviews:FR-A", "repair_action": "reassign_route"}))

    def test_repair_protects_another_valid_mapping_in_same_capability(self):
        old = {"manifest_candidate": {"flows": []}, "coverage_table": [
            {"requirement_id": "FR-A", "rationale": "broken"},
            {"requirement_id": "FR-B", "rationale": "valid"}], "tests": []}
        new = deepcopy(old)
        new["coverage_table"][0]["rationale"] = "fixed"
        issue = {"code": "coverage_disposition_invalid:FR-A"}
        self.assertEqual([], generation.repair_scope_errors(old, new, issue))
        new["coverage_table"][1]["rationale"] = "collateral change"
        self.assertIn("repair_unrelated_coverage_changed:FR-B", generation.repair_scope_errors(old, new, issue))

    def test_repair_scope_does_not_match_identifier_prefixes(self):
        old = {"manifest_candidate": {"flows": []}, "coverage_table": [
            {"requirement_id": "FR-1", "rationale": "valid"},
            {"requirement_id": "FR-10", "rationale": "broken"}], "tests": []}
        revised = deepcopy(old)
        revised["coverage_table"][0]["rationale"] = "collateral"
        revised["coverage_table"][1]["rationale"] = "fixed"
        self.assertIn("repair_unrelated_coverage_changed:FR-1", generation.repair_scope_errors(
            old, revised, {"code": "coverage_disposition_invalid:FR-10"}))

    def test_semantic_transport_retry_preserves_generated_increment(self):
        with tempfile.TemporaryDirectory() as directory:
            generated, reviews = [], []
            def propose(scope, base, prior, issue, context, call):
                generated.append(context)
                call("generate")
                return {"flows": [], "coverage_table": [{"requirement_id": "FR-A"}], "tests": [], "entrypoints": []}
            def semantic(scope, base, proposal, call, context):
                call("semantic")
                reviews.append(context)
                if len(reviews) < 3:
                    raise RuntimeError("invalid review JSON")
                return {"issues": [], "proof": {"approved": True}, "execution": {}}
            result = append.run_capability_append(Path(directory), scopes=[{"capability_id": "CAP-A"}],
                seed={"manifest_candidate": {"flows": []}}, identity="fixture", propose=propose,
                machine=lambda *args: [], semantic=semantic, final_machine=lambda proposal: [])
            self.assertEqual("admitted", result["status"])
            self.assertEqual([1], generated)
            self.assertEqual([1, 1, 1], reviews)
            self.assertEqual(4, result["total_invocations"])

    def test_interruption_preserves_predecessor_and_invocation_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            scopes = [{"capability_id": "CAP-A"}, {"capability_id": "CAP-B"}]
            seen = []
            def propose(scope, base, prior, issue, context, call):
                seen.append(scope["capability_id"])
                call("generate")
                if scope["capability_id"] == "CAP-B" and len(seen) == 2:
                    raise KeyboardInterrupt("Fixture process interruption")
                return {"flows": [], "coverage_table": [{"requirement_id": scope["capability_id"]}], "tests": []}
            def semantic(scope, base, proposal, call, context):
                call("semantic")
                return {"issues": [], "proof": {"approved": True}, "execution": {}}
            args = dict(scopes=scopes, seed={"manifest_candidate": {"flows": []}}, identity="fixture",
                        propose=propose, machine=lambda *args: [], semantic=semantic, final_machine=lambda proposal: [])
            with self.assertRaises(KeyboardInterrupt):
                append.run_capability_append(Path(directory), **args)
            result = append.run_capability_append(Path(directory), **args)
            self.assertEqual(["CAP-A", "CAP-B", "CAP-B"], seen)
            self.assertEqual(5, result["total_invocations"])
            self.assertEqual("admitted", result["status"])

    def test_missing_capability_membership_fails_before_model(self):
        with self.assertRaisesRegex(ValueError, "membership_incomplete"):
            generation.capability_scopes({"capabilities": [{"capability_id": "CAP-A", "requirement_ids": []}]},
                                         {"requirements": [{"requirement_id": "FR-A"}]}, None)

    def test_real_cumulative_generation_admission_and_proof_verification(self):
        self.exercise_public_generation()

    def test_bound_source_drift_after_first_dispatch_blocks_next_dispatch(self):
        self.exercise_public_generation(drift_after_first_dispatch=True)

    def test_bound_source_drift_after_final_dispatch_blocks_admission(self):
        self.exercise_public_generation(drift_after_final_dispatch=True)

    def test_public_generate_rejects_drifted_candidate_without_recopying(self):
        self.exercise_public_generation(public_candidate_drift=True)

    def test_missing_requirement_is_repaired_from_authoritative_scope(self):
        self.exercise_public_generation(fault="duplicate_coverage")

    def test_missing_entrypoints_receive_three_repairs_before_clean_restart(self):
        self.exercise_public_generation(fault="missing_entrypoints", failed_generations=4)

    def test_missing_requirement_receives_three_repairs_before_clean_restart(self):
        self.exercise_public_generation(fault="duplicate_coverage", failed_generations=4)

    def test_added_predecessor_entrypoint_is_bound_into_public_admission_proof(self):
        self.exercise_public_generation(fault="predecessor_entrypoint", failed_generations=0)

    def test_missing_entrypoints_on_legacy_flow_use_coverage_route_for_address(self):
        scope = {"cumulative_requirement_ids": ["FR-A"], "new_requirement_ids": ["FR-A"]}
        proposal = {"manifest_candidate": {"flows": [{"id": "flow-a", "handoffs": [{}]},
            {"id": "future", "requirement_ids": ["FR-B"], "handoffs": [{}]}]},
            "coverage_table": [{"requirement_id": "FR-A", "flow_id": "flow-a"}]}
        issues = generation.machine_validation_issues(
            {"errors": ["entrypoints_missing_or_empty"], "formal_blockers": []}, scope, proposal)
        self.assertEqual(["flow-a"], issues[0]["detail"]["flow_ids"])

    def test_membership_repair_targets_flow_claimed_by_coverage_row(self):
        old = {"manifest_candidate": {"flows": [{"id": "flow-a", "requirement_ids": []}]},
               "coverage_table": [{"requirement_id": "FR-A", "flow_id": "flow-a"}]}
        revised = deepcopy(old)
        revised["manifest_candidate"]["flows"][0]["requirement_ids"] = ["FR-A"]
        self.assertEqual([], generation.repair_scope_errors(old, revised,
            {"code": "coverage_flow_membership_invalid:FR-A"}))

    def test_new_entrypoint_on_unchanged_predecessor_enters_semantic_review(self):
        scope = {"requirement_ids": ["FR-A"], "cumulative_requirement_ids": ["FR-A", "FR-B"]}
        base = {"manifest_candidate": {"flows": [
            {"id": "flow-b", "requirement_ids": ["FR-B"], "test_ids": ["test-b"]}]},
            "coverage_table": [{"requirement_id": "FR-B"}],
            "entrypoints": [], "tests": [{"id": "test-b"}]}
        revised = deepcopy(base)
        revised["manifest_candidate"]["flows"].append(
            {"id": "flow-a", "requirement_ids": ["FR-A"], "test_ids": []})
        revised["coverage_table"].append({"requirement_id": "FR-A"})
        revised["entrypoints"].append({"path": "runtime.cs", "symbol": "Run", "owner_task": 2,
                                       "flow_ids": ["flow-b"]})
        projection, requirements = generation.review_projection(scope, base, revised)
        self.assertEqual({"flow-a", "flow-b"}, {row["id"] for row in projection["manifest_candidate"]["flows"]})
        self.assertEqual({"FR-A", "FR-B"}, requirements)
        self.assertEqual(revised["entrypoints"], projection["entrypoints"])
        self.assertEqual([{"id": "test-b"}], projection["tests"])

    def test_shared_entrypoint_review_includes_every_linked_flow(self):
        scope = {"requirement_ids": ["FR-A"], "cumulative_requirement_ids": ["FR-A", "FR-B", "FR-C"]}
        base = {"manifest_candidate": {"flows": [
            {"id": "flow-" + letter.lower(), "requirement_ids": ["FR-" + letter], "test_ids": []}
            for letter in ("A", "B", "C")]}, "coverage_table": [], "tests": [],
            "entrypoints": [{"owner_task": 1, "path": "runtime.cs", "symbol": "Run", "flow_ids": ["flow-a", "flow-b"]},
                            {"owner_task": 2, "path": "runtime.cs", "symbol": "Resume", "flow_ids": ["flow-b", "flow-c"]}]}
        projection, requirements = generation.review_projection(scope, base, deepcopy(base))
        self.assertEqual({"flow-a", "flow-b", "flow-c"}, {row["id"] for row in projection["manifest_candidate"]["flows"]})
        self.assertEqual({"FR-A", "FR-B", "FR-C"}, requirements)

    def test_entrypoint_review_includes_owner_acceptance_and_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            import planning_acceptance_fixture as fixture
            import chapter5_semantic_reconciliation as chapter5
            root = Path(directory) / "fixture"
            fixture.build_fixture(root)
            semantics = plan_mvg.load_json(root / plan_mvg.SEMANTICS)
            req = semantics["requirements"][0]
            rid = req["requirement_id"]
            capabilities = root / "docs/planning/semantic-topology/capabilities.v1.json"
            atomic_json(capabilities, {"schema_version": "newrouge.capabilities.v1",
                "source_revision": semantics["source_revision"], "capabilities": [
                    {"capability_id": "CAP-" + str(index), "requirement_ids": [row["requirement_id"]],
                     "source_block_ids": row["source_block_ids"]}
                    for index, row in enumerate(semantics["requirements"], 1)]})
            views = plan_mvg.load_json(root / plan_mvg.TASK_VIEWS[1])
            owner = next(row for row in views if row["taskmaster_id"] == 42)
            owner["source_refs"] = ["owner.md"]
            atomic_json(root / plan_mvg.TASK_VIEWS[1], views)
            (root / "owner.md").write_text("Full boundary evidence", encoding="utf-8")
            fixture._write_readiness(root, plan_mvg.load_json(root / chapter5.DEFAULT_EXTRACTION_SNAPSHOT),
                semantics, {block: row["requirement_id"] for row in semantics["requirements"]
                            for block in row["source_block_ids"]},
                {str(row["taskmaster_id"]): row["semantic_refs"] for row in views})
            plan_mvg.prepare(root, run_id="owner-context", capabilities_path=capabilities,
                manifest_path=root / "docs/testing/mvg/owner-context.json", task_ids=["7", "42"],
                allow_unready=False, evidence_refs=["owner.md"])
            prepared = root / plan_mvg.DEFAULT_RUN_ROOT / "owner-context/analysis-input"
            scope = {"capability": {}, "requirement_ids": [rid], "cumulative_requirement_ids": [rid]}
            base = {"manifest_candidate": {"flows": [{"id": "flow-a", "requirement_ids": [rid],
                    "task_ids": [7], "test_ids": []}]}, "coverage_table": [], "tests": [], "entrypoints": []}
            revised = deepcopy(base)
            revised["entrypoints"] = [{"owner_task": 42, "flow_ids": ["flow-a"], "path": "runtime.cs", "symbol": "Run"}]
            context = generation.complete_scope_context(prepared, scope, base, revised)
            self.assertEqual({7, 42}, {row["id"] for row in context["task_master"]})
            owner_context = next(row for row in context["task_views"] if row["taskmaster_id"] == 42)
            self.assertEqual(owner["acceptance"], owner_context["acceptance"])
            self.assertEqual("tasks_gameplay.json", owner_context["_source_view"])
            self.assertTrue(any(row.get("text") == "Full boundary evidence" for row in context["evidence"]))

    def test_repair_rejects_new_unrelated_entrypoint(self):
        old = {"manifest_candidate": {"flows": [
            {"id": "flow-a", "requirement_ids": ["FR-A"]},
            {"id": "flow-b", "requirement_ids": ["FR-B"]}]},
            "coverage_table": [{"requirement_id": "FR-A", "rationale": "broken"},
                               {"requirement_id": "FR-B", "rationale": "valid"}], "entrypoints": []}
        revised = deepcopy(old)
        revised["coverage_table"][0]["rationale"] = "fixed"
        entrypoint = {"owner_task": 2, "path": "runtime.cs", "symbol": "Run", "flow_ids": ["flow-b"]}
        revised["entrypoints"].append(entrypoint)
        issue = {"code": "coverage_rationale_missing:FR-A"}
        self.assertIn("repair_unrelated_entrypoint_added:runtime.cs", generation.repair_scope_errors(old, revised, issue))
        entrypoint["flow_ids"] = ["flow-a"]
        self.assertEqual([], generation.repair_scope_errors(old, revised, issue))
        entrypoint["flow_ids"] = ["flow-a", "flow-b"]
        self.assertIn("repair_unrelated_entrypoint_added:runtime.cs", generation.repair_scope_errors(old, revised, issue))

    def test_public_append_planned_verification_reaches_selection_and_validation(self):
        self.exercise_public_generation(planned_verification=True)

    def test_oversized_auxiliary_sources_are_fully_inspected_before_append_admission(self):
        # The production fixture includes the full Chapter 5 authority. Its
        # core context must fit while the three large sources still require transport.
        with patch.dict(os.environ, {"SC_CAPABILITY_MAX_INPUT_TOKENS": "24000"}):
            self.exercise_public_generation(fault="evidence_transport", failed_generations=0)

    def test_synthesis_context_deduplicates_transport_citations_without_dropping_transport(self):
        payload = {
            "task_views": [
                {"taskmaster_id": 1, "_source_view": "tasks_back.json", "title": "Combat",
                 "acceptance": ["Ready"], "labels": ["back"], "unused_metadata": "preserve-me"},
                {"taskmaster_id": 1, "_source_view": "tasks_gameplay.json", "title": "Combat",
                 "acceptance": ["Ready"], "labels": ["gameplay"], "unused_metadata": "preserve-me"},
            ],
            "task_master": [{"id": 1, "title": "Combat", "status": "done",
                             "unused_metadata": "preserve-master"}],
            "available_reference_paths": ["unused/path.cs"],
            "evidence": [{"path": "test.cs", "sha256": "sha256:test", "text": "complete source"}],
        }
        transport = {
            "context": deepcopy(payload),
            "plan": {"inventory": [{"path": "test.cs", "sha256": "sha256:test", "status": "complete"}],
                     "context_sha256": "sha256:context"},
            "audits": [{"audit": {"reports": {
                "part-1": {"part_id": "part-1", "citations": [1],
                            "citation_texts": [{"line": 1, "text": "complete source"}],
                            "facts": ["fact"]}}}}],
        }
        reduced = generation.synthesis_context(payload, transport)
        self.assertNotIn("citation_texts", json.dumps(reduced, ensure_ascii=False))
        self.assertIn("preserve-me", json.dumps(reduced, ensure_ascii=False))
        self.assertIn("preserve-master", json.dumps(reduced, ensure_ascii=False))
        self.assertNotIn("text", reduced["evidence"][0])
        group = reduced["task_views"][0]
        self.assertEqual(["Ready"], group["shared"]["acceptance"])
        rebuilt = [{"taskmaster_id": group["taskmaster_id"], **group["shared"], **view["fields"],
                    "_source_view": view["source"]} for view in group["views"]]
        self.assertEqual(payload["task_views"], rebuilt)
        self.assertEqual([1], reduced["evidence_inspections"][0]["reports"]["part-1"]["citations"])
        self.assertEqual("complete source", transport["audits"][0]["audit"]["reports"]["part-1"]["citation_texts"][0]["text"])
        self.assertEqual("complete source", transport["context"]["evidence"][0]["text"])
        self.assertEqual(["unused/path.cs"], transport["context"]["available_reference_paths"])

    def exercise_public_generation(self, planned_verification=False, fault=None, failed_generations=1,
                                   drift_after_first_dispatch=False, drift_after_final_dispatch=False,
                                   public_candidate_drift=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            import planning_acceptance_fixture as fixture
            import chapter5_semantic_reconciliation as chapter5
            original_semantics = fixture._build_semantics
            def fixture_semantics(ledger):
                semantics, by_block = original_semantics(ledger)
                mapping = {row["requirement_id"]: "FR-" + letter
                           for row, letter in zip(semantics["requirements"], ("a", "b"))}
                for row in semantics["requirements"]:
                    row["requirement_id"] = mapping[row["requirement_id"]]
                return semantics, {block: mapping[rid] for block, rid in by_block.items()}
            with patch.object(fixture, "_build_semantics", fixture_semantics):
                fixture.build_fixture(root)
            run = root / "logs/ci/mvg-planning/fixture"
            candidate = run / "candidates/candidate-1"
            prepared = candidate / "analysis-input"
            flows, tests, caps, views, reqs = [], [], [], [], []
            real_semantics = plan_mvg.load_json(root / plan_mvg.SEMANTICS)
            real_views = plan_mvg.load_json(root / plan_mvg.TASK_VIEWS[1])
            for index, letter in enumerate(("a", "b"), 1):
                task_id = fixture.TASK_IDS[index - 1]
                rid, cid, fid, tid = "FR-" + letter, "CAP-" + letter, "flow-" + letter, "test-" + letter
                refs = [fixture.CONTRACT_PATH.as_posix(), "Game.Core/Runtime.cs", fixture.TEST_PATH.as_posix()]
                flows.append({"id": fid, "outcome": letter, "requirement_ids": [rid], "capability_refs": [cid],
                    "task_ids": [task_id], "source_paths": [fixture.GDD_PATH.as_posix()], "test_ids": [tid], "handoffs": [
                        {"producer_task": task_id, "consumer_task": task_id, "owner_task": task_id,
                         "contract_ref": refs[0], "behavior": letter, "test_ids": [tid]}]})
                tests.append({"id": tid, "kind": "dotnet", "state": "implemented", "path": refs[2],
                              "selector": "RuntimeTests", "evidence_level": "domain-integration", "min_tests": 1})
                real_req = next(row for row in real_semantics["requirements"] if row["requirement_id"] == rid)
                caps.append({"capability_id": cid, "requirement_ids": [rid], "description": letter,
                             "source_block_ids": real_req["source_block_ids"]})
                reqs.append(real_req)
                views.append(dict(next(row for row in real_views if row["taskmaster_id"] == task_id), capability_refs=[cid]))
            manifest = {"schema_version": "newrouge.mvg-integration.v1", "mvg_id": "fixture", "flows": flows,
                        "tests": tests, "coverage": {"mode": "critical", "scope_id": "fixture",
                        "required_flow_ids": ["flow-a", "flow-b"], "blocking_task_ids": [],
                        "excluded_claims": ["Runtime remains unverified"]}}
            if fault == "duplicate_coverage":
                caps = [dict(caps[0], requirement_ids=["FR-a", "FR-b"])]
                flows[1]["capability_refs"] = ["CAP-a"]
                views[1]["capability_refs"] = ["CAP-a"]
            manifest_path = root / "docs/testing/mvg/fixture.json"
            capabilities_path = root / "docs/planning/semantic-topology/capabilities.v1.json"
            atomic_json(manifest_path, manifest)
            atomic_json(capabilities_path, {"schema_version": "newrouge.capabilities.v1", "capabilities": caps,
                                          "source_revision": real_semantics["source_revision"]})
            for view_path in plan_mvg.TASK_VIEWS:
                atomic_json(root / view_path, views)
            for ref in refs:
                dest = root / ref
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text("public class RuntimeTests {}" + (
                    "\n// Full auxiliary source line\n" * 2000 if fault == "evidence_transport" else ""), encoding="utf-8")
            snapshot = plan_mvg.load_json(root / chapter5.DEFAULT_EXTRACTION_SNAPSHOT)
            by_block = {block: row["requirement_id"] for row in reqs for block in row["source_block_ids"]}
            by_task = {str(row["taskmaster_id"]): row["semantic_refs"] for row in views}
            fixture._write_readiness(root, snapshot, real_semantics, by_block, by_task)
            state = plan_mvg.prepare(root, run_id="fixture", capabilities_path=capabilities_path,
                manifest_path=manifest_path, task_ids=list(map(str, fixture.TASK_IDS)), allow_unready=False, evidence_refs=refs)
            import shutil
            shutil.copytree(run / "analysis-input", prepared)
            description = {"schema_version": RUNNER_SCHEMA, "filesystem_scope": "workspace_only",
                           "fresh_session_per_invocation": True, "can_read_outside_workspace": False,
                           "model": "fixture", "model_tools": []}
            if public_candidate_drift:
                changed = {}
                for label in plan_mvg.MVG_CANDIDATE_LABELS:
                    candidate_input = run / "candidates" / label / "analysis-input"
                    if not candidate_input.exists():
                        shutil.copytree(run / "analysis-input", candidate_input)
                    target = candidate_input / "capabilities.v1.json"
                    data = plan_mvg.load_json(target)
                    data["capabilities"].reverse()
                    atomic_json(target, data)
                    changed[label] = target.read_bytes()
                with patch.object(plan_mvg, "inspect_isolated_runner", return_value=description), \
                     patch.object(plan_mvg, "run_isolated_model") as dispatch:
                    with self.assertRaises(ValueError):
                        plan_mvg.generate(root, run_id="fixture", timeout_sec=1, llm_backend="codex-cli")
                    dispatch.assert_not_called()
                for label in plan_mvg.MVG_CANDIDATE_LABELS:
                    candidate_root = run / "candidates" / label
                    self.assertEqual(changed[label], (candidate_root / "analysis-input/capabilities.v1.json").read_bytes())
                    freshness = plan_mvg.load_json(candidate_root / "input-freshness.json")
                    self.assertEqual("blocked", freshness["status"])
                    self.assertIn("analysis-input/capabilities.v1.json", freshness["drift"])
                self.assertFalse((run / "proposal.json").exists())
                return
            seen = []
            generations = []

            def invoke_factory(workspace):
                def invoke(prompt, number, *, output_name, output_schema_path, output_schema):
                    atomic_json(output_schema_path, output_schema)
                    props = output_schema["properties"]
                    value = {key: prop["const"] for key, prop in props.items() if "const" in prop}
                    seen.append((number, value["schema_version"], prompt))
                    if value["schema_version"] == "newrouge.mvg-evidence-audit.v1":
                        import json
                        payload = json.loads(prompt.split("\n", 1)[1].split("\nSOURCE PART ", 1)[0])
                        reports = {}
                        for part in payload["parts"]:
                            reports[part["part_id"]] = {"part_id": part["part_id"], "verdict": "relevant",
                                "requirement_ids": [payload["core"]["requirements"][0]["requirement_id"]],
                                "rationale": "Complete source inspected", "facts": ["Evidence supports runtime boundary"],
                                "citations": [1], "hard_issues": []}
                        value["reports"] = reports
                    elif value["schema_version"] == plan_mvg.MVG_SELECTION_SCHEMA:
                        labels = props["candidate_reviews"]["items"]["properties"]["label"]["enum"]
                        value.update(status="selected", selected="A", tradeoffs=["Prefer clear journeys"], evidence_refs=[],
                                     rationale="All candidates are admitted", candidate_reviews=[
                                         {"label": label, "verdict": "viable", "rank": rank,
                                          "rationale": "Valid complete proposal"} for rank, label in enumerate(labels, 1)])
                    elif value["schema_version"] == generation.APPEND_SCHEMA:
                        cid = value["capability_id"]
                        index = next(i for i, cap in enumerate(caps) if cap["capability_id"] == cid)
                        task_id = fixture.TASK_IDS[index]
                        value.update(flows=[], tests=[], change_reviews=[], gaps=[], notes=[],
                            coverage_table=[{"requirement_id": reqs[index]["requirement_id"], "flow_id": flows[index]["id"],
                                "capability_ref": cid, "task_id": task_id, "disposition": "flow", "rationale": "Concrete journey",
                                "sink_id": None, "verification_ref": None, "authority_ref": None, "authority_review": None}],
                            entrypoints=[{"status": "planned", "flow_ids": [flows[index]["id"]], "owner_task": task_id,
                                "path": "Game.Core/Runtime.cs", "symbol": "Execute", "inputs": "Request", "state": "Ready",
                                "assertions": "Consumer state observed", "implementation_acceptance": "Test failure recovery"}])
                        if fault == "duplicate_coverage":
                            value["coverage_table"].append(dict(value["coverage_table"][0],
                                requirement_id="FR-b", flow_id="flow-b", task_id=fixture.TASK_IDS[1]))
                            value["entrypoints"].append(dict(value["entrypoints"][0], flow_ids=["flow-b"], owner_task=fixture.TASK_IDS[1]))
                        generations.append(prompt)
                        if len(generations) <= failed_generations:
                            if fault == "duplicate_coverage":
                                value["coverage_table"][1] = deepcopy(value["coverage_table"][0])
                            elif fault == "missing_entrypoints":
                                value["entrypoints"] = []
                        if fault == "predecessor_entrypoint" and cid == "CAP-b":
                            value["entrypoints"].append(dict(value["entrypoints"][0],
                                flow_ids=["flow-a"], owner_task=fixture.TASK_IDS[0], symbol="Resume"))
                        if planned_verification:
                            value["tests"] = [{"id": "verify-" + flows[index]["id"] + "-failure",
                                "flow_id": flows[index]["id"], "state": "planned", "kind": "dotnet",
                                "path": "Game.Core.Tests/PlannedFailureTests.cs", "selector": "PlannedFailureTests",
                                "evidence_level": "domain-integration", "min_tests": 1, "test_refs": [],
                                "owner_task": task_id, "requirement_ids": [reqs[index]["requirement_id"]],
                                "handoff_indexes": [0], "inputs": "Invalid request", "assertions": "Recovery preserves state",
                                "implementation_acceptance": "Exercise actual consumer recovery"}]
                    else:
                        coverage = props["requirement_reviews"]["items"]["anyOf"]
                        rows = []
                        for item in coverage:
                            row = {key: prop["const"] for key, prop in item["properties"].items() if "const" in prop}
                            row.update(verdict="covered", rationale="Source supports the observable interaction", repair_action="none")
                            rows.append(row)
                        value.update(verdict="approved", findings=[], requirement_reviews=rows,
                            flow_reviews=[{"flow_id": fid, "verdict": "sound", "rationale": "Owned handoff"}
                                for fid in props["flow_reviews"]["items"]["properties"]["flow_id"].get("enum", [])])
                    output = workspace / Path(output_name).name
                    atomic_json(output, value)
                    if drift_after_first_dispatch and len(seen) == 1:
                        source = root / fixture.GDD_PATH
                        source.write_text(source.read_text(encoding="utf-8") + "\nBound source drift.\n",
                                          encoding="utf-8")
                    if drift_after_final_dispatch and len(seen) == 4:
                        source = root / fixture.GDD_PATH
                        source.write_text(source.read_text(encoding="utf-8") + "\nFinal dispatch drift.\n",
                                          encoding="utf-8")
                    receipt = {"model": "fixture", "model_tools": [], "output_sha256": file_sha(output)}
                    name = Path(output_name).with_suffix("").as_posix().replace("/", "-")
                    reports = list((workspace / "llm-sandbox" / f"attempt-{number}" / name).glob("runner-input-integrity.json"))
                    if reports:
                        receipt["input_integrity"] = plan_mvg.load_json(reports[0], {})
                    return output, {"backend_info": description, "receipt": receipt}
                return invoke

            if drift_after_first_dispatch:
                result = generation.generate_append(root, state, candidate, invoke_factory=invoke_factory,
                                                   before_call=lambda phase: None, checkpoint=lambda ledger: None)
                self.assertEqual("blocked", result["status"])
                self.assertEqual(1, len(seen))
                freshness = plan_mvg.load_json(candidate / "input-freshness.json")
                self.assertEqual("blocked", freshness["status"])
                self.assertTrue(any(fixture.GDD_PATH.as_posix() in str(row) for row in freshness["drift"]))
                return
            if drift_after_final_dispatch:
                result = generation.generate_append(root, state, candidate, invoke_factory=invoke_factory,
                                                   before_call=lambda phase: None, checkpoint=lambda ledger: None)
                self.assertEqual("blocked", result["status"])
                self.assertEqual(4, len(seen))
                freshness = plan_mvg.load_json(candidate / "input-freshness.json")
                self.assertEqual("blocked", freshness["status"])
                self.assertTrue(any(fixture.GDD_PATH.as_posix() in str(row) for row in freshness["drift"]))
                return
            result = generation.generate_append(root, state, candidate, invoke_factory=invoke_factory,
                                                 before_call=lambda phase: None, checkpoint=lambda ledger: None)
            self.assertEqual("admitted", result["status"], result.get("errors", result.get("issue_events", [])[:1]))
            if not fault:
                self.assertEqual(4, len(seen))
            if planned_verification:
                self.assertEqual(4, len(result["accepted"]["tests"]))
                self.assertEqual(["test-a", "verify-flow-a-failure"],
                    result["accepted"]["manifest_candidate"]["flows"][0]["handoffs"][0]["test_ids"])
            if not fault:
                self.assertIn("flow-a", seen[2][2], "Accepted predecessor must reach the next scope")
            proof = result["proof"]
            errors = plan_mvg.candidate_admission_errors(root, state, result["accepted"], proof)
            self.assertEqual([], errors)
            if fault == "evidence_transport":
                self.assertGreater(len(seen), 4)
                self.assertEqual(len(seen), result["total_invocations"])
                self.assertNotIn("citation_texts", generations[0])
                for record in proof["records"]:
                    transport = record["proof"]["evidence_transport"]
                    inventory = {row["path"] for row in transport["plan"]["inventory"]}
                    evidence = {row["path"]: row for row in transport["context"]["evidence"]}
                    self.assertTrue(set(refs) <= inventory)
                    self.assertTrue(all(len(evidence[ref]["text"]) > 50000 for ref in refs))
                    self.assertIn(chapter5.DEFAULT_EXTRACTION_SNAPSHOT.as_posix(), inventory)
                corrupt_transport = deepcopy(proof)
                corrupt_transport["records"][0]["proof"]["evidence_transport"]["audits"].pop()
                self.assertTrue(plan_mvg.candidate_admission_errors(root, state, result["accepted"], corrupt_transport))
            from _mvg_planning_review import review_execution_errors
            execution = plan_mvg.load_json(candidate / "admission-execution.json", {})
            self.assertEqual([], review_execution_errors(state, result["accepted"], execution, proof))
            corrupted = deepcopy(proof)
            corrupted["records"][0]["proof"]["review"]["flow_reviews"][0]["verdict"] = "blocked"
            self.assertTrue(plan_mvg.candidate_admission_errors(root, state, result["accepted"], corrupted))

            if fault:
                self.assertEqual(failed_generations, len(result.get("issue_events", [])))
                if failed_generations == 4:
                    self.assertEqual(3, result["restarts"][0]["repair_attempts"])
                    import json
                    restarted = json.loads(generations[4].split("\n", 1)[1])
                    self.assertIsNone(restarted["repair_proposal"])
                    self.assertIsNone(restarted["hard_issue"])
                if fault == "predecessor_entrypoint":
                    bound = proof["records"][1]["proof"]
                    self.assertEqual({"flow-a", "flow-b"},
                        {row["id"] for row in bound["projection"]["manifest_candidate"]["flows"]})
                    self.assertEqual(["FR-a", "FR-b"], bound["required_requirement_ids"])
                    self.assertEqual(3, len(bound["projection"]["entrypoints"]))
                    omitted = deepcopy(proof)
                    omitted["records"][1]["proof"]["projection"]["manifest_candidate"]["flows"] = [
                        row for row in bound["projection"]["manifest_candidate"]["flows"] if row["id"] == "flow-b"]
                    self.assertIn("capability_admission_projection_changed",
                        [row["code"] for row in plan_mvg.candidate_admission_errors(root, state, result["accepted"], omitted)])
                return

            # Exercise the actual public generate -> selection -> review ->
            # validate chain using the same schema-enforcing fake transport.
            state.update(schema_version=plan_mvg.RUN_SCHEMA, formal_ready=True, task_scope=list(fixture.TASK_IDS))
            atomic_json(run / "run.json", state)
            seen.clear()

            def runner(_runner, *, workspace, prompt_path, output_path, output_schema, **kwargs):
                invoke = invoke_factory(workspace)
                schema = plan_mvg.load_json(output_schema, {})
                generated, execution = invoke(prompt_path.read_text(encoding="utf-8"), len(seen) + 1,
                    output_name=output_path.name, output_schema_path=output_schema, output_schema=schema)
                self.assertEqual(generated, output_path)
                return execution["receipt"]

            with patch.object(plan_mvg, "inspect_isolated_runner", return_value=description), \
                 patch.object(plan_mvg, "run_isolated_model", side_effect=runner):
                result = plan_mvg.generate(root, run_id="fixture", timeout_sec=1, llm_backend="codex-cli")
                self.assertEqual(3, result["candidate_count"])
                calls_before_review = len(seen)
                reviewed = plan_mvg.review(root, run_id="fixture", runner=Path("unused"), timeout_sec=1)
                self.assertEqual("approved", reviewed["status"])
                self.assertEqual(calls_before_review, len(seen), "Final review must not call a model")
                validated = plan_mvg.validate(root, run_id="fixture")
                self.assertTrue(validated["formal_applicable"], validated)
                reused = plan_mvg.generate(root, run_id="fixture", timeout_sec=1, llm_backend="codex-cli")
                self.assertEqual(result["selected"], reused["selected"])
                self.assertEqual(calls_before_review, len(seen), "Resume must verify hash-bound artifacts locally")
                for label in plan_mvg.MVG_CANDIDATE_LABELS:
                    ledger = plan_mvg.load_json(run / "candidates" / label / "capability-append/append-ledger.json", {})
                    self.assertEqual(["CAP-a", "CAP-b"], ledger["completed"])
                    self.assertEqual(4, ledger["total_invocations"])
                from _project_health_planning import _mvg_valid_candidates
                persisted = plan_mvg.load_json(run / "run.json", {})
                self.assertEqual(list(plan_mvg.MVG_CANDIDATE_LABELS), _mvg_valid_candidates(run, persisted),
                                 "HTTP recovery must recognize append admission proofs")


if __name__ == "__main__":
    unittest.main()
