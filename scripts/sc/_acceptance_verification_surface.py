from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


VERIFICATION_SURFACES = {
    "core-behavior",
    "godot-scene",
    "player-journey",
    "human-experience",
}
HUMAN_STATUSES = {"pending", "passed", "failed"}


def _list_of_strings(value: Any) -> list[str]:
    return [str(item).strip() for item in value] if isinstance(value, list) and all(str(item).strip() for item in value) else []


def collect_acceptance_verification(triplet: Any) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for view in (getattr(triplet, "back", None), getattr(triplet, "gameplay", None)):
        if not isinstance(view, dict):
            continue
        mapping = view.get("acceptance_verification")
        if not isinstance(mapping, dict):
            continue
        for anchor, raw in mapping.items():
            key = str(anchor or "").strip()
            if not key or not isinstance(raw, dict):
                continue
            if key in merged and merged[key] != raw:
                merged[key] = {"_conflict": True, "_values": [merged[key], raw]}
            else:
                merged[key] = dict(raw)
    return merged


def _resolve_evidence_path(value: str, *, root: Path) -> Path:
    path = Path(str(value or "").strip())
    return path if path.is_absolute() else (root / path)


def _human_evidence_confirms_pass(path: Path, *, revision: str) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return False

    revision_value = str(revision or "").strip()
    if not revision_value:
        return False

    if path.suffix.lower() == ".json":
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            evidence_revision = str(
                payload.get("revision")
                or payload.get("git_revision")
                or payload.get("commit")
                or payload.get("version")
                or ""
            ).strip()
            conclusion = str(
                payload.get("result")
                or payload.get("status")
                or payload.get("verdict")
                or payload.get("conclusion")
                or ""
            ).strip().lower()
            if evidence_revision == revision_value and conclusion == "passed":
                return True

    if revision_value.casefold() not in text.casefold():
        return False
    return bool(
        re.search(
            r"(?im)^\s*(?:result|status|verdict|conclusion)\s*:\s*passed\s*$",
            text,
        )
    )


def _validate_human_evidence(
    *,
    label: str,
    row: dict[str, Any],
    primary: list[str],
    root: Path,
    errors: list[str],
) -> str:
    status = str(row.get("human_evidence_status") or "pending").strip().lower()
    if status not in HUMAN_STATUSES:
        errors.append(f"{label}: invalid human_evidence_status={status}")
        return "invalid"
    if status == "passed":
        revision = str(row.get("human_evidence_revision") or "").strip()
        if not revision:
            errors.append(f"{label}: passed human evidence requires human_evidence_revision")
        paths = [(item, _resolve_evidence_path(item, root=root)) for item in primary]
        missing = [item for item, path in paths if not path.is_file()]
        if missing:
            errors.append(f"{label}: passed human evidence files do not exist: {missing}")
        elif revision and not any(_human_evidence_confirms_pass(path, revision=revision) for _item, path in paths):
            errors.append(
                f"{label}: passed human evidence must explicitly bind revision={revision} and a passed conclusion"
            )
    return status


def _verification_rows(anchor: str, row: dict[str, Any], errors: list[str]) -> list[tuple[str, dict[str, Any]]]:
    raw_obligations = row.get("obligations")
    if raw_obligations is None:
        return [(anchor, row)]
    if not isinstance(raw_obligations, list) or not raw_obligations:
        errors.append(f"{anchor}: obligations must be a non-empty array when present")
        return []
    rows: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_obligations, start=1):
        if not isinstance(raw, dict):
            errors.append(f"{anchor}: obligation #{index} must be an object")
            continue
        obligation_id = str(raw.get("obligation_id") or "").strip()
        if not obligation_id:
            errors.append(f"{anchor}: obligation #{index} requires obligation_id")
            continue
        if obligation_id in seen:
            errors.append(f"{anchor}: duplicate obligation_id={obligation_id}")
            continue
        seen.add(obligation_id)
        rows.append((f"{anchor}#{obligation_id}", dict(raw)))
    return rows


def _validate_row(
    *,
    label: str,
    row: dict[str, Any],
    root: Path,
    errors: list[str],
) -> tuple[str, str]:
    surface = str(row.get("verification_surface") or "").strip()
    if surface not in VERIFICATION_SURFACES:
        errors.append(f"{label}: invalid verification_surface={surface or '<missing>'}")
        return "invalid", surface

    primary = _list_of_strings(row.get("primary_evidence"))
    secondary_raw = row.get("secondary_evidence")
    secondary = [] if secondary_raw in (None, []) else _list_of_strings(secondary_raw)
    if not primary:
        errors.append(f"{label}: primary_evidence must contain at least one bound evidence identity")
    if secondary_raw not in (None, []) and not secondary:
        errors.append(f"{label}: secondary_evidence must be an array of non-empty strings")

    human_required = row.get("human_evidence_required")
    if not isinstance(human_required, bool):
        errors.append(f"{label}: human_evidence_required must be boolean")
        return "invalid", surface

    if surface == "core-behavior" and primary and not any(item.lower().endswith(".cs") for item in primary):
        errors.append(f"{label}: core-behavior primary_evidence must include an xUnit .cs identity")
    if surface == "godot-scene" and primary and not any(item.lower().endswith(".gd") for item in primary):
        errors.append(f"{label}: godot-scene primary_evidence must include a GdUnit .gd identity")

    if surface == "player-journey" and primary and not any(
        item.lower().endswith((".cs", ".gd"))
        for item in primary
    ):
        errors.append(
            f"{label}: player-journey primary_evidence must include an executable .cs or .gd test identity; "
            "integration MVG manifests remain separate integration evidence"
        )

    if surface == "human-experience":
        if human_required is not True:
            errors.append(f"{label}: human-experience requires human_evidence_required=true")
            return "invalid", surface
        return _validate_human_evidence(
            label=label,
            row=row,
            primary=primary,
            root=root,
            errors=errors,
        ), surface

    if human_required:
        return _validate_human_evidence(
            label=label,
            row=row,
            primary=primary,
            root=root,
            errors=errors,
        ), surface
    return "passed", surface


def validate_acceptance_verification(*, triplet: Any, root: Path | None = None) -> dict[str, Any]:
    task_id = str(getattr(triplet, "task_id", "") or "").strip()
    root_dir = Path(root) if root is not None else Path.cwd()
    mapping = collect_acceptance_verification(triplet)
    errors: list[str] = []
    pending: list[str] = []
    failed: list[str] = []
    passed: list[str] = []
    obligations: dict[str, list[dict[str, str]]] = {}
    surfaces: dict[str, Any] = {}

    for anchor, row in sorted(mapping.items()):
        prefix = f"ACC:T{task_id}."
        if not anchor.startswith(prefix):
            errors.append(f"{anchor}: anchor must belong to task {task_id}")
            continue
        if row.get("_conflict"):
            errors.append(f"{anchor}: verification metadata differs across task views")
            continue

        rows = _verification_rows(anchor, row, errors)
        states: list[str] = []
        surface_values: list[str] = []
        obligation_rows: list[dict[str, str]] = []
        for label, obligation in rows:
            state, surface = _validate_row(
                label=label,
                row=obligation,
                root=root_dir,
                errors=errors,
            )
            states.append(state)
            surface_values.append(surface)
            obligation_rows.append(
                {
                    "obligation_id": label.split("#", 1)[1] if "#" in label else "",
                    "verification_surface": surface,
                    "status": state,
                    "source_anchor": anchor,
                }
            )
        if obligation_rows:
            obligations[anchor] = obligation_rows

        if len(surface_values) == 1:
            surfaces[anchor] = surface_values[0]
        elif surface_values:
            surfaces[anchor] = surface_values

        if not states or "invalid" in states:
            continue
        if "failed" in states:
            failed.append(anchor)
        elif "pending" in states:
            pending.append(anchor)
        elif all(state == "passed" for state in states):
            passed.append(anchor)

    status = "fail" if errors or failed or pending else "ok"
    return {
        "status": status,
        "classified_count": len(mapping),
        "errors": errors,
        "passed_anchors": passed,
        "pending_anchors": pending,
        "failed_anchors": failed,
        "surfaces": surfaces,
        "obligations": obligations,
    }
