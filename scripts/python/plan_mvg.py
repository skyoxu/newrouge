#!/usr/bin/env python3
"""Independent post-Capability MVG planning that produces an initial manifest or reviewed cumulative delta."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from _mvg_manifest import validate_manifest
from _planning_skill_common import (
    atomic_json,
    canonical_sha,
    file_sha,
    inspect_isolated_runner,
    load_json,
    repo_path,
    run_isolated_model,
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

    rows = []
    all_ready = True
    for task_id in task_ids:
        ok, payload, reason = load_task_readiness(root, task_id)
        rows.append({
            "task_id": task_id,
            "ready": bool(ok),
            "reason": reason,
            "readiness": payload.get("readiness") if isinstance(payload, dict) else None,
        })
        all_ready = all_ready and ok
    if not task_ids:
        all_ready = False
        rows.append({"task_id": None, "ready": False, "reason": "explicit_task_scope_required"})
    if not all_ready and not allow_unready:
        raise ValueError(
            "MVG formal planning requires current Chapter 5 readiness for the explicit task scope"
        )
    return {
        "schema_version": "newrouge.mvg-planning-readiness-summary.v1",
        "formal_ready": all_ready,
        "allow_unready_draft": bool(allow_unready),
        "tasks": rows,
    }


def prepare(
    root: Path,
    *,
    run_id: str,
    capabilities_path: Path,
    task_ids: list[str],
    manifest_path: Path | None,
    allow_unready: bool,
) -> dict[str, Any]:
    capabilities = load_json(capabilities_path, {})
    if capabilities.get("schema_version") != "newrouge.capabilities.v1":
        raise ValueError("explicit Capability input is missing or invalid")
    run_dir = _run_dir(root, run_id)
    bundle = run_dir / "analysis-input"
    if bundle.exists():
        shutil.rmtree(bundle)
    bundle.mkdir(parents=True)
    readiness = _task_readiness(root, task_ids, allow_unready)

    files: dict[str, str] = {}
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

    referenced: set[str] = set()
    for row in _task_view_rows(root):
        for field in ("overlay_refs", "contractRefs", "test_refs"):
            for value in row.get(field, []):
                text = str(value).strip().replace("\\", "/")
                if text:
                    referenced.add(text)
        for acceptance in row.get("acceptance", []):
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

    existing_manifest = None
    if manifest_path is not None and manifest_path.is_file():
        existing_manifest = load_json(manifest_path, {})
        files["existing-manifest.json"] = _copy_file(root, manifest_path, bundle, "existing-manifest.json")

    atomic_json(bundle / "readiness-summary.json", readiness)
    files["readiness-summary.json"] = file_sha(bundle / "readiness-summary.json")
    index = {
        "schema_version": "newrouge.mvg-planning-input.v1",
        "capabilities_sha256": file_sha(capabilities_path),
        "files": files,
        "task_scope": task_ids,
        "existing_manifest": (
            {"path": manifest_path.resolve().relative_to(root.resolve()).as_posix(), "sha256": file_sha(manifest_path)}
            if manifest_path is not None and manifest_path.is_file()
            else None
        ),
    }
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
        "applied": False,
    }
    atomic_json(run_dir / "run.json", state)
    return state


PROMPT = """You are planning cumulative MVG integration scope after Capability planning.

Read every file under analysis-input/. The exact Capability file is an explicit input and must not be modified. Authoritative design semantics remain the GDD/source and reviewed Requirements. Existing task/Acceptance/contracts/tests and an existing manifest, when present, are evidence.

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

Tests may be planned or implemented using the existing MVG schema. implemented means implementation exists, not passed. Do not set runtime_verified and do not claim any plan validation is a runtime run.
When an existing manifest is present, preserve old flow/test IDs and obligations unless an explicit reviewed specification supports update/retire/coverage weakening. Provide those reviews in change_reviews / retirement_reviews / coverage_review.
"""


def generate(root: Path, *, run_id: str, timeout_sec: int, llm_backend: str) -> dict[str, Any]:
    run_path, state = _load_run(root, run_id)
    if state.get("formal_ready") is not True:
        raise ValueError("formal MVG planning is blocked until the explicit Chapter 5 scope is ready")
    if llm_backend not in SUPPORTED_LLM_BACKENDS:
        raise ValueError(
            "MVG planning requires one of: " + ", ".join(sorted(SUPPORTED_LLM_BACKENDS))
        )
    run_dir = run_path.parent
    workspace = run_dir / "model-workspace"
    if workspace.exists():
        shutil.rmtree(workspace)
    workspace.mkdir(parents=True)
    shutil.copytree(run_dir / "analysis-input", workspace / "analysis-input")
    tool_sc_dir = Path(__file__).resolve().parents[1] / "sc"
    if str(tool_sc_dir) not in sys.path:
        sys.path.insert(0, str(tool_sc_dir))
    from _llm_backend import inspect_llm_backend, run_llm_exec

    runner: Path | None = None
    backend_info: dict[str, Any]
    if llm_backend in {"openai-api", "copilot-cli"}:
        runner_name = (
            "openai_isolated_model_runner.py"
            if llm_backend == "openai-api"
            else "copilot_isolated_model_runner.py"
        )
        runner = Path(__file__).resolve().with_name(runner_name)
        backend_info = inspect_isolated_runner(runner)
    else:
        backend_info = inspect_llm_backend(llm_backend)
        if backend_info.get("available") is not True:
            reasons = "; ".join(str(value) for value in backend_info.get("blocking_errors", []))
            raise ValueError(f"{llm_backend} backend is unavailable: {reasons}")

    def invoke(prompt: str, attempt: int) -> tuple[Path, dict[str, Any]]:
        output = workspace / f"proposal-attempt-{attempt}.json"
        if runner is not None:
            prompt_path = workspace / f"prompt-attempt-{attempt}.txt"
            prompt_path.write_text(prompt, encoding="utf-8", newline="\n")
            receipt = run_isolated_model(
                runner,
                workspace=workspace,
                prompt_path=prompt_path,
                output_path=output,
                timeout_sec=timeout_sec,
            )
            return output, {
                "attempt": attempt,
                "backend": llm_backend,
                "backend_info": backend_info,
                "runner": runner.as_posix(),
                "returncode": 0,
                "receipt": receipt,
            }
        rc, stdout, cmd = run_llm_exec(
            backend=llm_backend,
            root=workspace,
            prompt=prompt,
            output_last_message=output,
            timeout_sec=timeout_sec,
            codex_configs=["model_reasoning_effort=high"],
        )
        execution: dict[str, Any] = {
            "attempt": attempt,
            "backend": llm_backend,
            "backend_info": backend_info,
            "command": cmd,
            "returncode": rc,
        }
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

    strict_contract = """
Deterministic validation reminders for the FULL replacement proposal:
- manifest_candidate.schema_version must be exactly newrouge.mvg-integration.v1.
- manifest_candidate.mvg_id and every flow/test id must be lowercase kebab-case strings.
- manifest_candidate must contain non-empty flows and tests arrays.
- manifest_candidate.coverage is mandatory with mode, scope_id, required_flow_ids in exact flow order, blocking_task_ids, and non-empty excluded_claims.
- Every flow requires id, outcome, task_ids, source_paths, handoffs, test_ids. task_ids and every handoff producer_task/consumer_task/owner_task are JSON integers, never quoted numeric strings.
- Every test requires id, kind, state, path, selector, evidence_level, min_tests.
- For this planning fixture, use only task IDs that are present in analysis-input/task-views and the master task file.
- Every planned entrypoint requires integer owner_task plus non-empty path, symbol, inputs, state, assertions, implementation_acceptance.
- Do not omit a required field merely because it can be inferred from prose.
"""

    prompt = PROMPT + "\n" + strict_contract
    attempts: list[dict[str, Any]] = []
    proposal: dict[str, Any] | None = None
    validation: dict[str, Any] = {"status": "blocked", "errors": ["model_not_run"]}
    for attempt in (1, 2):
        output, execution = invoke(prompt, attempt)
        text_value = output.read_text(encoding="utf-8").strip()
        if text_value.startswith("```"):
            lines = text_value.splitlines()[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text_value = "\n".join(lines)
        parsed = json.loads(text_value)
        if not isinstance(parsed, dict):
            raise ValueError("MVG proposal must be an object")
        proposal = parsed
        validation = validate_proposal(root, state, proposal)
        execution["proposal_sha256"] = canonical_sha(proposal)
        execution["deterministic_validation"] = validation
        attempts.append(execution)
        atomic_json(run_dir / f"proposal-attempt-{attempt}.json", proposal)
        if validation.get("status") == "passed":
            break
        errors = validation.get("errors") or []
        prompt = (
            PROMPT
            + "\n"
            + strict_contract
            + "\nYour previous FULL proposal failed deterministic validation. "
              "Do not patch fragments; return a completely corrected FULL proposal JSON. "
              "These validator errors must all be fixed without inventing task, contract, source, or test evidence:\n- "
            + "\n- ".join(str(value) for value in errors)
        )

    if proposal is None:
        raise ValueError("MVG proposal was not produced")
    atomic_json(run_dir / "proposal.json", proposal)
    atomic_json(run_dir / "model-execution.json", {
        "schema_version": "newrouge.mvg-planning-model-execution.v1",
        "backend": llm_backend,
        "attempts": attempts,
        "final_attempt": len(attempts),
    })
    if validation.get("status") != "passed":
        raise ValueError(
            "MVG model output remains structurally invalid after bounded correction: "
            + "; ".join(str(value) for value in validation.get("errors", []))
        )
    state["phase"] = "generated"
    state["model_backend"] = llm_backend
    state["model_execution"] = {
        "path": (run_dir / "model-execution.json").relative_to(root).as_posix(),
        "backend": llm_backend,
        "attempt_count": len(attempts),
    }
    atomic_json(run_path, state)
    return {
        "run_id": run_id,
        "proposal_sha256": file_sha(run_dir / "proposal.json"),
        "attempt_count": len(attempts),
    }

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
    capabilities = load_json(root / str(state["capabilities_path"]), {})
    known_caps = {
        str(row.get("capability_id"))
        for row in capabilities.get("capabilities", [])
        if isinstance(row, dict)
    }
    semantics = load_json(root / SEMANTICS, {})
    known_requirements = {
        str(row.get("requirement_id"))
        for row in semantics.get("requirements", [])
        if isinstance(row, dict)
    }
    known_tasks = _task_ids(root)
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

    for row in proposal.get("entrypoints", []):
        if not isinstance(row, dict):
            errors.append("invalid_entrypoint")
            continue
        status = str(row.get("status") or "")
        owner = row.get("owner_task")
        path = str(row.get("path") or "").strip()
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
        elif status == "planned":
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
    proposal = load_json(run_dir / "proposal.json", {})
    result = validate_proposal(root, state, proposal)
    if result["status"] == "passed":
        manifest_path = root / str(state["manifest_path"]) if state.get("manifest_path") else None
        if manifest_path is not None and manifest_path.is_file():
            existing = load_json(manifest_path, {})
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


def apply(root: Path, *, run_id: str, confirm: bool) -> dict[str, Any]:
    if not confirm:
        raise ValueError("MVG planning apply requires --confirm")
    run_path, state = _load_run(root, run_id)
    run_dir = run_path.parent
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
        atomic_json(manifest_path, updated)
    else:
        errors = validate_manifest(root, candidate, executable=False)
        if errors:
            raise ValueError("initial MVG manifest invalid: " + "; ".join(errors))
        atomic_json(manifest_path, candidate)

    trace = deepcopy(proposal)
    trace["applied_manifest_path"] = manifest_path.resolve().relative_to(root.resolve()).as_posix()
    trace["applied_manifest_sha256"] = file_sha(manifest_path)
    trace["capabilities_sha256"] = state["capabilities_sha256"]
    trace["applied_at_utc"] = now()
    trace_path = root / FORMAL_TRACE_ROOT / f"{run_id}.json"
    atomic_json(trace_path, trace)

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
    state["phase"] = "applied"
    state["applied"] = True
    state["applied_manifest_sha256"] = file_sha(manifest_path)
    state["post_apply_task_readiness"] = readiness
    state["involved_task_ids"] = involved
    state["handoff_bindings"] = dict(state.get("handoff_bindings") or {})
    state["handoff_review_required_tasks"] = involved
    atomic_json(run_path, state)
    result = {
        "status": "applied",
        "manifest_path": state["manifest_path"],
        "manifest_sha256": state["applied_manifest_sha256"],
        "trace_path": trace_path.resolve().relative_to(root.resolve()).as_posix(),
        "planning_complete": True,
        "runtime_verified": False,
        "chapter6_ready": False,
        "handoff_review_required_tasks": involved,
        "handoff_note": (
            "Only milestone-owned tasks require milestone handoff rebind. "
            "Use rebind-handoff for each applicable task; ordinary tasks continue through current Chapter 5 readiness."
        ),
        "post_apply_task_readiness": readiness,
    }
    atomic_json(run_dir / "apply-summary.json", result)
    return result


def rebind_handoff(
    root: Path,
    *,
    run_id: str,
    task_id: str,
    change_plan_path: Path,
    out_path: Path,
) -> dict[str, Any]:
    run_path, state = _load_run(root, run_id)
    if state.get("applied") is not True:
        raise ValueError("MVG handoff rebind requires an applied planning run")
    manifest_ref = str(state.get("manifest_path") or "").strip()
    if not manifest_ref:
        raise ValueError("MVG handoff rebind is missing the applied manifest path")
    manifest_path = repo_path(root, manifest_ref)
    expected_manifest_sha = str(state.get("applied_manifest_sha256") or "")
    if not manifest_path.is_file() or file_sha(manifest_path) != expected_manifest_sha:
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

    from milestone_incremental_handoff import (
        build_task_handoff,
        validate_task_handoff,
    )
    handoff = build_task_handoff(
        root,
        plan_path=change_plan_path,
        task_id=canonical_task,
        readiness_path=readiness_path,
    )
    atomic_json(out_path, handoff)
    ok, validation_reason, validated = validate_task_handoff(
        root, out_path, canonical_task
    )
    if not ok:
        out_path.unlink(missing_ok=True)
        raise ValueError(
            f"rebuilt milestone handoff is invalid for task {canonical_task}: "
            f"{validation_reason}"
        )

    bindings = dict(state.get("handoff_bindings") or {})
    bindings[canonical_task] = {
        "status": "valid",
        "path": out_path.relative_to(root).as_posix(),
        "sha256": file_sha(out_path),
        "change_plan_path": change_plan_path.relative_to(root).as_posix(),
        "chapter5_readiness_path": readiness_path.relative_to(root).as_posix(),
        "manifest_path": manifest_ref,
        "manifest_sha256": expected_manifest_sha,
    }
    state["handoff_bindings"] = bindings
    atomic_json(run_path, state)
    return {
        "status": "bound",
        "task_id": canonical_task,
        "handoff_path": out_path.relative_to(root).as_posix(),
        "handoff_sha256": file_sha(out_path),
        "chapter6_handoff_ready": True,
        "runtime_verified": False,
        "handoff": validated,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prepare = sub.add_parser("prepare")
    p_prepare.add_argument("--run-id", required=True)
    p_prepare.add_argument("--capabilities", required=True)
    p_prepare.add_argument("--task-id", action="append", default=[])
    p_prepare.add_argument("--manifest", required=True)
    p_prepare.add_argument("--allow-unready-draft", action="store_true")

    p_generate = sub.add_parser("generate")
    p_generate.add_argument("--run-id", required=True)
    p_generate.add_argument("--timeout-sec", type=int, default=1800)
    p_generate.add_argument("--llm-backend", default="codex-cli")

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
    p_handoff.add_argument("--change-plan", required=True)
    p_handoff.add_argument("--out", required=True)

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
            )
        elif args.command == "generate":
            result = generate(
                root, run_id=args.run_id,
                timeout_sec=args.timeout_sec,
                llm_backend=args.llm_backend,
            )
        elif args.command == "validate":
            result = validate(root, run_id=args.run_id)
        elif args.command == "apply":
            result = apply(root, run_id=args.run_id, confirm=bool(args.confirm))
        elif args.command == "rebind-handoff":
            result = rebind_handoff(
                root,
                run_id=args.run_id,
                task_id=str(args.task_id),
                change_plan_path=repo_path(root, args.change_plan),
                out_path=repo_path(root, args.out),
            )
        else:
            _path, result = _load_run(root, args.run_id)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
