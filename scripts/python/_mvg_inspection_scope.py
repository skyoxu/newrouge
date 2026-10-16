"""Versioned per-batch authority projection; unknown ownership stays conservative."""
from copy import deepcopy

from _planning_skill_common import canonical_sha

SCOPE_SCHEMA = "newrouge.mvg-scoped-evidence.v3"


def inspection_core(core, parts):
    """Deliver complete related rows plus an explicit global boundary map."""
    result = deepcopy(core)
    if core.get("evidence_scope_schema") != SCOPE_SCHEMA or not parts:
        return result
    from _mvg_input_envelope import _acceptance_refs, _reference_path
    views = core.get("task_views", [])
    master = core.get("task_master", [])
    readiness = core.get("chapter5", {}).get("tasks", [])
    owners, dependencies, boundaries = {}, {}, []
    row_ids = set()

    def bind(path, task_id):
        path = _reference_path(path)
        if path:
            owners.setdefault(path, set()).add(task_id)

    for rows, id_field in ((views, "taskmaster_id"), (master, "id"), (readiness, "task_id")):
        for row in rows:
            tid = row.get(id_field) if isinstance(row, dict) else None
            # Malformed/anonymous authority cannot be assigned safely.
            if not isinstance(tid, (str, int)) or isinstance(tid, bool):
                return result
            tid = str(tid)
            row_ids.add(tid)
            for family in ("overlay_refs", "contractRefs", "test_refs", "source_refs", "adr_refs"):
                refs = row.get(family, [])
                if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
                    return result
                for ref in refs:
                    bind(ref, tid)
            for acceptance in row.get("acceptance", []):
                if "Refs:" in str(acceptance):
                    for ref in _acceptance_refs(acceptance):
                        bind(ref, tid)
            for kind in ("readiness", "reconciliation"):
                if isinstance(row.get(kind), dict):
                    bind(row[kind].get("path"), tid)
            for key in ("depends_on", "dependencies"):
                values = row.get(key, [])
                if not isinstance(values, list) or any(
                        not isinstance(value, (str, int)) or isinstance(value, bool) for value in values):
                    return result
                dependencies.setdefault(tid, set()).update(map(str, values))
            boundaries.append({"task_id": tid, "source": row.get("_source_view", id_field),
                **{key: deepcopy(row[key]) for key in ("title", "status", "semantic_refs", "requirement_ids",
                    "capability_refs", "depends_on", "dependencies", "unresolved_dependencies") if key in row}})
    # Explicit evidence is intentionally unscoped. A future/unknown path also
    # keeps all authority; a missing association is never proof of irrelevance.
    explicit = {row["path"] for row in core.get("evidence_selection", {}).get("sources", [])
                if "explicit_evidence" in row.get("reason", "").split(",")}
    paths = {part["path"] for part in parts}
    if paths & explicit or any(path not in owners for path in paths):
        return result
    selected = set().union(*(owners[path] for path in paths))
    while True:
        expanded = selected | {tid for owner in selected for tid in dependencies.get(owner, set()) if tid in row_ids}
        if expanded == selected:
            break
        selected = expanded
    result["task_views"] = [deepcopy(row) for row in views if str(row["taskmaster_id"]) in selected]
    if "task_master" in result:
        result["task_master"] = [deepcopy(row) for row in master if str(row["id"]) in selected]
    if "chapter5" in result:
        result["chapter5"]["tasks"] = [deepcopy(row) for row in readiness if str(row["task_id"]) in selected]
    result["inspection_authority_scope"] = {"schema_version": "newrouge.mvg-inspection-authority.v1",
        "task_ids": sorted(selected), "global_boundaries": boundaries,
        "complete_core_sha256": canonical_sha(core),
        "delivery": "Complete related task rows; all Requirements, source blocks, Capability and affected flows retained. "
                    "Other tasks are boundary context, not independently verified by this batch."}
    return result


def authority_delivery_errors(core, batches):
    """Require the batch union to deliver every frozen authority row exactly."""
    if core.get("evidence_scope_schema") != SCOPE_SCHEMA or not batches:
        return []
    delivered = [inspection_core(core, batch["parts"]) for batch in batches]
    for name, getter in (("task_views", lambda c: c.get("task_views", [])),
                         ("task_master", lambda c: c.get("task_master", [])),
                         ("chapter5", lambda c: c.get("chapter5", {}).get("tasks", []))):
        hashes = {canonical_sha(row) for context in delivered for row in getter(context)}
        if any(canonical_sha(row) not in hashes for row in getter(core)):
            return ["evidence_inspection_authority_incomplete:" + name]
    return []
