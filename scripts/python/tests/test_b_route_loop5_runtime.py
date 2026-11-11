"""Loop-five offline regressions; synthetic protocols never grant qualification."""
from copy import deepcopy
import os
import unittest
from unittest.mock import Mock, patch

import _b_route_planning_runtime as runtime
import _mvg_capability_append as append
import _planning_skill_common as common
import test_b_route_planning_runtime as fixtures
import test_b_route_loop4_runtime as loop4_fixtures


class MaskedMachineTests(unittest.TestCase):
    create = loop4_fixtures.FreshProfileProtocolTests.create

    def setUp(self):
        fixtures.RuntimeTests.setUp(self)
        self.run, self.state = self.create(run_id="masked")

    def broken(self, *, human=True):
        value = deepcopy(self.value)
        flow = value["content"]["definitions"]["flows"][0]
        flow["ui"].update(applicability="applicable", responsibilities=[], inputs=["Declared input"],
            feedback=["Visible feedback"], scene_entry=["Declared entry"], scene_return=["Declared return"])
        flow["human_verification"].update(applicability="applicable",
            responsibilities=[] if human else ["Observe the declared result"])
        return value

    def fix(self, value, field):
        result = deepcopy(value)
        result["content"]["definitions"]["flows"][0][field]["responsibilities"] = ["Source-backed responsibility"]
        return result

    def issue(self, value):
        return runtime.admission_machine(self.root, self.state, value)[0]

    def test_real_old_hidden_failure_can_be_repaired_in_sequence_without_mutating_original(self):
        before = self.broken()
        snapshot = deepcopy(before)
        ui_issue = self.issue(before)
        first = self.fix(before, "ui")
        human_issue = self.issue(first)
        self.assertTrue(ui_issue["detail"]["entity_id"].endswith(".ui"))
        self.assertTrue(human_issue["detail"]["entity_id"].endswith(".human_verification"))
        self.assertEqual(runtime.repair_scope_errors(self.root, self.state, before, first, ui_issue), [])
        self.assertIn(human_issue, runtime.local_machine_witnesses(self.root, self.state, before))
        self.assertEqual(self.issue(before), ui_issue)
        final = self.fix(first, "human_verification")
        self.assertEqual(runtime.repair_scope_errors(self.root, self.state, first, final, human_issue), [])
        self.assertEqual(runtime.admission_machine(self.root, self.state, final), [])
        self.assertEqual(before, snapshot)

    def test_shared_predicates_also_witness_a_hidden_failure_within_one_local_owner(self):
        before = self.broken(human=False)
        before["content"]["definitions"]["flows"][0]["ui"]["inputs"] = []
        after = self.fix(before, "ui")
        self.assertEqual(self.issue(after)["detail"]["expected"],
            "explicit input, feedback, scene entry and return obligations")
        self.assertEqual(runtime.repair_scope_errors(self.root, self.state, before, after, self.issue(before)), [])
        self.assertTrue(runtime.admission_machine(self.root, self.state, after))

    def test_canonical_local_first_failure_order_and_diagnostics_are_unchanged(self):
        store = runtime.candidate.frozen_bytes(self.root, self.ref, self.frozen, runtime.sources.Observations(self.root))
        owners, resolve, plans = runtime.candidate.check_owners(self.value["content"], store)
        blocks, _scope = runtime.candidate.check_sources(self.value["content"], self.frozen, store, plans)
        before = self.broken()
        first = self.fix(before, "ui")
        complete = self.fix(first, "human_verification")
        missing_input = deepcopy(complete)
        missing_input["content"]["definitions"]["flows"][0]["ui"]["inputs"] = []
        missing_part = deepcopy(complete)
        missing_part["content"]["definitions"]["flows"][0]["parts"].pop()
        unknown_source = deepcopy(complete)
        unknown_source["content"]["definitions"]["flows"][0]["source_block_ids"] = ["UNKNOWN-SOURCE"]
        fid = self.value["content"]["definitions"]["flows"][0]["id"]
        cases = ((before, fid + ".ui", "nonempty applicable responsibility"),
                 (first, fid + ".human_verification", "nonempty applicable responsibility"),
                 (missing_input, fid + ".ui", "explicit input, feedback, scene entry and return obligations"),
                 (missing_part, fid, "all four applicability responsibilities exactly once"),
                 (unknown_source, fid, "known Flow source blocks"))
        for value, entity, expected in cases:
            with self.subTest(expected=expected), self.assertRaises(runtime.codec.CodecError) as failure:
                runtime.candidate.check_graph(value["content"], owners, resolve, blocks)
            self.assertEqual(failure.exception.diagnostic.to_dict(), {
                "reason_code": runtime.codec.ReasonCode.SEMANTIC_ERROR.value,
                "stage": runtime.codec.Stage.CONTENT.value, "entity_id": entity,
                "expected": expected, "actual": None, "resume_ref": None})
        runtime.candidate.check_graph(complete["content"], owners, resolve, blocks)

    def test_new_human_failure_outside_domain_and_no_progress_are_rejected(self):
        before = self.broken(human=False)
        after = self.fix(before, "ui")
        after["content"]["definitions"]["flows"][0]["human_verification"]["responsibilities"] = []
        self.assertEqual(runtime.machine_repair_errors(self.root, self.state, before, after),
            ["repair_new_machine_issue"])
        self.assertIn("b_route_repair_outside_domain",
            runtime.repair_scope_errors(self.root, self.state, before, after, self.issue(before)))
        self.assertIn("b_route_repair_no_target_progress",
            runtime.repair_scope_errors(self.root, self.state, before, before, self.issue(before)))

    def test_unproven_hidden_or_new_business_defects_still_fail_closed(self):
        for existing in (False, True):
            with self.subTest(already_hidden=existing):
                before = self.broken(human=False)
                if existing:
                    before["content"]["implementation_objects"][0]["availability"] = "existing"
                after = self.fix(before, "ui")
                after["content"]["implementation_objects"][0]["availability"] = "existing"
                self.assertEqual(self.issue(after)["detail"]["expected"], "existing object has exact frozen reference")
                self.assertIn("repair_new_machine_issue",
                    runtime.repair_scope_errors(self.root, self.state, before, after, self.issue(before)))

    def test_schema_source_identity_and_owner_errors_are_never_witness_exemptions(self):
        before = self.broken()
        after = self.fix(before, "ui")
        mutations = (
            ("input_identity", lambda value: value.update(input_identity="sha256:" + "0" * 64),
             runtime.codec.ReasonCode.SEMANTIC_ERROR, "exact current prepared identity"),
            ("schema_extra_field", lambda value: value["content"].update(unknown="illegal schema field"),
             runtime.codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
             {"json_pointer": "/content", "rule": "additionalProperties"}),
            ("source_revision", lambda value: value["content"]["source_identity"].update(source_revision="foreign revision"),
             runtime.codec.ReasonCode.SEMANTIC_ERROR, "matching native source revision and manifest digest"),
            ("source_manifest_digest", lambda value: value["content"]["source_identity"].update(
                source_manifest_digest="sha256:" + "0" * 64),
             runtime.codec.ReasonCode.SEMANTIC_ERROR, "matching native source revision and manifest digest"),
        )
        for name, mutate, reason, expected in mutations:
            changed = deepcopy(after)
            mutate(changed)
            with self.subTest(mutation=name), self.assertRaises(runtime.codec.CodecError) as failure:
                runtime.repair_scope_errors(self.root, self.state, before, changed, self.issue(before))
            self.assertEqual(failure.exception.diagnostic.reason_code, reason)
            self.assertEqual(failure.exception.diagnostic.expected, expected)
        # An unresolved logical owner is a canonical machine business diagnostic.
        # It must reject the repair explicitly, rather than escape as an exception.
        changed = deepcopy(after)
        changed["content"]["definitions"]["flows"][0]["human_verification"]["owner"].update(
            definition_id="UNKNOWN-OWNER")
        with self.subTest(mutation="unknown_logical_owner"):
            self.assertEqual(runtime.repair_scope_errors(self.root, self.state, before, changed, self.issue(before)),
                ["b_route_repair_outside_domain", "repair_new_machine_issue"])
        with patch.object(runtime, "admission_machine", side_effect=RuntimeError("execution binding failure")):
            with self.assertRaisesRegex(RuntimeError, "execution binding failure"):
                runtime.machine_repair_errors(self.root, self.state, before, after)

    def handoff_candidate(self, *, linked=False):
        value = deepcopy(self.value)
        flow = value["content"]["definitions"]["flows"][0]
        flow["handoffs"] = [{"id": "unlinked-handoff",
            "from": {"flow_id": flow["id"], "node_id": "entry"},
            "to": {"flow_id": flow["id"], "node_id": "act" if linked else "optional"},
            "owner": deepcopy(flow["ui"]["owner"]), "state_uses": [],
            "responsibility": "Transfer the declared result", "result": "Next node observes the result"}]
        return value

    def test_original_missing_handoff_edge_uses_only_three_clean_replacement_rounds(self):
        value = self.handoff_candidate()
        original = deepcopy(value)
        issue = self.issue(value)
        self.assertEqual(issue["detail"]["entity_id"], "unlinked-handoff")
        self.assertEqual(issue["detail"]["expected"], "handoff corresponds to declared graph edge")
        self.assertFalse(runtime.repair_is_local(value, self.frozen, issue, root=self.root, state=self.state))
        self.assertEqual(value, original)
        seed = runtime.seed(self.state, self.run / "analysis-input")
        scope = runtime.scopes(self.state, self.run / "analysis-input")[0]
        self.state["capability_selection"] = {"current": {"capability_id": scope["capability_id"]},
            "calls": [{"number": 1, "outcome": None, "reservation_id": "original-unknown"}]}
        original_calls = deepcopy(self.state["capability_selection"]["calls"])
        contexts = []
        def propose(scope, accepted, prior, finding, context, call):
            self.assertEqual(accepted, seed)
            self.assertIsNone(prior)
            self.assertIsNone(finding)
            contexts.append(context)
            call("generate")
            return deepcopy(value)
        semantic = Mock(side_effect=AssertionError("missing edge cannot be admitted"))
        result = append.run_capability_append(self.run / "handoff-replacement", scopes=[scope], seed=seed,
            identity=self.state["runtime_identity"], propose=propose,
            machine=lambda scope, accepted, proposal: runtime.admission_machine(self.root, self.state, proposal),
            final_machine=lambda proposal: runtime.admission_machine(self.root, self.state, proposal),
            semantic=semantic, merge=lambda base, delta, scope: deepcopy(delta), preserve=lambda *_: [],
            repairability=lambda before, finding: runtime.repair_is_local(
                before, self.frozen, finding, root=self.root, state=self.state),
            replacement=lambda **event: runtime.replacement_reservation(self.state, "candidate-1", **event),
            invocation_limit=64, fail_execution_closed=True)
        self.assertEqual((result["status"], result["total_invocations"]), ("retired", 4))
        self.assertEqual(contexts, [1, 2, 3, 4])
        self.assertEqual(self.state["capability_selection"]["replacement_depths"]["candidate-1"], 3)
        self.assertEqual(self.state["capability_selection"]["calls"], original_calls)
        self.assertTrue(all(row["repair_attempts"] == 0 for row in result["restarts"]))
        self.assertEqual(result["accepted"], seed)
        semantic.assert_not_called()

    def test_handoff_replacement_rejects_forged_unrelated_immutable_and_execution_errors(self):
        original = self.handoff_candidate()
        issue = self.issue(original)
        for name, mutate in (
                ("schema", lambda value: value["content"].update(unknown="invalid schema")),
                ("source", lambda value: value["content"]["source_identity"].update(source_revision="foreign")),
                ("identity", lambda value: value.update(input_identity="sha256:" + "0" * 64))):
            value = deepcopy(original)
            mutate(value)
            with self.subTest(mutation=name), self.assertRaises(runtime.codec.CodecError):
                runtime.repair_is_local(value, self.frozen, issue, root=self.root, state=self.state)
        forged = deepcopy(issue)
        forged["detail"]["entity_id"] = "foreign-handoff"
        nonsemantic = deepcopy(issue)
        nonsemantic["detail"]["reason_code"] = runtime.codec.ReasonCode.MAPPING_MISMATCH.value
        for name, value, finding in (("forged", original, forged), ("nonsemantic", original, nonsemantic),
                ("linked", self.handoff_candidate(linked=True), issue)):
            with self.subTest(mutation=name), self.assertRaisesRegex(ValueError, "original_host_finding"):
                runtime.repair_is_local(value, self.frozen, finding, root=self.root, state=self.state)
        for name in ("missing_endpoint", "unrelated_object"):
            value = self.handoff_candidate() if name == "missing_endpoint" else deepcopy(self.value)
            if name == "missing_endpoint":
                value["content"]["definitions"]["flows"][0]["handoffs"][0]["to"]["node_id"] = "UNKNOWN-NODE"
            else:
                value["content"]["implementation_objects"][0]["availability"] = "existing"
            finding = self.issue(value)
            with self.subTest(mutation=name), self.assertRaisesRegex(ValueError, "repair_domain_unresolved"):
                runtime.repair_is_local(value, self.frozen, finding, root=self.root, state=self.state)
        with patch.object(runtime, "admission_machine", side_effect=RuntimeError("execution binding failure")):
            with self.assertRaisesRegex(RuntimeError, "execution binding failure"):
                runtime.repair_is_local(original, self.frozen, issue, root=self.root, state=self.state)

    def test_production_generate_append_wiring_preserves_continuous_masked_repairs(self):
        before = self.broken()
        first = self.fix(before, "ui")
        complete = self.fix(first, "human_verification")
        contents = [value["content"] for value in (before, first, complete)]
        self.assertEqual(len(self.frozen["transport"]["batches"]), 1)
        self.state["runtime_slot"] = "candidate-1"
        requests, checkpoints, synthesis_attempts = [], [], [0]
        def model_leaf(factory, frozen, workspace, number, payload, schema, phase, call, **kwargs):
            # Only the model/execution transport leaf is synthetic. Production
            # generate_append supplies all callbacks to the real append loop.
            call(phase)
            requests.append(deepcopy(payload))
            if payload["phase"] == "generation":
                expected = payload["root_request"]["input"]
                attempt = synthesis_attempts[0]
                self.assertLess(attempt, len(contents), "production rejected a witnessed original failure")
                draft = {"schema_version": runtime.planning.DRAFT, "input_identity": frozen["input_identity"],
                    "stage": expected["stage"], "ordinal": expected["ordinal"],
                    "parent_draft_identities": [row["identity"] for row in expected["prior_drafts"]],
                    "content": deepcopy(contents[attempt])}
                if expected["stage"] == "synthesis":
                    synthesis_attempts[0] += 1
                return draft, {"synthetic": "model-transport-leaf"}
            self.assertEqual(payload["proposal"]["content"], complete["content"])
            return fixtures.RuntimeTests.review(self, self.state, proposal=payload["proposal"]), {
                "synthetic": "model-transport-leaf"}
        replacement = Mock(side_effect=AssertionError("local repairs must not replace their lineage"))
        with patch.object(runtime, "invoke_data", side_effect=model_leaf):
            result = runtime.generate_append(self.root, self.state, self.run,
                invoke_factory=Mock(side_effect=AssertionError("transport leaf owns fixture output")),
                before_call=None, checkpoint=lambda ledger: checkpoints.append(deepcopy(ledger)),
                replacement=replacement)
        self.assertEqual((result["status"], result["total_invocations"]), ("admitted", 7))
        self.assertEqual(result["accepted"]["content"], complete["content"])
        self.assertEqual(result["restarts"], [])
        self.assertNotIn("rejected_repairs", result)
        self.assertEqual(synthesis_attempts[0], 3)
        synthesis = [row for row in requests if row["phase"] == "generation"
            and row["root_request"]["input"]["stage"] == "synthesis"]
        self.assertEqual([row["repair_issue"] for row in synthesis], [None, self.issue(before), self.issue(first)])
        self.assertEqual([row["lineage_context"] for row in synthesis], [1, 1, 1])
        attempts = {append.issue_key(self.issue(before)): 1, append.issue_key(self.issue(first)): 1}
        self.assertTrue(any((row.get("current") or {}).get("issue_attempts") == attempts for row in checkpoints))
        self.assertEqual(common.load_json(self.run / "proposal.json"), result["accepted"])
        replacement.assert_not_called()

    def run_append(self, name, proposals, *, callback=True, preserve=None, limit=4):
        seed = runtime.seed(self.state, self.run / "analysis-input")
        scope = runtime.scopes(self.state, self.run / "analysis-input")[0]
        generated, semantic_calls, checkpoints = [], [], []
        def propose(scope, accepted, prior, issue, context, call):
            call("generate")
            generated.append(deepcopy(issue))
            return deepcopy(proposals[min(len(generated) - 1, len(proposals) - 1)])
        def semantic(scope, accepted, proposal, call, context):
            call("semantic")
            semantic_calls.append(deepcopy(proposal))
            return {"issues": [], "proof": {"synthetic": "local-loop-only"}, "execution": {}}
        options = {} if callback is False else {"machine_repair_check": callback if callable(callback) else
            lambda before, after: runtime.machine_repair_errors(self.root, self.state, before, after)}
        result = append.run_capability_append(self.run / name, scopes=[scope], seed=seed,
            identity=self.state["runtime_identity"], propose=propose,
            machine=lambda scope, accepted, proposal: runtime.admission_machine(self.root, self.state, proposal),
            final_machine=lambda proposal: runtime.admission_machine(self.root, self.state, proposal),
            semantic=semantic, merge=lambda base, delta, scope: deepcopy(delta),
            preserve=preserve or (lambda *_: []), invocation_limit=limit, fail_execution_closed=True,
            checkpoint=lambda ledger: checkpoints.append(deepcopy(ledger)),
            repair_check=lambda before, after, issue, **kwargs: runtime.repair_scope_errors(
                self.root, self.state, before, after, issue, **kwargs), **options)
        self.last_append_checkpoints = checkpoints
        return result, generated, semantic_calls

    def test_actual_append_keeps_old_issue_accounts_and_continues_both_local_repairs(self):
        before = self.broken()
        first = self.fix(before, "ui")
        final = self.fix(first, "human_verification")
        result, generated, semantic = self.run_append("sequence", [before, first, final])
        self.assertEqual((result["status"], result["total_invocations"]), ("admitted", 4))
        self.assertEqual(generated, [None, self.issue(before), self.issue(first)])
        self.assertEqual(semantic, [final])
        self.assertEqual(result["accepted"], final)
        self.assertEqual(result["restarts"], [])
        self.assertNotIn("rejected_repairs", result)
        self.assertEqual(result["issue_events"][-1]["issue_attempts"], {append.issue_key(self.issue(before)): 1})
        attempts = {append.issue_key(self.issue(before)): 1, append.issue_key(self.issue(first)): 1}
        self.assertTrue(any((row.get("current") or {}).get("issue_attempts") == attempts
            for row in self.last_append_checkpoints))

    def test_actual_append_rejects_new_human_and_preservation_exemptions(self):
        original = self.broken(human=False)
        introduced = self.fix(original, "ui")
        introduced["content"]["definitions"]["flows"][0]["human_verification"]["responsibilities"] = []
        result, generated, semantic = self.run_append("new-human", [original, introduced], limit=3)
        self.assertEqual((result["status"], result["total_invocations"]), ("retired", 3))
        self.assertEqual(semantic, [])
        self.assertTrue(all("repair_new_machine_issue" in row["errors"] for row in result["rejected_repairs"]))
        before = self.broken()
        first = self.fix(before, "ui")
        def preserve(seed, proposal):
            return ([{"code": "accepted_predecessor_changed", "path": "seed"}]
                if proposal["content"]["definitions"]["flows"][0]["ui"]["responsibilities"] else [])
        result, generated, semantic = self.run_append("preservation", [before, first], preserve=preserve, limit=3)
        self.assertEqual(result["status"], "retired")
        self.assertEqual(semantic, [])
        self.assertTrue(all("repair_new_preservation_issue" in row["errors"] for row in result["rejected_repairs"]))

    def test_actual_append_keeps_legacy_first_error_rule_and_rejects_invalid_callback_results(self):
        before = self.broken()
        first = self.fix(before, "ui")
        result, generated, semantic = self.run_append("legacy", [before, first], callback=False, limit=3)
        self.assertEqual(result["status"], "retired")
        self.assertEqual(semantic, [])
        self.assertTrue(all("repair_new_machine_issue" in row["errors"] for row in result["rejected_repairs"]))
        for index, invalid in enumerate((None, True, {"errors": []}, [True], [""])):
            with self.subTest(callback_result=invalid):
                result, generated, semantic = self.run_append("bad-callback-" + str(index), [before, first],
                    callback=lambda *args: invalid, limit=3)
                self.assertEqual((result["status"], result["total_invocations"]), ("blocked", 2))
                self.assertIn("append_machine_repair_errors_required", result["errors"][0]["detail"])
                self.assertEqual(semantic, [])

    def test_actual_append_mixed_immutable_failures_stop_without_replacement_or_semantic_admission(self):
        before = self.broken()
        for index, mutate in enumerate((
                lambda value: value["content"]["source_identity"].update(source_revision="foreign source"),
                lambda value: value.update(input_identity="sha256:" + "0" * 64),
                lambda value: value["content"].update(unknown="invalid schema"))):
            after = self.fix(before, "ui")
            mutate(after)
            with self.subTest(mixed_failure=index):
                result, generated, semantic = self.run_append("mixed-" + str(index), [before, after], limit=3)
                self.assertEqual((result["status"], result["total_invocations"]), ("blocked", 2))
                self.assertEqual(result["errors"][0]["code"], "append_execution_failure")
                self.assertEqual(semantic, [])
                self.assertEqual(result["records"], [])
                self.assertEqual(result["restarts"], [])
                self.assertEqual(result["accepted"], runtime.seed(self.state, self.run / "analysis-input"))


class DistinctHandoffTests(unittest.TestCase):
    setUp = fixtures.RuntimeTests.setUp
    create = loop4_fixtures.FreshProfileProtocolTests.create

    def test_completed_handoff_has_exact_winner_relative_deltas_for_all_admitted_candidates(self):
        entries = {
            "candidate-1": "First independently declared entry condition",
            "candidate-2": "Second independently declared entry condition",
            "candidate-3": "Third independently declared entry condition",
        }
        contents = {}
        for label, entry in entries.items():
            contents[label] = deepcopy(self.value["content"])
            contents[label]["definitions"]["flows"][0]["entry_condition"] = entry
        originals = deepcopy(contents)
        # Complete production generation/admission/reservation/selector/checkpoint
        # validators run; only model stdio and source preparation are fixtures.
        with patch.dict(os.environ, {"NEWROGUE_CODEX_REASONING_EFFORT": "high",
                "NEWROGUE_B_ROUTE_FIXTURE_REASONING_EFFORT": "high"}):
            delivery, state, run = fixtures.ReviewFixTests.complete_offline_transport_coordinator(
                self, "3b-mvg-v1", complete_wire=True, candidate_contents=contents)
        self.assertEqual(state["selection_status"], "selected")
        self.assertEqual(contents, originals)
        self.assertEqual(len(delivery["selected"]), 1)
        step = delivery["selected"][0]
        self.assertEqual(set(step["admissions"]), set(entries))
        winner = step["selected_candidate"]
        expected = []
        for label, admission in step["admissions"].items():
            proposal = common.load_json(run / admission["proposal_path"])
            self.assertEqual(proposal["content"], originals[label])
            self.assertEqual(runtime.admission_machine(self.root, state, proposal), [])
            proof = common.load_json(run / admission["proof_path"])
            self.assertTrue(proof["records"])
            # json_delta treats an ordered array as a complete replacement.
            # Expected paths and values come from literal generated fixtures,
            # never from the delta helper or the handoff under test.
            delta = [] if label == winner else [{
                "op": "replace", "path": "/definitions/flows",
                "before": originals[winner]["definitions"]["flows"],
                "after": originals[label]["definitions"]["flows"],
            }]
            expected.append({"candidate": label, "lineage": admission["lineage"],
                "proposal_sha256": admission["proposal_sha256"],
                "selected": label == winner, "changes_from_selected": delta})
        self.assertEqual(delivery["comparisons"], expected)
        self.assertEqual(sum(row["selected"] for row in delivery["comparisons"]), 1)
        self.assertFalse(delivery["formal_adoption"] or delivery["readiness"] or delivery["runtime_verified"])


if __name__ == "__main__":
    unittest.main()
