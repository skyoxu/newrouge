"""Behavioral protection tests with isolated, synthetic Git repositories."""
from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _b_route_codec as codec
import _b_route_inventory as inventory
import _b_route_protection as protection
import _b_route_records as records
import capture_b_route_protection as cli


DIAGNOSTIC_FIELDS = {"reason_code", "stage", "entity_id", "expected", "actual", "resume_ref"}
AUTHORIZATION_FIELDS = {"formal_protection_baseline", "frozen_a", "write", "policy_bootstrap", "target_projection_verified"}


def documents() -> dict:
    return {
        "master": {"format": {"status": "keep-envelope"}, "master": {"status": "keep-master", "tasks": [
            {"id": 1, "status": "done", "history": [{"status": "keep-history"}],
             "acceptance": [{"status": "keep-acceptance", "text": "A"}], "dependencies": [2, 3],
             "metadata": {"status": "keep-metadata"}, "subtasks": [
                 {"id": 7, "status": "pending", "metadata": {"status": "keep-subtask-metadata"},
                  "subtasks": [{"id": 70, "status": "keep-grandchild"}]}]},
            {"id": 2, "status": "pending", "title": "Independent"}]}},
        "back": [{"id": "BACK-1", "taskmaster_id": 1, "status": "review", "semantic_review_tier": "strict",
                  "source_refs": ["docs/source.md:2"], "responsibility": "producer", "future": {"status": "keep-unknown"}},
                 {"id": "BACK-2", "taskmaster_id": 2, "status": "pending"}],
        "gameplay": [{"id": "GAME-1", "taskmaster_id": 1, "status": "done"}],
    }


class ProjectionTests(unittest.TestCase):
    def test_projection_owns_one_existing_codec_without_changing_receipt_claims(self):
        self.assertEqual(codec.PROJECTION_CODEC, "newrouge.b-route-task-definition.v1")
        self.assertEqual(records.PROJECTION_CODEC, codec.PROJECTION_CODEC)
        self.assertFalse(records.BundleValidation(True, codec.Diagnostic(codec.ReasonCode.OK)).target_projection_verified)

    def test_only_actual_task_and_direct_subtask_status_is_removed(self):
        source = documents()
        before = copy.deepcopy(source)
        actual = protection.triplet_definition_projection(source)
        task = actual["master"]["master"]["tasks"][0]
        self.assertEqual(protection.task_definition_projection(source["master"]["master"]["tasks"][0]), task)
        self.assertNotIn("status", task)
        self.assertNotIn("status", task["subtasks"][0])
        self.assertEqual(task["subtasks"][0]["subtasks"][0]["status"], "keep-grandchild")
        self.assertEqual(task["metadata"]["status"], "keep-metadata")
        self.assertEqual(task["acceptance"][0]["status"], "keep-acceptance")
        self.assertEqual(task["history"][0]["status"], "keep-history")
        self.assertEqual(actual["master"]["master"]["status"], "keep-master")
        self.assertEqual(actual["master"]["format"]["status"], "keep-envelope")
        self.assertEqual(actual["back"][0]["future"]["status"], "keep-unknown")
        self.assertEqual(actual["back"][0]["semantic_review_tier"], "strict")
        self.assertEqual(source, before, "Projection must never mutate its input")

    def test_status_progress_is_definition_equivalent_but_unknown_fields_and_order_are_not(self):
        source = documents()
        expected = protection.triplet_definition_projection(source)
        source["master"]["master"]["tasks"][0]["status"] = "in-progress"
        source["master"]["master"]["tasks"][0]["subtasks"][0]["status"] = "done"
        source["back"][0]["status"] = "done"
        self.assertEqual(protection.triplet_definition_projection(source), expected)
        for mutate in (
            lambda value: value["back"][0]["future"].update(status="changed"),
            lambda value: value["master"]["master"]["tasks"][0]["acceptance"].append({"text": "New responsibility"}),
            lambda value: value["master"]["master"]["tasks"][0]["dependencies"].reverse(),
            lambda value: value["back"].reverse(),
            lambda value: value["master"]["master"]["tasks"].reverse(),
        ):
            changed = copy.deepcopy(source)
            mutate(changed)
            self.assertNotEqual(protection.triplet_definition_projection(changed), expected)

    def test_join_rejects_coercion_duplicates_orphans_and_unmapped_master(self):
        cases = []
        for value in (True, "1", 1.0, 0, -1, None):
            changed = documents()
            changed["back"][0]["taskmaster_id"] = value
            cases.append(changed)
        changed = documents()
        changed["master"]["master"]["tasks"].append(copy.deepcopy(changed["master"]["master"]["tasks"][0]))
        cases.append(changed)
        changed = documents()
        changed["back"].append(copy.deepcopy(changed["back"][0]))
        cases.append(changed)
        changed = documents()
        changed["back"][0]["taskmaster_id"] = 1000
        cases.append(changed)
        changed = documents()
        changed["master"]["master"]["tasks"].append({"id": 3, "status": "done"})
        cases.append(changed)
        for index, changed in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(codec.CodecError) as caught:
                protection.triplet_definition_projection(changed)
            self.assertEqual(set(caught.exception.diagnostic.to_dict()), DIAGNOSTIC_FIELDS)

    def test_one_business_view_per_master_is_sufficient_and_zero_tasks_is_real(self):
        source = documents()
        source["gameplay"] = []
        self.assertEqual(len(protection.triplet_definition_projection(source)["back"]), 2)
        empty = {"master": {"master": {"tasks": []}, "preserve": {"status": "unknown"}}, "back": [], "gameplay": []}
        self.assertEqual(protection.triplet_definition_projection(empty), empty)


class ProtectionTests(unittest.TestCase):
    def setUp(self):
        # Composition keeps Story 1.1 tests out of this suite's discovery.
        fixtures = importlib.import_module("test_b_route_inventory")
        self.fixture = fixtures.InventoryTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root, self.epics = self.fixture.root, self.fixture.epics

    def dump(self, path, value):
        self.fixture.dump(path, value)

    def load(self, path):
        return self.fixture.load(path)

    def collect(self, **kwargs):
        return protection.collect_protection(self.root, self.epics, **kwargs)

    def snapshot_path(self, output):
        return (output / "snapshot.json").relative_to(self.root).as_posix()

    def archive(self, capture=None, name="baseline"):
        output = self.root / "logs/ci/protection-fixture" / name
        output.mkdir(parents=True, exist_ok=False)
        protection.write_capture(output, capture if capture is not None else self.collect())
        return output

    def all_bytes(self):
        return {path.relative_to(self.root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in self.root.rglob("*") if path.is_file() and ".git" not in path.parts}

    def assert_no_authorization(self, value):
        self.assertEqual(set(value["authorization"]), AUTHORIZATION_FIELDS)
        self.assertTrue(all(value["authorization"][key] is False for key in AUTHORIZATION_FIELDS))

    def assert_public_diagnostics(self, value):
        self.assertTrue(value["diagnostics"])
        for row in value["diagnostics"]:
            self.assertEqual(set(row), DIAGNOSTIC_FIELDS)

    def compare(self, baseline, **kwargs):
        return protection.compare_protection(self.root, self.snapshot_path(baseline), self.epics, **kwargs)

    def test_capture_preserves_every_present_raw_input_and_archives_full_manifest(self):
        self.fixture.edit_task("master", lambda rows: rows[0].update(subtasks=[{"id": 1, "status": "pending", "unknown": {"status": "keep"}}]))
        raw = b"# Source\r\nA\r\nB\r\n"
        (self.root / "docs/source.md").write_bytes(raw)
        before = self.all_bytes()
        capture = self.collect()
        self.assertEqual(before, self.all_bytes())
        self.assertTrue(capture.snapshot["capture_complete"], capture.snapshot["diagnostics"])
        self.assertEqual(capture.raw_files["docs/source.md"], raw)
        present = {row["path"] for row in capture.inventory["inputs"] if row["exists"]}
        self.assertTrue(present <= capture.raw_files.keys())
        for row in capture.inventory["inputs"]:
            if row["exists"]:
                self.assertEqual(codec.raw_digest(capture.raw_files[row["path"]]), row["raw_sha256"])
        self.assertIn("logs/ci/historical/explicit.json", capture.raw_files)
        self.assertIn("Game.Core.Tests/Unmanifested.cs", capture.raw_files)
        self.assertIn("manifest-only/source.txt", capture.raw_files)
        self.assert_no_authorization(capture.snapshot)
        output = self.archive(capture)
        serialized = (output / "snapshot.json").read_text(encoding="utf-8")
        self.assertIn("Not a product-wide run", serialized)
        self.assertIn("ManifestOnly", serialized)
        self.assertIn("manifest-only/Contract.cs", serialized)
        verified = protection.verify_protection(self.root, self.snapshot_path(output))
        self.assertTrue(verified["ok"], verified["diagnostics"])
        self.assert_no_authorization(verified)

    def test_current_done_and_reviewed_text_never_authorize_frozen_a(self):
        self.fixture.edit_task("back", lambda rows: rows[0].update(review={"status": "reviewed", "a_eligible": True}))
        capture = self.collect()
        self.assertTrue(capture.snapshot["capture_complete"])
        self.assert_no_authorization(capture.snapshot)
        frozen = capture.snapshot["frozen_a"]
        self.assertEqual(len(frozen["candidates"]), 2)
        self.assertEqual({row["task_id"] for row in frozen["candidates"]}, {1, 2})
        for row in frozen["candidates"]:
            self.assertEqual(row["status"], "blocked")
            self.assertTrue(row["definition_digest"].startswith("sha256:"))
            self.assertIn("source_scope", row)
            self.assertTrue(row["old_operation_candidates"])
            self.assertIn("review_basis", row)

    def test_full_133_task_set_is_enumerated_without_guessing_legacy(self):
        master = {"master": {"tasks": [{"id": task_id, "status": "done", "history": [{"event": "completed"}]}
                                          for task_id in range(1, 134)]}}
        back = [{"id": f"BACK-{task_id}", "taskmaster_id": task_id, "status": "done", "source_refs": ["docs/source.md:2"]}
                for task_id in range(1, 134)]
        for name, doc in (("master", master), ("back", back), ("gameplay", [])):
            self.dump(inventory.TRIPLET[name], doc)
        capture = self.collect()
        self.assertTrue(capture.snapshot["capture_complete"], capture.snapshot["diagnostics"])
        candidates = capture.snapshot["frozen_a"]["candidates"]
        self.assertEqual([row["task_id"] for row in candidates], list(range(1, 134)))
        self.assertTrue(all(row["status"] == "blocked" for row in candidates))
        self.assert_no_authorization(capture.snapshot)

    def test_zero_tasks_stays_empty_and_an_unmapped_master_is_never_disguised_as_empty(self):
        for name, doc in (("master", {"master": {"tasks": []}}), ("back", []), ("gameplay", [])):
            self.dump(inventory.TRIPLET[name], doc)
        empty = self.collect()
        self.assertEqual(empty.snapshot["frozen_a"]["candidates"], [])
        self.assert_no_authorization(empty.snapshot)
        self.dump(inventory.TRIPLET["master"], {"master": {"tasks": [{"id": 1, "status": "done"}]}})
        invalid = self.collect()
        self.assertFalse(invalid.snapshot["capture_complete"])
        self.assert_public_diagnostics(invalid.snapshot)
        self.assert_no_authorization(invalid.snapshot)

    def test_state_progress_changes_current_raw_and_state_without_definition_change(self):
        self.fixture.edit_task("master", lambda rows: rows[0].update(subtasks=[{"id": 1, "status": "pending"}]))
        baseline = self.archive()
        self.fixture.edit_task("master", lambda rows: rows[0].update(status="in-progress", subtasks=[{"id": 1, "status": "done"}]))
        before = self.all_bytes()
        compared = self.compare(baseline)
        self.assertEqual(before, self.all_bytes())
        changes = compared.report["changes"]
        self.assertEqual(changes["task_definitions"]["changed"], [])
        self.assertEqual(changes["task_states"]["changed"], [1])
        self.assertIn(inventory.TRIPLET["master"], changes["raw_files"]["changed"])
        current = compared.current.raw_files[inventory.TRIPLET["master"]]
        self.assertEqual(current, (self.root / inventory.TRIPLET["master"]).read_bytes())
        self.assert_no_authorization(compared.report)

    def test_legitimate_master_view_state_differences_are_preserved_without_writes(self):
        before = self.all_bytes()
        capture = self.collect()
        expected = [
            {"master_id": 1, "view": "back", "view_id": "BACK-9", "master_status": "done", "view_status": "pending",
             "master_pointer": "/master/tasks/0/status", "view_pointer": "/0/status",
             "authority": inventory.TRIPLET["master"], "action": "report-only"},
            {"master_id": 1, "view": "gameplay", "view_id": "GAME-1", "master_status": "done", "view_status": "review",
             "master_pointer": "/master/tasks/0/status", "view_pointer": "/0/status",
             "authority": inventory.TRIPLET["master"], "action": "report-only"},
        ]
        self.assertEqual(before, self.all_bytes())
        self.assertEqual(capture.snapshot["triplet"]["status_differences"], expected)
        self.assertEqual(capture.inventory["tasks"]["status_differences"], expected)
        self.assertEqual(capture.inventory["tasks"]["counts"], {"master": 2, "back": 2, "gameplay": 2})
        self.assertEqual(capture.inventory["tasks"]["status_authority"], inventory.TRIPLET["master"])
        output = self.archive(capture)
        verified = protection.verify_protection(self.root, self.snapshot_path(output))
        self.assertTrue(verified["ok"], verified["diagnostics"])
        self.assert_no_authorization(verified)

    def test_resigned_task_summary_cannot_hide_or_forge_current_states(self):
        capture = self.collect()
        self.assertTrue(capture.inventory["tasks"]["status_differences"])
        output = self.archive(capture)
        snapshot_path = self.snapshot_path(output)
        original_tasks = {path: (self.root / path).read_bytes() for path in inventory.TRIPLET.values()}
        mutations = (
            ("hidden-differences", lambda value: value.update(status_differences=[])),
            ("forged-state", lambda value: value["status_differences"][0].update(master_status="pending")),
            ("forged-count", lambda value: value["counts"].update(master=0)),
            ("wrong-count-type", lambda value: value["counts"].update(master=2.0)),
            ("forged-authority", lambda value: value.update(status_authority=inventory.TRIPLET["back"])),
        )
        for label, mutate in mutations:
            with self.subTest(case=label):
                report, snapshot = copy.deepcopy(capture.inventory), copy.deepcopy(capture.snapshot)
                mutate(report["tasks"])
                identity = codec.canonical_digest({key: value for key, value in report.items() if key not in protection._INVENTORY_ENVELOPE})
                report.update(content_identity=identity, second_pass_identity=identity)
                raw = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                (output / "inventory.json").write_bytes(raw)
                snapshot["inventory"].update(raw_digest=codec.raw_digest(raw), content_identity=identity)
                snapshot["triplet"]["status_differences"] = copy.deepcopy(report["tasks"]["status_differences"])
                snapshot["snapshot_digest"] = codec.canonical_digest({key: value for key, value in snapshot.items() if key != "snapshot_digest"})
                self.dump(snapshot_path, snapshot)
                verified = protection.verify_protection(self.root, snapshot_path)
                self.assertFalse(verified["ok"], "Re-signed task summaries must still match the archived triplet bytes")
                self.assert_public_diagnostics(verified)
                self.assert_no_authorization(verified)
        self.assertEqual({path: (self.root / path).read_bytes() for path in inventory.TRIPLET.values()}, original_tasks)

    def test_definition_change_does_not_invalidate_an_unrelated_task(self):
        baseline = self.archive()
        self.fixture.edit_task("back", lambda rows: rows[0].update(acceptance=["New obligation"], unknown={"status": "meaning"}))
        compared = self.compare(baseline)
        self.assertEqual(compared.report["changes"]["task_definitions"]["changed"], [1])
        self.assertEqual(compared.report["changes"]["task_states"]["changed"], [])
        self.assert_no_authorization(compared.report)

    def test_json_layout_change_affects_raw_only(self):
        baseline = self.archive()
        path = self.root / inventory.TRIPLET["back"]
        path.write_text(json.dumps(json.loads(path.read_bytes()), ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        compared = self.compare(baseline)
        self.assertEqual(compared.report["changes"]["task_definitions"]["changed"], [])
        self.assertEqual(compared.report["changes"]["task_states"]["changed"], [])
        self.assertIn(inventory.TRIPLET["back"], compared.report["changes"]["raw_files"]["changed"])

    def test_source_and_history_post_edits_are_separate_from_task_definition(self):
        baseline = self.archive()
        self.fixture.write("docs/source.md", "# Source\nChanged source meaning\nB\n")
        self.fixture.write("logs/ci/historical/explicit.json", '{"historical": "post-edited"}\n')
        before = self.all_bytes()
        compared = self.compare(baseline)
        changes = compared.report["changes"]
        self.assertEqual(changes["task_definitions"]["changed"], [])
        self.assertEqual(changes["task_states"]["changed"], [])
        self.assertEqual(changes["source_test_history_references_changed"]["changed"], [1])
        self.assertIn("docs/source.md", changes["raw_files"]["changed"])
        self.assertIn("logs/ci/historical/explicit.json", changes["raw_files"]["changed"])
        self.assertEqual(before, self.all_bytes())
        self.assert_no_authorization(compared.report)

    def test_removed_or_weakened_manifest_obligations_require_review_including_manual_limits(self):
        baseline = self.archive()
        changed = copy.deepcopy(self.fixture.manifest)
        changed["tests"][0].update(min_tests=0, state="planned")
        changed["flows"][0]["handoffs"] = []
        changed["coverage"]["excluded_claims"] = ["Rewritten manual limitation"]
        changed["unknown_manual_obligation"] = {"status": "pending", "owner": 1}
        self.dump("docs/testing/mvg/fixture.json", changed)
        compared = self.compare(baseline)
        self.assertTrue(compared.report["changes"]["manifests"])
        change = compared.report["changes"]["manifests"][0]
        self.assertTrue(change["source_backed_review_required"])
        self.assertFalse(change["source_backed_review_verified"])
        self.assertFalse(change["apply_authorized"])
        self.assertTrue(change["manual_limits_changed"])
        self.assertTrue(change["weakening_detected"])
        self.assertIn("tests/test", change["weakened_obligations"])
        self.assertFalse(compared.report["old_done_satisfies_new_obligations"])
        self.assertEqual(compared.current.inventory["manifests"][0]["document"], changed)
        self.assertEqual(compared.current.snapshot["cumulative"][0]["document"], changed)
        self.assert_no_authorization(compared.report)
        (self.root / "docs/testing/mvg/fixture.json").unlink()
        removed = self.compare(baseline)
        self.assertTrue(removed.report["changes"]["manifests"])
        self.assert_no_authorization(removed.report)

    def test_missing_historical_summary_is_explicit_and_never_formal_protection(self):
        missing = "logs/ci/historical/task-108/summary.json"
        self.fixture.edit_task("back", lambda rows: rows[0]["evidence_refs"].append(missing))
        capture = self.collect()
        self.assertFalse(capture.snapshot["capture_complete"])
        self.assertNotIn(missing, capture.raw_files)
        self.assertIn(missing, json.dumps(capture.snapshot))
        self.assert_no_authorization(capture.snapshot)
        output = self.archive(capture)
        verified = protection.verify_protection(self.root, self.snapshot_path(output))
        self.assertTrue(verified["ok"], verified["diagnostics"])
        self.assertEqual(verified["claim"], "protection_archive_integrity_only")
        self.assertFalse(verified["capture_complete"])
        self.assert_no_authorization(verified)

    def test_resigned_missing_inventory_envelope_cannot_claim_complete(self):
        missing = "logs/ci/historical/task-108/summary.json"
        self.fixture.edit_task("back", lambda rows: rows[0]["evidence_refs"].append(missing))
        capture = self.collect()
        output = self.archive(capture)
        snapshot_path = self.snapshot_path(output)
        original_snapshot, original_report = copy.deepcopy(capture.snapshot), copy.deepcopy(capture.inventory)
        self.assertTrue(any(row["severity"] == "error" for row in original_report["diagnostics"]))
        original_task = (self.root / inventory.TRIPLET["back"]).read_bytes()
        mutations = (
            ("false-complete", lambda value: value.update(adoptable=True, status="stable")),
            ("false-status", lambda value: value.update(status="stable")),
            ("nonboolean-adoptable", lambda value: value.update(adoptable=0)),
            ("input-drift", lambda value: value["drift"]["changed_inputs"].append("docs/source.md")),
            ("nonboolean-drift", lambda value: value["drift"].update(git_changed=0)),
        )
        for label, mutate in mutations:
            with self.subTest(case=label):
                report, snapshot = copy.deepcopy(original_report), copy.deepcopy(original_snapshot)
                mutate(report)
                raw = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
                (output / "inventory.json").write_bytes(raw)
                snapshot["inventory"].update(raw_digest=codec.raw_digest(raw), adoptable=report["adoptable"])
                snapshot["capture_complete"] = report["adoptable"] is True
                snapshot["snapshot_digest"] = codec.canonical_digest({key: value for key, value in snapshot.items() if key != "snapshot_digest"})
                self.dump(snapshot_path, snapshot)
                verified = protection.verify_protection(self.root, snapshot_path)
                self.assertFalse(verified["ok"], "Re-signing envelope contradictions cannot establish completeness")
                self.assert_public_diagnostics(verified)
                self.assert_no_authorization(verified)
        self.assertFalse((self.root / missing).exists())
        self.assertEqual((self.root / inventory.TRIPLET["back"]).read_bytes(), original_task)

    def test_historical_report_envelope_and_original_metadata_are_rebuilt(self):
        missing = "logs/ci/historical/task-108/summary.json"
        historical = "logs/ci/historical/missing-inventory.json"
        self.fixture.edit_task("back", lambda rows: rows[0]["evidence_refs"].append(missing))
        old = inventory.collect_inventory(self.root, self.epics)
        self.dump(historical, old)
        capture = self.collect(historical_inventory=historical)
        output = self.archive(capture)
        snapshot_path = self.snapshot_path(output)
        verified = protection.verify_protection(self.root, snapshot_path)
        self.assertTrue(verified["ok"], verified["diagnostics"])
        self.assertFalse(verified["capture_complete"])
        for field, forged in (("original_adoptable", True), ("original_diagnostics", []),
                              ("diagnostics", [{"unverified": "self-reported failure"}])):
            with self.subTest(field=field):
                snapshot = copy.deepcopy(capture.snapshot)
                snapshot["historical_inventory"][field] = forged
                snapshot["snapshot_digest"] = codec.canonical_digest({key: value for key, value in snapshot.items() if key != "snapshot_digest"})
                self.dump(snapshot_path, snapshot)
                result = protection.verify_protection(self.root, snapshot_path)
                self.assertFalse(result["ok"])
                self.assert_public_diagnostics(result)
                self.assert_no_authorization(result)
        old.update(adoptable=True, status="stable")
        self.dump(historical, old)
        forged_capture = self.collect(historical_inventory=historical)
        self.assertFalse(forged_capture.snapshot["historical_inventory"]["integrity_verified"])
        self.assertFalse(forged_capture.snapshot["capture_complete"])
        self.assert_public_diagnostics(forged_capture.snapshot)

    def test_warnings_only_inventory_remains_complete(self):
        self.fixture.edit_task("back", lambda rows: rows[0]["source_refs"].append("fixture-event"))
        capture = self.collect()
        self.assertTrue(capture.inventory["diagnostics"])
        self.assertTrue(all(row["severity"] == "warning" for row in capture.inventory["diagnostics"]))
        self.assertTrue(capture.snapshot["capture_complete"])
        output = self.archive(capture)
        verified = protection.verify_protection(self.root, self.snapshot_path(output))
        self.assertTrue(verified["ok"], verified["diagnostics"])
        self.assertTrue(verified["capture_complete"])
        self.assert_no_authorization(verified)

    def test_historical_inventory_is_bound_to_original_bytes_and_not_current_proof(self):
        old = inventory.collect_inventory(self.root, self.epics)
        historical = "logs/ci/historical/old-inventory.json"
        raw = (json.dumps(old, ensure_ascii=False, indent=3) + "\r\n").encode("utf-8")
        (self.root / historical).write_bytes(raw)
        self.fixture.edit_task("back", lambda rows: rows[0].update(title="Current definition"))
        capture = self.collect(historical_inventory=historical)
        self.assertEqual(capture.raw_files[historical], raw)
        self.assertIn("Current definition", json.dumps(capture.snapshot))
        self.assert_no_authorization(capture.snapshot)
        self.assertIn("historical", json.dumps(capture.snapshot).lower())

    def test_missing_or_corrupt_old_report_cannot_become_a_current_capture(self):
        for path in ("logs/ci/historical/missing.json", "logs/ci/historical/corrupt.json"):
            if path.endswith("corrupt.json"):
                self.fixture.write(path, '{"schema_version": "unknown", "adoptable": true}\n')
            capture = self.collect(historical_inventory=path)
            self.assertFalse(capture.snapshot["capture_complete"])
            self.assert_public_diagnostics(capture.snapshot)
            self.assert_no_authorization(capture.snapshot)

    def test_historical_only_missing_file_created_between_reads_is_observed_drift(self):
        old_only = "logs/ci/historical/old-only.json"
        historical = "logs/ci/historical/old-with-extra-inventory.json"
        self.fixture.write(old_only, '{"historical": "original"}\n')
        self.fixture.edit_task("back", lambda rows: rows[0]["evidence_refs"].append(old_only))
        self.dump(historical, inventory.collect_inventory(self.root, self.epics))
        self.fixture.edit_task("back", lambda rows: rows[0]["evidence_refs"].remove(old_only))
        (self.root / old_only).unlink()
        calls = []
        def create():
            calls.append(True)
            self.fixture.write(old_only, '{"historical": "created after missing observation"}\n')
        capture = self.collect(historical_inventory=historical, between_reads=create)
        self.assertEqual(calls, [True])
        self.assertNotIn(old_only, {row["path"] for row in capture.inventory["inputs"]})
        self.assertFalse(capture.snapshot["stable"], "Historical-only missing observations need a second read too")
        self.assertFalse(capture.snapshot["capture_complete"])
        self.assertTrue(any(row["reason_code"] == "file_changed" and old_only in json.dumps(row)
                            for row in capture.snapshot["diagnostics"]), capture.snapshot["diagnostics"])
        self.assert_no_authorization(capture.snapshot)

    def test_historical_reread_cannot_hide_a_temporary_missing_current_input(self):
        historical = "logs/ci/historical/current-inputs-inventory.json"
        self.dump(historical, inventory.collect_inventory(self.root, self.epics))
        target, calls = "docs/source.md", []
        real_read = protection._read
        def missing_on_historical_reread(root, path):
            if path == target:
                calls.append(path)
                if len(calls) == 2:
                    raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.FILE_NOT_FOUND, codec.Stage.PATH,
                        expected="readable observed input", actual="temporary missing input", resume_ref=target))
            return real_read(root, path)
        with patch.object(protection, "_read", missing_on_historical_reread):
            capture = self.collect(historical_inventory=historical)
        self.assertGreaterEqual(len(calls), 3, "The historical fault and subsequent restored read must both execute")
        self.assertFalse(capture.snapshot["stable"])
        self.assertFalse(capture.snapshot["capture_complete"])
        self.assertEqual(capture.raw_files[target], (self.root / target).read_bytes())
        self.assertTrue(any(row["reason_code"] == "file_changed" and target in json.dumps(row)
                            for row in capture.snapshot["diagnostics"]), capture.snapshot["diagnostics"])
        self.assert_no_authorization(capture.snapshot)

    def test_observed_mid_capture_edit_refuses_stability_and_preserves_current_bytes(self):
        calls = []
        def edit():
            calls.append(True)
            self.fixture.write("docs/source.md", "# Source\nChanged during capture\nB\n")
        capture = self.collect(between_reads=edit)
        self.assertEqual(calls, [True])
        self.assertFalse(capture.snapshot["capture_complete"])
        self.assertFalse(capture.snapshot["stable"])
        self.assert_public_diagnostics(capture.snapshot)
        self.assert_no_authorization(capture.snapshot)

    def test_unreadable_reference_is_reported_and_never_replaced_by_parsed_summary(self):
        target = (self.root / "docs/source.md").resolve()
        original = Path.read_bytes
        calls = []
        def denied(path):
            if path.resolve() == target:
                calls.append(path)
                raise PermissionError(13, "Synthetic read denied", str(path))
            return original(path)
        before = self.all_bytes()
        with patch.object(Path, "read_bytes", denied):
            capture = self.collect()
        self.assertTrue(calls, "The input permission fault must actually execute")
        self.assertFalse(capture.snapshot["capture_complete"])
        self.assertIn("docs/source.md", json.dumps(capture.snapshot))
        self.assert_public_diagnostics(capture.snapshot)
        self.assert_no_authorization(capture.snapshot)
        self.assertEqual(before, self.all_bytes())

    def test_verify_detects_missing_or_modified_raw_archive(self):
        output = self.archive()
        files = sorted((output / "raw").glob("*.bin"))
        self.assertTrue(files)
        target, original = files[0], files[0].read_bytes()
        for mutation in ("change", "remove"):
            with self.subTest(mutation=mutation):
                if mutation == "change":
                    target.write_bytes(original + b"corruption")
                else:
                    target.unlink()
                verified = protection.verify_protection(self.root, self.snapshot_path(output))
                self.assertFalse(verified["ok"])
                self.assert_public_diagnostics(verified)
                self.assert_no_authorization(verified)
                target.write_bytes(original)

    def test_verify_rejects_snapshot_version_claim_or_definition_tampering(self):
        output = self.archive()
        path = output / "snapshot.json"
        original = path.read_bytes()
        for label in ("schema", "authorization", "tasks", "resigned-definition", "resigned-frozen", "resigned-closure"):
            with self.subTest(case=label):
                value = json.loads(original)
                if label == "schema":
                    value["schema_version"] = "newrouge.b-route-protection.v999"
                elif label == "authorization":
                    value["authorization"]["write"] = True
                elif label in ("tasks", "resigned-definition"):
                    value["tasks"] = []
                elif label == "resigned-frozen":
                    value["frozen_a"]["candidates"][0]["status"] = "reviewed"
                else:
                    value["raw_files"] = [row for row in value["raw_files"] if row["path"] != "docs/source.md"]
                if label.startswith("resigned-"):
                    value["snapshot_digest"] = codec.canonical_digest({key: item for key, item in value.items() if key != "snapshot_digest"})
                path.write_text(json.dumps(value) + "\n", encoding="utf-8")
                verified = protection.verify_protection(self.root, self.snapshot_path(output))
                self.assertFalse(verified["ok"])
                self.assert_public_diagnostics(verified)
                self.assert_no_authorization(verified)
        path.write_bytes(original)

    def test_late_snapshot_inventory_or_raw_edit_cannot_mix_baseline_observations(self):
        baseline = self.archive()
        snapshot_path = self.snapshot_path(baseline)
        snapshot = self.load(snapshot_path)
        inventory_path = (baseline / "inventory.json").relative_to(self.root).as_posix()
        baseline_prefix = baseline.relative_to(self.root).as_posix() + "/"
        artifact_paths = [baseline_prefix + row["artifact"]
                          for row in snapshot["raw_files"] if row["exists"]]
        unique_artifacts = list(dict.fromkeys(artifact_paths))
        raw_path = next(path for path in unique_artifacts[:-1] if artifact_paths.count(path) == 1)
        real_read = protection._read
        for operation in ("verify", "compare"):
            for kind, target in (("snapshot", snapshot_path), ("inventory", inventory_path), ("raw", raw_path)):
                with self.subTest(operation=operation, changed=kind):
                    original = (self.root / target).read_bytes()
                    seen, mutations = set(), []
                    def change_after_another_artifact(root, path):
                        data = real_read(root, path)
                        should_change = target in seen and path != target and path.startswith(baseline_prefix)
                        if kind == "snapshot":
                            should_change = should_change and path == inventory_path
                        else:
                            should_change = should_change and "/raw/" in path
                        if should_change and not mutations:
                            (self.root / target).write_bytes(original + b"\n")
                            mutations.append(path)
                        seen.add(path)
                        return data
                    try:
                        with patch.object(protection, "_read", change_after_another_artifact):
                            if operation == "verify":
                                result = protection.verify_protection(self.root, snapshot_path)
                            else:
                                compared = self.compare(baseline)
                                result = compared.report
                                self.assertIsNone(result["changes"], "Differences must not use a drifting baseline")
                                self.assertEqual(compared.current.raw_files[inventory.TRIPLET["master"]],
                                                 (self.root / inventory.TRIPLET["master"]).read_bytes())
                        self.assertTrue(mutations, "The late archive mutation must actually execute")
                        self.assertFalse(result["ok"])
                        self.assertTrue(any(row["reason_code"] == "file_changed" for row in result["diagnostics"]), result["diagnostics"])
                        self.assert_no_authorization(result)
                    finally:
                        (self.root / target).write_bytes(original)

    def test_resigned_reference_closure_cannot_override_the_original_task_raw(self):
        baseline = self.archive()
        snapshot_path = self.snapshot_path(baseline)
        inv_path = (baseline / "inventory.json").relative_to(self.root).as_posix()
        report, snapshot = self.load(inv_path), self.load(snapshot_path)
        def forge(rows):
            matches = [row for row in rows if row.get("owner_file") == inventory.TRIPLET["back"]
                       and row.get("field") == "source_refs" and row.get("master_id") == 1]
            self.assertEqual(len(matches), 1)
            matches[0].update(raw_reference="docs/source.md:1", line_start=1, line_end=1)
        forge(report["task_and_manifest_references"])
        task = next(row for row in snapshot["tasks"] if row["task_id"] == 1)
        candidate = next(row for row in snapshot["frozen_a"]["candidates"] if row["task_id"] == 1)
        forge(task["source_test_history_references"])
        forge(candidate["source_scope"]["task_source_references"])
        forge(candidate["review_basis"]["source_test_history_references"])
        envelope = {"content_identity", "second_pass_identity", "drift", "collection", "stable", "adoptable", "status", "verification_limits"}
        identity = codec.canonical_digest({key: value for key, value in report.items() if key not in envelope})
        report.update(content_identity=identity, second_pass_identity=identity)
        inv_bytes = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        (self.root / inv_path).write_bytes(inv_bytes)
        snapshot["inventory"].update(content_identity=identity, raw_digest=codec.raw_digest(inv_bytes))
        snapshot["snapshot_digest"] = codec.canonical_digest({key: value for key, value in snapshot.items() if key != "snapshot_digest"})
        self.dump(snapshot_path, snapshot)
        verified = protection.verify_protection(self.root, snapshot_path)
        self.assertFalse(verified["ok"], "Re-signed derived source locators must still match the original Task bytes")
        self.assertTrue(any(row["reason_code"] == "digest_mismatch" and "reference closure" in json.dumps(row)
                            for row in verified["diagnostics"]), verified["diagnostics"])
        self.assert_no_authorization(verified)

    def test_direct_writer_refuses_external_non_log_and_link_ancestor_directories(self):
        capture = self.collect()
        with tempfile.TemporaryDirectory() as external:
            external_root = Path(external)
            outside = external_root / "outside"
            outside.mkdir()
            non_log = self.root / "unapproved-evidence"
            non_log.mkdir()
            for output in (outside, non_log):
                with self.subTest(output=str(output)), self.assertRaises(codec.CodecError):
                    protection.write_capture(output, capture)
                self.assertEqual(list(output.iterdir()), [])
            internal_root = self.root / "logs/ci/internal-writer-target"
            internal_root.mkdir()
            for label, target in (("internal", internal_root), ("external", external_root)):
                alias = self.root / ("logs/ci/writer-link-" + label)
                actual_output = target / "redirected"
                actual_output.mkdir()
                if os.name == "nt":
                    result = subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(alias), str(target)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, "Required real Windows junction setup failed: " + result.stderr)
                else:
                    alias.symlink_to(target, target_is_directory=True)
                try:
                    with self.assertRaises(codec.CodecError):
                        protection.write_capture(alias / "redirected", capture)
                    self.assertEqual(list(actual_output.iterdir()), [], "A plain output leaf cannot conceal a linked ancestor")
                finally:
                    if os.name == "nt":
                        alias.rmdir()
                    else:
                        alias.unlink()

    def test_existing_root_alias_preserves_physical_output_identity(self):
        if os.name == "nt":
            import ctypes
            short_path = ctypes.WinDLL("kernel32", use_last_error=True).GetShortPathNameW
            short_path.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
            short_path.restype = ctypes.c_uint
            size = short_path(str(self.root), None, 0)
            self.assertGreater(size, 0, "Required real Windows short-path lookup failed")
            buffer = ctypes.create_unicode_buffer(size)
            written = short_path(str(self.root), buffer, size)
            self.assertTrue(0 < written < size, "Required real Windows short-path lookup failed")
            alias_root = Path(buffer.value)
            self.assertNotEqual(str(alias_root), str(self.root.resolve()), "The real Windows root alias must be exercised")
        else:
            # A real, existing alternate spelling exercises the physical anchor
            # on POSIX; Windows keeps its distinct native 8.3 fixture above.
            (self.root / "root-spelling").mkdir()
            alias_root = self.root / "root-spelling" / ".."
        self.assertTrue(alias_root.samefile(self.root))
        capture = protection.collect_protection(alias_root, self.epics)
        self.assertEqual(str(capture.root), str(alias_root.absolute()), "Do not normalize the fixture root to conceal an alias")
        output = protection.create_run_directory(alias_root, "physical-root-alias")
        protection.write_capture(output, capture)
        expected = output.resolve().relative_to(self.root.resolve()).as_posix()
        self.assertEqual(protection._output_relative_path(alias_root, output), expected)
        code, stdout = self.run_cli("verify", "--root", str(alias_root), "--run-id", "physical-root-alias-verify",
                                    "--snapshot", expected + "/snapshot.json")
        self.assertEqual(code, 0, stdout)
        self.assertTrue(json.loads(stdout)["output"].startswith("logs/ci/"))

    def test_corrupt_baseline_compare_still_collects_current_state_without_writes(self):
        baseline = self.archive()
        (baseline / "snapshot.json").write_text("{broken", encoding="utf-8")
        self.fixture.edit_task("master", lambda rows: rows[0].update(status="in-progress"))
        before = self.all_bytes()
        compared = self.compare(baseline)
        self.assertFalse(compared.report["ok"])
        self.assertIn(b'"in-progress"', compared.current.raw_files[inventory.TRIPLET["master"]])
        self.assertEqual(before, self.all_bytes())
        self.assert_no_authorization(compared.report)

    def run_cli(self, *args):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            code = cli.main(list(args))
        return code, stdout.getvalue()

    def cli_output(self, run_id):
        return next((self.root / "logs/ci").glob("*/b-route-protection/" + run_id))

    def test_cli_capture_verify_compare_and_repeated_run_preserve_old_inputs(self):
        before = self.all_bytes()
        common = ["--root", str(self.root)]
        code, text = self.run_cli("capture", *common, "--run-id", "capture", "--epics", self.epics)
        self.assertEqual(code, 0, text)
        output = self.cli_output("capture")
        for path, digest in before.items():
            self.assertEqual(hashlib.sha256((self.root / path).read_bytes()).hexdigest(), digest, path)
        self.assertFalse(list(self.root.rglob("__pycache__")))
        after_capture = self.all_bytes()
        duplicate_code, duplicate_text = self.run_cli("capture", *common, "--run-id", "capture", "--epics", self.epics)
        self.assertNotEqual(duplicate_code, 0, duplicate_text)
        self.assertEqual(after_capture, self.all_bytes())
        code, text = self.run_cli("verify", *common, "--run-id", "verify", "--snapshot", self.snapshot_path(output))
        self.assertEqual(code, 0, text)
        code, text = self.run_cli("compare", *common, "--run-id", "compare", "--epics", self.epics, "--baseline", self.snapshot_path(output))
        self.assertEqual(code, 0, text)
        self.assertTrue((self.cli_output("compare") / "snapshot.json").is_file())

    def test_cli_bad_arguments_and_invalid_inputs_have_structured_public_errors(self):
        cases = [[], ["unknown"], ["capture", "--root", str(self.root), "--run-id", "../escape", "--epics", self.epics],
                 ["capture", "--root", str(self.root), "--run-id", "missing-epics", "--epics", "planning/missing.md"],
                 ["verify", "--root", str(self.root), "--run-id", "missing-snapshot", "--snapshot", "logs/ci/absent.json"]]
        for index, argv in enumerate(cases):
            with self.subTest(case=index):
                code, text = self.run_cli(*argv)
                self.assertNotEqual(code, 0)
                payload = json.loads(text)
                self.assert_public_diagnostics(payload)
                self.assert_no_authorization(payload)

    def test_malformed_current_manifest_compare_keeps_raw_and_snapshot_evidence(self):
        baseline = self.archive()
        manifest_path = "docs/testing/mvg/fixture.json"
        changed = copy.deepcopy(self.fixture.manifest)
        del changed["tests"][0]["id"]
        self.dump(manifest_path, changed)
        current_raw = (self.root / manifest_path).read_bytes()
        before = self.all_bytes()
        code, stdout = self.run_cli("compare", "--root", str(self.root), "--run-id", "malformed-current",
                                    "--epics", self.epics, "--baseline", self.snapshot_path(baseline))
        self.assertEqual(code, 1, stdout)
        result = json.loads(stdout)
        self.assertFalse(result["ok"])
        self.assert_public_diagnostics(result)
        self.assert_no_authorization(result)
        output = self.cli_output("malformed-current")
        self.assertTrue((output / "snapshot.json").is_file())
        self.assertTrue((output / "comparison.json").is_file())
        snapshot = json.loads((output / "snapshot.json").read_bytes())
        raw_ref = next(row for row in snapshot["raw_files"] if row["path"] == manifest_path)
        self.assertEqual((output / raw_ref["artifact"]).read_bytes(), current_raw)
        self.assertEqual(snapshot["cumulative"][0]["document"], changed)
        for path, digest in before.items():
            self.assertEqual(hashlib.sha256((self.root / path).read_bytes()).hexdigest(), digest, path)

    def test_real_directory_links_cannot_redirect_snapshot_reads_or_output(self):
        baseline = self.archive()
        with tempfile.TemporaryDirectory() as external:
            for label, target in (("internal", baseline), ("external", Path(external))):
                alias = self.root / ("logs/ci/" + label + "-link")
                if os.name == "nt":
                    result = subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(alias), str(target)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, "Required real Windows junction setup failed: " + result.stderr)
                else:
                    alias.symlink_to(target, target_is_directory=True)
                try:
                    verified = protection.verify_protection(self.root, alias.relative_to(self.root).as_posix() + "/snapshot.json")
                    self.assertFalse(verified["ok"])
                    self.assert_no_authorization(verified)
                finally:
                    if os.name == "nt":
                        alias.rmdir()
                    else:
                        alias.unlink()
            original = self.root / "logs/ci"
            saved = self.root / "logs/original-ci"
            original.rename(saved)
            if os.name == "nt":
                result = subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(original), external], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, "Required real Windows junction setup failed: " + result.stderr)
            else:
                original.symlink_to(Path(external), target_is_directory=True)
            try:
                code, text = self.run_cli("capture", "--root", str(self.root), "--run-id", "unsafe-output", "--epics", self.epics)
                self.assertNotEqual(code, 0, text)
                self.assertEqual(list(Path(external).iterdir()), [], "No redirected output may be created")
            finally:
                if os.name == "nt":
                    original.rmdir()
                else:
                    original.unlink()
                saved.rename(original)


if __name__ == "__main__":
    unittest.main()
