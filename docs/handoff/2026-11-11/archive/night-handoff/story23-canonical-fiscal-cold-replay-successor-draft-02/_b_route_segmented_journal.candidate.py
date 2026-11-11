"""Segmented control journal using the original registry, mutexes and run ledger.

No packet journal is a payment/admission authority. Reservations live in the
original run capability_selection.calls; auxiliary claims/journals only bind that
ledger to one exact request and conservatively retain uncertain publication.
"""
from contextlib import contextmanager, nullcontext
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from datetime import datetime, timezone

import _b_route_codec as codec
import _b_route_sources as sources
from _mvg_capability_checkpoint import coordinator_lock
import _mvg_capability_recovery as recovery
from _planning_apply_journal import create_journal, resume_journal
from _planning_skill_common import atomic_json, file_sha

SCHEMA = "newrouge.b-route-segmented-journal.v1"
CLAIM = "newrouge.b-route-segmented-claim.v1"
HEAD = "newrouge.b-route-segmented-active.v1"
TX = "newrouge.b-route-segmented-publication.v1"
_SEAL = object()
_REQUEST_FIELDS = {"protocol", "request_sha256", "plan_digest", "node_id", "phase", "input_measurement",
                   "output_reserve", "source_hashes", "schema_digest", "request_ref", "schema_ref", "timeout_sec",
                   "input_archive_ref"}
_JOURNAL_NAME = r"[0-9a-f]{24}-[0-9]{3}-(born|init|reserve|complete|fail|finalize)\.json"


class JournalBlocked(ValueError):
    pass


def require(value, reason):
    if not value:
        raise JournalBlocked("segmented_journal_blocked:" + reason)


def _core():
    import _b_route_segmented_workflow as core
    return core


def _same(left, right):
    return codec.canonical_digest(left) == codec.canonical_digest(right)


def _integer(value):
    return type(value) is int and value >= 0


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _safe(root, path):
    path = Path(path)
    require(path.is_absolute() and path.resolve().is_relative_to(root), "path_outside_original_project")
    relative = path.relative_to(root).as_posix()
    require(not any(p.casefold() in {".codex", ".aws", ".ssh", "sessions", "credentials", "archived_sessions"}
                    or p.casefold().startswith(".env") for p in Path(relative).parts), "sensitive_path_role")
    checked = sources.checked_path(root, relative)
    if checked.exists():
        info = checked.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                "reparse_topology")
        require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode) and info.st_nlink == 1, "special_or_hardlinked_file")
    return checked


def _read(root, path):
    path = _safe(root, path)
    require(path.is_file(), "missing_regular_file:" + str(path.relative_to(root)))
    return codec.strict_json_loads(path.read_bytes())


def _relative(root, path):
    return _safe(root, path).relative_to(root).as_posix()


def _original_writer(root, target, payload):
    target = _safe(root, target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.name in {"claim.json", "complete-claim.json", "birth-claim.json", "completion.json"}:
        with target.open("xb") as stream:
            stream.write(_json_bytes(payload))
            stream.flush()
            os.fsync(stream.fileno())
    else:
        atomic_json(target, payload)


def _publish_born_v1(root, run_dir, *, files, registry_after):
    """JSON-only metadata primitive for the qualified runtime under original locks.

    This creates a new namespace; it cannot retrofit an existing run, produce
    native qualification or authorize a model. The runtime owns qualification and
    original operation/run/store locking before entering this primitive.
    """
    root, run = Path(root).resolve(), Path(run_dir).resolve()
    _safe(root, run)
    require(type(files) is dict and files and run / "run.json" in files, "born_exact_json_files_required")
    if run.exists():
        children = list(run.iterdir())
        require(all(path.name == "capability-coordinator.lock" and path.is_file()
                    and path.stat().st_size == 1 and path.stat().st_nlink == 1 for path in children),
                "born_namespace_must_be_new")
    require(all(type(value) is dict for value in files.values()), "born_json_values_only")
    require(all(_safe(root, path).is_relative_to(run) for path in files), "born_file_outside_new_run")
    state = files[run / "run.json"]
    require(state.get("capability_selection", {}).get("calls") == []
            and _integer(state["capability_selection"].get("total_invocations"))
            and state["capability_selection"]["total_invocations"] == 0, "born_before_first_native_call")
    born = [value for value in files.values() if value.get("schema_version") == "newrouge.b-route-segmented-born.v1"]
    require(len(born) == 1 and born[0]["run_id"] == state["run_id"] and born[0]["initial_calls"] == 0,
            "born_original_zero_archive")
    require(any(Path(path).name in {"claim.json", "birth-claim.json"} for path in files), "born_permanent_claim_required")
    store = recovery.store_root(root, state)
    require(store == root / "logs/ci/mvg-recovery", "born_original_registry")
    registry_path = store / "registry.json"
    before = _read(root, registry_path)
    require(all(_same(value, registry_after.get(key)) for key, value in before.items() if key != "segmented_runs")
            and set(registry_after) == set(before) | {"segmented_runs"}, "born_cannot_change_legacy_registry")
    index = registry_after["segmented_runs"]
    previous = before.get("segmented_runs", {"runs": []})
    require(type(index) is dict and index.get("schema_version") == "newrouge.b-route-segmented-run-index.v1"
            and index.get("campaign") == "story25" and type(index.get("runs")) is list
            and len(index["runs"]) == len(previous["runs"]) + 1
            and _same(index["runs"][:-1], previous["runs"])
            and index["runs"][-1]["run_path"] == _relative(root, run / "run.json"), "born_index_append_only")
    journals = store / "activity/segmented-journals"
    if journals.exists():
        for path in journals.iterdir():
            require(path.is_file() and re.fullmatch(_JOURNAL_NAME, path.name), "born_unknown_shared_publication")
            require(_read(root, path).get("status") == "complete", "born_pending_publication_blocks_new_run")
    stem = hashlib.sha256((str(run) + "\0" + born[0]["plan_digest"]).encode()).hexdigest()[:24]
    path = journals / (stem + "-000-born.json")
    require(not os.path.lexists(path), "born_publication_already_claimed")
    path.parent.mkdir(parents=True, exist_ok=True)
    targets = dict(files)
    targets[registry_path] = registry_after
    metadata = {"schema_version": TX, "protocol": born[0]["protocol"], "plan_digest": born[0]["plan_digest"],
                "run_id": state["run_id"], "run_path": _relative(root, run / "run.json"), "verb": "born",
                "node_id": None, "result": {"born": True, "model_calls": 0}}
    create_journal(root, path, targets, {}, metadata)
    resume_journal(root, path, lambda target, payload: _original_writer(root, target, payload))
    return {"journal_ref": _relative(root, path), "model_calls": 0, "native_qualified": False}

def publish_born(root, run_dir, *, files, registry_after):
    state = files.get(Path(run_dir).resolve() / 'run.json') if type(files) is dict else None
    if type(state) is dict and state.get('schema_version') == 'newrouge.b-route-segmented-planning-run.fiscal-v2':
        return _publish_born_fiscal(root, run_dir, files=files, registry_after=registry_after)
    require(not (type(files) is dict and any(type(v) is dict and (
            v.get('schema_version') == 'newrouge.b-route-segmented-born.fiscal-v2'
            or 'segmented_fiscal_claim' in v) for v in files.values())), 'born_mixed_financial_family')
    return _publish_born_v1(root, run_dir, files=files, registry_after=registry_after)


def _publish_born_fiscal(root, run_dir, *, files, registry_after):
    """JSON-only metadata primitive for the qualified runtime under original locks.

    This creates a new namespace; it cannot retrofit an existing run, produce
    native qualification or authorize a model. The runtime owns qualification and
    original operation/run/store locking before entering this primitive.
    """
    root, run = Path(root).resolve(), Path(run_dir).resolve()
    _safe(root, run)
    require(type(files) is dict and files and run / "run.json" in files, "born_exact_json_files_required")
    if run.exists():
        children = list(run.iterdir())
        require(all(path.name == "capability-coordinator.lock" and path.is_file()
                    and path.stat().st_size == 1 and path.stat().st_nlink == 1 for path in children),
                "born_namespace_must_be_new")
    require(all(type(value) is dict for value in files.values()), "born_json_values_only")
    require(all(_safe(root, path).is_relative_to(run) for path in files), "born_file_outside_new_run")
    state = files[run / "run.json"]
    require(state.get("capability_selection", {}).get("calls") == []
            and _integer(state["capability_selection"].get("total_invocations"))
            and state["capability_selection"]["total_invocations"] == 0, "born_before_first_native_call")
    born = [value for value in files.values() if value.get("schema_version") == "newrouge.b-route-segmented-born.fiscal-v2"]
    require(len(born) == 1 and born[0]["run_id"] == state["run_id"] and born[0]["initial_calls"] == 0,
            "born_original_zero_archive")
    require(state.get('schema_version') == 'newrouge.b-route-segmented-planning-run.fiscal-v2'
            and all(v.get('schema_version') != 'newrouge.b-route-segmented-born.v1' for v in files.values()),
            'born_financial_state_family')
    initial_path = run / 'b/initial-run.json'
    require(initial_path in files
            and files[initial_path].get('schema_version') == state['schema_version']
            and born[0]['initial_run_ref']['schema_version'] == state['schema_version']
            and born[0]['initial_run_ref']['path'] == _relative(root, initial_path)
            and born[0]['segmented_fiscal_claim'] == files[initial_path]['segmented_fiscal_claim']
            == state['segmented_fiscal_claim'], 'born_financial_initial_same_family')
    require(any(Path(path).name in {"claim.json", "birth-claim.json"} for path in files), "born_permanent_claim_required")
    store = recovery.store_root(root, state)
    require(store == root / "logs/ci/mvg-recovery", "born_original_registry")
    registry_path = store / "registry.json"
    before = _read(root, registry_path)
    require(all(_same(value, registry_after.get(key)) for key, value in before.items() if key != "segmented_runs")
            and set(registry_after) == set(before) | {"segmented_runs"}, "born_cannot_change_legacy_registry")
    index = registry_after["segmented_runs"]
    previous = before.get("segmented_runs", {"runs": []})
    require(type(index) is dict and index.get("schema_version") == "newrouge.b-route-segmented-run-index.v1"
            and index.get("campaign") == "story25" and type(index.get("runs")) is list
            and len(index["runs"]) == len(previous["runs"]) + 1
            and _same(index["runs"][:-1], previous["runs"])
            and index["runs"][-1]["run_path"] == _relative(root, run / "run.json"), "born_index_append_only")
    journals = store / "activity/segmented-journals"
    if journals.exists():
        for path in journals.iterdir():
            require(path.is_file() and re.fullmatch(_JOURNAL_NAME, path.name), "born_unknown_shared_publication")
            require(_read(root, path).get("status") == "complete", "born_pending_publication_blocks_new_run")
    stem = hashlib.sha256((str(run) + "\0" + born[0]["plan_digest"]).encode()).hexdigest()[:24]
    path = journals / (stem + "-000-born.json")
    require(not os.path.lexists(path), "born_publication_already_claimed")
    path.parent.mkdir(parents=True, exist_ok=True)
    targets = dict(files)
    targets[registry_path] = registry_after
    metadata = {"schema_version": TX, "protocol": born[0]["protocol"], "plan_digest": born[0]["plan_digest"],
                "run_id": state["run_id"], "run_path": _relative(root, run / "run.json"), "verb": "born",
                "node_id": None, "result": {"born": True, "model_calls": 0}}
    create_journal(root, path, targets, {}, metadata)
    resume_journal(root, path, lambda target, payload: _original_writer(root, target, payload))
    return {"journal_ref": _relative(root, path), "model_calls": 0, "native_qualified": False}


def resume_born(root, run_dir, *, journal_ref):
    """Same original known birth transaction under runtime-owned original locks."""
    root, run = Path(root).resolve(), Path(run_dir).resolve()
    path = _safe(root, root / journal_ref)
    require(path.parent == root / "logs/ci/mvg-recovery/activity/segmented-journals", "born_original_journal_namespace")
    value = _read(root, path)
    metadata = value.get("result", {})
    require(metadata.get("schema_version") == TX and metadata.get("verb") == "born"
            and metadata.get("run_path") == _relative(root, run / "run.json"), "not_original_born_transaction")
    registry = root / "logs/ci/mvg-recovery/registry.json"
    require(len({row["path"] for row in value["entries"]}) == len(value["entries"])
            and all(_safe(root, root / row["path"]) == registry or _safe(root, root / row["path"]).is_relative_to(run)
                    for row in value["entries"]), "born_transaction_target_scope")
    for row in value["entries"]:
        require(row.get("mutable_json_keys_after_complete", []) == [], "born_mutability_mask")
        if row["path"] == _relative(root, run / "run.json"):
            require(row["payload"]["capability_selection"]["calls"] == []
                    and row["payload"]["capability_selection"]["total_invocations"] == 0, "born_cannot_restore_paid_run")
    result = resume_journal(root, path, lambda target, payload: _original_writer(root, target, payload))
    return {"publication": result, "model_calls": 0, "native_qualified": False}


def _ledger_budget(state, plan, witness):
    """Read the original authority; never an auxiliary counter or a fresh quota."""
    ledger = state["capability_selection"]
    calls = ledger["calls"]
    require(type(calls) is list and _integer(ledger["total_invocations"])
            and ledger["total_invocations"] == len(calls), "native_ledger_counter")
    for number, row in enumerate(calls, 1):
        require(type(row) is dict and type(row.get("number")) is int and row["number"] == number
                and row.get("reservation_id") == plan["run_id"] + ":dispatch:" + str(number), "native_reservation_sequence")
        identity = row.get("request_identity", {})
        require(identity.get("protocol") == plan["protocol"] and identity.get("plan_digest") == plan["plan_digest"]
                and number <= len(plan["nodes"]) and identity.get("node_id") == plan["nodes"][number - 1]["node_id"],
                "native_packet_order_or_mixed_plan")
        node = plan["nodes"][number - 1]
        mapping = witness["candidate_lineages"]
        require(all(label in mapping for label in node["candidate_labels"]), "original_lineage_mapping_missing")
        charged = [] if node["phase"] == "selection" else sorted({mapping[label] for label in node["candidate_labels"]})
        require(row.get("phase") == node["phase"] and identity.get("phase") == node["phase"]
                and row.get("candidate_labels") == node["candidate_labels"] and row.get("lineage_ids") == charged
                and row.get("candidate") == (charged[0] if len(charged) == 1 else None), "native_lineage_charge_changed")
    funding = witness["funding"]
    declared = state["b_route_campaign_funding"]
    for key in ("paid_or_unknown_before_run", "campaign_limit", "subsequent_full_reservation",
                "maximum_native_charges", "released", "retained_profile_calls"):
        require(_integer(funding.get(key)), "native_funding_integer:" + key)
    require(funding["campaign_limit"] == 290 and funding["released"] == 0, "campaign_liability_or_refund")
    require(type(declared) is dict and all(_integer(declared.get(key)) for key in
            ("paid_or_unknown_before_run", "campaign_limit", "subsequent_full_reservation", "maximum_native_charges", "released"))
            and declared["campaign_limit"] == 290 and declared["released"] == 0
            and funding["paid_or_unknown_before_run"] >= declared["paid_or_unknown_before_run"]
            and funding["retained_profile_calls"] >= declared.get("retained_profile_calls", 0),
            "original_declared_funding_cannot_be_released")
    limit = 96 if plan["planner"] == "capability" else 192
    require(type(witness["native_limit"]) is int and witness["native_limit"] == plan["budget"]["native_limit"] == limit
            and type(state["mvg.run_invocation_limit"]) is int and state["mvg.run_invocation_limit"] == limit,
            "original_profile_limit")
    costs = ledger["lineage_invocations"]
    expected = {candidate: sum(candidate in row.get("lineage_ids", [row.get("candidate")]) for row in calls)
                for candidate in set(witness["candidate_lineages"].values())}
    require(type(costs) is dict and _same(costs, expected)
            and all(type(v) is int and 0 <= v <= 64 for v in costs.values()), "original_lineage_counter")
    retained_lineages = funding.get("retained_lineage_calls")
    require(type(retained_lineages) is dict and all(type(k) is str and _integer(v) for k, v in retained_lineages.items()),
            "retained_lineage_charge_evidence_required")
    for lineage, count in costs.items():
        future = sum(node["phase"] != "selection" and lineage in
                     {witness["candidate_lineages"][label] for label in node["candidate_labels"]}
                     for node in plan["nodes"][len(calls):])
        require(retained_lineages.get(lineage, 0) + count + future <= 64, "cannot_fund_original_lineage_plan")
    remaining = min(limit - funding["retained_profile_calls"] - len(calls),
                    funding["maximum_native_charges"] - len(calls),
                    declared["maximum_native_charges"] - len(calls),
                    290 - funding["paid_or_unknown_before_run"] - len(calls) - funding["subsequent_full_reservation"],
                    290 - declared["paid_or_unknown_before_run"] - len(calls) - declared["subsequent_full_reservation"])
    require(remaining >= 0, "original_budget_exhausted")
    return {"native_reserved_calls": len(calls), "retained_profile_calls": funding["retained_profile_calls"],
            "campaign_paid_or_unknown": funding["paid_or_unknown_before_run"] + len(calls),
            "remaining_reservable_calls": remaining, "released": 0}


def inspect_native_history(root, run_dir, state):
    """Original journal/claim to native-row linkage, not qualification.

    Runtime funding may call this pure reader without core/session recursion.
    A pending original transaction may be before or after its native write; it is
    reported as an encumbrance and never dispatch permission or a refunded slot.
    """
    root, run = Path(root).resolve(), Path(run_dir).resolve()
    require(_same(_read(root, run / "run.json"), state), "native_history_not_live_state")
    store = recovery.store_root(root, state)
    require(store == root / "logs/ci/mvg-recovery", "native_history_original_registry")
    directory = store / "activity/segmented-journals"
    calls = state["capability_selection"]["calls"]
    owned, pending, pending_views = [], [], []
    if directory.exists():
        for path in sorted(directory.iterdir()):
            require(path.is_file() and re.fullmatch(_JOURNAL_NAME, path.name),
                    "unknown_shared_journal_member")
            journal = _read(root, path)
            require(journal.get("schema_version") == "newrouge.planning-apply-journal.v1"
                    and journal.get("status") in {"pending", "complete"}, "native_history_original_journal")
            metadata = journal.get("result", {})
            require(metadata.get("schema_version") == TX, "native_history_foreign_journal")
            if journal["status"] == "pending":
                pending.append({"journal_ref": _relative(root, path), "run_id": metadata["run_id"],
                                "node_id": metadata["node_id"], "verb": metadata["verb"], "may_redispatch": False})
            if metadata.get("run_path") == _relative(root, run / "run.json"):
                require(metadata["run_id"] == state["run_id"], "native_history_run_mix")
                for row in journal["entries"]:
                    require(codec.raw_digest(_json_bytes(row["payload"])) == row["after_sha256"], "native_history_target_digest")
                    if journal["status"] == "pending" and row["path"] == _relative(root, run / "run.json"):
                        actual_raw = file_sha(_safe(root, run / "run.json"))
                        require(actual_raw in {row["before_sha256"], row["after_sha256"]}, "pending_native_not_original_before_or_after")
                        pending_views.append({"journal_ref": _relative(root, path), "before_digest": row["before_sha256"],
                            "after_digest": row["after_sha256"], "actual_relation": "after" if actual_raw == row["after_sha256"] else "before",
                            "target_path": row["path"]})
                owned.append((path, journal))
    require(len(pending) <= 1, "multiple_active_native_publications")
    reservations = {}
    completed, pending_completed, completions = {}, {}, []
    for path, journal in owned:
        metadata = journal["result"]
        if metadata["verb"] not in {"reserve", "complete"}:
            continue
        targets = [e for e in journal["entries"] if e["path"] == _relative(root, run / "run.json")]
        require(len(targets) == 1, "native_history_missing_ledger_target")
        after = targets[0]["payload"]["capability_selection"]["calls"]
        if metadata["verb"] == "reserve":
            require(bool(after), "native_history_empty_reservation")
            row = after[-1]
            number = row["number"]
            require(type(number) is int and number == len(after)
                    and row["request_identity"]["node_id"] == metadata["node_id"]
                    and row["request_identity"]["plan_digest"] == metadata["plan_digest"], "native_history_reservation_binding")
            require(number not in reservations, "duplicate_native_reserve_journal")
            claims = [e for e in journal["entries"] if Path(e["path"]).name == "claim.json"]
            require(len(claims) == 1 and _same(claims[0]["payload"]["reservation"], row), "native_history_permanent_claim_target")
            require(claims[0]["payload"].get("native_after_digest") == targets[0]["after_sha256"]
                    and claims[0]["payload"].get("journal_ref") == _relative(root, path), "native_history_claim_after")
            if journal["status"] == "complete" or len(calls) >= number:
                require(file_sha(_safe(root, root / claims[0]["path"])) == claims[0]["after_sha256"],
                        "native_history_claim_removed_or_changed")
            if journal["status"] == "complete":
                require(len(calls) >= number, "native_history_paid_prefix_rollback")
            reservations[number] = {"row": row, "journal_ref": _relative(root, path), "status": journal["status"],
                                    "claim_ref": claims[0]["path"], "claim_raw_digest": claims[0]["after_sha256"],
                                    "run_after_digest": targets[0]["after_sha256"]}
        else:
            matches = [row for row in after if row["request_identity"]["node_id"] == metadata["node_id"]]
            require(len(matches) == 1 and matches[0].get("outcome", {}).get("status") == "completed", "native_history_completed_binding")
            destination = completed if journal["status"] == "complete" else pending_completed
            require(matches[0]["number"] not in destination, "duplicate_native_complete_journal")
            destination[matches[0]["number"]] = matches[0]
            claims = [e for e in journal["entries"] if Path(e["path"]).name == "complete-claim.json"]
            require(len(claims) == 1 and claims[0]["payload"].get("native_after_digest") == targets[0]["after_sha256"]
                    and claims[0]["payload"].get("journal_ref") == _relative(root, path)
                    and claims[0]["payload"].get("reservation_id") == matches[0]["reservation_id"]
                    and claims[0]["payload"].get("result_digest") == matches[0]["outcome"]["segmented_result_digest"],
                    "native_history_complete_claim_binding")
            if journal["status"] == "complete":
                require(file_sha(_safe(root, root / claims[0]["path"])) == claims[0]["after_sha256"],
                        "native_history_complete_claim_changed")
            completions.append({"journal_ref": _relative(root, path), "status": journal["status"],
                "claim_ref": claims[0]["path"], "claim_raw_digest": claims[0]["after_sha256"],
                "run_after_digest": targets[0]["after_sha256"], "reservation_id": matches[0]["reservation_id"]})
    for number, actual in enumerate(calls, 1):
        require(number in reservations and actual["number"] == number, "unclaimed_native_row")
        expected = completed.get(number, reservations[number]["row"])
        require(_same(actual, expected) or number in pending_completed and _same(actual, pending_completed[number]),
                "native_history_row_or_outcome_rollback")
    return {"native_reserved_calls": len(calls), "charged_or_pending_calls": max([len(calls), *reservations.keys()]),
            "reservations": [deepcopy(reservations[n]) for n in sorted(reservations)],
            "completions": completions, "pending_native_views": pending_views,
            "pending_publications": pending, "released": 0, "native_qualified": False}


def inspect_reservation_metadata(root, run_dir, *, plan, node, reservation):
    """Pure paid-row linkage for the runtime gate; never result replay/dispatch.

    The runtime still owns actual birth/current source/epoch/index qualification.
    A reserved/unknown row is an encumbrance, not a completed model result.
    """
    root, run = Path(root).resolve(), Path(run_dir).resolve()
    require(type(node) is dict and type(node.get("ordinal")) is int
            and 0 <= node["ordinal"] < len(plan["nodes"])
            and _same(plan["nodes"][node["ordinal"]], node), "paid_node_not_exact_plan")
    require(type(reservation) is dict, "paid_reservation_object_required")
    state_path = _safe(root, run / "run.json")
    initial_state_raw = state_path.read_bytes()
    original_state = codec.strict_json_loads(initial_state_raw)
    aux_path = _safe(root, run / "q/state.json")
    claim_path = _safe(root, run / "q" / ("n" + str(node["ordinal"])) / "claim.json")
    head_path = _safe(root, recovery.store_root(root, original_state) / "activity/segmented-active.json")
    paths = (state_path, aux_path, claim_path, head_path)
    pins = {path: path.read_bytes() for path in paths}
    require(pins[state_path] == initial_state_raw, "paid_original_store_changed_during_read")
    state, auxiliary, claim, head = (codec.strict_json_loads(pins[path]) for path in paths)
    require(state["run_id"] == plan["run_id"], "paid_original_run_identity")
    history = inspect_native_history(root, run, state)
    require(not history["pending_publications"], "paid_publication_not_closed")
    records = [row for row in history["reservations"] if row["row"].get("reservation_id") == reservation.get("reservation_id")]
    require(len(records) == 1 and records[0]["status"] == "complete"
            and _same(records[0]["row"], reservation), "paid_original_reservation_required")
    record = records[0]
    claim_ref = {"path": _relative(root, claim_path), "schema_version": CLAIM, "raw_digest": codec.raw_digest(pins[claim_path])}
    require(record["claim_ref"] == claim_ref["path"] and record["claim_raw_digest"] == claim_ref["raw_digest"]
            and claim.get("schema_version") == CLAIM and claim.get("protocol") == plan["protocol"]
            and claim.get("plan_digest") == plan["plan_digest"] and _same(claim["node"], node)
            and _same(claim["reservation"], reservation), "paid_permanent_claim_binding")
    require(auxiliary.get("schema_version") == SCHEMA and auxiliary.get("protocol") == plan["protocol"]
            and auxiliary.get("plan_digest") == plan["plan_digest"] and auxiliary.get("run_id") == plan["run_id"],
            "paid_original_auxiliary_identity")
    entry = auxiliary["nodes"].get(node["node_id"])
    require(type(entry) is dict and entry.get("status") in {"unknown", "completed"}
            and entry.get("claim_ref") == claim_ref["path"] and _same(entry.get("reservation"), reservation),
            "paid_original_auxiliary_reservation")
    rows = [row for row in state["capability_selection"]["calls"] if row.get("reservation_id") == reservation.get("reservation_id")]
    require(len(rows) == 1, "paid_actual_native_row_required")
    if entry["status"] == "completed":
        require(rows[0].get("outcome", {}).get("status") == "completed"
                and rows[0]["outcome"].get("segmented_result_digest") == entry.get("result_digest"),
                "paid_completed_auxiliary_not_native_outcome")
    else:
        require("outcome" not in rows[0], "paid_unknown_auxiliary_not_closed_outcome")
    require(head.get("schema_version") == HEAD and head.get("status") in {"active", "settled"}, "paid_actual_head_shape")
    workspace = str(_safe(root, claim_path.parent / "m"))
    require(reservation.get("workspace") == workspace and reservation.get("phase") == node["phase"]
            and reservation.get("request_identity", {}).get("node_id") == node["node_id"], "paid_original_workspace_node")
    require(all(_safe(root, path).read_bytes() == raw for path, raw in pins.items()), "paid_metadata_changed_during_read")
    return {"run_ref": _relative(root, state_path), "run_raw_digest": codec.raw_digest(pins[state_path]),
        "original_reservation": deepcopy(record["row"]), "actual_row": deepcopy(rows[0]), "claim_ref": claim_ref,
        "claim": deepcopy(claim), "aux_ref": {"path": _relative(root, aux_path), "schema_version": SCHEMA,
            "raw_digest": codec.raw_digest(pins[aux_path])}, "aux_node": deepcopy(entry), "workspace": workspace,
        "head_ref": {"path": _relative(root, head_path), "schema_version": HEAD, "raw_digest": codec.raw_digest(pins[head_path])},
        "head": deepcopy(head), "history": history}


class _Session:
    def __init__(self, seal, root, run_dir, plan, witness):
        require(seal is _SEAL, "original_lock_session_required")
        self._seal, self.root, self.run, self.plan = seal, root, run_dir, deepcopy(plan)
        self.store = Path(witness["registry_store"])
        self.activity = self.store / "activity"
        self.journals = self.activity / "segmented-journals"
        self.head = self.activity / "segmented-active.json"
        self.aux = self.run / "q/state.json"
        self.plan_path = self.run / "q/plan.json"
        self._closed = False
        self._read_only = False
        self._prefixes = {}

    def _live(self):
        require(self._seal is _SEAL and not self._closed, "closed_session")

    def _writable(self):
        self._live()
        require(not self._read_only, "read_only_session")

    def _fresh(self):
        self._live()
        state = _read(self.root, self.run / "run.json")
        witness = _core().require_segmented_run(self.root, self.run, state, self.plan)
        require(Path(witness["registry_store"]) == self.store, "original_registry_store_changed")
        require(recovery.store_root(self.root, state) == self.store, "parallel_registry_forbidden")
        with (nullcontext() if self._read_only else coordinator_lock(self.store)):
            actual = recovery.registry(self.root, state)
            recovery.assert_epoch(self.root, state, value=actual)
            require(actual["epoch"] == witness["registry_epoch"], "original_registry_epoch_changed")
        return state, witness, _ledger_budget(state, self.plan, witness)

    def _node(self, node):
        require(type(node) is dict and type(node.get("ordinal")) is int
                and 0 <= node["ordinal"] < len(self.plan["nodes"]), "node_ordinal")
        exact = self.plan["nodes"][node["ordinal"]]
        require(_same(node, exact), "node_identity_or_order_changed")
        return exact

    def _workspace(self, node):
        return _safe(self.root, self.run / "q" / ("n" + str(node["ordinal"])) / "m")

    def _pending(self):
        if not self.journals.exists():
            return []
        pending = []
        for path in sorted(self.journals.iterdir()):
            require(path.is_file() and re.fullmatch(_JOURNAL_NAME, path.name),
                    "unknown_shared_publication_file")
            value = _read(self.root, path)
            require(value.get("schema_version") == "newrouge.planning-apply-journal.v1"
                    and value.get("status") in {"pending", "complete"}, "original_publication_journal_shape")
            result = value.get("result", {})
            require(result.get("schema_version") == TX, "foreign_parallel_journal")
            if value["status"] == "pending":
                pending.append((path, value))
        require(len(pending) <= 1, "concurrent_shared_pending_claims")
        return pending

    def _head(self):
        if not self.head.exists():
            return None
        value = _read(self.root, self.head)
        require(type(value) is dict and value.get("schema_version") == HEAD
                and value.get("status") in {"active", "settled"}, "active_head_shape")
        return value

    def _auxiliary(self):
        value = _read(self.root, self.aux)
        require(type(value) is dict and set(value) == {"schema_version", "protocol", "plan_digest", "run_id",
                "nodes", "completed_order", "blocked"} and value["schema_version"] == SCHEMA
                and value["protocol"] == self.plan["protocol"] and value["plan_digest"] == self.plan["plan_digest"]
                and value["run_id"] == self.plan["run_id"] and type(value["nodes"]) is dict, "auxiliary_identity")
        return value

    def _publication_path(self, verb, node):
        ordinal = 0 if node is None else node["ordinal"]
        stem = hashlib.sha256((str(self.run) + "\0" + self.plan["plan_digest"]).encode()).hexdigest()[:24]
        return self.journals / f"{stem}-{ordinal:03d}-{verb}.json"

    def _transaction(self, verb, node, targets, result, *, witness):
        self._writable()
        require(not self._pending(), "pending_publication_requires_resume")
        path = self._publication_path(verb, node)
        require(not os.path.lexists(path), "publication_already_consumed")
        path.parent.mkdir(parents=True, exist_ok=True)
        for target in targets:
            _safe(self.root, target)
        authority = {witness["born_ref"]["path"]: witness["born_ref"]["raw_digest"]}
        value = {"schema_version": TX, "protocol": self.plan["protocol"], "plan_digest": self.plan["plan_digest"],
                 "run_id": self.plan["run_id"], "run_path": _relative(self.root, self.run / "run.json"),
                 "verb": verb, "node_id": None if node is None else node["node_id"], "result": result}
        # The existing store mutex is short and never spans rendering/model IO.
        with coordinator_lock(self.store):
            actual = recovery.registry(self.root, _read(self.root, self.run / "run.json"))
            require(actual["epoch"] == witness["registry_epoch"], "publication_registry_epoch_changed")
            if verb in {"reserve", "complete"}:
                import _b_route_segmented_runtime as runtime
                claim_path = self._workspace(node).parent / ("claim.json" if verb == "reserve" else "complete-claim.json")
                native_after = codec.raw_digest(_json_bytes(targets[self.run / "run.json"]))
                require(targets[claim_path]["native_after_digest"] == native_after
                        and targets[claim_path]["journal_ref"] == _relative(self.root, path), "publication_claim_after_binding")
                targets = dict(targets)
                targets[self.store / "registry.json"] = runtime.with_ledger_head(self.root, actual, self.run,
                    self.plan, witness, journal_ref=_relative(self.root, path),
                    claim_ref=_relative(self.root, claim_path), claim_raw_digest=codec.raw_digest(_json_bytes(targets[claim_path])),
                    run_after_digest=native_after)
            create_journal(self.root, path, targets, authority, value)
            self._resume_one(path)
        return result

    def _journal_targets(self, verb, node):
        base = {self.aux}
        if verb == "finalize":
            return {self.run / "q/completion.json"}
        if verb == "init":
            return base | {self.plan_path}
        workspace = self._workspace(node)
        if verb == "reserve":
            return base | {self.head, workspace.parent / "claim.json", self.run / "run.json", self.store / "registry.json"}
        if verb == "complete":
            return base | {self.head, workspace.parent / "result.json", workspace.parent / "complete-claim.json",
                           self.run / "run.json", self.store / "registry.json"}
        require(verb == "fail", "unknown_publication_verb")
        return base | {self.head, workspace.parent / "failure.json"}

    def _resume_one(self, path):
        journal = _read(self.root, path)
        metadata = journal.get("result", {})
        require(metadata.get("schema_version") == TX and metadata.get("plan_digest") == self.plan["plan_digest"]
                and metadata.get("run_id") == self.plan["run_id"]
                and metadata.get("run_path") == _relative(self.root, self.run / "run.json"), "foreign_pending_publication")
        verb = metadata["verb"]
        node = None if verb in {"init", "finalize"} else next((n for n in self.plan["nodes"] if n["node_id"] == metadata["node_id"]), None)
        require(verb in {"init", "finalize"} or node is not None, "pending_node_not_in_plan")
        expected = self._journal_targets(verb, node)
        actual = {_safe(self.root, self.root / row["path"]) for row in journal["entries"]}
        require(actual == expected and len(actual) == len(journal["entries"]), "pending_target_domain_changed")
        require(all(row.get("mutable_json_keys_after_complete", []) == [] for row in journal["entries"]),
                "generic_mutability_mask_forbidden")
        for reference, digest in journal["authority_inputs"].items():
            require(file_sha(_safe(self.root, self.root / reference)) == digest, "pending_exact_authority_changed")
        def writer(target, payload):
            _safe(self.root, target)
            target.parent.mkdir(parents=True, exist_ok=True)
            _original_writer(self.root, target, payload)
        return resume_journal(self.root, path, writer)

    def resume(self):
        """Roll forward the original metadata transaction; never dispatch again."""
        self._writable()
        self._fresh()
        with coordinator_lock(self.store):
            for path, _value in self._pending():
                self._resume_one(path)
        return self.snapshot()

    def _initialize(self):
        state, witness, budget = self._fresh()
        pending = self._pending()
        if pending:
            metadata = pending[0][1]["result"]
            require(metadata["run_id"] == self.plan["run_id"] and metadata["plan_digest"] == self.plan["plan_digest"],
                    "another_original_publication_pending")
            return  # Only snapshot/resume is useful; no second intent is created.
        head = self._head()
        require(head is None or head["status"] == "settled" or head["run_id"] == self.plan["run_id"]
                and head["plan_digest"] == self.plan["plan_digest"], "another_original_claim_active")
        remaining_nodes = len(self.plan["nodes"]) - len(state["capability_selection"]["calls"])
        require(remaining_nodes <= budget["remaining_reservable_calls"], "cannot_fund_complete_original_plan")
        if self.aux.exists():
            require(_same(_read(self.root, self.plan_path), self.plan), "persisted_plan_changed")
            self._auxiliary()
            return
        require(not os.path.lexists(self.plan_path), "partial_auxiliary_initialization")
        require(state["capability_selection"]["calls"] == [], "new_auxiliary_cannot_erase_paid_prefix")
        initial = {"schema_version": SCHEMA, "protocol": self.plan["protocol"], "plan_digest": self.plan["plan_digest"],
                   "run_id": self.plan["run_id"], "nodes": {}, "completed_order": [], "blocked": None}
        self._transaction("init", None, {self.plan_path: self.plan, self.aux: initial}, {"initialized": True}, witness=witness)

    def workspace(self, node):
        self._writable()
        state, _witness, _budget = self._fresh()
        node = self._node(node)
        self._ready_metadata(state, node)
        path = self._workspace(node)
        require(not os.path.lexists(path.parent / "claim.json"), "node_claim_already_consumed")
        require(not os.path.lexists(path), "model_workspace_must_be_fresh")
        path.parent.mkdir(parents=True, exist_ok=True)  # Renderer alone creates the exact final three-file sandbox.
        return path

    def _ready_metadata(self, state, node):
        require(not self._pending(), "pending_publication_requires_resume")
        auxiliary, head = self._auxiliary(), self._head()
        require(auxiliary["blocked"] is None and (head is None or head["status"] == "settled"), "unknown_original_claim_blocks_next_node")
        require(auxiliary["completed_order"] == [n["node_id"] for n in self.plan["nodes"][:node["ordinal"]]]
                and len(state["capability_selection"]["calls"]) == node["ordinal"], "not_next_original_node")
        return auxiliary

    def timeout(self, node):
        state, witness, _budget = self._fresh()
        node = self._node(node)
        import _b_route_segmented_runtime as runtime
        owner = getattr(runtime, "request_timeout", None)
        if not callable(owner):
            raise _core().DependencyUnavailable("segmented_native_timeout_owner_unavailable")
        value = owner(self.root, self.run, state, self.plan, node, witness)
        require(type(value) is int and value >= 1, "native_time_budget_unavailable")
        return value

    def snapshot(self):
        state, _witness, budget = self._fresh()
        paths = [self.run / "run.json", self.aux, self.plan_path, self.head, self.store / "registry.json"]
        before = {path: path.read_bytes() if path.is_file() else None for path in paths}
        journal_members = sorted(path.name for path in self.journals.iterdir()) if self.journals.exists() else []
        pending = self._pending()
        if pending:
            return {"completed": [], "blocked": {"reason": "pending_original_publication", "journal":
                    _relative(self.root, pending[0][0]), "may_redispatch": False}, "budget": budget}
        auxiliary = self._auxiliary()
        require(type(auxiliary["completed_order"]) is list
                and auxiliary["completed_order"] == [n["node_id"] for n in self.plan["nodes"][:len(auxiliary["completed_order"])]],
                "completed_prefix_order")
        completed = []
        for node in self.plan["nodes"][:len(auxiliary["completed_order"])]:
            entry = auxiliary["nodes"][node["node_id"]]
            require(entry["status"] == "completed", "completed_status_changed")
            stored = _read(self.root, self.root / entry["result_ref"])
            require(file_sha(_safe(self.root, self.root / entry["result_ref"])) == entry["stored_raw_digest"]
                    and stored["result_digest"] == entry["result_digest"], "completed_result_changed")
            token = _core().replay_verified_result(self.root, self.plan, node, entry["reservation"], stored)
            value = _core().validate_verified_result(self.plan, node, entry["reservation"], token)
            completed.append({"node_id": node["node_id"], "reservation": deepcopy(entry["reservation"]),
                              "result": value, "verified_result": token})
        head = self._head()
        blocked = deepcopy(auxiliary["blocked"])
        if head is not None and head["status"] == "active":
            blocked = {"reason": "original_request_unknown_or_active", "run_id": head["run_id"],
                       "reservation_id": head["reservation_id"], "may_redispatch": False}
        require(len(completed) <= len(state["capability_selection"]["calls"]), "unpaid_completed_packet")
        self._fresh()
        require(all((path.read_bytes() if path.is_file() else None) == raw for path, raw in before.items())
                and (sorted(path.name for path in self.journals.iterdir()) if self.journals.exists() else []) == journal_members,
                "snapshot_concurrent_metadata_changed")
        return {"completed": completed, "blocked": blocked, "budget": budget}

    def reserve(self, node, request_identity, *, rendered_request, completed_prefix):
        self._writable()
        state, witness, budget = self._fresh()
        node = self._node(node)
        auxiliary = self._ready_metadata(state, node)
        prefix = _core().verify_completed_prefix(self.root, self.plan, completed_prefix)
        require(list(prefix) == auxiliary["completed_order"], "genuine_prefix_order_changed")
        for parent, value in prefix.items():
            stored = auxiliary["nodes"][parent]
            require(stored["result_digest"] == value["result_digest"]
                    and _same(stored["reservation"], value["reservation"]), "genuine_prefix_not_original_journal")
        require(type(request_identity) is dict and set(request_identity) == _REQUEST_FIELDS, "actual_request_identity_shape")
        archive = request_identity["input_archive_ref"]
        archive_path = self._workspace(node).parent / "input-archive.json"
        require(type(archive) is dict and set(archive) == {"path", "schema_version", "raw_digest"}
                and archive["schema_version"] == "newrouge.b-route-segmented-input-archive.v1"
                and archive["path"] == _relative(self.root, archive_path)
                and type(archive["raw_digest"]) is str and re.fullmatch(r"sha256:[0-9a-f]{64}", archive["raw_digest"])
                and archive_path.is_file() and file_sha(_safe(self.root, archive_path)) == archive["raw_digest"],
                "original_input_archive_reference")
        request = _core().validate_request_identity(self.root, self.plan, node, request_identity,
            self._workspace(node), witness, rendered_request=rendered_request, completed_prefix=completed_prefix)
        require(type(request) is dict and _same(request, request_identity), "actual_request_identity_changed")
        require(type(request["timeout_sec"]) is int and 1 <= request["timeout_sec"] <= self.timeout(node), "native_timeout_expanded")
        require(len(self.plan["nodes"]) - len(state["capability_selection"]["calls"]) <= budget["remaining_reservable_calls"],
                "cannot_fund_remaining_plan")
        require(node["node_id"] not in auxiliary["nodes"], "node_reservation_never_repeated")
        require(set(node["dependencies"]) <= set(auxiliary["completed_order"]), "missing_parent_receipts")
        lineages = witness["candidate_lineages"]
        require(all(label in lineages for label in node["candidate_labels"]), "original_lineage_mapping_missing")
        charged_lineages = [] if node["phase"] == "selection" else sorted({lineages[label] for label in node["candidate_labels"]})
        candidate = charged_lineages[0] if len(charged_lineages) == 1 else None
        ledger = state["capability_selection"]
        for lineage in charged_lineages:
            require(ledger["lineage_invocations"][lineage] < 64, "original_lineage_limit")
        number = len(ledger["calls"]) + 1
        reservation = {"schema_version": CLAIM, "protocol": self.plan["protocol"], "number": number,
            "reservation_id": self.plan["run_id"] + ":dispatch:" + str(number), "run_id": self.plan["run_id"],
            "phase": node["phase"], "candidate": candidate, "generation": 1, "execution": 1,
            "candidate_labels": deepcopy(node["candidate_labels"]), "lineage_ids": charged_lineages,
            "reserved_at_utc": _now(), "status": "reserved", "request_identity": deepcopy(request),
            "workspace": str(self._workspace(node)), "timeout_sec": request["timeout_sec"],
            "model_identity": deepcopy(witness["runtime_identity"])}
        next_state, next_aux = deepcopy(state), deepcopy(auxiliary)
        next_state["capability_selection"]["calls"].append(reservation)
        next_state["capability_selection"]["total_invocations"] += 1
        for lineage in charged_lineages:
            next_state["capability_selection"]["lineage_invocations"][lineage] += 1
        claim = {"schema_version": CLAIM, "protocol": self.plan["protocol"], "plan_digest": self.plan["plan_digest"],
                 "node": deepcopy(node), "reservation": deepcopy(reservation), "registry_epoch": witness["registry_epoch"],
                 "funding_at_reserve": deepcopy(witness["funding"]),
                 "parents": {parent: prefix[parent]["result_digest"] for parent in node["dependencies"]},
                 "native_after_digest": codec.raw_digest(_json_bytes(next_state)),
                 "journal_ref": _relative(self.root, self._publication_path("reserve", node))}
        claim_path = self._workspace(node).parent / "claim.json"
        head = {"schema_version": HEAD, "status": "active", "run_id": self.plan["run_id"], "plan_digest": self.plan["plan_digest"],
                "node_id": node["node_id"], "reservation_id": reservation["reservation_id"],
                "claim_ref": _relative(self.root, claim_path), "claim_raw_digest": codec.raw_digest(_json_bytes(claim))}
        next_aux["nodes"][node["node_id"]] = {"status": "unknown", "reservation": deepcopy(reservation),
                                                 "claim_ref": head["claim_ref"]}
        fiscal_grant = None
        import _b_route_segmented_runtime as runtime_owner
        if state['schema_version'] == runtime_owner.FISCAL_RUN:
            import _b_route_segmented_funding as funding_owner
            fiscal_grant = funding_owner.current_schedule_grant()
            fiscal_grant.before_reserve(self, node, reservation, claim, claim_path)
        self._transaction("reserve", node, {self.head: head, claim_path: claim, self.run / "run.json": next_state,
                          self.aux: next_aux}, {"reservation": reservation}, witness=witness)
        self._fresh()  # A lost return never gives permission to reserve/dispatch twice.
        if fiscal_grant is not None:
            fiscal_grant.after_persist(self, reservation)
        self._prefixes[reservation["reservation_id"]] = completed_prefix
        return deepcopy(reservation)

    def _reservation(self, reservation):
        auxiliary = self._auxiliary()
        matches = [(node, auxiliary["nodes"].get(node["node_id"])) for node in self.plan["nodes"]
                   if auxiliary["nodes"].get(node["node_id"], {}).get("reservation", {}).get("reservation_id") == reservation.get("reservation_id")]
        require(len(matches) == 1 and _same(matches[0][1]["reservation"], reservation), "original_reservation_changed")
        node, entry = matches[0]
        require(entry["status"] == "unknown", "known_packet_not_republished")
        head = self._head()
        require(head is not None and head["status"] == "active" and head["reservation_id"] == reservation["reservation_id"],
                "one_original_active_claim_required")
        raw_claim = _safe(self.root, self.root / head["claim_ref"]).read_bytes()
        require(codec.raw_digest(raw_claim) == head["claim_raw_digest"], "permanent_claim_changed")
        claim = codec.strict_json_loads(raw_claim)
        require(_same(claim["reservation"], reservation) and _same(claim["node"], node), "claim_packet_changed")
        return auxiliary, node, entry, head

    def complete(self, reservation, verified_result):
        self._writable()
        state, witness, _budget = self._fresh()
        auxiliary, node, entry, head = self._reservation(reservation)
        prefix = self._prefixes.get(reservation["reservation_id"])
        if prefix is None:
            snapshot = self.snapshot()
            prefix = _core().capture_completed_prefix(self.root, self.plan,
                {item["node_id"]: item["verified_result"] for item in snapshot["completed"]})
        previous = _core().verify_completed_prefix(self.root, self.plan, prefix)
        require(list(previous) == auxiliary["completed_order"], "completion_prefix_order_changed")
        original_claim = _read(self.root, self.root / head["claim_ref"])
        require(_same(original_claim["parents"], {parent: previous[parent]["result_digest"] for parent in node["dependencies"]}),
                "completion_claim_parents_changed")
        for parent, result in previous.items():
            require(auxiliary["nodes"][parent]["result_digest"] == result["result_digest"], "completion_prefix_journal_changed")
        _core().validate_result_independence(self.root, self.run, self.plan, prefix, verified_result)
        value = _core().validate_verified_result(self.plan, node, reservation, verified_result)
        require(type(value) is dict, "verified_result_not_persistable")
        # Factory verification is repeated against the exact original artifacts;
        # no caller boolean or copied result dictionary grants completion.
        _core().verify_manifest(self.root, self.plan["manifest"])
        result_path = self._workspace(node).parent / "result.json"
        next_state, next_aux = deepcopy(state), deepcopy(auxiliary)
        rows = [row for row in next_state["capability_selection"]["calls"] if row["reservation_id"] == reservation["reservation_id"]]
        require(len(rows) == 1 and "outcome" not in rows[0] and _same(rows[0], reservation), "native_outcome_already_recorded")
        binding = value["binding"]
        elapsed = binding["host_execution"]["active_elapsed_seconds"]
        require(_number(elapsed), "actual_elapsed_time_required")
        rows[0]["outcome"] = {"status": "completed", "completed_at_utc": _now(), "output_sha256": binding["output_sha256"],
                              "active_elapsed_seconds": elapsed, "segmented_result_digest": value["result_digest"]}
        next_state["active_elapsed_seconds"] = state.get("active_elapsed_seconds", 0) + elapsed
        next_aux["nodes"][node["node_id"]].update(status="completed", result_ref=_relative(self.root, result_path),
            result_digest=value["result_digest"], stored_raw_digest=codec.raw_digest(_json_bytes(value)))
        next_aux["completed_order"].append(node["node_id"])
        next_aux["blocked"] = None
        settled = {**head, "status": "settled"}
        complete_claim = {"schema_version": CLAIM, "protocol": self.plan["protocol"], "plan_digest": self.plan["plan_digest"],
            "node_id": node["node_id"], "reservation_id": reservation["reservation_id"],
            "original_claim_ref": head["claim_ref"], "original_claim_raw_digest": head["claim_raw_digest"],
            "result_digest": value["result_digest"], "native_after_digest": codec.raw_digest(_json_bytes(next_state)),
            "journal_ref": _relative(self.root, self._publication_path("complete", node))}
        self._transaction("complete", node, {result_path: value, self._workspace(node).parent / "complete-claim.json": complete_claim,
                          self.run / "run.json": next_state,
                          self.aux: next_aux, self.head: settled}, {"node_id": node["node_id"], "recorded": True}, witness=witness)
        import _b_route_segmented_runtime as runtime_owner
        if state['schema_version'] == runtime_owner.FISCAL_RUN:
            import _b_route_segmented_funding as funding_owner
            funding_owner.current_schedule_grant().after_outcome(self, reservation, verified_result)
        return {"node_id": node["node_id"], "recorded": True, "native_qualified": False}

    def fail(self, reservation, diagnostic):
        self._writable()
        _state, witness, _budget = self._fresh()
        auxiliary, node, _entry, head = self._reservation(reservation)
        require(type(diagnostic) is dict, "failure_diagnostic_shape")
        value = {"schema_version": SCHEMA + ".failure", "protocol": self.plan["protocol"], "plan_digest": self.plan["plan_digest"],
                 "node_id": node["node_id"], "reservation": deepcopy(reservation), "diagnostic": deepcopy(diagnostic),
                 "outcome": "unknown", "may_redispatch": False, "released": 0}
        next_aux = deepcopy(auxiliary)
        next_aux["blocked"] = {"reason": "original_request_unknown", "reservation_id": reservation["reservation_id"],
                               "may_redispatch": False}
        # No unverified diagnostic can publish failed/completed native outcome.
        self._transaction("fail", node, {self._workspace(node).parent / "failure.json": value,
                          self.aux: next_aux, self.head: head}, {"blocked": True, "released": 0}, witness=witness)
        return value

    def finalize(self, completion_token):
        """Publish new-protocol auxiliary completion, never legacy admission."""
        self._writable()
        _state, witness, _budget = self._fresh()
        require(not self._pending(), "pending_publication_requires_resume")
        auxiliary, head = self._auxiliary(), self._head()
        require(auxiliary["blocked"] is None and head is not None and head["status"] == "settled"
                and auxiliary["completed_order"] == [node["node_id"] for node in self.plan["nodes"]],
                "completion_requires_all_settled_nodes")
        value = _core().validate_completion(self.root, self.plan, completion_token)
        require(_same(value["results"], [{"node_id": node["node_id"],
                "result_digest": auxiliary["nodes"][node["node_id"]]["result_digest"]} for node in self.plan["nodes"]]),
                "completion_not_original_paid_results")
        path = self.run / "q/completion.json"
        if os.path.lexists(path):
            require(_safe(self.root, path).read_bytes() == _json_bytes(value), "completion_never_replaced")
            return {"completion_ref": _relative(self.root, path), "raw_digest": file_sha(path), "model_calls": 0}
        self._transaction("finalize", None, {path: value}, {"completion_ref": _relative(self.root, path)}, witness=witness)
        return {"completion_ref": _relative(self.root, path), "raw_digest": file_sha(path), "model_calls": 0}


@contextmanager
def open_workflow(root, *, run_dir, plan, read_only=False):
    """Opt-in born/source validation precedes even lock-file/directory writes."""
    core = _core()
    require(type(read_only) is bool, "read_only_boolean_required")
    plan = core.validate_plan(plan)
    root, run_dir = Path(root).resolve(), Path(run_dir).resolve()
    _safe(root, run_dir)
    state = _read(root, run_dir / "run.json")
    witness = core.require_segmented_run(root, run_dir, state, plan)
    _ledger_budget(state, plan, witness)
    store = Path(witness["registry_store"])
    require(store == root / "logs/ci/mvg-recovery" and recovery.store_root(root, state) == store
            and (store / "registry.json").is_file(), "original_registry_required")
    if read_only:
        # Status/verification does not create a lock file or repair publication.
        session = _Session(_SEAL, root, run_dir, plan, witness)
        session._read_only = True
        require(not session._pending(), "read_only_pending_publication")
        require(session.aux.is_file() and session.plan_path.is_file()
                and _same(_read(root, session.plan_path), plan), "read_only_existing_workflow_required")
        session._auxiliary()
        try:
            yield session
        finally:
            session._closed = True
        return
    # Exactly the existing operation mutex and native run mutex, in this order.
    with recovery.operation_lock(root, state), coordinator_lock(run_dir):
        session = _Session(_SEAL, root, run_dir, plan, witness)
        try:
            session._initialize()
            yield session
        finally:
            session._closed = True
