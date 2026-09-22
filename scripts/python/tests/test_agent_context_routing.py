#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


class AgentContextRoutingContractTests(unittest.TestCase):
    def test_root_routing_is_task_scoped_and_cross_domain_composable(self) -> None:
        text = _read("AGENTS.md")
        self.assertIn("不要固定预加载一组无关文档", text)
        self.assertIn("跨领域任务取必要路由的并集", text)

        rows = {
            line.split("|")[1].strip(): line
            for line in text.splitlines()
            if line.startswith("|") and line.count("|") >= 4
        }
        for chapter in ("Chapter 3", "Chapter 4", "Chapter 5", "Chapter 7"):
            self.assertIn(chapter, rows)
            self.assertNotIn("resume-task", rows[chapter])
            self.assertNotIn("chapter6-route", rows[chapter])

        self.assertIn("Architecture/Contract", rows)
        self.assertIn("Game.Core/Contracts/**", rows["Architecture/Contract"])
        self.assertIn("Testing/MVG", rows)
        self.assertIn("docs/testing-framework.md", rows["Testing/MVG"])
        self.assertIn("Chapter 6 新任务", rows)
        self.assertIn("Task/Acceptance", rows["Chapter 6 新任务"])

    def test_recovery_is_compact_first_and_expands_events_only_when_needed(self) -> None:
        text = _read("docs/agents/01-session-recovery.md")
        self.assertIn("resume-task --task-id <id> --recommendation-only", text)
        self.assertIn("chapter6-route --task-id <id> --recommendation-only", text)
        self.assertIn(
            "read append-only events only when event ordering or turn history is needed",
            text,
        )
        self.assertIn(
            "Do not choose a plan or decision merely because it is newest in its directory",
            text,
        )

    def test_chapter6_knowledge_query_is_pre_red_and_cannot_widen_mid_tdd(self) -> None:
        text = _read(".agents/skills/workflow-chapter6-single-task-daily-loop/SKILL.md")
        self.assertIn("Chapter 6 may query bounded Knowledge only before RED", text)
        self.assertIn(
            "Do not issue another semantic Locator query during the same RED/GREEN/REFACTOR sequence",
            text,
        )
        self.assertIn(
            "stop and create a new explicit preflight/context revision instead of widening context invisibly",
            text,
        )
        self.assertIn("fallback_required", text)
        self.assertIn("continue from direct authoritative sources", text)


if __name__ == "__main__":
    unittest.main()
