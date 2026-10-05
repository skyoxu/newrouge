"""Tests for retaining the incumbent Capability version during review."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import plan_capabilities as cap
from _planning_skill_common import atomic_json, load_json
from planning_acceptance_fixture import build_fixture


def _state(*, incumbent: bool) -> dict:
    state = {
        "analysis_identity_sha256": "sha256:analysis",
        "run_id": "review-fixture",
        "candidate_attempts": {
            f"candidate-{index}": {
                "final_meta": {"validation_errors": []},
            }
            for index in (1, 2, 3)
        },
    }
    if incumbent:
        state.update(
            incumbent_present=True,
            incumbent_path="incumbent/current-capabilities.v1.json",
            incumbent_sha256="sha256:incumbent",
        )
    return state


class CapabilityIncumbentReviewTests(unittest.TestCase):
    def test_prepare_freezes_valid_incumbent_without_exposing_it_to_analysis_input(self):
        with self.subTest("prepare"):
            import tempfile

            with tempfile.TemporaryDirectory() as folder:
                root = Path(folder) / "harbor"
                build_fixture(root)
                ledger = load_json(root / "logs/ci/task-generation/source-blocks.v1.json")
                semantics = load_json(root / "logs/ci/task-generation/semantic-requirements.v1.json")
                atomic_json(root / cap.FORMAL_CAPABILITIES, {
                    "schema_version": "newrouge.capabilities.v1",
                    "capabilities": [{
                        "capability_id": "CAP-CURRENT",
                        "title": "Current baseline",
                        "description": "Current published grouping.",
                        "requirement_ids": [row["requirement_id"] for row in semantics["requirements"]],
                        "boundary_rationale": "Current published boundary.",
                        "source_block_ids": [row["block_id"] for row in ledger["blocks"]],
                    }],
                })
                state = cap.prepare(
                    root, run_id="incumbent", task_ids=["7", "42"], allow_unready=False,
                    source_manifest=root / "logs/ci/task-generation/source-manifest.v1.json",
                    ledger=root / "logs/ci/task-generation/source-blocks.v1.json",
                    semantics=root / "logs/ci/task-generation/semantic-requirements.v1.json",
                    model_batch_char_budget=12000, candidate_retry_limit=1,
                    review_retry_limit=1, candidate_budget_sec=1800,
                    total_budget_sec=7200, request_limit=50,
                )
                run = root / "logs/ci/capability-planning/incumbent"
                self.assertTrue(state["incumbent_present"])
                self.assertTrue((run / "incumbent/current-capabilities.v1.json").is_file())
                self.assertTrue((run / "candidates/__incumbent__.json").is_file())
                self.assertNotIn("capabilities.v1.json", (run / "analysis-input/analysis-index.json").read_text(encoding="utf-8"))

    def test_incumbent_formal_payload_is_projected_as_a_valid_review_candidate(self):
        formal = {
            "schema_version": "newrouge.capabilities.v1",
            "capabilities": [{
                "capability_id": "CAP-OLD",
                "title": "Existing Journey",
                "description": "Current published grouping.",
                "requirement_ids": ["FR-T0001"],
                "boundary_rationale": "Existing boundary.",
                "source_block_ids": ["SB-1"],
            }],
        }
        ledger = {"blocks": [{"block_id": "SB-1"}, {"block_id": "SB-2"}]}
        semantics = {"requirements": [{
            "requirement_id": "FR-T0001", "status": "active", "delivery_relevant": True,
        }]}

        candidate = cap._build_incumbent_candidate(
            formal, ledger, semantics, "sha256:analysis"
        )

        self.assertEqual(cap.CANDIDATE_SCHEMA, candidate["schema_version"])
        self.assertEqual("sha256:analysis", candidate["analysis_identity_sha256"])
        self.assertTrue(candidate["capabilities"][0]["capability_id"].startswith("TMP-CAP-CURRENT-"))
        self.assertEqual([], candidate["ungrouped_requirements"])
        self.assertEqual({"SB-1", "SB-2"}, {row["block_id"] for row in candidate["source_accounting"]})
        self.assertEqual([], cap.validate_candidate(candidate, {"blocks": ledger["blocks"]}, semantics, "sha256:analysis"))

    def test_review_anonymization_includes_incumbent_when_present(self):
        _seed, mapping = cap._anonymous_candidates(_state(incumbent=True))

        self.assertEqual({"A", "B", "C", "D"}, set(mapping))
        self.assertEqual("__incumbent__", mapping["D"])

    def test_review_anonymization_falls_back_to_three_candidates_without_incumbent(self):
        _seed, mapping = cap._anonymous_candidates(_state(incumbent=False))

        self.assertEqual({"A", "B", "C"}, set(mapping))
        self.assertNotIn("__incumbent__", mapping.values())
        self.assertEqual(cap.REVIEW_PROMPT, cap._review_prompt(_state(incumbent=False)))

    def test_incumbent_review_uses_distinct_prompt_and_explicit_current_label(self):
        prompt = cap._review_prompt(_state(incumbent=True))

        self.assertNotEqual(cap.REVIEW_PROMPT, prompt)
        self.assertIn('"D"', prompt)
        self.assertIn("current published Capability baseline", prompt)


if __name__ == "__main__":
    unittest.main()
