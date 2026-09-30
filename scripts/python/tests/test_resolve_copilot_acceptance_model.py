#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PYTHON = ROOT / "scripts" / "python"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))

from resolve_copilot_acceptance_model import resolve_model


class ResolveCopilotAcceptanceModelTests(unittest.TestCase):
    def test_first_available_model_is_locked(self) -> None:
        calls = []
        def probe(executable: str, model: str):
            calls.append(model)
            return (model == "model-b", f"probe:{model}")
        result = resolve_model(
            ["model-a", "model-b", "model-c"],
            env={"GITHUB_TOKEN": "test"},
            executable="copilot",
            probe=probe,
        )
        self.assertEqual("model-b", result["model"])
        self.assertEqual(["model-a", "model-b"], calls)
        self.assertEqual([False, True], [row["available"] for row in result["attempts"]])

    def test_resolution_fails_closed_when_none_available(self) -> None:
        def probe(_executable: str, model: str):
            return False, f"not available:{model}"
        with self.assertRaisesRegex(ValueError, "no fixed Copilot model"):
            resolve_model(
                ["a", "b"],
                env={"COPILOT_GITHUB_TOKEN": "test"},
                executable="copilot",
                probe=probe,
            )

    def test_resolution_requires_token(self) -> None:
        with self.assertRaisesRegex(ValueError, "GITHUB_TOKEN"):
            resolve_model(
                ["a"],
                env={},
                executable="copilot",
                probe=lambda _exe, _model: (True, "OK"),
            )


if __name__ == "__main__":
    unittest.main()
