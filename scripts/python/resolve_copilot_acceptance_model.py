#!/usr/bin/env python3
"""Resolve one actually available fixed Copilot CLI model for real planning acceptance."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Sequence

DEFAULT_CANDIDATES = (
    "gpt-5.3-codex",
    "claude-haiku-4.5",
    "gemini-3.5-flash",
    "gemini-3.6-flash",
    "gemini-3.7-flash",
)


def _token(env: dict[str, str]) -> str:
    return str(env.get("COPILOT_GITHUB_TOKEN") or env.get("GITHUB_TOKEN") or "").strip()


def probe_model(
    executable: str,
    model: str,
    *,
    env: dict[str, str],
    timeout_sec: int = 90,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> tuple[bool, str]:
    if not _token(env):
        return False, "missing_github_token"
    with tempfile.TemporaryDirectory(prefix="copilot-model-probe-") as folder:
        runtime_home = Path(folder) / "home"
        runtime_home.mkdir()
        probe_env = dict(env)
        probe_env["COPILOT_HOME"] = str(runtime_home)
        probe_env["NO_COLOR"] = "1"
        proc = run(
            [
                executable,
                "-s",
                "-p", "Reply with exactly OK.",
                "--model", model,
                "--no-ask-user",
                "--available-tools=ask_user",
                "--no-custom-instructions",
                "--no-auto-update",
                "--no-color",
            ],
            env=probe_env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_sec,
        )
    output = (proc.stdout or "").strip()
    if proc.returncode == 0 and output:
        return True, output[-400:]
    return False, output[-1200:] or f"rc={proc.returncode}"


def resolve_model(
    candidates: Sequence[str],
    *,
    env: dict[str, str] | None = None,
    executable: str | None = None,
    probe: Callable[[str, str], tuple[bool, str]] | None = None,
) -> dict:
    resolved_env = dict(os.environ if env is None else env)
    exe = executable or shutil.which("copilot")
    if not exe:
        raise ValueError("GitHub Copilot CLI is unavailable")
    if not _token(resolved_env):
        raise ValueError("GITHUB_TOKEN/COPILOT_GITHUB_TOKEN is required")

    attempts = []
    for model in candidates:
        name = str(model).strip()
        if not name:
            continue
        if probe is None:
            ok, detail = probe_model(exe, name, env=resolved_env)
        else:
            ok, detail = probe(exe, name)
        attempts.append({"model": name, "available": bool(ok), "detail": detail})
        if ok:
            return {
                "schema_version": "newrouge.copilot-model-resolution.v1",
                "status": "resolved",
                "model": name,
                "attempts": attempts,
            }
    # Diagnostic only: GitHub may allow auto selection even when named models
    # are hidden by entitlement. Capture structured output so a later revision
    # can bind and verify the actual model identity; never treat auto as resolved.
    auto = subprocess.run(
        [
            exe,
            "-p", "Reply with exactly OK.",
            "--model", "auto",
            "--output-format", "json",
            "--no-ask-user",
            "--available-tools=ask_user",
            "--no-custom-instructions",
            "--no-auto-update",
            "--no-color",
        ],
        env=resolved_env,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=90,
    )
    auto_detail = (auto.stdout or "").strip()[-4000:]
    raise ValueError(
        "no fixed Copilot model is available; attempts="
        + json.dumps(attempts, ensure_ascii=False)
        + f"; auto_probe_rc={auto.returncode}; auto_probe={auto_detail}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", action="append", default=[])
    parser.add_argument("--github-output", default=os.environ.get("GITHUB_OUTPUT", ""))
    args = parser.parse_args()
    candidates = tuple(args.candidate) or DEFAULT_CANDIDATES
    try:
        result = resolve_model(candidates)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False))
    if args.github_output:
        with Path(args.github_output).open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(f"model={result['model']}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
