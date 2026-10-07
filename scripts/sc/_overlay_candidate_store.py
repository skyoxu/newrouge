from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from _overlay_generator_scaffold import select_pages_by_family
from _overlay_generator_support import classify_page_kind, normalize_relpath, write_json


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def page_name(value: str) -> str:
    if not value.endswith(".md") or any(char in value for char in ("/", "\\", ":")) or value in {".md", "..md"}:
        raise ValueError(f"Invalid overlay filename: {value}")
    return value


def overlay_dir(root: Path, prd_id: str) -> Path:
    if not prd_id or prd_id in {".", ".."} or any(char in prd_id for char in ("/", "\\", ":")):
        raise ValueError("Invalid candidate PRD-ID")
    parent = (root / "docs/architecture/overlays").resolve()
    target = (parent / prd_id / "08").resolve()
    if not target.is_relative_to(parent):
        raise ValueError("Overlay target escaped the repository")
    return target


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Expected an object")
        return value
    except (OSError, ValueError) as exc:
        raise ValueError(f"Candidate artifact missing or invalid: {path}") from exc


def artifact_path(root: Path, value: str) -> Path:
    path = Path(value)
    path = (path if path.is_absolute() else root / path).resolve()
    if not path.is_relative_to((root / "logs/ci").resolve()):
        raise ValueError("Candidate artifact must be under logs/ci")
    return path


def build_candidate_inputs(
    *, repo_root: Path, prd_path: Path, companion_paths: list[Path], prd_id: str, page_mode: str,
) -> dict[str, Any]:
    overlay_dir(repo_root, prd_id)
    paths = [prd_path, *companion_paths, *[
        repo_root / ".taskmaster/tasks" / name
        for name in ("tasks.json", "tasks_back.json", "tasks_gameplay.json")
    ]]
    sources = {
        normalize_relpath(path.resolve(), root=repo_root): digest(path.read_bytes())
        for path in paths
    }
    identity = {"prd_id": prd_id, "page_mode": page_mode, "source_paths": sorted(sources)}
    selection_key = digest(json.dumps(identity, sort_keys=True).encode("utf-8"))
    return {"prd_id": prd_id, "page_mode": page_mode, "sources": sources, "selection_key": selection_key}


def verify_inputs(root: Path, context: dict[str, Any]) -> None:
    for name, expected in context["sources"].items():
        path = Path(name)
        path = path if path.is_absolute() else root / path
        if not path.is_file() or digest(path.read_bytes()) != expected:
            raise ValueError(f"Candidate input drifted: {name}")


def _index_path(root: Path, context: dict[str, Any]) -> Path:
    return root / "logs/ci/overlay-candidates" / (context["selection_key"] + ".json")


def invalidate_default_candidate(root: Path, context: dict[str, Any], pages: list[str]) -> None:
    path = _index_path(root, context)
    if not path.exists():
        return
    index = read_object(path)
    for name in pages:
        index.get("pages", {}).pop(name, None)
    write_json(path, index)


def save_candidate(
    *, repo_root: Path, out_dir: Path, context: dict[str, Any],
    base_files: dict[str, bytes | None], generated_dir: Path,
) -> dict[str, str]:
    verify_inputs(repo_root, context)
    if not base_files:
        raise ValueError("No candidate pages to save")
    target = overlay_dir(repo_root, context["prd_id"])
    files = {}
    for name, original in base_files.items():
        page_name(name)
        current = (target / name).read_bytes() if (target / name).exists() else None
        if current != original:
            raise ValueError(f"Overlay source changed during simulate: {name}")
        files[name] = {
            "base_sha256": digest(original) if original is not None else None,
            "generated_sha256": digest((generated_dir / name).read_bytes()),
        }
    manifest = artifact_path(repo_root, str(out_dir / "candidate.json"))
    write_json(manifest, {"schema_version": 1, "status": "ready", "context": context, "files": files})
    pointer = {
        "candidate_manifest_path": normalize_relpath(manifest, root=repo_root),
        "candidate_manifest_sha256": digest(manifest.read_bytes()),
    }
    write_json(out_dir / "candidate-pointer.json", pointer)
    index_path = _index_path(repo_root, context)
    index = read_object(index_path) if index_path.exists() else {"pages": {}}
    for name in files:
        index["pages"][name] = pointer
    write_json(index_path, index)
    return pointer


def write_candidate_bundle(*, repo_root: Path, out_dir: Path, results: list[dict[str, Any]]) -> None:
    pages = {
        item["page"]: {key: item[key] for key in ("candidate_manifest_path", "candidate_manifest_sha256")}
        for item in results if item.get("candidate_manifest_path") and item.get("candidate_manifest_sha256")
    }
    write_json(artifact_path(repo_root, str(out_dir / "candidate-bundle.json")), {"schema_version": 1, "pages": pages})


def _candidate_manifest(repo_root: Path, context: dict[str, Any], pointer: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    manifest = artifact_path(repo_root, str(pointer.get("candidate_manifest_path", "")))
    manifest_bytes = manifest.read_bytes() if manifest.is_file() else b""
    if not manifest_bytes or digest(manifest_bytes) != pointer.get("candidate_manifest_sha256"):
        raise ValueError("Candidate manifest changed or missing")
    payload = json.loads(manifest_bytes)
    if not isinstance(payload, dict) or payload.get("schema_version") != 1 or payload.get("status") != "ready":
        raise ValueError("Candidate manifest is not ready")
    if payload.get("context") != context:
        raise ValueError("Candidate inputs changed since simulate")
    if not isinstance(payload.get("files"), dict):
        raise ValueError("Invalid candidate manifest files")
    return manifest, payload


def _candidate_pointers(repo_root: Path, context: dict[str, Any], candidate_from: str) -> dict[str, Any]:
    if candidate_from:
        source = artifact_path(repo_root, candidate_from)
        if not source.exists():
            raise ValueError("Selected candidate run is missing")
        bundle = source / "candidate-bundle.json" if source.is_dir() else source
        if bundle.name == "candidate-bundle.json" and bundle.exists():
            bundle_payload = read_object(bundle)
            if bundle_payload.get("schema_version") != 1:
                raise ValueError("Invalid candidate bundle version")
            pointers = bundle_payload.get("pages", {})
        else:
            directory = source if source.is_dir() else source.parent
            pointer = read_object(directory / "candidate-pointer.json")
            if artifact_path(repo_root, pointer.get("candidate_manifest_path", "")) != directory / "candidate.json":
                raise ValueError("Candidate manifest pointer does not match the selected run")
            _, payload = _candidate_manifest(repo_root, context, pointer)
            pointers = {name: pointer for name in payload["files"]}
    else:
        pointers = read_object(_index_path(repo_root, context)).get("pages", {})
    if not isinstance(pointers, dict):
        raise ValueError("Invalid candidate page pointers")
    return pointers


def select_candidate_pages(
    *, repo_root: Path, context: dict[str, Any], pages: list[str] | None,
    candidate_from: str = "", page_family: str = "all",
) -> list[str]:
    verify_inputs(repo_root, context)
    pointers = _candidate_pointers(repo_root, context, candidate_from)
    if pages is not None:
        selected = list(dict.fromkeys(page_name(name) for name in pages))
        for name in selected:
            if name not in pointers:
                raise ValueError(f"Candidate missing for page: {name}")
    else:
        profile = [{"filename": page_name(name), "page_kind": classify_page_kind(name)} for name in pointers]
        selected = [str(page["filename"]) for page in select_pages_by_family(profile, page_family)]
    if not selected:
        raise ValueError("No selected candidate pages")
    return selected


def resolve_candidate_pages(
    *, repo_root: Path, context: dict[str, Any], pages: list[str], candidate_from: str = "",
) -> dict[str, dict[str, Any]]:
    verify_inputs(repo_root, context)
    pointers = _candidate_pointers(repo_root, context, candidate_from)
    resolved = {}
    target = overlay_dir(repo_root, context["prd_id"])
    for name in pages:
        page_name(name)
        pointer = pointers.get(name)
        if not isinstance(pointer, dict):
            raise ValueError(f"Candidate missing for page: {name}")
        manifest, payload = _candidate_manifest(repo_root, context, pointer)
        record = payload["files"].get(name)
        if not isinstance(record, dict):
            raise ValueError(f"Candidate missing for page: {name}")
        generated = manifest.parent / "generated" / context["prd_id"] / "08" / name
        if not generated.is_file() or not generated.resolve().is_relative_to(manifest.parent.resolve()):
            raise ValueError(f"Candidate output missing or outside its run: {name}")
        content = generated.read_bytes()
        if digest(content) != record.get("generated_sha256"):
            raise ValueError(f"Candidate content changed: {name}")
        original = (target / name).read_bytes() if (target / name).exists() else None
        if original != content and (digest(original) if original is not None else None) != record.get("base_sha256"):
            raise ValueError(f"Overlay source changed since simulate: {name}")
        resolved[name] = {"content": content, "original": original, **pointer}
    return resolved
