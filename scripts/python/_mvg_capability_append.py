"""Durable Capability-local MVG admission without a final model veto."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from _planning_skill_common import atomic_json, canonical_sha, load_json
from _mvg_requirement_routes import FIELD, memberships, pair_errors
from _mvg_requirement_accounting import (VERIFICATION, EVIDENCE, verification_rows, evidence_rows,
    key_errors, string_list, manifest_key_errors)

PROOF_SCHEMA = "newrouge.mvg-capability-admission.v1"


class AppendBudgetExhausted(RuntimeError):
    """The complete candidate lineage exhausted its model-call budget."""


class RunBudgetExhausted(ValueError):
    """A frozen run budget ended; this is never a candidate finding."""


def issue_key(issue: dict[str, Any]) -> str:
    return str(issue.get("code", "invalid")) + "@" + str(issue.get("path", ""))


def preservation_errors(base: dict[str, Any], revised: dict[str, Any]) -> list[dict[str, str]]:
    """Protect accepted coverage, tests and boundaries; allow shared-flow extension."""
    errors = []
    base_shape, revised_shape = key_errors(base) + manifest_key_errors(base), key_errors(revised) + manifest_key_errors(revised)
    if base_shape or revised_shape:
        return [{'code': code, 'path': 'requirement_accounting'} for code in base_shape + revised_shape]
    for family, prior, current in ((VERIFICATION, verification_rows(base), verification_rows(revised)),
                                   (EVIDENCE, evidence_rows(base), evidence_rows(revised))):
        for row in prior if isinstance(prior, list) else []:
            retained = isinstance(current, list) and row in current
            if family == VERIFICATION and isinstance(current, list):
                retained = string_list(row.get('evidence_ids', [])) and any(isinstance(new, dict)
                    and string_list(new.get('evidence_ids', []))
                    and all(new.get(key) == value for key, value in row.items() if key != 'evidence_ids')
                    and set(row.get('evidence_ids', [])) <= set(new.get('evidence_ids', [])) for new in current)
            if not retained:
                errors.append({'code': 'append_accepted_' + family + '_changed', 'path': family})
    current_routes = memberships(revised)
    if not isinstance(current_routes, list):
        current_routes = []
    for row in memberships(base):
        if row not in current_routes:
            errors.append({"code": "append_accepted_requirement_route_changed",
                           "path": f"{FIELD}:{row.get('requirement_id')}:{row.get('flow_id')}"})
    for family in ("coverage_table", "tests", "entrypoints"):
        rows = revised.get(family, [])
        for row in base.get(family, []):
            retained = row in rows
            if family == "entrypoints" and not retained:
                matching = next((new for new in rows if all(new.get(field) == row.get(field)
                    for field in ("owner_task", "path", "symbol"))), None)
                retained = matching is not None and all(
                    (isinstance(matching.get(field), list) and all(item in matching[field] for item in value))
                    if isinstance(value, list) else matching.get(field) == value
                    for field, value in row.items())
            if not retained:
                errors.append({"code": f"append_accepted_{family}_changed", "path": family})
    flows = {str(row.get("id")): row for row in revised.get("manifest_candidate", {}).get("flows", [])}
    for prior in base.get("manifest_candidate", {}).get("flows", []):
        row = flows.get(str(prior.get("id")))
        if row is None:
            errors.append({"code": "append_accepted_flow_removed", "path": str(prior.get("id"))})
            continue
        for key, value in prior.items():
            if isinstance(value, list):
                retained = isinstance(row.get(key), list) and all(item in row[key] for item in value)
                if key == "handoffs" and isinstance(row.get(key), list):
                    retained = all(any(all(
                        (isinstance(new.get(field), list) and all(test in new[field] for test in original))
                        if field == "test_ids" and isinstance(original, list) else new.get(field) == original
                        for field, original in handoff.items()) for new in row[key]) for handoff in value)
            else:
                retained = row.get(key) == value
            if not retained:
                errors.append({"code": "append_accepted_flow_weakened:" + key,
                               "path": str(prior.get("id"))})
    return errors


def merge_append(base: dict[str, Any], delta: dict[str, Any], scope: dict[str, Any] | None = None) -> dict[str, Any]:
    from plan_mvg import bind_planned_verification, merge_planning_segments
    errors = key_errors(base) + key_errors(delta) + manifest_key_errors(base)
    for key in ('flows', 'tests', 'entrypoints'):
        if key in delta and (not isinstance(delta[key], list) or any(not isinstance(row, dict) for row in delta[key])):
            errors.append('append_' + key + '_invalid')
    if errors:
        raise ValueError(';'.join(errors))
    if VERIFICATION in delta or EVIDENCE in delta:
        errors = key_errors(delta)
        if errors:
            raise ValueError(';'.join(errors))
        existing = {row.get('requirement_id') for row in verification_rows(base) if isinstance(row, dict)}
        for row in delta.get(VERIFICATION, []):
            rid = row.get('requirement_id') if isinstance(row, dict) else None
            if rid in existing or (scope and rid not in scope['new_requirement_ids']):
                errors.append('append_requirement_verification_outside_new_scope:' + str(rid))
        prior_evidence = {(row['requirement_id'], row['evidence_id']) for row in evidence_rows(base)}
        errors.extend('append_requirement_evidence_already_accepted:' + row['requirement_id'] + ':' + row['evidence_id']
                      for row in delta.get(EVIDENCE, []) if (row['requirement_id'], row['evidence_id']) in prior_evidence)
        if errors:
            raise ValueError(';'.join(errors))
    if FIELD in delta:
        errors = pair_errors(delta[FIELD])
        existing = {row.get("requirement_id") for row in base.get("coverage_table", []) if isinstance(row, dict)}
        errors += ["append_coverage_requirement_already_accepted:" + str(row.get("requirement_id"))
                   for row in delta.get("coverage_table", []) if isinstance(row, dict)
                   and row.get("requirement_id") in existing]
        if errors:
            raise ValueError(";".join(errors))
    result = merge_planning_segments(base, [delta])
    result["gaps"] = deepcopy(delta.get("gaps", []))
    result["notes"] = list(dict.fromkeys(base.get("notes", []) + delta.get("notes", [])))
    result["manifest_candidate"]["tests"] = deepcopy(result.get("tests", []))
    planned = [test for test in delta.get("tests", []) if str(test.get("id", "")).startswith("verify-")]
    if planned:
        binding = {"manifest_candidate": result["manifest_candidate"], "tests": planned}
        bind_planned_verification(binding, base.get("manifest_candidate", {}))
    if scope and "task_statuses" in scope:
        from _mvg_manifest import _dedicated_integration_owner_task_ids
        manifest = result["manifest_candidate"]
        flows = manifest.get("flows", [])
        excluded = _dedicated_integration_owner_task_ids(flows)
        blockers = sorted({tid for flow in flows for tid in flow.get("task_ids", [])
                           if tid not in excluded and scope["task_statuses"].get(str(tid), "") != "done"})
        manifest.setdefault("coverage", {})["blocking_task_ids"] = blockers
    return result


def run_capability_append(workspace: Path, *, scopes: list[dict[str, Any]], seed: dict[str, Any],
                          identity: str, propose: Any, machine: Any, semantic: Any,
                          final_machine: Any, invocation_limit: int = 64,
                          before_call: Any = None, checkpoint: Any = None,
                          repair_check: Any = None) -> dict[str, Any]:
    """Admit each slice; retry one issue three times, then restart that slice."""
    workspace.mkdir(parents=True, exist_ok=True)
    path = workspace / "append-ledger.json"
    binding = canonical_sha({"identity": identity, "scopes": scopes, "seed": seed})
    ledger = load_json(path, None)
    if ledger is None:
        ledger = {"binding": binding, "status": "generating", "order": [s["capability_id"] for s in scopes],
                  "completed": [], "records": [], "restarts": [], "total_invocations": 0,
                  "accepted": deepcopy(seed), "current": None}
    if ledger.get("binding") != binding:
        raise ValueError("Capability append input identity changed")

    def persist():
        atomic_json(path, ledger)
        if checkpoint:
            checkpoint(deepcopy(ledger))

    def call(phase, request_identity=None):
        if ledger["total_invocations"] >= invocation_limit:
            raise AppendBudgetExhausted("capability_append_invocation_budget_exhausted")
        reservation = None
        if before_call:
            reservation = (before_call(phase, request_identity=request_identity)
                           if request_identity is not None else before_call(phase))
        ledger["total_invocations"] += 1
        ledger.setdefault("calls", []).append({"number": ledger["total_invocations"], "phase": phase,
                                               "capability_id": ledger["current"]["capability_id"],
                                               "context": ledger["current"]["context"]})
        if isinstance(reservation, dict):
            ledger["calls"][-1]["reservation_id"] = reservation["reservation_id"]
        persist()
        return ledger["total_invocations"]

    # Reconstruct the accepted chain on recovery; unknown artifact edits fail closed.
    accepted = deepcopy(seed)
    for index, record in enumerate(ledger["records"]):
        if index >= len(scopes) or record.get("scope") != scopes[index]:
            raise ValueError("Capability append accepted order changed")
        if record.get("base_sha256") != canonical_sha(accepted):
            raise ValueError("Capability append accepted base changed")
        rebuilt = merge_append(accepted, record["delta"], scopes[index])
        if record.get("proposal_sha256") != canonical_sha(rebuilt):
            raise ValueError("Capability append accepted proposal changed")
        if record.get("record_sha256") != canonical_sha({key: value for key, value in record.items() if key != "record_sha256"}):
            raise ValueError("Capability append accepted review changed")
        issues = machine(scopes[index], accepted, rebuilt)
        if issues:
            raise ValueError("Capability append accepted accounting invalid:" + str(issues))
        accepted = rebuilt
    if accepted != ledger["accepted"] or ledger["completed"] != ledger["order"][:len(ledger["records"])]:
        raise ValueError("Capability append checkpoint changed")
    if ledger["status"] in {"retired", "blocked"}:
        return ledger
    try:
        for index in range(len(ledger["records"]), len(scopes)):
            scope = scopes[index]
            current = ledger.get("current")
            if current is None:
                current = {"capability_id": scope["capability_id"], "context": 1, "issue": None,
                           "issue_attempts": {}, "proposal": None, "delta": None}
                ledger["current"] = current
            if current["capability_id"] != scope["capability_id"]:
                raise ValueError("Capability append current scope changed")
            while True:
                issue = current["issue"]
                if issue:
                    key = issue_key(issue)
                    if current["issue_attempts"].get(key, 0) >= 3:
                        ledger["restarts"].append({"capability_id": scope["capability_id"],
                            "context": current["context"], "issue_id": key, "repair_attempts": 3})
                        # Only the immutable scope and accepted predecessors survive.
                        current = {"capability_id": scope["capability_id"], "context": current["context"] + 1,
                                   "issue": None, "issue_attempts": {}, "proposal": None, "delta": None}
                        ledger["current"] = current
                        issue = None
                    else:
                        current["issue_attempts"][key] = current["issue_attempts"].get(key, 0) + 1
                persist()
                before_invocations = ledger["total_invocations"]
                stage = "generate"
                proposal = None
                delta = None
                try:
                    review_only = bool(issue and issue.get("code") == "append_semantic_execution_invalid"
                                       and current["proposal"] is not None)
                    if review_only:
                        proposal, delta = deepcopy(current["proposal"]), deepcopy(current["delta"])
                    else:
                        delta = propose(scope, deepcopy(ledger["accepted"]), deepcopy(current["proposal"]),
                                        deepcopy(issue), current["context"], call)
                        proposal = merge_append(ledger["accepted"], delta, scope)
                    issues = preservation_errors(ledger["accepted"], proposal)
                    issues += machine(scope, ledger["accepted"], proposal)
                    if any(str(row.get('code', '')).startswith('requirement_source_gap:') for row in issues):
                        ledger.update(status='blocked', errors=deepcopy(issues))
                        current.update(proposal=proposal, delta=delta, issues=issues)
                        persist()
                        return ledger
                    rejection = []
                    if issue and current["proposal"] is not None and not review_only:
                        old_issues = preservation_errors(ledger["accepted"], current["proposal"])
                        old_issues += machine(scope, ledger["accepted"], current["proposal"])
                        if {issue_key(row) for row in issues} - {issue_key(row) for row in old_issues}:
                            rejection.append("repair_new_machine_issue")
                        if repair_check:
                            rejection += repair_check(current["proposal"], proposal, issue, scope=scope)
                    gate = None
                    if not issues and not rejection:
                        stage = "semantic"
                        gate = semantic(scope, ledger["accepted"], proposal, call, current["context"])
                        issues = gate.get("issues", [])
                        if issue and issue.get("path") == "semantic-review":
                            if {issue_key(row) for row in issues} - {issue_key(row) for row in current.get("issues", [])}:
                                rejection.append("repair_new_semantic_issue")
                    if rejection:
                        ledger.setdefault("rejected_repairs", []).append({"capability_id": scope["capability_id"],
                            "context": current["context"], "invocations": ledger["total_invocations"], "errors": rejection})
                        proposal, delta = deepcopy(current["proposal"]), deepcopy(current["delta"])
                        issues = deepcopy(current.get("issues") or [issue])
                except (AppendBudgetExhausted, RunBudgetExhausted):
                    raise
                except (OSError, RuntimeError, ValueError) as exc:
                    from plan_mvg import classify_review_error
                    if (any(code in str(exc) for code in ("runner_input_too_large", "runner_context_budget_exceeded"))
                            or before_invocations == ledger["total_invocations"]):
                        ledger.update(status="blocked", errors=[{"code": "append_input_preparation_failed", "detail": str(exc)}])
                        persist()
                        return ledger
                    execution_issue = {"code": "append_semantic_execution_invalid" if stage == "semantic" else "append_execution_or_output_invalid",
                                       "path": "model", "error_type": classify_review_error(exc), "detail": str(exc)[:2000]}
                    ledger.setdefault("execution_errors", []).append({"capability_id": scope["capability_id"],
                        "context": current["context"], "invocations": ledger["total_invocations"],
                        "stage": stage, "issue": execution_issue})
                    pending_hard_issue = issue and issue.get("code") not in {
                        "append_semantic_execution_invalid", "append_execution_or_output_invalid"}
                    if stage != "semantic" or pending_hard_issue:
                        delta, proposal = deepcopy(current["delta"]), deepcopy(current["proposal"])
                    issues = deepcopy(current.get("issues") or [issue]) if pending_hard_issue else [execution_issue]
                if not issues:
                    record = {"scope": deepcopy(scope), "context": current["context"],
                              "base_sha256": canonical_sha(ledger["accepted"]),
                              "proposal_sha256": canonical_sha(proposal), "delta": delta,
                              "proof": gate["proof"], "execution": gate["execution"]}
                    record["record_sha256"] = canonical_sha(record)
                    ledger["records"].append(record)
                    ledger["accepted"] = proposal
                    ledger["completed"].append(scope["capability_id"])
                    ledger["current"] = None
                    persist()
                    break
                # Stable identity survives report reordering. A different problem
                # gets its own counter only after the old problem is absent.
                current["issue"] = next((row for row in issues if issue and issue_key(row) == issue_key(issue)), issues[0])
                current["proposal"] = proposal
                current["delta"] = delta
                current["issues"] = issues
                ledger.setdefault("issue_events", []).append({"capability_id": scope["capability_id"],
                    "context": current["context"], "invocations": ledger["total_invocations"],
                    "issues": deepcopy(issues), "issue_attempts": deepcopy(current["issue_attempts"])})
                persist()
        errors = final_machine(ledger["accepted"])
        ledger.update(status="blocked" if errors else "admitted", errors=errors)
        if not errors:
            ledger["proof"] = {"schema_version": PROOF_SCHEMA, "analysis_identity_sha256": identity,
                "proposal_sha256": canonical_sha(ledger["accepted"]), "verdict": "approved", "findings": [],
                "seed": seed, "scopes": scopes, "records": ledger["records"],
                "final_machine_status": "passed"}
        persist()
        return ledger
    except AppendBudgetExhausted:
        ledger.update(status="retired", errors=[{"code": "capability_append_invocation_budget_exhausted"}])
        persist()
        return ledger
