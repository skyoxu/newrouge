"""One final planning report, derived from the existing chain and machine audit."""
from __future__ import annotations

from copy import deepcopy
import json
import re

from _planning_skill_common import canonical_sha, text_sha
from _mvg_requirement_routes import project_routes
from _mvg_requirement_accounting import accounting_summary, prepared_evidence_validation, evidence_rows

FIELD = "planning_completion"
PROTOCOL_FIELD = "planning_completion_protocol"
PROTOCOL = "newrouge.mvg-planning-completion.v1"
_HASH = re.compile(r"sha256:[0-9a-f]{64}")


def _planned_obligations(proposal):
    return {"tests": [row["id"] for row in proposal.get("manifest_candidate", {}).get("tests", [])
                       if row.get("state") == "planned"],
        "entrypoints": [row.get("path") for row in proposal.get("entrypoints", []) if row.get("status") == "planned"],
        "manual": deepcopy(proposal.get("manual_obligations", []))}


def _passed_items(validation, audit, chain):
    passed = list(audit.get("passed_checks", [])) if audit else []
    if audit and audit.get("complete_chain") is True and chain is not None:
        passed += ["all_capability_admissions", "all_selections", "all_cumulative_merges"]
    if validation.get("formal_applicable") is True:
        passed.append("independent_review")
    if validation.get("status") == "passed":
        passed.append("proposal_validation")
    if validation.get("delta_status") in {"passed", "not_applicable_initial_manifest"}:
        passed.append("cumulative_delta_validation")
    return list(dict.fromkeys(passed))


def unavailable(reason="Historical trace has no bound final completion report."):
    return {"status": "unavailable", "planning_complete": None, "reason": reason,
            "runtime_acceptance": {"status": "not_verified", "runtime_verified": False}}


def build_report(root, run_dir, state, proposal, validation, audit, manifest):
    """The caller has verified the full chain, published proof and current audit."""
    from _mvg_global_audit import chain_identity
    gaps = deepcopy(audit.get("evidence_gaps", [])) if audit else []
    gaps.extend({"code": "validation_blocker", "reason": str(reason)} for reason in
                validation.get("errors", []) + validation.get("formal_blockers", []))
    supported = state.get("generation_strategy") == "capability-local-selection.v1"
    chain = None
    if supported:
        try:
            ledger = state["capability_selection"]
            if not isinstance(ledger["selected"], list) or not isinstance(ledger["accepted_sha256"], str):
                raise ValueError("selected_chain_shape_invalid")
            chain = chain_identity(run_dir, state)
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
            gaps.append({"code": "selected_chain_identity_unavailable", "reason": type(exc).__name__ + ":" + str(exc)})
    if not supported:
        gaps.append({"code": "complete_selected_chain_unavailable"})
    if audit is None:
        gaps.append({"code": "final_machine_audit_unavailable"})
    evidence_errors, valid = prepared_evidence_validation(root, proposal, run_dir / "analysis-input")
    gaps.extend({"code": "requirement_evidence_gap", "reason": reason} for reason in evidence_errors)
    accounting = accounting_summary(proposal, valid_evidence_keys=valid)
    if not accounting["planning_complete"]:
        gaps.append({"code": "requirement_source_gap"})
    complete = bool(supported and chain is not None and audit and audit.get("status") == "passed"
        and audit.get("complete_chain") is True and validation.get("status") == "passed"
        and validation.get("formal_applicable") is True and not gaps and not audit.get("hard_conflicts"))
    projection = project_routes(proposal)
    binding = {"run_id": state["run_id"], "analysis_identity_sha256": state["analysis_identity_sha256"],
        "manifest_path": state.get("manifest_path"),
        "manifest_sha256": text_sha(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"),
        "proposal_sha256": canonical_sha(proposal), "proposal_fields": sorted(projection),
        "trace_projection_sha256": canonical_sha(projection),
        "chain": chain,
        "audit_ref": deepcopy(state.get("global_audit"))}
    report = {"schema_version": PROTOCOL, "status": "complete" if complete else "blocked",
        "planning_complete": complete, "binding": binding,
        "passed_items": _passed_items(validation, audit, chain),
        "hard_conflicts": deepcopy(audit.get("hard_conflicts", [])) if audit else [],
        "obligations": deepcopy(audit["planned_obligations"]) if audit else _planned_obligations(proposal),
        "obligations_binding": "final_machine_audit" if audit else "proposal_only_unverified",
        "evidence_gaps": gaps, "requirement_accounting": accounting,
        "final_machine_audit": deepcopy(audit),
        "runtime_acceptance": {"status": "not_verified", "runtime_verified": False,
            "authority": "formal_mvg_acceptance_mode_run"}}
    report["report_sha256"] = canonical_sha(report)
    return report


def bound_report(trace, manifest, manifest_path):
    """Read the same report only after the consumer binds the published manifest."""
    report = trace.get(FIELD)
    if report is None:
        return unavailable()
    try:
        _validate_public_report(report, trace)
        unsigned = {key: value for key, value in report.items() if key != "report_sha256"}
        binding = report["binding"]
        audit = report["final_machine_audit"]
        projection = {key: trace[key] for key in binding["proposal_fields"]}
        digest = text_sha(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        if (report.get("schema_version") != PROTOCOL or report.get("report_sha256") != canonical_sha(unsigned)
                or binding["manifest_path"] != manifest_path or binding["manifest_sha256"] != digest
                or binding["trace_projection_sha256"] != canonical_sha(projection)
                or not isinstance(binding.get("chain"), dict) or not isinstance(audit, dict)
                or audit.get("binding") != binding["chain"]
                or binding["proposal_sha256"] != binding["chain"].get("proposal_sha256")
                or binding["analysis_identity_sha256"] != binding["chain"].get("analysis_identity_sha256")
                or binding["run_id"] != binding["chain"].get("run_id")
                or report.get("status") != "complete" or report.get("planning_complete") is not True
                or audit.get("complete_chain") is not True or audit.get("status") != "passed"
                or audit.get("hard_conflicts") or audit.get("evidence_gaps")
                or report.get("hard_conflicts") or report.get("evidence_gaps")
                or report.get("runtime_acceptance", {}).get("status") != "not_verified"
                or report.get("runtime_acceptance", {}).get("runtime_verified") is not False):
            raise ValueError("completion_binding_changed")
    except (ValueError, KeyError, TypeError, AttributeError):
        return unavailable("Final planning completion report is invalid or does not match this manifest/trace.")
    return deepcopy(report)


def _strings(value):
    return isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)


def _digest(value):
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


def _validate_public_report(report, trace):
    """Validate the existing machine projection without a new authority layer."""
    from _mvg_global_audit import AUDIT_SCHEMA
    if (not isinstance(report, dict) or not {"schema_version", "status", "planning_complete", "binding",
            "passed_items", "hard_conflicts", "obligations", "obligations_binding", "evidence_gaps",
            "requirement_accounting", "final_machine_audit", "runtime_acceptance", "report_sha256"} <= report.keys()):
        raise ValueError("completion_fields_missing")
    binding, audit = report["binding"], report["final_machine_audit"]
    if (not isinstance(binding, dict) or not isinstance(audit, dict)
            or not {"run_id", "analysis_identity_sha256", "manifest_path", "manifest_sha256", "proposal_sha256",
                "proposal_fields", "trace_projection_sha256", "chain", "audit_ref"} <= binding.keys()
            or not _strings(binding["proposal_fields"]) or len(set(binding["proposal_fields"])) != len(binding["proposal_fields"])
            or not isinstance(binding["run_id"], str) or not binding["run_id"]
            or not isinstance(binding["manifest_path"], str) or not binding["manifest_path"]
            or any(not _digest(binding[field]) for field in ("analysis_identity_sha256", "manifest_sha256",
                "proposal_sha256", "trace_projection_sha256"))):
        raise ValueError("completion_binding_shape_invalid")
    chain, pointer = binding["chain"], binding["audit_ref"]
    if (not isinstance(chain, dict) or not {"run_id", "analysis_identity_sha256", "prepared_index_sha256",
            "checkpoint_head", "selected_sha256", "proposal_sha256", "generation", "budget"} <= chain.keys()
            or any(not _digest(chain[field]) for field in ("analysis_identity_sha256", "prepared_index_sha256",
                "selected_sha256", "proposal_sha256"))
            or type(chain["generation"]) is not int or chain["generation"] < 1
            or not isinstance(chain["budget"], dict)
            or (chain["checkpoint_head"] is not None and not isinstance(chain["checkpoint_head"], dict))
            or not isinstance(pointer, dict) or set(pointer) != {"path", "sha256"}
            or pointer["path"] != "global-audits/" + canonical_sha(audit)[7:] + ".json"
            or pointer["sha256"] != text_sha(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")):
        raise ValueError("completion_audit_reference_invalid")
    if (audit.get("schema_version") != AUDIT_SCHEMA
            or not {"binding", "status", "complete_chain", "conflict_report", "hard_conflicts", "evidence_gaps",
                "resolved_reopened_conflicts", "ordinary_overlaps", "passed_checks", "planned_obligations",
                "runtime_verified", "claim"} <= audit.keys()
            or not _strings(audit["passed_checks"]) or not audit["passed_checks"]
            or any(not isinstance(audit[field], list) for field in ("hard_conflicts", "evidence_gaps",
                "resolved_reopened_conflicts", "ordinary_overlaps"))
            or audit["runtime_verified"] is not False or not isinstance(audit["claim"], str)):
        raise ValueError("completion_audit_shape_invalid")
    obligations = report["obligations"]
    if (not isinstance(obligations, dict) or set(obligations) != {"tests", "entrypoints", "manual"}
            or not _strings(obligations["tests"]) or not _strings(obligations["entrypoints"])
            or not isinstance(obligations["manual"], list)
            or obligations != audit["planned_obligations"] or obligations != _planned_obligations(trace)
            or report["obligations_binding"] != "final_machine_audit"
            or report["hard_conflicts"] != [] or report["evidence_gaps"] != []
            or not _strings(report["passed_items"]) or report["passed_items"] != _passed_items(
                {"formal_applicable": True, "status": "passed", "delta_status": "passed"}, audit, chain)
            or report["runtime_acceptance"] != {"status": "not_verified", "runtime_verified": False,
                "authority": "formal_mvg_acceptance_mode_run"}):
        raise ValueError("completion_projection_invalid")
    accounting = report["requirement_accounting"]
    if (not isinstance(accounting, dict) or not {"requirements", "accounted_count", "satisfied_count",
            "evidence_count", "planning_complete"} <= accounting.keys()
            or not isinstance(accounting["requirements"], list)
            or any(type(accounting[key]) is not int or accounting[key] < 0
                for key in ("accounted_count", "satisfied_count", "evidence_count"))
            or accounting["planning_complete"] is not True
            or any(not isinstance(row, dict) or type(row.get("satisfied")) is not bool
                or row.get("accounted") is not True for row in accounting["requirements"])):
        raise ValueError("completion_accounting_shape_invalid")
    satisfied = {row["requirement_id"] for row in accounting["requirements"] if row["satisfied"]}
    valid = {(row["requirement_id"], row["evidence_id"]) for row in evidence_rows(trace)
             if row["requirement_id"] in satisfied}
    if accounting != accounting_summary(trace, valid_evidence_keys=valid):
        raise ValueError("completion_accounting_projection_invalid")
