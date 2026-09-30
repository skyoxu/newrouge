#!/usr/bin/env python3
"""Post-Chapter-5 Capability planning with three isolated candidates and independent review."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import random
import re
import shutil
import subprocess
import time
from copy import deepcopy
from pathlib import Path
from typing import Any

from _planning_skill_common import (
    atomic_json,
    build_blinded_analysis_bundle,
    canonical_sha,
    file_sha,
    inspect_isolated_runner,
    load_json,
    parse_model_json,
    relative,
    repo_path,
    run_isolated_model,
    text_sha,
)

RUN_SCHEMA = "newrouge.capability-planning-run.v1"
CANDIDATE_SCHEMA = "newrouge.capability-candidate.v1"
REVIEW_SCHEMA = "newrouge.capability-review.v2"
DEFAULT_RUN_ROOT = Path("logs/ci/capability-planning")
FORMAL_CAPABILITIES = Path("docs/planning/semantic-topology/capabilities.v1.json")
FORMAL_SELECTION = Path("docs/planning/semantic-topology/capability-selection.v1.json")
FORMAL_EDGES = Path("docs/planning/semantic-topology/topology-edges.v1.json")
FORMAL_MANIFEST = Path("docs/planning/semantic-topology/topology-manifest.v1.json")
TASK_VIEWS = (
    Path(".taskmaster/tasks/tasks_back.json"),
    Path(".taskmaster/tasks/tasks_gameplay.json"),
)


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def slug(value: str) -> str:
    parts = re.findall(r"[A-Za-z0-9]+", value.upper())
    return "-".join(parts)[:72] or "UNNAMED"


def _run_dir(root: Path, run_id: str) -> Path:
    return root / DEFAULT_RUN_ROOT / run_id


def _load_run(root: Path, run_id: str) -> tuple[Path, dict[str, Any]]:
    path = _run_dir(root, run_id) / "run.json"
    payload = load_json(path, {})
    if payload.get("schema_version") != RUN_SCHEMA:
        raise ValueError(f"missing or invalid Capability planning run: {run_id}")
    return path, payload


def _repository_identity(root: Path) -> dict[str, Any]:
    try:
        revision = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, timeout=15,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=normal"],
            capture_output=True, text=True, check=True, timeout=15,
        ).stdout
        return {
            "revision": revision,
            "workspace_dirty": bool(status.strip()),
            "workspace_status_sha256": text_sha(status),
        }
    except (OSError, subprocess.SubprocessError):
        return {
            "revision": None,
            "workspace_dirty": None,
            "workspace_status_sha256": None,
        }


def _readiness_summary(root: Path, task_ids: list[str], *, allow_unready: bool) -> dict[str, Any]:
    from chapter5_semantic_reconciliation import load_task_readiness, readiness_path_for_task

    rows = []
    all_ready = True
    for task_id in task_ids:
        ok, payload, reason = load_task_readiness(root, task_id)
        readiness_path = readiness_path_for_task(root, task_id)
        rows.append({
            "task_id": str(task_id),
            "ready": bool(ok),
            "reason": reason,
            "readiness": payload.get("readiness") if isinstance(payload, dict) else None,
            "readiness_path": relative(root, readiness_path) if readiness_path.is_file() else None,
            "readiness_sha256": file_sha(readiness_path) if readiness_path.is_file() else None,
            "input_fingerprint_sha256": (
                (payload.get("input_fingerprint") or {}).get("sha256")
                if isinstance(payload, dict) else None
            ),
        })
        all_ready = all_ready and ok
    if not task_ids:
        all_ready = False
        rows.append({"task_id": None, "ready": False, "reason": "explicit_task_scope_required"})
    if not all_ready and not allow_unready:
        reasons = ", ".join(str(row["reason"]) for row in rows if not row["ready"])
        raise ValueError(f"Chapter 5 scope is not ready: {reasons}")
    return {
        "schema_version": "newrouge.capability-planning-readiness-summary.v1",
        "formal_ready": all_ready,
        "allow_unready_draft": bool(allow_unready),
        "tasks": rows,
    }


def prepare(
    root: Path,
    *,
    run_id: str,
    task_ids: list[str],
    allow_unready: bool,
    source_manifest: Path,
    ledger: Path,
    semantics: Path,
    model_batch_char_budget: int,
    candidate_retry_limit: int,
    review_retry_limit: int,
    candidate_budget_sec: int,
    total_budget_sec: int,
    request_limit: int,
) -> dict[str, Any]:
    run_dir = _run_dir(root, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    readiness = _readiness_summary(root, task_ids, allow_unready=allow_unready)
    analysis_dir = run_dir / "analysis-input"
    index = build_blinded_analysis_bundle(
        root,
        analysis_dir,
        source_manifest_path=source_manifest,
        ledger_path=ledger,
        semantics_path=semantics,
        task_view_paths=[root / value for value in TASK_VIEWS],
        readiness_summary=readiness,
        model_batch_char_budget=model_batch_char_budget,
        repository_identity=_repository_identity(root),
    )
    state = {
        "schema_version": RUN_SCHEMA,
        "run_id": run_id,
        "phase": "prepared",
        "created_at_utc": now(),
        "formal_ready": readiness["formal_ready"],
        "analysis_identity_sha256": index["analysis_identity_sha256"],
        "analysis_index_path": relative(root, analysis_dir / "analysis-index.json"),
        "task_scope": [str(value) for value in task_ids],
        "candidate_attempts": {},
        "review_attempts": [],
        "selected_candidate": None,
        "final_candidate_path": None,
        "budget": {
            "candidate_retry_limit": int(candidate_retry_limit),
            "review_retry_limit": int(review_retry_limit),
            "candidate_budget_sec": int(candidate_budget_sec),
            "total_budget_sec": int(total_budget_sec),
            "request_limit": int(request_limit),
            "activity_sec": 0.0,
            "runner_invocations": 0,
            "model_requests_observed": 0,
            "request_count_complete": True,
            "candidate_activity_sec": {},
            "review_activity_sec": 0.0,
        },
        "model_batch_count": int((index.get("model_batch_index") or {}).get("batch_count") or 0),
        "applied": False,
    }
    atomic_json(run_dir / "run.json", state)
    return state


CANDIDATE_PROMPT = """You are producing one independent cumulative Capability proposal for a game repository.

Use the complete prepared analysis-input. The runner may stream authoritative Source Block raw text and reviewed Requirements in ordered batches from analysis-input/model-batches; every batch belongs to this same fresh candidate session and no block may be truncated. Sanitized task views and readiness context are also part of the allowed input. Do not infer or search for any prior Capability answer. Preserve any capability/module organization written in the authoritative GDD itself; that source organization is evidence, not a derived answer to hide.

Return JSON only with schema_version = "newrouge.capability-candidate.v1".
Required top-level fields:
- schema_version
- analysis_identity_sha256 (copy from analysis-input/analysis-index.json)
- capabilities
- ungrouped_requirements
- source_accounting
- questions
- generation_notes

Each capability needs temporary capability_id beginning TMP-CAP-, title, description, boundary_rationale, requirement_ids, and source_block_ids.
Every source block in source-blocks.v1.json must appear exactly once in source_accounting, with block_id, disposition, capability_ids, and rationale.
Every active delivery-relevant Requirement must either belong to one or more capabilities or appear in ungrouped_requirements with a reason.
If a Requirement belongs to multiple capabilities, add multi_membership_rationales at top level mapping that Requirement ID to a non-empty rationale.
Do not modify or invent Requirements, Tasks, Acceptance, contracts, or source text. Report upstream gaps in questions instead.
"""


REVIEW_PROMPT = """You are the independent Capability proposal reviewer.

Read the complete analysis-input/ and all candidate files under candidates/. Candidate names are anonymous A/B/C and reveal no generation order. Reject structurally invalid or source-unfaithful options rather than averaging them. Select one complete candidate; do not merge the three by default.

Return JSON only with schema_version = "newrouge.capability-review.v2" and:
- selected: "A" | "B" | "C" | null
- status: "selected" | "no_valid_winner"
- source_fidelity_findings
- cohesion_findings
- boundary_findings
- multi_membership_findings
- navigation_findings
- tradeoffs
- evidence_refs
- corrections (empty unless a small explicit correction is required)
- rationale

If corrections are needed, use at most 12 JSON-Pointer operations. Each item must contain op (add|replace|remove), path, reason, evidence_refs, and value when required. Corrections apply only to the selected candidate; never change schema_version, analysis_identity_sha256, capability_id, add/remove an entire Capability, or merge candidates into a fourth design.
"""


def validate_candidate(candidate: dict[str, Any], ledger: dict[str, Any], semantics: dict[str, Any], analysis_sha: str) -> list[str]:
    errors: list[str] = []
    if candidate.get("schema_version") != CANDIDATE_SCHEMA:
        errors.append("invalid_candidate_schema")
    if candidate.get("analysis_identity_sha256") != analysis_sha:
        errors.append("analysis_identity_mismatch")
    blocks = {
        str(row.get("block_id"))
        for row in ledger.get("blocks", [])
        if isinstance(row, dict) and str(row.get("block_id") or "").strip()
    }
    requirements = {
        str(row.get("requirement_id")): row
        for row in semantics.get("requirements", [])
        if isinstance(row, dict) and str(row.get("requirement_id") or "").strip()
    }
    active_delivery = {
        rid for rid, row in requirements.items()
        if str(row.get("status") or "active").casefold() == "active"
        and row.get("delivery_relevant") is True
    }

    capabilities = candidate.get("capabilities")
    if not isinstance(capabilities, list):
        return errors + ["capabilities_not_array"]
    cap_ids: set[str] = set()
    membership: dict[str, set[str]] = {}
    for cap in capabilities:
        if not isinstance(cap, dict):
            errors.append("invalid_capability_row")
            continue
        cid = str(cap.get("capability_id") or "").strip()
        if not cid.startswith("TMP-CAP-") or cid in cap_ids:
            errors.append(f"invalid_or_duplicate_capability_id:{cid}")
        cap_ids.add(cid)
        if not str(cap.get("title") or "").strip() or not str(cap.get("boundary_rationale") or "").strip():
            errors.append(f"capability_missing_text:{cid}")
        reqs = [str(value) for value in cap.get("requirement_ids", [])]
        if not reqs:
            errors.append(f"capability_missing_requirements:{cid}")
        for rid in reqs:
            if rid not in requirements:
                errors.append(f"unknown_requirement:{rid}")
            membership.setdefault(rid, set()).add(cid)
        for block_id in cap.get("source_block_ids", []):
            if str(block_id) not in blocks:
                errors.append(f"unknown_source_block:{block_id}")

    accounting = candidate.get("source_accounting")
    if not isinstance(accounting, list):
        errors.append("source_accounting_not_array")
        accounting = []
    accounted = [str(row.get("block_id")) for row in accounting if isinstance(row, dict)]
    if set(accounted) != blocks or len(accounted) != len(blocks):
        errors.append("source_accounting_incomplete_or_duplicate")

    ungrouped_rows = candidate.get("ungrouped_requirements")
    if not isinstance(ungrouped_rows, list):
        errors.append("ungrouped_requirements_not_array")
        ungrouped_rows = []
    ungrouped = set()
    for row in ungrouped_rows:
        if not isinstance(row, dict):
            errors.append("invalid_ungrouped_requirement")
            continue
        rid = str(row.get("requirement_id") or "")
        if rid not in requirements:
            errors.append(f"unknown_ungrouped_requirement:{rid}")
        if not str(row.get("reason") or "").strip():
            errors.append(f"ungrouped_reason_missing:{rid}")
        ungrouped.add(rid)
    missing = sorted(active_delivery - set(membership) - ungrouped)
    if missing:
        errors.append("delivery_requirements_unaccounted:" + ",".join(missing))
    overlap = sorted(set(membership) & ungrouped)
    if overlap:
        errors.append("requirement_both_grouped_and_ungrouped:" + ",".join(overlap))
    rationales = candidate.get("multi_membership_rationales")
    if not isinstance(rationales, dict):
        rationales = {}
    for rid, values in membership.items():
        if len(values) > 1 and not str(rationales.get(rid) or "").strip():
            errors.append(f"multi_membership_rationale_missing:{rid}")
    return sorted(set(errors))


def _copy_analysis(run_dir: Path, workspace: Path) -> None:
    target = workspace / "analysis-input"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(run_dir / "analysis-input", target)


def _budget(state: dict[str, Any]) -> dict[str, Any]:
    value = state.get("budget")
    if not isinstance(value, dict):
        raise ValueError("Capability planning budget state is missing")
    return value


def _candidate_record(state: dict[str, Any], label: str) -> dict[str, Any]:
    records = state.setdefault("candidate_attempts", {})
    row = records.get(label)
    if not isinstance(row, dict) or "attempts" not in row:
        row = {"attempts": [], "valid_attempt": None, "final_meta": None}
        records[label] = row
    return row


def _estimated_requests(state: dict[str, Any], runner_info: dict[str, Any]) -> int | None:
    if runner_info.get("request_accounting") != "exact_per_runner_invocation":
        return None
    if runner_info.get("supports_batched_session") is True:
        return int(state.get("model_batch_count") or 0) + 2
    return 1


def _remaining_attempt_budget(
    state: dict[str, Any],
    *,
    label: str | None,
    timeout_sec: int,
    runner_info: dict[str, Any],
) -> int:
    budget = _budget(state)
    total_remaining = float(budget["total_budget_sec"]) - float(budget.get("activity_sec") or 0.0)
    if total_remaining <= 0:
        raise ValueError("Capability planning total active-time budget exhausted")
    remaining = total_remaining
    if label is not None:
        by_candidate = budget.setdefault("candidate_activity_sec", {})
        candidate_remaining = float(budget["candidate_budget_sec"]) - float(by_candidate.get(label) or 0.0)
        if candidate_remaining <= 0:
            raise ValueError(f"{label} active-time budget exhausted")
        remaining = min(remaining, candidate_remaining)
    estimated = _estimated_requests(state, runner_info)
    if estimated is not None and budget.get("request_count_complete") is True:
        observed = int(budget.get("model_requests_observed") or 0)
        if observed + estimated > int(budget["request_limit"]):
            raise ValueError(
                f"Capability planning model request budget exhausted: "
                f"{observed}+{estimated}>{budget['request_limit']}"
            )
    return max(1, min(int(timeout_sec), int(remaining)))


def _record_runner_activity(
    state: dict[str, Any],
    *,
    label: str | None,
    elapsed_sec: float,
    receipt: dict[str, Any] | None,
) -> None:
    budget = _budget(state)
    budget["activity_sec"] = float(budget.get("activity_sec") or 0.0) + float(elapsed_sec)
    budget["runner_invocations"] = int(budget.get("runner_invocations") or 0) + 1
    if label is not None:
        by_candidate = budget.setdefault("candidate_activity_sec", {})
        by_candidate[label] = float(by_candidate.get(label) or 0.0) + float(elapsed_sec)
    else:
        budget["review_activity_sec"] = float(budget.get("review_activity_sec") or 0.0) + float(elapsed_sec)
    if isinstance(receipt, dict) and receipt.get("request_count_observable") is True:
        budget["model_requests_observed"] = (
            int(budget.get("model_requests_observed") or 0)
            + int(receipt.get("model_request_count") or 0)
        )
    else:
        budget["request_count_complete"] = False


def _valid_candidate_reusable(
    run_dir: Path,
    state: dict[str, Any],
    label: str,
    *,
    prompt_sha: str,
    runner_info: dict[str, Any],
) -> bool:
    record = _candidate_record(state, label)
    meta = record.get("final_meta")
    path = run_dir / "candidates" / f"{label}.json"
    return (
        isinstance(meta, dict)
        and not meta.get("validation_errors")
        and meta.get("analysis_identity_sha256") == state.get("analysis_identity_sha256")
        and meta.get("prompt_sha256") == prompt_sha
        and meta.get("runner_contract_model") == runner_info.get("model")
        and path.is_file()
        and meta.get("output_sha256") == file_sha(path)
    )


def generate(root: Path, *, run_id: str, runner: Path, timeout_sec: int) -> dict[str, Any]:
    run_path, state = _load_run(root, run_id)
    if state.get("formal_ready") is not True:
        raise ValueError("formal generation is blocked until the explicit Chapter 5 scope is ready")
    runner_info = inspect_isolated_runner(runner)
    if int(state.get("model_batch_count") or 0) > 1 and runner_info.get("supports_batched_session") is not True:
        raise ValueError(
            "formal Capability generation with multiple model batches requires "
            "supports_batched_session=true"
        )
    run_dir = run_path.parent
    prompt_sha = text_sha(CANDIDATE_PROMPT)
    state["runner"] = runner_info
    outputs = []
    blocked: list[str] = []
    max_attempts = 1 + int(_budget(state).get("candidate_retry_limit") or 0)
    estimated = _estimated_requests(state, runner_info)
    budget = _budget(state)
    if estimated is not None and budget.get("request_count_complete") is True:
        remaining_initial = sum(
            1
            for index in range(1, 4)
            if not _valid_candidate_reusable(
                run_dir,
                state,
                f"candidate-{index}",
                prompt_sha=prompt_sha,
                runner_info=runner_info,
            )
        )
        observed = int(budget.get("model_requests_observed") or 0)
        required = remaining_initial * estimated
        if observed + required > int(budget["request_limit"]):
            state["phase"] = "generation-blocked"
            state["stop_reason"] = (
                f"initial candidate request estimate exceeds budget: "
                f"{observed}+{required}>{budget['request_limit']}"
            )
            atomic_json(run_path, state)
            raise ValueError(state["stop_reason"])
    for index in range(1, 4):
        label = f"candidate-{index}"
        if _valid_candidate_reusable(
            run_dir, state, label, prompt_sha=prompt_sha, runner_info=runner_info
        ):
            outputs.append({"candidate": label, "valid": True, "reused": True, "errors": []})
            continue
        record = _candidate_record(state, label)
        attempts = record.setdefault("attempts", [])
        valid = False
        last_errors: list[str] = []
        while len(attempts) < max_attempts and not valid:
            attempt_no = len(attempts) + 1
            try:
                attempt_timeout = _remaining_attempt_budget(
                    state,
                    label=label,
                    timeout_sec=timeout_sec,
                    runner_info=runner_info,
                )
            except ValueError as exc:
                last_errors = [str(exc)]
                break
            workspace = run_dir / "isolated-workspaces" / label / f"attempt-{attempt_no}"
            if workspace.exists():
                shutil.rmtree(workspace)
            workspace.mkdir(parents=True)
            _copy_analysis(run_dir, workspace)
            prompt_path = workspace / "prompt.txt"
            prompt_path.write_text(CANDIDATE_PROMPT, encoding="utf-8", newline="\n")
            output = workspace / "candidate.json"
            receipt: dict[str, Any] | None = None
            candidate: dict[str, Any] | None = None
            errors: list[str] = []
            started = time.monotonic()
            try:
                receipt = run_isolated_model(
                    runner,
                    workspace=workspace,
                    prompt_path=prompt_path,
                    output_path=output,
                    timeout_sec=attempt_timeout,
                )
                candidate = parse_model_json(output)
                ledger = load_json(workspace / "analysis-input/source-blocks.v1.json", {})
                semantics = load_json(workspace / "analysis-input/semantic-requirements.v1.json", {})
                errors = validate_candidate(
                    candidate, ledger, semantics, str(state["analysis_identity_sha256"])
                )
            except (OSError, RuntimeError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
                errors = [f"runner_or_output_failure:{exc}"]
            elapsed = time.monotonic() - started
            _record_runner_activity(
                state, label=label, elapsed_sec=elapsed, receipt=receipt
            )
            actual_model = str((receipt or {}).get("model") or runner_info.get("model") or "").strip()
            expected_actual_model = str(state.get("actual_model") or "").strip()
            if expected_actual_model and actual_model != expected_actual_model:
                errors.append(
                    f"actual_model_mismatch:{actual_model}!={expected_actual_model}"
                )
            elif actual_model:
                state["actual_model"] = actual_model
            meta = {
                "candidate": label,
                "attempt": attempt_no,
                "model": actual_model,
                "runner_contract_model": runner_info.get("model"),
                "runner": runner_info,
                "prompt_sha256": prompt_sha,
                "analysis_identity_sha256": state["analysis_identity_sha256"],
                "elapsed_active_sec": elapsed,
                "validation_errors": errors,
                "receipt": receipt or {},
                "output_sha256": file_sha(output) if output.is_file() else None,
            }
            attempts.append(meta)
            atomic_json(
                run_dir / "candidates" / "attempts" / f"{label}-attempt-{attempt_no}.meta.json",
                meta,
            )
            if candidate is not None:
                atomic_json(
                    run_dir / "candidates" / "attempts" / f"{label}-attempt-{attempt_no}.json",
                    candidate,
                )
            elif output.is_file():
                raw_target = run_dir / "candidates" / "attempts" / f"{label}-attempt-{attempt_no}.raw.txt"
                raw_target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(output, raw_target)
            if not errors and candidate is not None:
                persisted = run_dir / "candidates" / f"{label}.json"
                atomic_json(persisted, candidate)
                final_meta = dict(meta)
                final_meta["output_sha256"] = file_sha(persisted)
                record["valid_attempt"] = attempt_no
                record["final_meta"] = final_meta
                atomic_json(run_dir / "candidates" / f"{label}.meta.json", final_meta)
                valid = True
                last_errors = []
            else:
                last_errors = errors
            atomic_json(run_path, state)
        outputs.append({
            "candidate": label,
            "valid": valid,
            "reused": False,
            "attempt_count": len(record.get("attempts", [])),
            "errors": last_errors,
        })
        if not valid:
            blocked.append(label)
    if blocked:
        state["phase"] = "generation-blocked"
        details = []
        by_label = {str(row.get("candidate")): row for row in outputs if isinstance(row, dict)}
        for label in blocked:
            errors = by_label.get(label, {}).get("errors", [])
            first = str(errors[0])[:1200] if isinstance(errors, list) and errors else "no_error_detail"
            details.append(f"{label}={first}")
        state["stop_reason"] = (
            "invalid_or_budget_exhausted_candidates:"
            + ",".join(blocked)
            + "; "
            + " | ".join(details)
        )
        atomic_json(run_path, state)
        raise ValueError(state["stop_reason"])
    state["phase"] = "candidates-generated"
    state["stop_reason"] = None
    atomic_json(run_path, state)
    return {"run_id": run_id, "status": "complete", "candidates": outputs, "budget": state["budget"]}


def _decode_json_pointer(path: str) -> list[str]:
    if not path.startswith("/") or path == "/":
        raise ValueError(f"invalid correction JSON pointer: {path}")
    return [
        token.replace("~1", "/").replace("~0", "~")
        for token in path[1:].split("/")
    ]


def _validate_correction_path(tokens: list[str]) -> None:
    if not tokens:
        raise ValueError("empty correction path")
    if tokens[0] in {"schema_version", "analysis_identity_sha256"}:
        raise ValueError("correction cannot change candidate identity")
    if tokens[0] == "capabilities":
        if len(tokens) < 3 or not tokens[1].isdigit():
            raise ValueError("correction cannot add/remove an entire Capability")
        if tokens[2] == "capability_id":
            raise ValueError("correction cannot change capability_id")
        if tokens[2] not in {
            "title", "description", "boundary_rationale",
            "requirement_ids", "source_block_ids",
        }:
            raise ValueError(f"unsupported Capability correction field: {tokens[2]}")
        return
    if tokens[0] not in {
        "ungrouped_requirements",
        "multi_membership_rationales",
        "source_accounting",
        "questions",
        "generation_notes",
    }:
        raise ValueError(f"unsupported correction root: {tokens[0]}")


def apply_review_corrections(
    candidate: dict[str, Any],
    corrections: Any,
) -> dict[str, Any]:
    if corrections in (None, []):
        return deepcopy(candidate)
    if not isinstance(corrections, list) or len(corrections) > 12:
        raise ValueError("review corrections must be an array of at most 12 operations")
    result: Any = deepcopy(candidate)
    for index, row in enumerate(corrections, 1):
        if not isinstance(row, dict):
            raise ValueError(f"correction {index} must be an object")
        op = str(row.get("op") or "").strip().lower()
        path = str(row.get("path") or "").strip()
        reason = str(row.get("reason") or "").strip()
        refs = row.get("evidence_refs")
        if op not in {"add", "replace", "remove"} or not reason:
            raise ValueError(f"invalid correction operation {index}")
        if not isinstance(refs, list) or not refs:
            raise ValueError(f"correction {index} requires evidence_refs")
        tokens = _decode_json_pointer(path)
        _validate_correction_path(tokens)
        parent = result
        for token in tokens[:-1]:
            if isinstance(parent, list):
                if not token.isdigit() or int(token) >= len(parent):
                    raise ValueError(f"correction path not found: {path}")
                parent = parent[int(token)]
            elif isinstance(parent, dict):
                if token not in parent:
                    if op == "add":
                        parent[token] = {}
                    else:
                        raise ValueError(f"correction path not found: {path}")
                parent = parent[token]
            else:
                raise ValueError(f"correction path is not traversable: {path}")
        leaf = tokens[-1]
        if isinstance(parent, list):
            if op == "add" and leaf == "-":
                parent.append(deepcopy(row.get("value")))
            elif leaf.isdigit() and int(leaf) < len(parent):
                pos = int(leaf)
                if op == "remove":
                    parent.pop(pos)
                else:
                    parent[pos] = deepcopy(row.get("value"))
            else:
                raise ValueError(f"correction list path invalid: {path}")
        elif isinstance(parent, dict):
            if op == "remove":
                if leaf not in parent:
                    raise ValueError(f"correction remove path not found: {path}")
                del parent[leaf]
            elif op == "replace":
                if leaf not in parent:
                    raise ValueError(f"correction replace path not found: {path}")
                parent[leaf] = deepcopy(row.get("value"))
            else:
                parent[leaf] = deepcopy(row.get("value"))
        else:
            raise ValueError(f"correction parent is not editable: {path}")
    if not isinstance(result, dict):
        raise ValueError("corrected candidate must remain an object")
    return result


def review(root: Path, *, run_id: str, runner: Path, timeout_sec: int) -> dict[str, Any]:
    run_path, state = _load_run(root, run_id)
    run_dir = run_path.parent
    labels = [f"candidate-{index}" for index in range(1, 4)]
    for label in labels:
        record = _candidate_record(state, label)
        meta = record.get("final_meta")
        if not isinstance(meta, dict) or meta.get("validation_errors"):
            raise ValueError("all three candidates must be structurally valid before review")
        if not (run_dir / "candidates" / f"{label}.json").is_file():
            raise ValueError(f"missing candidate: {label}")
    runner_info = inspect_isolated_runner(runner)
    if state.get("runner", {}).get("model") != runner_info.get("model"):
        raise ValueError("review must use the same model identity as candidate generation")
    seed_hex = hashlib.sha256(
        (str(state["analysis_identity_sha256"]) + ":" + run_id).encode("utf-8")
    ).hexdigest()
    shuffled = labels[:]
    random.Random(int(seed_hex[:16], 16)).shuffle(shuffled)
    anonymous = dict(zip(["A", "B", "C"], shuffled))

    max_attempts = 1 + int(_budget(state).get("review_retry_limit") or 0)
    attempts = state.setdefault("review_attempts", [])
    final_result: dict[str, Any] | None = None
    final_meta: dict[str, Any] | None = None
    corrected_candidate: dict[str, Any] | None = None
    last_error = ""
    while len(attempts) < max_attempts and final_result is None:
        attempt_no = len(attempts) + 1
        attempt_timeout = _remaining_attempt_budget(
            state, label=None, timeout_sec=timeout_sec, runner_info=runner_info
        )
        workspace = run_dir / "isolated-workspaces" / "review" / f"attempt-{attempt_no}"
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True)
        _copy_analysis(run_dir, workspace)
        (workspace / "candidates").mkdir()
        for alias, label in anonymous.items():
            shutil.copyfile(
                run_dir / "candidates" / f"{label}.json",
                workspace / "candidates" / f"{alias}.json",
            )
        prompt_path = workspace / "prompt.txt"
        prompt_path.write_text(REVIEW_PROMPT, encoding="utf-8", newline="\n")
        output = workspace / "review.json"
        receipt: dict[str, Any] | None = None
        result: dict[str, Any] | None = None
        errors: list[str] = []
        started = time.monotonic()
        try:
            receipt = run_isolated_model(
                runner, workspace=workspace, prompt_path=prompt_path,
                output_path=output, timeout_sec=attempt_timeout,
            )
            result = parse_model_json(output)
            if result.get("schema_version") != REVIEW_SCHEMA:
                errors.append("invalid_review_schema")
            selected = result.get("selected")
            if selected is not None and selected not in anonymous:
                errors.append("unknown_selected_candidate")
            if result.get("status") == "selected" and selected is None:
                errors.append("selected_review_missing_candidate")
            if result.get("status") == "no_valid_winner" and selected is not None:
                errors.append("no_valid_winner_cannot_select_candidate")
            if result.get("status") not in {"selected", "no_valid_winner"}:
                errors.append("invalid_review_status")
            if not errors and result.get("status") == "selected":
                source_label = anonymous[str(selected)]
                source_candidate = load_json(
                    run_dir / "candidates" / f"{source_label}.json", {}
                )
                corrected_candidate = apply_review_corrections(
                    source_candidate, result.get("corrections", [])
                )
                ledger = load_json(run_dir / "analysis-input/source-blocks.v1.json", {})
                semantics = load_json(run_dir / "analysis-input/semantic-requirements.v1.json", {})
                correction_errors = validate_candidate(
                    corrected_candidate,
                    ledger,
                    semantics,
                    str(state["analysis_identity_sha256"]),
                )
                if correction_errors:
                    errors.extend(
                        f"corrected_candidate:{value}" for value in correction_errors
                    )
        except (OSError, RuntimeError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            errors = [f"review_runner_or_output_failure:{exc}"]
        elapsed = time.monotonic() - started
        _record_runner_activity(
            state, label=None, elapsed_sec=elapsed, receipt=receipt
        )
        actual_model = str((receipt or {}).get("model") or runner_info.get("model") or "").strip()
        meta = {
            "attempt": attempt_no,
            "model": actual_model,
            "runner_contract_model": runner_info.get("model"),
            "prompt_sha256": text_sha(REVIEW_PROMPT),
            "analysis_identity_sha256": state["analysis_identity_sha256"],
            "elapsed_active_sec": elapsed,
            "validation_errors": errors,
            "receipt": receipt or {},
            "output_sha256": file_sha(output) if output.is_file() else None,
        }
        attempts.append(meta)
        atomic_json(
            run_dir / "review" / "attempts" / f"review-attempt-{attempt_no}.meta.json",
            meta,
        )
        if result is not None:
            atomic_json(
                run_dir / "review" / "attempts" / f"review-attempt-{attempt_no}.json",
                result,
            )
        if not errors and result is not None:
            final_result = result
            final_meta = meta
        else:
            last_error = ";".join(errors)
        atomic_json(run_path, state)

    if final_result is None or final_meta is None:
        state["phase"] = "review-blocked"
        state["stop_reason"] = last_error or "review_attempt_budget_exhausted"
        atomic_json(run_path, state)
        raise ValueError(state["stop_reason"])

    review_dir = run_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(review_dir / "anonymous-map.json", {
        "seed_sha256": "sha256:" + seed_hex,
        "mapping": anonymous,
    })
    atomic_json(review_dir / "review.json", final_result)
    atomic_json(review_dir / "review.meta.json", final_meta)
    selected = final_result.get("selected")
    selected_label = anonymous.get(str(selected)) if selected is not None else None
    final_candidate_path = None
    if final_result.get("status") == "selected":
        if corrected_candidate is None:
            raise ValueError("selected review did not materialize a final candidate")
        if final_result.get("corrections"):
            path = review_dir / "corrected-candidate.json"
            atomic_json(path, corrected_candidate)
            final_candidate_path = "review/corrected-candidate.json"
    state["phase"] = "reviewed"
    state["selected_candidate"] = selected_label
    state["final_candidate_path"] = final_candidate_path
    state["review_status"] = final_result.get("status")
    state["stop_reason"] = (
        "no_valid_winner"
        if final_result.get("status") == "no_valid_winner"
        else None
    )
    atomic_json(run_path, state)
    return {
        "run_id": run_id,
        "status": final_result.get("status"),
        "selected_candidate": selected_label,
        "corrected": bool(final_result.get("corrections")),
        "budget": state["budget"],
    }


def build_alignment(candidate: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    old_rows = [
        row for row in existing.get("capabilities", [])
        if isinstance(row, dict) and str(row.get("capability_id") or "").strip()
    ]
    old_by_members = {
        tuple(sorted(str(value) for value in row.get("requirement_ids", []))): row
        for row in old_rows
    }
    used_old: set[str] = set()
    decisions = []
    first_run = not old_rows
    allocated: set[str] = set()
    for cap in candidate.get("capabilities", []):
        temp_id = str(cap.get("capability_id") or "")
        members = tuple(sorted(str(value) for value in cap.get("requirement_ids", [])))
        old = old_by_members.get(members)
        if old is not None:
            stable_id = str(old["capability_id"])
            used_old.add(stable_id)
            decisions.append({
                "candidate_id": temp_id,
                "action": "reuse",
                "stable_id": stable_id,
                "reason": "exact Requirement membership match",
                "resolved": True,
            })
            allocated.add(stable_id)
            continue
        if first_run:
            base = "CAP-" + slug(str(cap.get("title") or temp_id))
            stable_id = base
            suffix = 2
            while stable_id in allocated:
                stable_id = f"{base}-{suffix}"
                suffix += 1
            allocated.add(stable_id)
            decisions.append({
                "candidate_id": temp_id,
                "action": "add",
                "stable_id": stable_id,
                "reason": "first formal Capability baseline",
                "resolved": True,
            })
        else:
            decisions.append({
                "candidate_id": temp_id,
                "action": "unresolved",
                "stable_id": None,
                "reason": "membership changed; explicit reuse/add/split/merge/rename decision required",
                "resolved": False,
            })
    for old in old_rows:
        cid = str(old["capability_id"])
        if cid not in used_old:
            decisions.append({
                "candidate_id": None,
                "action": "unresolved-retirement",
                "stable_id": cid,
                "reason": "existing Capability has no exact-membership match",
                "resolved": False,
            })
    return {
        "schema_version": "newrouge.capability-alignment.v1",
        "decisions": decisions,
        "resolved": all(bool(row.get("resolved")) for row in decisions),
    }


def _selected_candidate(run_dir: Path, state: dict[str, Any]) -> dict[str, Any]:
    label = str(state.get("selected_candidate") or "")
    if not label:
        raise ValueError("no selected Capability candidate")
    final_path = str(state.get("final_candidate_path") or "").strip()
    if final_path:
        path = (run_dir / final_path).resolve()
        if not path.is_relative_to(run_dir.resolve()) or not path.is_file():
            raise ValueError("corrected final candidate path is invalid")
        return load_json(path, {})
    return load_json(run_dir / "candidates" / f"{label}.json", {})


def _validate_snapshot_freshness(root: Path, run_dir: Path) -> dict[str, Any]:
    index = load_json(run_dir / "analysis-input" / "analysis-index.json", {})
    authority = index.get("authority_inputs")
    if not isinstance(authority, dict) or not authority:
        raise ValueError("Capability analysis input identity is incomplete")
    drift: list[dict[str, Any]] = []
    for rel_path, expected in sorted(authority.items()):
        path = repo_path(root, str(rel_path))
        actual = file_sha(path) if path.is_file() else None
        if actual != expected:
            drift.append({
                "path": str(rel_path),
                "expected_sha256": expected,
                "actual_sha256": actual,
            })
    prepared_repo = index.get("repository_identity") or {}
    current_repo = _repository_identity(root)
    report = {
        "schema_version": "newrouge.capability-input-freshness.v1",
        "analysis_identity_sha256": index.get("analysis_identity_sha256"),
        "authority_input_drift": drift,
        "prepared_repository_identity": prepared_repo,
        "current_repository_identity": current_repo,
        "repository_revision_changed": (
            prepared_repo.get("revision") is not None
            and current_repo.get("revision") is not None
            and prepared_repo.get("revision") != current_repo.get("revision")
        ),
        "status": "blocked" if drift else "current",
    }
    atomic_json(run_dir / "input-freshness.json", report)
    if drift:
        raise ValueError(
            "Capability apply blocked by input drift: "
            + ",".join(str(row["path"]) for row in drift)
        )
    return report


def preview_alignment(root: Path, *, run_id: str) -> dict[str, Any]:
    run_path, state = _load_run(root, run_id)
    run_dir = _run_dir(root, run_id)
    started = time.monotonic()
    candidate = _selected_candidate(run_dir, state)
    existing = load_json(root / FORMAL_CAPABILITIES, {"capabilities": []})
    result = build_alignment(candidate, existing)
    elapsed = time.monotonic() - started
    budget = _budget(state)
    budget["activity_sec"] = float(budget.get("activity_sec") or 0.0) + elapsed
    budget["alignment_activity_sec"] = float(budget.get("alignment_activity_sec") or 0.0) + elapsed
    if float(budget["activity_sec"]) > float(budget["total_budget_sec"]):
        state["phase"] = "alignment-blocked"
        state["stop_reason"] = "Capability planning total active-time budget exhausted"
        atomic_json(run_path, state)
        raise ValueError(state["stop_reason"])
    atomic_json(run_dir / "alignment-preview.json", result)
    atomic_json(run_path, state)
    return result


def _apply_alignment_override(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    rows = [dict(row) for row in base.get("decisions", []) if isinstance(row, dict)]
    by_candidate = {
        str(row.get("candidate_id")): row
        for row in override.get("decisions", [])
        if isinstance(row, dict) and row.get("candidate_id") is not None
    }
    by_stable = {
        str(row.get("stable_id")): row
        for row in override.get("decisions", [])
        if isinstance(row, dict) and row.get("candidate_id") is None and row.get("stable_id")
    }
    out = []
    for row in rows:
        key = str(row.get("candidate_id")) if row.get("candidate_id") is not None else None
        replacement = by_candidate.get(key) if key is not None else by_stable.get(str(row.get("stable_id")))
        out.append(dict(replacement) if replacement is not None else row)
    return {
        "schema_version": "newrouge.capability-alignment.v1",
        "decisions": out,
        "resolved": all(bool(row.get("resolved")) for row in out),
    }


def _formal_payload(candidate: dict[str, Any], alignment: dict[str, Any], source_revision: str) -> tuple[dict[str, Any], dict[str, str]]:
    mapping = {
        str(row.get("candidate_id")): str(row.get("stable_id"))
        for row in alignment.get("decisions", [])
        if row.get("candidate_id") and row.get("stable_id") and row.get("action") != "retire"
    }
    rows = []
    for cap in candidate.get("capabilities", []):
        temp = str(cap.get("capability_id") or "")
        stable = mapping.get(temp)
        if not stable:
            raise ValueError(f"candidate Capability lacks resolved stable identity: {temp}")
        rows.append({
            "capability_id": stable,
            "title": str(cap.get("title") or ""),
            "description": str(cap.get("description") or ""),
            "requirement_ids": sorted({str(value) for value in cap.get("requirement_ids", [])}),
            "boundary_rationale": str(cap.get("boundary_rationale") or ""),
            "source_block_ids": sorted({str(value) for value in cap.get("source_block_ids", [])}),
        })
    return {
        "schema_version": "newrouge.capabilities.v1",
        "generated_at_utc": now(),
        "source_revision": source_revision,
        "capabilities": rows,
    }, mapping


def _task_capability_refs(task_rows: list[dict[str, Any]], cap_by_req: dict[str, set[str]]) -> tuple[list[dict[str, Any]], set[str]]:
    changed: set[str] = set()
    out = deepcopy(task_rows)
    for row in out:
        if not isinstance(row, dict):
            continue
        refs = [str(value) for value in row.get("semantic_refs", row.get("requirement_ids", []))]
        next_refs = sorted({cap for rid in refs for cap in cap_by_req.get(rid, set())})
        current = sorted({str(value) for value in row.get("capability_refs", [])})
        if current != next_refs:
            row["capability_refs"] = next_refs
            task_id = row.get("taskmaster_id")
            if task_id is not None:
                changed.add(str(task_id))
    return out, changed


def _rebind_readiness(root: Path, task_id: str, run_id: str) -> dict[str, Any]:
    from chapter5_semantic_reconciliation import (
        DEFAULT_CH3_SEMANTICS,
        DEFAULT_EXTRACTION_SNAPSHOT,
        DEFAULT_SOURCE_LEDGER,
        DEFAULT_SOURCE_MANIFEST,
        _canonical_sha,
        _load_json,
        _load_task_rows,
        _task_bundle,
        augment_authority_scope_from_acceptance_links,
        build_chapter5_input_fingerprint,
        build_task_authority_scope,
        readiness_path_for_task,
        reconciliation_path_for_task,
    )

    readiness_path = readiness_path_for_task(root, task_id)
    reconciliation_path = reconciliation_path_for_task(root, task_id)
    if not readiness_path.is_file() or not reconciliation_path.is_file():
        return {"task_id": task_id, "status": "missing"}
    reconciliation = _load_json(reconciliation_path, {})
    readiness = _load_json(readiness_path, {})
    old = reconciliation.get("input_fingerprint")
    if not isinstance(old, dict):
        return {"task_id": task_id, "status": "blocked", "reason": "missing_old_fingerprint"}
    task = _task_bundle(_load_task_rows(root), task_id)
    authority_scope, errors = build_task_authority_scope(root, task)
    if errors:
        return {"task_id": task_id, "status": "blocked", "reason": "authority_scope_invalid"}
    stored_scope = reconciliation.get("authority_scope", {})
    stored_refs = []
    if isinstance(stored_scope, dict):
        for kind in ("contracts", "adrs"):
            for item in stored_scope.get(kind, []):
                if isinstance(item, dict) and str(item.get("ref") or "").strip():
                    stored_refs.append(str(item.get("ref")))
    if stored_refs:
        authority_scope = augment_authority_scope_from_acceptance_links(
            root,
            authority_scope,
            {"acceptance_links": [{"authority_refs": sorted(set(stored_refs))}]},
        )
    snapshot = _load_json(root / DEFAULT_EXTRACTION_SNAPSHOT, {})
    new = build_chapter5_input_fingerprint(
        root,
        manifest_path=root / DEFAULT_SOURCE_MANIFEST,
        ledger_path=root / DEFAULT_SOURCE_LEDGER,
        snapshot=snapshot,
        semantics_path=root / DEFAULT_CH3_SEMANTICS,
        task=task,
        authority_scope=authority_scope,
        authority_reconciliation=(
            reconciliation.get("authority_reconciliation", [])
            if isinstance(reconciliation.get("authority_reconciliation"), list)
            else []
        ),
    )
    old_payload = deepcopy(old.get("payload") or {})
    new_payload = deepcopy(new.get("payload") or {})
    old_surface = deepcopy(old_payload.get("task_semantic_surface") or {})
    new_surface = deepcopy(new_payload.get("task_semantic_surface") or {})
    old_caps = old_surface.pop("capability_refs", [])
    new_caps = new_surface.pop("capability_refs", [])
    old_payload["task_semantic_surface"] = old_surface
    new_payload["task_semantic_surface"] = new_surface
    if canonical_sha(old_payload) != canonical_sha(new_payload):
        return {
            "task_id": task_id,
            "status": "blocked",
            "reason": "fingerprint_changed_beyond_capability_refs",
        }
    reconciliation["input_fingerprint"] = new
    reconciliation["capability_rebind"] = {
        "run_id": run_id,
        "previous_capability_refs": old_caps,
        "current_capability_refs": new_caps,
        "rebound_at_utc": now(),
    }
    atomic_json(reconciliation_path, reconciliation)
    readiness["input_fingerprint"] = new
    readiness["reconciliation_sha256"] = "sha256:" + _canonical_sha(reconciliation)
    readiness["capability_rebind"] = reconciliation["capability_rebind"]
    atomic_json(readiness_path, readiness)
    return {"task_id": task_id, "status": "rebound", "capability_refs": new_caps}


def apply(root: Path, *, run_id: str, alignment_override: Path | None, confirm: bool) -> dict[str, Any]:
    if not confirm:
        raise ValueError("Capability apply requires --confirm")
    run_path, state = _load_run(root, run_id)
    run_dir = run_path.parent
    if state.get("review_status") != "selected":
        raise ValueError("Capability apply requires a selected independent review winner")
    review = load_json(run_dir / "review/review.json", {})
    freshness = _validate_snapshot_freshness(root, run_dir)
    candidate = _selected_candidate(run_dir, state)
    ledger = load_json(run_dir / "analysis-input/source-blocks.v1.json", {})
    semantics = load_json(run_dir / "analysis-input/semantic-requirements.v1.json", {})
    errors = validate_candidate(candidate, ledger, semantics, str(state["analysis_identity_sha256"]))
    if errors:
        raise ValueError("selected candidate is invalid: " + "; ".join(errors))
    alignment = build_alignment(candidate, load_json(root / FORMAL_CAPABILITIES, {"capabilities": []}))
    if alignment_override is not None:
        alignment = _apply_alignment_override(alignment, load_json(alignment_override, {}))
    if not alignment.get("resolved"):
        atomic_json(run_dir / "alignment-preview.json", alignment)
        raise ValueError("Capability identity alignment is unresolved; review alignment-preview.json")
    formal, _mapping = _formal_payload(candidate, alignment, str(semantics.get("source_revision") or ""))
    cap_by_req: dict[str, set[str]] = {}
    for cap in formal["capabilities"]:
        for rid in cap["requirement_ids"]:
            cap_by_req.setdefault(rid, set()).add(cap["capability_id"])

    back_path = root / TASK_VIEWS[0]
    gameplay_path = root / TASK_VIEWS[1]
    back, changed_back = _task_capability_refs(load_json(back_path, []), cap_by_req)
    gameplay, changed_game = _task_capability_refs(load_json(gameplay_path, []), cap_by_req)
    changed_tasks = sorted(changed_back | changed_game, key=lambda value: int(value) if value.isdigit() else value)

    edges_path = root / FORMAL_EDGES
    edges_doc = load_json(edges_path, {})
    kept = [
        row for row in edges_doc.get("edges", [])
        if isinstance(row, dict)
        and row.get("source_type") != "capability"
        and row.get("target_type") != "capability"
    ]
    for cap in formal["capabilities"]:
        for rid in cap["requirement_ids"]:
            kept.append({
                "source_type": "requirement",
                "source_id": rid,
                "target_type": "capability",
                "target_id": cap["capability_id"],
                "relation": "grouped_by",
            })
    task_caps: dict[str, set[str]] = {}
    for rows in (back, gameplay):
        for row in rows:
            if not isinstance(row, dict) or row.get("taskmaster_id") is None:
                continue
            tid = str(row["taskmaster_id"])
            task_caps.setdefault(tid, set()).update(str(value) for value in row.get("capability_refs", []))
    for tid, refs in sorted(task_caps.items()):
        for cid in sorted(refs):
            kept.append({
                "source_type": "capability",
                "source_id": cid,
                "target_type": "task",
                "target_id": tid,
                "relation": "implemented_by",
            })
    edges_doc = {
        "schema_version": "newrouge.topology-edges.v1",
        "generated_at_utc": now(),
        "source_revision": formal["source_revision"],
        "edges": kept,
    }

    selection = {
        "schema_version": "newrouge.capability-selection.v1",
        "run_id": run_id,
        "analysis_identity_sha256": state["analysis_identity_sha256"],
        "selected_candidate": state["selected_candidate"],
        "selected_candidate_sha256": canonical_sha(candidate),
        "review_sha256": canonical_sha(review),
        "final_candidate_sha256": canonical_sha(candidate),
        "corrections_applied": bool(review.get("corrections")),
        "alignment": alignment,
        "input_freshness": freshness,
        "generation_readiness_sha256": file_sha(run_dir / "analysis-input/readiness-summary.json"),
        "applied_at_utc": now(),
    }

    targets = {
        root / FORMAL_CAPABILITIES: formal,
        root / FORMAL_SELECTION: selection,
        back_path: back,
        gameplay_path: gameplay,
        edges_path: edges_doc,
    }
    log_capabilities = root / "logs/ci/task-generation/capabilities.v1.json"
    if log_capabilities.parent.exists():
        targets[log_capabilities] = formal
    snapshots = {path: path.read_bytes() if path.is_file() else None for path in targets}
    manifest_path = root / FORMAL_MANIFEST
    manifest_snapshot = manifest_path.read_bytes() if manifest_path.is_file() else None
    try:
        for path, payload in targets.items():
            atomic_json(path, payload)
        manifest = load_json(manifest_path, {})
        artifacts = dict(manifest.get("artifacts") or {})
        for rel_path in (
            "docs/planning/semantic-topology/source-blocks.v1.json",
            "docs/planning/semantic-topology/semantic-requirements.v1.json",
            FORMAL_CAPABILITIES.as_posix(),
            FORMAL_EDGES.as_posix(),
        ):
            path = root / rel_path
            if not path.is_file():
                raise ValueError(f"missing topology artifact while updating manifest: {rel_path}")
            artifacts[rel_path] = file_sha(path)
        manifest["artifacts"] = artifacts
        manifest["generator_revision"] = "post-chapter5-capability-planning-v1"
        atomic_json(manifest_path, manifest)
    except Exception:
        for path, snapshot in snapshots.items():
            if snapshot is None:
                path.unlink(missing_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(snapshot)
        if manifest_snapshot is None:
            manifest_path.unlink(missing_ok=True)
        else:
            manifest_path.write_bytes(manifest_snapshot)
        raise

    rebind = [_rebind_readiness(root, task_id, run_id) for task_id in changed_tasks]
    state["phase"] = "applied"
    state["applied"] = True
    state["changed_task_ids"] = changed_tasks
    state["readiness_rebind"] = rebind
    state["applied_capabilities_sha256"] = file_sha(root / FORMAL_CAPABILITIES)
    atomic_json(run_path, state)
    atomic_json(run_dir / "apply-summary.json", {
        "run_id": run_id,
        "status": "applied",
        "changed_task_ids": changed_tasks,
        "readiness_rebind": rebind,
        "capabilities_sha256": state["applied_capabilities_sha256"],
        "generation_readiness_sha256": file_sha(run_dir / "analysis-input/readiness-summary.json"),
        "mvg_formal_planning_allowed": all(row.get("status") == "rebound" for row in rebind),
    })
    return load_json(run_dir / "apply-summary.json", {})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("prepare")
    p.add_argument("--run-id", required=True)
    p.add_argument("--task-id", action="append", default=[])
    p.add_argument("--allow-unready-draft", action="store_true")
    p.add_argument("--source-manifest", default="logs/ci/task-generation/source-manifest.v1.json")
    p.add_argument("--ledger", default="logs/ci/task-generation/source-blocks.v1.json")
    p.add_argument("--semantics", default="logs/ci/task-generation/semantic-requirements.v1.json")
    p.add_argument("--model-batch-char-budget", type=int, default=160000)
    p.add_argument("--candidate-retry-limit", type=int, default=1)
    p.add_argument("--review-retry-limit", type=int, default=1)
    p.add_argument("--candidate-budget-sec", type=int, default=1800)
    p.add_argument("--total-budget-sec", type=int, default=7200)
    p.add_argument("--request-limit", type=int, default=50)

    for name in ("generate", "review"):
        p_stage = sub.add_parser(name)
        p_stage.add_argument("--run-id", required=True)
        p_stage.add_argument("--runner", required=True)
        p_stage.add_argument("--timeout-sec", type=int, default=1800)

    p_preview = sub.add_parser("preview-alignment")
    p_preview.add_argument("--run-id", required=True)

    p_apply = sub.add_parser("apply")
    p_apply.add_argument("--run-id", required=True)
    p_apply.add_argument("--alignment-override", default="")
    p_apply.add_argument("--confirm", action="store_true")

    p_validate = sub.add_parser("validate-candidate")
    p_validate.add_argument("--run-id", required=True)
    p_validate.add_argument("--candidate", required=True)

    p_status = sub.add_parser("status")
    p_status.add_argument("--run-id", required=True)

    args = parser.parse_args(argv)
    root = Path(args.repo_root).resolve()
    try:
        if args.command == "prepare":
            result = prepare(
                root,
                run_id=args.run_id,
                task_ids=[str(value) for value in args.task_id],
                allow_unready=bool(args.allow_unready_draft),
                source_manifest=repo_path(root, args.source_manifest),
                ledger=repo_path(root, args.ledger),
                semantics=repo_path(root, args.semantics),
                model_batch_char_budget=args.model_batch_char_budget,
                candidate_retry_limit=args.candidate_retry_limit,
                review_retry_limit=args.review_retry_limit,
                candidate_budget_sec=args.candidate_budget_sec,
                total_budget_sec=args.total_budget_sec,
                request_limit=args.request_limit,
            )
        elif args.command == "generate":
            result = generate(root, run_id=args.run_id, runner=Path(args.runner).resolve(), timeout_sec=args.timeout_sec)
        elif args.command == "review":
            result = review(root, run_id=args.run_id, runner=Path(args.runner).resolve(), timeout_sec=args.timeout_sec)
        elif args.command == "preview-alignment":
            result = preview_alignment(root, run_id=args.run_id)
        elif args.command == "apply":
            override = repo_path(root, args.alignment_override) if args.alignment_override else None
            result = apply(root, run_id=args.run_id, alignment_override=override, confirm=bool(args.confirm))
        elif args.command == "validate-candidate":
            _path, state = _load_run(root, args.run_id)
            run_dir = _run_dir(root, args.run_id)
            candidate = load_json(repo_path(root, args.candidate), {})
            errors = validate_candidate(
                candidate,
                load_json(run_dir / "analysis-input/source-blocks.v1.json", {}),
                load_json(run_dir / "analysis-input/semantic-requirements.v1.json", {}),
                str(state["analysis_identity_sha256"]),
            )
            result = {"status": "passed" if not errors else "blocked", "errors": errors}
        else:
            _path, result = _load_run(root, args.run_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
