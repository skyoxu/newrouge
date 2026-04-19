#!/usr/bin/env python3
"""
sc-build: Repo-specific build shim (Godot+C# template).

Usage (Windows):
  py -3 scripts/sc/build.py
  py -3 scripts/sc/build.py NewRouge.sln --type prod --clean --verbose

TDD helper (gated, non-generative):
  py -3 scripts/sc/build.py tdd --stage green
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from _delivery_profile import (
    default_security_profile_for_delivery,
    known_delivery_profiles,
    profile_build_defaults,
    resolve_delivery_profile,
)
from _repo_targets import resolve_build_target
from _security_profile import resolve_security_profile
from _util import ci_dir, repo_root, run_cmd, write_json, write_text


DELIVERY_PROFILE_CHOICES = tuple(sorted(known_delivery_profiles()))


def resolve_build_runtime(*, delivery_profile: str | None, security_profile: str | None) -> dict[str, object]:
    resolved_delivery_profile = resolve_delivery_profile(delivery_profile)
    resolved_security_profile = resolve_security_profile(
        security_profile or default_security_profile_for_delivery(resolved_delivery_profile)
    )
    defaults = profile_build_defaults(resolved_delivery_profile)
    return {
        "delivery_profile": resolved_delivery_profile,
        "security_profile": resolved_security_profile,
        "warn_as_error": bool(defaults.get("warn_as_error", True)),
    }


def build_dotnet_build_cmd(*, target: str, config: str, verbose: bool, warn_as_error: bool) -> list[str]:
    cmd = ["dotnet", "build", str(target), "-c", config]
    if warn_as_error:
        cmd.append("-warnaserror")
    if verbose:
        cmd += ["-v", "normal"]
    return cmd


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="sc-build (build shim)")
    ap.add_argument("target", nargs="?", default=None, help="build target (.csproj/.sln); auto-resolved when omitted")
    ap.add_argument("--type", choices=["dev", "prod", "test"], default="dev")
    ap.add_argument("--clean", action="store_true")
    ap.add_argument("--optimize", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument(
        "--delivery-profile",
        default=None,
        choices=DELIVERY_PROFILE_CHOICES,
        help="Delivery profile (default: env DELIVERY_PROFILE or fast-ship).",
    )
    ap.add_argument(
        "--security-profile",
        default=None,
        choices=["strict", "host-safe"],
        help="Security profile override (default derives from delivery profile).",
    )
    return ap


def _read_non_negative_int_env(name: str, default: int) -> int:
    raw = (os.environ.get(name, "") or "").strip()
    if not raw:
        return max(0, int(default))
    try:
        value = int(raw)
    except ValueError:
        return max(0, int(default))
    return max(0, value)


def _read_positive_float_env(name: str, default: float) -> float:
    raw = (os.environ.get(name, "") or "").strip()
    if not raw:
        return float(default)
    try:
        value = float(raw)
    except ValueError:
        return float(default)
    if value <= 0:
        return float(default)
    return value


def _is_retryable_file_lock_failure(rc: int, output: str) -> bool:
    if rc == 0:
        return False
    trace = output.lower()
    if "cs2012" in trace:
        return True
    if "being used by another process" in trace:
        return True
    if "cannot access the file" in trace and "another process" in trace:
        return True
    if "另一进程" in output or "另一个进程" in output:
        return True
    return False


def run_build_with_file_lock_retry(
    *,
    cmd: list[str],
    retry_on_file_lock: int,
    retry_backoff_sec: float,
    timeout_sec: int = 1_800,
) -> tuple[int, str, list[dict[str, object]]]:
    attempts: list[dict[str, object]] = []
    chunks: list[str] = []

    attempt = 0
    while attempt <= retry_on_file_lock:
        attempt += 1
        rc, out = run_cmd(cmd, cwd=repo_root(), timeout_sec=timeout_sec)
        retryable = _is_retryable_file_lock_failure(rc, out)
        attempts.append(
            {
                "attempt": attempt,
                "rc": rc,
                "retryable_file_lock": retryable,
            }
        )
        chunks.append(f"=== attempt {attempt} rc={rc} ===\n{out.rstrip()}\n")
        if rc == 0:
            return 0, "\n".join(chunks), attempts
        if not retryable or attempt > retry_on_file_lock:
            return rc, "\n".join(chunks), attempts
        if retry_backoff_sec > 0:
            time.sleep(retry_backoff_sec)

    # Defensive fallback (loop always returns above).
    return 1, "\n".join(chunks), attempts


def main() -> int:
    # Lightweight subcommand routing (keeps backward compatibility):
    #   py -3 scripts/sc/build.py tdd ...
    if len(sys.argv) > 1 and sys.argv[1] == "tdd":
        cmd = ["py", "-3", "scripts/sc/build/tdd.py"] + sys.argv[2:]
        rc, out = run_cmd(cmd, cwd=repo_root(), timeout_sec=3_600)
        out_dir = ci_dir("sc-build")
        write_text(out_dir / "tdd.log", out)
        if out:
            end = "" if out.endswith("\n") else "\n"
            print(out, end=end)
        print(f"SC_BUILD_TDD rc={rc} out={out_dir}")
        return 0 if rc == 0 else rc

    args = build_parser().parse_args()
    runtime = resolve_build_runtime(delivery_profile=args.delivery_profile, security_profile=args.security_profile)
    os.environ["DELIVERY_PROFILE"] = str(runtime["delivery_profile"])
    os.environ["SECURITY_PROFILE"] = str(runtime["security_profile"])
    out_dir = ci_dir("sc-build")

    config = "Debug"
    if args.type == "prod" or args.optimize:
        config = "Release"

    root = repo_root()
    if args.target:
        target = root / args.target
    else:
        resolved = resolve_build_target(root)
        target = resolved if resolved is not None else (root / "NewRouge.sln")
    if not target.exists():
        print(f"[sc-build] ERROR: target not found: {target}")
        return 2

    summary = {
        "cmd": "sc-build",
        "target": str(target),
        "configuration": config,
        "clean": bool(args.clean),
        "optimize": bool(args.optimize),
        "status": "fail",
    }

    logs = []
    if args.clean:
        cmd = ["dotnet", "clean", str(target), "-c", config]
        rc, out = run_cmd(cmd, cwd=repo_root(), timeout_sec=900)
        log_path = out_dir / "dotnet-clean.log"
        write_text(log_path, out)
        logs.append({"name": "dotnet-clean", "cmd": cmd, "rc": rc, "log": str(log_path)})
        if rc != 0:
            summary["logs"] = logs
            write_json(out_dir / "summary.json", summary)
            print(f"SC_BUILD status=fail out={out_dir}")
            return rc

    cmd = build_dotnet_build_cmd(
        target=str(target),
        config=config,
        verbose=bool(args.verbose),
        warn_as_error=bool(runtime["warn_as_error"]),
    )

    retry_on_file_lock = _read_non_negative_int_env("SC_BUILD_RETRY_ON_FILE_LOCK", 1)
    retry_backoff_ms = _read_non_negative_int_env("SC_BUILD_RETRY_BACKOFF_MS", 1200)
    retry_backoff_sec = _read_positive_float_env(
        "SC_BUILD_RETRY_BACKOFF_SEC",
        retry_backoff_ms / 1000.0,
    )
    rc, out, build_attempts = run_build_with_file_lock_retry(
        cmd=cmd,
        retry_on_file_lock=retry_on_file_lock,
        retry_backoff_sec=retry_backoff_sec,
        timeout_sec=1_800,
    )
    log_path = out_dir / "dotnet-build.log"
    write_text(log_path, out)
    logs.append(
        {
            "name": "dotnet-build",
            "cmd": cmd,
            "rc": rc,
            "log": str(log_path),
            "attempt_count": len(build_attempts),
            "retry_on_file_lock": retry_on_file_lock,
        }
    )

    summary["logs"] = logs
    summary["status"] = "ok" if rc == 0 else "fail"
    summary["build_retry"] = {
        "retry_on_file_lock": retry_on_file_lock,
        "retry_backoff_sec": retry_backoff_sec,
        "attempts": build_attempts,
    }
    write_json(out_dir / "summary.json", summary)

    print(f"SC_BUILD status={summary['status']} out={out_dir}")
    return 0 if rc == 0 else rc


if __name__ == "__main__":
    raise SystemExit(main())
