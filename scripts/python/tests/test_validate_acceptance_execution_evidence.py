from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


PYTHON_DIR = Path(__file__).resolve().parents[1]
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from validate_acceptance_execution_evidence import validate_view  # noqa: E402


class ClassifiedExecutionEvidenceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
