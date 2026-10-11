"""Offline tests for Capability-local generation and admission."""
from copy import deepcopy
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
            prepared = Path(directory)
            scope = {"capability": {}, "requirement_ids": ["FR-A"], "cumulative_requirement_ids": ["FR-A"]}
            base = {"manifest_candidate": {"flows": [{"id": "flow-a", "requirement_ids": ["FR-A"],
                    "task_ids": [1], "test_ids": []}]}, "coverage_table": [], "tests": [], "entrypoints": []}
            revised = deepcopy(base)
            revised["entrypoints"] = [{"owner_task": 9, "flow_ids": ["flow-a"], "path": "runtime.cs", "symbol": "Run"}]
            atomic_json(prepared / "semantic-requirements.v1.json", {"requirements": [{"requirement_id": "FR-A"}]})
            atomic_json(prepared / "capabilities.v1.json", {"capabilities": []})
            atomic_json(prepared / "task-master.json", {"master": {"tasks": [{"id": 1}, {"id": 9, "details": "Boundary owner"}]}})
            atomic_json(prepared / "task-views/tasks_back.json", [{"taskmaster_id": 9, "semantic_refs": [],
                "acceptance": ["Recovery is observable"], "source_refs": ["owner.md"]}])
            atomic_json(prepared / "task-views/tasks_gameplay.json", [])
            (prepared / "references").mkdir()
            (prepared / "references/owner.md").write_text("Full boundary evidence", encoding="utf-8")
            context = generation.complete_scope_context(prepared, scope, base, revised)
            self.assertEqual({1, 9}, {row["id"] for row in context["task_master"]})
            self.assertEqual(["Recovery is observable"], context["task_views"][0]["acceptance"])
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

    def exercise_public_generation(self, planned_verification=False, fault=None, failed_generations=1):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / "logs/ci/mvg-planning/fixture"
            candidate = run / "candidates/candidate-1"
            prepared = candidate / "analysis-input"
            tasks = {"master": {"tasks": [{"id": 1, "status": "done"}, {"id": 2, "status": "done"}]}}
            atomic_json(root / ".taskmaster/tasks/tasks.json", tasks)
            atomic_json(prepared / "task-master.json", tasks)
            flows, tests, caps, views, reqs = [], [], [], [], []
            for index, letter in enumerate(("a", "b"), 1):
                rid, cid, fid, tid = "FR-" + letter, "CAP-" + letter, "flow-" + letter, "test-" + letter
                refs = ["Game.Core/Contracts/Event.cs", "Game.Core/Runtime.cs", "Game.Core.Tests/RuntimeTests.cs"]
                flows.append({"id": fid, "outcome": letter, "requirement_ids": [rid], "capability_refs": [cid],
                    "task_ids": [index], "source_paths": [refs[1]], "test_ids": [tid], "handoffs": [
                        {"producer_task": index, "consumer_task": index, "owner_task": index,
                         "contract_ref": refs[0], "behavior": letter, "test_ids": [tid]}]})
                tests.append({"id": tid, "kind": "dotnet", "state": "implemented", "path": refs[2],
                              "selector": "RuntimeTests", "evidence_level": "domain-integration", "min_tests": 1})
                caps.append({"capability_id": cid, "requirement_ids": [rid], "description": letter})
                reqs.append({"requirement_id": rid, "statement": letter})
                views.append({"taskmaster_id": index, "semantic_refs": [rid], "capability_refs": [cid],
                              "contractRefs": [refs[0]], "test_refs": [refs[2]]})
            manifest = {"schema_version": "newrouge.mvg-integration.v1", "mvg_id": "fixture", "flows": flows,
                        "tests": tests, "coverage": {"mode": "critical", "scope_id": "fixture",
                        "required_flow_ids": ["flow-a", "flow-b"], "blocking_task_ids": [],
                        "excluded_claims": ["Runtime remains unverified"]}}
            if fault == "duplicate_coverage":
                caps = [dict(caps[0], requirement_ids=["FR-a", "FR-b"])]
                flows[1]["capability_refs"] = ["CAP-a"]
                views[1]["capability_refs"] = ["CAP-a"]
            atomic_json(prepared / "existing-manifest.json", manifest)
            atomic_json(prepared / "capabilities.v1.json", {"schema_version": "newrouge.capabilities.v1", "capabilities": caps})
            atomic_json(prepared / "semantic-requirements.v1.json", {"requirements": reqs})
            atomic_json(prepared / "task-views/tasks_back.json", views)
            atomic_json(prepared / "task-views/tasks_gameplay.json", [])
            authority, files = {}, {}
            for ref in refs:
                dest = root / ref
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text("// RuntimeTests evidence", encoding="utf-8")
                copy = prepared / "references" / ref
                copy.parent.mkdir(parents=True, exist_ok=True)
                copy.write_text(dest.read_text(encoding="utf-8"), encoding="utf-8")
                authority[ref], files["references/" + ref] = file_sha(dest), file_sha(copy)
            atomic_json(prepared / "analysis-index.json", {"authority_inputs": authority, "files": files})
            import shutil
            shutil.copytree(prepared, run / "analysis-input")
            state = {"run_id": "fixture", "analysis_identity_sha256": "sha256:fixture", "capabilities_path": "unused",
                     "capabilities_sha256": "sha256:fixture", "planning_scope": plan_mvg._manifest_planning_scope(manifest, views)}
            description = {"schema_version": RUNNER_SCHEMA, "filesystem_scope": "workspace_only",
                           "fresh_session_per_invocation": True, "can_read_outside_workspace": False,
                           "model": "fixture", "model_tools": []}
            seen = []
            generations = []

            def invoke_factory(workspace):
                def invoke(prompt, number, *, output_name, output_schema_path, output_schema):
                    atomic_json(output_schema_path, output_schema)
                    props = output_schema["properties"]
                    value = {key: prop["const"] for key, prop in props.items() if "const" in prop}
                    seen.append((number, value["schema_version"], prompt))
                    if value["schema_version"] == plan_mvg.MVG_SELECTION_SCHEMA:
                        labels = props["candidate_reviews"]["items"]["properties"]["label"]["enum"]
                        value.update(status="selected", selected="A", tradeoffs=["Prefer clear journeys"], evidence_refs=[],
                                     rationale="All candidates are admitted", candidate_reviews=[
                                         {"label": label, "verdict": "viable", "rank": rank,
                                          "rationale": "Valid complete proposal"} for rank, label in enumerate(labels, 1)])
                    elif value["schema_version"] == generation.APPEND_SCHEMA:
                        cid = value["capability_id"]
                        index = next(i for i, cap in enumerate(caps) if cap["capability_id"] == cid)
                        value.update(flows=[], tests=[], change_reviews=[], gaps=[], notes=[],
                            coverage_table=[{"requirement_id": reqs[index]["requirement_id"], "flow_id": flows[index]["id"],
                                "capability_ref": cid, "task_id": index + 1, "disposition": "flow", "rationale": "Concrete journey",
                                "sink_id": None, "verification_ref": None, "authority_ref": None, "authority_review": None}],
                            entrypoints=[{"status": "planned", "flow_ids": [flows[index]["id"]], "owner_task": index + 1,
                                "path": "Game.Core/Runtime.cs", "symbol": "Execute", "inputs": "Request", "state": "Ready",
                                "assertions": "Consumer state observed", "implementation_acceptance": "Test failure recovery"}])
                        if fault == "duplicate_coverage":
                            value["coverage_table"].append(dict(value["coverage_table"][0],
                                requirement_id="FR-b", flow_id="flow-b", task_id=2))
                            value["entrypoints"].append(dict(value["entrypoints"][0], flow_ids=["flow-b"], owner_task=2))
                        generations.append(prompt)
                        if len(generations) <= failed_generations:
                            if fault == "duplicate_coverage":
                                value["coverage_table"][1] = deepcopy(value["coverage_table"][0])
                            elif fault == "missing_entrypoints":
                                value["entrypoints"] = []
                        if fault == "predecessor_entrypoint" and cid == "CAP-b":
                            value["entrypoints"].append(dict(value["entrypoints"][0],
                                flow_ids=["flow-a"], owner_task=1, symbol="Resume"))
                        if planned_verification:
                            value["tests"] = [{"id": "verify-" + flows[index]["id"] + "-failure",
                                "flow_id": flows[index]["id"], "state": "planned", "kind": "dotnet",
                                "path": "Game.Core.Tests/PlannedFailureTests.cs", "selector": "PlannedFailureTests",
                                "evidence_level": "domain-integration", "min_tests": 1, "test_refs": [],
                                "owner_task": index + 1, "requirement_ids": [reqs[index]["requirement_id"]],
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
                    return output, {"backend_info": description, "receipt": {"model": "fixture", "model_tools": [],
                                                                                 "output_sha256": file_sha(output)}}
                return invoke

            result = generation.generate_append(root, state, candidate, invoke_factory=invoke_factory,
                                                 before_call=lambda phase: None, checkpoint=lambda ledger: None)
            self.assertEqual("admitted", result["status"], result.get("issue_events", [])[:1])
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
            state.update(schema_version=plan_mvg.RUN_SCHEMA, formal_ready=True, task_scope=[1, 2])
            atomic_json(run / "run.json", state)
            seen.clear()

            def runner(_runner, *, workspace, prompt_path, output_path, output_schema, **kwargs):
                invoke = invoke_factory(workspace)
                schema = plan_mvg.load_json(output_schema, {})
                generated, execution = invoke(prompt_path.read_text(encoding="utf-8"), len(seen) + 1,
                    output_name=output_path.name, output_schema_path=output_schema, output_schema=schema)
                self.assertEqual(generated, output_path)
                return execution["receipt"]

            with patch.object(plan_mvg, "_validate_input_freshness"), \
                 patch.object(plan_mvg, "inspect_isolated_runner", return_value=description), \
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
