#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compare task files checksum snapshot with overlay index baseline.

Usage (Windows):
  py -3 scripts/python/remind_overlay_task_drift.py
  py -3 scripts/python/remind_overlay_task_drift.py --write
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any


OVERLAY_INDEX = Path("docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/_index.md")
TASK_FILES = [
    Path(".taskmaster/tasks/tasks.json"),
    Path(".taskmaster/tasks/tasks_back.json"),
    Path(".taskmaster/tasks/tasks_gameplay.json"),
]

BASELINE_RE = re.compile(
    r"(<!-- TASK_BASELINE_START -->\s*```json\s*)(.*?)(\s*```\s*<!-- TASK_BASELINE_END -->)",
    re.DOTALL,
)


def _sha256(path: Path) -> str:
    data = _canonical_bytes(path)
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(path: Path) -> bytes:
    """Return canonical content bytes for cross-platform stable hashing.

    We normalize CRLF and lone CR to LF so Windows and CI checkouts produce
    the same digest, including malformed CRCRLF working-tree variants.
    """
    data = path.read_bytes()
    # First collapse CRLF into LF, then normalize any remaining CR bytes.
    normalized = data.replace(b"\r\n", b"\n")
    return normalized.replace(b"\r", b"\n")


def _build_baseline(repo_root: Path) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for rel in TASK_FILES:
        full_path = repo_root / rel
        if not full_path.exists():
            entries.append(
                {
                    "path": str(rel).replace("\\", "/"),
                    "exists": False,
                    "sha256": None,
                    "bytes": 0,
                }
            )
            continue

        entries.append(
            {
                "path": str(rel).replace("\\", "/"),
                "exists": True,
                "sha256": _sha256(full_path),
                "bytes": len(_canonical_bytes(full_path)),
            }
        )

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "files": entries,
    }


def _load_index(repo_root: Path) -> str:
    full_path = repo_root / OVERLAY_INDEX
    if not full_path.exists():
        raise FileNotFoundError(f"overlay index not found: {full_path}")
    return full_path.read_text(encoding="utf-8")


def _extract_embedded_baseline(index_text: str) -> dict[str, Any] | None:
    match = BASELINE_RE.search(index_text)
    if not match:
        return None
    payload = match.group(2).strip()
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def _replace_embedded_baseline(index_text: str, baseline: dict[str, Any]) -> str:
    rendered = json.dumps(baseline, ensure_ascii=False, indent=2)

    def _sub(match: re.Match[str]) -> str:
        return f"{match.group(1)}{rendered}{match.group(3)}"

    if not BASELINE_RE.search(index_text):
        raise ValueError("TASK_BASELINE block not found in overlay index")
    return BASELINE_RE.sub(_sub, index_text, count=1)


def _normalized_entries(entries: list[dict[str, Any]]) -> list[tuple[str, bool, str | None, int]]:
    normalized: list[tuple[str, bool, str | None, int]] = []
    for item in entries:
        normalized.append(
            (
                str(item.get("path") or ""),
                bool(item.get("exists")),
                item.get("sha256"),
                int(item.get("bytes") or 0),
            )
        )
    return sorted(normalized)


def _entries_equal(lhs: dict[str, Any] | None, rhs: dict[str, Any]) -> bool:
    if not lhs:
        return False
    lhs_entries = _normalized_entries(list(lhs.get("files") or []))
    rhs_entries = _normalized_entries(list(rhs.get("files") or []))
    return lhs_entries == rhs_entries


def main() -> int:
    parser = argparse.ArgumentParser(description="Overlay task-drift reminder based on embedded checksum baseline.")
    parser.add_argument("--write", action="store_true", help="Update baseline in overlay index with current checksums.")
    args = parser.parse_args()

    repo_root = Path.cwd().resolve()
    index_path = repo_root / OVERLAY_INDEX

    current = _build_baseline(repo_root)
    index_text = _load_index(repo_root)
    embedded = _extract_embedded_baseline(index_text)

    if args.write:
        # Stop-loss: avoid rewriting generated_at on every run when checksum entries are unchanged.
        # This keeps smart-commit idempotent and prevents noisy dirty working trees.
        if _entries_equal(embedded, current):
            print("OVERLAY_TASK_BASELINE status=ok drift=false")
            return 0
        updated_text = _replace_embedded_baseline(index_text, current)
        index_path.write_text(updated_text, encoding="utf-8")
        print(f"OVERLAY_TASK_BASELINE status=updated file={OVERLAY_INDEX.as_posix()}")
        return 0

    if not embedded:
        print("OVERLAY_TASK_BASELINE status=missing action=run-with---write")
        return 1

    embedded_entries = _normalized_entries(list(embedded.get("files") or []))
    current_entries = _normalized_entries(list(current.get("files") or []))

    if embedded_entries == current_entries:
        print("OVERLAY_TASK_BASELINE status=ok drift=false")
        return 0

    print("OVERLAY_TASK_BASELINE status=drift drift=true action=run-with---write")
    for old, new in zip(embedded_entries, current_entries):
        if old != new:
            print(f" - changed old={old} new={new}")
    if len(embedded_entries) != len(current_entries):
        print(f" - entries_count old={len(embedded_entries)} new={len(current_entries)}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
