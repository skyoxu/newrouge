"""Read-only B-route defect classification, anti-disguise guard, repair delta governance, and handoff reporting.

Responsibilities (Story 3.10):
- Classify Chapter 6 repair defects cleanly into pure implementation defects vs definition,
  contract, state-ownership, handoff/binding, or verification-obligation changes, always
  producing auditable six-field Diagnostics and rationale.
- Admit pure implementation repairs ONLY when live Story 3.8/3.9 gate, Task mapping,
  Chapter 5 readiness, and Stage-5 obligations are valid; cite committed 3B plan_refs,
  binding_refs, applicable_flow_closure, input_set_digest, readiness_path, required local
  self-checks, and applicable regressions; NEVER blindly rerun 3A/3B and NEVER skip
  Chapter 5 readiness or applicable regressions.
- Block disguised definition changes immediately (weakened/deleted Acceptance or Refs:,
  free-text N/A or mvg_applicable=false/flow_applicable=false labels, illegal status=done
  flips while failing/blocked, deleted bound tests, [Fact(Skip=...)]/[Theory(Skip=...)]
  or test skip attributes, and unreviewed MVG manifest weakening via _weakens_baseline)
  and return a structured governed handoff to exact owning_stage (3A..5).
- Validate business-view repair task deltas without writing .taskmaster/tasks/*.json or
  allocating permanent IDs: integrate cleanly with Story 3.1/3.2 governance, preserve
  mature IDs/done/history/cumulative MVG manifests and accurate M:N Task<->Flow mappings,
  block synonymous duplicate repair tasks, block old done covering new obligations, and
  compute invalidated bindings and readiness tasks.
- Consume Story 3.9 durable cross-date signals to pinpoint defect recurrence, preserve
  cumulative retry budgets and failure history, reuse valid upstream artifacts across
  unrelated HEAD/scope/status changes, block candidate-regeneration or global Knowledge
  refresh masking, and ensure local repairs never claim Flow or milestone completion.
- Report an honest verification breakdown separating local PASS, runtime verification
  (runtime_verified=False), manual obligations, and incomplete obligations (kept
  pending/blocked); enforce Needs Fix and the P1 must-fix floor; record measured
  telemetry (active_elapsed_seconds, model_invocation_count, reused_upstream_artifacts,
  rework_count) with runtime_verified=False and default_b_enabled=False unconditionally.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any

import _b_route_chapter5_readiness as ch5_b
import _b_route_chapter6_gate as ch6_gate
import _b_route_chapter6_recovery as ch6_recovery
import _b_route_codec as codec
import _b_route_input_set as input_set
import _b_route_inventory as inventory
import _b_route_preflight as preflight
import _b_route_protection as protection
import _b_route_records as records
import _b_route_task_preview as task_preview
import _b_route_task_resolver as task_resolver
import update_mvg_baseline as mvg_update


SCHEMA = "newrouge.b-route-defect-routing.v1"
DEFECT_REPORT_SCHEMA = "newrouge.b-route-defect-handoff.v1"
DEFECT_INPUT_SCHEMA = "newrouge.b-route-defect-input.v1"
DELTA_INTENTS_SCHEMA = "newrouge.b-route-repair-delta-intents.v1"

INVARIANT_FLAGS = {
    "runtime_verified": False,
    "default_b_enabled": False,
}

STAGE_RANK = input_set.STAGE_RANK
VALID_FIX_THROUGH = ("P1", "P2", "P3")
SEVERITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3, "P4": 4}

_NA_LABEL_RE = re.compile(
    r"(?i)(?:mvg_applicable\s*=\s*false|flow_applicable\s*=\s*false|"
    r"\bmvg\s*:\s*n/?a\b|\bflow\s*:\s*n/?a\b|\bacceptance\s*:\s*n/?a\b|"
    r"\bverification\s*:\s*n/?a\b|\bexempt\s*:\s*n/?a\b)"
)

_REFS_TOKEN_RE = re.compile(r"Refs:\s*([^\r\n]+)", re.IGNORECASE)

_TEST_SKIP_PATTERNS = (
    re.compile(r"\[[^\]]*\b(?:Fact|Theory|SkippableFact|SkippableTheory)\b[^\]]*\bSkip\s*=", re.IGNORECASE),
    re.compile(r"\[\s*Ignore\b", re.IGNORECASE),
    re.compile(r"\bAssert\.Skip\s*\(", re.IGNORECASE),
    re.compile(r"^\s*#if\s+(?:false|0)\b", re.IGNORECASE | re.MULTILINE),
    re.compile(r"@\s*(?:unittest\.skip|pytest\.mark\.skip)\b", re.IGNORECASE),
    re.compile(r"\bskip_test\s*(?:=\s*True|\()", re.IGNORECASE),
)

_CS_TEST_ATTR_RE = re.compile(
    r"\[[^\]]*\b(?:Fact|Theory|SkippableFact|SkippableTheory|Test|TestMethod)\b",
    re.IGNORECASE,
)
_CS_TEST_FRAMEWORK_RE = re.compile(
    r"\busing\s+(?:Xunit|NUnit|Microsoft\.VisualStudio\.TestTools)\b",
    re.IGNORECASE,
)
_CS_TEST_METHOD_RE = re.compile(
    r"\bpublic\s+(?:async\s+)?(?:void|Task(?:<[^>]+>)?)\s+\w+\s*\(",
    re.IGNORECASE,
)
_GD_TEST_FUNC_RE = re.compile(r"^\s*func\s+test_", re.MULTILINE)

_REPAIR_STOPWORDS = frozenset(
    {
        "fix",
        "bug",
        "repair",
        "patch",
        "hotfix",
        "rework",
        "issue",
        "defect",
        "regression",
        "error",
        "failure",
        "broken",
        "in",
        "for",
        "the",
        "of",
        "on",
        "to",
        "a",
        "an",
        "and",
        "or",
        "with",
        "task",
        "flow",
    }
)

_REPAIR_HINT_WORDS = frozenset(
    {"fix", "bug", "repair", "patch", "hotfix", "rework", "issue", "defect", "regression"}
)

_GAP_CATEGORY_STAGE: dict[str, str] = {
    "source_gap": "3A",
    "source_change": "3A",
    "source_ledger": "3A",
    "prd_gdd_change": "3A",
    "gameplay_definition": "3B",
    "flow_definition": "3B",
    "command_definition": "3B",
    "state_ownership": "3B",
    "non_flow_applicability": "3B",
    "plan_definition": "3B",
    "task_mapping": "3C",
    "task_split": "3C",
    "task_merge": "3C",
    "new_responsibility": "3C",
    "task_definition": "3C",
    "contract": "4",
    "production_contract": "4",
    "adr": "4",
    "overlay": "4",
    "handoff_binding": "4",
    "binding_design": "4",
    "adapter_binding": "4",
    "implementation_binding": "4",
    "scene_binding": "4",
    "verification_obligation": "5",
    "mvg_manifest": "5",
    "other_verification_refs": "5",
    "chapter5_reconciliation": "5",
    "acceptance_obligation": "5",
}

_PURE_IMPL_PREFIXES = (
    "game.core/",
    "game.core.tests/",
    "game.godot/",
    "tests.godot/",
    "scripts/",
)

_OWNING_STAGE_COMMANDS: dict[str, str] = {
    "3A": "py -3 -B scripts/python/dev_cli.py b-route-sources --stage prepare --root .",
    "3B": "py -3 -B scripts/python/dev_cli.py b-route-adoption --stage review --operation-id <op-id> --root .",
    "3C": "py -3 -B scripts/python/dev_cli.py b-route-task-preview --plan-id <plan-id> --scope-id <scope-id> --audit-ref <audit-ref> --root .",
    "4": "py -3 -B scripts/python/dev_cli.py b-route-chapter4-binding --stage preview --operation-id <op-id> --root .",
    "5": "py -3 -B scripts/python/dev_cli.py b-route-stage5-obligations --stage preview --operation-id <op-id> --root .",
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


def _earliest_stage(stages: list[str | None], default: str | None = None) -> str | None:
    valid = [s for s in stages if s in STAGE_RANK]
    if not valid:
        return default
    return min(valid, key=lambda s: STAGE_RANK[s])


def _norm_rel(raw: str) -> str:
    s = str(raw or "").strip().replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    while "//" in s:
        s = s.replace("//", "/")
    return s


def _resolve_contained_path(
    root_path: Path,
    raw_path: str | Path,
    *,
    label: str,
    entity_id: str | None,
) -> tuple[Path | None, str | None, dict[str, Any] | None]:
    """Resolve a relative or absolute path strictly inside root_path with full reparse protection."""
    text = str(raw_path or "").strip()
    if not text:
        return None, None, None
    root_resolved = root_path.resolve()
    cand = Path(text)
    try:
        if cand.is_absolute():
            for ancestor in reversed((cand, *cand.parents)):
                inventory.no_reparse(ancestor)
            resolved = cand.resolve()
            rel = resolved.relative_to(root_resolved).as_posix()
            target = inventory.safe_input(root_resolved, rel, allow_logs=True)
        else:
            norm = _norm_rel(text)
            target = inventory.safe_input(root_resolved, norm, allow_logs=True)
            rel = target.relative_to(root_resolved).as_posix()
        return target, rel, None
    except (codec.CodecError, ValueError, OSError) as exc:
        diag = _diag(
            codec.ReasonCode.UNSAFE_PATH,
            stage=codec.Stage.PATH,
            entity_id=entity_id,
            expected=f"safe contained path inside repository root for {label}",
            actual={"path": text, "error": f"{type(exc).__name__}: {exc}"},
            resume_ref=text,
        )
        return None, text, diag


def _safe_load_json_arg(
    root_path: Path,
    raw_arg: dict[str, Any] | str | Path | None,
    *,
    label: str,
    entity_id: str | None,
) -> tuple[dict[str, Any] | None, str | None, dict[str, Any] | None]:
    """Safely load an optional dict or repo-contained JSON file without writes."""
    if raw_arg is None:
        return None, None, None
    if isinstance(raw_arg, dict):
        return deepcopy(raw_arg), None, None
    text = str(raw_arg).strip()
    if not text:
        return None, None, None
    target, rel, path_err = _resolve_contained_path(
        root_path, text, label=label, entity_id=entity_id
    )
    if path_err is not None or target is None:
        return None, rel, path_err
    if not os.path.lexists(target):
        diag = _diag(
            codec.ReasonCode.FILE_NOT_FOUND,
            stage=codec.Stage.PATH,
            entity_id=entity_id,
            expected=f"existing JSON file for {label}",
            actual={"path": rel, "exists": False},
            resume_ref=rel,
        )
        return None, rel, diag
    try:
        inventory.no_reparse(target)
        if not target.is_file():
            raise ValueError("not a regular file")
        parsed = codec.strict_json_loads(target.read_bytes())
        if not isinstance(parsed, dict):
            raise ValueError("JSON root must be an object")
        return parsed, rel, None
    except (codec.CodecError, OSError, ValueError) as exc:
        rc = exc.diagnostic.reason_code if isinstance(exc, codec.CodecError) else codec.ReasonCode.INVALID_JSON
        diag = _diag(
            rc,
            stage=codec.Stage.DECODE,
            entity_id=entity_id,
            expected=f"valid JSON object for {label}",
            actual={"path": rel, "error": f"{type(exc).__name__}: {exc}"},
            resume_ref=rel,
        )
        return None, rel, diag


def _validate_fix_through(raw: str | None, entity_id: str | None) -> tuple[str, dict[str, Any] | None]:
    val = str(raw or "P1").strip().upper()
    if val not in VALID_FIX_THROUGH:
        diag = _diag(
            codec.ReasonCode.INVALID_ENUM,
            stage=codec.Stage.CONTENT,
            entity_id=entity_id,
            expected={"fix_through": list(VALID_FIX_THROUGH), "min_must_fix_floor": "P1"},
            actual={"fix_through": val, "violates_p1_floor": val == "P0"},
            resume_ref="DELIVERY_PROFILE.md",
        )
        return val, diag
    return val, None


def _classify_path(rel_path: str, *, root_path: Path | None = None) -> tuple[str, str]:
    """Return (classification, owning_stage_or_impl) for a single normalized repo-relative path."""
    norm = _norm_rel(rel_path)
    low = norm.lower()
    if (
        low.startswith("sources/")
        or low.startswith("docs/prd/")
        or low.startswith("docs/gdd/")
        or low == ".taskmaster/docs/prd.txt"
        or low == "docs/workflows/chapter3-source-set.json"
        or low.startswith("logs/ci/b-route-sources/")
        or low.startswith("logs/ci/b-route-source-audit/")
    ):
        return "definition", "3A"
    if (
        low.startswith("docs/planning/b-route/plans/")
        or low == "docs/planning/b-route/catalog.v1.json"
        or low == "docs/planning/b-route/policy.v1.json"
        or low.startswith("docs/planning/b-route/commits/")
    ):
        return "definition", "3B"
    if (
        low.startswith(".taskmaster/tasks/")
        or low == "docs/planning/b-route/task-origins.v1.json"
    ):
        return "definition", "3C"
    if low.startswith("docs/planning/b-route/bindings/"):
        if root_path is not None:
            bfile = root_path / norm
            if bfile.is_file():
                bdoc = ch6_recovery._safe_read_json(bfile)
                if isinstance(bdoc, dict):
                    stg = str(bdoc.get("stage") or "").strip().upper()
                    if stg in {"3C", "4", "5"}:
                        return "definition", stg
        return "definition", "4"
    if (
        low.startswith("game.core/contracts/")
        or low.startswith("docs/adr/")
        or low.startswith("docs/architecture/overlays/")
        or low.startswith("docs/architecture/base/")
        or low.startswith("scenes/")
    ):
        return "definition", "4"
    if (
        low.startswith("docs/testing/mvg/")
        or low.startswith("docs/testing/")
        or low.startswith("logs/ci/chapter5/")
    ):
        return "definition", "5"
    if any(low.startswith(prefix) for prefix in _PURE_IMPL_PREFIXES):
        return "pure_implementation", "6"
    # Harness workflow/agent/knowledge docs and logs are non-product repo docs, not Task definitions.
    if (
        low.startswith("docs/workflows/")
        or low.startswith("docs/agents/")
        or low.startswith("docs/knowledge/")
        or low.startswith("logs/")
        or low.startswith("_bmad-output/")
        or low.startswith(".github/")
    ):
        return "pure_implementation", "6"
    # Fail closed on unrecognized planning/taskmaster governance paths.
    if low.startswith("docs/planning/") or low.startswith(".taskmaster/"):
        return "definition", "4"
    return "pure_implementation", "6"


def _extract_refs_from_acceptance(items: list[str]) -> list[str]:
    refs: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        for match in _REFS_TOKEN_RE.finditer(item):
            tail = match.group(1)
            for token in re.split(r"[\s,;]+", tail):
                cleaned = _norm_rel(token.strip("`\"'()[]"))
                if cleaned and ("/" in cleaned or cleaned.endswith((".cs", ".gd", ".md", ".json", ".py"))):
                    refs.append(cleaned)
    return sorted(set(refs))


def _load_triplet_for_task(root_path: Path, tid: int) -> dict[str, Any]:
    out: dict[str, Any] = {
        "master_doc": None,
        "back_doc": None,
        "gameplay_doc": None,
        "master_task": None,
        "back_task": None,
        "gameplay_task": None,
        "all_views": [],
    }
    for key, rel in task_resolver.TRIPLET.items():
        p = root_path / rel
        if not p.is_file():
            continue
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        out[f"{key}_doc"] = doc
        if key == "master" and isinstance(doc, dict):
            tasks = ((doc.get("master") or {}).get("tasks") or []) if isinstance(doc.get("master"), dict) else []
            for row in tasks:
                if isinstance(row, dict):
                    try:
                        if int(row.get("id")) == tid:
                            out["master_task"] = row
                            break
                    except (TypeError, ValueError):
                        continue
        elif isinstance(doc, list):
            for row in doc:
                if isinstance(row, dict):
                    out["all_views"].append((key, row))
                    try:
                        if int(row.get("taskmaster_id")) == tid:
                            out[f"{key}_task"] = row
                    except (TypeError, ValueError):
                        continue
    return out


def _extract_owned_ref_paths(ref_obj: Any) -> list[str]:
    paths: list[str] = []
    if isinstance(ref_obj, str) and ref_obj.strip():
        paths.append(_norm_rel(ref_obj))
    elif isinstance(ref_obj, dict):
        if isinstance(ref_obj.get("files"), list):
            for frow in ref_obj["files"]:
                if isinstance(frow, dict) and str(frow.get("path") or "").strip():
                    paths.append(_norm_rel(str(frow["path"])))
        raw_ref = str(ref_obj.get("path") or ref_obj.get("ref") or "").strip()
        if raw_ref and not paths:
            paths.append(_norm_rel(raw_ref))
    return paths


def _collect_bound_obligations(
    root_path: Path,
    tid: int,
    triplet_info: dict[str, Any],
    gate_res: dict[str, Any] | None,
) -> dict[str, Any]:
    """Extract committed plan_refs, binding_refs, flows, tests, contracts, manifests, and manual obligations."""
    bound_test_files: set[str] = set()
    planned_test_files: set[str] = set()
    other_verification_refs: set[str] = set()
    applicable_flows: set[str] = set()
    manifest_paths: list[str] = []
    manual_obligations: list[str] = []
    acceptance_items: list[str] = []

    for view_key in ("back_task", "gameplay_task"):
        row = triplet_info.get(view_key)
        if not isinstance(row, dict):
            continue
        for acc in row.get("acceptance") or []:
            if isinstance(acc, str) and acc.strip():
                acceptance_items.append(acc.strip())
        for ref in _extract_refs_from_acceptance(list(row.get("acceptance") or [])):
            bound_test_files.add(ref)
        for tref in row.get("test_refs") or []:
            if isinstance(tref, str) and tref.strip():
                bound_test_files.add(_norm_rel(tref))

    if isinstance(gate_res, dict):
        stage5 = gate_res.get("stage5_summary")
        if isinstance(stage5, dict):
            for prow in stage5.get("plans") or []:
                if not isinstance(prow, dict):
                    continue
                for fid in prow.get("flow_ids") or []:
                    if isinstance(fid, str) and fid.strip():
                        applicable_flows.add(fid.strip())
                for mp_item in prow.get("manifest_paths") or []:
                    if isinstance(mp_item, str) and mp_item.strip():
                        manifest_paths.append(_norm_rel(mp_item))
                mpath = prow.get("manifest_path")
                if isinstance(mpath, str) and mpath.strip():
                    manifest_paths.append(_norm_rel(mpath))
                for opath in prow.get("other_verification_paths") or []:
                    if isinstance(opath, str) and opath.strip():
                        other_verification_refs.add(_norm_rel(opath))
                for oref in prow.get("other_verification_refs") or []:
                    for op in _extract_owned_ref_paths(oref):
                        other_verification_refs.add(op)
        for bref in gate_res.get("binding_refs") or []:
            if not isinstance(bref, dict) or not bref.get("path"):
                continue
            bdoc = ch6_recovery._safe_read_json(root_path / str(bref["path"]))
            if not isinstance(bdoc, dict):
                continue
            for mref in bdoc.get("manifest_refs") or []:
                for mp in _extract_owned_ref_paths(mref):
                    manifest_paths.append(mp)
            for row in bdoc.get("mvg_manifests") or []:
                for mp in _extract_owned_ref_paths(row):
                    manifest_paths.append(mp)
            for oref in bdoc.get("other_verification_refs") or []:
                for op in _extract_owned_ref_paths(oref):
                    other_verification_refs.add(op)
            for row in bdoc.get("flows") or []:
                if isinstance(row, dict) and row.get("flow_id"):
                    applicable_flows.add(str(row["flow_id"]))

            task_obligation_ids: set[str] = set()
            matched_task_mapping = False
            for tmap in bdoc.get("task_mappings") or []:
                if not isinstance(tmap, dict):
                    continue
                try:
                    if int(tmap.get("task_id")) != tid:
                        continue
                except (TypeError, ValueError):
                    continue
                matched_task_mapping = True
                for fid in tmap.get("flow_ids") or []:
                    if isinstance(fid, str) and fid.strip():
                        applicable_flows.add(fid.strip())
                for oid in tmap.get("obligation_ids") or []:
                    if isinstance(oid, str) and oid.strip():
                        task_obligation_ids.add(oid.strip())

            for ob in bdoc.get("obligations") or []:
                if not isinstance(ob, dict):
                    continue
                oid = str(ob.get("id") or "").strip()
                if matched_task_mapping and task_obligation_ids and oid not in task_obligation_ids:
                    continue
                if matched_task_mapping and not task_obligation_ids:
                    continue
                for fid in ob.get("flow_ids") or []:
                    if isinstance(fid, str) and fid.strip():
                        applicable_flows.add(fid.strip())
                for vref in ob.get("verification_refs") or []:
                    for vp in _extract_owned_ref_paths(vref):
                        if vp.lower().startswith("docs/testing/mvg/") and vp.lower().endswith(".json"):
                            manifest_paths.append(vp)
                        else:
                            other_verification_refs.add(vp)

            for trow in bdoc.get("task_bindings") or bdoc.get("tasks") or []:
                if not isinstance(trow, dict):
                    continue
                if trow.get("task_id") is not None:
                    try:
                        if int(trow["task_id"]) != tid:
                            continue
                    except (TypeError, ValueError):
                        pass
                for oref in trow.get("other_verification_refs") or []:
                    for op in _extract_owned_ref_paths(oref):
                        other_verification_refs.add(op)
                for mzone in trow.get("ui_manual_zones") or []:
                    if isinstance(mzone, str) and mzone.strip():
                        manual_obligations.append(mzone.strip())

    # Inspect ONLY bound MVG manifests (NEVER glob unrelated manifests for non-Flow tasks!).
    manifest_docs: dict[str, dict[str, Any]] = {}
    seen_manifests: list[str] = []
    for mp in manifest_paths:
        if mp in seen_manifests:
            continue
        seen_manifests.append(mp)
        mdoc = ch6_recovery._safe_read_json(root_path / mp)
        if not isinstance(mdoc, dict):
            continue
        manifest_docs[mp] = mdoc
        cov = mdoc.get("coverage") if isinstance(mdoc.get("coverage"), dict) else {}
        for claim in cov.get("excluded_claims") or []:
            if isinstance(claim, str) and claim.strip():
                manual_obligations.append(claim.strip())
        task_flows_in_manifest: set[str] = set()
        task_test_ids: set[str] = set()
        for frow in mdoc.get("flows") or []:
            if not isinstance(frow, dict):
                continue
            ftids = set()
            for ft in frow.get("task_ids") or []:
                try:
                    ftids.add(int(ft))
                except (TypeError, ValueError):
                    pass
            if tid in ftids:
                fid = str(frow.get("id") or "").strip()
                if fid:
                    applicable_flows.add(fid)
                    task_flows_in_manifest.add(fid)
                for test_id in frow.get("test_ids") or []:
                    if isinstance(test_id, str) and test_id.strip():
                        task_test_ids.add(test_id.strip())
        for trow in mdoc.get("tests") or []:
            if not isinstance(trow, dict):
                continue
            test_id = str(trow.get("id") or "").strip()
            tpath = _norm_rel(str(trow.get("path") or ""))
            state = str(trow.get("state") or "implemented").strip().lower()
            if not task_test_ids or test_id not in task_test_ids:
                continue
            if not tpath:
                continue
            if state == "planned":
                planned_test_files.add(tpath)
                bound_test_files.discard(tpath)
            else:
                bound_test_files.add(tpath)

    # Remove planned tests from implemented set if explicitly listed as planned.
    implemented_tests = sorted(bound_test_files - planned_test_files - other_verification_refs)
    return {
        "acceptance_items": acceptance_items,
        "implemented_test_files": implemented_tests,
        "planned_test_files": sorted(planned_test_files),
        "other_verification_refs": sorted(other_verification_refs),
        "applicable_flow_ids": sorted(applicable_flows),
        "manifest_paths": seen_manifests,
        "manifest_docs": manifest_docs,
        "manual_obligations": sorted(set(manual_obligations)),
    }


def _scan_text_for_skip(content: str) -> list[str]:
    hits: list[str] = []
    for pat in _TEST_SKIP_PATTERNS:
        for m in pat.finditer(content):
            hits.append(m.group(0).strip())
    return hits


def _strip_code_comments(tpath: str, content: str) -> str:
    low = tpath.lower()
    if low.endswith(".cs"):
        no_block = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
        return re.sub(r"//[^\r\n]*", "", no_block)
    if low.endswith((".gd", ".py")):
        return re.sub(r"#[^\r\n]*", "", content)
    return content


def _detect_gutted_test_file(
    tpath: str,
    content: str,
    *,
    previous_content: str | None = None,
) -> str | None:
    """Detect empty, comment-only, or gutted bound .cs/.gd test files."""
    low = tpath.lower()
    if not low.endswith((".cs", ".gd")):
        return None
    stripped = _strip_code_comments(tpath, content).strip()
    if not stripped:
        return "empty_or_comment_only_test_file"
    if low.endswith(".cs"):
        has_active_attr = bool(_CS_TEST_ATTR_RE.search(stripped))
        has_active_method = bool(_CS_TEST_METHOD_RE.search(stripped))
        if not has_active_attr and _CS_TEST_ATTR_RE.search(content):
            return "all_test_attributes_commented_out"
        if _CS_TEST_FRAMEWORK_RE.search(stripped) and not has_active_attr and not has_active_method:
            return "xunit_test_file_missing_executable_tests"
        if previous_content is not None:
            prev_stripped = _strip_code_comments(tpath, previous_content)
            prev_had_tests = bool(_CS_TEST_ATTR_RE.search(prev_stripped) or _CS_TEST_METHOD_RE.search(prev_stripped))
            if prev_had_tests and not has_active_attr and not has_active_method:
                return "test_declarations_gutted"
    elif low.endswith(".gd"):
        if not _GD_TEST_FUNC_RE.search(stripped):
            return "gdunit_test_file_missing_test_methods"
    return None


def _detect_disguise_violations(
    root_path: Path,
    tid: int,
    *,
    triplet_info: dict[str, Any],
    obligations: dict[str, Any],
    defect_input: dict[str, Any] | None,
    run_baseline: dict[str, Any] | None,
    durable_signals: dict[str, Any],
    latest_run_status: str,
) -> list[dict[str, Any]]:
    """Run hard anti-disguise checks against weakening acceptance, N/A labels, illegal done flips, and test deletion/skips."""
    entity_id = str(tid)
    violations: list[dict[str, Any]] = []
    di = defect_input if isinstance(defect_input, dict) else {}

    # 1. Free-text N/A / mvg_applicable=false / flow_applicable=false labels in live triplet or proposed edits.
    na_labels = list(ch6_gate._detect_task_na_labels(root_path, tid))
    for view_key in ("master_task", "back_task", "gameplay_task"):
        row = triplet_info.get(view_key)
        if not isinstance(row, dict):
            continue
        blob = json.dumps(row, ensure_ascii=False)
        for m in _NA_LABEL_RE.finditer(blob):
            na_labels.append(m.group(0))
    prop_edits = di.get("proposed_task_edits") if isinstance(di.get("proposed_task_edits"), dict) else {}
    if prop_edits:
        if prop_edits.get("mvg_applicable") is False or prop_edits.get("flow_applicable") is False:
            na_labels.append("proposed_mvg_or_flow_applicable=false")
        prop_blob = json.dumps(prop_edits, ensure_ascii=False)
        for m in _NA_LABEL_RE.finditer(prop_blob):
            na_labels.append(m.group(0))
    if na_labels:
        violations.append(
            {
                "kind": "free_text_na_exemption",
                "owning_stage": "5",
                "diagnostic": _diag(
                    codec.ReasonCode.SEMANTIC_ERROR,
                    stage=codec.Stage.CONTENT,
                    entity_id=entity_id,
                    expected={"free_text_na_or_exemption_labels": [], "return_stage": "5"},
                    actual={"detected_labels": sorted(set(na_labels)), "return_stage": "5"},
                    resume_ref=task_resolver.TRIPLET["back"],
                ),
            }
        )

    # 2. Weakening or deleting Acceptance items / Refs: / test_refs across BOTH back and gameplay views.
    if prop_edits:
        target_view = str(prop_edits.get("view") or "").strip().lower()
        checked_views = (target_view,) if target_view in {"back", "gameplay"} else ("back", "gameplay")
        for vname in checked_views:
            live_row = triplet_info.get(f"{vname}_task")
            if not isinstance(live_row, dict):
                continue
            view_edit = prop_edits.get(vname) if isinstance(prop_edits.get(vname), dict) else prop_edits
            live_acc = [str(x).strip() for x in (live_row.get("acceptance") or []) if str(x).strip()]
            live_refs = set(_extract_refs_from_acceptance(live_acc))
            live_trefs = {_norm_rel(str(x)) for x in (live_row.get("test_refs") or []) if str(x).strip()}
            if "acceptance" in view_edit and isinstance(view_edit["acceptance"], list):
                prop_acc = [str(x).strip() for x in view_edit["acceptance"] if str(x).strip()]
                prop_refs = set(_extract_refs_from_acceptance(prop_acc))
                missing_acc = [item for item in live_acc if item not in prop_acc]
                missing_refs = sorted(live_refs - prop_refs)
                if len(prop_acc) < len(live_acc) or missing_acc or missing_refs:
                    violations.append(
                        {
                            "kind": "acceptance_weakened_or_deleted",
                            "owning_stage": "5",
                            "diagnostic": _diag(
                                codec.ReasonCode.CONFLICT,
                                stage=codec.Stage.CONTENT,
                                entity_id=entity_id,
                                expected={"view": vname, "preserved_acceptance_count": len(live_acc), "preserved_refs": sorted(live_refs), "return_stage": "5"},
                                actual={"view": vname, "proposed_acceptance_count": len(prop_acc), "missing_acceptance": missing_acc, "missing_refs": missing_refs, "return_stage": "5"},
                                resume_ref=task_resolver.TRIPLET[vname],
                            ),
                        }
                    )
            if "test_refs" in view_edit and isinstance(view_edit["test_refs"], list):
                prop_trefs = {_norm_rel(str(x)) for x in view_edit["test_refs"] if str(x).strip()}
                removed_trefs = sorted(live_trefs - prop_trefs)
                if removed_trefs:
                    violations.append(
                        {
                            "kind": "test_refs_removed",
                            "owning_stage": "5",
                            "diagnostic": _diag(
                                codec.ReasonCode.CONFLICT,
                                stage=codec.Stage.CONTENT,
                                entity_id=entity_id,
                                expected={"view": vname, "preserved_test_refs": sorted(live_trefs), "return_stage": "5"},
                                actual={"view": vname, "removed_test_refs": removed_trefs, "return_stage": "5"},
                                resume_ref=task_resolver.TRIPLET[vname],
                            ),
                        }
                    )

    # 2b. Check BOTH live views against frozen run baseline task projection if present.
    if isinstance(run_baseline, dict) and isinstance(run_baseline.get("input_set_snapshot"), dict):
        snap = run_baseline["input_set_snapshot"]
        snap_views = (snap.get("task_projection") or {}).get("views") if isinstance(snap.get("task_projection"), dict) else None
        if isinstance(snap_views, dict):
            for vname in ("back", "gameplay"):
                base_row = snap_views.get(vname)
                live_row = triplet_info.get(f"{vname}_task")
                if isinstance(base_row, dict) and isinstance(live_row, dict):
                    base_acc = [str(x).strip() for x in (base_row.get("acceptance") or []) if str(x).strip()]
                    curr_acc = [str(x).strip() for x in (live_row.get("acceptance") or []) if str(x).strip()]
                    base_refs = set(_extract_refs_from_acceptance(base_acc))
                    curr_refs = set(_extract_refs_from_acceptance(curr_acc))
                    base_trefs = {_norm_rel(str(x)) for x in (base_row.get("test_refs") or []) if str(x).strip()}
                    curr_trefs = {_norm_rel(str(x)) for x in (live_row.get("test_refs") or []) if str(x).strip()}
                    missing_acc = [item for item in base_acc if item not in curr_acc]
                    missing_refs = sorted(base_refs - curr_refs)
                    removed_trefs = sorted(base_trefs - curr_trefs)
                    if len(curr_acc) < len(base_acc) or missing_acc or missing_refs or removed_trefs:
                        violations.append(
                            {
                                "kind": "acceptance_weakened_against_baseline",
                                "owning_stage": "5",
                                "diagnostic": _diag(
                                    codec.ReasonCode.CONFLICT,
                                    stage=codec.Stage.BUNDLE,
                                    entity_id=entity_id,
                                    expected={
                                        "view": vname,
                                        "baseline_acceptance_count": len(base_acc),
                                        "baseline_refs": sorted(base_refs),
                                        "baseline_test_refs": sorted(base_trefs),
                                        "return_stage": "5",
                                    },
                                    actual={
                                        "view": vname,
                                        "live_acceptance_count": len(curr_acc),
                                        "missing_acceptance": missing_acc,
                                        "missing_refs": missing_refs,
                                        "removed_test_refs": removed_trefs,
                                        "return_stage": "5",
                                    },
                                    resume_ref=task_resolver.TRIPLET[vname],
                                ),
                            }
                        )

    # 3. Illegal status flip to "done" while failing / blocked.
    master_status = str((triplet_info.get("master_task") or {}).get("status") or "").strip().lower()
    proposed_status = str(prop_edits.get("status") or "").strip().lower()
    local_verif = di.get("local_verification") if isinstance(di.get("local_verification"), dict) else {}
    local_status = str(local_verif.get("status") or "").strip().lower()
    is_failing_or_blocked = bool(
        latest_run_status in {"fail", "stopped", "blocked", "indeterminate"}
        or local_status in {"failed", "fail", "blocked"}
        or durable_signals.get("has_active_stop_loss")
        or (int(durable_signals.get("consecutive_failures") or 0) > 0 and local_status != "passed")
    )
    if (proposed_status == "done" and is_failing_or_blocked) or (
        di.get("flip_status_to_done") is True and is_failing_or_blocked
    ) or (master_status == "done" and local_status in {"failed", "fail", "blocked"}):
        violations.append(
            {
                "kind": "illegal_status_done_flip",
                "owning_stage": "3C",
                "diagnostic": _diag(
                    codec.ReasonCode.CONFLICT,
                    stage=codec.Stage.CONTENT,
                    entity_id=entity_id,
                    expected={"status_flip_to_done_while_failing": False, "return_stage": "3C"},
                    actual={
                        "master_status": master_status,
                        "proposed_status": proposed_status or ("done" if di.get("flip_status_to_done") else None),
                        "latest_run_status": latest_run_status,
                        "local_status": local_status,
                        "return_stage": "3C",
                    },
                    resume_ref=task_resolver.TRIPLET["master"],
                ),
            }
        )

    # 4. Deleted bound implemented test files, skip/ignore attributes, or gutted empty test files.
    deleted_paths = {_norm_rel(p) for p in list(di.get("deleted_paths") or []) if str(p).strip()}
    for tpath in obligations.get("implemented_test_files") or []:
        tfile = root_path / tpath
        if tpath in deleted_paths or not tfile.is_file():
            violations.append(
                {
                    "kind": "bound_test_deleted",
                    "owning_stage": "5",
                    "diagnostic": _diag(
                        codec.ReasonCode.CONFLICT,
                        stage=codec.Stage.TARGET,
                        entity_id=entity_id,
                        expected={"bound_test_present": True, "path": tpath, "return_stage": "5"},
                        actual={"bound_test_present": False, "deleted": True, "path": tpath, "return_stage": "5"},
                        resume_ref=tpath,
                    ),
                }
            )
            continue
        try:
            text = tfile.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        skip_hits = _scan_text_for_skip(text)
        if skip_hits:
            violations.append(
                {
                    "kind": "bound_test_skipped_or_disabled",
                    "owning_stage": "5",
                    "diagnostic": _diag(
                        codec.ReasonCode.CONFLICT,
                        stage=codec.Stage.CONTENT,
                        entity_id=entity_id,
                        expected={"skipped_tests": [], "path": tpath, "return_stage": "5"},
                        actual={"skip_attributes": skip_hits, "path": tpath, "return_stage": "5"},
                        resume_ref=tpath,
                    ),
                }
            )
        gutted_reason = _detect_gutted_test_file(tpath, text)
        if gutted_reason:
            violations.append(
                {
                    "kind": "bound_test_gutted_or_empty",
                    "owning_stage": "5",
                    "diagnostic": _diag(
                        codec.ReasonCode.CONFLICT,
                        stage=codec.Stage.CONTENT,
                        entity_id=entity_id,
                        expected={"executable_bound_tests_preserved": True, "path": tpath, "return_stage": "5"},
                        actual={"gutted_reason": gutted_reason, "path": tpath, "return_stage": "5"},
                        resume_ref=tpath,
                    ),
                }
            )

    # Also scan proposed_test_edits for skip/ignore attributes or gutted content.
    for tedit in list(di.get("proposed_test_edits") or []):
        if not isinstance(tedit, dict):
            continue
        tpath = _norm_rel(str(tedit.get("path") or ""))
        if tedit.get("deleted") is True:
            violations.append(
                {
                    "kind": "bound_test_deleted",
                    "owning_stage": "5",
                    "diagnostic": _diag(
                        codec.ReasonCode.CONFLICT,
                        stage=codec.Stage.TARGET,
                        entity_id=entity_id,
                        expected={"bound_test_deleted": False, "path": tpath, "return_stage": "5"},
                        actual={"bound_test_deleted": True, "path": tpath, "return_stage": "5"},
                        resume_ref=tpath or None,
                    ),
                }
            )
            continue
        content = str(tedit.get("content") or "")
        skip_hits = _scan_text_for_skip(content)
        if tedit.get("skipped_tests"):
            skip_hits.extend(str(x) for x in tedit["skipped_tests"])
        if skip_hits:
            violations.append(
                {
                    "kind": "bound_test_skipped_or_disabled",
                    "owning_stage": "5",
                    "diagnostic": _diag(
                        codec.ReasonCode.CONFLICT,
                        stage=codec.Stage.CONTENT,
                        entity_id=entity_id,
                        expected={"skipped_tests": [], "path": tpath, "return_stage": "5"},
                        actual={"skip_attributes": skip_hits, "path": tpath, "return_stage": "5"},
                        resume_ref=tpath or None,
                    ),
                }
            )
        if "content" in tedit:
            prev_text: str | None = None
            if tpath and (root_path / tpath).is_file():
                try:
                    prev_text = (root_path / tpath).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    prev_text = None
            gutted_reason = _detect_gutted_test_file(tpath or "test.cs", content, previous_content=prev_text)
            if gutted_reason:
                violations.append(
                    {
                        "kind": "bound_test_gutted_or_empty",
                        "owning_stage": "5",
                        "diagnostic": _diag(
                            codec.ReasonCode.CONFLICT,
                            stage=codec.Stage.CONTENT,
                            entity_id=entity_id,
                            expected={"executable_bound_tests_preserved": True, "path": tpath, "return_stage": "5"},
                            actual={"gutted_reason": gutted_reason, "path": tpath, "return_stage": "5"},
                            resume_ref=tpath or None,
                        ),
                    }
                )

    # 5. Unreviewed weakening of cumulative MVG manifest via _weakens_baseline.
    proposed_manifest = di.get("proposed_manifest")
    if isinstance(proposed_manifest, dict):
        manifest_docs = obligations.get("manifest_docs") or {}
        target_mp = _norm_rel(str(di.get("manifest_path") or ""))
        base_mp = target_mp if target_mp in manifest_docs else (next(iter(manifest_docs.keys()), None))
        if base_mp and isinstance(manifest_docs.get(base_mp), dict):
            base_doc = manifest_docs[base_mp]
            weakening_reasons = _check_manifest_weakening(base_doc, proposed_manifest)
            if weakening_reasons:
                violations.append(
                    {
                        "kind": "mvg_manifest_weakened",
                        "owning_stage": "5",
                        "diagnostic": _diag(
                            codec.ReasonCode.CONFLICT,
                            stage=codec.Stage.CONTENT,
                            entity_id=entity_id,
                            expected={"mvg_baseline_weakened": False, "manifest_path": base_mp, "return_stage": "5"},
                            actual={"weakening_reasons": weakening_reasons, "manifest_path": base_mp, "return_stage": "5"},
                            resume_ref=base_mp,
                        ),
                    }
                )

    proposed_delta = di.get("proposed_manifest_delta")
    if isinstance(proposed_delta, dict):
        manifest_docs = obligations.get("manifest_docs") or {}
        target_mp = _norm_rel(str(di.get("manifest_path") or ""))
        base_mp = target_mp if target_mp in manifest_docs else (next(iter(manifest_docs.keys()), None))
        if base_mp and isinstance(manifest_docs.get(base_mp), dict):
            try:
                mvg_update.apply_delta(manifest_docs[base_mp], proposed_delta, root=root_path, validate_final=False)
            except Exception as exc:
                violations.append(
                    {
                        "kind": "mvg_manifest_weakened",
                        "owning_stage": "5",
                        "diagnostic": _diag(
                            codec.ReasonCode.CONFLICT,
                            stage=codec.Stage.CONTENT,
                            entity_id=entity_id,
                            expected={"valid_non_weakening_mvg_delta": True, "manifest_path": base_mp, "return_stage": "5"},
                            actual={"error": str(exc), "manifest_path": base_mp, "return_stage": "5"},
                            resume_ref=base_mp,
                        ),
                    }
                )

    return violations


def _check_manifest_weakening(base_doc: dict[str, Any], proposed_doc: dict[str, Any]) -> list[str]:
    """Compare a proposed MVG manifest against cumulative baseline using update_mvg_baseline._weakens_baseline."""
    reasons: list[str] = []
    base_cov = base_doc.get("coverage") if isinstance(base_doc.get("coverage"), dict) else {}
    prop_cov = proposed_doc.get("coverage") if isinstance(proposed_doc.get("coverage"), dict) else {}
    if mvg_update._weakens_baseline(base_cov, prop_cov):
        reasons.append("coverage_weakened")

    base_flows = {str(r.get("id")): r for r in (base_doc.get("flows") or []) if isinstance(r, dict) and r.get("id")}
    prop_flows = {str(r.get("id")): r for r in (proposed_doc.get("flows") or []) if isinstance(r, dict) and r.get("id")}
    for fid, frow in sorted(base_flows.items()):
        if fid not in prop_flows:
            reasons.append(f"flow_removed:{fid}")
        elif mvg_update._weakens_baseline(frow, prop_flows[fid]):
            reasons.append(f"flow_weakened:{fid}")

    base_tests = {str(r.get("id")): r for r in (base_doc.get("tests") or []) if isinstance(r, dict) and r.get("id")}
    prop_tests = {str(r.get("id")): r for r in (proposed_doc.get("tests") or []) if isinstance(r, dict) and r.get("id")}
    for tid_key, trow in sorted(base_tests.items()):
        if tid_key not in prop_tests:
            reasons.append(f"test_removed:{tid_key}")
        elif mvg_update._weakens_baseline(trow, prop_tests[tid_key]):
            reasons.append(f"test_weakened:{tid_key}")

    return reasons


def _meaningful_tokens(text: str) -> set[str]:
    raw_tokens = re.findall(r"[a-z0-9]+", str(text or "").lower())
    return {tok for tok in raw_tokens if len(tok) >= 3 and tok not in _REPAIR_STOPWORDS}


def _has_repair_hint(text: str) -> bool:
    raw_tokens = set(re.findall(r"[a-z0-9]+", str(text or "").lower()))
    return bool(raw_tokens & _REPAIR_HINT_WORDS)


def validate_repair_task_delta(
    root: Path | str,
    task_id: Any,
    delta_intents: dict[str, Any],
    *,
    gate_res: dict[str, Any] | None = None,
    obligations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a business-view repair task delta under Story 3.1/3.2 governance without writing tasks.json."""
    root_path = Path(root).resolve()
    tid = ch6_gate.parse_strict_task_id(task_id)
    entity_id = str(tid)
    diagnostics: list[dict[str, Any]] = []

    if not isinstance(delta_intents, dict):
        diag = _diag(
            codec.ReasonCode.INVALID_TYPE,
            stage=codec.Stage.SCHEMA,
            entity_id=entity_id,
            expected="JSON object for repair delta intents",
            actual=type(delta_intents).__name__,
        )
        return {
            "ok": False,
            "task_triplet_written": False,
            "permanent_task_ids_allocated": False,
            "old_done_covers_new_obligations": False,
            "requires_chapter6_reverification": True,
            "synonymous_duplicates_blocked": [],
            "accepted_deltas": [],
            "invalidated_bindings": [],
            "invalidated_readiness_tasks": [],
            "governance_handoff_commands": [],
            "diagnostics": [diag],
            **INVARIANT_FLAGS,
        }

    # Forbid direct triplet writes or permanent ID allocation outside Story 3.2 compile.
    if delta_intents.get("direct_triplet_write") is True or delta_intents.get("allocate_permanent_id") is True:
        diagnostics.append(
            _diag(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected={"direct_triplet_write": False, "allocate_permanent_id": False, "return_stage": "3C"},
                actual={
                    "direct_triplet_write": bool(delta_intents.get("direct_triplet_write")),
                    "allocate_permanent_id": bool(delta_intents.get("allocate_permanent_id")),
                    "return_stage": "3C",
                },
                resume_ref=task_resolver.TRIPLET["master"],
            )
        )

    triplet_info = _load_triplet_for_task(root_path, tid)
    master_tasks = (
        ((triplet_info["master_doc"] or {}).get("master") or {}).get("tasks") or []
        if isinstance(triplet_info.get("master_doc"), dict)
        else []
    )
    master_by_id: dict[int, dict[str, Any]] = {}
    for row in master_tasks:
        if isinstance(row, dict) and row.get("id") is not None:
            try:
                master_by_id[int(row["id"])] = row
            except (TypeError, ValueError):
                continue

    if obligations is None:
        obligations = _collect_bound_obligations(root_path, tid, triplet_info, gate_res)

    known_flows = set(obligations.get("applicable_flow_ids") or [])
    # Collect existing task obligations & titles from live catalog + active bindings + triplet views (even when gate_res is None).
    existing_tasks_index: list[dict[str, Any]] = []
    binding_task_map: dict[int, dict[str, Any]] = {}
    all_binding_paths: list[str] = []

    def _add_binding_path(raw_bp: str) -> None:
        nbp = _norm_rel(raw_bp)
        if nbp and nbp not in all_binding_paths:
            all_binding_paths.append(nbp)

    if isinstance(gate_res, dict):
        for bref in gate_res.get("binding_refs") or []:
            if isinstance(bref, dict) and bref.get("path"):
                _add_binding_path(str(bref["path"]))

    catalog_doc = ch6_recovery._safe_read_json(root_path / records.BASE / "catalog.v1.json")
    if isinstance(catalog_doc, dict):
        for shead in catalog_doc.get("scope_heads") or []:
            if not isinstance(shead, dict):
                continue
            for bref in shead.get("binding_refs") or []:
                if isinstance(bref, dict) and bref.get("path"):
                    _add_binding_path(str(bref["path"]))
    if not all_binding_paths:
        bdir = root_path / records.BASE / "bindings"
        if bdir.is_dir():
            for bf in sorted(bdir.glob("*.json")):
                _add_binding_path(bf.relative_to(root_path).as_posix())

    for bpath in all_binding_paths:
        bdoc = ch6_recovery._safe_read_json(root_path / bpath)
        if not isinstance(bdoc, dict):
            continue
        for frow in bdoc.get("flows") or []:
            if isinstance(frow, dict) and frow.get("flow_id"):
                known_flows.add(str(frow["flow_id"]))
        for ob in bdoc.get("obligations") or []:
            if isinstance(ob, dict):
                for fid in ob.get("flow_ids") or []:
                    if str(fid).strip():
                        known_flows.add(str(fid).strip())
        for trow in list(bdoc.get("task_mappings") or []) + list(bdoc.get("task_bindings") or bdoc.get("tasks") or []):
            if isinstance(trow, dict) and trow.get("task_id") is not None:
                try:
                    btid = int(trow["task_id"])
                except (TypeError, ValueError):
                    continue
                entry = binding_task_map.setdefault(
                    btid,
                    {"flow_ids": set(), "requirement_ids": set(), "part_kinds": set(), "roles": set()},
                )
                for fid in trow.get("flow_ids") or []:
                    if str(fid).strip():
                        entry["flow_ids"].add(str(fid).strip())
                        known_flows.add(str(fid).strip())
                for rid in trow.get("requirement_ids") or []:
                    if str(rid).strip():
                        entry["requirement_ids"].add(str(rid).strip())
                for pk in trow.get("part_kinds") or []:
                    if str(pk).strip():
                        entry["part_kinds"].add(str(pk).strip())
                for rval in trow.get("roles") or []:
                    if str(rval).strip():
                        entry["roles"].add(str(rval).strip())
                if trow.get("role") and str(trow["role"]).strip():
                    entry["roles"].add(str(trow["role"]).strip())

    seen_indexed_tids: set[int] = set()
    for view_key, row in triplet_info.get("all_views") or []:
        tmid = row.get("taskmaster_id")
        try:
            tmid_int = int(tmid)
        except (TypeError, ValueError):
            continue
        seen_indexed_tids.add(tmid_int)
        bmeta = binding_task_map.get(tmid_int, {})
        mstatus = str((master_by_id.get(tmid_int) or {}).get("status") or row.get("status") or "").strip().lower()
        title_text = str(row.get("title") or (master_by_id.get(tmid_int) or {}).get("title") or "")
        acc_text = " ".join(str(x) for x in (row.get("acceptance") or []))
        existing_tasks_index.append(
            {
                "task_id": tmid_int,
                "view": view_key,
                "status": mstatus,
                "title": title_text,
                "tokens": _meaningful_tokens(title_text + " " + acc_text),
                "title_tokens": _meaningful_tokens(title_text),
                "flow_ids": set(bmeta.get("flow_ids") or set()),
                "requirement_ids": set(bmeta.get("requirement_ids") or set()),
                "part_kinds": set(bmeta.get("part_kinds") or set()),
                "roles": set(bmeta.get("roles") or set()),
            }
        )
    for mid_int, mrow in sorted(master_by_id.items()):
        if mid_int in seen_indexed_tids:
            continue
        bmeta = binding_task_map.get(mid_int, {})
        title_text = str(mrow.get("title") or "")
        details_text = str(mrow.get("details") or "")
        existing_tasks_index.append(
            {
                "task_id": mid_int,
                "view": "master",
                "status": str(mrow.get("status") or "").strip().lower(),
                "title": title_text,
                "tokens": _meaningful_tokens(title_text + " " + details_text),
                "title_tokens": _meaningful_tokens(title_text),
                "flow_ids": set(bmeta.get("flow_ids") or set()),
                "requirement_ids": set(bmeta.get("requirement_ids") or set()),
                "part_kinds": set(bmeta.get("part_kinds") or set()),
                "roles": set(bmeta.get("roles") or set()),
            }
        )

    all_existing_reqs: set[str] = set()
    for e_item in existing_tasks_index:
        all_existing_reqs.update(e_item["requirement_ids"])

    raw_deltas = delta_intents.get("deltas")
    if raw_deltas is None:
        raw_deltas = delta_intents.get("operations")
    if raw_deltas is None:
        raw_deltas = delta_intents.get("changes")
    deltas = list(raw_deltas or [])
    if not deltas:
        diagnostics.append(
            _diag(
                codec.ReasonCode.MISSING_REQUIRED_FIELD,
                stage=codec.Stage.CONTENT,
                entity_id=entity_id,
                expected="nonempty deltas/operations/changes list in repair delta intents",
                actual={"deltas": []},
            )
        )

    synonymous_duplicates: list[dict[str, Any]] = []
    accepted_deltas: list[dict[str, Any]] = []
    affected_task_ids: set[int] = {tid}
    affected_flow_ids: set[str] = set()
    requires_reverification = False

    # Validate optional manifest delta in delta_intents.
    if isinstance(delta_intents.get("manifest_delta"), dict):
        manifest_docs = obligations.get("manifest_docs") or {}
        base_mp = next(iter(manifest_docs.keys()), None)
        if base_mp and isinstance(manifest_docs.get(base_mp), dict):
            try:
                mvg_update.apply_delta(
                    manifest_docs[base_mp],
                    delta_intents["manifest_delta"],
                    root=root_path,
                    validate_final=False,
                )
            except Exception as exc:
                diagnostics.append(
                    _diag(
                        codec.ReasonCode.CONFLICT,
                        stage=codec.Stage.CONTENT,
                        entity_id=entity_id,
                        expected={"cumulative_mvg_baseline_preserved": True, "return_stage": "5"},
                        actual={"error": str(exc), "manifest_path": base_mp, "return_stage": "5"},
                        resume_ref=base_mp,
                    )
                )

    for idx, delta in enumerate(deltas):
        if not isinstance(delta, dict):
            diagnostics.append(
                _diag(
                    codec.ReasonCode.INVALID_TYPE,
                    stage=codec.Stage.CONTENT,
                    entity_id=entity_id,
                    expected="object entry in deltas",
                    actual={"index": idx, "type": type(delta).__name__},
                )
            )
            continue
        action = str(delta.get("action") or "").strip().lower()
        if action not in task_preview.ALLOWED_ACTIONS:
            diagnostics.append(
                _diag(
                    codec.ReasonCode.INVALID_ENUM,
                    stage=codec.Stage.CONTENT,
                    entity_id=entity_id,
                    expected=sorted(task_preview.ALLOWED_ACTIONS),
                    actual={"index": idx, "action": action},
                )
            )
            continue

        prop_flows = {str(x).strip() for x in (delta.get("flow_ids") or []) if str(x).strip()}
        prop_reqs = {str(x).strip() for x in (delta.get("requirement_ids") or []) if str(x).strip()}
        new_reqs = {str(x).strip() for x in (delta.get("new_requirement_ids") or []) if str(x).strip()}
        prop_parts = {str(x).strip() for x in (delta.get("part_kinds") or []) if str(x).strip()}
        prop_roles: set[str] = set()
        if isinstance(delta.get("roles"), list):
            prop_roles.update(str(x).strip() for x in delta["roles"] if str(x).strip())
        if str(delta.get("role") or "").strip():
            prop_roles.add(str(delta["role"]).strip())
        prop_role = sorted(prop_roles)[0] if prop_roles else ""
        prop_title = str(delta.get("title") or "").strip()
        prop_resps = [str(x).strip() for x in (delta.get("responsibilities") or []) if str(x).strip()]
        affected_flow_ids.update(prop_flows)

        # Reject unknown Flow IDs if known_flows is non-empty and not explicitly adding a new 3B flow.
        if known_flows and prop_flows and not delta.get("introduces_3b_flow"):
            unknown_flows = sorted(prop_flows - known_flows)
            if unknown_flows:
                diagnostics.append(
                    _diag(
                        codec.ReasonCode.MAPPING_MISMATCH,
                        stage=codec.Stage.REFERENCE,
                        entity_id=entity_id,
                        expected={"known_flow_ids": sorted(known_flows), "return_stage": "3C"},
                        actual={"unknown_flow_ids": unknown_flows, "return_stage": "3C"},
                    )
                )
                continue

        # Block using old done status to cover newly added obligations.
        if delta.get("use_old_done_for_new_obligations") is True or delta.get("skip_reverification") is True:
            requires_reverification = True
            diagnostics.append(
                _diag(
                    codec.ReasonCode.CONFLICT,
                    stage=codec.Stage.CONTENT,
                    entity_id=entity_id,
                    expected={"old_done_covers_new_obligations": False, "requires_chapter6_reverification": True, "return_stage": "3C"},
                    actual={"index": idx, "attempted_old_done_coverage": True, "return_stage": "3C"},
                    resume_ref=task_resolver.TRIPLET["master"],
                )
            )
            continue

        # Reject allocating permanent integer ID inside a create proposal.
        if action == "create" and delta.get("task_id") is not None:
            diagnostics.append(
                _diag(
                    codec.ReasonCode.CONFLICT,
                    stage=codec.Stage.CONTENT,
                    entity_id=entity_id,
                    expected={"permanent_task_ids_allocated": False, "use_candidate_key": True, "return_stage": "3C"},
                    actual={"index": idx, "supplied_permanent_task_id": delta.get("task_id"), "return_stage": "3C"},
                    resume_ref=task_resolver.TRIPLET["master"],
                )
            )
            continue

        if action == "create":
            # Detect synonymous duplicate repair tasks against existing Tasks.
            # Existing requirement IDs stuffed into new_requirement_ids MUST NOT bypass duplicate detection.
            genuinely_new_reqs = new_reqs - all_existing_reqs
            combined_prop_reqs = prop_reqs | new_reqs
            cand_title_tokens = _meaningful_tokens(prop_title)
            cand_all_tokens = _meaningful_tokens(prop_title + " " + " ".join(prop_resps))
            dup_match: dict[str, Any] | None = None
            for existing in existing_tasks_index:
                existing_reqs = existing["requirement_ids"]
                existing_flows = existing["flow_ids"]
                # 1. Exact/subset obligation overlap with zero genuinely new requirements.
                same_flow_overlap = bool(prop_flows and existing_flows and (prop_flows <= existing_flows))
                covered = bool(
                    (combined_prop_reqs and existing_reqs and (combined_prop_reqs <= existing_reqs) and not genuinely_new_reqs)
                    or (not genuinely_new_reqs and not combined_prop_reqs and same_flow_overlap)
                )
                same_part_or_role = bool(
                    (not prop_parts or not existing["part_kinds"] or prop_parts <= existing["part_kinds"])
                    and (not prop_roles or not existing["roles"] or prop_roles <= existing["roles"])
                )
                if covered and same_part_or_role and (same_flow_overlap or (combined_prop_reqs and existing_reqs)):
                    dup_match = {
                        "existing_task_id": existing["task_id"],
                        "reason": "duplicate_flow_requirement_obligation",
                        "title": prop_title,
                    }
                    break
                # 2. Repair-synonym lexical overlap whenever no genuinely new requirement IDs are declared.
                if not genuinely_new_reqs:
                    union = cand_title_tokens | existing["title_tokens"]
                    inter = cand_title_tokens & existing["title_tokens"]
                    jaccard = (len(inter) / len(union)) if union else 0.0
                    containment = (len(inter) / len(cand_title_tokens)) if cand_title_tokens else 0.0
                    all_inter = cand_all_tokens & existing["tokens"]
                    all_contain = (len(all_inter) / len(cand_all_tokens)) if cand_all_tokens else 0.0
                    if (_has_repair_hint(prop_title) and (containment >= 0.5 or all_contain >= 0.6)) or jaccard >= 0.65:
                        dup_match = {
                            "existing_task_id": existing["task_id"],
                            "reason": "synonymous_repair_task_overlap",
                            "title": prop_title,
                            "overlap": round(max(jaccard, containment, all_contain), 3),
                        }
                        break

            if dup_match is not None:
                synonymous_duplicates.append(dup_match)
                diagnostics.append(
                    _diag(
                        codec.ReasonCode.DUPLICATE_OWNER,
                        stage=codec.Stage.CONTENT,
                        entity_id=entity_id,
                        expected={"synonymous_duplicate_repair_task": False, "repair_owning_task_id": dup_match["existing_task_id"], "return_stage": "3C"},
                        actual={**dup_match, "return_stage": "3C"},
                        resume_ref=task_resolver.TRIPLET["back"],
                    )
                )
                continue

            if not (genuinely_new_reqs or prop_resps):
                diagnostics.append(
                    _diag(
                        codec.ReasonCode.SEMANTIC_ERROR,
                        stage=codec.Stage.CONTENT,
                        entity_id=entity_id,
                        expected={"genuine_new_responsibility_for_create": True, "return_stage": "3C"},
                        actual={"index": idx, "title": prop_title, "return_stage": "3C"},
                    )
                )
                continue

            view_name = str(delta.get("view") or "back").strip().lower()
            if view_name not in {"back", "gameplay"}:
                view_name = "back"
            plan_id_seed = str(delta_intents.get("plan_id") or "repair-delta")
            cand_key = task_preview._candidate_key(
                plan_id_seed,
                view_name,
                "create",
                sorted(prop_flows),
                sorted(genuinely_new_reqs or combined_prop_reqs),
                split_index=idx,
            )
            accepted_deltas.append(
                {
                    "action": "create",
                    "view": view_name,
                    "candidate_key": cand_key,
                    "candidate_business_id": task_preview._candidate_business_id(view_name, cand_key),
                    "permanent_task_id": None,
                    "title": prop_title,
                    "flow_ids": sorted(prop_flows),
                    "requirement_ids": sorted(combined_prop_reqs),
                    "part_kinds": sorted(prop_parts),
                    "role": prop_role or "producer",
                    "roles": sorted(prop_roles) or ["producer"],
                    "responsibilities": prop_resps,
                }
            )
            requires_reverification = True
        else:
            # Mutating/reusing existing Task: verify target task exists & preserves ID/done/history & M:N flows.
            target_tid_raw = delta.get("task_id", tid)
            try:
                target_tid = int(target_tid_raw)
            except (TypeError, ValueError):
                diagnostics.append(
                    _diag(
                        codec.ReasonCode.INVALID_TYPE,
                        stage=codec.Stage.CONTENT,
                        entity_id=entity_id,
                        expected="positive integer existing task_id",
                        actual=target_tid_raw,
                    )
                )
                continue
            if target_tid not in master_by_id:
                diagnostics.append(
                    _diag(
                        codec.ReasonCode.UNKNOWN_ENTITY,
                        stage=codec.Stage.REFERENCE,
                        entity_id=str(target_tid),
                        expected="existing mature Task in tasks.json",
                        actual={"task_id": target_tid, "present": False, "return_stage": "3C"},
                        resume_ref=task_resolver.TRIPLET["master"],
                    )
                )
                continue
            if delta.get("rewrite_task_id") is True or delta.get("erase_done_history") is True:
                diagnostics.append(
                    _diag(
                        codec.ReasonCode.CONFLICT,
                        stage=codec.Stage.CONTENT,
                        entity_id=str(target_tid),
                        expected={"preserve_mature_task_id_and_done_history": True, "return_stage": "3C"},
                        actual={"rewrite_task_id": bool(delta.get("rewrite_task_id")), "erase_done_history": bool(delta.get("erase_done_history")), "return_stage": "3C"},
                        resume_ref=task_resolver.TRIPLET["master"],
                    )
                )
                continue
            # Check M:N Flow preservation on existing Task.
            existing_bmeta = binding_task_map.get(target_tid, {})
            existing_flows = set(existing_bmeta.get("flow_ids") or set())
            if existing_flows and prop_flows and not existing_flows.issubset(prop_flows) and not delta.get("reviewed_flow_removal"):
                diagnostics.append(
                    _diag(
                        codec.ReasonCode.MAPPING_MISMATCH,
                        stage=codec.Stage.CONTENT,
                        entity_id=str(target_tid),
                        expected={"preserved_many_to_many_flows": sorted(existing_flows), "return_stage": "3C"},
                        actual={"proposed_flows": sorted(prop_flows), "dropped_flows": sorted(existing_flows - prop_flows), "return_stage": "3C"},
                    )
                )
                continue

            affected_task_ids.add(target_tid)
            existing_status = str((master_by_id[target_tid]).get("status") or "").strip().lower()
            if action in {"update", "split", "merge", "retire"} and (new_reqs or prop_resps or existing_status == "done" or action == "retire"):
                requires_reverification = True
            accepted_deltas.append(
                {
                    "action": action,
                    "task_id": target_tid,
                    "preserved_status": existing_status,
                    "requires_chapter6_reverification": bool(existing_status == "done" and action != "reuse"),
                    "flow_ids": sorted(existing_flows | prop_flows),
                    "requirement_ids": sorted(new_reqs | prop_reqs),
                    "roles": sorted(prop_roles),
                    "responsibilities": prop_resps,
                }
            )

    # Expand invalidated_readiness_tasks to tasks depending on any affected task or sharing changed flows.
    invalidated_tasks: set[int] = set(affected_task_ids) if (accepted_deltas or delta_intents.get("source_or_definition_changed")) else set()
    for mid, mrow in master_by_id.items():
        deps = set()
        for raw_dep in mrow.get("dependencies") or []:
            try:
                deps.add(int(raw_dep))
            except (TypeError, ValueError):
                pass
        if deps & invalidated_tasks:
            invalidated_tasks.add(mid)
        bmeta = binding_task_map.get(mid, {})
        if affected_flow_ids and (set(bmeta.get("flow_ids") or set()) & affected_flow_ids):
            invalidated_tasks.add(mid)

    invalidated_bindings = sorted(set(all_binding_paths)) if invalidated_tasks else []
    plan_id_hint = str(delta_intents.get("plan_id") or "<plan-id>")
    scope_id_hint = str(delta_intents.get("scope_id") or "<scope-id>")
    audit_ref_hint = str(delta_intents.get("audit_ref") or "<audit-ref>")
    handoff_cmds = [
        f"py -3 -B scripts/python/dev_cli.py b-route-task-preview --plan-id {plan_id_hint} --scope-id {scope_id_hint} --audit-ref {audit_ref_hint} --root .",
        "py -3 -B scripts/python/dev_cli.py b-route-task-compile --stage prepare --operation-id <op-id> --request <request.json> --root .",
    ]
    if invalidated_tasks:
        handoff_cmds.append(
            f"py -3 -B scripts/python/dev_cli.py b-route-chapter5-readiness --stage reconcile --task-id {tid} --root ."
        )

    return {
        "ok": len(diagnostics) == 0,
        "task_triplet_written": False,
        "permanent_task_ids_allocated": False,
        "old_done_covers_new_obligations": False,
        "requires_chapter6_reverification": requires_reverification,
        "preserves_mature_ids_and_done_history": len(diagnostics) == 0,
        "synonymous_duplicates_blocked": synonymous_duplicates,
        "accepted_deltas": accepted_deltas,
        "invalidated_bindings": invalidated_bindings,
        "invalidated_readiness_tasks": sorted(invalidated_tasks),
        "governance_handoff_commands": handoff_cmds,
        "diagnostics": diagnostics,
        **INVARIANT_FLAGS,
    }


def _collect_durable_history_and_recurrence(
    root_path: Path,
    tid: int,
    durable_signals: dict[str, Any],
    *,
    run_dir_path: Path | None,
) -> dict[str, Any]:
    """Build durable failure history, recurrence signature, and measured rework/model telemetry."""
    run_dirs = list(durable_signals.get("durable_run_dirs") or [])
    if run_dir_path is not None and run_dir_path.is_dir():
        rel_cur = ch6_recovery._repo_rel(root_path, run_dir_path)
        if rel_cur not in run_dirs:
            run_dirs.append(rel_cur)

    history: list[dict[str, Any]] = []
    signature_counts: dict[str, int] = {}
    latest_sig = ""
    latest_status = "unknown"
    latest_failed_step = ""
    durable_llm_calls = 0
    needs_fix_runs = 0
    latest_review_findings: list[dict[str, Any]] = []
    inferred_changed_paths: list[str] = []

    for rel_dir in run_dirs:
        dpath = root_path / rel_dir
        summary = ch6_recovery._safe_read_json(dpath / "summary.json") or {}
        ctx = ch6_recovery._safe_read_json(dpath / "execution-context.json") or {}
        review = ch6_recovery._safe_read_json(dpath / "agent-review.json") or {}
        status = str(summary.get("status") or ctx.get("status") or "").strip().lower()
        reason = str(summary.get("reason") or "").strip()
        failed_step = str(summary.get("failed_step") or ctx.get("failed_step") or "").strip()
        cmd = str(summary.get("cmd") or ctx.get("cmd") or "").strip()
        if "needs-fix" in rel_dir or "needs-fix" in cmd:
            needs_fix_runs += 1
        for step in summary.get("steps") or []:
            if isinstance(step, dict):
                sname = str(step.get("name") or "").lower()
                if "llm" in sname or sname in {"sc-llm-review", "agent-review", "needs-fix-round"}:
                    durable_llm_calls += 1
                if not failed_step and str(step.get("status") or "").lower() == "fail":
                    failed_step = str(step.get("name") or "").strip()

        # Reset stale changed paths / review findings when a later run cleanly succeeds.
        if status == "ok" and not reason.startswith("rerun_blocked:"):
            inferred_changed_paths = []
            latest_review_findings = []

        if isinstance(ctx.get("changed_paths"), list):
            inferred_changed_paths = [_norm_rel(str(p)) for p in ctx["changed_paths"] if str(p).strip()]
        elif isinstance((ctx.get("git") or {}).get("status_short"), list):
            parsed_paths: list[str] = []
            for line in ctx["git"]["status_short"]:
                if isinstance(line, str) and len(line.strip()) > 2:
                    parts = line.strip().split(None, 1)
                    if len(parts) == 2:
                        raw_tail = parts[1].strip()
                        if " -> " in raw_tail:
                            old_seg, new_seg = raw_tail.split(" -> ", 1)
                            for seg in (old_seg, new_seg):
                                nseg = _norm_rel(seg.strip().strip('"'))
                                if nseg and nseg not in parsed_paths:
                                    parsed_paths.append(nseg)
                        else:
                            nseg = _norm_rel(raw_tail.strip('"'))
                            if nseg and nseg not in parsed_paths:
                                parsed_paths.append(nseg)
            if parsed_paths:
                inferred_changed_paths = parsed_paths

        if isinstance(review.get("findings"), list):
            latest_review_findings = [f for f in review["findings"] if isinstance(f, dict)]

        latest_status = status or latest_status
        latest_failed_step = failed_step or latest_failed_step
        is_fail = status in {"fail", "stopped", "blocked", "indeterminate"} or reason.startswith("rerun_blocked:")
        sig = ""
        if is_fail:
            sig = f"{failed_step or 'unknown'}|{reason or status}"
            signature_counts[sig] = signature_counts.get(sig, 0) + 1
            latest_sig = sig
        history.append(
            {
                "run_dir": rel_dir,
                "run_id": str(summary.get("run_id") or ctx.get("run_id") or ""),
                "status": status or "unknown",
                "reason": reason,
                "failed_step": failed_step,
                "signature": sig,
            }
        )

    max_sig_count = max(signature_counts.values(), default=0)
    recurring_sig = ""
    if latest_sig and signature_counts.get(latest_sig, 0) >= 2:
        recurring_sig = latest_sig
    elif max_sig_count >= 2:
        recurring_sig = max(signature_counts.items(), key=lambda kv: kv[1])[0]

    same_family_streak = int(durable_signals.get("same_family_streak") or 0)
    recurrence_count = max(same_family_streak, signature_counts.get(recurring_sig, 0) if recurring_sig else 0)
    recurrence_detected = bool(
        recurrence_count >= 2
        or "repeat_deterministic_failure" in list(durable_signals.get("active_stop_loss_signals") or [])
    )
    rework_count = (
        int(durable_signals.get("failed_runs") or 0)
        + int(durable_signals.get("total_resume_count") or 0)
        + needs_fix_runs
    )

    return {
        "history": history,
        "latest_status": latest_status,
        "latest_failed_step": latest_failed_step,
        "latest_review_findings": latest_review_findings,
        "inferred_changed_paths": inferred_changed_paths,
        "recurrence_detected": recurrence_detected,
        "recurrence_count": recurrence_count,
        "recurring_failure_signature": recurring_sig,
        "durable_model_invocation_count": durable_llm_calls,
        "rework_count": rework_count,
    }


def _evaluate_needs_fix_findings(
    findings: list[dict[str, Any]],
    *,
    fix_through: str,
) -> dict[str, Any]:
    """Enforce Needs Fix and P1 floor on review findings."""
    threshold = SEVERITY_RANK.get(fix_through, 1)
    blocking: list[dict[str, Any]] = []
    deferrable: list[dict[str, Any]] = []
    for item in findings:
        if not isinstance(item, dict):
            continue
        status = str(item.get("status") or "open").strip().lower()
        if status in {"fixed", "resolved", "closed"}:
            continue
        raw_sev = str(item.get("severity") or "").strip().upper()
        sev_map = {"CRITICAL": "P0", "HIGH": "P1", "MEDIUM": "P2", "LOW": "P3", "INFO": "P4"}
        norm_sev = sev_map.get(raw_sev, raw_sev if raw_sev in SEVERITY_RANK else "P1")
        rank = SEVERITY_RANK.get(norm_sev, 1)
        entry = {
            "finding_id": str(item.get("finding_id") or item.get("id") or "finding"),
            "severity": norm_sev,
            "message": str(item.get("message") or ""),
            "status": status or "open",
        }
        if rank <= threshold:
            blocking.append(entry)
        else:
            deferrable.append(entry)
    return {
        "fix_through": fix_through,
        "p1_floor_enforced": True,
        "has_blocking_findings": bool(blocking),
        "must_fix_blocking_findings": blocking,
        "deferrable_findings": deferrable,
    }


def _build_handoff(
    *,
    task_id: int | None,
    owning_stage: str,
    resume_ref: str | None,
    affected_paths: list[str],
    gap_categories: list[str],
    disguise_violations: list[str],
    invalidated_bindings: list[str],
    invalidated_readiness_tasks: list[int],
    gate_res: dict[str, Any] | None,
) -> dict[str, Any]:
    cmd = _OWNING_STAGE_COMMANDS.get(owning_stage, _OWNING_STAGE_COMMANDS["5"])
    if task_id is not None and owning_stage == "5":
        cmd = f"py -3 -B scripts/python/dev_cli.py b-route-chapter5-readiness --stage reconcile --task-id {task_id} --root ."
    elif owning_stage == "3C" and isinstance(gate_res, dict):
        plans = gate_res.get("plan_refs") or []
        scopes = gate_res.get("scope_ids") or []
        if plans and isinstance(plans[0], dict) and plans[0].get("entity_id"):
            cmd = cmd.replace("<plan-id>", str(plans[0]["entity_id"]))
        if scopes:
            cmd = cmd.replace("<scope-id>", str(scopes[0]))
    return {
        "schema_version": DEFECT_REPORT_SCHEMA,
        "owning_stage": owning_stage,
        "return_stage": owning_stage,
        "resume_ref": resume_ref,
        "entrypoint_command": cmd,
        "affected_paths": sorted(set(affected_paths)),
        "gap_categories": sorted(set(gap_categories)),
        "disguise_violations": sorted(set(disguise_violations)),
        "invalidated_bindings": sorted(set(invalidated_bindings)),
        "invalidated_readiness_tasks": sorted(set(invalidated_readiness_tasks)),
        "auto_reruns_upstream": False,
        **INVARIANT_FLAGS,
    }


def evaluate_defect_routing(
    root: Path | str,
    task_id: Any,
    *,
    run_dir: Path | str | None = None,
    defect_input: dict[str, Any] | str | Path | None = None,
    delta_intents: dict[str, Any] | str | Path | None = None,
    fix_through: str = "P1",
    changed_paths: list[str] | None = None,
    recovery_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Read-only zero-write defect classifier, anti-disguise guard, delta validator, and handoff reporter."""
    started = time.monotonic()

    def _finish(payload: dict[str, Any]) -> dict[str, Any]:
        elapsed = round(max(0.0, time.monotonic() - started), 6)
        metrics = dict(payload.get("metrics") or {})
        metrics["active_elapsed_seconds"] = elapsed
        metrics.setdefault("model_invocation_count", 0)
        metrics.setdefault("durable_model_invocation_count", 0)
        metrics.setdefault("reused_upstream_artifacts", 0)
        metrics.setdefault("rework_count", 0)
        payload["metrics"] = metrics
        payload["runtime_verified"] = False
        payload["default_b_enabled"] = False
        payload["flow_completed"] = False
        payload["cumulative_milestone_completed"] = False
        payload["global_knowledge_refresh"] = "forbidden"
        return payload

    validated_tid: int | None = None
    try:
        root_path = task_resolver._validate_root(Path(root))
        validated_tid = ch6_gate.parse_strict_task_id(task_id)
    except codec.CodecError as err:
        diag = err.diagnostic.to_dict()
        if diag.get("entity_id") is None and validated_tid is not None:
            diag["entity_id"] = str(validated_tid)
        return _finish(
            {
                "schema_version": SCHEMA,
                "ok": False,
                "task_id": validated_tid,
                "route": "blocked",
                "legacy_a_passthrough": False,
                "defect_class": "invalid_arguments",
                "action": "blocked",
                "local_repair_allowed": False,
                "reruns_3a_3b": False,
                "owning_stage": "3C",
                "return_stage": "3C",
                "reason_code": diag["reason_code"],
                "reason": f"invalid_arguments:{diag['reason_code']}",
                "diagnostics": [diag],
                "governed_handoff": None,
                "delta_governance": None,
                "upstream_reuse": {"upstream_reused": False, "reused_artifacts": []},
                "recurrence_analysis": {},
                "verification_breakdown": {},
                "needs_fix_policy": {},
                "report_path": None,
            }
        )

    entity_id = str(validated_tid)
    norm_fix_through, ft_diag = _validate_fix_through(fix_through, entity_id)
    if ft_diag is not None:
        return _finish(
            {
                "schema_version": SCHEMA,
                "ok": False,
                "task_id": validated_tid,
                "route": "blocked",
                "legacy_a_passthrough": False,
                "defect_class": "policy_violation",
                "action": "blocked",
                "local_repair_allowed": False,
                "reruns_3a_3b": False,
                "owning_stage": "5",
                "return_stage": "5",
                "reason_code": ft_diag["reason_code"],
                "reason": "fix_through_below_p1_floor",
                "diagnostics": [ft_diag],
                "governed_handoff": None,
                "delta_governance": None,
                "upstream_reuse": {"upstream_reused": False, "reused_artifacts": []},
                "recurrence_analysis": {},
                "verification_breakdown": {},
                "needs_fix_policy": {"fix_through": norm_fix_through, "p1_floor_enforced": True},
                "report_path": None,
            }
        )

    defect_doc, defect_rel, defect_err = _safe_load_json_arg(
        root_path, defect_input, label="defect-input", entity_id=entity_id
    )
    if defect_err is not None:
        return _finish(
            {
                "schema_version": SCHEMA,
                "ok": False,
                "task_id": validated_tid,
                "route": "blocked",
                "legacy_a_passthrough": False,
                "defect_class": "invalid_arguments",
                "action": "blocked",
                "local_repair_allowed": False,
                "reruns_3a_3b": False,
                "owning_stage": "5",
                "return_stage": "5",
                "reason_code": defect_err["reason_code"],
                "reason": f"invalid_defect_input:{defect_err['reason_code']}",
                "diagnostics": [defect_err],
                "governed_handoff": None,
                "delta_governance": None,
                "upstream_reuse": {"upstream_reused": False, "reused_artifacts": []},
                "recurrence_analysis": {},
                "verification_breakdown": {},
                "needs_fix_policy": {"fix_through": norm_fix_through, "p1_floor_enforced": True},
                "report_path": None,
            }
        )

    delta_doc, delta_rel, delta_err = _safe_load_json_arg(
        root_path, delta_intents, label="delta-intents", entity_id=entity_id
    )
    if delta_err is not None:
        return _finish(
            {
                "schema_version": SCHEMA,
                "ok": False,
                "task_id": validated_tid,
                "route": "blocked",
                "legacy_a_passthrough": False,
                "defect_class": "invalid_arguments",
                "action": "blocked",
                "local_repair_allowed": False,
                "reruns_3a_3b": False,
                "owning_stage": "3C",
                "return_stage": "3C",
                "reason_code": delta_err["reason_code"],
                "reason": f"invalid_delta_intents:{delta_err['reason_code']}",
                "diagnostics": [delta_err],
                "governed_handoff": None,
                "delta_governance": None,
                "upstream_reuse": {"upstream_reused": False, "reused_artifacts": []},
                "recurrence_analysis": {},
                "verification_breakdown": {},
                "needs_fix_policy": {"fix_through": norm_fix_through, "p1_floor_enforced": True},
                "report_path": None,
            }
        )

    run_dir_path: Path | None = None
    if run_dir is not None and str(run_dir).strip():
        rd_target, _rd_rel, rd_err = _resolve_contained_path(
            root_path, run_dir, label="run-dir", entity_id=entity_id
        )
        if rd_err is not None:
            return _finish(
                {
                    "schema_version": SCHEMA,
                    "ok": False,
                    "task_id": validated_tid,
                    "route": "blocked",
                    "legacy_a_passthrough": False,
                    "defect_class": "invalid_arguments",
                    "action": "blocked",
                    "local_repair_allowed": False,
                    "reruns_3a_3b": False,
                    "owning_stage": "5",
                    "return_stage": "5",
                    "reason_code": rd_err["reason_code"],
                    "reason": f"invalid_run_dir:{rd_err['reason_code']}",
                    "diagnostics": [rd_err],
                    "governed_handoff": None,
                    "delta_governance": None,
                    "upstream_reuse": {"upstream_reused": False, "reused_artifacts": []},
                    "recurrence_analysis": {},
                    "verification_breakdown": {},
                    "needs_fix_policy": {"fix_through": norm_fix_through, "p1_floor_enforced": True},
                    "report_path": None,
                }
            )
        run_dir_path = rd_target

    # 1. Live Story 3.9/3.8 recovery & gate evaluation (zero writes).
    rec_res = (
        deepcopy(recovery_result)
        if isinstance(recovery_result, dict)
        else ch6_recovery.evaluate_chapter6_recovery(
            root_path,
            validated_tid,
            run_dir=run_dir_path,
            operation="defect_routing",
            recommendation_only=True,
            consumer="b_route_defect_routing",
            lock_mode="none",
        )
    )
    gate_res = rec_res.get("gate_result") if isinstance(rec_res.get("gate_result"), dict) else None
    durable_signals = rec_res.get("durable_signals") if isinstance(rec_res.get("durable_signals"), dict) else ch6_recovery.scan_durable_recovery_signals(root_path, validated_tid)
    run_baseline = ch6_recovery.load_run_recovery_baseline(root_path, run_dir_path)
    durable_info = _collect_durable_history_and_recurrence(
        root_path,
        validated_tid,
        durable_signals,
        run_dir_path=run_dir_path,
    )

    triplet_info = _load_triplet_for_task(root_path, validated_tid)
    obligations = _collect_bound_obligations(root_path, validated_tid, triplet_info, gate_res)
    di = defect_doc or {}

    # Combine review findings from latest agent-review.json + defect_input.
    combined_findings = list(durable_info["latest_review_findings"])
    if isinstance(di.get("review_findings"), list):
        combined_findings.extend(f for f in di["review_findings"] if isinstance(f, dict))
    needs_fix_eval = _evaluate_needs_fix_findings(combined_findings, fix_through=norm_fix_through)

    # Assemble candidate changed paths from args, defect_input, and run execution-context.
    cand_paths: list[str] = []
    for raw_list in (changed_paths or [], di.get("changed_paths") or [], durable_info["inferred_changed_paths"]):
        for p in raw_list:
            np = _norm_rel(str(p))
            if np and np not in cand_paths:
                cand_paths.append(np)

    # Upstream artifacts eligible for reuse when gate/recovery is healthy.
    reused_artifacts: list[str] = []
    if isinstance(gate_res, dict) and gate_res.get("ok"):
        for ref_key in ("plan_refs", "binding_refs"):
            for ref in gate_res.get(ref_key) or []:
                if isinstance(ref, dict) and ref.get("path"):
                    reused_artifacts.append(str(ref["path"]))
        for pkey in ("readiness_path", "reconciliation_path"):
            if gate_res.get(pkey):
                reused_artifacts.append(str(gate_res[pkey]))
    reused_artifacts = sorted(set(reused_artifacts))
    upstream_valid = bool(rec_res.get("ok") and not rec_res.get("legacy_a_passthrough"))

    # Build verification breakdown (AC-5: local PASS vs runtime vs manual vs incomplete).
    local_in = di.get("local_verification") if isinstance(di.get("local_verification"), dict) else {}
    raw_local_status = str(local_in.get("status") or "").strip().lower()
    if raw_local_status in {"pass", "passed", "ok"}:
        local_status = "passed"
    elif raw_local_status in {"fail", "failed"}:
        local_status = "failed"
    elif raw_local_status == "blocked":
        local_status = "blocked"
    elif durable_info["latest_status"] == "ok":
        local_status = "passed"
    elif durable_info["latest_status"] in {"fail", "stopped", "indeterminate"}:
        local_status = "failed"
    else:
        local_status = "pending"

    required_self_checks = [
        f"py -3 -B scripts/python/dev_cli.py run-acceptance-preflight --task-id {validated_tid}",
        "py -3 -B scripts/python/dev_cli.py run-local-hard-checks-preflight",
    ]
    required_regressions = sorted(
        set(obligations["implemented_test_files"])
        | set(obligations["planned_test_files"])
        | set(obligations["other_verification_refs"])
    )
    manual_items = list(obligations["manual_obligations"])
    if isinstance(di.get("manual_obligations"), list):
        for m in di["manual_obligations"]:
            if isinstance(m, str) and m.strip() and m.strip() not in manual_items:
                manual_items.append(m.strip())

    incomplete_obligations: list[dict[str, Any]] = []
    executed_tests = {_norm_rel(str(x)) for x in list(local_in.get("executed_tests") or []) if str(x).strip()}
    for ptest in obligations["planned_test_files"]:
        incomplete_obligations.append({"kind": "planned_test", "ref": ptest, "status": "pending"})
    for itest in obligations["implemented_test_files"]:
        if local_status != "passed" or (executed_tests and itest not in executed_tests):
            incomplete_obligations.append(
                {
                    "kind": "applicable_regression",
                    "ref": itest,
                    "status": "blocked" if local_status in {"failed", "blocked"} else "pending",
                }
            )
    if obligations["applicable_flow_ids"]:
        incomplete_obligations.append(
            {
                "kind": "runtime_mvg_verification",
                "flows": list(obligations["applicable_flow_ids"]),
                "status": "pending" if rec_res.get("ok") else "blocked",
            }
        )
    for mitem in manual_items:
        incomplete_obligations.append({"kind": "manual_obligation", "description": mitem, "status": "pending"})
    for bf in needs_fix_eval.get("must_fix_blocking_findings") or []:
        incomplete_obligations.append(
            {
                "kind": "needs_fix_blocking_finding",
                "finding_id": bf["finding_id"],
                "severity": bf["severity"],
                "status": "blocked",
            }
        )

    verification_breakdown = {
        "local_verification": {
            "status": local_status,
            "required_local_self_checks": required_self_checks,
            "required_applicable_regressions": required_regressions,
            "executed_tests": sorted(executed_tests),
            "never_skips_readiness": True,
            "never_skips_applicable_regressions": True,
        },
        "runtime_verification": {
            "status": "pending" if rec_res.get("ok") else "blocked",
            "runtime_verified": False,
            "required_mvg_flows": list(obligations["applicable_flow_ids"]),
            "pending_reason": "local_repair_does_not_establish_runtime_engine_verification",
        },
        "manual_obligations": {
            "status": "pending" if manual_items else "not_applicable",
            "items": manual_items,
        },
        "incomplete_obligations": incomplete_obligations,
    }

    recurrence_analysis = {
        "recurrence_detected": durable_info["recurrence_detected"],
        "recurrence_count": durable_info["recurrence_count"],
        "recurring_failure_signature": durable_info["recurring_failure_signature"],
        "durable_failed_runs": int(durable_signals.get("failed_runs") or 0),
        "consecutive_failures": int(durable_signals.get("consecutive_failures") or 0),
        "cumulative_step_retries": int(durable_signals.get("total_step_retries") or 0),
        "cumulative_resume_count": int(durable_signals.get("total_resume_count") or 0),
        "active_stop_loss_signals": list(durable_signals.get("active_stop_loss_signals") or []),
        "rerun_guard_active": bool("rerun_guard" in list(durable_signals.get("active_stop_loss_signals") or [])),
        "source_changed_since_last_stop": bool(durable_signals.get("source_changed_since_last_stop")),
        "budget_preserved": True,
        "candidate_generation_masking_blocked": True,
        "global_knowledge_refresh": "forbidden",
        "failure_history": durable_info["history"],
    }

    metrics_base = {
        "model_invocation_count": 0,
        "durable_model_invocation_count": durable_info["durable_model_invocation_count"],
        "reused_upstream_artifacts": len(reused_artifacts),
        "rework_count": durable_info["rework_count"],
    }

    # 2. Check explicit policy / anti-masking / anti-impersonation violations from defect_input.
    policy_diags: list[dict[str, Any]] = []
    policy_reasons: list[str] = []
    policy_stage = "5"
    for flag, rsn, stg in (
        ("skip_readiness", "cannot_skip_chapter5_readiness", "5"),
        ("skip_regressions", "cannot_skip_applicable_regressions", "5"),
        ("force_rerun_3a_3b", "blind_3a_3b_rerun_forbidden_for_pure_impl", "3B"),
        ("request_candidate_regeneration", "candidate_generation_masking_blocked", "3B"),
        ("request_global_knowledge_refresh", "global_knowledge_refresh_masking_blocked", "5"),
        ("claim_flow_completed", "local_repair_cannot_claim_flow_completed", "5"),
        ("claim_cumulative_milestone_completed", "local_repair_cannot_claim_milestone_completed", "5"),
        ("claim_runtime_verified", "local_repair_cannot_claim_runtime_verified", "5"),
    ):
        if di.get(flag) is True:
            policy_reasons.append(rsn)
            policy_stage = _earliest_stage([policy_stage, stg], default="5") or "5"
            policy_diags.append(
                _diag(
                    codec.ReasonCode.CONFLICT,
                    stage=codec.Stage.CONTENT,
                    entity_id=entity_id,
                    expected={flag: False, "return_stage": stg},
                    actual={flag: True, "reason": rsn, "return_stage": stg},
                    resume_ref=defect_rel,
                )
            )
    if policy_diags:
        return _finish(
            {
                "schema_version": SCHEMA,
                "ok": False,
                "task_id": validated_tid,
                "route": str(rec_res.get("route") or "B"),
                "legacy_a_passthrough": bool(rec_res.get("legacy_a_passthrough")),
                "defect_class": "policy_violation",
                "action": "blocked",
                "local_repair_allowed": False,
                "reruns_3a_3b": False,
                "owning_stage": policy_stage,
                "return_stage": policy_stage,
                "reason_code": codec.ReasonCode.CONFLICT.value,
                "reason": policy_reasons[0],
                "classification_rationale": "Policy or anti-masking invariant violated: " + ", ".join(policy_reasons),
                "diagnostics": policy_diags,
                "governed_handoff": _build_handoff(
                    task_id=validated_tid,
                    owning_stage=policy_stage,
                    resume_ref=defect_rel,
                    affected_paths=cand_paths,
                    gap_categories=policy_reasons,
                    disguise_violations=[],
                    invalidated_bindings=[],
                    invalidated_readiness_tasks=[],
                    gate_res=gate_res,
                ),
                "delta_governance": None,
                "upstream_reuse": {
                    "upstream_reused": upstream_valid,
                    "reused_artifacts": reused_artifacts,
                },
                "recurrence_analysis": {**recurrence_analysis, "return_stage": policy_stage},
                "verification_breakdown": verification_breakdown,
                "needs_fix_policy": needs_fix_eval,
                "metrics": metrics_base,
                "report_path": None,
            }
        )

    # 3. Anti-disguise hard checks (AC-2): runs even if caller claims pure implementation.
    disguise_violations = _detect_disguise_violations(
        root_path,
        validated_tid,
        triplet_info=triplet_info,
        obligations=obligations,
        defect_input=defect_doc,
        run_baseline=run_baseline,
        durable_signals=durable_signals,
        latest_run_status=durable_info["latest_status"],
    )
    if disguise_violations:
        d_stages = [v["owning_stage"] for v in disguise_violations]
        earliest = _earliest_stage(d_stages, default="5") or "5"
        d_diags = [v["diagnostic"] for v in disguise_violations]
        d_kinds = [v["kind"] for v in disguise_violations]
        first_ref = next((d.get("resume_ref") for d in d_diags if d.get("resume_ref")), None)
        return _finish(
            {
                "schema_version": SCHEMA,
                "ok": False,
                "task_id": validated_tid,
                "route": str(rec_res.get("route") or "B"),
                "legacy_a_passthrough": bool(rec_res.get("legacy_a_passthrough")),
                "defect_class": "disguised_definition_change",
                "action": "return_to_owning_stage",
                "local_repair_allowed": False,
                "reruns_3a_3b": False,
                "owning_stage": earliest,
                "return_stage": earliest,
                "resume_ref": first_ref,
                "reason_code": str(d_diags[0]["reason_code"]),
                "reason": f"disguised_definition_change:{d_kinds[0]}",
                "classification_rationale": "Rejected disguised local repair attempt: " + ", ".join(sorted(set(d_kinds))),
                "diagnostics": d_diags,
                "governed_handoff": _build_handoff(
                    task_id=validated_tid,
                    owning_stage=earliest,
                    resume_ref=first_ref,
                    affected_paths=cand_paths,
                    gap_categories=d_kinds,
                    disguise_violations=d_kinds,
                    invalidated_bindings=[str(r.get("path")) for r in (gate_res or {}).get("binding_refs", []) if isinstance(r, dict) and r.get("path")],
                    invalidated_readiness_tasks=[validated_tid],
                    gate_res=gate_res,
                ),
                "delta_governance": None,
                "upstream_reuse": {
                    "upstream_reused": False,
                    "reused_artifacts": [],
                },
                "recurrence_analysis": {**recurrence_analysis, "return_stage": earliest},
                "verification_breakdown": verification_breakdown,
                "needs_fix_policy": needs_fix_eval,
                "metrics": metrics_base,
                "report_path": None,
            }
        )

    # 4. Clean explicit_not_enabled_a passthrough (zero writes, no B lock/artifact assumptions).
    if rec_res.get("legacy_a_passthrough"):
        delta_gov = (
            validate_repair_task_delta(root_path, validated_tid, delta_doc, gate_res=gate_res, obligations=obligations)
            if delta_doc is not None
            else None
        )
        ok_a = True if delta_gov is None else bool(delta_gov["ok"])
        return _finish(
            {
                "schema_version": SCHEMA,
                "ok": ok_a,
                "task_id": validated_tid,
                "route": "explicit_not_enabled_a",
                "legacy_a_passthrough": True,
                "defect_class": "pure_implementation" if ok_a else "delta_governance_rejected",
                "action": "local_repair" if ok_a else "return_to_owning_stage",
                "local_repair_allowed": ok_a,
                "reruns_3a_3b": False,
                "owning_stage": None if ok_a else "3C",
                "return_stage": None if ok_a else "3C",
                "reason_code": codec.ReasonCode.OK.value if ok_a else str((delta_gov or {}).get("diagnostics", [{}])[0].get("reason_code", codec.ReasonCode.CONFLICT.value)),
                "reason": "explicit_not_enabled_a" if ok_a else "delta_governance_rejected",
                "classification_rationale": "Explicit A-only repository without B traces; local repair routing preserves A compatibility.",
                "diagnostics": [] if ok_a else list((delta_gov or {}).get("diagnostics") or []),
                "governed_handoff": None,
                "delta_governance": delta_gov,
                "upstream_reuse": {"upstream_reused": False, "reused_artifacts": []},
                "recurrence_analysis": {**recurrence_analysis, "return_stage": None if ok_a else "3C"},
                "verification_breakdown": verification_breakdown,
                "needs_fix_policy": needs_fix_eval,
                "metrics": metrics_base,
                "report_path": None,
            }
        )

    # 5. Live gate/recovery block -> return to exact upstream owning stage (3A..5) with zero auto-rerun.
    if not rec_res.get("ok"):
        rstage = str(rec_res.get("return_stage") or "5")
        if rstage not in STAGE_RANK:
            rstage = "5"
        diags = list(rec_res.get("diagnostics") or [])
        if not diags:
            diags = [
                _diag(
                    codec.ReasonCode.CONFLICT,
                    stage=codec.Stage.BUNDLE,
                    entity_id=entity_id,
                    expected="valid Chapter 5 readiness, Stage-5 obligations, and Chapter 6 gate",
                    actual={"reason": rec_res.get("reason"), "return_stage": rstage},
                    resume_ref=rec_res.get("resume_ref"),
                )
            ]
        return _finish(
            {
                "schema_version": SCHEMA,
                "ok": False,
                "task_id": validated_tid,
                "route": str(rec_res.get("route") or "blocked"),
                "legacy_a_passthrough": False,
                "defect_class": "upstream_or_definition_blocked",
                "action": "return_to_owning_stage",
                "local_repair_allowed": False,
                "reruns_3a_3b": False,
                "owning_stage": rstage,
                "return_stage": rstage,
                "reason_code": str(rec_res.get("reason_code") or diags[0]["reason_code"]),
                "reason": str(rec_res.get("reason") or "chapter6_recovery_blocked"),
                "classification_rationale": f"Live Story 3.8/3.9 gate or readiness is not valid; return to owning stage {rstage} without auto-rerunning 3A/3B.",
                "diagnostics": diags,
                "governed_handoff": _build_handoff(
                    task_id=validated_tid,
                    owning_stage=rstage,
                    resume_ref=rec_res.get("resume_ref"),
                    affected_paths=cand_paths,
                    gap_categories=[str(rec_res.get("reason") or "upstream_blocked")],
                    disguise_violations=[],
                    invalidated_bindings=[str(r.get("path")) for r in (gate_res or {}).get("binding_refs", []) if isinstance(r, dict) and r.get("path")],
                    invalidated_readiness_tasks=[validated_tid],
                    gate_res=gate_res,
                ),
                "delta_governance": None,
                "upstream_reuse": {
                    "upstream_reused": False,
                    "reused_artifacts": [],
                },
                "recurrence_analysis": {**recurrence_analysis, "return_stage": rstage},
                "verification_breakdown": verification_breakdown,
                "needs_fix_policy": needs_fix_eval,
                "metrics": metrics_base,
                "report_path": None,
            }
        )

    # 6. Validate optional business-view repair task delta (AC-3).
    delta_gov: dict[str, Any] | None = None
    if delta_doc is not None:
        delta_gov = validate_repair_task_delta(
            root_path,
            validated_tid,
            delta_doc,
            gate_res=gate_res,
            obligations=obligations,
        )

    # 7. Classify changed paths & declared gap categories (AC-1 vs AC-2).
    def_paths: list[str] = []
    def_stages: list[str] = []
    impl_paths: list[str] = []
    for p in cand_paths:
        cls, stg = _classify_path(p, root_path=root_path)
        if cls == "definition":
            def_paths.append(p)
            def_stages.append(stg)
        else:
            impl_paths.append(p)

    gap_categories: list[str] = []
    for raw_cat in list(di.get("gap_categories") or []) + list(di.get("change_kinds") or []):
        cat = str(raw_cat or "").strip().lower()
        if not cat or cat == "pure_implementation":
            continue
        gap_categories.append(cat)
        mapped_stage = _GAP_CATEGORY_STAGE.get(cat, "4")
        def_stages.append(mapped_stage)

    if delta_doc is not None:
        def_stages.append("3C")
        gap_categories.append("task_delta_required")

    # 8. If definition/contract/ownership/handoff/binding/obligation change or task delta exists -> return to owning stage (3A..5).
    if def_stages:
        owning_stage = _earliest_stage(def_stages, default="4") or "4"
        diags: list[dict[str, Any]] = []
        if delta_gov is not None and not delta_gov["ok"]:
            diags.extend(delta_gov["diagnostics"])
        first_ref = (def_paths[0] if def_paths else None) or delta_rel or defect_rel
        diags.append(
            _diag(
                codec.ReasonCode.CONFLICT,
                stage=codec.Stage.BUNDLE,
                entity_id=entity_id,
                expected={"pure_implementation_only": True, "owning_stage": owning_stage, "return_stage": owning_stage},
                actual={
                    "definition_paths": def_paths,
                    "gap_categories": sorted(set(gap_categories)),
                    "owning_stage": owning_stage,
                    "return_stage": owning_stage,
                },
                resume_ref=first_ref,
            )
        )
        inv_bindings = (
            list(delta_gov.get("invalidated_bindings") or [])
            if isinstance(delta_gov, dict)
            else [str(r.get("path")) for r in (gate_res or {}).get("binding_refs", []) if isinstance(r, dict) and r.get("path")]
        )
        inv_tasks = (
            list(delta_gov.get("invalidated_readiness_tasks") or [])
            if isinstance(delta_gov, dict)
            else [validated_tid]
        )
        delta_failed = bool(delta_gov is not None and not delta_gov["ok"])
        return _finish(
            {
                "schema_version": SCHEMA,
                "ok": False,
                "task_id": validated_tid,
                "route": str(rec_res.get("route") or "B"),
                "legacy_a_passthrough": False,
                "defect_class": "delta_governance_rejected" if delta_failed else "definition_or_contract_change",
                "action": "return_to_owning_stage",
                "local_repair_allowed": False,
                "reruns_3a_3b": False,
                "owning_stage": owning_stage,
                "return_stage": owning_stage,
                "reason_code": str(diags[0]["reason_code"]),
                "reason": (
                    "repair_delta_governance_rejected"
                    if delta_failed
                    else f"definition_or_contract_change:return_stage={owning_stage}"
                ),
                "classification_rationale": (
                    f"Defect touches governed definitions/contracts/bindings/obligations owned by stage {owning_stage}; "
                    "local Chapter 6 repair is forbidden and routed via governed handoff."
                ),
                "diagnostics": diags,
                "governed_handoff": _build_handoff(
                    task_id=validated_tid,
                    owning_stage=owning_stage,
                    resume_ref=first_ref,
                    affected_paths=def_paths or cand_paths,
                    gap_categories=gap_categories,
                    disguise_violations=[],
                    invalidated_bindings=inv_bindings,
                    invalidated_readiness_tasks=inv_tasks,
                    gate_res=gate_res,
                ),
                "delta_governance": delta_gov,
                "upstream_reuse": {
                    "upstream_reused": False,
                    "reused_artifacts": [],
                },
                "recurrence_analysis": {**recurrence_analysis, "return_stage": owning_stage},
                "verification_breakdown": verification_breakdown,
                "needs_fix_policy": needs_fix_eval,
                "metrics": metrics_base,
                "report_path": None,
            }
        )

    # 9. Pure implementation defect admitted under valid 3B adoption + Stage-5 obligations + Chapter 5 readiness (AC-1).
    plan_refs = deepcopy((gate_res or {}).get("plan_refs") or rec_res.get("plan_refs") or [])
    binding_refs = deepcopy((gate_res or {}).get("binding_refs") or rec_res.get("binding_refs") or [])
    rationale = (
        "Pure implementation defect: gameplay definitions, production contracts, state ownership, "
        "handoff/binding design, Task definition projection, and verification obligations are unchanged; "
        "reusing committed 3B adoption, Stage-5 bindings, and valid Chapter 5 readiness without rerunning 3A/3B."
    )
    return _finish(
        {
            "schema_version": SCHEMA,
            "ok": True,
            "task_id": validated_tid,
            "route": str(rec_res.get("route") or "B"),
            "legacy_a_passthrough": False,
            "defect_class": "pure_implementation",
            "action": "local_repair",
            "local_repair_allowed": True,
            "reruns_3a_3b": False,
            "owning_stage": None,
            "return_stage": "6" if durable_info["recurrence_detected"] else None,
            "reason_code": codec.ReasonCode.OK.value,
            "reason": (
                "pure_implementation_recurring_local_repair"
                if durable_info["recurrence_detected"]
                else "pure_implementation_local_repair_admitted"
            ),
            "classification_rationale": rationale,
            "implemented_paths": impl_paths,
            "input_set_digest": rec_res.get("input_set_digest"),
            "applicable_set_digest": rec_res.get("applicable_set_digest"),
            "scope_ids": list(rec_res.get("scope_ids") or []),
            "plan_refs": plan_refs,
            "binding_refs": binding_refs,
            "applicable_flow_closure": list(obligations["applicable_flow_ids"]),
            "readiness_path": (gate_res or {}).get("readiness_path"),
            "reconciliation_path": (gate_res or {}).get("reconciliation_path"),
            "requires_chapter6_reverification": bool(rec_res.get("requires_chapter6_reverification")),
            "old_done_covers_new_obligations": False,
            "required_local_self_checks": required_self_checks,
            "required_applicable_regressions": required_regressions,
            "diagnostics": [],
            "governed_handoff": None,
            "delta_governance": None,
            "upstream_reuse": {
                "upstream_reused": True,
                "reused_artifacts": reused_artifacts,
                "reruns_3a_3b": False,
            },
            "recurrence_analysis": {
                **recurrence_analysis,
                "return_stage": "6" if durable_info["recurrence_detected"] else None,
            },
            "verification_breakdown": verification_breakdown,
            "needs_fix_policy": needs_fix_eval,
            "metrics": metrics_base,
            "report_path": None,
        }
    )


def build_chapter6_handoff_summary(
    root: Path | str,
    task_id: Any,
    *,
    run_dir: Path | str | None = None,
    recovery_result: dict[str, Any] | None = None,
    changed_paths: list[str] | None = None,
    fix_through: str = "P1",
) -> dict[str, Any]:
    """Build compact auditable defect-routing summary for Chapter 6 resume/route/lane consumers (zero writes)."""
    full = evaluate_defect_routing(
        root,
        task_id,
        run_dir=run_dir,
        fix_through=fix_through,
        changed_paths=changed_paths,
        recovery_result=recovery_result,
    )
    handoff = full.get("governed_handoff") if isinstance(full.get("governed_handoff"), dict) else None
    resume_ref = (handoff.get("resume_ref") if handoff else None) or next(
        (d.get("resume_ref") for d in (full.get("diagnostics") or []) if isinstance(d, dict) and d.get("resume_ref")),
        None,
    )
    return {
        "schema_version": SCHEMA,
        "ok": full["ok"],
        "defect_class": full["defect_class"],
        "action": full["action"],
        "local_repair_allowed": full["local_repair_allowed"],
        "reruns_3a_3b": full["reruns_3a_3b"],
        "owning_stage": full["owning_stage"],
        "return_stage": full["return_stage"],
        "resume_ref": resume_ref,
        "reason_code": full["reason_code"],
        "reason": full["reason"],
        "classification_rationale": full.get("classification_rationale", ""),
        "plan_refs": full.get("plan_refs") or [],
        "binding_refs": full.get("binding_refs") or [],
        "applicable_flow_ids": full.get("applicable_flow_closure") or [],
        "readiness_path": full.get("readiness_path"),
        "required_local_self_checks": full.get("required_local_self_checks") or [],
        "required_applicable_regressions": full.get("required_applicable_regressions") or [],
        "governed_handoff": handoff,
        "delta_governance": full.get("delta_governance"),
        "upstream_reuse": full.get("upstream_reuse"),
        "recurrence_analysis": {
            "recurrence_detected": bool((full.get("recurrence_analysis") or {}).get("recurrence_detected")),
            "recurrence_count": int((full.get("recurrence_analysis") or {}).get("recurrence_count") or 0),
            "recurring_failure_signature": str((full.get("recurrence_analysis") or {}).get("recurring_failure_signature") or ""),
            "return_stage": (full.get("recurrence_analysis") or {}).get("return_stage"),
            "budget_preserved": True,
        },
        "verification_breakdown": full.get("verification_breakdown"),
        "needs_fix_policy": full.get("needs_fix_policy"),
        "metrics": full.get("metrics"),
        "diagnostics": full.get("diagnostics") or [],
        "flow_completed": False,
        "cumulative_milestone_completed": False,
        **INVARIANT_FLAGS,
    }


def write_report(root: Path | str, report_rel: str, payload: dict[str, Any]) -> str:
    """Write a report ONLY to a new non-reparse logs/ci/.../*.json path with non-null report_path on disk."""
    root_path = task_resolver._validate_root(Path(root))
    _target, rel = ch5_b._validate_log_path(root_path, report_rel, require_logs=True)
    output_payload = deepcopy(payload)
    output_payload["report_path"] = rel
    return ch6_gate.write_report(root_path, rel, output_payload)
