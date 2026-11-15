"""One ephemeral official Gemini CLI stream-json turn; runtime configuration is not provider attestation."""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import queue
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any, Mapping

import _b_route_codec as codec
from _isolated_runner_registry import load_llm_routing, resolve_reasoning_effort

SOURCE = "gemini-cli-runtime-configuration"
POLICY = "official-gemini-cli-runtime-bound.v1"
MAX_TRANSCRIPT_BYTES = 32 * 1024 * 1024

FORBIDDEN_MODEL_ALIASES = frozenset(
    {
        "auto",
        "automatic",
        "default",
        "environment-default",
        "gemini-cli-default",
        "codex-cli-default",
    }
)

HEADER_KEYS = frozenset(
    {
        "direction",
        "event",
        "executable",
        "command",
        "model",
        "model_provider",
        "requested_reasoning_effort",
        "runtime_reasoning_effort",
        "isolated_settings_sha256",
        "system_settings_sha256",
        "system_md_sha256",
        "prompt_sha256",
        "schema_sha256",
        "model_tools",
    }
)

SCRUBBED_CHILD_ENV_KEYS = (
    "GEMINI_MODEL",
    "GEMINI_SANDBOX",
    "GEMINI_PROMPT",
    "GEMINI_SYSTEM_MD",
    "GEMINI_WRITE_SYSTEM_MD",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "ANTIGRAVITY_API_KEY",
    "GOOGLE_GENAI_USE_VERTEXAI",
    "GOOGLE_GENAI_USE_GCA",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
    "GEMINI_CLI_SYSTEM_DEFAULTS_PATH",
    "GEMINI_CLI_SYSTEM_SETTINGS_PATH",
    "NODE_OPTIONS",
)

AGY_SYSTEM_PROMPT_BOUNDARY = "\n===== NEWROGUE_SYSTEM_PROMPT_BOUNDARY =====\n"
AGY_ALLOWED_STEP_TYPES = frozenset(
    {
        "user_input",
        "agent_response",
        "finish",
        "thinking",
        "thought",
        "system_message",
    }
)


def digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def schema_digest(schema: dict[str, Any] | None) -> str | None:
    if schema is None:
        return None
    return digest(_canonical_bytes(schema))


def deterministic_turn_id(session_id: str, prompt_sha256: str) -> str:
    return digest(f"{session_id}:{prompt_sha256}".encode("utf-8"))


def _require(condition: bool, reason: str) -> None:
    if not condition:
        raise ValueError("gemini_cli_protocol_" + reason)


def _is_sha256_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and value.startswith("sha256:")
        and len(value) == 71
        and all(ch in "0123456789abcdef" for ch in value[7:])
    )


def _valid_exact_model(value: object) -> str:
    _require(
        isinstance(value, str)
        and bool(value)
        and not any(ch.isspace() for ch in value)
        and value.casefold() not in FORBIDDEN_MODEL_ALIASES,
        "runtime_identity_missing",
    )
    return str(value)


def _valid_session_id(value: object) -> str:
    _require(
        isinstance(value, str)
        and bool(value.strip())
        and not any(ch.isspace() for ch in value)
        and value.casefold() not in {"none", "null", "unknown", "synthetic"},
        "session_id_missing",
    )
    return str(value)


def requested_reasoning_effort(env: Mapping[str, str] | None = None) -> str | None:
    try:
        return resolve_reasoning_effort(env, default=None, allowed=("low", "high"))
    except ValueError as exc:
        raise ValueError("gemini_cli_protocol_" + str(exc)) from exc


def cli_flavor(executable: str) -> str:
    stem = Path(str(executable).replace("\\", "/")).stem.casefold()
    if stem in {"agy", "antigravity-cli"} or stem.startswith("agy_") or "_agy_" in stem:
        return "agy"
    return "gemini"


def gemini_command(
    executable: str,
    model: str,
    *,
    has_schema: bool = False,
) -> list[str]:
    exact_model = _valid_exact_model(model)
    if cli_flavor(executable) == "agy":
        args = [
            "--sandbox",
            "--disable-slash-commands",
            "--model",
            exact_model,
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
        ]
        if has_schema:
            args.extend(["--json-schema", "../schema.json"])
    else:
        args = [
            "-m",
            exact_model,
            "--output-format",
            "stream-json",
            "--raw-output",
            "--accept-raw-output-risk",
            "--skip-trust",
        ]
    if executable.casefold().endswith(".py"):
        return [sys.executable, "-B", executable, *args]
    return [executable, *args]


def find_gemini_executable(env: Mapping[str, str] | None = None) -> str:
    source_env = os.environ if env is None else env
    override = str(source_env.get("NEWROGUE_GEMINI_BIN") or "").strip()
    if override:
        override_path = Path(override)
        if override_path.is_file():
            return str(override_path.resolve())
        found_override = shutil.which(override, path=source_env.get("PATH"))
        if found_override:
            return found_override
        raise ValueError("Gemini CLI override in NEWROGUE_GEMINI_BIN does not exist")

    auth_dir = _locate_auth_source_dir(source_env)
    prefer_agy = bool(
        auth_dir is not None
        and (auth_dir / "antigravity-cli" / "antigravity-oauth-token").is_file()
    )

    path_arg = source_env.get("PATH")
    agy_names = ("agy.exe", "agy.cmd", "agy") if os.name == "nt" else ("agy",)
    gemini_names = ("gemini.cmd", "gemini") if os.name == "nt" else ("gemini", "gemini.cmd")
    ordered_names = (*agy_names, *gemini_names) if prefer_agy else (*gemini_names, *agy_names)
    for name in ordered_names:
        found = shutil.which(name, path=path_arg)
        if found:
            return found

    agy_homes: list[Path] = []
    gemini_homes: list[Path] = []
    for home_dir in _candidate_user_homes(source_env):
        if os.name == "nt":
            agy_homes.append(home_dir / "AppData" / "Local" / "agy" / "bin" / "agy.exe")
            agy_homes.append(home_dir / ".local" / "bin" / "agy.exe")
            gemini_homes.append(home_dir / "AppData" / "Roaming" / "npm" / "gemini.cmd")
            gemini_homes.append(home_dir / ".local" / "bin" / "gemini.cmd")
        else:
            agy_homes.append(home_dir / ".local" / "bin" / "agy")
            gemini_homes.append(home_dir / ".local" / "bin" / "gemini")
    ordered_candidates = [*agy_homes, *gemini_homes] if prefer_agy else [*gemini_homes, *agy_homes]
    for candidate in ordered_candidates:
        if candidate.is_file():
            return str(candidate)
    raise ValueError("Gemini CLI is unavailable; set NEWROGUE_GEMINI_BIN or add agy/gemini to PATH")


def _candidate_user_homes(env: Mapping[str, str] | None = None) -> list[Path]:
    source_env = os.environ if env is None else env
    homes: list[Path] = []
    seen: set[str] = set()

    def add(raw: str | Path | None) -> None:
        if not raw:
            return
        text = str(raw).strip()
        if not text:
            return
        p = Path(text)
        key = str(p)
        if key not in seen:
            seen.add(key)
            homes.append(p)

    add(source_env.get("HOME"))
    if os.name == "nt":
        add(source_env.get("USERPROFILE"))
    else:
        try:
            import pwd

            add(pwd.getpwuid(os.getuid()).pw_dir)
        except (ImportError, KeyError, AttributeError, OSError):
            pass
    try:
        add(Path.home())
    except RuntimeError:
        pass
    return homes


def _locate_auth_source_dir(env: Mapping[str, str] | None = None) -> Path | None:
    source_env = os.environ if env is None else env
    explicit = str(source_env.get("NEWROGUE_GEMINI_AUTH_SRC") or "").strip()
    if explicit:
        explicit_path = Path(explicit)
        dot_dir = explicit_path if explicit_path.name == ".gemini" else (explicit_path / ".gemini")
        return dot_dir if dot_dir.is_dir() else None
    for home_dir in _candidate_user_homes(source_env):
        dot_dir = home_dir / ".gemini"
        if dot_dir.is_dir():
            return dot_dir
    return None


def build_isolated_settings(runtime_reasoning_effort: str) -> dict[str, Any]:
    _require(runtime_reasoning_effort in ("low", "high"), "unsupported_runtime_reasoning_effort")
    thinking_budget = 24576 if runtime_reasoning_effort == "high" else 1024
    thinking_level = "HIGH" if runtime_reasoning_effort == "high" else "LOW"
    return {
        "security": {
            "auth": {
                "selectedType": "oauth-personal",
            },
        },
        "tools": {
            "core": [],
            "allowed": [],
        },
        "mcpServers": {},
        "admin": {
            "extensions": {"enabled": False},
            "mcp": {"enabled": False},
        },
        "context": {
            "fileName": [],
        },
        "general": {
            "checkpointing": {"enabled": False},
        },
        "modelConfigs": {
            "customOverrides": [
                {
                    "match": {"model": "chat-base-2.5"},
                    "modelConfig": {
                        "generateContentConfig": {
                            "thinkingConfig": {
                                "thinkingBudget": thinking_budget,
                            },
                        },
                    },
                },
                {
                    "match": {"model": "chat-base-3"},
                    "modelConfig": {
                        "generateContentConfig": {
                            "thinkingConfig": {
                                "thinkingLevel": thinking_level,
                            },
                        },
                    },
                },
            ],
        },
    }


def build_system_markdown(system_instruction: str, schema: dict[str, Any] | None) -> bytes:
    base = system_instruction.strip()
    _require(bool(base), "system_instruction_missing")
    if schema is None:
        return (base + "\n").encode("utf-8")
    schema_json = _canonical_bytes(schema).decode("utf-8")
    return (base + "\n\nRequested JSON Schema:\n" + schema_json + "\n").encode("utf-8")


def replay(
    raw: bytes,
    *,
    prompt: str | None = None,
    schema: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    try:
        return _replay(raw, prompt=prompt, schema=schema)
    except ValueError:
        raise
    except (KeyError, TypeError, AttributeError, UnicodeError) as error:
        raise ValueError("gemini_cli_protocol_invalid_transcript") from error


def _replay(
    raw: bytes,
    *,
    prompt: str | None = None,
    schema: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    _require(0 < len(raw) <= MAX_TRANSCRIPT_BYTES, "invalid_transcript_size")
    lines = [line for line in raw.decode("utf-8").splitlines() if line]
    _require(len(lines) >= 2, "incomplete_transcript")
    records = [codec.strict_json_loads(line.encode("utf-8")) for line in lines]
    _require(all(isinstance(record, dict) for record in records), "invalid_transcript_record")

    header = records[0]
    _require(
        set(header) == HEADER_KEYS
        and header.get("direction") == "host"
        and header.get("event") == "gemini_cli_launch",
        "invalid_host_header",
    )
    expected_model = _valid_exact_model(header.get("model"))
    executable_hdr = header.get("executable")
    _require(
        isinstance(executable_hdr, str) and bool(executable_hdr.strip()),
        "invalid_host_executable",
    )
    hdr_schema_sha = header.get("schema_sha256")
    _require(hdr_schema_sha is None or _is_sha256_digest(hdr_schema_sha), "invalid_schema_sha256")
    is_agy = cli_flavor(executable_hdr) == "agy"
    cmd_hdr = header.get("command")
    _require(
        isinstance(cmd_hdr, list)
        and cmd_hdr
        == gemini_command(
            executable_hdr,
            expected_model,
            has_schema=(hdr_schema_sha is not None),
        ),
        "invalid_launch_command",
    )
    _require(header.get("model_provider") == "google", "invalid_model_provider")
    _require(header.get("model_tools") == [], "header_tools_non_empty")
    req_effort = header.get("requested_reasoning_effort")
    run_effort = header.get("runtime_reasoning_effort")
    _require(req_effort in (None, "low", "high"), "unsupported_requested_reasoning_effort")
    _require(run_effort in ("low", "high"), "unsupported_runtime_reasoning_effort")
    if req_effort is not None:
        _require(run_effort == req_effort, "requested_reasoning_effort_mismatch")
    for digest_key in (
        "isolated_settings_sha256",
        "system_settings_sha256",
        "system_md_sha256",
        "prompt_sha256",
    ):
        _require(_is_sha256_digest(header.get(digest_key)), f"invalid_{digest_key}")
    expected_settings_sha = digest(_canonical_bytes(build_isolated_settings(run_effort)) + b"\n")
    _require(
        header["isolated_settings_sha256"] == expected_settings_sha,
        "isolated_settings_sha256_mismatch",
    )
    _require(
        header["system_settings_sha256"] == expected_settings_sha,
        "system_settings_sha256_mismatch",
    )

    stdin_events: list[dict[str, Any]] = []
    stdout_events: list[dict[str, Any]] = []
    exit_records: list[dict[str, Any]] = []
    for idx, record in enumerate(records[1:], start=1):
        direction = record.get("direction")
        if direction == "stdin":
            _require(is_agy and idx == 1 and not stdin_events and not stdout_events and not exit_records, "invalid_stdin_position")
            _require(set(record) == {"direction", "line"} and isinstance(record.get("line"), dict), "invalid_stdin_record")
            stdin_events.append(record["line"])
        elif direction == "stdout":
            _require(not exit_records, "stdout_after_exit")
            _require(set(record) == {"direction", "line"} and isinstance(record.get("line"), dict), "invalid_stdout_record")
            stdout_events.append(record["line"])
        elif direction == "exit":
            _require(idx == len(records) - 1 and not exit_records, "invalid_exit_position")
            _require(
                set(record) == {"direction", "returncode", "stderr_sha256"}
                and type(record.get("returncode")) is int
                and record["returncode"] == 0
                and _is_sha256_digest(record.get("stderr_sha256")),
                "nonzero_or_invalid_exit_record",
            )
            exit_records.append(record)
        else:
            raise ValueError("gemini_cli_protocol_invalid_direction")

    _require(len(exit_records) == 1, "missing_exit_record")
    _require(len(stdout_events) >= 3, "incomplete_stream_events")

    if is_agy:
        _require(len(stdin_events) == 1, "missing_agy_stdin_record")
        stdin_line = stdin_events[0]
        _require(
            set(stdin_line) == {"event", "message"}
            and stdin_line.get("event") == "user"
            and isinstance(stdin_line.get("message"), dict)
            and set(stdin_line["message"]) == {"content"}
            and isinstance(stdin_line["message"].get("content"), str),
            "invalid_agy_stdin_payload",
        )
        sys_part, sep, observed_prompt = stdin_line["message"]["content"].partition(
            AGY_SYSTEM_PROMPT_BOUNDARY
        )
        _require(bool(sep), "missing_agy_system_boundary")
        _require(
            digest(sys_part.encode("utf-8")) == header["system_md_sha256"],
            "system_md_sha256_mismatch",
        )

        agy_session_id: str | None = None
        saw_user_step = False
        agy_chunks: list[str] = []
        agy_result: dict[str, Any] | None = None
        for event_idx, event in enumerate(stdout_events):
            ev_name = event.get("event")
            if ev_name == "init":
                _require(event_idx == 0 and agy_session_id is None, "invalid_or_duplicate_init")
                agy_session_id = _valid_session_id(event.get("conversation_id"))
                init_meta = event.get("init")
                _require(isinstance(init_meta, dict), "invalid_agy_init_payload")
                init_model = _valid_exact_model(init_meta.get("model"))
                _require(init_model == expected_model, "init_model_mismatch")
                _require(
                    init_meta.get("permission_mode") == "request-review",
                    "unsafe_agy_permission_mode",
                )
            elif ev_name == "step_update":
                _require(agy_session_id is not None and agy_result is None, "step_outside_turn")
                su = event.get("step_update")
                _require(isinstance(su, dict), "invalid_agy_step_update")
                _require(
                    su.get("conversation_id") == agy_session_id,
                    "step_conversation_id_mismatch",
                )
                step_type = su.get("step_type")
                _require(
                    isinstance(step_type, str) and step_type in AGY_ALLOWED_STEP_TYPES,
                    "model_tools_observed",
                )
                if step_type == "user_input":
                    saw_user_step = True
                elif step_type == "agent_response":
                    delta = su.get("text_delta")
                    if isinstance(delta, str):
                        agy_chunks.append(delta)
            elif ev_name == "error":
                raise ValueError("gemini_cli_protocol_error_event")
            elif ev_name == "result":
                _require(
                    event_idx == len(stdout_events) - 1
                    and agy_result is None
                    and agy_session_id is not None
                    and saw_user_step,
                    "invalid_or_duplicate_result",
                )
                res_obj = event.get("result")
                _require(isinstance(res_obj, dict), "invalid_agy_result_payload")
                _require(
                    res_obj.get("conversation_id") == agy_session_id,
                    "result_conversation_id_mismatch",
                )
                _require(res_obj.get("status") == "SUCCESS", "result_status_not_success")
                max_agy_turns = 3 if hdr_schema_sha is not None else 1
                _require(
                    type(res_obj.get("num_turns")) is int
                    and 1 <= res_obj["num_turns"] <= max_agy_turns,
                    "result_num_turns_invalid",
                )
                agy_result = res_obj
            else:
                raise ValueError(f"gemini_cli_protocol_unexpected_event:{ev_name}")

        _require(
            agy_session_id is not None and saw_user_step and agy_result is not None,
            "incomplete_turn_events",
        )
        session_id = agy_session_id
        if hdr_schema_sha is not None and agy_result.get("structured_output") is not None:
            output_text = _canonical_bytes(agy_result["structured_output"]).decode("utf-8")
        else:
            res_text = agy_result.get("response")
            output_text = (
                res_text
                if isinstance(res_text, str) and res_text.strip()
                else "".join(agy_chunks)
            )
    else:
        _require(not stdin_events, "unexpected_stdin_record")
        init_events: list[dict[str, Any]] = []
        user_messages: list[str] = []
        assistant_chunks: list[str] = []
        result_events: list[dict[str, Any]] = []

        for event_idx, event in enumerate(stdout_events):
            event_type = event.get("type")
            if event_type == "init":
                _require(event_idx == 0 and not init_events, "invalid_or_duplicate_init")
                session_id_val = _valid_session_id(event.get("session_id"))
                init_model = _valid_exact_model(event.get("model"))
                _require(init_model == expected_model, "init_model_mismatch")
                init_events.append({"session_id": session_id_val, "model": init_model})
            elif event_type == "message":
                _require(bool(init_events) and not result_events, "message_outside_turn")
                role = event.get("role")
                content = event.get("content")
                _require(isinstance(content, str), "invalid_message_content")
                if role == "user":
                    _require(not user_messages and not assistant_chunks, "duplicate_or_late_user_message")
                    user_messages.append(content)
                elif role == "assistant":
                    _require(len(user_messages) == 1, "assistant_before_user_message")
                    assistant_chunks.append(content)
                else:
                    raise ValueError("gemini_cli_protocol_unexpected_message_role")
            elif event_type in {"tool_use", "tool_result"}:
                raise ValueError("gemini_cli_protocol_model_tools_observed")
            elif event_type == "error":
                severity = event.get("severity")
                if severity == "error" or severity != "warning":
                    raise ValueError("gemini_cli_protocol_error_event")
            elif event_type == "result":
                _require(
                    event_idx == len(stdout_events) - 1 and not result_events and len(init_events) == 1 and len(user_messages) == 1,
                    "invalid_or_duplicate_result",
                )
                _require(event.get("status") == "success", "result_status_not_success")
                stats = event.get("stats")
                _require(isinstance(stats, dict), "result_stats_missing")
                tool_calls = stats.get("tool_calls", 0)
                _require(type(tool_calls) is int and tool_calls == 0, "result_tool_calls_observed")
                tools_meta = stats.get("tools")
                if isinstance(tools_meta, dict):
                    total_calls = tools_meta.get("totalCalls", 0)
                    _require(type(total_calls) is int and total_calls == 0, "result_tools_total_calls_observed")
                result_events.append(event)
            else:
                raise ValueError(f"gemini_cli_protocol_unexpected_event:{event_type}")

        _require(len(init_events) == 1 and len(user_messages) == 1 and len(result_events) == 1, "incomplete_turn_events")
        observed_prompt = user_messages[0]
        output_text = "".join(assistant_chunks)
        session_id = init_events[0]["session_id"]

    observed_prompt_sha = digest(observed_prompt.encode("utf-8"))
    _require(observed_prompt_sha == header["prompt_sha256"], "prompt_sha256_mismatch")
    if prompt is not None:
        _require(observed_prompt == prompt, "user_prompt_mismatch")
        _require(digest(prompt.encode("utf-8")) == header["prompt_sha256"], "expected_prompt_sha256_mismatch")

    stripped = output_text.strip()
    _require(bool(stripped), "empty_assistant_output")
    _require(
        not stripped.startswith("```")
        and not stripped.startswith("~~~")
        and not stripped.endswith("```")
        and not stripped.endswith("~~~"),
        "markdown_fence_forbidden",
    )
    try:
        parsed_output = codec.strict_json_loads(output_text.encode("utf-8"))
    except ValueError as exc:
        raise ValueError(f"gemini_cli_protocol_invalid_json_output:{exc}") from exc

    if schema is not None:
        expected_schema_sha = schema_digest(schema)
        _require(header["schema_sha256"] == expected_schema_sha, "schema_sha256_mismatch")
        import jsonschema  # type: ignore

        try:
            jsonschema.Draft202012Validator(schema).validate(parsed_output)
        except (jsonschema.ValidationError, jsonschema.SchemaError) as exc:
            raise ValueError(f"gemini_cli_protocol_schema_validation_failed:{exc.message}") from exc

    turn_id = deterministic_turn_id(session_id, observed_prompt_sha)
    proof: dict[str, Any] = {
        "source": SOURCE,
        "evidence_policy": POLICY,
        "model": expected_model,
        "model_provider": "google",
        "session_id": session_id,
        "thread_id": session_id,
        "turn_id": turn_id,
        "runtime_identity_verified": True,
        "model_identity_scope": "runtime_configuration",
        "provider_reported_model": None,
        "provider_identity_verified": False,
        "provider_dispatch_count": "unknown",
        "model_tools": [],
        "requested_reasoning_effort": req_effort,
        "runtime_reasoning_effort": run_effort,
        "isolated_settings_sha256": header["isolated_settings_sha256"],
        "system_settings_sha256": header["system_settings_sha256"],
        "system_md_sha256": header["system_md_sha256"],
        "prompt_sha256": observed_prompt_sha,
        "schema_sha256": header["schema_sha256"],
        "output_sha256": digest(output_text.encode("utf-8")),
        "protocol_sha256": digest(raw),
        "protocol_jsonl_base64": base64.b64encode(raw).decode("ascii"),
    }
    return output_text, proof


def _posix_descendant_pids(root_pid: int) -> list[int]:
    children_map: dict[int, list[int]] = {}
    proc_root = Path("/proc")
    if proc_root.is_dir():
        for entry in proc_root.iterdir():
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            try:
                stat_text = (entry / "stat").read_text(encoding="ascii", errors="ignore")
                rparen = stat_text.rfind(")")
                if rparen == -1:
                    continue
                fields = stat_text[rparen + 2 :].split()
                ppid = int(fields[1])
                children_map.setdefault(ppid, []).append(pid)
            except (OSError, ValueError, IndexError):
                continue
    descendants: list[int] = []
    stack = list(children_map.get(root_pid, ()))
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if current in seen or current == os.getpid():
            continue
        seen.add(current)
        descendants.append(current)
        stack.extend(children_map.get(current, ()))
    return descendants


def _terminate_child_tree(proc: subprocess.Popen[Any], *, own_session: bool) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=5,
            )
        except (OSError, subprocess.SubprocessError):
            pass
        if proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
        return
    if own_session:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
            return
        except OSError:
            pass
    descendants = _posix_descendant_pids(proc.pid)
    for child_pid in reversed(descendants):
        try:
            os.kill(child_pid, signal.SIGKILL)
        except OSError:
            pass
    try:
        proc.kill()
    except OSError:
        pass


def _cleanup_temp_dir_safely(temp_dir: tempfile.TemporaryDirectory[str]) -> None:
    sandbox_path = Path(temp_dir.name)
    for attempt in range(3):
        try:
            temp_dir.cleanup()
            return
        except PermissionError:
            if attempt < 2:
                time.sleep(0.05 * (attempt + 1))
        except OSError:
            return
    if sandbox_path.exists():
        shutil.rmtree(sandbox_path, ignore_errors=True)


def _copy_oauth_credentials(
    gemini_dot_dir: Path,
    *,
    env: Mapping[str, str] | None = None,
    include_agy: bool = False,
) -> None:
    auth_src = _locate_auth_source_dir(env)
    if auth_src is not None:
        for filename in ("oauth_creds.json", "google_accounts.json"):
            src_file = auth_src / filename
            if src_file.is_file():
                dst_file = gemini_dot_dir / filename
                data = src_file.read_bytes()
                dst_file.write_bytes(data)
                try:
                    os.chmod(dst_file, 0o600)
                except OSError:
                    pass
        if include_agy:
            agy_tok_src = auth_src / "antigravity-cli" / "antigravity-oauth-token"
            if agy_tok_src.is_file():
                agy_dir = gemini_dot_dir / "antigravity-cli"
                agy_dir.mkdir(parents=True, exist_ok=True)
                agy_tok_dst = agy_dir / "antigravity-oauth-token"
                agy_tok_dst.write_bytes(agy_tok_src.read_bytes())
                try:
                    os.chmod(agy_tok_dst, 0o600)
                except OSError:
                    pass
    if include_agy:
        agy_dir = gemini_dot_dir / "antigravity-cli"
        agy_dir.mkdir(parents=True, exist_ok=True)
        (agy_dir / "settings.json").write_bytes(
            _canonical_bytes({"toolPermission": "request-review"}) + b"\n"
        )


def _build_child_env(
    *,
    gemini_home: Path,
    system_settings_path: Path,
    system_md_path: Path,
    executable: str,
    base_env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    raw_env = os.environ if base_env is None else base_env
    scrub_upper = {key.upper() for key in SCRUBBED_CHILD_ENV_KEYS}
    source_env = {
        key: val
        for key, val in raw_env.items()
        if key not in SCRUBBED_CHILD_ENV_KEYS and key.upper() not in scrub_upper
    }

    path_entries = [p for p in str(source_env.get("PATH") or "").split(os.pathsep) if p]
    exe_parent = str(Path(executable).resolve().parent)
    if exe_parent and exe_parent not in path_entries:
        path_entries.insert(0, exe_parent)
    if os.name != "nt":
        for std_dir in ("/usr/local/bin", "/usr/bin", "/bin"):
            if Path(std_dir).is_dir() and std_dir not in path_entries:
                path_entries.append(std_dir)
    source_env["PATH"] = os.pathsep.join(path_entries)
    source_env["HOME"] = str(gemini_home)
    source_env["USERPROFILE"] = str(gemini_home)
    source_env["GEMINI_CLI_HOME"] = str(gemini_home)
    source_env["GEMINI_CLI_SYSTEM_SETTINGS_PATH"] = str(system_settings_path)
    source_env["GEMINI_SYSTEM_MD"] = str(system_md_path)
    source_env["NO_COLOR"] = "1"
    source_env["CI"] = "1"
    source_env["PYTHONDONTWRITEBYTECODE"] = "1"
    return source_env


def run_request(
    executable: str,
    *,
    prompt: str,
    schema: dict[str, Any] | None,
    timeout_sec: int,
    model: str | None = None,
    system_instruction: str | None = None,
    default_reasoning_effort: str = "high",
    journal_path: Path | None = None,
    root: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Execute one physical zero-tools ephemeral Gemini/Antigravity CLI turn outside workspace."""
    from _planning_skill_common import _stop_owned_pipe_workers

    source_env = os.environ if env is None else env
    if model is None or system_instruction is None:
        routing = load_llm_routing(root, env=source_env)
        gemini_cfg = routing["plane_b"]["runners"]["gemini"]
        if model is None:
            model = str(gemini_cfg["model"])
        if system_instruction is None:
            system_instruction = str(gemini_cfg["system_instruction"])
        default_reasoning_effort = str(gemini_cfg.get("reasoning_effort") or default_reasoning_effort)

    exact_model = _valid_exact_model(model)
    is_agy = cli_flavor(executable) == "agy"
    cmd = gemini_command(executable, exact_model, has_schema=(schema is not None))
    req_effort = requested_reasoning_effort(source_env)
    run_effort = req_effort if req_effort is not None else default_reasoning_effort
    _require(run_effort in ("low", "high"), "unsupported_runtime_reasoning_effort")

    settings_obj = build_isolated_settings(run_effort)
    settings_bytes = _canonical_bytes(settings_obj) + b"\n"
    isolated_settings_sha = digest(settings_bytes)
    system_settings_sha = digest(settings_bytes)
    system_md_bytes = build_system_markdown(system_instruction, schema)
    system_md_text = system_md_bytes.decode("utf-8")
    if is_agy:
        _require(
            AGY_SYSTEM_PROMPT_BOUNDARY not in system_md_text,
            "system_instruction_boundary_collision",
        )
    system_md_sha = digest(system_md_bytes)
    prompt_bytes = prompt.encode("utf-8")
    prompt_sha = digest(prompt_bytes)
    expected_schema_sha = schema_digest(schema)

    records: list[dict[str, Any]] = []
    stderr_chunks: list[str] = []
    incoming: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=32)
    stopping = threading.Event()
    transcript_bytes = [0]
    journal = None

    def append_record(row: dict[str, Any]) -> None:
        encoded_line = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        transcript_bytes[0] += len(encoded_line.encode("utf-8"))
        if transcript_bytes[0] > MAX_TRANSCRIPT_BYTES:
            raise ValueError("gemini_cli_protocol_transcript_budget_exceeded")
        records.append(row)
        if journal is not None:
            journal.write(encoded_line)
            journal.flush()

    if journal_path is not None:
        journal_path.parent.mkdir(parents=True, exist_ok=True)
        journal = journal_path.open("w", encoding="utf-8", newline="\n")

    header_record = {
        "direction": "host",
        "event": "gemini_cli_launch",
        "executable": executable,
        "command": cmd,
        "model": exact_model,
        "model_provider": "google",
        "requested_reasoning_effort": req_effort,
        "runtime_reasoning_effort": run_effort,
        "isolated_settings_sha256": isolated_settings_sha,
        "system_settings_sha256": system_settings_sha,
        "system_md_sha256": system_md_sha,
        "prompt_sha256": prompt_sha,
        "schema_sha256": expected_schema_sha,
        "model_tools": [],
    }

    proc: subprocess.Popen[Any] | None = None
    workers: list[threading.Thread] = []
    already_isolated_group = (
        os.name != "nt" and hasattr(os, "getpgrp") and os.getpgrp() == os.getpid()
    )
    own_session = os.name != "nt" and not already_isolated_group
    temp_sandbox: tempfile.TemporaryDirectory[str] | None = None

    try:
        temp_sandbox = tempfile.TemporaryDirectory(prefix="newrouge-gemini-no-tools-")
        try:
            append_record(header_record)
            sandbox_dir = Path(temp_sandbox.name).resolve()
            empty_cwd = sandbox_dir / "empty_cwd"
            empty_cwd.mkdir(parents=True, exist_ok=True)
            gemini_home = sandbox_dir / "gemini_home"
            dot_gemini = gemini_home / ".gemini"
            dot_gemini.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(dot_gemini, 0o700)
            except OSError:
                pass

            _copy_oauth_credentials(dot_gemini, env=source_env, include_agy=is_agy)

            isolated_settings_path = dot_gemini / "settings.json"
            system_settings_path = sandbox_dir / "system-settings.json"
            system_md_path = sandbox_dir / "system.md"
            req_file_path = sandbox_dir / "request.stdin"

            isolated_settings_path.write_bytes(settings_bytes)
            system_settings_path.write_bytes(settings_bytes)
            system_md_path.write_bytes(system_md_bytes)
            if is_agy:
                if schema is not None:
                    (sandbox_dir / "schema.json").write_bytes(_canonical_bytes(schema) + b"\n")
                agy_stdin_obj = {
                    "event": "user",
                    "message": {"content": system_md_text + AGY_SYSTEM_PROMPT_BOUNDARY + prompt},
                }
                append_record({"direction": "stdin", "line": agy_stdin_obj})
                req_file_path.write_bytes(
                    (
                        json.dumps(agy_stdin_obj, ensure_ascii=False, separators=(",", ":"))
                        + "\n"
                    ).encode("utf-8")
                )
            else:
                req_file_path.write_bytes(prompt_bytes)

            child_env = _build_child_env(
                gemini_home=gemini_home,
                system_settings_path=system_settings_path,
                system_md_path=system_md_path,
                executable=executable,
                base_env=source_env,
            )

            deadline = time.monotonic() + max(1, int(timeout_sec))
            with req_file_path.open("rb") as req_stdin:
                proc = subprocess.Popen(
                    cmd,
                    cwd=str(empty_cwd),
                    env=child_env,
                    stdin=req_stdin,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="strict",
                    start_new_session=own_session,
                )

            def push_queue(item: tuple[str, Any]) -> bool:
                while not stopping.is_set():
                    try:
                        incoming.put(item, timeout=0.05)
                        return True
                    except queue.Full:
                        continue
                return False

            def read_stdout() -> None:
                assert proc is not None and proc.stdout is not None
                try:
                    for raw_line in proc.stdout:
                        if stopping.is_set():
                            break
                        if len(raw_line.encode("utf-8")) > MAX_TRANSCRIPT_BYTES:
                            push_queue(("error", ValueError("gemini_cli_protocol_line_too_large")))
                            return
                        stripped_line = raw_line.strip()
                        if not stripped_line:
                            continue
                        try:
                            parsed = codec.strict_json_loads(stripped_line.encode("utf-8"))
                        except ValueError as exc:
                            push_queue(("error", ValueError(f"gemini_cli_protocol_non_json_stdout:{exc}")))
                            return
                        if not isinstance(parsed, dict):
                            push_queue(("error", ValueError("gemini_cli_protocol_non_object_stdout")))
                            return
                        if not push_queue(("stdout", parsed)):
                            return
                    push_queue(("eof", None))
                except (OSError, UnicodeError, ValueError) as exc:
                    push_queue(("error", ValueError(f"gemini_cli_protocol_stdout_read_failed:{exc}")))

            def read_stderr() -> None:
                assert proc is not None and proc.stderr is not None
                retained = 0
                try:
                    while not stopping.is_set():
                        chunk = proc.stderr.read(4096)
                        if not chunk:
                            break
                        if retained < 262144:
                            piece = chunk[: 262144 - retained]
                            stderr_chunks.append(piece)
                            retained += len(piece)
                except OSError:
                    pass

            workers = [
                threading.Thread(target=read_stdout, daemon=True, name="gemini-cli-stdout"),
                threading.Thread(target=read_stderr, daemon=True, name="gemini-cli-stderr"),
            ]
            for worker in workers:
                worker.start()

            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Gemini CLI timed out waiting for stream-json completion")
                try:
                    kind, payload = incoming.get(timeout=min(0.25, remaining))
                except queue.Empty:
                    continue
                if kind == "error":
                    raise payload
                if kind == "eof":
                    break
                append_record({"direction": "stdout", "line": payload})
                if is_agy:
                    agy_ev = payload.get("event")
                    if agy_ev == "init":
                        init_meta = payload.get("init")
                        init_model = init_meta.get("model") if isinstance(init_meta, dict) else None
                        if init_model != exact_model:
                            raise ValueError("gemini_cli_protocol_init_model_mismatch")
                    elif agy_ev == "step_update":
                        su = payload.get("step_update")
                        st = su.get("step_type") if isinstance(su, dict) else None
                        if not isinstance(st, str) or st not in AGY_ALLOWED_STEP_TYPES:
                            raise ValueError("gemini_cli_protocol_model_tools_observed")
                    elif agy_ev == "error":
                        raise ValueError("gemini_cli_protocol_error_event")
                else:
                    event_type = payload.get("type")
                    if event_type in {"tool_use", "tool_result"}:
                        raise ValueError("gemini_cli_protocol_model_tools_observed")
                    if event_type == "error" and payload.get("severity") != "warning":
                        raise ValueError("gemini_cli_protocol_error_event")

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("Gemini CLI timed out waiting for process exit")
            try:
                proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired as exc:
                raise TimeoutError("Gemini CLI did not exit after stream EOF") from exc

            for worker in workers:
                rem_worker = max(0.05, min(0.5, deadline - time.monotonic()))
                worker.join(timeout=rem_worker)

            stderr_text = "".join(stderr_chunks)
            _require(
                proc.returncode == 0,
                "process_failed:rc=" + str(proc.returncode) + ":" + stderr_text[-1000:],
            )
            append_record(
                {
                    "direction": "exit",
                    "returncode": int(proc.returncode),
                    "stderr_sha256": digest(stderr_text.encode("utf-8")),
                }
            )
            raw_transcript = (
                "\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in records)
                + "\n"
            ).encode("utf-8")
            return replay(raw_transcript, prompt=prompt, schema=schema)
        finally:
            stopping.set()
            if proc is not None:
                try:
                    _terminate_child_tree(proc, own_session=own_session)
                except BaseException:
                    pass
                try:
                    _stop_owned_pipe_workers(workers, stopping)
                except BaseException:
                    pass
                try:
                    proc.wait(timeout=0.5)
                except BaseException:
                    pass
                if not any(w.is_alive() for w in workers):
                    for stream_name in ("stdout", "stderr"):
                        stream = getattr(proc, stream_name, None)
                        if stream is not None and not stream.closed:
                            try:
                                stream.close()
                            except OSError:
                                pass
    finally:
        if temp_sandbox is not None:
            try:
                _cleanup_temp_dir_safely(temp_sandbox)
            except BaseException:
                pass
        if journal is not None:
            try:
                journal.close()
            except OSError:
                pass
        if journal_path is not None:
            stderr_sidecar = journal_path.with_suffix(".stderr.txt")
            try:
                stderr_sidecar.write_text("".join(stderr_chunks), encoding="utf-8")
            except OSError:
                pass


run = run_request
