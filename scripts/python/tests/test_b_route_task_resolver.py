"""Deterministic tests for Story 3.3 unified Task origin and applicable plan-set resolution.

Covers every row of the Story 3.3 I/O & Edge-Case Matrix (B_MULTI, FROZEN_A,
CLONE_PEND, NOT_EN, NON_FLOW), zero-write/zero-lock invariants, clean-clone
without logs/, double-read drift detection, six-field Diagnostics, non-authorization
invariants, CLI/dev_cli/builder integration, and policy anchoring.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import base64
import contextlib
import copy
import hashlib
import importlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS_PY = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS_PY.parents[1]
if str(SCRIPTS_PY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_PY))

import _b_route_adoption_review as adoption_review
import _b_route_codec as codec
import _b_route_commit as commit
import _b_route_commit_projection as commit_projection
import _b_route_operation_scope as op_scope
import _b_route_protection as protection
import _b_route_records as records
import _b_route_task_resolver as resolver
import _planning_apply_journal as journal
import dev_cli
import dev_cli_builders
import resolve_b_route_task_origin as origin_cli


DIAGNOSTIC_KEYS = {"reason_code", "stage", "entity_id", "expected", "actual", "resume_ref"}
AUTH_KEYS = ("execution_authorized", "readiness", "runtime_verified", "default_b_enabled")


def _encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _typed_ref(path: str, schema_version: str, entity_id: str, revision: int, raw: bytes) -> dict:
    return {
        "path": path,
        "schema_version": schema_version,
        "entity_id": entity_id,
        "revision": revision,
        "digest": codec.raw_digest(raw),
        "verification_mode": "raw",
        "codec_version": None,
    }


def _owned_ref(owner: str, ref: str, files: list[tuple[str, bytes]]) -> dict:
    return {
        "owner": owner,
        "ref": ref,
        "files": [{"path": p, "raw_digest": codec.raw_digest(raw)} for p, raw in files],
    }


def _four_parts(*, domain: bool = True, adapter: bool = True, binding: bool = True, scene: bool = False) -> list[dict]:
    specs = [
        ("domain_rules", domain, "Core deterministic domain rules."),
        ("csharp_adapter", adapter, "Thin C# adapter forwarding commands."),
        ("binding", binding, "Resource and event binding contracts."),
        ("scene", scene, "Godot scene wiring for UI presentation."),
    ]
    return [
        {
            "kind": kind,
            "applicability": "applicable" if applicable else "not_applicable",
            "rationale": desc if applicable else f"{kind} is not needed.",
            "responsibilities": [desc] if applicable else [],
        }
        for kind, applicable, desc in specs
    ]


def _make_flow(
    flow_id: str,
    req_ids: list[str],
    state_uses: list[dict] | None = None,
) -> dict:
    return {
        "id": flow_id,
        "requirement_ids": req_ids,
        "entry": f"enter:{flow_id}",
        "entry_condition": f"precondition:{flow_id}",
        "success_end": f"complete:{flow_id}",
        "branches": [
            {"kind": "failure", "rationale": "Reject invalid input.", "description": "Abort safely."},
            {"kind": "cancel", "rationale": "Allow user cancel.", "description": "Return cleanly."},
            {"kind": "return", "rationale": "Return to map.", "description": "Exit to caller."},
        ],
        "handoffs": [],
        "state_owners": list(state_uses or []),
        "parts": _four_parts(),
        "observable_result": f"observable:{flow_id}",
        "verification_targets": [f"verify:{flow_id}"],
        "loops": [],
    }


def _build_plan_doc(
    *,
    plan_id: str,
    revision: int,
    source_manifest_ref: dict,
    source_ledger_ref: dict,
    source_revision: str,
    source_manifest_digest: str,
    proof_ref: dict,
    requirements: list[dict],
    flows: list[dict],
    commands: list[dict],
    states: list[dict],
    logical_references: list[dict],
    requirement_verification: list[dict],
    requirement_route_memberships: list[dict],
    requirement_evidence: list[dict],
    evidence_source_refs: list[dict],
) -> dict:
    coverage_table = [
        {k: v for k, v in row.items() if k != "evidence_ids"}
        for row in requirement_verification
    ]
    ev_by_owner_ref = {(r["owner"], r["ref"]): r for r in evidence_source_refs}
    applicability = [
        {
            "requirement_id": row["requirement_id"],
            "disposition": row["disposition"],
            "rationale": row["rationale"],
            "other_verification_refs": (
                [ev_by_owner_ref[("other_verification", row["verification_ref"])]]
                if row["disposition"] == "other_verification"
                else []
            ),
        }
        for row in requirement_verification
    ]
    return {
        "schema_version": "newrouge.b-route-plan.v1",
        "plan_id": plan_id,
        "revision": revision,
        "source_identity": {
            "manifest_ref": source_manifest_ref,
            "ledger_ref": source_ledger_ref,
            "source_revision": source_revision,
            "source_manifest_digest": source_manifest_digest,
        },
        "requirements": requirements,
        "definitions": {
            "flows": flows,
            "commands": commands,
            "states": states,
        },
        "logical_references": logical_references,
        "requirement_verification": requirement_verification,
        "requirement_route_memberships": requirement_route_memberships,
        "requirement_evidence": requirement_evidence,
        "evidence_source_refs": evidence_source_refs,
        "coverage_table": coverage_table,
        "applicability": applicability,
        "adoption_proof_refs": [proof_ref],
        "lineage": {
            "previous_plan_ref": None,
            "change_summary": f"Committed {plan_id} rev {revision}.",
            "identity_alignment": [],
        },
    }


def _build_binding_doc(
    *,
    plan_id: str,
    binding_revision: int,
    plan_ref: dict,
    stage: str,
    task_mappings: list[dict],
    obligations: list[dict],
    implementation_objects: list[dict] | None = None,
    other_verification_refs: list[dict] | None = None,
) -> dict:
    return {
        "schema_version": "newrouge.b-route-binding.v1",
        "plan_id": plan_id,
        "binding_revision": binding_revision,
        "plan_ref": plan_ref,
        "stage": stage,
        "task_mappings": task_mappings,
        "parts": _four_parts(),
        "implementation_objects": list(implementation_objects or []),
        "obligations": obligations,
        "manifest_refs": [],
        "other_verification_refs": list(other_verification_refs or []),
    }


class ResolverRepoBuilder:
    """Builds schema-valid committed B-route repositories and optional clean clones."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def put(self, rel: str, data: bytes | str) -> bytes:
        raw = data.encode("utf-8") if isinstance(data, str) else data
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        return raw

    def put_json(self, rel: str, value: object) -> bytes:
        return self.put(rel, _encoded(value))

    def read_json(self, rel: str) -> object:
        return json.loads((self.root / rel).read_text(encoding="utf-8"))

    def write_adr_0040(self, *, valid: bool = True) -> bytes:
        if valid:
            text = (REPO_ROOT / resolver.ADR_0040).read_text(encoding="utf-8")
        else:
            text = "# ADR-0040\n\n- Status: Superseded\n\nReplaced.\n"
        return self.put(resolver.ADR_0040, text)

    def write_triplet(
        self,
        *,
        master_tasks: list[dict],
        back_tasks: list[dict],
        gameplay_tasks: list[dict],
    ) -> dict[str, bytes]:
        m_raw = self.put_json(resolver.TRIPLET["master"], {"master": {"tasks": master_tasks}})
        b_raw = self.put_json(resolver.TRIPLET["back"], back_tasks)
        g_raw = self.put_json(resolver.TRIPLET["gameplay"], gameplay_tasks)
        return {
            resolver.TRIPLET["master"]: m_raw,
            resolver.TRIPLET["back"]: b_raw,
            resolver.TRIPLET["gameplay"]: g_raw,
        }

    def write_sources_and_proof(self, *, use_log_proof: bool = True) -> dict:
        gdd_rel = "docs/gdd/reward.md"
        gdd_raw = self.put(gdd_rel, "# Reward\n\nReward flow and static audit.\n")
        other_v_rel = "docs/testing/static-audit-rule.md"
        other_v_raw = self.put(other_v_rel, "# Static Audit Verification\nDeterministic verification rule.\n")
        auth_rel = "docs/adr/ADR-0099-deferred-boundary.md"
        auth_raw = self.put(auth_rel, "# ADR-0099\n\n- Status: Accepted\n\nDeferred scope authority.\n")

        manifest_rel = "logs/ci/source-3a/source-manifest.json" if use_log_proof else "docs/planning/sources/source-manifest.json"
        ledger_rel = "logs/ci/source-3a/source-blocks.json" if use_log_proof else "docs/planning/sources/source-blocks.json"
        proof_rel = "logs/ci/source-3a/adoption-proof.json" if use_log_proof else "docs/planning/sources/adoption-proof.json"

        manifest_digest = codec.raw_digest(gdd_raw)
        source_rev = "src-rev-001"
        manifest_raw = self.put_json(
            manifest_rel,
            {
                "schema_version": "chapter3.source-manifest.v1",
                "source_revision": source_rev,
                "manifest_sha256": manifest_digest,
                "sources": [{"path": gdd_rel, "raw_digest": manifest_digest}],
            },
        )
        ledger_raw = self.put_json(
            ledger_rel,
            {
                "schema_version": "chapter3.source-blocks.v1",
                "source_revision": source_rev,
                "source_manifest_sha256": manifest_digest,
                "blocks": [
                    {"block_id": "BLK-REWARD-1", "path": gdd_rel},
                    {"block_id": "BLK-AUDIT-1", "path": gdd_rel},
                    {"block_id": "BLK-DEFER-1", "path": gdd_rel},
                    {"block_id": "BLK-COMBAT-1", "path": gdd_rel},
                ],
            },
        )
        proof_raw = self.put_json(proof_rel, {"schema_version": "test.proof.v1", "verdict": "approved"})
        return {
            "gdd_rel": gdd_rel,
            "gdd_raw": gdd_raw,
            "other_v_rel": other_v_rel,
            "other_v_raw": other_v_raw,
            "auth_rel": auth_rel,
            "auth_raw": auth_raw,
            "manifest_rel": manifest_rel,
            "manifest_raw": manifest_raw,
            "ledger_rel": ledger_rel,
            "ledger_raw": ledger_raw,
            "proof_rel": proof_rel,
            "proof_raw": proof_raw,
            "source_revision": source_rev,
            "source_manifest_digest": manifest_digest,
            "manifest_ref": _owned_ref("source_manifest", manifest_rel, [(manifest_rel, manifest_raw)]),
            "ledger_ref": _owned_ref("source_ledger", ledger_rel, [(ledger_rel, ledger_raw)]),
            "proof_ref": _owned_ref("planning_proof", proof_rel, [(proof_rel, proof_raw)]),
            "other_v_owned": _owned_ref("other_verification", other_v_rel, [(other_v_rel, other_v_raw)]),
            "auth_owned": _owned_ref("authority", auth_rel, [(auth_rel, auth_raw)]),
            "source_owned": _owned_ref("authority", gdd_rel, [(gdd_rel, gdd_raw)]),
        }

    def commit_bundle(
        self,
        *,
        operation_id: str,
        plans: list[tuple[str, dict]],
        bindings: list[tuple[str, dict]],
        origins_tasks: list[dict],
        frozen_a_refs: list[dict] | None = None,
        frozen_legacy_refs: list[dict] | None = None,
        allowed_a_operations: list[str] | None = None,
        a_write_allowed: bool = True,
        default_route: str = "A",
        authority_pins: list[tuple[str, bytes]] | None = None,
        scope_map: dict[str, tuple[list[str], list[str]]] | None = None,
        catalog_revision: int = 1,
    ) -> dict:
        adr_raw = self.write_adr_0040(valid=True)
        policy_doc = {
            "schema_version": "newrouge.b-route-policy.v1",
            "policy_id": "policy-main",
            "policy_revision": catalog_revision,
            "switch_boundary": {
                "default_route": default_route,
                "a_write_allowed": a_write_allowed,
                "allowed_a_operations": (
                    list(allowed_a_operations)
                    if allowed_a_operations is not None
                    else ["implement", "resume", "route"]
                ),
                "authority_refs": [_owned_ref("adr", resolver.ADR_0040, [(resolver.ADR_0040, adr_raw)])],
            },
            "frozen_a_refs": list(frozen_a_refs or []),
        }
        policy_raw = self.put_json(resolver.POLICY_PATH, policy_doc)
        policy_ref = _typed_ref(resolver.POLICY_PATH, "newrouge.b-route-policy.v1", "policy-main", catalog_revision, policy_raw)

        plan_refs_by_path: dict[str, dict] = {}
        plan_raw_by_path: dict[str, bytes] = {}
        plan_docs_by_path: dict[str, dict] = {}
        for rel, doc in plans:
            raw = self.put_json(rel, doc)
            plan_raw_by_path[rel] = raw
            plan_docs_by_path[rel] = doc
            plan_refs_by_path[rel] = _typed_ref(rel, "newrouge.b-route-plan.v1", doc["plan_id"], doc["revision"], raw)

        binding_refs_by_path: dict[str, dict] = {}
        binding_raw_by_path: dict[str, bytes] = {}
        for rel, doc in bindings:
            raw = self.put_json(rel, doc)
            binding_raw_by_path[rel] = raw
            binding_refs_by_path[rel] = _typed_ref(
                rel, "newrouge.b-route-binding.v1", doc["plan_id"], doc["binding_revision"], raw
            )

        origins_doc = {
            "schema_version": "newrouge.b-route-origins.v1",
            "origins_id": "task-origins",
            "revision": catalog_revision,
            "tasks": origins_tasks,
            "frozen_legacy_refs": list(frozen_legacy_refs or []),
        }
        origins_raw = self.put_json(resolver.ORIGINS_PATH, origins_doc)
        origins_ref = _typed_ref(resolver.ORIGINS_PATH, "newrouge.b-route-origins.v1", "task-origins", catalog_revision, origins_raw)

        definition_owners: list[dict] = []
        for rel, doc in plans:
            pref = plan_refs_by_path[rel]
            for kind, plural in (("flow", "flows"), ("command", "commands"), ("state", "states")):
                for defn in doc["definitions"][plural]:
                    definition_owners.append({"kind": kind, "definition_id": defn["id"], "plan_ref": pref})

        # Compute exact recursive resolved_definitions closure for receipt.
        owners_index = {(row["kind"], row["definition_id"]): row for row in definition_owners}
        use_fields = {"kind", "definition_id", "owner_plan_id", "owner_revision"}
        resolved_defs: dict[tuple[str, str], dict] = {}
        pending = []
        for rel, doc in plans:
            for child in records._walk(doc):
                if set(child) == use_fields:
                    pending.append(child)
        while pending:
            use = pending.pop()
            key = (use["kind"], use["definition_id"])
            if key in owners_index:
                resolved_defs[key] = owners_index[key]

        scopes = sorted(scope_map.keys()) if scope_map else ["scope-default"]
        targets: list[dict] = []
        for rel, raw in [
            (resolver.POLICY_PATH, policy_raw),
            (resolver.ORIGINS_PATH, origins_raw),
            *list(plan_raw_by_path.items()),
            *list(binding_raw_by_path.items()),
        ]:
            dg = codec.raw_digest(raw)
            targets.append(
                {
                    "path": rel,
                    "before_digest": None,
                    "after_digest": dg,
                    "projection_digest": dg,
                    "verification_mode": "immutable_bytes",
                    "codec_version": None,
                }
            )
        authority_rows = [
            {"path": p, "before_digest": codec.raw_digest(raw), "after_digest": codec.raw_digest(raw)}
            for p, raw in (authority_pins or [])
        ]
        receipt_rel = f"docs/planning/b-route/commits/{operation_id}.json"
        receipt_doc = {
            "schema_version": "newrouge.b-route-commit.v1",
            "operation_id": operation_id,
            "revision": 1,
            "operation_digest": codec.canonical_digest({"op": operation_id, "rev": catalog_revision}),
            "scopes": scopes,
            "authority": authority_rows,
            "targets": targets,
            "plan_refs": list(plan_refs_by_path.values()),
            "binding_refs": list(binding_refs_by_path.values()),
            "resolved_definitions": list(resolved_defs.values()),
            "result": {
                "target_paths": [row["path"] for row in targets],
                "scope_ids": scopes,
            },
        }
        receipt_raw = self.put_json(receipt_rel, receipt_doc)
        receipt_ref = _typed_ref(receipt_rel, "newrouge.b-route-commit.v1", operation_id, 1, receipt_raw)

        scope_heads: list[dict] = []
        if scope_map:
            for sid in sorted(scope_map):
                p_paths, b_paths = scope_map[sid]
                scope_heads.append(
                    {
                        "scope_id": sid,
                        "plan_refs": [plan_refs_by_path[p] for p in p_paths],
                        "binding_refs": [binding_refs_by_path[b] for b in b_paths],
                        "receipt_ref": receipt_ref,
                    }
                )
        elif plans or bindings:
            scope_heads.append(
                {
                    "scope_id": scopes[0],
                    "plan_refs": list(plan_refs_by_path.values()),
                    "binding_refs": list(binding_refs_by_path.values()),
                    "receipt_ref": receipt_ref,
                }
            )

        task_index = [
            {
                "task_id": row["task_id"],
                "plan_refs": row["plan_refs"],
                "binding_refs": row["binding_refs"],
            }
            for row in origins_tasks
        ]
        catalog_doc = {
            "schema_version": "newrouge.b-route-catalog.v1",
            "catalog_id": "catalog",
            "revision": catalog_revision,
            "policy_ref": policy_ref,
            "origins_ref": origins_ref,
            "scope_heads": scope_heads,
            "definition_owners": definition_owners,
            "task_index": task_index,
        }
        catalog_raw = self.put_json(resolver.CATALOG_PATH, catalog_doc)
        return {
            "policy_ref": policy_ref,
            "origins_ref": origins_ref,
            "catalog_raw": catalog_raw,
            "receipt_ref": receipt_ref,
            "plan_refs": plan_refs_by_path,
            "binding_refs": binding_refs_by_path,
        }


def _create_unapplied_operation(
    root: Path,
    *,
    operation_id: str,
    scope_ids: list[str],
    state: str = "prepared",
    write_commit_intent: bool = False,
    write_commit_pending: bool = False,
) -> None:
    """Persist a real schema-valid auxiliary operation envelope under logs/ci/b-route-operations."""
    req_path = "docs/gdd/reward.md"
    if not (root / req_path).is_file():
        (root / req_path).parent.mkdir(parents=True, exist_ok=True)
        (root / req_path).write_text("# Dummy\n", encoding="utf-8")
    req_raw_bytes = (root / req_path).read_bytes()
    req_dg = codec.raw_digest(req_raw_bytes)
    ref_obj = {"path": req_path, "schema_version": "test.ref.v1", "raw_digest": req_dg}

    request = {
        "schema_version": journal.TASK_COMPILATION_REQUEST,
        "producer": "task_compilation",
        "operation_id": operation_id,
        "scope_id": "scope-other",
        "plan_id": "other-plan",
        "audit_ref": ref_obj,
        "preview_ref": ref_obj,
    }
    request_raw = _encoded(request)
    target_path = "docs/planning/b-route/plans/other-plan/1.json"
    source_manifest_ref = _owned_ref(
        "source_manifest",
        "docs/planning/sources/other-manifest.json",
        [(req_path, req_raw_bytes)],
    )
    source_ledger_ref = _owned_ref(
        "source_ledger",
        "docs/planning/sources/other-blocks.json",
        [(req_path, req_raw_bytes)],
    )
    proof_ref = _owned_ref(
        "planning_proof",
        "docs/planning/sources/other-proof.json",
        [(req_path, req_raw_bytes)],
    )
    after_payload = _build_plan_doc(
        plan_id="other-plan",
        revision=1,
        source_manifest_ref=source_manifest_ref,
        source_ledger_ref=source_ledger_ref,
        source_revision=f"src-{operation_id}",
        source_manifest_digest=req_dg,
        proof_ref=proof_ref,
        requirements=[
            {
                "requirement_id": "REQ-OTHER-1",
                "source_block_ids": ["BLK-OTHER-1"],
                "acceptance_intent": f"Unrelated scope requirement for {operation_id}.",
                "non_task_sinks": [],
            }
        ],
        flows=[_make_flow("flow-other", ["REQ-OTHER-1"])],
        commands=[],
        states=[],
        logical_references=[],
        requirement_verification=[
            {
                "requirement_id": "REQ-OTHER-1",
                "disposition": "flow",
                "flow_id": "flow-other",
                "rationale": "Verified by unrelated other flow.",
                "sink_id": None,
                "verification_ref": None,
                "authority_ref": None,
                "evidence_ids": [],
            }
        ],
        requirement_route_memberships=[
            {"requirement_id": "REQ-OTHER-1", "flow_id": "flow-other", "observable_role": "primary"}
        ],
        requirement_evidence=[],
        evidence_source_refs=[],
    )
    after_raw = commit_projection.serialized(after_payload)
    after_raw_digest = codec.raw_digest(after_raw)
    plan_ref_obj = commit_projection.reference(target_path, after_raw)
    triplet_projs = {
        resolver.TRIPLET["master"]: after_raw_digest,
        resolver.TRIPLET["back"]: after_raw_digest,
        resolver.TRIPLET["gameplay"]: after_raw_digest,
    }
    sorted_scopes = sorted(set(scope_ids))
    frozen = {
        "producer": "task_compilation",
        "request": request,
        "scope_ids": sorted_scopes,
        "authority_refs": [ref_obj],
        "allocations": {
            "plan_id": "other-plan",
            "plan_revision": 1,
            "binding_revision": 1,
            "origins_revision": 1,
            "next_taskmaster_id_base": 100,
            "task_ids": {},
            "task_definitions": {},
        },
        "compilation": {
            "plan_id": "other-plan",
            "scope_id": "scope-other",
            "preview_digest": after_raw_digest,
            "current_catalog_digest": after_raw_digest,
            "current_frame_digest": after_raw_digest,
            "plan_ref": plan_ref_obj,
            "old_scope_ids": sorted_scopes,
            "new_scope_ids": sorted_scopes,
            "triplet_before_projections": triplet_projs,
            "triplet_after_projections": triplet_projs,
        },
        "targets": [
            {
                "path": target_path,
                "schema_version": "newrouge.b-route-plan.v1",
                "before_raw_digest": None,
                "after_raw_digest": after_raw_digest,
                "after_payload": after_payload,
                "verification_mode": "immutable_bytes",
            }
        ],
    }
    journal.prepare_operation(root, operation_id=operation_id, request_raw=request_raw, frozen=frozen)
    if state == "reserved":
        journal.reserve_operation(root, operation_id=operation_id)

    envelope = journal.read_operation(root, operation_id=operation_id)
    intent_rel, pending_rel = commit._paths(operation_id)
    if write_commit_pending:
        marker = {
            "schema_version": commit.SCHEMA + ".pending",
            "operation_id": operation_id,
            "frozen_digest": envelope["frozen_digest"],
        }
        (root / pending_rel).write_bytes(commit_projection.serialized(marker))
    if write_commit_intent:
        catalog_path = root / resolver.CATALOG_PATH
        cat_raw = catalog_path.read_bytes() if catalog_path.is_file() else None
        receipt = commit_projection.receipt_for_frozen(
            operation_id=operation_id,
            frozen=envelope["frozen"],
            resolved_definitions=[],
            catalog_before=cat_raw,
        )
        before_files = {
            target_path: None,
            resolver.CATALOG_PATH: base64.b64encode(cat_raw).decode("ascii") if cat_raw is not None else None,
        }
        intent_val = commit._seal(
            {
                "schema_version": commit.SCHEMA,
                "operation_id": operation_id,
                "frozen_digest": envelope["frozen_digest"],
                "policy_identity": adoption_review.policy_identity(),
                "phase": "applied",
                "before_files": before_files,
                "files": {},
                "directories": {},
                "trees": {},
                "receipt": receipt,
                "catalog_before": before_files[resolver.CATALOG_PATH],
                "catalog_after": None,
                "origins_before": None,
                "publication_base": before_files[resolver.CATALOG_PATH],
                "catalog_attempts": [],
                "catalog_after_digest": None,
                "catalog_frame": None,
            }
        )
        (root / intent_rel).write_bytes(commit_projection.serialized(intent_val))


class TaskResolverTests(unittest.TestCase):
    """Covers all 5 Matrix rows (B_MULTI, FROZEN_A, CLONE_PEND, NOT_EN, NON_FLOW) and CLI/policy invariants."""

    def _assert_non_auth(self, result: dict) -> None:
        for key in AUTH_KEYS:
            self.assertIs(result[key], False, f"{key} must remain False")
            self.assertIs(result["authorization"][key], False, f"authorization.{key} must remain False")
        for diag in result["diagnostics"]:
            self.assertEqual(set(diag.keys()), DIAGNOSTIC_KEYS)

    def _make_single_and_multi_plan_repo(self, root: Path, *, two_plans: bool = False, use_log_proof: bool = True) -> dict:
        builder = ResolverRepoBuilder(root)
        src = builder.write_sources_and_proof(use_log_proof=use_log_proof)
        builder.write_triplet(
            master_tasks=[
                {"id": 1, "title": "Reward Core", "status": "in-progress", "dependencies": []},
                {"id": 2, "title": "Non-Flow Governance Audit", "status": "pending", "dependencies": []},
                {"id": 3, "title": "Deferred Task", "status": "pending", "dependencies": []},
            ],
            back_tasks=[
                {"id": "NG-0001", "taskmaster_id": 1, "title": "Reward Core", "status": "in-progress"},
                {"id": "NG-0002", "taskmaster_id": 2, "title": "Non-Flow Governance Audit", "status": "pending"},
                {"id": "NG-0003", "taskmaster_id": 3, "title": "Deferred Task", "status": "pending"},
            ],
            gameplay_tasks=[
                {"id": "GM-0001", "taskmaster_id": 1, "title": "Reward Core", "status": "in-progress"},
            ],
        )

        plan_a_path = "docs/planning/b-route/plans/plan-reward/1.json"
        plan_a = _build_plan_doc(
            plan_id="plan-reward",
            revision=1,
            source_manifest_ref=src["manifest_ref"],
            source_ledger_ref=src["ledger_ref"],
            source_revision=src["source_revision"],
            source_manifest_digest=src["source_manifest_digest"],
            proof_ref=src["proof_ref"],
            requirements=[
                {
                    "requirement_id": "REQ-REWARD-1",
                    "source_block_ids": ["BLK-REWARD-1"],
                    "acceptance_intent": "Reward selection returns to map.",
                    "non_task_sinks": [],
                },
                {
                    "requirement_id": "REQ-AUDIT-1",
                    "source_block_ids": ["BLK-AUDIT-1"],
                    "acceptance_intent": "Static audit check.",
                    "non_task_sinks": ["sink:static-audit"],
                },
                {
                    "requirement_id": "REQ-DEFER-1",
                    "source_block_ids": ["BLK-DEFER-1"],
                    "acceptance_intent": "Deferred milestone rule.",
                    "non_task_sinks": [],
                },
            ],
            flows=[_make_flow("flow-reward", ["REQ-REWARD-1"], state_uses=[
                {"kind": "state", "definition_id": "state-reward", "owner_plan_id": "plan-reward", "owner_revision": 1}
            ])],
            commands=[
                {
                    "id": "cmd-pick-reward",
                    "requirement_ids": ["REQ-REWARD-1"],
                    "responsibility": "Pick reward option.",
                    "uses": [{"kind": "state", "definition_id": "state-reward", "owner_plan_id": "plan-reward", "owner_revision": 1}],
                }
            ],
            states=[
                {
                    "id": "state-reward",
                    "requirement_ids": ["REQ-REWARD-1"],
                    "responsibility": "Track current reward offer.",
                    "uses": [],
                }
            ],
            logical_references=[],
            requirement_verification=[
                {
                    "requirement_id": "REQ-REWARD-1",
                    "disposition": "flow",
                    "flow_id": "flow-reward",
                    "rationale": "Verified by reward flow.",
                    "sink_id": None,
                    "verification_ref": None,
                    "authority_ref": None,
                    "evidence_ids": [],
                },
                {
                    "requirement_id": "REQ-AUDIT-1",
                    "disposition": "other_verification",
                    "flow_id": None,
                    "rationale": "Static deterministic audit suffices without fake MVG flow.",
                    "sink_id": "sink:static-audit",
                    "verification_ref": src["other_v_rel"],
                    "authority_ref": None,
                    "evidence_ids": [],
                },
                {
                    "requirement_id": "REQ-DEFER-1",
                    "disposition": "deferred",
                    "flow_id": None,
                    "rationale": "Explicitly deferred to next milestone by ADR-0099.",
                    "sink_id": None,
                    "verification_ref": None,
                    "authority_ref": src["auth_rel"],
                    "evidence_ids": [],
                },
            ],
            requirement_route_memberships=[{"requirement_id": "REQ-REWARD-1", "flow_id": "flow-reward", "observable_role": "primary"}],
            requirement_evidence=[],
            evidence_source_refs=[src["other_v_owned"], src["auth_owned"]],
        )
        plan_a_raw = builder.put_json(plan_a_path, plan_a)
        plan_a_ref = _typed_ref(plan_a_path, "newrouge.b-route-plan.v1", "plan-reward", 1, plan_a_raw)

        binding_a_path = "docs/planning/b-route/bindings/plan-reward/1.json"
        binding_a = _build_binding_doc(
            plan_id="plan-reward",
            binding_revision=1,
            plan_ref=plan_a_ref,
            stage="3C",
            task_mappings=[
                {
                    "task_id": 1,
                    "view_refs": [
                        {"view": "back", "business_id": "NG-0001"},
                        {"view": "gameplay", "business_id": "GM-0001"},
                    ],
                    "requirement_ids": ["REQ-REWARD-1"],
                    "flow_ids": ["flow-reward"],
                    "part_kinds": ["domain_rules", "csharp_adapter", "binding"],
                    "roles": ["producer"],
                    "obligation_ids": ["obl-reward-1"],
                },
                {
                    "task_id": 2,
                    "view_refs": [{"view": "back", "business_id": "NG-0002"}],
                    "requirement_ids": ["REQ-AUDIT-1"],
                    "flow_ids": [],
                    "part_kinds": ["domain_rules"],
                    "roles": ["integration_only_owner"],
                    "obligation_ids": ["obl-audit-1"],
                },
                {
                    "task_id": 3,
                    "view_refs": [{"view": "back", "business_id": "NG-0003"}],
                    "requirement_ids": ["REQ-DEFER-1"],
                    "flow_ids": [],
                    "part_kinds": ["domain_rules"],
                    "roles": ["consumer"],
                    "obligation_ids": [],
                },
            ],
            obligations=[
                {
                    "id": "obl-reward-1",
                    "requirement_ids": ["REQ-REWARD-1"],
                    "flow_ids": ["flow-reward"],
                    "test_ids": ["test-reward-1"],
                    "responsibility": "Verify reward flow.",
                    "verification_refs": [],
                },
                {
                    "id": "obl-audit-1",
                    "requirement_ids": ["REQ-AUDIT-1"],
                    "flow_ids": [],
                    "test_ids": ["test-audit-1"],
                    "responsibility": "Run static audit verification.",
                    "verification_refs": [src["other_v_owned"]],
                },
            ],
            other_verification_refs=[src["other_v_owned"]],
        )
        binding_a_raw = builder.put_json(binding_a_path, binding_a)
        binding_a_ref = _typed_ref(binding_a_path, "newrouge.b-route-binding.v1", "plan-reward", 1, binding_a_raw)

        plans = [(plan_a_path, plan_a)]
        bindings = [(binding_a_path, binding_a)]
        scope_map = {"scope-reward": ([plan_a_path], [binding_a_path])}
        t1_plan_refs = [plan_a_ref]
        t1_binding_refs = [binding_a_ref]

        if two_plans:
            plan_b_path = "docs/planning/b-route/plans/plan-combat/1.json"
            plan_b = _build_plan_doc(
                plan_id="plan-combat",
                revision=1,
                source_manifest_ref=src["manifest_ref"],
                source_ledger_ref=src["ledger_ref"],
                source_revision=src["source_revision"],
                source_manifest_digest=src["source_manifest_digest"],
                proof_ref=src["proof_ref"],
                requirements=[
                    {
                        "requirement_id": "REQ-COMBAT-1",
                        "source_block_ids": ["BLK-COMBAT-1"],
                        "acceptance_intent": "Combat victory enters reward state.",
                        "non_task_sinks": [],
                    }
                ],
                flows=[_make_flow("flow-combat", ["REQ-COMBAT-1"], state_uses=[
                    {"kind": "state", "definition_id": "state-reward", "owner_plan_id": "plan-reward", "owner_revision": 1}
                ])],
                commands=[],
                states=[],
                logical_references=[
                    {"kind": "flow", "definition_id": "flow-reward", "owner_plan_id": "plan-reward", "owner_revision": 1}
                ],
                requirement_verification=[
                    {
                        "requirement_id": "REQ-COMBAT-1",
                        "disposition": "flow",
                        "flow_id": "flow-combat",
                        "rationale": "Verified by combat flow.",
                        "sink_id": None,
                        "verification_ref": None,
                        "authority_ref": None,
                        "evidence_ids": [],
                    }
                ],
                requirement_route_memberships=[{"requirement_id": "REQ-COMBAT-1", "flow_id": "flow-combat", "observable_role": "primary"}],
                requirement_evidence=[],
                evidence_source_refs=[],
            )
            plan_b_raw = builder.put_json(plan_b_path, plan_b)
            plan_b_ref = _typed_ref(plan_b_path, "newrouge.b-route-plan.v1", "plan-combat", 1, plan_b_raw)

            binding_b_path = "docs/planning/b-route/bindings/plan-combat/1.json"
            binding_b = _build_binding_doc(
                plan_id="plan-combat",
                binding_revision=1,
                plan_ref=plan_b_ref,
                stage="3C",
                task_mappings=[
                    {
                        "task_id": 1,
                        "view_refs": [{"view": "back", "business_id": "NG-0001"}],
                        "requirement_ids": ["REQ-COMBAT-1"],
                        "flow_ids": ["flow-combat"],
                        "part_kinds": ["domain_rules"],
                        "roles": ["consumer"],
                        "obligation_ids": ["obl-combat-1"],
                    }
                ],
                obligations=[
                    {
                        "id": "obl-combat-1",
                        "requirement_ids": ["REQ-COMBAT-1"],
                        "flow_ids": ["flow-combat"],
                        "test_ids": ["test-combat-1"],
                        "responsibility": "Verify combat handoff to reward.",
                        "verification_refs": [],
                    }
                ],
            )
            binding_b_raw = builder.put_json(binding_b_path, binding_b)
            binding_b_ref = _typed_ref(binding_b_path, "newrouge.b-route-binding.v1", "plan-combat", 1, binding_b_raw)
            plans.append((plan_b_path, plan_b))
            bindings.append((binding_b_path, binding_b))
            scope_map["scope-combat"] = ([plan_b_path], [binding_b_path])
            t1_plan_refs.append(plan_b_ref)
            t1_binding_refs.append(binding_b_ref)

        origins_tasks = [
            {"task_id": 1, "source_refs": [src["source_owned"]], "plan_refs": t1_plan_refs, "binding_refs": t1_binding_refs},
            {"task_id": 2, "source_refs": [src["source_owned"]], "plan_refs": [plan_a_ref], "binding_refs": [binding_a_ref]},
            {"task_id": 3, "source_refs": [src["source_owned"]], "plan_refs": [plan_a_ref], "binding_refs": [binding_a_ref]},
        ]
        authority_pins = [
            (src["manifest_rel"], src["manifest_raw"]),
            (src["ledger_rel"], src["ledger_raw"]),
            (src["proof_rel"], src["proof_raw"]),
        ]
        committed = builder.commit_bundle(
            operation_id="op-commit-001",
            plans=plans,
            bindings=bindings,
            origins_tasks=origins_tasks,
            authority_pins=authority_pins,
            scope_map=scope_map,
        )
        return {"builder": builder, "src": src, "committed": committed}

    # --- Matrix Row 1: B_MULTI ---
    def test_b_multi_single_and_multi_plan_changes_applicable_set_digest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
            root1, root2 = Path(tmp1), Path(tmp2)
            self._make_single_and_multi_plan_repo(root1, two_plans=False)
            self._make_single_and_multi_plan_repo(root2, two_plans=True)

            with patch.object(op_scope, "initialize_lock_namespace", side_effect=AssertionError("lock init forbidden")):
                res1 = resolver.resolve_task_origin(root1, 1)
                res2 = resolver.resolve_task_origin(root2, 1)

            self._assert_non_auth(res1)
            self._assert_non_auth(res2)
            self.assertTrue(res1["ok"] and res1["stable"])
            self.assertEqual(res1["route"], "B")
            self.assertEqual([r["entity_id"] for r in res1["plan_refs"]], ["plan-reward"])
            self.assertEqual(res1["applicable_flow_closure"], ["flow-reward"])
            self.assertIs(res1["non_flow_summary"]["downstream_definition_check_required"], False)
            self.assertIs(res1["non_flow_summary"]["downstream_impact_check_required"], False)
            self.assertTrue(res1["applicable_set_digest"].startswith("sha256:"))

            self.assertTrue(res2["ok"] and res2["stable"])
            self.assertEqual(res2["route"], "B")
            self.assertEqual([r["entity_id"] for r in res2["plan_refs"]], ["plan-combat", "plan-reward"])
            self.assertEqual([r["entity_id"] for r in res2["binding_refs"]], ["plan-combat", "plan-reward"])
            self.assertEqual(res2["applicable_flow_closure"], ["flow-combat", "flow-reward"])
            self.assertEqual(res2["applicable_requirements"], ["REQ-COMBAT-1", "REQ-REWARD-1"])
            self.assertEqual(len(res2["dispositions"]), 2)
            self.assertNotEqual(res1["applicable_set_digest"], res2["applicable_set_digest"])

    def test_b_multi_blocks_missing_origin_row_tampered_policy_and_stripped_b_ownership(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._make_single_and_multi_plan_repo(root, two_plans=True)
            builder = ctx["builder"]

            # Case A: Remove Task 1 from origins.tasks while catalog/binding still map it -> MAPPING_MISMATCH or DIGEST_MISMATCH.
            origins = builder.read_json(resolver.ORIGINS_PATH)
            orig_bytes = (root / resolver.ORIGINS_PATH).read_bytes()
            origins["tasks"] = [r for r in origins["tasks"] if r["task_id"] != 1]
            builder.put_json(resolver.ORIGINS_PATH, origins)
            res = resolver.resolve_task_origin(root, 1)
            self._assert_non_auth(res)
            self.assertFalse(res["ok"])
            self.assertEqual(res["route"], "blocked")
            self.assertIn(res["diagnostics"][0]["reason_code"], ("digest_mismatch", "mapping_mismatch"))
            builder.put(resolver.ORIGINS_PATH, orig_bytes)

            # Case B: Tamper policy.v1.json directly -> DIGEST_MISMATCH (never falls back to A).
            policy = builder.read_json(resolver.POLICY_PATH)
            pol_bytes = (root / resolver.POLICY_PATH).read_bytes()
            policy["switch_boundary"]["allowed_a_operations"].append("tampered")
            builder.put_json(resolver.POLICY_PATH, policy)
            res_pol = resolver.resolve_task_origin(root, 1)
            self._assert_non_auth(res_pol)
            self.assertFalse(res_pol["ok"])
            self.assertEqual(res_pol["route"], "blocked")
            self.assertEqual(res_pol["diagnostics"][0]["reason_code"], "digest_mismatch")
            builder.put(resolver.POLICY_PATH, pol_bytes)

            # Case C: Re-commit with Task 1 stripped from origins/catalog/bindings, leaving residual B ref in tasks_back.json.
            back = builder.read_json(resolver.TRIPLET["back"])
            back[0]["source_refs"] = ["docs/planning/b-route/plans/plan-reward/1.json"]
            builder.put_json(resolver.TRIPLET["back"], back)
            b_doc = builder.read_json("docs/planning/b-route/bindings/plan-reward/1.json")
            b_doc["task_mappings"] = [r for r in b_doc["task_mappings"] if r["task_id"] != 1]
            p_doc = builder.read_json("docs/planning/b-route/plans/plan-reward/1.json")
            p_raw = (root / "docs/planning/b-route/plans/plan-reward/1.json").read_bytes()
            p_ref = _typed_ref("docs/planning/b-route/plans/plan-reward/1.json", "newrouge.b-route-plan.v1", "plan-reward", 1, p_raw)
            b_raw = builder.put_json("docs/planning/b-route/bindings/plan-reward/1.json", b_doc)
            b_ref = _typed_ref("docs/planning/b-route/bindings/plan-reward/1.json", "newrouge.b-route-binding.v1", "plan-reward", 1, b_raw)
            src = ctx["src"]
            builder.commit_bundle(
                operation_id="op-strip-002",
                plans=[("docs/planning/b-route/plans/plan-reward/1.json", p_doc)],
                bindings=[("docs/planning/b-route/bindings/plan-reward/1.json", b_doc)],
                origins_tasks=[
                    {"task_id": 2, "source_refs": [src["source_owned"]], "plan_refs": [p_ref], "binding_refs": [b_ref]},
                    {"task_id": 3, "source_refs": [src["source_owned"]], "plan_refs": [p_ref], "binding_refs": [b_ref]},
                ],
                authority_pins=[
                    (src["manifest_rel"], src["manifest_raw"]),
                    (src["ledger_rel"], src["ledger_raw"]),
                    (src["proof_rel"], src["proof_raw"]),
                ],
                scope_map={"scope-reward": (["docs/planning/b-route/plans/plan-reward/1.json"], ["docs/planning/b-route/bindings/plan-reward/1.json"])},
                catalog_revision=2,
            )
            res_strip = resolver.resolve_task_origin(root, 1)
            self._assert_non_auth(res_strip)
            self.assertFalse(res_strip["ok"])
            self.assertEqual(res_strip["route"], "blocked")
            self.assertEqual(res_strip["route_required"], "B")
            self.assertEqual(res_strip["diagnostics"][0]["reason_code"], "mapping_mismatch")

    # --- Matrix Row 2: FROZEN_A ---
    def _make_frozen_a_repo(self) -> tuple[object, ResolverRepoBuilder, dict]:
        inv_mod = importlib.import_module("test_b_route_inventory")
        inv_fixture = inv_mod.InventoryTests(methodName="runTest")
        inv_fixture.setUp()
        self.addCleanup(inv_fixture.tearDown)
        root = inv_fixture.root
        epics = inv_fixture.epics

        # Add a subtask on Task 1 so we can verify subtasks[].status progress is allowed.
        master = inv_fixture.load(resolver.TRIPLET["master"])
        master["master"]["tasks"][0]["subtasks"] = [
            {"id": "1.1", "title": "Subtask A", "status": "pending"}
        ]
        inv_fixture.dump(resolver.TRIPLET["master"], master)

        # Capture a genuine Story 1.5 protection snapshot under logs/ci/...
        capture = protection.collect_protection(root, epics)
        self.assertTrue(capture.snapshot["stable"], capture.snapshot["diagnostics"])
        snap_dir = root / "logs/ci/2026-11-23/b-route-protection/frozen-baseline"
        snap_dir.mkdir(parents=True, exist_ok=False)
        protection.write_capture(snap_dir, capture)
        snap_rel = "logs/ci/2026-11-23/b-route-protection/frozen-baseline/snapshot.json"
        snap_raw = (root / snap_rel).read_bytes()

        # Also create chapter3-task-scope.json locking frozen Task IDs.
        frozen_ids = sorted(t["id"] for t in master["master"]["tasks"])
        scope_doc = {
            "schema_version": "chapter3.task-scope.v1",
            "mode": "reconcile-existing-only",
            "master_path": resolver.TRIPLET["master"],
            "expected_master_task_count": len(frozen_ids),
            "allowed_numeric_task_ids": frozen_ids,
        }
        builder = ResolverRepoBuilder(root)
        scope_raw = builder.put_json(resolver.CHAPTER3_TASK_SCOPE, scope_doc)

        # Create one B-route plan/binding on a new Task (e.g. Task 99) so B governance is active and published.
        next_tid = max(frozen_ids) + 1
        master["master"]["tasks"].append({"id": next_tid, "title": "New B Task", "status": "pending", "dependencies": []})
        back = inv_fixture.load(resolver.TRIPLET["back"])
        back.append({"id": f"NG-{next_tid:04d}", "taskmaster_id": next_tid, "title": "New B Task", "status": "pending"})
        inv_fixture.dump(resolver.TRIPLET["master"], master)
        inv_fixture.dump(resolver.TRIPLET["back"], back)

        src = builder.write_sources_and_proof(use_log_proof=True)
        plan_path = "docs/planning/b-route/plans/plan-b/1.json"
        plan_doc = _build_plan_doc(
            plan_id="plan-b",
            revision=1,
            source_manifest_ref=src["manifest_ref"],
            source_ledger_ref=src["ledger_ref"],
            source_revision=src["source_revision"],
            source_manifest_digest=src["source_manifest_digest"],
            proof_ref=src["proof_ref"],
            requirements=[
                {
                    "requirement_id": "REQ-B-1",
                    "source_block_ids": ["BLK-REWARD-1"],
                    "acceptance_intent": "B task requirement.",
                    "non_task_sinks": [],
                }
            ],
            flows=[_make_flow("flow-b", ["REQ-B-1"])],
            commands=[],
            states=[],
            logical_references=[],
            requirement_verification=[
                {
                    "requirement_id": "REQ-B-1",
                    "disposition": "flow",
                    "flow_id": "flow-b",
                    "rationale": "B flow.",
                    "sink_id": None,
                    "verification_ref": None,
                    "authority_ref": None,
                    "evidence_ids": [],
                }
            ],
            requirement_route_memberships=[{"requirement_id": "REQ-B-1", "flow_id": "flow-b", "observable_role": "primary"}],
            requirement_evidence=[],
            evidence_source_refs=[],
        )
        plan_raw = builder.put_json(plan_path, plan_doc)
        plan_ref = _typed_ref(plan_path, "newrouge.b-route-plan.v1", "plan-b", 1, plan_raw)

        binding_path = "docs/planning/b-route/bindings/plan-b/1.json"
        binding_doc = _build_binding_doc(
            plan_id="plan-b",
            binding_revision=1,
            plan_ref=plan_ref,
            stage="3C",
            task_mappings=[
                {
                    "task_id": next_tid,
                    "view_refs": [{"view": "back", "business_id": f"NG-{next_tid:04d}"}],
                    "requirement_ids": ["REQ-B-1"],
                    "flow_ids": ["flow-b"],
                    "part_kinds": ["domain_rules"],
                    "roles": ["producer"],
                    "obligation_ids": [],
                }
            ],
            obligations=[],
        )
        binding_raw = builder.put_json(binding_path, binding_doc)
        binding_ref = _typed_ref(binding_path, "newrouge.b-route-binding.v1", "plan-b", 1, binding_raw)

        frozen_a_refs = [
            _owned_ref("frozen_a_inventory", snap_rel, [(snap_rel, snap_raw)]),
            _owned_ref("authority", resolver.CHAPTER3_TASK_SCOPE, [(resolver.CHAPTER3_TASK_SCOPE, scope_raw)]),
        ]
        authority_pins = [
            (src["manifest_rel"], src["manifest_raw"]),
            (src["ledger_rel"], src["ledger_raw"]),
            (src["proof_rel"], src["proof_raw"]),
            (snap_rel, snap_raw),
        ]
        builder.commit_bundle(
            operation_id="op-frozen-a-001",
            plans=[(plan_path, plan_doc)],
            bindings=[(binding_path, binding_doc)],
            origins_tasks=[
                {
                    "task_id": next_tid,
                    "source_refs": [src["source_owned"]],
                    "plan_refs": [plan_ref],
                    "binding_refs": [binding_ref],
                }
            ],
            frozen_a_refs=frozen_a_refs,
            allowed_a_operations=["implement", "resume", "route"],
            a_write_allowed=True,
            authority_pins=authority_pins,
            scope_map={"scope-b": ([plan_path], [binding_path])},
        )
        return inv_fixture, builder, {
            "frozen_tid": frozen_ids[0],
            "b_tid": next_tid,
            "snap_rel": snap_rel,
            "src": src,
            "frozen_a_refs": frozen_a_refs,
        }

    def test_frozen_a_passes_with_live_status_progress_and_blocks_drift_done_new_and_forbidden_op(self) -> None:
        inv_fixture, builder, info = self._make_frozen_a_repo()
        root = inv_fixture.root
        frozen_tid = info["frozen_tid"]

        # 1. Exact frozen A match with allowed operation -> route="A"
        with patch.object(op_scope, "initialize_lock_namespace", side_effect=AssertionError("lock init forbidden")):
            res = resolver.resolve_task_origin(root, frozen_tid, operation="implement")
        self._assert_non_auth(res)
        self.assertTrue(res["ok"] and res["stable"])
        self.assertEqual(res["route"], "A")
        self.assertIsNone(res["applicable_set_digest"])
        self.assertTrue(res["frozen_a_boundary"]["verified"])
        self.assertTrue(res["frozen_a_boundary"]["projection_verified"])
        self.assertTrue(res["frozen_a_boundary"]["source_scope_verified"])

        # 2. Live status + subtasks[].status progress -> still route="A"
        master = inv_fixture.load(resolver.TRIPLET["master"])
        t0 = next(t for t in master["master"]["tasks"] if t["id"] == frozen_tid)
        t0["status"] = "done"
        t0["subtasks"][0]["status"] = "done"
        inv_fixture.dump(resolver.TRIPLET["master"], master)
        res_done = resolver.resolve_task_origin(root, frozen_tid, operation="resume")
        self._assert_non_auth(res_done)
        self.assertTrue(res_done["ok"])
        self.assertEqual(res_done["route"], "A")

        # 3. Forbidden operation not in allowed_a_operations -> blocked (route_required="B")
        res_forbid = resolver.resolve_task_origin(root, frozen_tid, operation="replan")
        self._assert_non_auth(res_forbid)
        self.assertFalse(res_forbid["ok"])
        self.assertEqual(res_forbid["route"], "blocked")
        self.assertEqual(res_forbid["route_required"], "B")
        self.assertEqual(res_forbid["diagnostics"][0]["reason_code"], "conflict")

        # 4. Done does NOT exempt definition drift -> blocked (INPUT_STALE, route_required="B")
        orig_master_bytes = (root / resolver.TRIPLET["master"]).read_bytes()
        t0["title"] = "Drifted title after done"
        inv_fixture.dump(resolver.TRIPLET["master"], master)
        res_drift = resolver.resolve_task_origin(root, frozen_tid, operation="implement")
        self._assert_non_auth(res_drift)
        self.assertFalse(res_drift["ok"])
        self.assertEqual(res_drift["route"], "blocked")
        self.assertEqual(res_drift["route_required"], "B")
        self.assertEqual(res_drift["diagnostics"][0]["reason_code"], "input_stale")
        builder.put(resolver.TRIPLET["master"], orig_master_bytes)

        # 5. Source scope drift -> blocked (INPUT_STALE, route_required="B")
        snap_doc = builder.read_json(info["snap_rel"])
        cand = next(c for c in snap_doc["frozen_a"]["candidates"] if c["task_id"] == frozen_tid)
        src_rel = cand["source_scope"]["task_source_references"][0]["path"]
        orig_src_bytes = (root / src_rel).read_bytes()
        builder.put(src_rel, orig_src_bytes + b"\n# Drift\n")
        res_src_drift = resolver.resolve_task_origin(root, frozen_tid, operation="implement")
        self._assert_non_auth(res_src_drift)
        self.assertFalse(res_src_drift["ok"])
        self.assertEqual(res_src_drift["route"], "blocked")
        self.assertEqual(res_src_drift["route_required"], "B")
        self.assertEqual(res_src_drift["diagnostics"][0]["reason_code"], "input_stale")
        builder.put(src_rel, orig_src_bytes)

        # 6. Newly added Task not in frozen snapshot/chapter3-task-scope and not in B -> blocked (must use B)
        new_tid = info["b_tid"] + 1
        master = inv_fixture.load(resolver.TRIPLET["master"])
        back = inv_fixture.load(resolver.TRIPLET["back"])
        master["master"]["tasks"].append({"id": new_tid, "title": "Unregistered Task", "status": "pending", "dependencies": []})
        back.append({"id": f"NG-{new_tid:04d}", "taskmaster_id": new_tid, "title": "Unregistered Task", "status": "pending"})
        inv_fixture.dump(resolver.TRIPLET["master"], master)
        inv_fixture.dump(resolver.TRIPLET["back"], back)
        res_new = resolver.resolve_task_origin(root, new_tid, operation="implement")
        self._assert_non_auth(res_new)
        self.assertFalse(res_new["ok"])
        self.assertEqual(res_new["route"], "blocked")
        self.assertEqual(res_new["route_required"], "B")
        self.assertEqual(res_new["diagnostics"][0]["reason_code"], "mapping_mismatch")

    # --- Matrix Row 3: CLONE_PEND ---
    def test_clone_without_logs_passes_b_zero_writes_and_blocks_candidate_a_missing_archive(self) -> None:
        inv_fixture, _builder, info = self._make_frozen_a_repo()
        src_root = inv_fixture.root
        with tempfile.TemporaryDirectory() as clone_tmp:
            clone_root = Path(clone_tmp) / "clean-clone"
            # Materialize clean clone WITHOUT logs/ and WITHOUT .git/
            for rel_dir in (".taskmaster", "docs"):
                if (src_root / rel_dir).exists():
                    shutil.copytree(src_root / rel_dir, clone_root / rel_dir)
            self.assertFalse((clone_root / "logs").exists())

            with patch.object(op_scope, "initialize_lock_namespace", side_effect=AssertionError("lock init forbidden")):
                res_b = resolver.resolve_task_origin(clone_root, info["b_tid"])
            self._assert_non_auth(res_b)
            self.assertTrue(res_b["ok"] and res_b["stable"])
            self.assertEqual(res_b["route"], "B")
            self.assertFalse((clone_root / "logs").exists(), "Zero-write query must never create logs/ in clean clone")

            with patch.object(op_scope, "initialize_lock_namespace", side_effect=AssertionError("lock init forbidden")):
                res_a = resolver.resolve_task_origin(clone_root, info["frozen_tid"], operation="implement")
            self._assert_non_auth(res_a)
            self.assertFalse(res_a["ok"])
            self.assertEqual(res_a["route"], "blocked")
            self.assertEqual(res_a["route_required"], "B")
            self.assertEqual(res_a["diagnostics"][0]["reason_code"], "file_not_found")
            self.assertFalse((clone_root / "logs").exists(), "Blocked query must also create zero directories")

    def test_frozen_a_write_disallowed_and_protection_input_in_policy(self) -> None:
        inv_fixture, builder, info = self._make_frozen_a_repo()
        root = inv_fixture.root
        frozen_tid = info["frozen_tid"]
        snap_rel = info["snap_rel"]
        snap_raw = (root / snap_rel).read_bytes()
        inv_rel = snap_rel.rsplit("/", 1)[0] + "/inventory.json"
        inv_raw = (root / inv_rel).read_bytes()

        # Build a valid protection-input (newrouge.b-route-protection-input.v1) and Markdown authority ref.
        prot_input_rel = "docs/planning/b-route/protection-input-test.v1.json"
        prot_input_doc = {
            "document_version": "newrouge.b-route-protection-input.v1",
            "input_id": "test-protection-input",
            "revision": 1,
            "definition": {
                "projection_codec": codec.PROJECTION_CODEC,
                "content_codec": codec.CODEC_VERSION,
                "mutable_allowlist": ["Task.status", "Task.subtasks[].status"],
            },
            "inventory_ref": _owned_ref("frozen_a_inventory", inv_rel, [(inv_rel, inv_raw)]),
            "snapshot_ref": _owned_ref("frozen_a_inventory", snap_rel, [(snap_rel, snap_raw)]),
            "authorization": dict(protection.AUTHORIZATION),
        }
        prot_input_raw = builder.put_json(prot_input_rel, prot_input_doc)
        adr_rel = resolver.ADR_0040
        adr_raw = (root / adr_rel).read_bytes()
        scope_raw = (root / resolver.CHAPTER3_TASK_SCOPE).read_bytes()

        plan_path = "docs/planning/b-route/plans/plan-b/1.json"
        binding_path = "docs/planning/b-route/bindings/plan-b/1.json"
        plan_doc = builder.read_json(plan_path)
        binding_doc = builder.read_json(binding_path)
        plan_raw = (root / plan_path).read_bytes()
        binding_raw = (root / binding_path).read_bytes()
        plan_ref = _typed_ref(plan_path, "newrouge.b-route-plan.v1", "plan-b", 1, plan_raw)
        binding_ref = _typed_ref(binding_path, "newrouge.b-route-binding.v1", "plan-b", 1, binding_raw)
        src = info["src"]

        frozen_a_refs = [
            _owned_ref("frozen_a_inventory", prot_input_rel, [(prot_input_rel, prot_input_raw)]),
            _owned_ref("authority", resolver.CHAPTER3_TASK_SCOPE, [(resolver.CHAPTER3_TASK_SCOPE, scope_raw)]),
            _owned_ref("authority", adr_rel, [(adr_rel, adr_raw)]),
        ]
        authority_pins = [
            (src["manifest_rel"], src["manifest_raw"]),
            (src["ledger_rel"], src["ledger_raw"]),
            (src["proof_rel"], src["proof_raw"]),
            (snap_rel, snap_raw),
        ]
        builder.commit_bundle(
            operation_id="op-frozen-a-prot-input-002",
            plans=[(plan_path, plan_doc)],
            bindings=[(binding_path, binding_doc)],
            origins_tasks=[
                {
                    "task_id": info["b_tid"],
                    "source_refs": [src["source_owned"]],
                    "plan_refs": [plan_ref],
                    "binding_refs": [binding_ref],
                }
            ],
            frozen_a_refs=frozen_a_refs,
            allowed_a_operations=["implement", "inspect", "read"],
            a_write_allowed=False,
            authority_pins=authority_pins,
            scope_map={"scope-b": ([plan_path], [binding_path])},
            catalog_revision=2,
        )

        # a_write_allowed=False blocks write operation "implement" with conflict + route_required="B".
        res_write = resolver.resolve_task_origin(root, frozen_tid, operation="implement")
        self._assert_non_auth(res_write)
        self.assertFalse(res_write["ok"])
        self.assertEqual(res_write["route"], "blocked")
        self.assertEqual(res_write["route_required"], "B")
        self.assertEqual(res_write["diagnostics"][0]["reason_code"], "conflict")

        # Read-only operation "inspect" passes via protection-input + Markdown authority ref -> route="A".
        res_read = resolver.resolve_task_origin(root, frozen_tid, operation="inspect")
        self._assert_non_auth(res_read)
        self.assertTrue(res_read["ok"] and res_read["stable"])
        self.assertEqual(res_read["route"], "A")
        self.assertTrue(res_read["frozen_a_boundary"]["verified"])
        kinds = [row["kind"] for row in res_read["frozen_a_boundary"]["matched_frozen_refs"]]
        self.assertIn("protection_input", kinds)
        self.assertIn("authority", kinds)

    def test_pending_blocks_legacy_commit_intent_and_overlapping_scopes_but_allows_disjoint_prepared(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_single_and_multi_plan_repo(root, two_plans=False)

            # 1. Unapplied prepared operation on a DISJOINT business scope (even sharing file:<tasks.json>) -> ALLOWED!
            disjoint_scopes = list(
                op_scope.resource_scopes(
                    target_paths=[resolver.TRIPLET["master"], resolver.ORIGINS_PATH],
                    task_ids=[999],
                    plan_ids=["unrelated-plan"],
                    flow_ids=["unrelated-flow"],
                    requirement_ids=["REQ-UNRELATED"],
                    command_ids=["cmd-unrelated"],
                    state_ids=["state-unrelated"],
                )
            )
            _create_unapplied_operation(root, operation_id="op-disjoint-prep", scope_ids=disjoint_scopes, state="prepared")
            res_ok = resolver.resolve_task_origin(root, 1)
            self._assert_non_auth(res_ok)
            self.assertTrue(res_ok["ok"] and res_ok["stable"])
            self.assertEqual(res_ok["route"], "B")
            self.assertEqual(len(res_ok["pending_summary"]["non_overlapping_unapplied_operations"]), 1)

            # 2. Unapplied reserved operation on OVERLAPPING flow/state/requirement/plan scope -> BLOCKED (PENDING)!
            for label, kwargs in (
                ("overlap-flow", {"flow_ids": ["flow-reward"]}),
                ("overlap-plan", {"plan_ids": ["plan-reward"]}),
                ("overlap-req", {"requirement_ids": ["REQ-REWARD-1"]}),
                ("overlap-state", {"state_ids": ["state-reward"]}),
                ("overlap-cmd", {"command_ids": ["cmd-pick-reward"]}),
                ("overlap-task", {"task_ids": [1]}),
            ):
                with self.subTest(case=label), tempfile.TemporaryDirectory() as sub_tmp:
                    sroot = Path(sub_tmp)
                    self._make_single_and_multi_plan_repo(sroot, two_plans=False)
                    _create_unapplied_operation(
                        sroot,
                        operation_id=f"op-{label}",
                        scope_ids=list(op_scope.resource_scopes(**kwargs)),
                        state="reserved",
                    )
                    res_ov = resolver.resolve_task_origin(sroot, 1)
                    self._assert_non_auth(res_ov)
                    self.assertFalse(res_ov["ok"])
                    self.assertEqual(res_ov["route"], "blocked")
                    self.assertEqual(res_ov["diagnostics"][0]["reason_code"], "pending")

            # 3. Active op that entered commit.json (mixed/in-flight apply) even on disjoint business scope -> CONSERVATIVE BLOCK!
            with tempfile.TemporaryDirectory() as sub_tmp:
                sroot = Path(sub_tmp)
                self._make_single_and_multi_plan_repo(sroot, two_plans=False)
                _create_unapplied_operation(
                    sroot,
                    operation_id="op-inflight-commit",
                    scope_ids=disjoint_scopes,
                    state="reserved",
                    write_commit_intent=True,
                )
                res_ci = resolver.resolve_task_origin(sroot, 1)
                self._assert_non_auth(res_ci)
                self.assertFalse(res_ci["ok"])
                self.assertEqual(res_ci["route"], "blocked")
                self.assertIn(res_ci["diagnostics"][0]["reason_code"], ("pending", "unpublished"))

            # 4. Active op with commit.pending.json -> CONSERVATIVE BLOCK (PENDING)!
            with tempfile.TemporaryDirectory() as sub_tmp:
                sroot = Path(sub_tmp)
                self._make_single_and_multi_plan_repo(sroot, two_plans=False)
                _create_unapplied_operation(
                    sroot,
                    operation_id="op-inflight-pending",
                    scope_ids=disjoint_scopes,
                    state="reserved",
                    write_commit_pending=True,
                )
                res_cp = resolver.resolve_task_origin(sroot, 1)
                self._assert_non_auth(res_cp)
                self.assertFalse(res_cp["ok"])
                self.assertEqual(res_cp["route"], "blocked")
                self.assertEqual(res_cp["diagnostics"][0]["reason_code"], "pending")

            # 5. Unknown/file-only scope on unapplied prepared op -> BLOCKED (PENDING)!
            with tempfile.TemporaryDirectory() as sub_tmp:
                sroot = Path(sub_tmp)
                self._make_single_and_multi_plan_repo(sroot, two_plans=False)
                _create_unapplied_operation(
                    sroot,
                    operation_id="op-file-only",
                    scope_ids=list(op_scope.resource_scopes(target_paths=[resolver.TRIPLET["master"]])),
                    state="prepared",
                )
                res_unk = resolver.resolve_task_origin(sroot, 1)
                self._assert_non_auth(res_unk)
                self.assertFalse(res_unk["ok"])
                self.assertEqual(res_unk["diagnostics"][0]["reason_code"], "pending")

            # 6. Legacy capability-apply.pending.json -> CONSERVATIVE BLOCK (PENDING)!
            with tempfile.TemporaryDirectory() as sub_tmp:
                sroot = Path(sub_tmp)
                self._make_single_and_multi_plan_repo(sroot, two_plans=False)
                b = ResolverRepoBuilder(sroot)
                target_payload = {"schema_version": "cap.v1"}
                target_raw = _encoded(target_payload)
                jrel = "logs/ci/capability-planning/run-old/apply-journal.json"
                b.put_json(
                    jrel,
                    {
                        "schema_version": "newrouge.planning-apply-journal.v1",
                        "status": "pending",
                        "authority_inputs": {},
                        "entries": [
                            {
                                "path": "docs/planning/semantic-topology/capabilities.v1.json",
                                "before_sha256": None,
                                "before_base64": None,
                                "after_sha256": codec.raw_digest(target_raw),
                                "payload": target_payload,
                            }
                        ],
                        "result": {"status": "pending"},
                    },
                )
                b.put_json(resolver.CAP_PENDING, {"run_id": "run-old", "journal_path": jrel})
                res_leg = resolver.resolve_task_origin(sroot, 1)
                self._assert_non_auth(res_leg)
                self.assertFalse(res_leg["ok"])
                self.assertEqual(res_leg["route"], "blocked")
                self.assertEqual(res_leg["diagnostics"][0]["reason_code"], "pending")

    # --- Matrix Row 4: NOT_EN ---
    def test_not_enabled_returns_explicit_not_enabled_a_and_blocks_partial_trace_or_invalid_adr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            b = ResolverRepoBuilder(root)
            b.write_adr_0040(valid=True)
            b.write_triplet(
                master_tasks=[{"id": 1, "title": "Legacy Task", "status": "pending", "dependencies": []}],
                back_tasks=[{"id": "NG-0001", "taskmaster_id": 1, "title": "Legacy Task", "status": "pending"}],
                gameplay_tasks=[],
            )
            # 1. Zero B traces + valid ADR-0040 -> explicit_not_enabled_a with zero writes
            with patch.object(op_scope, "initialize_lock_namespace", side_effect=AssertionError("lock init forbidden")):
                res = resolver.resolve_task_origin(root, 1)
            self._assert_non_auth(res)
            self.assertTrue(res["ok"] and res["stable"])
            self.assertEqual(res["route"], "explicit_not_enabled_a")
            self.assertEqual(res["authority_ref"], resolver.ADR_0040)
            self.assertIsNone(res["applicable_set_digest"])
            self.assertFalse((root / "logs").exists())

            # 2. Invalid/superseded ADR-0040 with zero B traces -> BLOCKED
            b.write_adr_0040(valid=False)
            res_bad_adr = resolver.resolve_task_origin(root, 1)
            self._assert_non_auth(res_bad_adr)
            self.assertFalse(res_bad_adr["ok"])
            self.assertEqual(res_bad_adr["route"], "blocked")
            self.assertEqual(res_bad_adr["diagnostics"][0]["reason_code"], "identity_unprovable")

            # 3. Missing governance while a stray B trace exists -> REQUIRED_GOVERNANCE_MISSING
            b.write_adr_0040(valid=True)
            b.put_json("docs/planning/b-route/plans/stray/1.json", {"stray": True})
            res_trace = resolver.resolve_task_origin(root, 1)
            self._assert_non_auth(res_trace)
            self.assertFalse(res_trace["ok"])
            self.assertEqual(res_trace["route"], "blocked")
            self.assertEqual(res_trace["diagnostics"][0]["reason_code"], "required_governance_missing")

    # --- Matrix Row 5: NON_FLOW ---
    def test_non_flow_dispositions_pass_with_downstream_flags_and_deny_free_na_label_exemption(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._make_single_and_multi_plan_repo(root, two_plans=False)
            builder = ctx["builder"]

            # 1. Legitimate non-Flow (other_verification on Task 2, deferred on Task 3)
            res_ov = resolver.resolve_task_origin(root, 2)
            self._assert_non_auth(res_ov)
            self.assertTrue(res_ov["ok"] and res_ov["stable"])
            self.assertEqual(res_ov["route"], "B")
            self.assertEqual(res_ov["applicable_flow_closure"], [])
            self.assertEqual(res_ov["dispositions"][0]["disposition"], "other_verification")
            self.assertTrue(res_ov["non_flow_summary"]["has_non_flow_dispositions"])
            self.assertTrue(res_ov["non_flow_summary"]["downstream_definition_check_required"])
            self.assertTrue(res_ov["non_flow_summary"]["downstream_impact_check_required"])
            self.assertIs(res_ov["non_flow_summary"]["free_label_exemption_allowed"], False)

            res_def = resolver.resolve_task_origin(root, 3)
            self._assert_non_auth(res_def)
            self.assertTrue(res_def["ok"])
            self.assertEqual(res_def["route"], "B")
            self.assertEqual(res_def["applicable_flow_closure"], [])
            self.assertEqual(res_def["dispositions"][0]["disposition"], "deferred")
            self.assertTrue(res_def["non_flow_summary"]["has_non_flow_dispositions"])
            self.assertTrue(res_def["non_flow_summary"]["downstream_definition_check_required"])
            self.assertTrue(res_def["non_flow_summary"]["downstream_impact_check_required"])

            # 2. Free-text N/A labels on Flow Task 1 NEVER exempt Flow disposition!
            back = builder.read_json(resolver.TRIPLET["back"])
            back[0]["labels"] = ["N/A", "mvg:n/a", "non-flow"]
            builder.put_json(resolver.TRIPLET["back"], back)
            res_na = resolver.resolve_task_origin(root, 1)
            self._assert_non_auth(res_na)
            self.assertTrue(res_na["ok"])
            self.assertEqual(res_na["route"], "B")
            self.assertEqual(res_na["dispositions"][0]["disposition"], "flow")
            self.assertEqual(res_na["applicable_flow_closure"], ["flow-reward"])
            self.assertIs(res_na["non_flow_summary"]["free_label_exemption_allowed"], False)
            self.assertTrue(res_na["non_flow_summary"]["detected_non_authoritative_labels"])
            self.assertTrue(res_na["non_flow_summary"]["downstream_definition_check_required"])
            self.assertTrue(res_na["non_flow_summary"]["downstream_impact_check_required"])

            # 3. Missing definition (empty requirement_ids & flow_ids) even with N/A label -> BLOCKED (SEMANTIC_ERROR)
            b_doc = builder.read_json("docs/planning/b-route/bindings/plan-reward/1.json")
            b_doc["task_mappings"][0]["requirement_ids"] = []
            b_doc["task_mappings"][0]["flow_ids"] = []
            b_doc["task_mappings"][0]["obligation_ids"] = []
            p_doc = builder.read_json("docs/planning/b-route/plans/plan-reward/1.json")
            p_raw = (root / "docs/planning/b-route/plans/plan-reward/1.json").read_bytes()
            p_ref = _typed_ref("docs/planning/b-route/plans/plan-reward/1.json", "newrouge.b-route-plan.v1", "plan-reward", 1, p_raw)
            b_raw = builder.put_json("docs/planning/b-route/bindings/plan-reward/1.json", b_doc)
            b_ref = _typed_ref("docs/planning/b-route/bindings/plan-reward/1.json", "newrouge.b-route-binding.v1", "plan-reward", 1, b_raw)
            src = ctx["src"]
            builder.commit_bundle(
                operation_id="op-missing-def-003",
                plans=[("docs/planning/b-route/plans/plan-reward/1.json", p_doc)],
                bindings=[("docs/planning/b-route/bindings/plan-reward/1.json", b_doc)],
                origins_tasks=[
                    {"task_id": 1, "source_refs": [src["source_owned"]], "plan_refs": [p_ref], "binding_refs": [b_ref]},
                    {"task_id": 2, "source_refs": [src["source_owned"]], "plan_refs": [p_ref], "binding_refs": [b_ref]},
                    {"task_id": 3, "source_refs": [src["source_owned"]], "plan_refs": [p_ref], "binding_refs": [b_ref]},
                ],
                authority_pins=[
                    (src["manifest_rel"], src["manifest_raw"]),
                    (src["ledger_rel"], src["ledger_raw"]),
                    (src["proof_rel"], src["proof_raw"]),
                ],
                scope_map={"scope-reward": (["docs/planning/b-route/plans/plan-reward/1.json"], ["docs/planning/b-route/bindings/plan-reward/1.json"])},
                catalog_revision=2,
            )
            res_missing_def = resolver.resolve_task_origin(root, 1)
            self._assert_non_auth(res_missing_def)
            self.assertFalse(res_missing_def["ok"])
            self.assertEqual(res_missing_def["route"], "blocked")
            self.assertEqual(res_missing_def["diagnostics"][0]["reason_code"], "semantic_error")

    def test_multi_flow_plan_scopes_closure_and_pending_and_blocks_source_gap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            builder = ResolverRepoBuilder(root)
            src = builder.write_sources_and_proof(use_log_proof=False)
            builder.write_triplet(
                master_tasks=[
                    {"id": 1, "title": "Flow One Task", "status": "pending", "dependencies": []},
                    {"id": 2, "title": "Flow Two Task", "status": "pending", "dependencies": []},
                    {"id": 3, "title": "Source Gap Task", "status": "pending", "dependencies": []},
                ],
                back_tasks=[
                    {"id": "NG-0001", "taskmaster_id": 1, "title": "Flow One Task", "status": "pending"},
                    {"id": "NG-0002", "taskmaster_id": 2, "title": "Flow Two Task", "status": "pending"},
                    {"id": "NG-0003", "taskmaster_id": 3, "title": "Source Gap Task", "status": "pending"},
                ],
                gameplay_tasks=[],
            )
            plan_path = "docs/planning/b-route/plans/plan-multi-flow/1.json"
            plan_doc = _build_plan_doc(
                plan_id="plan-multi-flow",
                revision=1,
                source_manifest_ref=src["manifest_ref"],
                source_ledger_ref=src["ledger_ref"],
                source_revision=src["source_revision"],
                source_manifest_digest=src["source_manifest_digest"],
                proof_ref=src["proof_ref"],
                requirements=[
                    {
                        "requirement_id": "REQ-F1",
                        "source_block_ids": ["BLK-REWARD-1"],
                        "acceptance_intent": "Flow one behavior.",
                        "non_task_sinks": [],
                    },
                    {
                        "requirement_id": "REQ-F2",
                        "source_block_ids": ["BLK-COMBAT-1"],
                        "acceptance_intent": "Flow two behavior.",
                        "non_task_sinks": [],
                    },
                    {
                        "requirement_id": "REQ-GAP",
                        "source_block_ids": ["BLK-AUDIT-1"],
                        "acceptance_intent": "Unresolved source gap.",
                        "non_task_sinks": [],
                    },
                ],
                flows=[
                    _make_flow("flow-1", ["REQ-F1"]),
                    _make_flow("flow-2", ["REQ-F2"]),
                ],
                commands=[],
                states=[],
                logical_references=[],
                requirement_verification=[
                    {
                        "requirement_id": "REQ-F1",
                        "disposition": "flow",
                        "flow_id": "flow-1",
                        "rationale": "Verified by flow-1.",
                        "sink_id": None,
                        "verification_ref": None,
                        "authority_ref": None,
                        "evidence_ids": [],
                    },
                    {
                        "requirement_id": "REQ-F2",
                        "disposition": "flow",
                        "flow_id": "flow-2",
                        "rationale": "Verified by flow-2.",
                        "sink_id": None,
                        "verification_ref": None,
                        "authority_ref": None,
                        "evidence_ids": [],
                    },
                    {
                        "requirement_id": "REQ-GAP",
                        "disposition": "source_gap",
                        "flow_id": None,
                        "rationale": "Missing source specification.",
                        "sink_id": None,
                        "verification_ref": None,
                        "authority_ref": None,
                        "evidence_ids": [],
                    },
                ],
                requirement_route_memberships=[
                    {"requirement_id": "REQ-F1", "flow_id": "flow-1", "observable_role": "primary"},
                    {"requirement_id": "REQ-F2", "flow_id": "flow-2", "observable_role": "primary"},
                ],
                requirement_evidence=[],
                evidence_source_refs=[],
            )
            plan_raw = builder.put_json(plan_path, plan_doc)
            plan_ref = _typed_ref(plan_path, "newrouge.b-route-plan.v1", "plan-multi-flow", 1, plan_raw)

            binding_path = "docs/planning/b-route/bindings/plan-multi-flow/1.json"
            binding_doc = _build_binding_doc(
                plan_id="plan-multi-flow",
                binding_revision=1,
                plan_ref=plan_ref,
                stage="3C",
                task_mappings=[
                    {
                        "task_id": 1,
                        "view_refs": [{"view": "back", "business_id": "NG-0001"}],
                        "requirement_ids": ["REQ-F1"],
                        "flow_ids": ["flow-1"],
                        "part_kinds": ["domain_rules"],
                        "roles": ["producer"],
                        "obligation_ids": [],
                    },
                    {
                        "task_id": 2,
                        "view_refs": [{"view": "back", "business_id": "NG-0002"}],
                        "requirement_ids": ["REQ-F2"],
                        "flow_ids": ["flow-2"],
                        "part_kinds": ["domain_rules"],
                        "roles": ["producer"],
                        "obligation_ids": [],
                    },
                    {
                        "task_id": 3,
                        "view_refs": [{"view": "back", "business_id": "NG-0003"}],
                        "requirement_ids": ["REQ-GAP"],
                        "flow_ids": [],
                        "part_kinds": ["domain_rules"],
                        "roles": ["consumer"],
                        "obligation_ids": [],
                    },
                ],
                obligations=[],
            )
            binding_raw = builder.put_json(binding_path, binding_doc)
            binding_ref = _typed_ref(binding_path, "newrouge.b-route-binding.v1", "plan-multi-flow", 1, binding_raw)
            builder.commit_bundle(
                operation_id="op-multi-flow-001",
                plans=[(plan_path, plan_doc)],
                bindings=[(binding_path, binding_doc)],
                origins_tasks=[
                    {"task_id": 1, "source_refs": [src["source_owned"]], "plan_refs": [plan_ref], "binding_refs": [binding_ref]},
                    {"task_id": 2, "source_refs": [src["source_owned"]], "plan_refs": [plan_ref], "binding_refs": [binding_ref]},
                    {"task_id": 3, "source_refs": [src["source_owned"]], "plan_refs": [plan_ref], "binding_refs": [binding_ref]},
                ],
                authority_pins=[
                    (src["manifest_rel"], src["manifest_raw"]),
                    (src["ledger_rel"], src["ledger_raw"]),
                    (src["proof_rel"], src["proof_raw"]),
                ],
                scope_map={"scope-mf": ([plan_path], [binding_path])},
            )

            # Task 3 with disposition == "source_gap" blocks with semantic_error.
            res_gap = resolver.resolve_task_origin(root, 3)
            self._assert_non_auth(res_gap)
            self.assertFalse(res_gap["ok"])
            self.assertEqual(res_gap["route"], "blocked")
            self.assertEqual(res_gap["diagnostics"][0]["reason_code"], "semantic_error")

            # Unapplied prepared op on sibling flow-2 does NOT block Task 1 (flow-1 only),
            # but DOES block Task 2 (flow-2)!
            _create_unapplied_operation(
                root,
                operation_id="op-sibling-flow-2",
                scope_ids=list(op_scope.resource_scopes(flow_ids=["flow-2"])),
                state="prepared",
            )
            res_t1 = resolver.resolve_task_origin(root, 1)
            self._assert_non_auth(res_t1)
            self.assertTrue(res_t1["ok"] and res_t1["stable"])
            self.assertEqual(res_t1["route"], "B")
            self.assertEqual(res_t1["applicable_flow_closure"], ["flow-1"])
            self.assertNotIn("flow-2", res_t1["applicable_flow_closure"])

            res_t2 = resolver.resolve_task_origin(root, 2)
            self._assert_non_auth(res_t2)
            self.assertFalse(res_t2["ok"])
            self.assertEqual(res_t2["route"], "blocked")
            self.assertEqual(res_t2["diagnostics"][0]["reason_code"], "pending")

    # --- Drift, CLI, Builder, Policy Anchor & Real Repo Smoke ---
    def test_mid_read_drift_blocks_via_double_read_observations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._make_single_and_multi_plan_repo(root, two_plans=False)

            def mutate_mid_read() -> None:
                p = root / resolver.TRIPLET["master"]
                p.write_bytes(p.read_bytes() + b" ")

            res = resolver.resolve_task_origin(root, 1, before_reread=mutate_mid_read)
            self._assert_non_auth(res)
            self.assertFalse(res["ok"])
            self.assertFalse(res["stable"])
            self.assertEqual(res["route"], "blocked")
            self.assertEqual(res["plan_refs"], [])
            self.assertIsNone(res["applicable_set_digest"])
            self.assertIsNone(res["frozen_a_boundary"])
            self.assertTrue(any(d["reason_code"] == "file_changed" for d in res["diagnostics"]))

    def test_cli_dev_cli_builder_report_opt_in_and_policy_anchor(self) -> None:
        # 1. Policy anchoring includes _b_route_task_resolver.py
        _identity, files = adoption_review.policy_observations()
        self.assertTrue(any(p.endswith("_b_route_task_resolver.py") for p in files))

        # 2. dev_cli_builders rejects write/apply flags and builds read-only command
        class _Args:
            root = "."
            task_id = "1"
            operation = "implement"
            report = None
            write = False
            apply = False

        cmd = dev_cli_builders.build_b_route_task_origin_cmd(_Args())
        self.assertIn("resolve_b_route_task_origin.py", cmd[2])
        self.assertIn("--task-id", cmd)
        _Args.write = True
        with self.assertRaises(ValueError):
            dev_cli_builders.build_b_route_task_origin_cmd(_Args())

        # 3. CLI zero-write invocation + opt-in --report + overwrite rejection + invalid task_id
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_single_and_multi_plan_repo(root, two_plans=False, use_log_proof=False)
            self.assertFalse((root / "logs").exists())

            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = dev_cli.main(["b-route-task-origin", "--root", str(root), "--task-id", "1"])
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self._assert_non_auth(payload)
            self.assertEqual(payload["route"], "B")
            self.assertIsNone(payload["report_path"])
            self.assertFalse((root / "logs").exists(), "CLI without --report must create zero logs/locks")

            # Opt-in --report writes once and refuses overwrite (rc=2)
            report_rel = "logs/ci/2026-11-23/task-origin-1.json"
            buf2 = io.StringIO()
            with contextlib.redirect_stdout(buf2):
                rc2 = origin_cli.main(["--root", str(root), "--task-id", "1", "--report", report_rel])
            self.assertEqual(rc2, 0)
            self.assertTrue((root / report_rel).is_file())
            self.assertEqual(json.loads(buf2.getvalue())["report_path"], report_rel)

            buf3 = io.StringIO()
            with contextlib.redirect_stdout(buf3):
                rc3 = origin_cli.main(["--root", str(root), "--task-id", "1", "--report", report_rel])
            self.assertEqual(rc3, 2)
            self.assertEqual(json.loads(buf3.getvalue())["diagnostics"][0]["reason_code"], "conflict")

            # Invalid --task-id -> rc=2 with six-field diagnostic
            buf4 = io.StringIO()
            with contextlib.redirect_stdout(buf4):
                rc4 = origin_cli.main(["--root", str(root), "--task-id", "abc"])
            self.assertEqual(rc4, 2)
            self._assert_non_auth(json.loads(buf4.getvalue()))

            # Invalid --root -> rc=2 with six-field diagnostic
            buf_bad_root = io.StringIO()
            with contextlib.redirect_stdout(buf_bad_root):
                rc_bad_root = origin_cli.main(["--root", str(root / "nonexistent-root"), "--task-id", "1"])
            self.assertEqual(rc_bad_root, 2)
            self._assert_non_auth(json.loads(buf_bad_root.getvalue()))

            # Exercise dev_cli.build_parser().parse_args(...) via args.func(args) forwarding --operation and --report.
            report_dev_cli = "logs/ci/2026-11-23/task-origin-dev-cli-1.json"
            parsed = dev_cli.build_parser().parse_args(
                [
                    "b-route-task-origin",
                    "--root",
                    str(root),
                    "--task-id",
                    "1",
                    "--operation",
                    "implement",
                    "--report",
                    report_dev_cli,
                ]
            )
            buf_dc = io.StringIO()
            with contextlib.redirect_stdout(buf_dc):
                rc_dc = parsed.func(parsed)
            self.assertEqual(rc_dc, 0)
            dc_payload = json.loads(buf_dc.getvalue())
            self._assert_non_auth(dc_payload)
            self.assertEqual(dc_payload["route"], "B")
            self.assertEqual(dc_payload["operation"], "implement")
            self.assertEqual(dc_payload["report_path"], report_dev_cli)
            self.assertTrue((root / report_dev_cli).is_file())

        # 4. Clean-checkout smoke check using real tracked repo files without untracked logs/
        with tempfile.TemporaryDirectory() as clean_tmp:
            clean_root = Path(clean_tmp)
            tracked_paths = [
                resolver.ADR_0040,
                resolver.TRIPLET["master"],
                resolver.TRIPLET["back"],
                resolver.TRIPLET["gameplay"],
                "docs/workflows/chapter3-task-scope.json",
            ]
            for rel in tracked_paths:
                src_file = REPO_ROOT / rel
                if src_file.is_file():
                    dst_file = clean_root / rel
                    dst_file.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_file, dst_file)
            res_live = resolver.resolve_task_origin(clean_root, 1)
            self._assert_non_auth(res_live)
            self.assertTrue(res_live["ok"] and res_live["stable"])
            self.assertEqual(res_live["route"], "explicit_not_enabled_a")
            self.assertFalse((clean_root / "logs").exists(), "Clean-checkout query must create zero logs/")

        # 5. Subprocess --help check via dev_cli.py
        proc = subprocess.run(
            [sys.executable, "-B", str(SCRIPTS_PY / "dev_cli.py"), "b-route-task-origin", "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("--task-id", proc.stdout)
        self.assertIn("--report", proc.stdout)


if __name__ == "__main__":
    unittest.main()
