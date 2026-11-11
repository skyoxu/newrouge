"""Offline indexed review codec; synthetic seams confer no native qualification."""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import jsonschema
import _b_route_planning_runtime as runtime


class IndexedReviewTests(unittest.TestCase):
    def setUp(self):
        self.blocks = [{"semantic_namespace": "synthetic-index-codec", "semantic_ledger_digest": "sha256:" + "1" * 64,
            "block_id": name, "original": {"raw_text": "Complete synthetic " + name}} for name in ("z", "a", "other")]
        self.sources = [runtime.source_key(row) for row in self.blocks]
        self.rows = [
            {"id": runtime.canonical_sha(["synthetic", "first"]), "target": ["synthetic", "first"],
             "source_block_ids": [self.sources[1], self.sources[0]]},
            {"id": runtime.canonical_sha(["synthetic", "second"]), "target": ["synthetic", "second"],
             "source_block_ids": [self.sources[2]]}]
        for name, value in (("obligations", self.rows), ("semantic_domain", ([], self.blocks))):
            seam = patch.object(runtime, name, return_value=deepcopy(value))
            seam.start()
            self.addCleanup(seam.stop)
        self.frozen = {"input_identity": "sha256:" + "2" * 64,
            "inputs": {"contract": {"scope": {"scope_id": "synthetic-scope"}}, "closure": {}}}
        descriptor = {"schema_version": runtime.PROFILE, "profile": "3b-capabilities-v1", "planner": "capabilities",
            "prepared_ref": "synthetic/prepared.json", "input_identity": self.frozen["input_identity"],
            "frozen_sha256": "sha256:" + "3" * 64, "rules": {"runtime": {}}, "limits": runtime.profile_limits("3b-capabilities-v1"),
            "wire_delivery": runtime.wire.CURRENT_SCHEMA}
        self.state = {"schema_version": runtime.RUN, "input_stage": "3b", "run_id": "indexed-codec-only",
            "planning_runtime": descriptor, "runtime_identity": runtime.canonical_sha(descriptor),
            "analysis_identity_sha256": self.frozen["input_identity"]}
        self.proposal = {"content": {"synthetic": True}, "provenance": {"kind": "model_draft", "draft_chain": []}}
        self.raw = {"schema_version": runtime.INDEXED_REVIEW, "input_identity": self.frozen["input_identity"],
            "runtime_identity": self.state["runtime_identity"], "proposal_sha256": runtime.canonical_sha(self.proposal),
            "verdict": "approved", "findings": [], "checks": [
                {"id": 0, "verdict": "approved", "rationale": "  Synthetic first rationale.\n", "source_block_ids": [1, 0]},
                {"id": 1, "verdict": "approved", "rationale": "Synthetic second rationale", "source_block_ids": [2]}]}

    def decode(self, value=None, policy=runtime.REVIEW_SOURCE_POLICY):
        return runtime.decode_review(self.state, self.proposal, self.frozen, self.raw if value is None else value, policy)

    def schema(self, policy=runtime.REVIEW_SOURCE_POLICY):
        return runtime.review_producer_schema(self.state, self.proposal, self.frozen, policy=policy)

    def install_generation_two_context(self):
        # Schema-only synthetic data; the real reopen-context reader is used.
        scope_id = self.frozen["inputs"]["contract"]["scope"]["scope_id"]
        self.state["capability_selection"] = {"generation": 2, "order": [scope_id]}
        self.state["reopen_contexts"] = {"2": {
            "generation": 2,
            "plan": {"path": "synthetic-reopen-plan.json", "sha256": "sha256:" + "4" * 64},
            "conflicts": [{"id": "synthetic-conflict"}],
            "replacement_order": [scope_id], "resolution_boundaries": {"synthetic-conflict": 0}}}

    def test_original_generation_schema_survives_later_reopen_context(self):
        original_schema = self.schema()
        original_bytes = runtime.canonical_sha(original_schema)
        self.install_generation_two_context()
        materials = {"phase": "independent_admission", "proposal": self.proposal,
            "generation": 1, "review_source_policy": runtime.REVIEW_SOURCE_POLICY}
        runtime.check_review_producer_schema(self.state, self.frozen, materials, original_schema)
        self.assertEqual(runtime.canonical_sha(original_schema), original_bytes)
        self.assertNotIn("reopen_reviews", original_schema["required"])
        self.assertIn("reopen_reviews", self.schema()["required"])

    def test_current_generation_keeps_exact_reopen_schema_and_generation_binding(self):
        original_schema = self.schema()
        self.install_generation_two_context()
        materials = {"phase": "independent_admission", "proposal": self.proposal,
            "generation": 2, "review_source_policy": runtime.REVIEW_SOURCE_POLICY}
        with self.assertRaisesRegex(ValueError, "review_producer_schema_changed"):
            runtime.check_review_producer_schema(self.state, self.frozen, materials, original_schema)
        current_schema = self.schema()
        runtime.check_review_producer_schema(self.state, self.frozen, materials, current_schema)
        with self.assertRaisesRegex(ValueError, "review_producer_schema_changed"):
            runtime.check_review_producer_schema(self.state, self.frozen,
                {**materials, "generation": 1}, current_schema)
        with self.assertRaisesRegex(ValueError, "reopen_context_missing"):
            runtime.check_review_producer_schema(self.state, self.frozen,
                {**materials, "generation": 3}, current_schema)

    def test_exact_codebooks_map_without_sorting_or_changing_original_fields(self):
        before = deepcopy(self.raw)
        expected = deepcopy(self.raw)
        expected["schema_version"] = runtime.REVIEW
        for row, obligation in zip(expected["checks"], self.rows):
            row["id"] = obligation["id"]
            row["source_block_ids"] = [self.sources[index] for index in row["source_block_ids"]]
        self.assertEqual(expected, self.decode())
        self.assertEqual(before, self.raw)
        schema = self.schema()
        jsonschema.Draft202012Validator.check_schema(schema)
        self.assertEqual(runtime.INDEXED_REVIEW, schema["properties"]["schema_version"]["const"])
        branch = schema["properties"]["checks"]["items"]["anyOf"][0]
        self.assertEqual({"type": "integer", "enum": [0]}, branch["properties"]["id"])
        self.assertEqual([1, 0], branch["properties"]["source_block_ids"]["items"]["enum"])

    def test_legitimate_blocked_review_preserves_findings_and_rationale_verbatim(self):
        value = deepcopy(self.raw)
        finding = "  Original finding with Unicode \u96ea and newline.\n"
        value["verdict"] = "blocked"
        value["checks"][0].update(verdict="blocked", rationale=finding)
        value["findings"] = [finding]
        result = self.decode(value)
        issues = runtime.review_issues(self.state, self.proposal, self.frozen, result)
        self.assertEqual(1, len(issues))
        self.assertEqual(finding, issues[0]["detail"])
        for key in ("verdict", "findings", "input_identity", "runtime_identity", "proposal_sha256"):
            self.assertEqual(value[key], result[key])
        self.assertEqual(value["checks"][0]["rationale"], result["checks"][0]["rationale"])

    def test_per_obligation_producer_rejects_associated_but_unpermitted_source(self):
        value = deepcopy(self.raw)
        value["checks"][0]["source_block_ids"].append(2)
        with self.assertRaisesRegex(ValueError, "producer_output_invalid"):
            self.decode(value)

    def test_indices_reject_bool_float_negative_out_of_range_and_string(self):
        for field in ("id", "source_block_ids"):
            for invalid in (True, False, 0.0, 1.0, -1, 200, "0", None):
                value = deepcopy(self.raw)
                value["checks"][0][field] = [invalid] if field == "source_block_ids" else invalid
                with self.subTest(field=field, invalid=invalid), self.assertRaises(ValueError):
                    self.decode(value)

    def test_duplicate_checks_and_sources_remain_canonical_gate_failures(self):
        for mutation in ("check", "source"):
            value = deepcopy(self.raw)
            if mutation == "check":
                value["checks"][1] = deepcopy(value["checks"][0])
            else:
                value["checks"][0]["source_block_ids"] = [1, 1]
            self.assertTrue(jsonschema.Draft202012Validator(self.schema()).is_valid(value))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.decode(value)

    def test_missing_extra_or_empty_checks_and_sources_are_rejected(self):
        for mutation in ("missing", "extra", "no-checks", "no-sources"):
            value = deepcopy(self.raw)
            if mutation == "missing":
                value["checks"].pop()
            elif mutation == "extra":
                value["checks"].append(deepcopy(value["checks"][0]))
            elif mutation == "no-checks":
                value["checks"] = []
            else:
                value["checks"][0]["source_block_ids"] = []
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.decode(value)

    def test_finding_denominator_and_verdict_contradictions_are_not_repaired(self):
        for mutation in ("hidden-finding", "missing-finding", "wrong-verdict", "duplicate-finding"):
            value = deepcopy(self.raw)
            value["checks"][0].update(verdict="blocked", rationale="Original issue")
            value.update(verdict="blocked", findings=["Original issue"])
            if mutation == "hidden-finding":
                value["findings"].append("Unrepresented issue")
            elif mutation == "missing-finding":
                value["findings"] = []
            elif mutation == "wrong-verdict":
                value["verdict"] = "approved"
            else:
                value["findings"] *= 2
            before = deepcopy(value)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.decode(value)
            self.assertEqual(before, value)

    def test_exact_producer_rejects_metadata_schema_and_unknown_fields(self):
        for field in ("schema_version", "input_identity", "runtime_identity", "proposal_sha256", "caller_pass"):
            value = deepcopy(self.raw)
            value[field] = True if field == "caller_pass" else "wrong"
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "producer_output_invalid"):
                self.decode(value)

    def test_legacy_decode_is_deep_copy_and_policy_cannot_relabel_carrier(self):
        historical = {"schema_version": runtime.REVIEW, "historical": ["  Exact old output.\n"]}
        for policy in (None, runtime.LEGACY_REVIEW_SOURCE_POLICY):
            result = self.decode(historical, policy)
            self.assertEqual(historical, result)
            self.assertIsNot(historical, result)
            self.assertIsNot(historical["historical"], result["historical"])
        with self.assertRaises(ValueError):
            self.decode(historical)
        with self.assertRaises(ValueError):
            self.decode(policy="unknown")
        with self.assertRaises(ValueError):
            runtime.check_review_producer_schema(self.state, self.frozen,
                {"phase": "independent_admission", "proposal": self.proposal, "review_source_policy": runtime.LEGACY_REVIEW_SOURCE_POLICY},
                self.schema())

    def test_versioned_prompt_delivers_complete_codebooks_and_zero_based_rule(self):
        materials = {"phase": "independent_admission", "wire_delivery": runtime.wire.CURRENT_SCHEMA,
            "review_source_policy": runtime.REVIEW_SOURCE_POLICY, "obligations": self.rows,
            "qualified_sources": runtime.qualified_sources(self.proposal, self.frozen)}
        prompt = runtime.materials_prompt(materials)
        self.assertIn("zero-based integer index", prompt)
        self.assertIn("Do not generate hashes", prompt)
        self.assertEqual(materials, runtime.wire.read_prompt(prompt, runtime.wire.CURRENT_SCHEMA))

    def test_invoke_decodes_review_but_retains_raw_file_and_execution_binding(self):
        with tempfile.TemporaryDirectory(prefix="indexed-codec-") as name:
            home = Path(name)
            output = home / "raw.json"
            original = json.dumps(self.raw, ensure_ascii=False).encode("utf-8")
            output.write_bytes(original)
            binding = {"synthetic_execution_binding": True}
            runner = Mock(return_value=(output, {"execution_binding": binding}))
            payload = {"phase": "independent_admission", "wire_delivery": runtime.wire.CURRENT_SCHEMA,
                "review_source_policy": runtime.REVIEW_SOURCE_POLICY, "proposal": self.proposal}
            with patch.object(runtime, "verify_call", return_value=deepcopy(self.raw)) as verify:
                value, actual_binding = runtime.invoke_data(lambda target: runner, self.frozen, home, 4,
                    payload, self.schema(), "semantic", Mock(), state=self.state)
            self.assertEqual(self.decode(), value)
            self.assertEqual(binding, actual_binding)
            verify.assert_called_once_with(binding)
            self.assertEqual(original, output.read_bytes())
            self.assertEqual(1, runner.call_count)

    def test_proof_replay_decodes_only_the_policy_from_bound_actual_materials(self):
        scope = {"capability_id": "synthetic-scope", "unit_kind": "governed_planning_closure",
            "scope": self.frozen["inputs"]["contract"]["scope"], "closure": {},
            "input_identity": self.frozen["input_identity"], "cumulative_requirement_ids": []}
        seed = {"synthetic_seed": True}
        record = {"scope": scope, "base_sha256": runtime.canonical_sha(seed),
            "proposal_sha256": runtime.canonical_sha(self.proposal), "context": 1,
            "delta": {"generation_calls": [], "lineage": {"context": 1, "identity": "synthetic-lineage"}},
            "proof": {"review": self.decode(), "runtime_identity": self.state["runtime_identity"],
                "obligations": self.rows, "lineage_context": 1}, "execution": {"synthetic_raw_binding": True}}
        materials = {"phase": "independent_admission", "review_source_policy": runtime.REVIEW_SOURCE_POLICY,
            "root_request": {"synthetic_original": "complete"}, "proposal": self.proposal, "accepted_seed": seed,
            "obligations": self.rows, "qualified_sources": runtime.qualified_sources(self.proposal, self.frozen),
            "lineage_identity": "synthetic-lineage"}
        def proof():
            record["record_sha256"] = runtime.canonical_sha({k: v for k, v in record.items() if k != "record_sha256"})
            return runtime.admission_proof(self.state, seed, [scope], [record], self.proposal)
        with ExitStack() as stack:
            for function, result in (("frozen_input", self.frozen), ("verify_proof_reservations", None),
                    ("merge", self.proposal), ("bound_materials", materials), ("verify_call", self.raw),
                    ("request_attempt", {"payload": json.dumps(materials["root_request"])}), ("machine", [])):
                stack.enter_context(patch.object(runtime, function, return_value=result))
            self.assertEqual([], runtime.proof_errors(Path("synthetic"), self.state, self.proposal, proof()))
            record["proof"]["review"]["checks"][0]["rationale"] += " altered"
            self.assertIn("proof_execution_changed", str(runtime.proof_errors(Path("synthetic"), self.state, self.proposal, proof())))
            record["proof"]["review"] = self.decode()
            materials.pop("review_source_policy")
            self.assertIn("proof_execution_changed", str(runtime.proof_errors(Path("synthetic"), self.state, self.proposal, proof())))


if __name__ == "__main__":
    unittest.main(verbosity=2)
