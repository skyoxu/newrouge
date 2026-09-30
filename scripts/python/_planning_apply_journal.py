"""Durable roll-forward for a reviewed multi-file planning apply."""
import base64
import json
from pathlib import Path
from typing import Any, Callable

from _planning_skill_common import atomic_json, file_sha, load_json, relative, repo_path, text_sha


def create_journal(root: Path, path: Path, targets: dict[Path, Any], authority: dict[str, Any],
                   result: dict[str, Any]) -> dict[str, Any]:
    entries = []
    for target, payload in targets.items():
        raw = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        entries.append({"path": relative(root, target), "before_sha256": file_sha(target) if target.is_file() else None,
            "before_base64": base64.b64encode(target.read_bytes()).decode() if target.is_file() else None,
            "after_sha256": text_sha(raw), "payload": payload})
    journal = {"schema_version": "newrouge.planning-apply-journal.v1", "status": "pending",
        "authority_inputs": authority, "entries": entries, "result": result}
    atomic_json(path, journal)
    return journal


def resume_journal(root: Path, path: Path, writer: Callable) -> dict[str, Any]:
    journal = load_json(path, {})
    if journal.get("schema_version") != "newrouge.planning-apply-journal.v1":
        raise ValueError("invalid planning apply journal")
    entries = journal["entries"]
    owned = {row["path"] for row in entries}
    # Validate the entire transaction before replacing any file. Subsequent user
    # changes are never treated as writes made by this transaction.
    for rel, expected in journal["authority_inputs"].items():
        if rel in owned:
            continue
        target = repo_path(root, rel)
        actual = file_sha(target) if target.is_file() else None
        if actual != expected:
            raise ValueError(f"planning recovery input drift:{rel}")
    for row in entries:
        if text_sha(json.dumps(row["payload"], ensure_ascii=False, indent=2) + "\n") != row["after_sha256"]:
            raise ValueError("planning journal payload identity changed")
        target = repo_path(root, row["path"])
        actual = file_sha(target) if target.is_file() else None
        allowed = {row["after_sha256"]} if journal["status"] == "complete" else {row["before_sha256"], row["after_sha256"]}
        if actual not in allowed:
            raise ValueError(f"planning recovery target drift:{row['path']}")
    for row in entries:
        target = repo_path(root, row["path"])
        if not target.is_file() or file_sha(target) != row["after_sha256"]:
            writer(target, row["payload"])
    journal["status"] = "complete"
    atomic_json(path, journal)
    return journal["result"]
