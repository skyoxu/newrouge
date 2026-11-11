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
RESIDUAL_SCHEMA = "newrouge.b-route-compact-literal.v4"
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
RESIDUAL_INSTRUCTION = ATOM_INSTRUCTION.replace(ATOM_SCHEMA, RESIDUAL_SCHEMA) + (
    " v4 additionally shares exact residual literal prefixes through the same visible P/C grammar; "
    "every original character and all integrity metadata remain present after restoration."
)


def _schema(schema):
    if schema is None:
        return SCHEMA
    if type(schema) is not str or schema not in (SCHEMA, CURRENT_SCHEMA, ATOM_SCHEMA, RESIDUAL_SCHEMA):
        raise ValueError("Unsupported compact literal schema")
    return schema


def instruction(schema=None):
    """Return the complete decoder instructions for an explicitly selected packet."""
    schema = _schema(schema)
    return (INSTRUCTION if schema == SCHEMA else CURRENT_INSTRUCTION if schema == CURRENT_SCHEMA
        else ATOM_INSTRUCTION if schema == ATOM_SCHEMA else RESIDUAL_INSTRUCTION)

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
# ADR-0055 sets a measured fixed work ceiling without changing other bounds.
RESOURCE_POLICY = "newrouge.b-route-resource-pipeline.v4"
MAX_ENCODED_BYTES = 8 * 1024 * 1024
MAX_EXPANDED_BYTES = 64 * 1024 * 1024
MAX_EXPANDED_NODES = 1_000_000
MAX_DEPTH = 128
MAX_ENCODING_WORK = 170_000_000


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


def _repr_size(value, work):
    # Prepay the added private helper call/return and its scalar dispatch.
    work.spend(4)
    if type(value) is str:
        work.spend(len(value) + 1)
        size = 2
        for char in value:
            code = ord(char)
            size += (2 if char in "\\\"'\n\r\t" else 1 if char.isprintable()
                else 4 if code <= 255 else 6 if code <= 65535 else 10)
        return size
    return _scalar_bytes(value)


def _repr(value, work):
    size = _repr_size(value, work)
    work.spend(size)
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
    work.spend(4)  # Text length and fixed bucket setup.
    size = len(text)
    starts = {}
    for fragment in originals:
        work.spend(8)  # Iteration, length, empty/oversized checks and reserve arithmetic.
        length = len(fragment)
        if not fragment or length > size:
            continue
        # Retain the original once-per-indexed-fragment reservation.
        work.spend(length + 1)
        work.spend(5)  # First character, bucket/list allocation and append.
        starts.setdefault(fragment[0], []).append(fragment)
    work.spend(3)  # Allocate the initial complete-end witness set.
    reachable = {size}
    work.spend(4)  # Reverse-range arithmetic, allocation and iterator setup.
    for offset in range(size - 1, -1, -1):
        work.spend(5)  # Position/character read, bucket lookup and iteration.
        for fragment in starts.get(text[offset], ()):
            work.spend(9)  # Length/end arithmetic, membership and branch.
            length = len(fragment)
            end = offset + length
            if end not in reachable:
                continue
            # Only an actual startswith reserves the SAME original comparison
            # weight. Impossible DP edges never perform a character comparison.
            work.spend(len(fragment) + 1)
            if text.startswith(fragment, offset):
                work.spend(2)  # Publish this complete predecessor and break.
                reachable.add(offset)
                break
    work.spend()  # Final exact reachability observation.
    return 0 in reachable


class _SubstringIndex:
    """Action-local generalized SAM for the union of completed leaf substrings."""
    __slots__ = ('edges', 'links', 'lengths', 'last', 'epoch', 'failed')

    def __new__(cls, work):
        # Includes one prepaid fail-closed poison write if this action aborts.
        work.spend(13)
        return object.__new__(cls)

    def __init__(self, work):
        self.edges = [{}]
        self.links = [-1]
        self.lengths = [0]
        self.last = 0
        self.epoch = 0
        self.failed = False

    def _state(self, length, link, copy_from, work):
        count = 0 if copy_from is None else len(copy_from)
        # Prepay dict/state allocation, three array appends, metadata and every
        # clone entry read/move/insert before allocating or copying anything.
        work.spend(10 + 4 * count)
        edges = {} if copy_from is None else {symbol: target for symbol, target in copy_from.items()}
        state = len(self.edges)
        self.edges.append(edges)
        self.links.append(link)
        self.lengths.append(length)
        return state

    def _extend(self, symbol, work):
        work.spend(4)  # Last-state read, length increment and traversal setup.
        current = self._state(self.lengths[self.last] + 1, 0, None, work)
        previous = self.last
        existing = None
        while True:
            work.spend(2)  # Suffix-link boundary and loop control.
            if previous < 0:
                break
            work.spend(2)  # Exact integer-symbol edge lookup and branch.
            existing = self.edges[previous].get(symbol)
            if existing is not None:
                break
            work.spend(3)  # New edge plus suffix-link read/move.
            self.edges[previous][symbol] = current
            previous = self.links[previous]
        work.spend(2)
        if previous >= 0:
            target = existing
            work.spend(5)  # State/length observations, increment and branch.
            if self.lengths[previous] + 1 == self.lengths[target]:
                work.spend()
                self.links[current] = target
            else:
                work.spend(4)  # Clone arguments and length arithmetic.
                clone = self._state(self.lengths[previous] + 1, self.links[target], self.edges[target], work)
                while True:
                    work.spend(2)
                    if previous < 0:
                        break
                    work.spend(2)
                    if self.edges[previous].get(symbol) != target:
                        break
                    work.spend(3)  # Redirect an existing edge, then follow its suffix link.
                    self.edges[previous][symbol] = clone
                    previous = self.links[previous]
                work.spend(2)
                self.links[target] = clone
                self.links[current] = clone
        work.spend()
        self.last = current

    def append(self, text, work, *, epoch):
        if self.failed:
            raise ValueError('Incomplete substring index cannot be reused')
        try:
            work.spend(6)  # Exact input/epoch checks and unpublished-leaf marker.
            if type(text) is not str or type(epoch) is not int or epoch != self.epoch:
                raise ValueError('Substring index requires the next complete leaf epoch')
            self.failed = True
            work.spend(1)  # A new leaf starts at root, never a prior leaf's tail.
            self.last = 0
            for char in text:
                work.spend(3)  # Loop, character read and exact code-point conversion.
                symbol = ord(char)
                work.spend(5)  # Existing-prefix edge lookup and branch.
                target = self.edges[self.last].get(symbol)
                if target is None:
                    self._extend(symbol, work)
                else:
                    work.spend(4)  # Exact prefix-length comparison.
                    if self.lengths[target] == self.lengths[self.last] + 1:
                        work.spend(1)
                        self.last = target
                    else:
                        work.spend(5)  # Clone arguments and redirect traversal setup.
                        clone = self._state(self.lengths[self.last] + 1,
                            self.links[target], self.edges[target], work)
                        previous = self.last
                        while True:
                            work.spend(2)
                            if previous < 0:
                                break
                            work.spend(2)
                            if self.edges[previous].get(symbol) != target:
                                break
                            work.spend(3)
                            self.edges[previous][symbol] = clone
                            previous = self.links[previous]
                        work.spend(2)
                        self.links[target] = clone
                        self.last = clone
            work.spend(3)  # Publish only the completely inserted leaf.
            self.epoch += 1
            self.failed = False
        except BaseException:
            # The constructor prepaid this single final poison write. No graph
            # or epoch is published after a budget/allocation interruption.
            self.failed = True
            raise

    def longest(self, text, offset, prefix_size, work, *, epoch):
        if self.failed:
            raise ValueError('Incomplete substring index cannot be queried')
        work.spend(10)  # Input/epoch/position checks and fixed root-query state.
        if (type(text) is not str or type(offset) is not int or not 0 <= offset <= len(text)
                or type(prefix_size) is not int or prefix_size < 0
                or type(epoch) is not int or epoch != self.epoch):
            raise ValueError('Substring query requires an exact current leaf position and epoch')
        state, cursor, length = 0, offset, 0
        while True:
            work.spend(2)
            if cursor == len(text):
                break
            work.spend(4)  # Character/ord, exact edge lookup and missing-edge branch.
            target = self.edges[state].get(ord(text[cursor]))
            if target is None:
                break
            work.spend(3)  # State move and both query-position increments.
            state = target
            cursor += 1
            length += 1
        work.spend()
        # The original prefix bucket contained no witness shorter than16.
        return length if length >= prefix_size else 0

    def lengths_for_leaf(self, text, prefix_size, work, *, epoch):
        """Return every longest previous-leaf prefix without restarting at root."""
        if self.failed:
            raise ValueError('Incomplete substring index cannot be queried')
        work.spend(20)  # Exact input/epoch checks, size and fixed scan state.
        if (type(text) is not str or type(prefix_size) is not int or prefix_size < 0
                or type(epoch) is not int or epoch != self.epoch):
            raise ValueError('Substring query requires an exact current leaf and epoch')
        size = len(text)
        work.spend(size + 10)  # Reserve every list slot and scan setup before allocation.
        ends = [-1] * size
        state, length = 0, 0
        work.spend()  # Initialize the next not-yet-finalized output position.
        cursor = 0
        for end in range(size):
            work.spend(6)  # Loop/position, character read and integer symbol.
            symbol = ord(text[end])
            while True:
                work.spend(5)  # Loop, state-edge read, lookup, assignment and branch.
                target = self.edges[state].get(symbol)
                if target is not None:
                    work.spend(3)  # State move, length arithmetic and write.
                    state, length = target, length + 1
                    break
                work.spend(2)  # Root observation and missing-edge branch.
                if state == 0:
                    work.spend()
                    length = 0
                    break
                work.spend(4)  # Suffix-link read/move and its exact length.
                state = self.links[state]
                length = self.lengths[state]
            # L[end] <= L[end-1]+1, so the longest suffix start never moves
            # backwards. Starts before this boundary cannot reach this end;
            # their final farthest match ended at end-1. Write each once.
            work.spend(5)  # Read end/length, subtract/add and bind boundary.
            boundary = end - length + 1
            while True:
                work.spend(2)  # Boundary comparison and loop control, including exit.
                if cursor >= boundary:
                    break
                work.spend(8)  # Length calculation, threshold, slot write and cursor move.
                value = end - cursor
                ends[cursor] = value if value >= prefix_size else 0
                cursor += 1
        # Every remaining start reaches the last character. No second whole
        # table normalization or repeated raw-end update is needed.
        while True:
            work.spend(2)
            if cursor >= size:
                break
            work.spend(8)
            value = size - cursor
            ends[cursor] = value if value >= prefix_size else 0
            cursor += 1
        return ends


def _pack_text(value, work=None, *, schema=ATOM_SCHEMA):
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
    substrings, candidates = _SubstringIndex(work), set()
    prefix_size = min(16, _MIN_PHRASE)
    for index, text in enumerate(texts):
        # Longest-first order makes every remaining short leaf incapable of
        # adding a >=64 candidate. Later matching/rendering still sees texts.
        work.spend(32, phase='compact.text.discovery.length_guard')
        if len(text) < _MIN_PHRASE:
            break
        if len(text) >= _MIN_PHRASE and text_counts[text] >= 2:
            candidates.add(text)
        # The newly constructed index has no previous-leaf witness at zero.
        # Keep its whole-text candidate above and the same epoch append below.
        work.spend(32, phase='compact.text.discovery.first_guard')
        if index:
            lengths = substrings.lengths_for_leaf(text, prefix_size, work, epoch=index)
            offset = 0
            while offset + _MIN_PHRASE <= len(text):
                work.spend(3)  # Loop bounds; no obsolete16-character slice/index allocation.
                work.spend()  # Read the same exact maximum from this leaf's table.
                best = lengths[offset]
                if best >= _MIN_PHRASE:
                    work.spend(best)
                    candidates.add(text[offset:offset + best])
                    offset += best
                else:
                    offset += 1
            work.spend()  # Release the leaf-only table before publishing its text.
            del lengths
        # Publish this complete eligible leaf at its original index/epoch.
        substrings.append(text, work, epoch=index)
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
    if schema == RESIDUAL_SCHEMA:
        originals = [phrases[index] for index in retained]
        definitions, packed = _factor_phrases(originals, prune(encoded), work)
        return _residual_text(definitions, packed, originals, work)
    return _factor_phrases([phrases[index] for index in retained], prune(encoded), work)


class _ResidualScanCache:
    """Action-local exact greedy spans, bounded with the owner's retained graphs.

    Bounds are the existing logical expansion contract, not Python heap/RSS.
    A row retains a full logical text key and each complete winner string. This
    overcounts shared string references but never discounts them by identity.
    Scanner winners coexist with every pending/published cache row. Insufficient
    cache space discards rows BEFORE invoking the original scanner or appending
    another span; the unchanged work account may still refuse that fallback.
    """
    def __new__(cls, work, max_scan_chars):
        # Both work AND logical fixed metadata are reserved before allocating
        # the instance. Returning None skips __init__ and retains no cache.
        work.spend(96)  # Validation, bounds, instance/fields and final cleanup.
        retained = getattr(work, '_residual_retained', None)
        if (type(retained) is not tuple or len(retained) != 3
                or any(type(part) is not int or part < 0 for part in retained)):
            raise ValueError('Invalid internal residual retained measurement')
        _metric(*retained, phase='compact.residual.retained')
        if type(max_scan_chars) is not int or max_scan_chars < 0:
            raise ValueError('Invalid internal residual scanner bound')
        # Derive this from the actual distinct eligible leaves, never a wire
        # length. Empty cache plus the worst scanner must fit BEFORE instance
        # allocation, so _drop always leaves enough room for a later fallback.
        size = retained[0] + 256 + 32 * max_scan_chars + 2
        nodes = retained[1] + 4 + max_scan_chars + 1
        depth = max(retained[2], 4)
        if size > MAX_EXPANDED_BYTES or nodes > MAX_EXPANDED_NODES or depth > MAX_DEPTH:
            return None
        _metric(size, nodes, depth, phase='compact.residual.fixed_cache')
        return object.__new__(cls)

    def __init__(self, work, max_scan_chars):
        self.work = work
        self.retained = getattr(work, '_residual_retained', None)
        if (type(self.retained) is not tuple or len(self.retained) != 3
                or any(type(part) is not int or part < 0 for part in self.retained)):
            raise ValueError('Invalid internal residual retained measurement')
        _metric(*self.retained, phase='compact.residual.retained')
        self.max_scan_chars = max_scan_chars
        self.size, self.nodes = 256, 4
        self.rows = {} if self._room(0, 0) else None

    def _room(self, extra_size, extra_nodes, scan_size=0, scan_nodes=0):
        self.work.spend(32)  # Reads, additions, bounds, metric call/result and branches.
        size = self.retained[0] + self.size + extra_size + scan_size
        nodes = self.retained[1] + self.nodes + extra_nodes + scan_nodes
        depth = max(self.retained[2], 4)
        if size > MAX_EXPANDED_BYTES or nodes > MAX_EXPANDED_NODES or depth > MAX_DEPTH:
            return False
        _metric(size, nodes, depth, phase='compact.residual.scan_cache')
        return True

    def _scan(self, text):
        self.work.spend(12)  # Length, sealed bound, scalar/list metrics and tuple.
        if len(text) > self.max_scan_chars:
            raise ValueError('Residual text exceeds this action scanner bound')
        # finditer retains one rank/None winner per character. _scalar_bytes
        # bounds both with 32 logical bytes; the list itself has one node.
        return 32 * len(text) + 2, len(text) + 1

    def _drop(self):
        self.work.spend(8)  # Clear call and metric reset; entry release prepaid.
        self.rows.clear()
        self.size, self.nodes = 256, 4

    def capture(self, text, pattern):
        work = self.work
        work.spend(12)  # Generator locals, branches, final row cleanup.
        row, published = None, False
        row_size, row_nodes = 6 * len(text) + 100, 3
        scan_size, scan_nodes = self._scan(text)
        if self.rows is not None:
            if not self._room(row_size, row_nodes, scan_size, scan_nodes):
                self._drop()
            if self._room(row_size, row_nodes, scan_size, scan_nodes):
                work.spend(4)  # Empty row allocation and eventual clear.
                row = []
        try:
            for start, end, phrase in pattern.finditer(text):
                work.spend(6)  # Loop, unpack, row branch and yield bookkeeping.
                if row is not None:
                    work.spend(16)  # Scalar bit lengths, lengths and span metric.
                    span_size = _scalar_bytes(start) + _scalar_bytes(end) + 6 * len(phrase) + 8
                    if not self._room(row_size + span_size, row_nodes + 4, scan_size, scan_nodes):
                        # No new tuple/list slot is allocated before the bound.
                        work.spend(6)  # Clear and local row release, prepaid spans.
                        row.clear()
                        row = None
                    else:
                        work.spend(16)  # Tuple fields/allocation, append and cleanup credit.
                        row.append((start, end, phrase))
                        row_size += span_size
                        row_nodes += 4
                yield start, end, phrase
            if row is not None:
                # Hash/equality of the complete exact key plus dict entry/write,
                # metric updates and eventual key/row destruction are prepaid.
                work.spend(2 * len(text) + 20)
                self.rows[text] = row
                self.size += row_size
                self.nodes += row_nodes
                published = True
        finally:
            if row is not None and not published:
                row.clear()  # Prepaid; never mask a work/MemoryError primary.

    def replay(self, text, pattern):
        work = self.work
        work.spend(2 * len(text) + 12)  # Exact cache key hash/equality and branches.
        row = None if self.rows is None else self.rows.get(text)
        if row is not None:
            for start, end, phrase in row:
                work.spend(6)  # Original full winner tuple read/unpack and yield.
                yield start, end, phrase
            return
        scan_size, scan_nodes = self._scan(text)
        if self.rows is not None and not self._room(0, 0, scan_size, scan_nodes):
            self._drop()  # All new retained rows leave before fallback allocation.
        work.spend(4)  # Fallback generator construction and delegation.
        yield from pattern.finditer(text)

    def close(self):
        if self.rows is not None:
            self.rows.clear()  # All row/key/span release was prepaid.


def _residual_text(phrases, value, originals, work):
    """v4 only: share exact residual prefixes; leave all old definitions fixed.

    One adjacent-LCP span per distinct leaf plus duplicate complete leaves
    bounds candidate spelling by twice the unique residual text length. There
    are no suffix copies, all-pairs substring scans or cross-action caches.
    The matcher keeps its original winners even after benefit filtering, so
    counted occurrences and replacement spans cannot diverge through overlap.
    """
    work.spend(28)  # Local maps/lists, cache binding and eventual safe cleanup.
    counts, candidates, occurrences, indices, known = {}, {}, {}, {}, set()
    scans = None
    try:
        for text in originals:
            work.spend(2 * len(text) + 8)  # Exact hash/equality, entry and cleanup.
            known.add(text)

        def eligible(text):
            work.spend(4)  # Length, bounds and digest-shape branch.
            if len(text) < _MIN_PHRASE:
                return False
            if len(text) == 71:
                # Anchored fixed-width digest syntax has linear character work.
                # Complete digests retain their original possibly tiny H atom.
                work.spend(2 * len(text) + 8)
                if _FULL_SHA256.fullmatch(text):
                    return False
            return True

        def collect(node):
            work.spend(3)  # Type and branch; walk charges traversal.
            if type(node) is str and eligible(node):
                work.spend(2 * len(node) + 12)  # Hash/equality, count and cleanup.
                counts[node] = counts.get(node, 0) + 1
        _walk(value, collect, work)
        work.spend(4 * len(counts) * (len(counts).bit_length() + 1))
        ordered = _sorted_strings(counts, work)

        def candidate(text, length):
            # Prepay the one span copy and full exact dictionary/set probes.
            work.spend(5 * length + 16)
            prefix = text[:length]
            if prefix not in known and prefix not in candidates:
                candidates[prefix] = None

        previous = None
        for text in ordered:
            work.spend(12)  # Loop, count lookup, length, bounds and scalar moves.
            work.spend(2 * len(text))
            if counts[text] >= 2:
                candidate(text, len(text))
            if previous is not None:
                limit, length = min(len(previous), len(text)), 0
                while length < limit:
                    work.spend(10)  # Bounds, two character reads, compare and move.
                    if previous[length] != text[length]:
                        break
                    length += 1
                work.spend(2)
                if length >= _MIN_PHRASE:
                    candidate(text, length)
            previous = text
        if not candidates:
            return phrases, value
        work.spend(4 * len(candidates) * (len(candidates).bit_length() + 1))
        choices = _sorted_strings(candidates, work, longest=True)
        pattern = _LiteralMatcher(choices, work)
        work.spend(4)  # Optional actual-owner retention context lookup/branch.
        if getattr(work, '_residual_retained', None) is not None:
            work.spend(6 * len(counts) + 8)  # Exact metadata-only max-length pass.
            max_scan_chars = 0
            for text in counts:
                length = len(text)
                if length > max_scan_chars:
                    max_scan_chars = length
            scans = _ResidualScanCache(work, max_scan_chars)
        for text, count in counts.items():
            work.spend(4)
            work.spend(12)  # Branch/call, generator allocation and final close.
            matches = scans.capture(text, pattern) if scans is not None else pattern.finditer(text)
            try:
                for _start, _end, phrase in matches:
                    work.spend(2 * len(phrase) + 14)
                    occurrences[phrase] = occurrences.get(phrase, 0) + count
            finally:
                matches.close()  # Prepaid; closes pending capture on consumer refusal.
        work.spend(8 + _scalar_bytes(len(phrases) + len(choices)))
        reference_bound = 1 + len(str(len(phrases) + len(choices)))
        selected = []
        for phrase in choices:
            work.spend(2 * len(phrase) + 14)
            count = occurrences.get(phrase, 0)
            # Twelve characters cover quotes, commas, C wrapper and split
            # boundaries per occurrence; use original characters as a lower
            # savings bound even when repr escapes would save more.
            literal_size = len(_repr(phrase, work))
            if count >= 2 and count * len(phrase) > literal_size + 1 + count * (reference_bound + 12):
                work.spend(2 * len(phrase) + 12)
                indices[phrase] = len(phrases) + len(selected)
                selected.append(phrase)
        if not selected:
            return phrases, value

        def replace(node):
            work.spend(4)
            if type(node) is str:
                if not eligible(node):
                    return node
                work.spend(3)  # Local list/offset and eventual list release.
                pieces, offset = [], 0
                work.spend(12)  # Branch/call, generator allocation and final close.
                matches = scans.replay(node, pattern) if scans is not None else pattern.finditer(node)
                try:
                    for start, end, phrase in matches:
                        work.spend(2 * len(phrase) + 6)
                        if phrase not in indices:
                            continue
                        if offset < start:
                            work.spend(start - offset + 5)
                            pieces.append(node[offset:start])
                        work.spend(2 * len(phrase) + 8)
                        pieces.append((_TEXT_PHRASE, indices[phrase]))
                        offset = end
                finally:
                    matches.close()  # Prepaid; no traceback-held replay row.
                if not pieces:
                    return node
                if offset < len(node):
                    work.spend(len(node) - offset + 5)
                    pieces.append(node[offset:])
                work.spend(3)
                return pieces[0] if len(pieces) == 1 else (_TEXT_CONCAT, pieces)
            if type(node) is dict:
                work.spend(6 * len(node) + 4)  # Prepay the metadata sum loop itself.
                work.spend(sum(2 * len(key) + 1 for key in node))
            return _children(node, replace, work)

        # Original phrase indexes and definitions never move. New definitions
        # are complete literals, hence have no forward or cyclic dependency.
        work.spend(len(phrases) + len(selected) + 4)
        definitions = [*phrases, *selected]
        return definitions, replace(value)
    finally:
        # Entry/cache cleanup was prepaid; never mask a primary work/MemoryError.
        if scans is not None:
            scans.close()
        counts.clear()
        candidates.clear()
        occurrences.clear()
        indices.clear()
        known.clear()


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

    def finditer(self, text, *, exclude_full=False):
        work = self.work
        work.spend(8)  # Original setup plus new exact mode/branch bookkeeping.
        if type(exclude_full) is not bool:
            raise ValueError('Literal matcher exclusion mode must be an exact boolean')
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
        if exclude_full:
            work.spend(10)  # Bounds, last winner, choice length and comparison.
            if winners:
                rank = winners[-1]
                if rank is not None and len(self.choices[rank]) == len(text):
                    # Only offset zero can match the complete input. The reverse
                    # trie state is that exact terminal; its failure best is the
                    # highest-priority proper-prefix alternative.
                    work.spend(6)  # Failure/best reads and replacement slot.
                    winners[-1] = self.best[self.failure[state]]
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
    """Reuse one original largest proper-phrase matcher; preserve wire choices."""
    if work is None:
        work = _EncodingWork()
    work.spend(4 * len(phrases) * (len(phrases).bit_length() + 1))
    order = sorted(range(len(phrases)), key=lambda index: (len(phrases[index]), index))
    mapping = {index: number for number, index in enumerate(order)}
    work.spend(16)  # Endpoint lengths, maps/list setup and final metadata release.
    shortest = len(phrases[order[0]]) if order else 0
    longest = len(phrases[order[-1]]) if order else 0
    earlier, definitions = {}, []
    # This is exactly the distinct choice set of the OLD largest-length matcher.
    # Maximum-length phrases are never eligible in any definition, so retaining
    # them in the trie would add unnecessary graph/memory and is avoided.
    for index in order:
        work.spend(6)  # Iteration, index/text/length reads and comparison.
        text = phrases[index]
        if len(text) < longest:
            work.spend(2 * len(text) + 12)  # Full key hash/equality, entry and clear.
            earlier[text] = None
    choices = _sorted_strings(earlier, work, longest=True)
    pattern = _LiteralMatcher(choices, work) if choices else None
    work.spend(4)  # Clear call; per-entry release prepaid on insertion.
    earlier.clear()
    for index in order:
        text = phrases[index]
        length = len(text)
        work.spend(12)  # Branch/call, generator construction and final close.
        matches = pattern.finditer(text, exclude_full=True) if pattern and length > shortest else iter(())
        pieces, offset = [], 0
        try:
            for start, end, phrase in matches:
                if offset < start:
                    work.spend(start - offset)
                    pieces.append(text[offset:start])
                work.spend(2)
                pieces.append((_TEXT_PHRASE, earlier[phrase]))
                offset = end
        finally:
            # Tuple iterators have no close; actual scanners close on consumer
            # budget/allocation refusal without spending after the primary.
            if pattern and length > shortest:
                matches.close()
        if offset < len(text):
            work.spend(len(text) - offset)
            pieces.append(text[offset:])
        definition = pieces[0] if len(pieces) == 1 else (_TEXT_CONCAT, pieces)
        definitions.append(definition if len(_atom_literal(definition, work)) < len(_repr(text, work)) else text)
        work.spend(2 * len(text) + 12)  # Current exact key/entry and eventual release.
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
        if schema in (CURRENT_SCHEMA, ATOM_SCHEMA, RESIDUAL_SCHEMA) and len(value) == 1 and "r" in value:
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


class _ShareKeyCapacity(RuntimeError):
    """Private optimization-only miss; never a work or MemoryError refusal."""


def _share_literal_input_floor(value, work):
    """Current typed input floor, without rendering or a wide pending stack."""
    def visit(node):
        work.spend(8)
        kind = type(node)
        if kind is str:
            return 6 * len(node) + 2, 1
        if node is None or kind in (bool, int) or kind is float and math.isfinite(node):
            return _scalar_bytes(node), 1
        if kind not in (dict, list, tuple):
            return None
        size, nodes = 2 + len(node), 1
        for key, child in node.items() if kind is dict else ((None, child) for child in node):
            work.spend(8)
            if kind is dict:
                if type(key) is not str:
                    return None
                size += 6 * len(key) + 4
            result = visit(child)
            if result is None:
                return None
            size += result[0]
            nodes += result[1]
            if size > MAX_EXPANDED_BYTES or nodes > MAX_EXPANDED_NODES:
                return None
        return size, nodes
    return visit(value)


class _ShareStructuralKey:
    """Private immutable key; children are exact-interned keys, never records."""
    __slots__ = ('kind', 'parts', 'length', '_work', '_owner', '_hash')

    def __init__(self, kind, parts, length, owner):
        work = owner.work
        # parts is flat: (typed tag, original scalar OR canonical child key).
        # Prepay tuple copy/hash scans and direct scalar hash BEFORE either.
        work.spend(32 + 4 * len(parts))
        for index in range(1, len(parts), 2):
            value = parts[index]
            if type(value) is str:
                work.spend(len(value) + 1)
            elif type(value) is int:
                work.spend(_scalar_bytes(value))
            else:
                work.spend(2)
        frozen = tuple(parts)
        # Tuple hashing visits only these direct slots. Child __hash__ reads
        # its prepaid cached hash; it does not recursively hash child.parts.
        hashed = hash((kind, frozen))
        object.__setattr__(self, 'kind', kind)
        object.__setattr__(self, 'parts', frozen)
        object.__setattr__(self, 'length', length)
        object.__setattr__(self, '_work', work)
        object.__setattr__(self, '_owner', owner)
        object.__setattr__(self, '_hash', hashed)

    def __setattr__(self, name, value):
        raise AttributeError('Immutable share structural key')

    def __len__(self):
        self._work.spend(2)
        return self.length

    def __hash__(self):
        self._work.spend(2)  # Each actual dict get/insert invokes this again.
        return self._hash

    def __eq__(self, other):
        work = self._work
        work.spend(16)
        # Collision recursion has a real frame at every visited key.
        self._owner._reserve(1024, 32)
        try:
            if type(other) is not _ShareStructuralKey:
                return NotImplemented
            if (self.kind != other.kind or self.length != other.length or
                    len(self.parts) != len(other.parts)):
                return False
            for index in range(0, len(self.parts), 2):
                work.spend(12)  # Slot reads, tag test, identity and branches.
                tag = self.parts[index]
                if tag != other.parts[index]:
                    return False
                left, right = self.parts[index + 1], other.parts[index + 1]
                if left is right:
                    continue
                if tag == 5:
                    # A real collision compares complete typed child structures.
                    # Recursive calls pay their own actual comparisons.
                    if left != right:
                        return False
                else:
                    work.spend(len(left) + len(right) + 1 if tag == 0 else
                        _scalar_bytes(left) + _scalar_bytes(right) + 4)
                    if left != right:
                        return False
                    # Finite float equality has exactly one repr ambiguity: +/-0.
                    # Type tags already distinguish bool/int/float/None/string.
                    if tag == 4 and left == 0.0 and math.copysign(1.0, left) != math.copysign(1.0, right):
                        return False
            return True
        finally:
            self._owner._release(1024, 32)


class _ShareLiteralKeys:
    """Action-local structural keys; exact equality, before-allocation room."""
    FIXED_BYTES = 4096
    FIXED_NODES = 64

    def __new__(cls, work, value, encoded, counts, by_id):
        work.spend(192)  # Validation, constructor/fields, sentinel and final cleanup.
        retained = getattr(work, '_residual_retained', None)
        if retained is None:
            return None
        if (type(retained) is not tuple or len(retained) != 3 or
                any(type(part) is not int or part < 0 for part in retained)):
            raise ValueError('Invalid internal share retained measurement')
        _metric(*retained, phase='compact.share_keys.retained')
        if (retained[0] + cls.FIXED_BYTES > MAX_EXPANDED_BYTES or
                retained[1] + cls.FIXED_NODES > MAX_EXPANDED_NODES):
            return None
        value_floor = _share_literal_input_floor(value, work)
        encoded_floor = _share_literal_input_floor(encoded, work)
        if value_floor is None or encoded_floor is None:
            return None
        # Neither locally produced graph is claimed to be inside owner_live.
        # Conservatively add both complete logical floors, even shared scalars.
        base = (retained[0] + value_floor[0] + encoded_floor[0],
                retained[1] + value_floor[1] + encoded_floor[1], retained[2])
        if (base[0] + cls.FIXED_BYTES > MAX_EXPANDED_BYTES or
                base[1] + cls.FIXED_NODES > MAX_EXPANDED_NODES):
            return None
        _metric(base[0] + cls.FIXED_BYTES, base[1] + cls.FIXED_NODES,
                max(base[2], 4), phase='compact.share_keys.fixed')
        instance = object.__new__(cls)
        instance.base, instance.input_floor = base, (value_floor, encoded_floor)
        return instance

    def __init__(self, work, value, encoded, counts, by_id):
        self.work, self.counts, self.by_id = work, counts, by_id
        self.order = []
        self.size, self.nodes = self.FIXED_BYTES, self.FIXED_NODES
        self.pending_size, self.pending_nodes = 0, 0
        self.peak_size, self.peak_nodes = self.size, self.nodes
        self.peak_pending_size, self.peak_pending_nodes = 0, 0
        self.builds = self.memo_hits = self.equal_hits = self.key_chars = 0
        self.capacity_misses, self.fallback, self.closed = 0, False, False
        self.enabled = True
        self.capacity_error = _ShareKeyCapacity('share literal cache headroom')

    def _room(self, size, nodes):
        self.work.spend(32)  # All arithmetic, fields, branches and metric call.
        total_size = self.size + self.pending_size + size
        total_nodes = self.nodes + self.pending_nodes + nodes
        if (self.base[0] + total_size > MAX_EXPANDED_BYTES or
                self.base[1] + total_nodes > MAX_EXPANDED_NODES):
            self.capacity_misses += 1
            raise self.capacity_error
        _metric(self.base[0] + total_size, self.base[1] + total_nodes,
                max(self.base[2], 4), phase='compact.share_keys.coexist')
        self.peak_size = max(self.peak_size, total_size)
        self.peak_nodes = max(self.peak_nodes, total_nodes)
        self.peak_pending_size = max(self.peak_pending_size, self.pending_size + size)
        self.peak_pending_nodes = max(self.peak_pending_nodes, self.pending_nodes + nodes)

    def _reserve(self, size, nodes):
        self._room(size, nodes)
        self.pending_size += size
        self.pending_nodes += nodes

    def _release(self, size, nodes):
        # All releases and their integer/attribute operations were prepaid.
        self.pending_size -= size
        self.pending_nodes -= nodes

    def _atom(self, parts, value):
        work = self.work
        work.spend(32)  # Bound, tag/length, appends, repr release and cleanup.
        kind = type(value)
        tag = (0 if kind is str else 1 if value is None else 2 if kind is bool
               else 3 if kind is int else 4 if kind is float and math.isfinite(value) else None)
        if tag is None:
            raise ValueError('Only exact legacy scalar types are supported')
        # Same prepaid scan and size rule as _repr, before allocating repr.
        bound = _repr_size(value, work)
        if kind is str:
            # Two actual count scans/calls, quote choice and length arithmetic.
            work.spend(2 * len(value) + 12)
            double_quotes = value.count('"')
            single_quotes = value.count("'")
            work.spend(bound)  # Preserve the complete original repr-size charge.
            length = bound - (double_quotes if double_quotes else single_quotes)
            parts.extend((tag, value))
            return length
        reserved = 6 * bound + 128
        self._reserve(reserved, 2)
        text = None
        try:
            work.spend(bound)
            text = repr(value)
            if 6 * len(text) + 128 > reserved:
                raise ValueError('Legacy scalar representation exceeded share reservation')
            length = len(text)
            # Strong reference to the actual scalar already included in both
            # original input floors. Never retain a copied string repr.
            parts.extend((tag, value))
            return length
        finally:
            text = None
            self._release(reserved, 2)

    def prepare(self, encoded):
        self.work.spend(12)
        if type(encoded) in (dict, list, tuple):
            self._build(encoded)

    def _build(self, node):
        work = self.work
        work.spend(36)  # Original frame work plus added cleanup-credit bookkeeping.
        kind = type(node)
        identity = id(node)
        entry = self.by_id.get(identity)
        if entry is not None:
            self.memo_hits += 1
            return entry[0]
        count = len(node)
        slots = (4 * count) if kind is dict else (2 * count)
        # Keep the existing accounting unit, and reserve both mutable builder
        # slots and iterator/frame temporaries before allocating the list.
        frame_size, frame_nodes = 1024 + 64 * slots, 32 + 2 * slots
        self._reserve(frame_size, frame_nodes)
        key_size = key_nodes = 0
        metadata_size = metadata_nodes = 0
        parts = key = child_key = None
        try:
            work.spend(16 + 4 * count)
            parts = []
            characters = 2 + max(0, count - 1) + (1 if kind is tuple and count == 1 else 0)
            for item in node.items() if kind is dict else node:
                work.spend(16)
                if kind is dict:
                    name, child = item
                    characters += self._atom(parts, name) + 1
                else:
                    child = item
                if type(child) in (dict, list, tuple):
                    child_key = self._build(child)
                    work.spend(8)
                    parts.extend((5, child_key))
                    characters += len(child_key)
                    child_key = None
                else:
                    characters += self._atom(parts, child)
            # Wrapper fields, frozen tuple slots and cached hash are charged
            # locally; old 384/6 record and 256/4 id-row units stay unchanged.
            desired_size, desired_nodes = 512 + 32 * slots, 16 + slots
            self._reserve(desired_size, desired_nodes)
            # Publish cleanup credit only after this reservation succeeds.
            key_size, key_nodes = desired_size, desired_nodes
            key = _ShareStructuralKey(0 if kind is dict else 1 if kind is list else 2,
                                      parts, characters, self)
            work.spend(24)
            entry = self.counts.get(key)
            if entry is None:
                # Insert performs another real hash/collision comparison.
                # Its frame must coexist with the already-created new entry.
                self._reserve(384, 6)
                metadata_size, metadata_nodes = 384, 6
                work.spend(24)  # Original entry work plus metadata-credit transfer.
                entry = [key, 0]
                self.counts[key] = entry
                self.size += key_size + metadata_size
                self.nodes += key_nodes + metadata_nodes
                self.key_chars += characters
                self._release(key_size + metadata_size, key_nodes + metadata_nodes)
                key_size = key_nodes = metadata_size = metadata_nodes = 0
            else:
                self.equal_hits += 1
            self._room(256, 4)
            work.spend(16)
            self.by_id[identity] = entry
            self.size += 256
            self.nodes += 4
            self.builds += 1
            return entry[0]
        finally:
            if parts is not None:
                parts.clear()
            key = child_key = entry = None
            self._release(frame_size + key_size + metadata_size,
                          frame_nodes + key_nodes + metadata_nodes)

    def abandon(self, error):
        # Only the owner's capacity sentinel reaches here. Never retry a
        # work/MemoryError refusal, and never transfer structural keys to the
        # legacy literal pass, even after a complete counts-only publication.
        self.work.spend(16)
        error.__traceback__ = error.__context__ = error.__cause__ = None
        self.fallback = True
        self.order.clear()
        self.by_id.clear()
        self.counts.clear()
        self.size, self.nodes = self.FIXED_BYTES, self.FIXED_NODES
        self.pending_size = self.pending_nodes = 0

    def close(self):
        self.counts.clear()
        self.by_id.clear()
        self.order.clear()
        self.size, self.nodes = self.FIXED_BYTES, self.FIXED_NODES
        self.pending_size = self.pending_nodes = 0
        self.closed = True



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
    work.spend(3 * len(strings))  # Existing map plus each real immutable marker.
    indices = {string: (None, index) for index, string in enumerate(strings)}
    def encode_strings(node):
        work.spend(2)  # Exact type dispatch and miss branch.
        if type(node) is str:
            work.spend(len(node) + 4)  # One actual lookup/string comparison.
            marker = indices.get(node)
            if marker is not None:
                return marker
        return _children(node, encode_strings, work)
    encoded = encode_strings(value)
    work.spend(6)  # Local maps, fixed setup and their eventual clear calls.
    counts, by_id = {}, {}
    cache, entries, cached_entries = None, None, False
    try:
        work.spend(8)  # Owner-context gate and optional helper lifecycle.
        if getattr(work, '_residual_retained', None) is not None:
            cache = _ShareLiteralKeys(work, value, encoded, counts, by_id)
        if cache is not None:
            try:
                cache.prepare(encoded)
            except _ShareKeyCapacity as error:
                if error is not cache.capacity_error:
                    raise
                cache.abandon(error)
        def count_container(node):
            if type(node) in (dict, list, tuple):
                # First-pass character rendering and hash/equality weight stay
                # original. Equal temporary keys retain only the FIRST key.
                work.spend(4)  # Legacy branch and its entry local.
                entry = None

                if entry is None:
                    key = _literal(node, work)
                    work.spend(2 * len(key) + 1)
                work.spend(16)  # Entry/count/id operations and id cleanup credit.
                if entry is None:
                    entry = counts.get(key)
                if entry is None:
                    work.spend(6)  # Two-slot entry allocation and cleanup credit.
                    entry = [key, 0]
                    counts[key] = entry
                entry[1] += 1
                by_id[id(node)] = entry
        if cache is not None and not cache.fallback:
            def count_cached(node):
                if type(node) in (dict, list, tuple):
                    work.spend(16)  # Original count/id operations, no character key.
                    entry = by_id[id(node)]
                    if entry[1] == 0:
                        work.spend(8)  # First-preorder order slot, prepaid room.
                        cache.order.append(entry)
                    entry[1] += 1
            _walk(encoded, count_cached, work)
            work.spend(16)  # Selection generator and its guaranteed final close.
            entries = ((entry[0], entry) for entry in cache.order)
            cached_entries = True
        else:
            _walk(encoded, count_container, work)
            work.spend(4)  # Original dictionary view setup.
            entries = counts.items()
        work.spend(len(counts))
        for key, entry in entries:
            work.spend(8)  # Original count/threshold plus one in-place state write.
            count = entry[1]
            # Counting is complete. Every equal canonical key already shares
            # this exact FIRST two-slot entry through by_id, including nodes
            # with different identities. Reuse the old count slot: None means
            # unselected, -1 selected/unemitted, >=0 its postorder definition.
            entry[1] = (-1 if count >= 2 and len(key) >= 24 and
                (count - 1) * len(key) > count * len(_literal((False, len(counts)), work)) + 1 else None)
        work.spend(4)  # Definition-list setup; no selected/identities maps exist.
        definitions = []
        def encode_shared(node):
            if type(node) in (dict, list, tuple):
                work.spend(12)  # Exact live id/entry/state, branch and reference.
                entry = by_id[id(node)]
                index = entry[1]
                if index is not None:
                    if index < 0:
                        definition = _children(node, encode_shared, work)
                        work.spend(8)  # Index read, shared slot write and append.
                        index = len(definitions)
                        entry[1] = index
                        definitions.append(definition)
                    return (False, index)
            return _children(node, encode_shared, work)
        return strings, definitions, encode_shared(encoded)
    finally:
        # Encoded stays strongly rooted and unchanged throughout both passes.
        # Repeated parents can skip children; retained ids need no pop/refcount.
        # Cleanup was prepaid and must never mask a primary refusal by spending.
        if cached_entries and entries is not None:
            entries.close()
        if cache is not None:
            cache.close()
        by_id.clear()
        counts.clear()


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
    if schema in (ATOM_SCHEMA, RESIDUAL_SCHEMA):
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
    # One prepaid character classification replaces the UTF-8 scan, discarded
    # byte copy and independent JSON-escape scan. Other _utf8_size uses stay.
    work.spend(len(text))
    encoded_size = 2
    for char in text:
        code = ord(char)
        if code < 32:
            width = 2 if code in (8, 9, 10, 12, 13) else 6
        elif code in (34, 92):
            width = 2
        elif code < 128:
            width = 1
        elif code < 2048:
            width = 2
        elif 0xD800 <= code <= 0xDFFF:
            raise ValueError("JSON data must be encodable as strict UTF-8")
        elif code < 65536:
            width = 3
        else:
            width = 4
        encoded_size += width
    work.spend(2)  # Retain the original fixed quoted-string framing charge.
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
        if schema in (CURRENT_SCHEMA, ATOM_SCHEMA, RESIDUAL_SCHEMA):
            tables = [keys for keys in tables if keys]
        work.spend(sum(len(keys) + 1 for keys in tables))
        indices = {tuple(keys): index for index, keys in enumerate(tables)}
        packed = _pack(aliased, indices, schema, work)
        if schema in (CURRENT_SCHEMA, ATOM_SCHEMA, RESIDUAL_SCHEMA):
            strings, definitions, packed = _share(packed, work)
            if schema in (ATOM_SCHEMA, RESIDUAL_SCHEMA):
                phrases, encoded = _pack_text([strings, definitions, packed], work, schema=schema)
                strings, definitions, packed = encoded
                return _bounded_packet(_atom_literal({"schema_version": schema, "keysets": tables,
                    "strings": strings, "shared": definitions, "phrases": phrases,
                    "value": packed, "sha256": _digest(value, work)}, work), schema, work)
            render = _atom_literal if schema in (ATOM_SCHEMA, RESIDUAL_SCHEMA) else _literal
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
    if type(node) is ast.Name and schema in (ATOM_SCHEMA, RESIDUAL_SCHEMA):
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
    if type(node) is ast.Tuple and schema in (CURRENT_SCHEMA, ATOM_SCHEMA, RESIDUAL_SCHEMA):
        if (schema in (ATOM_SCHEMA, RESIDUAL_SCHEMA) and node.elts and type(node.elts[0]) is ast.Name
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
        if schema in (CURRENT_SCHEMA, ATOM_SCHEMA, RESIDUAL_SCHEMA) and type(value) is tuple and len(value) == 1:
            return {"$mvg_ref": _restore(value[0], tables, used, schema)}
        if type(value) is tuple or "@" in value:
            if schema in (CURRENT_SCHEMA, ATOM_SCHEMA, RESIDUAL_SCHEMA):
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


def _decode_complete(text, work, *, retained=None):
    """Full primitive decoder gates, without claiming canonical spelling."""
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
    fields = _FIELDS if schema == SCHEMA else _ATOM_FIELDS if schema in (ATOM_SCHEMA, RESIDUAL_SCHEMA) else _CURRENT_FIELDS
    if type(packet) is not dict or set(packet) != fields:
        raise ValueError("Unknown or missing packet fields")
    if packet["schema_version"] != schema:
        raise ValueError("Unsupported compact literal schema")
    tables = packet["keysets"]
    if type(tables) is not list:
        raise ValueError("Keysets must be a list")
    seen = set()
    for keys in tables:
        if (type(keys) is not list or (schema in (CURRENT_SCHEMA, ATOM_SCHEMA, RESIDUAL_SCHEMA) and not keys) or any(type(key) is not str for key in keys)
                or len(set(keys)) != len(keys) or tuple(keys) in seen):
            raise ValueError("Invalid or duplicate keyset")
        for key in keys:
            _unalias(key)
        seen.add(tuple(keys))
    expanded = _expanded_preflight(packet, schema, work)
    if retained is not None:
        if (type(retained) is not tuple or len(retained) != 3
                or any(type(part) is not int or part < 0 for part in retained)):
            raise ValueError("Invalid retained snapshot metric")
        _metric(expanded[0] + retained[0], expanded[1] + retained[1], max(expanded[2], retained[2]),
                phase="atomic.restore.retained_cache")
    used = set()
    if schema in (ATOM_SCHEMA, RESIDUAL_SCHEMA):
        packet["strings"], packet["shared"], packet["value"] = _unpack_text(
            [packet["strings"], packet["shared"], packet["value"]], packet["phrases"])
    if schema in (CURRENT_SCHEMA, ATOM_SCHEMA, RESIDUAL_SCHEMA):
        packet["value"] = _unshare(packet["value"], packet["strings"], packet["shared"])
    restored = _restore(packet["value"], tables, used, schema)
    if type(restored) is not dict or len(used) != len(tables):
        raise ValueError("Expected an object and complete keyset usage")
    if type(packet["sha256"]) is not str or packet["sha256"] != _digest(restored, work):
        raise ValueError("Original JSON digest mismatch")
    return restored, schema


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
        restored, schema = _decode_complete(text, work)
        if dumps(restored, schema=schema, work=work) != text:
            raise ValueError("Noncanonical compact literal packet")
        return restored
    except (SyntaxError, RecursionError, UnicodeError) as exc:
        raise ValueError("Invalid data literal or runtime nesting limit") from exc


# Bound once to the genuine installed producer. The atomic API never accepts a
# caller-supplied body, approval flag, producer or transferable witness.
_ATOMIC_PRODUCER = dumps


def produce_canonical_roundtrip(value, schema=None, *, work=None):
    """Produce and restore one private JSON snapshot in the same work account.

    Canonical equivalence is local: body=E(snapshot), and exact JSON equality
    proves restored=snapshot, so E(restored)=body without a second E. Cold loads
    still performs its complete canonical re-encoding for every untrusted text.
    """
    schema = _schema(schema)
    work = _work(work)
    if type(value) is not dict:
        raise ValueError("The top-level value must be an object")
    try:
        metric = _json_preflight(value, work)
        # Caller value + private snapshot + immutable ordered JSON witness.
        retained = (2 * metric[0] + metric[5], 2 * metric[1] + 1, metric[2])
        _metric(*retained, phase="atomic.snapshot.retained_cache")
        work.spend(metric[5], phase="atomic.snapshot.serialization")
        original = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        _syntax_preflight(original, work, json_only=True)
        work.spend(metric[0] + metric[1], phase="atomic.snapshot.private_copy")
        snapshot = json.loads(original)
        body = _ATOMIC_PRODUCER(snapshot, schema=schema, work=work)
        if type(body) is not str:
            raise ValueError("Canonical producer did not complete a literal")
        work.phase = "compact.decode"
        restored, actual_schema = _decode_complete(body, work, retained=retained)
        if actual_schema != schema:
            raise ValueError("Atomic producer schema changed")
        def exact(current, prior_json=0):
            measured = _json_preflight(current, work)
            _metric(retained[0] + measured[0] + measured[5] + prior_json, retained[1] + measured[1] + 2,
                    max(retained[2], measured[2]), phase="atomic.roundtrip.retained_cache")
            work.spend(measured[5], phase="atomic.roundtrip.serialization")
            return json.dumps(current, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        restored_text = exact(restored)
        work.spend(len(original) + len(restored_text), phase="atomic.roundtrip.compare")
        if restored_text != original:
            raise ValueError("Atomic snapshot/input ordered JSON changed")
        current_text = exact(value, metric[5])
        work.spend(len(original) + len(current_text), phase="atomic.roundtrip.compare")
        if current_text != original:
            raise ValueError("Atomic snapshot/input ordered JSON changed")
        return body, restored
    except (SyntaxError, RecursionError, UnicodeError) as exc:
        raise ValueError("Invalid data literal or runtime nesting limit") from exc
