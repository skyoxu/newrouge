#!/usr/bin/env python3
"""Run the controlled real-model Capability -> MVG production-path acceptance.

Run only in an isolated checkout/worktree because Capability apply writes formal derived
planning artifacts in that checkout. The script never marks runtime verification or Taskmaster
status. It requires the production isolated model runner and therefore an actual configured
model backend (for example OPENAI_API_KEY for the default OpenAI runner).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def run(cmd: list[str], *, cwd: Path) -> dict[str, Any]:
    started = dt.datetime.now(dt.timezone.utc)
    proc = subprocess.run(
        cmd, cwd=cwd, text=True, encoding="utf-8", errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    return {
        "command": cmd,
        "returncode": proc.returncode,
        "started_at_utc": started.isoformat(),
        "finished_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "output": proc.stdout[-12000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--task-id", action="append", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument(
        "--runner",
        default="scripts/python/openai_isolated_model_runner.py",
    )
    parser.add_argument("--alignment-override", default="")
    parser.add_argument("--confirm-isolated-checkout", action="store_true")
    args = parser.parse_args()

    root = Path(args.repo_root).resolve()
    if not args.confirm_isolated_checkout:
        print("PLANNING_PRODUCTION_ACCEPTANCE status=blocked reason=isolated_checkout_confirmation_required")
        return 2

    py = sys.executable
    cap_run = f"{args.run_id}-cap"
    mvg_run = f"{args.run_id}-mvg"
    steps: list[dict[str, Any]] = []

    commands = [
        [py, "scripts/python/plan_capabilities.py", "prepare", "--run-id", cap_run,
         *sum((["--task-id", value] for value in args.task_id), [])],
        [py, "scripts/python/plan_capabilities.py", "generate", "--run-id", cap_run,
         "--runner", args.runner],
        [py, "scripts/python/plan_capabilities.py", "review", "--run-id", cap_run,
         "--runner", args.runner],
        [py, "scripts/python/plan_capabilities.py", "preview-alignment", "--run-id", cap_run],
    ]
    if args.alignment_override:
        commands.append([
            py, "scripts/python/plan_capabilities.py", "apply", "--run-id", cap_run,
            "--alignment-override", args.alignment_override, "--confirm",
        ])
    else:
        commands.append([
            py, "scripts/python/plan_capabilities.py", "apply", "--run-id", cap_run, "--confirm",
        ])
    commands += [
        [py, "scripts/python/validate_semantic_topology.py", "--worktree", "--require-available"],
        [py, "scripts/python/plan_mvg.py", "prepare", "--run-id", mvg_run,
         "--capabilities", "docs/planning/semantic-topology/capabilities.v1.json",
         "--manifest", args.manifest,
         *sum((["--task-id", value] for value in args.task_id), [])],
        [py, "scripts/python/plan_mvg.py", "generate", "--run-id", mvg_run],
        [py, "scripts/python/plan_mvg.py", "validate", "--run-id", mvg_run],
    ]

    for command in commands:
        result = run(command, cwd=root)
        steps.append(result)
        if result["returncode"] != 0:
            report = {
                "schema_version": "newrouge.planning-production-acceptance.v1",
                "status": "blocked",
                "run_id": args.run_id,
                "steps": steps,
                "runtime_verified": False,
            }
            out = root / "logs/ci/planning-production-acceptance" / f"{args.run_id}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"PLANNING_PRODUCTION_ACCEPTANCE status=blocked report={out.relative_to(root).as_posix()}")
            return 2

    report = {
        "schema_version": "newrouge.planning-production-acceptance.v1",
        "status": "passed",
        "run_id": args.run_id,
        "steps": steps,
        "capability_run_id": cap_run,
        "mvg_run_id": mvg_run,
        "runtime_verified": False,
        "note": "This proves the real planning production path only; it does not prove game runtime acceptance.",
    }
    out = root / "logs/ci/planning-production-acceptance" / f"{args.run_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PLANNING_PRODUCTION_ACCEPTANCE status=passed report={out.relative_to(root).as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
