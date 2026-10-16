"""Readable, versioned sharing of exact JSON values and source-text spans."""
from collections import Counter
from bisect import bisect_right
from copy import deepcopy
import hashlib
import json
import re

SCHEMA = "newrouge.mvg-lossless-context.v1"
RESERVED = {"$mvg_ref", "$mvg_concat", "$mvg_object", "$mvg_lines", "$mvg_source"}
TOKENS = re.compile(r'"(?:\\.|[^"\\])*"|[{}\[\]]')


def wire(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def digest(value):
    return "sha256:" + hashlib.sha256(wire(value).encode("utf-8")).hexdigest()


def _line_starts(text):
    starts, offset = [], 0
    for line in text.splitlines(keepends=True):
        starts.append(offset)
        offset += len(line)
    return starts or [0]


def _numbered(text):
    return {"$mvg_lines": [[number, line] for number, line in enumerate(text.splitlines(keepends=True), 1)]}


def _spans(text):
    """Find exact raw blocks, without parsing or normalizing source characters."""
    stack, spans = [], []
    for match in TOKENS.finditer(text):
        token = match.group()
        if token in ("{", "["):
            stack.append((token, match.start()))
        elif token in ("}", "]") and stack:
            opening, start = stack.pop()
            if (opening, token) in (("{", "}"), ("[", "]")) and match.end() - start >= 128:
                spans.append((start, match.end()))
    offset = 0
    for line in text.splitlines(keepends=True):
        if len(line) >= 96:
            spans.append((offset, offset + len(line)))
        offset += len(line)
    return sorted(set(spans), key=lambda pair: (pair[0], -pair[1]))


def lossless_context(value):
    """Every reference definition travels in this request; no external cache exists."""
    counts, raw_counts, spans_by_text = Counter(), Counter(), {}
    def count(node):
        key = wire(node)
        if len(key) >= (48 if isinstance(node, str) else 96):
            counts[key] += 1
        if isinstance(node, dict):
            for child in node.values():
                count(child)
        elif isinstance(node, list):
            for child in node:
                count(child)
        elif isinstance(node, str) and len(node) >= 128:
            if node not in spans_by_text:
                spans_by_text[node] = _spans(node)
            spans = spans_by_text[node]
            raw_counts.update(node[start:end] for start, end in spans)
    count(value)
    shared, ids = [], {}
    def reference(key, build):
        if key not in ids:
            body = build()
            ids[key] = len(shared)
            shared.append(body)
        return {"$mvg_ref": ids[key]}
    def literal(node):
        if isinstance(node, dict):
            if set(node) & RESERVED:
                return {"$mvg_object": [[key, encode(child)] for key, child in node.items()]}
            return {key: encode(child) for key, child in node.items()}
        if isinstance(node, list):
            return [encode(child) for child in node]
        if isinstance(node, str):
            pieces, offset = [], 0
            starts = _line_starts(node)
            def fragment(start, text, body):
                line = bisect_right(starts, start)
                return {"first_line": line, "first_column": start - starts[line - 1] + 1, "value": body}
            for start, end in spans_by_text.get(node, []):
                chunk = node[start:end]
                if start < offset or raw_counts[chunk] < 2 or len(chunk) == len(node):
                    continue
                if start > offset:
                    pieces.append(fragment(offset, node[offset:start], _numbered(node[offset:start])))
                pieces.append(fragment(start, chunk, reference(wire(chunk), lambda chunk=chunk: _numbered(chunk))))
                offset = end
            if pieces:
                if offset < len(node):
                    pieces.append(fragment(offset, node[offset:], _numbered(node[offset:])))
                return {"$mvg_source": pieces}
            if len(node.splitlines(keepends=True)) > 1:
                return _numbered(node)
        return node
    def encode(node):
        key = wire(node)
        if len(key) >= (48 if isinstance(node, str) else 96) and counts[key] > 1:
            return reference(key, lambda: literal(node))
        return literal(node)
    result = {"schema_version": SCHEMA, "content_sha256": digest(value),
              "shared": shared, "value": encode(value)}
    if wire(_restore(result)) != wire(value):
        raise ValueError("mvg_lossless_roundtrip_mismatch")
    return result


def _restore(encoded):
    if (not isinstance(encoded, dict) or set(encoded) != {"schema_version", "content_sha256", "shared", "value"}
            or encoded["schema_version"] != SCHEMA or not isinstance(encoded["shared"], list)):
        raise ValueError("mvg_lossless_schema_invalid")
    definitions, resolved, used = encoded["shared"], {}, set()
    def decode(node, limit):
        if isinstance(node, dict):
            if set(node) == {"$mvg_ref"}:
                index = node["$mvg_ref"]
                if type(index) is not int or not 0 <= index < limit:
                    raise ValueError("mvg_lossless_reference_invalid")
                used.add(index)
                if index not in resolved:
                    resolved[index] = decode(definitions[index], index)
                return deepcopy(resolved[index])
            if set(node) == {"$mvg_concat"}:
                pieces = node["$mvg_concat"]
                if not isinstance(pieces, list):
                    raise ValueError("mvg_lossless_text_invalid")
                strings = [decode(piece, limit) for piece in pieces]
                if any(not isinstance(piece, str) for piece in strings):
                    raise ValueError("mvg_lossless_text_invalid")
                return "".join(strings)
            if set(node) == {"$mvg_lines"}:
                lines = node["$mvg_lines"]
                if (not isinstance(lines, list) or any(not isinstance(row, list) or len(row) != 2
                        or type(row[0]) is not int or row[0] != number or not isinstance(row[1], str)
                        for number, row in enumerate(lines, 1))):
                    raise ValueError("mvg_lossless_lines_invalid")
                text = "".join(row[1] for row in lines)
                if [row[1] for row in lines] != text.splitlines(keepends=True):
                    raise ValueError("mvg_lossless_lines_invalid")
                return text
            if set(node) == {"$mvg_source"}:
                pieces = node["$mvg_source"]
                if (not isinstance(pieces, list) or any(not isinstance(piece, dict)
                        or set(piece) != {"first_line", "first_column", "value"} for piece in pieces)):
                    raise ValueError("mvg_lossless_source_invalid")
                strings = [decode(piece["value"], limit) for piece in pieces]
                if any(not isinstance(piece, str) for piece in strings):
                    raise ValueError("mvg_lossless_source_invalid")
                text = "".join(strings)
                starts, offset = _line_starts(text), 0
                for piece, string in zip(pieces, strings):
                    line = bisect_right(starts, offset)
                    if (type(piece["first_line"]) is not int or type(piece["first_column"]) is not int
                            or piece["first_line"] != line or piece["first_column"] != offset - starts[line - 1] + 1):
                        raise ValueError("mvg_lossless_source_address_invalid")
                    offset += len(string)
                return text
            if set(node) == {"$mvg_object"}:
                pairs = node["$mvg_object"]
                if (not isinstance(pairs, list) or any(not isinstance(pair, list) or len(pair) != 2
                        or not isinstance(pair[0], str) for pair in pairs)
                        or len({pair[0] for pair in pairs}) != len(pairs)):
                    raise ValueError("mvg_lossless_object_invalid")
                return {key: decode(child, limit) for key, child in pairs}
            if set(node) & RESERVED:
                raise ValueError("mvg_lossless_reserved_key_invalid")
            return {key: decode(child, limit) for key, child in node.items()}
        if isinstance(node, list):
            return [decode(child, limit) for child in node]
        return node
    value = decode(encoded["value"], len(definitions))
    if used != set(range(len(definitions))) or digest(value) != encoded["content_sha256"]:
        raise ValueError("mvg_lossless_content_changed")
    return value


def restore_lossless_context(encoded):
    value = _restore(encoded)
    if wire(lossless_context(value)) != wire(encoded):
        raise ValueError("mvg_lossless_encoding_changed")
    return value
