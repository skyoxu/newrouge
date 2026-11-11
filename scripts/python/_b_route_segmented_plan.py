"""Deterministic plans from genuine original-owner source/funding captures.

This module does not invent source authority, semantic partitions, paid results,
or a new accounting pool. It never dispatches a model or publishes a native run.
"""
from copy import deepcopy
import math
from pathlib import Path

import _b_route_codec as codec
import _b_route_segmented_candidates as products
import _b_route_segmented_runtime as runtime
import _b_route_segmented_workflow as core

PRODUCER = "newrouge.b-route-segmented-plan-producer.v1"
AUTHORITY = "newrouge.b-route-segmented-plan-authority.v1"
PARTITIONS = ("whole", "audited-components")
OUTPUT_RESERVE = 26000
_FACTS = {"schema_version", "run_id", "planner", "source_input_identity", "domain", "funding",
          "retained_time", "registry_epoch", "source_policy", "authority_digest"}


def _require(condition, field):
    if not condition:
        raise core.SegmentedBlocked("segmented_plan_blocked:" + field)


def _same(left, right):
    return codec.canonical_digest(left) == codec.canonical_digest(right)


def _facts(root, authority):
    # Only the runtime issuer can open its genuine opaque capture. A dictionary,
    # saved plan or a copied token is not a substitute for this current action.
    facts = runtime.verify_plan_authority(root, authority)
    _require(type(facts) is dict and set(facts) == _FACTS and facts["schema_version"] == AUTHORITY,
             "original_authority_shape")
    _require(facts["planner"] in runtime.PROFILE and type(facts["domain"]) is dict,
             "original_planner_domain")
    return facts


def _groups(domain, policy):
    obligations = domain["obligations"]
    _require(type(obligations) is list and obligations, "complete_original_obligations")
    by_id = {row["obligation_id"]: row for row in obligations}
    _require(len(by_id) == len(obligations), "complete_original_obligations")
    ids = list(by_id)
    _require(all(type(oid) is str and oid for oid in ids), "original_obligation_identity")
    for row in obligations:
        _require(type(row["dependency_ids"]) is list and all(dep in by_id for dep in row["dependency_ids"]),
                 "unknown_original_dependency")
    edges = sorted([[row["obligation_id"], dependency] for row in obligations for dependency in row["dependency_ids"]])
    _require(_same(edges, domain["dependency_edges"]), "original_complete_edge_denominator")
    if policy == "whole":
        return [ids]
    _require(policy == "audited-components" and type(domain.get("original_contract")) is dict,
             "audited_partition_owner_required")
    # Dependencies are treated as undirected for scheduling: no component can
    # hide the other side of a source interaction merely because its edge points
    # the other way. No byte/token-length heuristic introduces a boundary.
    adjacent = {oid: set() for oid in ids}
    for left, right in edges:
        adjacent[left].add(right)
        adjacent[right].add(left)
    result, visited = [], set()
    for oid in ids:
        if oid in visited:
            continue
        component, pending = set(), [oid]
        while pending:
            current = pending.pop()
            if current in component:
                continue
            component.add(current)
            pending.extend(adjacent[current] - component)
        visited.update(component)
        result.append([item for item in ids if item in component])
    return result


def _schedule(domain, groups):
    manifest = domain["manifest"]
    labels = [candidate["label"] for candidate in manifest["candidates"]]
    obligations = {row["obligation_id"]: row for row in domain["obligations"]}
    segments = manifest["segments"]
    nodes, node_ids = [], {}

    def add(node_id, phase, group, candidate_labels, parents, *, final=False):
        required = {sid for oid in group for sid in obligations[oid]["segment_ids"]}
        raw_segments = (list(manifest["final_required_segments"]) if final else
                        [segment["segment_id"] for segment in segments if segment["segment_id"] in required])
        nodes.append({"node_id": node_id, "phase": phase, "ordinal": len(nodes),
            "candidate_labels": list(candidate_labels), "segment_ids": raw_segments,
            "obligation_ids": list(group), "dependencies": list(parents),
            "output_reserve": OUTPUT_RESERVE, "final": final})

    for phase, prefix, previous in (("generation", "g", None), ("synthesis", "s", "generation"),
                                     ("independent-review", "r", "synthesis")):
        for label in labels:
            for index, group in enumerate(groups):
                name = prefix + label + str(index)
                parents = [] if previous is None else [node_ids[previous, label, index]]
                add(name, phase, group, [label], parents)
                node_ids[phase, label, index] = name
    panels = []
    for index, group in enumerate(groups):
        name = "p" + str(index)
        add(name, "selection", group, labels, [node_ids["independent-review", label, index] for label in labels])
        panels.append(name)
    add("final", "selection", [row["obligation_id"] for row in domain["obligations"]], labels, panels, final=True)

    slots = []
    for label in labels:
        for index, group in enumerate(groups):
            targets = list(products.TARGETS) if index == 0 else [target for target in products.TARGETS if target != "source_identity"]
            ids = ["o" + label + "-" + str(index) + "-" + str(number) for number in range(len(targets))]
            for number, target in enumerate(targets):
                slots.append({"slot_id": ids[number], "candidate_label": label, "target": target,
                    "generation_node": node_ids["generation", label, index],
                    "synthesis_node": node_ids["synthesis", label, index], "obligation_ids": list(group),
                    "dependency_slot_ids": [sid for sid in ids if sid != ids[number]]})
    return nodes, slots


def _limits(facts, nodes):
    planner = facts["planner"]
    _profile, limit, count = runtime.PROFILE[planner]
    funding = facts["funding"]
    _require(type(funding) is dict and all(type(funding.get(key)) is int and funding[key] >= 0 for key in
        ("paid_or_unknown_before_run", "retained_profile_calls", "campaign_limit", "released",
         "maximum_native_charges", "subsequent_full_reservation")), "actual_original_funding")
    _require(funding["campaign_limit"] == 290 and funding["released"] == 0, "original_limits_or_refund")
    remaining = min(limit - funding["retained_profile_calls"], funding["maximum_native_charges"],
                    290 - funding["paid_or_unknown_before_run"] - funding["subsequent_full_reservation"])
    _require(len(nodes) <= remaining, "whole_plan_exceeds_current_original_budget")
    labels = [row["label"] for row in facts["domain"]["manifest"]["candidates"]]
    _require(len(labels) == count, "original_fixed_candidate_count")
    retained = funding.get("retained_lineage_calls")
    _require(type(retained) is dict and all(type(key) is str and type(value) is int and value >= 0
                                         for key, value in retained.items()), "actual_retained_lineages")
    time = facts["retained_time"]
    _require(type(time) is dict and set(time) == {"total_active_seconds", "lineage_active_seconds"}
             and type(time["total_active_seconds"]) in (int, float) and math.isfinite(time["total_active_seconds"])
             and time["total_active_seconds"] >= 0 and type(time["lineage_active_seconds"]) is dict,
             "original_retained_time")
    for index, label in enumerate(labels):
        lineage = "candidate-" + str(index + 1)  # Original stable native budget slot, never a business CID.
        calls = sum(node["phase"] != "selection" and label in node["candidate_labels"] for node in nodes)
        _require(calls + retained.get(lineage, 0) <= 64, "whole_plan_exceeds_original_lineage_budget")
        spent = time["lineage_active_seconds"].get(lineage, 0)
        _require(type(spent) in (int, float) and math.isfinite(spent) and spent >= 0, "original_lineage_time")
        # 3,900 is only the absolute existing maximum; original runtime still
        # requires actual runner support for its synthesis extension and assigns
        # each current timeout. This producer does not grant that extension.
        if planner == "capability":
            _require(spent + calls <= 3900, "original_lineage_time_exhausted")
    if planner == "capability":
        _require(time["total_active_seconds"] + len(nodes) <= 13500, "original_profile_time_exhausted")


def build_plan(root, authority, *, partition_policy="whole"):
    """Return a declaration from actual owner facts, never currentness approval.

    Actual source and fees are closed again after construction and at prepare.
    Future paid outputs and interactions still face original business checks,
    actual joint-review closure and the exact 70k-input/96k-context renderer.
    """
    root = Path(root).absolute()
    _require(partition_policy in PARTITIONS, "explicit_partition_policy")
    facts = _facts(root, authority)
    domain = facts["domain"]
    core.verify_manifest(root, domain["manifest"])
    groups = _groups(domain, partition_policy)
    nodes, slots = _schedule(domain, groups)
    _limits(facts, nodes)
    contract = {"schema_version": products.CONTRACT, "source_input_identity": facts["source_input_identity"],
                "slots": slots, "final_required_slot_ids": []}
    # Empty final slot seeds do not approve a summary-only final. The actual
    # product owner must prove complete original joint panels and independent
    # interaction-domain reviews before it can omit candidate bodies there.
    plan = core.build_plan(domain["manifest"], planner=facts["planner"], dimensions=domain["dimensions"],
        obligations=domain["obligations"], dependency_edges=domain["dependency_edges"], nodes=nodes,
        candidate_contract=contract)
    _require(plan["run_id"] == facts["run_id"] and _same(plan["budget"], {"native_limit": runtime.PROFILE[facts["planner"]][1],
             "campaign_limit": 290, "released": 0, "worst_case_calls": len(nodes)}), "static_plan_not_fee_authority")
    _require(_same(facts, _facts(root, authority)), "original_authority_changed_during_plan")
    return deepcopy(plan)
