from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SC_DIR = Path(__file__).resolve().parents[1]
if str(SC_DIR) not in sys.path:
    sys.path.insert(0, str(SC_DIR))

import acceptance_check  # noqa: E402
from _acceptance_verification_surface import requires_task_local_execution_evidence  # noqa: E402


class ClassifiedExecutionGateTests(unittest.TestCase):
    def test_only_classified_task_local_automation_requires_test_execution(self) -> None:
        def triplet(row: dict[str, object] | None) -> SimpleNamespace:
            back = {"acceptance_verification": {"ACC:T15.1": row}} if row is not None else {}
            return SimpleNamespace(back=back, gameplay=None)

        self.assertTrue(requires_task_local_execution_evidence(triplet({
            "obligations": [
                {"verification_surface": "human-experience"},
                {"verification_surface": "godot-scene"},
            ],
        })))
        self.assertTrue(requires_task_local_execution_evidence(triplet({
            "verification_surface": "player-journey", "journey_scope": "task-local",
        })))
        for row in (
            None,
            {"verification_surface": "human-experience"},
            {"verification_surface": "player-journey", "journey_scope": "mvg-critical"},
            {"verification_surface": "player-journey", "journey_scope": "mvg-full"},
        ):
            self.assertFalse(requires_task_local_execution_evidence(triplet(row)))

    def test_dry_run_real_entry_plans_classified_execution_gate_across_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ref = "Game.Core.Tests/Tasks/Task15Tests.cs"
            path = root / ref
            path.parent.mkdir(parents=True)
            path.write_text("public class Task15Tests\n{\n// ACC:T15.1\n[Fact]\npublic void CoreWorks() {}\n}", encoding="utf-8")
            triplet = SimpleNamespace(
                task_id="15", master={"title": "Classified core behavior"},
                back={
                    "acceptance": [f"Core behavior. Refs: {ref}"],
                    "acceptance_verification": {"ACC:T15.1": {
                        "verification_surface": "core-behavior", "primary_evidence": [ref],
                        "human_evidence_required": False,
                    }},
                },
                gameplay=None,
            )
            for profile in ("fast-ship", "playable-ea", "standard"):
                with self.subTest(profile=profile), \
                    patch.object(sys, "argv", [
                        "acceptance_check.py", "--task-id", "15", "--delivery-profile", profile,
                        "--dry-run-plan", "--only", "tests",
                    ]), \
                    patch.object(acceptance_check, "_restore_task_triplet_from_head_if_needed"), \
                    patch.object(acceptance_check, "resolve_triplet", return_value=triplet), \
                    patch.object(acceptance_check, "repo_root", return_value=root), \
                    patch.object(acceptance_check, "ci_dir", return_value=root / "out"):
                    self.assertEqual(0, acceptance_check.main())
                summary = json.loads((root / "out" / "summary.json").read_text(encoding="utf-8"))
                gate = next(item for item in summary["step_plan"] if item["name"] == "acceptance-executed-refs")
                self.assertTrue(gate["enabled"])


if __name__ == "__main__":
    unittest.main()
