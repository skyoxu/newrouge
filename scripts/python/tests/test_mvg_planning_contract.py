#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PYTHON = ROOT / "scripts" / "python"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))

from plan_mvg import build_delta, validate_proposal
from update_mvg_baseline import apply_delta


class MvgPlanningContractTests(unittest.TestCase):
    def _root(self, folder: str) -> Path:
        root = Path(folder)
        tasks = root / ".taskmaster/tasks"
        tasks.mkdir(parents=True)
        (tasks / "tasks.json").write_text(json.dumps({"master": {"tasks": [
            {"id": 1, "status": "done"}, {"id": 2, "status": "done"}
        ]}}), encoding="utf-8")
        (root / "docs/gdd").mkdir(parents=True)
        (root / "docs/gdd/spec.md").write_text("spec\n", encoding="utf-8")
        (root / "docs/contracts").mkdir(parents=True)
        (root / "docs/contracts/handoff.md").write_text("contract\n", encoding="utf-8")
        (root / "docs/planning/semantic-topology").mkdir(parents=True)
        (root / "docs/planning/semantic-topology/capabilities.v1.json").write_text(json.dumps({
            "schema_version": "newrouge.capabilities.v1",
            "capabilities": [{"capability_id": "CAP-A", "title": "A", "requirement_ids": ["RQ-1"]}]
        }), encoding="utf-8")
        (root / "logs/ci/task-generation").mkdir(parents=True)
        (root / "logs/ci/task-generation/semantic-requirements.v1.json").write_text(json.dumps({
            "schema_version": "newrouge.semantic-requirements.v1",
            "requirements": [{"requirement_id": "RQ-1"}]
        }), encoding="utf-8")
        return root

    def manifest(self) -> dict:
        return {
            "schema_version": "newrouge.mvg-integration.v1",
            "mvg_id": "fixture",
            "coverage": {
                "mode": "pilot",
                "scope_id": "fixture",
                "required_flow_ids": ["flow-a"],
                "blocking_task_ids": [],
                "excluded_claims": ["manual experience"],
            },
            "flows": [{
                "id": "flow-a",
                "outcome": "result",
                "task_ids": [1, 2],
                "source_paths": ["docs/gdd/spec.md"],
                "handoffs": [{
                    "producer_task": 1,
                    "consumer_task": 2,
                    "owner_task": 1,
                    "contract_ref": "docs/contracts/handoff.md",
                    "behavior": "handoff",
                    "test_ids": ["test-a"],
                }],
                "test_ids": ["test-a"],
                "requirement_ids": ["RQ-1"],
                "capability_refs": ["CAP-A"],
            }],
            "tests": [{
                "id": "test-a",
                "kind": "dotnet",
                "state": "planned",
                "path": "Game.Core.Tests/Tasks/FixtureTests.cs",
                "selector": "Fixture.Tests",
                "evidence_level": "domain-integration",
                "min_tests": 1,
            }],
        }

    def test_proposal_rejects_unknown_capability(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = self._root(folder)
            state = {
                "analysis_identity_sha256": "sha256:x",
                "capabilities_path": "docs/planning/semantic-topology/capabilities.v1.json",
            }
            manifest = self.manifest()
            manifest["flows"][0]["capability_refs"] = ["CAP-MISSING"]
            proposal = {
                "schema_version": "newrouge.mvg-planning-proposal.v1",
                "analysis_identity_sha256": "sha256:x",
                "manifest_candidate": manifest,
                "entrypoints": [],
            }
            result = validate_proposal(root, state, proposal)
            self.assertIn("unknown_capability_ref:CAP-MISSING", result["errors"])

    def test_delta_preserves_unchanged_rows(self) -> None:
        existing = self.manifest()
        proposal = {
            "manifest_candidate": self.manifest(),
            "change_reviews": [],
            "retirement_reviews": [],
            "coverage_review": {},
        }
        delta = build_delta(existing, proposal)
        self.assertEqual("retain", delta["flow_operations"][0]["action"])
        self.assertEqual("retain", delta["test_operations"][0]["action"])

    def test_delta_retirement_without_review_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = self._root(folder)
            existing = self.manifest()
            desired = self.manifest()
            desired["flows"] = []
            desired["coverage"]["required_flow_ids"] = []
            proposal = {
                "manifest_candidate": desired,
                "change_reviews": [],
                "retirement_reviews": [],
                "coverage_review": {},
            }
            delta = build_delta(existing, proposal)
            with self.assertRaisesRegex(ValueError, "authority_ref"):
                apply_delta(existing, delta, root=root)


if __name__ == "__main__":
    unittest.main()
