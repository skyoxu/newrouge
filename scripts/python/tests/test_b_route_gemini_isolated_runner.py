#!/usr/bin/env python3
"""Unit tests for Gemini isolated runner, stream-json protocol replay, registry, and Plane A backends."""

from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

TRACK_A_ROOT = Path(__file__).resolve().parents[3]
TRACK_A_PYTHON = TRACK_A_ROOT / "scripts" / "python"
TRACK_A_TESTS = TRACK_A_PYTHON / "tests"
REPO_ROOT = TRACK_A_ROOT
REPO_PYTHON = REPO_ROOT / "scripts" / "python"

for entry in reversed((str(TRACK_A_PYTHON), str(TRACK_A_TESTS), str(REPO_PYTHON))):
    if entry not in sys.path:
        sys.path.insert(0, entry)

import _b_route_codec as codec  # noqa: E402
import _b_route_source_audit as source_audit  # noqa: E402
import _gemini_cli_protocol as gemini_protocol  # noqa: E402
import _isolated_runner_registry as registry  # noqa: E402
import _planning_execution_binding as execution_binding  # noqa: E402
import _planning_skill_common as skill_common  # noqa: E402
import gemini_isolated_model_runner as gemini_runner  # noqa: E402
import plan_mvg  # noqa: E402

FAKE_GEMINI_CLI = TRACK_A_TESTS / "fixtures" / "b_route_fake_gemini_cli.py"
GEMINI_RUNNER_PATH = TRACK_A_PYTHON / "gemini_isolated_model_runner.py"
ROUTING_CONFIG_PATH = TRACK_A_ROOT / "docs" / "workflows" / "llm-routing.json"


def _load_staged_sc_llm_backend():
    module_path = TRACK_A_ROOT / "scripts" / "sc" / "_llm_backend.py"
    spec = importlib.util.spec_from_file_location("track_a_sc_llm_backend", module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"failed to load staged module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules["track_a_sc_llm_backend"] = module
    spec.loader.exec_module(module)
    return module


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return False
        try:
            exit_code = ctypes.c_ulong(0)
            ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
            return bool(ok and exit_code.value == 259)
        finally:
            kernel32.CloseHandle(handle)
    proc_stat = Path(f"/proc/{pid}/stat")
    if proc_stat.exists():
        try:
            txt = proc_stat.read_text(encoding="ascii", errors="ignore")
            state = txt[txt.rfind(")") + 2 :].split()[0]
            if state == "Z":
                return False
        except (OSError, IndexError):
            return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _sample_transcript_lines(
    *,
    executable: str = "/usr/local/bin/gemini",
    command: list[str] | None = None,
    model: str = "gemini-4-carbon-high",
    init_model: str | None = None,
    session_id: str = "550e8400-e29b-41d4-a716-446655440000",
    prompt: str = "exact prompt bytes\nline 2",
    assistant_chunks: tuple[str, ...] = ('{"verdict":', '"viable"}'),
    schema: dict[str, object] | None = None,
    requested_effort: str | None = "high",
    runtime_effort: str = "high",
    isolated_settings_sha256: str | None = None,
    system_settings_sha256: str | None = None,
    extra_events: tuple[dict[str, object], ...] = (),
    tool_calls: int = 0,
    exit_code: int | None = 0,
    include_init: bool = True,
) -> bytes:
    prompt_sha = gemini_protocol.digest(prompt.encode("utf-8"))
    schema_sha = gemini_protocol.schema_digest(schema)
    dummy_sha = "sha256:" + ("a" * 64)
    effort_for_settings = runtime_effort if runtime_effort in ("low", "high") else "high"
    expected_settings_sha = gemini_protocol.digest(
        gemini_protocol._canonical_bytes(gemini_protocol.build_isolated_settings(effort_for_settings))
        + b"\n"
    )
    if command is not None:
        launch_cmd = command
    elif model.casefold() not in gemini_protocol.FORBIDDEN_MODEL_ALIASES and model and not any(
        ch.isspace() for ch in model
    ):
        launch_cmd = gemini_protocol.gemini_command(executable, model)
    else:
        launch_cmd = [
            executable,
            "-m",
            model,
            "--output-format",
            "stream-json",
            "--raw-output",
            "--accept-raw-output-risk",
            "--skip-trust",
        ]
    records: list[dict[str, object]] = [
        {
            "direction": "host",
            "event": "gemini_cli_launch",
            "executable": executable,
            "command": launch_cmd,
            "model": model,
            "model_provider": "google",
            "requested_reasoning_effort": requested_effort,
            "runtime_reasoning_effort": runtime_effort,
            "isolated_settings_sha256": isolated_settings_sha256 or expected_settings_sha,
            "system_settings_sha256": system_settings_sha256 or expected_settings_sha,
            "system_md_sha256": dummy_sha,
            "prompt_sha256": prompt_sha,
            "schema_sha256": schema_sha,
            "model_tools": [],
        }
    ]
    if include_init:
        records.append(
            {
                "direction": "stdout",
                "line": {
                    "type": "init",
                    "timestamp": "2026-11-14T00:00:00Z",
                    "session_id": session_id,
                    "model": model if init_model is None else init_model,
                },
            }
        )
    records.append(
        {
            "direction": "stdout",
            "line": {
                "type": "message",
                "timestamp": "2026-11-14T00:00:01Z",
                "role": "user",
                "content": prompt,
            },
        }
    )
    for event in extra_events:
        records.append({"direction": "stdout", "line": event})
    for chunk in assistant_chunks:
        records.append(
            {
                "direction": "stdout",
                "line": {
                    "type": "message",
                    "timestamp": "2026-11-14T00:00:02Z",
                    "role": "assistant",
                    "content": chunk,
                    "delta": True,
                },
            }
        )
    records.append(
        {
            "direction": "stdout",
            "line": {
                "type": "result",
                "timestamp": "2026-11-14T00:00:03Z",
                "status": "success",
                "stats": {"tool_calls": tool_calls, "total_tokens": 10},
            },
        }
    )
    if exit_code is not None:
        records.append(
            {
                "direction": "exit",
                "returncode": exit_code,
                "stderr_sha256": gemini_protocol.digest(b""),
            }
        )
    return ("\n".join(json.dumps(row, separators=(",", ":")) for row in records) + "\n").encode(
        "utf-8"
    )


class LlmRoutingAndRegistryTests(unittest.TestCase):
    def test_routing_config_and_registry_helpers(self) -> None:
        raw_routing_bytes = ROUTING_CONFIG_PATH.read_bytes()
        self.assertGreater(raw_routing_bytes.count(b"\r\n"), 0)
        self.assertEqual(raw_routing_bytes.count(b"\r\n"), raw_routing_bytes.count(b"\n"))

        routing = registry.load_llm_routing(TRACK_A_ROOT)
        self.assertEqual("newrouge.llm-routing.v1", routing["schema_version"])
        self.assertEqual(
            "scripts/python/codex_isolated_model_runner.py",
            routing["plane_b"]["default_runner"],
        )
        self.assertEqual("codex-runtime-configured", routing["plane_b"]["runners"]["codex"]["model"])
        self.assertEqual("gemini-4-carbon-high", routing["plane_b"]["runners"]["gemini"]["model"])
        self.assertEqual("codex-cli", routing["plane_a"]["default_backend"])
        for alias in gemini_protocol.FORBIDDEN_MODEL_ALIASES:
            self.assertNotIn(f'"{alias}"', raw_routing_bytes.decode("utf-8"))
        self.assertTrue(routing["plane_a"]["backends"]["agy-subagent"]["plane_b_forbidden"])
        self.assertTrue(routing["plane_a"]["backends"]["openai-api"]["opt_in_only"])
        self.assertTrue(routing["plane_a"]["backends"]["gemini-api"]["opt_in_only"])

        self.assertEqual(
            ("codex_isolated_model_runner.py", "gemini_isolated_model_runner.py"),
            registry.OFFICIAL_RUNNER_SCRIPTS,
        )
        self.assertTrue(registry.is_official_isolated_runner_name("codex_isolated_model_runner.py"))
        self.assertTrue(registry.is_official_isolated_runner_name("gemini_isolated_model_runner.py"))
        self.assertTrue(
            registry.is_official_isolated_runner_name(
                "scripts/python/gemini_isolated_model_runner.py"
            )
        )
        self.assertFalse(
            registry.is_official_isolated_runner_name("/tmp/gemini_isolated_model_runner.py")
        )
        self.assertFalse(registry.is_official_isolated_runner_name("openai_isolated_model_runner.py"))

        self.assertEqual(
            "codex-app-server-stdio",
            registry.describe_runner_protocol("scripts/python/codex_isolated_model_runner.py"),
        )
        self.assertEqual(
            "codex-app-server-stdio",
            registry.describe_runner_protocol("codex-cli"),
        )
        self.assertEqual(
            "gemini-cli-stream-json",
            registry.describe_runner_protocol("scripts/python/gemini_isolated_model_runner.py"),
        )
        self.assertEqual(
            "gemini-cli-stream-json",
            registry.describe_runner_protocol("gemini-cli"),
        )

        self.assertTrue(registry.is_official_isolated_runner(GEMINI_RUNNER_PATH, TRACK_A_ROOT))
        with tempfile.TemporaryDirectory() as td:
            spoof = Path(td) / "gemini_isolated_model_runner.py"
            spoof.write_text("# spoof\n", encoding="utf-8")
            self.assertFalse(registry.is_official_isolated_runner(spoof, TRACK_A_ROOT))

        codex_runner = (TRACK_A_ROOT / "scripts/python/codex_isolated_model_runner.py").resolve()
        self.assertEqual(
            codex_runner,
            registry.resolve_plane_b_runner(TRACK_A_ROOT, env={}),
        )
        self.assertEqual(
            codex_runner,
            registry.resolve_plane_b_runner(
                TRACK_A_ROOT, requested_runner="auto", env={"NEWROGUE_PLANE_B_RUNNER": "auto"}
            ),
        )
        self.assertEqual(
            GEMINI_RUNNER_PATH.resolve(),
            registry.resolve_plane_b_runner(
                TRACK_A_ROOT, requested_runner="auto", env={"NEWROGUE_PLANE_B_RUNNER": "gemini-cli"}
            ),
        )
        self.assertEqual(
            codex_runner,
            registry.resolve_plane_b_runner(
                TRACK_A_ROOT, requested_runner="codex-cli", env={"NEWROGUE_PLANE_B_RUNNER": "gemini"}
            ),
        )
        self.assertEqual(
            GEMINI_RUNNER_PATH.resolve(),
            registry.resolve_plane_b_runner(
                TRACK_A_ROOT, requested_runner="gemini-cli", env={"NEWROGUE_PLANE_B_RUNNER": "codex"}
            ),
        )
        self.assertEqual(
            GEMINI_RUNNER_PATH.resolve(),
            registry.resolve_plane_b_runner(
                TRACK_A_ROOT, env={"NEWROGUE_PLANE_B_RUNNER": "gemini"}
            ),
        )
        self.assertEqual(
            GEMINI_RUNNER_PATH.resolve(),
            registry.resolve_plane_b_runner(
                TRACK_A_ROOT,
                requested_runner="scripts/python/gemini_isolated_model_runner.py",
                env={"NEWROGUE_PLANE_B_RUNNER": "codex"},
            ),
        )

        with mock.patch.dict(
            os.environ, {"NEWROGUE_LLM_ROUTING_PATH": "/nonexistent/override/llm-routing.json"}
        ):
            self.assertEqual(
                "gemini-4-carbon-high", registry.governed_model_for_provider("google", TRACK_A_ROOT)
            )
            self.assertEqual("auto", registry.governed_model_for_provider("openai", TRACK_A_ROOT))
            with self.assertRaises(ValueError):
                registry.governed_model_for_provider("anthropic", TRACK_A_ROOT)

        hex32 = "0123456789abcdef0123456789abcdef"
        self.assertTrue(
            registry.execution_output_name(f"out.json.{hex32}.gemini-stream.jsonl", "out.json")
        )
        self.assertTrue(
            registry.execution_output_name(
                f"out.json.{hex32}.gemini-stream.stderr.txt",
                "out.json",
                GEMINI_RUNNER_PATH,
            )
        )
        self.assertFalse(
            registry.execution_output_name(
                f"out.json.{hex32}.app-server.jsonl",
                "out.json",
                GEMINI_RUNNER_PATH,
            )
        )

    def test_reasoning_effort_bridge_and_conflict_rejection(self) -> None:
        self.assertIsNone(registry.resolve_reasoning_effort({}, allowed=("low", "high")))
        self.assertEqual(
            "high",
            registry.resolve_reasoning_effort(
                {"NEWROGUE_CODEX_REASONING_EFFORT": "high"}, allowed=("low", "high")
            ),
        )
        self.assertEqual(
            "low",
            registry.resolve_reasoning_effort(
                {"NEWROGUE_GEMINI_REASONING_EFFORT": "low"}, allowed=("low", "high")
            ),
        )
        with self.assertRaises(ValueError):
            registry.resolve_reasoning_effort(
                {
                    "NEWROGUE_GEMINI_REASONING_EFFORT": "low",
                    "NEWROGUE_CODEX_REASONING_EFFORT": "high",
                },
                allowed=("low", "high"),
            )
        env = registry.runner_environment(GEMINI_RUNNER_PATH, reasoning_effort="high", base_env={})
        self.assertEqual("1", env["PYTHONDONTWRITEBYTECODE"])
        self.assertEqual("plane_b", env["NEWROGUE_EXECUTION_PLANE"])
        self.assertEqual("high", env["NEWROGUE_GEMINI_REASONING_EFFORT"])
        self.assertEqual("high", env["NEWROGUE_CODEX_REASONING_EFFORT"])


class GeminiCliProtocolReplayTests(unittest.TestCase):
    def test_gemini_command_avoids_cmd_exe_wrapper_and_uses_long_output_format(self) -> None:
        win_exe = "C:\\Program Files\\nodejs\\gemini.cmd"
        with mock.patch.object(gemini_protocol.os, "name", "nt"):
            cmd = gemini_protocol.gemini_command(win_exe, "gemini-4-carbon-high")
        self.assertEqual(
            [
                win_exe,
                "-m",
                "gemini-4-carbon-high",
                "--output-format",
                "stream-json",
                "--raw-output",
                "--accept-raw-output-risk",
                "--skip-trust",
            ],
            cmd,
        )
        for forbidden_token in ("cmd.exe", "/d", "/s", "/c", "-o"):
            self.assertNotIn(forbidden_token, cmd)

    def test_build_child_env_scrubs_paid_api_and_cloud_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            gemini_home = base / "gemini_home"
            sys_settings = base / "system-settings.json"
            sys_md = base / "system.md"
            dirty_env = {
                "PATH": os.environ.get("PATH", ""),
                "GEMINI_MODEL": "gemini-1.5-flash",
                "GEMINI_SANDBOX": "docker",
                "GEMINI_PROMPT": "injected",
                "GEMINI_SYSTEM_MD": "/tmp/host-system.md",
                "GEMINI_WRITE_SYSTEM_MD": "/tmp/leak.md",
                "GEMINI_API_KEY": "paid-gemini-key",
                "GOOGLE_API_KEY": "paid-google-key",
                "GOOGLE_GENAI_USE_VERTEXAI": "true",
                "GOOGLE_GENAI_USE_GCA": "true",
                "GOOGLE_APPLICATION_CREDENTIALS": "/tmp/adc.json",
                "GOOGLE_CLOUD_PROJECT": "billing-proj",
                "GOOGLE_CLOUD_LOCATION": "us-central1",
                "GEMINI_CLI_SYSTEM_DEFAULTS_PATH": "/tmp/defaults.json",
                "GEMINI_CLI_SYSTEM_SETTINGS_PATH": "/tmp/host-settings.json",
                "NODE_OPTIONS": "--require=/tmp/hook.js",
            }
            cleaned = gemini_protocol._build_child_env(
                gemini_home=gemini_home,
                system_settings_path=sys_settings,
                system_md_path=sys_md,
                executable=str(FAKE_GEMINI_CLI),
                base_env=dirty_env,
            )
            for scrubbed_key in (
                "GEMINI_MODEL",
                "GEMINI_SANDBOX",
                "GEMINI_PROMPT",
                "GEMINI_WRITE_SYSTEM_MD",
                "GEMINI_API_KEY",
                "GOOGLE_API_KEY",
                "GOOGLE_GENAI_USE_VERTEXAI",
                "GOOGLE_GENAI_USE_GCA",
                "GOOGLE_APPLICATION_CREDENTIALS",
                "GOOGLE_CLOUD_PROJECT",
                "GOOGLE_CLOUD_LOCATION",
                "GEMINI_CLI_SYSTEM_DEFAULTS_PATH",
                "NODE_OPTIONS",
            ):
                self.assertNotIn(scrubbed_key, cleaned)
            self.assertEqual(str(sys_settings), cleaned["GEMINI_CLI_SYSTEM_SETTINGS_PATH"])
            self.assertEqual(str(sys_md), cleaned["GEMINI_SYSTEM_MD"])
            self.assertEqual(str(gemini_home), cleaned["GEMINI_CLI_HOME"])

    def test_replay_validates_authentic_stream_and_populates_thread_and_session_ids(self) -> None:
        schema = {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"verdict": {"type": "string", "enum": ["viable", "blocked"]}},
            "required": ["verdict"],
            "additionalProperties": False,
        }
        prompt = "exact prompt bytes\nline 2"
        session_id = "550e8400-e29b-41d4-a716-446655440000"
        raw = _sample_transcript_lines(
            session_id=session_id,
            prompt=prompt,
            schema=schema,
            extra_events=(
                {
                    "type": "error",
                    "timestamp": "2026-11-14T00:00:01.500Z",
                    "severity": "warning",
                    "message": "benign warning",
                },
            ),
        )
        output_text, proof = gemini_protocol.replay(raw, prompt=prompt, schema=schema)
        self.assertEqual('{"verdict":"viable"}', output_text)
        self.assertEqual(gemini_protocol.SOURCE, proof["source"])
        self.assertEqual(gemini_protocol.POLICY, proof["evidence_policy"])
        self.assertEqual("gemini-4-carbon-high", proof["model"])
        self.assertEqual("google", proof["model_provider"])
        self.assertEqual(session_id, proof["session_id"])
        self.assertEqual(session_id, proof["thread_id"])
        expected_turn = "sha256:" + hashlib.sha256(
            f"{session_id}:{proof['prompt_sha256']}".encode("utf-8")
        ).hexdigest()
        self.assertEqual(expected_turn, proof["turn_id"])
        self.assertTrue(proof["runtime_identity_verified"])
        self.assertEqual("runtime_configuration", proof["model_identity_scope"])
        self.assertIsNone(proof["provider_reported_model"])
        self.assertFalse(proof["provider_identity_verified"])
        self.assertEqual("unknown", proof["provider_dispatch_count"])
        self.assertEqual([], proof["model_tools"])
        self.assertEqual("high", proof["requested_reasoning_effort"])
        self.assertEqual("high", proof["runtime_reasoning_effort"])

    def test_replay_rejects_all_protocol_violations_and_tampering(self) -> None:
        schema = {
            "type": "object",
            "properties": {"verdict": {"type": "string"}},
            "required": ["verdict"],
            "additionalProperties": False,
        }
        prompt = "exact prompt bytes\nline 2"
        forged_sha = "sha256:" + ("b" * 64)
        tampered_yolo_cmd = [
            *gemini_protocol.gemini_command("/usr/local/bin/gemini", "gemini-4-carbon-high"),
            "--yolo",
        ]

        cases = [
            ("missing_init", _sample_transcript_lines(prompt=prompt, schema=schema, include_init=False)),
            ("empty_session", _sample_transcript_lines(prompt=prompt, schema=schema, session_id="")),
            ("auto_model_header", _sample_transcript_lines(prompt=prompt, schema=schema, model="auto")),
            (
                "forged_isolated_settings_sha256",
                _sample_transcript_lines(
                    prompt=prompt, schema=schema, isolated_settings_sha256=forged_sha
                ),
            ),
            (
                "mismatched_system_settings_sha256",
                _sample_transcript_lines(
                    prompt=prompt, schema=schema, system_settings_sha256=forged_sha
                ),
            ),
            (
                "tampered_command_yolo_flag",
                _sample_transcript_lines(
                    prompt=prompt, schema=schema, command=tampered_yolo_cmd
                ),
            ),
            (
                "init_model_downgrade",
                _sample_transcript_lines(prompt=prompt, schema=schema, init_model="auto"),
            ),
            (
                "init_model_mismatch",
                _sample_transcript_lines(
                    prompt=prompt, schema=schema, init_model="gemini-2.5-flash"
                ),
            ),
            (
                "tool_use_event",
                _sample_transcript_lines(
                    prompt=prompt,
                    schema=schema,
                    extra_events=({"type": "tool_use", "tool_name": "read_file"},),
                ),
            ),
            (
                "tool_result_event",
                _sample_transcript_lines(
                    prompt=prompt,
                    schema=schema,
                    extra_events=({"type": "tool_result", "status": "success"},),
                ),
            ),
            (
                "nonzero_tool_calls",
                _sample_transcript_lines(prompt=prompt, schema=schema, tool_calls=1),
            ),
            (
                "error_severity",
                _sample_transcript_lines(
                    prompt=prompt,
                    schema=schema,
                    extra_events=({"type": "error", "severity": "error", "message": "boom"},),
                ),
            ),
            (
                "markdown_fence",
                _sample_transcript_lines(
                    prompt=prompt,
                    schema=schema,
                    assistant_chunks=('```json\n{"verdict":"viable"}\n```',),
                ),
            ),
            (
                "duplicate_json_key",
                _sample_transcript_lines(
                    prompt=prompt,
                    schema=schema,
                    assistant_chunks=('{"verdict":"a","verdict":"b"}',),
                ),
            ),
            (
                "schema_violation",
                _sample_transcript_lines(
                    prompt=prompt,
                    schema=schema,
                    assistant_chunks=('{"wrong_key":"viable"}',),
                ),
            ),
            (
                "nonzero_exit",
                _sample_transcript_lines(prompt=prompt, schema=schema, exit_code=1),
            ),
        ]
        for label, raw in cases:
            with self.subTest(case=label):
                with self.assertRaises(ValueError):
                    gemini_protocol.replay(raw, prompt=prompt, schema=schema)

        valid_raw = _sample_transcript_lines(prompt=prompt, schema=schema)
        with self.assertRaises(ValueError):
            gemini_protocol.replay(valid_raw, prompt=prompt + " ", schema=schema)

    def test_agy_flavor_command_and_stream_replay(self) -> None:
        agy_exe = "/home/user/.local/bin/agy"
        self.assertEqual("agy", gemini_protocol.cli_flavor(agy_exe))
        self.assertEqual("agy", gemini_protocol.cli_flavor("C:\\Users\\u\\AppData\\Local\\agy\\bin\\agy.exe"))
        self.assertEqual("gemini", gemini_protocol.cli_flavor("/usr/local/bin/gemini"))
        self.assertEqual("gemini", gemini_protocol.cli_flavor(str(FAKE_GEMINI_CLI)))

        schema = {
            "type": "object",
            "properties": {"verdict": {"type": "string", "enum": ["viable", "blocked"]}},
            "required": ["verdict"],
            "additionalProperties": False,
        }
        cmd_with_schema = gemini_protocol.gemini_command(
            agy_exe, "gemini-4-carbon-high", has_schema=True
        )
        self.assertEqual(
            [
                agy_exe,
                "--sandbox",
                "--disable-slash-commands",
                "--model",
                "gemini-4-carbon-high",
                "--input-format",
                "stream-json",
                "--output-format",
                "stream-json",
                "--json-schema",
                "../schema.json",
            ],
            cmd_with_schema,
        )

        prompt = "Evaluate sc25 segment."
        sys_md_bytes = gemini_protocol.build_system_markdown(
            "Return ONLY a single valid JSON value.", schema
        )
        sys_md_text = sys_md_bytes.decode("utf-8")
        settings_sha = gemini_protocol.digest(
            gemini_protocol._canonical_bytes(gemini_protocol.build_isolated_settings("high"))
            + b"\n"
        )
        conv_id = "7a5c5e8f-7a86-4474-ae7b-7ae852d4c347"

        def make_agy_transcript(
            *,
            extra_step: dict[str, object] | None = None,
            permission_mode: str = "request-review",
            num_turns: int = 1,
        ) -> bytes:
            rows = [
                {
                    "direction": "host",
                    "event": "gemini_cli_launch",
                    "executable": agy_exe,
                    "command": cmd_with_schema,
                    "model": "gemini-4-carbon-high",
                    "model_provider": "google",
                    "requested_reasoning_effort": "high",
                    "runtime_reasoning_effort": "high",
                    "isolated_settings_sha256": settings_sha,
                    "system_settings_sha256": settings_sha,
                    "system_md_sha256": gemini_protocol.digest(sys_md_bytes),
                    "prompt_sha256": gemini_protocol.digest(prompt.encode("utf-8")),
                    "schema_sha256": gemini_protocol.schema_digest(schema),
                    "model_tools": [],
                },
                {
                    "direction": "stdin",
                    "line": {
                        "event": "user",
                        "message": {
                            "content": sys_md_text
                            + gemini_protocol.AGY_SYSTEM_PROMPT_BOUNDARY
                            + prompt
                        },
                    },
                },
                {
                    "direction": "stdout",
                    "line": {
                        "event": "init",
                        "conversation_id": conv_id,
                        "init": {
                            "model": "gemini-4-carbon-high",
                            "permission_mode": permission_mode,
                            "json_schema": schema,
                        },
                    },
                },
                {
                    "direction": "stdout",
                    "line": {
                        "event": "step_update",
                        "step_update": {
                            "conversation_id": conv_id,
                            "step_index": 0,
                            "state": "DONE",
                            "step_type": "user_input",
                        },
                    },
                },
            ]
            if extra_step is not None:
                rows.append({"direction": "stdout", "line": extra_step})
            rows.extend(
                [
                    {
                        "direction": "stdout",
                        "line": {
                            "event": "step_update",
                            "step_update": {
                                "conversation_id": conv_id,
                                "step_index": 1,
                                "state": "DONE",
                                "step_type": "agent_response",
                                "text_delta": '{"verdict":"viable"}\n',
                            },
                        },
                    },
                    {
                        "direction": "stdout",
                        "line": {
                            "event": "step_update",
                            "step_update": {
                                "conversation_id": conv_id,
                                "step_index": 2,
                                "state": "DONE",
                                "step_type": "finish",
                            },
                        },
                    },
                    {
                        "direction": "stdout",
                        "line": {
                            "event": "result",
                            "result": {
                                "conversation_id": conv_id,
                                "status": "SUCCESS",
                                "response": '{"verdict":"viable"}\n',
                                "num_turns": num_turns,
                                "structured_output": {"verdict": "viable"},
                            },
                        },
                    },
                    {
                        "direction": "exit",
                        "returncode": 0,
                        "stderr_sha256": gemini_protocol.digest(b""),
                    },
                ]
            )
            return ("\n".join(json.dumps(r, separators=(",", ":")) for r in rows) + "\n").encode(
                "utf-8"
            )

        out_txt, proof = gemini_protocol.replay(
            make_agy_transcript(), prompt=prompt, schema=schema
        )
        self.assertEqual('{"verdict":"viable"}', out_txt)
        self.assertEqual("gemini-4-carbon-high", proof["model"])
        self.assertEqual(conv_id, proof["session_id"])
        self.assertEqual(conv_id, proof["thread_id"])
        self.assertEqual([], proof["model_tools"])

        # Multi-step agy schema finalizer (num_turns=2) extracts clean structured_output
        out_t2, _ = gemini_protocol.replay(
            make_agy_transcript(num_turns=2), prompt=prompt, schema=schema
        )
        self.assertEqual('{"verdict":"viable"}', out_t2)

        # Cold-start replay without passing prompt argument must also verify prompt_sha256
        out_cold, proof_cold = gemini_protocol.replay(make_agy_transcript(), schema=schema)
        self.assertEqual(out_txt, out_cold)
        self.assertEqual(proof["turn_id"], proof_cold["turn_id"])

        # Any tool step_type, unsafe permission_mode, or excessive multi-turn result must fail closed
        for bad_raw in (
            make_agy_transcript(
                extra_step={
                    "event": "step_update",
                    "step_update": {
                        "conversation_id": conv_id,
                        "step_index": 1,
                        "state": "DONE",
                        "step_type": "run_command",
                    },
                }
            ),
            make_agy_transcript(permission_mode="auto"),
            make_agy_transcript(num_turns=4),
        ):
            with self.assertRaises(ValueError):
                gemini_protocol.replay(bad_raw, prompt=prompt, schema=schema)


class GeminiIsolatedModelRunnerTests(unittest.TestCase):
    def _runner_subprocess_env(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        python_path = os.pathsep.join([str(TRACK_A_PYTHON), str(REPO_PYTHON)])
        env = {
            key: val
            for key, val in os.environ.items()
            if not key.startswith(("NEWROGUE_", "GEMINI_", "GOOGLE_", "SC_", "OPENAI_", "CODEX_"))
            and key not in {"HOME", "USERPROFILE"}
        }
        env["PYTHONPATH"] = python_path
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["NEWROGUE_LLM_ROUTING_PATH"] = str(ROUTING_CONFIG_PATH)
        if extra:
            env.update(extra)
        return env

    def test_describe_in_scrubbed_env_and_model_conflict_guards(self) -> None:
        proc = subprocess.run(
            [sys.executable, "-B", str(GEMINI_RUNNER_PATH), "--describe"],
            env=self._runner_subprocess_env(),
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
        self.assertEqual(0, proc.returncode, msg=proc.stderr)
        info = json.loads(proc.stdout)
        skill_common.validate_runner_description(info)
        self.assertEqual("gemini-4-carbon-high", info["model"])
        self.assertEqual("google", info["model_provider"])
        self.assertEqual("google/gemini-4-carbon-high", info["model_identity"])
        self.assertEqual(gemini_protocol.POLICY, info["evidence_policy"])
        self.assertEqual([], info["model_tools"])
        self.assertNotIn("requested_reasoning_effort", info)

        state = {"analysis_identity_sha256": "input-sha"}
        sel_receipt = {
            "schema_version": "newrouge.mvg-selection-execution-receipt.v1",
            "analysis_identity_sha256": "input-sha",
            "selection_input_sha256": "sel-sha",
            "output_sha256": "out-sha",
            "runner_info": info,
            "runner_receipt": {"model": "gemini-4-carbon-high", "model_tools": []},
        }
        self.assertEqual(
            [],
            plan_mvg.validate_selection_execution_receipt(
                state,
                {"status": "selected"},
                sel_receipt,
                selection_input_sha256="sel-sha",
                output_sha256="out-sha",
            ),
        )

        bad_model = subprocess.run(
            [
                sys.executable,
                "-B",
                str(GEMINI_RUNNER_PATH),
                "--describe",
                "--model",
                "gemini-2.5-flash",
            ],
            env=self._runner_subprocess_env(),
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
        self.assertEqual(2, bad_model.returncode)
        self.assertEqual("blocked", json.loads(bad_model.stdout)["status"])

        override_ok = subprocess.run(
            [
                sys.executable,
                "-B",
                str(GEMINI_RUNNER_PATH),
                "--describe",
                "--model",
                "gemini-2.5-flash",
            ],
            env=self._runner_subprocess_env(
                {
                    "NEWROGUE_GEMINI_MODEL_OVERRIDE": "gemini-2.5-flash",
                    "NEWROGUE_CODEX_REASONING_EFFORT": "high",
                }
            ),
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
        self.assertEqual(0, override_ok.returncode)
        override_info = json.loads(override_ok.stdout)
        self.assertEqual("gemini-2.5-flash", override_info["model"])
        self.assertEqual("high", override_info["requested_reasoning_effort"])

        bad_effort = subprocess.run(
            [sys.executable, "-B", str(GEMINI_RUNNER_PATH), "--describe"],
            env=self._runner_subprocess_env(
                {
                    "NEWROGUE_GEMINI_REASONING_EFFORT": "low",
                    "NEWROGUE_CODEX_REASONING_EFFORT": "high",
                }
            ),
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
        self.assertEqual(2, bad_effort.returncode)
        self.assertEqual("blocked", json.loads(bad_effort.stdout)["status"])

    def test_single_turn_sandbox_isolation_stream_sidecars_and_execution_binding(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            fake_auth_home = base / "host_user"
            fake_dot_gemini = fake_auth_home / ".gemini"
            fake_dot_gemini.mkdir(parents=True)
            (fake_dot_gemini / "oauth_creds.json").write_text('{"refresh_token":"tok"}', encoding="utf-8")
            (fake_dot_gemini / "google_accounts.json").write_text('{"active":"u@example.com"}', encoding="utf-8")
            (fake_dot_gemini / "settings.json").write_text('{"mcpServers":{"evil":{}}}', encoding="utf-8")
            (fake_dot_gemini / "GEMINI.md").write_text("HOST_SECRET_CONTEXT", encoding="utf-8")

            inspect_log = base / "inspect.jsonl"
            workspace = base / "workspace"
            workspace.mkdir()
            prompt_path = workspace / "prompt.md"
            schema_path = workspace / "schema.json"
            output_path = workspace / "output.json"

            prompt_path.write_text("Evaluate isolated capability candidate.", encoding="utf-8")
            schema_obj = {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {
                    "verdict": {"type": "string", "enum": ["viable", "blocked"]},
                    "count": {"type": "integer", "minimum": 1},
                },
                "required": ["verdict", "count"],
                "additionalProperties": False,
            }
            schema_path.write_text(json.dumps(schema_obj), encoding="utf-8")

            env = self._runner_subprocess_env(
                {
                    "NEWROGUE_GEMINI_BIN": str(FAKE_GEMINI_CLI),
                    "NEWROGUE_GEMINI_AUTH_SRC": str(fake_auth_home),
                    "NEWROGUE_CODEX_REASONING_EFFORT": "high",
                    "FAKE_GEMINI_INSPECT_LOG": str(inspect_log),
                    "FAKE_GEMINI_RESPONSE_JSON": '{"verdict":"viable","count":3}',
                    "FAKE_GEMINI_CHUNK_SIZE": "9",
                }
            )

            preflight = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(GEMINI_RUNNER_PATH),
                    "--workspace",
                    str(workspace),
                    "--prompt-file",
                    str(prompt_path),
                    "--output",
                    str(output_path),
                    "--output-schema",
                    str(schema_path),
                    "--preflight",
                ],
                env=env,
                text=True,
                capture_output=True,
                check=False,
                timeout=20,
            )
            self.assertEqual(0, preflight.returncode, msg=preflight.stderr)
            self.assertFalse(json.loads(preflight.stdout)["model_invoked"])
            self.assertFalse(inspect_log.exists())

            full_payload = gemini_runner.workspace_payload(
                workspace,
                prompt_path=prompt_path,
                output_path=output_path,
                max_bytes=gemini_runner.DEFAULT_MAX_BYTES,
            )

            proc1 = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(GEMINI_RUNNER_PATH),
                    "--workspace",
                    str(workspace),
                    "--prompt-file",
                    str(prompt_path),
                    "--output",
                    str(output_path),
                    "--output-schema",
                    str(schema_path),
                ],
                env=env,
                text=True,
                capture_output=True,
                check=False,
                timeout=20,
            )
            self.assertEqual(0, proc1.returncode, msg=proc1.stdout + proc1.stderr)
            receipt1 = json.loads(proc1.stdout.strip().splitlines()[-1])
            self.assertEqual("gemini-4-carbon-high", receipt1["model"])
            self.assertEqual("google", receipt1["model_provider"])
            self.assertEqual("google/gemini-4-carbon-high", receipt1["model_identity"])

            stream_files = sorted(workspace.glob("output.json.*.gemini-stream.jsonl"))
            stderr_files = sorted(workspace.glob("output.json.*.gemini-stream.stderr.txt"))
            self.assertEqual(1, len(stream_files))
            self.assertEqual(1, len(stderr_files))
            self.assertEqual(0, stderr_files[0].stat().st_size)

            allowed_names = {
                "prompt.md",
                "schema.json",
                "output.json",
                "runner-input-integrity.json",
                stream_files[0].name,
                stderr_files[0].name,
            }
            self.assertEqual(allowed_names, {p.name for p in workspace.iterdir()})
            for sfile in (stream_files[0].name, stderr_files[0].name):
                self.assertTrue(
                    registry.execution_output_name(sfile, "output.json", GEMINI_RUNNER_PATH)
                )

            telemetry = json.loads(inspect_log.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual([], telemetry["cwd_entries"])
            self.assertEqual(
                ["google_accounts.json", "oauth_creds.json", "settings.json"],
                telemetry["dot_gemini_files"],
            )
            if os.name != "nt":
                self.assertEqual("0o600", telemetry["oauth_creds_mode"])
            self.assertTrue(telemetry["system_settings_exists"])
            self.assertTrue(telemetry["system_md_exists"])
            self.assertTrue(telemetry["system_md_has_schema"])
            self.assertNotIn("-p", telemetry["argv"])
            self.assertNotIn("--prompt", telemetry["argv"])

            host_exec = {
                "status": "completed",
                "returncode": 0,
                "runner_dispatch_count": 1,
                "active_elapsed_seconds": 0.12,
                "stdout": proc1.stdout,
                "stdout_base64": base64.b64encode(proc1.stdout.encode("utf-8")).decode("ascii"),
            }
            output_bytes = output_path.read_bytes()
            execution_binding.validate_execution(
                workspace,
                host_exec,
                receipt1,
                "gemini-4-carbon-high",
                output_bytes,
                prompt=full_payload,
                schema=schema_obj,
                require_runtime=True,
                expected_reasoning_effort="high",
            )
            execution_binding.validate_execution(
                workspace,
                host_exec,
                receipt1,
                "google/gemini-4-carbon-high",
                output_bytes,
                prompt=full_payload,
                schema=schema_obj,
                require_runtime=False,
                expected_reasoning_effort="high",
            )

            tampered = deepcopy(receipt1)
            tampered["model_identity_evidence"][0]["model"] = "forged-model"
            tampered_stdout = json.dumps(tampered) + "\n"
            tampered_exec = {
                **host_exec,
                "stdout": tampered_stdout,
                "stdout_base64": base64.b64encode(tampered_stdout.encode("utf-8")).decode("ascii"),
            }
            with self.assertRaises((ValueError, codec.CodecError)):
                execution_binding.validate_execution(
                    workspace,
                    tampered_exec,
                    tampered,
                    "gemini-4-carbon-high",
                    output_bytes,
                    prompt=full_payload,
                    schema=schema_obj,
                    require_runtime=True,
                    expected_reasoning_effort="high",
                )

            workspace_2 = base / "workspace_2"
            workspace_2.mkdir()
            prompt_2 = workspace_2 / "prompt.md"
            schema_2 = workspace_2 / "schema.json"
            output_2 = workspace_2 / "output.json"
            prompt_2.write_text(prompt_path.read_text(encoding="utf-8"), encoding="utf-8")
            schema_2.write_text(schema_path.read_text(encoding="utf-8"), encoding="utf-8")
            proc2 = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(GEMINI_RUNNER_PATH),
                    "--workspace",
                    str(workspace_2),
                    "--prompt-file",
                    str(prompt_2),
                    "--output",
                    str(output_2),
                    "--output-schema",
                    str(schema_2),
                ],
                env=env,
                text=True,
                capture_output=True,
                check=False,
                timeout=20,
            )
            self.assertEqual(0, proc2.returncode, msg=proc2.stdout + proc2.stderr)
            receipt2 = json.loads(proc2.stdout.strip().splitlines()[-1])
            ev1 = receipt1["model_identity_evidence"][0]
            ev2 = receipt2["model_identity_evidence"][0]
            self.assertNotEqual(ev1["session_id"], ev2["session_id"])
            self.assertNotEqual(ev1["thread_id"], ev2["thread_id"])
            self.assertNotEqual(ev1["turn_id"], ev2["turn_id"])

    def test_runner_blocks_when_fake_gemini_emits_tool_use_or_fences(self) -> None:
        for fault in ("tool_use", "markdown_fence", "model_downgrade_auto", "error_event"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as td:
                workspace = Path(td) / "workspace"
                workspace.mkdir()
                prompt_path = workspace / "prompt.md"
                output_path = workspace / "output.json"
                prompt_path.write_text("Test negative guard.", encoding="utf-8")
                proc = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        str(GEMINI_RUNNER_PATH),
                        "--workspace",
                        str(workspace),
                        "--prompt-file",
                        str(prompt_path),
                        "--output",
                        str(output_path),
                    ],
                    env=self._runner_subprocess_env(
                        {
                            "NEWROGUE_GEMINI_BIN": str(FAKE_GEMINI_CLI),
                            "FAKE_GEMINI_FAULT_MODE": fault,
                            "FAKE_GEMINI_RESPONSE_JSON": '{"ok":true}',
                        }
                    ),
                    text=True,
                    capture_output=True,
                    check=False,
                    timeout=15,
                )
                self.assertEqual(2, proc.returncode)
                self.assertEqual("blocked", json.loads(proc.stdout.strip())["status"])
                self.assertFalse(output_path.exists())
                self.assertEqual(1, len(list(workspace.glob("output.json.*.gemini-stream.jsonl"))))
                self.assertEqual(
                    1, len(list(workspace.glob("output.json.*.gemini-stream.stderr.txt")))
                )

    def test_batched_mode_executes_batches_and_synthesis_with_disjoint_threads(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            workspace = Path(td) / "workspace"
            analysis_dir = workspace / "analysis-input"
            batches_dir = analysis_dir / "model-batches"
            batches_dir.mkdir(parents=True)

            block_row = {
                "block_id": "SB-001",
                "source_id": "SRC-1",
                "source_path": "docs/gdd/sample.md",
                "section_heading": "Combat",
                "block_kind": "paragraph",
                "raw_text": "Player plays cards using mana each turn.",
                "delivery_relevant": True,
            }
            req_row = {
                "requirement_id": "REQ-001",
                "status": "active",
                "delivery_relevant": True,
                "summary": "Turn mana card play",
                "source_block_ids": ["SB-001"],
            }
            sb_path = analysis_dir / "source-blocks.v1.json"
            sr_path = analysis_dir / "semantic-requirements.v1.json"
            sb_path.write_text(
                json.dumps({"schema_version": "1.0", "blocks": [block_row]}),
                encoding="utf-8",
            )
            sr_path.write_text(
                json.dumps({"schema_version": "1.0", "requirements": [req_row]}),
                encoding="utf-8",
            )
            batch_payload = {
                "schema_version": "newrouge.capability-model-batch.v1",
                "batch_index": 1,
                "batch_count": 1,
                "blocks": [block_row],
                "requirements": [req_row],
            }
            batch_file = batches_dir / "batch-001.json"
            batch_file.write_text(
                json.dumps(batch_payload), encoding="utf-8"
            )
            batch_index = {
                "schema_version": "newrouge.capability-model-batch-index.v1",
                "batch_count": 1,
                "block_count": 1,
                "model_block_count": 1,
                "excluded_source_blocks": [],
                "requirement_count": 1,
                "batches": [
                    {
                        "batch_index": 1,
                        "path": "model-batches/batch-001.json",
                        "sha256": skill_common.file_sha(batch_file),
                        "block_ids": ["SB-001"],
                        "requirement_ids": ["REQ-001"],
                    }
                ],
            }
            batch_index_file = batches_dir / "batch-index.json"
            batch_index_file.write_text(
                json.dumps(batch_index), encoding="utf-8"
            )
            analysis_index_body = {
                "schema_version": "newrouge.planning-analysis-input.v1",
                "files": {
                    "source-blocks.v1.json": skill_common.file_sha(sb_path),
                    "semantic-requirements.v1.json": skill_common.file_sha(sr_path),
                },
                "model_batch_index": batch_index,
            }
            analysis_index = {
                **analysis_index_body,
                "analysis_identity_sha256": skill_common.canonical_sha(analysis_index_body),
            }
            (analysis_dir / "analysis-index.json").write_text(
                json.dumps(analysis_index), encoding="utf-8"
            )

            prompt_path = workspace / "prompt.md"
            prompt_path.write_text("Synthesize capabilities.", encoding="utf-8")
            schema_path = workspace / "final-schema.json"
            schema_path.write_text(
                json.dumps(
                    {
                        "type": "object",
                        "properties": {"capabilities": {"type": "array"}},
                        "required": ["capabilities"],
                    }
                ),
                encoding="utf-8",
            )
            output_path = workspace / "final-output.json"

            queue_file = Path(td) / "responses.json"
            queue_file.write_text(
                json.dumps(
                    [
                        {
                            "schema_version": "newrouge.capability-batch-analysis.v1",
                            "batch_index": 1,
                            "source_block_analyses": [
                                {
                                    "source_block_id": "SB-001",
                                    "summary": "Mana card play rule.",
                                    "boundary_signals": ["combat"],
                                }
                            ],
                            "requirement_analyses": [
                                {
                                    "requirement_id": "REQ-001",
                                    "source_block_ids": ["SB-001"],
                                    "intent": "Allow playing cards with mana.",
                                    "user_outcome": "Player spends mana to play cards.",
                                    "boundary_signals": ["combat"],
                                }
                            ],
                            "task_view_analyses": [],
                        },
                        {"capabilities": [{"id": "CAP-001", "requirements": ["REQ-001"]}]},
                    ]
                ),
                encoding="utf-8",
            )

            proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(GEMINI_RUNNER_PATH),
                    "--workspace",
                    str(workspace),
                    "--prompt-file",
                    str(prompt_path),
                    "--output",
                    str(output_path),
                ],
                env=self._runner_subprocess_env(
                    {
                        "NEWROGUE_GEMINI_BIN": str(FAKE_GEMINI_CLI),
                        "FAKE_GEMINI_RESPONSE_QUEUE_FILE": str(queue_file),
                    }
                ),
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )
            self.assertEqual(0, proc.returncode, msg=proc.stdout + proc.stderr)
            receipt = json.loads(proc.stdout.strip().splitlines()[-1])
            self.assertEqual("gemini-cli-stream-json-batched", receipt["transport"])
            self.assertEqual(2, receipt["model_request_count"])
            self.assertEqual(2, len(receipt["model_identity_evidence"]))
            t0, t1 = (
                receipt["model_identity_evidence"][0]["thread_id"],
                receipt["model_identity_evidence"][1]["thread_id"],
            )
            self.assertNotEqual(t0, t1)

    def test_hanging_child_tree_is_killed_cleanly_on_timeout(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            workspace = base / "workspace"
            workspace.mkdir()
            prompt_path = workspace / "prompt.md"
            output_path = workspace / "output.json"
            prompt_path.write_text("Trigger hang.", encoding="utf-8")
            pid_file = base / "pids.json"

            env = self._runner_subprocess_env(
                {
                    "NEWROGUE_GEMINI_BIN": str(FAKE_GEMINI_CLI),
                    "FAKE_GEMINI_FAULT_MODE": "hang_with_child",
                    "FAKE_GEMINI_PID_FILE": str(pid_file),
                }
            )
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-B",
                    str(GEMINI_RUNNER_PATH),
                    "--workspace",
                    str(workspace),
                    "--prompt-file",
                    str(prompt_path),
                    "--output",
                    str(output_path),
                    "--timeout-sec",
                    "30",
                ],
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                start_new_session=(os.name != "nt"),
            )
            try:
                deadline = time.monotonic() + 5.0
                while not pid_file.is_file() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(pid_file.is_file(), "Fake Gemini CLI did not record child PIDs")
                pids = json.loads(pid_file.read_text(encoding="utf-8"))

                skill_common._terminate_process_tree(proc)
                proc.wait(timeout=5)

                wait_dead = time.monotonic() + 3.0
                while time.monotonic() < wait_dead and (
                    _pid_alive(pids["gemini_pid"]) or _pid_alive(pids["child_pid"])
                ):
                    time.sleep(0.05)
                self.assertFalse(_pid_alive(pids["gemini_pid"]))
                self.assertFalse(_pid_alive(pids["child_pid"]))
            finally:
                if proc.poll() is None:
                    skill_common._terminate_process_tree(proc)
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
                if proc.stdout is not None and not proc.stdout.closed:
                    proc.stdout.close()

    def test_source_audit_tool_identity_binds_gemini_runner_and_governed_identity(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "NEWROGUE_GEMINI_BIN": str(FAKE_GEMINI_CLI),
                "NEWROGUE_LLM_ROUTING_PATH": str(ROUTING_CONFIG_PATH),
                "NEWROGUE_GEMINI_REASONING_EFFORT": "high",
                "NEWROGUE_CODEX_REASONING_EFFORT": "high",
            },
            clear=False,
        ):
            spec = registry.resolve_runner_spec(GEMINI_RUNNER_PATH, TRACK_A_ROOT)
            self.assertEqual("google", spec.provider)
            self.assertEqual("gemini-4-carbon-high", spec.model)
            self.assertEqual("google/gemini-4-carbon-high", spec.model_identity)

            desc = skill_common.inspect_isolated_runner(GEMINI_RUNNER_PATH, suppress_bytecode=True)
            self.assertEqual("google", desc["model_provider"])
            self.assertEqual("gemini-4-carbon-high", desc["model"])
            self.assertEqual("google/gemini-4-carbon-high", desc["model_identity"])

            identity = source_audit.tool_identity(
                TRACK_A_ROOT,
                GEMINI_RUNNER_PATH,
                spec.model_identity,
                "full-block",
            )
            self.assertEqual("google/gemini-4-carbon-high", identity["expected_model"])
            self.assertEqual("high", identity["expected_reasoning_effort"])
            tools = identity["tools"]
            self.assertIn("scripts/python/gemini_isolated_model_runner.py", tools)
            self.assertIn("scripts/python/_gemini_cli_protocol.py", tools)
            self.assertIn("scripts/python/_isolated_runner_registry.py", tools)
            self.assertIn("docs/workflows/llm-routing.json", tools)
            self.assertIn("gemini:system_md_sha256", tools)
            self.assertIn("gemini:thinking_config", tools)
            self.assertIn(str(FAKE_GEMINI_CLI.resolve()), tools)


class PlaneALlmBackendMultiModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sc_backend = _load_staged_sc_llm_backend()

    def test_routing_defaults_and_known_backends(self) -> None:
        self.assertEqual(
            ("codex-cli", "gemini-cli", "agy-subagent", "openai-api", "gemini-api"),
            self.sc_backend.KNOWN_LLM_BACKENDS,
        )
        with mock.patch.dict(
            os.environ,
            {
                "SC_LLM_BACKEND": "",
                "NEWROGUE_PLANE_A_BACKEND": "",
                "NEWROGUE_LLM_ROUTING_PATH": str(ROUTING_CONFIG_PATH),
            },
            clear=False,
        ):
            self.assertEqual(
                "codex-cli", self.sc_backend.resolve_llm_backend(None, root=TRACK_A_ROOT)
            )
            self.assertTrue(
                self.sc_backend.is_plane_b_forbidden_backend("agy-subagent", root=TRACK_A_ROOT)
            )
            self.assertFalse(
                self.sc_backend.is_plane_b_forbidden_backend("gemini-cli", root=TRACK_A_ROOT)
            )
        with mock.patch.dict(
            os.environ,
            {
                "SC_LLM_BACKEND": "",
                "NEWROGUE_PLANE_A_BACKEND": "gemini-cli",
                "NEWROGUE_LLM_ROUTING_PATH": str(ROUTING_CONFIG_PATH),
            },
            clear=False,
        ):
            self.assertEqual(
                "gemini-cli", self.sc_backend.resolve_llm_backend(None, root=TRACK_A_ROOT)
            )

    def test_gemini_cli_backend_executes_and_enforces_strict_schema_without_fence_fallback(
        self,
    ) -> None:
        schema_doc = {
            "type": "object",
            "properties": {"status": {"type": "string"}},
            "required": ["status"],
            "additionalProperties": False,
        }
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            schema_path = base / "schema.json"
            schema_path.write_text(json.dumps(schema_doc), encoding="utf-8")
            inspect_log = base / "sc-inspect.jsonl"

            with mock.patch.dict(
                os.environ,
                {
                    "NEWROGUE_GEMINI_BIN": str(FAKE_GEMINI_CLI),
                    "NEWROGUE_LLM_ROUTING_PATH": str(ROUTING_CONFIG_PATH),
                    "NEWROGUE_ALLOW_PAID_API": "",
                    "SC_ALLOW_PAID_API": "",
                    "GEMINI_API_KEY": "should-be-scrubbed",
                    "GOOGLE_API_KEY": "should-be-scrubbed",
                    "GOOGLE_GENAI_USE_VERTEXAI": "true",
                    "GOOGLE_APPLICATION_CREDENTIALS": "/tmp/adc.json",
                    "FAKE_GEMINI_INSPECT_LOG": str(inspect_log),
                    "FAKE_GEMINI_RESPONSE_JSON": '{"status":"ok"}',
                },
                clear=False,
            ):
                out_path = base / "last.json"
                info = self.sc_backend.inspect_llm_backend("gemini-cli", root=TRACK_A_ROOT)
                self.assertTrue(info["available"])
                self.assertEqual("gemini-4-carbon-high", info["model"])

                rc, _stdout, cmd = self.sc_backend.run_llm_exec(
                    backend="gemini-cli",
                    root=TRACK_A_ROOT,
                    prompt="review diff",
                    output_last_message=out_path,
                    timeout_sec=15,
                    output_schema=schema_path,
                )
                self.assertEqual(0, rc)
                self.assertIn("gemini-4-carbon-high", cmd)
                self.assertIn("plan", cmd)
                self.assertIn("--output-format", cmd)
                self.assertNotIn("-o", cmd)
                self.assertNotIn("cmd.exe", cmd)
                self.assertEqual('{"status":"ok"}\n', out_path.read_text(encoding="utf-8"))

                telemetry = json.loads(inspect_log.read_text(encoding="utf-8").splitlines()[-1])
                self.assertEqual([], telemetry["cwd_entries"])
                self.assertTrue(telemetry["system_settings_exists"])
                self.assertEqual([], telemetry["scrubbed_env_present"])

            with mock.patch.dict(
                os.environ,
                {
                    "NEWROGUE_GEMINI_BIN": str(FAKE_GEMINI_CLI),
                    "NEWROGUE_LLM_ROUTING_PATH": str(ROUTING_CONFIG_PATH),
                    "FAKE_GEMINI_RESPONSE_JSON": '```json\n{"status":"ok"}\n```',
                },
                clear=False,
            ):
                fenced_out = base / "fenced.json"
                rc_fence, msg_fence, _ = self.sc_backend.run_llm_exec(
                    backend="gemini-cli",
                    root=TRACK_A_ROOT,
                    prompt="review diff",
                    output_last_message=fenced_out,
                    timeout_sec=15,
                    output_schema=schema_path,
                )
                self.assertNotEqual(0, rc_fence)
                self.assertIn("markdown fence", msg_fence)
                self.assertFalse(fenced_out.exists())

            with mock.patch.dict(
                os.environ,
                {
                    "NEWROGUE_GEMINI_BIN": str(FAKE_GEMINI_CLI),
                    "NEWROGUE_LLM_ROUTING_PATH": str(ROUTING_CONFIG_PATH),
                    "FAKE_GEMINI_RESPONSE_JSON": '{"status":123}',
                },
                clear=False,
            ):
                invalid_out = base / "invalid.json"
                rc_invalid, msg_invalid, _ = self.sc_backend.run_llm_exec(
                    backend="gemini-cli",
                    root=TRACK_A_ROOT,
                    prompt="review diff",
                    output_last_message=invalid_out,
                    timeout_sec=15,
                    output_schema=schema_path,
                )
                self.assertNotEqual(0, rc_invalid)
                self.assertIn("Schema validation", msg_invalid)
                self.assertFalse(invalid_out.exists())

    def test_agy_subagent_plane_b_forbidden_and_bridge_execution(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            out_path = Path(td) / "subagent.md"
            with mock.patch.dict(
                os.environ,
                {
                    "NEWROGUE_EXECUTION_PLANE": "plane_b",
                    "SC_AGY_SUBAGENT_CMD": f"{sys.executable} -B -c \"print('hi')\"",
                },
                clear=False,
            ):
                rc, out, _cmd = self.sc_backend.run_llm_exec(
                    backend="agy-subagent",
                    root=TRACK_A_ROOT,
                    prompt="forbidden on plane b",
                    output_last_message=out_path,
                    timeout_sec=10,
                )
                self.assertEqual(2, rc)
                self.assertIn("forbidden on Plane B", out)

            with mock.patch.dict(
                os.environ,
                {
                    "NEWROGUE_EXECUTION_PLANE": "",
                    "SC_PLANE_B_CONTEXT": "",
                    "SC_AGY_SUBAGENT_CMD": (
                        f"{sys.executable} -B -c \"import sys; print('subagent:' + sys.stdin.read().strip())\""
                    ),
                },
                clear=False,
            ):
                rc2, _out2, _cmd2 = self.sc_backend.run_llm_exec(
                    backend="agy-subagent",
                    root=TRACK_A_ROOT,
                    prompt="check task",
                    output_last_message=out_path,
                    timeout_sec=10,
                )
                self.assertEqual(0, rc2)
                self.assertEqual("subagent:check task\n", out_path.read_text(encoding="utf-8"))

    def test_paid_api_opt_in_honors_both_newrogue_and_sc_env_vars(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "NEWROGUE_ALLOW_PAID_API": "",
                "SC_ALLOW_PAID_API": "",
                "GEMINI_API_KEY": "fake-key",
                "GOOGLE_API_KEY": "",
            },
            clear=False,
        ):
            rc_optin, out_optin, _ = self.sc_backend.run_llm_exec(
                backend="gemini-api",
                root=TRACK_A_ROOT,
                prompt="hello",
                output_last_message=TRACK_A_ROOT / "unused.md",
                timeout_sec=10,
            )
            self.assertEqual(2, rc_optin)
            self.assertIn("opt-in only", out_optin)

        with mock.patch.dict(
            os.environ,
            {
                "NEWROGUE_ALLOW_PAID_API": "1",
                "SC_ALLOW_PAID_API": "",
                "GEMINI_API_KEY": "",
                "GOOGLE_API_KEY": "",
            },
            clear=False,
        ):
            rc_missing, out_missing, _ = self.sc_backend.run_llm_exec(
                backend="gemini-api",
                root=TRACK_A_ROOT,
                prompt="hello",
                output_last_message=TRACK_A_ROOT / "unused.md",
                timeout_sec=10,
            )
            self.assertEqual(2, rc_missing)
            self.assertIn("GEMINI_API_KEY is not set", out_missing)

        class _FakeHTTPResponse(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *args):
                self.close()

        fake_body = json.dumps(
            {"candidates": [{"content": {"parts": [{"text": '{"ok":true}'}]}}]}
        ).encode("utf-8")
        for allow_env in (
            {"NEWROGUE_ALLOW_PAID_API": "1", "SC_ALLOW_PAID_API": ""},
            {"NEWROGUE_ALLOW_PAID_API": "", "SC_ALLOW_PAID_API": "1"},
        ):
            with self.subTest(gemini_api_env=allow_env), tempfile.TemporaryDirectory() as td, mock.patch.dict(
                os.environ,
                {
                    **allow_env,
                    "GEMINI_API_KEY": "fake-key",
                    "NEWROGUE_LLM_ROUTING_PATH": str(ROUTING_CONFIG_PATH),
                },
                clear=False,
            ), mock.patch.object(
                self.sc_backend.urllib.request,
                "urlopen",
                return_value=_FakeHTTPResponse(fake_body),
            ):
                out_path = Path(td) / "api.json"
                rc_ok, trace_out, cmd_ok = self.sc_backend.run_llm_exec(
                    backend="gemini-api",
                    root=TRACK_A_ROOT,
                    prompt="hello",
                    output_last_message=out_path,
                    timeout_sec=10,
                )
                self.assertEqual(0, rc_ok)
                self.assertEqual(["gemini-api", "gemini-4-carbon-high"], cmd_ok)
                self.assertIn('"backend": "gemini-api"', trace_out)
                self.assertEqual('{"ok":true}\n', out_path.read_text(encoding="utf-8"))

        class _FakeOpenAIResponses:
            def create(self, **_kwargs):
                return types.SimpleNamespace(id="resp_paid_ok", output_text='{"ok":true}')

        class _FakeOpenAIClient:
            def __init__(self, *, timeout):
                self.timeout = timeout
                self.responses = _FakeOpenAIResponses()

        spec_backed_openai = types.ModuleType("openai")
        spec_backed_openai.__spec__ = importlib.machinery.ModuleSpec("openai", loader=None)
        spec_backed_openai.OpenAI = _FakeOpenAIClient  # type: ignore[attr-defined]

        with mock.patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "sk-fake",
                "NEWROGUE_ALLOW_PAID_API": "",
                "SC_ALLOW_PAID_API": "",
            },
            clear=False,
        ), mock.patch.object(
            self.sc_backend.importlib.util, "find_spec", return_value=spec_backed_openai.__spec__
        ), mock.patch.dict(sys.modules, {"openai": spec_backed_openai}):
            rc_blocked, out_blocked, _ = self.sc_backend.run_llm_exec(
                backend="openai-api",
                root=TRACK_A_ROOT,
                prompt="hello",
                output_last_message=TRACK_A_ROOT / "unused-openai.json",
                timeout_sec=10,
            )
            self.assertEqual(2, rc_blocked)
            self.assertIn("opt-in only", out_blocked)

        for allow_env in (
            {"NEWROGUE_ALLOW_PAID_API": "1", "SC_ALLOW_PAID_API": ""},
            {"NEWROGUE_ALLOW_PAID_API": "", "SC_ALLOW_PAID_API": "1"},
        ):
            with self.subTest(openai_api_env=allow_env), tempfile.TemporaryDirectory() as td, mock.patch.dict(
                os.environ,
                {
                    **allow_env,
                    "OPENAI_API_KEY": "sk-fake",
                    "SC_OPENAI_MODEL": "gpt-5",
                },
                clear=False,
            ), mock.patch.object(
                self.sc_backend.importlib.util,
                "find_spec",
                return_value=spec_backed_openai.__spec__,
            ), mock.patch.dict(sys.modules, {"openai": spec_backed_openai}):
                out_path = Path(td) / "openai-api.json"
                rc_ok, trace_out, cmd_ok = self.sc_backend.run_llm_exec(
                    backend="openai-api",
                    root=TRACK_A_ROOT,
                    prompt="hello",
                    output_last_message=out_path,
                    timeout_sec=10,
                )
                self.assertEqual(0, rc_ok)
                self.assertEqual(["openai-api", "gpt-5"], cmd_ok)
                self.assertIn('"backend": "openai-api"', trace_out)
                self.assertEqual('{"ok":true}\n', out_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
