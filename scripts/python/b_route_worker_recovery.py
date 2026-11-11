"""Explicit, dispatch-free recovery of completed first-scope MVG workers.

Original dispatch/worker/selection rules remain byte-identical. Missing evidence
is a blocker, never a failed invocation or permission to try another model call.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import re
import sys

# A standalone support-worktree entry may inspect an original run only with the
# original repository's owners. Do not load relocated copies and relabel them.
if __name__ == "__main__":
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--repo-root", type=Path, required=True)
    selected_root, _ = bootstrap.parse_known_args()
    sys.path.insert(0, str(selected_root.repo_root.resolve() / "scripts/python"))

import _b_route_codec as codec
import _b_route_planning_runtime as runtime
import _b_route_sources as sources
import _mvg_capability_selection as selection
from _planning_skill_common import atomic_json, canonical_sha, file_sha

SCHEMA = "newrouge.b-route-completed-worker-recovery.v1"


def _check_owners(root):
    directory = root / "scripts/python"
    for owner in (codec, runtime, runtime.planning, runtime.candidate, sources, selection, runtime.wire):
        if Path(owner.__file__).resolve().parent != directory:
            raise ValueError("worker_recovery_original_module_origin_required:" + owner.__name__)
    for name, owner in list(sys.modules.items()):
        if "." not in name and (directory / (name + ".py")).is_file():
            origin = getattr(owner, "__file__", None)
            if origin is None or Path(origin).resolve() != directory / (name + ".py"):
                raise ValueError("worker_recovery_original_import_cache_required:" + name)


def _load(path):
    return codec.strict_json_loads(path.read_bytes())


def _path(root, relative):
    return sources.checked_path(root, relative)


def manifest(run):
    """Never follow links or discover files outside this explicit run."""
    result = {}
    for directory, folders, files in os.walk(run, followlinks=False):
        for name in [*folders, *files]:
            path = Path(directory) / name
            if (name.casefold() in {"sessions", "auth.json", "credentials.json"}
                    or getattr(path.lstat(), "st_file_attributes", 0) & 0x400 or path.is_symlink()):
                raise ValueError("worker_recovery_protected_or_reparse_path")
        for name in files:
            path = Path(directory) / name
            # Windows denies byte reads even through a second handle in the
            # owning process while the native mutex is held. This one-byte OS
            # synchronization file is not evidence; apply validates it before
            # acquiring its original lock. All other files remain raw-bound.
            if path == run / "capability-coordinator.lock":
                if path.stat().st_size != 1:
                    raise ValueError("worker_recovery_native_lock_shape_changed")
                continue
            result[path.relative_to(run).as_posix()] = file_sha(path)
    return result


def process_absent(pid):
    """A live or inaccessible PID is a blocker; never stop or adopt it."""
    if type(pid) is not int or pid <= 0:
        raise ValueError("worker_recovery_process_identity_invalid")
    if os.name != "nt":
        raise ValueError("worker_recovery_requires_windows_process_observation")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    api.GetExitCodeProcess.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    handle = api.OpenProcess(0x1000, False, pid)
    if not handle:
        return ctypes.get_last_error() == 87  # ERROR_INVALID_PARAMETER: no such PID.
    try:
        code = wintypes.DWORD()
        return bool(api.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value != 259
    finally:
        api.CloseHandle(handle)


def _worker(run, state, label, scope, seed):
    workspace = selection.scope_workspace(run, label, 0, 1, state["capability_selection"]["current"].get("execution", 1))
    relative = workspace.relative_to(run).as_posix()
    lifecycle = _path(run, relative + "/lifecycle")
    if not lifecycle.exists():
        return None
    job = _load(lifecycle / "job.json")
    if set(job) != {"schema_version", "identity", "input"} or job["schema_version"] != "newrouge.mvg-capability-worker.v1" or canonical_sha(job["input"]) != job["identity"]:
        raise ValueError("worker_recovery_job_identity_changed")
    data = job["input"]
    if (set(data) != {"root", "run_dir", "workspace", "state", "scope_index", "accepted_seed", "selected_records", "runner"}
            or Path(data["run_dir"]) != run or Path(data["root"]) != run.parents[3]
            or Path(data["workspace"]) != workspace or data["scope_index"] != 0
            or data["selected_records"] != [] or data["accepted_seed"] != seed
            or data["runner"] != state["runner_configuration"]):
        raise ValueError("worker_recovery_job_scope_changed")
    original = data["state"]
    for key in ("schema_version", "run_id", "input_stage", "planning_runtime", "runtime_identity",
                "analysis_identity_sha256", "checkpoint_strategy", "checkpoint_schema_version",
                "mvg.run_invocation_limit", "mvg.run_invocation_limit_source", "runner_configuration", "recovery"):
        if original.get(key) != state.get(key):
            raise ValueError("worker_recovery_job_state_changed:" + key)
    if (original.get("runtime_slot") != label
            or original.get("runtime_execution") != state["capability_selection"]["current"].get("execution", 1)):
        raise ValueError("worker_recovery_job_slot_changed")
    process = _load(lifecycle / "process.json")
    if process.get("identity") != job["identity"] or type(process.get("pid")) is not int:
        raise ValueError("worker_recovery_process_identity_changed")
    requests, responses = {}, {}
    mailbox = lifecycle / "mailbox"
    for path in mailbox.glob("*.request.json"):
        message = _load(path)
        number = message.get("sequence")
        if (type(number) is not int or number < 1 or path.name != str(number) + ".request.json"
                or message.get("identity") != job["identity"] or number in requests):
            raise ValueError("worker_recovery_mailbox_identity_changed")
        requests[number] = message
        response = mailbox / (str(number) + ".response.json")
        if response.exists():
            responses[number] = _load(response)
            if responses[number].get("identity") != job["identity"] or responses[number].get("sequence") != number:
                raise ValueError("worker_recovery_mailbox_response_changed")
    if set(requests) != set(range(1, len(requests) + 1)):
        raise ValueError("worker_recovery_mailbox_sequence_changed")
    return {"workspace": workspace, "lifecycle": lifecycle, "job": job, "process": process,
            "requests": requests, "responses": responses, "scope": scope}


def completed_outcome(run, row, worker):
    """Require original acknowledged reservation and one original completion message."""
    reserved = {key: value for key, value in row.items() if key != "outcome"}
    matches = [(sequence, request) for sequence, request in worker["requests"].items()
               if request.get("kind") == "outcome" and request.get("reservation_id") == row["reservation_id"]]
    if not matches:
        return None
    if len(matches) != 1:
        raise ValueError("worker_recovery_duplicate_outcome")
    sequence, message = matches[0]
    acknowledgments = [(number, response) for number, response in worker["responses"].items()
                       if worker["requests"][number].get("kind") == "reserve"
                       and response.get("value") == reserved and not response.get("error")]
    if len(acknowledgments) != 1 or acknowledgments[0][0] >= sequence:
        raise ValueError("worker_recovery_reservation_acknowledgment_missing")
    outcome = message.get("outcome")
    if not isinstance(outcome, dict) or outcome.get("status") != "completed":
        return None  # An error message alone is not proof of an undispatched request.
    proposed = {**deepcopy(row), "outcome": deepcopy(outcome)}
    # This is the existing complete protocol/input/output/schema/high/host binding
    # verifier. It also requires an already persisted canonical draft. No output,
    # projection, canonical draft, receipt or completion is manufactured here.
    runtime.verify_reserved_call(run, proposed)
    return deepcopy(outcome)


def budget_invariants(original, proposed):
    """Publication changes projections only, never budgets or existing proof."""
    def without(value, keys):
        return {k: v for k, v in value.items() if k not in keys}
    if without(original, {"capability_selection", "candidate_admissions", "candidate_attempts"}) != without(proposed, {"capability_selection", "candidate_admissions", "candidate_attempts"}):
        raise ValueError("worker_recovery_nonprojection_state_changed")
    left, right = original["capability_selection"], proposed["capability_selection"]
    if without(left, {"calls", "current"}) != without(right, {"calls", "current"}) or len(left["calls"]) != len(right["calls"]):
        raise ValueError("worker_recovery_reservation_accounting_changed")
    for old, new in zip(left["calls"], right["calls"]):
        if without(old, {"outcome"}) != without(new, {"outcome"}) or (old.get("outcome") is not None and old.get("outcome") != new.get("outcome")):
            raise ValueError("worker_recovery_original_reservation_changed")
    if without(left["current"], {"admissions"}) != without(right["current"], {"admissions"}):
        raise ValueError("worker_recovery_original_scope_changed")
    for old, new in ((left["current"]["admissions"], right["current"]["admissions"]),
                     (original.get("candidate_admissions", {}), proposed.get("candidate_admissions", {}))):
        if any(new.get(k) != value for k, value in old.items()):
            raise ValueError("worker_recovery_existing_admission_changed")


def plan(root, *, run_id, planner="mvg"):
    root = runtime.planning.root_path(root)
    _check_owners(root)
    run = runtime.run_location(root, planner, run_id)
    if not run.is_dir():
        raise ValueError("worker_recovery_existing_run_required")
    before = manifest(run)
    state = _load(run / "run.json")
    if state.get("run_id") != run_id:
        raise ValueError("worker_recovery_run_identity_changed")
    desc = runtime.descriptor(state)
    if desc["planner"] != planner or planner != "mvg":
        raise ValueError("worker_recovery_mvg_only_no_time_refund")
    runtime.validate_input(root, run, state)
    _check_owners(root)
    proposed = deepcopy(state)
    ledger = proposed["capability_selection"]
    current = ledger.get("current")
    if (ledger.get("terminal") or ledger.get("selected") != [] or selection.generation(state) != 1
            or not isinstance(current, dict) or current.get("order_index") != 0
            or current.get("selection_attempts") or current.get("input_sha256") is not None
            or ledger.get("checkpoint_head") is not None or state.get("selection_status") != "pending"):
        raise ValueError("worker_recovery_requires_pending_first_scope")
    if (type(current.get("execution", 1)) is not int or current.get("execution", 1) < 1
            or not isinstance(current.get("admissions"), dict)
            or not set(current["admissions"]).issubset(runtime.labels(state))):
        raise ValueError("worker_recovery_current_identity_changed")
    scopes = runtime.scopes(state, run / "analysis-input")
    seed = runtime.seed(state, run / "analysis-input")
    if current.get("capability_id") != scopes[0]["capability_id"] or current.get("base_sha256") != canonical_sha(seed) or ledger.get("accepted_sha256") != canonical_sha(seed):
        raise ValueError("worker_recovery_seed_changed")
    blocked, recovered, workers = [], [], {}
    for label in runtime.labels(state):
        worker = _worker(run, state, label, scopes[0], seed)
        if worker:
            workers[label] = worker
            if not process_absent(worker["process"]["pid"]):
                blocked.append({"candidate": label, "reason": "worker_pid_live_or_unobservable"})
    for row in ledger.get("calls", []):
        if row.get("outcome") is not None:
            runtime.verify_reserved_call(run, row)
            continue
        # Unknown request integrity still fails closed before missing evidence is
        # classified. The current verifier is allowed to report only unknown.
        try:
            runtime.verify_reserved_call(run, row)
        except ValueError as exc:
            if str(exc) != "b_route_dispatch_outcome_unknown":
                raise
        else:
            raise ValueError("worker_recovery_unknown_gate_changed")
        worker = workers.get(row.get("candidate"))
        if (worker is None or row.get("generation", 1) != 1
                or row.get("execution", 1) != current.get("execution", 1)
                or row.get("capability_id") != current["capability_id"]):
            blocked.append({"reservation_id": row["reservation_id"], "reason": "original_worker_completion_unavailable"})
            continue
        outcome = completed_outcome(run, row, worker)
        if outcome is None:
            blocked.append({"reservation_id": row["reservation_id"], "reason": "dispatch_outcome_unknown"})
        else:
            row["outcome"] = outcome
            recovered.append(row["reservation_id"])
    admissions = []
    if not blocked:
        # No historical counter recovery or selected-checkpoint diagnostics are
        # needed in this explicitly bounded first-scope/generation contract.
        selection.verified_prefix(root, run, proposed, recover_counters=False)
        for label, worker in workers.items():
            if label in current["admissions"]:
                selection.candidate_artifacts(root, run, proposed, scopes, 0, seed, [], current["admissions"][label])
                continue
            path = worker["lifecycle"] / "result.json"
            if not path.exists():
                blocked.append({"candidate": label, "reason": "original_worker_result_missing"})
                continue
            result = _load(path)
            if (result.get("schema_version") != worker["job"]["schema_version"]
                    or result.get("identity") != worker["job"]["identity"]
                    or result.get("pid") != worker["process"]["pid"]):
                raise ValueError("worker_recovery_result_identity_changed")
            if result.get("status") != "admitted":
                blocked.append({"candidate": label, "reason": "original_worker_not_admitted"})
                continue
            workspace = worker["workspace"]
            artifacts = {name: file_sha(workspace / name) for name in (
                "proposal.json", "admission-review.json", "admission-execution.json")}
            if result.get("artifacts") != artifacts:
                raise ValueError("worker_recovery_result_artifacts_changed")
            admission = {"candidate": label, "status": "admitted", "lineage": label + "-r1", "generation": 1,
                "execution": current.get("execution", 1), "workspace": workspace.relative_to(run).as_posix(),
                "errors": result.get("errors", []), "append_terminal": False, "retryable": False,
                "total_invocations": result["total_invocations"]}
            for key, name in (("proposal", "proposal.json"), ("proof", "admission-review.json"), ("execution", "admission-execution.json")):
                admission[key + "_path"] = (workspace / name).relative_to(run).as_posix()
                admission[key + "_sha256"] = artifacts[name]
            proposal, _, _ = selection.candidate_artifacts(root, run, proposed, scopes, 0, seed, [], admission)
            import plan_mvg as pm
            validation = pm.validate_proposal(root, proposed, proposal, append_requirement_ids=set(scopes[0]["cumulative_requirement_ids"]))
            current["admissions"][label] = admission
            proposed.setdefault("candidate_admissions", {})[label] = deepcopy(admission)
            proposed.setdefault("candidate_attempts", {})[label] = {"status": "valid", "validation": validation,
                "attempt_count": admission["total_invocations"], "proposal_sha256": admission["proposal_sha256"]}
            admissions.append(label)
    if manifest(run) != before:
        raise ValueError("worker_recovery_snapshot_changed")
    budget_invariants(state, proposed)
    # Even a recoverable completion is not published while any worker is blocked.
    changed = proposed != state
    result = {"schema_version": SCHEMA, "run_id": run_id, "runtime_identity": state["runtime_identity"],
        "status": "blocked" if blocked else "ready" if changed else "no-op", "blockers": blocked,
        "original_manifest": before, "original_state_sha256": canonical_sha(state),
        "proposed_state_sha256": canonical_sha(proposed),
        "proposed_raw_sha256": codec.raw_digest((json.dumps(proposed, ensure_ascii=False, indent=2) + "\n").encode("utf-8")),
        "recovery_source_sha256": file_sha(Path(__file__)), "recovered_completion_ids": recovered,
        "recovered_admissions": admissions, "logical_reservations": ledger["total_invocations"],
        "new_model_calls": 0, "released_reservations": 0, "released_stage_ceiling": 0,
        "provider_model": "unknown", "provider_dispatches": "unknown", "billing": "unknown"}
    result["plan_identity"] = canonical_sha(result)
    return result, proposed


def apply(root, *, run_id, expected_plan, planner="mvg"):
    """One explicit coordinator publication, with no worker/model invocation."""
    root = runtime.planning.root_path(root)
    run = runtime.run_location(root, planner, run_id)
    lock = _path(run, "capability-coordinator.lock")
    if not lock.is_file() or lock.read_bytes() != b"0":
        raise ValueError("worker_recovery_existing_native_lock_required")
    from _mvg_capability_checkpoint import coordinator_lock
    with coordinator_lock(run):
        report, proposed = plan(root, run_id=run_id, planner=planner)
        if report["plan_identity"] != expected_plan:
            raise ValueError("worker_recovery_plan_changed")
        if report["status"] == "blocked":
            raise ValueError("worker_recovery_blocked_no_publication")
        if report["status"] == "no-op":
            return report
        # The immutable intent is written first; run.json remains the sole
        # authoritative commit. Existing outputs/mailboxes/sidecars are untouched.
        target = _path(run, "worker-recovery/" + expected_plan.split(":")[-1] + ".json")
        if target.exists():
            raise ValueError("worker_recovery_prior_publication_requires_reinspection")
        original_bytes = (run / "run.json").read_bytes()
        if file_sha(run / "run.json") != report["original_manifest"]["run.json"]:
            raise ValueError("worker_recovery_original_state_changed")
        atomic_json(target, {"schema_version": SCHEMA, "plan": report,
            "original_state_base64": base64.b64encode(original_bytes).decode("ascii"),
            "proposed_state": proposed, "commit_policy": "run.json_is_authority",
            "recovery_source_sha256": file_sha(Path(__file__))})
        if manifest(run) != {**report["original_manifest"], target.relative_to(run).as_posix(): file_sha(target)}:
            raise ValueError("worker_recovery_snapshot_changed_before_commit")
        atomic_json(run / "run.json", proposed)
        if file_sha(run / "run.json") != report["proposed_raw_sha256"]:
            raise ValueError("worker_recovery_publication_outcome_unknown")
        return {**report, "status": "published", "original_worker_restarted": False}


def publication_status(root, *, run_id, plan_identity):
    """Resolve an interrupted publication from exact sealed pre/post bytes only."""
    root = runtime.planning.root_path(root)
    _check_owners(root)
    run = runtime.run_location(root, "mvg", run_id)
    if not isinstance(plan_identity, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", plan_identity):
        raise ValueError("worker_recovery_plan_identity_invalid")
    target = _path(run, "worker-recovery/" + plan_identity[7:] + ".json")
    event = _load(target)
    sealed = event["plan"]
    original_bytes = base64.b64decode(event["original_state_base64"], validate=True)
    original = codec.strict_json_loads(original_bytes)
    proposed = event["proposed_state"]
    if (event.get("schema_version") != SCHEMA or sealed["plan_identity"] != plan_identity
            or canonical_sha({k: v for k, v in sealed.items() if k != "plan_identity"}) != plan_identity
            or sealed["run_id"] != run_id or canonical_sha(original) != sealed["original_state_sha256"]
            or codec.raw_digest(original_bytes) != sealed["original_manifest"]["run.json"]
            or canonical_sha(proposed) != sealed["proposed_state_sha256"]
            or codec.raw_digest((json.dumps(proposed, ensure_ascii=False, indent=2) + "\n").encode("utf-8")) != sealed["proposed_raw_sha256"]
            or event["recovery_source_sha256"] != sealed["recovery_source_sha256"]):
        raise ValueError("worker_recovery_publication_journal_changed")
    budget_invariants(original, proposed)
    observed = file_sha(run / "run.json")
    status = ("committed" if observed == sealed["proposed_raw_sha256"] else
              "not_committed" if observed == sealed["original_manifest"]["run.json"] else "unknown_third_state")
    return {"schema_version": SCHEMA, "run_id": run_id, "plan_identity": plan_identity,
            "status": status, "new_model_calls": 0, "mutation_performed": False,
            "qualification_claimed": False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--planner", choices=("mvg", "capabilities"), default="mvg")
    parser.add_argument("--operation", choices=("inspect", "apply", "publication-status"), default="inspect")
    parser.add_argument("--expected-plan")
    args = parser.parse_args(argv)
    if args.operation != "inspect" and not args.expected_plan:
        parser.error("publication operations require --expected-plan from inspect")
    if args.operation == "publication-status":
        if args.planner != "mvg":
            parser.error("publication-status supports only MVG")
        report = publication_status(args.repo_root, run_id=args.run_id, plan_identity=args.expected_plan)
        print(json.dumps(report, indent=2))
        return 2 if report["status"] == "unknown_third_state" else 0
    result = (apply(args.repo_root, run_id=args.run_id, planner=args.planner, expected_plan=args.expected_plan)
              if args.operation == "apply" else plan(args.repo_root, run_id=args.run_id, planner=args.planner)[0])
    print(json.dumps(result, indent=2))
    return 2 if result["status"] == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
