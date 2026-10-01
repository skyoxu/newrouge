#!/usr/bin/env python3
"""Shared deterministic helpers for post-Chapter-5 planning skills."""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import shutil
import subprocess
import sys
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


def normalized_file_sha(path: Path) -> str:
    """Use the MVG runner's content identity across Git newline conversions."""
    from _mvg_manifest import manifest_sha256
    return manifest_sha256(path.read_bytes())


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


def scrub_capability_answers_with_paths(
    value: Any,
    *,
    path: str = "$",
) -> tuple[Any, list[str]]:
    removed: list[str] = []
    if isinstance(value, list):
        output = []
        for index, item in enumerate(value):
            scrubbed, nested = scrub_capability_answers_with_paths(
                item, path=f"{path}[{index}]"
            )
            output.append(scrubbed)
            removed.extend(nested)
        return output, removed
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if key_text in SENSITIVE_CAPABILITY_KEYS:
                removed.append(child_path)
                continue
            scrubbed, nested = scrub_capability_answers_with_paths(
                item, path=child_path
            )
            output[key_text] = scrubbed
            removed.extend(nested)
        return output, removed
    return value, removed


def scrub_capability_answers(value: Any) -> Any:
    scrubbed, _removed = scrub_capability_answers_with_paths(value)
    return scrubbed


def _write_model_batches(
    out_dir: Path,
    *,
    ledger: dict[str, Any],
    semantics: dict[str, Any],
    char_budget: int,
) -> dict[str, Any]:
    if char_budget < 1000:
        raise ValueError("Capability model batch char budget must be at least 1000")
    batches_dir = out_dir / "model-batches"
    batches_dir.mkdir(parents=True, exist_ok=True)
    clean_ledger = scrub_capability_answers(ledger)
    clean_semantics = scrub_capability_answers(semantics)
    requirements = [
        row for row in clean_semantics.get("requirements", [])
        if isinstance(row, dict) and str(row.get("requirement_id") or "").strip()
    ]
    by_block: dict[str, list[dict[str, Any]]] = {}
    for row in requirements:
        for block_id in row.get("source_block_ids", []):
            by_block.setdefault(str(block_id), []).append(row)

    payloads: list[dict[str, Any]] = []
    current_blocks: list[dict[str, Any]] = []
    current_requirements: dict[str, dict[str, Any]] = {}
    current_chars = 0
    seen_requirements: set[str] = set()

    def flush(*, oversize_blocks: list[str] | None = None) -> None:
        nonlocal current_blocks, current_requirements, current_chars
        if not current_blocks and not current_requirements:
            return
        payloads.append({
            "schema_version": "newrouge.capability-model-batch.v1",
            "blocks": current_blocks,
            "requirements": list(current_requirements.values()),
            "oversize_blocks": list(oversize_blocks or []),
        })
        current_blocks = []
        current_requirements = {}
        current_chars = 0

    for block in clean_ledger.get("blocks", []):
        if not isinstance(block, dict):
            continue
        block_id = str(block.get("block_id") or "")
        linked = by_block.get(block_id, [])
        item = {"block": block, "requirements": linked}
        item_chars = len(json.dumps(item, ensure_ascii=False))
        if current_blocks and current_chars + item_chars > char_budget:
            flush()
        if item_chars > char_budget:
            current_blocks = [block]
            current_requirements = {
                str(row["requirement_id"]): row for row in linked
            }
            seen_requirements.update(current_requirements)
            current_chars = item_chars
            flush(oversize_blocks=[block_id])
            continue
        current_blocks.append(block)
        current_chars += item_chars
        for row in linked:
            rid = str(row["requirement_id"])
            current_requirements[rid] = row
            seen_requirements.add(rid)
    flush()

    remaining = [
        row for row in requirements
        if str(row["requirement_id"]) not in seen_requirements
    ]
    current: list[dict[str, Any]] = []
    current_chars = 0
    for row in remaining:
        row_chars = len(json.dumps(row, ensure_ascii=False))
        if current and current_chars + row_chars > char_budget:
            payloads.append({
                "schema_version": "newrouge.capability-model-batch.v1",
                "blocks": [],
                "requirements": current,
                "oversize_blocks": [],
            })
            current = []
            current_chars = 0
        current.append(row)
        current_chars += row_chars
    if current:
        payloads.append({
            "schema_version": "newrouge.capability-model-batch.v1",
            "blocks": [],
            "requirements": current,
            "oversize_blocks": [],
        })

    rows = []
    for index, payload in enumerate(payloads, 1):
        payload["batch_index"] = index
        payload["batch_count"] = len(payloads)
        path = batches_dir / f"batch-{index:03d}.json"
        atomic_json(path, payload)
        rows.append({
            "path": f"model-batches/{path.name}",
            "sha256": file_sha(path),
            "block_ids": [
                str(row.get("block_id") or "")
                for row in payload["blocks"]
                if str(row.get("block_id") or "").strip()
            ],
            "requirement_ids": sorted({
                str(row.get("requirement_id") or "")
                for row in payload["requirements"]
                if str(row.get("requirement_id") or "").strip()
            }),
            "oversize_blocks": payload["oversize_blocks"],
        })
    index = {
        "schema_version": "newrouge.capability-model-batch-index.v1",
        "char_budget": char_budget,
        "batch_count": len(rows),
        "block_count": len([
            row for row in clean_ledger.get("blocks", []) if isinstance(row, dict)
        ]),
        "requirement_count": len(requirements),
        "batches": rows,
    }
    atomic_json(out_dir / "model-batches" / "batch-index.json", index)
    return index


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
    model_batch_char_budget: int = 160000,
    repository_identity: dict[str, Any] | None = None,
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
    authority_inputs: dict[str, str] = {}
    transformations: list[dict[str, Any]] = []

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
        authority_inputs[value] = file_sha(source)
        classification[value] = source_classification_signal(
            source.read_text(encoding="utf-8", errors="replace")
        )

    for name, source, payload in (
        ("source-manifest.v1.json", source_manifest_path, manifest),
        ("source-blocks.v1.json", ledger_path, ledger),
        ("semantic-requirements.v1.json", semantics_path, semantics),
    ):
        target = out_dir / name
        scrubbed, removed = scrub_capability_answers_with_paths(payload)
        atomic_json(target, scrubbed)
        files[name] = file_sha(target)
        authority_inputs[relative(root, source)] = file_sha(source)
        transformations.append({
            "source_path": relative(root, source),
            "analysis_path": name,
            "source_sha256": file_sha(source),
            "analysis_sha256": files[name],
            "removed_fields": removed,
        })

    task_dir = out_dir / "task-views"
    task_dir.mkdir(parents=True, exist_ok=True)
    for source in task_view_paths:
        payload = load_json(source, [])
        target = task_dir / source.name
        scrubbed, removed = scrub_capability_answers_with_paths(payload)
        atomic_json(target, scrubbed)
        analysis_name = f"task-views/{source.name}"
        files[analysis_name] = file_sha(target)
        authority_inputs[relative(root, source)] = file_sha(source)
        transformations.append({
            "source_path": relative(root, source),
            "analysis_path": analysis_name,
            "source_sha256": file_sha(source),
            "analysis_sha256": files[analysis_name],
            "removed_fields": removed,
        })

    batch_index = _write_model_batches(
        out_dir,
        ledger=ledger,
        semantics=semantics,
        char_budget=model_batch_char_budget,
    )
    files["model-batches/batch-index.json"] = file_sha(
        out_dir / "model-batches" / "batch-index.json"
    )
    for row in batch_index["batches"]:
        files[str(row["path"])] = str(row["sha256"])

    atomic_json(out_dir / "readiness-summary.json", readiness_summary)
    files["readiness-summary.json"] = file_sha(out_dir / "readiness-summary.json")
    for row in readiness_summary.get("tasks", []):
        if not isinstance(row, dict):
            continue
        rel_path = str(row.get("readiness_path") or "").strip()
        if not rel_path:
            continue
        path = repo_path(root, rel_path)
        if path.is_file():
            authority_inputs[rel_path] = file_sha(path)
    index = {
        "schema_version": "newrouge.planning-analysis-input.v1",
        "source_revision": ledger.get("source_revision") or manifest.get("source_revision"),
        "repository_identity": dict(repository_identity or {}),
        "source_manifest_sha256": ledger.get("source_manifest_sha256") or manifest.get("manifest_sha256"),
        "files": files,
        "blinded_fields": sorted(SENSITIVE_CAPABILITY_KEYS),
        "blinding_transformations": transformations,
        "authority_inputs": authority_inputs,
        "model_batch_index": batch_index,
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


def _runner_prefix(executable: Path) -> list[str]:
    if executable.suffix.casefold() == ".py":
        return [sys.executable, str(executable)]
    return [str(executable)]


def inspect_isolated_runner(executable: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [*_runner_prefix(executable), "--describe"],
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
    if payload.get("model_tools") != []:
        raise ValueError("formal Capability generation requires a no-tools model session")


def _terminate_process_tree(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
            )
            if proc.poll() is not None:
                return
            proc.kill()
            return
        except (OSError, subprocess.SubprocessError):
            proc.kill()
            return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        proc.kill()


def run_isolated_model(
    executable: Path,
    *,
    workspace: Path,
    prompt_path: Path,
    output_path: Path,
    timeout_sec: int,
) -> dict[str, Any]:
    cmd = [
        *_runner_prefix(executable),
        "--workspace", str(workspace),
        "--prompt-file", str(prompt_path),
        "--output", str(output_path),
        "--timeout-sec", str(timeout_sec),
    ]
    kwargs: dict[str, Any] = {
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(cmd, **kwargs)
    try:
        stdout, _stderr = proc.communicate(timeout=max(timeout_sec + 30, 60))
    except subprocess.TimeoutExpired as exc:
        _terminate_process_tree(proc)
        stdout, _stderr = proc.communicate()
        raise TimeoutError(
            f"isolated model runner timed out after {timeout_sec}s: {stdout[-2000:]}"
        ) from exc
    except BaseException:
        _terminate_process_tree(proc)
        proc.communicate(timeout=15)
        raise
    if proc.returncode != 0:
        raise RuntimeError(f"isolated model runner failed: {stdout.strip()}")
    if not output_path.is_file():
        raise RuntimeError("isolated model runner produced no output")
    receipt = {}
    for line in reversed(stdout.splitlines()):
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
