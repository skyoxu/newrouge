"""One-comparison v4 liability storage, never native proof or dispatch permission.

The caller verifies original manifests, current external authority and complete
input membership before using these local integrity records. This module does
not prove native audit success, provider identity, billing, remote termination or
permission to dispatch. It never touches a parent v3 file or refunds an unknown.
The caller supplies an exclusively owned, stable directory topology; path checks
do not authenticate the directory owner against hostile concurrent replacement.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Any
import uuid


SCHEMA = "newrouge.b-route-recovery-funding.v4"
_SHA = re.compile(r"sha256:[0-9a-f]{64}\Z")
_UUID = re.compile(r"[0-9a-f]{32}\Z")
_NAMES = frozenset({"intent.json", "claim.json", "state.json", "settlement.json"})
_INPUTS = frozenset({"old_permit", "old_request", "old_protocol", "extraction",
                     "source", "current_identity", "code_freeze"})
_BUDGET = {"old_liabilities": 54, "retained_guard": 240, "campaign_limit": 290,
           "parent_pool": 192, "outside_headroom": 50, "comparison_calls": 1,
           "comparison_seconds": 330, "capability_ceiling": 96, "mvg_ceiling": 192,
           "refunds_allowed": False}


class FundingError(ValueError):
    """A stale, malformed, partial, unsafe or already-consumed funding record."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise FundingError(message)


def _keys(value: Any, keys: set[str] | frozenset[str]) -> None:
    _require(type(value) is dict and set(value) == set(keys), "Closed object shape required")


def _strict(value: Any) -> None:
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        _require(math.isfinite(value), "Finite JSON number required")
        return
    if type(value) is list:
        for item in value:
            _strict(item)
        return
    if type(value) is dict:
        _require(all(type(key) is str for key in value), "String JSON keys required")
        for item in value.values():
            _strict(item)
        return
    raise FundingError("Strict JSON value required")


def _encode(value: Any) -> bytes:
    try:
        _strict(value)
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                          allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise FundingError("Strict canonical UTF-8 JSON required") from error


def raw_digest(raw: bytes) -> str:
    _require(type(raw) is bytes, "Exact raw bytes required")
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def digest(value: Any) -> str:
    """Identity of the complete strict JSON value; not authentication."""
    return raw_digest(_encode(value))


def _parse(raw: bytes) -> Any:
    def pairs(items):
        value = {}
        for key, item in items:
            _require(key not in value, "Duplicate JSON key")
            value[key] = item
        return value

    def constant(value):
        raise FundingError("Non-finite JSON constant")

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
        _strict(value)
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError) as error:
        raise FundingError("Strict UTF-8 JSON required") from error


def _sha(value: Any) -> None:
    _require(type(value) is str and _SHA.fullmatch(value) is not None, "SHA-256 digest required")


def _safe_component(value: str) -> None:
    _require(bool(value) and value not in (".", "..") and value[-1] not in (".", " "),
             "Unsafe path name")
    _require(not any(ord(c) < 32 or c in '<>:"|?*' for c in value), "Unsafe path name")
    stem = value.split(".", 1)[0].upper()
    _require(stem not in {"CON", "PRN", "AUX", "NUL"}
             and re.fullmatch(r"(?:COM|LPT)[1-9]", stem) is None, "Reserved path name")


def _no_reparse(path: Path, *, directory: bool) -> os.stat_result:
    record = path.lstat()
    _require(not stat.S_ISLNK(record.st_mode) and not (getattr(record, "st_file_attributes", 0) & 0x400),
             "Reparse points and symlinks are forbidden")
    _require(stat.S_ISDIR(record.st_mode) if directory else stat.S_ISREG(record.st_mode),
             "Unexpected filesystem type")
    if not directory:
        _require(record.st_nlink == 1, "Hardlinked records are forbidden")
    return record


def _namespace(value: str | Path, *, create: bool = False) -> Path:
    raw = os.fspath(value)
    _require(type(raw) is str and bool(raw) and "\x00" not in raw, "Namespace path required")
    _require(not raw.startswith(("\\\\", "//")), "UNC and device paths are forbidden")
    original = Path(raw)
    for part in original.parts:
        if part != original.anchor:
            _safe_component(part)
    path = Path(os.path.abspath(raw))
    _require(path != Path(path.anchor), "Filesystem root is not a namespace")
    chain = list(reversed(path.parents)) + [path]
    for current in chain:
        if current == path and create and not current.exists():
            current.mkdir()
        _no_reparse(current, directory=True)
    _safe_component(path.name)
    return path


def _inventory(path: Path) -> set[str]:
    names = set()
    for child in path.iterdir():
        _require(child.name in _NAMES, "Unknown or partial namespace artifact")
        _no_reparse(child, directory=False)
        names.add(child.name)
    return names


def _read(path: Path) -> tuple[dict[str, Any], bytes]:
    before = _no_reparse(path, directory=False)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        actual = os.fstat(descriptor)
        _require(stat.S_ISREG(actual.st_mode) and actual.st_nlink == 1
                 and (actual.st_dev, actual.st_ino) == (before.st_dev, before.st_ino),
                 "Record identity changed during open")
        chunks = []
        while True:
            chunk = os.read(descriptor, 65536)
            if not chunk:
                break
            chunks.append(chunk)
        raw = b"".join(chunks)
    finally:
        os.close(descriptor)
    value = _parse(raw)
    _require(type(value) is dict and _encode(value) == raw, "Canonical record bytes required")
    return value, raw


def _write_exclusive(path: Path, value: dict[str, Any]) -> None:
    _no_reparse(path.parent, directory=True)
    raw = _encode(value)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    try:
        descriptor = os.open(path, flags, 0o666)
    except FileExistsError as error:
        raise FundingError("Permanent record already exists") from error
    try:
        record = os.fstat(descriptor)
        _require(stat.S_ISREG(record.st_mode) and record.st_nlink == 1, "Unsafe new record")
        remaining = memoryview(raw)
        while remaining:
            count = os.write(descriptor, remaining)
            _require(count > 0, "Incomplete durable record write")
            remaining = remaining[count:]
        os.fsync(descriptor)
    finally:
        # A partial file is an unknown consumed record, never removed or repaired.
        os.close(descriptor)


def _atomic_state(path: Path, value: dict[str, Any]) -> None:
    if path.exists():
        _no_reparse(path, directory=False)
    temporary = path.with_name(".state-" + uuid.uuid4().hex + ".tmp")
    _write_exclusive(temporary, value)
    if path.exists():
        _no_reparse(path, directory=False)
    os.replace(temporary, path)
    # The temporary file was fsynced before replace. Failed replacements retain
    # that artifact; later reads fail closed instead of silently cleaning it up.


def _reference(value: Any) -> None:
    _keys(value, {"ref", "sha256"})
    _sha(value["sha256"])
    ref = value["ref"]
    _require(type(ref) is str and bool(ref) and "\\" not in ref and not ref.startswith("/"),
             "Canonical relative reference required")
    for part in ref.split("/"):
        _safe_component(part)


def _inputs(value: Any) -> None:
    _keys(value, _INPUTS)
    for name in ("old_permit", "old_request", "old_protocol"):
        _reference(value[name])
    for name in ("extraction", "source", "current_identity", "code_freeze"):
        _require(type(value[name]) is dict and bool(value[name]), "Complete input object required")
    _encode(value)


def _intent(value: Any, parent_raw: bytes) -> None:
    _keys(value, {"schema_version", "budget", "parent_v3_sha256", "inputs", "input_digest", "intent_id"})
    _require(value["schema_version"] == SCHEMA + ".intent" and digest(value["budget"]) == digest(_BUDGET),
             "Fixed v4 funding contract required")
    _require(value["parent_v3_sha256"] == raw_digest(parent_raw), "Parent v3 raw digest changed")
    _inputs(value["inputs"])
    _require(value["input_digest"] == digest(value["inputs"]), "Complete input digest changed")
    body = {key: item for key, item in value.items() if key != "intent_id"}
    _require(value["intent_id"] == digest(body), "Intent identity changed")


def _claim(value: Any, intent: dict[str, Any]) -> None:
    _keys(value, {"schema_version", "intent_id", "parent_v3_sha256", "claim_id",
                  "ordinal", "logical_calls", "reserved_seconds"})
    _require(value["schema_version"] == SCHEMA + ".claim"
             and value["intent_id"] == intent["intent_id"]
             and value["parent_v3_sha256"] == intent["parent_v3_sha256"], "Original claim binding required")
    _require(type(value["claim_id"]) is str and _UUID.fullmatch(value["claim_id"]) is not None,
             "Original claim token required")
    for key, expected in (("ordinal", 1), ("logical_calls", 1), ("reserved_seconds", 330)):
        _require(type(value[key]) is int and value[key] == expected, "Fixed one-call permit required")


def _state(claim: dict[str, Any], *, settled: bool, outcome: str,
           evidence: dict[str, Any] | None) -> dict[str, Any]:
    return {"schema_version": SCHEMA + ".state", "intent_id": claim["intent_id"],
            "claim_digest": digest(claim), "settled": settled, "outcome": outcome,
            "logical_charged_or_unknown": 1, "released": 0, "evidence": deepcopy(evidence)}


def prepare(namespace: str | Path, *, parent_v3_raw: bytes,
            inputs: dict[str, Any]) -> dict[str, Any]:
    """Persist the complete immutable intent; this does not authorize dispatch."""
    _require(type(parent_v3_raw) is bytes and bool(parent_v3_raw), "Original parent bytes required")
    _inputs(inputs)
    body = {"schema_version": SCHEMA + ".intent", "budget": deepcopy(_BUDGET),
            "parent_v3_sha256": raw_digest(parent_v3_raw), "inputs": deepcopy(inputs),
            "input_digest": digest(inputs)}
    value = {**body, "intent_id": digest(body)}
    path = _namespace(namespace, create=True)
    names = _inventory(path)
    if "intent.json" in names:
        snapshot = inspect(path, parent_v3_raw=parent_v3_raw)
        _require(snapshot["intent"] == value, "Existing immutable intent differs")
        return deepcopy(value)
    _require(not names, "Orphan funding artifacts must be preserved")
    _write_exclusive(path / "intent.json", value)
    return deepcopy(value)


def inspect(namespace: str | Path, *, parent_v3_raw: bytes) -> dict[str, Any]:
    """Read and validate only. Partial files are never classified as unspent."""
    path = _namespace(namespace)
    names = _inventory(path)
    _require("intent.json" in names, "Missing immutable intent")
    intent, _ = _read(path / "intent.json")
    _intent(intent, parent_v3_raw)
    if "claim.json" not in names:
        _require(names == {"intent.json"}, "Orphan state or settlement")
        return {"intent": intent, "claim": None, "state": None, "status": "prepared",
                "logical_charged_or_unknown": 0, "released": 0}
    claim, _ = _read(path / "claim.json")
    _claim(claim, intent)
    _require("state.json" in names, "Claim consumed; missing state remains unknown")
    state, _ = _read(path / "state.json")
    started = _state(claim, settled=False, outcome="unknown", evidence=None)
    if "settlement.json" not in names:
        _require(_encode(state) == _encode(started), "Unanchored or malformed funding state")
    else:
        settlement, _ = _read(path / "settlement.json")
        _keys(settlement, {"schema_version", "claim_digest", "state"})
        _require(settlement["schema_version"] == SCHEMA + ".settlement"
                 and settlement["claim_digest"] == digest(claim), "Original settlement binding required")
        terminal = settlement["state"]
        _keys(terminal, set(started))
        _require(terminal["outcome"] in ("success", "blocked", "unknown")
                 and type(terminal["evidence"]) is dict, "Terminal outcome and evidence required")
        expected = _state(claim, settled=True, outcome=terminal["outcome"], evidence=terminal["evidence"])
        _require(_encode(terminal) == _encode(expected) and _encode(state) == _encode(expected),
                 "Partial or conflicting settlement")
    return {"intent": intent, "claim": claim, "state": state,
            "status": "settled" if state["settled"] else "unknown",
            "logical_charged_or_unknown": 1, "released": 0}


def claim_comparison(namespace: str | Path, *, parent_v3_raw: bytes) -> dict[str, Any]:
    """Consume the sole permit durably before any caller dispatch action.

    An exception after exclusive creation consumes this permit permanently.
    Never retry by removing a file, changing IDs or interpreting partial state
    as an unused call. Only one concurrent caller can win O_EXCL claim creation.
    """
    path = _namespace(namespace)
    snapshot = inspect(path, parent_v3_raw=parent_v3_raw)
    _require(snapshot["claim"] is None, "Comparison permit permanently consumed")
    intent = snapshot["intent"]
    value = {"schema_version": SCHEMA + ".claim", "intent_id": intent["intent_id"],
             "parent_v3_sha256": intent["parent_v3_sha256"], "claim_id": uuid.uuid4().hex,
             "ordinal": 1, "logical_calls": 1, "reserved_seconds": 330}
    _write_exclusive(path / "claim.json", value)
    _atomic_state(path / "state.json", _state(value, settled=False, outcome="unknown", evidence=None))
    return deepcopy(value)


def settle_comparison(namespace: str | Path, *, parent_v3_raw: bytes,
                      claim: dict[str, Any], outcome: str,
                      evidence: dict[str, Any]) -> dict[str, Any]:
    """Record one caller-validated outcome; success is not native audit proof."""
    _require(type(outcome) is str and outcome in ("success", "blocked", "unknown"), "Known outcome required")
    _require(type(evidence) is dict, "Complete caller evidence object required")
    _encode(evidence)
    path = _namespace(namespace)
    snapshot = inspect(path, parent_v3_raw=parent_v3_raw)
    _require(snapshot["claim"] is not None and _encode(snapshot["claim"]) == _encode(claim),
             "Exact original claim required for settlement")
    _require(snapshot["state"]["settled"] is False, "Settlement is permanent")
    state = _state(claim, settled=True, outcome=outcome, evidence=evidence)
    settlement = {"schema_version": SCHEMA + ".settlement", "claim_digest": digest(claim), "state": state}
    _write_exclusive(path / "settlement.json", settlement)
    _atomic_state(path / "state.json", state)
    return deepcopy(state)


def mvg_funding(capability_calls: int, *, qualified: bool) -> dict[str, Any]:
    """Pure budget projection; caller proves true qualification separately.

    Full native ceilings stay Cap96/MVG192. After charging the comparison and
    preserving old54, a full new MVG requires topup7+k from the existing50.
    This arithmetic neither funds a file nor authorizes any dispatch or refund.
    """
    _require(type(qualified) is bool and qualified, "True original Cap qualification required")
    _require(type(capability_calls) is int and 0 <= capability_calls <= 96, "Cap charge must be 0..96")
    topup = 7 + capability_calls
    _require(topup <= 50, "Full MVG192 cannot fit retained campaign budget")
    return {"old_liabilities": 54, "comparison_charged_or_unknown": 1,
            "capability_calls": capability_calls, "capability_ceiling": 96,
            "mvg_ceiling": 192, "topup": topup, "guard": 240 + topup,
            "campaign_limit": 290, "released": 0}
