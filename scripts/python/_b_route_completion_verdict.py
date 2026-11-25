"""Story 4.5 read-only completion verdict service.

Separately verifies Task-local completion, target-Flow completion, cumulative
full-MVG milestone completion, and legal non-Flow completion from authoritative
Taskmaster/plan/binding/manifest/VerificationScope/coverage-receipt/raw-report
evidence without mutating tasks.json, catalog.v1.json, or publish pointers.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

import _b_route_chapter6_gate as ch6_gate
import _b_route_chapter7_slice as ch7_slice
import _b_route_codec as codec
import _b_route_evidence_reuse as evidence_reuse
import _b_route_impact_closure as closure
import _b_route_input_set as input_set_mod
import _b_route_inventory as inventory
import _b_route_scope_runner as scope_runner
import _b_route_task_resolver as task_resolver
import _b_route_verification_scope as vs
import milestone_incremental_handoff as handoff_mod
from _mvg_manifest import (
    manifest_sha256,
    validate_manifest,
)

SCHEMA = "newrouge.b-route-completion-verdict.v1"
MANUAL_SIGNOFF_SCHEMA = "newrouge.b-route-manual-signoff.v1"
VALID_LEVELS = frozenset({"task", "flow", "milestone", "non_flow"})
INVALID_ARGUMENT_CODES = vs.INVALID_ARGUMENT_CODES
INVARIANT_FLAGS = {
    "task_status_mutated": False,
    "catalog_mutated": False,
    "publish_pointer_mutated": False,
    "default_b_enabled": False,
}

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$", re.ASCII)
_SNAPSHOT_DIGEST_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$", re.ASCII)
_CJK_RE = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
_FORBIDDEN_MANUAL_NOTE_TOKENS = frozenset({
    "skip", "skipped", "todo", "tbd", "na", "n/a", "waive", "waived",
    "bypass", "auto", "placeholder", "fake", "stub", "ignore", "ignored",
})
_MIN_MANUAL_NOTE_CHARS = 12


def _raw_hex(digest: str) -> str:
    return digest.removeprefix("sha256:")


def _strict_int(
    val: Any,
    *,
    field: str,
    entity_id: str | None,
    resume_ref: str | None,
    default: int | None = None,
) -> int:
    if val is None and default is not None:
        return default
    if type(val) is not int:
        raise _err(
            codec.ReasonCode.INVALID_TYPE,
            codec.Stage.CONTENT,
            entity_id,
            f"strict integer for {field}",
            f"{type(val).__name__}:{val!r}",
            resume_ref,
        )
    return val


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _elapsed(started: float) -> float:
    return round(max(0.0, time.monotonic() - started), 6)


def _diag(
    code: codec.ReasonCode,
    stage: codec.Stage,
    entity_id: str | None,
    expected: Any,
    actual: Any,
    resume_ref: str | None = None,
) -> dict[str, Any]:
    return codec.Diagnostic(code, stage, entity_id, expected, actual, resume_ref).to_dict()


def _err(
    code: codec.ReasonCode,
    stage: codec.Stage,
    entity_id: str | None,
    expected: Any,
    actual: Any,
    resume_ref: str | None = None,
) -> codec.CodecError:
    return codec.CodecError(codec.Diagnostic(code, stage, entity_id, expected, actual, resume_ref))


def _check_no_reparse_chain(target: Path, root: Path, rel: str) -> None:
    try:
        root_res = root.resolve()
        cur = target
        chain: list[Path] = []
        while True:
            chain.append(cur)
            if cur == root_res or cur.parent == cur:
                break
            cur = cur.parent
        for part in reversed(chain):
            if os.path.lexists(part):
                inventory.no_reparse(part)
    except ValueError as exc:
        raise _err(
            codec.ReasonCode.UNSAFE_PATH,
            codec.Stage.PATH,
            rel,
            "path without reparse ancestors or leaf",
            str(exc),
            rel,
        ) from exc


def _normalize_repo_path(root: Path, raw: Any, *, label: str, allow_logs: bool = True) -> tuple[Path, str]:
    if type(raw) is not str or not raw.strip():
        raise _err(
            codec.ReasonCode.INVALID_ARGUMENT,
            codec.Stage.PATH,
            None,
            f"nonempty repository-relative path for {label}",
            raw,
            None,
        )
    try:
        resolved = inventory.safe_input(root, raw, allow_logs=allow_logs).resolve()
    except ValueError as exc:
        raise _err(
            codec.ReasonCode.UNSAFE_PATH,
            codec.Stage.PATH,
            raw,
            f"safe repository-relative POSIX path for {label}",
            str(exc),
            raw,
        ) from exc
    root_res = root.resolve()
    if not resolved.is_relative_to(root_res):
        raise _err(
            codec.ReasonCode.UNSAFE_PATH,
            codec.Stage.PATH,
            raw,
            f"path inside repository root for {label}",
            raw,
            raw,
        )
    rel = resolved.relative_to(root_res).as_posix()
    _check_no_reparse_chain(resolved, root_res, rel)
    return resolved, rel


def _resolve_contained_run_file(
    root: Path,
    run_dir: Path,
    raw_ref: Any,
    *,
    label: str,
    entity_id: str | None,
    resume_ref: str | None,
) -> Path:
    if type(raw_ref) is not str or not raw_ref.strip():
        raise _err(
            codec.ReasonCode.MISSING_REQUIRED_FIELD,
            codec.Stage.CONTENT,
            entity_id,
            f"nonempty path inside run_dir for {label}",
            raw_ref,
            resume_ref,
        )
    root_res = root.resolve()
    run_dir_res = run_dir.resolve()
    lp = Path(raw_ref)
    if not lp.is_absolute():
        try:
            lp = inventory.safe_input(root_res, raw_ref, allow_logs=True)
        except ValueError as exc:
            raise _err(
                codec.ReasonCode.UNSAFE_PATH,
                codec.Stage.PATH,
                entity_id or raw_ref,
                f"safe path inside run_dir for {label}",
                str(exc),
                resume_ref,
            ) from exc
    _check_no_reparse_chain(lp, root_res, str(raw_ref))
    lp_res = lp.resolve()
    if not lp_res.is_relative_to(root_res) or run_dir_res not in lp_res.parents:
        raise _err(
            codec.ReasonCode.UNSAFE_PATH,
            codec.Stage.PATH,
            entity_id or raw_ref,
            f"file strictly inside owning run directory for {label}",
            raw_ref,
            resume_ref,
        )
    if not lp_res.is_file():
        raise _err(
            codec.ReasonCode.FILE_NOT_FOUND,
            codec.Stage.PATH,
            entity_id or raw_ref,
            f"existing file inside run_dir for {label}",
            raw_ref,
            resume_ref,
        )
    return lp_res


def _load_strict_json(root: Path, raw_path: Any, *, label: str, allow_logs: bool = True) -> tuple[dict[str, Any], Path, str]:
    target, rel = _normalize_repo_path(root, raw_path, label=label, allow_logs=allow_logs)
    if not target.is_file():
        raise _err(
            codec.ReasonCode.FILE_NOT_FOUND,
            codec.Stage.PATH,
            rel,
            f"existing JSON file for {label}",
            rel,
            rel,
        )
    _check_no_reparse_chain(target, root, rel)
    try:
        raw_bytes = target.read_bytes()
    except OSError as exc:
        raise _err(
            codec.ReasonCode.READ_ERROR,
            codec.Stage.DECODE,
            rel,
            f"readable UTF-8 JSON file for {label}",
            str(exc),
            rel,
        ) from exc
    try:
        doc = codec.strict_json_loads(raw_bytes)
    except codec.CodecError as exc:
        d = exc.diagnostic
        raise _err(d.reason_code, d.stage or codec.Stage.DECODE, rel, d.expected, d.actual, rel) from exc
    if type(doc) is not dict:
        raise _err(
            codec.ReasonCode.INVALID_TYPE,
            codec.Stage.CONTENT,
            rel,
            f"JSON object for {label}",
            type(doc).__name__,
            rel,
        )
    return doc, target, rel


def _validate_report_output(root: Path, report_path: str | None) -> tuple[Path, str] | None:
    if report_path is None:
        return None
    target, rel = _normalize_repo_path(root, report_path, label="report", allow_logs=True)
    if not rel.startswith("logs/") or not rel.lower().endswith(".json"):
        raise _err(
            codec.ReasonCode.UNSAFE_PATH,
            codec.Stage.PATH,
            rel,
            "new repository-relative logs/**/*.json report path",
            rel,
            rel,
        )
    if os.path.lexists(target):
        raise _err(
            codec.ReasonCode.CONFLICT,
            codec.Stage.PATH,
            rel,
            "non-existing report path (exclusive write)",
            rel,
            rel,
        )
    return target, rel


def _validate_events_output(root: Path, events_log_path: str | None) -> tuple[Path, str] | None:
    if events_log_path is None:
        return None
    target, rel = _normalize_repo_path(root, events_log_path, label="events_log", allow_logs=True)
    if not rel.startswith("logs/") or not rel.lower().endswith(".jsonl"):
        raise _err(
            codec.ReasonCode.UNSAFE_PATH,
            codec.Stage.PATH,
            rel,
            "repository-relative logs/**/*.jsonl events log path",
            rel,
            rel,
        )
    return target, rel


def _write_exclusive_report(root: Path, target: Path, rel: str, payload: dict[str, Any]) -> None:
    if os.path.lexists(target):
        raise _err(codec.ReasonCode.CONFLICT, codec.Stage.PATH, rel, "non-existing report path", rel, rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    _check_no_reparse_chain(target, root, rel)
    payload["report_path"] = rel
    raw = (json.dumps(payload, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    try:
        with open(target, "xb") as fh:
            fh.write(raw)
    except FileExistsError as exc:
        payload["report_path"] = None
        raise _err(codec.ReasonCode.CONFLICT, codec.Stage.PATH, rel, "non-existing report path", rel, rel) from exc
    _check_no_reparse_chain(target, root, rel)


def _normalize_required_tier(kind: str, raw_level: str | None) -> str:
    lvl = str(raw_level or "").strip().lower()
    if lvl in {"engine-input", "scene-method", "static-wiring", "manual", "other-verification"}:
        return lvl
    if kind == "dotnet" or lvl in {"domain-integration", "domain-xunit"}:
        return "domain-xunit"
    if kind == "other_verification" or kind == "other-verification":
        return "other-verification"
    if kind == "manual":
        return "manual"
    if kind == "gdunit":
        return "godot-gdunit"
    return lvl or kind


def _tier_matches_strict(required_tier: str, actual_entry: dict[str, Any]) -> tuple[bool, str]:
    """Strict non-substitution check between required evidence tier and executed test entry."""
    actual_kind = str(actual_entry.get("kind") or "").strip().lower()
    actual_tier = _normalize_required_tier(actual_kind, actual_entry.get("evidence_level"))
    req = _normalize_required_tier(actual_kind if required_tier == "" else "", required_tier)

    if req == "manual":
        return False, "machine_evidence_cannot_satisfy_manual_obligation"
    if req == "engine-input":
        if actual_tier != "engine-input":
            return False, f"evidence_tier_substitution_forbidden:required=engine-input,actual={actual_tier}"
        auth = actual_entry.get("input_authenticity")
        if not isinstance(auth, dict) or auth.get("valid") is not True or auth.get("player_action_input_detected") is not True:
            return False, "engine_input_requires_verified_player_action_input"
        return True, "ok"
    if req == "scene-method":
        if actual_tier != "scene-method":
            return False, f"evidence_tier_substitution_forbidden:required=scene-method,actual={actual_tier}"
        return True, "ok"
    if req == "static-wiring":
        if actual_tier != "static-wiring":
            return False, f"evidence_tier_substitution_forbidden:required=static-wiring,actual={actual_tier}"
        return True, "ok"
    if req == "domain-xunit":
        if actual_tier != "domain-xunit" or actual_kind != "dotnet":
            return False, f"evidence_tier_substitution_forbidden:required=domain-xunit,actual={actual_tier}"
        return True, "ok"
    if req == "other-verification":
        if actual_tier != "other-verification" and actual_kind != "other_verification":
            return False, f"evidence_tier_substitution_forbidden:required=other-verification,actual={actual_tier}"
        return True, "ok"
    if req == "godot-gdunit":
        if actual_kind != "gdunit" or actual_tier not in {"godot-gdunit", "scene-method", "engine-input"}:
            return False, f"evidence_tier_substitution_forbidden:required=godot-gdunit,actual={actual_tier}"
        return True, "ok"
    if actual_tier != req:
        return False, f"evidence_tier_substitution_forbidden:required={req},actual={actual_tier}"
    return True, "ok"


def _load_master_tasks(root: Path) -> dict[int, dict[str, Any]]:
    tasks_path = root / ".taskmaster/tasks/tasks.json"
    if not tasks_path.is_file():
        return {}
    _check_no_reparse_chain(tasks_path, root, ".taskmaster/tasks/tasks.json")
    doc = codec.strict_json_loads(tasks_path.read_bytes())
    if not isinstance(doc, dict) or not isinstance(doc.get("master"), dict):
        raise _err(
            codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
            codec.Stage.SCHEMA,
            ".taskmaster/tasks/tasks.json",
            "valid tasks.json with master.tasks list",
            type(doc).__name__,
            ".taskmaster/tasks/tasks.json",
        )
    rows = doc["master"].get("tasks")
    if not isinstance(rows, list):
        raise _err(
            codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
            codec.Stage.SCHEMA,
            ".taskmaster/tasks/tasks.json",
            "master.tasks list",
            type(rows).__name__,
            ".taskmaster/tasks/tasks.json",
        )
    out: dict[int, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and type(row.get("id")) is int:
            out[row["id"]] = row
    return out


def _load_task_test_refs(root: Path) -> dict[int, set[str]]:
    refs: dict[int, set[str]] = {}
    for rel in (".taskmaster/tasks/tasks_back.json", ".taskmaster/tasks/tasks_gameplay.json"):
        p = root / rel
        if not p.is_file():
            continue
        _check_no_reparse_chain(p, root, rel)
        rows = codec.strict_json_loads(p.read_bytes())
        if not isinstance(rows, list):
            raise _err(
                codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
                codec.Stage.SCHEMA,
                rel,
                "list of task view objects",
                type(rows).__name__,
                rel,
            )
        for row in rows:
            if not isinstance(row, dict):
                continue
            tid = row.get("taskmaster_id")
            if type(tid) is not int:
                continue
            slot = refs.setdefault(tid, set())
            for tr in row.get("test_refs") or []:
                if isinstance(tr, str) and tr.strip():
                    slot.add(tr.strip().replace("\\", "/"))
    return refs


def _load_committed_plans_and_bindings(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    plans: dict[str, dict[str, Any]] = {}
    bindings: dict[str, dict[str, Any]] = {}
    catalog_rel = "docs/planning/b-route/catalog.v1.json"
    catalog_path = root / catalog_rel
    if not catalog_path.is_file():
        return plans, bindings
    _check_no_reparse_chain(catalog_path, root, catalog_rel)
    cat = codec.strict_json_loads(catalog_path.read_bytes())
    if not isinstance(cat, dict):
        raise _err(
            codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
            codec.Stage.SCHEMA,
            catalog_rel,
            "JSON object for B-route catalog",
            type(cat).__name__,
            catalog_rel,
        )
    seen_paths: set[str] = set()
    for head in cat.get("scope_heads") or []:
        if not isinstance(head, dict):
            raise _err(
                codec.ReasonCode.INVALID_TYPE,
                codec.Stage.SCHEMA,
                catalog_rel,
                "scope_heads object entry",
                type(head).__name__,
                catalog_rel,
            )
        for key in ("plan_refs", "binding_refs"):
            for ref in head.get(key) or []:
                if not isinstance(ref, dict):
                    raise _err(
                        codec.ReasonCode.INVALID_TYPE,
                        codec.Stage.SCHEMA,
                        catalog_rel,
                        f"{key} reference object",
                        type(ref).__name__,
                        catalog_rel,
                    )
                p = ref.get("path")
                if not isinstance(p, str) or not p.strip():
                    raise _err(
                        codec.ReasonCode.MISSING_REQUIRED_FIELD,
                        codec.Stage.SCHEMA,
                        catalog_rel,
                        f"nonempty {key}.path",
                        p,
                        catalog_rel,
                    )
                if p in seen_paths:
                    continue
                seen_paths.add(p)
                doc, _, rel = _load_strict_json(root, p, label=key, allow_logs=False)
                sv = doc.get("schema_version")
                if sv == "newrouge.b-route-plan.v1" and isinstance(doc.get("plan_id"), str):
                    plans[doc["plan_id"]] = {"path": rel, "doc": doc}
                elif sv == "newrouge.b-route-binding.v1" and isinstance(doc.get("plan_id"), str):
                    bindings[doc["plan_id"]] = {"path": rel, "doc": doc}
    return plans, bindings


def _compute_dedicated_integration_owners(
    manifest_doc: dict[str, Any] | None,
    bindings: dict[str, dict[str, Any]],
    flow_id: str | None = None,
) -> set[int]:
    """Cross-source dedicated integration-only owner calculation.

    Collects integration-only owner declarations AND producer/consumer participant
    roles across BOTH manifest handoffs and Stage-5 bindings using separate checks
    before subtracting all participants from all owners.
    """
    all_owners: set[int] = set()
    all_participants: set[int] = set()

    if isinstance(manifest_doc, dict):
        for mf in manifest_doc.get("flows") or []:
            if not isinstance(mf, dict):
                continue
            if flow_id is not None and mf.get("id") != flow_id:
                continue
            for edge in mf.get("handoffs") or []:
                if not isinstance(edge, dict):
                    continue
                owner = edge.get("owner_task")
                producer = edge.get("producer_task")
                consumer = edge.get("consumer_task")
                if type(owner) is int:
                    all_owners.add(owner)
                if type(producer) is int:
                    all_participants.add(producer)
                if type(consumer) is int:
                    all_participants.add(consumer)

    for binfo in bindings.values():
        bdoc = binfo.get("doc") or {}
        for tm in bdoc.get("task_mappings") or []:
            if not isinstance(tm, dict):
                continue
            tid = tm.get("task_id")
            if type(tid) is not int:
                continue
            fids = [str(f) for f in (tm.get("flow_ids") or []) if isinstance(f, str)]
            if flow_id is not None and flow_id not in fids:
                continue
            role_tokens: set[str] = set()
            for rkey in ("role", "ownership_role"):
                rval = tm.get(rkey)
                if isinstance(rval, str) and rval.strip():
                    role_tokens.add(rval.strip().lower())
            for ritem in tm.get("roles") or []:
                if isinstance(ritem, str) and ritem.strip():
                    role_tokens.add(ritem.strip().lower())
            if tm.get("integration_only_owner") is True or bool(
                role_tokens & {"integration_only_owner", "integration_owner", "owner_only"}
            ):
                all_owners.add(tid)
            if bool(role_tokens & {"producer", "consumer", "implementer", "participant"}):
                all_participants.add(tid)
        for obl in bdoc.get("obligations") or []:
            if not isinstance(obl, dict):
                continue
            ofids = [str(f) for f in (obl.get("flow_ids") or []) if isinstance(f, str)]
            if flow_id is not None and flow_id not in ofids:
                continue
            if type(obl.get("owner_task")) is int:
                all_owners.add(obl["owner_task"])
            if type(obl.get("producer_task")) is int:
                all_participants.add(obl["producer_task"])
            if type(obl.get("consumer_task")) is int:
                all_participants.add(obl["consumer_task"])

    return all_owners - all_participants


def _git_head_and_dirty(root: Path) -> tuple[str, bool]:
    try:
        head = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, timeout=15,
        ).stdout.strip()
        dirty_out = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=normal"],
            capture_output=True, text=True, check=True, timeout=15,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise _err(
            codec.ReasonCode.READ_ERROR,
            codec.Stage.CONTENT,
            ".git",
            "readable git HEAD commit and workspace status",
            str(exc),
            None,
        ) from exc
    if not head:
        raise _err(
            codec.ReasonCode.READ_ERROR,
            codec.Stage.CONTENT,
            ".git",
            "nonempty git HEAD commit hash",
            head,
            None,
        )
    return head, bool(dirty_out)


def _load_and_verify_scope(root: Path, scope_path: str) -> tuple[dict[str, Any], str]:
    doc, _, rel = _load_strict_json(root, scope_path, label="verification_scope", allow_logs=True)
    if evidence_reuse.is_planning_adoption_payload(doc):
        raise _err(
            codec.ReasonCode.SCHEMA_MISMATCH,
            codec.Stage.SCHEMA,
            rel,
            vs.SCHEMA,
            doc.get("schema_version"),
            rel,
        )
    if doc.get("schema_version") != vs.SCHEMA:
        raise _err(
            codec.ReasonCode.UNKNOWN_SCHEMA,
            codec.Stage.SCHEMA,
            rel,
            vs.SCHEMA,
            doc.get("schema_version"),
            rel,
        )
    val = vs.validate_verification_scope(root, rel)
    if not val.get("ok"):
        diags = val.get("diagnostics") or []
        if diags:
            d = diags[0]
            raise codec.CodecError(codec.Diagnostic(
                codec.ReasonCode(d.get("reason_code") or "schema_validation_failed"),
                codec.Stage(d["stage"]) if d.get("stage") in {s.value for s in codec.Stage} else codec.Stage.SCHEMA,
                d.get("entity_id") or rel,
                d.get("expected"),
                d.get("actual"),
                d.get("resume_ref") or rel,
            ))
        raise _err(
            codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
            codec.Stage.SCHEMA,
            rel,
            "valid VerificationScope",
            val.get("reason_code"),
            rel,
        )
    reval = vs.revalidate_verification_scope(root, rel)
    if not reval.get("ok") or not reval.get("valid"):
        raise _err(
            codec.ReasonCode.INPUT_STALE,
            codec.Stage.CONTENT,
            rel,
            {"scope_id": doc.get("scope_id"), "valid": True},
            {
                "status": reval.get("status"),
                "replacement_scope_id": reval.get("replacement_scope_id"),
                "invalidated_obligations": reval.get("invalidated_obligations"),
                "invalidated_flows": reval.get("invalidated_flows"),
            },
            rel,
        )
    return doc, rel


def _load_and_verify_manifest(root: Path, manifest_path: str) -> tuple[dict[str, Any], str, str]:
    doc, target, rel = _load_strict_json(root, manifest_path, label="manifest", allow_logs=False)
    if doc.get("schema_version") != "newrouge.mvg-integration.v1":
        raise _err(
            codec.ReasonCode.UNKNOWN_SCHEMA,
            codec.Stage.SCHEMA,
            rel,
            "newrouge.mvg-integration.v1",
            doc.get("schema_version"),
            rel,
        )
    sha = manifest_sha256(target.read_bytes())
    errors = validate_manifest(root, doc, executable=False)
    if errors:
        raise _err(
            codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
            codec.Stage.SCHEMA,
            rel,
            "valid MVG manifest",
            errors,
            rel,
        )
    return doc, rel, sha


def _resolve_receipt_entry_spec(
    entry: dict[str, Any],
    manifest_tests: dict[str, dict[str, Any]],
) -> tuple[str, str, int]:
    tid = str(entry.get("id") or "")
    kind = str(entry.get("kind") or "").strip().lower()
    mtest = manifest_tests.get(tid) or {}
    if kind == "dotnet":
        expected = str(mtest.get("selector") or "")
        if not expected:
            cmd = entry.get("command") or []
            for idx, tok in enumerate(cmd):
                if tok == "--filter" and idx + 1 < len(cmd):
                    expected = str(cmd[idx + 1]).removeprefix("FullyQualifiedName~")
                    break
        if not expected:
            expected = tid
    else:
        path = str(mtest.get("path") or "")
        if not path:
            cmd = entry.get("command") or []
            for idx, tok in enumerate(cmd):
                if tok == "--add" and idx + 1 < len(cmd):
                    path = str(cmd[idx + 1])
                    break
        expected = Path(path).stem if path else tid
    raw_min = mtest.get("min_tests")
    min_tests = _strict_int(raw_min, field="min_tests", entity_id=tid or None, resume_ref=None, default=1)
    return kind, expected, max(1, min_tests)


def _load_and_verify_receipt(
    root: Path,
    raw_receipt: Any,
    *,
    scope: dict[str, Any] | None,
    manifest_tests: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    target, rel = _normalize_repo_path(root, raw_receipt, label="receipt", allow_logs=True)
    if target.is_dir():
        target = target / "coverage-receipt.json"
        rel = rel.rstrip("/") + "/coverage-receipt.json"
        _check_no_reparse_chain(target, root, rel)
    doc, file_path, rel = _load_strict_json(root, rel, label="coverage_receipt", allow_logs=True)
    if evidence_reuse.is_planning_adoption_payload(doc):
        raise _err(
            codec.ReasonCode.SCHEMA_MISMATCH,
            codec.Stage.SCHEMA,
            rel,
            scope_runner.RECEIPT_SCHEMA,
            doc.get("schema_version"),
            rel,
        )
    if doc.get("schema_version") != scope_runner.RECEIPT_SCHEMA:
        raise _err(
            codec.ReasonCode.UNKNOWN_SCHEMA,
            codec.Stage.SCHEMA,
            rel,
            scope_runner.RECEIPT_SCHEMA,
            doc.get("schema_version"),
            rel,
        )
    if not evidence_reuse.verify_receipt_seal(doc):
        raise _err(
            codec.ReasonCode.DIGEST_MISMATCH,
            codec.Stage.CONTENT,
            rel,
            "valid sealed coverage-receipt.json receipt_id",
            doc.get("receipt_id"),
            rel,
        )

    if doc.get("mode") != "run":
        raise _err(
            codec.ReasonCode.CONFLICT,
            codec.Stage.CONTENT,
            rel,
            "mode == 'run'",
            doc.get("mode"),
            rel,
        )

    # Check scope binding & drift
    if scope is not None:
        if doc.get("scope_id") != scope.get("scope_id"):
            raise _err(
                codec.ReasonCode.INPUT_STALE,
                codec.Stage.CONTENT,
                rel,
                scope.get("scope_id"),
                doc.get("scope_id"),
                rel,
            )
        if doc.get("input_set_digest") != scope.get("input_set_digest"):
            raise _err(
                codec.ReasonCode.INPUT_STALE,
                codec.Stage.CONTENT,
                rel,
                scope.get("input_set_digest"),
                doc.get("input_set_digest"),
                rel,
            )

    drift = doc.get("drift")
    if isinstance(drift, dict):
        if drift.get("drift_detected") is True or drift.get("post_run_valid") is False:
            raise _err(
                codec.ReasonCode.INPUT_STALE,
                codec.Stage.CONTENT,
                rel,
                {"drift_detected": False, "post_run_valid": True},
                drift,
                rel,
            )

    iso = doc.get("state_isolation")
    if isinstance(iso, dict) and iso.get("pollution_detected") is True:
        raise _err(
            codec.ReasonCode.CONFLICT,
            codec.Stage.CONTENT,
            rel,
            {"pollution_detected": False},
            iso.get("polluted_tests"),
            rel,
        )

    snap_digest = doc.get("snapshot_digest")
    if type(snap_digest) is not str or not _SNAPSHOT_DIGEST_RE.fullmatch(snap_digest):
        raise _err(
            codec.ReasonCode.INVALID_DIGEST,
            codec.Stage.CONTENT,
            rel,
            "64-hex or sha256:<64-hex> snapshot_digest",
            snap_digest,
            rel,
        )

    run_dir = file_path.parent
    input_manifest_rel = (run_dir / "input-manifest.json").relative_to(root.resolve()).as_posix()
    im_doc, _, _ = _load_strict_json(root, input_manifest_rel, label="input_manifest", allow_logs=True)
    im_snap = im_doc.get("snapshot_digest")
    if type(im_snap) is not str or not _SNAPSHOT_DIGEST_RE.fullmatch(im_snap):
        raise _err(
            codec.ReasonCode.INVALID_DIGEST,
            codec.Stage.CONTENT,
            input_manifest_rel,
            "64-hex or sha256:<64-hex> snapshot_digest in input-manifest.json",
            im_snap,
            rel,
        )
    if _raw_hex(im_snap) != _raw_hex(snap_digest):
        raise _err(
            codec.ReasonCode.DIGEST_MISMATCH,
            codec.Stage.CONTENT,
            input_manifest_rel,
            snap_digest,
            im_snap,
            rel,
        )

    cov_summary = doc.get("coverage_summary") if isinstance(doc.get("coverage_summary"), dict) else {}
    if _strict_int(cov_summary.get("skipped_count"), field="coverage_summary.skipped_count", entity_id=rel, resume_ref=rel, default=0) > 0:
        raise _err(
            codec.ReasonCode.CONFLICT,
            codec.Stage.CONTENT,
            rel,
            {"skipped_count": 0},
            {"skipped_count": cov_summary.get("skipped_count")},
            rel,
        )
    raw_reverified_tests: dict[str, dict[str, Any]] = {}
    failed_tests: list[dict[str, Any]] = []
    skipped_tests: list[dict[str, Any]] = []
    any_step_protocol_fixture = False

    for entry in doc.get("executed_tests") or []:
        if not isinstance(entry, dict):
            raise _err(
                codec.ReasonCode.INVALID_TYPE,
                codec.Stage.CONTENT,
                rel,
                "executed_tests object entry",
                type(entry).__name__,
                rel,
            )
        tid = str(entry.get("id") or "")
        kind = str(entry.get("kind") or "").strip().lower()
        status = str(entry.get("status") or "").strip().lower()
        step_auth = str(entry.get("evidence_authenticity") or "").strip().lower()
        if step_auth == "protocol_fixture":
            any_step_protocol_fixture = True

        skipped_cases = _strict_int(entry.get("skipped_cases"), field="skipped_cases", entity_id=tid or rel, resume_ref=rel, default=0)
        failed_cases = _strict_int(entry.get("failed_cases"), field="failed_cases", entity_id=tid or rel, resume_ref=rel, default=0)
        passed_cases = _strict_int(entry.get("passed_cases"), field="passed_cases", entity_id=tid or rel, resume_ref=rel, default=0)

        if skipped_cases > 0:
            skipped_tests.append({"test_id": tid, "skipped_cases": skipped_cases, "receipt": rel})
        if status != "passed" or failed_cases > 0:
            failed_tests.append({
                "test_id": tid,
                "status": status,
                "failed_cases": failed_cases,
                "reason": entry.get("evidence_reason") or status,
                "receipt": rel,
            })
            continue

        if kind in {"dotnet", "gdunit"}:
            r_kind, expected_name, min_tests = _resolve_receipt_entry_spec(entry, manifest_tests)
            ok_raw, recheck, reason = evidence_reuse._reverify_raw_reports(
                root,
                run_dir,
                entry,
                kind=r_kind,
                expected=expected_name,
                min_tests=min_tests,
            )
            if not ok_raw:
                raise _err(
                    codec.ReasonCode.DIGEST_MISMATCH,
                    codec.Stage.CONTENT,
                    tid or rel,
                    f"passing non-empty raw {r_kind} report for {expected_name} (min_tests={min_tests})",
                    {"reason": reason, "recheck": recheck},
                    rel,
                )
            if _strict_int(recheck.get("skipped"), field="recheck.skipped", entity_id=tid or rel, resume_ref=rel, default=0) > 0:
                raise _err(
                    codec.ReasonCode.CONFLICT,
                    codec.Stage.CONTENT,
                    tid or rel,
                    {"skipped": 0},
                    {"skipped": recheck.get("skipped")},
                    rel,
                )
            if _strict_int(recheck.get("tests"), field="recheck.tests", entity_id=tid or rel, resume_ref=rel, default=0) < min_tests:
                raise _err(
                    codec.ReasonCode.CONFLICT,
                    codec.Stage.CONTENT,
                    tid or rel,
                    {"min_tests": min_tests},
                    {"tests": recheck.get("tests")},
                    rel,
                )
            raw_reverified_tests[tid] = {**entry, "_raw_recheck": recheck, "_receipt_path": rel}
        elif kind == "other_verification":
            ec = _strict_int(entry.get("exit_code"), field="exit_code", entity_id=tid or rel, resume_ref=rel, default=1)
            if ec != 0:
                failed_tests.append({"test_id": tid, "status": "failed", "reason": "nonzero_exit_code", "receipt": rel})
                continue
            log_file = _resolve_contained_run_file(
                root,
                run_dir,
                entry.get("log_path"),
                label="other_verification.log_path",
                entity_id=tid or rel,
                resume_ref=rel,
            )
            if not log_file.read_text(encoding="utf-8", errors="replace").strip():
                raise _err(
                    codec.ReasonCode.CONFLICT,
                    codec.Stage.CONTENT,
                    tid or rel,
                    "nonempty other_verification log output",
                    str(entry.get("log_path")),
                    rel,
                )
            raw_reverified_tests[tid] = {**entry, "_receipt_path": rel}
        elif kind == "static-wiring":
            raw_rps = entry.get("report_paths")
            sw_raw_ref = (
                raw_rps[0]
                if isinstance(raw_rps, list) and raw_rps
                else entry.get("log_path")
            )
            sw_file = _resolve_contained_run_file(
                root,
                run_dir,
                sw_raw_ref,
                label="static-wiring.report.json",
                entity_id=tid or rel,
                resume_ref=rel,
            )
            sw_doc = codec.strict_json_loads(sw_file.read_bytes())
            if not isinstance(sw_doc, dict) or sw_doc.get("wiring_static_ok") is not True:
                raise _err(
                    codec.ReasonCode.CONFLICT,
                    codec.Stage.CONTENT,
                    tid or rel,
                    {"wiring_static_ok": True},
                    sw_doc.get("wiring_static_ok") if isinstance(sw_doc, dict) else type(sw_doc).__name__,
                    rel,
                )
            if passed_cases < 1 and not sw_doc.get("scenes_inspected") and not sw_doc.get("adapters_inspected"):
                raise _err(
                    codec.ReasonCode.CONFLICT,
                    codec.Stage.CONTENT,
                    tid or rel,
                    "nonempty static-wiring inspection",
                    {"passed_cases": passed_cases},
                    rel,
                )
            raw_reverified_tests[tid] = {**entry, "_static_wiring_report": sw_doc, "_receipt_path": rel}
        else:
            raise _err(
                codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
                codec.Stage.CONTENT,
                tid or rel,
                ["dotnet", "gdunit", "other_verification", "static-wiring"],
                kind,
                rel,
            )

    env = doc.get("environment") if isinstance(doc.get("environment"), dict) else {}
    protocol_fixture_only = (
        env.get("protocol_fixture_only") is True
        or str(env.get("evidence_authenticity") or "").strip().lower() == "protocol_fixture"
        or any_step_protocol_fixture
    )
    automated_scope_passed = (
        doc.get("automated_scope_passed") is True
        and not failed_tests
        and not skipped_tests
    )
    return {
        "path": rel,
        "run_dir": run_dir,
        "doc": doc,
        "snapshot_digest": snap_digest,
        "source_revision": doc.get("source_revision"),
        "workspace_dirty": bool(doc.get("workspace_dirty")),
        "protocol_fixture_only": protocol_fixture_only,
        "automated_scope_passed": automated_scope_passed,
        "runtime_verified": (doc.get("runtime_verified") is True) and not protocol_fixture_only,
        "reverified_tests": raw_reverified_tests,
        "failed_tests": failed_tests,
        "skipped_tests": skipped_tests,
        "not_run": list(doc.get("not_run") or []),
        "manual_obligations": list(doc.get("manual_obligations") or []),
    }


def _check_cross_snapshot_consistency(loaded_receipts: list[dict[str, Any]]) -> tuple[str | None, str | None, bool | None]:
    if not loaded_receipts:
        return None, None, None
    first = loaded_receipts[0]
    snap = first["snapshot_digest"]
    rev = first["source_revision"]
    dirty = first["workspace_dirty"]
    for other in loaded_receipts[1:]:
        if (
            _raw_hex(other["snapshot_digest"]) != _raw_hex(snap)
            or other["source_revision"] != rev
            or other["workspace_dirty"] != dirty
        ):
            raise _err(
                codec.ReasonCode.CONFLICT,
                codec.Stage.CONTENT,
                other["path"],
                {"snapshot_digest": snap, "source_revision": rev, "workspace_dirty": dirty},
                {
                    "reason": "cross_snapshot_report_splicing_forbidden",
                    "snapshot_digest": other["snapshot_digest"],
                    "source_revision": other["source_revision"],
                    "workspace_dirty": other["workspace_dirty"],
                },
                other["path"],
            )
    return snap, rev, dirty


def _is_substantive_manual_notes(notes: Any) -> bool:
    if type(notes) is not str:
        return False
    text = notes.strip()
    if len(text) < _MIN_MANUAL_NOTE_CHARS:
        return False
    lower = text.lower()
    if re.search(r"(?<![a-z0-9])n/a(?![a-z0-9])", lower):
        return False
    slash_tokens = set(re.findall(r"[a-z0-9]+(?:/[a-z0-9]+)?", lower))
    word_tokens = set(re.findall(r"[a-z0-9]+", lower))
    all_ascii_tokens = slash_tokens | word_tokens
    if all_ascii_tokens & _FORBIDDEN_MANUAL_NOTE_TOKENS:
        return False
    cjk_chars = _CJK_RE.findall(text)
    if not all_ascii_tokens and len(cjk_chars) < 6:
        return False
    return True


def _load_and_verify_manual_signoff(
    root: Path,
    manual_signoff_path: str | None,
    *,
    expected_scope_id: str | None,
    expected_snapshot_digest: str | None,
) -> tuple[dict[str, dict[str, Any]], str | None]:
    if manual_signoff_path is None:
        return {}, None
    doc, _, rel = _load_strict_json(root, manual_signoff_path, label="manual_signoff", allow_logs=True)
    if doc.get("schema_version") != MANUAL_SIGNOFF_SCHEMA:
        raise _err(
            codec.ReasonCode.UNKNOWN_SCHEMA,
            codec.Stage.SCHEMA,
            rel,
            MANUAL_SIGNOFF_SCHEMA,
            doc.get("schema_version"),
            rel,
        )
    doc_scope_id = doc.get("scope_id")
    if type(doc_scope_id) is not str or not doc_scope_id.strip():
        raise _err(
            codec.ReasonCode.MISSING_REQUIRED_FIELD,
            codec.Stage.CONTENT,
            rel,
            "nonempty scope_id matching target VerificationScope",
            doc_scope_id,
            rel,
        )
    if expected_scope_id is not None and doc_scope_id != expected_scope_id:
        raise _err(
            codec.ReasonCode.INPUT_STALE,
            codec.Stage.CONTENT,
            rel,
            expected_scope_id,
            doc_scope_id,
            rel,
        )
    doc_snap = doc.get("snapshot_digest")
    if type(doc_snap) is not str or not _SNAPSHOT_DIGEST_RE.fullmatch(doc_snap):
        raise _err(
            codec.ReasonCode.INVALID_DIGEST,
            codec.Stage.CONTENT,
            rel,
            "nonempty 64-hex or sha256:<64-hex> snapshot_digest",
            doc_snap,
            rel,
        )
    if expected_snapshot_digest is not None and _raw_hex(doc_snap) != _raw_hex(expected_snapshot_digest):
        raise _err(
            codec.ReasonCode.INPUT_STALE,
            codec.Stage.CONTENT,
            rel,
            expected_snapshot_digest,
            doc_snap,
            rel,
        )
    reviewer = doc.get("reviewer")
    if type(reviewer) is not str or not reviewer.strip():
        raise _err(
            codec.ReasonCode.MISSING_REQUIRED_FIELD,
            codec.Stage.CONTENT,
            rel,
            "nonempty reviewer name",
            reviewer,
            rel,
        )
    entries = doc.get("entries")
    if not isinstance(entries, list) or not entries:
        raise _err(
            codec.ReasonCode.MISSING_REQUIRED_FIELD,
            codec.Stage.CONTENT,
            rel,
            "nonempty manual signoff entries list",
            entries,
            rel,
        )
    verified: dict[str, dict[str, Any]] = {}
    for item in entries:
        if not isinstance(item, dict):
            raise _err(codec.ReasonCode.INVALID_TYPE, codec.Stage.CONTENT, rel, "manual entry dict", type(item).__name__, rel)
        mid = str(item.get("manual_id") or "").strip()
        if not mid:
            raise _err(codec.ReasonCode.MISSING_REQUIRED_FIELD, codec.Stage.CONTENT, rel, "nonempty manual_id", item, rel)
        if mid in verified:
            raise _err(
                codec.ReasonCode.CONFLICT,
                codec.Stage.CONTENT,
                mid,
                "unique manual_id in manual_signoff entries",
                f"duplicate:{mid}",
                rel,
            )
        st = str(item.get("status") or "").strip().lower()
        if st != "approved":
            raise _err(
                codec.ReasonCode.CONFLICT,
                codec.Stage.CONTENT,
                mid,
                "status == 'approved'",
                item.get("status"),
                rel,
            )
        if not _is_substantive_manual_notes(item.get("notes")):
            raise _err(
                codec.ReasonCode.SEMANTIC_ERROR,
                codec.Stage.CONTENT,
                mid,
                "substantive manual acceptance notes (>= 12 chars, no forbidden skip/waive/placeholder tokens)",
                item.get("notes"),
                rel,
            )
        verified[mid] = {
            "manual_id": mid,
            "reviewer": reviewer.strip(),
            "notes": str(item["notes"]).strip(),
            "signed_at": item.get("signed_at"),
            "signoff_path": rel,
        }
    return verified, rel


def _extract_ch7_manual_ids(c7_doc: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for mi in c7_doc.get("manual_items") or []:
        mid = str(mi.get("manual_id") or mi.get("id") or "") if isinstance(mi, dict) else str(mi)
        if mid.strip():
            out.append(mid.strip())
    return sorted(set(out))


def _load_and_verify_chapter7_report(
    root: Path,
    report_path: str,
    *,
    expected_flow_id: str | None,
    expected_input_set_digest: str | None,
) -> tuple[dict[str, Any], str]:
    doc, _, rel = _load_strict_json(root, report_path, label="chapter7_slice_report", allow_logs=True)
    if doc.get("schema_version") != ch7_slice.SCHEMA:
        raise _err(
            codec.ReasonCode.UNKNOWN_SCHEMA,
            codec.Stage.SCHEMA,
            rel,
            ch7_slice.SCHEMA,
            doc.get("schema_version"),
            rel,
        )
    if expected_flow_id is not None and doc.get("target_flow_id") not in (None, expected_flow_id):
        raise _err(
            codec.ReasonCode.MAPPING_MISMATCH,
            codec.Stage.CONTENT,
            rel,
            expected_flow_id,
            doc.get("target_flow_id"),
            rel,
        )
    if expected_input_set_digest is not None and doc.get("input_set_digest") is not None:
        if doc.get("input_set_digest") != expected_input_set_digest:
            raise _err(
                codec.ReasonCode.INPUT_STALE,
                codec.Stage.CONTENT,
                rel,
                expected_input_set_digest,
                doc.get("input_set_digest"),
                rel,
            )
    # Verify task_input_sets against live InputSet resolver (never trust drifted logs/** reports)
    tis = doc.get("task_input_sets")
    if tis is not None:
        if not isinstance(tis, dict):
            raise _err(codec.ReasonCode.INVALID_TYPE, codec.Stage.CONTENT, rel, "task_input_sets object", type(tis).__name__, rel)
        for tid_key, tmeta in tis.items():
            tid_int = ch6_gate.parse_strict_task_id(tid_key)
            rec_digest = tmeta.get("input_set_digest") if isinstance(tmeta, dict) else None
            live_is = input_set_mod.resolve_input_set(root, tid_int)
            live_digest = live_is.get("input_set_digest")
            if not live_digest or rec_digest != live_digest:
                raise _err(
                    codec.ReasonCode.INPUT_STALE,
                    codec.Stage.CONTENT,
                    rel,
                    {"task_id": tid_int, "input_set_digest": live_digest},
                    {"task_id": tid_int, "input_set_digest": rec_digest},
                    rel,
                )
    return doc, rel


def _is_ch7_doc_satisfied(c7_doc: dict[str, Any]) -> bool:
    if c7_doc.get("ok") is not True:
        return False
    if c7_doc.get("pending_items") or c7_doc.get("blocked_items"):
        return False
    if c7_doc.get("governed_gap_routing") or c7_doc.get("gap_routing"):
        return False
    if str(c7_doc.get("ui_applicability") or "").strip().lower() == "applicable":
        wi = c7_doc.get("wiring_inspection")
        if not isinstance(wi, dict) or wi.get("wiring_static_ok") is not True:
            return False
    return True


def _flow_requires_chapter7(
    flow_id: str,
    plans: dict[str, dict[str, Any]],
    bindings: dict[str, dict[str, Any]],
    manifest_doc: dict[str, Any] | None,
    scope: dict[str, Any] | None,
) -> bool:
    flow_plan_ids: set[str] = set()
    for pid, pinfo in plans.items():
        flows = ((pinfo.get("doc") or {}).get("definitions") or {}).get("flows") or []
        for f in flows:
            if isinstance(f, dict) and f.get("id") == flow_id:
                flow_plan_ids.add(pid)
                ui = f.get("ui")
                if isinstance(ui, dict):
                    if str(ui.get("applicability") or "").strip().lower() == "applicable":
                        return True
                    for sref in ui.get("scene_refs") or []:
                        if isinstance(sref, str) and sref.strip().lower().endswith(".tscn"):
                            return True
    for pid, binfo in bindings.items():
        bdoc = binfo.get("doc") or {}
        flow_tids = {
            tm["task_id"]
            for tm in (bdoc.get("task_mappings") or [])
            if isinstance(tm, dict) and flow_id in (tm.get("flow_ids") or []) and type(tm.get("task_id")) is int
        }
        in_plan = pid in flow_plan_ids or bool(flow_tids)
        if not in_plan:
            continue
        for part in bdoc.get("parts") or []:
            if not isinstance(part, dict):
                continue
            p_kind = str(part.get("kind") or "").strip().lower()
            p_path = str(part.get("path") or part.get("ref") or "").strip().lower()
            if p_kind in {"scene", "ui"} or p_path.endswith(".tscn"):
                return True
        for obj in bdoc.get("implementation_objects") or []:
            if not isinstance(obj, dict):
                continue
            obj_flows = set(str(f) for f in (obj.get("flow_ids") or []) if isinstance(f, str))
            obj_tids = {t for t in (obj.get("responsible_task_ids") or []) if type(t) is int}
            if obj_flows and flow_id not in obj_flows and not (obj_tids & flow_tids):
                continue
            if str(obj.get("kind") or "").strip().lower() in {"scene", "ui"}:
                return True
            tref = obj.get("target_ref")
            if isinstance(tref, dict):
                for f in tref.get("files") or []:
                    if isinstance(f, dict) and str(f.get("path") or "").strip().lower().endswith(".tscn"):
                        return True
    if isinstance(manifest_doc, dict):
        for mf in manifest_doc.get("flows") or []:
            if isinstance(mf, dict) and mf.get("id") == flow_id:
                for sp in mf.get("source_paths") or []:
                    if isinstance(sp, str) and sp.strip().lower().endswith(".tscn"):
                        return True
    if isinstance(scope, dict):
        for obl in scope.get("obligations") or []:
            if not isinstance(obl, dict) or flow_id not in (obl.get("flow_ids") or []):
                continue
            if obl.get("tier") in vs.CURRENT_TIERS and obl.get("evidence_level") in {"engine-input", "scene-method", "static-wiring"}:
                if obl.get("evidence_level") == "static-wiring" or any(
                    str(t).lower().endswith(".tscn") for t in (obl.get("missing_targets") or [])
                ):
                    return True
    return False


def _verify_chapter7_for_flow(
    root: Path,
    *,
    flow_id: str,
    scope_doc: dict[str, Any] | None,
    chapter7_slice_report: str | None,
    plans: dict[str, dict[str, Any]],
    bindings: dict[str, dict[str, Any]],
    manifest_doc: dict[str, Any] | None,
    strict_report_flow_match: bool = True,
) -> tuple[bool, dict[str, Any] | None, list[str], list[str]]:
    """Verify Chapter 7 UI closure for a Flow (report with live InputSet check, or live slice evaluation)."""
    requires_ch7 = _flow_requires_chapter7(flow_id, plans, bindings, manifest_doc, scope_doc)
    if chapter7_slice_report is not None:
        c7_doc, c7_rel = _load_and_verify_chapter7_report(
            root,
            chapter7_slice_report,
            expected_flow_id=flow_id if strict_report_flow_match else None,
            expected_input_set_digest=scope_doc.get("input_set_digest") if scope_doc else None,
        )
        rep_flow = c7_doc.get("target_flow_id")
        if rep_flow in (None, flow_id):
            c7_ok = _is_ch7_doc_satisfied(c7_doc)
            manual_items = _extract_ch7_manual_ids(c7_doc)
            summary = {
                "report_path": c7_rel,
                "flow_id": flow_id,
                "ok": c7_ok,
                "ui_applicability": c7_doc.get("ui_applicability"),
                "wiring_static_ok": bool(
                    isinstance(c7_doc.get("wiring_inspection"), dict)
                    and c7_doc["wiring_inspection"].get("wiring_static_ok") is True
                ),
            }
            missing = [] if c7_ok else [f"chapter7:{flow_id}:incomplete_or_blocked"]
            return c7_ok, summary, missing, manual_items
    if not requires_ch7:
        return True, None, [], []
    # Live Chapter 7 slice evaluation when no matching report was provided for a UI-applicable Flow
    live_c7 = ch7_slice.evaluate_chapter7_slice(root, flow_id=flow_id)
    live_ok = _is_ch7_doc_satisfied(live_c7)
    manual_items = _extract_ch7_manual_ids(live_c7)
    wi = live_c7.get("wiring_inspection")
    summary = {
        "live_evaluated": True,
        "flow_id": flow_id,
        "ok": live_ok,
        "ui_applicability": live_c7.get("ui_applicability"),
        "wiring_static_ok": bool(isinstance(wi, dict) and wi.get("wiring_static_ok") is True),
    }
    missing = [] if live_ok else [f"chapter7:{flow_id}:missing_verified_ui_closure"]
    return live_ok, summary, missing, manual_items


def _is_flow_out_of_scope_future(fc: dict[str, Any]) -> bool:
    if fc.get("classification") == "out_of_scope_future":
        return True
    return (
        fc.get("has_out_of_scope_future") is True
        and not fc.get("in_current_delivery_scope")
        and not fc.get("has_existing_required")
        and not fc.get("has_current_new")
    )


def _collect_manual_obligations_for_scope(
    scope: dict[str, Any] | None,
    loaded_receipts: list[dict[str, Any]],
    *,
    flow_id: str | None = None,
) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    if isinstance(scope, dict):
        plan_view = scope.get("execution_plan") or {}
        for item in plan_view.get("manual_obligations") or []:
            if not isinstance(item, dict):
                continue
            fids = [str(f) for f in (item.get("flow_ids") or []) if isinstance(f, str)]
            if flow_id is not None and flow_id not in fids:
                continue
            if item.get("tier") == "out_of_scope_future":
                continue
            mid = str(item.get("manual_id") or item.get("obligation_id") or "").strip()
            if mid:
                seen[mid] = {
                    "manual_id": mid,
                    "obligation_id": item.get("obligation_id"),
                    "flow_ids": fids,
                    "tier": item.get("tier"),
                    "check": item.get("check") or item.get("description") or mid,
                }
        for obl in scope.get("obligations") or []:
            if not isinstance(obl, dict):
                continue
            if obl.get("tier") not in vs.CURRENT_TIERS:
                continue
            if obl.get("evidence_level") != "manual" and obl.get("execution_kind") not in {"manual", "manual_check"}:
                continue
            fids = [str(f) for f in (obl.get("flow_ids") or []) if isinstance(f, str)]
            if flow_id is not None and flow_id not in fids:
                continue
            mid = str(obl.get("obligation_id") or "").strip()
            if mid and mid not in seen:
                seen[mid] = {
                    "manual_id": mid,
                    "obligation_id": mid,
                    "flow_ids": fids,
                    "tier": obl.get("tier"),
                    "check": mid,
                }
    for rec in loaded_receipts:
        for item in rec.get("manual_obligations") or []:
            if not isinstance(item, dict):
                continue
            fids = [str(f) for f in (item.get("flow_ids") or []) if isinstance(f, str)]
            if flow_id is not None and fids and flow_id not in fids:
                continue
            if item.get("tier") == "out_of_scope_future":
                continue
            mid = str(item.get("manual_id") or item.get("obligation_id") or "").strip()
            if mid and mid not in seen:
                seen[mid] = {
                    "manual_id": mid,
                    "obligation_id": item.get("obligation_id"),
                    "flow_ids": fids,
                    "tier": item.get("tier"),
                    "check": item.get("check") or mid,
                }
    return [seen[k] for k in sorted(seen)]


def _merge_receipt_tests(loaded_receipts: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    passed_tests: dict[str, dict[str, Any]] = {}
    failed_tests: list[dict[str, Any]] = []
    skipped_tests: list[dict[str, Any]] = []
    not_run_blocking: list[dict[str, Any]] = []
    for rec in loaded_receipts:
        for tid, entry in rec["reverified_tests"].items():
            passed_tests[tid] = entry
        failed_tests.extend(rec["failed_tests"])
        skipped_tests.extend(rec["skipped_tests"])
        for nr in rec["not_run"]:
            if isinstance(nr, dict) and nr.get("blocking_current_delivery"):
                not_run_blocking.append(nr)
    return passed_tests, failed_tests, skipped_tests, not_run_blocking


def _evaluate_obligation_satisfaction(
    obl: dict[str, Any],
    passed_tests: dict[str, dict[str, Any]],
    failed_tests: list[dict[str, Any]],
    manifest_tests: dict[str, dict[str, Any]],
) -> tuple[bool, list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (satisfied, missing_items, tier_violations) for a single current-tier obligation."""
    oid = str(obl.get("obligation_id") or "")
    status = str(obl.get("status") or "").strip().lower()
    tier = str(obl.get("tier") or "")
    ev_level = str(obl.get("evidence_level") or "")
    test_ids = [str(t) for t in (obl.get("test_ids") or []) if isinstance(t, str) and t.strip()]
    ov_refs = [str(r) for r in (obl.get("other_verification_refs") or []) if isinstance(r, str) and r.strip()]
    missing_targets = [str(m) for m in (obl.get("missing_targets") or []) if isinstance(m, str) and m.strip()]

    missing: list[dict[str, Any]] = []
    tier_violations: list[dict[str, Any]] = []

    if status in {"pending", "blocked"} or missing_targets:
        missing.append({
            "obligation_id": oid,
            "tier": tier,
            "status": status,
            "reason": "obligation_unimplemented_or_blocked",
            "missing_targets": missing_targets,
            "flow_ids": list(obl.get("flow_ids") or []),
            "task_ids": list(obl.get("task_ids") or []),
            "test_ids": test_ids,
        })
        return False, missing, tier_violations

    if ev_level == "manual" or obl.get("execution_kind") in {"manual", "manual_check"}:
        return True, [], []

    failed_ids = {str(f.get("test_id") or "") for f in failed_tests}

    if test_ids:
        for tid in test_ids:
            if tid in failed_ids:
                missing.append({
                    "obligation_id": oid,
                    "tier": tier,
                    "test_id": tid,
                    "reason": "test_failed",
                    "flow_ids": list(obl.get("flow_ids") or []),
                    "task_ids": list(obl.get("task_ids") or []),
                })
                continue
            entry = passed_tests.get(tid)
            if entry is None:
                missing.append({
                    "obligation_id": oid,
                    "tier": tier,
                    "test_id": tid,
                    "reason": "test_not_executed_or_missing_evidence",
                    "flow_ids": list(obl.get("flow_ids") or []),
                    "task_ids": list(obl.get("task_ids") or []),
                })
                continue
            mtest = manifest_tests.get(tid) or {}
            req_tier = _normalize_required_tier(
                str(mtest.get("kind") or entry.get("kind") or ""),
                mtest.get("evidence_level") or ev_level,
            )
            tier_ok, tier_reason = _tier_matches_strict(req_tier, entry)
            if not tier_ok:
                tier_violations.append({
                    "obligation_id": oid,
                    "test_id": tid,
                    "required_tier": req_tier,
                    "actual_tier": _normalize_required_tier(str(entry.get("kind") or ""), entry.get("evidence_level")),
                    "reason": tier_reason,
                })
        return not missing and not tier_violations, missing, tier_violations

    if ov_refs or ev_level == "other-verification" or obl.get("execution_kind") == "other_verification":
        matched_ov = [
            entry for tid, entry in passed_tests.items()
            if entry.get("kind") == "other_verification"
            and (
                entry.get("obligation_id") == oid
                or oid in (entry.get("obligation_ids") or [])
                or tid in ov_refs
                or any(ref in str(entry.get("script_path") or "") or ref == tid for ref in ov_refs)
            )
        ]
        if not matched_ov:
            missing.append({
                "obligation_id": oid,
                "tier": tier,
                "other_verification_refs": ov_refs,
                "reason": "other_verification_not_executed_or_missing_evidence",
                "flow_ids": list(obl.get("flow_ids") or []),
                "task_ids": list(obl.get("task_ids") or []),
            })
            return False, missing, tier_violations
        return True, [], []

    # Implementation-object obligation with ready status has no separate test_id unless missing_targets existed.
    if obl.get("execution_kind") in {"implementation_object", "implementation"}:
        return True, [], []

    # Unknown / uncovered obligation: fail closed.
    missing.append({
        "obligation_id": oid,
        "tier": tier,
        "reason": "obligation_lacks_verifiable_evidence",
        "flow_ids": list(obl.get("flow_ids") or []),
        "task_ids": list(obl.get("task_ids") or []),
    })
    return False, missing, tier_violations


def _base_verdict_payload(*, level: str, operation: str, started: float) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA,
        "ok": False,
        "level": level,
        "verdict_status": "blocked",
        "verified_scope": "none",
        "operation": operation,
        "reason_code": codec.ReasonCode.CONFLICT.value,
        "reason": "",
        "task_id": None,
        "flow_id": None,
        "scope_id": None,
        "input_set_digest": None,
        "snapshot_digest": None,
        "source_revision": None,
        "workspace_dirty": None,
        "task_local_satisfied": False,
        "automated_flow_passed": False,
        "flow_completed": False,
        "flow_status": "unknown",
        "automated_milestone_passed": False,
        "cumulative_full_mvg_completed": False,
        "milestone_completed": False,
        "non_flow_completed": False,
        "runtime_verified": False,
        "protocol_fixture_satisfied_only": False,
        "manual_pending": False,
        "cross_snapshot_splicing_detected": False,
        "forced_premature_future_implementation": False,
        "dedicated_integration_owner_task_ids": [],
        "blocking_participant_task_ids": [],
        "missing_flow_obligations": {
            "missing_tasks": [],
            "missing_tests": [],
            "missing_implementations": [],
            "missing_chapter7_slices": [],
            "pending_manual_obligations": [],
        },
        "evidence_tier_violations": [],
        "failed_existing_flows": [],
        "failed_tests": [],
        "skipped_tests": [],
        "out_of_scope_future_tracked": [],
        "flow_verdicts": {},
        "manual_signoff_verified": [],
        "chapter7_slice": None,
        "receipt_paths": [],
        "manifest_path": None,
        "verification_scope_path": None,
        "diagnostics": [],
        "report_path": None,
        "events_log_path": None,
        "metrics": {"active_elapsed_seconds": _elapsed(started)},
        "INVARIANT_FLAGS": dict(INVARIANT_FLAGS),
        **INVARIANT_FLAGS,
    }


def _finalize_verdict(
    root: Path | None,
    payload: dict[str, Any],
    report_target: tuple[Path, str] | None,
    events_target: tuple[Path, str] | None,
    started: float,
) -> dict[str, Any]:
    payload["metrics"] = {"active_elapsed_seconds": _elapsed(started)}
    for key, val in INVARIANT_FLAGS.items():
        payload[key] = val
    payload["INVARIANT_FLAGS"] = dict(INVARIANT_FLAGS)

    # Write --report BEFORE --events-log so a failing exclusive report write never pollutes events.
    if report_target is not None and root is not None:
        rep_path, rep_rel = report_target
        if events_target is not None:
            payload["events_log_path"] = events_target[1]
        _write_exclusive_report(root, rep_path, rep_rel, payload)

    if events_target is not None:
        ev_path, ev_rel = events_target
        evidence_reuse.append_deduplicated_event(ev_path, {
            "event_type": "completion_verdict_evaluated",
            "level": payload.get("level"),
            "ok": payload.get("ok"),
            "verdict_status": payload.get("verdict_status"),
            "verified_scope": payload.get("verified_scope"),
            "reason_code": payload.get("reason_code"),
            "reason": payload.get("reason"),
            "task_id": payload.get("task_id"),
            "flow_id": payload.get("flow_id"),
            "scope_id": payload.get("scope_id"),
            "snapshot_digest": payload.get("snapshot_digest"),
            "task_local_satisfied": payload.get("task_local_satisfied"),
            "flow_completed": payload.get("flow_completed"),
            "cumulative_full_mvg_completed": payload.get("cumulative_full_mvg_completed"),
            "milestone_completed": payload.get("milestone_completed"),
            "non_flow_completed": payload.get("non_flow_completed"),
            "runtime_verified": payload.get("runtime_verified"),
        })
        payload["events_log_path"] = ev_rel

    return payload


def evaluate_completion_verdict(
    root: Path | str,
    *,
    level: str,
    task_id: int | str | None = None,
    flow_id: str | None = None,
    manifest_path: str | Path | None = None,
    verification_scope_path: str | Path | None = None,
    receipt_paths: list[str | Path] | str | Path | None = None,
    chapter7_slice_report: str | Path | None = None,
    manual_signoff_path: str | Path | None = None,
    milestone_handoff_path: str | Path | None = None,
    inline_handoff: dict[str, Any] | None = None,
    operation: str = "completion_verdict",
    report_path: str | None = None,
    events_log_path: str | None = None,
) -> dict[str, Any]:
    """Evaluate completion verdict strictly at the requested level without mutating authority files."""
    started = time.monotonic()
    op = operation if isinstance(operation, str) and operation.strip() else "completion_verdict"
    lvl = str(level or "").strip().lower()
    payload = _base_verdict_payload(level=lvl, operation=op, started=started)

    root_path: Path | None = None
    report_target: tuple[Path, str] | None = None
    events_target: tuple[Path, str] | None = None

    try:
        if lvl not in VALID_LEVELS:
            raise _err(
                codec.ReasonCode.INVALID_ENUM,
                codec.Stage.PATH,
                None,
                sorted(VALID_LEVELS),
                level,
                None,
            )
        root_path = closure._validate_root(root)
        report_target = _validate_report_output(root_path, report_path)
        events_target = _validate_events_output(root_path, events_log_path)

        norm_receipts: list[str] = []
        if receipt_paths is not None:
            raw_list = [receipt_paths] if isinstance(receipt_paths, (str, Path)) else list(receipt_paths)
            for item in raw_list:
                norm_receipts.append(str(item))

        norm_manifest_arg = str(manifest_path) if manifest_path is not None else None
        norm_scope_arg = str(verification_scope_path) if verification_scope_path is not None else None
        norm_ch7_arg = str(chapter7_slice_report) if chapter7_slice_report is not None else None
        norm_manual_arg = str(manual_signoff_path) if manual_signoff_path is not None else None
        norm_handoff_arg = str(milestone_handoff_path) if milestone_handoff_path is not None else None

        # Load & validate optional milestone handoff (SHA, Chapter 5 readiness freshness, scope_id)
        handoff_doc: dict[str, Any] | None = None
        if norm_handoff_arg is not None:
            handoff_doc, h_path, h_rel = _load_strict_json(root_path, norm_handoff_arg, label="milestone_handoff", allow_logs=True)
            if handoff_doc.get("schema_version") != handoff_mod.HANDOFF_SCHEMA:
                raise _err(
                    codec.ReasonCode.UNKNOWN_SCHEMA,
                    codec.Stage.SCHEMA,
                    h_rel,
                    handoff_mod.HANDOFF_SCHEMA,
                    handoff_doc.get("schema_version"),
                    h_rel,
                )
            h_tid = str(handoff_doc.get("task_id") or "").strip()
            if not h_tid:
                raise _err(
                    codec.ReasonCode.MISSING_REQUIRED_FIELD,
                    codec.Stage.CONTENT,
                    h_rel,
                    "nonempty task_id in milestone handoff",
                    handoff_doc.get("task_id"),
                    h_rel,
                )
            if task_id is not None:
                if type(task_id) is bool:
                    raise _err(codec.ReasonCode.INVALID_TYPE, codec.Stage.PATH, None, "strict positive integer --task-id", task_id, None)
                if str(ch6_gate.parse_strict_task_id(task_id)) != h_tid:
                    raise _err(
                        codec.ReasonCode.MAPPING_MISMATCH,
                        codec.Stage.CONTENT,
                        h_rel,
                        str(task_id),
                        h_tid,
                        h_rel,
                    )
            h_ok, h_reason, _ = handoff_mod.validate_task_handoff(root_path, h_path, h_tid)
            if not h_ok:
                h_code = (
                    codec.ReasonCode.INPUT_STALE
                    if ("stale" in h_reason or "drift" in h_reason)
                    else codec.ReasonCode.CONFLICT
                )
                raise _err(
                    h_code,
                    codec.Stage.CONTENT,
                    h_rel,
                    "valid fresh milestone task handoff",
                    h_reason,
                    h_rel,
                )
            if norm_scope_arg is None and isinstance(handoff_doc.get("b_route_verification_scope"), dict):
                scoped_ref = handoff_doc["b_route_verification_scope"].get("scope_path")
                if isinstance(scoped_ref, str) and scoped_ref.strip():
                    norm_scope_arg = scoped_ref.strip()
            if norm_manifest_arg is None and isinstance(handoff_doc.get("baseline_manifest_path"), str):
                norm_manifest_arg = handoff_doc["baseline_manifest_path"]
        elif isinstance(inline_handoff, dict):
            handoff_doc = inline_handoff
            if handoff_doc.get("schema_version") == handoff_mod.HANDOFF_SCHEMA:
                if norm_scope_arg is None and isinstance(handoff_doc.get("b_route_verification_scope"), dict):
                    scoped_ref = handoff_doc["b_route_verification_scope"].get("scope_path")
                    if isinstance(scoped_ref, str) and scoped_ref.strip():
                        norm_scope_arg = scoped_ref.strip()
                if norm_manifest_arg is None and isinstance(handoff_doc.get("baseline_manifest_path"), str):
                    norm_manifest_arg = handoff_doc["baseline_manifest_path"]

        master_tasks = _load_master_tasks(root_path)
        task_test_refs = _load_task_test_refs(root_path)
        plans, bindings = _load_committed_plans_and_bindings(root_path)

        # Load & revalidate VerificationScope if provided
        scope_doc: dict[str, Any] | None = None
        scope_rel: str | None = None
        if norm_scope_arg is not None:
            scope_doc, scope_rel = _load_and_verify_scope(root_path, norm_scope_arg)
            payload["verification_scope_path"] = scope_rel
            payload["scope_id"] = scope_doc.get("scope_id")
            payload["input_set_digest"] = scope_doc.get("input_set_digest")

        # Cross-check handoff scope_id against loaded VerificationScope
        if isinstance(handoff_doc, dict) and isinstance(handoff_doc.get("b_route_verification_scope"), dict) and scope_doc is not None:
            h_sid = handoff_doc["b_route_verification_scope"].get("scope_id")
            if h_sid and h_sid != scope_doc.get("scope_id"):
                raise _err(
                    codec.ReasonCode.INPUT_STALE,
                    codec.Stage.CONTENT,
                    norm_handoff_arg or scope_rel,
                    scope_doc.get("scope_id"),
                    h_sid,
                    scope_rel,
                )

        # Load & validate MVG manifest if provided
        manifest_doc: dict[str, Any] | None = None
        manifest_rel: str | None = None
        manifest_sha: str | None = None
        if norm_manifest_arg is not None:
            manifest_doc, manifest_rel, manifest_sha = _load_and_verify_manifest(root_path, norm_manifest_arg)
            payload["manifest_path"] = manifest_rel

        manifest_tests: dict[str, dict[str, Any]] = {}
        if isinstance(manifest_doc, dict):
            for t in manifest_doc.get("tests") or []:
                if isinstance(t, dict) and isinstance(t.get("id"), str):
                    manifest_tests[t["id"]] = t

        # Load & cryptographically + raw-report verify all coverage receipts
        loaded_receipts: list[dict[str, Any]] = []
        for r_arg in norm_receipts:
            loaded_receipts.append(
                _load_and_verify_receipt(
                    root_path,
                    r_arg,
                    scope=scope_doc,
                    manifest_tests=manifest_tests,
                )
            )
        payload["receipt_paths"] = [r["path"] for r in loaded_receipts]

        # Enforce zero cross-snapshot splicing across all receipts
        snap_digest, src_rev, ws_dirty = _check_cross_snapshot_consistency(loaded_receipts)
        payload["snapshot_digest"] = snap_digest
        payload["source_revision"] = src_rev
        payload["workspace_dirty"] = ws_dirty

        # Check receipt manifest consistency when both manifest and receipts provided
        if manifest_doc is not None and manifest_sha is not None:
            for r in loaded_receipts:
                rdoc = r["doc"]
                r_msha = rdoc.get("manifest_sha256")
                if rdoc.get("manifest") == manifest_rel:
                    if not isinstance(r_msha, str) or not r_msha.strip():
                        raise _err(
                            codec.ReasonCode.MISSING_REQUIRED_FIELD,
                            codec.Stage.CONTENT,
                            r["path"],
                            manifest_sha,
                            r_msha,
                            r["path"],
                        )
                    if r_msha != manifest_sha:
                        raise _err(
                            codec.ReasonCode.DIGEST_MISMATCH,
                            codec.Stage.CONTENT,
                            r["path"],
                            manifest_sha,
                            r_msha,
                            r["path"],
                        )

        passed_tests, failed_tests, skipped_tests, not_run_blocking = _merge_receipt_tests(loaded_receipts)
        payload["failed_tests"] = failed_tests
        payload["skipped_tests"] = skipped_tests
        any_protocol_fixture = any(r["protocol_fixture_only"] for r in loaded_receipts)
        all_receipts_automated_scope_passed = bool(loaded_receipts) and all(r["automated_scope_passed"] for r in loaded_receipts)
        all_receipts_runtime_verified = bool(loaded_receipts) and all(r["runtime_verified"] for r in loaded_receipts)

        # Load & verify manual signoff if provided
        manual_verified_map, _ = _load_and_verify_manual_signoff(
            root_path,
            norm_manual_arg,
            expected_scope_id=scope_doc.get("scope_id") if scope_doc else None,
            expected_snapshot_digest=snap_digest,
        )
        payload["manual_signoff_verified"] = sorted(manual_verified_map.keys())

        # Dispatch by level
        if lvl == "task":
            _eval_task_level(
                root_path,
                payload,
                task_id=task_id,
                master_tasks=master_tasks,
                task_test_refs=task_test_refs,
                plans=plans,
                bindings=bindings,
                manifest_doc=manifest_doc,
                manifest_tests=manifest_tests,
                scope_doc=scope_doc,
                loaded_receipts=loaded_receipts,
                passed_tests=passed_tests,
                failed_tests=failed_tests,
                skipped_tests=skipped_tests,
                not_run_blocking=not_run_blocking,
                any_protocol_fixture=any_protocol_fixture,
                all_receipts_runtime_verified=all_receipts_runtime_verified,
                manual_verified_map=manual_verified_map,
                chapter7_slice_report=norm_ch7_arg,
                handoff_doc=handoff_doc,
            )
        elif lvl == "flow":
            _eval_flow_level(
                root_path,
                payload,
                flow_id=flow_id,
                master_tasks=master_tasks,
                plans=plans,
                bindings=bindings,
                manifest_doc=manifest_doc,
                manifest_tests=manifest_tests,
                scope_doc=scope_doc,
                loaded_receipts=loaded_receipts,
                passed_tests=passed_tests,
                failed_tests=failed_tests,
                skipped_tests=skipped_tests,
                not_run_blocking=not_run_blocking,
                any_protocol_fixture=any_protocol_fixture,
                all_receipts_runtime_verified=all_receipts_runtime_verified,
                manual_verified_map=manual_verified_map,
                chapter7_slice_report=norm_ch7_arg,
            )
        elif lvl == "milestone":
            _eval_milestone_level(
                root_path,
                payload,
                master_tasks=master_tasks,
                plans=plans,
                bindings=bindings,
                manifest_doc=manifest_doc,
                manifest_rel=manifest_rel,
                manifest_sha=manifest_sha,
                manifest_tests=manifest_tests,
                scope_doc=scope_doc,
                loaded_receipts=loaded_receipts,
                passed_tests=passed_tests,
                failed_tests=failed_tests,
                skipped_tests=skipped_tests,
                not_run_blocking=not_run_blocking,
                any_protocol_fixture=any_protocol_fixture,
                all_receipts_runtime_verified=all_receipts_runtime_verified,
                manual_verified_map=manual_verified_map,
                chapter7_slice_report=norm_ch7_arg,
                handoff_doc=handoff_doc,
            )
        else:
            _eval_non_flow_level(
                root_path,
                payload,
                plans=plans,
                manifest_tests=manifest_tests,
                scope_doc=scope_doc,
                loaded_receipts=loaded_receipts,
                passed_tests=passed_tests,
                failed_tests=failed_tests,
                skipped_tests=skipped_tests,
                not_run_blocking=not_run_blocking,
                any_protocol_fixture=any_protocol_fixture,
                all_receipts_automated_scope_passed=all_receipts_automated_scope_passed,
                all_receipts_runtime_verified=all_receipts_runtime_verified,
                manual_verified_map=manual_verified_map,
            )

        return _finalize_verdict(root_path, payload, report_target, events_target, started)

    except codec.CodecError as err:
        d = err.diagnostic.to_dict()
        payload["ok"] = False
        payload["verdict_status"] = "blocked"
        payload["reason_code"] = d["reason_code"]
        actual = d.get("actual")
        if isinstance(actual, dict) and actual.get("reason") == "cross_snapshot_report_splicing_forbidden":
            payload["reason"] = "cross_snapshot_report_splicing_forbidden"
            payload["cross_snapshot_splicing_detected"] = True
        else:
            payload["reason"] = f"blocked:{d['reason_code']}"
        payload["diagnostics"] = [d]
        payload["flow_completed"] = False
        payload["cumulative_full_mvg_completed"] = False
        payload["milestone_completed"] = False
        payload["runtime_verified"] = False
        return _finalize_verdict(root_path, payload, None, events_target, started)
    except (OSError, ValueError) as exc:
        d = _diag(codec.ReasonCode.READ_ERROR, codec.Stage.DECODE, None, "valid readable inputs", str(exc), None)
        payload["ok"] = False
        payload["verdict_status"] = "blocked"
        payload["reason_code"] = d["reason_code"]
        payload["reason"] = f"io_error:{exc}"
        payload["diagnostics"] = [d]
        return _finalize_verdict(root_path, payload, None, events_target, started)


def _eval_task_level(
    root: Path,
    payload: dict[str, Any],
    *,
    task_id: int | str | None,
    master_tasks: dict[int, dict[str, Any]],
    task_test_refs: dict[int, set[str]],
    plans: dict[str, dict[str, Any]],
    bindings: dict[str, dict[str, Any]],
    manifest_doc: dict[str, Any] | None,
    manifest_tests: dict[str, dict[str, Any]],
    scope_doc: dict[str, Any] | None,
    loaded_receipts: list[dict[str, Any]],
    passed_tests: dict[str, dict[str, Any]],
    failed_tests: list[dict[str, Any]],
    skipped_tests: list[dict[str, Any]],
    not_run_blocking: list[dict[str, Any]],
    any_protocol_fixture: bool,
    all_receipts_runtime_verified: bool,
    manual_verified_map: dict[str, dict[str, Any]],
    chapter7_slice_report: str | None,
    handoff_doc: dict[str, Any] | None,
) -> None:
    if task_id is None or type(task_id) is bool:
        raise _err(
            codec.ReasonCode.INVALID_ARGUMENT,
            codec.Stage.PATH,
            None,
            "strict positive integer --task-id for level=task",
            task_id,
            None,
        )
    tid = ch6_gate.parse_strict_task_id(task_id)
    payload["task_id"] = tid
    payload["verified_scope"] = "task_local"

    if tid not in master_tasks:
        raise _err(
            codec.ReasonCode.UNKNOWN_ENTITY,
            codec.Stage.TARGET,
            f"task:{tid}",
            "existing master task id in .taskmaster/tasks/tasks.json",
            tid,
            ".taskmaster/tasks/tasks.json",
        )
    if scope_doc is None:
        raise _err(
            codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
            codec.Stage.PATH,
            f"task:{tid}",
            "sealed VerificationScope (--verification-scope) for level=task",
            None,
            None,
        )
    if not loaded_receipts:
        raise _err(
            codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
            codec.Stage.PATH,
            f"task:{tid}",
            "at least one sealed coverage-receipt.json (--receipt) for level=task",
            [],
            payload.get("verification_scope_path"),
        )

    # Identify all Flows associated with this Task (bindings, manifest, scope)
    mapped_flows: set[str] = set()
    for binfo in bindings.values():
        bdoc = binfo.get("doc") or {}
        for tm in bdoc.get("task_mappings") or []:
            if isinstance(tm, dict) and tm.get("task_id") == tid:
                mapped_flows.update(str(f) for f in (tm.get("flow_ids") or []) if isinstance(f, str))
    if isinstance(manifest_doc, dict):
        for f in manifest_doc.get("flows") or []:
            if isinstance(f, dict) and tid in (f.get("task_ids") or []):
                mapped_flows.add(str(f["id"]))
    for obl in scope_doc.get("obligations") or []:
        if isinstance(obl, dict) and tid in (obl.get("task_ids") or []):
            mapped_flows.update(str(f) for f in (obl.get("flow_ids") or []) if isinstance(f, str))

    dedicated_owners = _compute_dedicated_integration_owners(manifest_doc, bindings)
    payload["dedicated_integration_owner_task_ids"] = sorted(dedicated_owners)

    # Map each manifest test_id to the set of tasks declaring its path in test_refs
    test_ref_owners: dict[str, set[int]] = {}
    for mt_id, mtest in manifest_tests.items():
        mpath = str(mtest.get("path") or "").strip().replace("\\", "/")
        owners_for_test = {
            t_owner for t_owner, paths in task_test_refs.items()
            if mpath and mpath in paths
        }
        test_ref_owners[mt_id] = owners_for_test

    tid_test_ref_ids = {
        mt_id for mt_id, owners_set in test_ref_owners.items() if tid in owners_set
    }

    # Collect handoff tests explicitly bound to tid
    tid_handoff_test_ids: set[str] = set()
    if isinstance(manifest_doc, dict):
        for mf in manifest_doc.get("flows") or []:
            if not isinstance(mf, dict):
                continue
            for edge in mf.get("handoffs") or []:
                if not isinstance(edge, dict):
                    continue
                if tid in {edge.get("producer_task"), edge.get("consumer_task"), edge.get("owner_task")}:
                    for ht in edge.get("test_ids") or []:
                        if isinstance(ht, str) and ht.strip():
                            ht_owners = test_ref_owners.get(ht, set())
                            # Include handoff test if owned by tid OR not exclusively owned by a different sibling task
                            if not ht_owners or tid in ht_owners or tid in dedicated_owners:
                                tid_handoff_test_ids.add(ht)

    # Collect binding obligation/impl IDs explicitly assigned to tid
    tid_assigned_oids: set[str] = set()
    for binfo in bindings.values():
        bdoc = binfo.get("doc") or {}
        pid = str(bdoc.get("plan_id") or "")
        for tm in bdoc.get("task_mappings") or []:
            if isinstance(tm, dict) and tm.get("task_id") == tid:
                for oid_ref in tm.get("obligation_ids") or []:
                    tid_assigned_oids.add(f"binding_obligation:{pid}:{oid_ref}")
                    tid_assigned_oids.add(str(oid_ref))
        for impl_obj in bdoc.get("implementation_objects") or []:
            if isinstance(impl_obj, dict) and tid in (impl_obj.get("responsible_task_ids") or []):
                if impl_obj.get("id"):
                    tid_assigned_oids.add(f"implementation_object:{pid}:{impl_obj['id']}")
        for bobl in bdoc.get("obligations") or []:
            if isinstance(bobl, dict) and tid in (bobl.get("task_ids") or []):
                if bobl.get("id"):
                    tid_assigned_oids.add(f"binding_obligation:{pid}:{bobl['id']}")
                    tid_assigned_oids.add(str(bobl["id"]))
                for bt in bobl.get("test_ids") or []:
                    if isinstance(bt, str) and bt.strip():
                        tid_assigned_oids.add(f"test:{bt}")

    local_missing: list[dict[str, Any]] = []
    local_tier_violations: list[dict[str, Any]] = []
    local_pending_manual: list[str] = []
    evaluated_local_count = 0
    checked_test_ids: set[str] = set()
    task_requires_runtime = False

    # Map ALL of tid's own obligations from VerificationScope (never skip multi-task shared obligations!)
    for obl in scope_doc.get("obligations") or []:
        if not isinstance(obl, dict):
            continue
        if obl.get("tier") not in vs.CURRENT_TIERS:
            continue
        oid = str(obl.get("obligation_id") or "")
        obl_tids = {t for t in (obl.get("task_ids") or []) if type(t) is int}
        obl_test_ids = [str(t) for t in (obl.get("test_ids") or []) if isinstance(t, str) and t.strip()]
        is_manual = obl.get("evidence_level") == "manual" or obl.get("execution_kind") in {"manual", "manual_check"}

        is_sole_task = obl_tids == {tid}
        is_assigned = oid in tid_assigned_oids
        if is_manual:
            if is_sole_task or is_assigned:
                evaluated_local_count += 1
                if oid and oid not in manual_verified_map:
                    local_pending_manual.append(oid)
            continue

        include_obl = False
        if is_sole_task or is_assigned:
            include_obl = True
        elif tid in obl_tids:
            if obl_test_ids:
                # Include if ANY test belongs to tid's test_refs, OR is a shared test not exclusively in another sibling's test_refs
                for mt_id in obl_test_ids:
                    owners_set = test_ref_owners.get(mt_id, set())
                    if tid in owners_set or not owners_set or mt_id in tid_handoff_test_ids:
                        include_obl = True
                        break
            else:
                # Pending/unimplemented current_new or binding obligation mentioning tid
                include_obl = True

        if not include_obl:
            continue

        evaluated_local_count += 1
        checked_test_ids.update(obl_test_ids)
        if any((manifest_tests.get(mt_id) or {}).get("kind") in {"dotnet", "gdunit"} for mt_id in obl_test_ids):
            task_requires_runtime = True
        elif obl.get("evidence_level") in {"engine-input", "scene-method", "domain-xunit", "domain-integration", "godot-gdunit"}:
            task_requires_runtime = True

        sat, miss, tv = _evaluate_obligation_satisfaction(obl, passed_tests, failed_tests, manifest_tests)
        if not sat:
            local_missing.extend(miss)
        local_tier_violations.extend(tv)

    # Also verify tid's direct test_refs and handoff tests not already checked via scope obligations
    direct_local_tests = (tid_test_ref_ids | tid_handoff_test_ids) - checked_test_ids
    for mt_id in sorted(direct_local_tests):
        evaluated_local_count += 1
        mtest = manifest_tests.get(mt_id) or {}
        if mtest.get("kind") in {"dotnet", "gdunit"}:
            task_requires_runtime = True
        entry = passed_tests.get(mt_id)
        if entry is None:
            local_missing.append({
                "obligation_id": f"task:{tid}:test:{mt_id}",
                "test_id": mt_id,
                "reason": "task_local_test_not_executed_or_failed",
                "task_ids": [tid],
            })
            continue
        req_tier = _normalize_required_tier(str(mtest.get("kind") or ""), mtest.get("evidence_level"))
        tier_ok, tier_reason = _tier_matches_strict(req_tier, entry)
        if not tier_ok:
            local_tier_violations.append({
                "obligation_id": f"task:{tid}:test:{mt_id}",
                "test_id": mt_id,
                "required_tier": req_tier,
                "actual_tier": _normalize_required_tier(str(entry.get("kind") or ""), entry.get("evidence_level")),
                "reason": tier_reason,
            })

    # Verify handoff_doc planned_tests, required_regressions, and manual_obligations for this task
    if isinstance(handoff_doc, dict):
        for ht_key in ("required_regressions", "planned_tests"):
            for req_t in handoff_doc.get(ht_key) or []:
                rt = str(req_t)
                if not rt.strip():
                    continue
                evaluated_local_count += 1
                if rt not in passed_tests:
                    local_missing.append({
                        "obligation_id": f"handoff:{tid}:{ht_key}:{rt}",
                        "test_id": rt,
                        "reason": f"handoff_{ht_key}_not_verified",
                        "task_ids": [tid],
                    })
        for hm in handoff_doc.get("manual_obligations") or []:
            hmid = str(hm).strip()
            if hmid:
                evaluated_local_count += 1
                if hmid not in manual_verified_map and hmid not in local_pending_manual:
                    local_pending_manual.append(hmid)

    # NEVER fall back to arbitrary unrelated passed_tests! Require at least one mapped local obligation.
    if evaluated_local_count == 0:
        local_missing.append({
            "obligation_id": f"task:{tid}:local",
            "reason": "no_mapped_task_local_obligations_in_scope",
            "task_ids": [tid],
        })

    if skipped_tests:
        local_missing.append({"reason": "skipped_tests_present", "skipped_tests": skipped_tests})

    local_automated_ok = not local_missing and not local_tier_violations and not skipped_tests
    if any_protocol_fixture or (task_requires_runtime and not all_receipts_runtime_verified):
        payload["protocol_fixture_satisfied_only"] = local_automated_ok
        task_local_ok = False
    else:
        task_local_ok = local_automated_ok and not local_pending_manual

    payload["task_local_satisfied"] = task_local_ok
    payload["manual_pending"] = bool(local_pending_manual)
    payload["evidence_tier_violations"] = local_tier_violations

    # Now inspect ALL mapped parent Flows to prove that single-Task local pass NEVER implies Flow completion
    missing_tasks: set[int] = set()
    missing_tests: set[str] = set()
    missing_impls: set[str] = set()
    missing_ch7: set[str] = set()
    pending_manual: list[str] = list(local_pending_manual)
    flow_verdicts: dict[str, dict[str, Any]] = {}

    for fid in sorted(mapped_flows):
        f_missing_tasks: set[int] = set()
        f_missing_tests: set[str] = set()
        f_missing_impls: set[str] = set()
        f_missing_ch7: set[str] = set()
        f_pending_manual: list[str] = []

        flow_dedicated = _compute_dedicated_integration_owners(manifest_doc, bindings, flow_id=fid)
        flow_tids: set[int] = set()
        if isinstance(manifest_doc, dict):
            for f in manifest_doc.get("flows") or []:
                if isinstance(f, dict) and f.get("id") == fid:
                    flow_tids.update(t for t in (f.get("task_ids") or []) if type(t) is int)
        for binfo in bindings.values():
            for tm in (binfo.get("doc") or {}).get("task_mappings") or []:
                if isinstance(tm, dict) and fid in (tm.get("flow_ids") or []) and type(tm.get("task_id")) is int:
                    flow_tids.add(tm["task_id"])
        for ftid in sorted(flow_tids):
            if ftid in flow_dedicated:
                continue
            status = str((master_tasks.get(ftid) or {}).get("status") or "").strip().lower()
            if status != "done":
                f_missing_tasks.add(ftid)

        for obl in scope_doc.get("obligations") or []:
            if not isinstance(obl, dict) or fid not in (obl.get("flow_ids") or []):
                continue
            if obl.get("tier") not in vs.CURRENT_TIERS:
                continue
            if obl.get("evidence_level") == "manual" or obl.get("execution_kind") in {"manual", "manual_check"}:
                mid = str(obl.get("obligation_id") or "")
                if mid and mid not in manual_verified_map:
                    f_pending_manual.append(mid)
                continue
            sat, miss, tv = _evaluate_obligation_satisfaction(obl, passed_tests, failed_tests, manifest_tests)
            if not sat:
                for m in miss:
                    if m.get("reason") == "obligation_unimplemented_or_blocked":
                        f_missing_impls.add(str(obl.get("obligation_id") or ""))
                        for mt in m.get("missing_targets") or []:
                            f_missing_impls.add(str(mt))
                    for mtid in m.get("test_ids") or []:
                        f_missing_tests.add(str(mtid))
                    if m.get("test_id"):
                        f_missing_tests.add(str(m["test_id"]))
            if tv:
                for v in tv:
                    f_missing_tests.add(str(v.get("test_id") or obl.get("obligation_id")))

        if isinstance(manifest_doc, dict):
            for f in manifest_doc.get("flows") or []:
                if isinstance(f, dict) and f.get("id") == fid:
                    for test_id in f.get("test_ids") or []:
                        if test_id not in passed_tests:
                            f_missing_tests.add(str(test_id))

        _, _, f_ch7_missing, f_ch7_manual = _verify_chapter7_for_flow(
            root,
            flow_id=fid,
            scope_doc=scope_doc,
            chapter7_slice_report=chapter7_slice_report,
            plans=plans,
            bindings=bindings,
            manifest_doc=manifest_doc,
            strict_report_flow_match=False,
        )
        f_missing_ch7.update(f_ch7_missing)
        for mid in f_ch7_manual:
            if mid not in manual_verified_map and mid not in f_pending_manual:
                f_pending_manual.append(mid)

        for mo in _collect_manual_obligations_for_scope(scope_doc, loaded_receipts, flow_id=fid):
            if mo["manual_id"] not in manual_verified_map and mo["manual_id"] not in f_pending_manual:
                f_pending_manual.append(mo["manual_id"])

        f_status = "pending" if (f_missing_tasks or f_missing_impls or f_pending_manual or f_missing_ch7) else (
            "blocked" if f_missing_tests else "ready_for_flow_verdict"
        )
        # Task-level check NEVER declares a Flow completed!
        flow_verdicts[fid] = {
            "flow_id": fid,
            "flow_completed": False,
            "flow_status": "pending" if f_status == "ready_for_flow_verdict" else f_status,
            "missing_tasks": sorted(f_missing_tasks),
            "missing_tests": sorted(f_missing_tests),
            "missing_implementations": sorted(f_missing_impls),
            "missing_chapter7_slices": sorted(f_missing_ch7),
            "pending_manual_obligations": sorted(set(f_pending_manual)),
        }
        missing_tasks |= f_missing_tasks
        missing_tests |= f_missing_tests
        missing_impls |= f_missing_impls
        missing_ch7 |= f_missing_ch7
        pending_manual.extend(f_pending_manual)

    payload["blocking_participant_task_ids"] = sorted(missing_tasks)
    payload["missing_flow_obligations"] = {
        "missing_tasks": sorted(missing_tasks),
        "missing_tests": sorted(missing_tests),
        "missing_implementations": sorted(missing_impls),
        "missing_chapter7_slices": sorted(missing_ch7),
        "pending_manual_obligations": sorted(set(pending_manual)),
    }
    payload["flow_verdicts"] = flow_verdicts
    payload["flow_completed"] = False
    payload["cumulative_full_mvg_completed"] = False
    payload["milestone_completed"] = False

    if mapped_flows:
        any_missing_impl = bool(missing_tasks or missing_impls or missing_ch7 or pending_manual)
        payload["flow_status"] = "pending" if any_missing_impl else "blocked"
    else:
        payload["flow_status"] = "not_applicable"

    if any_protocol_fixture or (task_requires_runtime and not all_receipts_runtime_verified):
        payload["ok"] = False
        payload["runtime_verified"] = False
        payload["verdict_status"] = "blocked"
        payload["reason_code"] = codec.ReasonCode.CONFLICT.value
        payload["reason"] = "protocol_fixture_cannot_satisfy_task_local_completion"
        payload["diagnostics"] = [
            _diag(
                codec.ReasonCode.CONFLICT,
                codec.Stage.CONTENT,
                f"task:{tid}",
                "real_runtime verified receipt (protocol_fixture_only=false)",
                {"protocol_fixture_only": any_protocol_fixture, "receipts_runtime_verified": all_receipts_runtime_verified},
                loaded_receipts[0]["path"],
            )
        ]
        return

    if task_local_ok:
        payload["ok"] = True
        payload["runtime_verified"] = bool(task_requires_runtime and all_receipts_runtime_verified)
        payload["verdict_status"] = "task_local_passed"
        payload["reason_code"] = codec.ReasonCode.OK.value
        payload["reason"] = "task_local_obligations_satisfied_flow_remains_unclaimed"
    else:
        payload["ok"] = False
        payload["runtime_verified"] = False
        payload["verdict_status"] = "manual_pending" if (local_automated_ok and local_pending_manual) else "blocked"
        rc = codec.ReasonCode.CONFLICT if local_tier_violations else codec.ReasonCode.PENDING
        payload["reason_code"] = rc.value
        payload["reason"] = (
            "task_local_manual_obligations_pending"
            if (local_automated_ok and local_pending_manual)
            else "task_local_obligations_unsatisfied"
        )
        payload["diagnostics"] = [
            _diag(
                rc,
                codec.Stage.CONTENT,
                f"task:{tid}",
                "all task-local current_new, existing_required, and task-bound manual obligations verified",
                {"missing": local_missing, "tier_violations": local_tier_violations, "pending_manual": local_pending_manual},
                payload.get("verification_scope_path"),
            )
        ]


def _eval_flow_level(
    root: Path,
    payload: dict[str, Any],
    *,
    flow_id: str | None,
    master_tasks: dict[int, dict[str, Any]],
    plans: dict[str, dict[str, Any]],
    bindings: dict[str, dict[str, Any]],
    manifest_doc: dict[str, Any] | None,
    manifest_tests: dict[str, dict[str, Any]],
    scope_doc: dict[str, Any] | None,
    loaded_receipts: list[dict[str, Any]],
    passed_tests: dict[str, dict[str, Any]],
    failed_tests: list[dict[str, Any]],
    skipped_tests: list[dict[str, Any]],
    not_run_blocking: list[dict[str, Any]],
    any_protocol_fixture: bool,
    all_receipts_runtime_verified: bool,
    manual_verified_map: dict[str, dict[str, Any]],
    chapter7_slice_report: str | None,
) -> None:
    fid = str(flow_id or "").strip()
    if not fid:
        raise _err(codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.PATH, None, "nonempty --flow-id for level=flow", flow_id, None)
    payload["flow_id"] = fid
    payload["verified_scope"] = "single_flow"

    if scope_doc is None:
        raise _err(
            codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
            codec.Stage.PATH,
            f"flow:{fid}",
            "sealed VerificationScope (--verification-scope) for level=flow",
            None,
            None,
        )
    if not loaded_receipts:
        raise _err(
            codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
            codec.Stage.PATH,
            f"flow:{fid}",
            "at least one sealed coverage-receipt.json (--receipt) for level=flow",
            [],
            payload.get("verification_scope_path"),
        )

    # Check Flow classification in VerificationScope
    flow_class_map = {
        str(fc.get("flow_id")): fc
        for fc in (scope_doc.get("flow_classifications") or [])
        if isinstance(fc, dict) and fc.get("flow_id")
    }
    fc = flow_class_map.get(fid)
    manifest_flow = None
    if isinstance(manifest_doc, dict):
        for mf in manifest_doc.get("flows") or []:
            if isinstance(mf, dict) and mf.get("id") == fid:
                manifest_flow = mf
                break
    if fc is None and manifest_flow is None:
        raise _err(
            codec.ReasonCode.UNKNOWN_ENTITY,
            codec.Stage.TARGET,
            f"flow:{fid}",
            "known Flow ID in VerificationScope or MVG manifest",
            fid,
            payload.get("verification_scope_path"),
        )
    if fc is not None and _is_flow_out_of_scope_future(fc):
        payload["flow_status"] = "out_of_scope_future"
        payload["flow_completed"] = False
        payload["out_of_scope_future_tracked"] = [fid]
        payload["ok"] = False
        payload["verdict_status"] = "out_of_scope_future"
        payload["reason_code"] = codec.ReasonCode.PENDING.value
        payload["reason"] = "flow_is_out_of_scope_future"
        payload["diagnostics"] = [
            _diag(codec.ReasonCode.PENDING, codec.Stage.CONTENT, f"flow:{fid}", "in-scope flow", "out_of_scope_future", payload.get("verification_scope_path"))
        ]
        return

    # Dedicated integration owner exemption vs participant task status
    dedicated_owners = _compute_dedicated_integration_owners(manifest_doc, bindings, flow_id=fid)
    payload["dedicated_integration_owner_task_ids"] = sorted(dedicated_owners)

    flow_task_ids: set[int] = set()
    if manifest_flow is not None:
        flow_task_ids.update(t for t in (manifest_flow.get("task_ids") or []) if type(t) is int)
    for binfo in bindings.values():
        for tm in (binfo.get("doc") or {}).get("task_mappings") or []:
            if isinstance(tm, dict) and fid in (tm.get("flow_ids") or []) and type(tm.get("task_id")) is int:
                flow_task_ids.add(tm["task_id"])
    for obl in scope_doc.get("obligations") or []:
        if isinstance(obl, dict) and fid in (obl.get("flow_ids") or []) and obl.get("tier") in vs.CURRENT_TIERS:
            flow_task_ids.update(t for t in (obl.get("task_ids") or []) if type(t) is int)

    blocking_participants = sorted(
        tid for tid in flow_task_ids
        if tid not in dedicated_owners
        and str((master_tasks.get(tid) or {}).get("status") or "").strip().lower() != "done"
    )
    payload["blocking_participant_task_ids"] = blocking_participants

    # Evaluate all current-tier obligations for this Flow
    missing_tests: set[str] = set()
    missing_impls: set[str] = set()
    tier_violations: list[dict[str, Any]] = []
    flow_obligations = [
        o for o in (scope_doc.get("obligations") or [])
        if isinstance(o, dict) and fid in (o.get("flow_ids") or []) and o.get("tier") in vs.CURRENT_TIERS
    ]
    for obl in flow_obligations:
        if obl.get("evidence_level") == "manual" or obl.get("execution_kind") in {"manual", "manual_check"}:
            continue
        sat, miss, tv = _evaluate_obligation_satisfaction(obl, passed_tests, failed_tests, manifest_tests)
        if not sat:
            for m in miss:
                if m.get("reason") == "obligation_unimplemented_or_blocked":
                    missing_impls.add(str(obl.get("obligation_id") or ""))
                    for mt in m.get("missing_targets") or []:
                        missing_impls.add(str(mt))
                if m.get("test_id"):
                    missing_tests.add(str(m["test_id"]))
                for mtid in m.get("test_ids") or []:
                    missing_tests.add(str(mtid))
        tier_violations.extend(tv)

    # Also enforce all manifest test_ids for this Flow with strict tier check
    if manifest_flow is not None:
        for test_id in manifest_flow.get("test_ids") or []:
            entry = passed_tests.get(test_id)
            if entry is None:
                missing_tests.add(str(test_id))
                continue
            mtest = manifest_tests.get(test_id) or {}
            req_tier = _normalize_required_tier(str(mtest.get("kind") or ""), mtest.get("evidence_level"))
            tier_ok, tier_reason = _tier_matches_strict(req_tier, entry)
            if not tier_ok:
                tier_violations.append({
                    "obligation_id": f"manifest:{fid}:{test_id}",
                    "test_id": test_id,
                    "required_tier": req_tier,
                    "actual_tier": _normalize_required_tier(str(entry.get("kind") or ""), entry.get("evidence_level")),
                    "reason": tier_reason,
                })

    # Check Chapter 7 UI closure (verified report or live slice evaluation; merges manual_items)
    _, ch7_summary, missing_ch7, ch7_manual_items = _verify_chapter7_for_flow(
        root,
        flow_id=fid,
        scope_doc=scope_doc,
        chapter7_slice_report=chapter7_slice_report,
        plans=plans,
        bindings=bindings,
        manifest_doc=manifest_doc,
        strict_report_flow_match=True,
    )
    if ch7_summary is not None:
        payload["chapter7_slice"] = ch7_summary

    # Check manual obligations for this Flow
    manual_obs = _collect_manual_obligations_for_scope(scope_doc, loaded_receipts, flow_id=fid)
    required_manual_ids = sorted({m["manual_id"] for m in manual_obs} | set(ch7_manual_items))
    pending_manual_ids = [mid for mid in required_manual_ids if mid not in manual_verified_map]

    # Check blocking not_run items belonging to this Flow
    flow_test_id_set = set(manifest_flow.get("test_ids") or []) if manifest_flow else set()
    for obl in flow_obligations:
        flow_test_id_set.update(obl.get("test_ids") or [])
    flow_not_run = [nr for nr in not_run_blocking if str(nr.get("id") or "") in flow_test_id_set]
    for nr in flow_not_run:
        missing_tests.add(str(nr.get("id") or ""))

    payload["evidence_tier_violations"] = tier_violations
    payload["missing_flow_obligations"] = {
        "missing_tasks": blocking_participants,
        "missing_tests": sorted(missing_tests),
        "missing_implementations": sorted(missing_impls),
        "missing_chapter7_slices": missing_ch7,
        "pending_manual_obligations": pending_manual_ids,
    }

    automated_checks_ok = (
        not blocking_participants
        and not missing_tests
        and not missing_impls
        and not missing_ch7
        and not tier_violations
        and not skipped_tests
        and not any(f.get("test_id") in flow_test_id_set for f in failed_tests)
    )

    if any_protocol_fixture or not all_receipts_runtime_verified:
        payload["protocol_fixture_satisfied_only"] = automated_checks_ok
        payload["automated_flow_passed"] = False
        payload["runtime_verified"] = False
        payload["flow_completed"] = False
        payload["flow_status"] = "protocol_fixture_only" if automated_checks_ok else "blocked"
        payload["ok"] = False
        payload["verdict_status"] = "blocked"
        payload["reason_code"] = codec.ReasonCode.CONFLICT.value
        payload["reason"] = "protocol_fixture_cannot_satisfy_real_runtime_flow_completion"
        payload["diagnostics"] = [
            _diag(
                codec.ReasonCode.CONFLICT,
                codec.Stage.CONTENT,
                f"flow:{fid}",
                "real_runtime verified receipt (protocol_fixture_only=false)",
                {"protocol_fixture_only": any_protocol_fixture, "receipts_runtime_verified": all_receipts_runtime_verified},
                loaded_receipts[0]["path"],
            )
        ]
        return

    if not automated_checks_ok:
        payload["automated_flow_passed"] = False
        payload["flow_completed"] = False
        payload["flow_status"] = "blocked" if (tier_violations or failed_tests or skipped_tests) else "pending"
        payload["ok"] = False
        payload["verdict_status"] = "blocked"
        rc = codec.ReasonCode.CONFLICT if (tier_violations or failed_tests or skipped_tests) else codec.ReasonCode.PENDING
        payload["reason_code"] = rc.value
        payload["reason"] = "evidence_tier_substitution_forbidden" if tier_violations else "flow_obligations_incomplete"
        payload["diagnostics"] = [
            _diag(
                rc,
                codec.Stage.CONTENT,
                f"flow:{fid}",
                "all required flow obligations, participant tasks, Chapter 7 slice, and exact evidence tiers satisfied",
                {
                    "missing_flow_obligations": payload["missing_flow_obligations"],
                    "evidence_tier_violations": tier_violations,
                },
                payload.get("verification_scope_path"),
            )
        ]
        return

    # Automated Flow checks passed with real runtime! Now check manual obligations.
    payload["automated_flow_passed"] = True
    payload["runtime_verified"] = True
    if pending_manual_ids:
        payload["manual_pending"] = True
        payload["flow_completed"] = False
        payload["flow_status"] = "manual_pending"
        payload["ok"] = False
        payload["verdict_status"] = "manual_pending"
        payload["reason_code"] = codec.ReasonCode.PENDING.value
        payload["reason"] = "manual_obligations_pending_human_signoff"
        payload["diagnostics"] = [
            _diag(
                codec.ReasonCode.PENDING,
                codec.Stage.CONTENT,
                f"flow:{fid}",
                "signed manual acceptance covering all applicable manual_obligations",
                {"pending_manual_obligations": pending_manual_ids},
                payload.get("verification_scope_path"),
            )
        ]
        return

    payload["manual_pending"] = False
    payload["flow_completed"] = True
    payload["flow_status"] = "completed"
    payload["ok"] = True
    payload["verdict_status"] = "flow_completed"
    payload["reason_code"] = codec.ReasonCode.OK.value
    payload["reason"] = "target_flow_completed_with_verified_runtime_and_manual_evidence"
    payload["flow_verdicts"][fid] = {
        "flow_id": fid,
        "flow_completed": True,
        "flow_status": "completed",
        "dedicated_integration_owner_task_ids": sorted(dedicated_owners),
    }


def _eval_milestone_level(
    root: Path,
    payload: dict[str, Any],
    *,
    master_tasks: dict[int, dict[str, Any]],
    plans: dict[str, dict[str, Any]],
    bindings: dict[str, dict[str, Any]],
    manifest_doc: dict[str, Any] | None,
    manifest_rel: str | None,
    manifest_sha: str | None,
    manifest_tests: dict[str, dict[str, Any]],
    scope_doc: dict[str, Any] | None,
    loaded_receipts: list[dict[str, Any]],
    passed_tests: dict[str, dict[str, Any]],
    failed_tests: list[dict[str, Any]],
    skipped_tests: list[dict[str, Any]],
    not_run_blocking: list[dict[str, Any]],
    any_protocol_fixture: bool,
    all_receipts_runtime_verified: bool,
    manual_verified_map: dict[str, dict[str, Any]],
    chapter7_slice_report: str | None,
    handoff_doc: dict[str, Any] | None,
) -> None:
    if manifest_doc is None or not manifest_rel or not manifest_sha:
        raise _err(
            codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
            codec.Stage.PATH,
            manifest_rel,
            "cumulative full MVG manifest (--manifest) with valid SHA-256 for level=milestone",
            None,
            manifest_rel,
        )
    if scope_doc is None:
        raise _err(
            codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
            codec.Stage.PATH,
            manifest_rel,
            "sealed VerificationScope (--verification-scope) for level=milestone",
            None,
            manifest_rel,
        )
    if not loaded_receipts:
        raise _err(
            codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
            codec.Stage.PATH,
            manifest_rel,
            "sealed coverage-receipt.json (--receipt) for level=milestone",
            [],
            manifest_rel,
        )

    coverage = manifest_doc.get("coverage") if isinstance(manifest_doc.get("coverage"), dict) else {}
    cov_mode = str(coverage.get("mode") or "partial").strip().lower()

    # Dedicated integration owners across the entire cumulative manifest + bindings
    dedicated_owners = _compute_dedicated_integration_owners(manifest_doc, bindings)
    payload["dedicated_integration_owner_task_ids"] = sorted(dedicated_owners)

    # Check out_of_scope_future flows vs in-scope flows (AC-4)
    out_of_scope_flows: list[dict[str, Any]] = []
    out_of_scope_flow_ids: set[str] = set()
    in_scope_flow_ids: set[str] = set()
    existing_required_flow_ids: set[str] = set()
    current_new_flow_ids: set[str] = set()
    for fc in scope_doc.get("flow_classifications") or []:
        if not isinstance(fc, dict) or not fc.get("flow_id"):
            continue
        fid = str(fc["flow_id"])
        tiers = set(fc.get("tiers") or [])
        if _is_flow_out_of_scope_future(fc):
            out_of_scope_flow_ids.add(fid)
            follow_ups = sorted({
                resp
                for o in (scope_doc.get("obligations") or [])
                if isinstance(o, dict) and fid in (o.get("flow_ids") or []) and o.get("tier") == "out_of_scope_future"
                for resp in (o.get("follow_up_responsibilities") or [])
            })
            out_of_scope_flows.append({
                "flow_id": fid,
                "completed": False,
                "status": "out_of_scope_future",
                "follow_up_responsibilities": follow_ups,
            })
            payload["flow_verdicts"][fid] = {
                "flow_id": fid,
                "flow_completed": False,
                "flow_status": "out_of_scope_future",
                "follow_up_responsibilities": follow_ups,
            }
        else:
            in_scope_flow_ids.add(fid)
            if "existing_required" in tiers or fc.get("has_existing_required"):
                existing_required_flow_ids.add(fid)
            if "current_new" in tiers or fc.get("has_current_new"):
                current_new_flow_ids.add(fid)

    payload["out_of_scope_future_tracked"] = out_of_scope_flows
    payload["forced_premature_future_implementation"] = False

    # Check manifest mode == "full" BEFORE authority membership so pilot/critical report true scope
    if cov_mode != "full":
        payload["verified_scope"] = cov_mode if cov_mode in {"pilot", "critical"} else "partial"
        payload["cumulative_full_mvg_completed"] = False
        payload["milestone_completed"] = False
        payload["ok"] = False
        payload["verdict_status"] = "partial_scope_only"
        payload["reason_code"] = codec.ReasonCode.CONFLICT.value
        payload["reason"] = f"partial_or_non_full_manifest_cannot_claim_cumulative_full_mvg:{cov_mode}"
        payload["diagnostics"] = [
            _diag(
                codec.ReasonCode.CONFLICT,
                codec.Stage.CONTENT,
                manifest_rel,
                "coverage.mode == 'full'",
                cov_mode,
                manifest_rel,
            )
        ]
        return

    # On a full manifest, verified_scope stays "partial" until ALL obligations/Ch7/manual pass!
    payload["verified_scope"] = "partial"

    # Verify (manifest_rel, manifest_sha) belongs to VerificationScope.authority_refs
    auth_refs = scope_doc.get("authority_refs") if isinstance(scope_doc.get("authority_refs"), dict) else {}
    scope_manifest_pairs = {
        (str(r.get("path") or ""), str(r.get("manifest_sha256") or ""))
        for key in ("manifest_refs", "cumulative_baseline_refs")
        for r in (auth_refs.get(key) or [])
        if isinstance(r, dict)
    }
    if (manifest_rel, manifest_sha) not in scope_manifest_pairs:
        raise _err(
            codec.ReasonCode.CONFLICT,
            codec.Stage.CONTENT,
            manifest_rel,
            {"manifest_path": manifest_rel, "manifest_sha256": manifest_sha, "in_scope_authority_refs": True},
            sorted(scope_manifest_pairs),
            payload.get("verification_scope_path"),
        )

    # Check clean committed snapshot matching HEAD (fail closed if git fails!)
    if payload["workspace_dirty"]:
        payload["cumulative_full_mvg_completed"] = False
        payload["milestone_completed"] = False
        payload["ok"] = False
        payload["verdict_status"] = "blocked"
        payload["reason_code"] = codec.ReasonCode.CONFLICT.value
        payload["reason"] = "workspace_dirty_cannot_claim_formal_cumulative_full_mvg"
        payload["diagnostics"] = [
            _diag(
                codec.ReasonCode.CONFLICT,
                codec.Stage.CONTENT,
                loaded_receipts[0]["path"],
                {"workspace_dirty": False},
                {"workspace_dirty": True},
                loaded_receipts[0]["path"],
            )
        ]
        return

    git_head, git_dirty = _git_head_and_dirty(root)
    if payload["source_revision"] != git_head:
        raise _err(
            codec.ReasonCode.REVISION_MISMATCH,
            codec.Stage.CONTENT,
            loaded_receipts[0]["path"],
            git_head,
            payload["source_revision"],
            loaded_receipts[0]["path"],
        )
    if git_dirty:
        raise _err(
            codec.ReasonCode.CONFLICT,
            codec.Stage.CONTENT,
            manifest_rel,
            {"workspace_dirty": False},
            {"workspace_dirty": True, "reason": "live_workspace_dirty"},
            manifest_rel,
        )

    # Check blocking participant tasks in cumulative manifest + coverage.blocking_task_ids (modulo dedicated_owners)
    manifest_task_ids = sorted({
        tid
        for f in (manifest_doc.get("flows") or [])
        if isinstance(f, dict)
        for tid in (f.get("task_ids") or [])
        if type(tid) is int
    })
    declared_blockers = {
        tid for tid in (coverage.get("blocking_task_ids") or [])
        if type(tid) is int and tid not in dedicated_owners
    }
    blocking_participants = sorted(
        {
            tid for tid in manifest_task_ids
            if tid not in dedicated_owners
            and str((master_tasks.get(tid) or {}).get("status") or "").strip().lower() != "done"
        }
        | declared_blockers
    )
    payload["blocking_participant_task_ids"] = blocking_participants

    # Check every current_tier obligation in VerificationScope AND every flow/test/handoff in cumulative manifest
    missing_tests: set[str] = set()
    missing_impls: set[str] = set()
    tier_violations: list[dict[str, Any]] = []
    failed_existing_flows: set[str] = set()
    failed_current_flows: set[str] = set()

    # Enforce every test in cumulative full manifest has state == "implemented"
    for mtest in manifest_doc.get("tests") or []:
        if not isinstance(mtest, dict):
            continue
        mt_id = str(mtest.get("id") or "")
        if str(mtest.get("state") or "").strip().lower() != "implemented":
            missing_impls.add(f"planned_manifest_test:{mt_id}")
            missing_tests.add(mt_id)

    for obl in scope_doc.get("obligations") or []:
        if not isinstance(obl, dict):
            continue
        tier = str(obl.get("tier") or "")
        if tier not in vs.CURRENT_TIERS:
            continue
        if obl.get("evidence_level") == "manual" or obl.get("execution_kind") in {"manual", "manual_check"}:
            continue
        sat, miss, tv = _evaluate_obligation_satisfaction(obl, passed_tests, failed_tests, manifest_tests)
        if not sat or tv:
            for fid in obl.get("flow_ids") or []:
                if tier == "existing_required":
                    failed_existing_flows.add(str(fid))
                else:
                    failed_current_flows.add(str(fid))
            for m in miss:
                if m.get("reason") == "obligation_unimplemented_or_blocked":
                    missing_impls.add(str(obl.get("obligation_id") or ""))
                    for mt in m.get("missing_targets") or []:
                        missing_impls.add(str(mt))
                if m.get("test_id"):
                    missing_tests.add(str(m["test_id"]))
                for mtid in m.get("test_ids") or []:
                    missing_tests.add(str(mtid))
            tier_violations.extend(tv)

    # Verify committed in-scope Flows are NOT omitted from cumulative manifest
    manifest_flow_ids = {
        str(mf.get("id")) for mf in (manifest_doc.get("flows") or [])
        if isinstance(mf, dict) and mf.get("id")
    }
    committed_plan_flow_ids = {
        str(pf.get("id"))
        for pinfo in plans.values()
        for pf in (((pinfo.get("doc") or {}).get("definitions") or {}).get("flows") or [])
        if isinstance(pf, dict) and pf.get("id")
    }
    omitted_in_scope_flows = sorted(
        (in_scope_flow_ids | (committed_plan_flow_ids - out_of_scope_flow_ids)) - manifest_flow_ids
    )
    for ofid in omitted_in_scope_flows:
        missing_impls.add(f"manifest_omitted_flow:{ofid}")
        if ofid in existing_required_flow_ids:
            failed_existing_flows.add(ofid)
        else:
            failed_current_flows.add(ofid)

    # Enforce Chapter 7 UI closure for ALL in-scope UI-applicable Flows EVEN WHEN --chapter7-slice-report is omitted!
    missing_ch7: list[str] = []
    ch7_manual_by_flow: dict[str, list[str]] = {}
    ch7_failed_flows: set[str] = set()
    ch7_summaries: dict[str, dict[str, Any]] = {}
    all_checked_flow_ids = sorted((manifest_flow_ids | in_scope_flow_ids) - out_of_scope_flow_ids)
    for fid in all_checked_flow_ids:
        c7_ok, c7_sum, f_ch7_miss, f_ch7_man = _verify_chapter7_for_flow(
            root,
            flow_id=fid,
            scope_doc=scope_doc,
            chapter7_slice_report=chapter7_slice_report,
            plans=plans,
            bindings=bindings,
            manifest_doc=manifest_doc,
            strict_report_flow_match=False,
        )
        if c7_sum is not None:
            ch7_summaries[fid] = c7_sum
        if f_ch7_man:
            ch7_manual_by_flow[fid] = f_ch7_man
        if not c7_ok:
            ch7_failed_flows.add(fid)
            missing_ch7.extend(f_ch7_miss)
    if ch7_summaries:
        payload["chapter7_slice"] = ch7_summaries if len(ch7_summaries) > 1 else next(iter(ch7_summaries.values()))

    # Collect manual obligations across scope, receipts, Chapter 7, and handoff
    manual_obs = _collect_manual_obligations_for_scope(scope_doc, loaded_receipts, flow_id=None)
    all_required_manual_ids = {m["manual_id"] for m in manual_obs}
    for f_mans in ch7_manual_by_flow.values():
        all_required_manual_ids.update(f_mans)

    # Verify milestone handoff required_regressions, planned_tests, and manual_obligations against reverified evidence
    if isinstance(handoff_doc, dict):
        for ht_key in ("required_regressions", "planned_tests"):
            for req_test in handoff_doc.get(ht_key) or []:
                rt = str(req_test).strip()
                if rt and rt not in passed_tests:
                    missing_tests.add(rt)
                    for mf in manifest_doc.get("flows") or []:
                        if isinstance(mf, dict) and rt in (mf.get("test_ids") or []):
                            if ht_key == "required_regressions":
                                failed_existing_flows.add(str(mf["id"]))
                            else:
                                failed_current_flows.add(str(mf["id"]))
        for hm in handoff_doc.get("manual_obligations") or []:
            hmid = str(hm).strip()
            if hmid:
                all_required_manual_ids.add(hmid)

    pending_manual_ids = sorted(mid for mid in all_required_manual_ids if mid not in manual_verified_map)

    # Verify 100% of cumulative manifest flows, handoffs, tests, Ch7, and per-Flow manual signoff on the same snapshot
    for mf in manifest_doc.get("flows") or []:
        if not isinstance(mf, dict):
            continue
        fid = str(mf.get("id") or "")
        f_ok = True
        required_tids = set(mf.get("test_ids") or [])
        for h in mf.get("handoffs") or []:
            if isinstance(h, dict):
                required_tids.update(h.get("test_ids") or [])
        for tid in sorted(required_tids):
            entry = passed_tests.get(tid)
            if entry is None:
                missing_tests.add(str(tid))
                f_ok = False
                continue
            mtest = manifest_tests.get(tid) or {}
            if str(mtest.get("state") or "").strip().lower() != "implemented":
                f_ok = False
                continue
            req_tier = _normalize_required_tier(str(mtest.get("kind") or ""), mtest.get("evidence_level"))
            tier_ok, tier_reason = _tier_matches_strict(req_tier, entry)
            if not tier_ok:
                tier_violations.append({
                    "obligation_id": f"manifest:{fid}:{tid}",
                    "test_id": tid,
                    "required_tier": req_tier,
                    "actual_tier": _normalize_required_tier(str(entry.get("kind") or ""), entry.get("evidence_level")),
                    "reason": tier_reason,
                })
                f_ok = False
        f_blocking_tasks = [
            t for t in (mf.get("task_ids") or [])
            if type(t) is int and t in blocking_participants
        ]
        f_ch7_ok = fid not in ch7_failed_flows
        f_manual_obs = _collect_manual_obligations_for_scope(scope_doc, loaded_receipts, flow_id=fid)
        f_req_manual = {m["manual_id"] for m in f_manual_obs} | set(ch7_manual_by_flow.get(fid) or [])
        f_pending_manual = sorted(mid for mid in f_req_manual if mid not in manual_verified_map)

        if not f_ok or f_blocking_tasks or not f_ch7_ok:
            if fid in existing_required_flow_ids or fid not in current_new_flow_ids:
                failed_existing_flows.add(fid)
            else:
                failed_current_flows.add(fid)

        f_fully_done = (
            f_ok
            and not f_blocking_tasks
            and f_ch7_ok
            and not f_pending_manual
            and not any_protocol_fixture
            and all_receipts_runtime_verified
        )
        payload["flow_verdicts"][fid] = {
            "flow_id": fid,
            "flow_completed": f_fully_done,
            "flow_status": (
                "completed" if f_fully_done
                else ("manual_pending" if (f_ok and not f_blocking_tasks and f_ch7_ok and f_pending_manual) else "blocked")
            ),
        }

    for fid in sorted(failed_current_flows | failed_existing_flows):
        if fid in payload["flow_verdicts"]:
            payload["flow_verdicts"][fid]["flow_completed"] = False
            if payload["flow_verdicts"][fid]["flow_status"] == "completed":
                payload["flow_verdicts"][fid]["flow_status"] = "blocked"
        else:
            payload["flow_verdicts"][fid] = {
                "flow_id": fid,
                "flow_completed": False,
                "flow_status": "blocked",
            }

    for nr in not_run_blocking:
        missing_tests.add(str(nr.get("id") or ""))

    payload["failed_existing_flows"] = sorted(failed_existing_flows)
    payload["evidence_tier_violations"] = tier_violations
    payload["missing_flow_obligations"] = {
        "missing_tasks": blocking_participants,
        "missing_tests": sorted(missing_tests),
        "missing_implementations": sorted(missing_impls),
        "missing_chapter7_slices": sorted(set(missing_ch7)),
        "pending_manual_obligations": pending_manual_ids,
    }

    automated_ok = (
        not blocking_participants
        and not missing_tests
        and not missing_impls
        and not missing_ch7
        and not tier_violations
        and not failed_tests
        and not skipped_tests
        and not not_run_blocking
        and not failed_existing_flows
        and not failed_current_flows
    )

    if any_protocol_fixture or not all_receipts_runtime_verified:
        payload["protocol_fixture_satisfied_only"] = automated_ok
        payload["automated_milestone_passed"] = False
        payload["cumulative_full_mvg_completed"] = False
        payload["milestone_completed"] = False
        payload["runtime_verified"] = False
        payload["ok"] = False
        payload["verdict_status"] = "blocked"
        payload["reason_code"] = codec.ReasonCode.CONFLICT.value
        payload["reason"] = "protocol_fixture_cannot_satisfy_cumulative_full_mvg"
        payload["diagnostics"] = [
            _diag(
                codec.ReasonCode.CONFLICT,
                codec.Stage.CONTENT,
                manifest_rel,
                "real_runtime verified receipt (runtime_verified=true, protocol_fixture_only=false)",
                {"protocol_fixture_only": any_protocol_fixture, "receipts_runtime_verified": all_receipts_runtime_verified},
                loaded_receipts[0]["path"],
            )
        ]
        return

    if not automated_ok:
        payload["automated_milestone_passed"] = False
        payload["cumulative_full_mvg_completed"] = False
        payload["milestone_completed"] = False
        payload["ok"] = False
        payload["verdict_status"] = "blocked"
        rc = codec.ReasonCode.CONFLICT if (failed_existing_flows or tier_violations or failed_tests or skipped_tests) else codec.ReasonCode.PENDING
        payload["reason_code"] = rc.value
        if failed_existing_flows:
            payload["reason"] = "existing_required_flow_regression_blocks_milestone"
        elif failed_current_flows or missing_impls:
            payload["reason"] = "current_new_in_scope_obligations_incomplete"
        elif missing_ch7:
            payload["reason"] = "cumulative_full_mvg_chapter7_ui_closure_missing"
        elif tier_violations:
            payload["reason"] = "evidence_tier_substitution_forbidden"
        else:
            payload["reason"] = "cumulative_full_mvg_obligations_incomplete"
        payload["diagnostics"] = [
            _diag(
                rc,
                codec.Stage.CONTENT,
                manifest_rel,
                "all cumulative full-MVG existing_required, current_new, handoff, Chapter 7, and other_verification obligations passed on one snapshot",
                {
                    "failed_existing_flows": sorted(failed_existing_flows),
                    "failed_current_flows": sorted(failed_current_flows),
                    "missing_flow_obligations": payload["missing_flow_obligations"],
                    "evidence_tier_violations": tier_violations,
                },
                manifest_rel,
            )
        ]
        return

    payload["automated_milestone_passed"] = True
    payload["runtime_verified"] = True
    if pending_manual_ids:
        payload["manual_pending"] = True
        payload["cumulative_full_mvg_completed"] = False
        payload["milestone_completed"] = False
        payload["ok"] = False
        payload["verdict_status"] = "manual_pending"
        payload["reason_code"] = codec.ReasonCode.PENDING.value
        payload["reason"] = "cumulative_full_mvg_manual_obligations_pending"
        payload["diagnostics"] = [
            _diag(
                codec.ReasonCode.PENDING,
                codec.Stage.CONTENT,
                manifest_rel,
                "manual signoff matching exact scope_id and snapshot_digest",
                {"pending_manual_obligations": pending_manual_ids},
                manifest_rel,
            )
        ]
        return

    payload["manual_pending"] = False
    payload["verified_scope"] = "full"
    payload["cumulative_full_mvg_completed"] = True
    payload["milestone_completed"] = True
    payload["ok"] = True
    payload["verdict_status"] = "cumulative_full_mvg_completed"
    payload["reason_code"] = codec.ReasonCode.OK.value
    payload["reason"] = "cumulative_full_mvg_verified_on_single_snapshot"


def _eval_non_flow_level(
    root: Path,
    payload: dict[str, Any],
    *,
    plans: dict[str, dict[str, Any]],
    manifest_tests: dict[str, dict[str, Any]],
    scope_doc: dict[str, Any] | None,
    loaded_receipts: list[dict[str, Any]],
    passed_tests: dict[str, dict[str, Any]],
    failed_tests: list[dict[str, Any]],
    skipped_tests: list[dict[str, Any]],
    not_run_blocking: list[dict[str, Any]],
    any_protocol_fixture: bool,
    all_receipts_automated_scope_passed: bool,
    all_receipts_runtime_verified: bool,
    manual_verified_map: dict[str, dict[str, Any]],
) -> None:
    payload["verified_scope"] = "non_flow"
    if scope_doc is None:
        raise _err(
            codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
            codec.Stage.PATH,
            None,
            "sealed VerificationScope (--verification-scope) for level=non_flow",
            None,
            None,
        )
    if not loaded_receipts:
        raise _err(
            codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
            codec.Stage.PATH,
            payload.get("verification_scope_path"),
            "sealed coverage-receipt.json (--receipt) for level=non_flow",
            [],
            payload.get("verification_scope_path"),
        )

    # Collect legal non-Flow obligations from VerificationScope
    non_flow_obs = [
        o for o in (scope_doc.get("obligations") or [])
        if isinstance(o, dict)
        and o.get("tier") in vs.CURRENT_TIERS
        and (o.get("evidence_level") == "other-verification" or o.get("execution_kind") == "other_verification")
    ]
    if not non_flow_obs:
        raise _err(
            codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
            codec.Stage.CONTENT,
            payload.get("verification_scope_path"),
            "at least one adopted non-Flow other_verification obligation in VerificationScope",
            [],
            payload.get("verification_scope_path"),
        )

    # Verify substantive non-Flow rationale in BOTH plan.applicability AND plan.requirement_verification / dispositions
    req_app_map: dict[str, dict[str, Any]] = {}
    req_ver_map: dict[str, dict[str, Any]] = {}
    for pinfo in plans.values():
        pdoc = pinfo.get("doc") or {}
        for app in pdoc.get("applicability") or []:
            if isinstance(app, dict) and isinstance(app.get("requirement_id"), str):
                req_app_map[app["requirement_id"]] = app
        for rv in list(pdoc.get("requirement_verification") or []) + list(pdoc.get("dispositions") or []):
            if isinstance(rv, dict) and isinstance(rv.get("requirement_id"), str):
                req_ver_map[rv["requirement_id"]] = rv

    missing_rationale: list[str] = []
    missing_tests: set[str] = set()
    missing_impls: set[str] = set()
    tier_violations: list[dict[str, Any]] = []

    for obl in non_flow_obs:
        req_ids = [str(r) for r in (obl.get("requirement_ids") or []) if isinstance(r, str) and r.strip()]
        if not req_ids:
            missing_rationale.append(str(obl.get("obligation_id") or "non_flow"))
        for req_id in req_ids:
            app = req_app_map.get(req_id)
            rv = req_ver_map.get(req_id)
            app_ok = (
                app is not None
                and str(app.get("disposition") or "").strip().lower() == "other_verification"
                and _is_substantive_manual_notes(app.get("rationale"))
            )
            rv_ok = (
                rv is not None
                and str(rv.get("disposition") or "").strip().lower() == "other_verification"
            )
            if not (app_ok and rv_ok):
                missing_rationale.append(req_id)
        sat, miss, tv = _evaluate_obligation_satisfaction(obl, passed_tests, failed_tests, manifest_tests)
        if not sat:
            for m in miss:
                if m.get("reason") == "obligation_unimplemented_or_blocked":
                    missing_impls.add(str(obl.get("obligation_id") or ""))
                else:
                    missing_tests.add(str(obl.get("obligation_id") or ""))
        tier_violations.extend(tv)

    # If the non-Flow change ALSO impacted MVG Flows in VerificationScope, require those impacted regressions too!
    impacted_flow_obs = [
        o for o in (scope_doc.get("obligations") or [])
        if isinstance(o, dict)
        and o.get("tier") in vs.CURRENT_TIERS
        and o.get("flow_ids")
        and o.get("evidence_level") not in {"manual", "other-verification"}
        and o.get("execution_kind") not in {"manual", "manual_check", "other_verification"}
    ]
    failed_impacted_flows: set[str] = set()
    for obl in impacted_flow_obs:
        sat, miss, tv = _evaluate_obligation_satisfaction(obl, passed_tests, failed_tests, manifest_tests)
        if not sat or tv:
            for fid in obl.get("flow_ids") or []:
                failed_impacted_flows.add(str(fid))
            for m in miss:
                if m.get("test_id"):
                    missing_tests.add(str(m["test_id"]))
                for mtid in m.get("test_ids") or []:
                    missing_tests.add(str(mtid))
            tier_violations.extend(tv)

    # Check applicable manual obligations for non_flow scope
    manual_obs = _collect_manual_obligations_for_scope(scope_doc, loaded_receipts, flow_id=None)
    pending_manual_ids = sorted({m["manual_id"] for m in manual_obs if m["manual_id"] not in manual_verified_map})

    payload["failed_existing_flows"] = sorted(failed_impacted_flows)
    payload["evidence_tier_violations"] = tier_violations
    payload["missing_flow_obligations"] = {
        "missing_tasks": [],
        "missing_tests": sorted(missing_tests),
        "missing_implementations": sorted(missing_impls) + [f"rationale:{r}" for r in sorted(set(missing_rationale))],
        "missing_chapter7_slices": [],
        "pending_manual_obligations": pending_manual_ids,
    }

    if missing_rationale or missing_tests or missing_impls or tier_violations or failed_tests or skipped_tests or not_run_blocking or failed_impacted_flows:
        payload["non_flow_completed"] = False
        payload["runtime_verified"] = False
        payload["ok"] = False
        payload["verdict_status"] = "blocked"
        payload["reason_code"] = codec.ReasonCode.CONFLICT.value
        payload["reason"] = (
            "non_flow_missing_adopted_exemption_rationale" if missing_rationale else
            "non_flow_impacted_mvg_regressions_failed" if failed_impacted_flows else
            "non_flow_other_verification_unsatisfied"
        )
        payload["diagnostics"] = [
            _diag(
                codec.ReasonCode.CONFLICT,
                codec.Stage.CONTENT,
                payload.get("verification_scope_path"),
                "adopted non-Flow rationale in applicability+requirement_verification + passing other_verification evidence + any impacted MVG regressions",
                {
                    "missing_rationale": sorted(set(missing_rationale)),
                    "failed_impacted_flows": sorted(failed_impacted_flows),
                    "missing_flow_obligations": payload["missing_flow_obligations"],
                },
                payload.get("verification_scope_path"),
            )
        ]
        return

    if not impacted_flow_obs:
        # Pure legal non-Flow (zero impacted MVG runtime obligations):
        # accept automated_scope_passed=True + protocol_fixture_only=False while keeping runtime_verified=False!
        if any_protocol_fixture or not all_receipts_automated_scope_passed:
            payload["protocol_fixture_satisfied_only"] = bool(any_protocol_fixture)
            payload["non_flow_completed"] = False
            payload["runtime_verified"] = False
            payload["ok"] = False
            payload["verdict_status"] = "blocked"
            payload["reason_code"] = codec.ReasonCode.CONFLICT.value
            payload["reason"] = "protocol_fixture_or_incomplete_receipt_cannot_satisfy_non_flow_completion"
            payload["diagnostics"] = [
                _diag(
                    codec.ReasonCode.CONFLICT,
                    codec.Stage.CONTENT,
                    loaded_receipts[0]["path"],
                    "non-fixture receipt with automated_scope_passed=true for pure non-Flow other_verification",
                    {
                        "protocol_fixture_only": any_protocol_fixture,
                        "automated_scope_passed": all_receipts_automated_scope_passed,
                    },
                    loaded_receipts[0]["path"],
                )
            ]
            return
        if pending_manual_ids:
            payload["manual_pending"] = True
            payload["non_flow_completed"] = False
            payload["runtime_verified"] = False
            payload["ok"] = False
            payload["verdict_status"] = "manual_pending"
            payload["reason_code"] = codec.ReasonCode.PENDING.value
            payload["reason"] = "non_flow_manual_obligations_pending"
            payload["diagnostics"] = [
                _diag(
                    codec.ReasonCode.PENDING,
                    codec.Stage.CONTENT,
                    payload.get("verification_scope_path"),
                    "manual signoff covering applicable non-Flow manual obligations",
                    {"pending_manual_obligations": pending_manual_ids},
                    payload.get("verification_scope_path"),
                )
            ]
            return
        payload["manual_pending"] = False
        payload["non_flow_completed"] = True
        payload["runtime_verified"] = False
        payload["flow_completed"] = False
        payload["cumulative_full_mvg_completed"] = False
        payload["milestone_completed"] = False
        payload["ok"] = True
        payload["verdict_status"] = "non_flow_completed"
        payload["reason_code"] = codec.ReasonCode.OK.value
        payload["reason"] = "legal_non_flow_other_verification_completed"
        return

    # Flow-impacting non-Flow change: requires runtime_verified=True on impacted MVG Flow tests + manual signoff!
    if any_protocol_fixture or not all_receipts_runtime_verified:
        payload["protocol_fixture_satisfied_only"] = True
        payload["non_flow_completed"] = False
        payload["runtime_verified"] = False
        payload["ok"] = False
        payload["verdict_status"] = "blocked"
        payload["reason_code"] = codec.ReasonCode.CONFLICT.value
        payload["reason"] = "flow_impacting_non_flow_requires_real_runtime_verified_receipt"
        payload["diagnostics"] = [
            _diag(
                codec.ReasonCode.CONFLICT,
                codec.Stage.CONTENT,
                loaded_receipts[0]["path"],
                "real_runtime verified receipt (runtime_verified=true, protocol_fixture_only=false) for impacted MVG flows",
                {
                    "protocol_fixture_only": any_protocol_fixture,
                    "receipts_runtime_verified": all_receipts_runtime_verified,
                },
                loaded_receipts[0]["path"],
            )
        ]
        return

    if pending_manual_ids:
        payload["manual_pending"] = True
        payload["non_flow_completed"] = False
        payload["runtime_verified"] = True
        payload["ok"] = False
        payload["verdict_status"] = "manual_pending"
        payload["reason_code"] = codec.ReasonCode.PENDING.value
        payload["reason"] = "non_flow_manual_obligations_pending"
        payload["diagnostics"] = [
            _diag(
                codec.ReasonCode.PENDING,
                codec.Stage.CONTENT,
                payload.get("verification_scope_path"),
                "manual signoff covering applicable manual obligations",
                {"pending_manual_obligations": pending_manual_ids},
                payload.get("verification_scope_path"),
            )
        ]
        return

    payload["manual_pending"] = False
    payload["non_flow_completed"] = True
    payload["runtime_verified"] = True
    payload["flow_completed"] = False
    payload["cumulative_full_mvg_completed"] = False
    payload["milestone_completed"] = False
    payload["ok"] = True
    payload["verdict_status"] = "non_flow_completed"
    payload["reason_code"] = codec.ReasonCode.OK.value
    payload["reason"] = "legal_non_flow_and_impacted_mvg_completed"
