"""Behavioral contracts for Task-free cumulative source accounting."""
import contextlib
import ctypes
import datetime as dt
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_sources as sources
import _b_route_codec as codec


class SourceAccountingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="story21-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.put("docs/source.md", b"# Rule\r\n\r\nKeep the reward order.  \r\n")
        self.registration(["docs/source.md"])
        self.guard = {p.relative_to(self.root).as_posix(): p.read_bytes()
                      for p in self.root.rglob("*") if p.is_file()}

    def put(self, path, data):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data if isinstance(data, bytes) else (json.dumps(data) + "\n").encode())
        return target

    def registration(self, patterns, active=None, retired=None):
        self.put("docs/source-set.json", {"schema_version": "chapter3.source-set.v1", "active_patterns": patterns,
                                           "active_sources": active if active is not None else patterns,
                                           "retirements": retired or []})

    def invoke(self, stage, attempt="a1", extras=(), entry=None, run="run", scope="scope"):
        args = ["--stage", stage, "--root", str(self.root), "--run-id", run, "--scope-id", scope,
                "--attempt-id", attempt, *extras]
        if entry:
            prefix = ["b-route-sources"] if entry.name == "dev_cli.py" else []
            proc = subprocess.run([sys.executable, str(entry), *prefix, *args], capture_output=True, text=True)
            self.assertEqual(proc.stderr, "", proc.stderr)
            payload = json.loads(proc.stdout)
            self.assertEqual(len(proc.stdout.splitlines()), 1)
            return proc.returncode, payload
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = sources.main(args)
        self.assertEqual(len(stream.getvalue().splitlines()), 1)
        return code, json.loads(stream.getvalue())

    def prepare(self, attempt="a1", extras=(), entry=None):
        code, report = self.invoke("prepare", attempt, ["--source-set", "docs/source-set.json", *extras], entry)
        self.assertEqual(code, 0, report)
        return report

    def json(self, path):
        return json.loads((self.root / path).read_bytes())

    def candidate(self, prepared, *, disposition=None):
        prefix = prepared["output_ref"]
        candidate = self.json(prefix + "/candidate.json")
        all_ids = [row["block_id"] for row in candidate["block_results"]]
        for i, row in enumerate(candidate["block_results"]):
            row["delivery_potential"] = True
            if disposition:
                row.update(atoms=[], disposition=disposition, reason="The cited source remains a cumulative obligation.",
                           source_block_ids=[row["block_id"]])
            else:
                row.update(disposition="atomized", atoms=[{
                    "proposal_id": "proposal:reward-order", "kind": "functional", "statement": "Preserve reward order.",
                    "source_block_ids": all_ids, "acceptance_intent": "Selecting a reward preserves the displayed candidate ordering.",
                    "prior_requirement_ids": ["FR-EXISTING"], "non_task_sinks": ["reward-order-check"]}])
        for row in candidate["batch_summaries"]:
            row["output_accounted_count"] = row["input_block_count"]
        self.put("candidate.json", candidate)
        return candidate

    def account(self, prepared, attempt="a1", entry=None):
        return self.invoke("account", attempt, ["--prepared", prepared["prepared_ref"]["path"],
                                                "--candidate", "candidate.json"], entry)

    def test_zero_task_complete_and_raw_bytes_are_distinct_from_native_hashes(self):
        prepared = self.prepare(extras=["--max-blocks", "1"])
        candidate = self.candidate(prepared)
        code, report = self.account(prepared)
        self.assertEqual(code, 0, report)
        self.assertTrue(report["accounting_complete"])
        for field in ("satisfied", "independent_audit", "formal_adoption"):
            self.assertIs(report[field], False)
        self.assertEqual(report["model_dispatch_count"], 0)
        self.assertGreaterEqual(report["active_elapsed_seconds"], 0)
        proposed = self.json(report["output_ref"] + "/requirement-proposals.json")["proposals"]
        self.assertEqual(proposed[0]["acceptance_intent"], candidate["block_results"][0]["atoms"][0]["acceptance_intent"])
        self.assertEqual(proposed[0]["prior_requirement_ids"], ["FR-EXISTING"])
        self.assertEqual(proposed[0]["non_task_sinks"], ["reward-order-check"])
        accounting = self.json(report["output_ref"] + "/source-accounting.json")
        self.assertFalse(any(edge["target_type"] == "global_constraint"
                             for edge in accounting["edges"]["edges"]))
        proof = self.json(prepared["prepared_ref"]["path"])
        raw = next(row for row in proof["observations"] if row["path"] == "docs/source.md")
        manifest = self.json(prepared["output_ref"] + "/source-manifest.json")
        self.assertNotEqual(raw["raw_digest"], "sha256:" + manifest["sources"][0]["sha256"])
        self.assertEqual((self.root / prepared["output_ref"] / raw["archive"]).read_bytes(), self.guard["docs/source.md"])
        for path, data in self.guard.items():
            self.assertEqual((self.root / path).read_bytes(), data)
        self.assertFalse((self.root / ".taskmaster").exists())

    def test_all_unresolved_block_even_without_delivery_potential(self):
        prepared = self.prepare()
        candidate = self.candidate(prepared, disposition="unresolved")
        for row in candidate["block_results"]:
            row["delivery_potential"] = False
        self.put("candidate.json", candidate)
        code, report = self.account(prepared)
        self.assertEqual(code, 1)
        self.assertFalse(report["accounting_complete"])
        self.assertTrue(report["unresolved"])

    def test_normalized_unresolved_status_and_disposition_remain_blocking(self):
        prepared = self.prepare(extras=["--max-blocks", "1"])
        original_bytes = (self.root / "docs/source.md").read_bytes()
        original_ids = [row["block_id"] for row in self.json(prepared["output_ref"] + "/source-blocks.json")["blocks"]]
        for index, (field, value) in enumerate((("status", "UNRESOLVED"), ("status", " unresolved "),
                                                 ("disposition", " UNRESOLVED "))):
            with self.subTest(field=field, value=value):
                candidate = self.candidate(prepared)
                for row in candidate["block_results"]:
                    row["delivery_potential"] = False
                    row["atoms"][0].update(kind="context", delivery_relevant=False, **{field: value})
                self.put("candidate.json", candidate)
                code, report = self.account(prepared, "normalized-atom-" + str(index))
                self.assertEqual(code, 1, report)
                self.assertFalse(report["accounting_complete"])
                self.assertTrue(any(row["entity_id"] == "proposal:reward-order" for row in report["unresolved"]))
        candidate = self.candidate(prepared, disposition=" unresolved ")
        for row in candidate["block_results"]:
            row["delivery_potential"] = False
        self.put("candidate.json", candidate)
        code, report = self.account(prepared, "normalized-block")
        self.assertEqual(code, 1, report)
        self.assertFalse(report["accounting_complete"])
        self.assertTrue(any(row["entity_id"] == original_ids[0] for row in report["unresolved"]))
        self.assertEqual((self.root / "docs/source.md").read_bytes(), original_bytes)
        self.assertEqual([row["block_id"] for row in self.json(prepared["output_ref"] + "/source-blocks.json")["blocks"]], original_ids)

    def test_object_statement_is_rejected_without_string_coercion(self):
        prepared = self.prepare()
        candidate = self.candidate(prepared)
        candidate["block_results"][0]["atoms"][0]["statement"] = {"rule": "Preserve reward order."}
        self.put("candidate.json", candidate)
        code, report = self.account(prepared)
        self.assertEqual(code, 1, report)
        self.assertFalse(report["accounting_complete"])
        self.assertEqual(report["diagnostics"][0]["entity_id"], "proposal:reward-order")
        self.assertEqual(report["diagnostics"][0]["actual"], {"rule": "Preserve reward order."})

    def test_fractional_accounted_count_is_rejected_before_native_coercion(self):
        prepared = self.prepare()
        candidate = self.candidate(prepared)
        summary = candidate["batch_summaries"][0]
        summary["output_accounted_count"] = summary["input_block_count"] + 0.5
        self.put("candidate.json", candidate)
        code, report = self.account(prepared)
        self.assertEqual(code, 1, report)
        self.assertFalse(report["accounting_complete"])
        self.assertEqual(report["diagnostics"][0]["entity_id"], summary["batch_id"])
        self.assertEqual(report["diagnostics"][0]["actual"], summary["output_accounted_count"])

    def test_cross_batch_shared_proposal_conflicting_acceptance_intent_is_rejected(self):
        prepared = self.prepare(extras=["--max-blocks", "1"])
        candidate = self.candidate(prepared)
        first, second = candidate["block_results"][:2]
        self.assertNotEqual(first["batch_id"], second["batch_id"])
        self.assertEqual(first["atoms"][0]["source_block_ids"], second["atoms"][0]["source_block_ids"])
        self.assertEqual(first["atoms"][0]["proposal_id"], second["atoms"][0]["proposal_id"])
        second["atoms"][0]["acceptance_intent"] = "Selecting a reward reverses the displayed candidate ordering."
        self.put("candidate.json", candidate)
        code, report = self.account(prepared)
        self.assertEqual(code, 1, report)
        self.assertFalse(report["accounting_complete"])
        self.assertEqual(report["diagnostics"][0]["entity_id"], "proposal:reward-order")

    def test_missing_intent_preserves_local_proposal_but_blocks(self):
        prepared = self.prepare()
        candidate = self.candidate(prepared)
        for row in candidate["block_results"]:
            row["atoms"][0]["acceptance_intent"] = ""
        self.put("candidate.json", candidate)
        code, report = self.account(prepared)
        self.assertEqual(code, 1)
        self.assertTrue(self.json(report["output_ref"] + "/requirement-proposals.json")["proposals"])

    def test_source_backed_dispositions_and_missing_reason(self):
        prepared = self.prepare()
        for i, disposition in enumerate(("context", "rationale", "deferred", "out_of_scope", "adr_owned")):
            self.candidate(prepared, disposition=disposition)
            code, report = self.account(prepared, "a" + str(i + 2))
            self.assertEqual(code, 0, report)
        candidate = self.candidate(prepared, disposition="deferred")
        candidate["block_results"][0]["reason"] = ""
        self.put("candidate.json", candidate)
        code, report = self.account(prepared, "missing-reason")
        self.assertEqual(code, 1)

    def test_empty_json_is_retained_and_requires_file_disposition(self):
        self.put("docs/empty.json", b"{}\r\n  ")
        self.registration(["docs/empty.json"])
        prepared = self.prepare()
        candidate = self.candidate(prepared)
        code, report = self.account(prepared)
        self.assertEqual(code, 1)
        self.assertEqual(report["source_count"], 1)
        self.assertEqual(report["source_block_count"], 0)
        self.put("docs/review.md", b"The empty object is retained as source context.\n")
        candidate["file_results"][0].update(disposition="context", reason="An intentionally empty configuration object.",
            evidence={"path": "docs/review.md", "raw_digest": codec.raw_digest((self.root / "docs/review.md").read_bytes()),
                      "byte_start": 0, "byte_end": 10})
        self.put("candidate.json", candidate)
        code, report = self.account(prepared, "resolved")
        self.assertEqual(code, 0, report)

    def test_empty_file_object_reason_remains_unresolved_with_valid_evidence(self):
        self.put("docs/empty.json", b"{}\r\n  ")
        self.registration(["docs/empty.json"])
        prepared = self.prepare()
        candidate = self.candidate(prepared)
        self.put("docs/review.md", b"Retain this intentionally empty source.\n")
        candidate["file_results"][0].update(disposition="context", reason={"text": "Intentionally empty."},
            evidence={"path": "docs/review.md", "raw_digest": codec.raw_digest((self.root / "docs/review.md").read_bytes()),
                      "byte_start": 0, "byte_end": 10})
        self.put("candidate.json", candidate)
        code, report = self.account(prepared)
        self.assertEqual(code, 1, report)
        self.assertFalse(report["accounting_complete"])
        self.assertTrue(any(row["entity_id"] == "docs/empty.json" for row in report["unresolved"]))
        self.assertEqual(report["diagnostics"], [])

    def test_whole_long_json_object_transport_and_capacity_rejection(self):
        self.put("docs/long.json", ('[ {"long": "' + "x" * 16000 + '\\r\\n' + 'y' * 16000 + '"} ]\r\n ').encode())
        self.registration(["docs/long.json"])
        prepared = self.prepare(extras=["--max-chars", "50000", "--transport-max-bytes", "18000",
                                        "--transport-max-input-tokens", "18000"])
        ledger = self.json(prepared["output_ref"] + "/source-blocks.json")
        self.assertEqual(len(ledger["blocks"]), 1)
        self.assertIn("y" * 16000, ledger["blocks"][0]["raw_text"])
        plan = self.json(prepared["output_ref"] + "/transport.json")
        self.assertGreater(len(plan["batches"]), 1)
        self.candidate(prepared)
        code, report = self.account(prepared)
        self.assertEqual(code, 0, report)
        code, report = self.invoke("prepare", "too-small", ["--source-set", "docs/source-set.json", "--max-chars", "100"])
        self.assertEqual(code, 1)
        self.assertTrue((self.root / report["output_ref"] / "event.json").is_file())

    def test_cross_stage_source_and_glob_membership_drift(self):
        self.registration(["docs/*.md"], active=["docs/source.md"])
        prepared = self.prepare()
        self.candidate(prepared)
        self.put("docs/added.md", b"Another source.\n")
        code, report = self.account(prepared)
        self.assertEqual(code, 1)
        self.assertTrue(report["diagnostics"])
        (self.root / "docs/added.md").unlink()
        self.put("docs/source.md", b"changed")
        code, report = self.account(prepared, "source-drift")
        self.assertEqual(code, 1)
        self.assertIn("docs/source.md", json.dumps(report["diagnostics"]))

    def test_prepare_and_candidate_damage_are_located(self):
        for damage in ("batch", "raw", "binding", "duplicate", "omitted", "summary", "reference"):
            with self.subTest(damage=damage):
                prepared = self.prepare(attempt=damage)
                candidate = self.candidate(prepared)
                if damage == "batch":
                    target = next((self.root / prepared["output_ref"] / "batches").glob("*.json"))
                    target.write_bytes(b"{}")
                elif damage == "raw":
                    target = next((self.root / prepared["output_ref"] / "raw").glob("*.bin"))
                    target.write_bytes(b"corrupt")
                else:
                    if damage == "binding":
                        candidate["prepared_ref"]["raw_digest"] = "sha256:" + "0" * 64
                    elif damage == "duplicate":
                        candidate["block_results"].append(candidate["block_results"][0])
                    elif damage == "omitted":
                        candidate["block_results"].pop()
                    elif damage == "summary":
                        candidate["batch_summaries"].append(candidate["batch_summaries"][0])
                    else:
                        candidate["block_results"][0]["atoms"][0]["source_block_ids"].append("SB-MISSING")
                    self.put("candidate.json", candidate)
                code, report = self.account(prepared, damage)
                self.assertEqual(code, 1, report)
                self.assertTrue(report["diagnostics"])

    def test_bad_prepared_reference_retains_parsed_failure_snapshot(self):
        prepared = self.prepare()
        candidate = self.candidate(prepared)
        candidate["prepared_ref"]["raw_digest"] = "sha256:" + "0" * 64
        self.put("candidate.json", candidate)
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        code, report = self.account(prepared, "bad-prepared-ref")
        self.assertEqual(code, 1, report)
        self.assertFalse(report["accounting_complete"])
        self.assertEqual(report["model_dispatch_count"], 0)
        self.assertEqual(report["diagnostics"][0]["expected"], "exact prepared reference and raw identity")
        snapshot = self.root / report["output_ref"] / "candidate.snapshot.json"
        self.assertEqual(self.json(snapshot.relative_to(self.root).as_posix()), candidate)
        event = self.json(report["output_ref"] + "/event.json")
        self.assertEqual(event["artifacts"]["candidate.snapshot.json"], codec.raw_digest(snapshot.read_bytes()))
        for path, raw in before.items():
            self.assertEqual((self.root / path).read_bytes(), raw)
        frozen = {p.relative_to(snapshot.parent): p.read_bytes() for p in snapshot.parent.rglob("*") if p.is_file()}
        replay_code, replay = self.account(prepared, "bad-prepared-ref")
        self.assertEqual(replay_code, 1, replay)
        self.assertEqual(replay, report)
        for path, raw in frozen.items():
            self.assertEqual((snapshot.parent / path).read_bytes(), raw)

    def test_account_rejects_rebound_caches_that_omit_a_registered_source(self):
        self.put("docs/other.md", b"Another registered cumulative obligation.\r\n")
        self.registration(["docs/source.md", "docs/other.md"])
        protected = {path: (self.root / path).read_bytes()
                     for path in ("docs/source-set.json", "docs/source.md", "docs/other.md")}
        prepared = self.prepare()
        prefix = self.root / prepared["output_ref"]
        proof = self.json(prepared["prepared_ref"]["path"])
        limits = sources.argparse.Namespace(**proof["limits"])
        obs = sources.Observations(self.root)
        manifest, ledger = sources.native.build_ledger(self.root, ["docs/source.md"], "add", True,
            text_reader=obs.reader, previous_sources=["docs/source.md"])
        index, candidate = sources.projection.prepare(ledger, limits.max_blocks, prefix / "batches", limits.max_chars)
        candidate.update(schema_version=sources.CANDIDATE, file_results=[])
        proof.update(effective_patterns=["docs/source.md"], prior_sources=["docs/source.md"],
                     source_revision=manifest["source_revision"], source_manifest_sha256=manifest["manifest_sha256"])
        self.assertEqual(proof["source_registration"]["active_sources"], ["docs/source.md", "docs/other.md"])
        for name, payload in (("source-manifest.json", manifest), ("source-blocks.json", ledger),
                              ("batch-index.json", index), ("prepared.json", proof)):
            self.put(prepared["output_ref"] + "/" + name, payload)
        candidate["prepared_ref"] = {"path": prepared["prepared_ref"]["path"],
            "raw_digest": codec.raw_digest((prefix / "prepared.json").read_bytes())}
        self.put(prepared["output_ref"] + "/candidate.json", candidate)
        plan = sources.plan_transport(sources.transport_context(obs, manifest), phase="inspect",
            probe=sources.probe_for(limits), schema_version=sources.TRANSPORT_SCHEMA)
        self.put(prepared["output_ref"] + "/transport.json", plan)
        event = self.json(prepared["output_ref"] + "/event.json")
        event["artifacts"] = {path.relative_to(prefix).as_posix(): codec.raw_digest(path.read_bytes())
                              for path in prefix.rglob("*") if path.is_file() and path.name != "event.json"}
        self.put(prepared["output_ref"] + "/event.json", event)
        self.candidate(prepared)
        code, report = self.account(prepared, "contradictory-cache")
        self.assertEqual(code, 1, report)
        self.assertFalse(report["accounting_complete"])
        self.assertEqual(report["diagnostics"][0]["entity_id"], "prepared.effective_patterns")
        self.assertEqual(report["diagnostics"][0]["expected"], ["docs/source.md", "docs/other.md"])
        self.assertEqual(report["diagnostics"][0]["actual"], ["docs/source.md"])
        self.assertEqual(report["model_dispatch_count"], 0)
        self.assertFalse(report["formal_adoption"])
        for path, raw in protected.items():
            self.assertEqual((self.root / path).read_bytes(), raw)

    def test_explicit_retirement_and_additions_preserve_registration(self):
        before = (self.root / "docs/source-set.json").read_bytes()
        self.put("docs/new.md", b"A new cumulative obligation.\n")
        self.put("docs/review.md", b"Retire the old wording and retain it in history.\n")
        declaration = {"schema_version": sources.DECLARATION, "additions": ["docs/new.md"], "retirements": [{
            "path": "docs/source.md", "reason": "The reviewed replacement uses the new wording.",
            "evidence": {"path": "docs/review.md", "raw_digest": codec.raw_digest((self.root / "docs/review.md").read_bytes()),
                         "byte_start": 0, "byte_end": 10}}]}
        self.put("declaration.json", declaration)
        prepared = self.prepare(extras=["--declaration", "declaration.json"])
        manifest = self.json(prepared["output_ref"] + "/source-manifest.json")
        self.assertEqual([r["path"] for r in manifest["sources"]], ["docs/new.md"])
        self.assertEqual((self.root / "docs/source-set.json").read_bytes(), before)
        proof = self.json(prepared["prepared_ref"]["path"])
        self.assertTrue(any(r["path"] == "docs/source.md" for r in proof["observations"]))
        self.candidate(prepared)
        code, report = self.account(prepared)
        self.assertEqual(code, 0, report)
        declaration["retirements"][0]["reason"] = ""
        self.put("declaration.json", declaration)
        code, _ = self.invoke("prepare", "bad-retire", ["--source-set", "docs/source-set.json", "--declaration", "declaration.json"])
        self.assertEqual(code, 1)

    def test_prior_active_empty_source_disappearance_fails(self):
        self.put("docs/empty.json", b"{}")
        self.registration(["docs/source.md"], active=["docs/source.md", "docs/empty.json"])
        code, report = self.invoke("prepare", extras=["--source-set", "docs/source-set.json"])
        self.assertEqual(code, 1, report)
        self.assertIn("docs/empty.json", json.dumps(report["diagnostics"]))

    def test_historical_retirements_are_not_resurrected(self):
        self.put("docs/retired.md", b"Historical source.\n")
        self.registration(["docs/*.md"], active=["docs/source.md"],
                          retired=[{"path": "docs/retired.md", "reason": "historical-reference-only"}])
        prepared = self.prepare()
        manifest = self.json(prepared["output_ref"] + "/source-manifest.json")
        self.assertNotIn("docs/retired.md", [r["path"] for r in manifest["sources"]])

    def test_previous_prepared_stabilizes_ids_for_changed_sources(self):
        previous = self.prepare()
        old = self.json(previous["output_ref"] + "/source-blocks.json")
        self.put("docs/source.md", b"# Rule\n\nNew first paragraph.\n\nKeep the reward order.  \n")
        prepared = self.prepare("increment", ["--previous", previous["prepared_ref"]["path"]])
        new = self.json(prepared["output_ref"] + "/source-blocks.json")
        old_id = next(r["block_id"] for r in old["blocks"] if "Keep" in r["raw_text"])
        new_id = next(r["block_id"] for r in new["blocks"] if "Keep" in r["raw_text"])
        self.assertEqual(old_id, new_id)
        self.candidate(prepared)
        code, report = self.account(prepared)
        self.assertEqual(code, 0, report)

    def test_previous_explicit_retirement_cannot_disappear_or_reactivate_source(self):
        self.put("docs/current.md", b"Current cumulative source and reviewed retirement basis.\n")
        self.registration(["docs/source.md", "docs/current.md"])
        self.put("declaration.json", {"schema_version": sources.DECLARATION, "additions": [], "retirements": [{
            "path": "docs/source.md", "reason": "Retain this earlier source as retired history.",
            "evidence": {"path": "docs/current.md", "raw_digest": codec.raw_digest((self.root / "docs/current.md").read_bytes()),
                         "byte_start": 0, "byte_end": 10}}]})
        previous = self.prepare(extras=["--declaration", "declaration.json"])
        prefix = self.root / previous["output_ref"]
        original_proof = {p.relative_to(prefix): p.read_bytes() for p in prefix.rglob("*") if p.is_file()}
        code, report = self.invoke("prepare", "missing-history", ["--source-set", "docs/source-set.json",
            "--previous", previous["prepared_ref"]["path"]])
        self.assertEqual(code, 1, report)
        self.assertFalse(report["accounting_complete"])
        self.assertEqual(report["diagnostics"][0]["actual"], ["docs/source.md"])
        self.assertFalse((self.root / report["output_ref"] / "source-manifest.json").exists())
        explicit = self.prepare("retained-explicit", ["--declaration", "declaration.json",
                                                      "--previous", previous["prepared_ref"]["path"]])
        self.assertEqual([row["path"] for row in self.json(explicit["output_ref"] + "/source-manifest.json")["sources"]],
                         ["docs/current.md"])
        self.candidate(explicit)
        code, report = self.account(explicit, "account-retained-explicit")
        self.assertEqual(code, 0, report)
        self.registration(["docs/current.md"], retired=[{"path": "docs/source.md", "reason": "Reviewed registered retirement."}])
        registered = self.prepare("retained-registered", ["--previous", previous["prepared_ref"]["path"]])
        self.assertEqual(self.json(registered["prepared_ref"]["path"])["retired_sources"], ["docs/source.md"])
        self.candidate(registered)
        code, report = self.account(registered, "account-retained-registered")
        self.assertEqual(code, 0, report)
        self.registration(["docs/current.md"])
        code, report = self.invoke("prepare", "missing-registered-history", ["--source-set", "docs/source-set.json",
            "--previous", registered["prepared_ref"]["path"]])
        self.assertEqual(code, 1, report)
        self.assertEqual(report["diagnostics"][0]["actual"], ["docs/source.md"])
        for path, raw in original_proof.items():
            self.assertEqual((prefix / path).read_bytes(), raw)

    def test_nested_addition_conflict_uses_native_retirement_fnmatch(self):
        self.put("prd/current.md", b"An active source outside the retired tree.\n")
        self.put("docs/nested/new.md", b"An explicit addition cannot disappear silently.\n")
        self.registration(["prd/current.md"], retired=[{"path": "docs/*.md", "reason": "Retired source range."}])
        self.put("declaration.json", {"schema_version": sources.DECLARATION,
                                      "additions": ["docs/nested/new.md"], "retirements": []})
        source_bytes = (self.root / "docs/nested/new.md").read_bytes()
        code, report = self.invoke("prepare", "nested-addition", ["--source-set", "docs/source-set.json",
                                                                   "--declaration", "declaration.json"])
        self.assertEqual(code, 1, report)
        self.assertFalse(report["accounting_complete"])
        self.assertTrue(report["diagnostics"])
        self.assertFalse((self.root / report["output_ref"] / "source-manifest.json").exists())
        self.assertEqual((self.root / "docs/nested/new.md").read_bytes(), source_bytes)

    def test_duplicate_event_conflict_partial_and_new_attempt(self):
        first = self.prepare()
        prefix = self.root / first["output_ref"]
        raw = {p.relative_to(prefix).as_posix(): p.read_bytes() for p in prefix.rglob("*") if p.is_file()}
        code, replay = self.invoke("prepare", extras=["--source-set", "docs/source-set.json"])
        self.assertEqual(code, 0)
        self.assertEqual(replay, first)
        for path, data in raw.items():
            self.assertEqual((prefix / path).read_bytes(), data)
        code, _ = self.invoke("prepare", extras=["--source-set", "docs/source-set.json"], scope="different")
        self.assertEqual(code, 2)
        (prefix / "event.json").unlink()
        code, _ = self.invoke("prepare", extras=["--source-set", "docs/source-set.json"])
        self.assertEqual(code, 2)
        self.prepare("new-attempt")

    def test_event_deduplication_across_utc_dates(self):
        first = self.prepare()
        original = self.root / first["output_ref"]
        different = self.root / first["output_ref"].replace(dt.datetime.now(dt.timezone.utc).date().isoformat(), "2001-01-01")
        different.parent.mkdir(parents=True, exist_ok=True)
        original.rename(different)
        code, report = self.invoke("prepare", extras=["--source-set", "docs/source-set.json"])
        self.assertEqual(code, 0, report)
        self.assertEqual(report, first)
        self.assertFalse(original.exists())

    def test_same_event_changed_input_conflicts_without_rewriting(self):
        first = self.prepare()
        event = self.root / first["output_ref"] / "event.json"
        original = event.read_bytes()
        self.put("docs/source.md", b"Changed after preparation.\n")
        code, report = self.invoke("prepare", extras=["--source-set", "docs/source-set.json"])
        self.assertEqual(code, 2, report)
        self.assertEqual(event.read_bytes(), original)

    def test_real_injected_end_read_drift_and_disk_failure_have_events(self):
        original_verify = sources.Observations.verify
        changed = False
        def drift(obs):
            nonlocal changed
            if not changed:
                self.put("docs/source.md", b"concurrent edit")
                changed = True
            return original_verify(obs)
        with patch.object(sources.Observations, "verify", drift):
            code, report = self.invoke("prepare", extras=["--source-set", "docs/source-set.json"])
        self.assertEqual(code, 1)
        self.assertEqual(self.json(report["output_ref"] + "/event.json")["termination_reason"], "blocked")
        actual_write = sources.write
        def broken(path, value):
            if path.name == "transport.json":
                raise OSError("injected disk write failure")
            return actual_write(path, value)
        with patch.object(sources, "write", broken):
            code, report = self.invoke("prepare", "disk-failure", ["--source-set", "docs/source-set.json"])
        self.assertEqual(code, 1)
        self.assertEqual(self.json(report["output_ref"] + "/event.json")["exit_code"], 1)

    def test_strict_json_missing_input_and_parameter_admission(self):
        self.put("docs/source-set.json", b'{"active_patterns":[],"active_patterns":[]}')
        code, report = self.invoke("prepare", extras=["--source-set", "docs/source-set.json"])
        self.assertEqual(code, 1)
        self.assertEqual(report["diagnostics"][0]["reason_code"], "duplicate_key")
        self.assertEqual(report["diagnostics"][0]["entity_id"], "docs/source-set.json")
        for args in (("--source-set", "../escape"), (), ("--source-set", "docs/source-set.json", "--unexpected", "x")):
            code, _ = self.invoke("prepare", "invalid", args)
            self.assertEqual(code, 2)
        code, report = self.invoke("prepare", "missing", ["--source-set", "docs/missing.json"])
        self.assertEqual(code, 1)
        self.assertEqual(report["diagnostics"][0]["reason_code"], "file_not_found")

    def test_json_source_decode_errors_locate_exact_input_and_preserve_codec_diagnostic(self):
        self.put("docs/a-valid.json", b'{"rule":"Valid source read first."}')
        for label, raw in (("syntax", b'{"rule":'), ("utf8", b'{"rule":"\xff"}')):
            with self.subTest(label=label):
                corrupt_path = "docs/z-corrupt.json"
                self.put(corrupt_path, raw)
                self.registration(["docs/a-valid.json", corrupt_path])
                with self.assertRaises(codec.CodecError) as original:
                    codec.strict_json_loads(raw)
                expected = original.exception.diagnostic.to_dict()
                code, report = self.invoke("prepare", "bad-source-" + label,
                                           ["--source-set", "docs/source-set.json"])
                self.assertEqual(code, 1, report)
                actual = report["diagnostics"][0]
                self.assertEqual(actual["entity_id"], corrupt_path)
                for field in ("reason_code", "stage", "expected", "actual"):
                    self.assertEqual(actual[field], expected[field])
                event = self.json(report["output_ref"] + "/event.json")
                self.assertEqual(event["diagnostics"], report["diagnostics"])
                observed = list(event["observations"])
                self.assertLess(observed.index("docs/a-valid.json"), observed.index(corrupt_path))
                self.assertEqual((self.root / corrupt_path).read_bytes(), raw)

    def test_registry_and_candidate_decode_errors_share_located_codec_diagnostic(self):
        prepared = self.prepare()
        for label, raw in (("syntax", b'{"rule":'), ("utf8", b'{"rule":"\xff"}')):
            with self.subTest(label=label):
                with self.assertRaises(codec.CodecError) as original:
                    codec.strict_json_loads(raw)
                expected = original.exception.diagnostic.to_dict()
                for path, stage, extras in (
                    ("candidate.json", "account", ["--prepared", prepared["prepared_ref"]["path"],
                                                       "--candidate", "candidate.json"]),
                    ("docs/source-set.json", "prepare", ["--source-set", "docs/source-set.json"]),
                ):
                    self.put(path, raw)
                    code, report = self.invoke(stage, "bad-" + stage + "-" + label, extras)
                    self.assertEqual(code, 1, report)
                    actual = report["diagnostics"][0]
                    self.assertEqual(actual["entity_id"], path)
                    for field in ("reason_code", "stage", "expected", "actual"):
                        self.assertEqual(actual[field], expected[field])
                    self.registration(["docs/source.md"])

    @unittest.skipIf(os.name == "nt", "POSIX symlink counterpart; Windows junction is tested separately")
    def test_root_source_and_logs_symlinks_are_rejected(self):
        outside = self.root / "outside"
        outside.mkdir()
        link = self.root / "linked-root"
        link.symlink_to(outside, target_is_directory=True)
        args = ["--stage", "prepare", "--root", str(link), "--run-id", "r", "--scope-id", "s", "--attempt-id", "a",
                "--source-set", "source.json"]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sources.main(args), 2)
        (self.root / "logs").symlink_to(outside, target_is_directory=True)
        code, _ = self.invoke("prepare", extras=["--source-set", "docs/source-set.json"])
        self.assertEqual(code, 2)
        self.assertEqual(list(outside.iterdir()), [])

    def test_independent_cli_both_entries_without_B_and_no_bytecode(self):
        script_root = Path(__file__).resolve().parents[1]
        copied = self.root / "scripts/python"
        copied.mkdir(parents=True)
        for source in script_root.glob("*.py"):
            shutil.copyfile(source, copied / source.name)
        for name in ("account_b_route_sources.py", "dev_cli.py"):
            entry = copied / name
            prepared = self.prepare(name.replace(".", "-"), entry=entry)
            self.candidate(prepared)
            code, report = self.account(prepared, name.replace(".", "-"), entry=entry)
            self.assertEqual(code, 0, report)
            code, _ = self.invoke("prepare", "bad-" + name.replace(".", "-"), ["--source-set", "docs/missing.json"], entry=entry)
            self.assertEqual(code, 1)
        self.assertEqual(list(copied.rglob("*.pyc")), [])

    @unittest.skipUnless(os.name == "nt", "Requires real Windows junctions and short-path identities")
    def test_windows_real_junction_and_short_path(self):
        target = self.root / "long-root-directory-for-story-two-one"
        target.mkdir()
        (target / "source.md").write_bytes(b"A source.\r\n")
        (target / "set.json").write_text(json.dumps({"schema_version": "chapter3.source-set.v1", "active_patterns": ["source.md"],
                                                     "active_sources": ["source.md"], "retirements": []}))
        link = self.root / "junction"
        proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.addCleanup(lambda: os.rmdir(link) if link.exists() else None)
        args = ["--stage", "prepare", "--root", str(link), "--run-id", "r", "--scope-id", "s", "--attempt-id", "a",
                "--source-set", "set.json"]
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(sources.main(args), 2)
        buffer = ctypes.create_unicode_buffer(32768)
        self.assertGreater(ctypes.windll.kernel32.GetShortPathNameW(str(target), buffer, len(buffer)), 0)
        if "~" not in buffer.value:
            proc = subprocess.run(["fsutil", "file", "setshortname", str(target), "STORY2~1"], capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertGreater(ctypes.windll.kernel32.GetShortPathNameW(str(target), buffer, len(buffer)), 0)
        self.assertIn("~", buffer.value, "A real short path must be exercised on Windows")
        args[3] = buffer.value
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            self.assertEqual(sources.main(args), 0, stream.getvalue())
        self.assertTrue((target / "logs").is_dir())
        outside = self.root / "outside-log-target"
        outside.mkdir()
        logs_link = self.root / "logs"
        proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(logs_link), str(outside)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        try:
            code, report = self.invoke("prepare", extras=["--source-set", "docs/source-set.json"])
            self.assertEqual(code, 2, report)
            self.assertEqual(list(outside.iterdir()), [])
        finally:
            os.rmdir(logs_link)
        self.put("outside-log-target/linked.md", b"Junction source must not be consumed.\n")
        source_link = self.root / "docs" / "source-junction"
        proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(source_link), str(outside)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        try:
            self.registration(["docs/source-junction/*.md"], active=[])
            code, report = self.invoke("prepare", "source-junction", ["--source-set", "docs/source-set.json"])
            self.assertEqual(code, 1, report)
            self.assertTrue(report["diagnostics"])
        finally:
            os.rmdir(source_link)


if __name__ == "__main__":
    unittest.main()
