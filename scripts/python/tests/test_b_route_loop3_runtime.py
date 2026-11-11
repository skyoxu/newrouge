"""Loop-three runtime seams; synthetic controls never grant model qualification."""
from copy import deepcopy
from contextlib import ExitStack
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import _b_route_planning_runtime as runtime
import _b_route_issue_accounts as accounts
import _mvg_capability_append as append
import _mvg_capability_selection as selection
import test_b_route_planning_runtime as fixtures


class IssueAccountRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.RuntimeTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.frozen, self.value = self.fixture.root, self.fixture.frozen, self.fixture.value
        self.run, self.state = self.fixture.create(complete_wire=True)

    def blocked(self, value=None, target=None, rationale="Source-backed missing behavior"):
        value = self.value if value is None else value
        review = self.fixture.review(self.state, value)
        required = runtime.obligations(value, self.frozen)
        obligation = next(row for row in required if row["target"] == target) if target else required[0]
        row = next(row for row in review["checks"] if row["id"] == obligation["id"])
        row.update(verdict="blocked", rationale=rationale)
        review.update(verdict="blocked", findings=[rationale])
        return review

    def test_policy_is_bound_to_frozen_runtime_rules_and_cannot_be_deleted(self):
        self.assertEqual(runtime.issue_account_policy(self.state), accounts.POLICY)
        for policy in (None, "unknown"):
            changed = deepcopy(self.state)
            changed["b_route_issue_account_policy"] = policy
            with self.assertRaisesRegex(ValueError, "issue_account_policy_changed"):
                runtime.issue_account_policy(changed)

    def test_historical_manifest_keeps_original_issue_identity(self):
        historical = deepcopy(self.state)
        historical.pop("b_route_issue_account_policy")
        historical["planning_runtime"]["rules"]["runtime"].pop("_b_route_issue_accounts.py")
        historical["runtime_identity"] = runtime.canonical_sha(historical["planning_runtime"])
        review = self.blocked()
        review["runtime_identity"] = historical["runtime_identity"]
        self.assertEqual(runtime.account_review_issues(historical, self.value, self.frozen, review),
                         runtime.review_issues(historical, self.value, self.frozen, review))

    def test_rationale_changes_keep_account_but_bind_distinct_complete_reviews(self):
        first = self.blocked(rationale="Missing observable boundary")
        second = self.blocked(rationale="The observable boundary remains incomplete")
        old = runtime.account_review_issues(self.state, self.value, self.frozen, first)[0]
        new = runtime.account_review_issues(self.state, self.value, self.frozen, second)[0]
        self.assertEqual(append.issue_key(old), append.issue_key(new))
        self.assertNotEqual(old["review_sha256"], new["review_sha256"])
        self.assertNotEqual(runtime.review_issues(self.state, self.value, self.frozen, first)[0]["code"],
                            runtime.review_issues(self.state, self.value, self.frozen, second)[0]["code"])

    def test_complete_review_denominator_and_source_support_still_gate_accounts(self):
        review = self.blocked()
        for mutate in (lambda value: value["checks"].pop(),
                       lambda value: value["checks"][0].update(source_block_ids=[])):
            changed = deepcopy(review)
            mutate(changed)
            with self.assertRaises(ValueError):
                runtime.account_review_issues(self.state, self.value, self.frozen, changed)

    def test_local_branch_partial_repair_keeps_account_and_exact_scope(self):
        target = next(row["target"] for row in runtime.obligations(self.value, self.frozen)
                      if row["target"][0] == "flow_branch")
        review = self.blocked(target=target)
        issue = runtime.account_review_issues(self.state, self.value, self.frozen, review)[0]
        self.assertTrue(runtime.repair_is_local(self.value, self.frozen, issue))
        revised = deepcopy(self.value)
        path = issue["local_owner_path"]
        branch = revised["content"]
        for part in path:
            branch = branch[part]
        branch["rationale"] += " More precise source-supported behavior."
        origin = (self.value, runtime.obligations(self.value, self.frozen),
                  runtime.semantic_domain(self.value, self.frozen)[0], issue)
        after_target = next(row["target"] for row in runtime.obligations(revised, self.frozen)
                            if row["target"][:3] == target[:3])
        after = runtime.account_review_issues(self.state, revised, self.frozen,
                                             self.blocked(revised, after_target), origin=origin)[0]
        self.assertEqual(append.issue_key(issue), append.issue_key(after))
        self.assertEqual(runtime.repair_scope_errors(self.root, self.state, self.value, revised, issue), [])
        unchanged = deepcopy(self.value)
        self.assertIn("b_route_repair_no_target_progress",
                      runtime.repair_scope_errors(self.root, self.state, self.value, unchanged, issue))

    def test_cumulative_business_owner_uses_replacement_without_edit_authority(self):
        target = next(row["target"] for row in runtime.obligations(self.value, self.frozen)
                      if row["target"][0] == "cumulative")
        issue = runtime.account_review_issues(self.state, self.value, self.frozen, self.blocked(target=target))[0]
        self.assertFalse(runtime.repair_is_local(self.value, self.frozen, issue))
        with self.assertRaisesRegex(ValueError, "repair_domain_unresolved"):
            runtime.repair_domain(self.value, self.frozen, issue)
        changed = deepcopy(issue)
        changed["local_repairable"] = True
        with self.assertRaises(ValueError):
            runtime.repair_is_local(self.value, self.frozen, changed)

    def test_machine_issue_may_make_real_partial_progress_with_original_count(self):
        fid = self.value["content"]["definitions"]["flows"][0]["id"]
        issue = {"code": "b_route_machine:fixture", "path": "candidate:" + fid + ".entry_condition",
                 "detail": {"entity_id": fid + ".entry_condition"}}
        revised = deepcopy(self.value)
        revised["content"]["definitions"]["flows"][0]["entry_condition"] += " Explicit progress."
        with patch.object(runtime, "machine", return_value=[issue]):
            self.assertEqual(runtime.repair_scope_errors(self.root, self.state, self.value, revised, issue), [])
            self.assertIn("b_route_repair_no_target_progress",
                          runtime.repair_scope_errors(self.root, self.state, self.value, self.value, issue))

    def test_selector_virtual_file_budget_precedes_legacy_factor(self):
        aliases = dict(zip(selection.alias_keys(self.state), runtime.labels(self.state)))
        proposals = {label: self.value for label in runtime.labels(self.state)}
        with patch.object(runtime.compact, "MAX_EXPANDED_BYTES", 64), \
             patch.object(runtime.wire, "lossless_context", side_effect=AssertionError("legacy factor reached")):
            with self.assertRaisesRegex(ValueError, "exceeds"):
                runtime._selector_files(self.state, self.frozen, {}, {}, proposals, aliases)

    def test_nested_schema_request_reconstruction_shares_one_resource_account(self):
        observed = []
        original = runtime.planning.build_wire_request
        def capture(*args, **kwargs):
            observed.append(kwargs.get("work"))
            return original(*args, **kwargs)
        with runtime.request_resources() as work, patch.object(runtime.planning, "build_wire_request", side_effect=capture):
            payload = runtime.request_payload(self.frozen, phase="generation", seed_value={},
                                              batch=1, delivery=runtime.wire.SCHEMA, work=work)
            runtime.generation_schema(self.frozen, payload["root_request"], delivery=runtime.wire.SCHEMA)
        self.assertGreaterEqual(len(observed), 2)
        self.assertTrue(all(value is work for value in observed))


class CleanBusinessReplacementTests(unittest.TestCase):
    def run_blocked(self, root, *, repairability, replacement):
        proposals = []
        issue = {"code": "semantic_review_account:cumulative", "path": "semantic-review"}
        def propose(scope, accepted, prior, finding, context, call):
            self.assertIsNone(prior)
            self.assertIsNone(finding)
            self.assertEqual(accepted, {"accepted": "immutable"})
            proposals.append(context)
            call("generate")
            return {"context": context}
        def semantic(scope, accepted, proposal, call, context):
            call("semantic")
            return {"issues": [issue]}
        result = append.run_capability_append(root, scopes=[{"capability_id": "scope"}],
            seed={"accepted": "immutable"}, identity="fixture", propose=propose,
            machine=lambda *_: [], semantic=semantic, final_machine=lambda *_: [],
            merge=lambda base, delta, scope: deepcopy(delta), preserve=lambda *_: [],
            repairability=repairability, replacement=replacement, invocation_limit=64,
            fail_execution_closed=True)
        return result, proposals

    def test_unrepairable_business_replacement_is_finite_clean_and_not_three_fake_repairs(self):
        events = []
        def replacement(**event):
            if len(events) == 3:
                return None
            events.append(deepcopy(event))
            return {"round": len(events), **event}
        with tempfile.TemporaryDirectory() as temporary:
            result, proposals = self.run_blocked(Path(temporary), repairability=lambda *_: False, replacement=replacement)
        self.assertEqual(result["status"], "retired")
        self.assertEqual(proposals, [1, 2, 3, 4])
        self.assertEqual(result["total_invocations"], 8)
        self.assertEqual(len(events), 3)
        self.assertTrue(all(row["repair_attempts"] == 0 for row in result["restarts"]))
        self.assertEqual(result["accepted"], {"accepted": "immutable"})
        self.assertEqual(result["current"]["issue_attempts"], {})

    def test_invalid_issue_owner_stops_without_replacement_or_another_call(self):
        events = []
        def invalid(*_):
            raise ValueError("unbound owner")
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "unbound owner"):
                self.run_blocked(Path(temporary), repairability=invalid,
                                 replacement=lambda **kwargs: events.append(kwargs))
        self.assertEqual(events, [])


class RepairOriginTraversalTests(unittest.TestCase):
    """Actual verifier traversal with explicit synthetic leaf-validator stubs.

    These controls measure graph work and rejection paths only. They do not
    establish receipt validity, native execution or Story qualification.
    """
    def graph(self, depth):
        run = Path(tempfile.gettempdir()) / "synthetic-origin-leaf-stubs"
        graph = {"run": run, "calls": [], "bindings": {}, "materials": {}, "outputs": {},
                 "issues": {}, "reserved_reads": 0, "raw_reads": []}
        candidates = []
        def add(name, data, output):
            binding = {"binding_sha256": "sha256:" + name, "output_path": str(run / (name + ".json"))}
            graph["bindings"][name] = binding
            graph["materials"][name] = data
            graph["outputs"][name] = output
            graph["calls"].append({"number": len(graph["calls"]) + 1, "candidate": "candidate-1",
                "generation": 1, "execution": 1, "outcome": {"status": "completed"},
                "request_identity": {"output_path": name + ".json", "fresh_lineage_identity": "lineage"}})
        for number in range(depth + 1):
            draft = {"stage": "synthesis", "ordinal": 1, "content": {"value": number}}
            candidate = {"content": deepcopy(draft["content"]), "provenance": {"draft_chain": [draft]}}
            prior = candidates[-1] if candidates else None
            issue = graph["issues"].get(number - 1)
            frame = {"prior_candidate": prior, "repair_issue": issue}
            generation = {"phase": "generation", "root_request": {}, "lineage_identity": "lineage",
                "lineage_context": 1, "repair_scope_policy": runtime.REPAIR_SCOPE_POLICY if issue else None, **frame}
            add("g" + str(number), generation, draft)
            graph["issues"][number] = {"path": "semantic-review", "code": "semantic_review_account:" + str(number),
                "account_policy": accounts.POLICY, "detail": "Synthetic blocked owner " + str(number)}
            candidates.append(candidate)
            if number < depth:
                add("r" + str(number), {"phase": "independent_admission", "proposal": candidate,
                    "lineage_identity": "lineage", "lineage_context": 1, **frame}, {"value": number})
        graph["state"] = {"run_id": "synthetic", "capability_selection": {"calls": graph["calls"]}}
        graph["top"] = "g" + str(depth)
        return graph

    def leaves(self, graph, stack):
        def name(binding):
            return Path(binding["output_path"]).stem
        def reserved(run, row):
            graph["reserved_reads"] += 1
            return graph["bindings"][Path(row["request_identity"]["output_path"]).stem]
        def raw(binding):
            key = name(binding)
            graph["raw_reads"].append(key)
            if graph.get("tampered_raw") == key:
                raise ValueError("synthetic raw binding changed")
            return deepcopy(graph["outputs"][key])
        def origin(data, frozen):
            issue = data.get("repair_issue")
            return (data["prior_candidate"], [], [], issue) if issue is not None else None
        replacements = {
            "descriptor": lambda state: {"planner": "mvg", "limits": {"request_limit": 192}},
            "run_location": lambda *_: graph["run"],
            "wire_delivery": lambda *_: None,
            "verify_reserved_call": reserved,
            "bound_materials": lambda binding, *_: graph["materials"][name(binding)],
            "verify_call": raw,
            "decode_generation_output": lambda frozen, data, value: value,
            "request_attempt": lambda *args, **kwargs: {"payload": "{}"},
            "repair_scope_errors": lambda *args, **kwargs: [],
            "decode_review": lambda state, proposal, frozen, value, policy: value,
            "review_source_policy": lambda *_: None,
            "review_account_origin": origin,
            "account_review_issues": lambda state, proposal, frozen, review, **kwargs:
                [graph["issues"][proposal["content"]["value"]]],
        }
        for key, value in replacements.items():
            stack.enter_context(patch.object(runtime, key, side_effect=value))
        stack.enter_context(patch.object(runtime.planning, "validate_draft_chain"))

    def verify(self, graph, *, work=None):
        key = graph["top"]
        runtime.verify_repair_origin(graph["run"], graph["state"], {},
            graph["materials"][key], graph["bindings"][key], _work=work)

    def test_actual_multi_hop_verifier_has_one_entry_per_generation_edge(self):
        original = runtime.verify_repair_origin
        for depth in (1, 2, 4, 8, 24):
            with self.subTest(depth=depth), ExitStack() as stack:
                graph = self.graph(depth)
                self.leaves(graph, stack)
                observed = stack.enter_context(patch.object(runtime, "verify_repair_origin", wraps=original))
                work = runtime._RepairOriginWork(graph["state"])
                self.verify(graph, work=work)
                self.assertLessEqual(len(graph["calls"]), 64)
                self.assertEqual(observed.call_count, depth)
                self.assertEqual(work.entries, depth)
                self.assertLessEqual(work.steps, work.max_steps)
                self.assertLessEqual(graph["reserved_reads"], depth * (depth + 1))
                self.assertEqual(sorted(key for key in graph["raw_reads"] if key.startswith("r")),
                                 sorted("r" + str(number) for number in range(depth)))

    def test_separate_actions_revalidate_all_original_leaves_without_authority_cache(self):
        with ExitStack() as stack:
            graph = self.graph(4)
            self.leaves(graph, stack)
            self.verify(graph)
            reserved, raw = graph["reserved_reads"], list(graph["raw_reads"])
            self.verify(graph)
            self.assertEqual(graph["reserved_reads"], 2 * reserved)
            self.assertEqual(graph["raw_reads"], raw + raw)

    def test_rehashed_review_parent_or_issue_mismatch_is_rejected(self):
        for field in ("prior_candidate", "repair_issue"):
            with self.subTest(field=field), ExitStack() as stack:
                graph = self.graph(3)
                graph["materials"]["r1"][field] = {"different": "synthetic captured frame"}
                self.leaves(graph, stack)
                with self.assertRaisesRegex(ValueError, "review_issue_account_origin_changed"):
                    self.verify(graph)

    def test_review_cannot_invent_or_erase_a_verified_generation_edge(self):
        for missing in ("generation", "review"):
            with self.subTest(missing=missing), ExitStack() as stack:
                graph = self.graph(3)
                data = graph["materials"]["g1" if missing == "generation" else "r1"]
                data.update(prior_candidate=None, repair_issue=None)
                self.leaves(graph, stack)
                with self.assertRaisesRegex(ValueError, "review_issue_account_origin_changed"):
                    self.verify(graph)

    def test_unknown_ancestor_stays_charged_and_does_not_prove_a_finding(self):
        with ExitStack() as stack:
            graph = self.graph(3)
            row = next(row for row in graph["calls"] if row["request_identity"]["output_path"] == "r1.json")
            row["outcome"] = None
            original = deepcopy(graph["state"])
            self.leaves(graph, stack)
            with self.assertRaisesRegex(ValueError, "issue_not_original_host_finding"):
                self.verify(graph)
            self.assertEqual(graph["state"], original)

    def test_raw_review_binding_is_still_checked_on_the_aligned_edge(self):
        with ExitStack() as stack:
            graph = self.graph(3)
            graph["tampered_raw"] = "r1"
            self.leaves(graph, stack)
            with self.assertRaisesRegex(ValueError, "raw binding changed"):
                self.verify(graph)
            self.assertIn("r1", graph["raw_reads"])

    def test_cycle_identity_is_rejected_even_with_strictly_earlier_row_numbers(self):
        with ExitStack() as stack:
            graph = self.graph(3)
            graph["bindings"]["g1"]["binding_sha256"] = graph["bindings"]["g2"]["binding_sha256"]
            self.leaves(graph, stack)
            with self.assertRaisesRegex(ValueError, "origin_cycle_or_limit"):
                self.verify(graph)

    def test_total_action_work_and_original_slot_limit_fail_before_more_leaf_reads(self):
        with ExitStack() as stack:
            graph = self.graph(3)
            self.leaves(graph, stack)
            work = runtime._RepairOriginWork(graph["state"])
            work.spend(work.max_steps)
            with self.assertRaisesRegex(ValueError, "origin_work_limit"):
                self.verify(graph, work=work)
            self.assertEqual(graph["reserved_reads"], 0)
        with ExitStack() as stack:
            graph = self.graph(32)  # 65 rows is outside the unchanged stable-slot 64 limit.
            self.leaves(graph, stack)
            with self.assertRaisesRegex(ValueError, "origin_slot_limit"):
                self.verify(graph)
            self.assertEqual(graph["reserved_reads"], 0)

    def test_frame_reuse_requires_completed_generation_verification(self):
        frame = {"prior_candidate": {"original": True}, "repair_issue": {"account_policy": accounts.POLICY}}
        with self.assertRaisesRegex(ValueError, "review_issue_account_origin_changed"):
            runtime.check_review_origin_frame(deepcopy(frame), frame, generation_verified=False)
        runtime.check_review_origin_frame(deepcopy(frame), frame, generation_verified=True)



if __name__ == "__main__":
    unittest.main()
