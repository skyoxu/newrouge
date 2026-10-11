"""Bind Capability append execution to prepared MVG schemas and evidence."""
from __future__ import annotations

from copy import deepcopy
import json
import re
from pathlib import Path
from typing import Any

from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json, parse_model_json, validate_output_schema
from _mvg_capability_append import PROOF_SCHEMA, run_capability_append, preservation_errors

APPEND_SCHEMA = "newrouge.mvg-capability-append.v1"
INPUT_LIMIT = 850_000


def capability_scopes(capabilities, semantics, planning_scope, task_statuses=None):
    required = {str(row["requirement_id"]) for row in semantics.get("requirements", [])
                if row.get("status", "active") == "active" and row.get("delivery_relevant", True)}
    if planning_scope is not None:
        required &= set(planning_scope["requirement_ids"])
    seen = set()
    scopes = []
    ids = set()
    for cap in capabilities.get("capabilities", []):
        cid = str(cap.get("capability_id") or "")
        if not cid or cid in ids:
            raise ValueError("Capability append requires unique explicit Capability IDs")
        ids.add(cid)
        members = set(cap.get("requirement_ids", [])) & required
        if not members:
            continue
        scopes.append({"capability_id": cid, "capability": deepcopy(cap),
                       "requirement_ids": sorted(members), "new_requirement_ids": sorted(members - seen),
                       "accepted_requirement_ids": sorted(seen), "cumulative_requirement_ids": sorted(seen | members)})
        if task_statuses is not None:
            scopes[-1]["task_statuses"] = task_statuses
        seen |= members
    if not scopes or seen != required:
        raise ValueError("capability_append_requirement_membership_incomplete:" + ",".join(sorted(required - seen)))
    return scopes


def review_projection(scope, base, proposal):
    """Review every changed flow and every link to an accepted predecessor."""
    prior = {row["id"]: row for row in base["manifest_candidate"].get("flows", [])}
    flows = proposal["manifest_candidate"].get("flows", [])
    ids = {row["id"] for row in flows if row != prior.get(row["id"])
           or set(row.get("requirement_ids", [])) & set(scope["requirement_ids"])}
    entries = proposal.get("entrypoints", [])
    for row in entries:
        if row not in base.get("entrypoints", []):
            ids.update(row.get("flow_ids", []))
    # Shared runtime boundaries are indivisible review objects: include every
    # linked flow, including unchanged predecessors, until the closure stabilizes.
    while True:
        linked = {fid for row in entries if set(row.get("flow_ids", [])) & ids
                  for fid in row.get("flow_ids", [])}
        if linked <= ids:
            break
        ids |= linked
    affected = [deepcopy(row) for row in flows if row["id"] in ids]
    requirements = set(scope["requirement_ids"]) | {
        rid for row in affected for rid in row.get("requirement_ids", [])}
    # Future baseline membership is visible as context, but coverage cannot be
    # claimed before that Capability has passed its own gate.
    requirements &= set(scope["cumulative_requirement_ids"])
    result = deepcopy(proposal)
    result["manifest_candidate"]["flows"] = affected
    result["coverage_table"] = [row for row in result["coverage_table"] if row["requirement_id"] in requirements]
    test_ids = {tid for row in affected for tid in row.get("test_ids", [])}
    result["tests"] = [row for row in result.get("tests", []) if row["id"] in test_ids]
    result["manifest_candidate"]["tests"] = deepcopy(result["tests"])
    result["entrypoints"] = [row for row in result.get("entrypoints", []) if set(row.get("flow_ids", [])) & ids]
    result["manifest_candidate"].setdefault("coverage", {})["required_flow_ids"] = [row["id"] for row in affected]
    return result, requirements


def seed_proposal(state, prepared):
    import plan_mvg as pm
    baseline = load_json(prepared / "existing-manifest.json", None)
    statuses = {str(row["id"]): row.get("status", "") for row in load_json(prepared / "task-master.json", {}).get("master", {}).get("tasks", [])}
    manifest = deepcopy(baseline) if baseline else pm.build_manifest_skeleton(state["run_id"], [], statuses)
    return {"schema_version": pm.PROPOSAL_SCHEMA, "analysis_identity_sha256": state["analysis_identity_sha256"],
            "planning_status": "ready_for_validation", "manifest_candidate": manifest,
            "coverage_table": [], "entrypoints": [], "tests": deepcopy(manifest.get("tests", [])),
            "gaps": [], "manual_obligations": [], "change_reviews": [], "retirement_reviews": [],
            "coverage_review": {}, "notes": []}


def append_output_schema(state, scope, base, prepared):
    import plan_mvg as pm
    planning_scope = state.get("planning_scope")
    refs = sorted({path.relative_to(prepared / family).as_posix()
                   for family in ("sources", "references") for path in (prepared / family).rglob("*") if path.is_file()})
    contracts = [ref for ref in refs if ref.startswith("Game.Core/Contracts/") and ref.endswith(".cs")]
    known_capabilities = [cap["capability_id"] for cap in load_json(prepared / "capabilities.v1.json", {}).get("capabilities", [])]
    flows = planning_scope.get("flow_ids") if planning_scope else None
    tests = planning_scope.get("test_ids") if planning_scope else None
    properties = {"schema_version": {"type": "string", "const": APPEND_SCHEMA},
                  "analysis_identity_sha256": {"type": "string", "const": state["analysis_identity_sha256"]},
                  "capability_id": {"type": "string", "const": scope["capability_id"]},
                  "base_sha256": {"type": "string", "const": canonical_sha(base)}}
    for section, field in (("flows", "flows"), ("coverage", "coverage_table"),
                           ("entrypoints", "entrypoints"), ("tests", "tests")):
        schema = pm.segment_output_schema(section=section, identity=state["analysis_identity_sha256"],
            scope_id="routing", available_source_paths=refs, available_contract_paths=contracts,
            available_reference_paths=refs, allowed_flow_ids=flows, allowed_test_ids=tests,
            allowed_requirement_ids=scope["cumulative_requirement_ids"],
            allowed_change_ids=flows if flows else None,
            allow_planned_verification=bool((planning_scope or {}).get("allow_planned_verification")))
        if section == "flows":
            # Future cumulative membership is context from the frozen baseline;
            # exclusive new coverage is still bound to this Capability below.
            schema["properties"][field]["items"]["properties"]["requirement_ids"]["items"] = {
                "type": "string", "enum": sorted(set(scope["cumulative_requirement_ids"]) | {
                    rid for flow in base["manifest_candidate"].get("flows", []) for rid in flow.get("requirement_ids", [])})}
        properties[field] = schema["properties"][field]
        if section == "flows":
            properties[field]["items"]["properties"]["capability_refs"]["items"] = {
                "type": "string", "enum": known_capabilities}
        if section == "tests":
            for variant in properties[field]["items"]["anyOf"]:
                if variant["properties"]["kind"].get("const") == "dotnet":
                    variant["properties"]["selector"] = {"type": "string", "pattern": "^[A-Za-z_][A-Za-z0-9_.]+$"}
        if section == "coverage":
            properties[field]["items"]["properties"]["capability_ref"] = {
                "anyOf": [{"type": "string", "const": scope["capability_id"]}, {"type": "null"}]}
            properties[field]["items"]["properties"]["requirement_id"] = (
                {"type": "string", "enum": scope["new_requirement_ids"]} if scope["new_requirement_ids"]
                else {"type": "string", "const": ""})
            properties[field].update(minItems=len(scope["new_requirement_ids"]), maxItems=len(scope["new_requirement_ids"]))
        if section == "flows" and "change_reviews" in schema["properties"]:
            properties["change_reviews"] = schema["properties"]["change_reviews"]
    if "change_reviews" not in properties:
        properties["change_reviews"] = {"type": "array", "items": {
            "type": "object", "properties": {}, "required": [], "additionalProperties": False}, "maxItems": 0}
    properties["gaps"] = {"type": "array", "items": {"type": "string", "minLength": 1}}
    properties["notes"] = {"type": "array", "items": {"type": "string", "minLength": 1}}
    return {"type": "object", "properties": properties, "required": list(properties), "additionalProperties": False}


def complete_scope_context(prepared, scope, base, proposal=None):
    """Never truncate a selected Requirement, Acceptance or evidence file."""
    import plan_mvg as pm
    semantics = load_json(prepared / "semantic-requirements.v1.json", {})
    rids = set(scope["requirement_ids"])
    affected, _ = review_projection(scope, base, proposal or base)
    rids |= {rid for flow in affected["manifest_candidate"]["flows"] for rid in flow.get("requirement_ids", [])}
    requirements = [row for row in semantics["requirements"] if row["requirement_id"] in rids]
    owners = {tid for flow in affected["manifest_candidate"]["flows"] for tid in flow.get("task_ids", [])}
    owners |= {row.get("owner_task") for row in affected.get("entrypoints", []) + affected.get("tests", [])
               if row.get("owner_task") is not None}
    views = [row for name in ("tasks_back.json", "tasks_gameplay.json")
             for row in load_json(prepared / "task-views" / name, [])
             if set(row.get("semantic_refs", row.get("requirement_ids", []))) & rids
             or row.get("taskmaster_id") in owners]
    tids = {row.get("taskmaster_id") for row in views} | owners
    tasks = [row for row in load_json(prepared / "task-master.json", {}).get("master", {}).get("tasks", []) if row["id"] in tids]
    block_ids = set(scope["capability"].get("source_block_ids", [])) | {
        block for row in requirements for block in row.get("source_block_ids", [])}
    ledger = load_json(prepared / "source-blocks.v1.json", {})
    blocks = [row for row in ledger.get("blocks", []) if row.get("block_id") in block_ids]
    if block_ids - {row.get("block_id") for row in blocks}:
        raise ValueError("capability_append_source_blocks_missing")
    dependencies = pm._review_reference_paths(affected)
    for family in ("coverage_table", "change_reviews", "retirement_reviews"):
        for row in affected.get(family, []):
            for field in ("authority_ref", "verification_ref"):
                if row.get(field):
                    dependencies.add(str(row[field]).split("#", 1)[0])
    dependencies |= {str(ref).split("#", 1)[0] for row in views
                     for field in ("contractRefs", "test_refs", "source_refs") for ref in row.get(field, [])}
    evidence = []
    for ref in sorted(dependencies):
        path = pm._prepared_reference(prepared, ref)
        # Source-document blocks above carry the design evidence. Other named
        # references retain their complete text or explicitly show absence.
        if path is not None and path.is_file():
            evidence.append({"path": ref, "sha256": file_sha(path), "text": path.read_text(encoding="utf-8")})
        else:
            evidence.append({"path": ref, "status": "not_prepared"})
    return {"scope": scope, "requirements": requirements, "source_blocks": blocks,
            "task_views": views, "task_master": tasks, "evidence": evidence,
            "capabilities": load_json(prepared / "capabilities.v1.json", {}),
            "available_reference_paths": sorted({p.relative_to(prepared / family).as_posix()
                for family in ("sources", "references") for p in (prepared / family).rglob("*") if p.is_file()})}


def bounded_request(prompt, schema):
    from _capability_input_integrity import configured_input_limit, measure_request
    return measure_request(prompt + "\n" + json.dumps(schema, ensure_ascii=False),
        max_bytes=INPUT_LIMIT, max_input_tokens=configured_input_limit())


def preflight_runner_payload(attempt_root, attempt, prompt, schema, output_name):
    """Measure the isolated runner's fully wrapped, schema-bearing request."""
    from _capability_input_integrity import check_workspace_request, configured_input_limit
    from openai_isolated_model_runner import workspace_payload
    relative_output = Path(output_name)
    prompt_stem = relative_output.with_suffix("").as_posix().replace("/", "-")
    sandbox = attempt_root / "llm-sandbox" / f"attempt-{attempt}" / prompt_stem
    sandbox.mkdir(parents=True, exist_ok=True)
    prompt_path = sandbox / f"prompt-{attempt}-{prompt_stem}.txt"
    schema_path = sandbox / "output-schema.json"
    prompt_path.write_text(prompt, encoding="utf-8", newline="\n")
    atomic_json(schema_path, schema)
    output_path = sandbox / relative_output.name
    payload = workspace_payload(sandbox, prompt_path=prompt_path, output_path=output_path, max_bytes=INPUT_LIMIT)
    return check_workspace_request(sandbox, payload, max_bytes=INPUT_LIMIT,
        max_input_tokens=configured_input_limit())


def machine_validation_issues(validation, scope, proposal):
    """Attach deterministic object addresses without parsing reviewer prose."""
    requirements = set(scope["cumulative_requirement_ids"])
    flows = proposal["manifest_candidate"].get("flows", [])
    tests = proposal.get("tests", [])
    issues = []
    def named(identifier, code):
        return bool(re.search(r"(?<![A-Za-z0-9_-])" + re.escape(str(identifier)) + r"(?![A-Za-z0-9_-])", code))
    for code in dict.fromkeys(validation["errors"] + validation["formal_blockers"]):
        detail = {"requirement_ids": sorted(rid for rid in requirements if named(rid, code)),
                  "flow_ids": sorted(row["id"] for row in flows if named(row["id"], code)),
                  "test_ids": sorted(row["id"] for row in tests if named(row["id"], code))}
        if code == "coverage_table_missing_or_empty":
            detail["requirement_ids"] = list(scope["new_requirement_ids"])
        if code == "entrypoints_missing_or_empty":
            routed = {row.get("flow_id") for row in proposal.get("coverage_table", [])
                      if row.get("requirement_id") in requirements}
            detail["flow_ids"] = sorted(row["id"] for row in flows if row.get("handoffs")
                and (set(row.get("requirement_ids", [])) & requirements or row["id"] in routed))
        if "entrypoint" in code:
            for row in proposal.get("entrypoints", []):
                address = str(row.get("path") or row.get("owner_task") or "")
                if address and code.endswith(":" + address):
                    detail["flow_ids"] = sorted(set(detail["flow_ids"]) | set(row.get("flow_ids", [])))
        issues.append({"code": code, "path": "proposal", "detail": detail})
    return issues


def repair_scope_errors(old, new, issue, scope=None):
    """Preserve valid increment rows outside the named repair dependency domain."""
    identifiers = [str(issue.get("code", "")), str(issue.get("path", ""))]
    def object_targets(value):
        if isinstance(value, dict):
            for field, body in value.items():
                if field in {"flow_id", "flow_ids", "test_id", "test_ids", "requirement_id", "requirement_ids", "target_flow_id", "source_flow_id"}:
                    identifiers.append(str(body))
                elif field in {"errors", "issues", "detail", "objects"} and isinstance(body, (dict, list)):
                    object_targets(body)
        elif isinstance(value, list):
            for body in value:
                object_targets(body)
    object_targets(issue)
    if issue.get("code") == "append_cumulative_delta_invalid" and isinstance(issue.get("detail"), str):
        # Only deterministic delta diagnostics may carry machine object
        # addresses in text. Reviewer rationale/findings never widen scope.
        identifiers.append(issue["detail"])
    detail = " ".join(identifiers)
    requirements = {row["requirement_id"] for row in old.get("coverage_table", [])}
    requirements |= set((scope or {}).get("cumulative_requirement_ids", []))
    flows = {row["id"]: row for row in old["manifest_candidate"].get("flows", [])}
    def named(identifier):
        return bool(re.search(r"(?<![A-Za-z0-9_-])" + re.escape(identifier) + r"(?![A-Za-z0-9_-])", detail))
    target_requirements = {rid for rid in requirements if named(rid)}
    target_flows = {fid for fid in flows if named(fid)}
    target_flows |= {fid for fid, row in flows.items() if set(row.get("requirement_ids", [])) & target_requirements}
    target_flows |= {row["flow_id"] for row in old.get("coverage_table", [])
                    if row["requirement_id"] in target_requirements and row.get("flow_id") in flows}
    new_flows = {row["id"]: row for row in new["manifest_candidate"].get("flows", [])}
    if issue.get("repair_action") == "reassign_route" or target_requirements - {
            row["requirement_id"] for row in old.get("coverage_table", [])}:
        target_flows |= {str(row.get("flow_id")) for proposal in (old, new)
                        for row in proposal.get("coverage_table", []) if row["requirement_id"] in target_requirements
                        and row.get("flow_id")}
        target_flows |= {fid for fid, row in new_flows.items()
                         if set(row.get("requirement_ids", [])) & target_requirements}
    target_tests = {row["id"] for row in old.get("tests", []) if named(row["id"])}
    target_flows |= {fid for fid, row in flows.items() if set(row.get("test_ids", [])) & target_tests}
    target_tests |= {tid for fid in target_flows for table in (flows, new_flows)
                    for tid in table.get(fid, {}).get("test_ids", [])}
    if not target_requirements and target_flows:
        target_requirements = {rid for fid in target_flows for rid in flows.get(fid, {}).get("requirement_ids", [])}
    errors = []
    if not target_requirements and not target_flows and not target_tests:
        errors.append("repair_target_unresolved")
    for row in old.get("coverage_table", []):
        if row["requirement_id"] not in target_requirements and row not in new.get("coverage_table", []):
            errors.append("repair_unrelated_coverage_changed:" + row["requirement_id"])
    for fid, row in flows.items():
        if fid not in target_flows and row != new_flows.get(fid):
            errors.append("repair_unrelated_flow_changed:" + fid)
    for row in old.get("tests", []):
        if row["id"] not in target_tests and row not in new.get("tests", []):
            errors.append("repair_unrelated_test_changed:" + row["id"])
    old_tests = {row["id"] for row in old.get("tests", [])}
    for row in new.get("tests", []):
        if row["id"] not in old_tests and row.get("flow_id") not in target_flows:
            errors.append("repair_unrelated_test_added:" + row["id"])
    old_entrypoints = old.get("entrypoints", [])
    for row in old_entrypoints:
        if not set(row.get("flow_ids", [])) & target_flows and row not in new.get("entrypoints", []):
            errors.append("repair_unrelated_entrypoint_changed:" + str(row.get("path", "")))
    for row in new.get("entrypoints", []):
        if row in old_entrypoints:
            continue
        matching = next((prior for prior in old_entrypoints if all(prior.get(field) == row.get(field)
            for field in ("owner_task", "path", "symbol"))), None)
        linked = set(row.get("flow_ids", []))
        if matching is None:
            if not linked or not linked <= target_flows:
                errors.append("repair_unrelated_entrypoint_added:" + str(row.get("path", "")))
        elif linked - set(matching.get("flow_ids", [])) - target_flows:
            errors.append("repair_unrelated_entrypoint_changed:" + str(row.get("path", "")))
    if canonical_sha(old) == canonical_sha(new):
        errors.append("repair_target_unchanged")
    return errors


def generate_append(root, state, candidate_root, *, invoke_factory, before_call, checkpoint):
    import plan_mvg as pm
    from _mvg_planning_review import semantic_review_errors, review_execution_errors
    prepared = candidate_root / "analysis-input"
    capabilities = load_json(prepared / "capabilities.v1.json", {})
    semantics = load_json(prepared / "semantic-requirements.v1.json", {})
    task_statuses = {str(row["id"]): str(row.get("status", "")).lower()
                    for row in load_json(prepared / "task-master.json", {}).get("master", {}).get("tasks", [])}
    scopes = capability_scopes(capabilities, semantics, state.get("planning_scope"), task_statuses)
    if 2 * len(scopes) > pm.MVG_CANDIDATE_INVOCATION_LIMIT:
        raise ValueError("capability_append_budget_insufficient_for_scope:"
                         f"minimum_calls={2 * len(scopes)};limit={pm.MVG_CANDIDATE_INVOCATION_LIMIT}")
    baseline = load_json(prepared / "existing-manifest.json", None)
    seed = seed_proposal(state, prepared)

    def request(scope, base, prior, issue, context, call):
        schema = append_output_schema(state, scope, base, prepared)
        payload = complete_scope_context(prepared, scope, base, prior)
        payload.update(accepted_proposal=base, repair_proposal=prior, hard_issue=issue,
                       planning_scope=state.get("planning_scope"))
        prompt = (
            "Generate only this Capability's MVG increment. The selected Capability is the primary input; "
            "all other objects are supporting evidence. Return the strict schema JSON. A flow may span "
            "Capabilities. Extend shared flows when useful, preserve all accepted coverage rows, tests, "
            "handoffs and outcomes. Do not enumerate tasks as APIs. Provide real runtime boundaries, "
            "testable success/failure/recovery assertions and producer/consumer roles. Planned tests and "
            "entrypoints are obligations, never runtime proof. Account exactly once for each new Requirement "
            "in this scope. Other Requirements are context, not additional coverage. Existing-manifest "
            "flows/tests remain cumulative; an explicit change_reviews authority is required for semantic "
            "membership additions to frozen flows. Do not modify another Capability's accepted mapping. "
            "Report true missing upstream semantics in gaps, never invent evidence. Repairs change only "
            "the current issue and necessary dependencies, preserve other valid increment rows. No tools.\n"
            + json.dumps(payload, ensure_ascii=False))
        attempt_number = int(load_json(candidate_root / "capability-append/append-ledger.json", {}).get("total_invocations", 0)) + 1
        preflight_runner_payload(candidate_root / "capability-append" / f"call-{attempt_number}",
            attempt_number, prompt, schema, "segments/capability-append.json")
        number = call("generate" if issue is None else "repair")
        workspace = candidate_root / "capability-append" / f"call-{number}"
        output, execution = invoke_factory(workspace)(prompt, number,
            output_name="segments/capability-append.json", output_schema_path=workspace / "output-schema.json",
            output_schema=schema)
        validate_output_schema(output, workspace / "output-schema.json")
        delta = parse_model_json(output)
        atomic_json(workspace / "generation-execution.json", execution)
        return delta

    def machine(scope, base, proposal):
        validation = pm.validate_proposal(root, state, proposal,
            append_requirement_ids=set(scope["cumulative_requirement_ids"]))
        issues = machine_validation_issues(validation, scope, proposal)
        coverage = {row["requirement_id"] for row in proposal.get("coverage_table", [])}
        expected = set(scope["cumulative_requirement_ids"])
        if coverage != expected:
            rows = [row.get("requirement_id") for row in proposal.get("coverage_table", [])]
            duplicate = sorted({rid for rid in rows if rows.count(rid) > 1})
            issues.append({"code": "append_requirement_accounting_incomplete", "path": "coverage_table",
                "detail": {"requirement_ids": sorted(expected - coverage) + duplicate}})
        if baseline:
            from update_mvg_baseline import apply_delta
            try:
                apply_delta(baseline, pm.build_delta(baseline, proposal), root=root, validate_final=True)
            except (ValueError, KeyError, TypeError) as exc:
                issues.append({"code": "append_cumulative_delta_invalid", "path": "manifest", "detail": str(exc)})
        return issues

    def semantic(scope, base, proposal, call, context):
        projection, required = review_projection(scope, base, proposal)
        schema = pm.semantic_review_output_schema(state=state, proposal=projection)
        if not projection["coverage_table"]:
            schema["properties"]["requirement_reviews"]["maxItems"] = 0
        payload = complete_scope_context(prepared, scope, base, proposal)
        payload.update(proposal=projection, accepted_proposal=base)
        prompt = (
            "Independently check this Capability increment and every affected cross-Capability handoff. "
            "The selected Capability is the primary input. Check Requirement meaning, producer/consumer "
            "roles, observable outcomes, failures/recovery, ownership, test/entrypoint feasibility, "
            "preservation of accepted mappings and source-backed cumulative changes. Unchanged predecessors "
            "are context; do not demand missing future Capability coverage. The output schema binds exact "
            "accounting and proposal identity. Review exactly each supplied coverage row and projected flow. "
            "Accept concrete planned implementation obligations without claiming runtime success. Block only "
            "real hard issues and describe each precise repair in its row. Return complete review JSON, "
            "repair_action=none for accepted rows. Do not edit the proposal. No tools.\n"
            + json.dumps(payload, ensure_ascii=False))
        attempt_number = int(load_json(candidate_root / "capability-append/append-ledger.json", {}).get("total_invocations", 0)) + 1
        preflight_runner_payload(candidate_root / "capability-append" / f"call-{attempt_number}",
            attempt_number, prompt, schema, "segments/capability-review.json")
        number = call("semantic")
        workspace = candidate_root / "capability-append" / f"call-{number}"
        output, execution = invoke_factory(workspace)(prompt, number,
            output_name="segments/capability-review.json", output_schema_path=workspace / "output-schema.json",
            output_schema=schema)
        validate_output_schema(output, workspace / "output-schema.json")
        proof = parse_model_json(output)
        shape = pm.validate_review_shape(state, projection, proof, requirement_ids=required,
                                        flow_ids={row["id"] for row in projection["manifest_candidate"]["flows"]},
                                        check_identity=True, check_accounting=True)
        if shape:
            raise ValueError("capability_review_output_invalid:" + ";".join(shape))
        receipt = execution.get("receipt", {})
        bound_execution = {"runner_info": execution.get("backend_info", {}), "receipt": receipt,
            "analysis_identity_sha256": state["analysis_identity_sha256"], "proposal_sha256": canonical_sha(projection),
            "semantic_review_sha256": canonical_sha(proof), "output_sha256": file_sha(output)}
        exec_errors = review_execution_errors(state, projection, bound_execution, proof)
        if exec_errors:
            raise ValueError("capability_review_execution_invalid:" + ";".join(exec_errors))
        errors = semantic_review_errors(state, projection, proof, semantics, required)
        specific = [code for code in errors if code.startswith("semantic_review_blocked:")]
        if specific:
            errors = [code for code in errors if code != "semantic_review_not_approved"]
        issues = []
        for code in errors:
            detail = "; ".join(proof.get("findings", []))
            intent = {}
            if code.startswith("semantic_review_blocked:"):
                _, family, identifier = code.split(":", 2)
                row = next((row for row in proof.get(family, []) if row.get("requirement_id", row.get("flow_id")) == identifier), {})
                detail = str(row.get("rationale", detail))
                intent["repair_action"] = str(row.get("repair_action") or "repair_sections")
            issues.append({"code": code, "path": "semantic-review", "detail": detail,
                           "findings": deepcopy(proof.get("findings", [])), **intent})
        return {"issues": issues, "proof": {"projection": projection, "required_requirement_ids": sorted(required),
                "review": proof}, "execution": bound_execution}

    result = run_capability_append(candidate_root / "capability-append", scopes=scopes, seed=seed,
        identity=state["analysis_identity_sha256"], propose=request, machine=machine, semantic=semantic,
        final_machine=lambda proposal: pm.candidate_admission_errors(root, state, proposal),
        invocation_limit=pm.MVG_CANDIDATE_INVOCATION_LIMIT, before_call=before_call, checkpoint=checkpoint,
        repair_check=repair_scope_errors)
    if result["status"] == "admitted":
        proof = result["proof"]
        execution = {"schema_version": "newrouge.mvg-capability-admission-execution.v1",
                     "analysis_identity_sha256": state["analysis_identity_sha256"],
                     "proposal_sha256": canonical_sha(result["accepted"]), "semantic_review_sha256": canonical_sha(proof),
                     "records_sha256": canonical_sha(proof["records"]), "total_invocations": result["total_invocations"]}
        atomic_json(candidate_root / "proposal.json", result["accepted"])
        atomic_json(candidate_root / "admission-review.json", proof)
        atomic_json(candidate_root / "admission-execution.json", execution)
    return result


def append_proof_errors(state, proposal, proof, semantics, allowed=None):
    """Revalidate the complete hash-bound chain without a final model call."""
    from _mvg_planning_review import semantic_review_errors, review_execution_errors
    required = {row["requirement_id"] for row in semantics.get("requirements", [])
                if row.get("status", "active") == "active" and row.get("delivery_relevant", True)}
    if allowed is not None:
        required &= allowed
    if (proof.get("schema_version") != PROOF_SCHEMA or proof.get("verdict") != "approved"
            or proof.get("findings") != [] or proof.get("final_machine_status") != "passed"
            or proof.get("analysis_identity_sha256") != state["analysis_identity_sha256"]
            or proof.get("proposal_sha256") != canonical_sha(proposal)):
        return ["capability_admission_identity_invalid"]
    scopes = proof.get("scopes", [])
    records = proof.get("records", [])
    if (not scopes or len(scopes) != len(records)
            or len({scope["capability_id"] for scope in scopes}) != len(scopes)
            or {rid for scope in scopes for rid in scope["requirement_ids"]} != required):
        return ["capability_admission_scope_incomplete"]
    accepted = proof.get("seed")
    if not isinstance(accepted, dict):
        return ["capability_admission_seed_missing"]
    errors = []
    seen = set()
    for scope, record in zip(scopes, records):
        from _mvg_capability_append import merge_append
        seen |= set(scope["requirement_ids"])
        if set(scope["cumulative_requirement_ids"]) != seen:
            errors.append("capability_admission_scope_order_invalid")
        if record.get("scope") != scope or record.get("base_sha256") != canonical_sha(accepted):
            return errors + ["capability_admission_chain_identity_invalid"]
        revised = merge_append(accepted, record["delta"], scope)
        if record.get("proposal_sha256") != canonical_sha(revised) or preservation_errors(accepted, revised):
            return errors + ["capability_admission_chain_mutated"]
        projection, requirements = review_projection(scope, accepted, revised)
        bound = record.get("proof") or {}
        if bound.get("projection") != projection or set(bound.get("required_requirement_ids", [])) != requirements:
            return errors + ["capability_admission_projection_changed"]
        review = bound.get("review") or {}
        errors.extend(semantic_review_errors(state, projection, review, semantics, requirements))
        errors.extend(review_execution_errors(state, projection, record.get("execution") or {}, review))
        accepted = revised
    if accepted != proposal:
        errors.append("capability_admission_final_proposal_changed")
    return errors


def append_execution_errors(state, proposal, execution, proof):
    if (execution.get("schema_version") != "newrouge.mvg-capability-admission-execution.v1"
            or execution.get("analysis_identity_sha256") != state["analysis_identity_sha256"]
            or execution.get("proposal_sha256") != canonical_sha(proposal)
            or execution.get("semantic_review_sha256") != canonical_sha(proof)
            or execution.get("records_sha256") != canonical_sha(proof.get("records"))
            or not 0 < int(execution.get("total_invocations", 0)) <= 64):
        return ["capability_admission_execution_invalid"]
    return []
