#!/usr/bin/env python3
"""No-tools GitHub Copilot CLI runner for one prepared model-visible workspace."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from openai_isolated_model_runner import DEFAULT_MAX_BYTES, workspace_payload

SCHEMA = "newrouge.isolated-model-runner.v1"


def model_name() -> str:
    return str(
        os.environ.get("SC_COPILOT_MODEL")
        or os.environ.get("COPILOT_MODEL")
        or "auto"
    ).strip() or "auto"


def parse_copilot_json_stream(raw: str) -> tuple[str, str]:
    messages: list[str] = []
    actual_model = ""
    execution_models: set[str] = set()

    def identity(value: object) -> str:
        name = str(value or "").strip()
        return "" if name.lower() in {"auto", "automatic"} else name

    for line in raw.splitlines():
        text = line.strip()
        if not text.startswith("{"):
            continue
        try:
            event = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        event_type = str(event.get("type") or "")
        data = event.get("data")
        # https://github.com/github/copilot-sdk/blob/main/docs/features/streaming-events.md
        # Usage reports executed calls; shutdown currentModel only reports selection.
        if event_type == "assistant.usage" and isinstance(data, dict):
            model = identity(data.get("model"))
            if model:
                execution_models.add(model)
        if event_type == "session.shutdown" and isinstance(data, dict):
            metrics = data.get("modelMetrics")
            if isinstance(metrics, dict):
                for name, metric in metrics.items():
                    if not isinstance(metric, dict):
                        continue
                    requests = metric.get("requests") or {}
                    usage = metric.get("usage") or {}
                    counts = [requests.get("count", 0), usage.get("inputTokens", 0), usage.get("outputTokens", 0)]
                    if any(isinstance(value, (int, float)) and value > 0 for value in counts):
                        model = identity(name)
                        if model:
                            execution_models.add(model)
        if event_type == "assistant.message" and isinstance(data, dict):
            tool_requests = data.get("toolRequests")
            if isinstance(tool_requests, list) and tool_requests:
                raise ValueError("Copilot acceptance runner forbids model tool requests")
            content = str(data.get("content") or "").strip()
            phase = str(data.get("phase") or "response").strip().lower()
            if content and phase != "thinking":
                messages.append(content)
        if event_type == "session.usage_checkpoint" and isinstance(data, dict):
            last = identity(data.get("lastActiveModel"))
            if last:
                actual_model = last
    if not messages:
        raise ValueError("Copilot JSON stream contained no assistant.message response")
    if len(execution_models) > 1:
        raise ValueError("Copilot JSON stream exposes mixed actual models: " + ",".join(sorted(execution_models)))
    if execution_models:
        actual_model = next(iter(execution_models))
    if not actual_model:
        raise ValueError("Copilot JSON stream did not expose the actual model identity")
    return messages[-1], actual_model


def description() -> dict[str, object]:
    return {
        "schema_version": SCHEMA,
        "filesystem_scope": "workspace_only",
        "fresh_session_per_invocation": True,
        "can_read_outside_workspace": False,
        "model": model_name(),
        "transport": "github-copilot-cli-prompt-only",
        "model_tools": [],
        "request_accounting": "copilot-cli-invocation-only",
        "supports_batched_session": False,
    }


def runtime_model_events(runtime_home: Path) -> tuple[str, list[dict[str, object]]]:
    """Read model events only from this invocation's newly created runtime."""
    paths = sorted((runtime_home / "session-state").glob("*/events.jsonl"))
    if len(paths) > 1:
        raise ValueError("Copilot isolated invocation created multiple session event logs")
    events = []
    shapes = []
    for path in paths:
        if not path.resolve().is_relative_to(runtime_home.resolve()):
            raise ValueError("Copilot session event path escapes this invocation's runtime")
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            data = event.get("data")
            shapes.append({"type": event.get("type"), "keys": sorted(event),
                "data_keys": sorted(data) if isinstance(data, dict) else []})
            if event.get("type") in {"assistant.usage", "session.usage_checkpoint", "session.shutdown"}:
                events.append({"type": event["type"], "data": data})
    return "\n".join(json.dumps(event) for event in events), shapes


def run(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    prompt_path = Path(args.prompt_file).resolve()
    output_path = Path(args.output).resolve()
    if not workspace.is_dir():
        raise ValueError("workspace directory is missing")

    batch_index_path = workspace / "analysis-input/model-batches/batch-index.json"
    if batch_index_path.is_file():
        batch_index = json.loads(batch_index_path.read_text(encoding="utf-8"))
        batch_count = int(batch_index.get("batch_count") or 0)
        if batch_count > 1:
            raise ValueError(
                "Copilot isolated runner does not support multi-batch continuation; "
                "use a runner with supports_batched_session=true"
            )

    payload = workspace_payload(
        workspace,
        prompt_path=prompt_path,
        output_path=output_path,
        max_bytes=args.max_bytes,
    )
    executable = shutil.which("copilot")
    if not executable:
        raise ValueError("GitHub Copilot CLI is unavailable")

    token = str(
        os.environ.get("COPILOT_GITHUB_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or ""
    ).strip()
    if not token:
        raise ValueError("GITHUB_TOKEN/COPILOT_GITHUB_TOKEN is unavailable")

    runtime_home = Path(tempfile.mkdtemp(prefix="copilot-isolated-runtime-"))

    env = dict(os.environ)
    env["COPILOT_GITHUB_TOKEN"] = token
    env["COPILOT_HOME"] = str(runtime_home)
    env["NO_COLOR"] = "1"
    command = [
        executable,
        "-p", payload,
        "--model", model_name(),
        "--output-format", "json",
        "--no-ask-user",
        "--available-tools=ask_user",
        "--allow-all-paths",
        "--no-custom-instructions",
        "--no-auto-update",
        "--no-color",
    ]
    try:
        proc = subprocess.run(
            command,
            cwd=workspace,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=max(1, int(args.timeout_sec)),
        )
        raw = (proc.stdout or "").strip()
        if proc.returncode != 0:
            raise RuntimeError(f"Copilot CLI failed rc={proc.returncode}: {raw[-4000:]}")
        if not raw:
            raise RuntimeError("Copilot CLI returned empty output")
        runtime_events, event_shapes = runtime_model_events(runtime_home)
        combined = raw + "\n" + runtime_events
        evidence = {"schema_version": "newrouge.copilot-model-evidence.v1",
            "runtime_event_shapes": event_shapes, "model_events": runtime_events}
        serialized = json.dumps(evidence, ensure_ascii=False, indent=2)
        # Never retain the authentication token in diagnostic evidence.
        (workspace / "copilot-model-evidence.json").write_text(
            serialized.replace(token, "[REDACTED]") + "\n", encoding="utf-8", newline="\n")
        content, actual_model = parse_copilot_json_stream(combined)
    finally:
        shutil.rmtree(runtime_home, ignore_errors=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content.rstrip() + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({
        "schema_version": "newrouge.isolated-model-runner-receipt.v1",
        "model": actual_model,
        "requested_model": model_name(),
        "transport": "github-copilot-cli-prompt-only",
        "model_tools": [],
        "runner_invocations": 1,
        "model_request_count": None,
        "request_count_observable": False,
        "output_chars": len(content),
        "workspace": workspace.as_posix(),
    }, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--describe", action="store_true")
    parser.add_argument("--workspace")
    parser.add_argument("--prompt-file")
    parser.add_argument("--output")
    parser.add_argument("--timeout-sec", type=int, default=1800)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    args = parser.parse_args()
    if args.describe:
        print(json.dumps(description(), ensure_ascii=False))
        return 0
    if not args.workspace or not args.prompt_file or not args.output:
        parser.error("--workspace, --prompt-file and --output are required unless --describe is used")
    try:
        return run(args)
    except (OSError, ValueError, RuntimeError, TimeoutError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
