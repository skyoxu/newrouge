"""Shared declared Flow topology semantics; no source, runtime or Task admission."""
import _b_route_codec as codec
import _b_route_sources as sources

PARTS = {"domain_rules", "csharp_adapter", "binding", "scene"}


def require(condition, entity, expected, actual=None):
    sources.require(condition, entity, expected, actual)


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


def flow_source_predicate(flow, blocks):
    """Membership only; the caller supplies its already authenticated ledger."""
    return set(flow['source_block_ids']) <= set(blocks), flow['id'], 'known Flow source blocks'


def flow_local_predicates(flow, resolve, *, unique):
    """Yield original independent local predicates in canonical failure order.

    Resolution and uniqueness remain strict prerequisites, including during a
    read-only witness. Yielding a false condition never grants admission: the
    canonical caller still applies require immediately to every yielded tuple.
    """
    fid = flow["id"]
    parts = unique(flow["parts"], lambda r: r["kind"], "parts")
    yield set(parts) == PARTS, fid, "all four applicability responsibilities exactly once"
    for field in ("ui", "human_verification"):
        obligation = flow[field]
        resolve(obligation["owner"])
        yield (obligation["applicability"] != "applicable" or bool(obligation["responsibilities"]),
               fid + "." + field, "nonempty applicable responsibility")
    if flow["ui"]["applicability"] == "applicable":
        yield (all(flow["ui"][name] for name in ("inputs", "feedback", "scene_entry", "scene_return")),
               fid + ".ui", "explicit input, feedback, scene entry and return obligations")


def check_graph(content, owners, resolve, *, unique, flow_predicates):
    flows = {fid: definition for (kind, fid), (_owner, definition) in owners.items() if kind == "flow"}
    local_flows = content["definitions"]["flows"]
    nodes, adjacency, boundaries, state_owners = {}, {}, {}, {}
    declared_edge_count = 0
    for flow in local_flows:
        fid = flow["id"]
        for condition, entity, expected in flow_predicates(flow, resolve):
            require(condition, entity, expected)
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
