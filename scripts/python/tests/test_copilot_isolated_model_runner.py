#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PYTHON = ROOT / "scripts" / "python"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))

from _planning_skill_common import validate_runner_description
from copilot_isolated_model_runner import description


class CopilotIsolatedRunnerTests(unittest.TestCase):
    def test_description_satisfies_no_tools_isolation_contract(self) -> None:
        old = os.environ.get("SC_COPILOT_MODEL")
        try:
            os.environ["SC_COPILOT_MODEL"] = "gpt-test"
            payload = description()
            validate_runner_description(payload)
            self.assertEqual("gpt-test", payload["model"])
            self.assertEqual([], payload["model_tools"])
            self.assertEqual("workspace_only", payload["filesystem_scope"])
            self.assertFalse(payload["supports_batched_session"])
        finally:
            if old is None:
                os.environ.pop("SC_COPILOT_MODEL", None)
            else:
                os.environ["SC_COPILOT_MODEL"] = old


if __name__ == "__main__":
    unittest.main()
