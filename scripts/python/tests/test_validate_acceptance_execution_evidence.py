from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


PYTHON_DIR = Path(__file__).resolve().parents[1]
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from validate_acceptance_execution_evidence import (  # noqa: E402
    parse_junit_testcase_names,
    parse_trx_test_names,
    validate_view,
)


class ClassifiedExecutionEvidenceTests(unittest.TestCase):
    def test_skipped_and_failed_results_cannot_satisfy_classified_obligations(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            core = "Game.Core.Tests/Tasks/Task15Tests.cs"
            scene = "Tests.Godot/tests/Scenes/test_task_15.gd"
            for ref, source in (
                (core, "public class Task15Tests\n{\n// ACC:T15.1\n[Fact]\npublic void CoreWorks() {}\n}"),
                (scene, "# ACC:T15.1\nfunc test_scene_works():\n    pass"),
            ):
                path = root / ref
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(source, encoding="utf-8")
            entry = {
                "acceptance": [f"Mixed behavior. Refs: {core} {scene}"],
                "acceptance_verification": {"ACC:T15.1": {"obligations": [
                    {"obligation_id": "core", "verification_surface": "core-behavior", "primary_evidence": [core]},
                    {"obligation_id": "scene", "verification_surface": "godot-scene", "primary_evidence": [scene]},
                ]}},
            }
            trx = root / "run.trx"
            junit = root / "results.xml"
            for core_outcome, scene_result, expected in (
                ("Passed", "", "ok"),
                ("Passed", "<skipped/>", "fail"),
                ("NotExecuted", "<skipped/>", "fail"),
                ("Failed", "<failure/>", "fail"),
            ):
                trx.write_text(
                    f'<TestRun><Results><UnitTestResult testName="Game.Core.Tests.Tasks.Task15Tests.CoreWorks" '
                    f'outcome="{core_outcome}"/></Results></TestRun>', encoding="utf-8",
                )
                junit.write_text(
                    f'<testsuites><testsuite><testcase name="test_scene_works">{scene_result}'
                    '</testcase></testsuite></testsuites>', encoding="utf-8",
                )
                result = validate_view(
                    root=root, view_name="back", task_id="15", entry=entry,
                    trx_names=parse_trx_test_names(trx), gdunit_names=parse_junit_testcase_names(junit),
                )
                self.assertEqual(expected, result["status"], (core_outcome, scene_result))

    def test_mixed_anchor_requires_each_automated_obligation_to_execute(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            core = "Game.Core.Tests/Tasks/Task15Tests.cs"
            scene = "Tests.Godot/tests/Scenes/test_task_15.gd"
            for ref, content in (
                (core, "public class Task15Tests\n{\n// ACC:T15.1\n[Fact]\npublic void CoreWorks() {}\n}"),
                (scene, "# ACC:T15.1\nfunc test_scene_works():\n    assert_bool(true).is_true()"),
            ):
                path = root / ref
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            entry = {
                "acceptance": [f"Mixed behavior. Refs: {core} {scene}"],
                "acceptance_verification": {"ACC:T15.1": {"obligations": [
                    {"obligation_id": "core", "verification_surface": "core-behavior", "primary_evidence": [core]},
                    {"obligation_id": "scene", "verification_surface": "godot-scene", "primary_evidence": [scene]},
                ]}},
            }
            kwargs = dict(
                root=root, view_name="back", task_id="15", entry=entry,
                trx_names={"Game.Core.Tests.Tasks.Task15Tests.CoreWorks"},
            )
            missing_scene = validate_view(**kwargs, gdunit_names=set())
            self.assertEqual("fail", missing_scene["status"])
            self.assertEqual(["ok", "fail"], [item["status"] for item in missing_scene["items"]])
            self.assertIn("ACC:T15.1#scene", " ".join(missing_scene["errors"]))

            complete = validate_view(**kwargs, gdunit_names={"test_scene_works"})
            self.assertEqual("ok", complete["status"])
            self.assertEqual(["ok", "ok"], [item["status"] for item in complete["items"]])

    def test_human_obligation_has_separate_evidence_gate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            core = "Game.Core.Tests/Tasks/Task15Tests.cs"
            path = root / core
            path.parent.mkdir(parents=True)
            path.write_text("public class Task15Tests\n{\n// ACC:T15.1\n[Fact]\npublic void CoreWorks() {}\n}", encoding="utf-8")
            entry = {
                "acceptance": [f"Core and playtest. Refs: {core}"],
                "acceptance_verification": {"ACC:T15.1": {"obligations": [
                    {"obligation_id": "core", "verification_surface": "core-behavior", "primary_evidence": [core]},
                    {"obligation_id": "feel", "verification_surface": "human-experience", "primary_evidence": ["logs/manual/playtest.md"]},
                ]}},
            }
            result = validate_view(root=root, view_name="back", task_id="15", entry=entry,
                                   trx_names={"Game.Core.Tests.Tasks.Task15Tests.CoreWorks"}, gdunit_names=set())
            self.assertEqual("ok", result["status"])
            self.assertEqual(["ok", "not_required"], [item["status"] for item in result["items"]])

    def test_mvg_critical_journey_requires_runtime_verified_matching_revision(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest_ref = "docs/testing/mvg/m1-critical.json"
            manifest = root / manifest_ref
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({"coverage": {"mode": "critical", "blocking_task_ids": []}}), encoding="utf-8")
            summary = root / "logs/ci/mvg-acceptance/run-1/summary.json"
            summary.parent.mkdir(parents=True, exist_ok=True)
            summary.write_text(json.dumps({
                "mode": "run", "status": "passed", "runtime_verified": True, "workspace_dirty": False,
                "source_revision": "abc123", "manifest": manifest_ref,
                "coverage": {"mode": "critical", "blocking_task_ids": []},
            }), encoding="utf-8")
            entry = {
                "acceptance": [f"Integrated journey. Refs: {manifest_ref}"],
                "acceptance_verification": {"ACC:T15.1": {
                    "verification_surface": "player-journey",
                    "journey_scope": "mvg-critical",
                    "primary_evidence": [manifest_ref],
                }},
            }
            passed = validate_view(
                root=root, view_name="back", task_id="15", entry=entry,
                trx_names=set(), gdunit_names=set(), candidate_revision="abc123",
            )
            stale = validate_view(
                root=root, view_name="back", task_id="15", entry=entry,
                trx_names=set(), gdunit_names=set(), candidate_revision="old",
            )
            self.assertEqual("ok", passed["status"])
            self.assertEqual("fail", stale["status"])
            self.assertTrue(passed["items"][0]["mvg_summary"].endswith("summary.json"))

    def test_mvg_full_journey_rejects_plan_only_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest_ref = "docs/testing/mvg/m1-full.json"
            manifest = root / manifest_ref
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({"coverage": {"mode": "full", "blocking_task_ids": []}}), encoding="utf-8")
            summary = root / "logs/ci/mvg-acceptance/run-1/summary.json"
            summary.parent.mkdir(parents=True, exist_ok=True)
            summary.write_text(json.dumps({
                "mode": "plan", "status": "planned", "runtime_verified": False, "workspace_dirty": False,
                "source_revision": "abc123", "manifest": manifest_ref,
                "coverage": {"mode": "full", "blocking_task_ids": []},
            }), encoding="utf-8")
            entry = {
                "acceptance": [f"Full journey. Refs: {manifest_ref}"],
                "acceptance_verification": {"ACC:T15.1": {
                    "verification_surface": "player-journey",
                    "journey_scope": "mvg-full",
                    "primary_evidence": [manifest_ref],
                }},
            }
            report = validate_view(
                root=root, view_name="back", task_id="15", entry=entry,
                trx_names=set(), gdunit_names=set(), candidate_revision="abc123",
            )
            self.assertEqual("fail", report["status"])
            self.assertIn("runtime_verified MVG full evidence", " ".join(report["errors"]))


if __name__ == "__main__":
    unittest.main()
