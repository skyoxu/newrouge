"""Exact structured JSON delivery, request-local sharing and source citations."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class StructuredContextTests(unittest.TestCase):
    def codec(self):
        try:
            return importlib.import_module("_mvg_structured_context")
        except ImportError:
            self.fail("Self-contained structured JSON transmission is missing")

    def test_nested_snapshots_share_values_across_formatting_without_losing_bytes(self):
        codec = self.codec()
        shared = {"acceptance": ["Complete 中文 requirement " + str(n) for n in range(60)],
                  "types": [True, 1, None, False, 0], "ordered": {"z": 1, "a": 2}}
        texts = [json.dumps({"payload": shared}, ensure_ascii=False, indent=2) + "\n",
                 "\ufeff" + json.dumps({"fingerprint": {"payload": shared}}, ensure_ascii=False,
                                      indent=4).replace("\n", "\r\n") + "\r\n  ",
                 json.dumps({"payload": shared}, ensure_ascii=True, separators=(",", ":"))]
        original = {"core": shared, "sources": texts, "empty": "", "literal": {"$mvg_json_text": 42}}
        encoded = codec.structured_context(original)
        self.assertEqual(json.dumps(original, ensure_ascii=False),
                         json.dumps(codec.restore_structured_context(encoded), ensure_ascii=False))
        self.assertLess(len(json.dumps(encoded, ensure_ascii=False)), len(json.dumps(original, ensure_ascii=False)) // 2)
        self.assertIn("$mvg_json_text", json.dumps(encoded))

    def test_unusual_json_spelling_duplicate_keys_and_non_json_remain_literal(self):
        codec = self.codec()
        texts = ['{"a":1,"a":2}', '{"x":1e+03,"y":-0}', '{"x":NaN}',
                 'HEAD\r\n\r\nTAIL  ', '{"x":"\\u0061"}', '{"a":1,\n  "b":2}']
        for text in texts:
            with self.subTest(text=text):
                self.assertIsNone(codec.json_text_view(text))
                self.assertEqual(text, codec.restore_structured_context(codec.structured_context(text)))

    def test_corrupt_layout_content_hash_definitions_and_reserved_literals_are_rejected(self):
        codec = self.codec()
        text = json.dumps({"a": ["full requirement " * 40], "b": 1}, indent=2) + "\n"
        original = {"a": text, "b": text, "literal": {"$mvg_json_literal": [True, 1]}}
        encoded = codec.structured_context(original)
        self.assertEqual(original, codec.restore_structured_context(encoded))
        for field in ("schema_version", "content_sha256"):
            changed = deepcopy(encoded)
            changed[field] = "corrupt"
            with self.assertRaises(ValueError):
                codec.restore_structured_context(changed)
        changed = deepcopy(encoded)
        changed["encoded"]["shared"].append("unused")
        with self.assertRaises(ValueError):
            codec.restore_structured_context(changed)

    def test_json_pointer_citations_resolve_exact_original_subtrees(self):
        codec = self.codec()
        text = '\ufeff{\r\n  "a/b": {\r\n    "~x": [true, 1, "中文"]\r\n  },\r\n  "empty": {}\r\n}\r\n'
        for pointer, expected in (("/a~1b/~0x/0", "true"), ("/a~1b/~0x/1", "1"),
                                  ("/a~1b/~0x/2", '"中文"'), ("/empty", "{}")):
            quote = codec.resolve_json_pointer(text, pointer)
            self.assertEqual(expected, quote["text"])
            self.assertEqual(pointer, quote["json_pointer"])
            self.assertEqual(expected, text[quote["start"]:quote["end"]])
        for pointer in ("/absent", "/a~1b/~0x/01", "/a~1b/~0x/-1", "/a~2b", "paraphrase"):
            with self.subTest(pointer=pointer), self.assertRaises(ValueError):
                codec.resolve_json_pointer(text, pointer)


class StructuredTransportTests(unittest.TestCase):
    def context(self):
        import _mvg_evidence_transport as transport
        payload = {"acceptance": ["Full acceptance " + str(n) for n in range(80)], "unknown": [True, 1, None]}
        texts = [json.dumps({"payload": payload, "task_id": 1}, indent=2) + "\n",
                 json.dumps({"fingerprint": {"payload": payload}, "task_id": 1}, separators=(",", ":")) + "\n"]
        return {"evidence_scope_schema": "newrouge.mvg-scoped-evidence.v3",
            "scope": {"capability_id": "CAP-A", "requirement_ids": ["FR-A"]},
            "requirements": [{"requirement_id": "FR-A", "statement": "Complete authority"}],
            "task_views": [{"taskmaster_id": 1, "acceptance": payload["acceptance"],
                            "test_refs": ["a.json", "b.json"]}],
            "source_blocks": [{"text": "Full source"}],
            "evidence": [{"path": path, "sha256": transport.text_sha(text), "text": text}
                         for path, text in zip(("a.json", "b.json"), texts)]}

    def plan(self, phase="inspect"):
        import _mvg_evidence_transport as transport
        from _planning_skill_common import canonical_sha
        return transport.plan_transport(self.context(), phase=phase, probe=lambda prompt, schema: {
            "request_sha256": canonical_sha([prompt, schema]), "truncation_allowed": False})

    def test_new_scope_transmits_self_contained_structured_sources_in_both_phases(self):
        import _mvg_evidence_transport as transport
        for phase in ("inspect", "review"):
            plan = self.plan(phase)
            self.assertEqual("newrouge.mvg-complete-evidence-transport.v4", plan["schema_version"])
            self.assertEqual([], transport.plan_errors(self.context(), plan))
            for batch in plan["batches"]:
                prompt = transport.audit_prompt(plan, batch["parts"])
                self.assertIn("JSON Pointer", prompt)
                payload = transport.restore_lossless_context(json.loads(prompt.splitlines()[-1]))
                self.assertEqual([part["text"] for part in batch["parts"]],
                                 [row["text"] for row in payload["source_texts"]])

    def test_json_citation_schema_and_gate_require_actual_source_addresses(self):
        import _mvg_evidence_transport as transport
        from _planning_skill_common import canonical_sha
        from jsonschema import validate, ValidationError
        plan = self.plan()
        batch = plan["batches"][0]
        audit = {"schema_version": transport.AUDIT_SCHEMA, "phase": "inspect",
                 "context_sha256": plan["context_sha256"], "batch_sha256": canonical_sha(batch["parts"]),
                 "reports": {p["part_id"]: {"part_id": p["part_id"], "rationale": "Direct requirement evidence",
                    "verdict": "relevant", "requirement_ids": ["FR-A"], "facts": ["Source contains task ID"],
                    "citations": ["/task_id"], "hard_issues": []} for p in batch["parts"]}}
        validate(audit, transport.audit_schema(plan, batch["parts"]))
        self.assertEqual([], transport.audit_errors(plan, batch, audit))
        quote = transport.resolve_citations(batch["parts"][0], {"citations": ["/payload/unknown/0"]}, json_pointers=True)[0]
        self.assertEqual("true", quote["text"])
        changed = deepcopy(audit)
        next(iter(changed["reports"].values()))["citations"] = ["/nonexistent"]
        self.assertIn("evidence_audit_citation_not_in_source", transport.audit_errors(plan, batch, changed))
        next(iter(changed["reports"].values()))["citations"] = ["not a pointer"]
        with self.assertRaises(ValidationError):
            validate(changed, transport.audit_schema(plan, batch["parts"]))

    def test_explicit_historical_transport_retains_original_codec_and_line_gate(self):
        import _mvg_evidence_transport as transport
        from _planning_skill_common import canonical_sha
        context = self.context()
        plan = transport.plan_transport(context, phase="inspect", schema_version=transport.TRANSPORT_SCHEMA,
            probe=lambda prompt, schema: {"request_sha256": canonical_sha(prompt), "truncation_allowed": False})
        prompt = transport.audit_prompt(plan, plan["batches"][0]["parts"])
        encoded = json.loads(prompt.splitlines()[-1])
        self.assertEqual("newrouge.mvg-lossless-context.v1", encoded["schema_version"])
        self.assertEqual([], transport.plan_errors(context, plan))

    def test_structured_inspection_keeps_global_paths_but_only_current_provenance_details(self):
        import _mvg_evidence_transport as transport
        from _planning_skill_common import canonical_sha
        plan = self.plan()
        parts = plan["batches"][0]["parts"][:1]
        payload = transport.restore_lossless_context(json.loads(transport.audit_prompt(plan, parts).splitlines()[-1]))
        self.assertEqual([row for row in plan["inventory"] if row["path"] == parts[0]["path"]], payload["inventory"])
        self.assertEqual([{key: row[key] for key in ("path", "status")} for row in plan["inventory"]],
                         payload["global_evidence_boundary"])
        self.assertEqual(canonical_sha(plan["inventory"]), payload["complete_inventory_sha256"])
        self.assertEqual(2, len(plan["inventory"]), "Complete provenance stays in the checked proof")

    def test_capacity_fragments_remain_self_contained_exact_and_order_checked(self):
        import _mvg_evidence_transport as transport
        from _planning_skill_common import canonical_sha
        context = self.context()

        def probe(prompt, schema):
            payload = transport.restore_lossless_context(json.loads(prompt.splitlines()[-1]))
            if sum(len(row["text"]) for row in payload["source_texts"]) > 500:
                raise ValueError("runner_context_budget_exceeded:fixture")
            return {"request_sha256": canonical_sha([prompt, schema]), "truncation_allowed": False}

        plan = transport.plan_transport(context, phase="review", probe=probe)
        self.assertGreater(len(plan["batches"]), 1)
        self.assertEqual([], transport.plan_errors(context, plan))
        parts = []
        for batch in plan["batches"]:
            payload = transport.restore_lossless_context(json.loads(transport.audit_prompt(plan, batch["parts"]).splitlines()[-1]))
            self.assertEqual([row["text"] for row in batch["parts"]],
                             [row["text"] for row in payload["source_texts"]])
            self.assertTrue(all(row["citation_format"] == "line_number" for row in payload["parts"]))
            parts.extend(batch["parts"])
        for source in context["evidence"]:
            self.assertEqual(source["text"], "".join(row["text"] for row in parts if row["path"] == source["path"]))
        changed = deepcopy(plan)
        changed["batches"][:2] = reversed(changed["batches"][:2])
        self.assertTrue(transport.plan_errors(context, changed))
        changed = deepcopy(plan)
        changed["batches"].pop()
        self.assertTrue(transport.plan_errors(context, changed))

    def test_structured_review_proof_revalidates_citations_receipts_and_hard_conflicts(self):
        import _mvg_evidence_transport as transport
        from _planning_skill_common import canonical_sha, RUNNER_SCHEMA
        context = self.context()
        context.update(accepted_proposal={"notes": ["accepted"]}, proposal={"notes": ["new"]})
        plan = transport.plan_transport(context, phase="review", probe=lambda prompt, schema: {
            "request_sha256": canonical_sha([prompt, schema]), "truncation_allowed": False})
        audits = []
        for batch in plan["batches"]:
            audit = {"schema_version": transport.AUDIT_SCHEMA, "phase": "review",
                "context_sha256": plan["context_sha256"], "batch_sha256": canonical_sha(batch["parts"]),
                "reports": {p["part_id"]: {"part_id": p["part_id"], "rationale": "Checked full source",
                    "verdict": "relevant", "requirement_ids": ["FR-A"], "facts": ["Complete task evidence"],
                    "citations": ["/task_id"], "hard_issues": []} for p in batch["parts"]}}
            execution = {"backend_info": {"schema_version": RUNNER_SCHEMA, "filesystem_scope": "workspace_only",
                "fresh_session_per_invocation": True, "can_read_outside_workspace": False,
                "model": "fixture", "model_tools": []}, "output_sha256": "sha256:fixture",
                "audit_sha256": canonical_sha(audit), "receipt": {"model": "fixture", "model_tools": [],
                "input_integrity": batch["input_report"]}}
            audits.append({"audit": audit, "execution": execution})
        proof = {"context": context, "plan": plan, "audits": audits}

        def errors(value):
            return transport.transport_proof_errors(value, scope=context["scope"],
                base=context["accepted_proposal"], proposal=context["proposal"])

        self.assertEqual([], errors(proof))
        for mutation in ("citation", "receipt", "conflict"):
            with self.subTest(mutation=mutation):
                changed = deepcopy(proof)
                record = changed["audits"][0]
                report = next(iter(record["audit"]["reports"].values()))
                if mutation == "citation":
                    report["citations"] = ["/not_present"]
                elif mutation == "receipt":
                    record["execution"]["receipt"]["model_tools"] = ["unexpected"]
                else:
                    report.update(verdict="conflict", hard_issues=[{"requirement_ids": ["FR-A"],
                        "flow_ids": [], "detail": "Source-backed hard conflict"}])
                record["execution"]["audit_sha256"] = canonical_sha(record["audit"])
                self.assertTrue(errors(changed))


if __name__ == "__main__":
    unittest.main()
