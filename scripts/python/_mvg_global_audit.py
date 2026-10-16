"""Audit declared source conflicts and reopen immutable selected chains locally."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json, repo_path
from _mvg_capability_checkpoint import coordinator_lock, enabled, load_checkpoint, recover_commit_outcome
from _mvg_evidence_transport import resolve_citations
from _mvg_requirement_accounting import source_path, verification_rows

AUDIT_SCHEMA = "newrouge.mvg-global-audit.v1"
REPORT_SCHEMA = "newrouge.mvg-source-conflicts.v1"
PLAN_SCHEMA = "newrouge.mvg-reopen-plan.v1"


def _nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def _artifact(run_dir, path, digest):
    target = repo_path(run_dir, str(path))
    if (not target.is_relative_to(run_dir.resolve()) or not digest or not target.is_file()
            or file_sha(target) != digest):
        raise ValueError("global_audit_artifact_changed:" + str(path))
    return target


def _immutable(path, value):
    if path.exists():
        if load_json(path, None) != value:
            raise ValueError("global_audit_immutable_artifact_changed:" + str(path))
    else:
        atomic_json(path, value)


def chain_identity(run_dir, state):
    ledger = state["capability_selection"]
    return {"run_id": state["run_id"], "analysis_identity_sha256": state["analysis_identity_sha256"],
        "prepared_index_sha256": file_sha(run_dir / "analysis-input/analysis-index.json"),
        "checkpoint_head": deepcopy(ledger.get("checkpoint_head")),
        "selected_sha256": canonical_sha(ledger["selected"]),
        "proposal_sha256": ledger["accepted_sha256"], "generation": ledger.get("generation", 1),
        "budget": {"total_invocations": ledger["total_invocations"],
            "calls_sha256": canonical_sha(ledger.get("calls", [])),
            "lineage_invocations": deepcopy(ledger["lineage_invocations"]),
            "limit": state.get("mvg.run_invocation_limit", 192),
            "limit_source": deepcopy(state.get("mvg.run_invocation_limit_source"))}}


def _source(run_dir, reference):
    if (not isinstance(reference, dict) or not _nonempty(reference.get("path"))
            or not _nonempty(reference.get("sha256"))):
        raise ValueError("global_conflict_source_identity_invalid")
    ref = reference["path"]
    source_path(ref)
    index = load_json(run_dir / "analysis-input/analysis-index.json", {})
    prepared = run_dir / "analysis-input"
    copies = [prepared / key for key in index.get("files", {})
              if key in {"sources/" + ref, "references/" + ref}]
    if not copies or ref not in index.get("authority_inputs", {}):
        raise ValueError("global_conflict_source_not_frozen:" + ref)
    for copy in copies:
        if (not copy.is_file() or file_sha(copy) != reference["sha256"]
                or file_sha(copy) != index["files"][copy.relative_to(prepared).as_posix()]):
            raise ValueError("global_conflict_source_changed:" + ref)
    text = copies[0].read_bytes().decode("utf-8-sig")
    citations = reference.get("citations")
    if (not isinstance(citations, list) or not citations
            or any(not isinstance(row, dict) or set(row) != {"line", "text"}
                   or not isinstance(row["text"], str) for row in citations)):
        raise ValueError("global_conflict_citations_missing:" + ref)
    resolved = resolve_citations({"text": text}, {"citations": [row["line"] for row in citations]})
    if resolved != citations or len({row["line"] for row in citations}) != len(citations):
        raise ValueError("global_conflict_citations_changed:" + ref)


def validate_report(run_dir, state, scopes, proposal, report):
    """An explicit reviewed declaration supplies semantics; hashes prove its scope."""
    if (not isinstance(report, dict) or report.get("schema_version") != REPORT_SCHEMA
            or report.get("run_id") != state["run_id"]
            or report.get("analysis_identity_sha256") != state["analysis_identity_sha256"]
            or report.get("checkpoint_head_sha256") != canonical_sha(state["capability_selection"].get("checkpoint_head"))
            or report.get("proposal_sha256") != canonical_sha(proposal)
            or report.get("status") != "reviewed" or not _nonempty(report.get("reviewer"))
            or not _nonempty(report.get("rationale"))
            or not isinstance(report.get("conflicts"), list) or not report["conflicts"]):
        raise ValueError("global_conflict_declaration_identity_invalid")
    caps = {scope["capability_id"] for scope in scopes}
    flows = {flow["id"]: flow for flow in proposal["manifest_candidate"].get("flows", [])}
    seen = set()
    for issue in report["conflicts"]:
        if (not isinstance(issue, dict) or not isinstance(issue.get("id"), str) or not issue["id"].strip()
                or issue["id"] in seen or issue.get("kind") != "source_conflict"
                or issue.get("severity") != "hard" or not _nonempty(issue.get("contradiction"))
                or not isinstance(issue.get("capability_ids"), list)
                or not isinstance(issue.get("flow_ids"), list)
                or any(not _nonempty(value) for value in issue["capability_ids"] + issue["flow_ids"])
                or not (issue["capability_ids"] or issue["flow_ids"])
                or not set(issue["capability_ids"]) <= caps or not set(issue["flow_ids"]) <= flows.keys()
                or not isinstance(issue.get("source_refs"), list) or not issue["source_refs"]):
            raise ValueError("global_conflict_issue_invalid")
        seen.add(issue["id"])
        for ref in issue["source_refs"]:
            if not isinstance(ref, dict) or set(ref) != {"path", "sha256", "citations"}:
                raise ValueError("global_conflict_source_identity_invalid")
            _source(run_dir, ref)
    return deepcopy(report["conflicts"])


def _overlaps(proposal):
    groups = {}
    for flow in proposal["manifest_candidate"].get("flows", []):
        for key in flow.get("requirement_ids", []):
            groups.setdefault(("requirement", key), set()).add(flow["id"])
        for handoff in flow.get("handoffs", []):
            if handoff.get("contract_ref"):
                groups.setdefault(("contract", handoff["contract_ref"]), set()).add(flow["id"])
    return [{"kind": kind, "reference": ref, "flow_ids": sorted(ids), "classification": "ordinary_overlap"}
            for (kind, ref), ids in sorted(groups.items()) if len(ids) > 1]


def reopen_context(state, scope, attempt=None):
    ledger = state.get("capability_selection", {})
    attempt = ledger.get("generation", 1) if attempt is None else attempt
    contexts = state.get("reopen_contexts", {})
    if type(attempt) is not int or attempt < 1 or not isinstance(contexts, dict):
        raise ValueError("reopen_context_shape_invalid")
    context = contexts.get(str(attempt))
    if context is not None:
        if not valid_context(context) or context["generation"] != attempt:
            raise ValueError("reopen_context_shape_invalid")
        if scope["capability_id"] not in context["replacement_order"]:
            return None
        result = deepcopy(context)
        index = ledger["order"].index(scope["capability_id"])
        result["resolution_required_conflict_ids"] = [issue["id"] for issue in result["conflicts"]
            if result["resolution_boundaries"][issue["id"]] <= index]
        return result
    if attempt > 1:
        raise ValueError("reopen_context_missing")
    return None


def valid_context(context, *, projected=False):
    if (not isinstance(context, dict) or type(context.get("generation")) is not int or context["generation"] < 2
            or not isinstance(context.get("plan"), dict) or not _nonempty(context["plan"].get("path"))
            or not _nonempty(context["plan"].get("sha256")) or not isinstance(context.get("conflicts"), list)
            or any(not isinstance(issue, dict) or not _nonempty(issue.get("id")) for issue in context["conflicts"])
            or not isinstance(context.get("replacement_order"), list)
            or any(not _nonempty(cid) for cid in context["replacement_order"])
            or not isinstance(context.get("resolution_boundaries"), dict)):
        return False
    ids = [issue["id"] for issue in context["conflicts"]]
    if (len(set(ids)) != len(ids) or set(context["resolution_boundaries"]) != set(ids)
            or any(type(index) is not int or index < 0 for index in context["resolution_boundaries"].values())):
        return False
    required = context.get("resolution_required_conflict_ids")
    return not projected or (isinstance(required, list) and all(isinstance(cid, str) for cid in required)
        and len(set(required)) == len(required) and set(required) <= set(ids))


def record_generation(state, index):
    ledger = state.get("capability_selection")
    if not isinstance(ledger, dict):
        return 1
    selected = ledger.get("selected", [])
    if index < len(selected):
        step = selected[index]
        if step.get("kind") == "adoption":
            return step.get("generation", 1)
        return step["admissions"][step["selected_candidate"]].get("generation", 1)
    return ledger.get("generation", 1)


def verify_reopen_history(root, run_dir, state, *, check_originals=True):
    """Bind generations, immutable authority and the nonrefundable call prefix."""
    ledger = state["capability_selection"]
    histories = state.get("reopen_history", [])
    contexts = state.get("reopen_contexts", {})
    if (not isinstance(contexts, dict) or not isinstance(histories, list)
            or type(ledger.get("generation", 1)) is not int
            or any(not isinstance(entry, dict) for entry in histories)
            or len(histories) != ledger.get("generation", 1) - 1
            or set(contexts) != {str(number) for number in range(2, ledger.get("generation", 1) + 1)}):
        raise ValueError("reopen_generation_history_changed")
    inherited, boundaries = {}, {}
    for number, entry in enumerate(histories, 2):
        archive = load_json(_artifact(run_dir, entry["path"], entry["sha256"]), {})
        plan = load_json(_artifact(run_dir, entry["plan"]["path"], entry["plan"]["sha256"]), {})
        prior = archive["prior_state"]
        calls = prior["capability_selection"].get("calls", [])
        if (entry.get("generation") != number or plan.get("next_generation") != number
                or prior["capability_selection"].get("generation", 1) != number - 1
                or archive.get("plan") != entry["plan"] or plan.get("run_id") != state["run_id"]
                or plan.get("binding") != chain_identity(run_dir, prior)
                or canonical_sha(archive.get("proposal")) != plan["binding"]["proposal_sha256"]
                or ledger.get("calls", [])[:len(calls)] != calls):
            raise ValueError("reopen_historical_binding_changed")
        from _mvg_capability_selection import verified_prefix, verify_published_chain
        verified = verified_prefix(root, run_dir, prior, verify_history=False, recover_counters=False,
                                    check_originals=False)
        if len(verified[2]) == len(verified[0]):
            verify_published_chain(root, run_dir, prior, verified=verified, proposal=archive["proposal"],
                                   check_originals=False)
        historical_audit = verified_audit(root, run_dir, prior, prefix=verified)
        if archive.get("audit") != prior.get("global_audit") or historical_audit.get("hard_conflicts") != plan["conflicts"]:
            raise ValueError("reopen_historical_audit_changed")
        for issue in plan["conflicts"]:
            if issue["id"] in inherited and inherited[issue["id"]] != issue:
                raise ValueError("reopen_historical_conflict_changed")
            for ref in issue["source_refs"]:
                _source(run_dir, ref)
            inherited[issue["id"]] = issue
        boundaries.update(plan["conflict_resolution_boundaries"])
        if contexts[str(number)] != {"generation": number, "plan": entry["plan"],
                "conflicts": list(inherited.values()), "replacement_order": plan["replacement_order"],
                "resolution_boundaries": boundaries}:
            raise ValueError("reopen_historical_context_changed")


def historical_states(run_dir, state):
    return [load_json(_artifact(run_dir, entry["path"], entry["sha256"]), {})["prior_state"]
            for entry in state.get("reopen_history", [])]


def reopen_review_errors(context, review):
    if not valid_context(context, projected=True) or not isinstance(review, dict):
        return ["reopen_context_shape_invalid"]
    rows = review.get("reopen_reviews")
    expected = set(context["resolution_required_conflict_ids"])
    if (not isinstance(rows, list) or len(rows) != len(expected)
            or any(not isinstance(row, dict) for row in rows)
            or any(not _nonempty(row.get("conflict_id")) for row in rows)
            or {row.get("conflict_id") for row in rows} != expected):
        return ["reopen_conflict_resolution_accounting_invalid"]
    return ["reopen_conflict_unresolved:" + str(row.get("conflict_id")) for row in rows
            if row.get("plan_sha256") != context["plan"]["sha256"] or row.get("verdict") != "resolved"
            or not _nonempty(row.get("rationale"))]


def _reopen_resolutions(run_dir, state):
    resolved, unresolved = [], []
    selected = state["capability_selection"]["selected"]
    order = state["capability_selection"]["order"]
    for entry in state.get("reopen_history", []):
        plan = load_json(_artifact(run_dir, entry["plan"]["path"], entry["plan"]["sha256"]), {})
        checks = []
        for cid in plan["replacement_order"]:
            index = order.index(cid)
            if index >= len(selected):
                checks.append({"capability_id": cid, "reason": "replacement_not_selected"})
                continue
            step = selected[index]
            bound = step["record"]["proof"]
            context = bound.get("reopen_context")
            required = {issue["id"] for issue in plan["conflicts"]
                        if plan["conflict_resolution_boundaries"][issue["id"]] <= index}
            if (not valid_context(context, projected=True) or context.get("generation", 0) < entry["generation"]
                    or not required <= set(context.get("resolution_required_conflict_ids", []))
                    or reopen_review_errors(context, bound["review"])):
                checks.append({"capability_id": cid, "reason": "replacement_resolution_missing"})
        row = {"plan": entry["plan"], "conflict_ids": [issue["id"] for issue in plan["conflicts"]],
               "replacement_checkpoints": [step["checkpoint"] for step in selected[plan["earliest_order_index"]:]]}
        if checks:
            unresolved.append({**row, "gaps": checks})
        else:
            resolved.append(row)
    return resolved, unresolved


def audit(root, run_dir, state, *, conflict_report=None, conflict_report_sha256=None):
    from _mvg_capability_selection import verified_prefix, verify_published_chain
    scopes, proposal, records = verified_prefix(root, run_dir, state)
    complete = len(records) == len(scopes)
    if complete:
        verify_published_chain(root, run_dir, state)
    report_pointer = state.get("global_conflict_report")
    if conflict_report is not None:
        path = Path(conflict_report).resolve()
        if (not path.is_relative_to((root / "logs").resolve()) or not conflict_report_sha256
                or not path.is_file() or file_sha(path) != conflict_report_sha256):
            raise ValueError("global_conflict_report_hash_or_location_invalid")
        report = load_json(path, None)
        frozen = run_dir / "global-audits" / "reports" / (canonical_sha(report)[7:] + ".json")
        _immutable(frozen, report)
        report_pointer = {"path": frozen.relative_to(run_dir).as_posix(), "sha256": file_sha(frozen)}
    conflicts, gaps = [], []
    if report_pointer:
        try:
            report = load_json(_artifact(run_dir, report_pointer["path"], report_pointer["sha256"]), None)
            conflicts = validate_report(run_dir, state, scopes, proposal, report)
        except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
            gaps.append({"code": "conflict_evidence_gap", "reason": str(exc)})
    gaps.extend({"code": "requirement_source_gap", "requirement_id": row.get("requirement_id")}
                for row in verification_rows(proposal) if row.get("disposition") == "source_gap")
    if not complete:
        gaps.append({"code": "selected_chain_incomplete"})
    resolved, unresolved = _reopen_resolutions(run_dir, state)
    gaps.extend({"code": "unresolved_reopened_conflicts", **row} for row in unresolved)
    receipt = {"schema_version": AUDIT_SCHEMA, "binding": chain_identity(run_dir, state),
        "status": "blocked" if conflicts or gaps else "passed", "complete_chain": complete,
        "conflict_report": deepcopy(report_pointer), "hard_conflicts": conflicts, "evidence_gaps": gaps,
        "resolved_reopened_conflicts": resolved,
        "ordinary_overlaps": _overlaps(proposal),
        "passed_checks": ["selected_prefix", "frozen_sources", "invocation_accounting"],
        "planned_obligations": {"tests": [row["id"] for row in proposal["manifest_candidate"].get("tests", [])
                                          if row.get("state") == "planned"],
            "entrypoints": [row.get("path") for row in proposal.get("entrypoints", []) if row.get("status") == "planned"],
            "manual": deepcopy(proposal.get("manual_obligations", []))},
        "runtime_verified": False,
        "claim": "No reported hard conflicts in the checked evidence; no natural-language contradiction inference."}
    path = run_dir / "global-audits" / (canonical_sha(receipt)[7:] + ".json")
    _immutable(path, receipt)
    state["global_audit"] = {"path": path.relative_to(run_dir).as_posix(), "sha256": file_sha(path)}
    if report_pointer:
        state["global_conflict_report"] = report_pointer
    atomic_json(run_dir / "run.json", state)
    return {**state["global_audit"], **receipt}


def verified_audit(root, run_dir, state, path=None, digest=None, *, prefix=None):
    from _mvg_capability_selection import verified_prefix
    scopes, proposal, records = prefix if prefix is not None else verified_prefix(root, run_dir, state)
    pointer = state.get("global_audit") or {}
    if path is not None and (pointer.get("path") != path or pointer.get("sha256") != digest):
        raise ValueError("global_audit_pointer_changed")
    receipt = load_json(_artifact(run_dir, pointer.get("path", ""), pointer.get("sha256")), {})
    if receipt.get("schema_version") != AUDIT_SCHEMA or receipt.get("binding") != chain_identity(run_dir, state):
        raise ValueError("global_audit_binding_changed")
    report_pointer = receipt.get("conflict_report")
    if report_pointer != state.get("global_conflict_report"):
        raise ValueError("global_audit_report_pointer_changed")
    conflicts = []
    if report_pointer:
        report = load_json(_artifact(run_dir, report_pointer["path"], report_pointer["sha256"]), None)
        conflicts = validate_report(run_dir, state, scopes, proposal, report)
    if conflicts != receipt.get("hard_conflicts"):
        raise ValueError("global_audit_conflicts_changed")
    resolved, unresolved = _reopen_resolutions(run_dir, state)
    if unresolved or receipt.get("resolved_reopened_conflicts") != resolved:
        raise ValueError("global_audit_reopen_resolutions_changed")
    source_gaps = any(row.get("disposition") == "source_gap" for row in verification_rows(proposal))
    blocked = bool(conflicts or source_gaps or len(records) != len(scopes) or receipt.get("evidence_gaps"))
    if (receipt.get("status") != ("blocked" if blocked else "passed")
            or receipt.get("complete_chain") is not (len(records) == len(scopes))):
        raise ValueError("global_audit_verdict_changed")
    return receipt


def closure(state, proposal, conflicts):
    """No deterministic rebase proof exists: invalidate every cumulative successor."""
    ledger = state["capability_selection"]
    affected = {cid for row in conflicts for cid in row["capability_ids"]}
    flows = {fid for row in conflicts for fid in row["flow_ids"]}
    for flow in proposal["manifest_candidate"].get("flows", []):
        if flow["id"] in flows:
            affected.update(flow.get("capability_refs", []))
    # Bind flow changes to the earliest checkpoint that introduced or changed it.
    indices = [index for index, cid in enumerate(ledger["order"][:len(ledger["selected"])]) if cid in affected]
    for index, step in enumerate(ledger["selected"]):
        if any(flow.get("id") in flows for flow in step.get("record", {}).get("delta", {}).get("flows", [])):
            indices.append(index)
    if not indices:
        raise ValueError("reopen_no_accepted_affected_checkpoint")
    start = min(indices)
    return {"earliest_order_index": start, "affected_capability_ids": sorted(affected), "affected_flow_ids": sorted(flows),
        "invalidated_capability_ids": ledger["order"][start:len(ledger["selected"])],
        "invalidated_checkpoints": [deepcopy(row["checkpoint"]) for row in ledger["selected"][start:]],
        "replacement_order": ledger["order"][start:]}


def resolution_boundaries(state, proposal, conflicts):
    order = state["capability_selection"]["order"]
    result = {}
    for issue in conflicts:
        affected = set(issue["capability_ids"])
        for flow in proposal["manifest_candidate"].get("flows", []):
            if flow["id"] in issue["flow_ids"]:
                affected.update(flow.get("capability_refs", []))
        indices = [order.index(cid) for cid in affected]
        indices.extend(index for index, step in enumerate(state["capability_selection"]["selected"])
            if any(flow.get("id") in issue["flow_ids"] for flow in step.get("record", {}).get("delta", {}).get("flows", [])))
        if not indices:
            raise ValueError("reopen_conflict_resolution_boundary_missing")
        result[issue["id"]] = max(indices)
    return result


def plan_reopen(root, run_dir, state, *, audit_path, audit_sha256):
    from _mvg_capability_selection import verified_prefix
    if not enabled(state) or (run_dir / "apply-journal.json").exists() or state.get("applied"):
        raise ValueError("reopen_checkpoint_or_apply_journal_blocked")
    receipt = verified_audit(root, run_dir, state, audit_path, audit_sha256)
    if not receipt.get("hard_conflicts") or receipt.get("evidence_gaps"):
        raise ValueError("reopen_requires_source_backed_hard_conflict")
    _, proposal, _ = verified_prefix(root, run_dir, state)
    plan = {"schema_version": PLAN_SCHEMA, "run_id": state["run_id"],
        "binding": chain_identity(run_dir, state), "audit": deepcopy(state["global_audit"]),
        "conflicts": deepcopy(receipt["hard_conflicts"]), **closure(state, proposal, receipt["hard_conflicts"]),
        "conflict_resolution_boundaries": resolution_boundaries(state, proposal, receipt["hard_conflicts"]),
        "next_generation": state["capability_selection"].get("generation", 1) + 1,
        "replacement_policy": "three_independently_admitted_candidates_then_comparison_and_atomic_checkpoint",
        "refund_invocations": False}
    path = run_dir / "reopen-plans" / (canonical_sha(plan)[7:] + ".json")
    _immutable(path, plan)
    return {"path": path.relative_to(run_dir).as_posix(), "sha256": file_sha(path), **plan}


def _verify_reopen_plan(root, run_dir, state, plan, *, historical=False):
    from _mvg_capability_selection import verified_prefix, verify_published_chain
    if (not enabled(state) or (run_dir / "apply-journal.json").exists() or state.get("applied")
            or plan.get("schema_version") != PLAN_SCHEMA or plan.get("run_id") != state["run_id"]
            or plan.get("binding") != chain_identity(run_dir, state)):
        raise ValueError("reopen_stale_binding_or_apply_journal")
    prefix = verified_prefix(root, run_dir, state, check_originals=not historical)
    receipt = verified_audit(root, run_dir, state, plan.get("audit", {}).get("path"),
        plan.get("audit", {}).get("sha256"), prefix=prefix)
    scopes, proposal, records = prefix
    if len(records) == len(scopes):
        verify_published_chain(root, run_dir, state, verified=prefix, check_originals=not historical)
    if (not receipt.get("hard_conflicts") or receipt.get("evidence_gaps")
            or plan.get("conflicts") != receipt["hard_conflicts"]
            or any(plan.get(key) != value for key, value in closure(state, proposal, receipt["hard_conflicts"]).items())
            or plan.get("conflict_resolution_boundaries") != resolution_boundaries(state, proposal, receipt["hard_conflicts"])
            or plan.get("next_generation") != state["capability_selection"].get("generation", 1) + 1
            or plan.get("replacement_policy") != "three_independently_admitted_candidates_then_comparison_and_atomic_checkpoint"
            or plan.get("refund_invocations") is not False):
        raise ValueError("reopen_plan_closure_changed")
    return proposal


def _reopen_projection(run_dir, state, plan, plan_path, plan_sha256, proposal):
    start = plan["earliest_order_index"]
    pending = deepcopy(state)
    ledger = pending["capability_selection"]
    archive = {"schema_version": "newrouge.mvg-reopen-history.v1", "plan": {"path": plan_path, "sha256": plan_sha256},
        "audit": deepcopy(state["global_audit"]), "prior_state": deepcopy(state),
        "proposal": proposal, "replacement_order": plan["replacement_order"]}
    archive_path = run_dir / "reopen-history" / (canonical_sha(archive)[7:] + ".json")
    _immutable(archive_path, archive)
    ledger["selected"] = ledger["selected"][:start]
    head = ledger["selected"][-1]["checkpoint"] if start else None
    from _mvg_capability_generation import seed_proposal
    accepted = load_checkpoint(run_dir, head)["accepted"] if head else seed_proposal(state, run_dir / "analysis-input")
    ledger.update(checkpoint_head=head, accepted_sha256=canonical_sha(accepted), current=None,
                  generation=plan["next_generation"])
    ledger.pop("terminal", None)
    pending.setdefault("reopen_history", []).append({"path": archive_path.relative_to(run_dir).as_posix(),
        "sha256": file_sha(archive_path), "plan": {"path": plan_path, "sha256": plan_sha256},
        "replacement_order": plan["replacement_order"], "generation": plan["next_generation"]})
    inherited, boundaries = {}, {}
    for context in pending.get("reopen_contexts", {}).values():
        for issue in context["conflicts"]:
            inherited[issue["id"]] = issue
        boundaries.update(context["resolution_boundaries"])
    for issue in plan["conflicts"]:
        if issue["id"] in inherited and inherited[issue["id"]] != issue:
            raise ValueError("reopen_conflict_id_reused_with_different_evidence")
        inherited[issue["id"]] = issue
    boundaries.update(plan["conflict_resolution_boundaries"])
    pending.setdefault("reopen_contexts", {})[str(plan["next_generation"])] = {
        "generation": plan["next_generation"], "plan": {"path": plan_path, "sha256": plan_sha256},
        "conflicts": deepcopy(list(inherited.values())), "replacement_order": plan["replacement_order"],
        "resolution_boundaries": boundaries}
    for key in ("global_audit", "global_conflict_report", "selected_admission_review", "selected_candidate",
                "selection_block_reason", "selection_input_candidates", "admitted_candidates"):
        pending.pop(key, None)
    pending.update(phase="reopened", selection_status="pending", candidate_attempts={}, candidate_admissions={})
    revoked = [row["transaction_id"] for row in plan["invalidated_checkpoints"]]
    revoked += [row["adoption"]["source_transaction_id"] for row in state["capability_selection"]["selected"][start:]
                if row.get("kind") == "adoption"]
    return pending, sorted(set(revoked))


def _transaction_path(run_dir, plan_path, plan_sha256):
    return run_dir / "reopen-transactions" / (canonical_sha({"path": plan_path, "sha256": plan_sha256})[7:] + ".json")


def _transaction_result(transaction):
    pending = transaction["pending_state"]
    ledger = pending["capability_selection"]
    return {"status": "reopened", "run_id": pending["run_id"], "generation": ledger["generation"],
        "history": pending["reopen_history"][-1], "replacement_order": transaction["replacement_order"],
        "replacement_selections": [], "total_invocations": ledger["total_invocations"]}


def _commit_marker(path, transaction):
    return {"schema_version": "newrouge.mvg-reopen-commit.v1", "transaction_sha256": file_sha(path),
        "pending_state_sha256": canonical_sha(transaction["pending_state"])}


def assert_no_pending_reopen(run_dir):
    for path in (run_dir / "reopen-transactions").glob("*.json"):
        if path.name.endswith(".committed.json"):
            continue
        transaction = load_json(path, {})
        if load_json(path.with_suffix(".committed.json"), None) != _commit_marker(path, transaction):
            raise ValueError("pending_reopen_same_plan_recovery_required")


def execute_reopen(root, run_dir, state, *, plan_path, plan_sha256, writer=atomic_json):
    """Only an explicit same-plan retry may finish a write-ahead revocation."""
    from _mvg_capability_selection import verified_prefix
    from _mvg_capability_recovery import assert_epoch, revoke
    path = _transaction_path(run_dir, plan_path, plan_sha256)
    transaction = load_json(path, None)
    plan = load_json(_artifact(run_dir, plan_path, plan_sha256), {})
    if transaction is None:
        assert_no_pending_reopen(run_dir)
        if load_json(run_dir / "run.json", None) != state:
            raise ValueError("reopen_coordinator_state_changed")
        proposal = _verify_reopen_plan(root, run_dir, state, plan)
        pending, revoked = _reopen_projection(run_dir, state, plan, plan_path, plan_sha256, proposal)
        verified_prefix(root, run_dir, pending)
        transaction = {"schema_version": "newrouge.mvg-reopen-transaction.v1",
            "plan": {"path": plan_path, "sha256": plan_sha256}, "prior_state": deepcopy(state),
            "pending_state": pending, "revoked": revoked, "replacement_order": plan["replacement_order"]}
        _immutable(path, transaction)
    else:
        prior, pending = transaction["prior_state"], transaction["pending_state"]
        if (transaction.get("schema_version") != "newrouge.mvg-reopen-transaction.v1"
                or transaction.get("plan") != {"path": plan_path, "sha256": plan_sha256}
                or load_json(run_dir / "run.json", None) not in (prior, pending)
                or state not in (prior, pending)):
            raise ValueError("reopen_transaction_binding_changed")
        proposal = _verify_reopen_plan(root, run_dir, prior, plan, historical=True)
        expected, revoked = _reopen_projection(run_dir, prior, plan, plan_path, plan_sha256, proposal)
        if (pending != expected or transaction.get("revoked") != revoked
                or transaction.get("replacement_order") != plan["replacement_order"]):
            raise ValueError("reopen_transaction_projection_changed")
        # Current authority and retained selections still require the live epoch.
        if prior.get("recovery"):
            assert_epoch(root, prior)
        verified_prefix(root, run_dir, pending)
    prior, pending = transaction["prior_state"], transaction["pending_state"]
    if prior.get("recovery"):
        assert_epoch(root, prior)
    revoke(root, prior, transaction["revoked"])
    try:
        if load_json(run_dir / "run.json", None) == prior:
            writer(run_dir / "run.json", pending)
    except BaseException:
        # A failure after replace has committed. A failure before replace has not.
        # Never try to undo or overwrite either observable atomic outcome.
        observed = load_json(run_dir / "run.json", None)
        if observed not in (prior, pending):
            raise RuntimeError("reopen_commit_outcome_unknown")
        raise
    verified_prefix(root, run_dir, load_json(run_dir / "run.json", {}))
    _immutable(path.with_suffix(".committed.json"), _commit_marker(path, transaction))
    state.clear()
    state.update(pending)
    return _transaction_result(transaction)


def operate(root, *, run_id, operation, **kwargs):
    import plan_mvg as pm
    from _mvg_capability_selection import verified_prefix
    from _mvg_capability_recovery import operation_lock, assert_epoch
    run_path = pm._run_dir(root, run_id) / "run.json"
    raw = load_json(run_path, {})
    if raw.get("schema_version") != pm.RUN_SCHEMA or raw.get("run_id") != run_id:
        raise ValueError("reopen_run_identity_invalid")
    run_dir = run_path.parent
    with operation_lock(root, raw), coordinator_lock(run_dir):
        try:
            raw = load_json(run_path, {})
            if raw.get("recovery"):
                assert_epoch(root, raw)
            if operation == "reopen" and _transaction_path(run_dir, kwargs["plan_path"], kwargs["plan_sha256"]).is_file():
                return execute_reopen(root, run_dir, raw, **kwargs)
            _, state = pm._load_run(root, run_id)
            recover_commit_outcome(run_dir, state, verify=lambda: verified_prefix(root, run_dir, state))
            return {"audit": audit, "reopen-plan": plan_reopen, "reopen": execute_reopen}[operation](
                root, run_dir, state, **kwargs)
        except (OSError, ValueError, RuntimeError, KeyError, TypeError, UnicodeError) as exc:
            evidence = {"operation": operation, "run_id": run_id, "reason": str(exc),
                "arguments": {key: value for key, value in kwargs.items() if key != "writer"}}
            _immutable(run_dir / "global-audit-diagnostics" / (canonical_sha(evidence)[7:] + ".json"), evidence)
            if isinstance(exc, (KeyError, TypeError)):
                raise ValueError("global_audit_malformed_artifact:" + type(exc).__name__) from exc
            raise
