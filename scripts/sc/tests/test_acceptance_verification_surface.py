#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


REPO_ROOT = Path(__file__).resolve().parents[3]
SC_DIR = REPO_ROOT / "scripts" / "sc"
if str(SC_DIR) not in sys.path:
    sys.path.insert(0, str(SC_DIR))

from _acceptance_task_requirements import collect_task_refs  # noqa: E402
from _acceptance_verification_surface import validate_acceptance_verification  # noqa: E402


class AcceptanceVerificationSurfaceTests(unittest.TestCase):
    def _triplet(self, metadata: dict[str, object]) -> SimpleNamespace:
        return SimpleNamespace(
            task_id="15",
            back={
                "acceptance": ["ACC:T15.1 behavior"],
                "acceptance_verification": metadata,
            },
            gameplay=None,
        )

    def test_core_behavior_requires_bound_xunit_identity(self) -> None:
        good = self._triplet({
            "ACC:T15.1": {
                "verification_surface": "core-behavior",
                "primary_evidence": ["Game.Core.Tests/Combat/RewardTests.cs"],
                "secondary_evidence": [],
                "human_evidence_required": False,
            }
        })
        bad = self._triplet({
            "ACC:T15.1": {
                "verification_surface": "core-behavior",
                "primary_evidence": ["Tests.Godot/tests/test_reward.gd"],
                "secondary_evidence": [],
                "human_evidence_required": False,
            }
        })
        self.assertEqual("ok", validate_acceptance_verification(triplet=good)["status"])
        report = validate_acceptance_verification(triplet=bad)
        self.assertEqual("fail", report["status"])
        self.assertTrue(any("xUnit .cs" in item for item in report["errors"]))

    def test_godot_scene_requires_bound_gdunit_identity_and_routes_ref(self) -> None:
        triplet = self._triplet({
            "ACC:T15.1": {
                "verification_surface": "godot-scene",
                "primary_evidence": ["Tests.Godot/tests/Scenes/test_reward_scene.gd"],
                "secondary_evidence": ["Game.Core.Tests/Combat/RewardTests.cs"],
                "human_evidence_required": False,
            }
        })
        report = validate_acceptance_verification(triplet=triplet)
        self.assertEqual("ok", report["status"])
        refs = collect_task_refs(triplet)
        self.assertIn("Tests.Godot/tests/Scenes/test_reward_scene.gd", refs)
        self.assertIn("Game.Core.Tests/Combat/RewardTests.cs", refs)

    def test_human_experience_pending_and_failed_do_not_pass(self) -> None:
        for status in ("pending", "failed"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                triplet = self._triplet({
                    "ACC:T15.1": {
                        "verification_surface": "human-experience",
                        "primary_evidence": ["logs/manual/task-15-playtest.md"],
                        "secondary_evidence": [],
                        "human_evidence_required": True,
                        "human_evidence_status": status,
                    }
                })
                report = validate_acceptance_verification(triplet=triplet, root=root)
                self.assertEqual("fail", report["status"])

    def test_human_experience_pass_requires_real_revision_bound_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence = root / "logs/manual/task-15-playtest.md"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text(
                "# Task 15 playtest\n\nRevision: abc123\nResult: passed\n",
                encoding="utf-8",
            )
            triplet = self._triplet({
                "ACC:T15.1": {
                    "verification_surface": "human-experience",
                    "primary_evidence": ["logs/manual/task-15-playtest.md"],
                    "secondary_evidence": [],
                    "human_evidence_required": True,
                    "human_evidence_status": "passed",
                    "human_evidence_revision": "abc123",
                }
            })
            report = validate_acceptance_verification(triplet=triplet, root=root)
            self.assertEqual("ok", report["status"])
            self.assertEqual(["ACC:T15.1"], report["passed_anchors"])

    def test_human_experience_pass_rejects_missing_or_unbound_evidence(self) -> None:
        for case, extra in (
            ("missing_file", {"human_evidence_revision": "abc123"}),
            ("missing_revision", {}),
        ):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                if case == "missing_revision":
                    evidence = root / "logs/manual/task-15-playtest.md"
                    evidence.parent.mkdir(parents=True, exist_ok=True)
                    evidence.write_text("# playtest\n", encoding="utf-8")
                triplet = self._triplet({
                    "ACC:T15.1": {
                        "verification_surface": "human-experience",
                        "primary_evidence": ["logs/manual/task-15-playtest.md"],
                        "secondary_evidence": [],
                        "human_evidence_required": True,
                        "human_evidence_status": "passed",
                        **extra,
                    }
                })
                report = validate_acceptance_verification(triplet=triplet, root=root)
                self.assertEqual("fail", report["status"])
                self.assertTrue(report["errors"])

    def test_mixed_anchor_tracks_each_obligation_and_preserves_parent_anchor(self) -> None:
        triplet = self._triplet({
            "ACC:T15.1": {
                "obligations": [
                    {
                        "obligation_id": "core",
                        "verification_surface": "core-behavior",
                        "primary_evidence": ["Game.Core.Tests/Combat/RewardTests.cs"],
                        "secondary_evidence": [],
                        "human_evidence_required": False,
                    },
                    {
                        "obligation_id": "scene",
                        "verification_surface": "godot-scene",
                        "primary_evidence": ["Tests.Godot/tests/Scenes/test_reward_scene.gd"],
                        "secondary_evidence": [],
                        "human_evidence_required": False,
                    },
                ]
            }
        })
        report = validate_acceptance_verification(triplet=triplet)
        self.assertEqual("ok", report["status"])
        self.assertEqual(["ACC:T15.1"], report["passed_anchors"])
        self.assertEqual(
            ["core-behavior", "godot-scene"],
            report["surfaces"]["ACC:T15.1"],
        )
        self.assertEqual(
            {"core", "scene"},
            {item["obligation_id"] for item in report["obligations"]["ACC:T15.1"]},
        )
        self.assertTrue(all(
            item["source_anchor"] == "ACC:T15.1"
            for item in report["obligations"]["ACC:T15.1"]
        ))
        refs = collect_task_refs(triplet)
        self.assertIn("Game.Core.Tests/Combat/RewardTests.cs", refs)
        self.assertIn("Tests.Godot/tests/Scenes/test_reward_scene.gd", refs)

    def test_mixed_anchor_fails_when_one_obligation_is_pending(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            triplet = self._triplet({
                "ACC:T15.1": {
                    "obligations": [
                        {
                            "obligation_id": "core",
                            "verification_surface": "core-behavior",
                            "primary_evidence": ["Game.Core.Tests/Combat/RewardTests.cs"],
                            "secondary_evidence": [],
                            "human_evidence_required": False,
                        },
                        {
                            "obligation_id": "feel",
                            "verification_surface": "human-experience",
                            "primary_evidence": ["logs/manual/task-15-playtest.md"],
                            "secondary_evidence": [],
                            "human_evidence_required": True,
                            "human_evidence_status": "pending",
                        },
                    ]
                }
            })
            report = validate_acceptance_verification(triplet=triplet, root=root)
            self.assertEqual("fail", report["status"])
            self.assertEqual(["ACC:T15.1"], report["pending_anchors"])
            self.assertNotIn("ACC:T15.1", report["passed_anchors"])

    def test_player_journey_can_bind_mixed_existing_evidence(self) -> None:
        triplet = self._triplet({
            "ACC:T15.1": {
                "verification_surface": "player-journey",
                "primary_evidence": ["Tests.Godot/tests/Journey/test_combat_reward_return.gd"],
                "secondary_evidence": ["Game.Core.Tests/Combat/RewardTests.cs"],
                "human_evidence_required": False,
            }
        })
        report = validate_acceptance_verification(triplet=triplet)
        self.assertEqual("ok", report["status"])
        self.assertEqual("player-journey", report["surfaces"]["ACC:T15.1"])


if __name__ == "__main__":
    unittest.main()
