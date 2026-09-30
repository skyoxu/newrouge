#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PYTHON = ROOT / "scripts" / "python"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))

from _planning_skill_common import scrub_capability_answers, validate_runner_description
from plan_capabilities import build_alignment, validate_candidate


class CapabilityPlanningContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.ledger = {
            "schema_version": "newrouge.source-blocks.v1",
            "blocks": [
                {"block_id": "SB-1"},
                {"block_id": "SB-2"},
            ],
        }
        self.semantics = {
            "schema_version": "newrouge.semantic-requirements.v1",
            "requirements": [
                {"requirement_id": "RQ-1", "status": "active", "delivery_relevant": True},
                {"requirement_id": "RQ-2", "status": "active", "delivery_relevant": True},
            ],
        }
        self.analysis = "sha256:" + "1" * 64

    def candidate(self) -> dict:
        return {
            "schema_version": "newrouge.capability-candidate.v1",
            "analysis_identity_sha256": self.analysis,
            "capabilities": [
                {
                    "capability_id": "TMP-CAP-ONE",
                    "title": "One",
                    "description": "First",
                    "boundary_rationale": "Boundary",
                    "requirement_ids": ["RQ-1"],
                    "source_block_ids": ["SB-1"],
                },
                {
                    "capability_id": "TMP-CAP-TWO",
                    "title": "Two",
                    "description": "Second",
                    "boundary_rationale": "Boundary",
                    "requirement_ids": ["RQ-2"],
                    "source_block_ids": ["SB-2"],
                },
            ],
            "ungrouped_requirements": [],
            "source_accounting": [
                {"block_id": "SB-1", "disposition": "capability", "capability_ids": ["TMP-CAP-ONE"], "rationale": "x"},
                {"block_id": "SB-2", "disposition": "capability", "capability_ids": ["TMP-CAP-TWO"], "rationale": "y"},
            ],
            "questions": [],
            "generation_notes": [],
        }

    def test_candidate_requires_complete_source_accounting(self) -> None:
        value = self.candidate()
        self.assertEqual([], validate_candidate(value, self.ledger, self.semantics, self.analysis))
        value["source_accounting"].pop()
        self.assertIn(
            "source_accounting_incomplete_or_duplicate",
            validate_candidate(value, self.ledger, self.semantics, self.analysis),
        )

    def test_candidate_requires_multi_membership_rationale(self) -> None:
        value = self.candidate()
        value["capabilities"][1]["requirement_ids"].append("RQ-1")
        errors = validate_candidate(value, self.ledger, self.semantics, self.analysis)
        self.assertIn("multi_membership_rationale_missing:RQ-1", errors)
        value["multi_membership_rationales"] = {"RQ-1": "Shared responsibility is explicit."}
        self.assertNotIn(
            "multi_membership_rationale_missing:RQ-1",
            validate_candidate(value, self.ledger, self.semantics, self.analysis),
        )

    def test_existing_exact_membership_reuses_id_but_changed_membership_blocks(self) -> None:
        candidate = self.candidate()
        existing = {
            "capabilities": [
                {"capability_id": "CAP-KEEP", "title": "Old", "requirement_ids": ["RQ-1"]},
                {"capability_id": "CAP-OLD", "title": "Old2", "requirement_ids": ["RQ-X"]},
            ]
        }
        alignment = build_alignment(candidate, existing)
        by_candidate = {
            row.get("candidate_id"): row for row in alignment["decisions"]
            if row.get("candidate_id")
        }
        self.assertEqual("CAP-KEEP", by_candidate["TMP-CAP-ONE"]["stable_id"])
        self.assertFalse(by_candidate["TMP-CAP-TWO"]["resolved"])
        self.assertFalse(alignment["resolved"])

    def test_blinding_removes_prior_capability_answers(self) -> None:
        payload = {
            "requirements": [
                {
                    "requirement_id": "RQ-1",
                    "capability_ids": ["CAP-OLD"],
                    "nested": {"capability_ref": "CAP-OLD"},
                }
            ]
        }
        blinded = scrub_capability_answers(payload)
        self.assertNotIn("capability_ids", blinded["requirements"][0])
        self.assertNotIn("capability_ref", blinded["requirements"][0]["nested"])

    def test_formal_runner_rejects_read_anywhere_boundary(self) -> None:
        with self.assertRaisesRegex(ValueError, "workspace-only"):
            validate_runner_description({
                "schema_version": "newrouge.isolated-model-runner.v1",
                "filesystem_scope": "host_readable",
                "fresh_session_per_invocation": True,
                "can_read_outside_workspace": True,
                "model": "same-model",
            })
        validate_runner_description({
            "schema_version": "newrouge.isolated-model-runner.v1",
            "filesystem_scope": "workspace_only",
            "fresh_session_per_invocation": True,
            "can_read_outside_workspace": False,
            "model": "same-model",
        })


if __name__ == "__main__":
    unittest.main()
