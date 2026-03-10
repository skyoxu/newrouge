#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sync overlay mappings for Taskmaster triplet files via overlay-manifest.json."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


OVERLAY_PRD_RE = re.compile(r"^docs/architecture/overlays/([^/]+)/08(?:/|$)")
VALID_PRD_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
MANIFEST_FILE_NAME = "overlay-manifest.json"
MANIFEST_KEYS = ("index", "feature", "contracts", "testing", "observability", "acceptance")


@dataclass(frozen=True)
class OverlayPaths:
    prd_id: str
    base: str
    manifest: str
    index: str
    feature: str
    contracts: str
    testing: str
    observability: str
    acceptance: str

@dataclass(frozen=True)
class FileSyncResult:
    file: str
    total_tasks: int
    changed_tasks: int
    changed_ids: list[str]

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _today() -> str:
    return dt.date.today().isoformat()


def _to_posix(path: str) -> str:
    return path.replace("\\", "/")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def _validate_prd_id(prd_id: str) -> str:
    value = prd_id.strip()
    if not value:
        raise ValueError("Empty PRD id is not allowed.")
    if not VALID_PRD_ID_RE.fullmatch(value):
        raise ValueError(f"Invalid PRD id '{prd_id}'. Allowed chars: [A-Za-z0-9._-].")
    return value


def _normalize_refs(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return []

def _extract_prd_ids_from_values(values: list[str]) -> set[str]:
    found: set[str] = set()
    for value in values:
        candidate = _to_posix(str(value).strip())
        match = OVERLAY_PRD_RE.match(candidate)
        if match:
            found.add(match.group(1))
    return found


def _extract_prd_ids_from_master_tasks(payload: Any) -> set[str]:
    found: set[str] = set()
    if not isinstance(payload, dict):
        return found
    master = payload.get("master")
    if not isinstance(master, dict):
        return found
    tasks = master.get("tasks")
    if not isinstance(tasks, list):
        return found
    for task in tasks:
        if not isinstance(task, dict):
            continue
        overlay = str(task.get("overlay", "")).strip()
        found.update(_extract_prd_ids_from_values([overlay]))
    return found


def _extract_prd_ids_from_view_tasks(payload: Any) -> set[str]:
    found: set[str] = set()
    if not isinstance(payload, list):
        return found
    for task in payload:
        if not isinstance(task, dict):
            continue
        refs = _normalize_refs(task.get("overlay_refs"))
        found.update(_extract_prd_ids_from_values(refs))
    return found


def _auto_detect_prd_id(root: Path, tasks_dir: Path) -> str:
    task_candidates: set[str] = set()
    task_files = [
        tasks_dir / "tasks.json",
        tasks_dir / "tasks_back.json",
        tasks_dir / "tasks_gameplay.json",
    ]
    for file_path in task_files:
        if not file_path.exists():
            continue
        payload = _load_json(file_path)
        if file_path.name == "tasks.json":
            task_candidates.update(_extract_prd_ids_from_master_tasks(payload))
        else:
            task_candidates.update(_extract_prd_ids_from_view_tasks(payload))

    if len(task_candidates) == 1:
        return next(iter(task_candidates))
    if len(task_candidates) > 1:
        ordered = sorted(task_candidates)
        raise ValueError(
            f"Auto-detect found multiple PRD IDs in task files: {ordered}. Use --prd-id."
        )

    overlays_root = root / "docs" / "architecture" / "overlays"
    fs_candidates: list[str] = []
    if overlays_root.exists():
        for folder in overlays_root.iterdir():
            if not folder.is_dir() or folder.name.startswith("_"):
                continue
            manifest = folder / "08" / MANIFEST_FILE_NAME
            if manifest.exists():
                fs_candidates.append(folder.name)

    if len(fs_candidates) == 1:
        return fs_candidates[0]
    if len(fs_candidates) > 1:
        ordered = sorted(fs_candidates)
        raise ValueError(
            f"Auto-detect found multiple PRD IDs in overlays: {ordered}. Use --prd-id."
        )
    raise ValueError("Cannot auto-detect PRD ID. Use --prd-id.")


def _resolve_prd_id(root: Path, tasks_dir: Path, explicit_prd_id: str | None) -> str:
    if explicit_prd_id and explicit_prd_id.strip():
        return _validate_prd_id(explicit_prd_id)
    return _auto_detect_prd_id(root, tasks_dir)


def _resolve_overlay_file(base: str, value: object) -> str:
    raw = _to_posix(str(value).strip())
    if not raw:
        raise ValueError("Overlay manifest contains empty path value.")
    if raw.startswith("docs/"):
        return raw
    return f"{base}/{raw.lstrip('./')}"


def _load_overlay_paths_from_manifest(root: Path, prd_id: str) -> OverlayPaths:
    safe_prd_id = _validate_prd_id(prd_id)
    base = f"docs/architecture/overlays/{safe_prd_id}/08"
    manifest = f"{base}/{MANIFEST_FILE_NAME}"
    manifest_path = root / manifest
    if not manifest_path.exists():
        raise ValueError(f"Missing overlay manifest: {manifest}")

    payload = _load_json(manifest_path)
    if not isinstance(payload, dict):
        raise ValueError(f"Overlay manifest must be object: {manifest}")

    manifest_prd_id = str(payload.get("prd_id", "")).strip()
    if manifest_prd_id and manifest_prd_id != safe_prd_id:
        raise ValueError(
            f"Manifest prd_id mismatch: expected '{safe_prd_id}', got '{manifest_prd_id}'."
        )

    files = payload.get("files")
    if not isinstance(files, dict):
        raise ValueError(f"Overlay manifest missing 'files' object: {manifest}")

    missing = [key for key in MANIFEST_KEYS if key not in files]
    if missing:
        raise ValueError(f"Overlay manifest missing keys {missing}: {manifest}")

    return OverlayPaths(
        prd_id=safe_prd_id,
        base=base,
        manifest=manifest,
        index=_resolve_overlay_file(base, files["index"]),
        feature=_resolve_overlay_file(base, files["feature"]),
        contracts=_resolve_overlay_file(base, files["contracts"]),
        testing=_resolve_overlay_file(base, files["testing"]),
        observability=_resolve_overlay_file(base, files["observability"]),
        acceptance=_resolve_overlay_file(base, files["acceptance"]),
    )


def _ensure_overlay_files_exist(root: Path, paths: OverlayPaths) -> list[str]:
    required = [
        paths.manifest,
        paths.index,
        paths.feature,
        paths.contracts,
        paths.testing,
        paths.observability,
        paths.acceptance,
    ]
    return [rel for rel in required if not (root / rel).exists()]


def _refs_for_task(taskmaster_id: int, paths: OverlayPaths) -> list[str]:
    if 1 <= taskmaster_id <= 10:
        return [paths.index, paths.feature, paths.testing, paths.acceptance]
    if 11 <= taskmaster_id <= 20:
        return [paths.index, paths.feature, paths.contracts, paths.testing, paths.acceptance]
    if 21 <= taskmaster_id <= 30:
        return [paths.index, paths.feature, paths.testing, paths.observability, paths.acceptance]
    if 31 <= taskmaster_id <= 40:
        return [paths.index, paths.feature, paths.contracts, paths.testing, paths.observability, paths.acceptance]
    return [paths.index]


def _master_overlay_for_task(task_id: int, paths: OverlayPaths) -> str:
    _ = task_id
    return paths.index


def sync_master(tasks_json_path: Path, paths: OverlayPaths) -> tuple[dict[str, Any], FileSyncResult]:
    payload = _load_json(tasks_json_path)
    master = payload.get("master")
    if not isinstance(master, dict):
        raise ValueError("tasks.json missing top-level 'master' object.")
    tasks = master.get("tasks")
    if not isinstance(tasks, list):
        raise ValueError("tasks.json missing 'master.tasks' list.")

    changed_ids: list[str] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        task_id = task.get("id")
        if not isinstance(task_id, int):
            continue
        expected = _master_overlay_for_task(task_id, paths)
        current = str(task.get("overlay", "")).strip()
        if current != expected:
            task["overlay"] = expected
            changed_ids.append(str(task_id))

    return payload, FileSyncResult(
        file=str(tasks_json_path),
        total_tasks=len(tasks),
        changed_tasks=len(changed_ids),
        changed_ids=changed_ids,
    )


def sync_view(view_path: Path, paths: OverlayPaths) -> tuple[list[dict[str, Any]], FileSyncResult]:
    tasks = _load_json(view_path)
    if not isinstance(tasks, list):
        raise ValueError(f"{view_path.name} must be a JSON array.")

    changed_ids: list[str] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        raw_tm_id = task.get("taskmaster_id")
        task_id = str(task.get("id", "")).strip()
        taskmaster_id = raw_tm_id if isinstance(raw_tm_id, int) else None
        if taskmaster_id is None and isinstance(raw_tm_id, str) and raw_tm_id.isdigit():
            taskmaster_id = int(raw_tm_id)
        if taskmaster_id is None:
            m = re.search(r"(\d+)$", task_id)
            taskmaster_id = int(m.group(1)) if m else None
        if taskmaster_id is None:
            continue
        expected = _refs_for_task(taskmaster_id, paths)
        current = _normalize_refs(task.get("overlay_refs"))
        if current != expected:
            task["overlay_refs"] = expected
            changed_ids.append(task_id or str(taskmaster_id))

    return tasks, FileSyncResult(
        file=str(view_path),
        total_tasks=len(tasks),
        changed_tasks=len(changed_ids),
        changed_ids=changed_ids,
    )


def _write_summary(
    root: Path,
    dry_run: bool,
    status: str,
    reason: str | None,
    paths: OverlayPaths | None,
    results: list[FileSyncResult],
    missing: list[str],
) -> Path:
    out_dir = root / "logs" / "ci" / _today() / "task-overlays"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "sync-overlay-refs-summary.json"
    summary = {
        "action": "sync-task-overlay-refs",
        "dry_run": dry_run,
        "status": status,
        "reason": reason,
        "prd_id": paths.prd_id if paths else None,
        "overlay_base": paths.base if paths else None,
        "manifest": paths.manifest if paths else None,
        "missing_overlay_files": missing,
        "files": [
            {
                "file": item.file.replace("\\", "/"),
                "total_tasks": item.total_tasks,
                "changed_tasks": item.changed_tasks,
                "changed_ids": item.changed_ids,
            }
            for item in results
        ],
    }
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize Taskmaster overlay mappings (master/back/gameplay).")
    parser.add_argument("--dry-run", action="store_true", help="Compute and log changes without writing files.")
    parser.add_argument(
        "--prd-id",
        type=str,
        default="",
        help="PRD id in docs/architecture/overlays/<PRD-ID>. Auto-detect if omitted.",
    )
    parser.add_argument(
        "--tasks-dir",
        type=str,
        default=".taskmaster/tasks",
        help="Taskmaster tasks directory (default: .taskmaster/tasks).",
    )
    args = parser.parse_args()

    root = _repo_root()
    tasks_dir = (root / args.tasks_dir).resolve()
    tasks_json_path = tasks_dir / "tasks.json"
    tasks_back_path = tasks_dir / "tasks_back.json"
    tasks_gameplay_path = tasks_dir / "tasks_gameplay.json"

    try:
        prd_id = _resolve_prd_id(root, tasks_dir, args.prd_id)
        paths = _load_overlay_paths_from_manifest(root, prd_id)
    except ValueError as error:
        summary_path = _write_summary(root, args.dry_run, "fail", str(error), None, [], [])
        print(f"SYNC_TASK_OVERLAY_REFS status=fail reason={error} summary={summary_path.as_posix()}")
        return 2

    missing = _ensure_overlay_files_exist(root, paths)
    if missing:
        summary_path = _write_summary(root, args.dry_run, "fail", "missing-overlay-files", paths, [], missing)
        print(f"SYNC_TASK_OVERLAY_REFS status=fail missing={len(missing)} summary={summary_path.as_posix()}")
        for rel in missing:
            print(f"- missing overlay file: {rel}")
        return 2

    master_payload, master_result = sync_master(tasks_json_path, paths)
    back_payload, back_result = sync_view(tasks_back_path, paths)
    gameplay_payload, gameplay_result = sync_view(tasks_gameplay_path, paths)
    results = [master_result, back_result, gameplay_result]

    if not args.dry_run:
        _write_json(tasks_json_path, master_payload)
        _write_json(tasks_back_path, back_payload)
        _write_json(tasks_gameplay_path, gameplay_payload)

    status = "dry-run" if args.dry_run else "ok"
    summary_path = _write_summary(root, args.dry_run, status, None, paths, results, [])
    total_changed = sum(item.changed_tasks for item in results)
    print(
        "SYNC_TASK_OVERLAY_REFS "
        f"status={status} total_changed={total_changed} summary={summary_path.as_posix()}"
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
