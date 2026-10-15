"""Independent Requirement route memberships and lossless legacy read projection."""
from __future__ import annotations

from copy import deepcopy
from typing import Any
from pathlib import Path
import json

FIELD = "requirement_route_memberships"
PROTOCOL = "newrouge.requirement-routes.v1"
PROJECTION = "requirement_routes_projection"


def protocol_errors(index, proposal=None):
    value = index.get('requirement_routes_protocol')
    if value is None:
        return []
    if value != PROTOCOL:
        return ['requirement_routes_protocol_unknown:' + str(value)]
    if proposal is None:
        return []
    errors = [] if FIELD in proposal else ['requirement_route_memberships_required_by_protocol']
    if PROJECTION in proposal:
        errors.append('requirement_routes_legacy_projection_forbidden_by_protocol')
    return errors


def authority_ids(semantics, capabilities=None):
    known = {str(row['requirement_id']) for row in semantics.get('requirements', [])
             if isinstance(row, dict) and row.get('status', 'active') == 'active'
             and row.get('delivery_relevant', True)}
    if capabilities is not None:
        known &= {str(rid) for row in capabilities.get('capabilities', []) for rid in row.get('requirement_ids', [])}
    return known


def trace_errors(trace, manifest, requirement_ids):
    """Validate authority and routes against real inputs and the applied projection."""
    def valid_manifest(value):
        if not isinstance(value, dict) or not isinstance(value.get('flows', []), list):
            return False
        for flow in value.get('flows', []):
            if (not isinstance(flow, dict) or not isinstance(flow.get('id'), str)
                    or not isinstance(flow.get('handoffs', []), list)
                    or any(not isinstance(row, dict) for row in flow.get('handoffs', []))
                    or not isinstance(flow.get('requirement_ids', []), list)
                    or any(not isinstance(rid, str) for rid in flow.get('requirement_ids', []))):
                return False
        return True
    if not isinstance(trace, dict) or not valid_manifest(manifest):
        return ['planning_trace_manifest_invalid']
    def normalized(value):
        result = deepcopy(value)
        result.pop('baseline_lineage', None)
        for flow in result.get('flows', []):
            for handoff in flow.get('handoffs', []):
                for key in ('contract_refs', 'from', 'to'):
                    if handoff.get(key) is None:
                        handoff.pop(key, None)
        return result
    original = trace.get('manifest_candidate')
    applied = trace.get('applied_manifest_candidate', original)
    if (not valid_manifest(original) or not valid_manifest(applied)
            or normalized(applied) != normalized(manifest) or normalized(original) != normalized(applied)):
        return ['planning_trace_manifest_projection_mismatch']
    rows = trace.get('coverage_table')
    if not isinstance(rows, list):
        return ['planning_trace_coverage_not_array']
    errors, seen = [], set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f'planning_trace_coverage_row_invalid:{index}')
            continue
        rid = row.get('requirement_id')
        if not isinstance(rid, str) or rid not in requirement_ids:
            errors.append(f'planning_trace_unknown_requirement:{rid}')
        if isinstance(rid, str):
            if rid in seen:
                errors.append(f'coverage_requirement_duplicate:{rid}')
            seen.add(rid)
    projected = {**trace, 'manifest_candidate': manifest}
    errors += route_errors(projected, requirement_ids)
    from _mvg_requirement_accounting import (accounting_errors, protocol_errors as accounting_protocol_errors,
        VERIFICATION, EVIDENCE, PROTOCOL_FIELD, PROTOCOL as ACCOUNTING_PROTOCOL)
    if any(key in trace for key in (VERIFICATION, EVIDENCE, 'requirement_accounting_sources')) and trace.get(PROTOCOL_FIELD) != ACCOUNTING_PROTOCOL:
        errors.append('planning_trace_accounting_protocol_missing_or_invalid')
    errors += accounting_protocol_errors(trace, trace)
    errors += accounting_errors(projected, requirement_ids, complete=False)
    return errors


def prepared_trace(prepared: Path):
    from _planning_skill_common import file_sha, load_json
    index = load_json(prepared / 'analysis-index.json', {})
    errors = protocol_errors(index)
    if errors:
        raise ValueError(';'.join(errors))
    if index.get('requirement_routes_protocol') != PROTOCOL:
        return {}
    expected = index.get('files', {}).get('existing-planning-trace.json')
    if expected is None:
        return {}
    path = prepared / 'existing-planning-trace.json'
    if not path.is_file() or file_sha(path) != expected:
        raise ValueError('existing_planning_trace_snapshot_changed')
    return load_json(path, {})


def matching_trace(root: Path, manifest_path: Path, requirement_ids=None):
    """Select only persisted traces bound to the exact current manifest content."""
    from _mvg_manifest import manifest_sha256
    target = manifest_path.resolve().relative_to(root.resolve()).as_posix()
    digest = manifest_sha256(manifest_path.read_bytes())
    current = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    if requirement_ids is None:
        from _planning_skill_common import load_json
        requirement_ids = authority_ids(load_json(root / 'logs/ci/task-generation/semantic-requirements.v1.json', {}),
            load_json(root / 'docs/planning/semantic-topology/capabilities.v1.json', {}))
    candidates = []
    for path in (root / 'docs/testing/mvg/planning').glob('*.json'):
        try:
            trace = json.loads(path.read_text(encoding='utf-8-sig'))
        except (OSError, ValueError):
            continue
        if not isinstance(trace, dict):
            continue
        if trace.get('applied_manifest_path') == target and trace.get('applied_manifest_sha256') == digest:
            errors = trace_errors(trace, current, requirement_ids)
            if errors:
                raise ValueError('existing_planning_trace_invalid:' + ';'.join(errors))
            candidates.append((str(trace.get('applied_at_utc') or ''), path.as_posix(), path))
    return max(candidates)[2] if candidates else None


def membership_schema(requirement_ids=None, flow_ids=None):
    def identifier(values):
        return {"type": "string", "enum": sorted(values)} if values is not None else {
            "type": "string", "minLength": 1}
    return {"type": "array", "items": {"type": "object", "properties": {
        "requirement_id": identifier(requirement_ids), "flow_id": identifier(flow_ids),
        "observable_role": {"type": "string", "minLength": 1}},
        "required": ["requirement_id", "flow_id", "observable_role"], "additionalProperties": False}}


def memberships(proposal: dict[str, Any]):
    """Project only legacy owners; explicit content, including invalid content, wins."""
    if FIELD in proposal:
        return deepcopy(proposal[FIELD])
    result = []
    for row in (proposal.get("coverage_table") or []):
        if isinstance(row, dict) and row.get("flow_id") and row.get("disposition", "flow") == "flow":
            rationale = row.get('rationale')
            result.append({"requirement_id": row.get("requirement_id"), "flow_id": row["flow_id"],
                           "observable_role": rationale if isinstance(rationale, str) and rationale.strip()
                           else row.get("coverage", "")})
    return result


def project_routes(proposal: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(proposal)
    result[FIELD] = memberships(proposal)
    if FIELD not in proposal:
        result[PROJECTION] = 'legacy_owner_only'
    return result


def pair_errors(rows) -> list[str]:
    if not isinstance(rows, list):
        return ["requirement_route_memberships_not_array"]
    errors, seen = [], set()
    for index, row in enumerate(rows):
        address = f"requirement_route_memberships[{index}]"
        if not isinstance(row, dict):
            errors.append(f"requirement_route_row_invalid:{address}")
            continue
        if set(row) != {'requirement_id', 'flow_id', 'observable_role'}:
            errors.append(f'requirement_route_fields_invalid:{address}')
        pair = (row.get("requirement_id"), row.get("flow_id"))
        if any(not isinstance(value, str) or not value.strip() for value in pair):
            errors.append(f"requirement_route_key_invalid:{address}")
            continue
        if pair in seen:
            errors.append(f"requirement_route_pair_duplicate:{pair[0]}:{pair[1]}:{address}")
        seen.add(pair)
        if not isinstance(row.get("observable_role"), str) or not row["observable_role"].strip():
            errors.append(f"requirement_route_role_missing:{pair[0]}:{pair[1]}:{address}")
    return errors


def route_errors(proposal: dict[str, Any], requirement_ids, *, complete=True) -> list[str]:
    rows = memberships(proposal)
    errors = pair_errors(rows)
    if not isinstance(rows, list):
        return errors
    manifest = proposal.get('manifest_candidate', {})
    if not isinstance(manifest, dict) or not isinstance(manifest.get('flows', []), list):
        return errors + ['requirement_route_flows_invalid']
    for index, flow in enumerate(manifest.get('flows', [])):
        if (not isinstance(flow, dict) or not isinstance(flow.get('id'), str)
                or not isinstance(flow.get('requirement_ids', []), list)
                or any(not isinstance(rid, str) for rid in flow.get('requirement_ids', []))):
            return errors + [f'requirement_route_flow_invalid:flows[{index}]']
    flows = {str(row.get("id")): row for row in proposal.get("manifest_candidate", {}).get("flows", [])
             if isinstance(row, dict)}
    known = set(requirement_ids)
    pairs = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        rid, fid = row.get("requirement_id"), row.get("flow_id")
        if not isinstance(rid, str) or not isinstance(fid, str):
            continue
        address = f"{rid}:{fid}:requirement_route_memberships[{index}]"
        pairs.add((rid, fid))
        if rid not in known:
            errors.append(f"requirement_route_unknown_requirement:{address}")
        if fid not in flows:
            errors.append(f"requirement_route_unknown_flow:{address}")
        elif rid not in flows[fid].get("requirement_ids", []):
            errors.append(f"requirement_route_flow_membership_invalid:{address}")
    # Legacy sources can establish only their recorded owner, never extra roles.
    owner_only = proposal.get(PROJECTION) == 'legacy_owner_only'
    if owner_only:
        original = {key: value for key, value in proposal.items() if key not in {FIELD, PROJECTION}}
        if rows != memberships(original):
            errors.append('requirement_routes_legacy_projection_invalid')
    elif PROJECTION in proposal:
        errors.append('requirement_routes_projection_unknown')
    if complete and FIELD in proposal and not owner_only:
        expected = {(rid, fid) for fid, flow in flows.items()
                    for rid in flow.get("requirement_ids", []) if rid in known}
        errors.extend(f"requirement_route_pair_missing:{rid}:{fid}"
                      for rid, fid in sorted(expected - pairs))
    return errors
