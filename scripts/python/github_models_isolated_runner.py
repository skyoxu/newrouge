#!/usr/bin/env python3
"""Text-only GitHub Models runner with a workspace-only model-visible boundary."""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from openai_isolated_model_runner import (
    DEFAULT_MAX_BYTES,
    batched_workspace_parts,
    workspace_payload,
)

SCHEMA = "newrouge.isolated-model-runner.v1"
API_URL = "https://models.github.ai/inference/chat/completions"


def model_name() -> str:
    return str(
        os.environ.get("SC_GITHUB_MODEL")
        or os.environ.get("GITHUB_MODELS_MODEL")
        or "openai/gpt-4o"
    ).strip() or "openai/gpt-4o"


def token_value() -> str:
    return str(
        os.environ.get("GITHUB_MODELS_TOKEN")
        or os.environ.get("GITHUB_TOKEN")
        or ""
    ).strip()


def description() -> dict[str, object]:
    return {
        "schema_version": SCHEMA,
        "filesystem_scope": "workspace_only",
        "fresh_session_per_invocation": True,
        "can_read_outside_workspace": False,
        "model": model_name(),
        "transport": "github-models-chat-completions-text-only",
        "model_tools": [],
        "request_accounting": "exact_per_runner_invocation",
        "supports_batched_session": True,
    }


def _content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        chunks = []
        for item in content:
            if isinstance(item, dict):
                value = item.get("text") or item.get("content")
                if isinstance(value, str) and value.strip():
                    chunks.append(value.strip())
        return "\n".join(chunks).strip()
    return ""


def _chat(messages: list[dict[str, str]], *, timeout_sec: float) -> tuple[str, dict[str, Any]]:
    token = token_value()
    if not token:
        raise ValueError("GitHub Models token is unavailable")
    request = urllib.request.Request(
        API_URL,
        data=json.dumps({
            "model": model_name(),
            "messages": messages,
        }).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=max(1.0, timeout_sec)) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub Models HTTP {exc.code}: {body[-2000:]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub Models request failed: {exc}") from exc
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise RuntimeError("GitHub Models response is not a JSON object")
    output = _content(payload)
    if not output:
        raise RuntimeError("GitHub Models returned empty output")
    return output, payload


def _run_single(
    *,
    workspace: Path,
    prompt_path: Path,
    output_path: Path,
    timeout_sec: int,
    max_bytes: int,
) -> dict[str, Any]:
    payload = workspace_payload(
        workspace,
        prompt_path=prompt_path,
        output_path=output_path,
        max_bytes=max_bytes,
    )
    output, response = _chat(
        [{"role": "user", "content": payload}],
        timeout_sec=timeout_sec,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output.rstrip() + "\n", encoding="utf-8", newline="\n")
    return {
        "schema_version": "newrouge.isolated-model-runner-receipt.v1",
        "model": model_name(),
        "transport": "github-models-chat-completions-text-only",
        "output_chars": len(output),
        "model_tools": [],
        "model_request_count": 1,
        "request_count_observable": True,
        "response_id": str(response.get("id") or ""),
        "workspace": workspace.as_posix(),
    }


def _run_batched(
    *,
    workspace: Path,
    prompt_path: Path,
    output_path: Path,
    timeout_sec: int,
    max_bytes: int,
) -> dict[str, Any]:
    original_prompt = prompt_path.read_text(encoding="utf-8").rstrip()
    base, batches = batched_workspace_parts(
        workspace,
        prompt_path=prompt_path,
        output_path=output_path,
        max_bytes=max_bytes,
    )
    deadline = time.monotonic() + timeout_sec
    messages: list[dict[str, str]] = []
    request_count = 0
    last_response: dict[str, Any] = {}

    def call(user_text: str) -> str:
        nonlocal request_count, last_response
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("isolated GitHub Models active-time budget exhausted")
        messages.append({"role": "user", "content": user_text})
        output, response = _chat(messages, timeout_sec=remaining)
        messages.append({"role": "assistant", "content": output})
        request_count += 1
        last_response = response
        return output

    call("\n\n".join([
        original_prompt,
        base,
        "Do not produce the final answer yet. Confirm only that the base context is loaded and wait for ordered source batches.",
    ]))
    for index, (rel, section) in enumerate(batches, 1):
        ack = call("\n\n".join([
            f"Source batch {index}/{len(batches)} follows. Preserve exact source/Requirement identity and boundary observations for the final answer.",
            section,
            "Do not finalize yet. Return a compact ingestion acknowledgement listing the block IDs and Requirement IDs read from this batch.",
        ]))
        if not ack:
            raise RuntimeError(f"empty ingestion acknowledgement for {rel}")

    output = call("\n\n".join([
        "All ordered source batches are now loaded in this same session.",
        "Produce the final answer now, following the original instruction exactly.",
        "Return only the requested final JSON object; do not include ingestion acknowledgements or markdown fences.",
    ]))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output.rstrip() + "\n", encoding="utf-8", newline="\n")
    return {
        "schema_version": "newrouge.isolated-model-runner-receipt.v1",
        "model": model_name(),
        "transport": "github-models-chat-completions-text-only-batched",
        "response_id": str(last_response.get("id") or ""),
        "output_chars": len(output),
        "model_tools": [],
        "model_request_count": request_count,
        "request_count_observable": True,
        "batch_count": len(batches),
        "workspace": workspace.as_posix(),
    }


def run(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    prompt_path = Path(args.prompt_file).resolve()
    output_path = Path(args.output).resolve()
    if not workspace.is_dir():
        raise ValueError("workspace directory is missing")
    batch_index = workspace / "analysis-input/model-batches/batch-index.json"
    receipt = (
        _run_batched(
            workspace=workspace,
            prompt_path=prompt_path,
            output_path=output_path,
            timeout_sec=args.timeout_sec,
            max_bytes=args.max_bytes,
        )
        if batch_index.is_file()
        else _run_single(
            workspace=workspace,
            prompt_path=prompt_path,
            output_path=output_path,
            timeout_sec=args.timeout_sec,
            max_bytes=args.max_bytes,
        )
    )
    print(json.dumps(receipt, ensure_ascii=False))
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
    except (OSError, ValueError, RuntimeError, TimeoutError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
