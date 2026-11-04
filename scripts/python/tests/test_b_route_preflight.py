"""Migration preflight behavior and independent CLI matrix over synthetic bytes."""
from __future__ import annotations

import copy
import contextlib
import io
import hashlib
import importlib
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _b_route_codec as codec
import _b_route_inventory as inventory
import _b_route_preflight as preflight
import _b_route_protection as protection

REPOSITORY = Path(__file__).resolve().parents[3]
FIELDS = {"reason_code", "stage", "entity_id", "expected", "actual", "resume_ref"}
CASES = ("success", "missing-input", "unknown-version", "path-escape", "state-overwrite",
         "unsupported-retirement", "old-pending", "zero-task")


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def identity(data):
    # Independent expected raw hash, not the implementation under test.
    return "sha256:" + hashlib.sha256(data).hexdigest()


class Fixture:
    def __init__(self, *, zero_tasks=False):
        fixtures = importlib.import_module("test_b_route_inventory")
        self.base = fixtures.InventoryTests(methodName="runTest")
        self.base.setUp()
        self.root, self.epics = self.base.root, self.base.epics
        self.write(preflight.ADR, "# Synthetic authority\n- Status: Accepted\n"
            "本文不冻结 A、不切换默认 B、不退出 A\n迁移启用前沿显式原入口执行当前 A\n")
        self.write("docs/review.md", "# Synthetic external review input\nInspect the requirement change.\n")
        if zero_tasks:
            for name, source in inventory.TRIPLET.items():
                self.dump(source, {"master": {"tasks": []}} if name == "master" else [])
        if zero_tasks:
            (self.root / "docs/testing/mvg/fixture.json").unlink()
        capture = protection.collect_protection(self.root, self.epics)
        if not capture.snapshot["capture_complete"] and not (zero_tasks and
                {row["code"] for row in capture.inventory["diagnostics"]} == {"missing-manifests"}):
            self.base.tearDown()
            raise AssertionError(capture.inventory["diagnostics"])
        self.archive = "logs/ci/preflight-fixture/protection"
        output = self.root / self.archive
        output.mkdir(parents=True)
        protection.write_capture(output, capture)
        self.protection_input = "logs/ci/preflight-fixture/protection-input.json"
        self.candidate_path = "logs/ci/preflight-fixture/candidate.json"
        self.intents_path = "logs/ci/preflight-fixture/intents.json"
        snap = self.archive + "/snapshot.json"
        inv = self.archive + "/inventory.json"
        self.dump(self.protection_input, {
            "document_version": preflight.PROTECTION_VERSION,
            "definition": {"projection_codec": codec.PROJECTION_CODEC, "content_codec": codec.CODEC_VERSION,
                "mutable_allowlist": ["Task.status", "Task.subtasks[].status"]},
            "authorization": dict(protection.AUTHORIZATION),
            "inventory_ref": self.owned("frozen_a_inventory", inv),
            "snapshot_ref": self.owned("frozen_a_inventory", snap),
            "task_definitions_ref": self.owned("frozen_a_inventory", snap + "#/tasks"),
            "triplet_definition_ref": self.owned("frozen_a_inventory", snap + "#/triplet/definition"),
            "raw_archive_index_ref": self.owned("frozen_a_inventory", snap + "#/raw_files"),
            "frozen_a_candidates_ref": self.owned("frozen_a_inventory", snap + "#/frozen_a/candidates"),
            "manifest_refs": [] if zero_tasks else [self.owned("manifest", "docs/testing/mvg/fixture.json")],
            "review": {"evidence_ref": self.owned("authority", "docs/review.md")},
            "unresolved": [],
        })
        self.candidate = {}
        self.set_candidate({"docs/new-source.md": b"# New source\nA declared future responsibility.\n"})

    def close(self):
        self.base.tearDown()

    def write(self, source, value):
        self.base.write(source, value)

    def dump(self, source, value):
        self.base.dump(source, value)

    def load(self, source):
        return self.base.load(source)

    def raw(self, source):
        return (self.root / source).read_bytes()

    def owned(self, owner, ref):
        source = ref.split("#", 1)[0]
        return {"owner": owner, "ref": ref,
                "files": [{"path": source, "raw_digest": identity(self.raw(source))}]}

    def bind(self, source):
        target = self.root / source
        return {"path": source, "raw_digest": identity(target.read_bytes()) if target.is_file() else None}

    def set_candidate(self, candidates):
        self.candidate = copy.deepcopy(candidates)
        rows = []
        for index, (logical, raw) in enumerate(candidates.items()):
            original = f"logs/ci/preflight-fixture/candidates/{index}.bin"
            target = self.root / original
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            rows.append({"path": logical, "source_path": original})
        self.dump(self.candidate_path, {"records": rows})
        self.rebind()

    def rebind(self):
        # Expected entity locators and definitions are constructed independently.
        before_docs = {name: self.load(source) for name, source in inventory.TRIPLET.items()}
        after_docs = {name: json.loads(self.candidate[source]) if source in self.candidate else before_docs[name]
                      for name, source in inventory.TRIPLET.items()}
        def entities(docs, after=False):
            result = {}
            for name, doc in docs.items():
                source = inventory.TRIPLET[name]
                raw = self.candidate.get(source, self.raw(source)) if after else self.raw(source)
                for index, row in enumerate(doc["master"]["tasks"] if name == "master" else doc):
                    task_id = row["id"] if name == "master" else row["taskmaster_id"]
                    value = result.setdefault(task_id, {"master": [], "back": [], "gameplay": [], "locators": []})
                    projected = copy.deepcopy(row)
                    projected.pop("status", None)
                    for subtask in projected.get("subtasks", []):
                        subtask.pop("status", None)
                    value[name].append(projected)
                    value["locators"].append({"path": source, "json_pointer":
                        ("/master/tasks/" if name == "master" else "/") + str(index), "raw_digest": identity(raw)})
            return result
        old, new = entities(before_docs), entities(after_docs, True)
        changes = []
        for task_id in sorted(set(old) | set(new), key=str):
            a, b = old.get(task_id), new.get(task_id)
            a_def = {key: value for key, value in a.items() if key != "locators"} if a else None
            b_def = {key: value for key, value in b.items() if key != "locators"} if b else None
            operation = "new" if a is None else "retire" if b is None else "reuse" if json.dumps(a_def, sort_keys=True) == json.dumps(b_def, sort_keys=True) else "update"
            if operation != "reuse" or any(source in self.candidate for source in inventory.TRIPLET.values()):
                changes.append(self.intent("task", task_id, operation,
                    a["locators"] if a else [], b["locators"] if b else []))
        def envelope(docs):
            master = docs["master"]
            return {**{key: copy.deepcopy(value) for key, value in master.items() if key != "master"},
                "master": {key: copy.deepcopy(value) for key, value in master["master"].items() if key != "tasks"}}
        def ordering(docs):
            return {name: [row["id"] for row in (doc["master"]["tasks"] if name == "master" else doc)]
                    for name, doc in docs.items()}
        if envelope(before_docs) != envelope(after_docs) or ordering(before_docs) != ordering(after_docs):
            changes.append(self.intent("file", "task-triplet-envelope", "update",
                [{"path": source, "json_pointer": "", "raw_digest": identity(self.raw(source))}
                    for source in inventory.TRIPLET.values()],
                [{"path": source, "json_pointer": "", "raw_digest": identity(self.candidate.get(source, self.raw(source)))}
                    for source in inventory.TRIPLET.values()]))
        for source, raw in self.candidate.items():
            if source in inventory.TRIPLET.values():
                continue
            a = self.raw(source) if (self.root / source).is_file() else None
            def decoded(raw):
                return json.loads(raw) if source.endswith(".json") else raw.decode("utf-8")
            operation = "new" if a is None else "reuse" if decoded(a) == decoded(raw) else "update"
            changes.append(self.intent("file", source, operation,
                [{"path": source, "json_pointer": "", "raw_digest": identity(a)}] if a else [],
                [{"path": source, "json_pointer": "", "raw_digest": identity(raw)}]))
            if source.startswith("docs/testing/mvg/"):
                old_manifest, new_manifest = json.loads(a) if a else {}, json.loads(raw)
                for section in ("flows", "tests"):
                    left = {item["id"]: (index, item) for index, item in enumerate(old_manifest.get(section, []))}
                    right = {item["id"]: (index, item) for index, item in enumerate(new_manifest.get(section, []))}
                    for entity in sorted(set(left) | set(right)):
                        old_row, new_row = left.get(entity), right.get(entity)
                        if old_row and new_row and old_row[1] == new_row[1]:
                            continue
                        action = "new" if old_row is None else "retire" if new_row is None else "update"
                        def locator(row, data):
                            return [] if row is None else [{"path": source, "json_pointer": "/" + section + "/" + str(row[0]),
                                "raw_digest": identity(data)}]
                        changes.append(self.intent("obligation", source + "#/" + section + "/" + entity, action,
                                                   locator(old_row, a), locator(new_row, raw)))
        self.dump(self.intents_path, {"document_version": preflight.INTENTS_VERSION, "scope_id": "synthetic-migration",
            "inputs": {"epics": self.bind(self.epics), "protection_input": self.bind(self.protection_input),
                "inventory": self.bind(self.archive + "/inventory.json"),
                "targets": [self.bind(source) for source in sorted(set(self.candidate) | set(inventory.TRIPLET.values()))]},
            "changes": changes, "unresolved": []})

    def intent(self, kind, entity, operation, before, after):
        return {"scope_id": "synthetic-migration", "entity_type": kind, "entity_id": entity, "operation": operation,
            "before": before, "after": after, "source_refs": [self.owned("authority", "docs/source.md#L2-L3")],
            "reason": "Explicit synthetic reviewed proposal; semantic approval remains unverified.",
            "review_ref": self.owned("authority", "docs/review.md#L2"), "unresolved": []}

    def preview(self, **kwargs):
        return preflight.preflight(self.root, self.epics, self.protection_input,
                                   self.candidate_path, self.intents_path, **kwargs)

    def arguments(self, run_id="preview"):
        return ["--root", str(self.root), "--epics", self.epics, "--protection-input", self.protection_input,
                "--candidate", self.candidate_path, "--intents", self.intents_path, "--run-id", run_id]

    def bytes(self):
        return {item.relative_to(self.root).as_posix(): identity(item.read_bytes()) for item in self.root.rglob("*")
                if item.is_file() and ".git" not in item.parts}

    def cli(self, run_id="preview", *, direct=False, extra=None):
        entry = "preflight_b_route_migration.py" if direct else "dev_cli.py"
        command = [sys.executable, "-B", str(REPOSITORY / "scripts/python" / entry)]
        if not direct:
            command.append("b-route-preflight")
        return subprocess.run(command + self.arguments(run_id) + (extra or []),
                              capture_output=True, text=True, encoding="utf-8", timeout=30)


def configure_case(fixture, case):
    if case == "missing-input":
        (fixture.root / fixture.candidate_path).unlink()
    elif case == "unknown-version":
        value = fixture.load(fixture.intents_path)
        value["document_version"] = "newrouge.b-route-preflight-intents.v99"
        fixture.dump(fixture.intents_path, value)
    elif case == "path-escape":
        fixture.dump(fixture.candidate_path, {"records": [{"path": "../outside.json", "source_path": "docs/source.md"}]})
    elif case == "state-overwrite":
        docs = {source: fixture.load(source) for source in inventory.TRIPLET.values()}
        docs[inventory.TRIPLET["master"]]["master"]["tasks"][0]["status"] = "pending"
        fixture.set_candidate({source: encode(doc) for source, doc in docs.items()})
    elif case == "unsupported-retirement":
        source = "docs/testing/mvg/fixture.json"
        doc = fixture.load(source)
        doc["flows"] = []
        fixture.set_candidate({source: encode(doc)})
    elif case == "old-pending":
        fixture.dump("logs/ci/preflight-fixture/old-journal.json", {
            "schema_version": "newrouge.planning-apply-journal.v1", "status": "pending",
            "entries": [{"path": "docs/source.md"}], "authority_inputs": {"docs/review.md": None}})
        fixture.dump(preflight.PENDING, {"run_id": "old-run", "journal_path": "logs/ci/preflight-fixture/old-journal.json"})


def run_cli_matrix(output):
    """Eight real subprocess cases; persist synthetic reports and byte guards only."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    summary = []
    started = time.perf_counter()
    for case in CASES:
        fixture = Fixture(zero_tasks=case == "zero-task")
        try:
            configure_case(fixture, case)
            before = fixture.bytes()
            cli_started = time.perf_counter()
            completed = fixture.cli()
            cli_elapsed = time.perf_counter() - cli_started
            report = json.loads(completed.stdout)
            after = fixture.bytes()
            original_ok = all(after.get(source) == value for source, value in before.items())
            added = sorted(set(after) - set(before))
            added_ok = all("/b-route-preflight/preview/" in source and source.endswith("/report.json") for source in added)
            expected = 0 if case in ("success", "zero-task") else 1
            if completed.returncode != expected or completed.stderr or not original_ok or not added_ok:
                raise AssertionError({"case": case, "expected": expected, "actual": completed.returncode,
                    "stderr": completed.stderr, "diagnostics": report.get("diagnostics"), "byte_guard": original_ok,
                    "unexpected_outputs": added})
            (output / (case + ".json")).write_bytes(encode(report))
            summary.append({"case": case, "exit_code": completed.returncode, "original_bytes_unchanged": original_ok,
                            "only_fresh_log_report_added": added_ok, "diagnostics": report["diagnostics"],
                            "difference_identity": report["difference_identity"], "cli_elapsed_seconds": cli_elapsed})
        finally:
            fixture.close()
    (output / "summary.json").write_bytes(encode({"platform": sys.platform, "python": sys.version,
        "case_count": len(summary), "cases": summary, "synthetic_only": True,
        "elapsed_seconds": time.perf_counter() - started}))
    return summary


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.fixture = Fixture()
        self.addCleanup(self.fixture.close)

    def assert_failed(self, report, reason=None):
        self.assertFalse(report["ok"], report)
        self.assertTrue(report["diagnostics"])
        if reason:
            self.assertIn(reason, {row["reason_code"] for row in report["diagnostics"]}, report["diagnostics"])
        for diagnostic in report["diagnostics"]:
            self.assertEqual(set(diagnostic), FIELDS)
        self.assertEqual(report["authorization"], protection.AUTHORIZATION)

    def test_success_exact_changes_identities_semantic_limits_and_no_writes(self):
        before = self.fixture.bytes()
        report = self.fixture.preview()
        self.assertTrue(report["ok"], report["diagnostics"])
        self.assertEqual(self.fixture.bytes(), before)
        self.assertEqual({(row["entity_type"], row["entity_id"], row["operation"]) for row in report["changes"]},
                         {("task", 1, "reuse"), ("task", 2, "reuse"), ("file", "docs/new-source.md", "new")})
        source = next(row for row in report["changes"] if row["category"] == "source")
        self.assertEqual(source["before"], [])
        self.assertEqual(source["after"], [{"path": "docs/new-source.md", "json_pointer": "",
            "raw_digest": identity(self.fixture.candidate["docs/new-source.md"])}])
        self.assertEqual(report["governance"]["state"], "explicitly_not_enabled")
        self.assertFalse(report["candidate_validation"]["relationships_verified"])
        self.assertFalse(report["old_done_satisfies_new_obligations"])
        self.assertEqual(report["authorization"], protection.AUTHORIZATION)
        self.assertTrue(all(row["locator_and_digest_verified"] and not row["source_semantics_verified"]
                            and not row["external_review_verified"] for row in report["semantic_review_inputs"]))

    def test_repeated_preview_has_same_identity_and_no_candidate_generation(self):
        before = self.fixture.bytes()
        one, two = self.fixture.preview(), self.fixture.preview()
        self.assertTrue(one["ok"], one["diagnostics"])
        self.assertEqual(one["difference_identity"], two["difference_identity"])
        self.assertEqual(before, self.fixture.bytes())

    def test_current_status_progress_is_preserved_and_not_definition_change(self):
        source = inventory.TRIPLET["master"]
        doc = self.fixture.load(source)
        doc["master"]["tasks"][1]["status"] = "in-progress"
        self.fixture.dump(source, doc)
        self.fixture.rebind()
        report = self.fixture.preview()
        self.assertTrue(report["ok"], report["diagnostics"])
        self.assertFalse(report["protection_to_current"]["triplet_definition_changed"])
        task = next(row for row in report["changes"] if row["entity_id"] == 2)
        self.assertEqual(task["before_state"]["master"][0]["status"], "in-progress")
        self.assertEqual(task["before_state"], task["after_state"])

    def test_full_candidate_update_keeps_done_and_history(self):
        docs = {source: self.fixture.load(source) for source in inventory.TRIPLET.values()}
        docs[inventory.TRIPLET["master"]]["master"]["tasks"][0]["title"] = "Additional responsibility"
        self.fixture.set_candidate({source: encode(doc) for source, doc in docs.items()})
        report = self.fixture.preview()
        self.assertTrue(report["ok"], report["diagnostics"])
        self.assertEqual([(row["entity_id"], row["operation"]) for row in report["changes"]], [(1, "update"), (2, "reuse")])
        self.assertFalse(report["old_done_satisfies_new_obligations"])

    def test_status_overwrite_and_history_removal_block_with_entity(self):
        configure_case(self.fixture, "state-overwrite")
        report = self.fixture.preview()
        self.assert_failed(report, "conflict")
        self.assertIn("1", {row["entity_id"] for row in report["diagnostics"]})
        docs = {source: self.fixture.load(source) for source in inventory.TRIPLET.values()}
        docs[inventory.TRIPLET["master"]]["master"]["tasks"][0]["history"] = []
        self.fixture.set_candidate({source: encode(doc) for source, doc in docs.items()})
        self.assert_failed(self.fixture.preview(), "conflict")

    def test_strict_join_duplicate_ids_string_ids_and_partial_triplet(self):
        for mutate in (lambda docs: docs["back"][0].update(taskmaster_id="1"),
                       lambda docs: docs["back"].append(copy.deepcopy(docs["back"][0])),
                       lambda docs: docs["master"]["master"]["tasks"].append({"id": 1, "status": "done"})):
            docs = {name: self.fixture.load(source) for name, source in inventory.TRIPLET.items()}
            mutate(docs)
            self.fixture.set_candidate({inventory.TRIPLET[name]: encode(doc) for name, doc in docs.items()})
            self.assert_failed(self.fixture.preview())
        self.fixture.set_candidate({inventory.TRIPLET["master"]: self.fixture.raw(inventory.TRIPLET["master"])})
        self.assert_failed(self.fixture.preview(), "mapping_mismatch")

    def test_mature_id_removal_and_business_id_reassignment_block(self):
        docs = {source: self.fixture.load(source) for source in inventory.TRIPLET.values()}
        for source in inventory.TRIPLET.values():
            rows = docs[source]["master"]["tasks"] if source == inventory.TRIPLET["master"] else docs[source]
            rows.pop()
        self.fixture.set_candidate({source: encode(doc) for source, doc in docs.items()})
        self.assert_failed(self.fixture.preview(), "conflict")
        docs = {source: self.fixture.load(source) for source in inventory.TRIPLET.values()}
        docs[inventory.TRIPLET["back"]][0]["id"] = "BACK-NEW"
        self.fixture.set_candidate({source: encode(doc) for source, doc in docs.items()})
        self.assert_failed(self.fixture.preview(), "mapping_mismatch")

    def test_retirement_and_lower_test_coverage_require_real_semantic_review(self):
        configure_case(self.fixture, "unsupported-retirement")
        report = self.fixture.preview()
        self.assert_failed(report, "semantic_error")
        self.assertEqual(report["cumulative_changes"][0]["removed_obligations"], ["flows/flow"])
        self.assertFalse(report["cumulative_changes"][0]["source_backed_review_verified"])
        doc = self.fixture.load("docs/testing/mvg/fixture.json")
        doc["tests"][0]["min_tests"] = 0
        self.fixture.set_candidate({"docs/testing/mvg/fixture.json": encode(doc)})
        self.assert_failed(self.fixture.preview(), "semantic_error")

    def test_additive_manifest_obligation_never_claims_old_done_satisfies_it(self):
        doc = self.fixture.load("docs/testing/mvg/fixture.json")
        test = copy.deepcopy(doc["tests"][0]); test["id"] = "new-test"; test["state"] = "planned"
        doc["tests"].append(test)
        doc["flows"][0]["test_ids"].append("new-test")
        self.fixture.set_candidate({"docs/testing/mvg/fixture.json": encode(doc)})
        report = self.fixture.preview()
        self.assertTrue(report["ok"], report["diagnostics"])
        self.assertEqual(report["cumulative_changes"][0]["added_obligations"], ["tests/new-test"])
        self.assertFalse(report["old_done_satisfies_new_obligations"])

    def test_intent_unknown_version_missing_declaration_conflict_and_raw_mismatch(self):
        original = self.fixture.load(self.fixture.intents_path)
        for mutate, reason in (
            (lambda value: value.update(document_version="v99"), "unknown_schema"),
            (lambda value: value.update(changes=[]), "missing_required_field"),
            (lambda value: value["changes"][0].update(operation="reuse"), "conflict"),
            (lambda value: value["changes"].append(copy.deepcopy(value["changes"][0])), "conflict"),
            (lambda value: value["changes"][0]["after"][0].update(raw_digest="sha256:" + "0" * 64), "digest_mismatch"),
            (lambda value: value["inputs"]["targets"][0].update(raw_digest="sha256:" + "0" * 64), "input_stale"),
            (lambda value: value.update(enabled=True), "invalid_type"),
        ):
            value = copy.deepcopy(original); mutate(value); self.fixture.dump(self.fixture.intents_path, value)
            self.assert_failed(self.fixture.preview(), reason)

    def test_owned_review_locator_digest_and_source_support_are_not_self_approved(self):
        value = self.fixture.load(self.fixture.intents_path)
        value["changes"][0]["review_ref"]["ref"] = "docs/review.md#L999"
        self.fixture.dump(self.fixture.intents_path, value)
        self.assert_failed(self.fixture.preview(), "unresolved_reference")
        value["changes"][0]["review_ref"] = self.fixture.owned("authority", "docs/review.md")
        value["changes"][0]["source_refs"][0]["files"][0]["raw_digest"] = "sha256:" + "0" * 64
        self.fixture.dump(self.fixture.intents_path, value)
        self.assert_failed(self.fixture.preview(), "digest_mismatch")

    def test_governance_trace_with_missing_policy_never_becomes_legacy(self):
        self.fixture.dump("docs/planning/b-route/plans/p/1.json", {"schema_version": "newrouge.b-route-plan.v1"})
        report = self.fixture.preview()
        self.assert_failed(report, "required_governance_missing")
        self.assertEqual(report["governance"]["state"], "unknown_or_damaged")
        self.assertFalse(report["governance"]["activation_authorized"])

    def test_missing_adr_is_unknown_not_not_enabled(self):
        self.fixture.write(preflight.ADR, self.fixture.raw(preflight.ADR).decode("utf-8") + "- Status: Proposed\n")
        conflicting = self.fixture.preview()
        self.assert_failed(conflicting, "identity_unprovable")
        self.assertEqual(conflicting["governance"]["state"], "unknown_or_damaged")
        (self.fixture.root / preflight.ADR).unlink()
        report = self.fixture.preview()
        self.assert_failed(report)
        self.assertEqual(report["governance"]["state"], "unknown_or_damaged")

    def test_old_pending_kept_unknown_scope_and_original_recovery_navigation(self):
        configure_case(self.fixture, "old-pending")
        before = self.fixture.bytes()
        report = self.fixture.preview()
        self.assert_failed(report, "pending")
        self.assertEqual(report["pending"]["state"], "pending_unknown_scope")
        self.assertIn("--stage apply --run-id old-run --confirm", report["pending"]["resume_ref"])
        self.assertEqual(self.fixture.bytes(), before)
        self.assertIn("logs/ci/preflight-fixture/old-journal.json", {row["path"] for row in report["observations"]})
        marker = self.fixture.load(preflight.PENDING)
        marker["run_id"] = "old-run;echo"
        self.fixture.dump(preflight.PENDING, marker)
        before = self.fixture.bytes()
        self.assert_failed(self.fixture.preview(), "invalid_argument")
        self.assertEqual(before, self.fixture.bytes())

    def test_actual_post_edit_of_all_input_classes_invalidates_conclusion(self):
        for source in (self.fixture.epics, self.fixture.protection_input, self.fixture.candidate_path,
                       self.fixture.intents_path, "docs/source.md", "docs/review.md", inventory.TRIPLET["master"],
                       "docs/testing/mvg/fixture.json", preflight.ADR, self.fixture.archive + "/snapshot.json",
                       self.fixture.archive + "/inventory.json"):
            original = self.fixture.raw(source)
            hit = []
            def edit():
                hit.append(source)
                (self.fixture.root / source).write_bytes(original + b"\n")
            report = self.fixture.preview(before_reread=edit)
            self.assertEqual(hit, [source], "Fault hook must execute")
            self.assert_failed(report, "file_changed")
            self.assertFalse(report["stable"])
            self.assertFalse(report["conclusion_valid"])
            (self.fixture.root / source).write_bytes(original)

    def test_absence_observations_and_new_governance_membership_are_reread(self):
        for source in (preflight.GOVERNANCE[0], preflight.PENDING, "docs/new-source.md",
                       "docs/planning/b-route/plans/new/1.json"):
            hits = []
            def add():
                hits.append(source); self.fixture.dump(source, {})
            report = self.fixture.preview(before_reread=add)
            self.assertEqual(hits, [source])
            self.assert_failed(report, "file_changed")
            self.assertFalse(report["conclusion_valid"])
            (self.fixture.root / source).unlink()

    def test_paths_duplicates_and_versions_are_strict(self):
        original = self.fixture.load(self.fixture.candidate_path)
        for source in ("../escape.json", "C:/outside.json", "docs/CON.txt", "docs/../source.md", "docs//source.md"):
            self.fixture.dump(self.fixture.candidate_path, {"records": [{"path": source, "source_path": "docs/source.md"}]})
            self.assert_failed(self.fixture.preview(), "unsafe_path")
        original["records"].append(copy.deepcopy(original["records"][0]))
        self.fixture.dump(self.fixture.candidate_path, original)
        self.assert_failed(self.fixture.preview(), "conflict")

    def test_duplicate_json_key_is_not_last_value_wins(self):
        (self.fixture.root / self.fixture.candidate_path).write_bytes(b'{"records":[],"records":[]}')
        self.assert_failed(self.fixture.preview(), "duplicate_key")

    def test_cli_direct_dispatch_json_exit_codes_persisted_report_and_raw_guard(self):
        before = self.fixture.bytes()
        first = self.fixture.cli("dispatch")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertEqual(first.stderr, "")
        report = json.loads(first.stdout)
        self.assertEqual(json.loads(self.fixture.raw(report["report_path"])), report)
        second = self.fixture.cli("direct", direct=True)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(json.loads(second.stdout)["difference_identity"], report["difference_identity"])
        current = self.fixture.bytes()
        self.assertTrue(all(current.get(source) == digest for source, digest in before.items()))
        self.assertTrue(all("/b-route-preflight/" in source and source.endswith("/report.json") for source in set(current) - set(before)))
        third = self.fixture.cli("dispatch")
        self.assertEqual(third.returncode, 2, third.stdout + third.stderr)
        self.assertEqual(json.loads(third.stdout)["diagnostics"][0]["reason_code"], "conflict")

    def test_cli_argument_failure_unknown_apply_and_bad_run_are_public_diagnostics(self):
        for extra in (["--apply"], ["--run-id", "../escape"], ["--unknown"]):
            completed = self.fixture.cli(extra=extra)
            self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
            value = json.loads(completed.stdout)
            self.assertEqual(set(value["diagnostics"][0]), FIELDS)
            self.assertEqual(completed.stderr, "")
        completed = subprocess.run([sys.executable, "-B", str(REPOSITORY / "scripts/python/dev_cli.py"), "b-route-preflight"],
                                   capture_output=True, text=True, timeout=30)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(json.loads(completed.stdout)["diagnostics"][0]["reason_code"], "invalid_argument")

    def test_zero_task_without_fake_readiness(self):
        fixture = Fixture(zero_tasks=True)
        self.addCleanup(fixture.close)
        report = fixture.preview()
        self.assertTrue(report["ok"], report["diagnostics"])
        self.assertFalse(any(row["entity_type"] == "task" for row in report["changes"]))
        self.assertEqual(fixture.load(inventory.TRIPLET["master"]), {"master": {"tasks": []}})

    def test_pre_catalog_six_schema_planned_and_zero_task_shape_remain_legitimate(self):
        module = importlib.import_module("test_b_route_records")
        matrix = module.MatrixFixture()
        plan_path = module.plan_path()
        matrix.add_flow(plan_path)
        binding_path = matrix.add_binding(task_id=1)
        binding = matrix.bindings[binding_path][0]
        binding["stage"] = "4"
        binding["implementation_objects"] = [{"id": "adapter", "kind": "adapter", "availability": "planned",
            "responsible_task_ids": [1], "expected_type": "SyntheticAdapter", "lifecycle": "Scene-owned",
            "target_ref": None, "later_checks": ["compile", "type"]}]
        all_bytes = matrix.render()
        for source, raw in all_bytes.items():
            if not preflight.records._managed_candidate(source):
                target = self.fixture.root / source
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
        self.fixture.set_candidate({plan_path: all_bytes[plan_path], binding_path: all_bytes[binding_path]})
        report = self.fixture.preview()
        self.assertTrue(report["ok"], report["diagnostics"])
        self.assertFalse(report["candidate_validation"]["relationships_verified"])
        self.assertEqual(len(report["candidate_validation"]["records"]), 2)
        self.assertFalse((self.fixture.root / "Game.Godot/SyntheticAdapter.cs").exists())

    def test_candidate_catalog_uses_unique_bundle_validator_without_fake_records(self):
        module = importlib.import_module("test_b_route_records")
        matrix = module.MatrixFixture()
        all_bytes = matrix.render()
        for source, raw in all_bytes.items():
            if not preflight.records._managed_candidate(source):
                target = self.fixture.root / source
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
        self.fixture.set_candidate({source: raw for source, raw in all_bytes.items()
                                    if preflight.records._managed_candidate(source)})
        report = self.fixture.preview()
        self.assertTrue(report["ok"], report["diagnostics"])
        self.assertEqual(report["candidate_validation"]["claim"], "candidate_structure_only")
        self.assertTrue(report["candidate_validation"]["references_validated"])
        self.assertFalse(report["candidate_validation"]["target_projection_verified"])
        self.assertFalse((self.fixture.root / preflight.records.CATALOG_PATH).exists())

    def test_individual_obligation_retirement_requires_explicit_retire_intent(self):
        configure_case(self.fixture, "unsupported-retirement")
        value = self.fixture.load(self.fixture.intents_path)
        self.assertEqual(value["changes"][1]["entity_type"], "obligation")
        self.assertEqual(value["changes"][1]["operation"], "retire")
        value["changes"] = value["changes"][:1]
        self.fixture.dump(self.fixture.intents_path, value)
        self.assert_failed(self.fixture.preview(), "missing_required_field")

    def test_deleted_b_origin_and_plan_membership_cannot_downgrade(self):
        module = importlib.import_module("test_b_route_records")
        matrix = module.MatrixFixture()
        matrix.add_binding(task_id=1)
        all_bytes = matrix.render()
        for source, raw in all_bytes.items():
            target = self.fixture.root / source
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        original = json.loads(all_bytes[preflight.GOVERNANCE[2]])
        original["tasks"] = []
        self.fixture.set_candidate({preflight.GOVERNANCE[2]: encode(original)})
        report = self.fixture.preview()
        self.assert_failed(report, "mapping_mismatch")
        self.assertIn("1", {row["entity_id"] for row in report["diagnostics"]})

    def test_input_archive_missing_original_and_corrupt_schema_never_get_approval(self):
        value = self.fixture.load(self.fixture.protection_input)
        value["authorization"]["formal_protection_baseline"] = True
        self.fixture.dump(self.fixture.protection_input, value)
        self.fixture.rebind()
        self.assert_failed(self.fixture.preview(), "conflict")

    def test_new_task_and_subtask_have_explicit_identity_and_keep_mature_progress(self):
        docs = {source: self.fixture.load(source) for source in inventory.TRIPLET.values()}
        docs[inventory.TRIPLET["master"]]["master"]["tasks"].append({"id": 30, "status": "pending", "title": "Real gap"})
        docs[inventory.TRIPLET["back"]].append({"id": "BACK-30", "taskmaster_id": 30, "status": "pending"})
        docs[inventory.TRIPLET["master"]]["master"]["tasks"][0]["subtasks"] = [{"id": 9, "status": "pending"}]
        self.fixture.set_candidate({source: encode(doc) for source, doc in docs.items()})
        report = self.fixture.preview()
        self.assertTrue(report["ok"], report["diagnostics"])
        task = next(row for row in report["changes"] if row["entity_type"] == "task" and row["entity_id"] == 30)
        self.assertEqual(task["operation"], "new")
        self.assertEqual(task["before"], [])
        self.assertEqual(self.fixture.load(inventory.TRIPLET["master"])["master"]["tasks"][0]["status"], "done")

    def test_candidate_source_archive_and_old_journal_are_in_final_reread(self):
        configure_case(self.fixture, "old-pending")
        candidate_source = self.fixture.load(self.fixture.candidate_path)["records"][0]["source_path"]
        snapshot = self.fixture.load(self.fixture.archive + "/snapshot.json")
        raw_archive = self.fixture.archive + "/" + next(row["artifact"] for row in snapshot["raw_files"] if row["exists"])
        for source in (candidate_source, raw_archive, "logs/ci/preflight-fixture/old-journal.json"):
            original = self.fixture.raw(source)
            hits = []
            def edit():
                hits.append(source); (self.fixture.root / source).write_bytes(original + b" ")
            report = self.fixture.preview(before_reread=edit)
            self.assertEqual(hits, [source])
            self.assert_failed(report, "file_changed")
            self.assertFalse(report["conclusion_valid"])
            (self.fixture.root / source).write_bytes(original)

    def test_unknown_governance_version_and_boolean_auth_type_block(self):
        for source in preflight.GOVERNANCE:
            self.fixture.dump(source, {"schema_version": "newrouge.b-route-policy.v99"})
        report = self.fixture.preview()
        self.assert_failed(report, "unknown_schema")
        self.assertEqual(report["governance"]["state"], "unknown_or_damaged")
        for source in preflight.GOVERNANCE:
            (self.fixture.root / source).unlink()
        value = self.fixture.load(self.fixture.protection_input)
        value["authorization"]["write"] = 0
        self.fixture.dump(self.fixture.protection_input, value)
        self.fixture.rebind()
        self.assert_failed(self.fixture.preview(), "conflict")

    def test_manifest_duplicate_ids_and_missing_retirement_intent_block(self):
        source = "docs/testing/mvg/fixture.json"
        doc = self.fixture.load(source)
        doc["tests"].append(copy.deepcopy(doc["tests"][0]))
        self.fixture.set_candidate({source: encode(doc)})
        self.assert_failed(self.fixture.preview(), "conflict")

    def test_external_registered_source_root_is_not_privately_restricted(self):
        source = "planning/new-requirement.txt"
        self.fixture.set_candidate({source: b"A full explicitly supplied requirement.\n"})
        report = self.fixture.preview()
        self.assertTrue(report["ok"], report["diagnostics"])
        self.assertEqual(next(row["entity_id"] for row in report["changes"] if row["operation"] == "new"), source)

    def test_unknown_native_manifest_or_source_set_version_is_not_silently_accepted(self):
        for source in ("docs/testing/mvg/fixture.json", inventory.SOURCE_SET):
            document = self.fixture.load(source)
            document["schema_version"] = "unknown.v99"
            self.fixture.set_candidate({source: encode(document)})
            self.assert_failed(self.fixture.preview(), "unknown_schema")

    def test_current_triplet_new_required_reference_closure_is_observed(self):
        source = inventory.TRIPLET["back"]
        doc = self.fixture.load(source)
        missing = "docs/current-required-missing.md"
        doc[0]["source_refs"].append(missing)
        self.fixture.dump(source, doc)
        self.fixture.rebind()
        before = self.fixture.bytes()
        report = self.fixture.preview()
        self.assert_failed(report, "file_not_found")
        observation = next(row for row in report["observations"] if row["path"] == missing)
        self.assertFalse(observation["exists"])
        located = [row for row in report["diagnostics"] if row["resume_ref"] == source + "#/0/source_refs/1"]
        self.assertTrue(located, report["diagnostics"])
        self.assertEqual(located[0]["entity_id"], "1")
        self.assertEqual(self.fixture.bytes(), before)

    def test_current_manifest_membership_and_new_references_use_current_owner(self):
        source = "docs/testing/mvg/new-current-manifest.json"
        self.fixture.dump(source, self.fixture.load("docs/testing/mvg/fixture.json"))
        report = self.fixture.preview()
        self.assertTrue(report["ok"], report["diagnostics"])
        self.assertIn(source, report["current_inventory"]["manifest_paths"])
        manifest = self.fixture.load(source)
        missing = "registered/current-manifest-source.md"
        manifest["flows"][0]["source_paths"].append(missing)
        self.fixture.dump(source, manifest)
        report = self.fixture.preview()
        self.assert_failed(report, "file_not_found")
        self.assertIn(missing, {row["path"] for row in report["observations"]})
        self.assertTrue(any(row["resume_ref"] == source + "#/flows/0/source_paths/1" for row in report["diagnostics"]))

    def test_actual_late_current_manifest_addition_invalidates_preview(self):
        source = "docs/testing/mvg/new-current-manifest.json"
        hits = []
        def add():
            hits.append(source)
            self.fixture.dump(source, self.fixture.load("docs/testing/mvg/fixture.json"))
        report = self.fixture.preview(before_reread=add)
        self.assertEqual(hits, [source], "The actual filesystem injection must execute")
        self.assert_failed(report, "file_changed")
        self.assertFalse(report["stable"])
        self.assertFalse(report["conclusion_valid"])
        self.assertIn(source, {row["path"] for row in report["observations"]})

    def test_current_source_set_new_dependencies_and_late_pattern_membership(self):
        source = "registered/current-source.md"
        source_set = self.fixture.load(inventory.SOURCE_SET)
        source_set["active_patterns"].append("registered/*.md")
        source_set["active_sources"].append(source)
        self.fixture.dump(inventory.SOURCE_SET, source_set)
        self.fixture.rebind()
        missing = self.fixture.preview()
        self.assert_failed(missing, "file_not_found")
        self.assertIn(source, {row["path"] for row in missing["observations"]})
        self.fixture.write(source, "# A registered source outside docs\nCurrent requirement.\n")
        valid = self.fixture.preview()
        self.assertTrue(valid["ok"], valid["diagnostics"])
        self.assertIn(source, valid["current_inventory"]["active_source_paths"])
        late = "registered/late-source.md"
        hits = []
        def add():
            hits.append(late); self.fixture.write(late, "# A late registered member\n")
        changed = self.fixture.preview(before_reread=add)
        self.assertEqual(hits, [late])
        self.assert_failed(changed, "file_changed")
        self.assertFalse(changed["conclusion_valid"])
        self.assertIn(late, {row["path"] for row in changed["observations"]})

    def test_current_epics_new_canonical_dependency_is_observed_and_reread(self):
        source = "registered/current-canonical.md"
        original = self.fixture.raw(self.fixture.epics).decode("utf-8")
        self.fixture.write(self.fixture.epics, original.replace(self.fixture.base.sources[-1], source))
        self.fixture.rebind()
        missing = self.fixture.preview()
        self.assert_failed(missing, "file_not_found")
        self.assertIn(source, {row["path"] for row in missing["observations"]})
        self.assertTrue(any(row["resume_ref"] == self.fixture.epics + "#/frontmatter/inputDocuments/9"
                            for row in missing["diagnostics"]))
        self.fixture.write(source, "# New canonical dependency\nFull original text.\n")
        valid = self.fixture.preview()
        self.assertTrue(valid["ok"], valid["diagnostics"])
        hits = []
        def edit():
            hits.append(source); self.fixture.write(source, "# Edited canonical dependency\n")
        changed = self.fixture.preview(before_reread=edit)
        self.assertEqual(hits, [source])
        self.assert_failed(changed, "file_changed")
        self.assertFalse(changed["conclusion_valid"])

    def test_json_history_and_subtask_identity_cannot_coerce_int_to_bool(self):
        source = inventory.TRIPLET["master"]
        current = self.fixture.load(source)
        current["master"]["tasks"][0]["history"] = [{"event": 1}]
        current["master"]["tasks"][0]["subtasks"] = [{"id": 1, "status": "pending"}]
        self.fixture.dump(source, current)
        for field in ("history", "subtasks"):
            documents = {target: self.fixture.load(target) for target in inventory.TRIPLET.values()}
            task = documents[source]["master"]["tasks"][0]
            task[field][0]["event" if field == "history" else "id"] = True
            self.fixture.set_candidate({target: encode(doc) for target, doc in documents.items()})
            report = self.fixture.preview()
            self.assert_failed(report, "conflict")
            self.assertIn("1", {row["entity_id"] for row in report["diagnostics"]})
        documents = {target: self.fixture.load(target) for target in inventory.TRIPLET.values()}
        documents[source]["master"]["tasks"][0]["history"].append({"event": True})
        documents[source]["master"]["tasks"][0]["subtasks"].append({"id": 2, "status": "pending"})
        self.fixture.set_candidate({target: encode(doc) for target, doc in documents.items()})
        valid = self.fixture.preview()
        self.assertTrue(valid["ok"], valid["diagnostics"])
        self.assertEqual(self.fixture.load(source), current)

    def task_candidate(self):
        return {source: self.fixture.load(source) for source in inventory.TRIPLET.values()}

    def test_candidate_task_required_reference_closure_and_locator_use_native_owner(self):
        for field, missing in (("source_refs", "registered/candidate-missing.md"),
                               ("test_refs", "Game.Core.Tests/CandidateMissing.cs"),
                               ("evidence_refs", "logs/ci/candidate-missing.json")):
            documents = self.task_candidate()
            documents[inventory.TRIPLET["back"]][0].setdefault(field, []).append(missing)
            self.fixture.set_candidate({source: encode(doc) for source, doc in documents.items()})
            before = self.fixture.bytes()
            report = self.fixture.preview()
            self.assert_failed(report, "file_not_found")
            self.assertTrue(any(row["path"] == missing and not row["exists"] for row in report["observations"]))
            located = [row for row in report["diagnostics"]
                       if row["reason_code"] == "file_not_found" and row["entity_id"] == "1"
                       and row["resume_ref"].startswith(inventory.TRIPLET["back"] + "#/0/" + field)]
            self.assertTrue(located, report["diagnostics"])
            self.assertEqual(before, self.fixture.bytes())
        documents = self.task_candidate()
        documents[inventory.TRIPLET["back"]][0]["source_refs"].append("docs/source.md:999")
        self.fixture.set_candidate({source: encode(doc) for source, doc in documents.items()})
        self.assert_failed(self.fixture.preview(), "unresolved_reference")

    def test_candidate_manifest_missing_dependencies_and_unknown_tests_use_native_rules(self):
        source = "docs/testing/mvg/fixture.json"
        for label, missing, mutate in (
            ("source", "registered/candidate-manifest.md", lambda doc, value: doc["flows"][0]["source_paths"].append(value)),
            ("contract", "Game.Core/Contracts/CandidateMissing.cs", lambda doc, value: doc["flows"][0]["handoffs"][0].update(contract_ref=value)),
            ("test", "Game.Core.Tests/CandidateMissing.cs", lambda doc, value: doc["tests"][0].update(path=value)),
        ):
            document = self.fixture.load(source)
            mutate(document, missing)
            self.fixture.set_candidate({source: encode(document)})
            before = self.fixture.bytes()
            report = self.fixture.preview()
            self.assert_failed(report, "file_not_found")
            self.assertTrue(any(row["path"] == missing and not row["exists"] for row in report["observations"]), label)
            self.assertTrue(any(row["resume_ref"].startswith(source + "#/")
                                and row["reason_code"] == "file_not_found" for row in report["diagnostics"]))
            self.assertEqual(before, self.fixture.bytes())
        document = self.fixture.load(source)
        document["flows"][0]["test_ids"].append("unknown-test")
        self.fixture.set_candidate({source: encode(document)})
        report = self.fixture.preview()
        self.assert_failed(report, "schema_validation_failed")
        self.assertTrue(any(issue["message"] == "flow: unknown or empty test coverage"
                            for issue in report["candidate_inventory"]["owning_diagnostics"]))
        self.assertFalse(any(row["reason_code"] == "file_not_found" for row in report["diagnostics"]))

    def test_candidate_source_set_missing_member_escape_and_membership_mismatch(self):
        source = inventory.SOURCE_SET
        document = self.fixture.load(source)
        missing = "registered/candidate-required.md"
        document["active_patterns"].append(missing)
        document["active_sources"].append(missing)
        self.fixture.set_candidate({source: encode(document)})
        report = self.fixture.preview()
        self.assert_failed(report, "file_not_found")
        self.assertTrue(any(row["resume_ref"] == source + "#/active_sources/1" for row in report["diagnostics"]))
        for pattern in ("../outside/*.md", "registered/**bad/*.md"):
            document = self.fixture.load(source)
            document["active_patterns"].append(pattern)
            self.fixture.set_candidate({source: encode(document)})
            report = self.fixture.preview()
            self.assert_failed(report)
            self.assertTrue(any(issue["code"] == "invalid-source-set"
                                for issue in report["candidate_inventory"]["owning_diagnostics"]))
        document = self.fixture.load(source)
        document["active_patterns"].append("registered/*.md")
        self.fixture.set_candidate({source: encode(document), "registered/extra.md": b"# Candidate-only source\n"})
        report = self.fixture.preview()
        self.assert_failed(report, "schema_validation_failed")
        self.assertTrue(any(issue["code"] == "source-set-mismatch"
                            for issue in report["candidate_inventory"]["owning_diagnostics"]))

    def test_candidate_source_pattern_safety_precedes_resolver_enumeration(self):
        document = self.fixture.load(inventory.SOURCE_SET)
        document["active_patterns"] = ["../outside/*.md"]
        self.fixture.set_candidate({inventory.SOURCE_SET: encode(document)})
        original = inventory.resolve_sources
        calls = []
        def resolver(*args, **kwargs):
            calls.append(list(args[1]))
            self.assertNotIn("../outside/*.md", args[1], "Unsafe candidate must never reach enumeration")
            return original(*args, **kwargs)
        with patch.object(inventory, "resolve_sources", side_effect=resolver) as checked:
            report = self.fixture.preview()
        self.assertTrue(checked.called)
        self.assertEqual(calls, [["docs/source.md"], ["docs/source.md"]])
        self.assert_failed(report, "schema_validation_failed")

    def test_candidate_only_dependencies_tasks_manifest_and_planned_missing_are_valid(self):
        documents = self.task_candidate()
        documents[inventory.TRIPLET["master"]]["master"]["tasks"].append(
            {"id": 30, "status": "pending", "title": "Candidate-only task"})
        documents[inventory.TRIPLET["back"]].append({"id": "BACK-30", "taskmaster_id": 30,
            "status": "pending", "source_refs": ["registered/new.md:2"],
            "test_refs": ["Game.Core.Tests/Candidate.cs"], "evidence_refs": ["logs/ci/new-proof.json"]})
        manifest_path = "docs/testing/mvg/candidate-only.json"
        manifest = self.fixture.load("docs/testing/mvg/fixture.json")
        manifest["mvg_id"] = "candidate-only"
        manifest["coverage"]["blocking_task_ids"] = [30]
        manifest["flows"][0].update(task_ids=[30], source_paths=["registered/new.md"])
        manifest["flows"][0]["handoffs"][0].update(producer_task=30, consumer_task=30, owner_task=30,
            contract_ref="Game.Core/Contracts/Candidate.cs")
        manifest["tests"][0].update(path="Game.Core.Tests/Candidate.cs", selector="Candidate")
        planned = copy.deepcopy(manifest["tests"][0])
        planned.update(id="future-test", state="planned", path="Game.Core.Tests/FutureCandidate.cs")
        manifest["tests"].append(planned)
        manifest["flows"][0]["test_ids"].append("future-test")
        source_set = self.fixture.load(inventory.SOURCE_SET)
        source_set["active_patterns"].append("registered/**/*.md")
        source_set["active_sources"].append("registered/new.md")
        candidates = {source: encode(doc) for source, doc in documents.items()}
        candidates.update({manifest_path: encode(manifest), inventory.SOURCE_SET: encode(source_set),
            "registered/new.md": b"# Candidate-only source\nFull requirement.\n",
            "Game.Core/Contracts/Candidate.cs": b"public interface Candidate {}\n",
            "Game.Core.Tests/Candidate.cs": b"public class Candidate {}\n",
            "logs/ci/new-proof.json": b'{"synthetic":true}\n'})
        self.fixture.set_candidate(candidates)
        before = self.fixture.bytes()
        report = self.fixture.preview()
        self.assertTrue(report["ok"], report["diagnostics"])
        self.assertEqual(report["candidate_inventory"]["source_set"]["resolved_active_sources"],
                         ["docs/source.md", "registered/new.md"])
        self.assertIn(manifest_path, report["candidate_inventory"]["manifest_paths"])
        self.assertEqual(report["cumulative_changes"][0]["before_digest"], None)
        self.assertFalse(report["cumulative_changes"][0]["weakening_detected"])
        references = report["candidate_inventory"]["references"]
        self.assertTrue(any(row.get("master_id") == 30 and row["path"] == "registered/new.md"
                            and row["state"] == "present" for row in references))
        self.assertTrue(any(row["path"] == planned["path"] and row["state"] == "missing" for row in references))
        self.assertEqual(before, self.fixture.bytes())
        self.assertTrue(all(not (self.fixture.root / source).exists() for source in candidates
                            if source not in inventory.TRIPLET.values() and source != inventory.SOURCE_SET))
        self.assertFalse(report["candidate_inventory"]["runtime_verified"])

    def test_candidate_dependency_actual_post_edit_invalidates_preview(self):
        source = "registered/candidate-dependency.md"
        self.fixture.write(source, "# Candidate dependency\nOriginal requirement.\n")
        documents = self.task_candidate()
        documents[inventory.TRIPLET["back"]][0]["source_refs"].append(source + ":2")
        self.fixture.set_candidate({target: encode(doc) for target, doc in documents.items()})
        valid = self.fixture.preview()
        self.assertTrue(valid["ok"], valid["diagnostics"])
        hits = []
        def edit():
            hits.append(source)
            self.fixture.write(source, "# Changed candidate dependency\nEdited requirement.\n")
        changed = self.fixture.preview(before_reread=edit)
        self.assertEqual(hits, [source], "The actual candidate dependency edit must execute")
        self.assert_failed(changed, "file_changed")
        self.assertFalse(changed["stable"])
        self.assertFalse(changed["conclusion_valid"])
        self.assertIn(source, {row["path"] for row in changed["observations"]})

    def test_candidate_source_pattern_late_member_invalidates_preview(self):
        document = self.fixture.load(inventory.SOURCE_SET)
        document["active_patterns"].append("registered/**/*.md")
        document["active_sources"].append("registered/candidate.md")
        self.fixture.set_candidate({inventory.SOURCE_SET: encode(document),
                                    "registered/candidate.md": b"# Candidate requirement\n"})
        valid = self.fixture.preview()
        self.assertTrue(valid["ok"], valid["diagnostics"])
        late = "registered/deep/late.md"
        hits = []
        def add():
            hits.append(late)
            self.fixture.write(late, "# Late candidate pattern member\n")
        changed = self.fixture.preview(before_reread=add)
        self.assertEqual(hits, [late], "The actual late pattern member must be created")
        self.assert_failed(changed, "file_changed")
        self.assertFalse(changed["stable"])
        self.assertFalse(changed["conclusion_valid"])
        self.assertIn(late, {row["path"] for row in changed["observations"]})

    def test_virtual_source_resolver_preserves_native_glob_semantics(self):
        from build_source_ledger import resolve_sources
        members = ["registered/a.md", "registered/a.txt", "registered/deep/b.md",
                   "registered/deep/nested/c.md", "registered/Upper.MD"]
        for source in members:
            self.fixture.write(source, "# Synthetic resolver member\n")
        patterns = ["registered/a.md", "registered/*.md", "registered/**/*.md", "registered/**/**/*.md",
                    "registered/*/*.md", "registered/[ab].md", "registered/**", "registered/deep"]
        expected = {pattern: ([path.relative_to(self.fixture.root).as_posix() for path in
                              resolve_sources(self.fixture.root, [pattern], True)[0]],
                              resolve_sources(self.fixture.root, [pattern], True)[1]) for pattern in patterns}
        for source in members:
            (self.fixture.root / source).unlink()
        for pattern in patterns:
            paths, missing = resolve_sources(self.fixture.root, [pattern], True, virtual_files=members)
            self.assertEqual(([path.relative_to(self.fixture.root).as_posix() for path in paths], missing),
                             expected[pattern], pattern)

    def test_public_cli_nonempty_top_level_and_item_unresolved_are_independent_blockers(self):
        original = self.fixture.load(self.fixture.intents_path)
        self.assertTrue(self.fixture.preview()["ok"])
        for label in ("top", "item"):
            value = copy.deepcopy(original)
            target = value if label == "top" else value["changes"][0]
            target["unresolved"] = ["Independent unresolved semantic question"]
            self.fixture.dump(self.fixture.intents_path, value)
            before = self.fixture.bytes()
            completed = self.fixture.cli("unresolved-" + label)
            self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
            self.assertEqual(completed.stderr, "")
            report = json.loads(completed.stdout)
            self.assert_failed(report, "semantic_error")
            self.assertEqual({row["reason_code"] for row in report["diagnostics"]}, {"semantic_error"})
            self.assertTrue(report["stable"])
            self.assertEqual(json.loads(self.fixture.raw(report["report_path"])), report)
            self.assertTrue(all(self.fixture.bytes().get(source) == raw for source, raw in before.items()))

    def test_public_cli_same_revision_plan_body_conflicts_without_candidate_catalog(self):
        module = importlib.import_module("test_b_route_records")
        matrix = module.MatrixFixture()
        artifacts = matrix.render()
        for source, raw in artifacts.items():
            target = self.fixture.root / source
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        self.fixture.set_candidate({"docs/new-source.md": b"# Synthetic new source\n"})
        baseline = self.fixture.preview()
        self.assertTrue(baseline["ok"], baseline["diagnostics"])
        self.assertEqual(baseline["governance"]["state"], "structure_valid_publication_unverified")
        source = module.plan_path()
        changed = json.loads(artifacts[source])
        changed["requirements"][0]["acceptance_intent"] = "Changed content with the same immutable identity"
        self.fixture.set_candidate({source: encode(changed)})
        self.assertNotIn(preflight.records.CATALOG_PATH, self.fixture.candidate)
        before = self.fixture.bytes()
        completed = self.fixture.cli("same-plan-revision")
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertEqual(completed.stderr, "")
        report = json.loads(completed.stdout)
        self.assert_failed(report, "conflict")
        self.assertEqual({row["reason_code"] for row in report["diagnostics"]}, {"conflict"})
        self.assertEqual(report["diagnostics"][0]["entity_id"], "p")
        self.assertEqual(report["diagnostics"][0]["resume_ref"], source)
        self.assertEqual(report["candidate_validation"]["mode"], "single_records_only")
        self.assertTrue(report["stable"])
        self.assertEqual(json.loads(self.fixture.raw(report["report_path"])), report)
        self.assertTrue(all(self.fixture.bytes().get(target) == raw for target, raw in before.items()))

    def existing_root_alias(self):
        if os.name == "nt":
            import ctypes
            short_path = ctypes.WinDLL("kernel32", use_last_error=True).GetShortPathNameW
            short_path.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
            short_path.restype = ctypes.c_uint
            physical = self.fixture.root.resolve(strict=True)
            size = short_path(str(physical), None, 0)
            self.assertGreater(size, 0, "A real Windows short-path lookup is required")
            buffer = ctypes.create_unicode_buffer(size)
            written = short_path(str(physical), buffer, size)
            self.assertTrue(0 < written < size, "A real Windows short-path lookup is required")
            alias = Path(buffer.value)
            self.assertNotEqual(str(alias), str(physical), "Exercise the native 8.3 root alias")
        else:
            (self.fixture.root / "root-spelling").mkdir()
            alias = self.fixture.root / "root-spelling" / ".."
        self.assertTrue(alias.samefile(self.fixture.root))
        return alias

    def test_root_alias_keeps_nonempty_governance_scan_and_original_diagnostics(self):
        alias = self.existing_root_alias()
        source = "docs/planning/b-route/plans/p/1.json"
        self.fixture.dump(source, {"schema_version": "newrouge.b-route-plan.v1"})
        before = self.fixture.bytes()
        observed = preflight.Observations(alias)
        self.assertEqual(str(observed.root), str(alias.absolute()), "Keep the caller's original root spelling")
        self.assertEqual(observed.scan("docs/planning/b-route"), [source])
        report = preflight.preflight(alias, self.fixture.epics, self.fixture.protection_input,
                                     self.fixture.candidate_path, self.fixture.intents_path)
        self.assert_failed(report, "required_governance_missing")
        self.assertNotIn("identity_unprovable", {row["reason_code"] for row in report["diagnostics"]})
        self.assertEqual(self.fixture.bytes(), before)

    def test_root_alias_direct_and_public_cli_keep_single_json_and_physical_report_identity(self):
        alias = self.existing_root_alias()
        before = self.fixture.bytes()
        for direct, run_id in ((True, "alias-direct"), (False, "alias-public")):
            arguments = self.fixture.arguments(run_id)
            arguments[arguments.index("--root") + 1] = str(alias)
            entry = "preflight_b_route_migration.py" if direct else "dev_cli.py"
            command = [sys.executable, "-B", str(REPOSITORY / "scripts/python" / entry)]
            if not direct:
                command.append("b-route-preflight")
            completed = subprocess.run(command + arguments, capture_output=True, text=True,
                                       encoding="utf-8", timeout=30)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertEqual(completed.stderr, "")
            report = json.loads(completed.stdout)
            target = self.fixture.root / report["report_path"]
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), report)
            self.assertEqual(report["report_path"], target.resolve().relative_to(self.fixture.root.resolve()).as_posix())
        current = self.fixture.bytes()
        self.assertTrue(all(current.get(source) == digest for source, digest in before.items()))
        self.assertTrue(all("/b-route-preflight/" in source and source.endswith("/report.json")
                            for source in set(current) - set(before)))

    def test_report_path_admission_failure_is_a_public_json_diagnostic(self):
        import preflight_b_route_migration as command
        output = io.StringIO()
        error = codec.CodecError(codec.Diagnostic(codec.ReasonCode.UNSAFE_PATH, codec.Stage.PATH,
            expected="contained output with no linked ancestors", actual="unsafe output identity"))
        with patch.object(protection, "_output_relative_path", side_effect=error) as guard:
            with contextlib.redirect_stdout(output):
                code = command.main(self.fixture.arguments("path-guard-failure"))
        self.assertTrue(guard.called, "The output identity fault must hit the real CLI boundary")
        self.assertEqual(code, 2)
        report = json.loads(output.getvalue())
        self.assertFalse(report["ok"])
        self.assertIsNone(report["report_path"])
        self.assertEqual(report["diagnostics"][-1]["reason_code"], "unsafe_path")
        self.assertEqual(set(report["diagnostics"][-1]), FIELDS)

    def test_real_directory_links_still_block_governance_scan_and_report_output(self):
        def link(alias, target):
            if os.name == "nt":
                completed = subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(alias), str(target)],
                                           capture_output=True, text=True)
                self.assertEqual(completed.returncode, 0, "Real Windows junction creation failed: " + completed.stderr)
            else:
                alias.symlink_to(target, target_is_directory=True)
        def unlink(alias):
            alias.rmdir() if os.name == "nt" else alias.unlink()
        with tempfile.TemporaryDirectory() as external:
            target = Path(external)
            (target / "sentinel.json").write_bytes(b"{}")
            governance = self.fixture.root / "docs/planning/b-route"
            governance.parent.mkdir(parents=True, exist_ok=True)
            link(governance, target)
            try:
                report = self.fixture.preview()
                self.assert_failed(report, "unsafe_path")
                self.assertEqual((target / "sentinel.json").read_bytes(), b"{}")
            finally:
                unlink(governance)
            original = self.fixture.root / "logs/ci"
            saved = self.fixture.root / "logs/original-ci"
            original.rename(saved)
            link(original, target)
            try:
                completed = self.fixture.cli("junction-output")
                self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
                self.assertEqual(completed.stderr, "")
                report = json.loads(completed.stdout)
                self.assertEqual(report["diagnostics"][0]["reason_code"], "unsafe_path")
                self.assertEqual(set(report["diagnostics"][0]), FIELDS)
                self.assertEqual([item.name for item in target.iterdir()], ["sentinel.json"])
            finally:
                unlink(original)
                saved.rename(original)

    def test_eight_independent_cli_scenarios(self):
        with tempfile.TemporaryDirectory() as temporary:
            rows = run_cli_matrix(Path(temporary) / "synthetic")
        self.assertEqual([row["case"] for row in rows], list(CASES))
        self.assertTrue(all(row["original_bytes_unchanged"] and row["only_fresh_log_report_added"] for row in rows))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--cli-matrix":
        run_cli_matrix(sys.argv[2])
    else:
        unittest.main()
