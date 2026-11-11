"""Story 1.1 behavioral fixtures; no engine, planner or production writes."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _b_route_inventory as inventory
from inventory_b_route_baseline import main


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.epics = "planning/epics.md"
        self.write(".gitignore", "logs/\n__pycache__/\n*.pyc\n")
        for category, responsibility, difference, epic, entries in inventory.GROUPS:
            by_path = {}
            for path, symbol in entries:
                by_path.setdefault(path, set())
                if symbol:
                    by_path[path].add(symbol)
            for path, symbols in by_path.items():
                self.write(path, "\n".join(f"def {name}():\n    pass\n" for name in sorted(symbols))
                           if symbols else "Document fixture\n")
        self.write(".agents/skills/plan-capabilities/SKILL.md", "# Capability planning\n")
        self.write(".agents/skills/plan-mvg/SKILL.md", "# MVG planning\n")
        # These inputs are intentionally independent of production discovery lists.
        for path in (
            ".agents/skills/workflow-chapter3-task-triplet-baseline/SKILL.md",
            ".agents/skills/workflow-chapter4-overlays-contracts-baseline/SKILL.md",
            ".agents/skills/workflow-chapter5-semantics-stabilization/SKILL.md",
            ".agents/skills/workflow-chapter6-single-task-daily-loop/SKILL.md",
            ".agents/skills/workflow-chapter7-ui-wiring-closure/SKILL.md",
        ):
            self.write(path, "# Chapter skill fixture\n")
        self.write("scripts/python/_mvg_capability_worker.py", "def run_candidate():\n    pass\n")
        self.write("scripts/python/_mvg_capability_checkpoint.py", "def commit_checkpoint():\n    pass\n")
        self.write("scripts/python/_mvg_capability_recovery.py", "def try_adopt():\n    pass\n")
        for path in ("docs/architecture/ADR_INDEX_GODOT.md", "DELIVERY_PROFILE.md", "docs/workflows/run-protocol.md",
                     "docs/workflows/local-hard-checks.md", "docs/architecture/base/07-build.md",
                     "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/contract.md"):
            self.write(path, "# Authority fixture\n")
        self.write("docs/adr/ADR-0038-first.md", "# ADR\n\n- Status: Accepted\n")
        self.write("docs/adr/ADR-0038-second.md", "---\nstatus: Proposed\n---\n# ADR\n")
        self.write("Game.Core/Contracts/Test.cs", "public interface Test {}\n")
        self.write("Game.Core.Tests/Test.cs", "public class Test {}\n")
        self.write("Game.Core.Tests/Unmanifested.cs", "public class Unmanifested {}\n")
        self.write("Game.Core.Tests/ManifestOnly.cs", "public class ManifestOnly {}\n")
        self.write("manifest-only/source.txt", "Manifest source\n")
        self.write("manifest-only/Contract.cs", "public interface ManifestContract {}\n")
        self.write("docs/source.md", "# Source\nA\nB\n")
        self.write("evidence/existing.json", '{"pass": true}\n')
        self.write("logs/ci/historical/explicit.json", '{"historical": true}\n')
        self.write("examples/helper.py", '"""A legal Python documentation example."""\n')
        self.write("docs/workflows/examples/README.md", "# Workflow examples\n")
        self.write("docs/workflows/examples/nested/approval.example.json", '{"decision": "approve"}\n')
        self.write("docs/planning/knowledge/current.json", '{"generation": "unchanged"}\n')
        self.dump(inventory.SOURCE_SET, {"schema_version": "chapter3.source-set.v1",
                                       "active_patterns": ["docs/source.md"], "active_sources": ["docs/source.md"], "retirements": []})
        master = {"master": {"tasks": [{"id": 1, "status": "done", "history": [{"event": "completed"}]},
                                        {"id": 2, "status": "done", "history": []}]}}
        back = [{"id": "BACK-9", "taskmaster_id": 1, "status": "pending", "test_refs": ["Game.Core.Tests/Test.cs"],
                 "source_refs": ["docs/source.md:2"], "evidence_refs": ["evidence/existing.json", "logs/ci/historical/explicit.json"]},
                {"id": "BACK-10", "taskmaster_id": 2, "status": "done", "test_refs": ["Game.Core.Tests/Unmanifested.cs"]}]
        gameplay = [{"id": "GAME-1", "taskmaster_id": 1, "status": "review"}, {"id": "GAME-2", "taskmaster_id": 2, "status": "done"}]
        for name, doc in (("master", master), ("back", back), ("gameplay", gameplay)):
            self.dump(inventory.TRIPLET[name], doc)
        self.manifest = {"schema_version": "newrouge.mvg-integration.v1", "mvg_id": "fixture",
                         "coverage": {"mode": "pilot", "scope_id": "fixture", "required_flow_ids": ["flow"],
                                      "excluded_claims": ["Not a product-wide run"], "blocking_task_ids": []},
                         "tests": [{"id": "test", "state": "implemented", "kind": "dotnet", "evidence_level": "domain-integration",
                                    "path": "Game.Core.Tests/ManifestOnly.cs", "min_tests": 1, "selector": "ManifestOnly"}],
                         "flows": [{"id": "flow", "outcome": "Observe fixture", "task_ids": [1], "test_ids": ["test"],
                                    "source_paths": ["manifest-only/source.txt"], "handoffs": [{"producer_task": 1, "consumer_task": 1,
                                     "owner_task": 1, "contract_ref": "manifest-only/Contract.cs", "behavior": "Transfer", "test_ids": ["test"]}]}]}
        self.dump("docs/testing/mvg/fixture.json", self.manifest)
        self.sources = [f"planning/source-{index}.md" for index in range(10)]
        for path in self.sources:
            self.write(path, "# Canonical source\nOriginal content\n")
        self.run_git("init", "-q")
        self.run_git("config", "user.email", "fixture@example.invalid")
        self.run_git("config", "user.name", "Fixture")
        self.run_git("config", "core.autocrlf", "false")
        self.run_git("add", ".")
        self.run_git("commit", "-qm", "Fixture baseline")
        self.head = self.run_git("rev-parse", "HEAD").strip()
        self.write_epics()
        self.run_git("add", ".")
        self.run_git("commit", "-qm", "Epic inputs")

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")

    def dump(self, path, data):
        self.write(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    def load(self, path):
        return json.loads((self.root / path).read_text(encoding="utf-8"))

    def edit_task(self, name, callback):
        path = inventory.TRIPLET[name]
        doc = self.load(path)
        callback(doc["master"]["tasks"] if name == "master" else doc)
        self.dump(path, doc)

    def run_git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True).stdout.decode("utf-8")

    def write_epics(self):
        self.write(self.epics, "---\nstatus: final\ncodeBaselineCommit: " + self.head + "\ninputSnapshotCommit: " + self.head
                   + "\ninputDocuments:\n" + "".join("  - " + json.dumps(x) + "\n" for x in self.sources) + "---\n# Epics\n")

    def collect(self, **kwargs):
        return inventory.collect_inventory(self.root, self.epics, **kwargs)

    def assert_invalid(self, report, code):
        self.assertFalse(report["adoptable"])
        self.assertIn(code, {d["code"] for d in report["diagnostics"]})

    def bytes_before(self):
        return {p.relative_to(self.root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.root.rglob("*") if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts}

    def cli(self, run_id="fixture-run", epics=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return main(["--root", str(self.root), "--epics", epics or self.epics, "--run-id", run_id])

    def output(self, run_id="fixture-run"):
        return next((self.root / "logs/ci").glob("*/b-route-baseline-inventory/" + run_id))

    def test_valid_baseline_preserves_original_inventory_and_distinguishes_git_history(self):
        before = self.bytes_before()
        report = self.collect()
        self.assertTrue(report["adoptable"], report["diagnostics"])
        self.assertEqual(report["rules"], inventory.rule_identity())
        self.assertEqual(report["git"]["head"], self.run_git("rev-parse", "HEAD").strip())
        self.assertEqual(report["declared_code_baseline"], self.head)
        self.assertNotEqual(report["git"]["head"], report["declared_code_baseline"])
        self.assertEqual(report["tasks"]["documents"]["master"], self.load(inventory.TRIPLET["master"]))
        self.assertEqual(report["manifests"][0]["document"], self.manifest)
        self.assertEqual({row["status"] for row in report["adrs"]}, {"accepted", "proposed"})
        self.assertEqual(before, self.bytes_before())

    def test_exact_status_differences_and_equal_states_excluded(self):
        expected = [{"master_id": 1, "view": "back", "view_id": "BACK-9", "master_status": "done", "view_status": "pending",
                     "master_pointer": "/master/tasks/0/status", "view_pointer": "/0/status", "authority": inventory.TRIPLET["master"], "action": "report-only"},
                    {"master_id": 1, "view": "gameplay", "view_id": "GAME-1", "master_status": "done", "view_status": "review",
                     "master_pointer": "/master/tasks/0/status", "view_pointer": "/0/status", "authority": inventory.TRIPLET["master"], "action": "report-only"}]
        self.assertEqual(self.collect()["tasks"]["status_differences"], expected)

    def test_matrix_covers_real_paths_symbols_skills_and_python_document_examples(self):
        report = self.collect()
        self.assertTrue(report["adoptable"], report["diagnostics"])
        self.assertEqual({r["category"] for r in report["consumers"]}, {g[0] for g in inventory.GROUPS})
        by_path = {r["path"]: r for r in report["consumers"]}
        for path in (".agents/skills/plan-capabilities/SKILL.md", ".agents/skills/plan-mvg/SKILL.md", "scripts/sc/llm_generate_overlays_batch.py"):
            self.assertIn(path, by_path)
        self.assertEqual(by_path["examples/helper.py"]["locator_kind"], "document")
        for row in report["consumers"]:
            self.assertTrue(row["line"])
            self.assertTrue(row["responsibility"])
            self.assertTrue(row["current_a_to_target_b"])
            self.assertTrue(row["followup_epic"])
            self.assertFalse(row["invoked"])

    def test_research_worker_checkpoint_and_completed_recovery_rows_are_required(self):
        report = self.collect()
        expected = {
            ("scripts/python/_mvg_capability_worker.py", "run_candidate"),
            ("scripts/python/_mvg_capability_checkpoint.py", "commit_checkpoint"),
            ("scripts/python/_mvg_capability_recovery.py", "try_adopt"),
        }
        rows = [row for row in report["consumers"] if row["category"] == "worker-checkpoint-recovery"]
        self.assertEqual({(row["path"], row["symbol"]) for row in rows}, expected)
        for row in rows:
            self.assertEqual(row["locator"], row["path"] + ":1")

    def test_each_versioned_chapter_skill_is_mandatory_even_when_discovery_is_empty(self):
        paths = (
            ".agents/skills/workflow-chapter3-task-triplet-baseline/SKILL.md",
            ".agents/skills/workflow-chapter4-overlays-contracts-baseline/SKILL.md",
            ".agents/skills/workflow-chapter5-semantics-stabilization/SKILL.md",
            ".agents/skills/workflow-chapter6-single-task-daily-loop/SKILL.md",
            ".agents/skills/workflow-chapter7-ui-wiring-closure/SKILL.md",
        )
        for path in paths:
            with self.subTest(path=path):
                raw = (self.root / path).read_bytes()
                (self.root / path).unlink()
                report = self.collect()
                self.assert_invalid(report, "missing-input")
                self.assertTrue(any(d["code"] == "missing-input" and d["location"] == path for d in report["diagnostics"]))
                (self.root / path).write_bytes(raw)
        for path in paths:
            (self.root / path).unlink()
        report = self.collect()
        self.assert_invalid(report, "missing-input")
        self.assertEqual({d["location"] for d in report["diagnostics"] if d["code"] == "missing-input"}, set(paths))

    def test_same_bytes_stable_identity_different_event_and_absolute_root_excluded(self):
        first, second = self.collect(), self.collect()
        self.assertEqual(first["content_identity"], second["content_identity"])
        self.assertNotEqual(first["collection"]["event_id"], second["collection"]["event_id"])
        with tempfile.TemporaryDirectory() as other:
            copied = Path(other) / "copy"
            shutil.copytree(self.root, copied)
            self.assertEqual(first["content_identity"], inventory.collect_inventory(copied, self.epics)["content_identity"])

    def test_workflow_examples_have_exact_input_and_consumer_coverage(self):
        report = self.collect()
        expected = {"docs/workflows/examples/README.md", "docs/workflows/examples/nested/approval.example.json"}
        inputs = {r["path"]: r for r in report["inputs"] if r["path"].startswith("docs/workflows/examples/")}
        consumers = {r["path"]: r for r in report["consumers"] if r["path"].startswith("docs/workflows/examples/")}
        self.assertTrue(report["adoptable"], report["diagnostics"])
        self.assertEqual(set(inputs), expected)
        self.assertEqual(set(consumers), expected)
        for path in expected:
            self.assertEqual(inputs[path]["raw_sha256"], inventory.file_sha(self.root / path))
            self.assertIn("example", inputs[path]["roles"])
            self.assertEqual(consumers[path]["category"], "cli-skill-routing-examples")
            self.assertEqual(consumers[path]["locator"], path + ":1")
            self.assertEqual(consumers[path]["locator_kind"], "document")

    def test_workflow_example_edits_additions_and_removals_are_drift(self):
        changes = (
            ("changed_inputs", "docs/workflows/examples/README.md", lambda: self.write("docs/workflows/examples/README.md", "# Edited workflow examples\n")),
            ("added_inputs", "docs/workflows/examples/nested/new.py", lambda: self.write("docs/workflows/examples/nested/new.py", "# New documentation example\n")),
            ("removed_inputs", "docs/workflows/examples/nested/approval.example.json", lambda: (self.root / "docs/workflows/examples/nested/approval.example.json").unlink()),
        )
        for field, path, callback in changes:
            with self.subTest(field=field):
                report = self.collect(between_passes=callback)
                self.assert_invalid(report, "unstable-inputs")
                self.assertIn(path, report["drift"][field])

    def test_raw_crlf_is_distinct_from_normalized_and_head_blob(self):
        before = self.collect()
        target = self.root / self.sources[0]
        target.write_bytes(target.read_bytes().replace(b"\n", b"\r\n"))
        after = self.collect()
        a = next(row for row in before["inputs"] if row["path"] == self.sources[0])
        b = next(row for row in after["inputs"] if row["path"] == self.sources[0])
        self.assertNotEqual(a["raw_sha256"], b["raw_sha256"])
        self.assertEqual(a["normalized_sha256"], b["normalized_sha256"])
        self.assertEqual(a["head_blob"], b["head_blob"])
        self.assertNotEqual(before["content_identity"], after["content_identity"])

    def test_reference_closure_records_owner_pointer_join_original_and_raw_identity(self):
        report = self.collect()
        refs = report["task_and_manifest_references"]
        row = next(r for r in refs if r["raw_reference"] == "Game.Core.Tests/Unmanifested.cs")
        self.assertEqual((row["owner_file"], row["json_pointer"], row["task_id"], row["master_id"], row["state"]),
                         (inventory.TRIPLET["back"], "/1/test_refs/0", "BACK-10", 2, "present"))
        self.assertEqual(row["raw_sha256"], inventory.file_sha(self.root / row["path"]))
        self.assertIn(row["path"], {r["path"] for r in report["inputs"]})
        historical = next(r for r in refs if r["raw_reference"] == "logs/ci/historical/explicit.json")
        self.assertEqual(historical["state"], "present")
        self.assertEqual((historical["reference_role"], historical["required"]),
                         ("historical-debug-attachment", False))
        self.assertEqual((row["reference_role"], row["required"]), ("current-input", True))

    def test_cached_evidence_cannot_be_reused_as_forbidden_test_input(self):
        path = "logs/ci/historical/explicit.json"
        self.edit_task("back", lambda rows: rows[1]["test_refs"].append(path))
        before = self.bytes_before()
        report = self.collect()
        self.assert_invalid(report, "unsafe-or-unreadable-input")
        refs = [row for row in report["task_and_manifest_references"] if row["raw_reference"] == path]
        self.assertEqual([(r["field"], r["state"], r["raw_sha256"]) for r in refs],
                         [("evidence_refs", "present", inventory.file_sha(self.root / path)), ("test_refs", "missing", None)])
        self.assertEqual(next(r["raw_sha256"] for r in report["inputs"] if r["path"] == path), inventory.file_sha(self.root / path))
        self.assertEqual(before, self.bytes_before())

    def test_manifest_only_reference_closure_has_exact_original_locators_and_raw_identity(self):
        report = self.collect()
        owner = "docs/testing/mvg/fixture.json"
        expected = {
            ("/tests/0/path", "Game.Core.Tests/ManifestOnly.cs", "manifest-test"),
            ("/flows/0/source_paths/0", "manifest-only/source.txt", "manifest-source"),
            ("/flows/0/handoffs/0/contract_ref", "manifest-only/Contract.cs", "manifest-contract"),
        }
        refs = [r for r in report["task_and_manifest_references"] if r["owner_file"] == owner]
        self.assertEqual({(r["json_pointer"], r["raw_reference"], r["field"], r["raw_sha256"], r["state"]) for r in refs},
                         {(pointer, path, field, inventory.file_sha(self.root / path), "present") for pointer, path, field in expected})
        inputs = {r["path"]: r for r in report["inputs"]}
        for _pointer, path, field in expected:
            self.assertEqual(inputs[path]["roles"], ["task-reference:" + field])

    def test_untracked_manifest_only_source_bytes_trigger_drift_without_git_change(self):
        path = "manifest-only/untracked.txt"
        self.write(path, "Before\n")
        self.manifest["flows"][0]["source_paths"] = [path]
        self.dump("docs/testing/mvg/fixture.json", self.manifest)
        report = self.collect(between_passes=lambda: self.write(path, "After\n"))
        self.assert_invalid(report, "unstable-inputs")
        self.assertEqual(report["drift"]["changed_inputs"], [path])
        self.assertFalse(report["drift"]["git_changed"])
        self.assertIsNone(next(r["head_blob"] for r in report["inputs"] if r["path"] == path))

    def test_unmanifested_mature_test_change_is_identity_change_and_drift(self):
        first = self.collect()
        self.write("Game.Core.Tests/Unmanifested.cs", "public class Changed {}\n")
        self.assertNotEqual(first["content_identity"], self.collect()["content_identity"])
        report = self.collect(between_passes=lambda: self.write("Game.Core.Tests/Unmanifested.cs", "Changed again\n"))
        self.assert_invalid(report, "unstable-inputs")

    def test_evidence_bytes_are_part_of_double_read_closure(self):
        report = self.collect(between_passes=lambda: self.write("logs/ci/historical/explicit.json", '{"historical": false}\n'))
        self.assert_invalid(report, "unstable-inputs")

    def test_historical_templates_unknown_and_event_ids_are_not_files(self):
        self.edit_task("back", lambda rows: rows[0]["evidence_refs"].append("logs/ci/<date>/task.json"))
        self.edit_task("back", lambda rows: rows[0]["source_refs"].append("EVENT-001"))
        report = self.collect()
        self.assertTrue(report["adoptable"], report["diagnostics"])
        unknown = {r["raw_reference"] for r in report["task_and_manifest_references"] if r["state"] == "unknown"}
        self.assertEqual(unknown, {"logs/ci/<date>/task.json", "EVENT-001"})
        self.assertNotIn("EVENT-001", {row["path"] for row in report["inputs"]})

    def test_missing_current_test_and_source_are_not_adoptable(self):
        for path in ("Game.Core.Tests/Unmanifested.cs", "docs/source.md"):
            with self.subTest(path=path):
                original = (self.root / path).read_bytes()
                (self.root / path).unlink()
                self.assert_invalid(self.collect(), "missing-input")
                (self.root / path).write_bytes(original)

    def test_missing_historical_attachment_keeps_original_reference_and_warning(self):
        path = "logs/ci/historical/explicit.json"
        (self.root / path).unlink()
        before = self.bytes_before()
        report = self.collect()
        self.assertTrue(report["adoptable"], report["diagnostics"])
        self.assertEqual(report["schema_version"], "newrouge.b-route-baseline-inventory.v2")
        row = next(r for r in report["task_and_manifest_references"] if r["raw_reference"] == path)
        self.assertEqual((row["owner_file"], row["json_pointer"], row["task_id"], row["master_id"]),
                         (inventory.TRIPLET["back"], "/0/evidence_refs/1", "BACK-9", 1))
        self.assertEqual((row["reference_role"], row["required"], row["state"], row["raw_sha256"]),
                         ("historical-debug-attachment", False, "missing", None))
        self.assertIn("no runtime proof", row["reason"])
        observed = next(r for r in report["inputs"] if r["path"] == path)
        self.assertFalse(observed["exists"])
        self.assertIsNone(observed["raw_sha256"])
        self.assertTrue(any(d["location"] == path and d["code"] == "missing-input" and d["severity"] == "warning"
                            for d in report["diagnostics"]))
        self.assertEqual(before, self.bytes_before())

    def test_historical_role_cannot_make_a_shared_current_input_optional(self):
        path = "evidence/existing.json"
        (self.root / path).unlink()
        for field in ("source_refs", "test_refs"):
            for first in (True, False):
                with self.subTest(field=field, current_first=first):
                    original = self.load(inventory.TRIPLET["back"])
                    self.edit_task("back", lambda rows: rows[0 if first else 1].setdefault(field, []).append(path))
                    report = self.collect()
                    self.assert_invalid(report, "missing-input")
                    refs = [r for r in report["task_and_manifest_references"] if r["raw_reference"] == path]
                    self.assertEqual({(r["reference_role"], r["required"]) for r in refs},
                                     {("historical-debug-attachment", False), ("current-input", True)})
                    self.assertTrue(any(d["location"] == path and d["severity"] == "error" for d in report["diagnostics"]))
                    self.dump(inventory.TRIPLET["back"], original)

    def test_missing_historical_attachment_created_between_passes_is_drift(self):
        path = "logs/ci/historical/explicit.json"
        (self.root / path).unlink()
        report = self.collect(between_passes=lambda: self.write(path, '{"debug": "new"}\n'))
        self.assert_invalid(report, "unstable-inputs")
        self.assertIn(path, report["drift"]["changed_inputs"])

    def test_unsafe_historical_attachment_is_still_rejected(self):
        for path in ("../outside.json", "logs/ci/../escape.json", "LOGS/ci/alias.json", ".git/config"):
            with self.subTest(path=path):
                original = self.load(inventory.TRIPLET["back"])
                self.edit_task("back", lambda rows: rows[0]["evidence_refs"].append(path))
                self.assert_invalid(self.collect(), "unsafe-or-unreadable-input")
                self.dump(inventory.TRIPLET["back"], original)

    def test_historical_attachment_reparse_boundary_is_still_rejected(self):
        path = self.root / "logs/ci/historical/explicit.json"
        original = inventory.no_reparse
        hits = []
        def reject_attachment(candidate):
            if candidate == path:
                hits.append(candidate)
                raise ValueError("Synthetic historical attachment reparse point")
            return original(candidate)
        before = self.bytes_before()
        with patch.object(inventory, "no_reparse", reject_attachment):
            self.assert_invalid(self.collect(), "unsafe-or-unreadable-input")
        self.assertTrue(hits)
        self.assertEqual(before, self.bytes_before())

    def test_missing_canonical_input_and_unsupported_format(self):
        (self.root / self.sources[0]).unlink()
        self.assert_invalid(self.collect(), "missing-input")
        self.sources[0] = "planning/source.bin"
        self.write_epics()
        self.assert_invalid(self.collect(), "invalid-epics")

    def test_draft_epics_rejected_without_changing_canonical_or_task_inputs(self):
        epics = self.root / self.epics
        epics.write_text(epics.read_text(encoding="utf-8").replace("status: final", "status: draft", 1), encoding="utf-8")
        before = self.bytes_before()
        report = self.collect()
        self.assert_invalid(report, "invalid-epics")
        self.assertTrue(any(d["location"] == self.epics and d["message"] == "Epics frontmatter status must be final"
                            for d in report["diagnostics"]))
        self.assertEqual(before, self.bytes_before())

    def test_corrupt_json_and_containers_fail_closed(self):
        for contents in ("{broken", "[]", '{"master":{"tasks":{}}}',
                         '{"master":{"tasks":[]},"extra":NaN}',
                         '{"master":{"tasks":[]},"master":{"tasks":[]}}'):
            with self.subTest(contents=contents):
                self.write(inventory.TRIPLET["master"], contents)
                self.assertFalse(self.collect()["adoptable"])

    def test_all_master_tasks_require_at_least_one_business_mapping(self):
        self.edit_task("master", lambda rows: rows.append({"id": 3, "status": "done"}))
        self.assert_invalid(self.collect(), "missing-business-mapping")

    def test_business_id_duplicates_across_distinct_master_joins_fail(self):
        self.edit_task("back", lambda rows: rows[1].update(id="BACK-9"))
        self.assert_invalid(self.collect(), "invalid-view-id")

    def test_missing_blank_or_wrong_type_business_id_fail(self):
        for value in (None, "", " ", 3, True):
            self.edit_task("back", lambda rows: rows[0].update(id=value))
            self.assert_invalid(self.collect(), "invalid-view-id")

    def test_duplicate_master_and_duplicate_or_bad_joins_fail(self):
        for name, mutate in (("master", lambda rows: rows.append(dict(rows[0]))),
                             ("back", lambda rows: rows[1].update(taskmaster_id=1)),
                             ("gameplay", lambda rows: rows[1].update(taskmaster_id=True))):
            with self.subTest(name=name):
                original = self.load(inventory.TRIPLET[name])
                self.edit_task(name, mutate)
                self.assert_invalid(self.collect(), "invalid-master-join-id")
                self.dump(inventory.TRIPLET[name], original)

    def test_orphan_business_join_fails(self):
        self.edit_task("back", lambda rows: rows[0].update(taskmaster_id=99))
        self.assert_invalid(self.collect(), "orphan-view-join")

    def test_unmanifested_master_missing_status_and_all_invalid_status_types(self):
        for value in (None, "", 0, True, [], "UNKNOWN", " done "):
            with self.subTest(value=value):
                self.edit_task("master", lambda rows: rows[1].update(status=value))
                self.assert_invalid(self.collect(), "invalid-task-status")
        self.edit_task("master", lambda rows: rows[1].pop("status"))
        self.assert_invalid(self.collect(), "invalid-task-status")

    def test_invalid_business_status_fails_without_normalization(self):
        self.edit_task("gameplay", lambda rows: rows[1].update(status=7))
        report = self.collect()
        self.assert_invalid(report, "invalid-task-status")
        self.assertEqual(report["tasks"]["documents"]["gameplay"][1]["status"], 7)

    def test_missing_conflicting_and_unknown_adr_body_statuses_fail(self):
        for text in ("# ADR\n", "# ADR\n- Status: Accepted\n- Status: Proposed\n", "status: SomethingElse\n"):
            with self.subTest(text=text):
                self.write("docs/adr/ADR-0038-first.md", text)
                report = self.collect()
                self.assert_invalid(report, "unknown-adr-status")
                self.assertEqual(next(r["status"] for r in report["adrs"] if r["path"].endswith("first.md")), "unknown")

    def test_adr_status_with_parenthetical_explanation_retains_original(self):
        self.write("docs/adr/ADR-0038-first.md", "# ADR\n- Status: Proposed (trial stage)\n")
        report = self.collect()
        self.assertTrue(report["adoptable"], report["diagnostics"])
        row = next(r for r in report["adrs"] if r["path"].endswith("first.md"))
        self.assertEqual(row["status"], "proposed")
        self.assertEqual(row["body_declarations"][0]["raw_status"], "Proposed (trial stage)")

    def test_adr_example_code_and_comments_cannot_supply_status(self):
        examples = (
            "```yaml\nstatus: Accepted\n```\n",
            "~~~~markdown\n- Status: Accepted\n~~~~\n",
            "    - Status: Accepted\n",
            "\tstatus: Accepted\n",
            "<!--\n- Status: Accepted\n-->\n",
            "<!-- status: Accepted -->\n",
        )
        for example in examples:
            with self.subTest(example=example):
                self.write("docs/adr/ADR-0038-first.md", "# ADR\n" + example)
                report = self.collect()
                self.assert_invalid(report, "unknown-adr-status")
                row = next(r for r in report["adrs"] if r["path"].endswith("first.md"))
                self.assertEqual(row["body_declarations"], [])

    def test_genuine_body_and_frontmatter_adr_status_ignore_conflicting_examples(self):
        for declaration in ("# ADR\n- Status: Accepted\n", "---\nstatus: Accepted\n---\n# ADR\n", "# ADR\n    <!--\n- Status: Accepted\n"):
            self.write("docs/adr/ADR-0038-first.md", declaration + "```yaml\nstatus: Proposed\n```\n<!--\nstatus: Rejected\n-->\n    status: Superseded\n")
            report = self.collect()
            self.assertTrue(report["adoptable"], report["diagnostics"])
            row = next(r for r in report["adrs"] if r["path"].endswith("first.md"))
            self.assertEqual(row["status"], "accepted")
            self.assertEqual(len(row["body_declarations"]), 1)

    def test_ten_input_alias_and_duplicate_paths_are_rejected(self):
        for value in ("planning//source-0.md", "planning/./source-0.md", "planning/source-0.md", "Planning/source-0.md", "planning/source-0.md."):
            self.sources[9] = value
            self.write_epics()
            self.assertFalse(self.collect()["adoptable"], value)

    def test_windows_aliases_forbidden_trees_and_device_paths(self):
        for path in ("Logs/x", "LOGS/x", ".GIT/config", "logs./x", "logs /x", "a//b", "a/../b", "C:/x", "a\\b", "NUL.txt", "a/COM1.txt", "a/x.", "a/x "):
            with self.subTest(path=path), self.assertRaises(ValueError):
                inventory.safe_input(self.root, path)

    def test_symlink_inputs_and_output_parents_refused(self):
        try:
            (self.root / "planning/alias.md").symlink_to(self.root / self.sources[0])
        except OSError:
            self.skipTest("Host cannot create symlinks")
        self.sources[9] = "planning/alias.md"
        self.write_epics()
        self.assert_invalid(self.collect(), "unsafe-or-unreadable-input")
        (self.root / "logs/redirect").mkdir()
        (self.root / "logs/ci").rename(self.root / "logs/ci-original")
        (self.root / "logs/ci").symlink_to(self.root / "logs/redirect", target_is_directory=True)
        self.assertEqual(self.cli(), 2)

    def test_reparse_attribute_detection_does_not_require_is_junction(self):
        fake_stat = SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
        with patch.object(Path, "lstat", return_value=fake_stat):
            with self.assertRaisesRegex(ValueError, "reparse"):
                inventory.no_reparse(self.root)

    def test_python_minimum_version_is_enforced_before_writing(self):
        before = self.bytes_before()
        with patch.object(inventory.sys, "version_info", (3, 11, 9)):
            self.assertEqual(self.cli(), 2)
        self.assertEqual(before, self.bytes_before())

    def test_source_set_bad_path_and_unresolved_glob_fail(self):
        doc = self.load(inventory.SOURCE_SET)
        doc["active_patterns"] = ["Logs/**/*"]
        self.dump(inventory.SOURCE_SET, doc)
        self.assert_invalid(self.collect(), "invalid-source-set")
        doc["active_patterns"] = ["docs/absent-*.md"]
        self.dump(inventory.SOURCE_SET, doc)
        self.assert_invalid(self.collect(), "missing-source-pattern")

    def test_source_glob_refuses_reparse_before_enumerating_log_tree(self):
        try:
            (self.root / "docs/aliased-sources").symlink_to(self.root / "logs", target_is_directory=True)
        except OSError:
            self.skipTest("Host cannot create symlinks")
        doc = self.load(inventory.SOURCE_SET)
        doc["active_patterns"] = ["docs/aliased-sources/**/*"]
        self.dump(inventory.SOURCE_SET, doc)
        with patch.object(inventory, "resolve_sources", side_effect=AssertionError("Unsafe resolver must not run")):
            self.assert_invalid(self.collect(), "invalid-source-set")

    def test_discovery_permission_error_blocks_an_otherwise_nonempty_authority_set(self):
        base = self.root / "docs/architecture/base"
        self.write("docs/architecture/base/denied/hidden.md", "# Hidden authority\n")
        walk = inventory.os.walk
        def denied_walk(path, *args, **kwargs):
            if Path(path) == base:
                yield str(base), [], ["07-build.md"]
                if kwargs.get("onerror"):
                    kwargs["onerror"](PermissionError(13, "Denied subtree", str(base / "denied")))
                return
            yield from walk(path, *args, **kwargs)
        with patch.object(inventory.os, "walk", denied_walk):
            report = self.collect()
        self.assert_invalid(report, "unreadable-discovery")
        self.assertTrue(any(d["code"] == "unreadable-discovery" and d["severity"] == "error" for d in report["diagnostics"]))

    def test_source_pattern_permission_error_is_visible_before_resolver(self):
        self.write("sources/input.md", "# Source\n")
        doc = self.load(inventory.SOURCE_SET)
        doc.update(active_patterns=["sources/**/*"], active_sources=["sources/input.md"])
        self.dump(inventory.SOURCE_SET, doc)
        walk = inventory.os.walk
        denied_hits = []
        def denied_walk(path, *args, **kwargs):
            if Path(path).resolve() == (self.root / "sources").resolve():
                denied_hits.append(str(path))
                if kwargs.get("onerror"):
                    kwargs["onerror"](PermissionError(13, "Denied source subtree", str(self.root / "sources/denied")))
                return
            yield from walk(path, *args, **kwargs)
        with patch.object(inventory.os, "walk", denied_walk), patch.object(inventory, "resolve_sources", side_effect=AssertionError("Resolver must not run")):
            report = self.collect()
        self.assertTrue(denied_hits, "The source traversal fault injection must execute")
        self.assert_invalid(report, "invalid-source-set")
        self.assertTrue(any("Source traversal failed" in d["message"] for d in report["diagnostics"]))

    def test_output_rejects_existing_logs_case_alias(self):
        (self.root / "logs").rename(self.root / "Logs")
        self.assertEqual(self.cli(), 2)

    def test_source_line_locator_and_consumer_symbol_failure(self):
        self.edit_task("back", lambda rows: rows[0].update(source_refs=["docs/source.md:999"]))
        self.assert_invalid(self.collect(), "invalid-reference-locator")
        self.write("scripts/sc/llm_generate_overlays_batch.py", "# Missing main\n")
        self.assert_invalid(self.collect(), "invalid-consumer-locator")

    def test_byte_drift_add_remove_discovery_and_git_identity_changes(self):
        callbacks = [lambda: self.write(self.sources[0], "Edited canonical\n"),
                     lambda: self.write("examples/new-helper.py", "# New example\n"),
                     lambda: (self.root / "examples/helper.py").unlink(),
                     lambda: self.run_git("checkout", "-qb", "changed-branch")]
        for callback in callbacks:
            self.assert_invalid(self.collect(between_passes=callback), "unstable-inputs")

    def test_git_z_preserves_unicode_spaces_tabs_newlines_and_rename_direction(self):
        names = ["special/中文 space.txt", "special/tab\tname.txt", "special/line\nname.txt"]
        if os.name == "nt":
            names = names[:1]
        for name in names:
            self.write(name, "Original\n")
        self.run_git("add", "special")
        self.run_git("commit", "-qm", "Special filenames")
        new_name = "special/重命名 target.txt"
        self.run_git("mv", names[0], new_name)
        for name in names[1:]:
            self.write(name, "Changed\n")
        changes = self.collect()["git"]["changes"]
        self.assertIn({"status": "R ", "path": new_name, "original_path": names[0]}, changes)
        for name in names[1:]:
            self.assertIn({"status": " M", "path": name}, changes)

    def test_staged_content_change_with_same_final_worktree_is_git_drift(self):
        self.write("unrelated.txt", "Base\n")
        self.run_git("add", "unrelated.txt")
        self.run_git("commit", "-qm", "Unrelated base")
        self.write("unrelated.txt", "Staged first\n")
        self.run_git("add", "unrelated.txt")
        self.write("unrelated.txt", "Final worktree\n")
        def change_index():
            self.write("unrelated.txt", "Staged second\n")
            self.run_git("add", "unrelated.txt")
            self.write("unrelated.txt", "Final worktree\n")
        report = self.collect(between_passes=change_index)
        self.assert_invalid(report, "unstable-inputs")
        self.assertTrue(report["drift"]["git_changed"])

    def test_explicit_root_must_be_repository_top_level(self):
        with self.assertRaisesRegex(ValueError, "top-level"):
            inventory.collect_inventory(self.root / "planning", "epics.md")

    def test_cli_invalid_roots_do_not_create_directories_or_modify_files(self):
        before, tree = self.bytes_before(), sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*"))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--root", str(self.root / "planning"), "--epics", "epics.md", "--run-id", "nested"]), 2)
        self.assertEqual(before, self.bytes_before())
        self.assertEqual(tree, sorted(p.relative_to(self.root).as_posix() for p in self.root.rglob("*")))
        with tempfile.TemporaryDirectory() as other:
            outside = Path(other)
            (outside / "keep.txt").write_text("Keep\n", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--root", other, "--epics", "epics.md", "--run-id", "outside"]), 2)
            self.assertEqual(sorted(p.name for p in outside.iterdir()), ["keep.txt"])
            self.assertEqual((outside / "keep.txt").read_text(encoding="utf-8"), "Keep\n")

    def test_git_timeout_after_reservation_writes_explicit_failure_evidence(self):
        run = inventory.subprocess.run
        def timeout_head(command, *args, **kwargs):
            if command[0] == "git" and command[4:] == ["rev-parse", "HEAD"]:
                raise subprocess.TimeoutExpired(command, 30)
            return run(command, *args, **kwargs)
        with patch.object(inventory.subprocess, "run", timeout_head):
            self.assertEqual(self.cli(), 1)
        failure = json.loads((self.output() / "failure.json").read_text(encoding="utf-8"))
        self.assertFalse(failure["adoptable"])
        self.assertEqual(failure["diagnostics"][0]["code"], "git-timeout")
        self.assertIn("timed out after 30 seconds", failure["error"])
        self.assertFalse((self.output() / "inventory.json").exists())

    def test_git_diff_external_and_textconv_drivers_are_executable_but_never_invoked(self):
        self.write("drivers/diff_driver.py", "from pathlib import Path\nimport sys\nPath(sys.argv[1]).write_text('executed', encoding='utf-8')\nprint('converted')\n")
        self.write("probe.txt", "Original\n")
        self.write(".gitattributes", "probe.txt diff=inventory-probe\n")
        self.run_git("add", "probe.txt", ".gitattributes")
        self.run_git("commit", "-qm", "Diff driver fixture")
        self.write("probe.txt", "Changed\n")
        external = self.root / "external-executed.txt"
        textconv = self.root / "textconv-executed.txt"
        command = lambda marker: " ".join(shlex.quote(str(p)) for p in (sys.executable, self.root / "drivers/diff_driver.py", marker))
        self.run_git("config", "diff.inventory-probe.textconv", command(textconv))
        with patch.dict(os.environ, {"GIT_EXTERNAL_DIFF": command(external)}):
            self.run_git("diff", "--no-textconv", "--", "probe.txt")
            self.assertTrue(external.is_file(), "Control must execute the external driver")
            external.unlink()
            self.run_git("diff", "--no-ext-diff", "--", "probe.txt")
            self.assertTrue(textconv.is_file(), "Control must execute the textconv driver")
            textconv.unlink()
            report = self.collect()
        self.assertTrue(report["adoptable"], report["diagnostics"])
        self.assertFalse(external.exists())
        self.assertFalse(textconv.exists())

    def test_manifest_planned_test_is_preserved_without_runtime_claim(self):
        self.manifest["tests"][0].update(state="planned", path="Game.Core.Tests/Future.cs")
        self.dump("docs/testing/mvg/fixture.json", self.manifest)
        report = self.collect()
        self.assertTrue(report["adoptable"], report["diagnostics"])
        self.assertEqual(report["manifests"][0]["document"]["tests"][0]["state"], "planned")
        self.assertIn("not-run", report["manifests"][0]["execution_claim"])

    def test_optional_planned_reference_reparse_and_permission_failures_block(self):
        path = "Game.Core.Tests/PlannedOnly.cs"
        self.write(path, "public class PlannedOnly {}\n")
        self.manifest["tests"][0].update(state="planned", path=path)
        self.dump("docs/testing/mvg/fixture.json", self.manifest)
        target = self.root / path
        hits = {"no_reparse": 0, "read_bytes": 0}
        no_reparse, read_bytes = inventory.no_reparse, Path.read_bytes
        def reparse(candidate):
            if candidate.resolve() == target.resolve():
                hits["no_reparse"] += 1
                raise ValueError("Reparse point fixture")
            return no_reparse(candidate)
        def denied(candidate):
            if candidate.resolve() == target.resolve():
                hits["read_bytes"] += 1
                raise PermissionError(13, "Denied planned test", str(candidate))
            return read_bytes(candidate)
        for name, guard in (("no_reparse", patch.object(inventory, "no_reparse", reparse)),
                            ("read_bytes", patch.object(Path, "read_bytes", denied))):
            with guard:
                report = self.collect()
            self.assertGreater(hits[name], 0, "The planned input fault injection must execute")
            self.assert_invalid(report, "unsafe-or-unreadable-input")
            self.assertTrue(any(d["code"] == "unsafe-or-unreadable-input" and d["severity"] == "error" and d["location"] == path
                                for d in report["diagnostics"]))

    def test_optional_unsafe_path_blocks_but_genuine_absence_remains_optional(self):
        snapshot = inventory.Snapshot(self.root, self.epics)
        self.assertIsNone(snapshot.read("logs/ci/historical/explicit.json", "optional-test", required=False))
        self.assertEqual(snapshot.diagnostics[-1]["severity"], "error")
        self.assertIsNone(snapshot.read("Game.Core.Tests/Absent.cs", "planned-test", required=False))
        self.assertEqual(snapshot.diagnostics[-1]["severity"], "warning")

    def test_binary_example_preserves_raw_resource_identity_and_detects_drift(self):
        path = "docs/workflows/examples/diagram.png"
        target = self.root / path
        target.write_bytes(b"\x89PNG\r\n\x1a\n\x00\xfffixture")
        report = self.collect()
        self.assertTrue(report["adoptable"], report["diagnostics"])
        row = next(r for r in report["consumers"] if r["path"] == path)
        self.assertEqual((row["locator_kind"], row["locator"], row["line"], row["symbol"]), ("resource", path, None, None))
        self.assertEqual(next(r["raw_sha256"] for r in report["inputs"] if r["path"] == path), inventory.file_sha(target))
        report = self.collect(between_passes=lambda: target.write_bytes(b"\x89PNG\x00\xffchanged"))
        self.assert_invalid(report, "unstable-inputs")
        self.assertEqual(report["drift"]["changed_inputs"], [path])
        self.assertFalse(report["drift"]["git_changed"])

    def test_manifest_invalid_id_and_missing_implemented_test_fail(self):
        self.manifest["tests"][0]["id"] = "BAD ID"
        self.dump("docs/testing/mvg/fixture.json", self.manifest)
        self.assert_invalid(self.collect(), "invalid-manifest")

    def test_cli_saved_markdown_contains_dynamic_locators_roles_status_and_diagnostics(self):
        self.write("scripts/sc/llm_generate_overlays_batch.py", "# Offset\n\n\ndef main():\n    pass\n")
        self.edit_task("back", lambda rows: rows[0]["evidence_refs"].append("logs/ci/<date>/task.json"))
        self.assertEqual(self.cli(), 0)
        output = self.output()
        report = json.loads((output / "inventory.json").read_text(encoding="utf-8"))
        text = (output / "inventory.md").read_text(encoding="utf-8")
        self.assertIn(report["content_identity"], text)
        self.assertIn("scripts/sc/llm_generate_overlays_batch.py:4", text)
        self.assertIn("Chapter4 generates overlays", text)
        self.assertIn("BACK-9", text)
        self.assertIn("pending", text)
        self.assertIn("/master/tasks/0/status", text)
        self.assertIn("historical-reference-template", text)
        self.assertIn("historical-debug-attachment / False", text)
        self.assertIn("current-input / True", text)
        self.assertIn("logs/ci/&lt;date&gt;/task.json", text)
        self.assertIn("logs/ci/<date>/task.json", [r["raw_reference"] for r in report["task_and_manifest_references"]])

    def test_saved_markdown_renders_worktree_renames_html_and_line_breaks(self):
        old, new = "special/source & name.txt", "special/renamed & target.txt"
        self.write(old, "Original\n")
        self.run_git("add", "special")
        self.run_git("commit", "-qm", "Markdown rename fixture")
        self.run_git("mv", old, new)
        if os.name != "nt":
            self.write("special/multi\nline.txt", "Line break fixture\n")
        self.edit_task("back", lambda rows: rows[0]["evidence_refs"].append("logs/ci/<date>/task.json"))
        self.assertEqual(self.cli(), 0)
        text = (self.output() / "inventory.md").read_text(encoding="utf-8")
        report = json.loads((self.output() / "inventory.json").read_text(encoding="utf-8"))
        self.assertIn("## Worktree changes", text)
        self.assertIn("Original path (rename/copy)", text)
        self.assertIn("| R  | special/renamed &amp; target.txt | special/source &amp; name.txt |", text)
        self.assertIn("logs/ci/&lt;date&gt;/task.json", text)
        self.assertNotIn("logs/ci/<date>/task.json", text)
        if os.name != "nt":
            self.assertIn("special/multi<br>line.txt", text)
        self.assertIn({"status": "R ", "path": new, "original_path": old}, report["git"]["changes"])
        self.assertIn("logs/ci/<date>/task.json", [r["raw_reference"] for r in report["task_and_manifest_references"]])

    def test_failure_markdown_is_saved_and_nonzero(self):
        self.edit_task("master", lambda rows: rows[1].pop("status"))
        self.assertEqual(self.cli(), 1)
        text = (self.output() / "inventory.md").read_text(encoding="utf-8")
        self.assertIn("Status: invalid; adoptable: False", text)
        self.assertIn("invalid-task-status", text)
        self.assertIn("/master/tasks/1/status", text)

    def test_no_overwrite_and_all_preexisting_bytes_unchanged_on_success_and_failure(self):
        before = self.bytes_before()
        self.assertEqual(self.cli(), 0)
        after_success = self.bytes_before()
        for path, sha in before.items():
            self.assertEqual(after_success[path], sha, path)
        self.assertEqual(self.cli(), 2)
        self.assertEqual(after_success, self.bytes_before())
        self.assertEqual(self.cli("failure-run", epics="planning/absent.md"), 1)
        after_failure = self.bytes_before()
        for path, sha in after_success.items():
            self.assertEqual(after_failure[path], sha, path)

    def test_output_run_id_traversal_alias_and_device_refused(self):
        for value in ("../escape", "a/b", "a\\b", "bad.", "bad ", "NUL", "CON", "x:y"):
            self.assertEqual(self.cli(run_id=value), 2, value)


if __name__ == "__main__":
    unittest.main()
