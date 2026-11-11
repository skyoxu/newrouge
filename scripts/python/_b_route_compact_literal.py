"""Independent, canonical, data-only encoding of complete JSON objects."""

import ast
import base64
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
import re


SCHEMA = "newrouge.b-route-compact-literal.v1"
CURRENT_SCHEMA = "newrouge.b-route-compact-literal.v2"
ATOM_SCHEMA = "newrouge.b-route-compact-literal.v3"
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
CURRENT_INSTRUCTION = INSTRUCTION.replace(
    "dicts, lists, strings, finite numbers, True, False and None,",
    "dicts, lists, tuple records (child,) or (integer index, one or more field values), strings, finite numbers, True, False and None,",
).replace(SCHEMA, CURRENT_SCHEMA).replace(
    "In value, {'@':[N,[values]]} restores the complete ordered object using keysets[N]; restore nested records recursively.",
    "The strings table contains literal complete strings; (None,N) restores strings[N]. "
    "The shared table contains complete ordered data subtrees; (False,N) restores a fresh copy of shared[N]. "
    "Shared entries may reference only earlier entries. N is always an exact integer, never a boolean. "
    "In value, (child,) restores the one-key object {'r':child}; restore child recursively. "
    "A tuple (N,value1,...,valueK) restores the complete ordered object using nonempty keysets[N]; "
    "N is an exact integer and K equals that keyset's length. Restore nested records recursively.",
)
ATOM_INSTRUCTION = CURRENT_INSTRUCTION.replace(CURRENT_SCHEMA, ATOM_SCHEMA).replace(
    "(None,N) restores strings[N].", "SN restores strings[N] (for example S12 means strings[12])."
).replace(
    "(False,N) restores a fresh copy of shared[N].",
    "DN restores a fresh copy of shared[N] (D12 means shared[12])."
).replace(
    "In value, (child,) restores the one-key object {'r':child}; restore child recursively.",
    "RN restores the one-key object {'r':N} (R12 means {'r':12}); N is a nonnegative integer. "
    "These R/S/D atoms are closed DATA reference names, never Python variables or executable expressions. "
    "An atom's suffix uses ASCII decimal digits without leading zeroes, except zero itself. "
    "All other one-key r objects keep the tuple form (child,); restore child recursively."
)
ATOM_INSTRUCTION += (
    " The phrases table contains exact visible text fragments; PN restores phrases[N]. "
    "A phrase definition may concatenate literal text and references to strictly earlier phrases; "
    "restore the phrase table in order, rejecting forward or cyclic references. "
    "A tuple (C,piece1,...,pieceK) concatenates its restored string pieces in order without separators. "
    "A tuple (B,text) restores standard padded base64 of the strict UTF-8 bytes of its restored visible text. "
    "B is used only for an exact reversible alias of text assembled from original visible string fragments. "
    "P atoms and the C/B tuple tags are also closed DATA syntax, never executable expressions. "
    "Restore these text forms before the S/D tables and normal object restoration. "
    "Every fragment is printed in this request; no external dictionary, omitted source or summary is used."
    " HN restores only the exact digest string 'sha256:' plus N's lowercase hexadecimal value padded "
    "to exactly 64 digits. N is a canonical nonnegative decimal integer below 2**256; all leading "
    "hexadecimal zeroes and the prefix are restored. This is a transparent numeral spelling of the "
    "complete digest, not a shortened identity. Do not recompute cryptographic hashes."
)


def _schema(schema):
    if schema is None:
        return SCHEMA
    if type(schema) is not str or schema not in (SCHEMA, CURRENT_SCHEMA, ATOM_SCHEMA):
        raise ValueError("Unsupported compact literal schema")
    return schema


def instruction(schema=None):
    """Return the complete decoder instructions for an explicitly selected packet."""
    schema = _schema(schema)
    return INSTRUCTION if schema == SCHEMA else ATOM_INSTRUCTION if schema == ATOM_SCHEMA else CURRENT_INSTRUCTION

_ALIASES = {
    "$mvg_ref": "r",
    "$mvg_object": "o",
    "$mvg_lines": "l",
    "$mvg_source": "s",
}
_ORIGINALS = {short: original for original, short in _ALIASES.items()}
_RESERVED = set(_ORIGINALS) | {"@"}
_FIELDS = {"schema_version", "keysets", "value", "sha256"}
_CURRENT_FIELDS = _FIELDS | {"strings", "shared"}
_ATOM_FIELDS = _CURRENT_FIELDS | {"phrases"}
_TEXT_PHRASE = "compact-text-phrase"
_TEXT_CONCAT = "compact-text-concat"
_TEXT_BASE64 = "compact-text-base64"
_MIN_PHRASE = 64
_FULL_SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _literal(value):
    if type(value) is dict:
        return "{" + ",".join(
            repr(key) + ":" + _literal(child) for key, child in value.items()
        ) + "}"
    if type(value) is list:
        return "[" + ",".join(_literal(child) for child in value) + "]"
    if type(value) is tuple:
        return "(" + ",".join(_literal(child) for child in value) + ("," if len(value) == 1 else "") + ")"
    return repr(value)


def _atom_literal(value):
    """Render the v3 data grammar; no atom is evaluated or looked up in Python."""
    if type(value) is str and _FULL_SHA256.fullmatch(value):
        return "H" + str(int(value[7:], 16))
    if type(value) is dict:
        return "{" + ",".join(repr(key) + ":" + _atom_literal(child) for key, child in value.items()) + "}"
    if type(value) is list:
        return "[" + ",".join(_atom_literal(child) for child in value) + "]"
    if type(value) is tuple:
        if len(value) == 2 and value[0] == _TEXT_PHRASE:
            return "P" + str(value[1])
        if len(value) == 2 and value[0] == _TEXT_CONCAT:
            return "(C," + ",".join(_atom_literal(child) for child in value[1]) + ")"
        if len(value) == 2 and value[0] == _TEXT_BASE64:
            return "(B," + _atom_literal(value[1]) + ")"
        if len(value) == 1 and type(value[0]) is int and value[0] >= 0:
            return "R" + str(value[0])
        if len(value) == 2 and type(value[1]) is int and value[1] >= 0:
            if value[0] is None:
                return "S" + str(value[1])
            if value[0] is False:
                return "D" + str(value[1])
        return "(" + ",".join(_atom_literal(child) for child in value) + ("," if len(value) == 1 else "") + ")"
    return repr(value)


def _visible_text(text, originals):
    """Prove a full plaintext is exactly made from already visible original leaves."""
    starts = {}
    for fragment in originals:
        if fragment:
            starts.setdefault(fragment[0], []).append(fragment)
    reachable = {len(text)}
    for offset in range(len(text) - 1, -1, -1):
        if any(offset + len(fragment) in reachable and text.startswith(fragment, offset)
                for fragment in starts.get(text[offset], ())):
            reachable.add(offset)
    return 0 in reachable


def _pack_text(value):
    """Share visible literal substrings, never opaque or external compressed data."""
    original_counts = Counter()
    _walk(value, lambda node: original_counts.update([node]) if type(node) is str else None)
    originals = set(original_counts)
    aliases = {}
    for string in sorted(originals):
        if len(string) < 1024:
            continue
        try:
            raw = base64.b64decode(string, validate=True)
            text = raw.decode("utf-8", errors="strict")
        except (ValueError, UnicodeError):
            continue
        if (text and base64.b64encode(raw).decode("ascii") == string
                and _visible_text(text, originals - {string})):
            aliases[string] = text
    text_counts = Counter({text: count for text, count in original_counts.items() if text not in aliases})
    for alias, text in aliases.items():
        text_counts[text] += original_counts[alias]
    texts = sorted(text_counts, key=lambda text: (-len(text), text))
    # Each substring has a visible earlier full-text witness. This scan discovers
    # candidates only; the final packet prints each selected phrase in full.
    prefixes, candidates = {}, set()
    prefix_size = min(16, _MIN_PHRASE)
    for index, text in enumerate(texts):
        if len(text) >= _MIN_PHRASE and text_counts[text] >= 2:
            candidates.add(text)
        offset = 0
        while offset + _MIN_PHRASE <= len(text):
            best = 0
            for earlier, start in prefixes.get(text[offset:offset + prefix_size], ()):
                source = texts[earlier]
                length = prefix_size
                while (offset + length < len(text) and start + length < len(source)
                        and text[offset + length] == source[start + length]):
                    length += 1
                best = max(best, length)
            if best >= _MIN_PHRASE:
                candidates.add(text[offset:offset + best])
                offset += best
            else:
                offset += 1
        for offset in range(max(0, len(text) - prefix_size + 1)):
            prefixes.setdefault(text[offset:offset + prefix_size], []).append((index, offset))
    phrases = sorted(candidates, key=lambda text: (-len(text), text))
    if phrases:
        pattern = re.compile("|".join(re.escape(phrase) for phrase in phrases))
        counts = Counter()
        for text in texts:
            for match in pattern.finditer(text):
                counts[match.group()] += text_counts[text]
        phrases = [phrase for phrase in phrases if counts[phrase] >= 2
            and (counts[phrase] - 1) * len(repr(phrase)) > counts[phrase] * 8 + 8]
    indices = {phrase: index for index, phrase in enumerate(phrases)}
    pattern = re.compile("|".join(re.escape(phrase) for phrase in phrases)) if phrases else None
    def text_value(text):
        pieces, offset = [], 0
        for match in pattern.finditer(text) if pattern else ():
            if offset < match.start():
                pieces.append(text[offset:match.start()])
            pieces.append((_TEXT_PHRASE, indices[match.group()]))
            offset = match.end()
        if offset < len(text):
            pieces.append(text[offset:])
        result = pieces[0] if len(pieces) == 1 else (_TEXT_CONCAT, pieces)
        return result if len(_atom_literal(result)) < len(repr(text)) else text
    def encode(node):
        if type(node) is str:
            return (_TEXT_BASE64, text_value(aliases[node])) if node in aliases else text_value(node)
        return _children(node, encode)
    encoded = encode(value)
    used = Counter()
    def count_phrase(node):
        if type(node) is tuple and len(node) == 2 and node[0] == _TEXT_PHRASE:
            used[node[1]] += 1
    _walk(encoded, count_phrase)
    retained = [index for index in range(len(phrases)) if used[index] >= 2]
    mapping = {index: number for number, index in enumerate(retained)}
    def prune(node):
        if type(node) is tuple and len(node) == 2 and node[0] == _TEXT_PHRASE:
            return (_TEXT_PHRASE, mapping[node[1]]) if node[1] in mapping else phrases[node[1]]
        return _children(node, prune)
    return _factor_phrases([phrases[index] for index in retained], prune(encoded))


def _factor_phrases(phrases, value):
    """Reuse existing visible definitions; add no short or external dictionary."""
    order = sorted(range(len(phrases)), key=lambda index: (len(phrases[index]), index))
    mapping = {index: number for number, index in enumerate(order)}
    earlier, definitions, patterns = {}, [], {}
    for index in order:
        text = phrases[index]
        length = len(text)
        if length not in patterns:
            choices = [phrase for phrase in earlier if len(phrase) < length]
            choices.sort(key=lambda phrase: (-len(phrase), phrase))
            patterns[length] = re.compile("|".join(re.escape(phrase) for phrase in choices)) if choices else None
        pattern = patterns[length]
        pieces, offset = [], 0
        for match in pattern.finditer(text) if pattern else ():
            if offset < match.start():
                pieces.append(text[offset:match.start()])
            pieces.append((_TEXT_PHRASE, earlier[match.group()]))
            offset = match.end()
        if offset < len(text):
            pieces.append(text[offset:])
        definition = pieces[0] if len(pieces) == 1 else (_TEXT_CONCAT, pieces)
        definitions.append(definition if len(_atom_literal(definition)) < len(repr(text)) else text)
        earlier[text] = mapping[index]
    def remap(node):
        if type(node) is tuple and len(node) == 2 and node[0] == _TEXT_PHRASE:
            return (_TEXT_PHRASE, mapping[node[1]])
        return _children(node, remap)
    return definitions, remap(value)


def _unpack_text(value, phrases):
    if type(phrases) is not list:
        raise ValueError("Invalid visible phrase definitions")
    used, resolved, seen = set(), [], set()
    def phrase_text(node, limit):
        if type(node) is str:
            return node
        if type(node) is tuple and len(node) == 2:
            if node[0] == _TEXT_PHRASE:
                index = node[1]
                if type(index) is not int or not 0 <= index < limit:
                    raise ValueError("Invalid or forward visible phrase definition")
                used.add(index)
                return resolved[index]
            if node[0] == _TEXT_CONCAT and type(node[1]) is list:
                return "".join(phrase_text(piece, limit) for piece in node[1])
        raise ValueError("Phrase definitions require literal text and earlier phrases")
    for index, definition in enumerate(phrases):
        text = phrase_text(definition, index)
        if not text or text in seen:
            raise ValueError("Empty or duplicate restored visible phrase")
        resolved.append(text)
        seen.add(text)
    def restore(node):
        if type(node) is tuple and len(node) == 2:
            if node[0] == _TEXT_PHRASE:
                index = node[1]
                if type(index) is not int or not 0 <= index < len(phrases):
                    raise ValueError("Invalid visible phrase reference")
                used.add(index)
                return resolved[index]
            if node[0] == _TEXT_CONCAT:
                if type(node[1]) is not list:
                    raise ValueError("Invalid visible concatenation")
                pieces = [restore(piece) for piece in node[1]]
                if any(type(piece) is not str for piece in pieces):
                    raise ValueError("Visible concatenation requires strings")
                return "".join(pieces)
            if node[0] == _TEXT_BASE64:
                text = restore(node[1])
                if type(text) is not str:
                    raise ValueError("Visible base64 requires UTF-8 text")
                return base64.b64encode(text.encode("utf-8", errors="strict")).decode("ascii")
        return _children(node, restore)
    restored = restore(value)
    if used != set(range(len(phrases))):
        raise ValueError("Unused visible phrase definition")
    return restored


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


def _pack(value, indices, schema=SCHEMA):
    if type(value) is dict:
        if schema in (CURRENT_SCHEMA, ATOM_SCHEMA) and len(value) == 1 and "r" in value:
            return (_pack(value["r"], indices, schema),)
        values = [_pack(child, indices, schema) for child in value.values()]
        index = indices.get(tuple(value))
        if index is not None:
            return {"@": [index, values]} if schema == SCHEMA else tuple([index, *values])
        return dict(zip(value, values))
    if type(value) is list:
        return [_pack(child, indices, schema) for child in value]
    return value


def _children(value, transform):
    if type(value) is dict:
        return {key: transform(child) for key, child in value.items()}
    if type(value) is list:
        return [transform(child) for child in value]
    if type(value) is tuple:
        return tuple(transform(child) for child in value)
    return value


def _walk(value, visit):
    visit(value)
    children = value.values() if type(value) is dict else value if type(value) in (list, tuple) else ()
    for child in children:
        _walk(child, visit)


def _share(value):
    """Select visible definitions by deterministic character savings, not a tokenizer."""
    counts = Counter()
    def count_string(node):
        if type(node) is str:
            counts[node] += 1
    _walk(value, count_string)
    strings = []
    for string, count in counts.items():
        if (count >= 2 and len(string) >= 16 and (count - 1) * len(repr(string))
                > count * len(_literal((None, len(strings)))) + 1):
            strings.append(string)
    indices = {string: index for index, string in enumerate(strings)}
    def encode_strings(node):
        if type(node) is str and node in indices:
            return (None, indices[node])
        return _children(node, encode_strings)
    encoded = encode_strings(value)
    counts = Counter()
    def count_container(node):
        if type(node) in (dict, list, tuple):
            counts[_literal(node)] += 1
    _walk(encoded, count_container)
    selected = {key for key, count in counts.items() if count >= 2 and len(key) >= 24
        and (count - 1) * len(key) > count * len(_literal((False, len(counts)))) + 1}
    definitions, identities = [], {}
    def encode_shared(node):
        key = _literal(node) if type(node) in (dict, list, tuple) else None
        if key in selected:
            if key not in identities:
                definition = _children(node, encode_shared)
                identities[key] = len(definitions)
                definitions.append(definition)
            return (False, identities[key])
        return _children(node, encode_shared)
    return strings, definitions, encode_shared(encoded)


def _unshare(value, strings, definitions):
    if (type(strings) is not list or any(type(string) is not str for string in strings)
            or len(set(strings)) != len(strings) or type(definitions) is not list
            or any(type(item) not in (dict, list, tuple) for item in definitions)):
        raise ValueError("Invalid string or subtree definitions")
    used_strings, used_shared, cache = set(), set(), {}
    def restore(node, limit):
        if type(node) is tuple:
            if len(node) == 2 and node[0] is None:
                index = node[1]
                if type(index) is not int or not 0 <= index < len(strings):
                    raise ValueError("Invalid string reference")
                used_strings.add(index)
                return strings[index]
            if len(node) == 2 and node[0] is False:
                index = node[1]
                if type(index) is not int or not 0 <= index < limit:
                    raise ValueError("Invalid or forward subtree reference")
                used_shared.add(index)
                if index not in cache:
                    cache[index] = restore(definitions[index], index)
                return deepcopy(cache[index])
            if not (len(node) == 1 or len(node) >= 2 and type(node[0]) is int):
                raise ValueError("Invalid tuple record grammar")
        return _children(node, lambda child: restore(child, limit))
    restored = restore(value, len(definitions))
    if used_strings != set(range(len(strings))) or used_shared != set(range(len(definitions))):
        raise ValueError("Unused string or subtree definitions")
    return restored


def dumps(value: dict, *, schema=None) -> str:
    """Return the deterministic packet literal for a complete JSON object.

    Reject non-JSON values, subclasses and cycles with ValueError. No caller
    containers are retained or modified. Runtime depth/integer limits still apply.
    """
    schema = _schema(schema)
    if type(value) is not dict:
        raise ValueError("The top-level value must be an object")
    try:
        aliased = _copy_aliased(value, set())
        tables = _keysets(aliased)
        if schema in (CURRENT_SCHEMA, ATOM_SCHEMA):
            tables = [keys for keys in tables if keys]
        indices = {tuple(keys): index for index, keys in enumerate(tables)}
        packed = _pack(aliased, indices, schema)
        if schema in (CURRENT_SCHEMA, ATOM_SCHEMA):
            strings, definitions, packed = _share(packed)
            if schema == ATOM_SCHEMA:
                phrases, encoded = _pack_text([strings, definitions, packed])
                strings, definitions, packed = encoded
                return _atom_literal({"schema_version": schema, "keysets": tables,
                    "strings": strings, "shared": definitions, "phrases": phrases,
                    "value": packed, "sha256": _digest(value)})
            render = _atom_literal if schema == ATOM_SCHEMA else _literal
            return render({"schema_version": schema, "keysets": tables,
                "strings": strings, "shared": definitions, "value": packed, "sha256": _digest(value)})
        return _literal({
            "schema_version": schema,
            "keysets": tables,
            "value": packed,
            "sha256": _digest(value),
        })
    except RecursionError as exc:
        raise ValueError("JSON data exceeds the runtime nesting limit") from exc
    except UnicodeError as exc:
        raise ValueError("JSON data must be encodable as strict UTF-8") from exc


def _parse(node, schema=SCHEMA):
    """Construct data from a closed AST grammar; never compile or execute input."""
    if type(node) is ast.Name and schema == ATOM_SCHEMA:
        name = node.id
        suffix = name[1:]
        if (len(name) < 2 or name[0] not in "RSDPH" or not suffix
                or any(char < "0" or char > "9" for char in suffix)
                or len(suffix) > 1 and suffix[0] == "0"):
            raise ValueError("Invalid compact reference atom")
        if name[0] == "H" and len(suffix) > 78:
            raise ValueError("Digest atom outside 256-bit range")
        index = int(suffix)
        if name[0] == "H":
            if index >= 1 << 256:
                raise ValueError("Digest atom outside 256-bit range")
            return "sha256:" + format(index, "064x")
        return ((index,) if name[0] == "R" else (None, index) if name[0] == "S"
            else (False, index) if name[0] == "D" else (_TEXT_PHRASE, index))
    if type(node) is ast.Dict:
        result = {}
        for key_node, child in zip(node.keys, node.values):
            if type(key_node) is not ast.Constant or type(key_node.value) is not str:
                raise ValueError("Literal object keys must be strings")
            key = key_node.value
            if key in result:
                raise ValueError("Duplicate literal object key")
            result[key] = _parse(child, schema)
        return result
    if type(node) is ast.List:
        return [_parse(child, schema) for child in node.elts]
    if type(node) is ast.Tuple and schema in (CURRENT_SCHEMA, ATOM_SCHEMA):
        if (schema == ATOM_SCHEMA and node.elts and type(node.elts[0]) is ast.Name
                and node.elts[0].id in ("C", "B")):
            if node.elts[0].id == "C" and len(node.elts) >= 2:
                return (_TEXT_CONCAT, [_parse(child, schema) for child in node.elts[1:]])
            if node.elts[0].id == "B" and len(node.elts) == 2:
                return (_TEXT_BASE64, _parse(node.elts[1], schema))
            raise ValueError("Invalid visible text tuple")
        if len(node.elts) == 1:
            return (_parse(node.elts[0], schema),)
        if len(node.elts) >= 2 and type(node.elts[0]) is ast.Constant:
            tag = node.elts[0].value
            if type(tag) is int:
                return tuple(_parse(child, schema) for child in node.elts)
            if (len(node.elts) == 2 and (tag is None or tag is False)
                    and type(node.elts[1]) is ast.Constant and type(node.elts[1].value) is int):
                return (tag, node.elts[1].value)
        raise ValueError("Malformed tuple record")
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


def _restore(value, tables, used, schema=SCHEMA):
    if type(value) is dict or type(value) is tuple:
        if schema in (CURRENT_SCHEMA, ATOM_SCHEMA) and type(value) is tuple and len(value) == 1:
            return {"$mvg_ref": _restore(value[0], tables, used, schema)}
        if type(value) is tuple or "@" in value:
            if schema in (CURRENT_SCHEMA, ATOM_SCHEMA):
                if type(value) is not tuple:
                    raise ValueError("Legacy record spelling in a tuple packet")
                record = [value[0], list(value[1:])]
            else:
                if type(value) is not dict or len(value) != 1:
                    raise ValueError("Malformed record envelope")
                record = value["@"]
            if type(record) is not list or len(record) != 2:
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
            result[original] = _restore(child, tables, used, schema)
        return result
    if type(value) is list:
        return [_restore(child, tables, used, schema) for child in value]
    return value


def loads(text: str) -> dict:
    """Restore a fresh object from an exact canonical packet, or raise ValueError.

    Parsing uses only AST data nodes. Digest and full re-encoding validation are
    mandatory; a valid digest alone cannot make a noncanonical packet acceptable.
    """
    if type(text) is not str:
        raise ValueError("The literal must be text")
    try:
        node = ast.parse(text, mode="eval").body
        if type(node) is not ast.Dict:
            raise ValueError("Expected a packet object")
        versions = [child for key, child in zip(node.keys, node.values)
            if type(key) is ast.Constant and type(key.value) is str and key.value == "schema_version"]
        if len(versions) != 1 or type(versions[0]) is not ast.Constant:
            raise ValueError("Expected exactly one literal packet version")
        schema = _schema(versions[0].value)
        packet = _parse(node, schema)
        fields = _FIELDS if schema == SCHEMA else _ATOM_FIELDS if schema == ATOM_SCHEMA else _CURRENT_FIELDS
        if type(packet) is not dict or set(packet) != fields:
            raise ValueError("Unknown or missing packet fields")
        if packet["schema_version"] != schema:
            raise ValueError("Unsupported compact literal schema")
        tables = packet["keysets"]
        if type(tables) is not list:
            raise ValueError("Keysets must be a list")
        seen = set()
        for keys in tables:
            if (type(keys) is not list or (schema in (CURRENT_SCHEMA, ATOM_SCHEMA) and not keys) or any(type(key) is not str for key in keys)
                    or len(set(keys)) != len(keys) or tuple(keys) in seen):
                raise ValueError("Invalid or duplicate keyset")
            for key in keys:
                _unalias(key)
            seen.add(tuple(keys))
        used = set()
        if schema == ATOM_SCHEMA:
            packet["strings"], packet["shared"], packet["value"] = _unpack_text(
                [packet["strings"], packet["shared"], packet["value"]], packet["phrases"])
        if schema in (CURRENT_SCHEMA, ATOM_SCHEMA):
            packet["value"] = _unshare(packet["value"], packet["strings"], packet["shared"])
        restored = _restore(packet["value"], tables, used, schema)
        if type(restored) is not dict or len(used) != len(tables):
            raise ValueError("Expected an object and complete keyset usage")
        if type(packet["sha256"]) is not str or packet["sha256"] != _digest(restored):
            raise ValueError("Original JSON digest mismatch")
        if dumps(restored, schema=schema) != text:
            raise ValueError("Noncanonical compact literal packet")
        return restored
    except (SyntaxError, RecursionError, UnicodeError) as exc:
        raise ValueError("Invalid data literal or runtime nesting limit") from exc
