#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


class PlanningProductionAcceptanceCliTests(unittest.TestCase):
    def test_requires_isolated_checkout_confirmation_before_any_model_work(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/python/run_planning_production_acceptance.py"),
                "--repo-root", str(ROOT),
                "--run-id", "test",
                "--task-id", "1",
                "--manifest", "docs/testing/mvg/test.json",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.assertEqual(2, proc.returncode)
        self.assertIn("isolated_checkout_confirmation_required", proc.stdout)


if __name__ == "__main__":
    unittest.main()
