"""Governed Chapter 4 production contract and four-part binding refinement owner.

Refines committed 3B definitions and 3C/4 bindings into production commands
(preconditions/postconditions/invariants), read-only state and single state
owner, thin C# adapter dependencies/lifecycle, control-to-object/resource
bindings, scene entry/return, UI slice / human-owned zone boundaries, and test
obligations. Publishes immutable stage=4 bindings and updated task-origins via
the shared _b_route_commit protocol (catalog.v1.json last).

Explicit contract/overlay updates run only under writer_boundary through a
raw-byte base64 journal (public-sync-journal.json + public-sync.pending.json)
without ever feeding raw source/markdown files to JSON create_journal.
Never mutates old plans, never alters the conserved 3C/4 task_id set, never
drops other plans' references on shared Tasks, and never sets readiness,
runtime_verified, or default_b_enabled to true.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import base64
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from dataclasses import replace
import datetime as dt
from functools import wraps
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

import _b_route_codec as codec
import _b_route_commit as commit
import _b_route_commit_projection as projection
import _b_route_operation_scope as op_scope
import _b_route_protection as protection
import _b_route_records as records
import _b_route_task_compilation as task_compilation
import _b_route_task_resolver as task_resolver
import _planning_apply_journal as journal
import check_task_contract_refs
import validate_contracts
import validate_overlay_execution

_SC_DIR = Path(__file__).resolve().parents[1] / "sc"
if str(_SC_DIR) not in sys.path:
    sys.path.insert(0, str(_SC_DIR))
import _overlay_generator_markdown_patch as overlay_patch


REQUEST_SCHEMA = journal.CHAPTER4_BINDING_REQUEST
OPERATION_SCHEMA = journal.CHAPTER4_BINDING_SCHEMA
PRODUCER = "chapter4_binding"
PUBLIC_SYNC_SCHEMA = "newrouge.b-route-chapter4-public-sync.v1"
PUBLIC_SYNC_PENDING_SCHEMA = "newrouge.b-route-chapter4-public-sync.v1.pending"
STAGE4_SEMANTICS_SCHEMA = "newrouge.b-route-stage4-semantics.v1"
PREVIEW_SCHEMA = "newrouge.b-route-chapter4-binding-preview.v1"
EVENTS_BASE = "logs/ci/b-route-chapter4-binding"

FLAGS = {
    "readiness": False,
    "runtime_verified": False,
    "default_b_enabled": False,
}

TRIPLET = {
    "master": ".taskmaster/tasks/tasks.json",
    "back": ".taskmaster/tasks/tasks_back.json",
    "gameplay": ".taskmaster/tasks/tasks_gameplay.json",
}
TRIPLET_SCHEMAS = {
    ".taskmaster/tasks/tasks.json": "newrouge.taskmaster-master.v1",
    ".taskmaster/tasks/tasks_back.json": "newrouge.taskmaster-back.v1",
    ".taskmaster/tasks/tasks_gameplay.json": "newrouge.taskmaster-gameplay.v1",
}

PART_KINDS = ("domain_rules", "csharp_adapter", "binding", "scene")
REQUIRED_HUMAN_ZONES = ("layout", "art", "animation")
REQUIRED_LATER_CHECKS: dict[str, tuple[str, ...]] = {
    "command": ("type", "compile"),
    "read_only_state": ("type", "compile"),
    "adapter": ("type", "compile", "binding"),
    "binding": ("type", "compile", "binding"),
    "scene": ("binding", "engine"),
    "resource": ("type", "binding"),
}

STAGE4_LIFECYCLE_PREFIX = "stage4:v1|"
STAGE4_PART_PREFIX = "stage4:part:v1|"
STAGE4_UI_PREFIX = "stage4:ui:v1|"
STAGE4_OBL_PREFIX = "stage4:obl:v1|"

_FILE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_WIN_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
_OVERLAY_PATH_RE = re.compile(r"^docs/architecture/overlays/[A-Za-z0-9._-]+/08/[^/]+\.md$")
_CONST_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FAKE_NODE_RE = re.compile(r"(?:FAKE_NODE|PLACEHOLDER_NODE|TODO_FAKE_SCENE|DUMMY_NODE)", re.IGNORECASE)


def _checkpoint(name: str) -> None:
    """Fault-test seam only; no environment switch or production skip path."""


def _fail(
    code: codec.ReasonCode,
    expected: Any,
    actual: Any,
    *,
    entity_id: str | None = None,
    resume_ref: str | None = None,
    stage: codec.Stage = codec.Stage.BUNDLE,
    return_stage: str | None = None,
) -> None:
    actual_payload = actual
    if return_stage is not None:
        if type(actual) is dict:
            actual_payload = {**actual, "return_stage": return_stage}
        else:
            actual_payload = {
                "return_stage": return_stage,
                "entity_id": entity_id,
                "detail": actual,
            }
    raise codec.CodecError(
        codec.Diagnostic(code, stage, entity_id, expected, actual_payload, resume_ref)
    )


def _require(
    condition: Any,
    expected: Any,
    actual: Any,
    code: codec.ReasonCode = codec.ReasonCode.CONFLICT,
    *,
    entity_id: str | None = None,
    resume_ref: str | None = None,
    stage: codec.Stage = codec.Stage.BUNDLE,
    return_stage: str | None = None,
) -> None:
    if not condition:
        _fail(
            code,
            expected,
            actual,
            entity_id=entity_id,
            resume_ref=resume_ref,
            stage=stage,
            return_stage=return_stage,
        )


def extract_mismatch_attribution(diagnostic: dict[str, Any]) -> dict[str, Any] | None:
    """Extract return_stage (3A|3B|3C|4) and offending entity from a 6-field Diagnostic dict."""
    actual = diagnostic.get("actual")
    if type(actual) is dict and actual.get("return_stage") in ("3A", "3B", "3C", "4"):
        return {
            "return_stage": actual["return_stage"],
            "entity_id": diagnostic.get("entity_id") or actual.get("entity_id"),
            "reason_code": diagnostic.get("reason_code"),
            "resume_ref": diagnostic.get("resume_ref"),
        }
    return None


def _validate_file_id(value: Any, label: str) -> str:
    _require(
        type(value) is str
        and _FILE_ID_RE.fullmatch(value) is not None
        and value.split(".", 1)[0].upper() not in _WIN_RESERVED,
        f"portable FileId for {label}",
        value,
        codec.ReasonCode.INVALID_ARGUMENT,
        stage=codec.Stage.PATH,
    )
    codec.validate_business_id(value)
    return value


def _compact_json(value: Any) -> str:
    codec.validate_json_value(value)
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _encode_b64(raw: bytes | None) -> str | None:
    return None if raw is None else base64.b64encode(raw).decode("ascii")


def _decode_b64(value: Any) -> bytes | None:
    if value is None:
        return None
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError):
        _fail(
            codec.ReasonCode.INVALID_JSON,
            "valid base64 raw bytes",
            "invalid base64",
            stage=codec.Stage.DECODE,
            return_stage="4",
        )


def _read_bytes(root: Path, relative: str, *, optional: bool = False) -> bytes | None:
    path = journal._operation_path(root, relative)
    if optional and not path.exists():
        return None
    return codec.read_reference_bytes(root, relative)


def _events_path(root: Path, operation_id: str) -> Path:
    _validate_file_id(operation_id, "operation_id")
    rel = f"{EVENTS_BASE}/{operation_id}/events.jsonl"
    return journal._operation_path(root, rel)


def append_event(
    root: Path,
    operation_id: str,
    stage: str,
    status: str,
    detail: dict[str, Any] | None = None,
) -> str:
    """Append one deterministic JSONL audit event under logs/ci/b-route-chapter4-binding/<op>/events.jsonl."""
    path = _events_path(root, operation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": "newrouge.b-route-chapter4-binding-event.v1",
        "ts_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "producer": PRODUCER,
        "operation_id": operation_id,
        "stage": stage,
        "status": status,
        "detail": detail or {},
        **FLAGS,
    }
    line = json.dumps(record, ensure_ascii=True, allow_nan=False, separators=(",", ":")) + "\n"
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(line)
        stream.flush()
    return path.relative_to(Path(root).resolve()).as_posix()


def public_sync_paths(operation_id: str) -> tuple[str, str]:
    """Return repository-relative POSIX paths for raw-byte public sync journal and pending marker."""
    home = journal._operation_ref(operation_id).rsplit("/", 1)[0]
    return home + "/public-sync-journal.json", home + "/public-sync.pending.json"


def _seal_public_sync_journal(doc: dict[str, Any]) -> dict[str, Any]:
    sealed = deepcopy(doc)
    body = {k: v for k, v in sealed.items() if k != "journal_digest"}
    sealed["journal_digest"] = codec.canonical_digest(body)
    return sealed


def _validate_public_sync_entries(entries: Any) -> list[dict[str, Any]]:
    _require(type(entries) is list, "list of raw-byte public sync entries", type(entries).__name__, codec.ReasonCode.INVALID_TYPE)
    seen_paths: set[str] = set()
    validated: list[dict[str, Any]] = []
    for row in entries:
        _require(
            type(row) is dict
            and set(row) == {"path", "kind", "before_sha256", "before_base64", "after_sha256", "after_base64"},
            "complete raw-byte public sync entry",
            row,
            codec.ReasonCode.INVALID_TYPE,
        )
        rel = codec.validate_reference_path(row["path"])
        key = rel.casefold()
        _require(key not in seen_paths, "distinct public sync file paths", rel)
        seen_paths.add(key)
        _require(row["kind"] in ("contract", "event_types", "overlay"), "known public sync kind", row["kind"], codec.ReasonCode.INVALID_ENUM)
        b_sha, b_b64 = row["before_sha256"], row["before_base64"]
        if b_sha is None:
            _require(b_b64 is None, "null before_base64 for new public file", rel)
        else:
            b_bytes = _decode_b64(b_b64)
            _require(
                b_bytes is not None and codec.raw_digest(b_bytes) == b_sha,
                b_sha,
                rel,
                codec.ReasonCode.DIGEST_MISMATCH,
            )
        a_bytes = _decode_b64(row["after_base64"])
        _require(
            a_bytes is not None and codec.raw_digest(a_bytes) == row["after_sha256"],
            row["after_sha256"],
            rel,
            codec.ReasonCode.DIGEST_MISMATCH,
        )
        validated.append(row)
    return validated


def validate_public_sync_local(root: Path, envelope: dict[str, Any]) -> dict[str, Any] | None:
    """Validate optional local public-sync-journal.json and public-sync.pending.json."""
    op_id = envelope["operation_id"]
    journal_rel, pending_rel = public_sync_paths(op_id)
    j_raw = _read_bytes(root, journal_rel, optional=True)
    p_raw = _read_bytes(root, pending_rel, optional=True)
    expected_marker = {
        "schema_version": PUBLIC_SYNC_PENDING_SCHEMA,
        "operation_id": op_id,
        "frozen_digest": envelope["frozen_digest"],
    }
    if p_raw is not None:
        _require(
            codec.strict_json_loads(p_raw) == expected_marker,
            "exact owned public-sync.pending.json marker",
            pending_rel,
            entity_id=op_id,
            resume_ref=pending_rel,
        )
    if j_raw is None:
        return None
    doc = codec.strict_json_loads(j_raw)
    _require(
        type(doc) is dict,
        "JSON object in public-sync-journal.json",
        type(doc).__name__,
        codec.ReasonCode.INVALID_TYPE,
        entity_id=op_id,
        resume_ref=journal_rel,
    )
    _require(
        set(doc) == {"schema_version", "operation_id", "frozen_digest", "phase", "entries", "journal_digest"}
        and doc["schema_version"] == PUBLIC_SYNC_SCHEMA
        and doc["operation_id"] == op_id
        and doc["frozen_digest"] == envelope["frozen_digest"]
        and doc["phase"] in ("intent", "applied", "complete"),
        "valid operation-bound public-sync-journal.json",
        journal_rel,
        entity_id=op_id,
        resume_ref=journal_rel,
    )
    _require(
        doc == _seal_public_sync_journal(doc),
        "intact sealed public-sync-journal.json digest",
        journal_rel,
        codec.ReasonCode.DIGEST_MISMATCH,
        entity_id=op_id,
        resume_ref=journal_rel,
    )
    _validate_public_sync_entries(doc["entries"])
    expected_entries = envelope["frozen"]["refinement"]["public_sync_entries"]
    _require(
        doc["entries"] == expected_entries,
        "public-sync-journal entries matching frozen refinement",
        journal_rel,
        entity_id=op_id,
        resume_ref=journal_rel,
    )
    return doc


def public_sync_terminal_ok(root: Path, envelope: dict[str, Any], *, graph: dict[str, Any] | None = None) -> bool:
    """Return True only when public-sync.pending.json is absent and any journal is complete."""
    op_id = envelope["operation_id"]
    journal_rel, pending_rel = public_sync_paths(op_id)
    if graph is not None and "local_bytes" in graph:
        p_raw = graph["local_bytes"].get(pending_rel)
        j_raw = graph["local_bytes"].get(journal_rel)
    else:
        p_raw = _read_bytes(root, pending_rel, optional=True)
        j_raw = _read_bytes(root, journal_rel, optional=True)
    if p_raw is not None:
        return False
    has_changes = bool(envelope["frozen"]["refinement"]["has_public_changes"])
    if not has_changes:
        return j_raw is None
    if j_raw is None:
        return False
    doc = codec.strict_json_loads(j_raw)
    return type(doc) is dict and doc.get("phase") == "complete"


def _atomic_write_raw(root: Path, relative: str, raw: bytes, *, recheck) -> None:
    """Write complete raw bytes inside writer_boundary via commit._replace."""
    with op_scope.writer_boundary(root, recheck=recheck):
        commit._replace(root, relative, raw)


def apply_public_sync(root: Path | str, *, operation_id: str, _lease_held: bool = False) -> dict[str, Any]:
    """Roll forward explicit raw-byte contract/overlay updates via public-sync-journal.json + .pending."""
    root_path = Path(root).resolve()
    envelope = journal.read_operation(root_path, operation_id=operation_id)
    _require(
        envelope["schema_version"] == OPERATION_SCHEMA and envelope["state"] == "reserved",
        "reserved chapter4_binding operation",
        operation_id,
        entity_id=operation_id,
        resume_ref=journal._operation_ref(operation_id),
    )
    entries = envelope["frozen"]["refinement"]["public_sync_entries"]
    if not entries:
        return {"status": "noop", "operation_id": operation_id, "entries": 0}
    journal_rel, pending_rel = public_sync_paths(operation_id)
    marker_raw = projection.serialized(
        {
            "schema_version": PUBLIC_SYNC_PENDING_SCHEMA,
            "operation_id": operation_id,
            "frozen_digest": envelope["frozen_digest"],
        }
    )

    guard = (
        nullcontext()
        if _lease_held
        else op_scope.business_guard(root_path, envelope["frozen"]["scope_ids"], operation_id=operation_id)
    )
    with guard:
        existing_journal = validate_public_sync_local(root_path, envelope)
        if existing_journal is not None and existing_journal["phase"] == "complete":
            for entry in entries:
                actual = _read_bytes(root_path, entry["path"], optional=True)
                actual_sha = codec.raw_digest(actual) if actual is not None else None
                _require(
                    actual_sha == entry["after_sha256"],
                    entry["after_sha256"],
                    actual_sha,
                    codec.ReasonCode.CONFLICT,
                    entity_id=entry["path"],
                    resume_ref=journal_rel,
                    return_stage="4",
                )
            return {"status": "complete", "operation_id": operation_id, "entries": len(entries)}

        # Validate every target file on disk is exact before or after image (never overwrite unknown drift).
        def _verify_all_states() -> dict[str, str | None]:
            observed: dict[str, str | None] = {}
            for entry in entries:
                raw_now = _read_bytes(root_path, entry["path"], optional=True)
                sha_now = codec.raw_digest(raw_now) if raw_now is not None else None
                allowed = {entry["before_sha256"], entry["after_sha256"]}
                _require(
                    sha_now in allowed,
                    {"before": entry["before_sha256"], "after": entry["after_sha256"]},
                    sha_now,
                    codec.ReasonCode.CONFLICT,
                    entity_id=entry["path"],
                    resume_ref=journal_rel,
                    return_stage="4",
                )
                observed[entry["path"]] = sha_now
            return observed

        observed_before = _verify_all_states()
        if _read_bytes(root_path, pending_rel, optional=True) is None:
            def _recheck_marker():
                cur_m = _read_bytes(root_path, pending_rel, optional=True)
                _require(cur_m in (None, marker_raw), "absent or exact owned public-sync.pending.json", pending_rel)
                _verify_all_states()

            _atomic_write_raw(root_path, pending_rel, marker_raw, recheck=_recheck_marker)
        _checkpoint("public_sync_pending_durable")

        if existing_journal is None:
            draft_journal = _seal_public_sync_journal(
                {
                    "schema_version": PUBLIC_SYNC_SCHEMA,
                    "operation_id": operation_id,
                    "frozen_digest": envelope["frozen_digest"],
                    "phase": "intent",
                    "entries": deepcopy(entries),
                }
            )
            draft_raw = projection.serialized(draft_journal)

            def _recheck_journal():
                _require(_read_bytes(root_path, pending_rel) == marker_raw, "durable public-sync.pending.json", pending_rel)
                _require(_read_bytes(root_path, journal_rel, optional=True) is None, "initial public-sync-journal.json", journal_rel)
                _verify_all_states()

            _atomic_write_raw(root_path, journal_rel, draft_raw, recheck=_recheck_journal)
            existing_journal = draft_journal
        _checkpoint("public_sync_journal_durable")

        for idx, entry in enumerate(entries):
            rel = entry["path"]
            cur_raw = _read_bytes(root_path, rel, optional=True)
            cur_sha = codec.raw_digest(cur_raw) if cur_raw is not None else None
            if cur_sha == entry["after_sha256"]:
                continue
            _require(
                cur_sha == entry["before_sha256"],
                entry["before_sha256"],
                cur_sha,
                codec.ReasonCode.CONFLICT,
                entity_id=rel,
                resume_ref=journal_rel,
                return_stage="4",
            )
            _checkpoint(f"public_sync_before_file:{idx}")
            after_bytes = _decode_b64(entry["after_base64"])

            def _recheck_file(target_rel=rel, expected_before=entry["before_sha256"]):
                _require(_read_bytes(root_path, pending_rel) == marker_raw, "durable public-sync.pending.json", pending_rel)
                now_b = _read_bytes(root_path, target_rel, optional=True)
                now_sha = codec.raw_digest(now_b) if now_b is not None else None
                _require(
                    now_sha == expected_before,
                    expected_before,
                    now_sha,
                    codec.ReasonCode.INPUT_STALE,
                    entity_id=target_rel,
                    resume_ref=journal_rel,
                    return_stage="4",
                )

            _atomic_write_raw(root_path, rel, after_bytes, recheck=_recheck_file)
            _checkpoint(f"public_sync_after_file:{idx}")

        # Verify all files now equal exact after_sha256.
        for entry in entries:
            after_now = _read_bytes(root_path, entry["path"])
            _require(
                codec.raw_digest(after_now) == entry["after_sha256"],
                entry["after_sha256"],
                codec.raw_digest(after_now),
                codec.ReasonCode.DIGEST_MISMATCH,
                entity_id=entry["path"],
                resume_ref=journal_rel,
                return_stage="4",
            )

        if existing_journal["phase"] != "applied":
            applied_journal = _seal_public_sync_journal({**existing_journal, "phase": "applied"})
            applied_raw = projection.serialized(applied_journal)

            def _recheck_applied():
                _require(_read_bytes(root_path, pending_rel) == marker_raw, "durable public-sync.pending.json", pending_rel)
                for e in entries:
                    _require(
                        codec.raw_digest(_read_bytes(root_path, e["path"])) == e["after_sha256"],
                        e["after_sha256"],
                        e["path"],
                    )

            _atomic_write_raw(root_path, journal_rel, applied_raw, recheck=_recheck_applied)
            existing_journal = applied_journal
        _checkpoint("public_sync_applied_durable")
        return {
            "status": "applied",
            "operation_id": operation_id,
            "entries": len(entries),
            "journal_ref": journal_rel,
            "pending_ref": pending_rel,
            "observed_before_count": len(observed_before),
        }


def finalize_public_sync_cleanup(root: Path, envelope: dict[str, Any]) -> None:
    """Mark public-sync-journal.json complete and unlink public-sync.pending.json after commit publication."""
    op_id = envelope["operation_id"]
    journal_rel, pending_rel = public_sync_paths(op_id)
    j_doc = validate_public_sync_local(root, envelope)
    marker_path = journal._operation_path(root, pending_rel)
    expected_marker = projection.serialized(
        {
            "schema_version": PUBLIC_SYNC_PENDING_SCHEMA,
            "operation_id": op_id,
            "frozen_digest": envelope["frozen_digest"],
        }
    )
    commit_intent_rel, commit_pending_rel = commit._paths(op_id)
    commit_intent_bytes = _read_bytes(root, commit_intent_rel)
    catalog_bytes = _read_bytes(root, records.CATALOG_PATH)

    def _recheck_commit_terminal() -> None:
        _require(
            _read_bytes(root, commit_intent_rel) == commit_intent_bytes,
            "unchanged complete commit intent before public-sync cleanup",
            commit_intent_rel,
            codec.ReasonCode.INPUT_STALE,
            entity_id=op_id,
            resume_ref=commit_intent_rel,
            return_stage="4",
        )
        _require(
            _read_bytes(root, commit_pending_rel, optional=True) is None,
            "cleaned commit.pending.json before public-sync cleanup",
            commit_pending_rel,
            codec.ReasonCode.INPUT_STALE,
            entity_id=op_id,
            resume_ref=commit_pending_rel,
            return_stage="4",
        )
        _require(
            _read_bytes(root, records.CATALOG_PATH) == catalog_bytes,
            "unchanged published catalog before public-sync cleanup",
            records.CATALOG_PATH,
            codec.ReasonCode.INPUT_STALE,
            entity_id=op_id,
            resume_ref=records.CATALOG_PATH,
            return_stage="4",
        )

    final_journal_raw: bytes | None = None
    if j_doc is not None and j_doc["phase"] != "complete":
        orig_journal_raw = _read_bytes(root, journal_rel)
        complete_doc = _seal_public_sync_journal({**j_doc, "phase": "complete"})
        complete_raw = projection.serialized(complete_doc)

        def _recheck_complete():
            _recheck_commit_terminal()
            _require(
                _read_bytes(root, journal_rel) == orig_journal_raw,
                "unchanged public-sync-journal.json before terminal completion",
                journal_rel,
                codec.ReasonCode.INPUT_STALE,
                entity_id=op_id,
                resume_ref=journal_rel,
                return_stage="4",
            )

        with op_scope.writer_boundary(root, recheck=_recheck_complete):
            commit._replace(root, journal_rel, complete_raw)
        final_journal_raw = complete_raw
    elif j_doc is not None:
        final_journal_raw = _read_bytes(root, journal_rel)

    if marker_path.exists():
        def _recheck_unlink():
            _recheck_commit_terminal()
            if final_journal_raw is not None:
                _require(
                    _read_bytes(root, journal_rel) == final_journal_raw,
                    "complete public-sync-journal.json before pending cleanup",
                    journal_rel,
                    codec.ReasonCode.INPUT_STALE,
                    entity_id=op_id,
                    resume_ref=journal_rel,
                    return_stage="4",
                )
            _require(
                not marker_path.exists() or marker_path.read_bytes() == expected_marker,
                "exact owned public-sync.pending.json before cleanup",
                pending_rel,
            )

        with op_scope.writer_boundary(root, recheck=_recheck_unlink):
            if marker_path.exists():
                marker_path.unlink()


# ---------------------------------------------------------------------------
# C# BCL / Non-Empty DTO & Interface / Godot .tscn/.tres Verifiers
# ---------------------------------------------------------------------------


def _strip_csharp_comments(text: str) -> str:
    """Single-pass C# lexer preserving string/char literals while stripping // and /* */ comments."""
    out: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        # Line comment: // ... \n
        if ch == "/" and nxt == "/":
            i += 2
            while i < n and text[i] != "\n":
                i += 1
            if i < n:
                out.append("\n")
                i += 1
            continue
        # Block comment: /* ... */
        if ch == "/" and nxt == "*":
            i += 2
            out.append(" ")
            while i < n:
                if text[i] == "*" and i + 1 < n and text[i + 1] == "/":
                    i += 2
                    break
                if text[i] == "\n":
                    out.append("\n")
                i += 1
            continue
        # Verbatim string literal: @"..." or $@"..." or @$"..."
        if (ch == "@" and nxt == '"') or (
            ch in ("$", "@")
            and nxt in ("$", "@")
            and ch != nxt
            and i + 2 < n
            and text[i + 2] == '"'
        ):
            start_q = i + 1 if ch == "@" and nxt == '"' else i + 2
            out.append(text[i : start_q + 1])
            i = start_q + 1
            while i < n:
                c = text[i]
                out.append(c)
                if c == '"':
                    if i + 1 < n and text[i + 1] == '"':
                        out.append('"')
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue
        # Normal / interpolated string literal: "..."
        if ch == '"':
            out.append(ch)
            i += 1
            while i < n:
                c = text[i]
                out.append(c)
                if c == "\\" and i + 1 < n:
                    out.append(text[i + 1])
                    i += 2
                    continue
                i += 1
                if c == '"' or c == "\n":
                    break
            continue
        # Char literal: '...'
        if ch == "'":
            out.append(ch)
            i += 1
            while i < n:
                c = text[i]
                out.append(c)
                if c == "\\" and i + 1 < n:
                    out.append(text[i + 1])
                    i += 2
                    continue
                i += 1
                if c == "'" or c == "\n":
                    break
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _extract_balanced_brace_body(text: str, open_idx: int) -> tuple[str, int] | None:
    """Return (inner_body, close_idx) for a '{' at open_idx, respecting strings/chars."""
    if open_idx >= len(text) or text[open_idx] != "{":
        return None
    depth = 0
    i = open_idx
    n = len(text)
    while i < n:
        ch = text[i]
        if ch == '"':
            i += 1
            while i < n:
                if text[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                if text[i] == '"':
                    i += 1
                    break
                i += 1
            continue
        if ch == "'":
            i += 1
            while i < n:
                if text[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                if text[i] == "'":
                    i += 1
                    break
                i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[open_idx + 1 : i], i
        i += 1
    return None


def _body_has_non_const_member(body: str) -> bool:
    """Return True if a type body contains at least one non-const member (property/field/method/ctor)."""
    stripped = body.strip()
    if not stripped:
        return False
    without_consts = re.sub(
        r"(?:\[[^\]]*\]\s*)*(?:(?:public|internal|private|protected|new|static)\s+)*const\s+[^;]+;",
        "",
        stripped,
        flags=re.S,
    )
    return bool(re.sub(r"[;\s]+", "", without_consts))


def _check_no_empty_interfaces_or_dtos(rel_path: str, text: str) -> None:
    cleaned = _strip_csharp_comments(text)
    # 1. Empty interface: interface IFoo ... { }
    for match in re.finditer(
        r"\binterface\s+([A-Za-z_][A-Za-z0-9_]*)[^{;]*\{",
        cleaned,
        flags=re.S,
    ):
        name = match.group(1)
        extracted = _extract_balanced_brace_body(cleaned, match.end() - 1)
        if extracted is None:
            continue
        body, _ = extracted
        _require(
            bool(re.sub(r"[;\s]+", "", body)),
            f"non-empty interface declaration for {name}",
            {"file": rel_path, "symbol": name, "issue": "empty_interface"},
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=name,
            resume_ref=rel_path,
            return_stage="4",
        )
    # 2. Primary-constructor empty DTOs/classes/records/structs:
    #    record Foo(); / class Bar(); / struct Baz(); / or () { /* empty or const-only */ }
    for match in re.finditer(
        r"\b((?:(?:public|internal|private|protected|sealed|abstract|readonly|static|partial|ref|file)\s+)*)"
        r"(record(?:\s+(?:class|struct))?|class|struct)\s+([A-Za-z_][A-Za-z0-9_]*)"
        r"(?:<[^<>]+>)?\s*\(\s*\)\s*(?::[^{;]+)?(\{|;)",
        cleaned,
        flags=re.S,
    ):
        modifiers = match.group(1).split()
        kind_tok = match.group(2)
        name = match.group(3)
        delim = match.group(4)
        if "static" in modifiers:
            continue
        if delim == ";":
            _fail(
                codec.ReasonCode.SEMANTIC_ERROR,
                f"non-empty primary-constructor {kind_tok} DTO declaration for {name}",
                {"file": rel_path, "symbol": name, "issue": "empty_dto"},
                entity_id=name,
                resume_ref=rel_path,
                return_stage="4",
            )
        extracted = _extract_balanced_brace_body(cleaned, match.end() - 1)
        if extracted is None:
            continue
        body, _ = extracted
        _require(
            _body_has_non_const_member(body),
            f"non-empty {kind_tok} DTO declaration for {name}",
            {"file": rel_path, "symbol": name, "issue": "empty_dto"},
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=name,
            resume_ref=rel_path,
            return_stage="4",
        )
    # 3. Body-only empty or const-only non-static record/class/struct:
    #    public [sealed|readonly] (record|class|struct) Foo { } (no primary-constructor params)
    for match in re.finditer(
        r"\b((?:(?:public|internal|sealed|abstract|readonly|static|partial|ref|file)\s+)+)"
        r"(record(?:\s+(?:class|struct))?|class|struct)\s+([A-Za-z_][A-Za-z0-9_]*)"
        r"(?:<[^<>]+>)?\s*(?::[^{;(]+)?\{",
        cleaned,
        flags=re.S,
    ):
        modifiers = match.group(1).split()
        kind_tok = match.group(2)
        name = match.group(3)
        if "static" in modifiers:
            continue
        extracted = _extract_balanced_brace_body(cleaned, match.end() - 1)
        if extracted is None:
            continue
        body, _ = extracted
        _require(
            _body_has_non_const_member(body),
            f"non-empty {kind_tok} DTO declaration for {name}",
            {"file": rel_path, "symbol": name, "issue": "empty_dto"},
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=name,
            resume_ref=rel_path,
            return_stage="4",
        )


def _validate_contract_source(rel_path: str, text: str, event_types_map: dict[str, str]) -> None:
    _require(
        rel_path.startswith("Game.Core/Contracts/") and rel_path.endswith(".cs"),
        "Game.Core/Contracts/**.cs path",
        rel_path,
        codec.ReasonCode.INVALID_REFERENCE,
        entity_id=rel_path,
        resume_ref=rel_path,
        return_stage="4",
    )
    ns_issues = validate_contracts._validate_namespace(rel_path, text)
    _require(
        not ns_issues,
        "Game.Core.Contracts namespace",
        ns_issues,
        codec.ReasonCode.SEMANTIC_ERROR,
        entity_id=rel_path,
        resume_ref=rel_path,
        return_stage="4",
    )
    bcl_issues = validate_contracts._validate_bcl_only(rel_path, text)
    _require(
        not bcl_issues,
        "BCL-only contract without Godot.* or non-BCL dependencies",
        bcl_issues,
        codec.ReasonCode.SEMANTIC_ERROR,
        entity_id=rel_path,
        resume_ref=rel_path,
        return_stage="4",
    )
    has_event_const = "public const string EventType" in text
    xml_issues = validate_contracts._validate_xml_comments(rel_path, text, require_remarks=has_event_const)
    _require(
        not xml_issues,
        "XML documentation comments on public contract type",
        xml_issues,
        codec.ReasonCode.SEMANTIC_ERROR,
        entity_id=rel_path,
        resume_ref=rel_path,
        return_stage="4",
    )
    ev_issues = validate_contracts._validate_eventtype_constants(rel_path, text, event_types_map)
    _require(
        not ev_issues,
        "valid ADR-0004 EventType constants",
        ev_issues,
        codec.ReasonCode.SEMANTIC_ERROR,
        entity_id=rel_path,
        resume_ref=rel_path,
        return_stage="4",
    )
    _check_no_empty_interfaces_or_dtos(rel_path, text)


def _strip_godot_text_comments(text: str) -> str:
    """Strip ';' comment lines from Godot .tscn/.tres text files."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(";"))


def _verify_existing_asset_content(
    *,
    obj_id: str,
    kind: str,
    expected_type: str,
    rel_path: str,
    raw: bytes,
    event_types_map: dict[str, str],
) -> None:
    # Enforce layer path rules by implementation object kind.
    if kind in ("command", "read_only_state"):
        _require(
            rel_path.startswith("Game.Core/Contracts/") and rel_path.endswith(".cs"),
            "Game.Core/Contracts/**.cs path for command/read_only_state contract asset",
            rel_path,
            codec.ReasonCode.INVALID_REFERENCE,
            entity_id=obj_id,
            resume_ref=rel_path,
            return_stage="4",
        )
    elif kind == "adapter":
        _require(
            rel_path.startswith("Game.Godot/") and rel_path.endswith(".cs"),
            "Game.Godot/**.cs path for thin C# adapter asset",
            rel_path,
            codec.ReasonCode.INVALID_REFERENCE,
            entity_id=obj_id,
            resume_ref=rel_path,
            return_stage="4",
        )

    if rel_path.endswith(".res"):
        _require(
            len(raw) >= 4 and (raw.startswith((b"RSRC", b"RSCC")) or bool(raw.strip())),
            "non-empty valid Godot .res binary or text resource",
            rel_path,
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=obj_id,
            resume_ref=rel_path,
            return_stage="4",
        )
        return

    if not rel_path.endswith((".cs", ".tscn", ".tres")):
        _fail(
            codec.ReasonCode.INVALID_REFERENCE,
            "supported existing implementation asset extension (.cs, .tscn, .tres, .res)",
            rel_path,
            entity_id=obj_id,
            resume_ref=rel_path,
            return_stage="4",
        )

    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        _fail(
            codec.ReasonCode.INVALID_UTF8,
            "valid UTF-8 existing implementation file",
            rel_path,
            entity_id=obj_id,
            resume_ref=rel_path,
            return_stage="4",
        )
    _require(
        bool(text.strip()),
        "non-empty existing implementation file",
        rel_path,
        codec.ReasonCode.SEMANTIC_ERROR,
        entity_id=obj_id,
        resume_ref=rel_path,
        return_stage="4",
    )
    _require(
        _FAKE_NODE_RE.search(text) is None,
        "real implementation artifact without fake/placeholder markers",
        rel_path,
        codec.ReasonCode.SEMANTIC_ERROR,
        entity_id=obj_id,
        resume_ref=rel_path,
        return_stage="4",
    )

    if rel_path.endswith(".cs"):
        if rel_path.startswith("Game.Core/Contracts/"):
            _validate_contract_source(rel_path, text, event_types_map)
        else:
            _check_no_empty_interfaces_or_dtos(rel_path, text)
        cleaned = _strip_csharp_comments(text)
        # Extract simple symbol token from expected_type (supports Namespace.Type, Type<T>, Type.Member).
        base_type = expected_type.split("<", 1)[0].strip()
        parts = [p for p in re.split(r"[.:/]", base_type) if p]
        symbol = parts[-1] if parts else base_type
        parent_symbol = parts[-2] if len(parts) >= 2 else None
        type_decl = re.search(
            rf"\b(?:record(?:\s+(?:class|struct))?|class|struct|interface|enum)\s+{re.escape(symbol)}\b",
            cleaned,
        )
        member_decl = re.search(rf"\b{re.escape(symbol)}\b", cleaned)
        parent_decl = (
            re.search(
                rf"\b(?:record(?:\s+(?:class|struct))?|class|struct|interface|enum)\s+{re.escape(parent_symbol)}\b",
                cleaned,
            )
            if parent_symbol
            else None
        )
        _require(
            type_decl is not None or (parent_decl is not None and member_decl is not None),
            f"existing C# symbol matching {expected_type}",
            {"path": rel_path, "expected_type": expected_type},
            codec.ReasonCode.UNRESOLVED_REFERENCE,
            entity_id=obj_id,
            resume_ref=rel_path,
            return_stage="4",
        )
    elif rel_path.endswith(".tscn"):
        uncommented = _strip_godot_text_comments(text)
        _require(
            "[gd_scene" in uncommented,
            "valid Godot .tscn [gd_scene header",
            rel_path,
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=obj_id,
            resume_ref=rel_path,
            return_stage="4",
        )
        node_types = set(re.findall(r'\[node\s+[^\]]*type="([^"]+)"', uncommented))
        node_names = set(re.findall(r'\[node\s+[^\]]*name="([^"]+)"', uncommented))
        _require(
            bool(node_types),
            "at least one real typed [node ...] in .tscn",
            rel_path,
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=obj_id,
            resume_ref=rel_path,
            return_stage="4",
        )
        simple = expected_type.split(":", 1)[-1].split(".", 1)[-1].strip()
        _require(
            simple in node_types or simple in node_names or expected_type in uncommented,
            f"scene node matching expected_type {expected_type}",
            {"node_types": sorted(node_types), "node_names": sorted(node_names)},
            codec.ReasonCode.UNRESOLVED_REFERENCE,
            entity_id=obj_id,
            resume_ref=rel_path,
            return_stage="4",
        )
    elif rel_path.endswith(".tres"):
        uncommented = _strip_godot_text_comments(text)
        _require(
            "[gd_resource" in uncommented,
            "valid Godot .tres [gd_resource header",
            rel_path,
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=obj_id,
            resume_ref=rel_path,
            return_stage="4",
        )
        res_types = set(re.findall(r'type="([^"]+)"', uncommented))
        script_classes = set(re.findall(r'script_class="([^"]+)"', uncommented))
        simple = expected_type.split(":", 1)[-1].split(".", 1)[-1].strip()
        _require(
            simple in res_types or simple in script_classes or expected_type in uncommented,
            f"resource type matching expected_type {expected_type}",
            {"resource_types": sorted(res_types), "script_classes": sorted(script_classes)},
            codec.ReasonCode.UNRESOLVED_REFERENCE,
            entity_id=obj_id,
            resume_ref=rel_path,
            return_stage="4",
        )
    else:
        _fail(
            codec.ReasonCode.INVALID_REFERENCE,
            "supported existing implementation asset extension (.cs, .tscn, .tres, .res)",
            rel_path,
            entity_id=obj_id,
            resume_ref=rel_path,
            return_stage="4",
        )


def _merge_event_types_source(existing_text: str | None, additions: list[dict[str, str]]) -> str:
    if existing_text is None:
        base = (
            "namespace Game.Core.Contracts;\n\n"
            "/// <summary>\n"
            "/// Canonical domain and UI event type constants.\n"
            "/// </summary>\n"
            "public static class EventTypes\n"
            "{\n"
            "}\n"
        )
    else:
        base = existing_text.replace("\r\n", "\n").replace("\r", "\n")

    current_map: dict[str, str] = {}
    for match in validate_contracts.EVENT_TYPES_CONST_PATTERN.finditer(base):
        current_map[match.group(1)] = match.group(2)

    new_lines: list[str] = []
    for item in additions:
        name = item["name"]
        value = item["value"]
        _require(
            _CONST_NAME_RE.fullmatch(name) is not None,
            "valid C# EventTypes constant identifier",
            name,
            codec.ReasonCode.INVALID_ARGUMENT,
            entity_id=name,
            resume_ref="Game.Core/Contracts/EventTypes.cs",
            return_stage="4",
        )
        _require(
            validate_contracts.EVENT_TYPE_PATTERN.fullmatch(value) is not None,
            "ADR-0004 EventType pattern (core.*/ui.menu.*/screen.*)",
            value,
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=name,
            resume_ref="Game.Core/Contracts/EventTypes.cs",
            return_stage="4",
        )
        if name in current_map:
            _require(
                current_map[name] == value,
                f"consistent existing EventTypes.{name} value {current_map[name]}",
                value,
                codec.ReasonCode.CONFLICT,
                entity_id=name,
                resume_ref="Game.Core/Contracts/EventTypes.cs",
                return_stage="4",
            )
            continue
        current_map[name] = value
        new_lines.append(f'    public const string {name} = "{value}";')

    if not new_lines:
        return base if base.endswith("\n") else base + "\n"

    close_idx = base.rfind("}")
    _require(
        close_idx >= 0,
        "closing brace in Game.Core/Contracts/EventTypes.cs",
        "EventTypes.cs",
        codec.ReasonCode.SEMANTIC_ERROR,
        entity_id="EventTypes",
        resume_ref="Game.Core/Contracts/EventTypes.cs",
        return_stage="4",
    )
    prefix = base[:close_idx].rstrip("\n")
    suffix = base[close_idx:]
    merged = prefix + "\n" + "\n".join(new_lines) + "\n" + suffix
    if not merged.endswith("\n"):
        merged += "\n"
    return merged


# ---------------------------------------------------------------------------
# Clean-Clone Stage-4 Semantics Extractor (Zero logs/ Dependency)
# ---------------------------------------------------------------------------


def _parse_prefixed_json(text: str, prefix: str) -> dict[str, Any] | None:
    if not isinstance(text, str):
        return None
    idx = text.find(prefix)
    if idx < 0:
        return None
    payload_text = text[idx + len(prefix) :].strip()
    value = codec.strict_json_loads(payload_text)
    if type(value) is not dict:
        _fail(
            codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
            "JSON object in Stage-4 semantic tag",
            type(value).__name__,
            stage=codec.Stage.CONTENT,
            return_stage="4",
        )
    return value


def extract_stage4_semantics(plan: dict[str, Any], binding: dict[str, Any]) -> dict[str, Any]:
    """Parse complete Stage-4 implementation semantics directly from formal plan and binding records.

    Works on clean clones without any logs/ directory or local operation store.
    """
    _require(
        type(plan) is dict and plan.get("schema_version") == "newrouge.b-route-plan.v1",
        "formal newrouge.b-route-plan.v1 document",
        plan.get("schema_version") if type(plan) is dict else type(plan).__name__,
        codec.ReasonCode.SCHEMA_MISMATCH,
        stage=codec.Stage.SCHEMA,
        return_stage="3B",
    )
    _require(
        type(binding) is dict and binding.get("schema_version") == "newrouge.b-route-binding.v1",
        "formal newrouge.b-route-binding.v1 document",
        binding.get("schema_version") if type(binding) is dict else type(binding).__name__,
        codec.ReasonCode.SCHEMA_MISMATCH,
        stage=codec.Stage.SCHEMA,
        return_stage="4",
    )
    _require(
        binding.get("plan_id") == plan.get("plan_id"),
        plan.get("plan_id"),
        binding.get("plan_id"),
        codec.ReasonCode.MAPPING_MISMATCH,
        entity_id=str(binding.get("plan_id")),
        return_stage="4",
    )
    _require(
        binding.get("stage") in ("4", "5"),
        "binding stage 4 or 5",
        binding.get("stage"),
        codec.ReasonCode.SEMANTIC_ERROR,
        entity_id=binding["plan_id"],
        return_stage="4",
    )

    commands: list[dict[str, Any]] = []
    read_only_states: list[dict[str, Any]] = []
    adapters: list[dict[str, Any]] = []
    bindings_list: list[dict[str, Any]] = []
    scenes_and_resources: list[dict[str, Any]] = []
    planned_objects: list[dict[str, Any]] = []
    existing_objects: list[dict[str, Any]] = []

    for obj in binding.get("implementation_objects", []):
        meta = _parse_prefixed_json(obj.get("lifecycle", ""), STAGE4_LIFECYCLE_PREFIX) or {}
        base_entry = {
            "id": obj["id"],
            "kind": obj["kind"],
            "availability": obj["availability"],
            "responsible_task_ids": list(obj["responsible_task_ids"]),
            "expected_type": obj["expected_type"],
            "later_checks": list(obj["later_checks"]),
            "target_ref": deepcopy(obj["target_ref"]),
            "handoff": meta.get("handoff"),
        }
        if obj["availability"] == "planned":
            planned_objects.append(deepcopy(base_entry))
        else:
            existing_objects.append(deepcopy(base_entry))

        kind = obj["kind"]
        if kind == "command":
            commands.append(
                {
                    **base_entry,
                    "owner": meta.get("owner"),
                    "preconditions": list(meta.get("preconditions", [])),
                    "postconditions": list(meta.get("postconditions", [])),
                    "invariants": list(meta.get("invariants", [])),
                    "contract_ref": meta.get("contract_ref"),
                }
            )
        elif kind == "read_only_state":
            read_only_states.append(
                {
                    **base_entry,
                    "single_owner": meta.get("single_owner"),
                    "read_only_views": list(meta.get("read_only_views", [])),
                    "forbidden_direct_writers": list(meta.get("forbidden_direct_writers", ["adapter", "ui"])),
                    "contract_ref": meta.get("contract_ref"),
                }
            )
        elif kind == "adapter":
            adapters.append(
                {
                    **base_entry,
                    "dependencies": list(meta.get("dependencies", [])),
                    "lifecycle_spec": meta.get("lifecycle"),
                    "forbidden_arbitration": bool(meta.get("forbidden_arbitration", True)),
                }
            )
        elif kind == "binding":
            bindings_list.append(
                {
                    **base_entry,
                    "control_to_target": deepcopy(meta.get("control_to_target", [])),
                }
            )
        elif kind in ("scene", "resource"):
            scenes_and_resources.append(
                {
                    **base_entry,
                    "scene_entry": list(meta.get("scene_entry", [])),
                    "scene_return": list(meta.get("scene_return", [])),
                }
            )

    parts_summary: dict[str, dict[str, Any]] = {}
    ui_slice: dict[str, Any] = {
        "applicable": False,
        "rationale": "",
        "inputs": [],
        "methods": [],
        "wiring": [],
        "human_zones": [],
        "chapter7_required": False,
    }
    for part in binding.get("parts", []):
        part_meta: dict[str, Any] = {}
        plain_resps: list[str] = []
        ui_meta = _parse_prefixed_json(part.get("rationale", ""), STAGE4_UI_PREFIX)
        if ui_meta is not None:
            ui_slice = deepcopy(ui_meta)
        for resp in part.get("responsibilities", []):
            parsed_part = _parse_prefixed_json(resp, STAGE4_PART_PREFIX)
            if parsed_part is not None:
                part_meta.update(parsed_part)
                continue
            parsed_ui = _parse_prefixed_json(resp, STAGE4_UI_PREFIX)
            if parsed_ui is not None:
                ui_slice = deepcopy(parsed_ui)
                continue
            plain_resps.append(resp)
        parts_summary[part["kind"]] = {
            "applicability": part["applicability"],
            "rationale": part["rationale"].split(" | " + STAGE4_UI_PREFIX, 1)[0],
            "responsibilities": plain_resps,
            "stage4_meta": part_meta,
        }

    obligations_summary: list[dict[str, Any]] = []
    for obl in binding.get("obligations", []):
        obl_meta = _parse_prefixed_json(obl.get("responsibility", ""), STAGE4_OBL_PREFIX) or {}
        plain_resp = obl["responsibility"].split(" | " + STAGE4_OBL_PREFIX, 1)[0]
        obligations_summary.append(
            {
                "id": obl["id"],
                "requirement_ids": list(obl["requirement_ids"]),
                "flow_ids": list(obl["flow_ids"]),
                "test_ids": list(obl["test_ids"]),
                "responsibility": plain_resp,
                "verification_refs": deepcopy(obl["verification_refs"]),
                "stage4_meta": obl_meta,
            }
        )

    return {
        "schema_version": STAGE4_SEMANTICS_SCHEMA,
        "plan_id": plan["plan_id"],
        "plan_revision": plan["revision"],
        "binding_revision": binding["binding_revision"],
        "stage": binding["stage"],
        "task_ids": sorted(m["task_id"] for m in binding.get("task_mappings", [])),
        "task_mappings": deepcopy(binding.get("task_mappings", [])),
        "parts": parts_summary,
        "commands": commands,
        "read_only_states": read_only_states,
        "adapters": adapters,
        "bindings": bindings_list,
        "scenes_and_resources": scenes_and_resources,
        "obligations": obligations_summary,
        "ui_slice": ui_slice,
        "planned_objects": planned_objects,
        "existing_objects": existing_objects,
        **FLAGS,
    }


# ---------------------------------------------------------------------------
# Snapshot & Triplet Sync Helpers
# ---------------------------------------------------------------------------


class Chapter4Snapshot:
    """Tracks raw non-triplet files and triplet definition projections before commit freeze."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.files: dict[str, str | None] = {}
        self.triplet_projections: dict[str, str] = {}
        self.directories: dict[str, list[str]] = {}
        self.native_capture = None

    def read(self, name: str, *, optional: bool = False) -> bytes | None:
        raw = _read_bytes(self.root, name, optional=optional)
        digest = codec.raw_digest(raw) if raw is not None else None
        if name.casefold() in {p.casefold() for p in TRIPLET.values()}:
            _require(raw is not None, "existing Taskmaster triplet file", name, codec.ReasonCode.FILE_NOT_FOUND)
            proj = records.task_document_digest(name, raw)
            _require(
                name not in self.triplet_projections or self.triplet_projections[name] == proj,
                "stable Taskmaster triplet projection",
                name,
                codec.ReasonCode.INPUT_STALE,
            )
            self.triplet_projections[name] = proj
            return raw
        _require(
            name not in self.files or self.files[name] == digest,
            "stable observed chapter4 input",
            name,
            codec.ReasonCode.INPUT_STALE,
        )
        self.files[name] = digest
        return raw

    def verify(self) -> None:
        for name, expected in list(self.files.items()):
            raw = _read_bytes(self.root, name, optional=True)
            actual = codec.raw_digest(raw) if raw is not None else None
            _require(actual == expected, expected, name, codec.ReasonCode.INPUT_STALE)
        docs = {}
        for key, path in TRIPLET.items():
            if path in self.triplet_projections:
                raw = _read_bytes(self.root, path)
                actual_proj = records.task_document_digest(path, raw)
                _require(
                    actual_proj == self.triplet_projections[path],
                    self.triplet_projections[path],
                    actual_proj,
                    codec.ReasonCode.INPUT_STALE,
                    resume_ref=path,
                )
                docs[key] = codec.strict_json_loads(raw)
        if len(docs) == 3:
            records.TaskJoinContext(**docs).indexes()


def _load_triplet(snapshot: Chapter4Snapshot) -> dict[str, Any]:
    raws = {key: snapshot.read(path) for key, path in TRIPLET.items()}
    docs = {key: codec.strict_json_loads(raw) for key, raw in raws.items()}
    join = records.TaskJoinContext(**docs)
    master_by_id, views = join.indexes()
    for task in master_by_id.values():
        protection._task_state(task, master=True)
    for view_name in ("back", "gameplay"):
        for row in docs[view_name]:
            protection._task_state(row, master=False)
    return {
        "raws": raws,
        "docs": docs,
        "join": join,
        "master": master_by_id,
        "views": views,
    }


def _apply_triplet_ref_sync(
    *,
    root: Path,
    triplet: dict[str, Any],
    sync_entries: list[dict[str, Any]],
    allowed_task_ids: set[int],
    allowed_events: set[str],
    binding_path: str,
    virtual_files: dict[str, bytes] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Sync contractRefs/overlay_refs/evidence_refs/additive acceptance while strictly forbidding weakening."""
    master_doc = deepcopy(triplet["docs"]["master"])
    back_rows = deepcopy(triplet["docs"]["back"])
    gameplay_rows = deepcopy(triplet["docs"]["gameplay"])
    master_by_id = {row["id"]: row for row in master_doc["master"]["tasks"]}
    back_by_tid = {row["taskmaster_id"]: row for row in back_rows}
    gameplay_by_tid = {row["taskmaster_id"]: row for row in gameplay_rows}
    vfiles = virtual_files or {}
    affected_tids: set[int] = set()

    for entry in sync_entries:
        tid = entry["task_id"]
        _require(
            tid in allowed_task_ids,
            "conserved 3C/4 task_id for triplet_ref_sync",
            tid,
            codec.ReasonCode.MAPPING_MISMATCH,
            entity_id=str(tid),
            resume_ref=TRIPLET["master"],
            return_stage="3C",
        )
        affected_tids.add(tid)
        add_contracts = list(entry.get("add_contract_refs", []))
        for ev in add_contracts:
            _require(
                ev in allowed_events,
                "EventTypes.cs registered event constant for contractRefs",
                ev,
                codec.ReasonCode.UNRESOLVED_REFERENCE,
                entity_id=str(tid),
                resume_ref="Game.Core/Contracts/EventTypes.cs",
                return_stage="4",
            )
        add_overlays = list(entry.get("add_overlay_refs", []))
        for ov in add_overlays:
            ov_rel = codec.validate_reference_path(ov)
            _require(
                _OVERLAY_PATH_RE.fullmatch(ov_rel) is not None,
                "docs/architecture/overlays/<PRD-ID>/08/<page>.md for add_overlay_refs",
                ov_rel,
                codec.ReasonCode.INVALID_REFERENCE,
                entity_id=str(tid),
                resume_ref=ov_rel,
                return_stage="4",
            )
            exists_ov = (ov_rel in vfiles) or (_read_bytes(root, ov_rel, optional=True) is not None)
            _require(
                exists_ov,
                f"existing overlay file {ov_rel} in post-sync tree",
                ov_rel,
                codec.ReasonCode.UNRESOLVED_REFERENCE,
                entity_id=str(tid),
                resume_ref=ov_rel,
                return_stage="4",
            )
        add_evidence = list(entry.get("add_evidence_refs", []))
        add_acceptance = list(entry.get("add_acceptance", []))
        replace_acceptance = entry.get("replace_acceptance")

        for item in add_acceptance:
            _require(
                type(item) is str and "Refs:" in item,
                "acceptance entry containing 'Refs:'",
                item,
                codec.ReasonCode.SEMANTIC_ERROR,
                entity_id=str(tid),
                resume_ref=TRIPLET["back"],
                return_stage="4",
            )

        views_touched = [r for r in (back_by_tid.get(tid), gameplay_by_tid.get(tid)) if r is not None]
        _require(
            bool(views_touched),
            "at least one view row for synced task_id",
            tid,
            codec.ReasonCode.MAPPING_MISMATCH,
            entity_id=str(tid),
            return_stage="3C",
        )
        for row in views_touched:
            existing_acc = list(row.get("acceptance", []))
            if replace_acceptance is not None:
                # Anti-weakening: every existing acceptance entry must remain intact and all entries need Refs:.
                for item in replace_acceptance:
                    _require(
                        type(item) is str and "Refs:" in item,
                        "acceptance entry containing 'Refs:'",
                        item,
                        codec.ReasonCode.SEMANTIC_ERROR,
                        entity_id=str(tid),
                        return_stage="4",
                    )
                missing_existing = [old for old in existing_acc if old not in replace_acceptance]
                _require(
                    not missing_existing,
                    "no acceptance weakening (all existing acceptance entries retained)",
                    {"task_id": tid, "dropped_acceptance": missing_existing},
                    codec.ReasonCode.SEMANTIC_ERROR,
                    entity_id=str(tid),
                    return_stage="4",
                )
                merged_acc = list(dict.fromkeys([*replace_acceptance, *add_acceptance]))
                row["acceptance"] = merged_acc
            elif add_acceptance:
                row["acceptance"] = list(dict.fromkeys([*existing_acc, *add_acceptance]))

            if add_contracts:
                row["contractRefs"] = sorted(set(row.get("contractRefs", [])) | set(add_contracts))
            if add_overlays:
                row["overlay_refs"] = list(dict.fromkeys([*row.get("overlay_refs", []), *add_overlays]))
            row["evidence_refs"] = list(
                dict.fromkeys([*row.get("evidence_refs", []), *add_evidence, binding_path])
            )

        # Keep master task details synchronized without touching status/subtasks/id or clobbering shared overlay.
        m_row = master_by_id[tid]
        if add_overlays and not str(m_row.get("overlay") or "").strip():
            m_row["overlay"] = add_overlays[0]
        if add_contracts or add_overlays:
            details_lines = str(m_row.get("details") or "").splitlines()
            if add_overlays:
                marker = "Overlays: " + "; ".join(add_overlays)
                if marker not in details_lines:
                    details_lines.append(marker)
            if add_contracts:
                marker = "ContractRefs: " + "; ".join(sorted(set(add_contracts)))
                if marker not in details_lines:
                    details_lines.append(marker)
            m_row["details"] = "\n".join(line for line in details_lines if line)

    # Validate affected task_ids with check_task_contract_refs rules against post-sync EventTypes & views.
    consistency_overrides = check_task_contract_refs._load_consistency_overrides(
        root, check_task_contract_refs.DEFAULT_CONSISTENCY_WHITELIST
    )
    for tid in sorted(affected_tids):
        view_entries: list[tuple[str, dict[str, Any]]] = []
        if tid in back_by_tid:
            view_entries.append((TRIPLET["back"], back_by_tid[tid]))
        if tid in gameplay_by_tid:
            view_entries.append((TRIPLET["gameplay"], gameplay_by_tid[tid]))
        for view_path, row in view_entries:
            refs = row.get("contractRefs")
            if refs is None:
                refs = []
            _require(
                isinstance(refs, list),
                "array contractRefs on business view task",
                {"task_id": tid, "file": view_path},
                codec.ReasonCode.INVALID_TYPE,
                entity_id=str(tid),
                resume_ref=view_path,
                return_stage="4",
            )
            unknown_ev = [str(x) for x in refs if str(x) not in allowed_events]
            _require(
                not unknown_ev,
                "all contractRefs registered in post-sync EventTypes.cs",
                {"task_id": tid, "file": view_path, "unknown_events": unknown_ev},
                codec.ReasonCode.UNRESOLVED_REFERENCE,
                entity_id=str(tid),
                resume_ref="Game.Core/Contracts/EventTypes.cs",
                return_stage="4",
            )
            if check_task_contract_refs._is_ui_task(row):
                _require(
                    len(refs) > 0,
                    "non-empty contractRefs on UI consumer task",
                    {"task_id": tid, "file": view_path},
                    codec.ReasonCode.SEMANTIC_ERROR,
                    entity_id=str(tid),
                    resume_ref=view_path,
                    return_stage="4",
                )
            if check_task_contract_refs._is_core_compute_task(row):
                _require(
                    len(refs) > 0,
                    "non-empty contractRefs on core computation task",
                    {"task_id": tid, "file": view_path},
                    codec.ReasonCode.SEMANTIC_ERROR,
                    entity_id=str(tid),
                    resume_ref=view_path,
                    return_stage="4",
                )
        if len(view_entries) > 1:
            override = consistency_overrides.get(tid)
            if override is not None:
                for view_path, row in view_entries:
                    expected = override.get(view_path)
                    actual_norm = check_task_contract_refs._normalize_refs(row.get("contractRefs"))
                    _require(
                        expected is not None and actual_norm == expected,
                        expected,
                        {"task_id": tid, "file": view_path, "actual": actual_norm},
                        codec.ReasonCode.CONFLICT,
                        entity_id=str(tid),
                        resume_ref=view_path,
                        return_stage="4",
                    )
            else:
                base_refs = check_task_contract_refs._normalize_refs(view_entries[0][1].get("contractRefs"))
                for view_path, row in view_entries[1:]:
                    cur_refs = check_task_contract_refs._normalize_refs(row.get("contractRefs"))
                    _require(
                        cur_refs == base_refs,
                        base_refs,
                        {"task_id": tid, "file": view_path, "actual": cur_refs},
                        codec.ReasonCode.CONFLICT,
                        entity_id=str(tid),
                        resume_ref=view_path,
                        return_stage="4",
                    )

    records.TaskJoinContext(master=master_doc, back=back_rows, gameplay=gameplay_rows).indexes()
    return master_doc, back_rows, gameplay_rows


def _prepare_public_sync_entries(
    *,
    root: Path,
    public_changes: dict[str, Any] | None,
    saved_public_sync: list[dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, bytes], dict[str, str]]:
    """Validate explicit contract/overlay changes and compute deterministic raw-byte sync entries."""
    event_types_rel = "Game.Core/Contracts/EventTypes.cs"
    existing_event_raw = _read_bytes(root, event_types_rel, optional=True)

    # Load baseline event types map from disk (if present).
    event_types_map: dict[str, str] = {}
    if existing_event_raw is not None:
        for match in validate_contracts.EVENT_TYPES_CONST_PATTERN.finditer(
            existing_event_raw.decode("utf-8", errors="strict")
        ):
            event_types_map[match.group(1)] = match.group(2)

    if not public_changes:
        return [], {}, event_types_map

    contracts_changes = list(public_changes.get("contracts") or [])
    overlays_changes = list(public_changes.get("overlays") or [])
    if not contracts_changes and not overlays_changes:
        return [], {}, event_types_map

    saved_by_path = {row["path"]: row for row in (saved_public_sync or [])}
    virtual_files: dict[str, bytes] = {}
    sync_entries: list[dict[str, Any]] = []
    collected_event_constants: list[dict[str, str]] = []
    contract_paths_modified: list[str] = []

    # 1. Process EventTypes additions first so contract validation sees updated EventTypes.
    for item in contracts_changes:
        for ev in item.get("event_constants") or []:
            collected_event_constants.append(ev)

    if collected_event_constants:
        if event_types_rel in saved_by_path:
            saved_row = saved_by_path[event_types_rel]
            disk_now = _read_bytes(root, event_types_rel)
            _require(
                codec.raw_digest(disk_now) == saved_row["after_sha256"],
                saved_row["after_sha256"],
                codec.raw_digest(disk_now),
                codec.ReasonCode.INPUT_STALE,
                entity_id=event_types_rel,
                resume_ref=event_types_rel,
                return_stage="4",
            )
            before_raw = _decode_b64(saved_row["before_base64"])
            before_text = before_raw.decode("utf-8", errors="strict") if before_raw is not None else None
        else:
            before_raw = existing_event_raw
            before_text = before_raw.decode("utf-8", errors="strict") if before_raw is not None else None
        merged_ev_text = _merge_event_types_source(before_text, collected_event_constants)
        merged_ev_raw = merged_ev_text.encode("utf-8")
        # Rebuild updated event_types_map.
        event_types_map = {
            m.group(1): m.group(2)
            for m in validate_contracts.EVENT_TYPES_CONST_PATTERN.finditer(merged_ev_text)
        }
        _validate_contract_source(event_types_rel, merged_ev_text, event_types_map)
        if before_raw != merged_ev_raw:
            virtual_files[event_types_rel] = merged_ev_raw
            sync_entries.append(
                {
                    "path": event_types_rel,
                    "kind": "event_types",
                    "before_sha256": codec.raw_digest(before_raw) if before_raw is not None else None,
                    "before_base64": _encode_b64(before_raw),
                    "after_sha256": codec.raw_digest(merged_ev_raw),
                    "after_base64": _encode_b64(merged_ev_raw),
                }
            )

    # 2. Process explicit contract .cs file changes.
    for item in contracts_changes:
        rel = codec.validate_reference_path(item["path"])
        _require(
            rel.startswith("Game.Core/Contracts/") and rel.endswith(".cs") and rel != event_types_rel,
            "Game.Core/Contracts/**.cs (distinct from EventTypes.cs)",
            rel,
            codec.ReasonCode.INVALID_REFERENCE,
            entity_id=rel,
            resume_ref=rel,
            return_stage="4",
        )
        content_text = item["content"].replace("\r\n", "\n").replace("\r", "\n")
        if not content_text.endswith("\n"):
            content_text += "\n"
        _validate_contract_source(rel, content_text, event_types_map)
        after_raw = content_text.encode("utf-8")

        if rel in saved_by_path:
            saved_row = saved_by_path[rel]
            disk_now = _read_bytes(root, rel)
            _require(
                codec.raw_digest(disk_now) == saved_row["after_sha256"] == codec.raw_digest(after_raw),
                saved_row["after_sha256"],
                codec.raw_digest(disk_now),
                codec.ReasonCode.INPUT_STALE,
                entity_id=rel,
                resume_ref=rel,
                return_stage="4",
            )
            before_raw = _decode_b64(saved_row["before_base64"])
        else:
            before_raw = _read_bytes(root, rel, optional=True)
            if "expected_before_sha256" in item:
                actual_before = codec.raw_digest(before_raw) if before_raw is not None else None
                _require(
                    actual_before == item["expected_before_sha256"],
                    item["expected_before_sha256"],
                    actual_before,
                    codec.ReasonCode.INPUT_STALE,
                    entity_id=rel,
                    resume_ref=rel,
                    return_stage="4",
                )

        virtual_files[rel] = after_raw
        contract_paths_modified.append(rel)
        sync_entries.append(
            {
                "path": rel,
                "kind": "contract",
                "before_sha256": codec.raw_digest(before_raw) if before_raw is not None else None,
                "before_base64": _encode_b64(before_raw),
                "after_sha256": codec.raw_digest(after_raw),
                "after_base64": _encode_b64(after_raw),
            }
        )

    # 3. Process explicit Overlay Markdown changes (sha256-guarded incremental merge preserving tables/prose/code).
    for item in overlays_changes:
        rel = codec.validate_reference_path(item["path"])
        _require(
            _OVERLAY_PATH_RE.fullmatch(rel) is not None,
            "docs/architecture/overlays/<PRD-ID>/08/<page>.md",
            rel,
            codec.ReasonCode.INVALID_REFERENCE,
            entity_id=rel,
            resume_ref=rel,
            return_stage="4",
        )
        if rel in saved_by_path:
            saved_row = saved_by_path[rel]
            before_raw = _decode_b64(saved_row["before_base64"])
            disk_now = _read_bytes(root, rel)
            _require(
                codec.raw_digest(disk_now) == saved_row["after_sha256"],
                saved_row["after_sha256"],
                codec.raw_digest(disk_now),
                codec.ReasonCode.INPUT_STALE,
                entity_id=rel,
                resume_ref=rel,
                return_stage="4",
            )
        else:
            before_raw = _read_bytes(root, rel, optional=True)
            if "expected_before_sha256" in item:
                actual_before = codec.raw_digest(before_raw) if before_raw is not None else None
                _require(
                    actual_before == item["expected_before_sha256"],
                    item["expected_before_sha256"],
                    actual_before,
                    codec.ReasonCode.INPUT_STALE,
                    entity_id=rel,
                    resume_ref=rel,
                    return_stage="4",
                )

        if before_raw is not None:
            _require(
                isinstance(item.get("scaffold_update"), dict),
                "sha256-guarded scaffold_update for existing overlay markdown merge",
                rel,
                codec.ReasonCode.SEMANTIC_ERROR,
                entity_id=rel,
                resume_ref=rel,
                return_stage="4",
            )
            current_md = before_raw.decode("utf-8", errors="strict")
            scaffold = deepcopy(item["scaffold_update"])
            if not str(scaffold.get("expected_sha256") or "").strip():
                _fail(
                    codec.ReasonCode.MISSING_REQUIRED_FIELD,
                    "expected_sha256 in scaffold_update for existing overlay",
                    rel,
                    entity_id=rel,
                    resume_ref=rel,
                    return_stage="4",
                )
            try:
                merged_md = overlay_patch.apply_scaffold_update_to_existing_markdown(
                    current_markdown=current_md,
                    scaffold_update=scaffold,
                )
            except ValueError as err:
                code = (
                    codec.ReasonCode.INPUT_STALE
                    if "hash drifted" in str(err).lower()
                    else codec.ReasonCode.CONFLICT
                )
                _fail(
                    code,
                    "clean sha256-guarded overlay markdown merge preserving tables/prose/code",
                    str(err),
                    entity_id=rel,
                    resume_ref=rel,
                    return_stage="4",
                )
            after_text = merged_md if merged_md.endswith("\n") else merged_md + "\n"
        else:
            _require(
                isinstance(item.get("content"), str) and bool(item["content"].strip()),
                "nonempty UTF-8 markdown content for new overlay page",
                rel,
                codec.ReasonCode.MISSING_REQUIRED_FIELD,
                entity_id=rel,
                resume_ref=rel,
                return_stage="4",
            )
            after_text = item["content"].replace("\r\n", "\n").replace("\r", "\n")
            if not after_text.endswith("\n"):
                after_text += "\n"

        after_raw = after_text.encode("utf-8")
        if rel in saved_by_path:
            _require(
                codec.raw_digest(after_raw) == saved_by_path[rel]["after_sha256"],
                saved_by_path[rel]["after_sha256"],
                codec.raw_digest(after_raw),
                codec.ReasonCode.INPUT_STALE,
                entity_id=rel,
                resume_ref=rel,
                return_stage="4",
            )
        virtual_files[rel] = after_raw
        sync_entries.append(
            {
                "path": rel,
                "kind": "overlay",
                "before_sha256": codec.raw_digest(before_raw) if before_raw is not None else None,
                "before_base64": _encode_b64(before_raw),
                "after_sha256": codec.raw_digest(after_raw),
                "after_base64": _encode_b64(after_raw),
            }
        )

    # 4. Validate overlay backtick path resolution and contract backlinks against post-sync view.
    all_overlay_texts: dict[str, str] = {}
    for md_path in validate_contracts.find_overlay_docs(root):
        rel = md_path.relative_to(root).as_posix()
        if rel in virtual_files:
            all_overlay_texts[rel] = virtual_files[rel].decode("utf-8", errors="strict")
        else:
            all_overlay_texts[rel] = md_path.read_text(encoding="utf-8")
    for rel, raw in virtual_files.items():
        if _OVERLAY_PATH_RE.fullmatch(rel):
            all_overlay_texts[rel] = raw.decode("utf-8", errors="strict")

    for rel in sorted(p for p in virtual_files if _OVERLAY_PATH_RE.fullmatch(p)):
        md_text = all_overlay_texts[rel]
        for ref in validate_overlay_execution.extract_backtick_paths(md_text):
            if not validate_overlay_execution.should_check_path(ref):
                continue
            exists = (ref in virtual_files) or (root / ref).exists()
            _require(
                exists,
                f"existing referenced path {ref} in overlay {rel}",
                ref,
                codec.ReasonCode.UNRESOLVED_REFERENCE,
                entity_id=rel,
                resume_ref=rel,
                return_stage="4",
            )

    if contract_paths_modified:
        referenced_contracts: set[str] = set()
        pattern = re.compile(r"`(Game\.Core/Contracts/[^`]+?\.cs)`")
        for md_text in all_overlay_texts.values():
            for match in pattern.findall(md_text):
                referenced_contracts.add(str(match).replace("\\", "/"))
        for cpath in contract_paths_modified:
            _require(
                cpath in referenced_contracts,
                f"overlay 08 backlink for contract {cpath}",
                cpath,
                codec.ReasonCode.UNRESOLVED_REFERENCE,
                entity_id=cpath,
                resume_ref=cpath,
                return_stage="4",
            )

    sync_entries.sort(key=lambda row: row["path"])
    _validate_public_sync_entries(sync_entries)
    return sync_entries, virtual_files, event_types_map


# ---------------------------------------------------------------------------
# Plan / UI / Dual-State / Four-Part Refinement Builder
# ---------------------------------------------------------------------------


def _plan_ui_policy(plan: dict[str, Any]) -> tuple[bool, list[str], dict[str, dict[str, Any]]]:
    """Derive 3B UI applicability, non-UI rationales, and four-part applicability from committed 3B plan."""
    flows = plan["definitions"]["flows"]
    ui_applicable = False
    no_ui_rationales: list[str] = []
    merged_parts: dict[str, dict[str, Any]] = {}

    for kind in PART_KINDS:
        merged_parts[kind] = {
            "kind": kind,
            "applicability": "not_applicable",
            "rationale": f"{kind} is not applicable for this plan.",
            "responsibilities": [],
        }

    for flow in flows:
        if "ui" in flow:
            ui_obj = flow["ui"]
            if ui_obj.get("applicability") == "applicable":
                ui_applicable = True
            else:
                rat = str(ui_obj.get("rationale") or "").strip()
                if rat:
                    no_ui_rationales.append(rat)
        for part in flow.get("parts", []):
            kind = part["kind"]
            if part["applicability"] == "applicable":
                if kind == "scene" and "ui" not in flow:
                    ui_applicable = True
                slot = merged_parts[kind]
                slot["applicability"] = "applicable"
                slot["rationale"] = part["rationale"]
                for resp in part.get("responsibilities", []):
                    if resp not in slot["responsibilities"]:
                        slot["responsibilities"].append(resp)
            else:
                if kind == "scene" and "ui" not in flow:
                    rat = str(part.get("rationale") or "").strip()
                    if rat:
                        no_ui_rationales.append(rat)
                if merged_parts[kind]["applicability"] != "applicable":
                    merged_parts[kind]["rationale"] = part["rationale"]

    return ui_applicable, no_ui_rationales, merged_parts


def _check_source_alignment(root: Path, plan: dict[str, Any], prior_binding: dict[str, Any] | None = None) -> None:
    """Verify 3A source_identity and reject source_gap dispositions on plan requirements."""
    src = plan["source_identity"]
    for ref_key in ("manifest_ref", "ledger_ref"):
        owned = src[ref_key]
        for frow in owned["files"]:
            rel = frow["path"]
            if rel.startswith("logs/"):
                continue
            raw = _read_bytes(root, rel, optional=True)
            _require(
                raw is not None and codec.raw_digest(raw) == frow["raw_digest"],
                frow["raw_digest"],
                codec.raw_digest(raw) if raw is not None else None,
                codec.ReasonCode.INPUT_STALE,
                entity_id=plan["plan_id"],
                resume_ref=rel,
                return_stage="3A",
            )
            if ref_key == "manifest_ref" and rel.endswith(".json"):
                manifest_doc = codec.strict_json_loads(raw)
                if type(manifest_doc) is dict and isinstance(manifest_doc.get("sources"), list):
                    for srow in manifest_doc["sources"]:
                        if (
                            type(srow) is dict
                            and isinstance(srow.get("path"), str)
                            and isinstance(srow.get("sha256"), str)
                        ):
                            s_rel = srow["path"]
                            if s_rel.startswith("logs/"):
                                continue
                            s_raw = _read_bytes(root, s_rel, optional=True)
                            if s_raw is not None:
                                _require(
                                    codec.raw_digest(s_raw) == srow["sha256"],
                                    srow["sha256"],
                                    codec.raw_digest(s_raw),
                                    codec.ReasonCode.INPUT_STALE,
                                    entity_id=plan["plan_id"],
                                    resume_ref=s_rel,
                                    return_stage="3A",
                                )
    if prior_binding is not None:
        req_verif = {row["requirement_id"]: row for row in plan["requirement_verification"]}
        for mapping in prior_binding.get("task_mappings", []):
            for rid in mapping.get("requirement_ids", []):
                verif = req_verif.get(rid)
                _require(
                    verif is not None and verif.get("disposition") != "source_gap",
                    "resolved non-source_gap requirement disposition before Chapter 4",
                    verif.get("disposition") if verif is not None else None,
                    codec.ReasonCode.SEMANTIC_ERROR,
                    entity_id=rid,
                    resume_ref=records.BASE + f"plans/{plan['plan_id']}/{plan['revision']}.json",
                    return_stage="3A",
                )


def _build_stage4_binding(
    *,
    root: Path,
    request: dict[str, Any],
    plan: dict[str, Any],
    plan_ref: dict[str, Any],
    prior_binding: dict[str, Any],
    catalog: dict[str, Any],
    binding_revision: int,
    virtual_files: dict[str, bytes],
    event_types_map: dict[str, str],
) -> tuple[dict[str, Any], bool]:
    """Validate all Stage-4 rules and construct formal newrouge.b-route-binding.v1 (stage='4')."""
    plan_id = plan["plan_id"]
    req_ids_in_plan = {row["requirement_id"] for row in plan["requirements"]}
    req_verif_by_id = {row["requirement_id"]: row for row in plan["requirement_verification"]}
    cmd_defs = {row["id"]: row for row in plan["definitions"]["commands"]}
    state_defs = {row["id"]: row for row in plan["definitions"]["states"]}
    flow_owners = {
        row["definition_id"]: row
        for row in catalog["definition_owners"]
        if row["kind"] == "flow"
    }
    catalog_cmd_owners = {
        row["definition_id"]: row
        for row in catalog["definition_owners"]
        if row["kind"] == "command"
    }
    catalog_state_owners = {
        row["definition_id"]: row
        for row in catalog["definition_owners"]
        if row["kind"] == "state"
    }

    # Validate upstream 3B flow.state_owners uniqueness and alignment with catalog.definition_owners.
    flow_state_owners: dict[str, set[tuple[str, int]]] = {}
    for flow in plan["definitions"]["flows"]:
        for so in flow.get("state_owners") or []:
            if so.get("kind") == "state":
                flow_state_owners.setdefault(so["definition_id"], set()).add(
                    (so["owner_plan_id"], so["owner_revision"])
                )
    for sid, owner_pairs in flow_state_owners.items():
        _require(
            len(owner_pairs) == 1,
            f"unique 3B flow.state_owners entry for state {sid}",
            sorted(owner_pairs),
            codec.ReasonCode.DUPLICATE_OWNER,
            entity_id=sid,
            resume_ref=plan_ref["path"],
            return_stage="3B",
        )
        owner_pid, owner_rev = next(iter(owner_pairs))
        cat_owner = catalog_state_owners.get(sid)
        _require(
            cat_owner is not None
            and cat_owner["plan_ref"]["entity_id"] == owner_pid
            and cat_owner["plan_ref"]["revision"] == owner_rev,
            "3B flow.state_owners aligned with catalog.definition_owners",
            {"state_id": sid, "flow_owner": [owner_pid, owner_rev], "catalog_owner": cat_owner},
            codec.ReasonCode.CONFLICT,
            entity_id=sid,
            resume_ref=plan_ref["path"],
            return_stage="3B",
        )
    for sid in state_defs:
        cat_owner = catalog_state_owners.get(sid)
        _require(
            cat_owner is not None and cat_owner["plan_ref"]["entity_id"] == plan_id,
            f"catalog.definition_owners state owner matching plan {plan_id}",
            cat_owner,
            codec.ReasonCode.MAPPING_MISMATCH,
            entity_id=sid,
            resume_ref=records.CATALOG_PATH,
            return_stage="3B",
        )
        if plan["definitions"]["flows"]:
            _require(
                sid in flow_state_owners and (plan_id, plan["revision"]) in flow_state_owners[sid],
                f"3B flow.state_owners declaring state {sid} owned by {plan_id}@{plan['revision']}",
                sorted(flow_state_owners.get(sid, set())),
                codec.ReasonCode.SEMANTIC_ERROR,
                entity_id=sid,
                resume_ref=plan_ref["path"],
                return_stage="3B",
            )

    # 1. Conserve exact 3C/4 task_id set.
    prior_mappings = deepcopy(prior_binding["task_mappings"])
    _require(
        bool(prior_mappings),
        "nonempty prior 3C/4 task_mappings",
        prior_binding["binding_revision"],
        codec.ReasonCode.MAPPING_MISMATCH,
        entity_id=plan_id,
        return_stage="3C",
    )
    conserved_task_ids = sorted(row["task_id"] for row in prior_mappings)
    conserved_task_set = set(conserved_task_ids)
    if "task_ids" in request and request["task_ids"] is not None:
        req_tids = sorted(set(request["task_ids"]))
        _require(
            req_tids == conserved_task_ids,
            conserved_task_ids,
            req_tids,
            codec.ReasonCode.MAPPING_MISMATCH,
            entity_id=plan_id,
            return_stage="3C",
        )

    mapping_by_tid = {row["task_id"]: row for row in prior_mappings}

    # Check no mapped requirement is source_gap (3A attribution).
    for row in prior_mappings:
        for rid in row["requirement_ids"]:
            _require(
                rid in req_ids_in_plan,
                "requirement declared in committed 3B plan",
                rid,
                codec.ReasonCode.UNRESOLVED_REFERENCE,
                entity_id=rid,
                resume_ref=plan_ref["path"],
                return_stage="3A",
            )
            verif = req_verif_by_id.get(rid)
            _require(
                verif is not None and verif["disposition"] != "source_gap",
                "resolved non-source_gap requirement disposition",
                verif["disposition"] if verif else None,
                codec.ReasonCode.SEMANTIC_ERROR,
                entity_id=rid,
                resume_ref=plan_ref["path"],
                return_stage="3A",
            )

    # 2. Validate UI slice & human zones against 3B plan.
    plan_ui_applicable, plan_no_ui_rationales, parts_map = _plan_ui_policy(plan)
    # Also incorporate prior binding parts if plan had zero flows (legal non-Flow).
    if not plan["definitions"]["flows"]:
        for p in prior_binding.get("parts", []):
            parts_map[p["kind"]] = deepcopy(p)
            if p["kind"] == "scene" and p["applicability"] == "applicable":
                plan_ui_applicable = True
            elif p["kind"] == "scene" and p["applicability"] == "not_applicable" and p.get("rationale"):
                plan_no_ui_rationales.append(p["rationale"])

    ui_req = request.get("ui_slice")
    if ui_req is None:
        if plan_ui_applicable:
            _fail(
                codec.ReasonCode.MISSING_REQUIRED_FIELD,
                "explicit ui_slice specification for UI-applicable 3B flow",
                None,
                entity_id=plan_id,
                resume_ref=plan_ref["path"],
                return_stage="4",
            )
        _require(
            bool(plan_no_ui_rationales),
            "3B rationale for non-UI flow",
            plan_id,
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=plan_id,
            resume_ref=plan_ref["path"],
            return_stage="3B",
        )
        ui_meta = {
            "applicable": False,
            "rationale": plan_no_ui_rationales[0],
            "inputs": [],
            "methods": [],
            "wiring": [],
            "human_zones": [],
            "chapter7_required": False,
        }
        chapter7_required = False
    elif ui_req["applicable"] is False:
        _require(
            not plan_ui_applicable and bool(plan_no_ui_rationales),
            "3B explicit rationale when declaring UI not applicable (undeclared UI exemption forbidden)",
            {"plan_ui_applicable": plan_ui_applicable, "plan_no_ui_rationales": plan_no_ui_rationales},
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=plan_id,
            resume_ref=plan_ref["path"],
            return_stage="3B",
        )
        ui_meta = {
            "applicable": False,
            "rationale": ui_req.get("rationale") or plan_no_ui_rationales[0],
            "inputs": [],
            "methods": [],
            "wiring": [],
            "human_zones": [],
            "chapter7_required": False,
        }
        chapter7_required = False
    else:
        inputs = list(ui_req.get("inputs") or [])
        methods = list(ui_req.get("methods") or [])
        wiring = list(ui_req.get("wiring") or [])
        human_zones = list(ui_req.get("human_zones") or [])
        modified_zones = list(ui_req.get("modified_zones") or [])
        direct_writes = list(ui_req.get("direct_state_writes") or [])

        _require(
            bool(inputs) and bool(methods) and bool(wiring),
            "nonempty UI inputs, methods, and wiring lists",
            {"inputs": inputs, "methods": methods, "wiring": wiring},
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=plan_id,
            return_stage="4",
        )
        missing_zones = [z for z in REQUIRED_HUMAN_ZONES if z not in human_zones]
        _require(
            not missing_zones,
            list(REQUIRED_HUMAN_ZONES),
            {"human_zones": human_zones, "missing": missing_zones},
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=plan_id,
            return_stage="4",
        )
        encroached = sorted(set(modified_zones) & set(REQUIRED_HUMAN_ZONES))
        _require(
            not encroached,
            "zero modifications encroaching on human-owned zones (layout, art, animation)",
            {"encroached_zones": encroached},
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=plan_id,
            return_stage="4",
        )
        _require(
            not direct_writes,
            "zero direct state writes from UI (must route through production commands)",
            {"direct_state_writes": direct_writes},
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=plan_id,
            return_stage="4",
        )
        ui_meta = {
            "applicable": True,
            "rationale": ui_req.get("rationale") or "UI slice governed with human-owned layout/art/animation zones.",
            "inputs": inputs,
            "methods": methods,
            "wiring": wiring,
            "human_zones": sorted(set(human_zones)),
            "chapter7_required": True,
        }
        chapter7_required = True
        # Ensure scene part is applicable when UI is applicable.
        if parts_map["scene"]["applicability"] != "applicable":
            parts_map["scene"]["applicability"] = "applicable"
            parts_map["scene"]["rationale"] = ui_meta["rationale"]
            if not parts_map["scene"]["responsibilities"]:
                parts_map["scene"]["responsibilities"].append("Governed UI scene entry/return and wiring.")

    # 3. Validate dual-state helper.
    def _validate_dual_state(
        *,
        obj_id: str,
        kind: str,
        item: dict[str, Any],
        lifecycle_payload: dict[str, Any],
    ) -> dict[str, Any]:
        resp_tids = list(item["responsible_task_ids"])
        _require(
            bool(resp_tids),
            "nonempty responsible_task_ids",
            obj_id,
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=obj_id,
            return_stage="4",
        )
        unknown_tids = [t for t in resp_tids if t not in conserved_task_set]
        _require(
            not unknown_tids,
            conserved_task_ids,
            unknown_tids,
            codec.ReasonCode.MAPPING_MISMATCH,
            entity_id=obj_id,
            return_stage="3C",
        )
        availability = item["availability"]
        expected_type = item["expected_type"]
        target_ref = deepcopy(item.get("target_ref"))
        later_checks = list(item.get("later_checks") or [])
        required_checks = REQUIRED_LATER_CHECKS[kind]

        if availability == "planned":
            _require(
                item.get("claimed_passed") is not True,
                "planned implementation object must not claim passed/implemented",
                obj_id,
                codec.ReasonCode.SEMANTIC_ERROR,
                entity_id=obj_id,
                return_stage="4",
            )
            missing_checks = [c for c in required_checks if c not in later_checks]
            _require(
                bool(later_checks) and not missing_checks,
                list(required_checks),
                {"later_checks": later_checks, "missing": missing_checks},
                codec.ReasonCode.SEMANTIC_ERROR,
                entity_id=obj_id,
                return_stage="4",
            )
            if target_ref is not None:
                # Planned target_ref, if provided, must not point to a fake or nonexistent artifact.
                for frow in target_ref["files"]:
                    rel = frow["path"]
                    raw = virtual_files.get(rel) if rel in virtual_files else _read_bytes(root, rel, optional=True)
                    _require(
                        raw is not None and codec.raw_digest(raw) == frow["raw_digest"],
                        "null target_ref for planned object or real unchanged reference",
                        rel,
                        codec.ReasonCode.SEMANTIC_ERROR,
                        entity_id=obj_id,
                        resume_ref=rel,
                        return_stage="4",
                    )
                    if rel.endswith((".tscn", ".tres", ".cs")):
                        _require(
                            _FAKE_NODE_RE.search(raw.decode("utf-8", errors="replace")) is None,
                            "no fake node or stub artifact",
                            rel,
                            codec.ReasonCode.SEMANTIC_ERROR,
                            entity_id=obj_id,
                            resume_ref=rel,
                            return_stage="4",
                        )
        else:
            _require(
                target_ref is not None,
                "non-null OwnedRef target_ref for existing implementation object",
                obj_id,
                codec.ReasonCode.MISSING_REQUIRED_FIELD,
                entity_id=obj_id,
                return_stage="4",
            )
            if not later_checks:
                later_checks = list(required_checks)
            for frow in target_ref["files"]:
                rel = codec.validate_reference_path(frow["path"])
                raw = virtual_files.get(rel) if rel in virtual_files else _read_bytes(root, rel, optional=True)
                _require(
                    raw is not None,
                    f"existing file {rel} for existing object {obj_id}",
                    None,
                    codec.ReasonCode.FILE_NOT_FOUND,
                    entity_id=obj_id,
                    resume_ref=rel,
                    return_stage="4",
                )
                actual_sha = codec.raw_digest(raw)
                _require(
                    actual_sha == frow["raw_digest"],
                    frow["raw_digest"],
                    actual_sha,
                    codec.ReasonCode.DIGEST_MISMATCH,
                    entity_id=obj_id,
                    resume_ref=rel,
                    return_stage="4",
                )
                _verify_existing_asset_content(
                    obj_id=obj_id,
                    kind=kind,
                    expected_type=expected_type,
                    rel_path=rel,
                    raw=raw,
                    event_types_map=event_types_map,
                )

        lifecycle_str = STAGE4_LIFECYCLE_PREFIX + _compact_json(lifecycle_payload)
        return {
            "id": obj_id,
            "kind": kind,
            "availability": availability,
            "responsible_task_ids": sorted(set(resp_tids)),
            "expected_type": expected_type,
            "lifecycle": lifecycle_str,
            "target_ref": target_ref,
            "later_checks": sorted(set(later_checks)),
        }

    # 4. Validate commands, read-only states (single owner!), adapters, bindings, scenes/resources.
    impl_objects: list[dict[str, Any]] = []
    seen_obj_ids: set[str] = set()
    state_single_owners: dict[str, str] = {}
    command_ids_refined: set[str] = set()
    state_ids_refined: set[str] = set()

    def _add_obj(obj: dict[str, Any]) -> None:
        _require(
            obj["id"] not in seen_obj_ids,
            "unique implementation_objects id",
            obj["id"],
            codec.ReasonCode.CONFLICT,
            entity_id=obj["id"],
            return_stage="4",
        )
        seen_obj_ids.add(obj["id"])
        impl_objects.append(obj)

    for cmd in request.get("commands") or []:
        cid = cmd["id"]
        _require(
            cid in cmd_defs,
            "command declared in committed 3B plan definitions.commands",
            cid,
            codec.ReasonCode.UNRESOLVED_REFERENCE,
            entity_id=cid,
            resume_ref=plan_ref["path"],
            return_stage="3B",
        )
        _require(
            bool(cmd["preconditions"]) and bool(cmd["postconditions"]) and bool(cmd["invariants"]),
            "nonempty preconditions, postconditions, and invariants on production command",
            cid,
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=cid,
            return_stage="4",
        )
        # integration_only_owner cannot invent new runtime APIs when no producer task owns the command.
        resp_tids = list(cmd["responsible_task_ids"])
        if resp_tids and all(t in mapping_by_tid for t in resp_tids):
            all_integration_only = all(
                set(mapping_by_tid[t]["roles"]) == {"integration_only_owner"} for t in resp_tids
            )
            if all_integration_only and cmd["availability"] == "planned":
                _fail(
                    codec.ReasonCode.SEMANTIC_ERROR,
                    "integration_only_owner must not invent new runtime API (requires producer task or existing API)",
                    {"command_id": cid, "responsible_task_ids": resp_tids},
                    entity_id=cid,
                    return_stage="3B",
                )
        command_ids_refined.add(cid)
        _add_obj(
            _validate_dual_state(
                obj_id=cid,
                kind="command",
                item=cmd,
                lifecycle_payload={
                    "kind": "command",
                    "owner": cmd["owner"],
                    "preconditions": list(cmd["preconditions"]),
                    "postconditions": list(cmd["postconditions"]),
                    "invariants": list(cmd["invariants"]),
                    "contract_ref": cmd.get("contract_ref"),
                    "handoff": cmd.get("handoff") or f"command:{cid}->{cmd['owner']}",
                },
            )
        )

    for st in request.get("read_only_states") or []:
        sid = st["id"]
        _require(
            sid in state_defs,
            "state declared in committed 3B plan definitions.states",
            sid,
            codec.ReasonCode.UNRESOLVED_REFERENCE,
            entity_id=sid,
            resume_ref=plan_ref["path"],
            return_stage="3B",
        )
        owner = st["single_owner"]
        if sid in state_single_owners:
            _require(
                state_single_owners[sid] == owner,
                f"single unique owner {state_single_owners[sid]} for state {sid}",
                owner,
                codec.ReasonCode.DUPLICATE_OWNER,
                entity_id=sid,
                return_stage="3B",
            )
        state_single_owners[sid] = owner
        _require(
            bool(st["read_only_views"]),
            "nonempty read_only_views on read-only state",
            sid,
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=sid,
            return_stage="4",
        )
        forbidden_writers = sorted(set(st.get("forbidden_direct_writers") or ["adapter", "ui"]))
        _require(
            owner.strip() and owner.strip().casefold() not in {w.casefold() for w in forbidden_writers},
            f"non-empty authoritative single_owner outside forbidden_direct_writers for state {sid}",
            owner,
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=sid,
            return_stage="4",
        )
        state_ids_refined.add(sid)
        _add_obj(
            _validate_dual_state(
                obj_id=sid,
                kind="read_only_state",
                item=st,
                lifecycle_payload={
                    "kind": "read_only_state",
                    "single_owner": owner,
                    "read_only_views": list(st["read_only_views"]),
                    "forbidden_direct_writers": forbidden_writers,
                    "contract_ref": st.get("contract_ref"),
                    "handoff": st.get("handoff") or f"readonly:{sid}@{owner}",
                },
            )
        )

    for adp in request.get("adapters") or []:
        aid = adp["id"]
        _require(
            adp.get("arbitrates_domain_rules") is not True,
            "thin C# adapter must not arbitrate domain rules",
            aid,
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=aid,
            return_stage="4",
        )
        _require(
            adp.get("direct_state_mutation") is not True,
            "thin C# adapter must not directly mutate domain state",
            aid,
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=aid,
            return_stage="4",
        )
        _add_obj(
            _validate_dual_state(
                obj_id=aid,
                kind="adapter",
                item=adp,
                lifecycle_payload={
                    "kind": "adapter",
                    "dependencies": list(adp["dependencies"]),
                    "lifecycle": adp["lifecycle"],
                    "forbidden_arbitration": True,
                    "handoff": adp.get("handoff") or f"adapter:{aid}",
                },
            )
        )

    for bnd in request.get("bindings") or []:
        bid = bnd["id"]
        _require(
            bool(bnd["control_to_target"]),
            "nonempty control_to_target mapping on binding object",
            bid,
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=bid,
            return_stage="4",
        )
        for c_entry in bnd["control_to_target"]:
            _require(
                c_entry.get("direct_state_write") is not True,
                "control binding must not directly write domain state",
                c_entry,
                codec.ReasonCode.SEMANTIC_ERROR,
                entity_id=bid,
                return_stage="4",
            )
        _add_obj(
            _validate_dual_state(
                obj_id=bid,
                kind="binding",
                item=bnd,
                lifecycle_payload={
                    "kind": "binding",
                    "control_to_target": deepcopy(bnd["control_to_target"]),
                    "handoff": bnd.get("handoff") or f"binding:{bid}",
                },
            )
        )

    for sr in request.get("scenes_and_resources") or []:
        srid = sr["id"]
        sr_kind = sr["kind"]
        _add_obj(
            _validate_dual_state(
                obj_id=srid,
                kind=sr_kind,
                item=sr,
                lifecycle_payload={
                    "kind": sr_kind,
                    "scene_entry": list(sr.get("scene_entry") or []),
                    "scene_return": list(sr.get("scene_return") or []),
                    "handoff": sr.get("handoff") or f"{sr_kind}:{srid}",
                },
            )
        )

    # Retain any prior implementation objects not superseded by id (preserving cumulative obligations).
    for prior_obj in prior_binding.get("implementation_objects", []):
        if prior_obj["id"] not in seen_obj_ids:
            impl_objects.append(deepcopy(prior_obj))
            seen_obj_ids.add(prior_obj["id"])
    impl_objects.sort(key=lambda item: item["id"])

    # Enforce complete Stage-4 coverage of EVERY 3B plan command and state definition.
    all_cmd_ids_refined = command_ids_refined | {obj["id"] for obj in impl_objects if obj["kind"] == "command"}
    missing_cmds = sorted(set(cmd_defs) - all_cmd_ids_refined)
    _require(
        not missing_cmds,
        "all 3B plan definitions.commands covered by Stage-4 commands",
        {"missing_commands": missing_cmds},
        codec.ReasonCode.SEMANTIC_ERROR,
        entity_id=missing_cmds[0] if missing_cmds else plan_id,
        resume_ref=plan_ref["path"],
        return_stage="4",
    )
    all_state_ids_refined = state_ids_refined | {obj["id"] for obj in impl_objects if obj["kind"] == "read_only_state"}
    missing_states = sorted(set(state_defs) - all_state_ids_refined)
    _require(
        not missing_states,
        "all 3B plan definitions.states covered by Stage-4 read_only_states",
        {"missing_states": missing_states},
        codec.ReasonCode.SEMANTIC_ERROR,
        entity_id=missing_states[0] if missing_states else plan_id,
        resume_ref=plan_ref["path"],
        return_stage="4",
    )

    # Enforce referential integrity on ControlBindingEntry (via_command, reads_state, target_resource, target_object).
    active_cmd_ids = all_cmd_ids_refined | set(catalog_cmd_owners)
    active_state_ids = all_state_ids_refined | set(catalog_state_owners)
    declared_obj_ids = {obj["id"] for obj in impl_objects}
    declared_ref_paths = {
        frow["path"]
        for obj in impl_objects
        if obj.get("target_ref")
        for frow in obj["target_ref"]["files"]
    }
    declared_type_tokens: set[str] = set()
    for obj in impl_objects:
        etype = str(obj.get("expected_type") or "").strip()
        if etype:
            declared_type_tokens.add(etype)
            base_t = etype.split("<", 1)[0].strip()
            declared_type_tokens.add(base_t)
            t_parts = [p for p in re.split(r"[.:/]", base_t) if p]
            if t_parts:
                declared_type_tokens.add(t_parts[-1])

    for bnd in request.get("bindings") or []:
        bid = bnd["id"]
        for c_entry in bnd["control_to_target"]:
            via_cmd = c_entry.get("via_command")
            if via_cmd is not None:
                _require(
                    via_cmd in active_cmd_ids,
                    "ControlBindingEntry.via_command resolving to refined/active command ID",
                    {"binding_id": bid, "via_command": via_cmd},
                    codec.ReasonCode.UNRESOLVED_REFERENCE,
                    entity_id=bid,
                    return_stage="4",
                )
            reads_st = c_entry.get("reads_state")
            if reads_st is not None:
                st_items = reads_st if isinstance(reads_st, list) else [reads_st]
                for st_ref in st_items:
                    _require(
                        st_ref in active_state_ids,
                        "ControlBindingEntry.reads_state resolving to refined/active state ID",
                        {"binding_id": bid, "reads_state": st_ref},
                        codec.ReasonCode.UNRESOLVED_REFERENCE,
                        entity_id=bid,
                        return_stage="4",
                    )
            t_res = c_entry.get("target_resource")
            if t_res is not None:
                res_ok = (
                    t_res in declared_obj_ids
                    or t_res in declared_ref_paths
                    or t_res in virtual_files
                    or (_read_bytes(root, t_res, optional=True) is not None if "/" in t_res else False)
                )
                _require(
                    res_ok,
                    "ControlBindingEntry.target_resource resolving to declared implementation_object or verified asset",
                    {"binding_id": bid, "target_resource": t_res},
                    codec.ReasonCode.UNRESOLVED_REFERENCE,
                    entity_id=bid,
                    return_stage="4",
                )
            t_obj = c_entry.get("target_object")
            if t_obj is not None:
                t_obj_head = t_obj.split(".", 1)[0].split(":", 1)[0].strip()
                obj_ok = (
                    t_obj in declared_obj_ids
                    or t_obj in declared_ref_paths
                    or t_obj in declared_type_tokens
                    or t_obj_head in declared_obj_ids
                    or t_obj_head in declared_type_tokens
                    or t_obj in virtual_files
                    or (_read_bytes(root, t_obj, optional=True) is not None if "/" in t_obj else False)
                )
                _require(
                    obj_ok,
                    "ControlBindingEntry.target_object resolving to declared implementation_object or verified asset",
                    {"binding_id": bid, "target_object": t_obj},
                    codec.ReasonCode.UNRESOLVED_REFERENCE,
                    entity_id=bid,
                    return_stage="4",
                )

    # 5. Build 4-part list (all 4 parts in binding.parts), stripping prior stage4:* tags for iterative idempotency.
    stage4_prefixes = (STAGE4_LIFECYCLE_PREFIX, STAGE4_PART_PREFIX, STAGE4_UI_PREFIX, STAGE4_OBL_PREFIX)
    for part in parts_map.values():
        rat = part["rationale"]
        for pfx in stage4_prefixes:
            rat = rat.split(" | " + pfx, 1)[0].strip()
        part["rationale"] = rat
        cleaned_resps: list[str] = []
        for resp in part.get("responsibilities", []):
            if any(resp.startswith(pfx) for pfx in stage4_prefixes):
                continue
            stripped_resp = resp
            for pfx in stage4_prefixes:
                stripped_resp = stripped_resp.split(" | " + pfx, 1)[0].strip()
            if stripped_resp and stripped_resp not in cleaned_resps:
                cleaned_resps.append(stripped_resp)
        part["responsibilities"] = cleaned_resps

    ui_tag = STAGE4_UI_PREFIX + _compact_json(ui_meta)
    scene_part = parts_map["scene"]
    if scene_part["applicability"] == "applicable":
        if ui_tag not in scene_part["responsibilities"]:
            scene_part["responsibilities"].append(ui_tag)
    else:
        base_rat = scene_part["rationale"].split(" | " + STAGE4_UI_PREFIX, 1)[0]
        scene_part["rationale"] = f"{base_rat} | {ui_tag}"

    ordered_parts = [parts_map[kind] for kind in PART_KINDS]
    applicable_part_kinds = {p["kind"] for p in ordered_parts if p["applicability"] == "applicable"}

    # Apply optional task_part_kinds overrides (still enforcing single-task applicable subset).
    task_part_overrides = request.get("task_part_kinds") or {}
    for tid_str, pkinds in task_part_overrides.items():
        tid = int(tid_str)
        _require(
            tid in mapping_by_tid,
            conserved_task_ids,
            tid,
            codec.ReasonCode.MAPPING_MISMATCH,
            entity_id=str(tid),
            return_stage="3C",
        )
        invalid_pk = [k for k in pkinds if k not in applicable_part_kinds]
        _require(
            not invalid_pk,
            sorted(applicable_part_kinds),
            invalid_pk,
            codec.ReasonCode.MAPPING_MISMATCH,
            entity_id=str(tid),
            return_stage="4",
        )
        mapping_by_tid[tid]["part_kinds"] = sorted(set(pkinds))

    # Also keep existing mapping part_kinds valid against applicable_part_kinds.
    covered_part_kinds: set[str] = set()
    for tid in conserved_task_ids:
        row = mapping_by_tid[tid]
        row["part_kinds"] = sorted(k for k in row["part_kinds"] if k in applicable_part_kinds)
        covered_part_kinds.update(row["part_kinds"])
    # Also count parts explicitly covered by refined implementation_objects.
    kind_to_part = {
        "command": "domain_rules",
        "read_only_state": "domain_rules",
        "adapter": "csharp_adapter",
        "binding": "binding",
        "scene": "scene",
        "resource": "binding",
    }
    for obj in impl_objects:
        mapped_part = kind_to_part[obj["kind"]]
        if mapped_part in applicable_part_kinds:
            covered_part_kinds.add(mapped_part)
            for tid in obj["responsible_task_ids"]:
                if mapped_part not in mapping_by_tid[tid]["part_kinds"]:
                    mapping_by_tid[tid]["part_kinds"] = sorted(set(mapping_by_tid[tid]["part_kinds"]) | {mapped_part})

    orphan_parts = sorted(applicable_part_kinds - covered_part_kinds)
    _require(
        not orphan_parts,
        "zero orphan applicable four-part responsibilities",
        {"orphan_parts": orphan_parts},
        codec.ReasonCode.SEMANTIC_ERROR,
        entity_id=plan_id,
        return_stage="4",
    )

    # 6. Merge and validate test obligations.
    obligations_by_id: dict[str, dict[str, Any]] = {
        row["id"]: deepcopy(row) for row in prior_binding.get("obligations", [])
    }
    for obl in request.get("obligations") or []:
        oid = obl["id"]
        for rid in obl["requirement_ids"]:
            _require(
                rid in req_ids_in_plan,
                "requirement declared in committed 3B plan",
                rid,
                codec.ReasonCode.UNRESOLVED_REFERENCE,
                entity_id=rid,
                resume_ref=plan_ref["path"],
                return_stage="3A",
            )
        for fid in obl["flow_ids"]:
            _require(
                fid in flow_owners,
                "flow declared in catalog definition_owners",
                fid,
                codec.ReasonCode.UNRESOLVED_REFERENCE,
                entity_id=fid,
                resume_ref=records.CATALOG_PATH,
                return_stage="3B",
            )
        obl_tids = list(obl.get("task_ids") or [])
        for tid in obl_tids:
            _require(
                tid in conserved_task_set,
                conserved_task_ids,
                tid,
                codec.ReasonCode.MAPPING_MISMATCH,
                entity_id=oid,
                return_stage="3C",
            )
            if oid not in mapping_by_tid[tid]["obligation_ids"]:
                mapping_by_tid[tid]["obligation_ids"] = sorted(set(mapping_by_tid[tid]["obligation_ids"]) | {oid})
        obl_meta = {"stage": "4", "task_ids": sorted(set(obl_tids)), "test_ids": sorted(set(obl["test_ids"]))}
        resp_text = obl["responsibility"].split(" | " + STAGE4_OBL_PREFIX, 1)[0]
        obligations_by_id[oid] = {
            "id": oid,
            "requirement_ids": sorted(set(obl["requirement_ids"])),
            "flow_ids": sorted(set(obl["flow_ids"])),
            "test_ids": sorted(set(obl["test_ids"])),
            "responsibility": f"{resp_text} | {STAGE4_OBL_PREFIX}{_compact_json(obl_meta)}",
            "verification_refs": deepcopy(obl.get("verification_refs") or []),
        }

    manifest_refs = deepcopy(prior_binding.get("manifest_refs", []))
    for mref in request.get("manifest_refs") or []:
        if mref not in manifest_refs:
            manifest_refs.append(deepcopy(mref))

    other_verif_refs = deepcopy(prior_binding.get("other_verification_refs", []))
    for oref in request.get("other_verification_refs") or []:
        if oref not in other_verif_refs:
            other_verif_refs.append(deepcopy(oref))

    stage4_binding = {
        "schema_version": "newrouge.b-route-binding.v1",
        "plan_id": plan_id,
        "binding_revision": binding_revision,
        "plan_ref": deepcopy(plan_ref),
        "stage": "4",
        "task_mappings": [mapping_by_tid[tid] for tid in conserved_task_ids],
        "parts": ordered_parts,
        "implementation_objects": impl_objects,
        "obligations": [obligations_by_id[k] for k in sorted(obligations_by_id)],
        "manifest_refs": manifest_refs,
        "other_verification_refs": other_verif_refs,
    }
    return stage4_binding, chapter7_required


def _build_updated_origins(
    *,
    current_origins: dict[str, Any],
    plan_id: str,
    plan_ref: dict[str, Any],
    binding_ref: dict[str, Any],
    conserved_task_ids: list[int],
) -> dict[str, Any]:
    """Update task-origins.v1.json for plan_id while strictly preserving ALL other plans' refs on shared Tasks."""
    origins_by_tid = {row["task_id"]: deepcopy(row) for row in current_origins["tasks"]}
    for tid in conserved_task_ids:
        _require(
            tid in origins_by_tid,
            f"existing task-origins.v1.json entry for B-route Task {tid}",
            tid,
            codec.ReasonCode.MAPPING_MISMATCH,
            entity_id=str(tid),
            resume_ref=records.BASE + "task-origins.v1.json",
            return_stage="3C",
        )
        row = origins_by_tid[tid]
        # Preserve EVERY other plan's plan_refs and binding_refs verbatim; replace only plan_id's binding_ref.
        other_plans = [p for p in row["plan_refs"] if p["entity_id"] != plan_id]
        other_bindings = [b for b in row["binding_refs"] if b["entity_id"] != plan_id]
        row["plan_refs"] = other_plans + [deepcopy(plan_ref)]
        row["binding_refs"] = other_bindings + [deepcopy(binding_ref)]

    updated = {
        "schema_version": "newrouge.b-route-origins.v1",
        "origins_id": "task-origins",
        "revision": int(current_origins["revision"]) + 1,
        "tasks": [origins_by_tid[tid] for tid in sorted(origins_by_tid)],
        "frozen_legacy_refs": deepcopy(current_origins.get("frozen_legacy_refs", [])),
    }
    origins_path = records.BASE + "task-origins.v1.json"
    checked = records.validate_record(updated, path=origins_path)
    if not checked.ok:
        raise codec.CodecError(checked.diagnostic)
    return updated


def _collect_plan_authority_files(snapshot: Chapter4Snapshot, doc: dict[str, Any], *, exclude: set[str]) -> None:
    for child in records._walk(doc):
        if set(child) == {"owner", "ref", "files"}:
            for item in child["files"]:
                rel = item["path"]
                if rel.startswith("logs/") or rel in exclude:
                    continue
                raw = snapshot.read(rel)
                _require(
                    codec.raw_digest(raw) == item["raw_digest"],
                    item["raw_digest"],
                    rel,
                    codec.ReasonCode.INPUT_STALE,
                    resume_ref=rel,
                    return_stage="4",
                )


def build(
    root: Path,
    request: dict[str, Any],
    *,
    allocations: dict[str, Any] | None = None,
    inventory_ops: list[dict[str, Any]] | None = None,
    read_operation_id: str | None = None,
    saved_public_sync: list[dict[str, Any]] | None = None,
    _held_scopes: set[str] | None = None,
) -> tuple[Chapter4Snapshot, dict[str, Any], dict[str, Any]]:
    """Revalidate committed 3B+3C/4, Story 3.3 B-route eligibility, and build frozen Stage-4 operation."""
    root = Path(root).resolve()
    journal.validate_operation_request(request)
    _require(
        request.get("schema_version") == REQUEST_SCHEMA and request.get("producer") == PRODUCER,
        REQUEST_SCHEMA,
        request.get("schema_version"),
        codec.ReasonCode.SCHEMA_MISMATCH,
        return_stage="4",
    )
    operation_id = _validate_file_id(request["operation_id"], "operation_id")
    plan_id = _validate_file_id(request["plan_id"], "plan_id")
    scope_id = request["scope_id"]
    codec.validate_business_id(scope_id)

    op_scope._legacy_pending(root, None)
    snapshot = Chapter4Snapshot(root)
    pre_sync_overrides = (
        {
            entry["path"]: _decode_b64(entry["before_base64"])
            for entry in saved_public_sync
            if entry.get("before_base64") is not None
        }
        if saved_public_sync
        else None
    ) or None

    # 1. Verify committed bundle via read_committed inside read_operation_context.
    with commit.read_operation_context(read_operation_id, pre_sync_bytes=pre_sync_overrides):
        committed = commit.read_committed(
            root, scope_ids=[scope_id], operation_id=read_operation_id, _held_scopes=_held_scopes
        )
    _require(
        committed.get("status") == "committed" and committed.get("formal_adoption") is True,
        "committed 3B+3C formal bundle",
        committed.get("status"),
        codec.ReasonCode.UNPUBLISHED,
        entity_id=plan_id,
        resume_ref=records.CATALOG_PATH,
        return_stage="3B",
    )
    catalog_raw = snapshot.read(records.CATALOG_PATH)
    _require(
        codec.raw_digest(catalog_raw) == committed["catalog_raw_digest"],
        committed["catalog_raw_digest"],
        codec.raw_digest(catalog_raw),
        codec.ReasonCode.INPUT_STALE,
        resume_ref=records.CATALOG_PATH,
    )
    catalog = codec.strict_json_loads(catalog_raw)
    snapshot.read(catalog["policy_ref"]["path"])
    origins_raw = _read_bytes(root, catalog["origins_ref"]["path"])
    current_origins = codec.strict_json_loads(origins_raw)

    # Locate committed plan_ref and prior 3C/4 binding_ref for plan_id.
    plan_ref = None
    prior_binding_ref = None
    affected_existing_heads: list[dict[str, Any]] = []
    for head in catalog["scope_heads"]:
        head_has_plan = False
        for ref in head["plan_refs"]:
            if ref["entity_id"] == plan_id:
                plan_ref = deepcopy(ref)
                head_has_plan = True
        for ref in head["binding_refs"]:
            if ref["entity_id"] == plan_id:
                prior_binding_ref = deepcopy(ref)
                head_has_plan = True
        if head_has_plan or head["scope_id"] == scope_id:
            affected_existing_heads.append(head)

    _require(
        plan_ref is not None,
        f"published 3B plan {plan_id} in catalog",
        plan_id,
        codec.ReasonCode.UNPUBLISHED,
        entity_id=plan_id,
        resume_ref=records.CATALOG_PATH,
        return_stage="3B",
    )
    _require(
        prior_binding_ref is not None,
        f"published 3C/4 binding for plan {plan_id} before Chapter 4 refinement",
        plan_id,
        codec.ReasonCode.UNPUBLISHED,
        entity_id=plan_id,
        resume_ref=records.CATALOG_PATH,
        return_stage="3C",
    )
    plan = codec.strict_json_loads(snapshot.read(plan_ref["path"]))
    prior_binding = codec.strict_json_loads(snapshot.read(prior_binding_ref["path"]))
    _require(
        prior_binding.get("stage") in ("3C", "4"),
        "prior binding stage 3C or 4",
        prior_binding.get("stage"),
        codec.ReasonCode.CONFLICT,
        entity_id=plan_id,
        resume_ref=prior_binding_ref["path"],
        return_stage="3C",
    )
    for head in affected_existing_heads:
        snapshot.read(head["receipt_ref"]["path"])

    # Verify 3A source alignment on non-log source files and non-source_gap dispositions.
    _check_source_alignment(root, plan, prior_binding)

    # 2. Load live Taskmaster triplet via strict TaskJoinContext.
    triplet = _load_triplet(snapshot)
    conserved_task_ids = sorted(row["task_id"] for row in prior_binding["task_mappings"])
    _require(
        bool(conserved_task_ids),
        "nonempty mapped Task IDs in prior 3C/4 binding",
        plan_id,
        codec.ReasonCode.MAPPING_MISMATCH,
        entity_id=plan_id,
        resume_ref=prior_binding_ref["path"],
        return_stage="3C",
    )

    # 3. Verify EVERY mapped Task classifies as B via Story 3.3 resolve_task_origin without conflict.
    with commit.read_operation_context(read_operation_id, pre_sync_bytes=pre_sync_overrides):
        for tid in conserved_task_ids:
            resolved = task_resolver.resolve_task_origin(root, tid)
            if not (resolved.get("ok") is True and resolved.get("stable") is True and resolved.get("route") == "B"):
                diags = resolved.get("diagnostics") or []
                first_code = codec.ReasonCode.CONFLICT
                resume = records.CATALOG_PATH
                if diags:
                    raw_code = diags[0].get("reason_code")
                    try:
                        first_code = codec.ReasonCode(raw_code)
                    except ValueError:
                        first_code = codec.ReasonCode.CONFLICT
                    resume = diags[0].get("resume_ref") or resume
                _fail(
                    first_code,
                    "Story 3.3 task origin route='B' without pending or conflict",
                    {
                        "task_id": tid,
                        "route": resolved.get("route"),
                        "diagnostics": diags,
                    },
                    entity_id=str(tid),
                    resume_ref=resume,
                    return_stage="3C",
                )
            resolved_plan_ids = {ref["entity_id"] for ref in resolved.get("plan_refs", [])}
            _require(
                plan_id in resolved_plan_ids,
                f"plan {plan_id} in Story 3.3 applicable plan_refs for Task {tid}",
                sorted(resolved_plan_ids),
                codec.ReasonCode.MAPPING_MISMATCH,
                entity_id=str(tid),
                resume_ref=records.BASE + "task-origins.v1.json",
                return_stage="3C",
            )

    # Also verify any extra task_ids requested match the conserved set and classify as B.
    if request.get("task_ids") is not None:
        req_tids = sorted(set(request["task_ids"]))
        if req_tids != conserved_task_ids:
            # Check if any supplied extra task is non-B to give clearest diagnostic.
            for extra_tid in req_tids:
                if extra_tid not in conserved_task_ids:
                    with commit.read_operation_context(read_operation_id):
                        extra_res = task_resolver.resolve_task_origin(root, extra_tid)
                    _fail(
                        codec.ReasonCode.MAPPING_MISMATCH,
                        conserved_task_ids,
                        {"requested_task_ids": req_tids, "extra_task_route": extra_res.get("route")},
                        entity_id=str(extra_tid),
                        resume_ref=prior_binding_ref["path"],
                        return_stage="3C",
                    )
            _fail(
                codec.ReasonCode.MAPPING_MISMATCH,
                conserved_task_ids,
                req_tids,
                entity_id=plan_id,
                resume_ref=prior_binding_ref["path"],
                return_stage="3C",
            )

    # 4. Prepare explicit public changes (contracts, EventTypes.cs, overlays) in memory.
    public_changes = request.get("public_changes")
    sync_entries, virtual_files, event_types_map = _prepare_public_sync_entries(
        root=root,
        public_changes=public_changes,
        saved_public_sync=saved_public_sync,
    )
    public_sync_path_set = {row["path"] for row in sync_entries}

    # 5. Compute monotonic binding_revision.
    inv = inventory_ops if inventory_ops is not None else journal.operation_inventory(root)
    existing_revs = [prior_binding["binding_revision"]]
    for op in inv:
        if op["operation_id"] == operation_id:
            continue
        claim = op["frozen"]["allocations"]
        if claim.get("plan_id") == plan_id and claim.get("binding_revision") is not None:
            existing_revs.append(claim["binding_revision"])
    binding_revision = (
        allocations["binding_revision"]
        if allocations is not None
        else max(existing_revs) + 1
    )
    _require(
        binding_revision > prior_binding["binding_revision"],
        "strictly monotonic binding_revision",
        binding_revision,
        codec.ReasonCode.REVISION_MISMATCH,
        entity_id=plan_id,
        return_stage="4",
    )

    # 6. Build and validate Stage-4 formal binding record.
    stage4_binding, chapter7_required = _build_stage4_binding(
        root=root,
        request=request,
        plan=plan,
        plan_ref=plan_ref,
        prior_binding=prior_binding,
        catalog=catalog,
        binding_revision=binding_revision,
        virtual_files=virtual_files,
        event_types_map=event_types_map,
    )
    binding_path = f"{records.BASE}bindings/{plan_id}/{binding_revision}.json"
    b_check = records.validate_record(stage4_binding, path=binding_path)
    if not b_check.ok:
        raise codec.CodecError(b_check.diagnostic)
    binding_raw = projection.serialized(stage4_binding)
    binding_ref = projection.reference(binding_path, binding_raw)

    # 7. Update task-origins.v1.json preserving ALL other plans' refs on shared Tasks.
    updated_origins = _build_updated_origins(
        current_origins=current_origins,
        plan_id=plan_id,
        plan_ref=plan_ref,
        binding_ref=binding_ref,
        conserved_task_ids=conserved_task_ids,
    )
    origins_path = records.BASE + "task-origins.v1.json"
    origins_after_raw = projection.serialized(updated_origins)

    # Collect non-synced external refs into snapshot for drift pinning.
    _collect_plan_authority_files(snapshot, plan, exclude=public_sync_path_set)
    _collect_plan_authority_files(snapshot, stage4_binding, exclude=public_sync_path_set)
    _collect_plan_authority_files(snapshot, updated_origins, exclude=public_sync_path_set)

    # 8. Optional live-projection triplet ref sync (ONLY when explicitly requested in public_changes).
    triplet_sync_reqs = list((public_changes or {}).get("triplet_ref_sync") or [])
    triplet_before_proj: dict[str, str] | None = None
    triplet_after_proj: dict[str, str] | None = None
    compiled_join = triplet["join"]

    if allocations is None:
        _require(
            _read_bytes(root, binding_path, optional=True) is None,
            "fresh immutable stage=4 binding path",
            binding_path,
            codec.ReasonCode.CONFLICT,
            entity_id=binding_path,
            return_stage="4",
        )

    targets: list[dict[str, Any]] = [
        {
            "path": binding_path,
            "schema_version": "newrouge.b-route-binding.v1",
            "before_raw_digest": None,
            "after_payload": stage4_binding,
            "after_raw_digest": codec.raw_digest(binding_raw),
            "verification_mode": "immutable_bytes",
        },
        {
            "path": origins_path,
            "schema_version": "newrouge.b-route-origins.v1",
            "before_raw_digest": codec.raw_digest(origins_raw),
            "after_payload": updated_origins,
            "after_raw_digest": codec.raw_digest(origins_after_raw),
            "verification_mode": "immutable_bytes",
        },
    ]

    if triplet_sync_reqs:
        allowed_events = set(event_types_map.values())
        synced_master, synced_back, synced_gameplay = _apply_triplet_ref_sync(
            root=root,
            triplet=triplet,
            sync_entries=triplet_sync_reqs,
            allowed_task_ids=set(conserved_task_ids),
            allowed_events=allowed_events,
            binding_path=binding_path,
            virtual_files=virtual_files,
        )
        compiled_join = records.TaskJoinContext(
            master=synced_master, back=synced_back, gameplay=synced_gameplay
        )
        triplet_before_proj = {}
        triplet_after_proj = {}
        for key, payload in (("master", synced_master), ("back", synced_back), ("gameplay", synced_gameplay)):
            tpath = TRIPLET[key]
            before_raw = triplet["raws"][key]
            after_raw = projection.serialized(payload)
            b_proj = records.task_document_digest(tpath, before_raw)
            a_proj = records.task_document_digest(tpath, after_raw)
            triplet_before_proj[tpath] = b_proj
            triplet_after_proj[tpath] = a_proj
            targets.append(
                {
                    "path": tpath,
                    "schema_version": TRIPLET_SCHEMAS[tpath],
                    "before_raw_digest": codec.raw_digest(before_raw),
                    "after_payload": payload,
                    "after_raw_digest": codec.raw_digest(after_raw),
                    "verification_mode": "task_definition_projection",
                    "codec_version": records.PROJECTION_CODEC,
                    "before_projection_digest": b_proj,
                    "after_projection_digest": a_proj,
                }
            )

    # 9. Build allocations (including task_definitions compatible with _b_route_commit & _b_route_compensation).
    task_definitions: dict[str, str] = {}
    for tid in conserved_task_ids:
        defn = {
            "master": protection.task_definition_projection(triplet["master"][tid]),
            "back": [
                protection.task_definition_projection(row)
                for row in triplet["docs"]["back"]
                if row["taskmaster_id"] == tid
            ],
            "gameplay": [
                protection.task_definition_projection(row)
                for row in triplet["docs"]["gameplay"]
                if row["taskmaster_id"] == tid
            ],
        }
        task_definitions[str(tid)] = codec.canonical_digest(defn)

    proposed_allocations = {
        "plan_id": plan_id,
        "plan_revision": plan["revision"],
        "binding_revision": binding_revision,
        "origins_revision": updated_origins["revision"],
        "task_definitions": task_definitions,
    }
    _require(
        allocations is None or allocations == proposed_allocations,
        "unchanged frozen chapter4_binding allocations",
        proposed_allocations,
        codec.ReasonCode.INPUT_STALE,
        entity_id=operation_id,
    )

    # 10. Compute complete old + new resource_scopes union (including public sync paths).
    old_scope_ids = sorted({scope_id} | {head["scope_id"] for head in affected_existing_heads})
    new_scope_ids = list(
        op_scope.resource_scopes(
            target_paths=[row["path"] for row in targets] + sorted(public_sync_path_set),
            plan_ids=[plan_id],
            requirement_ids=[row["requirement_id"] for row in plan["requirements"]],
            flow_ids=[row["id"] for row in plan["definitions"]["flows"]],
            command_ids=[row["id"] for row in plan["definitions"]["commands"]],
            state_ids=[row["id"] for row in plan["definitions"]["states"]],
            task_ids=conserved_task_ids,
        )
    )
    scope_ids = sorted(set(old_scope_ids) | set(new_scope_ids))

    # 11. Build authority_refs excluding targets; pin post-sync digests of synced public files.
    excluded_auth = {row["path"] for row in targets} | public_sync_path_set
    authority_map: dict[str, str] = {
        name: digest
        for name, digest in snapshot.files.items()
        if digest is not None and name not in excluded_auth
    }
    for entry in sync_entries:
        authority_map[entry["path"]] = entry["after_sha256"]
    authority_refs = [
        {"path": name, "schema_version": "raw.bytes.v1", "raw_digest": digest}
        for name, digest in sorted(authority_map.items())
    ]

    bundle_candidates: dict[str, bytes] = {records.CATALOG_PATH: catalog_raw}
    if pre_sync_overrides:
        bundle_candidates.update(pre_sync_overrides)
    bundle = records._PublishedBundle(
        bundle_candidates, root, records.CATALOG_PATH, None, triplet["join"]
    )
    loaded_cat = bundle.load(records.CATALOG_PATH)
    bundle.select(loaded_cat, [scope_id])
    bundle.expand()
    bundle.relationships(loaded_cat)
    bundle.bytes.stable()

    frozen = {
        "producer": PRODUCER,
        "request": deepcopy(request),
        "allocations": proposed_allocations,
        "scope_ids": scope_ids,
        "authority_refs": authority_refs,
        "targets": targets,
        "refinement": {
            "plan_id": plan_id,
            "scope_id": scope_id,
            "prior_binding_ref": deepcopy(prior_binding_ref),
            "plan_ref": deepcopy(plan_ref),
            "current_catalog_digest": codec.raw_digest(catalog_raw),
            "current_frame_digest": codec.canonical_digest(bundle.semantic_frame),
            "old_scope_ids": old_scope_ids,
            "new_scope_ids": new_scope_ids,
            "has_public_changes": bool(sync_entries),
            "public_sync_entries": sync_entries,
            "chapter7_required": chapter7_required,
            "triplet_before_projections": triplet_before_proj,
            "triplet_after_projections": triplet_after_proj,
        },
    }
    journal._operation_schema(frozen, "Frozen")

    # 12. Dry-run validate future receipt + catalog bundle against post-sync virtual files!
    candidates: dict[str, bytes] = {
        row["path"]: projection.serialized(row["after_payload"]) for row in targets
    }
    candidates[records.CATALOG_PATH] = catalog_raw
    for rel, raw in virtual_files.items():
        candidates[rel] = raw

    draft_bundle = records._Bundle(candidates, root, records.CATALOG_PATH, None, compiled_join)
    owners = {(row["kind"], row["definition_id"]): row for row in catalog["definition_owners"]}
    pre_receipt = projection.receipt_for_frozen(
        operation_id=operation_id, frozen=frozen, resolved_definitions=[], catalog_before=catalog_raw
    )
    resolved = draft_bundle.closure(
        pre_receipt["plan_refs"],
        pre_receipt["binding_refs"],
        owners,
        records.BASE + f"commits/{operation_id}.json",
    )
    full_receipt = projection.receipt_for_frozen(
        operation_id=operation_id,
        frozen=frozen,
        resolved_definitions=[resolved[k] for k in sorted(resolved)],
        catalog_before=catalog_raw,
    )
    projection.catalog_for_receipt(
        current_catalog=catalog_raw,
        receipt=full_receipt,
        candidates=candidates,
        task_join=compiled_join,
        root=root,
        frozen=frozen,
    )

    semantics = extract_stage4_semantics(plan, stage4_binding)
    snapshot.verify()
    return snapshot, frozen, semantics


# ---------------------------------------------------------------------------
# Public Lifecycle Operations (preview / prepare / reserve / inspect / commit hooks)
# ---------------------------------------------------------------------------


def _result(
    envelope: dict[str, Any],
    *,
    semantics: dict[str, Any] | None = None,
    event_log: str | None = None,
) -> dict[str, Any]:
    refinement = envelope["frozen"]["refinement"]
    res = {
        "producer": PRODUCER,
        "operation_id": envelope["operation_id"],
        "state": envelope["state"],
        "scope_ids": envelope["frozen"]["scope_ids"],
        "request_digest": envelope["request_digest"],
        "frozen_digest": envelope["frozen_digest"],
        "allocations": envelope["frozen"]["allocations"],
        "has_public_changes": refinement["has_public_changes"],
        "public_sync_paths": [e["path"] for e in refinement["public_sync_entries"]],
        "chapter7_required": refinement["chapter7_required"],
        "resume_ref": journal._operation_ref(envelope["operation_id"]),
        "formal_adoption": False,
        "diagnostics": [],
        **FLAGS,
    }
    if semantics is not None:
        res["stage4_semantics"] = semantics
    if event_log is not None:
        res["event_log"] = event_log
    return res


def public(function):
    @wraps(function)
    def checked(root, *, operation_id, **kwargs):
        try:
            return function(root, operation_id=operation_id, **kwargs)
        except codec.CodecError as error:
            diagnostic = error.diagnostic
            if diagnostic.entity_id is None and type(operation_id) is str:
                diagnostic = replace(diagnostic, entity_id=operation_id)
            raise codec.CodecError(diagnostic) from error
        except (OSError, KeyError, TypeError, ValueError, RuntimeError) as error:
            _fail(
                codec.ReasonCode.IDENTITY_UNPROVABLE,
                "complete governed chapter4 binding evidence",
                f"{type(error).__name__}: {error}",
                entity_id=operation_id if type(operation_id) is str else None,
            )

    return checked


@public
def preview(root: Path | str, *, operation_id: str, request_ref: str) -> dict[str, Any]:
    """Pure read-only zero-write Chapter 4 refinement preview."""
    root_path = Path(root).resolve()
    _validate_file_id(operation_id, "operation_id")
    raw = _read_bytes(root_path, request_ref)
    request = journal.validate_operation_request(raw)
    _require(
        request["operation_id"] == operation_id,
        operation_id,
        request["operation_id"],
        codec.ReasonCode.CONFLICT,
        entity_id=operation_id,
    )
    _snapshot, frozen, semantics = build(root_path, request, read_operation_id=None)
    return {
        "schema_version": PREVIEW_SCHEMA,
        "producer": PRODUCER,
        "status": "previewed",
        "operation_id": operation_id,
        "plan_id": frozen["allocations"]["plan_id"],
        "binding_revision": frozen["allocations"]["binding_revision"],
        "scope_ids": frozen["scope_ids"],
        "frozen_digest": codec.canonical_digest(frozen),
        "has_public_changes": frozen["refinement"]["has_public_changes"],
        "public_sync_paths": [e["path"] for e in frozen["refinement"]["public_sync_entries"]],
        "chapter7_required": frozen["refinement"]["chapter7_required"],
        "target_paths": [t["path"] for t in frozen["targets"]],
        "stage4_semantics": semantics,
        "formal_adoption": False,
        "diagnostics": [],
        **FLAGS,
    }


def _run(root: Path, operation_id: str, request_raw: bytes, *, reserve_only: bool = False) -> dict[str, Any]:
    root = Path(root).resolve()
    _validate_file_id(operation_id, "operation_id")
    request = journal.validate_operation_request(request_raw)
    _require(
        request.get("schema_version") == REQUEST_SCHEMA and request.get("producer") == PRODUCER,
        REQUEST_SCHEMA,
        request.get("schema_version"),
        codec.ReasonCode.SCHEMA_MISMATCH,
        entity_id=operation_id,
    )
    _require(
        request["operation_id"] == operation_id,
        operation_id,
        request["operation_id"],
        codec.ReasonCode.CONFLICT,
        entity_id=operation_id,
    )
    inv = journal.operation_inventory(root)
    existing = next((row for row in inv if row["operation_id"] == operation_id), None)
    _require(
        not reserve_only or existing is not None,
        "existing prepared chapter4_binding operation",
        operation_id,
        codec.ReasonCode.FILE_NOT_FOUND,
        entity_id=operation_id,
    )
    if existing is not None:
        _require(
            existing["schema_version"] == OPERATION_SCHEMA,
            OPERATION_SCHEMA,
            existing["schema_version"],
            codec.ReasonCode.CONFLICT,
            entity_id=operation_id,
        )
        _require(
            existing["request_digest"] == codec.canonical_digest(request),
            "same ID and complete request for chapter4_binding",
            operation_id,
            codec.ReasonCode.CONFLICT,
            entity_id=operation_id,
        )
        if commit.validate_local(root, existing) is not None:
            return _result(existing)
        request = existing["frozen"]["request"]
        request_raw = base64.b64decode(existing["request_raw_base64"], validate=True)

    op_scope.initialize_lock_namespace(root)
    read_op = operation_id if existing is not None else None
    snapshot, frozen, semantics = build(
        root,
        request,
        allocations=existing["frozen"]["allocations"] if existing is not None else None,
        inventory_ops=inv,
        read_operation_id=read_op,
    )
    if existing is not None:
        existing_targets = existing["frozen"]["targets"]
        _require(
            len(frozen["targets"]) == len(existing_targets)
            and frozen["allocations"] == existing["frozen"]["allocations"]
            and frozen["scope_ids"] == existing["frozen"]["scope_ids"]
            and frozen["refinement"]["public_sync_entries"]
            == existing["frozen"]["refinement"]["public_sync_entries"],
            "unchanged frozen chapter4_binding operation between prepare and reserve",
            operation_id,
            codec.ReasonCode.INPUT_STALE,
            entity_id=operation_id,
        )
        for cur_t, old_t in zip(frozen["targets"], existing_targets):
            _require(
                cur_t["path"] == old_t["path"] and cur_t["verification_mode"] == old_t["verification_mode"],
                "same target sequence between prepare and reserve",
                cur_t["path"],
                codec.ReasonCode.INPUT_STALE,
                entity_id=operation_id,
            )
            if cur_t["verification_mode"] == "immutable_bytes":
                _require(
                    cur_t["before_raw_digest"] == old_t["before_raw_digest"]
                    and cur_t["after_raw_digest"] == old_t["after_raw_digest"],
                    "unchanged immutable formal targets between prepare and reserve",
                    cur_t["path"],
                    codec.ReasonCode.INPUT_STALE,
                    entity_id=operation_id,
                )
            else:
                _require(
                    cur_t["before_projection_digest"] == old_t["before_projection_digest"]
                    and cur_t["after_projection_digest"] == old_t["after_projection_digest"],
                    "unchanged triplet definition projection between prepare and reserve",
                    cur_t["path"],
                    codec.ReasonCode.INPUT_STALE,
                    entity_id=operation_id,
                )
        frozen = existing["frozen"]

    with op_scope.business_guard(root, frozen["scope_ids"], operation_id=operation_id):
        snapshot.verify()
        current = journal.operation_inventory(root)
        live_existing = next((row for row in current if row["operation_id"] == operation_id), None)
        _require(
            not reserve_only or live_existing is not None,
            "existing prepared chapter4_binding operation under lease",
            operation_id,
            codec.ReasonCode.FILE_NOT_FOUND,
            entity_id=operation_id,
        )
        if live_existing is not None:
            _require(
                live_existing["request_digest"] == codec.canonical_digest(request)
                and live_existing["frozen"] == frozen,
                "unchanged persisted chapter4_binding operation under lease",
                operation_id,
                codec.ReasonCode.CONFLICT,
                entity_id=operation_id,
            )
            new_state = "reserved" if (reserve_only or live_existing["state"] == "reserved") else live_existing["state"]
            value = {**live_existing, "state": new_state}
        else:
            locked_plan_id = frozen["allocations"]["plan_id"]
            locked_binding_rev = frozen["allocations"]["binding_revision"]
            for other in current:
                if other["operation_id"] == operation_id:
                    continue
                other_claim = other["frozen"]["allocations"]
                if (
                    other_claim.get("plan_id") == locked_plan_id
                    and other_claim.get("binding_revision") == locked_binding_rev
                ):
                    _fail(
                        codec.ReasonCode.CONFLICT,
                        "unique monotonic binding_revision under lease",
                        locked_binding_rev,
                        entity_id=operation_id,
                    )
            value = journal.draft_operation(root, request_raw=request_raw, frozen=frozen)

        captured = {
            journal._operation_ref(row["operation_id"]): codec.read_reference_bytes(
                root, journal._operation_ref(row["operation_id"])
            )
            for row in current
        }
        index_rel = journal.OPERATION_STORE + "/pending.json"
        index_path = journal._operation_path(root, index_rel)
        index_raw = index_path.read_bytes() if index_path.exists() else None

        def unchanged():
            snapshot.verify()
            _require(
                all(codec.read_reference_bytes(root, name) == raw for name, raw in captured.items())
                and (index_path.read_bytes() if index_path.exists() else None) == index_raw,
                "same operation/index at short writer boundary",
                operation_id,
                codec.ReasonCode.INPUT_STALE,
                entity_id=operation_id,
            )

        with op_scope.writer_boundary(root, recheck=unchanged):
            if live_existing != value:
                journal._operation_write(root, value, current, verify=False)
        persisted = journal.read_operation(root, operation_id=operation_id)
        _require(
            persisted == value,
            "complete persisted chapter4_binding operation",
            operation_id,
            codec.ReasonCode.CONFLICT,
            entity_id=operation_id,
        )
        event_log = append_event(
            root,
            operation_id,
            "reserve" if reserve_only else "prepare",
            persisted["state"],
            {
                "plan_id": persisted["frozen"]["allocations"]["plan_id"],
                "binding_revision": persisted["frozen"]["allocations"]["binding_revision"],
                "has_public_changes": persisted["frozen"]["refinement"]["has_public_changes"],
                "chapter7_required": persisted["frozen"]["refinement"]["chapter7_required"],
                "frozen_digest": persisted["frozen_digest"],
            },
        )
        return _result(persisted, semantics=semantics, event_log=event_log)


@public
def prepare(root: Path | str, *, operation_id: str, request_ref: str) -> dict[str, Any]:
    root_path = Path(root).resolve()
    raw = _read_bytes(root_path, request_ref)
    return _run(root_path, operation_id, raw, reserve_only=False)


@public
def reserve(root: Path | str, *, operation_id: str) -> dict[str, Any]:
    root_path = Path(root).resolve()
    envelope = journal.read_operation(root_path, operation_id=operation_id)
    _require(
        envelope["schema_version"] == OPERATION_SCHEMA,
        OPERATION_SCHEMA,
        envelope["schema_version"],
        codec.ReasonCode.SCHEMA_MISMATCH,
        entity_id=operation_id,
    )
    return _run(
        root_path,
        operation_id,
        base64.b64decode(envelope["request_raw_base64"], validate=True),
        reserve_only=True,
    )


@public
def inspect(root: Path | str, *, operation_id: str) -> dict[str, Any]:
    """Read-only inspection of a prepared/reserved chapter4_binding operation."""
    root_path = Path(root).resolve()
    envelope = journal.read_operation(root_path, operation_id=operation_id)
    _require(
        envelope["schema_version"] == OPERATION_SCHEMA,
        OPERATION_SCHEMA,
        envelope["schema_version"],
        codec.ReasonCode.SCHEMA_MISMATCH,
        entity_id=operation_id,
    )
    intent = commit.validate_local(root_path, envelope)
    pub_journal = validate_public_sync_local(root_path, envelope)
    sealed = commit._sealed_targets(intent) if intent is not None else None
    differences: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    pub_sync_by_path = {
        entry["path"]: entry
        for entry in envelope["frozen"]["refinement"]["public_sync_entries"]
    }
    for ref in envelope["frozen"]["authority_refs"]:
        if intent is not None and ref["path"] == records.CATALOG_PATH and intent.get("catalog_after") is not None:
            actual_cat = _read_bytes(root_path, records.CATALOG_PATH, optional=True)
            cat_digest = codec.raw_digest(actual_cat) if actual_cat is not None else None
            if cat_digest not in {ref["raw_digest"], intent["catalog_after_digest"]}:
                diagnostics.append(
                    codec.Diagnostic(
                        codec.ReasonCode.INPUT_STALE,
                        codec.Stage.BUNDLE,
                        operation_id,
                        ref["raw_digest"],
                        cat_digest,
                        records.CATALOG_PATH,
                    ).to_dict()
                )
            continue
        actual = _read_bytes(root_path, ref["path"], optional=True)
        actual_sha = codec.raw_digest(actual) if actual is not None else None
        if ref["path"] in pub_sync_by_path:
            entry = pub_sync_by_path[ref["path"]]
            allowed_shas = (
                {entry["before_sha256"], entry["after_sha256"]}
                if intent is None
                else {entry["after_sha256"]}
            )
            if actual_sha not in allowed_shas:
                diagnostics.append(
                    codec.Diagnostic(
                        codec.ReasonCode.INPUT_STALE,
                        codec.Stage.BUNDLE,
                        operation_id,
                        sorted(x for x in allowed_shas if x is not None),
                        actual_sha,
                        ref["path"],
                    ).to_dict()
                )
            continue
        if actual_sha != ref["raw_digest"]:
            diagnostics.append(
                codec.Diagnostic(
                    codec.ReasonCode.INPUT_STALE,
                    codec.Stage.BUNDLE,
                    operation_id,
                    ref["raw_digest"],
                    actual_sha,
                    ref["path"],
                ).to_dict()
            )

    for entry in envelope["frozen"]["refinement"]["public_sync_entries"]:
        cur = _read_bytes(root_path, entry["path"], optional=True)
        cur_sha = codec.raw_digest(cur) if cur is not None else None
        matches = cur_sha in {entry["before_sha256"], entry["after_sha256"]}
        differences.append(
            {
                "path": entry["path"],
                "verification_mode": "public_sync_raw_bytes",
                "expected_before": entry["before_sha256"],
                "actual": cur_sha,
                "frozen_after": entry["after_sha256"],
                "matches_before": cur_sha == entry["before_sha256"],
            }
        )
        if not matches:
            diagnostics.append(
                codec.Diagnostic(
                    codec.ReasonCode.CONFLICT,
                    codec.Stage.TARGET,
                    operation_id,
                    {"before": entry["before_sha256"], "after": entry["after_sha256"]},
                    cur_sha,
                    entry["path"],
                ).to_dict()
            )

    for target in envelope["frozen"]["targets"]:
        cur = _read_bytes(root_path, target["path"], optional=True)
        cur_sha = codec.raw_digest(cur) if cur is not None else None
        if target["verification_mode"] == "task_definition_projection":
            actual_proj = records.task_document_digest(target["path"], cur) if cur is not None else None
            matches_before = actual_proj == target["before_projection_digest"]
            matches_after = (
                sealed is not None
                and target["path"] in sealed
                and cur_sha == sealed[target["path"]]["after_digest"]
                and actual_proj == target["after_projection_digest"]
            )
            differences.append(
                {
                    "path": target["path"],
                    "verification_mode": target["verification_mode"],
                    "expected_before_projection": target["before_projection_digest"],
                    "actual_projection": actual_proj,
                    "frozen_after_projection": target["after_projection_digest"],
                    "matches_before": matches_before,
                }
            )
            if not (matches_before or matches_after):
                diagnostics.append(
                    codec.Diagnostic(
                        codec.ReasonCode.INPUT_STALE,
                        codec.Stage.TARGET,
                        operation_id,
                        target["before_projection_digest"],
                        actual_proj,
                        target["path"],
                    ).to_dict()
                )
        else:
            matches_before = cur_sha == target["before_raw_digest"]
            matches_after = (
                sealed is not None
                and target["path"] in sealed
                and cur_sha == sealed[target["path"]]["after_digest"]
            )
            differences.append(
                {
                    "path": target["path"],
                    "verification_mode": target["verification_mode"],
                    "expected_before": target["before_raw_digest"],
                    "actual": cur_sha,
                    "frozen_after": target["after_raw_digest"],
                    "matches_before": matches_before,
                }
            )
            if not (matches_before or matches_after):
                diagnostics.append(
                    codec.Diagnostic(
                        codec.ReasonCode.INPUT_STALE,
                        codec.Stage.TARGET,
                        operation_id,
                        target["before_raw_digest"],
                        cur_sha,
                        target["path"],
                    ).to_dict()
                )

    return {
        **_result(envelope),
        "public_sync_phase": None if pub_journal is None else pub_journal["phase"],
        "target_differences": differences,
        "diagnostics": diagnostics,
        "status": "blocked" if diagnostics else "inspected",
        "eligibility": "read-only inspect; reserve and apply revalidate committed 3B+3C and Story 3.3 B eligibility",
    }


@contextmanager
def commit_context(root: Path, *, operation_id: str, _held_scopes: set[str] | None = None):
    """Initial apply admission context for shared _b_route_commit.execute."""
    root = Path(root).resolve()
    envelope = journal.read_operation(root, operation_id=operation_id)
    _require(
        envelope["schema_version"] == OPERATION_SCHEMA and envelope["state"] == "reserved",
        "reserved chapter4_binding operation",
        operation_id,
        codec.ReasonCode.CONFLICT,
        entity_id=operation_id,
    )
    saved_public_sync = None
    if envelope["frozen"]["refinement"]["has_public_changes"]:
        pub_doc = validate_public_sync_local(root, envelope)
        _require(
            pub_doc is not None and pub_doc["phase"] in ("applied", "complete"),
            "applied public-sync-journal.json before formal commit freeze",
            None if pub_doc is None else pub_doc["phase"],
            codec.ReasonCode.UNPUBLISHED,
            entity_id=operation_id,
            resume_ref=public_sync_paths(operation_id)[0],
        )
        saved_public_sync = pub_doc["entries"]
    request = envelope["frozen"]["request"]
    snapshot, checked_frozen, _semantics = build(
        root,
        request,
        allocations=envelope["frozen"]["allocations"],
        read_operation_id=operation_id,
        saved_public_sync=saved_public_sync,
        _held_scopes=_held_scopes,
    )
    _require(
        checked_frozen["allocations"] == envelope["frozen"]["allocations"]
        and checked_frozen["scope_ids"] == envelope["frozen"]["scope_ids"]
        and checked_frozen["refinement"] == envelope["frozen"]["refinement"],
        "unchanged reserved chapter4_binding semantics before apply freeze",
        operation_id,
        codec.ReasonCode.INPUT_STALE,
        entity_id=operation_id,
    )
    for frozen_t, checked_t in zip(envelope["frozen"]["targets"], checked_frozen["targets"]):
        _require(
            frozen_t["path"] == checked_t["path"]
            and frozen_t["verification_mode"] == checked_t["verification_mode"],
            "same target sequence before apply freeze",
            frozen_t["path"],
            codec.ReasonCode.INPUT_STALE,
        )
        if frozen_t["verification_mode"] == "immutable_bytes":
            _require(
                frozen_t["before_raw_digest"] == checked_t["before_raw_digest"]
                and frozen_t["after_raw_digest"] == checked_t["after_raw_digest"],
                "unchanged immutable targets before apply freeze",
                frozen_t["path"],
                codec.ReasonCode.INPUT_STALE,
            )
        else:
            _require(
                frozen_t["before_projection_digest"] == checked_t["before_projection_digest"]
                and frozen_t["after_projection_digest"] == checked_t["after_projection_digest"],
                "unchanged triplet definition projection before apply freeze",
                frozen_t["path"],
                codec.ReasonCode.INPUT_STALE,
            )
    snapshot.verify()
    yield snapshot, envelope


def verify_saved(root: Path, envelope: dict[str, Any]) -> None:
    """Re-verify saved operation envelope and public-sync state during unfinished commit/recover."""
    root = Path(root).resolve()
    journal._operation_validate(root, envelope)
    op_scope._legacy_pending(root, None)
    if envelope["frozen"]["refinement"]["has_public_changes"]:
        pub_doc = validate_public_sync_local(root, envelope)
        _require(
            pub_doc is not None and pub_doc["phase"] in ("applied", "complete"),
            "applied or complete public-sync-journal.json during commit step",
            None if pub_doc is None else pub_doc["phase"],
            codec.ReasonCode.PENDING,
            entity_id=envelope["operation_id"],
            resume_ref=public_sync_paths(envelope["operation_id"])[0],
        )
        for entry in pub_doc["entries"]:
            actual = _read_bytes(root, entry["path"])
            _require(
                codec.raw_digest(actual) == entry["after_sha256"],
                entry["after_sha256"],
                codec.raw_digest(actual),
                codec.ReasonCode.INPUT_STALE,
                entity_id=entry["path"],
                resume_ref=entry["path"],
            )


def verify_observations(
    root: Path,
    envelope: dict[str, Any],
    intent: dict[str, Any],
    *,
    facts,
    published: bool = False,
) -> None:
    """Verify frozen commit.json observations plus synced public files and sealed targets."""
    from _b_route_commit import _catalog_frame, _classify_target, _decode, _digest, _read, _sealed_targets
    import _b_route_adoption_review as review

    root = Path(root).absolute()
    _require(
        intent["policy_identity"] == review.policy_identity(),
        "same reviewed chapter4_binding rules",
        "policy changed",
        codec.ReasonCode.INPUT_STALE,
    )
    sealed = _sealed_targets(intent)
    permitted = {
        str(root / path): (
            {row["after_digest"]} if published else {row["before_digest"], row["after_digest"]}
        )
        for path, row in sealed.items()
    }
    permitted[str(root / records.CATALOG_PATH)] = {_digest(_decode(intent["catalog_before"]))}
    if intent["catalog_after"] is not None:
        permitted[str(root / records.CATALOG_PATH)].add(_digest(_decode(intent["catalog_after"])))

    # Pin all synced public files at their exact after_sha256.
    for entry in envelope["frozen"]["refinement"]["public_sync_entries"]:
        actual = _digest(_read(root, entry["path"], optional=True))
        _require(
            actual == entry["after_sha256"],
            entry["after_sha256"],
            actual,
            codec.ReasonCode.INPUT_STALE,
            entity_id=entry["path"],
            resume_ref=entry["path"],
        )
        facts.file(str(root / entry["path"]), actual)

    for name, expected in intent["files"].items():
        if name == str(root / records.CATALOG_PATH):
            continue
        obs_path = Path(name)
        journal._operation_no_reparse(obs_path)
        rel = obs_path.resolve().relative_to(root.resolve()).as_posix()
        actual = _digest(_read(root, rel, optional=True))
        _require(
            actual in permitted.get(name, {expected}),
            "unchanged chapter4 input or exact sealed target image",
            rel,
            codec.ReasonCode.INPUT_STALE,
        )
        facts.file(name, actual)

    for ref in envelope["frozen"]["authority_refs"]:
        if ref["path"] == records.CATALOG_PATH:
            continue
        actual = _digest(_read(root, ref["path"], optional=True))
        key = str(root / ref["path"])
        _require(
            actual in permitted.get(key, {ref["raw_digest"]}),
            ref["raw_digest"],
            ref["path"],
            codec.ReasonCode.INPUT_STALE,
        )
        facts.file(key, actual)

    for target in envelope["frozen"]["targets"]:
        checked = _classify_target(root, target, sealed=sealed)
        if published:
            _require(
                checked["state"] == "after",
                "all sealed targets in after state once published",
                target["path"],
                codec.ReasonCode.CONFLICT,
            )
        facts.file(str(root / target["path"]), checked["actual_raw_digest"])

    actual_catalog = _read(root, records.CATALOG_PATH)
    expected_catalog = _decode(intent["catalog_after"]) if published else _decode(intent["catalog_before"])
    if actual_catalog != expected_catalog and (published or actual_catalog != _decode(intent["catalog_after"])):
        _require(
            _catalog_frame(root, envelope, actual_catalog, intent["before_files"])
            == _catalog_frame(root, envelope, expected_catalog, intent["before_files"]),
            "unchanged affected catalog scope after unrelated publication",
            records.CATALOG_PATH,
            codec.ReasonCode.INPUT_STALE,
        )
    _require(
        _catalog_frame(
            root,
            envelope,
            _decode(intent["catalog_before"]),
            intent["before_files"],
            origins_raw=_decode(intent["origins_before"]),
        )
        == intent["catalog_frame"],
        "exact original catalog before frame",
        envelope["operation_id"],
        codec.ReasonCode.CONFLICT,
    )
    facts.file(str(root / records.CATALOG_PATH), _digest(actual_catalog))
