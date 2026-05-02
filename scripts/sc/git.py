#!/usr/bin/env python3
"""
sc-git: Repo-specific git shim with basic safety rails.

Usage (Windows):
  py -3 scripts/sc/git.py status
  py -3 scripts/sc/git.py diff -- --stat
  py -3 scripts/sc/git.py commit --smart-commit --yes
"""

from __future__ import annotations

import argparse
import shlex
from pathlib import Path
from typing import Any

from _taskmaster import resolve_triplet
from _util import ci_dir, repo_root, run_cmd, write_json, write_text


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="sc-git (git shim)")
    ap.add_argument("operation", nargs="?", default="status")
    ap.add_argument("args", nargs=argparse.REMAINDER, help="args for git operation (use -- to separate)")
    ap.add_argument("--smart-commit", action="store_true")
    ap.add_argument("--interactive", action="store_true")
    ap.add_argument("--yes", action="store_true", help="confirm potentially destructive operations")
    ap.add_argument("--task-id", default=None, help="task id; defaults to first status=in-progress in tasks.json")
    ap.add_argument("--task-ref", default=None, help="commit Task ref (e.g. #2.1); defaults to #<task-id>")
    return ap


def is_force_push(op: str, args: list[str]) -> bool:
    if op != "push":
        return False
    force_flags = {"--force", "-f", "--force-with-lease"}
    return any(a in force_flags for a in args)


def requires_yes(op: str, args: list[str]) -> bool:
    if op in {"reset", "clean", "rebase"}:
        return True
    if is_force_push(op, args):
        return True
    return False


def has_commit_message(args: list[str]) -> bool:
    return "-m" in args or "--message" in args


def smart_commit_message() -> str:
    rc, out = run_cmd(["git", "diff", "--cached", "--name-only"], cwd=repo_root(), timeout_sec=30)
    files = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if not files:
        return "chore(repo): update working tree"

    areas = set()
    for f in files:
        f = f.replace("\\", "/")
        if f.startswith("docs/"):
            areas.add("docs")
        elif f.startswith("scripts/"):
            areas.add("scripts")
        elif f.startswith("Game.Core.Tests/") or f.endswith("Tests.cs"):
            areas.add("tests")
        elif f.startswith("Game.Core/Contracts/"):
            areas.add("contracts")
        elif f.startswith("Game.Core/"):
            areas.add("core")
        elif f.startswith("Game.Godot/"):
            areas.add("godot")
        else:
            areas.add("repo")

    scope = ",".join(sorted(areas))
    prefix = "chore"
    if "tests" in areas and len(areas) == 1:
        prefix = "test"
    if "docs" in areas and len(areas) == 1:
        prefix = "docs"
    if "core" in areas and len(areas) == 1:
        prefix = "feat"
    if "contracts" in areas and len(areas) == 1:
        prefix = "feat"

    return f"{prefix}({scope}): update {scope}"


def load_commit_template() -> str:
    # Hardcoded repo convention (per project standard).
    path = repo_root() / ".superclaude" / "commit-template.txt"
    if not path.exists():
        raise FileNotFoundError(f"commit template not found: {path}")
    return path.read_text(encoding="utf-8")


def build_commit_body(max_files: int = 12) -> str:
    rc, out = run_cmd(["git", "diff", "--cached", "--name-only"], cwd=repo_root(), timeout_sec=30)
    files = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if not files:
        return "- No staged files.\n"

    lines = ["- Changes:"]
    for f in files[:max_files]:
        lines.append(f"  - {f}")
    if len(files) > max_files:
        lines.append(f"  - (+{len(files) - max_files} more)")
    lines.append("")
    lines.append("- Rationale: (please amend this commit message to explain why)")
    return "\n".join(lines) + "\n"


def render_commit_message(
    *,
    subject: str,
    body: str,
    task_ref: str,
    adr_refs: list[str],
    overlay_file: str | None,
) -> str:
    if not adr_refs:
        raise ValueError("Missing ADR refs for commit message (expected at least 1).")

    tpl = load_commit_template()
    msg = tpl.replace("<type>(<scope>): <description>", subject)
    msg = msg.replace("<body>", body.rstrip() + "\n")
    msg = msg.replace("{{task_id}}", task_ref)
    msg = msg.replace("{{adr_refs}}", ", ".join(adr_refs))
    msg = msg.replace("{{overlay_file}}", overlay_file or "")
    return msg


def sync_overlay_task_drift_baseline(*, out_dir: Path) -> tuple[int, str, Path]:
    cmd = ["py", "-3", "scripts/python/remind_overlay_task_drift.py", "--write"]
    rc, out = run_cmd(cmd, cwd=repo_root(), timeout_sec=120)
    if rc != 0:
        log_path = out_dir / "overlay-task-drift-sync.log"
        write_text(log_path, out)
        return rc, out, log_path

    # Ensure potential baseline updates are included in the current commit.
    overlay_index_rel = "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/_index.md"
    add_rc, add_out = run_cmd(["git", "add", overlay_index_rel], cwd=repo_root(), timeout_sec=30)
    if add_rc != 0:
        out = out + ("\n" if out else "") + add_out
        rc = add_rc

    log_path = out_dir / "overlay-task-drift-sync.log"
    write_text(log_path, out)
    return rc, out, log_path


def _promote_commit_wrapper_flags(args: argparse.Namespace) -> tuple[argparse.Namespace, list[str]]:
    """Recover wrapper flags accidentally captured by argparse.REMAINDER after operation."""
    if args.operation != "commit":
        return args, list(args.args)

    extra = list(args.args)
    if extra and extra[0] == "--":
        extra = extra[1:]

    filtered: list[str] = []
    i = 0
    while i < len(extra):
        tok = extra[i]

        if tok == "--smart-commit":
            args.smart_commit = True
            i += 1
            continue
        if tok == "--interactive":
            args.interactive = True
            i += 1
            continue
        if tok == "--yes":
            args.yes = True
            i += 1
            continue

        if tok.startswith("--task-id="):
            args.task_id = tok.split("=", 1)[1]
            i += 1
            continue
        if tok == "--task-id" and i + 1 < len(extra):
            args.task_id = extra[i + 1]
            i += 2
            continue

        if tok.startswith("--task-ref="):
            args.task_ref = tok.split("=", 1)[1]
            i += 1
            continue
        if tok == "--task-ref" and i + 1 < len(extra):
            args.task_ref = extra[i + 1]
            i += 2
            continue

        filtered.append(tok)
        i += 1

    return args, filtered


def main() -> int:
    args = build_parser().parse_args()
    out_dir = ci_dir("sc-git")

    args, extra = _promote_commit_wrapper_flags(args)

    op = args.operation

    if requires_yes(op, extra) and not args.yes:
        print(f"[sc-git] ERROR: operation '{op}' requires --yes for confirmation.")
        return 2

    git_args = ["git", op] + extra
    notes = []

    if op == "commit" and args.smart_commit and not has_commit_message(extra):
        drift_rc, _drift_out, drift_log = sync_overlay_task_drift_baseline(out_dir=out_dir)
        if drift_rc != 0:
            summary: dict[str, Any] = {
                "cmd": "sc-git",
                "operation": op,
                "args": extra,
                "interactive": bool(args.interactive),
                "rc": drift_rc,
                "log": str(drift_log),
                "notes": [{"overlay_task_drift_sync": "failed"}],
            }
            write_json(out_dir / "summary.json", summary)
            print(f"SC_GIT rc={drift_rc} op={op} cmd=overlay-task-drift-sync out={out_dir}")
            return drift_rc

        notes.append({"overlay_task_drift_sync": "updated_or_ok", "log": str(drift_log)})
        triplet = resolve_triplet(task_id=args.task_id)
        task_ref = args.task_ref or f"#{triplet.task_id}"
        subject = smart_commit_message()
        body = build_commit_body()
        commit_msg = render_commit_message(
            subject=subject,
            body=body,
            task_ref=task_ref,
            adr_refs=triplet.adr_refs(),
            overlay_file=triplet.overlay(),
        )

        msg_path = out_dir / "commit-message.txt"
        write_text(msg_path, commit_msg)

        git_args = ["git", "commit", "-F", str(msg_path)] + extra
        notes.append(
            {
                "smart_commit_subject": subject,
                "task_id": triplet.task_id,
                "task_ref": task_ref,
                "adr_refs": triplet.adr_refs(),
                "overlay": triplet.overlay(),
                "message_file": str(msg_path),
            }
        )

    rc, out = run_cmd(git_args, cwd=repo_root(), timeout_sec=300)

    # Log output
    safe_op = "".join(ch for ch in op if ch.isalnum() or ch in ("-", "_"))[:32]
    log_path = out_dir / f"{safe_op}.log"
    write_text(log_path, out)

    summary: dict[str, Any] = {
        "cmd": "sc-git",
        "operation": op,
        "args": extra,
        "interactive": bool(args.interactive),
        "rc": rc,
        "log": str(log_path),
        "notes": notes,
    }
    write_json(out_dir / "summary.json", summary)

    printable = " ".join(shlex.quote(a) for a in git_args)
    print(f"SC_GIT rc={rc} op={op} cmd={printable} out={out_dir}")
    return 0 if rc == 0 else rc


if __name__ == "__main__":
    raise SystemExit(main())
