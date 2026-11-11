"""One exact, request-local 3B delivery; no semantic projection or model execution."""
import json

import _b_route_codec as codec
import _b_route_compact_literal as compact
from _mvg_evidence_transport import MODEL_ENCODING, ENCODING_INSTRUCTION, lossless_context
from _mvg_lossless_context import _restore as _restore_lossless_value, wire as _original_lossless_wire

SCHEMA = "newrouge.b-route-complete-materials-wire.v1"
CURRENT_SCHEMA = "newrouge.b-route-complete-materials-wire.v2"
DELIVERIES = (SCHEMA, CURRENT_SCHEMA)
INSTRUCTION = ("The complete materials below use one request-local lossless envelope. "
    "Restore every original field, JSON type, order and string before using it. Nested legacy encoded core "
    "or virtual-file values retain their OWN local envelope namespaces; literal reference-like keys remain data. "
    + ENCODING_INSTRUCTION.strip())

_MARKERS = {"$mvg_ref", "$mvg_concat", "$mvg_object", "$mvg_lines", "$mvg_source"}
_BREAKS = "\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029"


def _source_plan(text, work):
    """Bound the existing span scanner using its actual disjoint token rules."""
    offset, stack, spans = 0, [], set()
    regex_steps = len(text) if len(text) >= 128 else 0
    def span(begin, end):
        work.spend()
        pair = (begin, end)
        if pair not in spans and len(spans) >= compact.MAX_EXPANDED_NODES:
            raise ValueError("b_route_wire_source_span_resource_bound")
        spans.add(pair)
    if len(text) >= 128:
        while offset < len(text):
            work.spend()
            char = text[offset]
            if char == '"':
                end, closed = offset + 1, False
                while end < len(text):
                    work.spend()
                    current = text[end]
                    end += 1
                    if current == "\\":
                        if end >= len(text) or text[end] == "\n":
                            break
                        end += 1
                    elif current == '"':
                        closed = True
                        break
                # The regex alternatives for quoted content are disjoint. Each
                # attempted token inspects at most twice this scanned range.
                regex_steps += 2 * (min(end, len(text)) - offset + 1)
                if closed:
                    offset = end
                    continue
            elif char in "{[":
                work.spend()
                if len(stack) >= compact.MAX_EXPANDED_NODES:
                    raise ValueError("b_route_wire_source_stack_resource_bound")
                stack.append((char, offset))
            elif char in "}]" and stack:
                opening, start = stack.pop()
                if (opening, char) in (("{", "}"), ("[", "]")) and offset + 1 - start >= 128:
                    span(start, offset + 1)
            offset += 1
    offset, start, lines = 0, 0, 0
    while offset < len(text):
        work.spend()
        char = text[offset]
        offset += 1
        if char in _BREAKS:
            if char == "\r" and offset < len(text) and text[offset] == "\n":
                work.spend()
                offset += 1
            lines += 1
            if lines > compact.MAX_EXPANDED_NODES:
                raise ValueError("b_route_wire_source_lines_resource_bound")
            if len(text) >= 128 and offset - start >= 96:
                span(start, offset)
            start = offset
    if start < len(text):
        lines += 1
        if len(text) >= 128 and len(text) - start >= 96:
            span(start, len(text))
    if len(spans) > compact.MAX_EXPANDED_NODES:
        raise ValueError("b_route_wire_source_span_resource_bound")
    work.spend(2 * len(spans))
    raw_volume = sum(end - begin for begin, end in spans)
    candidates = sum(end - begin < len(text) for begin, end in spans)
    # Reserve the legacy token scan and numeric tuple sort before that helper.
    work.spend(regex_steps + 4 * len(spans) * (len(spans).bit_length() + 1))
    return lines, raw_volume, min(candidates, len(text) // 96)


def _factor_reservation(value, work):
    """Reserve the unchanged legacy factor/roundtrip call before it allocates.

    This is a disclosed upper reservation, not a claim of measured CPU or RSS.
    Two wire(node) traversals and seven string-key hash/compare/copy reserves use
    summed subtree serialization size. Nine root-size units cover digests,
    roundtrip serializations and the final copy. Span reserves cover actual
    candidate intervals, including worst-case JSON escaping of chunk keys.
    Restored caches are conservatively bounded by all original subtrees.
    """
    work.phase = "wire.factor.analysis"
    metric = compact._json_preflight(value, work)
    sources, active = {}, set()
    def shape(node, level):
        work.spend()
        if level > compact.MAX_DEPTH:
            return compact._metric(0, depth=level, phase="wire.factor.transform_reservation")
        if type(node) is str:
            work.spend(3 * len(node) + 1)
            if node not in sources:
                sources[node] = _source_plan(node, work)
            lines, raw_volume, count = sources[node]
            if count:
                pieces = 2 * count + 1
                return compact._metric(6 * len(node) + 74 + 348 * pieces + 39 * lines,
                    2 + 8 * pieces + 3 * lines, 7, phase="wire.factor.transform_reservation"), raw_volume, (6 * len(node) + 4 * lines +
                        10 * pieces + pieces * (lines.bit_length() + 1)), count
            if lines > 1:
                return compact._metric(6 * len(node) + 68 + 39 * lines, 2 + 3 * lines, 4,
                    phase="wire.factor.transform_reservation"), raw_volume, 6 * len(node) + 4 * lines, 0
            return compact._text_metric(node, work), raw_volume, 4 * len(node) + lines, 0
        if type(node) not in (dict, list):
            return compact._metric(compact._scalar_bytes(node)), 0, 0, 0
        if id(node) in active:
            raise ValueError("b_route_wire_cycle")
        active.add(id(node))
        work.spend(len(node))
        escaped = type(node) is dict and any(key in _MARKERS for key in node)
        size, nodes, depth, raw_volume, line_work, chunk_nodes = 2, 1, 1, 0, 0, 0
        if escaped:
            size += 6 * len("$mvg_object") + 6
            nodes, depth = 2, 2
        for key, child in (node.items() if type(node) is dict else ((None, child) for child in node)):
            child_metric, child_raw, child_lines, child_chunks = shape(child, level + 1)
            work.spend()
            size += child_metric[0] + 1
            nodes += child_metric[1]
            depth = max(depth, child_metric[2] + (3 if escaped else 1))
            raw_volume += child_raw
            line_work += child_lines
            chunk_nodes += child_chunks
            if type(node) is dict:
                size += compact._text_metric(key, work)[0] + (4 if escaped else 1)
                nodes += 2 if escaped else 0
            compact._metric(size, nodes, depth, phase="wire.factor.transform_reservation")
        active.remove(id(node))
        return compact._metric(size, nodes, depth, phase="wire.factor.transform_reservation"), raw_volume, line_work, chunk_nodes
    transformed, span_volume, line_work, chunk_nodes = shape(value, 1)
    # Each potential reference contributes at most one tiny object. Definitions
    # retain original values once, not an exponentially expanded new namespace.
    frame = compact._json_preflight({"schema_version": MODEL_ENCODING,
        "content_sha256": "sha256:" + "0" * 64, "shared": [], "value": None}, work)
    encoded_bound = compact._metric(transformed[0] + 88 * metric[1] + frame[0],
        transformed[1] + 2 * metric[1] + frame[1], transformed[2] + 3, phase="wire.factor.encoded_reservation")
    cache_bound = compact._metric(metric[3] + metric[0] + 6 * span_volume + 2 * chunk_nodes,
        metric[4] + metric[1] + chunk_nodes, metric[2], phase="wire.factor.cache_reservation")
    reservation = 9 * metric[6] + 9 * metric[5] + 44 * span_volume + line_work + encoded_bound[1]
    work.spend(reservation, phase="wire.factor.work_reservation")
    return {"logical": metric[:3], "encoded_reservation": encoded_bound[:3],
        "cache_reservation": cache_bound[:3], "work_reservation": reservation,
        "subtree_serialization_bound": metric[6], "root_serialization_bound": metric[5],
        "span_slice_bound": span_volume, "line_transform_bound": line_work}


def _lossless_preflight(encoded, work):
    """Close only this envelope's marker namespace, before restore/deepcopy/join."""
    work.phase = "wire.restore.analysis"
    compact._json_preflight(encoded, work)
    if (type(encoded) is not dict or len(encoded) != 4 or set(encoded) != {"schema_version", "content_sha256", "shared", "value"}
            or encoded["schema_version"] != MODEL_ENCODING or type(encoded["shared"]) is not list):
        raise ValueError("mvg_lossless_schema_invalid")
    cache, used = [], set()
    def text_info(value):
        work.spend(len(value) + 1)
        breaks, previous = 0, ""
        for char in value:
            if char in _BREAKS and not (previous == "\r" and char == "\n"):
                breaks += 1
            previous = char
        return len(value), breaks, value[:1], value[-1:]
    def merge(children, *, keys=None, text=False):
        size, nodes, depth, volume, node_volume, wire_size, wire_volume = (2, 1, 1, 0, 0, 2, 0)
        chars, breaks, first, last = 0, 0, "", ""
        for index, child in enumerate(children):
            work.spend()
            metric, is_text = child
            if text and not is_text:
                raise ValueError("mvg_lossless_text_invalid")
            if text:
                length, count, start, end = is_text
                breaks += count - (1 if last == "\r" and start == "\n" else 0)
                if length:
                    first = first or start
                    last = end
                chars += length
            size += metric[0] - 2 if text else metric[0] + 1
            nodes += 0 if text else metric[1]
            depth = max(depth, metric[2] + 1)
            volume += metric[3]
            node_volume += metric[4]
            wire_size += metric[5] - 2 if text else metric[5] + 1
            wire_volume += metric[6]
            if keys is not None:
                key = compact._text_metric(keys[index], work)
                size += key[0] + 1
                wire_size += key[5] + 1
            compact._metric(size, nodes, depth)
        if text:
            line_count = breaks + (1 if chars and last not in _BREAKS else 0)
            if line_count > compact.MAX_EXPANDED_NODES:
                raise ValueError("b_route_wire_lossless_lines_resource_bound")
            work.spend(chars + line_count)
        return compact._metric(size, nodes, depth, volume + size, node_volume + nodes,
            wire_size, wire_volume + wire_size), (chars, breaks, first, last) if text else None
    def visit(node, limit, level=1):
        work.spend()
        if level > compact.MAX_DEPTH:
            return compact._metric(0, depth=level), False
        if type(node) is str:
            return compact._text_metric(node, work), text_info(node)
        if type(node) is list:
            return merge((visit(child, limit, level + 1) for child in node))
        if type(node) is not dict:
            return compact._metric(compact._scalar_bytes(node), wire_size=compact._wire_scalar_bytes(node)), False
        work.spend(len(node))
        names = set(node)
        if names == {"$mvg_ref"}:
            index = node["$mvg_ref"]
            if type(index) is not int or not 0 <= index < limit:
                raise ValueError("mvg_lossless_reference_invalid")
            used.add(index)
            metric, kind = cache[index]
            compact._metric(metric[0], metric[1], metric[2] + 1)
            return (metric[0], metric[1], metric[2] + 1, *metric[3:]), kind
        if names == {"$mvg_concat"}:
            if type(node["$mvg_concat"]) is not list:
                raise ValueError("mvg_lossless_text_invalid")
            return merge((visit(child, limit, level + 1) for child in node["$mvg_concat"]), text=True)
        if names == {"$mvg_lines"}:
            rows = node["$mvg_lines"]
            if type(rows) is not list:
                raise ValueError("mvg_lossless_lines_invalid")
            for number, row in enumerate(rows, 1):
                work.spend()
                if type(row) is not list or len(row) != 2 or type(row[0]) is not int or row[0] != number or type(row[1]) is not str:
                    raise ValueError("mvg_lossless_lines_invalid")
            return merge(((compact._text_metric(row[1], work), text_info(row[1])) for row in rows), text=True)
        if names == {"$mvg_source"}:
            pieces = node["$mvg_source"]
            if type(pieces) is not list:
                raise ValueError("mvg_lossless_source_invalid")
            for piece in pieces:
                work.spend()
                if (type(piece) is not dict or len(piece) != 3 or set(piece) != {"first_line", "first_column", "value"}
                        or type(piece["first_line"]) is not int or type(piece["first_column"]) is not int):
                    raise ValueError("mvg_lossless_source_invalid")
            return merge((visit(piece["value"], limit, level + 1) for piece in pieces), text=True)
        if names == {"$mvg_object"}:
            pairs = node["$mvg_object"]
            if type(pairs) is not list:
                raise ValueError("mvg_lossless_object_invalid")
            keys = []
            for pair in pairs:
                work.spend()
                if type(pair) is not list or len(pair) != 2 or type(pair[0]) is not str:
                    raise ValueError("mvg_lossless_object_invalid")
                compact._text_metric(pair[0], work)
                keys.append(pair[0])
            work.spend(len(keys))
            if len(set(keys)) != len(keys):
                raise ValueError("mvg_lossless_object_invalid")
            return merge((visit(pair[1], limit, level + 1) for pair in pairs), keys=keys)
        if names & _MARKERS:
            raise ValueError("mvg_lossless_reserved_key_invalid")
        return merge((visit(child, limit, level + 1) for child in node.values()), keys=list(node))
    for definition in encoded["shared"]:
        cache.append(visit(definition, len(cache)))
    result = visit(encoded["value"], len(cache))
    work.spend(4 * len(cache) + len(used) + 1)
    if used != set(range(len(cache))):
        raise ValueError("mvg_lossless_content_changed")
    total_size = sum(metric[0] for metric, _kind in cache) + result[0][0]
    total_nodes = sum(metric[1] for metric, _kind in cache) + result[0][1]
    compact._metric(total_size, total_nodes, max([result[0][2], *(metric[2] for metric, _kind in cache)]),
        phase="wire.restore.expanded_and_cache")
    work.spend(3 * result[0][5] + total_size + total_nodes, phase="wire.restore.reservation")
    return result[0]


def factor_lossless_context(value, *, work=None):
    """Reserve the legacy factor owner before its first subtree serialization.

    Its output and namespace remain the original lossless-context v1 bytes. The
    caller may carry one request-local work account across nested legacy cores,
    host comparison artifacts and final complete-material transport.
    """
    work = compact._work(work)
    _factor_reservation(value, work)
    return lossless_context(value)


def restore_lossless_context(encoded, *, work=None):
    """Keep the original primitive decoder and canonical factor comparison."""
    work = compact._work(work)
    _lossless_preflight(encoded, work)
    value = _restore_lossless_value(encoded)
    canonical = factor_lossless_context(value, work=work)
    if _lossless_text(canonical, work) != _lossless_text(encoded, work):
        raise ValueError("mvg_lossless_encoding_changed")
    return value


def _lossless_text(value, work):
    metric = compact._json_preflight(value, work)
    work.spend(metric[5], phase="wire.lossless.serialization")
    return _original_lossless_wire(value)


def _canonical_digest(value, work):
    work.phase = "wire.canonical"
    metric = compact._json_preflight(value, work)
    def keys(node):
        work.spend()
        if type(node) is dict:
            before = work.remaining
            compact._sorted_strings(node, work)
            work.spend(before - work.remaining)
            for child in node.values():
                keys(child)
        elif type(node) is list:
            for child in node:
                keys(child)
    keys(value)
    work.spend(4 * metric[5])
    return codec.canonical_digest(value)


def _raw_digest(value, work):
    work.spend(2 * compact._utf8_size(value, work))
    return codec.raw_digest(value.encode("utf-8"))


def _render_body(header, body, work):
    compact._encoded_preflight(body, work)
    work.spend(len(header) + len(body) + 1)
    return header + "\n" + body


def text(value, *, work=None):
    work = compact._work(work)
    work.phase = "wire.text"
    metric = compact._json_preflight(value, work)
    work.spend(metric[5])
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def artifact_text(value, *, work=None):
    """Reserve and reproduce the original indented host JSON artifact bytes."""
    work = compact._work(work)
    metric = compact._json_preflight(value, work)
    # Each tree edge contributes a value line and each container a closing line.
    # Indent=2 therefore adds at most four depth units per JSON value, plus
    # separators/newlines; this upper reservation precedes json.dumps.
    work.spend(metric[5] + (4 * metric[2] + 4) * metric[1] + 1,
        phase="wire.artifact.serialization")
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def encode(materials, delivery=SCHEMA, *, work=None):
    work = compact._work(work)
    if delivery not in DELIVERIES:
        raise ValueError("b_route_wire_version_invalid")
    if type(materials) is not dict:
        raise ValueError("b_route_wire_materials_not_object")
    encoded = factor_lossless_context(materials, work=work)
    if text(restore_lossless_context(encoded, work=work), work=work) != text(materials, work=work):
        raise ValueError("b_route_wire_roundtrip_changed")
    raw = text(materials, work=work)
    return {"schema_version": delivery, "materials_identity": _canonical_digest(materials, work),
        "materials_bytes_sha256": _raw_digest(raw, work), "encoded": encoded}


def decode(envelope, delivery=SCHEMA, *, work=None):
    work = compact._work(work)
    if (type(envelope) is not dict or len(envelope) != 4 or set(envelope) != {
            "schema_version", "materials_identity", "materials_bytes_sha256", "encoded"}
            or delivery not in DELIVERIES or envelope["schema_version"] != delivery or type(envelope["encoded"]) is not dict
            or envelope["encoded"].get("schema_version") != MODEL_ENCODING):
        raise ValueError("b_route_wire_version_or_shape_invalid")
    value = restore_lossless_context(envelope["encoded"], work=work)
    raw = text(value, work=work)
    if (type(value) is not dict or _canonical_digest(value, work) != envelope["materials_identity"]
            or _raw_digest(raw, work) != envelope["materials_bytes_sha256"]):
        raise ValueError("b_route_wire_materials_changed")
    return value


def read_prompt(prompt, delivery=None, *, work=None):
    work = compact._work(work)
    if type(prompt) is not str:
        raise ValueError("b_route_wire_prompt_invalid")
    work.spend(len(prompt))
    boundary = prompt.find("\n")
    if boundary < 0:
        raise ValueError("b_route_wire_prompt_invalid")
    start = boundary + 1
    if len(prompt) - start > compact.MAX_ENCODED_BYTES:
        raise ValueError("b_route_wire_encoded_resource_bound")
    body = prompt[start:]
    compact._encoded_preflight(body, work)
    if delivery == CURRENT_SCHEMA:
        value = compact.loads(body, work=work)
    else:
        compact._syntax_preflight(body, work, json_only=True)
        value = codec.strict_json_loads(body)
    if delivery is None:
        if not isinstance(value, dict) or value.get("schema_version") in DELIVERIES or "encoded" in value or "wire_delivery" in value:
            raise ValueError("b_route_wire_mixed_delivery")
        return value
    if delivery not in DELIVERIES:
        raise ValueError("b_route_wire_version_invalid")
    return decode(value, delivery, work=work)


def render(instruction, materials, delivery=None, *, compact_schema=None, work=None):
    work = compact._work(work)
    if type(instruction) is not str:
        raise ValueError("b_route_wire_instruction_invalid")
    if compact_schema is not None and delivery != CURRENT_SCHEMA:
        raise ValueError("b_route_wire_compact_policy_requires_compact_delivery")
    if delivery is None:
        return _render_body(instruction, text(materials, work=work), work)
    if delivery not in DELIVERIES:
        raise ValueError("b_route_wire_version_invalid")
    if delivery == CURRENT_SCHEMA:
        header = compact._join([instruction, " ", compact.instruction(compact_schema),
            " After restoring the compact packet, decode its complete B-route envelope. ", INSTRUCTION], work)
        return _render_body(header,
            compact.dumps(encode(materials, delivery, work=work), schema=compact_schema, work=work), work)
    header = compact._join([instruction, " ", INSTRUCTION], work)
    return _render_body(header, text(encode(materials, work=work), work=work), work)
