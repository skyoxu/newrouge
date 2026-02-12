#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lock obligations baseline from LLM verdicts and apply deterministic acceptance diffs.

This script is a stop-loss tool for semantic drift:
1) Read latest obligations verdicts (from sc-llm-obligations-task-<id>/verdict.json).
2) Freeze uncovered obligations into a baseline file.
3) Deterministically append baseline lines to tasks_back/tasks_gameplay acceptance.
4) Verify baseline lines are present in both views.

Windows examples:
  py -3 scripts/sc/obligations_baseline_sync.py --task-ids 6,8,11,12 --refresh-baseline --apply --verify
  py -3 scripts/sc/obligations_baseline_sync.py --task-ids 6,8,11,12 --verify
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def _bootstrap_imports() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))


_bootstrap_imports()

from _taskmaster import default_paths, load_json  # noqa: E402
from _util import ci_dir, repo_root, write_json, write_text  # noqa: E402


REFS_RE = re.compile(r"\s*Refs\s*:\s*.+$", re.IGNORECASE)


def _parse_task_ids(csv_text: str) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for raw in (csv_text or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        if not raw.isdigit():
            raise ValueError(f"Invalid task id: {raw}")
        value = int(raw)
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _detect_newline(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    return "\r\n" if "\r\n" in text else "\n"


def _write_json_preserve_newline(path: Path, payload: Any, newline: str) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if newline == "\r\n":
        text = text.replace("\n", "\r\n")
    path.write_text(text, encoding="utf-8")


def _normalize_acceptance_text(text: str) -> str:
    value = str(text or "").strip()
    value = REFS_RE.sub("", value).strip()
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _find_latest_verdict(task_id: int) -> Path | None:
    root = repo_root() / "logs" / "ci"
    pattern = f"**/sc-llm-obligations-task-{task_id}/verdict.json"
    matches = [p for p in root.glob(pattern) if p.is_file()]
    if not matches:
        return None
    matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0]


def _load_or_init_baseline(path: Path) -> dict[str, Any]:
    if path.exists():
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(obj, dict):
                obj.setdefault("version", 1)
                obj.setdefault("tasks", {})
                if isinstance(obj.get("tasks"), dict):
                    return obj
        except Exception:
            pass
    return {"version": 1, "tasks": {}}


def _build_task_baseline(task_id: int, verdict: dict[str, Any], verdict_path: Path) -> dict[str, Any]:
    uncovered_ids = [str(x) for x in (verdict.get("uncovered_obligation_ids") or [])]
    obligations = verdict.get("obligations") or []
    ob_map = {
        str(o.get("id")): o
        for o in obligations
        if isinstance(o, dict) and str(o.get("id") or "").strip()
    }
    entries: list[dict[str, Any]] = []
    for oid in uncovered_ids:
        item = ob_map.get(oid, {})
        text = _normalize_acceptance_text(str(item.get("text") or ""))
        suggestions_raw = item.get("suggested_acceptance") or []
        suggestions: list[str] = []
        for raw in suggestions_raw:
            s = _normalize_acceptance_text(str(raw or ""))
            if s and s not in suggestions:
                suggestions.append(s)
        if text and text not in suggestions:
            suggestions.append(text)
        acceptance_lines = [f"[OBL:T{task_id}.{oid}] {s}" for s in suggestions]
        entries.append(
            {
                "id": oid,
                "text": text,
                "kind": str(item.get("kind") or ""),
                "source": str(item.get("source") or ""),
                "suggestions": suggestions,
                "acceptance_lines": acceptance_lines,
            }
        )
    return {
        "task_id": task_id,
        "verdict_path": str(verdict_path.relative_to(repo_root())).replace("\\", "/"),
        "uncovered_count": len(uncovered_ids),
        "obligations": entries,
    }


def _find_view_task(view_tasks: list[dict[str, Any]], task_id: int) -> dict[str, Any] | None:
    for row in view_tasks:
        if not isinstance(row, dict):
            continue
        if row.get("taskmaster_id") == task_id:
            return row
    return None


def _apply_diff_to_view(view_tasks: list[dict[str, Any]], task_baseline: dict[str, Any]) -> tuple[int, list[str], bool]:
    task_id = int(task_baseline.get("task_id"))
    row = _find_view_task(view_tasks, task_id)
    if not row:
        return 0, [], True
    acceptance = row.get("acceptance")
    if not isinstance(acceptance, list):
        return 0, [f"task {task_id}: acceptance is not list"], False
    existing = {str(x).strip() for x in acceptance}
    added = 0
    errors: list[str] = []
    for obligation in task_baseline.get("obligations") or []:
        for line in obligation.get("acceptance_lines") or []:
            s = str(line or "").strip()
            if not s:
                continue
            if s in existing:
                continue
            acceptance.append(s)
            existing.add(s)
            added += 1
    return added, errors, False


def _verify_view(view_tasks: list[dict[str, Any]], task_baseline: dict[str, Any]) -> tuple[list[str], bool]:
    task_id = int(task_baseline.get("task_id"))
    row = _find_view_task(view_tasks, task_id)
    if not row:
        return [], True
    acceptance = row.get("acceptance")
    if not isinstance(acceptance, list):
        return [f"task {task_id}: acceptance is not list"], False
    existing = {str(x).strip() for x in acceptance}
    missing: list[str] = []
    for obligation in task_baseline.get("obligations") or []:
        oid = str(obligation.get("id") or "")
        for line in obligation.get("acceptance_lines") or []:
            s = str(line or "").strip()
            if s and s not in existing:
                missing.append(f"T{task_id}.{oid}: {s}")
    return missing, False


def main() -> int:
    ap = argparse.ArgumentParser(description="Lock obligations baseline and apply deterministic acceptance diff.")
    ap.add_argument("--task-ids", required=True, help="Comma-separated Taskmaster IDs, e.g. 6,8,11,12")
    ap.add_argument(
        "--baseline-file",
        default=".taskmaster/docs/obligations-baseline.json",
        help="Path to baseline file (default: .taskmaster/docs/obligations-baseline.json)",
    )
    ap.add_argument("--refresh-baseline", action="store_true", help="Refresh baseline from latest obligations verdicts.")
    ap.add_argument("--apply", action="store_true", help="Apply baseline diff to tasks_back/tasks_gameplay acceptance.")
    ap.add_argument("--verify", action="store_true", help="Verify baseline acceptance lines exist in both views.")
    args = ap.parse_args()

    task_ids = _parse_task_ids(args.task_ids)
    baseline_path = repo_root() / args.baseline_file
    baseline = _load_or_init_baseline(baseline_path)
    tasks_obj = baseline.get("tasks")
    if not isinstance(tasks_obj, dict):
        baseline["tasks"] = {}
        tasks_obj = baseline["tasks"]

    out_dir = ci_dir("sc-obligations-baseline-sync")
    errors: list[str] = []
    refreshed: list[int] = []

    if args.refresh_baseline:
        for task_id in task_ids:
            verdict_path = _find_latest_verdict(task_id)
            if not verdict_path:
                errors.append(f"task {task_id}: verdict.json not found")
                continue
            verdict = load_json(verdict_path)
            baseline_task = _build_task_baseline(task_id, verdict, verdict_path)
            tasks_obj[str(task_id)] = baseline_task
            refreshed.append(task_id)

    baseline["task_ids"] = sorted(task_ids)
    baseline["last_sync_mode"] = {
        "refresh_baseline": bool(args.refresh_baseline),
        "apply": bool(args.apply),
        "verify": bool(args.verify),
    }
    write_json(baseline_path, baseline)

    tasks_json_path, back_path, gameplay_path = default_paths()
    if not back_path.exists() or not gameplay_path.exists() or not tasks_json_path.exists():
        errors.append("required task files are missing under .taskmaster/tasks")

    added_back = 0
    added_gameplay = 0
    skipped_missing_view = {"back": [], "gameplay": []}
    verify_missing: dict[str, list[str]] = {}

    if args.apply and not errors:
        back_nl = _detect_newline(back_path)
        gameplay_nl = _detect_newline(gameplay_path)
        back_data = load_json(back_path)
        gameplay_data = load_json(gameplay_path)
        if not isinstance(back_data, list) or not isinstance(gameplay_data, list):
            errors.append("tasks_back.json or tasks_gameplay.json is not a JSON array")
        else:
            for task_id in task_ids:
                task_baseline = tasks_obj.get(str(task_id))
                if not isinstance(task_baseline, dict):
                    errors.append(f"task {task_id}: baseline not found")
                    continue
                added, err, skipped = _apply_diff_to_view(back_data, task_baseline)
                added_back += added
                errors.extend(err)
                if skipped:
                    skipped_missing_view["back"].append(task_id)
                added, err, skipped = _apply_diff_to_view(gameplay_data, task_baseline)
                added_gameplay += added
                errors.extend(err)
                if skipped:
                    skipped_missing_view["gameplay"].append(task_id)
            if not errors:
                _write_json_preserve_newline(back_path, back_data, back_nl)
                _write_json_preserve_newline(gameplay_path, gameplay_data, gameplay_nl)

    if args.verify and not errors:
        back_data = load_json(back_path)
        gameplay_data = load_json(gameplay_path)
        for task_id in task_ids:
            task_baseline = tasks_obj.get(str(task_id))
            if not isinstance(task_baseline, dict):
                errors.append(f"task {task_id}: baseline not found")
                continue
            missing_back, skipped_back = _verify_view(back_data, task_baseline)
            missing_gameplay, skipped_gameplay = _verify_view(gameplay_data, task_baseline)
            if missing_back:
                verify_missing[f"back:{task_id}"] = missing_back
            if missing_gameplay:
                verify_missing[f"gameplay:{task_id}"] = missing_gameplay
            if skipped_back:
                skipped_missing_view["back"].append(task_id)
            if skipped_gameplay:
                skipped_missing_view["gameplay"].append(task_id)

    summary = {
        "cmd": "sc-obligations-baseline-sync",
        "task_ids": task_ids,
        "baseline_file": str(baseline_path.relative_to(repo_root())).replace("\\", "/"),
        "refreshed_tasks": refreshed,
        "apply": bool(args.apply),
        "verify": bool(args.verify),
        "added": {"back": added_back, "gameplay": added_gameplay},
        "skipped_missing_view": {
            "back": sorted(set(skipped_missing_view["back"])),
            "gameplay": sorted(set(skipped_missing_view["gameplay"])),
        },
        "verify_missing": verify_missing,
        "errors": errors,
        "status": "ok" if (not errors and not verify_missing) else "fail",
        "out_dir": str(out_dir.relative_to(repo_root())).replace("\\", "/"),
    }

    write_json(out_dir / "summary.json", summary)
    lines = [
        "# obligations baseline sync",
        "",
        f"- status: {summary['status']}",
        f"- baseline: {summary['baseline_file']}",
        f"- refreshed_tasks: {','.join(str(x) for x in refreshed) if refreshed else '(none)'}",
        f"- added_back: {added_back}",
        f"- added_gameplay: {added_gameplay}",
    ]
    if verify_missing:
        lines.append("- verify_missing:")
        for key, values in verify_missing.items():
            lines.append(f"  - {key}: {len(values)}")
    if errors:
        lines.append("- errors:")
        for e in errors:
            lines.append(f"  - {e}")
    write_text(out_dir / "report.md", "\n".join(lines) + "\n")

    print(
        f"SC_OBLIGATIONS_BASELINE_SYNC status={summary['status']} "
        f"tasks={len(task_ids)} refreshed={len(refreshed)} "
        f"added_back={added_back} added_gameplay={added_gameplay} out={out_dir}"
    )
    return 0 if summary["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
