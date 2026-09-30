#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PYTHON = ROOT / "scripts" / "python"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))

from _planning_skill_common import validate_runner_description
from openai_isolated_model_runner import description, workspace_payload


class OpenAiIsolatedRunnerTests(unittest.TestCase):
    def test_description_satisfies_capability_isolation_contract(self) -> None:
        old = os.environ.get("SC_OPENAI_MODEL")
        try:
            os.environ["SC_OPENAI_MODEL"] = "gpt-test"
            payload = description()
            validate_runner_description(payload)
            self.assertEqual("gpt-test", payload["model"])
            self.assertEqual([], payload["model_tools"])
        finally:
            if old is None:
                os.environ.pop("SC_OPENAI_MODEL", None)
            else:
                os.environ["SC_OPENAI_MODEL"] = old

    def test_workspace_payload_contains_only_workspace_text_files(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prompt = root / "prompt.txt"
            prompt.write_text("Return JSON only.", encoding="utf-8")
            (root / "analysis-input").mkdir()
            (root / "analysis-input" / "a.json").write_text('{"a": 1}\n', encoding="utf-8")
            output = root / "out.json"
            text = workspace_payload(root, prompt_path=prompt, output_path=output)
            self.assertIn("analysis-input/a.json", text)
            self.assertIn('{"a": 1}', text)
            self.assertNotIn("FILE: prompt.txt", text)

    def test_workspace_payload_rejects_external_prompt(self) -> None:
        with tempfile.TemporaryDirectory() as folder, tempfile.TemporaryDirectory() as other:
            root = Path(folder)
            prompt = Path(other) / "prompt.txt"
            prompt.write_text("x", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "prompt path must be inside workspace"):
                workspace_payload(root, prompt_path=prompt, output_path=root / "out.json")


if __name__ == "__main__":
    unittest.main()
