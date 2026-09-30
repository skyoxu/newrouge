#!/usr/bin/env python3
from __future__ import annotations

import os
import json
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

    def test_usage_event_proves_model_without_legacy_checkpoint(self) -> None:
        raw = '\n'.join(json.dumps(event) for event in [
            {"type": "assistant.message", "data": {"content": "answer", "toolRequests": []}},
            {"type": "assistant.usage", "data": {"model": "actual-model", "outputTokens": 10}},
            {"type": "session.usage_checkpoint", "data": {"lastActiveModel": "auto"}},
        ])
        self.assertEqual(("answer", "actual-model"), parse_copilot_json_stream(raw))

    def test_shutdown_metrics_use_executed_model_and_ignore_unused_selection(self) -> None:
        raw = '\n'.join(json.dumps(event) for event in [
            {"type": "assistant.message", "data": {"content": "answer"}},
            {"type": "session.shutdown", "data": {"currentModel": "selected-model", "modelMetrics": {
                "actual-model": {"requests": {"count": 1}, "usage": {"outputTokens": 10}},
                "selected-model": {"requests": {"count": 0}, "usage": {"outputTokens": 0}},
            }}},
        ])
        self.assertEqual(("answer", "actual-model"), parse_copilot_json_stream(raw))

    def test_mixed_execution_models_are_rejected(self) -> None:
        for event_type in ("assistant.usage", "session.shutdown"):
            with self.subTest(event_type=event_type):
                events = [{"type": "assistant.message", "data": {"content": "answer"}}]
                if event_type == "assistant.usage":
                    events.extend({"type": event_type, "data": {"model": name}} for name in ("a", "b"))
                else:
                    events.append({"type": event_type, "data": {"modelMetrics": {
                        name: {"requests": {"count": 1}} for name in ("a", "b")}}})
                with self.assertRaisesRegex(ValueError, "mixed actual models"):
                    parse_copilot_json_stream('\n'.join(json.dumps(event) for event in events))

    def test_selected_model_without_execution_evidence_is_rejected(self) -> None:
        raw = '\n'.join(json.dumps(event) for event in [
            {"type": "assistant.message", "data": {"content": "answer"}},
            {"type": "session.shutdown", "data": {"currentModel": "selected-model", "modelMetrics": {}}},
        ])
        with self.assertRaisesRegex(ValueError, "did not expose the actual model identity"):
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
