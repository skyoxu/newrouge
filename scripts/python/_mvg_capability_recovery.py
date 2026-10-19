"""Exact-content completed recovery, persistent clear epochs, and adoption proofs."""
from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
import os
from pathlib import Path

from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json, repo_path
from _mvg_capability_checkpoint import STRATEGY as CHECKPOINT_STRATEGY, coordinator_lock, load_checkpoint

SCHEMA = "newrouge.mvg-completed-registry.v1"
ADOPTION = "newrouge.mvg-capability-adoption.v1"


def capability_hash(capability):
    if not isinstance(capability, dict) or not isinstance(capability.get("capability_id"), str):
        raise ValueError("recovery_capability_object_invalid")
    return canonical_sha(capability)


def store_root(root, state=None):
    configured = (state or {}).get("recovery", {}).get("store") or os.environ.get("SC_MVG_RECOVERY_ROOT")
    return Path(configured).resolve() if configured else (root / "logs/ci/mvg-recovery").resolve()


def registry(root, state=None):
    store = store_root(root, state)
    value = load_json(store / "registry.json", None)
    if value is None:
        return {"schema_version": SCHEMA, "epoch": 0, "entries": [], "revoked": []}
    if (not isinstance(value, dict) or value.get("schema_version") != SCHEMA
            or type(value.get("epoch")) is not int or value["epoch"] < 0
            or not isinstance(value.get("entries"), list) or not isinstance(value.get("revoked"), list)):
        raise ValueError("recovery_registry_invalid")
    return value


def bind_epoch(root, state):
    store = store_root(root, state)
    store.mkdir(parents=True, exist_ok=True)
    with coordinator_lock(store):
        value = registry(root, state)
        requested_epoch = os.environ.get("SC_MVG_RECOVERY_EPOCH")
        initial_epoch = int(requested_epoch) if requested_epoch is not None else value["epoch"]
        state.setdefault("recovery", {"store": str(store), "epoch": initial_epoch})
        assert_epoch(root, state, value=value)
        if not (store / "registry.json").is_file():
            atomic_json(store / "registry.json", value)


def assert_epoch(root, state, *, value=None):
    value = registry(root, state) if value is None else value
    if state.get("recovery", {}).get("epoch") != value["epoch"]:
        raise ValueError("mvg_recovery_epoch_invalidated")


def assert_active_chain(root, state, run_dir):
    """Current consumers honor revocation independently of historical replay."""
    if state.get("checkpoint_strategy") != CHECKPOINT_STRATEGY:
        # Legacy runs have no hash-bound checkpoint pointers to validate.  The
        # legacy prefix remains local-only and is intentionally ineligible for
        # cross-run recovery/adoption.
        return
    value = registry(root, state)
    assert_epoch(root, state, value=value)
    for index, step in enumerate(state.get("capability_selection", {}).get("selected", [])):
        if not isinstance(step, dict) or not isinstance(step.get("checkpoint"), dict):
            raise ValueError(f"recovery_selection_checkpoint_invalid:{index}")
        transaction_id = str(step["checkpoint"].get("transaction_id") or "")
        if not transaction_id:
            raise ValueError(f"recovery_selection_checkpoint_invalid:{index}")
        if transaction_id in value["revoked"]:
            raise ValueError("recovery_source_revoked")
        if step.get("kind") == "adoption":
            receipt = load_json(repo_path(run_dir, step["receipt_path"]))
            _eligible(root, state, receipt["source"])


def clear(root):
    """The caller holds the authenticated project operation lock."""
    store = store_root(root)
    store.mkdir(parents=True, exist_ok=True)
    with operation_lock(root), coordinator_lock(store):
        previous = registry(root)
        value = {"schema_version": SCHEMA, "epoch": previous["epoch"] + 1, "entries": [], "revoked": []}
        # Keep the prior index as audit; only the epoch pointer is authoritative.
        atomic_json(store / "clears" / f"epoch-{previous['epoch']}.json", previous)
        atomic_json(store / "registry.json", value)
    return {"epoch": value["epoch"], "completed": 0, "runtime_verified": False}


@contextmanager
def operation_lock(root, state=None):
    """Serialize CLI generation and authenticated clear across service processes."""
    directory = store_root(root, state) / "activity"
    directory.mkdir(parents=True, exist_ok=True)
    with coordinator_lock(directory):
        yield


def _source_pointer(run_dir, state, step):
    return {"run_dir": str(run_dir.resolve()), "run_id": state["run_id"],
        "transaction_id": step["checkpoint"]["transaction_id"]}


def _dependency(prepared, scope, base, proposal):
    from _mvg_capability_generation import complete_scope_context, review_projection
    context = complete_scope_context(prepared, scope, base, proposal)
    # Global catalogs/revision/readiness identities are provenance, not the
    # local dependency key. Full relevant source bytes remain bound below.
    dependency = {key: deepcopy(context[key]) for key in (
        "requirements", "source_blocks", "task_views", "task_master", "evidence")}
    affected, requirements = review_projection(scope, base, proposal)
    flow_ids = {row["id"] for row in affected["manifest_candidate"]["flows"]}
    affected_requirements = set(requirements)

    def expand_shared_flows(value):
        """Bind shared baseline flows/handoffs, not only projected flow IDs."""
        flows = value["manifest_candidate"].get("flows", [])
        selected = set(flow_ids)
        changed = True
        while changed:
            changed = False
            for row in flows:
                rid_overlap = affected_requirements.intersection(row.get("requirement_ids", []))
                handoffs = row.get("handoffs", []) or []
                endpoint_overlap = any(
                    str(handoff.get(field, "")) in selected
                    for handoff in handoffs
                    for field in ("source_flow_id", "target_flow_id", "from_flow_id", "to_flow_id", "producer_flow_id", "consumer_flow_id")
                )
                if row.get("id") in selected or rid_overlap or endpoint_overlap:
                    if row.get("id") not in selected:
                        selected.add(row.get("id"))
                        changed = True
                    affected_requirements.update(row.get("requirement_ids", []))
        return selected

    # The dependency key must include baseline context that can affect a
    # shared handoff even when projection did not select that flow for review.
    flow_ids |= expand_shared_flows(base)
    flow_ids |= expand_shared_flows(proposal)

    def boundaries(value):
        flows = [row for row in value["manifest_candidate"].get("flows", []) if row["id"] in flow_ids]
        tests = {tid for row in flows for tid in row.get("test_ids", [])}
        result = {"flows": flows,
            "tests": [row for row in value.get("tests", []) if row["id"] in tests],
            "entrypoints": [row for row in value.get("entrypoints", []) if flow_ids.intersection(row.get("flow_ids", []))]}
        for field in ("coverage_table", "requirement_route_memberships", "requirement_verification", "requirement_evidence"):
            result[field] = [row for row in value.get(field, []) if row.get("requirement_id") in affected_requirements
                            and (field != "requirement_route_memberships" or row.get("flow_id") in flow_ids)]
        return deepcopy(result)

    dependency["accepted_boundaries"] = boundaries(base)
    dependency["result_boundaries"] = boundaries(proposal)
    return dependency


def register_committed(root, run_dir, state):
    """Only disk-selected checkpoints are eligible; staged payloads are ignored."""
    # Legacy runs deliberately omit the checkpoint protocol.  They can still
    # resume their persisted selected prefix through the legacy coordinator,
    # but there is no hash-bound checkpoint payload that can be registered for
    # cross-run adoption.  Treat that mode as non-adoptable instead of
    # dereferencing a missing ``checkpoint`` field.
    if (not state.get("recovery")
            or state.get("checkpoint_strategy") != CHECKPOINT_STRATEGY):
        return
    disk = load_json(run_dir / "run.json", {})
    if disk != state:
        raise ValueError("recovery_uncommitted_state")
    store = store_root(root, state)
    with coordinator_lock(store):
        value = registry(root, state)
        assert_epoch(root, state, value=value)
        selected = state.get("capability_selection", {}).get("selected", [])
        ancestry = []
        for index, step in enumerate(selected):
            token = step["checkpoint"]["transaction_id"]
            if step.get("kind") == "adoption":
                ancestry.append(step["adoption"]["source_transaction_id"])
                ancestry.append(token)
                continue
            ancestry.append(token)
            if token in value["revoked"] or any(item.get("transaction_id") == token for item in value["entries"]):
                continue
            payload = load_checkpoint(run_dir, step["checkpoint"])
            scope = step["record"]["scope"]
            snapshot = deepcopy(state)
            ledger = snapshot["capability_selection"]
            ledger.update(selected=deepcopy(selected[:index + 1]), current=None,
                checkpoint_head=deepcopy(step["checkpoint"]), accepted_sha256=payload["result_sha256"])
            # A prefix snapshot carries no whole-run publication/audit claim.
            for key in ("global_audit", "selected_admission_review", "global_conflict_report"):
                snapshot.pop(key, None)
            snapshot.update(selection_status="pending", phase="committed-prefix")
            target = run_dir / "completed-recovery" / (token[7:] + ".json")
            if target.is_file():
                existing = load_json(target)
                if existing != snapshot:
                    # Keep the first immutable snapshot, including original costs.
                    snapshot = existing
            else:
                atomic_json(target, snapshot)
            entry = {"epoch": value["epoch"], "capability_id": scope["capability_id"],
                "capability_sha256": capability_hash(scope["capability"]),
                **_source_pointer(run_dir, state, step), "order_index": index,
                "checkpoint": deepcopy(step["checkpoint"]), "ancestry": deepcopy(ancestry),
                "state_path": target.relative_to(run_dir).as_posix(), "state_sha256": file_sha(target),
                "dependency_sha256": canonical_sha(_dependency(run_dir / "analysis-input", scope,
                    payload["accepted_seed"], payload["accepted"]))}
            value["entries"].append(entry)
        atomic_json(store / "registry.json", value)


def revoke(root, state, transactions):
    """Write-ahead invalidation fails closed even if the reopen pointer write fails."""
    if not state.get("recovery"):
        return
    store = store_root(root, state)
    with coordinator_lock(store):
        value = registry(root, state)
        assert_epoch(root, state, value=value)
        revoked = set(value["revoked"]) | set(transactions)
        changed = True
        while changed:
            before = set(revoked)
            revoked.update(entry["transaction_id"] for entry in value["entries"]
                if set(entry.get("ancestry", [])) & revoked)
            changed = before != revoked
        value["revoked"] = sorted(revoked)
        atomic_json(store / "registry.json", value)


def _eligible(root, state, entry, *, historical=False):
    value = registry(root, state)
    if not historical:
        assert_epoch(root, state, value=value)
        if entry.get("epoch") != value["epoch"] or set(entry.get("ancestry", [])) & set(value["revoked"]):
            raise ValueError("recovery_source_revoked")
        if entry not in value["entries"]:
            raise ValueError("recovery_registry_entry_changed")


def verify_source(root, state, entry, *, historical=False):
    from _mvg_capability_selection import verified_prefix
    _eligible(root, state, entry, historical=historical)
    source = Path(entry["run_dir"]).resolve()
    canonical_recovery_root = (root / "logs/ci/mvg-planning").resolve()
    if not source.is_relative_to(canonical_recovery_root):
        raise ValueError("recovery_source_path_outside_canonical_root")
    expected_run_id = str(entry.get("run_id") or "")
    # A run directory is exactly ``<canonical root>/<run id>``.  Checking the
    # parent against ``canonical root`` keeps valid recovery sources usable
    # while the ``is_relative_to`` guard above rejects nested path escapes.
    if not expected_run_id or source.parent != canonical_recovery_root:
        raise ValueError("recovery_source_run_id_mismatch")
    disk_state = load_json(source / "run.json", {})
    if disk_state.get("run_id") != expected_run_id:
        raise ValueError("recovery_source_run_id_mismatch")
    path = repo_path(source, entry["state_path"])
    if (not path.is_relative_to(source) or not path.is_file() or file_sha(path) != entry["state_sha256"]):
        raise ValueError("recovery_source_state_changed")
    original = load_json(path)
    pointer = original["capability_selection"]["selected"][entry["order_index"]]["checkpoint"]
    if pointer != entry["checkpoint"] or pointer["transaction_id"] != entry["transaction_id"]:
        raise ValueError("recovery_source_checkpoint_changed")
    disk = disk_state
    if not historical and not any(row.get("checkpoint") == pointer
            for row in disk.get("capability_selection", {}).get("selected", [])):
        raise ValueError("recovery_source_not_committed")
    original_root = source.parents[3]
    # Validate old proof against its immutable envelope, never current authority.
    scopes, _, _ = verified_prefix(original_root, source, original,
        check_originals=False, recover_counters=False)
    payload = load_checkpoint(source, pointer)
    scope = scopes[entry["order_index"]]
    if capability_hash(scope["capability"]) != entry["capability_sha256"]:
        raise ValueError("recovery_source_capability_changed")
    if canonical_sha(_dependency(source / "analysis-input", scope, payload["accepted_seed"],
            payload["accepted"])) != entry["dependency_sha256"]:
        raise ValueError("recovery_source_dependencies_changed")
    return payload, scope


def replay(root, run_dir, state, scope, base, entry, *, historical=False):
    from _mvg_capability_append import merge_append, preservation_errors
    import plan_mvg as pm
    payload, source_scope = verify_source(root, state, entry, historical=historical)
    if capability_hash(scope["capability"]) != entry["capability_sha256"]:
        raise ValueError("recovery_capability_content_changed")
    # Reopening requires fresh source-backed resolution, never old admission.
    from _mvg_global_audit import reopen_context
    if reopen_context(state, scope) is not None:
        raise ValueError("recovery_reopen_requires_fresh_resolution")
    proposal = merge_append(base, payload["delta"], scope)
    if preservation_errors(base, proposal):
        raise ValueError("recovery_delta_mutates_accepted_state")
    if canonical_sha(_dependency(run_dir / "analysis-input", scope, base, proposal)) != entry["dependency_sha256"]:
        raise ValueError("recovery_current_dependencies_incompatible")
    errors = pm.candidate_admission_errors(root, state, proposal,
        append_requirement_ids=set(scope["cumulative_requirement_ids"]), check_originals=not historical)
    if errors:
        raise ValueError("recovery_current_delta_incompatible:" + str(errors))
    return proposal, payload


def try_adopt(root, run_dir, state, scope, index, base):
    digest = capability_hash(scope["capability"])
    value = registry(root, state)
    assert_epoch(root, state, value=value)
    failures = []
    for entry in reversed(value["entries"]):
        if entry.get("capability_sha256") != digest:
            continue
        try:
            proposal, payload = replay(root, run_dir, state, scope, base, entry)
            receipt = {"schema_version": ADOPTION, "run_id": state["run_id"],
                "analysis_identity_sha256": state["analysis_identity_sha256"], "epoch": value["epoch"],
                "capability_sha256": digest, "source": deepcopy(entry),
                "base_sha256": canonical_sha(base), "result_sha256": canonical_sha(proposal),
                "verification": "original_frozen_proof_and_current_dependency_delta_replay"}
            path = run_dir / "adoptions" / (canonical_sha(receipt)[7:] + ".json")
            atomic_json(path, receipt)
            record = {"kind": "adoption", "scope": deepcopy(scope), "base_sha256": canonical_sha(base),
                "delta": deepcopy(payload["delta"]), "proposal_sha256": canonical_sha(proposal),
                "adoption": {"path": path.relative_to(run_dir).as_posix(), "sha256": file_sha(path)}}
            record["record_sha256"] = canonical_sha(record)
            step = {"kind": "adoption", "selected_candidate": "reused", "generation":
                state["capability_selection"].get("generation", 1), "record": record,
                "proposal_sha256": canonical_sha(proposal), "input_identity": {
                    "base_sha256": canonical_sha(base), "run_id": state["run_id"], "order_index": index},
                "receipt_path": path.relative_to(run_dir).as_posix(), "receipt_sha256": file_sha(path),
                "adoption": {**record["adoption"], "source_transaction_id": entry["transaction_id"]}}
            return proposal, record, step
        except (OSError, ValueError, RuntimeError, KeyError, TypeError, IndexError) as exc:
            failures.append({"source_transaction_id": entry.get("transaction_id"), "reason": str(exc)})
    atomic_json(run_dir / "recovery-lookups" / f"scope-{index + 1}.json", {
        "capability_sha256": digest, "epoch": value["epoch"], "failures": failures, "status": "generate_fresh"})
    return None


def verify_adoption_record(root, state, prepared, scope, base, proposal, record, *, check_originals=True):
    pointer = record["adoption"]
    # Candidate bundles carry the same frozen envelope in nested workspaces;
    # adoption receipts belong to the coordinator run, never that candidate.
    run_dir = root / "logs/ci/mvg-planning" / state["run_id"]
    path = repo_path(run_dir, pointer["path"])
    if not path.is_relative_to(run_dir.resolve()) or file_sha(path) != pointer["sha256"]:
        raise ValueError("adoption_receipt_changed")
    receipt = load_json(path)
    if (receipt.get("schema_version") != ADOPTION or receipt.get("run_id") != state["run_id"]
            or receipt.get("analysis_identity_sha256") != state["analysis_identity_sha256"]
            or receipt.get("epoch") != state.get("recovery", {}).get("epoch")
            or receipt.get("capability_sha256") != capability_hash(scope["capability"])
            or receipt.get("base_sha256") != canonical_sha(base)
            or receipt.get("result_sha256") != canonical_sha(proposal)):
        raise ValueError("adoption_identity_changed")
    revised, payload = replay(root, run_dir, state, scope, base, receipt["source"], historical=not check_originals)
    if revised != proposal or payload["delta"] != record["delta"]:
        raise ValueError("adoption_replay_changed")
    return proposal


def progress(root, run_dir, state):
    """Reconstruct only the committed prefix; attempts never authorize display."""
    from _mvg_capability_selection import verified_prefix
    assert_active_chain(root, state, run_dir)
    committed = deepcopy(state)
    ledger = committed["capability_selection"]
    ledger["current"] = None
    # A live request reserves its charge before the worker writes its journal.
    # Progress verifies only the call prefix ending at the last committed rank.
    # Those calls and selected artifacts are immutable even while a later scope
    # is updating mailbox outcomes and lineage counters.
    reservations = {step.get("reservation_id") for step in ledger["selected"]
        if step.get("kind") != "adoption"}
    cutoff = max((row["number"] for row in ledger.get("calls", [])
        if row.get("reservation_id") in reservations), default=0)
    if None in reservations:
        completed_ids = {row["record"]["scope"]["capability_id"] for row in ledger["selected"]}
        cutoff = max((row["number"] for row in ledger.get("calls", [])
            if row.get("capability_id") in completed_ids), default=cutoff)
    # Reopen archives bind the complete nonrefundable prior call prefix, even
    # when the corresponding checkpoints have been invalidated. Only the
    # later live dispatch suffix is excluded from the read-only projection.
    from _mvg_global_audit import historical_states
    for prior in historical_states(run_dir, committed):
        cutoff = max(cutoff, len(prior["capability_selection"].get("calls", [])))
    ledger["calls"] = ledger.get("calls", [])[:cutoff]
    ledger["total_invocations"] = cutoff
    ledger["lineage_invocations"] = {label: sum(row.get("candidate") == label for row in ledger["calls"])
        for label in ledger["lineage_invocations"]}
    scopes, proposal, records = verified_prefix(root, run_dir, committed,
        check_originals=False, recover_counters=False)
    selected = state["capability_selection"]["selected"]
    current = state["capability_selection"].get("current") or {}
    projection = {"epoch": state["recovery"]["epoch"], "run_id": state["run_id"],
        "completed": len(records), "total": len(scopes), "current": current.get("capability_id"),
        "status": "partial_planning", "runtime_verified": False,
        "items": [{"capability_id": scopes[i]["capability_id"],
            "provenance": "reused" if step.get("kind") == "adoption" else "new",
            "checkpoint": step["checkpoint"]} for i, step in enumerate(selected)],
        "proposal": proposal, "checkpoint_head": state["capability_selection"].get("checkpoint_head")}
    projection["sha256"] = canonical_sha(projection)
    return projection
