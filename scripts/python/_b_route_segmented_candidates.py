"""New segmented candidate products, never legacy model_draft/admission proofs.

Generation emits complete business objects. Synthesis resolves dependency-closed
object slots. The host assembles once and uses the original complete business
schema/source/owner/graph/accounting predicates, without fabricating old receipt
provenance. Only the common engine can supply completed-prefix authority.
"""
from __future__ import annotations

from copy import deepcopy
import json

import _b_route_codec as codec
import _b_route_candidate as candidate
import _b_route_schema_resources as schemas
import _b_route_records as records

CONTRACT = "newrouge.b-route-segmented-candidate-contract.v1"
PRODUCT = "newrouge.b-route-segmented-candidate-product.v1"
PROOF = "newrouge.b-route-segmented-candidate-proof.v1"
TARGETS = ("source_identity", "requirements", "out_of_scope_requirement_ids", "selected_dependencies",
           "definitions.flows", "definitions.commands", "definitions.states", "logical_references",
           "requirement_verification", "requirement_route_memberships", "requirement_evidence",
           "evidence_source_refs", "coverage_table", "applicability", "unresolved", "implementation_objects")


def _core():
    import _b_route_segmented_workflow as core
    return core


def validate_contract(plan):
    core = _core()
    contract = plan["candidate_contract"]
    if contract is None:
        return None
    core._keys(contract, "schema_version source_input_identity slots final_required_slot_ids", "candidate_contract")
    core._require(contract["schema_version"] == CONTRACT and type(contract["source_input_identity"]) is str
                  and contract["source_input_identity"].startswith("sha256:"), "candidate_contract.identity")
    core._require(type(contract["slots"]) is list and contract["slots"], "candidate_contract.slots")
    nodes = {n["node_id"]: n for n in plan["nodes"]}
    labels = [c["label"] for c in plan["manifest"]["candidates"]]
    slots = {}
    for row in contract["slots"]:
        core._keys(row, "slot_id candidate_label target generation_node synthesis_node obligation_ids dependency_slot_ids", "candidate_slot")
        sid = row["slot_id"]
        core._require(type(sid) is str and sid and sid not in slots and row["candidate_label"] in labels
                      and row["target"] in TARGETS, "candidate_slot.identity")
        core._strings(row["obligation_ids"], "candidate_slot.obligations")
        core._strings(row["dependency_slot_ids"], "candidate_slot.dependencies", empty=True)
        for phase, key in (("generation", "generation_node"), ("synthesis", "synthesis_node")):
            core._require(row[key] in nodes and nodes[row[key]]["phase"] == phase
                          and nodes[row[key]]["candidate_labels"] == [row["candidate_label"]]
                          and set(row["obligation_ids"]) <= set(nodes[row[key]]["obligation_ids"]), "candidate_slot.actual_phase")
        core._require(row["generation_node"] in nodes[row["synthesis_node"]]["dependencies"], "candidate_slot.original_parent")
        slots[sid] = row
    for row in slots.values():
        core._require(all(s in slots and slots[s]["candidate_label"] == row["candidate_label"] for s in row["dependency_slot_ids"]), "candidate_slot.dependency_identity")
        core._require(all(nodes[slots[s]["generation_node"]]["ordinal"] <= nodes[row["generation_node"]]["ordinal"]
                          for s in row["dependency_slot_ids"]), "candidate_slot.future_generation_dependency")
    for node in plan["nodes"]:
        if node["phase"] == "selection":
            continue
        core._require(len(node["candidate_labels"]) == 1, "candidate_view.single_identity")
        for parent in node["dependencies"]:
            core._require(nodes[parent]["candidate_labels"] == node["candidate_labels"], "candidate_view.foreign_private_parent")
    for label in labels:
        rows = [s for s in slots.values() if s["candidate_label"] == label]
        core._require({s["target"] for s in rows} == set(TARGETS)
                      and sum(s["target"] == "source_identity" for s in rows) == 1, "candidate_slot.complete_business_shape")
    core._strings(contract["final_required_slot_ids"], "candidate_contract.final_closure", empty=True)
    core._require(set(contract["final_required_slot_ids"]) <= set(slots), "candidate_contract.final_unknown_slot")
    core._require(all(not c["material_ids"] for c in plan["manifest"]["candidates"]), "candidate_contract.no_preexisting_candidate_substitution")
    return deepcopy(contract)


def expected_slots(plan, node):
    contract = plan["candidate_contract"]
    if contract is None or node["phase"] not in {"generation", "synthesis"}:
        return []
    key = "generation_node" if node["phase"] == "generation" else "synthesis_node"
    return [row for row in contract["slots"] if row[key] == node["node_id"]]


def _target_schema(target):
    validator = schemas.validator(candidate.SCHEMA, auxiliary=True)
    content = validator.schema["properties"]["content"]
    schema = content
    for key in target.split("."):
        schema = schema["properties"][key]
    return validator.evolve(schema=schema)


def verify_pieces(plan, node, pieces):
    core = _core()
    core._require(type(pieces) is list, "candidate_pieces.list")
    expected = expected_slots(plan, node)
    core._require([p.get("slot_id") for p in pieces if type(p) is dict] == [s["slot_id"] for s in expected]
                  and len(pieces) == len(expected), "candidate_pieces.complete_ordered_slots")
    for piece, slot in zip(pieces, expected):
        core._keys(piece, "slot_id value_json citations parent_piece_refs change_reason", "candidate_piece")
        core._require(type(piece["value_json"]) is str and piece["value_json"].strip(), "candidate_piece.actual_json")
        value = codec.strict_json_loads(piece["value_json"].encode("utf-8"))
        error = next(_target_schema(slot["target"]).iter_errors(value), None)
        core._require(error is None, "candidate_piece.original_business_schema." + slot["target"])
        core._require(type(piece["citations"]) is list and piece["citations"], "candidate_piece.source_citations")
        core._require(type(piece["parent_piece_refs"]) is list and type(piece["change_reason"]) is str, "candidate_piece.parent_shape")
        for parent in piece["parent_piece_refs"]:
            core._keys(parent, "slot_id raw_digest", "candidate_piece.parent_ref")
        if node["phase"] == "generation":
            core._require(piece["change_reason"] == "", "candidate_piece.not_invented_generation_revision")
    return deepcopy(pieces)


def _values(plan, results, label, phase):
    """Only called after the common engine verifies its opaque prefix."""
    core = _core()
    nodes = {n["node_id"]: n for n in plan["nodes"]}
    key = "generation_node" if phase == "generation" else "synthesis_node"
    values = {}
    for slot in plan["candidate_contract"]["slots"]:
        if slot["candidate_label"] != label:
            continue
        node_id = slot[key]
        core._require(node_id in results, "candidate_piece.missing_completed_parent")
        response = results[node_id]["response"]
        verified = verify_pieces(plan, nodes[node_id], response["candidate_pieces"])
        piece = next(p for p in verified if p["slot_id"] == slot["slot_id"])
        values[slot["slot_id"]] = {"slot": slot, "piece": piece,
            "value": codec.strict_json_loads(piece["value_json"].encode("utf-8")),
            "result_digest": results[node_id]["result_digest"]}
    return values


def _edges(values, *, include_declared=True):
    """Derive actual logical/graph use closure, not a caller-provided mask."""
    definitions, requirements = {}, {}
    for sid, row in values.items():
        target, value = row["slot"]["target"], row["value"]
        if target.startswith("definitions."):
            kind = {"flows": "flow", "commands": "command", "states": "state"}[target.split(".")[1]]
            for obj in value:
                definitions.setdefault((kind, obj["id"]), set()).add(sid)
        elif target == "requirements":
            for obj in value:
                requirements.setdefault(obj["requirement_id"], set()).add(sid)
    adjacency = {sid: set(row["slot"]["dependency_slot_ids"]) if include_declared else set() for sid, row in values.items()}
    for sid, row in values.items():
        for obj in candidate.walk(row["value"]):
            kind, did = obj.get("kind"), obj.get("definition_id")
            if kind in {"flow", "command", "state"} and type(did) is str:
                adjacency[sid].update(definitions.get((kind, did), set()))
            fid = obj.get("flow_id")
            if type(fid) is str:
                adjacency[sid].update(definitions.get(("flow", fid), set()))
            rids = obj.get("requirement_ids", [])
            if type(rids) is list:
                for rid in rids:
                    adjacency[sid].update(requirements.get(rid, set()))
            rid = obj.get("requirement_id")
            if type(rid) is str:
                adjacency[sid].update(requirements.get(rid, set()))
        adjacency[sid].discard(sid)
    return adjacency


def _closed_slots(values, seeds):
    core = _core()
    edges = _edges(values)
    seen, pending = set(seeds), list(seeds)
    while pending:
        sid = pending.pop()
        core._require(sid in values, "candidate_closure.unknown_slot")
        for dependency in edges[sid]:
            if dependency not in seen:
                seen.add(dependency)
                pending.append(dependency)
    return [sid for sid in values if sid in seen]


def derive_review_domains(plan, values, *, context=None):
    """Actual semantic-use components; this pure product is not admission.

    Reverse use edges are essential: F1 -> C <- F2 is one interaction domain,
    even when each outgoing closure alone looks complete. Unrelated definitions
    remain in separate components. Declaration-only acquisition dependencies do
    not create spurious reverse co-consumption edges.
    """
    core = _core()
    forward = _edges(values, include_declared=False)
    external = {sid: [] for sid in values}
    qualified = {}
    qualified_by_slot = {sid: set() for sid in values}
    if context is not None:
        content = _content(values)
        byte_store = records._Bytes(context["byte_store"], None)
        owners, resolve, _plans = candidate.check_owners(content, byte_store)
        dependencies = {}
        for sid, row in values.items():
            if row["slot"]["target"] == "selected_dependencies":
                for reference in row["value"]:
                    dependencies.setdefault((reference["entity_id"], reference["revision"]), []).append((sid, reference))
        for sid, row in values.items():
            for use in candidate.walk(row["value"]):
                if (use.get("kind") not in {"flow", "command", "state"} or "definition_id" not in use
                        or not ("proposed_owner_key" in use or "owner_plan_id" in use)):
                    continue
                definition = resolve(use)
                key = use["kind"], use["definition_id"]
                owner = owners[key][0]
                identity = {"kind": key[0], "definition_id": key[1], "owner": list(owner),
                            "object_digest": codec.canonical_digest(definition)}
                identity_digest = codec.canonical_digest(identity)
                qualified[identity_digest] = identity
                qualified_by_slot[sid].add(identity_digest)
                if owner[0] == "existing":
                    matches = dependencies.get((owner[1], owner[2]), [])
                    core._require(matches, "candidate.interaction_selected_owner_missing")
                    for dependency_slot, reference in matches:
                        forward[sid].add(dependency_slot)
                        external[sid].append({"path": reference["path"],
                                              "raw_digest": core._raw(byte_store.read(reference["path"])),
                                              "definition_identity": identity})
    adjacency = {sid: set(targets) for sid, targets in forward.items()}
    for source, targets in forward.items():
        for target in targets:
            core._require(target in adjacency, "candidate.interaction_unknown_actual_target")
            adjacency[target].add(source)
    domains, visited = [], set()
    order = {sid: i for i, sid in enumerate(values)}
    material = {m["material_id"]: m for m in plan["manifest"]["materials"]}
    for first in values:
        if first in visited:
            continue
        members, pending = set(), [first]
        while pending:
            sid = pending.pop()
            if sid not in members:
                members.add(sid)
                pending.extend(adjacency[sid] - members)
        visited.update(members)
        member_ids = sorted(members, key=order.get)
        obligation_ids = {o for sid in member_ids for o in values[sid]["slot"]["obligation_ids"]}
        source_segments = {s for o in plan["obligations"] if o["obligation_id"] in obligation_ids for s in o["segment_ids"]}
        originals = {codec.canonical_digest(ref): ref for sid in member_ids for ref in external[sid]}
        for original in originals.values():
            matching = {s["segment_id"] for s in plan["manifest"]["segments"] if material[s["material_id"]]["path"] == original["path"]}
            core._require(matching, "candidate.interaction_external_original_missing")
            source_segments.update(matching)
        label_set = {values[sid]["slot"]["candidate_label"] for sid in member_ids}
        core._require(len(label_set) == 1, "candidate.interaction_foreign_candidate")
        domain = {"schema_version": "newrouge.b-route-segmented-interaction-domain.v1",
                  "candidate_label": next(iter(label_set)), "member_slot_ids": member_ids,
                  "member_digests": [{"slot_id": sid, "raw_digest": core._raw(values[sid]["piece"]["value_json"].encode("utf-8"))} for sid in member_ids],
                  "interaction_edges": [[sid, target] for sid in member_ids for target in sorted(forward[sid], key=order.get) if target in members],
                  "source_obligation_ids": [o["obligation_id"] for o in plan["obligations"] if o["obligation_id"] in obligation_ids],
                  "required_original_segments": [s["segment_id"] for s in plan["manifest"]["segments"] if s["segment_id"] in source_segments],
                  "external_originals": [originals[k] for k in sorted(originals)],
                  "qualified_definition_identities": [qualified[k] for k in sorted({k for sid in member_ids for k in qualified_by_slot[sid]})]}
        domain["domain_digest"] = codec.canonical_digest(domain)
        domains.append(domain)
    return domains


def review_interaction_closure(values, seeds, domains):
    """Complete each touched joint domain, then its forward prerequisites."""
    selected = set(_closed_slots(values, seeds))
    while True:
        expanded = set(selected)
        for domain in domains:
            members = set(domain["member_slot_ids"])
            if members & selected:
                expanded.update(members)
        expanded = set(_closed_slots(values, expanded))
        if expanded == selected:
            return [sid for sid in values if sid in selected]
        selected = expanded


def _content(values):
    content = {"definitions": {"flows": [], "commands": [], "states": []}}
    for row in values.values():
        path, value = row["slot"]["target"].split("."), row["value"]
        parent = content
        for key in path[:-1]:
            parent = parent[key]
        key = path[-1]
        if row["slot"]["target"] == "source_identity":
            _core()._require(key not in parent, "candidate.source_identity_duplicate")
            parent[key] = deepcopy(value)
        else:
            parent.setdefault(key, []).extend(deepcopy(value))
    return content


def _business_check(content, context):
    """The exact original full business predicates; no old provenance wrapper."""
    core = _core()
    validator = schemas.validator(candidate.SCHEMA, auxiliary=True)
    error = next(validator.evolve(schema=validator.schema["properties"]["content"]).iter_errors(content), None)
    core._require(error is None, "candidate.complete_original_content_schema")
    byte_store = records._Bytes(context["byte_store"], None)
    owners, resolve, plans = candidate.check_owners(content, byte_store)
    blocks, scope = candidate.check_sources(content, context["frozen"], byte_store, plans)
    flows, graph = candidate.check_graph(content, owners, resolve, blocks)
    accounting = candidate.check_relations(content, flows)
    candidate.unique(content["implementation_objects"], lambda row: row["id"], "implementation_objects")
    for row in content["implementation_objects"]:
        core._require(row["availability"] != "existing" or row["target_ref"] is not None, "candidate.existing_implementation_reference")
    core._require(content["unresolved"] == [], "candidate.unresolved_business_effects")
    return {"scope": scope, "graph": graph, "accounting": accounting,
            "definitions": [{"kind": kind, "id": obj["id"], "object_digest": codec.canonical_digest(obj)}
                            for kind, plural in (("flow", "flows"), ("command", "commands"), ("state", "states"))
                            for obj in content["definitions"][plural]],
            "requirements": [{"requirement_id": r["requirement_id"], "object_digest": codec.canonical_digest(r)} for r in content["requirements"]]}


def request_contract(root, run_dir, plan, node):
    """Publish the actual business format and source identity, not guesswork."""
    if plan["candidate_contract"] is None:
        return None
    import _b_route_segmented_runtime as runtime
    context = runtime.candidate_context(root, run_dir, plan)
    runtime.verify_candidate_context(root, context)
    core = _core()
    core._require(context["frozen"]["input_identity"] == plan["candidate_contract"]["source_input_identity"], "candidate.request_actual_input")
    view = deepcopy(plan["candidate_contract"])
    if node["phase"] != "selection":
        view["slots"] = [s for s in view["slots"] if s["candidate_label"] in node["candidate_labels"]]
        local_ids = {s["slot_id"] for s in view["slots"]}
        view["final_required_slot_ids"] = [s for s in view["final_required_slot_ids"] if s in local_ids]
    required = {s["target"] for s in expected_slots(plan, node)}
    if not required:
        required = {s["target"] for s in view["slots"]}
    documents = {codec.strict_json_loads(raw)["$id"]: codec.strict_json_loads(raw) for _name, raw in schemas.resources(auxiliary=True)}
    target_schemas, resources, pending = {}, {}, []
    for target in sorted(required):
        schema = documents[candidate.SCHEMA]["properties"]["content"]
        for key in target.split("."):
            schema = schema["properties"][key]
        target_schemas[target] = deepcopy(schema)
        pending.extend((candidate.SCHEMA, v["$ref"]) for v in candidate.walk(schema) if "$ref" in v)
    while pending:
        origin, reference = pending.pop()
        identity = reference.partition("#")[0] or origin
        core._require(identity in documents, "candidate.local_business_schema_resource")
        if identity not in resources:
            resources[identity] = documents[identity]
            pending.extend((identity, v["$ref"]) for v in candidate.walk(documents[identity]) if "$ref" in v)
    inputs = context["frozen"]["inputs"]
    proof = inputs["global_proof"]
    identity_choices = {"manifest_ref": [], "ledger_ref": []}
    for path, raw in context["byte_store"].items():
        if not raw.lstrip().startswith(b"{"):
            continue
        try:
            value = codec.strict_json_loads(raw)
        except ValueError:
            continue
        for key, proof_key, owner in (("manifest_ref", "manifest", "source_manifest"), ("ledger_ref", "ledger", "source_ledger")):
            if core._same(value, proof[proof_key]):
                identity_choices[key].append({"owner": owner, "ref": path,
                                               "files": [{"path": path, "raw_digest": core._raw(raw)}]})
    core._require(all(identity_choices.values()), "candidate.actual_original_source_reference")
    view["business_format"] = {"target_schemas": target_schemas, "local_resources": resources}
    view["source_frame"] = {"contract": deepcopy(inputs["contract"]), "closure": deepcopy(inputs["closure"]),
                            "source_inventory": deepcopy(inputs["source_inventory"]),
                            "source_block_paths": {b["block_id"]: b["source_path"] for b in proof["ledger"]["blocks"]},
                            "source_identity_choices": identity_choices,
                            "source_revision": proof["manifest"]["source_revision"],
                            "source_manifest_digest": proof["manifest"]["manifest_sha256"],
                            "audited_requirements": deepcopy(proof["proposals"])}
    runtime.verify_candidate_context(root, context)
    return view


def verify_piece_source_scope(plan, node, pieces, source_frame):
    """A slot label cannot conceal a body's actual declared source uses.

    Without a qualified finer byte-region mapping, the referenced original file
    is the conservative closure. Existing external Requirement namespaces cannot
    be guessed from a matching unqualified block ID; they retain the full source
    denominator until the qualified original owner supplies a narrower mapping.
    """
    if plan["candidate_contract"] is None or node["phase"] not in {"generation", "independent-review"}:
        return
    core = _core()
    core._require(type(source_frame) is dict and type(source_frame.get("source_block_paths")) is dict, "candidate.actual_source_frame")
    paths = source_frame["source_block_paths"]
    proposals = source_frame["audited_requirements"]["proposals"]
    requirements = {r["proposal_id"]: r["source_block_ids"] for r in proposals}
    required_paths, external = set(), False
    for piece in pieces:
        value = codec.strict_json_loads(piece["value_json"].encode("utf-8"))
        for obj in candidate.walk(value):
            block_ids = obj.get("source_block_ids", [])
            if type(block_ids) is list:
                for block_id in block_ids:
                    if block_id in paths:
                        required_paths.add(paths[block_id])
                    else:
                        external = True
            rids = obj.get("requirement_ids", [])
            if type(obj.get("requirement_id")) is str:
                rids = [*rids, obj["requirement_id"]] if type(rids) is list else [obj["requirement_id"]]
            if type(rids) is list:
                for rid in rids:
                    if rid in requirements:
                        required_paths.update(paths[b] for b in requirements[rid] if b in paths)
                    else:
                        external = True
    manifest = plan["manifest"]
    materials = {m["material_id"]: m for m in manifest["materials"]}
    if external:
        required = {s["segment_id"] for s in manifest["segments"]}
    else:
        core._require(required_paths <= {m["path"] for m in manifest["materials"]}, "candidate.actual_source_original_missing_from_inventory")
        required = {s["segment_id"] for s in manifest["segments"] if materials[s["material_id"]]["path"] in required_paths}
    globals_ = {s["segment_id"] for s in manifest["segments"] if materials[s["material_id"]]["role"] == "global"}
    core._require(required <= set(node["segment_ids"]) | globals_, "candidate.actual_source_closure_not_in_current_request")


def _reviewed(plan, results, label, values, domains):
    checked, reviewed_domains, identities = set(), set(), []
    for node in plan["nodes"]:
        if node["phase"] != "independent-review" or node["candidate_labels"] != [label] or node["node_id"] not in results:
            continue
        response = results[node["node_id"]]["response"]
        for row in response["product_checks"]:
            sid = row["slot_id"]
            if row["candidate_label"] == label and sid in values:
                _core()._require(row["raw_digest"] == _core()._raw(values[sid]["piece"]["value_json"].encode("utf-8"))
                                 and row["verdict"] == "supported", "candidate.review_exact_original")
                checked.add(sid)
        original_products = results[node["node_id"]]["candidate_products"]
        verified_joint = verify_joint_checks(plan, node, response, original_products)
        for row in verified_joint:
            if row["candidate_label"] == label:
                reviewed_domains.add(row["domain_digest"])
        identities.append(results[node["node_id"]]["result_digest"])
    _core()._require(checked == set(values), "candidate.semantic_review_omission")
    _core()._require(reviewed_domains == {d["domain_digest"] for d in domains}, "candidate.joint_semantic_review_omission")
    return identities


def materials_for_node(root, run_dir, plan, node, prefix):
    core = _core()
    if plan["candidate_contract"] is None:
        return []
    results = core.verify_completed_prefix(root, plan, prefix)
    nodes = {n["node_id"]: n for n in plan["nodes"]}
    ancestors, pending = set(), list(node["dependencies"])
    while pending:
        parent = pending.pop()
        if parent not in ancestors:
            ancestors.add(parent)
            pending.extend(nodes[parent]["dependencies"])
    if node["phase"] == "generation" and not ancestors:
        return []
    import _b_route_segmented_runtime as runtime
    context = runtime.candidate_context(root, run_dir, plan)
    runtime.verify_candidate_context(root, context)
    core._require(context["frozen"]["input_identity"] == plan["candidate_contract"]["source_input_identity"], "candidate.actual_frozen_input")
    products = []
    for label in node["candidate_labels"]:
        phase = "generation" if node["phase"] in {"generation", "synthesis"} else "synthesis"
        if node["phase"] == "generation":
            values = {}
            for slot in plan["candidate_contract"]["slots"]:
                source = slot["generation_node"]
                if slot["candidate_label"] != label or source not in ancestors:
                    continue
                core._require(source in results, "candidate_generation.actual_parent_missing")
                piece = next(p for p in verify_pieces(plan, nodes[source], results[source]["response"]["candidate_pieces"]) if p["slot_id"] == slot["slot_id"])
                values[slot["slot_id"]] = {"slot": slot, "piece": piece,
                    "value": codec.strict_json_loads(piece["value_json"].encode("utf-8")),
                    "result_digest": results[source]["result_digest"], "source_node": source, "synthesized": False}
        else:
            values = _values(plan, results, label, phase)
            for row in values.values():
                row["source_node"] = row["slot"]["generation_node" if phase == "generation" else "synthesis_node"]
                row["synthesized"] = phase == "synthesis"
            if node["phase"] == "synthesis":
                for row in values.values():
                    source = row["slot"]["synthesis_node"]
                    if source in ancestors and source in results:
                        piece = next(p for p in verify_pieces(plan, nodes[source], results[source]["response"]["candidate_pieces"]) if p["slot_id"] == row["slot"]["slot_id"])
                        row.update(piece=piece, value=codec.strict_json_loads(piece["value_json"].encode("utf-8")),
                                   result_digest=results[source]["result_digest"], source_node=source, synthesized=True)
        if node["final"]:
            seeds = [s for s in plan["candidate_contract"]["final_required_slot_ids"] if s in values]
        elif node["phase"] == "generation":
            seeds = {dependency for slot in expected_slots(plan, node) for dependency in slot["dependency_slot_ids"] if dependency in values}
        else:
            seeds = [sid for sid, row in values.items() if set(row["slot"]["obligation_ids"]) & set(node["obligation_ids"])]
        domains = derive_review_domains(plan, values, context=context) if phase == "synthesis" else []
        selected = review_interaction_closure(values, seeds, domains) if domains else _closed_slots(values, seeds)
        core._require(all(values[s]["source_node"] in ancestors for s in selected), "candidate_closure.undeclared_paid_parent")
        if not node["final"]:
            core._require(all(set(values[s]["slot"]["obligation_ids"]) <= set(node["obligation_ids"]) for s in selected), "candidate_closure.missing_original_source_obligations")
        if phase == "generation":
            domain, digest, reviews = {"stage": "unassembled_generation_objects"}, None, []
        else:
            content = _content(values)
            domain = _business_check(content, context)
            domain["slot_edges"] = [[sid, target] for sid, targets in _edges(values).items() for target in sorted(targets)]
            domain["all_slot_digests"] = {sid: core._raw(row["piece"]["value_json"].encode("utf-8")) for sid, row in values.items()}
            domain["global_ids_are_metadata_not_unseen_bodies"] = True
            domain["provided_slot_ids"] = selected
            domain["interaction_domains"] = domains
            digest = codec.canonical_digest({"schema_version": PRODUCT, "protocol": core.PROTOCOL,
                "plan_digest": plan["plan_digest"], "candidate_label": label, "content": content,
                "synthesis_results": [row["result_digest"] for row in values.values()]})
            reviews = _reviewed(plan, results, label, values, domains) if node["phase"] == "selection" else []
            global_ids = {s["segment_id"] for s in plan["manifest"]["segments"]
                          if next(m for m in plan["manifest"]["materials"] if m["material_id"] == s["material_id"])["role"] == "global"}
            for joint in domains:
                if set(joint["member_slot_ids"]) & set(selected):
                    core._require(set(joint["member_slot_ids"]) <= set(selected)
                                  and set(joint["required_original_segments"]) <= set(node["segment_ids"]) | global_ids
                                  and set(joint["source_obligation_ids"]) <= set(node["obligation_ids"]),
                                  "candidate.joint_review_body_or_original_closure_missing")
        slots = []
        for sid in selected:
            row = values[sid]
            generation = results[row["slot"]["generation_node"]]["result_digest"]
            original_piece = next(p for p in results[row["slot"]["generation_node"]]["response"]["candidate_pieces"] if p["slot_id"] == sid)
            original_json = original_piece["value_json"]
            slots.append({"slot_id": sid, "target": row["slot"]["target"], "value_json": row["piece"]["value_json"],
                          "raw_digest": core._raw(row["piece"]["value_json"].encode("utf-8")),
                          "generation_value_json": original_json if row["synthesized"] and original_json != row["piece"]["value_json"] else None,
                          "generation_raw_digest": core._raw(original_json.encode("utf-8")),
                          "generation_result_digest": generation,
                          "synthesis_result_digest": row["result_digest"] if row["synthesized"] else None})
        products.append({"candidate_label": label,
                         # Only a plan-bound blinded identity enters any model
                         # request. Original native IDs remain in the host map.
                         "candidate_id": codec.canonical_digest({"plan_digest": plan["plan_digest"], "blind_label": label}),
                         "stage": ("generation-fragments" if node["phase"] == "generation" else "synthesis-inputs") if phase == "generation" else "assembled-original",
                         "content_digest": digest, "slots": slots, "object_domain": domain, "review_result_digests": reviews})
    runtime.verify_candidate_context(root, context)
    core.verify_completed_prefix(root, plan, prefix)
    return products


def verify_product_checks(plan, node, response, products):
    core = _core()
    expected = [(p["candidate_label"], s["slot_id"], s["raw_digest"]) for p in products for s in p["slots"]]
    if node["phase"] not in {"independent-review", "selection"}:
        expected = []
    checks = response["product_checks"]
    core._require(type(checks) is list and len(checks) == len(expected), "product_review.complete_denominator")
    actual = []
    for check in checks:
        core._keys(check, "candidate_label slot_id raw_digest verdict citations", "product_check")
        core._require(check["verdict"] == "supported" and type(check["citations"]) is list and check["citations"], "product_review.not_supported")
        actual.append((check["candidate_label"], check["slot_id"], check["raw_digest"]))
    core._require(actual == expected, "product_review.mixed_stale_duplicate_order")
    return deepcopy(checks)


def verify_joint_checks(plan, node, response, products):
    core = _core()
    checks = response["joint_checks"]
    core._require(type(checks) is list, "joint_review.checks_list")
    expected = []
    if node["phase"] in {"independent-review", "selection"}:
        material = {m["material_id"]: m for m in plan["manifest"]["materials"]}
        globals_ = {s["segment_id"] for s in plan["manifest"]["segments"] if material[s["material_id"]]["role"] == "global"}
        for product in products:
            provided = {s["slot_id"]: s["raw_digest"] for s in product["slots"]}
            for domain in product["object_domain"]["interaction_domains"]:
                if not set(domain["member_slot_ids"]) & set(provided):
                    continue
                core._require(set(domain["member_slot_ids"]) <= set(provided)
                              and all(provided[d["slot_id"]] == d["raw_digest"] for d in domain["member_digests"])
                              and set(domain["required_original_segments"]) <= set(node["segment_ids"]) | globals_
                              and set(domain["source_obligation_ids"]) <= set(node["obligation_ids"]),
                              "joint_review.complete_body_and_originals_required")
                expected.append({k: deepcopy(domain[k]) for k in ("candidate_label", "domain_digest", "member_digests", "interaction_edges", "source_obligation_ids")})
    core._require(len(checks) == len(expected), "joint_review.complete_domain_denominator")
    for actual, domain in zip(checks, expected):
        core._keys(actual, "candidate_label domain_digest member_digests interaction_edges source_obligation_ids verdict citations", "joint_review")
        core._require(core._same({k: actual[k] for k in domain}, domain)
                      and actual["verdict"] == "supported" and type(actual["citations"]) is list and actual["citations"],
                      "joint_review.mixed_stale_partial_or_unsupported")
    return deepcopy(checks)


def verify_piece_parents(plan, node, response, products):
    core = _core()
    if node["phase"] not in {"generation", "synthesis"} or plan["candidate_contract"] is None:
        return
    actual = [{"slot_id": s["slot_id"], "raw_digest": s["raw_digest"]} for p in products for s in p["slots"]]
    sources = {s["slot_id"]: s["value_json"] for p in products for s in p["slots"]}
    for piece in response["candidate_pieces"]:
        core._require(core._same(piece["parent_piece_refs"], actual), "candidate_piece.complete_actual_generation_parents")
        if node["phase"] == "synthesis":
            core._require(piece["slot_id"] in sources, "candidate_piece.missing_original_generation")
            core._require(piece["value_json"] == sources[piece["slot_id"]] or piece["change_reason"].strip(), "candidate_piece.unexplained_revision")


def completion_proof(root, run_dir, plan, prefix):
    core = _core()
    if plan["candidate_contract"] is None:
        return None
    results = core.verify_completed_prefix(root, plan, prefix)
    final = plan["nodes"][-1]
    products = materials_for_node(root, run_dir, plan, final, prefix)
    selected = results[final["node_id"]]["response"]["selected_label"]
    value = {"schema_version": PROOF, "protocol": core.PROTOCOL, "plan_digest": plan["plan_digest"],
             "products": [{**{k: deepcopy(v) for k, v in p.items() if k != "slots"},
                           "original_candidate_id": next(c["candidate_id"] for c in plan["manifest"]["candidates"] if c["label"] == p["candidate_label"])} for p in products],
             "selected_original_candidate": next(c["candidate_id"] for c in plan["manifest"]["candidates"] if c["label"] == selected),
             "paid_results": [{"node_id": n["node_id"], "result_digest": results[n["node_id"]]["result_digest"]} for n in plan["nodes"]],
             "new_segmented_candidate_qualified": True, "legacy_native_admission": False,
             "configured_reasoning_effort": "high", "provider_actual_reasoning": "unknown",
             "physical_model_identity": "unknown", "provider_model_identity": "unknown",
             "formal_adoption": False, "readiness": False, "b_default_active": False}
    value["proof_digest"] = codec.canonical_digest(value)
    return value


def verify_proof(root, *, run_dir, plan, proof):
    """Fresh own-protocol verification, outside any consumer locks.

    The journal's read-only mode cannot repair counters or continue publication.
    All paid protocols are replayed once in that original-owner snapshot, then
    genuine in-memory tokens are reused for local closure and host checks.
    """
    import _b_route_segmented_runtime as runtime
    import _b_route_segmented_journal as journal
    core = _core()
    core._require(plan["candidate_contract"] is not None and type(proof) is dict, "candidate_proof.production_required")
    with runtime.verified_run(root, run_dir, plan):
        with journal.open_workflow(root, run_dir=run_dir, plan=plan, read_only=True) as session:
            snapshot = session.snapshot()
            core._require(snapshot["blocked"] is None and len(snapshot["completed"]) == len(plan["nodes"]), "candidate_proof.incomplete_or_unknown")
            results = {}
            for node, item in zip(plan["nodes"], snapshot["completed"]):
                core._require(item["node_id"] == node["node_id"], "candidate_proof.prefix_order")
                token = item.get("verified_result")
                if type(token) is not core.VerifiedResult:
                    token = core.replay_verified_result(root, plan, node, item["reservation"], item["result"])
                core.validate_verified_result(plan, node, item["reservation"], token)
                core._fresh_turn(root, run_dir, plan, results, token["binding"])
                results[node["node_id"]] = token
            actual = completion_proof(root, run_dir, plan, core.capture_completed_prefix(root, plan, results))
            core._require(core._same(actual, proof), "candidate_proof.original_evidence_mismatch")
            return actual
