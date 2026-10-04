#!/usr/bin/env python3
"""Independent post-Capability MVG planning that produces an initial manifest or reviewed cumulative delta."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import json
import re
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


def build_coverage_skeleton(semantics: dict[str, Any], task_views: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create non-droppable Requirement rows before semantic flow planning."""
    task_by_requirement: dict[str, tuple[int | None, str | None]] = {}
    for row in task_views:
        try:
            task_id = int(row.get("taskmaster_id"))
        except (TypeError, ValueError):
            continue
        capability_refs = [str(value) for value in row.get("capability_refs", []) if str(value).strip()]
        for requirement_id in row.get("semantic_refs", row.get("requirement_ids", [])):
            task_by_requirement.setdefault(str(requirement_id), (task_id, capability_refs[0] if capability_refs else None))
    result = []
    for requirement in semantics.get("requirements", []):
        if (not isinstance(requirement, dict)
                or requirement.get("delivery_relevant", True) is not True
                or requirement.get("status", "active") != "active"):
            continue
        requirement_id = str(requirement.get("requirement_id") or "").strip()
        task_id, capability_ref = task_by_requirement.get(requirement_id, (None, None))
        result.append({"requirement_id": requirement_id, "disposition": "flow",
            "flow_id": None, "capability_ref": capability_ref, "task_id": task_id,
            "rationale": "Pending LLM journey assignment; Requirement retained in coverage ledger."})
    return result


def build_entrypoint_skeleton(task_ids: list[int]) -> list[dict[str, Any]]:
    return [{"status": "planned", "owner_task": int(task_id),
        "path": f"Game.Godot/Planned/Task{int(task_id)}Entry.cs",
        "symbol": f"Task{int(task_id)}Entry", "inputs": "planned flow inputs",
        "state": "planned transition", "assertions": "observable result",
        "implementation_acceptance": "implement the planned integration entrypoint"}
        for task_id in sorted(set(task_ids))]


def correction_prompt(errors: list[str]) -> str:
    return ("Return a JSON patch only, not a replacement proposal. Allowed arrays are: "
            "coverage_additions, flow_updates, handoff_updates, entrypoint_additions. "
            "Do not remove or rewrite valid existing data. Preserve all IDs and Requirement rows. "
            "Fix only these validator errors:\n- " + "\n- ".join(str(value) for value in errors))


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

def segment_output_schema(*, section: str, identity: str, scope_id: str) -> dict[str, Any]:
    """Build the CLI-enforced envelope for one routed segment request."""
    payload_key = {
        "flows": "flows",
        "coverage": "coverage_table",
        "entrypoints": "entrypoints",
        "tests": "tests",
    }.get(section)
    if payload_key is None:
        raise ValueError(f"unsupported MVG segment section: {section}")
    return {
        "type": "object",
        "required": ["schema_version", "analysis_identity_sha256", "section", "scope_id", payload_key],
        "properties": {
            "schema_version": {"type": "string", "const": SEGMENT_SCHEMA},
            "analysis_identity_sha256": {"type": "string", "const": identity},
            "section": {"type": "string", "const": section},
            "scope_id": {"type": "string", "const": scope_id},
            payload_key: {"type": "array"},
        },
        "additionalProperties": False,
    }


def segment_prompt(*, section: str, identity: str, requirements: list[str], task_ids: list[int],
                   flow_context: list[dict[str, Any]] | None = None,
                   scope_id: str = "", flow_id_prefix: str = "", test_id_prefix: str = "") -> str:
    """Build a bounded LLM request for one MVG planning section.

    The model returns only the requested section. Deterministic code owns the
    final proposal envelope and the non-droppable skeleton accounting.
    """
    scope = json.dumps({"requirement_ids": requirements, "task_ids": task_ids,
                        "flow_ids": [str(row.get("id")) for row in (flow_context or [])]}, ensure_ascii=False)
    scope_label = scope_id or "unscoped"
    flow_rule = (f"Every new flow id must start with {flow_id_prefix!r}." if flow_id_prefix
                 else "Use stable lowercase kebab-case flow ids.")
    test_rule = (f"Every new test id must start with {test_id_prefix!r}." if test_id_prefix
                 else "Use stable lowercase kebab-case test ids.")
    return f"""You are producing one bounded section of an MVG integration plan.
Use only the prepared evidence needed for this section and return JSON only, with no markdown, shell commands, or commentary.
schema_version must be {SEGMENT_SCHEMA!r}.
analysis_identity_sha256 must be exactly {identity!r}.
section must be {section!r}.
scope_id must be {scope_label!r}; this request is independent from every other scope.
scope is {scope}.
The section is one patch to a deterministic proposal skeleton. Do not emit the full proposal envelope.
Return only fields needed for this section:
- flows: for section=flows, one or two complete player-journey flow objects for this scope only. Prefer one coherent journey when the evidence supports it; split only when the slice contains distinct observable outcomes. Each flow must include id, outcome, requirement_ids, capability_refs, task_ids, source_paths, handoffs, and test_ids. {flow_rule}
- coverage_table: for section=coverage, rows for the supplied requirements only;
- entrypoints: for section=entrypoints, planned/existing entrypoint rows for supplied task IDs;
- tests: for section=tests, test objects only. Every supplied flow must receive at least one test id, and each test id must be used by exactly one supplied flow. {test_rule}
For coverage rows, assign flow_id to an actual flow id from the supplied flow context; never leave it null.
The required bounded context is included inline in this prompt. Do not call shell/tools or scan files.
For section=tests, the inline context includes the prepared test refs; do not load full task views.
For entrypoints and tests, use only the specific prepared references named by that context. Do not scan unrelated files.
Do not invent repository paths, contracts, tasks, or capabilities. Use prepared evidence only.
For source_paths and contract_ref, use only paths listed in the inline available_*_paths arrays. If a required real object is not listed, report a gap instead of inventing a path.
"""


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
    return errors


def load_reusable_segment(run_dir: Path, *, current_attempt: int, index: int,
                          section: str, identity: str, scope_id: str) -> dict[str, Any] | None:
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
    return sorted(set(selected))


def _flow_summaries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: row.get(key) for key in (
        "id", "outcome", "requirement_ids", "capability_refs", "task_ids", "test_ids")}
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
        for requirement_id in row.get("requirement_ids", []):
            rid = str(requirement_id).strip()
            if rid:
                members.setdefault(rid, []).append(capability_id)
    return order, rows, members


def build_flow_scopes(semantics: dict[str, Any], capabilities: dict[str, Any],
                      task_views: list[dict[str, Any]], task_ids: list[int],
                      *, batch_size: int = 24) -> list[dict[str, Any]]:
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
        for requirement_id in row.get("semantic_refs", row.get("requirement_ids", [])):
            task_by_requirement.setdefault(str(requirement_id), set()).add(task_id)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for requirement in _active_delivery_requirements(semantics):
        rid = str(requirement["requirement_id"])
        capability_refs = cap_members.get(rid, [])
        if not capability_refs:
            capability_refs = [str(value) for value in requirement.get("capability_ids", [])
                               if str(value).strip()]
        anchor = capability_refs[0] if capability_refs else "unassigned"
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
            identity_key = "requirement_id" if key == "coverage_table" else "id" if key == "tests" else "owner_task"
            by_identity = {str(row.get(identity_key)): row for row in target if isinstance(row, dict)}
            for row in segment.get(key, []) or []:
                if not isinstance(row, dict):
                    continue
                value = str(row.get(identity_key) or "")
                if value and value in by_identity:
                    by_identity[value].update(row)
                elif value:
                    target.append(row)
                    by_identity[value] = row
    return result


def build_segment_scope(semantics: dict[str, Any], task_ids: list[int], *, batch_size: int = 24) -> list[dict[str, Any]]:
    requirements = [str(row.get("requirement_id")) for row in _active_delivery_requirements(semantics)]
    scopes = []
    for start in range(0, len(requirements), max(1, batch_size)):
        scopes.append({"requirements": requirements[start:start + batch_size], "task_ids": task_ids})
    return scopes


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
        "declared_contract_refs": sorted({str(value) for row in views for value in row.get("contractRefs", []) if str(value).strip()}),
    }
    path = workspace / "model-context.json"
    atomic_json(path, context)
    atomic_json(workspace / "test-context.json", {
        "schema_version": "newrouge.mvg-test-context.v1",
        "task_views": test_views,
        "declared_test_refs": sorted({str(value) for row in test_views for value in row.get("test_refs", []) if str(value).strip()}),
    })
    return path


def invoke_segmented(invoke: Any, run_dir: Path, state: dict[str, Any], attempt: int,
                     full_prompt: str, workspace: Path, *, semantics: dict[str, Any],
                     task_ids: list[int], base_proposal: dict[str, Any] | None = None) -> tuple[Path, dict[str, Any]]:
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
    flow_scopes = build_flow_scopes(semantics, capabilities, task_views, task_ids)
    model_context = load_json(workspace / "model-context.json", {})
    all_task_views = model_context.get("task_views", [])
    all_test_views = load_json(workspace / "test-context.json", {}).get("task_views", [])
    prepared = run_dir / "analysis-input"
    source_paths = sorted({"docs/gdd/GDD-NEWROUGE-TASK-BASELINE.md"}
                          | {str(value).split(":", 1)[0] for row in all_task_views
                             if int(row.get("taskmaster_id", -1)) in set(task_ids)
                             for value in row.get("source_refs", []) if str(value).strip()})
    contract_paths = sorted(
        path.relative_to(prepared / "references").as_posix()
        for path in (prepared / "references" / "Game.Core" / "Contracts").rglob("*.cs")
        if path.is_file()
    ) if (prepared / "references" / "Game.Core" / "Contracts").is_dir() else []
    declared_contract_refs = set(model_context.get("declared_contract_refs", []))

    requests: list[dict[str, Any]] = []
    for scope in flow_scopes:
        requests.append({"section": "flows", "scope_id": scope["scope_id"],
                         "requirements": scope["requirements"],
                         "requirement_ids": scope["requirement_ids"],
                         "task_ids": scope["task_ids"],
                         "capabilities": scope["capabilities"]})

    # Flow coverage is accounted for in small Requirement batches after all
    # flow IDs are known. A batch contains only its own Requirement statements.
    active_rows = _active_delivery_requirements(semantics)
    requirement_context = {
        str(row["requirement_id"]): row for row in active_rows
    }
    for scope in build_segment_scope(semantics, task_ids, batch_size=24):
        selected_requirements = set(scope["requirements"])
        scoped_tasks = sorted({int(row.get("taskmaster_id")) for row in task_views
                               if isinstance(row, dict)
                               and str(row.get("taskmaster_id") or "").isdigit()
                               and int(row.get("taskmaster_id")) in set(task_ids)
                               and selected_requirements.intersection(
                                   {str(value) for value in row.get("semantic_refs", row.get("requirement_ids", []))})})
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

    # Only tasks actually referenced by a flow need an LLM-owned entrypoint
    # refinement. The deterministic skeleton still retains all prepared owners.
    flow_task_ids = sorted({task_id for scope in flow_scopes for task_id in scope["task_ids"]})
    for start in range(0, len(flow_task_ids), 32):
        scoped_tasks = flow_task_ids[start:start + 32]
        requests.append({"section": "entrypoints", "scope_id": f"entrypoints-{start // 32 + 1:02d}",
                         "requirements": [], "requirement_ids": [], "task_ids": scoped_tasks})

    for start in range(0, len(flow_scopes), 3):
        scoped_scopes = flow_scopes[start:start + 3]
        requests.append({"section": "tests", "scope_id": f"tests-{start // 3 + 1:02d}",
                         "requirements": [], "requirement_ids": [],
                         "task_ids": sorted({task_id for scope in scoped_scopes for task_id in scope["task_ids"]}),
                         "flow_scope_ids": [scope["scope_id"] for scope in scoped_scopes]})

    def execute_request(index: int, request: dict[str, Any], flow_context: list[dict[str, Any]]) -> tuple[int, dict[str, Any], dict[str, Any]]:
        section = request["section"]
        requirements = request["requirement_ids"]
        scoped_tasks = request["task_ids"]
        flow_context = [row for segment in segments for row in (segment.get("flows", []) or [])
                        if isinstance(row, dict)]
        flow_prefix = f"{request['scope_id']}-" if section == "flows" else ""
        test_prefix = f"{request['scope_id']}-" if section == "tests" else ""
        section_prompt_text = segment_prompt(
            section=section, identity=identity,
            requirements=requirements, task_ids=scoped_tasks,
            flow_context=flow_context,
            scope_id=request["scope_id"], flow_id_prefix=flow_prefix, test_id_prefix=test_prefix,
        )
        if flow_context:
            selected_flow_rows = flow_context
            if request.get("flow_scope_ids"):
                selected_flow_rows = [row for row in flow_context
                                      if any(str(row.get("id", "")).startswith(scope_id + "-")
                                             for scope_id in request["flow_scope_ids"])]
            section_prompt_text += "\nUse these already prepared flow objects as the only flow context:\n"
            section_prompt_text += json.dumps(
                _flow_summaries(selected_flow_rows), ensure_ascii=False)
        if section == "flows":
            scoped_refs = {str(value) for row in all_task_views
                           if int(row.get("taskmaster_id", -1)) in set(scoped_tasks)
                           for value in row.get("contractRefs", []) if str(value).strip()}
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
            }, ensure_ascii=False)
        elif section == "entrypoints":
            section_prompt_text += "\nInline bounded evidence context:\n" + json.dumps({
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
                                                for value in row.get("test_refs", []) if str(value).strip()}),
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
                                         ))
                parsed = json.loads(output.read_text(encoding="utf-8"))
                if not isinstance(parsed, dict):
                    raise ValueError(f"MVG segment {section} must be a JSON object")
                errors = validate_segment_identity(parsed, section=section, identity=identity,
                                                   scope_id=request["scope_id"])
                if errors:
                    raise ValueError(f"MVG segment {section} identity invalid: {'; '.join(errors)}")
                return index, parsed, {"section": section, "index": index, "retry": retry, "receipt": receipt}
            except (json.JSONDecodeError, OSError, RuntimeError, TimeoutError, ValueError) as exc:
                last_error = str(exc)
                section_prompt_text += (
                    "\nThe previous response failed deterministic routing/schema validation. "
                    "Retry this exact scope and return the required envelope fields; do not return a bare section payload."
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
    skeleton_coverage = load_json(run_dir / "coverage-skeleton.json", [])
    skeleton_entrypoints = load_json(run_dir / "entrypoint-skeleton.json", [])
    assembled["coverage_table"] = merge_planning_segments(
        {"coverage_table": skeleton_coverage},
        [{"coverage_table": assembled.get("coverage_table", [])}],
    ).get("coverage_table", skeleton_coverage)
    assembled["entrypoints"] = merge_planning_segments(
        {"entrypoints": skeleton_entrypoints},
        [{"entrypoints": assembled.get("entrypoints", [])}],
    ).get("entrypoints", skeleton_entrypoints)
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
    existing_manifest = None
    if manifest_path is not None and manifest_path.is_file():
        existing_manifest = load_json(manifest_path, {})
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

    atomic_json(bundle / "readiness-summary.json", readiness)
    files["readiness-summary.json"] = file_sha(bundle / "readiness-summary.json")
    skeleton = build_coverage_skeleton(load_json(root / SEMANTICS, {}), _task_view_rows(root))
    atomic_json(bundle / "coverage-skeleton.json", {"schema_version": "newrouge.mvg-coverage-skeleton.v1", "rows": skeleton})
    files["coverage-skeleton.json"] = file_sha(bundle / "coverage-skeleton.json")
    entrypoint_tasks = sorted({int(row.get("taskmaster_id")) for row in _task_view_rows(root)
                               if str(row.get("taskmaster_id", "")).isdigit()})
    atomic_json(bundle / "entrypoint-skeleton.json", {"schema_version": "newrouge.mvg-entrypoint-skeleton.v1",
        "rows": build_entrypoint_skeleton(entrypoint_tasks)})
    files["entrypoint-skeleton.json"] = file_sha(bundle / "entrypoint-skeleton.json")
    index = {
        "schema_version": "newrouge.mvg-planning-input.v1",
        "capabilities_sha256": file_sha(capabilities_path),
        "files": files,
        "task_scope": task_ids,
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
        authority[path.resolve().relative_to(root.resolve()).as_posix()] = file_sha(path) if path.is_file() else None
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

Read every file under analysis-input/. The exact Capability file is an explicit input and must not be modified. `coverage-skeleton.json` is a non-droppable ledger: every active delivery Requirement must remain represented; you must not delete or silently omit its rows. Authoritative design semantics remain the GDD/source and reviewed Requirements. Existing task/Acceptance/contracts/tests and an existing manifest, when present, are evidence.

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

coverage_table must account for EVERY active delivery-relevant Requirement. Start from coverage-skeleton.json and preserve every row; assign flow_id and rationale without deleting rows. Every flow row requires requirement_id, capability_ref, integer task_id, flow_id, and a nonempty string field named rationale, consistent with both the flow's requirement_ids/capability_refs/task_ids and the actual Requirement-to-Capability and Requirement-to-Task membership. Use the literal JSON key rationale, not coverage_rationale or reason. Other verification rows require disposition=other_verification, sink_id from the Requirement's non_task_sinks, verification_ref to an existing prepared file and rationale. Deferred rows require disposition=deferred and the same resolvable authority_ref/authority_review contract used for baseline weakening. Start entrypoints from entrypoint-skeleton.json; every flow task needs a planned or existing_verified entrypoint. Never leave coverage_table or entrypoints empty.
"""


def generate(root: Path, *, run_id: str, timeout_sec: int, llm_backend: str, segmented: bool = True) -> dict[str, Any]:
    run_path, state = _load_run(root, run_id)
    _validate_input_freshness(root, run_path.parent, state)
    if state.get("formal_ready") is not True:
        raise ValueError("formal MVG planning is blocked until the explicit Chapter 5 scope is ready")
    if llm_backend not in SUPPORTED_LLM_BACKENDS:
        raise ValueError(
            "MVG planning requires one of: " + ", ".join(sorted(SUPPORTED_LLM_BACKENDS))
        )
    run_dir = run_path.parent
    existing_proposal = load_json(run_dir / "proposal.json", {})
    if state.get("model_execution") and validate_proposal(root, state, existing_proposal)["status"] == "passed":
        return {"run_id": run_id, "proposal_sha256": file_sha(run_dir / "proposal.json"),
                "attempt_count": state["model_execution"]["attempt_count"]}
    workspace_base = run_dir / "model-workspace"
    workspace = workspace_base
    workspace_base.mkdir(parents=True, exist_ok=True)
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

    def invoke(prompt: str, attempt: int, *, output_name: str | None = None,
               output_schema_path: Path | None = None,
               output_schema: dict[str, Any] | None = None) -> tuple[Path, dict[str, Any]]:
        relative_output = Path(output_name or f"proposal-attempt-{attempt}.json")
        prompt_stem = relative_output.with_suffix("").as_posix().replace("/", "-")
        # Keep the model's cwd empty and segment-local. The prepared evidence
        # remains immutable under attempt/analysis-input, but is supplied only
        # through the bounded inline prompt. This prevents Codex from spending
        # its budget recursively scanning the entire evidence bundle.
        llm_workspace = workspace / "llm-sandbox" / f"attempt-{attempt}" / prompt_stem
        llm_workspace.mkdir(parents=True, exist_ok=True)
        output = llm_workspace / relative_output.name
        if output_schema_path is not None and output_schema is not None:
            atomic_json(output_schema_path, output_schema)
        if runner is not None:
            prompt_path = llm_workspace / f"prompt-{attempt}-{prompt_stem}.txt"
            prompt_path.write_text(prompt, encoding="utf-8", newline="\n")
            receipt = run_isolated_model(
                runner,
                workspace=llm_workspace,
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
            root=llm_workspace,
            prompt=prompt,
            output_last_message=output,
            timeout_sec=timeout_sec,
            # Let Codex use the environment-default model and reasoning policy.
            # MVG segmentation controls scope; it should not hard-code a model
            # or override the user's CLI defaults.
            codex_configs=[],
            output_schema=output_schema_path,
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

    known_task_ids = sorted(_task_ids(root))
    task_master = load_json(root / ".taskmaster/tasks/tasks.json", {})
    task_statuses = {
        str(row["id"]): str(row.get("status", "")).lower()
        for row in task_master.get("master", {}).get("tasks", [])
    }
    known_non_done_ids = sorted(int(task_id) for task_id, status in task_statuses.items() if status != "done")
    source_manifest = load_json(root / SOURCE_MANIFEST, {})
    known_source_paths = sorted({
        str(row.get("path"))
        for row in source_manifest.get("sources", [])
        if isinstance(row, dict) and str(row.get("path") or "").strip()
    })
    known_contract_refs = sorted({
        str(value)
        for row in _task_view_rows(root)
        for value in row.get("contractRefs", [])
        if str(value).strip()
    })
    known_test_refs = sorted({
        str(value)
        for row in _task_view_rows(root)
        for value in row.get("test_refs", [])
        if str(value).strip()
    })
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
- Every dotnet selector must be a class name (for example RelayTests or Game.Core.Tests.Tasks.RelayTests), never a test filter expression, method selector, wildcard, or comparison.
- gdunit tests require evidence_level=scene-method or engine-input and a Tests.Godot/tests/... .gd path.
- source_paths and contract_ref values in the formal manifest are original repository-relative paths, never analysis-input/... paths.
- Every planned entrypoint requires integer owner_task plus non-empty path, symbol, inputs, state, assertions, implementation_acceptance.
- coverage_table rows require a nonempty "rationale" string. Write that exact JSON key. The validator error coverage_rationale_missing means rationale is missing; coverage_rationale is an error label, not the required output field.
- Do not omit a required field merely because it can be inferred from prose.
Known Taskmaster IDs for this planning input: {known_task_ids}
Authoritative Taskmaster statuses (task ID to status): {json.dumps(task_statuses, sort_keys=True)}
The only known non-done Taskmaster IDs are: {known_non_done_ids}. If this list is empty, coverage.blocking_task_ids MUST be [] in every replacement proposal, even when tests and entrypoints are planned.
Declared authoritative source paths: {known_source_paths}
Existing reviewed contract refs from task views: {known_contract_refs}
Existing test refs from task views: {known_test_refs}
Prefer these real refs instead of inventing alternatives. If a required real object does not exist, record a gap and use planning_status=draft.
"""

    prompt = PROMPT + "\n" + strict_contract
    state["generation_strategy"] = "segmented" if segmented else "single-proposal"
    atomic_json(run_path, state)
    attempts: list[dict[str, Any]] = state.setdefault("generation_attempts", [])
    proposal: dict[str, Any] | None = None
    validation: dict[str, Any] = {"status": "blocked", "errors": ["model_not_run"]}
    for attempt in (1, 2, 3):
        if attempt <= len(attempts):
            continue
        workspace = workspace_base / f"attempt-{attempt}"
        workspace.mkdir(parents=True, exist_ok=False)
        shutil.copytree(run_dir / "analysis-input", workspace / "analysis-input")
        record = {"attempt": attempt, "status": "running", "backend": llm_backend}
        attempts.append(record)
        atomic_json(run_path, state)
        try:
            # Keep each model response bounded. The final proposal is assembled
            # locally from section outputs and then subjected to the existing
            # full deterministic validator.
            if segmented:
                output, execution = invoke_segmented(
                    invoke, run_dir, state, attempt, prompt, workspace,
                    semantics=load_json(run_dir / "analysis-input/semantic-requirements.v1.json", {}),
                    task_ids=[int(value) for value in state.get("task_scope", [])],
                    base_proposal=proposal,
                )
            else:
                output, execution = invoke(prompt, attempt)
        except (RuntimeError, TimeoutError, OSError, ValueError) as exc:
            record.update(status="execution-failed", error=str(exc))
            state["phase"] = "generation-execution-blocked"
            atomic_json(run_path, state)
            atomic_json(run_dir / "model-execution.json", {"backend": llm_backend, "attempts": attempts})
            continue
        text_value = output.read_text(encoding="utf-8").strip()
        if text_value.startswith("```"):
            lines = text_value.splitlines()[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text_value = "\n".join(lines)
        try:
            parsed = json.loads(text_value)
        except (TypeError, ValueError) as exc:
            record.update(status="execution-failed", error=f"model output is not valid JSON: {exc}")
            state["phase"] = "generation-execution-blocked"
            atomic_json(run_path, state)
            atomic_json(run_dir / "model-execution.json", {"backend": llm_backend, "attempts": attempts})
            continue
        if not isinstance(parsed, dict):
            raise ValueError("MVG proposal must be an object")
        if attempt > 1 and not segmented:
            patch_errors = [] if is_restricted_patch(parsed) else ["restricted_patch_required"]
            patch_errors.extend(validate_restricted_patch_identity(parsed, state))
            if patch_errors:
                execution["proposal_sha256"] = canonical_sha(parsed)
                execution["deterministic_validation"] = {"status": "blocked", "errors": patch_errors}
                record.update(execution, status="completed")
                atomic_json(run_path, state)
                atomic_json(run_dir / f"proposal-attempt-{attempt}.json", parsed)
                validation = execution["deterministic_validation"]
                prompt = PROMPT + "\n" + strict_contract + "\n" + correction_prompt(patch_errors)
                continue
            base = proposal or load_json(run_dir / "proposal.json", {})
            parsed = apply_restricted_patch(base, parsed)
        proposal = parsed
        validation = validate_proposal(root, state, proposal)
        execution["proposal_sha256"] = canonical_sha(proposal)
        execution["deterministic_validation"] = validation
        record.update(execution, status="completed")
        atomic_json(run_path, state)
        atomic_json(run_dir / f"proposal-attempt-{attempt}.json", proposal)
        ready_with_gaps = validation.get("planning_status") == "ready_for_validation" and validation.get("unresolved_gap_count", 0) > 0
        if validation.get("status") == "passed" and not ready_with_gaps:
            break
        errors = validation.get("errors") or []
        if ready_with_gaps:
            errors = errors + ["unresolved_gaps contradict ready_for_validation. Preserve true upstream gaps as draft. Correctly specified planned implementation/tests and absent runtime evidence belong in notes/manual_obligations, not gaps. Return a full consistent proposal; do not hide genuine upstream uncertainty."]
        prompt = PROMPT + "\n" + strict_contract + "\n" + correction_prompt(errors)

    if proposal is None:
        raise ValueError("MVG proposal execution attempt budget exhausted; prepared inputs are preserved")
    atomic_json(run_dir / "proposal.json", proposal)
    atomic_json(run_dir / "model-execution.json", {
        "schema_version": "newrouge.mvg-planning-model-execution.v1",
        "backend": llm_backend,
        "attempts": attempts,
        "final_attempt": len(attempts),
    })
    if validation.get("status") != "passed":
        raise ValueError(
            "MVG model output remains structurally invalid after bounded correction attempts: "
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
    from _mvg_planning_review import coverage_errors, prepared_evidence_errors
    errors.extend(coverage_errors(root, proposal, semantics, capabilities, _task_view_rows(root)))
    errors.extend(prepared_evidence_errors(root, proposal,
        _run_dir(root, str(state.get("run_id"))) / "analysis-input"))
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
                    else:
                        prepared = _run_dir(root, str(state.get("run_id"))) / "analysis-input"
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
    run_path, state = _load_run(root, run_id)
    run_dir = run_path.parent
    _validate_input_freshness(root, run_dir, state)
    proposal = load_json(run_dir / "proposal.json", {})
    if validate_proposal(root, state, proposal)["status"] != "passed":
        raise ValueError("MVG semantic review requires a structurally valid proposal")
    runner_info = inspect_isolated_runner(runner)
    from _mvg_planning_review import semantic_review_errors, review_execution_errors
    from _planning_review_publication import completed_output, prepare_publication, publication_complete, resume_publication
    proposal_sha = canonical_sha(proposal)
    publication = run_dir / f"semantic-review-publication-{proposal_sha.removeprefix('sha256:')}.json"
    publication_identity = {"analysis_identity_sha256": state["analysis_identity_sha256"],
        "proposal_sha256": proposal_sha, "runner": runner_info}
    for recorded in run_dir.glob("semantic-review-publication-*.json"):
        if recorded != publication and not publication_complete(recorded):
            raise ValueError("MVG review publication is pending; recover the original proposal before revising it")
    settled = state.get("semantic_review_attempts") or []
    if settled and settled[-1].get("status") == "completed" and settled[-1].get("proposal_sha256") != proposal_sha:
        prior_sha = str(settled[-1].get("proposal_sha256") or "").removeprefix("sha256:")
        if not (run_dir / f"semantic-review-publication-{prior_sha}.json").is_file():
            raise ValueError("Completed MVG review is unpublished; recover the original proposal before revising it")
    published = resume_publication(publication, publication_identity, atomic_json)
    existing = load_json(run_dir / "semantic-review.json", {})
    if published or (existing.get("proposal_sha256") == proposal_sha
            and existing.get("analysis_identity_sha256") == state["analysis_identity_sha256"]):
        errors = semantic_review_errors(state, proposal, existing,
            load_json(run_dir / "analysis-input/semantic-requirements.v1.json", {}))
        errors.extend(review_execution_errors(state, proposal,
            load_json(run_dir / "semantic-review-execution.json", {})))
        if state.get("phase") != "applied":
            state["phase"] = "review-blocked" if errors else "reviewed"
        atomic_json(run_path, state)
        if errors:
            raise ValueError("existing independent semantic review is blocked; resolve findings before reviewing a revised proposal: "
                + ";".join(errors))
        return {"status": "approved", "proposal_sha256": proposal_sha, "runtime_verified": False}
    prompt = f'''Independently review proposal.json against ALL prepared source text, reviewed Requirements,
Capability membership, real Task/Acceptance/contracts/tests and the existing manifest under analysis-input.
You did not generate this proposal. Evaluate semantic conservation, player journey and failure/recovery,
cross-system handoffs, every Requirement's flow/other-verification/deferred accounting, entrypoint inputs/state/assertions,
test evidence levels and feasibility. Planned entrypoints/tests are legitimate future obligations, not runtime proof.
Do not require their implementation or claim runtime_verified. Do not approve invented refs, missing obligations,
mechanical one-flow-per-Capability grouping, unsupported deferral or baseline weakening.
Return JSON only: schema_version="newrouge.mvg-semantic-review.v1",
analysis_identity_sha256="{state['analysis_identity_sha256']}", proposal_sha256="{canonical_sha(proposal)}",
Copy both identity values verbatim from this prompt; do not compute, shorten, or edit their sha256 strings.
They are fixed host-supplied input identities, not semantic judgments. Check their exact characters before returning JSON.
verdict="approved" or "blocked", findings=[] ONLY if all checks pass (otherwise concrete findings),
requirement_reviews=[{{"requirement_id":"...","verdict":"covered|other_verification|deferred|blocked","rationale":"..."}}]
with exactly one explicit non-empty rationale per active delivery-relevant Requirement,
flow_reviews=[{{"flow_id":"...","verdict":"sound|blocked","rationale":"..."}}] with exactly one row per flow.
Use one actual verdict value, not the pipe-separated enumeration above. Do not rewrite the proposal.
'''
    import time
    attempts = state.setdefault("semantic_review_attempts", [])
    receipt = None
    result = None
    if attempts and attempts[-1].get("proposal_sha256") == proposal_sha:
        restored = completed_output(attempts, run_dir / "semantic-review-workspace" / f"attempt-{len(attempts)}" / "review.json")
        if restored:
            record, result = restored
            if record.get("runner_info") != runner_info or record.get("analysis_identity_sha256") != state["analysis_identity_sha256"]:
                raise ValueError("Completed MVG review execution identity changed")
            receipt = record["receipt"]
    while len(attempts) < 3 and result is None:
        number = len(attempts) + 1
        workspace = run_dir / "semantic-review-workspace" / f"attempt-{number}"
        workspace.mkdir(parents=True, exist_ok=False)
        shutil.copytree(run_dir / "analysis-input", workspace / "analysis-input")
        atomic_json(workspace / "proposal.json", proposal)
        prompt_path = workspace / "prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8", newline="\n")
        output = workspace / "review.json"
        record = {"attempt": number, "status": "running", "proposal_sha256": proposal_sha,
            "runner_info": runner_info, "analysis_identity_sha256": state["analysis_identity_sha256"]}
        attempts.append(record)
        atomic_json(run_path, state)  # Count even an interrupted invocation.
        started = time.monotonic()
        try:
            receipt = run_isolated_model(runner, workspace=workspace, prompt_path=prompt_path,
                output_path=output, timeout_sec=timeout_sec)
            if receipt.get("model_tools") != [] or not receipt.get("model"):
                raise ValueError("independent reviewer execution identity is incomplete")
            result = parse_model_json(output)
            record.update(status="completed", receipt=receipt, output_sha256=file_sha(output))
        except (OSError, RuntimeError, TimeoutError, ValueError) as exc:
            record.update(status="execution-failed", error=str(exc))
            state["phase"] = "review-execution-blocked"
        finally:
            record["activity_sec"] = time.monotonic() - started
            atomic_json(run_path, state)
        if result is not None:
            break
    if result is None:
        raise ValueError("MVG independent review execution attempt budget exhausted; upstream proposal is preserved")
    execution = {"runner": runner.as_posix(), "runner_info": runner_info, "receipt": receipt,
        "analysis_identity_sha256": state["analysis_identity_sha256"], "proposal_sha256": canonical_sha(proposal),
        "attempt_count": len(attempts)}
    prepare_publication(publication, publication_identity,
        {"semantic-review.json": result, "semantic-review-execution.json": execution}, atomic_json)
    resume_publication(publication, publication_identity, atomic_json)
    errors = semantic_review_errors(state, proposal, result,
        load_json(run_dir / "analysis-input/semantic-requirements.v1.json", {}))
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
    review_errors = semantic_review_errors(state, proposal, load_json(run_dir / "semantic-review.json", {}),
        load_json(run_dir / "analysis-input/semantic-requirements.v1.json", {}))
    review_errors.extend(review_execution_errors(state, proposal,
        load_json(run_dir / "semantic-review-execution.json", {})))
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
    if canonical_sha(index) != identity or identity != state.get("analysis_identity_sha256"):
        raise ValueError("MVG prepared analysis identity changed")
    authority = index.get("authority_inputs")
    if not isinstance(authority, dict) or not authority:
        raise ValueError("MVG original authority identity is incomplete; prepare again")
    drift = []
    for rel, expected in authority.items():
        path = repo_path(root, rel)
        if (file_sha(path) if path.is_file() else None) != expected:
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
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
