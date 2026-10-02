#!/usr/bin/env python3
"""No-tools isolated runner backed by the authenticated Codex CLI session."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import os
import re
from pathlib import Path

from openai_isolated_model_runner import (
    DEFAULT_MAX_BYTES,
    batched_workspace_parts,
    workspace_payload,
)

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


def _trim_workspace_context(base: str) -> str:
    """Keep Codex input below its 1 MiB turn limit.

    The complete task-view JSON is already projected into the semantic
    requirements and makes the otherwise valid two-batch prompt exceed the
    Codex CLI limit.  Capability generation must use the requirements/source
    evidence, so omit only those duplicated raw views.
    """
    sections = re.split(r"(?=^===== FILE: )", base, flags=re.MULTILINE)
    kept = []
    for section in sections:
        match = re.match(r"===== FILE: ([^ ]+) =====", section)
        if match and "/analysis-input/task-views/" in "/" + match.group(1):
            # Keep only the identity and semantic cross-reference fields. The
            # full views duplicate long descriptions/acceptance text already
            # represented by the prepared requirements and source blocks.
            try:
                payload = json.loads(section.split("\n", 1)[1].rsplit("\n===== END FILE:", 1)[0])
                if isinstance(payload, list):
                    fields = {
                        "id", "taskmaster_id", "title", "status", "priority",
                        "semantic_refs", "requirement_ids", "source_refs",
                    }
                    compact = [
                        {key: value for key, value in row.items() if key in fields}
                        for row in payload if isinstance(row, dict)
                    ]
                    rel = match.group(1)
                    kept.append(
                        f"===== FILE: {rel} (compact semantic view) =====\n"
                        + json.dumps(compact, ensure_ascii=False, separators=(",", ":"))
                        + f"\n===== END FILE: {rel} (compact semantic view) ====="
                    )
                    continue
            except (ValueError, json.JSONDecodeError, IndexError):
                pass
            continue
        kept.append(section)
    return "\n".join(kept)


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
        return (
            "\n\nFINAL COVERAGE AUDIT (machine-generated IDs; do not omit):\n"
            "Before returning JSON, verify every active delivery Requirement appears "
            "exactly once in capabilities or ungrouped_requirements. Verify every "
            "Source Block ID appears exactly once in source_accounting.\n"
            "REQUIREMENT_IDS=" + ",".join(requirements) + "\n"
            "SOURCE_BLOCK_IDS=" + ",".join(blocks) + "\n"
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
        base = _trim_workspace_context(base)
        payload = "\n\n".join([
            prompt_path.read_text(encoding="utf-8").rstrip(),
            base.rstrip(),
            *[part for _name, part in batches],
            _coverage_checklist(workspace),
        ]) + "\n"
    else:
        payload = workspace_payload(
            workspace,
            prompt_path=prompt_path,
            output_path=output_path,
            max_bytes=args.max_bytes,
        )
    executable = _codex_executable()
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
