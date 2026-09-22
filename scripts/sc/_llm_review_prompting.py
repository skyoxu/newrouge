#!/usr/bin/env python3
"""
Prompt and verdict helpers for llm_review.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from _llm_review_acceptance import read_text, truncate
from _taskmaster import TaskmasterTriplet
from _util import repo_root


_SURFACE_FOCUS_GUIDANCE = {
    "Save/Load": "Check reload, persistence identity, serialization compatibility, and idempotent restore behavior.",
    "Contract/EventBus": "Check producer/consumer compatibility, event identity, ordering assumptions, and contract evolution.",
    "UI/Scene": "Check input wiring, scene lifecycle, signal connections, visibility/state synchronization, and adapter boundaries.",
    "State Machine": "Check legal transitions, re-entry, partial transition failure, and state recovery.",
    "Security": "Check the real trust/safety boundary, input validation, path/process access, and fail-closed behavior.",
    "Performance": "Check hot loops, repeated allocations/work, bounded resource use, and performance evidence.",
}


def derive_surface_focus(changed_paths: list[str], *, limit: int = 3) -> list[dict[str, str]]:
    normalized = [str(path or "").strip().replace("\\", "/").casefold() for path in changed_paths if str(path or "").strip()]
    selectors = [
        ("Save/Load", ("save", "load", "snapshot", "serializ", "persist", "checkpoint")),
        ("Contract/EventBus", ("/contracts/", "contract", "/events/", "eventbus", "event_bus")),
        ("UI/Scene", ("game.godot/", "tests.godot/", ".tscn", "/ui/", "/scene", "scene/")),
        ("State Machine", ("state", "transition", "fsm", "state_machine", "statemachine")),
        ("Security", ("security", "permission", "sandbox", "trusted", "auth", "crypto", "pathguard", "path_guard")),
        ("Performance", ("performance", "benchmark", "workerthread", "worker_thread", "hotloop", "hot_loop")),
    ]
    selected: list[dict[str, str]] = []
    for name, tokens in selectors:
        matched = sorted({path for path in normalized if any(token in path for token in tokens)})
        if not matched:
            continue
        selected.append({
            "name": name,
            "reason": f"changed surface: {', '.join(matched[:3])}",
            "guidance": _SURFACE_FOCUS_GUIDANCE[name],
        })
        if len(selected) >= max(0, int(limit)):
            break
    return selected


def render_surface_focus_prompt(surface_focus: list[dict[str, str]]) -> str:
    if not surface_focus:
        return ""
    lines = [
        "## Selected Surface Focus",
        "Apply these focus checks in addition to the three required lenses; they are methods, not extra reviewer personas.",
    ]
    for item in surface_focus:
        lines.append(f"- {item['name']}: {item['guidance']} ({item['reason']})")
    return "\n".join(lines)


def build_task_context(triplet: TaskmasterTriplet | None, *, mode: str = "full") -> str:
    if not triplet:
        return ""
    normalized_mode = str(mode or "full").strip().lower()
    profiles = {
        "full": {
            "master_desc": 1200,
            "view_desc": 1200,
            "master_details": 2000,
            "view_details": 2000,
        },
        "semantic": {
            "master_desc": 900,
            "view_desc": 700,
            "master_details": 1200,
            "view_details": 800,
        },
        "compact": {
            "master_desc": 420,
            "view_desc": 260,
            "master_details": 720,
            "view_details": 360,
        },
    }
    profile = profiles.get(normalized_mode, profiles["full"])
    title = str(triplet.master.get("title") or "").strip()
    adr = ", ".join(triplet.adr_refs()) or "(none)"
    ch = ", ".join(triplet.arch_refs()) or "(none)"
    overlay = triplet.overlay() or "(none)"
    master_desc = truncate(str(triplet.master.get("description") or ""), max_chars=profile["master_desc"])
    back_desc = truncate(str((triplet.back or {}).get("description") or ""), max_chars=profile["view_desc"])
    gameplay_desc = truncate(str((triplet.gameplay or {}).get("description") or ""), max_chars=profile["view_desc"])
    master_details = truncate(str(triplet.master.get("details") or ""), max_chars=profile["master_details"])
    back_details = truncate(str((triplet.back or {}).get("details") or ""), max_chars=profile["view_details"])
    gameplay_details = truncate(str((triplet.gameplay or {}).get("details") or ""), max_chars=profile["view_details"])
    return "\n".join(
        [
            "Task Context:",
            f"- id: {triplet.task_id}",
            f"- title: {title}",
            f"- mode: {normalized_mode}",
            f"- adrRefs: {adr}",
            f"- archRefs: {ch}",
            f"- overlay: {overlay}",
            "",
            "Task Description (truncated):",
            f"- master.description: {master_desc or '(empty)'}",
            f"- tasks_back.description: {back_desc or '(empty)'}",
            f"- tasks_gameplay.description: {gameplay_desc or '(empty)'}",
            "",
            "Task Details (truncated):",
            f"- master.details: {master_details or '(empty)'}",
            f"- tasks_back.details: {back_details or '(empty)'}",
            f"- tasks_gameplay.details: {gameplay_details or '(empty)'}",
        ]
    )


def resolve_threat_model(value: str | None) -> str:
    s = str(value or "").strip().lower()
    if not s:
        s = str(os.environ.get("SC_THREAT_MODEL") or "").strip().lower()
    return s if s in {"singleplayer", "modded", "networked"} else "singleplayer"


def build_threat_model_context(threat_model: str) -> str:
    if threat_model == "networked":
        note = "Assume network features may exist or be added soon; prioritize boundary checks, rate limits, and allowlists."
    elif threat_model == "modded":
        note = "Assume mods/plugins may exist; prioritize trust boundaries, input validation, and stop-loss logging."
    else:
        note = "Single-player/offline default; prioritize deterministic correctness, resource limits, and avoid over-hardening."
    return "\n".join(["Threat Model:", f"- mode: {threat_model}", f"- guidance: {note}"])


def load_optional_agent_prompt(rel_path: str) -> str | None:
    p = repo_root() / rel_path
    if p.is_file():
        return read_text(p)
    return None


def default_agent_prompt(agent: str) -> str:
    if agent == "semantic-equivalence-auditor":
        return "\n".join(
            [
                "Role: semantic-equivalence-auditor",
                "",
                "Goal: determine whether the acceptance set is semantically equivalent to the task description.",
                "Important: do NOT re-run or restate deterministic gates (refs existence, anchors, ADR compliance, security/static scans).",
                "Assume sc-acceptance-check has already enforced those. Focus only on semantic coverage.",
                "",
                "How to judge equivalence:",
                "- Compare tasks.json master.description/details and the task view descriptions to acceptance items.",
                "- Identify missing behaviors/invariants/failure-semantics implied by the description but not present in acceptance.",
                "- Identify acceptance items that are too generic or unrelated (false coverage).",
                "- Prefer minimal changes: adjust acceptance wording, split/merge acceptance items, or point to the correct test file.",
                "",
                "Output a concise Markdown report with:",
                "- Missing semantic obligations (bullet list)",
                "- Acceptance items to rewrite/remove (bullet list)",
                "- Minimal delta proposal (exact acceptance lines to add/change)",
                "- Verdict: OK | Needs Fix (single line at the end)",
                "",
                "Stop-loss: If you cannot point to a concrete missing obligation implied by the description, set Verdict to OK.",
            ]
        )
    return "\n".join(
        [
            f"Role: {agent}",
            "",
            "Goal: judge whether the Task acceptance is truly completed (semantic, not only refs).",
            "Primary evidence: the 'Acceptance Semantics (anchors + referenced tests)' section.",
            "Secondary evidence: deterministic gates (acceptance_check/test/coverage/perf) and the diff.",
            "",
            "Output a concise Markdown report with:",
            "- P0/P1/P2/P3/P4 findings (if any)",
            "- specific file paths + what to change",
            "- call out weak tests (anchors present but no meaningful assertions)",
            "- call out missing negative/error-path tests when acceptance implies them",
            "- a short 'Verdict: OK | Needs Fix' line at the end",
            "",
            "Avoid speculative claims. Focus on deterministic evidence when present.",
            "Stop-loss: if the deterministic gates for this task are OK and you cannot point to a concrete missing behavior/test weakness, set Verdict to OK.",
        ]
    )


_VERDICT_RE = re.compile(r"(?mi)^\s*(?:#+\s*)?Verdict\s*:\s*(OK|Needs Fix)\s*$")
_ANTI_TAMPER_TERMS = (
    "anti-tamper",
    "anti tamper",
    "tamper",
    "hmac",
    "signature",
    "checksum",
    "chain hash",
    "chain-hash",
    "trusted publisher",
    "snapshot integrity",
    "save integrity",
    "anti-cheat",
    "anti cheat",
)
_HOST_SAFETY_BASELINE_TERMS = (
    "path traversal",
    "traversal",
    "res://",
    "user://",
    "os.execute",
    "dynamic load",
    "dynamic assembly",
    "https",
    "allowlist",
    "whitelist",
    "sql injection",
    "absolute path",
)
_HOST_SAFE_STRICT_INTENT_TERMS = (
    "security_profile=strict",
    "security_profile: strict",
    "strict profile",
    "anti-tamper required",
    "tamper-proof required",
    "hmac required",
    "signature required",
)


def parse_verdict(text: str) -> str | None:
    if not text:
        return None
    m = _VERDICT_RE.search(text)
    if not m:
        return None
    return str(m.group(1)).strip()


_REVIEW_CONTRACT_MARKER = "Review Contract JSON:"
_REVIEW_CONTRACT_LENSES = ("Spec Compliance", "Edge Case", "Verification Gap")
_REVIEW_COMPLETION = {"completed", "incomplete", "failed"}
_LENS_STATUS = {"completed", "incomplete", "not-applicable"}
_UNCERTAINTY_KINDS = {"Question", "Limitation", "Declined to Judge"}
_FINDING_SEVERITIES = {"P0", "P1", "P2", "P3", "P4"}
_DISPOSITION_ACTIONS = {"retain", "fix", "reject", "defer"}


def parse_review_contract(
    text: str,
    *,
    fix_through: str = "P1",
) -> tuple[dict[str, Any] | None, list[str]]:
    raw = str(text or "")
    marker_index = raw.find(_REVIEW_CONTRACT_MARKER)
    if marker_index < 0:
        return None, ["review_contract_missing"]
    tail = raw[marker_index + len(_REVIEW_CONTRACT_MARKER):]
    json_start = tail.find("{")
    if json_start < 0:
        return None, ["review_contract_json_missing"]
    try:
        payload, _ = json.JSONDecoder().raw_decode(tail[json_start:])
    except json.JSONDecodeError as exc:
        return None, [f"review_contract_json_invalid:{exc.msg}"]
    if not isinstance(payload, dict):
        return None, ["review_contract_must_be_object"]

    errors: list[str] = []
    threshold = str(fix_through or "P1").strip().upper()
    threshold_rank = {"P1": 1, "P2": 2, "P3": 3}.get(threshold, 1)
    completion = str(payload.get("completion_status") or "").strip()
    if completion not in _REVIEW_COMPLETION:
        errors.append("completion_status_invalid")

    lenses = payload.get("lenses")
    seen_lenses: set[str] = set()
    if not isinstance(lenses, list):
        errors.append("lenses_must_be_array")
        lenses = []
    for index, lens in enumerate(lenses):
        if not isinstance(lens, dict):
            errors.append(f"lenses[{index}]_must_be_object")
            continue
        name = str(lens.get("name") or "").strip()
        status = str(lens.get("status") or "").strip()
        notes = str(lens.get("notes") or "").strip()
        if name not in _REVIEW_CONTRACT_LENSES:
            errors.append(f"lenses[{index}]_name_invalid")
        elif name in seen_lenses:
            errors.append(f"lenses[{index}]_duplicate")
        else:
            seen_lenses.add(name)
        if status not in _LENS_STATUS:
            errors.append(f"lenses[{index}]_status_invalid")
        if not notes:
            errors.append(f"lenses[{index}]_notes_missing")
    for required in _REVIEW_CONTRACT_LENSES:
        if required not in seen_lenses:
            errors.append(f"required_lens_missing:{required}")
    if completion == "completed":
        for lens in lenses:
            if isinstance(lens, dict) and str(lens.get("status") or "").strip() == "incomplete":
                errors.append("completed_review_has_incomplete_lens")

    findings = payload.get("findings")
    if not isinstance(findings, list):
        errors.append("findings_must_be_array")
        findings = []
    required_finding_fields = (
        "finding_id",
        "claim",
        "severity",
        "authority_refs",
        "evidence",
        "failure_scenario",
        "expected_protection",
        "observed_protection",
        "required_action",
        "verification",
        "disposition",
    )
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            errors.append(f"findings[{index}]_must_be_object")
            continue
        for field in required_finding_fields:
            if field not in finding:
                errors.append(f"findings[{index}]_{field}_missing")
        if not str(finding.get("finding_id") or "").strip():
            errors.append(f"findings[{index}]_finding_id_empty")
        if not str(finding.get("claim") or "").strip():
            errors.append(f"findings[{index}]_claim_empty")
        severity = str(finding.get("severity") or "").strip().upper()
        if severity not in _FINDING_SEVERITIES:
            errors.append(f"findings[{index}]_severity_invalid")
        for field in ("authority_refs", "evidence"):
            value = finding.get(field)
            if not isinstance(value, list) or any(not str(item or "").strip() for item in value):
                errors.append(f"findings[{index}]_{field}_invalid")
        for field in ("failure_scenario", "expected_protection", "observed_protection", "required_action", "verification"):
            if not str(finding.get(field) or "").strip():
                errors.append(f"findings[{index}]_{field}_empty")
        disposition = finding.get("disposition")
        if not isinstance(disposition, dict):
            errors.append(f"findings[{index}]_disposition_invalid")
        else:
            action = str(disposition.get("action") or "").strip()
            rationale = str(disposition.get("rationale") or "").strip()
            if action not in _DISPOSITION_ACTIONS:
                errors.append(f"findings[{index}]_disposition_action_invalid")
            if not rationale:
                errors.append(f"findings[{index}]_disposition_rationale_missing")
            if (
                severity in _FINDING_SEVERITIES
                and int(severity[1]) <= threshold_rank
                and action == "defer"
            ):
                errors.append(f"findings[{index}]_must_fix_cannot_defer")

    uncertainty = payload.get("uncertainty")
    if not isinstance(uncertainty, list):
        errors.append("uncertainty_must_be_array")
        uncertainty = []
    for index, item in enumerate(uncertainty):
        if not isinstance(item, dict):
            errors.append(f"uncertainty[{index}]_must_be_object")
            continue
        if str(item.get("kind") or "").strip() not in _UNCERTAINTY_KINDS:
            errors.append(f"uncertainty[{index}]_kind_invalid")
        if not str(item.get("statement") or "").strip():
            errors.append(f"uncertainty[{index}]_statement_missing")

    return payload, sorted(set(errors))


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(t in text for t in terms)


def _task_explicitly_requires_anti_tamper(task_blob: str) -> bool:
    lower = str(task_blob or "").lower()
    return _contains_any(lower, _HOST_SAFE_STRICT_INTENT_TERMS)


def _override_verdict(text: str, verdict: str) -> str:
    replaced, count = _VERDICT_RE.subn(f"Verdict: {verdict}", str(text or ""))
    if count > 0:
        return replaced
    base = str(text or "").rstrip()
    return f"{base}\nVerdict: {verdict}\n" if base else f"Verdict: {verdict}\n"


def normalize_host_safe_needs_fix(
    *,
    agent: str,
    text: str,
    security_profile: str,
    task_requirements_blob: str,
) -> tuple[str, str | None, dict[str, Any] | None]:
    verdict = parse_verdict(text)
    if security_profile != "host-safe" or verdict != "Needs Fix":
        return text, verdict, None

    lower = str(text or "").lower()
    if _task_explicitly_requires_anti_tamper(task_requirements_blob):
        return text, verdict, {"demoted": False, "reason": "task_requires_anti_tamper"}
    if _contains_any(lower, _HOST_SAFETY_BASELINE_TERMS):
        return text, verdict, {"demoted": False, "reason": "host_safety_boundary_issue_present"}
    if not _contains_any(lower, _ANTI_TAMPER_TERMS):
        return text, verdict, {"demoted": False, "reason": "not_anti_tamper_only"}

    normalized = str(text or "")
    if "Host-safe normalization:" not in normalized:
        normalized = (
            normalized.rstrip()
            + "\n\nHost-safe normalization:\n"
            + "- SECURITY_PROFILE=host-safe: anti-tamper-only findings are advisory unless task/acceptance explicitly requires strict anti-tamper.\n"
        )
    normalized = _override_verdict(normalized, "OK")
    return normalized, parse_verdict(normalized), {"demoted": True, "reason": "anti_tamper_only_under_host_safe", "agent": agent}


def resolve_claude_agents_root(value: str | None) -> Path:
    if value and str(value).strip():
        return Path(str(value).strip())
    env = os.environ.get("CLAUDE_AGENTS_ROOT")
    if env and env.strip():
        return Path(env.strip())
    return Path.home() / ".claude" / "agents"


def load_agent_prompt_blob(agent: str, *, claude_agents_root: Path) -> tuple[str | None, Path | None]:
    root = repo_root()
    project_specific = {
        "adr-compliance-checker": root / ".claude" / "agents" / "adr-compliance-checker.md",
        "performance-slo-validator": root / ".claude" / "agents" / "performance-slo-validator.md",
    }
    lst97_agents = {"architect-reviewer", "code-reviewer", "security-auditor", "test-automator"}

    candidates: list[Path] = []
    if agent in project_specific:
        candidates.append(project_specific[agent])
        candidates.append(claude_agents_root / f"{agent}.md")
    elif agent in lst97_agents:
        candidates.append(root / ".claude" / "agents" / "lst97" / f"{agent}.md")
        candidates.append(claude_agents_root / "lst97" / f"{agent}.md")
    else:
        candidates.append(root / ".claude" / "agents" / f"{agent}.md")
        candidates.append(claude_agents_root / f"{agent}.md")

    for p in candidates:
        if p.is_file():
            return read_text(p), p
    return None, None


def agent_prompt(agent: str, *, claude_agents_root: Path, skip_agent_files: bool) -> tuple[str, dict[str, Any]]:
    project_specific = {
        "adr-compliance-checker": ".claude/agents/adr-compliance-checker.md",
        "performance-slo-validator": ".claude/agents/performance-slo-validator.md",
    }
    base = default_agent_prompt(agent)
    if skip_agent_files:
        return base, {"agent_prompt_source": None}
    extra, source = load_agent_prompt_blob(agent, claude_agents_root=claude_agents_root)
    if not extra or not source:
        extra = load_optional_agent_prompt(project_specific.get(agent, ""))
        if not extra:
            return base, {"agent_prompt_source": None}
        extra_trim = truncate(extra, max_chars=6_000)
        return "\n\n".join([base, "Project agent prompt (truncated):", extra_trim]), {"agent_prompt_source": project_specific.get(agent)}

    try:
        rel = str(source.relative_to(repo_root())).replace("\\", "/")
    except Exception:
        rel = str(source)

    extra_trim = truncate(extra, max_chars=6_000)
    header = f"Agent prompt source: {rel}"
    return "\n\n".join([base, header, extra_trim]), {"agent_prompt_source": rel}
