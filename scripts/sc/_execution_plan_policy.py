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

REQUIRED_COORDINATION_SIGNALS = {
    "known_cross_session",
    "ordered_behavior_slices",
    "partial_work_recovery",
    "authority_migration",
    "staged_large_refactor",
    "workflow_control_plane",
}
RECOMMENDED_COORDINATION_SIGNALS = {
    "boundary_investigation",
    "cross_session_risk",
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
    decision: str


def _parse_fields(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        match = FIELD_LINE_RE.match(raw_line.strip())
        if match:
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
                key = (str(entry.get("anchor") or "").strip(), str(entry.get("text") or "").strip())
                if key in seen:
                    continue
                seen.add(key)
                existing.append({"anchor": key[0], "text": key[1]})
    return by_ref


def _test_root_for_ref(ref: str) -> str:
    normalized = str(ref or "").strip().replace("\\", "/")
    for prefix in TEST_ROOT_PREFIXES:
        if normalized.startswith(prefix):
            return prefix.rstrip("/")
    return normalized.split("/", 1)[0] if normalized else ""


def assess_execution_plan_need(
    *,
    repo_root: Path,
    triplet: Any,
    task_id: str,
    tdd_stage: str,
    verify: str,
    coordination_signals: list[str] | None = None,
) -> ExecutionPlanAssessment:
    by_ref = _iter_allowed_refs(triplet=triplet, task_id=task_id)
    allowed_refs = sorted(by_ref.keys())
    missing_refs = [ref for ref in allowed_refs if not (repo_root / ref).exists()]
    anchor_count = sum(len(by_ref.get(ref, [])) for ref in allowed_refs)
    test_roots = sorted({_test_root_for_ref(ref) for ref in missing_refs if _test_root_for_ref(ref)})

    normalized = {
        str(item or "").strip().lower().replace("-", "_")
        for item in (coordination_signals or [])
        if str(item or "").strip()
    }
    unknown = sorted(normalized - REQUIRED_COORDINATION_SIGNALS - RECOMMENDED_COORDINATION_SIGNALS)
    required = sorted(normalized & REQUIRED_COORDINATION_SIGNALS)
    recommended = sorted(normalized & RECOMMENDED_COORDINATION_SIGNALS)

    signals: list[dict[str, Any]] = []
    for signal_id in sorted(REQUIRED_COORDINATION_SIGNALS):
        signals.append({
            "id": signal_id,
            "active": signal_id in normalized,
            "level": "required",
            "detail": "explicit durable recovery/coordination requirement",
        })
    for signal_id in sorted(RECOMMENDED_COORDINATION_SIGNALS):
        signals.append({
            "id": signal_id,
            "active": signal_id in normalized,
            "level": "recommended",
            "detail": "explicit investigation/cross-session risk",
        })
    for signal_id in unknown:
        signals.append({
            "id": signal_id,
            "active": True,
            "level": "unknown",
            "detail": "unknown coordination signal; operator must resolve before escalation",
        })

    decision = "required" if required else "recommended" if recommended or unknown else "none"
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
        threshold_hit=decision in {"required", "recommended"},
        decision=decision,
    )


def find_active_execution_plans(root: Path, *, task_id: str) -> list[str]:
    plan_dir = root / "execution-plans"
    if not plan_dir.is_dir():
        return []
    matches: list[str] = []
    for path in sorted(plan_dir.glob("*.md")):
        if path.name.upper() in {"README.MD", "TEMPLATE.MD"}:
            continue
        fields = _parse_fields(path)
        if str(fields.get("Status") or "").strip().lower() not in ACTIVE_PLAN_STATUSES:
            continue
        if str(task_id) not in _extract_task_ids(fields.get("Related task id(s)", "")):
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
    title_text = f"Task {task_id} durable execution plan"
    if title:
        title_text = f"Task {task_id} {title} durable execution plan"
    active = [item["id"] for item in assessment.signals if item.get("active")]
    content = build_execution_plan_markdown(
        root=repo_root,
        title=title_text,
        status="active",
        goal=f"Preserve durable recovery and ordered coordination for task {task_id}.",
        scope=f"Execution-plan decision={assessment.decision}; coordination signals={', '.join(active) or 'none'}.",
        current_step="Record the current durable stage and the next ordered behavior slice.",
        stop_loss="Do not duplicate information already represented by run sidecars; update this plan only for durable cross-step recovery.",
        next_action="Continue from the first incomplete durable stage using the bound task/run evidence.",
        exit_criteria="All required ordered stages are complete and recovery no longer depends on cross-session coordination.",
        related_adrs=[],
        related_decision_logs=[],
        links=infer_recovery_links(root=repo_root, task_id=task_id, latest_json=latest_json),
        branch=resolve_git_branch(repo_root),
        git_head=resolve_git_head(repo_root),
    )
    out_path = ensure_output_path(repo_root, "", "execution-plans", title_text)
    write_markdown(out_path, content)
    return format_repo_path(repo_root, out_path)
