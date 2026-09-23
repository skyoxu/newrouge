#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "sc" / "llm_review.py"


def _extract_out_dir(output: str) -> Path:
    m = re.search(r"\bout=([^\r\n]+)", output or "")
    if not m:
        raise AssertionError(f"missing out=... in output:\n{output}")
    return Path(m.group(1).strip())


class LlmReviewCliGuardTests(unittest.TestCase):
    def _env_without_codex(self) -> dict[str, str]:
        env = dict(os.environ)
        env["PATH"] = str(REPO_ROOT)
        env.pop("SC_LLM_BACKEND", None)
        return env

    def test_self_check_should_exit_zero(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--self-check"],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        self.assertEqual(0, proc.returncode)
        self.assertIn("SC_LLM_REVIEW_SELF_CHECK status=ok", proc.stdout or "")

    def test_self_check_should_exit_zero_without_codex_in_path(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--self-check"],
            cwd=str(REPO_ROOT),
            env=self._env_without_codex(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        self.assertEqual(0, proc.returncode, proc.stdout)
        self.assertIn("SC_LLM_REVIEW_SELF_CHECK status=ok", proc.stdout or "")

    def test_self_check_should_fail_on_conflicting_args(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--self-check", "--uncommitted", "--commit", "abc123"],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        self.assertEqual(2, proc.returncode)
        self.assertIn("mutually exclusive", proc.stdout or "")

    def test_dry_run_plan_should_emit_summary(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--dry-run-plan", "--agents", "architect-reviewer,security-auditor"],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        self.assertEqual(0, proc.returncode)
        self.assertIn("SC_LLM_REVIEW_DRY_RUN_PLAN status=ok", proc.stdout or "")
        out_dir = _extract_out_dir(proc.stdout or "")
        summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual("dry-run-plan", summary.get("mode"))
        self.assertIsInstance(summary.get("plan"), list)
        self.assertEqual(["code-reviewer"], [str(x) for x in (summary.get("agents") or [])])

    def test_dry_run_plan_should_emit_summary_without_codex_in_path(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--dry-run-plan", "--agents", "architect-reviewer,security-auditor"],
            cwd=str(REPO_ROOT),
            env=self._env_without_codex(),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        self.assertEqual(0, proc.returncode, proc.stdout)
        self.assertIn("SC_LLM_REVIEW_DRY_RUN_PLAN status=ok", proc.stdout or "")

    def test_dry_run_plan_should_relax_defaults_for_playable_ea(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--dry-run-plan", "--delivery-profile", "playable-ea"],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        self.assertEqual(0, proc.returncode, proc.stdout)
        out_dir = _extract_out_dir(proc.stdout or "")
        summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
        self.assertFalse(bool(summary.get("strict")))
        self.assertEqual("skip", ((summary.get("prompt_budget") or {}).get("gate")))
        agents = [str(x) for x in (summary.get("agents") or [])]
        self.assertEqual(["code-reviewer"], agents)

    def test_dry_run_plan_should_use_single_reviewer_for_standard(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--dry-run-plan", "--delivery-profile", "standard"],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        self.assertEqual(0, proc.returncode, proc.stdout)
        out_dir = _extract_out_dir(proc.stdout or "")
        summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
        self.assertTrue(bool(summary.get("strict")))
        self.assertEqual(["code-reviewer"], [str(x) for x in (summary.get("agents") or [])])
        self.assertEqual(
            ["Spec Compliance", "Edge Case", "Verification Gap"],
            list((summary.get("execution_plan") or {}).get("review_lenses") or []),
        )


    def test_dry_run_plan_should_collapse_explicit_legacy_model_personas_to_single_reviewer(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--dry-run-plan",
                "--agents",
                "code-reviewer,security-auditor",
                "--semantic-gate",
                "warn",
            ],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        self.assertEqual(0, proc.returncode, proc.stdout)
        out_dir = _extract_out_dir(proc.stdout or "")
        summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
        agents = [str(x) for x in (summary.get("agents") or [])]
        self.assertEqual(["code-reviewer"], agents)
        self.assertEqual(
            ["Spec Compliance", "Edge Case", "Verification Gap"],
            list((summary.get("execution_plan") or {}).get("review_lenses") or []),
        )



    def test_self_check_should_validate_timeout(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--self-check", "--timeout-sec", "0"],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        self.assertEqual(2, proc.returncode)
        self.assertIn("--timeout-sec must be > 0", proc.stdout or "")

    def test_prompt_budget_gate_require_should_fail_when_truncated(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--prompts-only",
                "--agents",
                "architect-reviewer",
                "--diff-mode",
                "none",
                "--prompt-max-chars",
                "64",
                "--prompt-budget-gate",
                "require",
            ],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        self.assertEqual(1, proc.returncode)
        self.assertIn("SC_LLM_REVIEW status=fail", proc.stdout or "")
        out_dir = _extract_out_dir(proc.stdout or "")
        summary = json.loads((out_dir / "summary.json").read_text(encoding="utf-8"))
        self.assertEqual("fail", summary.get("status"))
        pb = summary.get("prompt_budget") or {}
        self.assertEqual("require", pb.get("gate"))
        self.assertGreaterEqual(int(pb.get("truncated_count") or 0), 1)


if __name__ == "__main__":
    unittest.main()
