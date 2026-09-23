#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
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
from _acceptance_verification_surface import infer_legacy_verification_candidates, validate_acceptance_verification  # noqa: E402


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

    def test_legacy_xunit_ref_yields_core_candidate_without_writing_authority(self) -> None:
        triplet = SimpleNamespace(
            task_id="15",
            back={
                "acceptance": [
                    "ACC behavior must keep deterministic reward totals. Refs: Game.Core.Tests/Combat/RewardTests.cs",
                ],
            },
            gameplay=None,
        )
        candidates = infer_legacy_verification_candidates(triplet)
        row = candidates["ACC:T15.1"]
        self.assertEqual("candidate", row["status"])
        self.assertEqual("core-behavior", row["suggested_surface"])
        self.assertEqual(["core-behavior"], row["candidate_surfaces"])
        self.assertNotIn("acceptance_verification", triplet.back)

    def test_legacy_generic_tests_cs_ref_is_a_core_candidate(self) -> None:
        triplet = SimpleNamespace(
            task_id="15",
            back={
                "acceptance": [
                    "Pure deterministic behavior remains covered. Refs: Tests/LegacyRewardTests.cs",
                ],
            },
            gameplay=None,
        )
        row = infer_legacy_verification_candidates(triplet)["ACC:T15.1"]
        self.assertEqual("candidate", row["status"])
        self.assertEqual("core-behavior", row["suggested_surface"])

    def test_legacy_gdunit_scene_ref_yields_scene_candidate(self) -> None:
        triplet = SimpleNamespace(
            task_id="15",
            back={
                "acceptance": [
                    "Scene lifecycle and signal wiring must preserve reward UI state. Refs: Tests.Godot/tests/Scenes/test_reward_scene.gd",
                ],
            },
            gameplay=None,
        )
        row = infer_legacy_verification_candidates(triplet)["ACC:T15.1"]
        self.assertEqual("candidate", row["status"])
        self.assertEqual("godot-scene", row["suggested_surface"])

    def test_legacy_mixed_refs_require_confirmation_without_journey_semantics(self) -> None:
        triplet = SimpleNamespace(
            task_id="15",
            back={
                "acceptance": [
                    "Reward behavior must remain correct. Refs: Game.Core.Tests/Combat/RewardTests.cs Tests.Godot/tests/Scenes/test_reward_scene.gd",
                ],
            },
            gameplay=None,
        )
        row = infer_legacy_verification_candidates(triplet)["ACC:T15.1"]
        self.assertEqual("needs-confirmation", row["status"])
        self.assertEqual("", row["suggested_surface"])
        self.assertIn("player-journey", row["candidate_surfaces"])
        self.assertIn("core-behavior", row["candidate_surfaces"])
        self.assertIn("godot-scene", row["candidate_surfaces"])

    def test_legacy_subjective_semantics_never_auto_classify_from_machine_ref(self) -> None:
        triplet = SimpleNamespace(
            task_id="15",
            back={
                "acceptance": [
                    "Combat pacing and visual readability must feel clear in playtest. Refs: Tests.Godot/tests/Scenes/test_combat_scene.gd",
                ],
            },
            gameplay=None,
        )
        row = infer_legacy_verification_candidates(triplet)["ACC:T15.1"]
        self.assertEqual("needs-confirmation", row["status"])
        self.assertEqual("", row["suggested_surface"])
        self.assertEqual(["human-experience"], row["candidate_surfaces"])

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

    def test_core_and_scene_surfaces_reject_production_code_as_test_evidence(self) -> None:
        cases = (
            (
                "core-behavior",
                ["Game.Core/Combat/RewardService.cs"],
                "Game.Core.Tests xUnit .cs identity",
            ),
            (
                "godot-scene",
                ["Game.Godot/Scripts/UI/CombatScene.gd"],
                "Tests.Godot GdUnit .gd identity",
            ),
        )
        for surface, primary, expected_error in cases:
            with self.subTest(surface=surface):
                triplet = self._triplet({
                    "ACC:T15.1": {
                        "verification_surface": surface,
                        "primary_evidence": primary,
                        "secondary_evidence": [],
                        "human_evidence_required": False,
                    }
                })

                report = validate_acceptance_verification(triplet=triplet)

                self.assertEqual("fail", report["status"])
                self.assertTrue(any(expected_error in item for item in report["errors"]))

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

    def test_automated_surface_fails_final_acceptance_when_primary_test_file_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            triplet = self._triplet({
                "ACC:T15.1": {
                    "verification_surface": "core-behavior",
                    "primary_evidence": ["Game.Core.Tests/Combat/RewardTests.cs"],
                    "secondary_evidence": [],
                    "human_evidence_required": False,
                }
            })

            report = validate_acceptance_verification(triplet=triplet, root=root)

            self.assertEqual("fail", report["status"])
            self.assertTrue(any("automated primary_evidence files do not exist" in item for item in report["errors"]))

    def test_automated_surface_accepts_existing_bound_primary_test_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence = root / "Game.Core.Tests/Combat/RewardTests.cs"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text("public sealed class RewardTests {}\n", encoding="utf-8")
            triplet = self._triplet({
                "ACC:T15.1": {
                    "verification_surface": "core-behavior",
                    "primary_evidence": ["Game.Core.Tests/Combat/RewardTests.cs"],
                    "secondary_evidence": [],
                    "human_evidence_required": False,
                }
            })

            report = validate_acceptance_verification(triplet=triplet, root=root)

            self.assertEqual("ok", report["status"])

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
                report = validate_acceptance_verification(
                    triplet=triplet,
                    root=root,
                    expected_revision="abc123",
                )
                self.assertEqual("fail", report["status"])

    def test_human_experience_pass_requires_real_revision_bound_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence = root / "logs/manual/task-15-playtest.md"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text(
                "# Task 15 playtest\n\nTask_ID: 15\nAcceptance_Anchor: ACC:T15.1\n"
                "Obligation_ID:\nRevision: abc123\nResult: passed\n",
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
            report = validate_acceptance_verification(
                triplet=triplet,
                root=root,
                expected_revision="abc123",
            )
            self.assertEqual("ok", report["status"])
            self.assertEqual(["ACC:T15.1"], report["passed_anchors"])

    def test_human_experience_pass_rejects_evidence_for_previous_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            evidence = root / "logs/manual/task-15-playtest.json"
            evidence.parent.mkdir(parents=True, exist_ok=True)
            evidence.write_text(json.dumps({
                "task_id": "15",
                "acceptance_anchor": "ACC:T15.1",
                "obligation_id": "",
                "revision": "old-revision",
                "result": "passed",
            }), encoding="utf-8")
            triplet = self._triplet({
                "ACC:T15.1": {
                    "verification_surface": "human-experience",
                    "primary_evidence": ["logs/manual/task-15-playtest.json"],
                    "secondary_evidence": [],
                    "human_evidence_required": True,
                    "human_evidence_status": "passed",
                    "human_evidence_revision": "old-revision",
                }
            })
            report = validate_acceptance_verification(
                triplet=triplet,
                root=root,
                expected_revision="current-revision",
            )
        self.assertEqual("fail", report["status"])
        self.assertTrue(any("does not match current candidate" in item for item in report["errors"]))

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

    def test_human_experience_pass_rejects_revision_or_conclusion_mismatch(self) -> None:
        cases = (
            ("revision_mismatch", "# playtest\n\nRevision: other\nResult: passed\n"),
            ("missing_passed_conclusion", "# playtest\n\nRevision: abc123\nResult: pending\n"),
        )
        for case, content in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                evidence = root / "logs/manual/task-15-playtest.md"
                evidence.parent.mkdir(parents=True, exist_ok=True)
                evidence.write_text(content, encoding="utf-8")
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

                report = validate_acceptance_verification(
                    triplet=triplet,
                    root=root,
                    expected_revision="abc123",
                )

                self.assertEqual("fail", report["status"])
                self.assertTrue(any("passed human evidence must explicitly bind" in item for item in report["errors"]))

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

    def test_player_journey_rejects_document_only_primary_evidence(self) -> None:
        triplet = self._triplet({
            "ACC:T15.1": {
                "verification_surface": "player-journey",
                "primary_evidence": ["docs/testing/mvg/m1-critical.json"],
                "secondary_evidence": [],
                "human_evidence_required": False,
            }
        })

        report = validate_acceptance_verification(triplet=triplet)

        self.assertEqual("fail", report["status"])
        self.assertTrue(any("executable Game.Core.Tests .cs" in item for item in report["errors"]))

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

    def test_player_journey_mvg_critical_requires_revision_bound_runtime_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            manifest_ref = "docs/testing/mvg/m1-critical.json"
            manifest = root / manifest_ref
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({"mvg_id": "m1-critical", "coverage": {"mode": "critical", "blocking_task_ids": []}}), encoding="utf-8")
            summary = root / "logs/ci/mvg-acceptance/run-1/summary.json"
            summary.parent.mkdir(parents=True, exist_ok=True)
            summary.write_text(json.dumps({
                "mode": "run", "status": "passed", "runtime_verified": True, "workspace_dirty": False,
                "source_revision": "abc123", "manifest": manifest_ref,
                "coverage": {"mode": "critical", "blocking_task_ids": []},
            }), encoding="utf-8")
            triplet = self._triplet({"ACC:T15.1": {
                "verification_surface": "player-journey", "journey_scope": "mvg-critical",
                "primary_evidence": [manifest_ref], "secondary_evidence": [], "human_evidence_required": False,
            }})
            passed = validate_acceptance_verification(triplet=triplet, root=root, expected_revision="abc123")
            stale = validate_acceptance_verification(triplet=triplet, root=root, expected_revision="different-revision")
            self.assertEqual("ok", passed["status"])
            self.assertEqual("fail", stale["status"])
            self.assertTrue(any("runtime_verified MVG critical evidence" in item for item in stale["errors"]))

    def test_player_journey_mvg_full_cannot_reuse_critical_scope(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            full_ref = "docs/testing/mvg/m1-full.json"
            manifest = root / full_ref
            manifest.parent.mkdir(parents=True, exist_ok=True)
            manifest.write_text(json.dumps({"mvg_id": "m1-full", "coverage": {"mode": "full", "blocking_task_ids": []}}), encoding="utf-8")
            summary = root / "logs/ci/mvg-acceptance/run-critical/summary.json"
            summary.parent.mkdir(parents=True, exist_ok=True)
            summary.write_text(json.dumps({
                "mode": "run", "status": "passed", "runtime_verified": True, "workspace_dirty": False,
                "source_revision": "abc123", "manifest": "docs/testing/mvg/m1-critical.json",
                "coverage": {"mode": "critical", "blocking_task_ids": []},
            }), encoding="utf-8")
            triplet = self._triplet({"ACC:T15.1": {
                "verification_surface": "player-journey", "journey_scope": "mvg-full",
                "primary_evidence": [full_ref], "secondary_evidence": [], "human_evidence_required": False,
            }})
            report = validate_acceptance_verification(triplet=triplet, root=root, expected_revision="abc123")
            self.assertEqual("fail", report["status"])
            self.assertTrue(any("runtime_verified MVG full evidence" in item for item in report["errors"]))


if __name__ == "__main__":
    unittest.main()
