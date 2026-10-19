"""Bind Capability append execution to prepared MVG schemas and evidence."""
from __future__ import annotations

from copy import deepcopy
import json
import re
from pathlib import Path
from typing import Any

from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json, parse_model_json, validate_output_schema
from _mvg_capability_append import PROOF_SCHEMA, run_capability_append, preservation_errors
from _mvg_requirement_routes import FIELD, PROJECTION, membership_schema, memberships, prepared_trace, project_routes
from _mvg_requirement_accounting import (VERIFICATION, EVIDENCE, PROTOCOL_FIELD, PROTOCOL,
    project_accounting, schemas as accounting_schemas, verification_rows, evidence_rows)
from _mvg_evidence_transport import (audit_errors, audit_execution_errors, audit_prompt, audit_schema,
    compact_schema, model_context, plan_errors, plan_transport, restore_chapter5_projection, transport_proof_errors, wire_json)

APPEND_SCHEMA = "newrouge.mvg-capability-append.v1"
INPUT_LIMIT = 850_000

_TOPOLOGY_ARTIFACT_PREPARED_PATHS = {
    "docs/planning/semantic-topology/source-blocks.v1.json": "source-blocks.v1.json",
    "docs/planning/semantic-topology/semantic-requirements.v1.json": "semantic-requirements.v1.json",
    "docs/planning/semantic-topology/capabilities.v1.json": "capabilities.v1.json",
    "docs/planning/semantic-topology/topology-edges.v1.json": "topology-edges.v1.json",
}


def _topology_artifact_sha(path: Path) -> str:
    """Match the topology validator's newline-independent JSON identity."""
    from _planning_skill_common import normalized_file_sha
    return normalized_file_sha(path)


def _validate_topology_binding(prepared: Path, *, scope: dict[str, Any]) -> tuple[dict[str, Any], set[tuple[str, str]]]:
    """Validate the complete frozen topology authority before deriving a closure."""
    from _semantic_topology import CAPABILITY_EVIDENCE_RELATIONS, resolve_relation_closure

    manifest_path = prepared / "topology-manifest.v1.json"
    edges_path = prepared / "topology-edges.v1.json"
    if manifest_path.is_file() != edges_path.is_file():
        raise ValueError("mvg_topology_artifacts_partial")
    # Historical callers may build a scope-only context without selecting a
    # Capability.  Preserve that read-only context path; topology is only a
    # base closure when an explicit Capability seed is available.
    if not str(scope.get("capability_id") or "").strip():
        return ({"available": False, "status": "legacy_unmapped",
                 "resolver_revision": "registered-edge-closure.v1",
                 "reason": "Capability seed is not present in scope",
                 "nodes": [], "edges": [], "seed_nodes": [], "problems": []}, set())
    if not (manifest_path.is_file() and edges_path.is_file()):
        return ({"available": False, "status": "legacy_unmapped",
                 "resolver_revision": "registered-edge-closure.v1",
                 "reason": "topology artifacts are not present in prepared inputs",
                 "nodes": [], "edges": [], "seed_nodes": [], "problems": []}, set())

    manifest = load_json(manifest_path, {})
    bindings = manifest.get("artifacts") if isinstance(manifest, dict) else None
    if not isinstance(bindings, dict):
        raise ValueError("mvg_topology_manifest_artifacts_missing")
    for artifact_path, prepared_name in _TOPOLOGY_ARTIFACT_PREPARED_PATHS.items():
        path = prepared / prepared_name
        expected = bindings.get(artifact_path)
        if not path.is_file() or not isinstance(expected, str):
            raise ValueError("mvg_topology_artifact_binding_missing:" + artifact_path)
        actual = _topology_artifact_sha(path)
        if expected != actual:
            raise ValueError("mvg_topology_artifact_hash_mismatch:" + artifact_path)

    source_manifest = load_json(prepared / "source-manifest.v1.json", {})
    source_revision = manifest.get("source_revision")
    if not isinstance(source_revision, str) or not source_revision:
        raise ValueError("mvg_topology_source_revision_missing")
    if source_manifest.get("source_revision") != source_revision:
        raise ValueError("mvg_topology_source_manifest_revision_mismatch")
    if manifest.get("source_manifest_sha256") != source_manifest.get("manifest_sha256"):
        raise ValueError("mvg_topology_source_manifest_hash_mismatch")

    documents = {
        "source_blocks": load_json(prepared / "source-blocks.v1.json", {}),
        "requirements": load_json(prepared / "semantic-requirements.v1.json", {}),
        "capabilities": load_json(prepared / "capabilities.v1.json", {}),
        "edges": load_json(edges_path, {}),
    }
    for name, document in documents.items():
        if name != "edges" and document.get("source_revision") != source_revision:
            raise ValueError("mvg_topology_artifact_revision_mismatch:" + name)
    if documents["edges"].get("source_revision") != source_revision:
        raise ValueError("mvg_topology_artifact_revision_mismatch:edges")

    task_master_doc = load_json(prepared / "task-master.json", {})
    from _capability_input_integrity import task_master_rows, task_master_identity
    capabilities_doc = documents["capabilities"]
    closure = resolve_relation_closure(
        source_blocks=documents["source_blocks"], requirements=documents["requirements"],
        capabilities=capabilities_doc, edges=documents["edges"],
        tasks=task_master_rows(task_master_doc),
        seed_nodes=[("capability", str(scope.get("capability_id") or ""))],
        allowed_node_types={"capability", "requirement", "source_block", "task"},
        traversal_rules=CAPABILITY_EVIDENCE_RELATIONS,
    )
    if closure["problems"]:
        raise ValueError("mvg_topology_closure_invalid:" + canonical_sha(closure["problems"]))
    closure.update({"available": True, "status": "fresh",
                    "manifest_sha256": _topology_artifact_sha(manifest_path),
                    "edges_sha256": _topology_artifact_sha(edges_path),
                    "source_revision": source_revision})
    return closure, {(row["type"], row["id"]) for row in closure["nodes"]}


def capability_scopes(capabilities, semantics, planning_scope, task_statuses=None, *, prepared=None,
                      accepted_requirement_ids=()):
    required = {str(row["requirement_id"]) for row in semantics.get("requirements", [])
                if row.get("status", "active") == "active" and row.get("delivery_relevant", True)}
    if planning_scope is not None:
        required &= set(planning_scope["requirement_ids"])
    trace = prepared_trace(prepared) if prepared else {}
    seen = ({row["requirement_id"] for row in trace.get("coverage_table", [])} | set(accepted_requirement_ids)) & required
    scopes = []
    ids = set()
    for cap in capabilities.get("capabilities", []):
        cid = str(cap.get("capability_id") or "")
        if not cid or cid in ids:
            raise ValueError("Capability append requires unique explicit Capability IDs")
        ids.add(cid)
        members = set(cap.get("requirement_ids", [])) & required
        if not members:
            continue
        scopes.append({"capability_id": cid, "capability": deepcopy(cap),
                       "requirement_ids": sorted(members), "new_requirement_ids": sorted(members - seen),
                       "accepted_requirement_ids": sorted(seen), "cumulative_requirement_ids": sorted(seen | members)})
        if task_statuses is not None:
            scopes[-1]["task_statuses"] = task_statuses
        seen |= members
    if not scopes or seen != required:
        raise ValueError("capability_append_requirement_membership_incomplete:" + ",".join(sorted(required - seen)))
    return scopes


def review_projection(scope, base, proposal):
    """Review every changed flow and every link to an accepted predecessor."""
    prior = {row["id"]: row for row in base["manifest_candidate"].get("flows", [])}
    flows = proposal["manifest_candidate"].get("flows", [])
    ids = {row["id"] for row in flows if row != prior.get(row["id"])
           or set(row.get("requirement_ids", [])) & set(scope["requirement_ids"])}
    if FIELD in proposal:
        old_routes = {(row['requirement_id'], row['flow_id']): row for row in memberships(base)}
        new_routes = {(row['requirement_id'], row['flow_id']): row for row in memberships(proposal)}
        ids.update(pair[1] for pair in set(old_routes) | set(new_routes)
                   if old_routes.get(pair) != new_routes.get(pair))
    for row in evidence_rows(proposal):
        if row not in evidence_rows(base):
            ids.update(row.get('flow_ids', []))
            ids.update(flow['id'] for flow in flows if row.get('requirement_id') in flow.get('requirement_ids', []))
    entries = proposal.get("entrypoints", [])
    for row in entries:
        if row not in base.get("entrypoints", []):
            ids.update(row.get("flow_ids", []))
    # Shared runtime boundaries are indivisible review objects: include every
    # linked flow, including unchanged predecessors, until the closure stabilizes.
    while True:
        linked = {fid for row in entries if set(row.get("flow_ids", [])) & ids
                  for fid in row.get("flow_ids", [])}
        if FIELD in proposal:
            related = {rid for row in flows if row['id'] in ids for rid in row.get('requirement_ids', [])}
            linked |= {row['id'] for row in flows if related.intersection(row.get('requirement_ids', []))}
        if linked <= ids:
            break
        ids |= linked
    affected = [deepcopy(row) for row in flows if row["id"] in ids]
    requirements = set(scope["requirement_ids"]) | {
        rid for row in affected for rid in row.get("requirement_ids", [])}
    requirements |= {row['requirement_id'] for row in evidence_rows(proposal)
                     if isinstance(row, dict) and row not in evidence_rows(base)}
    # Future baseline membership is visible as context, but coverage cannot be
    # claimed before that Capability has passed its own gate.
    requirements &= set(scope["cumulative_requirement_ids"])
    result = deepcopy(proposal)
    result["manifest_candidate"]["flows"] = affected
    result["coverage_table"] = [row for row in result["coverage_table"] if row["requirement_id"] in requirements]
    for field in (VERIFICATION, EVIDENCE):
        if field in result:
            result[field] = [row for row in result[field] if row['requirement_id'] in requirements]
    if FIELD in result:
        result[FIELD] = [row for row in result[FIELD]
                         if row["requirement_id"] in requirements and row["flow_id"] in ids]
    test_ids = {tid for row in affected for tid in row.get("test_ids", [])}
    result["tests"] = [row for row in result.get("tests", []) if row["id"] in test_ids]
    result["manifest_candidate"]["tests"] = deepcopy(result["tests"])
    result["entrypoints"] = [row for row in result.get("entrypoints", []) if set(row.get("flow_ids", [])) & ids]
    result["manifest_candidate"].setdefault("coverage", {})["required_flow_ids"] = [row["id"] for row in affected]
    return result, requirements


def seed_proposal(state, prepared):
    import plan_mvg as pm
    baseline = load_json(prepared / "existing-manifest.json", None)
    from _capability_input_integrity import task_master_rows, task_master_identity
    statuses = {task_master_identity(row): row.get("status", "")
                for row in task_master_rows(load_json(prepared / "task-master.json", {}))
                if task_master_identity(row) is not None}
    manifest = deepcopy(baseline) if baseline else pm.build_manifest_skeleton(state["run_id"], [], statuses)
    result = {"schema_version": pm.PROPOSAL_SCHEMA, "analysis_identity_sha256": state["analysis_identity_sha256"],
            "planning_status": "ready_for_validation", "manifest_candidate": manifest,
            "coverage_table": [], "entrypoints": [], "tests": deepcopy(manifest.get("tests", [])),
            "gaps": [], "manual_obligations": [], "change_reviews": [], "retirement_reviews": [],
            "coverage_review": {}, "notes": []}
    trace = prepared_trace(prepared)
    if trace:
        trace = project_routes(trace)
        selected = set((state.get("planning_scope") or {}).get("requirement_ids", []))
        previous = {row['requirement_id'] for row in trace.get('coverage_table', [])}
        if selected and previous - selected:
            raise ValueError('existing_planning_trace_authority_outside_scope:' + ','.join(sorted(previous - selected)))
        result["coverage_table"] = deepcopy(trace.get("coverage_table", []))
        result[FIELD] = memberships(trace)
        if PROJECTION in trace:
            result[PROJECTION] = trace[PROJECTION]
        result["entrypoints"] = deepcopy(trace.get("entrypoints", []))
    if load_json(prepared / 'analysis-index.json', {}).get(PROTOCOL_FIELD) == PROTOCOL:
        def read_legacy(ref):
            for family in ('sources', 'references'):
                path = prepared / family / ref
                if path.is_file():
                    return path.read_text(encoding='utf-8-sig')
            return None
        projected = project_accounting(trace if trace else result, read_text=read_legacy)
        result[VERIFICATION] = projected[VERIFICATION]
        result[EVIDENCE] = projected[EVIDENCE]
        result[PROTOCOL_FIELD] = PROTOCOL
    return result


def _runner_schema_without_patterns(value):
    """Remove schema keywords unsupported by the isolated Codex CLI parser."""
    if isinstance(value, dict):
        return {key: _runner_schema_without_patterns(item)
                for key, item in value.items() if key not in {"pattern", "allOf"}}
    if isinstance(value, list):
        return [_runner_schema_without_patterns(item) for item in value]
    return value


def append_output_schema(state, scope, base, prepared, *, evidence_paths=None):
    import plan_mvg as pm
    planning_scope = state.get("planning_scope")
    refs = sorted({str(path).replace("\\", "/") for path in (evidence_paths or []) if str(path).strip()})
    if evidence_paths is None:
        refs = sorted({path.relative_to(prepared / family).as_posix()
                       for family in ("sources", "references") for path in (prepared / family).rglob("*") if path.is_file()})
    contracts = [ref for ref in refs if ref.startswith("Game.Core/Contracts/") and ref.endswith(".cs")]
    entrypoint_paths = [ref for ref in refs if ref.endswith(".cs") and not ref.startswith((
        "Game.Core.Tests/", "Tests.Godot/", "Game.Core/Contracts/"))]
    test_paths = [ref for ref in refs if ref.startswith(("Game.Core.Tests/", "Tests.Godot/tests/"))
                  and ref.endswith((".cs", ".gd"))]
    # Large path enums make the external CLI reject an otherwise valid schema.
    # The local prepared-evidence gate remains authoritative for exact paths.
    schema_refs = refs if len(refs) <= 40 and sum(len(ref) for ref in refs) <= 12000 else None
    schema_entrypoint_paths = (entrypoint_paths if len(entrypoint_paths) <= 20
                               and sum(len(ref) for ref in entrypoint_paths) <= 6000 else None)
    known_capabilities = [cap["capability_id"] for cap in load_json(prepared / "capabilities.v1.json", {}).get("capabilities", [])]
    flows = planning_scope.get("flow_ids") if planning_scope else None
    tests = planning_scope.get("test_ids") if planning_scope else None
    properties = {"schema_version": {"type": "string", "const": APPEND_SCHEMA},
                  "analysis_identity_sha256": {"type": "string", "const": state["analysis_identity_sha256"]},
                  "capability_id": {"type": "string", "const": scope["capability_id"]},
                  "base_sha256": {"type": "string", "const": canonical_sha(base)}}
    properties[FIELD] = membership_schema(scope["cumulative_requirement_ids"], flows)
    for section, field in (("flows", "flows"), ("coverage", "coverage_table"),
                           ("entrypoints", "entrypoints"), ("tests", "tests")):
        schema = pm.segment_output_schema(section=section, identity=state["analysis_identity_sha256"],
            scope_id="routing", available_source_paths=None, available_contract_paths=None,
            available_reference_paths=None, allowed_flow_ids=flows, allowed_test_ids=tests,
            allowed_test_paths=(test_paths if len(test_paths) <= 300
                                and sum(len(ref) for ref in test_paths) <= 30000 else None),
            available_entrypoint_paths=None,
            allowed_requirement_ids=scope["cumulative_requirement_ids"],
            allowed_change_ids=flows if flows else None,
            allow_planned_verification=bool((planning_scope or {}).get("allow_planned_verification")))
        if section == "flows":
            # Future cumulative membership is context from the frozen baseline;
            # exclusive new coverage is still bound to this Capability below.
            schema["properties"][field]["items"]["properties"]["requirement_ids"]["items"] = {
                "type": "string", "enum": sorted(set(scope["cumulative_requirement_ids"]) | {
                    rid for flow in base["manifest_candidate"].get("flows", []) for rid in flow.get("requirement_ids", [])})}
        properties[field] = schema["properties"][field]
        if section == "flows":
            properties[field]["items"]["properties"]["capability_refs"]["items"] = {
                "type": "string", "enum": known_capabilities}
        if section == "tests":
            for variant in properties[field]["items"]["anyOf"]:
                if variant["properties"]["kind"].get("const") == "dotnet":
                    variant["properties"]["selector"] = {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_.]+$"}
        if section == "coverage":
            properties[field]["items"]["properties"]["capability_ref"] = {
                "anyOf": [{"type": "string", "const": scope["capability_id"]}, {"type": "null"}]}
            properties[field]["items"]["properties"]["requirement_id"] = (
                {"type": "string", "enum": scope["new_requirement_ids"]} if scope["new_requirement_ids"]
                else {"type": "string", "const": ""})
            properties[field].update(minItems=len(scope["new_requirement_ids"]), maxItems=len(scope["new_requirement_ids"]))
            if load_json(prepared / 'analysis-index.json', {}).get(PROTOCOL_FIELD) == PROTOCOL:
                properties[field]['items']['properties']['disposition']['enum'] = [
                    'flow', 'other_verification', 'deferred', 'source_gap']
            else:
                for key in ('verification_ref', 'authority_ref', 'authority_review'):
                    properties[field]['items']['properties'][key] = {'type': 'null'}
        if section == "entrypoints":
            # Existing verification must be proven from prepared files by the
            # deterministic gate; generation emits only explicit obligations.
            properties[field]["items"]["properties"]["status"] = {"type": "string", "const": "planned"}
        if section == "flows" and "change_reviews" in schema["properties"]:
            properties["change_reviews"] = schema["properties"]["change_reviews"]
    if "change_reviews" not in properties:
        properties["change_reviews"] = {"type": "array", "items": {
            "type": "object", "properties": {}, "required": [], "additionalProperties": False}, "maxItems": 0}
    properties["gaps"] = {"type": "array", "items": {"type": "string", "minLength": 1}}
    properties["notes"] = {"type": "array", "items": {"type": "string", "minLength": 1}}
    if load_json(prepared / 'analysis-index.json', {}).get(PROTOCOL_FIELD) == PROTOCOL:
        properties.update(accounting_schemas(properties['coverage_table']['items'],
            scope['cumulative_requirement_ids'], flows, tests))
        properties[VERIFICATION]['items']['properties']['requirement_id'] = deepcopy(
            properties['coverage_table']['items']['properties']['requirement_id'])
        properties[VERIFICATION].update(minItems=len(scope['new_requirement_ids']), maxItems=len(scope['new_requirement_ids']))
    schema = {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}
    # Regex and cross-field constraints are rechecked by append machine
    # validation and local prepared-evidence gates. Codex CLI rejects these
    # keywords in nested branches before invocation, so keep transport portable.
    return _runner_schema_without_patterns(schema)


def _chapter5_model_projection(chapter5, evidence):
    """Replace only duplicate fingerprint payloads; keep frozen authority intact."""
    projected = deepcopy(chapter5)
    for task in projected.get("tasks", []):
        fingerprint = task.get("input_fingerprint")
        if not isinstance(fingerprint, dict) or "payload" not in fingerprint:
            continue
        source = task.get("readiness", {})
        fingerprint.pop("payload")
        fingerprint["payload_ref"] = {"path": source.get("path"), "sha256": source.get("sha256"),
                                      "json_pointer": "/input_fingerprint/payload"}
    if restore_chapter5_projection(projected, evidence) != chapter5:
        raise ValueError("mvg_chapter5_payload_source_roundtrip_mismatch")
    return projected


def complete_scope_context(prepared, scope, base, proposal=None, *, scope_schema=None):
    """Keep complete frozen proof and conservative, reproducible model evidence."""
    import plan_mvg as pm
    from _mvg_input_envelope import input_identity, _reference_path, _acceptance_refs, _looks_like_path
    from _mvg_reconciliation_projection import SCOPE_SCHEMA, LEGACY_SCOPE_SCHEMA, project_source
    from _mvg_inspection_scope import SCOPED_SCHEMAS, TOPOLOGY_SCOPE_SCHEMA
    scope_schema = TOPOLOGY_SCOPE_SCHEMA if scope_schema is None else scope_schema
    if scope_schema not in SCOPED_SCHEMAS | {SCOPE_SCHEMA, LEGACY_SCOPE_SCHEMA}:
        raise ValueError("mvg_evidence_scope_schema_invalid")
    semantics = load_json(prepared / "semantic-requirements.v1.json", {})
    rids = set(scope["requirement_ids"])
    affected, required = review_projection(scope, base, proposal or base)
    rids |= required
    rids |= {rid for flow in affected["manifest_candidate"]["flows"] for rid in flow.get("requirement_ids", [])}
    topology_closure, topology_nodes = ({}, set())
    if scope_schema == TOPOLOGY_SCOPE_SCHEMA:
        topology_closure, topology_nodes = _validate_topology_binding(prepared, scope=scope)
    rids |= {node_id for kind, node_id in topology_nodes if kind == "requirement"}
    requirements = [row for row in semantics["requirements"] if row["requirement_id"] in rids]
    owners = {str(tid) for tid in pm._review_task_ids(affected)}
    owners |= {str(row["owner_task"]) for row in affected.get("tests", []) if row.get("owner_task") is not None}
    # Taskmaster's master file is the status authority.  Views are retained
    # as evidence, but inactive/orphaned rows must never become effective MVG
    # context even when they still carry old semantic references.
    from _capability_input_integrity import _load_master_task_statuses, _task_view_is_active
    master_statuses = _load_master_task_statuses(prepared)
    all_views = [{**row, "_source_view": name}
             for name in ("tasks_back.json", "tasks_gameplay.json")
             for row in load_json(prepared / "task-views" / name, [])
             if _task_view_is_active(row, master_statuses)]
    tids = owners | {str(row["taskmaster_id"]) for row in all_views
                    if set(row.get("semantic_refs", row.get("requirement_ids", []))) & rids}
    task_master_payload = load_json(prepared / "task-master.json", {})
    from _capability_input_integrity import task_master_rows as canonical_task_master_rows, task_master_identity
    task_master_rows = [row for row in canonical_task_master_rows(task_master_payload)
                        if _task_view_is_active(row, master_statuses)]
    if topology_closure.get("available"):
        for edge in topology_closure["edges"]:
            if edge["target_type"] == "task" and edge["source_type"] in {"capability", "requirement"}:
                tids.add(edge["target_id"])
    views = [row for row in all_views if str(row.get("taskmaster_id")) in tids]
    tasks = [row for row in task_master_rows
             if task_master_identity(row) in tids]
    block_ids = set(scope["capability"].get("source_block_ids", [])) | {
        block for row in requirements for block in row.get("source_block_ids", [])}
    block_ids |= {node_id for kind, node_id in topology_nodes if kind == "source_block"}
    ledger = load_json(prepared / "source-blocks.v1.json", {})
    blocks = [row for row in ledger.get("blocks", []) if row.get("block_id") in block_ids]
    if block_ids - {row.get("block_id") for row in blocks}:
        raise ValueError("capability_append_source_blocks_missing")
    envelope = load_json(prepared / "analysis-index.json", {}).get("input_envelope", {})
    inventory = {row["path"]: row for row in envelope.get("inventory", [])}
    dependencies, necessary = {}, set()
    def bind(value, reason, *, required=True):
        ref = _reference_path(value)
        if not ref:
            return
        if ref.startswith("ADR-") and not _looks_like_path(ref):
            matches = [path for path in inventory if Path(path).name.startswith(ref + "-")]
            if len(matches) != 1:
                raise ValueError("mvg_model_required_authority_unresolved:" + ref)
            ref = matches[0]
        if not _looks_like_path(ref) and inventory.get(ref, {}).get("classification") not in {"file", "planned", "context"}:
            return
        dependencies.setdefault(ref, set()).add(reason)
        if required and inventory.get(ref, {}).get("classification") != "planned":
            necessary.add(ref)
    for ref in pm._review_reference_paths(affected):
        bind(ref, "affected_proposal", required=not ref.startswith(("Game.Core.Tests/", "Tests.Godot/")))
    for row in affected.get("tests", []):
        bind(row.get("path"), "affected_test", required=row.get("state") != "planned")
    for row in affected.get("entrypoints", []):
        bind(row.get("path"), "affected_entrypoint", required=row.get("status") == "existing_verified")
    for row in evidence_rows(affected):
        if isinstance(row, dict):
            bind(row.get("source_ref"), "requirement_evidence")
    for family in ("coverage_table", "change_reviews", "retirement_reviews"):
        for row in affected.get(family, []):
            for field in ("authority_ref", "verification_ref"):
                if row.get(field):
                    bind(row[field], "affected_" + field)
    statuses = {task_master_identity(row): str(row.get("status", "")).lower()
                for row in tasks if task_master_identity(row) is not None}
    for row in views:
        for field in ("overlay_refs", "contractRefs", "test_refs", "source_refs", "adr_refs"):
            for ref in row.get(field, []):
                bind(ref, "task_" + field, required=field != "test_refs" or statuses.get(str(row["taskmaster_id"])) == "done")
        for acceptance in row.get("acceptance", []):
            if "Refs:" in str(acceptance):
                for ref in _acceptance_refs(acceptance):
                    test = _reference_path(ref).startswith(("Game.Core.Tests/", "Tests.Godot/"))
                    bind(ref, "task_acceptance", required=not test or statuses.get(str(row["taskmaster_id"])) == "done")
    for block in blocks:
        bind(block.get("source_path"), "requirement_source_block")
    chapter5 = deepcopy(envelope["chapter5"])
    task_ids = {task_master_identity(row) for row in tasks if task_master_identity(row) is not None}
    if chapter5.get("formal_ready") is True and tids - task_ids:
        raise ValueError("mvg_model_required_task_master_missing:" + ",".join(sorted(tids - task_ids)))
    chapter5["tasks"] = [row for row in chapter5.get("tasks", []) if str(row["task_id"]) in tids]
    if chapter5.get("formal_ready") is True and tids - {str(row["task_id"]) for row in chapter5["tasks"]}:
        raise ValueError("mvg_model_required_task_readiness_missing:" + ",".join(sorted(tids - {str(row["task_id"]) for row in chapter5["tasks"]})))
    for task in chapter5["tasks"]:
        for kind in ("readiness", "reconciliation"):
            descriptor = task.get(kind, {})
            bind(descriptor.get("path"), "selected_chapter5_" + kind, required=chapter5.get("formal_ready") is True)
        ref = task.get("reconciliation", {}).get("path")
        source = pm._prepared_reference(prepared, ref)
        if source is None:
            if chapter5.get("formal_ready") is True:
                raise ValueError("mvg_model_required_evidence_missing:" + str(ref))
            continue
        if file_sha(source) != task["reconciliation"].get("sha256"):
            raise ValueError("mvg_model_required_evidence_hash_mismatch:" + str(ref))
        reconciliation = load_json(source, {})
        source_scope = reconciliation.get("source_scope") or []
        for source_row in source_scope if isinstance(source_scope, list) else [source_scope]:
            bind(source_row.get("path"), "chapter5_source_scope")
        for family in ("overlays", "contracts", "adrs"):
            for authority in (reconciliation.get("authority_scope") or {}).get(family, []):
                bind(authority.get("path") or authority.get("ref"), "chapter5_authority_" + family)
    for row in envelope.get("inventory", []):
        if "explicit_evidence" in row.get("roles", []):
            bind(row["path"], "explicit_evidence")
    evidence = []
    for ref in sorted(dependencies):
        path = pm._prepared_reference(prepared, ref)
        # Source-document blocks above carry the design evidence. Other named
        # references retain their complete text or explicitly show absence.
        if path is not None and path.is_file():
            if ref in inventory and inventory[ref].get("sha256") not in (None, file_sha(path)):
                raise ValueError("mvg_model_required_evidence_hash_mismatch:" + ref)
            with path.open(encoding="utf-8", newline="") as source:
                evidence.append({"path": ref, "sha256": file_sha(path), "text": source.read()})
            # Explicit/claimed file references require the complete document.
            # Narrow only reconciliation selected as readiness context alone.
            if (scope_schema in SCOPED_SCHEMAS | {SCOPE_SCHEMA} and "selected_chapter5_reconciliation" in dependencies[ref]
                    and dependencies[ref] == {"selected_chapter5_reconciliation"}):
                evidence[-1] = project_source(evidence[-1], requirement_ids=rids,
                    task_ids=tids, source_block_ids=block_ids,
                    capability_ids=[scope.get("capability_id", "")])
        else:
            if ref in necessary:
                raise ValueError("mvg_model_required_evidence_missing:" + ref)
            evidence.append({"path": ref, "status": "not_prepared"})
    selection = {"global_task_ids": [str(row["task_id"]) for row in envelope["chapter5"].get("tasks", [])],
        "model_task_ids": [str(row["task_id"]) for row in chapter5["tasks"]],
        "global_inventory_sha256": canonical_sha(envelope.get("inventory", [])),
        "global_inventory_count": len(inventory), "requirement_ids": sorted(rids),
        "sources": [{"path": ref, "selected": ref in dependencies,
            "reason": ",".join(sorted(dependencies[ref])) if ref in dependencies else "outside_model_dependency_scope"}
            for ref in sorted(set(inventory) | set(dependencies))]}
    if scope_schema == TOPOLOGY_SCOPE_SCHEMA:
        selection["topology_base_closure"] = {
            "status": topology_closure["status"],
            "resolver_revision": topology_closure["resolver_revision"],
            "node_count": len(topology_closure["nodes"]),
            "edge_count": len(topology_closure["edges"]),
            "manifest_sha256": topology_closure.get("manifest_sha256"),
            "edges_sha256": topology_closure.get("edges_sha256"),
        }
    if scope_schema in SCOPED_SCHEMAS | {SCOPE_SCHEMA}:
        evidence_hashes = {row["path"]: row.get("sha256") for row in evidence}
        for row in selection["sources"]:
            row["sha256"] = inventory.get(row["path"], {}).get("sha256") or evidence_hashes.get(row["path"])
    context = {"input_identity": input_identity(prepared),
            "evidence_scope_schema": scope_schema,
            "chapter5": _chapter5_model_projection(chapter5, evidence), "evidence_selection": selection,
            "scope": scope, "requirements": requirements, "source_blocks": blocks,
            "task_views": views, "task_master": tasks, "evidence": evidence,
            "capabilities": load_json(prepared / "capabilities.v1.json", {}),
            "available_reference_paths": sorted({p.relative_to(prepared / family).as_posix()
                for family in ("sources", "references") for p in (prepared / family).rglob("*") if p.is_file()})}
    if scope_schema == TOPOLOGY_SCOPE_SCHEMA:
        context["topology_base_closure"] = topology_closure
    return context


def _legacy_complete_scope_context(prepared, scope, base, proposal=None):
    """Rebuild the pre-scoped full-repository projection for historical proofs.

    This deliberately mirrors the frozen baseline behavior, including task-id
    comparisons and ``Path.read_text`` newline normalization.  It is only a
    recovery reader; new requests always use :func:`complete_scope_context`.
    """
    import plan_mvg as pm
    from _mvg_input_envelope import input_identity, _reference_path
    semantics = load_json(prepared / "semantic-requirements.v1.json", {})
    rids = set(scope["requirement_ids"])
    affected, required = review_projection(scope, base, proposal or base)
    rids |= required
    rids |= {rid for flow in affected["manifest_candidate"]["flows"]
             for rid in flow.get("requirement_ids", [])}
    requirements = [row for row in semantics["requirements"] if row["requirement_id"] in rids]
    owners = {tid for flow in affected["manifest_candidate"]["flows"] for tid in flow.get("task_ids", [])}
    owners |= {row.get("owner_task") for row in affected.get("entrypoints", []) + affected.get("tests", [])
               if row.get("owner_task") is not None}
    views = [{**row, "_source_view": name}
             for name in ("tasks_back.json", "tasks_gameplay.json")
             for row in load_json(prepared / "task-views" / name, [])
             if set(row.get("semantic_refs", row.get("requirement_ids", []))) & rids
             or row.get("taskmaster_id") in owners]
    tids = {row.get("taskmaster_id") for row in views} | owners
    from _capability_input_integrity import task_master_rows, task_master_identity
    tasks = [row for row in task_master_rows(load_json(prepared / "task-master.json", {}))
             if task_master_identity(row) in {str(value) for value in tids}]
    block_ids = set(scope["capability"].get("source_block_ids", [])) | {
        block for row in requirements for block in row.get("source_block_ids", [])}
    ledger = load_json(prepared / "source-blocks.v1.json", {})
    blocks = [row for row in ledger.get("blocks", []) if row.get("block_id") in block_ids]
    if block_ids - {row.get("block_id") for row in blocks}:
        raise ValueError("capability_append_source_blocks_missing")
    dependencies = pm._review_reference_paths(affected)
    dependencies |= {row["source_ref"].split("#", 1)[0] for row in evidence_rows(affected)
                     if isinstance(row, dict) and isinstance(row.get("source_ref"), str)}
    for family in ("coverage_table", "change_reviews", "retirement_reviews"):
        for row in affected.get(family, []):
            for field in ("authority_ref", "verification_ref"):
                if row.get(field):
                    dependencies.add(str(row[field]).split("#", 1)[0])
    dependencies |= {_reference_path(ref) for row in views
                     for field in ("overlay_refs", "contractRefs", "test_refs", "source_refs")
                     for ref in row.get(field, [])}
    envelope = load_json(prepared / "analysis-index.json", {}).get("input_envelope", {})
    dependencies |= {row["path"] for row in envelope.get("inventory", [])
                     if row["required"] and row.get("prepared_path", "").startswith(("sources/", "references/"))}
    evidence = []
    for ref in sorted(dependencies):
        path = pm._prepared_reference(prepared, ref)
        if path is not None and path.is_file():
            evidence.append({"path": ref, "sha256": file_sha(path),
                             "text": path.read_text(encoding="utf-8")})
        else:
            evidence.append({"path": ref, "status": "not_prepared"})
    return {"input_identity": input_identity(prepared),
            "chapter5": deepcopy(envelope["chapter5"]), "scope": scope,
            "requirements": requirements, "source_blocks": blocks, "task_views": views,
            "task_master": tasks, "evidence": evidence,
            "capabilities": load_json(prepared / "capabilities.v1.json", {}),
            "available_reference_paths": sorted({p.relative_to(prepared / family).as_posix()
                for family in ("sources", "references")
                for p in (prepared / family).rglob("*") if p.is_file()})}


def bounded_request(prompt, schema):
    from _capability_input_integrity import configured_input_limit, measure_request
    return measure_request(prompt + "\n" + json.dumps(schema, ensure_ascii=False),
        max_bytes=INPUT_LIMIT, max_input_tokens=configured_input_limit())


def evidence_scope_errors(prepared, scope, base, proposal, context):
    """Recompute source selection from frozen authority before trusting admission."""
    try:
        # New scoped contexts carry an explicit schema marker.  Missing
        # selection in such a context is deletion/tampering, never a legacy
        # format, and must fail closed.
        from _mvg_reconciliation_projection import SCOPE_SCHEMA, LEGACY_SCOPE_SCHEMA
        from _mvg_inspection_scope import SCOPED_SCHEMAS
        if context.get("evidence_scope_schema") in SCOPED_SCHEMAS | {SCOPE_SCHEMA, LEGACY_SCOPE_SCHEMA}:
            if "evidence_selection" not in context:
                return ["evidence_transport_scope_selection_missing"]
            expected = complete_scope_context(prepared, scope, base, proposal,
                scope_schema=context["evidence_scope_schema"])
        elif "evidence_selection" not in context:
            # Historical proofs predate scoped selection. Rebuild their exact
            # full-repository projection from frozen prepared inputs.
            expected = _legacy_complete_scope_context(prepared, scope, base, proposal)
        else:
            return ["evidence_transport_scope_schema_invalid"]
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        return ["evidence_transport_scope_invalid:" + str(exc)]
    fields = ("input_identity", "chapter5", "scope", "requirements", "source_blocks",
              "task_views", "task_master", "evidence", "capabilities", "available_reference_paths")
    if "evidence_selection" in expected:
        fields = ("evidence_scope_schema", "evidence_selection") + fields
    if "topology_base_closure" in expected:
        fields += ("topology_base_closure",)
    # Only runtime review bindings may accompany the reconstructed scope.
    # Reject unknown/new fields in an alleged legacy context as well.
    if set(context) - set(expected) - {"accepted_proposal", "proposal", "reopen_context"}:
        return ["evidence_transport_scope_changed"]
    if any(context.get(field) != expected[field] for field in fields):
        return ["evidence_transport_scope_changed"]
    return []


_PREFLIGHT_REQUEST_CACHE = {}


def preflight_runner_payload(attempt_root, attempt, prompt, schema, output_name):
    """Measure the isolated runner's fully wrapped, schema-bearing request."""
    from _capability_input_integrity import check_workspace_request, configured_input_limit, REPORT_NAME
    from _mvg_evidence_transport import text_sha
    from openai_isolated_model_runner import workspace_payload
    relative_output = Path(output_name)
    prompt_stem = relative_output.with_suffix("").as_posix().replace("/", "-")
    sandbox = attempt_root / "llm-sandbox" / f"attempt-{attempt}" / prompt_stem
    sandbox.mkdir(parents=True, exist_ok=True)
    prompt_path = sandbox / f"prompt-{attempt}-{prompt_stem}.txt"
    schema_path = sandbox / "output-schema.json"
    prompt_path.write_text(prompt, encoding="utf-8", newline="\n")
    atomic_json(schema_path, schema)
    output_path = sandbox / relative_output.name
    payload = workspace_payload(sandbox, prompt_path=prompt_path, output_path=output_path, max_bytes=INPUT_LIMIT)
    limit = configured_input_limit()
    key = (text_sha(payload), INPUT_LIMIT, limit)
    cached = _PREFLIGHT_REQUEST_CACHE.get(key)
    if cached is not None:
        if isinstance(cached, str):
            atomic_json(sandbox / REPORT_NAME, {"status": "blocked", "reason": cached,
                "complete_request_bytes": len(payload.encode("utf-8")), "model_invoked": False,
                "truncation_allowed": False})
            raise ValueError(cached)
        atomic_json(sandbox / REPORT_NAME, {"status": "ready", "complete": True, **cached})
        return deepcopy(cached)
    if len(_PREFLIGHT_REQUEST_CACHE) >= 256:
        _PREFLIGHT_REQUEST_CACHE.clear()
    try:
        report = check_workspace_request(sandbox, payload, max_bytes=INPUT_LIMIT, max_input_tokens=limit)
    except ValueError as exc:
        if any(code in str(exc) for code in ("runner_input_too_large", "runner_context_budget_exceeded")):
            _PREFLIGHT_REQUEST_CACHE[key] = str(exc)
        raise
    _PREFLIGHT_REQUEST_CACHE[key] = deepcopy(report)
    return report


def preflight_dispatch(runner, *, workspace, prompt_path, output_path, output_schema, timeout_sec):
    """Validate the final sandbox and backend availability without model dispatch."""
    import argparse
    import contextlib
    import io
    import os
    import shutil
    from _capability_input_integrity import check_workspace_request, configured_input_limit
    from openai_isolated_model_runner import DEFAULT_MAX_BYTES, workspace_payload
    if (workspace / "analysis-input/model-batches/batch-index.json").exists():
        raise ValueError("mvg_runner_batched_input_unsupported")
    if output_schema is not None:
        schema = load_json(output_schema, None)
        if not isinstance(schema, dict) or not output_schema.resolve().is_relative_to(workspace.resolve()):
            raise ValueError("runner_output_schema_preparation_invalid")
        import jsonschema
        try:
            jsonschema.validators.validator_for(schema).check_schema(schema)
        except jsonschema.exceptions.SchemaError as exc:
            raise ValueError("runner_output_schema_preparation_invalid") from exc
    if runner.name == "codex_isolated_model_runner.py":
        import codex_isolated_model_runner as codex
        args = argparse.Namespace(workspace=str(workspace), prompt_file=str(prompt_path),
            output=str(output_path), output_schema=str(output_schema) if output_schema else "",
            max_bytes=DEFAULT_MAX_BYTES, max_input_tokens=configured_input_limit(),
            timeout_sec=timeout_sec, preflight=True)
        with contextlib.redirect_stdout(io.StringIO()):
            codex.run(args)
        codex._codex_executable()
        return
    payload = workspace_payload(workspace, prompt_path=prompt_path, output_path=output_path,
                                max_bytes=DEFAULT_MAX_BYTES)
    if runner.name == "openai_isolated_model_runner.py":
        from openai_isolated_model_runner import inspect_llm_backend
        backend = inspect_llm_backend("openai-api")
        if backend.get("available") is not True:
            raise ValueError("openai-api backend unavailable: " + "; ".join(backend.get("blocking_errors", [])))
        if output_schema is not None:
            payload += "\n" + json.dumps({"text": {"format": {"type": "json_schema", "name": "newrouge_mvg_review",
                "strict": True, "schema": schema}}}, ensure_ascii=False)
    elif runner.name == "copilot_isolated_model_runner.py":
        if not shutil.which("copilot"):
            raise ValueError("GitHub Copilot CLI is unavailable")
        if not str(os.environ.get("COPILOT_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN") or "").strip():
            raise ValueError("GITHUB_TOKEN/COPILOT_GITHUB_TOKEN is unavailable")
    else:
        from _planning_skill_common import inspect_isolated_runner
        configured = os.environ.get("SC_KNOWLEDGE_PLANNING_RUNNER")
        if not configured or Path(configured).resolve() != runner.resolve():
            raise ValueError("MVG runner preflight is unsupported")
        inspect_isolated_runner(runner)
    check_workspace_request(workspace, payload, max_bytes=DEFAULT_MAX_BYTES,
                            max_input_tokens=configured_input_limit())


def dispatch_request_identity(run_dir, runner, *, workspace, prompt_path, output_path, output_schema, attempt):
    """Bind every final sandbox input and runner wrapper before reservation."""
    from _capability_input_integrity import REPORT_NAME
    workspace = workspace.resolve()
    def relative(path):
        path = path.resolve()
        if not path.is_relative_to(run_dir.resolve()):
            raise ValueError("mvg_dispatch_request_path_invalid")
        return path.relative_to(run_dir.resolve()).as_posix()
    excluded = {output_path.resolve(), (workspace / REPORT_NAME).resolve()}
    files = {path.relative_to(workspace).as_posix(): file_sha(path) for path in sorted(workspace.rglob("*"))
             if path.is_file() and path.resolve() not in excluded}
    identity = {"attempt": attempt, "workspace": relative(workspace), "prompt_path": relative(prompt_path),
        "schema_path": relative(output_schema) if output_schema else None, "output_path": relative(output_path),
        "runner": runner.name, "runner_sha256": file_sha(runner) if runner.is_file() else None,
        "input_files": files}
    identity["request_sha256"] = canonical_sha(identity)
    return identity


def verify_dispatch_receipts(run_dir, calls):
    """The coordinator owns request and outcome identity; sidecars are projections."""
    from _planning_skill_common import repo_path
    from _capability_input_integrity import REPORT_NAME
    for row in calls:
        request = row.get("request_identity")
        if request is None:
            continue  # Historical calls remain read-only and retain their original identity.
        if not isinstance(request, dict) or canonical_sha({key: value for key, value in request.items()
                if key != "request_sha256"}) != request.get("request_sha256"):
            raise ValueError("mvg_dispatch_request_identity_changed")
        def safe_path(value):
            path = repo_path(run_dir, value)
            if not path.is_relative_to(run_dir.resolve()):
                raise ValueError("mvg_dispatch_request_path_invalid")
            return path
        workspace, output = safe_path(request["workspace"]), safe_path(request["output_path"])
        prompt = safe_path(request["prompt_path"])
        schema = safe_path(request["schema_path"]) if request.get("schema_path") else None
        if (type(request.get("attempt")) is not int or request["attempt"] <= 0
                or not output.is_relative_to(workspace) or not prompt.is_relative_to(workspace)
                or (schema is not None and not schema.is_relative_to(workspace))):
            raise ValueError("mvg_dispatch_request_path_invalid")
        excluded = {output.resolve(), (workspace / REPORT_NAME).resolve()}
        if request.get("runner") == "copilot_isolated_model_runner.py" and "copilot-model-evidence.json" not in request.get("input_files", {}):
            excluded.add((workspace / "copilot-model-evidence.json").resolve())
        files = {path.relative_to(workspace).as_posix(): file_sha(path) for path in sorted(workspace.rglob("*"))
                 if path.is_file() and path.resolve() not in excluded}
        if files != request.get("input_files"):
            raise ValueError("mvg_dispatch_request_inputs_changed:" + request["workspace"] + ":" + str([
                key for key in set(files) | set(request.get("input_files", {}))
                if files.get(key) != request.get("input_files", {}).get(key)]))
        outcome = load_json(run_dir / "dispatch-receipts" / f"dispatch-{row['number']}.json", None)
        bound = row.get("outcome")
        reserved_projection = {key: deepcopy(value) for key, value in row.items() if key != "outcome"}
        expected = deepcopy(reserved_projection)
        if bound is not None:
            expected.update(bound)
        if (outcome is not None and canonical_sha(outcome) != canonical_sha(expected)
                and canonical_sha(outcome) != canonical_sha(reserved_projection)):
            raise ValueError("mvg_dispatch_outcome_projection_changed")
        if bound is not None:
            if bound.get("status") == "completed":
                if not output.is_file() or file_sha(output) != bound.get("output_sha256"):
                    raise ValueError("mvg_dispatch_completed_output_changed")
                if schema is not None:
                    validate_output_schema(output, schema)
                parse_model_json(output)
            elif bound.get("status") != "failed" or not bound.get("error_type") or not bound.get("error_class"):
                raise ValueError("mvg_dispatch_failed_outcome_invalid")


def _compact_task_views(rows):
    """Encode repeated task-view fields once while preserving each exact source row."""
    groups = {}
    order = []
    for ordinal, row in enumerate(rows):
        task_id = row.get("taskmaster_id")
        key = ("task", canonical_sha(task_id)) if task_id is not None else ("row", str(ordinal))
        if key not in groups:
            groups[key] = {"taskmaster_id": task_id, "views": []}
            order.append(key)
        groups[key]["views"].append({
            "source": row.get("_source_view", "unknown"),
            "fields": {name: value for name, value in row.items()
                       if name not in {"taskmaster_id", "_source_view"}},
        })
    result = []
    for key in order:
        group = groups[key]
        view_rows = [row["fields"] for row in group["views"]]
        shared_keys = set(view_rows[0]) if view_rows else set()
        for row in view_rows[1:]:
            shared_keys = {name for name in shared_keys if name in row and row[name] == view_rows[0][name]}
        group["shared"] = {name: view_rows[0][name] for name in sorted(shared_keys)} if view_rows else {}
        for view, row in zip(group["views"], view_rows):
            view["fields"] = {name: value for name, value in row.items() if name not in shared_keys}
        result.append(group)
    return result


def synthesis_context(payload, transport):
    """Build a compact model view while retaining complete source text in transport."""
    reduced = deepcopy(payload)
    reduced["evidence"] = deepcopy(transport["plan"]["inventory"])
    from _mvg_inspection_scope import SCOPED_SCHEMAS
    if payload.get("evidence_scope_schema") not in SCOPED_SCHEMAS:
        # Preserve historical synthesis hashes. New contexts use the existing
        # typed, ordered lossless codec rather than a second grouping format.
        reduced["task_views"] = _compact_task_views(reduced.get("task_views", []))
    # Exact source refs remain in the task views and evidence inventory. The
    # repository-wide names-only index remains in transport for local checks.
    reduced.pop("available_reference_paths", None)
    inspections = []
    for record in transport["audits"]:
        audit = deepcopy(record["audit"])
        for row in audit.get("reports", {}).values():
            row.pop("citation_texts", None)
        inspections.append(audit)
    reduced["evidence_inspections"] = inspections
    reduced["evidence_context_sha256"] = transport["plan"]["context_sha256"]
    return model_context(reduced)


def machine_validation_issues(validation, scope, proposal):
    """Attach deterministic object addresses without parsing reviewer prose."""
    requirements = set(scope["cumulative_requirement_ids"])
    flows = proposal["manifest_candidate"].get("flows", [])
    tests = proposal.get("tests", [])
    issues = []
    def named(identifier, code):
        return bool(re.search(r"(?<![A-Za-z0-9_-])" + re.escape(str(identifier)) + r"(?![A-Za-z0-9_-])", code))
    for code in dict.fromkeys(validation["errors"] + validation["formal_blockers"]):
        detail = {"requirement_ids": sorted(rid for rid in requirements if named(rid, code)),
                  "flow_ids": sorted(row["id"] for row in flows if named(row["id"], code)),
                  "test_ids": sorted(row["id"] for row in tests if named(row["id"], code))}
        if code == "coverage_table_missing_or_empty":
            detail["requirement_ids"] = list(scope["new_requirement_ids"])
        if code == "entrypoints_missing_or_empty":
            routed = {row.get("flow_id") for row in proposal.get("coverage_table", [])
                      if row.get("requirement_id") in requirements}
            detail["flow_ids"] = sorted(row["id"] for row in flows if row.get("handoffs")
                and (set(row.get("requirement_ids", [])) & requirements or row["id"] in routed))
        if "entrypoint" in code:
            for row in proposal.get("entrypoints", []):
                address = str(row.get("path") or row.get("owner_task") or "")
                if address and code.endswith(":" + address):
                    detail["flow_ids"] = sorted(set(detail["flow_ids"]) | set(row.get("flow_ids", [])))
        issues.append({"code": code, "path": "proposal", "detail": detail})
    return issues


def repair_scope_errors(old, new, issue, scope=None):
    """Preserve valid increment rows outside the named repair dependency domain."""
    identifiers = [str(issue.get("code", "")), str(issue.get("path", ""))]
    def object_targets(value):
        if isinstance(value, dict):
            for field, body in value.items():
                if field in {"flow_id", "flow_ids", "test_id", "test_ids", "requirement_id", "requirement_ids", "target_flow_id", "source_flow_id"}:
                    identifiers.append(str(body))
                elif field in {"errors", "issues", "detail", "objects"} and isinstance(body, (dict, list)):
                    object_targets(body)
        elif isinstance(value, list):
            for body in value:
                object_targets(body)
    object_targets(issue)
    if issue.get("code") == "append_cumulative_delta_invalid" and isinstance(issue.get("detail"), str):
        # Only deterministic delta diagnostics may carry machine object
        # addresses in text. Reviewer rationale/findings never widen scope.
        identifiers.append(issue["detail"])
    detail = " ".join(identifiers)
    requirements = {row["requirement_id"] for row in old.get("coverage_table", [])}
    requirements |= set((scope or {}).get("cumulative_requirement_ids", []))
    flows = {row["id"]: row for row in old["manifest_candidate"].get("flows", [])}
    def named(identifier):
        return bool(re.search(r"(?<![A-Za-z0-9_-])" + re.escape(identifier) + r"(?![A-Za-z0-9_-])", detail))
    target_requirements = {rid for rid in requirements if named(rid)}
    target_flows = {fid for fid in flows if named(fid)}
    target_flows |= {fid for fid, row in flows.items() if set(row.get("requirement_ids", [])) & target_requirements}
    target_flows |= {row["flow_id"] for row in old.get("coverage_table", [])
                    if row["requirement_id"] in target_requirements and row.get("flow_id") in flows}
    new_flows = {row["id"]: row for row in new["manifest_candidate"].get("flows", [])}
    if issue.get("repair_action") == "reassign_route" or target_requirements - {
            row["requirement_id"] for row in old.get("coverage_table", [])}:
        target_flows |= {str(row.get("flow_id")) for proposal in (old, new)
                        for row in proposal.get("coverage_table", []) if row["requirement_id"] in target_requirements
                        and row.get("flow_id")}
        target_flows |= {fid for fid, row in new_flows.items()
                         if set(row.get("requirement_ids", [])) & target_requirements}
    target_tests = {row["id"] for row in old.get("tests", []) if named(row["id"])}
    target_flows |= {fid for fid, row in flows.items() if set(row.get("test_ids", [])) & target_tests}
    target_tests |= {tid for fid in target_flows for table in (flows, new_flows)
                    for tid in table.get(fid, {}).get("test_ids", [])}
    if not target_requirements and target_flows:
        target_requirements = {rid for fid in target_flows for rid in flows.get(fid, {}).get("requirement_ids", [])}
    errors = []
    if not target_requirements and not target_flows and not target_tests:
        errors.append("repair_target_unresolved")
    for field, project in ((VERIFICATION, verification_rows), (EVIDENCE, evidence_rows)):
        old_rows, new_rows = project(old), project(new)
        for row in old_rows:
            if row.get('requirement_id') not in target_requirements and row not in new_rows:
                errors.append('repair_unrelated_' + field + '_changed:' + str(row.get('requirement_id')))
        for row in new_rows:
            if row.get('requirement_id') not in target_requirements and row not in old_rows:
                errors.append('repair_unrelated_' + field + '_added:' + str(row.get('requirement_id')))
    for row in old.get("coverage_table", []):
        if row["requirement_id"] not in target_requirements and row not in new.get("coverage_table", []):
            errors.append("repair_unrelated_coverage_changed:" + row["requirement_id"])
    old_routes, new_routes = memberships(old), memberships(new)
    if not isinstance(new_routes, list):
        new_routes = []
    route_targets = {fid for fid in set(flows) | set(new_flows) if named(fid)} or target_flows
    for row in old_routes:
        if not (row["requirement_id"] in target_requirements and row["flow_id"] in route_targets) and row not in new_routes:
            errors.append(f"repair_unrelated_requirement_route_changed:{row['requirement_id']}:{row['flow_id']}")
    for row in new_routes:
        if row not in old_routes and not (row["requirement_id"] in target_requirements and row["flow_id"] in route_targets):
            errors.append(f"repair_unrelated_requirement_route_added:{row['requirement_id']}:{row['flow_id']}")
    for fid, row in flows.items():
        if fid not in target_flows and row != new_flows.get(fid):
            errors.append("repair_unrelated_flow_changed:" + fid)
    for row in old.get("tests", []):
        if row["id"] not in target_tests and row not in new.get("tests", []):
            errors.append("repair_unrelated_test_changed:" + row["id"])
    old_tests = {row["id"] for row in old.get("tests", [])}
    for row in new.get("tests", []):
        if row["id"] not in old_tests and row.get("flow_id") not in target_flows:
            errors.append("repair_unrelated_test_added:" + row["id"])
    old_entrypoints = old.get("entrypoints", [])
    for row in old_entrypoints:
        if not set(row.get("flow_ids", [])) & target_flows and row not in new.get("entrypoints", []):
            errors.append("repair_unrelated_entrypoint_changed:" + str(row.get("path", "")))
    for row in new.get("entrypoints", []):
        if row in old_entrypoints:
            continue
        matching = next((prior for prior in old_entrypoints if all(prior.get(field) == row.get(field)
            for field in ("owner_task", "path", "symbol"))), None)
        linked = set(row.get("flow_ids", []))
        if matching is None:
            if not linked or not linked <= target_flows:
                errors.append("repair_unrelated_entrypoint_added:" + str(row.get("path", "")))
        elif linked - set(matching.get("flow_ids", [])) - target_flows:
            errors.append("repair_unrelated_entrypoint_changed:" + str(row.get("path", "")))
    if canonical_sha(old) == canonical_sha(new):
        errors.append("repair_target_unchanged")
    return errors


def stage_cost_preflight(path, *, phase, evidence_calls, remaining, future, selector_calls=0,
                         unknown_future_scope_estimate=None):
    """Reject a known impossible stage; unknown future model output is never predicted."""
    stage = evidence_calls + 1
    required = {"run": stage + future["run"] + selector_calls,
                "lineage": (0 if phase == "selection" else stage) + future["lineage"]}
    blocked = [key for key in required if required[key] > remaining[key]]
    report = {"schema_version": "newrouge.mvg-stage-cost.v1", "phase": phase,
        "measured_evidence_calls": evidence_calls, "synthesis_calls": 0 if phase == "selection" else 1,
        "current_selector_calls": 1 if phase == "selection" else 0,
        "measured_stage_calls": stage, "necessary_future_base_calls": future,
        "selector_calls": selector_calls, "minimum_required_calls": required,
        "remaining_calls": remaining, "dynamic_review_and_repair_calls": "unknown",
        "stage_dispatch_status": "not_dispatched", "status": "blocked" if blocked else "ready",
        "blocking_budgets": blocked}
    if unknown_future_scope_estimate is not None:
        report["unknown_future_scope_estimate"] = unknown_future_scope_estimate
    atomic_json(path, report)
    if blocked:
        raise ValueError("mvg_stage_cost_budget_insufficient:" + ";".join(
            key + "=" + str(required[key]) + ">" + str(remaining[key]) for key in blocked))
    return report


def restore_inspection_cost(candidate_root, context_number, expected):
    """Recover only measured cost from this candidate's exact verified inspection."""
    path = (candidate_root / "capability-append/evidence-contexts" / str(context_number) / "inspect" /
            canonical_sha(expected).split(":")[-1] / "transport.json")
    transport = load_json(path, None)
    if transport is None:
        return 0
    if transport.get("context") != expected or transport.get("plan", {}).get("phase") != "inspect":
        raise ValueError("mvg_evidence_transport_invalid:inspection_cost_context_changed")
    plan = transport["plan"]
    errors = plan_errors(expected, plan)
    if len(transport.get("audits", [])) != len(plan["batches"]):
        errors.append("evidence_transport_audits_incomplete")
    for batch, record in zip(plan["batches"], transport.get("audits", [])):
        errors += audit_errors(plan, batch, record["audit"])
        errors += audit_execution_errors(batch, record["audit"], record["execution"])
    if errors:
        raise ValueError("mvg_evidence_transport_invalid:" + ";".join(errors))
    return len(plan["batches"])


def generate_append(root, state, candidate_root, *, invoke_factory, before_call, checkpoint,
                    scope_index=None, accepted_seed=None, selected_records=None, cost_budget=None):
    import plan_mvg as pm
    from _mvg_planning_review import semantic_review_errors, review_execution_errors
    prepared = candidate_root / "analysis-input"
    from _mvg_input_envelope import validate_envelope
    validate_envelope(root, prepared, state)
    if state.get("formal_ready") is not True:
        raise ValueError("MVG formal generation requires current Chapter 5 readiness")
    capabilities = load_json(prepared / "capabilities.v1.json", {})
    semantics = load_json(prepared / "semantic-requirements.v1.json", {})
    from _capability_input_integrity import task_master_rows, task_master_identity
    task_statuses = {task_master_identity(row): str(row.get("status", "")).lower()
                    for row in task_master_rows(load_json(prepared / "task-master.json", {}))
                    if task_master_identity(row) is not None}
    all_scopes = capability_scopes(capabilities, semantics, state.get("planning_scope"), task_statuses, prepared=prepared)
    scopes = all_scopes
    baseline = load_json(prepared / "existing-manifest.json", None)
    original_seed = seed_proposal(state, prepared)
    seed = original_seed
    prefix = deepcopy(selected_records or [])
    if scope_index is not None:
        if not isinstance(scope_index, int) or not 0 <= scope_index < len(all_scopes):
            raise ValueError("capability_append_scope_index_invalid")
        scopes = [all_scopes[scope_index]]
        if len(prefix) != scope_index or not isinstance(accepted_seed, dict):
            raise ValueError("capability_append_selected_prefix_missing")
        seed = deepcopy(accepted_seed)
        if prefix:
            prefix_proof = admission_proof(state, original_seed, all_scopes[:scope_index], prefix, seed)
            errors = append_proof_errors(state, seed, prefix_proof, semantics,
                                         set(all_scopes[scope_index - 1]["cumulative_requirement_ids"]),
                                         root=root, prepared=prepared)
            if errors:
                raise ValueError("capability_append_selected_prefix_invalid:" + ";".join(errors))
        elif seed != original_seed:
            raise ValueError("capability_append_original_seed_changed")
    if 2 * len(scopes) > pm.MVG_CANDIDATE_INVOCATION_LIMIT:
        raise ValueError("capability_append_budget_insufficient_for_scope:"
                         f"minimum_calls={2 * len(scopes)};limit={pm.MVG_CANDIDATE_INVOCATION_LIMIT}")

    def next_attempt():
        return int(load_json(candidate_root / "capability-append/append-ledger.json", {}).get("total_invocations", 0)) + 1

    known_inspect_batches = {}

    def check_cost(phase, count, payload):
        scope_id = payload["scope"]["capability_id"]
        if phase == "inspect":
            known_inspect_batches[scope_id] = max(known_inspect_batches.get(scope_id, 0), count)
        if cost_budget is not None:
            budget = cost_budget(phase, known_evidence_calls=known_inspect_batches.get(scope_id, 0))
        else:
            scope_position = next(index for index, row in enumerate(scopes) if row["capability_id"] == scope_id)
            future = 2 * (len(scopes) - scope_position - 1) + (1 if phase == "inspect" else 0)
            budget = {"remaining": {"run": state.get("mvg.run_invocation_limit", 192),
                "lineage": pm.MVG_CANDIDATE_INVOCATION_LIMIT - next_attempt() + 1},
                "future": {"run": future, "lineage": future}, "selector_calls": 0}
        return stage_cost_preflight(candidate_root / "capability-append/stage-costs" /
            (str(next_attempt()) + "-" + phase + ".json"), phase=phase, evidence_calls=count, **budget)

    def preflight(prompt, schema, output_name):
        validate_envelope(root, prepared, state)
        number = next_attempt()
        return preflight_runner_payload(candidate_root / "capability-append" / f"call-{number}",
                                        number, prompt, schema, output_name)

    def input_prompt(payload, instruction, schema, output_name, phase, context, call):
        """Prefer complete inline input; route oversize auxiliary files losslessly."""
        selection = payload.get("evidence_selection")
        if selection is not None:
            atomic_json(candidate_root / "capability-append/evidence-selections" / phase /
                        (canonical_sha(selection).split(":")[-1] + ".json"), selection)
        from _mvg_evidence_transport import encode_model_context
        prompt = instruction + encode_model_context(model_context(payload))
        try:
            preflight(prompt, schema, output_name)
            check_cost(phase, 0, payload)
            return prompt, None
        except ValueError as exc:
            if not any(code in str(exc) for code in ("runner_input_too_large", "runner_context_budget_exceeded")):
                raise
        # Inspectors never see failed proposal/issue context. The final repair
        # request still gets both objects, complete and without clipping.
        inspect_context = deepcopy(payload)
        if phase == "inspect":
            inspect_context.pop("repair_proposal", None)
            inspect_context.pop("hard_issue", None)
        cache = candidate_root / "capability-append/evidence-contexts" / str(context) / phase / canonical_sha(inspect_context).split(":")[-1]
        path = cache / "transport.json"
        transport = load_json(path, None)
        if transport is None:
            probe_count = 0
            def probe(text, output_schema):
                nonlocal probe_count
                probe_count += 1
                return preflight_runner_payload(cache / "preflight" / str(probe_count), 1, text, output_schema,
                                                f"segments/evidence-{phase}.json")
            plan = plan_transport(inspect_context, phase=phase, probe=probe)
            # No model call is made until every full-text batch fits and its
            # exact reassembly has passed the local conservation gate.
            transport = {"context": inspect_context, "plan": plan, "audits": []}
            atomic_json(cache / "plan.json", plan)
            check_cost(phase, len(plan["batches"]), payload)
            for batch in plan["batches"]:
                text = audit_prompt(plan, batch["parts"])
                output_schema = audit_schema(plan, batch["parts"])
                name = f"segments/evidence-{phase}.json"
                admitted = preflight(text, output_schema, name)
                if admitted["request_sha256"] != batch["input_report"]["request_sha256"]:
                    raise ValueError("mvg_evidence_request_changed_after_preflight")
                number = next_attempt()
                workspace = candidate_root / "capability-append" / f"call-{number}"
                validate_envelope(root, prepared, state)
                output, execution = invoke_factory(workspace)(text, number, output_name=name,
                    output_schema_path=workspace / "output-schema.json", output_schema=output_schema,
                    before_dispatch=lambda request_identity=None: call("evidence-" + phase, request_identity))
                validate_output_schema(output, workspace / "output-schema.json")
                audit = parse_model_json(output)
                execution = dict(execution, output_sha256=file_sha(output), audit_sha256=canonical_sha(audit))
                errors = audit_errors(plan, batch, audit) + audit_execution_errors(batch, audit, execution)
                atomic_json(workspace / "evidence-execution.json", execution)
                if errors:
                    raise ValueError("mvg_evidence_audit_invalid:" + ";".join(errors))
                transport["audits"].append({"audit": audit, "execution": execution})
            atomic_json(path, transport)
        if transport.get("context") != inspect_context:
            raise ValueError("mvg_evidence_context_changed")
        plan = transport["plan"]
        errors = plan_errors(inspect_context, plan)
        if len(transport["audits"]) != len(plan["batches"]):
            errors.append("evidence_transport_audits_incomplete")
        for batch, record in zip(plan["batches"], transport["audits"]):
            errors += audit_errors(plan, batch, record["audit"])
            errors += audit_execution_errors(batch, record["audit"], record["execution"])
        if errors:
            raise ValueError("mvg_evidence_transport_invalid:" + ";".join(errors))
        if phase == "inspect":
            known_inspect_batches[payload["scope"]["capability_id"]] = len(plan["batches"])
        check_cost(phase, 0, payload)
        reduced = synthesis_context(payload, transport)
        prompt = (instruction +
            "Auxiliary evidence was sent in full to isolated inspectors; every file/part has an exact "
            "hash-bound report below. Core authority is complete here. Use all reports, distinguish "
            "context-only material from relevant facts, and honor every source-backed hard contradiction. "
            "Inspector facts are derived evidence, not new requirements or runtime proof. Citation line "
            "addresses remain bound to immutable source parts and are rechecked locally; do not reproduce "
            "or invent quote text. Complete source text, full task records, path inventory and exact citation "
            "lines remain in the hash-bound transport proof.\n" + encode_model_context(reduced))
        preflight(prompt, schema, output_name)
        return prompt, transport

    def request(scope, base, prior, issue, context, call):
        payload = complete_scope_context(prepared, scope, base, prior)
        from _mvg_global_audit import reopen_context
        directive = reopen_context(state, scope)
        if directive:
            payload["reopen_context"] = directive
        schema = compact_schema(append_output_schema(state, scope, base, prepared,
            evidence_paths=[row["path"] for row in payload.get("evidence", []) if row.get("status") != "not_prepared"]))
        payload.update(accepted_proposal=base, repair_proposal=prior, hard_issue=issue,
                       planning_scope=state.get("planning_scope"))
        instruction = (
            "Generate only this Capability's MVG increment. The selected Capability is the primary input; "
            "all other objects are supporting evidence. Return the strict schema JSON. A flow may span "
            "Capabilities. Extend shared flows when useful, preserve all accepted coverage rows, tests, "
            "handoffs and outcomes. Do not enumerate tasks as APIs. Provide real runtime boundaries, "
            "testable success/failure/recovery assertions and producer/consumer roles. Planned tests and "
            "entrypoints are obligations, never runtime proof. Account exactly once for each new Requirement "
            "in this scope. Other Requirements are context, not additional coverage. Return requirement_route_memberships "
            "for every new (requirement_id, flow_id) pair in the cumulative Requirement scope, each with its own "
            "nonempty observable_role. A Requirement may participate in several flows; preserve accepted pair roles "
            "and its unique coverage owner. Do not repeat accepted coverage rows. "
            "For accounting-protocol runs also return requirement_verification for exactly the new Requirement IDs, "
            "copying coverage owner/disposition/authority fields with evidence_ids. Return requirement_evidence "
            "with unique (requirement_id,evidence_id), kind, source_ref, covered_behavior, flow_ids and test_ids. "
            "Evidence may support accepted Requirements without replacing their verification rows. "
            "implementation_reference never satisfies verification; verification_record needs an explicit frozen "
            "passed record with matching behavior and scope; runtime_acceptance needs a formal bound MVG receipt. "
            "Use empty evidence_ids when proof is absent; never self-report satisfied or runtime_verified. "
            "flow, other_verification, deferred and source_gap are distinct dispositions; retain reviewed authority. "
            "Existing-manifest flows/tests remain cumulative; an explicit change_reviews authority is required for semantic "
            "membership additions to frozen flows. Do not modify another Capability's accepted mapping. "
            "Report true missing upstream semantics in gaps, never invent evidence. Repairs change only "
            "the current issue and necessary dependencies, preserve other valid increment rows. No tools.\n")
        prompt, transport = input_prompt(payload, instruction, schema, "segments/capability-append.json",
                                        "inspect", context, call)
        number = next_attempt()
        workspace = candidate_root / "capability-append" / f"call-{number}"
        validate_envelope(root, prepared, state)
        output, execution = invoke_factory(workspace)(prompt, number,
            output_name="segments/capability-append.json", output_schema_path=workspace / "output-schema.json",
            output_schema=schema, before_dispatch=lambda request_identity=None: call("generate" if issue is None else "repair", request_identity))
        validate_output_schema(output, workspace / "output-schema.json")
        delta = parse_model_json(output)
        atomic_json(workspace / "generation-execution.json", execution)
        if transport is not None:
            atomic_json(workspace / "evidence-transport.json", transport)
        return delta

    def machine(scope, base, proposal):
        validation = pm.validate_proposal(root, state, proposal,
            append_requirement_ids=set(scope["cumulative_requirement_ids"]))
        issues = machine_validation_issues(validation, scope, proposal)
        coverage = {row["requirement_id"] for row in proposal.get("coverage_table", [])}
        expected = set(scope["cumulative_requirement_ids"])
        if coverage != expected:
            rows = [row.get("requirement_id") for row in proposal.get("coverage_table", [])]
            duplicate = sorted({rid for rid in rows if rows.count(rid) > 1})
            issues.append({"code": "append_requirement_accounting_incomplete", "path": "coverage_table",
                "detail": {"requirement_ids": sorted(expected - coverage) + duplicate}})
        if baseline:
            from update_mvg_baseline import apply_delta
            try:
                apply_delta(baseline, pm.build_delta(baseline, proposal), root=root, validate_final=True)
            except (ValueError, KeyError, TypeError) as exc:
                issues.append({"code": "append_cumulative_delta_invalid", "path": "manifest", "detail": str(exc)})
        return issues

    def semantic(scope, base, proposal, call, context):
        projection, required = review_projection(scope, base, proposal)
        schema = pm.semantic_review_output_schema(state=state, proposal=projection)
        from _mvg_global_audit import reopen_context, reopen_review_errors
        directive = reopen_context(state, scope)
        if directive:
            variants = [{"type": "object", "properties": {
                "conflict_id": {"type": "string", "const": issue["id"]},
                "plan_sha256": {"type": "string", "const": directive["plan"]["sha256"]},
                "verdict": {"type": "string", "enum": ["resolved", "blocked"]},
                "rationale": {"type": "string", "minLength": 1}},
                "required": ["conflict_id", "plan_sha256", "verdict", "rationale"], "additionalProperties": False}
                for issue in directive["conflicts"] if issue["id"] in directive["resolution_required_conflict_ids"]]
            schema["properties"]["reopen_reviews"] = {"type": "array", "items": {"anyOf": variants} if variants else {
                "type": "object", "properties": {}, "required": [], "additionalProperties": False},
                "minItems": len(variants), "maxItems": len(variants)}
            schema["required"].append("reopen_reviews")
        if not projection["coverage_table"]:
            schema["properties"]["requirement_reviews"]["maxItems"] = 0
        schema = compact_schema(schema)
        payload = complete_scope_context(prepared, scope, base, proposal)
        if directive:
            payload["reopen_context"] = directive
        payload.update(proposal=projection, accepted_proposal=base)
        if scope["capability_id"] not in known_inspect_batches:
            inspection = complete_scope_context(prepared, scope, base)
            inspection.update(accepted_proposal=base, planning_scope=state.get("planning_scope"))
            if directive:
                inspection["reopen_context"] = directive
            known_inspect_batches[scope["capability_id"]] = restore_inspection_cost(candidate_root, context, inspection)
        instruction = (
            "Independently check this Capability increment and every affected cross-Capability handoff. "
            "The selected Capability is the primary input. Check Requirement meaning, producer/consumer "
            "roles, observable outcomes, failures/recovery, ownership, test/entrypoint feasibility, "
            "preservation of accepted mappings and source-backed cumulative changes. Unchanged predecessors "
            "are context; do not demand missing future Capability coverage. The output schema binds exact "
            "accounting and proposal identity. Review exactly each supplied coverage row and projected flow. "
            "Accept concrete planned implementation obligations without claiming runtime success. Block only "
            "real hard issues and describe each precise repair in its row. If reopen_context is present, "
            "independently check each source-bound declared contradiction against this replacement and its "
            "accepted predecessor, and return one explicit reopen_reviews resolution for each ID in "
            "resolution_required_conflict_ids. Earlier scopes must not certify future Capability replacements. "
            "Source authority is immutable; an unresolved authority contradiction must remain blocked. "
            "Return complete review JSON, "
            "repair_action=none for accepted rows. Do not edit the proposal. No tools.\n")
        prompt, transport = input_prompt(payload, instruction, schema, "segments/capability-review.json",
                                        "review", context, call)
        number = next_attempt()
        workspace = candidate_root / "capability-append" / f"call-{number}"
        validate_envelope(root, prepared, state)
        output, execution = invoke_factory(workspace)(prompt, number,
            output_name="segments/capability-review.json", output_schema_path=workspace / "output-schema.json",
            output_schema=schema, before_dispatch=lambda request_identity=None: call("semantic", request_identity))
        validate_output_schema(output, workspace / "output-schema.json")
        proof = parse_model_json(output)
        shape = pm.validate_review_shape(state, projection, proof, requirement_ids=required,
                                        flow_ids={row["id"] for row in projection["manifest_candidate"]["flows"]},
                                        check_identity=True, check_accounting=True)
        if shape:
            raise ValueError("capability_review_output_invalid:" + ";".join(shape))
        receipt = execution.get("receipt", {})
        bound_execution = {"runner_info": execution.get("backend_info", {}), "receipt": receipt,
            "analysis_identity_sha256": state["analysis_identity_sha256"], "proposal_sha256": canonical_sha(projection),
            "semantic_review_sha256": canonical_sha(proof), "output_sha256": file_sha(output)}
        exec_errors = review_execution_errors(state, projection, bound_execution, proof)
        if exec_errors:
            raise ValueError("capability_review_execution_invalid:" + ";".join(exec_errors))
        errors = semantic_review_errors(state, projection, proof, semantics, required)
        if directive:
            errors.extend(reopen_review_errors(directive, proof))
        specific = [code for code in errors if code.startswith("semantic_review_blocked:")]
        if specific:
            errors = [code for code in errors if code != "semantic_review_not_approved"]
        issues = []
        for code in errors:
            detail = "; ".join(proof.get("findings", []))
            intent = {}
            if code.startswith("semantic_review_blocked:"):
                _, family, identifier = code.split(":", 2)
                row = next((row for row in proof.get(family, []) if row.get("requirement_id", row.get("flow_id")) == identifier), {})
                detail = str(row.get("rationale", detail))
                intent["repair_action"] = str(row.get("repair_action") or "repair_sections")
            issues.append({"code": code, "path": "semantic-review", "detail": detail,
                           "findings": deepcopy(proof.get("findings", [])), **intent})
        if transport is not None:
            for record in transport["audits"]:
                for row in record["audit"]["reports"].values():
                    for conflict in row["hard_issues"]:
                        family = "requirement_reviews" if conflict["requirement_ids"] else "flow_reviews"
                        for identifier in conflict["requirement_ids"] or conflict["flow_ids"]:
                            issues.append({"code": "semantic_review_blocked:" + family + ":" + identifier,
                                           "path": "semantic-review", "detail": conflict["detail"],
                                           "repair_action": "repair_sections"})
        bound_proof = {"projection": projection, "required_requirement_ids": sorted(required), "review": proof}
        if directive:
            bound_proof["reopen_context"] = directive
        if transport is not None:
            bound_proof["evidence_transport"] = transport
        return {"issues": issues, "proof": bound_proof, "execution": bound_execution}

    def final_machine(proposal):
        # Recheck after the final model dispatch as well as before each call.
        # Sources may drift while the last semantic response is being written.
        try:
            validate_envelope(root, prepared, state)
        except ValueError as exc:
            # The append engine treats returned issues as a terminal admission
            # result.  Do not leak a freshness exception past the ledger: the
            # candidate must be recorded as blocked, with its receipt intact.
            return ["input_freshness_blocked:" + str(exc)]
        if scope_index is not None:
            return machine(scopes[-1], seed, proposal)
        return pm.candidate_admission_errors(root, state, proposal)

    result = run_capability_append(candidate_root / "capability-append", scopes=scopes, seed=seed,
        identity=state["analysis_identity_sha256"], propose=request, machine=machine, semantic=semantic,
        final_machine=final_machine,
        invocation_limit=pm.MVG_CANDIDATE_INVOCATION_LIMIT, before_call=before_call, checkpoint=checkpoint,
        repair_check=repair_scope_errors)
    if result["status"] == "admitted":
        proof = result["proof"]
        if scope_index is not None:
            proof = admission_proof(state, original_seed, all_scopes[:scope_index + 1],
                                    prefix + result["records"], result["accepted"])
            errors = append_proof_errors(state, result["accepted"], proof, semantics,
                                         set(scopes[-1]["cumulative_requirement_ids"]), root=root, prepared=prepared)
            if errors:
                raise ValueError("capability_append_combined_proof_invalid:" + ";".join(errors))
            result["proof"] = proof
        execution = {"schema_version": "newrouge.mvg-capability-admission-execution.v1",
                     "analysis_identity_sha256": state["analysis_identity_sha256"],
                     "proposal_sha256": canonical_sha(result["accepted"]), "semantic_review_sha256": canonical_sha(proof),
                     "records_sha256": canonical_sha(proof["records"]), "total_invocations": result["total_invocations"]}
        atomic_json(candidate_root / "proposal.json", result["accepted"])
        atomic_json(candidate_root / "admission-review.json", proof)
        atomic_json(candidate_root / "admission-execution.json", execution)
    return result


def admission_proof(state, seed, scopes, records, proposal):
    """Compose admitted increments without inventing a whole-batch review."""
    return {"schema_version": PROOF_SCHEMA, "analysis_identity_sha256": state["analysis_identity_sha256"],
            "proposal_sha256": canonical_sha(proposal), "verdict": "approved", "findings": [],
            "seed": deepcopy(seed), "scopes": deepcopy(scopes), "records": deepcopy(records),
            "final_machine_status": "passed"}


def append_proof_errors(state, proposal, proof, semantics, allowed=None, *, root=None, prepared=None,
                        check_originals=True):
    """Revalidate the complete hash-bound chain without a final model call."""
    from _mvg_planning_review import semantic_review_errors, review_execution_errors
    if not isinstance(proof, dict):
        return ['capability_admission_identity_invalid']
    required = {row["requirement_id"] for row in semantics.get("requirements", [])
                if row.get("status", "active") == "active" and row.get("delivery_relevant", True)}
    if allowed is not None:
        required &= allowed
    if (proof.get("schema_version") != PROOF_SCHEMA or proof.get("verdict") != "approved"
            or proof.get("findings") != [] or proof.get("final_machine_status") != "passed"
            or proof.get("analysis_identity_sha256") != state["analysis_identity_sha256"]
            or proof.get("proposal_sha256") != canonical_sha(proposal)):
        return ["capability_admission_identity_invalid"]
    scopes = proof.get("scopes", [])
    records = proof.get("records", [])
    accepted = proof.get("seed")
    if not isinstance(accepted, dict):
        return ["capability_admission_seed_missing"]
    if (not isinstance(scopes, list) or not isinstance(records, list)
            or any(not isinstance(scope, dict) or not isinstance(scope.get('capability_id'), str)
                   or any(not isinstance(scope.get(field), list)
                          or any(not isinstance(rid, str) for rid in scope[field])
                          for field in ('requirement_ids', 'cumulative_requirement_ids')) for scope in scopes)
            or any(not isinstance(record, dict) or not isinstance(record.get('delta'), dict) for record in records)):
        return ['capability_admission_chain_shape_invalid']
    from _mvg_requirement_accounting import boundary_errors
    seed_rows = accepted.get('coverage_table', [])
    if not isinstance(seed_rows, list) or any(not isinstance(row, dict)
            or not isinstance(row.get('requirement_id'), str) for row in seed_rows):
        return ['capability_admission_seed_accounting_invalid']
    seed_requirements = {row['requirement_id'] for row in seed_rows}
    if (not scopes or len(scopes) != len(records)
            or len({scope["capability_id"] for scope in scopes}) != len(scopes)
            or ({rid for scope in scopes for rid in scope["requirement_ids"]} | seed_requirements) != required):
        return ["capability_admission_scope_incomplete"]
    errors = boundary_errors(accepted, seed_requirements, root=root, prepared=prepared,
                             check_originals=check_originals, complete=False, enforce_protocol=False)
    if errors:
        return ['capability_admission_prefix:seed:' + error for error in errors]
    seen = {row["requirement_id"] for row in accepted.get("coverage_table", [])} & required
    for index, (scope, record) in enumerate(zip(scopes, records)):
        from _mvg_capability_append import merge_append
        seen |= set(scope["requirement_ids"])
        if set(scope["cumulative_requirement_ids"]) != seen:
            errors.append("capability_admission_scope_order_invalid")
        if record.get("scope") != scope or record.get("base_sha256") != canonical_sha(accepted):
            return errors + ["capability_admission_chain_identity_invalid"]
        if record.get("record_sha256") != canonical_sha({key: value for key, value in record.items()
                                                       if key != "record_sha256"}):
            errors.append("capability_admission_record_identity_invalid")
        try:
            revised = merge_append(accepted, record["delta"], scope)
        except (ValueError, TypeError, KeyError) as exc:
            return errors + ['capability_admission_delta_invalid:' + scope['capability_id'] + ':' + str(exc)]
        if record.get("proposal_sha256") != canonical_sha(revised) or preservation_errors(accepted, revised):
            return errors + ["capability_admission_chain_mutated"]
        prefix_errors = boundary_errors(revised, seen, root=root, prepared=prepared,
                                         check_originals=check_originals)
        if prefix_errors:
            return errors + ['capability_admission_prefix:' + scope['capability_id'] + ':' + error
                             for error in prefix_errors]
        if record.get("kind") == "adoption":
            if root is None or prepared is None:
                return errors + ["capability_adoption_verification_context_missing"]
            try:
                from _mvg_capability_recovery import verify_adoption_record
                verify_adoption_record(root, state, prepared, scope, accepted, revised, record,
                    check_originals=check_originals)
            except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
                return errors + ["capability_adoption_invalid:" + str(exc)]
            accepted = revised
            continue
        prefix_errors += ['requirement_source_gap:' + row['requirement_id'] for row in verification_rows(revised)
                         if isinstance(row, dict) and row.get('disposition') == 'source_gap']
        if prefix_errors:
            return errors + ['capability_admission_prefix:' + scope['capability_id'] + ':' + error
                             for error in prefix_errors]
        projection, requirements = review_projection(scope, accepted, revised)
        bound = record.get("proof")
        if (not isinstance(bound, dict) or not isinstance(bound.get('required_requirement_ids'), list)
                or any(not isinstance(rid, str) for rid in bound['required_requirement_ids'])
                or not isinstance(bound.get('review'), dict) or not isinstance(record.get('execution'), dict)):
            return errors + ['capability_admission_record_shape_invalid:' + scope['capability_id']]
        if bound.get("projection") != projection or set(bound.get("required_requirement_ids", [])) != requirements:
            return errors + ["capability_admission_projection_changed"]
        if "evidence_transport" in bound:
            if (not isinstance(bound['evidence_transport'], dict)
                    or not isinstance(bound['evidence_transport'].get('context'), dict)
                    or not isinstance(bound['evidence_transport']['context'].get('input_identity'), dict)):
                return errors + ['capability_admission_transport_shape_invalid:' + scope['capability_id']]
            identity = bound["evidence_transport"].get("context", {}).get("input_identity", {})
            if (identity.get("run_id") != state.get("run_id")
                    or identity.get("analysis_identity_sha256") != state.get("analysis_identity_sha256")
                    or (state.get("input_envelope_sha256") is not None
                        and identity.get("envelope_sha256") != state.get("input_envelope_sha256"))):
                errors.append("evidence_transport_run_identity_changed")
            errors.extend(transport_proof_errors(bound["evidence_transport"], scope=scope,
                                                base=accepted, proposal=projection))
            if prepared is not None:
                errors.extend(evidence_scope_errors(prepared, scope, accepted, revised,
                    bound["evidence_transport"]["context"]))
        review = bound.get("review") or {}
        directive = bound.get("reopen_context")
        from _mvg_global_audit import reopen_context, reopen_review_errors, record_generation
        try:
            expected = reopen_context(state, scope, record_generation(state, index))
            if directive != expected:
                errors.append("capability_admission_reopen_context_changed")
            if expected is not None:
                errors.extend(reopen_review_errors(directive, review))
        except (AttributeError, TypeError, KeyError, ValueError):
            errors.append("capability_admission_reopen_context_invalid")
        if any(key in record['execution'] and not isinstance(record['execution'][key], dict)
               for key in ('receipt', 'runner_info')):
            return errors + ['capability_admission_record_invalid:' + scope['capability_id'] + ':execution_shape']
        try:
            errors.extend(semantic_review_errors(state, projection, review, semantics, requirements))
            errors.extend(review_execution_errors(state, projection, record.get("execution") or {}, review))
        except (AttributeError, TypeError, KeyError, ValueError) as exc:
            return errors + ['capability_admission_record_invalid:' + scope['capability_id'] + ':' + type(exc).__name__]
        accepted = revised
    if accepted != proposal:
        errors.append("capability_admission_final_proposal_changed")
    return errors


def append_execution_errors(state, proposal, execution, proof):
    lineages = execution.get("lineage_invocations")
    if lineages is not None:
        if (not isinstance(lineages, dict) or (not lineages and not all(
                    row.get("kind") == "adoption" for row in proof.get("records", [])))
                or any(type(count) is not int or not 0 < count <= 64 for count in lineages.values())
                or execution.get("total_invocations") != sum(lineages.values())):
            return ["capability_admission_lineage_execution_invalid"]
    if (execution.get("schema_version") != "newrouge.mvg-capability-admission-execution.v1"
            or execution.get("analysis_identity_sha256") != state["analysis_identity_sha256"]
            or execution.get("proposal_sha256") != canonical_sha(proposal)
            or execution.get("semantic_review_sha256") != canonical_sha(proof)
            or execution.get("records_sha256") != canonical_sha(proof.get("records"))
            or (lineages is None and not 0 < int(execution.get("total_invocations", 0)) <= 64)):
        return ["capability_admission_execution_invalid"]
    return []
