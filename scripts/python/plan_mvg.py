#!/usr/bin/env python3
"""Independent post-Capability MVG planning that produces an initial manifest or reviewed cumulative delta."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import random
import re
import shutil
import sys
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from _mvg_manifest import validate_manifest
from _planning_skill_common import (
    atomic_json,
    canonical_sha,
    file_sha,
    normalized_file_sha,
    inspect_isolated_runner,
    load_json,
    parse_model_json,
    repo_path,
    run_isolated_model,
    text_sha,
)

RUN_SCHEMA = "newrouge.mvg-planning-run.v1"
PROPOSAL_SCHEMA = "newrouge.mvg-planning-proposal.v1"
SUPPORTED_LLM_BACKENDS = {"codex-cli", "openai-api", "copilot-cli"}
DEFAULT_RUN_ROOT = Path("logs/ci/mvg-planning")
FORMAL_TRACE_ROOT = Path("docs/testing/mvg/planning")
TASK_VIEWS = (
    Path(".taskmaster/tasks/tasks_back.json"),
    Path(".taskmaster/tasks/tasks_gameplay.json"),
)
SOURCE_MANIFEST = Path("logs/ci/task-generation/source-manifest.v1.json")
LEDGER = Path("logs/ci/task-generation/source-blocks.v1.json")
SEMANTICS = Path("logs/ci/task-generation/semantic-requirements.v1.json")
MVG_REVIEW_ATTEMPT_LIMIT = 10
MVG_ERROR_MESSAGE_LIMIT = 2000
MVG_REVIEW_WORKSPACE_LIMIT = 850_000
MVG_REVIEW_EVIDENCE_EXCERPT_CHARS = 2400
MVG_CANDIDATE_LABELS = ("candidate-1", "candidate-2", "candidate-3")
MVG_SELECTION_SCHEMA = "newrouge.mvg-selection-review.v1"
MVG_SELECTION_ATTEMPT_LIMIT = 3
MVG_REPAIR_ATTEMPT_LIMIT = 3
# A candidate may have more than eight ordered hard issues.  Keep a durable
# global stop-loss as well as the per-issue three-repair rule so a malformed
# proposal cannot cause unbounded model calls.
MVG_CANDIDATE_ATTEMPT_LIMIT = 64
MVG_CANDIDATE_INVOCATION_LIMIT = 64
MVG_REPLACEMENT_ROUND_LIMIT = 3


def admission_issue_id(code: str, path: str = "") -> str:
    """Return a stable identity for one ordered candidate hard issue."""
    return f"{str(code).strip()}@{str(path).strip()}"


def admission_repair_prompt(base_prompt: str, strict_contract: str,
                            admission_state: dict[str, Any]) -> str:
    """Build a focused repair prompt from the durable current-issue checkpoint."""
    issue = admission_state.get("current_issue")
    if not isinstance(issue, dict):
        issues = admission_state.get("issues")
        issue = issues[0] if isinstance(issues, list) and issues else {}
    code = str(issue.get("code") or "issue")
    path = str(issue.get("path") or "")
    detail = str(issue.get("detail") or "").strip()
    target = f"{code}:{path}" if path else code
    if detail:
        target += f": {detail}"
    return base_prompt + "\n" + strict_contract + "\n" + correction_prompt([target])


def advance_admission_state(state: dict[str, Any], issue_codes: list[Any], *,
                            repaired: bool) -> dict[str, Any]:
    """Advance one candidate's ordered repair queue after a focused recheck."""
    result = deepcopy(state)
    issues = result.get("issues") if isinstance(result.get("issues"), list) else []
    normalized = []
    for item in issue_codes:
        if isinstance(item, dict):
            code, path = str(item.get("code") or "issue"), str(item.get("path") or "")
            detail = str(item.get("detail") or "").strip()
        else:
            code, path = str(item), ""
            detail = ""
        if not path:
            prior = next((row for row in issues if isinstance(row, dict)
                          and str(row.get("code") or "") == code), None)
            if prior is not None:
                path = str(prior.get("path") or "")
                detail = detail or str(prior.get("detail") or "").strip()
        normalized_issue = {"code": code, "path": path}
        if detail:
            normalized_issue["detail"] = detail
        normalized.append(normalized_issue)
    current_id = (admission_issue_id(str(issues[0].get("code") or "issue"),
                                     str(issues[0].get("path") or ""))
                  if issues and isinstance(issues[0], dict) else "")
    attempts = result.setdefault("issue_attempts", {})
    normalized_ids = {
        admission_issue_id(row["code"], row["path"])
        for row in normalized
    }
    # Callers may only claim a repair when the prior issue is absent from the
    # fresh deterministic/semantic issue set.  This prevents issue reordering
    # from silently deleting an issue that is still present.
    repaired = bool(repaired and current_id and current_id not in normalized_ids)
    if current_id and not repaired:
        current_row = next((row for row in normalized
                            if admission_issue_id(row["code"], row["path"]) == current_id), None)
        if current_row is not None:
            normalized = [current_row] + [row for row in normalized if row is not current_row]
    for row in normalized:
        attempts.setdefault(admission_issue_id(row["code"], row["path"]), 0)
    if not current_id:
        result["issues"] = normalized
    else:
        attempts[current_id] = int(attempts.get(current_id, 0)) + 1
        if repaired:
            result["issues"] = [row for row in normalized
                                 if admission_issue_id(row["code"], row["path"]) != current_id]
        else:
            result["issues"] = normalized
        if not repaired and attempts[current_id] >= MVG_REPAIR_ATTEMPT_LIMIT:
            result.update(status="retired", retirement_reason="repair_attempt_limit_exhausted")
            return result
    if result.get("issues"):
        result["status"] = "repairing"
        result["current_issue"] = result["issues"][0]
    else:
        result["status"] = "admitted"
        result["current_issue"] = None
    return result


def fresh_replacement_lineage(retired: dict[str, Any], candidate: str) -> dict[str, Any]:
    """Create a replacement identity with no retired proposal or findings."""
    prior = str(retired.get("lineage") or f"{candidate}-r1")
    match = re.search(r"-r(\d+)$", prior)
    revision = int(match.group(1)) + 1 if match else 2
    return {"candidate": candidate, "lineage": f"{candidate}-r{revision}",
            "status": "pending", "issues": [], "issue_attempts": {},
            "replacement_of": prior}


def candidate_attempt_numbers(record_count: int, *, segmented: bool) -> range:
    """Return a non-expanding attempt range for one persisted lineage."""
    if segmented:
        return range(record_count + 1, MVG_CANDIDATE_ATTEMPT_LIMIT + 1)
    return range(record_count + 1, MVG_REPAIR_ATTEMPT_LIMIT + 1)


def candidate_resume_attempt_numbers(record_count: int, *, segmented: bool) -> list[int]:
    """Scan persisted attempt slots before allocating the remaining bounded slots."""
    limit = MVG_CANDIDATE_ATTEMPT_LIMIT if segmented else MVG_REPAIR_ATTEMPT_LIMIT
    persisted = min(max(int(record_count), 0), limit)
    return [*range(1, persisted + 1), *range(persisted + 1, limit + 1)]


def reserve_replacement_round(state: dict[str, Any]) -> int | None:
    """Persist one replacement round or return None after the stop-loss."""
    used = int(state.get("replacement_rounds_used", 0) or 0)
    if used >= MVG_REPLACEMENT_ROUND_LIMIT:
        return None
    state["replacement_rounds_used"] = used + 1
    return used + 1


def restore_admission_checkpoint(prior: dict[str, Any], events: list[Any], *,
                                 candidate: str, lineage: str) -> dict[str, Any]:
    """Restore the latest issue queue/counters for one non-terminal lineage."""
    result = deepcopy(prior)
    for event in reversed(events):
        if not isinstance(event, dict) or str(event.get("candidate") or "") != candidate:
            continue
        if str(event.get("lineage") or lineage) != lineage:
            continue
        event_name = str(event.get("event") or "")
        if event_name == "admission-execution-failed":
            result.update(status="execution-failed", execution_error=deepcopy(event.get("error") or {}))
            return result
        if event_name in {"candidate-retired", "candidate-admitted"}:
            if isinstance(event.get("admission"), dict):
                result.update(deepcopy(event["admission"]))
            result["status"] = "retired" if event_name == "candidate-retired" else "admitted"
            if isinstance(event.get("issues"), list):
                result["issues"] = [dict(row) for row in event["issues"] if isinstance(row, dict)]
            if isinstance(event.get("issue_attempts"), dict):
                result["issue_attempts"] = dict(event["issue_attempts"])
            if event.get("retirement_reason"):
                result["retirement_reason"] = event["retirement_reason"]
            return result
        if event_name != "admission-issue":
            continue
        if not result.get("issues") and isinstance(event.get("issue"), dict):
            result["issues"] = [dict(event["issue"])]
        if isinstance(event.get("issue_attempts"), dict):
            result["issue_attempts"] = dict(event["issue_attempts"])
        if event.get("status"):
            result["status"] = event["status"]
        break
    return result


def _latest_attempt_artifact(paths: Any) -> Path | None:
    """Return the highest numeric attempt artifact, not lexical last."""
    candidates = [path for path in paths if isinstance(path, Path)]
    if not candidates:
        return None
    def key(path: Path) -> tuple[int, str]:
        match = re.search(r"(?:^|/)attempt-(\d+)(?:/|$)", path.as_posix())
        return (int(match.group(1)) if match else -1, path.as_posix())
    return max(candidates, key=key)


def _admission_execution_artifact(workspace: Path, review_key: str) -> Path | None:
    """Return the execution receipt for one isolated semantic-gate review key."""
    safe_review_key = re.sub(r"[^a-zA-Z0-9-]", "-", str(review_key))[:80] or "default"
    published = workspace / f"gate-{safe_review_key}" / "semantic-review-execution.json"
    return published if published.is_file() else None


def _bound_admission_artifacts(root: Path, run_dir: Path,
                               admission: dict[str, Any]) -> tuple[Path, Path, Path]:
    """Resolve a candidate's proposal, proof, and receipt within its workspace."""
    workspace_ref = str(admission.get("workspace") or "")
    if not workspace_ref:
        raise ValueError("candidate admission workspace is missing")
    candidate_root = repo_path(run_dir, workspace_ref)
    proposal = repo_path(candidate_root, "proposal.json")
    proof = repo_path(root, str(admission.get("review_path") or ""))
    execution = repo_path(root, str(admission.get("review_execution_path") or ""))
    if not (proposal.is_relative_to(candidate_root.resolve())
            and proof.is_relative_to(candidate_root.resolve())
            and execution.is_relative_to(candidate_root.resolve())):
        raise ValueError("candidate admission artifact escapes its workspace")
    return proposal, proof, execution


def build_selection_input_identity(analysis_identity_sha256: str,
                                   candidate_hashes: dict[str, str],
                                   candidate_lineages: dict[str, Any], *,
                                   incumbent_present: bool) -> tuple[dict[str, str], str]:
    """Bind comparative selection to every proposal and lineage it evaluates."""
    aliases = ("A", "B", "C", "D") if incumbent_present else ("A", "B", "C")
    identity = {alias: str(candidate_hashes.get(alias) or "") for alias in aliases}
    if any(not value for value in identity.values()):
        raise ValueError("selection input identity is missing a scored proposal hash")
    digest = canonical_sha({
        "analysis_identity_sha256": analysis_identity_sha256,
        "candidates": identity,
        "candidate_lineages": candidate_lineages,
        "incumbent_present": incumbent_present,
    })
    return identity, digest


def candidate_admission_errors(root: Path, state: dict[str, Any],
                               proposal: dict[str, Any],
                               semantic_review: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """Return ordered hard issues that prevent a proposal entering selection."""
    validation = validate_proposal(root, state, proposal)
    issues: list[dict[str, str]] = [
        {"code": str(error), "path": "proposal"} for error in validation.get("errors", [])
    ]
    if int(validation.get("unresolved_gap_count", 0) or 0) > 0:
        issues.append({"code": "unresolved_planning_gaps", "path": "proposal.gaps"})
    if validation.get("status") == "passed":
        baseline = _run_dir(root, str(state.get("run_id"))) / "analysis-input/existing-manifest.json"
        if baseline.is_file():
            try:
                existing = load_json(baseline, {})
                delta = build_delta(existing, proposal)
                from update_mvg_baseline import apply_delta
                apply_delta(existing, delta, root=root, validate_final=True)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                issues.append({"code": "delta_validation_blocked", "path": "manifest", "detail": str(exc)})
    if semantic_review is not None:
        from _mvg_planning_review import semantic_review_errors
        scope = state.get("planning_scope") if isinstance(state.get("planning_scope"), dict) else None
        allowed = set(scope.get("requirement_ids", [])) if scope else None
        semantics_path = _run_dir(root, str(state.get("run_id"))) / "analysis-input/semantic-requirements.v1.json"
        semantics = load_json(semantics_path, None)
        if (not isinstance(semantics, dict) or not isinstance(semantics.get("requirements"), list)
                or not semantics["requirements"]):
            issues.append({"code": "prepared_semantic_requirements_snapshot_missing_or_invalid",
                           "path": "analysis-input/semantic-requirements.v1.json"})
            errors = []
        else:
            errors = semantic_review_errors(state, proposal, semantic_review, semantics, allowed)
        finding_detail = "; ".join(
            str(value).strip() for value in (semantic_review.get("findings") or [])
            if isinstance(value, str) and value.strip()
        )[:1000]
        for error in errors:
            issue = {"code": str(error), "path": "semantic-review"}
            if finding_detail and str(error) == "semantic_review_not_approved":
                issue["detail"] = finding_detail
            issues.append(issue)
    # A candidate may enter selection only with no deterministic or semantic
    # hard issue. Preserve first-seen order for focused repair routing.
    seen: set[str] = set()
    ordered: list[dict[str, str]] = []
    for issue in issues:
        key = admission_issue_id(issue.get("code", "issue"), issue.get("path", ""))
        if key not in seen:
            seen.add(key)
            ordered.append(issue)
    return ordered


def run_admission_semantic_gate(root: Path, state: dict[str, Any], proposal: dict[str, Any],
                                workspace: Path, *, runner: Path | None,
                                timeout_sec: int, invoke: Any = None,
                                review_key: str = "default",
                                before_invoke: Any = None) -> dict[str, Any]:
    """Run the independent semantic hard gate in a fresh candidate lineage workspace."""
    run_dir = _run_dir(root, str(state.get("run_id")))
    semantics = load_json(run_dir / "analysis-input/semantic-requirements.v1.json", None)
    if (not isinstance(semantics, dict) or not isinstance(semantics.get("requirements"), list)
            or not semantics["requirements"]):
        raise ValueError("prepared semantic requirements snapshot is missing or invalid")
    scope = state.get("planning_scope") if isinstance(state.get("planning_scope"), dict) else None
    allowed = set(scope.get("requirement_ids", [])) if scope else None
    required_requirements = {
        str(row.get("requirement_id")) for row in semantics.get("requirements", [])
        if isinstance(row, dict) and row.get("status", "active") == "active"
        and row.get("delivery_relevant", True) and (allowed is None or str(row.get("requirement_id")) in allowed)
    }
    flow_ids = {str(row.get("id")) for row in (proposal.get("manifest_candidate") or {}).get("flows", [])
                if isinstance(row, dict) and str(row.get("id") or "").strip()}
    proposal_sha = canonical_sha(proposal)
    workspace.mkdir(parents=True, exist_ok=True)
    atomic_json(workspace / "proposal.json", proposal)
    source = run_dir / "analysis-input"
    safe_review_key = re.sub(r"[^a-zA-Z0-9-]", "-", str(review_key))[:80] or "default"
    review_workspace = workspace / f"gate-{safe_review_key}"
    review_workspace.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, review_workspace / "analysis-input", dirs_exist_ok=True)
    prompt = ("You are the independent MVG candidate admission semantic gate. "
              "Review proposal.json against analysis-input and return JSON only. "
              "Block any semantic, ownership, handoff, recovery, or accounting issue. "
              f"schema_version='newrouge.mvg-semantic-review.v1', analysis_identity_sha256='{state['analysis_identity_sha256']}', "
              f"proposal_sha256='{proposal_sha}'. Return complete requirement_reviews and flow_reviews.")
    attempts: list[dict[str, Any]] = []
    proposal_sha = canonical_sha(proposal)
    publication = review_workspace / (
        f"semantic-review-publication-{proposal_sha.removeprefix('sha256:')}-{safe_review_key}.json")
    runner_identity = inspect_isolated_runner(runner) if runner is not None else {"backend": "isolated-invoke"}
    publication_identity = {
        "analysis_identity_sha256": state["analysis_identity_sha256"],
        "proposal_sha256": proposal_sha, "runner": runner_identity,
    }
    if publication.is_file():
        from _planning_review_publication import resume_publication
        resume_publication(publication, publication_identity, atomic_json)
        restored = load_json(review_workspace / "semantic-review.json", None)
        restored_execution = load_json(review_workspace / "semantic-review-execution.json", None)
        if isinstance(restored, dict):
            restored_errors = validate_review_shape(
                state, proposal, restored,
                requirement_ids=required_requirements, flow_ids=flow_ids,
                check_identity=True, check_accounting=False,
            )
            if isinstance(restored_execution, dict):
                from _mvg_planning_review import review_execution_errors
                restored_errors.extend(review_execution_errors(state, proposal, restored_execution, restored))
            else:
                restored_errors.append("candidate_admission_execution_missing")
            if restored_errors:
                raise ValueError("candidate admission publication evidence is invalid: "
                                 + ";".join(restored_errors))
            return restored
    for number in range(1, MVG_REVIEW_ATTEMPT_LIMIT + 1):
        attempt_workspace = review_workspace / f"attempt-{number}"
        attempt_workspace.mkdir(parents=True, exist_ok=True)
        atomic_json(attempt_workspace / "proposal.json", proposal)
        _prepare_review_workspace(run_dir, attempt_workspace, proposal)
        prompt_path = attempt_workspace / "prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8", newline="\n")
        output = attempt_workspace / "semantic-review.json"
        schema = attempt_workspace / "semantic-review-output-schema.json"
        atomic_json(schema, semantic_review_output_schema())
        try:
            if runner is not None:
                if before_invoke is not None:
                    before_invoke()
                receipt = run_isolated_model(runner, workspace=attempt_workspace, prompt_path=prompt_path,
                                             output_path=output, timeout_sec=timeout_sec,
                                             output_schema=schema)
            elif invoke is not None:
                generated, execution = invoke(prompt, number, output_name="semantic-review.json",
                                              output_schema_path=schema,
                                              output_schema=semantic_review_output_schema())
                if generated != output:
                    shutil.copyfile(generated, output)
                receipt = execution.get("receipt", {}) if isinstance(execution, dict) else {}
            else:
                raise ValueError("independent semantic admission runner is unavailable")
            if runner is not None and ((receipt or {}).get("model_tools") != []
                                       or not (receipt or {}).get("model")):
                raise ValueError("candidate admission reviewer execution identity is incomplete")
            result = parse_model_json(output)
            shape_errors = validate_review_shape(state, proposal, result,
                requirement_ids=required_requirements, flow_ids=flow_ids,
                check_identity=True, check_accounting=False)
            if shape_errors:
                raise ValueError("candidate admission semantic review output invalid: " + ";".join(shape_errors))
            execution = {
                "runner": str(runner) if runner else "isolated-invoke", "runner_info": runner_identity,
                "receipt": receipt, "output_sha256": file_sha(output),
                "analysis_identity_sha256": state["analysis_identity_sha256"],
                "proposal_sha256": proposal_sha, "semantic_review_sha256": canonical_sha(result),
                "attempt_count": number,
            }
            atomic_json(attempt_workspace / "semantic-review-execution.json", execution)
            from _planning_review_publication import prepare_publication, resume_publication
            prepare_publication(publication, publication_identity, {
                "semantic-review.json": result,
                "semantic-review-execution.json": execution}, atomic_json)
            resume_publication(publication, publication_identity, atomic_json)
            return result
        except (OSError, RuntimeError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            attempts.append({"attempt": number, "status": "execution-failed",
                             "error": _compact_exception_message(exc),
                             "error_type": classify_review_error(exc)})
    raise MVGReviewAttemptBudgetError(
        error_type=str(attempts[-1].get("error_type") or "runner_execution_failed"),
        attempts_used=len(attempts), attempt_limit=MVG_REVIEW_ATTEMPT_LIMIT,
        last_error=str(attempts[-1].get("error") or "admission semantic gate failed"),
    )


def _compact_exception_message(value: Any, limit: int = MVG_ERROR_MESSAGE_LIMIT) -> str:
    """Keep durable attempt logs diagnostic without persisting runner payloads."""
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    suffix = " ...[truncated]"
    available = max(0, limit - len(suffix))
    markers = (
        "Input exceeds the maximum length",
        "maximum context length",
        "stream disconnected",
        "timed out",
    )
    for marker in markers:
        index = text.lower().find(marker.lower())
        if index >= 0:
            start = max(0, index - 240)
            return (text[start:start + available] + suffix).strip()
    return text[:available].rstrip() + suffix


def classify_review_error(exc: BaseException) -> str:
    """Return a stable machine-readable class for one isolated review failure."""
    text = str(exc)
    lowered = text.lower()
    if isinstance(exc, MVGCandidateInvocationBudgetError):
        return exc.error_type
    if ("input exceeds the maximum length" in lowered
            or "maximum context length" in lowered
            or "bounded mvg review workspace exceeds" in lowered):
        return "runner_input_too_large"
    if "stream disconnected" in lowered or "connection reset" in lowered:
        return "runner_stream_disconnected"
    if isinstance(exc, TimeoutError) or "timed out" in lowered or "timeout" in lowered:
        return "runner_timeout"
    if "output schema" in lowered or "json schema" in lowered:
        return "runner_output_schema_invalid"
    if "json" in lowered or "model output" in lowered:
        return "runner_invalid_json"
    if "identity" in lowered:
        return "runner_identity_invalid"
    return "runner_execution_failed"


def validate_review_shape(state: dict[str, Any], proposal: dict[str, Any], review: dict[str, Any], *,
                          requirement_ids: set[str], flow_ids: set[str],
                          check_identity: bool = True, check_accounting: bool = True) -> list[str]:
    """Validate the review envelope before treating it as a semantic verdict.

    This is intentionally stricter than the semantic review gate: malformed or
    incomplete model output is a runner/schema failure and may be retried. A
    structurally valid ``blocked`` verdict remains a semantic finding and is
    not retried automatically.
    """
    errors: list[str] = []
    if review.get("schema_version") != "newrouge.mvg-semantic-review.v1":
        errors.append("semantic_review_schema_mismatch")
    if check_identity and review.get("analysis_identity_sha256") != state.get("analysis_identity_sha256"):
        errors.append("semantic_review_analysis_identity_mismatch")
    if check_identity and review.get("proposal_sha256") != canonical_sha(proposal):
        errors.append("semantic_review_proposal_identity_mismatch")
    if review.get("verdict") not in {"approved", "blocked"}:
        errors.append("semantic_review_verdict_invalid")
    findings = review.get("findings")
    if not isinstance(findings, list):
        errors.append("semantic_review_findings_not_array")
    elif review.get("verdict") == "approved" and findings:
        errors.append("semantic_review_approved_findings_nonempty")

    def check_rows(key: str, id_key: str, expected: set[str], verdicts: set[str]) -> None:
        rows = review.get(key)
        if not isinstance(rows, list):
            errors.append(f"semantic_review_invalid_array:{key}")
            return
        ids: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                errors.append(f"semantic_review_invalid_row:{key}")
                continue
            row_id = str(row.get(id_key) or "")
            ids.append(row_id)
            if row.get("verdict") not in verdicts:
                errors.append(f"semantic_review_invalid_verdict:{key}")
            if not isinstance(row.get("rationale"), str) or not row["rationale"].strip():
                errors.append(f"semantic_review_rationale_missing:{key}:{row_id}")
        if set(ids) != expected or len(ids) != len(expected):
            errors.append(f"semantic_review_incomplete:{key}")

    if check_accounting:
        check_rows("requirement_reviews", "requirement_id", requirement_ids,
                   {"covered", "other_verification", "deferred", "blocked"})
        check_rows("flow_reviews", "flow_id", flow_ids, {"sound", "blocked"})
    else:
        for key in ("requirement_reviews", "flow_reviews"):
            if not isinstance(review.get(key), list):
                errors.append(f"semantic_review_invalid_array:{key}")
    return sorted(set(errors))


def backfill_review_error_types(state: dict[str, Any]) -> bool:
    """Annotate pre-budget-error logs without changing their historical status."""
    changed = False
    for row in state.get("semantic_review_attempts", []) or []:
        if not isinstance(row, dict) or row.get("error_type") or row.get("status") == "completed":
            continue
        error = str(row.get("error") or "")
        if not error:
            continue
        row["error_type"] = classify_review_error(error)
        changed = True
    return changed


def semantic_review_output_schema() -> dict[str, Any]:
    """Return the transport-level JSON schema for an independent review."""
    rationale = {"type": "string", "minLength": 1}
    requirement = {
        "type": "object",
        "additionalProperties": False,
        "required": ["requirement_id", "verdict", "rationale", "disposition",
                     "flow_id", "sink_id", "verification_ref", "authority_ref"],
        "properties": {
            "requirement_id": {"type": "string", "minLength": 1},
            "verdict": {"type": "string", "enum": ["covered", "other_verification", "deferred", "blocked"]},
            "rationale": rationale,
            "disposition": {"type": "string", "enum": ["flow", "other_verification", "deferred"]},
            "flow_id": {"type": ["string", "null"]},
            "sink_id": {"type": ["string", "null"]},
            "verification_ref": {"type": ["string", "null"]},
            "authority_ref": {"type": ["string", "null"]},
            "route": {"type": "string", "minLength": 1},
        },
    }
    flow = {
        "type": "object",
        "additionalProperties": False,
        "required": ["flow_id", "verdict", "rationale"],
        "properties": {
            "flow_id": {"type": "string", "minLength": 1},
            "verdict": {"type": "string", "enum": ["sound", "blocked"]},
            "rationale": rationale,
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "analysis_identity_sha256", "proposal_sha256",
                      "verdict", "findings", "requirement_reviews", "flow_reviews"],
        "properties": {
            "schema_version": {"type": "string", "const": "newrouge.mvg-semantic-review.v1"},
            "analysis_identity_sha256": {"type": "string", "minLength": 1},
            "proposal_sha256": {"type": "string", "minLength": 1},
            "verdict": {"type": "string", "enum": ["approved", "blocked"]},
            "findings": {"type": "array", "items": {"type": "string", "minLength": 1}},
            "requirement_reviews": {"type": "array", "items": requirement},
            "flow_reviews": {"type": "array", "items": flow},
        },
    }


def mvg_selection_output_schema(*, incumbent_present: bool) -> dict[str, Any]:
    """Return the strict envelope for comparative MVG candidate selection."""
    labels = ["A", "B", "C"] + (["D"] if incumbent_present else [])
    review = {
        "type": "object",
        "additionalProperties": False,
        "required": ["label", "verdict", "rationale", "rank"],
        "properties": {
            "label": {"type": "string", "enum": labels},
            "verdict": {"type": "string", "const": "viable"},
            "rationale": {"type": "string", "minLength": 1},
            "rank": {"type": "integer", "minimum": 1},
        },
    }
    properties: dict[str, Any] = {
        "schema_version": {"type": "string", "const": MVG_SELECTION_SCHEMA},
        "selected": {"anyOf": [{"type": "string", "enum": labels}, {"type": "null"}]},
        "status": {"type": "string", "const": "selected"},
        "candidate_reviews": {"type": "array", "items": review},
        "tradeoffs": {"type": "array", "items": {"type": "string", "minLength": 1}, "minItems": 1},
        "evidence_refs": {"type": "array", "items": {"type": "string", "minLength": 1}},
        "rationale": {"type": "string", "minLength": 1},
    }
    return {
        "type": "object",
        "required": list(properties),
        "properties": properties,
        "additionalProperties": False,
    }


def mvg_selection_prompt(*, incumbent_present: bool,
                         planning_scope: dict[str, Any] | None) -> str:
    """Build the comparative selector prompt with the frozen scope explicit."""
    scope = planning_scope or {}
    scope_view = {
        key: scope.get(key)
        for key in ("scope_id", "mode", "flow_ids", "requirement_ids", "capability_refs",
                    "task_ids", "test_ids", "excluded_claims")
        if scope.get(key) is not None
    }
    incumbent_note = (
        " Also read D.json, which is the current published MVG incumbent and may be retained."
        if incumbent_present else ""
    )
    return f"""You are the independent MVG proposal evaluator.
Read the prepared analysis-input and anonymous proposal files A.json, B.json, C.json
under this isolated workspace.{incumbent_note}
This run has a frozen manifest planning scope. Only the immutable planning scope is required;
only the immutable planning scope and
coverage-skeleton rows are required for this comparison. Requirements outside that
scope are intentionally excluded by excluded_claims and must not be penalized as
missing coverage. A proposal that widens the scope is blocked; a proposal that
preserves the exact scope and accounts for every scoped row is complete for this run.
Frozen planning scope:
{json.dumps(scope_view, ensure_ascii=False, sort_keys=True)}
Select one complete proposal; never merge proposals. The exact capabilities.v1.json is
the only Capability SSoT. GDD, task views, contracts and tests are auxiliary evidence.
Evaluate in order: Capability membership fidelity, complete in-scope Requirement coverage,
coherent player journeys and handoffs, ownership/test feasibility, and cumulative
baseline preservation. A new candidate is not automatically better than the incumbent.
Return JSON only with schema_version={MVG_SELECTION_SCHEMA!r}, selected={"A|B|C|D|null" if incumbent_present else "A|B|C|null"},
status=selected, candidate_reviews with exactly one viable row for each available label.
Rank every row with a unique integer from 1 through the number of rows; array order is irrelevant.
The selected label must have rank 1. All rows are already admitted and viable; ranking is
comparative preference only and is not a semantic fallback mechanism.
tradeoffs (non-empty), evidence_refs (paths or Requirement IDs), and rationale (non-empty).
"""


def ranked_semantic_fallback_candidates(selection: dict[str, Any],
                                         alias_mapping: dict[str, str], *,
                                         selected: str) -> list[str]:
    """Return ranked viable identities for legacy inspection only.

    The production review path never falls back to a ranked candidate after
    selection; all candidates must be admitted before the selector runs.
    """
    reviews = selection.get("candidate_reviews", [])
    ranked = sorted(
        (row for row in reviews if isinstance(row, dict)
         and row.get("verdict") == "viable"
         and isinstance(row.get("rank"), int) and not isinstance(row.get("rank"), bool)),
        key=lambda row: (row["rank"], str(row.get("label") or "")),
    )
    result: list[str] = []
    for row in ranked:
        label = str(row.get("label") or "")
        candidate = "incumbent" if label == "D" else str(alias_mapping.get(label) or "")
        if (candidate in MVG_CANDIDATE_LABELS or candidate == "incumbent") \
                and candidate != selected and candidate not in result:
            result.append(candidate)
    return result


def validate_mvg_selection(result: dict[str, Any], *, candidate_labels: set[str],
                           incumbent_present: bool,
                           alias_mapping: dict[str, str] | None = None,
                           viable_labels: set[str] | None = None) -> list[str]:
    """Validate comparative selection without judging semantic quality locally."""
    errors: list[str] = []
    allowed = {"A", "B", "C"} | ({"D"} if incumbent_present else set())
    if result.get("schema_version") != MVG_SELECTION_SCHEMA:
        errors.append("mvg_selection_schema_mismatch")
    if result.get("status") != "selected":
        errors.append("mvg_selection_status_invalid")
    selected = result.get("selected")
    if selected is not None and selected not in allowed:
        errors.append("mvg_selection_label_invalid")
    if result.get("status") == "selected" and selected is None:
        errors.append("mvg_selection_missing_winner")
    if result.get("status") != "selected" and selected is not None:
        errors.append("mvg_selection_unexpected_winner")
    reviews = result.get("candidate_reviews")
    expected_labels = {"A", "B", "C"} | ({"D"} if incumbent_present else set())
    if not isinstance(reviews, list):
        errors.append("mvg_selection_reviews_missing")
    else:
        labels: list[str] = []
        for row in reviews:
            if not isinstance(row, dict):
                errors.append("mvg_selection_review_invalid")
                continue
            label = str(row.get("label") or "")
            labels.append(label)
            if label not in expected_labels:
                errors.append(f"mvg_selection_review_unknown:{label}")
            if row.get("verdict") != "viable":
                errors.append(f"mvg_selection_review_verdict_invalid:{label}")
            if not str(row.get("rationale") or "").strip():
                errors.append(f"mvg_selection_review_rationale_missing:{label}")
        # Rank is part of the persisted comparative-selection contract, not an
        # optional presentation hint. It records why an admitted candidate
        # lost without turning rank into a semantic fallback path.
        for row in reviews:
            if not isinstance(row, dict):
                continue
            if type(row.get("rank")) is not int or row["rank"] < 1:
                errors.append(f"mvg_selection_review_rank_invalid:{row.get('label', '')}")
        ranks = [row.get("rank") for row in reviews
                 if isinstance(row, dict) and type(row.get("rank")) is int]
        if sorted(ranks) != list(range(1, len(expected_labels) + 1)):
            errors.append("mvg_selection_review_rank_invalid")
        if set(labels) != expected_labels or len(labels) != len(expected_labels):
            errors.append("mvg_selection_review_incomplete")
        if selected is not None:
            selected_review = next((row for row in reviews
                                    if isinstance(row, dict)
                                    and row.get("label") == selected), None)
            if isinstance(selected_review, dict) and selected_review.get("rank") != 1:
                errors.append("mvg_selection_winner_not_top_ranked")
    if not isinstance(result.get("tradeoffs"), list) or not result.get("tradeoffs"):
        errors.append("mvg_selection_tradeoffs_missing")
    if not isinstance(result.get("evidence_refs"), list):
        errors.append("mvg_selection_evidence_refs_missing")
    if not str(result.get("rationale") or "").strip():
        errors.append("mvg_selection_rationale_missing")
    if candidate_labels and selected in {"A", "B", "C"}:
        available_aliases = alias_mapping or {"A": "candidate-1", "B": "candidate-2", "C": "candidate-3"}
        if available_aliases[selected] not in candidate_labels:
            errors.append(f"mvg_selection_selected_candidate_unavailable:{selected}")
        elif viable_labels is not None and available_aliases[selected] not in viable_labels:
            errors.append(f"mvg_selection_selected_candidate_not_formally_applicable:{selected}")
    if selected == "D" and viable_labels is not None and "incumbent" not in viable_labels:
        errors.append("mvg_selection_selected_incumbent_not_formally_applicable")
    return sorted(set(errors))


class MVGReviewAttemptBudgetError(ValueError):
    """Terminal review retry error carrying the diagnostic that exhausted retries."""

    def __init__(self, *, error_type: str, attempts_used: int, attempt_limit: int, last_error: str):
        self.error_type = error_type
        self.attempts_used = attempts_used
        self.attempt_limit = attempt_limit
        self.last_error = last_error
        super().__init__(
            "MVG independent review execution attempt budget exhausted; upstream proposal is preserved; "
            f"error_type={error_type}; attempts={attempts_used}/{attempt_limit}; "
            f"last_error={_compact_exception_message(last_error)}"
        )


class MVGCandidateInvocationBudgetError(RuntimeError):
    error_type = "candidate_lineage_invocation_budget_exhausted"


def validate_selection_execution_receipt(
    state: dict[str, Any], selection: dict[str, Any], receipt: dict[str, Any], *,
    selection_input_sha256: str, output_sha256: str,
    expected_attempt: int | None = None,
) -> list[str]:
    """Validate the runner and hash binding for one comparative selection output."""
    from _planning_skill_common import validate_runner_description

    errors: list[str] = []
    if not isinstance(receipt, dict):
        return ["selection_receipt_schema_invalid", "selection_receipt_not_object"]
    if receipt.get("schema_version") != "newrouge.mvg-selection-execution-receipt.v1":
        errors.append("selection_receipt_schema_invalid")
    if receipt.get("analysis_identity_sha256") != state.get("analysis_identity_sha256"):
        errors.append("selection_analysis_identity_invalid")
    if expected_attempt is not None and receipt.get("attempt") != expected_attempt:
        errors.append("selection_attempt_identity_invalid")
    if receipt.get("selection_input_sha256") != selection_input_sha256:
        errors.append("selection_input_identity_invalid")
    if receipt.get("output_sha256") != output_sha256:
        errors.append("selection_output_identity_invalid")
    runner_info = receipt.get("runner_info")
    try:
        if not isinstance(runner_info, dict):
            raise ValueError("runner description must be an object")
        validate_runner_description(runner_info)
    except (TypeError, ValueError):
        errors.append("selection_runner_description_invalid")
    runner_receipt = receipt.get("runner_receipt") or {}
    expected_model = str((runner_info or {}).get("model") or "") if isinstance(runner_info, dict) else ""
    actual_model = str(runner_receipt.get("model") or "") if isinstance(runner_receipt, dict) else ""
    model_matches = (
        bool(actual_model)
        and (expected_model.lower() in {"auto", "automatic", "codex-cli-default"}
             or actual_model == expected_model)
    )
    if (not isinstance(runner_receipt, dict)
            or not model_matches
            or runner_receipt.get("model_tools") != []):
        errors.append("selection_runner_identity_invalid")
    if not isinstance(selection, dict) or selection.get("status") != "selected":
        errors.append("selection_result_invalid")
    return sorted(set(errors))


_candidate_invocation_lock_guard = threading.Lock()
_candidate_invocation_locks: dict[str, threading.Lock] = {}


def _candidate_invocation_lock(path: Path) -> threading.Lock:
    """Return the process-local lock for one durable lineage counter.

    Segmented candidate generation intentionally runs independent model calls
    in parallel.  All segments still reserve from one lineage counter, so the
    read/modify/atomic-replace sequence must be serialized on Windows where
    concurrent replacement of the shared ``.tmp`` path raises WinError 32.
    """
    key = str(path.resolve())
    with _candidate_invocation_lock_guard:
        return _candidate_invocation_locks.setdefault(key, threading.Lock())


def reserve_candidate_model_invocation(candidate_root: Path, candidate: str, lineage: str) -> int:
    """Durably reserve one model call against the candidate-lineage stop-loss."""
    path = candidate_root / "lineage-execution.json"
    with _candidate_invocation_lock(path):
        current = load_json(path, {})
        if current and (current.get("candidate") != candidate or current.get("lineage") != lineage):
            raise ValueError("candidate lineage execution identity changed")
        count = int(current.get("model_invocation_count", 0) or 0)
        if count >= MVG_CANDIDATE_INVOCATION_LIMIT:
            raise MVGCandidateInvocationBudgetError(
                f"candidate lineage reached {MVG_CANDIDATE_INVOCATION_LIMIT} model invocations")
        count += 1
        atomic_json(path, {"candidate": candidate, "lineage": lineage,
                           "model_invocation_count": count})
        return count


class MVGReviewPreparationError(ValueError):
    """Terminal deterministic review-input failure; no model attempt was made."""

    def __init__(self, *, error_type: str, last_error: str, attempt_limit: int):
        self.error_type = error_type
        self.attempts_used = 0
        self.attempt_limit = attempt_limit
        self.last_error = last_error
        super().__init__(
            "MVG independent review preparation blocked; upstream proposal is preserved; "
            f"error_type={error_type}; attempts=0/{attempt_limit}; "
            f"last_error={_compact_exception_message(last_error)}"
        )


def _review_reference_paths(proposal: dict[str, Any]) -> set[str]:
    """Collect repository-relative evidence paths explicitly claimed by a proposal."""
    refs: set[str] = set()
    manifest = proposal.get("manifest_candidate") or {}
    if not isinstance(manifest, dict):
        return refs
    for flow in manifest.get("flows", []):
        if not isinstance(flow, dict):
            continue
        source_paths = flow.get("source_paths")
        if isinstance(source_paths, list):
            refs.update(str(value).replace("\\", "/") for value in source_paths if str(value).strip())
        for handoff in flow.get("handoffs", []):
            if isinstance(handoff, dict) and handoff.get("contract_ref"):
                refs.add(str(handoff["contract_ref"]).split("#", 1)[0].replace("\\", "/"))
            if isinstance(handoff, dict):
                contract_refs = handoff.get("contract_refs")
                if isinstance(contract_refs, list):
                    refs.update(str(value).split("#", 1)[0].replace("\\", "/")
                                for value in contract_refs if str(value).strip())
    tests = manifest.get("tests")
    if isinstance(tests, list):
        for row in tests:
            if isinstance(row, dict) and row.get("path"):
                refs.add(str(row["path"]).split("#", 1)[0].replace("\\", "/"))
    for row in proposal.get("entrypoints", []):
        if isinstance(row, dict) and row.get("status") == "existing_verified" and row.get("path"):
            refs.add(str(row["path"]).split("#", 1)[0].replace("\\", "/"))
    return {value for value in refs if value}


def _review_task_ids(proposal: dict[str, Any]) -> set[int]:
    """Return only Taskmaster IDs actually claimed by the fixed proposal."""
    result: set[int] = set()
    manifest = proposal.get("manifest_candidate") or {}
    if isinstance(manifest, dict):
        for flow in manifest.get("flows", []):
            if not isinstance(flow, dict):
                continue
            values = list(flow.get("task_ids") or [])
            for handoff in flow.get("handoffs", []) if isinstance(flow.get("handoffs"), list) else []:
                if isinstance(handoff, dict):
                    values.extend(handoff.get(key) for key in ("producer_task", "consumer_task", "owner_task"))
            for value in values:
                if type(value) is int:
                    result.add(value)
    for row in proposal.get("coverage_table", []) if isinstance(proposal.get("coverage_table"), list) else []:
        if isinstance(row, dict) and type(row.get("task_id")) is int:
            result.add(row["task_id"])
    for row in proposal.get("entrypoints", []) if isinstance(proposal.get("entrypoints"), list) else []:
        if isinstance(row, dict) and type(row.get("owner_task")) is int:
            result.add(row["owner_task"])
    return result


def _review_excerpt(path: Path, limit: int = MVG_REVIEW_EVIDENCE_EXCERPT_CHARS) -> tuple[str, bool]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return "", True
    if len(text) <= limit:
        return text, False
    head = limit // 2
    tail = limit - head
    return text[:head] + "\n... [excerpt truncated; full file hash is retained] ...\n" + text[-tail:], True


def _write_review_projection(path: Path, payload: Any) -> None:
    """Write ephemeral model context without touching the durable run journal."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _write_review_evidence_projection(target: Path, evidence: list[dict[str, Any]], excerpt_limit: int) -> None:
    """Write evidence excerpts at the requested bounded size."""
    projected: list[dict[str, Any]] = []
    for item in evidence:
        # Missing references have no excerpt to shrink and must remain visible.
        if "path" not in item or "source_path" not in item:
            projected.append(dict(item))
            continue
        source_path = Path(str(item["source_path"]))
        excerpt, truncated = _review_excerpt(source_path, excerpt_limit)
        projected.append({
            "path": item["path"],
            "sha256": item["sha256"],
            "excerpt": excerpt,
            "excerpt_truncated": truncated,
        })
    _write_review_projection(target / "review-evidence.json", {
        "schema_version": "newrouge.mvg-review-evidence.v1",
        "note": "Bounded excerpts are for semantic review context; deterministic validation uses the complete immutable bundle.",
        "files": projected,
    })


def _prepare_review_workspace(run_dir: Path, workspace: Path, proposal: dict[str, Any]) -> None:
    """Create a bounded, hash-bound model projection without changing review inputs."""
    source = run_dir / "analysis-input"
    target = workspace / "analysis-input"
    target.mkdir(parents=True, exist_ok=True)
    excluded_files = {"task-master.json", "analysis-index.json"}
    excluded_dirs = {"references", "task-views"}
    for item in source.iterdir():
        if item.name in excluded_files or item.name in excluded_dirs:
            continue
        destination = target / item.name
        if item.is_dir():
            shutil.copytree(item, destination)
        elif item.is_file():
            shutil.copy2(item, destination)

    compact_fields = (
        "taskmaster_id", "id", "status", "priority", "semantic_refs",
        "requirement_ids", "capability_refs",
    )
    proposal_task_ids = _review_task_ids(proposal)
    proposal_task_labels = {str(value) for value in proposal_task_ids}
    for name in ("tasks_back.json", "tasks_gameplay.json"):
        payload = load_json(source / "task-views" / name, [])
        compact = [{key: row.get(key) for key in compact_fields if key in row}
                   for row in payload if isinstance(row, dict)
                   and (not proposal_task_ids or str(row.get("taskmaster_id")) in proposal_task_labels)]
        _write_review_projection(target / "task-views" / name, compact)

    master = load_json(source / "task-master.json", {})
    tasks = (master.get("master") or {}).get("tasks", []) if isinstance(master, dict) else []
    _write_review_projection(target / "task-master.json", {"master": {"tasks": [
        {key: row.get(key) for key in ("id", "status", "priority") if key in row}
        for row in tasks if isinstance(row, dict)
        and (not proposal_task_ids or str(row.get("id")) in proposal_task_labels)
    ]}})

    index = load_json(source / "analysis-index.json", {})
    _write_review_projection(target / "analysis-index.json", {
        "schema_version": index.get("schema_version"),
        "analysis_identity_sha256": index.get("analysis_identity_sha256"),
        "source_revision": index.get("source_revision"),
        "source_manifest_sha256": index.get("source_manifest_sha256"),
        "authority_input_count": len(index.get("authority_inputs") or {}),
        "prepared_file_count": len(index.get("files") or {}),
    })

    evidence: list[dict[str, Any]] = []
    references = source / "references"
    for rel in sorted(_review_reference_paths(proposal)):
        candidate = references / rel
        if not candidate.is_file():
            candidate = source / "sources" / rel
        if not candidate.is_file():
            evidence.append({"path": rel, "status": "not_in_prepared_bundle"})
            continue
        evidence.append({"path": rel, "source_path": str(candidate),
                         "sha256": file_sha(candidate)})

    # Keep the complete immutable prepared bundle untouched, while shrinking only
    # semantic-review excerpts until the projection fits the transport budget.
    # This makes a large-but-reviewable proposal recoverable without spending a
    # fresh independent-review attempt for each deterministic size failure.
    excerpt_limits = (MVG_REVIEW_EVIDENCE_EXCERPT_CHARS, 1200, 600, 240, 80, 0)
    last_size = 0
    for excerpt_limit in excerpt_limits:
        _write_review_evidence_projection(target, evidence, excerpt_limit)
        last_size = sum(path.stat().st_size for path in workspace.rglob("*") if path.is_file())
        if last_size < MVG_REVIEW_WORKSPACE_LIMIT:
            return
    raise ValueError(
        f"bounded MVG review workspace exceeds {MVG_REVIEW_WORKSPACE_LIMIT} bytes: {last_size}"
    )


def normalize_dotnet_selectors(root: Path, proposal: dict[str, Any]) -> int:
    """Repair deterministic selector syntax when the referenced file has one class."""
    changed = 0
    manifest = proposal.get("manifest_candidate") or {}
    for test in manifest.get("tests", []) if isinstance(manifest, dict) else []:
        if not isinstance(test, dict) or test.get("kind") != "dotnet":
            continue
        selector = str(test.get("selector") or "")
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]+", selector):
            continue
        paths = [str(test.get("path") or "")]
        paths.extend(str(value) for value in test.get("test_refs", []) if str(value).strip())
        classes: set[str] = set()
        for path in paths:
            try:
                target = repo_path(root, path)
            except ValueError:
                continue
            if target.is_file():
                classes.update(re.findall(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)\b", target.read_text(encoding="utf-8")))
        # dotnet test accepts filter expressions, but the MVG manifest deliberately
        # stores only the declared class name.  Reduce a FullyQualifiedName~Class
        # expression (and the older wildcard form) only when the referenced
        # evidence makes the result deterministic.
        tail = re.search(r"([A-Za-z_][A-Za-z0-9_]*)$", selector)
        tail_name = tail.group(1) if tail else ""
        matching = []
        if tail_name in classes and ("~" in selector or selector != tail_name):
            matching = [tail_name]
        elif "*" in selector:
            pattern = selector.replace("*", "")
            matching = sorted(name for name in classes if name.startswith(pattern))
        elif len(classes) == 1 and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]+", selector):
            matching = sorted(classes)
        if len(matching) != 1:
            continue
        test["selector"] = matching[0]
        changed += 1
    return changed


def normalize_proposal_format(proposal: dict[str, Any]) -> int:
    """Apply only lossless formatting repairs before semantic validation.

    This never invents IDs or routes. It normalizes legacy scalar encodings and
    derives the required-flow ordering from the proposal's own flow list.
    """
    changed = 0
    manifest = proposal.get("manifest_candidate")
    if not isinstance(manifest, dict):
        return changed
    flows = manifest.get("flows")
    if not isinstance(flows, list):
        return changed
    for flow in flows:
        if not isinstance(flow, dict):
            continue
        task_ids = flow.get("task_ids")
        if isinstance(task_ids, list):
            converted = []
            for value in task_ids:
                if isinstance(value, str) and value.isdigit():
                    converted.append(int(value))
                    changed += 1
                else:
                    converted.append(value)
            flow["task_ids"] = converted
        test_ids = flow.get("test_ids")
        if isinstance(test_ids, str) and test_ids.strip():
            flow["test_ids"] = [test_ids.strip()]
            changed += 1
        for handoff in flow.get("handoffs", []) if isinstance(flow.get("handoffs"), list) else []:
            if not isinstance(handoff, dict):
                continue
            for key in ("producer_task", "consumer_task", "owner_task"):
                value = handoff.get(key)
                if isinstance(value, str) and value.isdigit():
                    handoff[key] = int(value)
                    changed += 1
    for test in manifest.get("tests", []) if isinstance(manifest.get("tests"), list) else []:
        if not isinstance(test, dict):
            continue
        value = test.get("min_tests")
        if isinstance(value, str) and value.isdigit():
            test["min_tests"] = int(value)
            changed += 1
    coverage = manifest.get("coverage")
    if isinstance(coverage, dict):
        blockers = coverage.get("blocking_task_ids")
        if isinstance(blockers, list):
            converted_blockers = []
            for value in blockers:
                if isinstance(value, str) and value.isdigit():
                    converted_blockers.append(int(value))
                    changed += 1
                else:
                    converted_blockers.append(value)
            coverage["blocking_task_ids"] = converted_blockers
        required = [str(flow.get("id")) for flow in flows
                    if isinstance(flow, dict) and str(flow.get("id") or "").strip()]
        if coverage.get("required_flow_ids") != required:
            coverage["required_flow_ids"] = required
            changed += 1
    return changed


def _list_field(row: dict[str, Any], key: str) -> list[Any]:
    """Return a task-view list field without treating explicit null as iterable."""
    value = row.get(key)
    return value if isinstance(value, list) else []


def build_coverage_skeleton(semantics: dict[str, Any], task_views: list[dict[str, Any]],
                            allowed_requirement_ids: set[str] | None = None) -> list[dict[str, Any]]:
    """Create non-droppable Requirement rows before semantic flow planning."""
    task_by_requirement: dict[str, tuple[int | None, str | None]] = {}
    for row in task_views:
        try:
            task_id = int(row.get("taskmaster_id"))
        except (TypeError, ValueError):
            continue
        capability_refs = [str(value) for value in _list_field(row, "capability_refs") if str(value).strip()]
        requirement_values = (row.get("semantic_refs")
                              if isinstance(row.get("semantic_refs"), list)
                              else _list_field(row, "requirement_ids"))
        for requirement_id in requirement_values:
            task_by_requirement.setdefault(str(requirement_id), (task_id, capability_refs[0] if capability_refs else None))
    result = []
    for requirement in semantics.get("requirements", []):
        if (not isinstance(requirement, dict)
                or requirement.get("delivery_relevant", True) is not True
                or requirement.get("status", "active") != "active"):
            continue
        requirement_id = str(requirement.get("requirement_id") or "").strip()
        if allowed_requirement_ids is not None and requirement_id not in allowed_requirement_ids:
            continue
        task_id, capability_ref = task_by_requirement.get(requirement_id, (None, None))
        result.append({"requirement_id": requirement_id, "disposition": "flow",
            "flow_id": None, "capability_ref": capability_ref, "task_id": task_id,
            "rationale": "Pending LLM journey assignment; Requirement retained in coverage ledger."})
    return result


def build_entrypoint_skeleton(task_ids: list[int]) -> list[dict[str, Any]]:
    """Reserve an empty section: task identity cannot establish a runtime API.

    Entrypoints are populated after Capability journeys identify real system
    boundaries. Evidence-only task owners must never acquire invented APIs.
    """
    return []


def correction_prompt(errors: list[str]) -> str:
    return ("Return a JSON patch only, not a replacement proposal. Allowed arrays are: "
            "coverage_additions, flow_updates, handoff_updates, entrypoint_additions. "
            "Do not remove or rewrite valid existing data. Preserve all IDs and Requirement rows. "
            "For selector errors, update the existing manifest test object in-place using the exact C# class "
            "declared by that test's path; the selector must be a class name and never contain *, a method "
            "filter, or a wildcard. Fix only these validator errors:\n- " + "\n- ".join(str(value) for value in errors))


RESTRICTED_PATCH_KEYS = {"coverage_additions", "flow_updates", "handoff_updates", "entrypoint_additions"}
PATCH_IDENTITY_KEYS = {"schema_version", "analysis_identity_sha256"}


def is_restricted_patch(value: dict[str, Any]) -> bool:
    return (bool(value)
            and set(value).issubset(RESTRICTED_PATCH_KEYS | PATCH_IDENTITY_KEYS)
            and any(key in value for key in RESTRICTED_PATCH_KEYS))


def validate_restricted_patch_identity(value: dict[str, Any], state: dict[str, Any]) -> list[str]:
    errors = []
    if value.get("schema_version") not in (None, PROPOSAL_SCHEMA):
        errors.append("restricted_patch_schema_mismatch")
    if value.get("analysis_identity_sha256") not in (None, state.get("analysis_identity_sha256")):
        errors.append("restricted_patch_analysis_identity_mismatch")
    return errors


def apply_restricted_patch(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """Merge only additive/update patch fields while preserving the valid proposal."""
    result = json.loads(json.dumps(base))
    coverage = result.setdefault("coverage_table", [])
    existing_requirements = {str(row.get("requirement_id")) for row in coverage if isinstance(row, dict)}
    coverage.extend(row for row in (patch.get("coverage_additions") or [])
                    if isinstance(row, dict) and str(row.get("requirement_id")) not in existing_requirements)
    manifest = result.setdefault("manifest_candidate", {})
    flows = {str(row.get("id")): row for row in manifest.get("flows", []) if isinstance(row, dict)}
    for update in (patch.get("flow_updates") or []):
        row = flows.get(str(update.get("id")))
        if row:
            row.update({key: value for key, value in update.items() if key != "id"})
    handoffs = {(str(flow.get("id")), str(handoff.get("contract_ref"))): handoff
                for flow in manifest.get("flows", []) if isinstance(flow, dict)
                for handoff in flow.get("handoffs", []) if isinstance(handoff, dict)}
    for update in (patch.get("handoff_updates") or []):
        key = (str(update.get("flow_id")), str(update.get("contract_ref")))
        if key in handoffs:
            handoffs[key].update({key: value for key, value in update.items() if key not in {"flow_id"}})
    existing = {str(row.get("owner_task")) for row in result.setdefault("entrypoints", []) if isinstance(row, dict)}
    result["entrypoints"].extend(row for row in (patch.get("entrypoint_additions") or [])
                                  if str(row.get("owner_task")) not in existing)
    return result


SEGMENT_SCHEMA = "newrouge.mvg-planning-segment.v1"

def segment_output_schema(*, section: str, identity: str, scope_id: str,
                          available_source_paths: list[str] | None = None,
                          available_contract_paths: list[str] | None = None,
                          allowed_flow_ids: list[str] | None = None,
                          allowed_test_ids: list[str] | None = None,
                          allowed_test_paths: list[str] | None = None,
                          available_reference_paths: list[str] | None = None) -> dict[str, Any]:
    """Build the CLI-enforced envelope for one routed segment request."""
    payload_key = {
        "flows": "flows",
        "coverage": "coverage_table",
        "entrypoints": "entrypoints",
        "tests": "tests",
    }.get(section)
    if payload_key is None:
        raise ValueError(f"unsupported MVG segment section: {section}")

    def nullable(schema: dict[str, Any]) -> dict[str, Any]:
        return {"anyOf": [schema, {"type": "null"}]}

    def array(item: dict[str, Any]) -> dict[str, Any]:
        return {"type": "array", "items": item}

    def strict_object(properties: dict[str, Any]) -> dict[str, Any]:
        return {"type": "object", "properties": properties,
                "required": list(properties), "additionalProperties": False}

    nonempty_string = {"type": "string", "minLength": 1}

    def bounded_path(paths: list[str] | None) -> dict[str, Any]:
        values = sorted({str(path).replace("\\", "/") for path in (paths or []) if str(path).strip()})
        return {"type": "string", "enum": values} if values else nonempty_string

    source_path = bounded_path(available_source_paths)
    contract_path = bounded_path(available_contract_paths)
    flow_id = bounded_path(allowed_flow_ids)
    test_id = bounded_path(allowed_test_ids)
    reference_path = nonempty_string
    if available_reference_paths is not None:
        paths = sorted({str(path).replace("\\", "/") for path in available_reference_paths
                        if str(path).strip()})
        # Anchors are valid only after an exact prepared repository path.
        reference_path = {"type": "string", "pattern": (
            "^(?:" + "|".join(re.escape(path) for path in paths) + ")(?:#[^\\r\\n]+)?$"
        )} if paths else {"type": "string", "const": ""}
    if section == "tests" and allowed_test_ids is None:
        test_id = {**nonempty_string, "pattern": "^" + re.escape(scope_id + "-")}
    if section == "flows" and allowed_flow_ids is None:
        flow_id = {**nonempty_string, "pattern": "^" + re.escape(scope_id + "-")}

    def bounded_test_path(prefix: str, suffix: str) -> dict[str, Any]:
        values = sorted({str(path).replace("\\", "/") for path in (allowed_test_paths or [])
                         if str(path).replace("\\", "/").startswith(prefix)
                         and str(path).replace("\\", "/").endswith(suffix)})
        if values:
            return {"type": "string", "enum": values}
        return {"type": "string", "pattern": rf"^{re.escape(prefix)}.+{re.escape(suffix)}$"}
    integer = {"type": "integer"}
    handoff = strict_object({
        "producer_task": integer, "consumer_task": integer, "owner_task": integer,
        "contract_ref": contract_path, "contract_refs": nullable(array(nonempty_string)),
        "behavior": nonempty_string, "test_ids": {"type": "array", "items": test_id, "minItems": 1},
        "from": nullable(nonempty_string), "to": nullable(nonempty_string),
    })
    flow = strict_object({
        "id": flow_id, "outcome": nonempty_string,
        "requirement_ids": {"type": "array", "items": nonempty_string, "minItems": 1},
        "capability_refs": {"type": "array", "items": nonempty_string, "minItems": 1},
        "task_ids": {"type": "array", "items": integer, "minItems": 1},
        "source_paths": {"type": "array", "items": source_path, "minItems": 1},
        "handoffs": {"type": "array", "items": handoff, "minItems": 1},
        "test_ids": {"type": "array", "items": test_id, "minItems": 1},
    })
    coverage = strict_object({
        "requirement_id": nonempty_string, "flow_id": nullable(flow_id),
        "capability_ref": nullable(nonempty_string), "task_id": nullable(integer),
        "disposition": {"type": "string", "enum": ["flow", "other_verification", "deferred"]},
        "rationale": nonempty_string,
        "sink_id": nullable(nonempty_string), "verification_ref": nullable(reference_path),
        "authority_ref": nullable(reference_path),
        "authority_review": nullable(strict_object({
            "status": nonempty_string, "rationale": nonempty_string,
        })),
    })
    flexible_text = {"anyOf": [nonempty_string, array(nonempty_string), {"type": "null"}]}
    entrypoint = strict_object({
        "status": {"type": "string", "enum": ["planned", "existing_verified"]},
        "owner_task": integer, "path": nonempty_string, "symbol": nonempty_string,
        "inputs": flexible_text, "state": flexible_text, "assertions": flexible_text,
        "implementation_acceptance": flexible_text,
    })
    test_common = {
        "id": test_id, "flow_id": flow_id, "test_refs": array(nonempty_string),
        "state": {"type": "string", "enum": ["planned", "implemented"]},
        "selector": nonempty_string, "min_tests": {"type": "integer", "minimum": 1},
    }
    test = {"anyOf": [
        strict_object({**test_common, "kind": {"type": "string", "const": "dotnet"},
                       "path": bounded_test_path("Game.Core.Tests/", ".cs"),
                       "evidence_level": {"type": "string", "const": "domain-integration"}}),
        strict_object({**test_common, "kind": {"type": "string", "const": "gdunit"},
                       "path": bounded_test_path("Tests.Godot/tests/", ".gd"),
                       "evidence_level": {"type": "string", "enum": ["scene-method", "engine-input"]}}),
    ]}
    item_schema = {"flows": flow, "coverage_table": coverage,
                   "entrypoints": entrypoint, "tests": test}[payload_key]
    payload_schema = array(item_schema)
    if ((section == "tests" and allowed_test_ids == [])
            or (section == "flows" and allowed_test_ids == [])):
        payload_schema["maxItems"] = 0
    return {
        "type": "object",
        "required": ["schema_version", "analysis_identity_sha256", "section", "scope_id", payload_key],
        "properties": {
            "schema_version": {"type": "string", "const": SEGMENT_SCHEMA},
            "analysis_identity_sha256": {"type": "string", "const": identity},
            "section": {"type": "string", "const": section},
            "scope_id": {"type": "string", "const": scope_id},
            payload_key: payload_schema,
        },
        "additionalProperties": False,
    }


def _segment_allowed_test_ids(request: dict[str, Any],
                              planning_scope: dict[str, Any] | None,
                              section: str) -> list[str] | None:
    """Return the exact frozen test domain for one routed segment."""
    if planning_scope is None or section not in ("flows", "tests"):
        return None
    return sorted({str(value) for value in request.get("test_ids", [])
                   if str(value).strip()})


def segment_prompt(*, section: str, identity: str, requirements: list[str], task_ids: list[int],
                   flow_context: list[dict[str, Any]] | None = None,
                   scope_id: str = "", flow_id_prefix: str = "", test_id_prefix: str = "",
                   allow_exact_flow_id: bool = False,
                   allow_exact_test_id: bool = False) -> str:
    """Build a bounded LLM request for one MVG planning section.

    The model returns only the requested section. Deterministic code owns the
    final proposal envelope and the non-droppable skeleton accounting.
    """
    scope = json.dumps({"requirement_ids": requirements, "task_ids": task_ids,
                        "flow_ids": [str(row.get("id")) for row in (flow_context or [])]}, ensure_ascii=False)
    scope_label = scope_id or "unscoped"
    flow_rule = ("Copy the exact incumbent flow id supplied in this frozen request; do not add a suffix."
                 if allow_exact_flow_id else
                 (f"Every new flow id must start with {flow_id_prefix!r}." if flow_id_prefix
                  else "Use stable lowercase kebab-case flow ids."))
    test_rule = ("Copy the exact incumbent test ids supplied in this frozen request; do not add a prefix or suffix."
                 if allow_exact_test_id else
                 (f"Every new test id must start with {test_id_prefix!r}." if test_id_prefix
                  else "Use stable lowercase kebab-case test ids."))
    return f"""You are producing one bounded section of an MVG integration plan.
Use only the prepared evidence needed for this section and return JSON only, with no markdown, shell commands, or commentary.
The prepared capabilities.v1.json is the exclusive Capability SSoT. Capability IDs and Requirement membership must come from that file only; other evidence may explain behavior but cannot create or reassign a Capability.
schema_version must be {SEGMENT_SCHEMA!r}.
analysis_identity_sha256 must be exactly {identity!r}.
section must be {section!r}.
scope_id must be {scope_label!r}; this request is independent from every other scope.
scope is {scope}.
The section is one patch to a deterministic proposal skeleton. Do not emit the full proposal envelope.
Return only fields needed for this section:
- flows: for section=flows, one or two complete player-journey flow objects for this scope only. Prefer one coherent journey when the evidence supports it; split only when the slice contains distinct observable outcomes. Each flow must include id, outcome, requirement_ids, capability_refs, task_ids, source_paths, handoffs, and test_ids. {flow_rule}
- coverage_table: for section=coverage, rows for the supplied requirements only;
- entrypoints: for section=entrypoints, planned/existing entrypoint rows for the real runtime boundaries in the supplied Capability flow context, with supplied task IDs used only to verify ownership;
- tests: for section=tests, test objects only. Every supplied flow must receive at least one test id, and each test id must be used by exactly one supplied flow. {test_rule}
For coverage rows with disposition=flow, assign flow_id to an actual flow id from the supplied flow context; other_verification and deferred rows must leave flow_id null. The only valid disposition values are exactly flow, other_verification, or deferred; every row needs a non-empty rationale string.
Coverage routing is strict: use only the supplied requirement_ids/task_ids/capability refs. A flow row must have verification_ref, authority_ref, and authority_review set to null; an other_verification row must have flow_id/authority_ref/authority_review null and a sink_id from that Requirement's non_task_sinks; a Requirement with an empty non_task_sinks list cannot use other_verification and must be routed to a flow or a reviewed deferred row; a deferred row must have flow_id/verification_ref null and a reviewed authority_ref/authority_review.
For entrypoints, status is exactly planned or existing_verified; use planned unless the prepared evidence proves a real existing entrypoint. Never use gap, existing, or unlisted. Planned rows require non-empty path, symbol, inputs, state, assertions, and implementation_acceptance.
Task IDs are evidence owners, not runtime API obligations. Never create an entrypoint merely because a Task appears in task_ids, coverage or a legacy handoff. A test or governance task supplies verification/review evidence, not a runtime API. Derive runtime boundaries from the selected Capability journey and prepared implementation/Acceptance evidence; return no row for evidence-only owners. Data-only contracts are not executable entrypoints. Multiple real boundaries may share an owner, and not every owner needs an entrypoint. If the supplied flows have no runtime boundary, entrypoints may be empty.
For tests, kind is exactly dotnet or gdunit, state is exactly planned or implemented, path is a repository-relative Game.Core.Tests/*.cs or Tests.Godot/tests/*.gd path, selector is non-empty, and evidence_level is domain-integration for dotnet or scene-method/engine-input for gdunit. Do not use acceptance, unit, integration, direct, or null for these fields.
For section=tests, this request is for exactly one flow: the sole value in flow_scope_ids. Never emit a test for another flow, even if its Task or test file appears in the evidence context. In a frozen request, use only the exact test IDs listed for this flow; never copy a test ID from another flow or invent a replacement. If the flow has no prepared test evidence, return an empty tests array and let deterministic coverage report the missing evidence.
For flows, every handoff must be an object with integer producer_task, consumer_task, and owner_task, a real non-empty contract_ref from available_contract_paths, non-empty behavior, and a non-empty test_ids array.
Do not use task IDs, flow IDs, or test IDs from another scope. For section=flows, every new flow id must start with the requested scope_id plus '-', while a frozen request must copy the exact incumbent flow ID. For coverage/tests, route only to the supplied flow context. Every flow task and every handoff role must be in this request's task_ids.
The required bounded context is included inline in this prompt. Do not call shell/tools or scan files.
For section=tests, the inline context includes the prepared test refs; do not load full task views.
For entrypoints and tests, use only the specific prepared references named by that context. Do not scan unrelated files.
Do not invent repository paths, contracts, tasks, or capabilities. Use prepared evidence only.
For source_paths and contract_ref, use only paths listed in the inline available_*_paths arrays. If a required real object is not listed, report a gap instead of inventing a path.
"""


def _prepared_reference(prepared: Path, value: str) -> Path | None:
    try:
        normalized = str(value or "").replace("\\", "/")
        if not normalized or normalized.startswith("/") or ":" in normalized or ".." in Path(normalized).parts:
            return None
        for prefix in ("references", "sources"):
            candidate = prepared / prefix / normalized
            if candidate.is_file():
                return candidate
    except (OSError, ValueError):
        return None
    return None


def validate_segment_references(value: dict[str, Any], *, section: str, prepared: Path,
                                available_source_paths: list[str],
                                available_contract_paths: list[str],
                                available_test_paths: list[str] | None = None) -> list[str]:
    """Reject references that are not present in the immutable prepared bundle."""
    errors: list[str] = []
    source_paths = {str(path).replace("\\", "/") for path in available_source_paths}
    contract_paths = {str(path).replace("\\", "/") for path in available_contract_paths}
    test_paths = {str(path).replace("\\", "/") for path in (available_test_paths or [])}
    rows = value.get({"flows": "flows", "coverage": "coverage_table",
                      "entrypoints": "entrypoints", "tests": "tests"}.get(section, ""), [])
    if not isinstance(rows, list):
        return errors
    for row in rows:
        if not isinstance(row, dict):
            continue
        if section == "flows":
            for source in row.get("source_paths", []):
                normalized = str(source).replace("\\", "/")
                if normalized not in source_paths or _prepared_reference(prepared, normalized) is None:
                    errors.append(f"segment_flow_source_unprepared:{normalized}")
            for handoff in row.get("handoffs", []):
                if not isinstance(handoff, dict):
                    continue
                contract = str(handoff.get("contract_ref") or "").replace("\\", "/")
                if contract not in contract_paths or _prepared_reference(prepared, contract) is None:
                    errors.append("segment_handoff_contract_unprepared")
        elif section == "entrypoints" and row.get("status") == "existing_verified":
            path = str(row.get("path") or "").replace("\\", "/")
            target = _prepared_reference(prepared, path)
            if target is None:
                errors.append("segment_entrypoint_existing_unprepared")
                continue
            symbol = str(row.get("symbol") or "").strip()
            try:
                text = target.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                text = ""
            if not symbol or symbol.split(".")[-1] not in text:
                errors.append("segment_entrypoint_existing_symbol_missing")
        elif section == "tests":
            path = str(row.get("path") or "").replace("\\", "/")
            if row.get("state") == "implemented" and (path not in test_paths
                    or _prepared_reference(prepared, path) is None):
                errors.append("segment_test_implemented_unprepared")
        elif section == "coverage":
            if row.get("disposition") == "other_verification":
                verification = str(row.get("verification_ref") or "").split("#", 1)[0].replace("\\", "/")
                if not verification or _prepared_reference(prepared, verification) is None:
                    errors.append("segment_coverage_verification_unprepared")
            elif row.get("disposition") == "deferred":
                authority = str(row.get("authority_ref") or "").split("#", 1)[0].replace("\\", "/")
                if not authority or _prepared_reference(prepared, authority) is None:
                    errors.append(
                        f"segment_coverage_authority_unprepared:{row.get('requirement_id', '')}"
                    )
    return errors


def validate_segment_routing(value: dict[str, Any], *, section: str,
                             request: dict[str, Any],
                             flow_context: list[dict[str, Any]] | None = None) -> list[str]:
    """Reject valid JSON that escaped the requested segment route.

    JSON Schema can enforce shape and value domains, but it cannot know the
    per-request Requirement/Task/Flow partition.  This validator is the local
    routing gate used both after a fresh CLI response and before reusing a
    previous segment.
    """
    errors: list[str] = []
    rows = value.get({"flows": "flows", "coverage": "coverage_table",
                      "entrypoints": "entrypoints", "tests": "tests"}.get(section, ""), [])
    if not isinstance(rows, list):
        return errors
    allowed_requirements = {str(item) for item in request.get("requirement_ids", [])}
    allowed_tasks = {int(item) for item in request.get("task_ids", []) if type(item) is int}
    allowed_capabilities = {
        str(row.get("capability_id"))
        for row in request.get("capabilities", [])
        if isinstance(row, dict) and str(row.get("capability_id") or "").strip()
    }
    for requirement in request.get("requirements", []):
        if isinstance(requirement, dict):
            allowed_capabilities.update(
                str(item) for item in requirement.get("capability_refs", [])
                if str(item).strip()
            )
    scope_id = str(request.get("scope_id") or "")
    flow_scope_ids = {str(item) for item in request.get("flow_scope_ids", [])}
    known_flow_ids = {str(row.get("id")) for row in (flow_context or [])
                      if isinstance(row, dict) and str(row.get("id") or "").strip()}

    for row in rows:
        if not isinstance(row, dict):
            continue
        if section == "flows":
            flow_id = str(row.get("id") or "")
            # Cumulative manifests freeze their existing flow IDs.  A frozen
            # request must return the exact incumbent ID; accepting a suffixed
            # variant would create a second route that cannot be merged safely.
            allow_exact_flow_id = bool(request.get("allow_exact_flow_id"))
            if scope_id and not (
                    (allow_exact_flow_id and flow_id == scope_id)
                    or (not allow_exact_flow_id and flow_id.startswith(scope_id + "-"))):
                errors.append("segment_flow_id_outside_scope")
            requirement_ids = {str(item) for item in row.get("requirement_ids", [])}
            if not requirement_ids or not requirement_ids <= allowed_requirements:
                errors.append("segment_flow_requirements_outside_scope")
            capability_refs = {str(item) for item in row.get("capability_refs", [])}
            if not capability_refs or (allowed_capabilities and not capability_refs <= allowed_capabilities):
                errors.append("segment_flow_capabilities_outside_scope")
            task_values = row.get("task_ids", [])
            if (not isinstance(task_values, list)
                    or any(type(item) is not int or item not in allowed_tasks for item in task_values)):
                errors.append("segment_flow_tasks_outside_scope")
            allowed_test_ids = {str(value) for value in request.get("test_ids", []) if str(value).strip()}
            if allowed_test_ids and any(str(value) not in allowed_test_ids
                                        for value in (row.get("test_ids") or [])):
                errors.append("segment_flow_tests_outside_scope")
            for handoff in row.get("handoffs", []) if isinstance(row.get("handoffs"), list) else []:
                if not isinstance(handoff, dict):
                    continue
                if any(type(handoff.get(key)) is not int
                       or handoff.get(key) not in set(task_values)
                       for key in ("producer_task", "consumer_task", "owner_task")):
                    errors.append("segment_handoff_tasks_outside_flow")
                allowed_test_ids = {str(value) for value in request.get("test_ids", [])}
                if allowed_test_ids and any(str(value) not in allowed_test_ids
                                            for value in (handoff.get("test_ids") or [])):
                    errors.append("segment_handoff_tests_outside_scope")
        elif section == "coverage":
            rid = str(row.get("requirement_id") or "")
            if rid not in allowed_requirements:
                errors.append("segment_coverage_requirement_outside_scope")
            task_id = row.get("task_id")
            if task_id is not None and (type(task_id) is not int or task_id not in allowed_tasks):
                errors.append("segment_coverage_task_outside_scope")
            capability_ref = row.get("capability_ref")
            if capability_ref is not None and str(capability_ref) not in allowed_capabilities:
                errors.append("segment_coverage_capability_outside_scope")
            disposition = row.get("disposition")
            flow_id = row.get("flow_id")
            verification_ref = row.get("verification_ref")
            authority_ref = row.get("authority_ref")
            if disposition == "flow":
                flow_row = next((flow for flow in (flow_context or [])
                                 if isinstance(flow, dict)
                                 and str(flow.get("id") or "") == str(flow_id or "")), None)
                if not isinstance(flow_id, str) or not flow_id.strip() or flow_id not in known_flow_ids:
                    errors.append("segment_coverage_flow_route_invalid")
                elif (str(row.get("requirement_id") or "") not in {
                        str(value) for value in (flow_row or {}).get("requirement_ids", [])
                    } or str(row.get("capability_ref") or "") not in {
                        str(value) for value in (flow_row or {}).get("capability_refs", [])
                    } or (type(row.get("task_id")) is not int
                          or row.get("task_id") not in (flow_row or {}).get("task_ids", []))):
                    # A valid flow ID is not sufficient: the routed
                    # Requirement, Capability and owner Task must all belong
                    # to that exact flow before the segment can be merged.
                    errors.append("segment_coverage_flow_membership_invalid")
                if verification_ref not in (None, "") or authority_ref not in (None, ""):
                    errors.append("segment_coverage_flow_file_refs_forbidden")
            elif disposition == "other_verification":
                if flow_id not in (None, ""):
                    errors.append("segment_coverage_other_verification_flow_forbidden")
                if not isinstance(verification_ref, str) or not verification_ref.strip():
                    errors.append("segment_coverage_verification_ref_missing")
                if authority_ref not in (None, ""):
                    errors.append("segment_coverage_other_verification_authority_forbidden")
                requirement_row = next((item for item in request.get("requirements", [])
                                        if isinstance(item, dict)
                                        and str(item.get("requirement_id") or "") == rid), None)
                allowed_sinks = set()
                for item in (requirement_row or {}).get("non_task_sinks", []):
                    if isinstance(item, dict):
                        sink = item.get("sink_id") or item.get("id")
                    else:
                        sink = item
                    if str(sink or "").strip():
                        allowed_sinks.add(str(sink))
                if not allowed_sinks:
                    errors.append("segment_coverage_other_verification_sink_unavailable")
                elif str(row.get("sink_id") or "") not in allowed_sinks:
                    errors.append("segment_coverage_other_verification_sink_invalid")
            elif disposition == "deferred":
                if flow_id not in (None, ""):
                    errors.append("segment_coverage_deferred_flow_forbidden")
                if not isinstance(authority_ref, str) or not authority_ref.strip():
                    errors.append("segment_coverage_authority_ref_missing")
                if verification_ref not in (None, ""):
                    errors.append("segment_coverage_deferred_verification_forbidden")
        elif section == "entrypoints":
            owner_task = row.get("owner_task")
            if type(owner_task) is not int or owner_task not in allowed_tasks:
                errors.append("segment_entrypoint_owner_outside_scope")
        elif section == "tests":
            flow_id = str(row.get("flow_id") or "")
            exact_flow_ids = set(flow_scope_ids) if request.get("allow_exact_flow_id") else set()
            if flow_scope_ids and not (
                    (flow_id in exact_flow_ids if request.get("allow_exact_flow_id") else
                     any(flow_id.startswith(scope + "-") for scope in flow_scope_ids))):
                errors.append("segment_test_flow_outside_scope")
            if known_flow_ids and flow_id not in known_flow_ids:
                errors.append("segment_test_flow_unknown")
            allowed_test_paths = {str(value).replace("\\", "/")
                                  for value in request.get("test_paths", []) if str(value).strip()}
            if allowed_test_paths and str(row.get("path") or "").replace("\\", "/") not in allowed_test_paths:
                errors.append("segment_test_path_outside_scope")
            test_id = str(row.get("id") or "")
            exact_test_ids = {str(value) for value in request.get("test_ids", [])}
            if scope_id and not (
                    (request.get("allow_exact_test_id") and test_id in exact_test_ids)
                    or (not request.get("allow_exact_test_id") and test_id.startswith(scope_id + "-"))):
                errors.append("segment_test_id_outside_scope")
    return sorted(set(errors))


def validate_segment_identity(value: dict[str, Any], *, section: str, identity: str,
                             scope_id: str | None = None) -> list[str]:
    errors: list[str] = []
    payload_key = {"flows": "flows", "coverage": "coverage_table",
                   "entrypoints": "entrypoints", "tests": "tests"}.get(section)
    if payload_key is None:
        errors.append("segment_section_unknown")
    if value.get("schema_version") != SEGMENT_SCHEMA:
        errors.append("segment_schema_mismatch")
    if value.get("analysis_identity_sha256") != identity:
        errors.append("segment_analysis_identity_mismatch")
    if value.get("section") != section:
        errors.append("segment_section_mismatch")
    if scope_id is not None and value.get("scope_id") != scope_id:
        errors.append("segment_scope_mismatch")
    if payload_key is not None and not isinstance(value.get(payload_key), list):
        errors.append(f"segment_{payload_key}_missing")
    rows = value.get(payload_key) if payload_key is not None else []
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                errors.append(f"segment_{section}_item_invalid")
                continue
            if section == "coverage":
                disposition = row.get("disposition")
                if disposition not in {"flow", "other_verification", "deferred"}:
                    errors.append("segment_disposition_invalid")
                if not isinstance(row.get("rationale"), str) or not row.get("rationale", "").strip():
                    errors.append("segment_coverage_rationale_missing")
            elif section == "flows":
                handoffs = row.get("handoffs")
                if not isinstance(handoffs, list) or not handoffs:
                    errors.append("segment_flow_handoffs_missing")
                for handoff in handoffs if isinstance(handoffs, list) else []:
                    if not isinstance(handoff, dict):
                        errors.append("segment_flow_handoff_invalid")
                        continue
                    for field in ("producer_task", "consumer_task", "owner_task"):
                        if type(handoff.get(field)) is not int:
                            errors.append(f"segment_handoff_{field}_invalid")
                    if not isinstance(handoff.get("contract_ref"), str) or not handoff.get("contract_ref", "").strip():
                        errors.append("segment_handoff_contract_ref_missing")
                    if not isinstance(handoff.get("behavior"), str) or not handoff.get("behavior", "").strip():
                        errors.append("segment_handoff_behavior_missing")
                    if not isinstance(handoff.get("test_ids"), list) or not handoff.get("test_ids"):
                        errors.append("segment_handoff_test_ids_missing")
            elif section == "entrypoints":
                status = row.get("status")
                if status not in {"planned", "existing_verified"}:
                    errors.append("segment_entrypoint_status_invalid")
                if status == "planned":
                    for field in ("inputs", "state", "assertions", "implementation_acceptance"):
                        if row.get(field) in (None, "", []):
                            errors.append(f"segment_entrypoint_{field}_missing")
            elif section == "tests":
                kind = row.get("kind")
                state = row.get("state")
                evidence = row.get("evidence_level")
                expected = {"dotnet": {"domain-integration"},
                            "gdunit": {"scene-method", "engine-input"}}
                if kind not in expected:
                    errors.append("segment_test_kind_invalid")
                elif evidence not in expected[kind]:
                    errors.append("segment_test_evidence_invalid")
                if state not in {"planned", "implemented"}:
                    errors.append("segment_test_state_invalid")
                if not isinstance(row.get("path"), str) or not row.get("path", "").strip():
                    errors.append("segment_test_path_missing")
                if not isinstance(row.get("selector"), str) or not row.get("selector", "").strip():
                    errors.append("segment_test_selector_missing")
    return errors


def bind_manifest_test_ids(proposal: dict[str, Any], *,
                           preserve_flow_ids: set[str] | None = None) -> None:
    """Bind generated test routes without weakening cumulative baseline flows.

    A cumulative proposal may add newly scoped flows while its test segment only
    routes those new IDs.  Existing baseline flows are intentionally retained
    when they have no route in this round; newly added flows must receive an
    explicit route and otherwise remain invalid for deterministic retry.
    """
    manifest = proposal.get("manifest_candidate")
    if not isinstance(manifest, dict):
        return
    tests = proposal.get("tests")
    if not isinstance(tests, list):
        return
    by_flow: dict[str, list[str]] = {}
    for row in tests:
        if not isinstance(row, dict):
            continue
        test_id = str(row.get("id") or "").strip()
        flow_id = str(row.get("flow_id") or "").strip()
        if test_id and flow_id:
            by_flow.setdefault(flow_id, []).append(test_id)
    preserved = {str(value) for value in (preserve_flow_ids or set())}
    for flow in manifest.get("flows", []):
        if not isinstance(flow, dict):
            continue
        flow_id = str(flow.get("id") or "")
        routed = list(dict.fromkeys(by_flow.get(flow_id, [])))
        if not routed and flow_id in preserved:
            # No fresh test route is an allowed no-op for an existing
            # cumulative flow.  Keep its handoff bindings byte-for-byte.
            continue
        test_ids = routed
        flow["test_ids"] = test_ids
        for handoff in flow.get("handoffs", []):
            if isinstance(handoff, dict):
                handoff["test_ids"] = list(test_ids)


def load_reusable_segment(run_dir: Path, *, current_attempt: int, index: int,
                          section: str, identity: str, scope_id: str,
                          prepared: Path | None = None,
                          available_source_paths: list[str] | None = None,
                          available_contract_paths: list[str] | None = None,
                          available_test_paths: list[str] | None = None,
                          routing_request: dict[str, Any] | None = None,
                          flow_context: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """Load only a prior segment whose route and payload envelope are valid."""
    payload_key = {"flows": "flows", "coverage": "coverage_table",
                   "entrypoints": "entrypoints", "tests": "tests"}.get(section)
    if payload_key is None:
        return None
    for prior_attempt in range(current_attempt - 1, 0, -1):
        path = (run_dir / "model-workspace" / f"attempt-{prior_attempt}" / "llm-sandbox"
                / f"attempt-{prior_attempt}" / f"segments-{index:03d}-{section}"
                / f"{index:03d}-{section}.json")
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if validate_segment_identity(payload, section=section, identity=identity,
                                     scope_id=scope_id):
            continue
        if routing_request is not None and validate_segment_routing(
                payload, section=section, request=routing_request,
                flow_context=flow_context):
            continue
        if prepared is not None and validate_segment_references(
                payload,
                section=section,
                prepared=prepared,
                available_source_paths=available_source_paths or [],
                available_contract_paths=available_contract_paths or [],
                available_test_paths=available_test_paths or [],
        ):
            continue
        if not isinstance(payload.get(payload_key), list):
            continue
        return payload
    return None


def _active_delivery_requirements(semantics: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in semantics.get("requirements", [])
            if isinstance(row, dict)
            and row.get("delivery_relevant", True) is True
            and row.get("status", "active") == "active"
            and str(row.get("requirement_id") or "").strip()]


def _manifest_planning_scope(manifest: dict[str, Any] | None,
                             task_views: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    """Return the immutable planning boundary declared by an existing manifest.

    A supplied manifest is an explicit cumulative target, not a hint to plan
    every Requirement in the repository.  Keep the boundary small and derived
    only from the manifest itself so model output cannot widen a pilot into a
    full-project plan.
    """
    if not isinstance(manifest, dict):
        return None
    coverage = manifest.get("coverage") if isinstance(manifest.get("coverage"), dict) else {}
    flows = [row for row in manifest.get("flows", []) if isinstance(row, dict)]
    tests = [row for row in manifest.get("tests", []) if isinstance(row, dict)]
    flow_ids = {str(row.get("id")) for row in flows if str(row.get("id") or "").strip()}
    required_flow_ids = {str(value) for value in coverage.get("required_flow_ids", [])
                         if str(value).strip()}
    if required_flow_ids:
        flow_ids = required_flow_ids
    requirement_ids = {str(value) for row in flows for value in row.get("requirement_ids", [])
                        if str(value).strip()}
    capability_refs = {str(value) for row in flows for value in row.get("capability_refs", [])
                       if str(value).strip()}
    task_ids = {int(value) for row in flows for value in row.get("task_ids", [])
                if type(value) is int}
    test_ids = {str(value) for row in flows for value in row.get("test_ids", [])
                if str(value).strip()}
    test_ids.update(str(row.get("id")) for row in tests if str(row.get("id") or "").strip())
    source_paths = {str(value).replace("\\", "/") for row in flows
                    for value in row.get("source_paths", []) if str(value).strip()}
    contract_refs = {str(handoff.get("contract_ref")).split("#", 1)[0].replace("\\", "/")
                     for row in flows for handoff in (row.get("handoffs", []) or [])
                     if isinstance(handoff, dict) and str(handoff.get("contract_ref") or "").strip()}
    test_paths = {str(row.get("path")).split("#", 1)[0].replace("\\", "/")
                  for row in tests if str(row.get("path") or "").strip()}
    # Older manifests may not carry semantic/capability fields on each flow.
    # Resolve those fields from the authoritative task views, still bounded to
    # the manifest's explicit task IDs.
    for row in task_views or []:
        if not isinstance(row, dict):
            continue
        try:
            task_id = int(row.get("taskmaster_id"))
        except (TypeError, ValueError):
            continue
        if task_id not in task_ids:
            continue
        requirement_values = (row.get("semantic_refs")
                              if isinstance(row.get("semantic_refs"), list)
                              else row.get("requirement_ids"))
        requirement_ids.update(str(value) for value in (requirement_values or []) if str(value).strip())
        capability_values = row.get("capability_refs")
        capability_refs.update(str(value) for value in (capability_values or []) if str(value).strip())
    return {
        "scope_id": str(coverage.get("scope_id") or manifest.get("mvg_id") or "").strip(),
        "mode": str(coverage.get("mode") or "").strip(),
        "flow_ids": sorted(flow_ids),
        "requirement_ids": sorted(requirement_ids),
        "capability_refs": sorted(capability_refs),
        "task_ids": sorted(task_ids),
        "test_ids": sorted(test_ids),
        "source_paths": sorted(source_paths),
        "contract_refs": sorted(contract_refs),
        "test_paths": sorted(test_paths),
        "excluded_claims": list(coverage.get("excluded_claims") or []),
    }


def _bounded_text(value: Any, limit: int = 480) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."


def _contract_candidates(contract_refs: set[str], paths: list[str], *, limit: int = 3) -> list[str]:
    """Reduce contract evidence to paths plausibly owned by this task slice."""
    selected: list[str] = []
    for ref in sorted(contract_refs):
        tokens = {token.lower() for token in str(ref).replace(".", " ").replace("_", " ").split()
                  if len(token) > 2 and token.lower() not in {"core", "event"}}
        matches = []
        for path in paths:
            stem = Path(path).stem.replace("-", " ").replace("_", " ")
            stem_tokens = {
                token.lower() for token in re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", stem)
            }
            if tokens.intersection(stem_tokens):
                matches.append(path)
        selected.extend(matches[:limit])
    if selected:
        return sorted(set(selected))[:limit]
    # Task views often carry event/contract identifiers rather than file
    # paths. Keep a bounded real-path fallback so the model can choose an
    # actual prepared contract instead of inventing a GAP pseudo-path.
    return sorted(set(paths))[:limit]


def _flow_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: row.get(key) for key in (
        "id", "outcome", "requirement_ids", "capability_refs", "task_ids", "test_ids",
        "handoffs", "source_paths")}
            for row in rows if isinstance(row, dict)]


def _capability_membership(capabilities: dict[str, Any]) -> tuple[list[str], dict[str, dict[str, Any]], dict[str, list[str]]]:
    order: list[str] = []
    rows: dict[str, dict[str, Any]] = {}
    members: dict[str, list[str]] = {}
    for row in capabilities.get("capabilities", []):
        if not isinstance(row, dict):
            continue
        capability_id = str(row.get("capability_id") or "").strip()
        if not capability_id:
            continue
        order.append(capability_id)
        rows[capability_id] = row
        for requirement_id in _list_field(row, "requirement_ids"):
            rid = str(requirement_id).strip()
            if rid:
                members.setdefault(rid, []).append(capability_id)
    return order, rows, members


def build_flow_scopes(semantics: dict[str, Any], capabilities: dict[str, Any],
                      task_views: list[dict[str, Any]], task_ids: list[int],
                      *, batch_size: int = 24,
                      allowed_requirement_ids: set[str] | None = None) -> list[dict[str, Any]]:
    """Partition flow evidence by reviewed Capability membership.

    Capability membership in the prepared Capability file is authoritative for
    this partition. This also handles legacy Requirement capability labels that
    differ from the current Capability IDs without making the model guess.
    """
    cap_order, cap_rows, cap_members = _capability_membership(capabilities)
    task_id_set = {int(value) for value in task_ids}
    task_by_requirement: dict[str, set[int]] = {}
    for row in task_views:
        if not isinstance(row, dict):
            continue
        try:
            task_id = int(row.get("taskmaster_id"))
        except (TypeError, ValueError):
            continue
        if task_id not in task_id_set:
            continue
        requirement_values = (row.get("semantic_refs")
                              if isinstance(row.get("semantic_refs"), list)
                              else _list_field(row, "requirement_ids"))
        for requirement_id in requirement_values:
            task_by_requirement.setdefault(str(requirement_id), set()).add(task_id)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for requirement in _active_delivery_requirements(semantics):
        rid = str(requirement["requirement_id"])
        if allowed_requirement_ids is not None and rid not in allowed_requirement_ids:
            continue
        capability_refs = cap_members.get(rid, [])
        if not capability_refs:
            raise ValueError(f"Requirement {rid} has no membership in the selected Capability version")
        anchor = capability_refs[0]
        grouped.setdefault(anchor, []).append({
            "requirement_id": rid,
            "statement": str(requirement.get("statement") or "").strip(),
            "priority": requirement.get("priority"),
            "owner_hint": requirement.get("owner_hint"),
            "capability_refs": capability_refs,
            "task_ids": sorted(task_by_requirement.get(rid, set())),
        })

    order_index = {value: index for index, value in enumerate(cap_order)}
    anchors = sorted(grouped, key=lambda value: (order_index.get(value, len(order_index)), value))
    scopes: list[dict[str, Any]] = []
    for anchor in anchors:
        rows = grouped[anchor]
        for chunk_index in range(0, len(rows), max(1, batch_size)):
            chunk = rows[chunk_index:chunk_index + max(1, batch_size)]
            scope_id = f"{anchor.lower().replace('_', '-')}-{chunk_index // max(1, batch_size) + 1:02d}"
            capability_ids = sorted({capability_id for row in chunk
                                     for capability_id in row["capability_refs"]})
            scopes.append({
                "scope_id": scope_id,
                "requirements": [{**row, "statement": _bounded_text(row.get("statement"))}
                                 for row in chunk],
                "requirement_ids": [row["requirement_id"] for row in chunk],
                "task_ids": sorted({task_id for row in chunk for task_id in row["task_ids"]}),
                "capabilities": [{key: cap_rows[capability_id].get(key) for key in (
                    "capability_id", "title", "description", "requirement_ids", "boundary_rationale")}
                                  for capability_id in capability_ids if capability_id in cap_rows],
            })
    return scopes


def merge_planning_segments(base: dict[str, Any], segments: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge bounded model sections without allowing replacement or deletion."""
    result = json.loads(json.dumps(base))
    manifest = result.setdefault("manifest_candidate", {})
    if "tests" not in result and isinstance(manifest.get("tests"), list):
        # Cumulative manifests carry their existing test inventory inside the
        # manifest.  Promote it into the proposal's working section before
        # merging new test segments so baseline flow references stay resolvable.
        result["tests"] = json.loads(json.dumps(manifest["tests"]))
    flows = manifest.setdefault("flows", [])
    flow_map = {str(row.get("id")): row for row in flows if isinstance(row, dict)}
    for segment in segments:
        for row in segment.get("flows", []) or []:
            if not isinstance(row, dict) or not str(row.get("id") or "").strip():
                continue
            existing = flow_map.get(str(row["id"]))
            if existing is None:
                flows.append(row)
                flow_map[str(row["id"])] = row
            else:
                existing.update(row)
        for key in ("coverage_table", "entrypoints", "tests"):
            target = result.setdefault(key, [])
            identity_key = "requirement_id" if key == "coverage_table" else "id" if key == "tests" else None
            if key == "entrypoints":
                # One Task may own multiple real runtime boundaries.  Path and
                # symbol, rather than owner_task alone, define identity.
                by_identity = {
                    (row.get("owner_task"), str(row.get("path") or ""), str(row.get("symbol") or "")): row
                    for row in target if isinstance(row, dict)
                }
            else:
                by_identity = {str(row.get(identity_key)): row for row in target if isinstance(row, dict)}
            for row in segment.get(key, []) or []:
                if not isinstance(row, dict):
                    continue
                value = ((row.get("owner_task"), str(row.get("path") or ""), str(row.get("symbol") or ""))
                         if key == "entrypoints" else str(row.get(identity_key) or ""))
                if value and value in by_identity:
                    by_identity[value].update(row)
                elif value:
                    target.append(row)
                    by_identity[value] = row
    coverage = manifest.get("coverage")
    if isinstance(coverage, dict):
        # The manifest contract requires this sequence to be an exact ordered
        # projection of the final flow list.  Keep the flow rows themselves
        # model-owned; only repair this structural projection deterministically.
        coverage["required_flow_ids"] = [
            str(row.get("id")) for row in flows
            if isinstance(row, dict) and str(row.get("id") or "").strip()
        ]
    return result


def preserve_frozen_manifest_baseline(proposal: dict[str, Any],
                                      baseline: dict[str, Any] | None,
                                      planning_scope: dict[str, Any] | None) -> dict[str, Any]:
    """Keep an existing cumulative manifest immutable inside a frozen run.

    Model sections may still provide coverage and explanatory proposal fields,
    but an existing flow/test is an executable regression baseline. Replacing
    its handoffs or weakening an implemented test would make a planning run
    silently rewrite the acceptance contract.
    """
    if not isinstance(baseline, dict) or not isinstance(planning_scope, dict):
        return proposal
    manifest = proposal.get("manifest_candidate")
    if not isinstance(manifest, dict):
        return proposal
    baseline_flows = {
        str(row.get("id")): row
        for row in baseline.get("flows", [])
        if isinstance(row, dict) and str(row.get("id") or "").strip()
    }
    baseline_tests = {
        str(row.get("id")): row
        for row in baseline.get("tests", [])
        if isinstance(row, dict) and str(row.get("id") or "").strip()
    }
    allowed_flow_ids = [str(value) for value in planning_scope.get("flow_ids", [])]
    allowed_test_ids = set(str(value) for value in planning_scope.get("test_ids", []))
    if allowed_flow_ids:
        preserved_flows = []
        candidate_flows = {
            str(row.get("id")): row
            for row in manifest.get("flows", [])
            if isinstance(row, dict) and str(row.get("id") or "").strip()
        }
        for flow_id in allowed_flow_ids:
            baseline_flow = baseline_flows.get(flow_id)
            if baseline_flow is None:
                continue
            merged = json.loads(json.dumps(candidate_flows.get(flow_id, {})))
            # Keep the cumulative route contract and evidence inventory byte-
            # stable, while retaining model-owned semantic membership fields
            # needed to account for the frozen Requirement rows.
            for key in ("id", "task_ids", "source_paths", "handoffs", "test_ids"):
                if key in baseline_flow:
                    merged[key] = json.loads(json.dumps(baseline_flow[key]))
            preserved_flows.append(merged)
        manifest["flows"] = preserved_flows
        coverage = manifest.setdefault("coverage", {})
        if isinstance(coverage, dict):
            coverage["required_flow_ids"] = list(allowed_flow_ids)
    if allowed_test_ids:
        manifest["tests"] = [
            json.loads(json.dumps(baseline_tests[test_id]))
            for test_id in sorted(allowed_test_ids)
            if test_id in baseline_tests
        ]
        proposal["tests"] = json.loads(json.dumps(manifest["tests"]))
    return proposal


def build_segment_scope(semantics: dict[str, Any], task_ids: list[int], *, batch_size: int = 24,
                        allowed_requirement_ids: set[str] | None = None) -> list[dict[str, Any]]:
    requirements = [str(row.get("requirement_id")) for row in _active_delivery_requirements(semantics)
                    if allowed_requirement_ids is None or str(row.get("requirement_id")) in allowed_requirement_ids]
    scopes = []
    for start in range(0, len(requirements), max(1, batch_size)):
        scopes.append({"requirements": requirements[start:start + batch_size], "task_ids": task_ids})
    return scopes


def build_test_segment_requests(flow_scopes: list[dict[str, Any]],
                                planning_scope: dict[str, Any] | None = None,
                                existing_manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Route each test-generation request to exactly one Capability flow.

    A multi-flow test batch lets a model accidentally copy tests across flow
    boundaries.  Keeping one flow per request makes the route deterministic and
    gives frozen manifests their exact incumbent test IDs.
    """
    tests_by_flow = {
        str(row.get("id")): [str(value) for value in (row.get("test_ids") or [])
                              if str(value).strip()]
        for row in (existing_manifest or {}).get("flows", [])
        if isinstance(row, dict) and str(row.get("id") or "").strip()
    }
    requests: list[dict[str, Any]] = []
    for index, scope in enumerate(flow_scopes, start=1):
        flow_id = str(scope.get("scope_id") or "")
        frozen_test_ids = tests_by_flow.get(flow_id, []) if planning_scope is not None else []
        requests.append({
            "section": "tests",
            "scope_id": f"tests-{index:02d}",
            "requirements": [],
            "requirement_ids": [],
            "task_ids": sorted({int(task_id) for task_id in scope.get("task_ids", [])
                                 if type(task_id) is int}),
            "flow_scope_ids": [flow_id],
            "allow_exact_flow_id": planning_scope is not None,
            "allow_exact_test_id": planning_scope is not None,
            "test_ids": frozen_test_ids if planning_scope is not None else [],
            "test_paths": sorted(planning_scope.get("test_paths", [])) if planning_scope else [],
        })
    return requests


def build_manifest_skeleton(run_id: str, flows: list[dict[str, Any]],
                            task_statuses: dict[str, str]) -> dict[str, Any]:
    """Create only the structural manifest envelope; journey semantics stay LLM-owned."""
    flow_ids = [str(row.get("id")) for row in flows if isinstance(row, dict)]
    flow_tasks = {
        int(task_id)
        for flow in flows if isinstance(flow, dict)
        for task_id in flow.get("task_ids", [])
        if type(task_id) is int
    }

    role_tasks = {
        int(task_id)
        for flow in flows if isinstance(flow, dict)
        for handoff in flow.get("handoffs", []) if isinstance(handoff, dict)
        for task_id in (handoff.get("producer_task"), handoff.get("consumer_task"))
        if type(task_id) is int
    }
    blockers = sorted(task_id for task_id in flow_tasks & role_tasks
                      if str(task_statuses.get(str(task_id), "")).lower() != "done")
    return {
        "schema_version": "newrouge.mvg-integration.v1",
        "mvg_id": str(run_id).lower(),
        "coverage": {
            "mode": "pilot",
            "scope_id": str(run_id).lower(),
            "required_flow_ids": flow_ids,
            "blocking_task_ids": blockers,
            "excluded_claims": ["Planning does not establish runtime verification."],
        },
        "flows": flows,
        "tests": [],
    }


def write_model_context(run_dir: Path, workspace: Path, semantics: dict[str, Any],
                        task_ids: list[int]) -> Path:
    """Write a bounded, derived context view without changing prepared identity."""
    input_dir = run_dir / "analysis-input"
    capabilities = load_json(input_dir / "capabilities.v1.json", {})
    master = load_json(input_dir / "task-master.json", {})
    task_id_set = set(task_ids)
    task_rows = [row for row in (master.get("master", {}) or {}).get("tasks", [])
                 if isinstance(row, dict) and int(row.get("id", -1)) in task_id_set]
    views = []
    for name in ("tasks_back.json", "tasks_gameplay.json"):
        payload = load_json(input_dir / "task-views" / name, [])
        for row in payload:
            if not isinstance(row, dict) or int(row.get("taskmaster_id", -1)) not in task_id_set:
                continue
            views.append({key: row.get(key) for key in (
                "taskmaster_id", "semantic_refs", "capability_refs",
                "contractRefs", "source_refs", "test_refs")})
    test_views = []
    for name in ("tasks_back.json", "tasks_gameplay.json"):
        payload = load_json(input_dir / "task-views" / name, [])
        for row in payload:
            if not isinstance(row, dict) or int(row.get("taskmaster_id", -1)) not in task_id_set:
                continue
            test_views.append({"taskmaster_id": row.get("taskmaster_id"),
                               "test_refs": row.get("test_refs", [])})
    context = {
        "schema_version": "newrouge.mvg-model-context.v1",
        "requirements": [{key: row.get(key) for key in (
            "requirement_id", "kind", "statement", "capability_ids", "priority", "owner_hint")}
                          for row in semantics.get("requirements", [])
                          if isinstance(row, dict) and row.get("delivery_relevant", True) is True
                          and row.get("status", "active") == "active"],
        "capabilities": [{key: row.get(key) for key in (
            "capability_id", "title", "description", "requirement_ids", "boundary_rationale")}
                         for row in capabilities.get("capabilities", []) if isinstance(row, dict)],
        "task_master": [{key: row.get(key) for key in ("id", "title", "status")}
                        for row in task_rows],
        "task_views": views,
        "declared_contract_refs": sorted({str(value) for row in views for value in _list_field(row, "contractRefs") if str(value).strip()}),
    }
    path = workspace / "model-context.json"
    atomic_json(path, context)
    atomic_json(workspace / "test-context.json", {
        "schema_version": "newrouge.mvg-test-context.v1",
        "task_views": test_views,
        "declared_test_refs": sorted({str(value) for row in test_views for value in _list_field(row, "test_refs") if str(value).strip()}),
    })
    return path


def invoke_segmented(invoke: Any, run_dir: Path, state: dict[str, Any], attempt: int,
                     full_prompt: str, workspace: Path, *, semantics: dict[str, Any],
                     task_ids: list[int], base_proposal: dict[str, Any] | None = None,
                     planning_scope: dict[str, Any] | None = None) -> tuple[Path, dict[str, Any]]:
    """Run bounded section requests and assemble a proposal-shaped document.

    Each request is bounded to one Capability slice or one small accounting
    batch. Local code owns only identity, deduplication and skeleton retention;
    journey semantics, handoffs and test choices remain model-owned.
    """
    identity = str(state.get("analysis_identity_sha256") or "")
    segment_dir = workspace / "segments"
    segment_dir.mkdir(parents=True, exist_ok=True)
    write_model_context(run_dir, workspace, semantics, task_ids)
    model_context = load_json(workspace / "model-context.json", {})
    test_context = load_json(workspace / "test-context.json", {})
    segments: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []

    task_views: list[dict[str, Any]] = []
    for name in ("tasks_back.json", "tasks_gameplay.json"):
        payload = load_json(run_dir / "analysis-input/task-views" / name, [])
        if isinstance(payload, list):
            task_views.extend(row for row in payload if isinstance(row, dict))
    capabilities = load_json(run_dir / "analysis-input/capabilities.v1.json", {})
    _, _, capability_members = _capability_membership(capabilities)
    allowed_requirement_ids = (set(planning_scope.get("requirement_ids", []))
                               if planning_scope is not None else None)
    flow_scopes = build_flow_scopes(semantics, capabilities, task_views, task_ids,
                                    allowed_requirement_ids=allowed_requirement_ids)
    if planning_scope is not None and planning_scope.get("flow_ids"):
        # Route bounded sections through the incumbent flow IDs.  Without this
        # projection, a model-generated capability scope would create a new
        # flow ID and leave coverage/tests pointing outside the pilot.
        existing_manifest = load_json(run_dir / "analysis-input/existing-manifest.json", {})
        existing_flows = {str(row.get("id")): row for row in existing_manifest.get("flows", [])
                          if isinstance(row, dict)}
        remapped: list[dict[str, Any]] = []
        for flow_id in planning_scope["flow_ids"]:
            baseline = existing_flows.get(flow_id, {})
            requirement_set = {str(value) for value in baseline.get("requirement_ids", [])
                               if str(value).strip()}
            baseline_tasks = {int(value) for value in baseline.get("task_ids", [])
                              if type(value) is int}
            # Older manifests may omit requirement_ids.  In that case derive the
            # bounded requirements from the incumbent flow's real task owners;
            # selecting every scope here lets one frozen flow consume the other
            # flow's Requirements and makes coverage routing nondeterministic.
            selected = [scope for scope in flow_scopes
                        if (requirement_set.intersection(scope.get("requirement_ids", []))
                            if requirement_set else
                            baseline_tasks.intersection(set(scope.get("task_ids", []))))]
            if not selected and requirement_set:
                selected = [scope for scope in flow_scopes
                            if requirement_set.intersection(scope.get("requirement_ids", []))]
            requirements = [row for scope in selected for row in scope.get("requirements", [])]
            requirement_ids = list(dict.fromkeys(row.get("requirement_id") for row in requirements))
            if not requirement_ids:
                requirement_ids = sorted(requirement_set or allowed_requirement_ids or set())
            remapped.append({
                "scope_id": flow_id,
                "requirements": requirements,
                "requirement_ids": requirement_ids,
                "task_ids": sorted(set(baseline.get("task_ids", [])) & set(task_ids)),
                "capabilities": [row for row in capabilities.get("capabilities", [])
                                 if row.get("capability_id") in {
                                     cid for scope in selected for cap in scope.get("capabilities", [])
                                     for cid in [cap.get("capability_id")]}],
            })
        flow_scopes = remapped
    model_context = load_json(workspace / "model-context.json", {})
    all_task_views = model_context.get("task_views", [])
    all_test_views = load_json(workspace / "test-context.json", {}).get("task_views", [])
    prepared = run_dir / "analysis-input"
    source_manifest = load_json(prepared / "source-manifest.v1.json", {})
    manifest_source_paths = {
        str(row.get("path")).replace("\\", "/")
        for row in source_manifest.get("sources", [])
        if isinstance(row, dict) and str(row.get("path") or "").strip()
    }
    source_paths = sorted(manifest_source_paths
                          | {str(value).split(":", 1)[0] for row in all_task_views
                             if int(row.get("taskmaster_id", -1)) in set(task_ids)
                             for value in _list_field(row, "source_refs") if str(value).strip()})
    if planning_scope is not None and planning_scope.get("source_paths"):
        # An existing manifest is itself authoritative for its frozen source
        # boundary.  Those paths are copied into each candidate's immutable
        # evidence bundle during prepare, even when task views only point to
        # GDD lines rather than implementation files.  Keep them available to
        # the routed schema and reference validator.
        source_paths = sorted(
            (set(source_paths) | {
                str(value).replace("\\", "/")
                for value in planning_scope["source_paths"]
                if str(value).strip()
            }) & set(planning_scope["source_paths"])
        )
    contract_paths = sorted(
        path.relative_to(prepared / "references").as_posix()
        for path in (prepared / "references" / "Game.Core" / "Contracts").rglob("*.cs")
        if path.is_file()
    ) if (prepared / "references" / "Game.Core" / "Contracts").is_dir() else []
    if planning_scope is not None and planning_scope.get("contract_refs"):
        contract_paths = sorted(set(contract_paths) & {
            str(value).replace("\\", "/") for value in planning_scope["contract_refs"]
        })
    declared_contract_refs = set(model_context.get("declared_contract_refs", []))
    prepared_reference_paths = sorted({
        path.relative_to(prepared / family).as_posix()
        for family in ("sources", "references")
        for path in (prepared / family).rglob("*") if path.is_file()
    })

    frozen_manifest = load_json(prepared / "existing-manifest.json", {})
    frozen_tests_by_flow = {
        str(row.get("id")): sorted({str(value) for value in row.get("test_ids", [])
                                    if str(value).strip()})
        for row in frozen_manifest.get("flows", []) if isinstance(row, dict)
    }
    requests: list[dict[str, Any]] = []
    for scope in flow_scopes:
        requests.append({"section": "flows", "scope_id": scope["scope_id"],
                         "requirements": scope["requirements"],
                         "requirement_ids": scope["requirement_ids"],
                         "task_ids": scope["task_ids"],
                         "capabilities": scope["capabilities"],
                         "allow_exact_flow_id": planning_scope is not None,
                         "test_ids": sorted(
                             frozen_tests_by_flow.get(scope["scope_id"], [])
                         ) if planning_scope else []})

    # Flow coverage is accounted for in small Requirement batches after all
    # flow IDs are known. A batch contains only its own Requirement statements.
    active_rows = _active_delivery_requirements(semantics)
    requirement_context = {
        str(row["requirement_id"]): row for row in active_rows
    }
    for scope in build_segment_scope(semantics, task_ids, batch_size=24,
                                    allowed_requirement_ids=allowed_requirement_ids):
        selected_requirements = set(scope["requirements"])
        scoped_tasks = sorted({int(row.get("taskmaster_id")) for row in task_views
                               if isinstance(row, dict)
                               and str(row.get("taskmaster_id") or "").isdigit()
                               and int(row.get("taskmaster_id")) in set(task_ids)
                               and selected_requirements.intersection(
                                   {str(value) for value in (
                                       row.get("semantic_refs")
                                       if isinstance(row.get("semantic_refs"), list)
                                       else _list_field(row, "requirement_ids"))})})
        coverage_rows = []
        for rid in scope["requirements"]:
            row = requirement_context.get(rid)
            if not row:
                continue
            bounded = {key: row.get(key) for key in (
                "requirement_id", "kind", "statement", "priority", "owner_hint", "non_task_sinks")}
            bounded["capability_refs"] = capability_members.get(rid, [])
            coverage_rows.append(bounded)
        requests.append({"section": "coverage", "scope_id": f"coverage-{len(requests) + 1:02d}",
                         "requirements": coverage_rows,
                         "requirement_ids": scope["requirements"],
                         "task_ids": scoped_tasks})

    # Entrypoints follow Capability journeys, not one placeholder per task.
    # The flow barrier below supplies the actual runtime boundary context.
    for start in range(0, len(flow_scopes), 3):
        scoped_scopes = flow_scopes[start:start + 3]
        requests.append({"section": "entrypoints", "scope_id": f"entrypoints-{start // 3 + 1:02d}",
                         "requirements": [], "requirement_ids": [],
                         "task_ids": sorted({tid for scope in scoped_scopes for tid in scope["task_ids"]}),
                         "flow_scope_ids": [scope["scope_id"] for scope in scoped_scopes],
                         "capabilities": [cap for scope in scoped_scopes for cap in scope["capabilities"]]})

    requests.extend(build_test_segment_requests(
        flow_scopes,
        planning_scope,
        load_json(run_dir / "analysis-input/existing-manifest.json", {})
        if planning_scope is not None else None,
    ))

    def execute_request(index: int, request: dict[str, Any], flow_context: list[dict[str, Any]]) -> tuple[int, dict[str, Any], dict[str, Any]]:
        section = request["section"]
        requirements = request["requirement_ids"]
        scoped_tasks = request["task_ids"]
        flow_prefix = ("" if planning_scope is not None else f"{request['scope_id']}-") if section == "flows" else ""
        test_prefix = (f"{request['scope_id']}-"
                       if section == "tests" and planning_scope is None else "")
        prompt_flow_context = flow_context
        if section == "tests" and request.get("flow_scope_ids"):
            prompt_flow_context = [row for row in flow_context
                                   if isinstance(row, dict)
                                   and any((str(row.get("id", "")) == scope_id or
                                            (not request.get("allow_exact_flow_id") and
                                             str(row.get("id", "")).startswith(scope_id + "-")))
                                           for scope_id in request["flow_scope_ids"])]
        section_prompt_text = segment_prompt(
            section=section, identity=identity,
            requirements=requirements, task_ids=scoped_tasks,
            flow_context=prompt_flow_context,
            scope_id=request["scope_id"], flow_id_prefix=flow_prefix, test_id_prefix=test_prefix,
            allow_exact_flow_id=bool(planning_scope is not None and section == "flows"),
            allow_exact_test_id=bool(planning_scope is not None and section == "tests"),
        )
        if planning_scope is not None:
            section_prompt_text += "\nThis is a frozen existing-manifest scope. Do not add obligations outside it. " \
                "Preserve exactly these flow/test IDs and use only these Requirement, Task, source and test IDs:\n"
            section_prompt_text += json.dumps({
                "flow_ids": ([request["scope_id"]] if section == "flows" else
                             request.get("flow_scope_ids", []) if section == "tests" else
                             planning_scope.get("flow_ids", [])),
                "requirement_ids": planning_scope.get("requirement_ids", []),
                "task_ids": planning_scope.get("task_ids", []),
                "test_ids": (request.get("test_ids", [])
                             if section in ("flows", "tests")
                             else planning_scope.get("test_ids", [])),
                "source_paths": planning_scope.get("source_paths", []),
                "contract_refs": planning_scope.get("contract_refs", []),
                "test_paths": planning_scope.get("test_paths", []),
            }, ensure_ascii=False)
            if section in ("coverage", "tests"):
                section_prompt_text += (
                    "\nFor this frozen scope, every flow_id must be copied exactly from the listed "
                    "existing flow_ids. Never prefix or rename an existing flow ID; only test IDs "
                    "may use the segment prefix.\n"
                )
        if flow_context:
            selected_flow_rows = flow_context
            if request.get("flow_scope_ids"):
                selected_flow_rows = [row for row in flow_context
                                      if any((str(row.get("id", "")) == scope_id or
                                              str(row.get("id", "")).startswith(scope_id + "-"))
                                             for scope_id in request["flow_scope_ids"])]
            section_prompt_text += "\nUse these already prepared flow objects as the only flow context:\n"
            section_prompt_text += json.dumps(
                _flow_summaries(selected_flow_rows), ensure_ascii=False)
        if section == "flows":
            scoped_refs = {str(value) for row in all_task_views
                           if int(row.get("taskmaster_id", -1)) in set(scoped_tasks)
                           for value in _list_field(row, "contractRefs") if str(value).strip()}
            section_prompt_text += "\nInline bounded evidence context:\n" + json.dumps({
                "requirements": request["requirements"],
                "capabilities": request.get("capabilities", []),
                "task_views": [row for row in all_task_views
                               if int(row.get("taskmaster_id", -1)) in set(scoped_tasks)],
                "available_source_paths": source_paths,
                "available_contract_paths": _contract_candidates(scoped_refs, contract_paths),
                "declared_contract_refs": sorted(scoped_refs),
            }, ensure_ascii=False)
        elif section == "coverage":
            section_prompt_text += "\nInline bounded evidence context:\n" + json.dumps({
                "requirements": request["requirements"],
                "capabilities": [{key: row.get(key) for key in (
                    "capability_id", "title", "requirement_ids")}
                                 for row in request.get("capabilities", [])],
                "available_reference_paths": prepared_reference_paths,
            }, ensure_ascii=False)
        elif section == "entrypoints":
            section_prompt_text += "\nInline bounded evidence context:\n" + json.dumps({
                "capabilities": request.get("capabilities", []),
                "task_master": [row for row in model_context.get("task_master", [])
                                if int(row.get("id", -1)) in set(scoped_tasks)],
                "task_views": [row for row in all_task_views
                               if int(row.get("taskmaster_id", -1)) in set(scoped_tasks)],
                "available_source_paths": source_paths,
            }, ensure_ascii=False)
        elif section == "tests":
            section_prompt_text += "\nInline bounded evidence context:\n" + json.dumps({
                "task_views": [row for row in all_test_views
                               if int(row.get("taskmaster_id", -1)) in set(scoped_tasks)],
                "available_test_paths": sorted({str(value) for row in all_test_views
                                                if int(row.get("taskmaster_id", -1)) in set(scoped_tasks)
                                                for value in _list_field(row, "test_refs") if str(value).strip()}),
            }, ensure_ascii=False)
        output_name = f"segments/{index:03d}-{section}.json"
        last_error = ""
        for retry in range(1, 4):
            try:
                output, receipt = invoke(section_prompt_text, attempt,
                                         output_name=output_name,
                                         output_schema_path=workspace / "segment-schemas" / f"{index:03d}-{section}.json",
                                         output_schema=segment_output_schema(
                                              section=section,
                                              identity=identity,
                                              scope_id=request["scope_id"],
                                              available_source_paths=source_paths,
                                              available_contract_paths=contract_paths,
                                              allowed_flow_ids=(
                                                  [request["scope_id"]]
                                                  if planning_scope is not None and section == "flows"
                                                  else ([str(row["id"]) for row in prompt_flow_context]
                                                        if section == "tests"
                                                        else planning_scope.get("flow_ids", [])
                                                        if planning_scope is not None and section == "coverage"
                                                        else None)
                                              ),
                                              allowed_test_ids=(
                                                  _segment_allowed_test_ids(request, planning_scope, section)
                                                  if planning_scope is not None and section in ("flows", "tests") else None
                                              ),
                                              allowed_test_paths=(
                                                  planning_scope.get("test_paths", [])
                                                  if planning_scope is not None and section == "tests" else None
                                              ),
                                              available_reference_paths=(
                                                  prepared_reference_paths if section == "coverage" else None
                                              ),
                                          ))
                parsed = json.loads(output.read_text(encoding="utf-8"))
                if not isinstance(parsed, dict):
                    raise ValueError(f"MVG segment {section} must be a JSON object")
                errors = validate_segment_identity(parsed, section=section, identity=identity,
                                                   scope_id=request["scope_id"])
                errors.extend(validate_segment_routing(
                    parsed, section=section, request=request,
                    flow_context=flow_context,
                ))
                errors.extend(validate_segment_references(
                    parsed,
                    section=section,
                    prepared=prepared,
                    available_source_paths=source_paths,
                    available_contract_paths=contract_paths,
                    available_test_paths=sorted({str(value).replace("\\", "/")
                                                 for row in all_test_views
                                                 for value in _list_field(row, "test_refs")
                                                 if str(value).strip()}),
                ))
                if errors:
                    raise ValueError(f"MVG segment {section} identity invalid: {'; '.join(errors)}")
                return index, parsed, {"section": section, "index": index, "retry": retry, "receipt": receipt}
            except (json.JSONDecodeError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
                last_error = str(exc)
                section_prompt_text += (
                    "\nThe previous response failed deterministic routing/schema validation. "
                    f"Exact errors: {last_error}. Correct every listed route or schema error "
                    "in this retry; do not return a bare section payload or reuse a flow with "
                    "a mismatched Requirement, Capability, or owner Task."
                )
        raise ValueError(last_error or f"MVG segment {section} failed after retries")

    def execute_batch(batch: list[tuple[int, dict[str, Any]]], flow_context: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any], dict[str, Any]]]:
        if not batch:
            return []
        reusable: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
        pending: list[tuple[int, dict[str, Any]]] = []
        for index, request in batch:
            cached = load_reusable_segment(
                run_dir,
                current_attempt=attempt,
                index=index,
                section=request["section"],
                identity=identity,
                scope_id=request["scope_id"],
                prepared=prepared,
                available_source_paths=source_paths,
                available_contract_paths=contract_paths,
                available_test_paths=sorted({str(value).replace("\\", "/")
                                             for row in all_test_views
                                             for value in _list_field(row, "test_refs")
                                             if str(value).strip()}),
                routing_request=request,
                flow_context=flow_context,
            )
            if cached is None:
                pending.append((index, request))
            else:
                reusable.append((index, cached, {
                    "section": request["section"],
                    "index": index,
                    "reused_from_prior_attempt": True,
                }))
        # Parallelize independent bounded LLM calls while keeping the flow
        # stage as a barrier for coverage/tests that need stable flow IDs.
        if pending:
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(3, len(pending))) as executor:
                futures = [executor.submit(execute_request, index, request, flow_context)
                           for index, request in pending]
                generated = [future.result() for future in futures]
        else:
            generated = []
        return sorted(reusable + generated, key=lambda row: row[0])

    indexed_requests = list(enumerate(requests, start=1))
    flow_batch = [(index, request) for index, request in indexed_requests if request["section"] == "flows"]
    flow_results = execute_batch(flow_batch, [])
    segments.extend(parsed for _, parsed, _ in flow_results)
    receipts.extend(receipt for _, _, receipt in flow_results)
    flow_context = [row for _, parsed, _ in flow_results
                    for row in (parsed.get("flows", []) or []) if isinstance(row, dict)]
    other_batch = [(index, request) for index, request in indexed_requests if request["section"] != "flows"]
    other_results = execute_batch(other_batch, flow_context)
    segments.extend(parsed for _, parsed, _ in other_results)
    receipts.extend(receipt for _, _, receipt in other_results)

    flow_rows = [row for segment in segments if segment.get("section") == "flows"
                 for row in (segment.get("flows", []) or []) if isinstance(row, dict)]
    status_payload = load_json(run_dir / "analysis-input/task-master.json", {})
    task_statuses = {
        str(row.get("id")): str(row.get("status", "")).lower()
        for row in (status_payload.get("master", {}) or {}).get("tasks", [])
        if isinstance(row, dict)
    }
    existing_manifest = load_json(run_dir / "analysis-input/existing-manifest.json", None)
    baseline_flow_ids = {
        str(row.get("id"))
        for row in (existing_manifest or {}).get("flows", [])
        if isinstance(row, dict) and str(row.get("id") or "").strip()
    } if isinstance(existing_manifest, dict) else set()
    if isinstance(existing_manifest, dict):
        manifest_base = existing_manifest
    else:
        manifest_base = build_manifest_skeleton(str(state.get("run_id")), flow_rows, task_statuses)
    base = {
        "schema_version": PROPOSAL_SCHEMA,
        "analysis_identity_sha256": identity,
        "planning_status": "ready_for_validation",
        "manifest_candidate": manifest_base,
        "coverage_table": [], "entrypoints": [], "gaps": [],
        "manual_obligations": [], "change_reviews": [], "retirement_reviews": [],
        "coverage_review": {}, "notes": [],
    }
    if base_proposal:
        base = merge_planning_segments(base_proposal, [])
    assembled = merge_planning_segments(base, segments)
    # Preserve the non-droppable prepared skeleton even if an individual
    # section returns an incomplete subset. Semantic assignments still belong
    # to the model and are validated in the normal proposal pass.
    skeleton_coverage_payload = load_json(run_dir / "coverage-skeleton.json", None)
    if skeleton_coverage_payload is None:
        skeleton_coverage_payload = load_json(run_dir / "analysis-input/coverage-skeleton.json", {})
    skeleton_entrypoints_payload = load_json(run_dir / "entrypoint-skeleton.json", None)
    if skeleton_entrypoints_payload is None:
        skeleton_entrypoints_payload = load_json(run_dir / "analysis-input/entrypoint-skeleton.json", {})
    skeleton_coverage = (skeleton_coverage_payload.get("rows", [])
                         if isinstance(skeleton_coverage_payload, dict)
                         else skeleton_coverage_payload or [])
    skeleton_entrypoints = (skeleton_entrypoints_payload.get("rows", [])
                            if isinstance(skeleton_entrypoints_payload, dict)
                            else skeleton_entrypoints_payload or [])
    assembled["coverage_table"] = merge_planning_segments(
        {"coverage_table": skeleton_coverage},
        [{"coverage_table": assembled.get("coverage_table", [])}],
    ).get("coverage_table", skeleton_coverage)
    assembled["entrypoints"] = merge_planning_segments(
        {"entrypoints": skeleton_entrypoints},
        [{"entrypoints": assembled.get("entrypoints", [])}],
    ).get("entrypoints", skeleton_entrypoints)
    bind_manifest_test_ids(assembled, preserve_flow_ids=baseline_flow_ids)
    if planning_scope is not None:
        # The existing manifest is the cumulative target. Keep its exact
        # baseline rows and discard any model-created out-of-scope additions;
        # validate_proposal will report the boundary if the model changed one.
        allowed_flows = set(planning_scope.get("flow_ids", []))
        if allowed_flows:
            base_flows = {str(row.get("id")): row for row in (base.get("manifest_candidate", {}).get("flows", []) or [])
                          if isinstance(row, dict)}
            model_flows = [row for row in assembled.get("manifest_candidate", {}).get("flows", [])
                           if isinstance(row, dict) and str(row.get("id")) in allowed_flows]
            merged_flows = {str(row.get("id")): row for row in model_flows}
            for flow_id, row in base_flows.items():
                if flow_id in allowed_flows and flow_id not in merged_flows:
                    merged_flows[flow_id] = row
            assembled["manifest_candidate"]["flows"] = [merged_flows[key] for key in planning_scope["flow_ids"]
                                                          if key in merged_flows]
            assembled["manifest_candidate"].setdefault("coverage", {})["required_flow_ids"] = list(planning_scope["flow_ids"])
        assembled = preserve_frozen_manifest_baseline(
            assembled,
            load_json(run_dir / "analysis-input/existing-manifest.json", None),
            planning_scope,
        )
    assembled.setdefault("manifest_candidate", {})["tests"] = assembled.get("tests", [])
    output = workspace / f"proposal-attempt-{attempt}.json"
    atomic_json(output, assembled)
    return output, {"attempt": attempt, "segmented": True, "segments": receipts}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _run_dir(root: Path, run_id: str) -> Path:
    return root / DEFAULT_RUN_ROOT / run_id


def _load_run(root: Path, run_id: str) -> tuple[Path, dict[str, Any]]:
    path = _run_dir(root, run_id) / "run.json"
    payload = load_json(path, {})
    if payload.get("schema_version") != RUN_SCHEMA:
        raise ValueError(f"missing or invalid MVG planning run: {run_id}")
    return path, payload


def _copy_file(root: Path, source: Path, bundle: Path, rel: str | None = None) -> str:
    if not source.is_file():
        raise ValueError(f"missing planning input: {source}")
    target = bundle / (rel or source.resolve().relative_to(root.resolve()).as_posix())
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    return file_sha(target)


def _task_ids(root: Path) -> set[int]:
    payload = load_json(root / ".taskmaster/tasks/tasks.json", {})
    return {
        int(row["id"])
        for row in (payload.get("master", {}) or {}).get("tasks", [])
        if isinstance(row, dict) and type(row.get("id")) is int
    }


def _task_view_rows(root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in TASK_VIEWS:
        payload = load_json(root / path, [])
        if isinstance(payload, list):
            rows.extend(row for row in payload if isinstance(row, dict))
    return rows


def _task_readiness(root: Path, task_ids: list[str], allow_unready: bool) -> dict[str, Any]:
    from chapter5_semantic_reconciliation import load_task_readiness
    from _planning_scope import round_scope

    scope = round_scope(root, task_ids, root / LEDGER, root / SEMANTICS)

    rows = []
    all_ready = not scope["errors"]
    for task_id in sorted(set(task_ids + ([scope["global_chapter5_witness"]] if scope.get("global_chapter5_witness") else []))):
        ok, payload, reason = load_task_readiness(root, task_id)
        rows.append({
            "task_id": task_id,
            "ready": bool(ok),
            "reason": reason,
            "readiness": payload.get("readiness") if isinstance(payload, dict) else None,
        })
        all_ready = all_ready and ok
    if not all_ready and not allow_unready:
        raise ValueError(
            "MVG formal planning requires current Chapter 5 readiness for the explicit task scope"
        )
    return {
        "schema_version": "newrouge.mvg-planning-readiness-summary.v1",
        "formal_ready": all_ready,
        "allow_unready_draft": bool(allow_unready),
        "tasks": rows,
        "round_scope": scope,
    }


def prepare(
    root: Path,
    *,
    run_id: str,
    capabilities_path: Path,
    task_ids: list[str],
    manifest_path: Path | None,
    allow_unready: bool,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    capabilities = load_json(capabilities_path, {})
    if capabilities.get("schema_version") != "newrouge.capabilities.v1":
        raise ValueError("explicit Capability input is missing or invalid")
    run_dir = _run_dir(root, run_id)
    if (run_dir / "run.json").is_file():
        raise ValueError("MVG run already exists; resume its incomplete stage or use a new run ID")
    bundle = run_dir / "analysis-input"
    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True)
    readiness = _task_readiness(root, task_ids, allow_unready)

    files: dict[str, str] = {}
    authority: dict[str, str | None] = {}
    files["capabilities.v1.json"] = _copy_file(root, capabilities_path, bundle, "capabilities.v1.json")
    files["source-manifest.v1.json"] = _copy_file(root, root / SOURCE_MANIFEST, bundle, "source-manifest.v1.json")
    files["source-blocks.v1.json"] = _copy_file(root, root / LEDGER, bundle, "source-blocks.v1.json")
    files["semantic-requirements.v1.json"] = _copy_file(root, root / SEMANTICS, bundle, "semantic-requirements.v1.json")
    manifest = load_json(root / SOURCE_MANIFEST, {})
    for row in manifest.get("sources", []):
        if not isinstance(row, dict) or not str(row.get("path") or "").strip():
            continue
        value = str(row["path"])
        files[f"sources/{value}"] = _copy_file(root, repo_path(root, value), bundle, f"sources/{value}")
    for path in TASK_VIEWS:
        files[f"task-views/{path.name}"] = _copy_file(root, root / path, bundle, f"task-views/{path.name}")
    files["task-master.json"] = _copy_file(root, root / ".taskmaster/tasks/tasks.json", bundle, "task-master.json")

    referenced: set[str] = set()
    # Task views commonly store event/contract identifiers rather than file
    # paths. Bind the real BCL-only contract sources into the immutable bundle
    # so flow planning can select an actual prepared contract_ref.
    contract_root = root / "Game.Core" / "Contracts"
    if contract_root.is_dir():
        referenced.update(
            path.resolve().relative_to(root.resolve()).as_posix()
            for path in contract_root.rglob("*.cs") if path.is_file()
        )
    existing_manifest = None
    planning_scope = None
    if manifest_path is not None and manifest_path.is_file():
        existing_manifest = load_json(manifest_path, {})
        planning_scope = _manifest_planning_scope(existing_manifest, _task_view_rows(root))
        files["existing-manifest.json"] = _copy_file(root, manifest_path, bundle, "existing-manifest.json")
        for flow in existing_manifest.get("flows", []):
            referenced.update(str(p) for p in flow.get("source_paths", []))
            referenced.update(str(h["contract_ref"]) for h in flow.get("handoffs", []))
        referenced.update(str(t["path"]) for t in existing_manifest.get("tests", []))
    for ref in evidence_refs or []:
        path = repo_path(root, ref)
        if not path.is_file():
            raise ValueError(f"explicit MVG evidence file is missing:{ref}")
        referenced.add(path.relative_to(root.resolve()).as_posix())
    for row in _task_view_rows(root):
        for field in ("overlay_refs", "contractRefs", "test_refs"):
            for value in _list_field(row, field):
                text = str(value).strip().replace("\\", "/")
                if text:
                    referenced.add(text)
        for acceptance in _list_field(row, "acceptance"):
            text = str(acceptance)
            if "Refs:" not in text:
                continue
            tail = text.split("Refs:", 1)[1]
            for value in tail.replace(";", ",").split(","):
                cleaned = value.strip().replace("\\", "/")
                if cleaned:
                    referenced.add(cleaned)
    for value in sorted(referenced):
        try:
            path = repo_path(root, value)
        except ValueError:
            continue
        if path.is_file():
            files[f"references/{value}"] = _copy_file(root, path, bundle, f"references/{value}")

    atomic_json(bundle / "readiness-summary.json", readiness)
    files["readiness-summary.json"] = file_sha(bundle / "readiness-summary.json")
    scoped_requirement_ids = (set(planning_scope["requirement_ids"])
                              if planning_scope is not None else None)
    skeleton = build_coverage_skeleton(load_json(root / SEMANTICS, {}), _task_view_rows(root),
                                       scoped_requirement_ids)
    atomic_json(bundle / "coverage-skeleton.json", {"schema_version": "newrouge.mvg-coverage-skeleton.v1", "rows": skeleton})
    files["coverage-skeleton.json"] = file_sha(bundle / "coverage-skeleton.json")
    entrypoint_tasks = sorted(set(planning_scope["task_ids"]) if planning_scope is not None else
                              {int(row.get("taskmaster_id")) for row in _task_view_rows(root)
                               if str(row.get("taskmaster_id", "")).isdigit()})
    atomic_json(bundle / "entrypoint-skeleton.json", {"schema_version": "newrouge.mvg-entrypoint-skeleton.v1",
        "rows": build_entrypoint_skeleton(entrypoint_tasks)})
    files["entrypoint-skeleton.json"] = file_sha(bundle / "entrypoint-skeleton.json")
    index = {
        "schema_version": "newrouge.mvg-planning-input.v1",
        "capabilities_sha256": file_sha(capabilities_path),
        "files": files,
        "task_scope": task_ids,
        "planning_scope": planning_scope,
        "authority_inputs": authority,
        "existing_manifest": (
            {"path": manifest_path.resolve().relative_to(root.resolve()).as_posix(), "sha256": file_sha(manifest_path)}
            if manifest_path is not None and manifest_path.is_file()
            else None
        ),
    }
    # Bind original authority paths as well as their copies. The prepared
    # baseline includes absence, so an initial plan cannot overwrite a newly
    # introduced manifest at apply time.
    originals = [capabilities_path, root / SOURCE_MANIFEST, root / LEDGER, root / SEMANTICS,
                 root / ".taskmaster/tasks/tasks.json", *(root / p for p in TASK_VIEWS)]
    originals.extend(repo_path(root, str(row["path"])) for row in manifest.get("sources", []))
    originals.extend(repo_path(root, value) for value in referenced)
    from chapter5_semantic_reconciliation import (
        DEFAULT_EXTRACTION_SNAPSHOT, readiness_path_for_task, reconciliation_path_for_task,
    )
    originals.append(root / DEFAULT_EXTRACTION_SNAPSHOT)
    for task_id in [row["task_id"] for row in readiness["tasks"]]:
        originals.extend([readiness_path_for_task(root, task_id), reconciliation_path_for_task(root, task_id)])
        reconciliation = load_json(reconciliation_path_for_task(root, task_id), {})
        for kind in ("contracts", "adrs"):
            for row in (reconciliation.get("authority_scope") or {}).get(kind, []):
                path = repo_path(root, str(row["path"]))
                originals.append(path)
                rel = path.resolve().relative_to(root.resolve()).as_posix()
                if path.is_file() and f"references/{rel}" not in files:
                    files[f"references/{rel}"] = _copy_file(root, path, bundle, f"references/{rel}")
    if manifest_path is not None:
        originals.append(manifest_path)
    for path in originals:
        authority[path.resolve().relative_to(root.resolve()).as_posix()] = normalized_file_sha(path) if path.is_file() else None
    index["analysis_identity_sha256"] = canonical_sha(index)
    atomic_json(bundle / "analysis-index.json", index)

    state = {
        "schema_version": RUN_SCHEMA,
        "run_id": run_id,
        "phase": "prepared",
        "created_at_utc": now(),
        "formal_ready": readiness["formal_ready"],
        "analysis_identity_sha256": index["analysis_identity_sha256"],
        "capabilities_path": capabilities_path.resolve().relative_to(root.resolve()).as_posix(),
        "capabilities_sha256": index["capabilities_sha256"],
        "manifest_path": (
            manifest_path.resolve().relative_to(root.resolve()).as_posix()
            if manifest_path is not None else None
        ),
        "existing_manifest_sha256": (
            file_sha(manifest_path) if manifest_path is not None and manifest_path.is_file() else None
        ),
        "task_scope": task_ids,
        "planning_scope": planning_scope,
        "applied": False,
    }
    atomic_json(run_dir / "run.json", state)
    return state


def _build_incumbent_proposal(root: Path, run_dir: Path, state: dict[str, Any],
                              manifest: dict[str, Any]) -> dict[str, Any]:
    """Project the current manifest into the proposal envelope for comparison.

    The existing MVG manifest is the only incumbent authority. The surrounding
    proposal fields are a deterministic review projection, never a new source
    of Capability or Requirement membership.
    """
    semantics = load_json(run_dir / "analysis-input/semantic-requirements.v1.json", {})
    capabilities = load_json(run_dir / "analysis-input/capabilities.v1.json", {})
    task_views: list[dict[str, Any]] = []
    for name in ("tasks_back.json", "tasks_gameplay.json"):
        payload = load_json(run_dir / "analysis-input/task-views" / name, [])
        if isinstance(payload, list):
            task_views.extend(row for row in payload if isinstance(row, dict))
    active = _active_delivery_requirements(semantics)
    planning_scope = state.get("planning_scope")
    if isinstance(planning_scope, dict):
        scoped_ids = {str(value) for value in planning_scope.get("requirement_ids", [])}
        active = [row for row in active if str(row.get("requirement_id")) in scoped_ids]
    cap_membership = {
        str(row.get("capability_id")): {str(value) for value in row.get("requirement_ids", [])}
        for row in capabilities.get("capabilities", [])
        if isinstance(row, dict) and str(row.get("capability_id") or "").strip()
    }
    task_members: dict[int, set[str]] = {}
    for row in task_views:
        if isinstance(row.get("taskmaster_id"), int):
            task_members.setdefault(int(row["taskmaster_id"]), set()).update(
                str(value) for value in row.get("semantic_refs", row.get("requirement_ids", []))
            )
    flows = [row for row in manifest.get("flows", []) if isinstance(row, dict)]
    coverage: list[dict[str, Any]] = []
    for requirement in active:
        rid = str(requirement.get("requirement_id"))
        matched = None
        for flow in flows:
            if rid not in {str(value) for value in flow.get("requirement_ids", [])}:
                continue
            capability_ref = next((str(value) for value in flow.get("capability_refs", [])
                                   if rid in cap_membership.get(str(value), set())), None)
            task_id = next((int(value) for value in flow.get("task_ids", [])
                            if rid in task_members.get(int(value), set()) or not task_members), None)
            if capability_ref and task_id is not None:
                matched = (str(flow.get("id")), capability_ref, task_id)
                break
        if matched is None:
            coverage.append({
                "requirement_id": rid,
                "flow_id": None,
                "capability_ref": None,
                "task_id": None,
                "disposition": "deferred",
                "rationale": "Incumbent manifest does not expose a complete reviewed route for this Requirement.",
                "sink_id": None,
                "verification_ref": None,
                "authority_ref": None,
                "authority_review": None,
            })
        else:
            flow_id, capability_ref, task_id = matched
            coverage.append({
                "requirement_id": rid,
                "flow_id": flow_id,
                "capability_ref": capability_ref,
                "task_id": task_id,
                "disposition": "flow",
                "rationale": "Retained from the current MVG incumbent manifest.",
                "sink_id": None,
                "verification_ref": None,
                "authority_ref": None,
                "authority_review": None,
            })
    entrypoints = load_json(run_dir / "analysis-input/entrypoint-skeleton.json", {})
    return {
        "schema_version": PROPOSAL_SCHEMA,
        "analysis_identity_sha256": state["analysis_identity_sha256"],
        "planning_status": "ready_for_validation",
        "manifest_candidate": deepcopy(manifest),
        "coverage_table": coverage,
        "entrypoints": entrypoints.get("rows", []) if isinstance(entrypoints, dict) else [],
        "gaps": [],
        "manual_obligations": [],
        "change_reviews": [],
        "retirement_reviews": [],
        "coverage_review": {},
        "notes": ["Current MVG incumbent projected for comparative evaluation; no Capability membership was inferred."],
    }


PROMPT = """You are planning cumulative MVG integration scope after Capability planning.

Read every file under analysis-input/. `capabilities.v1.json` is the explicit and exclusive Capability SSoT for this run: use only its Capability IDs, titles, boundaries, and Requirement membership. Do not create, rename, merge, split, or infer Capabilities from the GDD, task views, tests, contracts, or an existing MVG manifest. Those other files are auxiliary evidence for journey semantics, ownership, implementation, and verification only. The exact Capability file must not be modified. `coverage-skeleton.json` is a non-droppable ledger: every active delivery Requirement must remain represented; you must not delete or silently omit its rows. Authoritative design semantics remain the GDD/source and reviewed Requirements, but they cannot override the selected Capability version's membership. Existing task/Acceptance/contracts/tests and an existing manifest, when present, are evidence.

Return JSON only with schema_version = "newrouge.mvg-planning-proposal.v1".
Required fields:
- schema_version
- analysis_identity_sha256 (copy from analysis-input/analysis-index.json)
- planning_status: draft | ready_for_validation
- manifest_candidate: one complete newrouge.mvg-integration.v1 document
- coverage_table
- entrypoints
- gaps
- manual_obligations
- change_reviews
- retirement_reviews
- coverage_review
- notes

Design flows from player goals, triggers, actions, cross-system state changes, observable outcomes, failure/recovery and real handoffs. A flow may span many Capabilities and a Capability may participate in many flows. Do not create one flow per Capability mechanically.

Every flow in manifest_candidate may use additional requirement_ids and capability_refs fields for traceability. task_ids and handoff producer/consumer/owner must be real Taskmaster IDs. contract_ref must refer to an existing repository contract; if no real contract exists, record a gap and keep planning_status=draft rather than inventing one.

entrypoints rows use status existing_verified or planned. existing_verified must point to an input file actually present in references/ or sources/. planned must name a real owner_task plus target path/symbol, inputs, state, assertions and implementation acceptance; it must not claim the file exists.

For every handoff success/failure/recovery assertion, explicitly identify the producer request data, the consumer-observable result or failure signal, and the owned state transition that makes the assertion testable. Request/contract data alone is not proof of completion. A success-only input cannot exercise the failure branch. Explain how prepared recovery/retry/permission fields constrain the consumer's result and recovery state. A planned owned entrypoint may specify a proposed result callback or failure input as an implementation obligation, but must label it planned rather than invent an existing contract member. If an actual required contract or upstream semantic decision is missing, retain a genuine gap. Make these relationships explicit in inputs, state, assertions and implementation_acceptance so the independent reviewer can verify the whole handoff.

Preserve the source-specified producer/consumer system roles for every required interaction and map each role to its real owning Task ID. Task IDs identify owners; they do not replace distinct services, terminals, UI surfaces or domain consumers named by the source. One task may own more than one such role, so do not collapse a required internal system boundary merely because its roles share a task. State which system sends which contract/request/result, which receiving system consumes it, and the receiving system's observable state change. Make the same named producer-to-consumer interaction explicit in the flow/handoff, owned entrypoints and planned test scenarios/assertions; generic producer/consumer task labels alone cannot substantiate domain-integration evidence. Preserve source roles without inventing new components or existing implementations.

Tests may be planned or implemented using the existing MVG schema. implemented means implementation exists in the prepared references/ or sources/, not passed. Every claimed existing source, contract, entrypoint, verification or reviewed authority must also be readable in this fixed bundle. If missing, report the dependency so the operator can prepare a new run with --evidence-ref; never validate a newly read repository file outside the prepared input. Do not set runtime_verified and do not claim any plan validation is a runtime run.
Reserve gaps for unresolved upstream design, Requirement, ownership, Acceptance or required real-contract evidence. A correctly specified planned entrypoint/test is a future implementation obligation, not an upstream gap. Missing runtime execution is expected at this planning stage, not a gap. Record those boundaries in notes/manual_obligations and keep the entrypoint/test state planned. Use planning_status=ready_for_validation with gaps=[] when all upstream evidence and planning obligations are complete; use draft for a genuine unresolved upstream gap. Never erase or disguise a genuine gap just to make validation pass.
When an existing manifest is present, preserve old flow/test IDs and obligations unless an explicit reviewed specification supports update/retire/coverage weakening. Provide those reviews in change_reviews / retirement_reviews / coverage_review.

coverage_table must account for EVERY active delivery-relevant Requirement. Start from coverage-skeleton.json and preserve every row; assign flow_id and rationale without deleting rows. Every flow row requires requirement_id, capability_ref, integer task_id, flow_id, and a nonempty string field named rationale, consistent with both the flow's requirement_ids/capability_refs/task_ids and the actual Requirement-to-Capability and Requirement-to-Task membership. Use the literal JSON key rationale, not coverage_rationale or reason. Other verification rows require disposition=other_verification, sink_id from the Requirement's non_task_sinks, verification_ref to an existing prepared file and rationale. Deferred rows require disposition=deferred and the same resolvable authority_ref/authority_review contract used for baseline weakening. Never leave coverage_table empty. entrypoint-skeleton.json is intentionally empty: derive executable entrypoints from real Capability journey boundaries, not Task enumeration. Task IDs are evidence owners, not runtime API obligations. A test or governance task remains verification/review evidence even when referenced by a legacy handoff. Do not convert data-only contracts into executable APIs. Evidence-only owners do not need entrypoints; a flow with runtime handoffs still needs real executable boundary evidence, checked by independent semantic review.
"""


def generate(root: Path, *, run_id: str, timeout_sec: int, llm_backend: str, segmented: bool = True) -> dict[str, Any]:
    """Generate three isolated MVG proposals, then have an isolated reviewer select one."""
    # Legacy correction runs still use apply_restricted_patch; new candidates
    # are complete independent proposals and never patch another candidate.
    run_path, state = _load_run(root, run_id)
    _validate_input_freshness(root, run_path.parent, state)
    if state.get("formal_ready") is not True:
        raise ValueError("formal MVG planning is blocked until the explicit Chapter 5 scope is ready")
    if llm_backend not in SUPPORTED_LLM_BACKENDS:
        raise ValueError("MVG planning requires one of: " + ", ".join(sorted(SUPPORTED_LLM_BACKENDS)))
    run_dir = run_path.parent
    existing_proposal = load_json(run_dir / "proposal.json", {})
    if state.get("selection_status") == "selected" and isinstance(existing_proposal, dict):
        validation = validate_proposal(root, state, existing_proposal)
        selected_admission = state.get("selected_admission_review") or {}
        selected_candidate = str(state.get("selected_candidate") or "")
        candidate_admission = (state.get("candidate_admissions") or {}).get(selected_candidate) or {}
        try:
            _proposal_path, proof_path, execution_path = _bound_admission_artifacts(
                root, run_dir, candidate_admission)
            proof_ok = (
                selected_admission.get("path") == proof_path.relative_to(root).as_posix()
                and selected_admission.get("execution_path") == execution_path.relative_to(root).as_posix()
                and proof_path.is_file() and execution_path.is_file()
            )
        except (OSError, ValueError):
            proof_path = execution_path = None
            proof_ok = False
        if proof_ok:
            expected_proof_sha = str(selected_admission.get("proof_sha256") or "")
            expected_execution_sha = str(selected_admission.get("execution_sha256") or "")
            proof_ok = (bool(expected_proof_sha and expected_execution_sha)
                        and file_sha(proof_path) == expected_proof_sha
                        and file_sha(execution_path) == expected_execution_sha)
        if proof_ok:
            from _mvg_planning_review import review_execution_errors
            proof = load_json(proof_path, {})
            execution = load_json(execution_path, {})
            proof_errors = candidate_admission_errors(root, state, existing_proposal, proof)
            proof_errors.extend(review_execution_errors(state, existing_proposal, execution, proof))
            proof_ok = not proof_errors
        if (validation.get("status") == "passed"
                and validation.get("formal_applicable") is True
                and selected_admission.get("proposal_sha256") == canonical_sha(existing_proposal)
                and proof_ok):
            return {"run_id": run_id, "proposal_sha256": file_sha(run_dir / "proposal.json"),
                    "selected": state.get("selected_candidate"),
                    "candidate_count": len(state.get("candidate_attempts") or {})}
        if not proof_ok:
            raise ValueError("selected MVG admission proof is missing, stale, or invalid")
    workspace_base = run_dir / "candidates"
    workspace_base.mkdir(parents=True, exist_ok=True)
    tool_sc_dir = Path(__file__).resolve().parents[1] / "sc"
    if str(tool_sc_dir) not in sys.path:
        sys.path.insert(0, str(tool_sc_dir))
    from _llm_backend import run_llm_exec

    runner_names = {
        "codex-cli": "codex_isolated_model_runner.py",
        "openai-api": "openai_isolated_model_runner.py",
        "copilot-cli": "copilot_isolated_model_runner.py",
    }
    runner = Path(__file__).resolve().with_name(runner_names[llm_backend])
    backend_info = inspect_isolated_runner(runner)

    known_task_ids = sorted(_task_ids(root))
    task_master = load_json(root / ".taskmaster/tasks/tasks.json", {})
    task_statuses = {str(row["id"]): str(row.get("status", "")).lower()
                     for row in task_master.get("master", {}).get("tasks", [])}
    known_non_done_ids = sorted(int(task_id) for task_id, status in task_statuses.items() if status != "done")
    source_manifest = load_json(root / SOURCE_MANIFEST, {})
    known_source_paths = sorted(str(row.get("path")) for row in source_manifest.get("sources", [])
                                if isinstance(row, dict) and str(row.get("path") or "").strip())
    known_contract_refs = sorted({str(value) for row in _task_view_rows(root)
                                  for value in _list_field(row, "contractRefs") if str(value).strip()})
    known_test_refs = sorted({str(value) for row in _task_view_rows(root)
                              for value in _list_field(row, "test_refs") if str(value).strip()})
    strict_contract = f"""
Deterministic validation reminders for the FULL replacement proposal:
- manifest_candidate.schema_version must be exactly newrouge.mvg-integration.v1.
- manifest_candidate.mvg_id and every flow/test id must be lowercase kebab-case strings.
- manifest_candidate must contain non-empty flows and tests arrays.
- coverage.mode must be exactly one of pilot, critical, full. For a minimal acceptance journey prefer pilot unless the evidence clearly supports a broader mode.
- manifest_candidate.coverage is mandatory with scope_id, required_flow_ids in exact flow order, blocking_task_ids, and non-empty excluded_claims.
- blocking_task_ids is derived ONLY from Taskmaster status in analysis-input/task-master.json: sorted unique referenced flow tasks whose status is not done, excluding dedicated integration owners that appear as owners but never producers/consumers across all flows. Planned entrypoints/tests and missing runtime evidence do not change Taskmaster status and must not add blockers. Never infer status from implementation obligations.
- Every flow requires id, outcome, task_ids, source_paths, handoffs, test_ids. task_ids and every handoff producer_task/consumer_task/owner_task are JSON integers, never quoted numeric strings.
- Every handoff requires producer_task, consumer_task, owner_task, contract_ref, non-empty behavior, and non-empty test_ids.
- Every test requires id, kind, state, path, selector, evidence_level, min_tests.
- dotnet tests require evidence_level=domain-integration and a Game.Core.Tests/... .cs path.
- Every dotnet selector must be a class name, never a test filter expression, method selector, wildcard, or comparison.
- gdunit tests require evidence_level=scene-method or engine-input and a Tests.Godot/tests/... .gd path.
- source_paths and contract_ref values in the formal manifest are original repository-relative paths, never analysis-input/... paths.
- Every planned entrypoint requires integer owner_task plus non-empty path, symbol, inputs, state, assertions, implementation_acceptance.
- coverage_table rows require a nonempty "rationale" string.
- The explicit capabilities.v1.json is the only Capability SSoT. Do not create or reassign Capability IDs from auxiliary evidence.
    Known Taskmaster IDs for this planning input: {known_task_ids}
Authoritative Taskmaster statuses: {json.dumps(task_statuses, sort_keys=True)}
The only known non-done Taskmaster IDs are: {known_non_done_ids}.
{"coverage.blocking_task_ids MUST be [] when this list is empty." if not known_non_done_ids else "Do not add a blocking task ID unless its Taskmaster status is non-done."}
Declared authoritative source paths: {known_source_paths}
Existing reviewed contract refs: {known_contract_refs}
Existing test refs: {known_test_refs}
Prefer these real refs instead of inventing alternatives. If a required real object does not exist, record a gap and use planning_status=draft.
"""
    planning_scope = state.get("planning_scope") if isinstance(state.get("planning_scope"), dict) else None
    if planning_scope is not None:
        strict_contract += """
This run has an immutable existing-manifest planning scope. The supplied manifest is the
cumulative target and must not be widened. Preserve exactly its flow IDs and test IDs;
do not add any Requirement, Capability, Task, source path, contract route or test outside
the listed scope. Requirements outside this scope are intentionally excluded by the
manifest's excluded_claims and must not be added to coverage_table.
Frozen manifest scope:
""" + json.dumps({key: planning_scope.get(key) for key in (
            "scope_id", "mode", "flow_ids", "requirement_ids", "capability_refs",
            "task_ids", "test_ids", "source_paths", "excluded_claims")}, ensure_ascii=False)
    prompt = PROMPT + "\n" + strict_contract
    state["generation_strategy"] = "independent-candidates-segmented" if segmented else "independent-candidates-single"
    state.setdefault("candidate_attempts", {})
    state.setdefault("candidate_admissions", {})
    state.setdefault("admission_events", [])
    atomic_json(run_path, state)
    state_lock = threading.Lock()

    def invoke_for(candidate_root: Path, attempt_root: Path, *,
                   candidate_label: str | None = None, lineage: str | None = None):
        def invoke(prompt_text: str, attempt: int, *, output_name: str | None = None,
                   output_schema_path: Path | None = None,
                   output_schema: dict[str, Any] | None = None) -> tuple[Path, dict[str, Any]]:
            invocation_number = (reserve_candidate_model_invocation(candidate_root, candidate_label, lineage)
                                 if candidate_label and lineage else None)
            relative_output = Path(output_name or f"proposal-attempt-{attempt}.json")
            prompt_stem = relative_output.with_suffix("").as_posix().replace("/", "-")
            # Equivalent to the former `llm_workspace = workspace / "llm-sandbox"`
            # layout, with the candidate and section identities made explicit.
            llm_workspace = attempt_root / "llm-sandbox" / f"attempt-{attempt}" / prompt_stem
            llm_workspace.mkdir(parents=True, exist_ok=True)
            admission_proposal = candidate_root / "admission-review" / "proposal.json"
            if not admission_proposal.is_file():
                admission_proposal = candidate_root / "proposal.json"
            if admission_proposal.is_file():
                shutil.copyfile(admission_proposal, llm_workspace / "proposal.json")
            admission_input = candidate_root / "admission-review" / "analysis-input"
            if not admission_input.is_dir():
                admission_input = candidate_root / "analysis-input"
            if admission_input.is_dir():
                shutil.copytree(admission_input, llm_workspace / "analysis-input", dirs_exist_ok=True)
            output = llm_workspace / relative_output.name
            if output_schema_path is not None and output_schema is not None:
                atomic_json(output_schema_path, output_schema)
            if runner is not None:
                prompt_path = llm_workspace / f"prompt-{attempt}-{prompt_stem}.txt"
                prompt_path.write_text(prompt_text, encoding="utf-8", newline="\n")
                receipt = run_isolated_model(
                    runner, workspace=llm_workspace, prompt_path=prompt_path,
                    output_path=output, timeout_sec=timeout_sec,
                    output_schema=output_schema_path,
                )
                return output, {"attempt": attempt, "invocation": invocation_number, "backend": llm_backend,
                                "backend_info": backend_info, "runner": runner.as_posix(),
                                "returncode": 0, "receipt": receipt}
            rc, stdout, cmd = run_llm_exec(
                backend=llm_backend, root=llm_workspace, prompt=prompt_text,
                output_last_message=output, timeout_sec=timeout_sec, codex_configs=[],
                output_schema=output_schema_path,
            )
            execution: dict[str, Any] = {"attempt": attempt, "invocation": invocation_number, "backend": llm_backend,
                                          "backend_info": backend_info, "command": cmd,
                                          "returncode": rc}
            try:
                trace = json.loads(stdout)
            except json.JSONDecodeError:
                trace = None
            if isinstance(trace, dict):
                execution["trace"] = trace
            else:
                execution["stdout_tail"] = stdout[-4000:]
            if rc != 0:
                raise RuntimeError(f"MVG planning model failed: {stdout[-2000:]}")
            return output, execution
        return invoke

    def generate_candidate(label: str) -> dict[str, Any]:
        prior_admission = state.get("candidate_admissions", {}).get(label) or {}
        lineage_hint = str(prior_admission.get("lineage") or f"{label}-r1")
        prior_admission = restore_admission_checkpoint(
            prior_admission, state.get("admission_events") or [],
            candidate=label, lineage=lineage_hint)
        if prior_admission.get("status") == "admitted":
            state["candidate_admissions"][label] = prior_admission
        if prior_admission.get("status") == "admitted":
            # An admitted candidate is immutable input to selection.  Reuse it
            # only when its proposal, deterministic validation and admission
            # proof are still readable and hash-bound. Artifact drift is an
            # execution-integrity failure, not a semantic reason to regenerate.
            admitted_proposal_path = None
            review_path = execution_path = None
            try:
                admitted_proposal_path, review_path, execution_path = _bound_admission_artifacts(
                    root, run_dir, prior_admission)
            except (OSError, ValueError):
                pass
            if (admitted_proposal_path is not None and admitted_proposal_path.is_file()
                    and review_path is not None and review_path.is_file()
                    and execution_path is not None and execution_path.is_file()):
                try:
                    admitted_proposal = load_json(admitted_proposal_path, {})
                    admitted_validation = validate_proposal(root, state, admitted_proposal)
                    admitted_review = load_json(review_path, {})
                    admitted_execution = load_json(execution_path, {})
                    from _mvg_planning_review import review_execution_errors
                    admitted_errors = candidate_admission_errors(
                        root, state, admitted_proposal, admitted_review)
                    admitted_errors.extend(review_execution_errors(
                        state, admitted_proposal, admitted_execution, admitted_review))
                    expected_sha = str(prior_admission.get("proposal_sha256") or "")
                    expected_proof_sha = str(prior_admission.get("proof_sha256") or "")
                    expected_execution_sha = str(prior_admission.get("execution_sha256") or "")
                    if not expected_sha or expected_sha != file_sha(admitted_proposal_path):
                        admitted_errors.append({"code": "admitted_proposal_hash_drift", "path": "proposal"})
                    if (not expected_proof_sha or file_sha(review_path) != expected_proof_sha
                            or not expected_execution_sha or file_sha(execution_path) != expected_execution_sha):
                        admitted_errors.append({"code": "admission_proof_hash_missing_or_drift", "path": "admission-review"})
                    if (admitted_validation.get("status") == "passed"
                            and admitted_validation.get("formal_applicable") is True
                            and not admitted_errors):
                        summary = state.get("candidate_attempts", {}).get(label) or {}
                        summary = dict(summary)
                        summary.update(status="valid", admission_status="admitted",
                                       proposal_sha256=file_sha(admitted_proposal_path),
                                       validation=admitted_validation,
                                       lineage=prior_admission.get("lineage"))
                        with state_lock:
                            state["candidate_attempts"][label] = summary
                            atomic_json(run_path, state)
                        return {"label": label, "valid": True, "admitted": True,
                                "proposal": admitted_proposal, "summary": summary}
                    integrity_error = ";".join(
                        str(row.get("code") or "invalid") for row in admitted_errors[:6]
                    ) or "admitted proposal failed formal validation"
                except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                    admitted_proposal = None
                    integrity_error = f"admitted artifact unreadable: {exc}"
            else:
                admitted_proposal = None
                integrity_error = "admission proof or admitted proposal is missing"
            failed_admission = dict(prior_admission)
            failed_admission.update(status="execution-failed", integrity_error=integrity_error)
            summary = dict(state.get("candidate_attempts", {}).get(label) or {})
            summary.update(status="execution-failed", admission_status="execution-failed",
                           admission_error={"error_type": "admission_artifact_integrity_failure",
                                            "error": integrity_error})
            with state_lock:
                state["candidate_admissions"][label] = failed_admission
                state["candidate_attempts"][label] = summary
                atomic_json(run_path, state)
            return {"label": label, "valid": False, "admitted": False,
                    "proposal": None, "summary": summary}
        # Terminal execution failures survive a crash between event and summary
        # publication; don't silently restart their model lineage on resume.
        if prior_admission.get("status") == "execution-failed":
            summary = dict(state.get("candidate_attempts", {}).get(label) or {})
            summary.update(status="execution-failed", admission_status="execution-failed",
                           admission_error=prior_admission.get("execution_error") or {})
            state["candidate_admissions"][label] = prior_admission
            state["candidate_attempts"][label] = summary
            with state_lock:
                atomic_json(run_path, state)
            return {"label": label, "valid": False, "admitted": False,
                    "proposal": None, "summary": summary}
        if prior_admission.get("status") == "retired":
            # Replacement accounting belongs to the outer durable round
            # budget. Do not allocate a new lineage here, which would let a
            # restarted process bypass that stop-loss.
            state["candidate_admissions"][label] = prior_admission
            summary = dict(state.get("candidate_attempts", {}).get(label) or {})
            summary.update(status="failed", admission_status="retired",
                           lineage=prior_admission.get("lineage"),
                           admission_issues=prior_admission.get("issues") or [])
            state["candidate_attempts"][label] = summary
            with state_lock:
                atomic_json(run_path, state)
            return {"label": label, "valid": False, "admitted": False,
                    "proposal": None, "summary": summary}
        lineage = str(prior_admission.get("lineage") or f"{label}-r1")
        candidate_root = workspace_base / (label if lineage == f"{label}-r1"
                                           else f"{label}--{lineage}")
        candidate_root.mkdir(parents=True, exist_ok=True)
        prepared = candidate_root / "analysis-input"
        if prepared.exists():
            shutil.rmtree(prepared)
        shutil.copytree(run_dir / "analysis-input", prepared)
        for name in ("coverage-skeleton.json", "entrypoint-skeleton.json"):
            source = prepared / name
            if source.is_file():
                shutil.copyfile(source, candidate_root / name)
        candidate_state = deepcopy(state)
        records = list((state.get("candidate_attempts", {}).get(label) or {}).get("attempts", []))
        proposal: dict[str, Any] | None = None
        validation: dict[str, Any] = {"status": "blocked", "errors": ["model_not_run"]}
        candidate_prompt = prompt
        # The old single-proposal path used `for attempt in (1, 2, 3)` and is
        # retained only for explicit segmented=False compatibility. The new
        # default spends exactly one fresh context per candidate label.
        # A fresh run gets one independent context per candidate.  On resume,
        # a candidate whose durable result is missing/invalid gets one bounded
        # fresh replacement context; already-valid siblings remain reusable.
        # Existing attempt slots are scanned first so a durable proposal can
        # recover across the output/journal write boundary. New invocations
        # still start after the persisted record count and remain bounded.
        attempt_numbers = candidate_resume_attempt_numbers(len(records), segmented=segmented)
        admission_runtime: dict[str, Any] = {
            "candidate": label, "lineage": lineage, "status": "admitting",
            "issues": list(prior_admission.get("issues") or []),
            "issue_attempts": dict(prior_admission.get("issue_attempts") or {}),
        }
        if admission_runtime["issues"]:
            admission_runtime["current_issue"] = admission_runtime["issues"][0]
            candidate_prompt = admission_repair_prompt(prompt, strict_contract, admission_runtime)
        admission_execution_error: dict[str, str] | None = None
        admission_review_path = candidate_root / "admission-review.json"
        admission_review = load_json(admission_review_path, None) if admission_review_path.is_file() else None
        admission_issues: list[dict[str, str]] = ([
            {"code": "proposal_missing", "path": "proposal"}
        ] if proposal is None else candidate_admission_errors(root, state, proposal, admission_review))

        def checkpoint_admission_issues(issues: list[dict[str, str]], attempt: int) -> None:
            nonlocal admission_runtime, candidate_prompt
            previous = admission_runtime.get("issues") or []
            previous_id = (admission_issue_id(str(previous[0].get("code") or "issue"),
                                              str(previous[0].get("path") or ""))
                           if previous and isinstance(previous[0], dict) else "")
            current_issue_ids = {
                admission_issue_id(str(issue.get("code") or "issue"), str(issue.get("path") or ""))
                for issue in issues if isinstance(issue, dict)
            }
            admission_runtime = advance_admission_state(
                admission_runtime, issues,
                repaired=bool(previous and previous_id not in current_issue_ids),
            )
            current_issue = admission_runtime.get("current_issue") or issues[0]
            with state_lock:
                state["candidate_admissions"][label] = dict(admission_runtime)
                state["admission_events"].append({
                    "candidate": label, "lineage": lineage, "attempt": attempt,
                    "event": "admission-issue", "issue": current_issue,
                    "issue_attempts": dict(admission_runtime.get("issue_attempts") or {}),
                    "status": admission_runtime.get("status"),
                })
                atomic_json(run_path, state)
            if admission_runtime.get("status") != "retired":
                candidate_prompt = admission_repair_prompt(PROMPT, strict_contract, admission_runtime)
            # Keep the legacy correction_prompt(errors) contract discoverable;
            # production segmented generation routes through the durable helper above.

        for attempt in attempt_numbers:
            if attempt <= len(records):
                # A process can terminate after the candidate output is
                # durable but before the shared run journal is updated. On
                # resume, recover and revalidate that output instead of
                # treating the already completed candidate as missing.
                prior = records[attempt - 1]
                if isinstance(prior, dict) and prior.get("status") in {"completed", "running"}:
                    prior_output = candidate_root / "proposal.json"
                    if not prior_output.is_file():
                        prior_output = candidate_root / f"proposal-attempt-{attempt}.json"
                    if prior_output.is_file():
                        try:
                            recovered = json.loads(prior_output.read_text(encoding="utf-8"))
                            if isinstance(recovered, dict):
                                normalize_proposal_format(recovered)
                                normalize_dotnet_selectors(root, recovered)
                                recovered_validation = validate_proposal(root, state, recovered)
                                proposal = recovered
                                validation = recovered_validation
                                if (recovered_validation.get("status") == "passed"
                                        and recovered_validation.get("formal_applicable") is True):
                                    admission_review = load_json(admission_review_path, None) if admission_review_path.is_file() else None
                                    if admission_review is None:
                                        try:
                                            admission_review = run_admission_semantic_gate(
                                                root, state, proposal, candidate_root / "admission-review",
                                                runner=runner, timeout_sec=timeout_sec,
                                                invoke=invoke_for(candidate_root, candidate_root / "model-workspace" / f"attempt-{attempt}",
                                                                  candidate_label=label, lineage=lineage),
                                                review_key=f"attempt-{attempt}",
                                                before_invoke=lambda: reserve_candidate_model_invocation(
                                                    candidate_root, label, lineage),
                                            )
                                            atomic_json(admission_review_path, admission_review)
                                        except MVGReviewAttemptBudgetError as exc:
                                            admission_execution_error = {
                                                "error_type": exc.error_type,
                                                "error": _compact_exception_message(exc),
                                            }
                                            break
                                        except (OSError, RuntimeError, TimeoutError, ValueError,
                                                json.JSONDecodeError) as exc:
                                            admission_execution_error = {
                                                "error_type": classify_review_error(exc),
                                                "error": _compact_exception_message(exc),
                                            }
                                            break
                                    if not candidate_admission_errors(root, state, proposal, admission_review):
                                        break
                                recovered_issues = candidate_admission_errors(
                                    root, state, proposal, admission_review)
                                if recovered_issues:
                                    checkpoint_admission_issues(recovered_issues, attempt)
                                    if admission_runtime.get("status") == "retired":
                                        break
                        except (OSError, ValueError, json.JSONDecodeError) as exc:
                            validation = {"status": "blocked", "errors": [str(exc)]}
                # A previously failed or formally inapplicable attempt may be
                # replaced once on resume. Do not copy its output into the
                # next context; the new invocation remains independent.
                continue
            attempt_root = candidate_root / "model-workspace" / f"attempt-{attempt}"
            attempt_root.mkdir(parents=True, exist_ok=True)
            shutil.copytree(prepared, attempt_root / "analysis-input")
            # A focused repair may read only the current lineage's proposal.
            # Keep it inside this attempt workspace and admission workspace;
            # replacement lineages use a different root and therefore cannot
            # inherit retired proposal/findings/prompts.
            if proposal is not None:
                atomic_json(attempt_root / "proposal.json", proposal)
                atomic_json(candidate_root / "admission-review" / "proposal.json", proposal)
            record: dict[str, Any] = {"candidate": label, "attempt": attempt,
                                      "status": "running", "backend": llm_backend}
            records.append(record)
            with state_lock:
                state["candidate_attempts"][label] = {"attempts": records}
                state["generation_attempts"] = [
                    {"candidate": name, "attempt_count": len((state["candidate_attempts"].get(name) or {}).get("attempts", [])),
                     "status": (state["candidate_attempts"].get(name) or {}).get("status", "pending")}
                    for name in MVG_CANDIDATE_LABELS if name in state["candidate_attempts"]
                ]
                atomic_json(run_path, state)
            try:
                invoke = invoke_for(candidate_root, attempt_root,
                                    candidate_label=label, lineage=lineage)
                if segmented:
                    output, execution = invoke_segmented(
                        invoke, candidate_root, candidate_state, attempt, candidate_prompt, attempt_root,
                        semantics=load_json(prepared / "semantic-requirements.v1.json", {}),
                        task_ids=[int(value) for value in state.get("task_scope", [])],
                        base_proposal=proposal,
                        planning_scope=state.get("planning_scope"),
                    )
                else:
                    output, execution = invoke(candidate_prompt, attempt)
                parsed = json.loads(output.read_text(encoding="utf-8").strip())
                if not isinstance(parsed, dict):
                    raise ValueError("MVG proposal must be an object")
                if not segmented and attempt > 1:
                    patch_errors = [] if is_restricted_patch(parsed) else ["restricted_patch_required"]
                    patch_errors.extend(validate_restricted_patch_identity(parsed, state))
                    if patch_errors:
                        raise ValueError("restricted patch invalid: " + ";".join(patch_errors))
                    proposal = apply_restricted_patch(proposal or {}, parsed)
                else:
                    proposal = parsed
                normalize_proposal_format(proposal)
                normalize_dotnet_selectors(root, proposal)
                # Every repaired proposal requires a fresh semantic admission
                # review bound to its new hash; never reuse the prior verdict.
                admission_review = None
                if admission_review_path.is_file():
                    admission_review_path.unlink()
                validation = validate_proposal(root, state, proposal)
                execution["proposal_sha256"] = canonical_sha(proposal)
                execution["deterministic_validation"] = validation
                record.update(execution, status="completed")
                atomic_json(candidate_root / f"proposal-attempt-{attempt}.json", proposal)
            except (RuntimeError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
                record.update(status="execution-failed", error=_compact_exception_message(exc),
                               error_type=classify_review_error(exc))
                validation = {"status": "blocked", "errors": [str(exc)]}
                state["phase"] = "generation-execution-blocked"
                if segmented:
                    admission_execution_error = {
                        "error_type": classify_review_error(exc),
                        "error": _compact_exception_message(exc),
                    }
            with state_lock:
                atomic_json(run_path, state)
                if admission_execution_error:
                    state["admission_events"].append({
                        "candidate": label, "lineage": lineage, "attempt": attempt,
                        "event": "admission-execution-failed",
                        "error": admission_execution_error,
                    })
                    atomic_json(run_path, state)
            if admission_execution_error:
                break
            ready_with_gaps = (validation.get("planning_status") == "ready_for_validation"
                               and validation.get("unresolved_gap_count", 0) > 0)
            if validation.get("status") == "passed" and not ready_with_gaps and segmented:
                if admission_review is None:
                    try:
                        admission_review = run_admission_semantic_gate(
                            root, state, proposal or {}, candidate_root / "admission-review",
                            runner=runner, timeout_sec=timeout_sec,
                            invoke=invoke_for(candidate_root, attempt_root,
                                              candidate_label=label, lineage=lineage),
                            review_key=f"attempt-{attempt}",
                            before_invoke=lambda: reserve_candidate_model_invocation(
                                candidate_root, label, lineage),
                        )
                        atomic_json(admission_review_path, admission_review)
                    except MVGReviewAttemptBudgetError as exc:
                        admission_execution_error = {
                            "error_type": getattr(exc, "error_type", "runner_execution_failed"),
                            "error": _compact_exception_message(exc),
                        }
                        admission_review = None
                        break
                    except (OSError, RuntimeError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
                        admission_execution_error = {
                            "error_type": classify_review_error(exc),
                            "error": _compact_exception_message(exc),
                        }
                        admission_review = None
                        break
                if not candidate_admission_errors(root, state, proposal or {}, admission_review):
                    break
            admission_issues = candidate_admission_errors(root, state, proposal or {}, admission_review) if proposal else [
                {"code": "proposal_missing", "path": "proposal"}
            ]
            if admission_execution_error:
                admission_issues = []
                break
            if not admission_issues:
                break
            if not segmented:
                candidate_prompt = admission_repair_prompt(
                    PROMPT, strict_contract,
                    {"issues": admission_issues, "current_issue": admission_issues[0]})
                continue
            # The initial generated proposal does not consume a repair attempt.
            checkpoint_admission_issues(admission_issues, attempt)
            if admission_runtime.get("status") == "retired":
                break
        if admission_issues and len(records) >= MVG_CANDIDATE_ATTEMPT_LIMIT:
            admission_execution_error = {
                "error_type": "candidate_attempt_budget_exhausted",
                "error": f"candidate lineage reached {MVG_CANDIDATE_ATTEMPT_LIMIT} attempts with hard issues remaining",
            }
        # A structurally valid draft or unresolved-gap proposal is evidence
        # only. It must never enter comparative selection as a viable winner.
        admission_review = load_json(admission_review_path, None) if admission_review_path.is_file() else None
        admission_issues = candidate_admission_errors(root, state, proposal or {}, admission_review) if proposal else [
            {"code": "proposal_missing", "path": "proposal"}
        ]
        review_attempt = _admission_execution_artifact(
            candidate_root / "admission-review", f"attempt-{attempt}") if segmented else None
        if segmented and not admission_execution_error:
            if admission_review is None or review_attempt is None:
                admission_execution_error = {
                    "error_type": "candidate_admission_evidence_missing",
                    "error": "semantic admission proof or published execution receipt is missing",
                }
            else:
                from _mvg_planning_review import review_execution_errors
                execution = load_json(review_attempt, {})
                execution_errors = review_execution_errors(state, proposal or {}, execution, admission_review)
                if execution_errors:
                    admission_execution_error = {
                        "error_type": "candidate_admission_execution_identity_invalid",
                        "error": ";".join(execution_errors),
                    }
        valid = bool(proposal and not admission_execution_error and not admission_issues
                     and validation.get("status") == "passed"
                     and validation.get("formal_applicable") is True)
        if valid:
            atomic_json(candidate_root / "proposal.json", proposal)
        admission = {"candidate": label, "lineage": lineage,
                     "status": "admitted" if valid else (
                         "execution-failed" if admission_execution_error else "retired"),
                     "issues": admission_issues,
                     "issue_attempts": admission_runtime.get("issue_attempts", {}),
                     "attempt_count": len(records), "workspace": candidate_root.relative_to(run_dir).as_posix(),
                     "execution_error": admission_execution_error,
                     "proposal_sha256": file_sha(candidate_root / "proposal.json")
                     if valid and (candidate_root / "proposal.json").is_file() else None}
        if valid and admission_review is not None:
            admission["review_path"] = (candidate_root / "admission-review.json").relative_to(root).as_posix()
            if review_attempt is not None:
                admission["review_execution_path"] = review_attempt.relative_to(root).as_posix()
                admission["proof_sha256"] = file_sha(candidate_root / "admission-review.json")
                admission["execution_sha256"] = file_sha(review_attempt)
        with state_lock:
            state["admission_events"].append({
                "candidate": label, "lineage": lineage,
                "event": "candidate-admitted" if valid else (
                    "admission-execution-failed" if admission_execution_error else "candidate-retired"),
                "attempt_count": len(records), "issues": admission_issues,
                "issue_attempts": dict(admission_runtime.get("issue_attempts") or {}),
                "error": admission_execution_error,
                "retirement_reason": admission_runtime.get("retirement_reason") if not valid else None,
                "admission": admission,
            })
            atomic_json(run_path, state)
        summary = {"status": "valid" if valid else "failed", "attempts": records,
                   "attempt_count": len(records), "validation": validation,
                   "admission_status": admission["status"], "admission_issues": admission_issues,
                   "lineage": lineage}
        if admission_execution_error:
            summary.update(status="execution-failed", admission_status="execution-failed",
                           admission_error=admission_execution_error)
        if valid:
            atomic_json(candidate_root / "proposal.json", proposal)
            summary["proposal_sha256"] = file_sha(candidate_root / "proposal.json")
        with state_lock:
            state["candidate_attempts"][label] = summary
            state["candidate_admissions"][label] = admission
            state["generation_attempts"] = [
                {"candidate": name, "attempt_count": int((state["candidate_attempts"].get(name) or {}).get("attempt_count", 0)),
                 "status": (state["candidate_attempts"].get(name) or {}).get("status", "pending")}
                for name in MVG_CANDIDATE_LABELS if name in state["candidate_attempts"]
            ]
            atomic_json(run_path, state)
        return {"label": label, "valid": valid, "admitted": valid, "proposal": proposal,
                "summary": state["candidate_attempts"][label]}

    if not segmented:
        # Explicit legacy callers retain the old single-proposal correction
        # contract. The production/default path below is always A/B/C plus D.
        legacy = generate_candidate("candidate-1")
        # Preserve the legacy durable attempt list shape for explicit
        # segmented=False callers and their recovery diagnostics.
        state["generation_attempts"] = legacy["summary"]["attempts"]
        atomic_json(run_path, state)
        if not legacy["valid"]:
            raise ValueError("MVG independent candidate generation attempt budget exhausted; incomplete: candidate-1")
        atomic_json(run_dir / "proposal.json", legacy["proposal"])
        state.update(
            phase="generated", selection_status="legacy-single", selected_candidate="candidate-1",
            model_backend=llm_backend,
            model_execution={"path": (run_dir / "model-execution.json").relative_to(root).as_posix(),
                              "backend": llm_backend,
                              "candidate_count": 1,
                              "attempt_count": legacy["summary"]["attempt_count"]},
        )
        atomic_json(run_dir / "model-execution.json", {
            "schema_version": "newrouge.mvg-planning-model-execution.v1",
            "backend": llm_backend, "candidate_attempts": state["candidate_attempts"],
            "selection_status": "legacy-single", "selected_candidate": "candidate-1",
        })
        atomic_json(run_path, state)
        return {"run_id": run_id, "proposal_sha256": file_sha(run_dir / "proposal.json"),
                "selected": "candidate-1", "candidate_count": 1,
                "attempt_count": legacy["summary"]["attempt_count"]}

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(MVG_CANDIDATE_LABELS)) as executor:
        futures = [executor.submit(generate_candidate, label) for label in MVG_CANDIDATE_LABELS]
        results = [future.result() for future in futures]
    execution_failures = [row for row in results
                          if (row.get("summary") or {}).get("admission_status") == "execution-failed"]
    if execution_failures:
        state["phase"] = "candidate-admission-execution-blocked"
        state["selection_status"] = "blocked"
        state["admission_stop_reason"] = "runner_or_input_failure"
        atomic_json(run_path, state)
        labels = ",".join(str(row.get("label")) for row in execution_failures)
        raise ValueError("MVG candidate admission stopped on runner/input failure; recoverable state preserved: " + labels)
    # Retired slots are replenished with a clean replacement lineage. The
    # replacement context is rebuilt from the immutable prepared bundle and
    # never receives the retired proposal, findings or repair prompt.
    replacement_round = int(state.get("replacement_rounds_used", 0) or 0)
    while len([row for row in results if row.get("admitted")]) < len(MVG_CANDIDATE_LABELS):
        reserved_round = reserve_replacement_round(state)
        if reserved_round is None:
            state["phase"] = "candidate-admission-replacement-budget-exhausted"
            state["selection_status"] = "blocked"
            state["admission_stop_reason"] = "replacement_round_budget_exhausted"
            atomic_json(run_path, state)
            raise ValueError(
                "MVG candidate replacement budget exhausted; admitted candidates: "
                + str(len([row for row in results if row.get("admitted")]))
            )
        replacement_round = reserved_round
        changed = False
        for index, row in enumerate(list(results)):
            if row.get("admitted"):
                continue
            label = str(row.get("label") or "")
            retired = state.get("candidate_admissions", {}).get(label) or {
                "candidate": label, "lineage": f"{label}-r{replacement_round}"
            }
            replacement = fresh_replacement_lineage(retired, label)
            state["candidate_admissions"][label] = replacement
            state["candidate_attempts"].pop(label, None)
            state["admission_events"].append({
                "candidate": label, "lineage": replacement["lineage"],
                "replacement_of": replacement.get("replacement_of"),
                "event": "replacement-started",
            })
            with state_lock:
                atomic_json(run_path, state)
            replacement_result = generate_candidate(label)
            results[index] = replacement_result
            changed = True
            if (replacement_result.get("summary") or {}).get("admission_status") == "execution-failed":
                break
        if not changed:
            break
        if any((row.get("summary") or {}).get("admission_status") == "execution-failed" for row in results):
            break
    valid_results = [row for row in results if row.get("admitted")]
    state["admitted_candidates"] = [str(row.get("label")) for row in valid_results]
    state["retired_candidates"] = [str(row.get("label")) for row in results if not row.get("admitted")]
    if len(valid_results) != len(MVG_CANDIDATE_LABELS):
        atomic_json(run_dir / "model-execution.json", {
            "schema_version": "newrouge.mvg-planning-model-execution.v1",
            "backend": llm_backend, "candidate_attempts": state["candidate_attempts"],
            "selection_status": "blocked", "selection_error": "all three independent candidates must be valid",
        })
        reasons = []
        for row in results:
            if row.get("admitted"):
                continue
            summary = row.get("summary") or {}
            validation_errors = (summary.get("validation") or {}).get("errors") or []
            attempt_errors = [str(item.get("error") or "") for item in (summary.get("attempts") or [])
                              if isinstance(item, dict) and item.get("error")]
            detail = ";".join(str(value) for value in (validation_errors or attempt_errors)[:4])
            reasons.append(f"{row['label']}={_compact_exception_message(detail or 'unknown_candidate_failure', 500)}")
        raise ValueError("MVG independent candidate generation attempt budget exhausted; incomplete: "
                         + ",".join(row["label"] for row in results if not row["valid"])
                         + ("; reasons: " + " | ".join(reasons) if reasons else ""))

    existing_manifest = load_json(run_dir / "analysis-input/existing-manifest.json", None)
    incumbent_present = isinstance(existing_manifest, dict) and existing_manifest.get("schema_version") == "newrouge.mvg-integration.v1"
    incumbent_valid = incumbent_present
    incumbent_proposal = None
    if incumbent_present:
        incumbent_proposal = _build_incumbent_proposal(root, run_dir, state, existing_manifest)
        incumbent_validation = validate_proposal(root, state, incumbent_proposal)
        incumbent_errors = incumbent_validation["errors"]
        if incumbent_errors:
            # Keep an invalid incumbent in the comparative review as D so the
            # evaluator sees the real baseline; deterministic selection below
            # forbids retaining it until its defects are resolved.
            incumbent_valid = False
            state["incumbent_rejected"] = incumbent_errors or incumbent_validation.get("formal_blockers", [])
        else:
            incumbent_workspace = run_dir / "incumbent-admission"
            try:
                incumbent_review = run_admission_semantic_gate(
                    root, state, incumbent_proposal, incumbent_workspace,
                    runner=runner, timeout_sec=timeout_sec,
                    invoke=invoke_for(incumbent_workspace, incumbent_workspace / "model-workspace"),
                    review_key="incumbent",
                )
                atomic_json(incumbent_workspace / "semantic-review.json", incumbent_review)
                incumbent_errors = candidate_admission_errors(root, state, incumbent_proposal, incumbent_review)
                incumbent_execution = _admission_execution_artifact(incumbent_workspace, "incumbent")
                if incumbent_execution is None:
                    incumbent_errors.append({"code": "incumbent_admission_execution_missing",
                                             "path": "semantic-review-execution"})
                else:
                    from _mvg_planning_review import review_execution_errors
                    incumbent_errors.extend({"code": error, "path": "semantic-review-execution"}
                        for error in review_execution_errors(
                            state, incumbent_proposal,
                            load_json(incumbent_execution, {}), incumbent_review))
                if incumbent_errors:
                    incumbent_valid = False
                    state["incumbent_rejected"] = incumbent_errors
            except MVGReviewAttemptBudgetError as exc:
                state["phase"] = "incumbent-admission-execution-blocked"
                state["selection_status"] = "blocked"
                state["admission_stop_reason"] = "incumbent_runner_or_input_failure"
                state["incumbent_rejected"] = [{"code": "incumbent_semantic_runner_failure", "path": str(exc)}]
                atomic_json(run_path, state)
                raise ValueError("MVG incumbent admission stopped on runner/input failure: " + str(exc)) from exc
            except (OSError, RuntimeError, TimeoutError, ValueError, TypeError, json.JSONDecodeError) as exc:
                state["phase"] = "incumbent-admission-execution-blocked"
                state["selection_status"] = "blocked"
                state["admission_stop_reason"] = classify_review_error(exc)
                state["incumbent_rejected"] = [{"code": "incumbent_admission_evidence_invalid",
                                                "path": _compact_exception_message(exc)}]
                state.setdefault("admission_events", []).append({
                    "candidate": "incumbent", "event": "admission-execution-failed",
                    "error": {"error_type": state["admission_stop_reason"],
                              "error": _compact_exception_message(exc)},
                })
                atomic_json(run_path, state)
                raise ValueError("MVG incumbent admission evidence failed validation: "
                                 + _compact_exception_message(exc)) from exc
    state["incumbent_present"] = incumbent_present
    state["incumbent_valid"] = incumbent_valid
    selection_incumbent_present = incumbent_present and incumbent_valid
    selection_dir = run_dir / "selection-workspace"
    selection_dir.mkdir(parents=True, exist_ok=True)
    stored_mapping = state.get("selection_anonymous_mapping")
    if (isinstance(stored_mapping, dict)
            and set(stored_mapping) == {"A", "B", "C"}
            and set(stored_mapping.values()) == set(MVG_CANDIDATE_LABELS)):
        aliases = {str(key): str(value) for key, value in stored_mapping.items()}
    else:
        shuffled_labels = list(MVG_CANDIDATE_LABELS)
        shuffle_seed = int(canonical_sha({
            "analysis_identity_sha256": state["analysis_identity_sha256"],
            "run_id": run_id,
        }).split(":", 1)[-1][:16], 16)
        random.Random(shuffle_seed).shuffle(shuffled_labels)
        aliases = dict(zip(("A", "B", "C"), shuffled_labels))
    state["selection_anonymous_mapping"] = {alias: label for alias, label in aliases.items()}
    state["selection_input_candidates"] = list(state["admitted_candidates"])
    for alias, label in aliases.items():
        candidate_summary = state.get("candidate_admissions", {}).get(label) or {}
        if candidate_summary.get("status") != "admitted":
            raise ValueError(f"selector candidate is not admitted: {label}")
        try:
            source_proposal, review_path, execution_path = _bound_admission_artifacts(
                root, run_dir, candidate_summary)
        except (OSError, ValueError) as exc:
            raise ValueError(f"selector candidate workspace is invalid: {label}") from exc
        if not source_proposal.is_file():
            raise ValueError(f"selector candidate proposal is missing: {label}")
        expected_proposal_sha = str(candidate_summary.get("proposal_sha256") or "")
        if expected_proposal_sha and file_sha(source_proposal) != expected_proposal_sha:
            raise ValueError(f"selector candidate proposal identity drift: {label}")
        candidate_proposal = load_json(source_proposal, {})
        candidate_validation = validate_proposal(root, state, candidate_proposal)
        if not review_path.is_file() or not execution_path.is_file():
            raise ValueError(f"selector admission proof is incomplete: {label}")
        expected_proof_sha = str(candidate_summary.get("proof_sha256") or "")
        expected_execution_sha = str(candidate_summary.get("execution_sha256") or "")
        if (not expected_proof_sha or file_sha(review_path) != expected_proof_sha
                or not expected_execution_sha or file_sha(execution_path) != expected_execution_sha):
            raise ValueError(f"selector admission proof identity drift: {label}")
        candidate_review = load_json(review_path, {})
        candidate_execution = load_json(execution_path, {})
        candidate_errors = candidate_admission_errors(root, state, candidate_proposal, candidate_review)
        from _mvg_planning_review import review_execution_errors
        candidate_errors.extend(review_execution_errors(
            state, candidate_proposal, candidate_execution, candidate_review))
        if candidate_validation.get("status") != "passed" or candidate_validation.get("formal_applicable") is not True:
            candidate_errors.append({"code": "candidate_formal_validation_failed", "path": "proposal"})
        if candidate_errors:
            raise ValueError(f"selector candidate admission proof is invalid: {label}")
        shutil.copyfile(source_proposal, selection_dir / f"{alias}.json")
    if selection_incumbent_present and incumbent_proposal is not None:
        atomic_json(selection_dir / "D.json", incumbent_proposal)
    candidate_hashes = {
        alias: file_sha(selection_dir / f"{alias}.json")
        for alias in (("A", "B", "C", "D") if selection_incumbent_present else ("A", "B", "C"))
    }
    selection_input_identity, selection_input_sha256 = build_selection_input_identity(
        state["analysis_identity_sha256"], candidate_hashes,
        {
            label: (state.get("candidate_admissions", {}).get(label) or {}).get("lineage")
            for label in MVG_CANDIDATE_LABELS
        },
        incumbent_present=selection_incumbent_present,
    )
    state["selection_input_identity"] = selection_input_identity
    state["selection_input_sha256"] = selection_input_sha256
    atomic_json(run_path, state)
    selection_prompt = mvg_selection_prompt(
        incumbent_present=selection_incumbent_present,
        planning_scope=state.get("planning_scope") if isinstance(state.get("planning_scope"), dict) else None,
    )
    selection_attempts = state.setdefault("selection_attempts", [])
    selection_result: dict[str, Any] | None = None
    selection_errors: list[str] = []
    viable_labels = {alias for alias, label in aliases.items()
                     if label in {row["label"] for row in valid_results}}
    viable_selection_labels = {aliases[alias] for alias in viable_labels}
    if incumbent_valid:
        viable_selection_labels.add("incumbent")
    # If selection.json was durably written before the run journal update, use
    # that exact artifact instead of consuming another selector attempt. Scan
    # the bounded attempt directories, including records still marked running.
    selection_candidates = set()
    for completed in selection_attempts:
        if isinstance(completed, dict):
            try:
                selection_candidates.add(int(completed.get("attempt")))
            except (TypeError, ValueError):
                pass
    selection_candidates.update(
        int(match.group(1)) for path in selection_dir.glob("attempt-*/selection.json")
        if (match := re.search(r"attempt-(\d+)$", path.parent.name))
    )
    for completed_number in sorted(selection_candidates, reverse=True):
        completed_output = selection_dir / f"attempt-{completed_number}" / "selection.json"
        if not completed_output.is_file():
            continue
        receipt_path = selection_dir / f"attempt-{completed_number}" / "selection-receipt.json"
        receipt = load_json(receipt_path, {})
        if (receipt.get("selection_input_sha256") != selection_input_sha256
                or receipt.get("output_sha256") != file_sha(completed_output)):
            continue
        recorded = next((row for row in selection_attempts
                         if isinstance(row, dict) and str(row.get("attempt")) == str(completed_number)), {})
        if (recorded.get("selection_input_sha256")
                and recorded.get("selection_input_sha256") != selection_input_sha256):
            continue
        if recorded.get("output_sha256") and recorded.get("output_sha256") != file_sha(completed_output):
            raise ValueError("selection artifact identity drift")
        try:
            recovered_selection = load_json(completed_output, {})
            recovered_receipt = receipt
            recovered_errors = validate_mvg_selection(
                recovered_selection, candidate_labels=set(MVG_CANDIDATE_LABELS),
                incumbent_present=selection_incumbent_present, alias_mapping=aliases,
                viable_labels=viable_selection_labels)
            recovered_errors.extend(validate_selection_execution_receipt(
                state, recovered_selection, recovered_receipt,
                selection_input_sha256=selection_input_sha256,
                output_sha256=file_sha(completed_output),
                expected_attempt=completed_number))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            recovered_errors = [str(exc)]
        if not recovered_errors:
            selection_result = recovered_selection
            recorded.update(status="completed", output_sha256=file_sha(completed_output),
                            recovered_from_receipt=True)
            atomic_json(run_path, state)
            break
    for attempt in range(len(selection_attempts) + 1, MVG_SELECTION_ATTEMPT_LIMIT + 1):
        if selection_result is not None:
            break
        attempt_dir = selection_dir / f"attempt-{attempt}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        selection_input = attempt_dir / "analysis-input"
        if selection_input.exists():
            shutil.rmtree(selection_input)
        shutil.copytree(run_dir / "analysis-input", selection_input)
        for alias in ("A", "B", "C", "D"):
            source = selection_dir / f"{alias}.json"
            if source.is_file():
                shutil.copyfile(source, attempt_dir / f"{alias}.json")
        output = attempt_dir / "selection.json"
        schema_path = attempt_dir / "selection-output-schema.json"
        atomic_json(schema_path, mvg_selection_output_schema(incumbent_present=selection_incumbent_present))
        prompt_path = attempt_dir / "prompt.txt"
        prompt_path.write_text(selection_prompt, encoding="utf-8", newline="\n")
        record: dict[str, Any] = {"attempt": attempt, "status": "running", "backend": llm_backend,
                                  "runner_info": backend_info,
                                  "selection_input_sha256": selection_input_sha256,
                                  "selection_input_identity": selection_input_identity}
        selection_attempts.append(record)
        atomic_json(run_path, state)
        try:
            if runner is not None:
                receipt = run_isolated_model(runner, workspace=attempt_dir, prompt_path=prompt_path,
                                             output_path=output, timeout_sec=timeout_sec,
                                             output_schema=schema_path)
                record["receipt"] = receipt
            else:
                rc, stdout, command = run_llm_exec(
                    backend=llm_backend, root=attempt_dir, prompt=selection_prompt,
                    output_last_message=output, timeout_sec=timeout_sec, codex_configs=[],
                    output_schema=schema_path,
                )
                record.update(returncode=rc, command=command, stdout_tail=stdout[-2000:])
                if rc != 0:
                    raise RuntimeError(f"MVG selection model failed: {stdout[-2000:]}")
            selection_result = parse_model_json(output)
            selection_errors = validate_mvg_selection(
                selection_result, candidate_labels=set(MVG_CANDIDATE_LABELS),
                incumbent_present=selection_incumbent_present, alias_mapping=aliases,
                viable_labels=viable_selection_labels,
            )
            if selection_errors:
                raise ValueError("MVG selection output invalid: " + ";".join(selection_errors))
            record.update(status="completed", output_sha256=file_sha(output))
            selection_receipt = {
                "schema_version": "newrouge.mvg-selection-execution-receipt.v1",
                "attempt": attempt,
                "backend": llm_backend,
                "analysis_identity_sha256": state["analysis_identity_sha256"],
                "selection_input_sha256": selection_input_sha256,
                "output_sha256": file_sha(output),
                "runner_info": backend_info,
                "runner_receipt": record.get("receipt"),
                "returncode": record.get("returncode"),
            }
            atomic_json(attempt_dir / "selection-receipt.json", selection_receipt)
            receipt_errors = validate_selection_execution_receipt(
                state, selection_result,
                selection_receipt,
                selection_input_sha256=selection_input_sha256,
                output_sha256=file_sha(output),
                expected_attempt=attempt,
            )
            if receipt_errors:
                raise ValueError("MVG selection execution receipt invalid: " + ";".join(receipt_errors))
            break
        except (OSError, RuntimeError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            selection_result = None
            selection_errors = [str(exc)]
            record.update(status="execution-failed", error=_compact_exception_message(exc),
                          error_type=classify_review_error(exc))
        finally:
            atomic_json(run_path, state)
    if selection_result is None:
        state["phase"] = "selection-blocked"
        atomic_json(run_path, state)
        raise ValueError("MVG comparative selection failed after bounded attempts: " + ";".join(selection_errors))
    atomic_json(run_dir / "selection-review.json", selection_result)
    selected_alias = selection_result.get("selected")
    if selected_alias in aliases:
        selected_label = aliases[selected_alias]
        selected_meta = state.get("candidate_admissions", {}).get(selected_label) or {}
        selected_root = run_dir / str(selected_meta.get("workspace")) if selected_meta.get("workspace") \
            else workspace_base / selected_label
        selected_proposal = load_json(selected_root / "proposal.json", {})
        selected_admission = state.get("candidate_admissions", {}).get(selected_label) or {}
    elif selected_alias == "D" and incumbent_proposal is not None and incumbent_valid:
        selected_label = "incumbent"
        selected_proposal = incumbent_proposal
        incumbent_root = run_dir / "incumbent-admission"
        incumbent_execution = _admission_execution_artifact(
            incumbent_root, "incumbent")
        incumbent_review = incumbent_root / "semantic-review.json"
        if incumbent_execution is None or not incumbent_review.is_file():
            raise ValueError("selected incumbent admission proof or execution receipt is missing")
        selected_admission = {
            "candidate": "incumbent", "lineage": "incumbent-r1", "status": "admitted",
            "workspace": incumbent_root.relative_to(run_dir).as_posix(),
            "proposal_sha256": canonical_sha(selected_proposal),
            "review_path": incumbent_review.relative_to(root).as_posix(),
            "review_execution_path": incumbent_execution.relative_to(root).as_posix(),
            "proof_sha256": file_sha(incumbent_review),
            "execution_sha256": file_sha(incumbent_execution),
        }
        state.setdefault("candidate_admissions", {})["incumbent"] = selected_admission
    else:
        raise ValueError("MVG comparative selection returned no usable winner")
    atomic_json(run_dir / "proposal.json", selected_proposal)
    if selected_admission.get("review_path") and selected_admission.get("review_execution_path"):
        proof_file = repo_path(root, selected_admission["review_path"])
        execution_file = repo_path(root, selected_admission["review_execution_path"])
        state["selected_admission_review"] = {
            "path": selected_admission["review_path"],
            "execution_path": selected_admission["review_execution_path"],
            "proposal_sha256": canonical_sha(selected_proposal),
            "proof_sha256": file_sha(proof_file) if proof_file.is_file() else None,
            "execution_sha256": file_sha(execution_file) if execution_file.is_file() else None,
        }
    state.update(
        phase="generated", selection_status="selected", selected_candidate=selected_label,
        selection_alias=selected_alias, selection_path="selection-review.json",
        selection_schema=MVG_SELECTION_SCHEMA, model_backend=llm_backend,
        model_execution={"path": (run_dir / "model-execution.json").relative_to(root).as_posix(),
                          "backend": llm_backend,
                          "candidate_count": len(valid_results),
                          "attempt_count": sum(int(row["summary"].get("attempt_count", 0)) for row in results),
                          "selection_attempt_count": len(selection_attempts),
                          "incumbent_present": selection_incumbent_present,
                          "incumbent_valid": incumbent_valid},
    )
    atomic_json(run_dir / "model-execution.json", {
        "schema_version": "newrouge.mvg-planning-model-execution.v1",
        "backend": llm_backend, "candidate_attempts": state["candidate_attempts"],
        "selection_attempts": selection_attempts, "selected_alias": selected_alias,
        "selected_candidate": selected_label,
        "incumbent_present": selection_incumbent_present, "incumbent_valid": incumbent_valid,
    })
    atomic_json(run_path, state)
    return {"run_id": run_id, "proposal_sha256": file_sha(run_dir / "proposal.json"),
            "selected": selected_label, "selection_alias": selected_alias,
            "candidate_count": len(valid_results),
            "attempt_count": state["model_execution"]["attempt_count"]}

def validate_proposal(root: Path, state: dict[str, Any], proposal: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if proposal.get("schema_version") != PROPOSAL_SCHEMA:
        errors.append("invalid_proposal_schema")
    if proposal.get("analysis_identity_sha256") != state.get("analysis_identity_sha256"):
        errors.append("analysis_identity_mismatch")
    planning_status = str(proposal.get("planning_status") or "").strip()
    if planning_status not in {"draft", "ready_for_validation"}:
        errors.append("invalid_planning_status")
    gaps = proposal.get("gaps")
    if not isinstance(gaps, list):
        errors.append("gaps_not_array")
        gaps = []
    manifest = proposal.get("manifest_candidate")
    if not isinstance(manifest, dict):
        return {"status": "blocked", "errors": errors + ["manifest_candidate_missing"]}

    errors.extend(validate_manifest(root, manifest, executable=False))
    prepared = _run_dir(root, str(state.get("run_id"))) / "analysis-input"
    # Validate against the byte-bound prepared snapshot. The selected local
    # Capability is the planning SSoT; live auxiliary files cannot drift into
    # a candidate after prepare.
    capabilities = load_json(prepared / "capabilities.v1.json", None)
    if not isinstance(capabilities, dict) or capabilities.get("schema_version") != "newrouge.capabilities.v1":
        # Production runs always carry a frozen Capability fingerprint. Never
        # replace a missing/corrupt snapshot with the live workspace file: that
        # would let auxiliary edits or another Capability version cross the
        # prepared run boundary. Minimal legacy fixtures predate this state
        # field and retain the compatibility fallback only for their tests.
        if state.get("capabilities_sha256"):
            errors.append("prepared_capability_snapshot_missing")
            capabilities = {}
        else:
            capabilities = load_json(root / str(state["capabilities_path"]), {})
    known_caps = {
        str(row.get("capability_id"))
        for row in capabilities.get("capabilities", [])
        if isinstance(row, dict)
    }
    semantics = load_json(prepared / "semantic-requirements.v1.json", None)
    if not isinstance(semantics, dict) or not isinstance(semantics.get("requirements"), list):
        if state.get("capabilities_sha256"):
            errors.append("prepared_semantic_requirements_snapshot_missing")
            semantics = {"requirements": []}
        else:
            semantics = load_json(root / SEMANTICS, {})
    known_requirements = {
        str(row.get("requirement_id"))
        for row in semantics.get("requirements", [])
        if isinstance(row, dict)
    }
    task_master = load_json(prepared / "task-master.json", None)
    if not isinstance(task_master, dict):
        if state.get("capabilities_sha256"):
            errors.append("prepared_task_master_snapshot_missing")
            task_master = {"master": {"tasks": []}}
        else:
            task_master = load_json(root / ".taskmaster/tasks/tasks.json", {})
    known_tasks = {
        int(row["id"])
        for row in (task_master.get("master", {}) or {}).get("tasks", [])
        if isinstance(row, dict) and type(row.get("id")) is int
    }
    prepared_task_views: list[dict[str, Any]] = []
    for name in ("tasks_back.json", "tasks_gameplay.json"):
        payload = load_json(prepared / "task-views" / name, None)
        if not isinstance(payload, list):
            if state.get("capabilities_sha256"):
                errors.append(f"prepared_task_view_snapshot_missing:{name}")
                payload = []
            else:
                payload = load_json(root / ".taskmaster/tasks" / name, [])
        if isinstance(payload, list):
            prepared_task_views.extend(row for row in payload if isinstance(row, dict))
    from _mvg_planning_review import coverage_errors, prepared_evidence_errors
    planning_scope = state.get("planning_scope") if isinstance(state.get("planning_scope"), dict) else None
    scoped_requirement_ids = (set(planning_scope.get("requirement_ids", []))
                              if planning_scope is not None else None)
    errors.extend(coverage_errors(root, proposal, semantics, capabilities, prepared_task_views,
                                  scoped_requirement_ids))
    errors.extend(prepared_evidence_errors(root, proposal, prepared))
    for flow in manifest.get("flows", []):
        if not isinstance(flow, dict):
            continue
        for cid in flow.get("capability_refs", []):
            if str(cid) not in known_caps:
                errors.append(f"unknown_capability_ref:{cid}")
        for rid in flow.get("requirement_ids", []):
            if str(rid) not in known_requirements:
                errors.append(f"unknown_requirement_ref:{rid}")
        for tid in flow.get("task_ids", []):
            if type(tid) is not int or tid not in known_tasks:
                errors.append(f"unknown_task_id:{tid}")
    if planning_scope is not None:
        def scope_error(kind: str, value: Any) -> None:
            errors.append(f"manifest_scope_violation:{kind}:{value}")
        allowed = planning_scope
        allowed_flows = set(allowed.get("flow_ids", []))
        allowed_requirements = set(allowed.get("requirement_ids", []))
        allowed_capabilities = set(allowed.get("capability_refs", []))
        allowed_tasks = set(allowed.get("task_ids", []))
        allowed_tests = set(allowed.get("test_ids", []))
        allowed_sources = set(allowed.get("source_paths", []))
        allowed_contracts = set(allowed.get("contract_refs", []))
        allowed_test_paths = set(allowed.get("test_paths", []))
        actual_flows = {str(row.get("id")) for row in manifest.get("flows", []) if isinstance(row, dict)}
        for flow_id in sorted(actual_flows - allowed_flows):
            scope_error("flow", flow_id)
        for required in sorted(allowed_flows - actual_flows):
            scope_error("missing_flow", required)
        for flow in manifest.get("flows", []):
            if not isinstance(flow, dict):
                continue
            for value in flow.get("requirement_ids", []):
                if str(value) not in allowed_requirements:
                    scope_error("requirement", value)
            for value in flow.get("capability_refs", []):
                if str(value) not in allowed_capabilities:
                    scope_error("capability", value)
            for value in flow.get("task_ids", []):
                if type(value) is not int or value not in allowed_tasks:
                    scope_error("task", value)
            for value in flow.get("test_ids", []):
                if str(value) not in allowed_tests:
                    scope_error("test", value)
            for value in flow.get("source_paths", []):
                if str(value).replace("\\", "/") not in allowed_sources:
                    scope_error("source", value)
            for handoff in flow.get("handoffs", []):
                if isinstance(handoff, dict):
                    contract = str(handoff.get("contract_ref") or "").split("#", 1)[0].replace("\\", "/")
                    if contract not in allowed_contracts:
                        scope_error("contract", contract)
                    for extra in handoff.get("contract_refs", []) or []:
                        extra_ref = str(extra).split("#", 1)[0].replace("\\", "/")
                        if extra_ref not in allowed_contracts:
                            scope_error("contract", extra_ref)
        for test in manifest.get("tests", []):
            if isinstance(test, dict):
                if str(test.get("id")) not in allowed_tests:
                    scope_error("test", test.get("id"))
                test_path = str(test.get("path") or "").split("#", 1)[0].replace("\\", "/")
                if test_path not in allowed_test_paths:
                    scope_error("test_path", test_path)
        for row in proposal.get("coverage_table", []):
            if isinstance(row, dict) and str(row.get("requirement_id")) not in allowed_requirements:
                scope_error("coverage_requirement", row.get("requirement_id"))
        for row in proposal.get("entrypoints", []):
            if isinstance(row, dict) and row.get("owner_task") not in allowed_tasks:
                scope_error("entrypoint_task", row.get("owner_task"))

    for row in proposal.get("entrypoints", []):
        if not isinstance(row, dict):
            errors.append("invalid_entrypoint")
            continue
        status = str(row.get("status") or "")
        owner = row.get("owner_task")
        path = str(row.get("path") or "").strip()
        normalized_path = path.replace("\\", "/").lower()
        if normalized_path.startswith(("game.core/contracts/", "game.core.tests/", "tests.godot/")):
            errors.append(f"entrypoint_non_executable_evidence:{path}")
        if type(owner) is not int or owner not in known_tasks:
            errors.append(f"entrypoint_unknown_owner:{owner}")
        if status == "existing_verified":
            if not path:
                errors.append("verified_entrypoint_missing_path")
            else:
                try:
                    resolved = repo_path(root, path)
                except ValueError:
                    errors.append(f"verified_entrypoint_invalid_path:{path}")
                else:
                    if not resolved.is_file():
                        errors.append(f"verified_entrypoint_missing:{path}")
                    else:
                        if not any((prepared / prefix / path).is_file() for prefix in ("references", "sources")):
                            errors.append(f"verified_entrypoint_not_prepared:{path}")
                        symbol = str(row.get("symbol") or "").strip()
                        if not symbol or symbol.split(".")[-1] not in resolved.read_text(encoding="utf-8"):
                            errors.append(f"verified_entrypoint_symbol_missing:{path}")
        elif status == "planned":
            if not path:
                errors.append(f"planned_entrypoint_missing_path:{owner}")
            else:
                repo_path(root, path)
            for field in ("symbol", "inputs", "state", "assertions", "implementation_acceptance"):
                value = row.get(field)
                if value in (None, "", [], {}):
                    errors.append(f"planned_entrypoint_missing_{field}:{path or owner}")
        else:
            errors.append(f"invalid_entrypoint_status:{status}")
    status = "passed" if not errors else "blocked"
    formal_blockers: list[str] = []
    if planning_status != "ready_for_validation":
        formal_blockers.append("planning_status_not_ready")
    if gaps:
        formal_blockers.append("unresolved_gaps")
    return {
        "status": status,
        "errors": sorted(set(errors)),
        "planning_status": planning_status,
        "unresolved_gap_count": len(gaps),
        "formal_applicable": status == "passed" and not formal_blockers,
        "formal_blockers": formal_blockers,
    }


def review(root: Path, *, run_id: str, runner: Path, timeout_sec: int) -> dict[str, Any]:
    """Run a fresh text-only reviewer against sources and the fixed proposal."""
    from _mvg_planning_review import semantic_review_errors, review_execution_errors
    run_path, state = _load_run(root, run_id)
    run_dir = run_path.parent
    _validate_input_freshness(root, run_dir, state)
    proposal = load_json(run_dir / "proposal.json", {})
    if validate_proposal(root, state, proposal)["status"] != "passed":
        raise ValueError("MVG semantic review requires a structurally valid proposal")
    # Candidate admission already performed the independent semantic hard gate
    # against this exact proposal hash. Reuse that durable proof; never score a
    # winner and then silently replace it after a second semantic block.
    admission_proof = state.get("selected_admission_review")
    if isinstance(admission_proof, dict) and admission_proof.get("proposal_sha256") == canonical_sha(proposal):
        proof_path = repo_path(root, str(admission_proof.get("path") or ""))
        execution_path = repo_path(root, str(admission_proof.get("execution_path") or "")) if admission_proof.get("execution_path") else None
        if proof_path.is_file() and execution_path is not None and execution_path.is_file():
            expected_proof_sha = str(admission_proof.get("proof_sha256") or "")
            expected_execution_sha = str(admission_proof.get("execution_sha256") or "")
            if (not expected_proof_sha or not expected_execution_sha
                    or file_sha(proof_path) != expected_proof_sha
                    or file_sha(execution_path) != expected_execution_sha):
                state["phase"] = "review-blocked"
                atomic_json(run_path, state)
                raise ValueError("MVG candidate admission proof identity is stale or corrupted")
            proof = load_json(proof_path, {})
            execution = load_json(execution_path, {})
            errors = semantic_review_errors(state, proposal, proof,
                load_json(run_dir / "analysis-input/semantic-requirements.v1.json", {}),
                set(state.get("planning_scope", {}).get("requirement_ids", [])) if isinstance(state.get("planning_scope"), dict) else None)
            errors.extend(review_execution_errors(state, proposal, execution, proof))
            if errors:
                state["phase"] = "review-blocked"
                atomic_json(run_path, state)
                raise ValueError("MVG candidate admission proof is blocked: " + ";".join(errors))
            atomic_json(run_dir / "semantic-review.json", proof)
            atomic_json(run_dir / "semantic-review-execution.json", execution)
            state["phase"] = "reviewed"
            atomic_json(run_path, state)
            return {"status": "approved", "proposal_sha256": canonical_sha(proposal), "runtime_verified": False,
                    "source": "candidate-admission"}
    if state.get("selection_status") in {"selected", "legacy-single"}:
        state["phase"] = "review-blocked"
        atomic_json(run_path, state)
        raise ValueError(
            "selected MVG run has no valid hash-bound admission proof; "
            "legacy review bypass is disabled"
        )
    runner_info = inspect_isolated_runner(runner)
    from _planning_review_publication import completed_output, prepare_publication, publication_complete, resume_publication
    proposal_sha = canonical_sha(proposal)
    publication = run_dir / f"semantic-review-publication-{proposal_sha.removeprefix('sha256:')}.json"
    publication_identity = {"analysis_identity_sha256": state["analysis_identity_sha256"],
        "proposal_sha256": proposal_sha, "runner": runner_info}
    for recorded in run_dir.glob("semantic-review-publication-*.json"):
        if recorded != publication and not publication_complete(recorded):
            raise ValueError("MVG review publication is pending; recover the original proposal before revising it")
    settled = state.get("semantic_review_attempts") or []
    if backfill_review_error_types(state):
        atomic_json(run_path, state)
    if settled and settled[-1].get("status") == "completed" and settled[-1].get("proposal_sha256") != proposal_sha:
        prior_sha = str(settled[-1].get("proposal_sha256") or "").removeprefix("sha256:")
        if not (run_dir / f"semantic-review-publication-{prior_sha}.json").is_file():
            raise ValueError("Completed MVG review is unpublished; recover the original proposal before revising it")
    published = resume_publication(publication, publication_identity, atomic_json)
    existing = load_json(run_dir / "semantic-review.json", {})
    if published or (existing.get("proposal_sha256") == proposal_sha
            and existing.get("analysis_identity_sha256") == state["analysis_identity_sha256"]):
        scope = state.get("planning_scope") if isinstance(state.get("planning_scope"), dict) else None
        allowed_requirements = set(scope.get("requirement_ids", [])) if scope else None
        errors = semantic_review_errors(state, proposal, existing,
            load_json(run_dir / "analysis-input/semantic-requirements.v1.json", {}), allowed_requirements)
        existing_execution = load_json(run_dir / "semantic-review-execution.json", {})
        errors.extend(review_execution_errors(state, proposal, existing_execution, existing))
        if state.get("phase") != "applied":
            state["phase"] = "review-blocked" if errors else "reviewed"
        atomic_json(run_path, state)
        if errors:
            raise ValueError("existing independent semantic review is blocked; resolve findings before reviewing a revised proposal: "
                + ";".join(errors))
        return {"status": "approved", "proposal_sha256": proposal_sha, "runtime_verified": False}
    prompt = f'''Independently review proposal.json against the prepared source text and bounded review evidence,
the exact Capability membership in analysis-input/capabilities.v1.json, real Task/Acceptance/contracts/tests and the existing manifest under analysis-input.
Treat analysis-input/capabilities.v1.json as the only Capability SSoT; other evidence can support behavior and ownership but cannot create or remap Capability membership.
Task IDs are provenance/evidence owners, not a checklist of runtime APIs. Test and governance Tasks do not need runtime entrypoints, even if retained in legacy handoffs. Review each actual executable boundary against the Capability journey and prepared implementation/Acceptance evidence instead. Do not approve invented APIs assigned to evidence-only owners or data-only contracts. Check runtime boundary completeness across the whole flow, not one entrypoint per Task.
You did not generate this proposal. Evaluate semantic conservation, player journey and failure/recovery,
cross-system handoffs, every Requirement's flow/other-verification/deferred accounting, entrypoint inputs/state/assertions,
test evidence levels and feasibility. Planned entrypoints/tests are legitimate future obligations, not runtime proof.
Do not require their implementation or claim runtime_verified. The review-evidence.json file contains hash-bound
excerpts of proposal-referenced contracts/tests; deterministic validation still uses the complete immutable bundle.
Do not approve invented refs, missing obligations,
mechanical one-flow-per-Capability grouping, unsupported deferral or baseline weakening.
If this run includes a frozen existing-manifest scope, review only that scope. Requirements
outside its listed flow IDs are intentionally excluded claims, not missing coverage. Reject
any flow, test, task, source or Requirement that crosses the frozen boundary.
Return JSON only: schema_version="newrouge.mvg-semantic-review.v1",
analysis_identity_sha256="{state['analysis_identity_sha256']}", proposal_sha256="{canonical_sha(proposal)}",
Copy both identity values verbatim from this prompt; do not compute, shorten, or edit their sha256 strings.
They are fixed host-supplied input identities, not semantic judgments. Check their exact characters before returning JSON.
verdict="approved" or "blocked", findings=[] ONLY if all checks pass (otherwise concrete findings),
requirement_reviews=[{{"requirement_id":"...","verdict":"covered|other_verification|deferred|blocked","rationale":"...","disposition":"flow|other_verification|deferred","flow_id":null,"sink_id":null,"verification_ref":null,"authority_ref":null}}]
with exactly one explicit non-empty rationale per active delivery-relevant Requirement,
flow_reviews=[{{"flow_id":"...","verdict":"sound|blocked","rationale":"..."}}] with exactly one row per flow.
Use one actual verdict value, not the pipe-separated enumeration above. Do not rewrite the proposal.
'''
    review_scope = state.get("planning_scope") if isinstance(state.get("planning_scope"), dict) else None
    if review_scope is not None:
        prompt += "\nFrozen existing-manifest scope for this review:\n" + json.dumps({key: review_scope.get(key) for key in (
            "scope_id", "flow_ids", "requirement_ids", "capability_refs", "task_ids",
            "test_ids", "source_paths", "contract_refs", "test_paths", "excluded_claims")}, ensure_ascii=False)
    semantics = load_json(run_dir / "analysis-input/semantic-requirements.v1.json", {})
    scope = state.get("planning_scope") if isinstance(state.get("planning_scope"), dict) else None
    scoped_requirements = set(scope.get("requirement_ids", [])) if scope else None
    required_requirement_ids = {
        str(row.get("requirement_id"))
        for row in semantics.get("requirements", [])
        if isinstance(row, dict) and row.get("status", "active") == "active"
        and row.get("delivery_relevant", True)
        and (scoped_requirements is None or str(row.get("requirement_id")) in scoped_requirements)
    }
    manifest = proposal.get("manifest_candidate") or {}
    required_flow_ids = {
        str(row.get("id")) for row in manifest.get("flows", [])
        if isinstance(row, dict) and str(row.get("id") or "").strip()
    }
    # Validate the bounded projection before reserving any model attempt. A
    # deterministic input-size failure is not a transient runner failure and
    # must never burn the ten-attempt semantic review budget.
    preflight = run_dir / "semantic-review-workspace" / "_preflight"
    try:
        _prepare_review_workspace(run_dir, preflight, proposal)
    except (OSError, ValueError, RuntimeError) as exc:
        error_type = classify_review_error(exc)
        if error_type == "runner_input_too_large":
            state["phase"] = "review-input-blocked"
            atomic_json(run_path, state)
            raise MVGReviewPreparationError(
                error_type=error_type, attempt_limit=MVG_REVIEW_ATTEMPT_LIMIT,
                last_error=str(exc),
            ) from exc
        raise
    finally:
        if preflight.exists():
            shutil.rmtree(preflight, ignore_errors=True)
    import time
    attempts = state.setdefault("semantic_review_attempts", [])
    state["semantic_review_attempt_limit"] = MVG_REVIEW_ATTEMPT_LIMIT
    atomic_json(run_path, state)
    receipt = None
    result = None
    if attempts and attempts[-1].get("proposal_sha256") == proposal_sha:
        restored = completed_output(attempts, run_dir / "semantic-review-workspace" / f"attempt-{len(attempts)}" / "review.json")
        if restored:
            record, restored_result = restored
            if record.get("runner_info") != runner_info or record.get("analysis_identity_sha256") != state["analysis_identity_sha256"]:
                raise ValueError("Completed MVG review execution identity changed")
            restored_errors = validate_review_shape(
                state, proposal, restored_result,
                requirement_ids=required_requirement_ids,
                flow_ids=required_flow_ids,
                check_identity=False,
                check_accounting=False,
            )
            if restored_errors:
                record.update(status="execution-failed",
                              error="restored review output schema invalid: " + ";".join(restored_errors),
                              error_type="runner_output_schema_invalid")
                atomic_json(run_path, state)
            else:
                result = restored_result
                receipt = record["receipt"]
    while len(attempts) < MVG_REVIEW_ATTEMPT_LIMIT and result is None:
        number = len(attempts) + 1
        workspace = run_dir / "semantic-review-workspace" / f"attempt-{number}"
        workspace.mkdir(parents=True, exist_ok=False)
        atomic_json(workspace / "proposal.json", proposal)
        prompt_path = workspace / "prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8", newline="\n")
        output = workspace / "review.json"
        output_schema = workspace / "review-output-schema.json"
        atomic_json(output_schema, semantic_review_output_schema())
        record = {"stage": "review", "attempt": number, "status": "running", "proposal_sha256": proposal_sha,
            "runner_info": runner_info, "analysis_identity_sha256": state["analysis_identity_sha256"]}
        attempts.append(record)
        atomic_json(run_path, state)  # Count even an interrupted invocation.
        started = time.monotonic()
        try:
            _prepare_review_workspace(run_dir, workspace, proposal)
            receipt = run_isolated_model(runner, workspace=workspace, prompt_path=prompt_path,
                output_path=output, timeout_sec=timeout_sec, output_schema=output_schema)
            if receipt.get("model_tools") != [] or not receipt.get("model"):
                raise ValueError("independent reviewer execution identity is incomplete")
            result = parse_model_json(output)
            shape_errors = validate_review_shape(
                state, proposal, result,
                requirement_ids=required_requirement_ids,
                flow_ids=required_flow_ids,
                check_identity=False,
                check_accounting=False,
            )
            if shape_errors:
                raise ValueError("independent reviewer output schema invalid: " + ";".join(shape_errors))
            record.update(status="completed", receipt=receipt, output_sha256=file_sha(output))
        except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
            # A parsed but schema-invalid response is not a usable result;
            # clear it so the bounded retry loop actually executes.
            result = None
            record.update(status="execution-failed", error=_compact_exception_message(exc),
                          error_type=classify_review_error(exc))
            state["phase"] = "review-execution-blocked"
        finally:
            record["activity_sec"] = time.monotonic() - started
            atomic_json(run_path, state)
        if result is not None:
            break
    if result is None:
        last = attempts[-1] if attempts else {}
        raise MVGReviewAttemptBudgetError(
            error_type=str(last.get("error_type") or "runner_execution_failed"),
            attempts_used=len(attempts),
            attempt_limit=MVG_REVIEW_ATTEMPT_LIMIT,
            last_error=str(last.get("error") or "no review attempt completed"),
        )
    execution = {"runner": runner.as_posix(), "runner_info": runner_info, "receipt": receipt,
        "analysis_identity_sha256": state["analysis_identity_sha256"], "proposal_sha256": canonical_sha(proposal),
        "semantic_review_sha256": canonical_sha(result), "attempt_count": len(attempts)}
    prepare_publication(publication, publication_identity,
        {"semantic-review.json": result, "semantic-review-execution.json": execution}, atomic_json)
    resume_publication(publication, publication_identity, atomic_json)
    scope = state.get("planning_scope") if isinstance(state.get("planning_scope"), dict) else None
    errors = semantic_review_errors(state, proposal, result,
        load_json(run_dir / "analysis-input/semantic-requirements.v1.json", {}),
        set(scope.get("requirement_ids", [])) if scope else None)
    # A semantic block is terminal for this candidate. Candidate replacement
    # belongs to pre-selection admission; the final review must never silently
    # switch the selected winner after comparative scoring.
    state["phase"] = "reviewed" if not errors else "review-blocked"
    atomic_json(run_path, state)
    if errors:
        raise ValueError("MVG independent semantic review blocked: " + ";".join(errors))
    return {"status": "approved", "proposal_sha256": canonical_sha(proposal), "runtime_verified": False}


def _review_map(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        return {}
    return {
        str(row.get("id")): row
        for row in value
        if isinstance(row, dict) and str(row.get("id") or "").strip()
    }


def build_delta(existing: dict[str, Any], proposal: dict[str, Any]) -> dict[str, Any]:
    from update_mvg_baseline import _canonical_sha

    desired = proposal["manifest_candidate"]
    change_reviews = _review_map(proposal.get("change_reviews"))
    retirement_reviews = _review_map(proposal.get("retirement_reviews"))

    def ops(kind: str) -> list[dict[str, Any]]:
        old_rows = {str(row["id"]): row for row in existing.get(kind, [])}
        new_rows = {str(row["id"]): row for row in desired.get(kind, [])}
        result = []
        for item_id, old in old_rows.items():
            new = new_rows.get(item_id)
            if new is None:
                review = retirement_reviews.get(item_id, {})
                result.append({
                    "id": item_id,
                    "action": "retire",
                    "reason": str(review.get("reason") or "candidate removes existing obligation"),
                    "authority_ref": review.get("authority_ref"),
                    "authority_review": review.get("authority_review"),
                })
            elif canonical_sha(old) == canonical_sha(new):
                result.append({"id": item_id, "action": "retain", "reason": "unchanged cumulative baseline"})
            else:
                review = change_reviews.get(item_id, {})
                updates = {key: value for key, value in new.items() if key != "id" and old.get(key) != value}
                row = {
                    "id": item_id,
                    "action": "update",
                    "reason": str(review.get("reason") or "planned cumulative update"),
                    "field_updates": updates,
                }
                if review.get("authority_ref"):
                    row["authority_ref"] = review.get("authority_ref")
                if review.get("authority_review"):
                    row["authority_review"] = review.get("authority_review")
                result.append(row)
        for item_id, new in new_rows.items():
            if item_id not in old_rows:
                result.append({
                    "id": item_id,
                    "action": "add",
                    "reason": "new planned cumulative obligation",
                    "value": new,
                })
        return result

    delta = {
        "schema_version": "newrouge.mvg-baseline-delta.v1",
        "expected_manifest_sha256": _canonical_sha(existing),
        "change_plan_sha256": canonical_sha(proposal),
        "flow_operations": ops("flows"),
        "test_operations": ops("tests"),
    }
    old_coverage = existing.get("coverage") or {}
    new_coverage = desired.get("coverage") or {}
    if canonical_sha(old_coverage) != canonical_sha(new_coverage):
        delta["coverage_updates"] = {
            key: value for key, value in new_coverage.items()
            if old_coverage.get(key) != value
        }
        review = proposal.get("coverage_review")
        if isinstance(review, dict):
            delta["authority_ref"] = review.get("authority_ref")
            delta["authority_review"] = review.get("authority_review")
    return delta


def validate(root: Path, *, run_id: str) -> dict[str, Any]:
    run_path, state = _load_run(root, run_id)
    run_dir = run_path.parent
    _validate_input_freshness(root, run_dir, state)
    proposal = load_json(run_dir / "proposal.json", {})
    result = validate_proposal(root, state, proposal)
    from _mvg_planning_review import semantic_review_errors, review_execution_errors
    scope = state.get("planning_scope") if isinstance(state.get("planning_scope"), dict) else None
    review_errors = semantic_review_errors(state, proposal, load_json(run_dir / "semantic-review.json", {}),
        load_json(run_dir / "analysis-input/semantic-requirements.v1.json", {}),
        set(scope.get("requirement_ids", [])) if scope else None)
    review_errors.extend(review_execution_errors(state, proposal,
        load_json(run_dir / "semantic-review-execution.json", {}),
        load_json(run_dir / "semantic-review.json", {})))
    if review_errors:
        result["formal_applicable"] = False
        result["formal_blockers"].extend(review_errors)
    if result["status"] == "passed":
        baseline = run_dir / "analysis-input/existing-manifest.json"
        if baseline.is_file():
            existing = load_json(baseline, {})
            delta = build_delta(existing, proposal)
            atomic_json(run_dir / "delta.json", delta)
            from update_mvg_baseline import apply_delta
            try:
                apply_delta(existing, delta, root=root, validate_final=True)
                result["delta_status"] = "passed"
            except ValueError as exc:
                result["delta_status"] = "blocked"
                result.setdefault("errors", []).append(str(exc))
                result["status"] = "blocked"
        else:
            result["delta_status"] = "not_applicable_initial_manifest"
    atomic_json(run_dir / "validation.json", result)
    state["phase"] = "validated" if result["status"] == "passed" else "validation-blocked"
    atomic_json(run_path, state)
    return result


def _validate_input_freshness(root: Path, run_dir: Path, state: dict[str, Any]) -> None:
    index = load_json(run_dir / "analysis-input/analysis-index.json", {})
    identity = index.pop("analysis_identity_sha256", None)
    # Repository revision/dirty state is provenance, not the planning input
    # identity. Local commits may advance without invalidating unchanged inputs.
    index.pop("repository_identity", None)
    if canonical_sha(index) != identity or identity != state.get("analysis_identity_sha256"):
        raise ValueError("MVG prepared analysis identity changed")
    authority = index.get("authority_inputs")
    if not isinstance(authority, dict) or not authority:
        raise ValueError("MVG original authority identity is incomplete; prepare again")
    drift = []
    for rel, expected in authority.items():
        path = repo_path(root, rel)
        if ((normalized_file_sha(path) if path.is_file() else None) != expected
                and (file_sha(path) if path.is_file() else None) != expected):
            drift.append(rel)
    for rel, expected in index["files"].items():
        path = repo_path(run_dir / "analysis-input", rel)
        if not path.is_file() or file_sha(path) != expected:
            drift.append("analysis-input/" + rel)
    atomic_json(run_dir / "input-freshness.json", {"status": "blocked" if drift else "current", "drift": drift})
    if drift:
        raise ValueError("MVG input drift: " + ",".join(drift))


def apply(root: Path, *, run_id: str, confirm: bool) -> dict[str, Any]:
    if not confirm:
        raise ValueError("MVG planning apply requires --confirm")
    run_path, state = _load_run(root, run_id)
    run_dir = run_path.parent
    from _planning_apply_journal import create_journal, resume_journal
    journal_path = run_dir / "apply-journal.json"
    if journal_path.is_file():
        result = resume_journal(root, journal_path, atomic_json)
        state.update(phase="applied", applied=True, applied_manifest_sha256=result["manifest_sha256"],
            post_apply_task_readiness=result["post_apply_task_readiness"],
            involved_task_ids=result["handoff_review_required_tasks"],
            handoff_review_required_tasks=result["handoff_review_required_tasks"])
        trace = load_json(root / result["trace_path"], {})
        state["handoff_bindings"] = dict(trace.get("handoff_bindings") or {})
        atomic_json(run_path, state)
        atomic_json(run_dir / "apply-summary.json", result)
        return result
    proposal = load_json(run_dir / "proposal.json", {})
    validation = validate(root, run_id=run_id)
    if validation.get("status") != "passed":
        raise ValueError("MVG proposal/delta validation is blocked")
    if validation.get("formal_applicable") is not True:
        blockers = ",".join(str(value) for value in validation.get("formal_blockers", []))
        raise ValueError(
            "MVG proposal is structurally valid but not formally applicable: "
            + (blockers or "unknown_formal_blocker")
        )
    if file_sha(root / str(state["capabilities_path"])) != state.get("capabilities_sha256"):
        raise ValueError("selected Capability input changed after MVG planning prepare")

    manifest_path = root / str(state["manifest_path"]) if state.get("manifest_path") else None
    if manifest_path is None:
        raise ValueError("MVG apply requires an explicit --manifest destination from prepare")
    candidate = proposal["manifest_candidate"]
    if manifest_path.is_file():
        from update_mvg_baseline import apply_delta
        existing = load_json(manifest_path, {})
        updated = apply_delta(existing, load_json(run_dir / "delta.json", {}), root=root, validate_final=True)
    else:
        errors = validate_manifest(root, candidate, executable=False)
        if errors:
            raise ValueError("initial MVG manifest invalid: " + "; ".join(errors))
        updated = candidate

    trace = deepcopy(proposal)
    trace["applied_manifest_path"] = manifest_path.resolve().relative_to(root.resolve()).as_posix()
    trace["applied_manifest_sha256"] = text_sha(json.dumps(updated, ensure_ascii=False, indent=2) + "\n")
    trace["capabilities_sha256"] = state["capabilities_sha256"]
    trace["applied_at_utc"] = now()
    trace_path = root / FORMAL_TRACE_ROOT / f"{run_id}.json"
    trace["handoff_bindings"] = {}
    # Persist the execution blocker before introducing new manifest obligations.

    involved = sorted({
        str(task_id)
        for flow in candidate.get("flows", [])
        if isinstance(flow, dict)
        for task_id in flow.get("task_ids", [])
    })
    from chapter5_semantic_reconciliation import load_task_readiness
    readiness = []
    for task_id in involved:
        ok, payload, reason = load_task_readiness(root, task_id)
        readiness.append({
            "task_id": task_id,
            "ready": bool(ok),
            "reason": reason,
            "readiness": payload.get("readiness") if isinstance(payload, dict) else None,
        })
    result = {
        "status": "applied",
        "manifest_path": state["manifest_path"],
        "manifest_sha256": trace["applied_manifest_sha256"],
        "trace_path": trace_path.resolve().relative_to(root.resolve()).as_posix(),
        "planning_complete": True,
        "runtime_verified": False,
        "chapter6_ready": False,
        "handoff_review_required_tasks": involved,
        "handoff_note": "Bind current Chapter 5 readiness for ordinary tasks; actual milestone owners also require the existing manifest-bound milestone handoff.",
        "post_apply_task_readiness": readiness,
    }
    authority = load_json(run_dir / "analysis-input/analysis-index.json", {})["authority_inputs"]
    create_journal(root, journal_path, {trace_path: trace, manifest_path: updated}, authority, result,
        mutable_json_keys={trace_path: ["handoff_bindings"]})
    return apply(root, run_id=run_id, confirm=True)


def rebind_handoff(
    root: Path,
    *,
    run_id: str,
    task_id: str,
    change_plan_path: Path | None,
    out_path: Path | None,
) -> dict[str, Any]:
    run_path, state = _load_run(root, run_id)
    if state.get("applied") is not True:
        raise ValueError("MVG handoff rebind requires an applied planning run")
    manifest_ref = str(state.get("manifest_path") or "").strip()
    if not manifest_ref:
        raise ValueError("MVG handoff rebind is missing the applied manifest path")
    manifest_path = repo_path(root, manifest_ref)
    expected_manifest_sha = str(state.get("applied_manifest_sha256") or "")
    if not manifest_path.is_file() or normalized_file_sha(manifest_path) != expected_manifest_sha:
        raise ValueError("applied MVG manifest changed before handoff rebind")

    canonical_task = str(task_id).strip()
    involved = {str(value) for value in state.get("involved_task_ids", [])}
    if canonical_task not in involved:
        raise ValueError(
            f"task {canonical_task} is not involved in this applied MVG planning run"
        )

    from chapter5_semantic_reconciliation import (
        load_task_readiness,
        readiness_path_for_task,
    )
    ready, _payload, reason = load_task_readiness(root, canonical_task)
    if not ready:
        raise ValueError(
            f"current Chapter 5 readiness is not valid for task {canonical_task}: {reason}"
        )
    readiness_path = readiness_path_for_task(root, canonical_task)

    from _mvg_obligations import applicable_milestone_plans
    plans = applicable_milestone_plans(root, canonical_task, manifest_ref)
    validated = {}
    binding = {
        "status": "valid", "kind": "ordinary",
        "chapter5_readiness_path": readiness_path.relative_to(root).as_posix(),
        "chapter5_readiness_sha256": file_sha(readiness_path),
        "manifest_path": manifest_ref, "manifest_sha256": expected_manifest_sha,
    }
    if change_plan_path is None:
        if plans:
            raise ValueError("applicable milestone plan requires a real --change-plan and --out handoff")
    else:
        if out_path is None:
            raise ValueError("milestone handoff rebind requires --out")
        plan = load_json(change_plan_path, {})
        if str(plan.get("baseline_manifest") or "") != manifest_ref:
            raise ValueError("milestone change plan must name the applied MVG manifest")
        if plans and any(p.resolve() != change_plan_path.resolve() for p in plans):
            raise ValueError("multiple applicable milestone plans require upstream resolution")
        from milestone_incremental_handoff import build_task_handoff, validate_task_handoff
        handoff = build_task_handoff(root, plan_path=change_plan_path,
            task_id=canonical_task, readiness_path=readiness_path)
        atomic_json(out_path, handoff)
        ok, validation_reason, validated = validate_task_handoff(root, out_path, canonical_task)
        if not ok:
            raise ValueError("rebuilt milestone handoff is invalid: " + validation_reason)
        binding.update(kind="milestone", path=out_path.relative_to(root).as_posix(), sha256=normalized_file_sha(out_path),
            change_plan_path=change_plan_path.relative_to(root).as_posix())
    trace_path = root / FORMAL_TRACE_ROOT / f"{run_id}.json"
    trace = load_json(trace_path, {})
    if trace.get("applied_manifest_sha256") != expected_manifest_sha:
        raise ValueError("MVG durable applied trace is missing or stale")
    bindings = dict(trace.get("handoff_bindings") or {})
    bindings[canonical_task] = binding
    trace["handoff_bindings"] = bindings
    atomic_json(trace_path, trace)
    state["handoff_bindings"] = bindings
    atomic_json(run_path, state)
    return {"status": "bound", "task_id": canonical_task, "binding_kind": binding["kind"],
        "handoff_path": binding.get("path"), "handoff_sha256": binding.get("sha256"),
        "chapter6_handoff_ready": True, "runtime_verified": False, "handoff": validated}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prepare = sub.add_parser("prepare")
    p_prepare.add_argument("--run-id", required=True)
    p_prepare.add_argument("--capabilities", required=True)
    p_prepare.add_argument("--task-id", action="append", default=[])
    p_prepare.add_argument("--manifest", required=True)
    p_prepare.add_argument("--evidence-ref", action="append", default=[],
        help="additional existing verification file to include in the immutable input")
    p_prepare.add_argument("--allow-unready-draft", action="store_true")

    p_generate = sub.add_parser("generate")
    p_generate.add_argument("--run-id", required=True)
    p_generate.add_argument("--timeout-sec", type=int, default=1800)
    p_generate.add_argument("--llm-backend", default="codex-cli")

    p_review = sub.add_parser("review")
    p_review.add_argument("--run-id", required=True)
    p_review.add_argument("--runner", required=True)
    p_review.add_argument("--timeout-sec", type=int, default=1800)

    for name in ("validate", "status"):
        p = sub.add_parser(name)
        p.add_argument("--run-id", required=True)

    p_apply = sub.add_parser("apply")
    p_apply.add_argument("--run-id", required=True)
    p_apply.add_argument("--confirm", action="store_true")

    p_handoff = sub.add_parser(
        "rebind-handoff",
        help="rebuild one applicable milestone handoff against the applied MVG manifest and current Chapter 5 readiness",
    )
    p_handoff.add_argument("--run-id", required=True)
    p_handoff.add_argument("--task-id", required=True)
    p_handoff.add_argument("--change-plan", default="")
    p_handoff.add_argument("--out", default="")

    args = parser.parse_args(argv)
    root = Path(args.repo_root).resolve()
    try:
        if args.command == "prepare":
            result = prepare(
                root,
                run_id=args.run_id,
                capabilities_path=repo_path(root, args.capabilities),
                task_ids=[str(value) for value in args.task_id],
                manifest_path=repo_path(root, args.manifest),
                allow_unready=bool(args.allow_unready_draft),
                evidence_refs=args.evidence_ref,
            )
        elif args.command == "generate":
            result = generate(
                root, run_id=args.run_id,
                timeout_sec=args.timeout_sec,
                llm_backend=args.llm_backend,
            )
        elif args.command == "validate":
            result = validate(root, run_id=args.run_id)
        elif args.command == "review":
            result = review(root, run_id=args.run_id, runner=Path(args.runner).resolve(), timeout_sec=args.timeout_sec)
        elif args.command == "apply":
            result = apply(root, run_id=args.run_id, confirm=bool(args.confirm))
        elif args.command == "rebind-handoff":
            result = rebind_handoff(
                root,
                run_id=args.run_id,
                task_id=str(args.task_id),
                change_plan_path=repo_path(root, args.change_plan) if args.change_plan else None,
                out_path=repo_path(root, args.out) if args.out else None,
            )
        else:
            _path, result = _load_run(root, args.run_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        payload = {"status": "blocked", "reason": str(exc)}
        if isinstance(exc, (MVGReviewAttemptBudgetError, MVGReviewPreparationError)):
            payload.update({"stage": "review", "error_type": exc.error_type,
                "attempts_used": exc.attempts_used, "attempt_limit": exc.attempt_limit,
                "last_error": exc.last_error, "proposal_preserved": True})
        print(json.dumps(payload, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
