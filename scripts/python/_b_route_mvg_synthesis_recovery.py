"""One typed m4 synthesis continuation; retain every original paid result.

This owner never edits a model result, refunds a reservation, manufactures a
business issue or performs a model call. Source epoch and native admission
owners remain responsible for original/current qualification.
"""
from copy import deepcopy
import base64
import math
import os
from pathlib import Path
import re
import stat
import uuid

import _b_route_codec as codec
import _b_route_sources as sources

SCHEMA = "newrouge.b-route-mvg-synthesis-recovery.v1"
MVG_EPOCH_SCHEMA = "newrouge.b-route-mvg-source-epoch.v1"
REFERENCE = "b_route_mvg_synthesis_recovery"
NAMESPACE = "m1"
PRIOR_COMMIT = "dc245b3b3d14abd512879369b30692536dfac4fd"
RUN_REF = "logs/ci/mvg-planning/m4"
WORKSPACE = "candidates/candidate-2/scope-1"
REJECTION_POINTER = "/content/evidence_source_refs/0/files/0/raw_digest"
_CONTROL_HOME = "logs/ci/2026-11-06/story25-path-recovery/host-resume-v11/post-capability-v16/"
ROOT_CONTROL_REFS = {"supervisor_receipt": _CONTROL_HOME + "supervisor/exit.json",
                     "original_failure": _CONTROL_HOME + "native-mvg/failure.json",
                     "supervisor_started": _CONTROL_HOME + "supervisor/started.json",
                     "supervisor_claim": _CONTROL_HOME + "supervisor/claim.json",
                     "native_claim": "logs/ci/2026-11-06/story25-path-recovery/native-stages/mvg/claim.json"}
ROOT_CONTROL_PINS = {"supervisor_receipt": "sha256:1ddfbd0d3aa6768e4505e58075ea95dedf67dbf7adbb24884619738e3cd358d6",
                     "original_failure": "sha256:72bafb3ec2f11cbd953bd77752cab3f968ca0ac20b8c32357930dd9a00a51d80",
                     "supervisor_started": "sha256:1c795fd1e8f30f90c4fec10995cf54917f8c7582cc406df6077d7c3c9bba2131",
                     "supervisor_claim": "sha256:48af2cdb1ecc60ddadce5985b3c559d70523011bdbaa05b15b92b8d25d06b0b4",
                     "native_claim": "sha256:48c1870570469dfe1f9af80a32c1bd87b16d3e83f1530aa45cb7b77c295ad216"}
HINT_KEY = "known_synthesis_schema_recovery"
ROOT_MANIFEST_REF = "logs/ci/2026-11-07/story25-m4-v16-terminal-snapshot/manifest.json"
ROOT_MANIFEST_DIGEST = "sha256:2e3c7706f93c7ebc5f908a68faa2f5fe426437c635ca248ff7dfb6e7082d0b12"
ORIGINAL_RUN_DIGEST = "sha256:e7c8431eed6d15b0d041bec3de8d55b1b399ff4922308419c6e8287f441e2164"
ORIGINAL_APPEND_DIGEST = "sha256:5420ad6abc50b4026feec5357e641afcd4521570adb455ebb60b6d1592729ceb"
_MUTABLE = frozenset({"run.json", "model-execution.json", "capability-coordinator.lock",
                      "candidates/candidate-2/lineage-execution.json",
                      WORKSPACE + "/capability-append/append-ledger.json"})
_SEALED = ("analysis-input", "candidates/candidate-1", WORKSPACE + "/analysis-input",
           WORKSPACE + "/capability-append/c1", WORKSPACE + "/capability-append/c2", WORKSPACE + "/lifecycle")


def require(value, reason):
    if not value:
        raise ValueError("b_route_mvg_synthesis_recovery:" + reason)


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


def _integer(value, expected):
    return type(value) is int and value == expected


def _active_recovery(state):
    epoch = state.get("b_route_execution_transition") or {}
    reference = state.get(REFERENCE)
    if epoch.get("schema_version") == MVG_EPOCH_SCHEMA:
        require(type(reference) is dict and bool(reference), "typed_epoch_requires_recovery_reference")
    if reference:
        require(type(reference) is dict, "recovery_reference_not_object")
        return True
    return False


def retained_shape(state, append):
    """Exact known schema rejection, not an arbitrary failed/unknown proposal."""
    ledger = state["capability_selection"]
    calls = ledger["calls"]
    desc = state["planning_runtime"]
    require(state["run_id"] == "m4" and state["input_stage"] == "3b"
            and desc["planner"] == "mvg" and desc["profile"] == "3b-mvg-v1"
            and same(desc["limits"], {"request_limit": 192})
            and _integer(state["mvg.run_invocation_limit"], 192), "run_or_native_limits")
    expected = [("candidate-1", "generate", 1, False), ("candidate-1", "generate", 2, True),
                ("candidate-1", "repair", 3, False), ("candidate-1", "repair", 4, True),
                ("candidate-1", "semantic", 5, False), ("candidate-2", "generate", 1, False),
                ("candidate-2", "generate", 2, True)]
    require(type(ledger["total_invocations"]) is int and ledger["total_invocations"] == len(calls) == 7
            and same(ledger["lineage_invocations"], {"candidate-1": 5, "candidate-2": 2, "candidate-3": 0}),
            "paid_seven_prefix")
    for number, (row, expected_row) in enumerate(zip(calls, expected), 1):
        request = row["request_identity"]
        require(_integer(row["number"], number) and row["reservation_id"] == f"m4:dispatch:{number}"
                and same([row["candidate"], row["phase"], request["attempt"], request["synthesis"]], list(expected_row))
                and _integer(row["generation"], 1) and _integer(row["execution"], 1)
                and row["outcome"]["status"] == "completed"
                and _number(row["outcome"]["active_elapsed_seconds"]), "paid_row_identity")
    require(_number(state["active_elapsed_seconds"])
            and state["active_elapsed_seconds"] >= sum(row["outcome"]["active_elapsed_seconds"] for row in calls),
            "clock_changed")
    require(ledger["terminal"] is True and ledger["selected"] == []
            and state["selection_status"] == "blocked"
            and state["selection_block_reason"] == "selection_blocked_insufficient_admitted_candidates",
            "terminal_identity")
    current = ledger["current"]
    require(_integer(current["order_index"], 0) and _integer(current["execution"], 1)
            and current["selection_attempts"] == []
            and set(current["admissions"]) == {"candidate-1", "candidate-2"}, "pending_scope")
    for slot, status, count, terminal in [("candidate-1", "admitted", 5, False), ("candidate-2", "blocked", 2, True)]:
        admission = current["admissions"][slot]
        require(admission["status"] == status and _integer(admission["total_invocations"], count)
                and admission["append_terminal"] is terminal and admission["retryable"] is False
                and _integer(admission.get("generation", 1), 1) and _integer(admission.get("execution", 1), 1), "admission_identity")
    local = append["current"]
    require(append["status"] == "blocked" and _integer(append["total_invocations"], 2) and len(append["calls"]) == 2
            and append["completed"] == append["records"] == []
            and _integer(local["context"], 1) and local["issue"] is None and local["proposal"] is None
            and local["delta"] is None and local["issue_attempts"] == {}, "local_original_state")
    require([row["reservation_id"] for row in append["calls"]] == ["m4:dispatch:6", "m4:dispatch:7"]
            and same([row["number"] for row in append["calls"]], [1, 2])
            and [row["phase"] for row in append["calls"]] == ["generate", "generate"], "local_paid_prefix")
    require(append["errors"] == [{"code": "append_execution_failure", "stage": "generate",
                                   "error_type": "runner_execution_failed", "detail": "schema_validation_failed"}],
            "known_schema_execution_rejection")
    require(same(state["b_route_campaign_funding"], {"schema_version": "newrouge.story25-native-funding.v1",
                "paid_or_unknown_before_run": 66, "campaign_limit": 290, "subsequent_full_reservation": 0,
                "maximum_native_charges": 224, "released": 0}), "original_funding")


def _root_snapshot(root):
    raw = codec.read_reference_bytes(Path(root).resolve().parent, ROOT_MANIFEST_REF)
    require(codec.raw_digest(raw) == ROOT_MANIFEST_DIGEST, "root_snapshot_changed")
    return codec.strict_json_loads(raw)


def _root_controls(root, observation=None):
    """Read literal-pinned original files; a caller's statement is never proof."""
    require(bool(ROOT_CONTROL_PINS) and set(ROOT_CONTROL_PINS) == set(ROOT_CONTROL_REFS),
            "root_literal_controls_not_frozen")
    _root_snapshot(root)
    values = {}
    for name, reference in ROOT_CONTROL_REFS.items():
        raw = codec.read_reference_bytes(root, reference)
        require(codec.raw_digest(raw) == ROOT_CONTROL_PINS[name], "original_control_changed:" + name)
        values[name] = codec.strict_json_loads(raw)
    receipt = values["supervisor_receipt"]
    require(type(receipt["os_exit_code"]) is int and receipt["os_exit_code"] == 1
            and receipt["exit_source"] == "held_subprocess_handle_wait"
            and receipt["source_pins_unchanged"] is True, "actual_held_handle_os1_required")
    for reference, digest in receipt["pins"].items():
        path = Path(reference)
        require(path.is_absolute() and path.is_relative_to(Path(root).resolve().parent), "control_source_escape")
        require(codec.raw_digest(codec.read_reference_bytes(path.parent, path.name)) == digest, "control_source_changed")
    expected = {"schema_version": SCHEMA + ".root-terminal-observation", "source_commit": PRIOR_COMMIT,
                "controls": deepcopy(ROOT_CONTROL_PINS), "os_exit_code": 1,
                "exit_source": "held_subprocess_handle_wait", "released": 0,
                "root_manifest_digest": ROOT_MANIFEST_DIGEST}
    if observation is not None:
        require(same(observation, expected), "root_observation_must_match_literal_original_controls")
    return expected


def root_terminal_observation(root):
    """Return a fact only after reading the literal-pinned original OS1 files."""
    return _root_controls(Path(root).resolve())


def graph_observations(draft):
    """Compare actual unedited declared endpoints, without issuing admission."""
    flows = draft["content"]["definitions"]["flows"]
    endpoint = lambda value: (value["flow_id"], value["node_id"])
    edges = {(endpoint(edge["from"]), endpoint(edge["to"])) for flow in flows for edge in flow["graph"]["edges"]}
    return [{"classification": "unadmitted_original_graph_observation", "entity_id": handoff["id"],
             "flow_id": flow["id"], "from": deepcopy(handoff["from"]), "to": deepcopy(handoff["to"]),
             "expected": "handoff corresponds to declared graph edge",
             "rule_source": "_b_route_candidate.check_graph", "formal_business_finding": False}
            for flow in flows for handoff in flow["handoffs"]
            if (endpoint(handoff["from"]), endpoint(handoff["to"])) not in edges]


def _snapshot(run, *, excluding=None):
    """Membership plus exact hashes; no broad unknown-directory/file mask."""
    files, directories = {}, []
    for path in (run, *sorted(run.rglob("*"))):
        if excluding is not None and path.is_relative_to(excluding):
            continue
        info = path.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                "reparse_topology")
        require(stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode), "special_file")
        relative = path.relative_to(run).as_posix()
        if stat.S_ISDIR(info.st_mode):
            directories.append(relative)
        elif relative == "capability-coordinator.lock":
            require(info.st_size == 1 and info.st_nlink == 1, "native_lock_shape")
        else:
            require(info.st_nlink == 1, "hardlinked_evidence")
            files[relative] = codec.raw_digest(codec.read_reference_bytes(run, relative))
    return {"files": files, "directories": directories}


def _immutable_snapshot(snapshot):
    return {"files": {name: digest for name, digest in snapshot["files"].items() if name not in _MUTABLE},
            "directories": snapshot["directories"], "sealed_subtrees": list(_SEALED)}


def _close_immutable(run, record):
    for name, digest in record["immutable"]["files"].items():
        require(codec.raw_digest(codec.read_reference_bytes(run, name)) == digest, "old_file_changed:" + name)
    # Old directories remain real and cannot be substituted; additions are not historical evidence.
    for name in record["immutable"]["directories"]:
        path = sources.checked_path(run, name) if name != "." else run
        info = path.lstat()
        require(stat.S_ISDIR(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                "old_directory_changed:" + name)
    for prefix in record["immutable"]["sealed_subtrees"]:
        tree = sources.checked_path(run, prefix)
        expected_files = {name[len(prefix) + 1:]: digest for name, digest in record["immutable"]["files"].items()
                          if name.startswith(prefix + "/")}
        expected_dirs = ["." if name == prefix else name[len(prefix) + 1:]
                         for name in record["immutable"]["directories"]
                         if name == prefix or name.startswith(prefix + "/")]
        actual = _snapshot(tree)
        require(actual["files"] == expected_files and set(actual["directories"]) == set(expected_dirs),
                "sealed_historical_membership_changed:" + prefix)


def _candidate(runtime, frozen, drafts):
    return {"schema_version": runtime.candidate.SCHEMA, "input_stage": "3b", "input_identity": frozen["input_identity"],
            "provenance": {"kind": "model_draft", "declaration": "Complete original model draft chain; execution separately replayed",
                           "upstream_model_history": "declared_model", "draft_chain": drafts,
                           "final_draft_identity": codec.canonical_digest(drafts[-1])},
            "content": deepcopy(drafts[-1]["content"])}


def _verify_original(root, run, state, append):
    """Execute existing native owners, not a diagnosis file or synthetic approval."""
    import _b_route_planning_runtime as runtime
    from _mvg_capability_selection import candidate_artifacts
    frozen = runtime.frozen_input(root, state)
    scopes = runtime.scopes(state, run / "analysis-input")
    accepted = runtime.seed(state, run / "analysis-input")
    require(same(accepted, append["accepted"]), "original_seed_changed")
    admission = state["capability_selection"]["current"]["admissions"]["candidate-1"]
    candidate_artifacts(root, run, state, scopes, 0, accepted, [], admission, check_originals=True)
    require(len(frozen["transport"]["batches"]) == 1, "original_single_batch_changed")
    drafts, bindings = [], []
    for index in (5, 6):
        row = state["capability_selection"]["calls"][index]
        binding = runtime.verify_reserved_call(run, row)
        material = runtime.bound_materials(binding, state, frozen)
        draft = runtime.decode_generation_output(frozen, material, runtime.verify_call(binding))
        draft_ref = WORKSPACE + f"/capability-append/c{index - 4}/canonical-draft.json"
        require(same(draft, read(run, draft_ref)), "original_canonical_draft_changed")
        expected_root = json_request(runtime, frozen, drafts, index == 5, state)
        require(material["phase"] == "generation" and material["slot"] == "candidate-2"
                and material["generation"] == material["execution"] == material["lineage_context"] == 1
                and material["prior_candidate"] is material["repair_issue"] is None
                and same(material["root_request"], expected_root) and same(material["accepted_seed"], accepted)
                and material["lineage_identity"] == runtime.lineage_identity(state, accepted, "candidate-2", 1, 1, 1),
                "original_complete_request_changed")
        drafts.append(draft)
        bindings.append(binding)
        runtime.planning.validate_draft_chain(frozen, drafts)
    proposal = _candidate(runtime, frozen, drafts)
    errors = list(runtime.candidate.schemas.validator(runtime.candidate.SCHEMA, auxiliary=True).iter_errors(proposal))
    require(bool(errors) and all("/" + "/".join(map(str, error.absolute_path)) == REJECTION_POINTER
            and error.validator in {"pattern", "minLength"} for error in errors), "different_or_missing_schema_rejection")
    row = drafts[-1]["content"]["evidence_source_refs"][0]["files"][0]
    expected_digest = frozen["inputs"]["dependencies"]["files"][row["path"]]
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", expected_digest) is not None
            and expected_digest != row["raw_digest"], "original_authoritative_source_digest_missing")
    rejection = {"json_pointer": REJECTION_POINTER, "source_path": row["path"],
                 "observed_raw_digest": row["raw_digest"], "expected_raw_digest": expected_digest}
    rejection["structural_observations"] = graph_observations(drafts[-1])
    require([row["entity_id"] for row in rejection["structural_observations"]] == ["profile-to-harness"],
            "known_original_graph_observation_changed")
    return frozen, drafts, bindings, rejection


def json_request(runtime, frozen, drafts, batch, state):
    return codec.strict_json_loads(runtime.request_attempt(frozen, batch=1 if batch else None,
        drafts=drafts, delivery=runtime.wire_delivery(state))["payload"].encode("utf-8"))


def _durable(path, value, *, exclusive=False):
    codec.validate_json_value(value)
    import json
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    target = path if exclusive else path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with target.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    if not exclusive:
        os.replace(target, path)
    return raw


def _record(root, state):
    reference = state.get(REFERENCE)
    require(type(reference) is dict and set(reference) == {"schema_version", "record_ref", "record_digest", "artifact_root"}
            and reference["schema_version"] == SCHEMA and Path(reference["artifact_root"]).resolve() == root
            and reference["record_ref"] == RUN_REF + "/recovery/" + NAMESPACE + "/record.json", "typed_reference")
    path = sources.checked_path(root, reference["record_ref"])
    raw = codec.read_reference_bytes(root, reference["record_ref"])
    require(codec.raw_digest(raw) == reference["record_digest"], "record_changed")
    record = codec.strict_json_loads(raw)
    fields = {"schema_version", "run_id", "run_ref", "previous_run", "previous_append", "immutable", "transition",
              "history", "root_terminal_observation", "prior_commit", "batch_draft_ref", "batch_draft_digest",
              "batch_binding_digest", "rejected_synthesis_draft_ref", "rejected_synthesis_draft_digest",
              "rejected_synthesis_binding_digest", "schema_rejection", "retained_global_calls", "retained_local_calls",
              "next_global_call", "next_local_call", "maximum_new_synthesis_attempts", "released", "mutable_preimages"}
    require(set(record) == fields and _integer(record["next_global_call"], 8) and _integer(record["next_local_call"], 3),
            "record_fields_or_next_call_changed")
    require(record["schema_version"] == SCHEMA and record["run_id"] == "m4"
            and record["run_ref"] == RUN_REF and _integer(record["retained_global_calls"], 7)
            and _integer(record["retained_local_calls"], 2) and _integer(record["maximum_new_synthesis_attempts"], 1)
            and _integer(record["released"], 0) and record["prior_commit"] == PRIOR_COMMIT, "record_identity")
    require(record["previous_run"]["raw_digest"] == ORIGINAL_RUN_DIGEST
            and record["previous_append"]["raw_digest"] == ORIGINAL_APPEND_DIGEST, "literal_original_preimage_changed")
    snapshot = _root_snapshot(root)
    expected_files = {name[len(RUN_REF) + 1:]: "sha256:" + value["sha256"]
                      for name, value in snapshot["files"].items() if name.startswith(RUN_REF + "/")
                      and name[len(RUN_REF) + 1:] not in _MUTABLE}
    require(record["immutable"]["files"] == expected_files, "original_snapshot_denominator_changed")
    require(set(record["immutable"]) == {"files", "directories", "sealed_subtrees"}
            and record["immutable"]["sealed_subtrees"] == list(_SEALED), "sealed_old_namespaces_changed")
    projected = {name for name in ("model-execution.json", "candidates/candidate-2/lineage-execution.json")
                 if RUN_REF + "/" + name in snapshot["files"]}
    require(set(record["mutable_preimages"]) == projected, "old_projection_archive_missing")
    for name, archived in record["mutable_preimages"].items():
        require(codec.raw_digest(image_bytes(archived)) == "sha256:" + snapshot["files"][RUN_REF + "/" + name]["sha256"],
                "old_projection_archive_changed:" + name)
    require(same(read(path.parent, "claim.json"), {"schema_version": SCHEMA, "record_digest": reference["record_digest"],
            "retained_global_calls": 7, "retained_local_calls": 2}), "claim_changed")
    require(same(read(path.parent, "committed.json"), {"record_digest": reference["record_digest"],
            "transition_digest": record["transition"]["transition_digest"]}), "partial_preparation")
    return path, record


def _retained_admission(ledger, original):
    matches = []
    if ledger.get("current") is not None and ledger["current"].get("order_index") == 0:
        matches.append(ledger["current"])
    for step in ledger.get("selected", []):
        if step.get("input_identity", {}).get("order_index") == 0:
            matches.append(step)
    require(len(matches) == 1 and same(matches[0]["admissions"]["candidate-1"], original), "c1_admission_changed")


def validate_recovery(root, state):
    """Read-only metadata closure; never recursively calls frozen_input/runtime."""
    root = Path(root).resolve()
    _, record = _record(root, state)
    old, previous_append = (codec.strict_json_loads(image_bytes(record[key])) for key in ("previous_run", "previous_append"))
    retained_shape(old, previous_append)
    require(state["run_id"] == "m4" and same(state["b_route_execution_transition"], record["transition"])
            and same(state["b_route_execution_history"], record["history"]), "source_frame_changed")
    for field in ("runtime_identity", "planning_runtime", "mvg.run_invocation_limit", "b_route_campaign_funding",
                  "b_route_input_compact_policy", "b_route_output_schema_policy"):
        require(same(state.get(field), old.get(field)), "identity_or_budget_changed:" + field)
    ledger = state["capability_selection"]
    calls = ledger["calls"]
    require(same(calls[:7], old["capability_selection"]["calls"])
            and _integer(ledger["total_invocations"], len(calls)) and 7 <= len(calls) <= 192
            and same([row["number"] for row in calls], list(range(1, len(calls) + 1)))
            and _number(state["active_elapsed_seconds"]) and state["active_elapsed_seconds"] >= old["active_elapsed_seconds"],
            "paid_prefix_or_clock_changed")
    if len(calls) > 7:
        _check_synthesis_claim(root, state, record)
        row = calls[7]
        require(row["candidate"] == "candidate-2" and row["phase"] == "generate"
                and row["generation"] == row["execution"] == 1 and row["request_identity"]["attempt"] == 3
                and row["request_identity"]["synthesis"] is True, "first_recovery_dispatch_changed")
    require(same(ledger["lineage_invocations"], {slot: sum(row.get("candidate") == slot for row in calls)
            for slot in ("candidate-1", "candidate-2", "candidate-3")})
            and all(count <= 64 for count in ledger["lineage_invocations"].values()), "lineage_charge_changed")
    run = sources.checked_path(root, RUN_REF)
    _close_immutable(run, record)
    _root_controls(root, record["root_terminal_observation"])
    original = old["capability_selection"]["current"]["admissions"]["candidate-1"]
    if state.get("runtime_slot") is not None and ledger.get("current") is None:
        owner = read(root, RUN_REF + "/run.json")
        require(same(owner.get(REFERENCE), state.get(REFERENCE))
                and same(owner["capability_selection"]["calls"][:len(calls)], calls)
                and owner["active_elapsed_seconds"] >= state["active_elapsed_seconds"], "worker_owner_changed")
        _retained_admission(owner["capability_selection"], original)
    else:
        _retained_admission(ledger, original)
    local = read(run, WORKSPACE + "/capability-append/append-ledger.json")
    require(same(local["calls"][:2], previous_append["calls"])
            and local["total_invocations"] == len(local["calls"]) >= 2
            and local["binding"] == previous_append["binding"], "local_charge_or_seed_changed")
    return record


def call_root(state, workspace, number, slot):
    require(type(number) is int and number >= 1, "local_call_number")
    base = Path(workspace) / "capability-append"
    if _active_recovery(state) and slot == "candidate-2" and number >= 3:
        return base / NAMESPACE / ("c" + str(number))
    return base / ("c" + str(number))


def _resume_marker(record, state):
    return {"schema_version": SCHEMA + ".synthesis-claim", "record_digest": state[REFERENCE]["record_digest"],
            "old_global_calls": 7, "old_local_calls": 2, "next_local_call": 3,
            "batch_draft_digest": record["batch_draft_digest"],
            "rejected_synthesis_draft_digest": record["rejected_synthesis_draft_digest"]}


def _check_synthesis_claim(root, state, record):
    path = sources.checked_path(root, state[REFERENCE]["record_ref"]).with_name("synthesis-claim.json")
    require(same(read(path.parent, path.name), _resume_marker(record, state)), "synthesis_claim_missing_or_changed")


def _retained_generation(root, state, workspace, frozen, accepted, prior, issue, context, *, consume_claim):
    """One complete verification algorithm shared by preview and actual resume."""
    if not _active_recovery(state) or state.get("runtime_slot") != "candidate-2":
        return None
    root = Path(root).resolve()
    record = validate_recovery(root, state)
    run = sources.checked_path(root, RUN_REF)
    require(Path(workspace).resolve() == (run / WORKSPACE).resolve(), "workspace_changed")
    if prior is not None or issue is not None or context != 1:
        _later_native_proposal(root, state, record, prior, issue, context)
        return None
    owner = read(root, RUN_REF + "/run.json")
    require(same(owner.get(REFERENCE), state.get(REFERENCE))
            and owner["capability_selection"]["total_invocations"] == 7
            and same(owner["capability_selection"]["calls"], state["capability_selection"]["calls"]),
            "synthesis_already_reserved_or_owner_changed")
    local = read(run, WORKSPACE + "/capability-append/append-ledger.json")
    old_append = codec.strict_json_loads(image_bytes(record["previous_append"]))
    require(local["total_invocations"] == 2 and same(local["calls"], old_append["calls"])
            and same(local["current"], old_append["current"]) and same(accepted, old_append["accepted"]),
            "initial_proposal_or_counts_changed")
    path = sources.checked_path(root, state[REFERENCE]["record_ref"]).with_name("synthesis-claim.json")
    require(not os.path.lexists(path), "synthesis_intent_already_consumed")
    import _b_route_planning_runtime as runtime
    drafts, bindings = [], []
    for index, prefix in [(5, "batch"), (6, "rejected_synthesis")]:
        binding = runtime.verify_reserved_call(run, owner["capability_selection"]["calls"][index])
        draft = read(run, record[prefix + "_draft_ref"])
        require(codec.canonical_digest(binding) == record[prefix + "_binding_digest"]
                and codec.canonical_digest(draft) == record[prefix + "_draft_digest"]
                and same(runtime.decode_generation_carrier(runtime.verify_call(binding)), draft), "completed_draft_changed")
        material = runtime.bound_materials(binding, state, frozen)
        require(same(material["root_request"], json_request(runtime, frozen, drafts, index == 5, state))
                and same(material["accepted_seed"], accepted) and material["slot"] == "candidate-2"
                and material["prior_candidate"] is material["repair_issue"] is None
                and material["generation"] == material["execution"] == material["lineage_context"] == context == 1
                and material["lineage_identity"] == runtime.lineage_identity(state, accepted, "candidate-2", 1, 1, 1),
                "completed_draft_request_changed")
        drafts.append(draft)
        bindings.append(binding)
        runtime.planning.validate_draft_chain(frozen, drafts)
    if consume_claim:
        _durable(path, _resume_marker(record, state), exclusive=True)
    return drafts, bindings


def preview_generation(root, state, workspace, frozen, accepted, prior=None, issue=None, context=1):
    """No claim/write/dispatch; this result is not admission or model evidence."""
    require(prior is None and issue is None and _integer(context, 1), "preview_only_initial_extra_synthesis")
    return _retained_generation(root, state, workspace, frozen, accepted, prior, issue, context, consume_claim=False)


def resume_generation(root, state, workspace, frozen, accepted, prior, issue, context):
    """Retain both paid drafts, even rejected content; one new final synthesis."""
    return _retained_generation(root, state, workspace, frozen, accepted, prior, issue, context, consume_claim=True)


def _expected_recovery_materials(root, state, materials, *, check_claim):
    """One exact typed hint, never a business finding or an output correction."""
    if not _active_recovery(state):
        require(HINT_KEY not in materials, "hint_without_recovery")
        return None
    record = validate_recovery(root, state)
    prior_drafts = materials.get("root_request", {}).get("input", {}).get("prior_drafts", [])
    selected = (materials.get("phase") == "generation" and materials.get("slot") == "candidate-2"
                and all(_integer(materials.get(key), 1) for key in ("generation", "execution", "lineage_context"))
                and materials.get("prior_candidate") is None and materials.get("repair_issue") is None)
    if not selected:
        require(HINT_KEY not in materials, "hint_on_other_generation_or_review")
        return None
    require(len(prior_drafts) == 2, "initial_extra_synthesis_must_retain_both_paid_drafts")
    require([codec.canonical_digest(item["value"]) for item in prior_drafts] ==
            [record["batch_draft_digest"], record["rejected_synthesis_draft_digest"]], "hint_original_draft_chain_changed")
    require(materials["root_request"]["input"]["stage"] == "synthesis"
            and _integer(materials["root_request"]["input"]["ordinal"], 3), "hint_not_one_extra_synthesis")
    old_append = codec.strict_json_loads(image_bytes(record["previous_append"]))
    require(same(materials["accepted_seed"], old_append["accepted"]), "hint_original_seed_changed")
    if check_claim:
        _check_synthesis_claim(Path(root).resolve(), state, record)
    hint = {"schema_version": SCHEMA + ".hint", "record_digest": state[REFERENCE]["record_digest"],
            "rejected_synthesis_draft_digest": record["rejected_synthesis_draft_digest"],
            **record["schema_rejection"],
            "instruction": "The prior synthesis is retained exactly but fails the candidate schema at this pointer. "
                           "Produce one complete new synthesis with the exact original authoritative source digest. "
                           "Preserve all prior draft identities; the host does not patch your output."}
    if HINT_KEY in materials:
        require(same(materials[HINT_KEY], hint), "typed_hint_changed")
    return hint


def expected_recovery_materials(root, state, materials):
    """Actual dispatch/proof path always requires the consumed one-use claim."""
    return _expected_recovery_materials(root, state, materials, check_claim=True)


def decorate_payload(root, state, payload, *, local_number):
    """Called before materials identity/render; all unrelated payloads stay exact."""
    require(HINT_KEY not in payload, "hint_prepopulated")
    value = deepcopy(payload)
    expected = expected_recovery_materials(root, state, value)
    if expected is not None:
        require(_integer(local_number, 3), "extra_synthesis_local_call_changed")
        value[HINT_KEY] = expected
    return value


def preview_payload(root, state, payload, *, local_number=3):
    """Exact data-only preview; actual bound-material validation never uses this."""
    require(HINT_KEY not in payload, "preview_hint_prepopulated")
    value = deepcopy(payload)
    hint = _expected_recovery_materials(root, state, value, check_claim=False)
    require(hint is not None and _integer(local_number, 3), "preview_only_extra_synthesis")
    value[HINT_KEY] = hint
    return value


def _later_native_proposal(root, state, record, prior, issue, context):
    """Subsequent original business repair requires an actual valid-schema result."""
    run = sources.checked_path(root, RUN_REF)
    owner = read(root, RUN_REF + "/run.json")
    require(same(owner.get(REFERENCE), state.get(REFERENCE)), "later_owner_changed")
    local = read(run, WORKSPACE + "/capability-append/append-ledger.json")
    current = local.get("current")
    if context > 1 and prior is None and issue is None:
        require(type(current) is dict and current.get("context") == context
                and current.get("proposal") is current.get("delta") is current.get("issue") is None
                and current.get("issue_attempts") == {}, "not_native_replacement_context")
        ledger = owner["capability_selection"]
        events = ledger.get("replacement_events", [])
        for event in events:
            if (event.get("candidate") != "candidate-2" or event.get("context") != context
                    or event.get("scope_id") != current["capability_id"]
                    or type(event.get("round")) is not int or not 1 <= event["round"] <= 3
                    or type(event.get("event_number")) is not int or not 1 <= event["event_number"] <= len(events)
                    or not same(events[event["event_number"] - 1], event)
                    or ledger.get("replacement_depths", {}).get("candidate-2") != event["round"]):
                continue
            if (sum(same(row, event) for row in local.get("replacement_reservations", [])) == 1
                    and any(row.get("capability_id") == current["capability_id"]
                            and row.get("context") == context - 1 and row.get("issue_id") == event.get("issue_id")
                            and row.get("repair_attempts") == 3 for row in local.get("restarts", []))):
                return
        require(False, "original_native_replacement_reservation_missing")
    require(type(current) is dict and same(current.get("proposal"), prior) and same(current.get("issue"), issue)
            and current.get("context") == context and type(prior) is dict and type(issue) is dict,
            "not_native_business_repair")
    import _b_route_planning_runtime as runtime
    frozen = runtime.frozen_input(root, state)
    runtime.candidate.check_identity(prior, frozen)  # A repeated schema failure never becomes a business repair.
    rows = [row for row in owner["capability_selection"]["calls"][7:]
            if row.get("candidate") == "candidate-2" and row["request_identity"].get("synthesis") is True
            and row.get("outcome", {}).get("status") == "completed"]
    require(bool(rows), "new_completed_synthesis_missing")
    for row in reversed(rows):
        binding = runtime.verify_reserved_call(run, row)
        materials = runtime.bound_materials(binding, owner, frozen)
        draft = runtime.decode_generation_output(frozen, materials, runtime.verify_call(binding))
        drafts = [item["value"] for item in materials["root_request"]["input"]["prior_drafts"]] + [draft]
        if same(_candidate(runtime, frozen, drafts), prior):
            require(materials["lineage_context"] == context and same(materials["accepted_seed"], local["accepted"]),
                    "later_proposal_lineage_changed")
            return
    require(False, "later_proposal_not_actual_completed_synthesis")


def path_preflight(root):
    """Conservative Windows legacy path bound; does not access the filesystem."""
    run = Path(root).resolve() / RUN_REF
    base = run / WORKSPACE
    # Windows DWORD PID: at most 10 decimal digits. Allow a full unsigned
    # 64-bit thread identifier (20 digits), more than the observed runtime.
    suffix = "." + "9" * 10 + "." + "9" * 20 + "." + "f" * 32 + ".tmp"
    leaves = [base / "capability-append/m1/c64/llm-sandbox/attempt-64/r/runner-input-integrity.json",
              base / "capability-append/m1/c64/llm-sandbox/attempt-64/r/output-schema.json",
              base / "capability-append/m1/c64/execution-binding-64-r.json",
              base / "lifecycle-m1/job.json", base / "lifecycle-m1/mailbox/response-999999.json",
              base / "capability-append/stage-costs/m1/64-generate.json",
              run / "recovery/m1/synthesis-claim.json", run / "recovery/m1/committed.json"]
    report = {str(path): len(str(path) + suffix) for path in leaves}
    # Runner protocol/stderr names are longer than r.json but shorter than the
    # integrity basename plus the same conservative 69-character writer suffix.
    require(max(report.values()) <= 259, "legacy_atomic_path_over_259")
    return {"maximum_atomic_path_chars": max(report.values()), "limit": 259, "paths": report}


def prepare(root, run_dir, *, original_source_root, current_commit, prior_source_root, prior_commit,
            expected_run_digest, expected_append_digest, root_terminal_observation):
    """Explicit CAS preparation, never a run restart or direct model invocation."""
    import _b_route_execution_transition as transition
    from _mvg_capability_checkpoint import coordinator_lock
    root, run = Path(root).resolve(), Path(run_dir).resolve()
    require(run == sources.checked_path(root, RUN_REF) and prior_commit == PRIOR_COMMIT, "explicit_original_m4")
    require(expected_run_digest == ORIGINAL_RUN_DIGEST and expected_append_digest == ORIGINAL_APPEND_DIGEST,
            "root_literal_snapshot_required")
    path_preflight(root)
    home = run / "recovery" / NAMESPACE
    with coordinator_lock(run), transition._verification_transaction():
        require(not os.path.lexists(home), "recovery_namespace_occupied")
        raw_run = codec.read_reference_bytes(run, "run.json")
        raw_append = codec.read_reference_bytes(run, WORKSPACE + "/capability-append/append-ledger.json")
        require(codec.raw_digest(raw_run) == expected_run_digest and codec.raw_digest(raw_append) == expected_append_digest,
                "expected_snapshot_changed")
        old, append = codec.strict_json_loads(raw_run), codec.strict_json_loads(raw_append)
        retained_shape(old, append)
        require(not old.get(REFERENCE), "already_recovered")
        observation = _root_controls(root, root_terminal_observation)
        before = _snapshot(run)
        frozen, drafts, bindings, rejection = _verify_original(root, run, old, append)
        new_transition = transition.build_mvg_synthesis_transition(root, old, original_source_root, current_commit,
                                                                 prior_source_root, prior_commit)
        history = {**old.get("b_route_execution_history", {}),
                   old["b_route_execution_transition"]["transition_digest"]: deepcopy(old["b_route_execution_transition"])}
        require(_snapshot(run) == before and codec.read_reference_bytes(run, "run.json") == raw_run
                and codec.read_reference_bytes(run, WORKSPACE + "/capability-append/append-ledger.json") == raw_append,
                "original_changed_during_verification")
        _root_controls(root, observation)
        record = {"schema_version": SCHEMA, "run_id": "m4", "run_ref": RUN_REF,
                  "previous_run": image(raw_run), "previous_append": image(raw_append),
                  "mutable_preimages": {name: image(codec.read_reference_bytes(run, name))
                      for name in ("model-execution.json", "candidates/candidate-2/lineage-execution.json")
                      if name in before["files"]},
                  "immutable": _immutable_snapshot(before), "transition": new_transition, "history": history,
                  "root_terminal_observation": observation, "prior_commit": PRIOR_COMMIT,
                  "batch_draft_ref": WORKSPACE + "/capability-append/c1/canonical-draft.json",
                  "batch_draft_digest": codec.canonical_digest(drafts[0]),
                  "batch_binding_digest": codec.canonical_digest(bindings[0]),
                  "rejected_synthesis_draft_ref": WORKSPACE + "/capability-append/c2/canonical-draft.json",
                  "rejected_synthesis_draft_digest": codec.canonical_digest(drafts[1]),
                  "rejected_synthesis_binding_digest": codec.canonical_digest(bindings[1]),
                  "schema_rejection": rejection,
                  "retained_global_calls": 7, "retained_local_calls": 2, "next_global_call": 8,
                  "next_local_call": 3, "maximum_new_synthesis_attempts": 1, "released": 0}
    # Fresh witness ran at transaction exit. Re-lock and recheck raw CAS before any publication.
    with coordinator_lock(run):
        require(not os.path.lexists(home) and _snapshot(run) == before, "preparation_closing_changed")
        _root_controls(root, observation)
        home.mkdir(parents=True, exist_ok=False)
        import json
        record_raw = (json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        digest = codec.raw_digest(record_raw)
        _durable(home / "claim.json", {"schema_version": SCHEMA, "record_digest": digest,
                 "retained_global_calls": 7, "retained_local_calls": 2}, exclusive=True)
        _durable(home / "record.json", record, exclusive=True)
        reference = {"schema_version": SCHEMA, "record_ref": (home / "record.json").relative_to(root).as_posix(),
                     "record_digest": digest, "artifact_root": str(root)}
        next_state = deepcopy(old)
        next_state.update(b_route_execution_transition=new_transition, b_route_execution_history=history,
                          phase="mvg-synthesis-recovery-prepared", selection_status="pending")
        next_state[REFERENCE] = reference
        next_state.pop("selection_block_reason", None)
        next_state["capability_selection"]["terminal"] = False
        next_state["capability_selection"]["current"]["admissions"]["candidate-2"]["retryable"] = True
        next_append = deepcopy(append)
        next_append.setdefault("execution_errors", []).append({"stage": "generate", "invocations": 2,
                      "original_errors": deepcopy(append["errors"]), "recovery": reference})
        next_append.update(status="generating", errors=[])
        require(codec.read_reference_bytes(run, "run.json") == raw_run
                and codec.read_reference_bytes(run, WORKSPACE + "/capability-append/append-ledger.json") == raw_append,
                "raw_cas_changed")
        _durable(run / WORKSPACE / "capability-append/append-ledger.json", next_append)
        _durable(run / "run.json", next_state)
        _durable(home / "committed.json", {"record_digest": digest,
                 "transition_digest": new_transition["transition_digest"]}, exclusive=True)
    return {"status": "mvg-synthesis-recovery-prepared", "record": reference, "model_calls": 0,
            "retained_logical_calls": 7, "next_dispatch": "m4:dispatch:8", "released": 0}
