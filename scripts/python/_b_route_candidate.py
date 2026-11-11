"""Task-independent 3B candidate structure owner. No model or runtime execution.

Only supplied declarations and references into the current prepared byte snapshot
are checked. Ownership selection is explicit, never inferred from context labels.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path
import sys
import uuid

import _b_route_codec as codec
import _b_route_planning_input as planning
import _b_route_records as records
import _b_route_schema_resources as schemas
import _b_route_sources as sources
from _b_route_record_owners import resolve_owned_ref
from _mvg_requirement_routes import route_errors

SCHEMA = "newrouge.b-route-planning-candidate.v1"
REPORT = "newrouge.b-route-candidate-check.v1"
RULES = "declared-graph-and-relations.v1"
PARTS = {"domain_rules", "csharp_adapter", "binding", "scene"}
PLURALS = {"flow": "flows", "command": "commands", "state": "states"}


def require(condition, entity, expected, actual=None):
    sources.require(condition, entity, expected, actual)


def walk(value):
    pending = [value]
    while pending:
        item = pending.pop()
        if type(item) is dict:
            yield item
            pending.extend(item.values())
        elif type(item) is list:
            pending.extend(item)


def unique(rows, key, label):
    return records._unique(rows, path="candidate", pointer="/" + label, key=key)


def endpoint(value):
    return value["flow_id"], value["node_id"]


def reachable(start, adjacency):
    found, pending = set(), [start]
    while pending:
        node = pending.pop()
        if node in found:
            continue
        found.add(node)
        pending.extend(adjacency[node] - found)
    return found


def components(adjacency):
    """Iterative Kosaraju: long chains and rings do not depend on recursion limits."""
    seen, order = set(), []
    for start in adjacency:
        if start in seen:
            continue
        seen.add(start)
        stack = [(start, iter(adjacency[start]))]
        while stack:
            node, children = stack[-1]
            child = next(children, None)
            if child is None:
                order.append(node)
                stack.pop()
            elif child not in seen:
                seen.add(child)
                stack.append((child, iter(adjacency[child])))
    reverse = {node: set() for node in adjacency}
    for source, targets in adjacency.items():
        for target in targets:
            reverse[target].add(source)
    seen, result = set(), []
    for start in reversed(order):
        if start not in seen:
            component, pending = set(), [start]
            seen.add(start)
            while pending:
                node = pending.pop()
                component.add(node)
                for predecessor in reverse[node]:
                    if predecessor not in seen:
                        seen.add(predecessor)
                        pending.append(predecessor)
            result.append(component)
    return result


def frozen_bytes(root, prepared_ref, frozen, obs):
    prefix = Path(prepared_ref).parent.as_posix()
    rows = obs.json(prefix + "/raw-index.json")
    result = {}
    for row in rows:
        if row["archive"] is None:
            continue
        raw = obs.read(prefix + "/" + row["archive"])
        require(codec.raw_digest(raw) == row["raw_digest"]
                and frozen["inputs"]["dependencies"]["files"][row["path"]] == row["raw_digest"],
                row["path"], "exact prepared original bytes")
        result[row["path"]] = raw
    return records._Bytes(result, None)


def source_documents(source, byte_store):
    """Resolve one source identity in its own frozen manifest/ledger namespace."""
    for field in ("manifest_ref", "ledger_ref"):
        resolve_owned_ref(source[field], read_bytes=byte_store.read,
                          contract_sources=byte_store.contracts)
    manifest = codec.strict_json_loads(byte_store.read(source["manifest_ref"]["ref"].partition("#")[0]))
    ledger = codec.strict_json_loads(byte_store.read(source["ledger_ref"]["ref"].partition("#")[0]))
    require(source["source_revision"] == manifest.get("source_revision") == ledger.get("source_revision")
            and source["source_manifest_digest"] == manifest.get("manifest_sha256") == ledger.get("source_manifest_sha256"),
            "source_identity", "matching native source revision and manifest digest")
    blocks = unique(ledger["blocks"], lambda row: row["block_id"], "source_blocks")
    return manifest, ledger, blocks


def requirement_source(row, blocks, manifest):
    """Keep block meaning and relevant manifest bindings, without rekeying IDs."""
    rid = row.get("requirement_id", row.get("proposal_id"))
    refs = set(row["source_block_ids"])
    require(refs and refs <= set(blocks), rid, "known original source blocks in owning ledger", sorted(refs))
    meanings, paths = {}, set()
    for bid in refs:
        block = blocks[bid]
        path = codec.validate_reference_path(block["source_path"])
        paths.add(path)
        bindings = [binding for binding in manifest.get("sources", [])
                    if isinstance(binding, dict) and binding.get("path") == path]
        require(len(bindings) == 1, rid, "exactly one owning manifest source binding", path)
        meanings[bid] = {"block": block, "source_bindings": sorted(bindings, key=codec.canonical_digest)}
    return meanings, paths


def check_sources(content, frozen, byte_store, dependency_plans):
    inputs = frozen["inputs"]
    proof = inputs["global_proof"]
    source = content["source_identity"]
    manifest, ledger, blocks = source_documents(source, byte_store)
    require(manifest == proof["manifest"] and ledger == proof["ledger"], "source_identity",
            "current prepared native manifest and ledger")
    proposals = unique(proof["proposals"]["proposals"], lambda r: r["proposal_id"], "proposals")
    # Only exact explicitly selected effective PlanRefs contribute existing IDs.
    # JSON parsing and context category labels never activate a Requirement.
    existing, source_meanings, requirement_paths = {}, {}, {}
    for plan in dependency_plans:
        old_manifest, _old_ledger, old_blocks = source_documents(plan["source_identity"], byte_store)
        for row in plan["requirements"]:
            rid = row["requirement_id"]
            meaning, paths = requirement_source(row, old_blocks, old_manifest)
            if rid in existing:
                require(existing[rid] == row and source_meanings[rid] == meaning, rid,
                        "identical frozen Requirement body and source meaning across selected dependencies")
            else:
                existing[rid], source_meanings[rid], requirement_paths[rid] = row, meaning, paths
    global_rows = {**existing, **proposals}
    require(not (set(existing) & set(proposals)), "requirements", "separate existing and proposal identities")
    source_paths = set(inputs["closure"]["source_paths"])
    applicable = set()
    for rid, row in proposals.items():
        _meaning, requirement_paths[rid] = requirement_source(row, blocks, manifest)
    for rid in global_rows:
        if requirement_paths[rid] & source_paths:
            applicable.add(rid)
    declared = unique(content["requirements"], lambda r: r["requirement_id"], "requirements")
    require(set(declared) == applicable, "requirements", "exact governed applicable Requirement domain",
            {"missing": sorted(applicable-set(declared)), "extra": sorted(set(declared)-applicable)})
    require(set(content["out_of_scope_requirement_ids"]) == set(global_rows)-applicable,
            "out_of_scope_requirement_ids", "complete unchanged global denominator outside scope")
    for rid, row in declared.items():
        original = global_rows[rid]
        for field in ("source_block_ids", "acceptance_intent", "non_task_sinks", "prior_requirement_ids"):
            require(row[field] == original.get(field, []), rid, "preserved original " + field)
    return blocks, {"global_requirement_ids": sorted(global_rows), "applicable_requirement_ids": sorted(applicable),
                    "out_of_scope_requirement_ids": sorted(set(global_rows)-applicable)}


def check_owners(content, byte_store):
    owners, selected, originals = {}, {}, {}

    def read_reference(reference):
        ref = codec.TypedReference.from_value(reference)
        key = (ref.schema_version, ref.entity_id, ref.revision, ref.path, ref.digest, ref.verification_mode, ref.codec_version)
        if key in originals:
            return originals[key]
        raw = byte_store.read(ref.path)
        result = records.validate_record(raw, path=ref.path)
        if not result.ok:
            raise codec.CodecError(result.diagnostic)
        value = codec.strict_json_loads(raw)
        require(codec._record_identity(value) == (ref.schema_version, ref.entity_id, ref.revision),
                ref.path, "exact frozen dependency schema, ID and revision")
        require((codec.raw_digest(raw) if ref.verification_mode == "raw" else codec.canonical_digest(value)) == ref.digest,
                ref.path, "exact frozen dependency digest")
        if value["schema_version"] == "newrouge.b-route-plan.v1":
            records.plan_evidence_checks(value, ref.path)
        originals[key] = value
        return value

    refs = unique(content["selected_dependencies"], lambda r: (r["entity_id"], r["revision"]), "selected_dependencies")
    for reference in refs.values():
        ref = codec.TypedReference.from_value(reference)
        value = read_reference(reference)
        selected[(ref.entity_id, ref.revision)] = value
        for kind, plural in PLURALS.items():
            for definition in value["definitions"][plural]:
                key = kind, definition["id"]
                require(key not in owners, str(key), "one explicitly selected effective owner")
                owners[key] = (("existing", ref.entity_id, ref.revision), definition)
    for kind, plural in PLURALS.items():
        for definition in content["definitions"][plural]:
            key = kind, definition["id"]
            require(key not in owners, str(key), "one proposed or selected effective owner")
            owners[key] = (("proposed", definition["proposed_owner_key"]), definition)

    def resolve(use, expected_kind=None):
        key = use["kind"], use["definition_id"]
        require(expected_kind is None or key[0] == expected_kind, str(key), "correct definition type", expected_kind)
        require(key in owners, str(key), "declared unique effective owner")
        owner, definition = owners[key]
        requested = (("proposed", use["proposed_owner_key"]) if "proposed_owner_key" in use else
                     ("existing", use["owner_plan_id"], use["owner_revision"]))
        require(owner == requested, str(key), "exact selected owner identity", requested)
        return definition

    # Resolve the complete selected logical closure without loading any current
    # catalog or letting unselected historical revisions compete for ownership.
    pending, visited = [content, *selected.values()], set()
    effective = {codec.canonical_digest(document) for document in pending}
    typed_fields = {"path", "schema_version", "entity_id", "revision", "digest", "verification_mode", "codec_version"}
    while pending:
        document = pending.pop()
        identity = codec.canonical_digest(document)
        if identity in visited:
            continue
        visited.add(identity)
        for row in walk(document):
            if set(row) == typed_fields:
                pending.append(read_reference(row))
            if identity in effective and "definition_id" in row and "kind" in row and ("proposed_owner_key" in row or "owner_plan_id" in row):
                resolve(row)
            if set(row) == {"owner", "ref", "files"}:
                resolve_owned_ref(row, read_bytes=byte_store.read, contract_sources=byte_store.contracts)
    # The complete originals map proves reference integrity, not current scope.
    # A previous_plan_ref never activates historical Requirement dispositions.
    dependency_plans = tuple(selected.values())
    return owners, resolve, dependency_plans


def check_graph(content, owners, resolve, blocks):
    flows = {fid: definition for (kind, fid), (_owner, definition) in owners.items() if kind == "flow"}
    local_flows = content["definitions"]["flows"]
    nodes, adjacency, boundaries, state_owners = {}, {}, {}, {}
    declared_edge_count = 0
    for flow in local_flows:
        fid = flow["id"]
        require(set(flow["source_block_ids"]) <= set(blocks), fid, "known Flow source blocks")
        parts = unique(flow["parts"], lambda r: r["kind"], "parts")
        require(set(parts) == PARTS, fid, "all four applicability responsibilities exactly once")
        for field in ("ui", "human_verification"):
            obligation = flow[field]
            resolve(obligation["owner"])
            require(obligation["applicability"] != "applicable" or bool(obligation["responsibilities"]),
                    fid + "." + field, "nonempty applicable responsibility")
        if flow["ui"]["applicability"] == "applicable":
            require(all(flow["ui"][name] for name in ("inputs", "feedback", "scene_entry", "scene_return")),
                    fid + ".ui", "explicit input, feedback, scene entry and return obligations")
        for use in flow["state_owners"]:
            resolve(use, "state")
        state_owners[fid] = {codec.canonical_digest(use) for use in flow["state_owners"]}
        for node in flow["graph"]["nodes"]:
            key = fid, node["id"]
            require(key not in nodes, str(key), "unique Flow-local node")
            nodes[key], adjacency[key] = node, set()
            resolve(node["owner"])
            for field, kind in (("command_uses", "command"), ("state_uses", "state")):
                for use in node[field]:
                    resolve(use, kind)
                    if kind == "state":
                        require(codec.canonical_digest(use) in state_owners[fid], fid,
                                "direct State use represented in Flow state_owners")
        boundaries[fid] = unique(flow["graph"]["boundaries"], lambda r: r["id"], "boundaries")

    def node_ref(value):
        key = endpoint(value)
        require(key in nodes, str(key), "fully resolved graph endpoint; selected text-only plans supply no fabricated nodes")
        return key

    for flow in local_flows:
        fid = flow["id"]
        unique(flow["graph"]["edges"], lambda r: r["id"], "edges")
        for edge in flow["graph"]["edges"]:
            start, end = node_ref(edge["from"]), node_ref(edge["to"])
            require(fid in {start[0], end[0]}, fid, "edge belongs to at least one endpoint Flow")
            adjacency[start].add(end)
            declared_edge_count += 1
            resolve(edge["owner"])
        for boundary in boundaries[fid].values():
            require(node_ref(boundary["node"])[0] == fid, fid, "Flow-local boundary endpoint")
        entries = [b for b in boundaries[fid].values() if b["kind"] == "entry"]
        successes = [b for b in boundaries[fid].values() if b["kind"] == "success"]
        require(len(entries) == 1 and entries[0]["required"] and successes and all(b["required"] for b in successes),
                fid, "one required entry and nonempty required success boundaries")
        branches = unique(flow["branches"], lambda r: r["kind"], "branches")
        require(set(branches) == {"failure", "cancel", "return"}, fid, "explicit branch applicability")
        for kind, branch in branches.items():
            actual = {b["id"] for b in boundaries[fid].values() if b["kind"] == kind}
            require(set(branch["boundary_ids"]) == actual and
                    ((branch["applicability"] == "applicable") == bool(actual)), fid, "branch/boundary correspondence")
    # Check handoffs after all cross-Flow edges have been indexed.
    for flow in local_flows:
        fid = flow["id"]
        unique(flow["handoffs"], lambda r: r["id"], "handoffs")
        for handoff in flow["handoffs"]:
            start, end = node_ref(handoff["from"]), node_ref(handoff["to"])
            require(fid in {start[0], end[0]}, handoff["id"], "handoff belongs to at least one endpoint Flow")
            require(end in adjacency[start], handoff["id"], "handoff corresponds to declared graph edge")
            resolve(handoff["owner"])
            for use in handoff["state_uses"]:
                resolve(use, "state")
                require(codec.canonical_digest(use) in state_owners[fid], fid,
                        "direct State use represented in Flow state_owners")
    cyclic = sorted((group for group in components(adjacency)
                     if len(group) > 1 or any(n in adjacency[n] for n in group)), key=lambda group:tuple(sorted(group)))
    reverse = {node:set() for node in adjacency}
    for start, targets in adjacency.items():
        for target in targets:
            reverse[target].add(start)
    predecessors = {}

    def reaches_targets(starts, targets):
        for target in targets:
            if target not in predecessors:
                predecessors[target] = reachable(target, reverse)
            if not starts <= predecessors[target]:
                return False
        return True

    explained = set()
    for flow in local_flows:
        fid = flow["id"]
        entry = next(endpoint(b["node"]) for b in boundaries[fid].values() if b["kind"] == "entry")
        from_entry = reachable(entry, adjacency)
        required = {endpoint(b["node"]) for b in boundaries[fid].values() if b["required"] and b["kind"] != "entry"}
        require(required <= from_entry, fid, "required boundaries reachable from entry", sorted(required-from_entry))
        for index, group in enumerate(cyclic):
            if group & from_entry and any(n[0] == fid for n in group):
                require(reaches_targets(group, required), fid,
                        "required boundaries reachable from related cycle positions")
        unique(flow["graph"]["loops"], lambda r: r["id"], "loops")
        for loop in flow["graph"]["loops"]:
            anchors = {node_ref(a) for a in loop["anchors"]}
            relevant = {i for i, group in enumerate(cyclic) if anchors & group}
            require(relevant and anchors <= set().union(*(cyclic[i] for i in relevant)), loop["id"], "anchors in actual cyclic SCCs")
            exits = []
            for bid in loop["exit_boundary_ids"]:
                require(bid in boundaries[fid] and boundaries[fid][bid]["kind"] != "entry", loop["id"], "declared exit boundary")
                exits.append(endpoint(boundaries[fid][bid]["node"]))
            require(all(reaches_targets(cyclic[i], set(exits)) for i in relevant),
                    loop["id"], "declared exit boundaries reachable from covered SCCs")
            explained.update(relevant)
    require(explained == set(range(len(cyclic))), "loops", "exit explanation anchored to every actual cyclic SCC")
    return flows, {"node_count":len(nodes),"edge_count":declared_edge_count,
        "cyclic_components":[[list(n) for n in sorted(group)] for group in cyclic],
        "termination_proven":False,"scope":"declared endpoint, owner, required reachability and SCC facts only"}


def check_relations(content, flows):
    records.plan_relation_checks(content, "candidate")
    domain = {r["requirement_id"] for r in content["requirements"]}
    routes = {**content, "manifest_candidate":{"flows":list(flows.values())}}
    errors = route_errors(routes, domain)
    require(not errors, "requirement_route_memberships", "complete explicit route relationships", errors)
    pairs = {(r["requirement_id"],r["flow_id"]) for r in content["requirement_route_memberships"]}
    for row in content["requirement_verification"]:
        if row["disposition"] == "flow":
            require((row["requirement_id"],row["flow_id"]) in pairs, row["requirement_id"], "verification owner belongs to route")
    for row in content["requirement_evidence"]:
        require(all((row["requirement_id"],fid) in pairs for fid in row["flow_ids"]), row["evidence_id"], "same-Requirement evidence route scope")
    unresolved = unique(content["unresolved"], lambda r:r["requirement_id"], "unresolved")
    gaps = {r["requirement_id"] for r in content["requirement_verification"] if r["disposition"] == "source_gap"}
    require(set(unresolved) == gaps, "unresolved", "exact explicit source-gap domain")
    requirements = {r["requirement_id"]:r for r in content["requirements"]}
    for rid, row in unresolved.items():
        require(set(row["source_block_ids"]) <= set(requirements[rid]["source_block_ids"]), rid, "same-Requirement unresolved source blocks")
    # Shared formal pure evidence binding rules: no runtime receipt or Task gates.
    records.plan_evidence_checks(content, "candidate")
    verification = {r["requirement_id"]:r for r in content["requirement_verification"]}
    for row in content["applicability"]:
        if row["disposition"] == "other_verification":
            locator = verification[row["requirement_id"]]["verification_ref"]
            require(any(r["owner"] == "other_verification" and r["ref"] == locator for r in row["other_verification_refs"]),
                    row["requirement_id"], "applicability retains exact verification obligation")
    return {"unique_requirement_count":len(domain),"route_membership_count":len(pairs),
        "unique_evidence_count":len(content["requirement_evidence"]),"source_gap_ids":sorted(gaps),
        "completed_requirements_claimed":False}


def check_identity(value, frozen):
    """One schema/provenance/input boundary, shared by structure and admission."""
    schemas.validate(value, SCHEMA, auxiliary=True)
    require(value["input_identity"] == frozen["input_identity"], "input_identity", "exact current prepared identity")
    provenance = value["provenance"]
    if provenance["kind"] == "model_draft":
        chain = provenance["draft_chain"]
        identities = planning.validate_draft_chain(frozen, chain)
        require(len(chain) > len(frozen["transport"]["batches"]) and chain[-1]["stage"] == "synthesis",
                "draft_chain", "all original batches followed by final synthesis")
        require(identities[-1] == provenance["final_draft_identity"]
                and codec.canonical_digest(chain[-1]["content"]) == codec.canonical_digest(value["content"]),
                "draft_chain", "exact final original candidate content and identity")


def check(value, frozen, byte_store):
    """Pure structure seam; the public reader supplies CURRENT verified prepared."""
    check_identity(value, frozen)
    content = value["content"]
    owners, resolve, dependency_plans = check_owners(content, byte_store)
    blocks, scope = check_sources(content, frozen, byte_store, dependency_plans)
    flows, graph = check_graph(content, owners, resolve, blocks)
    relations = check_relations(content, flows)
    unique(content["implementation_objects"], lambda r:r["id"], "implementation_objects")
    for row in content["implementation_objects"]:
        require(row["availability"] != "existing" or row["target_ref"] is not None,
                row["id"], "existing object has exact frozen reference")
    return {"scope":scope,"graph":graph,"accounting":relations,
            "reference_claim":"frozen_content_match_only; no published/current owner authority",
            "provenance_claim":"caller declaration; input identity does not prove author read originals",
            "upstream_model_history":value["provenance"]["upstream_model_history"]}


def rules_identity():
    # The independent reader's code and exact public resources participate in the
    # check identity, without retroactively modifying frozen planning-input v1.
    import _b_route_record_owners as owner_module
    from _mvg_requirement_routes import __file__ as route_file
    paths = [Path(__file__), Path(planning.__file__), Path(records.__file__), Path(schemas.__file__),
             Path(codec.__file__), Path(sources.__file__), Path(owner_module.__file__),Path(route_file)]
    return {"version":RULES,"runtime":list(sys.version_info[:3]),"schemas":schemas.identity(auxiliary=True),
            "tools":{p.name:codec.raw_digest(p.read_bytes()) for p in paths}}


def validate(root, *, run_id, prepared_ref, candidate):
    root = planning.root_path(root)
    require(type(run_id) is str and sources.ID.fullmatch(run_id), "run_id", "safe explicit invocation ID")
    obs, output = sources.Observations(root), None
    report = {"schema_version":REPORT,"input_stage":"3b","stage":"validate-candidate","run_id":run_id,
        "status":"blocked","claim":"candidate_structure_only","formal_adoption":False,"readiness":False,
        "runtime_verified":False,"model_dispatch_count":0,"runner_dispatch_count":0,"diagnostics":[]}
    try:
        frozen = planning.load_prepared(root, prepared_ref)
        raw = obs.read(candidate)
        value = codec.strict_json_loads(raw)
        rules = rules_identity()
        report.update(input_identity=frozen["input_identity"],candidate_raw_digest=codec.raw_digest(raw),
            candidate_identity=codec.canonical_digest(value),rules_identity=rules,prepared_ref=prepared_ref)
        identity = codec.canonical_digest({"input":frozen["input_identity"],"candidate_raw":codec.raw_digest(raw),"rules":rules})
        report.update(check_identity=identity,attempt_id=identity.split(":")[1],scope_id=frozen["inputs"]["contract"]["scope"]["scope_id"])
        store = frozen_bytes(root, prepared_ref, frozen, obs)
        report["facts"] = check(value, frozen, store)
        # Revalidate immediately before publication or immutable read-only reuse.
        planning.load_prepared(root, prepared_ref)
        require(rules_identity() == rules, "candidate-rules", "unchanged code and schema bytes")
        obs.verify()
        base = f"logs/ci/{dt.datetime.now(dt.timezone.utc).date().isoformat()}/b-route-candidate-check/{run_id}/{report['attempt_id']}"
        target = sources.checked_path(root, base)
        if target.exists():
            old, event, _prefix = sources.validate_event(obs, base+"/report.json", stage="validate-candidate")
            expected = {**report,"status":"passed","output_ref":base,"resume_ref":base+"/report.json","exit_code":0}
            expected["event_key"] = [expected[key] for key in ("run_id","scope_id","stage","attempt_id")]
            expected_identity = codec.canonical_digest(expected)
            require(codec.canonical_digest(old) == expected_identity
                    and codec.canonical_digest({key:item for key,item in event.items() if key != "artifacts"}) == expected_identity,
                    base, "cached report and event exactly match freshly calculated candidate result")
            require(obs.read(base+"/candidate.raw.json") == raw
                    and codec.canonical_digest(obs.json(base+"/candidate.json")) == report["candidate_identity"],
                    base, "cached candidate artifacts match current original bytes and JSON identity")
            obs.verify()
            return old
        output = planning.new_directory(root, base)
        sources.write(output/"candidate.json", value)
        with (output/"candidate.raw.json").open("xb") as stream:
            stream.write(raw)
        report.update(status="passed",output_ref=base,resume_ref=base+"/report.json")
    except (ValueError,OSError,KeyError,TypeError,RuntimeError,ImportError,UnicodeError) as error:
        report["diagnostics"].append(error.diagnostic.to_dict() if isinstance(error,codec.CodecError) else
            {"reason_code":"candidate_blocked","actual":str(error)})
        if output is not None:
            return partial_failure(root,run_id,report,error,output)
        base = f"logs/ci/{dt.datetime.now(dt.timezone.utc).date().isoformat()}/b-route-candidate-check/{run_id}/failures/{uuid.uuid4().hex}"
        report.update(output_ref=base,resume_ref=base+"/report.json",scope_id=report.get("scope_id","unresolved"),attempt_id=uuid.uuid4().hex)
        try:
            output = planning.new_directory(root,base)
        except (ValueError,OSError) as persistence:
            return partial_failure(root,run_id,report,persistence,root/base)
    report.update(exit_code=0 if report["status"] == "passed" else 1)
    report["event_key"] = [report[k] for k in ("run_id","scope_id","stage","attempt_id")]
    try:
        sources.write(output/"raw-index.json",sources.archive_observations(obs,output))
        if report["status"] == "passed":
            planning.load_prepared(root,prepared_ref)
            require(rules_identity() == rules,"candidate-rules","unchanged through publication")
            obs.verify()
        sources.write(output/"report.json",report)
        artifacts = {p.relative_to(output).as_posix():codec.raw_digest(codec.read_reference_bytes(root,p.relative_to(root).as_posix()))
                     for p in output.rglob("*") if p.is_file()}
        sources.write(output/"event.json",{**report,"artifacts":artifacts})
    except (ValueError,OSError) as error:
        return partial_failure(root,run_id,report,error,output)
    return report


def partial_failure(root,run_id,report,error,output):
    """Retain the partial original site; never repair or point at a false success."""
    report = {**report,"status":"blocked","exit_code":1,"termination_reason":"partial_write",
              "partial_ref":output.relative_to(root).as_posix(),"partial_exists":output.exists(),"resume_ref":None}
    report["diagnostics"] = [*report["diagnostics"],{"reason_code":"read_error","actual":str(error)}]
    try:
        relative=f"logs/ci/{dt.datetime.now(dt.timezone.utc).date().isoformat()}/b-route-candidate-check/{run_id}/failures/{uuid.uuid4().hex}"
        site=planning.new_directory(root,relative)
        report["resume_ref"]=relative+"/report.json"
        sources.write(site/"report.json",report)
    except (ValueError,OSError) as persistence:
        report["resume_ref"]=None
        report["diagnostics"].append({"reason_code":"read_error","actual":str(persistence)})
    return report


def from_cli(args, *, planner):
    stage=getattr(args,"input_stage","legacy")
    prepared=getattr(args,"prepared_ref",None)
    if stage == "legacy":
        require(not prepared,"prepared-ref","explicit --input-stage 3b required")
        require(planner != "mvg" or not getattr(args,"candidate",None),
                "candidate","legacy MVG validate retains its original run-based contract")
        return None
    require(stage == "3b" and args.command == ("validate" if planner == "mvg" else "validate-candidate")
            and prepared and getattr(args,"candidate",None),"input-stage","3b candidate reader with prepared-ref and candidate")
    return validate(Path(args.repo_root).absolute(),run_id=args.run_id,prepared_ref=prepared,candidate=args.candidate)
