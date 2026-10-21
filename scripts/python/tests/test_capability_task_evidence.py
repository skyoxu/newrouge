"""Lossless evidence, provenance, blinding, and final dispatch selection."""
from __future__ import annotations

import copy
import json
import os
import random
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _capability_task_evidence as codec
import _capability_input_integrity as integrity
import openai_isolated_model_runner as api
import codex_isolated_model_runner as codex
from _planning_skill_common import _write_model_batches, atomic_json, build_blinded_analysis_bundle, canonical_sha, file_sha, load_json


class TaskEvidenceCodecTests(unittest.TestCase):
    def payload(self):
        return {"task_views": {
            "task-views/back.json": [{"id": "B-17", "taskmaster_id": 17, "description": "Same meaning",
                "acceptance": ["Reject invalid route", "Keep state"], "verification": ["Windows assertion"],
                "unknown": {"nested": [], "nullable": None}, "requirement_ids": ["FR-17"]}],
            "task-views/gameplay.json": [{"id": "G-17", "taskmaster_id": 17, "description": "Same meaning",
                "acceptance": ["Show rejection"], "verification": ["Windows assertion"],
                "unknown": {"nested": [], "nullable": None}, "requirement_ids": ["FR-17"]}]},
            "related_evidence": {"master_tasks": [{"id": 17, "status": "active"}],
                "requirements": [{"requirement_id": "FR-17", "statement": "Full requirement", "source_block_ids": ["SB-17"]}],
                "source_blocks": [{"block_id": "SB-17", "raw_text": "Authored Capability boundary and handoff: CAP-MAP"}]},
            "unknown_top_level": {"preserve": True}}

    def test_strict_values_unknown_fields_and_array_order_roundtrip(self):
        payload = self.payload()
        left, right = [rows[0] for rows in payload["task_views"].values()]
        left.update(null=None, empty_string="", empty_list=[], empty_object={}, numeric=1,
                    boolean=True, float_value=1.0, order=[1, "1", None], escaped={"a~/b": [False]})
        right.update(empty_string="", empty_list=[], empty_object={}, numeric="1", boolean=1,
                     float_value=1, order=[None, "1", 1], escaped={"a~/b": [False]})
        packet = codec.compress(payload)
        codec.validate_roundtrip(payload, packet)
        shared = packet["content_objects"]["tasks"]["17"]["shared_fields"]
        self.assertNotIn("null", shared)
        for field in ("numeric", "boolean", "float_value", "order", "acceptance"):
            self.assertNotIn(field, shared)
        self.assertEqual({"nested": [], "nullable": None}, shared["unknown"])
        mapping = codec.expansion_map(payload, packet)
        codec.validate_expansion_map(payload, packet, mapping)
        self.assertEqual(codec.json_value(payload), codec.json_value(codec.expand(packet)))

    def test_deterministic_nested_json_fuzz(self):
        rng = random.Random(1701)
        def value(depth=0):
            atoms = [None, "", 1, 1.0, True, False, "1", "功能性正文", -0.0]
            if depth > 2 or rng.randrange(3) == 0:
                return copy.deepcopy(rng.choice(atoms))
            if rng.randrange(2):
                return [value(depth + 1) for _ in range(rng.randrange(4))]
            return {"field/" + str(i): value(depth + 1) for i in range(rng.randrange(4))}
        for _ in range(100):
            payload = self.payload()
            for rows in payload["task_views"].values():
                rows[0]["unknown_extension"] = value()
            codec.validate_roundtrip(payload, codec.compress(payload))

    def test_corrupt_and_unused_objects_fail_closed(self):
        for mutation in ("value", "extra_view", "collision", "identity", "missing_row"):
            payload = self.payload()
            packet = codec.compress(payload)
            task = packet["content_objects"]["tasks"]["17"]
            if mutation == "value":
                task["shared_fields"]["description"] = "Changed intent"
            elif mutation == "extra_view":
                task["view_specific_fields"]["unknown.json"] = {"id": 17}
            elif mutation == "collision":
                task["view_specific_fields"]["task-views/back.json"]["description"] = "Same meaning"
            elif mutation == "identity":
                task["shared_fields"]["taskmaster_id"] = 18
            else:
                packet["relation_index"]["view_order"]["task-views/back.json"] = []
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                codec.validate_roundtrip(payload, packet)

    def test_expansion_map_requires_all_fields_and_exact_hashes(self):
        payload = self.payload()
        packet = codec.compress(payload)
        mapping = codec.expansion_map(payload, packet)
        mapping["fields"].pop()
        with self.assertRaisesRegex(ValueError, "coverage_mismatch"):
            codec.validate_expansion_map(payload, packet, mapping)
        mapping = codec.expansion_map(payload, packet)
        mapping["fields"][0]["sha256"] = "wrong"
        with self.assertRaises(ValueError):
            codec.validate_expansion_map(payload, packet, mapping)

    def test_partition_is_disjoint_and_conserves_excluded_ids(self):
        codec.validate_partition(["17", "18"], ["17"], ["18"])
        for kept, excluded in ((["17"], []), (["17"], ["17", "18"]), (["17", "17"], ["18"])):
            with self.assertRaises(ValueError):
                codec.validate_partition(["17", "18"], kept, excluded)

    def test_blinding_checks_nested_payload_but_keeps_authored_text(self):
        payload = self.payload()
        codec.assert_blinded(payload)
        for value in ({"arbitrary": [{"capability_refs": ["CAP-OLD"]}]},
                      {"nested": {"schema_version": "newrouge.capabilities.v1", "capabilities": []}}):
            with self.assertRaises(ValueError):
                codec.assert_blinded(value)
        packet = codec.compress(payload)
        links, pointers = codec.declared_relations(payload, {})
        packet["relation_index"]["declared_links"] = links
        packet["source_pointers"] = pointers
        codec.validate_packet(payload, packet, {})
        packet["source_pointers"]["old_answer"] = {"title": "Historical copied answer"}
        with self.assertRaisesRegex(ValueError, "projection_mismatch"):
            codec.validate_packet(payload, packet, {})

    def test_only_declared_relations_and_missing_optional_is_undeclared(self):
        payload = self.payload()
        payload["task_views"]["task-views/back.json"][0]["description"] = "Mentions FR-MISSING and ADR-9999"
        links, pointers = codec.declared_relations(payload, {})
        self.assertFalse(any(row["kind"] == "adr" for row in links))
        self.assertEqual({"adr": {}, "test": {}}, pointers)
        payload["task_views"]["task-views/back.json"][0]["semantic_refs"] = [" FR-17 "]
        links, _ = codec.declared_relations(payload, {})
        self.assertEqual(["FR-17"], next(row["refs"] for row in links if row["field"] == "semantic_refs"))
        codec.validate_roundtrip(payload, codec.compress(payload))
        payload["task_views"]["task-views/back.json"][0]["requirement_ids"].append("FR-MISSING")
        with self.assertRaisesRegex(ValueError, "declared_target_missing"):
            codec.declared_relations(payload, {})

    def test_unknown_schema_version_values_survive_recursive_blinding(self):
        for value in (None, [], {}, {"nested": [1, "1", True]}, ["future", 2]):
            with self.subTest(value=value):
                payload = self.payload()
                for rows in payload["task_views"].values():
                    rows[0]["extension"] = {"schema_version": value}
                packet = codec.compress(payload)
                links, pointers = codec.declared_relations(payload, {})
                packet["relation_index"]["declared_links"] = links
                packet["source_pointers"] = pointers
                codec.validate_packet(payload, packet, {})
                self.assertEqual(codec.json_value(payload), codec.json_value(codec.expand(packet)))
        with self.assertRaisesRegex(ValueError, "unblinded_field"):
            codec.assert_blinded({"schema_version": {"capability_refs": ["CAP-OLD"]}})

    def test_external_refs_are_resolved_by_exact_declared_id_or_path(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "docs/adr").mkdir(parents=True)
            (root / "docs/adr/ADR-0007-test.md").write_text("# Decision", encoding="utf-8")
            (root / "test.cs").write_text("test", encoding="utf-8")
            catalog = codec.freeze_reference_catalog(root, [{"adr_refs": ["ADR-0007", "ADR-0008"],
                                                           "test_refs": ["test.cs", "missing.cs"]}])
            self.assertEqual("valid", catalog["adr"]["ADR-0007"]["status"])
            self.assertEqual("blocking_error", catalog["test"]["missing.cs"]["status"])
            payload = self.payload()
            payload["task_views"]["task-views/back.json"][0]["test_refs"] = ["missing.cs"]
            with self.assertRaisesRegex(ValueError, "declared_target_missing"):
                codec.declared_relations(payload, catalog)

    def test_selection_measures_schema_wrappers_and_requires_both_savings(self):
        raw = "complete raw input"
        selected, metrics = codec.select_smaller(raw, raw + codec.GUIDE, lambda text: text + "SCHEMA" * 10)
        self.assertEqual(raw, selected)
        self.assertEqual("raw", metrics["selected_encoding"])
        self.assertEqual(len((raw + "SCHEMA" * 10).encode()), metrics["measurements"]["raw"]["request_bytes"])


class TaskEvidenceAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.analysis = self.workspace / "analysis-input"
        common = {"taskmaster_id": 17, "description": "Preserve every requirement and acceptance boundary. " * 240,
                  "acceptance": ["Reject invalid route and preserve state"], "requirement_ids": ["FR-17"]}
        self.rows = {"task-views/back.json": [{**common, "id": "B-17"}],
                     "task-views/gameplay.json": [{**common, "id": "G-17", "verification": ["Visible rejection"]}]}
        for path, rows in self.rows.items():
            atomic_json(self.analysis / path, rows)
        atomic_json(self.analysis / "task-master.json", {"master": {"tasks": [{"id": 17, "status": "active"}]}})
        self.ledger = {"blocks": [{"block_id": "SB-17", "raw_text": "Original GDD functional body: CAP-MAP boundary"}]}
        self.semantics = {"requirements": [{"requirement_id": "FR-17", "source_block_ids": ["SB-17"], "statement": "Keep failure observable"}]}
        atomic_json(self.analysis / "source-blocks.v1.json", self.ledger)
        atomic_json(self.analysis / "semantic-requirements.v1.json", self.semantics)
        atomic_json(self.analysis / codec.CATALOG, {"adr": {}, "test": {}})
        self.batches = _write_model_batches(self.analysis, ledger=self.ledger, semantics=self.semantics, char_budget=1000)
        self.refresh()
        self.prompt = self.workspace / "prompt.txt"
        self.prompt.write_text("Generate candidate", encoding="utf-8")
        self.output = self.workspace / "candidate.json"

    def refresh(self, mode="lossless-v1"):
        index = {"task_view_encoding": mode, "files": {p.relative_to(self.analysis).as_posix(): file_sha(p)
                 for p in self.analysis.rglob("*") if p.is_file() and p.name != "analysis-index.json"}}
        index["analysis_identity_sha256"] = canonical_sha(index)
        atomic_json(self.analysis / "analysis-index.json", index)

    def build(self):
        return codec.build_task_request(self.workspace, base="shared context", rows=self.rows, label="task-views-001",
            measure_text=lambda text: api._measured_request_text(text, {"type": "object"}))

    def test_selected_packet_is_self_contained_and_audits_never_enter_model_workspace(self):
        text = self.build()
        self.assertIn("LOSSLESS TASK EVIDENCE", text)
        self.assertNotIn("COMPLETE TASK-VIEW ROWS", text)
        self.assertIn(self.ledger["blocks"][0]["raw_text"], text)
        audit = self.workspace / codec.AUDIT_DIR / "task-views-001"
        packet, original, mapping = [load_json(audit / name) for name in ("packet.json", "authoritative-input.json", "expansion-map.json")]
        codec.validate_roundtrip(original, packet)
        codec.validate_expansion_map(original, packet, mapping, workspace=self.workspace)
        changed = copy.deepcopy(mapping)
        changed["fields"][0]["source"]["json_pointer"] = "/999/id"
        with self.assertRaisesRegex(ValueError, "expansion_source_mismatch"):
            codec.validate_expansion_map(original, packet, changed, workspace=self.workspace)
        base, _ = api.batched_workspace_parts(self.workspace, prompt_path=self.prompt, output_path=self.output)
        self.assertNotIn("expansion-map", base)
        self.assertNotIn(codec.CATALOG, "\n".join(str(path) for path in api._safe_files(self.workspace, set())))
        self.assertNotIn("authoritative-input.json", base)
        self.assertEqual(text, self.build())

    def test_grouping_keeps_both_views_with_same_task_and_preserves_exclusions(self):
        for rel in self.rows:
            rows = self.rows[rel] + [{"id": "OLD", "taskmaster_id": 18, "description": "RETIRED_BODY"}]
            atomic_json(self.analysis / rel, rows)
        atomic_json(self.analysis / "task-master.json", {"master": {"tasks": [{"id": 17}, {"id": 18, "status": "retired"}]}})
        self.refresh()
        chunks = integrity.task_view_payload_chunks(self.workspace, char_budget=1000)
        self.assertEqual(1, len(chunks))
        self.assertEqual(set(self.rows), set(chunks[0]))
        _, coverage = integrity.task_view_batch_rows(self.workspace, self.batches)
        self.assertEqual(2, sum(len(row["excluded_rows"]) for row in coverage["views"].values()))
        self.assertNotIn("RETIRED_BODY", json.dumps(chunks))

    def test_prepare_setting_is_frozen_and_raw_remains_default(self):
        self.refresh("raw")
        with patch.dict(os.environ, {codec.MODE_ENV: "lossless-v1"}):
            self.assertEqual("raw", codec.workspace_encoding(self.workspace))
            self.assertIn("COMPLETE TASK-VIEW ROWS", self.build())
        self.assertFalse((self.workspace / codec.AUDIT_DIR).exists())

    def test_multiple_chunks_reconstruct_original_view_order_and_all_values(self):
        # Views deliberately disagree on task order; a task also exists in only
        # one view. Recombination must use source positions, not dispatch order.
        orders = {"task-views/back.json": [19, 17, 18, 20],
                  "task-views/gameplay.json": [20, 18, 19, 17, 21]}
        self.rows = {rel: [{"id": rel + "#" + str(key), "taskmaster_id": key,
            "description": "Shared description with full functional meaning. " * 40,
            "acceptance": [rel, str(key)], "requirement_ids": ["FR-17"],
            "extension": {"schema_version": {}, "ordered": [None, "", False, 0, 0.0]}}
            for key in order] for rel, order in orders.items()}
        for rel, rows in self.rows.items():
            atomic_json(self.analysis / rel, rows)
        atomic_json(self.analysis / "task-master.json", {"master": {"tasks": [{"id": key} for key in range(17, 22)]}})
        self.refresh()
        chunks = integrity.task_view_payload_chunks(self.workspace, char_budget=4500)
        self.assertGreater(len(chunks), 1)
        dispatch_by_task, reconstructed = {}, {rel: {} for rel in self.rows}
        for ordinal, rows in enumerate(chunks, 1):
            label = f"task-views-{ordinal:03d}"
            codec.build_task_request(self.workspace, base="shared context", rows=rows, label=label,
                                     measure_text=lambda text: text)
            audit = self.workspace / codec.AUDIT_DIR / label
            packet, original, mapping = [load_json(audit / name) for name in
                                        ("packet.json", "authoritative-input.json", "expansion-map.json")]
            codec.validate_expansion_map(original, packet, mapping, workspace=self.workspace)
            expanded = codec.expand(packet)
            for rel, items in expanded["task_views"].items():
                for index, row in enumerate(items):
                    key = codec.identity(row)
                    self.assertEqual(ordinal, dispatch_by_task.setdefault(key, ordinal))
                    input_pointer = f"/task_views/{codec.pointer_part(rel)}/{index}/taskmaster_id"
                    source = next(entry["source"] for entry in mapping["fields"]
                                  if entry["input_pointer"] == input_pointer)
                    position = int(source["original_json_pointer"].split("/")[1])
                    self.assertNotIn(position, reconstructed[rel])
                    reconstructed[rel][position] = row
        actual = {rel: [items[position] for position in sorted(items)] for rel, items in reconstructed.items()}
        self.assertEqual(codec.json_value(self.rows), codec.json_value(actual))

    def test_missing_ref_blocks_both_runners_before_any_dispatch(self):
        self.rows["task-views/back.json"][0]["test_refs"] = ["missing.cs"]
        atomic_json(self.analysis / "task-views/back.json", self.rows["task-views/back.json"])
        self.refresh()
        with patch.object(codex, "_run_codex_request") as codex_call, patch.object(api, "_openai_client") as client:
            with self.assertRaisesRegex(ValueError, "declared_target_missing"):
                codex._run_batched_codex(self.workspace, self.prompt, self.output, executable="fixture",
                    timeout_sec=30, max_bytes=1048576, max_input_tokens=96000, preflight=True)
            with self.assertRaisesRegex(ValueError, "declared_target_missing"):
                api._run_batched_session(workspace=self.workspace, prompt_path=self.prompt, output_path=self.output,
                    timeout_sec=30, max_bytes=1048576)
            codex_call.assert_not_called()
            client.assert_not_called()

    def test_catalog_drift_and_nested_answer_are_not_raw_fallbacks(self):
        atomic_json(self.analysis / codec.CATALOG, {"adr": {}, "test": {}, "changed": True})
        with self.assertRaisesRegex(ValueError, "catalog_missing_or_changed"):
            self.build()
        self.refresh()
        self.rows["task-views/back.json"][0]["extension"] = {"capability_ids": ["CAP-OLD"]}
        with self.assertRaisesRegex(ValueError, "unblinded_field"):
            self.build()

    def test_explicit_dependency_cycles_and_direct_sources_have_complete_bodies(self):
        self.semantics["requirements"][0]["dependency_ids"] = ["FR-18"]
        self.semantics["requirements"].append({"requirement_id": "FR-18", "dependency_ids": ["FR-17"],
                                             "source_block_ids": ["SB-18"], "statement": "Related outcome"})
        self.ledger["blocks"].extend([{"block_id": "SB-18", "raw_text": "DEPENDENCY_SOURCE_BODY"},
                                      {"block_id": "SB-DIRECT", "raw_text": "DIRECT_SOURCE_BODY"}])
        self.rows["task-views/back.json"][0]["source_block_ids"] = ["SB-DIRECT"]
        atomic_json(self.analysis / "task-views/back.json", self.rows["task-views/back.json"])
        atomic_json(self.analysis / "semantic-requirements.v1.json", self.semantics)
        atomic_json(self.analysis / "source-blocks.v1.json", self.ledger)
        self.batches = _write_model_batches(self.analysis, ledger=self.ledger, semantics=self.semantics, char_budget=1000)
        self.refresh()
        text = self.build()
        self.assertIn("DEPENDENCY_SOURCE_BODY", text)
        self.assertIn("DIRECT_SOURCE_BODY", text)
        packet = load_json(self.workspace / codec.AUDIT_DIR / "task-views-001/packet.json")
        body = codec.expand(packet)["related_evidence"]
        self.assertEqual(["FR-17", "FR-18"], [row["requirement_id"] for row in body["requirements"]])
        self.assertEqual(["FR-18"], body["requirements"][0]["dependency_ids"])

    def test_codex_preflight_uses_packet_and_is_stable_on_repeat(self):
        with patch.object(codex, "_run_codex_request") as dispatch:
            first = codex._run_batched_codex(self.workspace, self.prompt, self.output, executable="fixture",
                timeout_sec=30, max_bytes=1048576, max_input_tokens=96000, preflight=True)
            second = codex._run_batched_codex(self.workspace, self.prompt, self.output, executable="fixture",
                timeout_sec=30, max_bytes=1048576, max_input_tokens=96000, preflight=True)
            dispatch.assert_not_called()
        self.assertEqual(first, second)
        self.assertEqual("lossless-v1", load_json(self.workspace / codec.AUDIT_DIR / "task-views-001/metrics.json")["selected_encoding"])

    def test_api_dispatch_uses_encoded_task_evidence_and_original_output_ids(self):
        sent = []
        def respond(**kwargs):
            sent.append(kwargs["prompt"])
            if "LOSSLESS TASK EVIDENCE" in kwargs["prompt"]:
                self.assertNotIn("COMPLETE TASK-VIEW ROWS", kwargs["prompt"])
                self.assertEqual(set(self.rows), {key.split("#")[0] for key in
                    kwargs["output_schema"]["properties"]["task_view_analyses"]["items"]["properties"]["task_view_key"]["enum"]})
                raise ValueError("runner_input_too_large:probe_stopped_after_task_dispatch")
            value = {"schema_version": "newrouge.capability-batch-analysis.v1", "batch_index": 1,
                "source_block_analyses": [{"source_block_id": "SB-17", "summary": "Boundary", "boundary_signals": ["Map owns routing"]}],
                "requirement_analyses": [{"requirement_id": "FR-17", "intent": "Observable failure", "user_outcome": "Keep state",
                    "boundary_signals": ["Rejection"], "source_block_ids": ["SB-17"]}], "task_view_analyses": []}
            return SimpleNamespace(id="fixture", output_text=json.dumps(value), status="completed")
        with patch.object(api, "_openai_client", return_value=object()), patch.object(api, "_response", side_effect=respond):
            with self.assertRaisesRegex(ValueError, "probe_stopped_after_task_dispatch"):
                api._run_batched_session(workspace=self.workspace, prompt_path=self.prompt, output_path=self.output,
                    timeout_sec=30, max_bytes=1048576)
        self.assertEqual(2, len(sent))

    def test_prepare_freezes_mode_catalog_authority_hashes_and_blinding(self):
        atomic_json(self.workspace / ".taskmaster/tasks/tasks.json", {"master": {"tasks": [{"id": 17}]}})
        manifest = self.workspace / "manifest.json"
        atomic_json(manifest, {"schema_version": "chapter3.source-manifest.v1", "sources": []})
        atomic_json(self.analysis / "source-blocks.v1.json", {**self.ledger, "schema_version": "newrouge.source-blocks.v1"})
        atomic_json(self.analysis / "semantic-requirements.v1.json", {**self.semantics, "schema_version": "newrouge.semantic-requirements.v1"})
        test_path = self.workspace / "test.cs"
        test_path.write_text("explicit test target", encoding="utf-8")
        self.rows["task-views/back.json"][0].update(test_refs=["test.cs"], nested={"capability_refs": ["CAP-OLD"], "keep": None})
        atomic_json(self.analysis / "task-views/back.json", self.rows["task-views/back.json"])
        output = self.workspace / "prepared/analysis-input"
        with patch.dict(os.environ, {codec.MODE_ENV: "lossless-v1"}):
            index = build_blinded_analysis_bundle(self.workspace, output, source_manifest_path=manifest,
                ledger_path=self.analysis / "source-blocks.v1.json", semantics_path=self.analysis / "semantic-requirements.v1.json",
                task_view_paths=[self.analysis / rel for rel in self.rows], readiness_summary={"tasks": []})
        self.assertEqual("lossless-v1", index["task_view_encoding"])
        self.assertIn("test.cs", index["authority_inputs"])
        self.assertEqual(file_sha(output / codec.CATALOG), index["files"][codec.CATALOG])
        row = load_json(output / "task-views/back.json")[0]
        self.assertEqual({"keep": None}, row["nested"])
        self.assertEqual("lossless-v1", codec.workspace_encoding(output.parent))

    def test_source_body_boolean_to_number_change_fails_even_with_updated_batch_hash(self):
        self.ledger["blocks"][0]["extension"] = True
        atomic_json(self.analysis / "source-blocks.v1.json", self.ledger)
        self.batches = _write_model_batches(self.analysis, ledger=self.ledger, semantics=self.semantics, char_budget=1000)
        row = self.batches["batches"][0]
        path = self.analysis / row["path"]
        payload = load_json(path)
        payload["blocks"][0]["extension"] = 1
        atomic_json(path, payload)
        row["sha256"] = file_sha(path)
        atomic_json(self.analysis / "model-batches/batch-index.json", self.batches)
        self.refresh()
        with self.assertRaisesRegex(ValueError, "source_block_body_mismatch"):
            integrity.validate_batches(self.workspace, self.batches)


if __name__ == "__main__":
    unittest.main()
