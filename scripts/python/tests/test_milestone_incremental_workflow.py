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
            linked["changes"][0]["impact"]["tasks"] = ["200", "201"]
            self.assertEqual([], handoff_mod.validate_change_plan(root, linked))

            reopened = json.loads(json.dumps(base))
            reopened["changes"][0]["reopen_task"] = True
            self.assertEqual([], handoff_mod.validate_change_plan(root, reopened))

    def test_new_source_block_and_shared_contract_regression_cannot_be_omitted(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            write_json(root / ".taskmaster/tasks/tasks_back.json", [])
            write_json(root / ".taskmaster/tasks/tasks_gameplay.json", [
                {"id": "GM-1", "taskmaster_id": 1, "status": "done", "contractRefs": ["core.reward.claimed"]},
                {"id": "GM-2", "taskmaster_id": 2, "status": "pending", "contractRefs": ["core.reward.claimed"]},
                {"id": "GM-3", "taskmaster_id": 3, "status": "done", "contractRefs": ["core.reward.claimed"]},
            ])
            write_json(root / "logs/ci/task-generation/source-blocks.v1.json", {
                "blocks": [
                    {"block_id": "SB-SHOP", "content_hash": "sha256:shop", "block_type": "paragraph"},
                    {"block_id": "SB-SAVE", "content_hash": "sha256:save", "block_type": "paragraph"},
                    {"block_id": "SB-EXTRA", "content_hash": "sha256:extra", "block_type": "paragraph", "requirement_like_hint": True},
                ],
                "delta": {"added": ["SB-SHOP", "SB-SAVE", "SB-EXTRA"], "changed": []},
            })
            write_json(root / "logs/ci/task-generation/semantic-requirements.v1.json", {
                "requirements": [{"requirement_id": "FR-SHOP", "status": "active", "source_block_ids": ["SB-SHOP"]},
                                 {"requirement_id": "FR-SAVE", "status": "active", "source_block_ids": ["SB-SAVE"]}],
            })
            write_json(root / "docs/testing/mvg/current.json", {
                "flows": [{"id": "old-reward", "task_ids": [1], "test_ids": ["old-reward"],
                           "handoffs": [{"producer_task": 1, "consumer_task": 3,
                                         "test_ids": ["old-reward-handoff"]}]},
                          {"id": "old-save", "task_ids": [3], "test_ids": ["old-save"]}],
            })
            plan = {
                "schema_version": handoff_mod.CHANGE_PLAN_SCHEMA,
                "source_identity": {"source_revision": "source-set:shop"},
                "baseline_manifest": "docs/testing/mvg/current.json",
                "source_block_reviews": [
                    {"block_id": "SB-SHOP", "content_hash": "sha256:shop", "disposition": "requirement",
                     "requirement_ids": ["FR-SHOP"], "reason": "Reviewed shop behavior"},
                    {"block_id": "SB-SAVE", "content_hash": "sha256:save", "disposition": "requirement",
                     "requirement_ids": ["FR-SAVE"], "reason": "Reviewed save behavior"},
                    {"block_id": "SB-EXTRA", "content_hash": "sha256:extra", "disposition": "context",
                     "non_delivery_rationale": "This paragraph describes only the title format.", "reason": "Reviewed non-delivery context"},
                ],
                "changes": [{"change_id": "shop", "action": "extend", "target_task_id": "1",
                             "owner_task_id": "2", "reason": "Shared reward contract extension",
                             "requirement_ids": ["FR-SHOP", "FR-SAVE"],
                             "impact": {"tasks": [1, 2, 3], "contracts": ["core.reward.claimed"]},
                             "verification": {"required_regressions": ["old-reward", "old-save", "old-reward-handoff"],
                                              "planned_tests": ["shop-save"]}}],
            }
            self.assertEqual([], handoff_mod.validate_change_plan(root, plan))
            cases = (
                ("unreviewed_source_blocks:SB-SAVE", lambda copy: copy["source_block_reviews"].pop(1)),
                ("stale_source_block_review:SB-SAVE", lambda copy: copy["source_block_reviews"][1].update(content_hash="sha256:stale")),
                ("source_block_review_conflicts_with_requirements:SB-SAVE", lambda copy: copy["source_block_reviews"][1].update(disposition="context")),
                ("unmapped_source_block_review:SB-SAVE", lambda copy: copy["source_block_reviews"][1].update(requirement_ids=["FR-SHOP"])),
                ("unassigned_source_block_requirements:SB-SAVE", lambda copy: copy["changes"][0].update(requirement_ids=["FR-SHOP"])),
                ("requirement_like_context_needs_review:SB-EXTRA", lambda copy: copy["source_block_reviews"][-1].pop("non_delivery_rationale")),
                ("impact_missing_tasks:1", lambda copy: copy["changes"][0]["impact"].update(tasks=[2, 3])),
                ("impact_missing_shared_contracts:core.reward.claimed", lambda copy: copy["changes"][0]["impact"].update(contracts=[])),
                ("impact_missing_contract_consumers:3", lambda copy: copy["changes"][0]["impact"].update(tasks=[1, 2])),
                ("missing_old_regressions:old-save", lambda copy: copy["changes"][0]["verification"].update(required_regressions=["old-reward", "old-reward-handoff"])),
                ("missing_old_regressions:old-reward-handoff", lambda copy: copy["changes"][0]["verification"].update(required_regressions=["old-reward", "old-save"])),
            )
            for expected, mutate in cases:
                with self.subTest(expected=expected):
                    altered = json.loads(json.dumps(plan))
                    mutate(altered)
                    self.assertTrue(any(expected in error for error in handoff_mod.validate_change_plan(root, altered)))

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
