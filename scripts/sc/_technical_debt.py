from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from _util import ensure_dir, repo_root, today_str, write_json


_BEGIN = "<!-- BEGIN AUTO:RUN_REVIEW_PIPELINE_TECHNICAL_DEBT -->"
_END = "<!-- END AUTO:RUN_REVIEW_PIPELINE_TECHNICAL_DEBT -->"
_TASK_SECTION_RE = re.compile(r"(?ms)^## Task (?P<task_id>\d+)\n.*?(?=^## Task \d+\n|\Z)")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s*(P[0-4])\b.*$", flags=re.IGNORECASE)
_INLINE_RE = re.compile(r"^\s*(?:[-*]|\d+\.)?\s*(P[0-4])\b(?:\s*[:\-]\s*|\s+)(.+?)\s*$", flags=re.IGNORECASE)
_BULLET_PREFIX_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s*")
_VERDICT_RE = re.compile(r"^\s*Verdict\s*:", flags=re.IGNORECASE)
_LOW_PRIORITY = {"P2", "P3", "P4"}
_STRUCTURED_SEVERITY = {
    "P0": "P0",
    "P1": "P1",
    "P2": "P2",
    "P3": "P3",
    "P4": "P4",
    "HIGH": "P1",
    "MEDIUM": "P2",
    "LOW": "P3",
}
_RENDERED_FINDING_RE = re.compile(
    r"^- \[(?P<finding_id>[^\]]+)\] \[(?P<agent>[^\]]+)\] "
    r"(?P<message>.*?)(?: \(\`(?P<source_path>[^\`]+)\`\))?"
    r"(?: \[run:(?P<source_run>[^\]]+)\])?$"
)


def _normalize_relpath(path: Path, *, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _parse_review_markdown(text: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    current_severity: str | None = None
    for raw_line in str(text or "").splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        if _VERDICT_RE.match(line):
            current_severity = None
            continue
        heading_match = _HEADING_RE.match(line)
        if heading_match:
            current_severity = str(heading_match.group(1)).upper()
            continue
        inline_match = _INLINE_RE.match(line)
        if inline_match:
            severity = str(inline_match.group(1)).upper()
            message = str(inline_match.group(2)).strip()
            if severity in _LOW_PRIORITY and message:
                findings.append({"severity": severity, "message": message})
            continue
        if current_severity not in _LOW_PRIORITY:
            continue
        message = _BULLET_PREFIX_RE.sub("", line).strip()
        if message:
            findings.append({"severity": current_severity, "message": message})
    return findings


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _stable_finding_id(*, agent: str, severity: str, message: str, authority: str = "") -> str:
    material = "|".join(
        [
            str(agent or "").strip().casefold(),
            str(severity or "").strip().upper(),
            " ".join(str(message or "").split()).casefold(),
            str(authority or "").strip().casefold(),
        ]
    )
    return "finding-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _normalize_finding_severity(value: Any) -> str:
    return _STRUCTURED_SEVERITY.get(str(value or "").strip().upper(), "")


def _resolve_review_results(
    *,
    summary: dict[str, Any],
    root_dir: Path,
) -> tuple[list[dict[str, Any]], str, dict[str, Any]]:
    direct = summary.get("results")
    if isinstance(direct, list):
        return [row for row in direct if isinstance(row, dict)], "direct-results", summary

    llm_step = next(
        (
            step
            for step in (summary.get("steps") or [])
            if isinstance(step, dict) and str(step.get("name") or "") == "sc-llm-review"
        ),
        None,
    )
    if not isinstance(llm_step, dict) or str(llm_step.get("status") or "").strip().lower() != "ok":
        return [], "llm-review-not-executed", {}
    raw_summary_path = str(llm_step.get("summary_file") or "").strip()
    if not raw_summary_path:
        return [], "llm-review-summary-missing", {}
    summary_path = Path(raw_summary_path)
    if not summary_path.is_absolute():
        summary_path = root_dir / summary_path
    child = _read_json_object(summary_path)
    if str(child.get("status") or "").strip().lower() not in {"ok", "warn"}:
        return [], "llm-review-summary-invalid", child
    results = child.get("results")
    if not isinstance(results, list):
        return [], "llm-review-results-missing", child
    return [row for row in results if isinstance(row, dict)], _normalize_relpath(summary_path, root=root_dir), child


def _structured_findings_from_result(
    result: dict[str, Any],
    *,
    agent: str,
    source_path: str,
    source_run: str,
) -> list[dict[str, str]]:
    details = result.get("details") if isinstance(result.get("details"), dict) else {}
    raw = details.get("findings") if isinstance(details.get("findings"), list) else []
    findings: list[dict[str, str]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        severity = _normalize_finding_severity(row.get("severity"))
        message = str(row.get("claim") or row.get("message") or "").strip()
        if severity not in _LOW_PRIORITY or not message:
            continue
        authority = str(
            row.get("authority")
            or row.get("requirement_id")
            or row.get("acceptance_id")
            or ""
        ).strip()
        finding_id = str(row.get("finding_id") or "").strip() or _stable_finding_id(
            agent=agent,
            severity=severity,
            message=message,
            authority=authority,
        )
        findings.append(
            {
                "finding_id": finding_id,
                "severity": severity,
                "agent": agent,
                "message": message,
                "authority": authority,
                "source_path": source_path,
                "source_run": source_run,
            }
        )
    return findings


def collect_low_priority_review_findings(*, summary: dict[str, Any], root: Path | None = None) -> list[dict[str, str]]:
    root_dir = root or repo_root()
    results, _source, child_summary = _resolve_review_results(summary=summary, root_dir=root_dir)
    source_run = str(
        child_summary.get("run_id")
        or summary.get("run_id")
        or ""
    ).strip()
    findings: list[dict[str, str]] = []
    seen: set[str] = set()
    for result in results:
        output_path = Path(str(result.get("output_path") or "").strip())
        source_path = ""
        if str(output_path):
            if not output_path.is_absolute():
                output_path = root_dir / output_path
            source_path = _normalize_relpath(output_path, root=root_dir)
        agent = str(result.get("agent") or "").strip() or "chapter6-reviewer"

        structured = _structured_findings_from_result(
            result,
            agent=agent,
            source_path=source_path,
            source_run=source_run,
        )
        if structured:
            candidates = structured
        elif output_path.exists():
            candidates = []
            text = output_path.read_text(encoding="utf-8", errors="ignore")
            for item in _parse_review_markdown(text):
                finding_id = _stable_finding_id(
                    agent=agent,
                    severity=item["severity"],
                    message=item["message"],
                )
                candidates.append(
                    {
                        "finding_id": finding_id,
                        "severity": item["severity"],
                        "agent": agent,
                        "message": item["message"],
                        "authority": "",
                        "source_path": source_path,
                        "source_run": source_run,
                    }
                )
        else:
            candidates = []

        for item in candidates:
            finding_id = str(item.get("finding_id") or "").strip()
            if not finding_id or finding_id in seen:
                continue
            seen.add(finding_id)
            findings.append(item)
    return findings


def _reviewed_finding_ids(*, summary: dict[str, Any], root_dir: Path) -> set[str]:
    results, _source, child_summary = _resolve_review_results(summary=summary, root_dir=root_dir)
    reviewed: set[str] = set()
    for container in (child_summary, summary):
        scope = container.get("review_scope") if isinstance(container.get("review_scope"), dict) else {}
        reviewed.update(str(item).strip() for item in scope.get("finding_ids", []) if str(item).strip())
    for result in results:
        details = result.get("details") if isinstance(result.get("details"), dict) else {}
        scope = details.get("review_scope") if isinstance(details.get("review_scope"), dict) else {}
        reviewed.update(str(item).strip() for item in scope.get("finding_ids", []) if str(item).strip())
    return reviewed


def _base_document() -> str:
    return "\n".join(
        [
            "# Technical Debt Register",
            "",
            "This file is updated by `scripts/sc/run_review_pipeline.py`.",
            "",
            "- P0/P1 findings stay in the must-fix path and should not be parked here.",
            "- Only `P2/P3/P4` items from `sc-llm-review` are recorded here, grouped by task.",
            "",
            _BEGIN,
            _END,
            "",
        ]
    )


def _ensure_markers(text: str) -> str:
    if _BEGIN in text and _END in text:
        return text
    stripped = text.rstrip()
    if stripped:
        return stripped + "\n\n" + _BEGIN + "\n" + _END + "\n"
    return _base_document()


def _split_document(text: str) -> tuple[str, str, str]:
    prepared = _ensure_markers(text)
    start = prepared.index(_BEGIN)
    end = prepared.index(_END)
    prefix = prepared[:start]
    body = prepared[start + len(_BEGIN) : end]
    suffix = prepared[end + len(_END) :]
    return prefix, body, suffix


def _parse_sections(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    for match in _TASK_SECTION_RE.finditer(body.strip()):
        sections[str(match.group("task_id"))] = str(match.group(0)).strip()
    return sections


def _parse_rendered_findings(section: str) -> list[dict[str, str]]:
    current_severity = ""
    findings: list[dict[str, str]] = []
    for raw in str(section or "").splitlines():
        line = raw.strip()
        if line.startswith("### P"):
            current_severity = line[4:].strip().upper()
            continue
        match = _RENDERED_FINDING_RE.match(line)
        if not match or current_severity not in _LOW_PRIORITY:
            continue
        findings.append(
            {
                "finding_id": str(match.group("finding_id") or "").strip(),
                "severity": current_severity,
                "agent": str(match.group("agent") or "").strip(),
                "message": str(match.group("message") or "").strip(),
                "authority": "",
                "source_path": str(match.group("source_path") or "").strip(),
                "source_run": str(match.group("source_run") or "").strip(),
            }
        )
    return findings


def _render_task_section(*, task_id: str, run_id: str, findings: list[dict[str, str]], delivery_profile: str) -> str:
    grouped: dict[str, list[dict[str, str]]] = {"P2": [], "P3": [], "P4": []}
    for item in findings:
        sev = str(item.get("severity") or "").upper()
        if sev in grouped:
            grouped[sev].append(item)
    lines = [
        f"## Task {task_id}",
        f"- last_updated: {today_str()}",
        f"- latest_run_id: {run_id}",
        f"- delivery_profile: {delivery_profile}",
        "",
    ]
    for severity in ("P2", "P3", "P4"):
        items = grouped[severity]
        if not items:
            continue
        lines.append(f"### {severity}")
        for item in sorted(items, key=lambda row: str(row.get("finding_id") or "")):
            finding_id = str(item.get("finding_id") or "").strip() or _stable_finding_id(
                agent=str(item.get("agent") or ""),
                severity=severity,
                message=str(item.get("message") or ""),
                authority=str(item.get("authority") or ""),
            )
            agent = str(item.get("agent") or "").strip() or "chapter6-reviewer"
            message = str(item.get("message") or "").strip()
            source_path = str(item.get("source_path") or "").strip()
            source_run = str(item.get("source_run") or run_id).strip()
            line = f"- [{finding_id}] [{agent}] {message}"
            if source_path:
                line += f" (\`{source_path}\`)"
            if source_run:
                line += f" [run:{source_run}]"
            lines.append(line)
        lines.append("")
    return "\n".join(lines).rstrip()


def update_technical_debt_register(
    *,
    doc_path: Path,
    task_id: str,
    run_id: str,
    findings: list[dict[str, str]],
    delivery_profile: str,
    reviewed_finding_ids: set[str] | None = None,
) -> dict[str, Any]:
    ensure_dir(doc_path.parent)
    original = doc_path.read_text(encoding="utf-8") if doc_path.exists() else _base_document()
    prefix, body, suffix = _split_document(original)
    sections = _parse_sections(body)
    reviewed = {str(item).strip() for item in (reviewed_finding_ids or set()) if str(item).strip()}
    incoming = {
        str(item.get("finding_id") or "").strip(): item
        for item in findings
        if str(item.get("finding_id") or "").strip()
    }

    if reviewed:
        existing_findings = _parse_rendered_findings(sections.get(str(task_id), ""))
        merged = {
            str(item.get("finding_id") or "").strip(): item
            for item in existing_findings
            if str(item.get("finding_id") or "").strip() and str(item.get("finding_id") or "").strip() not in reviewed
        }
        merged.update(incoming)
        final_findings = list(merged.values())
    else:
        final_findings = list(incoming.values()) if incoming else list(findings)

    if final_findings:
        sections[str(task_id)] = _render_task_section(
            task_id=str(task_id),
            run_id=str(run_id),
            findings=final_findings,
            delivery_profile=delivery_profile,
        )
        status = "updated"
    elif reviewed:
        status = "removed_reviewed" if sections.pop(str(task_id), None) else "noop"
    else:
        status = "removed" if sections.pop(str(task_id), None) else "noop"

    ordered = "\n\n".join(section for _, section in sorted(sections.items(), key=lambda item: int(item[0])))
    new_text = prefix + _BEGIN + "\n"
    if ordered:
        new_text += ordered + "\n"
    new_text += _END + suffix
    doc_path.write_text(new_text, encoding="utf-8")
    return {
        "status": status,
        "task_id": str(task_id),
        "run_id": str(run_id),
        "item_count": len(final_findings),
        "reviewed_finding_ids": sorted(reviewed),
        "path": str(doc_path),
    }


def write_low_priority_debt_artifacts(
    *,
    out_dir: Path,
    summary: dict[str, Any],
    task_id: str,
    run_id: str,
    delivery_profile: str,
    root: Path | None = None,
) -> dict[str, Any]:
    root_dir = root or repo_root()
    findings_path = out_dir / "llm-review-low-priority-findings.json"
    _results, source_reason, _child = _resolve_review_results(summary=summary, root_dir=root_dir)
    if source_reason in {
        "llm-review-not-executed",
        "llm-review-summary-missing",
        "llm-review-summary-invalid",
        "llm-review-results-missing",
    }:
        payload = {
            "cmd": "sc-review-pipeline",
            "task_id": str(task_id),
            "run_id": str(run_id),
            "delivery_profile": str(delivery_profile),
            "item_count": 0,
            "findings": [],
            "register": {
                "status": "skipped",
                "reason": source_reason,
                "path": str(root_dir / "docs" / "technical-debt.md"),
            },
        }
        write_json(findings_path, payload)
        return {
            "findings_path": str(findings_path),
            "register_path": str(root_dir / "docs" / "technical-debt.md"),
            "item_count": 0,
            "register_status": "skipped",
            "reason": source_reason,
        }

    findings = collect_low_priority_review_findings(summary=summary, root=root_dir)
    reviewed_finding_ids = _reviewed_finding_ids(summary=summary, root_dir=root_dir)
    payload = {
        "cmd": "sc-review-pipeline",
        "task_id": str(task_id),
        "run_id": str(run_id),
        "delivery_profile": str(delivery_profile),
        "source": source_reason,
        "reviewed_finding_ids": sorted(reviewed_finding_ids),
        "item_count": len(findings),
        "findings": findings,
    }
    write_json(findings_path, payload)
    register_result = update_technical_debt_register(
        doc_path=root_dir / "docs" / "technical-debt.md",
        task_id=str(task_id),
        run_id=str(run_id),
        findings=findings,
        delivery_profile=str(delivery_profile),
        reviewed_finding_ids=reviewed_finding_ids,
    )
    payload["register"] = register_result
    write_json(findings_path, payload)
    return {
        "findings_path": str(findings_path),
        "register_path": str(root_dir / "docs" / "technical-debt.md"),
        "item_count": len(findings),
        "register_status": register_result["status"],
        "reviewed_finding_ids": sorted(reviewed_finding_ids),
    }

