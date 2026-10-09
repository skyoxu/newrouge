"""Verify Requirement accounting and independent semantic review identities."""
from pathlib import Path
from typing import Any

from _planning_skill_common import canonical_sha, file_sha, load_json, normalized_file_sha, repo_path


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
        # A flow row is descriptive accounting and must not turn a model label
        # into a repository dependency.  Only dispositions that explicitly
        # claim an existing verification or authority file may contribute a
        # prepared dependency.
        disposition = str(row.get("disposition") or "")
        keys = ("verification_ref",) if disposition == "other_verification" else (
            ("authority_ref",) if disposition == "deferred" else ()
        )
        if not disposition:
            # Change/retirement/coverage review rows use authority_ref when
            # they explicitly carry a reviewed baseline decision.
            keys = ("authority_ref", "verification_ref")
        for key in keys:
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
        elif (not path.is_file() or (normalized_file_sha(path) != expected
              and file_sha(path) != expected)
              or any(file_sha(prepared / key) != files[key] for key in matched)):
            errors.append(f"verification_dependency_drift:{rel}")
    return errors


def coverage_errors(root: Path, proposal: dict[str, Any], semantics: dict[str, Any],
                    capabilities: dict[str, Any], task_rows: list[dict[str, Any]],
                    allowed_requirement_ids: set[str] | None = None) -> list[str]:
    requirements = {str(r["requirement_id"]): r for r in semantics.get("requirements", [])
        if isinstance(r, dict) and r.get("status", "active") == "active" and r.get("delivery_relevant", True)}
    if allowed_requirement_ids is not None:
        requirements = {key: value for key, value in requirements.items()
                        if key in allowed_requirement_ids}
    cap_members = {str(c["capability_id"]): set(map(str, c.get("requirement_ids", [])))
        for c in capabilities.get("capabilities", []) if isinstance(c, dict)}
    task_members: dict[int, set[str]] = {}
    for row in task_rows:
        if row.get("taskmaster_id") is not None:
            task_members.setdefault(int(row["taskmaster_id"]), set()).update(map(str,
                row.get("semantic_refs", row.get("requirement_ids", []))))
    flow_rows = [f for f in proposal["manifest_candidate"].get("flows", []) if isinstance(f, dict)]
    flows = {str(f["id"]): f for f in flow_rows}
    rows = proposal.get("coverage_table")
    errors = []
    if not isinstance(rows, list) or not rows:
        return ["coverage_table_missing_or_empty"]
    accounted = set()
    coverage_row_counts: dict[str, int] = {}
    requirement_flow_owners: dict[str, set[str]] = {}
    for flow in flow_rows:
        flow_id = str(flow.get("id") or "")
        seen_in_flow: set[str] = set()
        for value in flow.get("requirement_ids", []):
            rid = str(value)
            if rid in seen_in_flow:
                errors.append(f"flow_requirement_duplicate:{flow_id}:{rid}")
            seen_in_flow.add(rid)
            requirement_flow_owners.setdefault(rid, set()).add(flow_id)
    errors.extend(
        f"flow_requirement_multiple_routes:{rid}"
        for rid, owners in sorted(requirement_flow_owners.items())
        if len(owners) > 1
    )
    for row in rows:
        if not isinstance(row, dict):
            errors.append("invalid_coverage_row")
            continue
        rid = str(row.get("requirement_id") or "")
        coverage_row_counts[rid] = coverage_row_counts.get(rid, 0) + 1
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
            if row.get("verification_ref") or row.get("authority_ref") or row.get("authority_review"):
                errors.append(f"coverage_flow_file_ref_forbidden:{rid}")
        elif disposition == "other_verification":
            sink = str(row.get("sink_id") or "")
            if sink not in {str(s.get("id")) for s in requirements[rid].get("non_task_sinks", []) if isinstance(s, dict)}:
                errors.append(f"coverage_non_task_sink_invalid:{rid}")
            path = str(row.get("verification_ref") or "").split("#", 1)[0]
            if not path or not repo_path(root, path).is_file():
                errors.append(f"coverage_verification_ref_missing:{rid}")
            if row.get("authority_ref") or row.get("authority_review"):
                errors.append(f"coverage_other_verification_authority_forbidden:{rid}")
        elif disposition == "deferred":
            from update_mvg_baseline import _reviewed_authority
            try:
                _reviewed_authority(row, root)
            except ValueError as exc:
                errors.append(f"coverage_deferral_unreviewed:{rid}:{exc}")
            if row.get("verification_ref") or row.get("flow_id"):
                errors.append(f"coverage_deferred_route_invalid:{rid}")
        else:
            errors.append(f"coverage_disposition_invalid:{rid}")
        accounted.add(rid)
    errors.extend(
        f"coverage_requirement_duplicate:{rid}"
        for rid, count in sorted(coverage_row_counts.items())
        if count > 1
    )
    errors.extend(f"coverage_requirement_missing:{rid}" for rid in sorted(set(requirements) - accounted))
    entries = proposal.get("entrypoints")
    incumbent_projection = any("incumbent" in str(note).lower()
                               for note in (proposal.get("notes") or [])
                               if isinstance(note, str))
    if (not isinstance(entries, list) or
            (not entries and any(f.get("handoffs") for f in flows.values())
             and not incumbent_projection)):
        errors.append("entrypoints_missing_or_empty")
    # Task membership proves provenance, not executable boundary ownership.
    # Runtime boundary completeness is reviewed against Capability journeys and
    # source evidence; verification/governance owners need no synthetic API.
    if isinstance(entries, list) and entries:
        owners = {row.get("owner_task") for row in entries if isinstance(row, dict)}
        for flow_id, flow in flows.items():
            if flow.get("handoffs") and not owners.intersection(flow.get("task_ids", [])):
                errors.append(f"flow_runtime_entrypoint_missing:{flow_id}")
    return errors


def semantic_review_errors(state: dict[str, Any], proposal: dict[str, Any], review: dict[str, Any],
                           semantics: dict[str, Any],
                           allowed_requirement_ids: set[str] | None = None) -> list[str]:
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
    if allowed_requirement_ids is not None:
        required &= allowed_requirement_ids
    manifest = proposal.get("manifest_candidate")
    flows = {str(f["id"]) for f in (manifest if isinstance(manifest, dict) else {}).get("flows", [])}
    for key, id_key, expected, verdicts in (
        ("requirement_reviews", "requirement_id", required, {"covered", "other_verification", "deferred", "blocked"}),
        ("flow_reviews", "flow_id", flows, {"sound", "blocked"}),
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
        for row in rows:
            if isinstance(row, dict) and row.get("verdict") == "blocked":
                errors.append(f"semantic_review_blocked:{key}:{row.get(id_key, '')}")
    # When the reviewer echoes proposal accounting fields, bind them to the
    # exact frozen row. This prevents an approved review from silently
    # changing a Requirement's route, sink, or evidence reference.
    coverage = {
        str(row.get("requirement_id")): row
        for row in (proposal.get("coverage_table") or [])
        if isinstance(row, dict) and str(row.get("requirement_id") or "").strip()
    }
    requirement_reviews = review.get("requirement_reviews") or []
    for row in requirement_reviews:
        if not isinstance(row, dict):
            continue
        rid = str(row.get("requirement_id") or "")
        expected = coverage.get(rid)
        if not expected:
            continue
        if row.get("verdict") == "blocked":
            continue
        expected_disposition = str(expected.get("disposition") or ("flow" if expected.get("flow_id") else ""))
        verdict = str(row.get("verdict") or "")
        expected_verdict = {
            "flow": "covered", "other_verification": "other_verification",
            "deferred": "deferred",
        }.get(expected_disposition)
        if expected_verdict and verdict != "blocked" and verdict != expected_verdict:
            errors.append(f"semantic_review_accounting_disposition_mismatch:{rid}")
        for field, error_name in (
            ("flow_id", "flow"), ("sink_id", "sink"),
            ("verification_ref", "evidence"), ("authority_ref", "authority"),
        ):
            actual = str(row.get(field) or "").split("#", 1)[0].replace("\\", "/")
            expected_value = str(expected.get(field) or "").split("#", 1)[0].replace("\\", "/")
            if actual != expected_value:
                errors.append(f"semantic_review_accounting_{error_name}_mismatch:{rid}")
        actual_route = str(row.get("disposition") or row.get("route") or "").strip()
        if actual_route != expected_disposition:
            errors.append(f"semantic_review_accounting_route_mismatch:{rid}")
    return errors


def review_execution_errors(state: dict[str, Any], proposal: dict[str, Any], execution: dict[str, Any],
                            review: dict[str, Any]) -> list[str]:
    from _planning_skill_common import validate_runner_description
    errors = []
    try:
        validate_runner_description(execution.get("runner_info") or {})
    except ValueError:
        errors.append("independent_semantic_review_isolation_missing")
    receipt = execution.get("receipt") or {}
    receipt_output_sha = receipt.get("output_sha256")
    execution_output_sha = execution.get("output_sha256")
    if (execution.get("proposal_sha256") != canonical_sha(proposal)
        or execution.get("analysis_identity_sha256") != state["analysis_identity_sha256"]
        or execution.get("semantic_review_sha256") != canonical_sha(review)
        or (receipt_output_sha is not None and execution_output_sha != receipt_output_sha)
        or receipt.get("model_tools") != [] or not receipt.get("model")):
        errors.append("independent_semantic_review_output_identity_invalid")
    return errors
