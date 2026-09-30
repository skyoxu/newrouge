#!/usr/bin/env python3
"""Shared deterministic helpers for post-Chapter-5 planning skills."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

RUNNER_SCHEMA = "newrouge.isolated-model-runner.v1"
SENSITIVE_CAPABILITY_KEYS = {
    "capability_ref",
    "capability_refs",
    "capability_id",
    "capability_ids",
    "capability_title",
    "capability_titles",
}


def load_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def canonical_sha(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def file_sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def repo_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    resolved = path if path.is_absolute() else root / path
    resolved = resolved.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"path escapes repository: {value}")
    return resolved


def relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def scrub_capability_answers(value: Any) -> Any:
    if isinstance(value, list):
        return [scrub_capability_answers(item) for item in value]
    if isinstance(value, dict):
        return {
            key: scrub_capability_answers(item)
            for key, item in value.items()
            if str(key) not in SENSITIVE_CAPABILITY_KEYS
        }
    return value


def source_classification_signal(text: str) -> dict[str, Any]:
    terms = re.findall(r"(?i)\bcapabilit(?:y|ies)\b|能力|模块", text)
    return {"present": bool(terms), "term_count": len(terms)}


def build_blinded_analysis_bundle(
    root: Path,
    out_dir: Path,
    *,
    source_manifest_path: Path,
    ledger_path: Path,
    semantics_path: Path,
    task_view_paths: list[Path],
    readiness_summary: dict[str, Any],
) -> dict[str, Any]:
    manifest = load_json(source_manifest_path, {})
    ledger = load_json(ledger_path, {})
    semantics = load_json(semantics_path, {})
    if manifest.get("schema_version") != "chapter3.source-manifest.v1":
        raise ValueError("invalid source manifest")
    if ledger.get("schema_version") != "newrouge.source-blocks.v1":
        raise ValueError("invalid source block ledger")
    if semantics.get("schema_version") != "newrouge.semantic-requirements.v1":
        raise ValueError("invalid semantic requirements")

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    files: dict[str, str] = {}
    classification: dict[str, Any] = {}

    for row in manifest.get("sources", []):
        if not isinstance(row, dict):
            continue
        value = str(row.get("path") or "").strip()
        if not value:
            continue
        source = repo_path(root, value)
        if not source.is_file():
            raise ValueError(f"missing declared source: {value}")
        target = out_dir / "sources" / value
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        files[f"sources/{value}"] = file_sha(target)
        classification[value] = source_classification_signal(
            source.read_text(encoding="utf-8", errors="replace")
        )

    for name, source in (
        ("source-manifest.v1.json", source_manifest_path),
        ("source-blocks.v1.json", ledger_path),
        ("semantic-requirements.v1.json", semantics_path),
    ):
        target = out_dir / name
        shutil.copyfile(source, target)
        files[name] = file_sha(target)

    task_dir = out_dir / "task-views"
    task_dir.mkdir(parents=True, exist_ok=True)
    for source in task_view_paths:
        payload = load_json(source, [])
        target = task_dir / source.name
        atomic_json(target, scrub_capability_answers(payload))
        files[f"task-views/{source.name}"] = file_sha(target)

    atomic_json(out_dir / "readiness-summary.json", readiness_summary)
    files["readiness-summary.json"] = file_sha(out_dir / "readiness-summary.json")
    index = {
        "schema_version": "newrouge.planning-analysis-input.v1",
        "source_revision": ledger.get("source_revision") or manifest.get("source_revision"),
        "source_manifest_sha256": ledger.get("source_manifest_sha256") or manifest.get("manifest_sha256"),
        "files": files,
        "blinded_fields": sorted(SENSITIVE_CAPABILITY_KEYS),
        "source_declared_classification": classification,
    }
    index["analysis_identity_sha256"] = canonical_sha(index)
    atomic_json(out_dir / "analysis-index.json", index)
    return index


def parse_model_json(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8").strip()
    if text.startswith("~~~") or text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 2:
            lines = lines[1:]
        if lines and (lines[-1].strip().startswith("~~~") or lines[-1].strip().startswith("```")):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("model output must be a JSON object")
    return payload


def inspect_isolated_runner(executable: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [str(executable), "--describe"],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    if proc.returncode != 0:
        raise ValueError(f"isolation runner describe failed: {proc.stdout.strip()}")
    payload = json.loads(proc.stdout)
    validate_runner_description(payload)
    return payload


def validate_runner_description(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != RUNNER_SCHEMA:
        raise ValueError("unsupported isolation runner schema")
    if payload.get("filesystem_scope") != "workspace_only":
        raise ValueError("formal Capability generation requires workspace-only filesystem reads")
    if payload.get("fresh_session_per_invocation") is not True:
        raise ValueError("formal Capability generation requires a fresh model session per invocation")
    if payload.get("can_read_outside_workspace") is not False:
        raise ValueError("formal Capability generation rejects runners that can read outside the workspace")
    if not str(payload.get("model") or "").strip():
        raise ValueError("isolation runner must report the model identity")


def run_isolated_model(
    executable: Path,
    *,
    workspace: Path,
    prompt_path: Path,
    output_path: Path,
    timeout_sec: int,
) -> dict[str, Any]:
    proc = subprocess.run(
        [
            str(executable),
            "--workspace", str(workspace),
            "--prompt-file", str(prompt_path),
            "--output", str(output_path),
            "--timeout-sec", str(timeout_sec),
        ],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=max(timeout_sec + 30, 60),
    )
    if proc.returncode != 0:
        raise RuntimeError(f"isolated model runner failed: {proc.stdout.strip()}")
    if not output_path.is_file():
        raise RuntimeError("isolated model runner produced no output")
    receipt = {}
    for line in reversed(proc.stdout.splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                receipt = candidate
                break
    return receipt
