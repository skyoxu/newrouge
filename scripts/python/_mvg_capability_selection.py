"""Coordinate three admitted increments against one immutable selected prefix."""
from __future__ import annotations

from copy import deepcopy
import random
import shutil
from pathlib import Path

from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json, parse_model_json, repo_path
from _mvg_capability_generation import capability_scopes, seed_proposal, generate_append, admission_proof
import _mvg_capability_checkpoint as selected_checkpoint
from _mvg_capability_append import RunBudgetExhausted

STRATEGY = "capability-local-selection.v1"


def generation(state):
    value = state.get("capability_selection", {}).get("generation", 1)
    if type(value) is not int or value < 1:
        raise ValueError("capability_selection_generation_invalid")
    return value


def candidate_root(run_dir, label, attempt):
    root = run_dir / "candidates" / label
    return root if attempt == 1 else root / f"generation-{attempt}"


def scope_workspace(run_dir, label, index, attempt):
    return candidate_root(run_dir, label, attempt) / f"scope-{index + 1}"


def frozen_scopes(state, prepared):
    statuses = {str(row["id"]): str(row.get("status", "")).lower()
                for row in load_json(prepared / "task-master.json", {}).get("master", {}).get("tasks", [])}
    return capability_scopes(load_json(prepared / "capabilities.v1.json", {}),
        load_json(prepared / "semantic-requirements.v1.json", {}), state.get("planning_scope"), statuses, prepared=prepared)


def _artifact(run_dir, relative, expected):
    path = repo_path(run_dir, str(relative))
    if not path.is_relative_to(run_dir.resolve()) or not expected or not path.is_file() or file_sha(path) != expected:
        raise ValueError("capability_selection_artifact_identity_changed:" + str(relative))
    return path


def candidate_artifacts(root, run_dir, state, scopes, index, accepted, prefix, admission):
    """Recheck every selected predecessor and the current admitted increment."""
    import plan_mvg as pm
    from _mvg_planning_review import review_execution_errors
    if admission.get("status") != "admitted":
        raise ValueError("capability_selection_candidate_not_admitted")
    label = str(admission.get("candidate") or "")
    if label not in {"candidate-1", "candidate-2", "candidate-3"}:
        raise ValueError("capability_selection_candidate_label_invalid")
    workspace = repo_path(run_dir, admission["workspace"])
    attempt = admission.get("generation", 1)
    if type(attempt) is not int or not 1 <= attempt <= generation(state):
        raise ValueError("capability_selection_candidate_generation_invalid")
    if workspace != scope_workspace(run_dir, label, index, attempt).resolve():
        raise ValueError("capability_selection_candidate_workspace_binding_invalid")
    if admission.get("lineage") != f"{label}-r{attempt}":
        raise ValueError("capability_selection_candidate_lineage_invalid")
    pm._validate_input_freshness(root, workspace, state)
    proposal_path = _artifact(run_dir, admission["proposal_path"], admission["proposal_sha256"])
    proof_path = _artifact(run_dir, admission["proof_path"], admission["proof_sha256"])
    execution_path = _artifact(run_dir, admission["execution_path"], admission["execution_sha256"])
    if any(not path.is_relative_to(workspace) for path in (proposal_path, proof_path, execution_path)):
        raise ValueError("capability_selection_candidate_workspace_changed")
    proposal, proof, execution = (load_json(path, {}) for path in (proposal_path, proof_path, execution_path))
    from _mvg_global_audit import reopen_context
    if proof.get("records", [{}])[-1].get("proof", {}).get("reopen_context") != reopen_context(state, scopes[index], attempt):
        raise ValueError("capability_selection_candidate_reopen_context_changed")
    if (proof.get("records", [])[:-1] != prefix or proof.get("scopes") != scopes[:index + 1]
            or proof.get("records", [{}])[-1].get("base_sha256") != canonical_sha(accepted)):
        raise ValueError("capability_selection_candidate_prefix_changed")
    errors = pm.candidate_admission_errors(root, state, proposal, proof,
        append_requirement_ids=set(scopes[index]["cumulative_requirement_ids"]))
    errors += review_execution_errors(state, proposal, execution, proof)
    if errors:
        raise ValueError("capability_selection_candidate_proof_invalid:" + str(errors))
    local_ledger = load_json(workspace / "capability-append/append-ledger.json", {})
    calls = state["capability_selection"].get("calls", [])
    expected_calls = sum(row.get("candidate") == label and row.get("capability_id") == scopes[index]["capability_id"]
                         and row.get("generation", 1) == attempt
                         for row in calls)
    if (type(admission.get("total_invocations")) is not int
            or admission["total_invocations"] != execution.get("total_invocations")
            or admission["total_invocations"] != local_ledger.get("total_invocations")
            or admission["total_invocations"] != expected_calls
            or local_ledger.get("records") != proof.get("records", [])[-1:]):
        raise ValueError("capability_selection_candidate_execution_totals_changed")
    return proposal, proof, execution


def selection_identity(state, scope, index, base, admissions, aliases):
    return {"schema_version": "newrouge.mvg-capability-selection-input.v1",
        "analysis_identity_sha256": state["analysis_identity_sha256"],
        "run_id": state["run_id"], "capability_id": scope["capability_id"],
        "scope_sha256": canonical_sha(scope), "order_index": index, "base_sha256": canonical_sha(base),
        "candidates": {alias: {key: admissions[label][key] for key in
            ("lineage", "proposal_sha256", "proof_sha256", "execution_sha256")}
            for alias, label in aliases.items()}}


def _selected_step(root, run_dir, state, scopes, index, base, prefix, step):
    import plan_mvg as pm
    aliases = step["aliases"]
    if set(aliases) != {"A", "B", "C"} or set(aliases.values()) != set(pm.MVG_CANDIDATE_LABELS):
        raise ValueError("capability_selection_aliases_changed")
    proposals = {}
    proofs = {}
    for label in pm.MVG_CANDIDATE_LABELS:
        if step["admissions"][label].get("candidate") != label:
            raise ValueError("capability_selection_candidate_slot_changed")
        proposals[label], proofs[label], _ = candidate_artifacts(
            root, run_dir, state, scopes, index, base, prefix, step["admissions"][label])
    identity = selection_identity(state, scopes[index], index, base, step["admissions"], aliases)
    if identity != step.get("input_identity") or canonical_sha(identity) != step.get("input_sha256"):
        raise ValueError("capability_selection_input_identity_changed")
    output = _artifact(run_dir, step["selection_path"], step["selection_sha256"])
    pm._validate_input_freshness(root, output.parent, state)
    if load_json(output.parent / "accepted-seed.json", None) != base:
        raise ValueError("capability_selection_comparison_seed_changed")
    for alias, label in aliases.items():
        if load_json(output.parent / f"{alias}.json", None) != proposals[label]:
            raise ValueError("capability_selection_comparison_candidate_changed")
    receipt_path = _artifact(run_dir, step["receipt_path"], step["receipt_sha256"])
    selection, receipt = load_json(output, {}), load_json(receipt_path, {})
    errors = pm.validate_mvg_selection(selection, candidate_labels=set(pm.MVG_CANDIDATE_LABELS),
        incumbent_present=False, alias_mapping=aliases, viable_labels=set(pm.MVG_CANDIDATE_LABELS))
    errors += pm.validate_selection_execution_receipt(state, selection, receipt,
        selection_input_sha256=canonical_sha(identity), output_sha256=file_sha(output),
        expected_attempt=step["attempt"])
    if (receipt.get("runner_receipt") or {}).get("output_sha256") != file_sha(output):
        errors.append("capability_selection_runner_output_changed")
    label = aliases.get(selection.get("selected"))
    if errors or label != step.get("selected_candidate"):
        raise ValueError("capability_selection_receipt_invalid:" + str(errors))
    record = proofs[label]["records"][-1]
    if step.get("record") != record or step.get("proposal_sha256") != canonical_sha(proposals[label]):
        raise ValueError("capability_selection_selected_record_changed")
    return proposals[label], record


def verified_prefix(root, run_dir, state, *, verify_history=True, recover_counters=True):
    """Return frozen scope, selected proposal and records without model dispatch."""
    import plan_mvg as pm
    pm._validate_input_freshness(root, run_dir, state)
    scopes = frozen_scopes(state, run_dir / "analysis-input")
    seed = seed_proposal(state, run_dir / "analysis-input")
    ledger = state.get("capability_selection") or {}
    from _mvg_global_audit import verify_reopen_history
    if verify_history:
        verify_reopen_history(root, run_dir, state)
    binding = canonical_sha({"strategy": STRATEGY, "scopes": scopes, "seed": seed})
    if ledger.get("binding") != binding or ledger.get("order") != [scope["capability_id"] for scope in scopes]:
        raise ValueError("capability_selection_frozen_scope_changed")
    calls = ledger.get("calls", [])
    total = ledger.get("total_invocations")
    costs = ledger.get("lineage_invocations", {})
    if (type(total) is not int or total != len(calls)
            or [row.get("number") for row in calls] != list(range(1, total + 1))
            or set(costs) != set(pm.MVG_CANDIDATE_LABELS)
            or any(type(costs[label]) is not int or costs[label] != sum(
                row.get("candidate") == label for row in calls) or not 0 <= costs[label] <= 64
                for label in pm.MVG_CANDIDATE_LABELS)):
        raise ValueError("capability_selection_invocation_accounting_changed")
    if "mvg.run_invocation_limit_source" in state:
        if total > state["mvg.run_invocation_limit"]:
            raise ValueError("capability_selection_run_budget_changed")
        for row in calls:
            if (row.get("reservation_id") != state["run_id"] + ":dispatch:" + str(row["number"])
                    or row.get("run_id") != state["run_id"] or not row.get("reserved_at_utc")
                    or not isinstance(row.get("request_identity"), dict)
                    or type(row.get("generation", 1)) is not int
                    or not 1 <= row.get("generation", 1) <= generation(state)
                    or row.get("lineage") != (f"{row['candidate']}-r{row.get('generation', 1)}" if row.get("candidate") else None)):
                raise ValueError("capability_selection_reservation_identity_changed")
    from _mvg_capability_generation import verify_dispatch_receipts
    verify_dispatch_receipts(run_dir, calls)
    for attempt in range(1, generation(state) + 1):
      for label in pm.MVG_CANDIDATE_LABELS:
        charged = [row for row in calls if row.get("candidate") == label and row.get("generation", 1) == attempt]
        counter_path = candidate_root(run_dir, label, attempt) / "lineage-execution.json"
        if counter_path.is_file():
            counter = load_json(counter_path, {})
            count = counter.get("model_invocation_count")
            if (type(count) is not int or count > len(charged)
                    or counter.get("candidate") != label or counter.get("lineage") != f"{label}-r{attempt}"):
                raise ValueError("capability_selection_lineage_budget_changed")
            if "mvg.run_invocation_limit_source" in state and counter.get("reservation_ids") != [
                    row["reservation_id"] for row in charged][:count]:
                raise ValueError("capability_selection_lineage_reservations_changed")
            if count < len(charged):
                if not recover_counters:
                    raise ValueError("capability_selection_historical_counter_incomplete")
                atomic_json(counter_path, {"candidate": label, "lineage": f"{label}-r{attempt}",
                    "model_invocation_count": len(charged), "recovered_reserved_invocations": len(charged) - count,
                    "reservation_ids": [row.get("reservation_id") for row in charged]})
        elif charged:
            if not recover_counters:
                raise ValueError("capability_selection_historical_counter_missing")
            atomic_json(counter_path, {"candidate": label, "lineage": f"{label}-r{attempt}",
                "model_invocation_count": len(charged), "recovered_reserved_invocations": len(charged),
                "reservation_ids": [row.get("reservation_id") for row in charged]})
    selected = ledger.get("selected", [])
    if not isinstance(selected, list) or len(selected) > len(scopes):
        raise ValueError("capability_selection_prefix_length_invalid")
    accepted, records = deepcopy(seed), []
    predecessor = None
    for index, step in enumerate(selected):
        base = accepted
        try:
            accepted, record = _selected_step(root, run_dir, state, scopes, index, accepted, records, step)
            if selected_checkpoint.enabled(state):
                accepted = selected_checkpoint.verify_checkpoint(run_dir, state, scopes[index]["capability_id"],
                    index, base, accepted, step, predecessor)
                predecessor = step["checkpoint"]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            if selected_checkpoint.enabled(state):
                selected_checkpoint.record_failure(run_dir, state, step, exc,
                    expected={"checkpoint": step.get("checkpoint"), "base_sha256": canonical_sha(base)},
                    actual={"selection": step, "predecessor": predecessor}, hash_subject="selected_step_binding")
            raise
        records.append(record)
    if selected_checkpoint.enabled(state) and ("checkpoint_head" not in ledger
            or canonical_sha(ledger["checkpoint_head"]) != canonical_sha(predecessor)):
        exc = ValueError("checkpoint_head_changed")
        selected_checkpoint.record_failure(run_dir, state, selected[-1] if selected else {}, exc,
            expected=predecessor, actual=ledger.get("checkpoint_head"), hash_subject="checkpoint_head")
        raise exc
    if ledger.get("accepted_sha256") != canonical_sha(accepted):
        exc = ValueError("capability_selection_accepted_base_changed")
        if selected_checkpoint.enabled(state):
            selected_checkpoint.record_failure(run_dir, state, selected[-1] if selected else {}, exc,
                expected=canonical_sha(accepted),
                actual=ledger.get("accepted_sha256"), hash_subject="accepted_projection_hash")
        raise exc
    current = ledger.get("current")
    if current is not None and (len(selected) >= len(scopes)
            or current.get("order_index") != len(selected)
            or current.get("capability_id") != scopes[len(selected)]["capability_id"]
            or current.get("base_sha256") != canonical_sha(accepted)):
        raise ValueError("capability_selection_current_scope_changed")
    if current is not None:
        for label in pm.MVG_CANDIDATE_LABELS:
            local_path = scope_workspace(run_dir, label, len(selected), generation(state)) / "capability-append/append-ledger.json"
            local = load_json(local_path, None)
            if local is None:
                continue
            charged = [row for row in calls if row.get("candidate") == label
                       and row.get("capability_id") == current["capability_id"]
                       and row.get("generation", 1) == generation(state)]
            count = local.get("total_invocations")
            if type(count) is not int or count > len(charged):
                raise ValueError("capability_selection_worker_budget_changed")
            if "mvg.run_invocation_limit_source" in state and [row.get("reservation_id") for row in local.get("calls", [])] != [
                    row["reservation_id"] for row in charged[:count]]:
                raise ValueError("capability_selection_worker_reservations_changed")
            if count < len(charged):
                if not recover_counters:
                    raise ValueError("capability_selection_historical_worker_incomplete")
                if local.get("status") == "admitted" or local.get("records"):
                    raise ValueError("capability_selection_admitted_worker_budget_changed")
                # The host reservation precedes the worker journal. Recover its
                # consumed slots while retaining issue attempts and accepted
                # state, so interruptions never refund a repair opportunity.
                local.setdefault("interrupted_reservations", []).append({"from": count,
                    "through": len(charged), "calls": deepcopy(charged[count:])})
                local["total_invocations"] = len(charged)
                pending = local.get("current") or {}
                for row in charged[count:]:
                    local.setdefault("calls", []).append({"number": len(local.get("calls", [])) + 1,
                        "phase": row["phase"], "capability_id": current["capability_id"],
                        "context": pending.get("context", 1), "interrupted": True,
                        "reservation_id": row.get("reservation_id")})
                atomic_json(local_path, local)
    if current is not None and current.get("input_sha256") is not None:
        aliases = current.get("aliases") or {}
        if (set(aliases) != {"A", "B", "C"}
                or set(aliases.values()) != set(pm.MVG_CANDIDATE_LABELS)
                or set(current.get("admissions", {})) != set(pm.MVG_CANDIDATE_LABELS)):
            raise ValueError("capability_selection_current_candidates_changed")
        identity = selection_identity(state, scopes[len(selected)], len(selected), accepted,
                                      current["admissions"], aliases)
        if current.get("input_identity") != identity or current["input_sha256"] != canonical_sha(identity):
            raise ValueError("capability_selection_current_input_changed")
        for attempt in current.get("selection_attempts", []):
            if attempt.get("status") == "completed":
                _selected_step(root, run_dir, state, scopes, len(selected), accepted, records, attempt)
    return scopes, accepted, records


def valid_current_candidates(root, run_dir, state):
    import plan_mvg as pm
    scopes, accepted, prefix = verified_prefix(root, run_dir, state)
    ledger = state["capability_selection"]
    current = ledger.get("current")
    if current is None:
        if len(prefix) == len(scopes) and state.get("selection_status") == "selected":
            verify_published_chain(root, run_dir, state)
            return list(pm.MVG_CANDIDATE_LABELS)
        return []
    valid = []
    for label, admission in current.get("admissions", {}).items():
        if label not in pm.MVG_CANDIDATE_LABELS or admission.get("status") != "admitted":
            continue
        if admission.get("candidate") != label:
            raise ValueError("capability_selection_candidate_slot_changed")
        candidate_artifacts(root, run_dir, state, scopes, len(prefix), accepted, prefix, admission)
        valid.append(label)
    return sorted(valid)


def recovery_available(root, run_dir, state):
    """Terminal budgets never reuse a Knowledge run; valid prefixes can resume."""
    if state.get("capability_selection", {}).get("terminal") is True:
        return False
    _, _, prefix = verified_prefix(root, run_dir, state)
    current = state["capability_selection"].get("current") or {}
    candidates = valid_current_candidates(root, run_dir, state)
    return bool(prefix or candidates or any(row.get("retryable") is True
        for row in current.get("admissions", {}).values()))


def verify_published_chain(root, run_dir, state, *, verified=None, proposal=None):
    """Require the selected prefix and published proof to describe one chain."""
    import plan_mvg as pm
    from _mvg_planning_review import review_execution_errors
    scopes, accepted, records = verified if verified is not None else verified_prefix(root, run_dir, state)
    published = load_json(run_dir / "proposal.json", {}) if proposal is None else proposal
    if len(records) != len(scopes) or published != accepted:
        raise ValueError("capability_selection_published_proposal_changed")
    selected = state.get("selected_admission_review") or {}
    paths = []
    for key, name in (("proof", "path"), ("execution", "execution_path")):
        path = repo_path(root, selected.get(name, ""))
        if (not path.is_relative_to(run_dir.resolve()) or not path.is_file()
                or file_sha(path) != selected.get(key + "_sha256")):
            raise ValueError("capability_selection_published_proof_changed")
        paths.append(path)
    proof, execution = (load_json(path, {}) for path in paths)
    expected_proof = admission_proof(state, seed_proposal(state, run_dir / "analysis-input"), scopes, records, accepted)
    errors = pm.candidate_admission_errors(root, state, accepted, proof)
    errors += review_execution_errors(state, accepted, execution, proof)
    totals = {}
    for step in state["capability_selection"]["selected"]:
        label = step["selected_candidate"]
        totals[label] = totals.get(label, 0) + step["admissions"][label]["total_invocations"]
    if execution.get("lineage_invocations") != totals or execution.get("total_invocations") != sum(totals.values()):
        errors.append("capability_selection_execution_aggregate_invalid")
    if proof != expected_proof or errors or selected.get("proposal_sha256") != canonical_sha(accepted):
        raise ValueError("capability_selection_published_chain_invalid:" + str(errors))


def generate_selected_capabilities(root, run_dir, state, *, backend, invoke_factory, selector_factory):
    disk = load_json(run_dir / "run.json", None)
    if isinstance(disk, dict) and disk != state:
        raise ValueError("capability_coordinator_state_changed")
    return _generate_selected_capabilities(root, run_dir, state, backend=backend,
        invoke_factory=invoke_factory, selector_factory=selector_factory)


def _generate_selected_capabilities(root, run_dir, state, *, backend, invoke_factory, selector_factory):
    import plan_mvg as pm
    scopes = frozen_scopes(state, run_dir / "analysis-input")
    seed = seed_proposal(state, run_dir / "analysis-input")
    ledger = state.setdefault("capability_selection", {
        "binding": canonical_sha({"strategy": STRATEGY, "scopes": scopes, "seed": seed}),
        "order": [scope["capability_id"] for scope in scopes], "selected": [],
        "accepted_sha256": canonical_sha(seed), "current": None, "total_invocations": 0,
        "lineage_invocations": {label: 0 for label in pm.MVG_CANDIDATE_LABELS}})
    if selected_checkpoint.enabled(state) and not ledger["selected"]:
        ledger.setdefault("checkpoint_head", None)

    def persist():
        atomic_json(run_dir / "run.json", state)
        try:
            execution = load_json(run_dir / "model-execution.json", {})
        except (OSError, ValueError, UnicodeError) as exc:
            execution = {"previous_receipt_error": pm._compact_exception_message(exc)}
        if not isinstance(execution, dict):
            execution = {"previous_receipt_error": "model-execution.json was not an object"}
        execution.update({
            "schema_version": "newrouge.mvg-planning-model-execution.v1", "backend": backend,
            "strategy": STRATEGY, "capability_selection": ledger,
            "candidate_attempts": state.get("candidate_attempts", {}),
            "selection_status": state.get("selection_status", "pending"),
            "selection_error": state.get("selection_block_reason"),
            "total_invocations": ledger["total_invocations"],
            "lineage_invocations": ledger["lineage_invocations"]})
        execution["dispatch_receipts"] = [load_json(run_dir / "dispatch-receipts" /
            f"dispatch-{row['number']}.json", row) for row in ledger.get("calls", [])]
        atomic_json(run_dir / "model-execution.json", execution)

    def reserve(phase, label=None, request_identity=None, publish=None):
        limit = state.get("mvg.run_invocation_limit", 192)
        if type(limit) is not int or limit <= 0:
            raise ValueError("mvg_run_invocation_limit_invalid")
        if ledger["total_invocations"] >= limit:
            raise RunBudgetExhausted("run_blocked_budget_exhausted")
        if label is not None and ledger["lineage_invocations"][label] >= 64:
            from _mvg_capability_append import AppendBudgetExhausted
            raise AppendBudgetExhausted("capability_append_invocation_budget_exhausted")
        ledger["total_invocations"] += 1
        if label is not None:
            ledger["lineage_invocations"][label] += 1
        receipt = {"number": ledger["total_invocations"], "phase": phase, "candidate": label,
            "capability_id": ledger["current"]["capability_id"], "run_id": state["run_id"],
            "lineage": f"{label}-r{generation(state)}" if label else None,
            "generation": generation(state),
            "reservation_id": state["run_id"] + ":dispatch:" + str(ledger["total_invocations"]),
            "reserved_at_utc": pm.now(), "status": "reserved"}
        if request_identity is not None:
            receipt["request_identity"] = deepcopy(request_identity)
        ledger.setdefault("calls", []).append(receipt)
        if publish is not None:
            publish(receipt)
        persist()
        if label is not None:
            charged = [row for row in ledger["calls"] if row.get("candidate") == label
                       and row.get("generation", 1) == generation(state)]
            atomic_json(candidate_root(run_dir, label, generation(state)) / "lineage-execution.json", {
                "candidate": label, "lineage": f"{label}-r{generation(state)}",
                "model_invocation_count": len(charged),
                "reservation_ids": [row.get("reservation_id") for row in charged]})
        return deepcopy(receipt)

    try:
        scopes, accepted, prefix = verified_prefix(root, run_dir, state)
        rebuild_replacement_selections(state, scopes)
        persist()
        if ledger.get("terminal") is True:
            if state.get("selection_block_reason") == "run_blocked_budget_exhausted":
                raise RunBudgetExhausted("run_blocked_budget_exhausted")
            current = ledger.get("current") or {}
            if state.get("selection_block_reason") == "selection_blocked_insufficient_admitted_candidates":
                results = [{"label": label, "admitted": row.get("status") == "admitted", "summary": row}
                           for label, row in current.get("admissions", {}).items()]
                pm._block_selection_for_insufficient_admitted_candidates(run_dir, state, results)
            raise ValueError(str(state.get("selection_block_reason") or "capability_selection_terminal"))
        if state.get("selection_status") == "selected":
            verify_published_chain(root, run_dir, state)
        # Reject all admitted current evidence before allowing any other model call.
        valid_current_candidates(root, run_dir, state)
        for index in range(len(prefix), len(scopes)):
            scope = scopes[index]
            current = ledger.get("current")
            if current is None:
                current = {"order_index": index, "capability_id": scope["capability_id"],
                    "base_sha256": canonical_sha(accepted), "admissions": {}, "selection_attempts": []}
                ledger["current"] = current
                state["candidate_attempts"] = {}
                state["candidate_admissions"] = {}
            state.update(selection_status="pending", phase="generating-capability")
            state.pop("selection_block_reason", None)
            persist()
            for label in pm.MVG_CANDIDATE_LABELS:
                existing = scope_workspace(run_dir, label, index, generation(state))
                if (existing / "analysis-input").exists():
                    pm._validate_input_freshness(root, existing, state)
            results = []
            for label in pm.MVG_CANDIDATE_LABELS:
                admission = current["admissions"].get(label)
                if admission is None or admission.get("retryable") is True:
                    budget_root = candidate_root(run_dir, label, generation(state))
                    workspace = budget_root / f"scope-{index + 1}"
                    def checkpoint(progress, label=label):
                        state["candidate_attempts"][label] = {"status": progress["status"],
                            "attempt_count": progress["total_invocations"], "capability_append": {
                                key: deepcopy(progress.get(key)) for key in ("order", "completed", "status", "total_invocations", "errors")}}
                        persist()
                    try:
                        workspace.mkdir(parents=True, exist_ok=True)
                        prepared = workspace / "analysis-input"
                        if not prepared.exists():
                            shutil.copytree(run_dir / "analysis-input", prepared)
                        pm._validate_input_freshness(root, workspace, state)
                        result = generate_append(root, state, workspace,
                            invoke_factory=lambda target, label=label, budget_root=budget_root:
                                invoke_factory(budget_root, target, label),
                            before_call=lambda phase, request_identity=None, label=label: reserve(
                                phase, label, request_identity), checkpoint=checkpoint,
                            scope_index=index, accepted_seed=accepted, selected_records=prefix)
                        admission = {"candidate": label, "status": result["status"], "lineage": f"{label}-r{generation(state)}",
                            "generation": generation(state),
                            "workspace": workspace.relative_to(run_dir).as_posix(), "errors": result.get("errors", []),
                            "append_terminal": result["status"] != "admitted", "retryable": False,
                            "total_invocations": result["total_invocations"]}
                        if admission["status"] == "admitted":
                            for key, name in (("proposal", "proposal.json"), ("proof", "admission-review.json"),
                                              ("execution", "admission-execution.json")):
                                admission[key + "_path"] = (workspace / name).relative_to(run_dir).as_posix()
                                admission[key + "_sha256"] = file_sha(workspace / name)
                            candidate_artifacts(root, run_dir, state, scopes, index, accepted, prefix, admission)
                            validation = pm.validate_proposal(root, state, result["accepted"],
                                append_requirement_ids=set(scope["cumulative_requirement_ids"]))
                            state["candidate_attempts"][label].update(status="valid", validation=validation,
                                proposal_sha256=admission["proposal_sha256"])
                    except RunBudgetExhausted:
                        raise
                    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
                        admission = {"candidate": label, "status": "execution-failed", "lineage": f"{label}-r{generation(state)}",
                            "generation": generation(state),
                            "workspace": workspace.relative_to(run_dir).as_posix(),
                            "retryable": isinstance(exc, (OSError, RuntimeError)),
                            "append_terminal": not isinstance(exc, (OSError, RuntimeError)),
                            "total_invocations": sum(row.get("candidate") == label and
                                row.get("capability_id") == scope["capability_id"] and
                                row.get("generation", 1) == generation(state) for row in ledger.get("calls", [])),
                            "errors": [{"code": "candidate_execution_failed", "error_type": pm.classify_review_error(exc),
                                        "detail": str(exc)[:2000]}]}
                        state["candidate_attempts"][label] = deepcopy(admission)
                    current["admissions"][label] = admission
                    state["candidate_admissions"][label] = deepcopy(admission)
                    persist()
                if admission["status"] == "admitted":
                    candidate_artifacts(root, run_dir, state, scopes, index, accepted, prefix, admission)
                results.append({"label": label, "admitted": admission["status"] == "admitted", "summary": admission})
            if sum(row["admitted"] for row in results) != 3:
                ledger["terminal"] = any(row["summary"].get("append_terminal") is True for row in results)
                persist()
                pm._block_selection_for_insufficient_admitted_candidates(run_dir, state, results)
            aliases = current.get("aliases")
            if aliases is None:
                labels = list(pm.MVG_CANDIDATE_LABELS)
                random.Random(canonical_sha({"run": state["run_id"], "scope": scope})).shuffle(labels)
                aliases = dict(zip(("A", "B", "C"), labels))
                current["aliases"] = aliases
            if set(aliases) != {"A", "B", "C"} or set(aliases.values()) != set(pm.MVG_CANDIDATE_LABELS):
                raise ValueError("capability_selection_aliases_changed")
            identity = selection_identity(state, scope, index, accepted, current["admissions"], aliases)
            input_sha = canonical_sha(identity)
            if current.get("input_sha256") is not None and (current["input_sha256"] != input_sha
                    or current.get("input_identity") != identity):
                raise ValueError("capability_selection_input_identity_changed")
            current.update(input_identity=identity, input_sha256=input_sha)
            state["admitted_candidates"] = list(pm.MVG_CANDIDATE_LABELS)
            state["selection_input_candidates"] = list(pm.MVG_CANDIDATE_LABELS)
            persist()
            selection = None
            selection_root = run_dir / "capability-selection" / f"scope-{index + 1}"
            if generation(state) > 1:
                selection_root = run_dir / "capability-selection" / f"generation-{generation(state)}" / f"scope-{index + 1}"
            attempts = current["selection_attempts"]
            for recorded in attempts:
                if recorded.get("status") == "running":
                    # A receipt written before journal publication can be
                    # recovered locally. Missing output keeps the reserved
                    # attempt consumed; it never earns a free retry slot.
                    number = recorded["attempt"]
                    workspace = selection_root / f"attempt-{number}"
                    output = workspace / "llm-sandbox" / f"attempt-{number}" / "selection/selection.json"
                    receipt_path = workspace / "selection-receipt.json"
                    if receipt_path.is_file():
                        result = load_json(output, {})
                        label = aliases.get(result.get("selected"))
                        if label not in pm.MVG_CANDIDATE_LABELS:
                            raise ValueError("capability_selection_recovered_output_invalid")
                        proposal, proof, _ = candidate_artifacts(root, run_dir, state, scopes, index, accepted,
                                                                prefix, current["admissions"][label])
                        recorded.update(status="completed", aliases=deepcopy(aliases), admissions=deepcopy(current["admissions"]),
                            input_identity=identity, input_sha256=input_sha, selected_candidate=label,
                            record=proof["records"][-1], proposal_sha256=canonical_sha(proposal),
                            selection_path=output.relative_to(run_dir).as_posix(), selection_sha256=file_sha(output),
                            receipt_path=receipt_path.relative_to(run_dir).as_posix(), receipt_sha256=file_sha(receipt_path))
                    else:
                        recorded.update(status="interrupted", error="selection_receipt_missing")
                if recorded.get("status") != "completed":
                    continue
                _selected_step(root, run_dir, state, scopes, index, accepted, prefix, recorded)
                selection = recorded
                break
            while selection is None and len(attempts) < pm.MVG_SELECTION_ATTEMPT_LIMIT:
                current["stage"] = "selection-preparing"
                number = len(attempts) + 1
                workspace = selection_root / f"attempt-{number}"
                workspace.mkdir(parents=True, exist_ok=True)
                prepared = workspace / "analysis-input"
                if not prepared.exists():
                    shutil.copytree(run_dir / "analysis-input", prepared)
                for alias, label in aliases.items():
                    proposal, _, _ = candidate_artifacts(root, run_dir, state, scopes, index, accepted, prefix,
                                                        current["admissions"][label])
                    atomic_json(workspace / f"{alias}.json", proposal)
                atomic_json(workspace / "accepted-seed.json", accepted)
                public_identity = {key: value for key, value in identity.items() if key != "candidates"}
                public_identity["candidates"] = {alias: {key: value for key, value in candidate.items()
                    if key != "lineage"} for alias, candidate in identity["candidates"].items()}
                prompt = ("Compare only the three admitted increments for the current Capability in A.json, B.json, C.json. "
                    "accepted-seed.json is read-only context and is never a candidate or fallback. All three share the "
                    "same frozen input and base. Do not demand coverage of future Capabilities. Rank source fidelity, "
                    "journey coherence, affected handoffs, verification feasibility and cumulative impact. Select one "
                    "candidate without mixing. All candidates passed machine and independent semantic admission; "
                    "return only viable reviews, no additional hard veto. Candidate order and labels convey no quality. "
                    "Return strict selection JSON with unique ranks 1..3; the winner must rank 1. No tools.\n" +
                    pm.json.dumps({"scope": scope, "identity": public_identity}, ensure_ascii=False))
                recorded = {"attempt": number, "status": "preparing"}
                persist()
                try:
                    pm._validate_input_freshness(root, run_dir, state)
                    from _mvg_capability_generation import preflight_runner_payload
                    schema = pm.mvg_selection_output_schema(incumbent_present=False)
                    # Measure the exact runner wrapper with all complete files.
                    sandbox = workspace / "llm-sandbox" / f"attempt-{number}" / "selection"
                    sandbox.mkdir(parents=True, exist_ok=True)
                    for name in ("A.json", "B.json", "C.json", "accepted-seed.json"):
                        shutil.copyfile(workspace / name, sandbox / name)
                    if not (sandbox / "analysis-input").exists():
                        shutil.copytree(prepared, sandbox / "analysis-input")
                    preflight_runner_payload(workspace, number, prompt, schema, "selection.json")
                    def dispatch_selection(request_identity=None):
                        def publish(reservation):
                            recorded.update(status="running", reservation_id=reservation["reservation_id"])
                            attempts.append(recorded)
                            current["stage"] = "selection-executing"
                        return reserve("selection", request_identity=request_identity, publish=publish)
                    output, execution = selector_factory(workspace)(prompt, number,
                        output_name="selection.json", output_schema_path=workspace / "output-schema.json",
                        output_schema=schema, before_dispatch=dispatch_selection)
                    result = parse_model_json(output)
                    errors = pm.validate_mvg_selection(result, candidate_labels=set(pm.MVG_CANDIDATE_LABELS),
                        incumbent_present=False, alias_mapping=aliases, viable_labels=set(pm.MVG_CANDIDATE_LABELS))
                    if errors:
                        raise ValueError("capability_selection_output_invalid:" + str(errors))
                    receipt = {"schema_version": "newrouge.mvg-selection-execution-receipt.v1",
                        "attempt": number, "backend": backend, "analysis_identity_sha256": state["analysis_identity_sha256"],
                        "selection_input_sha256": input_sha, "output_sha256": file_sha(output),
                        "runner_info": execution["backend_info"], "runner_receipt": execution["receipt"], "returncode": 0}
                    receipt_path = workspace / "selection-receipt.json"
                    atomic_json(receipt_path, receipt)
                    label = aliases[result["selected"]]
                    proposal, proof, _ = candidate_artifacts(root, run_dir, state, scopes, index, accepted, prefix,
                                                           current["admissions"][label])
                    recorded.update(status="completed", aliases=deepcopy(aliases), admissions=deepcopy(current["admissions"]),
                        input_identity=identity, input_sha256=input_sha, selected_candidate=label,
                        record=proof["records"][-1], proposal_sha256=canonical_sha(proposal),
                        selection_path=output.relative_to(run_dir).as_posix(), selection_sha256=file_sha(output),
                        receipt_path=receipt_path.relative_to(run_dir).as_posix(), receipt_sha256=file_sha(receipt_path))
                    _selected_step(root, run_dir, state, scopes, index, accepted, prefix, recorded)
                    selection = deepcopy(recorded)
                except RunBudgetExhausted:
                    raise
                except (OSError, RuntimeError, ValueError, TimeoutError) as exc:
                    if recorded["status"] == "preparing":
                        raise
                    recorded.update(status="failed", error=str(exc))
                persist()
            if selection is None:
                if ledger["total_invocations"] >= state.get("mvg.run_invocation_limit", 192):
                    raise RunBudgetExhausted("run_blocked_budget_exhausted")
                ledger["terminal"] = True
                raise ValueError("capability_selection_bounded_attempts_exhausted")
            proposal, record = _selected_step(root, run_dir, state, scopes, index, accepted, prefix, selection)
            if selected_checkpoint.enabled(state):
                current["stage"] = "checkpoint-preparing"
                current["checkpoint_preparation"] = {"status": "pending"}
                persist()
                pointer = selected_checkpoint.prepare_checkpoint(run_dir, state,
                    scope["capability_id"], index, accepted, proposal, selection)
                current["checkpoint_preparation"].update(status="prepared", pointer=pointer)
                persist()
                # Recheck frozen input and all receipts after staging, before visibility.
                _selected_step(root, run_dir, state, scopes, index, accepted, prefix, selection)
                checked_scopes, checked_accepted, checked_prefix = verified_prefix(root, run_dir, state)
                if checked_scopes != scopes or checked_accepted != accepted or checked_prefix != prefix:
                    raise ValueError("checkpoint_accepted_predecessor_changed")
                selected_checkpoint.commit_checkpoint(run_dir, state, pointer, selection, proposal, writer=atomic_json)
            else:
                ledger["selected"].append(selection)
                ledger.update(accepted_sha256=canonical_sha(proposal), current=None)
            accepted = proposal
            prefix.append(record)
            rebuild_replacement_selections(state, scopes)
            persist()
        proof = admission_proof(state, seed, scopes, prefix, accepted)
        errors = pm.candidate_admission_errors(root, state, accepted, proof)
        if errors:
            raise ValueError("capability_selection_final_admission_invalid:" + str(errors))
        selected_costs = {}
        for step in ledger["selected"]:
            label = step["selected_candidate"]
            selected_costs[label] = selected_costs.get(label, 0) + step["admissions"][label]["total_invocations"]
        execution = {"schema_version": "newrouge.mvg-capability-admission-execution.v1",
            "analysis_identity_sha256": state["analysis_identity_sha256"], "proposal_sha256": canonical_sha(accepted),
            "semantic_review_sha256": canonical_sha(proof), "records_sha256": canonical_sha(prefix),
            "total_invocations": sum(selected_costs.values()), "lineage_invocations": selected_costs}
        workspace = run_dir / "accepted-chain"
        if generation(state) > 1:
            workspace /= f"generation-{generation(state)}"
        atomic_json(workspace / "admission-review.json", proof)
        atomic_json(workspace / "admission-execution.json", execution)
        atomic_json(workspace / "proposal.json", accepted)
        atomic_json(run_dir / "proposal.json", accepted)
        state.update(phase="generated", selection_status="selected", selected_candidate="winner-chain",
            selected_admission_review={"path": (workspace / "admission-review.json").relative_to(root).as_posix(),
                "execution_path": (workspace / "admission-execution.json").relative_to(root).as_posix(),
                "proposal_sha256": canonical_sha(accepted), "proof_sha256": file_sha(workspace / "admission-review.json"),
                "execution_sha256": file_sha(workspace / "admission-execution.json")})
        state.pop("selection_block_reason", None)
        persist()
        from _mvg_global_audit import audit
        audit(root, run_dir, state)
        return {"run_id": state["run_id"], "proposal_sha256": file_sha(run_dir / "proposal.json"),
                "selected": "winner-chain", "candidate_count": 3, "capability_count": len(scopes)}
    except selected_checkpoint.CheckpointCommitOutcomeUnknown:
        # Only sidecar evidence is safe when the authoritative replace outcome is unknown.
        raise
    except RunBudgetExhausted:
        ledger["terminal"] = True
        state.update(phase="run_blocked_budget_exhausted", selection_status="blocked",
            selection_block_reason="run_blocked_budget_exhausted")
        persist()
        raise
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        current = ledger.get("current") or {}
        if current.get("stage") == "checkpoint-preparing":
            current.setdefault("checkpoint_preparation", {}).update(status="failed", reason=str(exc)[:2000])
            if isinstance(exc, ValueError):
                ledger["terminal"] = True
        if current.get("stage") == "selection-preparing":
            current["preparation_error"] = {"code": "selection_preparation_failed",
                "error_type": pm.classify_review_error(exc), "detail": str(exc)[:2000]}
            ledger["terminal"] = True
        if state.get("selection_block_reason") != "selection_blocked_insufficient_admitted_candidates":
            state.update(phase="selection-blocked", selection_status="blocked", selection_block_reason=str(exc))
        persist()
        raise


def rebuild_replacement_selections(state, scopes):
    """Recover this derived projection from committed checkpoints, never from attempts."""
    for reopened in state.get("reopen_history", []):
        reopened["replacement_selections"] = [{"capability_id": scopes[position]["capability_id"],
            "selected_candidate": step["selected_candidate"], "checkpoint": deepcopy(step["checkpoint"])}
            for position, step in enumerate(state["capability_selection"]["selected"])
            if step["admissions"][step["selected_candidate"]].get("generation", 1) == reopened["generation"]]
