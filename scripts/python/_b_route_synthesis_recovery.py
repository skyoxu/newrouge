"""Explicit, bounded continuation of a known failed synthesis, without refund.

The completed batch remains the actual original model output. The failed
synthesis, old worker and all paid reservations remain immutable evidence.
"""
from copy import deepcopy
import base64
import json
import os
from pathlib import Path

import _b_route_codec as codec
import _b_route_sources as sources
from _planning_skill_common import atomic_json, canonical_sha

SCHEMA = "newrouge.b-route-known-synthesis-recovery.v1"
PRIOR_COMMIT = "d7d0dad0acef19ea829da39a52738865de256ff9"
WORKSPACE = "candidates/candidate-2/scope-1"


def require(condition, reason):
    if not condition:
        raise ValueError("b_route_synthesis_recovery:" + reason)


def image(raw):
    return {"raw_digest": codec.raw_digest(raw), "bytes_base64": base64.b64encode(raw).decode("ascii")}


def image_bytes(value):
    require(type(value) is dict and set(value) == {"raw_digest", "bytes_base64"}, "archive_shape")
    raw = base64.b64decode(value["bytes_base64"], validate=True)
    require(codec.raw_digest(raw) == value["raw_digest"], "archive_digest")
    return raw


def retained_shape(state, append):
    """Validate the precise terminal state; never treat failed as unexecuted."""
    ledger = state["capability_selection"]
    calls = ledger["calls"]
    require(state["run_id"] == "c4" and ledger["total_invocations"] == len(calls) == 6
            and ledger["lineage_invocations"] == {"candidate-1": 4, "candidate-2": 2}, "paid_prefix")
    require([row["number"] for row in calls] == list(range(1, 7))
            and [row.get("outcome", {}).get("status") for row in calls] == ["completed"] * 5 + ["failed"],
            "unknown_or_changed_outcome")
    require(calls[4]["candidate"] == calls[5]["candidate"] == "candidate-2"
            and calls[4]["phase"] == calls[5]["phase"] == "generate"
            and calls[4]["request_identity"]["attempt"] == 1
            and calls[5]["request_identity"]["attempt"] == 2
            and calls[4]["request_identity"]["synthesis"] is False
            and calls[5]["request_identity"]["synthesis"] is True
            and all(row.get("generation") == row.get("execution") == 1 for row in calls), "stage_identity")
    require(ledger["selected"] == [] and ledger["terminal"] is True
            and state["selection_status"] == "blocked"
            and state["selection_block_reason"] == "selection_blocked_insufficient_admitted_candidates",
            "terminal_identity")
    current = ledger["current"]
    require(current["order_index"] == 0 and current["execution"] == 1
            and current["selection_attempts"] == []
            and current["admissions"]["candidate-1"]["status"] == "admitted"
            and current["admissions"]["candidate-2"]["status"] == "blocked", "candidate_identity")
    require(append["status"] == "blocked" and append["total_invocations"] == 2
            and len(append["calls"]) == 2 and append["completed"] == append["records"] == []
            and append["current"]["context"] == 1 and append["current"]["issue"] is None
            and append["current"]["proposal"] is append["current"]["delta"] is None,
            "append_identity")
    require([row["reservation_id"] for row in append["calls"]] == ["c4:dispatch:5", "c4:dispatch:6"],
            "append_paid_prefix")
    require(state["active_elapsed_seconds"] >= sum(row["outcome"]["active_elapsed_seconds"] for row in calls)
            and state["mvg.run_invocation_limit"] == 96, "clock_or_native_budget")
    funding = state["b_route_campaign_funding"]
    require(funding["paid_or_unknown_before_run"] == 55 and funding["campaign_limit"] == 290
            and funding["subsequent_full_reservation"] == 192 and funding["maximum_native_charges"] == 43
            and funding["released"] == 0, "campaign_funding")


def _read(root, reference):
    return codec.strict_json_loads(sources.checked_path(root, reference).read_bytes())


def _record(root, state):
    reference = state.get("b_route_synthesis_recovery")
    require(type(reference) is dict and set(reference) == {"schema_version", "record_ref", "record_digest", "artifact_root"}
            and reference["schema_version"] == SCHEMA and Path(reference["artifact_root"]).resolve() == Path(root).resolve(),
            "record_reference")
    path = sources.checked_path(root, reference["record_ref"])
    raw = path.read_bytes()
    require(codec.raw_digest(raw) == reference["record_digest"], "record_changed")
    record = codec.strict_json_loads(raw)
    require(record["schema_version"] == SCHEMA and record["run_id"] == state["run_id"], "record_identity")
    committed = codec.strict_json_loads((path.parent / "committed.json").read_bytes())
    require(committed == {"record_digest": reference["record_digest"],
                         "transition_digest": record["transition"]["transition_digest"]}, "partial_transaction")
    return record


def _scope_zero(ledger, original):
    """Selected steps use native prefix position; only current has order_index."""
    selected = ledger["selected"]
    require(len(selected) <= 1, "selected_scope_count_changed")
    matches = []
    if selected:
        step = selected[0]
        identity = step.get("input_identity", {})
        require(step.get("status") == "completed" and identity.get("order_index") == 0
                and identity.get("capability_id") == original["capability_id"]
                and identity.get("base_sha256") == original["base_sha256"], "selected_scope_identity_changed")
        matches.append(step)
    current = ledger.get("current")
    if current is not None and current.get("order_index") == 0:
        matches.append(current)
    return matches


def validate_recovery(root, state):
    """Read-only checks; counter and clock values may increase, never decrease."""
    root = Path(root).resolve()
    record = _record(root, state)
    old = codec.strict_json_loads(image_bytes(record["previous_run"]))
    append = codec.strict_json_loads(image_bytes(record["previous_append"]))
    retained_shape(old, append)
    source_state = state
    if state["b_route_execution_transition"] != record["transition"]:
        from _b_route_execution_transition import historical_state
        source_state = historical_state(root, state, record["transition"]["transition_digest"])
        require(source_state["b_route_synthesis_recovery"] == state["b_route_synthesis_recovery"]
                and state["capability_selection"]["calls"][:len(source_state["capability_selection"]["calls"])]
                    == source_state["capability_selection"]["calls"]
                and state["active_elapsed_seconds"] >= source_state["active_elapsed_seconds"],
                "successor_prefix_or_clock_changed")
    require(source_state["b_route_execution_transition"] == record["transition"]
            and source_state["b_route_execution_history"] == record["history"]
            and state["b_route_campaign_funding"] == old["b_route_campaign_funding"]
            and state["b_route_review_recovery"] == old["b_route_review_recovery"]
            and state["b_route_output_schema_policy"] == record["output_schema_policy"], "source_or_funding_changed")
    ledger = state["capability_selection"]
    require(ledger["calls"][:6] == old["capability_selection"]["calls"]
            and ledger["total_invocations"] == len(ledger["calls"]) >= 6
            and ledger["lineage_invocations"]["candidate-1"] == 4
            and ledger["lineage_invocations"]["candidate-2"] >= 2
            and state["active_elapsed_seconds"] >= old["active_elapsed_seconds"]
            and state["mvg.run_invocation_limit"] == old["mvg.run_invocation_limit"], "retained_charge_or_clock_changed")
    # The already admitted first candidate must survive byte for byte, including
    # its real source envelope. The selector can later move current into selected.
    original_current = old["capability_selection"]["current"]
    matching = _scope_zero(ledger, original_current)
    if not matching:
        # Native workers deliberately receive current=None and have no right to
        # publish coordinator admissions. Validate the actual owner state too.
        require(state.get("runtime_slot") == "candidate-2" and state.get("runtime_execution") == 1
                and ledger.get("current") is None, "missing_coordinator_admission")
        owner = _read(root, record["run_ref"] + "/run.json")["capability_selection"]
        require(owner["calls"][:6] == old["capability_selection"]["calls"], "worker_owner_prefix_changed")
        matching = _scope_zero(owner, original_current)
    require(len(matching) == 1 and matching[0]["admissions"]["candidate-1"] ==
            old["capability_selection"]["current"]["admissions"]["candidate-1"], "admitted_candidate_changed")
    run = sources.checked_path(root, record["run_ref"])
    for name, expected in record["immutable_files"].items():
        require(codec.raw_digest(sources.checked_path(run, name).read_bytes()) == expected,
                "retained_file_changed:" + name)
    local = _read(run, WORKSPACE + "/capability-append/append-ledger.json")
    require(local["calls"][:2] == append["calls"] and local["total_invocations"] >= 2
            and local["binding"] == append["binding"], "local_charge_or_binding_changed")
    return record


def resume_generation(root, state, workspace, frozen, accepted, prior, issue, context):
    """Return the actual paid prefix only for the initially interrupted propose."""
    if not state.get("b_route_synthesis_recovery") or state.get("runtime_slot") != "candidate-2":
        return None
    record = validate_recovery(root, state)
    if prior is not None or issue is not None or context != 1:
        return None  # Original native business-repair/replacement rules remain owned there.
    require(not any(row.get("candidate") == "candidate-2" and row.get("phase") == "generate"
                    for row in state["capability_selection"]["calls"][6:]), "synthesis_attempt_already_consumed")
    run = sources.checked_path(root, record["run_ref"])
    require(Path(workspace).resolve() == (run / WORKSPACE).resolve(), "workspace_changed")
    import _b_route_planning_runtime as runtime
    binding = _read(run, record["completed_binding_ref"])
    draft = _read(run, record["completed_draft_ref"])
    require(canonical_sha(binding) == record["completed_binding_digest"]
            and canonical_sha(draft) == record["completed_draft_digest"], "retained_prefix_changed")
    runtime.verify_reserved_call(run, state["capability_selection"]["calls"][4])
    require(runtime.same_json(runtime.decode_generation_carrier(runtime.verify_call(binding)), draft), "raw_draft_changed")
    materials = runtime.bound_materials(binding, state, frozen)
    expected = json.loads(runtime.request_attempt(frozen, batch=1, drafts=[], delivery=runtime.wire_delivery(state))["payload"])
    require(materials["phase"] == "generation" and materials["slot"] == "candidate-2"
            and materials["generation"] == materials["execution"] == materials["lineage_context"] == 1
            and runtime.same_json(materials["root_request"], expected)
            and runtime.same_json(materials["accepted_seed"], accepted)
            and materials["prior_candidate"] is materials["repair_issue"] is None
            and materials["lineage_identity"] == runtime.lineage_identity(state, accepted, "candidate-2", 1, 1, 1),
            "retained_generation_inputs_changed")
    runtime.planning.validate_draft_chain(frozen, [draft])
    return [draft], [binding]


def prepare_synthesis_retry(root, run_dir, *, original_source_root, current_commit, prior_source_root):
    """Exclusive, append-only preparation; no model dispatch or budget release."""
    import _b_route_planning_runtime as runtime
    import _b_route_execution_transition as transition
    from _mvg_capability_checkpoint import coordinator_lock
    root, run_dir = Path(root).resolve(), Path(run_dir).resolve()
    with coordinator_lock(run_dir):
        raw_run = (run_dir / "run.json").read_bytes()
        state = codec.strict_json_loads(raw_run)
        append_path = run_dir / WORKSPACE / "capability-append/append-ledger.json"
        raw_append = append_path.read_bytes()
        append = codec.strict_json_loads(raw_append)
        retained_shape(state, append)
        require(not state.get("b_route_synthesis_recovery") and not state.get("b_route_execution_history"),
                "recovery_already_prepared")
        require(state["b_route_execution_transition"]["current_commit"] == PRIOR_COMMIT
                and Path(state["b_route_execution_transition"]["current_source_root"]).resolve() == Path(prior_source_root).resolve(),
                "prior_source_changed")
        new_transition = transition.build_successor_transition(root, state, original_source_root, current_commit,
                                                               prior_source_root, PRIOR_COMMIT)
        next_state = deepcopy(state)
        history = {state["b_route_execution_transition"]["transition_digest"]: deepcopy(state["b_route_execution_transition"])}
        next_state.update(b_route_execution_history=history, b_route_execution_transition=new_transition,
                          b_route_output_schema_policy=runtime.PROVIDER_SCHEMA_POLICY)
        # Prove the complete original batch before a permanent recovery claim.
        binding_ref = WORKSPACE + "/capability-append/c1/execution-binding-1-r.json"
        draft_ref = WORKSPACE + "/capability-append/c1/canonical-draft.json"
        retained_binding, draft = _read(run_dir, binding_ref), _read(run_dir, draft_ref)
        require(runtime.same_json(runtime.decode_generation_carrier(runtime.verify_call(retained_binding)), draft),
                "completed_batch_not_bound")
        frozen = transition.load_prepared(root, next_state)
        materials = runtime.bound_materials(retained_binding, next_state, frozen)
        require(materials["phase"] == "generation" and materials["root_request"]["input"]["stage"] == "batch"
                and materials["slot"] == "candidate-2", "completed_batch_wrong_stage")
        runtime.planning.validate_draft_chain(frozen, [draft])
        # Only the documented known provider rejection permits this recovery.
        failed = run_dir / WORKSPACE / "capability-append/c2"
        host = _read(failed, "host-execution-2-r.json")
        require(host["returncode"] == 2 and host["status"] == "failed" and host["runner_dispatch_count"] == 1
                and host["active_elapsed_seconds"] == state["capability_selection"]["calls"][5]["outcome"]["active_elapsed_seconds"],
                "failed_host_not_bound")
        schema = _read(failed, "output-schema.json")
        require(schema["properties"]["parent_draft_identities"]["const"] == [codec.canonical_digest(draft)],
                "failed_parent_identity_changed")
        journals = list((failed / "llm-sandbox/attempt-2/r").glob("r.json.*.app-server.jsonl"))
        require(len(journals) == 1, "failed_journal_ambiguous")
        terminal_errors = []
        for line in journals[0].read_text(encoding="utf-8").splitlines():
            row = codec.strict_json_loads(line)
            message = row.get("message", {})
            if row.get("direction") == "server" and message.get("method") == "turn/completed":
                terminal_errors.append(message)
        require(terminal_errors and terminal_errors[-1]["params"]["turn"]["status"] == "failed"
                and 'invalid_json_schema' in json.dumps(terminal_errors[-1])
                and 'parent_draft_identities' in json.dumps(terminal_errors[-1]), "provider_failure_not_proven")
        home = run_dir / "recovery/synthesis-1"
        home.mkdir(parents=True, exist_ok=False)
        with (home / "claim.json").open("x", encoding="utf-8") as stream:
            json.dump({"schema_version": SCHEMA, "run_id": "c4", "pid": os.getpid()}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        mutable = {"run.json", "model-execution.json", "candidates/candidate-2/lineage-execution.json",
                   WORKSPACE + "/capability-append/append-ledger.json", "capability-coordinator.lock"}
        immutable = {path.relative_to(run_dir).as_posix(): codec.raw_digest(path.read_bytes())
                     for path in sorted(run_dir.rglob("*")) if path.is_file() and not path.is_relative_to(home)
                     and path.relative_to(run_dir).as_posix() not in mutable}
        record = {"schema_version": SCHEMA, "run_id": "c4", "run_ref": run_dir.relative_to(root).as_posix(),
                  "previous_run": image(raw_run), "previous_append": image(raw_append),
                  "immutable_files": immutable, "transition": new_transition, "history": history,
                  "output_schema_policy": runtime.PROVIDER_SCHEMA_POLICY,
                  "completed_binding_ref": binding_ref, "completed_draft_ref": draft_ref,
                  "completed_binding_digest": canonical_sha(retained_binding), "completed_draft_digest": canonical_sha(draft),
                  "retained_slots": 6, "released": 0, "next_native_dispatch": 7, "next_local_dispatch": 3,
                  "maximum_new_synthesis_attempts": 1}
        atomic_json(home / "record.json", record)
        reference = {"schema_version": SCHEMA, "record_ref": (home / "record.json").relative_to(root).as_posix(),
                     "record_digest": codec.raw_digest((home / "record.json").read_bytes()), "artifact_root": str(root)}
        next_state["b_route_synthesis_recovery"] = reference
        next_state["capability_selection"]["terminal"] = False
        next_state["capability_selection"]["current"]["admissions"]["candidate-2"]["retryable"] = True
        next_state.update(phase="synthesis-recovery-prepared", selection_status="pending")
        next_state.pop("selection_block_reason", None)
        next_append = deepcopy(append)
        next_append.setdefault("execution_errors", []).append({"stage": "generate", "invocations": 2,
            "original_errors": deepcopy(append["errors"]), "recovery": reference})
        next_append.update(status="generating", errors=[])
        atomic_json(append_path, next_append)
        atomic_json(run_dir / "run.json", next_state)
        atomic_json(home / "committed.json", {"record_digest": reference["record_digest"],
                                              "transition_digest": new_transition["transition_digest"]})
        validate_recovery(root, next_state)
        return {"status": "synthesis-recovery-prepared", "record": reference, "model_calls": 0,
                "retained_logical_calls": 6, "next_dispatch": "c4:dispatch:7", "released": 0}
