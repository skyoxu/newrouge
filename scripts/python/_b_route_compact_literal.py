"""Independent, canonical, data-only encoding of complete JSON objects."""

import ast
import base64
from collections import Counter
from copy import deepcopy
import hashlib
import json
import math
import re
from functools import cmp_to_key


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

# Host resource policy is independent of the unchanged v1/v2/v3 wire grammar.
# A model window is not an expanded-memory budget. Rejected packets are never
# truncated or silently recoded; historical producers retain their own policy.
# v3 applies the same ceilings to legacy inner factor/restore and frozen request
# reconstruction in the caller's single final-request work account as well.
RESOURCE_POLICY = "newrouge.b-route-resource-pipeline.v3"
MAX_ENCODED_BYTES = 8 * 1024 * 1024
MAX_EXPANDED_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_NODES = 1_000_000
MAX_DEPTH = 128
MAX_ENCODING_WORK = 100_000_000


class _EncodingWork:
    def __init__(self):
        self.limit = MAX_ENCODING_WORK
        self.remaining = MAX_ENCODING_WORK
        self.phase = "compact"

    def spend(self, amount=1, *, phase=None):
        if type(amount) is not int or amount < 0:
            raise ValueError("Invalid resource work charge")
        if amount > self.remaining:
            raise ValueError("Compact encoding work exceeds " + RESOURCE_POLICY +
                f"; charged={self.limit - self.remaining}; reserve={amount}; remaining={self.remaining}; phase={phase or self.phase}")
        self.remaining -= amount


def _work(work):
    return _EncodingWork() if work is None else work


def _repr(value, work):
    if type(value) is str:
        work.spend(len(value) + 1)
        size = 2
        for char in value:
            code = ord(char)
            size += (2 if char in "\\\"'\n\r\t" else 1 if char.isprintable()
                else 4 if code <= 255 else 6 if code <= 65535 else 10)
        work.spend(size)
    else:
        work.spend(_scalar_bytes(value))
    return repr(value)


def _join(parts, work):
    work.spend(len(parts))
    work.spend(sum(len(part) for part in parts))
    return "".join(parts)


def _literal(value, work=None):
    return _render_literal(value, _work(work), False)


def _atom_literal(value, work=None):
    """Render the v3 data grammar; no atom is evaluated or looked up in Python."""
    return _render_literal(value, _work(work), True)


def _render_literal(value, work, atoms):
    work.spend()
    if atoms and type(value) is str and _FULL_SHA256.fullmatch(value):
        work.spend(160)
        return "H" + str(int(value[7:], 16))
    if type(value) is dict:
        work.spend(4 * len(value) + 2)
        parts = ["{"]
        for index, (key, child) in enumerate(value.items()):
            if index:
                parts.append(",")
            parts.extend((_repr(key, work), ":", _render_literal(child, work, atoms)))
        parts.append("}")
        return _join(parts, work)
    if atoms and type(value) is tuple:
        if len(value) == 2 and value[0] == _TEXT_PHRASE:
            work.spend(_scalar_bytes(value[1]) + 1)
            return "P" + str(value[1])
        if len(value) == 2 and value[0] == _TEXT_CONCAT:
            work.spend(2 * len(value[1]) + 2)
            parts = ["(C,"]
            for index, child in enumerate(value[1]):
                if index:
                    parts.append(",")
                parts.append(_render_literal(child, work, atoms))
            parts.append(")")
            return _join(parts, work)
        if len(value) == 2 and value[0] == _TEXT_BASE64:
            return _join(["(B,", _render_literal(value[1], work, atoms), ")"], work)
        if len(value) == 1 and type(value[0]) is int and value[0] >= 0:
            work.spend(_scalar_bytes(value[0]) + 1)
            return "R" + str(value[0])
        if len(value) == 2 and type(value[1]) is int and value[1] >= 0:
            if value[0] is None:
                work.spend(_scalar_bytes(value[1]) + 1)
                return "S" + str(value[1])
            if value[0] is False:
                work.spend(_scalar_bytes(value[1]) + 1)
                return "D" + str(value[1])
    if type(value) in (list, tuple):
        work.spend(2 * len(value) + 2)
        parts = ["[" if type(value) is list else "("]
        for index, child in enumerate(value):
            if index:
                parts.append(",")
            parts.append(_render_literal(child, work, atoms))
        parts.append("]" if type(value) is list else ",)" if len(value) == 1 else ")")
        return _join(parts, work)
    return _repr(value, work)


def _sorted_strings(values, work, *, longest=False):
    work.spend(len(values))
    def compare(left, right):
        work.spend()
        if longest and len(left) != len(right):
            return -1 if len(left) > len(right) else 1
        for a, b in zip(left, right):
            work.spend()
            if a != b:
                return -1 if a < b else 1
        return (len(left) > len(right)) - (len(left) < len(right))
    return sorted(values, key=cmp_to_key(compare))


def _visible_text(text, originals, work):
    """Prove a full plaintext is exactly made from already visible original leaves."""
    starts = {}
    for fragment in originals:
        work.spend(len(fragment) + 1)
        if fragment:
            starts.setdefault(fragment[0], []).append(fragment)
    reachable = {len(text)}
    for offset in range(len(text) - 1, -1, -1):
        work.spend()
        for fragment in starts.get(text[offset], ()):
            work.spend(len(fragment) + 1)
            if offset + len(fragment) in reachable and text.startswith(fragment, offset):
                reachable.add(offset)
                break
    return 0 in reachable


def _pack_text(value, work=None):
    """Share visible literal substrings, never opaque or external compressed data."""
    work = _work(work)
    original_counts = Counter()
    _walk(value, lambda node: original_counts.update([node]) if type(node) is str else None, work)
    work.spend(len(original_counts))
    originals = set(original_counts)
    aliases = {}
    for string in _sorted_strings(originals, work):
        work.spend(4 * len(string) + 1)
        if len(string) < 1024:
            continue
        try:
            raw = base64.b64decode(string, validate=True)
            text = raw.decode("utf-8", errors="strict")
        except (ValueError, UnicodeError):
            continue
        if text and base64.b64encode(raw).decode("ascii") == string:
            work.spend(len(originals))
            if _visible_text(text, originals - {string}, work):
                aliases[string] = text
    work.spend(2 * len(original_counts) + len(aliases))
    text_counts = Counter({text: count for text, count in original_counts.items() if text not in aliases})
    for alias, text in aliases.items():
        text_counts[text] += original_counts[alias]
    texts = _sorted_strings(text_counts, work, longest=True)
    # Each substring has a visible earlier full-text witness. This scan discovers
    # candidates only; the final packet prints each selected phrase in full.
    prefixes, candidates = {}, set()
    prefix_size = min(16, _MIN_PHRASE)
    for index, text in enumerate(texts):
        if len(text) >= _MIN_PHRASE and text_counts[text] >= 2:
            candidates.add(text)
        offset = 0
        while offset + _MIN_PHRASE <= len(text):
            work.spend(prefix_size + 1)
            best = 0
            for earlier, start in prefixes.get(text[offset:offset + prefix_size], ()):
                work.spend()
                source = texts[earlier]
                length = prefix_size
                while (offset + length < len(text) and start + length < len(source)
                        and text[offset + length] == source[start + length]):
                    work.spend()
                    length += 1
                best = max(best, length)
            if best >= _MIN_PHRASE:
                work.spend(best)
                candidates.add(text[offset:offset + best])
                offset += best
            else:
                offset += 1
        for offset in range(max(0, len(text) - prefix_size + 1)):
            work.spend(prefix_size + 1)
            prefixes.setdefault(text[offset:offset + prefix_size], []).append((index, offset))
    phrases = _sorted_strings(candidates, work, longest=True)
    if phrases:
        pattern = _LiteralMatcher(phrases, work)
        counts = Counter()
        for text in texts:
            for _start, _end, phrase in pattern.finditer(text):
                counts[phrase] += text_counts[text]
        phrases = [phrase for phrase in phrases if counts[phrase] >= 2
            and (counts[phrase] - 1) * len(_repr(phrase, work)) > counts[phrase] * 8 + 8]
    work.spend(len(phrases))
    indices = {phrase: index for index, phrase in enumerate(phrases)}
    pattern = _LiteralMatcher(phrases, work) if phrases else None
    def text_value(text):
        pieces, offset = [], 0
        for start, end, phrase in pattern.finditer(text) if pattern else ():
            if offset < start:
                work.spend(start - offset)
                pieces.append(text[offset:start])
            work.spend(2)
            pieces.append((_TEXT_PHRASE, indices[phrase]))
            offset = end
        if offset < len(text):
            work.spend(len(text) - offset)
            pieces.append(text[offset:])
        result = pieces[0] if len(pieces) == 1 else (_TEXT_CONCAT, pieces)
        return result if len(_atom_literal(result, work)) < len(_repr(text, work)) else text
    def encode(node):
        if type(node) is str:
            return (_TEXT_BASE64, text_value(aliases[node])) if node in aliases else text_value(node)
        return _children(node, encode, work)
    encoded = encode(value)
    used = Counter()
    def count_phrase(node):
        if type(node) is tuple and len(node) == 2 and node[0] == _TEXT_PHRASE:
            used[node[1]] += 1
    _walk(encoded, count_phrase, work)
    work.spend(3 * len(phrases))
    retained = [index for index in range(len(phrases)) if used[index] >= 2]
    mapping = {index: number for number, index in enumerate(retained)}
    def prune(node):
        if type(node) is tuple and len(node) == 2 and node[0] == _TEXT_PHRASE:
            return (_TEXT_PHRASE, mapping[node[1]]) if node[1] in mapping else phrases[node[1]]
        return _children(node, prune, work)
    return _factor_phrases([phrases[index] for index in retained], prune(encoded), work)


class _LiteralMatcher:
    """Metered reverse trie: earliest start, first listed nonempty literal.

    Failure links cache the smallest alternative rank, without enumerating all
    overlapping outputs. A reverse scan records the winner at each start; the
    forward pass skips consumed spans exactly like escaped-literal re.finditer.
    Every choice, node/edge operation, failure traversal and scan step spends the
    caller's shared work budget before allocating or performing that work.
    """
    def __init__(self, choices, work):
        self.work = work
        work.spend()
        self.choices, self.edges, self.failure, self.best = [], [{}], [0], [None]
        for rank, phrase in enumerate(choices):
            work.spend()
            if type(phrase) is not str or not phrase:
                raise ValueError("Literal matcher requires nonempty strings")
            self.choices.append(phrase)
            state = 0
            for char in reversed(phrase):
                work.spend()
                child = self.edges[state].get(char)
                if child is None:
                    work.spend(4)
                    child = len(self.edges)
                    self.edges[state][char] = child
                    self.edges.append({})
                    self.failure.append(0)
                    self.best.append(None)
                state = child
            work.spend()
            if self.best[state] is None:
                self.best[state] = rank
        queue = []
        for child in self.edges[0].values():
            work.spend()
            queue.append(child)
        head = 0
        while head < len(queue):
            work.spend()
            state = queue[head]
            head += 1
            for char, child in self.edges[state].items():
                work.spend()
                fallback = self.failure[state]
                while True:
                    work.spend()
                    target = self.edges[fallback].get(char)
                    if target is not None or fallback == 0:
                        break
                    work.spend()
                    fallback = self.failure[fallback]
                work.spend(4)
                self.failure[child] = target if target is not None else 0
                inherited = self.best[self.failure[child]]
                if inherited is not None and (self.best[child] is None or inherited < self.best[child]):
                    self.best[child] = inherited
                queue.append(child)

    def finditer(self, text):
        work = self.work
        work.spend()
        if not self.choices:
            return
        winners, state = [], 0
        for char in reversed(text):
            work.spend()
            while True:
                work.spend()
                child = self.edges[state].get(char)
                if child is not None or state == 0:
                    state = child if child is not None else 0
                    break
                work.spend()
                state = self.failure[state]
            work.spend(2)
            winners.append(self.best[state])
        offset = 0
        while offset < len(text):
            work.spend()
            rank = winners[len(text) - offset - 1]
            if rank is None:
                offset += 1
                continue
            work.spend()
            phrase = self.choices[rank]
            end = offset + len(phrase)
            yield offset, end, phrase
            offset = end


def _factor_phrases(phrases, value, work=None):
    """Reuse existing visible definitions; add no short or external dictionary."""
    if work is None:
        work = _EncodingWork()
    work.spend(4 * len(phrases) * (len(phrases).bit_length() + 1))
    order = sorted(range(len(phrases)), key=lambda index: (len(phrases[index]), index))
    mapping = {index: number for number, index in enumerate(order)}
    earlier, definitions, patterns = {}, [], {}
    for index in order:
        text = phrases[index]
        length = len(text)
        if length not in patterns:
            work.spend(len(earlier))
            choices = [phrase for phrase in earlier if len(phrase) < length]
            choices = _sorted_strings(choices, work, longest=True)
            patterns[length] = _LiteralMatcher(choices, work) if choices else None
        pattern = patterns[length]
        pieces, offset = [], 0
        for start, end, phrase in pattern.finditer(text) if pattern else ():
            if offset < start:
                work.spend(start - offset)
                pieces.append(text[offset:start])
            work.spend(2)
            pieces.append((_TEXT_PHRASE, earlier[phrase]))
            offset = end
        if offset < len(text):
            work.spend(len(text) - offset)
            pieces.append(text[offset:])
        definition = pieces[0] if len(pieces) == 1 else (_TEXT_CONCAT, pieces)
        definitions.append(definition if len(_atom_literal(definition, work)) < len(_repr(text, work)) else text)
        earlier[text] = mapping[index]
    def remap(node):
        if type(node) is tuple and len(node) == 2 and node[0] == _TEXT_PHRASE:
            return (_TEXT_PHRASE, mapping[node[1]])
        return _children(node, remap, work)
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


def _copy_aliased(value, active, work=None):
    """Validate exact JSON types and copy containers, detecting only active cycles."""
    work = _work(work)
    work.spend()
    kind = type(value)
    if kind is dict or kind is list:
        identity = id(value)
        if identity in active:
            raise ValueError("Cyclic input is not JSON data")
        active.add(identity)
        try:
            if kind is list:
                work.spend(len(value))
                return [_copy_aliased(child, active, work) for child in value]
            result = {}
            for key, child in value.items():
                if type(key) is not str:
                    raise ValueError("Object keys must be strings")
                work.spend(len(key) + 1)
                result[_alias(key)] = _copy_aliased(child, active, work)
            return result
        finally:
            active.remove(identity)
    if value is None or kind in (str, int, bool):
        return value
    if kind is float and math.isfinite(value):
        return value
    raise ValueError("Only exact JSON data types and finite numbers are supported")


def _digest(value, work=None):
    work = _work(work)
    metric = _json_preflight(value, work)
    work.spend(3 * metric[5])
    original = json.dumps(
        value, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    )
    return "sha256:" + hashlib.sha256(
        original.encode("utf-8")
    ).hexdigest()


def _keysets(value, work=None):
    work = _work(work)
    counts = {}

    def count(node):
        work.spend()
        if type(node) is dict:
            for key in node:
                work.spend(len(key) + 1)
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
        work.spend(3 * len(keys) + 1)
        index = len(selected)
        ordinary = len(_literal(dict.fromkeys(keys), work))
        record = len(_literal({"@": [index, [None] * len(keys)]}, work))
        benefit = occurrences * (ordinary - record) - len(_literal(list(keys), work))
        if occurrences >= 2 and benefit > 0:
            work.spend(len(keys) + 1)
            selected.append(list(keys))
    return selected


def _pack(value, indices, schema=SCHEMA, work=None):
    work = _work(work)
    work.spend(1 + (len(value) if type(value) in (dict, list) else 0))
    if type(value) is dict:
        if schema in (CURRENT_SCHEMA, ATOM_SCHEMA) and len(value) == 1 and "r" in value:
            return (_pack(value["r"], indices, schema, work),)
        values = [_pack(child, indices, schema, work) for child in value.values()]
        index = indices.get(tuple(value))
        if index is not None:
            return {"@": [index, values]} if schema == SCHEMA else tuple([index, *values])
        return dict(zip(value, values))
    if type(value) is list:
        return [_pack(child, indices, schema, work) for child in value]
    return value


def _children(value, transform, work=None):
    if work is not None:
        work.spend(1 + (len(value) if type(value) in (dict, list, tuple) else 0))
    if type(value) is dict:
        return {key: transform(child) for key, child in value.items()}
    if type(value) is list:
        return [transform(child) for child in value]
    if type(value) is tuple:
        return tuple(transform(child) for child in value)
    return value


def _walk(value, visit, work=None):
    if work is not None:
        work.spend(1 + (2 * len(value) if type(value) is str else 0))
    visit(value)
    children = value.values() if type(value) is dict else value if type(value) in (list, tuple) else ()
    for child in children:
        _walk(child, visit, work)


def _share(value, work=None):
    """Select visible definitions by deterministic character savings, not a tokenizer."""
    work = _work(work)
    counts = Counter()
    def count_string(node):
        if type(node) is str:
            counts[node] += 1
    _walk(value, count_string, work)
    strings = []
    for string, count in counts.items():
        if (count >= 2 and len(string) >= 16 and (count - 1) * len(_repr(string, work))
                > count * len(_literal((None, len(strings)), work)) + 1):
            strings.append(string)
    work.spend(len(strings))
    indices = {string: index for index, string in enumerate(strings)}
    def encode_strings(node):
        if type(node) is str and node in indices:
            return (None, indices[node])
        return _children(node, encode_strings, work)
    encoded = encode_strings(value)
    counts = Counter()
    def count_container(node):
        if type(node) in (dict, list, tuple):
            key = _literal(node, work)
            work.spend(2 * len(key) + 1)
            counts[key] += 1
    _walk(encoded, count_container, work)
    work.spend(len(counts))
    selected = {key for key, count in counts.items() if count >= 2 and len(key) >= 24
        and (count - 1) * len(key) > count * len(_literal((False, len(counts)), work)) + 1}
    definitions, identities = [], {}
    def encode_shared(node):
        key = _literal(node, work) if type(node) in (dict, list, tuple) else None
        if key is not None:
            work.spend(2 * len(key) + 1)
        if key in selected:
            if key not in identities:
                definition = _children(node, encode_shared, work)
                identities[key] = len(definitions)
                definitions.append(definition)
            return (False, identities[key])
        return _children(node, encode_shared, work)
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


def _scalar_bytes(value):
    if type(value) is int:
        # 30103/100000 exceeds log10(2): bound decimal digits without str(int).
        digits = max(1, (value.bit_length() * 30103 + 99999) // 100000)
        return max(32, digits + (1 if value < 0 else 0))
    return 32


def _wire_scalar_bytes(value):
    if value is None or type(value) is bool:
        return 5 if value is False else 4
    if type(value) is int:
        return max(1, (value.bit_length() * 30103 + 99999) // 100000) + (1 if value < 0 else 0)
    return 32


def _expanded_preflight(packet, schema, work=None, *, reserve_restore=True):
    """Saturating DAG analysis before phrase joins, base64 or subtree copies.

    Metrics count expanded UTF-8 text, nodes and JSON depth, including cached
    definitions. No reference expansion, concatenation or deepcopy occurs here.
    Canonical and digest checks still run afterwards, without granting trust to
    malformed packets merely because their resource metrics fit.
    """
    work = _work(work)
    def metric(size, nodes=1, depth=1):
        if size > MAX_EXPANDED_BYTES or nodes > MAX_EXPANDED_NODES or depth > MAX_DEPTH:
            raise ValueError("Compact expansion exceeds " + RESOURCE_POLICY)
        return size, nodes, depth
    def combine(children, overhead=0):
        size, nodes, depth = overhead, 1, 1
        for child in children:
            size += child[0]
            nodes += child[1]
            depth = max(depth, child[2] + 1)
            metric(size, nodes, depth)
        return metric(size, nodes, depth)
    def literal(string):
        if type(string) is not str:
            raise ValueError("Invalid compact text")
        # Six bytes per character bounds JSON escaping as well as UTF-8 text.
        weighted = 6 * len(string)
        metric(weighted + 2)  # Reject before allocating an oversized UTF-8 copy.
        work.spend(len(string) + 1)
        return metric(max(len(string.encode("utf-8", errors="strict")), weighted) + 2)
    phrases = []
    def text(node, limit):
        work.spend()
        if type(node) is str:
            return literal(node)
        if type(node) is tuple and len(node) == 2:
            tag, value = node
            if tag == _TEXT_PHRASE:
                if type(value) is not int or not 0 <= value < limit:
                    raise ValueError("Invalid or forward visible phrase definition")
                return phrases[value]
            if tag == _TEXT_CONCAT and type(value) is list:
                # Treat text dependencies as depth too, bounding recursion before
                # unpacking a small phrase chain with enormous fanout.
                return combine((text(piece, limit) for piece in value))
            if tag == _TEXT_BASE64:
                child = text(value, limit)
                return metric(4 * ((child[0] + 2) // 3) + 2, child[1] + 1, child[2] + 1)
        raise ValueError("Invalid compact text grammar")
    if schema == ATOM_SCHEMA:
        if type(packet["phrases"]) is not list:
            raise ValueError("Invalid visible phrase definitions")
        for definition in packet["phrases"]:
            phrases.append(text(definition, len(phrases)))
        combine(phrases)
    strings = packet.get("strings", [])
    definitions = packet.get("shared", [])
    if type(strings) is not list or type(definitions) is not list:
        raise ValueError("Invalid compact definition tables")
    string_metrics = [text(item, len(phrases)) for item in strings]
    shared = []
    tables = packet["keysets"]
    def value(node, limit):
        work.spend()
        if type(node) is str:
            return literal(node)
        if type(node) is tuple:
            if len(node) == 2 and node[0] in (_TEXT_PHRASE, _TEXT_CONCAT, _TEXT_BASE64):
                return text(node, len(phrases))
            if len(node) == 2 and (node[0] is None or node[0] is False):
                index = node[1]
                table = string_metrics if node[0] is None else shared
                bound = len(table) if node[0] is None else limit
                if type(index) is not int or not 0 <= index < bound:
                    raise ValueError("Invalid or forward compact reference")
                result = table[index]
                return metric(result[0], result[1], result[2] + (1 if node[0] is False else 0))
            if len(node) == 1:
                return combine([value(node[0], limit)], len("$mvg_ref") * 6 + 6)
            if len(node) >= 2 and type(node[0]) is int:
                index = node[0]
                if not 0 <= index < len(tables) or len(node) - 1 != len(tables[index]):
                    raise ValueError("Invalid compact keyset record")
                return combine((value(child, limit) for child in node[1:]),
                    2 + sum(literal(_unalias(key))[0] + 2 for key in tables[index]))
            raise ValueError("Invalid compact tuple")
        if type(node) is dict:
            if schema == SCHEMA and "@" in node:
                record = node["@"]
                if set(node) != {"@"} or type(record) is not list or len(record) != 2:
                    raise ValueError("Invalid compact legacy record")
                index, children = record
                if (type(index) is not int or not 0 <= index < len(tables) or type(children) is not list
                        or len(children) != len(tables[index])):
                    raise ValueError("Invalid compact keyset record")
                return combine((value(child, limit) for child in children),
                    2 + sum(literal(_unalias(key))[0] + 2 for key in tables[index]))
            return combine((value(child, limit) for child in node.values()),
                2 + sum(literal(_unalias(key))[0] + 2 for key in node))
        if type(node) is list:
            return combine((value(child, limit) for child in node), len(node) + 2)
        return metric(_scalar_bytes(node))
    for definition in definitions:
        shared.append(value(definition, len(shared)))
    # Count caches and final expanded output together. This is a finite host
    # budget, deliberately distinct from the encoded model request byte limit.
    work.spend(len(phrases) + len(string_metrics) + len(shared) + 1)
    result = combine([*phrases, *string_metrics, *shared, value(packet["value"], len(shared))])
    # Reserve the bounded expanded copies/joins before invoking their old owners.
    if reserve_restore:
        work.spend(result[0] + result[1])
    return result


def _ast_preflight(node):
    pending, count = [(node, 0)], 0
    while pending:
        item, depth = pending.pop()
        count += 1
        if count > MAX_EXPANDED_NODES or depth > MAX_DEPTH:
            raise ValueError("Compact syntax exceeds " + RESOURCE_POLICY)
        pending.extend((child, depth + 1) for child in ast.iter_child_nodes(item))


def _metric(size, nodes=1, depth=1, volume=None, node_volume=None, wire_size=None, wire_volume=None, *, phase="input"):
    if size > MAX_EXPANDED_BYTES or nodes > MAX_EXPANDED_NODES or depth > MAX_DEPTH:
        raise ValueError("Compact input exceeds " + RESOURCE_POLICY +
            f"; bytes_bound={size}; nodes_bound={nodes}; depth_bound={depth}; phase={phase}")
    wire_size = size if wire_size is None else wire_size
    return (size, nodes, depth, size if volume is None else volume,
        nodes if node_volume is None else node_volume, wire_size,
        wire_size if wire_volume is None else wire_volume)


def _text_metric(text, work):
    size = 6 * len(text) + 2
    _metric(size)
    encoded_size = _utf8_size(text, work) + 2
    work.spend(encoded_size + len(text))
    text.encode("utf-8", errors="strict")
    encoded_size += sum(1 if char in '\\"\b\t\n\f\r' else 5 if ord(char) < 32 else 0 for char in text)
    return _metric(size, wire_size=encoded_size)


def _json_preflight(value, work=None):
    """Measure without rendering or a wide pending-node allocation."""
    work, active, cache = _work(work), set(), {}
    def visit(item, level):
        work.spend()
        if level > MAX_DEPTH:
            return _metric(0, depth=level)
        kind = type(item)
        if kind is str:
            return _text_metric(item, work)
        if item is None or kind in (bool, int) or kind is float and math.isfinite(item):
            return _metric(_scalar_bytes(item), wire_size=_wire_scalar_bytes(item))
        if kind not in (dict, list):
            raise ValueError("Only exact JSON data types and finite numbers are supported")
        identity = id(item)
        if identity in active:
            raise ValueError("Cyclic input is not JSON data")
        if identity in cache:
            result = cache[identity]
            _metric(result[0], result[1], result[2] + level - 1)
            return result
        active.add(identity)
        size, nodes, depth, volume = (2 if kind is dict else len(item) + 2), 1, 1, 0
        node_volume, wire_size, wire_volume = 0, size, 0
        _metric(size, nodes, depth)
        for key, child in (item.items() if kind is dict else ((None, child) for child in item)):
            work.spend()
            if kind is dict:
                if type(key) is not str:
                    raise ValueError("Object keys must be strings")
                key_metric = _text_metric(key, work)
                size += key_metric[0] + 2
                wire_size += key_metric[5] + 2
                _metric(size, nodes, depth)
            metric = visit(child, level + 1)
            size += metric[0]
            nodes += metric[1]
            depth = max(depth, metric[2] + 1)
            volume += metric[3]
            node_volume += metric[4]
            wire_size += metric[5]
            wire_volume += metric[6]
            _metric(size, nodes, depth)
        active.remove(identity)
        result = _metric(size, nodes, depth, volume + size, node_volume + nodes, wire_size, wire_volume + wire_size)
        cache[identity] = result
        return result
    return visit(value, 1)


def _syntax_preflight(text, work=None, *, json_only=False):
    """Count a restricted token stream before constructing any AST/JSON tree."""
    work, stack, offset, nodes, allow_value = _work(work), [], 0, 0, True
    while offset < len(text):
        work.spend()
        char = text[offset]
        if char.isspace():
            offset += 1
            continue
        if char in "{[(":
            if not allow_value:
                raise ValueError("Unsupported data expression")
            if json_only and char == "(":
                raise ValueError("Unsupported data syntax")
            nodes += 1 if char == "{" else 2
            if len(stack) + 1 > MAX_DEPTH:
                raise ValueError("Compact syntax exceeds " + RESOURCE_POLICY)
            stack.append(char)
            offset += 1
            allow_value = True
        elif char in "}])":
            if not stack or stack.pop() != {"}": "{", "]": "[", ")": "("}[char]:
                raise ValueError("Unbalanced data syntax")
            offset += 1
            allow_value = False
        elif char in ":,":
            offset += 1
            allow_value = True
        elif char in "\"'":
            if not allow_value:
                raise ValueError("Unsupported adjacent data literals")
            if json_only and char != '"':
                raise ValueError("Unsupported JSON string")
            quote = char
            offset += 1
            while offset < len(text):
                work.spend()
                char = text[offset]
                offset += 1
                if char == "\\":
                    work.spend()
                    offset += 1
                elif char == quote:
                    break
            else:
                raise ValueError("Unterminated data string")
            nodes += 1
            allow_value = False
        elif char == "-":
            if not allow_value or offset + 1 >= len(text) or not "0" <= text[offset + 1] <= "9":
                raise ValueError("Unsupported data operator")
            nodes += 2
            offset += 1
        elif "0" <= char <= "9":
            if not allow_value:
                raise ValueError("Unsupported adjacent data literals")
            offset += 1
            while offset < len(text) and "0" <= text[offset] <= "9":
                work.spend()
                offset += 1
            if offset < len(text) and text[offset] == ".":
                offset += 1
                while offset < len(text) and "0" <= text[offset] <= "9":
                    work.spend()
                    offset += 1
            if offset < len(text) and text[offset] in "eE":
                offset += 1
                if offset < len(text) and text[offset] in "+-":
                    offset += 1
                while offset < len(text) and "0" <= text[offset] <= "9":
                    work.spend()
                    offset += 1
            nodes += 1
            allow_value = False
        elif char.isascii() and char.isalpha():
            if not allow_value:
                raise ValueError("Unsupported adjacent data literals")
            start = offset
            while offset < len(text) and text[offset].isascii() and text[offset].isalnum():
                work.spend()
                offset += 1
            name = text[start:offset]
            if name not in (("true", "false", "null") if json_only else ("True", "False", "None", "C", "B")):
                if json_only or name[0] not in "RSDPH" or not name[1:].isdigit():
                    raise ValueError("Unsupported data name")
            nodes += 2
            allow_value = False
        else:
            raise ValueError("Unsupported data syntax")
        if nodes > MAX_EXPANDED_NODES:
            raise ValueError("Compact syntax exceeds " + RESOURCE_POLICY + f"; nodes_bound={nodes}")
    if stack:
        raise ValueError("Unbalanced data syntax")
    work.spend(nodes)
    return nodes


def _utf8_size(text, work):
    work.spend(len(text))
    size = 0
    for char in text:
        code = ord(char)
        if 0xD800 <= code <= 0xDFFF:
            raise ValueError("JSON data must be encodable as strict UTF-8")
        size += 1 if code < 128 else 2 if code < 2048 else 3 if code < 65536 else 4
    return size


def _encoded_preflight(text, work):
    if len(text) > MAX_ENCODED_BYTES:
        raise ValueError("Compact encoded bytes exceed " + RESOURCE_POLICY)
    size = _utf8_size(text, work)
    if size > MAX_ENCODED_BYTES:
        raise ValueError("Compact encoded bytes exceed " + RESOURCE_POLICY)
    return size


def _bounded_packet(text, schema, work=None):
    work = _work(work)
    _encoded_preflight(text, work)
    try:
        _syntax_preflight(text, work)
        node = ast.parse(text, mode="eval").body
        _ast_preflight(node)
        _expanded_preflight(_parse(node, schema), schema, work, reserve_restore=False)
    except (SyntaxError, RecursionError) as exc:
        raise ValueError("Compact syntax exceeds " + RESOURCE_POLICY) from exc
    return text


def dumps(value: dict, *, schema=None, work=None) -> str:
    """Return the deterministic packet literal for a complete JSON object.

    Reject non-JSON values, subclasses and cycles with ValueError. No caller
    containers are retained or modified. Runtime depth/integer limits still apply.
    """
    schema = _schema(schema)
    work = _work(work)
    work.phase = "compact.encode"
    if type(value) is not dict:
        raise ValueError("The top-level value must be an object")
    try:
        _json_preflight(value, work)
        aliased = _copy_aliased(value, set(), work)
        tables = _keysets(aliased, work)
        if schema in (CURRENT_SCHEMA, ATOM_SCHEMA):
            tables = [keys for keys in tables if keys]
        work.spend(sum(len(keys) + 1 for keys in tables))
        indices = {tuple(keys): index for index, keys in enumerate(tables)}
        packed = _pack(aliased, indices, schema, work)
        if schema in (CURRENT_SCHEMA, ATOM_SCHEMA):
            strings, definitions, packed = _share(packed, work)
            if schema == ATOM_SCHEMA:
                phrases, encoded = _pack_text([strings, definitions, packed], work)
                strings, definitions, packed = encoded
                return _bounded_packet(_atom_literal({"schema_version": schema, "keysets": tables,
                    "strings": strings, "shared": definitions, "phrases": phrases,
                    "value": packed, "sha256": _digest(value, work)}, work), schema, work)
            render = _atom_literal if schema == ATOM_SCHEMA else _literal
            return _bounded_packet(render({"schema_version": schema, "keysets": tables,
                "strings": strings, "shared": definitions, "value": packed, "sha256": _digest(value, work)}, work), schema, work)
        return _bounded_packet(_literal({
            "schema_version": schema,
            "keysets": tables,
            "value": packed,
            "sha256": _digest(value, work),
        }, work), schema, work)
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


def loads(text: str, *, work=None) -> dict:
    """Restore a fresh object from an exact canonical packet, or raise ValueError.

    Parsing uses only AST data nodes. Digest and full re-encoding validation are
    mandatory; a valid digest alone cannot make a noncanonical packet acceptable.
    """
    if type(text) is not str:
        raise ValueError("The literal must be text")
    try:
        work = _work(work)
        work.phase = "compact.decode"
        _encoded_preflight(text, work)
        _syntax_preflight(text, work)
        node = ast.parse(text, mode="eval").body
        _ast_preflight(node)
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
        _expanded_preflight(packet, schema, work)
        used = set()
        if schema == ATOM_SCHEMA:
            packet["strings"], packet["shared"], packet["value"] = _unpack_text(
                [packet["strings"], packet["shared"], packet["value"]], packet["phrases"])
        if schema in (CURRENT_SCHEMA, ATOM_SCHEMA):
            packet["value"] = _unshare(packet["value"], packet["strings"], packet["shared"])
        restored = _restore(packet["value"], tables, used, schema)
        if type(restored) is not dict or len(used) != len(tables):
            raise ValueError("Expected an object and complete keyset usage")
        if type(packet["sha256"]) is not str or packet["sha256"] != _digest(restored, work):
            raise ValueError("Original JSON digest mismatch")
        if dumps(restored, schema=schema, work=work) != text:
            raise ValueError("Noncanonical compact literal packet")
        return restored
    except (SyntaxError, RecursionError, UnicodeError) as exc:
        raise ValueError("Invalid data literal or runtime nesting limit") from exc
