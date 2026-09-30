#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PYTHON = ROOT / "scripts" / "python"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))

from _chapter7_profile import load_chapter7_profile
from _planning_skill_common import _write_model_batches
from compile_task_triplet import build_change_plan
from dev_cli import build_parser
from normalize_task_intents import build_intents, semantic_to_anchors


class WorkflowPortabilityAcceptanceTests(unittest.TestCase):
    def test_ac03_same_generated_numeric_identity_can_have_different_semantics(self) -> None:
        blocks = {
            "blocks": [{
                "block_id": "SB-1",
                "source_path": "docs/gdd/game.md",
                "line_start": 1,
                "heading_path": ["Game"],
            }]
        }
        functional = {
            "requirements": [{
                "requirement_id": "RQ-1",
                "statement": "Player launches the relay.",
                "kind": "functional",
                "priority": "P1",
                "delivery_relevant": True,
                "status": "active",
                "source_block_ids": ["SB-1"],
            }]
        }
        governance = {
            "requirements": [{
                "requirement_id": "RQ-2",
                "statement": "Build output must preserve the audit manifest.",
                "kind": "non_functional",
                "priority": "P1",
                "delivery_relevant": True,
                "status": "active",
                "source_block_ids": ["SB-1"],
            }]
        }
        a = build_intents(
            {"anchors": semantic_to_anchors(functional, blocks, {"capabilities": []})},
            "init", "INT", 8,
        )["intents"][0]
        b = build_intents(
            {"anchors": semantic_to_anchors(governance, blocks, {"capabilities": []})},
            "init", "INT", 8,
        )["intents"][0]
        self.assertEqual("INT-0001", a["id"])
        self.assertEqual("INT-0001", b["id"])
        self.assertEqual("gameplay", a["owner"])
        self.assertEqual("architecture", b["owner"])
        self.assertNotEqual(a["layer"], b["layer"])

    def test_ac04_batch_count_is_input_driven_and_oversize_blocks_are_not_truncated(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            blocks = []
            requirements = []
            for index in range(7):
                block_id = f"SB-{index}"
                text = f"Requirement {index} " + ("x" * 1600)
                blocks.append({
                    "block_id": block_id,
                    "source_path": "docs/gdd/game.md",
                    "raw_text": text,
                })
                requirements.append({
                    "requirement_id": f"RQ-{index}",
                    "statement": text,
                    "status": "active",
                    "delivery_relevant": True,
                    "source_block_ids": [block_id],
                })
            result = _write_model_batches(
                out,
                ledger={"blocks": blocks},
                semantics={"requirements": requirements},
                char_budget=1000,
            )
            self.assertEqual(7, result["batch_count"])
            self.assertNotEqual(6, result["batch_count"])
            accounted = {
                block_id
                for row in result["batches"]
                for block_id in row["block_ids"]
            }
            self.assertEqual({f"SB-{index}" for index in range(7)}, accounted)
            self.assertEqual(
                accounted,
                {
                    block_id
                    for row in result["batches"]
                    for block_id in row["oversize_blocks"]
                },
            )

    def test_ac05_multi_capability_and_multi_task_mapping_remain_legal(self) -> None:
        blocks = {
            "blocks": [
                {"block_id": "SB-1", "source_path": "docs/gdd/game.md", "line_start": 1},
                {"block_id": "SB-2", "source_path": "docs/gdd/game.md", "line_start": 2},
            ]
        }
        semantics = {
            "requirements": [
                {
                    "requirement_id": "RQ-SHARED",
                    "statement": "Shared player state participates in two implementation slices.",
                    "kind": "functional",
                    "delivery_relevant": True,
                    "status": "active",
                    "source_block_ids": ["SB-1"],
                },
                {
                    "requirement_id": "RQ-GLOBAL",
                    "statement": "Global audit policy.",
                    "kind": "non_functional",
                    "delivery_relevant": True,
                    "status": "active",
                    "source_block_ids": ["SB-2"],
                    "sink_policy": "quality_gate",
                    "non_task_sinks": [{"type": "quality_gate", "id": "audit-gate"}],
                },
            ]
        }
        capabilities = {
            "capabilities": [
                {"capability_id": "CAP-A", "title": "A", "requirement_ids": ["RQ-SHARED"]},
                {"capability_id": "CAP-B", "title": "B", "requirement_ids": ["RQ-SHARED"]},
            ]
        }
        anchors = semantic_to_anchors(semantics, blocks, capabilities)
        self.assertEqual(1, len(anchors))
        self.assertEqual(["CAP-A", "CAP-B"], anchors[0]["capability_ids"])
        candidates = [
            {"id": "7", "change_action": "create", "requirement_ids": ["RQ-SHARED"], "semantic_refs": ["RQ-SHARED"]},
            {"id": "42", "change_action": "create", "requirement_ids": ["RQ-SHARED"], "semantic_refs": ["RQ-SHARED"]},
        ]
        updated, operations, conflicts = build_change_plan([], candidates, "gameplay")
        self.assertEqual([], conflicts)
        self.assertEqual({"7", "42"}, {str(row["id"]) for row in updated})
        self.assertEqual(["create", "create"], [row["action"] for row in operations])

    def test_ac07_profile_rejects_view_id_template_collision(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "docs/workflows/chapter7-profile.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "bucket_order": ["custom"],
                "fallback_bucket": "custom",
                "task_creation": {"view_id_templates": {"NG": "STATIC", "GM": "GM-{task_id:04d}"}},
                "buckets": {
                    "custom": {
                        "feature_task_ids": [7, 42],
                        "feature_families": [],
                    }
                },
            }), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "template collision"):
                load_chapter7_profile(repo_root=root)

    def test_ac12_default_public_cli_does_not_expose_historical_replay_as_normal_route(self) -> None:
        parser = build_parser()
        subparsers = next(
            action for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        )
        commands = set(subparsers.choices)
        self.assertNotIn("review-frozen-task-projection", commands)
        self.assertNotIn("reconcile-frozen-task-candidates", commands)
        self.assertIn("plan-capabilities", commands)
        self.assertIn("plan-mvg", commands)


if __name__ == "__main__":
    unittest.main()
