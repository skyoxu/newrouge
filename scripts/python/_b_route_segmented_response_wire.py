"""Closed citation-set representation of a complete segmented response.

Only enumerated proof fields use the table. Business JSON strings and every
other result value remain data; no recursive citation-name substitution occurs.
This codec grants no semantic, execution, paid-call or admission authority.
"""
from copy import deepcopy
import json


SCHEMA = "newrouge.b-route-segmented-response-citation-wire.v1"
EXPANSION_POLICY = "newrouge.b-route-segmented-response-expansion-limits.v1"
MAX_EXPANDED_UTF8_BYTES = 16 * 1024 * 1024
MAX_EXPANDED_NODES = 100000
ROWS = ("coverage", "decisions", "unresolved", "findings", "checks",
        "comparisons", "candidate_pieces", "product_checks", "joint_checks")


def _require(value, field):
    if not value:
        raise ValueError("segmented_response_wire_" + field)


def _identity(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _validate(schema, value):
    try:
        from jsonschema import Draft202012Validator
    except ImportError as exc:
        raise ValueError("segmented_response_wire_schema_backend_unavailable") from exc
    _require(next(Draft202012Validator(schema).iter_errors(value), None) is None,
             "complete_schema")


def _rows(result):
    """The declared canonical first-use order, including each comparison child."""
    for field in ROWS:
        _require(type(result.get(field)) is list, "proof_rows")
        for row in result[field]:
            _require(type(row) is dict, "proof_row")
            yield row
            if field == "comparisons":
                _require(type(row.get("cross_impacts")) is list, "cross_impacts")
                for impact in row["cross_impacts"]:
                    _require(type(impact) is dict, "cross_impact")
                    yield impact


def _string_bytes(text, limit):
    """Exact ensure_ascii=False JSON UTF-8 size, without making an encoded copy."""
    size = 2
    for char in text:
        point = ord(char)
        _require(not 0xD800 <= point <= 0xDFFF, "expansion_invalid_utf8")
        amount = (2 if char in '\\"\b\f\n\r\t' else 6 if point < 32 else
                  1 if point < 128 else 2 if point < 2048 else 3 if point < 65536 else 4)
        _require(amount <= limit - size, "expansion_utf8_limit")
        size += amount
    _require(size <= limit, "expansion_utf8_limit")
    return size


def _measure_expanded(value, byte_limit, node_limit, replacements=None):
    """Saturating occurrence costs; object keys count as string nodes too.

    Stack frames are iterators, so width does not allocate a second child list.
    Reused containers are counted on every occurrence; active cycles are refused.
    A proof-row replacement contributes its precomputed full table-entry cost.
    """
    replacements = replacements or {}
    byte_count, node_count, active = 0, 0, set()
    stack = [(iter((("value", value),)), None)]
    while stack:
        iterator, owner = stack[-1]
        try:
            kind, child = next(iterator)
        except StopIteration:
            stack.pop()
            if owner is not None:
                active.remove(owner)
            continue
        if kind == "cost":
            amount, nodes = child
        elif type(child) in (dict, list):
            identity = id(child)
            _require(identity not in active, "expansion_cycle")
            amount, nodes = 2 + max(0, len(child) - 1), 1
            if type(child) is dict:
                amount += len(child)  # colons; commas/braces are above
                replacement = replacements.get(identity)
                def items(mapping, replacement):
                    for key, item in mapping.items():
                        _require(type(key) is str, "expansion_object_key")
                        if replacement is not None and key == "citation_set_index":
                            yield "value", "citations"
                            yield "cost", replacement
                        else:
                            yield "value", key
                            yield "value", item
                children = items(child, replacement)
            else:
                children = (("value", item) for item in child)
            active.add(identity)
            stack.append((iter(children), identity))
        else:
            nodes = 1
            if type(child) is str:
                amount = _string_bytes(child, byte_limit - byte_count)
            else:
                _require(child is None or type(child) in (bool, int, float), "expansion_json_type")
                amount = len(json.dumps(child, allow_nan=False, separators=(",", ":")))
        _require(amount <= byte_limit - byte_count, "expansion_utf8_limit")
        _require(nodes <= node_limit - node_count, "expansion_node_limit")
        byte_count += amount
        node_count += nodes
    return byte_count, node_count


def _preflight_expansion(value, *, byte_limit, node_limit):
    """Compute the whole logical result cost before copying any model subtree."""
    _require(type(byte_limit) is int and byte_limit > 0 and type(node_limit) is int and node_limit > 0,
             "expansion_policy")
    costs, table_bytes, table_nodes = [], 0, 0
    for entry in value["citation_sets"]:
        cost = _measure_expanded(entry, byte_limit, node_limit)
        _require(cost[0] <= byte_limit - table_bytes, "expansion_utf8_limit")
        _require(cost[1] <= node_limit - table_nodes, "expansion_node_limit")
        table_bytes += cost[0]
        table_nodes += cost[1]
        costs.append(cost)
    uses, replacements, seen = {}, {}, set()
    for row in _rows(value["result"]):
        index = row["citation_set_index"]
        _require(type(index) is int and 0 <= index < len(costs), "citation_index")
        if index not in seen:
            _require(index == len(seen), "citation_set_first_use_order")
            seen.add(index)
        uses[index] = uses.get(index, 0) + 1
        _require(uses[index] <= byte_limit // costs[index][0], "expansion_utf8_limit")
        _require(uses[index] <= node_limit // costs[index][1], "expansion_node_limit")
        replacements[id(row)] = costs[index]
        _require(len(replacements) <= node_limit, "expansion_node_limit")
    _require(seen == set(range(len(costs))), "unused_citation_set")
    # Grouped table_cost * actual reference count is an early lower bound;
    # the complete walk also includes every original body, key and result row.
    repeated_bytes, repeated_nodes = 0, 0
    for index, count in uses.items():
        cost = costs[index]
        _require(count <= (byte_limit - repeated_bytes) // cost[0], "expansion_utf8_limit")
        _require(count <= (node_limit - repeated_nodes) // cost[1], "expansion_node_limit")
        repeated_bytes += cost[0] * count
        repeated_nodes += cost[1] * count
    return _measure_expanded(value["result"], byte_limit, node_limit, replacements)


def output_schema(logical_schema):
    """Derive the new physical schema without changing the logical validator."""
    result = deepcopy(logical_schema)
    citation = deepcopy(result["properties"]["coverage"]["items"]["properties"]["citations"]["items"])
    for field in ROWS:
        schemas = [result["properties"][field]["items"]]
        if field == "comparisons":
            schemas.append(schemas[0]["properties"]["cross_impacts"]["items"])
        for row in schemas:
            _require("citations" in row["properties"] and "citations" in row["required"], "schema_proof_path")
            row["properties"] = {
                ("citation_set_index" if key == "citations" else key):
                ({"type": "integer", "minimum": 0, "maximum": 99999} if key == "citations" else child)
                for key, child in row["properties"].items()}
            row["required"] = ["citation_set_index" if key == "citations" else key for key in row["required"]]
    return {"type": "object", "properties": {
        "schema_version": {"type": "string", "const": SCHEMA},
        "citation_sets": {"type": "array", "minItems": 1, "maxItems": 100000,
                          "items": {"type": "array", "minItems": 1, "maxItems": 100000, "items": citation}},
        "result": result},
        "required": ["schema_version", "citation_sets", "result"], "additionalProperties": False}


def encode(response, *, logical_schema):
    """Pure fixture/producer helper; never rewrite a received paid output."""
    _validate(logical_schema, response)
    result, table, indices = deepcopy(response), [], {}
    for row in _rows(result):
        citations = row["citations"]
        _require(type(citations) is list and citations, "citation_set_required")
        identity = _identity(citations)
        if identity not in indices:
            indices[identity] = len(table)
            table.append(deepcopy(citations))
        else:
            # Avoid normalizing any original ordered object representation.
            _require(json.dumps(table[indices[identity]], ensure_ascii=False) ==
                     json.dumps(citations, ensure_ascii=False), "citation_object_order")
        replacement = {("citation_set_index" if key == "citations" else key):
                       (indices[identity] if key == "citations" else child) for key, child in row.items()}
        row.clear()
        row.update(replacement)
    value = {"schema_version": SCHEMA, "citation_sets": table, "result": result}
    decode(value, logical_schema=logical_schema)
    return value


def decode(value, *, logical_schema):
    """Require this wire version, full tables, exact indices and first-use order."""
    _require(type(value) is dict and set(value) == {"schema_version", "citation_sets", "result"}, "fields")
    _require(value["schema_version"] == SCHEMA, "version")
    _validate(output_schema(logical_schema), value)
    _preflight_expansion(value, byte_limit=MAX_EXPANDED_UTF8_BYTES, node_limit=MAX_EXPANDED_NODES)
    table = value["citation_sets"]
    identities = [_identity(row) for row in table]
    _require(len(set(identities)) == len(identities), "duplicate_citation_set")
    result, seen = deepcopy(value["result"]), set()
    for row in _rows(result):
        index = row["citation_set_index"]
        _require(type(index) is int and 0 <= index < len(table), "citation_index")
        if index not in seen:
            _require(index == len(seen), "citation_set_first_use_order")
            seen.add(index)
        replacement = {("citations" if key == "citation_set_index" else key):
                       (deepcopy(table[index]) if key == "citation_set_index" else child) for key, child in row.items()}
        row.clear()
        row.update(replacement)
    _require(seen == set(range(len(table))), "unused_citation_set")
    _validate(logical_schema, result)
    return result


def instruction():
    return (" Return the physical response wire " + SCHEMA +
        ": exactly schema_version, citation_sets and result. citation_sets contains complete nonempty "
        "arrays of exact original source citations, once each, in first-use order. result contains the "
        "complete logical response, including its original logical schema_version, except that proof "
        "rows use citation_set_index instead of citations. Use exact nonnegative integer indices. "
        "First-use traversal is coverage, decisions, unresolved, findings, checks, comparisons "
        "(each comparison followed immediately by its cross_impacts), candidate_pieces, product_checks, "
        "joint_checks, preserving every array's order. Repeated citation arrays reuse their existing "
        "index; no duplicate, unused, missing or reordered table entry is allowed. Preserve every "
        "row, verdict, member digest, dependency and full business body. Only those enumerated proof "
        "citation fields use this table; never replace citations or any similarly named field inside "
        "candidate value_json or other original business data. This is a complete reversible "
        "representation, not a summary, approval flag or reference to another request. ")
