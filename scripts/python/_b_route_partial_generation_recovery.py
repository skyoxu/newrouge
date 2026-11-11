"""One typed continuation of a paid repair batch whose synthesis was not reserved.

No counters, clocks, model results or business issues are reset. The old eight
calls and unreserved c5 preparation remain immutable. The first retry shortcut
requires a permanent local claim before propose can reach a dispatch boundary.
This owner supplies integrity checks, not provider/billing or acceptance proof.
"""
from copy import deepcopy
import base64
import json
import math
import os
from pathlib import Path
import stat
import uuid

import _b_route_codec as codec
import _b_route_sources as sources
import _b_route_compact_literal as compact
from _planning_skill_common import canonical_sha
from _mvg_capability_append import issue_key

SCHEMA = "newrouge.b-route-partial-repair-recovery.v1"
PRIOR_COMMIT = "f828d861fab8e879c9069adfeb218d81c0d8b43c"
REFERENCE = "b_route_partial_generation_recovery"
WORKSPACE = "candidates/candidate-2/scope-1"
NAMESPACE = "input-budget-recovery-1"


def require(value, reason):
    if not value:
        raise ValueError("b_route_partial_generation_recovery:" + reason)


def same(left, right):
    return codec.canonical_digest(left) == codec.canonical_digest(right)


def image(raw):
    return {"raw_digest": codec.raw_digest(raw), "bytes_base64": base64.b64encode(raw).decode("ascii")}


def image_bytes(value):
    require(type(value) is dict and set(value) == {"raw_digest", "bytes_base64"}, "image_shape")
    raw = base64.b64decode(value["bytes_base64"], validate=True)
    require(codec.raw_digest(raw) == value["raw_digest"], "image_digest")
    return raw


def read(root, reference):
    return codec.strict_json_loads(codec.read_reference_bytes(root, reference))


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def model_used(state):
    return sum(row["outcome"]["active_elapsed_seconds"] for row in state["capability_selection"]["calls"]
               if row.get("candidate") == "candidate-2")


def retained_shape(state, append):
    ledger, calls = state["capability_selection"], state["capability_selection"]["calls"]
    require(state["run_id"] == "c4" and type(ledger["total_invocations"]) is int
            and ledger["total_invocations"] == len(calls) == 8
            and ledger["lineage_invocations"] == {"candidate-1": 4, "candidate-2": 4}, "old_eight_calls")
    require([row["number"] for row in calls] == list(range(1, 9))
            and [row.get("outcome", {}).get("status") for row in calls]
                == ["completed"] * 5 + ["failed", "completed", "completed"], "unknown_or_changed_outcome")
    require(all(row.get("generation") == row.get("execution") == 1 for row in calls)
            and all(row.get("candidate") == "candidate-2" for row in calls[4:])
            and [row["phase"] for row in calls[4:]] == ["generate", "generate", "generate", "repair"]
            and [row["request_identity"]["attempt"] for row in calls[4:]] == [1, 2, 3, 4]
            and [row["request_identity"]["synthesis"] for row in calls[4:]] == [False, True, True, False], "stage_identity")
    require(state["selection_status"] == "blocked" and ledger["terminal"] is True and ledger["selected"] == []
            and state["selection_block_reason"] == "selection_blocked_insufficient_admitted_candidates", "terminal_identity")
    owner = ledger["current"]
    require(owner["order_index"] == 0 and owner["execution"] == 1 and owner["selection_attempts"] == []
            and owner["admissions"]["candidate-1"]["status"] == "admitted"
            and owner["admissions"]["candidate-2"]["status"] == "blocked", "admission_identity")
    current = append["current"]
    require(append["status"] == "blocked" and type(append["total_invocations"]) is int
            and append["total_invocations"] == len(append["calls"]) == 4
            and append["completed"] == append["records"] == []
            and current["context"] == 1 and type(current["proposal"]) is dict
            and type(current["delta"]) is dict and same(current["proposal"], current["delta"]["candidate"]), "partial_append")
    issue = current["issue"]
    require(type(issue) is dict and issue.get("path") == "candidate:observations-to-audit"
            and str(issue.get("code", "")).startswith("b_route_machine:")
            and issue.get("detail", {}).get("entity_id") == "observations-to-audit"
            and issue["detail"].get("expected") == "handoff corresponds to declared graph edge"
            and current["issue_attempts"] == {issue_key(issue): 1}
            and type(current["issue_attempts"][issue_key(issue)]) is int, "original_business_issue_or_attempt_changed")
    require([row["reservation_id"] for row in append["calls"]] == ["c4:dispatch:" + str(i) for i in range(5, 9)]
            and [row["number"] for row in append["calls"]] == [1, 2, 3, 4]
            and [row["phase"] for row in append["calls"]] == ["generate", "generate", "generate", "repair"], "local_paid_prefix")
    errors = append["errors"]
    require(len(errors) == 1 and errors[0].get("code") == "append_input_preparation_failed"
            and "runner_context_budget_exceeded" in errors[0].get("detail", "")
            and all(text in errors[0]["detail"] for text in
                    ("estimated_input_tokens=94657", "continuation_reserve=2000", "limit=96000")), "known_unreserved_capacity_failure")
    require(all(_number(row["outcome"].get("active_elapsed_seconds")) for row in calls)
            and _number(state["active_elapsed_seconds"])
            and state["active_elapsed_seconds"] >= sum(row["outcome"]["active_elapsed_seconds"] for row in calls), "clock_changed")
    limits = state["planning_runtime"]["limits"]
    require(limits == {"request_limit": 96, "candidate_budget_sec": 2700, "synthesis_budget_sec": 1200,
                       "total_budget_sec": 13500}
            and state["mvg.run_invocation_limit"] == 96 and model_used(state) < 3900
            and state["active_elapsed_seconds"] < 13500, "native_budget_changed_or_exhausted")
    require(state["b_route_campaign_funding"] == {"schema_version": "newrouge.story25-native-funding.v1",
                "paid_or_unknown_before_run": 55, "campaign_limit": 290, "subsequent_full_reservation": 192,
                "maximum_native_charges": 43, "released": 0}, "campaign_funding_changed")


def _files(root):
    files, directories = {}, []
    for path in (root, *sorted(root.rglob("*"))):
        info = path.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400, "reparse_forbidden")
        require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode), "filesystem_type")
        if path.is_file():
            require(info.st_nlink == 1, "hardlink_forbidden")
            files[path.relative_to(root).as_posix()] = image(path.read_bytes())
        else:
            directories.append(path.relative_to(root).as_posix())
    return {"files": files, "directories": directories}


def _durable(path, value, *, exclusive=False):
    codec.validate_json_value(value)
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    target = path if exclusive else path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with target.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    if not exclusive:
        os.replace(target, path)


def _immutable(run_dir, mutable):
    result = {}
    for path in sorted(run_dir.rglob("*")):
        info = path.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400, "old_artifact_reparse")
        require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode), "old_artifact_type")
        if stat.S_ISREG(info.st_mode):
            require(info.st_nlink == 1, "old_artifact_hardlink")
            name = path.relative_to(run_dir).as_posix()
            if name not in mutable:
                result[name] = codec.raw_digest(codec.read_reference_bytes(run_dir, name))
    return result


def _record(root, state):
    reference = state.get(REFERENCE)
    require(type(reference) is dict and set(reference) == {"schema_version", "record_ref", "record_digest", "artifact_root"}
            and reference["schema_version"] == SCHEMA and Path(reference["artifact_root"]).resolve() == root, "typed_reference")
    path = sources.checked_path(root, reference["record_ref"])
    raw = codec.read_reference_bytes(root, reference["record_ref"])
    require(codec.raw_digest(raw) == reference["record_digest"], "record_changed")
    record = codec.strict_json_loads(raw)
    require(record["schema_version"] == SCHEMA and record["run_id"] == state["run_id"] == "c4"
            and record["released"] == 0 and record["retained_slots"] == 8
            and record["maximum_prefix_resumes"] == 1, "record_identity_or_refund_changed")
    claim = read(root, path.with_name("claim.json").relative_to(root).as_posix())
    require(claim["schema_version"] == SCHEMA and claim["record_digest"] == reference["record_digest"]
            and claim["retained_slots"] == 8, "preparation_claim_changed")
    marker = read(root, path.with_name("committed.json").relative_to(root).as_posix())
    require(marker == {"record_digest": reference["record_digest"],
                       "transition_digest": record["transition"]["transition_digest"]}, "partial_transaction")
    return path, record


def validate_recovery(root, state):
    if state.get("b_route_input_path_recovery"):
        import _b_route_input_path_recovery as path_recovery
        return path_recovery.original_partial_record(root, state)
    root = Path(root).resolve()
    _, record = _record(root, state)
    old = codec.strict_json_loads(image_bytes(record["previous_run"]))
    append = codec.strict_json_loads(image_bytes(record["previous_append"]))
    retained_shape(old, append)
    require(same(record["original_current"], append["current"])
            and same(record["original_local_calls"], append["calls"]), "archived_partial_identity_changed")
    require(same(state["b_route_execution_transition"], record["transition"])
            and same(state["b_route_execution_history"], record["history"])
            and same(state["b_route_output_schema_policy"], record["output_schema_policy"])
            and record.get("input_compact_policy") == compact.CURRENT_SCHEMA
            and state.get("b_route_input_compact_policy") == record["input_compact_policy"], "source_frame_changed")
    for field in ("runtime_identity", "planning_runtime", "b_route_campaign_funding", "b_route_review_recovery",
                  "b_route_synthesis_recovery", "mvg.run_invocation_limit"):
        require(same(state[field], old[field]), "retained_identity_or_budget_changed:" + field)
    ledger = state["capability_selection"]
    require(same(ledger["calls"][:8], old["capability_selection"]["calls"])
            and type(ledger["total_invocations"]) is int and ledger["total_invocations"] == len(ledger["calls"])
            and 8 <= ledger["total_invocations"] <= 43
            and [row["number"] for row in ledger["calls"]] == list(range(1, ledger["total_invocations"] + 1))
            and ledger["lineage_invocations"]["candidate-1"] == 4
            and ledger["lineage_invocations"]["candidate-2"] == sum(row.get("candidate") == "candidate-2" for row in ledger["calls"])
            and _number(state["active_elapsed_seconds"]) and state["active_elapsed_seconds"] >= old["active_elapsed_seconds"],
            "paid_prefix_counter_or_clock_changed")
    run = sources.checked_path(root, record["run_ref"])
    for name, expected in record["immutable_files"].items():
        require(codec.raw_digest(codec.read_reference_bytes(run, name)) == expected, "old_file_changed:" + name)
    failed = sources.checked_path(run, WORKSPACE + "/capability-append/c5")
    require(same(_files(failed), record["failed_preparation"]), "failed_c5_preparation_changed")
    local = read(run, WORKSPACE + "/capability-append/append-ledger.json")
    require(same(local["calls"][:4], append["calls"]) and local["total_invocations"] == len(local["calls"]) >= 4
            and same(local["binding"], append["binding"]), "local_prefix_or_counter_changed")
    # Validate the previous epoch under its original state, never under R9's
    # different transition. The old helper also checks its admitted first slot.
    import _b_route_synthesis_recovery as previous
    previous.validate_recovery(root, old)
    return record


def call_root(state, workspace, number, slot):
    require(type(number) is int and number >= 1, "local_call_number")
    base = Path(workspace) / "capability-append"
    if state.get("b_route_input_path_recovery") and slot == "candidate-2" and number >= 5:
        from _b_route_input_path_recovery import NAMESPACE as short_namespace
        return base / short_namespace / ("c" + str(number))
    if state.get(REFERENCE) and slot == "candidate-2" and number >= 5:
        return base / NAMESPACE / ("c" + str(number))
    return base / ("c" + str(number))


def _marker(record, state):
    return {"schema_version": SCHEMA + ".resume", "record_digest": state[REFERENCE]["record_digest"],
            "old_global_calls": 8, "old_local_calls": 4, "current_digest": canonical_sha(record["original_current"])}


def _fresh_owner(root, state, record):
    owner = read(root, record["run_ref"] + "/run.json")
    require(same(owner.get(REFERENCE), state.get(REFERENCE)), "owner_recovery_reference_changed")
    require(same(owner.get("b_route_input_path_recovery"), state.get("b_route_input_path_recovery")), "owner_path_reference_changed")
    validate_recovery(root, owner)
    private = state["capability_selection"]["calls"]
    require(same(owner["capability_selection"]["calls"][:len(private)], private)
            and owner["capability_selection"]["total_invocations"] >= state["capability_selection"]["total_invocations"]
            and owner["active_elapsed_seconds"] >= state["active_elapsed_seconds"], "owner_cannot_refund_private_snapshot")
    return owner


def _claimed(root, state, record):
    path = sources.checked_path(root, state[REFERENCE]["record_ref"]).with_name("resume-claim.json")
    require(same(read(root, path.relative_to(root).as_posix()), _marker(record, state)), "resume_claim_missing_or_changed")
    if state.get("b_route_input_path_recovery"):
        import _b_route_input_path_recovery as path_recovery
        path_recovery.claimed(root, state)


def _replacement_authorized(owner, local, current, original):
    context = current.get("context")
    if (type(context) is not int or context <= 1 or current.get("proposal") is not None
            or current.get("issue") is not None or current.get("delta") is not None
            or current.get("issue_attempts") != {} or current.get("capability_id") != original["capability_id"]):
        return False
    ledger = owner["capability_selection"]
    events = ledger.get("replacement_events", [])
    for event in events:
        if (event.get("candidate") != "candidate-2" or event.get("context") != context
                or event.get("scope_id") != original["capability_id"] or type(event.get("round")) is not int
                or not 1 <= event["round"] <= 3 or type(event.get("event_number")) is not int
                or not 1 <= event["event_number"] <= len(events) or not same(events[event["event_number"] - 1], event)
                or ledger.get("replacement_depths", {}).get("candidate-2") != event["round"]):
            continue
        if (sum(same(row, event) for row in local.get("replacement_reservations", [])) == 1
                and any(row.get("capability_id") == original["capability_id"] and row.get("context") == context - 1
                        and row.get("issue_id") == event.get("issue_id") and row.get("repair_attempts") == 3
                        for row in local.get("restarts", []))):
            return True
    return False


def _retained_machine_rejection(root, runtime, owner, local, current, record, row, materials, proposal):
    original = record["original_current"]
    if (not same(current.get("proposal"), original["proposal"]) or not same(current.get("delta"), original["delta"])
            or not same(current.get("issue"), original["issue"])
            or not same(materials.get("prior_candidate"), current["proposal"])
            or not same(materials.get("repair_issue"), current["issue"])):
        return False
    entries = [entry for entry in local.get("rejected_repairs", [])
               if entry.get("capability_id") == current["capability_id"]
               and entry.get("context") == current["context"]
               and entry.get("invocations") == row["request_identity"]["attempt"]
               and "repair_new_machine_issue" in entry.get("errors", [])]
    if len(entries) != 1:
        return False
    before = runtime.preservation(local["accepted"], current["proposal"]) + runtime.machine(root, owner, current["proposal"])
    after = runtime.preservation(local["accepted"], proposal) + runtime.machine(root, owner, proposal)
    return bool({issue_key(item) for item in after} - {issue_key(item) for item in before})


def _known_successor(root, state, record, owner, current):
    """Authenticate later progress from the owner, never a stale worker copy."""
    later = owner["capability_selection"]["calls"][8:]
    if not later or any(row.get("outcome", {}).get("status") != "completed" for row in later):
        return False
    _claimed(root, state, record)
    run = sources.checked_path(root, record["run_ref"])
    local = read(run, WORKSPACE + "/capability-append/append-ledger.json")
    if not same(local.get("current"), current):
        return False
    previous_append = codec.strict_json_loads(image_bytes(record["previous_append"]))
    require(same(local["accepted"], previous_append["accepted"]), "successor_accepted_seed_changed")
    frozen = read(run, "analysis-input/b-route-prepared.json")
    require(canonical_sha(frozen) == owner["planning_runtime"]["frozen_sha256"]
            and frozen["input_identity"] == owner["planning_runtime"]["input_identity"], "successor_frozen_changed")
    import _b_route_planning_runtime as runtime
    replacement = _replacement_authorized(owner, local, current, record["original_current"])
    for row in reversed(later):
        if (row.get("candidate") != "candidate-2" or row.get("phase") not in {"generate", "repair"}
                or row.get("request_identity", {}).get("synthesis") is not True):
            continue
        binding = runtime.verify_reserved_call(run, row)
        require(type(binding) is dict, "successor_binding_missing")
        materials = runtime.bound_materials(binding, owner, frozen)
        draft = runtime.decode_generation_output(frozen, materials, runtime.verify_call(binding))
        drafts = [item["value"] for item in materials["root_request"]["input"]["prior_drafts"]] + [draft]
        expected = {"schema_version": runtime.candidate.SCHEMA, "input_stage": "3b", "input_identity": frozen["input_identity"],
            "provenance": {"kind": "model_draft", "declaration": "Complete original model draft chain; execution separately replayed",
                "upstream_model_history": "declared_model", "draft_chain": drafts, "final_draft_identity": canonical_sha(draft)},
            "content": deepcopy(draft["content"])}
        require(materials["phase"] == "generation" and materials["slot"] == "candidate-2"
                and materials["generation"] == row["generation"] == 1
                and materials["execution"] == row["execution"] == 1
                and type(materials["lineage_context"]) is int
                and same(materials["accepted_seed"], local["accepted"])
                and materials["lineage_identity"] == runtime.lineage_identity(owner, local["accepted"], "candidate-2",
                                                                            materials["lineage_context"], 1, 1),
                "successor_request_or_lineage_changed")
        runtime.planning.validate_draft_chain(frozen, drafts)
        if replacement and materials["lineage_context"] == current["context"] - 1:
            return True
        if materials["lineage_context"] == current["context"] and (same(current.get("proposal"), expected)
                or _retained_machine_rejection(root, runtime, owner, local, current, record, row, materials, expected)):
            return True
    return False


def resume_propose_attempt(root, state, workspace, current, ledger):
    if not state.get(REFERENCE) or state.get("runtime_slot") != "candidate-2":
        return False
    root = Path(root).resolve()
    record = validate_recovery(root, state)
    owner = _fresh_owner(root, state, record)
    if owner["capability_selection"]["total_invocations"] > 8:
        # A genuinely completed subsequent proposal follows the ordinary native
        # repair accounting. It cannot reuse the old batch-prefix shortcut.
        require(_known_successor(root, state, record, owner, current), "unproven_changed_repair")
        return False
    require(same(current, record["original_current"]), "unproven_changed_repair")
    require(owner["capability_selection"]["total_invocations"] == 8
            and ledger["total_invocations"] == 4 and same(ledger["calls"], record["original_local_calls"])
            and current["issue_attempts"] == {issue_key(current["issue"]): 1}, "partial_attempt_already_consumed_or_changed")
    run = sources.checked_path(root, record["run_ref"])
    require(Path(workspace).resolve() == (run / WORKSPACE).resolve(), "workspace_changed")
    if state.get("b_route_input_path_recovery"):
        import _b_route_input_path_recovery as path_recovery
        path_recovery.claim_resume(root, state, current, ledger)
        return True
    path = sources.checked_path(root, state[REFERENCE]["record_ref"]).with_name("resume-claim.json")
    _durable(path, _marker(record, state), exclusive=True)
    return True


def resume_generation(root, state, workspace, frozen, accepted, prior, issue, context):
    if not state.get(REFERENCE) or state.get("runtime_slot") != "candidate-2":
        return None
    root = Path(root).resolve()
    record = validate_recovery(root, state)
    owner = _fresh_owner(root, state, record)
    current = record["original_current"]
    if owner["capability_selection"]["total_invocations"] > 8:
        run = sources.checked_path(root, record["run_ref"])
        local = read(run, WORKSPACE + "/capability-append/append-ledger.json")
        changed = local.get("current")
        require(type(changed) is dict and same(prior, changed.get("proposal"))
                and same(issue, changed.get("issue")) and context == changed.get("context")
                and _known_successor(root, state, record, owner, changed), "unproven_changed_partial_inputs")
        return None
    require(same(prior, current["proposal"]) and same(issue, current["issue"]) and context == 1,
            "unproven_changed_partial_inputs")
    _claimed(root, state, record)
    run = sources.checked_path(root, record["run_ref"])
    require(Path(workspace).resolve() == (run / WORKSPACE).resolve(), "workspace_changed")
    binding, draft = read(run, record["completed_binding_ref"]), read(run, record["completed_draft_ref"])
    require(canonical_sha(binding) == record["completed_binding_digest"] and canonical_sha(draft) == record["completed_draft_digest"],
            "completed_prefix_changed")
    import _b_route_planning_runtime as runtime
    require(same(runtime.verify_reserved_call(run, state["capability_selection"]["calls"][7]), binding), "batch8_reservation_changed")
    require(same(runtime.decode_generation_carrier(runtime.verify_call(binding)), draft), "batch8_output_changed")
    materials = runtime.bound_materials(binding, state, frozen)
    expected = json.loads(runtime.request_attempt(frozen, batch=1, drafts=[], delivery=runtime.wire_delivery(state))["payload"])
    require(materials["phase"] == "generation" and materials["slot"] == "candidate-2"
            and materials["generation"] == materials["execution"] == materials["lineage_context"] == context == 1
            and same(materials["root_request"], expected) and same(materials["accepted_seed"], accepted)
            and same(materials["prior_candidate"], prior) and same(materials["repair_issue"], issue)
            and materials["lineage_identity"] == runtime.lineage_identity(state, accepted, "candidate-2", 1, 1, 1),
            "batch8_request_or_lineage_changed")
    runtime.planning.validate_draft_chain(frozen, [draft])
    return [draft], [binding]


def prepare(root, run_dir, *, original_source_root, current_commit, prior_source_root, prior_commit=PRIOR_COMMIT):
    """Append-only preparation under the native coordinator lock; zero dispatch."""
    import _b_route_planning_runtime as runtime
    import _b_route_execution_transition as transition
    from _mvg_capability_checkpoint import coordinator_lock
    root, run_dir = Path(root).resolve(), Path(run_dir).resolve()
    require(run_dir == sources.checked_path(root, "logs/ci/capability-planning/c4"), "explicit_run_required")
    with coordinator_lock(run_dir):
        raw_run = codec.read_reference_bytes(run_dir, "run.json")
        raw_append = codec.read_reference_bytes(run_dir, WORKSPACE + "/capability-append/append-ledger.json")
        old, append = codec.strict_json_loads(raw_run), codec.strict_json_loads(raw_append)
        retained_shape(old, append)
        require(not old.get(REFERENCE) and prior_commit == PRIOR_COMMIT
                and old["b_route_execution_transition"]["current_commit"] == prior_commit
                and Path(old["b_route_execution_transition"]["current_source_root"]).resolve() == Path(prior_source_root).resolve(),
                "already_prepared_or_prior_source_changed")
        new_transition = transition.build_successor_transition(root, old, original_source_root, current_commit,
                                                               prior_source_root, prior_commit)
        history = deepcopy(old["b_route_execution_history"])
        history[old["b_route_execution_transition"]["transition_digest"]] = deepcopy(old["b_route_execution_transition"])
        next_state = deepcopy(old)
        next_state.update(b_route_execution_transition=new_transition, b_route_execution_history=history,
                          b_route_output_schema_policy=runtime.PROVIDER_SCHEMA_POLICY,
                          b_route_input_compact_policy=compact.CURRENT_SCHEMA)
        binding_ref = WORKSPACE + "/capability-append/c4/execution-binding-4-r.json"
        draft_ref = WORKSPACE + "/capability-append/c4/canonical-draft.json"
        binding, draft = read(run_dir, binding_ref), read(run_dir, draft_ref)
        require(same(runtime.verify_reserved_call(run_dir, old["capability_selection"]["calls"][7]), binding), "batch8_reservation_unproven")
        require(same(runtime.decode_generation_carrier(runtime.verify_call(binding)), draft), "batch8_output_unproven")
        frozen = transition.load_prepared(root, next_state)
        materials = runtime.bound_materials(binding, next_state, frozen)
        current = append["current"]
        accepted = runtime.seed(next_state, run_dir / "analysis-input")
        expected = json.loads(runtime.request_attempt(frozen, batch=1, drafts=[], delivery=runtime.wire_delivery(next_state))["payload"])
        require(materials["phase"] == "generation" and materials["slot"] == "candidate-2"
                and materials["generation"] == materials["execution"] == materials["lineage_context"] == 1
                and same(materials["root_request"], expected)
                and same(materials["prior_candidate"], current["proposal"]) and same(materials["repair_issue"], current["issue"])
                and same(materials["accepted_seed"], accepted)
                and materials["lineage_identity"] == runtime.lineage_identity(next_state, accepted, "candidate-2", 1, 1, 1),
                "batch8_partial_request_unproven")
        runtime.planning.validate_draft_chain(frozen, [draft])
        failed = sources.checked_path(run_dir, WORKSPACE + "/capability-append/c5")
        failed_preparation = _files(failed)
        require(bool(failed_preparation["files"]) and not any("execution-binding" in name or name.endswith("r.json")
                                                            for name in failed_preparation["files"]), "c5_must_be_unreserved")
        home = run_dir / "recovery" / NAMESPACE
        mutable = {"run.json", "model-execution.json", "capability-coordinator.lock",
                   "candidates/candidate-2/lineage-execution.json", WORKSPACE + "/capability-append/append-ledger.json"}
        immutable = _immutable(run_dir, mutable)
        record = {"schema_version": SCHEMA, "run_id": "c4", "run_ref": run_dir.relative_to(root).as_posix(),
                  "previous_run": image(raw_run), "previous_append": image(raw_append), "immutable_files": immutable,
                  "failed_preparation": failed_preparation, "transition": new_transition, "history": history,
                  "output_schema_policy": runtime.PROVIDER_SCHEMA_POLICY, "input_compact_policy": compact.CURRENT_SCHEMA,
                  "original_current": deepcopy(current),
                  "original_local_calls": deepcopy(append["calls"]), "completed_binding_ref": binding_ref,
                  "completed_draft_ref": draft_ref, "completed_binding_digest": canonical_sha(binding),
                  "completed_draft_digest": canonical_sha(draft), "retained_slots": 8, "released": 0,
                  "maximum_prefix_resumes": 1, "candidate_model_used": model_used(old),
                  "candidate_model_remaining": 3900 - model_used(old), "global_active_elapsed_seconds": old["active_elapsed_seconds"],
                  "prior_source_root": str(Path(prior_source_root).resolve()), "prior_commit": prior_commit}
        record_raw = (json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        home.mkdir(parents=True, exist_ok=False)
        _durable(home / "claim.json", {"schema_version": SCHEMA, "record_digest": codec.raw_digest(record_raw),
                                      "retained_slots": 8}, exclusive=True)
        _durable(home / "record.json", record, exclusive=True)
        reference = {"schema_version": SCHEMA, "record_ref": (home / "record.json").relative_to(root).as_posix(),
                     "record_digest": codec.raw_digest(record_raw), "artifact_root": str(root)}
        next_state[REFERENCE] = reference
        next_state["capability_selection"]["terminal"] = False
        next_state["capability_selection"]["current"]["admissions"]["candidate-2"]["retryable"] = True
        next_state.update(phase="partial-repair-recovery-prepared", selection_status="pending")
        next_state.pop("selection_block_reason", None)
        next_append = deepcopy(append)
        next_append.setdefault("input_preparation_errors", []).append({"errors": deepcopy(append["errors"]), "recovery": reference})
        next_append.update(status="generating", errors=[])
        _durable(run_dir / WORKSPACE / "capability-append/append-ledger.json", next_append)
        _durable(run_dir / "run.json", next_state)
        _durable(home / "committed.json", {"record_digest": reference["record_digest"],
                                           "transition_digest": new_transition["transition_digest"]}, exclusive=True)
        validate_recovery(root, next_state)
        return {"status": "partial-repair-recovery-prepared", "record": reference, "model_calls": 0,
                "retained_logical_calls": 8, "next_native_dispatch": 9, "next_local_dispatch": 5, "released": 0}
