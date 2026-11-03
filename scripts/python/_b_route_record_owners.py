"""Read-only external locator adapters for the shared B-route record service.

These adapters establish locator and raw-file relationships only. They never
interpret review outcomes, runtime status, or a source owner's completion rules.
"""
from __future__ import annotations

import posixpath
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from _b_route_codec import (
    CodecError,
    Diagnostic,
    ReasonCode,
    Stage,
    raw_digest,
    strict_json_loads,
    validate_reference_path,
)
from _chapter5_contract_bindings import resolve_contract


OWNERS = frozenset({
    "source_manifest", "source_ledger", "planning_proof", "manifest", "contract",
    "overlay", "adr", "authority", "other_verification", "frozen_a_inventory",
    "implementation_reference", "verification_record", "runtime_acceptance",
})


def _error(code: ReasonCode, ref: Any, expected: Any, actual: Any) -> None:
    raise CodecError(Diagnostic(code, Stage.REFERENCE,
                               expected={"ref": ref, "value": expected},
                               actual={"ref": ref, "value": actual}))


def _path(value: Any) -> str:
    return posixpath.normpath(validate_reference_path(value))


def _text(data: bytes, ref: str) -> str:
    try:
        return data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _error(ReasonCode.INVALID_UTF8, ref, "UTF-8 locator source", "invalid byte sequence")


def _json_pointer(data: bytes, fragment: str, ref: str) -> None:
    value = strict_json_loads(data)
    for part in fragment[1:].split("/"):
        if re.search(r"~(?![01])", part):
            _error(ReasonCode.INVALID_REFERENCE, ref, "RFC 6901 escape", "invalid escape")
        token = part.replace("~1", "/").replace("~0", "~")
        if type(value) is dict and token in value:
            value = value[token]
        elif (type(value) is list and re.fullmatch(r"0|[1-9][0-9]*", token)
              and len(token) <= len(str(len(value))) and int(token) < len(value)):
            value = value[int(token)]
        else:
            _error(ReasonCode.UNRESOLVED_REFERENCE, ref, "existing JSON Pointer target", token)


def _native_record(data: bytes, fragment: str, ref: str) -> None:
    """Use the native evidence_id locator without enforcing PASS semantics."""
    text = _text(data, ref).removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    fenced = re.findall(r"```json\s*\n(.*?)\n```", text, re.S)
    records: list[Any] = []
    for index, payload in enumerate([text, *fenced]):
        try:
            value = strict_json_loads(payload)
        except CodecError as error:
            # The complete document may be Markdown; fenced JSON stays strict.
            if index == 0 and error.diagnostic.reason_code == ReasonCode.INVALID_JSON:
                continue
            raise
        if type(value) is dict:
            candidates = value.get("records", [value])
            if type(candidates) is list:
                records.extend(item for item in candidates if type(item) is dict)
    if not any(not fragment or record.get("evidence_id") == fragment for record in records):
        _error(ReasonCode.UNRESOLVED_REFERENCE, ref, "native evidence record", fragment or "no records")


def _file_locator(owner: str, ref: str, read_bytes: Callable[[str], bytes]) -> dict[str, bytes]:
    source, separator, fragment = ref.partition("#")
    path = validate_reference_path(source)
    data = read_bytes(path)
    if type(data) is not bytes:
        _error(ReasonCode.INVALID_TYPE, ref, "source bytes", type(data).__name__)
    if owner == "verification_record":
        _native_record(data, fragment, ref)
    elif separator:
        if fragment.startswith("/"):
            _json_pointer(data, fragment, ref)
        else:
            lines = re.fullmatch(r"L([1-9][0-9]*)(?:-L([1-9][0-9]*))?", fragment)
            if lines is None:
                _error(ReasonCode.UNSUPPORTED_LOCATOR, ref, "JSON Pointer or line range", fragment)
            count = len(_text(data, ref).splitlines())
            if any(len(part) > len(str(count)) for part in lines.groups() if part is not None):
                _error(ReasonCode.UNRESOLVED_REFERENCE, ref, "existing ordered line range", fragment)
            first = int(lines.group(1))
            last = int(lines.group(2) or lines.group(1))
            if first > last or last > count:
                _error(ReasonCode.UNRESOLVED_REFERENCE, ref, "existing ordered line range", fragment)
    return {path: data}


def resolve_owned_ref(
    value: dict,
    *,
    read_bytes: Callable[[str], bytes],
    contract_sources: Callable[[], Mapping[str, bytes]],
    path_key: Callable[[str], str] | None = None,
) -> dict[str, bytes]:
    """Resolve a fixed owner and require the exact declared raw-file collection.

    read_bytes and contract_sources must use the service's shared safe byte cache;
    this module has no independent disk-reading fallback.
    """
    if type(value) is not dict or set(value) != {"owner", "ref", "files"}:
        _error(ReasonCode.INVALID_REFERENCE, None, "complete OwnedRef fields", "missing or unknown fields")
    owner, ref = value["owner"], value["ref"]
    if type(owner) is not str or owner not in OWNERS:
        _error(ReasonCode.INVALID_REFERENCE, ref, "registered external owner", owner)
    if type(ref) is not str or not ref.strip():
        _error(ReasonCode.INVALID_TYPE, ref, "nonempty locator string", type(ref).__name__)
    key = path_key if path_key is not None else _path
    declared: dict[str, str] = {}
    if type(value["files"]) is not list or not value["files"]:
        _error(ReasonCode.INVALID_REFERENCE, ref, "nonempty raw-file collection", "missing files")
    for row in value["files"]:
        if type(row) is not dict or set(row) != {"path", "raw_digest"}:
            _error(ReasonCode.INVALID_REFERENCE, ref, "complete raw-file fields", "missing or unknown fields")
        path = key(validate_reference_path(row["path"]))
        digest = row["raw_digest"]
        if type(digest) is not str or re.fullmatch(r"sha256:[0-9a-f]{64}", digest) is None:
            _error(ReasonCode.INVALID_DIGEST, ref, "sha256:<64 lowercase hex digits>", digest)
        if path in declared:
            _error(ReasonCode.INVALID_REFERENCE, ref, "unique resolved file paths", path)
        declared[path] = digest
    if owner == "contract":
        if "#" in ref:
            _error(ReasonCode.UNSUPPORTED_LOCATOR, ref, "native contract symbol or file", "fragment")
        sources = contract_sources()
        if not isinstance(sources, Mapping):
            _error(ReasonCode.INVALID_TYPE, ref, "contract byte mapping", type(sources).__name__)
        checked: dict[str, bytes] = {}
        for source, data in sources.items():
            path = _path(source)
            if not path.startswith("Game.Core/Contracts/") or not path.endswith(".cs"):
                _error(ReasonCode.INVALID_REFERENCE, ref, "contract C# source path", path)
            if path in checked:
                _error(ReasonCode.INVALID_REFERENCE, ref, "unique contract source paths", path)
            if type(data) is not bytes:
                _error(ReasonCode.INVALID_TYPE, ref, "contract source bytes", type(data).__name__)
            _text(data, ref)
            checked[path] = data
        try:
            resolver_ref = ref
            if posixpath.normpath(ref).startswith("Game.Core/Contracts/"):
                resolver_ref = _path(ref)
            binding = resolve_contract(Path("."), resolver_ref, sources=checked)
        except UnicodeDecodeError:
            _error(ReasonCode.INVALID_UTF8, ref, "UTF-8 contract source", "invalid byte sequence")
        if binding is None:
            _error(ReasonCode.UNRESOLVED_REFERENCE, ref, "native contract declaration", "no matching declaration")
        actual = {row["path"]: checked[row["path"]] for row in binding["bindings"]}
    else:
        actual = _file_locator(owner, ref, read_bytes)
    actual_by_key: dict[str, bytes] = {}
    for path, data in actual.items():
        address = key(path)
        if address in actual_by_key:
            _error(ReasonCode.INVALID_REFERENCE, ref, "unique resolved file paths", address)
        actual_by_key[address] = data
    if set(declared) != set(actual_by_key):
        _error(ReasonCode.INVALID_REFERENCE, ref, {"files": sorted(actual_by_key)}, {"files": sorted(declared)})
    for path, data in actual_by_key.items():
        digest = raw_digest(data)
        if declared[path] != digest:
            _error(ReasonCode.DIGEST_MISMATCH, ref,
                   {"path": path, "raw_digest": declared[path]},
                   {"path": path, "raw_digest": digest})
    return actual
