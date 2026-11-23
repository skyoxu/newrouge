"""Governed Stage-5 MVG obligations or legal other_verification binding owner.

Consumes a committed 3B plan and Stage-4/5 binding, verifies every conserved
Task via Story 3.3 resolve_task_origin (route="B") and validates the candidate
Stage-5 binding through Story 3.5 resolve_input_set (single-slot candidate
replacement plus pre-sync support). Enforces:
- Conservation of the Stage-4 task_id set, four parts, implementation_objects,
  and STAGE4_OBL_PREFIX tags (preventing false return_stage="4" drift).
- Valid MVG manifest binding (raw_digest, manifest_sha256, status-decoupled
  validation, and optional update_mvg_baseline reviewed delta synced via raw-byte
  base64 public-sync-journal.json + public-sync.pending.json) for any Flow,
  handoff/integration/regression owner, or Flow-impacted Task.
- Strict formal subset discipline: binding.obligations[].requirement_ids and
  flow_ids stay subsets of plan.requirements and covered catalog.definition_owners;
  non-catalog cumulative regression flows and out_of_scope_future flows are
  recorded in STAGE5_OBL_PREFIX plus manifest_refs/test_ids without triggering
  MAPPING_MISMATCH.
- Legal non-Flow exemption ONLY when 3B applicability rationale,
  adoption_proof_refs, genuine other_verification_refs, InputSet, and proven
  zero Flow impact all hold; blocks labels, empty/N/A, source_gap, or deleted
  verification evidence.
- Flow impact analysis and conservative expansion (existing_required,
  current_new, out_of_scope_future) without waiting for Epic 4, rejecting
  narrowing, forced future implementation, or unprovable impact.
- Role-aware handoff and dependency checks (producer / consumer /
  integration_only_owner) without requiring runtime APIs from integration-only
  owners or introducing self-locks, preserving prerequisites, and distinguishing
  legal unimplemented (planned / non-done) from missing definitions.
- Shared deduplication along unique requirement_verification,
  (requirement_id, flow_id), and dedup keys; old done never covers new
  obligations or planned tests (requires_reverification=true without copying
  Task status into formal authority); reducing/retiring obligations requires a
  valid specification authority_ref and reviewed rationale.
- Publication via shared _b_route_commit (monotonic binding_revision,
  multi-plan preservation on shared Tasks, catalog.v1.json last), compatible
  with Story 2.8 compensation, with readiness=false, runtime_verified=false,
  and default_b_enabled=false always.
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
import json
from pathlib import Path
import re
from typing import Any

import _b_route_chapter4_binding as ch4_binding
import _b_route_codec as codec
import _b_route_commit as commit
import _b_route_commit_projection as projection
import _b_route_input_set as input_set
import _b_route_operation_scope as op_scope
import _b_route_preflight as preflight
import _b_route_protection as protection
import _b_route_record_owners as record_owners
import _b_route_records as records
import _b_route_task_resolver as task_resolver
import _chapter5_contract_bindings as contract_bindings
import _mvg_manifest as mvg_manifest
import _planning_apply_journal as journal
import update_mvg_baseline


REQUEST_SCHEMA = journal.STAGE5_OBLIGATIONS_REQUEST
OPERATION_SCHEMA = journal.STAGE5_OBLIGATIONS_SCHEMA
PRODUCER = "stage5_obligations"
PUBLIC_SYNC_SCHEMA = "newrouge.b-route-stage5-public-sync.v1"
PUBLIC_SYNC_PENDING_SCHEMA = "newrouge.b-route-stage5-public-sync.v1.pending"
STAGE5_SEMANTICS_SCHEMA = "newrouge.b-route-stage5-obligations-semantics.v1"
PREVIEW_SCHEMA = "newrouge.b-route-stage5-obligations-preview.v1"
EVENTS_BASE = "logs/ci/b-route-stage5-obligations"

STAGE5_OBL_PREFIX = "stage5:obl:v1|"
STAGE4_OBL_PREFIX = ch4_binding.STAGE4_OBL_PREFIX

FLAGS = {
    "readiness": False,
    "runtime_verified": False,
    "default_b_enabled": False,
}

TRIPLET = ch4_binding.TRIPLET

_FILE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_WIN_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
_NA_VALUE_RE = re.compile(
    r"^(?:n/?a|none|null|tbd|todo|skip|exempt|not[-_ ]?applicable|-+|—+)$",
    re.IGNORECASE,
)
_OBL_CATEGORIES = ("existing_required", "current_new", "out_of_scope_future")


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
    """Extract return_stage (3A|3B|3C|4|5) and offending entity from a 6-field Diagnostic dict."""
    actual = diagnostic.get("actual")
    if type(actual) is dict and actual.get("return_stage") in ("3A", "3B", "3C", "4", "5"):
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
            return_stage="5",
        )


def _read_bytes(root: Path, relative: str, *, optional: bool = False) -> bytes | None:
    path = journal._operation_path(root, relative)
    if optional and not path.exists():
        return None
    return codec.read_reference_bytes(root, relative)


def _is_substantive_text(value: Any) -> bool:
    if type(value) is not str:
        return False
    stripped = value.strip()
    if not stripped:
        return False
    return _NA_VALUE_RE.fullmatch(stripped) is None


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
    """Append one deterministic JSONL audit event under logs/ci/b-route-stage5-obligations/<op>/events.jsonl."""
    path = _events_path(root, operation_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "schema_version": "newrouge.b-route-stage5-obligations-event.v1",
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


# ---------------------------------------------------------------------------
# Raw-Byte Public Sync Journal (MVG Manifest Deltas)
# ---------------------------------------------------------------------------


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
        _require(row["kind"] == "mvg_manifest", "mvg_manifest public sync kind", row["kind"], codec.ReasonCode.INVALID_ENUM)
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
    expected_entries = envelope["frozen"]["binding_meta"]["public_sync_entries"]
    _require(
        doc["entries"] == expected_entries,
        "public-sync-journal entries matching frozen binding_meta",
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
    has_changes = bool(envelope["frozen"]["binding_meta"]["has_public_changes"])
    if not has_changes:
        return j_raw is None
    if j_raw is None:
        return False
    doc = codec.strict_json_loads(j_raw)
    return type(doc) is dict and doc.get("phase") == "complete"


def _atomic_write_raw(root: Path, relative: str, raw: bytes, *, recheck) -> None:
    with op_scope.writer_boundary(root, recheck=recheck):
        commit._replace(root, relative, raw)


def apply_public_sync(root: Path | str, *, operation_id: str, _lease_held: bool = False) -> dict[str, Any]:
    """Roll forward reviewed MVG manifest delta updates via public-sync-journal.json + .pending."""
    root_path = Path(root).resolve()
    envelope = journal.read_operation(root_path, operation_id=operation_id)
    _require(
        envelope["schema_version"] == OPERATION_SCHEMA and envelope["state"] == "reserved",
        "reserved stage5_obligations operation",
        operation_id,
        entity_id=operation_id,
        resume_ref=journal._operation_ref(operation_id),
    )
    entries = envelope["frozen"]["binding_meta"]["public_sync_entries"]
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
                    return_stage="5",
                )
            return {"status": "complete", "operation_id": operation_id, "entries": len(entries)}

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
                    return_stage="5",
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
                return_stage="5",
            )
            _checkpoint(f"public_sync_before_file:{idx}")
            after_bytes = _decode_b64(entry["after_base64"])
            assert after_bytes is not None

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
                    return_stage="5",
                )

            _atomic_write_raw(root_path, rel, after_bytes, recheck=_recheck_file)
            _checkpoint(f"public_sync_after_file:{idx}")

        for entry in entries:
            after_now = _read_bytes(root_path, entry["path"])
            assert after_now is not None
            _require(
                codec.raw_digest(after_now) == entry["after_sha256"],
                entry["after_sha256"],
                codec.raw_digest(after_now),
                codec.ReasonCode.DIGEST_MISMATCH,
                entity_id=entry["path"],
                resume_ref=journal_rel,
                return_stage="5",
            )

        if existing_journal["phase"] != "applied":
            applied_journal = _seal_public_sync_journal({**existing_journal, "phase": "applied"})
            applied_raw = projection.serialized(applied_journal)

            def _recheck_applied():
                _require(_read_bytes(root_path, pending_rel) == marker_raw, "durable public-sync.pending.json", pending_rel)
                for e in entries:
                    now_raw = _read_bytes(root_path, e["path"])
                    assert now_raw is not None
                    _require(
                        codec.raw_digest(now_raw) == e["after_sha256"],
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
            return_stage="5",
        )
        _require(
            _read_bytes(root, commit_pending_rel, optional=True) is None,
            "cleaned commit.pending.json before public-sync cleanup",
            commit_pending_rel,
            codec.ReasonCode.INPUT_STALE,
            entity_id=op_id,
            resume_ref=commit_pending_rel,
            return_stage="5",
        )
        _require(
            _read_bytes(root, records.CATALOG_PATH) == catalog_bytes,
            "unchanged published catalog before public-sync cleanup",
            records.CATALOG_PATH,
            codec.ReasonCode.INPUT_STALE,
            entity_id=op_id,
            resume_ref=records.CATALOG_PATH,
            return_stage="5",
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
                return_stage="5",
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
                    return_stage="5",
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
# Clean-Clone Stage-5 Semantics Extractor (Zero logs/ Dependency)
# ---------------------------------------------------------------------------


def _split_stage4_suffix(text: str) -> tuple[str, str | None]:
    """Return (prefix_before_stage4, raw_stage4_json_payload_or_None)."""
    marker = " | " + STAGE4_OBL_PREFIX
    idx = text.find(marker)
    if idx >= 0:
        return text[:idx], text[idx + len(marker) :].strip()
    if text.startswith(STAGE4_OBL_PREFIX):
        return "", text[len(STAGE4_OBL_PREFIX) :].strip()
    return text, None


def _parse_stage5_obl_meta(text: str) -> tuple[str, dict[str, Any]]:
    """Extract (plain_responsibility, stage5_meta) while tolerating a trailing STAGE4_OBL_PREFIX."""
    if not isinstance(text, str):
        return "", {}
    before_s4, _s4_raw = _split_stage4_suffix(text)
    marker = " | " + STAGE5_OBL_PREFIX
    idx = before_s4.find(marker)
    if idx >= 0:
        plain = before_s4[:idx].strip()
        payload = before_s4[idx + len(marker) :].strip()
    elif before_s4.startswith(STAGE5_OBL_PREFIX):
        plain = ""
        payload = before_s4[len(STAGE5_OBL_PREFIX) :].strip()
    else:
        return before_s4.strip(), {}
    parsed = codec.strict_json_loads(payload)
    if type(parsed) is not dict:
        _fail(
            codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
            "JSON object in Stage-5 obligation tag",
            type(parsed).__name__,
            stage=codec.Stage.CONTENT,
            return_stage="5",
        )
    return plain, parsed


def extract_stage5_semantics(
    plan: dict[str, Any],
    binding: dict[str, Any],
    *,
    master_tasks: dict[int, dict[str, Any]] | None = None,
    manifests: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Parse Stage-5 obligations semantics directly from formal plan and binding records.

    Works on clean clones without any logs/ directory. Never writes or copies
    Task status into formal authority; optional master_tasks/manifests compute
    live read-only reverification status on the fly.
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
        return_stage="5",
    )
    _require(
        binding.get("plan_id") == plan.get("plan_id"),
        plan.get("plan_id"),
        binding.get("plan_id"),
        codec.ReasonCode.MAPPING_MISMATCH,
        entity_id=str(binding.get("plan_id")),
        return_stage="5",
    )
    _require(
        binding.get("stage") == "5",
        "binding stage 5",
        binding.get("stage"),
        codec.ReasonCode.SEMANTIC_ERROR,
        entity_id=binding["plan_id"],
        return_stage="5",
    )

    manifest_test_states: dict[str, str] = {}
    if manifests:
        for m_doc in manifests.values():
            for test in m_doc.get("tests", []):
                manifest_test_states[test["id"]] = test["state"]

    obligations_summary: list[dict[str, Any]] = []
    by_category: dict[str, list[dict[str, Any]]] = {cat: [] for cat in _OBL_CATEGORIES}
    unique_tests: set[str] = set()
    unique_obls: set[str] = set()
    obl_by_id: dict[str, dict[str, Any]] = {}

    for obl in binding.get("obligations", []):
        plain_resp, s5_meta = _parse_stage5_obl_meta(obl.get("responsibility", ""))
        s4_meta = ch4_binding._parse_prefixed_json(obl.get("responsibility", ""), STAGE4_OBL_PREFIX) or {}
        category = s5_meta.get("category", "current_new")
        if category not in by_category:
            category = "current_new"
        entry = {
            "id": obl["id"],
            "category": category,
            "requirement_ids": list(obl["requirement_ids"]),
            "flow_ids": list(obl["flow_ids"]),
            "test_ids": list(obl["test_ids"]),
            "responsibility": plain_resp,
            "verification_refs": deepcopy(obl["verification_refs"]),
            "stage5_meta": s5_meta,
            "stage4_meta": s4_meta,
        }
        obligations_summary.append(entry)
        obl_by_id[obl["id"]] = entry
        unique_obls.add(obl["id"])
        unique_tests.update(obl["test_ids"])
        by_category[category].append(
            {
                "obligation_id": obl["id"],
                "flow_ids": sorted(
                    set(obl["flow_ids"])
                    | set(s5_meta.get("manifest_flow_ids", []))
                    | set(s5_meta.get("non_catalog_flow_ids", []))
                    | set(s5_meta.get("out_of_scope_future_flow_ids", []))
                ),
                "test_ids": list(obl["test_ids"]),
                "requirement_ids": list(obl["requirement_ids"]),
            }
        )

    unique_reqs = sorted({r["requirement_id"] for r in plan.get("requirement_verification", [])})
    unique_routes = sorted(
        {(r["requirement_id"], r["flow_id"]) for r in plan.get("requirement_route_memberships", [])}
    )
    unique_evidence = sorted(
        {(r["requirement_id"], r["evidence_id"]) for r in plan.get("requirement_evidence", [])}
    )

    reverification_by_task: list[dict[str, Any]] = []
    for mapping in sorted(binding.get("task_mappings", []), key=lambda m: m["task_id"]):
        tid = mapping["task_id"]
        task_obls = [obl_by_id[oid] for oid in mapping.get("obligation_ids", []) if oid in obl_by_id]
        has_new = any(
            bool(o["stage5_meta"].get("has_new_obligation"))
            or (tid in o["stage5_meta"].get("newly_assigned_task_ids", []))
            for o in task_obls
        )
        planned_tests: set[str] = set()
        for o in task_obls:
            planned_tests.update(o["stage5_meta"].get("planned_test_ids", []))
            for test_id in o["test_ids"]:
                if manifest_test_states.get(test_id) == "planned":
                    planned_tests.add(test_id)
        requires_on_done = bool(has_new or planned_tests or any(
            bool(o["stage5_meta"].get("requires_reverification_on_done")) for o in task_obls
        ))
        is_old_done: bool | None = None
        requires_reverification: bool | None = None
        if master_tasks is not None and tid in master_tasks:
            is_old_done = str(master_tasks[tid].get("status", "")).lower() == "done"
            requires_reverification = bool(is_old_done and requires_on_done)
        reverification_by_task.append(
            {
                "task_id": tid,
                "is_old_done": is_old_done,
                "has_new_obligation": has_new,
                "planned_test_ids": sorted(planned_tests),
                "requires_reverification_on_done": requires_on_done,
                "requires_reverification": requires_reverification,
                "old_done_covers_new_obligations": False,
            }
        )

    retired_items: list[dict[str, Any]] = []
    seen_retired: set[str] = set()
    for entry in obligations_summary:
        for ritem in entry["stage5_meta"].get("retired_items", []):
            rkey = codec.canonical_digest(ritem)
            if rkey not in seen_retired:
                seen_retired.add(rkey)
                retired_items.append(deepcopy(ritem))

    return {
        "schema_version": STAGE5_SEMANTICS_SCHEMA,
        "plan_id": plan["plan_id"],
        "plan_revision": plan["revision"],
        "binding_revision": binding["binding_revision"],
        "stage": binding["stage"],
        "task_ids": sorted(m["task_id"] for m in binding.get("task_mappings", [])),
        "task_mappings": deepcopy(binding.get("task_mappings", [])),
        "manifest_refs": deepcopy(binding.get("manifest_refs", [])),
        "other_verification_refs": deepcopy(binding.get("other_verification_refs", [])),
        "obligations": obligations_summary,
        "impact_classification": by_category,
        "retired_items": retired_items,
        "deduplication": {
            "unique_requirement_ids": unique_reqs,
            "unique_requirement_count": len(unique_reqs),
            "unique_route_pairs": [list(p) for p in unique_routes],
            "unique_route_count": len(unique_routes),
            "unique_evidence_keys": [list(p) for p in unique_evidence],
            "unique_evidence_count": len(unique_evidence),
            "unique_obligation_ids": sorted(unique_obls),
            "unique_test_ids": sorted(unique_tests),
            "unique_test_count": len(unique_tests),
            "double_counting_detected": False,
        },
        "reverification_summary": {
            "status_copied_into_authority": False,
            "tasks": reverification_by_task,
        },
        **FLAGS,
    }


# ---------------------------------------------------------------------------
# Snapshot & Decoupled Manifest Helpers
# ---------------------------------------------------------------------------


class Stage5Snapshot(ch4_binding.Chapter4Snapshot):
    """Tracks raw non-triplet files and triplet definition projections before commit freeze."""


def _validate_manifest_decoupled(
    *,
    root: Path,
    manifest_rel: str,
    manifest_raw: bytes,
    master_tasks: dict[int, dict[str, Any]],
    entity_id: str,
    virtual_files: dict[str, bytes] | None = None,
) -> tuple[dict[str, Any], str]:
    obs = preflight.Observations(root)
    return input_set._validate_mvg_manifest_decoupled(
        root=root,
        manifest_rel=manifest_rel,
        manifest_raw=manifest_raw,
        observations=obs,
        master_tasks=master_tasks,
        entity_id=entity_id,
        candidate_overlay=virtual_files,
    )


def _verify_owned_ref(
    root: Path,
    ref: dict[str, Any],
    *,
    snapshot: Stage5Snapshot,
    virtual_files: dict[str, bytes] | None = None,
    entity_id: str | None = None,
    return_stage: str = "5",
) -> list[tuple[str, bytes, str]]:
    """Verify OwnedRef syntax, file containment, locator semantics, and exact raw_digest."""
    vfiles = virtual_files or {}
    _require(
        type(ref) is dict and set(ref) == {"owner", "ref", "files"},
        "valid OwnedRef object",
        ref,
        codec.ReasonCode.INVALID_REFERENCE,
        entity_id=entity_id,
        return_stage=return_stage,
    )
    files = ref["files"]
    _require(
        type(files) is list and bool(files),
        "nonempty OwnedRef.files",
        ref,
        codec.ReasonCode.INVALID_REFERENCE,
        entity_id=entity_id,
        return_stage=return_stage,
    )
    if ref["owner"] != "contract":
        ref_loc = ref["ref"].partition("#")[0]
        _require(
            _is_substantive_text(ref_loc),
            "non-empty non-N/A OwnedRef.ref locator",
            ref["ref"],
            codec.ReasonCode.INVALID_REFERENCE,
            entity_id=entity_id,
            return_stage=return_stage,
        )

    def _rb(rel_p: str) -> bytes:
        norm = codec.validate_reference_path(rel_p)
        if norm in vfiles:
            return vfiles[norm]
        raw = snapshot.read(norm)
        assert raw is not None
        return raw

    def _contracts() -> dict[str, bytes]:
        return records._Bytes(vfiles, root).contracts()

    try:
        record_owners.resolve_owned_ref(ref, read_bytes=_rb, contract_sources=_contracts)
    except codec.CodecError as err:
        _fail(
            err.diagnostic.reason_code,
            err.diagnostic.expected,
            err.diagnostic.actual,
            entity_id=entity_id or err.diagnostic.entity_id,
            resume_ref=err.diagnostic.resume_ref or ref["ref"],
            stage=err.diagnostic.stage,
            return_stage=return_stage,
        )

    observed: list[tuple[str, bytes, str]] = []
    for row in files:
        rel = codec.validate_reference_path(row["path"])
        raw = _rb(rel)
        dg = codec.raw_digest(raw)
        _require(
            dg == row["raw_digest"],
            row["raw_digest"],
            dg,
            codec.ReasonCode.DIGEST_MISMATCH,
            entity_id=entity_id,
            resume_ref=rel,
            stage=codec.Stage.REFERENCE,
            return_stage=return_stage,
        )
        observed.append((rel, raw, dg))
    return observed


def _validate_reviewed_authority_entry(
    root: Path,
    snapshot: Stage5Snapshot,
    retirement: dict[str, Any],
    *,
    entity_id: str,
) -> dict[str, Any]:
    """Enforce reviewed specification authority_ref + rationale for any obligation reduction."""
    auth_ref = retirement.get("authority_ref")
    review = retirement.get("authority_review")
    _require(
        _is_substantive_text(auth_ref),
        "repository-relative specification authority_ref for obligation reduction",
        auth_ref,
        codec.ReasonCode.SEMANTIC_ERROR,
        entity_id=entity_id,
        return_stage="5",
    )
    _require(
        type(review) is dict,
        "authority_review object with status='reviewed' and rationale",
        review,
        codec.ReasonCode.SEMANTIC_ERROR,
        entity_id=entity_id,
        return_stage="5",
    )
    status = str(review.get("status") or "").strip().lower()
    rationale = review.get("rationale")
    _require(
        status == "reviewed",
        "authority_review.status == 'reviewed'",
        status,
        codec.ReasonCode.SEMANTIC_ERROR,
        entity_id=entity_id,
        return_stage="5",
    )
    _require(
        _is_substantive_text(rationale),
        "non-empty substantive reviewed rationale for obligation reduction",
        rationale,
        codec.ReasonCode.SEMANTIC_ERROR,
        entity_id=entity_id,
        return_stage="5",
    )
    assert isinstance(auth_ref, str)
    auth_path_text = auth_ref.split("#", 1)[0].strip()
    _require(
        bool(auth_path_text),
        "repository-relative specification path in authority_ref",
        auth_ref,
        codec.ReasonCode.INVALID_REFERENCE,
        entity_id=entity_id,
        return_stage="5",
    )
    norm_auth = codec.validate_reference_path(auth_path_text)
    _require(
        not norm_auth.casefold().startswith("logs/"),
        "non-log formal specification path in retirement authority_ref",
        auth_ref,
        codec.ReasonCode.UNSAFE_PATH,
        entity_id=entity_id,
        resume_ref=norm_auth,
        return_stage="5",
    )
    raw = snapshot.read(norm_auth, optional=True)
    _require(
        raw is not None and bool(raw.strip()),
        f"existing non-empty specification file at authority_ref {norm_auth}",
        auth_ref,
        codec.ReasonCode.UNRESOLVED_REFERENCE,
        entity_id=entity_id,
        resume_ref=norm_auth,
        return_stage="5",
    )
    assert raw is not None
    raw_dg = codec.raw_digest(raw)
    authority_owned_ref = {
        "owner": "authority",
        "ref": auth_ref.strip(),
        "files": [{"path": norm_auth, "raw_digest": raw_dg}],
    }
    _verify_owned_ref(
        root,
        authority_owned_ref,
        snapshot=snapshot,
        virtual_files=None,
        entity_id=entity_id,
        return_stage="5",
    )
    return {
        "kind": retirement["kind"],
        "target_id": retirement["target_id"],
        "obligation_id": retirement.get("obligation_id"),
        "authority_ref": auth_ref.strip(),
        "authority_path": norm_auth,
        "authority_digest": raw_dg,
        "rationale": rationale.strip(),
        "authority_owned_ref": authority_owned_ref,
    }


_REFS_SEGMENT_RE = re.compile(r"\bRefs\s*:\s*(.+)$", re.IGNORECASE)


def _collect_task_touched_paths(
    *,
    root: Path,
    prior_binding: dict[str, Any],
    triplet: dict[str, Any],
    conserved_task_ids: list[int],
    virtual_files: dict[str, bytes] | None = None,
) -> set[str]:
    """Extract repository-relative paths touched by conserved Tasks' objects, contractRefs, test_refs, and Refs:."""
    vfiles = virtual_files or {}
    paths: set[str] = set()

    def _try_add_existing(candidate: str) -> None:
        cleaned = candidate.strip().strip("`\"'.,;()[]")
        if not cleaned:
            return
        cleaned = cleaned.split("#", 1)[0].strip()
        if "/" not in cleaned:
            return
        try:
            norm = codec.validate_reference_path(cleaned)
        except codec.CodecError:
            return
        if norm in vfiles:
            paths.add(norm)
            return
        try:
            disk_path = journal._operation_path(root, norm)
        except codec.CodecError:
            return
        if disk_path.is_file():
            paths.add(norm)

    for obj in prior_binding.get("implementation_objects", []):
        tref = obj.get("target_ref")
        if type(tref) is dict:
            for frow in tref.get("files", []):
                if type(frow) is dict and type(frow.get("path")) is str:
                    paths.add(codec.validate_reference_path(frow["path"]))
    contract_files_dir = root / "Game.Core/Contracts"
    contract_sources: dict[str, bytes] | None = None
    for tid in conserved_task_ids:
        back_rows = [r for r in triplet["docs"]["back"] if r["taskmaster_id"] == tid]
        gameplay_rows = [r for r in triplet["docs"]["gameplay"] if r["taskmaster_id"] == tid]
        rows = [triplet["master"][tid], *back_rows, *gameplay_rows]
        for row in rows:
            for tref_path in row.get("test_refs") or []:
                if type(tref_path) is str:
                    _try_add_existing(tref_path)
            for cref in row.get("contractRefs") or []:
                if type(cref) is str and cref.strip():
                    if contract_sources is None and contract_files_dir.is_dir():
                        contract_sources = records._Bytes({}, root).contracts()
                    if contract_sources:
                        bound = contract_bindings.resolve_contract(root, cref.strip(), sources=contract_sources)
                        if bound is not None:
                            for brow in bound["bindings"]:
                                paths.add(codec.validate_reference_path(brow["path"]))
        for vrow in (*back_rows, *gameplay_rows):
            for acc in vrow.get("acceptance") or []:
                if type(acc) is not str:
                    continue
                match = _REFS_SEGMENT_RE.search(acc)
                if match is None:
                    continue
                for raw_tok in re.split(r"[\s,;]+", match.group(1)):
                    if raw_tok:
                        _try_add_existing(raw_tok)
    return paths


# ---------------------------------------------------------------------------
# Core Build & Verification Engine
# ---------------------------------------------------------------------------


def build(
    root: Path | str,
    request: dict[str, Any],
    *,
    allocations: dict[str, Any] | None = None,
    inventory_ops: list[dict[str, Any]] | None = None,
    read_operation_id: str | None = None,
    saved_public_sync: list[dict[str, Any]] | None = None,
    _held_scopes: set[str] | None = None,
) -> tuple[Stage5Snapshot, dict[str, Any], dict[str, Any]]:
    """Build and verify a complete Stage-5 obligations binding frozen operation."""
    root = Path(root).resolve()
    journal._operation_schema(request, "Request", schema_id=OPERATION_SCHEMA)
    operation_id = _validate_file_id(request["operation_id"], "operation_id")
    plan_id = _validate_file_id(request["plan_id"], "plan_id")
    scope_id = request["scope_id"]
    codec.validate_business_id(scope_id)

    op_scope._legacy_pending(root, None)
    snapshot = Stage5Snapshot(root)

    pre_sync_overrides: dict[str, bytes] | None = None
    if saved_public_sync:
        pre_sync_overrides = {}
        for entry in saved_public_sync:
            before_raw = _decode_b64(entry["before_base64"])
            if before_raw is not None:
                pre_sync_overrides[entry["path"]] = before_raw

    # 1. Load committed catalog, policy, origins, and Taskmaster triplet.
    catalog_raw = snapshot.read(records.CATALOG_PATH)
    policy_raw = snapshot.read(records.BASE + "policy.v1.json")
    origins_raw = snapshot.read(records.BASE + "task-origins.v1.json")
    assert catalog_raw is not None and policy_raw is not None and origins_raw is not None
    catalog = codec.strict_json_loads(catalog_raw)
    origins = codec.strict_json_loads(origins_raw)
    triplet = ch4_binding._load_triplet(snapshot)

    records.published_bundle(
        root,
        catalog_raw=catalog_raw,
        scope_ids=[scope_id],
        task_join=triplet["join"],
        extra_candidates=pre_sync_overrides,
    )

    scope_head = next((h for h in catalog["scope_heads"] if h["scope_id"] == scope_id), None)
    _require(
        scope_head is not None,
        f"published scope_head for {scope_id}",
        scope_id,
        codec.ReasonCode.UNPUBLISHED,
        entity_id=plan_id,
        resume_ref=records.CATALOG_PATH,
        return_stage="3B",
    )
    assert scope_head is not None

    plan_ref = next((ref for ref in scope_head["plan_refs"] if ref["entity_id"] == plan_id), None)
    _require(
        plan_ref is not None,
        f"committed 3B plan_ref for {plan_id} in {scope_id}",
        plan_id,
        codec.ReasonCode.UNPUBLISHED,
        entity_id=plan_id,
        resume_ref=records.CATALOG_PATH,
        return_stage="3B",
    )
    prior_binding_ref = next((ref for ref in scope_head["binding_refs"] if ref["entity_id"] == plan_id), None)
    _require(
        prior_binding_ref is not None,
        f"committed stage=4|5 binding_ref for {plan_id} in {scope_id}",
        plan_id,
        codec.ReasonCode.UNPUBLISHED,
        entity_id=plan_id,
        resume_ref=records.CATALOG_PATH,
        return_stage="4",
    )
    assert plan_ref is not None and prior_binding_ref is not None

    plan_raw = snapshot.read(plan_ref["path"])
    prior_binding_raw = snapshot.read(prior_binding_ref["path"])
    assert plan_raw is not None and prior_binding_raw is not None
    plan = codec.strict_json_loads(plan_raw)
    prior_binding = codec.strict_json_loads(prior_binding_raw)

    # Never skip Stage 4: require committed stage="4"|"5" binding!
    _require(
        prior_binding.get("stage") in ("4", "5"),
        "committed Stage-4 or Stage-5 binding before Stage-5 obligations binding",
        {"plan_id": plan_id, "prior_stage": prior_binding.get("stage")},
        codec.ReasonCode.SEMANTIC_ERROR,
        entity_id=plan_id,
        resume_ref=prior_binding_ref["path"],
        return_stage="4",
    )
    # Validate Stage-4 foundation directly from formal plan + prior_binding.
    ch4_binding.extract_stage4_semantics(plan, prior_binding)

    conserved_task_ids = sorted(m["task_id"] for m in prior_binding["task_mappings"])
    _require(
        bool(conserved_task_ids),
        "nonempty conserved Task set in Stage-4/5 binding",
        plan_id,
        codec.ReasonCode.MAPPING_MISMATCH,
        entity_id=plan_id,
        resume_ref=prior_binding_ref["path"],
        return_stage="3C",
    )

    # 2. Verify every conserved Task resolves as route="B" via Story 3.3 (respecting active operation context).
    origins_by_tid: dict[int, dict[str, Any]] = {}
    with commit.read_operation_context(read_operation_id, pre_sync_bytes=pre_sync_overrides):
        for tid in conserved_task_ids:
            origin = task_resolver.resolve_task_origin(root, tid)
            if not origin["ok"] or not origin["stable"] or origin["route"] != "B":
                first_diag = origin["diagnostics"][0] if origin["diagnostics"] else None
                if first_diag is not None:
                    code = codec.ReasonCode(first_diag["reason_code"])
                    rstage = "3C" if origin["route"] in ("A", "explicit_not_enabled_a") else None
                    _fail(
                        code,
                        first_diag["expected"],
                        first_diag["actual"],
                        entity_id=first_diag.get("entity_id") or str(tid),
                        resume_ref=first_diag.get("resume_ref"),
                        stage=codec.Stage(first_diag["stage"]) if first_diag.get("stage") else codec.Stage.BUNDLE,
                        return_stage=rstage,
                    )
                _fail(
                    codec.ReasonCode.CONFLICT,
                    "Story 3.3 route='B' for every conserved Task",
                    {"task_id": tid, "route": origin["route"]},
                    entity_id=str(tid),
                    resume_ref=records.BASE + "task-origins.v1.json",
                    return_stage="3C",
                )
            origins_by_tid[tid] = origin

    # 3. Check 3B plan dispositions: block source_gap immediately (return_stage="3A").
    plan_reqs_by_id = {r["requirement_id"]: r for r in plan["requirements"]}
    plan_verif_by_req = {r["requirement_id"]: r for r in plan["requirement_verification"]}
    plan_app_by_req = {r["requirement_id"]: r for r in plan["applicability"]}
    plan_ev_refs = {(r["owner"], r["ref"]): r for r in plan["evidence_source_refs"]}
    plan_routes_by_req: dict[str, set[str]] = {}
    for row in plan["requirement_route_memberships"]:
        plan_routes_by_req.setdefault(row["requirement_id"], set()).add(row["flow_id"])

    mapped_req_ids: set[str] = set()
    for m in prior_binding["task_mappings"]:
        mapped_req_ids.update(m["requirement_ids"])
    for rid in sorted(mapped_req_ids | set(plan_verif_by_req)):
        vrow = plan_verif_by_req.get(rid)
        if vrow is not None and vrow["disposition"] == "source_gap":
            _fail(
                codec.ReasonCode.SEMANTIC_ERROR,
                "resolved 3A/3B requirement disposition (source_gap blocks Stage-5 binding)",
                {"plan_id": plan_id, "requirement_id": rid, "disposition": "source_gap"},
                entity_id=rid,
                resume_ref=plan_ref["path"],
                return_stage="3A",
            )

    # 4. Process optional manifest_deltas through update_mvg_baseline.apply_delta -> public_sync_entries.
    virtual_files: dict[str, bytes] = {}
    sync_entries: list[dict[str, Any]] = []
    public_sync_path_set: set[str] = set()
    delta_specs = list(request.get("manifest_deltas") or [])
    saved_sync_by_path = {e["path"]: e for e in (saved_public_sync or [])}
    seen_delta_paths: set[str] = set()

    for dspec in delta_specs:
        m_path = codec.validate_reference_path(dspec["manifest_path"])
        _require(
            m_path.casefold() not in seen_delta_paths,
            "unique manifest_path across manifest_deltas",
            m_path,
            codec.ReasonCode.CONFLICT,
            entity_id=m_path,
            resume_ref=m_path,
            return_stage="5",
        )
        seen_delta_paths.add(m_path.casefold())

        if m_path in saved_sync_by_path:
            before_raw = _decode_b64(saved_sync_by_path[m_path]["before_base64"])
        else:
            before_raw = snapshot.read(m_path, optional=True)
        _require(
            before_raw is not None,
            f"existing MVG manifest before delta at {m_path}",
            m_path,
            codec.ReasonCode.FILE_NOT_FOUND,
            entity_id=m_path,
            resume_ref=m_path,
            return_stage="5",
        )
        assert before_raw is not None
        if dspec.get("expected_manifest_sha256"):
            actual_before_sha = mvg_manifest.manifest_sha256(before_raw)
            _require(
                actual_before_sha == dspec["expected_manifest_sha256"],
                dspec["expected_manifest_sha256"],
                actual_before_sha,
                codec.ReasonCode.INPUT_STALE,
                entity_id=m_path,
                resume_ref=m_path,
                return_stage="5",
            )
        before_doc = codec.strict_json_loads(before_raw)
        try:
            updated_doc = update_mvg_baseline.apply_delta(
                before_doc,
                dspec["delta"],
                root=root,
                validate_final=False,
            )
        except ValueError as exc:
            msg = str(exc)
            code = codec.ReasonCode.INPUT_STALE if "changed after delta review" in msg else codec.ReasonCode.SEMANTIC_ERROR
            _fail(
                code,
                "reviewed anti-weakening MVG baseline delta passing update_mvg_baseline.apply_delta",
                {"manifest_path": m_path, "error": msg},
                entity_id=m_path,
                resume_ref=m_path,
                return_stage="5",
            )
        after_raw = projection.serialized(updated_doc)
        _validate_manifest_decoupled(
            root=root,
            manifest_rel=m_path,
            manifest_raw=after_raw,
            master_tasks=triplet["master"],
            entity_id=m_path,
            virtual_files={**virtual_files, m_path: after_raw},
        )
        entry = {
            "path": m_path,
            "kind": "mvg_manifest",
            "before_sha256": codec.raw_digest(before_raw),
            "before_base64": _encode_b64(before_raw),
            "after_sha256": codec.raw_digest(after_raw),
            "after_base64": _encode_b64(after_raw),
        }
        if m_path in saved_sync_by_path:
            _require(
                saved_sync_by_path[m_path] == entry,
                "saved public_sync entry matching recomputed manifest delta",
                m_path,
                codec.ReasonCode.INPUT_STALE,
                entity_id=m_path,
                resume_ref=m_path,
                return_stage="5",
            )
            disk_now = _read_bytes(root, m_path)
            assert disk_now is not None
            _require(
                codec.raw_digest(disk_now) == entry["after_sha256"],
                entry["after_sha256"],
                codec.raw_digest(disk_now),
                codec.ReasonCode.INPUT_STALE,
                entity_id=m_path,
                resume_ref=m_path,
                return_stage="5",
            )
        sync_entries.append(entry)
        public_sync_path_set.add(m_path)
        virtual_files[m_path] = after_raw

    # 5. Load & validate all bound manifest_refs and impact_analysis.cumulative_manifest_refs.
    expected_m_shas = dict(request.get("expected_manifest_sha256") or {})
    impact = request.get("impact_analysis") or {}
    bound_manifest_refs = deepcopy(list(request.get("manifest_refs") or []))
    cumulative_manifest_refs = deepcopy(list(impact.get("cumulative_manifest_refs") or []))

    # Deduplicate manifest_refs by canonical digest while rejecting conflicting digests for same path.
    def _load_manifest_refs(refs_list: list[dict[str, Any]], *, label: str) -> dict[str, tuple[dict[str, Any], bytes, dict[str, Any], str]]:
        loaded: dict[str, tuple[dict[str, Any], bytes, dict[str, Any], str]] = {}
        for mref in refs_list:
            _require(
                type(mref) is dict and mref.get("owner") == "manifest",
                f"ManifestRef with owner='manifest' in {label}",
                mref,
                codec.ReasonCode.INVALID_REFERENCE,
                entity_id=plan_id,
                return_stage="5",
            )
            obs_rows = _verify_owned_ref(
                root,
                mref,
                snapshot=snapshot,
                virtual_files=virtual_files,
                entity_id=plan_id,
                return_stage="5",
            )
            for m_rel, m_raw, _m_raw_dg in obs_rows:
                m_doc, m_sha = _validate_manifest_decoupled(
                    root=root,
                    manifest_rel=m_rel,
                    manifest_raw=m_raw,
                    master_tasks=triplet["master"],
                    entity_id=m_rel,
                    virtual_files=virtual_files,
                )
                if m_rel in expected_m_shas:
                    _require(
                        m_sha == expected_m_shas[m_rel],
                        expected_m_shas[m_rel],
                        m_sha,
                        codec.ReasonCode.DIGEST_MISMATCH,
                        entity_id=m_rel,
                        resume_ref=m_rel,
                        return_stage="5",
                    )
                if m_rel in loaded:
                    _require(
                        loaded[m_rel][3] == m_sha,
                        loaded[m_rel][3],
                        m_sha,
                        codec.ReasonCode.CONFLICT,
                        entity_id=m_rel,
                        resume_ref=m_rel,
                        return_stage="5",
                    )
                else:
                    loaded[m_rel] = (mref, m_raw, m_doc, m_sha)
        return loaded

    bound_manifests = _load_manifest_refs(bound_manifest_refs, label="manifest_refs")
    # Also harvest any manifest refs embedded directly on obligations[].verification_refs.
    for ospec in request.get("obligations") or []:
        for vref in ospec.get("verification_refs") or []:
            if type(vref) is dict and vref.get("owner") == "manifest":
                extra_loaded = _load_manifest_refs([vref], label=f"obligations[{ospec['id']}].verification_refs")
                for m_rel, tup in extra_loaded.items():
                    if m_rel not in bound_manifests:
                        bound_manifests[m_rel] = tup
                        bound_manifest_refs.append(deepcopy(vref))

    cumulative_manifests = _load_manifest_refs(cumulative_manifest_refs, label="impact_analysis.cumulative_manifest_refs")

    # Auto-discover existing repository MVG manifests under docs/testing/mvg/*.json so omitting or
    # subsetting cumulative_manifest_refs cannot bypass Flow impact detection or conservative expansion.
    repo_manifests: dict[str, dict[str, Any]] = {}
    mvg_dir = root / "docs/testing/mvg"
    discovered_rels: set[str] = set()
    if mvg_dir.is_dir():
        for child in sorted(mvg_dir.glob("*.json")):
            if child.is_file() and not child.is_symlink():
                discovered_rels.add(child.relative_to(root).as_posix())
    for vrel in virtual_files:
        if vrel.startswith("docs/testing/mvg/") and vrel.endswith(".json") and vrel.count("/") == 3:
            discovered_rels.add(vrel)
    for m_rel in sorted(discovered_rels):
        if m_rel in bound_manifests:
            repo_manifests[m_rel] = bound_manifests[m_rel][2]
            continue
        if m_rel in cumulative_manifests:
            repo_manifests[m_rel] = cumulative_manifests[m_rel][2]
            continue
        if m_rel in virtual_files:
            m_raw = virtual_files[m_rel]
        else:
            m_raw = snapshot.read(m_rel, optional=True)
        if m_raw is None:
            continue
        try:
            cand_doc = codec.strict_json_loads(m_raw)
        except codec.CodecError:
            continue
        if type(cand_doc) is not dict or cand_doc.get("schema_version") != mvg_manifest.SCHEMA:
            continue
        m_doc, _m_sha = _validate_manifest_decoupled(
            root=root,
            manifest_rel=m_rel,
            manifest_raw=m_raw,
            master_tasks=triplet["master"],
            entity_id=m_rel,
            virtual_files=virtual_files,
        )
        repo_manifests[m_rel] = m_doc

    all_manifests: dict[str, dict[str, Any]] = {
        **repo_manifests,
        **{m_rel: tup[2] for m_rel, tup in cumulative_manifests.items()},
        **{m_rel: tup[2] for m_rel, tup in bound_manifests.items()},
    }
    bound_manifest_docs: dict[str, dict[str, Any]] = {m_rel: tup[2] for m_rel, tup in bound_manifests.items()}

    # Index bound manifest flows, tests, and required_flow_ids.
    bound_manifest_flows: dict[str, dict[str, Any]] = {}
    bound_manifest_tests: dict[str, dict[str, Any]] = {}
    bound_required_flow_ids: set[str] = set()
    for m_rel in sorted(bound_manifest_docs):
        m_doc = bound_manifest_docs[m_rel]
        bound_required_flow_ids.update(m_doc.get("coverage", {}).get("required_flow_ids", []))
        for flow in m_doc["flows"]:
            bound_manifest_flows[flow["id"]] = flow
        for test in m_doc["tests"]:
            bound_manifest_tests[test["id"]] = test

    # Index cumulative manifest flows and tests (for non-Flow impact matching / conservative expansion).
    cumulative_flows: dict[str, tuple[str, dict[str, Any]]] = {}
    cumulative_tests_by_flow: dict[str, set[str]] = {}
    cumulative_all_tests: set[str] = set()
    for m_rel in sorted(all_manifests):
        m_doc = all_manifests[m_rel]
        for flow in m_doc["flows"]:
            cumulative_flows[flow["id"]] = (m_rel, flow)
            cumulative_tests_by_flow.setdefault(flow["id"], set()).update(flow["test_ids"])
        for test in m_doc["tests"]:
            cumulative_all_tests.add(test["id"])

    # 6. Determine Flow plan status, Flow impact, conservative expansion, and future obligations.
    plan_flow_reqs = {rid for rid, v in plan_verif_by_req.items() if v["disposition"] == "flow"}
    plan_disp_flows = {v["flow_id"] for v in plan_verif_by_req.values() if v["disposition"] == "flow" and v["flow_id"]}
    plan_route_flows = {r["flow_id"] for r in plan["requirement_route_memberships"]}
    plan_mapped_flows = {fid for m in prior_binding["task_mappings"] for fid in m["flow_ids"]}
    plan_has_integration_owner = any("integration_only_owner" in m["roles"] for m in prior_binding["task_mappings"])
    is_flow_plan = bool(plan_flow_reqs or plan_disp_flows or plan_route_flows or plan_mapped_flows or plan_has_integration_owner)

    extracted_paths = _collect_task_touched_paths(
        root=root,
        prior_binding=prior_binding,
        triplet=triplet,
        conserved_task_ids=conserved_task_ids,
        virtual_files=virtual_files,
    )
    touched_paths = sorted(
        extracted_paths
        | {codec.validate_reference_path(p) for p in (impact.get("touched_paths") or [])}
        | {codec.validate_reference_path(p) for p in (impact.get("touched_contracts") or [])}
        | {codec.validate_reference_path(p) for p in (impact.get("touched_tests") or [])}
    )
    touched_chains = set(impact.get("touched_consumer_chains") or [])
    unknown_reason = str(impact.get("unknown_impact_reason") or "").strip()
    reverse_impact_known = impact.get("reverse_impact_known")

    hit_flows: set[str] = set()
    hit_manifest_paths: set[str] = set()
    expanded_required_flows: set[str] = set()
    expanded_required_tests: set[str] = set()
    impact_mode = "direct_flow" if is_flow_plan else "non_flow_zero_impact"

    def _scan_direct_impact() -> None:
        matched_chains: set[str] = set()
        for m_rel, m_doc in all_manifests.items():
            rec = mvg_manifest.recommend(m_doc, touched_paths, unknown_reason="")
            matched_in_m = set(rec["matched_flows"])
            for flow in m_doc["flows"]:
                flow_hit = False
                if flow["id"] in touched_chains:
                    flow_hit = True
                    matched_chains.add(flow["id"])
                for ftid in flow["task_ids"]:
                    t_tok = f"task:{ftid}"
                    if t_tok in touched_chains:
                        flow_hit = True
                        matched_chains.add(t_tok)
                for edge in flow["handoffs"]:
                    if edge["contract_ref"] in touched_chains:
                        flow_hit = True
                        matched_chains.add(edge["contract_ref"])
                if flow_hit:
                    matched_in_m.add(flow["id"])
            if matched_in_m:
                hit_flows.update(matched_in_m)
                hit_manifest_paths.add(m_rel)
        unmatched_chains = sorted(touched_chains - matched_chains)
        _require(
            not unmatched_chains,
            "bound MVG manifest covering every touched_consumer_chains entry",
            unmatched_chains,
            codec.ReasonCode.UNRESOLVED_REFERENCE,
            entity_id=plan_id,
            return_stage="5",
        )

    if not is_flow_plan:
        if reverse_impact_known is False or bool(unknown_reason):
            # Unknown reverse impact: MUST conservatively expand to full cumulative manifest scope (no waiting for Epic 4).
            _require(
                bool(all_manifests),
                "cumulative MVG manifest for conservative full-scope expansion when reverse impact is unknown",
                {"reverse_impact_known": reverse_impact_known, "unknown_impact_reason": unknown_reason},
                codec.ReasonCode.IDENTITY_UNPROVABLE,
                entity_id=plan_id,
                return_stage="5",
            )
            impact_mode = "conservative_full_cumulative_expansion"
            for m_rel, m_doc in all_manifests.items():
                hit_manifest_paths.add(m_rel)
                for flow in m_doc["flows"]:
                    expanded_required_flows.add(flow["id"])
                for test in m_doc["tests"]:
                    expanded_required_tests.add(test["id"])
        elif reverse_impact_known is None:
            _fail(
                codec.ReasonCode.IDENTITY_UNPROVABLE,
                "explicit impact_analysis.reverse_impact_known (true with zero-impact proof, or false with cumulative manifest expansion)",
                {"plan_id": plan_id, "impact_analysis": impact},
                entity_id=plan_id,
                return_stage="5",
            )
        else:
            # reverse_impact_known is True: run _mvg_manifest.recommend + consumer chain check across all known manifests.
            _scan_direct_impact()
            if hit_flows:
                impact_mode = "non_flow_touches_flow_regression"
    else:
        # Flow plan: also honor conservative expansion if reverse_impact_known is explicitly False!
        if reverse_impact_known is False or bool(unknown_reason):
            _require(
                bool(all_manifests),
                "cumulative MVG manifest for conservative full-scope expansion",
                {"reverse_impact_known": reverse_impact_known, "unknown_impact_reason": unknown_reason},
                codec.ReasonCode.IDENTITY_UNPROVABLE,
                entity_id=plan_id,
                return_stage="5",
            )
            impact_mode = "flow_plus_conservative_full_expansion"
            for m_rel, m_doc in all_manifests.items():
                hit_manifest_paths.add(m_rel)
                for flow in m_doc["flows"]:
                    expanded_required_flows.add(flow["id"])
                for test in m_doc["tests"]:
                    expanded_required_tests.add(test["id"])
        elif touched_paths or touched_chains:
            _scan_direct_impact()

    # Validate future_obligations in impact_analysis (must never force immediate implementation or claim pass).
    future_specs = list(impact.get("future_obligations") or [])
    for fspec in future_specs:
        fid = fspec["flow_id"]
        _require(
            not fspec.get("force_implement_now", False),
            "out_of_scope_future obligation must not force immediate implementation",
            {"flow_id": fid, "force_implement_now": True},
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=fid,
            return_stage="5",
        )
        _require(
            not fspec.get("claimed_passed", False),
            "out_of_scope_future obligation must not claim runtime pass",
            {"flow_id": fid, "claimed_passed": True},
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=fid,
            return_stage="5",
        )
        _require(
            fid not in bound_required_flow_ids and fid not in hit_flows and fid not in expanded_required_flows,
            "existing required or impacted flow cannot be downgraded to out_of_scope_future",
            {"flow_id": fid},
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=fid,
            return_stage="5",
        )

    # 7. Validate obligations list, categories, anti-N/A/label exemption, and deduplication.
    req_obligations = list(request.get("obligations") or [])
    _require(
        bool(req_obligations),
        "at least one governed Stage-5 obligation",
        plan_id,
        codec.ReasonCode.SEMANTIC_ERROR,
        entity_id=plan_id,
        return_stage="5",
    )

    conserved_set = set(conserved_task_ids)
    catalog_flow_ids = {r["definition_id"] for r in catalog["definition_owners"] if r["kind"] == "flow"}
    seen_obl_ids: set[str] = set()
    covered_flows_in_obls: set[str] = set()
    covered_tests_in_obls: set[str] = set()
    covered_reqs_in_obls: set[str] = set()
    tests_by_flow_in_obls: dict[str, set[str]] = {}
    obls_by_tid: dict[int, list[dict[str, Any]]] = {tid: [] for tid in conserved_task_ids}

    for ospec in req_obligations:
        oid = ospec["id"]
        _require(
            oid not in seen_obl_ids,
            "unique obligation IDs in Stage-5 request",
            oid,
            codec.ReasonCode.MAPPING_MISMATCH,
            entity_id=oid,
            return_stage="5",
        )
        seen_obl_ids.add(oid)
        _require(
            not ospec.get("claimed_passed", False),
            "Stage-5 binding never claims runtime pass",
            {"obligation_id": oid, "claimed_passed": True},
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=oid,
            return_stage="5",
        )
        cat = ospec["category"]
        _require(
            cat in _OBL_CATEGORIES,
            list(_OBL_CATEGORIES),
            cat,
            codec.ReasonCode.INVALID_ENUM,
            entity_id=oid,
            return_stage="5",
        )
        if cat == "out_of_scope_future":
            _require(
                not ospec.get("force_implement_now", False),
                "out_of_scope_future obligation must not force immediate implementation",
                {"obligation_id": oid, "force_implement_now": True},
                codec.ReasonCode.SEMANTIC_ERROR,
                entity_id=oid,
                return_stage="5",
            )
            for fid in ospec["flow_ids"]:
                _require(
                    fid not in bound_required_flow_ids and fid not in hit_flows and fid not in expanded_required_flows,
                    "existing required or impacted flow cannot be classified as out_of_scope_future",
                    {"obligation_id": oid, "flow_id": fid},
                    codec.ReasonCode.SEMANTIC_ERROR,
                    entity_id=oid,
                    return_stage="5",
                )
        ex_basis = ospec.get("exemption_basis")
        if ex_basis is not None:
            _require(
                ex_basis == "3b_applicability",
                "exemption_basis must be '3b_applicability' (labels/N/A/none cannot exempt MVG)",
                {"obligation_id": oid, "exemption_basis": ex_basis},
                codec.ReasonCode.SEMANTIC_ERROR,
                entity_id=oid,
                return_stage="5",
            )
        if ospec.get("exemption_rationale") is not None:
            _require(
                _is_substantive_text(ospec["exemption_rationale"]),
                "substantive non-N/A exemption_rationale",
                {"obligation_id": oid, "exemption_rationale": ospec["exemption_rationale"]},
                codec.ReasonCode.SEMANTIC_ERROR,
                entity_id=oid,
                return_stage="5",
            )
        _require(
            _is_substantive_text(ospec["responsibility"]),
            "substantive non-N/A obligation responsibility",
            {"obligation_id": oid, "responsibility": ospec["responsibility"]},
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=oid,
            return_stage="5",
        )
        # No duplicate requirement_ids / flow_ids / test_ids inside one obligation (anti-double-counting).
        for list_field in ("requirement_ids", "flow_ids", "test_ids"):
            vals = ospec[list_field]
            _require(
                len(vals) == len(set(vals)),
                f"deduplicated {list_field} in obligation {oid}",
                vals,
                codec.ReasonCode.MAPPING_MISMATCH,
                entity_id=oid,
                return_stage="5",
            )
        for tid in ospec["task_ids"]:
            _require(
                tid in conserved_set,
                "conserved Stage-4/5 task_id in obligation task_ids",
                {"obligation_id": oid, "task_id": tid, "conserved_task_ids": conserved_task_ids},
                codec.ReasonCode.MAPPING_MISMATCH,
                entity_id=str(tid),
                return_stage="3C",
            )
            obls_by_tid[tid].append(ospec)
        for rid in ospec["requirement_ids"]:
            _require(
                rid in plan_reqs_by_id,
                "declared plan.requirements ID in obligation",
                {"obligation_id": oid, "requirement_id": rid},
                codec.ReasonCode.MAPPING_MISMATCH,
                entity_id=oid,
                return_stage="3B",
            )
            _require(
                plan_verif_by_req[rid]["disposition"] != "source_gap",
                "non-source_gap disposition for obligation requirement",
                {"obligation_id": oid, "requirement_id": rid},
                codec.ReasonCode.SEMANTIC_ERROR,
                entity_id=rid,
                return_stage="3A",
            )
        # Validate every verification_ref on the obligation.
        for vref in ospec["verification_refs"]:
            _verify_owned_ref(
                root,
                vref,
                snapshot=snapshot,
                virtual_files=virtual_files,
                entity_id=oid,
                return_stage="5",
            )
        if cat != "out_of_scope_future":
            covered_flows_in_obls.update(ospec["flow_ids"])
            covered_tests_in_obls.update(ospec["test_ids"])
            covered_reqs_in_obls.update(ospec["requirement_ids"])
            for fid in ospec["flow_ids"]:
                tests_by_flow_in_obls.setdefault(fid, set()).update(ospec["test_ids"])

    # 8. Validate top-level other_verification_refs.
    other_verif_refs = deepcopy(list(request.get("other_verification_refs") or []))
    other_verif_seen: set[str] = set()
    for oref in other_verif_refs:
        _verify_owned_ref(
            root,
            oref,
            snapshot=snapshot,
            virtual_files=virtual_files,
            entity_id=plan_id,
            return_stage="5",
        )
        other_verif_seen.add(codec.canonical_digest(oref))
    for ospec in req_obligations:
        for vref in ospec["verification_refs"]:
            if vref["owner"] == "other_verification":
                key = codec.canonical_digest(vref)
                if key not in other_verif_seen:
                    other_verif_seen.add(key)
                    other_verif_refs.append(deepcopy(vref))

    # 9. Enforce Flow/Regression MVG manifest binding, unconditional Task N/A label block,
    #    and non-Flow / mixed-plan Requirement verification checks!
    for tid in conserved_task_ids:
        na_labels = origins_by_tid[tid]["non_flow_summary"]["detected_non_authoritative_labels"]
        if na_labels:
            _fail(
                codec.ReasonCode.SEMANTIC_ERROR,
                "Stage-5 exemption is governed by 3B applicability only, never free-form Task N/A labels",
                {"task_id": tid, "detected_non_authoritative_labels": na_labels},
                entity_id=str(tid),
                resume_ref=TRIPLET["master"],
                return_stage="5",
            )

    required_flows = plan_disp_flows | plan_route_flows | plan_mapped_flows | hit_flows | expanded_required_flows
    requires_mvg_manifest = is_flow_plan or bool(required_flows) or bool(hit_manifest_paths)

    if requires_mvg_manifest:
        _require(
            bool(bound_manifests),
            "at least one valid bound MVG manifest_ref for Flow, handoff/integration, or Flow-impacted Task",
            {"plan_id": plan_id, "impact_mode": impact_mode, "required_flows": sorted(required_flows)},
            codec.ReasonCode.UNRESOLVED_REFERENCE,
            entity_id=plan_id,
            return_stage="5",
        )
        # All hit/cumulative manifests must be bound in manifest_refs (no silent omission).
        missing_hit_manifests = sorted(hit_manifest_paths - set(bound_manifests))
        _require(
            not missing_hit_manifests,
            "every impacted or expanded cumulative manifest bound in manifest_refs",
            {"missing_manifests": missing_hit_manifests},
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=plan_id,
            return_stage="5",
        )
        # Every required flow must exist in bound manifests AND be covered by obligations AND cover all its tests.
        missing_in_manifest = sorted(required_flows - set(bound_manifest_flows))
        _require(
            not missing_in_manifest,
            "every required/impacted flow declared in bound MVG manifest(s)",
            {"missing_flows": missing_in_manifest, "bound_manifest_flows": sorted(bound_manifest_flows)},
            codec.ReasonCode.MAPPING_MISMATCH,
            entity_id=plan_id,
            return_stage="5",
        )
        missing_flow_obls = sorted(required_flows - covered_flows_in_obls)
        _require(
            not missing_flow_obls,
            "every required/impacted/expanded flow covered by Stage-5 obligation (no narrowing)",
            {"uncovered_flows": missing_flow_obls, "impact_mode": impact_mode},
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=plan_id,
            return_stage="5",
        )
        # Every test_id declared on obligations must exist in bound manifests.
        unknown_tests = sorted(covered_tests_in_obls - set(bound_manifest_tests))
        _require(
            not unknown_tests,
            "every obligation test_id exists in bound MVG manifest tests inventory",
            {"unknown_test_ids": unknown_tests},
            codec.ReasonCode.MAPPING_MISMATCH,
            entity_id=plan_id,
            return_stage="5",
        )
        # For every required flow, ALL its declared manifest tests must be covered (no omitted tests / narrowing).
        for fid in sorted(required_flows):
            expected_tests = set(bound_manifest_flows[fid]["test_ids"])
            actual_tests = tests_by_flow_in_obls.get(fid, set())
            missing_tests = sorted(expected_tests - actual_tests)
            _require(
                not missing_tests,
                f"complete manifest test coverage for flow {fid} (no omitted tests)",
                {"flow_id": fid, "missing_test_ids": missing_tests, "covered_test_ids": sorted(actual_tests)},
                codec.ReasonCode.SEMANTIC_ERROR,
                entity_id=fid,
                return_stage="5",
            )
        if expanded_required_tests:
            missing_exp_tests = sorted(expanded_required_tests - covered_tests_in_obls)
            _require(
                not missing_exp_tests,
                "complete cumulative manifest test coverage under conservative expansion (no narrowing)",
                {"missing_test_ids": missing_exp_tests},
                codec.ReasonCode.SEMANTIC_ERROR,
                entity_id=plan_id,
                return_stage="5",
            )
        # Every flow-disposed requirement in plan must be bound to an obligation.
        missing_flow_reqs = sorted(plan_flow_reqs - covered_reqs_in_obls)
        _require(
            not missing_flow_reqs,
            "every Flow-disposed requirement covered by Stage-5 obligations",
            {"uncovered_requirements": missing_flow_reqs},
            codec.ReasonCode.MAPPING_MISMATCH,
            entity_id=plan_id,
            return_stage="5",
        )

    # Enforce 3B non-Flow Requirement governance unconditionally whenever the plan is pure non-Flow
    # OR includes ANY Requirement with disposition in ("other_verification", "deferred") (including mixed
    # plans and Flow-impacted non-Flow plans).
    all_plan_and_mapped_rids = sorted(mapped_req_ids | set(plan_reqs_by_id))
    non_flow_req_ids = [
        rid
        for rid in all_plan_and_mapped_rids
        if plan_verif_by_req.get(rid, {}).get("disposition") in ("other_verification", "deferred")
    ]
    other_verif_req_ids = [
        rid
        for rid in non_flow_req_ids
        if plan_verif_by_req.get(rid, {}).get("disposition") == "other_verification"
    ]
    if (not requires_mvg_manifest) or bool(non_flow_req_ids):
        _require(
            bool(plan.get("adoption_proof_refs")),
            "nonempty 3B adoption_proof_refs for legal non-Flow/deferred requirement disposition",
            plan_id,
            codec.ReasonCode.UNRESOLVED_REFERENCE,
            entity_id=plan_id,
            resume_ref=plan_ref["path"],
            return_stage="3B",
        )
        checked_nf_rids = sorted(mapped_req_ids or set(plan_reqs_by_id)) if not requires_mvg_manifest else non_flow_req_ids
        for rid in checked_nf_rids:
            vrow = plan_verif_by_req.get(rid)
            arow = plan_app_by_req.get(rid)
            _require(
                vrow is not None and arow is not None,
                "3B requirement_verification and applicability entries for non-Flow requirement",
                rid,
                codec.ReasonCode.UNRESOLVED_REFERENCE,
                entity_id=rid,
                resume_ref=plan_ref["path"],
                return_stage="3B",
            )
            assert vrow is not None and arow is not None
            _require(
                vrow["disposition"] in ("other_verification", "deferred"),
                "non-Flow disposition (other_verification|deferred)",
                {"requirement_id": rid, "disposition": vrow["disposition"]},
                codec.ReasonCode.SEMANTIC_ERROR,
                entity_id=rid,
                resume_ref=plan_ref["path"],
                return_stage="3B",
            )
            _require(
                _is_substantive_text(arow.get("rationale")) and _is_substantive_text(vrow.get("rationale")),
                "substantive non-N/A 3B applicability and requirement_verification rationale for non-Flow requirement",
                {"requirement_id": rid, "rationale": arow.get("rationale")},
                codec.ReasonCode.SEMANTIC_ERROR,
                entity_id=rid,
                resume_ref=plan_ref["path"],
                return_stage="3B",
            )
            if vrow["disposition"] == "other_verification":
                vref_key = vrow.get("verification_ref")
                _require(
                    _is_substantive_text(vref_key) and ("other_verification", vref_key) in plan_ev_refs,
                    "declared 3B other_verification evidence_source_ref",
                    {"requirement_id": rid, "verification_ref": vref_key},
                    codec.ReasonCode.UNRESOLVED_REFERENCE,
                    entity_id=rid,
                    resume_ref=plan_ref["path"],
                    return_stage="3B",
                )
        if not requires_mvg_manifest:
            _require(
                bool(other_verif_refs),
                "at least one verified genuine other_verification_ref for non-Flow exemption",
                plan_id,
                codec.ReasonCode.UNRESOLVED_REFERENCE,
                entity_id=plan_id,
                return_stage="5",
            )
            for ospec in req_obligations:
                if ospec["category"] == "out_of_scope_future":
                    continue
                has_other = any(v["owner"] in ("other_verification", "authority") for v in ospec["verification_refs"])
                _require(
                    has_other,
                    "genuine other_verification or authority verification_ref on non-Flow obligation",
                    {"obligation_id": ospec["id"]},
                    codec.ReasonCode.UNRESOLVED_REFERENCE,
                    entity_id=ospec["id"],
                    return_stage="5",
                )
        if other_verif_req_ids:
            missing_other_reqs = sorted(set(other_verif_req_ids) - covered_reqs_in_obls)
            _require(
                not missing_other_reqs,
                "every other_verification requirement covered by Stage-5 obligations",
                {"uncovered_requirements": missing_other_reqs},
                codec.ReasonCode.MAPPING_MISMATCH,
                entity_id=plan_id,
                return_stage="5",
            )
            for rid in other_verif_req_ids:
                covered_with_genuine = any(
                    ospec["category"] != "out_of_scope_future"
                    and rid in ospec["requirement_ids"]
                    and any(v["owner"] in ("other_verification", "authority") for v in ospec["verification_refs"])
                    for ospec in req_obligations
                )
                _require(
                    covered_with_genuine,
                    f"at least one genuine other_verification or authority verification_ref on obligation covering {rid}",
                    {"requirement_id": rid},
                    codec.ReasonCode.UNRESOLVED_REFERENCE,
                    entity_id=rid,
                    return_stage="5",
                )
            for ospec in req_obligations:
                if ospec["category"] == "out_of_scope_future" or ospec["flow_ids"]:
                    continue
                if set(ospec["requirement_ids"]) & set(other_verif_req_ids):
                    has_other = any(v["owner"] in ("other_verification", "authority") for v in ospec["verification_refs"])
                    _require(
                        has_other,
                        "genuine other_verification or authority verification_ref on non-Flow obligation covering other_verification requirement",
                        {"obligation_id": ospec["id"]},
                        codec.ReasonCode.UNRESOLVED_REFERENCE,
                        entity_id=ospec["id"],
                        return_stage="5",
                    )

    # 10. Role-Aware Handoff & Dependency Checks (producer / consumer / integration_only_owner; no self-lock!).
    role_checks = request.get("role_handoff_checks") or {}
    _require(
        not role_checks.get("require_self_done", False),
        "no self-done prerequisite (entering Stage-5/6 never requires self Task done)",
        {"require_self_done": True},
        codec.ReasonCode.DIGEST_CYCLE,
        entity_id=plan_id,
        return_stage="5",
    )
    _require(
        not role_checks.get("require_integration_owner_api", False),
        "integration_only_owner does not require runtime API objects",
        {"require_integration_owner_api": True},
        codec.ReasonCode.SEMANTIC_ERROR,
        entity_id=plan_id,
        return_stage="5",
    )

    back_by_tid: dict[int, list[dict[str, Any]]] = {}
    for row in triplet["docs"]["back"]:
        back_by_tid.setdefault(row["taskmaster_id"], []).append(row)
    gameplay_by_tid: dict[int, list[dict[str, Any]]] = {}
    for row in triplet["docs"]["gameplay"]:
        gameplay_by_tid.setdefault(row["taskmaster_id"], []).append(row)

    declared_prereqs = role_checks.get("declared_prerequisites") or {}
    dependency_summary: dict[str, Any] = {}
    for tid in conserved_task_ids:
        try:
            direct_deps, transitive_deps = input_set._compute_dependency_closure(
                tid,
                master_tasks=triplet["master"],
                back_by_tid=back_by_tid,
                gameplay_by_tid=gameplay_by_tid,
                views=triplet["views"],
            )
        except codec.CodecError as err:
            _fail(
                err.diagnostic.reason_code,
                err.diagnostic.expected,
                err.diagnostic.actual,
                entity_id=str(tid),
                resume_ref=err.diagnostic.resume_ref or TRIPLET["master"],
                stage=err.diagnostic.stage,
                return_stage="3C",
            )
        _require(
            tid not in transitive_deps,
            "acyclic prerequisites with no self-lock",
            {"task_id": tid, "transitive_deps": transitive_deps},
            codec.ReasonCode.DIGEST_CYCLE,
            entity_id=str(tid),
            resume_ref=TRIPLET["master"],
            return_stage="3C",
        )
        if str(tid) in declared_prereqs:
            decl = set(declared_prereqs[str(tid)])
            erased = sorted(set(direct_deps) - decl)
            _require(
                not erased,
                "preserve all declared Task prerequisites (no erasing dependencies)",
                {"task_id": tid, "erased_prerequisites": erased, "declared": sorted(decl)},
                codec.ReasonCode.MAPPING_MISMATCH,
                entity_id=str(tid),
                resume_ref=TRIPLET["master"],
                return_stage="3C",
            )
        dependency_summary[str(tid)] = {
            "direct_dependencies": direct_deps,
            "transitive_dependencies": transitive_deps,
            "self_done_required": False,
            "non_done_dependencies_legal": True,
            "non_done_dependency_ids": [
                dep for dep in transitive_deps if str(triplet["master"][dep].get("status", "")).lower() != "done"
            ],
        }

    # Verify manifest handoffs against roles (producer / consumer / integration_only_owner) and real contract/test definitions.
    mapping_by_tid = {m["task_id"]: m for m in prior_binding["task_mappings"]}
    for m_rel, m_doc in bound_manifest_docs.items():
        dedicated_owners = mvg_manifest._dedicated_integration_owner_task_ids(m_doc["flows"])
        declared_blockers = set(m_doc.get("coverage", {}).get("blocking_task_ids", []))
        self_locked_owners = sorted(dedicated_owners & declared_blockers)
        _require(
            not self_locked_owners,
            "dedicated integration_only_owner must not be self-locked in coverage.blocking_task_ids",
            {"manifest": m_rel, "self_locked_owners": self_locked_owners},
            codec.ReasonCode.DIGEST_CYCLE,
            entity_id=m_rel,
            resume_ref=m_rel,
            return_stage="5",
        )
        for flow in m_doc["flows"]:
            if flow["id"] not in required_flows and flow["id"] not in covered_flows_in_obls:
                continue
            for edge in flow["handoffs"]:
                p_tid = edge["producer_task"]
                c_tid = edge["consumer_task"]
                o_tid = edge["owner_task"]
                c_ref = codec.validate_reference_path(edge["contract_ref"])
                c_raw = snapshot.read(c_ref, optional=True)
                _require(
                    c_raw is not None and bool(c_raw.strip()),
                    f"existing non-empty handoff contract_ref {c_ref}",
                    {"flow_id": flow["id"], "contract_ref": c_ref},
                    codec.ReasonCode.UNRESOLVED_REFERENCE,
                    entity_id=flow["id"],
                    resume_ref=c_ref,
                    return_stage="4",
                )
                if p_tid in mapping_by_tid:
                    _require(
                        "producer" in mapping_by_tid[p_tid]["roles"],
                        f"producer role on task {p_tid} for handoff in flow {flow['id']}",
                        {"task_id": p_tid, "roles": mapping_by_tid[p_tid]["roles"]},
                        codec.ReasonCode.MAPPING_MISMATCH,
                        entity_id=str(p_tid),
                        resume_ref=prior_binding_ref["path"],
                        return_stage="5",
                    )
                if c_tid in mapping_by_tid:
                    _require(
                        "consumer" in mapping_by_tid[c_tid]["roles"],
                        f"consumer role on task {c_tid} for handoff in flow {flow['id']}",
                        {"task_id": c_tid, "roles": mapping_by_tid[c_tid]["roles"]},
                        codec.ReasonCode.MAPPING_MISMATCH,
                        entity_id=str(c_tid),
                        resume_ref=prior_binding_ref["path"],
                        return_stage="5",
                    )
                if o_tid in mapping_by_tid:
                    o_roles = set(mapping_by_tid[o_tid]["roles"])
                    _require(
                        bool(o_roles & {"integration_only_owner", "producer", "consumer"}),
                        f"valid owner role on task {o_tid} for handoff in flow {flow['id']}",
                        {"task_id": o_tid, "roles": sorted(o_roles)},
                        codec.ReasonCode.MAPPING_MISMATCH,
                        entity_id=str(o_tid),
                        resume_ref=prior_binding_ref["path"],
                        return_stage="5",
                    )

    # 11. Anti-Weakening / Reviewed Obligation Retirement & Double-Counting Guard.
    validated_retirements: list[dict[str, Any]] = []
    for ret in request.get("obligation_retirements") or []:
        validated_retirements.append(
            _validate_reviewed_authority_entry(root, snapshot, ret, entity_id=ret["target_id"])
        )

    def _has_retirement(kind: str, target_id: str, *, obligation_id: str | None = None) -> bool:
        for item in validated_retirements:
            if item["kind"] == kind and item["target_id"] == target_id:
                if obligation_id is None or item["obligation_id"] in (None, obligation_id):
                    return True
        return False

    # Synthesize out_of_scope_future formal obligations from impact_analysis.future_obligations
    # before Step 11 anti-weakening checks so re-running Stage 5 on a Stage-5 binding preserves them.
    plan_req_set = set(plan_reqs_by_id)
    existing_future_flows = {
        fid
        for o in req_obligations
        if o["category"] == "out_of_scope_future"
        for fid in o["flow_ids"]
    }
    synthetic_future_formal_obls: list[dict[str, Any]] = []
    synthetic_future_by_id: dict[str, dict[str, Any]] = {}
    for idx_f, fspec in enumerate(future_specs):
        fid = fspec["flow_id"]
        if fid in existing_future_flows:
            continue
        f_oid = f"OBL-FUTURE-{fid}"
        while f_oid in seen_obl_ids:
            f_oid = f"OBL-FUTURE-{fid}-{idx_f}"
        seen_obl_ids.add(f_oid)
        f_meta = {
            "stage": "5",
            "category": "out_of_scope_future",
            "task_ids": [],
            "newly_assigned_task_ids": [],
            "manifest_flow_ids": [],
            "non_catalog_flow_ids": [],
            "out_of_scope_future_flow_ids": [fid],
            "planned_test_ids": [],
            "has_new_obligation": False,
            "requires_reverification_on_done": False,
            "dedup_key": f"{plan_id}:{f_oid}",
        }
        f_obl = {
            "id": f_oid,
            "requirement_ids": sorted(set(fspec.get("requirement_ids") or []) & plan_req_set),
            "flow_ids": [],
            "test_ids": [],
            "responsibility": f"{fspec['reason'].strip()} | {STAGE5_OBL_PREFIX}{_compact_json(f_meta)}",
            "verification_refs": [],
        }
        synthetic_future_formal_obls.append(f_obl)
        synthetic_future_by_id[f_oid] = f_obl

    def _effective_obl_flows(obl_doc: dict[str, Any] | None) -> set[str]:
        if obl_doc is None:
            return set()
        _plain, s5_meta = _parse_stage5_obl_meta(obl_doc.get("responsibility", ""))
        return (
            set(obl_doc.get("flow_ids", []))
            | set(s5_meta.get("non_catalog_flow_ids", []))
            | set(s5_meta.get("out_of_scope_future_flow_ids", []))
        )

    prior_obls_by_id = {o["id"]: o for o in prior_binding.get("obligations", [])}
    new_obls_by_id = {**{o["id"]: o for o in req_obligations}, **synthetic_future_by_id}

    # Check removed prior obligations, tests, requirements, flows (including STAGE5_OBL_PREFIX flows), verification_refs.
    for p_oid, p_obl in prior_obls_by_id.items():
        if p_oid not in new_obls_by_id:
            _require(
                _has_retirement("retire_obligation", p_oid),
                f"reviewed specification authority_ref to retire prior obligation {p_oid}",
                {"retired_obligation_id": p_oid},
                codec.ReasonCode.SEMANTIC_ERROR,
                entity_id=p_oid,
                return_stage="5",
            )
            continue
        n_obl = new_obls_by_id[p_oid]
        for old_t in p_obl.get("test_ids", []):
            if old_t not in n_obl["test_ids"]:
                _require(
                    _has_retirement("remove_test", old_t, obligation_id=p_oid),
                    f"reviewed specification authority_ref to remove test {old_t} from {p_oid}",
                    {"obligation_id": p_oid, "removed_test_id": old_t},
                    codec.ReasonCode.SEMANTIC_ERROR,
                    entity_id=p_oid,
                    return_stage="5",
                )
        for old_r in p_obl.get("requirement_ids", []):
            if old_r not in n_obl["requirement_ids"]:
                _require(
                    _has_retirement("remove_requirement", old_r, obligation_id=p_oid),
                    f"reviewed specification authority_ref to remove requirement {old_r} from {p_oid}",
                    {"obligation_id": p_oid, "removed_requirement_id": old_r},
                    codec.ReasonCode.SEMANTIC_ERROR,
                    entity_id=p_oid,
                    return_stage="5",
                )
        prior_eff_flows = _effective_obl_flows(p_obl)
        new_eff_flows = (
            _effective_obl_flows(n_obl)
            if p_oid in synthetic_future_by_id
            else set(n_obl["flow_ids"])
        )
        for old_f in sorted(prior_eff_flows):
            if old_f not in new_eff_flows:
                _require(
                    _has_retirement("remove_flow", old_f, obligation_id=p_oid),
                    f"reviewed specification authority_ref to remove flow {old_f} from {p_oid}",
                    {"obligation_id": p_oid, "removed_flow_id": old_f},
                    codec.ReasonCode.SEMANTIC_ERROR,
                    entity_id=p_oid,
                    return_stage="5",
                )
        new_vref_keys = {v["ref"] for v in n_obl["verification_refs"]}
        for old_v in p_obl.get("verification_refs", []):
            if old_v["ref"] not in new_vref_keys:
                _require(
                    _has_retirement("remove_verification_ref", old_v["ref"], obligation_id=p_oid),
                    f"reviewed specification authority_ref to remove verification_ref {old_v['ref']} from {p_oid}",
                    {"obligation_id": p_oid, "removed_verification_ref": old_v["ref"]},
                    codec.ReasonCode.SEMANTIC_ERROR,
                    entity_id=p_oid,
                    return_stage="5",
                )

    # Check removed prior manifest_refs and prior/3B other_verification_refs (unconditionally for all other_verification reqs).
    new_manifest_paths = set(bound_manifests)
    for old_mref in prior_binding.get("manifest_refs", []):
        old_m_path = old_mref["ref"].partition("#")[0]
        if old_m_path not in new_manifest_paths:
            _require(
                _has_retirement("remove_manifest_ref", old_m_path),
                f"reviewed specification authority_ref to remove manifest_ref {old_m_path}",
                {"removed_manifest_ref": old_m_path},
                codec.ReasonCode.SEMANTIC_ERROR,
                entity_id=old_m_path,
                return_stage="5",
            )
    new_other_ref_strings = {r["ref"] for r in other_verif_refs}
    for old_oref in prior_binding.get("other_verification_refs", []):
        if old_oref["ref"] not in new_other_ref_strings:
            _require(
                _has_retirement("remove_verification_ref", old_oref["ref"]),
                f"reviewed specification authority_ref to remove other_verification_ref {old_oref['ref']}",
                {"removed_other_verification_ref": old_oref["ref"]},
                codec.ReasonCode.SEMANTIC_ERROR,
                entity_id=old_oref["ref"],
                return_stage="5",
            )
    for rid in all_plan_and_mapped_rids:
        vrow = plan_verif_by_req.get(rid)
        if vrow and vrow["disposition"] == "other_verification":
            vref_str = vrow["verification_ref"]
            if vref_str not in new_other_ref_strings:
                _require(
                    _has_retirement("remove_verification_ref", vref_str),
                    f"3B required other_verification_ref {vref_str} retained or retired with reviewed authority",
                    {"requirement_id": rid, "missing_other_verification_ref": vref_str},
                    codec.ReasonCode.SEMANTIC_ERROR,
                    entity_id=rid,
                    return_stage="5",
                )

    # Record verified formal retirement specification OwnedRefs in other_verification_refs for clean-clone proof.
    public_retirements: list[dict[str, Any]] = []
    for item in validated_retirements:
        auth_oref = item["authority_owned_ref"]
        auth_key = codec.canonical_digest(auth_oref)
        if auth_key not in other_verif_seen:
            other_verif_seen.add(auth_key)
            other_verif_refs.append(deepcopy(auth_oref))
        public_retirements.append({k: v for k, v in item.items() if k != "authority_owned_ref"})

    # Check optional caller-supplied reported_counts against true deduplicated counts (reject double counting).
    unique_req_count = len({r["requirement_id"] for r in plan["requirement_verification"]})
    unique_route_count = len({(r["requirement_id"], r["flow_id"]) for r in plan["requirement_route_memberships"]})
    unique_evidence_count = len({(r["requirement_id"], r["evidence_id"]) for r in plan["requirement_evidence"]})
    unique_test_count = len(covered_tests_in_obls)
    reported = request.get("reported_counts")
    if type(reported) is dict:
        for key, actual_count in (
            ("unique_requirements", unique_req_count),
            ("unique_routes", unique_route_count),
            ("unique_evidence", unique_evidence_count),
            ("unique_tests", unique_test_count),
        ):
            if key in reported and reported[key] != actual_count:
                _fail(
                    codec.ReasonCode.MAPPING_MISMATCH,
                    f"deduplicated {key} == {actual_count} (double counting forbidden)",
                    {"field": key, "reported": reported[key], "actual_deduplicated": actual_count},
                    entity_id=plan_id,
                    return_stage="5",
                )

    # 12. Per-Task Obligation Conservation & Old done vs New/Modified/Reassigned Obligations / planned Tests.
    prior_tests_by_tid: dict[int, set[str]] = {tid: set() for tid in conserved_task_ids}
    prior_obls_by_tid: dict[int, set[str]] = {tid: set() for tid in conserved_task_ids}
    for m in prior_binding["task_mappings"]:
        tid = m["task_id"]
        prior_obls_by_tid[tid] = set(m["obligation_ids"])
        for oid in m["obligation_ids"]:
            if oid in prior_obls_by_id:
                prior_tests_by_tid[tid].update(prior_obls_by_id[oid].get("test_ids", []))

    for prior_m in sorted(prior_binding["task_mappings"], key=lambda r: r["task_id"]):
        tid = prior_m["task_id"]
        new_oids_set = {o["id"] for o in obls_by_tid[tid]}
        mapped_t_reqs = list(prior_m.get("requirement_ids", []))
        all_deferred = bool(mapped_t_reqs) and all(
            plan_verif_by_req.get(r, {}).get("disposition") == "deferred" for r in mapped_t_reqs
        )
        _require(
            bool(new_oids_set) or all_deferred,
            f"nonempty Stage-5 obligation_ids for conserved Task {tid} unless all mapped requirements are deferred",
            {"task_id": tid, "obligation_ids": sorted(new_oids_set)},
            codec.ReasonCode.SEMANTIC_ERROR,
            entity_id=str(tid),
            return_stage="5",
        )
        for old_oid in sorted(prior_obls_by_tid[tid]):
            if old_oid not in new_oids_set:
                _require(
                    _has_retirement("retire_obligation", old_oid)
                    or _has_retirement("remove_task_obligation", f"{tid}:{old_oid}", obligation_id=old_oid),
                    f"reviewed specification authority_ref to remove obligation {old_oid} from Task {tid}",
                    {"task_id": tid, "removed_obligation_id": old_oid},
                    codec.ReasonCode.SEMANTIC_ERROR,
                    entity_id=str(tid),
                    return_stage="5",
                )

    obl_reverify_info: dict[str, tuple[bool, list[int], list[str]]] = {}
    for ospec in req_obligations:
        oid = ospec["id"]
        cat = ospec["category"]
        prior_o = prior_obls_by_id.get(oid)
        prior_eff_flows = _effective_obl_flows(prior_o)
        prior_vref_keys = {v["ref"] for v in prior_o.get("verification_refs", [])} if prior_o is not None else set()
        new_vref_keys = {v["ref"] for v in ospec["verification_refs"]}
        is_new_obl = (
            prior_o is None
            or cat == "current_new"
            or bool(set(ospec["flow_ids"]) - prior_eff_flows)
            or bool(set(ospec["test_ids"]) - set(prior_o.get("test_ids", [])))
            or bool(set(ospec["requirement_ids"]) - set(prior_o.get("requirement_ids", [])))
            or bool(new_vref_keys - prior_vref_keys)
        )
        newly_assigned_tids = sorted(
            set(ospec["task_ids"]) - {t for t, oset in prior_obls_by_tid.items() if oid in oset}
        )
        planned_in_obl = sorted(
            t for t in set(ospec["test_ids"]) if bound_manifest_tests.get(t, {}).get("state") == "planned"
        )
        obl_reverify_info[oid] = (is_new_obl, newly_assigned_tids, planned_in_obl)
        if ospec.get("skip_reverification", False):
            for tid in ospec["task_ids"]:
                is_done = str(triplet["master"][tid].get("status", "")).lower() == "done"
                if is_done and (is_new_obl or (tid in newly_assigned_tids) or planned_in_obl):
                    _fail(
                        codec.ReasonCode.SEMANTIC_ERROR,
                        "old done Task cannot skip reverification for new/modified/reassigned obligation or planned test",
                        {
                            "task_id": tid,
                            "obligation_id": oid,
                            "is_new_obligation": is_new_obl,
                            "newly_assigned": tid in newly_assigned_tids,
                            "planned_tests": planned_in_obl,
                        },
                        entity_id=str(tid),
                        return_stage="5",
                    )

    # 13. Build Formal Stage-5 Binding (conserving Stage-4 task_mappings/parts/objects/STAGE4_OBL_PREFIX).
    covered_manifest_flow_set = set(bound_manifest_flows)

    req_obl_id_set = {o["id"] for o in req_obligations}
    retirements_by_oid: dict[str, list[dict[str, Any]]] = {}
    for ritem in public_retirements:
        target_oid = ritem.get("obligation_id")
        if target_oid in req_obl_id_set:
            retirements_by_oid.setdefault(target_oid, []).append(ritem)
        else:
            retirements_by_oid.setdefault(req_obligations[0]["id"], []).append(ritem)

    formal_obligations: list[dict[str, Any]] = []
    for ospec in req_obligations:
        oid = ospec["id"]
        cat = ospec["category"]
        # Formal obligation requirement_ids/flow_ids MUST stay subsets of plan.requirements & covered catalog flows.
        formal_req_ids = sorted(set(ospec["requirement_ids"]) & plan_req_set)
        if cat == "out_of_scope_future":
            formal_flow_ids: list[str] = []
        else:
            formal_flow_ids = sorted(
                fid for fid in set(ospec["flow_ids"])
                if fid in catalog_flow_ids and fid in covered_manifest_flow_set
            )
        extra_flows = sorted(set(ospec["flow_ids"]) - set(formal_flow_ids))
        prior_o = prior_obls_by_id.get(oid)
        is_new_obl, newly_assigned_tids, planned_tests = obl_reverify_info[oid]
        stage5_meta: dict[str, Any] = {
            "stage": "5",
            "category": cat,
            "task_ids": sorted(set(ospec["task_ids"])),
            "newly_assigned_task_ids": newly_assigned_tids,
            "manifest_flow_ids": sorted(set(ospec["flow_ids"]) & covered_manifest_flow_set),
            "non_catalog_flow_ids": extra_flows if cat != "out_of_scope_future" else [],
            "out_of_scope_future_flow_ids": extra_flows if cat == "out_of_scope_future" else [],
            "planned_test_ids": planned_tests,
            "has_new_obligation": is_new_obl,
            "requires_reverification_on_done": bool(is_new_obl or planned_tests),
            "dedup_key": f"{plan_id}:{oid}",
        }
        if oid in retirements_by_oid:
            stage5_meta["retired_items"] = retirements_by_oid[oid]
        if not requires_mvg_manifest:
            stage5_meta["non_flow_exempt"] = True
            stage5_meta["exemption_basis"] = "3b_applicability"

        plain_resp, _old_s5 = _parse_stage5_obl_meta(ospec["responsibility"])
        # Preserve exact STAGE4_OBL_PREFIX suffix from prior_binding at the END of responsibility
        # so ch4_binding.extract_stage4_semantics and Story 3.5 stage4_semantics stay invariant!
        prior_s4_raw: str | None = None
        if prior_o is not None:
            _prefix_part, prior_s4_raw = _split_stage4_suffix(prior_o.get("responsibility", ""))
        if prior_s4_raw is not None:
            responsibility = f"{plain_resp} | {STAGE5_OBL_PREFIX}{_compact_json(stage5_meta)} | {STAGE4_OBL_PREFIX}{prior_s4_raw}"
        else:
            responsibility = f"{plain_resp} | {STAGE5_OBL_PREFIX}{_compact_json(stage5_meta)}"

        formal_obligations.append(
            {
                "id": oid,
                "requirement_ids": formal_req_ids,
                "flow_ids": formal_flow_ids,
                "test_ids": sorted(set(ospec["test_ids"])),
                "responsibility": responsibility,
                "verification_refs": deepcopy(ospec["verification_refs"]),
            }
        )

    # Append synthetic future_obligations already constructed prior to Step 11.
    formal_obligations.extend(synthetic_future_formal_obls)

    # Conserve task_mappings (exact Stage-4 fields except updated obligation_ids).
    new_task_mappings: list[dict[str, Any]] = []
    for prior_m in sorted(prior_binding["task_mappings"], key=lambda r: r["task_id"]):
        tid = prior_m["task_id"]
        new_oids = sorted({o["id"] for o in obls_by_tid[tid]})
        new_m = deepcopy(prior_m)
        new_m["obligation_ids"] = new_oids
        new_task_mappings.append(new_m)

    # Deduplicate manifest_refs & other_verification_refs cleanly.
    unique_manifest_refs = list(
        {codec.canonical_digest(r): r for r in bound_manifest_refs}.values()
    )
    unique_manifest_refs.sort(key=lambda r: (r["ref"], codec.canonical_digest(r)))
    unique_other_refs = list(
        {codec.canonical_digest(r): r for r in other_verif_refs}.values()
    )
    unique_other_refs.sort(key=lambda r: (r["owner"], r["ref"], codec.canonical_digest(r)))

    # Allocate monotonic binding_revision.
    inv_ops = inventory_ops if inventory_ops is not None else journal.operation_inventory(root)
    max_rev = prior_binding["binding_revision"]
    bindings_dir = root / records.BASE / "bindings" / plan_id
    if bindings_dir.is_dir():
        for child in bindings_dir.iterdir():
            if child.is_file() and child.suffix == ".json" and child.stem.isdigit():
                max_rev = max(max_rev, int(child.stem))
    for op in inv_ops:
        if op["operation_id"] == operation_id:
            continue
        alloc = op.get("frozen", {}).get("allocations", {})
        if alloc.get("plan_id") == plan_id and type(alloc.get("binding_revision")) is int:
            max_rev = max(max_rev, alloc["binding_revision"])
    binding_revision = allocations["binding_revision"] if allocations is not None else (max_rev + 1)
    binding_path = records.BASE + f"bindings/{plan_id}/{binding_revision}.json"

    stage5_binding = {
        "schema_version": "newrouge.b-route-binding.v1",
        "plan_id": plan_id,
        "binding_revision": binding_revision,
        "plan_ref": deepcopy(prior_binding["plan_ref"]),
        "stage": "5",
        "task_mappings": new_task_mappings,
        "parts": deepcopy(prior_binding["parts"]),
        "implementation_objects": deepcopy(prior_binding["implementation_objects"]),
        "obligations": formal_obligations,
        "manifest_refs": unique_manifest_refs,
        "other_verification_refs": unique_other_refs,
    }
    stage5_binding_raw = projection.serialized(stage5_binding)
    b_checked = records.validate_record(stage5_binding_raw, path=binding_path)
    if not b_checked.ok:
        raise codec.CodecError(b_checked.diagnostic)
    # Confirm Stage-4 semantics remain cleanly parseable from Stage-5 binding.
    ch4_binding.extract_stage4_semantics(plan, stage5_binding)

    # 14. Validate candidate Stage-5 binding through Story 3.5 resolve_input_set (candidate slot + pre-sync)!
    candidate_overlay: dict[str, bytes] = {binding_path: stage5_binding_raw, **virtual_files}
    task_input_set_digests: dict[str, str] = {}
    with commit.read_operation_context(read_operation_id, pre_sync_bytes=pre_sync_overrides):
        for tid in conserved_task_ids:
            iset = input_set.resolve_input_set(
                root,
                tid,
                candidate_binding=binding_path,
                candidate_overlay=candidate_overlay,
                max_attempts=1,
            )
            if not iset["ok"] or not iset["stable"] or not iset["valid_input_set"] or iset["route"] != "B":
                first_diag = iset["diagnostics"][0] if iset["diagnostics"] else None
                if first_diag is not None:
                    _fail(
                        codec.ReasonCode(first_diag["reason_code"]),
                        first_diag["expected"],
                        first_diag["actual"],
                        entity_id=first_diag.get("entity_id") or str(tid),
                        resume_ref=first_diag.get("resume_ref"),
                        stage=codec.Stage(first_diag["stage"]) if first_diag.get("stage") else codec.Stage.BUNDLE,
                        return_stage=iset.get("return_stage") or "5",
                    )
                _fail(
                    codec.ReasonCode.IDENTITY_UNPROVABLE,
                    "Story 3.5 resolve_input_set passing with candidate Stage-5 binding",
                    {"task_id": tid, "route": iset.get("route")},
                    entity_id=str(tid),
                    return_stage=iset.get("return_stage") or "5",
                )
            _require(
                iset["uses_candidate_binding"] is True and iset["input_set_digest"] is not None,
                "Story 3.5 candidate single-slot replacement active",
                {"task_id": tid, "uses_candidate_binding": iset["uses_candidate_binding"]},
                codec.ReasonCode.CONFLICT,
                entity_id=str(tid),
                return_stage="5",
            )
            task_input_set_digests[str(tid)] = iset["input_set_digest"]

    # 15. Build updated task-origins.v1.json (strictly preserving other plans on shared Tasks!).
    new_binding_ref = projection.reference(binding_path, stage5_binding_raw)
    updated_origins = deepcopy(origins)
    updated_origins["revision"] = origins["revision"] + 1
    for row in updated_origins["tasks"]:
        if row["task_id"] not in conserved_set:
            continue
        kept_bindings = [ref for ref in row["binding_refs"] if ref["entity_id"] != plan_id]
        kept_bindings.append(deepcopy(new_binding_ref))
        kept_bindings.sort(key=lambda r: (r["entity_id"], r["revision"], r["path"]))
        row["binding_refs"] = kept_bindings
    updated_origins_raw = projection.serialized(updated_origins)
    o_checked = records.validate_record(updated_origins_raw, path=records.BASE + "task-origins.v1.json")
    if not o_checked.ok:
        raise codec.CodecError(o_checked.diagnostic)

    # 16. Build targets, allocations, scope_ids, authority_refs, and frozen payload.
    targets = [
        {
            "path": binding_path,
            "schema_version": "newrouge.b-route-binding.v1",
            "before_raw_digest": None,
            "after_payload": stage5_binding,
            "after_raw_digest": codec.raw_digest(stage5_binding_raw),
            "verification_mode": "immutable_bytes",
        },
        {
            "path": records.BASE + "task-origins.v1.json",
            "schema_version": "newrouge.b-route-origins.v1",
            "before_raw_digest": codec.raw_digest(origins_raw),
            "after_payload": updated_origins,
            "after_raw_digest": codec.raw_digest(updated_origins_raw),
            "verification_mode": "immutable_bytes",
        },
    ]

    task_definitions = {
        str(tid): codec.canonical_digest(protection.task_definition_projection(triplet["master"][tid]))
        for tid in conserved_task_ids
    }
    proposed_allocations = {
        "plan_id": plan_id,
        "plan_revision": plan["revision"],
        "binding_revision": binding_revision,
        "origins_revision": updated_origins["revision"],
        "task_definitions": task_definitions,
    }
    _require(
        allocations is None or allocations == proposed_allocations,
        "unchanged frozen stage5_obligations allocations",
        proposed_allocations,
        codec.ReasonCode.INPUT_STALE,
        entity_id=operation_id,
    )

    affected_existing_heads = [
        head
        for head in catalog["scope_heads"]
        if any(ref["entity_id"] == plan_id for ref in head["plan_refs"] + head["binding_refs"])
    ]
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
        "binding_meta": {
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
            "task_input_set_digests": task_input_set_digests,
        },
    }
    journal._operation_schema(frozen, "Frozen", schema_id=OPERATION_SCHEMA)

    # 17. Dry-run validate future receipt + catalog bundle against post-sync virtual files!
    candidates: dict[str, bytes] = {
        row["path"]: projection.serialized(row["after_payload"]) for row in targets
    }
    candidates[records.CATALOG_PATH] = catalog_raw
    for rel, raw in virtual_files.items():
        candidates[rel] = raw

    draft_bundle = records._Bundle(candidates, root, records.CATALOG_PATH, None, triplet["join"])
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
        task_join=triplet["join"],
        root=root,
        frozen=frozen,
    )

    semantics = extract_stage5_semantics(
        plan,
        stage5_binding,
        master_tasks=triplet["master"],
        manifests=bound_manifest_docs,
    )
    semantics["impact_mode"] = impact_mode
    semantics["task_input_set_digests"] = deepcopy(task_input_set_digests)
    semantics["dependency_summary"] = dependency_summary
    semantics["retirements_applied"] = public_retirements
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
    meta = envelope["frozen"]["binding_meta"]
    res = {
        "producer": PRODUCER,
        "operation_id": envelope["operation_id"],
        "state": envelope["state"],
        "scope_ids": envelope["frozen"]["scope_ids"],
        "request_digest": envelope["request_digest"],
        "frozen_digest": envelope["frozen_digest"],
        "allocations": envelope["frozen"]["allocations"],
        "has_public_changes": meta["has_public_changes"],
        "public_sync_paths": [e["path"] for e in meta["public_sync_entries"]],
        "task_input_set_digests": deepcopy(meta["task_input_set_digests"]),
        "resume_ref": journal._operation_ref(envelope["operation_id"]),
        "formal_adoption": False,
        "diagnostics": [],
        **FLAGS,
    }
    if semantics is not None:
        res["stage5_semantics"] = semantics
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
                "complete governed stage5 obligations evidence",
                f"{type(error).__name__}: {error}",
                entity_id=operation_id if type(operation_id) is str else None,
            )

    return checked


@public
def preview(root: Path | str, *, operation_id: str, request_ref: str) -> dict[str, Any]:
    """Pure read-only zero-write Stage-5 obligations preview."""
    root_path = Path(root).resolve()
    _validate_file_id(operation_id, "operation_id")
    raw = _read_bytes(root_path, request_ref)
    assert raw is not None
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
        "has_public_changes": frozen["binding_meta"]["has_public_changes"],
        "public_sync_paths": [e["path"] for e in frozen["binding_meta"]["public_sync_entries"]],
        "task_input_set_digests": deepcopy(frozen["binding_meta"]["task_input_set_digests"]),
        "target_paths": [t["path"] for t in frozen["targets"]],
        "stage5_semantics": semantics,
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
        "existing prepared stage5_obligations operation",
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
            "same ID and complete request for stage5_obligations",
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
            and frozen["binding_meta"]["public_sync_entries"]
            == existing["frozen"]["binding_meta"]["public_sync_entries"]
            and frozen["binding_meta"]["task_input_set_digests"]
            == existing["frozen"]["binding_meta"]["task_input_set_digests"],
            "unchanged frozen stage5_obligations operation between prepare and reserve",
            operation_id,
            codec.ReasonCode.INPUT_STALE,
            entity_id=operation_id,
        )
        for cur_t, old_t in zip(frozen["targets"], existing_targets):
            _require(
                cur_t["path"] == old_t["path"]
                and cur_t["before_raw_digest"] == old_t["before_raw_digest"]
                and cur_t["after_raw_digest"] == old_t["after_raw_digest"],
                "unchanged immutable targets between prepare and reserve",
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
            "existing prepared stage5_obligations operation under lease",
            operation_id,
            codec.ReasonCode.FILE_NOT_FOUND,
            entity_id=operation_id,
        )
        if live_existing is not None:
            _require(
                live_existing["request_digest"] == codec.canonical_digest(request)
                and live_existing["frozen"] == frozen,
                "unchanged persisted stage5_obligations operation under lease",
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
            "complete persisted stage5_obligations operation",
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
                "has_public_changes": persisted["frozen"]["binding_meta"]["has_public_changes"],
                "frozen_digest": persisted["frozen_digest"],
            },
        )
        return _result(persisted, semantics=semantics, event_log=event_log)


@public
def prepare(root: Path | str, *, operation_id: str, request_ref: str) -> dict[str, Any]:
    root_path = Path(root).resolve()
    raw = _read_bytes(root_path, request_ref)
    assert raw is not None
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
    """Read-only inspection of a prepared/reserved stage5_obligations operation."""
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
        for entry in envelope["frozen"]["binding_meta"]["public_sync_entries"]
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

    for entry in envelope["frozen"]["binding_meta"]["public_sync_entries"]:
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
        "eligibility": "read-only inspect; reserve and apply revalidate committed Stage-4/5, Story 3.3 B, and Story 3.5 InputSet",
    }


@contextmanager
def commit_context(root: Path, *, operation_id: str, _held_scopes: set[str] | None = None):
    """Initial apply admission context for shared _b_route_commit.execute."""
    root = Path(root).resolve()
    envelope = journal.read_operation(root, operation_id=operation_id)
    _require(
        envelope["schema_version"] == OPERATION_SCHEMA and envelope["state"] == "reserved",
        "reserved stage5_obligations operation",
        operation_id,
        codec.ReasonCode.CONFLICT,
        entity_id=operation_id,
    )
    saved_public_sync = None
    if envelope["frozen"]["binding_meta"]["has_public_changes"]:
        pub_doc = validate_public_sync_local(root, envelope)
        _require(
            pub_doc is not None and pub_doc["phase"] in ("applied", "complete"),
            "applied public-sync-journal.json before formal commit freeze",
            None if pub_doc is None else pub_doc["phase"],
            codec.ReasonCode.UNPUBLISHED,
            entity_id=operation_id,
            resume_ref=public_sync_paths(operation_id)[0],
        )
        assert pub_doc is not None
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
        and checked_frozen["binding_meta"] == envelope["frozen"]["binding_meta"],
        "unchanged reserved stage5_obligations semantics before apply freeze",
        operation_id,
        codec.ReasonCode.INPUT_STALE,
        entity_id=operation_id,
    )
    for frozen_t, checked_t in zip(envelope["frozen"]["targets"], checked_frozen["targets"]):
        _require(
            frozen_t["path"] == checked_t["path"]
            and frozen_t["before_raw_digest"] == checked_t["before_raw_digest"]
            and frozen_t["after_raw_digest"] == checked_t["after_raw_digest"],
            "unchanged immutable targets before apply freeze",
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
    if envelope["frozen"]["binding_meta"]["has_public_changes"]:
        pub_doc = validate_public_sync_local(root, envelope)
        _require(
            pub_doc is not None and pub_doc["phase"] in ("applied", "complete"),
            "applied or complete public-sync-journal.json during commit step",
            None if pub_doc is None else pub_doc["phase"],
            codec.ReasonCode.PENDING,
            entity_id=envelope["operation_id"],
            resume_ref=public_sync_paths(envelope["operation_id"])[0],
        )
        assert pub_doc is not None
        for entry in pub_doc["entries"]:
            actual = _read_bytes(root, entry["path"])
            assert actual is not None
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
    """Verify frozen commit.json observations plus synced manifest files and sealed targets."""
    from _b_route_commit import _catalog_frame, _classify_target, _decode, _digest, _read, _sealed_targets
    import _b_route_adoption_review as review

    root = Path(root).absolute()
    _require(
        intent["policy_identity"] == review.policy_identity(),
        "same reviewed stage5_obligations rules",
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

    for entry in envelope["frozen"]["binding_meta"]["public_sync_entries"]:
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
            "unchanged stage5 input or exact sealed target image",
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
