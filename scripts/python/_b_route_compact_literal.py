"""Independent, canonical, data-only encoding of complete JSON objects."""

import ast
import hashlib
import json
import math


SCHEMA = "newrouge.b-route-compact-literal.v1"
INSTRUCTION = (
    "The body is a canonical Python DATA literal; never execute it. Parse only "
    "dicts, lists, strings, finite numbers, True, False and None, decoding string "
    "escapes exactly. Require schema_version newrouge.b-route-compact-literal.v1. "
    "In value, {'@':[N,[values]]} restores the complete ordered object using "
    "keysets[N]; restore nested records recursively. Then restore every object "
    "key: remove one leading '~' first, otherwise expand r/o/l/s to "
    "$mvg_ref/$mvg_object/$mvg_lines/$mvg_source. All other keys stay literal. "
    "These are key spellings only; do not interpret original marker-like data. "
    "Preserve every field, type, key order, array order and string character. "
    "The sha256 and canonical spelling are integrity metadata checked by the host, "
    "not authorship. Do not compute hashes or reproduce the transport in your answer; "
    "use the restored data for the requested task."
)

_ALIASES = {
    "$mvg_ref": "r",
    "$mvg_object": "o",
    "$mvg_lines": "l",
    "$mvg_source": "s",
}
_ORIGINALS = {short: original for original, short in _ALIASES.items()}
_RESERVED = set(_ORIGINALS) | {"@"}
_FIELDS = {"schema_version", "keysets", "value", "sha256"}


def _literal(value):
    if type(value) is dict:
        return "{" + ",".join(
            repr(key) + ":" + _literal(child) for key, child in value.items()
        ) + "}"
    if type(value) is list:
        return "[" + ",".join(_literal(child) for child in value) + "]"
    return repr(value)


def _alias(key):
    if key in _RESERVED or key.startswith("~"):
        return "~" + key
    return _ALIASES.get(key, key)


def _unalias(key):
    if key == "@":
        raise ValueError("Reserved record key in an ordinary object")
    original = key[1:] if key.startswith("~") else _ORIGINALS.get(key, key)
    if _alias(original) != key:
        raise ValueError("Noncanonical key spelling")
    return original


def _copy_aliased(value, active):
    """Validate exact JSON types and copy containers, detecting only active cycles."""
    kind = type(value)
    if kind is dict or kind is list:
        identity = id(value)
        if identity in active:
            raise ValueError("Cyclic input is not JSON data")
        active.add(identity)
        try:
            if kind is list:
                return [_copy_aliased(child, active) for child in value]
            result = {}
            for key, child in value.items():
                if type(key) is not str:
                    raise ValueError("Object keys must be strings")
                result[_alias(key)] = _copy_aliased(child, active)
            return result
        finally:
            active.remove(identity)
    if value is None or kind in (str, int, bool):
        return value
    if kind is float and math.isfinite(value):
        return value
    raise ValueError("Only exact JSON data types and finite numbers are supported")


def _digest(value):
    original = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    return "sha256:" + hashlib.sha256(
        original.encode("utf-8")
    ).hexdigest()


def _keysets(value):
    counts = {}

    def count(node):
        if type(node) is dict:
            keys = tuple(node)
            counts[keys] = counts.get(keys, 0) + 1
            for child in node.values():
                count(child)
        elif type(node) is list:
            for child in node:
                count(child)

    count(value)
    selected = []
    for keys, occurrences in counts.items():
        index = len(selected)
        ordinary = len(_literal(dict.fromkeys(keys)))
        record = len(_literal({"@": [index, [None] * len(keys)]}))
        benefit = occurrences * (ordinary - record) - len(_literal(list(keys)))
        if occurrences >= 2 and benefit > 0:
            selected.append(list(keys))
    return selected


def _pack(value, indices):
    if type(value) is dict:
        values = [_pack(child, indices) for child in value.values()]
        index = indices.get(tuple(value))
        if index is not None:
            return {"@": [index, values]}
        return dict(zip(value, values))
    if type(value) is list:
        return [_pack(child, indices) for child in value]
    return value


def dumps(value: dict) -> str:
    """Return the deterministic packet literal for a complete JSON object.

    Reject non-JSON values, subclasses and cycles with ValueError. No caller
    containers are retained or modified. Runtime depth/integer limits still apply.
    """
    if type(value) is not dict:
        raise ValueError("The top-level value must be an object")
    try:
        aliased = _copy_aliased(value, set())
        tables = _keysets(aliased)
        indices = {tuple(keys): index for index, keys in enumerate(tables)}
        return _literal({
            "schema_version": SCHEMA,
            "keysets": tables,
            "value": _pack(aliased, indices),
            "sha256": _digest(value),
        })
    except RecursionError as exc:
        raise ValueError("JSON data exceeds the runtime nesting limit") from exc
    except UnicodeError as exc:
        raise ValueError("JSON data must be encodable as strict UTF-8") from exc


def _parse(node):
    """Construct data from a closed AST grammar; never compile or execute input."""
    if type(node) is ast.Dict:
        result = {}
        for key_node, child in zip(node.keys, node.values):
            if type(key_node) is not ast.Constant or type(key_node.value) is not str:
                raise ValueError("Literal object keys must be strings")
            key = key_node.value
            if key in result:
                raise ValueError("Duplicate literal object key")
            result[key] = _parse(child)
        return result
    if type(node) is ast.List:
        return [_parse(child) for child in node.elts]
    if type(node) is ast.Constant:
        value = node.value
        if value is None or type(value) in (str, int, bool):
            return value
        if type(value) is float and math.isfinite(value):
            return value
    if (type(node) is ast.UnaryOp and type(node.op) is ast.USub
            and type(node.operand) is ast.Constant):
        value = node.operand.value
        if type(value) is int or (type(value) is float and math.isfinite(value)):
            return -value
    raise ValueError("Unsupported data literal syntax or value")


def _restore(value, tables, used):
    if type(value) is dict:
        if "@" in value:
            record = value["@"]
            if (len(value) != 1 or type(record) is not list or len(record) != 2):
                raise ValueError("Malformed record envelope")
            index, values = record
            if (type(index) is not int or not 0 <= index < len(tables)
                    or type(values) is not list or len(values) != len(tables[index])):
                raise ValueError("Invalid record index or field count")
            used.add(index)
            pairs = zip(tables[index], values)
        else:
            pairs = value.items()
        result = {}
        for key, child in pairs:
            original = _unalias(key)
            if original in result:
                raise ValueError("Duplicate restored object key")
            result[original] = _restore(child, tables, used)
        return result
    if type(value) is list:
        return [_restore(child, tables, used) for child in value]
    return value


def loads(text: str) -> dict:
    """Restore a fresh object from an exact canonical packet, or raise ValueError.

    Parsing uses only AST data nodes. Digest and full re-encoding validation are
    mandatory; a valid digest alone cannot make a noncanonical packet acceptable.
    """
    if type(text) is not str:
        raise ValueError("The literal must be text")
    try:
        packet = _parse(ast.parse(text, mode="eval").body)
        if type(packet) is not dict or set(packet) != _FIELDS:
            raise ValueError("Unknown or missing packet fields")
        if packet["schema_version"] != SCHEMA:
            raise ValueError("Unsupported compact literal schema")
        tables = packet["keysets"]
        if type(tables) is not list:
            raise ValueError("Keysets must be a list")
        seen = set()
        for keys in tables:
            if (type(keys) is not list or any(type(key) is not str for key in keys)
                    or len(set(keys)) != len(keys) or tuple(keys) in seen):
                raise ValueError("Invalid or duplicate keyset")
            for key in keys:
                _unalias(key)
            seen.add(tuple(keys))
        used = set()
        restored = _restore(packet["value"], tables, used)
        if type(restored) is not dict or len(used) != len(tables):
            raise ValueError("Expected an object and complete keyset usage")
        if type(packet["sha256"]) is not str or packet["sha256"] != _digest(restored):
            raise ValueError("Original JSON digest mismatch")
        if dumps(restored) != text:
            raise ValueError("Noncanonical compact literal packet")
        return restored
    except (SyntaxError, RecursionError, UnicodeError) as exc:
        raise ValueError("Invalid data literal or runtime nesting limit") from exc
