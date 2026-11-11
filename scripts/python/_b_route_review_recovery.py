"""One explicit recovery of a completed, source-citation-invalid 3B review.

This continues the same native run and candidate. No unknown request, refund,
new candidate seed, or selected checkpoint can be introduced by this operation.
"""
from copy import deepcopy
from pathlib import Path
import json
import os
import base64
import stat

from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json
import _b_route_codec as codec
import _b_route_sources as sources

SCHEMA = "newrouge.b-route-completed-review-recovery.v1"


def require(value, message):
    if not value:
        raise ValueError("b_route_review_recovery:" + message)


def _record(state):
    reference = state.get("b_route_review_recovery")
    require(type(reference) is dict and set(reference) == {"schema_version", "record_ref", "record_digest", "artifact_root"}
            and reference["schema_version"] == SCHEMA, "invalid_reference")
    root = Path(reference["artifact_root"])
    path = sources.checked_path(root, reference["record_ref"])
    value = codec.strict_json_loads(path.read_bytes())
    require(codec.raw_digest(path.read_bytes()) == reference["record_digest"], "record_changed")
    require(value["schema_version"] == SCHEMA and value["run_id"] == state["run_id"], "record_identity_changed")
    return root, path, value


def _image(raw):
    return {"raw_digest": codec.raw_digest(raw), "bytes_base64": base64.b64encode(raw).decode("ascii")}


def _image_bytes(value):
    require(type(value) is dict and set(value) == {"raw_digest", "bytes_base64"}, "invalid_raw_archive")
    raw = base64.b64decode(value["bytes_base64"], validate=True)
    require(codec.raw_digest(raw) == value["raw_digest"], "raw_archive_changed")
    return raw


def _worker_manifest(run, worker):
    files = {}
    for path in (worker, *sorted(worker.rglob("*"))):
        info = path.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                "worker_reparse_forbidden")
        require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode), "worker_path_type")
        if path.is_file():
            relative = path.relative_to(run).as_posix()
            files[relative] = codec.raw_digest(codec.read_reference_bytes(run, relative))
    return files


def _validate_worker_recovery(root, state, record, seen):
    recovery = record["worker_recovery"]
    require(type(recovery) is dict and set(recovery) == {"parent_ref", "previous_run", "previous_append",
            "worker_manifest", "stage_cost", "new_dispatches_since_previous", "attempt"}, "invalid_worker_recovery")
    previous_state = codec.strict_json_loads(_image_bytes(recovery["previous_run"]))
    parent_ref = recovery["parent_ref"]
    require(previous_state["b_route_review_recovery"] == parent_ref, "worker_parent_state_changed")
    _, _, parent = _record(previous_state)
    require(not parent.get("worker_recovery"), "worker_already_recovered")
    run = sources.checked_path(root, record["run_ref"])
    worker = run / "candidates/candidate-1/scope-1/lifecycle-review-recovery-1"
    stage = recovery["stage_cost"]
    require(type(stage) is dict and set(stage) == {"path", "raw_digest", "bytes_base64"}
            and stage["path"] == "candidates/candidate-1/scope-1/capability-append/stage-costs/4-review.json",
            "worker_stage_cost_path_changed")
    _image_bytes({key: stage[key] for key in ("raw_digest", "bytes_base64")})
    additions = {**recovery["worker_manifest"], stage["path"]: stage["raw_digest"]}
    require(recovery["worker_manifest"] == _worker_manifest(run, worker), "old_worker_changed")
    previous_map = parent["immutable_original_files"]
    require(all(key not in previous_map or previous_map[key] == digest for key, digest in additions.items()),
            "worker_original_map_conflict")
    expected = {**parent, "transition": record["transition"],
                "immutable_original_files": {**previous_map, **additions}, "worker_recovery": recovery}
    require(record == expected and recovery["new_dispatches_since_previous"] == 0 and recovery["attempt"] == 2,
            "worker_recovery_copy_changed")
    require(previous_state["b_route_execution_transition"] == parent["transition"], "worker_parent_transition_changed")
    # Validate the actual archived parent state. Substituting the R7 transition
    # into a parent reference would falsely present old source as current source.
    validate_recovery(root, previous_state, _seen=seen)
    require(state.get("b_route_review_worker_attempt") == 2
            and state.get("active_elapsed_seconds", 0) >= previous_state.get("active_elapsed_seconds", 0),
            "worker_attempt_or_clock_changed")
    previous_append = codec.strict_json_loads(_image_bytes(recovery["previous_append"]))
    require(previous_append["status"] == "blocked" and previous_append["total_invocations"] == 3
            and canonical_sha(previous_append["current"]["proposal"]) == parent["proposal_sha256"],
            "worker_previous_append_changed")


def validate_recovery(root, state, *, _seen=None):
    root = Path(root).resolve()
    actual_root, path, record = _record(state)
    require(actual_root.resolve() == Path(root).resolve(), "artifact_root_changed")
    seen = set() if _seen is None else set(_seen)
    require(str(path) not in seen, "recovery_parent_cycle")
    seen.add(str(path))
    if state["b_route_execution_transition"] != record["transition"]:
        from _b_route_execution_transition import historical_state
        previous = historical_state(root, state, record["transition"]["transition_digest"])
        require(previous["b_route_review_recovery"] == state["b_route_review_recovery"]
                and previous["b_route_execution_transition"] == record["transition"], "record_transition_changed")
        require(state["capability_selection"]["calls"][:len(previous["capability_selection"]["calls"])]
                    == previous["capability_selection"]["calls"]
                and state.get("active_elapsed_seconds", 0) >= previous.get("active_elapsed_seconds", 0),
                "historical_prefix_or_clock_changed")
    if record.get("worker_recovery"):
        _validate_worker_recovery(root, state, record, seen)
    elif record.get("source_amendment"):
        amendment = record["source_amendment"]
        parent_ref = amendment["previous_record"]
        parent_path = sources.checked_path(root, parent_ref["record_ref"])
        require(codec.raw_digest(parent_path.read_bytes()) == parent_ref["record_digest"], "previous_recovery_record_changed")
        parent = codec.strict_json_loads(parent_path.read_bytes())
        expected = {**parent, "transition": record["transition"], "source_amendment": amendment}
        require(record == expected and not parent.get("source_amendment")
                and amendment["previous_transition"] == parent["transition"]
                and amendment["new_dispatches_since_previous"] == 0, "invalid_source_amendment")
        previous_state = codec.strict_json_loads(base64.b64decode(amendment["previous_run_bytes_base64"], validate=True))
        require(state.get("active_elapsed_seconds", 0) >= previous_state.get("active_elapsed_seconds", 0)
                and previous_state["b_route_review_recovery"] == parent_ref,
                "source_amendment_clock_or_parent_changed")
        validate_recovery(root, previous_state, _seen=seen)
    if not record.get("worker_recovery"):
        require(state.get("b_route_review_worker_attempt", 1) == 1, "unexpected_worker_attempt")
    committed = codec.strict_json_loads(path.with_name("committed.json").read_bytes())
    require(committed == {"record_digest": state["b_route_review_recovery"]["record_digest"],
                          "transition_digest": record["transition"]["transition_digest"]}, "partial_transition")
    run = sources.checked_path(root, record["run_ref"])
    original = record["original_run"]
    calls = state.get("capability_selection", {}).get("calls", [])
    old_calls = original["capability_selection"]["calls"]
    require(calls[:len(old_calls)] == old_calls, "original_charges_or_times_changed")
    require(state["runtime_identity"] == original["runtime_identity"]
            and state["planning_runtime"] == original["planning_runtime"]
            and state["mvg.run_invocation_limit"] == original["mvg.run_invocation_limit"]
            and state.get("active_elapsed_seconds", 0) >= original.get("active_elapsed_seconds", 0), "budget_or_base_changed")
    ledger = state["capability_selection"]
    require(state.get("b_route_campaign_funding") == record["campaign_funding"], "campaign_funding_changed")
    require(ledger["total_invocations"] >= len(old_calls)
            and ledger["lineage_invocations"]["candidate-1"] >= len(old_calls), "refunded_charge")
    for relative, digest in record["immutable_original_files"].items():
        require(codec.raw_digest(sources.checked_path(run, relative).read_bytes()) == digest, "original_file_changed:" + relative)
    return record


def validate_materials_transition(state, materials, binding, *, allow_failed_review=False):
    transition = state.get("b_route_execution_transition")
    actual = materials.get("execution_source_transition")
    if not transition:
        require("execution_source_transition" not in materials, "unexpected_source_transition")
        return
    if actual == transition["transition_digest"]:
        return
    require("execution_source_transition" not in materials and state.get("b_route_review_recovery"), "new_call_missing_source_transition")
    _, _, record = _record(state)
    if (allow_failed_review and materials["phase"] == "independent_admission"
            and canonical_sha(binding) == record["retained_failed_review_binding"]):
        return  # Paid history only; admission calls never enable this exception.
    require(canonical_sha(binding) in record["historical_generation_bindings"], "unbound_legacy_execution")
    require(materials["phase"] == "generation", "legacy_review_cannot_be_reused")


def prepare_known_review_retry(root, run_dir, *, original_source_root, current_commit):
    """Coordinator-locked, fail-closed transaction; does not dispatch a model."""
    import _b_route_planning_runtime as runtime
    from _b_route_execution_transition import build_transition, load_prepared
    from _mvg_capability_checkpoint import coordinator_lock
    root, run_dir = Path(root).resolve(), Path(run_dir).resolve()
    with coordinator_lock(run_dir):
        original = codec.strict_json_loads((run_dir / "run.json").read_bytes())
        require(not original.get("b_route_review_recovery") and not original.get("b_route_execution_transition"), "already_transitioned")
        desc = runtime.descriptor(original)
        require(desc["planner"] == "capabilities" and original.get("phase") == "selection-blocked"
                and original.get("selection_block_reason") == "selection_blocked_insufficient_admitted_candidates", "not_supported_terminal")
        ledger = original["capability_selection"]
        calls = ledger["calls"]
        require(ledger.get("terminal") is True and not ledger["selected"] and len(calls) == 3
                and ledger["total_invocations"] == 3
                and ledger["lineage_invocations"] == {"candidate-1": 3, "candidate-2": 0},
                "not_first_completed_review_failure")
        require([row["phase"] for row in calls] == ["generate", "generate", "semantic"]
                and all(row.get("candidate") == "candidate-1" and row.get("outcome", {}).get("status") == "completed" for row in calls),
                "unknown_or_wrong_stage")
        current = ledger["current"]
        require(current["order_index"] == 0 and current.get("execution", 1) == 1
                and set(current["admissions"]) == {"candidate-1"}, "scope_or_execution_changed")
        workspace = sources.checked_path(run_dir, current["admissions"]["candidate-1"]["workspace"])
        append_path = workspace / "capability-append/append-ledger.json"
        append = codec.strict_json_loads(append_path.read_bytes())
        require(append["status"] == "blocked" and not append["records"] and not append["completed"]
                and append["total_invocations"] == 3 and len(append["errors"]) == 1
                and append["errors"][0]["code"] == "append_execution_failure"
                and append["errors"][0]["stage"] == "semantic"
                and "b_route_independent_review_source_support_invalid" in append["errors"][0]["detail"], "wrong_failure_class")
        state = deepcopy(original)
        state["b_route_execution_transition"] = build_transition(root, state, original_source_root, current_commit)
        state["schema_version"] = runtime.CONTINUATION_RUN
        state["b_route_campaign_funding"] = {"schema_version": "newrouge.story25-native-funding.v1",
            "paid_or_unknown_before_run": 55, "campaign_limit": 290,
            "subsequent_full_reservation": 192, "maximum_native_charges": 43, "released": 0}
        frozen = load_prepared(root, state)
        bindings = [runtime.verify_reserved_call(run_dir, row) for row in calls]
        drafts = [runtime.decode_generation_carrier(runtime.verify_call(binding)) for binding in bindings[:2]]
        runtime.planning.validate_draft_chain(frozen, drafts)
        base = runtime.seed(state, run_dir / "analysis-input")
        proposal = {"schema_version": runtime.candidate.SCHEMA, "input_stage": "3b", "input_identity": frozen["input_identity"],
            "provenance": {"kind": "model_draft", "declaration": "Complete original model draft chain; execution separately replayed",
                "upstream_model_history": "declared_model", "draft_chain": drafts, "final_draft_identity": codec.canonical_digest(drafts[-1])},
            "content": deepcopy(drafts[-1]["content"])}
        require(not runtime.machine(root, state, proposal), "generation_not_machine_valid")
        review = runtime.verify_call(bindings[2])
        legacy_materials = runtime.wire.read_prompt(Path(bindings[2]["prompt_path"]).read_text(encoding="utf-8"), runtime.wire_delivery(state))
        require(runtime.same_json(legacy_materials["proposal"], proposal) and review["verdict"] == "approved"
                and review["findings"] == [] and all(row["verdict"] == "approved" for row in review["checks"]), "business_failure_or_changed_draft")
        try:
            runtime.review_issues(state, proposal, frozen, review)
        except ValueError as exc:
            require(str(exc) == "b_route_independent_review_source_support_invalid", "not_only_source_format_failure")
        else:
            raise ValueError("b_route_review_recovery:original_review_was_valid")
        # Prove old generation materials with the original source implementation,
        # separately from the new execution identity; no historical re-signing.
        from _b_route_execution_transition import verify_historical_generation
        historical_check = verify_historical_generation(root, original, bindings[:2], proposal, original_source_root)
        delta = {"candidate": proposal, "generation_calls": bindings[:2], "lineage": {
            "context": 1, "identity": runtime.lineage_identity(state, base, "candidate-1", 1),
            "slot": "candidate-1", "generation": 1, "execution": 1}}
        home = run_dir / "recovery/review-1"
        home.mkdir(parents=True, exist_ok=False)
        # Exclusive claim precedes all mutable native state. A partial transaction
        # has no committed marker and cannot dispatch or be silently retried.
        with (home / "claim.json").open("x", encoding="utf-8") as stream:
            json.dump({"schema_version": SCHEMA, "run_id": state["run_id"], "pid": os.getpid()}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        mutable = {"run.json", "model-execution.json", "candidates/candidate-1/lineage-execution.json",
                   append_path.relative_to(run_dir).as_posix()}
        original_files = {}
        for path in run_dir.rglob("*"):
            if (path.is_file() and not path.is_relative_to(home)
                    and path.relative_to(run_dir).as_posix() not in mutable | {"capability-coordinator.lock"}):
                relative = path.relative_to(run_dir).as_posix()
                original_files[relative] = codec.raw_digest(sources.checked_path(run_dir, relative).read_bytes())
        record = {"schema_version": SCHEMA, "run_id": state["run_id"], "run_ref": run_dir.relative_to(root).as_posix(),
            "original_run": original, "original_append": append, "immutable_original_files": original_files,
            "original_control_bytes": {name: {"raw_digest": codec.raw_digest((run_dir/name).read_bytes()),
                "bytes_base64": base64.b64encode((run_dir/name).read_bytes()).decode("ascii")} for name in sorted(mutable)},
            "historical_generation_bindings": [canonical_sha(row) for row in bindings[:2]],
            "historical_generation_verification": historical_check,
            "retained_failed_review_binding": canonical_sha(bindings[2]), "proposal_sha256": canonical_sha(proposal),
            "new_dispatch_ordinal": 4, "transition": state["b_route_execution_transition"]}
        record["campaign_funding"] = deepcopy(state["b_route_campaign_funding"])
        atomic_json(home / "record.json", record)
        reference = {"schema_version": SCHEMA, "record_ref": (home / "record.json").relative_to(root).as_posix(),
            "record_digest": codec.raw_digest((home / "record.json").read_bytes()), "artifact_root": str(root)}
        state["b_route_review_recovery"] = reference
        resumed_append = deepcopy(append)
        execution_issue = {"code": "append_semantic_execution_invalid", "path": "model", "error_type": "runner_execution_failed",
                           "detail": "Completed original review failed canonical per-obligation source support; explicit recovery review-1"}
        resumed_append.setdefault("execution_errors", []).append({"stage": "semantic", "invocations": 3,
            "original_errors": deepcopy(append["errors"]), "recovery": reference})
        resumed_append.update(status="generating", errors=[])
        resumed_append["current"].update(proposal=proposal, delta=delta, issue=execution_issue, issues=[execution_issue])
        state["capability_selection"]["terminal"] = False
        state["capability_selection"]["current"]["admissions"]["candidate-1"]["retryable"] = True
        state.update(phase="review-recovery-prepared", selection_status="pending")
        state.pop("selection_block_reason", None)
        atomic_json(append_path, resumed_append)
        atomic_json(run_dir / "run.json", state)
        atomic_json(home / "committed.json", {"record_digest": reference["record_digest"],
            "transition_digest": state["b_route_execution_transition"]["transition_digest"]})
        validate_recovery(root, state)
        return {"status": "review-recovery-prepared", "record": reference, "model_calls": 0,
                "retained_logical_calls": 3, "next_dispatch": state["run_id"] + ":dispatch:4"}


def amend_before_dispatch(root, run_dir, *, original_source_root, current_commit):
    """Amend source identity only when no request used the earlier R6 source.

    A new immutable record preserves the earlier preparation and host failure;
    no model ordinal, proposal, reservation, charge or clock is restarted.
    """
    import _b_route_planning_runtime as runtime
    from _b_route_execution_transition import build_transition
    from _mvg_capability_checkpoint import coordinator_lock
    root, run_dir = Path(root).resolve(), Path(run_dir).resolve()
    with coordinator_lock(run_dir):
        state = codec.strict_json_loads((run_dir / "run.json").read_bytes())
        previous = validate_recovery(root, state)
        require(not previous.get("source_amendment"), "source_already_amended")
        old_calls = previous["original_run"]["capability_selection"]["calls"]
        require(state["capability_selection"]["calls"] == old_calls
                and state["capability_selection"]["total_invocations"] == 3
                and all(row.get("outcome", {}).get("status") == "completed" for row in old_calls), "dispatch_already_started")
        workspace = run_dir / "candidates/candidate-1/scope-1"
        require(not (workspace / "lifecycle-review-recovery-1").exists()
                and not (workspace / "capability-append/c4").exists(), "new_execution_artifacts_exist")
        append = codec.strict_json_loads((workspace / "capability-append/append-ledger.json").read_bytes())
        require(append["status"] == "generating" and append["total_invocations"] == 3
                and append["current"]["proposal"] is not None
                and canonical_sha(append["current"]["proposal"]) == previous["proposal_sha256"], "prepared_draft_changed")
        legacy = deepcopy(state)
        legacy.pop("b_route_execution_transition")
        legacy["schema_version"] = runtime.RUN
        transition = build_transition(root, legacy, original_source_root, current_commit)
        home = run_dir / "recovery/review-1/source-amendment-1"
        home.mkdir(parents=True, exist_ok=False)
        with (home / "claim.json").open("x", encoding="utf-8") as stream:
            json.dump({"previous_record": state["b_route_review_recovery"], "no_new_dispatch": True}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        record = deepcopy(previous)
        record["transition"] = transition
        record["source_amendment"] = {"previous_record": deepcopy(state["b_route_review_recovery"]),
            "previous_transition": deepcopy(state["b_route_execution_transition"]),
            "previous_run_bytes_base64": base64.b64encode((run_dir / "run.json").read_bytes()).decode("ascii"),
            "new_dispatches_since_previous": 0, "reason": "Separate paid-history replay from admission reuse"}
        atomic_json(home / "record.json", record)
        reference = {"schema_version": SCHEMA, "record_ref": (home / "record.json").relative_to(root).as_posix(),
            "record_digest": codec.raw_digest((home / "record.json").read_bytes()), "artifact_root": str(root)}
        state["b_route_review_recovery"] = reference
        state["b_route_execution_transition"] = transition
        state["capability_selection"]["terminal"] = False
        state["capability_selection"]["current"]["admissions"]["candidate-1"]["retryable"] = True
        state.update(phase="review-recovery-prepared", selection_status="pending")
        state.pop("selection_block_reason", None)
        atomic_json(run_dir / "run.json", state)
        atomic_json(home / "committed.json", {"record_digest": reference["record_digest"],
            "transition_digest": transition["transition_digest"]})
        validate_recovery(root, state)
        return {"status": "review-recovery-prepared", "record": reference, "model_calls": 0,
                "retained_logical_calls": 3, "next_dispatch": state["run_id"] + ":dispatch:4"}


def _completed_input_failure(run, workspace, state):
    worker = workspace / "lifecycle-review-recovery-1"
    snapshot = _worker_manifest(run, worker)

    def read(path):
        return codec.strict_json_loads(codec.read_reference_bytes(run, path.relative_to(run).as_posix()))

    job, process, result = (read(worker / name) for name in ("job.json", "process.json", "result.json"))
    schema = "newrouge.mvg-capability-worker.v1"
    require(set(job) == {"schema_version", "identity", "input"} and job["schema_version"] == schema
            and job["identity"] == canonical_sha(job["input"]), "worker_job_changed")
    require(set(process) == {"pid", "identity"} and type(process["pid"]) is int and process["pid"] > 0
            and process["identity"] == job["identity"], "worker_process_changed")
    require(set(result) == {"schema_version", "identity", "pid", "status", "total_invocations", "errors"}
            and result["schema_version"] == schema and result["identity"] == job["identity"]
            and result["pid"] == process["pid"] and result["status"] == "blocked"
            and type(result["total_invocations"]) is int and result["total_invocations"] == 3
            and result["errors"] == [{"code": "append_input_preparation_failed", "detail": "semantic_error"}],
            "worker_not_completed_input_failure")
    require(read(worker / "progress.json") == {"status": "blocked", "total_invocations": 3}, "worker_progress_changed")
    data = job["input"]
    require(Path(data["root"]).resolve() == run.parents[3] and Path(data["run_dir"]).resolve() == run
            and Path(data["workspace"]).resolve() == workspace and data["scope_index"] == 0
            and not data["selected_records"], "worker_scope_changed")
    private = data["state"]
    require(private["runtime_identity"] == state["runtime_identity"] and private["planning_runtime"] == state["planning_runtime"]
            and private["b_route_review_recovery"] == state["b_route_review_recovery"]
            and private["b_route_execution_transition"] == state["b_route_execution_transition"]
            and private.get("runtime_slot") == "candidate-1" and private.get("runtime_execution") == 1
            and private["capability_selection"]["calls"] == state["capability_selection"]["calls"]
            and private["capability_selection"]["total_invocations"] == 3, "worker_state_changed")
    mailbox = worker / "mailbox"
    names = {path.name for path in mailbox.iterdir()}
    requests = sorted(mailbox.glob("*.request.json"), key=lambda path: int(path.name.split(".", 1)[0]))
    require(requests and names == {str(n) + suffix for n in range(1, len(requests) + 1)
                                  for suffix in (".request.json", ".response.json")}, "worker_mailbox_partial_or_unknown")
    for number, path in enumerate(requests, 1):
        request, response = read(path), read(mailbox / (str(number) + ".response.json"))
        require(set(request) == {"identity", "sequence", "kind", "phase", "known_evidence_calls"}
                and request["identity"] == job["identity"] and request["sequence"] == number
                and request["kind"] == "cost" and request["phase"] == "review"
                and type(request["known_evidence_calls"]) is int and request["known_evidence_calls"] >= 0,
                "worker_model_reservation_or_unknown_mailbox")
        require(set(response) == {"identity", "sequence", "value"} and response["identity"] == job["identity"]
                and response["sequence"] == number and type(response["value"]) is dict
                and set(response["value"]) == {"remaining", "future", "selector_calls", "unknown_future_scope_estimate"}
                and response["value"]["remaining"] == {"run": 93, "lineage": 61}, "worker_cost_response_changed")
    stage_path = workspace / "capability-append/stage-costs/4-review.json"
    stage_raw = codec.read_reference_bytes(run, stage_path.relative_to(run).as_posix())
    stage = codec.strict_json_loads(stage_raw)
    require(stage["schema_version"] == "newrouge.mvg-stage-cost.v1" and stage["phase"] == "review"
            and stage["stage_dispatch_status"] == "not_dispatched" and stage["status"] == "ready"
            and stage["remaining_calls"] == {"run": 93, "lineage": 61}, "worker_stage_cost_changed")
    require(snapshot == _worker_manifest(run, worker), "worker_files_changed_during_validation")
    return snapshot, {"path": stage_path.relative_to(run).as_posix(), **_image(stage_raw)}


def resume_pre_dispatch_worker(root, run_dir, original_source_root, current_commit):
    """Recover one terminal input-preparation failure with no model reservation."""
    import _b_route_planning_runtime as runtime
    from _b_route_execution_transition import build_transition
    from _mvg_capability_checkpoint import coordinator_lock
    root, run_dir = Path(root).resolve(), Path(run_dir).resolve()
    require(run_dir.is_relative_to(root), "worker_run_outside_root")
    with coordinator_lock(run_dir):
        run_raw = (run_dir / "run.json").read_bytes()
        state = codec.strict_json_loads(run_raw)
        previous = validate_recovery(root, state)
        require(not previous.get("worker_recovery") and state.get("b_route_review_worker_attempt", 1) == 1,
                "worker_already_recovered")
        require(runtime.descriptor(state)["planner"] == "capabilities", "worker_wrong_planner")
        ledger = state["capability_selection"]
        old_calls = previous["original_run"]["capability_selection"]["calls"]
        require(len(old_calls) == 3 and ledger["calls"] == old_calls and ledger["total_invocations"] == 3
                and ledger["lineage_invocations"] == {"candidate-1": 3, "candidate-2": 0}
                and all(row.get("outcome", {}).get("status") == "completed" for row in old_calls)
                and [row["phase"] for row in old_calls] == ["generate", "generate", "semantic"]
                and not ledger["selected"], "worker_dispatch_already_started_or_unknown")
        current = ledger["current"]
        require(current["order_index"] == 0 and current.get("execution", 1) == 1
                and current["capability_id"] == previous["original_run"]["capability_selection"]["current"]["capability_id"]
                and set(current["admissions"]) == {"candidate-1"}
                and current["admissions"]["candidate-1"]["workspace"] == "candidates/candidate-1/scope-1",
                "worker_slot_or_scope_changed")
        workspace = run_dir / "candidates/candidate-1/scope-1"
        require(not (workspace / "capability-append/c4").exists()
                and not (workspace / "lifecycle-review-recovery-2").exists()
                and not (workspace / "capability-append/stage-costs/recovery-2").exists(), "worker_new_execution_artifacts_exist")
        append_path = workspace / "capability-append/append-ledger.json"
        append_raw = append_path.read_bytes()
        append = codec.strict_json_loads(append_raw)
        require(append["status"] == "blocked" and append["total_invocations"] == 3
                and not append["records"] and not append["completed"]
                and append["errors"] == [{"code": "append_input_preparation_failed", "detail": "semantic_error"}]
                and append["current"]["proposal"] is not None
                and canonical_sha(append["current"]["proposal"]) == previous["proposal_sha256"], "worker_append_or_proposal_changed")
        worker_manifest, stage_cost = _completed_input_failure(run_dir, workspace, state)
        legacy = deepcopy(state)
        legacy.pop("b_route_execution_transition")
        legacy["schema_version"] = runtime.RUN
        transition = build_transition(root, legacy, original_source_root, current_commit)
        home = run_dir / "recovery/review-1/worker-input-recovery-1"
        home.mkdir(parents=True, exist_ok=False)
        with (home / "claim.json").open("x", encoding="utf-8") as stream:
            json.dump({"parent_ref": state["b_route_review_recovery"], "attempt": 2, "new_model_calls": 0}, stream)
            stream.flush()
            os.fsync(stream.fileno())
        record = deepcopy(previous)
        record["transition"] = transition
        additions = {**worker_manifest, stage_cost["path"]: stage_cost["raw_digest"]}
        require(all(key not in previous["immutable_original_files"] or previous["immutable_original_files"][key] == value
                    for key, value in additions.items()), "worker_original_map_conflict")
        record["immutable_original_files"] = {**previous["immutable_original_files"], **additions}
        record["worker_recovery"] = {"parent_ref": deepcopy(state["b_route_review_recovery"]),
            "previous_run": _image(run_raw), "previous_append": _image(append_raw), "worker_manifest": worker_manifest,
            "stage_cost": stage_cost, "new_dispatches_since_previous": 0, "attempt": 2}
        atomic_json(home / "record.json", record)
        reference = {"schema_version": SCHEMA, "record_ref": (home / "record.json").relative_to(root).as_posix(),
            "record_digest": codec.raw_digest((home / "record.json").read_bytes()), "artifact_root": str(root)}
        state["b_route_review_recovery"] = reference
        state["b_route_execution_transition"] = transition
        state["b_route_review_worker_attempt"] = 2
        state["capability_selection"]["terminal"] = False
        current["admissions"]["candidate-1"]["retryable"] = True
        state.update(phase="review-recovery-prepared", selection_status="pending")
        state.pop("selection_block_reason", None)
        append.update(status="generating", errors=[])
        atomic_json(append_path, append)
        atomic_json(run_dir / "run.json", state)
        atomic_json(home / "committed.json", {"record_digest": reference["record_digest"],
            "transition_digest": transition["transition_digest"]})
        validate_recovery(root, state)
        return {"status": "review-recovery-prepared", "record": reference, "model_calls": 0,
                "retained_logical_calls": 3, "worker_attempt": 2, "next_dispatch": state["run_id"] + ":dispatch:4"}
