"""Read-only adaptation of a completed governed closure to ADR-0039 recovery.

This module owns no registry, journal, checkpoint, authorization or model call.
The original whole-closure proof remains historical; the current candidate uses
the existing external envelope and must pass the current structure owners.
"""
from __future__ import annotations

import base64
from copy import deepcopy

import _b_route_codec as codec
import _b_route_candidate as candidate
from _planning_skill_common import canonical_sha, load_json


def frozen(prepared):
    return load_json(prepared / "b-route-prepared.json")


def _documents(inputs):
    documents = {}
    for row in inputs["evidence"]:
        if row["path"] not in inputs["closure"]["source_paths"]:
            continue
        raw = row["text"].encode("utf-8")
        if codec.raw_digest(raw) != row["sha256"]:
            raise ValueError("b_route_recovery_original_bytes_changed:" + row["path"])
        documents[row["path"]] = (raw, None)
    for row in inputs["contexts"]:
        if "raw_base64" not in row:
            continue
        raw = base64.b64decode(row["raw_base64"], validate=True)
        if codec.raw_digest(raw) != row["raw_digest"]:
            raise ValueError("b_route_recovery_original_bytes_changed:" + row["path"])
        if row["path"] in documents and documents[row["path"]][0] != raw:
            raise ValueError("b_route_recovery_original_bytes_ambiguous:" + row["path"])
        documents[row["path"]] = (raw, row["kind"])
    return documents


def _rows(value):
    # These are the existing complete JSON document containers, never a walk
    # through arbitrary nested ID-bearing references or planning_relations.
    if isinstance(value, list):
        return [("/" + str(index), row) for index, row in enumerate(value)]
    if isinstance(value, dict) and "capability_id" in value:
        # A complete root row keeps the RFC 6901 empty root pointer. Its
        # unknown nested fields are part of that row, never more definitions.
        return [("", value)]
    if isinstance(value, dict) and isinstance(value.get("capabilities"), list):
        return [("/capabilities/" + str(index), row) for index, row in enumerate(value["capabilities"])]
    return []


def binding(prepared, scope):
    inputs = frozen(prepared)["inputs"]
    target = inputs["contract"]["scope"]
    if (scope.get("unit_kind") != "governed_planning_closure" or scope.get("scope") != target
            or scope.get("closure") != inputs["closure"] or target["kind"] != "capability"
            or len(target["ids"]) != 1):
        raise ValueError("b_route_recovery_requires_single_capability_target")
    matches = []
    declared_json = {row["path"] for row in inputs["contexts"] if row["format"] == "json"}
    for path, (raw, _kind) in _documents(inputs).items():
        if not (path.lower().endswith(".json") or path in declared_json):
            continue
        for pointer, row in _rows(codec.strict_json_loads(raw)):
            if isinstance(row, dict) and row.get("capability_id") == target["ids"][0]:
                matches.append({"capability": deepcopy(row), "path": path, "json_pointer": pointer,
                                "raw_digest": codec.raw_digest(raw)})
    if len(matches) != 1:
        raise ValueError("b_route_recovery_complete_input_row_not_unique:" + str(len(matches)))
    return matches[0]


def capability(prepared, scope):
    return binding(prepared, scope)["capability"]


def _semantic_document(raw, *, structured=False):
    # JSON object key order/format are not semantic changes. Text, array order,
    # types, unknown fields and all values remain significant.
    return codec.strict_json_loads(raw) if structured else raw.decode("utf-8", errors="strict")


def dependency(prepared, scope, base, proposal):
    envelope = frozen(prepared)
    inputs = envelope["inputs"]
    bound = binding(prepared, scope)
    content = proposal["content"]
    closure = inputs["closure"]
    source_paths = set(closure["source_paths"])
    # Requirement and source meaning use the existing native owner. Manifest
    # headers, audit identities and other catalog entries are not local meaning.
    proof = inputs["global_proof"]
    blocks = candidate.unique(proof["ledger"]["blocks"], lambda row: row["block_id"], "source_blocks")
    # Selected PlanRefs keep their own source namespace. They are never
    # mistaken for proposals owned by today's native manifest/ledger.
    root = prepared.resolve().parents[4]
    store = candidate.frozen_bytes(root, envelope["resume_ref"], envelope, candidate.sources.Observations(root))
    _owners, _resolve, plans = candidate.check_owners(content, store)
    inherited = {}
    for plan in plans:
        manifest, _ledger, old_blocks = candidate.source_documents(plan["source_identity"], store)
        for requirement in plan["requirements"]:
            inherited[requirement["requirement_id"]] = candidate.requirement_source(requirement, old_blocks, manifest)
    meanings = {}
    for row in content["requirements"]:
        if row["requirement_id"] in inherited:
            meanings[row["requirement_id"]], paths = inherited[row["requirement_id"]]
        else:
            meanings[row["requirement_id"]], paths = candidate.requirement_source(row, blocks, proof["manifest"])
        source_paths.update(paths)
    documents = {}
    formats = {row["path"]: row["format"] for row in inputs["contexts"]}
    for path, (raw, kind) in _documents(inputs).items():
        if path == bound["path"]:
            # The complete row is the semantic unit. Original file/locator/raw
            # identity is verified independently, not made into the match key.
            container = codec.strict_json_loads(raw)
            excluded = {"capabilities"}
            if isinstance(container, dict) and container.get("schema_version") == "newrouge.capabilities.v1":
                # Only the existing native publisher's known provenance fields
                # are excluded. Unknown container fields retain their meaning.
                excluded.update({"source_revision", "generated_at_utc"})
            documents[path] = {"capability": bound["capability"], "container":
                {key: deepcopy(value) for key, value in container.items()
                 if key not in excluded}
                if isinstance(container, dict) else None}
        elif path in source_paths or kind not in {"capability", "task", None}:
            documents[path] = _semantic_document(raw, structured=
                formats.get(path, "json" if path.lower().endswith(".json") else "text") == "json")
    constraints = [{key: deepcopy(row[key]) for key in ("path", "format")}
                   | {"value": _semantic_document(base64.b64decode(row["raw_base64"], validate=True), structured=row["format"] == "json")}
                   for row in inputs["constraints"]]
    # Typed references and OwnedRefs retain their full definitions and exact
    # bytes. Do not let the context kind hide a referenced Task/catalog file.
    references = []
    for row in candidate.walk(content):
        if set(row) == {"owner", "ref", "files"}:
            if row["owner"] not in {"source_manifest", "source_ledger"}:
                references.append(deepcopy(row))
        elif set(row) == {"path", "schema_version", "entity_id", "revision", "digest", "verification_mode", "codec_version"}:
            references.append(deepcopy(row))
    return {"capability": bound["capability"], "closure": {key: deepcopy(closure[key])
        for key in ("mode", "reason", "source_paths", "entities")}, "sources": documents,
        "requirements": deepcopy(content["requirements"]), "source_meanings": meanings,
        "constraints": constraints, "references": references,
        "accepted_boundaries": deepcopy(base.get("content")),
        "result_boundaries": {key: deepcopy(value) for key, value in content.items() if key != "source_identity"}}


def replay_delta(root, state, prepared, base, delta, scope, *, check_originals=True):
    """Replay unchanged source delta into an honest current external envelope."""
    import _b_route_planning_runtime as runtime
    from _b_route_record_owners import resolve_owned_ref
    current = runtime.frozen_input(root, state, prepared=prepared, check_originals=check_originals)
    proposal = runtime.merge(base, delta, scope)
    original_digest = canonical_sha(proposal)
    proposal["input_identity"] = current["input_identity"]
    proposal["provenance"] = {"kind": "external", "declaration": "Completed planning adoption from " + original_digest,
        "upstream_model_history": "declared_model", "draft_chain": [], "final_draft_identity": None}
    store = candidate.frozen_bytes(root, runtime.descriptor(state)["prepared_ref"], current, runtime.sources.Observations(root))
    identity = proposal["content"]["source_identity"]
    proof = current["inputs"]["global_proof"]
    # Keep the native source locators; only current native identity is rebound.
    # If those locators no longer resolve, the existing owner rejects adoption.
    for name, owner in (("manifest_ref", "source_manifest"), ("ledger_ref", "source_ledger")):
        path = identity[name]["ref"].partition("#")[0]
        raw = store.read(path)
        expected = proof["manifest" if owner == "source_manifest" else "ledger"]
        if canonical_sha(codec.strict_json_loads(raw)) != canonical_sha(expected):
            raise ValueError("b_route_recovery_current_source_locator_incompatible:" + path)
        identity[name] = {"owner": owner, "ref": identity[name]["ref"],
            "files": [{"path": path, "raw_digest": codec.raw_digest(raw)}]}
        resolve_owned_ref(identity[name], read_bytes=store.read, contract_sources=store.contracts)
    identity["source_revision"] = proof["manifest"]["source_revision"]
    identity["source_manifest_digest"] = proof["manifest"]["manifest_sha256"]
    if runtime.preservation(base, proposal):
        raise ValueError("recovery_delta_mutates_accepted_state")
    errors = runtime.admission_machine(root, state, proposal, check_originals=check_originals)
    if errors:
        raise ValueError("recovery_current_delta_incompatible:" + str(errors))
    return proposal
