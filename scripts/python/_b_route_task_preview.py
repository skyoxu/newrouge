"""Read-only 3C reuse inventory and real-gap task-change preview.

Consumes committed 3B adoption records (via read_committed), current 3A source
audit proof (via verify_current_proof), current Taskmaster triplet (via
TaskJoinContext), and optional protection/manifest/change-intent inputs.

Never mutates .taskmaster/tasks/*.json, docs/planning/b-route/**, manifests,
or publication pointers. Never allocates permanent positive-integer task IDs
(Story 3.2 owns permanent ID allocation and governed triplet compilation).
"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

import copy
import datetime as dt
import hashlib
import os
import re
from pathlib import Path
from typing import Any, Callable

import _b_route_codec as codec
import _b_route_commit as commit
import _b_route_inventory as inventory
import _b_route_preflight as preflight
import _b_route_protection as protection
import _b_route_records as records
import _b_route_source_audit as source_audit
import _b_route_sources as sources
import normalize_task_intents as normalizer
from update_mvg_baseline import _weakens_baseline


SCHEMA = "newrouge.b-route-task-preview.v1"
CHANGE_INTENTS_SCHEMA = "newrouge.b-route-task-change-intents.v1"
AUTHORIZATION = {
    "formal_adoption": False,
    "task_triplet_written": False,
    "readiness": False,
    "runtime_verified": False,
    "default_b_enabled": False,
}
ALLOWED_ACTIONS = frozenset({"reuse", "update", "create", "split", "merge", "retire"})
MUTATING_ACTIONS = frozenset({"update", "split", "merge", "retire"})
PART_KINDS = ("domain_rules", "csharp_adapter", "binding", "scene")
ALLOWED_ROLES = frozenset({"producer", "consumer", "integration_only_owner"})
STORY_ID_RE = re.compile(
    r"^(?:story[-_\s]?\d+(?:\.\d+)*|\d+\.\d+(?:\.\d+)*|s\d+\.\d+)$",
    re.IGNORECASE,
)
_WINDOWS_RESERVED_RUN_IDS = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def _diag(
    code: codec.ReasonCode,
    *,
    owning_stage: str,
    stage: codec.Stage = codec.Stage.BUNDLE,
    entity_id: str | None = None,
    expected: Any = None,
    actual: Any = None,
    resume_ref: str | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    return codec.Diagnostic(
        code,
        stage,
        str(entity_id) if entity_id is not None else None,
        {"owning_stage": owning_stage, "path": path, "value": expected},
        {"owning_stage": owning_stage, "path": path, "value": actual},
        resume_ref or path,
    ).to_dict()


def _tag_diagnostic(
    diagnostic: codec.Diagnostic | dict[str, Any],
    *,
    owning_stage: str,
    entity_id: str | None = None,
    resume_ref: str | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    raw = diagnostic.to_dict() if isinstance(diagnostic, codec.Diagnostic) else dict(diagnostic)
    expected = raw.get("expected")
    actual = raw.get("actual")
    if isinstance(expected, dict):
        expected = {**expected, "owning_stage": expected.get("owning_stage", owning_stage)}
        if path and "path" not in expected:
            expected["path"] = path
    else:
        expected = {"owning_stage": owning_stage, "path": path, "value": expected}
    if isinstance(actual, dict):
        actual = {**actual, "owning_stage": actual.get("owning_stage", owning_stage)}
        if path and "path" not in actual:
            actual["path"] = path
    else:
        actual = {"owning_stage": owning_stage, "path": path, "value": actual}
    return {
        "reason_code": raw.get("reason_code", codec.ReasonCode.IDENTITY_UNPROVABLE.value),
        "stage": raw.get("stage", codec.Stage.BUNDLE.value),
        "entity_id": raw.get("entity_id") or (str(entity_id) if entity_id is not None else None),
        "expected": expected,
        "actual": actual,
        "resume_ref": raw.get("resume_ref") or resume_ref or path,
    }


def _fail(
    code: codec.ReasonCode,
    *,
    owning_stage: str,
    stage: codec.Stage = codec.Stage.BUNDLE,
    entity_id: str | None = None,
    expected: Any = None,
    actual: Any = None,
    resume_ref: str | None = None,
    path: str | None = None,
) -> None:
    d = _diag(
        code,
        owning_stage=owning_stage,
        stage=stage,
        entity_id=entity_id,
        expected=expected,
        actual=actual,
        resume_ref=resume_ref,
        path=path,
    )
    raise codec.CodecError(
        codec.Diagnostic(
            code,
            stage,
            d["entity_id"],
            d["expected"],
            d["actual"],
            d["resume_ref"],
        )
    )


def _is_story_like_id(value: Any) -> bool:
    if isinstance(value, str):
        return STORY_ID_RE.fullmatch(value.strip()) is not None
    return False


def _validate_nonempty_str(value: Any, label: str, *, owning_stage: str = "3C", path: str | None = None) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        _fail(
            codec.ReasonCode.INVALID_TYPE,
            owning_stage=owning_stage,
            stage=codec.Stage.CONTENT,
            entity_id=label,
            expected="nonempty unpadded string",
            actual=value,
            path=path,
        )
    return value


def _candidate_key(
    plan_id: str,
    view: str,
    action: str,
    flow_ids: list[str],
    requirement_ids: list[str],
    split_index: int = 0,
) -> str:
    seed = {
        "plan_id": plan_id,
        "view": view,
        "action": action,
        "flow_ids": sorted(set(flow_ids)),
        "requirement_ids": sorted(set(requirement_ids)),
        "split_index": split_index,
    }
    digest = codec.canonical_digest(seed).split(":", 1)[1][:12]
    return f"cand:{plan_id}:{view}:{digest}"


def _candidate_business_id(view: str, candidate_key: str) -> str:
    suffix = candidate_key.rsplit(":", 1)[-1].upper()
    prefix = "GM-CAND" if view == "gameplay" else "NG-CAND"
    return f"{prefix}-{suffix}"


def _dedupe_owned_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for ref in refs:
        key = codec.canonical_digest(ref)
        if key not in seen:
            seen[key] = copy.deepcopy(ref)
    return [seen[k] for k in sorted(seen)]


def _mirror_audit_observations(
    obs: preflight.Observations,
    audit_obs: sources.Observations,
    *,
    ignore_errors: bool = False,
) -> None:
    for rel_path, raw in sorted(audit_obs.files.items()):
        try:
            obs.read(rel_path, optional=raw is None)
        except codec.CodecError:
            if not ignore_errors:
                raise


def _resolve_plan_flows(
    plan: dict[str, Any],
    catalog_flows_by_id: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Resolve all Flows owned by this plan plus external shared Flows referenced from catalog."""
    flows: dict[str, dict[str, Any]] = {row["id"]: row for row in plan["definitions"]["flows"]}
    referenced_ids: set[str] = set()
    for ref in plan.get("logical_references", []):
        if isinstance(ref, dict) and ref.get("kind") == "flow" and isinstance(ref.get("definition_id"), str):
            referenced_ids.add(ref["definition_id"])
    for row in plan.get("requirement_verification", []):
        if isinstance(row, dict) and isinstance(row.get("flow_id"), str):
            referenced_ids.add(row["flow_id"])
    for row in plan.get("requirement_route_memberships", []):
        if isinstance(row, dict) and isinstance(row.get("flow_id"), str):
            referenced_ids.add(row["flow_id"])
    for row in plan.get("requirement_evidence", []):
        if isinstance(row, dict):
            for fid in row.get("flow_ids", []):
                if isinstance(fid, str):
                    referenced_ids.add(fid)
    for fid in sorted(referenced_ids):
        if fid not in flows and fid in catalog_flows_by_id:
            flows[fid] = catalog_flows_by_id[fid]
    return flows


def _load_committed_plan(
    root: Path,
    obs: preflight.Observations,
    *,
    plan_id: str,
    scope_id: str,
) -> dict[str, Any]:
    try:
        committed = commit.read_committed(root, scope_ids=[scope_id])
    except codec.CodecError as error:
        raise codec.CodecError(
            codec.Diagnostic(
                error.diagnostic.reason_code,
                error.diagnostic.stage or codec.Stage.BUNDLE,
                error.diagnostic.entity_id or plan_id,
                _tag_diagnostic(error.diagnostic, owning_stage="3B", entity_id=plan_id, resume_ref=records.CATALOG_PATH)["expected"],
                _tag_diagnostic(error.diagnostic, owning_stage="3B", entity_id=plan_id, resume_ref=records.CATALOG_PATH)["actual"],
                error.diagnostic.resume_ref or records.CATALOG_PATH,
            )
        ) from error

    obs.scan("docs/planning/b-route")
    catalog_raw = obs.read(records.CATALOG_PATH)
    if codec.raw_digest(catalog_raw) != committed["catalog_raw_digest"]:
        _fail(
            codec.ReasonCode.FILE_CHANGED,
            owning_stage="3B",
            entity_id=records.CATALOG_PATH,
            expected=committed["catalog_raw_digest"],
            actual=codec.raw_digest(catalog_raw),
            resume_ref=records.CATALOG_PATH,
            path=records.CATALOG_PATH,
        )
    catalog = codec.strict_json_loads(catalog_raw)
    policy = obs.json(catalog["policy_ref"]["path"])
    origins = obs.json(catalog["origins_ref"]["path"])

    scope_head = next(
        (row for row in catalog["scope_heads"] if row["scope_id"] == scope_id),
        None,
    )
    if scope_head is None:
        _fail(
            codec.ReasonCode.UNPUBLISHED,
            owning_stage="3B",
            entity_id=scope_id,
            expected="committed scope head in catalog",
            actual=[row["scope_id"] for row in catalog["scope_heads"]],
            resume_ref=records.CATALOG_PATH,
            path=records.CATALOG_PATH,
        )

    plan_ref = next(
        (row for row in scope_head["plan_refs"] if row["entity_id"] == plan_id),
        None,
    )
    if plan_ref is None or plan_ref["path"] not in committed["formal_paths"]:
        _fail(
            codec.ReasonCode.UNPUBLISHED,
            owning_stage="3B",
            entity_id=plan_id,
            expected="plan_id present in committed catalog scope head",
            actual=[row["entity_id"] for row in scope_head["plan_refs"]],
            resume_ref=records.CATALOG_PATH,
            path=records.CATALOG_PATH,
        )

    plan_raw = obs.read(plan_ref["path"])
    plan = codec.strict_json_loads(plan_raw)
    obs.read(scope_head["receipt_ref"]["path"])

    existing_binding_ref = next(
        (row for row in scope_head["binding_refs"] if row["entity_id"] == plan_id),
        None,
    )
    existing_binding = None
    if existing_binding_ref is not None:
        existing_binding = obs.json(existing_binding_ref["path"])

    for ref in scope_head["plan_refs"]:
        obs.read(ref["path"])
    for ref in scope_head["binding_refs"]:
        obs.read(ref["path"])

    loaded_owner_plans: dict[str, dict[str, Any]] = {plan_ref["path"]: plan}
    catalog_flows_by_id: dict[str, dict[str, Any]] = {}
    for owner in catalog.get("definition_owners", []):
        owner_path = owner["plan_ref"]["path"]
        if owner_path not in loaded_owner_plans:
            loaded_owner_plans[owner_path] = obs.json(owner_path)
        else:
            obs.read(owner_path)
        if owner.get("kind") == "flow":
            owner_plan = loaded_owner_plans[owner_path]
            for frow in owner_plan.get("definitions", {}).get("flows", []):
                if frow["id"] == owner["definition_id"]:
                    catalog_flows_by_id[frow["id"]] = frow
                    break

    return {
        "committed": committed,
        "catalog": catalog,
        "policy": policy,
        "origins": origins,
        "scope_head": scope_head,
        "plan_ref": plan_ref,
        "plan": plan,
        "existing_binding_ref": existing_binding_ref,
        "existing_binding": existing_binding,
        "catalog_flows_by_id": catalog_flows_by_id,
    }


def _verify_3a_and_source_identity(
    root: Path,
    obs: preflight.Observations,
    *,
    audit_ref: str,
    scope_id: str,
    plan: dict[str, Any],
    plan_path: str,
) -> tuple[sources.Observations, dict[str, Any]]:
    audit_path = preflight.path(audit_ref)
    audit_obs = sources.Observations(root)
    try:
        proof = source_audit.verify_current_proof(audit_obs, audit_path, scope_id=scope_id)
        audit_obs.verify()
        _mirror_audit_observations(obs, audit_obs)

        report = proof["report"]
        if report.get("planning_eligible") is not True:
            _fail(
                codec.ReasonCode.SEMANTIC_ERROR,
                owning_stage="3A",
                stage=codec.Stage.CONTENT,
                entity_id=scope_id,
                expected="3A audit report planning_eligible=true (real_model, zero semantic_blockers)",
                actual={
                    "planning_eligible": report.get("planning_eligible"),
                    "evidence_class": report.get("evidence_class"),
                    "semantic_blockers": report.get("semantic_blockers"),
                },
                resume_ref=audit_path,
                path=audit_path,
            )

        accounted_ref = audit_obs.json(proof["prefix"] + "/proof.json")["accounted_ref"]
        accounted_state, _accounted_report = sources.load_accounted(audit_obs, accounted_ref)
        _mirror_audit_observations(obs, audit_obs)

        src_id = plan["source_identity"]
        manifest_ref = src_id["manifest_ref"]
        ledger_ref = src_id["ledger_ref"]

        # Observe and verify every OwnedFile in plan.source_identity.
        for ref_name, owned_ref in (("manifest_ref", manifest_ref), ("ledger_ref", ledger_ref)):
            for file_entry in owned_ref["files"]:
                raw = obs.read(file_entry["path"])
                actual_digest = codec.raw_digest(raw)
                if actual_digest != file_entry["raw_digest"]:
                    _fail(
                        codec.ReasonCode.DIGEST_MISMATCH,
                        owning_stage="3A",
                        stage=codec.Stage.REFERENCE,
                        entity_id=file_entry["path"],
                        expected={"ref": ref_name, "raw_digest": file_entry["raw_digest"]},
                        actual={"ref": ref_name, "raw_digest": actual_digest},
                        resume_ref=audit_path,
                        path=file_entry["path"],
                    )

        plan_manifest_path = manifest_ref["ref"].partition("#")[0]
        plan_ledger_path = ledger_ref["ref"].partition("#")[0]
        plan_manifest = obs.json(plan_manifest_path)
        plan_ledger = obs.json(plan_ledger_path)

        audit_manifest = accounted_state["manifest"]
        audit_ledger = accounted_state["ledger"]

        if (
            audit_manifest.get("source_revision") != src_id["source_revision"]
            or audit_ledger.get("source_revision") != src_id["source_revision"]
            or plan_manifest.get("source_revision") != src_id["source_revision"]
            or plan_ledger.get("source_revision") != src_id["source_revision"]
        ):
            _fail(
                codec.ReasonCode.REVISION_MISMATCH,
                owning_stage="3A",
                stage=codec.Stage.REFERENCE,
                entity_id=plan["plan_id"],
                expected={"plan_source_revision": src_id["source_revision"]},
                actual={
                    "audit_manifest_revision": audit_manifest.get("source_revision"),
                    "audit_ledger_revision": audit_ledger.get("source_revision"),
                    "plan_manifest_revision": plan_manifest.get("source_revision"),
                    "plan_ledger_revision": plan_ledger.get("source_revision"),
                },
                resume_ref=audit_path,
                path=plan_path,
            )

        expected_manifest_digest = src_id["source_manifest_digest"]
        if (
            audit_manifest.get("manifest_sha256") != expected_manifest_digest
            or audit_ledger.get("source_manifest_sha256") != expected_manifest_digest
            or plan_manifest.get("manifest_sha256") != expected_manifest_digest
            or plan_ledger.get("source_manifest_sha256") != expected_manifest_digest
        ):
            _fail(
                codec.ReasonCode.DIGEST_MISMATCH,
                owning_stage="3A",
                stage=codec.Stage.REFERENCE,
                entity_id=plan["plan_id"],
                expected={"source_manifest_digest": expected_manifest_digest},
                actual={
                    "audit_manifest_sha256": audit_manifest.get("manifest_sha256"),
                    "audit_ledger_source_manifest_sha256": audit_ledger.get("source_manifest_sha256"),
                    "plan_manifest_sha256": plan_manifest.get("manifest_sha256"),
                    "plan_ledger_source_manifest_sha256": plan_ledger.get("source_manifest_sha256"),
                },
                resume_ref=audit_path,
                path=plan_path,
            )

        if (
            codec.canonical_digest(audit_manifest.get("sources")) != codec.canonical_digest(plan_manifest.get("sources"))
            or codec.canonical_digest(audit_ledger.get("blocks")) != codec.canonical_digest(plan_ledger.get("blocks"))
        ):
            _fail(
                codec.ReasonCode.INPUT_STALE,
                owning_stage="3A",
                stage=codec.Stage.REFERENCE,
                entity_id=plan["plan_id"],
                expected="3A audited manifest sources and ledger blocks match committed plan.source_identity",
                actual="source manifest or ledger content differs between 3A proof and 3B plan",
                resume_ref=audit_path,
                path=plan_path,
            )

        return audit_obs, {
            "audit_ref": audit_path,
            "scope_id": scope_id,
            "planning_eligible": True,
            "evidence_class": report.get("evidence_class"),
            "source_revision": src_id["source_revision"],
            "source_manifest_digest": expected_manifest_digest,
            "input_identity": report.get("input_identity"),
            "manifest_ref": manifest_ref,
            "ledger_ref": ledger_ref,
            "ledger_blocks": {row["block_id"]: row for row in plan_ledger.get("blocks", []) if isinstance(row, dict) and "block_id" in row},
        }
    except codec.CodecError as error:
        _mirror_audit_observations(obs, audit_obs, ignore_errors=True)
        tagged = _tag_diagnostic(error.diagnostic, owning_stage="3A", entity_id=scope_id, resume_ref=audit_path, path=audit_path)
        raise codec.CodecError(
            codec.Diagnostic(
                error.diagnostic.reason_code,
                error.diagnostic.stage or codec.Stage.CONTENT,
                tagged["entity_id"],
                tagged["expected"],
                tagged["actual"],
                tagged["resume_ref"],
            )
        ) from error
    except (OSError, ValueError, KeyError, TypeError) as error:
        _mirror_audit_observations(obs, audit_obs, ignore_errors=True)
        _fail(
            codec.ReasonCode.INPUT_STALE,
            owning_stage="3A",
            stage=codec.Stage.CONTENT,
            entity_id=scope_id,
            expected="valid current 3A source audit proof and plan.source_identity alignment",
            actual=f"{type(error).__name__}: {error}",
            resume_ref=audit_path,
            path=audit_path,
        )


def _verify_plan_dispositions(plan: dict[str, Any], plan_path: str) -> dict[str, Any]:
    req_by_id = {row["requirement_id"]: row for row in plan["requirements"]}
    ver_by_id: dict[str, dict[str, Any]] = {}
    for row in plan["requirement_verification"]:
        rid = row["requirement_id"]
        if rid in ver_by_id:
            _fail(
                codec.ReasonCode.MAPPING_MISMATCH,
                owning_stage="3B",
                stage=codec.Stage.CONTENT,
                entity_id=rid,
                expected="unique authoritative requirement_verification entry per requirement_id",
                actual="duplicate requirement_verification entry",
                resume_ref=plan_path,
                path=plan_path,
            )
        ver_by_id[rid] = row
        if row["disposition"] == "source_gap":
            _fail(
                codec.ReasonCode.SEMANTIC_ERROR,
                owning_stage="3B",
                stage=codec.Stage.CONTENT,
                entity_id=rid,
                expected="resolved disposition (flow | other_verification | deferred); source_gap blocks 3C",
                actual={"disposition": "source_gap", "rationale": row.get("rationale")},
                resume_ref=plan_path,
                path=plan_path,
            )

    app_by_id = {row["requirement_id"]: row for row in plan["applicability"]}
    for rid, row in app_by_id.items():
        if row["disposition"] == "source_gap":
            _fail(
                codec.ReasonCode.SEMANTIC_ERROR,
                owning_stage="3B",
                stage=codec.Stage.CONTENT,
                entity_id=rid,
                expected="resolved applicability disposition; source_gap blocks 3C",
                actual={"disposition": "source_gap", "rationale": row.get("rationale")},
                resume_ref=plan_path,
                path=plan_path,
            )

    dedup_evidence: list[dict[str, Any]] = []
    seen_evidence: set[tuple[str, str]] = set()
    for row in plan.get("requirement_evidence", []):
        key = (row["requirement_id"], row["evidence_id"])
        if key not in seen_evidence:
            seen_evidence.add(key)
            dedup_evidence.append(copy.deepcopy(row))

    route_memberships: list[dict[str, Any]] = []
    seen_routes: set[tuple[str, str]] = set()
    for row in plan.get("requirement_route_memberships", []):
        key = (row["requirement_id"], row["flow_id"])
        if key not in seen_routes:
            seen_routes.add(key)
            route_memberships.append(copy.deepcopy(row))

    counts = {"flow": 0, "other_verification": 0, "deferred": 0, "source_gap": 0}
    for row in ver_by_id.values():
        counts[row["disposition"]] = counts.get(row["disposition"], 0) + 1

    return {
        "requirements": req_by_id,
        "verifications": ver_by_id,
        "applicability": app_by_id,
        "route_memberships": route_memberships,
        "shared_evidence": dedup_evidence,
        "dispositions_summary": counts,
    }


def _load_triplet(obs: preflight.Observations) -> dict[str, Any]:
    master_raw = obs.read(inventory.TRIPLET["master"])
    back_raw = obs.read(inventory.TRIPLET["back"])
    gameplay_raw = obs.read(inventory.TRIPLET["gameplay"])
    master_doc = codec.strict_json_loads(master_raw)
    back_doc = codec.strict_json_loads(back_raw)
    gameplay_doc = codec.strict_json_loads(gameplay_raw)
    try:
        master_tasks, view_ids = records.TaskJoinContext(
            master=master_doc, back=back_doc, gameplay=gameplay_doc
        ).indexes()
    except codec.CodecError as error:
        tagged = _tag_diagnostic(
            error.diagnostic,
            owning_stage="3C",
            resume_ref=inventory.TRIPLET["master"],
            path=inventory.TRIPLET["master"],
        )
        raise codec.CodecError(
            codec.Diagnostic(
                error.diagnostic.reason_code,
                error.diagnostic.stage or codec.Stage.BUNDLE,
                tagged["entity_id"],
                tagged["expected"],
                tagged["actual"],
                tagged["resume_ref"],
            )
        ) from error

    back_by_tid = {row["taskmaster_id"]: row for row in back_doc}
    gameplay_by_tid = {row["taskmaster_id"]: row for row in gameplay_doc}
    back_by_bid = {row["id"]: row for row in back_doc}
    gameplay_by_bid = {row["id"]: row for row in gameplay_doc}
    return {
        "documents": {"master": master_doc, "back": back_doc, "gameplay": gameplay_doc},
        "master": master_tasks,
        "view_ids": view_ids,
        "back_by_tid": back_by_tid,
        "gameplay_by_tid": gameplay_by_tid,
        "back_by_bid": back_by_bid,
        "gameplay_by_bid": gameplay_by_bid,
    }


def _verify_optional_protection(
    root: Path,
    obs: preflight.Observations,
    protection_ref: str | None,
) -> dict[str, Any] | None:
    if not protection_ref:
        return None
    ref_path = preflight.path(protection_ref)
    doc = obs.json(ref_path)
    is_protection_input = isinstance(doc, dict) and doc.get("document_version") == preflight.PROTECTION_VERSION
    if is_protection_input:
        definition = doc.get("definition")
        if not isinstance(definition, dict):
            _fail(
                codec.ReasonCode.INVALID_TYPE,
                owning_stage="3C",
                entity_id=ref_path,
                expected="protection-input definition object",
                actual=type(definition).__name__,
                resume_ref=ref_path,
                path=ref_path,
            )
        if (
            definition.get("projection_codec") != codec.PROJECTION_CODEC
            or definition.get("content_codec") != codec.CODEC_VERSION
            or definition.get("mutable_allowlist") != ["Task.status", "Task.subtasks[].status"]
        ):
            _fail(
                codec.ReasonCode.UNKNOWN_CODEC_VERSION,
                owning_stage="3C",
                entity_id=ref_path,
                expected="Story 1.5 exact definition projection",
                actual=definition,
                resume_ref=ref_path,
                path=ref_path,
            )
        if not protection._same_json(doc.get("authorization"), protection.AUTHORIZATION):
            _fail(
                codec.ReasonCode.CONFLICT,
                owning_stage="3C",
                entity_id=ref_path,
                expected=protection.AUTHORIZATION,
                actual=doc.get("authorization"),
                resume_ref=ref_path,
                path=ref_path,
            )
        for key in (
            "inventory_ref",
            "snapshot_ref",
            "task_definitions_ref",
            "triplet_definition_ref",
            "raw_archive_index_ref",
            "frozen_a_candidates_ref",
            "historical_inventory_ref",
        ):
            if key in doc:
                preflight.owned(doc[key], obs)
        if type(doc.get("manifest_refs")) is not list:
            _fail(
                codec.ReasonCode.INVALID_TYPE,
                owning_stage="3C",
                entity_id=ref_path,
                expected="manifest_refs array",
                actual=type(doc.get("manifest_refs")).__name__,
                resume_ref=ref_path,
                path=ref_path,
            )
        for reference in doc.get("rules_refs", []):
            if type(reference) is not dict or not {"path", "raw_digest"} <= set(reference):
                _fail(
                    codec.ReasonCode.INVALID_REFERENCE,
                    owning_stage="3C",
                    entity_id=ref_path,
                    expected="rule identity with path and raw_digest",
                    actual=reference,
                    resume_ref=ref_path,
                    path=ref_path,
                )
            preflight._binding({key: reference[key] for key in ("path", "raw_digest")}, obs)
        if type(doc.get("review")) is not dict or "evidence_ref" not in doc["review"]:
            _fail(
                codec.ReasonCode.INVALID_REFERENCE,
                owning_stage="3C",
                entity_id=ref_path,
                expected="external review evidence_ref",
                actual=doc.get("review"),
                resume_ref=ref_path,
                path=ref_path,
            )
        preflight.owned(doc["review"]["evidence_ref"], obs)
        snap_ref = doc.get("snapshot_ref")
        inv_ref = doc.get("inventory_ref")
        if (
            not isinstance(snap_ref, dict)
            or not isinstance(snap_ref.get("ref"), str)
            or not isinstance(inv_ref, dict)
            or not isinstance(inv_ref.get("files"), list)
            or not inv_ref["files"]
        ):
            _fail(
                codec.ReasonCode.MISSING_REQUIRED_FIELD,
                owning_stage="3C",
                entity_id=ref_path,
                expected="protection-input snapshot_ref and inventory_ref",
                actual={"snapshot_ref": snap_ref, "inventory_ref": inv_ref},
                resume_ref=ref_path,
                path=ref_path,
            )
        snapshot_path = preflight.path(snap_ref["ref"].split("#", 1)[0])
        obs.read(snapshot_path)
    elif isinstance(doc, dict) and doc.get("schema_version") == protection.SCHEMA:
        snapshot_path = ref_path
    else:
        _fail(
            codec.ReasonCode.UNKNOWN_SCHEMA,
            owning_stage="3C",
            stage=codec.Stage.SCHEMA,
            entity_id=ref_path,
            expected=[preflight.PROTECTION_VERSION, protection.SCHEMA],
            actual=(
                doc.get("document_version") or doc.get("schema_version")
                if isinstance(doc, dict)
                else type(doc).__name__
            ),
            resume_ref=ref_path,
            path=ref_path,
        )

    verified = protection.verify_protection(root, snapshot_path)
    if not verified.get("ok"):
        _fail(
            codec.ReasonCode.IDENTITY_UNPROVABLE,
            owning_stage="3C",
            entity_id=snapshot_path,
            expected="valid verified Story 1.5 protection archive",
            actual=verified.get("diagnostics"),
            resume_ref=snapshot_path,
            path=snapshot_path,
        )

    # Record every protection snapshot archive file in obs for end-of-run re-read drift checks.
    snapshot_doc = obs.json(snapshot_path)
    parent = snapshot_path.rsplit("/", 1)[0] + "/" if "/" in snapshot_path else ""
    obs.read(parent + "inventory.json")
    for row in snapshot_doc.get("raw_files", []):
        if isinstance(row, dict) and row.get("exists") is True and isinstance(row.get("artifact"), str):
            archived = obs.read(parent + row["artifact"])
            if codec.raw_digest(archived) != row.get("raw_digest"):
                _fail(
                    codec.ReasonCode.DIGEST_MISMATCH,
                    owning_stage="3C",
                    entity_id=row.get("path"),
                    expected=row.get("raw_digest"),
                    actual=codec.raw_digest(archived),
                    resume_ref=snapshot_path,
                    path=parent + row["artifact"],
                )
    if is_protection_input:
        inv_digest = doc["inventory_ref"]["files"][0].get("raw_digest")
        if snapshot_doc.get("inventory", {}).get("raw_digest") != inv_digest:
            _fail(
                codec.ReasonCode.CONFLICT,
                owning_stage="3C",
                entity_id=ref_path,
                expected=inv_digest,
                actual=snapshot_doc.get("inventory", {}).get("raw_digest"),
                resume_ref=ref_path,
                path=ref_path,
            )

    if verified.get("capture_complete") is not True:
        _fail(
            codec.ReasonCode.IDENTITY_UNPROVABLE,
            owning_stage="3C",
            entity_id=snapshot_path,
            expected="verified protection snapshot with capture_complete=true",
            actual={
                "capture_complete": verified.get("capture_complete"),
                "unresolved_inventory_diagnostics": verified.get("unresolved_inventory_diagnostics"),
            },
            resume_ref=snapshot_path,
            path=snapshot_path,
        )

    return {
        "path": ref_path,
        "snapshot_path": snapshot_path,
        "snapshot_digest": verified.get("snapshot_digest"),
        "capture_complete": True,
        "ok": True,
    }


def _load_optional_manifest(
    obs: preflight.Observations,
    manifest_ref: str | None,
) -> dict[str, Any] | None:
    if not manifest_ref:
        return None
    m_path = preflight.path(manifest_ref)
    raw = obs.read(m_path)
    doc = codec.strict_json_loads(raw)
    if type(doc) is not dict:
        _fail(
            codec.ReasonCode.INVALID_TYPE,
            owning_stage="3C",
            entity_id=m_path,
            expected="MVG manifest JSON object",
            actual=type(doc).__name__,
            resume_ref=m_path,
            path=m_path,
        )
    return {
        "path": m_path,
        "raw_digest": codec.raw_digest(raw),
        "canonical_digest": codec.canonical_digest(doc),
        "document": doc,
        "owned_ref": {
            "owner": "manifest",
            "ref": m_path,
            "files": [{"path": m_path, "raw_digest": codec.raw_digest(raw)}],
        },
    }


def _validate_change_intents(
    obs: preflight.Observations,
    change_intents_ref: str | None,
    *,
    plan: dict[str, Any],
    flows_by_id: dict[str, dict[str, Any]],
    triplet: dict[str, Any],
    manifest_info: dict[str, Any] | None,
    ledger_blocks: dict[str, Any],
) -> dict[str, Any] | None:
    if not change_intents_ref:
        return None
    ci_path = preflight.path(change_intents_ref)
    doc = obs.json(ci_path)
    if type(doc) is not dict or doc.get("schema_version") != CHANGE_INTENTS_SCHEMA:
        _fail(
            codec.ReasonCode.UNKNOWN_SCHEMA,
            owning_stage="3C",
            stage=codec.Stage.SCHEMA,
            entity_id=ci_path,
            expected=CHANGE_INTENTS_SCHEMA,
            actual=doc.get("schema_version") if isinstance(doc, dict) else type(doc).__name__,
            resume_ref=ci_path,
            path=ci_path,
        )
    operations = doc.get("operations")
    if type(operations) is not list:
        _fail(
            codec.ReasonCode.INVALID_TYPE,
            owning_stage="3C",
            entity_id=ci_path,
            expected="operations array",
            actual=type(operations).__name__,
            resume_ref=ci_path,
            path=ci_path,
        )

    plan_req_ids = {row["requirement_id"] for row in plan["requirements"]}
    allowed_flow_ids = set(flows_by_id)
    seen_targets: set[tuple[str, int]] = set()
    seen_candidate_keys: set[str] = set()
    seen_business_ids: set[str] = set(triplet["back_by_bid"]) | set(triplet["gameplay_by_bid"])

    def register_target(view_name: str, tid: int) -> None:
        if (view_name, tid) in seen_targets:
            _fail(
                codec.ReasonCode.CONFLICT,
                owning_stage="3C",
                entity_id=str(tid),
                expected="at most one change intent per existing (view, task_id)",
                actual=[view_name, tid],
                resume_ref=ci_path,
                path=ci_path,
            )
        seen_targets.add((view_name, tid))

    def check_not_story_like(val: Any, label: str) -> None:
        if _is_story_like_id(val):
            _fail(
                codec.ReasonCode.SEMANTIC_ERROR,
                owning_stage="3C",
                entity_id=str(val),
                expected="Task/business/candidate identifier (never Story ID)",
                actual={label: val},
                resume_ref=ci_path,
                path=ci_path,
            )

    def check_roles(roles_val: Any, entity: str) -> list[str]:
        if type(roles_val) is not list or any(r not in ALLOWED_ROLES for r in roles_val):
            _fail(
                codec.ReasonCode.INVALID_ENUM,
                owning_stage="3C",
                entity_id=entity,
                expected=sorted(ALLOWED_ROLES),
                actual=roles_val,
                resume_ref=ci_path,
                path=ci_path,
            )
        return sorted(set(roles_val))

    def check_part_kinds(kinds_val: Any, entity: str) -> list[str]:
        if type(kinds_val) is not list or any(k not in PART_KINDS for k in kinds_val):
            _fail(
                codec.ReasonCode.INVALID_ENUM,
                owning_stage="3C",
                entity_id=entity,
                expected=list(PART_KINDS),
                actual=kinds_val,
                resume_ref=ci_path,
                path=ci_path,
            )
        return sorted(set(kinds_val))

    def check_id_lists(container: dict[str, Any], entity: str) -> tuple[list[str], list[str]]:
        raw_reqs = container.get("requirement_ids", [])
        if type(raw_reqs) is not list or any(type(r) is not str or not r.strip() for r in raw_reqs):
            _fail(
                codec.ReasonCode.INVALID_TYPE,
                owning_stage="3C",
                entity_id=entity,
                expected="requirement_ids array of nonempty strings",
                actual=raw_reqs,
                resume_ref=ci_path,
                path=ci_path,
            )
        unknown_reqs = sorted(set(raw_reqs) - plan_req_ids)
        if unknown_reqs:
            _fail(
                codec.ReasonCode.UNRESOLVED_REFERENCE,
                owning_stage="3C",
                entity_id=entity,
                expected="requirement_ids declared in committed 3B plan",
                actual=unknown_reqs,
                resume_ref=ci_path,
                path=ci_path,
            )

        raw_flows = container.get("flow_ids", [])
        if type(raw_flows) is not list or any(type(f) is not str or not f.strip() for f in raw_flows):
            _fail(
                codec.ReasonCode.INVALID_TYPE,
                owning_stage="3C",
                entity_id=entity,
                expected="flow_ids array of nonempty strings",
                actual=raw_flows,
                resume_ref=ci_path,
                path=ci_path,
            )
        unknown_flows = sorted(set(raw_flows) - allowed_flow_ids)
        if unknown_flows:
            _fail(
                codec.ReasonCode.UNRESOLVED_REFERENCE,
                owning_stage="3C",
                entity_id=entity,
                expected="flow_ids declared in committed 3B plan or catalog definition_owners",
                actual=unknown_flows,
                resume_ref=ci_path,
                path=ci_path,
            )

        if "obligation_ids" in container:
            raw_obls = container["obligation_ids"]
            if type(raw_obls) is not list or any(type(o) is not str or not o.strip() for o in raw_obls):
                _fail(
                    codec.ReasonCode.INVALID_TYPE,
                    owning_stage="3C",
                    entity_id=entity,
                    expected="obligation_ids array of nonempty strings",
                    actual=raw_obls,
                    resume_ref=ci_path,
                    path=ci_path,
                )
        return sorted(set(raw_reqs)), sorted(set(raw_flows))

    def register_candidate(
        *,
        view_name: str,
        action_name: str,
        f_ids: list[str],
        req_ids: list[str],
        explicit_ckey: Any,
        explicit_bid: Any,
        entity: str,
        split_index: int = 0,
    ) -> tuple[str, str]:
        if explicit_ckey is not None:
            _validate_nonempty_str(explicit_ckey, f"{entity}.candidate_key", path=ci_path)
            check_not_story_like(explicit_ckey, f"{entity}.candidate_key")
            ckey = explicit_ckey
        else:
            ckey = _candidate_key(
                plan["plan_id"], view_name, action_name, f_ids, req_ids, split_index=split_index
            )
        if ckey in seen_candidate_keys:
            _fail(
                codec.ReasonCode.CONFLICT,
                owning_stage="3C",
                entity_id=ckey,
                expected="unique candidate_key across all create/split/merge candidates",
                actual=ckey,
                resume_ref=ci_path,
                path=ci_path,
            )
        seen_candidate_keys.add(ckey)

        if explicit_bid is not None:
            _validate_nonempty_str(explicit_bid, f"{entity}.business_id", path=ci_path)
            check_not_story_like(explicit_bid, f"{entity}.business_id")
            bid = explicit_bid
        else:
            bid = _candidate_business_id(view_name, ckey)
        if bid in seen_business_ids:
            _fail(
                codec.ReasonCode.CONFLICT,
                owning_stage="3C",
                entity_id=bid,
                expected="unique business_id across existing tasks and proposed candidates",
                actual=bid,
                resume_ref=ci_path,
                path=ci_path,
            )
        seen_business_ids.add(bid)
        return ckey, bid

    def check_evidence_path(raw_ref: str, entity: str) -> None:
        base_path = raw_ref.split("#", 1)[0].split(":", 1)[0]
        canonical = preflight.path(base_path)
        obs.read(canonical)

    def check_governance_fields(op: dict[str, Any], entity: str) -> None:
        scope = op.get("scope")
        if not (
            (isinstance(scope, str) and scope.strip())
            or (isinstance(scope, dict) and bool(scope))
        ):
            _fail(
                codec.ReasonCode.MISSING_REQUIRED_FIELD,
                owning_stage="3C",
                entity_id=entity,
                expected="nonempty scope for update/split/merge/retire",
                actual=scope,
                resume_ref=ci_path,
                path=ci_path,
            )
        evidence = op.get("source_diff_evidence")
        if type(evidence) is not list or not evidence:
            _fail(
                codec.ReasonCode.MISSING_REQUIRED_FIELD,
                owning_stage="3C",
                entity_id=entity,
                expected="nonempty source_diff_evidence list grounded in 3A/3B sources",
                actual=evidence,
                resume_ref=ci_path,
                path=ci_path,
            )
        for ev in evidence:
            if isinstance(ev, str):
                if not ev.strip() or ev != ev.strip():
                    _fail(
                        codec.ReasonCode.INVALID_TYPE,
                        owning_stage="3C",
                        entity_id=entity,
                        expected="nonempty unpadded anchored source_diff_evidence entry",
                        actual=ev,
                        resume_ref=ci_path,
                        path=ci_path,
                    )
                if ev in ledger_blocks or ev in plan_req_ids or ev in allowed_flow_ids:
                    continue
                if "/" in ev:
                    check_evidence_path(ev, entity)
                    continue
                _fail(
                    codec.ReasonCode.UNRESOLVED_REFERENCE,
                    owning_stage="3C",
                    entity_id=entity,
                    expected="source_diff_evidence anchored to a 3A block_id, 3B requirement/flow ID, or existing source path",
                    actual=ev,
                    resume_ref=ci_path,
                    path=ci_path,
                )
            elif isinstance(ev, dict):
                if not ev:
                    _fail(
                        codec.ReasonCode.MISSING_REQUIRED_FIELD,
                        owning_stage="3C",
                        entity_id=entity,
                        expected="nonempty anchored source_diff_evidence object",
                        actual=ev,
                        resume_ref=ci_path,
                        path=ci_path,
                    )
                anchored = False
                if "block_id" in ev:
                    block_id = _validate_nonempty_str(ev["block_id"], f"{entity}.source_diff_evidence.block_id", path=ci_path)
                    if ledger_blocks and block_id not in ledger_blocks:
                        _fail(
                            codec.ReasonCode.UNRESOLVED_REFERENCE,
                            owning_stage="3C",
                            entity_id=entity,
                            expected="source_diff_evidence block_id present in 3A ledger",
                            actual=block_id,
                            resume_ref=ci_path,
                            path=ci_path,
                        )
                    anchored = True
                if "requirement_id" in ev:
                    rid = _validate_nonempty_str(ev["requirement_id"], f"{entity}.source_diff_evidence.requirement_id", path=ci_path)
                    if rid not in plan_req_ids:
                        _fail(
                            codec.ReasonCode.UNRESOLVED_REFERENCE,
                            owning_stage="3C",
                            entity_id=entity,
                            expected="source_diff_evidence requirement_id declared in committed 3B plan",
                            actual=rid,
                            resume_ref=ci_path,
                            path=ci_path,
                        )
                    anchored = True
                if "flow_id" in ev:
                    fid = _validate_nonempty_str(ev["flow_id"], f"{entity}.source_diff_evidence.flow_id", path=ci_path)
                    if fid not in allowed_flow_ids:
                        _fail(
                            codec.ReasonCode.UNRESOLVED_REFERENCE,
                            owning_stage="3C",
                            entity_id=entity,
                            expected="source_diff_evidence flow_id declared in committed 3B plan or catalog",
                            actual=fid,
                            resume_ref=ci_path,
                            path=ci_path,
                        )
                    anchored = True
                for path_key in ("path", "source_ref"):
                    if path_key in ev:
                        raw_p = _validate_nonempty_str(ev[path_key], f"{entity}.source_diff_evidence.{path_key}", path=ci_path)
                        check_evidence_path(raw_p, entity)
                        anchored = True
                if not anchored:
                    _fail(
                        codec.ReasonCode.MISSING_REQUIRED_FIELD,
                        owning_stage="3C",
                        entity_id=entity,
                        expected="source_diff_evidence object with block_id, requirement_id, flow_id, path, or source_ref",
                        actual=ev,
                        resume_ref=ci_path,
                        path=ci_path,
                    )
            else:
                _fail(
                    codec.ReasonCode.INVALID_TYPE,
                    owning_stage="3C",
                    entity_id=entity,
                    expected="string or object source_diff_evidence entry",
                    actual=type(ev).__name__,
                    resume_ref=ci_path,
                    path=ci_path,
                )
        lineage = op.get("lineage")
        if type(lineage) is not dict or not lineage:
            _fail(
                codec.ReasonCode.MISSING_REQUIRED_FIELD,
                owning_stage="3C",
                entity_id=entity,
                expected="explicit lineage mapping for update/split/merge/retire",
                actual=lineage,
                resume_ref=ci_path,
                path=ci_path,
            )
        rationale = op.get("rationale")
        if type(rationale) is not str or not rationale.strip():
            _fail(
                codec.ReasonCode.MISSING_REQUIRED_FIELD,
                owning_stage="3C",
                entity_id=entity,
                expected="nonempty rationale for update/split/merge/retire",
                actual=rationale,
                resume_ref=ci_path,
                path=ci_path,
            )

    def check_mature_protections(
        op: dict[str, Any],
        existing_master: dict[str, Any],
        existing_view: dict[str, Any],
        view_name: str,
        *,
        check_identity_match: bool = True,
        disallow_status: bool = False,
    ) -> None:
        tid = existing_master["id"]
        bid = existing_view["id"]
        proposed = op.get("proposed_fields")
        if proposed is None:
            return
        if type(proposed) is not dict:
            _fail(
                codec.ReasonCode.INVALID_TYPE,
                owning_stage="3C",
                entity_id=str(tid),
                expected="proposed_fields object",
                actual=type(proposed).__name__,
                resume_ref=ci_path,
                path=ci_path,
            )
        if "id" in proposed:
            check_not_story_like(proposed["id"], "proposed_fields.id")
        if "taskmaster_id" in proposed:
            check_not_story_like(proposed["taskmaster_id"], "proposed_fields.taskmaster_id")
        if disallow_status:
            if "status" in proposed:
                _fail(
                    codec.ReasonCode.CONFLICT,
                    owning_stage="3C",
                    entity_id=str(tid),
                    expected="new merge candidate must not forge or overwrite mature Task status",
                    actual={"proposed_status": proposed["status"]},
                    resume_ref=ci_path,
                    path=ci_path,
                )
        elif check_identity_match and "status" in proposed and proposed["status"] != existing_master.get("status"):
            _fail(
                codec.ReasonCode.CONFLICT,
                owning_stage="3C",
                entity_id=str(tid),
                expected={"status": existing_master.get("status"), "rule": "never overwrite mature Task status"},
                actual={"proposed_status": proposed["status"]},
                resume_ref=ci_path,
                path=ci_path,
            )
        if "subtasks" in proposed and isinstance(proposed["subtasks"], list):
            old_sub = {s.get("id"): s.get("status") for s in existing_master.get("subtasks", []) if isinstance(s, dict)}
            for sub in proposed["subtasks"]:
                if isinstance(sub, dict) and sub.get("id") in old_sub:
                    if "status" in sub and sub["status"] != old_sub[sub["id"]]:
                        _fail(
                            codec.ReasonCode.CONFLICT,
                            owning_stage="3C",
                            entity_id=str(tid),
                            expected={"subtask_status": old_sub[sub["id"]]},
                            actual={"proposed_subtask_status": sub["status"]},
                            resume_ref=ci_path,
                            path=ci_path,
                        )
        if check_identity_match:
            if "taskmaster_id" in proposed and proposed["taskmaster_id"] != tid:
                _fail(
                    codec.ReasonCode.CONFLICT,
                    owning_stage="3C",
                    entity_id=str(tid),
                    expected={"taskmaster_id": tid},
                    actual={"proposed_taskmaster_id": proposed["taskmaster_id"]},
                    resume_ref=ci_path,
                    path=ci_path,
                )
            if "id" in proposed and proposed["id"] != bid:
                _fail(
                    codec.ReasonCode.CONFLICT,
                    owning_stage="3C",
                    entity_id=str(tid),
                    expected={"business_id": bid},
                    actual={"proposed_business_id": proposed["id"]},
                    resume_ref=ci_path,
                    path=ci_path,
                )
        # Prevent weakening existing Acceptance or stripping history/evidence/tests.
        for list_field in ("acceptance", "history", "evidence_refs", "test_refs"):
            if list_field in proposed:
                old_items = existing_view.get(list_field, existing_master.get(list_field, []))
                new_items = proposed[list_field]
                if not isinstance(new_items, list):
                    _fail(
                        codec.ReasonCode.INVALID_TYPE,
                        owning_stage="3C",
                        entity_id=str(tid),
                        expected=f"{list_field} list",
                        actual=type(new_items).__name__,
                        resume_ref=ci_path,
                        path=ci_path,
                    )
                old_set = {codec.canonical_digest(x) for x in old_items}
                new_set = {codec.canonical_digest(x) for x in new_items}
                if old_set - new_set:
                    _fail(
                        codec.ReasonCode.SEMANTIC_ERROR,
                        owning_stage="3C",
                        entity_id=str(tid),
                        expected=f"preserve existing {list_field}; weakening or history loss forbidden",
                        actual={"removed_count": len(old_set - new_set), "field": list_field},
                        resume_ref=ci_path,
                        path=ci_path,
                    )

    for idx, op in enumerate(operations):
        if type(op) is not dict:
            _fail(
                codec.ReasonCode.INVALID_TYPE,
                owning_stage="3C",
                entity_id=f"operations[{idx}]",
                expected="operation object",
                actual=type(op).__name__,
                resume_ref=ci_path,
                path=ci_path,
            )
        action = op.get("action")
        if action not in ALLOWED_ACTIONS:
            _fail(
                codec.ReasonCode.INVALID_ENUM,
                owning_stage="3C",
                entity_id=f"operations[{idx}]",
                expected=sorted(ALLOWED_ACTIONS),
                actual=action,
                resume_ref=ci_path,
                path=ci_path,
            )

        # Validate Story-ID-as-Task-ID anywhere in task_id / source_task_id / target_task_id / business_id.
        for id_field in ("task_id", "source_task_id", "target_task_id"):
            if id_field in op and op[id_field] is not None:
                val = op[id_field]
                if _is_story_like_id(val) or type(val) is not int or val < 1:
                    _fail(
                        codec.ReasonCode.SEMANTIC_ERROR,
                        owning_stage="3C",
                        entity_id=str(val),
                        expected="positive integer Task ID (never Story ID)",
                        actual={id_field: val},
                        resume_ref=ci_path,
                        path=ci_path,
                    )
        for bid_field in ("business_id", "proposed_business_id"):
            if bid_field in op and op[bid_field] is not None:
                check_not_story_like(op[bid_field], f"operations[{idx}].{bid_field}")

        if action in MUTATING_ACTIONS:
            check_governance_fields(op, f"operations[{idx}]:{action}")

        if action == "create":
            if op.get("task_id") is not None:
                _fail(
                    codec.ReasonCode.SEMANTIC_ERROR,
                    owning_stage="3C",
                    entity_id=str(op.get("task_id")),
                    expected="task_id=null for create (permanent ID allocation belongs to Story 3.2)",
                    actual=op.get("task_id"),
                    resume_ref=ci_path,
                    path=ci_path,
                )
            view = op.get("view")
            if view not in ("back", "gameplay"):
                _fail(
                    codec.ReasonCode.INVALID_ENUM,
                    owning_stage="3C",
                    entity_id=f"operations[{idx}]",
                    expected=["back", "gameplay"],
                    actual=view,
                    resume_ref=ci_path,
                    path=ci_path,
                )
            req_ids, f_ids = check_id_lists(op, f"operations[{idx}]")
            register_candidate(
                view_name=view,
                action_name="create",
                f_ids=f_ids,
                req_ids=req_ids,
                explicit_ckey=op.get("candidate_key"),
                explicit_bid=op.get("proposed_business_id") if op.get("proposed_business_id") is not None else op.get("business_id"),
                entity=f"operations[{idx}]",
            )
            if "roles" in op:
                check_roles(op["roles"], f"operations[{idx}].roles")
            if "part_kinds" in op:
                check_part_kinds(op["part_kinds"], f"operations[{idx}].part_kinds")

        elif action in ("reuse", "update", "retire"):
            tid = op.get("task_id")
            view = op.get("view")
            if view not in ("back", "gameplay") or type(tid) is not int or tid not in triplet["master"]:
                _fail(
                    codec.ReasonCode.MAPPING_MISMATCH,
                    owning_stage="3C",
                    entity_id=str(tid),
                    expected="existing master task_id and valid view (back|gameplay)",
                    actual={"task_id": tid, "view": view},
                    resume_ref=ci_path,
                    path=ci_path,
                )
            view_map = triplet["back_by_tid"] if view == "back" else triplet["gameplay_by_tid"]
            if tid not in view_map:
                _fail(
                    codec.ReasonCode.MAPPING_MISMATCH,
                    owning_stage="3C",
                    entity_id=str(tid),
                    expected=f"existing task_id {tid} in {view} view",
                    actual={"task_id": tid, "view": view},
                    resume_ref=ci_path,
                    path=ci_path,
                )
            existing_view = view_map[tid]
            if "business_id" in op and op["business_id"] != existing_view["id"]:
                _fail(
                    codec.ReasonCode.CONFLICT,
                    owning_stage="3C",
                    entity_id=str(tid),
                    expected={"business_id": existing_view["id"]},
                    actual={"business_id": op["business_id"]},
                    resume_ref=ci_path,
                    path=ci_path,
                )
            register_target(view, tid)
            check_id_lists(op, f"operations[{idx}]")
            check_mature_protections(op, triplet["master"][tid], existing_view, view)
            if "roles" in op:
                check_roles(op["roles"], f"operations[{idx}].roles")
            if "part_kinds" in op:
                check_part_kinds(op["part_kinds"], f"operations[{idx}].part_kinds")
            if action == "retire":
                auth_ref = op.get("authority_ref")
                if auth_ref is not None:
                    auth_str = _validate_nonempty_str(auth_ref, f"operations[{idx}].authority_ref", path=ci_path)
                    auth_file = preflight.path(auth_str.split("#", 1)[0])
                    obs.read(auth_file)
                # Ungrounded retire check: retiring a task that still covers an active plan requirement
                # without reviewed authority / replacement is blocked.
                existing_reqs = set(existing_view.get("requirement_ids", []))
                active_plan_reqs = {
                    rid
                    for rid, vrow in {r["requirement_id"]: r for r in plan["requirement_verification"]}.items()
                    if vrow["disposition"] in ("flow", "other_verification")
                }
                if existing_reqs & active_plan_reqs and not auth_ref:
                    _fail(
                        codec.ReasonCode.SEMANTIC_ERROR,
                        owning_stage="3C",
                        entity_id=str(tid),
                        expected="cannot retire mature Task covering active Requirements without reviewed authority_ref",
                        actual={"active_requirements": sorted(existing_reqs & active_plan_reqs)},
                        resume_ref=ci_path,
                        path=ci_path,
                    )

        elif action == "split":
            src_tid = op.get("source_task_id")
            view = op.get("view")
            if view not in ("back", "gameplay") or type(src_tid) is not int or src_tid not in triplet["master"]:
                _fail(
                    codec.ReasonCode.MAPPING_MISMATCH,
                    owning_stage="3C",
                    entity_id=str(src_tid),
                    expected="existing source_task_id and valid view for split",
                    actual={"source_task_id": src_tid, "view": view},
                    resume_ref=ci_path,
                    path=ci_path,
                )
            view_map = triplet["back_by_tid"] if view == "back" else triplet["gameplay_by_tid"]
            if src_tid not in view_map:
                _fail(
                    codec.ReasonCode.MAPPING_MISMATCH,
                    owning_stage="3C",
                    entity_id=str(src_tid),
                    expected=f"source_task_id {src_tid} present in {view} view",
                    actual={"source_task_id": src_tid, "view": view},
                    resume_ref=ci_path,
                    path=ci_path,
                )
            register_target(view, src_tid)
            check_mature_protections(op, triplet["master"][src_tid], view_map[src_tid], view)
            targets = op.get("targets")
            if type(targets) is not list or len(targets) < 2:
                _fail(
                    codec.ReasonCode.SEMANTIC_ERROR,
                    owning_stage="3C",
                    entity_id=str(src_tid),
                    expected="at least 2 split targets",
                    actual=len(targets) if isinstance(targets, list) else type(targets).__name__,
                    resume_ref=ci_path,
                    path=ci_path,
                )
            for t_idx, target in enumerate(targets, start=1):
                if type(target) is not dict:
                    _fail(
                        codec.ReasonCode.INVALID_TYPE,
                        owning_stage="3C",
                        entity_id=f"{src_tid}:split[{t_idx}]",
                        expected="split target object",
                        actual=type(target).__name__,
                        resume_ref=ci_path,
                        path=ci_path,
                    )
                if target.get("task_id") is not None:
                    _fail(
                        codec.ReasonCode.SEMANTIC_ERROR,
                        owning_stage="3C",
                        entity_id=str(target.get("task_id")),
                        expected="task_id=null for split target (Story 3.2 owns permanent IDs)",
                        actual=target.get("task_id"),
                        resume_ref=ci_path,
                        path=ci_path,
                    )
                t_view = target.get("view", view)
                if t_view not in ("back", "gameplay"):
                    _fail(
                        codec.ReasonCode.INVALID_ENUM,
                        owning_stage="3C",
                        entity_id=f"{src_tid}:split[{t_idx}]",
                        expected=["back", "gameplay"],
                        actual=t_view,
                        resume_ref=ci_path,
                        path=ci_path,
                    )
                t_reqs, t_flows = check_id_lists(target, f"{src_tid}:split[{t_idx}]")
                register_candidate(
                    view_name=t_view,
                    action_name="split",
                    f_ids=t_flows,
                    req_ids=t_reqs,
                    explicit_ckey=target.get("candidate_key"),
                    explicit_bid=(
                        target.get("proposed_business_id")
                        if target.get("proposed_business_id") is not None
                        else target.get("business_id")
                    ),
                    entity=f"{src_tid}:split[{t_idx}]",
                    split_index=t_idx,
                )
                if "roles" in target:
                    check_roles(target["roles"], f"split[{t_idx}].roles")
                if "part_kinds" in target:
                    check_part_kinds(target["part_kinds"], f"split[{t_idx}].part_kinds")

        elif action == "merge":
            src_tids = op.get("source_task_ids")
            view = op.get("view")
            if (
                view not in ("back", "gameplay")
                or type(src_tids) is not list
                or len(src_tids) < 2
                or len(set(src_tids)) != len(src_tids)
            ):
                _fail(
                    codec.ReasonCode.SEMANTIC_ERROR,
                    owning_stage="3C",
                    entity_id=f"operations[{idx}]",
                    expected="at least 2 unique existing source_task_ids and valid view for merge",
                    actual={"source_task_ids": src_tids, "view": view},
                    resume_ref=ci_path,
                    path=ci_path,
                )
            view_map = triplet["back_by_tid"] if view == "back" else triplet["gameplay_by_tid"]
            for stid in src_tids:
                if _is_story_like_id(stid) or type(stid) is not int or stid not in triplet["master"] or stid not in view_map:
                    _fail(
                        codec.ReasonCode.MAPPING_MISMATCH,
                        owning_stage="3C",
                        entity_id=str(stid),
                        expected=f"existing positive integer task_id in {view} view",
                        actual=stid,
                        resume_ref=ci_path,
                        path=ci_path,
                    )
                register_target(view, stid)
            req_ids, f_ids = check_id_lists(op, f"operations[{idx}]")
            if "from_task_ids" in op["lineage"]:
                from_ids = op["lineage"]["from_task_ids"]
                if type(from_ids) is not list or not set(src_tids) <= set(from_ids):
                    _fail(
                        codec.ReasonCode.SEMANTIC_ERROR,
                        owning_stage="3C",
                        entity_id=f"operations[{idx}]",
                        expected={"lineage.from_task_ids_superset": sorted(src_tids)},
                        actual=from_ids,
                        resume_ref=ci_path,
                        path=ci_path,
                    )
            target_tid = op.get("target_task_id")
            if target_tid is not None:
                if target_tid not in src_tids:
                    _fail(
                        codec.ReasonCode.CONFLICT,
                        owning_stage="3C",
                        entity_id=str(target_tid),
                        expected="merge target_task_id must be one of source_task_ids or null",
                        actual=target_tid,
                        resume_ref=ci_path,
                        path=ci_path,
                    )
                if "business_id" in op and op["business_id"] != view_map[target_tid]["id"]:
                    _fail(
                        codec.ReasonCode.CONFLICT,
                        owning_stage="3C",
                        entity_id=str(target_tid),
                        expected={"business_id": view_map[target_tid]["id"]},
                        actual={"business_id": op["business_id"]},
                        resume_ref=ci_path,
                        path=ci_path,
                    )
                if op.get("candidate_key") is not None:
                    _fail(
                        codec.ReasonCode.SEMANTIC_ERROR,
                        owning_stage="3C",
                        entity_id=str(target_tid),
                        expected="candidate_key=null when merge targets an existing target_task_id",
                        actual=op.get("candidate_key"),
                        resume_ref=ci_path,
                        path=ci_path,
                    )
                check_mature_protections(op, triplet["master"][target_tid], view_map[target_tid], view)
                for stid in src_tids:
                    if stid != target_tid:
                        check_mature_protections(
                            op,
                            triplet["master"][stid],
                            view_map[stid],
                            view,
                            check_identity_match=False,
                        )
            else:
                for stid in src_tids:
                    check_mature_protections(
                        op,
                        triplet["master"][stid],
                        view_map[stid],
                        view,
                        check_identity_match=False,
                        disallow_status=True,
                    )
                register_candidate(
                    view_name=view,
                    action_name="merge",
                    f_ids=f_ids,
                    req_ids=req_ids,
                    explicit_ckey=op.get("candidate_key"),
                    explicit_bid=(
                        op.get("proposed_business_id")
                        if op.get("proposed_business_id") is not None
                        else op.get("business_id")
                    ),
                    entity=f"operations[{idx}]",
                )
            if "roles" in op:
                check_roles(op["roles"], f"operations[{idx}].roles")
            if "part_kinds" in op:
                check_part_kinds(op["part_kinds"], f"operations[{idx}].part_kinds")

    # Check explicit proposed_manifest against baseline via protection._manifest_changes & _weakens_baseline.
    if manifest_info is not None:
        baseline_doc = manifest_info["document"]
        proposed_manifest = doc.get("proposed_manifest")
        if proposed_manifest is not None:
            if type(proposed_manifest) is not dict:
                _fail(
                    codec.ReasonCode.INVALID_TYPE,
                    owning_stage="3C",
                    entity_id=manifest_info["path"],
                    expected="proposed_manifest JSON object",
                    actual=type(proposed_manifest).__name__,
                    resume_ref=ci_path,
                    path=ci_path,
                )
            changes = protection._manifest_changes(
                [{"path": manifest_info["path"], "document": baseline_doc, "canonical_digest": manifest_info["canonical_digest"]}],
                [{"path": manifest_info["path"], "document": proposed_manifest, "canonical_digest": codec.canonical_digest(proposed_manifest)}],
            )
            for change in changes:
                if change["weakening_detected"]:
                    _fail(
                        codec.ReasonCode.SEMANTIC_ERROR,
                        owning_stage="3C",
                        entity_id=manifest_info["path"],
                        expected="cumulative MVG baseline non-weakening (no removed/weakened flows, tests, handoffs, or coverage)",
                        actual={
                            "removed_obligations": change["removed_obligations"],
                            "weakened_obligations": change["weakened_obligations"],
                            "manual_limits_changed": change["manual_limits_changed"],
                        },
                        resume_ref=manifest_info["path"],
                        path=manifest_info["path"],
                    )

    return {
        "path": ci_path,
        "document": doc,
        "operations": operations,
        "seen_candidate_keys": seen_candidate_keys,
        "seen_business_ids": seen_business_ids,
    }


def _aggregate_parts(plan: dict[str, Any], flows_by_id: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    by_kind: dict[str, dict[str, Any]] = {}
    flows = list(flows_by_id.values()) if flows_by_id is not None else list(plan["definitions"]["flows"])
    for flow in flows:
        for part in flow.get("parts", []):
            kind = part["kind"]
            entry = by_kind.setdefault(
                kind,
                {"kind": kind, "applicable": False, "rationales": [], "responsibilities": []},
            )
            if part["applicability"] == "applicable":
                entry["applicable"] = True
                for item in part.get("responsibilities", []):
                    if item not in entry["responsibilities"]:
                        entry["responsibilities"].append(item)
            if part.get("rationale") and part["rationale"] not in entry["rationales"]:
                entry["rationales"].append(part["rationale"])

    result: list[dict[str, Any]] = []
    for kind in PART_KINDS:
        entry = by_kind.get(kind)
        if entry is None:
            result.append(
                {
                    "kind": kind,
                    "applicability": "not_applicable",
                    "rationale": f"No committed Flow in plan {plan['plan_id']} declares applicable {kind} responsibilities.",
                    "responsibilities": [],
                }
            )
        elif entry["applicable"]:
            responsibilities = entry["responsibilities"] or [f"Deliver {kind} responsibilities for {plan['plan_id']}."]
            result.append(
                {
                    "kind": kind,
                    "applicability": "applicable",
                    "rationale": " | ".join(entry["rationales"]) or f"Applicable {kind} responsibilities.",
                    "responsibilities": responsibilities,
                }
            )
        else:
            result.append(
                {
                    "kind": kind,
                    "applicability": "not_applicable",
                    "rationale": " | ".join(entry["rationales"]) or f"Not applicable for plan {plan['plan_id']}.",
                    "responsibilities": [],
                }
            )
    return result


def _choose_view_for_flow(flow: dict[str, Any], parts: list[dict[str, Any]]) -> str:
    applicable_kinds = {p["kind"] for p in parts if p["applicability"] == "applicable"}
    if applicable_kinds & {"domain_rules", "csharp_adapter", "scene"}:
        return "gameplay"
    return "back"


def _normalize_create_proposal(
    *,
    plan_id: str,
    plan_ref: dict[str, Any],
    view: str,
    action: str,
    candidate_key: str,
    requirement_ids: list[str],
    flow_ids: list[str],
    part_kinds: list[str],
    roles: list[str],
    obligation_ids: list[str],
    req_by_id: dict[str, dict[str, Any]],
    ledger_blocks: dict[str, Any],
    proposed_business_id: str | None = None,
    title_override: str | None = None,
    split_index: int = 0,
    lineage: dict[str, Any] | None = None,
    scope: Any = None,
    source_diff_evidence: list[Any] | None = None,
    rationale: str | None = None,
) -> dict[str, Any]:
    anchors = []
    for rid in sorted(set(requirement_ids)):
        req = req_by_id.get(rid, {})
        block_ids = list(req.get("source_block_ids", []))
        first_block = ledger_blocks.get(block_ids[0], {}) if block_ids else {}
        anchors.append(
            {
                "requirement_id": rid,
                "source_path": str(first_block.get("source_path") or "docs/gdd/unknown.md"),
                "line": int(first_block.get("line_start") or 1),
                "kind": "functional" if view == "gameplay" else "non_functional",
                "priority": "P1" if flow_ids else "P2",
                "text": str(req.get("acceptance_intent") or rid),
                "refs": [],
                "source_block_ids": block_ids,
                "heading_path": list(first_block.get("heading_path", [])),
                "layer_hint": "core" if "domain_rules" in part_kinds else ("adapter" if "csharp_adapter" in part_kinds or "scene" in part_kinds else "ci"),
                "owner_hint": "gameplay" if view == "gameplay" else "architecture",
                "semantic": True,
            }
        )
    if anchors:
        topic, layer, owner = normalizer.choose_topic(anchors[0])
        phrase = normalizer.title_phrase(anchors, topic)
        title = title_override or normalizer.intent_title(topic, phrase, split_index)
        details = normalizer.intent_details(topic, layer, owner, phrase)
        test_strategy = normalizer.intent_test_strategy(topic, layer)
        priority = normalizer.priority_of(anchors)
        description = " ".join(str(anchors[0].get("text") or title).split())[:700]
        source_refs = [f"{a['source_path']}:{a['line']}" for a in anchors]
    else:
        topic, layer, owner = ("validation-gates", "ci", "architecture")
        title = title_override or f"Deliver {candidate_key}"
        details = normalizer.intent_details(topic, layer, owner, candidate_key)
        test_strategy = normalizer.intent_test_strategy(topic, layer)
        priority = "P2"
        description = title
        source_refs = []

    proposed_bid = proposed_business_id or _candidate_business_id(view, candidate_key)
    acceptance: list[str] = []
    for rid in sorted(set(requirement_ids)):
        req = req_by_id.get(rid, {})
        intent = " ".join(str(req.get("acceptance_intent") or f"Requirement {rid} is delivered and verified.").split())
        ref_tokens = [
            f"{ledger_blocks[bid]['source_path']}:{ledger_blocks[bid].get('line_start', 1)}"
            for bid in req.get("source_block_ids", [])
            if bid in ledger_blocks and ledger_blocks[bid].get("source_path")
        ]
        if not ref_tokens:
            ref_tokens = [plan_ref["path"]]
        refs_joined = ", ".join(dict.fromkeys(ref_tokens))
        acceptance.append(f"{rid}: {intent} (plan {plan_id}) Refs: {refs_joined}")
    if not acceptance:
        acceptance.append(f"Deliver {candidate_key} under plan {plan_id}. Refs: {plan_ref['path']}")

    delta: dict[str, Any] = {
        "action": action,
        "task_id": None,
        "candidate_key": candidate_key,
        "proposed_business_id": proposed_bid,
        "view": view,
        "topic": topic,
        "plan_ref": copy.deepcopy(plan_ref),
        "semantic_review_tier": "targeted",
        "title": title,
        "description": description,
        "details": details,
        "priority": priority,
        "layer": layer,
        "owner": owner,
        "requirement_ids": sorted(set(requirement_ids)),
        "semantic_refs": sorted(set(requirement_ids)),
        "flow_ids": sorted(set(flow_ids)),
        "part_kinds": sorted(set(part_kinds)),
        "roles": sorted(set(roles)),
        "obligation_ids": sorted(set(obligation_ids)),
        "source_refs": source_refs,
        "acceptance": acceptance,
        "test_strategy": test_strategy,
        "labels": sorted({"b-route", "3c-preview", view, layer, *roles}),
        "old_done_satisfies_new_obligations": False,
        "permanent_id_allocated": False,
    }
    if lineage is not None:
        delta["lineage"] = copy.deepcopy(lineage)
    if scope is not None:
        delta["scope"] = copy.deepcopy(scope)
    if source_diff_evidence is not None:
        delta["source_diff_evidence"] = copy.deepcopy(source_diff_evidence)
    if rationale is not None:
        delta["rationale"] = rationale
    return delta


def _build_binding_and_origins_preview(
    *,
    plan: dict[str, Any],
    plan_ref: dict[str, Any],
    origins: dict[str, Any],
    existing_binding: dict[str, Any] | None,
    manifest_info: dict[str, Any] | None,
    all_deltas: list[dict[str, Any]],
    removed_existing_tids: set[int],
    obligations: list[dict[str, Any]],
    other_verification_refs: list[dict[str, Any]],
    parts: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    plan_id = plan["plan_id"]
    binding_revision = (existing_binding["binding_revision"] + 1) if existing_binding else 1

    # Aggregate task_mappings by existing task_id OR candidate_key (preserving M:N and dual views).
    existing_map: dict[int, dict[str, Any]] = {}
    candidate_map: dict[str, dict[str, Any]] = {}
    for delta in all_deltas:
        if delta["action"] == "retire":
            continue
        tid = delta["task_id"]
        view = delta["view"]
        bid = delta.get("business_id") or delta.get("proposed_business_id")
        if tid is not None:
            row = existing_map.setdefault(
                tid,
                {
                    "task_id": tid,
                    "view_refs": [],
                    "requirement_ids": set(),
                    "flow_ids": set(),
                    "part_kinds": set(),
                    "roles": set(),
                    "obligation_ids": set(),
                },
            )
        else:
            ckey = delta["candidate_key"]
            row = candidate_map.setdefault(
                ckey,
                {
                    "task_id": None,
                    "candidate_key": ckey,
                    "view_refs": [],
                    "requirement_ids": set(),
                    "flow_ids": set(),
                    "part_kinds": set(),
                    "roles": set(),
                    "obligation_ids": set(),
                },
            )
        vref = {"view": view, "business_id": bid}
        if vref not in row["view_refs"]:
            row["view_refs"].append(vref)
        row["requirement_ids"].update(delta.get("requirement_ids", []))
        row["flow_ids"].update(delta.get("flow_ids", []))
        row["part_kinds"].update(delta.get("part_kinds", []))
        row["roles"].update(delta.get("roles", []))
        row["obligation_ids"].update(delta.get("obligation_ids", []))

    applicable_part_set = {p["kind"] for p in parts if p["applicability"] == "applicable"}
    task_mappings: list[dict[str, Any]] = []
    for tid in sorted(existing_map):
        row = existing_map[tid]
        task_mappings.append(
            {
                "task_id": tid,
                "view_refs": sorted(row["view_refs"], key=lambda x: (x["view"], x["business_id"])),
                "requirement_ids": sorted(row["requirement_ids"]),
                "flow_ids": sorted(row["flow_ids"]),
                "part_kinds": sorted(row["part_kinds"] & applicable_part_set),
                "roles": sorted(row["roles"]),
                "obligation_ids": sorted(row["obligation_ids"]),
            }
        )
    for ckey in sorted(candidate_map):
        row = candidate_map[ckey]
        task_mappings.append(
            {
                "task_id": None,
                "candidate_key": ckey,
                "view_refs": sorted(row["view_refs"], key=lambda x: (x["view"], x["business_id"])),
                "requirement_ids": sorted(row["requirement_ids"]),
                "flow_ids": sorted(row["flow_ids"]),
                "part_kinds": sorted(row["part_kinds"] & applicable_part_set),
                "roles": sorted(row["roles"]),
                "obligation_ids": sorted(row["obligation_ids"]),
            }
        )

    # Build implementation_objects strictly from declared plan commands/states or existing binding.
    # NEVER fabricate runtime/business APIs for integration_only_owner roles, and exclude unmapped/retired task_ids!
    existing_impl_by_id = {
        row["id"]: copy.deepcopy(row)
        for row in (existing_binding.get("implementation_objects", []) if existing_binding else [])
    }
    mapped_existing_tids = set(existing_map)
    req_to_existing_tids: dict[str, set[int]] = {}
    req_to_candidate_keys: dict[str, set[str]] = {}
    for m in task_mappings:
        # Skip pure integration_only_owner tasks when attributing runtime commands/states.
        if set(m["roles"]) == {"integration_only_owner"}:
            continue
        for rid in m["requirement_ids"]:
            if m["task_id"] is not None:
                req_to_existing_tids.setdefault(rid, set()).add(m["task_id"])
            else:
                req_to_candidate_keys.setdefault(rid, set()).add(m["candidate_key"])

    impl_objects: list[dict[str, Any]] = []
    seen_impl_ids: set[str] = set()
    for def_kind, plural, obj_kind in (
        ("command", "commands", "command"),
        ("state", "states", "read_only_state"),
    ):
        for item in plan["definitions"].get(plural, []):
            obj_id = f"{def_kind}:{item['id']}"
            seen_impl_ids.add(obj_id)
            resp_tids: set[int] = set()
            resp_ckeys: set[str] = set()
            for rid in item.get("requirement_ids", []):
                resp_tids.update(req_to_existing_tids.get(rid, set()))
                resp_ckeys.update(req_to_candidate_keys.get(rid, set()))
            if obj_id in existing_impl_by_id:
                existing_obj = copy.deepcopy(existing_impl_by_id[obj_id])
                kept_tids = {
                    tid for tid in existing_obj.get("responsible_task_ids", [])
                    if tid in mapped_existing_tids
                }
                merged_tids = sorted(kept_tids | resp_tids)
                if not merged_tids and not resp_ckeys:
                    continue
                existing_obj["responsible_task_ids"] = merged_tids
                if resp_ckeys:
                    existing_obj["responsible_candidate_keys"] = sorted(resp_ckeys)
                else:
                    existing_obj.pop("responsible_candidate_keys", None)
                impl_objects.append(existing_obj)
                continue
            if not resp_tids and not resp_ckeys:
                # Only integration_only_owner or deferred: do not fabricate runtime API ownership.
                continue
            entry: dict[str, Any] = {
                "id": obj_id,
                "kind": obj_kind,
                "availability": "planned",
                "responsible_task_ids": sorted(resp_tids),
                "expected_type": f"planned:{obj_kind}:{item['id']}",
                "lifecycle": "planned_for_chapter4_refinement",
                "target_ref": None,
                "later_checks": ["type", "compile", "binding"],
            }
            if resp_ckeys:
                entry["responsible_candidate_keys"] = sorted(resp_ckeys)
            impl_objects.append(entry)

    # Retain any existing binding implementation_objects whose responsible tasks remain mapped.
    for obj_id, obj in sorted(existing_impl_by_id.items()):
        if obj_id in seen_impl_ids:
            continue
        kept_tids = sorted(tid for tid in obj.get("responsible_task_ids", []) if tid in mapped_existing_tids)
        if kept_tids:
            retained_obj = copy.deepcopy(obj)
            retained_obj["responsible_task_ids"] = kept_tids
            impl_objects.append(retained_obj)

    manifest_refs: list[dict[str, Any]] = []
    if existing_binding:
        manifest_refs.extend(existing_binding.get("manifest_refs", []))
    if manifest_info is not None:
        manifest_refs.append(manifest_info["owned_ref"])
    manifest_refs = _dedupe_owned_refs(manifest_refs)

    all_other_refs = list(other_verification_refs)
    if existing_binding:
        all_other_refs.extend(existing_binding.get("other_verification_refs", []))
    all_other_refs = _dedupe_owned_refs(all_other_refs)

    binding_preview: dict[str, Any] = {
        "schema_version": "newrouge.b-route-binding.v1",
        "plan_id": plan_id,
        "binding_revision": binding_revision,
        "plan_ref": copy.deepcopy(plan_ref),
        "stage": "3C",
        "task_mappings": task_mappings,
        "parts": parts,
        "implementation_objects": impl_objects,
        "obligations": obligations,
        "manifest_refs": manifest_refs,
        "other_verification_refs": all_other_refs,
    }

    # Verify structural isomorphism against newrouge.b-route-binding.v1 using a throwaway copy.
    # For existing-ID-only previews, validate binding_preview directly without substitution!
    binding_path = f"{records.BASE}bindings/{plan_id}/{binding_revision}.json"
    has_pending_candidates = any(m["task_id"] is None for m in task_mappings)
    if not has_pending_candidates:
        validation = records.validate_record(binding_preview, path=binding_path)
    else:
        scratch = copy.deepcopy(binding_preview)
        next_temp_id = max([m["task_id"] for m in task_mappings if m["task_id"] is not None] or [0]) + 100000
        ckey_to_temp: dict[str, int] = {}
        for m in scratch["task_mappings"]:
            if m["task_id"] is None:
                ckey = m.pop("candidate_key")
                ckey_to_temp[ckey] = next_temp_id
                m["task_id"] = next_temp_id
                next_temp_id += 1
        for obj in scratch["implementation_objects"]:
            ckeys = obj.pop("responsible_candidate_keys", [])
            for ck in ckeys:
                if ck in ckey_to_temp and ckey_to_temp[ck] not in obj["responsible_task_ids"]:
                    obj["responsible_task_ids"].append(ckey_to_temp[ck])
            obj["responsible_task_ids"] = sorted(set(obj["responsible_task_ids"]))
        validation = records.validate_record(scratch, path=binding_path)

    schema_compat = {
        "binding_schema": "newrouge.b-route-binding.v1",
        "origins_schema": "newrouge.b-route-origins.v1",
        "binding_isomorphic_valid": validation.ok,
        "has_pending_candidate_keys": has_pending_candidates,
        "binding_validation_diagnostic": None if validation.ok else validation.diagnostic.to_dict(),
    }
    if not validation.ok:
        _fail(
            validation.diagnostic.reason_code,
            owning_stage="3C",
            stage=validation.diagnostic.stage or codec.Stage.SCHEMA,
            entity_id=plan_id,
            expected="binding_preview isomorphic to newrouge.b-route-binding.v1",
            actual=validation.diagnostic.to_dict(),
            resume_ref=plan_ref["path"],
            path=binding_path,
        )

    # Build origins_preview isomorphic to newrouge.b-route-origins.v1.
    preview_binding_ref = {
        "path": binding_path,
        "schema_version": "newrouge.b-route-binding.v1",
        "entity_id": plan_id,
        "revision": binding_revision,
        "digest": codec.canonical_digest(binding_preview),
        "verification_mode": "canonical",
        "codec_version": codec.CODEC_VERSION,
    }
    source_refs = _dedupe_owned_refs(
        [plan["source_identity"]["manifest_ref"], plan["source_identity"]["ledger_ref"]]
    )
    origins_by_tid: dict[int, dict[str, Any]] = {
        row["task_id"]: copy.deepcopy(row) for row in origins.get("tasks", [])
    }

    # Remove current plan's plan_ref/binding_ref from retired, split-away, or merge-absorbed tasks
    # that are no longer mapped in this plan; preserve other plans' refs if shared.
    for tid in sorted(removed_existing_tids - mapped_existing_tids):
        existing_row = origins_by_tid.get(tid)
        if existing_row is None:
            continue
        remaining_plans = [
            p for p in existing_row.get("plan_refs", [])
            if p.get("entity_id") != plan_id and p.get("path") != plan_ref["path"]
        ]
        remaining_bindings = [
            b for b in existing_row.get("binding_refs", [])
            if b.get("entity_id") != plan_id
        ]
        if not remaining_plans:
            del origins_by_tid[tid]
        else:
            existing_row["plan_refs"] = remaining_plans
            existing_row["binding_refs"] = remaining_bindings

    for tid in sorted(existing_map):
        existing_row = origins_by_tid.get(tid)
        if existing_row is None:
            origins_by_tid[tid] = {
                "task_id": tid,
                "source_refs": copy.deepcopy(source_refs),
                "plan_refs": [copy.deepcopy(plan_ref)],
                "binding_refs": [copy.deepcopy(preview_binding_ref)],
            }
        else:
            existing_row["source_refs"] = _dedupe_owned_refs(existing_row["source_refs"] + source_refs)
            existing_row["plan_refs"] = [
                p for p in existing_row["plan_refs"] if p.get("entity_id") != plan_id
            ] + [copy.deepcopy(plan_ref)]
            existing_row["binding_refs"] = [
                b for b in existing_row["binding_refs"] if b.get("entity_id") != plan_id
            ] + [copy.deepcopy(preview_binding_ref)]

    origin_tasks: list[dict[str, Any]] = [origins_by_tid[tid] for tid in sorted(origins_by_tid)]
    for ckey in sorted(candidate_map):
        origin_tasks.append(
            {
                "task_id": None,
                "candidate_key": ckey,
                "source_refs": copy.deepcopy(source_refs),
                "plan_refs": [copy.deepcopy(plan_ref)],
                "binding_refs": [copy.deepcopy(preview_binding_ref)],
            }
        )

    origins_preview: dict[str, Any] = {
        "schema_version": "newrouge.b-route-origins.v1",
        "origins_id": "task-origins",
        "revision": int(origins["revision"]) + 1,
        "tasks": origin_tasks,
        "frozen_legacy_refs": copy.deepcopy(origins.get("frozen_legacy_refs", [])),
    }
    origins_path = records.BASE + "task-origins.v1.json"
    if not has_pending_candidates:
        origins_check = records.validate_record(origins_preview, path=origins_path)
    else:
        scratch_origins = copy.deepcopy(origins_preview)
        next_tid = max([row["task_id"] for row in origin_tasks if row["task_id"] is not None] or [0]) + 100000
        for row in scratch_origins["tasks"]:
            if row["task_id"] is None:
                row.pop("candidate_key", None)
                row["task_id"] = next_tid
                next_tid += 1
        origins_check = records.validate_record(scratch_origins, path=origins_path)
    schema_compat["origins_isomorphic_valid"] = origins_check.ok
    schema_compat["origins_validation_diagnostic"] = (
        None if origins_check.ok else origins_check.diagnostic.to_dict()
    )
    if not origins_check.ok:
        _fail(
            origins_check.diagnostic.reason_code,
            owning_stage="3C",
            stage=origins_check.diagnostic.stage or codec.Stage.SCHEMA,
            entity_id=plan_id,
            expected="origins_preview isomorphic to newrouge.b-route-origins.v1",
            actual=origins_check.diagnostic.to_dict(),
            resume_ref=plan_ref["path"],
            path=origins_path,
        )

    return binding_preview, origins_preview, schema_compat


def _infer_roles(
    *,
    flow_ids: set[str] | list[str],
    requirement_ids: set[str] | list[str],
    part_kinds: set[str] | list[str],
    ver_by_id: dict[str, dict[str, Any]],
    impl_def_req_ids: set[str],
) -> list[str]:
    """Classify as integration_only_owner ONLY when a task has no implementation responsibilities."""
    has_impl_parts = bool(set(part_kinds) & set(PART_KINDS))
    has_flows = bool(flow_ids)
    has_flow_reqs = any(
        ver_by_id.get(rid, {}).get("disposition") == "flow" for rid in requirement_ids
    )
    has_impl_defs = bool(set(requirement_ids) & impl_def_req_ids)
    if has_impl_parts or has_flows or has_flow_reqs or has_impl_defs:
        return ["producer"]
    return ["integration_only_owner"]


def _check_mvg_baseline_non_weakening(
    *,
    manifest_info: dict[str, Any] | None,
    change_intents: dict[str, Any] | None,
    plan_req_ids: set[str],
    flow_obligation_id: dict[str, str],
    explicit_and_reused_deltas: list[dict[str, Any]],
    retired_tids: set[int],
    split_source_tids: set[int],
    absorbed_merge_source_tids: set[int],
    updated_ops_by_tid: dict[int, dict[str, Any]],
) -> None:
    if manifest_info is None or change_intents is None:
        return
    baseline_doc = manifest_info["document"]
    active_deltas = [d for d in explicit_and_reused_deltas if d["action"] != "retire"]

    for flow in baseline_doc.get("flows", []):
        if not isinstance(flow, dict):
            continue
        bfid = flow.get("id")
        if not isinstance(bfid, str) or not bfid:
            continue
        flow_tids = {
            int(t)
            for t in flow.get("task_ids", [])
            if isinstance(t, int) or (isinstance(t, str) and t.isdigit())
        }
        bflow_reqs = {r for r in flow.get("requirement_ids", []) if isinstance(r, str)}
        required_plan_reqs = bflow_reqs & plan_req_ids

        covering_deltas = [d for d in active_deltas if bfid in d.get("flow_ids", [])]
        covered_bfid_reqs: set[str] = set()
        covered_bfid_obls: set[str] = set()
        for d in covering_deltas:
            covered_bfid_reqs.update(d.get("requirement_ids", []))
            covered_bfid_obls.update(d.get("obligation_ids", []))
        expected_obl = flow_obligation_id.get(bfid)
        replacement_intact = (
            bool(covering_deltas)
            and (expected_obl is None or expected_obl in covered_bfid_obls)
            and (required_plan_reqs <= covered_bfid_reqs)
        )

        dropped_retired = sorted(flow_tids & retired_tids)
        if dropped_retired and not replacement_intact:
            _fail(
                codec.ReasonCode.SEMANTIC_ERROR,
                owning_stage="3C",
                entity_id=bfid,
                expected="retire must not weaken or orphan cumulative MVG baseline flow task_ids without replacement",
                actual={"flow_id": bfid, "retired_task_ids": dropped_retired},
                resume_ref=manifest_info["path"],
                path=manifest_info["path"],
            )

        dropped_split = sorted(flow_tids & split_source_tids)
        if dropped_split and not replacement_intact:
            _fail(
                codec.ReasonCode.SEMANTIC_ERROR,
                owning_stage="3C",
                entity_id=bfid,
                expected="split must preserve cumulative MVG baseline flow/obligations across resulting active mappings",
                actual={"flow_id": bfid, "split_source_task_ids": dropped_split},
                resume_ref=manifest_info["path"],
                path=manifest_info["path"],
            )

        dropped_merged = sorted(flow_tids & absorbed_merge_source_tids)
        if dropped_merged and not replacement_intact:
            _fail(
                codec.ReasonCode.SEMANTIC_ERROR,
                owning_stage="3C",
                entity_id=bfid,
                expected="merge absorbing baseline task_ids must preserve cumulative MVG baseline flow/obligations",
                actual={"flow_id": bfid, "absorbed_merge_source_task_ids": dropped_merged},
                resume_ref=manifest_info["path"],
                path=manifest_info["path"],
            )

        for utid in sorted(flow_tids & set(updated_ops_by_tid)):
            uop = updated_ops_by_tid[utid]
            dropped_flow = "flow_ids" in uop and bfid not in uop["flow_ids"]
            dropped_reqs = "requirement_ids" in uop and bool(required_plan_reqs - set(uop["requirement_ids"]))
            dropped_obl = (
                "obligation_ids" in uop
                and expected_obl is not None
                and expected_obl not in uop["obligation_ids"]
            )
            if (dropped_flow or dropped_reqs or dropped_obl) and not replacement_intact:
                _fail(
                    codec.ReasonCode.SEMANTIC_ERROR,
                    owning_stage="3C",
                    entity_id=bfid,
                    expected="update must not drop cumulative MVG baseline flow_ids/obligations without replacement",
                    actual={
                        "flow_id": bfid,
                        "updated_task_id": utid,
                        "dropped_flow": dropped_flow,
                        "dropped_reqs": dropped_reqs,
                        "dropped_obl": dropped_obl,
                    },
                    resume_ref=manifest_info["path"],
                    path=manifest_info["path"],
                )


def _inventory_and_plan_deltas(
    *,
    plan: dict[str, Any],
    plan_ref: dict[str, Any],
    flows_by_id: dict[str, dict[str, Any]],
    dispositions: dict[str, Any],
    triplet: dict[str, Any],
    existing_binding: dict[str, Any] | None,
    manifest_info: dict[str, Any] | None,
    change_intents: dict[str, Any] | None,
    ledger_blocks: dict[str, Any],
) -> dict[str, Any]:
    plan_id = plan["plan_id"]
    req_by_id = dispositions["requirements"]
    ver_by_id = dispositions["verifications"]
    app_by_id = dispositions["applicability"]
    evidence_refs_by_locator = {
        (row["owner"], row["ref"]): row for row in plan.get("evidence_source_refs", [])
    }
    impl_def_req_ids: set[str] = set()
    for plural in ("commands", "states"):
        for item in plan["definitions"].get(plural, []):
            impl_def_req_ids.update(item.get("requirement_ids", []))

    # 1. Build obligations from Flows (local + external shared) and other_verification (never fake Flows!).
    obligations: list[dict[str, Any]] = []
    flow_obligation_id: dict[str, str] = {}
    flow_plan_reqs_map: dict[str, list[str]] = {}
    other_ver_obligation_id: dict[str, str] = {}
    other_verification_refs: list[dict[str, Any]] = []
    deferred_items: list[dict[str, Any]] = []
    non_task_sinks_inventory: list[dict[str, Any]] = []

    for rid in sorted(req_by_id):
        req = req_by_id[rid]
        if req.get("non_task_sinks"):
            non_task_sinks_inventory.append(
                {
                    "requirement_id": rid,
                    "non_task_sinks": list(req["non_task_sinks"]),
                    "disposition": ver_by_id[rid]["disposition"],
                }
            )

    for fid in sorted(flows_by_id):
        flow = flows_by_id[fid]
        flow_reqs = sorted(set(flow["requirement_ids"]) & set(req_by_id))
        flow_plan_reqs_map[fid] = flow_reqs
        obl_id = f"obl:flow:{fid}"
        flow_obligation_id[fid] = obl_id
        # Collect evidence OwnedRefs tied to this flow.
        ver_refs = []
        for ev in plan.get("requirement_evidence", []):
            if fid in ev.get("flow_ids", []):
                owners = ("implementation_reference", "contract") if ev["kind"] == "implementation_reference" else (ev["kind"],)
                for owner in owners:
                    if (owner, ev["source_ref"]) in evidence_refs_by_locator:
                        ver_refs.append(evidence_refs_by_locator[(owner, ev["source_ref"])])
        obligations.append(
            {
                "id": obl_id,
                "requirement_ids": flow_reqs,
                "flow_ids": [fid],
                "test_ids": sorted(set(flow.get("verification_targets", []))),
                "responsibility": flow["observable_result"],
                "verification_refs": _dedupe_owned_refs(ver_refs),
            }
        )

    other_verification_items: list[dict[str, Any]] = []
    for rid in sorted(ver_by_id):
        vrow = ver_by_id[rid]
        disp = vrow["disposition"]
        if disp == "other_verification":
            obl_id = f"obl:other:{rid}"
            other_ver_obligation_id[rid] = obl_id
            refs = list(app_by_id.get(rid, {}).get("other_verification_refs", []))
            if vrow.get("verification_ref") and ("other_verification", vrow["verification_ref"]) in evidence_refs_by_locator:
                refs.append(evidence_refs_by_locator[("other_verification", vrow["verification_ref"])])
            deduped = _dedupe_owned_refs(refs)
            other_verification_refs.extend(deduped)
            obligations.append(
                {
                    "id": obl_id,
                    "requirement_ids": [rid],
                    "flow_ids": [],
                    "test_ids": [],
                    "responsibility": vrow["rationale"],
                    "verification_refs": deduped,
                }
            )
            other_verification_items.append(
                {
                    "requirement_id": rid,
                    "sink_id": vrow["sink_id"],
                    "verification_ref": vrow["verification_ref"],
                    "rationale": vrow["rationale"],
                    "obligation_id": obl_id,
                    "fabricated_flow": False,
                    "other_verification_refs": deduped,
                }
            )
        elif disp == "deferred":
            deferred_items.append(
                {
                    "requirement_id": rid,
                    "authority_ref": vrow["authority_ref"],
                    "rationale": vrow["rationale"],
                    "executing": False,
                    "satisfied": False,
                    "fabricated_flow": False,
                }
            )

    other_verification_refs = _dedupe_owned_refs(other_verification_refs)

    # 2. Index existing coverage from committed binding & Taskmaster views.
    existing_binding_by_tid: dict[int, dict[str, Any]] = {}
    if existing_binding:
        for m in existing_binding.get("task_mappings", []):
            existing_binding_by_tid[m["task_id"]] = m

    # Build a map of what each existing Task historically covers.
    existing_task_coverage: dict[tuple[str, int], dict[str, Any]] = {}
    for view_name, view_map in (("back", triplet["back_by_tid"]), ("gameplay", triplet["gameplay_by_tid"])):
        for tid, vrow in sorted(view_map.items()):
            bm = existing_binding_by_tid.get(tid)
            task_status = triplet["master"][tid].get("status")
            cov_reqs = set(vrow.get("requirement_ids", [])) | set(vrow.get("semantic_refs", []))
            cov_flows: set[str] = set()
            cov_parts: set[str] = set()
            cov_roles: set[str] = set()
            cov_obls: set[str] = set()
            has_binding = bm is not None and any(
                vr["view"] == view_name and vr["business_id"] == vrow["id"] for vr in bm["view_refs"]
            )
            explicit_part_kinds = False
            if has_binding:
                cov_reqs.update(bm.get("requirement_ids", []))
                cov_flows.update(bm.get("flow_ids", []))
                cov_parts.update(bm.get("part_kinds", []))
                cov_roles.update(bm.get("roles", []))
                cov_obls.update(bm.get("obligation_ids", []))
                explicit_part_kinds = True
            else:
                if isinstance(vrow.get("part_kinds"), list):
                    cov_parts.update(pk for pk in vrow["part_kinds"] if pk in PART_KINDS)
                    explicit_part_kinds = True
                # Without a committed binding, NEVER allow flow_ids alone to satisfy newly introduced
                # Requirements or parts of a Flow; require all plan Requirements (and declared parts).
                for fid, flow in flows_by_id.items():
                    f_reqs = set(flow_plan_reqs_map[fid])
                    f_app_parts = {p["kind"] for p in flow["parts"] if p["applicability"] == "applicable"}
                    reqs_covered = bool(f_reqs) and f_reqs <= cov_reqs
                    parts_covered = (not explicit_part_kinds) or (f_app_parts <= cov_parts)
                    if reqs_covered and parts_covered:
                        cov_flows.add(fid)
                        cov_obls.add(flow_obligation_id[fid])
                        if not explicit_part_kinds:
                            cov_parts.update(f_app_parts)
                    elif fid in vrow.get("flow_ids", []) and task_status != "done" and reqs_covered:
                        cov_flows.add(fid)
                for rid, obl_id in other_ver_obligation_id.items():
                    if rid in cov_reqs:
                        cov_obls.add(obl_id)
                cov_roles.update(
                    _infer_roles(
                        flow_ids=cov_flows,
                        requirement_ids=cov_reqs,
                        part_kinds=cov_parts,
                        ver_by_id=ver_by_id,
                        impl_def_req_ids=impl_def_req_ids,
                    )
                )
            existing_task_coverage[(view_name, tid)] = {
                "task_id": tid,
                "business_id": vrow["id"],
                "view": view_name,
                "status": task_status,
                "has_binding": has_binding,
                "explicit_part_kinds": explicit_part_kinds,
                "requirement_ids": cov_reqs,
                "flow_ids": cov_flows,
                "part_kinds": cov_parts,
                "roles": cov_roles,
                "obligation_ids": cov_obls,
            }

    # 3. Apply explicit --change-intents first (if provided), tracking covered flows/reqs/obls/parts.
    deltas_back: list[dict[str, Any]] = []
    deltas_gameplay: list[dict[str, Any]] = []
    covered_reqs: set[str] = set()
    covered_flows: set[str] = set()
    covered_obls: set[str] = set()
    covered_parts_by_flow: dict[str, set[str]] = {}
    handled_existing_tasks: set[tuple[str, int]] = set()
    retired_existing_tasks: set[int] = set()
    split_source_tasks: set[int] = set()
    absorbed_merge_source_tasks: set[int] = set()
    updated_ops_by_tid: dict[int, dict[str, Any]] = {}

    used_candidate_keys: set[str] = set(change_intents["seen_candidate_keys"]) if change_intents else set()
    used_business_ids: set[str] = (
        set(change_intents["seen_business_ids"])
        if change_intents
        else (set(triplet["back_by_bid"]) | set(triplet["gameplay_by_bid"]))
    )

    def append_delta(delta: dict[str, Any]) -> None:
        if delta["view"] == "gameplay":
            deltas_gameplay.append(delta)
        else:
            deltas_back.append(delta)

    if change_intents is not None:
        for op in change_intents["operations"]:
            action = op["action"]
            if action == "reuse":
                tid = op["task_id"]
                view = op["view"]
                cov = existing_task_coverage[(view, tid)]
                req_ids = sorted(set(op.get("requirement_ids", cov["requirement_ids"])) & set(req_by_id))
                f_ids = sorted(set(op.get("flow_ids", cov["flow_ids"])) & set(flows_by_id))
                # Old done task cannot claim reuse for a requirement/flow it did not historically cover!
                uncovered_new_reqs = sorted(set(req_ids) - cov["requirement_ids"])
                uncovered_new_flows = sorted(set(f_ids) - cov["flow_ids"])
                if uncovered_new_reqs or uncovered_new_flows:
                    _fail(
                        codec.ReasonCode.SEMANTIC_ERROR,
                        owning_stage="3C",
                        entity_id=str(tid),
                        expected="reuse cannot claim old Task covers newly added Requirements/Flows (old done never satisfies new obligations)",
                        actual={
                            "task_status": cov["status"],
                            "uncovered_new_requirements": uncovered_new_reqs,
                            "uncovered_new_flows": uncovered_new_flows,
                        },
                        resume_ref=change_intents["path"],
                        path=change_intents["path"],
                    )
                obl_ids = sorted(
                    set(op.get("obligation_ids", []))
                    | {flow_obligation_id[fid] for fid in f_ids}
                    | {other_ver_obligation_id[rid] for rid in req_ids if rid in other_ver_obligation_id}
                )
                part_kinds = sorted(
                    set(op.get("part_kinds", cov["part_kinds"]))
                    | (
                        set()
                        if cov["explicit_part_kinds"]
                        else {
                            p["kind"]
                            for fid in f_ids
                            for p in flows_by_id[fid]["parts"]
                            if p["applicability"] == "applicable"
                        }
                    )
                )
                roles = sorted(set(op.get("roles", cov["roles"])))
                handled_existing_tasks.add((view, tid))
                covered_reqs.update(req_ids)
                covered_flows.update(f_ids)
                covered_obls.update(obl_ids)
                for fid in f_ids:
                    covered_parts_by_flow.setdefault(fid, set()).update(part_kinds)
                append_delta(
                    {
                        "action": "reuse",
                        "task_id": tid,
                        "candidate_key": None,
                        "business_id": cov["business_id"],
                        "view": view,
                        "plan_ref": copy.deepcopy(plan_ref),
                        "status": cov["status"],
                        "preserved_fields": ["taskmaster_id", "business_id", "status", "history"],
                        "definition_digest": codec.canonical_digest(
                            protection.task_definition_projection(
                                triplet["back_by_tid"][tid] if view == "back" else triplet["gameplay_by_tid"][tid]
                            )
                        ),
                        "requirement_ids": req_ids,
                        "flow_ids": f_ids,
                        "part_kinds": part_kinds,
                        "roles": roles,
                        "obligation_ids": obl_ids,
                        "old_done_satisfies_new_obligations": False,
                    }
                )
            elif action == "update":
                tid = op["task_id"]
                view = op["view"]
                cov = existing_task_coverage[(view, tid)]
                updated_ops_by_tid[tid] = op
                if "requirement_ids" in op:
                    req_ids = sorted(set(op["requirement_ids"]))
                else:
                    req_ids = sorted(cov["requirement_ids"] & set(req_by_id))
                if "flow_ids" in op:
                    f_ids = sorted(set(op["flow_ids"]))
                else:
                    f_ids = sorted(cov["flow_ids"] & set(flows_by_id))
                if "obligation_ids" in op:
                    obl_ids = sorted(set(op["obligation_ids"]))
                else:
                    obl_ids = sorted(
                        {flow_obligation_id[fid] for fid in f_ids}
                        | {other_ver_obligation_id[rid] for rid in req_ids if rid in other_ver_obligation_id}
                    )
                part_kinds = sorted(
                    set(op.get("part_kinds", cov["part_kinds"]))
                    | {
                        p["kind"]
                        for fid in f_ids
                        for p in flows_by_id[fid]["parts"]
                        if p["applicability"] == "applicable"
                    }
                )
                roles = (
                    sorted(set(op["roles"]))
                    if "roles" in op
                    else _infer_roles(
                        flow_ids=f_ids,
                        requirement_ids=req_ids,
                        part_kinds=part_kinds,
                        ver_by_id=ver_by_id,
                        impl_def_req_ids=impl_def_req_ids,
                    )
                )
                handled_existing_tasks.add((view, tid))
                covered_reqs.update(req_ids)
                covered_flows.update(f_ids)
                covered_obls.update(obl_ids)
                for fid in f_ids:
                    covered_parts_by_flow.setdefault(fid, set()).update(part_kinds)
                append_delta(
                    {
                        "action": "update",
                        "task_id": tid,
                        "candidate_key": None,
                        "business_id": cov["business_id"],
                        "view": view,
                        "plan_ref": copy.deepcopy(plan_ref),
                        "status": cov["status"],
                        "preserved_fields": ["taskmaster_id", "business_id", "status", "history"],
                        "requirement_ids": req_ids,
                        "flow_ids": f_ids,
                        "part_kinds": part_kinds,
                        "roles": roles,
                        "obligation_ids": obl_ids,
                        "scope": copy.deepcopy(op["scope"]),
                        "source_diff_evidence": copy.deepcopy(op["source_diff_evidence"]),
                        "lineage": copy.deepcopy(op["lineage"]),
                        "rationale": op["rationale"],
                        "proposed_fields": copy.deepcopy(op.get("proposed_fields", {})),
                        "old_done_satisfies_new_obligations": False,
                        "requires_new_verification": True,
                    }
                )
            elif action == "create":
                view = op["view"]
                req_ids = sorted(set(op.get("requirement_ids", [])))
                f_ids = sorted(set(op.get("flow_ids", [])))
                ckey = op.get("candidate_key") or _candidate_key(plan_id, view, "create", f_ids, req_ids)
                proposed_bid = (
                    op.get("proposed_business_id")
                    if op.get("proposed_business_id") is not None
                    else op.get("business_id")
                )
                obl_ids = sorted(
                    set(op.get("obligation_ids", []))
                    | {flow_obligation_id[fid] for fid in f_ids}
                    | {other_ver_obligation_id[rid] for rid in req_ids if rid in other_ver_obligation_id}
                )
                part_kinds = sorted(
                    set(op.get("part_kinds", []))
                    | {
                        p["kind"]
                        for fid in f_ids
                        for p in flows_by_id[fid]["parts"]
                        if p["applicability"] == "applicable"
                    }
                )
                roles = (
                    sorted(set(op["roles"]))
                    if "roles" in op
                    else _infer_roles(
                        flow_ids=f_ids,
                        requirement_ids=req_ids,
                        part_kinds=part_kinds,
                        ver_by_id=ver_by_id,
                        impl_def_req_ids=impl_def_req_ids,
                    )
                )
                covered_reqs.update(req_ids)
                covered_flows.update(f_ids)
                covered_obls.update(obl_ids)
                for fid in f_ids:
                    covered_parts_by_flow.setdefault(fid, set()).update(part_kinds)
                append_delta(
                    _normalize_create_proposal(
                        plan_id=plan_id,
                        plan_ref=plan_ref,
                        view=view,
                        action="create",
                        candidate_key=ckey,
                        proposed_business_id=proposed_bid,
                        requirement_ids=req_ids,
                        flow_ids=f_ids,
                        part_kinds=part_kinds,
                        roles=roles,
                        obligation_ids=obl_ids,
                        req_by_id=req_by_id,
                        ledger_blocks=ledger_blocks,
                        title_override=op.get("title"),
                        rationale=op.get("rationale"),
                    )
                )
            elif action == "split":
                src_tid = op["source_task_id"]
                view = op["view"]
                handled_existing_tasks.add((view, src_tid))
                split_source_tasks.add(src_tid)
                for s_idx, target in enumerate(op["targets"], start=1):
                    t_view = target.get("view", view)
                    req_ids = sorted(set(target.get("requirement_ids", [])))
                    f_ids = sorted(set(target.get("flow_ids", [])))
                    ckey = target.get("candidate_key") or _candidate_key(
                        plan_id, t_view, "split", f_ids, req_ids, split_index=s_idx
                    )
                    proposed_bid = (
                        target.get("proposed_business_id")
                        if target.get("proposed_business_id") is not None
                        else target.get("business_id")
                    )
                    obl_ids = sorted(
                        set(target.get("obligation_ids", []))
                        | {flow_obligation_id[fid] for fid in f_ids}
                        | {other_ver_obligation_id[rid] for rid in req_ids if rid in other_ver_obligation_id}
                    )
                    part_kinds = sorted(
                        set(target.get("part_kinds", []))
                        | {
                            p["kind"]
                            for fid in f_ids
                            for p in flows_by_id[fid]["parts"]
                            if p["applicability"] == "applicable"
                        }
                    )
                    roles = (
                        sorted(set(target["roles"]))
                        if "roles" in target
                        else _infer_roles(
                            flow_ids=f_ids,
                            requirement_ids=req_ids,
                            part_kinds=part_kinds,
                            ver_by_id=ver_by_id,
                            impl_def_req_ids=impl_def_req_ids,
                        )
                    )
                    covered_reqs.update(req_ids)
                    covered_flows.update(f_ids)
                    covered_obls.update(obl_ids)
                    for fid in f_ids:
                        covered_parts_by_flow.setdefault(fid, set()).update(part_kinds)
                    append_delta(
                        _normalize_create_proposal(
                            plan_id=plan_id,
                            plan_ref=plan_ref,
                            view=t_view,
                            action="split",
                            candidate_key=ckey,
                            proposed_business_id=proposed_bid,
                            requirement_ids=req_ids,
                            flow_ids=f_ids,
                            part_kinds=part_kinds,
                            roles=roles,
                            obligation_ids=obl_ids,
                            req_by_id=req_by_id,
                            ledger_blocks=ledger_blocks,
                            title_override=target.get("title"),
                            split_index=s_idx,
                            lineage={
                                **copy.deepcopy(op["lineage"]),
                                "source_task_id": src_tid,
                                "source_status": triplet["master"][src_tid].get("status"),
                            },
                            scope=op["scope"],
                            source_diff_evidence=op["source_diff_evidence"],
                            rationale=op["rationale"],
                        )
                    )
            elif action == "merge":
                src_tids = list(op["source_task_ids"])
                view = op["view"]
                target_tid = op.get("target_task_id")
                view_map = triplet["back_by_tid"] if view == "back" else triplet["gameplay_by_tid"]
                for stid in src_tids:
                    handled_existing_tasks.add((view, stid))
                    if target_tid is None or stid != target_tid:
                        absorbed_merge_source_tasks.add(stid)
                req_ids = sorted(set(op.get("requirement_ids", [])))
                f_ids = sorted(set(op.get("flow_ids", [])))
                obl_ids = sorted(
                    set(op.get("obligation_ids", []))
                    | {flow_obligation_id[fid] for fid in f_ids}
                    | {other_ver_obligation_id[rid] for rid in req_ids if rid in other_ver_obligation_id}
                )
                part_kinds = sorted(
                    set(op.get("part_kinds", []))
                    | {
                        p["kind"]
                        for fid in f_ids
                        for p in flows_by_id[fid]["parts"]
                        if p["applicability"] == "applicable"
                    }
                )
                roles = (
                    sorted(set(op["roles"]))
                    if "roles" in op
                    else _infer_roles(
                        flow_ids=f_ids,
                        requirement_ids=req_ids,
                        part_kinds=part_kinds,
                        ver_by_id=ver_by_id,
                        impl_def_req_ids=impl_def_req_ids,
                    )
                )
                covered_reqs.update(req_ids)
                covered_flows.update(f_ids)
                covered_obls.update(obl_ids)
                for fid in f_ids:
                    covered_parts_by_flow.setdefault(fid, set()).update(part_kinds)
                merge_lineage = {
                    **copy.deepcopy(op["lineage"]),
                    "source_task_ids": src_tids,
                    "source_statuses": {str(s): triplet["master"][s].get("status") for s in src_tids},
                    "source_business_ids": {str(s): view_map[s]["id"] for s in src_tids},
                }
                if target_tid is not None:
                    cov = existing_task_coverage[(view, target_tid)]
                    append_delta(
                        {
                            "action": "merge",
                            "task_id": target_tid,
                            "candidate_key": None,
                            "business_id": cov["business_id"],
                            "view": view,
                            "plan_ref": copy.deepcopy(plan_ref),
                            "status": cov["status"],
                            "preserved_fields": ["taskmaster_id", "business_id", "status", "history"],
                            "requirement_ids": req_ids,
                            "flow_ids": f_ids,
                            "part_kinds": part_kinds,
                            "roles": roles,
                            "obligation_ids": obl_ids,
                            "scope": copy.deepcopy(op["scope"]),
                            "source_diff_evidence": copy.deepcopy(op["source_diff_evidence"]),
                            "lineage": merge_lineage,
                            "rationale": op["rationale"],
                            "old_done_satisfies_new_obligations": False,
                            "requires_new_verification": True,
                        }
                    )
                else:
                    ckey = op.get("candidate_key") or _candidate_key(plan_id, view, "merge", f_ids, req_ids)
                    proposed_bid = (
                        op.get("proposed_business_id")
                        if op.get("proposed_business_id") is not None
                        else op.get("business_id")
                    )
                    append_delta(
                        _normalize_create_proposal(
                            plan_id=plan_id,
                            plan_ref=plan_ref,
                            view=view,
                            action="merge",
                            candidate_key=ckey,
                            proposed_business_id=proposed_bid,
                            requirement_ids=req_ids,
                            flow_ids=f_ids,
                            part_kinds=part_kinds,
                            roles=roles,
                            obligation_ids=obl_ids,
                            req_by_id=req_by_id,
                            ledger_blocks=ledger_blocks,
                            title_override=op.get("title"),
                            lineage=merge_lineage,
                            scope=op["scope"],
                            source_diff_evidence=op["source_diff_evidence"],
                            rationale=op["rationale"],
                        )
                    )
            elif action == "retire":
                tid = op["task_id"]
                view = op["view"]
                cov = existing_task_coverage[(view, tid)]
                handled_existing_tasks.add((view, tid))
                retired_existing_tasks.add(tid)
                append_delta(
                    {
                        "action": "retire",
                        "task_id": tid,
                        "candidate_key": None,
                        "business_id": cov["business_id"],
                        "view": view,
                        "plan_ref": copy.deepcopy(plan_ref),
                        "status": cov["status"],
                        "preserved_fields": ["taskmaster_id", "business_id", "status", "history"],
                        "scope": copy.deepcopy(op["scope"]),
                        "source_diff_evidence": copy.deepcopy(op["source_diff_evidence"]),
                        "lineage": copy.deepcopy(op["lineage"]),
                        "rationale": op["rationale"],
                        "authority_ref": op.get("authority_ref"),
                    }
                )

    # 4. Automatically inventory reusable mature Tasks for any Flow/Requirement not already handled.
    for (view_name, tid), cov in sorted(existing_task_coverage.items()):
        if (view_name, tid) in handled_existing_tasks or tid in retired_existing_tasks:
            continue
        matched_reqs = sorted(
            cov["requirement_ids"] & {rid for rid, v in ver_by_id.items() if v["disposition"] != "deferred"}
        )
        candidate_flows = sorted(cov["flow_ids"] & set(flows_by_id))
        matched_flows: list[str] = []
        matched_flow_obls: set[str] = set()
        inferred_parts: set[str] = set()
        for fid in candidate_flows:
            flow = flows_by_id[fid]
            f_reqs = set(flow_plan_reqs_map[fid])
            f_app_parts = {p["kind"] for p in flow["parts"] if p["applicability"] == "applicable"}
            if cov["status"] == "done":
                reqs_ok = bool(f_reqs) and (f_reqs <= cov["requirement_ids"])
                parts_ok = (not cov["explicit_part_kinds"]) or (f_app_parts <= cov["part_kinds"])
                if reqs_ok and parts_ok:
                    matched_flows.append(fid)
                    matched_flow_obls.add(flow_obligation_id[fid])
                    if not cov["explicit_part_kinds"]:
                        inferred_parts.update(f_app_parts)
                # Else: old done task does NOT satisfy newly introduced Requirements/parts of fid!
            else:
                if cov["has_binding"]:
                    matched_flows.append(fid)
                    if flow_obligation_id[fid] in cov["obligation_ids"]:
                        matched_flow_obls.add(flow_obligation_id[fid])
                elif bool(f_reqs) and (f_reqs <= cov["requirement_ids"]):
                    matched_flows.append(fid)
                    matched_flow_obls.add(flow_obligation_id[fid])
                    if not cov["explicit_part_kinds"]:
                        inferred_parts.update(f_app_parts)
        if not matched_reqs and not matched_flows:
            continue
        matched_obls = sorted(
            matched_flow_obls
            | {other_ver_obligation_id[rid] for rid in matched_reqs if rid in other_ver_obligation_id}
        )
        matched_parts = sorted(cov["part_kinds"] | inferred_parts)
        roles = sorted(cov["roles"])
        covered_reqs.update(matched_reqs)
        covered_flows.update(matched_flows)
        covered_obls.update(matched_obls)
        for fid in matched_flows:
            covered_parts_by_flow.setdefault(fid, set()).update(matched_parts)
        handled_existing_tasks.add((view_name, tid))
        append_delta(
            {
                "action": "reuse",
                "task_id": tid,
                "candidate_key": None,
                "business_id": cov["business_id"],
                "view": view_name,
                "plan_ref": copy.deepcopy(plan_ref),
                "status": cov["status"],
                "preserved_fields": ["taskmaster_id", "business_id", "status", "history"],
                "definition_digest": codec.canonical_digest(
                    protection.task_definition_projection(
                        triplet["back_by_tid"][tid] if view_name == "back" else triplet["gameplay_by_tid"][tid]
                    )
                ),
                "requirement_ids": matched_reqs,
                "flow_ids": matched_flows,
                "part_kinds": matched_parts,
                "roles": roles,
                "obligation_ids": matched_obls,
                "old_done_satisfies_new_obligations": False,
            }
        )

    # Check cumulative MVG baseline non-weakening against resulting explicit + reused active mappings
    # BEFORE auto-gap creation (so unreplaced retire/split/merge/update weakening cannot be masked).
    _check_mvg_baseline_non_weakening(
        manifest_info=manifest_info,
        change_intents=change_intents,
        plan_req_ids=set(req_by_id),
        flow_obligation_id=flow_obligation_id,
        explicit_and_reused_deltas=deltas_back + deltas_gameplay,
        retired_tids=retired_existing_tasks,
        split_source_tids=split_source_tasks,
        absorbed_merge_source_tids=absorbed_merge_source_tasks,
        updated_ops_by_tid=updated_ops_by_tid,
    )

    def unique_auto_candidate(view_name: str, f_ids: list[str], req_ids: list[str]) -> tuple[str, str]:
        idx = 0
        while True:
            ckey = _candidate_key(plan_id, view_name, "create", f_ids, req_ids, split_index=idx)
            bid = _candidate_business_id(view_name, ckey)
            if ckey not in used_candidate_keys and bid not in used_business_ids:
                used_candidate_keys.add(ckey)
                used_business_ids.add(bid)
                return ckey, bid
            idx += 1

    # 5. Compute real gaps: uncovered Flows (kept coherent, NEVER mechanically 4-split per part!)
    #    and uncovered other_verification obligations (NEVER fabricate fake Flows!).
    real_gaps: list[dict[str, Any]] = []
    for fid in sorted(flows_by_id):
        flow = flows_by_id[fid]
        flow_reqs = flow_plan_reqs_map[fid]
        if not flow_reqs:
            continue
        uncovered_f_reqs = [rid for rid in flow_reqs if rid not in covered_reqs]
        obl_id = flow_obligation_id[fid]
        applicable_parts = sorted(p["kind"] for p in flow["parts"] if p["applicability"] == "applicable")
        uncovered_parts = [pk for pk in applicable_parts if pk not in covered_parts_by_flow.get(fid, set())]
        if fid in covered_flows and not uncovered_f_reqs and obl_id in covered_obls:
            continue
        gap_reqs = uncovered_f_reqs or flow_reqs
        gap_parts = uncovered_parts or applicable_parts
        view = _choose_view_for_flow(flow, flow["parts"])
        ckey, proposed_bid = unique_auto_candidate(view, [fid], gap_reqs)
        proposal = _normalize_create_proposal(
            plan_id=plan_id,
            plan_ref=plan_ref,
            view=view,
            action="create",
            candidate_key=ckey,
            proposed_business_id=proposed_bid,
            requirement_ids=gap_reqs,
            flow_ids=[fid],
            part_kinds=gap_parts,
            roles=["producer"],
            obligation_ids=[obl_id],
            req_by_id=req_by_id,
            ledger_blocks=ledger_blocks,
            rationale=f"Real implementation gap for committed Flow {fid} (requirements: {', '.join(gap_reqs)}).",
        )
        append_delta(proposal)
        covered_flows.add(fid)
        covered_reqs.update(gap_reqs)
        covered_obls.add(obl_id)
        covered_parts_by_flow.setdefault(fid, set()).update(gap_parts)
        real_gaps.append(
            {
                "gap_kind": "flow",
                "flow_id": fid,
                "requirement_ids": gap_reqs,
                "obligation_ids": [obl_id],
                "candidate_key": ckey,
                "view": view,
                "mechanical_four_split": False,
            }
        )

    # Check any uncovered other_verification obligations.
    for item in other_verification_items:
        rid = item["requirement_id"]
        obl_id = item["obligation_id"]
        if rid in covered_reqs and obl_id in covered_obls:
            continue
        view = "back"
        ckey, proposed_bid = unique_auto_candidate(view, [], [rid])
        proposal = _normalize_create_proposal(
            plan_id=plan_id,
            plan_ref=plan_ref,
            view=view,
            action="create",
            candidate_key=ckey,
            proposed_business_id=proposed_bid,
            requirement_ids=[rid],
            flow_ids=[],
            part_kinds=[],
            roles=["integration_only_owner"],
            obligation_ids=[obl_id],
            req_by_id=req_by_id,
            ledger_blocks=ledger_blocks,
            rationale=f"Real non-Flow verification gap for Requirement {rid} (sink: {item['sink_id']}); no Flow fabricated.",
        )
        append_delta(proposal)
        covered_reqs.add(rid)
        covered_obls.add(obl_id)
        real_gaps.append(
            {
                "gap_kind": "other_verification",
                "flow_id": None,
                "requirement_ids": [rid],
                "obligation_ids": [obl_id],
                "candidate_key": ckey,
                "view": view,
                "fabricated_flow": False,
            }
        )

    # Disambiguate duplicate titles among create/split proposals deterministically via normalize_task_intents.
    create_like = [d for d in deltas_back + deltas_gameplay if d["action"] in ("create", "split")]
    if len(create_like) > 1:
        normalizer.disambiguate_duplicate_titles(create_like)

    all_deltas = deltas_back + deltas_gameplay
    action_counts = {action: 0 for action in sorted(ALLOWED_ACTIONS)}
    for d in all_deltas:
        action_counts[d["action"]] = action_counts.get(d["action"], 0) + 1

    removed_existing_tids = retired_existing_tasks | split_source_tasks | absorbed_merge_source_tasks

    return {
        "view_deltas": {"back": deltas_back, "gameplay": deltas_gameplay},
        "all_deltas": all_deltas,
        "removed_existing_tids": removed_existing_tids,
        "action_counts": action_counts,
        "real_gaps": real_gaps,
        "obligations": obligations,
        "other_verification_items": other_verification_items,
        "other_verification_refs": other_verification_refs,
        "deferred_items": deferred_items,
        "non_task_sinks_inventory": non_task_sinks_inventory,
    }


def preview_task_changes(
    root: Path | str,
    *,
    plan_id: str,
    scope_id: str,
    audit_ref: str,
    protection_ref: str | None = None,
    manifest_ref: str | None = None,
    change_intents_ref: str | None = None,
    before_reread: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Run read-only 3C reuse inventory and task-change preview."""
    root_path: Path | None = None
    obs: preflight.Observations | None = None
    audit_obs: sources.Observations | None = None
    diagnostics: list[dict[str, Any]] = []

    result: dict[str, Any] = {
        "schema_version": SCHEMA,
        "ok": False,
        "stable": False,
        "plan_id": plan_id,
        "scope_id": scope_id,
        "audit_ref": audit_ref,
        "authorization": dict(AUTHORIZATION),
        "old_done_satisfies_new_obligations": False,
        "permanent_task_ids_allocated": False,
        "source_audit": None,
        "protection": None,
        "manifest_baseline": None,
        "requirement_accounting": None,
        "reuse_inventory": None,
        "view_deltas": {"back": [], "gameplay": []},
        "binding_preview": None,
        "origins_preview": None,
        "schema_compatibility": None,
        "diagnostics": diagnostics,
        "observations": [],
        "preview_digest": None,
    }

    committed_catalog_digest: str | None = None

    try:
        try:
            root_path = Path(root).resolve(strict=True)
        except (OSError, ValueError) as error:
            _fail(
                codec.ReasonCode.INVALID_ARGUMENT,
                owning_stage="3C",
                stage=codec.Stage.PATH,
                entity_id=str(root),
                expected="existing resolvable repository root directory",
                actual=f"{type(error).__name__}: {error}",
                path=str(root),
            )
        if not root_path.is_dir():
            _fail(
                codec.ReasonCode.INVALID_ARGUMENT,
                owning_stage="3C",
                stage=codec.Stage.PATH,
                entity_id=str(root_path),
                expected="existing repository root directory",
                actual="not a directory",
                path=str(root_path),
            )
        obs = preflight.Observations(root_path)

        _validate_nonempty_str(plan_id, "plan-id", owning_stage="3C")
        _validate_nonempty_str(scope_id, "scope-id", owning_stage="3C")
        preflight.path(audit_ref)

        # 1. Validate committed 3B formal adoption closure.
        committed_bundle = _load_committed_plan(root_path, obs, plan_id=plan_id, scope_id=scope_id)
        committed_catalog_digest = committed_bundle["committed"]["catalog_raw_digest"]
        plan = committed_bundle["plan"]
        plan_ref = committed_bundle["plan_ref"]
        origins = committed_bundle["origins"]
        existing_binding = committed_bundle["existing_binding"]
        flows_by_id = _resolve_plan_flows(plan, committed_bundle["catalog_flows_by_id"])

        # 2. Verify current 3A source audit proof & plan.source_identity alignment.
        audit_obs, source_audit_summary = _verify_3a_and_source_identity(
            root_path,
            obs,
            audit_ref=audit_ref,
            scope_id=scope_id,
            plan=plan,
            plan_path=plan_ref["path"],
        )
        ledger_blocks = source_audit_summary.pop("ledger_blocks")
        result["source_audit"] = source_audit_summary

        # 3. Validate Requirement dispositions (reject source_gap; preserve single disposition + M:N routes + dedup evidence).
        dispositions = _verify_plan_dispositions(plan, plan_ref["path"])
        result["requirement_accounting"] = {
            "authoritative_dispositions": dispositions["verifications"],
            "route_memberships": dispositions["route_memberships"],
            "shared_evidence": dispositions["shared_evidence"],
            "dispositions_summary": dispositions["dispositions_summary"],
        }

        # 4. Join current Taskmaster triplet via TaskJoinContext.
        triplet = _load_triplet(obs)

        # 5. Optional protection archive, cumulative MVG manifest baseline, and explicit change-intents.
        result["protection"] = _verify_optional_protection(root_path, obs, protection_ref)
        manifest_info = _load_optional_manifest(obs, manifest_ref)
        if manifest_info is not None:
            result["manifest_baseline"] = {
                "path": manifest_info["path"],
                "raw_digest": manifest_info["raw_digest"],
                "canonical_digest": manifest_info["canonical_digest"],
                "flow_count": len(manifest_info["document"].get("flows", [])),
                "test_count": len(manifest_info["document"].get("tests", [])),
            }
        change_intents = _validate_change_intents(
            obs,
            change_intents_ref,
            plan=plan,
            flows_by_id=flows_by_id,
            triplet=triplet,
            manifest_info=manifest_info,
            ledger_blocks=ledger_blocks,
        )

        # 6. Inventory flows/non-flow obligations, match mature Tasks, and build deltas.
        inventory_result = _inventory_and_plan_deltas(
            plan=plan,
            plan_ref=plan_ref,
            flows_by_id=flows_by_id,
            dispositions=dispositions,
            triplet=triplet,
            existing_binding=existing_binding,
            manifest_info=manifest_info,
            change_intents=change_intents,
            ledger_blocks=ledger_blocks,
        )
        parts = _aggregate_parts(plan, flows_by_id)
        binding_preview, origins_preview, schema_compat = _build_binding_and_origins_preview(
            plan=plan,
            plan_ref=plan_ref,
            origins=origins,
            existing_binding=existing_binding,
            manifest_info=manifest_info,
            all_deltas=inventory_result["all_deltas"],
            removed_existing_tids=inventory_result["removed_existing_tids"],
            obligations=inventory_result["obligations"],
            other_verification_refs=inventory_result["other_verification_refs"],
            parts=parts,
        )

        result["view_deltas"] = inventory_result["view_deltas"]
        result["binding_preview"] = binding_preview
        result["origins_preview"] = origins_preview
        result["schema_compatibility"] = schema_compat
        result["reuse_inventory"] = {
            "flow_count": len(flows_by_id),
            "flows": [
                {
                    "id": f["id"],
                    "requirement_ids": sorted(set(f["requirement_ids"]) & set(dispositions["requirements"])),
                    "applicable_part_kinds": sorted(p["kind"] for p in f["parts"] if p["applicability"] == "applicable"),
                    "handoff_count": len(f.get("handoffs", [])),
                    "state_owner_count": len(f.get("state_owners", [])),
                    "verification_targets": sorted(set(f.get("verification_targets", []))),
                }
                for _fid, f in sorted(flows_by_id.items())
            ],
            "other_verification_items": inventory_result["other_verification_items"],
            "deferred_items": inventory_result["deferred_items"],
            "non_task_sinks": inventory_result["non_task_sinks_inventory"],
            "real_gaps": inventory_result["real_gaps"],
            "gap_count": len(inventory_result["real_gaps"]),
            "action_counts": inventory_result["action_counts"],
            "all_reused": (
                len(inventory_result["real_gaps"]) == 0
                and inventory_result["action_counts"]["create"] == 0
                and inventory_result["action_counts"]["split"] == 0
                and inventory_result["action_counts"]["update"] == 0
                and inventory_result["action_counts"]["merge"] == 0
                and inventory_result["action_counts"]["retire"] == 0
            ),
            "fabricated_runtime_apis": False,
        }
    except codec.CodecError as error:
        diagnostics.append(
            _tag_diagnostic(error.diagnostic, owning_stage="3C", entity_id=plan_id, resume_ref=audit_ref)
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError, UnicodeError, RecursionError) as error:
        diagnostics.append(
            _diag(
                codec.ReasonCode.IDENTITY_UNPROVABLE,
                owning_stage="3C",
                stage=codec.Stage.BUNDLE,
                entity_id=plan_id,
                expected="complete valid 3A/3B/triplet inputs",
                actual=f"{type(error).__name__}: {error}",
                resume_ref=audit_ref,
            )
        )

    # Testing hook for deterministic mid-run concurrent edit injection before re-read.
    if before_reread is not None:
        before_reread()

    # End-of-run re-read stability verification (both 3A audit observations and main observations).
    drift_diags: list[dict[str, Any]] = []
    if audit_obs is not None:
        try:
            audit_obs.verify()
        except codec.CodecError as error:
            drift_diags.append(
                _tag_diagnostic(
                    codec.Diagnostic(
                        codec.ReasonCode.FILE_CHANGED,
                        error.diagnostic.stage or codec.Stage.PATH,
                        error.diagnostic.entity_id or scope_id,
                        error.diagnostic.expected,
                        error.diagnostic.actual,
                        error.diagnostic.resume_ref or audit_ref,
                    ),
                    owning_stage="3A",
                    resume_ref=audit_ref,
                )
            )
        except (OSError, ValueError) as error:
            drift_diags.append(
                _diag(
                    codec.ReasonCode.FILE_CHANGED,
                    owning_stage="3A",
                    stage=codec.Stage.PATH,
                    entity_id=scope_id,
                    expected="unchanged 3A source/audit observations during preview",
                    actual=f"{type(error).__name__}: {error}",
                    resume_ref=audit_ref,
                    path=audit_ref,
                )
            )

    if obs is not None:
        for raw_drift in obs.finish():
            drift_diags.append(_tag_diagnostic(raw_drift, owning_stage="3C"))

    if committed_catalog_digest is not None and root_path is not None:
        try:
            after_cat = codec.read_reference_bytes(root_path, records.CATALOG_PATH)
            if codec.raw_digest(after_cat) != committed_catalog_digest:
                drift_diags.append(
                    _diag(
                        codec.ReasonCode.FILE_CHANGED,
                        owning_stage="3B",
                        stage=codec.Stage.BUNDLE,
                        entity_id=records.CATALOG_PATH,
                        expected=committed_catalog_digest,
                        actual=codec.raw_digest(after_cat),
                        resume_ref=records.CATALOG_PATH,
                        path=records.CATALOG_PATH,
                    )
                )
        except (codec.CodecError, OSError) as error:
            drift_diags.append(
                _diag(
                    codec.ReasonCode.FILE_CHANGED,
                    owning_stage="3B",
                    stage=codec.Stage.BUNDLE,
                    entity_id=records.CATALOG_PATH,
                    expected=committed_catalog_digest,
                    actual=type(error).__name__,
                    resume_ref=records.CATALOG_PATH,
                    path=records.CATALOG_PATH,
                )
            )

    diagnostics.extend(drift_diags)
    result["stable"] = not drift_diags and not any(
        d["reason_code"] == codec.ReasonCode.FILE_CHANGED.value for d in diagnostics
    )
    result["observations"] = obs.identities() if obs is not None else []
    result["ok"] = (not diagnostics) and result["stable"]

    # Deterministic preview_digest strictly excludes timestamps and run-specific report_path.
    digest_payload = {
        key: result[key]
        for key in (
            "schema_version",
            "ok",
            "stable",
            "plan_id",
            "scope_id",
            "audit_ref",
            "authorization",
            "old_done_satisfies_new_obligations",
            "permanent_task_ids_allocated",
            "source_audit",
            "protection",
            "manifest_baseline",
            "requirement_accounting",
            "reuse_inventory",
            "view_deltas",
            "binding_preview",
            "origins_preview",
            "schema_compatibility",
            "diagnostics",
            "observations",
        )
    }
    result["preview_digest"] = codec.canonical_digest(digest_payload)
    return result


def create_run_directory(root: Path | str, run_id: str) -> Path:
    """Exclusively create logs/ci/<YYYY-MM-DD>/b-route-task-preview/<run-id>."""
    if (
        type(run_id) is not str
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", run_id) is None
        or run_id.upper() in _WINDOWS_RESERVED_RUN_IDS
    ):
        _fail(
            codec.ReasonCode.INVALID_ARGUMENT,
            owning_stage="3C",
            stage=codec.Stage.PATH,
            entity_id=str(run_id),
            expected="1-96 ASCII non-reserved run-id characters [A-Za-z0-9][A-Za-z0-9_-]{0,95}",
            actual=run_id,
        )
    try:
        root_path = Path(root).resolve(strict=True)
    except (OSError, ValueError) as error:
        _fail(
            codec.ReasonCode.INVALID_ARGUMENT,
            owning_stage="3C",
            stage=codec.Stage.PATH,
            entity_id=str(root),
            expected="existing explicit root directory",
            actual=f"{type(error).__name__}: {error}",
            path=str(root),
        )
    relative = (
        "logs/ci/"
        + dt.datetime.now(dt.timezone.utc).date().isoformat()
        + "/b-route-task-preview/"
        + run_id
    )
    try:
        if not root_path.is_dir():
            _fail(
                codec.ReasonCode.INVALID_ARGUMENT,
                owning_stage="3C",
                stage=codec.Stage.PATH,
                entity_id=str(root_path),
                expected="existing explicit root directory",
                actual="missing root",
                path=str(root_path),
            )
        inventory.no_reparse(root_path)
        target = inventory.safe_input(root_path, relative, allow_logs=True)
        current = root_path
        for component in relative.split("/")[:-1]:
            current /= component
            current.mkdir(exist_ok=True)
            inventory.no_reparse(current)
        target.mkdir(exist_ok=False)
        inventory.no_reparse(target)
        return target
    except codec.CodecError:
        raise
    except (OSError, ValueError) as error:
        _fail(
            codec.ReasonCode.CONFLICT if isinstance(error, FileExistsError) else codec.ReasonCode.UNSAFE_PATH,
            owning_stage="3C",
            stage=codec.Stage.PATH,
            entity_id=run_id,
            expected="new contained logs run directory (existing run is never overwritten)",
            actual=type(error).__name__,
            resume_ref=relative,
            path=relative,
        )
