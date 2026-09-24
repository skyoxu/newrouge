"""Regression tests for reviewed incremental writes and cumulative evidence."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/python"))

import build_source_ledger as source_mod
import build_taskmaster_tasks as master_mod
import compile_task_triplet as triplet_mod
import milestone_incremental_handoff as handoff_mod
import normalize_task_intents as intent_mod
import update_mvg_baseline as baseline_mod


def save(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class MilestoneHotfixTests(unittest.TestCase):
    def test_triplet_write_consumes_reviewed_actions_and_rejects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            back = root / ".taskmaster/tasks/tasks_back.json"
            save(back, [{"id": "NG-1", "title": "Old", "status": "done", "acceptance": ["Keep"]}])
            save(root / ".taskmaster/tasks/tasks_gameplay.json", [])
            save(root / "candidates.json", {"candidates": [{"id": "NG-1", "owner": "architecture", "change_action": "update", "field_updates": {"title": "New"}}]})
            save(root / "coverage.json", {"status": "ok"})
            args = ["compile_task_triplet.py", "--repo-root", str(root), "--candidates", "candidates.json", "--coverage", "coverage.json"]
            with patch.object(sys, "argv", args):
                self.assertEqual(0, triplet_mod.main())
            with patch.object(sys, "argv", args + ["--write"]):
                self.assertEqual(0, triplet_mod.main())
            self.assertEqual("New", json.loads(back.read_text())[0]["title"])
            self.assertEqual("done", json.loads(back.read_text())[0]["status"])
            self.assertEqual(["Keep"], json.loads(back.read_text())[0]["acceptance"])
            with patch.object(sys, "argv", args + ["--write"]), self.assertRaisesRegex(SystemExit, "differs from reviewed preview"):
                triplet_mod.main()

    def test_intent_ids_survive_ignored_output_deletion(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "requirements.json"
            original = {"schema": "task-generation.requirements-index.v1", "anchors": [{
                "requirement_id": "REQ-COMBAT-0001", "source_path": "docs/gdd/combat.md", "line": 1,
                "kind": "gdd", "priority": "P1", "text": "Combat enemy attack damage targeting must be implemented.", "refs": [],
            }]}
            save(index, original)
            args = ["--repo-root", str(root), "--requirements", "requirements.json", "--mode", "add"]
            self.assertEqual(0, intent_mod.main(args))
            out = root / "logs/ci/task-generation/task-intents.normalized.json"
            old = json.loads(out.read_text())["intents"][0]
            out.unlink()
            save(index, {**original, "anchors": [{
                "requirement_id": "REQ-UI-0001", "source_path": "docs/gdd/ui.md", "line": 1,
                "kind": "gdd", "priority": "P2", "text": "UI HUD display must be implemented.", "refs": [],
            }, *original["anchors"]]})
            self.assertEqual(0, intent_mod.main(args))
            current = {row["intent_key"]: row["id"] for row in json.loads(out.read_text())["intents"]}
            self.assertEqual(old["id"], current[old["intent_key"]])
            self.assertEqual(2, len(set(current.values())))

    def test_master_export_rollback_on_second_replace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            master = root / "tasks.json"
            back = root / "tasks_back.json"
            game = root / "tasks_gameplay.json"
            save(master, {"master": {"tasks": [{"id": 6, "subtasks": [{"id": 1, "status": "done"}]}]}})
            save(back, [{"id": "NG-6", "taskmaster_id": 6, "title": "Shared", "status": "done", "story_id": "NG", "depends_on": []}])
            save(game, [{"id": "GM-6", "taskmaster_id": 6, "title": "Shared", "status": "pending", "story_id": "GM", "depends_on": []}])
            original = {path: path.read_bytes() for path in (master, back, game)}
            args = SimpleNamespace(tasks_files=[str(back), str(game)], ids=["NG-6", "GM-6"], ids_file="", tag="master", allow_legacy_t2_default=False)
            original_replace = master_mod.os.replace
            calls = 0

            def fail_second(src, dst):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("injected second replacement failure")
                return original_replace(src, dst)

            with patch.object(master_mod, "ROOT", root), patch.object(master_mod, "TASKMASTER_TASKS_FILE", master), patch.object(master_mod.os, "replace", side_effect=fail_second):
                with self.assertRaisesRegex(OSError, "injected"):
                    master_mod.build_taskmaster_tasks(args)
            self.assertEqual(original, {path: path.read_bytes() for path in original})
            with patch.object(master_mod, "ROOT", root), patch.object(master_mod, "TASKMASTER_TASKS_FILE", master):
                master_mod.build_taskmaster_tasks(args)
            generated = json.loads(master.read_text())["master"]["tasks"][0]
            self.assertEqual("pending", generated["status"])
            self.assertEqual([{"id": 1, "status": "done"}], generated["subtasks"])
            self.assertEqual(6, json.loads(back.read_text())[0]["taskmaster_id"])
            self.assertTrue(json.loads(game.read_text())[0]["taskmaster_exported"])

    def test_handoff_projection_and_baseline_weakenings_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save(root / ".taskmaster/tasks/tasks_back.json", [{"id": "NG-1"}])
            plan = root / "plan.json"
            readiness = root / "ready.json"
            save(plan, {"schema_version": handoff_mod.CHANGE_PLAN_SCHEMA, "source_identity": {"source_revision": "source-set:old"}, "changes": [{"change_id": "c", "action": "extend", "target_task_id": "NG-1", "owner_task_id": "NG-1", "reason": "reviewed", "impact": {}, "verification": {"required_regressions": ["old-test"]}}]})
            save(readiness, {"schema_version": "newrouge.chapter5-readiness.v1", "task_id": "NG-1", "closure_allowed": True, "input_fingerprint": {"sha256": "stable"}})
            payload = handoff_mod.build_task_handoff(root, plan_path=plan, task_id="NG-1", readiness_path=readiness)
            payload["required_regressions"] = []
            handoff = root / "handoff.json"
            save(handoff, payload)
            self.assertEqual("milestone_handoff_projection_drift", handoff_mod.validate_task_handoff(root, handoff, "NG-1")[1])
        with self.assertRaisesRegex(ValueError, "authority_ref"):
            baseline_mod._apply_rows([{"id": "old", "min_tests": 10}], [{"id": "old", "action": "update", "reason": "weaken", "field_updates": {"min_tests": 1}}], "flow")

    def test_glob_source_set_requires_explicit_retirement_of_removed_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save(root / "docs/workflows/chapter3-source-set.json", {"schema_version": "chapter3.source-set.v1", "active_patterns": ["docs/gdd/**/*.md"], "active_sources": ["docs/gdd/old.md", "docs/gdd/new.md"]})
            source = root / "docs/gdd/new.md"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("# New\n\nRequirement.\n", encoding="utf-8")
            self.assertEqual(2, source_mod.main(["--repo-root", str(root), "--mode", "add"]))

    def test_chapter6_regression_consumption_requires_current_manifest_and_passed_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            # Commit identity is supplied per invocation to avoid relying on host config.
            subprocess.run(["git", "-C", str(root), "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "--allow-empty", "-qm", "baseline"], check=True)
            revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
            manifest = root / "docs/testing/mvg/critical.json"
            save(manifest, {"tests": [{"id": "old-test"}]})
            summary = root / "logs/ci/mvg-acceptance/run/summary.json"
            save(summary, {
                "schema_version": "newrouge.mvg-acceptance.v1", "manifest": "docs/testing/mvg/critical.json",
                "manifest_sha256": handoff_mod._file_sha(manifest), "mode": "run", "status": "passed",
                "runtime_verified": True, "workspace_dirty": False, "source_revision": revision,
                "steps": [{"id": "old-test", "status": "passed"}],
            })
            handoff = {"required_regressions": ["old-test"]}
            self.assertEqual((True, "ok"), handoff_mod.validate_milestone_regressions(root, handoff, summary))
            save(summary, {**json.loads(summary.read_text()), "steps": [{"id": "old-test", "status": "failed"}]})
            self.assertEqual("milestone_required_regressions_not_passed", handoff_mod.validate_milestone_regressions(root, handoff, summary)[1])
            manifest.write_text(manifest.read_text() + "\n", encoding="utf-8")
            self.assertEqual("milestone_regression_evidence_stale_or_unverified", handoff_mod.validate_milestone_regressions(root, handoff, summary)[1])


if __name__ == "__main__":
    unittest.main()
