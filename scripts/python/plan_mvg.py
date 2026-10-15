#!/usr/bin/env python3
"""Independent post-Capability MVG planning that produces an initial manifest or reviewed cumulative delta."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import os
import random
import re
import shutil
import sys
import threading
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from _mvg_manifest import validate_manifest
from _mvg_requirement_routes import (FIELD as ROUTE_FIELD, PROJECTION as ROUTE_PROJECTION,
    memberships, pair_errors, project_routes, route_errors, protocol_errors)
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


class MVGSegmentRoutingError(ValueError):
    """A bounded segment failed deterministic routing and remains repairable."""

    def __init__(self, message: str, issues: list[dict[str, str]] | None = None) -> None:
        super().__init__(message)
        self.issues = issues or segment_route_validation_issues(message)


class MVGRoutingSourceGapError(MVGSegmentRoutingError):
    """The model explicitly reported a missing non-runtime evidence source."""

    def __init__(self, gaps: list[str]) -> None:
        self.gaps = list(gaps)
        super().__init__("routing_source_evidence_missing:" + ";".join(self.gaps), [
            {"code": "routing_source_gap:" + gap.split(":", 1)[0], "path": "routing", "detail": gap}
            for gap in self.gaps])


def segment_route_validation_issues(error: BaseException | str) -> list[dict[str, str]]:
    """Convert a terminal segment routing error into candidate-local issues."""
    text = str(error or "").strip()
    marker = "identity invalid:"
    payload = text.split(marker, 1)[1].strip() if marker in text else text
    issues: list[dict[str, str]] = []
    for code in (part.strip() for part in payload.split(";")):
        if not code or not code.startswith("segment_"):
            continue
        section = "segment.flows" if "flow" in code else "segment"
        issues.append({"code": code, "path": section, "detail": code})
    return issues


def _flow_request_ids(request: dict[str, Any]) -> set[str]:
    if request.get("section") == "flows":
        return {str(request.get("scope_id") or "")}
    return {str(value) for value in request.get("flow_scope_ids", []) if str(value).strip()}


def requirement_route_repair_id(issue: dict[str, Any]) -> str:
    """Reassign ownership only when the review explicitly requests that repair."""
    code = str(issue.get("code") or "")
    if code.startswith("routing_reassign:"):
        return code.rsplit(":", 1)[-1]
    if (code.startswith("semantic_review_blocked:requirement_reviews:")
            and issue.get("repair_action") == "reassign_route"):
        return code.rsplit(":", 1)[-1]
    return ""


def route_candidate_repair_requests(requests: list[dict[str, Any]], issue: dict[str, Any],
                                    proposal: dict[str, Any] | None) -> set[int]:
    """Select only proposal sections that can repair one identified hard issue."""
    code = str(issue.get("code") or "")
    if not code:
        return set(range(1, len(requests) + 1))

    requirement_id = ""
    flow_id = ""
    if code.startswith("semantic_review_blocked:requirement_reviews:"):
        requirement_id = code.rsplit(":", 1)[-1]
    elif code.startswith("semantic_review_blocked:flow_reviews:"):
        flow_id = code.rsplit(":", 1)[-1]
    elif code.startswith(("coverage_", "semantic_review_accounting_")):
        requirement_id = code.rsplit(":", 1)[-1]
    elif code.startswith("segment_flow_change_review_missing:"):
        flow_id = code.split(":", 1)[1]
    elif code.startswith(("flow_requirement_multiple_routes:",
                          "segment_flow_requirement_multiple_routes:")):
        requirement_id = code.rsplit(":", 1)[-1]
    elif "flow" in code and ":" in code:
        suffix = code.rsplit(":", 1)[-1]
        known_flows = {
            str(row.get("id"))
            for row in ((proposal or {}).get("manifest_candidate") or {}).get("flows", [])
            if isinstance(row, dict)
        }
        if suffix in known_flows:
            flow_id = suffix
    if not requirement_id and not flow_id:
        return set(range(1, len(requests) + 1))

    flows = [row for row in (((proposal or {}).get("manifest_candidate") or {}).get("flows", []))
             if isinstance(row, dict)]
    flow_ids: set[str] = set()
    if requirement_id:
        matching = [row for row in flows if requirement_id in {
            str(value) for value in row.get("requirement_ids", [])
        }]
        if len(matching) == 1:
            flow_id = str(matching[0].get("id") or "")
        elif len(matching) > 1 and not flow_id:
            flow_ids = {str(row.get("id") or "") for row in matching}
        else:
            flow_ids = set()
    else:
        flow_ids = set()
    if flow_id:
        flow_ids.add(flow_id)

    routed: set[int] = set()
    for index, request in enumerate(requests, start=1):
        section = str(request.get("section") or "")
        request_requirements = {str(value) for value in request.get("requirement_ids", [])}
        request_flows = _flow_request_ids(request)
        if requirement_id and section == "coverage" and requirement_id in request_requirements:
            routed.add(index)
        if flow_ids and request_flows.intersection(flow_ids):
            if section in {"flows", "entrypoints", "tests"}:
                routed.add(index)
            elif section == "coverage" and requirement_id:
                if requirement_id in request_requirements:
                    routed.add(index)
    return routed or set(range(1, len(requests) + 1))


def admission_issue_id(code: str, path: str = "") -> str:
    """Return a stable identity for one ordered candidate hard issue."""
    return f"{str(code).strip()}@{str(path).strip()}"


def candidate_has_unfinished_repair(state: dict[str, Any], candidate: str) -> bool:
    """Return whether a candidate has a current hard issue below its repair cap."""
    admissions = state.get("candidate_admissions")
    admission = admissions.get(candidate) if isinstance(admissions, dict) else None
    if not isinstance(admission, dict) or admission.get("status") in {"retired", "admitted", "execution-failed"}:
        return False
    issues = admission.get("issues") if isinstance(admission.get("issues"), list) else []
    current = admission.get("current_issue") if isinstance(admission.get("current_issue"), dict) else None
    if current is None and issues and isinstance(issues[0], dict):
        current = issues[0]
    if not current:
        return False
    issue_id = admission_issue_id(str(current.get("code") or "issue"),
                                  str(current.get("path") or ""))
    attempts = admission.get("issue_attempts")
    used = int(attempts.get(issue_id, 0) or 0) if isinstance(attempts, dict) else 0
    return used < MVG_REPAIR_ATTEMPT_LIMIT


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
                            repaired: bool, count_repair: bool = True) -> dict[str, Any]:
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
        if isinstance(item, dict):
            for key in ("repair_action", "findings"):
                if item.get(key):
                    normalized_issue[key] = str(item[key])
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
        attempts[current_id] = int(attempts.get(current_id, 0)) + int(count_repair)
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
                               semantic_review: dict[str, Any] | None = None, *,
                               append_requirement_ids: set[str] | None = None) -> list[dict[str, str]]:
    """Return ordered hard issues that prevent a proposal entering selection."""
    validation = validate_proposal(root, state, proposal, append_requirement_ids=append_requirement_ids)
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
        if semantic_review.get("schema_version") == "newrouge.mvg-capability-admission.v1":
            from _mvg_capability_generation import capability_scopes, seed_proposal
            prepared = _run_dir(root, str(state.get("run_id"))) / "analysis-input"
            expected_scopes = capability_scopes(load_json(prepared / "capabilities.v1.json", {}),
                load_json(prepared / "semantic-requirements.v1.json", {}), state.get("planning_scope"),
                {str(row["id"]): str(row.get("status", "")).lower() for row in
                 load_json(prepared / "task-master.json", {}).get("master", {}).get("tasks", [])}, prepared=prepared)
            if append_requirement_ids is not None:
                matching = [index for index, scope in enumerate(expected_scopes)
                            if set(scope["cumulative_requirement_ids"]) == append_requirement_ids]
                # Shared membership may repeat; the proof still binds the exact
                # frozen ordered prefix, including scopes with no new coverage.
                count = len(semantic_review.get("scopes", []))
                if count - 1 not in matching:
                    issues.append({"code": "capability_admission_prefix_scope_invalid", "path": "admission-review"})
                expected_scopes = expected_scopes[:count]
            if semantic_review.get("scopes") != expected_scopes or semantic_review.get("seed") != seed_proposal(state, prepared):
                issues.append({"code": "capability_admission_prepared_binding_invalid", "path": "admission-review"})
        scope = state.get("planning_scope") if isinstance(state.get("planning_scope"), dict) else None
        allowed = set(scope.get("requirement_ids", [])) if scope else None
        if append_requirement_ids is not None:
            allowed = append_requirement_ids
        semantics_path = _run_dir(root, str(state.get("run_id"))) / "analysis-input/semantic-requirements.v1.json"
        semantics = load_json(semantics_path, None)
        if (not isinstance(semantics, dict) or not isinstance(semantics.get("requirements"), list)
                or not semantics["requirements"]):
            issues.append({"code": "prepared_semantic_requirements_snapshot_missing_or_invalid",
                           "path": "analysis-input/semantic-requirements.v1.json"})
            errors = []
        else:
            errors = semantic_review_errors(state, proposal, semantic_review, semantics, allowed,
                root=root, prepared=_run_dir(root, str(state.get('run_id'))) / 'analysis-input')
        specific_blockers = [error for error in errors
                             if str(error).startswith("semantic_review_blocked:")]
        if specific_blockers:
            # The aggregate verdict is a consequence of these identified rows,
            # not a second issue that would trigger a broad whole-proposal retry.
            errors = [error for error in errors if error != "semantic_review_not_approved"]
        finding_detail = "; ".join(
            str(value).strip() for value in (semantic_review.get("findings") or [])
            if isinstance(value, str) and value.strip()
        )[:1000]
        for error in errors:
            issue = {"code": str(error), "path": "semantic-review"}
            if str(error).startswith("semantic_review_blocked:"):
                _, family, identifier = str(error).split(":", 2)
                key = "requirement_id" if family == "requirement_reviews" else "flow_id"
                row = next((row for row in semantic_review.get(family, [])
                            if isinstance(row, dict) and str(row.get(key)) == identifier), {})
                issue["detail"] = str(row.get("rationale") or "")
                issue["repair_action"] = str(row.get("repair_action") or "repair_sections")
                if finding_detail:
                    issue["findings"] = finding_detail
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
    hard_issues = candidate_admission_errors(root, state, proposal)
    if hard_issues:
        raise ValueError('MVG candidate accounting admission blocked:' + str(hard_issues))
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
              "For an existing manifest, compare each changed flow with existing-manifest.json and "
              "verify that its change_reviews authority actually supports the exact semantic change. "
              "A candidate's authority_review.status=reviewed is a justification claim, not your approval; "
              "block unsupported baseline rewrites even when the referenced file exists. "
              "This is planning admission, not runtime acceptance. An implemented test means its implementation "
              "exists, not that it passed or proves an entire Requirement. Planned entrypoints/tests with real "
              "owners, concrete inputs/state/assertions and implementation acceptance are legitimate future "
              "obligations. Do not require those obligations to be implemented now. Block coverage claims "
              "that neither have adequate existing evidence nor explicitly specify the missing verification. "
              "For each requirement_review return repair_action=none when accepted, repair_sections for missing "
              "evidence, assertions, or implementation obligations within its correct journey, and reassign_route "
              "only when the Requirement belongs to a different journey. Missing verification alone is not "
              "a reason to reassign ownership. Explain the precise needed repair in that row's rationale. "
              f"schema_version='newrouge.mvg-semantic-review.v1', analysis_identity_sha256='{state['analysis_identity_sha256']}', "
              f"proposal_sha256='{proposal_sha}'. Return complete requirement_reviews and flow_reviews. "
              "Echo disposition, flow_id, sink_id, verification_ref and authority_ref exactly from "
              "each proposal coverage_table row, including nulls. Put your evidence analysis in "
              "rationale, not in the echoed fields. A blocked semantic verdict is allowed.")
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
                check_identity=True, check_accounting=True,
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
        atomic_json(schema, semantic_review_output_schema(state=state, proposal=proposal))
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
                                              output_schema=semantic_review_output_schema(state=state, proposal=proposal))
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
                check_identity=True, check_accounting=True)
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
            if isinstance(exc, MVGGenerationStoppedError):
                raise
            attempts.append({"attempt": number, "status": "execution-failed",
                             "error": _compact_exception_message(exc),
                             "error_type": classify_review_error(exc)})
            atomic_json(review_workspace / "semantic-review-attempts.json", {"attempts": attempts})
            prompt += ("\nThe previous review failed output validation; correct the review only. "
                       "Do not change proposal accounting or turn a formatting error into a semantic finding. "
                       "Exact error: " + _compact_exception_message(exc))
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
    if isinstance(exc, MVGGenerationStoppedError):
        return "candidate_sibling_execution_failed"
    if isinstance(exc, MVGCandidateInvocationBudgetError):
        return exc.error_type
    if isinstance(exc, MVGSegmentRoutingError):
        return "candidate_segment_route_invalid"
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
        coverage = {str(row.get("requirement_id")): row for row in proposal.get("coverage_table", [])
                    if isinstance(row, dict)}
        for row in review.get("requirement_reviews", []) or []:
            if not isinstance(row, dict) or str(row.get("requirement_id")) not in coverage:
                continue
            expected = coverage[str(row["requirement_id"])]
            for field in ("disposition", "flow_id", "sink_id", "verification_ref", "authority_ref"):
                value = expected.get(field)
                if field == "disposition":
                    value = value or ("flow" if expected.get("flow_id") else "")
                if row.get(field) != value:
                    errors.append(f"semantic_review_echo_mismatch:{row['requirement_id']}:{field}")
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


def semantic_review_output_schema(*, state: dict[str, Any] | None = None,
                                 proposal: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return the transport-level JSON schema for an independent review."""
    rationale = {"type": "string", "minLength": 1}
    requirement = {
        "type": "object",
        "additionalProperties": False,
        "required": ["requirement_id", "verdict", "rationale", "disposition",
                     "flow_id", "sink_id", "verification_ref", "authority_ref", "route", "repair_action"],
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
            "repair_action": {"type": "string", "enum": ["none", "repair_sections", "reassign_route"]},
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
    schema = {
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
    if state is not None and proposal is not None:
        schema["properties"]["analysis_identity_sha256"]["const"] = state["analysis_identity_sha256"]
        schema["properties"]["proposal_sha256"]["const"] = canonical_sha(proposal)
        rows = [row for row in proposal.get("coverage_table", []) if isinstance(row, dict)]
        if rows:
            bound_rows = []
            for row in rows:
                item = deepcopy(requirement)
                for field in ("requirement_id", "disposition", "route", "flow_id", "sink_id",
                              "verification_ref", "authority_ref"):
                    value = row.get(field)
                    if field == "disposition":
                        value = value or ("flow" if row.get("flow_id") else "")
                    if field == "route":
                        value = row.get("route") or row.get("disposition") or ("flow" if row.get("flow_id") else "")
                    item["properties"][field] = {"type": "null" if value is None else "string",
                                                 "const": value}
                bound_rows.append(item)
            schema["properties"]["requirement_reviews"].update(
                items={"anyOf": bound_rows}, minItems=len(rows), maxItems=len(rows))
        flow_ids = sorted({str(row["id"]) for row in (proposal.get("manifest_candidate") or {}).get("flows", [])
                           if isinstance(row, dict) and row.get("id")})
        if flow_ids:
            flow["properties"]["flow_id"]["enum"] = flow_ids
            schema["properties"]["flow_reviews"].update(minItems=len(flow_ids), maxItems=len(flow_ids))
        else:
            schema["properties"]["flow_reviews"]["maxItems"] = 0
    return schema


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


class MVGGenerationStoppedError(RuntimeError):
    """Stop new model work when a sibling has failed execution."""


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


def reserve_candidate_model_invocation(candidate_root: Path, candidate: str, lineage: str,
                                       ) -> int:
    """Reserve one model call under the durable hard lineage ceiling."""
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


def reserve_issue_repair(candidate_root: Path, issue: dict[str, Any]) -> int | None:
    """Reserve before a correction call; internal and outer repairs share this ledger."""
    path = candidate_root / "issue-repair-counts.json"
    key = admission_issue_id(str(issue.get("code") or "issue"), str(issue.get("path") or ""))
    with _candidate_invocation_lock(path):
        counts = load_json(path, {})
        used = int(counts.get(key, 0) or 0)
        if used >= MVG_REPAIR_ATTEMPT_LIMIT:
            return None
        counts[key] = used + 1
        atomic_json(path, counts)
        return used + 1


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
    from _mvg_requirement_accounting import evidence_rows
    refs.update(row['source_ref'].split('#', 1)[0] for row in evidence_rows(proposal)
                if isinstance(row, dict) and isinstance(row.get('source_ref'), str))
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
    test_groups = []
    if isinstance(manifest, dict):
        test_groups.append(manifest.get("tests", []))
    # Capability append proposals carry newly generated tests at the proposal
    # root; normalize those with the same deterministic rule as manifest tests.
    test_groups.append(proposal.get("tests", []))
    seen = set()
    for tests in test_groups:
      for test in tests if isinstance(tests, list) else []:
        marker = id(test)
        if marker in seen:
            continue
        seen.add(marker)
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


def promote_candidate_routing(candidate_root: Path) -> bool:
    """Atomically publish a fully admitted route; pending routes are never read as committed state."""
    pending = candidate_root / "candidate-routing.pending.json"
    committed = candidate_root / "candidate-routing.json"
    if not pending.is_file():
        return False
    os.replace(pending, committed)
    return True


def discard_candidate_routing_pending(candidate_root: Path) -> None:
    """Drop an uncommitted route left by a process interruption."""
    (candidate_root / "candidate-routing.pending.json").unlink(missing_ok=True)

def validate_candidate_routing(rows: list[dict[str, Any]], permitted: dict[str, set[str] | None],
                               requirements: dict[str, dict[str, Any]],
                               prepared: Path | None = None) -> list[str]:
    """Validate a model-owned whole-candidate route without assigning semantics."""
    errors, seen = [], set()
    if not isinstance(rows, list):
        return ["routing_rows_not_array"]
    for row in rows:
        if not isinstance(row, dict):
            errors.append("routing_row_not_object")
            continue
        rid = str(row.get("requirement_id") or "")
        if rid not in permitted or rid in seen:
            errors.append(f"routing_requirement_duplicate_or_foreign:{rid}")
        seen.add(rid)
        disposition = row.get("disposition")
        if disposition == "flow":
            eligible = permitted.get(rid, set())
            flow_id = row.get("flow_id")
            if (eligible is None and not (isinstance(flow_id, str) and re.fullmatch(r"routing-[a-z0-9]+(?:-[a-z0-9]+)*", flow_id))) or (
                    eligible is not None and flow_id not in eligible):
                errors.append(f"routing_flow_outside_evidence:{rid}")
            if any(row.get(key) is not None for key in ("sink_id", "verification_ref", "authority_ref")):
                errors.append(f"routing_flow_refs_forbidden:{rid}")
        elif disposition in {"other_verification", "deferred", "source_gap"}:
            if row.get("flow_id") is not None:
                errors.append(f"routing_nonruntime_flow_forbidden:{rid}")
            if disposition == "other_verification":
                sink_rows = requirements.get(rid, {}).get("non_task_sinks", []) or []
                sinks = {str(item.get("sink_id") or item.get("id")) if isinstance(item, dict) else str(item)
                         for item in sink_rows} if isinstance(sink_rows, list) else set()
                if not sinks or row.get("sink_id") not in sinks:
                    errors.append(f"routing_verification_sink_unavailable:{rid}")
                ref = row.get("verification_ref")
                if not ref or prepared is None or _prepared_reference(prepared, str(ref)) is None:
                    errors.append(f"routing_verification_source_missing:{rid}")
            elif disposition == "deferred":
                ref = row.get("authority_ref")
                if not ref or prepared is None or _prepared_reference(prepared, str(ref)) is None:
                    errors.append(f"routing_deferral_source_missing:{rid}")
            elif any(row.get(key) is not None for key in ("sink_id", "verification_ref", "authority_ref")):
                errors.append(f"routing_gap_invented_evidence:{rid}")
        else:
            errors.append(f"routing_disposition_invalid:{rid}")
    errors.extend(f"routing_requirement_missing:{rid}" for rid in sorted(set(permitted) - seen))
    return sorted(set(errors))


def candidate_routing_schema(identity: str, permitted: dict[str, set[str] | None]) -> dict[str, Any]:
    """Bind each route to its own Requirement/evidenced-flow domain in the CLI."""
    def obj(properties):
        return {"type": "object", "properties": properties, "required": list(properties),
                "additionalProperties": False}
    items = []
    for rid, flows in sorted(permitted.items()):
        properties = {
            "requirement_id": {"type": "string", "const": rid},
            "disposition": {"type": "string", "enum": ["flow", "other_verification", "deferred", "source_gap"]},
            "flow_id": {"anyOf": [{"type": "string", "pattern": r"^routing-[a-z0-9]+(?:-[a-z0-9]+)*$"}, {"type": "null"}]} if flows is None else
                       {"anyOf": [{"type": "string", "enum": sorted(flows)}, {"type": "null"}]} if flows else {"type": "null"},
            "rationale": {"type": "string", "minLength": 1},
            **{key: {"type": ["string", "null"]} for key in ("sink_id", "verification_ref", "authority_ref")},
        }
        for disposition in ("flow", "other_verification", "deferred", "source_gap"):
            variant = dict(properties)
            variant["disposition"] = {"type": "string", "const": disposition}
            if disposition == "flow":
                if flows is not None and not flows:
                    continue
                variant["flow_id"] = (
                    {"type": "string", "pattern": r"^routing-[a-z0-9]+(?:-[a-z0-9]+)*$"}
                    if flows is None else {"type": "string", "enum": sorted(flows)})
                for key in ("sink_id", "verification_ref", "authority_ref"):
                    variant[key] = {"type": "null"}
            else:
                variant["flow_id"] = {"type": "null"}
                if disposition == "other_verification":
                    variant["sink_id"] = {"type": "string", "minLength": 1}
                    variant["verification_ref"] = {"type": "string", "minLength": 1}
                    variant["authority_ref"] = {"type": "null"}
                elif disposition == "deferred":
                    variant["sink_id"] = {"type": "null"}
                    variant["verification_ref"] = {"type": "null"}
                    variant["authority_ref"] = {"type": "string", "minLength": 1}
                else:
                    for key in ("sink_id", "verification_ref", "authority_ref"):
                        variant[key] = {"type": "null"}
            items.append(obj(variant))
    return obj({"schema_version": {"type": "string", "const": SEGMENT_SCHEMA},
                "analysis_identity_sha256": {"type": "string", "const": identity},
                "section": {"type": "string", "const": "routing"},
                "scope_id": {"type": "string", "const": "candidate-routing"},
                "routes": {"type": "array", "minItems": len(permitted), "maxItems": len(permitted),
                           "items": {"anyOf": items} if items else {"type": "object"}}})


def validate_candidate_routing_envelope(value: Any, identity: str,
                                        permitted: dict[str, set[str] | None]) -> list[str]:
    """Validate cached or fresh whole-route envelopes before reuse."""
    if not isinstance(value, dict):
        return ["routing_envelope_not_object"]
    expected = {"schema_version", "analysis_identity_sha256", "section", "scope_id", "routes"}
    if set(value) != expected:
        return ["routing_envelope_keys_invalid"]
    errors: list[str] = []
    if value.get("schema_version") != SEGMENT_SCHEMA:
        errors.append("routing_schema_version_mismatch")
    if value.get("analysis_identity_sha256") != identity:
        errors.append("routing_analysis_identity_mismatch")
    if value.get("section") != "routing" or value.get("scope_id") != "candidate-routing":
        errors.append("routing_envelope_scope_mismatch")
    routes = value.get("routes")
    if not isinstance(routes, list) or len(routes) != len(permitted):
        errors.append("routing_route_count_mismatch")
    else:
        for row in routes:
            if not isinstance(row, dict) or set(row) != {"requirement_id", "disposition", "flow_id", "rationale", "sink_id", "verification_ref", "authority_ref"}:
                errors.append("routing_row_shape_invalid")
                continue
            if any(not isinstance(row.get(key), str) or not row[key].strip()
                   for key in ("requirement_id", "disposition", "rationale")):
                errors.append("routing_row_text_invalid")
            if any(row.get(key) is not None and not isinstance(row[key], str)
                   for key in ("flow_id", "sink_id", "verification_ref", "authority_ref")):
                errors.append("routing_row_ref_invalid")
    if not errors:
        try:
            from _planning_skill_common import validate_output_schema
            with tempfile.TemporaryDirectory() as directory:
                schema_path = Path(directory) / "routing-schema.json"
                output_path = Path(directory) / "routing.json"
                atomic_json(schema_path, candidate_routing_schema(identity, permitted))
                atomic_json(output_path, value)
                validate_output_schema(output_path, schema_path)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            errors.append("routing_schema_invalid:" + str(exc))
    return sorted(set(errors))


def atomic_repair_errors(base: dict[str, Any], changed: dict[str, Any], issue: dict[str, Any],
                         base_sha256: str) -> list[str]:
    """Reject collateral row/field changes against the exact current proposal."""
    if canonical_sha(base) != base_sha256:
        return ["repair_base_hash_mismatch"]
    code = str(issue.get("code") or "")
    rid = str(issue.get("requirement_id") or "")
    flow_id = str(issue.get("flow_id") or "")
    suffix = code.rsplit(":", 1)[-1] if ":" in code else ""
    known_requirements = {str(row.get("requirement_id")) for row in base.get("coverage_table", [])}
    flows = {str(row.get("id")): row for row in base.get("manifest_candidate", {}).get("flows", [])}
    if not rid and suffix in known_requirements:
        rid = suffix
    if not flow_id and suffix in flows:
        flow_id = suffix
    affected_flows = ({flow_id} if flow_id else
                      {key for key, row in flows.items() if rid in row.get("requirement_ids", [])})
    route_change = bool(requirement_route_repair_id(issue)) and rid
    if route_change:
        revised_rows = changed.get("manifest_candidate", {}).get("flows", [])
        affected_flows.update(str(row.get("id")) for row in revised_rows
                              if isinstance(row, dict) and rid in row.get("requirement_ids", []))
    if not rid and not affected_flows:
        return ["repair_dependency_domain_unresolved"] if base != changed else []
    if code.startswith("coverage_"):
        affected_flows = set()
    affected_tasks = {tid for fid in affected_flows for tid in flows.get(fid, {}).get("task_ids", [])}
    affected_tests = {str(tid) for fid in affected_flows for tid in flows.get(fid, {}).get("test_ids", [])}
    for test in changed.get("tests", []):
        if (test.get("flow_id") in affected_flows and test.get("state") == "planned"
                and not planned_verification_errors(test, flows.get(str(test.get("flow_id")), {}))):
            affected_tests.add(str(test.get("id")))
    errors = []
    old_targets = [row for row in base.get("coverage_table", []) if row.get("requirement_id") == rid]
    new_targets = [row for row in changed.get("coverage_table", []) if row.get("requirement_id") == rid]
    if rid and old_targets and len(new_targets) != 1:
        errors.append("repair_target_row_cardinality_invalid")
    revised_flows = {str(row.get("id")): row for row in changed.get("manifest_candidate", {}).get("flows", [])}
    for fid in affected_flows:
        old, new = flows.get(fid, {}), revised_flows.get(fid, {})
        protected = ("id", "task_ids", "source_paths", "test_ids")
        if not route_change:
            protected += ("requirement_ids", "capability_refs")
        for field in protected:
            if field == "test_ids" and set(old.get(field, [])) <= set(new.get(field, [])) <= affected_tests:
                continue
            if old.get(field) != new.get(field):
                errors.append(f"repair_protected_flow_field:{fid}:{field}")
        if route_change:
            old_members = set(old.get("requirement_ids", []))
            new_members = set(new.get("requirement_ids", []))
            if (old_members ^ new_members) - {rid}:
                errors.append(f"repair_unrelated_flow_requirement_change:{fid}")
        if code.startswith("segment_flow_change_review_missing:") and old != new:
            errors.append(f"repair_review_only_flow_changed:{fid}")
    if route_change and rid:
        old_routes = {str(row.get("id")): row for row in flows.values()}
        new_routes = {str(row.get("id")): row for row in revised_flows.values()}
        old_owners = {flow_id for flow_id, row in old_routes.items() if rid in row.get("requirement_ids", [])}
        new_owners = {flow_id for flow_id, row in new_routes.items() if rid in row.get("requirement_ids", [])}
        if len(new_owners) != 1 or old_owners == new_owners:
            errors.append("repair_requirement_route_not_reassigned")
        for flow_id in set(old_routes) | set(new_routes):
            old, new = old_routes.get(flow_id, {}), new_routes.get(flow_id, {})
            if flow_id in old_owners | new_owners:
                if (set(old.get("requirement_ids", [])) ^ set(new.get("requirement_ids", []))) - {rid}:
                    errors.append(f"repair_unrelated_flow_requirement_change:{flow_id}")
                for field in ("capability_refs", "task_ids", "source_paths", "test_ids", "handoffs"):
                    if old.get(field) != new.get(field):
                        errors.append(f"repair_protected_flow_field:{flow_id}:{field}")
            elif old != new:
                errors.append(f"repair_unrelated_flow_change:{flow_id}")
    for key in set(base) | set(changed):
        if key == "manifest_candidate":
            left, right = deepcopy(base.get(key, {})), deepcopy(changed.get(key, {}))
            for field in ("flows", "tests"):
                allowed = affected_flows if field == "flows" else affected_tests
                left[field] = [row for row in left.get(field, []) if str(row.get("id")) not in allowed]
                right[field] = [row for row in right.get(field, []) if str(row.get("id")) not in allowed]
            if left != right:
                errors.append("repair_unrelated_manifest_change")
        elif key in {"coverage_table", "entrypoints", "tests", "change_reviews"}:
            def outside(row):
                if key == "coverage_table":
                    return str(row.get("requirement_id")) != rid if rid else row.get("flow_id") not in affected_flows
                if key == "entrypoints":
                    refs = row.get("implementation_acceptance", [])
                    refs = refs if isinstance(refs, list) else [refs]
                    # Free-form text is not a dependency identifier. Existing
                    # rows may be changed only by exact, structured flow refs.
                    return not set(row.get("flow_ids", [])).intersection(affected_flows)
                return str(row.get("id")) not in (affected_flows if key == "change_reviews" else affected_tests)
            if [row for row in base.get(key, []) if outside(row)] != [row for row in changed.get(key, []) if outside(row)]:
                errors.append(f"repair_unrelated_{key}_change")
        elif base.get(key) != changed.get(key):
            errors.append(f"repair_unrelated_field_change:{key}")
    if code.startswith("routing_reassign:"):
        old_routing = issue.get("base_routes")
        new_routing = issue.get("changed_routes")
        if isinstance(old_routing, list) and isinstance(new_routing, list):
            old_other = [row for row in old_routing if row.get("requirement_id") != rid]
            new_other = [row for row in new_routing if row.get("requirement_id") != rid]
            if old_other != new_other:
                errors.append("repair_unrelated_route_change")
    return sorted(set(errors))


def _canonical_handoffs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Treat omitted optional fields and explicit null as the same handoff."""
    return [{key: value for key, value in row.items()
             if key not in {'contract_refs', 'from', 'to'} or value is not None}
            for row in rows]


def segment_output_schema(*, section: str, identity: str, scope_id: str,
                          available_source_paths: list[str] | None = None,
                          available_contract_paths: list[str] | None = None,
                          allowed_flow_ids: list[str] | None = None,
                          allowed_test_ids: list[str] | None = None,
                          allowed_test_paths: list[str] | None = None,
                          available_reference_paths: list[str] | None = None,
                          available_entrypoint_paths: list[str] | None = None,
                          allowed_change_ids: list[str] | None = None,
                          allowed_requirement_ids: list[str] | None = None,
                          allow_planned_verification: bool = False,
                          proposal_sha256: str | None = None) -> dict[str, Any]:
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
    if section == "flows" and allow_planned_verification and allowed_flow_ids:
        test_id = {"anyOf": [test_id, *[{"type": "string", "pattern": "^" + re.escape(f"verify-{fid}-")
                   + "[a-z0-9][a-z0-9-]*$"} for fid in allowed_flow_ids]]}
    reference_path = nonempty_string
    if available_reference_paths is not None:
        paths = sorted({str(path).replace("\\", "/") for path in available_reference_paths
                        if str(path).strip()})
        # Keep the runner schema bounded. Exact prepared paths are enforced by
        # the local reference gate; a giant path alternation can be rejected by
        # Codex CLI before the model is invoked.
        reference_path = {"type": "string", "enum": paths} if paths else {"type": "string", "const": ""}
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
        "requirement_ids": {"type": "array", "items": ({"type": "string", "enum": allowed_requirement_ids}
                            if allowed_requirement_ids is not None else nonempty_string), "minItems": 1},
        "capability_refs": {"type": "array", "items": nonempty_string, "minItems": 1},
        "task_ids": {"type": "array", "items": integer, "minItems": 1},
        "source_paths": {"type": "array", "items": source_path, "minItems": 1},
        "handoffs": {"type": "array", "items": handoff, "minItems": 1},
        "test_ids": {"type": "array", "items": test_id, "minItems": 1},
    })
    coverage = strict_object({
        "requirement_id": ({"type": "string", "enum": allowed_requirement_ids}
                           if allowed_requirement_ids is not None else nonempty_string), "flow_id": nullable(flow_id),
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
        "flow_ids": {"type": "array", "items": flow_id, "minItems": 1},
        "owner_task": integer, "path": nonempty_string, "symbol": nonempty_string,
        "inputs": flexible_text, "state": flexible_text, "assertions": flexible_text,
        "implementation_acceptance": flexible_text,
    })
    if available_entrypoint_paths is not None:
        prepared_entrypoints = sorted({str(path).replace("\\", "/") for path in available_entrypoint_paths
                                       if str(path).strip()})
        existing_path = {"type": "string", "enum": prepared_entrypoints} if prepared_entrypoints else {
            "type": "string", "const": "__no_prepared_existing_entrypoint__"}
        entrypoint["allOf"] = [{
            "if": {"properties": {"status": {"const": "existing_verified"}}, "required": ["status"]},
            "then": {"properties": {"path": existing_path}},
        }]
    coverage["allOf"] = [{
        "if": {"properties": {"disposition": {"const": "flow"}}, "required": ["disposition"]},
        "then": {"properties": {"verification_ref": {"type": "null"},
                                   "authority_ref": {"type": "null"},
                                   "authority_review": {"type": "null"}}},
    }]
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
    if section == "tests" and allow_planned_verification and allowed_flow_ids:
        for fid in allowed_flow_ids:
            for kind, prefix, suffix, levels in (
                    ("dotnet", "Game.Core.Tests/", ".cs", ["domain-integration"]),
                    ("gdunit", "Tests.Godot/tests/", ".gd", ["scene-method", "engine-input"])):
                test["anyOf"].append(strict_object({
                    **test_common,
                    "id": {"type": "string", "pattern": "^" + re.escape(f"verify-{fid}-") + "[a-z0-9][a-z0-9-]*$"},
                    "flow_id": {"type": "string", "enum": [fid], "const": fid},
                    "state": {"type": "string", "const": "planned"},
                    "kind": {"type": "string", "const": kind},
                    "path": {"type": "string", "pattern": "^" + re.escape(prefix) + ".+" + re.escape(suffix) + "$"},
                    "evidence_level": {"type": "string", "enum": levels},
                    "owner_task": integer,
                    "requirement_ids": {"type": "array", "items": nonempty_string, "minItems": 1},
                    "handoff_indexes": {"type": "array", "items": {"type": "integer", "minimum": 0}, "minItems": 1},
                    "inputs": nonempty_string, "assertions": nonempty_string,
                    "implementation_acceptance": nonempty_string,
                }))
    item_schema = {"flows": flow, "coverage_table": coverage,
                   "entrypoints": entrypoint, "tests": test}[payload_key]
    payload_schema = array(item_schema)
    if ((section == "tests" and allowed_test_ids == [] and not allow_planned_verification)
            or (section == "flows" and allowed_test_ids == [])):
        payload_schema["maxItems"] = 0
    schema = {
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
    if section == "flows" and allowed_change_ids is not None:
        schema["required"].append("change_reviews")
        schema["properties"]["change_reviews"] = array(strict_object({
            "id": {"type": "string", "enum": allowed_change_ids},
            "reason": nonempty_string,
            "authority_ref": reference_path,
            "authority_review": strict_object({
                "status": {"type": "string", "const": "reviewed"},
                "rationale": nonempty_string,
            }),
        }))
    if proposal_sha256 is not None:
        schema["properties"]["proposal_sha256"] = {"type": "string", "const": proposal_sha256}
        schema["required"].append("proposal_sha256")
    return schema


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
    for review in value.get("change_reviews", []) if isinstance(value.get("change_reviews"), list) else []:
        if not isinstance(review, dict):
            continue
        authority = str(review.get("authority_ref") or "").split("#", 1)[0].replace("\\", "/")
        if not authority or _prepared_reference(prepared, authority) is None:
            errors.append(f"segment_change_review_authority_unprepared:{review.get('id', '')}")
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

    incumbent = request.get("incumbent_flow")
    reviews = value.get("change_reviews", [])
    if incumbent is not None and not isinstance(value.get("change_reviews"), list):
        errors.append("segment_change_reviews_missing")
    review_ids: set[str] = set()
    for review in reviews if isinstance(reviews, list) else []:
        if not isinstance(review, dict):
            errors.append("segment_change_review_invalid")
            continue
        review_id = str(review.get("id") or "")
        if section != "flows" or not isinstance(incumbent, dict) or review_id != str(incumbent.get("id")):
            errors.append("segment_change_review_outside_scope")
        if review_id in review_ids:
            errors.append("segment_change_review_duplicate")
        review_ids.add(review_id)
        authority_review = review.get("authority_review")
        if (not str(review.get("reason") or "").strip()
                or not str(review.get("authority_ref") or "").strip()
                or not isinstance(authority_review, dict)
                or authority_review.get("status") != "reviewed"
                or not str(authority_review.get("rationale") or "").strip()):
            errors.append("segment_change_review_invalid")

    if ROUTE_FIELD in value:
        errors.extend(route_errors({**value, "manifest_candidate": {
            "flows": rows if section == "flows" else (flow_context or [])}}, allowed_requirements))

    for row in rows:
        if not isinstance(row, dict):
            continue
        if section == "flows":
            flow_id = str(row.get("id") or "")
            semantic_changed = isinstance(incumbent, dict) and (
                any((key in incumbent) != (key in row) or incumbent.get(key) != row.get(key)
                    for key in ("outcome", "requirement_ids", "capability_refs"))
                or _canonical_handoffs(incumbent.get('handoffs', []))
                != _canonical_handoffs(row.get('handoffs', [])))
            if semantic_changed and flow_id not in review_ids:
                errors.append(f"segment_flow_change_review_missing:{flow_id}")
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
            if "flow_ids" in row and (not row["flow_ids"] or not set(row["flow_ids"]).issubset(known_flow_ids)):
                errors.append("segment_entrypoint_flow_outside_scope")
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
            extension = bool(request.get("allow_planned_verification")
                             and str(row.get("id") or "").startswith(f"verify-{flow_id}-"))
            if allowed_test_paths and not extension and str(row.get("path") or "").replace("\\", "/") not in allowed_test_paths:
                errors.append("segment_test_path_outside_scope")
            test_id = str(row.get("id") or "")
            exact_test_ids = {str(value) for value in request.get("test_ids", [])}
            if scope_id and not (
                    (request.get("allow_exact_test_id") and test_id in exact_test_ids)
                    or extension
                    or (not request.get("allow_exact_test_id") and test_id.startswith(scope_id + "-"))):
                errors.append("segment_test_id_outside_scope")
            if extension:
                flow = next((flow for flow in flow_context or [] if flow.get("id") == flow_id), {})
                errors.extend(planned_verification_errors(row, flow))
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


def planned_verification_errors(test: dict[str, Any], flow: dict[str, Any]) -> list[str]:
    """Additive verification must bind to an actual journey and real owner."""
    errors = []
    test_id = str(test.get("id") or "")
    if str(test.get("flow_id") or "") != str(flow.get("id") or ""):
        errors.append("segment_verification_flow_mismatch")
    if test.get("state") != "planned":
        errors.append("segment_verification_not_planned")
    if (type(test.get("owner_task")) is not int
            or test.get("owner_task") not in flow.get("task_ids", [])):
        errors.append("segment_verification_owner_outside_flow")
    requirements = test.get("requirement_ids")
    if (not isinstance(requirements, list) or not requirements
            or not set(requirements).issubset(flow.get("requirement_ids", []))):
        errors.append("segment_verification_requirements_outside_flow")
    indexes = test.get("handoff_indexes")
    if (not isinstance(indexes, list) or not indexes
            or any(type(i) is not int or i < 0 or i >= len(flow.get("handoffs", [])) for i in indexes)):
        errors.append("segment_verification_handoff_outside_flow")
    for field in ("inputs", "assertions", "implementation_acceptance"):
        if not isinstance(test.get(field), str) or not test[field].strip():
            errors.append(f"segment_verification_missing_{field}")
    if not re.fullmatch(re.escape(f"verify-{flow.get('id')}-") + r"[a-z0-9][a-z0-9-]*", test_id):
        errors.append("segment_verification_id_outside_flow")
    return errors


def bind_planned_verification(proposal: dict[str, Any], baseline: dict[str, Any]) -> None:
    """Append model-owned planned tests to their explicit handoffs, retaining regressions."""
    baseline_tests = {str(row.get("id")) for row in baseline.get("tests", [])}
    flows = {str(row.get("id")): row for row in proposal.get("manifest_candidate", {}).get("flows", [])}
    for test in proposal.get("tests", []):
        if str(test.get("id")) in baseline_tests:
            continue
        fid = str(test.get("flow_id") or "")
        flow = flows.get(fid, {})
        errors = planned_verification_errors(test, flow)
        if errors:
            raise MVGSegmentRoutingError(";".join(errors), [{"code": error, "path": "tests"} for error in errors])
        test_id = str(test["id"])
        if test_id not in flow.get("test_ids", []):
            flow.setdefault("test_ids", []).append(test_id)
        for index in test["handoff_indexes"]:
            handoff = flow["handoffs"][index]
            if test_id not in handoff.get("test_ids", []):
                handoff.setdefault("test_ids", []).append(test_id)


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
        if flow_id in preserved:
            # Existing cumulative flows already have evidence-bound test
            # routes. A generated test segment must not replace each narrow
            # handoff binding with the entire flow's test inventory.
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
        acceptance = load_json(run_dir / f"proposal-attempt-{prior_attempt}-acceptance.json", {})
        if acceptance.get("status") == "rejected":
            continue
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
        if payload.get("proposal_sha256") is not None:
            # Repaired segments are meaningful only inside their accepted
            # proposal; never replay them as independent seeds.
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
    # Only those legacy manifests may resolve fields from task views.  Once a
    # manifest declares explicit membership, it is the frozen MVG boundary;
    # evidence-owner task views must not widen it with governance-only rows.
    for flow in flows:
        missing_requirements = "requirement_ids" not in flow
        missing_capabilities = "capability_refs" not in flow
        if not missing_requirements and not missing_capabilities:
            continue
        legacy_task_ids = {value for value in flow.get("task_ids", []) if type(value) is int}
        for row in task_views or []:
            if not isinstance(row, dict):
                continue
            try:
                task_id = int(row.get("taskmaster_id"))
            except (TypeError, ValueError):
                continue
            if task_id not in legacy_task_ids:
                continue
            requirement_values = (row.get("semantic_refs")
                                  if isinstance(row.get("semantic_refs"), list)
                                  else row.get("requirement_ids"))
            if missing_requirements:
                requirement_ids.update(str(value) for value in (requirement_values or []) if str(value).strip())
            capability_values = row.get("capability_refs")
            if missing_capabilities:
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
        "allow_planned_verification": True,
    }


def _bounded_text(value: Any, limit: int = 480) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[:limit - 3].rstrip() + "..."


def _contract_candidates(contract_refs: set[str], paths: list[str], *, limit: int = 3,
                         required_paths: list[str] | None = None) -> list[str]:
    """Reduce contract evidence to paths plausibly owned by this task slice."""
    required = {str(path).split('#', 1)[0].replace('\\', '/') for path in (required_paths or [])}
    missing = required - set(paths)
    if missing:
        raise ValueError('incumbent_contract_unprepared:' + ','.join(sorted(missing)))
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
        return sorted(required | set(sorted(set(selected))[:limit]))
    if required:
        return sorted(required)
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


def merge_planning_segments(base: dict[str, Any], segments: list[dict[str, Any]], *, repair=False) -> dict[str, Any]:
    """Merge bounded model sections without allowing replacement or deletion."""
    from _mvg_requirement_accounting import key_errors, manifest_key_errors
    shape_errors = key_errors(base) + manifest_key_errors(base)
    for segment in segments:
        if not isinstance(segment, dict):
            raise ValueError('planning_segment_invalid')
        shape_errors += key_errors(segment)
        for field in ('flows', 'tests', 'coverage_table', 'entrypoints'):
            if field in segment and (not isinstance(segment[field], list)
                    or any(not isinstance(row, dict) for row in segment[field])):
                shape_errors.append('planning_segment_' + field + '_invalid')
        for family, key in (('flows', 'id'), ('tests', 'id')):
            if isinstance(segment.get(family), list) and any(
                    not isinstance(row.get(key), str) for row in segment[family] if isinstance(row, dict)):
                shape_errors.append('planning_segment_' + family + '_key_invalid')
    if shape_errors:
        raise ValueError(';'.join(shape_errors))
    result = json.loads(json.dumps(base))
    manifest = result.setdefault("manifest_candidate", {})
    if "tests" not in result and isinstance(manifest.get("tests"), list):
        # Cumulative manifests carry their existing test inventory inside the
        # manifest.  Promote it into the proposal's working section before
        # merging new test segments so baseline flow references stay resolvable.
        result["tests"] = json.loads(json.dumps(manifest["tests"]))
    flows = manifest.setdefault("flows", [])
    flow_map = {str(row.get("id")): row for row in flows if isinstance(row, dict)}
    input_pairs = set()
    input_accounting_keys = set()
    for segment in segments:
        from _mvg_requirement_accounting import VERIFICATION, EVIDENCE, verification_rows, evidence_rows, key_errors
        if VERIFICATION in segment or EVIDENCE in segment:
            errors = key_errors(segment)
            if errors:
                raise ValueError(';'.join(errors))
            prior_authority_ids = {row['requirement_id'] for row in verification_rows(result)}
            result.setdefault(VERIFICATION, verification_rows(result))
            for field, project, keys in ((VERIFICATION, verification_rows, ('requirement_id',)),
                                         (EVIDENCE, evidence_rows, ('requirement_id', 'evidence_id'))):
                if field not in segment:
                    continue
                target = result.setdefault(field, project(result))
                existing = {tuple(row.get(key) for key in keys): row for row in target}
                for row in segment[field]:
                    key = tuple(row.get(key) for key in keys)
                    input_key = (field, *key)
                    if input_key in input_accounting_keys:
                        raise ValueError(field + '_duplicate:' + ':'.join(key) + ':segments')
                    input_accounting_keys.add(input_key)
                    if key in existing and existing[key] != row:
                        if not repair:
                            raise ValueError(field + '_conflict:' + ':'.join(key))
                        existing[key].clear()
                        existing[key].update(deepcopy(row))
                    elif key not in existing:
                        target.append(deepcopy(row))
                        existing[key] = target[-1]
            # Evidence is append-only. Link new immutable evidence to its existing
            # authority row without rewriting disposition, owner or authorization.
            if EVIDENCE in segment:
                for row in segment[EVIDENCE]:
                    authority_row = next((item for item in result.get(VERIFICATION, [])
                        if item.get('requirement_id') == row['requirement_id']), None)
                    if (authority_row is not None and row['requirement_id'] in prior_authority_ids
                            and row['evidence_id'] not in authority_row.get('evidence_ids', [])):
                        authority_row.setdefault('evidence_ids', []).append(row['evidence_id'])
        if ROUTE_FIELD in segment:
            errors = pair_errors(segment[ROUTE_FIELD])
            if errors:
                raise ValueError(";".join(errors))
            if ROUTE_FIELD not in result:
                result[ROUTE_FIELD] = memberships(result)
            target_routes = result[ROUTE_FIELD]
            route_map = {(row["requirement_id"], row["flow_id"]): row for row in target_routes}
            for row in segment[ROUTE_FIELD]:
                pair = (row["requirement_id"], row["flow_id"])
                if pair in input_pairs:
                    raise ValueError(f'requirement_route_pair_duplicate:{pair[0]}:{pair[1]}:segments')
                input_pairs.add(pair)
                if pair in route_map:
                    if route_map[pair] != row and not repair:
                        raise ValueError(f'requirement_route_pair_conflict:{pair[0]}:{pair[1]}')
                    route_map[pair].update(deepcopy(row))
                else:
                    target_routes.append(deepcopy(row))
                    route_map[pair] = target_routes[-1]
        coverage_ids = [row.get("requirement_id") for row in segment.get("coverage_table", []) if isinstance(row, dict)]
        duplicate_ids = sorted({rid for rid in coverage_ids if coverage_ids.count(rid) > 1}, key=str)
        if duplicate_ids:
            raise ValueError(";".join(f"coverage_requirement_duplicate:{rid}" for rid in duplicate_ids))
        if "change_reviews" in segment:
            # Replace reviews for this flow segment so repaired rows cannot
            # retain a stale justification from an earlier proposal attempt.
            replaced_ids = {str(row.get("id")) for row in segment.get("flows", []) if isinstance(row, dict)}
            result["change_reviews"] = [row for row in result.get("change_reviews", [])
                                        if str(row.get("id")) not in replaced_ids]
            result["change_reviews"].extend(json.loads(json.dumps(segment["change_reviews"])))
        for row in segment.get("flows", []) or []:
            if not isinstance(row, dict) or not str(row.get("id") or "").strip():
                continue
            row = deepcopy(row)
            if 'handoffs' in row:
                row['handoffs'] = _canonical_handoffs(row['handoffs'])
            existing = flow_map.get(str(row["id"]))
            if existing is None:
                flows.append(row)
                flow_map[str(row["id"])] = row
            else:
                # Optional null/omitted handoff fields are structurally
                # equivalent. Preserve the incumbent representation so a
                # section merge does not manufacture a semantic delta.
                if (isinstance(existing.get("handoffs"), list)
                        and row.get("handoffs") == _canonical_handoffs(existing["handoffs"])):
                    row["handoffs"] = deepcopy(existing["handoffs"])
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
    if ROUTE_PROJECTION in result and any(ROUTE_FIELD in segment for segment in segments):
        candidate = {key: value for key, value in result.items() if key != ROUTE_PROJECTION}
        known = {rid for flow in flows for rid in flow.get('requirement_ids', [])}
        if not route_errors(candidate, known):
            result.pop(ROUTE_PROJECTION)
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
    reviewed_changes = {
        str(row.get("id"))
        for row in proposal.get("change_reviews", [])
        if isinstance(row, dict)
        and str(row.get("id") or "").strip()
        and str(row.get("reason") or "").strip()
        and str(row.get("authority_ref") or "").strip()
        and isinstance(row.get("authority_review"), dict)
        and row["authority_review"].get("status") == "reviewed"
        and str(row["authority_review"].get("rationale") or "").strip()
    }
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
            for key in ("id", "task_ids", "source_paths", "test_ids"):
                if key in baseline_flow:
                    merged[key] = json.loads(json.dumps(baseline_flow[key]))
            if flow_id not in reviewed_changes or "handoffs" not in merged:
                merged["handoffs"] = deepcopy(baseline_flow.get("handoffs", []))
            if flow_id not in reviewed_changes:
                for key in ("requirement_ids", "capability_refs"):
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
            "allow_planned_verification": bool(planning_scope and planning_scope.get("allow_planned_verification")),
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
                     planning_scope: dict[str, Any] | None = None,
                     repair_issue: dict[str, Any] | None = None) -> tuple[Path, dict[str, Any]]:
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
            evidence_requirements = (requirement_set if requirement_set else {
                str(rid) for view in task_views
                if view.get("taskmaster_id") in baseline_tasks
                for rid in _list_field(view, "semantic_refs")
            })
            requirements = [row for scope in selected for row in scope.get("requirements", [])
                            if str(row.get("requirement_id")) in evidence_requirements]
            requirement_ids = list(dict.fromkeys(row.get("requirement_id") for row in requirements))
            if not requirement_ids:
                # A legacy incumbent without explicit Requirement metadata must
                # never widen every flow to the complete run scope.  Keep only
                # the incumbent's own declared membership; when it is absent,
                # leave the request empty so the candidate is rejected as an
                # evidence gap instead of manufacturing duplicate ownership.
                requirement_ids = sorted(requirement_set)
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

    # Every lineage asks its own model to assign the complete route before any
    # section is expanded. Evidence limits eligible associations, not semantics.
    prepared = run_dir / "analysis-input"
    requirement_context = {str(row["requirement_id"]): row for row in _active_delivery_requirements(semantics)
                           if allowed_requirement_ids is None or str(row["requirement_id"]) in allowed_requirement_ids}
    permitted = {rid: {scope["scope_id"] for scope in flow_scopes
                       if rid in scope.get("requirement_ids", [])} for rid in requirement_context}
    if planning_scope is None:
        # A new manifest has no incumbent flow domain. The model names and
        # groups journeys freely across the selected Capability membership.
        permitted = {rid: None if capability_members.get(rid) else set() for rid in requirement_context}
    route_path = run_dir / "candidate-routing.json"
    pending_route_path = run_dir / "candidate-routing.pending.json"
    repair_code = str((repair_issue or {}).get("code") or "")
    repair_rid = requirement_route_repair_id(repair_issue or {})
    routing_issue = repair_code.startswith("routing_") or bool(repair_rid)
    # Keep the incumbent route snapshot available while building a focused
    # route repair.  Clearing it before extracting the target route loses the
    # only trustworthy source for both the old owner and unrelated mappings.
    # Within a live lineage, a prior proposal's provisional route is useful
    # for repairing its next issue. On process recovery the pending file is
    # discarded before this function is reached, so only committed routing
    # can cross the crash boundary.
    routing = (load_json(pending_route_path, None) or load_json(route_path, None)) if base_proposal is not None else None
    if repair_rid and not isinstance(routing, dict):
        # Older proposals and focused admission tests may not have a route
        # artifact.  Preserve their ordinary section-level repair path; only
        # perform route reassignment when an identity-bound snapshot exists.
        repair_rid = ""
        routing_issue = repair_code.startswith("routing_")
    if routing is not None:
        if pending_route_path.is_file():
            # A pending route can only come from an earlier, locally validated
            # attempt in this live lineage. Preserve its evidence-approved
            # flow assignment while repairing a different issue. Pending
            # routes are removed before crash recovery, so this cannot widen
            # the route domain across a process restart.
            for row in routing.get("routes", []):
                rid = str(row.get("requirement_id") or "")
                flow_id = row.get("flow_id")
                if row.get("disposition") == "flow" and rid in permitted and flow_id:
                    allowed = permitted[rid]
                    if allowed is not None:
                        allowed.add(str(flow_id))
        cached_route_errors = validate_candidate_routing_envelope(routing, identity, permitted)
        cached_route_errors.extend(validate_candidate_routing(
            routing.get("routes", []), permitted, requirement_context, prepared))
        if cached_route_errors:
            raise MVGSegmentRoutingError(";".join(sorted(set(cached_route_errors))), [
                {"code": code, "path": "routing"} for code in sorted(set(cached_route_errors))])
    incumbent_routing = deepcopy(routing) if isinstance(routing, dict) else None
    if not isinstance(routing, dict) or routing_issue:
        routing_prompt = (
            "Assign whole-candidate Requirement coverage before designing sections. Return routing JSON only. "
            "The selected Capability file is the sole Capability authority. Shared context never claims coverage. "
            "Choose exactly one route per Requirement. Frozen manifests use only eligible flow IDs; new manifests "
            "name journeys with routing- lowercase kebab-case IDs. A journey may combine several Capabilities, "
            "and one Capability may participate in several journeys. Task owners supply "
            "evidence, not semantic conclusions. Prefer source_gap when no legitimate runtime journey, declared "
            "non_task_sink with prepared verification, or specification-backed deferral exists. Never invent "
            "a sink or deferral. Runtime route membership will bind every downstream flow/coverage section.\n"
            + json.dumps({"requirements": requirement_context, "permitted_flow_scopes": {
                rid: sorted(ids) if ids is not None else "model-owned-routing-prefix" for rid, ids in permitted.items()}, "capabilities": capabilities,
                "incumbent_flows": load_json(prepared / "existing-manifest.json", {}).get("flows", []),
                "task_views": task_views,
                "available_reference_paths": sorted(path.relative_to(prepared / family).as_posix()
                    for family in ("sources", "references") for path in (prepared / family).rglob("*") if path.is_file())}, ensure_ascii=False)
        )
        route_error = ""
        route_issues: list[dict[str, str]] = []
        route_permitted = permitted
        if repair_rid:
            routing_issue = True
            if isinstance(routing, dict):
                prior_target = next((row for row in routing.get("routes", [])
                                     if row.get("requirement_id") == repair_rid), None)
            else:
                prior_target = None
            if prior_target is None:
                raise MVGSegmentRoutingError("routing_repair_target_missing:" + repair_rid,
                    [{"code": "routing_repair_target_missing:" + repair_rid, "path": "routing"}])
            current_flow = prior_target.get("flow_id")
            if planning_scope is None:
                eligible = None
            else:
                # A frozen flow can receive a Requirement only when that
                # Requirement's own Task evidence and Capability membership
                # intersect the flow's prepared owners/references.
                existing_flows = {
                    str(row.get("id")): row for row in
                    load_json(prepared / "existing-manifest.json", {}).get("flows", [])
                    if isinstance(row, dict) and str(row.get("id") or "").strip()
                }
                requirement_tasks = {
                    int(view["taskmaster_id"]) for view in task_views
                    if str(view.get("taskmaster_id") or "").isdigit()
                    and int(view["taskmaster_id"]) in set(task_ids)
                    and repair_rid in {str(value) for value in (
                        view.get("semantic_refs") if isinstance(view.get("semantic_refs"), list)
                        else _list_field(view, "requirement_ids"))}
                }
                requirement_capabilities = set(capability_members.get(repair_rid, []))
                eligible = set()
                for candidate_flow_id, candidate_flow in existing_flows.items():
                    flow_tasks = {int(value) for value in candidate_flow.get("task_ids", [])
                                  if type(value) is int}
                    flow_capabilities = {str(value) for value in candidate_flow.get("capability_refs", [])
                                         if str(value).strip()}
                    if (requirement_tasks.intersection(flow_tasks)
                            and requirement_capabilities.intersection(flow_capabilities)):
                        eligible.add(candidate_flow_id)
            if not eligible:
                raise MVGSegmentRoutingError("routing_repair_no_evidence:" + repair_rid,
                    [{"code": "routing_repair_no_evidence:" + repair_rid, "path": "routing"}])
            if current_flow:
                eligible.discard(str(current_flow))
            if not eligible:
                raise MVGSegmentRoutingError("routing_repair_no_alternative:" + repair_rid,
                    [{"code": "routing_repair_no_alternative:" + repair_rid, "path": "routing"}])
            route_permitted = {}
            for rid, allowed in permitted.items():
                old_row = next((row for row in routing.get("routes", [])
                                if row.get("requirement_id") == rid), None)
                if old_row is None:
                    raise MVGSegmentRoutingError("routing_repair_target_missing:" + rid,
                        [{"code": "routing_repair_target_missing:" + rid, "path": "routing"}])
                route_permitted[rid] = eligible if rid == repair_rid else (
                    {str(old_row.get("flow_id"))} if old_row.get("disposition") == "flow" else set())
            # Later envelope validation must accept this evidence-authorized
            # alternative, while all unrelated Requirement routes stay fixed.
            permitted[repair_rid] = set(eligible) | {str(current_flow)}
            routing_prompt += ("\nFocused semantic routing repair. Only this Requirement may change route; every other "
                               "route row must be copied exactly. Select one different flow from the evidence-bound "
                               "alternatives or fail closed.\n" + json.dumps({
                                   "target_requirement_id": repair_rid,
                                   "current_route": prior_target,
                                   "eligible_alternative_flow_ids": sorted(eligible),
                                   "all_current_routes": routing.get("routes", []),
                               }, ensure_ascii=False))
        elif routing_issue:
            # Non-Requirement-specific routing diagnostics still use the
            # deterministic whole-route schema and full local validators.
            # They cannot be narrowed safely without a target Requirement.
            route_permitted = permitted
        for retry in range(1, 2 if repair_issue else 4):
            if route_error:
                if reserve_issue_repair(run_dir, route_issues[0]) is None:
                    raise MVGSegmentRoutingError(route_error, route_issues)
            try:
                route_output, route_receipt = invoke(
                    routing_prompt + ("\nCorrect routing errors: " + route_error if route_error else ""), attempt,
                    output_name=f"segments/000-routing-{retry}.json",
                    output_schema_path=workspace / "segment-schemas/routing.json",
                    output_schema=candidate_routing_schema(identity, route_permitted))
                routing = load_json(route_output, {})
                route_errors = validate_candidate_routing(routing.get("routes", []), route_permitted, requirement_context, prepared)
                if repair_rid and not route_errors:
                    changed_route = next((row for row in routing.get("routes", [])
                                          if row.get("requirement_id") == repair_rid), None)
                    if (not changed_route or changed_route.get("disposition") != "flow"
                            or changed_route.get("flow_id") == current_flow):
                        route_errors.append("routing_repair_target_not_reassigned:" + repair_rid)
                    incumbent_routes = {
                        str(row.get("requirement_id")): row
                        for row in (incumbent_routing or {}).get("routes", [])
                        if isinstance(row, dict)
                    }
                    changed_routes = {
                        str(row.get("requirement_id")): row
                        for row in routing.get("routes", []) if isinstance(row, dict)
                    }
                    if any(changed_routes.get(rid) != row
                           for rid, row in incumbent_routes.items() if rid != repair_rid):
                        route_errors.append("routing_repair_unrelated_route_changed")
                receipts.append({"section": "routing", "retry": retry, "receipt": route_receipt})
            except (ValueError, json.JSONDecodeError) as exc:
                if isinstance(exc, MVGGenerationStoppedError):
                    raise
                route_errors = ["routing_schema_invalid:" + str(exc)]
            if not route_errors:
                break
            route_error = ";".join(route_errors)
            route_issues = [{"code": value, "path": "routing"} for value in route_errors]
        else:
            raise MVGSegmentRoutingError(route_error, route_issues)
        # A fresh route is only provisional input until candidate admission.
        atomic_json(pending_route_path, routing)
    envelope_errors = validate_candidate_routing_envelope(routing, identity, permitted)
    envelope_errors.extend(validate_candidate_routing(
        routing.get("routes", []), permitted, requirement_context, prepared))
    if envelope_errors:
        raise MVGSegmentRoutingError(";".join(sorted(set(envelope_errors))), [
            {"code": code, "path": "routing"} for code in sorted(set(envelope_errors))])
    route_errors = validate_candidate_routing(routing.get("routes", []), permitted, requirement_context, prepared)
    if route_errors:
        raise MVGSegmentRoutingError(";".join(route_errors), [{"code": value, "path": "routing"} for value in route_errors])
    routing_by_requirement = {row["requirement_id"]: row for row in routing["routes"]}
    source_gaps = [row["requirement_id"] for row in routing["routes"] if row["disposition"] == "source_gap"]
    if source_gaps:
        raise MVGRoutingSourceGapError([
            rid + ":" + routing_by_requirement[rid]["rationale"] for rid in source_gaps])
    if planning_scope is None:
        routed_flows: dict[str, list[str]] = {}
        for row in routing["routes"]:
            if row["disposition"] == "flow":
                routed_flows.setdefault(row["flow_id"], []).append(row["requirement_id"])
        flow_scopes = []
        for flow_id, requirement_ids in routed_flows.items():
            selected_capabilities = {cid for rid in requirement_ids for cid in capability_members.get(rid, [])}
            evidence_tasks = {int(view["taskmaster_id"]) for view in task_views
                              if str(view.get("taskmaster_id", "")).isdigit()
                              and int(view["taskmaster_id"]) in task_ids
                              and set(requirement_ids).intersection(_list_field(view, "semantic_refs"))}
            flow_scopes.append({"scope_id": flow_id, "requirement_ids": requirement_ids,
                                "requirements": [requirement_context[rid] for rid in requirement_ids],
                                "task_ids": sorted(evidence_tasks),
                                "capabilities": [cap for cap in capabilities.get("capabilities", [])
                                                 if cap.get("capability_id") in selected_capabilities]})
    else:
        for scope in flow_scopes:
            scope["requirement_ids"] = [rid for rid in scope["requirement_ids"]
                                        if routing_by_requirement[rid].get("flow_id") == scope["scope_id"]]
            scope["requirements"] = [row for row in scope["requirements"] if row["requirement_id"] in scope["requirement_ids"]]
        if repair_rid:
            # Rebuild semantic membership from the accepted route, while
            # keeping the incumbent flow IDs and frozen evidence inventories.
            scope_by_id = {str(scope["scope_id"]): scope for scope in flow_scopes}
            for rid, route in routing_by_requirement.items():
                if route.get("disposition") != "flow":
                    continue
                scope = scope_by_id.get(str(route.get("flow_id") or ""))
                if scope is None:
                    continue
                if rid not in scope["requirement_ids"]:
                    scope["requirement_ids"].append(rid)
                if not any(row.get("requirement_id") == rid for row in scope["requirements"]):
                    scope["requirements"].append(requirement_context[rid])
                scope["capabilities"] = [cap for cap in capabilities.get("capabilities", [])
                                         if cap.get("capability_id") in {
                                             cid for requirement_id in scope["requirement_ids"]
                                             for cid in capability_members.get(requirement_id, [])}]
        flow_scopes = [scope for scope in flow_scopes if scope["requirement_ids"]]
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
    # Baseline tests are prepared dependencies even without task-view refs.
    available_test_paths = sorted({
        str(value).replace("\\", "/")
        for row in all_test_views for value in _list_field(row, "test_refs") if str(value).strip()
    } | {
        str(row["path"]).replace("\\", "/")
        for row in frozen_manifest.get("tests", []) if isinstance(row, dict) and row.get("path")
        and _prepared_reference(prepared, str(row["path"]).replace("\\", "/")) is not None
    })
    frozen_tests_by_flow = {
        str(row.get("id")): sorted({str(value) for value in row.get("test_ids", [])
                                    if str(value).strip()})
        for row in frozen_manifest.get("flows", []) if isinstance(row, dict)
    }
    frozen_flows_by_id = {str(row.get("id")): row for row in frozen_manifest.get("flows", [])
                          if isinstance(row, dict)}
    requests: list[dict[str, Any]] = []
    for scope in flow_scopes:
        requests.append({"section": "flows", "scope_id": scope["scope_id"],
                         "requirements": scope["requirements"],
                         "requirement_ids": scope["requirement_ids"],
                         "task_ids": scope["task_ids"],
                         "capabilities": scope["capabilities"],
                         "allow_exact_flow_id": True,
                         "test_ids": sorted(
                             frozen_tests_by_flow.get(scope["scope_id"], [])
                         ) if planning_scope else [],
                         **({"incumbent_flow": frozen_flows_by_id[scope["scope_id"]]}
                            if planning_scope is not None and scope["scope_id"] in frozen_flows_by_id else {})})

    # Flow coverage is accounted for in small Requirement batches after all
    # flow IDs are known. A batch contains only its own Requirement statements.
    active_rows = _active_delivery_requirements(semantics)
    requirement_context = {
        str(row["requirement_id"]): row for row in active_rows
    }
    for scope in build_segment_scope(semantics, task_ids, batch_size=1,
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
                         "task_ids": scoped_tasks,
                         "coverage_routes": [routing_by_requirement[rid] for rid in scope["requirements"]]})

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
    for request in requests:
        if request["section"] == "tests":
            request["allow_exact_flow_id"] = True

    # A hard-issue repair must not replay the segment that produced the issue.
    # Only coverage failures have an independent, provably narrow route. Other
    # issues may cross flow/test/entrypoint boundaries, so invalidate all their
    # dependent sections rather than guessing from a diagnostic string.
    repair_code = str((repair_issue or {}).get("code", ""))
    coverage_only = bool(repair_issue and repair_code.startswith("coverage_"))
    repair_requirement = (repair_code.split(":", 2)[1]
                         if coverage_only and repair_code.count(":") >= 1 else "")
    repair_request_indexes = route_candidate_repair_requests(requests, repair_issue or {}, base_proposal)
    repair_flow_ids: set[str] = set()
    if repair_rid and isinstance(routing, dict):
        old_route = next((row for row in (incumbent_routing or {}).get("routes", [])
                          if row.get("requirement_id") == repair_rid), None)
        new_route = next((row for row in routing.get("routes", [])
                          if row.get("requirement_id") == repair_rid), None)
        repair_flow_ids = {str(row.get("flow_id")) for row in (old_route, new_route)
                           if isinstance(row, dict) and row.get("disposition") == "flow"
                           and row.get("flow_id")}
        for index, request in enumerate(requests, start=1):
            if (request.get("section") == "flows" and request.get("scope_id") in repair_flow_ids) or (
                    request.get("section") == "tests"
                    and repair_flow_ids.intersection(request.get("flow_scope_ids", []))) or (
                    request.get("section") == "entrypoints"
                    and repair_flow_ids.intersection(request.get("flow_scope_ids", []))):
                repair_request_indexes.add(index)

    def needs_repair(index: int, request: dict[str, Any]) -> bool:
        if not repair_issue:
            return False
        if index not in repair_request_indexes:
            return False
        if repair_code.startswith("segment_flow_change_review_missing:"):
            flow_id = repair_code.split(":", 1)[1].strip()
            return request["section"] == "flows" and request.get("scope_id") == flow_id
        if repair_rid:
            if request["section"] == "coverage":
                return repair_rid in request.get("requirement_ids", [])
            if request["section"] == "flows":
                return request.get("scope_id") in repair_flow_ids
            if request["section"] in {"tests", "entrypoints"}:
                return bool(repair_flow_ids.intersection(request.get("flow_scope_ids", [])))
            return False
        if not coverage_only:
            return True
        return (request["section"] == "coverage"
                and (not repair_requirement or repair_requirement in request.get("requirement_ids", [])))

    def execute_request(index: int, request: dict[str, Any], flow_context: list[dict[str, Any]]) -> tuple[int, dict[str, Any], dict[str, Any]]:
        section = request["section"]
        section_contract_paths = contract_paths
        requirements = request["requirement_ids"]
        scoped_tasks = request["task_ids"]
        flow_prefix = ("" if planning_scope is not None else f"{request['scope_id']}-") if section == "flows" else ""
        test_prefix = (f"{request['scope_id']}-"
                       if section == "tests" and planning_scope is None else "")
        prompt_flow_context = flow_context
        if section in {"tests", "entrypoints"} and request.get("flow_scope_ids"):
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
            allow_exact_flow_id=bool(section == "flows"),
            allow_exact_test_id=bool(planning_scope is not None and section == "tests"),
        )
        if planning_scope is not None:
            section_prompt_text += "\nThis is a frozen existing-manifest scope. Do not add obligations outside it. " \
                "Preserve these baseline flow/test IDs and use only these Requirement, Task and source IDs. " \
                "Tests may add the separately schema-authorized planned verification extension within the same journey:\n"
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
            incumbent_contracts = [str(value) for handoff in (request.get('incumbent_flow') or {}).get('handoffs', [])
                                  for value in [handoff.get('contract_ref'), *(handoff.get('contract_refs') or [])]
                                  if value]
            section_contract_paths = _contract_candidates(scoped_refs, contract_paths,
                                                         required_paths=incumbent_contracts)
            section_prompt_text += "\nInline bounded evidence context:\n" + json.dumps({
                "requirements": request["requirements"],
                "capabilities": request.get("capabilities", []),
                "task_views": [row for row in all_task_views
                               if int(row.get("taskmaster_id", -1)) in set(scoped_tasks)],
                "available_source_paths": source_paths,
                "available_contract_paths": section_contract_paths,
                "declared_contract_refs": sorted(scoped_refs),
            }, ensure_ascii=False)
            if request.get("incumbent_flow") is not None:
                authority_paths = [path for path in prepared_reference_paths
                                   if Path(path).suffix.lower() in (".md", ".txt")]
                excerpt_limit = min(6000, 24000 // max(1, len(authority_paths)))
                section_prompt_text += "\nCumulative change authority context:\n" + json.dumps({
                    "incumbent_flow": request["incumbent_flow"],
                    "available_reference_paths": prepared_reference_paths,
                    "authority_evidence": [{"path": path, "sha256": file_sha(_prepared_reference(prepared, path)),
                                            "excerpt": _review_excerpt(_prepared_reference(prepared, path), excerpt_limit)[0]}
                                           for path in authority_paths],
                }, ensure_ascii=False)
                section_prompt_text += (
                    "\nReturn change_reviews alongside flows. Return [] when outcome, requirement_ids and "
                    "capability_refs and handoffs are unchanged. Any change to these fields requires a review row for this "
                    "exact incumbent flow id, with reason, a prepared specification authority_ref (optional "
                    "anchor), and authority_review={status:reviewed,rationale:<specific source-backed reason>}. "
                    "Preserve outcome wording when behavior is unchanged. Do not invent authorization; if "
                    "the prepared specification does not support a change, preserve the incumbent semantic "
                    "fields. This proposal justification is still subject to independent semantic admission."
                )
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
                "available_test_paths": available_test_paths,
                "baseline_tests": [row for row in frozen_manifest.get("tests", [])
                                   if row.get("id") in request.get("test_ids", [])],
                "baseline_test_evidence": [{"path": row["path"],
                    "excerpt": _review_excerpt(_prepared_reference(prepared, row["path"]), 3000)[0]}
                    for row in frozen_manifest.get("tests", [])
                    if row.get("id") in request.get("test_ids", [])
                    and _prepared_reference(prepared, str(row.get("path") or "")) is not None],
            }, ensure_ascii=False)
            if request.get("allow_planned_verification"):
                section_prompt_text += (
                    "\nAdditive verification is allowed inside this exact journey. Baseline implemented tests "
                    "are retained unchanged by the host; return an empty array if no new verification is needed. "
                    "For missing behavior coverage, return concrete planned tests with id verify-<flow_id>-<name>, "
                    "that exact flow_id, a real owner_task from this flow, a nonempty subset of its requirement_ids, "
                    "and zero-based handoff_indexes identifying the exact boundaries tested. Supply concrete inputs, "
                    "assertions and implementation_acceptance. New paths may be not-yet-created files under the "
                    "normal test directories. These rows remain planned; never relabel a baseline implemented test "
                    "or pretend a fixture verifies a branch it does not exercise. The full Requirement statement "
                    "may require additional cases beyond the old tests.\n"
                    + json.dumps({"requirements": [requirement_context[rid] for flow in prompt_flow_context
                        for rid in flow.get("requirement_ids", []) if rid in requirement_context]}, ensure_ascii=False)
                )
        if needs_repair(index, request):
            payload_key = {"flows": "flows", "coverage": "coverage_table",
                           "entrypoints": "entrypoints", "tests": "tests"}[section]
            prior = base_proposal or {}
            rows = (prior.get("manifest_candidate", {}).get(payload_key, [])
                    if section == "flows" else prior.get(payload_key, []))
            if section == "coverage":
                rows = [row for row in rows if row.get("requirement_id") in requirements]
            elif section == "flows":
                rows = [row for row in rows if str(row.get("id", "")) == request["scope_id"]
                        or str(row.get("id", "")).startswith(request["scope_id"] + "-")]
            elif section == "entrypoints":
                rows = [row for row in rows if row.get("owner_task") in scoped_tasks]
            elif section == "tests":
                ids = {str(row.get("id")) for row in prompt_flow_context}
                rows = [row for row in rows if row.get("flow_id") in ids
                        or row.get("id") in request.get("test_ids", [])]
            section_prompt_text += "\nFocused candidate hard-issue repair:\n" + json.dumps({
                "issue": repair_issue, "current_section": rows,
                "proposal_sha256": canonical_sha(base_proposal or {}),
                "instruction": "Echo proposal_sha256. Repair only the named row/fields and preserve other rows exactly. Return the complete routed section. Do not invent reviewed authority or weaken coverage.",
            }, ensure_ascii=False)
        output_name = f"segments/{index:03d}-{section}.json"
        last_error = ""
        for retry in range(1, 2 if repair_issue else 4):
            try:
                if last_error:
                    prior_issues = segment_route_validation_issues(last_error)
                    if prior_issues and reserve_issue_repair(run_dir, prior_issues[0]) is None:
                        raise MVGSegmentRoutingError(last_error, prior_issues)
                output, receipt = invoke(section_prompt_text, attempt,
                                         output_name=output_name,
                                         output_schema_path=workspace / "segment-schemas" / f"{index:03d}-{section}.json",
                                         output_schema=segment_output_schema(
                                              section=section,
                                              identity=identity,
                                              scope_id=request["scope_id"],
                                              available_source_paths=source_paths,
                                              available_contract_paths=section_contract_paths,
                                              allowed_flow_ids=(
                                                  [request["scope_id"]]
                                                  if section == "flows"
                                                  else ([str(row["id"]) for row in prompt_flow_context]
                                                        if section == "tests"
                                                        else [str(row["id"]) for row in prompt_flow_context]
                                                        if section == "coverage"
                                                        else [str(row["id"]) for row in prompt_flow_context]
                                                        if section == "entrypoints" else None)
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
                                                  prepared_reference_paths if section == "coverage" or request.get("incumbent_flow") is not None else None
                                              ),
                                              allowed_change_ids=(
                                                  [str(request["incumbent_flow"]["id"])]
                                                  if request.get("incumbent_flow") is not None else None
                                              ),
                                              allowed_requirement_ids=requirements if section in {"flows", "coverage"} else None,
                                              allow_planned_verification=bool(request.get("allow_planned_verification")),
                                              proposal_sha256=canonical_sha(base_proposal or {}) if needs_repair(index, request) else None,
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
                    available_test_paths=available_test_paths,
                ))
                if needs_repair(index, request) and base_proposal is not None:
                    tentative = merge_planning_segments(base_proposal or {}, [parsed])
                    if not repair_rid:
                        errors.extend(atomic_repair_errors(base_proposal or {}, tentative,
                                                           repair_issue or {}, parsed.get("proposal_sha256", "")))
                if section == "coverage":
                    for row in parsed.get("coverage_table", []):
                        expected = routing_by_requirement.get(str(row.get("requirement_id")), {})
                        if row.get("disposition") != expected.get("disposition"):
                            errors.append("segment_coverage_disposition_route_mismatch")
                        if row.get("disposition") == "flow":
                            expected_scope = str(expected.get("flow_id") or "")
                            if row.get("flow_id") != expected_scope:
                                errors.append("segment_coverage_whole_route_mismatch")
                if errors:
                    raise ValueError(f"MVG segment {section} identity invalid: {'; '.join(errors)}")
                return index, parsed, {"section": section, "index": index, "retry": retry, "receipt": receipt}
            except (json.JSONDecodeError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
                if isinstance(exc, (MVGGenerationStoppedError, MVGSegmentRoutingError)):
                    raise
                last_error = str(exc)
                section_prompt_text += (
                    "\nThe previous response failed deterministic routing/schema validation. "
                    f"Exact errors: {last_error}. Correct every listed route or schema error "
                    "in this retry; do not return a bare section payload or reuse a flow with "
                    "a mismatched Requirement, Capability, or owner Task."
                )
        route_issues = segment_route_validation_issues(last_error)
        if route_issues:
            raise MVGSegmentRoutingError(
                last_error or f"MVG segment {section} failed after retries",
                route_issues,
            )
        raise ValueError(last_error or f"MVG segment {section} failed after retries")

    def execute_batch(batch: list[tuple[int, dict[str, Any]]], flow_context: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any], dict[str, Any]]]:
        if not batch:
            return []
        reusable: list[tuple[int, dict[str, Any], dict[str, Any]]] = []
        pending: list[tuple[int, dict[str, Any]]] = []
        for index, request in batch:
            cached = None if needs_repair(index, request) else load_reusable_segment(
                run_dir,
                current_attempt=attempt,
                index=index,
                section=request["section"],
                identity=identity,
                scope_id=request["scope_id"],
                prepared=prepared,
                available_source_paths=source_paths,
                available_contract_paths=contract_paths,
                available_test_paths=available_test_paths,
                routing_request=request,
                flow_context=flow_context,
            )
            if base_proposal is not None and not needs_repair(index, request):
                key = {"flows": "flows", "coverage": "coverage_table", "entrypoints": "entrypoints", "tests": "tests"}[request["section"]]
                prior_rows = (base_proposal.get("manifest_candidate", {}).get(key, [])
                              if key == "flows" else base_proposal.get(key, []))
                if key == "flows":
                    prior_rows = [row for row in prior_rows if row.get("id") == request["scope_id"]
                                  or str(row.get("id", "")).startswith(request["scope_id"] + "-")]
                elif key == "coverage_table":
                    prior_rows = [row for row in prior_rows if row.get("requirement_id") in request["requirement_ids"]]
                elif key == "entrypoints":
                    prior_rows = [row for row in prior_rows if row.get("owner_task") in request["task_ids"]]
                elif key == "tests":
                    prior_rows = [row for row in prior_rows if row.get("flow_id") in request.get("flow_scope_ids", [])
                                  or row.get("id") in request.get("test_ids", [])]
                cached = {"section": request["section"], key: deepcopy(prior_rows)}
                if key == "flows":
                    cached["change_reviews"] = [deepcopy(row) for row in base_proposal.get("change_reviews", [])
                                                 if row.get("id") in {flow.get("id") for flow in prior_rows}]
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
    if planning_scope is not None:
        final_projection = preserve_frozen_manifest_baseline(
            merge_planning_segments({"manifest_candidate": frozen_manifest}, segments),
            frozen_manifest, planning_scope)
        flow_context = final_projection["manifest_candidate"]["flows"]
        for segment in segments:
            if segment.get("section") == "flows":
                ids = {row.get("id") for row in segment.get("flows", [])}
                segment["flows"] = [deepcopy(row) for row in flow_context if row.get("id") in ids]
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
        # Projection already happened at the flow barrier. Associated sections
        # have consumed those exact final flows; do not rewrite their inputs.
        if final_projection.get("tests") is not None:
            baseline_tests = deepcopy(final_projection["tests"])
            baseline_ids = {str(row.get("id")) for row in baseline_tests}
            extensions = [row for row in assembled.get("tests", []) if str(row.get("id")) not in baseline_ids]
            assembled["tests"] = baseline_tests + extensions
            if planning_scope.get("allow_planned_verification"):
                bind_planned_verification(assembled, frozen_manifest)
    assembled.setdefault("manifest_candidate", {})["tests"] = assembled.get("tests", [])
    output = workspace / f"proposal-attempt-{attempt}.json"
    atomic_json(output, assembled)
    return output, {"attempt": attempt, "segmented": True, "segments": receipts}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _run_dir(root: Path, run_id: str) -> Path:
    from _mvg_planning_boundary import safe_run_dir
    return safe_run_dir(root, run_id)


def _load_run(root: Path, run_id: str) -> tuple[Path, dict[str, Any]]:
    path = _run_dir(root, run_id) / "run.json"
    payload = load_json(path, {})
    if payload.get("schema_version") != RUN_SCHEMA:
        raise ValueError(f"missing or invalid MVG planning run: {run_id}")
    from _mvg_planning_boundary import planning_targets, reject
    if payload.get("run_id") != run_id:
        reject(root, "run_identity_changed", run_id=run_id)
    if payload.get("manifest_path") is not None:
        planning_targets(root, run_id, payload["manifest_path"])
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


def _prepare_impl(
    root: Path,
    *,
    run_id: str,
    capabilities_path: Path,
    task_ids: list[str],
    manifest_path: Path | None,
    allow_unready: bool,
    evidence_refs: list[str] | None = None,
    run_invocation_limit: int | None = None,
) -> dict[str, Any]:
    budget = {"mvg.run_invocation_limit": 192 if run_invocation_limit is None else run_invocation_limit,
              "mvg.run_invocation_limit_source": "default" if run_invocation_limit is None else "explicit"}
    if type(budget["mvg.run_invocation_limit"]) is not int or budget["mvg.run_invocation_limit"] <= 0:
        raise ValueError("mvg_run_invocation_limit_invalid")
    capabilities = load_json(capabilities_path, {})
    if capabilities.get("schema_version") != "newrouge.capabilities.v1":
        raise ValueError("explicit Capability input is missing or invalid")
    run_dir = _run_dir(root, run_id)
    if (run_dir / "run.json").is_file():
        raise ValueError("MVG run already exists; resume its incomplete stage or use a new run ID")
    # A failed readiness/freeze must leave a durable blocked receipt without
    # publishing run.json.  This gives callers one consistent diagnostic even
    # when failure occurs before the immutable bundle is complete.
    run_dir.mkdir(parents=True, exist_ok=True)
    bundle = run_dir / "analysis-input"
    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True)
    from _mvg_input_envelope import freeze_envelope, _reference_path
    readiness = _task_readiness(root, task_ids, allow_unready)
    prior_trace = None
    if manifest_path is not None and manifest_path.is_file():
        from _mvg_requirement_routes import matching_trace, authority_ids
        prior_trace = matching_trace(root, manifest_path, authority_ids(load_json(root / SEMANTICS, {}), capabilities))
        if prior_trace is not None:
            previous = load_json(prior_trace, {})
            historical_refs = []
            for row in previous.get('coverage_table', []):
                key = {'deferred': 'authority_ref', 'other_verification': 'verification_ref'}.get(row.get('disposition'))
                if key and row.get(key):
                    historical_refs.append(str(row[key]))
            from _mvg_requirement_accounting import evidence_rows
            historical_refs.extend(row['source_ref'] for row in evidence_rows(previous)
                                   if isinstance(row, dict) and row.get('source_ref'))
            evidence_refs = [*(evidence_refs or []), prior_trace.relative_to(root).as_posix(), *historical_refs]
    from _mvg_requirement_accounting import runtime_paths, source_path
    runtime_companions = []
    for ref in evidence_refs or []:
        canonical = source_path(ref)
        if canonical.startswith('logs/ci/mvg-acceptance/') and canonical.endswith('/summary.json'):
            runtime_companions.extend(runtime_paths(ref, load_json(repo_path(root, canonical), {})))
    evidence_refs = [*(evidence_refs or []), *runtime_companions]
    envelope = freeze_envelope(root, run_id=run_id, capabilities_path=capabilities_path,
        readiness=readiness, manifest_path=manifest_path, evidence_refs=evidence_refs)

    files: dict[str, str] = {}
    authority: dict[str, str | None] = {}
    if prior_trace is not None:
        files["existing-planning-trace.json"] = _copy_file(root, prior_trace, bundle, "existing-planning-trace.json")
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
        if prior_trace is not None:
            previous = load_json(bundle / 'existing-planning-trace.json', {})
            previous_ids = {row['requirement_id'] for row in previous.get('coverage_table', [])}
            planning_scope['requirement_ids'] = sorted(set(planning_scope['requirement_ids']) | previous_ids)
            envelope['historical_authority_requirement_ids'] = sorted(previous_ids)
        files["existing-manifest.json"] = _copy_file(root, manifest_path, bundle, "existing-manifest.json")
        for flow in existing_manifest.get("flows", []):
            referenced.update(str(p) for p in flow.get("source_paths", []))
            referenced.update(str(h["contract_ref"]) for h in flow.get("handoffs", []))
        referenced.update(str(t["path"]) for t in existing_manifest.get("tests", []))
    for ref in evidence_refs or []:
        normalized_ref = _reference_path(ref)
        path = repo_path(root, normalized_ref)
        if not path.is_file():
            raise ValueError(f"explicit MVG evidence file is missing:{normalized_ref}")
        referenced.add(path.relative_to(root.resolve()).as_posix())
    from _mvg_input_envelope import _acceptance_refs
    for row in _task_view_rows(root):
        for field in ("overlay_refs", "contractRefs", "test_refs"):
            for value in _list_field(row, field):
                text = _reference_path(value)
                if text:
                    referenced.add(text)
        for acceptance in _list_field(row, "acceptance"):
            text = str(acceptance)
            if "Refs:" not in text:
                continue
            for value in _acceptance_refs(acceptance):
                cleaned = _reference_path(value)
                if cleaned:
                    referenced.add(cleaned)
    for value in sorted(referenced):
        try:
            path = repo_path(root, value)
        except ValueError:
            continue
        if path.is_file():
            files[f"references/{value}"] = _copy_file(root, path, bundle, f"references/{value}")

    # Preserve full Chapter 5 owning documents and all classified evidence,
    # rather than exposing only the derived readiness summary to candidates.
    for row in envelope["inventory"]:
        rel = row.get("prepared_path")
        if row["sha256"] is not None and rel not in files:
            files[rel] = _copy_file(root, repo_path(root, row["path"]), bundle, rel)

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
    if prior_trace is not None:
        from _mvg_capability_generation import capability_scopes
        prior = load_json(bundle / "existing-planning-trace.json", {})
        envelope["requirement_routes_protocol"] = "newrouge.requirement-routes.v1"
        envelope["requirement_accounting_protocol"] = "newrouge.requirement-accounting.v1"
        envelope["scopes"] = capability_scopes(capabilities, load_json(root / SEMANTICS, {}), planning_scope,
            accepted_requirement_ids=[row["requirement_id"] for row in prior.get("coverage_table", [])])
    index = {
        "schema_version": "newrouge.mvg-planning-input.v1",
        "planning_completion_protocol": "newrouge.mvg-planning-completion.v1",
        "generation_strategy": "capability-local-selection.v1",
        "requirement_routes_protocol": "newrouge.requirement-routes.v1",
        "requirement_accounting_protocol": "newrouge.requirement-accounting.v1",
        "checkpoint_strategy": "capability-selected-checkpoint.v1",
        "checkpoint_schema_version": "newrouge.mvg-capability-checkpoint.v1",
        "capabilities_sha256": file_sha(capabilities_path),
        "files": files,
        "task_scope": task_ids,
        "planning_scope": planning_scope,
        "authority_inputs": authority,
        "input_envelope": envelope,
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
    envelope.update(budget)
    index.update(budget)
    index["analysis_identity_sha256"] = canonical_sha(index)
    atomic_json(bundle / "analysis-index.json", index)

    state = {
        "schema_version": RUN_SCHEMA,
        "generation_strategy": "capability-local-selection.v1",
        "checkpoint_strategy": index["checkpoint_strategy"],
        "requirement_routes_protocol": index["requirement_routes_protocol"],
        "requirement_accounting_protocol": index["requirement_accounting_protocol"],
        "checkpoint_schema_version": index["checkpoint_schema_version"],
        "planning_completion_protocol": index["planning_completion_protocol"],
        "run_id": run_id,
        "phase": "prepared",
        "created_at_utc": now(),
        "formal_ready": readiness["formal_ready"],
        "analysis_identity_sha256": index["analysis_identity_sha256"],
        "input_envelope_sha256": canonical_sha(envelope),
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
        **budget,
    }
    # The capture predates all copying. Fail closed on changes during prepare
    # before publishing a run that claims to be prepared.
    _validate_input_freshness(root, run_dir, state)
    atomic_json(run_dir / "run.json", state)
    return state


def prepare(
    root: Path,
    *,
    run_id: str,
    capabilities_path: Path,
    task_ids: list[str],
    manifest_path: Path | None,
    allow_unready: bool,
    evidence_refs: list[str] | None = None,
    run_invocation_limit: int | None = None,
) -> dict[str, Any]:
    """Prepare an MVG run and persist one diagnostic for every pre-run failure."""
    run_dir = _run_dir(root, run_id)
    if manifest_path is not None:
        from _mvg_planning_boundary import planning_targets, reject
        try:
            reference = manifest_path.relative_to(root.resolve()).as_posix() if manifest_path.is_absolute() else manifest_path.as_posix()
        except ValueError:
            reject(root, "manifest_outside_repository", run_id=run_id, target=str(manifest_path))
        manifest_path, _ = planning_targets(root, run_id, reference)
    diagnostic = run_dir / "input-freshness.json"
    try:
        if not (run_dir / "run.json").is_file():
            # A retry must not inherit the previous attempt's blocked receipt.
            diagnostic.unlink(missing_ok=True)
        return _prepare_impl(
            root,
            run_id=run_id,
            capabilities_path=capabilities_path,
            task_ids=task_ids,
            manifest_path=manifest_path,
            allow_unready=allow_unready,
            evidence_refs=evidence_refs,
            run_invocation_limit=run_invocation_limit,
        )
    except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError, RuntimeError) as exc:
        if not (run_dir / "run.json").is_file() and (
                not diagnostic.is_file() or load_json(diagnostic, {}).get("status") != "blocked"):
            run_dir.mkdir(parents=True, exist_ok=True)
            atomic_json(run_dir / "input-freshness.json", {
                "status": "blocked",
                "run_id": run_id,
                "analysis_identity_sha256": None,
                "drift": ["prepare:" + _compact_exception_message(exc)],
            })
        raise


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


def _block_selection_for_insufficient_admitted_candidates(
    run_dir: Path, state: dict[str, Any], results: list[dict[str, Any]]
) -> None:
    """Persist the explicit selection gate when three candidates are unavailable."""
    admitted = []
    for row in results:
        label = str(row.get("label") or "")
        if row.get("admitted") and label in MVG_CANDIDATE_LABELS and label not in admitted:
            admitted.append(label)
    reason = "selection_blocked_insufficient_admitted_candidates"
    state.update(
        phase="selection-blocked-insufficient-admitted-candidates",
        selection_status="blocked",
        selection_block_reason=reason,
        admitted_candidates=admitted,
        retired_candidates=[str(row.get("label")) for row in results if not row.get("admitted")],
    )
    for field in ("selected_candidate", "selection_alias", "selection_path", "selection_receipt",
                  "selection_input_candidates", "selection_input_identity", "selection_input_sha256",
                  "selection_execution", "selected_admission_review", "selection_incumbent_path",
                  "selection_incumbent_status", "selection_schema", "model_execution"):
        state.pop(field, None)
    execution_path = run_dir / "model-execution.json"
    try:
        receipt = load_json(execution_path, {}) if execution_path.is_file() else {}
    except (OSError, ValueError, UnicodeError) as exc:
        receipt = {"previous_receipt_error": _compact_exception_message(exc)}
    if not isinstance(receipt, dict):
        receipt = {}
    for field in ("selected_candidate", "selected_alias", "selection_status", "selection_error"):
        receipt.pop(field, None)
    receipt.update({
        "schema_version": "newrouge.mvg-planning-model-execution.v1",
        "backend": state.get("model_backend") or receipt.get("backend"),
        "candidate_attempts": state.get("candidate_attempts", {}),
        "selection_status": "blocked",
        "selection_error": reason,
        "admitted_candidates": admitted,
        "required_admitted_candidates": len(MVG_CANDIDATE_LABELS),
        "candidate_count": len(results),
        "candidate_failures": {
            str(row.get("label")): row.get("summary") or row.get("error")
            for row in results if not row.get("admitted")
        },
    })
    atomic_json(execution_path, receipt)
    atomic_json(run_dir / "run.json", state)
    detail = ("; MVG candidate replacement budget exhausted"
              if state.get("admission_stop_reason") == "replacement_round_budget_exhausted" else "")
    raise ValueError(
        f"{reason}: expected {len(MVG_CANDIDATE_LABELS)} admitted candidates, got {len(admitted)}{detail}"
    )


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
    """Serialize fresh incremental generation before any run state mutation."""
    run_path, state = _load_run(root, run_id)
    if state.get("generation_strategy") == "capability-local-selection.v1":
        from _mvg_capability_checkpoint import coordinator_lock, recover_commit_outcome
        from _mvg_capability_selection import verified_prefix
        with coordinator_lock(run_path.parent):
            # An uncertain replacement must be resolved from disk before any
            # generation status write can overwrite the committed projection.
            run_path, state = _load_run(root, run_id)
            recover_commit_outcome(run_path.parent, state,
                verify=lambda: verified_prefix(root, run_path.parent, state))
            return _generate(root, run_id=run_id, timeout_sec=timeout_sec,
                llm_backend=llm_backend, segmented=segmented)
    return _generate(root, run_id=run_id, timeout_sec=timeout_sec,
        llm_backend=llm_backend, segmented=segmented)


def _generate(root: Path, *, run_id: str, timeout_sec: int, llm_backend: str, segmented: bool = True) -> dict[str, Any]:
    """Generate three isolated MVG proposals, then have an isolated reviewer select one."""
    # Legacy correction runs still use apply_restricted_patch; new candidates
    # are complete independent proposals and never patch another candidate.
    run_path, state = _load_run(root, run_id)
    _validate_input_freshness(root, run_path.parent, state)
    legacy_segmented_run = state.get("generation_strategy") == "independent-candidates-segmented"
    from _mvg_capability_selection import STRATEGY, generate_selected_capabilities
    strategy = state.get("generation_strategy")
    # New prepared runs carry an explicit strategy marker. Synthetic/legacy
    # recovery fixtures without that marker must stay on their historical
    # path so their evidence is not silently reinterpreted.
    incremental = strategy == STRATEGY
    if strategy not in {None, STRATEGY, "independent-candidates-segmented",
                        "independent-candidates-capability-append", "independent-candidates-single"}:
        raise ValueError("MVG generation strategy is unsupported")
    if incremental and not segmented:
        raise ValueError("new MVG runs require Capability-local selection")
    if state.get("formal_ready") is not True:
        raise ValueError("formal MVG planning is blocked until the explicit Chapter 5 scope is ready")
    if llm_backend not in SUPPORTED_LLM_BACKENDS:
        raise ValueError("MVG planning requires one of: " + ", ".join(sorted(SUPPORTED_LLM_BACKENDS)))
    run_dir = run_path.parent
    existing_proposal = load_json(run_dir / "proposal.json", {})
    if not incremental and state.get("selection_status") == "selected" and isinstance(existing_proposal, dict):
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
    state["generation_strategy"] = STRATEGY if incremental else (("independent-candidates-segmented" if legacy_segmented_run else
                                    "independent-candidates-capability-append") if segmented else "independent-candidates-single"
                                    )
    state.setdefault("candidate_attempts", {})
    state.setdefault("candidate_admissions", {})
    state.setdefault("admission_events", [])
    state["model_backend"] = llm_backend
    atomic_json(run_path, state)
    state_lock = threading.Lock()
    def ensure_generation_active() -> None:
        # Candidate contexts are independent.  A runner failure in one slot
        # must not interrupt a sibling that is already generating or repairing;
        # the failed slot is replenished by the durable replacement loop.
        return None

    def reserve_generation_invocation(candidate_root: Path, label: str, lineage: str) -> int:
        ensure_generation_active()
        return reserve_candidate_model_invocation(candidate_root, label, lineage)

    def invoke_for(candidate_root: Path, attempt_root: Path, *,
                   candidate_label: str | None = None, lineage: str | None = None):
        def invoke(prompt_text: str, attempt: int, *, output_name: str | None = None,
                   output_schema_path: Path | None = None,
                   output_schema: dict[str, Any] | None = None,
                   before_dispatch: Any = None) -> tuple[Path, dict[str, Any]]:
            ensure_generation_active()
            relative_output = Path(output_name or f"proposal-attempt-{attempt}.json")
            prompt_stem = relative_output.with_suffix("").as_posix().replace("/", "-")
            # Equivalent to the former `llm_workspace = workspace / "llm-sandbox"`
            # layout, with the candidate and section identities made explicit.
            llm_workspace = attempt_root / "llm-sandbox" / f"attempt-{attempt}" / prompt_stem
            llm_workspace.mkdir(parents=True, exist_ok=True)
            # Segmented requests already contain their scoped evidence inline.
            # Copying the complete bundle defeats the section's input boundary.
            if relative_output.parts[0] != "segments":
                if incremental and relative_output.name == "selection.json":
                    for name in ("A.json", "B.json", "C.json", "accepted-seed.json"):
                        shutil.copyfile(candidate_root / name, llm_workspace / name)
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
            sandbox_schema_path = None
            if output_schema_path is not None:
                # The runner may only read schemas inside its actual model sandbox.
                sandbox_schema_path = llm_workspace / "output-schema.json"
                shutil.copyfile(output_schema_path, sandbox_schema_path)
            if runner is not None:
                prompt_path = llm_workspace / f"prompt-{attempt}-{prompt_stem}.txt"
                prompt_path.write_text(prompt_text, encoding="utf-8", newline="\n")
                _validate_input_freshness(root, run_dir, state)
                if incremental and (llm_workspace / "analysis-input").is_dir():
                    # Later selection receipt validation writes this same
                    # diagnostic; freeze it before the model can see it.
                    _validate_input_freshness(root, llm_workspace, state)
                if incremental:
                    from _mvg_capability_generation import preflight_dispatch
                    preflight_dispatch(runner, workspace=llm_workspace, prompt_path=prompt_path,
                        output_path=output, output_schema=sandbox_schema_path, timeout_sec=timeout_sec)
                request_identity = None
                if incremental:
                    from _mvg_capability_generation import dispatch_request_identity
                    request_identity = dispatch_request_identity(run_dir, runner, workspace=llm_workspace,
                        prompt_path=prompt_path, output_path=output, output_schema=sandbox_schema_path, attempt=attempt)
                reservation = (before_dispatch(request_identity) if incremental else before_dispatch()) if before_dispatch else None
                if incremental and before_dispatch:
                    reservation = deepcopy(state["capability_selection"]["calls"][-1])
                invocation_number = (reserve_generation_invocation(candidate_root, candidate_label, lineage)
                    if not incremental and candidate_label and lineage else reservation)
                dispatch_path = (run_dir / "dispatch-receipts" / f"dispatch-{reservation['number']}.json"
                    if incremental and isinstance(reservation, dict) else None)
                dispatch_receipt = ({**reservation, "status": "reserved"}
                    if dispatch_path is not None else None)
                if dispatch_path is not None:
                    atomic_json(dispatch_path, dispatch_receipt)
                try:
                    receipt = run_isolated_model(
                        runner, workspace=llm_workspace, prompt_path=prompt_path,
                        output_path=output, timeout_sec=timeout_sec,
                        output_schema=sandbox_schema_path,
                    )
                    if dispatch_path is not None:
                        parse_model_json(output)
                        outcome = {"status": "completed", "completed_at_utc": now(),
                            "error_type": None, "output_sha256": file_sha(output)}
                        state["capability_selection"]["calls"][-1]["outcome"] = outcome
                        atomic_json(run_path, state)
                        dispatch_receipt.update(outcome)
                        atomic_json(dispatch_path, dispatch_receipt)
                except Exception as exc:
                    if dispatch_path is not None:
                        outcome = {"status": "failed", "completed_at_utc": now(),
                            "error_type": classify_review_error(exc), "error_class": type(exc).__name__}
                        state["capability_selection"]["calls"][-1]["outcome"] = outcome
                        atomic_json(run_path, state)
                        dispatch_receipt.update(outcome)
                        atomic_json(dispatch_path, dispatch_receipt)
                    raise
                return output, {"attempt": attempt, "invocation": invocation_number, "backend": llm_backend,
                                "backend_info": backend_info, "runner": runner.as_posix(),
                                "returncode": 0, "receipt": receipt}
            reservation = before_dispatch() if before_dispatch else None
            invocation_number = (reserve_generation_invocation(candidate_root, candidate_label, lineage)
                if not incremental and candidate_label and lineage else reservation)
            rc, stdout, cmd = run_llm_exec(
                backend=llm_backend, root=llm_workspace, prompt=prompt_text,
                output_last_message=output, timeout_sec=timeout_sec, codex_configs=[],
                output_schema=sandbox_schema_path,
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

    if incremental:
        return generate_selected_capabilities(root, run_dir, state, backend=llm_backend,
            invoke_factory=lambda budget_root, workspace, label: invoke_for(
                budget_root, workspace, candidate_label=label,
                lineage=f"{label}-r{state['capability_selection'].get('generation', 1)}"),
            selector_factory=lambda workspace: invoke_for(workspace, workspace))

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
        # A process may have stopped after staging a route but before its
        # proposal passed admission. Never resume from that untrusted state.
        discard_candidate_routing_pending(candidate_root)
        prepared = candidate_root / "analysis-input"
        if prepared.exists():
            _validate_input_freshness(root, candidate_root, state)
        else:
            shutil.copytree(run_dir / "analysis-input", prepared)
        for name in ("coverage-skeleton.json", "entrypoint-skeleton.json"):
            source = prepared / name
            if source.is_file():
                shutil.copyfile(source, candidate_root / name)
        candidate_state = deepcopy(state)
        records = list((state.get("candidate_attempts", {}).get(label) or {}).get("attempts", []))
        proposal: dict[str, Any] | None = None
        validation: dict[str, Any] = {"status": "blocked", "errors": ["model_not_run"]}

        # The production path is Capability-local additive generation.  The
        # older flow/section dispatcher remains available to explicit legacy
        # callers and is deliberately bypassed here so a candidate cannot mix
        # whole-proposal and Capability append contexts.
        if segmented and not legacy_segmented_run:
            from _mvg_capability_generation import generate_append
            def append_checkpoint(ledger):
                progress = {key: deepcopy(ledger.get(key)) for key in (
                    "order", "completed", "status", "total_invocations", "errors")}
                current = ledger.get("current") or {}
                progress["current"] = {key: deepcopy(current.get(key)) for key in (
                    "capability_id", "context", "issue", "issue_attempts")}
                with state_lock:
                    state["candidate_attempts"][label] = {
                        "status": "running", "lineage": lineage, "capability_append": progress,
                        "attempt_count": ledger.get("total_invocations", 0), "attempts": []}
                    state["generation_attempts"] = [
                        {"candidate": name, "attempt_count": (state["candidate_attempts"].get(name) or {}).get("attempt_count", 0),
                         "status": (state["candidate_attempts"].get(name) or {}).get("status", "pending")}
                        for name in MVG_CANDIDATE_LABELS]
                    atomic_json(run_path, state)
            append_result = generate_append(
                root, candidate_state, candidate_root,
                invoke_factory=lambda workspace: invoke_for(
                    candidate_root, workspace, candidate_label=label, lineage=lineage),
                before_call=lambda phase: None,
                checkpoint=append_checkpoint,
            )
            if append_result.get("status") == "admitted":
                proposal = append_result["accepted"]
                validation = validate_proposal(root, state, proposal)
                atomic_json(candidate_root / "proposal.json", proposal)
                admission = {"candidate": label, "lineage": lineage, "status": "admitted",
                             "issues": [], "issue_attempts": {},
                             "attempt_count": append_result.get("total_invocations", 0),
                             "workspace": candidate_root.relative_to(run_dir).as_posix(),
                             "proposal_sha256": file_sha(candidate_root / "proposal.json"),
                             "append_ledger": (candidate_root / "capability-append/append-ledger.json").relative_to(root).as_posix(),
                             "review_path": (candidate_root / "admission-review.json").relative_to(root).as_posix(),
                             "review_execution_path": (candidate_root / "admission-execution.json").relative_to(root).as_posix(),
                             "proof_sha256": file_sha(candidate_root / "admission-review.json"),
                             "execution_sha256": file_sha(candidate_root / "admission-execution.json")}
                with state_lock:
                    state["candidate_admissions"][label] = admission
                    state["candidate_attempts"][label] = {
                        "status": "valid", "admission_status": "admitted",
                        "validation": validation,
                        "attempt_count": append_result.get("total_invocations", 0),
                        "lineage": lineage, "proposal_sha256": admission["proposal_sha256"],
                        "capability_append": {key: deepcopy(append_result.get(key)) for key in (
                            "order", "completed", "status", "total_invocations", "errors")},
                    }
                    atomic_json(run_path, state)
                return {"label": label, "valid": True, "admitted": True,
                        "proposal": proposal, "summary": state["candidate_attempts"][label]}
            failure = append_result.get("errors") or [{"code": "capability_append_not_admitted"}]
            admission = {"candidate": label, "lineage": lineage,
                         "status": "retired" if append_result.get("status") == "retired" else "execution-failed",
                         "issues": failure, "attempt_count": append_result.get("total_invocations", 0),
                         "append_terminal": True,
                         "workspace": candidate_root.relative_to(run_dir).as_posix(),
                         "execution_error": {"error_type": str(failure[0].get("code") if isinstance(failure[0], dict) else failure[0])}}
            with state_lock:
                state["candidate_admissions"][label] = admission
                state["candidate_attempts"][label] = {"status": "failed", "admission_status": admission["status"],
                    "attempt_count": append_result.get("total_invocations", 0), "lineage": lineage,
                    "capability_append": {key: deepcopy(append_result.get(key)) for key in (
                        "order", "completed", "status", "total_invocations", "errors")}}
                atomic_json(run_path, state)
            return {"label": label, "valid": False, "admitted": False, "proposal": None,
                    "summary": state["candidate_attempts"][label]}
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
            shared_counts = load_json(candidate_root / "issue-repair-counts.json", {})
            for key, used in shared_counts.items():
                admission_runtime.setdefault("issue_attempts", {})[key] = max(
                    int(used), int(admission_runtime.get("issue_attempts", {}).get(key, 0)))
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
                count_repair=False,
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
                                        and recovered_validation.get("formal_applicable") is True
                                        and not candidate_admission_errors(root, state, proposal)):
                                    admission_review = load_json(admission_review_path, None) if admission_review_path.is_file() else None
                                    if admission_review is None:
                                        try:
                                            admission_review = run_admission_semantic_gate(
                                                root, state, proposal, candidate_root / "admission-review",
                                                runner=runner, timeout_sec=timeout_sec,
                                                invoke=invoke_for(candidate_root, candidate_root / "model-workspace" / f"attempt-{attempt}",
                                                                  candidate_label=label, lineage=lineage),
                                                review_key=f"attempt-{attempt}",
                                                before_invoke=lambda: reserve_generation_invocation(
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
            target = admission_runtime.get("current_issue")
            if segmented and isinstance(target, dict):
                # Reserve before starting any model work. Recovery and local
                # routing corrections consume the same stable issue ledger.
                ledger_path = candidate_root / "issue-repair-counts.json"
                key = admission_issue_id(str(target.get("code") or "issue"), str(target.get("path") or ""))
                with _candidate_invocation_lock(ledger_path):
                    counts = load_json(ledger_path, {})
                    counts[key] = max(int(counts.get(key, 0)),
                                      int(admission_runtime.get("issue_attempts", {}).get(key, 0)))
                    atomic_json(ledger_path, counts)
                reservation = reserve_issue_repair(candidate_root, target)
                if reservation is None:
                    admission_runtime.update(status="retired", retirement_reason="repair_attempt_limit_exhausted")
                    break
                admission_runtime.setdefault("issue_attempts", {})[key] = reservation
                with state_lock:
                    state["candidate_admissions"][label] = deepcopy(admission_runtime)
                    state["admission_events"].append({
                        "candidate": label, "lineage": lineage, "attempt": attempt,
                        "event": "repair-reserved", "issue": target,
                        "issue_attempts": dict(admission_runtime["issue_attempts"]),
                        "status": "repairing"})
                    atomic_json(run_path, state)
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
                current_proposal = deepcopy(proposal)
                pending_admission_review = None
                invoke = invoke_for(candidate_root, attempt_root,
                                    candidate_label=label, lineage=lineage)
                if segmented:
                    output, execution = invoke_segmented(
                        invoke, candidate_root, candidate_state, attempt, candidate_prompt, attempt_root,
                        semantics=load_json(prepared / "semantic-requirements.v1.json", {}),
                        task_ids=[int(value) for value in state.get("task_scope", [])],
                        base_proposal=proposal,
                        planning_scope=state.get("planning_scope"),
                        repair_issue=admission_runtime.get("current_issue"),
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
                if segmented and current_proposal is not None and admission_runtime.get("current_issue"):
                    target = admission_runtime["current_issue"]
                    patch_errors = atomic_repair_errors(current_proposal, proposal, target,
                                                         canonical_sha(current_proposal))
                    old_validation = validate_proposal(root, state, current_proposal)
                    candidate_validation = validate_proposal(root, state, proposal)
                    new_errors = set(candidate_validation.get("errors", [])) - set(old_validation.get("errors", []))
                    patch_errors.extend("repair_new_deterministic_issue:" + str(error) for error in sorted(new_errors))
                    target_code = str(target.get("code") or "")
                    if current_proposal == proposal:
                        patch_errors.append("repair_target_unchanged")
                    elif target_code in old_validation.get("errors", []) and target_code in candidate_validation.get("errors", []):
                        patch_errors.append("repair_target_still_present")
                    if not target_code.startswith("semantic_review_"):
                        fresh_structural_issues = candidate_admission_errors(root, state, proposal)
                        if any(item.get("code") == target_code and str(item.get("path") or "") == str(target.get("path") or "")
                               for item in fresh_structural_issues):
                            patch_errors.append("repair_target_not_reduced")
                    if not patch_errors and target_code.startswith("semantic_review_"):
                        pending_admission_review = run_admission_semantic_gate(
                            root, state, proposal, candidate_root / "admission-review",
                            runner=runner, timeout_sec=timeout_sec,
                            invoke=invoke_for(candidate_root, attempt_root, candidate_label=label, lineage=lineage),
                            review_key=f"attempt-{attempt}",
                            before_invoke=lambda: reserve_generation_invocation(candidate_root, label, lineage))
                        fresh_issues = candidate_admission_errors(root, state, proposal, pending_admission_review)
                        prior_issue_ids = {admission_issue_id(str(item.get("code")), str(item.get("path") or ""))
                                           for item in admission_runtime.get("issues", [])}
                        fresh_issue_ids = {admission_issue_id(str(item.get("code")), str(item.get("path") or ""))
                                           for item in fresh_issues}
                        target_id = admission_issue_id(target_code, str(target.get("path") or ""))
                        if target_id in fresh_issue_ids:
                            patch_errors.append("repair_semantic_target_still_present")
                        if fresh_issue_ids - prior_issue_ids:
                            patch_errors.append("repair_new_semantic_issue")
                    if patch_errors:
                        proposal = current_proposal
                        atomic_json(candidate_root / f"proposal-attempt-{attempt}-acceptance.json", {
                            "status": "rejected", "base_sha256": canonical_sha(current_proposal),
                            "errors": patch_errors})
                        raise MVGSegmentRoutingError(";".join(patch_errors), [target])
                    atomic_json(candidate_root / f"proposal-attempt-{attempt}-acceptance.json", {
                        "status": "accepted", "base_sha256": canonical_sha(current_proposal),
                        "proposal_sha256": canonical_sha(proposal)})
                # Every repaired proposal requires a fresh semantic admission
                # review bound to its new hash; never reuse the prior verdict.
                admission_review = pending_admission_review
                if pending_admission_review is not None:
                    atomic_json(admission_review_path, pending_admission_review)
                elif admission_review_path.is_file():
                    admission_review_path.unlink()
                validation = validate_proposal(root, state, proposal)
                execution["proposal_sha256"] = canonical_sha(proposal)
                execution["deterministic_validation"] = validation
                record.update(execution, status="completed")
                atomic_json(candidate_root / f"proposal-attempt-{attempt}.json", proposal)
            except (RuntimeError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
                # A staged route is not durable input until the candidate
                # passes admission. Keep the committed snapshot untouched.
                if segmented:
                    discard_candidate_routing_pending(candidate_root)
                if segmented and isinstance(exc, MVGSegmentRoutingError) and exc.issues:
                    record.update(status="repairable-failure", error=_compact_exception_message(exc),
                                  error_type=classify_review_error(exc))
                    validation = {"status": "blocked", "errors": [str(exc)]}
                    with state_lock:
                        state["candidate_attempts"][label] = {"attempts": records}
                        atomic_json(run_path, state)
                    if current_proposal is not None:
                        proposal = current_proposal
                        atomic_json(candidate_root / "admission-review" / "proposal.json", current_proposal)
                        atomic_json(candidate_root / f"proposal-attempt-{attempt}-acceptance.json", {
                            "status": "rejected", "base_sha256": canonical_sha(current_proposal),
                            "errors": [str(exc)]})
                    existing_target = admission_runtime.get("current_issue")
                    existing_issues = admission_runtime.get("issues") or []
                    checkpoint_admission_issues(existing_issues if existing_target else exc.issues, attempt)
                    if admission_runtime.get("status") == "retired":
                        break
                    continue
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
            if (validation.get("status") == "passed" and not ready_with_gaps and segmented
                    and not candidate_admission_errors(root, state, proposal or {})):
                if admission_review is None:
                    try:
                        admission_review = run_admission_semantic_gate(
                            root, state, proposal or {}, candidate_root / "admission-review",
                            runner=runner, timeout_sec=timeout_sec,
                            invoke=invoke_for(candidate_root, attempt_root,
                                              candidate_label=label, lineage=lineage),
                            review_key=f"attempt-{attempt}",
                            before_invoke=lambda: reserve_generation_invocation(
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
        if (segmented and not admission_execution_error and not admission_issues
                and validation.get("status") == "passed"
                and validation.get("formal_applicable") is True):
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
            promote_candidate_routing(candidate_root)
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

    def generate_candidate_guarded(label: str) -> dict[str, Any]:
        try:
            result = generate_candidate(label)
        except Exception as exc:
            # Persist a candidate-local execution failure.  Do not propagate a
            # shared stop signal to sibling candidates; they remain eligible
            # for admission and the failed slot can be replaced independently.
            failure = {"error_type": classify_review_error(exc),
                       "error": _compact_exception_message(exc)}
            with state_lock:
                admission = dict(state.get("candidate_admissions", {}).get(label) or {})
                admission.update(candidate=label, status="execution-failed",
                                 execution_error=failure)
                if segmented and not legacy_segmented_run:
                    admission["append_terminal"] = True
                state.setdefault("candidate_admissions", {})[label] = admission
                state.setdefault("candidate_attempts", {})[label] = {
                    "status": "execution-failed", "admission_status": "execution-failed",
                    "admission_error": failure,
                }
                state.setdefault("admission_events", []).append({
                    "candidate": label, "lineage": admission.get("lineage"),
                    "event": "admission-execution-failed", "error": failure,
                })
                atomic_json(run_path, state)
            return {"label": label, "valid": False, "admitted": False,
                    "proposal": None,
                    "summary": {"status": "execution-failed",
                                "admission_status": "execution-failed",
                                "admission_error": failure}}
        return result

    # Replenish a completed failed slot immediately while siblings are still
    # running. A persisted round may fund each slot once; fast slots cannot
    # reset their round count or wait for the initial whole-set barrier.
    results_by_label: dict[str, dict[str, Any]] = {}
    exhausted = False
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(MVG_CANDIDATE_LABELS)) as executor:
        pending = {executor.submit(generate_candidate_guarded, label): label for label in MVG_CANDIDATE_LABELS}
        while pending:
            completed, _ = concurrent.futures.wait(pending, return_when=concurrent.futures.FIRST_COMPLETED)
            for future in completed:
                label = pending.pop(future)
                row = future.result()
                results_by_label[label] = row
                if row.get("admitted"):
                    continue
                retired = state.get("candidate_admissions", {}).get(label) or {"lineage": f"{label}-r1"}
                if retired.get("append_terminal"):
                    # Slice restarts already used the same immutable base and
                    # lineage budget. A full-batch failure must not allocate
                    # another 64 calls implicitly.
                    continue
                replacement = fresh_replacement_lineage(retired, label)
                round_number = int(replacement["lineage"].rsplit("-r", 1)[-1]) - 1
                with state_lock:
                    if round_number > MVG_REPLACEMENT_ROUND_LIMIT:
                        exhausted = True
                        continue
                    while int(state.get("replacement_rounds_used", 0)) < round_number:
                        if reserve_replacement_round(state) is None:
                            exhausted = True
                            break
                    if exhausted and int(state.get("replacement_rounds_used", 0)) < round_number:
                        continue
                    state["candidate_admissions"][label] = replacement
                    state["candidate_attempts"].pop(label, None)
                    state["admission_events"].append({"candidate": label, "lineage": replacement["lineage"],
                        "replacement_of": replacement.get("replacement_of"), "event": "replacement-started"})
                    atomic_json(run_path, state)
                pending[executor.submit(generate_candidate_guarded, label)] = label
    results = [results_by_label[label] for label in MVG_CANDIDATE_LABELS]
    if exhausted:
        state["admission_stop_reason"] = "replacement_round_budget_exhausted"
    valid_results = [row for row in results if row.get("admitted")]
    state["admitted_candidates"] = [str(row.get("label")) for row in valid_results]
    state["retired_candidates"] = [str(row.get("label")) for row in results if not row.get("admitted")]
    if len(valid_results) != len(MVG_CANDIDATE_LABELS):
        _block_selection_for_insufficient_admitted_candidates(run_dir, state, results)

    # The last candidate admission may finish after its final model call.
    # Revalidate the frozen envelope before constructing comparative selection.
    _validate_input_freshness(root, run_dir, state)

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

def validate_proposal(root: Path, state: dict[str, Any], proposal: dict[str, Any], *,
                      append_requirement_ids: set[str] | None = None) -> dict[str, Any]:
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
    from _mvg_requirement_accounting import manifest_key_errors, key_errors
    shape_errors = manifest_key_errors(proposal) + key_errors(proposal)
    if shape_errors:
        return {'status': 'blocked', 'errors': errors + shape_errors, 'formal_applicable': False, 'formal_blockers': []}

    manifest_errors = validate_manifest(root, manifest, executable=False)
    if append_requirement_ids is not None and not manifest.get("flows"):
        # A non-runtime Capability can legitimately precede the first journey.
        # Empty runtime arrays are allowed only at the internal append barrier.
        manifest_errors = [error for error in manifest_errors
                           if error != "At least one flow and test are required"]
    errors.extend(manifest_errors)
    prepared = _run_dir(root, str(state.get("run_id"))) / "analysis-input"
    errors.extend(protocol_errors(load_json(prepared / 'analysis-index.json', {}), proposal))
    from _mvg_requirement_accounting import protocol_errors as accounting_protocol_errors
    errors.extend(accounting_protocol_errors(load_json(prepared / 'analysis-index.json', {}), proposal))
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
    coverage_proposal = proposal
    if append_requirement_ids is not None:
        scoped_requirement_ids = append_requirement_ids
        coverage_proposal = deepcopy(proposal)
        def append_flow_requirements(flow):
            if "requirement_ids" in flow:
                return set(flow["requirement_ids"])
            return {rid for row in prepared_task_views if row.get("taskmaster_id") in flow.get("task_ids", [])
                    for rid in row.get("semantic_refs", row.get("requirement_ids", []))}
        coverage_proposal["manifest_candidate"]["flows"] = [
            flow for flow in manifest.get("flows", [])
            if append_flow_requirements(flow).intersection(append_requirement_ids)]
    errors.extend(coverage_errors(root, coverage_proposal, semantics, capabilities, prepared_task_views,
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
        extension_ids: set[str] = set()
        if allowed.get("allow_planned_verification"):
            flows_by_id = {str(flow.get("id")): flow for flow in manifest.get("flows", [])}
            for test in manifest.get("tests", []):
                if not isinstance(test, dict) or str(test.get("id")) in allowed_tests:
                    continue
                flow = flows_by_id.get(str(test.get("flow_id")), {})
                extension_errors = planned_verification_errors(test, flow)
                if not extension_errors:
                    extension_ids.add(str(test.get("id")))
                else:
                    errors.extend(extension_errors)
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
                if str(value) not in allowed_tests | extension_ids:
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
                if str(test.get("id")) not in allowed_tests | extension_ids:
                    scope_error("test", test.get("id"))
                test_path = str(test.get("path") or "").split("#", 1)[0].replace("\\", "/")
                if test_path not in allowed_test_paths and str(test.get("id")) not in extension_ids:
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
    from _mvg_requirement_accounting import verification_rows
    verification = verification_rows(proposal)
    if isinstance(verification, list):
        formal_blockers.extend('requirement_source_gap:' + row['requirement_id']
                               for row in verification if isinstance(row, dict)
                               and isinstance(row.get('requirement_id'), str) and row.get('disposition') == 'source_gap')
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
    _require_unblocked_selection(state)
    run_dir = run_path.parent
    _validate_input_freshness(root, run_dir, state)
    proposal = load_json(run_dir / "proposal.json", {})
    if state.get("generation_strategy") == "capability-local-selection.v1":
        from _mvg_capability_selection import verify_published_chain
        verify_published_chain(root, run_dir, state)
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
                set(state.get("planning_scope", {}).get("requirement_ids", [])) if isinstance(state.get("planning_scope"), dict) else None,
                root=root, prepared=run_dir / 'analysis-input')
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
requirement_reviews=[{{"requirement_id":"...","verdict":"covered|other_verification|deferred|blocked","rationale":"...","disposition":"flow|other_verification|deferred","route":"flow|other_verification|deferred","flow_id":null,"sink_id":null,"verification_ref":null,"authority_ref":null}}]
with exactly one explicit non-empty rationale per active delivery-relevant Requirement,
Each requirement_review must include repair_action="none|repair_sections|reassign_route". Use none for accepted rows,
repair_sections for evidence/assertion/implementation-obligation defects within the correct journey, and reassign_route
only for wrong journey ownership. Missing verification does not itself require a different flow.
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
        set(scope.get("requirement_ids", [])) if scope else None, root=root, prepared=run_dir / 'analysis-input')
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

    if ROUTE_FIELD in proposal:
        errors = route_errors(proposal, [row.get("requirement_id") for row in proposal.get("coverage_table", [])])
        if errors:
            raise ValueError(";".join(errors))

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
    _require_unblocked_selection(state)
    run_dir = run_path.parent
    _validate_input_freshness(root, run_dir, state)
    chain_errors = []
    global_receipt = None
    if state.get("generation_strategy") == "capability-local-selection.v1":
        from _mvg_capability_selection import verify_published_chain
        try:
            verify_published_chain(root, run_dir, state)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            chain_errors.append("selected_chain_invalid:" + str(exc))
    proposal = load_json(run_dir / "proposal.json", {})
    result = validate_proposal(root, state, proposal)
    from _mvg_planning_review import semantic_review_errors, review_execution_errors
    scope = state.get("planning_scope") if isinstance(state.get("planning_scope"), dict) else None
    review_errors = chain_errors + semantic_review_errors(state, proposal, load_json(run_dir / "semantic-review.json", {}),
        load_json(run_dir / "analysis-input/semantic-requirements.v1.json", {}),
        set(scope.get("requirement_ids", [])) if scope else None)
    review_errors.extend(review_execution_errors(state, proposal,
        load_json(run_dir / "semantic-review-execution.json", {}),
        load_json(run_dir / "semantic-review.json", {})))
    if state.get("generation_strategy") == "capability-local-selection.v1":
        from _mvg_global_audit import verified_audit
        try:
            global_receipt = verified_audit(root, run_dir, state)
            if global_receipt.get("status") != "passed":
                review_errors.append("global_audit_hard_conflicts_or_evidence_gaps")
        except (OSError, ValueError, KeyError, TypeError) as exc:
            review_errors.append("global_audit_invalid:" + str(exc))
    if review_errors:
        result["formal_applicable"] = False
        result["formal_blockers"].extend(review_errors)
    expected_manifest = proposal.get("manifest_candidate", {})
    if result["status"] == "passed":
        baseline = run_dir / "analysis-input/existing-manifest.json"
        if baseline.is_file():
            existing = load_json(baseline, {})
            delta = build_delta(existing, proposal)
            atomic_json(run_dir / "delta.json", delta)
            from update_mvg_baseline import apply_delta
            try:
                expected_manifest = apply_delta(existing, delta, root=root, validate_final=True)
                result["delta_status"] = "passed"
            except ValueError as exc:
                result["delta_status"] = "blocked"
                result.setdefault("errors", []).append(str(exc))
                result["status"] = "blocked"
        else:
            result["delta_status"] = "not_applicable_initial_manifest"
    from _mvg_planning_completion import FIELD, build_report
    result[FIELD] = build_report(root, run_dir, state, proposal, result, global_receipt, expected_manifest)
    result["planning_complete"] = result[FIELD]["planning_complete"]
    atomic_json(run_dir / "validation.json", result)
    state["phase"] = "validated" if result["planning_complete"] is True else "validation-blocked"
    atomic_json(run_path, state)
    return result


def _validate_input_freshness(root: Path, run_dir: Path, state: dict[str, Any]) -> None:
    prepared_index = load_json(run_dir / "analysis-input/analysis-index.json", {})
    for key in ("checkpoint_strategy", "checkpoint_schema_version", "planning_completion_protocol"):
        if prepared_index.get(key) != state.get(key):
            atomic_json(run_dir / "input-freshness.json", {"status": "blocked", "run_id": state.get("run_id"),
                "analysis_identity_sha256": state.get("analysis_identity_sha256"), "drift": ["run:" + key]})
            raise ValueError("MVG checkpoint protocol changed after prepare: " + key)
    prepared_strategy = prepared_index.get("generation_strategy")
    if prepared_strategy is not None and prepared_strategy != state.get("generation_strategy"):
        atomic_json(run_dir / "input-freshness.json", {"status": "blocked", "run_id": state.get("run_id"),
            "analysis_identity_sha256": state.get("analysis_identity_sha256"),
            "drift": ["run:generation_strategy"]})
        raise ValueError("MVG generation strategy changed after prepare")
    # Preserve validation for runs created before the input-envelope schema.
    # New runs carry input_envelope_sha256 and must use the stricter validator.
    index = load_json(run_dir / "analysis-input/analysis-index.json", {})
    requires_envelope = (
        "input_envelope_sha256" in state or "input_envelope" in index
    )
    if not isinstance(index.get("input_envelope"), dict) and requires_envelope:
        from _mvg_input_envelope import validate_envelope
        validate_envelope(root, run_dir / "analysis-input", state)
        return
    if not isinstance(index.get("input_envelope"), dict) and not requires_envelope:
        identity = index.get("analysis_identity_sha256")
        canonical_index = dict(index)
        canonical_index.pop("analysis_identity_sha256", None)
        canonical_index.pop("repository_identity", None)
        if canonical_sha(canonical_index) != identity or identity != state.get("analysis_identity_sha256"):
            raise ValueError("MVG prepared analysis identity changed")
        authority = index.get("authority_inputs")
        if not isinstance(authority, dict) or not authority:
            raise ValueError("MVG original authority identity is incomplete; prepare again")
        drift = []
        for rel, expected in authority.items():
            path = repo_path(root, rel)
            actual = normalized_file_sha(path) if path.is_file() else None
            if actual != expected and (file_sha(path) if path.is_file() else None) != expected:
                drift.append(rel)
        for rel, expected in (index.get("files") or {}).items():
            path = repo_path(run_dir / "analysis-input", rel)
            if not path.is_file() or file_sha(path) != expected:
                drift.append("analysis-input/" + rel)
        atomic_json(run_dir / "input-freshness.json", {
            "status": "blocked" if drift else "current", "drift": sorted(set(drift))})
        if drift:
            raise ValueError("MVG input drift: " + ",".join(sorted(set(drift))))
        return
    from _mvg_input_envelope import validate_envelope
    validate_envelope(root, run_dir / "analysis-input", state)


def _require_unblocked_selection(state: dict[str, Any]) -> None:
    """Historical proposal files cannot override a blocked selection gate."""
    if state.get("selection_status") == "blocked":
        raise ValueError(str(state.get("selection_block_reason") or "MVG selection is blocked"))


def _apply_checkpoint_projection(state: dict[str, Any]) -> dict[str, Any]:
    projection = {key: deepcopy(state.get(key)) for key in (
        "run_id", "analysis_identity_sha256", "generation_strategy", "checkpoint_strategy",
        "checkpoint_schema_version", "capability_selection", "selected_admission_review",
        "selection_status", "selected_candidate")}
    if "planning_completion_protocol" in state:
        projection.update({key: deepcopy(state.get(key)) for key in ("planning_completion_protocol", "manifest_path")})
    projection.update({key: deepcopy(state[key]) for key in (
        "global_audit", "global_conflict_report", "reopen_history", "reopen_contexts") if key in state})
    return projection


def _freeze_apply_checkpoint_binding(root: Path, run_dir: Path, state: dict[str, Any]) -> dict[str, Any] | None:
    """Freeze selected authority in the same atomic write as the apply journal."""
    import hashlib
    from _mvg_capability_checkpoint import enabled
    if not enabled(state):
        return None
    from _mvg_capability_selection import verify_published_chain, candidate_root
    verify_published_chain(root, run_dir, state)
    evidence = {}

    def bind(path: Path, expected: str | None = None, *, canonical: bool = False) -> None:
        resolved = path.resolve()
        if not resolved.is_relative_to(run_dir.resolve()) or not resolved.is_file():
            raise ValueError("MVG checkpoint journal evidence missing: " + str(path))
        raw = resolved.read_bytes()
        raw_sha = "sha256:" + hashlib.sha256(raw).hexdigest()
        actual = canonical_sha(json.loads(raw.decode("utf-8"))) if canonical else raw_sha
        if expected is not None and actual != expected:
            raise ValueError("MVG checkpoint journal evidence changed: " + str(path))
        evidence[resolved.relative_to(root.resolve()).as_posix()] = raw_sha

    selected = state["selected_admission_review"]
    bind(run_dir / "proposal.json", selected["proposal_sha256"], canonical=True)
    bind(repo_path(root, selected["path"]), selected["proof_sha256"])
    bind(repo_path(root, selected["execution_path"]), selected["execution_sha256"])
    from _mvg_global_audit import historical_states
    for saved in [state] + historical_states(run_dir, state):
        saved_review = saved.get("selected_admission_review")
        if saved_review:
            bind(repo_path(root, saved_review["path"]), saved_review["proof_sha256"])
            bind(repo_path(root, saved_review["execution_path"]), saved_review["execution_sha256"])
        for step in saved["capability_selection"]["selected"]:
            pointer = step["checkpoint"]
            bind(repo_path(run_dir, pointer["path"]), pointer["payload_sha256"], canonical=True)
            for name in ("selection", "receipt"):
                bind(repo_path(run_dir, step[name + "_path"]), step[name + "_sha256"])
            comparison = repo_path(run_dir, step["selection_path"]).parent
            bind(comparison / "accepted-seed.json", step["input_identity"]["base_sha256"], canonical=True)
            for alias, label in step["aliases"].items():
                admission = step["admissions"][label]
                proposal = repo_path(run_dir, admission["proposal_path"])
                bind(comparison / (alias + ".json"), canonical_sha(load_json(proposal)), canonical=True)
            for label, admission in step["admissions"].items():
                for name in ("proposal", "proof", "execution"):
                    bind(repo_path(run_dir, admission[name + "_path"]), admission[name + "_sha256"])
                bind(repo_path(run_dir, admission["workspace"]) / "capability-append/append-ledger.json")
                bind(candidate_root(run_dir, label, admission.get("generation", 1)) / "lineage-execution.json")
        for key in ("global_audit", "global_conflict_report"):
            pointer = saved.get(key)
            if pointer:
                bind(repo_path(run_dir, pointer["path"]), pointer["sha256"])
        for call in saved["capability_selection"].get("calls", []):
            request = call.get("request_identity")
            if request:
                for path in repo_path(run_dir, request["workspace"]).rglob("*"):
                    if path.is_file():
                        bind(path)
                outcome = run_dir / "dispatch-receipts" / f"dispatch-{call['number']}.json"
                if outcome.is_file():
                    bind(outcome)
    for history in state.get("reopen_history", []):
        bind(repo_path(run_dir, history["path"]), history["sha256"])
        bind(repo_path(run_dir, history["plan"]["path"]), history["plan"]["sha256"])
    for prepared in run_dir.rglob("analysis-input"):
        if prepared.is_dir():
            for path in prepared.rglob("*"):
                if path.is_file():
                    bind(path)
    for name in ("semantic-review.json", "semantic-review-execution.json", "validation.json", "delta.json"):
        path = run_dir / name
        if path.is_file():
            bind(path)
    projection = _apply_checkpoint_projection(state)
    return {"schema_version": "newrouge.mvg-apply-checkpoint-binding.v1", "projection": projection,
        "projection_sha256": canonical_sha(projection), "evidence": evidence}


def _validate_apply_checkpoint_binding(root: Path, run_dir: Path, state: dict[str, Any], journal: dict[str, Any]) -> None:
    """Check frozen run evidence without rejecting the journal's own output writes."""
    binding = journal.get("result", {}).get("_mvg_checkpoint_binding")
    index = load_json(run_dir / "analysis-input/analysis-index.json", {})
    required = (state.get("checkpoint_strategy") is not None or index.get("checkpoint_strategy") is not None)
    if binding is None:
        if required:
            raise ValueError("MVG checkpoint journal binding missing")
        return
    if (not isinstance(binding, dict)
            or binding.get("schema_version") != "newrouge.mvg-apply-checkpoint-binding.v1"
            or binding.get("projection_sha256") != canonical_sha(binding.get("projection"))
            or binding.get("projection") != _apply_checkpoint_projection(state)
            or not isinstance(binding.get("evidence"), dict) or not binding["evidence"]):
        raise ValueError("MVG checkpoint journal binding changed")
    for relative, expected in binding["evidence"].items():
        path = repo_path(root, relative)
        if (not path.is_relative_to(run_dir.resolve()) or not path.is_file() or file_sha(path) != expected):
            raise ValueError("MVG checkpoint journal evidence changed: " + relative)


def _validate_apply_accounting(root: Path, run_dir: Path, state: dict[str, Any], journal: dict[str, Any]) -> None:
    """Validate frozen accounting and bind both transaction payloads before writes.

    The generic journal subsequently checks every original authority except its
    owned targets, which may already contain this transaction's after-image.
    Never rewrite a historical proposal, proof, checkpoint or completed journal.
    """
    from _mvg_requirement_accounting import boundary_errors, freeze_accounting_sources, PROTOCOL_FIELD, PROTOCOL
    from _mvg_requirement_routes import authority_ids
    from _mvg_planning_review import semantic_review_errors, review_execution_errors
    prepared = run_dir / 'analysis-input'
    index = load_json(prepared / 'analysis-index.json', {})
    if (journal.get('schema_version') != 'newrouge.planning-apply-journal.v1'
            or journal.get('status') not in {'pending', 'complete'}):
        raise ValueError('MVG journal accounting transaction invalid')
    if (not isinstance(index, dict) or not isinstance(index.get('authority_inputs'), dict)
            or journal.get('authority_inputs') != index['authority_inputs']):
        raise ValueError('MVG journal accounting authority binding invalid')
    if 'input_envelope' in index or 'input_envelope_sha256' in state:
        from _mvg_input_envelope import validate_envelope
        validate_envelope(root, prepared, state, check_originals=False)
    else:
        original = {key: value for key, value in index.items()
                    if key not in {'analysis_identity_sha256', 'repository_identity'}}
        if canonical_sha(original) != state.get('analysis_identity_sha256'):
            raise ValueError('MVG journal prepared analysis identity changed')
        for relative, expected in index.get('files', {}).items():
            path = repo_path(prepared, relative)
            if not path.is_file() or file_sha(path) != expected:
                raise ValueError('MVG journal prepared evidence changed:' + relative)
    proposal = load_json(run_dir / 'proposal.json', {})
    semantics = load_json(prepared / 'semantic-requirements.v1.json', {})
    capabilities = load_json(prepared / 'capabilities.v1.json', {})
    if (not isinstance(proposal, dict) or not isinstance(semantics, dict)
            or not isinstance(semantics.get('requirements'), list)
            or not isinstance(capabilities, dict) or not isinstance(capabilities.get('capabilities'), list)
            or any(not isinstance(row, dict) for row in semantics['requirements'])
            or any(not isinstance(row, dict) or not isinstance(row.get('requirement_ids'), list)
                   for row in capabilities['capabilities'])):
        raise ValueError('MVG journal accounting frozen object invalid')
    required = authority_ids(semantics, capabilities)
    scope = state.get('planning_scope')
    if isinstance(scope, dict):
        required &= set(scope.get('requirement_ids', []))
    errors = boundary_errors(proposal, required, root=root, prepared=prepared, check_originals=False)
    from _mvg_requirement_accounting import verification_rows
    if proposal.get('planning_status') != 'ready_for_validation':
        errors.append('planning_status_not_ready')
    if not isinstance(proposal.get('gaps'), list) or proposal['gaps']:
        errors.append('unresolved_planning_gaps')
    errors += ['requirement_source_gap:' + str(row.get('requirement_id'))
               for row in verification_rows(proposal) if isinstance(row, dict) and row.get('disposition') == 'source_gap']
    if (proposal.get('schema_version') != PROPOSAL_SCHEMA
            or proposal.get('analysis_identity_sha256') != state.get('analysis_identity_sha256')):
        errors.append('journal_proposal_identity_invalid')
    review = load_json(run_dir / 'semantic-review.json', {})
    errors += semantic_review_errors(state, proposal, review, semantics, required,
        root=root, prepared=prepared, check_originals=False)
    errors += review_execution_errors(state, proposal,
        load_json(run_dir / 'semantic-review-execution.json', {}), review)
    if errors:
        raise ValueError('MVG journal accounting invalid:' + ';'.join(errors))
    result = journal.get('result')
    entries = journal.get('entries')
    expected_trace = (FORMAL_TRACE_ROOT / (str(state['run_id']) + '.json')).as_posix()
    expected_manifest = state.get('manifest_path')
    if (not isinstance(result, dict) or not isinstance(entries, list)
            or len(entries) != 2 or any(not isinstance(row, dict) or not isinstance(row.get('path'), str)
                                      or not isinstance(row.get('payload'), dict) for row in entries)
            or {row['path'] for row in entries} != {expected_trace, expected_manifest}
            or result.get('trace_path') != expected_trace or result.get('manifest_path') != expected_manifest):
        raise ValueError('MVG journal accounting target binding invalid')
    if (result.get('status') != 'applied' or not isinstance(result.get('manifest_sha256'), str)
            or not isinstance(result.get('post_apply_task_readiness'), list)
            or any(not isinstance(row, dict) for row in result['post_apply_task_readiness'])
            or not isinstance(result.get('handoff_review_required_tasks'), list)
            or any(not isinstance(task, str) for task in result['handoff_review_required_tasks'])
            or ('planning_complete' in result and result['planning_complete'] is not True)
            or ('runtime_verified' in result and result['runtime_verified'] is not False)
            or ('chapter6_ready' in result and result['chapter6_ready'] is not False)):
        raise ValueError('MVG journal accounting result invalid')
    if index.get(PROTOCOL_FIELD) == PROTOCOL and any(result.get(field) is not expected
            for field, expected in (('planning_complete', True), ('runtime_verified', False), ('chapter6_ready', False))):
        raise ValueError('MVG journal accounting result protocol fields missing')
    targets = {row['path']: row['payload'] for row in entries}
    if any(row.get('mutable_json_keys_after_complete', []) not in (
            [], ['handoff_bindings'] if row['path'] == expected_trace else []) for row in entries):
        raise ValueError('MVG journal accounting mutable target binding invalid')
    trace, manifest = targets[expected_trace], targets[expected_manifest]
    from _mvg_planning_completion import FIELD, PROTOCOL_FIELD as COMPLETION_PROTOCOL_FIELD, PROTOCOL as COMPLETION_PROTOCOL, bound_report
    report = trace.get(FIELD)
    required_report = index.get(COMPLETION_PROTOCOL_FIELD) == COMPLETION_PROTOCOL or report is not None or FIELD in result
    if required_report:
        validation = load_json(run_dir / 'validation.json', {})
        if (report is None or result.get(FIELD) != report or validation.get(FIELD) != report
                or bound_report(trace, manifest, expected_manifest).get('planning_complete') is not True
                or report.get('binding', {}).get('audit_ref') != state.get('global_audit')):
            raise ValueError('MVG journal final completion binding invalid')
    errors = boundary_errors(trace, required, root=root, prepared=prepared, check_originals=False)
    projected = (project_routes(proposal) if 'requirement_route_memberships' in trace
                 or index.get('requirement_routes_protocol') is not None else deepcopy(proposal))
    if any(trace.get(key) != value or key not in trace for key, value in projected.items()):
        errors.append('journal_trace_proposal_binding_invalid')
    baseline = load_json(prepared / 'existing-manifest.json', None)
    if baseline is not None:
        from update_mvg_baseline import apply_delta
        delta = build_delta(baseline, proposal)
        if load_json(run_dir / 'delta.json', None) != delta:
            errors.append('journal_delta_proposal_binding_invalid')
        expected = apply_delta(baseline, delta, root=root, validate_final=True)
    else:
        expected = proposal.get('manifest_candidate')
    digest = text_sha(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    if (manifest != expected or trace.get('applied_manifest_candidate') != manifest
            or trace.get('applied_manifest_path') != expected_manifest
            or trace.get('applied_manifest_sha256') != digest or result.get('manifest_sha256') != digest):
        errors.append('journal_manifest_proposal_binding_invalid')
    if index.get(PROTOCOL_FIELD) == PROTOCOL:
        if trace.get(PROTOCOL_FIELD) != PROTOCOL:
            errors.append('journal_accounting_protocol_changed')
        if trace.get('requirement_accounting_sources') != freeze_accounting_sources(proposal, prepared)['requirement_accounting_sources']:
            errors.append('journal_accounting_sources_binding_invalid')
    if errors:
        raise ValueError('MVG journal accounting invalid:' + ';'.join(errors))


def apply(root: Path, *, run_id: str, confirm: bool) -> dict[str, Any]:
    if not confirm:
        raise ValueError("MVG planning apply requires --confirm")
    run_path, state = _load_run(root, run_id)
    _require_unblocked_selection(state)
    run_dir = run_path.parent
    from _planning_apply_journal import create_journal, resume_journal
    journal_path = run_dir / "apply-journal.json"
    if journal_path.is_file():
        journal = load_json(journal_path, {})
        from _mvg_planning_boundary import validate_journal_targets
        validate_journal_targets(root, run_id, state.get("manifest_path"), journal)
        try:
            _validate_apply_checkpoint_binding(root, run_dir, state, journal)
            _validate_apply_accounting(root, run_dir, state, journal)
        except (TypeError, KeyError, AttributeError, UnicodeError) as exc:
            raise ValueError('MVG journal accounting malformed:' + type(exc).__name__) from exc
        result = dict(resume_journal(root, journal_path, atomic_json))
        result.pop("_mvg_checkpoint_binding", None)
        from _mvg_planning_completion import FIELD, unavailable
        if FIELD not in result and "planning_complete" in result:
            # Preserve historical journal bytes while refusing a new completion
            # authorization from its cached pre-protocol boolean.
            result[FIELD] = unavailable()
            result["planning_complete"] = None
        state.update(phase="applied", applied=True, applied_manifest_sha256=result["manifest_sha256"],
            post_apply_task_readiness=result["post_apply_task_readiness"],
            involved_task_ids=result["handoff_review_required_tasks"],
            handoff_review_required_tasks=result["handoff_review_required_tasks"])
        trace = load_json(root / result["trace_path"], {})
        state["handoff_bindings"] = dict(trace.get("handoff_bindings") or {})
        atomic_json(run_path, state)
        atomic_json(run_dir / "apply-summary.json", result)
        return result
    if state.get("generation_strategy") == "capability-local-selection.v1":
        from _mvg_capability_selection import verify_published_chain
        verify_published_chain(root, run_dir, state)
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
    from _mvg_planning_completion import FIELD, bound_report
    if validation.get("planning_complete") is not True:
        raise ValueError("MVG final planning completion is blocked")
    if file_sha(root / str(state["capabilities_path"])) != state.get("capabilities_sha256"):
        raise ValueError("selected Capability input changed after MVG planning prepare")

    if not state.get("manifest_path"):
        raise ValueError("MVG apply requires an explicit --manifest destination from prepare")
    from _mvg_planning_boundary import planning_targets
    manifest_path, trace_path = planning_targets(root, run_id, state["manifest_path"])
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

    trace = project_routes(proposal)
    from _mvg_requirement_accounting import PROTOCOL_FIELD, PROTOCOL
    if state.get(PROTOCOL_FIELD) == PROTOCOL:
        trace[PROTOCOL_FIELD] = PROTOCOL
        from _mvg_requirement_accounting import freeze_accounting_sources
        trace.update(freeze_accounting_sources(proposal, run_dir / 'analysis-input'))
    trace["applied_manifest_candidate"] = deepcopy(updated)
    trace["applied_manifest_path"] = manifest_path.resolve().relative_to(root.resolve()).as_posix()
    trace["applied_manifest_sha256"] = text_sha(json.dumps(updated, ensure_ascii=False, indent=2) + "\n")
    trace["capabilities_sha256"] = state["capabilities_sha256"]
    trace["applied_at_utc"] = now()
    trace[FIELD] = deepcopy(validation[FIELD])
    if bound_report(trace, updated, state["manifest_path"]).get("planning_complete") is not True:
        raise ValueError("MVG final planning completion does not match applied projection")
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
        "planning_complete": validation[FIELD]["planning_complete"],
        FIELD: deepcopy(validation[FIELD]),
        "runtime_verified": False,
        "chapter6_ready": False,
        "handoff_review_required_tasks": involved,
        "handoff_note": "Bind current Chapter 5 readiness for ordinary tasks; actual milestone owners also require the existing manifest-bound milestone handoff.",
        "post_apply_task_readiness": readiness,
    }
    authority = load_json(run_dir / "analysis-input/analysis-index.json", {})["authority_inputs"]
    binding = _freeze_apply_checkpoint_binding(root, run_dir, state)
    if binding is not None:
        result["_mvg_checkpoint_binding"] = binding
    from _mvg_planning_boundary import planning_targets
    planning_targets(root, run_id, state["manifest_path"])
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
    from _mvg_planning_boundary import handoff_target, planning_targets
    if out_path is not None:
        out_path = handoff_target(root, run_id, out_path)
    _, trace_path = planning_targets(root, run_id, state.get("manifest_path"))
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
    p_prepare.add_argument("--run-invocation-limit", type=int, default=None)

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

    p_audit = sub.add_parser("audit")
    p_audit.add_argument("--run-id", required=True)
    p_audit.add_argument("--conflict-report", default="")
    p_audit.add_argument("--conflict-report-sha256", default="")
    p_reopen_plan = sub.add_parser("reopen-plan")
    p_reopen_plan.add_argument("--run-id", required=True)
    p_reopen_plan.add_argument("--audit", required=True)
    p_reopen_plan.add_argument("--audit-sha256", required=True)
    p_reopen = sub.add_parser("reopen")
    p_reopen.add_argument("--run-id", required=True)
    p_reopen.add_argument("--plan", required=True)
    p_reopen.add_argument("--plan-sha256", required=True)

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
        # Preserve lexical CLI spelling until output validation; repo_path resolves
        # links and would otherwise conceal an absolute path or directory alias.
        from _mvg_planning_boundary import run_directory_path, safe_reference, planning_targets, handoff_target
        run_directory_path(root, args.run_id)
        if args.command == "prepare":
            planning_targets(root, args.run_id, args.manifest)
        if args.command == "rebind-handoff" and args.out:
            safe_reference(root, args.out)
            handoff_target(root, args.run_id, root / args.out)
        if args.command == "prepare":
            result = prepare(
                root,
                run_id=args.run_id,
                capabilities_path=repo_path(root, args.capabilities),
                task_ids=[str(value) for value in args.task_id],
                manifest_path=repo_path(root, args.manifest),
                allow_unready=bool(args.allow_unready_draft),
                evidence_refs=args.evidence_ref,
                run_invocation_limit=args.run_invocation_limit,
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
        elif args.command in {"audit", "reopen-plan", "reopen"}:
            from _mvg_global_audit import operate
            if args.command == "audit":
                if bool(args.conflict_report) != bool(args.conflict_report_sha256):
                    raise ValueError("audit requires both --conflict-report and --conflict-report-sha256")
                options = {"conflict_report": str(repo_path(root, args.conflict_report)) if args.conflict_report else None,
                    "conflict_report_sha256": args.conflict_report_sha256 or None}
            elif args.command == "reopen-plan":
                options = {"audit_path": args.audit, "audit_sha256": args.audit_sha256}
            else:
                options = {"plan_path": args.plan, "plan_sha256": args.plan_sha256}
            result = operate(root, run_id=args.run_id, operation=args.command, **options)
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
