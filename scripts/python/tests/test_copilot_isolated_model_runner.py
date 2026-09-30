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
from copilot_isolated_model_runner import description, parse_copilot_json_stream


class CopilotIsolatedRunnerTests(unittest.TestCase):
    def test_parse_json_stream_returns_response_and_actual_model(self) -> None:
        raw = "\n".join([
            '{"type":"assistant.message","data":{"content":"{\\\"ok\\\": true}","toolRequests":[],"phase":"response"}}',
            '{"type":"session.usage_checkpoint","data":{"lastActiveModel":"mai-code-1.1-flash","modelCacheState":[]}}',
        ])
        content, model = parse_copilot_json_stream(raw)
        self.assertEqual('{"ok": true}', content)
        self.assertEqual("mai-code-1.1-flash", model)

    def test_parse_json_stream_rejects_tool_request(self) -> None:
        raw = "\n".join([
            '{"type":"assistant.message","data":{"content":"x","toolRequests":[{"name":"bash"}]}}',
            '{"type":"session.usage_checkpoint","data":{"lastActiveModel":"m"}}',
        ])
        with self.assertRaisesRegex(ValueError, "forbids model tool requests"):
            parse_copilot_json_stream(raw)

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

    def test_description_defaults_to_auto_model_contract(self) -> None:
        old = os.environ.pop("SC_COPILOT_MODEL", None)
        old2 = os.environ.pop("COPILOT_MODEL", None)
        try:
            payload = description()
            validate_runner_description(payload)
            self.assertEqual("auto", payload["model"])
        finally:
            if old is not None:
                os.environ["SC_COPILOT_MODEL"] = old
            if old2 is not None:
                os.environ["COPILOT_MODEL"] = old2


if __name__ == "__main__":
    unittest.main()
