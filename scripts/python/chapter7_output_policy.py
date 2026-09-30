"""Keep current Chapter 7 planning output independent of task freeze policy."""
from __future__ import annotations

import json
from pathlib import Path

DEFAULT_OUTPUT = "docs/planning/chapter7/ui-wiring-board.md"


def output_path(root: Path) -> str:
    profile_path = root / "docs/workflows/chapter7-profile.json"
    profile = json.loads(profile_path.read_text(encoding="utf-8")) if profile_path.is_file() else {}
    if "ui_document_path" in profile:
        return str(profile["ui_document_path"])
    legacy = "docs/gdd/ui-gdd-flow.md"
    declaration = root / "docs/workflows/chapter3-source-set.json"
    if declaration.is_file():
        retired = json.loads(declaration.read_text(encoding="utf-8")).get("retirements", [])
        if any(row["path"] == legacy for row in retired):
            return DEFAULT_OUTPUT
    return legacy


def validate_output(root: Path, requested: Path) -> None:
    target = requested.resolve() if requested.is_absolute() else (root / requested).resolve()
    target.relative_to(root.resolve())
    declaration = root / "docs/workflows/chapter3-source-set.json"
    if declaration.is_file():
        retired = json.loads(declaration.read_text(encoding="utf-8")).get("retirements", [])
        if target in {(root / row["path"]).resolve() for row in retired}:
            raise ValueError("The retired Chapter 7 GDD reference is read-only")
