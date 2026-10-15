"""Stage immutable selected increments; run.json is their sole commit point."""
from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
import os

from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json, repo_path

STRATEGY = "capability-selected-checkpoint.v1"
SCHEMA = "newrouge.mvg-capability-checkpoint.v1"
OUTCOME_SCHEMA = "newrouge.mvg-checkpoint-commit-outcome.v1"
CONFLICT_SCHEMA = "newrouge.mvg-checkpoint-conflict.v1"


class CheckpointCommitOutcomeUnknown(RuntimeError):
    """The disk pointer must be recovered before any further run state write."""


def _diagnostic_sha(value):
    try:
        return canonical_sha(value)
    except (TypeError, ValueError):
        return canonical_sha({"invalid_type": type(value).__name__, "representation": repr(value)[:2000]})


def record_conflict(run_dir, state, step, reason, *, expected=None, actual=None,
                    hash_subject="canonical_payload", actual_transaction_id=None):
    """Persist diagnostic evidence without changing checkpoint authority."""
    step = step if isinstance(step, dict) else {}
    pointer = step.get("checkpoint")
    pointer = pointer if isinstance(pointer, dict) else {}
    transaction_id = pointer.get("transaction_id")
    if not isinstance(transaction_id, str):
        transaction_id = _diagnostic_sha({"run_id": state.get("run_id"), "selection": step})
    evidence = {"schema_version": CONFLICT_SCHEMA, "run_id": state.get("run_id"),
        "transaction_id": transaction_id, "reason": str(reason),
        "hash_subject": hash_subject,
        "expected_sha256": _diagnostic_sha(expected), "actual_sha256": _diagnostic_sha(actual)}
    if actual_transaction_id is not None:
        evidence["actual_transaction_id"] = actual_transaction_id
        if hash_subject == "transaction_identity":
            evidence.update(expected_sha256=transaction_id, actual_sha256=actual_transaction_id)
    elif hash_subject == "accepted_projection_hash":
        evidence.update(expected_sha256=expected, actual_sha256=actual)
    try:
        if "receipt" in str(reason):
            evidence.update(hash_subject="receipt_file_bytes",
                artifact_path=step.get("receipt_path") if isinstance(step.get("receipt_path"), str) else None,
                expected_sha256=step.get("receipt_sha256"), actual_sha256=None)
            if isinstance(step.get("receipt_path"), str):
                receipt = repo_path(run_dir, step["receipt_path"])
                if receipt.is_relative_to(run_dir.resolve()) and receipt.is_file():
                    evidence["actual_sha256"] = file_sha(receipt)
        elif actual is None and pointer:
            evidence.update(hash_subject="checkpoint_payload_canonical", actual_sha256=None,
                expected_sha256=pointer.get("payload_sha256"))
            if isinstance(pointer.get("path"), str):
                artifact = repo_path(run_dir, pointer["path"])
                if artifact.is_relative_to(run_dir.resolve()) and artifact.is_file():
                    evidence["actual_sha256"] = canonical_sha(load_json(artifact, None))
    except (OSError, ValueError, TypeError):
        # Diagnostics must never replace the validation failure they describe.
        pass
    # Hash the identity again before using it as a filename, including malformed input.
    path = run_dir / "checkpoint-conflicts" / canonical_sha(transaction_id)[7:] / (canonical_sha(evidence)[7:] + ".json")
    try:
        atomic_json(path, evidence)
    except (OSError, ValueError, TypeError):
        pass
    return evidence


def record_failure(run_dir, state, step, exc, **kwargs):
    """One failure receives one evidence record across nested validators."""
    if not getattr(exc, "checkpoint_conflict_recorded", False):
        record_conflict(run_dir, state, step, str(exc), **kwargs)
        exc.checkpoint_conflict_recorded = True


def _conflict(run_dir, state, step, reason, *, expected=None, actual=None, hash_subject="canonical_payload"):
    exc = ValueError(reason)
    record_failure(run_dir, state, step, exc, expected=expected, actual=actual, hash_subject=hash_subject)
    raise exc


def _committed_projection(state):
    ledger = state["capability_selection"]
    return {"checkpoint_head": deepcopy(ledger.get("checkpoint_head")),
        "selected_sha256": canonical_sha(ledger["selected"]),
        "accepted_sha256": ledger["accepted_sha256"]}


def recover_commit_outcome(run_dir, state, *, verify):
    """Resolve uncertainty using a freshly loaded run and full chain verification."""
    path = run_dir / "checkpoint-commit-outcome.json"
    outcome = load_json(path, None)
    if outcome is None:
        return
    if (not isinstance(outcome, dict) or outcome.get("schema_version") != OUTCOME_SCHEMA
            or outcome.get("run_id") != state["run_id"]
            or outcome.get("status") not in {"unknown", "resolved"}):
        raise CheckpointCommitOutcomeUnknown("checkpoint_commit_outcome_unknown:invalid_recovery_evidence")
    if outcome["status"] == "resolved":
        return
    projection = _committed_projection(state)
    if projection == outcome.get("proposed"):
        recovered = "committed"
    elif projection == outcome.get("prior"):
        recovered = "not_committed"
    else:
        raise CheckpointCommitOutcomeUnknown("checkpoint_commit_outcome_unknown:pointer_conflict")
    load_checkpoint(run_dir, outcome["attempted_checkpoint"])
    verify()
    atomic_json(path, {**outcome, "status": "resolved", "outcome": recovered,
                      "observed": projection})


def enabled(state):
    strategy = state.get("checkpoint_strategy")
    if strategy is None:
        return False
    if strategy != STRATEGY or state.get("checkpoint_schema_version") != SCHEMA:
        raise ValueError("checkpoint_protocol_changed")
    return True


def checkpoint_payload(state, capability_id, index, seed, accepted, step, predecessor):
    """Use canonical proposal hashes and the exact persisted receipt file hash."""
    if type(index) is not int or index < 0:
        raise ValueError("checkpoint_identity_invalid")
    base_sha = canonical_sha(seed)
    if step["input_identity"]["base_sha256"] != base_sha:
        raise ValueError("checkpoint_stale_base")
    proposal_sha = canonical_sha(accepted)
    if step["proposal_sha256"] != proposal_sha:
        raise ValueError("checkpoint_proposal_changed")
    identity = {"schema_version": SCHEMA, "run_id": state["run_id"],
        "capability_id": capability_id, "order_index": index, "base_sha256": base_sha,
        "proposal_sha256": proposal_sha, "selection_receipt_sha256": step["receipt_sha256"]}
    selection = deepcopy(step)
    selection.pop("checkpoint", None)
    admission = step["admissions"][step["selected_candidate"]]
    return {"schema_version": SCHEMA, "transaction_id": canonical_sha(identity), "identity": identity,
        "predecessor": deepcopy(predecessor), "accepted_seed": deepcopy(seed),
        "delta": deepcopy(step["record"]["delta"]), "accepted": deepcopy(accepted),
        "selection": selection, "proof_sha256": admission["proof_sha256"],
        "source_proposal_sha256": admission["proposal_sha256"], "result_sha256": proposal_sha}


def _receipt(run_dir, step):
    if not isinstance(step.get("receipt_path"), str):
        raise ValueError("checkpoint_receipt_changed")
    receipt = repo_path(run_dir, step["receipt_path"])
    if (not receipt.is_relative_to(run_dir.resolve()) or not receipt.is_file()
            or file_sha(receipt) != step["receipt_sha256"]):
        raise ValueError("checkpoint_receipt_changed")


def load_checkpoint(run_dir, pointer):
    """An unreferenced staged payload never authorizes an accepted increment."""
    if not isinstance(pointer, dict):
        raise ValueError("checkpoint_pointer_missing")
    transaction_id = pointer.get("transaction_id", "")
    if (not isinstance(transaction_id, str) or not transaction_id.startswith("sha256:")
            or len(transaction_id) != 71
            or any(char not in "0123456789abcdef" for char in transaction_id[7:])):
        raise ValueError("checkpoint_identity_invalid")
    relative = f"capability-checkpoints/{transaction_id[7:]}/payload.json"
    if pointer.get("path") != relative:
        raise ValueError("checkpoint_path_changed")
    path = repo_path(run_dir, relative)
    if not path.is_relative_to(run_dir.resolve()):
        raise ValueError("checkpoint_path_changed")
    payload = load_json(path, None)
    if (not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA
            or payload.get("transaction_id") != transaction_id
            or canonical_sha(payload.get("identity")) != transaction_id
            or canonical_sha(payload) != pointer.get("payload_sha256")):
        raise ValueError("checkpoint_payload_changed")
    if (not {"identity", "accepted_seed", "accepted", "predecessor", "delta", "selection",
             "proof_sha256", "source_proposal_sha256", "result_sha256"} <= payload.keys()
            or not isinstance(payload["identity"], dict)
            or not {"capability_id", "order_index", "base_sha256", "run_id", "proposal_sha256",
                    "selection_receipt_sha256", "schema_version"} <= payload["identity"].keys()
            or type(payload["identity"]["order_index"]) is not int
            or payload["identity"]["order_index"] < 0):
        raise ValueError("checkpoint_payload_incomplete")
    return payload


def verify_checkpoint(run_dir, state, capability_id, index, seed, accepted, step, predecessor):
    payload, expected = None, None
    try:
        payload = load_checkpoint(run_dir, step.get("checkpoint"))
        expected = checkpoint_payload(state, capability_id, index, seed, accepted, step, predecessor)
        if canonical_sha(payload) != canonical_sha(expected):
            raise ValueError("checkpoint_selected_binding_changed")
        _receipt(run_dir, step)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        record_failure(run_dir, state, step, exc,
            expected=expected or (step.get("checkpoint") if isinstance(step, dict) else step), actual=payload)
        raise
    return payload["accepted"]


def _committed_replay(run_dir, state, payload):
    """Only selected members authorize replay; verify successors before reusing one."""
    ledger = state["capability_selection"]
    selected = ledger["selected"]
    matches = [step for step in selected if isinstance(step, dict)
               and isinstance(step.get("checkpoint"), dict)
               and step["checkpoint"].get("transaction_id") == payload["transaction_id"]]
    if not matches:
        index = payload["identity"]["order_index"]
        if 0 <= index < len(selected):
            original = selected[index]
            exc = ValueError("checkpoint_identity_conflict:occupied_order_identity_changed")
            record_failure(run_dir, state, original, exc, expected=original.get("checkpoint"),
                actual=payload["identity"], hash_subject="transaction_identity",
                actual_transaction_id=payload["transaction_id"])
            raise exc
        return None
    step = matches[0]
    if len(matches) != 1:
        _conflict(run_dir, state, step, "checkpoint_identity_conflict:duplicate_selected_transaction",
                  expected=1, actual=len(matches), hash_subject="selected_transaction_count")
    production = (state.get("checkpoint_strategy") is not None
        or state.get("generation_strategy") is not None
        or (run_dir / "analysis-input/analysis-index.json").exists()
        or tuple(part.casefold() for part in run_dir.resolve().parent.parts[-3:]) == ("logs", "ci", "mvg-planning"))
    if production:
        # Production runs have one fixed public location. Synthetic helper tests
        # deliberately omit this protocol and exercise bundle validation only.
        import plan_mvg as pm
        from _mvg_capability_selection import verified_prefix
        try:
            if not enabled(state):
                raise ValueError("checkpoint_protocol_changed")
            root = run_dir.resolve().parents[len(pm.DEFAULT_RUN_ROOT.parts)]
            if (root / pm.DEFAULT_RUN_ROOT / state["run_id"]).resolve() != run_dir.resolve():
                raise ValueError("checkpoint_run_location_changed")
            verified_prefix(root, run_dir, state)
        except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
            record_failure(run_dir, state, step, exc, expected=step.get("checkpoint"),
                actual=state.get("capability_selection"), hash_subject="selected_prefix_projection")
            raise
    predecessor, accepted = None, None
    for index, committed in enumerate(selected):
        try:
            stored = load_checkpoint(run_dir, committed.get("checkpoint"))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            record_failure(run_dir, state, committed, exc, expected=committed.get("checkpoint"))
            raise
        seed = stored["accepted_seed"] if index == 0 else accepted
        accepted = verify_checkpoint(run_dir, state, stored["identity"]["capability_id"], index,
            seed, stored["accepted"], committed, predecessor)
        predecessor = committed["checkpoint"]
    if (canonical_sha(ledger.get("checkpoint_head")) != canonical_sha(predecessor)
            or ledger.get("accepted_sha256") != canonical_sha(accepted)):
        _conflict(run_dir, state, step, "checkpoint_identity_conflict:accepted_projection_changed",
            expected={"head": predecessor, "accepted": canonical_sha(accepted)},
            actual={"head": ledger.get("checkpoint_head"), "accepted": ledger.get("accepted_sha256")},
            hash_subject="accepted_projection")
    original = load_checkpoint(run_dir, step["checkpoint"])
    if canonical_sha(original) != canonical_sha(payload):
        _conflict(run_dir, state, step, "checkpoint_identity_conflict:payload_changed",
                  expected=original, actual=payload)
    return deepcopy(step["checkpoint"])


def prepare_checkpoint(run_dir, state, capability_id, index, seed, accepted, step):
    if type(index) is not int or index < 0:
        raise ValueError("checkpoint_identity_invalid")
    ledger = state["capability_selection"]
    selected = ledger["selected"]
    # Reconstruct the historical predecessor, never the latest head, for replay.
    predecessor = selected[index - 1].get("checkpoint") if 0 < index <= len(selected) else None
    try:
        payload = checkpoint_payload(state, capability_id, index, seed, accepted, step,
            predecessor if index < len(selected) else ledger.get("checkpoint_head"))
    except (ValueError, KeyError, TypeError) as exc:
        if type(index) is int and 0 <= index < len(selected):
            record_failure(run_dir, state, selected[index], exc, expected=selected[index],
                actual={"accepted_seed": seed, "accepted": accepted, "selection": step})
        raise
    replay = _committed_replay(run_dir, state, payload)
    if replay is not None:
        return replay
    if ledger["accepted_sha256"] != canonical_sha(seed) or len(ledger["selected"]) != index:
        raise ValueError("checkpoint_stale_base")
    _receipt(run_dir, step)
    transaction_id = payload["transaction_id"]
    relative = f"capability-checkpoints/{transaction_id[7:]}/payload.json"
    path = run_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        existing = load_json(path, None)
        if canonical_sha(existing) != canonical_sha(payload):
            _conflict(run_dir, state, {**step, "checkpoint": {"transaction_id": transaction_id}},
                "checkpoint_prepared_payload_changed", expected=existing, actual=payload)
    else:
        atomic_json(path, payload)
    pointer = {"transaction_id": transaction_id, "path": relative, "payload_sha256": canonical_sha(payload)}
    load_checkpoint(run_dir, pointer)
    return pointer


def commit_checkpoint(run_dir, state, pointer, step, accepted, *, writer=atomic_json):
    """Publish a complete bundle and its selected projection in one atomic replace."""
    try:
        payload = load_checkpoint(run_dir, pointer)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        record_failure(run_dir, state, {**step, "checkpoint": pointer}, exc, expected=pointer)
        raise
    ledger = state["capability_selection"]
    disk = load_json(run_dir / "run.json", {})
    previous = disk.get("capability_selection", {})
    identity = payload["identity"]
    if disk.get("run_id") == state["run_id"] and isinstance(previous, dict):
        replay = _committed_replay(run_dir, disk, payload)
        if replay is not None:
            verify_checkpoint(run_dir, disk, identity["capability_id"], identity["order_index"],
                payload["accepted_seed"], accepted, {**step, "checkpoint": pointer}, payload["predecessor"])
            ledger.clear()
            ledger.update(deepcopy(previous))
            state.clear()
            state.update(disk)
            state["capability_selection"] = ledger
            return "no-op"
    if (disk.get("run_id") != state["run_id"]
            or canonical_sha(previous.get("selected")) != canonical_sha(ledger["selected"])
            or canonical_sha(previous.get("checkpoint_head")) != canonical_sha(payload["predecessor"])
            or previous.get("accepted_sha256") != identity["base_sha256"]
            or ledger["accepted_sha256"] != identity["base_sha256"]
            or len(ledger["selected"]) != identity["order_index"]):
        if disk.get("run_id") == state["run_id"] and isinstance(previous, dict):
            ledger.clear()
            ledger.update(deepcopy(previous))
            state.clear()
            state.update(disk)
            state["capability_selection"] = ledger
        raise ValueError("checkpoint_stale_base")
    verify_checkpoint(run_dir, state, identity["capability_id"], identity["order_index"],
        payload["accepted_seed"], accepted, {**step, "checkpoint": pointer}, payload["predecessor"])
    pending = deepcopy(state)
    committed = pending["capability_selection"]
    committed["selected"].append({**deepcopy(step), "checkpoint": deepcopy(pointer)})
    committed.update(checkpoint_head=deepcopy(pointer), accepted_sha256=canonical_sha(accepted), current=None)
    try:
        writer(run_dir / "run.json", pending)
    except BaseException as write_error:
        # A writer may raise after replace. Preserve whichever pointer reached disk.
        try:
            persisted = load_json(run_dir / "run.json", {})
            if (persisted.get("run_id") != state["run_id"]
                    or _committed_projection(persisted) not in (
                        _committed_projection(state), _committed_projection(pending))):
                raise ValueError("checkpoint_commit_pointer_unrecognized")
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as read_error:
            outcome = {"schema_version": OUTCOME_SCHEMA, "run_id": state["run_id"],
                "status": "unknown", "attempted_checkpoint": deepcopy(pointer),
                "prior": _committed_projection(state), "proposed": _committed_projection(pending),
                "write_error": {"type": type(write_error).__name__, "detail": str(write_error)[:2000]},
                "read_error": {"type": type(read_error).__name__, "detail": str(read_error)[:2000]}}
            try:
                atomic_json(run_dir / "checkpoint-commit-outcome.json", outcome)
            except (OSError, ValueError) as evidence_error:
                raise CheckpointCommitOutcomeUnknown(
                    "checkpoint_commit_outcome_unknown:recovery_evidence_write_failed:" + str(evidence_error)
                ) from read_error
            raise CheckpointCommitOutcomeUnknown("checkpoint_commit_outcome_unknown:" + str(read_error)) from read_error
        ledger.clear()
        ledger.update(persisted["capability_selection"])
        state.clear()
        state.update(persisted)
        state["capability_selection"] = ledger
        raise
    ledger.clear()
    ledger.update(committed)
    state["capability_selection"] = ledger
    return "committed"


@contextmanager
def coordinator_lock(run_dir):
    """The OS releases the Windows byte lock even after process interruption."""
    path = run_dir / "capability-coordinator.lock"
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    try:
        if os.fstat(descriptor).st_size == 0:
            os.write(descriptor, b"0")
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise ValueError("capability_coordinator_busy") from exc
        else:
            import fcntl
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                raise ValueError("capability_coordinator_busy") from exc
        acquired = True
        yield
    finally:
        if acquired and os.name == "nt":
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        os.close(descriptor)
