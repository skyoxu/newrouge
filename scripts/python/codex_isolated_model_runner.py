#!/usr/bin/env python3
"""No-tools isolated runner backed by the authenticated Codex CLI session."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

from openai_isolated_model_runner import (
    DEFAULT_MAX_BYTES,
    batched_workspace_parts,
    workspace_payload,
)

SCHEMA = "newrouge.isolated-model-runner.v1"


def description() -> dict[str, object]:
    return {
        "schema_version": SCHEMA,
        "filesystem_scope": "workspace_only",
        "fresh_session_per_invocation": True,
        "can_read_outside_workspace": False,
        "model": "codex-cli-default",
        "transport": "codex-cli-text-only",
        "model_tools": [],
        "request_accounting": "codex-cli-invocation-only",
        "supports_batched_session": True,
    }


def run(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    prompt_path = Path(args.prompt_file).resolve()
    output_path = Path(args.output).resolve()
    if not workspace.is_dir():
        raise ValueError("workspace directory is missing")
    batch_index = workspace / "analysis-input/model-batches/batch-index.json"
    if batch_index.is_file():
        base, batches = batched_workspace_parts(
            workspace,
            prompt_path=prompt_path,
            output_path=output_path,
            max_bytes=args.max_bytes,
        )
        payload = "\n\n".join([
            prompt_path.read_text(encoding="utf-8").rstrip(),
            base.rstrip(),
            *[part for _name, part in batches],
        ]) + "\n"
    else:
        payload = workspace_payload(
            workspace,
            prompt_path=prompt_path,
            output_path=output_path,
            max_bytes=args.max_bytes,
        )
    executable = shutil.which("codex")
    if not executable:
        raise ValueError("Codex CLI is unavailable")
    command = [
        executable,
        "exec",
        "-s", "read-only",
        "-C", str(workspace),
        "--output-last-message", str(output_path),
        "-",
    ]
    proc = subprocess.run(
        command,
        cwd=workspace,
        input=payload,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=max(1, int(args.timeout_sec)),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"Codex CLI failed rc={proc.returncode}: {(proc.stdout or '')[-4000:]}")
    if not output_path.is_file():
        raise RuntimeError("Codex CLI produced no output")
    print(json.dumps({
        "schema_version": "newrouge.isolated-model-runner-receipt.v1",
        "model": "codex-cli-default",
        "transport": "codex-cli-text-only",
        "model_tools": [],
        "runner_invocations": 1,
        "request_count_observable": False,
        "output_chars": len(output_path.read_text(encoding="utf-8")),
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
    except (OSError, ValueError, RuntimeError, TimeoutError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
