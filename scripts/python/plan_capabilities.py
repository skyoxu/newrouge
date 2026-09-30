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


def generate(root: Path, *, run_id: str, runner: Path, timeout_sec: int) -> dict[str, Any]:
    run_path, state = _load_run(root, run_id)
    if state.get("formal_ready") is not True:
        raise ValueError("formal generation is blocked until the explicit Chapter 5 scope is ready")
    runner_info = inspect_isolated_runner(runner)
    run_dir = run_path.parent
    prompt_sha = text_sha(CANDIDATE_PROMPT)
    outputs = []
    for index in range(1, 4):
        label = f"candidate-{index}"
        workspace = run_dir / "isolated-workspaces" / label
        if workspace.exists():
            shutil.rmtree(workspace)
        workspace.mkdir(parents=True)
        _copy_analysis(run_dir, workspace)
        prompt_path = workspace / "prompt.txt"
        prompt_path.write_text(CANDIDATE_PROMPT, encoding="utf-8", newline="\n")
        output = workspace / "candidate.json"
        receipt = run_isolated_model(
            runner,
            workspace=workspace,
            prompt_path=prompt_path,
            output_path=output,
            timeout_sec=timeout_sec,
        )
        candidate = parse_model_json(output)
        ledger = load_json(workspace / "analysis-input/source-blocks.v1.json", {})
        semantics = load_json(workspace / "analysis-input/semantic-requirements.v1.json", {})
        errors = validate_candidate(
            candidate, ledger, semantics, str(state["analysis_identity_sha256"])
        )
        persisted = run_dir / "candidates" / f"{label}.json"
        atomic_json(persisted, candidate)
        meta = {
            "candidate": label,
            "model": runner_info.get("model"),
            "runner": runner_info,
            "prompt_sha256": prompt_sha,
            "analysis_identity_sha256": state["analysis_identity_sha256"],
            "output_sha256": file_sha(persisted),
            "validation_errors": errors,
            "receipt": receipt,
        }
        atomic_json(run_dir / "candidates" / f"{label}.meta.json", meta)
        state.setdefault("candidate_attempts", {})[label] = meta
        outputs.append({"candidate": label, "valid": not errors, "errors": errors})
    state["phase"] = "candidates-generated"
    state["runner"] = runner_info
    atomic_json(run_path, state)
    return {"run_id": run_id, "candidates": outputs}


def review(root: Path, *, run_id: str, runner: Path, timeout_sec: int) -> dict[str, Any]:
    run_path, state = _load_run(root, run_id)
    run_dir = run_path.parent
    labels = [f"candidate-{index}" for index in range(1, 4)]
    for label in labels:
        meta = state.get("candidate_attempts", {}).get(label, {})
        if meta.get("validation_errors"):
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

    workspace = run_dir / "isolated-workspaces" / "review"
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
    receipt = run_isolated_model(
        runner, workspace=workspace, prompt_path=prompt_path,
        output_path=output, timeout_sec=timeout_sec,
    )
    result = parse_model_json(output)
    if result.get("schema_version") != REVIEW_SCHEMA:
        raise ValueError("invalid review schema")
    selected = result.get("selected")
    if selected is not None and selected not in anonymous:
        raise ValueError("review selected an unknown anonymous candidate")
    if result.get("status") == "selected" and selected is None:
        raise ValueError("selected review must name one candidate")
    if result.get("status") == "no_valid_winner" and selected is not None:
        raise ValueError("no_valid_winner cannot select a candidate")

    review_dir = run_dir / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(review_dir / "anonymous-map.json", {
        "seed_sha256": "sha256:" + seed_hex,
        "mapping": anonymous,
    })
    atomic_json(review_dir / "review.json", result)
    atomic_json(review_dir / "review.meta.json", {
        "model": runner_info.get("model"),
        "prompt_sha256": text_sha(REVIEW_PROMPT),
        "analysis_identity_sha256": state["analysis_identity_sha256"],
        "receipt": receipt,
    })
    state["phase"] = "reviewed"
    state["selected_candidate"] = anonymous.get(selected) if selected else None
    state["review_status"] = result.get("status")
    atomic_json(run_path, state)
    return {
        "run_id": run_id,
        "status": result.get("status"),
        "selected_candidate": state["selected_candidate"],
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
    return load_json(run_dir / "candidates" / f"{label}.json", {})


def preview_alignment(root: Path, *, run_id: str) -> dict[str, Any]:
    _run_path, state = _load_run(root, run_id)
    run_dir = _run_dir(root, run_id)
    candidate = _selected_candidate(run_dir, state)
    existing = load_json(root / FORMAL_CAPABILITIES, {"capabilities": []})
    result = build_alignment(candidate, existing)
    atomic_json(run_dir / "alignment-preview.json", result)
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
    if review.get("corrections"):
        raise ValueError("review corrections must be materialized and revalidated before apply")
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
        "alignment": alignment,
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
