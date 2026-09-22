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
_FINDING_ID_RE = re.compile(r"\{finding_id=([^}]+)\}")
_LOW_PRIORITY = {"P2", "P3", "P4"}
_SEVERITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}


def _debt_severities_for_fix_through(fix_through: str) -> set[str]:
    threshold = str(fix_through or "P1").strip().upper()
    threshold_rank = _SEVERITY_RANK.get(threshold, 1)
    return {severity for severity, rank in _SEVERITY_RANK.items() if rank > threshold_rank}


def _normalize_relpath(path: Path, *, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _stable_finding_id(*, agent: str, severity: str, message: str) -> str:
    digest = hashlib.sha256(f"{agent}\n{severity}\n{message}".encode("utf-8")).hexdigest()[:16]
    return f"review-{digest}"


def _parse_review_markdown(text: str, *, agent: str = "") -> list[dict[str, str]]:
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
                findings.append({
                    "finding_id": _stable_finding_id(agent=agent, severity=severity, message=message),
                    "severity": severity,
                    "message": message,
                })
            continue
        if current_severity not in _LOW_PRIORITY:
            continue
        message = _BULLET_PREFIX_RE.sub("", line).strip()
        if message:
            findings.append({
                "finding_id": _stable_finding_id(agent=agent, severity=current_severity, message=message),
                "severity": current_severity,
                "message": message,
            })
    return findings


def _load_pipeline_child_review_summary(*, summary: dict[str, Any], root: Path) -> tuple[dict[str, Any] | None, str]:
    steps = summary.get("steps") if isinstance(summary.get("steps"), list) else []
    llm_step = next(
        (
            step for step in steps
            if isinstance(step, dict) and str(step.get("name") or "").strip() == "sc-llm-review"
        ),
        None,
    )
    if not isinstance(llm_step, dict):
        return None, "llm_review_not_executed"
    status = str(llm_step.get("status") or "").strip().lower()
    if status in {"planned", "skipped", ""}:
        return None, "llm_review_not_executed"
    raw_path = str(llm_step.get("summary_file") or "").strip()
    if not raw_path:
        return None, "llm_review_summary_missing"
    path = Path(raw_path)
    if not path.is_absolute():
        path = root / path
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, "llm_review_summary_invalid"
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        return None, "llm_review_summary_invalid"
    return payload, "ok"


def collect_low_priority_review_findings(
    *,
    summary: dict[str, Any],
    root: Path | None = None,
    fix_through: str = "P1",
) -> list[dict[str, str]]:
    root_dir = root or repo_root()
    results = summary.get("results") or []
    findings: list[dict[str, str]] = []
    seen: set[str] = set()
    allowed_severities = _debt_severities_for_fix_through(fix_through)
    if not isinstance(results, list):
        return findings
    for result in results:
        if not isinstance(result, dict):
            continue
        output_raw = str(result.get("output_path") or "").strip()
        agent = str(result.get("agent") or "").strip() or "single-reviewer"
        details = result.get("details") if isinstance(result.get("details"), dict) else {}
        contract = details.get("review_contract") if isinstance(details.get("review_contract"), dict) else None
        structured_findings = contract.get("findings") if isinstance(contract, dict) and isinstance(contract.get("findings"), list) else None

        if structured_findings is not None:
            for raw in structured_findings:
                if not isinstance(raw, dict):
                    continue
                severity = str(raw.get("severity") or "").strip().upper()
                disposition = raw.get("disposition") if isinstance(raw.get("disposition"), dict) else {}
                if severity not in allowed_severities:
                    continue
                if str(disposition.get("action") or "").strip().lower() != "defer":
                    continue
                message = str(raw.get("claim") or "").strip()
                if not message:
                    continue
                finding_id = str(raw.get("finding_id") or "").strip() or _stable_finding_id(
                    agent=agent,
                    severity=severity,
                    message=message,
                )
                if finding_id in seen:
                    continue
                seen.add(finding_id)
                findings.append(
                    {
                        "finding_id": finding_id,
                        "severity": severity,
                        "agent": agent,
                        "message": message,
                        "source_path": output_raw.replace("\\", "/"),
                        "source_status": str(result.get("status") or ""),
                    }
                )
            continue

        if not output_raw:
            continue
        output_path = Path(output_raw)
        if not output_path.is_absolute():
            output_path = root_dir / output_path
        if not output_path.exists():
            continue
        text = output_path.read_text(encoding="utf-8", errors="ignore")
        for item in _parse_review_markdown(text, agent=agent):
            severity = str(item.get("severity") or "").strip().upper()
            if severity not in allowed_severities:
                continue
            finding_id = str(item.get("finding_id") or "").strip()
            if not finding_id or finding_id in seen:
                continue
            seen.add(finding_id)
            findings.append(
                {
                    "finding_id": finding_id,
                    "severity": severity,
                    "agent": agent,
                    "message": item["message"],
                    "source_path": _normalize_relpath(output_path, root=root_dir),
                    "source_status": str(result.get("status") or ""),
                }
            )
    return findings

def collect_explicit_debt_dispositions(*, summary: dict[str, Any]) -> dict[str, str]:
    dispositions: dict[str, str] = {}
    results = summary.get("results")
    if not isinstance(results, list):
        return dispositions
    for result in results:
        if not isinstance(result, dict) or str(result.get("status") or "").strip().lower() != "ok":
            continue
        details = result.get("details") if isinstance(result.get("details"), dict) else {}
        contract = details.get("review_contract") if isinstance(details.get("review_contract"), dict) else None
        if not isinstance(contract, dict) or str(contract.get("completion_status") or "").strip() != "completed":
            continue
        findings = contract.get("findings")
        if not isinstance(findings, list):
            continue
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            finding_id = str(finding.get("finding_id") or "").strip()
            disposition = finding.get("disposition") if isinstance(finding.get("disposition"), dict) else {}
            action = str(disposition.get("action") or "").strip().lower()
            rationale = str(disposition.get("rationale") or "").strip()
            evidence = finding.get("evidence")
            verification = str(finding.get("verification") or "").strip()
            if (
                finding_id
                and action == "reject"
                and rationale
                and verification
                and isinstance(evidence, list)
                and any(str(item or "").strip() for item in evidence)
            ):
                dispositions[finding_id] = "rejected"
    return dispositions


def collect_pipeline_debt_dispositions(
    *,
    pipeline_summary: dict[str, Any],
    root: Path | None = None,
) -> tuple[dict[str, str], str]:
    root_dir = root or repo_root()
    child, reason = _load_pipeline_child_review_summary(summary=pipeline_summary, root=root_dir)
    if child is None:
        return {}, reason
    return collect_explicit_debt_dispositions(summary=child), "ok"


def collect_pipeline_low_priority_findings(
    *,
    pipeline_summary: dict[str, Any],
    root: Path | None = None,
    fix_through: str = "P1",
) -> tuple[list[dict[str, str]], str]:
    root_dir = root or repo_root()
    child, reason = _load_pipeline_child_review_summary(summary=pipeline_summary, root=root_dir)
    if child is None:
        return [], reason
    return collect_low_priority_review_findings(
        summary=child,
        root=root_dir,
        fix_through=fix_through,
    ), "ok"


def _base_document() -> str:
    return "\n".join(
        [
            "# Technical Debt Register",
            "",
            "This file is updated by `scripts/sc/run_review_pipeline.py`.",
            "",
            "- P0/P1 findings stay in the must-fix path and should not be parked here.",
            "- Only `P2/P3/P4` items from `sc-llm-review` are recorded here, grouped by task.",
            "- A narrow re-review updates only covered findings; unrelated existing debt remains until explicit verified disposition.",
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
    return prepared[:start], prepared[start + len(_BEGIN):end], prepared[end + len(_END):]


def _parse_sections(body: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    for match in _TASK_SECTION_RE.finditer(body.strip()):
        sections[str(match.group("task_id"))] = str(match.group(0)).strip()
    return sections


def _parse_existing_findings(section: str) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    severity = ""
    for raw in str(section or "").splitlines():
        heading = _HEADING_RE.match(raw)
        if heading:
            severity = str(heading.group(1)).upper()
            continue
        line = raw.strip()
        if not line.startswith("- ") or severity not in _LOW_PRIORITY:
            continue
        message = line[2:].strip()
        if message.startswith(("last_updated:", "latest_run_id:", "delivery_profile:")):
            continue
        match = _FINDING_ID_RE.search(message)
        finding_id = str(match.group(1)).strip() if match else _stable_finding_id(
            agent="legacy",
            severity=severity,
            message=message,
        )
        clean = _FINDING_ID_RE.sub("", message).strip()
        findings.append({
            "finding_id": finding_id,
            "severity": severity,
            "agent": "legacy",
            "message": clean,
            "source_path": "",
        })
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
        for item in items:
            finding_id = str(item.get("finding_id") or "").strip()
            agent = str(item.get("agent") or "").strip() or "single-reviewer"
            message = str(item.get("message") or "").strip()
            source_path = str(item.get("source_path") or "").strip()
            suffix = f" {{finding_id={finding_id}}}" if finding_id else ""
            if source_path:
                lines.append(f"- [{agent}] {message}{suffix} (`{source_path}`)")
            else:
                lines.append(f"- [{agent}] {message}{suffix}")
        lines.append("")
    return "\n".join(lines).rstrip()


def update_technical_debt_register(
    *,
    doc_path: Path,
    task_id: str,
    run_id: str,
    findings: list[dict[str, str]],
    delivery_profile: str,
    dispositions: dict[str, str] | None = None,
) -> dict[str, Any]:
    ensure_dir(doc_path.parent)
    original = doc_path.read_text(encoding="utf-8") if doc_path.exists() else _base_document()
    prefix, body, suffix = _split_document(original)
    sections = _parse_sections(body)
    existing = _parse_existing_findings(sections.get(str(task_id), ""))
    merged: dict[str, dict[str, str]] = {
        str(item.get("finding_id") or ""): item
        for item in existing
        if str(item.get("finding_id") or "").strip()
    }
    for item in findings:
        finding_id = str(item.get("finding_id") or "").strip()
        if not finding_id:
            finding_id = _stable_finding_id(
                agent=str(item.get("agent") or "single-reviewer"),
                severity=str(item.get("severity") or ""),
                message=str(item.get("message") or ""),
            )
            item = {**item, "finding_id": finding_id}
        merged[finding_id] = item
    for finding_id, disposition in (dispositions or {}).items():
        if str(disposition or "").strip().lower() in {"resolved", "rejected", "closed"}:
            merged.pop(str(finding_id), None)

    if merged:
        sections[str(task_id)] = _render_task_section(
            task_id=str(task_id),
            run_id=str(run_id),
            findings=list(merged.values()),
            delivery_profile=delivery_profile,
        )
        status = "updated"
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
        "item_count": len(merged),
        "reviewed_item_count": len(findings),
        "path": str(doc_path),
    }


def write_low_priority_debt_artifacts(
    *,
    out_dir: Path,
    summary: dict[str, Any],
    task_id: str,
    run_id: str,
    delivery_profile: str,
    fix_through: str = "P1",
    root: Path | None = None,
) -> dict[str, Any]:
    root_dir = root or repo_root()
    findings_path = out_dir / "llm-review-low-priority-findings.json"
    findings, source_status = collect_pipeline_low_priority_findings(
        pipeline_summary=summary,
        root=root_dir,
        fix_through=fix_through,
    )
    dispositions, disposition_status = collect_pipeline_debt_dispositions(
        pipeline_summary=summary,
        root=root_dir,
    )
    if source_status != "ok":
        payload = {
            "cmd": "sc-review-pipeline",
            "task_id": str(task_id),
            "run_id": str(run_id),
            "delivery_profile": str(delivery_profile),
            "item_count": 0,
            "findings": [],
            "register": {
                "status": "skipped",
                "reason": source_status,
                "path": str(root_dir / "docs" / "technical-debt.md"),
            },
        }
        write_json(findings_path, payload)
        return {
            "findings_path": str(findings_path),
            "register_path": str(root_dir / "docs" / "technical-debt.md"),
            "item_count": 0,
            "register_status": "skipped",
            "reason": source_status,
        }

    payload = {
        "cmd": "sc-review-pipeline",
        "task_id": str(task_id),
        "run_id": str(run_id),
        "delivery_profile": str(delivery_profile),
        "item_count": len(findings),
        "findings": findings,
        "source": "steps.sc-llm-review.summary_file",
    }
    write_json(findings_path, payload)
    register_result = update_technical_debt_register(
        doc_path=root_dir / "docs" / "technical-debt.md",
        task_id=str(task_id),
        run_id=str(run_id),
        findings=findings,
        delivery_profile=str(delivery_profile),
        dispositions=dispositions if disposition_status == "ok" else None,
    )
    payload["register"] = register_result
    write_json(findings_path, payload)
    return {
        "findings_path": str(findings_path),
        "register_path": str(root_dir / "docs" / "technical-debt.md"),
        "item_count": len(findings),
        "register_status": register_result["status"],
        "reason": "ok",
    }
