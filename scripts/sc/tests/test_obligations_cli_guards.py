#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "sc" / "llm_extract_task_obligations.py"


class ObligationsCliGuardTests(unittest.TestCase):
    def test_requires_task_id_in_ci(self) -> None:
        env = dict(os.environ)
        env["CI"] = "1"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=str(REPO_ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        self.assertEqual(2, proc.returncode)
        self.assertIn("task_id_required_in_ci", proc.stdout or "")

    def test_dry_run_fingerprint_exits_without_llm(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--task-id", "2", "--garbled-gate", "off", "--explain-reuse-miss", "--dry-run-fingerprint"],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        self.assertEqual(0, proc.returncode)
        self.assertIn("SC_LLM_OBLIGATIONS_FINGERPRINT status=ok", proc.stdout or "")
        self.assertIn("input_hash=", proc.stdout or "")
        self.assertIn("reuse_lookup_key=", proc.stdout or "")


if __name__ == "__main__":
    unittest.main()
