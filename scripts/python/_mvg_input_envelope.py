"""Freeze and revalidate the MVG run's complete authoritative input envelope."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import re

from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json, normalized_file_sha, repo_path

ENVELOPE_SCHEMA = "newrouge.mvg-input-envelope.v1"


def _reference_path(value):
    value = "" if value is None else str(value).strip().replace("\\", "/")
    return re.sub(r":\d+(?::\d+)?$", "", value.split("#", 1)[0])


def _looks_like_path(value):
    return "/" in value or Path(value).suffix.lower() in {
        ".cs", ".gd", ".md", ".json", ".txt", ".yaml", ".yml", ".tscn", ".tres"}


def _acceptance_refs(value):
    """Extract path-like Refs tokens from comma, semicolon, or space lists."""
    tail = str(value).split("Refs:", 1)[1]
    refs = []
    for token in re.split(r"[\s,;]+", tail.strip()):
        token = token.strip().strip("`").rstrip(".,;)")
        if token:
            refs.append(token)
    return refs


def freeze_envelope(root, *, run_id, capabilities_path, readiness, manifest_path, evidence_refs):
    """Capture originals before copying; identifiers and planned obligations are distinct."""
    import plan_mvg as pm
    from chapter5_semantic_reconciliation import (
        DEFAULT_EXTRACTION_SNAPSHOT, readiness_path_for_task, reconciliation_path_for_task,
    )
    inventory = {}

    def bind(value, role, *, required=False, prepared_path=None, planned=False, force_file=False):
        raw = "" if value is None else str(value).strip()
        if not raw:
            if required:
                raise ValueError("MVG required input is empty:" + role)
            return
        value = _reference_path(raw)
        # References may carry a markdown-style line address. Preserve only
        # the repository path as the identity-bound object.
        if not value:
            if required:
                raise ValueError("MVG required input is empty:" + role)
            return
        try:
            path = repo_path(root, value)
        except ValueError:
            if required:
                raise ValueError("MVG required input path invalid:" + value)
            path = None
        is_path = force_file or _looks_like_path(value)
        is_identifier = role in {"capability_order", "requirement_scope"} or (role == "task_contract" and not is_path)
        exists = not is_identifier and path is not None and path.is_file()
        classification = "identifier" if is_identifier else "file" if exists else "planned" if planned else "context" if (is_path or required) else "identifier"
        if required and not exists:
            raise ValueError("MVG required input missing:" + value)
        prior = inventory.get(value)
        if prior is not None and ((prior["classification"] == "identifier") != (classification == "identifier")):
            raise ValueError("MVG input role collision:" + value)
        if prior is not None and prior.get("sha256") is not None and exists:
            current_sha = file_sha(path)
            if current_sha != prior.get("sha256"):
                raise ValueError("MVG input changed during freeze:" + value)
        row = inventory.setdefault(value, {"path": value, "classification": classification,
            "required": False, "roles": [], "sha256": file_sha(path) if exists else None,
            "normalized_sha256": normalized_file_sha(path) if exists else None,
            "prepared_path": prepared_path or ("references/" + value if exists else None)})
        row["required"] |= required
        if role not in row["roles"]:
            row["roles"].append(role)
        if prepared_path:
            row["prepared_path"] = prepared_path
        if exists:
            row.update(classification="file", sha256=file_sha(path), normalized_sha256=normalized_file_sha(path))
            row["prepared_path"] = row["prepared_path"] or ("references/" + value)
        elif planned:
            row["classification"] = "planned"

    cap_rel = capabilities_path.resolve().relative_to(root.resolve()).as_posix()
    bind(cap_rel, "capabilities", required=True, prepared_path="capabilities.v1.json")
    for rel, prepared in ((pm.SOURCE_MANIFEST, "source-manifest.v1.json"),
                          (pm.LEDGER, "source-blocks.v1.json"), (pm.SEMANTICS, "semantic-requirements.v1.json"),
                          (Path(".taskmaster/tasks/tasks.json"), "task-master.json")):
        bind(rel, "core_authority", required=True, prepared_path=prepared)
    for rel in pm.TASK_VIEWS:
        bind(rel, "task_view", required=True, prepared_path="task-views/" + rel.name)
    for row in load_json(root / pm.SOURCE_MANIFEST, {}).get("sources", []):
        bind(row["path"], "source", required=True, prepared_path="sources/" + _reference_path(row["path"]))
    for path in (root / "Game.Core/Contracts").rglob("*.cs"):
        bind(path.relative_to(root).as_posix(), "contract_context")
    task_statuses = {str(row.get("id")): str(row.get("status", "")).lower()
                     for row in load_json(root / ".taskmaster/tasks/tasks.json", {}).get("master", {}).get("tasks", [])}
    for row in pm._task_view_rows(root):
        owner_done = task_statuses.get(str(row.get("taskmaster_id")), "") == "done"
        for field in ("overlay_refs", "contractRefs", "test_refs", "source_refs"):
            for value in pm._list_field(row, field):
                file_ref = _looks_like_path(_reference_path(value))
                is_test = field == "test_refs"
                role = "task_contract" if field == "contractRefs" else "task_context"
                # source/overlay/test fields are explicit repository-file
                # references even when the filename has no extension (for
                # example LICENSE or Makefile).  Do not let a filename
                # heuristic downgrade a missing authoritative reference to
                # context.  ContractRefs may still contain symbolic contract
                # identifiers and retain the legacy distinction.
                explicit_file = field in ("source_refs", "overlay_refs")
                bind(value, role, required=explicit_file or (is_test and owner_done) or
                     (file_ref and not is_test),
                     force_file=field in ("source_refs", "overlay_refs", "test_refs"),
                     planned=(not owner_done and is_test))
        for acceptance in pm._list_field(row, "acceptance"):
            if "Refs:" in str(acceptance):
                for value in _acceptance_refs(acceptance):
                    ref = _reference_path(value)
                    is_test = ref.startswith(("Game.Core.Tests/", "Tests.Godot/"))
                    bind(value, "acceptance_context",
                         required=(owner_done if is_test else True),
                         force_file=True,
                         planned=is_test and not owner_done)
    for ref in evidence_refs or []:
        from _mvg_requirement_accounting import source_path, normalized_source
        from _planning_skill_common import text_sha
        canonical = source_path(ref)
        bind(ref, "explicit_evidence", required=True)
        inventory[canonical]['source_content_sha256'] = text_sha(normalized_source(repo_path(root, canonical).read_bytes()))

    formal = readiness["formal_ready"] is True
    bind(DEFAULT_EXTRACTION_SNAPSHOT, "chapter5_extraction", required=formal)
    tasks = []
    for task in readiness["tasks"]:
        bound = {"task_id": task["task_id"], "ready": task["ready"], "reason": task["reason"]}
        for kind, path in (("readiness", readiness_path_for_task(root, task["task_id"])),
                           ("reconciliation", reconciliation_path_for_task(root, task["task_id"]))):
            rel = path.relative_to(root).as_posix()
            bind(rel, "chapter5_" + kind, required=formal)
            bound[kind] = deepcopy(inventory[rel])
        payload = load_json(readiness_path_for_task(root, task["task_id"]), {})
        for key in ("schema_version", "source_revision", "extraction_b_snapshot_id", "cache_key",
                    "input_fingerprint", "reconciliation_sha256", "closure_allowed"):
            bound[key] = deepcopy(payload.get(key))
        reconciliation = load_json(reconciliation_path_for_task(root, task["task_id"]), {})
        for kind in ("contracts", "adrs"):
            for row in (reconciliation.get("authority_scope") or {}).get(kind, []):
                bind(row["path"], "chapter5_authority", required=formal)
        tasks.append(bound)

    predecessor = {"status": "absent", "path": None, "sha256": None}
    if manifest_path is not None:
        rel = manifest_path.resolve().relative_to(root.resolve()).as_posix()
        predecessor["path"] = rel
        if manifest_path.is_file():
            bind(rel, "predecessor", required=True, prepared_path="existing-manifest.json")
            predecessor.update(status="present", sha256=file_sha(manifest_path))
            baseline = load_json(manifest_path, {})
            for flow in baseline.get("flows", []):
                for value in flow.get("source_paths", []):
                    bind(value, "predecessor_source", required=True)
                for handoff in flow.get("handoffs", []):
                    bind(handoff["contract_ref"], "predecessor_contract", required=True)
            for test in baseline.get("tests", []):
                bind(test["path"], "predecessor_test", required=test.get("state") != "planned",
                     planned=test.get("state") == "planned")

    capabilities = load_json(capabilities_path, {})
    semantics = load_json(root / pm.SEMANTICS, {})
    # Keep non-path identity values in the inventory as identifiers. They are
    # binding inputs, while event IDs and planned obligations are not files.
    for cap in capabilities.get("capabilities", []):
        bind(cap.get("capability_id"), "capability_order")
        for rid in cap.get("requirement_ids", []):
            bind(rid, "requirement_scope")
    from _mvg_capability_generation import capability_scopes
    scope = pm._manifest_planning_scope(load_json(manifest_path, {}), pm._task_view_rows(root)) \
        if predecessor["status"] == "present" else None
    return {"schema_version": ENVELOPE_SCHEMA, "run_id": run_id,
        "capabilities": {"path": cap_rel, "sha256": file_sha(capabilities_path),
                         "source_revision": capabilities.get("source_revision"),
                         "schema_version": capabilities.get("schema_version")},
        "capability_order": [{"source_index": i, "capability_id": row["capability_id"],
                              "requirement_ids": deepcopy(row.get("requirement_ids", []))}
                             for i, row in enumerate(capabilities.get("capabilities", []))],
        "scopes": capability_scopes(capabilities, semantics, scope),
        "chapter5": {"formal_ready": formal, "tasks": tasks,
                     "extraction": deepcopy(inventory[DEFAULT_EXTRACTION_SNAPSHOT.as_posix()])},
        "inventory": sorted(inventory.values(), key=lambda row: row["path"]), "predecessor": predecessor}


def validate_envelope(root, prepared, state, *, check_originals=True):
    """Validate the unified index and every bound copy without resealing old input."""
    drift = []
    identity = None
    envelope = {}
    try:
        index = load_json(prepared / "analysis-index.json", None)
        if not isinstance(index, dict):
            raise ValueError("analysis-index is not an object")
        from _mvg_requirement_routes import protocol_errors
        drift.extend(protocol_errors(index))
        from _mvg_requirement_accounting import protocol_errors as accounting_protocol_errors
        drift.extend(accounting_protocol_errors(index))
        identity = index.get("analysis_identity_sha256")
        canonical_index = dict(index)
        canonical_index.pop("analysis_identity_sha256", None)
        canonical_index.pop("repository_identity", None)
        if canonical_sha(canonical_index) != identity or identity != state.get("analysis_identity_sha256"):
            drift.append("analysis-input/analysis-index.json:analysis_identity")
        for key in ("checkpoint_strategy", "checkpoint_schema_version", "requirement_routes_protocol", "requirement_accounting_protocol"):
            if index.get(key) != state.get(key):
                drift.append("run:" + key)
        envelope = index.get("input_envelope")
        if not isinstance(envelope, dict) or envelope.get("schema_version") != ENVELOPE_SCHEMA:
            drift.append("analysis-input/analysis-index.json:input_envelope_missing")
            envelope = {}
        for key in ("mvg.run_invocation_limit", "mvg.run_invocation_limit_source"):
            if key in index or key in envelope:
                if (canonical_sha(index.get(key)) != canonical_sha(state.get(key))
                        or canonical_sha(envelope.get(key)) != canonical_sha(index.get(key))):
                    drift.append("run:" + key)
        if "mvg.run_invocation_limit" in index:
            limit = index["mvg.run_invocation_limit"]
            if type(limit) is not int or limit <= 0:
                drift.append("input_envelope:mvg_run_invocation_limit_invalid")
        if envelope.get("run_id") != state.get("run_id"):
            drift.append("input_envelope:run_id")
        index_task_scope = [str(value) for value in (index.get("task_scope") or [])]
        state_task_scope = [str(value) for value in (state.get("task_scope") or [])]
        if index_task_scope != state_task_scope:
            drift.append("run:task_scope")
        if index.get("planning_scope") != state.get("planning_scope"):
            drift.append("run:planning_scope")
        capabilities = envelope.get("capabilities") if isinstance(envelope, dict) else None
        if isinstance(capabilities, dict):
            if capabilities.get("path") != state.get("capabilities_path"):
                drift.append("run:capabilities_path")
            if capabilities.get("sha256") != state.get("capabilities_sha256"):
                drift.append("run:capabilities_sha256")
        predecessor = envelope.get("predecessor", {}) if isinstance(envelope, dict) else {}
        if predecessor.get("path") != state.get("manifest_path"):
            drift.append("run:manifest_path")
        expected_manifest_sha = state.get("existing_manifest_sha256")
        if predecessor.get("status") == "present" and predecessor.get("sha256") != expected_manifest_sha:
            drift.append("run:existing_manifest_sha256")
        if isinstance(envelope.get("chapter5"), dict) and envelope["chapter5"].get("formal_ready") != (state.get("formal_ready") is True):
            drift.append("input_envelope:formal_ready")
        if (state.get("input_envelope_sha256") is not None
                and canonical_sha(envelope) != state.get("input_envelope_sha256")):
            drift.append("input_envelope:sha256")
        files = index.get("files")
        if not isinstance(files, dict):
            raise ValueError("analysis-index files is not an object")
        allowed = {"analysis-index.json", *files.keys()}
        for path in prepared.rglob("*"):
            if path.is_file() and path.relative_to(prepared).as_posix() not in allowed:
                drift.append("analysis-input/extra-file:" + path.relative_to(prepared).as_posix())
        for rel, expected in files.items():
            path = repo_path(prepared, rel)
            if not path.is_file() or file_sha(path) != expected:
                drift.append("analysis-input/" + rel)
        inventory = envelope.get("inventory")
        if not isinstance(inventory, list):
            raise ValueError("input envelope inventory is not a list")
        for row in inventory:
            if not isinstance(row, dict) or not row.get("path"):
                raise ValueError("input envelope inventory row is invalid")
            if check_originals and row.get("classification") not in {"identifier", "planned"}:
                path = repo_path(root, row["path"])
                actual = file_sha(path) if path.is_file() else None
                normalized = normalized_file_sha(path) if path.is_file() else None
                content_matches = False
                if row.get('source_content_sha256') and path.is_file():
                    from _mvg_requirement_accounting import normalized_source
                    from _planning_skill_common import text_sha
                    content_matches = text_sha(normalized_source(path.read_bytes())) == row['source_content_sha256']
                if actual != row.get("sha256") and normalized != row.get("normalized_sha256") and not content_matches:
                    drift.append(row["path"])
            if row.get("sha256") is not None:
                prepared_path = row.get("prepared_path")
                if not isinstance(prepared_path, str):
                    raise ValueError("input envelope prepared_path is invalid")
                path = repo_path(prepared, prepared_path)
                if not path.is_file() or file_sha(path) != row["sha256"]:
                    drift.append("analysis-input/" + prepared_path)
        predecessor = envelope.get("predecessor", {})
        if check_originals and predecessor.get("status") == "absent" and predecessor.get("path"):
            if repo_path(root, predecessor["path"]).is_file():
                drift.append(predecessor["path"])
        if check_originals and envelope.get("chapter5", {}).get("formal_ready") is True:
            from chapter5_semantic_reconciliation import load_task_readiness
            for task in envelope["chapter5"]["tasks"]:
                ok, _, reason = load_task_readiness(root, task["task_id"])
                if not ok:
                    drift.append("chapter5/task-" + task["task_id"] + ":" + reason)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, UnicodeError) as exc:
        drift.append("input-envelope-invalid:" + str(exc))
    drift = sorted(set(drift))
    atomic_json(prepared.parent / "input-freshness.json", {
        "status": "blocked" if drift else "current", "run_id": state.get("run_id"),
        "analysis_identity_sha256": identity, "drift": drift})
    if drift:
        raise ValueError("MVG input drift: " + ",".join(drift))
    return envelope


def input_identity(prepared):
    index = load_json(prepared / "analysis-index.json", {})
    envelope = index.get("input_envelope")
    if not isinstance(envelope, dict):
        raise ValueError("MVG input envelope missing; prepare a new run")
    return {"run_id": envelope["run_id"], "analysis_identity_sha256": index["analysis_identity_sha256"],
            "envelope_sha256": canonical_sha(envelope)}
