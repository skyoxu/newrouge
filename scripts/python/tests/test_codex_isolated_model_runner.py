from __future__ import annotations
import copy
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import _codex_app_server as transport
import codex_isolated_model_runner as runner
from fixtures.codex_app_server_protocol import protocol, encoded


class CodexIsolatedRunnerTests(unittest.TestCase):
    def setUp(self):
        self.cwd = Path.cwd().resolve()
        self.rows = protocol(self.cwd)
        runner._LAST_MODEL_IDENTITY = runner._LAST_MODEL_PROVIDER = None
        runner._MODEL_IDENTITY_EVIDENCE = []

    def reject(self, rows, reason):
        with self.assertRaisesRegex(ValueError, reason):
            transport.replay(encoded(rows))

    def test_runtime_configuration_is_bound_and_provider_identity_unknown(self):
        output, proof = transport.replay(encoded(self.rows), prompt="complete input")
        self.assertEqual('{"answer":"ok"}', output)
        self.assertEqual("fixture-model", proof["model"])
        self.assertTrue(proof["runtime_identity_verified"])
        self.assertEqual("runtime_configuration", proof["model_identity_scope"])
        self.assertFalse(proof["provider_identity_verified"])
        self.assertIsNone(proof["provider_reported_model"])
        self.assertEqual("unknown", proof["provider_dispatch_count"])
        self.assertEqual(transport.digest(encoded(self.rows)), proof["protocol_sha256"])
        self.rows[6]["message"]["params"]["model"] = "requested-model"
        self.assertEqual("fixture-model", transport.replay(encoded(self.rows))[1]["model"])

    def test_stock_exec_and_assistant_text_cannot_supply_identity(self):
        for raw in (b'{"type":"thread.started","thread_id":"x"}\n', b'{"direction":"server","message":{"model":"invented"}}\n'):
            with self.assertRaises(ValueError):
                transport.replay(raw)

    def test_tool_items_and_host_requests_fail_closed(self):
        for kind in ("commandExecution", "mcpToolCall", "dynamicToolCall", "webSearch", "fileChange"):
            rows = copy.deepcopy(self.rows)
            rows[13]["message"]["params"]["item"]["type"] = kind
            self.reject(rows, "model_tools_observed")
        rows = self.rows + [{"direction":"server", "message":{"id":99,"method":"item/tool/call","params":{}}}]
        self.reject(rows, "server_tool_or_auth_request")

    def test_reroutes_and_runtime_changes_fail_closed(self):
        for method in ("model/rerouted", "thread/settings/updated", "thread/realtime/started"):
            self.reject(self.rows + [{"direction":"server", "message":{"method":method,"params":{}}}], "runtime_configuration_changed")

    def test_incomplete_failed_duplicate_and_wrong_turns_fail_closed(self):
        self.reject(self.rows[:-1], "incomplete_or_multiple_turns")
        self.reject(self.rows + [self.rows[-1]], "incomplete_or_multiple_turns")
        for field, value in (("status", "failed"), ("id", "another-turn")):
            rows = copy.deepcopy(self.rows)
            rows[-1]["message"]["params"]["turn"][field] = value
            self.reject(rows, "turn_failed_or_incomplete")

    def test_history_sandbox_and_workspace_changes_fail_closed(self):
        for field, value in (("ephemeral", False), ("turns", [{"id":"old"}]), ("cwd", str(self.cwd.parent))):
            rows = copy.deepcopy(self.rows)
            rows[7]["message"]["result"]["thread"][field] = value
            self.reject(rows, "thread_not_fresh|workspace_mismatch")
        rows = copy.deepcopy(self.rows)
        rows[7]["message"]["result"]["sandbox"]["type"] = "dangerFullAccess"
        self.reject(rows, "sandbox_not_read_only")

    def test_missing_alias_and_conflicting_runtime_identity_fail_closed(self):
        for model in (None, "default", "environment-default", ""):
            rows = copy.deepcopy(self.rows)
            rows[7]["message"]["result"]["model"] = model
            self.reject(rows, "runtime_identity_missing")
        rows = copy.deepcopy(self.rows)
        rows[7]["message"]["result"]["thread"]["model"] = "different"
        self.reject(rows, "runtime_model_conflict")

    def test_mcp_inventory_and_restrictions_cannot_be_omitted(self):
        for result in ({"data":[{"name":"server"}]}, {"data":[],"nextCursor":"more"}):
            rows = copy.deepcopy(self.rows)
            rows[9]["message"]["result"] = result
            self.reject(rows, "mcp_tools_available")
        rows = copy.deepcopy(self.rows)
        del rows[6]["message"]["params"]["config"]["features"]["shell_tool"]
        self.reject(rows, "missing_tool_restriction")

    def test_exact_input_schema_and_completed_output_are_bound(self):
        with self.assertRaisesRegex(ValueError, "input_mismatch"):
            transport.replay(encoded(self.rows), prompt="truncated")
        with self.assertRaisesRegex(ValueError, "output_schema_mismatch"):
            transport.replay(encoded(self.rows), schema={"type":"object"})
        rows = copy.deepcopy(self.rows)
        rows[-1]["message"]["params"]["turn"]["items"] = [{"type":"agentMessage","id":"answer","text":"altered"}]
        self.reject(rows, "completion_output_mismatch")

    def test_turn_overrides_and_late_items_fail_closed(self):
        rows = copy.deepcopy(self.rows)
        rows[10]["message"]["params"]["model"] = "different"
        self.reject(rows, "turn_override_or_thread_mismatch")
        self.reject(self.rows + [self.rows[13]], "late_or_wrong_turn_item")

    def test_turn_items_cannot_precede_the_turn_request(self):
        for before in ['thread/start','turn/start']:
            rows=copy.deepcopy(self.rows)
            completed=next(r for r in rows if r['message'].get('method')=='item/completed')
            rows.remove(completed)
            index=next(i for i,r in enumerate(rows) if r['direction']=='client' and r['message'].get('method')==before)
            rows.insert(index,completed)
            self.reject(rows,'notification_before_turn_request')

    def test_malformed_protocol_fails_with_value_error(self):
        for raw in (b'null\n', b'[]\n', b'{}\n', b'\xff\n'):
            with self.assertRaises(ValueError):
                transport.replay(raw)

    def test_command_has_no_auth_or_sandbox_bypass(self):
        command = transport.command("fixture")
        self.assertEqual(["app-server","--stdio"], command[-2:])
        self.assertIn("shell_tool", command)
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
        self.assertNotIn("--ignore-user-config", command)
        self.assertNotIn("--ignore-rules", command)

    def test_failed_proof_preserves_prior_output(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/"answer.json"
            target.write_text("prior", encoding="utf-8")
            with patch.object(runner,"run_app_server_request",side_effect=ValueError("missing proof")):
                with self.assertRaisesRegex(ValueError,"missing proof"):
                    runner._run_codex_request("fixture",Path(folder),prompt="complete input",output=target,schema_path=None,timeout_sec=1)
            self.assertEqual("prior", target.read_text(encoding="utf-8"))

    def test_output_publishes_atomically_and_model_drift_is_rejected(self):
        expected = '{\n  "answer": "ok"\n}\n'
        def fake(executable, **kwargs):
            return transport.replay(encoded(protocol(kwargs["cwd"],kwargs["prompt"],output=expected)))
        with tempfile.TemporaryDirectory() as folder, patch.object(runner,"run_app_server_request",side_effect=fake):
            target=Path(folder)/"answer.json"
            runner._run_codex_request("fixture",Path(folder),prompt="complete input",output=target,schema_path=None,timeout_sec=1)
            self.assertEqual(expected.encode("utf-8"),target.read_bytes())
            runner._LAST_MODEL_IDENTITY = "prior-model"
            with self.assertRaisesRegex(ValueError,"model_identity_changed"):
                runner._run_codex_request("fixture",Path(folder),prompt="complete input",output=target,schema_path=None,timeout_sec=1)

    def test_description_labels_runtime_scope(self):
        value=runner.description()
        self.assertFalse(value["provider_identity_verified"])
        self.assertEqual("runtime_configuration",value["model_identity_scope"])

    def test_optional_reasoning_description_default_bytes_and_invalid_values(self):
        name = "NEWROGUE_CODEX_REASONING_EFFORT"
        with patch.dict(os.environ, {}):
            os.environ.pop(name, None)
            default = runner.description()
            raw = (json.dumps(default, ensure_ascii=False) + "\n").encode()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), "3b63c473cc0c9333f3596eac23ef427d5d2743576eabf96a275b9bad161768e6")
            self.assertNotIn("requested_reasoning_effort", default)
            os.environ[name] = "high"
            selected = runner.description()
            self.assertEqual(selected.pop("requested_reasoning_effort"), "high")
            self.assertEqual(selected, default)
            for invalid in ("", "medium", "low", "HIGH", " high "):
                os.environ[name] = invalid
                with self.assertRaisesRegex(ValueError, "unsupported_requested_reasoning_effort"):
                    runner.description()
                with patch.object(runner, "run_app_server_request", side_effect=AssertionError("No execution")):
                    with self.assertRaisesRegex(ValueError, "unsupported_requested_reasoning_effort"):
                        runner.run(None)

    def test_reasoning_replay_uses_captured_config_and_preserves_historical_bytes(self):
        name = "NEWROGUE_CODEX_REASONING_EFFORT"
        old_raw = encoded(self.rows)
        old_output, old_proof = transport.replay(old_raw)
        baseline = json.dumps(old_proof, separators=(",", ":"))
        selected = copy.deepcopy(self.rows)
        selected[6]["message"]["params"]["config"]["model_reasoning_effort"] = "low"
        selected[7]["message"]["result"]["reasoningEffort"] = "low"
        for environment in ("high", "unrelated-invalid-value"):
            with patch.dict(os.environ, {name: environment}):
                output, historical = transport.replay(old_raw)
                self.assertEqual(output, old_output)
                self.assertEqual(json.dumps(historical, separators=(",", ":")), baseline)
                self.assertNotIn("requested_reasoning_effort", historical)
                self.assertEqual(historical["runtime_reasoning_effort"], "high")
                output, proof = transport.replay(encoded(selected))
                self.assertEqual(output, old_output)
                self.assertEqual(proof["requested_reasoning_effort"], "low")
                self.assertEqual(proof["runtime_reasoning_effort"], "low")
        for returned in (None, "medium", "high"):
            changed = copy.deepcopy(selected)
            changed[7]["message"]["result"]["reasoningEffort"] = returned
            self.reject(changed, "requested_reasoning_effort_mismatch")
        changed = copy.deepcopy(selected)
        changed[6]["message"]["params"]["config"]["model_reasoning_effort"] = "medium"
        self.reject(changed, "unsupported_requested_reasoning_effort")
        high = copy.deepcopy(selected)
        high[6]["message"]["params"]["config"]["model_reasoning_effort"] = "high"
        high[7]["message"]["result"]["reasoningEffort"] = "high"
        self.assertEqual(transport.replay(encoded(high))[1]["requested_reasoning_effort"], "high")
        high[7]["message"]["result"]["reasoningEffort"] = "low"
        self.reject(high, "requested_reasoning_effort_mismatch")
        with self.assertRaisesRegex(ValueError, "unsupported_requested_reasoning_effort"):
            transport.thread_config(reasoning_effort="low")

    def test_high_reasoning_keeps_exact_input_schema_output_and_no_tools_checks(self):
        schema = {"type": "object"}
        rows = protocol(self.cwd, schema=schema)
        rows[6]["message"]["params"]["config"]["model_reasoning_effort"] = "high"
        rows[7]["message"]["result"]["reasoningEffort"] = "high"
        transport.replay(encoded(rows), prompt="complete input", schema=schema)
        with self.assertRaisesRegex(ValueError, "input_mismatch"):
            transport.replay(encoded(rows), prompt="changed", schema=schema)
        with self.assertRaisesRegex(ValueError, "output_schema_mismatch"):
            transport.replay(encoded(rows), schema={"type": "string"})
        changed = copy.deepcopy(rows)
        changed[-1]["message"]["params"]["turn"]["items"] = [
            {**changed[-1]["message"]["params"]["turn"]["items"][0], "text": "changed output"}]
        self.reject(changed, "completion_output_mismatch")
        changed = copy.deepcopy(rows)
        changed[6]["message"]["params"]["config"]["features"]["shell_tool"] = True
        self.reject(changed, "missing_tool_restriction")
        changed = copy.deepcopy(rows)
        changed[13]["message"]["params"]["item"]["type"] = "commandExecution"
        self.reject(changed, "model_tools_observed")

    def test_shared_execution_binds_trusted_reasoning_expectation_to_original_protocol(self):
        """Synthetic protocol replay through the complete production receipt validator."""
        from _planning_execution_binding import validate_execution
        import _b_route_codec as codec
        schema = {"type": "object"}
        for requested, returned, expected, accepted in (("high", "high", "high", True),
                (None, "high", "high", False), (None, "medium", "high", False),
                ("low", "low", "high", False), ("low", "low", "low", True), (None, "high", None, True)):
            with self.subTest(requested=requested, returned=returned, expected=expected):
                rows = protocol(self.cwd, schema=schema)
                if requested is not None:
                    rows[6]["message"]["params"]["config"]["model_reasoning_effort"] = requested
                rows[7]["message"]["result"]["reasoningEffort"] = returned
                output, proof = transport.replay(encoded(rows), prompt="complete input", schema=schema)
                receipt = {"schema_version": "newrouge.isolated-model-runner-receipt.v1",
                    "model": proof["model"], "model_provider": proof["model_provider"], "model_identity": "fixture/fixture-model",
                    "model_identity_source": transport.SOURCE, "model_identity_verified": False,
                    "runtime_identity_verified": True, "model_identity_scope": "runtime_configuration",
                    "evidence_policy": transport.POLICY, "provider_reported_model": None,
                    "provider_identity_verified": False, "provider_dispatch_count": "unknown",
                    "model_identity_evidence": [proof], "model_tools": [], "runner_invocations": 1,
                    "request_count_observable": True, "model_request_count": 1,
                    "output_chars": len(output), "workspace": self.cwd.as_posix()}
                stdout = json.dumps(receipt) + "\n"
                execution = {"status": "completed", "returncode": 0, "runner_dispatch_count": 1,
                    "stdout": stdout, "stdout_base64": base64.b64encode(stdout.encode()).decode(), "active_elapsed_seconds": 0.1}
                with patch.dict(os.environ, {"NEWROGUE_CODEX_REASONING_EFFORT": "invalid-current-environment"}):
                    if accepted:
                        validate_execution(self.cwd, execution, receipt, "fixture/fixture-model", output.encode(),
                            prompt="complete input", schema=schema, require_runtime=True, expected_reasoning_effort=expected)
                    else:
                        with self.assertRaises(codec.CodecError) as failed:
                            validate_execution(self.cwd, execution, receipt, "fixture/fixture-model", output.encode(),
                                prompt="complete input", schema=schema, require_runtime=True, expected_reasoning_effort=expected)
                        self.assertEqual(failed.exception.diagnostic.entity_id, "receipt.reasoning_effort")


if __name__ == "__main__":
    unittest.main()
