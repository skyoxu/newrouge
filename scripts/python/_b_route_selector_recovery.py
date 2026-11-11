"""One selector-only continuation of twelve completed, admitted m4 calls.

Original native proof was actually captured by the fixed original R19 helper.
Only its Root-pinned, held-handle OS0 result can create a retained capture here.
Metadata closing never invents admission, clears an unknown call or starts a model.
"""
from copy import deepcopy
from contextlib import contextmanager
from contextvars import ContextVar
import base64
import json
import math
import os
from pathlib import Path
import re
import stat
import uuid

import _b_route_codec as codec
import _b_route_sources as sources

SCHEMA = "newrouge.b-route-selector-recovery.v1"
REFERENCE = "b_route_selector_recovery"
SELECTOR_EPOCH_SCHEMA = "newrouge.b-route-selector-source-epoch.v1"
CAPTURE_SCHEMA = "newrouge.b-route-selector-retained-capture.v1"
NAMESPACE = "s1"
RUN_REF = "logs/ci/mvg-planning/m4"
PRIOR_COMMIT = "1d126b85b908ba1eea4b27ceeb8a9669a771e6f3"
ORIGINAL_RUN_DIGEST = "sha256:351fe198ae4a9d049fd79d673f7a3f08f81af4d8ab1a6e4e93e3cf3bf15d7227"
HELPER_REF = "capture_story25_selector_retained_v18b.py"
HELPER_DIGEST = "sha256:3008a98c48e041f1e081f553a7cecc78a14163020aaa659cdb04cbb1334cbf04"
CAPTURE_HOME = "logs/ci/2026-11-07/story25-selector-original-capture-02"
# Sealed only after the real original capture reaches its natural terminal.
ANCHOR_DIGEST = "sha256:0a587887dddff98397b5d727042391b75aeead446033c6cfbefbbc77ba0816e1"
CAPTURE_EXIT_DIGEST = "sha256:42f486b504aed1968fe9baa3bcda654402353704258c5643f0c4d4f8d37d0232"
_SEAL = object()
_PROJECTIONS = frozenset({RUN_REF + "/run.json", RUN_REF + "/model-execution.json"})
_POLICY = "newrouge.b-route-compact-literal.v3"
TRANSACTION_SCHEMA = "newrouge.b-route-selector-metadata-transaction.v1"
_TRANSACTIONS = ("prepare", "reservation", "unknown")
_PUBLICATION_MATERIALS = ContextVar("selector_publication_materials", default=None)
_CAPTURE_FIELDS = {"schema_version", "utc", "artifact_root", "source", "run_ref", "original_run_raw_digest",
                   "original_state", "manifest", "runtime_binding", "selection", "admissions", "budget",
                   "terminal_controls", "helper_sha256", "original_m1_ref", "scope", "actual_model_dispatches"}


def require(value, reason):
    if not value:
        raise ValueError("b_route_selector_recovery:" + reason)


def same(left, right):
    return codec.canonical_digest(left) == codec.canonical_digest(right)


def _closed_publication_images(value):
    require(value is None or type(value) is dict and set(value) <= set(_TRANSACTIONS)
            and all(type(raw) is bytes for raw in value.values()), "closed_original_publication_images")
    return tuple(sorted((value or {}).items()))


@contextmanager
def _publication_material_scope(root, images):
    """Carry raw input only; no verification result, witness or cache is shared."""
    material = _closed_publication_images(images)
    require(_PUBLICATION_MATERIALS.get() is None, "publication_material_action_already_active")
    token = _PUBLICATION_MATERIALS.set((Path(root).resolve(), material))
    try:
        yield
    finally:
        _PUBLICATION_MATERIALS.reset(token)


def _images_for_action(root, supplied):
    material = _closed_publication_images(supplied)
    active = _PUBLICATION_MATERIALS.get()
    if active is None:
        return dict(material) if supplied is not None else None
    require(active[0] == Path(root).resolve(), "publication_material_root_changed")
    require(supplied is None or material == active[1], "publication_material_action_changed")
    return dict(active[1])


def _integer(value, expected):
    return type(value) is int and value == expected


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def read(root, reference):
    return codec.strict_json_loads(codec.read_reference_bytes(root, reference))


def is_selector_recovery(state):
    epoch = state.get("b_route_execution_transition") or {}
    reference = state.get(REFERENCE)
    if epoch.get("schema_version") == SELECTOR_EPOCH_SCHEMA:
        require(type(reference) is dict and bool(reference), "typed_epoch_requires_reference")
    if reference:
        require(type(reference) is dict, "reference_not_object")
        return True
    return False


def image(raw):
    return {"raw_digest": codec.raw_digest(raw), "bytes_base64": base64.b64encode(raw).decode("ascii")}


def image_bytes(value):
    require(type(value) is dict and set(value) == {"raw_digest", "bytes_base64"}, "image_shape")
    raw = base64.b64decode(value["bytes_base64"], validate=True)
    require(codec.raw_digest(raw) == value["raw_digest"], "image_changed")
    return raw


def retained_shape(state):
    """Closed twelve-call metadata only; actual admission came from the capture."""
    ledger, current = state["capability_selection"], state["capability_selection"]["current"]
    desc = state["planning_runtime"]
    require(state["run_id"] == "m4" and state["input_stage"] == "3b"
            and desc["planner"] == "mvg" and desc["profile"] == "3b-mvg-v1"
            and same(desc["limits"], {"request_limit": 192}) and _integer(state["mvg.run_invocation_limit"], 192),
            "original_mvg_profile")
    expected = [("candidate-1", "generate", 1, False), ("candidate-1", "generate", 2, True),
                ("candidate-1", "repair", 3, False), ("candidate-1", "repair", 4, True),
                ("candidate-1", "semantic", 5, False), ("candidate-2", "generate", 1, False),
                ("candidate-2", "generate", 2, True), ("candidate-2", "generate", 3, True),
                ("candidate-2", "semantic", 4, False), ("candidate-3", "generate", 1, False),
                ("candidate-3", "generate", 2, True), ("candidate-3", "semantic", 3, False)]
    calls = ledger["calls"]
    require(_integer(ledger["total_invocations"], 12) and len(calls) == 12
            and same(ledger["lineage_invocations"], {"candidate-1": 5, "candidate-2": 4, "candidate-3": 3}),
            "original_paid_twelve")
    for number, (row, item) in enumerate(zip(calls, expected), 1):
        request = row["request_identity"]
        require(_integer(row["number"], number) and row["reservation_id"] == f"m4:dispatch:{number}"
                and same([row["candidate"], row["phase"], request["attempt"], request.get("synthesis", False)], list(item))
                and _integer(row["generation"], 1) and _integer(row["execution"], 1)
                and row["outcome"]["status"] == "completed", "original_completed_row")
    require(ledger["terminal"] is True and ledger["selected"] == []
            and state["phase"] == "selection-blocked" and state["selection_status"] == "blocked"
            and _integer(current["order_index"], 0) and _integer(current["execution"], 1)
            and current["stage"] == "selection-preparing" and current["selection_attempts"] == [], "known_unreserved_selector")
    detail = ("runner_context_budget_exceeded:estimated_input_tokens=114776;continuation_reserve=0;limit=96000;"
              "complete_request_chars=392053;complete_request_bytes=392053;token_counter=max(o200k_base,cl100k_base)+10_percent")
    require(state["selection_block_reason"] == detail and current["preparation_error"] == {
            "code": "selection_preparation_failed", "error_type": "runner_execution_failed", "detail": detail},
            "original_capacity_error")
    require(current["aliases"] == {"A": "candidate-2", "B": "candidate-3", "C": "candidate-1"}
            and set(current["admissions"]) == {"candidate-1", "candidate-2", "candidate-3"}, "original_alias_domain")
    for slot, count in (("candidate-1", 5), ("candidate-2", 4), ("candidate-3", 3)):
        admission = current["admissions"][slot]
        require(admission["status"] == "admitted" and _integer(admission["total_invocations"], count)
                and admission["retryable"] is False and admission["append_terminal"] is False, "original_admission_shape")
    require(same(state["b_route_campaign_funding"], {"schema_version": "newrouge.story25-native-funding.v1",
                "paid_or_unknown_before_run": 66, "campaign_limit": 290, "subsequent_full_reservation": 0,
                "maximum_native_charges": 224, "released": 0}) and _number(state["active_elapsed_seconds"]), "funding_or_clock")


class _RetainedSelectorCapture:
    __slots__ = ("_seal", "_root", "_anchor", "_identity")

    def __init__(self, seal, root, anchor, identity):
        require(seal is _SEAL, "factory_only_capture")
        self._seal, self._root = seal, root
        self._anchor, self._identity = anchor, identity

    def __getitem__(self, key):
        require(key == "anchor_identity" and self._seal is _SEAL, "closed_capture_key")
        return deepcopy(self._identity)


def _trusted_anchor(root):
    require(type(ANCHOR_DIGEST) is str and type(CAPTURE_EXIT_DIGEST) is str, "capture_not_naturally_sealed")
    task = root.parent
    helper = codec.read_reference_bytes(task, HELPER_REF)
    raw = codec.read_reference_bytes(task, CAPTURE_HOME + "/anchor.json")
    receipt_raw = codec.read_reference_bytes(task, CAPTURE_HOME + "/exit.json")
    require(codec.raw_digest(helper) == HELPER_DIGEST and codec.raw_digest(raw) == ANCHOR_DIGEST
            and codec.raw_digest(receipt_raw) == CAPTURE_EXIT_DIGEST, "trusted_capture_controls_changed")
    receipt, anchor = codec.strict_json_loads(receipt_raw), codec.strict_json_loads(raw)
    require(_integer(receipt["os_exit_code"], 0) and receipt["exit_source"] == "held_subprocess_handle_wait"
            and receipt["source_pins_unchanged"] is True and receipt["anchor_sha256"] == ANCHOR_DIGEST,
            "actual_original_capture_os0_required")
    for reference, digest in receipt["source_pins"].items():
        path = Path(reference)
        require(path.is_absolute() and path.is_relative_to(task), "capture_source_escape")
        require(codec.raw_digest(codec.read_reference_bytes(path.parent, path.name)) == "sha256:" + digest,
                "capture_source_changed")
    for name in ("stdout", "stderr"):
        require(codec.raw_digest(codec.read_reference_bytes(task, CAPTURE_HOME + "/" + name + ".txt")) ==
                "sha256:" + receipt[name + "_sha256"], "capture_output_changed")
    require(set(anchor) == _CAPTURE_FIELDS and anchor["schema_version"] == CAPTURE_SCHEMA
            and Path(anchor["artifact_root"]).resolve() == root and anchor["run_ref"] == RUN_REF
            and anchor["original_run_raw_digest"] == ORIGINAL_RUN_DIGEST
            and anchor["source"]["commit"] == PRIOR_COMMIT
            and Path(anchor["source"]["root"]).resolve() == task / "r19"
            and anchor["helper_sha256"] == HELPER_DIGEST and _integer(anchor["actual_model_dispatches"], 0),
            "trusted_capture_identity")
    retained_shape(anchor["original_state"])
    require(same(anchor["original_m1_ref"], anchor["original_state"]["b_route_mvg_synthesis_recovery"])
            and set(anchor["admissions"]) == {"candidate-1", "candidate-2", "candidate-3"}, "original_capture_domains")
    require(len(anchor["selection"]["scopes"]) == 1 and anchor["selection"]["records"] == [], "single_retained_scope")
    return anchor


def _anchor_identity():
    return {"schema_version": "newrouge.b-route-selector-anchor-identity.v1", "anchor_raw_digest": ANCHOR_DIGEST,
                "helper_raw_digest": HELPER_DIGEST, "supervisor_exit_raw_digest": CAPTURE_EXIT_DIGEST,
                "original_run_raw_digest": ORIGINAL_RUN_DIGEST}


def capture_retained_selector(root):
    """Load only the actual Root-pinned original validation, never caller proof."""
    root = Path(root).resolve()
    anchor = _trusted_anchor(root)
    return _RetainedSelectorCapture(_SEAL, root, anchor, _anchor_identity())


def _original_admissions(state):
    ledger = state["capability_selection"]
    matches = []
    current = ledger.get("current")
    if current is not None and _integer(current.get("order_index"), 0):
        matches.append(current)
    for step in ledger.get("selected", []):
        if _integer(step.get("input_identity", {}).get("order_index"), 0):
            matches.append(step)
    require(len(matches) == 1 and len(ledger.get("selected", [])) <= 1, "original_scope_position")
    return matches[0]


def _current_projection(anchor, state):
    original = anchor["original_state"]
    ledger, before = state["capability_selection"], original["capability_selection"]
    calls = ledger["calls"]
    require(_integer(ledger["total_invocations"], len(calls)) and 12 <= len(calls) <= 13
            and same(calls[:12], before["calls"]) and same(ledger["lineage_invocations"], before["lineage_invocations"]),
            "paid_prefix_or_lineage_changed")
    require(_integer(ledger.get("generation", 1), 1), "generation_changed")
    for key in ("binding", "order", "replacement_events", "replacement_depths", "replacement_round", "reopen_history"):
        require(same(ledger.get(key), before.get(key)), "selector_cannot_change_candidate_history:" + key)
    for key in ("run_id", "runtime_identity", "planning_runtime", "input_stage", "analysis_identity_sha256",
                "mvg.run_invocation_limit", "mvg.run_invocation_limit_source", "b_route_campaign_funding",
                "runner_configuration", "recovery", "b_route_mvg_synthesis_recovery", "b_route_output_schema_policy",
                "b_route_input_compact_policy", "checkpoint_strategy", "checkpoint_schema_version"):
        require(same(state.get(key), original.get(key)), "retained_identity_changed:" + key)
    require(_number(state["active_elapsed_seconds"])
            and state["active_elapsed_seconds"] >= original["active_elapsed_seconds"], "clock_refunded")
    view = _original_admissions(state)
    require(_integer(view.get("execution", 1), 1), "execution_changed")
    for key in ("admissions", "aliases", "input_identity", "input_sha256"):
        require(same(view[key], before["current"][key]), "admitted_selector_input_changed:" + key)
    if len(calls) == 13:
        row = calls[12]
        require(_integer(row["number"], 13) and row["reservation_id"] == "m4:dispatch:13"
                and row["phase"] == "selection" and row.get("candidate") is None
                and _integer(row["generation"], 1) and _integer(row["execution"], 1)
                and _integer(row["request_identity"]["attempt"], 1)
                and row["request_identity"].get("selector_transport_policy") == _POLICY
                and row["request_identity"].get("selection_input_sha256") == anchor["selection"]["input_sha256"],
                "only_one_original_selector_dispatch")
    return view


def _close_sources(root, anchor):
    require(codec.raw_digest(codec.read_reference_bytes(root.parent, "continue_story25_mvg_synthesis_recovery_v17.py")) ==
            anchor["source"]["verifier_bridge_sha256"], "original_verifier_bridge_changed")
    source_hashes = anchor["source"]["source_hashes"]
    for reference, value in source_hashes["sources"].items():
        source = Path(reference)
        require(source.is_absolute() and source.is_relative_to(root.parent), "original_source_escape")
        for name, expected in value["manifest"].items():
            require(codec.raw_digest(codec.read_reference_bytes(source, name)) == expected["raw_digest"],
                    "original_source_changed:" + name)
    home = root / "logs/ci/v17"
    for name, digest in anchor["terminal_controls"].items():
        require(codec.raw_digest(codec.read_reference_bytes(home, name)) == digest, "original_terminal_control_changed")


def _new_paths(state, anchor):
    """Finite native write domain, not a wildcard exclusion of the new run."""
    workspace = RUN_REF + "/s1/attempt-1"
    top = {"A.json", "B.json", "C.json", "accepted-seed.json", "comparison-seed.json", "comparison-context.json",
           "comparison-A.json", "comparison-B.json", "comparison-C.json", "output-schema.json", "stage-cost.json",
           "selection-receipt.json", "execution-binding-1-selection.json", "host-execution-1-selection.json"}
    files = {workspace + "/" + name for name in top}
    sandbox = workspace + "/llm-sandbox/attempt-1/selection"
    files.update(sandbox + "/" + name for name in ("prompt-1-selection.txt", "output-schema.json", "selection.json", "runner-input-integrity.json"))
    source_prefix = RUN_REF + "/analysis-input/"
    files.update(workspace + "/analysis-input/" + name[len(source_prefix):]
                 for name in anchor["manifest"]["files"] if name.startswith(source_prefix))
    files.update(RUN_REF + "/recovery/s1/" + name for name in ("claim.json", "record.json", "committed.json", "intent.json", "receipt.json", "failure.json"))
    if len(state["capability_selection"]["calls"]) == 13:
        files.add(RUN_REF + "/dispatch-receipts/dispatch-13.json")
    ledger = state["capability_selection"]
    pointers = [ledger.get("checkpoint_head")]
    view = ledger.get("current") or {}
    pointers.append((view.get("checkpoint_preparation") or {}).get("pointer"))
    pointers.extend(step.get("checkpoint") for step in ledger.get("selected", []))
    for pointer in pointers:
        if pointer is not None:
            identity = pointer.get("transaction_id", "")
            require(re.fullmatch(r"sha256:[0-9a-f]{64}", identity) is not None
                    and pointer.get("path") == "capability-checkpoints/" + identity[7:] + "/payload.json", "native_checkpoint_path")
            files.add(RUN_REF + "/" + pointer["path"])
    if len(ledger["calls"]) == 13:
        files.add(RUN_REF + "/checkpoint-commit-outcome.json")
    if ledger.get("selected"):
        files.update(RUN_REF + "/accepted-chain/" + name for name in ("proposal.json", "admission-review.json", "admission-execution.json"))
        files.update((RUN_REF + "/proposal.json", RUN_REF + "/handoff.json"))
    directories = {RUN_REF + "/s1", workspace, workspace + "/analysis-input", sandbox,
                   workspace + "/llm-sandbox", workspace + "/llm-sandbox/attempt-1", RUN_REF + "/recovery/s1"}
    for name in files:
        parent = Path(name).parent
        while parent.as_posix().startswith(RUN_REF + "/"):
            directories.add(parent.as_posix())
            parent = parent.parent
    directories.update(workspace + "/analysis-input/" + name[len(source_prefix):]
                       for name in anchor["manifest"]["directories"] if name.startswith(source_prefix))
    return files, directories, sandbox


def _old_files_close(root, anchor, state, *, publication_images=None):
    publication_images = _images_for_action(root, publication_images)
    for reference, digest in anchor["manifest"]["files"].items():
        if reference in _PROJECTIONS:
            continue
        require(codec.raw_digest(codec.read_reference_bytes(root, reference)) == digest, "retained_file_changed:" + reference)
    for reference in anchor["manifest"]["directories"]:
        path = sources.checked_path(root, reference)
        info = path.lstat()
        require(stat.S_ISDIR(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                "retained_directory_changed")
    # Every old candidate/failed-selector subtree is sealed, including membership.
    sealed = [RUN_REF + "/candidates", RUN_REF + "/analysis-input", RUN_REF + "/capability-selection",
              RUN_REF + "/recovery/m1"]
    for prefix in sealed:
        path = sources.checked_path(root, prefix)
        actual_files, actual_dirs = set(), set()
        for item in path.rglob("*"):
            info = item.lstat()
            reference = item.relative_to(root).as_posix()
            require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                    "retained_reparse")
            if stat.S_ISDIR(info.st_mode):
                actual_dirs.add(reference)
            else:
                require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "retained_special_or_link")
                actual_files.add(reference)
        expected_files = {name for name in anchor["manifest"]["files"] if name.startswith(prefix + "/")}
        expected_dirs = {name for name in anchor["manifest"]["directories"] if name.startswith(prefix + "/")}
        require(actual_files == expected_files and actual_dirs == expected_dirs, "sealed_retained_membership_changed")
    allowed_files, allowed_dirs, sandbox = _new_paths(state, anchor)
    allowed_files.update(_journal_artifacts(root, anchor, publication_images=publication_images))
    before_files, before_dirs = anchor["manifest"]["files"], set(anchor["manifest"]["directories"])
    for path in (root / RUN_REF).rglob("*"):
        relative = path.relative_to(root).as_posix()
        info = path.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400, "new_namespace_reparse")
        if stat.S_ISDIR(info.st_mode):
            require(relative in before_dirs or relative in allowed_dirs, "unknown_new_directory:" + relative)
        else:
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "new_namespace_special_file")
            if relative == RUN_REF + "/capability-coordinator.lock":
                require(info.st_size == 1, "native_mutex_shape")
                continue
            protocol = (relative.startswith(sandbox + "/") and re.fullmatch(
                r"selection\.json\.[0-9a-f]{32}\.app-server\.(jsonl|stderr\.txt)", path.name) is not None)
            require(relative in before_files or relative in allowed_files or protocol, "unknown_new_file:" + relative)


def verify_retained_selector_capture(root, capture, *, current_state):
    """No runtime/transition/native recursion: actual raw/current/source close."""
    root = Path(root).resolve()
    require(type(capture) is _RetainedSelectorCapture and capture._seal is _SEAL and capture._root == root,
            "factory_capture_required")
    require(same(capture._identity, _anchor_identity()), "sealed_capture_identity_changed")
    anchor = _trusted_anchor(root)
    require(same(anchor, capture._anchor), "capture_instance_changed")
    if current_state["b_route_execution_transition"]["schema_version"] == SELECTOR_EPOCH_SCHEMA:
        require(is_selector_recovery(current_state), "selector_reference_required")
    else:
        require(codec.raw_digest(codec.read_reference_bytes(root, RUN_REF + "/run.json")) == ORIGINAL_RUN_DIGEST
                and same(current_state, anchor["original_state"]), "original_live_r19_state_required")
    _current_projection(anchor, current_state)
    _old_files_close(root, anchor, current_state)
    _close_sources(root, anchor)
    return deepcopy(anchor["original_state"])


def selector_workspace(root, state, index, attempt):
    require(is_selector_recovery(state) and _integer(index, 0) and _integer(attempt, 1), "single_selector_workspace")
    return sources.checked_path(Path(root).resolve(), RUN_REF) / "s1/attempt-1"


def selector_transport_policy(root, state):
    require(is_selector_recovery(state), "selector_policy_requires_reference")
    record = validate_recovery(root, state)
    require(record["selector_transport_policy"] == _POLICY, "selector_policy_changed")
    return _POLICY


def _record(root, state):
    reference = state.get(REFERENCE)
    require(type(reference) is dict and set(reference) == {"schema_version", "record_ref", "record_digest", "artifact_root"}
            and reference["schema_version"] == SCHEMA and reference["record_ref"] == RUN_REF + "/recovery/s1/record.json"
            and Path(reference["artifact_root"]).resolve() == root, "closed_reference")
    raw = codec.read_reference_bytes(root, reference["record_ref"])
    require(codec.raw_digest(raw) == reference["record_digest"], "record_digest_changed")
    record = codec.strict_json_loads(raw)
    fields = {"schema_version", "run_id", "run_ref", "anchor_identity", "previous_run", "model_execution_preimage",
              "transition", "history", "selector_transport_policy", "retained_calls", "maximum_selector_dispatches", "released"}
    require(set(record) == fields and record["schema_version"] == SCHEMA and record["run_id"] == "m4"
            and record["run_ref"] == RUN_REF and _integer(record["retained_calls"], 12)
            and _integer(record["maximum_selector_dispatches"], 1) and _integer(record["released"], 0)
            and record["selector_transport_policy"] == _POLICY, "closed_record")
    require(record["previous_run"]["raw_digest"] == ORIGINAL_RUN_DIGEST, "original_raw_preimage_changed")
    path = sources.checked_path(root, reference["record_ref"]).parent
    require(same(read(path, "claim.json"), {"schema_version": SCHEMA, "record_digest": reference["record_digest"],
                                          "retained_calls": 12, "maximum_selector_dispatches": 1}), "prepare_claim_changed")
    marker = read(path, "committed.json")
    require(set(marker) == {"record_digest", "transition_digest", "prepared_run_digest"}
            and marker["record_digest"] == reference["record_digest"]
            and marker["transition_digest"] == record["transition"]["transition_digest"], "partial_preparation")
    initial = _prepared_state(codec.strict_json_loads(image_bytes(record["previous_run"])), record, reference)
    initial_raw = (json.dumps(initial, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    require(marker["prepared_run_digest"] == codec.raw_digest(initial_raw), "prepared_target_digest_changed")
    return record


def validate_recovery(root, state):
    root = Path(root).resolve()
    require(is_selector_recovery(state), "selector_reference_required")
    record = _record(root, state)
    capture = capture_retained_selector(root)
    require(same(record["anchor_identity"], capture["anchor_identity"])
            and same(state["b_route_execution_transition"], record["transition"])
            and same(state["b_route_execution_history"], record["history"]), "source_frame_changed")
    original = verify_retained_selector_capture(root, capture, current_state=state)
    require(same(codec.strict_json_loads(image_bytes(record["previous_run"])), original), "archived_r19_frame_changed")
    model_ref = RUN_REF + "/model-execution.json"
    require(record["model_execution_preimage"]["raw_digest"] == capture._anchor["manifest"]["files"][model_ref],
            "original_model_projection_changed")
    image_bytes(record["model_execution_preimage"])
    import _b_route_mvg_synthesis_recovery as previous
    previous.validate_recovery(root, original)  # Genuine R19 frame, never new epoch masquerading as old.
    if len(state["capability_selection"]["calls"]) == 13:
        intent_path = sources.checked_path(root, state[REFERENCE]["record_ref"]).with_name("intent.json")
        expected_intent = {"schema_version": SCHEMA + ".selector-intent", "record_digest": state[REFERENCE]["record_digest"],
                           "anchor_identity": record["anchor_identity"], "retained_calls": 12,
                           "request_identity": state["capability_selection"]["calls"][12]["request_identity"], "next_global_call": 13}
        require(same(read(intent_path.parent, intent_path.name), expected_intent), "selector_intent_changed_or_missing")
    return record


def retained_candidate_artifacts(root, run_dir, state, scopes, index, accepted, prefix, admission, *, check_originals=True):
    require(type(check_originals) is bool and is_selector_recovery(state), "retained_originals_only")
    root, run_dir = Path(root).resolve(), Path(run_dir).resolve()
    require(run_dir == sources.checked_path(root, RUN_REF), "retained_run_changed")
    validate_recovery(root, state)
    # Current frozen qualification is a real current input/source/3A check; it
    # does not replace or re-sign the actual original three-admission capture.
    import _b_route_planning_runtime as runtime
    runtime.frozen_input(root, state)
    capture = capture_retained_selector(root)
    anchor = capture._anchor
    require(_integer(index, 0) and same(scopes, anchor["selection"]["scopes"])
            and same(accepted, anchor["selection"]["accepted_seed"])
            and same(prefix, anchor["selection"]["records"]), "retained_scope_or_prefix_changed")
    slot = admission.get("candidate")
    require(slot in anchor["admissions"] and same(admission, anchor["admissions"][slot]["admission"]), "retained_admission_changed")
    values = []
    for key in ("proposal", "proof", "execution"):
        reference = RUN_REF + "/" + admission[key + "_path"]
        raw = codec.read_reference_bytes(root, reference)
        require(codec.raw_digest(raw) == anchor["manifest"]["files"][reference], "retained_artifact_raw_changed")
        value = codec.strict_json_loads(raw)
        require(codec.canonical_digest(value) == anchor["admissions"][slot]["canonical_digests"][key], "retained_artifact_content_changed")
        values.append(value)
    verify_retained_selector_capture(root, capture, current_state=state)
    return tuple(values)


def _durable(path, value, *, exclusive=False):
    raw = (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if exclusive:
        _publish_transaction(path, value, raw)
        return raw
    target = path if exclusive else path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with target.open("xb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    if not exclusive:
        os.replace(target, path)
    return raw


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _transaction_operations(kind, record, before, after, row=None):
    home = RUN_REF + "/recovery/s1/"
    if kind == "prepare":
        raw = _json_bytes(record)
        digest = codec.raw_digest(raw)
        return [(home + "claim.json", None, _json_bytes({"schema_version": SCHEMA, "record_digest": digest,
                    "retained_calls": 12, "maximum_selector_dispatches": 1})),
                (home + "record.json", None, raw),
                (RUN_REF + "/run.json", before, after),
                (home + "committed.json", None, _json_bytes({"record_digest": digest,
                    "transition_digest": record["transition"]["transition_digest"],
                    "prepared_run_digest": codec.raw_digest(after)}))]
    if kind == "reservation":
        reference = codec.strict_json_loads(before)[REFERENCE]
        intent = {"schema_version": SCHEMA + ".selector-intent", "record_digest": reference["record_digest"],
                  "anchor_identity": record["anchor_identity"], "retained_calls": 12,
                  "request_identity": row["request_identity"], "next_global_call": 13}
        return [(home + "intent.json", None, _json_bytes(intent)), (RUN_REF + "/run.json", before, after),
                (home + "reservation-committed.json", None, _json_bytes({"parent_run_digest": codec.raw_digest(after),
                    "reservation_id": row["reservation_id"], "record_digest": reference["record_digest"]}))]
    return [(RUN_REF + "/run.json", before, after),
            (home + "unknown-committed.json", None, _json_bytes({"parent_run_digest": codec.raw_digest(after), "released": 0}))]


def _transaction_value(kind, record, before, after, row=None):
    body = {"schema_version": TRANSACTION_SCHEMA, "kind": kind, "nonce": uuid.uuid4().hex,
            "anchor_identity": record["anchor_identity"], "record": deepcopy(record),
            "before": image(before), "after": image(after), "row": deepcopy(row)}
    body["transaction_digest"] = codec.canonical_digest(body)
    return body


def _validate_transaction(root, kind, anchor, value):
    """Reconstruct exact operations; a self-reported digest is never authority."""
    home = RUN_REF + "/recovery/s1/"
    require(type(value) is dict, "transaction_object_required")
    fields = {"schema_version", "kind", "nonce", "anchor_identity", "record", "before", "after", "row", "transaction_digest"}
    require(set(value) == fields and value["schema_version"] == TRANSACTION_SCHEMA and value["kind"] == kind
            and re.fullmatch("[0-9a-f]{32}", value["nonce"]) is not None
            and same(value["anchor_identity"], _anchor_identity())
            and value["transaction_digest"] == codec.canonical_digest({k: v for k, v in value.items() if k != "transaction_digest"}),
            "transaction_identity_changed")
    record = value["record"]
    record_fields = {"schema_version", "run_id", "run_ref", "anchor_identity", "previous_run", "model_execution_preimage",
                     "transition", "history", "selector_transport_policy", "retained_calls", "maximum_selector_dispatches", "released"}
    # The original images/anchor and transition must still be the exact retained
    # source. validate_transition performs committed-source closure before apply.
    require(type(record) is dict and set(record) == record_fields
            and record["schema_version"] == SCHEMA and record["run_ref"] == RUN_REF and record["run_id"] == "m4"
            and _integer(record["retained_calls"], 12) and _integer(record["maximum_selector_dispatches"], 1)
            and _integer(record["released"], 0) and record["selector_transport_policy"] == _POLICY
            and same(record["anchor_identity"], value["anchor_identity"])
            and record["previous_run"]["raw_digest"] == ORIGINAL_RUN_DIGEST
            and same(codec.strict_json_loads(image_bytes(record["previous_run"])), anchor["original_state"])
            and record["model_execution_preimage"]["raw_digest"] == anchor["manifest"]["files"][RUN_REF + "/model-execution.json"],
            "transaction_original_source_changed")
    image_bytes(record["model_execution_preimage"])
    before_raw, after_raw = image_bytes(value["before"]), image_bytes(value["after"])
    before, after = codec.strict_json_loads(before_raw), codec.strict_json_loads(after_raw)
    digest = codec.raw_digest(_json_bytes(record))
    reference_value = {"schema_version": SCHEMA, "record_ref": home + "record.json",
                       "record_digest": digest, "artifact_root": str(root)}
    if kind == "prepare":
        require(value["row"] is None and before_raw == image_bytes(record["previous_run"])
                and after_raw == _json_bytes(_prepared_state(before, record, reference_value)), "transaction_prepare_postimage_changed")
    else:
        require(same(before.get(REFERENCE), reference_value) and same(before.get("b_route_execution_transition"), record["transition"]),
                "transaction_parent_identity_changed")
        expected = deepcopy(before)
        ledger = expected["capability_selection"]
        if kind == "reservation":
            row = value["row"]
            require(_integer(ledger["total_invocations"], 12) and len(ledger["calls"]) == 12
                    and _integer(row["number"], 13) and row["reservation_id"] == "m4:dispatch:13"
                    and row["phase"] == "selection" and row["candidate"] is None
                    and row["run_id"] == "m4" and row["status"] == "reserved" and "outcome" not in row
                    and row["capability_id"] == ledger["current"]["capability_id"] and row["lineage"] is None
                    and _integer(row["generation"], 1) and _integer(row["execution"], 1), "transaction_parent_row_changed")
            ledger["calls"].append(deepcopy(row))
            ledger["total_invocations"] = 13
        else:
            require(value["row"] is None and _integer(ledger["total_invocations"], 13) and len(ledger["calls"]) == 13
                    and ledger["calls"][12].get("outcome") is None, "transaction_unknown_requires_unsettled_row")
            ledger["calls"][12]["outcome"] = {"status": "unknown", "error_type": "metadata_reconcile_dispatch_uncertain"}
            ledger["terminal"] = True
            expected.update(phase="selection-blocked", selection_status="blocked",
                            selection_block_reason="selector_metadata_reconcile_dispatch_uncertain")
        require(after_raw == _json_bytes(expected), "transaction_parent_postimage_changed")
    _current_projection(anchor, after)
    operations = _transaction_operations(kind, record, before_raw, after_raw, value["row"])
    return value, operations


def _publication_paths(home, value, raw):
    stem = value["kind"] + "-publication-" + value["nonce"] + "-" + codec.raw_digest(raw)[7:]
    return home / (stem + ".image"), home / (stem + ".part"), home / (stem + ".pending")


def _plain_bytes(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and not stat.S_ISLNK(info.st_mode)
            and not getattr(info, "st_file_attributes", 0) & 0x400, "metadata_plain_single_link_required")
    raw = path.read_bytes()
    after = path.lstat()
    require((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), "metadata_changed_during_read")
    return raw


def _append_exact(path, expected):
    """Append a proven suffix; never replace or truncate an observed prefix."""
    exists = os.path.lexists(path)
    identity = path.lstat() if exists else None
    before = _plain_bytes(path) if exists else b""
    require(expected.startswith(before), "transaction_temporary_bytes_changed")
    if exists and before == expected:
        return
    if identity is not None:
        after_read = path.lstat()
        require((identity.st_dev, identity.st_ino, identity.st_size, identity.st_mtime_ns) ==
                (after_read.st_dev, after_read.st_ino, after_read.st_size, after_read.st_mtime_ns),
                "metadata_append_identity_changed")
    with path.open("ab" if exists else "xb") as stream:
        current = os.fstat(stream.fileno())
        require(stat.S_ISREG(current.st_mode) and current.st_nlink == 1
                and (identity is None or (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns) ==
                     (identity.st_dev, identity.st_ino, identity.st_size, identity.st_mtime_ns)),
                "metadata_append_identity_changed")
        stream.write(expected[len(before):])
        stream.flush()
        os.fsync(stream.fileno())
    require(_plain_bytes(path) == expected, "metadata_append_incomplete")


def _prefix_path(root, value, tag, expected, prefix):
    require(expected.startswith(prefix), "transaction_temporary_bytes_changed")
    name = (value["kind"] + "-history-" + value["nonce"] + "-" + tag + "-" + str(len(prefix)) +
            "-" + codec.raw_digest(prefix)[7:] + ".bin")
    return sources.checked_path(root, RUN_REF + "/recovery/s1/" + name)


def _remember_prefix(root, value, tag, expected, prefix):
    evidence = _prefix_path(root, value, tag, expected, prefix)
    _append_exact(evidence, prefix)
    return evidence


def _exclusive_rename(source, destination):
    # Windows rename is atomic and refuses an existing destination. Do not use
    # POSIX rename's replace semantics or a check-then-replace emulation.
    require(os.name == "nt", "exclusive_metadata_publication_requires_windows")
    os.rename(source, destination)


def _publish_transaction(path, value, raw):
    """Publish a full journal exclusively, retaining independent full material.

    A first incomplete material is not enough to reconstruct arbitrary lost
    request identity. It remains blocked unless an exact original full image
    is explicitly supplied and authenticated by its existing name and prefix.
    """
    require(os.name == "nt", "exclusive_metadata_publication_requires_windows")
    home = path.parent
    root = home.parents[len(Path(RUN_REF).parts) + 1]
    require(path.name == value["kind"] + "-transaction.json"
            and home == sources.checked_path(root, RUN_REF + "/recovery/s1"), "fixed_publication_path")
    material, part, pending = _publication_paths(home, value, raw)
    if os.path.lexists(material):
        require(_plain_bytes(material) == raw, "publication_material_changed")
    else:
        if os.path.lexists(part):
            _remember_prefix(root, value, "p", raw, _plain_bytes(part))
        _append_exact(part, raw)
        _exclusive_rename(part, material)
    if os.path.lexists(path):
        require(_plain_bytes(path) == raw, "published_transaction_changed")
        return
    if os.path.lexists(pending):
        _remember_prefix(root, value, "j", raw, _plain_bytes(pending))
    _append_exact(pending, raw)
    _exclusive_rename(pending, path)
    require(_plain_bytes(path) == raw and _plain_bytes(material) == raw, "publication_closing_changed")


def _publication_members(root, kind):
    home = sources.checked_path(root, RUN_REF + "/recovery/s1")
    if not home.exists():
        return []
    return sorted(path for path in home.iterdir() if path.name.startswith(kind + "-publication-"))


def _has_transaction(root, kind):
    home = sources.checked_path(root, RUN_REF + "/recovery/s1")
    return os.path.lexists(home / (kind + "-transaction.json")) or bool(_publication_members(root, kind))


def _journal(root, kind, anchor, *, publication_image=None):
    home = sources.checked_path(root, RUN_REF + "/recovery/s1")
    final = home / (kind + "-transaction.json")
    members = _publication_members(root, kind)
    if os.path.lexists(final):
        raw = codec.read_reference_bytes(root, final.relative_to(root).as_posix())
        try:
            value = codec.strict_json_loads(raw)
        except codec.CodecError as error:
            raise ValueError("b_route_selector_recovery:published_transaction_malformed_preserved") from error
    else:
        candidates = []
        for path in members:
            match = re.fullmatch(re.escape(kind) + r"-publication-([0-9a-f]{32})-([0-9a-f]{64})\.(image|part|pending)", path.name)
            require(match is not None, "publication_filename_changed")
            candidate = _plain_bytes(path)
            if codec.raw_digest(candidate)[7:] == match.group(2):
                decoded = codec.strict_json_loads(candidate)
                require(type(decoded) is dict and decoded.get("nonce") == match.group(1), "publication_nonce_changed")
                candidates.append(candidate)
        if publication_image is not None:
            require(type(publication_image) is bytes, "original_publication_image_bytes_required")
            decoded = codec.strict_json_loads(publication_image)
            require(type(decoded) is dict and decoded.get("kind") == kind, "original_publication_image_kind_changed")
            expected_paths = _publication_paths(home, decoded, publication_image)
            require(any(path in members for path in expected_paths), "original_publication_provenance_missing")
            candidates.append(publication_image)
        require(bool(candidates), "publication_material_incomplete_original_image_required")
        require(all(candidate == candidates[0] for candidate in candidates), "publication_material_ambiguous")
        raw = candidates[0]
        value = codec.strict_json_loads(raw)
    checked, operations = _validate_transaction(root, kind, anchor, value)
    if publication_image is not None:
        require(publication_image == raw, "original_publication_image_changed")
    if members:
        require(raw == _json_bytes(value), "publication_canonical_bytes_changed")
        allowed = set(_publication_paths(home, value, raw))
        require(all(path in allowed for path in members), "publication_identity_occupied")
        for path in members:
            data = _plain_bytes(path)
            require(raw.startswith(data) and (path.suffix != ".image" or data == raw), "publication_prefix_changed")
    return checked, operations


def _operation_paths(root, value, index, target_ref):
    target = sources.checked_path(root, target_ref)
    temporary = target.with_name(target.name + "." + value["nonce"] + ".tmp")
    evidence = sources.checked_path(root, RUN_REF + "/recovery/s1/" + value["kind"] + "-temporary-" + str(index) + ".bin")
    return target, temporary, evidence


def _history_artifacts(root, value, operations):
    """Authenticate a finite prefix identity, not a permissive file wildcard."""
    home = sources.checked_path(root, RUN_REF + "/recovery/s1")
    expected = {"p": _json_bytes(value), "j": _json_bytes(value)}
    expected.update({"o" + str(index): row[2] for index, row in enumerate(operations)})
    result = {}
    for path in home.iterdir():
        if not path.name.startswith(value["kind"] + "-history-"):
            continue
        pattern = (re.escape(value["kind"] + "-history-" + value["nonce"] + "-") +
                   r"(p|j|o[0-9]+)-(0|[1-9][0-9]*)-([0-9a-f]{64})\.bin")
        match = re.fullmatch(pattern, path.name)
        require(match is not None and match.group(1) in expected, "transaction_history_filename_changed")
        total = expected[match.group(1)]
        count = int(match.group(2))
        require(count <= len(total), "transaction_history_prefix_length_changed")
        snapshot = total[:count]
        require(codec.raw_digest(snapshot)[7:] == match.group(3), "transaction_history_prefix_identity_changed")
        require(snapshot.startswith(_plain_bytes(path)), "transaction_history_bytes_changed")
        result[path] = snapshot
    return result


def _transaction_artifacts(root, value, operations):
    result = {path: expected for path, expected in _history_artifacts(root, value, operations).items()}
    raw = _json_bytes(value)
    home = sources.checked_path(root, RUN_REF + "/recovery/s1")
    material, part, pending = _publication_paths(home, value, raw)
    for path in (material, part, pending):
        if os.path.lexists(path):
            data = _plain_bytes(path)
            require(raw.startswith(data) and (path != material or data == raw), "publication_prefix_changed")
            result[path] = raw
    for index, (target_ref, _before, after) in enumerate(operations):
        _, temporary, legacy_evidence = _operation_paths(root, value, index, target_ref)
        for path in (temporary, legacy_evidence):
            if os.path.lexists(path):
                require(after.startswith(_plain_bytes(path)), "transaction_temporary_bytes_changed")
                result[path] = after
    return result


def _journal_artifacts(root, anchor, *, publication_images=None):
    """Only journal-bound temporary bytes, including owned partial writes, enter."""
    result = set()
    for kind in _TRANSACTIONS:
        reference = RUN_REF + "/recovery/s1/" + kind + "-transaction.json"
        if not _has_transaction(root, kind):
            continue
        value, operations = _journal(root, kind, anchor,
            publication_image=(publication_images or {}).get(kind))
        if os.path.lexists(root / reference):
            result.add(reference)
        result.update(path.relative_to(root).as_posix() for path in _transaction_artifacts(root, value, operations))
        if kind == "reservation":
            # A receipt may exist even when the parent image is uncertain. It
            # remains unqualified evidence; permit only this exact charged row's
            # finite native receipt path while reconciling its liability.
            result.add(RUN_REF + "/dispatch-receipts/dispatch-13.json")
        for index, (target_ref, _before, after) in enumerate(operations):
            result.add(target_ref)
    return result


def _targets_close(root, value, operations):
    for index, (target_ref, before, after) in enumerate(operations):
        target, _temporary, _legacy = _operation_paths(root, value, index, target_ref)
        current = codec.read_reference_bytes(root, target_ref) if os.path.lexists(target) else None
        require(current in (before, after), "transaction_target_not_pre_or_postimage:" + target_ref)
    _transaction_artifacts(root, value, operations)


def _complete_publication(root, value, operations):
    final = sources.checked_path(root, RUN_REF + "/recovery/s1/" + value["kind"] + "-transaction.json")
    if os.path.lexists(final):
        require(same(read(root, final.relative_to(root).as_posix()), value), "published_transaction_changed")
        return
    _targets_close(root, value, operations)
    _durable(final, value, exclusive=True)
    checked, _ = _journal(root, value["kind"], _trusted_anchor(root))
    require(same(checked, value), "transaction_changed_during_publication_resume")


def _apply_transaction(root, value, operations):
    # Caller holds the original coordinator mutex. No model, request counter,
    # replacement or candidate lifecycle is owned by this metadata primitive.
    _targets_close(root, value, operations)
    for path, expected in _history_artifacts(root, value, operations).items():
        _append_exact(path, expected)
    for index, (target_ref, before, after) in enumerate(operations):
        target, temporary, _legacy = _operation_paths(root, value, index, target_ref)
        current = codec.read_reference_bytes(root, target_ref) if os.path.lexists(target) else None
        require(current in (before, after), "transaction_target_not_pre_or_postimage:" + target_ref)
        if os.path.lexists(temporary):
            _remember_prefix(root, value, "o" + str(index), after, _plain_bytes(temporary))
        if current == after:
            continue
        _append_exact(temporary, after)
        current = codec.read_reference_bytes(root, target_ref) if os.path.lexists(target) else None
        require(current in (before, after), "transaction_target_changed_before_replace:" + target_ref)
        if current == after:
            continue
        os.replace(temporary, target)


def _start_transaction(root, kind, record, before, after, *, row=None):
    value = _transaction_value(kind, record, before, after, row)
    path = sources.checked_path(root, RUN_REF + "/recovery/s1/" + kind + "-transaction.json")
    require(not _has_transaction(root, kind), "transaction_publication_occupied_reconcile_required")
    anchor = _trusted_anchor(root)
    checked, operations = _validate_transaction(root, kind, anchor, value)
    _targets_close(root, checked, operations)
    _close_sources(root, anchor)
    import _b_route_execution_transition as transition
    transition.validate_transition(root, codec.strict_json_loads(after))
    _old_files_close(root, anchor, read(root, RUN_REF + "/run.json"))
    _durable(path, value, exclusive=True)
    checked, operations = _journal(root, kind, anchor)
    require(same(checked, value), "transaction_changed_before_apply")
    _apply_transaction(root, value, operations)
    return value


def _prepared_state(original, record, reference):
    state = deepcopy(original)
    state.update(b_route_execution_transition=record["transition"], b_route_execution_history=record["history"],
                 phase="selector-recovery-prepared", selection_status="pending")
    state[REFERENCE] = reference
    state.pop("selection_block_reason", None)
    state["capability_selection"]["terminal"] = False
    state["capability_selection"]["current"]["stage"] = "selector-recovery-prepared"
    state["capability_selection"]["current"].pop("preparation_error", None)
    return state


def prepare(root, run_dir, *, prior_source_root, prior_commit, original_source_root, current_commit, retained_capture):
    import _b_route_execution_transition as transition
    from _mvg_capability_checkpoint import coordinator_lock
    root, run = Path(root).resolve(), Path(run_dir).resolve()
    require(run == sources.checked_path(root, RUN_REF) and prior_commit == PRIOR_COMMIT, "explicit_original_selector_run")
    path_preflight(root)
    home = run / "recovery/s1"
    with coordinator_lock(run), transition._verification_transaction():
        require(not os.path.lexists(home) and not os.path.lexists(run / "s1"), "selector_namespace_occupied")
        original = verify_retained_selector_capture(root, retained_capture,
            current_state=read(root, RUN_REF + "/run.json"))
        raw_run = codec.read_reference_bytes(run, "run.json")
        raw_model = codec.read_reference_bytes(run, "model-execution.json")
        next_epoch = transition.build_mvg_selector_transition(root, original, original_source_root,
            current_commit, prior_source_root, prior_commit, retained_capture=retained_capture)
        history = {**original.get("b_route_execution_history", {}),
                   original["b_route_execution_transition"]["transition_digest"]: original["b_route_execution_transition"]}
        record = {"schema_version": SCHEMA, "run_id": "m4", "run_ref": RUN_REF,
                  "anchor_identity": retained_capture["anchor_identity"], "previous_run": image(raw_run),
                  "model_execution_preimage": image(raw_model), "transition": next_epoch, "history": history,
                  "selector_transport_policy": _POLICY, "retained_calls": 12, "maximum_selector_dispatches": 1, "released": 0}
    with coordinator_lock(run):
        verify_retained_selector_capture(root, retained_capture, current_state=read(root, RUN_REF + "/run.json"))
        require(not os.path.lexists(home) and not os.path.lexists(run / "s1")
                and codec.read_reference_bytes(run, "run.json") == raw_run
                and codec.read_reference_bytes(run, "model-execution.json") == raw_model, "prepare_raw_cas_changed")
        home.mkdir(parents=True, exist_ok=False)
        raw_record = _json_bytes(record)
        digest = codec.raw_digest(raw_record)
        reference = {"schema_version": SCHEMA, "record_ref": RUN_REF + "/recovery/s1/record.json",
                     "record_digest": digest, "artifact_root": str(root)}
        value = _prepared_state(original, record, reference)
        _start_transaction(root, "prepare", record, raw_run, _json_bytes(value))
    transition.validate_transition(root, value)
    validate_recovery(root, value)
    return {"status": "selector-recovery-prepared", "record": reference, "retained_calls": 12,
            "next_dispatch": "m4:dispatch:13", "model_calls": 0, "released": 0}


def path_preflight(root):
    """Conservative path arithmetic only; no filesystem or registry change."""
    run = Path(root).resolve() / RUN_REF
    suffix = "." + "9" * 10 + "." + "9" * 20 + "." + "f" * 32 + ".tmp"
    paths = [run / "s1/attempt-1/llm-sandbox/attempt-1/selection/runner-input-integrity.json",
             run / "s1/attempt-1/execution-binding-1-selection.json", run / "recovery/s1/intent.json"]
    lengths = {str(path): len(str(path) + suffix) for path in paths}
    require(max(lengths.values()) <= 259, "legacy_atomic_path_over_259")
    return {"limit": 259, "maximum_atomic_path_chars": max(lengths.values()), "paths": lengths}


def authorize_selector_reservation(root, state, *, phase, candidate, request_identity, reservation=None):
    """One intent after actual final preflight; original reserve owns row13."""
    require(is_selector_recovery(state) and phase == "selection" and candidate is None, "selector_only_no_regeneration")
    record = validate_recovery(root, state)
    require(same(read(root, RUN_REF + "/run.json"), state), "actual_coordinator_state_changed")
    require(_integer(state["capability_selection"]["total_invocations"], 12), "selector_intent_already_reserved")
    request = request_identity
    workspace = selector_workspace(root, state, 0, 1) / "llm-sandbox/attempt-1/selection"
    require(_integer(request["attempt"], 1) and request["workspace"] == workspace.relative_to(Path(root) / RUN_REF).as_posix()
            and request.get("selector_transport_policy") == _POLICY
            and request["selection_input_sha256"] == state["capability_selection"]["current"]["input_sha256"],
            "exact_selector_request_required")
    path = sources.checked_path(root, state[REFERENCE]["record_ref"]).with_name("intent.json")
    require(type(reservation) is dict and same(reservation.get("request_identity"), request), "parent_reservation_required")
    require(not os.path.lexists(path), "selector_intent_occupied_reconcile_required")
    before = codec.read_reference_bytes(root, RUN_REF + "/run.json")
    after = deepcopy(state)
    after["capability_selection"]["total_invocations"] = 13
    after["capability_selection"]["calls"].append(deepcopy(reservation))
    # Parent constructs the exact paid row. The journal closes intent -> that
    # row before reserve returns; interruption is reconciled with zero dispatch.
    _start_transaction(root, "reservation", record, before, _json_bytes(after), row=reservation)


def reconcile(root, run_dir, *, retained_capture, publication_images=None):
    """Finish only proven metadata under the native lock; never authorize retry.

    An incomplete/unsettled reservation is conservatively charged as unknown and
    terminal. Missing row alone is not evidence that dispatch never happened.
    Old unjournaled partial preparation/intent remains blocked with originals.
    """
    from _mvg_capability_checkpoint import coordinator_lock
    import _b_route_execution_transition as transition
    root, run = Path(root).resolve(), Path(run_dir).resolve()
    require(run == sources.checked_path(root, RUN_REF), "explicit_original_selector_run")
    publication_images = dict(_closed_publication_images(publication_images))
    with coordinator_lock(run), _publication_material_scope(root, publication_images):
        # The original witness executes at this read-only scope's exit. It must
        # succeed before publishing material or changing any target.
        with transition._verification_transaction():
            require(type(retained_capture) is _RetainedSelectorCapture and retained_capture._root == root
                    and same(retained_capture._identity, _anchor_identity()), "factory_capture_required")
            anchor = _trusted_anchor(root)
            require(same(anchor, retained_capture._anchor), "capture_instance_changed")
            home = sources.checked_path(root, RUN_REF + "/recovery/s1")
            require(_has_transaction(root, "prepare"), "legacy_unjournaled_preparation_blocked")
            require(all(_has_transaction(root, kind) for kind in publication_images or {}), "original_publication_provenance_missing")
            prepare_value, operations = _journal(root, "prepare", anchor,
                publication_image=(publication_images or {}).get("prepare"))
            prepared = codec.strict_json_loads(image_bytes(prepare_value["after"]))
            _close_sources(root, anchor)
            actual = read(root, RUN_REF + "/run.json")
            _old_files_close(root, anchor, actual, publication_images=publication_images)
            preparation_incomplete = not os.path.lexists(home / "committed.json")
            transition.validate_transition(root, prepared if preparation_incomplete else actual)
        _complete_publication(root, prepare_value, operations)
        if preparation_incomplete:
            _apply_transaction(root, prepare_value, operations)
        else:
            _record(root, prepared)
        state = read(root, RUN_REF + "/run.json")
        validate_recovery(root, state)
        reservation_path = home / "reservation-transaction.json"
        if _has_transaction(root, "reservation"):
            value, operations = _journal(root, "reservation", anchor,
                publication_image=(publication_images or {}).get("reservation"))
            if not os.path.lexists(home / "reservation-committed.json"):
                _targets_close(root, value, operations)
            _complete_publication(root, value, operations)
            if not os.path.lexists(home / "reservation-committed.json"):
                _apply_transaction(root, value, operations)
            if _has_transaction(root, "unknown"):
                unknown, unknown_operations = _journal(root, "unknown", anchor,
                    publication_image=(publication_images or {}).get("unknown"))
                _complete_publication(root, unknown, unknown_operations)
                _apply_transaction(root, unknown, unknown_operations)
            state = read(root, RUN_REF + "/run.json")
            calls = state["capability_selection"]["calls"]
            require(len(calls) == 13, "reconciled_reservation_missing")
            if calls[12].get("outcome") is None:
                if not _has_transaction(root, "unknown"):
                    after = deepcopy(state)
                    after["capability_selection"]["calls"][12]["outcome"] = {
                        "status": "unknown", "error_type": "metadata_reconcile_dispatch_uncertain"}
                    after["capability_selection"]["terminal"] = True
                    after.update(phase="selection-blocked", selection_status="blocked",
                                 selection_block_reason="selector_metadata_reconcile_dispatch_uncertain")
                    _start_transaction(root, "unknown", value["record"], _json_bytes(state), _json_bytes(after))
                else:
                    unknown, operations = _journal(root, "unknown", anchor,
                        publication_image=(publication_images or {}).get("unknown"))
                    _complete_publication(root, unknown, operations)
                    _apply_transaction(root, unknown, operations)
                state = read(root, RUN_REF + "/run.json")
        elif os.path.lexists(home / "intent.json"):
            require(False, "legacy_unjournaled_intent_blocked")
        validate_recovery(root, state)
        return {"status": state["selection_status"], "logical_reserved_calls": state["capability_selection"]["total_invocations"],
                "model_calls": 0, "released": 0, "retry_authorized": False}


def verify_retained_dispatches(root, run_dir, state):
    """Actual captured old12 plus the original full verifier for new13 only."""
    root, run = Path(root).resolve(), Path(run_dir).resolve()
    require(run == sources.checked_path(root, RUN_REF), "retained_dispatch_run_changed")
    validate_recovery(root, state)
    calls = state["capability_selection"]["calls"]
    if len(calls) == 13:
        import _b_route_planning_runtime as runtime
        runtime.verify_reserved_call(run, calls[12])
        require(calls[12].get("outcome", {}).get("status") == "completed", "selector_dispatch_not_completed")
    return {"retained_original_calls": 12, "new_selector_calls": len(calls) - 12,
            "logical_reserved_calls": len(calls), "released": 0}


def preview_selector_materials(root, state):
    """Return complete real admitted inputs, no writes/intent/model authority."""
    validate_recovery(root, state)
    capture = capture_retained_selector(root)
    anchor = capture._anchor
    values = {}
    for slot, row in anchor["admissions"].items():
        values[slot] = retained_candidate_artifacts(root, Path(root) / RUN_REF, state,
            anchor["selection"]["scopes"], 0, anchor["selection"]["accepted_seed"], anchor["selection"]["records"],
            row["admission"])[0]
    return {"scopes": deepcopy(anchor["selection"]["scopes"]), "accepted_seed": deepcopy(anchor["selection"]["accepted_seed"]),
            "aliases": deepcopy(anchor["selection"]["aliases"]), "input_identity": deepcopy(anchor["selection"]["input_identity"]),
            "proposals": values, "selector_transport_policy": _POLICY}
