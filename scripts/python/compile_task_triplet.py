#!/usr/bin/env python3
"""Compile task candidates into Taskmaster triplet view files.

Default mode writes a patch preview only. Use --write to update tasks_back.json or
tasks_gameplay.json, then run build_taskmaster_tasks.py and Chapter 3.3 validators.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

TASKS_DIR = Path(".taskmaster/tasks")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def json_text(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_text(data), encoding="utf-8")


def canonical_sha(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def atomic_write_many(updates: list[tuple[Path, Any]]) -> None:
    staged: list[tuple[Path, Path]] = []
    originals: dict[Path, bytes | None] = {}
    try:
        for path, payload in updates:
            path.parent.mkdir(parents=True, exist_ok=True)
            originals[path] = path.read_bytes() if path.exists() else None
            fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
            os.close(fd)
            temp_path = Path(temp_name)
            temp_path.write_text(json_text(payload), encoding="utf-8")
            staged.append((path, temp_path))
        for path, temp_path in staged:
            os.replace(temp_path, path)
    except Exception:
        for path, original in originals.items():
            if original is None:
                path.unlink(missing_ok=True)
            else:
                path.write_bytes(original)
        raise
    finally:
        for _path, temp_path in staged:
            temp_path.unlink(missing_ok=True)


def normalize_task(candidate: dict[str, Any], target: str) -> dict[str, Any]:
    task = {
        "id": str(candidate.get("id")),
        "story_id": str(candidate.get("story_id") or "TASK-GENERATION"),
        "title": str(candidate.get("title") or candidate.get("id")),
        "description": str(candidate.get("description") or ""),
        "status": str(candidate.get("status") or "pending"),
        "priority": str(candidate.get("priority") or "P2"),
        "layer": str(candidate.get("layer") or "feature"),
        "depends_on": list(candidate.get("depends_on") or []),
        "dependency_status": str(candidate.get("dependency_status") or "provisional"),
        "dependency_reason": str(candidate.get("dependency_reason") or "Chapter 3 dependency skeleton"),
        "adr_refs": list(candidate.get("adr_refs") or []),
        "chapter_refs": list(candidate.get("chapter_refs") or []),
        "overlay_refs": list(candidate.get("overlay_refs") or []),
        "labels": sorted(set(list(candidate.get("labels") or []) + [target, "generated"])),
        "owner": str(candidate.get("owner") or ("gameplay" if target == "gameplay" else "architecture")),
        "test_refs": list(candidate.get("test_refs") or []),
        "acceptance": list(candidate.get("acceptance") or []),
        "test_strategy": list(candidate.get("test_strategy") or []),
        "contractRefs": list(candidate.get("contractRefs") or []),
        "evidence_refs": list(candidate.get("evidence_refs") or []),
        "source_refs": list(candidate.get("source_refs") or []),
        "requirement_ids": list(candidate.get("requirement_ids") or []),
        "semantic_refs": list(candidate.get("semantic_refs") or candidate.get("requirement_ids") or []),
        "capability_refs": list(candidate.get("capability_refs") or []),
        "complexity_score": int(candidate.get("complexity_score") or 1),
        "implementation_files": list(candidate.get("implementation_files") or []),
        "implementation_overlap_candidates": list(candidate.get("implementation_overlap_candidates") or []),
        "file_churn_signal": str(candidate.get("file_churn_signal") or "low"),
        "taskmaster_exported": False,
        "semantic_review_tier": "targeted",
    }
    return task


def target_for(candidate: dict[str, Any]) -> str:
    owner = str(candidate.get("owner", "")).lower()
    labels = {str(x).lower() for x in candidate.get("labels", [])}
    if owner == "gameplay" or "gdd" in labels or "gameplay" in labels:
        return "gameplay"
    return "back"


def _candidate_action(candidate: dict[str, Any], exists: bool) -> str:
    raw = str(candidate.get("change_action") or candidate.get("operation") or "").strip().lower()
    if raw:
        if raw not in {"create", "update", "reuse", "retire"}:
            raise ValueError(f"unsupported change_action for {candidate.get('id')}: {raw}")
        return raw
    return "conflict" if exists else "create"


def _field_patch(candidate: dict[str, Any], normalized: dict[str, Any]) -> dict[str, Any]:
    explicit = candidate.get("field_updates")
    if isinstance(explicit, dict):
        return {str(key): value for key, value in explicit.items()}
    return {}


def build_change_plan(
    existing: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    target: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    by_id = {str(row.get("id")): row for row in existing if isinstance(row, dict)}
    updated = [dict(row) if isinstance(row, dict) else row for row in existing]
    index_by_id = {
        str(row.get("id")): idx
        for idx, row in enumerate(updated)
        if isinstance(row, dict) and str(row.get("id") or "").strip()
    }
    operations: list[dict[str, Any]] = []
    conflicts: list[str] = []
    for candidate in candidates:
        normalized = normalize_task(candidate, target)
        tid = str(normalized["id"])
        current = by_id.get(tid)
        action = _candidate_action(candidate, current is not None)
        if action == "conflict":
            conflicts.append(tid)
            operations.append({
                "id": tid,
                "action": "blocked",
                "reason": "existing-id-requires-explicit-update-or-reuse",
                "old_fingerprint": canonical_sha(current),
            })
            continue
        if action == "create":
            if current is not None:
                conflicts.append(tid)
                operations.append({
                    "id": tid,
                    "action": "blocked",
                    "reason": "create-id-already-exists",
                    "old_fingerprint": canonical_sha(current),
                })
                continue
            updated.append(normalized)
            index_by_id[tid] = len(updated) - 1
            operations.append({"id": tid, "action": "create", "field_diff": normalized})
            continue
        if current is None:
            conflicts.append(tid)
            operations.append({"id": tid, "action": "blocked", "reason": f"{action}-target-missing"})
            continue
        if action == "reuse":
            operations.append({
                "id": tid,
                "action": "reuse",
                "old_fingerprint": canonical_sha(current),
                "field_diff": {},
            })
            continue
        patch = _field_patch(candidate, normalized)
        if action == "retire" and not patch:
            patch = {"status": "cancelled"}
        if not patch:
            conflicts.append(tid)
            operations.append({
                "id": tid,
                "action": "blocked",
                "reason": "update-requires-field_updates",
                "old_fingerprint": canonical_sha(current),
            })
            continue
        before = dict(current)
        after = dict(current)
        after.update(patch)
        updated[index_by_id[tid]] = after
        operations.append({
            "id": tid,
            "action": action,
            "old_fingerprint": canonical_sha(before),
            "field_diff": {
                key: {"before": before.get(key), "after": after.get(key)}
                for key in patch
                if before.get(key) != after.get(key)
            },
        })
    return updated, operations, conflicts


def main() -> int:
    parser = argparse.ArgumentParser(description="Compile task candidates into task triplet view files.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--candidates", default="logs/ci/task-generation/task-candidates.enriched.json")
    parser.add_argument("--coverage", default="logs/ci/task-generation/coverage-report.json")
    parser.add_argument("--mode", choices=["init", "add"], default="add")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--out", default="logs/ci/task-generation/task-triplet.patch.json")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    candidates = load_json(root / args.candidates, {}).get("candidates", [])
    coverage = load_json(root / args.coverage, {"status": "unknown"})
    if coverage.get("status") != "ok":
        raise SystemExit("coverage report is not ok; refusing to compile triplet")
    tasks_dir = root / TASKS_DIR
    back_path = tasks_dir / "tasks_back.json"
    gameplay_path = tasks_dir / "tasks_gameplay.json"
    back_existing = load_json(back_path, [])
    gameplay_existing = load_json(gameplay_path, [])
    if not isinstance(back_existing, list) or not isinstance(gameplay_existing, list):
        raise SystemExit("task view files must be JSON lists")

    back_new: list[dict[str, Any]] = []
    gameplay_new: list[dict[str, Any]] = []
    for candidate in candidates:
        target = target_for(candidate)
        if target == "gameplay":
            gameplay_new.append(normalize_task(candidate, "gameplay"))
        else:
            back_new.append(normalize_task(candidate, "back"))
    back_updated, back_ops, back_conflicts = build_change_plan(back_existing, back_new, "back")
    gameplay_updated, gameplay_ops, gameplay_conflicts = build_change_plan(gameplay_existing, gameplay_new, "gameplay")
    conflicts = sorted(set(back_conflicts + gameplay_conflicts))
    patch = {
        "schema": "task-generation.triplet-patch.v2",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": args.mode,
        "write": args.write,
        "source_fingerprints": {
            "tasks_back": canonical_sha(back_existing),
            "tasks_gameplay": canonical_sha(gameplay_existing),
        },
        "tasks_back_operations": back_ops,
        "tasks_gameplay_operations": gameplay_ops,
        "conflicts": conflicts,
        "next_commands": [
            "py -3 scripts/python/build_taskmaster_tasks.py --tasks-file .taskmaster/tasks/tasks_back.json --tasks-file .taskmaster/tasks/tasks_gameplay.json --ids-file logs/ci/task-generation/task-triplet.export-ids.json",
            "py -3 scripts/python/task_links_validate.py",
            "py -3 scripts/python/check_tasks_all_refs.py",
            "py -3 scripts/python/validate_task_master_triplet.py",
            "py -3 scripts/python/backfill_semantic_review_tier.py --mode conservative --write",
            "py -3 scripts/python/validate_semantic_review_tier.py --mode conservative",
        ],
    }
    out = root / args.out
    write_json(out, patch)
    export_ids = [
        row["id"]
        for row in back_ops + gameplay_ops
        if row.get("action") in {"create", "update", "reuse", "retire"}
    ]
    export_ids_path = root / "logs/ci/task-generation/task-triplet.export-ids.json"
    write_json(export_ids_path, export_ids)
    if args.write:
        if conflicts:
            raise SystemExit("task triplet patch has conflicts; refusing to write: " + ", ".join(conflicts))
        current_back = load_json(back_path, [])
        current_gameplay = load_json(gameplay_path, [])
        if canonical_sha(current_back) != patch["source_fingerprints"]["tasks_back"] or canonical_sha(current_gameplay) != patch["source_fingerprints"]["tasks_gameplay"]:
            raise SystemExit("task view changed after preview calculation; regenerate patch")
        atomic_write_many([(back_path, back_updated), (gameplay_path, gameplay_updated)])
        print(f"wrote back_ops={len(back_ops)} gameplay_ops={len(gameplay_ops)}")
    print(
        f"triplet_patch={out} back_candidates={len(back_new)} gameplay_candidates={len(gameplay_new)} "
        f"conflicts={len(conflicts)} write={args.write}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

