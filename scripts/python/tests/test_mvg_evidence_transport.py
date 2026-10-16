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

    def test_lossless_encoding_shares_raw_json_blocks_and_preserves_exact_order(self):
        module = self.transport()
        self.assertTrue(hasattr(module, "lossless_context"), "Versioned lossless model encoding is missing")
        shared = {"lines": ["HEAD\r\n", "中文 MIDDLE  \n", "TAIL\t"], "values": list(range(100))}
        text = json.dumps(shared, ensure_ascii=False, indent=2) + "\r\n  "
        context = {"first": shared, "second": deepcopy(shared), "evidence": [
            {"path": str(n), "text": text, "sha256": module.text_sha(text)} for n in range(8)],
            "reserved": {"$mvg_ref": 0}, "empty": "", "types": [True, 1, False, 0, None],
            "ordered": {"z": 1, "a": 2}, "duplicates": ["same", "same"]}
        encoded = module.lossless_context(context)
        restored = module.restore_lossless_context(encoded)
        self.assertEqual(module.wire_json(context), module.wire_json(restored))
        self.assertLess(len(module.wire_json(encoded)), len(module.wire_json(context)) // 2)
        self.assertEqual(context, restored)

    def test_lossless_encoding_rejects_content_reference_and_identity_pollution(self):
        module = self.transport()
        self.assertTrue(hasattr(module, "lossless_context"), "Versioned lossless model encoding is missing")
        encoded = module.lossless_context({"a": "repeated content " * 50, "b": "repeated content " * 50})
        for mutation in ("content", "reference", "cycle", "extra", "hash", "schema"):
            with self.subTest(mutation=mutation):
                changed = deepcopy(encoded)
                if mutation == "content":
                    changed["shared"][0] = "CORRUPTION"
                elif mutation == "reference":
                    changed["value"] = {"$mvg_ref": len(changed["shared"])}
                elif mutation == "cycle":
                    changed["shared"][0] = {"$mvg_ref": 0}
                elif mutation == "extra":
                    changed["shared"].append("UNREFERENCED")
                elif mutation == "hash":
                    changed["content_sha256"] = "sha256:changed"
                else:
                    changed["schema_version"] = "unknown"
                with self.assertRaisesRegex(ValueError, "mvg_lossless_"):
                    module.restore_lossless_context(changed)

    def test_new_transport_binds_encoding_and_historical_prompt_stays_literal(self):
        module = self.transport()
        plan = module.plan_transport(self.context(), phase="inspect", probe=lambda prompt, schema: {
            "request_sha256": canonical_sha(prompt), "truncation_allowed": False})
        self.assertEqual("newrouge.mvg-complete-evidence-transport.v3", plan["schema_version"])
        self.assertIn("newrouge.mvg-lossless-context.v1", module.audit_prompt(plan, plan["batches"][0]["parts"]))
        changed = deepcopy(plan)
        changed["model_encoding"] = "unknown"
        self.assertTrue(module.plan_errors(self.context(), changed))
        legacy = deepcopy(plan)
        legacy["schema_version"] = "newrouge.mvg-complete-evidence-transport.v1"
        legacy.pop("model_encoding", None)
        legacy_prompt = module.audit_prompt(legacy, legacy["batches"][0]["parts"])
        self.assertNotIn("newrouge.mvg-lossless-context.v1", legacy_prompt)
        self.assertIn("SOURCE PART ", legacy_prompt)

    def test_new_model_source_lines_have_explicit_exact_citation_addresses(self):
        module = self.transport()
        context = self.context()
        context["evidence"][0]["text"] = "HEAD\r\n\r\n1|中文  \nMID\rTAIL\t"
        plan = module.plan_transport(context, phase="review", probe=lambda prompt, schema: {
            "request_sha256": canonical_sha(prompt), "truncation_allowed": False})
        batch = plan["batches"][0]
        encoded = json.loads(module.audit_prompt(plan, batch["parts"]).splitlines()[-1])
        payload = module.restore_lossless_context(encoded)
        source = batch["parts"][0]
        self.assertEqual(source["text"], payload["source_texts"][0]["text"])
        self.assertIn("$mvg_lines", module.wire_json(encoded))
        self.assertIn("relative_line", module.audit_prompt(plan, batch["parts"]))

    def plan(self, context):
        module = self.transport()
        def probe(prompt, schema):
            if len(prompt.encode("utf-8")) > 2400:
                raise ValueError("runner_context_budget_exceeded:fixture")
            return {"request_sha256": canonical_sha(prompt), "truncation_allowed": False}
        return module.plan_transport(context, phase="inspect", probe=probe,
                                     schema_version=module.LEGACY_TRANSPORT_SCHEMA)

    def colocation_context(self):
        module = self.transport()
        shared = json.dumps({"payload": "Exact source payload " * 260}, ensure_ascii=False) + "\r\n"
        context = self.context()
        context["evidence"] = [{"path": path, "sha256": module.text_sha(text), "text": text}
            for path, text in (
                ("first.json", "FIRST 中文\r\n" + shared + "Unique A " * 650 + "  \n"),
                ("middle.txt", "Independent " * 650),
                ("last.json", "LAST\n" + shared + "Unique B " * 650 + "\t"),
                ("empty.txt", ""))]
        context["evidence"].append({"path": "missing.cs", "status": "not_prepared"})
        return context, shared

    def test_v3_colocates_exact_large_blocks_and_keeps_every_path_report(self):
        import jsonschema
        module = self.transport()
        context, shared = self.colocation_context()

        def probe(prompt, schema):
            if len(prompt.encode("utf-8")) + len(module.wire_json(schema).encode("utf-8")) > 16000:
                raise ValueError("runner_context_budget_exceeded:fixture")
            return {"request_sha256": canonical_sha(prompt), "truncation_allowed": False}

        plan = module.plan_transport(context, phase="inspect", probe=probe)
        legacy = module.plan_transport(context, phase="inspect", probe=probe,
            schema_version="newrouge.mvg-complete-evidence-transport.v2")
        self.assertLess(len(plan["batches"]), len(legacy["batches"]))
        self.assertEqual([], module.plan_errors(context, plan))
        self.assertEqual({k: v for k, v in context.items() if k != "evidence"}, plan["core"])
        grouped = [batch for batch in plan["batches"]
                   if sum(item["text"] == shared for item in batch["parts"]) == 2]
        self.assertEqual(1, len(grouped), "Exact duplicate blocks should share one wrapped request")
        batch = grouped[0]
        duplicates = [item for item in batch["parts"] if item["text"] == shared]
        self.assertEqual(["first.json", "last.json"], [item["path"] for item in duplicates])
        self.assertNotEqual(duplicates[0]["part_id"], duplicates[1]["part_id"])
        indexes = [batch["parts"].index(item) for item in duplicates]
        self.assertEqual(indexes[0] + 1, indexes[1])
        for source in context["evidence"]:
            if "text" not in source:
                continue
            pieces = sorted((item for b in plan["batches"] for item in b["parts"]
                             if item["path"] == source["path"]), key=lambda item: item["start"])
            self.assertEqual(source["text"], "".join(item["text"] for item in pieces))
            offset = 0
            for item in pieces:
                self.assertEqual(offset, item["start"])
                self.assertEqual(module.part(source, item["start"], item["end"]), item)
                offset = item["end"]
            self.assertEqual(len(source["text"]), offset)
            if not source["text"]:
                self.assertEqual(1, len(pieces))
        for batch in plan["batches"]:
            payload = module.restore_lossless_context(json.loads(module.audit_prompt(plan, batch["parts"]).splitlines()[-1]))
            self.assertEqual([{"part_id": p["part_id"], "text": p["text"]} for p in batch["parts"]],
                             payload["source_texts"])
        audit = self.audit(plan, grouped[0])
        self.assertEqual([], module.audit_errors(plan, grouped[0], audit))
        audit["reports"].pop(duplicates[1]["part_id"])
        self.assertTrue(module.audit_errors(plan, grouped[0], audit))
        self.assertFalse(jsonschema.Draft202012Validator(module.audit_schema(plan, grouped[0]["parts"])).is_valid(audit))

    def test_v3_checks_original_group_order_and_fragment_boundaries(self):
        module = self.transport()
        context, shared = self.colocation_context()
        plan = module.plan_transport(context, phase="review", probe=lambda prompt, schema: {
            "request_sha256": canonical_sha(prompt), "truncation_allowed": False})
        parts = plan["batches"][0]["parts"]
        self.assertEqual(2, sum(item["text"] == shared for item in parts))
        for mutation in ("missing", "duplicate", "reordered", "file_order", "cross_boundary",
                         "offset", "content", "source_hash", "part_hash", "empty_duplicate"):
            with self.subTest(mutation=mutation):
                changed = deepcopy(plan)
                actual = changed["batches"][0]["parts"]
                index = next(n for n, item in enumerate(actual) if item["text"] == shared)
                if mutation == "missing":
                    actual.pop(index)
                elif mutation == "duplicate":
                    actual.insert(index, deepcopy(actual[index]))
                elif mutation == "reordered":
                    actual[index:index + 2] = reversed(actual[index:index + 2])
                elif mutation == "file_order":
                    actual.sort(key=lambda item: (next(n for n, source in enumerate(context["evidence"])
                                                      if source["path"] == item["path"]), item["start"]))
                elif mutation == "cross_boundary":
                    source = context["evidence"][0]
                    actual[0] = module.part(source, 0, actual[index]["end"])
                    actual.pop(index)
                elif mutation in {"offset", "content", "source_hash"}:
                    item = actual[index]
                    if mutation == "offset":
                        item["start"] += 1
                        item["text"] = item["text"][1:]
                    elif mutation == "content":
                        item["text"] = "X" + item["text"][1:]
                    else:
                        item["source_sha256"] = "sha256:polluted"
                    item["part_id"] = canonical_sha({k: v for k, v in item.items() if k != "part_id"})
                elif mutation == "part_hash":
                    actual[index]["part_id"] = "sha256:polluted"
                else:
                    actual.append(deepcopy(next(item for item in actual if item["path"] == "empty.txt")))
                self.assertTrue(module.plan_errors(context, changed))

    def test_v3_capacity_splits_advance_inside_each_original_fragment(self):
        module = self.transport()
        context, shared = self.colocation_context()
        probes = []

        def probe(prompt, schema):
            probes.append(prompt)
            payload = module.restore_lossless_context(json.loads(prompt.splitlines()[-1]))
            if any(len(item["text"]) > 1200 for item in payload["source_texts"]):
                raise ValueError("runner_context_budget_exceeded:fixture")
            return {"request_sha256": canonical_sha(prompt), "truncation_allowed": False}

        plan = module.plan_transport(context, phase="inspect", probe=probe)
        self.assertEqual([], module.plan_errors(context, plan))
        for batch in plan["batches"]:
            self.assertIn(module.audit_prompt(plan, batch["parts"]), probes)
        actual = [item for batch in plan["batches"] for item in batch["parts"]]
        for source in context["evidence"][:3:2]:
            start = source["text"].index(shared)
            end = start + len(shared)
            self.assertTrue(any(item["path"] == source["path"] and item["start"] == start for item in actual))
            self.assertTrue(any(item["path"] == source["path"] and item["end"] == end for item in actual))
            self.assertFalse(any(item["path"] == source["path"] and
                (item["start"] < start < item["end"] or item["start"] < end < item["end"]) for item in actual))

    def test_v3_uses_exact_text_and_4096_character_threshold(self):
        module = self.transport()
        probe = lambda prompt, schema: {"request_sha256": canonical_sha(prompt), "truncation_allowed": False}
        for size in (4095, 4096):
            with self.subTest(size=size):
                block = json.dumps({"raw": "X" * (size - 10)}, separators=(",", ":"))
                self.assertEqual(size, len(block))
                context = self.context()
                context["evidence"] = [{"path": path, "sha256": "sha256:same-claimed-identity", "text": text}
                    for path, text in (("a", "HEAD\n" + block + "TAIL A"),
                                       ("b", "OTHER\n" + block + "TAIL B"),
                                       ("unique", "Different content"), ("empty", ""))]
                plan = module.plan_transport(context, phase="inspect", probe=probe)
                actual = plan["batches"][0]["parts"]
                self.assertEqual([], module.plan_errors(context, plan))
                if size == 4096:
                    self.assertEqual(2, sum(item["text"] == block for item in actual))
                else:
                    self.assertEqual([module.part(s) for s in context["evidence"]], actual)

    def test_historical_v1_v2_plan_prompt_and_schema_golden_hashes(self):
        module = self.transport()
        goldens = {
            "newrouge.mvg-complete-evidence-transport.v1": (
                "437370de28864265d80fab9a660d2a57e078e7b4aef2c692cb52b7b98e5e8427",
                "235722e1183418ce12e9d823bd47383af8a9e730454bd38cc0ad8d024f808b9e"),
            "newrouge.mvg-complete-evidence-transport.v2": (
                "eab0c0e29ddafc52865750ea3212553d57a9e16c52075e902facb618433a4099",
                "5e0f98231d88e10c65f5461e307825c22b19b1c505a94b3bf1576e8e307249cb")}
        for version, (plan_hash, prompt_hash) in goldens.items():
            with self.subTest(version=version):
                plan = module.plan_transport(self.context(), phase="inspect", schema_version=version,
                    probe=lambda prompt, schema: {"request_sha256": canonical_sha(prompt), "truncation_allowed": False})
                parts = plan["batches"][0]["parts"]
                self.assertEqual("sha256:" + plan_hash, canonical_sha(plan))
                self.assertEqual("sha256:" + prompt_hash, canonical_sha(module.audit_prompt(plan, parts)))
                self.assertEqual("sha256:d881aea9971b51213775d648226eb40dfdf894bc3e739a9774d1eef2b1a59e56",
                                 canonical_sha(module.audit_schema(plan, parts)))
                self.assertEqual([], module.plan_errors(self.context(), plan))

    def test_v3_prefers_longest_raw_block_and_keeps_repeated_offsets_distinct(self):
        module = self.transport()
        block = json.dumps({"outer": {"payload": "Nested raw content " * 300}})
        context = self.context()
        context["evidence"] = [{"path": path, "sha256": module.text_sha(text), "text": text}
            for path, text in (("repeat.json", "FIRST" + block + "GAP" + block + "TAIL"),
                               ("whole-a.json", block), ("whole-b.json", block))]
        plan = module.plan_transport(context, phase="inspect", probe=lambda prompt, schema: {
            "request_sha256": canonical_sha(prompt), "truncation_allowed": False})
        self.assertEqual([], module.plan_errors(context, plan))
        parts = plan["batches"][0]["parts"]
        copies = [item for item in parts if item["text"] == block]
        self.assertEqual(["repeat.json", "repeat.json", "whole-a.json", "whole-b.json"],
                         [item["path"] for item in copies])
        self.assertEqual([5, 5 + len(block) + 3, 0, 0], [item["start"] for item in copies])
        self.assertEqual(4, len({item["part_id"] for item in copies}))
        self.assertEqual(list(range(parts.index(copies[0]), parts.index(copies[0]) + 4)),
                         [parts.index(item) for item in copies])
        self.assertEqual([], module.audit_errors(plan, plan["batches"][0], self.audit(plan, plan["batches"][0])))

    def test_v3_empty_sources_keep_independent_required_reports(self):
        module = self.transport()
        context = self.context()
        context["evidence"] = [{"path": path, "sha256": module.text_sha(""), "text": ""}
                               for path in ("empty-a", "empty-b")]
        plan = module.plan_transport(context, phase="inspect", probe=lambda prompt, schema: {
            "request_sha256": canonical_sha(prompt), "truncation_allowed": False})
        self.assertEqual([], module.plan_errors(context, plan))
        batch = plan["batches"][0]
        self.assertEqual(2, len(batch["parts"]))
        audit = self.audit(plan, batch)
        for row in audit["reports"].values():
            row.update(verdict="context_only", citations=[], facts=[])
        self.assertEqual([], module.audit_errors(plan, batch, audit))
        audit["reports"].pop(batch["parts"][1]["part_id"])
        self.assertTrue(module.audit_errors(plan, batch, audit))

    def test_historical_v1_v2_reject_grouped_order_with_recomputed_parts(self):
        module = self.transport()
        context, shared = self.colocation_context()
        for version in (module.LEGACY_TRANSPORT_SCHEMA, "newrouge.mvg-complete-evidence-transport.v2"):
            with self.subTest(version=version):
                plan = module.plan_transport(context, phase="inspect", schema_version=version,
                    probe=lambda prompt, schema: {"request_sha256": canonical_sha(prompt), "truncation_allowed": False})
                first, _, last = context["evidence"][:3]
                a, b = first["text"].index(shared), last["text"].index(shared)
                plan["batches"][0]["parts"] = [module.part(first, 0, a), module.part(first, a, a + len(shared)),
                    module.part(last, b, b + len(shared)), module.part(first, a + len(shared)),
                    module.part(context["evidence"][1]), module.part(last, 0, b),
                    module.part(last, b + len(shared)), module.part(context["evidence"][3])]
                self.assertTrue(module.plan_errors(context, plan))

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

        plan = module.plan_transport(context, phase="inspect", probe=probe,
                                     schema_version=module.LEGACY_TRANSPORT_SCHEMA)
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
            module.plan_transport(context, phase="inspect", probe=probe,
                                  schema_version=module.LEGACY_TRANSPORT_SCHEMA)

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
