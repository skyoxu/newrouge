#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PYTHON = ROOT / "scripts" / "python"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))

from _chapter7_profile import bucket_names, load_chapter7_profile
from normalize_task_intents import build_intents
from update_mvg_baseline import _canonical_sha, apply_delta


class WorkflowPortabilityTests(unittest.TestCase):
    def test_chapter7_profile_does_not_inherit_business_task_ids(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            generic = load_chapter7_profile(repo_root=root)
            self.assertEqual(["unclassified"], bucket_names(generic))
            generic_ids = {
                task_id
                for config in generic["buckets"].values()
                for task_id in config.get("feature_task_ids", []) + config.get("closure_task_ids", [])
            }
            self.assertEqual(set(), generic_ids)

            path = root / "docs/workflows/chapter7-profile.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "bucket_order": ["custom"],
                "fallback_bucket": "custom",
                "buckets": {
                    "custom": {
                        "feature_task_ids": [7],
                        "feature_families": [],
                        "closure_task_ids": [70],
                        "wiring_task_id": 70,
                    }
                },
            }), encoding="utf-8")
            project = load_chapter7_profile(repo_root=root)
            self.assertEqual(["custom"], bucket_names(project))
            self.assertNotIn("unclassified", project["buckets"])
            self.assertEqual([7], project["buckets"]["custom"]["feature_task_ids"])
            self.assertNotIn(41, project["buckets"]["custom"]["closure_task_ids"])
            self.assertEqual(2, len(project["_profile_sources"]))

    def test_empty_bucket_order_does_not_truthy_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "docs/workflows/chapter7-profile.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "bucket_order": [],
                "fallback_bucket": "",
                "buckets": {},
            }), encoding="utf-8")
            profile = load_chapter7_profile(repo_root=root)
            self.assertEqual([], bucket_names(profile))
            self.assertEqual({}, profile["buckets"])

    def test_capability_regrouping_does_not_change_intent_identity(self) -> None:
        def index(capability_id: str) -> dict:
            return {"anchors": [{
                "requirement_id": "RQ-1",
                "source_path": "docs/gdd/game.md",
                "line": 10,
                "kind": "functional",
                "priority": "P1",
                "text": "Player chooses a route.",
                "refs": [],
                "heading_path": ["Route"],
                "capability_id": capability_id,
                "capability_title": f"Capability {capability_id}",
                "capability_ids": [capability_id],
                "layer_hint": "core",
                "owner_hint": "gameplay",
                "semantic": True,
            }]}
        first = build_intents(index("CAP-A"), "add", "INT", 8)
        second = build_intents(index("CAP-B"), "add", "INT", 8, previous_intents=first)
        self.assertEqual(first["intents"][0]["id"], second["intents"][0]["id"])
        self.assertEqual(first["intents"][0]["intent_key"], second["intents"][0]["intent_key"])
        self.assertEqual(["CAP-B"], second["intents"][0]["capability_refs"])

    def _mvg_fixture(self, root: Path) -> dict:
        tasks = root / ".taskmaster/tasks"
        tasks.mkdir(parents=True)
        (tasks / "tasks.json").write_text(json.dumps({"master": {"tasks": [
            {"id": 1, "status": "done"},
            {"id": 2, "status": "done"},
        ]}}), encoding="utf-8")
        (root / "docs/gdd").mkdir(parents=True)
        (root / "docs/gdd/spec.md").write_text("MVG specification\n", encoding="utf-8")
        (root / "docs/contracts").mkdir(parents=True)
        (root / "docs/contracts/handoff.md").write_text("handoff\n", encoding="utf-8")
        return {
            "schema_version": "newrouge.mvg-integration.v1",
            "mvg_id": "fixture",
            "coverage": {
                "mode": "pilot",
                "scope_id": "fixture",
                "required_flow_ids": ["flow-a"],
                "blocking_task_ids": [],
                "excluded_claims": ["human experience"],
            },
            "flows": [{
                "id": "flow-a",
                "outcome": "Observable result",
                "task_ids": [1, 2],
                "source_paths": ["docs/gdd/spec.md"],
                "handoffs": [{
                    "producer_task": 1,
                    "consumer_task": 2,
                    "owner_task": 1,
                    "contract_ref": "docs/contracts/handoff.md",
                    "behavior": "Transfer state",
                    "test_ids": ["test-a"],
                }],
                "test_ids": ["test-a"],
            }],
            "tests": [{
                "id": "test-a",
                "kind": "dotnet",
                "state": "planned",
                "path": "Game.Core.Tests/Tasks/FixtureTests.cs",
                "selector": "Fixture.Tests",
                "evidence_level": "domain-integration",
                "min_tests": 2,
            }],
        }

    def test_mvg_delta_rejects_id_rewrite_duplicate_and_unreviewed_weakening(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            manifest = self._mvg_fixture(root)
            base = {
                "schema_version": "newrouge.mvg-baseline-delta.v1",
                "expected_manifest_sha256": _canonical_sha(manifest),
                "flow_operations": [],
                "test_operations": [],
            }
            rewrite = deepcopy(base)
            rewrite["flow_operations"] = [{
                "id": "flow-a",
                "action": "update",
                "reason": "rewrite",
                "field_updates": {"id": "flow-b"},
            }]
            with self.assertRaisesRegex(ValueError, "cannot rewrite id"):
                apply_delta(manifest, rewrite, root=root)

            duplicate = deepcopy(base)
            duplicate["flow_operations"] = [
                {"id": "flow-a", "action": "retain", "reason": "one"},
                {"id": "flow-a", "action": "retain", "reason": "two"},
            ]
            with self.assertRaisesRegex(ValueError, "duplicate or conflicting"):
                apply_delta(manifest, duplicate, root=root)

            weaken = deepcopy(base)
            weaken["test_operations"] = [{
                "id": "test-a",
                "action": "update",
                "reason": "reduce obligation",
                "field_updates": {"min_tests": 1},
                "authority_ref": "docs/gdd/spec.md",
            }]
            with self.assertRaisesRegex(ValueError, "authority_review"):
                apply_delta(manifest, weaken, root=root)

            weaken["test_operations"][0]["authority_review"] = {
                "status": "reviewed",
                "rationale": "The reviewed specification reduces the required cases.",
            }
            updated = apply_delta(manifest, weaken, root=root, validate_final=True)
            self.assertEqual(1, updated["tests"][0]["min_tests"])


if __name__ == "__main__":
    unittest.main()
