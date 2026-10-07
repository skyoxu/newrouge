#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SC_DIR = REPO_ROOT / "scripts" / "sc"
sys.path.insert(0, str(SC_DIR))

from _repo_targets import resolve_acceptance_checklist, resolve_build_target, resolve_solution_file  # noqa: E402


class RepoTargetsAndRunDotnetTests(unittest.TestCase):
    def test_should_resolve_repo_targets_for_template_repo(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "Game.sln").touch()
            (root / "GodotGame.csproj").touch()
            expected_checklist = root / "docs/architecture/overlays/PRD-TEMPLATE/08/ACCEPTANCE_CHECKLIST.md"
            expected_checklist.parent.mkdir(parents=True)
            expected_checklist.touch()
            self.assertEqual(root / "Game.sln", resolve_solution_file(root))
            self.assertEqual(root / "GodotGame.csproj", resolve_build_target(root))
            self.assertEqual(expected_checklist, resolve_acceptance_checklist(root))
            (root / "NewRouge.sln").touch()
            self.assertEqual(root / "NewRouge.sln", resolve_solution_file(root))

    def test_run_dotnet_help_should_expose_filter_argument(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "python" / "run_dotnet.py"), "--help"],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="ignore",
        )
        self.assertEqual(0, proc.returncode)
        self.assertIn("--filter", proc.stdout or "")


if __name__ == "__main__":
    unittest.main()
