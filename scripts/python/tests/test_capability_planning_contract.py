#!/usr/bin/env python3
from __future__ import annotations

import sys
import hashlib
import unittest
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PYTHON = ROOT / "scripts" / "python"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))

from _planning_skill_common import scrub_capability_answers, validate_runner_description
from plan_capabilities import (
    CANDIDATE_PROMPT,
    REVIEW_PROMPT,
    build_alignment,
    validate_candidate,
    _finish_attempt,
    _manifest_artifact_sha,
)


class CapabilityPlanningContractTests(unittest.TestCase):
    def test_attempt_activity_is_capped_at_reserved_budget(self):
        state = {"budget": {"activity_sec": 0.0, "activity_reserved_sec": 30.0,
                             "candidate_reserved_sec": {"candidate-1": 30.0},
                             "candidate_activity_sec": {}}}
        row = {"reserved_active_sec": 30.0, "candidate": "candidate-1",
               "reserved_requests": 0}
        _finish_attempt(state, row, elapsed_sec=30000.0, receipt={})
        self.assertEqual(30.0, state["budget"]["activity_sec"])
        self.assertEqual(30.0, row["elapsed_active_sec"])

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

    def test_generation_policy_is_project_neutral_and_mvg_oriented(self) -> None:
        self.assertIn("Do not optimize for a fixed Capability count", CANDIDATE_PROMPT)
        self.assertIn("user-visible outcomes", CANDIDATE_PROMPT)
        self.assertIn("end-to-end journey handoffs", CANDIDATE_PROMPT)
        self.assertIn("never a template, authority, target shape, or ID source", CANDIDATE_PROMPT)
        self.assertIn("raw Capability count are diagnostics only", REVIEW_PROMPT)
        self.assertIn("human/MVG navigation cost", REVIEW_PROMPT)
        self.assertIn("new project whose domain and scale differ", REVIEW_PROMPT)

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
            "model_tools": [],
        })

    def test_manifest_artifact_hash_is_stable_across_crlf_checkout(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "source-blocks.v1.json"
            path.write_bytes(b'{\r\n  "blocks": []\r\n}\r\n')
            expected = "sha256:" + hashlib.sha256(
                b'{\n  "blocks": []\n}\n'
            ).hexdigest()
            self.assertEqual(expected, _manifest_artifact_sha(path))

    def test_topology_artifact_validation_is_stable_across_crlf_checkout(self) -> None:
        from _knowledge_catalog_builder import DirectorySnapshot
        from _semantic_topology import _validate_artifact_hashes
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "artifact.json"
            path.write_bytes(b'{\r\n  "blocks": []\r\n}\r\n')
            snapshot = DirectorySnapshot(root, ["artifact.json"])
            expected = hashlib.sha256(b'{\n  "blocks": []\n}\n').hexdigest()
            problems = []
            from _semantic_topology import TOPOLOGY_ARTIFACTS
            bindings = {path: expected for path in TOPOLOGY_ARTIFACTS.values()}
            bindings["artifact.json"] = expected
            snapshot.paths = tuple(list(snapshot.paths) + list(TOPOLOGY_ARTIFACTS.values()))
            snapshot._cache.update({path: b"{}" for path in TOPOLOGY_ARTIFACTS.values()})
            _validate_artifact_hashes(snapshot, {"artifacts": bindings}, problems)
            self.assertNotIn({"kind": "artifact_hash_mismatch", "path": "artifact.json"}, problems)


if __name__ == "__main__":
    unittest.main()
