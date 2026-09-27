"""Repository-specific guard for a frozen Chapter 3 task identity set."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG = Path("docs/workflows/chapter3-task-scope.json")


def load_scope(root: Path) -> dict[str, Any] | None:
    path = root / CONFIG
    if not path.is_file():
        return None
    scope = json.loads(path.read_text(encoding="utf-8"))
    if scope.get("schema_version") != "chapter3.task-scope.v1" or scope.get("mode") != "reconcile-existing-only":
        raise ValueError("Unsupported Chapter 3 task scope")
    return scope


def allowed_ids(scope: dict[str, Any]) -> set[int]:
    bounds = scope["allowed_numeric_task_ids"]
    result = set(range(int(bounds["first"]), int(bounds["last"]) + 1))
    if len(result) != int(scope["expected_master_task_count"]):
        raise ValueError("Frozen task scope count does not match ID bounds")
    return result


def validate_master(root: Path, scope: dict[str, Any]) -> set[int]:
    path = root / scope["master_path"]
    rows = json.loads(path.read_text(encoding="utf-8"))["master"]["tasks"]
    ids = [row["id"] for row in rows]
    expected = allowed_ids(scope)
    if len(ids) != len(expected) or set(ids) != expected:
        raise ValueError("Master task IDs differ from frozen Chapter 3 baseline")
    return expected


def validate_candidate_operations(operations: list[dict[str, Any]], allowed: set[int]) -> None:
    for operation in operations:
        if operation.get("action") == "create":
            raise ValueError(f"Frozen task scope rejects new task {operation.get('id')}")
        task_id = operation.get("taskmaster_id")
        if task_id is not None and task_id not in allowed:
            raise ValueError(f"Frozen task scope rejects numeric task {task_id}")
