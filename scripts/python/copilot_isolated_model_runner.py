#!/usr/bin/env python3
"""No-tools GitHub Copilot CLI runner for one prepared model-visible workspace."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

from openai_isolated_model_runner import DEFAULT_MAX_BYTES, workspace_payload

SCHEMA = "newrouge.isolated-model-runner.v1"


def model_name() -> str:
    return str(
        os.environ.get("SC_COPILOT_MODEL")
        or os.environ.get("COPILOT_MODEL")
        or "gpt-5.4"
    ).strip() or "gpt-5.4"


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

    runtime_home = workspace / ".copilot-isolated-runtime"
    if runtime_home.exists():
        shutil.rmtree(runtime_home)
    runtime_home.mkdir(parents=True)

    env = dict(os.environ)
    env["COPILOT_GITHUB_TOKEN"] = token
    env["COPILOT_HOME"] = str(runtime_home)
    env["NO_COLOR"] = "1"
    command = [
        executable,
        "-s",
        "--model", model_name(),
        "--no-ask-user",
        "--available-tools=ask_user",
        "--allow-all-paths",
        "--no-custom-instructions",
        "--no-auto-update",
        "--no-color",
    ]
    proc = subprocess.run(
        command,
        cwd=workspace,
        env=env,
        input=payload,
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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(raw.rstrip() + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({
        "schema_version": "newrouge.isolated-model-runner-receipt.v1",
        "model": model_name(),
        "transport": "github-copilot-cli-prompt-only",
        "model_tools": [],
        "runner_invocations": 1,
        "model_request_count": None,
        "request_count_observable": False,
        "output_chars": len(raw),
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
