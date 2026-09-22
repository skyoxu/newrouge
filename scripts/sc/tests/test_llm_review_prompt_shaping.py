#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SC_DIR = REPO_ROOT / "scripts" / "sc"
if str(SC_DIR) not in sys.path:
    sys.path.insert(0, str(SC_DIR))

from _llm_review_acceptance import build_acceptance_semantic_context  # noqa: E402
from _llm_review_engine import _REVIEW_LENSES_PROMPT, _build_agent_execution_plan, _fit_prompt_context, _prompt_shape_for_agent  # noqa: E402
from _llm_review_prompting import build_task_context, default_agent_prompt, derive_surface_focus, parse_review_contract, render_surface_focus_prompt  # noqa: E402
from _taskmaster import TaskmasterTriplet  # noqa: E402


def _triplet() -> TaskmasterTriplet:
    return TaskmasterTriplet(
        task_id="56",
        master={
            "id": "56",
            "title": "Task 56",
            "description": "A" * 1200,
            "details": "B" * 2400,
            "adrRefs": ["ADR-0032"],
            "archRefs": ["docs/architecture/overlays/PRD-X/08/_index.md"],
        },
        back={
            "taskmaster_id": "56",
            "description": "C" * 900,
            "details": "D" * 1400,
            "acceptance": [
                "Load must succeed and preserve audit semantics. Refs: Game.Core.Tests/Tasks/Task1EnvironmentEvidencePersistenceTests.cs",
            ],
            "overlay_refs": ["docs/architecture/overlays/PRD-X/08/_index.md"],
        },
        gameplay={
            "taskmaster_id": "56",
            "description": "E" * 900,
            "details": "F" * 1400,
            "acceptance": [
                "Godot adapter must route denied writes to audit log. Refs: Tests.Godot/tests/Security/Hard/test_db_open_denied_writes_audit_log.gd",
            ],
            "overlay_refs": ["docs/architecture/overlays/PRD-X/08/_index.md"],
        },
        tasks_json_path="examples/taskmaster/tasks.json",
        tasks_back_path="examples/taskmaster/tasks_back.json",
        tasks_gameplay_path="examples/taskmaster/tasks_gameplay.json",
        taskdoc_path=None,
    )


class LlmReviewPromptShapingTests(unittest.TestCase):
    def test_build_task_context_compact_should_be_shorter_than_full(self) -> None:
        triplet = _triplet()
        full = build_task_context(triplet, mode="full")
        compact = build_task_context(triplet, mode="compact")
        semantic = build_task_context(triplet, mode="semantic")
        self.assertIn("- mode: compact", compact)
        self.assertIn("- title: Task 56", compact)
        self.assertLess(len(compact), len(semantic))
        self.assertLess(len(semantic), len(full))

    def test_build_acceptance_semantic_context_compact_should_preserve_refs(self) -> None:
        triplet = _triplet()
        full_text, full_meta = build_acceptance_semantic_context(triplet, profile="full")
        compact_text, compact_meta = build_acceptance_semantic_context(triplet, profile="compact")
        self.assertEqual("compact", compact_meta.get("profile"))
        self.assertIn("Game.Core.Tests/Tasks/Task1EnvironmentEvidencePersistenceTests.cs", compact_text)
        self.assertIn("Tests.Godot/tests/Security/Hard/test_db_open_denied_writes_audit_log.gd", compact_text)
        self.assertLess(len(compact_text), len(full_text))
        self.assertEqual(2, int(full_meta.get("included_ref_files") or 0))

    def test_prompt_shape_should_give_required_semantics_to_single_reviewer(self) -> None:
        normal = _prompt_shape_for_agent(
            "code-reviewer",
            delivery_profile="fast-ship",
            resolved_agents=["code-reviewer"],
            semantic_gate="warn",
        )
        self.assertEqual("compact", normal["task_context_mode"])
        self.assertEqual("compact", normal["acceptance_semantic_profile"])
        self.assertEqual("before_acceptance_semantic", normal["diff_position"])

    def test_execution_plan_should_not_defer_semantics_to_a_persona(self) -> None:
        execution_plan = _build_agent_execution_plan(["code-reviewer"])
        self.assertFalse(bool(execution_plan["semantic_deferred"]))
        self.assertEqual(["code-reviewer"], execution_plan["primary_llm_agents"])
        self.assertEqual(["Spec Compliance", "Edge Case", "Verification Gap"], execution_plan["review_lenses"])

    def test_surface_focus_should_select_only_relevant_changed_surfaces(self) -> None:
        focus = derive_surface_focus(
            [
                "Game.Core/Contracts/Events/RewardOfferPresentedEvent.cs",
                "Game.Godot/UI/Reward/RewardScene.cs",
                "Game.Core/Run/RunStateTransition.cs",
                "docs/workflows/run-protocol.md",
            ]
        )
        names = [item["name"] for item in focus]
        self.assertEqual(["Contract/EventBus", "UI/Scene", "State Machine"], names)
        prompt = render_surface_focus_prompt(focus)
        self.assertIn("methods, not extra reviewer personas", prompt)
        self.assertIn("Contract/EventBus", prompt)
        self.assertIn("UI/Scene", prompt)

    def test_surface_focus_should_not_invent_focus_for_unrelated_docs(self) -> None:
        focus = derive_surface_focus(["docs/workflows/run-protocol.md", "README.md"])
        self.assertEqual([], focus)
        self.assertEqual("", render_surface_focus_prompt(focus))

    def test_review_contract_should_apply_active_fix_through_to_defer(self) -> None:
        payload = {
            "completion_status": "completed",
            "lenses": [
                {"name": "Spec Compliance", "status": "completed", "notes": "checked"},
                {"name": "Edge Case", "status": "completed", "notes": "checked"},
                {"name": "Verification Gap", "status": "completed", "notes": "checked"},
            ],
            "findings": [
                {
                    "finding_id": "F-P2",
                    "claim": "P2 finding",
                    "severity": "P2",
                    "authority_refs": ["ACC:T56.1"],
                    "evidence": ["Game.Core.Tests/Tasks/Task1EnvironmentEvidencePersistenceTests.cs"],
                    "failure_scenario": "Behavior regresses.",
                    "expected_protection": "Bound regression test fails.",
                    "observed_protection": "Current regression test exists.",
                    "required_action": "Fix or defer only when below active threshold.",
                    "verification": "Run the bound regression test.",
                    "disposition": {"action": "defer", "rationale": "Allowed only below the active threshold."},
                }
            ],
            "uncertainty": [],
        }
        text = "Review Contract JSON:\n" + __import__("json").dumps(payload)

        _parsed, p1_errors = parse_review_contract(text, fix_through="P1")
        self.assertNotIn("findings[0]_must_fix_cannot_defer", p1_errors)

        _parsed, p2_errors = parse_review_contract(text, fix_through="P2")
        self.assertIn("findings[0]_must_fix_cannot_defer", p2_errors)

    def test_review_contract_should_reject_missing_required_lens(self) -> None:
        payload = {
            "completion_status": "completed",
            "lenses": [
                {"name": "Spec Compliance", "status": "completed", "notes": "checked"},
                {"name": "Edge Case", "status": "completed", "notes": "checked"},
            ],
            "findings": [],
            "uncertainty": [],
        }
        text = "Review Contract JSON:\n" + __import__("json").dumps(payload)

        parsed, errors = parse_review_contract(text, fix_through="P1")

        self.assertIsNotNone(parsed)
        self.assertIn("required_lens_missing:Verification Gap", errors)

    def test_review_contract_should_reject_invalid_machine_output(self) -> None:
        parsed, errors = parse_review_contract(
            "Verdict: OK\nReview Contract JSON:\n{not-valid-json",
            fix_through="P1",
        )

        self.assertIsNone(parsed)
        self.assertTrue(any(item.startswith("review_contract_json_invalid:") for item in errors))

    def test_default_single_reviewer_prompt_should_allow_p4_findings(self) -> None:
        prompt = default_agent_prompt("code-reviewer")
        self.assertIn("P0/P1/P2/P3/P4", prompt)

    def test_required_review_prompt_should_request_machine_readable_completion_contract(self) -> None:
        self.assertIn("Review Contract JSON:", _REVIEW_LENSES_PROMPT)
        self.assertIn("completion_status", _REVIEW_LENSES_PROMPT)
        self.assertIn("Spec Compliance", _REVIEW_LENSES_PROMPT)
        self.assertIn("Edge Case", _REVIEW_LENSES_PROMPT)
        self.assertIn("Verification Gap", _REVIEW_LENSES_PROMPT)
        self.assertIn("expected_protection", _REVIEW_LENSES_PROMPT)
        self.assertIn("observed_protection", _REVIEW_LENSES_PROMPT)

    def test_fit_prompt_context_should_fallback_to_summary_diff_before_budget_truncation(self) -> None:
        prompt, meta = _fit_prompt_context(
            blocks=["Role: code-reviewer", "Task Context:\n- title: Task 56"],
            diff_ctx="## Diff\n" + ("x" * 5000),
            diff_ctx_summary="## Diff Summary\nshort",
            acceptance_semantic_ctx="## Acceptance Semantics\n" + ("y" * 320),
            diff_position="before_acceptance_semantic",
            max_chars=1000,
            allow_drop_acceptance_semantic=True,
        )

        self.assertEqual("summary", meta["diff_mode_used"])
        self.assertIn("summary_diff", meta["fallbacks_applied"])
        self.assertTrue(meta["acceptance_semantic_included"])
        self.assertLess(len(prompt), 1000)

    def test_fit_prompt_context_should_not_drop_required_acceptance_semantic(self) -> None:
        prompt, meta = _fit_prompt_context(
            blocks=["Role: code-reviewer", "Task Context:\n- title: Task 56"],
            diff_ctx="## Diff\n" + ("x" * 800),
            diff_ctx_summary="## Diff Summary\n" + ("x" * 600),
            acceptance_semantic_ctx="## Acceptance Semantics\n" + ("y" * 1200),
            diff_position="before_acceptance_semantic",
            max_chars=700,
            allow_drop_acceptance_semantic=False,
        )
        self.assertNotIn("drop_acceptance_semantic", meta["fallbacks_applied"])
        self.assertTrue(meta["acceptance_semantic_included"])
        self.assertIn("## Acceptance Semantics", prompt)


if __name__ == "__main__":
    unittest.main()
