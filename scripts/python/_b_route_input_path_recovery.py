"""One typed short-path continuation of a proven undispatched preparation.

The failed R9 namespace, its consumed claim and all paid calls remain intact.
This is a local integrity boundary, not billing proof, model acceptance or an
automatic dispatch permission. No Windows/network/authentication setting changes.
"""
from copy import deepcopy
import ast
import json
from pathlib import Path
import re

import _b_route_codec as codec
import _b_route_sources as sources
import _b_route_partial_generation_recovery as partial

SCHEMA = "newrouge.b-route-input-path-recovery.v1"
REFERENCE = "b_route_input_path_recovery"
PRIOR_COMMIT = "61eb6ac9ce741c4d1c9dba03088f58a0ba6be8f1"
NAMESPACE = "p1"
WORKSPACE = partial.WORKSPACE


def require(value, reason):
    if not value:
        raise ValueError("b_route_input_path_recovery:" + reason)


def _old_record(root, old):
    # This exact archived R9 view has no path-recovery reference, so the old
    # partial validator and consumed old marker retain their original meaning.
    require(not old.get(REFERENCE), "nested_path_recovery_forbidden")
    import _b_route_execution_transition as transition
    require(transition.validate_transition(root, old) == old["b_route_execution_transition"]["transition_digest"],
            "archived_source_frame_changed")
    record = partial.validate_recovery(root, old)
    partial._claimed(root, old, record)
    return record


def retained_failure(root, state, append):
    root = Path(root).resolve()
    record = _old_record(root, state)
    run = sources.checked_path(root, record["run_ref"])
    ledger = state["capability_selection"]
    original = codec.strict_json_loads(partial.image_bytes(record["previous_run"]))
    original_append = codec.strict_json_loads(partial.image_bytes(record["previous_append"]))
    require(ledger["total_invocations"] == len(ledger["calls"]) == 8
            and partial.same(ledger["calls"], original["capability_selection"]["calls"])
            and ledger["lineage_invocations"] == {"candidate-1": 4, "candidate-2": 4}
            and ledger["terminal"] is True and ledger["selected"] == []
            and state["selection_status"] == "blocked"
            and state["selection_block_reason"] == "selection_blocked_insufficient_admitted_candidates",
            "not_exact_known_eight_call_failure")
    require(append["status"] == "blocked" and append["total_invocations"] == len(append["calls"]) == 4
            and partial.same(append["calls"], record["original_local_calls"])
            and partial.same(append["current"], record["original_current"])
            and partial.same(append["accepted"], original_append["accepted"])
            and append["completed"] == append["records"] == [], "changed_partial_or_attempt")
    errors = append.get("errors", [])
    require(len(errors) == 1 and errors[0].get("code") == "append_input_preparation_failed", "failure_kind")
    detail = errors[0].get("detail", "")
    require(detail.startswith("[Errno 2] No such file or directory: "), "not_known_path_failure")
    try:
        failed_path = Path(ast.literal_eval(detail.split(": ", 1)[1]))
    except (ValueError, SyntaxError, TypeError):
        require(False, "failure_path_shape")
    expected_parent = run / WORKSPACE / "capability-append" / partial.NAMESPACE / "c5/llm-sandbox/attempt-5/r"
    require(failed_path.parent == expected_parent
            and re.fullmatch(r"runner-input-integrity\.json\.[1-9][0-9]*\.[1-9][0-9]*\.[0-9a-f]{32}\.tmp", failed_path.name)
            and len(str(failed_path)) >= 260 and expected_parent.is_dir(), "failure_path_identity_or_length")
    failed_root = run / WORKSPACE / "capability-append" / partial.NAMESPACE
    files = partial._files(failed_root)
    require(bool(files["files"]) and not any("execution-binding" in name or name.endswith("/r.json")
            for name in files["files"]), "old_failure_must_be_unreserved")
    return record, files


def _record(root, state):
    reference = state.get(REFERENCE)
    require(type(reference) is dict and set(reference) == {"schema_version", "record_ref", "record_digest", "artifact_root"}
            and reference["schema_version"] == SCHEMA and Path(reference["artifact_root"]).resolve() == root, "typed_reference")
    path = sources.checked_path(root, reference["record_ref"])
    raw = codec.read_reference_bytes(root, reference["record_ref"])
    require(codec.raw_digest(raw) == reference["record_digest"], "record_changed")
    record = codec.strict_json_loads(raw)
    require(record["schema_version"] == SCHEMA and record["run_id"] == state["run_id"] == "c4"
            and record["namespace"] == NAMESPACE and record["retained_slots"] == 8
            and record["released"] == 0 and record["maximum_prefix_resumes"] == 1, "record_identity_or_refund")
    claim = partial.read(root, path.with_name("claim.json").relative_to(root).as_posix())
    require(claim == {"schema_version": SCHEMA, "record_digest": reference["record_digest"], "retained_slots": 8}, "preparation_claim")
    committed = partial.read(root, path.with_name("committed.json").relative_to(root).as_posix())
    require(committed == {"record_digest": reference["record_digest"],
                          "transition_digest": record["transition"]["transition_digest"]}, "partial_transaction")
    return path, record


def validate_recovery(root, state):
    """Read only; archived R9 and original partial records are never repaired."""
    root = Path(root).resolve()
    _, record = _record(root, state)
    old = codec.strict_json_loads(partial.image_bytes(record["previous_run"]))
    old_append = codec.strict_json_loads(partial.image_bytes(record["previous_append"]))
    require(record["prior_commit"] == old["b_route_execution_transition"]["current_commit"] == PRIOR_COMMIT
            and Path(record["prior_source_root"]).resolve()
                == Path(old["b_route_execution_transition"]["current_source_root"]).resolve(), "archived_source_identity_changed")
    prior_record, files = retained_failure(root, old, old_append)
    require(partial.same(files, record["failed_namespace"]), "failed_namespace_changed")
    require(partial.same(state[partial.REFERENCE], old[partial.REFERENCE])
            and partial.same(state["b_route_execution_transition"], record["transition"])
            and partial.same(state["b_route_execution_history"], record["history"]), "source_frame_changed")
    for field in ("runtime_identity", "planning_runtime", "b_route_campaign_funding", "b_route_review_recovery",
                  "b_route_synthesis_recovery", "mvg.run_invocation_limit", "b_route_output_schema_policy", "b_route_input_compact_policy"):
        require(partial.same(state[field], old[field]), "retained_identity_or_budget_changed:" + field)
    ledger, before = state["capability_selection"], old["capability_selection"]
    require(partial.same(ledger["calls"][:8], before["calls"])
            and type(ledger["total_invocations"]) is int and ledger["total_invocations"] == len(ledger["calls"])
            and 8 <= ledger["total_invocations"] <= 43
            and [row["number"] for row in ledger["calls"]] == list(range(1, ledger["total_invocations"] + 1))
            and ledger["lineage_invocations"]["candidate-1"] == 4
            and ledger["lineage_invocations"]["candidate-2"] == sum(row.get("candidate") == "candidate-2" for row in ledger["calls"])
            and partial._number(state["active_elapsed_seconds"]) and state["active_elapsed_seconds"] >= old["active_elapsed_seconds"],
            "paid_prefix_counter_or_clock_changed")
    run = sources.checked_path(root, record["run_ref"])
    require(record["run_ref"] == prior_record["run_ref"], "run_changed")
    for name, digest in record["immutable_files"].items():
        require(codec.raw_digest(codec.read_reference_bytes(run, name)) == digest, "old_file_changed:" + name)
    local = partial.read(run, WORKSPACE + "/capability-append/append-ledger.json")
    require(partial.same(local["calls"][:4], old_append["calls"])
            and type(local["total_invocations"]) is int and local["total_invocations"] == len(local["calls"]) >= 4
            and partial.same(local["binding"], old_append["binding"]), "local_prefix_changed")
    return record


def original_partial_record(root, state):
    record = validate_recovery(root, state)
    old = codec.strict_json_loads(partial.image_bytes(record["previous_run"]))
    return partial._record(Path(root).resolve(), old)[1]


def _resume_marker(state):
    return {"schema_version": SCHEMA + ".resume", "record_digest": state[REFERENCE]["record_digest"],
            "original_partial_record_digest": state[partial.REFERENCE]["record_digest"], "retained_slots": 8, "released": 0}


def claimed(root, state):
    root = Path(root).resolve()
    path, _ = _record(root, state)
    require(partial.same(partial.read(root, path.with_name("resume-claim.json").relative_to(root).as_posix()),
                         _resume_marker(state)), "resume_claim_missing_or_changed")


def claim_resume(root, state, current, ledger):
    root = Path(root).resolve()
    path, record = _record(root, state)
    old = codec.strict_json_loads(partial.image_bytes(record["previous_run"]))
    old_append = codec.strict_json_loads(partial.image_bytes(record["previous_append"]))
    require(partial.same(current, old_append["current"]) and ledger["total_invocations"] == 4
            and partial.same(ledger["calls"], old_append["calls"]), "not_exact_undispatched_continuation")
    prior_record = partial._record(root, old)[1]
    partial._claimed(root, old, prior_record)
    partial._durable(path.with_name("resume-claim.json"), _resume_marker(state), exclusive=True)


def prepare(root, run_dir, *, original_source_root, current_commit, prior_source_root, prior_commit=PRIOR_COMMIT):
    """Prepare a new local path epoch under lock; no request is dispatched."""
    import _b_route_execution_transition as transition
    from _mvg_capability_checkpoint import coordinator_lock
    root, run_dir = Path(root).resolve(), Path(run_dir).resolve()
    require(run_dir == sources.checked_path(root, "logs/ci/capability-planning/c4"), "explicit_run_required")
    with coordinator_lock(run_dir):
        raw_run = codec.read_reference_bytes(run_dir, "run.json")
        raw_append = codec.read_reference_bytes(run_dir, WORKSPACE + "/capability-append/append-ledger.json")
        old, append = codec.strict_json_loads(raw_run), codec.strict_json_loads(raw_append)
        _, failed = retained_failure(root, old, append)
        require(not old.get(REFERENCE) and prior_commit == PRIOR_COMMIT
                and old["b_route_execution_transition"]["current_commit"] == prior_commit
                and Path(old["b_route_execution_transition"]["current_source_root"]).resolve() == Path(prior_source_root).resolve(),
                "prior_source_changed")
        require(not (run_dir / WORKSPACE / "capability-append" / NAMESPACE).exists(), "short_namespace_already_exists")
        new_transition = transition.build_successor_transition(root, old, original_source_root, current_commit, prior_source_root, prior_commit)
        history = deepcopy(old["b_route_execution_history"])
        history[old["b_route_execution_transition"]["transition_digest"]] = deepcopy(old["b_route_execution_transition"])
        next_state = deepcopy(old)
        next_state.update(b_route_execution_transition=new_transition, b_route_execution_history=history)
        mutable = {"run.json", "model-execution.json", "capability-coordinator.lock", "candidates/candidate-2/lineage-execution.json",
                   WORKSPACE + "/capability-append/append-ledger.json"}
        record = {"schema_version": SCHEMA, "run_id": "c4", "run_ref": run_dir.relative_to(root).as_posix(),
            "previous_run": partial.image(raw_run), "previous_append": partial.image(raw_append),
            "immutable_files": partial._immutable(run_dir, mutable), "failed_namespace": failed,
            "transition": new_transition, "history": history, "prior_commit": prior_commit,
            "prior_source_root": str(Path(prior_source_root).resolve()), "namespace": NAMESPACE,
            "retained_slots": 8, "released": 0, "maximum_prefix_resumes": 1}
        record_raw = (json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        home = run_dir / "recovery" / NAMESPACE
        home.mkdir(parents=True, exist_ok=False)
        digest = codec.raw_digest(record_raw)
        partial._durable(home / "claim.json", {"schema_version": SCHEMA, "record_digest": digest, "retained_slots": 8}, exclusive=True)
        partial._durable(home / "record.json", record, exclusive=True)
        reference = {"schema_version": SCHEMA, "record_ref": (home / "record.json").relative_to(root).as_posix(),
                     "record_digest": digest, "artifact_root": str(root)}
        next_state[REFERENCE] = reference
        next_state["capability_selection"]["terminal"] = False
        next_state["capability_selection"]["current"]["admissions"]["candidate-2"]["retryable"] = True
        next_state.update(phase="input-path-recovery-prepared", selection_status="pending")
        next_state.pop("selection_block_reason", None)
        next_append = deepcopy(append)
        next_append.setdefault("input_preparation_errors", []).append({"errors": deepcopy(append["errors"]), "recovery": reference})
        next_append.update(status="generating", errors=[])
        partial._durable(run_dir / WORKSPACE / "capability-append/append-ledger.json", next_append)
        partial._durable(run_dir / "run.json", next_state)
        partial._durable(home / "committed.json", {"record_digest": digest, "transition_digest": new_transition["transition_digest"]}, exclusive=True)
        validate_recovery(root, next_state)
        return {"status": "input-path-recovery-prepared", "record": reference, "model_calls": 0,
                "retained_logical_calls": 8, "next_native_dispatch": 9, "next_local_dispatch": 5, "released": 0}
