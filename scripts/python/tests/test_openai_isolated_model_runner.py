#!/usr/bin/env python3
from __future__ import annotations

import os
import base64
import argparse
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
PYTHON = ROOT / "scripts" / "python"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))

from _planning_skill_common import validate_runner_description
from openai_isolated_model_runner import description, workspace_payload
import openai_isolated_model_runner as runner
from _model_response_identity import response_identity


def provider_response(**overrides):
    values = dict(id="resp-test", model="gpt-actual", object="response", status="completed",
                  output=[{"type": "message", "role": "assistant", "content": [
                      {"type": "output_text", "text": "{}"}]}], output_text="{}", tools=[])
    values.update(overrides)
    return SimpleNamespace(**values)


class OpenAiIsolatedRunnerTests(unittest.TestCase):
    def invoke_response(self, root, response):
        prompt = root / "prompt.txt"
        prompt.write_text("Return JSON.", encoding="utf-8")
        args = argparse.Namespace(workspace=str(root), prompt_file=str(prompt), output=str(root / "out.json"),
            max_bytes=1024 * 1024, max_input_tokens=96000, timeout_sec=1,
            output_schema="", model_request_budget=1)
        with patch.object(runner, "inspect_llm_backend", return_value={"available": True}), \
             patch.object(runner, "_openai_client", return_value=object()), \
             patch.object(runner, "_response", return_value=response) as request, \
             contextlib.redirect_stdout(io.StringIO()) as stdout:
            runner.run(args)
        self.assertEqual(1, request.call_count)
        return json.loads(stdout.getvalue())

    def test_receipt_binds_provider_model_not_request_alias(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(runner, "model_name", return_value="requested-alias"):
            root = Path(folder)
            receipt = self.invoke_response(root, provider_response())
            self.assertEqual("gpt-actual", receipt["model"])
            self.assertEqual("gpt-actual", receipt["model_identity"])
            self.assertIs(True, receipt["model_identity_verified"])
            self.assertEqual("openai-responses-api", receipt["model_identity_source"])
            self.assertEqual("resp-test", receipt["model_identity_evidence"][0]["response_id"])
            self.assertEqual([], receipt["model_tools"])

    def test_multiline_receipt_passes_coordinator_with_exact_original_bytes(self):
        import _b_route_source_audit as audit
        text='{\n  "status": "ok"\n}'
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            receipt=self.invoke_response(root,provider_response(output_text=text,output=[{"type":"message","role":"assistant","content":[{"type":"output_text","text":text}]}]))
            raw=(root/'out.json').read_bytes()
            self.assertEqual(text.encode('utf-8'),raw)
            self.assertEqual(1,receipt['runner_invocations'])
            stdout=json.dumps(receipt)+'\n'
            execution={'status':'completed','returncode':0,'runner_dispatch_count':1,
                'stdout':stdout,'stdout_base64':base64.b64encode(stdout.encode()).decode(),
                'active_elapsed_seconds':0.1}
            audit.validate_execution(root,execution,receipt,'gpt-actual',raw)

    def test_missing_provider_identity_never_publishes_or_claims_success(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / "out.json"
            output.write_text("old", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "actual_model_identity_missing"):
                self.invoke_response(root, provider_response(model=None))
            self.assertEqual("old", output.read_text())
            integrity = json.loads((root / runner.REPORT_NAME).read_text())
            self.assertEqual("failed", integrity["status"])
            self.assertEqual(1, integrity["model_request_count"])
            self.assertEqual([], list(root.glob("*.tmp")))

    def test_tools_and_incomplete_responses_fail_before_publication(self):
        for response, error in [
            (provider_response(output=[{"type": "function_call", "name": "shell"}]), "model_tools_observed"),
            (provider_response(tools=[{"type": "web_search"}]), "model_tools_observed"),
            (provider_response(status="incomplete"), "actual_model_evidence_invalid"),
        ]:
            with self.subTest(error=error), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                with self.assertRaisesRegex(ValueError, error):
                    self.invoke_response(root, response)
                self.assertFalse((root / "out.json").exists())

    def test_response_identity_requires_real_metadata_shape(self):
        for overrides, error in [
            ({"id": None}, "actual_model_evidence_invalid"),
            ({"object": "message"}, "actual_model_evidence_invalid"),
            ({"output": None}, "actual_model_evidence_invalid"),
            ({"output": [{"type": "message", "role": "tool", "content": []}]}, "actual_model_evidence_invalid"),
            ({"output": [{"type": "message", "role": "assistant", "content": [
                {"type": "function_call"}]}]}, "model_tools_observed"),
            ({"model": "auto"}, "actual_model_identity_invalid"),
            ({"model": " actual "}, "actual_model_identity_invalid"),
        ]:
            with self.subTest(overrides=overrides), self.assertRaisesRegex(ValueError, error):
                response_identity(provider_response(**overrides), source="fixture-provider-response")

    def test_metadata_digest_binds_observed_response_and_model(self):
        model, first = response_identity(provider_response(), source="fixture-provider-response")
        _, second = response_identity(provider_response(id="resp-other"), source="fixture-provider-response")
        self.assertEqual("gpt-actual", model)
        self.assertNotEqual(first["response_metadata_sha256"], second["response_metadata_sha256"])

    def test_request_disables_tools_and_sdk_retries(self):
        client = unittest.mock.Mock()
        client.with_options.return_value.responses.create.return_value = provider_response()
        runner._response(client=client, prompt="test", previous_response_id=None, timeout_sec=1)
        sent = client.with_options.return_value.responses.create.call_args.kwargs
        self.assertEqual([], sent["tools"])
        self.assertEqual("none", sent["tool_choice"])
        self.assertEqual(0, client.with_options.call_args.kwargs["max_retries"])

    def test_single_request_preserves_provider_default_output_limit(self):
        client = unittest.mock.Mock()
        runner._response(client=client, prompt="test", previous_response_id=None,
            timeout_sec=1, max_output_tokens=None)
        self.assertNotIn("max_output_tokens", client.with_options.return_value.responses.create.call_args.kwargs)

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
