#!/usr/bin/env python3
"""Validate repository-neutral source-to-target migration reconciliation manifests."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DIR = Path("docs/migration/reconciliation")
SCHEMA_VERSION = "repo.cross-repo-migration-reconciliation.v1"
SUMMARY_SCHEMA_VERSION = "repo.cross-repo-migration-reconciliation-check.v1"
CLASSIFICATIONS = {
    "copy_exact",
    "adapt_target_native",
    "already_present",
    "derived_regenerate",
    "business_only_drop",
    "protocol_name_retain",
}
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise ValueError(f"duplicate JSON key: {key}")
        out[key] = value
    return out


def _read_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    if not isinstance(data, dict):
        raise ValueError("manifest root must be an object")
    return data


def _safe_repo_path(root: Path, value: str) -> tuple[Path | None, str | None]:
    text = str(value or "").replace("\\", "/").strip()
    pure = PurePosixPath(text)
    if not text or pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        return None, f"unsafe repository path: {value!r}"
    return root.joinpath(*pure.parts), None


def _git_blob_sha(path: Path, repo_root: Path | None = None) -> str:
    if repo_root is not None:
        try:
            rel = path.resolve().relative_to(repo_root.resolve()).as_posix()
            proc = subprocess.run(
                ["git", "-C", str(repo_root), "hash-object", f"--path={rel}", rel],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            value = (proc.stdout or "").strip()
            if proc.returncode == 0 and HEX40_RE.fullmatch(value):
                return value
        except (OSError, ValueError):
            pass
    data = path.read_bytes()
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def _changed_files_sha256(values: list[str]) -> str:
    payload = json.dumps(sorted(values), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require_existing_paths(root: Path, values: Any, field: str, source_path: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(values, list):
        return [f"{source_path}: {field} must be an array"]
    for raw in values:
        if not isinstance(raw, str):
            errors.append(f"{source_path}: {field} entries must be strings")
            continue
        candidate, err = _safe_repo_path(root, raw)
        if err:
            errors.append(f"{source_path}: {field}: {err}")
        elif candidate is None or not candidate.exists():
            errors.append(f"{source_path}: {field} path does not exist: {raw}")
    return errors


def validate_manifest(doc: dict[str, Any], repo_root: Path) -> list[str]:
    errors: list[str] = []
    if doc.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must equal {SCHEMA_VERSION}")

    source = doc.get("source")
    target = doc.get("target")
    entries = doc.get("entries")
    if not isinstance(source, dict):
        errors.append("source must be an object")
        source = {}
    if not isinstance(target, dict):
        errors.append("target must be an object")
        target = {}
    if not isinstance(entries, list):
        errors.append("entries must be an array")
        entries = []

    if not isinstance(source.get("repo"), str) or "/" not in str(source.get("repo")):
        errors.append("source.repo must be owner/name")
    if not isinstance(source.get("pr"), int) or int(source.get("pr") or 0) <= 0:
        errors.append("source.pr must be a positive integer")
    if not HEX40_RE.fullmatch(str(source.get("merge_commit") or "")):
        errors.append("source.merge_commit must be a full 40-character lowercase git hash")
    if not isinstance(target.get("repo"), str) or "/" not in str(target.get("repo")):
        errors.append("target.repo must be owner/name")

    changed_files = source.get("changed_files")
    if not isinstance(changed_files, list) or not changed_files or not all(isinstance(item, str) and item for item in changed_files):
        errors.append("source.changed_files must be a non-empty string array")
        changed_files = []
    if len(changed_files) != len(set(changed_files)):
        errors.append("source.changed_files contains duplicates")
    declared_count = source.get("changed_file_count")
    if declared_count != len(changed_files):
        errors.append(f"source.changed_file_count={declared_count!r} does not match changed_files={len(changed_files)}")
    expected_inventory_sha = _changed_files_sha256(changed_files)
    if str(source.get("changed_files_sha256") or "").lower() != expected_inventory_sha:
        errors.append("source.changed_files_sha256 does not match canonical changed_files inventory")

    seen: set[str] = set()
    for index, raw_entry in enumerate(entries):
        label = f"entries[{index}]"
        if not isinstance(raw_entry, dict):
            errors.append(f"{label} must be an object")
            continue
        source_path = raw_entry.get("source_path")
        if not isinstance(source_path, str) or not source_path:
            errors.append(f"{label}.source_path must be a non-empty string")
            continue
        if source_path in seen:
            errors.append(f"duplicate entry for source path: {source_path}")
        seen.add(source_path)

        classification = raw_entry.get("classification")
        if classification not in CLASSIFICATIONS:
            errors.append(f"{source_path}: unsupported classification {classification!r}")
            continue
        if not str(raw_entry.get("rationale") or "").strip():
            errors.append(f"{source_path}: rationale must not be blank")

        target_paths = raw_entry.get("target_paths", [])
        validation_paths = raw_entry.get("validation_paths", [])
        if classification == "copy_exact":
            if not isinstance(target_paths, list) or len(target_paths) != 1:
                errors.append(f"{source_path}: copy_exact requires exactly one target path")
                continue
            errors.extend(_require_existing_paths(repo_root, target_paths, "target_paths", source_path))
            source_blob_sha = str(raw_entry.get("source_blob_sha") or "")
            if not HEX40_RE.fullmatch(source_blob_sha):
                errors.append(f"{source_path}: copy_exact requires source_blob_sha")
            else:
                candidate, err = _safe_repo_path(repo_root, target_paths[0])
                if err:
                    errors.append(f"{source_path}: {err}")
                elif candidate is not None and candidate.is_file():
                    target_blob_sha = _git_blob_sha(candidate, repo_root)
                    if target_blob_sha != source_blob_sha:
                        errors.append(f"{source_path}: copy_exact drift target={target_blob_sha} source={source_blob_sha}")
        elif classification in {"adapt_target_native", "already_present", "protocol_name_retain"}:
            if not isinstance(target_paths, list) or not target_paths:
                errors.append(f"{source_path}: {classification} requires target_paths")
            else:
                errors.extend(_require_existing_paths(repo_root, target_paths, "target_paths", source_path))
            if not isinstance(validation_paths, list) or not validation_paths:
                errors.append(f"{source_path}: {classification} requires validation_paths")
            else:
                errors.extend(_require_existing_paths(repo_root, validation_paths, "validation_paths", source_path))
            if classification == "protocol_name_retain" and not raw_entry.get("retained_identifiers"):
                errors.append(f"{source_path}: protocol_name_retain requires retained_identifiers")
        elif classification == "derived_regenerate":
            if target_paths:
                errors.extend(_require_existing_paths(repo_root, target_paths, "target_paths", source_path))
            if not str(raw_entry.get("regeneration_command") or "").strip():
                errors.append(f"{source_path}: derived_regenerate requires regeneration_command")
        elif classification == "business_only_drop" and target_paths:
            errors.append(f"{source_path}: business_only_drop must not declare target_paths")

    changed_set = set(changed_files)
    missing = sorted(changed_set - seen)
    extra = sorted(seen - changed_set)
    if missing:
        errors.append("unclassified source files: " + ", ".join(missing))
    if extra:
        errors.append("entries not present in source.changed_files: " + ", ".join(extra))
    if len(entries) != len(changed_files):
        errors.append(f"entry count {len(entries)} does not match changed file count {len(changed_files)}")
    return errors


def _github_json(url: str, token: str) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "cross-repo-migration-reconciliation",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise ValueError(f"GitHub source verification failed: {exc}") from exc


def fetch_github_source_inventory(source: dict[str, Any], token: str = "") -> dict[str, Any]:
    repo = str(source.get("repo") or "")
    pr = int(source.get("pr") or 0)
    if "/" not in repo or pr <= 0:
        raise ValueError("source.repo/source.pr are invalid")
    base = f"https://api.github.com/repos/{repo}"
    pr_doc = _github_json(f"{base}/pulls/{pr}", token)
    if not isinstance(pr_doc, dict) or not pr_doc.get("merged_at"):
        raise ValueError("source PR is not merged")
    changed: list[str] = []
    page = 1
    while True:
        page_doc = _github_json(f"{base}/pulls/{pr}/files?per_page=100&page={page}", token)
        if not isinstance(page_doc, list):
            raise ValueError("source PR files response is invalid")
        changed.extend(str(item.get("filename") or "") for item in page_doc if isinstance(item, dict))
        if len(page_doc) < 100:
            break
        page += 1
        if page > 100:
            raise ValueError("source PR files pagination exceeded safety limit")
    if any(not item for item in changed):
        raise ValueError("source PR files response contains blank filename")
    return {
        "merge_commit": str(pr_doc.get("merge_commit_sha") or ""),
        "changed_files": changed,
    }


def verify_source_github(doc: dict[str, Any], token: str = "") -> list[str]:
    source = doc.get("source")
    if not isinstance(source, dict):
        return ["source must be an object before GitHub verification"]
    try:
        remote = fetch_github_source_inventory(source, token)
    except ValueError as exc:
        return [str(exc)]
    errors: list[str] = []
    if remote["merge_commit"] != source.get("merge_commit"):
        errors.append(f"source merge commit mismatch remote={remote['merge_commit']} manifest={source.get('merge_commit')}")
    remote_files = remote["changed_files"]
    manifest_files = source.get("changed_files") if isinstance(source.get("changed_files"), list) else []
    if set(remote_files) != set(manifest_files) or len(remote_files) != len(manifest_files):
        missing = sorted(set(remote_files) - set(manifest_files))
        extra = sorted(set(manifest_files) - set(remote_files))
        errors.append(f"source changed-file inventory mismatch missing={missing} extra={extra}")
    return errors


def validate_file(path: Path, repo_root: Path, *, verify_github: bool = False, token: str = "") -> list[str]:
    try:
        doc = _read_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        return [f"{path}: invalid JSON: {exc}"]
    errors = validate_manifest(doc, repo_root)
    if verify_github and not errors:
        errors.extend(verify_source_github(doc, token))
    return [f"{path}: {item}" for item in errors]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(REPO_ROOT))
    parser.add_argument("--dir", default=str(DEFAULT_DIR))
    parser.add_argument("--manifest", action="append", default=[])
    parser.add_argument("--require-manifests", action="store_true")
    parser.add_argument("--verify-source-github", action="store_true")
    parser.add_argument("--github-token-env", default="GITHUB_TOKEN")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    manifests = [root / item for item in args.manifest] if args.manifest else (
        sorted((root / args.dir).glob("*.json")) if (root / args.dir).exists() else []
    )
    errors: list[str] = []
    if not manifests and args.require_manifests:
        errors.append(f"no reconciliation manifests found under {args.dir}")
    token = os.getenv(args.github_token_env, "") if args.verify_source_github else ""
    for path in manifests:
        errors.extend(validate_file(path, root, verify_github=args.verify_source_github, token=token))

    status = "failed" if errors else ("skipped" if not manifests else "passed")
    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "status": status,
        "github_source_verified": bool(args.verify_source_github and manifests and not errors),
        "manifests": [str(path.relative_to(root)).replace("\\", "/") for path in manifests if path.is_relative_to(root)],
        "errors": errors,
    }
    out = Path(args.out) if args.out else (
        root / "logs" / "ci" / dt.date.today().isoformat() / "cross-repo-migration-reconciliation" / "summary.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shown_out = out.relative_to(root).as_posix() if out.is_relative_to(root) else str(out)
    print(f"CROSS_REPO_MIGRATION_RECONCILIATION status={status} manifests={len(manifests)} errors={len(errors)} out={shown_out}")
    for item in errors:
        print(f"ERROR: {item}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
