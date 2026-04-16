#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_TASK_ID = 39
DEFAULT_REQUIRED_ADR = "ADR-0010"
DEFAULT_REQUIRED_TEST_REFS = [
    "Tests.Godot/tests/Tasks/test_task0039_acceptance.gd",
    "Game.Core.Tests/Tasks/Task0039AcceptanceTests.cs",
]
DEFAULT_REQUIRED_EVIDENCE = [
    "scripts/python/verify_m1_translations.py",
    "Test-Refs",
]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _find_task(payload: Any, task_id: int) -> dict[str, Any] | None:
    if not isinstance(payload, list):
        return None
    for item in payload:
        if not isinstance(item, dict):
            continue
        if int(item.get("taskmaster_id", -1)) == task_id:
            return item
    return None


def _to_rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def main() -> int:
    parser = argparse.ArgumentParser(description="Task39 traceability gate for ADR-0010 and test refs linkage.")
    parser.add_argument("--task-id", type=int, default=DEFAULT_TASK_ID)
    parser.add_argument(
        "--task-file",
        default=".taskmaster/tasks/tasks_gameplay.json",
        help="Task view JSON file path.",
    )
    parser.add_argument(
        "--overlay-index",
        default="docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/_index.md",
        help="Overlay index markdown path.",
    )
    parser.add_argument(
        "--overlay-checklist",
        default="docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md",
        help="Overlay checklist markdown path.",
    )
    parser.add_argument("--require-adr", default=DEFAULT_REQUIRED_ADR)
    parser.add_argument(
        "--require-test-ref",
        action="append",
        dest="required_test_refs",
        default=[],
        help="Required test refs; repeat this option for multiple refs.",
    )
    parser.add_argument(
        "--require-evidence-token",
        action="append",
        dest="required_evidence_tokens",
        default=[],
        help="Required token that must appear in both overlay index and checklist.",
    )
    parser.add_argument(
        "--output",
        default="logs/ci/manual/task-39-traceability-gate.json",
        help="Output JSON summary path.",
    )
    args = parser.parse_args()

    root = _repo_root()
    task_file = Path(args.task_file)
    if not task_file.is_absolute():
        task_file = root / task_file
    overlay_index = Path(args.overlay_index)
    if not overlay_index.is_absolute():
        overlay_index = root / overlay_index
    overlay_checklist = Path(args.overlay_checklist)
    if not overlay_checklist.is_absolute():
        overlay_checklist = root / overlay_checklist
    output = Path(args.output)
    if not output.is_absolute():
        output = root / output

    required_test_refs = list(args.required_test_refs or [])
    if not required_test_refs:
        required_test_refs = list(DEFAULT_REQUIRED_TEST_REFS)
    required_tokens = list(args.required_evidence_tokens or [])
    if not required_tokens:
        required_tokens = list(DEFAULT_REQUIRED_EVIDENCE)

    errors: list[str] = []
    warnings: list[str] = []

    if not task_file.is_file():
        errors.append(f"task_file_missing::{_to_rel(root, task_file)}")
        task_payload: Any = []
    else:
        task_payload = _load_json(task_file)

    task = _find_task(task_payload, int(args.task_id))
    if task is None:
        errors.append(f"task_not_found::{args.task_id}")
        task = {}

    adr_refs = task.get("adr_refs") if isinstance(task.get("adr_refs"), list) else []
    test_refs = task.get("test_refs") if isinstance(task.get("test_refs"), list) else []

    required_adr = str(args.require_adr).strip()
    if required_adr and required_adr not in [str(item) for item in adr_refs]:
        errors.append(f"task_missing_required_adr::{required_adr}")

    normalized_test_refs = [str(item).strip().replace("\\", "/") for item in test_refs if str(item).strip()]
    for ref in required_test_refs:
        if ref not in normalized_test_refs:
            errors.append(f"task_missing_required_test_ref::{ref}")

    index_text = _read_text(overlay_index)
    checklist_text = _read_text(overlay_checklist)
    if not index_text:
        errors.append(f"overlay_index_missing_or_empty::{_to_rel(root, overlay_index)}")
    if not checklist_text:
        errors.append(f"overlay_checklist_missing_or_empty::{_to_rel(root, overlay_checklist)}")

    for token in [required_adr, *required_test_refs, *required_tokens]:
        token_text = str(token).strip()
        if not token_text:
            continue
        if index_text and token_text not in index_text:
            errors.append(f"overlay_index_missing_token::{token_text}")
        if checklist_text and token_text not in checklist_text:
            errors.append(f"overlay_checklist_missing_token::{token_text}")

    status = "ok" if not errors else "fail"
    payload = {
        "schema_version": "1.0.0",
        "task_id": int(args.task_id),
        "status": status,
        "task_file": _to_rel(root, task_file),
        "overlay_index": _to_rel(root, overlay_index),
        "overlay_checklist": _to_rel(root, overlay_checklist),
        "required_adr": required_adr,
        "required_test_refs": required_test_refs,
        "required_evidence_tokens": required_tokens,
        "errors": errors,
        "warnings": warnings,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        "TASK39_TRACEABILITY_GATE "
        f"status={status} "
        f"errors={len(errors)} "
        f"warnings={len(warnings)} "
        f"out={output}"
    )
    return 0 if status == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())

