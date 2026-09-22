from __future__ import annotations

import json
from pathlib import Path

from _taskmaster_paths import resolve_default_task_triplet_paths
from _util import repo_root


def normalize_task_root_id(task_id: str | None) -> str | None:
    raw = str(task_id or "").strip()
    if not raw:
        return None
    return raw.split(".", 1)[0].strip()


def _iter_bound_test_refs(item: dict) -> list[str]:
    refs: list[str] = []
    test_refs = item.get("test_refs")
    if isinstance(test_refs, list):
        refs.extend(str(value).replace("\\", "/").strip() for value in test_refs if isinstance(value, str) and value.strip())

    verification = item.get("acceptance_verification")
    if isinstance(verification, dict):
        for raw in verification.values():
            if not isinstance(raw, dict):
                continue
            obligations = raw.get("obligations")
            rows = obligations if isinstance(obligations, list) else [raw]
            for row in rows:
                if not isinstance(row, dict):
                    continue
                for key in ("primary_evidence", "secondary_evidence"):
                    values = row.get(key)
                    if not isinstance(values, list):
                        continue
                    refs.extend(
                        str(value).replace("\\", "/").strip()
                        for value in values
                        if isinstance(value, str) and value.strip()
                    )

    seen: set[str] = set()
    ordered: list[str] = []
    for ref in refs:
        key = ref.casefold()
        if not ref or key in seen:
            continue
        seen.add(key)
        ordered.append(ref)
    return ordered


def task_scoped_gdunit_refs(*, task_id: str | None, tests_project: Path) -> list[str]:
    task_root_id = normalize_task_root_id(task_id)
    if not task_root_id:
        return []

    refs: list[str] = []
    seen: set[str] = set()
    _tasks_json, tasks_back_path, tasks_gameplay_path = resolve_default_task_triplet_paths(repo_root())
    view_files = [tasks_back_path, tasks_gameplay_path]
    for view_path in view_files:
        if not view_path.is_file():
            continue
        try:
            data = json.loads(view_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            if str(item.get("taskmaster_id")).strip() != task_root_id:
                continue
            for ref in _iter_bound_test_refs(item):
                if not ref.lower().endswith(".gd"):
                    continue
                rel: str | None = None
                if ref.startswith("Tests.Godot/"):
                    rel = ref[len("Tests.Godot/") :]
                elif ref.startswith("tests/"):
                    rel = ref
                if not rel or not (tests_project / rel).is_file() or rel in seen:
                    continue
                seen.add(rel)
                refs.append(rel)
    return refs


def task_scoped_cs_refs(*, task_id: str | None) -> list[str]:
    task_root_id = normalize_task_root_id(task_id)
    if not task_root_id:
        return []

    refs: list[str] = []
    seen: set[str] = set()
    _tasks_json, tasks_back_path, tasks_gameplay_path = resolve_default_task_triplet_paths(repo_root())
    view_files = [tasks_back_path, tasks_gameplay_path]
    for view_path in view_files:
        if not view_path.is_file():
            continue
        try:
            data = json.loads(view_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        for item in data:
            if not isinstance(item, dict):
                continue
            if str(item.get("taskmaster_id")).strip() != task_root_id:
                continue
            for ref in _iter_bound_test_refs(item):
                if not ref.lower().endswith(".cs"):
                    continue
                if not ref.startswith("Game.Core.Tests/"):
                    continue
                if not (repo_root() / ref).is_file() or ref in seen:
                    continue
                seen.add(ref)
                refs.append(ref)
    return refs


def build_dotnet_filter_from_cs_refs(cs_refs: list[str]) -> str:
    clauses: list[str] = []
    seen: set[str] = set()
    for ref in cs_refs:
        stem = Path(ref).stem.strip()
        if not stem:
            continue
        clause = f"FullyQualifiedName~{stem}"
        if clause in seen:
            continue
        seen.add(clause)
        clauses.append(clause)
    return "|".join(clauses)
