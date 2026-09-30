#!/usr/bin/env python3
"""Recoverable closeout of an explicitly temporary Chapter 3 reconciliation.

The tracked pointer survives removal of the scope. Incomplete closeout blocks
task writers through chapter3_task_scope.load_scope. Evidence is historical;
Taskmaster remains the only task-state authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

POINTER = Path("docs/workflows/chapter3-closeout.json")
SCOPE = Path("docs/workflows/chapter3-task-scope.json")
SCHEMA = "chapter3.closeout.v1"
TASKS = [f".taskmaster/tasks/{name}.json" for name in ("tasks", "tasks_back", "tasks_gameplay")]
TOPOLOGY = "docs/planning/semantic-topology"
REPAIR_CHECKS = [
    ["scripts/python/attest_chapter3_triplet_baseline.py"],
    ["scripts/python/validate_semantic_topology.py", "--worktree", "--require-available"],
]
RECOVERY_TESTS = ["scripts.python.tests.test_chapter3_closeout_routes"]


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def confined(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    path.relative_to(root.resolve())
    return path


def load_record(root: Path) -> tuple[Path, dict[str, Any]] | None:
    pointer = root / POINTER
    if not pointer.exists():
        return None
    try:
        link = read(pointer)
        if link.get("schema_version") != SCHEMA:
            raise ValueError("Unsupported closeout pointer")
        path = confined(root, link["record_path"])
        state = read(path)
        if state.get("schema_version") != SCHEMA or state.get("run_id") != link["run_id"]:
            raise ValueError("Closeout identity mismatch")
        if state.get("phase") not in {"prepared", "repair-verified", "unfrozen", "recovery-verified", "complete"}:
            raise ValueError("Invalid closeout phase")
        if state["phase"] in {"recovery-verified", "complete"}:
            for key in ("repair_checks", "recovery_checks"):
                checks = state.get(key)
                if not checks or any(item.get("returncode") != 0 for item in checks):
                    raise ValueError("Closeout passing evidence missing")
        return path, state
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ValueError(f"Chapter 3 closeout record is invalid; restore {POINTER}: {exc}") from exc


def guard(root: Path) -> None:
    record = load_record(root)
    if record is None:
        return
    state = record[1]
    if state["phase"] != "complete" and not (root / SCOPE).is_file():
        raise ValueError("Chapter 3 closeout is incomplete; run chapter3_closeout.py resume before task creation")


def input_manifest(root: Path) -> dict[str, str]:
    source_set = root / "docs/workflows/chapter3-source-set.json"
    config = read(source_set)
    paths = TASKS + ["docs/workflows/chapter3-source-set.json", "docs/workflows/chapter7-profile.json"]
    paths += config["active_sources"]
    paths += [f"{TOPOLOGY}/{name}.v1.json" for name in (
        "source-blocks", "semantic-requirements", "capabilities", "topology-edges", "topology-manifest")]
    paths += [path.relative_to(root).as_posix() for path in (root / TOPOLOGY).rglob("*.json")]
    paths += [path.relative_to(root).as_posix() for path in (root / "scripts/python").rglob("*.py")]
    knowledge_config = "scripts/python/project_health_knowledge_config.json"
    if (root / knowledge_config).is_file():
        paths.append(knowledge_config)
    return {value: digest(confined(root, value)) for value in sorted(set(paths))}


def unchanged(root: Path, state: dict[str, Any]) -> None:
    if input_manifest(root) != state["inputs"]:
        raise ValueError("Closeout inputs changed; preserve edits and restart with a reviewed baseline")


def run_checks(root: Path, commands: list[list[str]], out: Path) -> list[dict[str, Any]]:
    results = []
    out.mkdir(parents=True, exist_ok=True)
    for index, command in enumerate(commands):
        result = subprocess.run([sys.executable, *command], cwd=root, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=300)
        (out / f"check-{index}.log").write_text(result.stdout + result.stderr, encoding="utf-8")
        results.append({"command": command, "returncode": result.returncode})
        if result.returncode:
            break
    return results


def passing(results: list[dict[str, Any]], count: int) -> bool:
    return len(results) == count and all(item["returncode"] == 0 for item in results)


def begin(root: Path, run_id: str, *, temporary: bool) -> dict[str, Any]:
    if not temporary:
        raise ValueError("Explicit temporary closeout ownership is required")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}", run_id):
        raise ValueError("Invalid run ID")
    previous = load_record(root)
    if previous:
        if previous[1]["run_id"] != run_id:
            raise ValueError("Another closeout is registered; inspect before replacing it")
        return previous[1]
    scope = read(root / SCOPE)
    if scope.get("lifecycle") == "permanent":
        raise ValueError("Permanent reconciliation scope cannot be automatically released")
    from chapter3_task_scope import validate_master
    validate_master(root, scope)
    state = {"schema_version": SCHEMA, "run_id": run_id, "phase": "prepared",
             "scope": scope, "scope_sha256": digest(root / SCOPE), "inputs": input_manifest(root)}
    record = Path(f"docs/workflows/closeouts/{run_id}.json")
    atomic_json(root / record, state)
    atomic_json(root / POINTER, {"schema_version": SCHEMA, "run_id": run_id, "record_path": record.as_posix()})
    return state


def resume(root: Path) -> dict[str, Any]:
    found = load_record(root)
    if found is None:
        raise ValueError("No closeout is registered; run begin --temporary first")
    path, state = found
    if state["phase"] == "complete":
        return state
    unchanged(root, state)
    scope_path = root / SCOPE
    if scope_path.exists() and digest(scope_path) != state["scope_sha256"]:
        raise ValueError("Scope changed; refusing to remove or overwrite later edits")
    out = root / "logs/ci/chapter3-closeout" / state["run_id"]
    if state["phase"] == "prepared":
        results = run_checks(root, REPAIR_CHECKS, out / "repair")
        if not passing(results, len(REPAIR_CHECKS)):
            raise ValueError(f"Reconciliation validation failed; see {out / 'repair'}")
        unchanged(root, state)
        state.update(phase="repair-verified", repair_checks=results)
        atomic_json(path, state)
    if state["phase"] == "repair-verified":
        # The durable pointer and record already block consumers if we crash here.
        if scope_path.exists():
            scope_path.unlink()
        state["phase"] = "unfrozen"
        atomic_json(path, state)
    if state["phase"] == "unfrozen":
        commands = [["-m", "unittest", *RECOVERY_TESTS]]
        results = run_checks(root, commands, out / "recovery")
        if not passing(results, len(commands)):
            raise ValueError(f"Recovery validation failed; creation remains blocked; see {out / 'recovery'}")
        unchanged(root, state)
        state.update(phase="recovery-verified", recovery_checks=results)
        atomic_json(path, state)
    unchanged(root, state)
    if scope_path.exists():
        raise ValueError("Scope reappeared; preserve it and inspect closeout conflict")
    state["phase"] = "complete"
    atomic_json(path, state)
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["begin", "preview", "resume"])
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--temporary", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.repo_root).resolve()
    try:
        if args.action == "begin":
            state = begin(root, args.run_id, temporary=args.temporary)
        elif args.action == "resume":
            state = resume(root)
        else:
            found = load_record(root)
            state = found[1] if found else {"phase": "not-started", "inputs": input_manifest(root)}
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"Closeout blocked: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
