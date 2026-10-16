"""Lossless auxiliary-evidence transport and admission regression tests."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _planning_skill_common import canonical_sha


class EvidenceTransportTests(unittest.TestCase):
    def transport(self):
        try:
            return importlib.import_module("_mvg_evidence_transport")
        except ImportError:
            self.fail("Complete bounded evidence transport is not implemented")

    def context(self):
        return {"scope": {"capability_id": "CAP-A", "requirement_ids": ["FR-A"]},
                "requirements": [{"requirement_id": "FR-A", "statement": "Complete requirement tail"}],
                "task_views": [{"acceptance": ["Complete acceptance tail"]}],
                "source_blocks": [{"text": "Complete source tail"}],
                "evidence": [{"path": "test.cs", "sha256": "sha256:fixture",
                              "text": "START\r\n" + "Body 中文\n" * 20 + "END  \n"},
                             {"path": "missing.cs", "status": "not_prepared"}]}

    def plan(self, context):
        module = self.transport()
        def probe(prompt, schema):
            if len(prompt.encode("utf-8")) > 2400:
                raise ValueError("runner_context_budget_exceeded:fixture")
            return {"request_sha256": canonical_sha(prompt), "truncation_allowed": False}
        return module.plan_transport(context, phase="inspect", probe=probe)

    def audit(self, plan, batch):
        reports = {part["part_id"]: {"part_id": part["part_id"],
                    "verdict": "relevant", "requirement_ids": ["FR-A"],
                    "rationale": "Complete source was inspected", "facts": ["Source supports FR-A"],
                    "citations": [1], "hard_issues": []} for part in batch["parts"]}
        return {"schema_version": "newrouge.mvg-evidence-audit.v1",
                "context_sha256": plan["context_sha256"], "batch_sha256": canonical_sha(batch["parts"]),
                "phase": plan["phase"], "reports": reports}

    def test_batches_reassemble_every_character_and_preserve_core(self):
        module = self.transport()
        context = self.context()
        context["evidence"][0]["text"] *= 20
        plan = self.plan(context)
        self.assertGreater(len(plan["batches"]), 1)
        self.assertEqual([], module.plan_errors(context, plan))
        pieces = [part for batch in plan["batches"] for part in batch["parts"]]
        self.assertEqual(context["evidence"][0]["text"], "".join(part["text"] for part in pieces))
        self.assertEqual({key: value for key, value in context.items() if key != "evidence"}, plan["core"])
        self.assertEqual("not_prepared", plan["inventory"][1]["status"])

    def test_transmitted_line_addresses_preserve_every_source_character(self):
        module = self.transport()
        context = self.context()
        context["evidence"][0]["text"] = "HEAD\r\n\r\n1|中文  \nMID\rTAIL\t"
        plan = self.plan(context)
        batch = plan["batches"][0]
        source = batch["parts"][0]
        prompt = module.audit_prompt(plan, batch["parts"])
        marker = "SOURCE PART " + source["part_id"] + " CHARACTERS " + str(len(source["text"])) + "\n"
        actual = prompt.split(marker, 1)[1].split("\nEND SOURCE PART " + source["part_id"], 1)[0]
        numbered = "".join(str(number) + "|" + line for number, line in
                           enumerate(source["text"].splitlines(keepends=True), 1))
        self.assertEqual(numbered, actual)
        row = {"citations": list(range(1, len(source["text"].splitlines(keepends=True)) + 1))}
        self.assertEqual(source["text"], "".join(quote["text"] for quote in module.resolve_citations(source, row)))

    def test_missing_duplicate_reordered_and_changed_parts_fail_closed(self):
        module = self.transport()
        context = self.context()
        context["evidence"][0]["text"] *= 10
        plan = self.plan(context)
        for mutation in ("missing", "duplicate", "reordered", "changed"):
            with self.subTest(mutation=mutation):
                changed = deepcopy(plan)
                parts = changed["batches"][0]["parts"]
                if mutation == "missing":
                    parts.clear()
                elif mutation == "duplicate":
                    parts.append(deepcopy(parts[0]))
                elif mutation == "reordered":
                    changed["batches"].reverse()
                else:
                    parts[0]["text"] += "CORRUPTION"
                self.assertTrue(module.plan_errors(context, changed))

    def test_core_oversize_blocks_before_any_model_call(self):
        module = self.transport()
        context = self.context()
        probes = []
        def probe(prompt, schema):
            probes.append(prompt)
            raise ValueError("runner_context_budget_exceeded:core")
        with self.assertRaisesRegex(ValueError, "runner_context_budget_exceeded"):
            module.plan_transport(context, phase="inspect", probe=probe)
        self.assertEqual(1, len(probes), "An oversized core cannot shrink by recursively splitting evidence")
        self.assertNotIn("SOURCE PART ", probes[0])

    def test_core_without_auxiliary_text_still_requires_preflight(self):
        module = self.transport()
        context = self.context()
        context["evidence"] = []
        for phase in ("inspect", "review"):
            with self.subTest(phase=phase), self.assertRaisesRegex(ValueError, "runner_input_too_large:core"):
                module.plan_transport(context, phase=phase, probe=lambda prompt, schema: (
                    _ for _ in ()).throw(ValueError("runner_input_too_large:core")))

    def test_adjacent_batches_are_coalesced_only_after_final_probe(self):
        module = self.transport()
        context = self.context()
        context["evidence"][0]["text"] = "A" * 2500
        context["evidence"][1].update(text="B" * 100, sha256="sha256:missing")
        probes = []

        def probe(prompt, schema):
            probes.append(prompt)
            if len(prompt.encode("utf-8")) > 4000:
                raise ValueError("runner_context_budget_exceeded:fixture")
            return {"request_sha256": canonical_sha(prompt), "truncation_allowed": False}

        plan = module.plan_transport(context, phase="inspect", probe=probe)
        # Binary splitting alone produces these three exact parts/batches.
        # The final two batches can share one request without changing any
        # source address or part hash.
        expected_parts = [module.part(context["evidence"][0], 0, 1250),
                          module.part(context["evidence"][0], 1250, 2500),
                          module.part(context["evidence"][1])]
        self.assertEqual(2, len(plan["batches"]))
        self.assertEqual(2, len(plan["batches"][1]["parts"]))
        self.assertEqual([], module.plan_errors(context, plan))
        pieces = [part for batch in plan["batches"] for part in batch["parts"]]
        self.assertEqual(expected_parts, pieces)
        self.assertEqual(context["evidence"][0]["text"], "".join(
            part["text"] for part in pieces if part["path"] == "test.cs"))
        self.assertEqual(context["evidence"][1]["text"], "".join(
            part["text"] for part in pieces if part["path"] == "missing.cs"))
        # The merged request itself was sent through the same probe, rather
        # than accepted from a byte estimate.
        for batch in plan["batches"]:
            prompt = module.audit_prompt(plan, batch["parts"])
            self.assertIn(prompt, probes)
            self.assertEqual(canonical_sha(prompt), batch["input_report"]["request_sha256"])

    def test_adjacent_batch_merge_propagates_non_capacity_probe_errors(self):
        module = self.transport()
        context = self.context()
        context["evidence"][0]["text"] = "A" * 2500
        context["evidence"][1].update(text="B" * 100, sha256="sha256:missing")

        def probe(prompt, schema):
            payload = json.loads(prompt.split("\n", 1)[1].split("\nSOURCE PART ", 1)[0])
            parts = payload["parts"]
            if len(parts) == 2 and parts[0]["start"] == 1250:
                raise ValueError("runner_isolation_invalid:fixture")
            if len(prompt.encode("utf-8")) > 4000:
                raise ValueError("runner_context_budget_exceeded:fixture")
            return {"request_sha256": canonical_sha(prompt), "truncation_allowed": False}

        with self.assertRaisesRegex(ValueError, "runner_isolation_invalid"):
            module.plan_transport(context, phase="inspect", probe=probe)

    def test_schema_dedup_keeps_exact_validation_constraints(self):
        import jsonschema
        module = self.transport()
        domain = {"type": "string", "enum": ["source-" + str(n) for n in range(200)]}
        schema = {"type": "object", "properties": {"a": domain, "b": deepcopy(domain)},
                  "required": ["a", "b"], "additionalProperties": False}
        compact = module.compact_schema(schema)
        self.assertLess(len(json.dumps(compact)), len(json.dumps(schema)))
        for value, valid in (({"a": "source-2", "b": "source-3"}, True),
                             ({"a": "source-2", "b": "foreign"}, False),
                             ({"a": "source-2"}, False)):
            self.assertEqual(valid, jsonschema.Draft202012Validator(compact).is_valid(value))
            self.assertEqual(valid, jsonschema.Draft202012Validator(schema).is_valid(value))

    def test_audit_requires_every_part_and_verifiable_quotes(self):
        module = self.transport()
        context = self.context()
        # Supply two complete sources so omission and duplicate accounting
        # exercise distinct part identities rather than the same sole part.
        context["evidence"].insert(1, {
            "path": "second.cs", "sha256": "sha256:second",
            "text": "class Secondary { }\n"})
        plan = module.plan_transport(context, phase="inspect", probe=lambda prompt, schema: {
            "request_sha256": canonical_sha(prompt), "truncation_allowed": False})
        self.assertGreaterEqual(len(plan["batches"][0]["parts"]), 2)
        batch = plan["batches"][0]
        audit = self.audit(plan, batch)
        self.assertEqual([], module.audit_errors(plan, batch, audit))
        audit["reports"] = {}
        self.assertTrue(module.audit_errors(plan, batch, audit))
        import jsonschema
        schema = module.audit_schema(plan, batch["parts"])
        missing = self.audit(plan, batch)
        missing["reports"].pop(next(reversed(missing["reports"])))
        self.assertFalse(jsonschema.Draft202012Validator(schema).is_valid(missing))
        duplicate = self.audit(plan, batch)
        duplicate["reports"][list(duplicate["reports"])[-1]]["part_id"] = list(duplicate["reports"])[0]
        self.assertFalse(jsonschema.Draft202012Validator(schema).is_valid(duplicate))
        self.assertTrue(module.audit_errors(plan, batch, duplicate))

    def test_cli_schema_binds_source_line_addresses_to_the_exact_part(self):
        import jsonschema
        module = self.transport()
        context = self.context()
        context["evidence"][0]["text"] = "class Alpha\r\n{\r\n    Assert.True(value);\r\n}\r\n"
        context["evidence"].append({"path": "other.cs", "sha256": "sha256:other", "text": "class Beta\n"})
        plan = module.plan_transport(context, phase="inspect", probe=lambda prompt, schema: {
            "request_sha256": canonical_sha(prompt), "truncation_allowed": False})
        batch = plan["batches"][0]
        audit = self.audit(plan, batch)
        reports = list(audit["reports"].values())
        reports[0]["citations"] = [3]
        reports[1]["citations"] = [1]
        validator = jsonschema.Draft202012Validator(module.audit_schema(plan, batch["parts"]))
        self.assertTrue(validator.is_valid(audit))
        for quote in ("Alpha asserts value is true", 0, 5, True):
            with self.subTest(quote=quote):
                changed = deepcopy(audit)
                list(changed["reports"].values())[0]["citations"] = [quote]
                self.assertFalse(validator.is_valid(changed))
        changed = deepcopy(audit)
        list(changed["reports"].values())[1]["citations"] = [3]
        self.assertFalse(validator.is_valid(changed))
        self.assertEqual([{"line": 3, "text": "    Assert.True(value);\r\n"}],
                         module.resolve_citations(batch["parts"][0], reports[0]))
        audit = self.audit(plan, batch)
        list(audit["reports"].values())[0]["citations"] = ["Invented source citation"]
        self.assertTrue(module.audit_errors(plan, batch, audit))

    def test_reference_regex_domains_are_shared_without_weakening_validation(self):
        import jsonschema
        module = self.transport()
        domain = {"type": "string", "pattern": "^(?:" + "|".join("path-" + str(n) for n in range(200)) + ")$"}
        schema = {"type": "object", "properties": {"a": domain, "b": deepcopy(domain)}}
        compact = module.compact_schema(schema)
        self.assertLess(len(json.dumps(compact)), len(json.dumps(schema)))
        self.assertTrue(jsonschema.Draft202012Validator(compact).is_valid({"a": "path-2", "b": "path-3"}))
        self.assertFalse(jsonschema.Draft202012Validator(compact).is_valid({"a": "path-2", "b": "foreign"}))

    def test_repeated_complete_schema_objects_share_all_constraints(self):
        import jsonschema
        module = self.transport()
        shared = {"type": "object", "properties": {"field" + str(n): {"type": "integer", "minimum": n}
                    for n in range(10)}, "required": ["field" + str(n) for n in range(10)],
                  "additionalProperties": False}
        schema = {"type": "object", "properties": {"a": shared, "b": deepcopy(shared)}}
        compact = module.compact_schema(schema, share_objects=True)
        self.assertLess(len(json.dumps(compact)), len(json.dumps(schema)))
        value = {"a": {"field" + str(n): n for n in range(10)}}
        self.assertTrue(jsonschema.Draft202012Validator(compact).is_valid(value))
        value["a"]["field5"] = 4
        self.assertFalse(jsonschema.Draft202012Validator(compact).is_valid(value))

    def test_empty_source_is_delivered_once_and_duplicate_empty_parts_are_rejected(self):
        module = self.transport()
        context = self.context()
        context["evidence"][0]["text"] = ""
        plan = self.plan(context)
        self.assertEqual([], module.plan_errors(context, plan))
        plan["batches"][0]["parts"].append(deepcopy(plan["batches"][0]["parts"][0]))
        self.assertTrue(module.plan_errors(context, plan))

    def test_audit_receipt_must_bind_the_actual_complete_request(self):
        from _planning_skill_common import RUNNER_SCHEMA
        module = self.transport()
        plan = self.plan(self.context())
        batch = plan["batches"][0]
        audit = self.audit(plan, batch)
        execution = {"backend_info": {"schema_version": RUNNER_SCHEMA, "filesystem_scope": "workspace_only",
            "fresh_session_per_invocation": True, "can_read_outside_workspace": False,
            "model": "fixture", "model_tools": []}, "output_sha256": "sha256:output",
            "audit_sha256": canonical_sha(audit), "receipt": {"model": "fixture", "model_tools": [],
                "output_sha256": "sha256:output", "input_integrity": batch["input_report"]}}
        self.assertEqual([], module.audit_execution_errors(batch, audit, execution))
        execution["receipt"]["input_integrity"] = dict(batch["input_report"], request_sha256="sha256:clipped")
        self.assertTrue(module.audit_execution_errors(batch, audit, execution))

    def test_same_sources_in_another_run_reject_old_audit_and_request_receipt(self):
        from _planning_skill_common import RUNNER_SCHEMA
        module = self.transport()
        first = self.context()
        first["input_identity"] = {"run_id": "first", "envelope_sha256": "sha256:first",
                                   "analysis_identity_sha256": "sha256:first-analysis"}
        second = deepcopy(first)
        second["input_identity"] = {"run_id": "second", "envelope_sha256": "sha256:second",
                                    "analysis_identity_sha256": "sha256:second-analysis"}
        old_plan, new_plan = self.plan(first), self.plan(second)
        old_batch, new_batch = old_plan["batches"][0], new_plan["batches"][0]
        old_audit = self.audit(old_plan, old_batch)
        self.assertTrue(module.audit_errors(new_plan, new_batch, old_audit))
        execution = {"backend_info": {"schema_version": RUNNER_SCHEMA, "filesystem_scope": "workspace_only",
            "fresh_session_per_invocation": True, "can_read_outside_workspace": False,
            "model": "fixture", "model_tools": []}, "output_sha256": "sha256:output",
            "audit_sha256": canonical_sha(old_audit), "receipt": {"model": "fixture", "model_tools": [],
                "output_sha256": "sha256:output", "input_integrity": old_batch["input_report"]}}
        self.assertEqual([], module.audit_execution_errors(old_batch, old_audit, execution))
        self.assertTrue(module.audit_execution_errors(new_batch, old_audit, execution))

    def test_conflicts_require_exact_requirement_or_flow_addresses(self):
        module = self.transport()
        plan = self.plan(self.context())
        batch = plan["batches"][0]
        plan["phase"] = "review"
        audit = self.audit(plan, batch)
        row = next(iter(audit["reports"].values()))
        row.update(verdict="conflict", hard_issues=[{"requirement_ids": ["FR-A"], "flow_ids": [], "detail": "Real contradiction"}])
        self.assertEqual([], module.audit_errors(plan, batch, audit))
        row["hard_issues"][0]["requirement_ids"] = ["FOREIGN"]
        self.assertTrue(module.audit_errors(plan, batch, audit))

    def test_inspection_can_surface_hard_conflict_without_review_verdict(self):
        module = self.transport()
        plan = self.plan(self.context())
        batch = plan["batches"][0]
        audit = self.audit(plan, batch)
        next(iter(audit["reports"].values()))["hard_issues"] = [{"requirement_ids": ["FR-A"], "flow_ids": [],
                                                  "detail": "Source-backed mismatch"}]
        self.assertEqual([], module.audit_errors(plan, batch, audit))


if __name__ == "__main__":
    unittest.main()
