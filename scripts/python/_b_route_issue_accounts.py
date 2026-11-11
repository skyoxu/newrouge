"""Versioned host issue accounts; canonical review validation remains separate.

Call only after the original independent review owner accepted its complete
schema, denominator, findings and source support. These accounts neither admit
a proposal nor authorize a repair. An origin is an earlier paid, replay-verified
host issue plus its exact before material, never model-supplied account metadata.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json


POLICY = "newrouge.b-route-issue-account.v1"


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _strings(values):
    if (type(values) is not list or any(type(value) is not str or not value for value in values)
            or len(values) != len(set(values))):
        raise ValueError("b_route_issue_account_source_domain_invalid")
    return sorted(values)


def _source_domain(required, sources):
    domain = {}
    for row in sources:
        key = row["id"]
        if type(key) is not str or key in domain:
            raise ValueError("b_route_issue_account_source_domain_invalid")
        domain[key] = {"id": key, "ledger_ref": row["ledger_ref"],
            "ledger_digest": row["ledger_digest"], "block_id": row["block_id"],
            "original_sha256": digest(row["original"])}
    if any(not set(_strings(row["source_block_ids"])) <= set(domain) for row in required):
        raise ValueError("b_route_issue_account_source_domain_invalid")
    return domain


def _flow_owner(proposal, flows, fid):
    actual = [flow for flow in flows if flow.get("id") == fid]
    if len(actual) != 1:
        return ["unresolved-flow", fid], None, False
    flow = actual[0]
    own = [(number, value) for number, value in enumerate(proposal["content"]["definitions"]["flows"])
           if value.get("id") == fid]
    if len(own) == 1 and own[0][1] == flow and type(flow.get("proposed_owner_key")) is str:
        return ["proposed-flow", fid, flow["proposed_owner_key"]], own[0][0], True
    return ["selected-flow", fid], None, False


def _entries(proposal, frozen, required, flows, sources):
    source_domain = _source_domain(required, sources)
    entries, seen = [], set()
    for obligation in required:
        oid, target = obligation["id"], obligation["target"]
        if type(oid) is not str or oid in seen or type(target) is not list or not target:
            raise ValueError("b_route_issue_account_obligation_domain_invalid")
        seen.add(oid)
        family = target[0]
        support = [source_domain[key] for key in _strings(obligation["source_block_ids"])]
        identity = {"policy": POLICY, "input_identity": frozen["input_identity"],
                    "owner": deepcopy(target), "sources": support}
        local_path, repairable = None, False
        if family == "requirement" and len(target) == 3:
            matches = [row for row in proposal["content"]["requirements"] if row.get("requirement_id") == target[1]]
            repairable = len(matches) == 1
        elif family in {"flow", "flow_part", "flow_branch"}:
            owner, index, local = _flow_owner(proposal, flows, target[1])
            flow_rows = [flow for flow in flows if flow.get("id") == target[1]]
            flow = flow_rows[0] if len(flow_rows) == 1 else None
            if family == "flow" and len(target) == 3:
                identity["owner"] = [*owner, "field", target[2]]
                repairable = local and target[2] in flow
                local_path = ["definitions", "flows", index, target[2]] if repairable else None
            elif family == "flow_part" and len(target) == 3:
                rows = [(number, row) for number, row in enumerate(flow.get("parts", []))
                        if row.get("kind") == target[2]] if flow else []
                identity["owner"] = [*owner, "part", target[2]]
                repairable = local and len(rows) == 1
                local_path = ["definitions", "flows", index, "parts", rows[0][0]] if repairable else None
            elif family == "flow_branch" and len(target) == 5:
                branches = flow.get("branches", []) if flow else []
                matches = [(number, row) for number, row in enumerate(branches)
                           if row.get("kind") == target[2] and digest(row) == target[3]]
                kinds = [row for row in branches if row.get("kind") == target[2]]
                if len(matches) == 1 and target[4] == 1:
                    number, row = matches[0]
                    anchors = _strings(row.get("boundary_ids", []))
                    peers = [branch for branch in kinds if _strings(branch.get("boundary_ids", [])) == anchors]
                    # A unique kind survives any local branch-body repair. When
                    # several share a kind, distinct structural boundary owners
                    # identify them without using their freely rewritten prose.
                    anchor = ["unique-kind"] if len(kinds) == 1 else ["boundaries", anchors]
                    identity["owner"] = [*owner, "branch", target[2], anchor]
                    repairable = local and (len(kinds) == 1 or (bool(anchors) and len(peers) == 1))
                    if len(kinds) > 1 and (not anchors or len(peers) != 1):
                        identity["owner"] = [*owner, "ambiguous-branch", *target[2:]]
                    local_path = ["definitions", "flows", index, "branches", number] if repairable else None
                else:
                    # Preserve every ambiguous occurrence as its own blocked
                    # account. No positional guess creates local repair power.
                    identity["owner"] = [*owner, "ambiguous-branch", *target[2:]]
            else:
                raise ValueError("b_route_issue_account_target_invalid")
        elif family == "source" and len(target) == 3:
            source = source_domain.get(target[1])
            root_ref = proposal["content"].get("source_identity", {}).get("ledger_ref", {}).get("ref")
            root_path = root_ref.partition("#")[0] if type(root_ref) is str else None
            if source is not None and source["ledger_ref"] == root_path:
                block = source["block_id"]
                repairable = (any(block in row.get("source_block_ids", [])
                                  for row in proposal["content"]["requirements"])
                              or any(block in row.get("source_block_ids", [])
                                     for row in proposal["content"]["definitions"]["flows"]))
        elif family != "cumulative":
            raise ValueError("b_route_issue_account_target_invalid")
        entries.append({"obligation": obligation, "identity": identity,
                        "local_path": local_path, "repairable": repairable})
    return entries


def resolve_target(proposal, frozen, required, flows, sources, issue):
    """Reconstruct a host account's target and local scope from exact materials.

    Runtime must independently close ``issue`` against its original paid review.
    This checks the current obligation, source namespace and actual owner scope;
    it does not treat a matching digest as evidence that a model call occurred.
    An inherited branch anchor is allowed only within the identical host owner,
    branch kind, original field position and frozen support. Its earlier origin
    remains the caller's recursively replayed proof obligation.
    """
    entries = _entries(proposal, frozen, required, flows, sources)
    matches = [entry for entry in entries if entry["obligation"]["id"] == issue.get("obligation_id")]
    if len(matches) != 1 or issue.get("account_policy") != POLICY:
        raise ValueError("b_route_issue_account_issue_invalid")
    entry = matches[0]
    identity = issue.get("account_identity")
    if (type(identity) is not dict or set(identity) != {"policy", "input_identity", "owner", "sources"}
            or issue.get("code") != "semantic_review_account:" + digest(identity)
            or issue.get("path") != "semantic-review"
            or identity.get("policy") != POLICY or identity.get("input_identity") != frozen["input_identity"]
            or identity.get("sources") != entry["identity"]["sources"]
            or issue.get("account_target") != entry["obligation"]["target"]
            or type(issue.get("local_repairable")) is not bool
            or issue["local_repairable"] != entry["repairable"]
            or issue.get("local_owner_path") != entry["local_path"]):
        raise ValueError("b_route_issue_account_issue_invalid")
    actual, claimed = entry["identity"]["owner"], identity.get("owner")
    inherited = (entry["obligation"]["target"][0] == "flow_branch" and entry["repairable"]
                 and entry["local_path"] is not None and type(claimed) is list
                 and len(claimed) == len(actual) and claimed[:-1] == actual[:-1])
    if claimed != actual and not inherited:
        raise ValueError("b_route_issue_account_issue_owner_changed")
    return deepcopy(entry["obligation"]["target"]), entry["repairable"], deepcopy(entry["local_path"])


def _origin_entry(proposal, frozen, required, flows, sources, entries, origin):
    if origin is None:
        return
    if type(origin) is not tuple or len(origin) != 4:
        raise ValueError("b_route_issue_account_origin_invalid")
    before, before_required, before_flows, issue = origin
    try:
        resolve_target(before, frozen, before_required, before_flows, sources, issue)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("b_route_issue_account_origin_invalid") from exc
    old = _entries(before, frozen, before_required, before_flows, sources)
    matches = [entry for entry in old if entry["obligation"]["id"] == issue.get("obligation_id")]
    if len(matches) != 1 or issue.get("account_policy") != POLICY:
        raise ValueError("b_route_issue_account_origin_invalid")
    prior = matches[0]
    identity = issue.get("account_identity")
    if (type(identity) is not dict or issue.get("code") != "semantic_review_account:" + digest(identity)
            or issue.get("account_target") != prior["obligation"]["target"]
            or identity.get("policy") != POLICY or identity.get("input_identity") != frozen["input_identity"]
            or identity.get("sources") != prior["identity"]["sources"]
            or issue.get("local_owner_path") != prior["local_path"]):
        raise ValueError("b_route_issue_account_origin_invalid")
    path = prior["local_path"]
    if (not prior["repairable"] or not path or len(path) != 5 or path[3] != "branches"
            or prior["obligation"]["target"][0] != "flow_branch"):
        return
    flow_index, branch_index = path[2], path[4]
    previous = before["content"]["definitions"]["flows"][flow_index]
    current_flows = proposal["content"]["definitions"]["flows"]
    if flow_index >= len(current_flows):
        return
    current = current_flows[flow_index]
    if (previous.get("id") != current.get("id")
            or previous.get("proposed_owner_key") != current.get("proposed_owner_key")
            or len(previous["branches"]) != len(current["branches"])
            or any(left != right for number, (left, right) in enumerate(zip(previous["branches"], current["branches"]))
                   if number != branch_index)):
        return
    old_branch, branch = previous["branches"][branch_index], current["branches"][branch_index]
    # Scope and paid-origin verification are still owned by runtime. This
    # narrower mapping refuses owner/kind changes and any new sibling branch.
    if old_branch.get("kind") != branch.get("kind"):
        return
    skeleton = prior["identity"]["owner"][:-1]
    if type(identity.get("owner")) is not list or identity["owner"][:-1] != skeleton:
        raise ValueError("b_route_issue_account_origin_owner_changed")
    revised = [entry for entry in entries if entry["local_path"] == path
               and entry["identity"]["sources"] == identity["sources"]
               and entry["obligation"]["target"][0] == "flow_branch"]
    if len(revised) == 1 and revised[0]["repairable"]:
        revised[0]["identity"] = deepcopy(identity)


def build_accounts(proposal, frozen, review, required, flows, sources, *, policy=POLICY, origin=None):
    """Adapt a fully validated review to stable host repair accounts.

    ``required`` is the complete original obligations result; ``flows`` is the
    original semantic_domain flow list, and ``sources`` is qualified_sources.
    The optional origin is (before, before_obligations, before_flows, host_issue).
    Its issue and before must first be replay-bound to an earlier paid review.
    An origin maps only one unchanged-position branch scope. It never validates
    a repair, alters checks, removes findings or weakens independent admission.
    """
    if policy != POLICY:
        raise ValueError("b_route_issue_account_policy_invalid")
    entries = _entries(proposal, frozen, required, flows, sources)
    checks = review.get("checks", [])
    if (len(checks) != len(entries) or len({row.get("id") for row in checks}) != len(checks)
            or {row.get("id") for row in checks} != {entry["obligation"]["id"] for entry in entries}):
        raise ValueError("b_route_issue_account_review_domain_invalid")
    _origin_entry(proposal, frozen, required, flows, sources, entries, origin)
    codes = [digest(entry["identity"]) for entry in entries]
    if len(codes) != len(set(codes)):
        raise ValueError("b_route_issue_account_owner_ambiguous")
    domain = {entry["obligation"]["id"]: entry for entry in entries}
    result, review_sha = [], digest(review)
    for row in checks:
        entry = domain[row["id"]]
        if not set(_strings(row["source_block_ids"])) <= set(entry["obligation"]["source_block_ids"]):
            raise ValueError("b_route_issue_account_review_source_invalid")
        if row["verdict"] != "blocked":
            continue
        result.append({"code": "semantic_review_account:" + digest(entry["identity"]),
            "path": "semantic-review", "detail": row["rationale"], "account_policy": POLICY,
            "account_identity": deepcopy(entry["identity"]), "account_target": deepcopy(entry["obligation"]["target"]),
            "obligation_id": row["id"], "review_sha256": review_sha,
            "local_repairable": entry["repairable"], "local_owner_path": deepcopy(entry["local_path"])})
    return result
