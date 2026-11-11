"""3B assembly/capacity tests use an explicit read-only audit seam, NOT real audit PASS.

Synthetic proof tests separately exercise the real verifier and cannot grant
admission. CLI-shell Python and OS path probes are separate from runner dispatch.
"""
import base64
import contextlib
from copy import deepcopy
import ctypes
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import _b_route_planning_input as planning
import _b_route_source_audit as audit
import _b_route_sources as sources
import _b_route_codec as codec
from _mvg_evidence_transport import restore_lossless_context
import plan_capabilities
import plan_mvg
import test_b_route_source_audit as audit_tests


class PlanningInputTests(unittest.TestCase):
    def setUp(self):
        # The real fixed producer paths retain their Windows 259-unit gate.
        # Keep the fixture root short instead of bypassing that production gate.
        self.temp = tempfile.TemporaryDirectory(prefix="b")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.put("docs/source.md", b"# Rule\r\n\r\nPreserve order.  \r\n")
        self.put("docs/empty.md", b"")
        self.put("docs/constraint.md", b"Do not change existing IDs.  \r\n")
        self.put("rules.py", b"RULE = 1\n")
        self.put("logs/ci/fixture/proof.json", b'{"original":"historical batch"}\r\n')
        self.contract = {"schema_version": planning.CONTRACT, "input_stage": "3b",
            "audit_ref": "logs/ci/fixture/report.json", "scope": {"scope_id": "scope", "kind": "all", "ids": []},
            "constraints": [{"path": "docs/constraint.md", "format": "text"}], "contexts": [],
            "limits": {"max_bytes": 1048576, "max_input_tokens": 96000, "reserved_tokens": 200}}
        self.source_paths = ["docs/source.md", "docs/empty.md"]
        self.put("contract.json", self.contract)
        seam = patch.object(audit, "verify_current_proof", side_effect=self.proof)
        self.verify = seam.start()
        self.addCleanup(seam.stop)
        rules = patch.object(planning, "rules_identity", side_effect=lambda root: {
            "rules": planning.RULES, "bytes": codec.raw_digest((root / "rules.py").read_bytes()),
            "codec_version": codec.CODEC_VERSION, "schema": codec.canonical_digest(planning.output_schema())})
        rules.start()
        self.addCleanup(rules.stop)

    def put(self, path, value):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value if isinstance(value, bytes) else (json.dumps(value, ensure_ascii=False) + "\n").encode("utf-8"))
        return target

    def proof(self, obs, ref, *, scope_id):
        self.assertEqual(scope_id, "scope")
        obs.read("logs/ci/fixture/proof.json")
        obs.watch(["docs/*.md"])
        files = []
        blocks = []
        for ordinal, path in enumerate(self.source_paths, 1):
            raw = obs.read(path)
            files.append({"path": path, "raw_digest": codec.raw_digest(raw), "raw_base64": base64.b64encode(raw).decode(), "text": raw.decode("utf-8")})
            blocks.append({"block_id": "B" + str(ordinal), "source_path": path, "text": raw.decode("utf-8")})
        return {"report": {"scope_id": "scope", "execution_complete": True, "independent_audit": True,
                    "evidence_class": "real_model", "planning_eligible": True, "semantic_blockers": [],
                    "fixture_notice": "EXPLICIT ASSEMBLY SEAM; NOT REAL AUDIT EVIDENCE"},
            "bundle": {"files": files, "ledger": {"blocks": blocks}, "manifest": {"sources": [{"path": p} for p in self.source_paths]},
                "accounting": {"source_accounting": [{"block_id": b["block_id"], "obligation": "cross-file ordering"} for b in blocks],
                               "cross_batch": {"from": "B1", "to": "B2", "unknown_nested": {"keep": [1, 2, 3]}}},
                "proposals": {"proposals": [{"proposal_id": "proposal:keep-original", "prior_requirement_ids": ["FR-EXISTING"]}]},
                "candidate": {"historical_batch_id": "ORIGINAL-BATCH-1"}, "unresolved": []},
            "identity": {"original_runner": "retained"}, "comparison": {"findings": []},
            "extractions": [{"obligations": [{"kind": "handoff", "full_text": "Keep both source obligations."}]}],
            "steps": [{"name": "original-batch-identity"}]}

    def prepare(self, run="r1", *, contract=None):
        if contract is not None:
            self.put("contract.json", contract)
        with patch.object(subprocess, "run", side_effect=AssertionError("No runner subprocess allowed")), \
             patch.object(audit, "run_isolated_model", side_effect=AssertionError("No model dispatch allowed")):
            return planning.prepare(self.root, run_id=run, planning_contract="contract.json")

    def frozen(self, result):
        self.assertEqual(result["status"], "prepared", result)
        return planning.load_prepared(self.root, result["resume_ref"])

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.root.rglob("*") if p.is_file()}

    def test_zero_task_complete_bytes_unknown_fields_and_read_only_reuse(self):
        object_value = {"taskmaster_id": "15", "capability_ids": ["CAP-ORIGINAL"], "extensions": {"new": ["x", {"deep": True}]}}
        self.put("reuse/task.json", object_value)
        contract = deepcopy(self.contract)
        contract["contexts"] = [{"kind": "task", "path": "reuse/task.json", "format": "json", "required": True, "absence": None},
            {"kind": "implementation", "path": "Game.Core/missing.cs", "format": "text", "required": False,
             "absence": {"reason": "No implementation exists at this declared location."}}]
        result = self.prepare(contract=contract)
        frozen = self.frozen(result)
        self.assertEqual(frozen["inputs"]["contexts"][0]["value"], object_value)
        self.assertEqual(frozen["inputs"]["contexts"][0]["value"]["taskmaster_id"], "15")
        self.assertTrue(result["reconstruction"]["complete"])
        self.assertFalse((self.root / ".taskmaster").exists())
        self.assertFalse(list(self.root.rglob("run.json")))
        self.assertFalse(list(self.root.rglob("budget.json")))
        for row in frozen["inputs"]["constraints"]:
            self.assertEqual(base64.b64decode(row["raw_base64"]), (self.root / row["path"]).read_bytes())
        before = self.snapshot()
        repeated = self.prepare()
        self.assertEqual(repeated, result)
        self.assertEqual(before, self.snapshot())
        self.put(".taskmaster/tasks/tasks.json", b'{"irrelevant_status":"changed"}\n')
        self.put(".git/HEAD", b"unrelated-commit\n")
        before = self.snapshot()
        self.assertEqual(self.prepare(), result)
        self.assertEqual(before, self.snapshot())

    def test_writes_are_only_new_exclusive_planning_logs(self):
        before = self.snapshot()
        result = self.prepare()
        self.assertEqual(result["model_dispatch_count"], 0)
        after = self.snapshot()
        for path, value in before.items():
            self.assertEqual(after[path], value)
        self.assertTrue(all("/b-route-planning-input/" in path for path in set(after) - set(before)))

    def test_no_implicit_task_or_readiness_reads(self):
        reader = sources.Observations.read
        reads = []
        def guarded(obs, path, **kwargs):
            self.assertNotIn(".taskmaster", path)
            self.assertNotIn("readiness", path)
            reads.append(path)
            return reader(obs, path, **kwargs)
        with patch.object(sources.Observations, "read", guarded), \
             patch("_planning_scope.round_scope", side_effect=AssertionError("No legacy scope")), \
             patch.object(plan_capabilities, "_readiness_summary", side_effect=AssertionError("No readiness")), \
             patch.object(plan_mvg, "_prepare_impl", side_effect=AssertionError("No legacy MVG prepare")):
            result = self.prepare()
        self.assertEqual(result["status"], "prepared")
        self.assertIn("docs/source.md", reads)

    def test_contract_rejects_unknown_categories_formats_and_malformed_values(self):
        cases = []
        for key, value in (("schema_version", "unknown"), ("input_stage", "legacy"), ("constraints", [])):
            contract = deepcopy(self.contract)
            contract[key] = value
            cases.append(contract)
        for field, value in (("kind", "unknown"), ("format", "binary"), ("required", "false"), ("path", "../escape.json"), ("path", "C:/outside.json")):
            row = {"kind": "task", "path": "reuse.json", "required": True, "format": "json", "absence": None}
            row[field] = value
            contract = deepcopy(self.contract)
            contract["contexts"] = [row]
            cases.append(contract)
        for index, contract in enumerate(cases):
            result = self.prepare("invalid" + str(index), contract=contract)
            self.assertEqual(result["status"], "blocked", result)
            self.assertTrue(result["diagnostics"][0]["resume_ref"])

    def test_missing_required_empty_constraint_bad_json_and_utf8_fail_closed(self):
        for index, data in enumerate((b"", b"  \r\n", b"\xff")):
            self.put("docs/constraint.md", data)
            self.assertEqual(self.prepare("constraint" + str(index))["status"], "blocked")
        self.put("docs/constraint.md", b"Required constraint\r\n")
        for index, data in enumerate((b'{"a":{"x":1,"x":2}}', b'{', b'"\\ud800"', b"\xff")):
            self.put("reuse.json", data)
            contract = deepcopy(self.contract)
            contract["contexts"] = [{"kind": "shared_capability", "path": "reuse.json", "required": True, "format": "json", "absence": None}]
            self.assertEqual(self.prepare("json" + str(index), contract=contract)["status"], "blocked")
        contract["contexts"][0]["path"] = "missing.json"
        self.assertEqual(self.prepare("missing", contract=contract)["status"], "blocked")

    def test_optional_absence_is_explicit_verified_and_bound(self):
        contract = deepcopy(self.contract)
        row = {"kind": "implementation", "path": "optional.cs", "required": False, "format": "text", "absence": {"reason": "Absent implementation"}}
        contract["contexts"] = [row]
        result = self.prepare(contract=contract)
        self.frozen(result)
        self.put("optional.cs", b"public class Existing {}\r\n")
        blocked = self.prepare()
        self.assertEqual(blocked["status"], "blocked")
        contract["contexts"][0]["absence"] = None
        new = self.prepare(contract=contract)
        self.assertEqual(new["status"], "prepared")
        self.assertNotEqual(new["input_identity"], result["input_identity"])
        self.assertIn("optional.cs", new["invalidated_dependencies"][0]["changed_dependencies"])

    def test_related_changes_have_new_identity_and_precise_invalidation(self):
        first = self.prepare()
        old = self.snapshot()
        self.put("docs/constraint.md", b"Updated constraint  \r\n")
        changed = self.prepare()
        self.assertEqual(changed["status"], "prepared")
        self.assertNotEqual(first["input_identity"], changed["input_identity"])
        self.assertIn("docs/constraint.md", changed["invalidated_dependencies"][0]["changed_dependencies"])
        for path, value in old.items():
            if "/b-route-planning-input/" in path:
                self.assertEqual(self.snapshot()[path], value)
        self.put("rules.py", b"RULE = 2\n")
        rules = self.prepare()
        self.assertEqual(rules["status"], "prepared")
        self.assertTrue(any("planning-rules/tools/runtime/schema" in row["changed_dependencies"] for row in rules["invalidated_dependencies"]))

    def test_source_glob_addition_changes_identity_without_git_head_dependency(self):
        first = self.prepare()
        self.put("docs/extra.md", b"New glob member.\r\n")
        changed = self.prepare()
        self.assertNotEqual(first["input_identity"], changed["input_identity"])
        self.assertIn("source-glob-membership", changed["invalidated_dependencies"][0]["changed_dependencies"])

    def test_contract_raw_bytes_and_output_schema_participate_in_identity(self):
        first = self.prepare()
        target = self.root / "contract.json"
        target.write_bytes(target.read_bytes() + b" \r\n")
        raw_change = self.prepare()
        self.assertNotEqual(first["input_identity"], raw_change["input_identity"])
        self.assertIn("contract.json", raw_change["invalidated_dependencies"][0]["changed_dependencies"])
        original = planning.output_schema()
        changed_schema = deepcopy(original)
        changed_schema["description"] = "Changed result-related delivery rule"
        with patch.object(planning, "output_schema", return_value=changed_schema):
            changed = self.prepare()
        self.assertEqual(changed["status"], "prepared")
        self.assertNotEqual(raw_change["input_identity"], changed["input_identity"])
        self.assertTrue(any("planning-rules/tools/runtime/schema" in row.get("changed_dependencies", [])
                            for row in changed["invalidated_dependencies"]))

    def test_corrupt_or_partial_completed_event_is_not_repaired(self):
        result = self.prepare()
        target = self.root / result["output_ref"] / "prepared.json"
        target.write_bytes(b"{broken original completion")
        corrupted = target.read_bytes()
        blocked = self.prepare()
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(target.read_bytes(), corrupted)
        self.assertIn("/failures/", blocked["output_ref"])
        self.assertNotEqual(result["output_ref"], blocked["output_ref"])

    def test_terminal_write_failure_stays_partial_and_reports_resume(self):
        writer = sources.write
        def fail_event(path, value):
            if path.name == "event.json":
                raise OSError("Injected terminal write failure")
            return writer(path, value)
        with patch.object(sources, "write", side_effect=fail_event):
            partial = self.prepare()
        self.assertEqual(partial["status"], "blocked")
        self.assertEqual(partial["termination_reason"], "partial_write")
        self.assertTrue(partial["resume_ref"])
        saved = json.loads((self.root / partial["resume_ref"]).read_bytes())
        self.assertEqual((saved["status"], saved["exit_code"]), ("blocked", 1))
        self.assertNotEqual(partial["resume_ref"], partial["partial_ref"] + "/report.json")
        target = self.root / partial["output_ref"] / "report.json"
        original = target.read_bytes()
        blocked = self.prepare()
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(original, target.read_bytes())
        self.assertIn("/failures/", blocked["output_ref"])

    def test_terminal_and_diagnostic_write_failures_have_no_success_resume(self):
        writer = sources.write
        def fail_terminal_and_diagnostic(path, value):
            if path.name == "event.json" or ("failures" in path.parts and path.name == "report.json"):
                raise OSError(32, "Windows-style file sharing failure", str(path))
            return writer(path, value)
        with patch.object(sources, "write", side_effect=fail_terminal_and_diagnostic):
            partial = self.prepare()
        self.assertEqual((partial["status"], partial["termination_reason"]), ("blocked", "partial_write"))
        self.assertIsNone(partial["resume_ref"])
        self.assertTrue((self.root / partial["partial_ref"]).is_dir())
        self.assertTrue(all(row["resume_ref"] is None for row in partial["diagnostics"]))

    def test_colocated_repeated_long_blocks_reconstruct_same_and_cross_files(self):
        x, y = "x" * 5000 + "\n", "y" * 5000 + "\n"
        cases = (("same", {"reuse/a.txt": "head\n" + x + "middle\n" + x + "tail\n"}),
                 ("cross", {"reuse/a.txt": "a\n" + x + y + "a-tail\n",
                            "reuse/b.txt": "b\n" + y + x + "b-tail\n"}))
        for name, files in cases:
            contract = deepcopy(self.contract)
            for path, text in files.items():
                self.put(path, text.encode("utf-8"))
                contract["contexts"].append({"kind": "implementation", "path": path,
                    "required": True, "format": "text", "absence": None})
            frozen = self.frozen(self.prepare(name, contract=contract))
            plan = frozen["transport"]
            arrivals = [[p["start"] for b in plan["batches"] for p in b["parts"] if p["path"] == path] for path in files]
            self.assertTrue(any(offsets != sorted(offsets) for offsets in arrivals), "Exercise actual colocation reordering")
            for path, text in files.items():
                row = next(r for r in plan["reconstruction"]["objects"] if r["path"] == path)
                self.assertEqual(row["raw_digest"], codec.raw_digest(text.encode("utf-8")))
            duplicate = deepcopy(plan)
            duplicate["batches"][0]["parts"].append(deepcopy(duplicate["batches"][0]["parts"][0]))
            with self.assertRaises(codec.CodecError):
                planning.reconstruction(frozen["inputs"], duplicate)

    def test_proof_bytes_repository_prefix_is_literal_and_archives_remain_exact(self):
        self.put("proof-bytes/source.md", b"Literal source, not base64.  \r\n")
        self.source_paths.append("proof-bytes/source.md")
        raw = b"\x00\xffOriginal binary proof\r\n"
        self.put("logs/ci/fixture/proof.json", raw)
        self.put("proof-bytes/context.txt", b"Literal context, not base64.  \r\n")
        contract = deepcopy(self.contract)
        contract["contexts"] = [{"kind": "implementation", "path": "proof-bytes/context.txt", "format": "text", "required": True, "absence": None}]
        frozen = self.frozen(self.prepare(contract=contract))
        rows = {r["path"]: r for r in frozen["transport"]["reconstruction"]["objects"]}
        for path in ("proof-bytes/source.md", "proof-bytes/context.txt"):
            self.assertEqual(rows[path]["raw_digest"], codec.raw_digest((self.root / path).read_bytes()))
        self.assertFalse(any(r["path"].startswith(planning._ARCHIVE_PREFIX) for r in frozen["inputs"]["evidence"]))
        archived = next(r for r in frozen["inputs"]["raw_proof_inventory"] if r["path"] == "logs/ci/fixture/proof.json")
        self.assertEqual(archived["raw_digest"], codec.raw_digest(raw))
        self.assertEqual(archived["byte_count"], len(raw))
        prefix = (self.root / frozen["resume_ref"]).parent
        original = next(r for r in json.loads((prefix / "raw-index.json").read_bytes()) if r["path"] == archived["path"])
        self.assertEqual((prefix / original["archive"]).read_bytes(), raw)

    def test_large_execution_archive_is_fully_bound_locally_without_spending_model_capacity(self):
        # Explicit assembly seam, never real audit qualification. The business
        # originals remain complete; a repeated CLI log is not a new source.
        raw = b"NON_SEMANTIC_CLI_LOG_" * 110000
        self.assertGreater(len(raw), self.contract["limits"]["max_bytes"])
        self.put("logs/ci/fixture/proof.json", raw)
        contract = deepcopy(self.contract)
        contract["limits"]["max_input_tokens"] = 30000
        result = self.prepare("large-host-proof", contract=contract)
        frozen = self.frozen(result)
        self.assertEqual(len(frozen["transport"]["batches"]), 1)
        inputs = frozen["inputs"]
        self.assertIn("host-verified-archive.v1", inputs["delivery"]["raw_proof_delivery"])
        self.assertEqual(inputs["dependencies"]["files"]["logs/ci/fixture/proof.json"], codec.raw_digest(raw))
        entry = next(r for r in inputs["raw_proof_inventory"] if r["path"] == "logs/ci/fixture/proof.json")
        self.assertEqual((entry["raw_digest"], entry["byte_count"]), (codec.raw_digest(raw), len(raw)))
        draft = {"schema_version": planning.DRAFT, "input_identity": frozen["input_identity"],
            "stage": "batch", "ordinal": 1, "parent_draft_identities": [],
            "content": {"fixture_notice": "Offline capacity forecast, not a model output"}}
        request = planning.build_request(frozen, previous_drafts=[draft])
        value = json.loads(request["payload"])
        restored = restore_lossless_context(value["input"]["core"])
        self.assertEqual(restored, frozen["transport"]["core"])
        self.assertEqual(restored["global_proof"], inputs["global_proof"])
        self.assertLessEqual(request["measurement"]["input_token_estimate"] + contract["limits"]["reserved_tokens"], 30000)
        self.assertNotIn("NON_SEMANTIC_CLI_LOG_", request["payload"])
        for source in inputs["evidence"]:
            actual = "".join(p["text"] for p in value["input"]["parts"] if p["path"] == source["path"])
            self.assertEqual(actual, source["text"])
        prefix = (self.root / frozen["resume_ref"]).parent
        indexed = next(r for r in json.loads((prefix / "raw-index.json").read_bytes()) if r["path"] == entry["path"])
        archive = prefix / indexed["archive"]
        self.assertEqual(archive.read_bytes(), raw)
        archive.write_bytes(raw[:-1] + b"!")
        with self.assertRaises(codec.CodecError):
            planning.load_prepared(self.root, result["resume_ref"], revalidate=False)

    def test_historical_inline_archive_format_still_replays_original_bytes(self):
        raw = b"\x00\xffOriginal historical proof\r\n"
        self.put("logs/ci/fixture/proof.json", raw)
        assemble = planning.assemble
        def historical_assembly(obs, reference):
            inputs = assemble(obs, reference)
            inputs["delivery"].pop("raw_proof_delivery")
            inputs["delivery"].pop("core_encoding")
            inputs["evidence"].append({"path": planning._ARCHIVE_PREFIX + "logs/ci/fixture/proof.json",
                "sha256": codec.raw_digest(raw), "text": base64.b64encode(raw).decode("ascii")})
            return inputs
        with patch.object(planning, "assemble", side_effect=historical_assembly):
            report = self.prepare("historical-inline")
        self.assertEqual(report["status"], "prepared", report)
        before = self.snapshot()
        historical = planning.load_prepared(self.root, report["resume_ref"], revalidate=False)
        archived = next(row for row in historical["inputs"]["evidence"] if row["path"].startswith(planning._ARCHIVE_PREFIX))
        self.assertEqual(base64.b64decode(archived["text"]), raw)
        self.assertEqual(before, self.snapshot())

    def test_lossless_core_preserves_unknown_fields_reserved_keys_types_and_order(self):
        original = self.proof
        extension = {"$mvg_ref": 12, "unknown": [True, 1, "1", None, {"tail": "Original.  \r\n"}]}
        def with_extension(*args, **kwargs):
            value = original(*args, **kwargs)
            value["identity"]["opaque_extension"] = deepcopy(extension)
            return value
        with patch.object(audit, "verify_current_proof", side_effect=with_extension):
            frozen = self.frozen(self.prepare("lossless-core"))
            request = json.loads(planning.build_request(frozen, batch_ordinal=1)["payload"])
        self.assertEqual(request["input"]["core_encoding"], planning.MODEL_ENCODING)
        restored = restore_lossless_context(request["input"]["core"])
        self.assertEqual(codec.canonical_digest(restored), codec.canonical_digest(frozen["transport"]["core"]))
        self.assertEqual(restored["global_proof"]["identity"]["opaque_extension"], extension)

    def test_rules_and_audit_identity_drift_during_batching_block_publication(self):
        pack = planning.plan_batches
        def change_rules(inputs):
            plan = pack(inputs)
            self.put("rules.py", b"RULE = 2\n")
            return plan
        with patch.object(planning, "plan_batches", side_effect=change_rules):
            blocked = self.prepare("rules-during-pack")
        self.assertEqual(blocked["status"], "blocked")
        self.assertIn("planning-rules/tools/runtime/schema", json.dumps(blocked))
        changed = [False]
        def audited(*args, **kwargs):
            proof = self.proof(*args, **kwargs)
            proof["identity"]["original_runner"] = "changed" if changed[0] else "original"
            return proof
        def change_audit(inputs):
            plan = pack(inputs)
            changed[0] = True
            return plan
        self.verify.side_effect = audited
        with patch.object(planning, "plan_batches", side_effect=change_audit):
            blocked = self.prepare("audit-during-pack")
        self.assertEqual(blocked["status"], "blocked")
        self.assertIn("unchanged current audit identity", json.dumps(blocked))

    def test_current_read_only_validation_rechecks_rules_after_capacity_work(self):
        first = self.prepare()
        capacity = planning._verify_current_capacity
        def drift(frozen):
            capacity(frozen)
            self.put("rules.py", b"RULE = 2\n")
        with patch.object(planning, "_verify_current_capacity", side_effect=drift):
            with self.assertRaises(codec.CodecError):
                planning.load_prepared(self.root, first["resume_ref"])

    def test_historical_load_ignores_current_counter_but_current_consumption_does_not(self):
        first = self.prepare()
        frozen = self.frozen(first)
        before = self.snapshot()
        counter = planning.measured
        def changed_counter(payload, inputs):
            report = counter(payload, inputs)
            report["input_token_estimate"] += 1
            return report
        with patch.object(planning, "measured", side_effect=changed_counter) as measured:
            planning.load_prepared(self.root, first["resume_ref"], revalidate=False)
            measured.assert_not_called()
            with self.assertRaises(codec.CodecError):
                planning.load_prepared(self.root, first["resume_ref"])
            with self.assertRaises(codec.CodecError):
                planning.build_request(frozen, batch_ordinal=1)
            rejected = self.prepare()
            self.assertEqual(rejected["status"], "blocked")
            self.assertEqual(rejected["invalidated_dependencies"][0]["prepared_ref"], first["resume_ref"])
            self.put("docs/constraint.md", b"Changed current constraint\r\n")
            changed = self.prepare()
            self.assertEqual(changed["status"], "prepared")
            old = next(r for r in changed["invalidated_dependencies"] if r["prepared_ref"] == first["resume_ref"])
            self.assertIn("docs/constraint.md", old["changed_dependencies"])
            self.assertNotIn("reason", old)
        for path, value in before.items():
            if "/b-route-planning-input/" in path:
                self.assertEqual(self.snapshot()[path], value)

    def test_rejected_source_and_audit_drift_keep_verified_previous_refs(self):
        first = self.prepare()
        original = {p: p.read_bytes() for p in (self.root / first["output_ref"]).rglob("*") if p.is_file()}
        self.put("docs/source.md", b"Changed source\r\n")
        cases = (("source", "docs/source.md", "old source", "changed source"),
                 ("audit", "audit-ref", "current tools", {"reason": "related_audit_tool_drift", "changed_dependencies": ["runner.py"]}))
        for name, entity, expected, actual in cases:
            self.verify.side_effect = codec.CodecError(codec.Diagnostic(codec.ReasonCode.INPUT_STALE,
                codec.Stage.CONTENT, entity, expected, actual))
            blocked = self.prepare()
            self.assertEqual(blocked["status"], "blocked")
            self.assertNotIn("input_identity", blocked)
            invalidated = blocked["invalidated_dependencies"][0]
            self.assertEqual(invalidated["prepared_ref"], first["resume_ref"])
            self.assertEqual(invalidated["input_identity"], first["input_identity"])
            self.assertIn("docs/source.md", invalidated["changed_dependencies"])
            if name == "audit":
                self.assertIn("runner.py", invalidated["changed_dependencies"])
            self.assertIn("synthesis", invalidated["affected"])
        for path, raw in original.items():
            self.assertEqual(path.read_bytes(), raw)

    def test_blocking_or_synthetic_seam_claim_never_becomes_eligible(self):
        original = self.proof
        for index, change in enumerate(("synthetic", "findings", "unresolved", "incomplete")):
            def modified(*args, **kwargs):
                proof = original(*args, **kwargs)
                if change == "synthetic":
                    proof["report"]["evidence_class"] = "synthetic"
                elif change == "findings":
                    proof["comparison"]["findings"] = [{"severity": "blocking", "reason": "Original semantic omission"}]
                elif change == "unresolved":
                    proof["bundle"]["unresolved"] = [{"reason": "Original unresolved accounting"}]
                else:
                    proof["report"]["execution_complete"] = False
                return proof
            self.verify.side_effect = modified
            result = self.prepare("blocked" + str(index))
            self.assertEqual(result["status"], "blocked")
            self.assertFalse(result["formal_adoption"])

    def graph(self, *, unknown=False):
        self.put("docs/unrelated.md", b"Unrelated full source.\n")
        self.put("docs/dependency.md", b"Dependency original source.\n")
        self.source_paths += ["docs/unrelated.md", "docs/dependency.md", "docs/relations.json"]
        self.put("docs/relations.json", {"planning_relations": {"schema_version": planning.RELATIONS,
            "dependency_coverage": "complete", "entities": [
                {"kind": "capability", "id": "CAP-ORIGINAL", "source_paths": ["docs/source.md"], "source_block_ids": ["B1"],
                 "depends_on": [{"kind": "flow", "id": "FLOW-MISSING" if unknown else "FLOW-ORIGINAL"}]},
                {"kind": "flow", "id": "FLOW-ORIGINAL", "source_paths": ["docs/dependency.md"], "source_block_ids": [], "depends_on": []}]},
            "unknown_nested_field": {"preserve": [1, 2]}})
        contract = deepcopy(self.contract)
        contract["scope"] = {"scope_id": "scope", "kind": "capability", "ids": ["CAP-ORIGINAL"]}
        return contract

    def test_governed_closure_follows_cross_file_dependency_and_keeps_global_proof(self):
        frozen = self.frozen(self.prepare(contract=self.graph()))
        closure = frozen["inputs"]["closure"]
        self.assertEqual(closure["mode"], "governed_transitive_closure")
        self.assertEqual(closure["source_paths"], ["docs/source.md", "docs/dependency.md", "docs/relations.json"])
        request = json.loads(planning.build_request(frozen, batch_ordinal=1)["payload"])
        restored_core = restore_lossless_context(request["input"]["core"])
        self.assertIn("docs/unrelated.md", json.dumps(restored_core["global_proof"]))
        self.assertEqual(restored_core["global_proof"]["candidate"]["historical_batch_id"], "ORIGINAL-BATCH-1")
        self.assertEqual(len(closure["entities"]), 2)

    def test_unknown_dependency_and_untrusted_caller_context_expand_full_scope(self):
        contract = self.graph(unknown=True)
        frozen = self.frozen(self.prepare(contract=contract))
        self.assertEqual(frozen["inputs"]["closure"]["source_paths"], self.source_paths)
        self.assertEqual(frozen["inputs"]["closure"]["mode"], "full_audit")
        graph = json.loads((self.root / "docs/relations.json").read_bytes())
        graph["planning_relations"]["entities"][0]["new_dependency_field"] = ["unknown"]
        self.put("docs/relations.json", graph)
        self.assertEqual(self.frozen(self.prepare("unknown-field"))["inputs"]["closure"]["mode"], "full_audit")

    def test_array_and_object_relation_kinds_preserve_original_and_expand_scope(self):
        contract = self.graph()
        original = json.loads((self.root / "docs/relations.json").read_bytes())
        for index, (dependency, kind) in enumerate(((False, []), (False, {}), (True, []), (True, {}))):
            value = deepcopy(original)
            node = value["planning_relations"]["entities"][0]
            (node["depends_on"][0] if dependency else node)["kind"] = kind
            self.put("docs/relations.json", value)
            frozen = self.frozen(self.prepare("unknown-kind" + str(index), contract=contract))
            closure = frozen["inputs"]["closure"]
            self.assertEqual(closure["mode"], "full_audit")
            self.assertEqual(closure["source_paths"], self.source_paths)
            self.assertEqual(closure["relation_evidence"][0]["value"], value["planning_relations"])

    def test_long_json_is_losslessly_split_and_actual_drafts_are_all_retained(self):
        large = {"id": "CAP-ORIGINAL", "unknown_nested": {"long": "value  \r\n" * 8000}, "tail": [True, None]}
        self.put("reuse.json", large)
        contract = deepcopy(self.contract)
        contract["contexts"] = [{"kind": "shared_capability", "path": "reuse.json", "format": "json", "required": True, "absence": None}]
        contract["limits"].update(max_bytes=20000, max_input_tokens=30000)
        frozen = self.frozen(self.prepare(contract=contract))
        self.assertGreater(len(frozen["transport"]["batches"]), 1)
        self.assertEqual(frozen["inputs"]["contexts"][0]["value"], large)
        drafts = []
        for ordinal in range(1, len(frozen["transport"]["batches"]) + 1):
            if ordinal in (2, 3):
                successor = planning.prepare_successor(self.root, frozen["resume_ref"], batch_ordinal=ordinal, previous_drafts=drafts)
                self.assertEqual(successor["status"], "ready", successor)
                saved = json.loads((self.root / successor["resume_ref"]).with_name("request.json").read_bytes())
                sent = json.loads(saved["payload"])["input"]["prior_drafts"]
                self.assertEqual([r["value"] for r in sent], drafts)
                self.assertEqual([r["identity"] for r in sent], [codec.canonical_digest(d) for d in drafts])
                self.assertEqual(saved["measurement"], planning.measured(saved["payload"], frozen["inputs"]))
                self.assertEqual(saved["complete_request_bytes"], len(saved["payload"].encode("utf-8")))
                self.assertEqual(saved["measurement"]["request_bytes"], saved["complete_request_bytes"])
            drafts.append({"schema_version": planning.DRAFT, "input_identity": frozen["input_identity"], "stage": "batch", "ordinal": ordinal,
                "parent_draft_identities": [codec.canonical_digest(row) for row in drafts], "content": {"unknown": "draft " + str(ordinal)}})
        # Full originals recur in synthesis. This intentionally stops when they
        # cannot fit; batch summaries never substitute for the original object.
        with self.assertRaises(planning.CapacityBlocked) as complete:
            planning.build_request(frozen, previous_drafts=drafts)
        request = complete.exception.measurement
        self.assertEqual([row["value"] for row in json.loads(request["payload"])["input"]["prior_drafts"]], drafts)
        self.assertIn("reuse.json", request["payload"])
        drafts[-1]["content"]["large"] = "full original draft" * 5000
        with self.assertRaises(planning.CapacityBlocked) as caught:
            planning.build_request(frozen, previous_drafts=drafts)
        self.assertEqual(caught.exception.resume_ref, frozen["resume_ref"])
        self.assertIn(drafts[-1]["content"]["large"], caught.exception.measurement["payload"])
        self.assertEqual(caught.exception.measurement["model_dispatch_count"], 0)
        before = {p: p.read_bytes() for p in (self.root / frozen["resume_ref"]).parent.rglob("*") if p.is_file()}
        stopped = planning.prepare_successor(self.root, frozen["resume_ref"], previous_drafts=drafts)
        self.assertEqual(stopped["status"], "blocked")
        self.assertEqual(stopped["reason_code"], "budget_exhausted")
        self.assertTrue((self.root / stopped["resume_ref"]).is_file())
        self.assertEqual(json.loads((self.root / stopped["resume_ref"]).with_name("drafts.json").read_bytes()), drafts)
        for path, raw in before.items():
            self.assertEqual(path.read_bytes(), raw)

    def test_synthesis_complete_actual_draft_and_original_request_measurement(self):
        frozen = self.frozen(self.prepare())
        draft = {"schema_version": planning.DRAFT, "input_identity": frozen["input_identity"], "stage": "batch", "ordinal": 1,
                 "parent_draft_identities": [], "content": {"original_id": "CAP-ORIGINAL", "unknown": {"keep": True}}}
        request = planning.build_request(frozen, previous_drafts=[draft])
        payload = json.loads(request["payload"])
        self.assertEqual(payload["input"]["prior_drafts"][0]["value"], draft)
        self.assertTrue(payload["input"]["parts"])
        self.assertEqual(request["measurement"]["request_bytes"], len(request["payload"].encode("utf-8")))
        result = planning.prepare_successor(self.root, frozen["resume_ref"], previous_drafts=[draft])
        self.assertEqual(result["status"], "ready")
        self.assertEqual(result["model_dispatch_count"], 0)

    def test_successor_windows_style_persistence_failures_are_structured_and_keep_drafts(self):
        frozen = self.frozen(self.prepare())
        draft = {"schema_version": planning.DRAFT, "input_identity": frozen["input_identity"], "stage": "batch", "ordinal": 1,
                 "parent_draft_identities": [], "content": {"complete": "Original draft  \r\n", "unknown": {"keep": True}}}
        original = {p: p.read_bytes() for p in (self.root / frozen["resume_ref"]).parent.rglob("*") if p.is_file()}
        writer, directory = sources.write, planning.new_directory
        for target in ("directory", "drafts.json", "request.json", "report.json", "event.json"):
            def fail_write(path, value):
                if "successors" in path.parts and path.name == target:
                    raise OSError(32, "Windows-style file sharing failure", str(path))
                return writer(path, value)
            def fail_directory(root, relative):
                if "/successors/" in relative and target == "directory":
                    raise OSError(5, "Windows-style access denied", str(root / relative))
                return directory(root, relative)
            with patch.object(sources, "write", side_effect=fail_write), \
                 patch.object(planning, "new_directory", side_effect=fail_directory):
                stopped = planning.prepare_successor(self.root, frozen["resume_ref"], previous_drafts=[draft])
            self.assertEqual((stopped["status"], stopped["termination_reason"]), ("blocked", "partial_write"), target)
            saved = json.loads((self.root / stopped["resume_ref"]).read_bytes())
            self.assertEqual(saved["status"], "blocked")
            self.assertIn("/successors/", stopped["partial_ref"])
            self.assertEqual(json.loads((self.root / stopped["resume_ref"]).with_name("drafts.json").read_bytes()), [draft])
            if target in {"request.json", "report.json", "event.json"}:
                request = json.loads((self.root / stopped["resume_ref"]).with_name("request.json").read_bytes())
                self.assertEqual(json.loads(request["payload"])["input"]["prior_drafts"][0]["value"], draft)
            for path, raw in original.items():
                self.assertEqual(path.read_bytes(), raw)

    def test_indivisible_global_core_capacity_blocks_with_resume(self):
        contract = deepcopy(self.contract)
        contract["limits"]["max_bytes"] = 100
        blocked = self.prepare(contract=contract)
        self.assertEqual(blocked["status"], "blocked")
        self.assertEqual(blocked["diagnostics"][0]["reason_code"], "budget_exhausted")
        self.assertTrue((self.root / blocked["resume_ref"]).is_file())
        self.assertTrue((self.root / blocked["output_ref"] / "inputs.json").is_file())

    def test_load_revalidates_declared_context_and_artifacts_read_only(self):
        first = self.prepare()
        before = self.snapshot()
        planning.load_prepared(self.root, first["resume_ref"])
        self.assertEqual(before, self.snapshot())
        self.put("docs/source.md", b"Changed source bytes.\n")
        with self.assertRaises(codec.CodecError):
            planning.load_prepared(self.root, first["resume_ref"])

    def test_both_direct_cli_prepare_route_before_legacy_gates(self):
        for module in (plan_capabilities, plan_mvg):
            with patch.object(module, "prepare", side_effect=AssertionError("Legacy prepare forbidden")), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                code = module.main(["--repo-root", str(self.root), "prepare", "--run-id", module.__name__,
                    "--input-stage", "3b", "--planning-contract", "contract.json"])
            self.assertEqual(code, 0, output.getvalue())
            self.assertEqual(json.loads(output.getvalue())["input_stage"], "3b")

    def test_3b_rejects_task_and_legacy_manifest_gates(self):
        for module in (plan_capabilities, plan_mvg):
            for mixed in (["--task-id", "15"], ["--allow-unready-draft"]):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(module.main(["--repo-root", str(self.root), "prepare", "--run-id", "mixed",
                        "--input-stage", "3b", "--planning-contract", "contract.json", *mixed]), 2)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(plan_mvg.main(["--repo-root", str(self.root), "prepare", "--run-id", "legacy"]), 2)
            self.assertEqual(plan_capabilities.main(["--repo-root", str(self.root), "prepare", "--run-id", "implicit",
                "--planning-contract", "contract.json"]), 2)

    @unittest.skipUnless(os.name == "nt", "Windows OS path boundary")
    def test_windows_real_junction_short_path_case_and_parent_rejected(self):
        actual = self.root / "long directory for alias check"
        actual.mkdir()
        (actual / "file.txt").write_bytes(b"Original constraint\r\n")
        junction = self.root / "junction"
        process = subprocess.run(["cmd", "/c", "mklink", "/J", str(junction), str(actual)], capture_output=True)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.addCleanup(lambda: os.rmdir(junction) if junction.exists() else None)
        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetShortPathNameW(str(actual), buffer, len(buffer))
        self.assertGreater(length, 0)
        aliases = ["junction/file.txt", "docs/../docs/constraint.md", "DOCS/constraint.md"]
        short = Path(buffer.value).name
        if short != actual.name:
            aliases.append(short + "/file.txt")
        for index, alias in enumerate(aliases):
            contract = deepcopy(self.contract)
            contract["constraints"][0]["path"] = alias
            self.assertEqual(self.prepare("path" + str(index), contract=contract)["status"], "blocked")
        with contextlib.redirect_stdout(io.StringIO()):
            for module in (plan_capabilities, plan_mvg):
                self.assertEqual(module.main(["--repo-root", str(junction), "prepare", "--run-id", "root-alias",
                    "--input-stage", "3b", "--planning-contract", "contract.json"]), 2)


class RealVerifierRejectionTests(unittest.TestCase):
    def test_original_synthetic_proof_read_only_revalidation_cannot_grant_3b(self):
        fixture = audit_tests.SourceAuditTests(methodName="test_complete_zero_task_os_lifecycle_verify_and_exact_replay")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        accounted, _ = fixture.accounted()
        code, proof = fixture.audit(accounted)
        self.assertEqual(code, 0, proof)
        fixture.put("constraint.md", b"Keep originals.\r\n")
        contract = {"schema_version": planning.CONTRACT, "input_stage": "3b", "audit_ref": proof["output_ref"] + "/report.json",
            "scope": {"scope_id": "scope", "kind": "all", "ids": []}, "constraints": [{"path": "constraint.md", "format": "text"}],
            "contexts": [], "limits": {"max_bytes": 1048576, "max_input_tokens": 96000, "reserved_tokens": 0}}
        fixture.put("contract.json", contract)
        original = {p: p.read_bytes() for p in (fixture.root / proof["output_ref"]).rglob("*") if p.is_file()}
        native_run = subprocess.run
        def only_git(command, *args, **kwargs):
            self.assertEqual(Path(command[0]).stem, "git", "Only native read-only Git provenance may spawn here")
            return native_run(command, *args, **kwargs)
        with patch.object(subprocess, "run", side_effect=only_git), \
             patch.object(audit, "run_isolated_model", side_effect=AssertionError("No model")):
            blocked = planning.prepare(fixture.root, run_id="synthetic-denied", planning_contract="contract.json")
        self.assertEqual(blocked["status"], "blocked", blocked)
        self.assertIn("synthetic", json.dumps(blocked))
        for path, raw in original.items():
            self.assertEqual(path.read_bytes(), raw)


if __name__ == "__main__":
    unittest.main()
