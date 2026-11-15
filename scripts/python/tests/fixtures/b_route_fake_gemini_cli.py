#!/usr/bin/env python3
"""Cross-platform Fake Gemini CLI fixture for Plane B and Plane A tests."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import time
from typing import Any
import uuid


def _extract_schema_from_system_md() -> dict[str, Any] | None:
    sys_md = str(os.environ.get("GEMINI_SYSTEM_MD") or "").strip()
    if not sys_md:
        return None
    path = Path(sys_md)
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    marker = "Requested JSON Schema:\n"
    idx = text.find(marker)
    if idx == -1:
        return None
    raw_schema = text[idx + len(marker) :].strip()
    if not raw_schema:
        return None
    return json.loads(raw_schema)


def _synthesize_from_schema(schema: dict[str, Any]) -> Any:
    if "const" in schema:
        return schema["const"]
    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = next((item for item in schema_type if item != "null"), schema_type[0])
    if schema_type == "object" or "properties" in schema:
        props = schema.get("properties") or {}
        required = list(schema.get("required") or props.keys())
        result: dict[str, Any] = {}
        for key in required:
            prop_schema = props.get(key, {"type": "string"})
            result[key] = _synthesize_from_schema(prop_schema)
        return result
    if schema_type == "array":
        min_items = int(schema.get("minItems") or 0)
        item_schema = schema.get("items") or {"type": "string"}
        return [_synthesize_from_schema(item_schema) for _ in range(min_items)]
    if schema_type == "boolean":
        return True
    if schema_type == "integer":
        return int(schema.get("minimum") or 1)
    if schema_type == "number":
        return float(schema.get("minimum") or 1.0)
    if schema_type == "null":
        return None
    min_len = int(schema.get("minLength") or 1)
    return "x" * max(1, min_len)


def _record_sandbox_inspection(argv: list[str]) -> None:
    log_path_raw = str(os.environ.get("FAKE_GEMINI_INSPECT_LOG") or "").strip()
    if not log_path_raw:
        return
    cwd = Path.cwd()
    gemini_home_raw = str(os.environ.get("GEMINI_CLI_HOME") or "")
    gemini_home = Path(gemini_home_raw) if gemini_home_raw else None
    dot_gemini = (gemini_home / ".gemini") if gemini_home is not None else None
    dot_files = sorted(p.name for p in dot_gemini.iterdir()) if dot_gemini and dot_gemini.is_dir() else []
    oauth_mode = None
    if dot_gemini is not None and (dot_gemini / "oauth_creds.json").is_file():
        oauth_mode = oct(stat.S_IMODE((dot_gemini / "oauth_creds.json").stat().st_mode))
    sys_settings = str(os.environ.get("GEMINI_CLI_SYSTEM_SETTINGS_PATH") or "")
    sys_md = str(os.environ.get("GEMINI_SYSTEM_MD") or "")
    scrubbed_probe_keys = (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_GENAI_USE_VERTEXAI",
        "GOOGLE_GENAI_USE_GCA",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "GEMINI_CLI_SYSTEM_DEFAULTS_PATH",
        "NODE_OPTIONS",
    )
    record = {
        "argv": list(argv),
        "cwd": str(cwd),
        "cwd_entries": sorted(p.name for p in cwd.iterdir()) if cwd.is_dir() else [],
        "env_home": str(os.environ.get("HOME") or ""),
        "gemini_cli_home": gemini_home_raw,
        "dot_gemini_files": dot_files,
        "oauth_creds_mode": oauth_mode,
        "system_settings_exists": bool(sys_settings and Path(sys_settings).is_file()),
        "system_md_exists": bool(sys_md and Path(sys_md).is_file()),
        "system_md_has_schema": _extract_schema_from_system_md() is not None,
        "scrubbed_env_present": sorted(k for k in scrubbed_probe_keys if k in os.environ),
    }
    log_path = Path(log_path_raw)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def _next_response_text() -> str:
    queue_file = str(os.environ.get("FAKE_GEMINI_RESPONSE_QUEUE_FILE") or "").strip()
    if queue_file:
        qpath = Path(queue_file)
        items = json.loads(qpath.read_text(encoding="utf-8"))
        if not isinstance(items, list) or not items:
            raise RuntimeError("FAKE_GEMINI_RESPONSE_QUEUE_FILE is exhausted")
        head = items.pop(0)
        qpath.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        return head if isinstance(head, str) else json.dumps(head, ensure_ascii=False, separators=(",", ":"))

    explicit_json = os.environ.get("FAKE_GEMINI_RESPONSE_JSON")
    if explicit_json is not None:
        return explicit_json

    schema = _extract_schema_from_system_md()
    if schema is not None:
        return json.dumps(_synthesize_from_schema(schema), ensure_ascii=False, separators=(",", ":"))
    return '{"ok":true}'


def main() -> int:
    raw_argv = list(sys.argv[1:])
    _record_sandbox_inspection(raw_argv)

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-m", "--model", default="auto")
    parser.add_argument("-o", "--output-format", dest="output_format", default="text")
    parser.add_argument("-p", "--prompt", default=None)
    parser.add_argument("--raw-output", action="store_true")
    parser.add_argument("--accept-raw-output-risk", action="store_true")
    parser.add_argument("--skip-trust", action="store_true")
    parser.add_argument("--approval-mode", default="default")
    args, unknown = parser.parse_known_args(raw_argv)
    if unknown:
        sys.stderr.write(f"unexpected arguments: {unknown}\n")
        return 2

    fault_mode = str(os.environ.get("FAKE_GEMINI_FAULT_MODE") or "").strip()
    if fault_mode == "hang_with_child":
        child = subprocess.Popen(
            [sys.executable, "-B", "-c", "import time; time.sleep(120)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        pid_file = str(os.environ.get("FAKE_GEMINI_PID_FILE") or "").strip()
        if pid_file:
            Path(pid_file).write_text(
                json.dumps({"gemini_pid": os.getpid(), "child_pid": child.pid}),
                encoding="utf-8",
            )
        time.sleep(120)
        return 0

    if fault_mode == "nonzero_exit":
        sys.stderr.write("simulated gemini cli fatal failure\n")
        return 1

    stdin_text = sys.stdin.buffer.read().decode("utf-8")
    user_prompt = args.prompt if args.prompt is not None else stdin_text
    if args.output_format == "stream-json" and args.prompt is not None:
        sys.stderr.write("Plane B must pass prompt via stdin without -p\n")
        return 2

    stderr_note = os.environ.get("FAKE_GEMINI_STDERR_TEXT")
    if stderr_note:
        sys.stderr.write(stderr_note)
        sys.stderr.flush()

    session_id = os.environ.get("FAKE_GEMINI_SESSION_ID")
    if session_id is None:
        session_id = "" if fault_mode == "empty_session_id" else str(uuid.uuid4())

    reported_model = args.model
    if fault_mode == "model_downgrade_auto":
        reported_model = "auto"
    elif fault_mode == "model_mismatch":
        reported_model = "gemini-2.5-flash"

    response_text = _next_response_text()
    if fault_mode == "markdown_fence":
        response_text = f"```json\n{response_text}\n```"

    if args.output_format == "json":
        payload = {
            "session_id": session_id,
            "response": response_text,
            "stats": {"models": {reported_model: {}}, "tools": {"totalCalls": 0}},
        }
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        return 0

    if args.output_format != "stream-json":
        sys.stdout.write(response_text + "\n")
        sys.stdout.flush()
        return 0

    def emit(event: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        sys.stdout.flush()

    if fault_mode != "missing_init":
        emit(
            {
                "type": "init",
                "timestamp": "2026-11-14T00:00:00.000Z",
                "session_id": session_id,
                "model": reported_model,
            }
        )

    echoed_user = user_prompt + (" " if fault_mode == "tamper_user_echo" else "")
    emit(
        {
            "type": "message",
            "timestamp": "2026-11-14T00:00:00.001Z",
            "role": "user",
            "content": echoed_user,
        }
    )

    if fault_mode == "warning_event":
        emit(
            {
                "type": "error",
                "timestamp": "2026-11-14T00:00:00.002Z",
                "severity": "warning",
                "message": "non-fatal deprecation notice",
            }
        )
    elif fault_mode == "error_event":
        emit(
            {
                "type": "error",
                "timestamp": "2026-11-14T00:00:00.002Z",
                "severity": "error",
                "message": "fatal stream error",
            }
        )
        return 0
    elif fault_mode == "tool_use":
        emit(
            {
                "type": "tool_use",
                "timestamp": "2026-11-14T00:00:00.002Z",
                "tool_name": "read_file",
                "tool_id": "call-1",
                "parameters": {"path": "README.md"},
            }
        )
    elif fault_mode == "tool_result":
        emit(
            {
                "type": "tool_result",
                "timestamp": "2026-11-14T00:00:00.002Z",
                "tool_id": "call-1",
                "status": "success",
                "output": "leaked",
            }
        )

    chunk_size = int(os.environ.get("FAKE_GEMINI_CHUNK_SIZE") or 0)
    if chunk_size > 0 and len(response_text) > chunk_size:
        chunks = [
            response_text[idx : idx + chunk_size]
            for idx in range(0, len(response_text), chunk_size)
        ]
    else:
        chunks = [response_text]

    for chunk in chunks:
        emit(
            {
                "type": "message",
                "timestamp": "2026-11-14T00:00:00.003Z",
                "role": "assistant",
                "content": chunk,
                "delta": True,
            }
        )

    tool_calls_stat = 1 if fault_mode == "nonzero_tool_calls" else 0
    emit(
        {
            "type": "result",
            "timestamp": "2026-11-14T00:00:00.004Z",
            "status": "success",
            "stats": {
                "total_tokens": 42,
                "input_tokens": 21,
                "output_tokens": 21,
                "cached": 0,
                "input": 21,
                "duration_ms": 12,
                "tool_calls": tool_calls_stat,
                "models": {reported_model: {"api": {"totalRequests": 1}}},
                "tools": {"totalCalls": tool_calls_stat},
            },
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
