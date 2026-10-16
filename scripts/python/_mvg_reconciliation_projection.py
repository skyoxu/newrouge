"""Deterministic model-only reconciliation views; original sources stay immutable."""
from copy import deepcopy
import json

from _planning_skill_common import canonical_sha

SCHEMA = "newrouge.mvg-reconciliation-projection.v1"
SCOPE_SCHEMA = "newrouge.mvg-scoped-evidence.v2"
LEGACY_SCOPE_SCHEMA = "newrouge.mvg-scoped-evidence.v1"


def project_source(source, *, requirement_ids, task_ids, source_block_ids, capability_ids):
    """Exclude only proven unrelated stable rows; keep unknown and hard findings."""
    try:
        document = json.loads(source["text"].removeprefix("\ufeff"))
    except (ValueError, TypeError):
        return source
    if (not isinstance(document, dict)
            or document.get("schema_version") != "newrouge.semantic-reconciliation.v1"
            or not isinstance(document.get("findings"), list)
            or not isinstance(document.get("topology_edges", []), list)):
        return source
    domains = {"requirement": set(map(str, requirement_ids)), "task": set(map(str, task_ids)),
        "source_block": set(map(str, source_block_ids)), "capability": set(map(str, capability_ids)),
        "acceptance": set(), "test": set(), "contract": set(), "adr": set()}
    excluded, included = [], []
    result = deepcopy(document)

    def record(field, index, row, keep, reason):
        receipt = {"json_pointer": f"/{field}/{index}", "sha256": canonical_sha(row), "reason": reason}
        (included if keep else excluded).append(receipt)
        return keep

    def finding_related(row):
        if not isinstance(row, dict):
            return True
        coordinates = (("chapter3_requirement_ids", "requirement"), ("source_block_ids", "source_block"),
                       ("task_ids", "task"), ("capability_ids", "capability"))
        # Future finding formats, malformed ownership and global/unresolved hard
        # findings are not evidence of irrelevance. Deliver them in full.
        if (row.get("finding_type") != "source_semantic" or row.get("status") != "equivalent"
                or row.get("action") != "keep"):
            return True
        addressed = False
        for field, kind in coordinates:
            values = row.get(field, [])
            if not isinstance(values, list) or any(not isinstance(value, (str, int)) or isinstance(value, bool) for value in values):
                return True
            addressed |= bool(values)
            if set(map(str, values)) & domains[kind]:
                return True
        # Do not discard future ownership fields based on an obsolete schema.
        if any((key.endswith("_id") or key.endswith("_ids")) and key not in {
                "obligation_id", *(field for field, _ in coordinates)} for key in row):
            return True
        return not addressed

    result["findings"] = [deepcopy(row) for index, row in enumerate(document["findings"])
        if record("findings", index, row, finding_related(row),
                  "related_or_unclassified_or_unresolved" if finding_related(row) else "outside_requirement_task_source_block_scope")]

    def endpoint(row, prefix):
        if not isinstance(row, dict):
            return None
        kind, value = row.get(prefix + "_type"), row.get(prefix + "_id")
        if kind not in domains or not isinstance(value, (str, int)) or isinstance(value, bool):
            return None
        return kind, str(value)

    # A selected requirement/task can name an acceptance/test/contract boundary.
    # Keep its incident edges as a whole. Never expand to a foreign Requirement
    # or Task and then transitively pull the complete repository back in.
    edges = document.get("topology_edges", [])
    for row in edges:
        left, right = endpoint(row, "source"), endpoint(row, "target")
        if left is None or right is None:
            continue
        for here, other in ((left, right), (right, left)):
            if here[0] in {"requirement", "task", "source_block", "capability"} and here[1] in domains[here[0]]:
                if other[0] in {"acceptance", "test", "contract", "adr"}:
                    domains[other[0]].add(other[1])

    def edge_related(row):
        left, right = endpoint(row, "source"), endpoint(row, "target")
        if isinstance(row, dict) and set(row) - {
                "source_type", "source_id", "target_type", "target_id", "relation", "contribution"}:
            return True
        return left is None or right is None or left[1] in domains[left[0]] or right[1] in domains[right[0]]

    if "topology_edges" in document:
        result["topology_edges"] = [deepcopy(row) for index, row in enumerate(edges)
            if record("topology_edges", index, row, edge_related(row),
                      "related_boundary_or_unknown_shape" if edge_related(row) else "outside_typed_boundary_scope")]
    if not excluded:
        return source
    model_text = json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n"
    audit = {"schema_version": SCHEMA, "source_sha256": source["sha256"],
        "citation_space": "json_projection", "criteria": {key: sorted(value) for key, value in domains.items()},
        "included_rows": included, "excluded_rows": excluded,
        "original_findings": len(document["findings"]), "included_findings": len(result["findings"]),
        "original_topology_edges": len(edges), "included_topology_edges": len(result.get("topology_edges", [])),
        "projected_document_sha256": canonical_sha(result)}
    return {**source, "model_text": model_text, "model_projection": audit}


def model_source(source):
    """Expose projection and explicit citation identity, never the omitted raw text."""
    result = deepcopy(source)
    if "model_text" not in result:
        return result
    result["text"] = result.pop("model_text")
    audit = result.pop("model_projection")
    result["model_projection"] = {key: deepcopy(audit[key]) for key in (
        "schema_version", "source_sha256", "citation_space", "original_findings", "included_findings",
        "original_topology_edges", "included_topology_edges", "projected_document_sha256")}
    result["model_projection"]["audit_sha256"] = canonical_sha(audit)
    return result


def transport_sources(context):
    return [model_source(source) for source in context["evidence"]]
