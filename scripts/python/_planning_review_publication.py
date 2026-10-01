"""Recover a validated review's multi-file publication without another model call."""
import json
from pathlib import Path
from typing import Any, Callable

from _planning_skill_common import canonical_sha, file_sha, load_json, parse_model_json, repo_path, text_sha


def serialized_sha(payload: Any) -> str:
    return text_sha(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _checkpoint_sha(checkpoint: dict[str, Any]) -> str:
    return canonical_sha({key: checkpoint.get(key) for key in ("schema_version", "status", "identity", "entries")})


def publication_complete(path: Path) -> bool:
    checkpoint = load_json(path, {})
    if (not isinstance(checkpoint, dict) or checkpoint.get("schema_version") != "newrouge.review-publication.v1"
        or checkpoint.get("status") not in {"pending", "complete"}
        or checkpoint.get("content_sha256") != _checkpoint_sha(checkpoint)):
        raise ValueError("Review publication checkpoint is invalid")
    return checkpoint["status"] == "complete"


def completed_output(attempts: list[dict[str, Any]], output: Path) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Recover a settled invocation before its publication checkpoint exists."""
    if not attempts or attempts[-1].get("status") != "completed":
        return None
    record = attempts[-1]
    if not output.is_file() or file_sha(output) != record.get("output_sha256"):
        raise ValueError("Completed review attempt output identity drift; preserve its evidence")
    return record, parse_model_json(output)


def prepare_publication(path: Path, identity: dict[str, Any], payloads: dict[str, Any], writer: Callable) -> None:
    if path.exists():
        raise ValueError("Review publication already exists; recover its recorded result")
    entries = []
    for rel, payload in payloads.items():
        target = repo_path(path.parent, rel)
        entries.append({"path": rel, "before_sha256": file_sha(target) if target.is_file() else None,
            "after_sha256": serialized_sha(payload), "payload": payload})
    checkpoint = {"schema_version": "newrouge.review-publication.v1", "status": "pending",
        "identity": identity, "entries": entries}
    checkpoint["content_sha256"] = _checkpoint_sha(checkpoint)
    writer(path, checkpoint)


def resume_publication(path: Path, identity: dict[str, Any], writer: Callable) -> bool:
    if not path.is_file():
        return False
    checkpoint = load_json(path, {})
    if (not isinstance(checkpoint, dict) or checkpoint.get("schema_version") != "newrouge.review-publication.v1"
        or checkpoint.get("status") not in {"pending", "complete"}
        or checkpoint.get("identity") != identity
        or checkpoint.get("content_sha256") != _checkpoint_sha(checkpoint)):
        raise ValueError("Review publication identity changed or checkpoint is invalid")
    entries = checkpoint["entries"]
    if (not isinstance(entries, list) or not entries or any(not isinstance(row, dict)
            or not isinstance(row.get("path"), str) or "payload" not in row
            or not isinstance(row.get("after_sha256"), str) or "before_sha256" not in row for row in entries)):
        raise ValueError("Review publication entries are invalid")
    if len({row["path"] for row in entries}) != len(entries):
        raise ValueError("Review publication contains duplicate targets")
    for row in entries:
        if serialized_sha(row["payload"]) != row["after_sha256"]:
            raise ValueError("Review publication payload identity changed")
        target = repo_path(path.parent, row["path"])
        if target == path.resolve():
            raise ValueError("Review publication cannot overwrite its checkpoint")
        actual = file_sha(target) if target.is_file() else None
        allowed = {row["after_sha256"]} if checkpoint["status"] == "complete" else {row["before_sha256"], row["after_sha256"]}
        if actual not in allowed:
            raise ValueError("Review publication target " + row["path"] + " identity drift")
    if checkpoint["status"] == "complete":
        return True
    for row in entries:
        target = repo_path(path.parent, row["path"])
        if not target.is_file() or file_sha(target) != row["after_sha256"]:
            writer(target, row["payload"])
    checkpoint["status"] = "complete"
    checkpoint["content_sha256"] = _checkpoint_sha(checkpoint)
    writer(path, checkpoint)
    return True
