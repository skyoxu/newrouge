#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run grouped hard/soft gates for local and CI usage.

Modes:
- hard: fail on any gate failure
- soft: do not fail by default (unless --strict-soft)
- all : run hard then soft

Outputs:
- logs/ci/<YYYY-MM-DD>/gate-bundle/<mode>/summary.json
- logs/ci/<YYYY-MM-DD>/gate-bundle/<mode>/<gate>.log
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _today() -> str:
    return dt.date.today().strftime("%Y-%m-%d")


def _run_command(cmd: list[str], log_path: Path) -> tuple[int, str]:
    proc = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="ignore",
        check=False,
    )
    output = proc.stdout or ""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(output, encoding="utf-8")
    return proc.returncode, output


def _hard_gate_commands(task_files: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "name": "docs_utf8_integrity",
            "cmd": [
                "py",
                "-3",
                "scripts/python/check_docs_utf8_integrity.py",
                "--roots",
                "docs",
                ".github",
                ".taskmaster",
                "AGENTS.md",
            ],
        },
        {
            "name": "prd_gdd_semantic_consistency",
            "cmd": ["py", "-3", "scripts/python/check_prd_gdd_semantic_consistency.py"],
        },
        {
            "name": "overlay_task_drift",
            "cmd": ["py", "-3", "scripts/python/remind_overlay_task_drift.py"],
        },
        {
            "name": "task_contract_refs_gate",
            "cmd": [
                "py",
                "-3",
                "scripts/python/check_task_contract_refs.py",
                "--task-files",
                *task_files,
            ],
        },
        {
            "name": "no_hardcoded_core_events",
            "cmd": ["py", "-3", "scripts/python/check_no_hardcoded_core_events.py"],
        },
        {
            "name": "forbid_mirror_path_refs",
            "cmd": ["py", "-3", "scripts/python/forbid_mirror_path_refs.py", "--root", "."],
        },
        {
            "name": "validate_contracts",
            "cmd": ["py", "-3", "scripts/python/validate_contracts.py"],
        },
        {
            "name": "check_domain_contracts",
            "cmd": ["py", "-3", "scripts/python/check_domain_contracts.py"],
        },
        {
            "name": "check_gate_bundle_consistency",
            "cmd": ["py", "-3", "scripts/python/check_gate_bundle_consistency.py"],
        },
        {
            "name": "check_workflow_gate_enforcement",
            "cmd": ["py", "-3", "scripts/python/check_workflow_gate_enforcement.py"],
        },
    ]


def _soft_gate_commands(task_files: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "name": "task_contract_test_matrix",
            "cmd": [
                "py",
                "-3",
                "scripts/python/generate_task_contract_test_matrix.py",
                "--task-views",
                *task_files,
            ],
        }
    ]


def _run_group(
    mode: str,
    commands: list[dict[str, Any]],
    strict_soft: bool,
    out_dir: Path,
) -> tuple[int, dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)

    gate_results: list[dict[str, Any]] = []
    failed = 0

    for item in commands:
        name = str(item["name"])
        cmd = [str(x) for x in item["cmd"]]
        log_path = out_dir / f"{name}.log"

        print(f"[gate-bundle] START mode={mode} gate={name}")
        rc, output = _run_command(cmd, log_path)
        if output:
            print(output, end="" if output.endswith("\n") else "\n")
        print(f"[gate-bundle] END mode={mode} gate={name} rc={rc}")

        if rc != 0:
            failed += 1

        gate_results.append(
            {
                "name": name,
                "rc": rc,
                "command": cmd,
                "log": str(log_path).replace("\\", "/"),
            }
        )

    if mode == "hard":
        exit_code = 0 if failed == 0 else 1
    elif mode == "soft":
        exit_code = 0 if (failed == 0 or not strict_soft) else 1
    else:
        exit_code = 0 if failed == 0 else 1

    summary = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "action": "gate-bundle",
        "mode": mode,
        "strict_soft": strict_soft,
        "total": len(gate_results),
        "failed": failed,
        "status": "ok" if exit_code == 0 else "fail",
        "gates": gate_results,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        f"GATE_BUNDLE status={summary['status']} mode={mode} "
        f"failed={failed}/{len(gate_results)} out={str((out_dir / 'summary.json')).replace('\\', '/')}"
    )
    return exit_code, summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run grouped hard/soft gates.")
    parser.add_argument(
        "--mode",
        choices=["hard", "soft", "all"],
        default="all",
        help="Bundle mode: hard | soft | all",
    )
    parser.add_argument(
        "--strict-soft",
        action="store_true",
        help="When mode=soft/all, return non-zero if any soft gate fails",
    )
    parser.add_argument(
        "--task-files",
        nargs="*",
        default=[
            ".taskmaster/tasks/tasks_back.json",
            ".taskmaster/tasks/tasks_gameplay.json",
        ],
        help="Task view files passed to contract-related gates",
    )
    parser.add_argument(
        "--out-dir",
        default="",
        help="Optional output directory root. Default: logs/ci/<YYYY-MM-DD>/gate-bundle",
    )
    args = parser.parse_args()

    if args.out_dir:
        out_root = Path(args.out_dir)
    else:
        out_root = Path("logs") / "ci" / _today() / "gate-bundle"

    hard_commands = _hard_gate_commands(args.task_files)
    soft_commands = _soft_gate_commands(args.task_files)

    if args.mode == "hard":
        rc, _ = _run_group("hard", hard_commands, args.strict_soft, out_root / "hard")
        return rc

    if args.mode == "soft":
        rc, _ = _run_group("soft", soft_commands, args.strict_soft, out_root / "soft")
        return rc

    hard_rc, hard_summary = _run_group("hard", hard_commands, args.strict_soft, out_root / "hard")
    soft_rc, soft_summary = _run_group("soft", soft_commands, args.strict_soft, out_root / "soft")

    combined = {
        "ts": dt.datetime.now(dt.timezone.utc).isoformat(),
        "action": "gate-bundle",
        "mode": "all",
        "hard": hard_summary,
        "soft": soft_summary,
        "status": "ok" if hard_rc == 0 and soft_rc == 0 else "fail",
    }
    combined_path = out_root / "summary.json"
    combined_path.write_text(json.dumps(combined, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        f"GATE_BUNDLE status={combined['status']} mode=all "
        f"hard_failed={hard_summary['failed']} soft_failed={soft_summary['failed']} "
        f"out={str(combined_path).replace('\\', '/')}"
    )

    return 0 if combined["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
