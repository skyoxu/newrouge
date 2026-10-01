"""Verify Requirement accounting and independent semantic review identities."""
from pathlib import Path
from typing import Any

from _planning_skill_common import canonical_sha, file_sha, load_json, repo_path


def prepared_evidence_errors(root: Path, proposal: dict[str, Any], prepared: Path) -> list[str]:
    """Every claimed existing verification dependency must be readable and bound."""
    index = load_json(prepared / "analysis-index.json", {})
    files = index.get("files") or {}
    authority = index.get("authority_inputs") or {}
    dependencies = set()
    manifest = proposal.get("manifest_candidate") or {}
    for flow in manifest.get("flows", []):
        if not isinstance(flow, dict):
            continue
        dependencies.update(str(p) for p in flow.get("source_paths", []))
        dependencies.update(str(h.get("contract_ref") or "") for h in flow.get("handoffs", []) if isinstance(h, dict))
    dependencies.update(str(t.get("path") or "") for t in manifest.get("tests", [])
        if isinstance(t, dict) and t.get("state") == "implemented")
    dependencies.update(str(e.get("path") or "") for e in proposal.get("entrypoints", [])
        if isinstance(e, dict) and e.get("status") == "existing_verified")
    rows = [r for key in ("coverage_table", "change_reviews", "retirement_reviews")
        for r in proposal.get(key, []) if isinstance(r, dict)]
    if isinstance(proposal.get("coverage_review"), dict):
        rows.append(proposal["coverage_review"])
    for row in rows:
        for key in ("verification_ref", "authority_ref"):
            if row.get(key):
                dependencies.add(str(row[key]).split("#", 1)[0])
    errors = []
    for ref in sorted(dependencies):
        try:
            path = repo_path(root, ref)
            rel = path.relative_to(root.resolve()).as_posix()
        except ValueError:
            errors.append(f"verification_dependency_invalid_path:{ref}")
            continue
        copies = [f"{prefix}/{rel}" for prefix in ("sources", "references")]
        matched = [key for key in copies if key in files and (prepared / key).is_file()]
        expected = authority.get(rel)
        if not expected or not matched:
            errors.append(f"verification_dependency_not_prepared:{rel}")
        elif (not path.is_file() or file_sha(path) != expected
              or any(file_sha(prepared / key) != files[key] or files[key] != expected for key in matched)):
            errors.append(f"verification_dependency_drift:{rel}")
    return errors


def coverage_errors(root: Path, proposal: dict[str, Any], semantics: dict[str, Any],
                    capabilities: dict[str, Any], task_rows: list[dict[str, Any]]) -> list[str]:
    requirements = {str(r["requirement_id"]): r for r in semantics.get("requirements", [])
        if isinstance(r, dict) and r.get("status", "active") == "active" and r.get("delivery_relevant", True)}
    cap_members = {str(c["capability_id"]): set(map(str, c.get("requirement_ids", [])))
        for c in capabilities.get("capabilities", []) if isinstance(c, dict)}
    task_members: dict[int, set[str]] = {}
    for row in task_rows:
        if row.get("taskmaster_id") is not None:
            task_members.setdefault(int(row["taskmaster_id"]), set()).update(map(str,
                row.get("semantic_refs", row.get("requirement_ids", []))))
    flows = {str(f["id"]): f for f in proposal["manifest_candidate"].get("flows", []) if isinstance(f, dict)}
    rows = proposal.get("coverage_table")
    errors = []
    if not isinstance(rows, list) or not rows:
        return ["coverage_table_missing_or_empty"]
    accounted = set()
    for row in rows:
        if not isinstance(row, dict):
            errors.append("invalid_coverage_row")
            continue
        rid = str(row.get("requirement_id") or "")
        if rid not in requirements:
            errors.append(f"coverage_unknown_requirement:{rid}")
            continue
        if not str(row.get("coverage") or row.get("rationale") or "").strip():
            errors.append(f"coverage_rationale_missing:{rid}")
        disposition = row.get("disposition", "flow" if row.get("flow_id") else "")
        if disposition == "flow":
            flow = flows.get(str(row.get("flow_id")))
            cid = str(row.get("capability_ref") or "")
            tid = row.get("task_id")
            valid = (flow is not None and rid in flow.get("requirement_ids", [])
                and cid in flow.get("capability_refs", []) and rid in cap_members.get(cid, set())
                and type(tid) is int and tid in flow.get("task_ids", []))
            # A requirement's owner must be an actual reviewed task sink. Minimal
            # standalone validator fixtures without task views still check IDs.
            if task_rows and rid not in task_members.get(tid, set()):
                valid = False
            if not valid:
                errors.append(f"coverage_flow_membership_invalid:{rid}")
        elif disposition == "other_verification":
            sink = str(row.get("sink_id") or "")
            if sink not in {str(s.get("id")) for s in requirements[rid].get("non_task_sinks", []) if isinstance(s, dict)}:
                errors.append(f"coverage_non_task_sink_invalid:{rid}")
            path = str(row.get("verification_ref") or "").split("#", 1)[0]
            if not path or not repo_path(root, path).is_file():
                errors.append(f"coverage_verification_ref_missing:{rid}")
        elif disposition == "deferred":
            from update_mvg_baseline import _reviewed_authority
            try:
                _reviewed_authority(row, root)
            except ValueError as exc:
                errors.append(f"coverage_deferral_unreviewed:{rid}:{exc}")
        else:
            errors.append(f"coverage_disposition_invalid:{rid}")
        accounted.add(rid)
    errors.extend(f"coverage_requirement_missing:{rid}" for rid in sorted(set(requirements) - accounted))
    entries = proposal.get("entrypoints")
    if not isinstance(entries, list) or not entries:
        errors.append("entrypoints_missing_or_empty")
    else:
        owners = {r.get("owner_task") for r in entries if isinstance(r, dict)}
        tasks = {t for f in flows.values() for t in f.get("task_ids", [])}
        errors.extend(f"entrypoint_owner_missing:{tid}" for tid in sorted(tasks - owners))
    return errors


def semantic_review_errors(state: dict[str, Any], proposal: dict[str, Any], review: dict[str, Any],
                           semantics: dict[str, Any]) -> list[str]:
    errors = []
    if review.get("schema_version") != "newrouge.mvg-semantic-review.v1":
        return ["independent_semantic_review_missing"]
    if review.get("analysis_identity_sha256") != state["analysis_identity_sha256"]:
        errors.append("semantic_review_analysis_identity_mismatch")
    if review.get("proposal_sha256") != canonical_sha(proposal):
        errors.append("semantic_review_proposal_identity_mismatch")
    if review.get("verdict") != "approved" or review.get("findings") != []:
        errors.append("semantic_review_not_approved")
    required = {str(r["requirement_id"]) for r in semantics.get("requirements", [])
        if isinstance(r, dict) and r.get("status", "active") == "active" and r.get("delivery_relevant", True)}
    manifest = proposal.get("manifest_candidate")
    flows = {str(f["id"]) for f in (manifest if isinstance(manifest, dict) else {}).get("flows", [])}
    for key, id_key, expected, verdicts in (
        ("requirement_reviews", "requirement_id", required, {"covered", "other_verification", "deferred"}),
        ("flow_reviews", "flow_id", flows, {"sound"}),
    ):
        rows = review.get(key, [])
        if not isinstance(rows, list):
            errors.append(f"semantic_review_invalid_array:{key}")
            continue
        ids = [str(r.get(id_key)) for r in rows if isinstance(r, dict)]
        if set(ids) != expected or len(ids) != len(expected):
            errors.append(f"semantic_review_incomplete:{key}")
        if any(not isinstance(r, dict) or r.get("verdict") not in verdicts or not str(r.get("rationale") or "").strip() for r in rows):
            errors.append(f"semantic_review_invalid_verdict:{key}")
    return errors


def review_execution_errors(state: dict[str, Any], proposal: dict[str, Any], execution: dict[str, Any]) -> list[str]:
    from _planning_skill_common import validate_runner_description
    errors = []
    try:
        validate_runner_description(execution.get("runner_info") or {})
    except ValueError:
        errors.append("independent_semantic_review_isolation_missing")
    receipt = execution.get("receipt") or {}
    if (execution.get("proposal_sha256") != canonical_sha(proposal)
        or execution.get("analysis_identity_sha256") != state["analysis_identity_sha256"]
        or receipt.get("model_tools") != [] or not receipt.get("model")):
        errors.append("independent_semantic_review_execution_identity_invalid")
    return errors
