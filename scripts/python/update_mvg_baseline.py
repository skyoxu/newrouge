#!/usr/bin/env python3
"""Apply a reviewed delta to an existing MVG integration manifest without creating a second lifecycle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

DELTA_SCHEMA = "newrouge.mvg-baseline-delta.v1"


def _canonical_sha(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def _apply_rows(existing: list[dict[str, Any]], ops: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
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
            updated = dict(result[idx])
            updated.update(op["field_updates"])
            if _weakens_baseline(result[idx], updated) and not str(op.get("authority_ref") or "").strip():
                raise ValueError(f"{kind} weakening requires authority_ref: {item_id}")
            result[idx] = updated
        else:
            if idx is None:
                raise ValueError(f"{kind} retire target missing: {item_id}")
            authority = str(op.get("authority_ref") or "").strip()
            if not authority:
                raise ValueError(f"{kind} retire requires authority_ref: {item_id}")
            result.pop(idx)
            by_id = {str(row.get("id")): pos for pos, row in enumerate(result)}
    return result


def _weakens_baseline(before: dict[str, Any], after: dict[str, Any]) -> bool:
    for key in ("min_tests", "minimum_tests"):
        if key in before:
            try:
                if int(after.get(key, 0)) < int(before[key]):
                    return True
            except (TypeError, ValueError):
                return True
    for key in ("test_ids", "required_flow_ids", "handoffs"):
        if key in before and isinstance(before[key], list):
            old = {_canonical_sha(item) for item in before[key]}
            new = {_canonical_sha(item) for item in after.get(key, [])} if isinstance(after.get(key), list) else set()
            if old - new:
                return True
    if before.get("state") == "implemented" and after.get("state") != "implemented":
        return True
    return False


def apply_delta(manifest: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
    if delta.get("schema_version") != DELTA_SCHEMA:
        raise ValueError("invalid MVG baseline delta schema")
    expected = str(delta.get("expected_manifest_sha256") or "")
    actual = _canonical_sha(manifest)
    if expected != actual:
        raise ValueError("MVG manifest changed after delta review")
    updated = dict(manifest)
    updated["flows"] = _apply_rows(list(manifest.get("flows") or []), list(delta.get("flow_operations") or []), "flow")
    updated["tests"] = _apply_rows(list(manifest.get("tests") or []), list(delta.get("test_operations") or []), "test")
    coverage_updates = delta.get("coverage_updates")
    if isinstance(coverage_updates, dict):
        coverage = dict(manifest.get("coverage") or {})
        coverage.update(coverage_updates)
        if _weakens_baseline(dict(manifest.get("coverage") or {}), coverage) and not str(delta.get("authority_ref") or "").strip():
            raise ValueError("coverage weakening requires authority_ref")
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
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--delta", required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    manifest_path = Path(args.manifest)
    delta_path = Path(args.delta)
    try:
        manifest = _load(manifest_path)
        delta = _load(delta_path)
        updated = apply_delta(manifest, delta)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"MVG_BASELINE_DELTA status=blocked reason={exc}")
        return 2
    out = Path(args.out) if args.out else manifest_path
    if args.write:
        _write(out, updated)
    print(
        f"MVG_BASELINE_DELTA status={'applied' if args.write else 'preview'} "
        f"manifest={manifest_path} next_sha256={_canonical_sha(updated)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
