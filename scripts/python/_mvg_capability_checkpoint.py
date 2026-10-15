"""Stage immutable selected increments; run.json is their sole commit point."""
from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
import os

from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json, repo_path

STRATEGY = "capability-selected-checkpoint.v1"
SCHEMA = "newrouge.mvg-capability-checkpoint.v1"
OUTCOME_SCHEMA = "newrouge.mvg-checkpoint-commit-outcome.v1"


class CheckpointCommitOutcomeUnknown(RuntimeError):
    """The disk pointer must be recovered before any further run state write."""


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
    return payload


def verify_checkpoint(run_dir, state, capability_id, index, seed, accepted, step, predecessor):
    payload = load_checkpoint(run_dir, step.get("checkpoint"))
    expected = checkpoint_payload(state, capability_id, index, seed, accepted, step, predecessor)
    if payload != expected:
        raise ValueError("checkpoint_selected_binding_changed")
    _receipt(run_dir, step)
    return payload["accepted"]


def prepare_checkpoint(run_dir, state, capability_id, index, seed, accepted, step):
    ledger = state["capability_selection"]
    if ledger["accepted_sha256"] != canonical_sha(seed) or len(ledger["selected"]) != index:
        raise ValueError("checkpoint_stale_base")
    _receipt(run_dir, step)
    payload = checkpoint_payload(state, capability_id, index, seed, accepted, step, ledger.get("checkpoint_head"))
    transaction_id = payload["transaction_id"]
    relative = f"capability-checkpoints/{transaction_id[7:]}/payload.json"
    path = run_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        if load_json(path, None) != payload:
            raise ValueError("checkpoint_prepared_payload_changed")
    else:
        atomic_json(path, payload)
    pointer = {"transaction_id": transaction_id, "path": relative, "payload_sha256": canonical_sha(payload)}
    load_checkpoint(run_dir, pointer)
    return pointer


def commit_checkpoint(run_dir, state, pointer, step, accepted, *, writer=atomic_json):
    """Publish a complete bundle and its selected projection in one atomic replace."""
    payload = load_checkpoint(run_dir, pointer)
    ledger = state["capability_selection"]
    disk = load_json(run_dir / "run.json", {})
    previous = disk.get("capability_selection", {})
    identity = payload["identity"]
    if (disk.get("run_id") != state["run_id"]
            or previous.get("selected") != ledger["selected"]
            or previous.get("checkpoint_head") != payload["predecessor"]
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
