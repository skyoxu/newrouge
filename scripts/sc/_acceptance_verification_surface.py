from __future__ import annotations

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


def validate_acceptance_verification(*, triplet: Any) -> dict[str, Any]:
    task_id = str(getattr(triplet, "task_id", "") or "").strip()
    mapping = collect_acceptance_verification(triplet)
    errors: list[str] = []
    pending: list[str] = []
    failed: list[str] = []
    passed: list[str] = []

    for anchor, row in sorted(mapping.items()):
        prefix = f"ACC:T{task_id}."
        if not anchor.startswith(prefix):
            errors.append(f"{anchor}: anchor must belong to task {task_id}")
            continue
        if row.get("_conflict"):
            errors.append(f"{anchor}: verification metadata differs across task views")
            continue
        surface = str(row.get("verification_surface") or "").strip()
        if surface not in VERIFICATION_SURFACES:
            errors.append(f"{anchor}: invalid verification_surface={surface or '<missing>'}")
            continue
        primary = _list_of_strings(row.get("primary_evidence"))
        secondary_raw = row.get("secondary_evidence")
        secondary = [] if secondary_raw in (None, []) else _list_of_strings(secondary_raw)
        if not primary:
            errors.append(f"{anchor}: primary_evidence must contain at least one bound evidence identity")
        if secondary_raw not in (None, []) and not secondary:
            errors.append(f"{anchor}: secondary_evidence must be an array of non-empty strings")
        human_required = row.get("human_evidence_required")
        if not isinstance(human_required, bool):
            errors.append(f"{anchor}: human_evidence_required must be boolean")
            continue

        if surface == "human-experience":
            if human_required is not True:
                errors.append(f"{anchor}: human-experience requires human_evidence_required=true")
                continue
            human_status = str(row.get("human_evidence_status") or "pending").strip().lower()
            if human_status not in HUMAN_STATUSES:
                errors.append(f"{anchor}: invalid human_evidence_status={human_status}")
                continue
            if human_status == "passed":
                passed.append(anchor)
            elif human_status == "failed":
                failed.append(anchor)
            else:
                pending.append(anchor)
            continue

        if human_required:
            human_status = str(row.get("human_evidence_status") or "pending").strip().lower()
            if human_status == "passed":
                passed.append(anchor)
            elif human_status == "failed":
                failed.append(anchor)
            else:
                pending.append(anchor)
        else:
            passed.append(anchor)

        if surface == "core-behavior" and primary and not any(item.lower().endswith(".cs") for item in primary):
            errors.append(f"{anchor}: core-behavior primary_evidence must include an xUnit .cs identity")
        if surface == "godot-scene" and primary and not any(item.lower().endswith(".gd") for item in primary):
            errors.append(f"{anchor}: godot-scene primary_evidence must include a GdUnit .gd identity")

    status = "fail" if errors or failed or pending else "ok"
    return {
        "status": status,
        "classified_count": len(mapping),
        "errors": errors,
        "passed_anchors": passed,
        "pending_anchors": pending,
        "failed_anchors": failed,
        "surfaces": {
            anchor: str(row.get("verification_surface") or "")
            for anchor, row in sorted(mapping.items())
            if not row.get("_conflict")
        },
    }
