#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PYTHON_DIR = REPO_ROOT / "scripts" / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

import milestone_incremental_handoff as handoff_mod
import update_mvg_baseline as baseline_mod


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class MilestoneIncrementalWorkflowTests(unittest.TestCase):
    def _prepare_task_and_semantics(self, root: Path) -> None:
        write_json(root / ".taskmaster/tasks/tasks_back.json", [])
        write_json(root / ".taskmaster/tasks/tasks_gameplay.json", [{
            "id": "GM-0200",
            "taskmaster_id": 200,
            "semantic_refs": ["FR-SHOP-1"],
        }])
        write_json(root / "logs/ci/task-generation/semantic-requirements.v1.json", {
            "schema_version": "newrouge.semantic-requirements.v1",
            "requirements": [{
                "requirement_id": "FR-SHOP-1",
                "status": "active",
                "delivery_relevant": True,
            }],
        })

    def test_reviewed_change_plan_requires_explicit_impact_owner_and_verification(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._prepare_task_and_semantics(root)
            plan = {
                "schema_version": handoff_mod.CHANGE_PLAN_SCHEMA,
                "source_identity": {"source_revision": "source-set:abc"},
                "changes": [{
                    "change_id": "CHG-1",
                    "action": "extend",
                    "target_task_id": "200",
                    "owner_task_id": "200",
                    "requirement_ids": ["FR-SHOP-1"],
                    "reason": "Existing reward route is extended by the new shop handoff.",
                    "impact": {
                        "tasks": ["200"],
                        "contracts": ["core.reward.offer.presented"],
                        "overlays": ["docs/architecture/overlays/PRD/08/_index.md"],
                    },
                    "verification": {
                        "required_regressions": ["reward-route"],
                        "planned_tests": ["shop-reward-route"],
                        "manual_obligations": [],
                    },
                    "baseline_delta": {"add_flow_ids": ["shop-reward-return"]},
                }],
            }
            self.assertEqual([], handoff_mod.validate_change_plan(root, plan))
            broken = json.loads(json.dumps(plan))
            broken["changes"][0]["verification"] = {}
            self.assertIn("CHG-1:missing_verification_plan", handoff_mod.validate_change_plan(root, broken))

    def test_done_task_extension_requires_change_owner_or_explicit_reopen(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_json(root / ".taskmaster/tasks/tasks_back.json", [])
            write_json(root / ".taskmaster/tasks/tasks_gameplay.json", [{
                "id": "GM-0200",
                "taskmaster_id": 200,
                "status": "done",
                "semantic_refs": ["FR-SHOP-1"],
            }, {
                "id": "GM-0201",
                "taskmaster_id": 201,
                "status": "pending",
                "semantic_refs": ["FR-SHOP-1"],
            }])
            write_json(root / "logs/ci/task-generation/semantic-requirements.v1.json", {
                "schema_version": "newrouge.semantic-requirements.v1",
                "requirements": [{"requirement_id": "FR-SHOP-1", "status": "active"}],
            })
            base = {
                "schema_version": handoff_mod.CHANGE_PLAN_SCHEMA,
                "source_identity": {"source_revision": "source-set:abc"},
                "changes": [{
                    "change_id": "CHG-DONE",
                    "action": "extend",
                    "target_task_id": "200",
                    "owner_task_id": "200",
                    "requirement_ids": ["FR-SHOP-1"],
                    "reason": "New milestone expands the old behavior.",
                    "impact": {"tasks": ["200"]},
                    "verification": {"required_regressions": ["old-regression"]},
                }],
            }
            errors = handoff_mod.validate_change_plan(root, base)
            self.assertIn("CHG-DONE:done_target_requires_change_owner_or_explicit_reopen", errors)

            linked = json.loads(json.dumps(base))
            linked["changes"][0]["owner_task_id"] = "201"
            self.assertEqual([], handoff_mod.validate_change_plan(root, linked))

            reopened = json.loads(json.dumps(base))
            reopened["changes"][0]["reopen_task"] = True
            self.assertEqual([], handoff_mod.validate_change_plan(root, reopened))

    def test_task_handoff_binds_current_chapter5_readiness_and_detects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self._prepare_task_and_semantics(root)
            plan_path = root / "logs/ci/milestone/change-plan.json"
            readiness_path = root / "logs/ci/chapter5/readiness/task-200.json"
            plan = {
                "schema_version": handoff_mod.CHANGE_PLAN_SCHEMA,
                "source_identity": {"source_revision": "source-set:abc"},
                "changes": [{
                    "change_id": "CHG-1",
                    "action": "extend",
                    "target_task_id": "200",
                    "owner_task_id": "200",
                    "requirement_ids": ["FR-SHOP-1"],
                    "reason": "Reviewed extension.",
                    "impact": {"tasks": ["200"]},
                    "verification": {"required_regressions": ["reward-route"], "planned_tests": [], "manual_obligations": []},
                }],
            }
            readiness = {
                "schema_version": "newrouge.chapter5-readiness.v1",
                "task_id": "200",
                "closure_allowed": True,
                "input_fingerprint": {"sha256": "sha256:fingerprint"},
            }
            write_json(plan_path, plan)
            write_json(readiness_path, readiness)
            handoff = handoff_mod.build_task_handoff(
                root, plan_path=plan_path, task_id="200", readiness_path=readiness_path
            )
            handoff_path = root / "logs/ci/milestone/task-200-handoff.json"
            write_json(handoff_path, handoff)
            ok, reason, payload = handoff_mod.validate_task_handoff(root, handoff_path, "200")
            self.assertTrue(ok, reason)
            self.assertEqual(["reward-route"], payload["required_regressions"])

            readiness["input_fingerprint"] = {"sha256": "sha256:changed"}
            write_json(readiness_path, readiness)
            ok, reason, _ = handoff_mod.validate_task_handoff(root, handoff_path, "200")
            self.assertFalse(ok)
            self.assertIn("stale_chapter5_readiness_path", reason)

    def test_cumulative_mvg_delta_retains_old_flows_and_requires_authority_to_retire(self) -> None:
        manifest = {
            "schema_version": "newrouge.mvg-integration.v1",
            "mvg_id": "current",
            "coverage": {"required_flow_ids": ["combat-reward"]},
            "flows": [{"id": "combat-reward", "test_ids": ["reward-route"], "handoffs": []}],
            "tests": [{"id": "reward-route", "kind": "gdunit", "state": "implemented"}],
        }
        delta = {
            "schema_version": baseline_mod.DELTA_SCHEMA,
            "expected_manifest_sha256": baseline_mod._canonical_sha(manifest),
            "change_plan_sha256": "sha256:plan",
            "flow_operations": [{
                "id": "shop-reward",
                "action": "add",
                "reason": "Second milestone adds a shop-to-reward handoff.",
                "value": {"id": "shop-reward", "test_ids": ["shop-route"], "handoffs": []},
            }],
            "test_operations": [{
                "id": "shop-route",
                "action": "add",
                "reason": "New combined route regression.",
                "value": {"id": "shop-route", "kind": "gdunit", "state": "planned"},
            }],
            "coverage_updates": {"required_flow_ids": ["combat-reward", "shop-reward"]},
        }
        updated = baseline_mod.apply_delta(manifest, delta)
        self.assertEqual({"combat-reward", "shop-reward"}, {row["id"] for row in updated["flows"]})
        self.assertEqual({"reward-route", "shop-route"}, {row["id"] for row in updated["tests"]})
        self.assertEqual("sha256:plan", updated["baseline_lineage"]["change_plan_sha256"])

        bad_retire = {
            **delta,
            "expected_manifest_sha256": baseline_mod._canonical_sha(manifest),
            "flow_operations": [{"id": "combat-reward", "action": "retire", "reason": "Remove old flow"}],
            "test_operations": [],
            "coverage_updates": {"required_flow_ids": []},
        }
        with self.assertRaisesRegex(ValueError, "authority_ref"):
            baseline_mod.apply_delta(manifest, bad_retire)


if __name__ == "__main__":
    unittest.main()
