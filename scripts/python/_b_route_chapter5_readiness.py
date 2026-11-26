"""B-route Chapter 5 same-source reconciliation and readiness gate engine.

Responsibilities:
- Classify Task via Story 3.3 (resolve_task_origin); require route="B" and
  committed stage="5" bindings across all applicable plans (blocking with
  return_stage="4" or "5" when unmet).
- Acquire only business-scope leases via Story 3.5 guarded_input_set
  (review_only=True, never global writer lock) during reconciliation and
  revalidate before finalizing.
- Read-only verify 3A source identities and proofs (reusing unchanged 3A proofs
  with zero model dispatch), while always running independent Chapter 5 semantic
  reconciliation (explicit acceptance_links, authority_decisions,
  dependency_decisions, overlap_decisions, Acceptance/Refs, Requirement,
  non-Flow dispositions, ADR/Overlay/Contract, dependencies, three roles,
  handoff ownership, and Stage-5 obligations).
- Permit non-done Tasks and explicitly defined planned objects/tests without
  requiring fake disk stubs or marking them implemented/runtime_verified.
- Enforce no self-lock on integration_only_owner, old-done reverification
  (requires_chapter6_reverification=True), P0/P1 floor, P2..P4 technical-debt
  recording in docs/technical-debt.md when allow_concerns=True, and strict
  anti-quality-downgrade / anti-timestamp-spoofing / anti-legacy-fallback rules.
- Freeze input_set_digest, applicable_set_digest, scope_ids, plan_refs,
  binding_refs, and reconciliation_sha256 in Chapter 5 standard schemas, and
  bridge chapter5_semantic_reconciliation.load_task_readiness and
  refresh_chapter_knowledge.chapter5_closure_evidence.
- Maintain runtime_verified=False and default_b_enabled=False unconditionally.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from copy import deepcopy
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import time
from typing import Any

import _b_route_chapter4_binding as ch4_binding
import _b_route_codec as codec
import _b_route_input_set as input_set
import _b_route_inventory as inventory
import _b_route_preflight as preflight
import _b_route_records as records
import _b_route_source_audit as source_audit
import _b_route_sources as b_sources
import _b_route_stage5_obligations as stage5_obls
import _b_route_task_resolver as task_resolver
import _chapter5_contract_bindings as contract_bindings
import _mvg_manifest as mvg_manifest
import _planning_apply_journal as journal


B_ROUTE_SCHEMA = "newrouge.b-route-chapter5-readiness.v1"
RECONCILIATION_SCHEMA = "newrouge.semantic-reconciliation.v1"
READINESS_SCHEMA = "newrouge.chapter5-readiness.v1"
DEFAULT_RECONCILIATION_DIR = Path("logs/ci/chapter5/reconciliation")
DEFAULT_READINESS_DIR = Path("logs/ci/chapter5/readiness")
TECHNICAL_DEBT_PATH = "docs/technical-debt.md"

_DEBT_BEGIN = "<!-- BEGIN AUTO:B_ROUTE_CHAPTER5_TECHNICAL_DEBT -->"
_DEBT_END = "<!-- END AUTO:B_ROUTE_CHAPTER5_TECHNICAL_DEBT -->"

P0_P1_SEVERITIES = frozenset({"P0", "P1"})
DEFERRABLE_SEVERITIES = frozenset({"P2", "P3", "P4"})
ALL_SEVERITIES = P0_P1_SEVERITIES | DEFERRABLE_SEVERITIES

P1_FLOOR_CATEGORIES = frozenset(
    {
        "acceptance-refs",
        "acceptance-anchors",
        "artifact-integrity",
        "planned-only",
        "planned_only",
        "security",
        "security-boundary",
        "test-false-green",
        "false-green",
    }
)

ALLOWED_AUTHORITY_STATUS = frozenset({"compatible", "conflict", "out_of_scope"})
ALLOWED_DEPENDENCY_RELATIONS = frozenset(
    {"producer_consumer", "contract", "schema", "state", "asset_scene_availability"}
)
ALLOWED_OVERLAP_DECISIONS = frozenset({"keep_separate", "merge_recommended", "overlap_justified"})
STAGE_ORDER = input_set.STAGE_ORDER
STAGE_RANK = input_set.STAGE_RANK

INVARIANT_FLAGS = {
    "runtime_verified": False,
    "default_b_enabled": False,
}

_REFS_RE = re.compile(r"\bRefs:\s*([^\n]+)$", re.IGNORECASE | re.MULTILINE)
_ADR_TOKEN_RE = re.compile(r"\bADR-\d{3,5}\b", re.IGNORECASE)
_NA_ONLY_RE = re.compile(r"^(?:n/?a|none|null|tbd|todo|skip|exempt|pass|ok|\-+)$", re.IGNORECASE)
_GODOT_USING_RE = re.compile(r"(?:^|\n)\s*using\s+Godot\b|\bGodot\.", re.MULTILINE)
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_POS_INT_RE = re.compile(r"^[1-9][0-9]*$")
_FLOAT_INT_RE = re.compile(r"^[0-9]+\.0$")

_FORBIDDEN_DOWNGRADE_KEYS = {
    "skip_chapter5_reconciliation": "3A proof cannot bypass Chapter 5 semantic reconciliation",
    "reuse_3a_skip_chapter5": "3A proof cannot bypass Chapter 5 semantic reconciliation",
    "lower_thresholds": "lowering quality thresholds is forbidden",
    "disable_tests": "disabling tests to obtain green readiness is forbidden",
    "skip_tests": "skipping required tests is forbidden",
    "ignore_test_failures": "ignoring test failures is forbidden",
    "weaken_acceptance": "weakening acceptance criteria is forbidden",
    "drop_acceptance_refs": "dropping acceptance Refs is forbidden",
    "waive_p1": "waiving P0/P1 findings violates the P1 floor",
    "waive_blocking_findings": "waiving blocking findings is forbidden",
    "override_p1_floor": "overriding the P1 floor is forbidden",
    "claim_skip_reverification": "claiming old done exempts new obligations is forbidden",
    "old_done_exempts_reverification": "old done status never exempts new obligations or planned tests",
    "claim_no_reverification": "claiming no reverification for old done with new obligations is forbidden",
}


def _diag(
    code: codec.ReasonCode,
    *,
    stage: codec.Stage = codec.Stage.BUNDLE,
    entity_id: str | None = None,
    expected: Any = None,
    actual: Any = None,
    resume_ref: str | None = None,
) -> dict[str, Any]:
    return codec.Diagnostic(
        code,
        stage,
        entity_id,
        expected,
        actual,
        resume_ref,
    ).to_dict()


def _fail(
    code: codec.ReasonCode,
    *,
    stage: codec.Stage = codec.Stage.BUNDLE,
    entity_id: str | None = None,
    expected: Any = None,
    actual: Any = None,
    resume_ref: str | None = None,
) -> None:
    raise codec.CodecError(
        codec.Diagnostic(code, stage, entity_id, expected, actual, resume_ref)
    )


def _canonical_sha(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_substantive_text(value: Any) -> bool:
    if type(value) is not str:
        return False
    stripped = value.strip()
    if len(stripped) < 4:
        return False
    return _NA_ONLY_RE.fullmatch(stripped) is None


def _earliest_stage(stages: list[str | None]) -> str | None:
    valid = [s for s in stages if s in STAGE_RANK]
    if not valid:
        return None
    return min(valid, key=lambda s: STAGE_RANK[s])


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        tmp.replace(path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def _parse_acceptance_refs(text: str) -> list[str]:
    refs: list[str] = []
    for match in _REFS_RE.finditer(str(text or "")):
        for token in re.split(r"[\s,;]+", match.group(1).strip()):
            cleaned = token.strip().strip("`'\"").replace("\\", "/")
            if cleaned and cleaned not in refs:
                refs.append(cleaned)
    return refs


def _stable_finding_id(prefix: str, category: str, message: str, entity_id: str = "") -> str:
    digest = hashlib.sha256(f"{prefix}\0{category}\0{entity_id}\0{message}".encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _canonical_task_id_str(value: Any) -> str:
    if value is None or isinstance(value, bool):
        return ""
    text = str(value).strip()
    if _FLOAT_INT_RE.fullmatch(text):
        return text[:-2]
    return text


def _readiness_path_for_task(root: Path, task_id: int) -> Path:
    return root / DEFAULT_READINESS_DIR / f"task-{task_id}.json"


def _reconciliation_path_for_task(root: Path, task_id: int) -> Path:
    return root / DEFAULT_RECONCILIATION_DIR / f"task-{task_id}.json"


def _validate_log_path(
    root: Path,
    raw_path: str | Path,
    *,
    require_logs: bool = True,
) -> tuple[Path, str]:
    """Validate repository-contained path with reparse/symlink protection and Windows 8.3 safety."""
    root_resolved = Path(root).resolve()
    text = str(raw_path).replace("\\", "/").strip()
    if not text:
        _fail(
            codec.ReasonCode.UNSAFE_PATH,
            stage=codec.Stage.PATH,
            expected="nonempty repository-relative path" + (" under logs/" if require_logs else ""),
            actual=str(raw_path),
        )
    candidate = Path(text)
    if candidate.is_absolute():
        try:
            for ancestor in reversed((candidate, *candidate.parents)):
                inventory.no_reparse(ancestor)
            resolved = candidate.resolve()
            rel = resolved.relative_to(root_resolved).as_posix()
        except (ValueError, OSError) as exc:
            _fail(
                codec.ReasonCode.UNSAFE_PATH,
                stage=codec.Stage.PATH,
                expected="safe non-reparse path inside repository" + (" under logs/" if require_logs else ""),
                actual=str(exc) if str(exc) else str(raw_path),
            )
    else:
        rel = preflight.path(text)
    if require_logs and (not rel.startswith("logs/") or rel == "logs/"):
        _fail(
            codec.ReasonCode.UNSAFE_PATH,
            stage=codec.Stage.PATH,
            expected="output path inside logs/",
            actual=rel,
        )
    try:
        target = inventory.safe_input(root_resolved, rel, allow_logs=True)
    except (ValueError, OSError) as exc:
        _fail(
            codec.ReasonCode.UNSAFE_PATH,
            stage=codec.Stage.PATH,
            expected="safe non-reparse path inside repository",
            actual=str(exc),
        )
    return target, rel


def _validate_log_output_path(root: Path, raw_path: str | Path) -> Path:
    target, _rel = _validate_log_path(root, raw_path, require_logs=True)
    return target


def _artifact_has_b_route_marker(payload: Any) -> bool:
    if type(payload) is not dict:
        return False
    return bool(
        payload.get("route") == "B"
        or payload.get("b_route_schema_version") == B_ROUTE_SCHEMA
        or isinstance(payload.get("b_route_readiness"), dict)
        or (
            type(payload.get("input_set_digest")) is str
            and _DIGEST_RE.fullmatch(payload["input_set_digest"]) is not None
        )
        or (
            type(payload.get("input_fingerprint")) is str
            and _DIGEST_RE.fullmatch(payload["input_fingerprint"]) is not None
        )
    )


def detect_repo_b_route_presence(
    root: Path | str,
    task_id: int | str | None = None,
    *,
    reconciliation: dict[str, Any] | None = None,
    readiness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Pure read-only zero-write detector of B-route traces in repo or artifacts."""
    root_path = Path(root).resolve()
    reasons: list[str] = []
    artifact_is_b = _artifact_has_b_route_marker(reconciliation) or _artifact_has_b_route_marker(readiness)
    if artifact_is_b:
        reasons.append("artifact_has_b_route_marker")

    repo_has_b = False
    b_dir = root_path / "docs/planning/b-route"
    if b_dir.is_dir():
        for path in b_dir.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root_path).as_posix()
            # Ignore static committed schema definitions under docs/planning/b-route/schemas/**.
            if rel.casefold().startswith("docs/planning/b-route/schemas/"):
                continue
            if rel in task_resolver.GOVERNANCE or records._managed_candidate(rel) or rel.startswith("docs/planning/b-route/"):
                repo_has_b = True
                reasons.append("b_route_governance_dir_present")
                break

    op_dir = root_path / task_resolver.OP_STORE
    if op_dir.is_dir():
        found_op = False
        for entry in op_dir.iterdir():
            if entry.name.casefold() == "locks":
                continue
            if entry.is_file() and entry.suffix.casefold() == ".json":
                found_op = True
                break
        if not found_op:
            ops_sub = op_dir / "operations"
            if ops_sub.is_dir():
                for child in ops_sub.iterdir():
                    if child.is_file() and child.suffix.casefold() == ".json":
                        found_op = True
                        break
                    if child.is_dir():
                        for sub in child.iterdir():
                            if sub.is_file() and sub.suffix.casefold() == ".json":
                                found_op = True
                                break
                        if found_op:
                            break
        if found_op:
            repo_has_b = True
            reasons.append("b_route_operations_present")

    if not repo_has_b:
        triplet_docs: dict[str, Any] = {}
        all_present = True
        for name, rel in task_resolver.TRIPLET.items():
            p = root_path / rel
            if not p.is_file():
                all_present = False
                break
            try:
                triplet_docs[name] = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                all_present = False
                break
        if all_present:
            try:
                global_traces, _per_task = task_resolver._scan_triplet_traces(triplet_docs)
                if global_traces:
                    repo_has_b = True
                    reasons.append("triplet_b_route_traces_present")
            except Exception:
                pass

    return {
        "has_b_traces": bool(artifact_is_b or repo_has_b),
        "artifact_is_b_route": artifact_is_b,
        "repo_has_b_traces": repo_has_b,
        "task_id": _canonical_task_id_str(task_id) if task_id is not None else None,
        "reasons": reasons,
    }


def _load_plan_and_binding_bundle(
    root: Path,
    origin: dict[str, Any],
) -> tuple[
    dict[str, tuple[dict[str, Any], bytes, dict[str, Any]]],
    dict[str, tuple[dict[str, Any], bytes, dict[str, Any], dict[str, Any]]],
    dict[str, str],
    dict[str, Any],
    dict[int, dict[str, Any]],
    dict[int, list[dict[str, Any]]],
    dict[int, list[dict[str, Any]]],
]:
    """Load all applicable committed plans, bindings, sealed log digests, and triplet."""
    obs = preflight.Observations(root)
    triplet_raw = {name: obs.read(rel) for name, rel in task_resolver.TRIPLET.items()}
    triplet_docs = {name: codec.strict_json_loads(raw) for name, raw in triplet_raw.items()}
    task_join = records.TaskJoinContext(**triplet_docs)
    master_tasks, views = task_join.indexes()
    back_by_tid: dict[int, list[dict[str, Any]]] = {}
    for row in triplet_docs["back"]:
        back_by_tid.setdefault(row["taskmaster_id"], []).append(row)
    gameplay_by_tid: dict[int, list[dict[str, Any]]] = {}
    for row in triplet_docs["gameplay"]:
        gameplay_by_tid.setdefault(row["taskmaster_id"], []).append(row)

    catalog = codec.strict_json_loads(obs.read(task_resolver.CATALOG_PATH))
    sealed_digests = input_set._build_receipt_seal_index(
        obs, catalog, sorted(set(origin.get("applicable_scope_ids") or []))
    )

    loaded_plans: dict[str, tuple[dict[str, Any], bytes, dict[str, Any]]] = {}
    for pref in origin.get("plan_refs") or []:
        pid = pref["entity_id"]
        praw = obs.read(pref["path"])
        pdoc = task_resolver._load_formal_json(obs, pref)
        loaded_plans[pid] = (pref, praw, pdoc)

    loaded_bindings: dict[str, tuple[dict[str, Any], bytes, dict[str, Any], dict[str, Any]]] = {}
    tid = int(origin["task_id"])
    for bref in origin.get("binding_refs") or []:
        pid = bref["entity_id"]
        braw = obs.read(bref["path"])
        bdoc = task_resolver._load_formal_json(obs, bref)
        mapping = next((m for m in bdoc.get("task_mappings", []) if m["task_id"] == tid), None)
        if mapping is None:
            _fail(
                codec.ReasonCode.MAPPING_MISMATCH,
                stage=codec.Stage.BUNDLE,
                entity_id=str(tid),
                expected=f"task_mapping for task {tid} in binding {bref['path']}",
                actual=pid,
                resume_ref=bref["path"],
            )
        loaded_bindings[pid] = (bref, braw, bdoc, mapping)
        if pid not in loaded_plans:
            pref = bdoc["plan_ref"]
            praw = obs.read(pref["path"])
            pdoc = task_resolver._load_formal_json(obs, pref)
            loaded_plans[pid] = (pref, praw, pdoc)

    return loaded_plans, loaded_bindings, sealed_digests, views, master_tasks, back_by_tid, gameplay_by_tid


def _read_owned_ref_bytes(
    root: Path,
    ref: dict[str, Any],
    *,
    sealed_digests: dict[str, str],
    allow_sealed_logs: bool,
    entity_id: str,
    return_stage: str,
) -> dict[str, bytes | None]:
    """Read and verify all files in an OwnedRef; allow sealed logs only on clean clones."""
    obs = preflight.Observations(root)
    result: dict[str, bytes | None] = {}
    for frow in ref.get("files") or []:
        rel = preflight.path(frow["path"])
        expected_digest = frow["raw_digest"]
        live = obs.read(rel, optional=True)
        if live is not None:
            actual_digest = codec.raw_digest(live)
            if actual_digest != expected_digest:
                _fail(
                    codec.ReasonCode.DIGEST_MISMATCH,
                    stage=codec.Stage.CONTENT,
                    entity_id=entity_id,
                    expected={"path": rel, "raw_digest": expected_digest, "return_stage": return_stage},
                    actual={"path": rel, "raw_digest": actual_digest, "return_stage": return_stage},
                    resume_ref=rel,
                )
            result[rel] = live
        elif allow_sealed_logs and rel.startswith("logs/") and sealed_digests.get(rel) == expected_digest:
            result[rel] = None
        else:
            _fail(
                codec.ReasonCode.FILE_NOT_FOUND,
                stage=codec.Stage.PATH,
                entity_id=entity_id,
                expected={"path": rel, "raw_digest": expected_digest, "return_stage": return_stage},
                actual={"path": rel, "exists": False, "return_stage": return_stage},
                resume_ref=rel,
            )
    return result


def _verify_3a_source_audit(
    root: Path,
    rel_ref: str,
    *,
    scope_hint: str | None = None,
    expected_sources_by_path: dict[str, str] | None = None,
    expected_manifest_digests: set[str] | None = None,
    entity_id: str = "",
) -> str:
    """Read-only validate a 3A source_audit event.json/report.json or newrouge.b-route-source-audit.v1 artifact."""
    root_resolved = Path(root).resolve()
    _target, norm_rel = _validate_log_path(root_resolved, rel_ref, require_logs=False)
    target_rel = norm_rel
    if norm_rel == "event.json" or norm_rel.endswith("/event.json"):
        sibling_report = norm_rel[: -len("event.json")] + "report.json"
        if not (root_resolved / sibling_report).is_file():
            _fail(
                codec.ReasonCode.FILE_NOT_FOUND,
                stage=codec.Stage.PATH,
                entity_id=entity_id,
                expected={"sibling_report_json": sibling_report, "return_stage": "3A"},
                actual={"exists": False, "return_stage": "3A"},
                resume_ref=norm_rel,
            )
        target_rel = sibling_report

    obs = b_sources.Observations(root_resolved)
    try:
        report_doc = obs.json(target_rel)
    except codec.CodecError as err:
        d = err.diagnostic
        _fail(
            d.reason_code,
            stage=d.stage or codec.Stage.CONTENT,
            entity_id=entity_id,
            expected={"audit_ref": target_rel, "expected": d.expected, "return_stage": "3A"},
            actual={"actual": d.actual, "return_stage": "3A"},
            resume_ref=target_rel,
        )
    except Exception as exc:
        _fail(
            codec.ReasonCode.FILE_NOT_FOUND if isinstance(exc, FileNotFoundError) else codec.ReasonCode.READ_ERROR,
            stage=codec.Stage.PATH,
            entity_id=entity_id,
            expected={"valid_3a_source_audit_proof": target_rel, "return_stage": "3A"},
            actual={"error": f"{type(exc).__name__}: {exc}", "return_stage": "3A"},
            resume_ref=target_rel,
        )

    if type(report_doc) is not dict or report_doc.get("schema_version") != source_audit.SCHEMA:
        _fail(
            codec.ReasonCode.SCHEMA_MISMATCH,
            stage=codec.Stage.SCHEMA,
            entity_id=entity_id,
            expected={"schema_version": source_audit.SCHEMA, "return_stage": "3A"},
            actual={
                "schema_version": report_doc.get("schema_version") if type(report_doc) is dict else type(report_doc).__name__,
                "return_stage": "3A",
            },
            resume_ref=target_rel,
        )

    parent_dir = (root_resolved / target_rel).parent
    is_event_bundle = (
        "/b-route-source-audit/" in target_rel
        or (parent_dir / "proof.json").is_file()
        or (parent_dir / "event.json").is_file()
    )
    expected_sources = dict(expected_sources_by_path or {})
    expected_manifests = set(expected_manifest_digests or ())

    if is_event_bundle:
        scope_id = scope_hint or str(report_doc.get("scope_id") or "")
        try:
            proof = source_audit.verify_current_proof(obs, target_rel, scope_id=scope_id)
            obs.verify()
        except codec.CodecError as err:
            d = err.diagnostic
            _fail(
                d.reason_code,
                stage=d.stage or codec.Stage.CONTENT,
                entity_id=entity_id,
                expected={"audit_ref": target_rel, "expected": d.expected, "return_stage": "3A"},
                actual={"actual": d.actual, "return_stage": "3A"},
                resume_ref=target_rel,
            )
        except Exception as exc:
            _fail(
                codec.ReasonCode.INPUT_STALE,
                stage=codec.Stage.CONTENT,
                entity_id=entity_id,
                expected={"valid_3a_source_audit_proof": target_rel, "return_stage": "3A"},
                actual={"error": f"{type(exc).__name__}: {exc}", "return_stage": "3A"},
                resume_ref=target_rel,
            )
        rep = proof["report"]
        comp = proof.get("comparison") or {}
        if rep.get("execution_complete") is not True or rep.get("independent_audit") is not True or rep.get("satisfied") is False:
            _fail(
                codec.ReasonCode.SEMANTIC_ERROR,
                stage=codec.Stage.CONTENT,
                entity_id=entity_id,
                expected={"execution_complete": True, "independent_audit": True, "return_stage": "3A"},
                actual={
                    "execution_complete": rep.get("execution_complete"),
                    "independent_audit": rep.get("independent_audit"),
                    "satisfied": rep.get("satisfied"),
                    "return_stage": "3A",
                },
                resume_ref=target_rel,
            )
        if rep.get("semantic_blockers") or comp.get("findings") or rep.get("termination_reason") != "complete":
            _fail(
                codec.ReasonCode.SEMANTIC_ERROR,
                stage=codec.Stage.CONTENT,
                entity_id=entity_id,
                expected={"semantic_blockers": [], "termination_reason": "complete", "return_stage": "3A"},
                actual={
                    "semantic_blockers_count": len(rep.get("semantic_blockers") or []),
                    "comparison_findings_count": len(comp.get("findings") or []),
                    "termination_reason": rep.get("termination_reason"),
                    "return_stage": "3A",
                },
                resume_ref=target_rel,
            )
        audited_files = {
            str(f.get("path")): str(f.get("raw_digest"))
            for f in (proof.get("bundle") or {}).get("files") or []
            if type(f) is dict and f.get("path")
        }
        for spath, expected_sdig in sorted(expected_sources.items()):
            actual_sdig = audited_files.get(spath)
            if actual_sdig != expected_sdig:
                _fail(
                    codec.ReasonCode.INPUT_STALE,
                    stage=codec.Stage.CONTENT,
                    entity_id=entity_id,
                    expected={"path": spath, "raw_digest": expected_sdig, "return_stage": "3A"},
                    actual={"path": spath, "raw_digest": actual_sdig, "return_stage": "3A"},
                    resume_ref=target_rel,
                )
        return target_rel

    # Standalone newrouge.b-route-source-audit.v1 artifact validation (strict fail-closed).
    if "satisfied" in report_doc and report_doc["satisfied"] is not True:
        _fail(
            codec.ReasonCode.SEMANTIC_ERROR,
            stage=codec.Stage.CONTENT,
            entity_id=entity_id,
            expected={"satisfied": True, "return_stage": "3A"},
            actual={"satisfied": report_doc.get("satisfied"), "return_stage": "3A"},
            resume_ref=target_rel,
        )
    if "execution_complete" in report_doc and report_doc["execution_complete"] is not True:
        _fail(
            codec.ReasonCode.SEMANTIC_ERROR,
            stage=codec.Stage.CONTENT,
            entity_id=entity_id,
            expected={"execution_complete": True, "return_stage": "3A"},
            actual={"execution_complete": report_doc.get("execution_complete"), "return_stage": "3A"},
            resume_ref=target_rel,
        )
    if "independent_audit" in report_doc and report_doc["independent_audit"] is not True:
        _fail(
            codec.ReasonCode.SEMANTIC_ERROR,
            stage=codec.Stage.CONTENT,
            entity_id=entity_id,
            expected={"independent_audit": True, "return_stage": "3A"},
            actual={"independent_audit": report_doc.get("independent_audit"), "return_stage": "3A"},
            resume_ref=target_rel,
        )
    if not (
        report_doc.get("satisfied") is True
        or (report_doc.get("execution_complete") is True and report_doc.get("independent_audit") is True)
    ):
        _fail(
            codec.ReasonCode.SEMANTIC_ERROR,
            stage=codec.Stage.CONTENT,
            entity_id=entity_id,
            expected={"satisfied_or_complete_audit": True, "return_stage": "3A"},
            actual={"satisfied": report_doc.get("satisfied"), "execution_complete": report_doc.get("execution_complete"), "return_stage": "3A"},
            resume_ref=target_rel,
        )
    raw_blockers = list(report_doc.get("semantic_blockers") or [])
    raw_findings = list(report_doc.get("findings") or [])
    blocking_in_findings = [
        f
        for f in raw_findings
        if type(f) is dict and str(f.get("severity") or "blocking").strip().lower() in ("blocking", "p0", "p1")
    ]
    if (
        raw_blockers
        or blocking_in_findings
        or int(report_doc.get("blocking_count") or 0) > 0
        or report_doc.get("exit_code") not in (None, 0)
    ):
        _fail(
            codec.ReasonCode.SEMANTIC_ERROR,
            stage=codec.Stage.CONTENT,
            entity_id=entity_id,
            expected={"blocking_findings": 0, "return_stage": "3A"},
            actual={
                "semantic_blockers_count": len(raw_blockers),
                "blocking_findings_count": len(blocking_in_findings),
                "blocking_count": report_doc.get("blocking_count"),
                "exit_code": report_doc.get("exit_code"),
                "return_stage": "3A",
            },
            resume_ref=target_rel,
        )

    # Require cryptographic source digest binding against committed plans & live source bytes!
    artifact_manifest_dg = report_doc.get("source_manifest_digest") or report_doc.get("manifest_sha256")
    artifact_sources_map: dict[str, str] = {}
    raw_sources = report_doc.get("sources") or report_doc.get("source_digests")
    if type(raw_sources) is dict:
        for k, v in raw_sources.items():
            if type(k) is str and type(v) is str:
                artifact_sources_map[preflight.path(k.replace("\\", "/"))] = v
    elif type(raw_sources) is list:
        for row in raw_sources:
            if type(row) is dict and row.get("path"):
                dg = row.get("raw_digest") or row.get("sha256")
                if type(dg) is str:
                    artifact_sources_map[preflight.path(str(row["path"]).replace("\\", "/"))] = dg

    if not artifact_manifest_dg and not artifact_sources_map:
        _fail(
            codec.ReasonCode.DIGEST_MISMATCH,
            stage=codec.Stage.CONTENT,
            entity_id=entity_id,
            expected={"source_digest_binding": True, "return_stage": "3A"},
            actual={"source_digest_binding": False, "return_stage": "3A"},
            resume_ref=target_rel,
        )
    if artifact_manifest_dg and expected_manifests and str(artifact_manifest_dg) not in expected_manifests:
        _fail(
            codec.ReasonCode.INPUT_STALE,
            stage=codec.Stage.CONTENT,
            entity_id=entity_id,
            expected={"source_manifest_digest": sorted(expected_manifests), "return_stage": "3A"},
            actual={"source_manifest_digest": artifact_manifest_dg, "return_stage": "3A"},
            resume_ref=target_rel,
        )
    if artifact_sources_map:
        for spath, expected_sdig in sorted(expected_sources.items()):
            actual_sdig = artifact_sources_map.get(spath)
            if actual_sdig != expected_sdig:
                _fail(
                    codec.ReasonCode.INPUT_STALE,
                    stage=codec.Stage.CONTENT,
                    entity_id=entity_id,
                    expected={"path": spath, "raw_digest": expected_sdig, "return_stage": "3A"},
                    actual={"path": spath, "raw_digest": actual_sdig, "return_stage": "3A"},
                    resume_ref=target_rel,
                )
        for spath, claimed_sdig in sorted(artifact_sources_map.items()):
            sfile = root_resolved / spath
            if not sfile.is_file():
                _fail(
                    codec.ReasonCode.FILE_NOT_FOUND,
                    stage=codec.Stage.PATH,
                    entity_id=entity_id,
                    expected={"source_path": spath, "return_stage": "3A"},
                    actual={"exists": False, "return_stage": "3A"},
                    resume_ref=spath,
                )
            live_dg = codec.raw_digest(sfile.read_bytes())
            if live_dg != claimed_sdig:
                _fail(
                    codec.ReasonCode.INPUT_STALE,
                    stage=codec.Stage.CONTENT,
                    entity_id=entity_id,
                    expected={"path": spath, "raw_digest": claimed_sdig, "return_stage": "3A"},
                    actual={"path": spath, "raw_digest": live_dg, "return_stage": "3A"},
                    resume_ref=spath,
                )
    return target_rel


def verify_3a_source_proofs(
    root: Path,
    *,
    loaded_plans: dict[str, tuple[dict[str, Any], bytes, dict[str, Any]]],
    sealed_digests: dict[str, str],
    explicit_audit_refs: list[str] | None = None,
    require_full_audit_proof: bool = False,
    entity_id: str,
) -> dict[str, Any]:
    """Read-only verify 3A source identities and proofs without rerunning 3A or invoking models."""
    source_revisions: list[str] = []
    verified_proof_refs: list[str] = []
    verified_full_audit_refs: list[str] = []
    candidate_audit_refs: list[tuple[str, str | None]] = []
    expected_sources_by_path: dict[str, str] = {}
    expected_manifest_digests: set[str] = set()

    for ref_str in explicit_audit_refs or []:
        rel = preflight.path(str(ref_str).replace("\\", "/"))
        candidate_audit_refs.append((rel, None))

    for pid in sorted(loaded_plans):
        pref, _praw, pdoc = loaded_plans[pid]
        src_id = pdoc["source_identity"]
        srev = str(src_id["source_revision"])
        sdig = str(src_id["source_manifest_digest"])
        expected_manifest_digests.add(sdig)
        if srev not in source_revisions:
            source_revisions.append(srev)

        manifest_bytes_map = _read_owned_ref_bytes(
            root,
            src_id["manifest_ref"],
            sealed_digests=sealed_digests,
            allow_sealed_logs=True,
            entity_id=entity_id,
            return_stage="3A",
        )
        ledger_bytes_map = _read_owned_ref_bytes(
            root,
            src_id["ledger_ref"],
            sealed_digests=sealed_digests,
            allow_sealed_logs=True,
            entity_id=entity_id,
            return_stage="3A",
        )

        # Verify manifest & ledger internal bindings and live non-log source files when present on disk.
        manifest_path = preflight.path(src_id["manifest_ref"]["ref"].partition("#")[0])
        ledger_path = preflight.path(src_id["ledger_ref"]["ref"].partition("#")[0])
        m_raw = manifest_bytes_map.get(manifest_path)
        l_raw = ledger_bytes_map.get(ledger_path)

        block_ids: set[str] | None = None
        if m_raw is not None:
            m_doc = codec.strict_json_loads(m_raw)
            if type(m_doc) is not dict:
                _fail(
                    codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
                    stage=codec.Stage.SCHEMA,
                    entity_id=entity_id,
                    expected={"schema": "source-manifest object", "return_stage": "3A"},
                    actual={"type": type(m_doc).__name__, "return_stage": "3A"},
                    resume_ref=manifest_path,
                )
            if str(m_doc.get("source_revision") or "") != srev:
                _fail(
                    codec.ReasonCode.INPUT_STALE,
                    stage=codec.Stage.CONTENT,
                    entity_id=entity_id,
                    expected={"source_revision": srev, "return_stage": "3A"},
                    actual={"source_revision": m_doc.get("source_revision"), "return_stage": "3A"},
                    resume_ref=manifest_path,
                )
            if str(m_doc.get("manifest_sha256") or "") != sdig:
                _fail(
                    codec.ReasonCode.DIGEST_MISMATCH,
                    stage=codec.Stage.CONTENT,
                    entity_id=entity_id,
                    expected={"manifest_sha256": sdig, "return_stage": "3A"},
                    actual={"manifest_sha256": m_doc.get("manifest_sha256"), "return_stage": "3A"},
                    resume_ref=manifest_path,
                )
            for srow in m_doc.get("sources") or []:
                if type(srow) is not dict or not srow.get("path"):
                    continue
                srel = preflight.path(str(srow["path"]).replace("\\", "/"))
                sfile = root / srel
                if not sfile.is_file():
                    _fail(
                        codec.ReasonCode.FILE_NOT_FOUND,
                        stage=codec.Stage.PATH,
                        entity_id=entity_id,
                        expected={"source_path": srel, "return_stage": "3A"},
                        actual={"exists": False, "return_stage": "3A"},
                        resume_ref=srel,
                    )
                live_sdig = codec.raw_digest(sfile.read_bytes())
                expected_sdig = str(srow.get("sha256") or "")
                if expected_sdig and live_sdig != expected_sdig:
                    _fail(
                        codec.ReasonCode.INPUT_STALE,
                        stage=codec.Stage.CONTENT,
                        entity_id=entity_id,
                        expected={"path": srel, "sha256": expected_sdig, "return_stage": "3A"},
                        actual={"path": srel, "sha256": live_sdig, "return_stage": "3A"},
                        resume_ref=srel,
                    )
                expected_sources_by_path[srel] = live_sdig

        if l_raw is not None:
            l_doc = codec.strict_json_loads(l_raw)
            if type(l_doc) is not dict:
                _fail(
                    codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
                    stage=codec.Stage.SCHEMA,
                    entity_id=entity_id,
                    expected={"schema": "source-ledger object", "return_stage": "3A"},
                    actual={"type": type(l_doc).__name__, "return_stage": "3A"},
                    resume_ref=ledger_path,
                )
            if str(l_doc.get("source_revision") or "") != srev:
                _fail(
                    codec.ReasonCode.INPUT_STALE,
                    stage=codec.Stage.CONTENT,
                    entity_id=entity_id,
                    expected={"source_revision": srev, "return_stage": "3A"},
                    actual={"source_revision": l_doc.get("source_revision"), "return_stage": "3A"},
                    resume_ref=ledger_path,
                )
            if str(l_doc.get("source_manifest_sha256") or "") != sdig:
                _fail(
                    codec.ReasonCode.DIGEST_MISMATCH,
                    stage=codec.Stage.CONTENT,
                    entity_id=entity_id,
                    expected={"source_manifest_sha256": sdig, "return_stage": "3A"},
                    actual={"source_manifest_sha256": l_doc.get("source_manifest_sha256"), "return_stage": "3A"},
                    resume_ref=ledger_path,
                )
            block_ids = {
                str(b.get("block_id"))
                for b in (l_doc.get("blocks") or [])
                if type(b) is dict and str(b.get("block_id") or "").strip()
            }

        if block_ids is not None:
            for req in pdoc.get("requirements") or []:
                for bid in req.get("source_block_ids") or []:
                    if str(bid) not in block_ids:
                        _fail(
                            codec.ReasonCode.UNRESOLVED_REFERENCE,
                            stage=codec.Stage.REFERENCE,
                            entity_id=entity_id,
                            expected={"block_id": bid, "ledger": ledger_path, "return_stage": "3A"},
                            actual={"missing_block_id": bid, "requirement_id": req.get("requirement_id"), "return_stage": "3A"},
                            resume_ref=pref["path"],
                        )

        # Verify adoption_proof_refs (and discover any full 3A source_audit proofs).
        proof_refs = list(pdoc.get("adoption_proof_refs") or [])
        if not proof_refs:
            _fail(
                codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected={"adoption_proof_refs": "nonempty", "return_stage": "3A"},
                actual={"plan_id": pid, "return_stage": "3A"},
                resume_ref=pref["path"],
            )
        for proof_ref in proof_refs:
            pbytes = _read_owned_ref_bytes(
                root,
                proof_ref,
                sealed_digests=sealed_digests,
                allow_sealed_logs=True,
                entity_id=entity_id,
                return_stage="3A",
            )
            ref_path = preflight.path(proof_ref["ref"].partition("#")[0])
            if ref_path not in verified_proof_refs:
                verified_proof_refs.append(ref_path)
            raw_doc = pbytes.get(ref_path)
            is_audit_candidate = (
                proof_ref.get("owner") == "source_audit"
                or "/b-route-source-audit/" in ref_path
            )
            if not is_audit_candidate and raw_doc is not None and ref_path.endswith(".json"):
                try:
                    parsed = codec.strict_json_loads(raw_doc)
                    if type(parsed) is dict and parsed.get("schema_version") == source_audit.SCHEMA:
                        is_audit_candidate = True
                except codec.CodecError:
                    pass
            if is_audit_candidate and raw_doc is not None:
                parsed = codec.strict_json_loads(raw_doc)
                scope_hint = parsed.get("scope_id") if type(parsed) is dict else None
                candidate_audit_refs.append((ref_path, scope_hint))

    # Read-only verify any discovered or explicit full 3A source_audit proofs.
    seen_audit: set[str] = set()
    for rel_ref, scope_hint in candidate_audit_refs:
        if rel_ref in seen_audit:
            continue
        seen_audit.add(rel_ref)
        verified_rel = _verify_3a_source_audit(
            root,
            rel_ref,
            scope_hint=scope_hint,
            expected_sources_by_path=expected_sources_by_path,
            expected_manifest_digests=expected_manifest_digests,
            entity_id=entity_id,
        )
        if verified_rel not in verified_full_audit_refs:
            verified_full_audit_refs.append(verified_rel)

    if require_full_audit_proof and not verified_full_audit_refs:
        _fail(
            codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected={"full_3a_source_audit_proof": True, "return_stage": "3A"},
            actual={"verified_full_audit_refs": [], "return_stage": "3A"},
            resume_ref=None,
        )

    reuse_reason = (
        "read_only_3a_full_audit_proof_reused"
        if verified_full_audit_refs
        else "read_only_committed_3a_source_identity_and_proof_reused"
    )
    return {
        "reused": True,
        "reuse_reason": reuse_reason,
        "source_revisions": sorted(source_revisions),
        "verified_proof_refs": sorted(verified_proof_refs),
        "verified_full_audit_refs": sorted(verified_full_audit_refs),
        "reused_3a_proof_count": len(verified_full_audit_refs) or len(verified_proof_refs),
        "model_invocation_count": 0,
    }


def _extract_authority_scope_for_b_task(
    root: Path,
    *,
    task_id: int,
    master_row: dict[str, Any],
    view_rows: list[dict[str, Any]],
    loaded_bindings: dict[str, tuple[dict[str, Any], bytes, dict[str, Any], dict[str, Any]]],
    decisions: dict[str, Any],
    planned_ref_paths: set[str],
    other_verif_paths: set[str] | None = None,
    extra_contract_refs: set[str] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Build complete ADR/Overlay/Contract authority scope and detect missing/non-BCL issues."""
    overlays: dict[str, dict[str, Any]] = {}
    contracts: dict[str, dict[str, Any]] = {}
    adrs: dict[str, dict[str, Any]] = {}
    errors: list[dict[str, Any]] = []
    known_other_verif = set(other_verif_paths or ())

    overlay_refs: set[str] = set()
    contract_refs: set[str] = set(extra_contract_refs or ())
    adr_refs: set[str] = set()

    if type(master_row.get("overlay")) is str and master_row["overlay"].strip():
        overlay_refs.add(master_row["overlay"].strip().replace("\\", "/"))
    for cref in master_row.get("contractRefs") or []:
        if type(cref) is str and cref.strip():
            contract_refs.add(cref.strip().replace("\\", "/"))

    for vrow in view_rows:
        for oref in vrow.get("overlay_refs") or []:
            if type(oref) is str and oref.strip():
                overlay_refs.add(oref.strip().replace("\\", "/"))
        for cref in vrow.get("contractRefs") or []:
            if type(cref) is str and cref.strip():
                contract_refs.add(cref.strip().replace("\\", "/"))
        for aref in vrow.get("adr_refs") or []:
            if type(aref) is str and aref.strip():
                adr_refs.add(aref.strip().upper())

    for _pid, (_bref, _braw, bdoc, _mapping) in loaded_bindings.items():
        for obj in bdoc.get("implementation_objects") or []:
            if task_id not in (obj.get("responsible_task_ids") or []):
                continue
            tref = obj.get("target_ref")
            if type(tref) is not dict:
                continue
            owner = tref.get("owner")
            ref_val = str(tref.get("ref") or "").strip().replace("\\", "/")
            if not ref_val:
                continue
            if owner == "overlay":
                overlay_refs.add(ref_val)
            elif owner == "contract":
                contract_refs.add(ref_val)
            elif owner == "adr":
                adr_refs.add(ref_val)

    for link in decisions.get("acceptance_links") or []:
        if type(link) is not dict:
            continue
        for aref in link.get("authority_refs") or []:
            tok = str(aref or "").strip().replace("\\", "/")
            if not tok or tok in known_other_verif:
                continue
            if _ADR_TOKEN_RE.fullmatch(tok):
                adr_refs.add(tok.upper())
            elif tok.startswith("docs/adr/"):
                adr_refs.add(tok)
            elif tok.startswith("docs/architecture/overlays/"):
                overlay_refs.add(tok)
            elif tok.startswith("Game.Core/Contracts/") or ("/" not in tok and "." in tok):
                contract_refs.add(tok)

    # Resolve overlays & harvest ADRs referenced inside them.
    for orel in sorted(overlay_refs):
        opath = root / orel
        if not opath.is_file():
            if orel in planned_ref_paths:
                overlays[orel] = {"ref": orel, "sha256": None, "planned": True}
            else:
                errors.append(
                    {
                        "finding_type": "authority_scope",
                        "status": "overlay_missing",
                        "authority_type": "overlay",
                        "authority_ref": orel,
                        "priority": "P1",
                        "return_stage": "4",
                        "reason": f"overlay file missing: {orel}",
                    }
                )
            continue
        otext = opath.read_text(encoding="utf-8")
        overlays[orel] = {"ref": orel, "sha256": "sha256:" + _sha_text(otext), "planned": False}
        for tok in sorted(set(_ADR_TOKEN_RE.findall(otext))):
            adr_refs.add(tok.upper())

    # Resolve ADRs.
    for aref in sorted(adr_refs):
        if _ADR_TOKEN_RE.fullmatch(aref):
            canonical = aref.upper()
            matches = sorted((root / "docs/adr").glob(canonical + "*.md")) if (root / "docs/adr").is_dir() else []
            if not matches:
                errors.append(
                    {
                        "finding_type": "authority_scope",
                        "status": "adr_missing",
                        "authority_type": "adr",
                        "authority_ref": canonical,
                        "priority": "P1",
                        "return_stage": "4",
                        "reason": f"ADR file missing for {canonical}",
                    }
                )
                continue
            adr_path = matches[0]
            adr_text = adr_path.read_text(encoding="utf-8")
            adrs[canonical] = {
                "ref": canonical,
                "path": adr_path.relative_to(root).as_posix(),
                "sha256": "sha256:" + _sha_text(adr_text),
            }
        else:
            adr_path = root / aref
            if not adr_path.is_file():
                errors.append(
                    {
                        "finding_type": "authority_scope",
                        "status": "adr_missing",
                        "authority_type": "adr",
                        "authority_ref": aref,
                        "priority": "P1",
                        "return_stage": "4",
                        "reason": f"ADR file missing: {aref}",
                    }
                )
                continue
            adr_text = adr_path.read_text(encoding="utf-8")
            adrs[aref] = {
                "ref": aref,
                "path": aref,
                "sha256": "sha256:" + _sha_text(adr_text),
            }

    # Resolve Contracts and verify BCL-only rule on Game.Core/Contracts/**.
    contract_sources = records._Bytes({}, root).contracts() if (root / "Game.Core/Contracts").is_dir() else {}
    for cref in sorted(contract_refs):
        if cref.startswith("Game.Core/Contracts/"):
            cpath = root / cref
            if not cpath.is_file():
                if cref in planned_ref_paths:
                    contracts[cref] = {"ref": cref, "path": cref, "sha256": None, "planned": True}
                else:
                    errors.append(
                        {
                            "finding_type": "authority_scope",
                            "status": "contract_missing",
                            "authority_type": "contract",
                            "authority_ref": cref,
                            "priority": "P1",
                            "return_stage": "4",
                            "reason": f"contract file missing: {cref}",
                        }
                    )
                continue
            ctext = cpath.read_text(encoding="utf-8")
            if _GODOT_USING_RE.search(ctext):
                errors.append(
                    {
                        "finding_type": "authority_scope",
                        "status": "contract_not_bcl_only",
                        "authority_type": "contract",
                        "authority_ref": cref,
                        "priority": "P1",
                        "return_stage": "4",
                        "reason": f"Game.Core/Contracts file must be BCL-only without Godot references: {cref}",
                    }
                )
            contracts[cref] = {"ref": cref, "path": cref, "sha256": "sha256:" + _sha_text(ctext), "planned": False}
        else:
            bound = contract_bindings.resolve_contract(root, cref, sources=contract_sources) if contract_sources else None
            if bound is None:
                if cref in planned_ref_paths:
                    contracts[cref] = {"ref": cref, "sha256": None, "planned": True}
                else:
                    errors.append(
                        {
                            "finding_type": "authority_scope",
                            "status": "contract_missing",
                            "authority_type": "contract",
                            "authority_ref": cref,
                            "priority": "P1",
                            "return_stage": "4",
                            "reason": f"contract reference unresolved: {cref}",
                        }
                    )
                continue
            for brow in bound.get("bindings") or []:
                bpath = root / brow["path"]
                if bpath.is_file() and _GODOT_USING_RE.search(bpath.read_text(encoding="utf-8")):
                    errors.append(
                        {
                            "finding_type": "authority_scope",
                            "status": "contract_not_bcl_only",
                            "authority_type": "contract",
                            "authority_ref": cref,
                            "priority": "P1",
                            "return_stage": "4",
                            "reason": f"bound contract file must be BCL-only: {brow['path']}",
                        }
                    )
            contracts[cref] = {
                "ref": cref,
                "sha256": bound.get("sha256"),
                "bindings": bound.get("bindings", []),
                "planned": False,
            }

    scope = {
        "overlays": [overlays[k] for k in sorted(overlays)],
        "contracts": [contracts[k] for k in sorted(contracts)],
        "adrs": [adrs[k] for k in sorted(adrs)],
    }
    return scope, errors


def _validate_technical_debt_findings(
    task_id: int,
    findings: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Validate that all findings are eligible P2..P4 non-P1-floor items without touching disk."""
    normalized: list[dict[str, str]] = []
    for item in findings:
        sev = str(item.get("priority") or item.get("severity") or "").strip().upper()
        cat = str(item.get("category") or item.get("finding_type") or "chapter5").strip().lower()
        if sev in P0_P1_SEVERITIES or cat in P1_FLOOR_CATEGORIES or sev not in DEFERRABLE_SEVERITIES:
            _fail(
                codec.ReasonCode.SEMANTIC_ERROR,
                stage=codec.Stage.CONTENT,
                entity_id=str(task_id),
                expected="only P2/P3/P4 non-P1-floor findings may be recorded in technical-debt.md",
                actual={"severity": sev, "category": cat, "finding_id": item.get("finding_id")},
                resume_ref=TECHNICAL_DEBT_PATH,
            )
        fid = str(item.get("finding_id") or "").strip()
        msg = str(item.get("reason") or item.get("message") or item.get("status") or "").strip()
        if not fid:
            fid = _stable_finding_id("ch5", cat, msg, str(task_id))
        normalized.append({"finding_id": fid, "severity": sev, "category": cat, "message": msg or "deferred concern"})
    normalized.sort(key=lambda row: row["finding_id"])
    return normalized


def record_technical_debt_findings(
    root: Path | str,
    task_id: int,
    findings: list[dict[str, Any]],
) -> list[str]:
    """Record eligible P2..P4 findings in docs/technical-debt.md; forbid P0/P1 parking."""
    root_path = Path(root).resolve()
    debt_path = root_path / TECHNICAL_DEBT_PATH
    normalized = _validate_technical_debt_findings(task_id, findings)
    existing = debt_path.read_text(encoding="utf-8") if debt_path.is_file() else "# Technical Debt Register\n\n"
    existing_norm = existing.replace("\r\n", "\n")

    section_lines = [f"### Task {task_id} (B-route Chapter 5 Concerns)"]
    for row in normalized:
        section_lines.append(
            f"- [{row['severity']}] ({row['category']}) {row['message']} {{finding_id={row['finding_id']}}}"
        )
    task_section = "\n".join(section_lines) + "\n"

    if _DEBT_BEGIN in existing_norm and _DEBT_END in existing_norm:
        pre, rest = existing_norm.split(_DEBT_BEGIN, 1)
        body, post = rest.split(_DEBT_END, 1)
        body = body.strip("\n")
        pattern = re.compile(
            rf"(?ms)^### Task {task_id} \(B-route Chapter 5 Concerns\)\n.*?(?=^### Task \d+ |\Z)"
        )
        if pattern.search(body):
            replacement = task_section + "\n"
            new_body = pattern.sub(lambda _: replacement, body).rstrip("\n")
        else:
            new_body = (body + "\n\n" + task_section.rstrip("\n")).strip("\n") if body else task_section.rstrip("\n")
        updated = f"{pre}{_DEBT_BEGIN}\n{new_body}\n{_DEBT_END}{post}"
    else:
        suffix = "\n" if existing_norm.endswith("\n") else "\n\n"
        updated = (
            existing_norm
            + suffix
            + f"{_DEBT_BEGIN}\n{task_section.rstrip()}\n{_DEBT_END}\n"
        )

    debt_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = debt_path.with_name(debt_path.name + ".tmp")
    try:
        tmp.write_text(updated, encoding="utf-8", newline="\n")
        tmp.replace(debt_path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return [row["finding_id"] for row in normalized]


def verify_technical_debt_recorded(
    root: Path | str,
    task_id: int,
    findings: list[dict[str, Any]],
) -> tuple[bool, list[str], list[str]]:
    """Verify every P2..P4 concern finding_id is recorded in this Task's managed section of docs/technical-debt.md."""
    root_path = Path(root).resolve()
    debt_path = root_path / TECHNICAL_DEBT_PATH
    text = debt_path.read_text(encoding="utf-8").replace("\r\n", "\n") if debt_path.is_file() else ""
    task_section_text = ""
    if _DEBT_BEGIN in text and _DEBT_END in text:
        _pre, rest = text.split(_DEBT_BEGIN, 1)
        body, _post = rest.split(_DEBT_END, 1)
        pattern = re.compile(
            rf"(?ms)^### Task {task_id} \(B-route Chapter 5 Concerns\)\n(.*?)(?=^### Task \d+ |\Z)"
        )
        match = pattern.search(body)
        if match:
            task_section_text = match.group(1)
    recorded: list[str] = []
    missing: list[str] = []
    for item in findings:
        fid = str(item.get("finding_id") or "").strip()
        if not fid:
            missing.append("<missing-finding-id>")
            continue
        if f"{{finding_id={fid}}}" in task_section_text:
            recorded.append(fid)
        else:
            missing.append(fid)
    return (len(missing) == 0), sorted(set(recorded)), sorted(set(missing))


def _load_bound_manifests(
    root: Path,
    loaded_bindings: dict[str, tuple[dict[str, Any], bytes, dict[str, Any], dict[str, Any]]],
    *,
    entity_id: str,
) -> dict[str, dict[str, Any]]:
    """Load and validate all MVG manifests referenced by Stage-5 bindings."""
    manifests: dict[str, dict[str, Any]] = {}
    for _pid, (_bref, _braw, bdoc, _mapping) in loaded_bindings.items():
        for obl in bdoc.get("obligations") or []:
            for vref in obl.get("verification_refs") or []:
                if vref.get("owner") not in ("manifest", "mvg_manifest"):
                    continue
                for frow in vref.get("files") or []:
                    mrel = preflight.path(frow["path"])
                    if mrel in manifests:
                        continue
                    mpath = root / mrel
                    if not mpath.is_file():
                        _fail(
                            codec.ReasonCode.FILE_NOT_FOUND,
                            stage=codec.Stage.PATH,
                            entity_id=entity_id,
                            expected={"mvg_manifest": mrel, "return_stage": "5"},
                            actual={"exists": False, "return_stage": "5"},
                            resume_ref=mrel,
                        )
                    mraw = mpath.read_bytes()
                    actual_dg = codec.raw_digest(mraw)
                    if actual_dg != frow["raw_digest"]:
                        _fail(
                            codec.ReasonCode.INPUT_STALE,
                            stage=codec.Stage.CONTENT,
                            entity_id=entity_id,
                            expected={"path": mrel, "raw_digest": frow["raw_digest"], "return_stage": "5"},
                            actual={"path": mrel, "raw_digest": actual_dg, "return_stage": "5"},
                            resume_ref=mrel,
                        )
                    manifests[mrel] = codec.strict_json_loads(mraw)
    return manifests


def _compute_live_reverification(
    task_id: int,
    *,
    master_tasks: dict[int, dict[str, Any]],
    loaded_plans: dict[str, tuple[dict[str, Any], bytes, dict[str, Any]]],
    loaded_bindings: dict[str, tuple[dict[str, Any], bytes, dict[str, Any], dict[str, Any]]],
    manifests: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Compute live read-only old-done reverification status without copying status into authority."""
    live_status = str(master_tasks[task_id].get("status", "")).strip().lower()
    is_old_done = live_status == "done"
    has_new_obligation = False
    planned_test_ids: set[str] = set()
    requires_on_done = False

    for pid in sorted(loaded_bindings):
        _bref, _braw, bdoc, _mapping = loaded_bindings[pid]
        _pref, _praw, pdoc = loaded_plans[pid]
        if bdoc.get("stage") != "5":
            continue
        s5_sem = stage5_obls.extract_stage5_semantics(
            pdoc, bdoc, master_tasks=master_tasks, manifests=manifests
        )
        reverification_summary = s5_sem.get("reverification_summary")
        rows = reverification_summary.get("tasks") if type(reverification_summary) is dict else []
        for row in rows or []:
            if row["task_id"] != task_id:
                continue
            if row.get("has_new_obligation"):
                has_new_obligation = True
            planned_test_ids.update(row.get("planned_test_ids") or [])
            if row.get("requires_reverification_on_done") or row.get("requires_reverification"):
                requires_on_done = True

    requires_reverification = bool(is_old_done and requires_on_done)
    return {
        "live_status": live_status,
        "is_old_done": is_old_done,
        "has_new_obligation": has_new_obligation,
        "planned_test_ids": sorted(planned_test_ids),
        "requires_reverification_on_done": requires_on_done,
        "requires_chapter6_reverification": requires_reverification,
        "old_done_covers_new_obligations": False,
    }


def _build_minimal_input_set_baseline(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": input_set.SCHEMA,
        "task_id": snapshot["task_id"],
        "route": snapshot["route"],
        "uses_candidate_binding": snapshot["uses_candidate_binding"],
        "input_set_digest": snapshot["input_set_digest"],
        "items": deepcopy(snapshot["items"]),
    }


def _extract_return_stage_from_diag(diag: dict[str, Any]) -> str:
    for field in ("actual", "expected"):
        val = diag.get(field)
        if type(val) is dict and val.get("return_stage") in STAGE_RANK:
            return str(val["return_stage"])
    inferred = input_set._stage_for_diag(diag)
    return inferred if inferred in STAGE_RANK else "5"


def _blocked_response(
    *,
    task_id: int | None,
    operation: str | None,
    diagnostics: list[dict[str, Any]],
    return_stage: str | None,
    started: float,
    route: str = "blocked",
    reconciliation_path: str | None = None,
    readiness_path: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    elapsed = round(max(0.0, time.monotonic() - started), 6)
    inferred = return_stage or (_extract_return_stage_from_diag(diagnostics[0]) if diagnostics else "5")
    payload: dict[str, Any] = {
        "schema_version": B_ROUTE_SCHEMA,
        "ok": False,
        "status": "blocked",
        "route": route,
        "task_id": task_id,
        "operation": operation,
        "readiness": "BLOCKED",
        "closure_allowed": False,
        "requires_chapter6_reverification": False,
        "old_done_covers_new_obligations": False,
        "input_set_digest": None,
        "applicable_set_digest": None,
        "scope_ids": [],
        "plan_refs": [],
        "binding_refs": [],
        "reconciliation_sha256": None,
        "return_stage": inferred,
        "metrics": {
            "active_elapsed_seconds": elapsed,
            "model_invocation_count": 0,
            "source_audit_reused": False,
            "reused_3a_proof_count": 0,
            "return_stage": inferred,
        },
        "reconciliation_path": reconciliation_path,
        "readiness_path": readiness_path,
        "diagnostics": diagnostics,
        **INVARIANT_FLAGS,
    }
    if extra:
        payload.update(extra)
    payload["runtime_verified"] = False
    payload["default_b_enabled"] = False
    return payload


def reconcile_b_route_chapter5(
    root: Path | str,
    *,
    task_id: Any,
    decisions: dict[str, Any] | str | Path,
    operation: str | None = None,
    audit_refs: list[str] | None = None,
    out_path: Path | str | None = None,
    readiness_path: Path | str | None = None,
    write_artifacts: bool = True,
    write_latest: bool = True,
    record_technical_debt: bool = False,
    require_full_audit_proof: bool = False,
) -> dict[str, Any]:
    """Run B-route Chapter 5 same-source reconciliation under guarded_input_set and form readiness."""
    started = time.monotonic()
    validated_tid: int | None = None
    validated_op: str | None = None
    try:
        root_path = task_resolver._validate_root(Path(root))
        validated_tid = codec.validate_task_id(task_id)
        validated_op = task_resolver._validate_operation(operation)
        entity_id = str(validated_tid)

        if type(decisions) is dict:
            decisions_doc = deepcopy(decisions)
        else:
            d_rel = preflight.path(str(decisions).replace("\\", "/"))
            d_file = root_path / d_rel
            if not d_file.is_file():
                _fail(
                    codec.ReasonCode.FILE_NOT_FOUND,
                    stage=codec.Stage.PATH,
                    entity_id=entity_id,
                    expected={"decisions_file": d_rel, "return_stage": "5"},
                    actual={"exists": False, "return_stage": "5"},
                    resume_ref=d_rel,
                )
            decisions_doc = codec.strict_json_loads(d_file.read_bytes())
        if type(decisions_doc) is not dict:
            _fail(
                codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
                stage=codec.Stage.SCHEMA,
                entity_id=entity_id,
                expected={"decisions": "JSON object", "return_stage": "5"},
                actual={"type": type(decisions_doc).__name__, "return_stage": "5"},
            )

        if out_path is not None:
            out_file, out_rel = _validate_log_path(root_path, out_path, require_logs=True)
        else:
            out_file, out_rel = _validate_log_path(
                root_path, (DEFAULT_RECONCILIATION_DIR / f"task-{validated_tid}.json").as_posix(), require_logs=True
            )
        if readiness_path is not None:
            readiness_file, rdy_rel = _validate_log_path(root_path, readiness_path, require_logs=True)
        else:
            readiness_file, rdy_rel = _validate_log_path(
                root_path, (DEFAULT_READINESS_DIR / f"task-{validated_tid}.json").as_posix(), require_logs=True
            )
    except codec.CodecError as err:
        d = err.diagnostic.to_dict()
        if d.get("entity_id") is None and validated_tid is not None:
            d["entity_id"] = str(validated_tid)
        return _blocked_response(
            task_id=validated_tid,
            operation=validated_op,
            diagnostics=[d],
            return_stage=_extract_return_stage_from_diag(d),
            started=started,
        )

    # 1. Story 3.3 unified Task origin check: MUST classify as route="B".
    origin = task_resolver.resolve_task_origin(root_path, validated_tid, operation=validated_op)
    if not origin["ok"] or not origin["stable"] or origin["route"] != "B":
        diags = list(origin.get("diagnostics") or [])
        if not diags:
            diags.append(
                _diag(
                    codec.ReasonCode.CONFLICT,
                    stage=codec.Stage.BUNDLE,
                    entity_id=entity_id,
                    expected={"route": "B", "return_stage": "3C"},
                    actual={"route": origin.get("route"), "return_stage": "3C"},
                    resume_ref=task_resolver.ORIGINS_PATH,
                )
            )
        rstage = _earliest_stage([_extract_return_stage_from_diag(d) for d in diags]) or "3C"
        return _blocked_response(
            task_id=validated_tid,
            operation=validated_op,
            diagnostics=diags,
            return_stage=rstage,
            started=started,
            route=str(origin.get("route") or "blocked"),
        )

    # 2. Acquire Story 3.5 guarded_input_set business scope lease (review_only=True, zero global writer lock).
    try:
        with input_set.guarded_input_set(
            root_path,
            validated_tid,
            operation=validated_op,
        ) as handle:
            if handle.uses_global_writer_lock:
                _fail(
                    codec.ReasonCode.CONFLICT,
                    stage=codec.Stage.BUNDLE,
                    entity_id=entity_id,
                    expected={"uses_global_writer_lock": False, "return_stage": "5"},
                    actual={"uses_global_writer_lock": True, "return_stage": "5"},
                )
            snap = handle.snapshot
            if snap.get("uses_candidate_binding") is True:
                _fail(
                    codec.ReasonCode.UNPUBLISHED,
                    stage=codec.Stage.BUNDLE,
                    entity_id=entity_id,
                    expected={"committed_bindings_only": True, "return_stage": "5"},
                    actual={"uses_candidate_binding": True, "return_stage": "5"},
                )

            # Re-verify Task origin INSIDE the guarded_input_set lease to eliminate TOCTOU drift.
            origin = task_resolver.resolve_task_origin(root_path, validated_tid, operation=validated_op)
            if (
                not origin["ok"]
                or not origin["stable"]
                or origin["route"] != "B"
                or origin.get("applicable_set_digest") != snap.get("applicable_set_digest")
            ):
                _fail(
                    codec.ReasonCode.INPUT_STALE,
                    stage=codec.Stage.BUNDLE,
                    entity_id=entity_id,
                    expected={
                        "route": "B",
                        "applicable_set_digest": snap.get("applicable_set_digest"),
                        "return_stage": "3C",
                    },
                    actual={
                        "route": origin.get("route"),
                        "applicable_set_digest": origin.get("applicable_set_digest"),
                        "return_stage": "3C",
                    },
                    resume_ref=task_resolver.ORIGINS_PATH,
                )

            (
                loaded_plans,
                loaded_bindings,
                sealed_digests,
                views,
                master_tasks,
                back_by_tid,
                gameplay_by_tid,
            ) = _load_plan_and_binding_bundle(root_path, origin)

            # 3. Every applicable binding MUST be committed stage="5"; otherwise block with return_stage 4 or 5.
            stage_diags: list[dict[str, Any]] = []
            stage_returns: list[str] = []
            for pid in sorted(loaded_bindings):
                bref, _braw, bdoc, _mapping = loaded_bindings[pid]
                bstage = str(bdoc.get("stage") or "")
                if bstage != "5":
                    rstage = "4" if bstage == "3C" else "5"
                    stage_returns.append(rstage)
                    stage_diags.append(
                        _diag(
                            codec.ReasonCode.SEMANTIC_ERROR,
                            stage=codec.Stage.BUNDLE,
                            entity_id=entity_id,
                            expected={"binding_stage": "5", "plan_id": pid, "return_stage": rstage},
                            actual={"binding_stage": bstage, "plan_id": pid, "return_stage": rstage},
                            resume_ref=bref["path"],
                        )
                    )
            if stage_diags:
                return _blocked_response(
                    task_id=validated_tid,
                    operation=validated_op,
                    diagnostics=stage_diags,
                    return_stage=_earliest_stage(stage_returns) or "5",
                    started=started,
                    route="B",
                )

            # 4. Read-only verify 3A source identities & proofs (reuse unchanged 3A, zero model calls).
            audit_summary = verify_3a_source_proofs(
                root_path,
                loaded_plans=loaded_plans,
                sealed_digests=sealed_digests,
                explicit_audit_refs=audit_refs,
                require_full_audit_proof=require_full_audit_proof,
                entity_id=entity_id,
            )

            # 5. Load bound MVG manifests and extract Stage-4 & Stage-5 semantics across all applicable plans.
            bound_manifests = _load_bound_manifests(root_path, loaded_bindings, entity_id=entity_id)
            master_row = master_tasks[validated_tid]
            view_rows = [*back_by_tid.get(validated_tid, []), *gameplay_by_tid.get(validated_tid, [])]

            all_findings: list[dict[str, Any]] = []
            blocking_findings: list[dict[str, Any]] = []
            concern_findings: list[dict[str, Any]] = []
            diagnostics: list[dict[str, Any]] = []
            return_stages: list[str] = []

            def add_blocking(
                finding: dict[str, Any],
                *,
                reason_code: codec.ReasonCode = codec.ReasonCode.SEMANTIC_ERROR,
                rstage: str = "5",
                resume_ref: str | None = None,
            ) -> None:
                row = dict(finding)
                row.setdefault("priority", "P1")
                row["return_stage"] = rstage
                row.setdefault(
                    "finding_id",
                    _stable_finding_id(
                        "ch5",
                        str(row.get("category") or row.get("finding_type") or "blocking"),
                        str(row.get("reason") or row.get("status") or ""),
                        entity_id,
                    ),
                )
                all_findings.append(row)
                blocking_findings.append(row)
                return_stages.append(rstage)
                diagnostics.append(
                    _diag(
                        reason_code,
                        stage=codec.Stage.CONTENT,
                        entity_id=entity_id,
                        expected={"status": "resolved", "return_stage": rstage},
                        actual={"finding": row.get("status"), "reason": row.get("reason"), "return_stage": rstage},
                        resume_ref=resume_ref,
                    )
                )

            def add_concern(finding: dict[str, Any], *, rstage: str = "5") -> None:
                row = dict(finding)
                sev = str(row.get("priority") or row.get("severity") or "P2").upper()
                cat = str(row.get("category") or row.get("finding_type") or "concern").lower()
                if sev in P0_P1_SEVERITIES or cat in P1_FLOOR_CATEGORIES:
                    add_blocking(row, rstage=rstage)
                    return
                row["priority"] = sev if sev in DEFERRABLE_SEVERITIES else "P2"
                row["return_stage"] = rstage
                row.setdefault(
                    "finding_id",
                    _stable_finding_id("ch5", cat, str(row.get("reason") or row.get("status") or ""), entity_id),
                )
                all_findings.append(row)
                concern_findings.append(row)

            # 5a. Forbidden bypass / quality downgrade checks.
            for fkey, fmsg in _FORBIDDEN_DOWNGRADE_KEYS.items():
                if decisions_doc.get(fkey):
                    add_blocking(
                        {
                            "finding_type": "quality_floor",
                            "category": "artifact-integrity",
                            "status": f"forbidden_{fkey}",
                            "priority": "P0",
                            "reason": fmsg,
                        },
                        reason_code=codec.ReasonCode.SEMANTIC_ERROR,
                        rstage="5",
                    )

            fix_through = str(decisions_doc.get("fix_through") or "P1").strip().upper()
            if fix_through not in P0_P1_SEVERITIES:
                # fix_through must at least cover P1 (P1, P2, P3, P4 are valid thresholds; only "none" or invalid weakens P1 floor).
                if fix_through not in ALL_SEVERITIES:
                    add_blocking(
                        {
                            "finding_type": "quality_floor",
                            "category": "artifact-integrity",
                            "status": "invalid_fix_through_threshold",
                            "priority": "P0",
                            "reason": f"invalid or weakened fix_through threshold: {fix_through}",
                        },
                        rstage="5",
                    )
            if fix_through == "P0":
                add_blocking(
                    {
                        "finding_type": "quality_floor",
                        "category": "artifact-integrity",
                        "status": "p1_floor_lowered",
                        "priority": "P0",
                        "reason": "fix_through=P0 lowers the mandatory P1 floor",
                    },
                    rstage="5",
                )

            # 5b. Validate Stage-4 planned objects, Stage-5 planned tests, and per-plan/per-task Requirement scoping.
            planned_objects: list[dict[str, Any]] = []
            planned_tests: list[dict[str, Any]] = []
            planned_obj_paths: set[str] = set()
            planned_test_paths: set[str] = set()
            bound_manifest_test_paths: set[str] = set()
            applicable_req_ids: set[str] = set()
            deferred_req_ids: set[str] = set()
            other_verif_paths: set[str] = set()
            extra_contract_refs: set[str] = set()
            task_roles: set[str] = set()
            required_prereq_deps: set[int] = set()
            unowned_handoffs: list[dict[str, Any]] = []
            handoff_count = 0
            self_lock_detected = False
            total_task_obls = 0
            task_assigned_test_ids: set[str] = set()
            all_mapped_dispositions: list[str] = []

            contract_sources = (
                records._Bytes({}, root_path).contracts()
                if (root_path / "Game.Core/Contracts").is_dir()
                else {}
            )

            for pid in sorted(loaded_bindings):
                bref, _braw, bdoc, mapping = loaded_bindings[pid]
                pref, _praw, pdoc = loaded_plans[pid]
                task_roles.update(mapping.get("roles") or [])
                plan_mapped_req_ids = sorted(set(mapping.get("requirement_ids") or []))
                applicable_req_ids.update(plan_mapped_req_ids)

                # Extract Stage-4 semantics cleanly.
                try:
                    s4_sem = ch4_binding.extract_stage4_semantics(pdoc, bdoc)
                except codec.CodecError as err:
                    add_blocking(
                        {
                            "finding_type": "stage4_semantics",
                            "status": "stage4_semantics_invalid",
                            "priority": "P1",
                            "reason": f"Stage-4 semantics invalid for {pid}: {err.diagnostic.actual}",
                        },
                        reason_code=err.diagnostic.reason_code,
                        rstage="4",
                        resume_ref=bref["path"],
                    )
                    s4_sem = {"planned_objects": [], "existing_objects": []}

                # Check planned objects completeness (no fake disk stubs required; target_ref may be null!).
                for pobj in s4_sem.get("planned_objects") or []:
                    if validated_tid not in (pobj.get("responsible_task_ids") or []):
                        continue
                    tref = pobj.get("target_ref")
                    tpath = str(tref.get("ref") or "").strip().replace("\\", "/") if type(tref) is dict else None
                    if not _is_substantive_text(pobj.get("expected_type")) or not pobj.get("later_checks"):
                        add_blocking(
                            {
                                "finding_type": "planned_object",
                                "category": "planned-only",
                                "status": "incomplete_planned_object",
                                "priority": "P1",
                                "object_id": pobj.get("id"),
                                "reason": f"planned object {pobj.get('id')} lacks explicit expected_type or later_checks",
                            },
                            rstage="4",
                            resume_ref=bref["path"],
                        )
                    else:
                        if tpath:
                            planned_obj_paths.add(tpath)
                        planned_objects.append(
                            {
                                "plan_id": pid,
                                "id": pobj["id"],
                                "kind": pobj["kind"],
                                "expected_type": pobj["expected_type"],
                                "later_checks": list(pobj["later_checks"]),
                                "target_ref": tpath,
                                "responsible_task_ids": list(pobj["responsible_task_ids"]),
                                "implementation_verified": False,
                                "runtime_verified": False,
                            }
                        )

                # Check every implementation object for unowned handoff, owner_task validity, or logical contract_ref.
                for obj in bdoc.get("implementation_objects") or []:
                    if validated_tid not in (obj.get("responsible_task_ids") or []):
                        continue
                    meta = ch4_binding._parse_prefixed_json(obj.get("lifecycle", ""), ch4_binding.STAGE4_LIFECYCLE_PREFIX) or {}
                    if meta.get("claimed_implemented") is True or meta.get("runtime_verified") is True:
                        if obj.get("availability") == "planned":
                            add_blocking(
                                {
                                    "finding_type": "planned_object",
                                    "category": "planned-only",
                                    "status": "planned_marked_implemented",
                                    "priority": "P0",
                                    "object_id": obj.get("id"),
                                    "reason": f"planned object {obj.get('id')} cannot claim implemented or runtime_verified",
                                },
                                rstage="4",
                                resume_ref=bref["path"],
                            )
                    obj_cref = str(meta.get("contract_ref") or "").strip().replace("\\", "/")
                    if obj_cref:
                        if (root_path / obj_cref).is_file() or obj_cref in planned_obj_paths:
                            if obj_cref.startswith("Game.Core/Contracts/"):
                                extra_contract_refs.add(obj_cref)
                        else:
                            bound_obj_c = (
                                contract_bindings.resolve_contract(root_path, obj_cref, sources=contract_sources)
                                if contract_sources
                                else None
                            )
                            if bound_obj_c is not None:
                                extra_contract_refs.add(obj_cref)
                            else:
                                add_blocking(
                                    {
                                        "finding_type": "authority_scope",
                                        "status": "contract_missing",
                                        "authority_type": "contract",
                                        "authority_ref": obj_cref,
                                        "object_id": obj.get("id"),
                                        "priority": "P1",
                                        "reason": f"Stage-4 object {obj.get('id')} contract_ref unresolved: {obj_cref}",
                                    },
                                    reason_code=codec.ReasonCode.UNRESOLVED_REFERENCE,
                                    rstage="4",
                                    resume_ref=bref["path"],
                                )
                    handoff = meta.get("handoff")
                    if type(handoff) is dict:
                        handoff_count += 1
                        owner_val = handoff.get("owner")
                        owner_task_val = handoff.get("owner_task")
                        owner_ok = (type(owner_val) is str and _is_substantive_text(owner_val)) or (
                            type(owner_task_val) is int and owner_task_val in master_tasks
                        )
                        if owner_task_val is not None and (
                            type(owner_task_val) is not int or owner_task_val not in master_tasks
                        ):
                            owner_ok = False
                        if not owner_ok:
                            unowned_handoffs.append({"plan_id": pid, "object_id": obj.get("id"), "handoff": handoff})
                            add_blocking(
                                {
                                    "finding_type": "handoff",
                                    "status": "unowned_handoff",
                                    "priority": "P1",
                                    "object_id": obj.get("id"),
                                    "reason": f"Stage-4 object {obj.get('id')} has an unowned or invalid handoff",
                                },
                                rstage="4",
                                resume_ref=bref["path"],
                            )

                # Check per-(plan_id, requirement_id) dispositions ONLY for THIS Task's mapped Requirements!
                verif_by_req = {r["requirement_id"]: r for r in pdoc.get("requirement_verification") or []}
                app_by_req = {r["requirement_id"]: r for r in pdoc.get("applicability") or []}
                ev_refs_by_key = {(r["owner"], r["ref"]): r for r in pdoc.get("evidence_source_refs") or []}
                obl_by_id = {o["id"]: o for o in bdoc.get("obligations") or []}
                task_obls = [obl_by_id[oid] for oid in (mapping.get("obligation_ids") or []) if oid in obl_by_id]
                total_task_obls += len(task_obls)
                for tobl in task_obls:
                    task_assigned_test_ids.update(str(t) for t in (tobl.get("test_ids") or []) if str(t).strip())

                for rid in plan_mapped_req_ids:
                    if rid not in verif_by_req or rid not in app_by_req:
                        add_blocking(
                            {
                                "finding_type": "requirement_disposition",
                                "status": "missing_3b_requirement_verification",
                                "priority": "P1",
                                "plan_id": pid,
                                "requirement_id": rid,
                                "reason": f"requirement {rid} in plan {pid} lacks 3B requirement_verification or applicability entry",
                            },
                            reason_code=codec.ReasonCode.UNRESOLVED_REFERENCE,
                            rstage="3B",
                            resume_ref=pref["path"],
                        )
                        continue
                    vrow = verif_by_req[rid]
                    app_row = app_by_req[rid]
                    disp = str(vrow.get("disposition") or "")
                    all_mapped_dispositions.append(disp)
                    if not _is_substantive_text(vrow.get("rationale")) or not _is_substantive_text(app_row.get("rationale")):
                        add_blocking(
                            {
                                "finding_type": "requirement_disposition",
                                "status": "invalid_requirement_rationale",
                                "priority": "P1",
                                "plan_id": pid,
                                "requirement_id": rid,
                                "reason": f"requirement {rid} in plan {pid} lacks substantive non-N/A 3B rationale",
                            },
                            rstage="3B",
                            resume_ref=pref["path"],
                        )
                    if disp == "source_gap":
                        add_blocking(
                            {
                                "finding_type": "requirement_disposition",
                                "status": "source_gap_unresolved",
                                "priority": "P1",
                                "plan_id": pid,
                                "requirement_id": rid,
                                "reason": f"requirement {rid} has unresolved source_gap disposition",
                            },
                            rstage="3A",
                            resume_ref=pref["path"],
                        )
                    elif disp == "deferred":
                        deferred_req_ids.add(rid)
                        if not _is_substantive_text(vrow.get("rationale")) or not vrow.get("authority_ref"):
                            add_blocking(
                                {
                                    "finding_type": "requirement_disposition",
                                    "status": "invalid_deferred_disposition",
                                    "priority": "P1",
                                    "plan_id": pid,
                                    "requirement_id": rid,
                                    "reason": f"deferred requirement {rid} lacks substantive rationale or authority_ref",
                                },
                                rstage="3B",
                                resume_ref=pref["path"],
                            )
                    elif disp == "other_verification":
                        if (
                            not _is_substantive_text(vrow.get("rationale"))
                            or not _is_substantive_text(app_row.get("rationale"))
                            or not vrow.get("sink_id")
                            or not vrow.get("verification_ref")
                        ):
                            add_blocking(
                                {
                                    "finding_type": "non_flow_disposition",
                                    "status": "invalid_non_flow_exemption",
                                    "priority": "P1",
                                    "plan_id": pid,
                                    "requirement_id": rid,
                                    "reason": f"non-Flow requirement {rid} lacks substantive 3B rationale or verification_ref",
                                },
                                rstage="5",
                                resume_ref=pref["path"],
                            )
                        else:
                            oref = ev_refs_by_key.get(("other_verification", vrow["verification_ref"]))
                            if oref is None:
                                add_blocking(
                                    {
                                        "finding_type": "non_flow_disposition",
                                        "status": "missing_other_verification_ref",
                                        "priority": "P1",
                                        "plan_id": pid,
                                        "requirement_id": rid,
                                        "reason": f"other_verification ref {vrow['verification_ref']} missing from evidence_source_refs",
                                    },
                                    rstage="5",
                                    resume_ref=pref["path"],
                                )
                            else:
                                for frow in oref.get("files") or []:
                                    other_verif_paths.add(preflight.path(frow["path"]))
                    elif disp == "flow":
                        # Verify a Stage-5 MVG manifest obligation covers this flow requirement!
                        fid = vrow.get("flow_id")
                        has_manifest_obl = any(
                            v.get("owner") in ("manifest", "mvg_manifest")
                            for tobl in task_obls
                            if (rid in tobl.get("requirement_ids", []) or fid in tobl.get("flow_ids", []))
                            for v in tobl.get("verification_refs", [])
                        )
                        if not has_manifest_obl:
                            add_blocking(
                                {
                                    "finding_type": "stage5_obligation",
                                    "status": "missing_mvg_manifest_obligation",
                                    "priority": "P1",
                                    "plan_id": pid,
                                    "requirement_id": rid,
                                    "flow_id": fid,
                                    "reason": f"Flow requirement {rid} ({fid}) lacks a bound Stage-5 MVG manifest obligation",
                                },
                                rstage="5",
                                resume_ref=bref["path"],
                            )

                # Extract Stage-5 semantics cleanly.
                try:
                    stage5_obls.extract_stage5_semantics(
                        pdoc, bdoc, master_tasks=master_tasks, manifests=bound_manifests
                    )
                except codec.CodecError as err:
                    add_blocking(
                        {
                            "finding_type": "stage5_obligations",
                            "status": "stage5_semantics_invalid",
                            "priority": "P1",
                            "reason": f"Stage-5 semantics invalid for {pid}: {err.diagnostic.actual}",
                        },
                        reason_code=err.diagnostic.reason_code,
                        rstage="5",
                        resume_ref=bref["path"],
                    )

            # Block empty mapped requirements + empty obligations unless this Task is integration_only_owner.
            if not applicable_req_ids and total_task_obls == 0 and "integration_only_owner" not in task_roles:
                add_blocking(
                    {
                        "finding_type": "requirement_scope",
                        "status": "empty_task_requirements_and_obligations",
                        "priority": "P1",
                        "reason": f"task {validated_tid} has empty mapped requirements and empty obligations without integration_only_owner role",
                    },
                    rstage="3C",
                    resume_ref=task_resolver.TRIPLET["master"],
                )

            # Anti-N/A free-text exemption check across all applicable plans.
            na_labels = list((origin.get("non_flow_summary") or {}).get("detected_non_authoritative_labels") or [])
            if na_labels:
                all_non_flow_valid = bool(all_mapped_dispositions) and all(
                    d == "other_verification" for d in all_mapped_dispositions
                )
                if not all_non_flow_valid:
                    add_blocking(
                        {
                            "finding_type": "non_flow_disposition",
                            "status": "non_authoritative_na_label_blocked",
                            "priority": "P1",
                            "labels": na_labels,
                            "reason": f"free-text N/A labels cannot exempt MVG/Chapter 5 obligations: {na_labels}",
                        },
                        rstage="5",
                        resume_ref=task_resolver.TRIPLET["master"],
                    )

            # 5c. Inspect bound MVG manifests: planned tests, three roles, handoff ownership, and no self-lock!
            mapping_by_tid_all: dict[int, set[str]] = {}
            for _pid, (_bref, _braw, bdoc, _mapping) in loaded_bindings.items():
                for mrow in bdoc.get("task_mappings") or []:
                    mapping_by_tid_all.setdefault(mrow["task_id"], set()).update(mrow.get("roles") or [])

            for mrel, mdoc in sorted(bound_manifests.items()):
                # Check dedicated integration_only_owner self-lock in coverage.blocking_task_ids.
                dedicated_owners = mvg_manifest._dedicated_integration_owner_task_ids(mdoc.get("flows") or [])
                declared_blockers = set((mdoc.get("coverage") or {}).get("blocking_task_ids") or [])
                self_locked = sorted(dedicated_owners & declared_blockers)
                if self_locked:
                    self_lock_detected = True
                    add_blocking(
                        {
                            "finding_type": "role_handoff",
                            "status": "integration_owner_self_lock",
                            "priority": "P1",
                            "manifest": mrel,
                            "self_locked_task_ids": self_locked,
                            "reason": f"integration_only_owner task(s) {self_locked} self-locked in coverage.blocking_task_ids",
                        },
                        reason_code=codec.ReasonCode.DIGEST_CYCLE,
                        rstage="5",
                        resume_ref=mrel,
                    )

                # Collect test IDs assigned to THIS Task via its applicable flows or Stage-5 obligations.
                applicable_flow_test_ids: set[str] = set(task_assigned_test_ids)
                for flow in mdoc.get("flows") or []:
                    if validated_tid not in (flow.get("task_ids") or []):
                        continue
                    applicable_flow_test_ids.update(str(t) for t in (flow.get("test_ids") or []) if str(t).strip())
                    for edge in flow.get("handoffs") or []:
                        applicable_flow_test_ids.update(str(t) for t in (edge.get("test_ids") or []) if str(t).strip())

                tests_by_id: dict[str, dict[str, Any]] = {}
                for trow in mdoc.get("tests") or []:
                    tid_str = str(trow.get("id") or "")
                    tests_by_id[tid_str] = trow
                    tpath = str(trow.get("path") or "").strip().replace("\\", "/")
                    is_task_test = tid_str in applicable_flow_test_ids
                    if trow.get("state") == "planned":
                        tsel = str(trow.get("selector") or "").strip()
                        min_tests = trow.get("min_tests")
                        if (
                            not tpath
                            or not tsel
                            or type(min_tests) is not int
                            or min_tests < 1
                            or not _is_substantive_text(trow.get("evidence_level"))
                        ):
                            add_blocking(
                                {
                                    "finding_type": "planned_test",
                                    "category": "planned-only",
                                    "status": "incomplete_planned_test",
                                    "priority": "P1",
                                    "test_id": tid_str,
                                    "manifest": mrel,
                                    "reason": f"planned test {tid_str} lacks explicit path, selector, evidence_level, or min_tests >= 1",
                                },
                                rstage="5",
                                resume_ref=mrel,
                            )
                        else:
                            if is_task_test:
                                planned_test_paths.add(tpath)
                                bound_manifest_test_paths.add(tpath)
                            planned_tests.append(
                                {
                                    "manifest": mrel,
                                    "id": tid_str,
                                    "kind": trow.get("kind"),
                                    "evidence_level": trow.get("evidence_level"),
                                    "path": tpath,
                                    "selector": tsel,
                                    "min_tests": min_tests,
                                    "state": "planned",
                                    "implementation_verified": False,
                                    "runtime_verified": False,
                                }
                            )
                    else:
                        # Existing implemented test must still have min_tests >= 1 (no threshold lowering).
                        min_tests = trow.get("min_tests")
                        if type(min_tests) is not int or min_tests < 1:
                            add_blocking(
                                {
                                    "finding_type": "quality_floor",
                                    "category": "test-false-green",
                                    "status": "test_threshold_lowered",
                                    "priority": "P0",
                                    "test_id": tid_str,
                                    "manifest": mrel,
                                    "reason": f"test {tid_str} has invalid min_tests={min_tests}",
                                },
                                rstage="5",
                                resume_ref=mrel,
                            )
                        elif is_task_test and tpath:
                            bound_manifest_test_paths.add(tpath)

                for flow in mdoc.get("flows") or []:
                    flow_task_ids = [t for t in (flow.get("task_ids") or []) if type(t) is int]
                    if validated_tid not in flow_task_ids:
                        continue
                    flow_task_id_set = set(flow_task_ids)
                    for edge in flow.get("handoffs") or []:
                        handoff_count += 1
                        p_tid = edge.get("producer_task")
                        c_tid = edge.get("consumer_task")
                        o_tid = edge.get("owner_task")
                        c_ref = str(edge.get("contract_ref") or "").strip().replace("\\", "/")
                        e_tids = list(edge.get("test_ids") or [])

                        if type(o_tid) is not int or o_tid not in master_tasks or o_tid not in flow_task_id_set:
                            unowned_handoffs.append({"manifest": mrel, "flow_id": flow.get("id"), "edge": edge})
                            add_blocking(
                                {
                                    "finding_type": "handoff",
                                    "status": "unowned_handoff",
                                    "priority": "P1",
                                    "flow_id": flow.get("id"),
                                    "reason": f"handoff in flow {flow.get('id')} has missing, unknown, or out-of-flow owner_task={o_tid}",
                                },
                                reason_code=codec.ReasonCode.UNRESOLVED_REFERENCE,
                                rstage="5",
                                resume_ref=mrel,
                            )
                        if type(p_tid) is not int or p_tid not in master_tasks or type(c_tid) is not int or c_tid not in master_tasks:
                            unowned_handoffs.append({"manifest": mrel, "flow_id": flow.get("id"), "edge": edge})
                            add_blocking(
                                {
                                    "finding_type": "handoff",
                                    "status": "unowned_handoff",
                                    "priority": "P1",
                                    "flow_id": flow.get("id"),
                                    "reason": f"handoff in flow {flow.get('id')} references unknown producer={p_tid} or consumer={c_tid}",
                                },
                                reason_code=codec.ReasonCode.UNRESOLVED_REFERENCE,
                                rstage="5",
                                resume_ref=mrel,
                            )

                        # Record prerequisite relationships derived from handoff roles.
                        if validated_tid == c_tid and type(p_tid) is int and p_tid != validated_tid:
                            required_prereq_deps.add(p_tid)
                        if validated_tid == o_tid and "integration_only_owner" in task_roles:
                            if type(p_tid) is int and p_tid != validated_tid:
                                required_prereq_deps.add(p_tid)
                            if type(c_tid) is int and c_tid != validated_tid:
                                required_prereq_deps.add(c_tid)

                        # Verify role alignment for this Task and all mapped tasks.
                        if validated_tid == p_tid and "producer" not in task_roles:
                            add_blocking(
                                {
                                    "finding_type": "role_handoff",
                                    "status": "role_mismatch",
                                    "priority": "P1",
                                    "task_id": validated_tid,
                                    "reason": f"task {validated_tid} is handoff producer_task but lacks producer role in Stage-5 binding",
                                },
                                reason_code=codec.ReasonCode.MAPPING_MISMATCH,
                                rstage="5",
                                resume_ref=mrel,
                            )
                        elif p_tid in mapping_by_tid_all and "producer" not in mapping_by_tid_all[p_tid]:
                            add_blocking(
                                {
                                    "finding_type": "role_handoff",
                                    "status": "role_mismatch",
                                    "priority": "P1",
                                    "task_id": p_tid,
                                    "reason": f"producer_task {p_tid} missing producer role in Stage-5 binding",
                                },
                                reason_code=codec.ReasonCode.MAPPING_MISMATCH,
                                rstage="5",
                                resume_ref=mrel,
                            )
                        if validated_tid == c_tid and "consumer" not in task_roles:
                            add_blocking(
                                {
                                    "finding_type": "role_handoff",
                                    "status": "role_mismatch",
                                    "priority": "P1",
                                    "task_id": validated_tid,
                                    "reason": f"task {validated_tid} is handoff consumer_task but lacks consumer role in Stage-5 binding",
                                },
                                reason_code=codec.ReasonCode.MAPPING_MISMATCH,
                                rstage="5",
                                resume_ref=mrel,
                            )
                        elif c_tid in mapping_by_tid_all and "consumer" not in mapping_by_tid_all[c_tid]:
                            add_blocking(
                                {
                                    "finding_type": "role_handoff",
                                    "status": "role_mismatch",
                                    "priority": "P1",
                                    "task_id": c_tid,
                                    "reason": f"consumer_task {c_tid} missing consumer role in Stage-5 binding",
                                },
                                reason_code=codec.ReasonCode.MAPPING_MISMATCH,
                                rstage="5",
                                resume_ref=mrel,
                            )
                        if validated_tid == o_tid and not (
                            task_roles & {"integration_only_owner", "producer", "consumer"}
                        ):
                            add_blocking(
                                {
                                    "finding_type": "role_handoff",
                                    "status": "role_mismatch",
                                    "priority": "P1",
                                    "task_id": validated_tid,
                                    "reason": f"task {validated_tid} is handoff owner_task but lacks valid owner role in Stage-5 binding",
                                },
                                reason_code=codec.ReasonCode.MAPPING_MISMATCH,
                                rstage="5",
                                resume_ref=mrel,
                            )
                        elif o_tid in mapping_by_tid_all and not (
                            mapping_by_tid_all[o_tid] & {"integration_only_owner", "producer", "consumer"}
                        ):
                            add_blocking(
                                {
                                    "finding_type": "role_handoff",
                                    "status": "role_mismatch",
                                    "priority": "P1",
                                    "task_id": o_tid,
                                    "reason": f"owner_task {o_tid} lacks valid owner role in Stage-5 binding",
                                },
                                reason_code=codec.ReasonCode.MAPPING_MISMATCH,
                                rstage="5",
                                resume_ref=mrel,
                            )

                        # Verify contract_ref exists on disk, is explicitly planned, OR resolves as a logical event contract!
                        if not c_ref:
                            add_blocking(
                                {
                                    "finding_type": "handoff",
                                    "status": "missing_handoff_contract",
                                    "priority": "P1",
                                    "flow_id": flow.get("id"),
                                    "contract_ref": c_ref,
                                    "reason": "handoff contract_ref is empty",
                                },
                                reason_code=codec.ReasonCode.UNRESOLVED_REFERENCE,
                                rstage="4",
                                resume_ref=mrel,
                            )
                        elif (root_path / c_ref).is_file() or c_ref in planned_obj_paths:
                            pass
                        else:
                            bound_handoff_c = (
                                contract_bindings.resolve_contract(root_path, c_ref, sources=contract_sources)
                                if contract_sources
                                else None
                            )
                            if bound_handoff_c is not None:
                                if validated_tid in (p_tid, c_tid, o_tid):
                                    extra_contract_refs.add(c_ref)
                            else:
                                add_blocking(
                                    {
                                        "finding_type": "handoff",
                                        "status": "missing_handoff_contract",
                                        "priority": "P1",
                                        "flow_id": flow.get("id"),
                                        "contract_ref": c_ref,
                                        "reason": f"handoff contract_ref missing, unplanned, and unresolved logically: {c_ref}",
                                    },
                                    reason_code=codec.ReasonCode.UNRESOLVED_REFERENCE,
                                    rstage="4",
                                    resume_ref=mrel,
                                )
                        if not e_tids or any(tid_s not in tests_by_id for tid_s in e_tids):
                            add_blocking(
                                {
                                    "finding_type": "handoff",
                                    "status": "missing_handoff_tests",
                                    "priority": "P1",
                                    "flow_id": flow.get("id"),
                                    "test_ids": e_tids,
                                    "reason": f"handoff test_ids missing or unresolved in manifest {mrel}",
                                },
                                reason_code=codec.ReasonCode.UNRESOLVED_REFERENCE,
                                rstage="5",
                                resume_ref=mrel,
                            )

            # 5d. Authority scope & explicit authority_decisions reconciliation (with strict schema & duplicate checks).
            authority_scope, authority_scope_errors = _extract_authority_scope_for_b_task(
                root_path,
                task_id=validated_tid,
                master_row=master_row,
                view_rows=view_rows,
                loaded_bindings=loaded_bindings,
                decisions=decisions_doc,
                planned_ref_paths=planned_obj_paths,
                other_verif_paths=other_verif_paths,
                extra_contract_refs=extra_contract_refs,
            )
            for aerr in authority_scope_errors:
                add_blocking(
                    aerr,
                    reason_code=codec.ReasonCode.UNRESOLVED_REFERENCE,
                    rstage=str(aerr.get("return_stage") or "4"),
                )

            raw_auth_decisions = decisions_doc.get("authority_decisions")
            auth_by_ref: dict[str, dict[str, Any]] = {}
            if "authority_decisions" in decisions_doc and raw_auth_decisions is not None:
                if type(raw_auth_decisions) is not list:
                    add_blocking(
                        {
                            "finding_type": "decisions_schema",
                            "status": "invalid_decisions_schema",
                            "priority": "P1",
                            "field": "authority_decisions",
                            "reason": "decisions.authority_decisions must be a list",
                        },
                        rstage="5",
                    )
                else:
                    seen_auth_keys: set[str] = set()
                    for idx_a, row in enumerate(raw_auth_decisions):
                        if type(row) is not dict:
                            add_blocking(
                                {
                                    "finding_type": "decisions_schema",
                                    "status": "invalid_decisions_schema",
                                    "priority": "P1",
                                    "field": "authority_decisions",
                                    "reason": f"decisions.authority_decisions[{idx_a}] must be an object",
                                },
                                rstage="5",
                            )
                            continue
                        key = str(row.get("authority_ref") or "").strip().replace("\\", "/")
                        if not key:
                            add_blocking(
                                {
                                    "finding_type": "decisions_schema",
                                    "status": "invalid_decisions_schema",
                                    "priority": "P1",
                                    "field": "authority_decisions",
                                    "reason": f"decisions.authority_decisions[{idx_a}] lacks nonempty authority_ref",
                                },
                                rstage="5",
                            )
                            continue
                        canon_key = key.upper() if _ADR_TOKEN_RE.fullmatch(key) else key
                        if canon_key in seen_auth_keys:
                            add_blocking(
                                {
                                    "finding_type": "decisions_schema",
                                    "status": "duplicate_decision_key",
                                    "priority": "P1",
                                    "field": "authority_decisions",
                                    "authority_ref": key,
                                    "reason": f"duplicate authority_decisions entry for {canon_key}",
                                },
                                rstage="5",
                            )
                            continue
                        seen_auth_keys.add(canon_key)
                        auth_by_ref[key] = row
                        if _ADR_TOKEN_RE.fullmatch(key):
                            auth_by_ref[key.upper()] = row

            authority_reconciliation: list[dict[str, Any]] = []
            authority_items = (
                [("overlay", item) for item in authority_scope["overlays"]]
                + [("adr", item) for item in authority_scope["adrs"]]
                + [("contract", item) for item in authority_scope["contracts"]]
            )
            for atype, item in authority_items:
                aref = str(item["ref"])
                dec = auth_by_ref.get(aref) or auth_by_ref.get(aref.upper()) or {}
                status = str(dec.get("status") or "").strip()
                rationale = str(dec.get("rationale") or "").strip()
                if status not in ALLOWED_AUTHORITY_STATUS or not _is_substantive_text(rationale):
                    status = "needs_human_decision"
                authority_reconciliation.append(
                    {
                        "authority_type": atype,
                        "authority_ref": aref,
                        "authority_sha256": item.get("sha256"),
                        "planned": bool(item.get("planned", False)),
                        "status": status,
                        "rationale": rationale,
                    }
                )
                if status == "conflict":
                    add_blocking(
                        {
                            "finding_type": "authority",
                            "status": "conflict_with_adr",
                            "authority_type": atype,
                            "authority_ref": aref,
                            "priority": "P1",
                            "reason": rationale,
                        },
                        rstage="4",
                    )
                elif status == "needs_human_decision":
                    add_blocking(
                        {
                            "finding_type": "authority",
                            "status": "needs_human_decision",
                            "authority_type": atype,
                            "authority_ref": aref,
                            "priority": "P1",
                            "reason": f"authority compatibility not explicitly reviewed for {atype}:{aref}",
                        },
                        rstage="5",
                    )

            # 5e. Acceptance/Refs & bidirectional Requirement coverage reconciliation.
            acceptance_list: list[str] = []
            task_semantic_refs: set[str] = set()
            overlap_candidates: set[str] = set()
            for vrow in view_rows:
                for acc in vrow.get("acceptance") or []:
                    text = str(acc or "").strip()
                    if text and text not in acceptance_list:
                        acceptance_list.append(text)
                for sref in vrow.get("semantic_refs") or []:
                    if str(sref or "").strip():
                        task_semantic_refs.add(str(sref).strip())
                for ov in vrow.get("implementation_overlap_candidates") or []:
                    if str(ov or "").strip():
                        overlap_candidates.add(str(ov).strip())

            # Check unsupported task semantic_refs claims not in committed applicable requirements.
            all_plan_req_ids = {
                r["requirement_id"]
                for (_pref, _praw, pdoc) in loaded_plans.values()
                for r in (pdoc.get("requirements") or [])
            }
            for sref in sorted(task_semantic_refs):
                if sref not in all_plan_req_ids:
                    add_blocking(
                        {
                            "finding_type": "task_claim",
                            "status": "unsupported_task_claim",
                            "priority": "P1",
                            "requirement_id": sref,
                            "reason": f"task semantic_ref {sref} not declared in committed applicable plans",
                        },
                        rstage="3C",
                    )

            if not acceptance_list:
                add_blocking(
                    {
                        "finding_type": "acceptance",
                        "category": "acceptance-refs",
                        "status": "missing_acceptance",
                        "priority": "P1",
                        "reason": f"task {validated_tid} has no acceptance criteria in business views",
                    },
                    rstage="3C",
                )

            raw_acc_links = decisions_doc.get("acceptance_links")
            links_by_index: dict[int, dict[str, Any]] = {}
            if "acceptance_links" in decisions_doc and raw_acc_links is not None:
                if type(raw_acc_links) is not list:
                    add_blocking(
                        {
                            "finding_type": "decisions_schema",
                            "status": "invalid_decisions_schema",
                            "priority": "P1",
                            "field": "acceptance_links",
                            "reason": "decisions.acceptance_links must be a list",
                        },
                        rstage="5",
                    )
                else:
                    for idx_l, row in enumerate(raw_acc_links):
                        if type(row) is not dict:
                            add_blocking(
                                {
                                    "finding_type": "decisions_schema",
                                    "status": "invalid_decisions_schema",
                                    "priority": "P1",
                                    "field": "acceptance_links",
                                    "reason": f"decisions.acceptance_links[{idx_l}] must be an object",
                                },
                                rstage="5",
                            )
                            continue
                        aidx = row.get("acceptance_index")
                        if type(aidx) is not int or aidx < 1 or aidx > len(acceptance_list):
                            add_blocking(
                                {
                                    "finding_type": "decisions_schema",
                                    "status": "invalid_acceptance_index",
                                    "priority": "P1",
                                    "field": "acceptance_links",
                                    "acceptance_index": aidx,
                                    "reason": f"decisions.acceptance_links[{idx_l}] has out-of-range or non-int acceptance_index={aidx} (valid: 1..{len(acceptance_list)})",
                                },
                                rstage="5",
                            )
                            continue
                        if aidx in links_by_index:
                            add_blocking(
                                {
                                    "finding_type": "decisions_schema",
                                    "status": "duplicate_decision_key",
                                    "priority": "P1",
                                    "field": "acceptance_links",
                                    "acceptance_index": aidx,
                                    "reason": f"duplicate acceptance_links entry for acceptance_index={aidx}",
                                },
                                rstage="5",
                            )
                            continue
                        links_by_index[aidx] = row

            allowed_authority_tokens = (
                {str(x["ref"]) for x in authority_scope["overlays"]}
                | {str(x["ref"]) for x in authority_scope["contracts"]}
                | {str(x["ref"]) for x in authority_scope["adrs"]}
                | {str(x["path"]) for x in authority_scope["adrs"] if x.get("path")}
                | other_verif_paths
            )
            decision_referenced_file_digests: dict[str, dict[str, str]] = {}

            def _record_decision_file_digest(rel_candidate: str, rstage: str) -> None:
                try:
                    rel_clean = preflight.path(rel_candidate.replace("\\", "/"))
                    target = inventory.safe_input(root_path, rel_clean, allow_logs=False)
                except (codec.CodecError, ValueError, OSError):
                    return
                if not target.is_file():
                    return
                dg = codec.raw_digest(target.read_bytes())
                prior = decision_referenced_file_digests.get(rel_clean)
                effective_stage = rstage
                if prior is not None and STAGE_RANK.get(prior["return_stage"], 99) < STAGE_RANK.get(effective_stage, 99):
                    effective_stage = prior["return_stage"]
                decision_referenced_file_digests[rel_clean] = {
                    "raw_digest": dg,
                    "return_stage": effective_stage,
                }

            def _is_valid_test_verification_ref(tref_raw: str) -> bool:
                try:
                    trel = preflight.path(tref_raw.replace("\\", "/"))
                except codec.CodecError:
                    return False
                if trel in bound_manifest_test_paths or trel in planned_test_paths:
                    return True
                if trel in other_verif_paths:
                    return (root_path / trel).is_file()
                if trel in planned_obj_paths:
                    return False
                tfile = root_path / trel
                if not tfile.is_file():
                    return False
                low = trel.casefold()
                if low.startswith(("game.core.tests/", "tests.godot/")) and low.endswith((".cs", ".gd")):
                    return True
                if low.startswith("scripts/python/tests/") and low.endswith(".py"):
                    return True
                parts = low.split("/")
                if any(p in ("tests", "test") for p in parts[:-1]) and low.endswith((".cs", ".gd", ".py")):
                    return True
                return False

            # Record digests of all extra authority files resolved via decisions.
            for item in authority_scope["overlays"]:
                if not item.get("planned") and item.get("ref"):
                    _record_decision_file_digest(str(item["ref"]), "4")
            for item in authority_scope["adrs"]:
                if item.get("path"):
                    _record_decision_file_digest(str(item["path"]), "4")
            for item in authority_scope["contracts"]:
                if item.get("planned"):
                    continue
                if item.get("path"):
                    _record_decision_file_digest(str(item["path"]), "4")
                for brow in item.get("bindings") or []:
                    if type(brow) is dict and brow.get("path"):
                        _record_decision_file_digest(str(brow["path"]), "4")

            acceptance_coverage: dict[str, list[int]] = {
                rid: [] for rid in sorted(applicable_req_ids - deferred_req_ids)
            }
            topology_edges: list[dict[str, Any]] = []
            for rid in sorted(applicable_req_ids):
                topology_edges.append(
                    {
                        "source_type": "requirement",
                        "source_id": rid,
                        "target_type": "task",
                        "target_id": entity_id,
                        "relation": "implemented_by",
                        "contribution": "chapter5_stabilized",
                    }
                )

            for idx, acc_text in enumerate(acceptance_list, 1):
                link = links_by_index.get(idx)
                if link is None:
                    add_blocking(
                        {
                            "finding_type": "acceptance",
                            "category": "acceptance-refs",
                            "status": "orphan_acceptance",
                            "priority": "P1",
                            "acceptance_index": idx,
                            "acceptance": acc_text,
                            "reason": f"acceptance[{idx}] lacks explicit Chapter 5 acceptance_links decision",
                        },
                        rstage="5",
                    )
                    continue
                req_ids = sorted({str(x).strip() for x in (link.get("requirement_ids") or []) if str(x).strip()})
                auth_refs = sorted(
                    {str(x).strip().replace("\\", "/") for x in (link.get("authority_refs") or []) if str(x).strip()}
                )
                parsed_refs = _parse_acceptance_refs(acc_text)
                link_test_refs = [
                    str(x).strip().replace("\\", "/") for x in (link.get("test_refs") or []) if str(x).strip()
                ]
                all_test_refs = sorted(set(parsed_refs + link_test_refs))

                if not req_ids and not auth_refs:
                    add_blocking(
                        {
                            "finding_type": "acceptance",
                            "category": "acceptance-refs",
                            "status": "orphan_acceptance",
                            "priority": "P1",
                            "acceptance_index": idx,
                            "reason": f"acceptance[{idx}] links to neither requirement_ids nor authority_refs",
                        },
                        rstage="5",
                    )
                if not parsed_refs or not all_test_refs:
                    add_blocking(
                        {
                            "finding_type": "acceptance",
                            "category": "acceptance-refs",
                            "status": "untraceable_acceptance",
                            "priority": "P1",
                            "acceptance_index": idx,
                            "reason": f"acceptance[{idx}] lacks explicit Refs: test/verification path",
                        },
                        rstage="3C",
                    )
                for tref in all_test_refs:
                    if not _is_valid_test_verification_ref(tref):
                        add_blocking(
                            {
                                "finding_type": "acceptance",
                                "category": "acceptance-refs",
                                "status": "untraceable_acceptance",
                                "priority": "P1",
                                "acceptance_index": idx,
                                "test_ref": tref,
                                "reason": f"acceptance[{idx}] ref {tref} does not resolve to a bound Stage-5 manifest test, existing test verification file, or bound other_verification_ref",
                            },
                            rstage="5",
                        )
                    else:
                        _record_decision_file_digest(tref, "5")
                out_of_scope = [rid for rid in req_ids if rid not in applicable_req_ids]
                if out_of_scope:
                    add_blocking(
                        {
                            "finding_type": "acceptance",
                            "category": "acceptance-refs",
                            "status": "out_of_task_scope",
                            "priority": "P1",
                            "acceptance_index": idx,
                            "requirement_ids": out_of_scope,
                            "reason": f"acceptance[{idx}] references out-of-scope requirement(s): {out_of_scope}",
                        },
                        rstage="3C",
                    )
                for aref in auth_refs:
                    if aref not in allowed_authority_tokens and aref.upper() not in allowed_authority_tokens:
                        add_blocking(
                            {
                                "finding_type": "acceptance",
                                "category": "acceptance-refs",
                                "status": "untraceable_acceptance",
                                "priority": "P1",
                                "acceptance_index": idx,
                                "authority_ref": aref,
                                "reason": f"acceptance[{idx}] authority_ref {aref} is not bound in Task authority scope",
                            },
                            rstage="4",
                        )
                acc_id = "AC-T" + entity_id + "-" + _sha_text(entity_id + "\0" + acc_text)[:12]
                topology_edges.append(
                    {
                        "source_type": "task",
                        "source_id": entity_id,
                        "target_type": "acceptance",
                        "target_id": acc_id,
                        "relation": "verified_by",
                    }
                )
                for rid in req_ids:
                    if rid in acceptance_coverage:
                        acceptance_coverage[rid].append(idx)
                    topology_edges.append(
                        {
                            "source_type": "requirement",
                            "source_id": rid,
                            "target_type": "acceptance",
                            "target_id": acc_id,
                            "relation": "accepted_by",
                        }
                    )

            for rid, covered_indices in sorted(acceptance_coverage.items()):
                if not covered_indices:
                    add_blocking(
                        {
                            "finding_type": "acceptance",
                            "category": "acceptance-refs",
                            "status": "partial_acceptance",
                            "priority": "P1",
                            "requirement_id": rid,
                            "reason": f"applicable requirement {rid} is omitted from Task {validated_tid} acceptance_links",
                        },
                        rstage="3C",
                    )

            # 5f. Dependency reconciliation & explicit dependency_decisions (acyclic, non-done legal, no erasing prerequisites).
            try:
                direct_deps, transitive_deps = input_set._compute_dependency_closure(
                    validated_tid,
                    master_tasks=master_tasks,
                    back_by_tid=back_by_tid,
                    gameplay_by_tid=gameplay_by_tid,
                    views=views,
                )
            except codec.CodecError as err:
                add_blocking(
                    {
                        "finding_type": "dependency",
                        "status": "invalid_dependency",
                        "priority": "P1",
                        "reason": f"dependency closure failed: {err.diagnostic.reason_code.value} ({err.diagnostic.actual})",
                    },
                    reason_code=err.diagnostic.reason_code,
                    rstage="3C",
                    resume_ref=task_resolver.TRIPLET["master"],
                )
                direct_deps, transitive_deps = [], []

            if validated_tid in transitive_deps:
                self_lock_detected = True
                add_blocking(
                    {
                        "finding_type": "dependency",
                        "status": "invalid_dependency",
                        "priority": "P1",
                        "reason": f"task {validated_tid} depends on itself (self-lock cycle)",
                    },
                    reason_code=codec.ReasonCode.DIGEST_CYCLE,
                    rstage="3C",
                    resume_ref=task_resolver.TRIPLET["master"],
                )

            raw_dep_decisions = decisions_doc.get("dependency_decisions")
            dep_by_id: dict[int, dict[str, Any]] = {}
            if "dependency_decisions" in decisions_doc and raw_dep_decisions is not None:
                if type(raw_dep_decisions) is not list:
                    add_blocking(
                        {
                            "finding_type": "decisions_schema",
                            "status": "invalid_decisions_schema",
                            "priority": "P1",
                            "field": "dependency_decisions",
                            "reason": "decisions.dependency_decisions must be a list",
                        },
                        rstage="5",
                    )
                else:
                    for idx_d, row in enumerate(raw_dep_decisions):
                        if type(row) is not dict:
                            add_blocking(
                                {
                                    "finding_type": "decisions_schema",
                                    "status": "invalid_decisions_schema",
                                    "priority": "P1",
                                    "field": "dependency_decisions",
                                    "reason": f"decisions.dependency_decisions[{idx_d}] must be an object",
                                },
                                rstage="5",
                            )
                            continue
                        raw_did = row.get("dependency_id")
                        did_str = _canonical_task_id_str(raw_did)
                        if _POS_INT_RE.fullmatch(did_str) is None:
                            add_blocking(
                                {
                                    "finding_type": "decisions_schema",
                                    "status": "invalid_decisions_schema",
                                    "priority": "P1",
                                    "field": "dependency_decisions",
                                    "dependency_id": raw_did,
                                    "reason": f"decisions.dependency_decisions[{idx_d}] has invalid dependency_id={raw_did}",
                                },
                                rstage="5",
                            )
                            continue
                        did_int = int(did_str)
                        if did_int in dep_by_id:
                            add_blocking(
                                {
                                    "finding_type": "decisions_schema",
                                    "status": "duplicate_decision_key",
                                    "priority": "P1",
                                    "field": "dependency_decisions",
                                    "dependency_id": str(did_int),
                                    "reason": f"duplicate dependency_decisions entry for dependency_id={did_int}",
                                },
                                rstage="5",
                            )
                            continue
                        dep_by_id[did_int] = row

            dependency_corrections: list[dict[str, Any]] = []
            all_expected_deps = sorted(set(direct_deps) | required_prereq_deps)
            for dep in all_expected_deps:
                dec = dep_by_id.get(dep)
                if dep in required_prereq_deps and dep not in direct_deps:
                    # Taskmaster erased a handoff prerequisite!
                    add_blocking(
                        {
                            "finding_type": "dependency",
                            "status": "erased_prerequisite_dependency",
                            "priority": "P1",
                            "dependency_id": str(dep),
                            "reason": f"required handoff prerequisite task {dep} is missing from Task {validated_tid} dependencies",
                        },
                        reason_code=codec.ReasonCode.MAPPING_MISMATCH,
                        rstage="3C",
                        resume_ref=task_resolver.TRIPLET["master"],
                    )
                    continue
                if dec is None:
                    dependency_corrections.append(
                        {
                            "dependency_id": str(dep),
                            "action": "needs_human_decision",
                            "reason": "dependency lacks explicit Chapter 5 dependency_decisions entry",
                            "dependency_evidence": [],
                        }
                    )
                    add_blocking(
                        {
                            "finding_type": "dependency",
                            "status": "dependency_unresolved",
                            "priority": "P1",
                            "dependency_id": str(dep),
                            "reason": f"dependency {dep} lacks explicit Chapter 5 dependency_decisions review",
                        },
                        rstage="5",
                    )
                    continue
                action = str(dec.get("action") or "").strip()
                reason = str(dec.get("dependency_reason") or dec.get("reason") or "").strip()
                evidence = [
                    str(x).strip()
                    for x in (dec.get("dependency_evidence") or dec.get("evidence") or [])
                    if str(x).strip()
                ]
                relation = str(dec.get("relation") or "").strip()
                if action == "remove" and dep in required_prereq_deps:
                    add_blocking(
                        {
                            "finding_type": "dependency",
                            "status": "erased_prerequisite_dependency",
                            "priority": "P1",
                            "dependency_id": str(dep),
                            "reason": f"cannot erase required handoff prerequisite dependency {dep}",
                        },
                        reason_code=codec.ReasonCode.MAPPING_MISMATCH,
                        rstage="3C",
                    )
                    continue
                effective_action = "keep" if action == "add" else action
                valid_dep = effective_action in {"keep", "remove"} and _is_substantive_text(reason)
                if effective_action == "keep":
                    valid_dep = valid_dep and relation in ALLOWED_DEPENDENCY_RELATIONS and bool(evidence)
                if not valid_dep:
                    dependency_corrections.append(
                        {
                            "dependency_id": str(dep),
                            "action": "needs_human_decision",
                            "relation": relation,
                            "dependency_reason": reason,
                            "dependency_evidence": evidence,
                        }
                    )
                    add_blocking(
                        {
                            "finding_type": "dependency",
                            "status": "dependency_unresolved",
                            "priority": "P1",
                            "dependency_id": str(dep),
                            "reason": f"dependency {dep} decision lacks valid relation/reason/evidence",
                        },
                        rstage="5",
                    )
                else:
                    dependency_corrections.append(
                        {
                            "dependency_id": str(dep),
                            "action": effective_action,
                            "relation": relation,
                            "dependency_reason": reason,
                            "dependency_evidence": evidence,
                        }
                    )

            # 5g. Overlap decisions reconciliation (strict schema + duplicate key check).
            raw_overlap = decisions_doc.get("overlap_decisions")
            overlap_by_other: dict[str, dict[str, Any]] = {}
            if "overlap_decisions" in decisions_doc and raw_overlap is not None:
                if type(raw_overlap) is not list:
                    add_blocking(
                        {
                            "finding_type": "decisions_schema",
                            "status": "invalid_decisions_schema",
                            "priority": "P1",
                            "field": "overlap_decisions",
                            "reason": "decisions.overlap_decisions must be a list",
                        },
                        rstage="5",
                    )
                else:
                    for idx_o, row in enumerate(raw_overlap):
                        if type(row) is not dict:
                            add_blocking(
                                {
                                    "finding_type": "decisions_schema",
                                    "status": "invalid_decisions_schema",
                                    "priority": "P1",
                                    "field": "overlap_decisions",
                                    "reason": f"decisions.overlap_decisions[{idx_o}] must be an object",
                                },
                                rstage="5",
                            )
                            continue
                        oid_str = _canonical_task_id_str(row.get("other_task_id"))
                        if not oid_str:
                            add_blocking(
                                {
                                    "finding_type": "decisions_schema",
                                    "status": "invalid_decisions_schema",
                                    "priority": "P1",
                                    "field": "overlap_decisions",
                                    "reason": f"decisions.overlap_decisions[{idx_o}] lacks other_task_id",
                                },
                                rstage="5",
                            )
                            continue
                        if oid_str in overlap_by_other:
                            add_blocking(
                                {
                                    "finding_type": "decisions_schema",
                                    "status": "duplicate_decision_key",
                                    "priority": "P1",
                                    "field": "overlap_decisions",
                                    "other_task_id": oid_str,
                                    "reason": f"duplicate overlap_decisions entry for other_task_id={oid_str}",
                                },
                                rstage="5",
                            )
                            continue
                        overlap_by_other[oid_str] = row
            overlap_reviews: list[dict[str, Any]] = []
            for other in sorted(overlap_candidates):
                other_id = _canonical_task_id_str(other)
                dec = overlap_by_other.get(other_id) or {}
                status = str(dec.get("status") or "").strip()
                rationale = str(dec.get("rationale") or "").strip()
                if status not in ALLOWED_OVERLAP_DECISIONS or not _is_substantive_text(rationale):
                    status = "needs_human_decision"
                    add_concern(
                        {
                            "finding_type": "overlap",
                            "category": "overlap",
                            "status": "needs_human_decision",
                            "priority": "P2",
                            "other_task_id": other_id,
                            "reason": f"overlap candidate {other_id} lacks reviewed overlap_decisions entry",
                        },
                        rstage="5",
                    )
                overlap_reviews.append(
                    {
                        "other_task_id": other_id,
                        "status": status,
                        "rationale": rationale,
                    }
                )

            # 5h. Merge BOTH findings AND review_findings from decisions (strict schema + duplicate finding_id check).
            combined_raw_findings: list[tuple[str, Any]] = []
            for fkey in ("findings", "review_findings"):
                if fkey in decisions_doc and decisions_doc[fkey] is not None:
                    raw_list = decisions_doc[fkey]
                    if type(raw_list) is not list:
                        add_blocking(
                            {
                                "finding_type": "decisions_schema",
                                "status": "invalid_decisions_schema",
                                "priority": "P1",
                                "field": fkey,
                                "reason": f"decisions.{fkey} must be a list",
                            },
                            rstage="5",
                        )
                    else:
                        for entry in raw_list:
                            combined_raw_findings.append((fkey, entry))

            seen_explicit_fids: set[str] = set()
            for fkey, raw_f in combined_raw_findings:
                if type(raw_f) is not dict:
                    add_blocking(
                        {
                            "finding_type": "decisions_schema",
                            "status": "invalid_decisions_schema",
                            "priority": "P1",
                            "field": fkey,
                            "reason": f"decisions.{fkey} contains non-object entry",
                        },
                        rstage="5",
                    )
                    continue
                explicit_fid = str(raw_f.get("finding_id") or "").strip()
                if explicit_fid:
                    if explicit_fid in seen_explicit_fids:
                        add_blocking(
                            {
                                "finding_type": "decisions_schema",
                                "status": "duplicate_decision_key",
                                "priority": "P1",
                                "field": fkey,
                                "finding_id": explicit_fid,
                                "reason": f"duplicate explicit finding_id={explicit_fid}",
                            },
                            rstage="5",
                        )
                        continue
                    seen_explicit_fids.add(explicit_fid)
                sev = str(raw_f.get("priority") or raw_f.get("severity") or "P1").strip().upper()
                cat = str(raw_f.get("category") or raw_f.get("finding_type") or "review").strip().lower()
                msg = str(raw_f.get("reason") or raw_f.get("message") or "").strip()
                fid = explicit_fid or _stable_finding_id("ch5", cat, msg, entity_id)
                f_stage = str(raw_f.get("return_stage") or "5")
                if f_stage not in STAGE_RANK:
                    f_stage = "5"
                normalized_f = {
                    "finding_id": fid,
                    "finding_type": raw_f.get("finding_type") or "review_finding",
                    "category": cat,
                    "status": raw_f.get("status") or "review_finding",
                    "priority": sev,
                    "reason": msg or "explicit Chapter 5 review finding",
                    "source_path": raw_f.get("source_path"),
                }
                if sev not in ALL_SEVERITIES or sev in P0_P1_SEVERITIES or cat in P1_FLOOR_CATEGORIES:
                    add_blocking(normalized_f, rstage=f_stage)
                else:
                    add_concern(normalized_f, rstage=f_stage)

            # 5i. Old done task encountering new obligations or planned tests.
            reverification = _compute_live_reverification(
                validated_tid,
                master_tasks=master_tasks,
                loaded_plans=loaded_plans,
                loaded_bindings=loaded_bindings,
                manifests=bound_manifests,
            )

            # 6. Revalidate guarded_input_set lease BEFORE ANY side-effect writes (including docs/technical-debt.md)!
            revalidated = handle.revalidate()

            # 5j. Enforce allow_concerns + docs/technical-debt.md for P2..P4 findings (zero-write when not write_artifacts).
            allow_concerns = bool(decisions_doc.get("allow_concerns", False))
            recorded_debt_ids: list[str] = []
            if not blocking_findings and concern_findings:
                if allow_concerns:
                    if not write_artifacts:
                        if record_technical_debt:
                            validated_debt = _validate_technical_debt_findings(validated_tid, concern_findings)
                            recorded_debt_ids = [row["finding_id"] for row in validated_debt]
                        else:
                            all_rec, rec_ids, missing_ids = verify_technical_debt_recorded(
                                root_path, validated_tid, concern_findings
                            )
                            recorded_debt_ids = rec_ids
                            if not all_rec:
                                add_blocking(
                                    {
                                        "finding_type": "technical_debt",
                                        "category": "artifact-integrity",
                                        "status": "technical_debt_unrecorded",
                                        "priority": "P1",
                                        "missing_finding_ids": missing_ids,
                                        "reason": f"P2..P4 concerns require recording in {TECHNICAL_DEBT_PATH}: {missing_ids}",
                                    },
                                    rstage="5",
                                    resume_ref=TECHNICAL_DEBT_PATH,
                                )
                    else:
                        if record_technical_debt:
                            recorded_debt_ids = record_technical_debt_findings(
                                root_path, validated_tid, concern_findings
                            )
                        all_rec, rec_ids, missing_ids = verify_technical_debt_recorded(
                            root_path, validated_tid, concern_findings
                        )
                        recorded_debt_ids = rec_ids
                        if not all_rec:
                            add_blocking(
                                {
                                    "finding_type": "technical_debt",
                                    "category": "artifact-integrity",
                                    "status": "technical_debt_unrecorded",
                                    "priority": "P1",
                                    "missing_finding_ids": missing_ids,
                                    "reason": f"P2..P4 concerns require recording in {TECHNICAL_DEBT_PATH}: {missing_ids}",
                                },
                                rstage="5",
                                resume_ref=TECHNICAL_DEBT_PATH,
                            )
                else:
                    # Concerns without allow_concerns -> readiness="CONCERNS", closure_allowed=False.
                    return_stages.append("5")
                    diagnostics.append(
                        _diag(
                            codec.ReasonCode.SEMANTIC_ERROR,
                            stage=codec.Stage.CONTENT,
                            entity_id=entity_id,
                            expected={"allow_concerns": True, "technical_debt_recorded": True, "return_stage": "5"},
                            actual={"allow_concerns": False, "concern_count": len(concern_findings), "return_stage": "5"},
                        )
                    )

            readiness_verdict = (
                "BLOCKED"
                if blocking_findings
                else ("CONCERNS" if concern_findings else "READY")
            )
            closure_allowed = readiness_verdict == "READY" or (
                readiness_verdict == "CONCERNS" and allow_concerns
            )
            final_return_stage = None if closure_allowed else (_earliest_stage(return_stages) or "5")

            plan_refs = deepcopy(origin["plan_refs"])
            binding_refs = deepcopy(origin["binding_refs"])
            scope_ids = list(revalidated["scope_ids"])
            input_set_digest = revalidated["input_set_digest"]
            applicable_set_digest = origin["applicable_set_digest"]
            baseline_doc = _build_minimal_input_set_baseline(revalidated)
            primary_source_revision = (
                audit_summary["source_revisions"][0]
                if audit_summary["source_revisions"]
                else "b-route-source-revision"
            )
            cache_key = {
                "route": "B",
                "task_id": entity_id,
                "input_set_digest": input_set_digest,
                "applicable_set_digest": applicable_set_digest,
                "source_revisions": audit_summary["source_revisions"],
            }
            snapshot_id = "B3A-" + _canonical_sha(cache_key)[:20].upper()
            elapsed = round(max(0.0, time.monotonic() - started), 6)
            metrics = {
                "active_elapsed_seconds": elapsed,
                "model_invocation_count": 0,
                "source_audit_reused": bool(audit_summary["reused"]),
                "reused_3a_proof_count": int(audit_summary["reused_3a_proof_count"]),
                "return_stage": final_return_stage,
            }
            now_utc = dt.datetime.now(dt.timezone.utc).isoformat()

            reconciliation_doc: dict[str, Any] = {
                "schema_version": RECONCILIATION_SCHEMA,
                "b_route_schema_version": B_ROUTE_SCHEMA,
                "route": "B",
                "generated_at_utc": now_utc,
                "task_id": entity_id,
                "source_revision": primary_source_revision,
                "extraction_b_snapshot_id": snapshot_id,
                "cache_key": cache_key,
                "global_audit_completed": True,
                "input_set_digest": input_set_digest,
                "applicable_set_digest": applicable_set_digest,
                "scope_ids": scope_ids,
                "plan_refs": plan_refs,
                "binding_refs": binding_refs,
                "input_set_baseline": baseline_doc,
                "input_fingerprint": input_set_digest,
                "source_audit_reuse": audit_summary,
                "authority_scope": authority_scope,
                "authority_scope_errors": authority_scope_errors,
                "authority_reconciliation": authority_reconciliation,
                "decision_referenced_file_digests": {
                    k: decision_referenced_file_digests[k]
                    for k in sorted(decision_referenced_file_digests)
                },
                "findings": all_findings,
                "dependency_corrections": dependency_corrections,
                "final_dependencies": [str(d) for d in direct_deps],
                "dependency_eligibility": deepcopy(revalidated["dependency_eligibility"]),
                "overlap_reviews": overlap_reviews,
                "acceptance_coverage": acceptance_coverage,
                "planned_summary": {
                    "planned_objects": planned_objects,
                    "planned_tests": planned_tests,
                    "implementation_verified": False,
                    "runtime_verified": False,
                },
                "role_handoff_summary": {
                    "roles": sorted(task_roles),
                    "handoff_count": handoff_count,
                    "self_lock_detected": self_lock_detected,
                    "unowned_handoffs": unowned_handoffs,
                },
                "reverification": reverification,
                "requires_chapter6_reverification": bool(reverification["requires_chapter6_reverification"]),
                "old_done_covers_new_obligations": False,
                "technical_debt": {
                    "register_path": TECHNICAL_DEBT_PATH,
                    "recorded_finding_ids": recorded_debt_ids,
                    "deferred_severities": sorted({str(c.get("priority", "P2")) for c in concern_findings}),
                },
                "readiness_verdict": readiness_verdict,
                "closure_allowed": closure_allowed,
                "allow_concerns": allow_concerns,
                "return_stage": final_return_stage,
                "metrics": metrics,
                "diagnostics": diagnostics,
                "topology_edges": topology_edges,
                "summary": {
                    "missing": sum(1 for r in all_findings if r.get("status") in {"missing_in_ch3", "missing_acceptance"}),
                    "partial": sum(1 for r in all_findings if r.get("status") in {"partial", "partial_acceptance"}),
                    "invented": sum(1 for r in all_findings if r.get("status") in {"invented_in_ch3", "unsupported_task_claim"}),
                    "conflicts": sum(1 for r in all_findings if r.get("status") == "conflict_with_adr"),
                    "orphan_delivery_semantic": sum(1 for r in all_findings if r.get("status") == "orphan_delivery_semantic"),
                    "orphan_acceptance": sum(1 for r in all_findings if r.get("status") == "orphan_acceptance"),
                    "blocking_count": len(blocking_findings),
                    "concern_count": len(concern_findings),
                },
                **INVARIANT_FLAGS,
            }
            reconciliation_sha = "sha256:" + _canonical_sha(reconciliation_doc)

            readiness_doc: dict[str, Any] = {
                "schema_version": READINESS_SCHEMA,
                "b_route_schema_version": B_ROUTE_SCHEMA,
                "route": "B",
                "generated_at_utc": now_utc,
                "task_id": entity_id,
                "source_revision": primary_source_revision,
                "extraction_b_snapshot_id": snapshot_id,
                "cache_key": cache_key,
                "reconciliation_sha256": reconciliation_sha,
                "reconciliation_path": out_rel,
                "input_fingerprint": input_set_digest,
                "input_set_digest": input_set_digest,
                "applicable_set_digest": applicable_set_digest,
                "scope_ids": scope_ids,
                "plan_refs": plan_refs,
                "binding_refs": binding_refs,
                "readiness": readiness_verdict,
                "closure_allowed": closure_allowed,
                "allow_concerns": allow_concerns,
                "requires_chapter6_reverification": bool(reverification["requires_chapter6_reverification"]),
                "old_done_covers_new_obligations": False,
                "source_audit_reuse": audit_summary,
                "planned_summary": deepcopy(reconciliation_doc["planned_summary"]),
                "role_handoff_summary": deepcopy(reconciliation_doc["role_handoff_summary"]),
                "technical_debt": deepcopy(reconciliation_doc["technical_debt"]),
                "blocking_findings": blocking_findings,
                "concerns": concern_findings,
                "return_stage": final_return_stage,
                "metrics": metrics,
                "diagnostics": diagnostics,
                **INVARIANT_FLAGS,
            }

            written_rec_rel: str | None = None
            written_rdy_rel: str | None = None
            if write_artifacts:
                _write_json_atomic(out_file, reconciliation_doc)
                _write_json_atomic(readiness_file, readiness_doc)
                written_rec_rel = out_rel
                written_rdy_rel = rdy_rel
                if write_latest and out_path is None and readiness_path is None:
                    _write_json_atomic(root_path / DEFAULT_RECONCILIATION_DIR / "latest.json", reconciliation_doc)
                    _write_json_atomic(root_path / DEFAULT_READINESS_DIR / "latest.json", readiness_doc)

            return {
                "schema_version": B_ROUTE_SCHEMA,
                "ok": closure_allowed,
                "status": "ok" if closure_allowed else "blocked",
                "route": "B",
                "task_id": validated_tid,
                "operation": validated_op,
                "readiness": readiness_verdict,
                "closure_allowed": closure_allowed,
                "allow_concerns": allow_concerns,
                "requires_chapter6_reverification": bool(reverification["requires_chapter6_reverification"]),
                "old_done_covers_new_obligations": False,
                "input_set_digest": input_set_digest,
                "applicable_set_digest": applicable_set_digest,
                "scope_ids": scope_ids,
                "plan_refs": plan_refs,
                "binding_refs": binding_refs,
                "reconciliation_sha256": reconciliation_sha,
                "source_audit_reuse": audit_summary,
                "planned_summary": reconciliation_doc["planned_summary"],
                "role_handoff_summary": reconciliation_doc["role_handoff_summary"],
                "technical_debt": reconciliation_doc["technical_debt"],
                "blocking_count": len(blocking_findings),
                "concern_count": len(concern_findings),
                "return_stage": final_return_stage,
                "metrics": metrics,
                "reconciliation_path": written_rec_rel,
                "readiness_path": written_rdy_rel,
                "diagnostics": diagnostics,
                "reconciliation_doc": reconciliation_doc,
                "readiness_doc": readiness_doc,
                **INVARIANT_FLAGS,
            }
    except codec.CodecError as err:
        d = err.diagnostic.to_dict()
        if d.get("entity_id") is None:
            d["entity_id"] = entity_id
        return _blocked_response(
            task_id=validated_tid,
            operation=validated_op,
            diagnostics=[d],
            return_stage=_extract_return_stage_from_diag(d),
            started=started,
            route="B",
        )


def _verify_loaded_b_route_artifacts(
    root_path: Path,
    *,
    task_id: int,
    reconciliation: dict[str, Any],
    readiness: dict[str, Any],
    operation: str | None = None,
    lock_mode: str = "none",
) -> dict[str, Any]:
    """Core B-route readiness & freshness verifier shared by verify CLI, load_task_readiness, and refresh."""
    started = time.monotonic()
    entity_id = str(task_id)
    diagnostics: list[dict[str, Any]] = []
    return_stages: list[str] = []
    invalidated_items: list[dict[str, Any]] = []

    def fail_verify(
        reason: str,
        *,
        code: codec.ReasonCode = codec.ReasonCode.SEMANTIC_ERROR,
        rstage: str = "5",
        expected: Any = None,
        actual: Any = None,
        resume_ref: str | None = None,
        inv_items: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        diag = _diag(
            code,
            stage=codec.Stage.BUNDLE,
            entity_id=entity_id,
            expected=expected if expected is not None else {"reason": reason, "return_stage": rstage},
            actual=actual if actual is not None else {"reason": reason, "return_stage": rstage},
            resume_ref=resume_ref,
        )
        all_diags = [*diagnostics, diag]
        final_stage = _earliest_stage([*return_stages, rstage]) or rstage
        return _blocked_response(
            task_id=task_id,
            operation=operation,
            diagnostics=all_diags,
            return_stage=final_stage,
            started=started,
            route="B",
            extra={
                "fresh": False,
                "reason": reason,
                "invalidated_items": list(inv_items or invalidated_items),
            },
        )

    # 1. Reject legacy capability-apply.pending.json immediately.
    if (root_path / task_resolver.CAP_PENDING).is_file():
        return fail_verify(
            "capability_apply_pending_recovery",
            code=codec.ReasonCode.PENDING,
            rstage="5",
            resume_ref=task_resolver.CAP_PENDING,
        )

    # 2. Story 3.3 origin check MUST pass as route="B".
    origin = task_resolver.resolve_task_origin(root_path, task_id, operation=operation)
    if not origin["ok"] or not origin["stable"] or origin["route"] != "B":
        diags = list(origin.get("diagnostics") or [])
        if diags:
            diagnostics.extend(diags)
            rstage = _earliest_stage([_extract_return_stage_from_diag(d) for d in diags]) or "3C"
        else:
            rstage = "3C"
        return fail_verify(
            f"b_route_origin_not_b:{origin.get('route')}",
            code=codec.ReasonCode.CONFLICT,
            rstage=rstage,
            resume_ref=task_resolver.ORIGINS_PATH,
        )

    # 3. Validate artifact shapes and forbid legacy A readiness on a B-route task.
    if type(readiness) is not dict or readiness.get("schema_version") != READINESS_SCHEMA:
        return fail_verify("chapter5_readiness_schema_invalid", code=codec.ReasonCode.SCHEMA_MISMATCH, rstage="5")
    if type(reconciliation) is not dict or reconciliation.get("schema_version") != RECONCILIATION_SCHEMA:
        return fail_verify("chapter5_reconciliation_missing_or_invalid", code=codec.ReasonCode.SCHEMA_MISMATCH, rstage="5")
    if not _artifact_has_b_route_marker(readiness) or not _artifact_has_b_route_marker(reconciliation):
        return fail_verify(
            "b_route_readiness_required_no_legacy_fallback",
            code=codec.ReasonCode.SCHEMA_MISMATCH,
            rstage="5",
            expected="B-route Chapter 5 readiness bound to InputSet",
            actual="legacy A-only readiness",
        )
    if str(readiness.get("task_id") or "") != entity_id or str(reconciliation.get("task_id") or "") != entity_id:
        return fail_verify("chapter5_readiness_task_mismatch", code=codec.ReasonCode.MAPPING_MISMATCH, rstage="5")

    # Enforce mandatory non-escalation flags (cannot forge runtime_verified or default_b_enabled).
    if readiness.get("runtime_verified") is not False or reconciliation.get("runtime_verified") is not False:
        return fail_verify("b_route_runtime_verified_must_be_false", code=codec.ReasonCode.SEMANTIC_ERROR, rstage="5")
    if readiness.get("default_b_enabled") is not False or reconciliation.get("default_b_enabled") is not False:
        return fail_verify("b_route_default_b_enabled_must_be_false", code=codec.ReasonCode.SEMANTIC_ERROR, rstage="5")

    # 4. Cryptographic reconciliation_sha256 check (defeats timestamp or field spoofing!).
    expected_rec_sha = "sha256:" + _canonical_sha(reconciliation)
    if str(readiness.get("reconciliation_sha256") or "") != expected_rec_sha:
        return fail_verify(
            "chapter5_readiness_reconciliation_stale",
            code=codec.ReasonCode.DIGEST_MISMATCH,
            rstage="5",
            expected=expected_rec_sha,
            actual=readiness.get("reconciliation_sha256"),
        )
    if readiness.get("extraction_b_snapshot_id") != reconciliation.get("extraction_b_snapshot_id"):
        return fail_verify("chapter5_readiness_snapshot_mismatch", code=codec.ReasonCode.DIGEST_MISMATCH, rstage="5")
    if readiness.get("cache_key") != reconciliation.get("cache_key"):
        return fail_verify("chapter5_cache_key_mismatch", code=codec.ReasonCode.DIGEST_MISMATCH, rstage="5")

    # Check verdict consistency between readiness and reconciliation (catches readiness.json tampering!).
    if readiness.get("readiness") != reconciliation.get("readiness_verdict"):
        return fail_verify("chapter5_readiness_verdict_tampered", code=codec.ReasonCode.DIGEST_MISMATCH, rstage="5")
    if readiness.get("closure_allowed") != reconciliation.get("closure_allowed"):
        return fail_verify("chapter5_closure_allowed_tampered", code=codec.ReasonCode.DIGEST_MISMATCH, rstage="5")
    if reconciliation.get("global_audit_completed") is not True:
        return fail_verify("chapter5_global_audit_incomplete", code=codec.ReasonCode.SEMANTIC_ERROR, rstage="5")

    summary = reconciliation.get("summary") if type(reconciliation.get("summary")) is dict else {}
    if int(summary.get("blocking_count") or 0) != 0 or readiness.get("blocking_findings"):
        return fail_verify("chapter5_readiness_blocked", code=codec.ReasonCode.SEMANTIC_ERROR, rstage=str(readiness.get("return_stage") or "5"))

    verdict = str(readiness.get("readiness") or "")
    if verdict not in {"READY", "CONCERNS"}:
        return fail_verify("chapter5_readiness_blocked", code=codec.ReasonCode.SEMANTIC_ERROR, rstage=str(readiness.get("return_stage") or "5"))
    if readiness.get("closure_allowed") is not True:
        return fail_verify("chapter5_concerns_not_allowed", code=codec.ReasonCode.SEMANTIC_ERROR, rstage="5")

    # 5. If CONCERNS, re-verify P0/P1 floor and docs/technical-debt.md persistence!
    if verdict == "CONCERNS":
        if readiness.get("allow_concerns") is not True:
            return fail_verify("chapter5_concerns_not_policy_allowed", code=codec.ReasonCode.SEMANTIC_ERROR, rstage="5")
        concerns = list(readiness.get("concerns") or [])
        for c in concerns:
            sev = str(c.get("priority") or c.get("severity") or "").upper()
            cat = str(c.get("category") or c.get("finding_type") or "").lower()
            if sev in P0_P1_SEVERITIES or cat in P1_FLOOR_CATEGORIES or sev not in DEFERRABLE_SEVERITIES:
                return fail_verify("chapter5_p1_floor_violated", code=codec.ReasonCode.SEMANTIC_ERROR, rstage="5")
        all_rec, _rec_ids, missing_ids = verify_technical_debt_recorded(root_path, task_id, concerns)
        if not all_rec:
            return fail_verify(
                "chapter5_technical_debt_unrecorded",
                code=codec.ReasonCode.SEMANTIC_ERROR,
                rstage="5",
                expected="all deferred P2..P4 findings recorded in docs/technical-debt.md",
                actual={"missing_finding_ids": missing_ids},
                resume_ref=TECHNICAL_DEBT_PATH,
            )

    # 6. Validate frozen InputSet baseline & live Story 3.5 InputSet comparison (anti-timestamp-spoofing!).
    frozen_digest = readiness.get("input_set_digest")
    frozen_baseline = reconciliation.get("input_set_baseline")
    if (
        type(frozen_digest) is not str
        or _DIGEST_RE.fullmatch(frozen_digest) is None
        or frozen_digest != reconciliation.get("input_set_digest")
        or type(frozen_baseline) is not dict
    ):
        return fail_verify("chapter5_input_set_binding_invalid", code=codec.ReasonCode.SCHEMA_VALIDATION_FAILED, rstage="5")

    try:
        if lock_mode == "scope":
            with input_set.guarded_input_set(
                root_path, task_id, operation=operation, baseline=frozen_baseline
            ) as handle:
                live_iset = handle.revalidate()
        else:
            live_iset = input_set.resolve_input_set(
                root_path, task_id, operation=operation, baseline=frozen_baseline
            )
    except codec.CodecError as err:
        d = err.diagnostic.to_dict()
        diagnostics.append(d)
        return fail_verify(
            "chapter5_input_set_stale",
            code=err.diagnostic.reason_code,
            rstage=_extract_return_stage_from_diag(d),
            resume_ref=d.get("resume_ref"),
        )

    if not live_iset["ok"] or not live_iset["stable"] or not live_iset["valid_input_set"]:
        freshness = live_iset.get("freshness") or {}
        inv = list(freshness.get("invalidated_items") or [])
        rstage = live_iset.get("return_stage") or freshness.get("return_stage") or "5"
        diagnostics.extend(live_iset.get("diagnostics") or [])
        return fail_verify(
            "chapter5_input_set_stale",
            code=codec.ReasonCode.INPUT_STALE,
            rstage=rstage,
            expected={"input_set_digest": frozen_digest, "return_stage": rstage},
            actual={"input_set_digest": live_iset.get("input_set_digest"), "return_stage": rstage},
            inv_items=inv,
        )

    if live_iset["input_set_digest"] != frozen_digest:
        return fail_verify(
            "chapter5_input_set_digest_mismatch",
            code=codec.ReasonCode.INPUT_STALE,
            rstage=live_iset.get("return_stage") or "5",
            expected=frozen_digest,
            actual=live_iset["input_set_digest"],
        )

    # 7. Verify frozen applicable_set_digest, plan_refs, binding_refs, scope_ids match live Story 3.3/3.5.
    if readiness.get("applicable_set_digest") != origin["applicable_set_digest"]:
        return fail_verify(
            "chapter5_applicable_set_digest_stale",
            code=codec.ReasonCode.INPUT_STALE,
            rstage="3B",
            expected=readiness.get("applicable_set_digest"),
            actual=origin["applicable_set_digest"],
        )
    if readiness.get("plan_refs") != origin["plan_refs"]:
        return fail_verify("chapter5_plan_refs_stale", code=codec.ReasonCode.INPUT_STALE, rstage="3B")
    if readiness.get("binding_refs") != origin["binding_refs"]:
        return fail_verify("chapter5_binding_refs_stale", code=codec.ReasonCode.INPUT_STALE, rstage="5")
    if readiness.get("scope_ids") != live_iset["scope_ids"]:
        return fail_verify("chapter5_scope_ids_stale", code=codec.ReasonCode.INPUT_STALE, rstage="5")

    # 7b. Re-verify raw SHA-256 digests of all extra decisions-referenced authority & test files!
    dec_digests = reconciliation.get("decision_referenced_file_digests")
    if dec_digests is not None:
        if type(dec_digests) is not dict:
            return fail_verify(
                "chapter5_decision_referenced_digests_invalid",
                code=codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
                rstage="5",
            )
        for rel_path_raw, meta in sorted(dec_digests.items()):
            if type(rel_path_raw) is not str or type(meta) is not dict or type(meta.get("raw_digest")) is not str:
                return fail_verify(
                    "chapter5_decision_referenced_digests_invalid",
                    code=codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
                    rstage="5",
                )
            rstage_meta = str(meta.get("return_stage") or "")
            low_p = rel_path_raw.replace("\\", "/").casefold()
            if low_p.startswith(("game.core/contracts/", "docs/adr/", "docs/architecture/overlays/")):
                file_rstage = "4"
            elif rstage_meta in STAGE_RANK:
                file_rstage = rstage_meta
            else:
                file_rstage = "5"
            try:
                norm_p = preflight.path(rel_path_raw.replace("\\", "/"))
                target_f = inventory.safe_input(root_path, norm_p, allow_logs=norm_p.startswith("logs/"))
            except (codec.CodecError, ValueError, OSError):
                return fail_verify(
                    "chapter5_decision_referenced_file_unsafe",
                    code=codec.ReasonCode.UNSAFE_PATH,
                    rstage=file_rstage,
                    resume_ref=rel_path_raw,
                )
            if not target_f.is_file():
                return fail_verify(
                    "chapter5_decision_referenced_file_missing",
                    code=codec.ReasonCode.INPUT_STALE,
                    rstage=file_rstage,
                    expected={"path": norm_p, "raw_digest": meta["raw_digest"], "return_stage": file_rstage},
                    actual={"path": norm_p, "exists": False, "return_stage": file_rstage},
                    resume_ref=norm_p,
                )
            live_dg = codec.raw_digest(target_f.read_bytes())
            if live_dg != meta["raw_digest"]:
                return fail_verify(
                    "chapter5_decision_referenced_file_stale",
                    code=codec.ReasonCode.INPUT_STALE,
                    rstage=file_rstage,
                    expected={"path": norm_p, "raw_digest": meta["raw_digest"], "return_stage": file_rstage},
                    actual={"path": norm_p, "raw_digest": live_dg, "return_stage": file_rstage},
                    resume_ref=norm_p,
                )

    # 8. Verify every applicable binding is still stage="5", re-verify 3A proofs read-only, and compute live reverification.
    try:
        (
            loaded_plans,
            loaded_bindings,
            sealed_digests,
            _views,
            master_tasks,
            _back_by_tid,
            _gameplay_by_tid,
        ) = _load_plan_and_binding_bundle(root_path, origin)
        for pid, (bref, _braw, bdoc, _mapping) in sorted(loaded_bindings.items()):
            bstage = str(bdoc.get("stage") or "")
            if bstage != "5":
                rstage = "4" if bstage == "3C" else "5"
                return fail_verify(
                    f"chapter5_binding_not_stage5:{pid}:{bstage}",
                    code=codec.ReasonCode.SEMANTIC_ERROR,
                    rstage=rstage,
                    resume_ref=bref["path"],
                )
        prior_audit_refs = list((reconciliation.get("source_audit_reuse") or {}).get("verified_full_audit_refs") or [])
        audit_summary = verify_3a_source_proofs(
            root_path,
            loaded_plans=loaded_plans,
            sealed_digests=sealed_digests,
            explicit_audit_refs=prior_audit_refs,
            require_full_audit_proof=bool(prior_audit_refs),
            entity_id=entity_id,
        )
        bound_manifests = _load_bound_manifests(root_path, loaded_bindings, entity_id=entity_id)
        live_reverification = _compute_live_reverification(
            task_id,
            master_tasks=master_tasks,
            loaded_plans=loaded_plans,
            loaded_bindings=loaded_bindings,
            manifests=bound_manifests,
        )
    except codec.CodecError as err:
        d = err.diagnostic.to_dict()
        diagnostics.append(d)
        return fail_verify(
            f"chapter5_live_verification_failed:{err.diagnostic.reason_code.value}",
            code=err.diagnostic.reason_code,
            rstage=_extract_return_stage_from_diag(d),
            resume_ref=d.get("resume_ref"),
        )

    if live_reverification["requires_chapter6_reverification"] and readiness.get("old_done_covers_new_obligations") is True:
        return fail_verify(
            "chapter5_old_done_cannot_cover_new_obligations",
            code=codec.ReasonCode.SEMANTIC_ERROR,
            rstage="5",
        )

    elapsed = round(max(0.0, time.monotonic() - started), 6)
    enriched_readiness = deepcopy(readiness)
    enriched_readiness["requires_chapter6_reverification"] = bool(
        live_reverification["requires_chapter6_reverification"]
    )
    enriched_readiness["old_done_covers_new_obligations"] = False
    enriched_readiness["runtime_verified"] = False
    enriched_readiness["default_b_enabled"] = False

    return {
        "schema_version": B_ROUTE_SCHEMA,
        "ok": True,
        "status": "ok",
        "fresh": True,
        "reason": "ready",
        "route": "B",
        "task_id": task_id,
        "operation": operation,
        "readiness": verdict,
        "closure_allowed": True,
        "allow_concerns": bool(readiness.get("allow_concerns")),
        "requires_chapter6_reverification": bool(live_reverification["requires_chapter6_reverification"]),
        "old_done_covers_new_obligations": False,
        "reverification": live_reverification,
        "input_set_digest": frozen_digest,
        "applicable_set_digest": origin["applicable_set_digest"],
        "scope_ids": list(live_iset["scope_ids"]),
        "plan_refs": deepcopy(origin["plan_refs"]),
        "binding_refs": deepcopy(origin["binding_refs"]),
        "reconciliation_sha256": expected_rec_sha,
        "source_audit_reuse": audit_summary,
        "invalidated_items": [],
        "return_stage": None,
        "metrics": {
            "active_elapsed_seconds": elapsed,
            "model_invocation_count": 0,
            "source_audit_reused": bool(audit_summary["reused"]),
            "reused_3a_proof_count": int(audit_summary["reused_3a_proof_count"]),
            "return_stage": None,
        },
        "diagnostics": [],
        "readiness_doc": enriched_readiness,
        **INVARIANT_FLAGS,
    }


def verify_b_route_chapter5_readiness(
    root: Path | str,
    *,
    task_id: Any,
    readiness_path: Path | str | None = None,
    reconciliation_path: Path | str | None = None,
    operation: str | None = None,
    lock_mode: str = "none",
) -> dict[str, Any]:
    """Read-only verify persisted B-route Chapter 5 readiness & InputSet freshness."""
    started = time.monotonic()
    validated_tid: int | None = None
    validated_op: str | None = None
    try:
        root_path = task_resolver._validate_root(Path(root))
        validated_tid = codec.validate_task_id(task_id)
        validated_op = task_resolver._validate_operation(operation)
        validated_lock = input_set._validate_lock_mode(lock_mode)
        if readiness_path is not None:
            rdy_file, rdy_rel = _validate_log_path(root_path, readiness_path, require_logs=False)
        else:
            rdy_file, rdy_rel = _validate_log_path(
                root_path, (DEFAULT_READINESS_DIR / f"task-{validated_tid}.json").as_posix(), require_logs=False
            )
    except codec.CodecError as err:
        d = err.diagnostic.to_dict()
        if d.get("entity_id") is None and validated_tid is not None:
            d["entity_id"] = str(validated_tid)
        return _blocked_response(
            task_id=validated_tid,
            operation=validated_op,
            diagnostics=[d],
            return_stage=_extract_return_stage_from_diag(d),
            started=started,
            extra={"fresh": False, "reason": "invalid_arguments", "invalidated_items": []},
        )

    entity_id = str(validated_tid)
    if not rdy_file.is_file():
        d = _diag(
            codec.ReasonCode.FILE_NOT_FOUND,
            stage=codec.Stage.PATH,
            entity_id=entity_id,
            expected={"readiness_path": rdy_rel, "return_stage": "5"},
            actual={"exists": False, "return_stage": "5"},
            resume_ref=rdy_rel,
        )
        return _blocked_response(
            task_id=validated_tid,
            operation=validated_op,
            diagnostics=[d],
            return_stage="5",
            started=started,
            route="B",
            readiness_path=rdy_rel,
            extra={"fresh": False, "reason": "b_route_chapter5_readiness_missing", "invalidated_items": []},
        )

    try:
        readiness_doc = codec.strict_json_loads(rdy_file.read_bytes())
    except (codec.CodecError, OSError) as err:
        d = (
            err.diagnostic.to_dict()
            if isinstance(err, codec.CodecError)
            else _diag(codec.ReasonCode.READ_ERROR, stage=codec.Stage.DECODE, entity_id=entity_id, actual=str(err))
        )
        return _blocked_response(
            task_id=validated_tid,
            operation=validated_op,
            diagnostics=[d],
            return_stage="5",
            started=started,
            route="B",
            readiness_path=rdy_rel,
            extra={"fresh": False, "reason": "chapter5_readiness_json_invalid", "invalidated_items": []},
        )

    # Resolve reconciliation_path from explicit arg OR readiness_doc["reconciliation_path"] OR default task-<id>.json.
    try:
        if reconciliation_path is not None:
            rec_file, rec_rel = _validate_log_path(root_path, reconciliation_path, require_logs=False)
        elif (
            type(readiness_doc) is dict
            and type(readiness_doc.get("reconciliation_path")) is str
            and readiness_doc["reconciliation_path"].strip()
        ):
            rec_file, rec_rel = _validate_log_path(
                root_path, readiness_doc["reconciliation_path"], require_logs=True
            )
        else:
            rec_file, rec_rel = _validate_log_path(
                root_path, (DEFAULT_RECONCILIATION_DIR / f"task-{validated_tid}.json").as_posix(), require_logs=False
            )
    except codec.CodecError as err:
        d = err.diagnostic.to_dict()
        if d.get("entity_id") is None:
            d["entity_id"] = entity_id
        return _blocked_response(
            task_id=validated_tid,
            operation=validated_op,
            diagnostics=[d],
            return_stage=_extract_return_stage_from_diag(d),
            started=started,
            route="B",
            readiness_path=rdy_rel,
            extra={"fresh": False, "reason": "invalid_reconciliation_path", "invalidated_items": []},
        )

    if not rec_file.is_file():
        d = _diag(
            codec.ReasonCode.FILE_NOT_FOUND,
            stage=codec.Stage.PATH,
            entity_id=entity_id,
            expected={"reconciliation_path": rec_rel, "return_stage": "5"},
            actual={"exists": False, "return_stage": "5"},
            resume_ref=rec_rel,
        )
        return _blocked_response(
            task_id=validated_tid,
            operation=validated_op,
            diagnostics=[d],
            return_stage="5",
            started=started,
            route="B",
            reconciliation_path=rec_rel,
            readiness_path=rdy_rel,
            extra={"fresh": False, "reason": "b_route_chapter5_reconciliation_missing", "invalidated_items": []},
        )

    try:
        reconciliation_doc = codec.strict_json_loads(rec_file.read_bytes())
    except (codec.CodecError, OSError) as err:
        d = (
            err.diagnostic.to_dict()
            if isinstance(err, codec.CodecError)
            else _diag(codec.ReasonCode.READ_ERROR, stage=codec.Stage.DECODE, entity_id=entity_id, actual=str(err))
        )
        return _blocked_response(
            task_id=validated_tid,
            operation=validated_op,
            diagnostics=[d],
            return_stage="5",
            started=started,
            route="B",
            reconciliation_path=rec_rel,
            readiness_path=rdy_rel,
            extra={"fresh": False, "reason": "chapter5_readiness_json_invalid", "invalidated_items": []},
        )

    result = _verify_loaded_b_route_artifacts(
        root_path,
        task_id=validated_tid,
        reconciliation=reconciliation_doc,
        readiness=readiness_doc,
        operation=validated_op,
        lock_mode=validated_lock,
    )
    result["reconciliation_path"] = rec_rel
    result["readiness_path"] = rdy_rel
    if type(result.get("readiness_doc")) is dict:
        result["readiness_doc"].setdefault("reconciliation_path", rec_rel)
        result["readiness_doc"]["readiness_path"] = rdy_rel
    return result


# ---------------------------------------------------------------------------
# Bridges for chapter5_semantic_reconciliation.py and refresh_chapter_knowledge.py
# ---------------------------------------------------------------------------


def validate_b_route_readiness_freshness(
    root: Path,
    *,
    task_id: str,
    reconciliation: dict[str, Any],
    readiness: dict[str, Any],
) -> tuple[bool, str]:
    """Bridge for chapter5_semantic_reconciliation.validate_chapter5_evidence_freshness."""
    root_path = Path(root).resolve()
    tid_str = _canonical_task_id_str(task_id)
    if _POS_INT_RE.fullmatch(tid_str) is None:
        return False, "b_route_task_id_invalid:return_stage=5"
    rec_doc = reconciliation
    if (
        (not rec_doc or type(rec_doc) is not dict)
        and type(readiness) is dict
        and type(readiness.get("reconciliation_path")) is str
        and readiness["reconciliation_path"].strip()
    ):
        try:
            rec_file, _rec_rel = _validate_log_path(root_path, readiness["reconciliation_path"], require_logs=True)
            if rec_file.is_file():
                loaded = codec.strict_json_loads(rec_file.read_bytes())
                if type(loaded) is dict:
                    rec_doc = loaded
        except (codec.CodecError, OSError):
            return False, "b_route_reconciliation_path_invalid:return_stage=5"
    verified = _verify_loaded_b_route_artifacts(
        root_path,
        task_id=int(tid_str),
        reconciliation=rec_doc,
        readiness=readiness,
        lock_mode="none",
    )
    if verified["ok"]:
        return True, "ready"
    rstage = verified.get("return_stage") or "5"
    reason = str(verified.get("reason") or "b_route_chapter5_readiness_blocked")
    return False, f"{reason}:return_stage={rstage}"


def load_b_route_task_readiness(
    root: Path,
    task_id: str,
    *,
    readiness_path: Path | str | None = None,
    reconciliation_path: Path | str | None = None,
    operation: str | None = None,
    lock_mode: str = "none",
) -> tuple[bool, dict[str, Any], str]:
    """Bridge for chapter5_semantic_reconciliation.load_task_readiness when B traces exist.

    Returns:
      - None if the task is verified frozen A (or explicit_not_enabled_a) with no B-route artifact,
        signaling the caller to run the legacy A readiness check.
      - (ok, payload, reason) directly for all B-route or blocked tasks (never falling back to legacy).
    """
    root_path = Path(root).resolve()
    tid_str = _canonical_task_id_str(task_id)
    if _POS_INT_RE.fullmatch(tid_str) is None:
        return False, {}, "b_route_task_id_invalid:return_stage=5"
    tid = int(tid_str)

    origin = task_resolver.resolve_task_origin(root_path, tid, operation=operation)
    rdy_preview: dict[str, Any] = {}
    try:
        if readiness_path is not None:
            rdy_file, _rdy_rel = _validate_log_path(root_path, readiness_path, require_logs=False)
        else:
            rdy_file = _readiness_path_for_task(root_path, tid)
        if rdy_file.is_file():
            loaded = codec.strict_json_loads(rdy_file.read_bytes())
            if type(loaded) is dict:
                rdy_preview = loaded
    except (codec.CodecError, OSError):
        rdy_preview = {}

    if origin["route"] == "blocked" or not origin["ok"] or not origin["stable"]:
        diags = list(origin.get("diagnostics") or [])
        rstage = _earliest_stage([_extract_return_stage_from_diag(d) for d in diags]) or "3C"
        first_code = diags[0]["reason_code"] if diags else "blocked"
        return (
            False,
            {
                "route": "blocked",
                "task_id": tid_str,
                "return_stage": rstage,
                "diagnostics": diags,
                **INVARIANT_FLAGS,
            },
            f"b_route_origin_blocked:{first_code}:return_stage={rstage}",
        )

    if origin["route"] in ("A", "explicit_not_enabled_a"):
        if _artifact_has_b_route_marker(rdy_preview):
            return (
                False,
                rdy_preview,
                f"b_route_readiness_route_mismatch:{origin['route']}",
            )
        # Verified A task with zero B obligations on this task: caller runs legacy A readiness check.
        return None  # type: ignore[return-value]

    # Route is "B": MUST pass full B-route Chapter 5 readiness verification (zero legacy fallback!).
    verified = verify_b_route_chapter5_readiness(
        root_path,
        task_id=tid,
        readiness_path=readiness_path,
        reconciliation_path=reconciliation_path,
        operation=operation,
        lock_mode=lock_mode,
    )
    if verified["ok"]:
        return True, verified["readiness_doc"], "ready"

    rstage = verified.get("return_stage") or "5"
    reason = str(verified.get("reason") or "b_route_chapter5_readiness_blocked")
    payload = dict(rdy_preview)
    payload.update(
        {
            "route": "B",
            "task_id": tid_str,
            "return_stage": rstage,
            "reconciliation_path": verified.get("reconciliation_path"),
            "readiness_path": verified.get("readiness_path"),
            "diagnostics": verified.get("diagnostics") or [],
            "invalidated_items": verified.get("invalidated_items") or [],
            **INVARIANT_FLAGS,
        }
    )
    return False, payload, f"{reason}:return_stage={rstage}"


def verify_b_route_closure_evidence(
    root: Path,
    *,
    reconciliation: dict[str, Any],
    readiness: dict[str, Any],
) -> tuple[dict[str, Any], bool, str]:
    """Bridge for refresh_chapter_knowledge.chapter5_closure_evidence on B-route tasks."""
    root_path = Path(root).resolve()
    tid_str = _canonical_task_id_str(readiness.get("task_id") or reconciliation.get("task_id"))
    source_revision = str(readiness.get("source_revision") or reconciliation.get("source_revision") or "")
    summary = reconciliation.get("summary") if type(reconciliation.get("summary")) is dict else {}

    errors: list[str] = []
    verified: dict[str, Any] | None = None
    if _POS_INT_RE.fullmatch(tid_str) is None:
        errors.append("b_route_task_id_invalid")
    else:
        verified = _verify_loaded_b_route_artifacts(
            root_path,
            task_id=int(tid_str),
            reconciliation=reconciliation,
            readiness=readiness,
            lock_mode="none",
        )
        if not verified["ok"]:
            rstage = verified.get("return_stage") or "5"
            errors.append(f"{verified.get('reason') or 'b_route_chapter5_readiness_blocked'}:return_stage={rstage}")

    report = {
        "schema_version": "chapter5.semantic-reconciliation-closure.v1",
        "stage": "closure",
        "source_revision": source_revision,
        "status": "passed" if not errors else "blocked",
        "blocking_counts": {
            "chapter5_readiness": len(errors),
            "missing": int(summary.get("missing") or 0),
            "partial": int(summary.get("partial") or 0),
            "invented": int(summary.get("invented") or 0),
            "conflicts": int(summary.get("conflicts") or 0),
            "orphan_delivery_semantic": int(summary.get("orphan_delivery_semantic") or 0),
            "orphan_acceptance": int(summary.get("orphan_acceptance") or 0),
        },
        "details": {
            "route": "B",
            "readiness": str(readiness.get("readiness") or ""),
            "closure_allowed": bool(verified["closure_allowed"]) if verified else False,
            "errors": errors,
            "extraction_b_snapshot_id": reconciliation.get("extraction_b_snapshot_id"),
            "input_set_digest": verified.get("input_set_digest") if verified else readiness.get("input_set_digest"),
            "applicable_set_digest": verified.get("applicable_set_digest") if verified else readiness.get("applicable_set_digest"),
            "requires_chapter6_reverification": bool(verified["requires_chapter6_reverification"]) if verified else False,
            "return_stage": verified.get("return_stage") if verified else "5",
            "diagnostics": verified.get("diagnostics") if verified else [],
            **INVARIANT_FLAGS,
        },
    }
    return report, not errors, ("verified_b_route_chapter5_readiness" if not errors else ",".join(errors))


def synthesize_b_route_refresh_inputs(
    root: Path,
    *,
    reconciliation: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Derive minimal workspace topology inputs for refresh_chapter_knowledge on pure B-route repos."""
    src_rev = str(readiness.get("source_revision") or reconciliation.get("source_revision") or "b-route")
    tid_str = _canonical_task_id_str(readiness.get("task_id") or reconciliation.get("task_id") or "0")
    input_digest = str(readiness.get("input_set_digest") or "")
    reqs = [
        {
            "requirement_id": rid,
            "statement": f"B-route requirement {rid}",
            "kind": "requirement",
            "delivery_relevant": True,
            "status": "active",
            "priority": "P1",
            "source_block_ids": [],
            "non_task_sinks": [],
        }
        for rid in sorted((reconciliation.get("acceptance_coverage") or {}).keys())
    ]
    return {
        "source_manifest": {
            "schema_version": "chapter3.source-manifest.v1",
            "source_revision": src_rev,
            "manifest_sha256": input_digest,
            "sources": [],
        },
        "ledger": {
            "schema_version": "newrouge.source-blocks.v1",
            "source_revision": src_rev,
            "source_manifest_sha256": input_digest,
            "blocks": [],
        },
        "semantics": {
            "schema_version": "newrouge.semantic-requirements.v1",
            "source_revision": src_rev,
            "source_manifest_sha256": input_digest,
            "requirements": reqs,
        },
        "capabilities": {
            "schema_version": "newrouge.capabilities.v1",
            "source_revision": src_rev,
            "capabilities": [],
        },
        "edges": {
            "schema_version": "newrouge.topology-edges.v1",
            "source_revision": src_rev,
            "edges": list(reconciliation.get("topology_edges") or []),
        },
        "candidates": {
            "schema_version": "newrouge.task-candidates.v1",
            "source_revision": src_rev,
            "candidates": [{"task_id": tid_str}],
        },
    }
