from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SC_DIR = Path(__file__).resolve().parent
PYTHON_DIR = SC_DIR.parent / "python"
for candidate in (SC_DIR, PYTHON_DIR):
    text = str(candidate)
    if text not in sys.path:
        sys.path.insert(0, text)

from _acceptance_testgen_refs import extract_acceptance_refs_with_anchors, is_allowed_test_path
from _recovery_doc_scaffold import (
    build_execution_plan_markdown,
    ensure_output_path,
    format_repo_path,
    infer_recovery_links,
    resolve_git_branch,
    resolve_git_head,
    write_markdown,
)


ACTIVE_PLAN_STATUSES = {"active", "paused", "blocked"}
FIELD_LINE_RE = re.compile(r"^- ([^:]+):\s*(.*)$")
TASK_ID_RE = re.compile(r"\b\d+\b")
TEST_ROOT_PREFIXES = ("Game.Core.Tests/", "Tests.Godot/tests/", "Tests/")
REQUIRED_PLAN_SIGNALS = {
    "cross-session",
    "ordered-behavior-slices",
    "partial-resume",
    "authority-migration",
    "large-refactor",
    "mvg-integration",
    "workflow-control-plane",
}
RECOMMENDED_PLAN_SIGNALS = {
    "boundary-investigation",
    "cross-session-risk",
}


@dataclass(frozen=True)
class ExecutionPlanAssessment:
    task_id: str
    title: str
    refs_total: int
    allowed_refs: list[str]
    missing_refs: list[str]
    missing_refs_count: int
    anchor_count: int
    test_roots: list[str]
    signals: list[dict[str, Any]]
    threshold_hit: bool
    need_level: str
    reason_codes: list[str]


def _parse_fields(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        match = FIELD_LINE_RE.match(raw_line.strip())
        if not match:
            continue
        fields[match.group(1).strip()] = match.group(2).strip()
    return fields


def _extract_task_ids(value: str) -> set[str]:
    return {match.group(0) for match in TASK_ID_RE.finditer(str(value or ""))}


def _iter_allowed_refs(*, triplet: Any, task_id: str) -> dict[str, list[dict[str, str]]]:
    by_ref: dict[str, list[dict[str, str]]] = {}
    for acceptance in ((triplet.back or {}).get("acceptance"), (triplet.gameplay or {}).get("acceptance")):
        mapping = extract_acceptance_refs_with_anchors(acceptance=acceptance, task_id=task_id)
        for ref, entries in mapping.items():
            normalized = str(ref or "").strip().replace("\\", "/")
            if not normalized or not is_allowed_test_path(normalized):
                continue
            existing = by_ref.setdefault(normalized, [])
            seen = {(item.get("anchor", ""), item.get("text", "")) for item in existing}
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                anchor = str(entry.get("anchor") or "").strip()
                text = str(entry.get("text") or "").strip()
                key = (anchor, text)
                if key in seen:
                    continue
                seen.add(key)
                existing.append({"anchor": anchor, "text": text})
    return by_ref


def _test_root_for_ref(ref: str) -> str:
    normalized = str(ref or "").strip().replace("\\", "/")
    for prefix in TEST_ROOT_PREFIXES:
        if normalized.startswith(prefix):
            return prefix.rstrip("/")
    return normalized.split("/", 1)[0] if normalized else ""


def _declared_plan_signals(triplet: Any) -> set[str]:
    signals: set[str] = set()
    for row in (getattr(triplet, "master", None), getattr(triplet, "back", None), getattr(triplet, "gameplay", None)):
        if not isinstance(row, dict):
            continue
        raw = row.get("execution_plan_signals")
        if isinstance(raw, list):
            signals.update(str(item).strip().lower() for item in raw if str(item).strip())
        plan_meta = row.get("execution_plan") if isinstance(row.get("execution_plan"), dict) else {}
        raw_meta = plan_meta.get("signals")
        if isinstance(raw_meta, list):
            signals.update(str(item).strip().lower() for item in raw_meta if str(item).strip())
    return signals


def assess_execution_plan_need(
    *,
    repo_root: Path,
    triplet: Any,
    task_id: str,
    tdd_stage: str,
    verify: str,
    plan_signals: list[str] | None = None,
    plan_reason: str = "",
) -> ExecutionPlanAssessment:
    by_ref = _iter_allowed_refs(triplet=triplet, task_id=task_id)
    allowed_refs = sorted(by_ref.keys())
    missing_refs = [ref for ref in allowed_refs if not (repo_root / ref).exists()]
    anchor_count = sum(len(by_ref.get(ref, [])) for ref in allowed_refs)
    test_roots = sorted({_test_root_for_ref(ref) for ref in missing_refs if _test_root_for_ref(ref)})

    declared = _declared_plan_signals(triplet)
    declared.update(str(item).strip().lower() for item in (plan_signals or []) if str(item).strip())
    unknown = sorted(declared - REQUIRED_PLAN_SIGNALS - RECOMMENDED_PLAN_SIGNALS)
    required = sorted(declared & REQUIRED_PLAN_SIGNALS)
    recommended = sorted(declared & RECOMMENDED_PLAN_SIGNALS)
    if required:
        need_level = "required"
        reason_codes = required
    elif recommended:
        need_level = "recommended"
        reason_codes = recommended
    else:
        need_level = "none"
        reason_codes = []

    signals = [
        {
            "id": signal_id,
            "active": signal_id in declared,
            "level": "required" if signal_id in REQUIRED_PLAN_SIGNALS else "recommended",
            "detail": str(plan_reason or "").strip() if signal_id in declared and str(plan_reason or "").strip() else "declared persistent coordination signal",
        }
        for signal_id in sorted(REQUIRED_PLAN_SIGNALS | RECOMMENDED_PLAN_SIGNALS)
    ]
    signals.extend(
        {
            "id": f"unknown:{signal_id}",
            "active": True,
            "level": "unknown",
            "detail": "unknown signals never create a required plan",
        }
        for signal_id in unknown
    )

    return ExecutionPlanAssessment(
        task_id=str(task_id),
        title=str((triplet.master or {}).get("title") or "").strip(),
        refs_total=len(allowed_refs),
        allowed_refs=allowed_refs,
        missing_refs=missing_refs,
        missing_refs_count=len(missing_refs),
        anchor_count=anchor_count,
        test_roots=test_roots,
        signals=signals,
        threshold_hit=need_level == "required",
        need_level=need_level,
        reason_codes=reason_codes,
    )


def find_active_execution_plans(root: Path, *, task_id: str) -> list[str]:
    plan_dir = root / "execution-plans"
    if not plan_dir.is_dir():
        return []
    matches: list[str] = []
    for path in sorted(plan_dir.glob("*.md")):
        upper = path.name.upper()
        if upper in {"README.MD", "TEMPLATE.MD"}:
            continue
        fields = _parse_fields(path)
        status = str(fields.get("Status") or "").strip().lower()
        if status not in ACTIVE_PLAN_STATUSES:
            continue
        task_ids = _extract_task_ids(fields.get("Related task id(s)", ""))
        if str(task_id) not in task_ids:
            continue
        matches.append(format_repo_path(root, path))
    return matches


def create_execution_plan_draft(
    *,
    repo_root: Path,
    task_id: str,
    title: str,
    assessment: ExecutionPlanAssessment,
    latest_json: str = "",
) -> str:
    title_text = f"Task {task_id} acceptance-test generation plan"
    if title:
        title_text = f"Task {task_id} {title} acceptance-test generation plan"
    scope_refs = ", ".join(assessment.missing_refs[:3]) if assessment.missing_refs else "no missing refs detected"
    if len(assessment.missing_refs) > 3:
        scope_refs += ", ..."
    content = build_execution_plan_markdown(
        root=repo_root,
        title=title_text,
        status="active",
        goal=f"Preserve resumable ordered execution for task {task_id}.",
        scope=(
            f"Persistent coordination reasons: {', '.join(assessment.reason_codes) or 'none'}; "
            f"acceptance refs remain evidence only ({assessment.refs_total} refs, {assessment.missing_refs_count} currently missing)."
        ),
        current_step="Execute the first ordered behavior slice while recording verified checkpoints.",
        stop_loss="Stop on authority migration ambiguity, unrecoverable partial state, or a failed required verification boundary.",
        next_action="Continue the ordered task work from the latest verified checkpoint.",
        exit_criteria="All required ordered/migration checkpoints are complete and resumable evidence is current.",
        related_adrs=[],
        related_decision_logs=[],
        links=infer_recovery_links(root=repo_root, task_id=task_id, latest_json=latest_json),
        branch=resolve_git_branch(repo_root),
        git_head=resolve_git_head(repo_root),
    )
    out_path = ensure_output_path(repo_root, "", "execution-plans", title_text)
    write_markdown(out_path, content)
    return format_repo_path(repo_root, out_path)
