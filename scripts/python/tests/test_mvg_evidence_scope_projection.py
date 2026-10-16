"""Model scope projection retains full frozen sources and conservative boundaries."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _mvg_capability_generation as generation
from _mvg_evidence_transport import model_context, plan_errors, plan_transport, wire_json
from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json


class EvidenceScopeProjectionTests(unittest.TestCase):
    def fixture(self, prepared):
        ref = "logs/ci/chapter5/reconciliation/task-7.json"
        source = prepared / "references" / ref
        doc = {"schema_version": "newrouge.semantic-reconciliation.v1", "task_id": "7",
            "findings": [
                {"finding_type": "source_semantic", "status": "equivalent", "action": "keep",
                 "chapter3_requirement_ids": ["FR-A"], "source_block_ids": ["SB-A"], "rationale": "RELEVANT FULL TEXT"},
                {"finding_type": "source_semantic", "status": "equivalent", "action": "keep",
                 "chapter3_requirement_ids": ["FR-B"], "source_block_ids": ["SB-B"], "rationale": "FOREIGN GLOBAL ROW"},
                {"finding_type": "unknown_future_type", "detail": "UNKNOWN PRESERVE"},
                {"finding_type": "source_semantic", "status": "blocked", "action": "repair",
                 "chapter3_requirement_ids": ["FR-B"], "detail": "GLOBAL HARD CONFLICT PRESERVE"}],
            "topology_edges": [
                {"source_type": "requirement", "source_id": "FR-A", "target_type": "acceptance", "target_id": "AC-A"},
                {"source_type": "acceptance", "source_id": "AC-A", "target_type": "test", "target_id": "test-A"},
                {"source_type": "requirement", "source_id": "FR-B", "target_type": "task", "target_id": "99"},
                {"source_type": "future_type", "source_id": "foreign", "target_type": "future_type", "target_id": "7"}],
            "other_metadata": {"opaque": "KEEP ALL UNKNOWN FIELDS"}}
        atomic_json(source, doc)
        binding = {"path": ref, "sha256": file_sha(source), "required": True,
            "prepared_path": "references/" + ref, "roles": ["chapter5_reconciliation"]}
        envelope = {"run_id": "projection", "chapter5": {"formal_ready": True, "tasks": [
            {"task_id": "7", "reconciliation": deepcopy(binding), "ready": True}]}, "inventory": [binding]}
        atomic_json(prepared / "analysis-index.json", {"analysis_identity_sha256": "sha256:fixture", "input_envelope": envelope})
        atomic_json(prepared / "semantic-requirements.v1.json", {"requirements": [
            {"requirement_id": "FR-A", "source_block_ids": []}]})
        atomic_json(prepared / "task-views/tasks_back.json", [{"taskmaster_id": 7, "semantic_refs": ["FR-A"], "acceptance": []}])
        atomic_json(prepared / "task-master.json", {"master": {"tasks": [{"id": 7, "status": "done"}]}})
        scope = {"capability_id": "CAP-A", "capability": {}, "requirement_ids": ["FR-A"],
            "cumulative_requirement_ids": ["FR-A"]}
        base = {"manifest_candidate": {"flows": []}, "coverage_table": [], "entrypoints": [], "tests": []}
        return ref, source, doc, scope, base

    def test_inline_model_excludes_only_proven_foreign_rows_and_retains_original_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared = Path(directory)
            ref, source, doc, scope, base = self.fixture(prepared)
            original = source.read_bytes()
            context = generation.complete_scope_context(prepared, scope, base)
            row = context["evidence"][0]
            self.assertEqual(json.loads(original), json.loads(row["text"]))
            self.assertEqual(file_sha(source), row["sha256"])
            wire = model_context(context)
            projected = json.loads(wire["evidence"][0]["text"])
            self.assertEqual([doc["findings"][0], doc["findings"][2], doc["findings"][3]], projected["findings"])
            self.assertEqual([doc["topology_edges"][0], doc["topology_edges"][1], doc["topology_edges"][3]], projected["topology_edges"])
            self.assertEqual(doc["other_metadata"], projected["other_metadata"])
            self.assertNotIn("FOREIGN GLOBAL ROW", wire_json(wire))
            self.assertEqual("newrouge.mvg-scoped-evidence.v2", context["evidence_scope_schema"])
            audit = row["model_projection"]
            self.assertEqual("json_projection", audit["citation_space"])
            self.assertEqual("/findings/1", audit["excluded_rows"][0]["json_pointer"])
            self.assertEqual(canonical_sha(doc["findings"][1]), audit["excluded_rows"][0]["sha256"])
            self.assertEqual(original, source.read_bytes())
            self.assertEqual([], generation.evidence_scope_errors(prepared, scope, base, base, context))
            for field in ("text", "model_text", "model_projection"):
                changed = deepcopy(context)
                changed["evidence"][0].pop(field)
                self.assertTrue(generation.evidence_scope_errors(prepared, scope, base, base, changed))

    def test_batched_model_uses_same_projection_and_rejects_lost_or_altered_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared = Path(directory)
            ref, source, doc, scope, base = self.fixture(prepared)
            context = generation.complete_scope_context(prepared, scope, base)
            def probe(prompt, schema):
                return {"request_sha256": canonical_sha(prompt), "truncation_allowed": False}
            plan = plan_transport(context, phase="review", probe=probe)
            text = "".join(part["text"] for batch in plan["batches"] for part in batch["parts"])
            self.assertNotIn("FOREIGN GLOBAL ROW", text)
            self.assertIn("RELEVANT FULL TEXT", text)
            self.assertIn("GLOBAL HARD CONFLICT PRESERVE", text)
            self.assertEqual([], plan_errors(context, plan))
            changed = deepcopy(plan)
            changed["batches"][0]["parts"][0]["text"] += "DRIFT"
            self.assertTrue(plan_errors(context, changed))
            self.assertTrue(plan["inventory"][0]["model_projection"])
            self.assertEqual(len(context["evidence"][0]["text"]), plan["inventory"][0]["source_characters"])

    def test_explicit_full_evidence_and_unknown_findings_shape_are_never_filtered(self):
        for mode in ("explicit", "unknown_shape"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                prepared = Path(directory)
                ref, source, doc, scope, base = self.fixture(prepared)
                index = load_json(prepared / "analysis-index.json")
                if mode == "explicit":
                    index["input_envelope"]["inventory"][0]["roles"].append("explicit_evidence")
                else:
                    doc["findings"] = {"unexpected": "FOREIGN GLOBAL ROW"}
                    atomic_json(source, doc)
                    index["input_envelope"]["inventory"][0]["sha256"] = file_sha(source)
                    index["input_envelope"]["chapter5"]["tasks"][0]["reconciliation"]["sha256"] = file_sha(source)
                atomic_json(prepared / "analysis-index.json", index)
                context = generation.complete_scope_context(prepared, scope, base)
                self.assertEqual(context["evidence"][0]["text"], model_context(context)["evidence"][0]["text"])

    def test_legacy_scoped_context_reconstructs_original_full_source(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared = Path(directory)
            ref, source, doc, scope, base = self.fixture(prepared)
            current = generation.complete_scope_context(prepared, scope, base)
            legacy = generation.complete_scope_context(prepared, scope, base,
                scope_schema="newrouge.mvg-scoped-evidence.v1")
            self.assertNotIn("model_text", legacy["evidence"][0])
            self.assertIn("FOREIGN GLOBAL ROW", model_context(legacy)["evidence"][0]["text"])
            self.assertEqual([], generation.evidence_scope_errors(prepared, scope, base, base, legacy))
            legacy["evidence"][0]["text"] += "DRIFT"
            self.assertTrue(generation.evidence_scope_errors(prepared, scope, base, base, legacy))

    def test_ambiguous_record_ownership_and_cross_scope_boundaries_remain_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            prepared = Path(directory)
            ref, source, doc, scope, base = self.fixture(prepared)
            doc["findings"].extend([
                {"finding_type": "source_semantic", "status": "equivalent", "action": "keep",
                 "chapter3_requirement_ids": ["FR-B"], "future_owner_id": "MAY RELATE"},
                {"finding_type": "source_semantic", "status": "equivalent", "action": "keep",
                 "chapter3_requirement_ids": "FR-B", "detail": "MALFORMED KEEP"},
                {"finding_type": "source_semantic", "status": "equivalent", "action": "keep", "detail": "GLOBAL KEEP"}])
            doc["topology_edges"].extend([
                {"source_type": "task", "source_id": "7", "target_type": "task", "target_id": "99", "relation": "handoff"},
                {"source_type": "task", "source_id": "99", "target_type": "task", "target_id": "100", "relation": "unrelated"}])
            atomic_json(source, doc)
            index = load_json(prepared / "analysis-index.json")
            index["input_envelope"]["inventory"][0]["sha256"] = file_sha(source)
            index["input_envelope"]["chapter5"]["tasks"][0]["reconciliation"]["sha256"] = file_sha(source)
            atomic_json(prepared / "analysis-index.json", index)
            current = generation.complete_scope_context(prepared, scope, base)
            projected = json.loads(model_context(current)["evidence"][0]["text"])
            self.assertTrue(all(row in projected["findings"] for row in doc["findings"][-3:]))
            self.assertIn(doc["topology_edges"][-2], projected["topology_edges"])
            self.assertNotIn(doc["topology_edges"][-1], projected["topology_edges"])


if __name__ == "__main__":
    unittest.main()
