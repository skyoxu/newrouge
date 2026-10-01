#!/usr/bin/env python3
from __future__ import annotations

import os
import json
import tempfile
import argparse
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
PYTHON = ROOT / "scripts" / "python"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))

from _planning_skill_common import validate_runner_description
from copilot_isolated_model_runner import description, parse_copilot_json_stream, runtime_model_events, run


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

    def test_private_runtime_supplies_missing_stdout_model_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            path = runtime / "session-state/fresh-session/events.jsonl"
            path.parent.mkdir(parents=True)
            events = [
                {"type": "assistant.message", "data": {"content": "Do not retain message or reasoning text."}},
                {"type": "assistant.reasoning", "data": {"content": "Do not retain reasoning."}},
                {"type": "session.shutdown", "data": {"modelMetrics": {
                    "actual-model": {"requests": {"count": 1}}}}},
            ]
            path.write_text('\n'.join(json.dumps(event) for event in events), encoding="utf-8")
            model_events, shapes = runtime_model_events(runtime)
            self.assertNotIn("Do not retain", model_events)
            self.assertEqual(3, len(shapes))
            stdout = json.dumps({"type": "assistant.message", "data": {"content": "answer"}})
            self.assertEqual(("answer", "actual-model"), parse_copilot_json_stream(stdout + '\n' + model_events))

    def test_private_runtime_never_selects_latest_of_multiple_sessions(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            runtime = Path(folder)
            for name in ("a", "b"):
                path = runtime / "session-state" / name / "events.jsonl"
                path.parent.mkdir(parents=True)
                path.write_text('', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "multiple session event logs"):
                runtime_model_events(runtime)

    def test_cached_model_without_execution_evidence_is_rejected(self) -> None:
        raw = '\n'.join(json.dumps(event) for event in [
            {"type": "assistant.message", "data": {"content": "answer"}},
            {"type": "session.usage_checkpoint", "data": {"modelCacheState": [{"modelId": "cached-model"}]}},
        ])
        with self.assertRaisesRegex(ValueError, "did not expose the actual model identity"):
            parse_copilot_json_stream(raw)

    def test_timeout_cleans_only_owned_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            workspace = Path(folder) / "workspace"
            workspace.mkdir()
            prompt = workspace / "prompt.txt"
            prompt.write_text("Return JSON only.", encoding="utf-8")
            runtime = Path(folder) / "owned-runtime"
            runtime.mkdir()
            args = argparse.Namespace(workspace=str(workspace), prompt_file=str(prompt),
                output=str(workspace / "output.json"), timeout_sec=1, max_bytes=10000)
            with patch.dict(os.environ, {"GITHUB_TOKEN": "fixture-token"}, clear=True), \
                 patch("copilot_isolated_model_runner.shutil.which", return_value="copilot"), \
                 patch("copilot_isolated_model_runner.tempfile.mkdtemp", return_value=str(runtime)), \
                 patch("copilot_isolated_model_runner.subprocess.run", side_effect=subprocess.TimeoutExpired("copilot", 1)):
                with self.assertRaises(subprocess.TimeoutExpired):
                    run(args)
            self.assertFalse(runtime.exists())
            self.assertTrue(prompt.is_file())

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
