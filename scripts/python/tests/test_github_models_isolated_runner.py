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
from github_models_isolated_runner import description
from openai_isolated_model_runner import workspace_payload


class GitHubModelsIsolatedRunnerTests(unittest.TestCase):
    def test_description_satisfies_isolation_contract(self) -> None:
        old = os.environ.get("SC_GITHUB_MODEL")
        try:
            os.environ["SC_GITHUB_MODEL"] = "openai/gpt-test"
            payload = description()
            validate_runner_description(payload)
            self.assertEqual("openai/gpt-test", payload["model"])
            self.assertEqual([], payload["model_tools"])
            self.assertEqual("workspace_only", payload["filesystem_scope"])
        finally:
            if old is None:
                os.environ.pop("SC_GITHUB_MODEL", None)
            else:
                os.environ["SC_GITHUB_MODEL"] = old

    def test_workspace_payload_is_still_workspace_scoped(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            prompt = root / "prompt.txt"
            prompt.write_text("Return JSON only.", encoding="utf-8")
            (root / "analysis-input").mkdir()
            (root / "analysis-input/a.json").write_text('{"a":1}\n', encoding="utf-8")
            payload = workspace_payload(
                root,
                prompt_path=prompt,
                output_path=root / "out.json",
            )
            self.assertIn("analysis-input/a.json", payload)
            self.assertNotIn(str(root.parent), payload)


if __name__ == "__main__":
    unittest.main()
