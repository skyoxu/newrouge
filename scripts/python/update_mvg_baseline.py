#!/usr/bin/env python3
"""Apply a reviewed delta to an existing MVG integration manifest without creating a second lifecycle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from _mvg_manifest import safe_path, validate_manifest

DELTA_SCHEMA = "newrouge.mvg-baseline-delta.v1"
COVERAGE_MODE_RANK = {"pilot": 1, "critical": 2, "full": 3}
EVIDENCE_LEVEL_RANK = {"scene-method": 1, "domain-integration": 2, "engine-input": 2}


def _canonical_sha(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _validate_operations(ops: list[dict[str, Any]], kind: str) -> None:
    ids: list[str] = []
    for op in ops:
        if not isinstance(op, dict):
            raise ValueError(f"invalid {kind} delta operation")
        item_id = str(op.get("id") or "").strip()
        if item_id:
            ids.append(item_id)
    duplicates = sorted({item_id for item_id in ids if ids.count(item_id) > 1})
    if duplicates:
        raise ValueError(f"duplicate or conflicting {kind} operations: {duplicates}")


def _reviewed_authority(payload: dict[str, Any], root: Path | None) -> None:
    authority_ref = str(payload.get("authority_ref") or "").strip()
    review = payload.get("authority_review")
    if root is None:
        raise ValueError("MVG weakening requires repo root for authority validation")
    if not authority_ref:
        raise ValueError("MVG weakening requires authority_ref")
    if not isinstance(review, dict):
        raise ValueError("MVG weakening requires authority_review")
    if str(review.get("status") or "").strip().lower() != "reviewed":
        raise ValueError("MVG authority_review.status must be reviewed")
    if not str(review.get("rationale") or "").strip():
        raise ValueError("MVG authority_review requires rationale")
    path_text = authority_ref.split("#", 1)[0].strip()
    if not path_text:
        raise ValueError("MVG authority_ref must include a repository-relative specification path")
    if not safe_path(root, path_text).is_file():
        raise ValueError(f"MVG authority_ref does not resolve to a file: {path_text}")


def _sequence_removed(before: dict[str, Any], after: dict[str, Any], key: str) -> bool:
    if key not in before or not isinstance(before[key], list):
        return False
    old = {_canonical_sha(item) for item in before[key]}
    new_value = after.get(key, [])
    new = {_canonical_sha(item) for item in new_value} if isinstance(new_value, list) else set()
    return bool(old - new)


def _weakens_baseline(before: dict[str, Any], after: dict[str, Any]) -> bool:
    for key in ("min_tests", "minimum_tests"):
        if key in before:
            try:
                if int(after.get(key, 0)) < int(before[key]):
                    return True
            except (TypeError, ValueError):
                return True
    for key in ("test_ids", "required_flow_ids", "handoffs", "task_ids", "source_paths"):
        if _sequence_removed(before, after, key):
            return True
    if before.get("state") == "implemented" and after.get("state") != "implemented":
        return True
    if "kind" in before and after.get("kind") != before.get("kind"):
        return True
    before_level = str(before.get("evidence_level") or "")
    after_level = str(after.get("evidence_level") or "")
    if before_level and after_level != before_level:
        if EVIDENCE_LEVEL_RANK.get(after_level, 0) < EVIDENCE_LEVEL_RANK.get(before_level, 0):
            return True
    before_mode = str(before.get("mode") or "")
    after_mode = str(after.get("mode") or "")
    if before_mode in COVERAGE_MODE_RANK:
        if COVERAGE_MODE_RANK.get(after_mode, 0) < COVERAGE_MODE_RANK[before_mode]:
            return True
    before_exclusions = set(map(str, before.get("excluded_claims") or []))
    after_exclusions = set(map(str, after.get("excluded_claims") or []))
    if after_exclusions - before_exclusions:
        return True
    return False


def _apply_rows(
    existing: list[dict[str, Any]],
    ops: list[dict[str, Any]],
    kind: str,
    *,
    root: Path | None,
) -> list[dict[str, Any]]:
    _validate_operations(ops, kind)
    result = [dict(row) for row in existing]
    by_id = {str(row.get("id")): idx for idx, row in enumerate(result)}
    for op in ops:
        item_id = str(op.get("id") or "").strip()
        action = str(op.get("action") or "").strip().lower()
        reason = str(op.get("reason") or "").strip()
        if not item_id or action not in {"add", "update", "retain", "retire"} or not reason:
            raise ValueError(f"invalid {kind} delta operation")
        idx = by_id.get(item_id)
        if action == "add":
            if idx is not None or not isinstance(op.get("value"), dict):
                raise ValueError(f"{kind} add collision or missing value: {item_id}")
            row = dict(op["value"])
            if str(row.get("id") or "") != item_id:
                raise ValueError(f"{kind} add id mismatch: {item_id}")
            by_id[item_id] = len(result)
            result.append(row)
        elif action == "retain":
            if idx is None:
                raise ValueError(f"{kind} retain target missing: {item_id}")
        elif action == "update":
            if idx is None or not isinstance(op.get("field_updates"), dict):
                raise ValueError(f"{kind} update target/fields missing: {item_id}")
            updates = dict(op["field_updates"])
            if "id" in updates and str(updates["id"]) != item_id:
                raise ValueError(f"{kind} update cannot rewrite id: {item_id}")
            updated = dict(result[idx])
            updated.update(updates)
            if _weakens_baseline(result[idx], updated):
                _reviewed_authority(op, root)
            result[idx] = updated
        else:
            if idx is None:
                raise ValueError(f"{kind} retire target missing: {item_id}")
            _reviewed_authority(op, root)
            result.pop(idx)
            by_id = {str(row.get("id")): pos for pos, row in enumerate(result)}
    return result


def apply_delta(
    manifest: dict[str, Any],
    delta: dict[str, Any],
    *,
    root: Path | None = None,
    validate_final: bool = False,
) -> dict[str, Any]:
    if delta.get("schema_version") != DELTA_SCHEMA:
        raise ValueError("invalid MVG baseline delta schema")
    expected = str(delta.get("expected_manifest_sha256") or "")
    actual = _canonical_sha(manifest)
    if expected != actual:
        raise ValueError("MVG manifest changed after delta review")
    flow_ops = list(delta.get("flow_operations") or [])
    test_ops = list(delta.get("test_operations") or [])
    updated = dict(manifest)
    updated["flows"] = _apply_rows(list(manifest.get("flows") or []), flow_ops, "flow", root=root)
    updated["tests"] = _apply_rows(list(manifest.get("tests") or []), test_ops, "test", root=root)
    coverage_updates = delta.get("coverage_updates")
    if isinstance(coverage_updates, dict):
        coverage = dict(manifest.get("coverage") or {})
        coverage.update(coverage_updates)
        if _weakens_baseline(dict(manifest.get("coverage") or {}), coverage):
            _reviewed_authority(delta, root)
        updated["coverage"] = coverage
    flow_ids = [str(row.get("id")) for row in updated["flows"]]
    if len(flow_ids) != len(set(flow_ids)):
        raise ValueError("duplicate flow ids after delta")
    test_ids = [str(row.get("id")) for row in updated["tests"]]
    if len(test_ids) != len(set(test_ids)):
        raise ValueError("duplicate test ids after delta")
    required = list((updated.get("coverage") or {}).get("required_flow_ids") or [])
    missing_required = sorted(set(map(str, required)) - set(flow_ids))
    if missing_required:
        raise ValueError("required flow removed without coverage update: " + ", ".join(missing_required))
    known_tests = set(test_ids)
    for flow in updated["flows"]:
        missing = sorted(set(map(str, flow.get("test_ids") or [])) - known_tests)
        if missing:
            raise ValueError(f"flow {flow.get('id')} references missing tests: {missing}")
        for handoff in flow.get("handoffs") or []:
            missing = sorted(set(map(str, handoff.get("test_ids") or [])) - known_tests)
            if missing:
                raise ValueError(f"handoff in {flow.get('id')} references missing tests: {missing}")
    updated["baseline_lineage"] = {
        "previous_manifest_sha256": actual,
        "change_plan_sha256": str(delta.get("change_plan_sha256") or ""),
        "delta_sha256": _canonical_sha(delta),
    }
    if validate_final:
        if root is None:
            raise ValueError("final MVG validation requires repo root")
        errors = validate_manifest(root, updated, executable=False)
        if errors:
            raise ValueError("final MVG manifest invalid: " + "; ".join(errors))
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--delta", required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    manifest_path = Path(args.manifest)
    manifest_path = manifest_path if manifest_path.is_absolute() else root / manifest_path
    delta_path = Path(args.delta)
    delta_path = delta_path if delta_path.is_absolute() else root / delta_path
    try:
        manifest = _load(manifest_path)
        delta = _load(delta_path)
        updated = apply_delta(manifest, delta, root=root, validate_final=True)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"MVG_BASELINE_DELTA status=blocked reason={exc}")
        return 2
    out = Path(args.out) if args.out else manifest_path
    out = out if out.is_absolute() else root / out
    if args.write:
        _write(out, updated)
    print(
        f"MVG_BASELINE_DELTA status={'applied' if args.write else 'preview'} "
        f"manifest={manifest_path} next_sha256={_canonical_sha(updated)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
