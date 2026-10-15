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
    def checkpoint_fixture(self, run):
        seed, accepted = {"notes": []}, {"notes": ["chosen"]}
        receipt = run / "receipt.json"
        atomic_json(receipt, {"verified": True})
        step = {"selected_candidate": "candidate-1", "receipt_path": "receipt.json",
                "receipt_sha256": file_sha(receipt), "proposal_sha256": canonical_sha(accepted),
                "input_identity": {"base_sha256": canonical_sha(seed)},
                "record": {"delta": {"notes": ["chosen"]}},
                "admissions": {"candidate-1": {"proof_sha256": "sha256:proof",
                                               "proposal_sha256": "sha256:source"}}}
        state = {"run_id": "checkpoint-fixture", "capability_selection": {
            "selected": [], "accepted_sha256": canonical_sha(seed), "checkpoint_head": None,
            "current": {"selection_attempts": [step]}}}
        atomic_json(run / "run.json", state)
        return state, seed, accepted, step

    def test_checkpoint_bundle_write_failure_preserves_prior_pointer(self):
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec("_mvg_capability_checkpoint"))
        import _mvg_capability_checkpoint as checkpoint
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            state, seed, accepted, step = self.checkpoint_fixture(run)
            prior = deepcopy(state)
            with patch.object(checkpoint, "atomic_json", side_effect=OSError("fixture write failure")):
                with self.assertRaisesRegex(OSError, "fixture write failure"):
                    checkpoint.prepare_checkpoint(run, state, "CAP-a", 0, seed, accepted, step)
            self.assertEqual(prior, plan_mvg.load_json(run / "run.json"))

    def test_checkpoint_stale_base_and_receipt_drift_never_publish(self):
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec("_mvg_capability_checkpoint"))
        import _mvg_capability_checkpoint as checkpoint
        for mutation in ("base", "receipt"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as folder:
                run = Path(folder)
                state, seed, accepted, step = self.checkpoint_fixture(run)
                pointer = checkpoint.prepare_checkpoint(run, state, "CAP-a", 0, seed, accepted, step)
                if mutation == "base":
                    changed = deepcopy(state)
                    changed["capability_selection"]["accepted_sha256"] = "sha256:stale"
                    atomic_json(run / "run.json", changed)
                else:
                    atomic_json(run / "receipt.json", {"verified": False})
                prior = plan_mvg.load_json(run / "run.json")
                with self.assertRaisesRegex(ValueError, "checkpoint_(stale_base|receipt_changed)"):
                    checkpoint.commit_checkpoint(run, state, pointer, step, accepted)
                self.assertEqual(prior, plan_mvg.load_json(run / "run.json"))

    def test_checkpoint_pointer_write_failure_does_not_mutate_memory(self):
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec("_mvg_capability_checkpoint"))
        import _mvg_capability_checkpoint as checkpoint
        with tempfile.TemporaryDirectory() as folder:
            run = Path(folder)
            state, seed, accepted, step = self.checkpoint_fixture(run)
            pointer = checkpoint.prepare_checkpoint(run, state, "CAP-a", 0, seed, accepted, step)
            prior = deepcopy(state)
            with self.assertRaisesRegex(OSError, "fixture pointer failure"):
                checkpoint.commit_checkpoint(run, state, pointer, step, accepted,
                    writer=lambda *_: (_ for _ in ()).throw(OSError("fixture pointer failure")))
            self.assertEqual(prior, state)
            self.assertEqual(prior, plan_mvg.load_json(run / "run.json"))

    def test_coordinator_replaces_corrupt_execution_receipt_with_authoritative_block(self):
        self.exercise_corrupt_execution_receipt(corrupt_json=True)

    def test_coordinator_replaces_non_object_execution_receipt_with_authoritative_block(self):
        self.exercise_corrupt_execution_receipt(corrupt_json=False)

    def exercise_corrupt_execution_receipt(self, *, corrupt_json):
        import _mvg_capability_selection as coordinator
        from _planning_skill_common import load_json
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run = root / "logs/ci/mvg-planning/corrupt-receipt"
            run.mkdir(parents=True)
            receipt_path = run / "model-execution.json"
            if not corrupt_json:
                atomic_json(receipt_path, ["old non-object receipt"])
            state = {"run_id": "corrupt-receipt", "analysis_identity_sha256": "sha256:fixture",
                     "generation_strategy": coordinator.STRATEGY}
            original_loader = coordinator.load_json
            calls = []
            def loader(path, default=None):
                if corrupt_json and path == receipt_path and not path.is_file():
                    raise ValueError("fixture corrupt JSON at line 1 column 1")
                return original_loader(path, default)
            with patch.object(coordinator, "frozen_scopes", return_value=[]), \
                 patch.object(coordinator, "seed_proposal", return_value={}), \
                 patch.object(coordinator, "verified_prefix", side_effect=ValueError("fixture frozen input rejection")), \
                 patch.object(coordinator, "load_json", side_effect=loader):
                with self.assertRaisesRegex(ValueError, "fixture frozen input rejection"):
                    coordinator.generate_selected_capabilities(root, run, state, backend="fixture",
                        invoke_factory=lambda *args: calls.append(args), selector_factory=lambda *args: calls.append(args))
            self.assertEqual([], calls)
            persisted = load_json(run / "run.json", {})
            execution = load_json(receipt_path, {})
            self.assertEqual("blocked", persisted["selection_status"])
            self.assertEqual("fixture frozen input rejection", persisted["selection_block_reason"])
            self.assertEqual("fixture frozen input rejection", execution["selection_error"])
            self.assertEqual("blocked", execution["selection_status"])
            self.assertTrue(execution["previous_receipt_error"])
            self.assertEqual(persisted["capability_selection"], execution["capability_selection"])

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

    def test_public_selection_uses_mixed_winners_and_one_shared_next_seed(self):
        self.exercise_public_generation(coordinator_case="mixed")

    def test_public_selected_checkpoint_contains_identity_and_atomic_bundle(self):
        self.exercise_public_generation(coordinator_case="checkpoint")

    def test_public_checkpoint_pointer_failure_keeps_committed_prefix_and_recovers(self):
        self.exercise_public_generation(coordinator_case="checkpoint-interruption")

    def test_public_checkpoint_replace_then_error_keeps_new_committed_prefix(self):
        self.exercise_public_generation(coordinator_case="checkpoint-after-error")

    def test_public_checkpoint_process_exit_before_commit_keeps_old_prefix(self):
        self.exercise_public_generation(coordinator_case="checkpoint-before-exit")

    def test_public_checkpoint_process_exit_after_commit_keeps_new_prefix(self):
        self.exercise_public_generation(coordinator_case="checkpoint-after-exit")

    def test_public_checkpoint_bundle_tampering_blocks_every_consumer(self):
        self.exercise_public_generation(coordinator_case="checkpoint-tamper")

    def test_public_checkpoint_unknown_commit_outcome_never_rolls_back(self):
        self.exercise_public_generation(coordinator_case="checkpoint-reread-unknown")

    def test_public_checkpoint_rechecks_predecessor_after_staging(self):
        self.exercise_public_generation(coordinator_case="checkpoint-predecessor-drift")

    def test_public_checkpoint_rechecks_predecessor_proof_after_staging(self):
        self.exercise_public_generation(coordinator_case="checkpoint-predecessor-proof-drift")

    def test_public_checkpoint_stale_base_keeps_blocked_evidence(self):
        self.exercise_public_generation(coordinator_case="checkpoint-public-stale")

    def test_public_checkpoint_receipt_drift_keeps_blocked_evidence(self):
        self.exercise_public_generation(coordinator_case="checkpoint-public-receipt")

    def test_public_legacy_selected_prefix_recovers_without_checkpoint_protocol(self):
        self.exercise_public_generation(coordinator_case="legacy-prefix")

    def test_public_incomplete_current_candidates_preserve_selected_prefix(self):
        self.exercise_public_generation(coordinator_case="incomplete")

    def test_public_recovery_rejects_prefix_scope_and_receipt_tampering_without_models(self):
        self.exercise_public_generation(coordinator_case="tamper")

    def test_public_selection_receipt_recovers_before_prefix_publication_without_models(self):
        self.exercise_public_generation(coordinator_case="receipt-recovery")

    def test_public_selected_chain_apply_replay_uses_existing_journal_without_models(self):
        self.exercise_public_generation(coordinator_case="apply-replay")

    def test_public_worker_exception_isolates_slot_and_preserves_failure_receipt(self):
        self.exercise_public_generation(coordinator_case="worker-exception")

    def test_public_selector_preparation_error_stops_without_selector_attempt(self):
        self.exercise_public_generation(coordinator_case="selector-preparation")

    def test_public_run_budget_boundary_preserves_prefix_and_stays_terminal(self):
        self.exercise_public_generation(coordinator_case="run-budget")

    def test_public_reserved_worker_call_interruption_keeps_charge_on_recovery(self):
        self.exercise_public_generation(coordinator_case="reserved-interruption")

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
                                   public_candidate_drift=False, coordinator_case=None, multi_route=False, legacy_next=False,
                                   accounting_evidence=False):
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
            if multi_route:
                caps[1]["requirement_ids"].append("FR-a")
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
            if accounting_evidence:
                evidence_ref = 'docs/testing/accounting-proof.json'
                evidence_records = [{'evidence_id': rid + '-' + fid, 'requirement_ids': [rid], 'status': 'passed',
                    'covered_behavior': 'Observed ' + fid, 'flow_ids': [fid], 'test_ids': []}
                    for rid, fid in (('FR-a', 'flow-a'), ('FR-a', 'flow-b'), ('FR-b', 'flow-b'))]
                atomic_json(root / evidence_ref, {'records': evidence_records})
                refs.append(evidence_ref)
            snapshot = plan_mvg.load_json(root / chapter5.DEFAULT_EXTRACTION_SNAPSHOT)
            by_block = {block: row["requirement_id"] for row in reqs for block in row["source_block_ids"]}
            by_task = {str(row["taskmaster_id"]): row["semantic_refs"] for row in views}
            fixture._write_readiness(root, snapshot, real_semantics, by_block, by_task)
            state = plan_mvg.prepare(root, run_id="fixture", capabilities_path=capabilities_path,
                manifest_path=manifest_path, task_ids=list(map(str, fixture.TASK_IDS)), allow_unready=False, evidence_refs=refs)
            if coordinator_case == "legacy-prefix":
                index = plan_mvg.load_json(run / "analysis-input/analysis-index.json")
                for key in ("checkpoint_strategy", "checkpoint_schema_version", "analysis_identity_sha256"):
                    index.pop(key, None)
                index["analysis_identity_sha256"] = canonical_sha(index)
                atomic_json(run / "analysis-input/analysis-index.json", index)
                state = plan_mvg.load_json(run / "run.json")
                for key in ("checkpoint_strategy", "checkpoint_schema_version"):
                    state.pop(key, None)
                state["analysis_identity_sha256"] = index["analysis_identity_sha256"]
                atomic_json(run / "run.json", state)
            import shutil
            shutil.copytree(run / "analysis-input", prepared)
            description = {"schema_version": RUNNER_SCHEMA, "filesystem_scope": "workspace_only",
                           "fresh_session_per_invocation": True, "can_read_outside_workspace": False,
                           "model": "fixture", "model_tools": []}
            if public_candidate_drift:
                changed = {}
                for label in plan_mvg.MVG_CANDIDATE_LABELS:
                    candidate_input = run / "candidates" / label / "scope-1/analysis-input"
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
                    candidate_root = run / "candidates" / label / "scope-1"
                    self.assertEqual(changed[label], (candidate_root / "analysis-input/capabilities.v1.json").read_bytes())
                # Sequential preflight stops at the first corrupt workspace.
                freshness = plan_mvg.load_json(run / "candidates" /
                    plan_mvg.MVG_CANDIDATE_LABELS[0] / "scope-1/input-freshness.json")
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
                        self.assertEqual(["A", "B", "C"], labels)
                        self.assertFalse((workspace / "D.json").exists())
                        alias = "A"
                        if coordinator_case == "mixed":
                            identity = json.loads(prompt.split("\n", 1)[1])["identity"]
                            target = "candidate-1" if identity["order_index"] == 0 else "candidate-2"
                            alias = next(label for label in labels if f"scope-{identity['order_index'] + 1}:{target}" in
                                         plan_mvg.load_json(workspace / f"{label}.json")["notes"])
                        ordered = [alias] + [label for label in labels if label != alias]
                        value.update(status="selected", selected=alias, tradeoffs=["Prefer clear journeys"], evidence_refs=[],
                                     rationale="All candidates are admitted", candidate_reviews=[
                                         {"label": label, "verdict": "viable", "rank": rank,
                                          "rationale": "Valid complete proposal"} for rank, label in enumerate(ordered, 1)])
                    elif value["schema_version"] == generation.APPEND_SCHEMA:
                        cid = value["capability_id"]
                        index = next(i for i, cap in enumerate(caps) if cap["capability_id"] == cid)
                        if coordinator_case == "mixed" and "scope-" in workspace.as_posix():
                            label = next(part for part in workspace.parts if part in plan_mvg.MVG_CANDIDATE_LABELS)
                            marker = f"scope-{index + 1}:{label}"
                        else:
                            marker = None
                        task_id = fixture.TASK_IDS[index]
                        value.update(flows=[], tests=[], change_reviews=[], gaps=[], notes=[],
                            requirement_route_memberships=[{"requirement_id": reqs[index]["requirement_id"],
                                "flow_id": flows[index]["id"], "observable_role": "Concrete journey"}],
                            coverage_table=[{"requirement_id": reqs[index]["requirement_id"], "flow_id": flows[index]["id"],
                                "capability_ref": cid, "task_id": task_id, "disposition": "flow", "rationale": "Concrete journey",
                                "sink_id": None, "verification_ref": None, "authority_ref": None, "authority_review": None}],
                            entrypoints=[{"status": "planned", "flow_ids": [flows[index]["id"]], "owner_task": task_id,
                                "path": "Game.Core/Runtime.cs", "symbol": "Execute", "inputs": "Request", "state": "Ready",
                                "assertions": "Consumer state observed", "implementation_acceptance": "Test failure recovery"}])
                        if marker is not None:
                            value["notes"] = [marker]
                        if multi_route and cid == "CAP-b":
                            value["flows"] = [deepcopy(flows[index])]
                            value["flows"][0]["requirement_ids"].append("FR-a")
                            for handoff in value["flows"][0]["handoffs"]:
                                handoff.update(contract_refs=None, **{"from": None, "to": None})
                            value["requirement_route_memberships"].append({"requirement_id": "FR-a",
                                "flow_id": "flow-b", "observable_role": "Recover accepted state in the later journey"})
                            value["change_reviews"] = [{"id": "flow-b", "reason": "Shared source-backed route",
                                "authority_ref": fixture.GDD_PATH.as_posix(),
                                "authority_review": {"status": "reviewed", "rationale": "Same requirement in later journey"}}]
                        if props["coverage_table"].get("maxItems") == 0:
                            value["coverage_table"] = []
                            value["flows"] = []
                            value["change_reviews"] = []
                        if legacy_next and cid == 'CAP-a' and 'next-run' in workspace.parts:
                            value['requirement_route_memberships'].append({'requirement_id': 'FR-a',
                                'flow_id': 'flow-b', 'observable_role': 'Recover accepted state in the later journey'})
                        if fault == "duplicate_coverage":
                            value["coverage_table"].append(dict(value["coverage_table"][0],
                                requirement_id="FR-b", flow_id="flow-b", task_id=fixture.TASK_IDS[1]))
                            value["requirement_route_memberships"].append({"requirement_id": "FR-b",
                                "flow_id": "flow-b", "observable_role": "Concrete later journey"})
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
                        if 'requirement_verification' in props:
                            value['requirement_verification'] = [{**deepcopy(row), 'evidence_ids': []}
                                                                 for row in value['coverage_table']]
                            value['requirement_evidence'] = []
                            if accounting_evidence and value['coverage_table']:
                                pairs = [(reqs[index]['requirement_id'], flows[index]['id'])]
                                if cid == 'CAP-b':
                                    pairs.append(('FR-a', 'flow-b'))
                                value['requirement_evidence'] = [{'requirement_id': rid, 'evidence_id': rid + '-' + fid,
                                    'kind': 'verification_record', 'source_ref': evidence_ref + '#' + rid + '-' + fid,
                                    'covered_behavior': 'Observed ' + fid, 'flow_ids': [fid], 'test_ids': []}
                                    for rid, fid in pairs]
                                for row in value['requirement_verification']:
                                    row['evidence_ids'] = [item['evidence_id'] for item in value['requirement_evidence']
                                                           if item['requirement_id'] == row['requirement_id']]
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
            self.assertEqual("admitted", result["status"], {"errors": result.get("errors"),
                "issues": result.get("issue_events", [])[:2], "execution": result.get("execution_errors", [])[:2]})
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
                if coordinator_case in {"incomplete", "worker-exception"}:
                    real_append = generation.generate_append
                    def incomplete(*args, **kwargs):
                        workspace = args[2]
                        if kwargs.get("scope_index") == 1 and "candidate-2" in workspace.parts:
                            if coordinator_case == "worker-exception":
                                raise RuntimeError("fixture_worker_failed_after_complete_source_preparation")
                            return {"status": "blocked", "total_invocations": 0,
                                    "errors": [{"code": "fixture_admission_blocked"}]}
                        return real_append(*args, **kwargs)
                    with patch.object(generation, "generate_append", side_effect=incomplete), \
                         patch("_mvg_capability_selection.generate_append", side_effect=incomplete):
                        with self.assertRaisesRegex(ValueError, "selection_blocked_insufficient_admitted_candidates"):
                            plan_mvg.generate(root, run_id="fixture", timeout_sec=1, llm_backend="codex-cli")
                    blocked = plan_mvg.load_json(run / "run.json")
                    ledger = blocked["capability_selection"]
                    self.assertEqual(1, len(ledger["selected"]))
                    self.assertEqual("CAP-b", ledger["current"]["capability_id"])
                    self.assertEqual(ledger["accepted_sha256"], ledger["current"]["base_sha256"])
                    self.assertNotIn("selection_input_candidates", blocked)
                    self.assertEqual(1, sum(schema == plan_mvg.MVG_SELECTION_SCHEMA for _, schema, _ in seen))
                    self.assertEqual("selection_blocked_insufficient_admitted_candidates",
                                     plan_mvg.load_json(run / "model-execution.json")["selection_error"])
                    self.assertEqual(3, plan_mvg.load_json(run / "model-execution.json")["candidate_count"])
                    self.assertIn("candidate-2", plan_mvg.load_json(run / "model-execution.json")["candidate_failures"])
                    calls = len(seen)
                    if coordinator_case == "worker-exception":
                        failed = ledger["current"]["admissions"]["candidate-2"]
                        self.assertEqual("execution-failed", failed["status"])
                        self.assertTrue(failed["retryable"])
                        resumed = plan_mvg.generate(root, run_id="fixture", timeout_sec=1, llm_backend="codex-cli")
                        self.assertEqual("winner-chain", resumed["selected"])
                        self.assertEqual(calls + 3, len(seen))
                        return
                    with self.assertRaisesRegex(ValueError, "selection_blocked_insufficient_admitted_candidates"):
                        plan_mvg.generate(root, run_id="fixture", timeout_sec=1, llm_backend="codex-cli")
                    self.assertEqual(calls, len(seen))
                    from _project_health_planning import _mvg_valid_candidates
                    self.assertEqual(["candidate-1", "candidate-3"], _mvg_valid_candidates(run, blocked))
                    return
                if coordinator_case in {"selector-preparation", "run-budget"}:
                    if coordinator_case == "run-budget":
                        updated = plan_mvg.load_json(run / "run.json")
                        updated["mvg.run_invocation_limit"] = 8
                        atomic_json(run / "run.json", updated)
                        failure_pattern = "selection_blocked_insufficient_admitted_candidates"
                        guard = patch.object(generation, "preflight_runner_payload", wraps=generation.preflight_runner_payload)
                    else:
                        real_preflight = generation.preflight_runner_payload
                        def fail_selector(*args, **kwargs):
                            if args[4] == "selection.json":
                                raise ValueError("runner_input_too_large:fixture_selector_bound")
                            return real_preflight(*args, **kwargs)
                        guard = patch.object(generation, "preflight_runner_payload", side_effect=fail_selector)
                        failure_pattern = "runner_input_too_large"
                    with guard, self.assertRaisesRegex(ValueError, failure_pattern):
                        plan_mvg.generate(root, run_id="fixture", timeout_sec=1, llm_backend="codex-cli")
                    failed = plan_mvg.load_json(run / "run.json")
                    selection_ledger = failed["capability_selection"]
                    self.assertTrue(selection_ledger["terminal"])
                    if coordinator_case == "selector-preparation":
                        self.assertEqual([], selection_ledger["current"]["selection_attempts"])
                        self.assertIn("runner_input_too_large", selection_ledger["current"]["preparation_error"]["detail"])
                        self.assertEqual(6, selection_ledger["total_invocations"])
                    else:
                        self.assertEqual(8, selection_ledger["total_invocations"])
                        self.assertEqual(1, len(selection_ledger["selected"]))
                    calls = len(seen)
                    with self.assertRaises(ValueError):
                        plan_mvg.generate(root, run_id="fixture", timeout_sec=1, llm_backend="codex-cli")
                    self.assertEqual(calls, len(seen))
                    from _mvg_capability_selection import recovery_available
                    self.assertFalse(recovery_available(root, run, failed))
                    return
                if coordinator_case == "reserved-interruption":
                    import _mvg_capability_selection as selection_module
                    writer = selection_module.atomic_json
                    def interrupt_reservation(path, payload):
                        writer(path, payload)
                        if path == run / "run.json" and payload.get("capability_selection", {}).get("total_invocations") == 8:
                            raise SystemExit("fixture_crash_after_host_reservation_before_worker_charge")
                    with patch.object(selection_module, "atomic_json", side_effect=interrupt_reservation), \
                         self.assertRaisesRegex(SystemExit, "fixture_crash_after_host_reservation"):
                        plan_mvg.generate(root, run_id="fixture", timeout_sec=1, llm_backend="codex-cli")
                    interrupted = plan_mvg.load_json(run / "run.json")
                    self.assertEqual(1, len(interrupted["capability_selection"]["selected"]))
                    self.assertEqual(8, interrupted["capability_selection"]["total_invocations"])
                    self.assertEqual(2, plan_mvg.load_json(run / "candidates/candidate-1/lineage-execution.json")["model_invocation_count"])
                    self.assertEqual(0, plan_mvg.load_json(run / "candidates/candidate-1/scope-2/capability-append/append-ledger.json")["total_invocations"])
                if coordinator_case == "checkpoint-reread-unknown":
                    import _mvg_capability_selection as coordinator
                    import _mvg_capability_checkpoint as checkpoint
                    writer, reader = coordinator.atomic_json, checkpoint.load_json
                    replaced, recovery_reads, later_run_writes = [], [], []
                    def uncertain_commit(path, payload):
                        ledger = payload.get("capability_selection", {})
                        if path == run / "run.json" and replaced:
                            later_run_writes.append(deepcopy(payload))
                        writer(path, payload)
                        if (path == run / "run.json" and len(ledger.get("selected", [])) == 2
                                and ledger.get("current") is None and not replaced):
                            replaced.append(True)
                            raise OSError("fixture_post_replace_error")
                    def uncertain_reader(path, default=None):
                        if path == run / "run.json" and replaced and not recovery_reads:
                            recovery_reads.append(True)
                            raise OSError("fixture_post_replace_reread_error")
                        return reader(path, default)
                    failure = None
                    with patch.object(coordinator, "atomic_json", side_effect=uncertain_commit), \
                         patch.object(checkpoint, "load_json", side_effect=uncertain_reader):
                        try:
                            plan_mvg.generate(root, run_id="fixture", timeout_sec=1, llm_backend="codex-cli")
                        except (OSError, RuntimeError) as exc:
                            failure = exc
                    interrupted = plan_mvg.load_json(run / "run.json")
                    self.assertEqual(2, len(interrupted["capability_selection"]["selected"]),
                                     "Unknown commit outcome must never roll back the on-disk commit")
                    self.assertEqual([], later_run_writes)
                    self.assertIsNotNone(failure)
                    self.assertIn("checkpoint_commit_outcome_unknown", str(failure))
                    sidecar = plan_mvg.load_json(run / "checkpoint-commit-outcome.json")
                    self.assertEqual("unknown", sidecar["status"])
                    self.assertEqual(14, len(seen))
                if coordinator_case in {"checkpoint-predecessor-drift", "checkpoint-predecessor-proof-drift", "checkpoint-public-stale",
                                         "checkpoint-public-receipt"}:
                    import _mvg_capability_checkpoint as checkpoint
                    preparer = checkpoint.prepare_checkpoint
                    def drift_after_staging(run_dir, current_state, capability_id, index, seed, accepted, step):
                        if index == 1 and coordinator_case == "checkpoint-public-stale":
                            stale = deepcopy(step)
                            stale["input_identity"]["base_sha256"] = "sha256:stale"
                            return preparer(run_dir, current_state, capability_id, index, seed, accepted, stale)
                        pointer = preparer(run_dir, current_state, capability_id, index, seed, accepted, step)
                        if index == 1:
                            if coordinator_case in {"checkpoint-predecessor-drift", "checkpoint-predecessor-proof-drift"}:
                                old_ledger = current_state["capability_selection"]
                                if coordinator_case == "checkpoint-predecessor-proof-drift":
                                    old_step = old_ledger["selected"][0]
                                    path = run / old_step["admissions"][old_step["selected_candidate"]]["proof_path"]
                                else:
                                    path = run / old_ledger["checkpoint_head"]["path"]
                                changed = plan_mvg.load_json(path)
                                changed["fixture_predecessor_drift"] = True
                                atomic_json(path, changed)
                            else:
                                atomic_json(run / step["receipt_path"], {"fixture_receipt_drift": True})
                        return pointer
                    with patch.object(checkpoint, "prepare_checkpoint", side_effect=drift_after_staging):
                        failure = None
                        try:
                            plan_mvg.generate(root, run_id="fixture", timeout_sec=1, llm_backend="codex-cli")
                        except ValueError as exc:
                            failure = exc
                    blocked = plan_mvg.load_json(run / "run.json")
                    ledger = blocked["capability_selection"]
                    self.assertEqual(1, len(ledger["selected"]), "Drift must not advance the committed prefix")
                    self.assertIsNotNone(failure)
                    self.assertEqual("blocked", blocked["selection_status"])
                    self.assertTrue(blocked["selection_block_reason"])
                    self.assertEqual("failed", ledger["current"]["checkpoint_preparation"]["status"])
                    expected_reason = ("checkpoint_stale_base" if coordinator_case == "checkpoint-public-stale"
                        else "checkpoint_payload_changed" if coordinator_case == "checkpoint-predecessor-drift"
                        else "capability_selection_artifact_identity_changed")
                    self.assertIn(expected_reason, blocked["selection_block_reason"])
                    self.assertEqual(blocked["selection_block_reason"],
                                     ledger["current"]["checkpoint_preparation"]["reason"])
                    self.assertEqual(ledger["selected"][0]["proposal_sha256"], ledger["accepted_sha256"])
                    self.assertEqual(ledger["selected"][0]["checkpoint"], ledger["checkpoint_head"])
                    self.assertEqual(14, len(seen))
                    return
                if coordinator_case in {"checkpoint-interruption", "checkpoint-after-error",
                                         "checkpoint-before-exit", "checkpoint-after-exit"}:
                    import _mvg_capability_selection as coordinator
                    writer = coordinator.atomic_json
                    failed = []
                    def interrupt_commit(path, payload):
                        ledger = payload.get("capability_selection", {})
                        if (path == run / "run.json" and len(ledger.get("selected", [])) == 2
                                and ledger.get("current") is None and not failed):
                            failed.append(True)
                            if coordinator_case.startswith("checkpoint-after"):
                                writer(path, payload)
                            if coordinator_case.endswith("exit"):
                                raise SystemExit("fixture_checkpoint_pointer_failure")
                            raise OSError("fixture_checkpoint_pointer_failure")
                        writer(path, payload)
                    with patch.object(coordinator, "atomic_json", side_effect=interrupt_commit), \
                         self.assertRaisesRegex(SystemExit if coordinator_case.endswith("exit") else OSError,
                                                "fixture_checkpoint_pointer_failure"):
                        plan_mvg.generate(root, run_id="fixture", timeout_sec=1, llm_backend="codex-cli")
                    interrupted = plan_mvg.load_json(run / "run.json")
                    ledger = interrupted["capability_selection"]
                    after = coordinator_case.startswith("checkpoint-after")
                    self.assertEqual(2 if after else 1, len(ledger["selected"]))
                    self.assertEqual(ledger["selected"][-1]["checkpoint"], ledger["checkpoint_head"])
                    if not after:
                        self.assertEqual(ledger["current"]["base_sha256"], ledger["accepted_sha256"])
                        self.assertEqual("prepared" if coordinator_case.endswith("exit") else "failed",
                                         ledger["current"]["checkpoint_preparation"]["status"])
                    else:
                        self.assertIsNone(ledger["current"])
                    self.assertEqual(2, len(list((run / "capability-checkpoints").glob("*/payload.json"))))
                    self.assertEqual(14, len(seen))
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
                persisted = plan_mvg.load_json(run / "run.json")
                if coordinator_case == "checkpoint-reread-unknown":
                    recovered_outcome = plan_mvg.load_json(run / "checkpoint-commit-outcome.json")
                    self.assertEqual("resolved", recovered_outcome["status"])
                    self.assertEqual("committed", recovered_outcome["outcome"])
                    self.assertEqual(14, len(seen), "Outcome recovery must verify locally before any state write")
                if coordinator_case in {"checkpoint-interruption", "checkpoint-after-error",
                                         "checkpoint-before-exit", "checkpoint-after-exit"}:
                    self.assertEqual(14, len(seen), "Prepared checkpoint recovery must not dispatch a model")
                if coordinator_case == "checkpoint-tamper":
                    from _project_health_planning import _mvg_valid_candidates
                    pointer = persisted["capability_selection"]["selected"][0]["checkpoint"]
                    path = run / pointer["path"]
                    original_payload = plan_mvg.load_json(path)
                    for mutation in ("schema", "tuple", "accepted", "delta", "pointer-missing", "head"):
                        changed_state = deepcopy(persisted)
                        changed = deepcopy(original_payload)
                        if mutation == "schema":
                            changed["schema_version"] = "unknown"
                        elif mutation == "tuple":
                            changed["identity"]["capability_id"] = "CAP-other"
                        elif mutation == "accepted":
                            changed["accepted"]["notes"].append("tampered")
                            changed_state["capability_selection"]["selected"][0]["checkpoint"]["payload_sha256"] = canonical_sha(changed)
                        elif mutation == "delta":
                            changed["delta"]["notes"].append("tampered")
                            changed_state["capability_selection"]["selected"][0]["checkpoint"]["payload_sha256"] = canonical_sha(changed)
                        elif mutation == "pointer-missing":
                            changed_state["capability_selection"]["selected"][0].pop("checkpoint")
                        else:
                            changed_state["capability_selection"]["checkpoint_head"] = pointer
                        atomic_json(path, changed)
                        atomic_json(run / "run.json", changed_state)
                        self.assertEqual([], _mvg_valid_candidates(run, changed_state), mutation)
                        with self.assertRaises(ValueError, msg=mutation):
                            plan_mvg.generate(root, run_id="fixture", timeout_sec=1, llm_backend="codex-cli")
                        for operation in (lambda: plan_mvg.review(root, run_id="fixture", runner=Path("unused"), timeout_sec=1),
                                          lambda: plan_mvg.validate(root, run_id="fixture"),
                                          lambda: plan_mvg.apply(root, run_id="fixture", confirm=True)):
                            atomic_json(run / "run.json", changed_state)
                            with self.assertRaises(ValueError, msg=mutation):
                                operation()
                        self.assertEqual(calls_before_review, len(seen))
                        atomic_json(path, original_payload)
                    atomic_json(run / "run.json", persisted)
                if coordinator_case == "checkpoint":
                    ledger = persisted["capability_selection"]
                    self.assertIn("checkpoint_head", ledger)
                    predecessor = None
                    for index, step in enumerate(ledger["selected"]):
                        pointer = step["checkpoint"]
                        payload = plan_mvg.load_json(run / pointer["path"])
                        expected_identity = {"schema_version": "newrouge.mvg-capability-checkpoint.v1",
                            "run_id": "fixture", "capability_id": ("CAP-a", "CAP-b")[index],
                            "order_index": index, "base_sha256": canonical_sha(payload["accepted_seed"]),
                            "proposal_sha256": step["proposal_sha256"],
                            "selection_receipt_sha256": file_sha(run / step["receipt_path"])}
                        self.assertEqual(expected_identity, payload["identity"])
                        self.assertEqual(canonical_sha(expected_identity), pointer["transaction_id"])
                        self.assertEqual(pointer["transaction_id"], canonical_sha(payload["identity"]))
                        self.assertEqual(pointer["payload_sha256"], canonical_sha(payload))
                        self.assertEqual(step["receipt_sha256"], payload["identity"]["selection_receipt_sha256"])
                        self.assertEqual(index, payload["identity"]["order_index"])
                        self.assertEqual(predecessor, payload["predecessor"])
                        self.assertEqual(step["record"]["delta"], payload["delta"])
                        self.assertEqual(step["proposal_sha256"], canonical_sha(payload["accepted"]))
                        self.assertEqual(step["input_identity"]["base_sha256"], canonical_sha(payload["accepted_seed"]))
                        predecessor = pointer
                    self.assertEqual(predecessor, ledger["checkpoint_head"])
                if coordinator_case == "reserved-interruption":
                    self.assertEqual(15, persisted["capability_selection"]["total_invocations"])
                    self.assertEqual(5, persisted["capability_selection"]["lineage_invocations"]["candidate-1"])
                    local = plan_mvg.load_json(run / "candidates/candidate-1/scope-2/capability-append/append-ledger.json")
                    self.assertEqual(3, local["total_invocations"])
                    self.assertEqual(1, len(local["interrupted_reservations"]))
                    self.assertEqual(1, local["interrupted_reservations"][0]["through"])
                    self.assertEqual(14, calls_before_review)
                    return
                if coordinator_case == "mixed":
                    self.assertEqual(["candidate-1", "candidate-2"],
                        [step["selected_candidate"] for step in persisted["capability_selection"]["selected"]])
                    payloads = [json.loads(prompt.split("\n", 1)[1]) for _, schema, prompt in seen
                                if schema == generation.APPEND_SCHEMA]
                    seeds = [row["accepted_proposal"] for row in payloads if row["scope"]["capability_id"] == "CAP-b"]
                    self.assertEqual(3, len(seeds))
                    self.assertTrue(all(seed == seeds[0] for seed in seeds))
                    self.assertIn("scope-1:candidate-1", seeds[0]["notes"])
                    self.assertNotIn("scope-1:candidate-2", seeds[0]["notes"])
                    self.assertEqual(14, persisted["capability_selection"]["total_invocations"])
                    self.assertEqual({label: 4 for label in plan_mvg.MVG_CANDIDATE_LABELS},
                                     persisted["capability_selection"]["lineage_invocations"])
                if coordinator_case == "tamper":
                    from _project_health_planning import _mvg_valid_candidates
                    original = deepcopy(persisted)
                    for mutation in ("prefix", "scope", "receipt", "candidate-clone", "candidate-lineage", "execution-total"):
                        changed = deepcopy(original)
                        if mutation == "prefix":
                            changed["capability_selection"]["selected"][0]["record"]["base_sha256"] = "sha256:tampered"
                        elif mutation == "scope":
                            changed["capability_selection"]["order"].reverse()
                        elif mutation == "receipt":
                            changed["capability_selection"]["selected"][0]["receipt_sha256"] = "sha256:tampered"
                        elif mutation == "candidate-clone":
                            step = changed["capability_selection"]["selected"][0]
                            step["admissions"]["candidate-2"] = deepcopy(step["admissions"]["candidate-1"])
                        elif mutation == "candidate-lineage":
                            changed["capability_selection"]["selected"][0]["admissions"]["candidate-1"]["lineage"] = "candidate-2-r1"
                        else:
                            changed["capability_selection"]["selected"][0]["admissions"]["candidate-1"]["total_invocations"] += 1
                        atomic_json(run / "run.json", changed)
                        self.assertEqual([], _mvg_valid_candidates(run, changed))
                        with self.assertRaises(ValueError):
                            plan_mvg.generate(root, run_id="fixture", timeout_sec=1, llm_backend="codex-cli")
                        self.assertEqual(calls_before_review, len(seen))
                        for operation in (lambda: plan_mvg.review(root, run_id="fixture", runner=Path("unused"), timeout_sec=1),
                                          lambda: plan_mvg.validate(root, run_id="fixture"),
                                          lambda: plan_mvg.apply(root, run_id="fixture", confirm=True)):
                            atomic_json(run / "run.json", changed)
                            with self.assertRaises(ValueError):
                                operation()
                    atomic_json(run / "run.json", original)
                    execution_path = root / original["selected_admission_review"]["execution_path"]
                    original_execution = plan_mvg.load_json(execution_path)
                    corrupted_execution = deepcopy(original_execution)
                    corrupted_execution["total_invocations"] += 1
                    first_lineage = next(iter(corrupted_execution["lineage_invocations"]))
                    corrupted_execution["lineage_invocations"][first_lineage] += 1
                    atomic_json(execution_path, corrupted_execution)
                    changed = deepcopy(original)
                    changed["selected_admission_review"]["execution_sha256"] = file_sha(execution_path)
                    atomic_json(run / "run.json", changed)
                    self.assertEqual([], _mvg_valid_candidates(run, changed),
                        "Completed Knowledge recovery must reject aggregate costs that disagree with selected scopes")
                    with self.assertRaises(ValueError):
                        plan_mvg.generate(root, run_id="fixture", timeout_sec=1, llm_backend="codex-cli")
                    self.assertEqual(calls_before_review, len(seen))
                    atomic_json(execution_path, original_execution)
                    atomic_json(run / "run.json", original)
                if coordinator_case in {"receipt-recovery", "legacy-prefix"}:
                    interrupted = deepcopy(persisted)
                    selection_ledger = interrupted["capability_selection"]
                    step = selection_ledger["selected"].pop()
                    step["status"] = "running"
                    if coordinator_case == "receipt-recovery" and selection_ledger.get("selected"):
                        selection_ledger["checkpoint_head"] = selection_ledger["selected"][-1].get("checkpoint")
                    if coordinator_case == "legacy-prefix":
                        self.assertNotIn("checkpoint_head", selection_ledger)
                        self.assertTrue(all("checkpoint" not in row for row in selection_ledger["selected"]))
                    selection_ledger.update(accepted_sha256=step["input_identity"]["base_sha256"], current={
                        "capability_id": "CAP-b", "order_index": 1,
                        "base_sha256": step["input_identity"]["base_sha256"], "admissions": step["admissions"],
                        "aliases": step["aliases"], "input_identity": step["input_identity"],
                        "input_sha256": step["input_sha256"], "selection_attempts": [step]})
                    interrupted.update(selection_status="pending", phase="generating-capability")
                    atomic_json(run / "run.json", interrupted)
                    resumed = plan_mvg.generate(root, run_id="fixture", timeout_sec=1, llm_backend="codex-cli")
                    self.assertEqual("winner-chain", resumed["selected"])
                    self.assertEqual(calls_before_review, len(seen))
                    self.assertEqual(2, len(plan_mvg.load_json(run / "run.json")["capability_selection"]["selected"]))
                    if coordinator_case == "legacy-prefix":
                        recovered = plan_mvg.load_json(run / "run.json")
                        self.assertNotIn("checkpoint_strategy", recovered)
                        self.assertNotIn("checkpoint_head", recovered["capability_selection"])
                        self.assertFalse((run / "capability-checkpoints").exists())
                if coordinator_case == "apply-replay":
                    applied = plan_mvg.apply(root, run_id="fixture", confirm=True)
                    replayed = plan_mvg.apply(root, run_id="fixture", confirm=True)
                    self.assertEqual(applied, replayed)
                    self.assertEqual("applied", replayed["status"])
                    self.assertEqual(calls_before_review, len(seen))
                    if multi_route:
                        proposal = plan_mvg.load_json(run / "proposal.json")
                        trace = plan_mvg.load_json(root / applied["trace_path"])
                        routes = proposal["requirement_route_memberships"]
                        self.assertEqual(3, len(routes))
                        self.assertEqual(2, len(proposal["coverage_table"]))
                        self.assertEqual(routes, trace["requirement_route_memberships"])
                        self.assertEqual("flow-a", proposal["coverage_table"][0]["flow_id"])
                        pointer = persisted["capability_selection"]["checkpoint_head"]
                        payload = plan_mvg.load_json(run / pointer["path"])
                        self.assertEqual(routes, payload["accepted"]["requirement_route_memberships"])
                        from _project_health_planning import build_result
                        def local_result():
                            return build_result(root, {"manifest": applied["manifest_path"], "revision": "fixture",
                                "job_id": "fixture"})
                        with patch('_project_health_tasks.task_details', return_value=[]), \
                             patch('_semantic_topology.build_topology_view', return_value={}), \
                             patch('_project_health_mvg_versions.build_overview', side_effect=lambda *args: {"manifests": [{
                                "path": applied["manifest_path"], "sha256": applied["manifest_sha256"]}]}):
                            result = local_result()
                            for mutation in ('proposal_role', 'run_applied', 'run_hash', 'trace_path', 'trace_hash'):
                                with self.subTest(local_binding=mutation):
                                    target = (run / 'proposal.json' if mutation == 'proposal_role' else
                                        run / 'run.json' if mutation.startswith('run_') else
                                        run / 'apply-summary.json' if mutation == 'trace_path' else root / applied['trace_path'])
                                    original_payload = plan_mvg.load_json(target)
                                    changed_payload = deepcopy(original_payload)
                                    if mutation == 'proposal_role':
                                        changed_payload['requirement_route_memberships'][0]['observable_role'] = 'Tampered role'
                                    elif mutation == 'run_applied':
                                        changed_payload['applied'] = False
                                    elif mutation == 'run_hash':
                                        changed_payload['applied_manifest_sha256'] = 'sha256:tampered'
                                    elif mutation == 'trace_path':
                                        changed_payload['trace_path'] = '../../outside.json'
                                    else:
                                        changed_payload['applied_manifest_sha256'] = 'sha256:tampered'
                                    atomic_json(target, changed_payload)
                                    try:
                                        projected = local_result()['overview']['manifests'][0]
                                        self.assertNotIn('requirement_routes_source', projected)
                                        self.assertNotIn('requirement_route_memberships', projected)
                                    finally:
                                        atomic_json(target, original_payload)
                        self.assertEqual(routes, result["overview"]["manifests"][0]["requirement_route_memberships"])
                        if accounting_evidence:
                            accounting = result['overview']['manifests'][0]['requirement_accounting']
                            self.assertEqual(2, accounting['satisfied_count'])
                            self.assertEqual(3, accounting['evidence_count'])
                        from _mvg_capability_generation import seed_proposal
                        if legacy_next:
                            # Historical traces know only the original coverage owners.
                            trace.pop('requirement_route_memberships')
                            atomic_json(root / applied['trace_path'], trace)
                        next_state = plan_mvg.prepare(root, run_id="next-run", capabilities_path=capabilities_path,
                            manifest_path=manifest_path, task_ids=list(map(str, fixture.TASK_IDS)),
                            allow_unready=False, evidence_refs=refs)
                        next_prepared = root / plan_mvg.DEFAULT_RUN_ROOT / "next-run/analysis-input"
                        next_seed = seed_proposal(next_state, next_prepared)
                        self.assertEqual(proposal['requirement_verification'], next_seed['requirement_verification'])
                        self.assertEqual(proposal['requirement_evidence'], next_seed['requirement_evidence'])
                        if not legacy_next:
                            self.assertEqual(routes, next_seed['requirement_route_memberships'])
                        else:
                            self.assertEqual([row for row in routes if
                                (row['requirement_id'], row['flow_id']) != ('FR-a', 'flow-b')],
                                next_seed['requirement_route_memberships'])
                            self.assertEqual('legacy_owner_only', next_seed['requirement_routes_projection'])
                        self.assertEqual(proposal["coverage_table"], next_seed["coverage_table"])
                        try:
                            next_result = plan_mvg.generate(root, run_id="next-run", timeout_sec=1, llm_backend="codex-cli")
                        except ValueError as exc:
                            errors = [{"path": str(path), "errors": plan_mvg.load_json(path).get('errors'),
                                "issues": plan_mvg.load_json(path).get('issue_events', [])[:1]}
                                for path in next_prepared.parent.rglob('append-ledger.json')]
                            self.fail(str(exc) + str(errors)[:3000])
                        self.assertEqual("winner-chain", next_result["selected"])
                        next_proposal = plan_mvg.load_json(next_prepared.parent / "proposal.json")
                        self.assertEqual(routes, next_proposal["requirement_route_memberships"])
                        self.assertNotIn('requirement_routes_projection', next_proposal)
                        self.assertEqual(proposal["coverage_table"], next_proposal["coverage_table"])
                    return
                for label in plan_mvg.MVG_CANDIDATE_LABELS:
                    for index, capability_id in enumerate(("CAP-a", "CAP-b"), 1):
                        ledger = plan_mvg.load_json(run / "candidates" / label /
                            f"scope-{index}/capability-append/append-ledger.json", {})
                        self.assertEqual([capability_id], ledger["completed"])
                        self.assertEqual(2, ledger["total_invocations"])
                from _project_health_planning import _mvg_valid_candidates
                persisted = plan_mvg.load_json(run / "run.json", {})
                self.assertEqual(list(plan_mvg.MVG_CANDIDATE_LABELS), _mvg_valid_candidates(run, persisted),
                                 "HTTP recovery must recognize append admission proofs")


if __name__ == "__main__":
    unittest.main()
