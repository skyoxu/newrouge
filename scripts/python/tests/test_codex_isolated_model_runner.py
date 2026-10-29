from __future__ import annotations

import json
import sys
import unittest
import tempfile
import time
import subprocess
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PYTHON = ROOT / "scripts" / "python"
if str(PYTHON) not in sys.path:
    sys.path.insert(0, str(PYTHON))

from codex_isolated_model_runner import (
    CODEX_DISABLED_FEATURES,
    _parse_codex_json_events,
    _codex_command,
)
import codex_isolated_model_runner as runner


class CodexIsolatedRunnerTests(unittest.TestCase):
    def test_parent_wait_includes_independent_synthesis_budget(self):
        import _planning_skill_common as common
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / 'output.json'
            output.write_text('{}', encoding='utf-8')
            with patch.object(common.subprocess, 'Popen') as popen:
                popen.return_value.communicate.return_value = ('{"model":"fixture"}', '')
                popen.return_value.returncode = 0
                common.run_isolated_model(Path('runner.py'), workspace=root,
                    prompt_path=root / 'prompt.txt', output_path=output,
                    timeout_sec=2700, synthesis_timeout_sec=600)
                self.assertEqual(3330, popen.return_value.communicate.call_args.kwargs['timeout'])
                command = popen.call_args.args[0]
                self.assertEqual('600', command[command.index('--synthesis-timeout-sec') + 1])

    def test_json_events_prove_model_and_reject_tool_events(self) -> None:
        raw = "\n".join([
            json.dumps({"type": "session_configured", "model": "gpt-test", "model_provider_id": "test"}),
            json.dumps({"type": "message", "content": "ok"}),
        ])
        self.assertEqual(("gpt-test", []), _parse_codex_json_events(raw))

        tool_raw = raw + "\n" + json.dumps({
            "type": "item.started", "item": {"type": "local_shell_call", "name": "shell"}
        })
        with self.assertRaisesRegex(ValueError, "model_tools_observed"):
            _parse_codex_json_events(tool_raw)

    def test_json_events_without_session_model_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "actual_model_identity_missing"):
            _parse_codex_json_events(json.dumps({"type": "message", "content": "ok"}))

    def test_command_disables_tools_rules_and_mcp_without_selecting_model(self) -> None:
        command = _codex_command("codex", Path("C:/workspace"), Path("C:/out.txt"), None)
        self.assertIn("--json", command)
        self.assertIn("--ignore-rules", command)
        self.assertNotIn("--ephemeral", command)
        self.assertIn("mcp_servers={}", command)
        self.assertNotIn("--model", command)
        for feature in CODEX_DISABLED_FEATURES:
            self.assertIn(feature, command)

    def test_empty_stdout_never_publishes_output(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / 'result.json'
            target.write_text('old', encoding='utf-8')
            def execute(command, **kwargs):
                Path(command[command.index('--output-last-message') + 1]).write_text('{}', encoding='utf-8')
                return subprocess.CompletedProcess(command, 0, stdout='')
            with patch.object(runner.subprocess, 'run', side_effect=execute):
                with self.assertRaisesRegex(ValueError, 'actual_model_identity_missing'):
                    runner._run_codex_request('fixture', root, prompt='test', output=target,
                        schema_path=None, timeout_sec=1)
            self.assertEqual('old', target.read_text(encoding='utf-8'))

    def test_real_command_execution_event_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, 'model_tools_observed'):
            _parse_codex_json_events(json.dumps({'type': 'item.completed',
                'item': {'type': 'command_execution', 'command': 'dir'}}))

    def test_runtime_rollout_is_bound_to_thread_and_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            thread = '00000000-0000-4000-8000-000000000001'
            folder = root / 'sessions' / '2026' / '10' / '21'
            folder.mkdir(parents=True)
            path = folder / f'rollout-2026-10-21T00-00-00-{thread}.jsonl'
            events = [
                {'type': 'session_meta', 'payload': {'id': thread, 'cwd': str(root)}},
                {'type': 'turn_context', 'payload': {'model': 'gpt-test', 'cwd': str(root)}},
            ]
            path.write_text('\n'.join(map(json.dumps, events)), encoding='utf-8')
            raw = json.dumps({'type': 'thread.started', 'thread_id': thread})
            with patch.dict(runner.os.environ, {'CODEX_HOME': str(root)}):
                model, evidence = runner._runtime_model_from_rollout(raw,
                    started_at=time.time() - 1, workspace=root)
                self.assertEqual('gpt-test', model)
                self.assertEqual(thread, evidence['thread_id'])
                with self.assertRaisesRegex(ValueError, 'model_session_workspace_mismatch'):
                    runner._runtime_model_from_rollout(raw, started_at=time.time() - 1, workspace=root / 'other')

    def test_description_does_not_claim_identity_already_verified(self) -> None:
        value = runner.description()
        self.assertNotEqual('codex-cli-default', value['model'])
        self.assertNotIn('model_identity_verified', value)
        self.assertTrue(value['model_identity_required'])
        self.assertEqual('prompt_only', value['filesystem_scope'])


if __name__ == "__main__":
    unittest.main()
