#!/usr/bin/env python3
"""No-tools isolated runner backed by the authenticated Codex CLI session."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import os
from pathlib import Path

from openai_isolated_model_runner import (
    DEFAULT_MAX_BYTES,
    batched_workspace_parts,
    workspace_payload,
)
from _planning_skill_common import validate_output_schema
from _capability_input_integrity import (
    CODEX_MAX_TURN_BYTES, DEFAULT_MAX_INPUT_TOKENS, REPORT_NAME, check_workspace_request, configured_input_limit, measure_request, validate_batches,
)
from _planning_skill_common import atomic_json

SCHEMA = "newrouge.isolated-model-runner.v1"


def _codex_executable() -> str:
    for name in ("codex", "codex.cmd"):
        found = shutil.which(name)
        if found:
            return found
    package_root = str(os.environ.get("CODEX_MANAGED_PACKAGE_ROOT") or "").strip()
    if package_root:
        npm_wrapper = Path(package_root).parents[2] / "codex.cmd"
        if npm_wrapper.is_file():
            return str(npm_wrapper)
        candidate = Path(package_root) / "bin" / "codex.js"
        if candidate.is_file():
            return str(candidate)
    raise ValueError("Codex CLI is unavailable; set CODEX_MANAGED_PACKAGE_ROOT or add codex to PATH")


def _coverage_checklist(workspace: Path) -> str:
    """Append compact machine-readable IDs for the model's final audit."""
    try:
        semantics = json.loads(
            (workspace / "analysis-input/semantic-requirements.v1.json")
            .read_text(encoding="utf-8")
        )
        ledger = json.loads(
            (workspace / "analysis-input/source-blocks.v1.json")
            .read_text(encoding="utf-8")
        )
        requirements = [
            str(row.get("requirement_id"))
            for row in semantics.get("requirements", [])
            if isinstance(row, dict)
            and row.get("status", "active") == "active"
            and row.get("delivery_relevant") is True
        ]
        blocks = [
            str(row.get("block_id"))
            for row in ledger.get("blocks", [])
            if isinstance(row, dict) and row.get("block_id")
        ]
        batch_index = json.loads(
            (workspace / "analysis-input/model-batches/batch-index.json")
            .read_text(encoding="utf-8")
        )
        return (
            "\n\nFINAL COVERAGE AUDIT (machine-generated IDs; do not omit):\n"
            "Before returning JSON, verify every active delivery Requirement appears "
            "exactly once in capabilities or ungrouped_requirements. Verify every "
            "Source Block ID appears exactly once in source_accounting.\n"
            "REQUIREMENT_IDS=" + ",".join(requirements) + "\n"
            "SOURCE_BLOCK_IDS=" + ",".join(blocks) + "\n"
            "EXPECTED_BATCH_COUNT=" + str(batch_index.get("batch_count") or len(batch_index.get("batches", []))) + "\n"
            "EXPECTED_SOURCE_BLOCK_COUNT=" + str(batch_index.get("block_count") or len(blocks)) + "\n"
            "EXPECTED_REQUIREMENT_COUNT=" + str(batch_index.get("requirement_count") or len(requirements)) + "\n"
        )
    except (OSError, ValueError, json.JSONDecodeError, TypeError):
        return ""


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
        "supports_input_preflight": True,
    }


def run(args: argparse.Namespace) -> int:
    workspace = Path(args.workspace).resolve()
    prompt_path = Path(args.prompt_file).resolve()
    output_path = Path(args.output).resolve()
    if not workspace.is_dir():
        raise ValueError("workspace directory is missing")
    schema_value = getattr(args, "output_schema", "")
    schema_path = Path(schema_value).resolve() if schema_value else None
    if schema_path is not None and not schema_path.is_relative_to(workspace):
        raise ValueError("output schema path must be inside workspace")
    batch_index = workspace / "analysis-input/model-batches/batch-index.json"
    integrity = None
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
            _coverage_checklist(workspace),
        ]) + "\n"
        try:
            integrity = {**validate_batches(workspace, json.loads(batch_index.read_text(encoding='utf-8'))),
                **measure_request(payload, max_bytes=min(args.max_bytes, CODEX_MAX_TURN_BYTES),
                    max_input_tokens=getattr(args, 'max_input_tokens', DEFAULT_MAX_INPUT_TOKENS))}
            atomic_json(workspace / REPORT_NAME, {'status': 'ready', **integrity})
        except ValueError as exc:
            atomic_json(workspace / REPORT_NAME, {'status': 'blocked', 'reason': str(exc),
                'complete_request_bytes': len(payload.encode('utf-8')), 'model_invoked': False})
            raise
    else:
        payload = workspace_payload(
            workspace,
            prompt_path=prompt_path,
            output_path=output_path,
            max_bytes=args.max_bytes,
        )
        integrity = check_workspace_request(workspace, payload,
            max_bytes=min(args.max_bytes, CODEX_MAX_TURN_BYTES),
            max_input_tokens=getattr(args, "max_input_tokens", configured_input_limit()))
    if getattr(args, 'preflight', False):
        print(json.dumps({'status': 'ready', 'model_invoked': False, 'input_integrity': integrity}, ensure_ascii=False))
        return 0
    executable = _codex_executable()
    command = [
        executable,
        "exec",
        "-s", "read-only",
        "-C", str(workspace),
        "--output-last-message", str(output_path),
        *( ["--output-schema", str(schema_path)] if schema_path is not None else [] ),
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
    if schema_path is not None:
        validate_output_schema(output_path, schema_path)
    print(json.dumps({
        "schema_version": "newrouge.isolated-model-runner-receipt.v1",
        "model": "codex-cli-default",
        "transport": "codex-cli-text-only",
        "model_tools": [],
        "runner_invocations": 1,
        "request_count_observable": False,
        "output_chars": len(output_path.read_text(encoding="utf-8")),
        "workspace": workspace.as_posix(),
        **({'input_integrity': integrity} if integrity is not None else {}),
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
    parser.add_argument('--max-input-tokens', type=int, default=configured_input_limit())
    parser.add_argument('--preflight', action='store_true', help='Validate Capability input without invoking Codex')
    parser.add_argument("--output-schema", default="")
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
