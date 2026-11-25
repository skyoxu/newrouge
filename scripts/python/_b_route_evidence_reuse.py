"""Story 4.4 identity-verified build/prewarm reuse, shared test evidence deduplication,
and per-test mutable state isolation.

Reuses existing runtime artifacts (`logs/ci/mvg-acceptance/<run-id>/summary.json`,
`coverage-receipt.json`, `input-manifest.json`, and raw `.trx`/`results.xml` reports)
without creating a second Task/MVG completion cache or second proof format.

Strictly separates:
- Build/prewarm reuse vs test result reuse (build reuse NEVER implies test pass)
- Runtime evidence reuse vs Story 2.9 planning capability adoption
- Read-only shared build/prewarm vs per-test isolated mutable user/temp state
- Machine automated reuse vs human manual verification obligations
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shutil
import stat
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import _b_route_codec as codec
import _b_route_inventory as inventory
from _mvg_execution import read_test_evidence
from _mvg_manifest import safe_path
from _project_health_runtime_snapshot import (
    _is_regenerable_gdunit_import,
    _is_workspace_ignored,
    snapshot_digest as compute_snapshot_digest,
)

EXECUTION_RECEIPT_SCHEMA = "newrouge.b-route-execution-receipt.v1"
MVG_SUMMARY_SCHEMA = "newrouge.mvg-acceptance.v1"

_PLANNING_ADOPTION_SCHEMAS = frozenset({
    "newrouge.mvg-capability-adoption.v1",
    "newrouge.b-route-commit.v1",
    "newrouge.b-route-plan.v1",
    "newrouge.b-route-catalog.v1",
    "newrouge.b-route-candidate.v1",
    "newrouge.b-route-review.v1",
    "newrouge.b-route-binding.v1",
    "newrouge.b-route-origins.v1",
    "newrouge.b-route-policy.v1",
    "newrouge.capabilities.v1",
})

_VOLATILE_RECEIPT_FIELDS = frozenset({"receipt_id", "generated_at", "finished_at"})
_VOLATILE_EVENT_FIELDS = frozenset({"event_id", "recorded_at", "timestamp"})

_DOTNET_SOURCE_EXTS = frozenset({".cs", ".csproj", ".sln"})
_DOTNET_CONFIG_NAMES = frozenset({"global.json", "nuget.config"})
_GODOT_SOURCE_EXTS = frozenset({".cs", ".gd", ".tscn", ".tres"})
_GODOT_PROJECT_FILES = frozenset({"project.godot", "Tests.Godot/project.godot"})

_RES_REF_RE = re.compile(
    r"""(?:preload|load)\s*\(\s*["']res://([^"']+\.(?:gd|tscn|tres|cs))["']\s*\)"""
)
_EXT_RES_RE = re.compile(
    r"""\[ext_resource\b[^\]]*\bpath="res://([^"]+)\""""
)
_GD_EXTENDS_RE = re.compile(
    r"""^\s*extends\s+["']res://([^"']+\.gd)["']""",
    re.MULTILINE,
)

_ALLOWED_DOTNET_ARTIFACT_PREFIXES = (
    "Game.Core/bin/",
    "Game.Core/obj/",
    "Game.Core.Tests/bin/",
    "Game.Core.Tests/obj/",
)
_ALLOWED_GODOT_ARTIFACT_PREFIXES = (
    "Tests.Godot/.godot/",
    ".godot/",
)
_EPHEMERAL_TEST_DIRS = (
    "logs",
    "reports",
    "Tests.Godot/reports",
)

REUSE_INVARIANT_FLAGS: dict[str, bool] = {
    "build_reuse_implies_test_pass": False,
    "manual_satisfied_by_machine_reuse": False,
    "planning_adoption_interchangeable": False,
    "speedup_or_cost_gate_enforced": False,
    "reserved_budget_claimed_as_savings": False,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _check_ancestors_no_reparse(path: Path, stop_at: Path | None = None) -> None:
    cur = path.absolute()
    boundary = stop_at.resolve() if stop_at is not None else None
    chain: list[Path] = []
    while True:
        chain.append(cur)
        if boundary is not None and cur == boundary:
            break
        if cur.parent == cur:
            break
        cur = cur.parent
    for node in reversed(chain):
        if os.path.lexists(node):
            inventory.no_reparse(node)


def _normalize_repo_rel(root: Path, raw_path: str | Path, *, allow_logs: bool = True) -> tuple[Path, str]:
    text = str(raw_path or "").strip()
    if not text:
        raise ValueError("Empty path is not allowed")
    norm_text = text.replace("\\", "/")
    root_res = root.resolve()
    cand_raw = Path(text)
    if cand_raw.is_absolute():
        _check_ancestors_no_reparse(cand_raw)
        resolved = cand_raw.resolve()
        try:
            rel_posix = resolved.relative_to(root_res).as_posix()
        except ValueError as exc:
            raise ValueError(f"Path escapes repository root: {text}") from exc
    else:
        rel_posix = norm_text
        while rel_posix.startswith("./"):
            rel_posix = rel_posix.removeprefix("./")
    safe = inventory.safe_input(root_res, rel_posix, allow_logs=allow_logs)
    _check_ancestors_no_reparse(safe, stop_at=root_res)
    if os.path.lexists(safe):
        inventory.no_reparse(safe)
    resolved_rel = safe.resolve().relative_to(root_res).as_posix()
    return safe, resolved_rel


def _is_benign_engine_metadata(rel_posix: str) -> bool:
    """Return True for Godot 4.5 / GdUnit4 regenerable cache metadata files."""
    if _is_regenerable_gdunit_import(rel_posix):
        return True
    low = rel_posix.lower()
    return low.endswith(".gd.uid") or low.endswith(".cs.uid")


def _is_allowed_tests_godot_junction(root_res: Path, child_rel: str, child_path: Path) -> bool:
    """Allow ONLY Tests.Godot/Game.Godot when it is a directory junction to <root>/Game.Godot."""
    if child_rel != "Tests.Godot/Game.Godot":
        return False
    try:
        info = child_path.lstat()
    except OSError:
        return False
    is_reparse = stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)
    if not is_reparse or not child_path.is_dir():
        return False
    expected_target = root_res / "Game.Godot"
    if not expected_target.is_dir():
        return False
    try:
        inventory.no_reparse(expected_target)
        return child_path.resolve() == expected_target.resolve()
    except (OSError, ValueError):
        return False


def _walk_safe_files(root: Path, *, ignore_workspace_dirs: bool = True) -> list[tuple[str, Path]]:
    """Walk files under root without crossing reparse points; returns sorted (posix_rel, Path)."""
    root_res = root.resolve()
    inventory.no_reparse(root_res)
    results: list[tuple[str, Path]] = []
    if not root_res.is_dir():
        return results
    for dirpath, dirnames, filenames in os.walk(root_res, followlinks=False):
        cur_dir = Path(dirpath)
        inventory.no_reparse(cur_dir)
        rel_dir = cur_dir.relative_to(root_res).as_posix()
        if rel_dir == ".":
            rel_dir = ""
        kept_dirs: list[str] = []
        for dname in sorted(dirnames):
            child_rel = f"{rel_dir}/{dname}" if rel_dir else dname
            child_path = cur_dir / dname
            if _is_allowed_tests_godot_junction(root_res, child_rel, child_path):
                # Allowed internal junction Tests.Godot/Game.Godot -> <execution_root>/Game.Godot.
                # Skip recursing here because Game.Godot/ is already walked directly.
                continue
            if child_path.is_symlink():
                raise ValueError(f"Symlink/reparse directory not allowed in snapshot: {child_rel}")
            inventory.no_reparse(child_path)
            if ignore_workspace_dirs and _is_workspace_ignored(child_rel + "/placeholder"):
                continue
            kept_dirs.append(dname)
        dirnames[:] = kept_dirs
        for fname in sorted(filenames):
            child_rel = f"{rel_dir}/{fname}" if rel_dir else fname
            child_path = cur_dir / fname
            if child_path.is_symlink():
                raise ValueError(f"Symlink/reparse file not allowed in snapshot: {child_rel}")
            inventory.no_reparse(child_path)
            if ignore_workspace_dirs and _is_workspace_ignored(child_rel):
                continue
            if _is_benign_engine_metadata(child_rel):
                continue
            results.append((child_rel, child_path))
    results.sort(key=lambda item: item[0])
    return results


def _collect_artifact_files(base_dir: Path, root: Path, *, extensions: frozenset[str] | None = None,
                            marker_names: frozenset[str] | None = None) -> dict[str, str]:
    """Hash verified build/prewarm artifact files under base_dir."""
    out: dict[str, str] = {}
    if not base_dir.is_dir():
        return out
    root_res = root.resolve()
    _check_ancestors_no_reparse(base_dir, stop_at=root_res)
    for dirpath, dirnames, filenames in os.walk(base_dir, followlinks=False):
        cur = Path(dirpath)
        inventory.no_reparse(cur)
        dirnames[:] = sorted(d for d in dirnames if not (cur / d).is_symlink())
        for fname in sorted(filenames):
            fp = cur / fname
            if fp.is_symlink():
                continue
            inventory.no_reparse(fp)
            if not fp.is_file():
                continue
            low_name = fname.lower()
            suffix = fp.suffix.lower()
            if extensions is not None:
                if suffix not in extensions and (marker_names is None or low_name not in marker_names):
                    continue
            rel = fp.resolve().relative_to(root_res).as_posix()
            out[rel] = _sha256_file(fp)
    return dict(sorted(out.items()))


def is_planning_adoption_payload(doc: Any) -> bool:
    """Return True if a JSON payload is a Story 2.9 planning adoption or formal planning record."""
    if not isinstance(doc, dict):
        return False
    schema = str(doc.get("schema_version") or "").strip()
    if schema in _PLANNING_ADOPTION_SCHEMAS:
        return True
    if "adoption" in schema.lower():
        return True
    if ("adopted" in doc or "operation_id" in doc) and "steps" not in doc and "executed_tests" not in doc:
        return True
    return False


def verify_receipt_seal(receipt_doc: Any) -> bool:
    """Re-verify Story 4.3/4.4 coverage-receipt.json canonical receipt_id seal."""
    if not isinstance(receipt_doc, dict):
        return False
    if receipt_doc.get("schema_version") != EXECUTION_RECEIPT_SCHEMA:
        return False
    expected = receipt_doc.get("receipt_id")
    if not isinstance(expected, str) or not expected:
        return False
    body = {k: v for k, v in receipt_doc.items() if k not in _VOLATILE_RECEIPT_FIELDS}
    return codec.canonical_digest(body) == expected


def _normalize_evidence_level(kind: str, raw_level: str | None) -> str:
    lvl = str(raw_level or "").strip().lower()
    if kind == "dotnet" or lvl in {"domain-integration", "domain-xunit"}:
        return "domain-xunit"
    if lvl in {"engine-input", "scene-method", "godot-gdunit", "static-wiring", "manual", "other-verification"}:
        return lvl
    if kind == "gdunit":
        return "godot-gdunit"
    if kind == "other_verification":
        return "other-verification"
    return lvl or kind


# ---------------------------------------------------------------------------
# AC-1: Separate Build / Prewarm Artifact Identity & Reuse
# ---------------------------------------------------------------------------

def compute_build_artifact_identity(
    execution_root: Path,
    *,
    kind: str,
    toolchain_env: dict[str, Any] | None,
    configuration: str = "Debug",
) -> dict[str, Any]:
    """Compute canonical identity for a dotnet_build or godot_prewarm artifact."""
    if kind not in {"dotnet_build", "godot_prewarm"}:
        raise ValueError(f"Unsupported build artifact kind: {kind}")
    exec_root = Path(execution_root).resolve()
    inventory.no_reparse(exec_root)
    env = dict(toolchain_env or {})
    source_files: dict[str, str] = {}

    if kind == "dotnet_build":
        for rel, fp in _walk_safe_files(exec_root, ignore_workspace_dirs=True):
            name_low = fp.name.lower()
            suffix_low = fp.suffix.lower()
            if (
                suffix_low in _DOTNET_SOURCE_EXTS
                or name_low in _DOTNET_CONFIG_NAMES
                or name_low.startswith("directory.build.")
            ):
                source_files[rel] = _sha256_file(fp)
        source_digest = codec.canonical_digest(source_files)
        toolchain = {
            "os_platform": str(env.get("os_platform") or ""),
            "dotnet_version": str(env.get("dotnet_version") or "unavailable"),
            "dotnet_genuine": bool(env.get("dotnet_genuine", False)),
            "evidence_authenticity": str(env.get("evidence_authenticity") or "protocol_fixture"),
            "protocol_fixture_only": bool(env.get("protocol_fixture_only", True)),
        }
        artifact_files: dict[str, str] = {}
        for art_dir in (
            exec_root / "Game.Core" / "bin" / configuration,
            exec_root / "Game.Core" / "obj",
            exec_root / "Game.Core.Tests" / "bin" / configuration,
            exec_root / "Game.Core.Tests" / "obj",
        ):
            artifact_files.update(_collect_artifact_files(art_dir, exec_root))
        artifact_files = dict(sorted(artifact_files.items()))
        has_compiled_output = any(
            (rel.startswith(f"Game.Core.Tests/bin/{configuration}/") or rel.startswith(f"Game.Core/bin/{configuration}/"))
            and (
                rel.lower().endswith(".dll")
                or PurePosixPath(rel).name.lower() in {".build-ready.json", "build-marker.json"}
            )
            for rel in artifact_files
        )
    else:
        for rel, fp in _walk_safe_files(exec_root, ignore_workspace_dirs=True):
            suffix_low = fp.suffix.lower()
            if (
                suffix_low in _GODOT_SOURCE_EXTS
                or rel in _GODOT_PROJECT_FILES
                or (rel.startswith("Tests.Godot/addons/gdUnit4/") and not _is_benign_engine_metadata(rel))
            ):
                source_files[rel] = _sha256_file(fp)
        source_digest = codec.canonical_digest(source_files)
        toolchain = {
            "os_platform": str(env.get("os_platform") or ""),
            "godot_version": str(env.get("godot_version") or "unavailable"),
            "godot_genuine": bool(env.get("godot_genuine", False)),
            "godot_bin_kind": str(env.get("godot_bin_kind") or "unavailable"),
            "evidence_authenticity": str(env.get("evidence_authenticity") or "protocol_fixture"),
            "protocol_fixture_only": bool(env.get("protocol_fixture_only", True)),
        }
        artifact_files = _collect_artifact_files(exec_root / "Tests.Godot" / ".godot", exec_root)
        if not artifact_files:
            artifact_files = _collect_artifact_files(exec_root / ".godot", exec_root)
        has_compiled_output = bool(artifact_files)

    artifact_present = bool(has_compiled_output)
    artifact_digest = codec.canonical_digest(artifact_files) if artifact_files else None
    identity_payload = {
        "kind": kind,
        "configuration": str(configuration),
        "source_digest": source_digest,
        "toolchain": toolchain,
    }
    build_artifact_id = codec.canonical_digest(identity_payload)
    return {
        "kind": kind,
        "configuration": str(configuration),
        "build_artifact_id": build_artifact_id,
        "source_digest": source_digest,
        "source_file_count": len(source_files),
        "toolchain": toolchain,
        "artifact_present": artifact_present,
        "artifact_digest": artifact_digest,
        "artifact_files": artifact_files,
        "identity_payload": identity_payload,
    }


def evaluate_build_reuse(
    execution_root: Path,
    *,
    kind: str,
    toolchain_env: dict[str, Any] | None,
    prior_build_record: dict[str, Any] | None = None,
    configuration: str = "Debug",
) -> dict[str, Any]:
    """Decide whether a prior dotnet_build or godot_prewarm artifact may be reused.

    Build/prewarm reuse NEVER implies test pass and NEVER claims reserved budget as savings.
    """
    current = compute_build_artifact_identity(
        execution_root,
        kind=kind,
        toolchain_env=toolchain_env,
        configuration=configuration,
    )

    def _reject(reason_code: str, reason: str) -> dict[str, Any]:
        return {
            "reused": False,
            "kind": kind,
            "artifact_id": current["build_artifact_id"],
            "source_digest": current["source_digest"],
            "artifact_present": current["artifact_present"],
            "artifact_digest": current["artifact_digest"],
            "source_run_id": prior_build_record.get("source_run_id") if isinstance(prior_build_record, dict) else None,
            "source_step_id": prior_build_record.get("source_step_id") if isinstance(prior_build_record, dict) else None,
            "original_created_at": (
                prior_build_record.get("original_created_at") if isinstance(prior_build_record, dict) else None
            ),
            "match_reason": None,
            "reason_code": reason_code,
            "reason": reason,
            "build_reuse_implies_test_pass": False,
            "reserved_budget_claimed_as_savings": False,
        }

    if not isinstance(prior_build_record, dict):
        return _reject("no_prior_build_record", f"No prior {kind} record available in current snapshot")
    if prior_build_record.get("kind") != kind:
        return _reject("build_kind_mismatch", f"Prior build kind {prior_build_record.get('kind')} != {kind}")
    if prior_build_record.get("status") not in {"ready", "built", "passed"}:
        return _reject("prior_build_not_ready", f"Prior {kind} status is not ready ({prior_build_record.get('status')})")
    if prior_build_record.get("configuration", "Debug") != str(configuration):
        return _reject("build_configuration_mismatch", "Build configuration differs from prior record")
    if prior_build_record.get("source_digest") != current["source_digest"]:
        return _reject("build_source_digest_mismatch", f"Source files affecting {kind} changed since prior build")
    if prior_build_record.get("build_artifact_id") != current["build_artifact_id"]:
        return _reject("build_toolchain_or_env_mismatch", f"Toolchain or environment for {kind} differs from prior build")
    if not current["artifact_present"]:
        return _reject("build_artifact_missing", f"Verified {kind} output artifact is missing on disk")
    prior_art_digest = prior_build_record.get("artifact_digest")
    if prior_art_digest and current["artifact_digest"] != prior_art_digest:
        return _reject("build_artifact_digest_mismatch", f"On-disk {kind} artifact digest does not match prior record")

    match_reason = (
        "matching_dotnet_source_and_toolchain_identity"
        if kind == "dotnet_build"
        else "matching_godot_source_and_toolchain_identity"
    )
    return {
        "reused": True,
        "kind": kind,
        "artifact_id": current["build_artifact_id"],
        "source_digest": current["source_digest"],
        "artifact_present": True,
        "artifact_digest": current["artifact_digest"],
        "source_run_id": prior_build_record.get("source_run_id"),
        "source_step_id": prior_build_record.get("source_step_id"),
        "original_created_at": prior_build_record.get("original_created_at"),
        "match_reason": match_reason,
        "reason_code": "reused",
        "reason": f"Reused verified {kind} artifact from {prior_build_record.get('source_run_id')}",
        "build_reuse_implies_test_pass": False,
        "reserved_budget_claimed_as_savings": False,
    }


def load_prior_build_record(
    root: Path,
    prior_ref: str,
    *,
    kind: str,
    execution_root: Path,
    toolchain_env: dict[str, Any] | None,
    configuration: str = "Debug",
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Validate a --reuse-build-from prior run and hydrate read-only build outputs when identity matches."""
    rejections: list[dict[str, Any]] = []

    def _fail(code: str, msg: str) -> tuple[None, list[dict[str, Any]]]:
        rejections.append({"entity_id": f"build:{kind}", "candidate": str(prior_ref), "reason_code": code, "reason": msg})
        return None, rejections

    try:
        cand_path, _cand_rel = _normalize_repo_rel(root, prior_ref, allow_logs=True)
    except ValueError as exc:
        return _fail("unsafe_path", str(exc))

    if not cand_path.exists():
        return _fail("prior_build_not_found", f"Prior build source does not exist: {prior_ref}")

    prior_run_dir = cand_path
    if cand_path.is_file():
        try:
            doc = codec.strict_json_loads(cand_path.read_bytes())
        except (OSError, ValueError, codec.CodecError) as exc:
            return _fail("corrupt_prior_receipt", f"Unreadable prior JSON: {exc}")
        if is_planning_adoption_payload(doc):
            return _fail(
                "planning_adoption_not_runtime_evidence",
                "Planning capability adoption receipt cannot supply runtime build artifacts",
            )
        if not isinstance(doc, dict) or doc.get("schema_version") not in {EXECUTION_RECEIPT_SCHEMA, MVG_SUMMARY_SCHEMA}:
            return _fail("unknown_schema", "Unsupported schema for --reuse-build-from")
        prior_run_dir = cand_path.parent

    receipt_path = prior_run_dir / "coverage-receipt.json"
    if not receipt_path.is_file():
        return _fail("missing_prior_run_receipt", f"Missing coverage-receipt.json in {prior_ref}")
    try:
        inventory.no_reparse(receipt_path)
        prior_receipt = codec.strict_json_loads(receipt_path.read_bytes())
    except (OSError, ValueError, codec.CodecError) as exc:
        return _fail("corrupt_coverage_receipt", f"Invalid coverage-receipt.json: {exc}")
    if is_planning_adoption_payload(prior_receipt):
        return _fail("planning_adoption_not_runtime_evidence", "Planning adoption payload is not a runtime receipt")
    if not verify_receipt_seal(prior_receipt):
        return _fail("corrupt_coverage_receipt", "Prior coverage-receipt.json failed receipt_id seal verification")

    # Verify prior input-manifest.json, zero mid-run drift, and zero snapshot pollution before trusting build outputs!
    manifest_file = prior_run_dir / "input-manifest.json"
    if not manifest_file.is_file() or manifest_file.is_symlink():
        return _fail("corrupt_or_missing_input_manifest", "Prior build run missing input-manifest.json")
    try:
        inventory.no_reparse(manifest_file)
        prior_manifest = codec.strict_json_loads(manifest_file.read_bytes())
    except (OSError, ValueError, codec.CodecError) as exc:
        return _fail("corrupt_or_missing_input_manifest", f"Invalid prior input-manifest.json: {exc}")
    if (
        not isinstance(prior_manifest, dict)
        or not isinstance(prior_manifest.get("files"), dict)
        or not isinstance(prior_manifest.get("snapshot_digest"), str)
    ):
        return _fail("corrupt_or_missing_input_manifest", "Invalid prior input-manifest.json structure")
    if compute_snapshot_digest(prior_manifest["files"]) != prior_manifest["snapshot_digest"]:
        return _fail("corrupt_or_missing_input_manifest", "Prior input-manifest.json snapshot_digest mismatch")
    if str(prior_receipt.get("snapshot_digest") or "") != prior_manifest["snapshot_digest"]:
        return _fail("inconsistent_prior_snapshot_metadata", "Prior receipt snapshot_digest disagrees with input-manifest.json")
    if str(prior_receipt.get("source_revision") or "") != str(prior_manifest.get("source_revision") or ""):
        return _fail("inconsistent_prior_snapshot_metadata", "Prior receipt source_revision disagrees with input-manifest.json")

    pdrift = prior_receipt.get("drift") or {}
    if pdrift.get("drift_detected") or pdrift.get("post_run_valid") is False or pdrift.get("pre_run_valid") is False:
        return _fail("prior_run_drifted", "Prior build run experienced drift and cannot supply reusable build artifacts")
    piso = prior_receipt.get("state_isolation") or {}
    if piso.get("pollution_detected"):
        return _fail("prior_run_state_polluted", "Prior build run had snapshot pollution and cannot supply reusable build artifacts")

    prior_art = (prior_receipt.get("build_artifacts") or {}).get(kind)
    if not isinstance(prior_art, dict):
        return _fail("no_prior_build_record", f"Prior receipt has no recorded {kind} artifact")

    current_id = compute_build_artifact_identity(
        execution_root, kind=kind, toolchain_env=toolchain_env, configuration=configuration
    )
    if prior_art.get("source_digest") != current_id["source_digest"]:
        return _fail("build_source_digest_mismatch", f"Prior {kind} source_digest differs from current snapshot")
    if prior_art.get("build_artifact_id") != current_id["build_artifact_id"]:
        return _fail("build_toolchain_or_env_mismatch", f"Prior {kind} toolchain/configuration identity differs")
    if prior_art.get("status") not in {"ready", "built", "passed"}:
        return _fail("prior_build_not_ready", f"Prior {kind} status is not ready")

    prior_snap = prior_run_dir / "snapshot"
    if not prior_snap.is_dir():
        return _fail("build_artifact_missing", "Prior run snapshot directory is not available for build reuse")
    inventory.no_reparse(prior_snap)
    prior_files = prior_art.get("artifact_files") or {}
    if not isinstance(prior_files, dict) or not prior_files:
        return _fail("build_artifact_missing", f"Prior {kind} artifact_files list is empty")

    allowed_prefixes = _ALLOWED_DOTNET_ARTIFACT_PREFIXES if kind == "dotnet_build" else _ALLOWED_GODOT_ARTIFACT_PREFIXES

    # Verify every prior artifact file prefix & digest before hydrating read-only build outputs into execution_root.
    verified_copies: list[tuple[str, bytes]] = []
    for rel_posix, expected_sha in sorted(prior_files.items()):
        if not isinstance(rel_posix, str) or not isinstance(expected_sha, str):
            return _fail("corrupt_prior_build_artifact", "Invalid artifact_files entry in prior receipt")
        if not rel_posix.startswith(allowed_prefixes):
            return _fail("unsafe_path", f"Prior {kind} artifact path escapes build output directories: {rel_posix}")
        try:
            src = safe_path(prior_snap, rel_posix)
            _check_ancestors_no_reparse(src, stop_at=prior_snap)
        except ValueError as exc:
            return _fail("unsafe_path", str(exc))
        if not src.is_file() or src.is_symlink():
            return _fail("build_artifact_missing", f"Missing prior build artifact file: {rel_posix}")
        inventory.no_reparse(src)
        raw = src.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_sha:
            return _fail("build_artifact_digest_mismatch", f"Prior build artifact corrupted: {rel_posix}")
        verified_copies.append((rel_posix, raw))

    # Hydrate verified read-only build/prewarm outputs into execution_root (outside tracked source files).
    for rel_posix, raw in verified_copies:
        dest = safe_path(execution_root, rel_posix)
        dest.parent.mkdir(parents=True, exist_ok=True)
        _check_ancestors_no_reparse(dest, stop_at=execution_root)
        dest.write_bytes(raw)

    return prior_art, rejections


# ---------------------------------------------------------------------------
# AC-2 & AC-4: Test Evidence Identity, Multi-Flow Coverage & Cross-Run Reuse
# ---------------------------------------------------------------------------

def _collect_gd_transitive_files(execution_root: Path, start_rel: str) -> set[str]:
    """Collect a .gd test file and its transitive preload/load/ext_resource dependencies."""
    found: set[str] = set()
    queue: list[str] = [start_rel]
    while queue:
        rel = queue.pop(0)
        if not rel or rel in found:
            continue
        try:
            fp = safe_path(execution_root, rel)
        except ValueError:
            continue
        if not fp.is_file() or fp.is_symlink():
            continue
        inventory.no_reparse(fp)
        found.add(rel)
        low = rel.lower()
        if not (low.endswith(".gd") or low.endswith(".tscn") or low.endswith(".tres")):
            continue
        text = fp.read_text(encoding="utf-8", errors="replace")
        for pat in (_RES_REF_RE, _EXT_RES_RE, _GD_EXTENDS_RE):
            for match in pat.finditer(text):
                dep = match.group(1)
                if dep.startswith("Tests.Godot/") or dep.startswith("Game."):
                    if dep not in found:
                        queue.append(dep)
                elif (execution_root / "Tests.Godot" / dep).is_file():
                    cand = "Tests.Godot/" + dep
                    if cand not in found:
                        queue.append(cand)
                elif (execution_root / dep).is_file():
                    if dep not in found:
                        queue.append(dep)
    return found


def compute_test_evidence_identity(
    execution_root: Path,
    *,
    test_spec: dict[str, Any],
    snapshot_digest: str,
    source_revision: str,
    workspace_dirty: bool,
    toolchain_env: dict[str, Any] | None,
    verification_semantics: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compute canonical identity for a test execution bound to exact snapshot, inputs, semantics, and toolchain."""
    exec_root = Path(execution_root).resolve()
    inventory.no_reparse(exec_root)

    test_id = str(test_spec.get("id") or test_spec.get("test_id") or "")
    kind = str(test_spec.get("kind") or "")
    test_path = str(test_spec.get("path") or "").replace("\\", "/")
    while test_path.startswith("./"):
        test_path = test_path.removeprefix("./")
    selector = test_spec.get("selector")
    selector_str = str(selector) if selector is not None else ""
    min_tests = int(test_spec.get("min_tests") or 1)
    manifest_evidence_level = str(test_spec.get("manifest_evidence_level") or test_spec.get("evidence_level") or "")
    evidence_level = _normalize_evidence_level(kind, test_spec.get("evidence_level") or manifest_evidence_level)

    relevant_paths: set[str] = set()
    if test_path:
        relevant_paths.add(test_path)
    for extra in test_spec.get("relevant_paths") or []:
        if isinstance(extra, str) and extra.strip():
            clean = extra.strip().replace("\\", "/")
            while clean.startswith("./"):
                clean = clean.removeprefix("./")
            relevant_paths.add(clean)

    # Always bind test-relevant source/contract/rule/scene inputs (never logs/** or tasks.json status!).
    if kind == "dotnet":
        for rel, fp in _walk_safe_files(exec_root, ignore_workspace_dirs=True):
            low_name = fp.name.lower()
            low_ext = fp.suffix.lower()
            if (
                rel.startswith("Game.Core/")
                or rel.startswith("Game.Core.Tests/")
                or (rel.startswith("Tests/CI/") and low_ext == ".cs")
                or low_ext in {".csproj", ".sln"}
                or low_name in _DOTNET_CONFIG_NAMES
                or low_name.startswith("directory.build.")
            ):
                if low_ext in _DOTNET_SOURCE_EXTS or low_name in _DOTNET_CONFIG_NAMES or low_name.startswith("directory.build."):
                    relevant_paths.add(rel)
    elif kind == "gdunit":
        if test_path:
            relevant_paths.update(_collect_gd_transitive_files(exec_root, test_path))
        for rel, fp in _walk_safe_files(exec_root, ignore_workspace_dirs=True):
            low_ext = fp.suffix.lower()
            if (
                rel in _GODOT_PROJECT_FILES
                or (rel.startswith("Game.Core/") and low_ext in _DOTNET_SOURCE_EXTS)
                or (rel.startswith("Game.Godot/") and low_ext in _GODOT_SOURCE_EXTS)
                or (rel.startswith("Tests.Godot/") and low_ext in {".cs", ".csproj"})
                or (rel.startswith("Tests.Godot/addons/gdUnit4/") and not _is_benign_engine_metadata(rel))
            ):
                relevant_paths.add(rel)

    file_hashes: dict[str, str] = {}
    for rel in sorted(relevant_paths):
        try:
            fp = safe_path(exec_root, rel)
        except ValueError:
            continue
        if fp.is_file() and not fp.is_symlink():
            inventory.no_reparse(fp)
            file_hashes[rel] = _sha256_file(fp)
        else:
            file_hashes[rel] = "missing"

    relevant_input_digest = codec.canonical_digest(file_hashes)

    sem = dict(verification_semantics or {})
    normalized_semantics = {
        "challenge": str(sem.get("challenge") or test_spec.get("challenge") or ""),
        "challenge_input": bool(sem.get("challenge_input", False)),
        "input_authenticity_required": bool(sem.get("input_authenticity_required", evidence_level == "engine-input")),
        "input_authenticity_valid": bool(sem.get("input_authenticity_valid", True)),
        "evidence_authenticity": str(sem.get("evidence_authenticity") or "protocol_fixture"),
        "protocol_fixture_only": bool(sem.get("protocol_fixture_only", True)),
    }

    env = dict(toolchain_env or {})
    normalized_toolchain = {
        "os_platform": str(env.get("os_platform") or ""),
        "dotnet_version": str(env.get("dotnet_version") or "unavailable"),
        "dotnet_genuine": bool(env.get("dotnet_genuine", False)),
        "godot_version": str(env.get("godot_version") or "unavailable"),
        "godot_genuine": bool(env.get("godot_genuine", False)),
        "godot_bin_kind": str(env.get("godot_bin_kind") or "unavailable"),
    }

    identity_payload = {
        "test_id": test_id,
        "kind": kind,
        "path": test_path,
        "selector": selector_str,
        "min_tests": min_tests,
        "evidence_level": evidence_level,
        "manifest_evidence_level": manifest_evidence_level,
        "snapshot_digest": str(snapshot_digest or ""),
        "source_revision": str(source_revision or ""),
        "workspace_dirty": bool(workspace_dirty),
        "test_relevant_input_digest": relevant_input_digest,
        "verification_semantics": normalized_semantics,
        "toolchain_identity": normalized_toolchain,
    }
    evidence_identity_id = codec.canonical_digest(identity_payload)
    return {
        "evidence_identity_id": evidence_identity_id,
        "test_id": test_id,
        "kind": kind,
        "path": test_path,
        "selector": selector_str,
        "min_tests": min_tests,
        "evidence_level": evidence_level,
        "manifest_evidence_level": manifest_evidence_level,
        "snapshot_digest": str(snapshot_digest or ""),
        "source_revision": str(source_revision or ""),
        "workspace_dirty": bool(workspace_dirty),
        "test_relevant_input_digest": relevant_input_digest,
        "relevant_input_files": sorted(file_hashes.keys()),
        "relevant_input_hashes": file_hashes,
        "verification_semantics": normalized_semantics,
        "toolchain_identity": normalized_toolchain,
        "identity_payload": identity_payload,
    }


def collect_requirement_route_coverage(
    execution_root: Path,
    scope_doc: dict[str, Any],
    flow_ids: list[str],
    *,
    fallback_requirement_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Collect unique Requirement verification dispositions and multi-Flow route observable roles."""
    flow_set = {f for f in flow_ids if isinstance(f, str) and f}
    req_ids: set[str] = {r for r in (fallback_requirement_ids or []) if isinstance(r, str) and r}
    dispositions: dict[str, str] = {}
    routes: list[dict[str, Any]] = []
    seen_route: set[tuple[str, str]] = set()
    observable_roles: set[str] = set()

    plan_refs = (scope_doc.get("authority_refs") or {}).get("plan_refs") or []
    for pref in plan_refs:
        if not isinstance(pref, dict) or not isinstance(pref.get("path"), str):
            continue
        try:
            ppath = safe_path(execution_root, pref["path"])
        except ValueError:
            continue
        if not ppath.is_file() or ppath.is_symlink():
            continue
        try:
            inventory.no_reparse(ppath)
            pdoc = codec.strict_json_loads(ppath.read_bytes())
        except (OSError, ValueError, codec.CodecError):
            continue
        if not isinstance(pdoc, dict):
            continue
        for item in pdoc.get("applicability") or []:
            if isinstance(item, dict) and isinstance(item.get("requirement_id"), str) and isinstance(item.get("disposition"), str):
                dispositions.setdefault(item["requirement_id"], item["disposition"])
        for item in pdoc.get("requirement_verification") or []:
            if isinstance(item, dict) and isinstance(item.get("requirement_id"), str) and isinstance(item.get("disposition"), str):
                dispositions[item["requirement_id"]] = item["disposition"]
        for row in pdoc.get("requirement_route_memberships") or []:
            if not isinstance(row, dict):
                continue
            rid = row.get("requirement_id")
            fid = row.get("flow_id")
            if not isinstance(rid, str) or not isinstance(fid, str):
                continue
            if fid in flow_set:
                req_ids.add(rid)
                role = str(row.get("observable_role") or "")
                if role:
                    observable_roles.add(role)
                pair = (rid, fid)
                if pair not in seen_route:
                    seen_route.add(pair)
                    routes.append({
                        "requirement_id": rid,
                        "flow_id": fid,
                        "observable_role": role,
                        "disposition": dispositions.get(rid, "flow"),
                    })
        for fobj in ((pdoc.get("definitions") or {}).get("flows") or []):
            if isinstance(fobj, dict) and fobj.get("id") in flow_set:
                for rid in fobj.get("requirement_ids") or []:
                    if isinstance(rid, str) and rid:
                        req_ids.add(rid)
                        pair = (rid, fobj["id"])
                        if pair not in seen_route:
                            seen_route.add(pair)
                            routes.append({
                                "requirement_id": rid,
                                "flow_id": fobj["id"],
                                "observable_role": "",
                                "disposition": dispositions.get(rid, "flow"),
                            })

    routes.sort(key=lambda r: (r["requirement_id"], r["flow_id"]))
    req_disp = {rid: dispositions.get(rid, "flow") for rid in sorted(req_ids)}
    return {
        "requirement_ids": sorted(req_ids),
        "requirement_dispositions": req_disp,
        "route_memberships": routes,
        "observable_roles": sorted(observable_roles),
    }


def _resolve_verified_origin_run_dir(
    root_res: Path,
    prior_run_dir: Path,
    prior_entry: dict[str, Any],
) -> tuple[Path | None, str]:
    """Return the exact allowed run directory for raw reports and command_record."""
    mvg_logs_root = (root_res / "logs" / "ci" / "mvg-acceptance").resolve()
    prior_run_res = prior_run_dir.resolve()
    if prior_entry.get("reused") is True:
        origin_run_id = str(prior_entry.get("reused_from_run_id") or "").strip()
        if (
            not origin_run_id
            or "/" in origin_run_id
            or "\\" in origin_run_id
            or origin_run_id in {".", ".."}
        ):
            return None, "Chained reused entry has invalid reused_from_run_id"
        origin_dir = mvg_logs_root / origin_run_id
        try:
            _check_ancestors_no_reparse(origin_dir, stop_at=root_res)
            if not origin_dir.is_dir() or origin_dir.is_symlink():
                return None, f"Chained origin run directory missing: {origin_run_id}"
            inventory.no_reparse(origin_dir)
            origin_res = origin_dir.resolve()
        except (OSError, ValueError) as exc:
            return None, f"Unsafe chained origin run directory: {exc}"
        if origin_res.parent != mvg_logs_root:
            return None, f"Chained origin run directory escapes logs/ci/mvg-acceptance/: {origin_run_id}"
        origin_receipt = origin_res / "coverage-receipt.json"
        if not origin_receipt.is_file() or origin_receipt.is_symlink():
            return None, f"Chained origin run missing sealed coverage-receipt.json: {origin_run_id}"
        try:
            inventory.no_reparse(origin_receipt)
            origin_doc = codec.strict_json_loads(origin_receipt.read_bytes())
        except (OSError, ValueError, codec.CodecError) as exc:
            return None, f"Chained origin coverage-receipt.json unreadable: {exc}"
        if not verify_receipt_seal(origin_doc):
            return None, f"Chained origin coverage-receipt.json failed seal check: {origin_run_id}"
        return origin_res, "ok"
    return prior_run_res, "ok"


def _reverify_raw_reports(
    root: Path,
    prior_run_dir: Path,
    prior_entry: dict[str, Any],
    *,
    kind: str,
    expected: str,
    min_tests: int,
) -> tuple[bool, dict[str, Any], str]:
    """Re-parse raw .trx / results.xml reports from disk; reject tampered summaries or foreign sibling dirs."""
    root_res = root.resolve()
    mvg_logs_root = (root_res / "logs" / "ci" / "mvg-acceptance").resolve()
    allowed_run_dir, origin_reason = _resolve_verified_origin_run_dir(root_res, prior_run_dir, prior_entry)
    if allowed_run_dir is None:
        return False, {}, origin_reason

    raw_report_paths = list(prior_entry.get("report_paths") or [])
    if not raw_report_paths and isinstance(prior_entry.get("evidence"), dict):
        raw_report_paths = list(prior_entry["evidence"].get("reports") or [])
    if not raw_report_paths:
        return False, {}, "Prior test entry declares no raw report_paths"

    resolved_reports: list[Path] = []
    for raw_rp in raw_report_paths:
        if not isinstance(raw_rp, str) or not raw_rp.strip():
            return False, {}, "Invalid empty report path in prior test entry"
        rp = Path(raw_rp)
        if not rp.is_absolute():
            rp = root_res / rp
        try:
            _check_ancestors_no_reparse(rp, stop_at=root_res)
            if os.path.lexists(rp):
                inventory.no_reparse(rp)
            if rp.is_symlink():
                return False, {}, f"Report path is a symlink/reparse point: {raw_rp}"
            rp_res = rp.resolve()
        except (OSError, ValueError) as exc:
            return False, {}, f"Unsafe report path {raw_rp}: {exc}"
        # Raw reports MUST reside inside the verified owning run directory (never an arbitrary sibling run dir!).
        if allowed_run_dir not in rp_res.parents or mvg_logs_root not in rp_res.parents:
            return False, {}, f"Report path escapes owning run directory boundary: {raw_rp}"
        if not rp_res.is_file():
            return False, {}, f"Raw test report missing on disk: {raw_rp}"
        resolved_reports.append(rp_res)

    # Verify reports via read_test_evidence against their common parent inside the step dir.
    common_parent = Path(os.path.commonpath([str(p.parent) for p in resolved_reports]))
    if common_parent == root_res or common_parent == mvg_logs_root or common_parent == allowed_run_dir:
        return False, {}, "Report paths do not share a bounded step directory"
    if allowed_run_dir not in common_parent.parents:
        return False, {}, "Report common parent escapes owning run directory"
    recheck = read_test_evidence(common_parent, kind, expected, min_tests)
    if not recheck.get("passed"):
        return False, recheck, f"Raw test report failed re-verification: {recheck.get('reason')}"
    return True, recheck, "verified"


def _extract_original_timestamp(
    root: Path,
    prior_entry: dict[str, Any],
    prior_receipt: dict[str, Any] | None,
    prior_summary: dict[str, Any] | None,
) -> str:
    """Extract the original execution ISO timestamp without refreshing it to now()."""
    for key in ("original_executed_at", "finished_at", "executed_at"):
        val = prior_entry.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    cmd_rec = prior_entry.get("command_record")
    if isinstance(cmd_rec, str) and cmd_rec.strip():
        cp = Path(cmd_rec)
        if not cp.is_absolute():
            cp = root / cp
        try:
            if cp.is_file() and not cp.is_symlink():
                inventory.no_reparse(cp)
                cdoc = codec.strict_json_loads(cp.read_bytes())
                if isinstance(cdoc, dict) and isinstance(cdoc.get("finished_at"), str) and cdoc["finished_at"].strip():
                    return cdoc["finished_at"].strip()
        except (OSError, ValueError, codec.CodecError):
            pass
    for container in (prior_receipt, prior_summary):
        if isinstance(container, dict):
            val = container.get("finished_at")
            if isinstance(val, str) and val.strip():
                return val.strip()
    return ""


def evaluate_test_evidence_reuse(
    root: Path,
    execution_root: Path,
    *,
    test_spec: dict[str, Any],
    current_identity: dict[str, Any],
    candidate_run_dirs: list[str | Path],
    referencing_flow_ids: list[str],
    requirement_routes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Evaluate prior MVG runs for exact same-snapshot, same-identity test evidence reuse.

    Never splices across different integration snapshots, never allows protocol fixtures to
    satisfy genuine runs, never substitutes planning adoption for runtime evidence, never
    refreshes original_executed_at, and re-parses raw .trx/results.xml from disk.
    """
    test_id = str(current_identity.get("test_id") or test_spec.get("id") or "")
    kind = str(current_identity.get("kind") or test_spec.get("kind") or "")
    expected_selector = (
        str(current_identity.get("selector") or "")
        if kind == "dotnet"
        else Path(str(current_identity.get("path") or "")).stem
    )
    min_tests = int(current_identity.get("min_tests") or 1)
    rejections: list[dict[str, Any]] = []

    def _reject(cand_label: str, code: str, msg: str) -> None:
        rejections.append({
            "entity_id": test_id,
            "candidate": cand_label,
            "reason_code": code,
            "reason": msg,
        })

    # Refuse to reuse if current input_authenticity already failed!
    cur_sem = current_identity.get("verification_semantics") or {}
    if cur_sem.get("input_authenticity_valid") is False:
        _reject("current", "input_authenticity_failed", "Current test failed input authenticity; reuse forbidden")
        return {
            "reused": False,
            "reused_entry": None,
            "rejections": rejections,
            "manual_satisfied_by_machine_reuse": False,
            "planning_adoption_interchangeable": False,
        }

    for raw_cand in candidate_run_dirs or []:
        cand_label = str(raw_cand)
        try:
            cand_path, _cand_rel = _normalize_repo_rel(root, raw_cand, allow_logs=True)
        except ValueError as exc:
            _reject(cand_label, "unsafe_path", str(exc))
            continue

        if not cand_path.exists():
            _reject(cand_label, "candidate_not_found", f"Prior evidence source not found: {cand_label}")
            continue

        prior_run_dir = cand_path
        explicit_file_doc: dict[str, Any] | None = None
        if cand_path.is_file():
            try:
                explicit_file_doc = codec.strict_json_loads(cand_path.read_bytes())
            except (OSError, ValueError, codec.CodecError) as exc:
                _reject(cand_label, "corrupt_prior_receipt", f"Corrupt JSON file: {exc}")
                continue
            if is_planning_adoption_payload(explicit_file_doc):
                _reject(
                    cand_label,
                    "planning_adoption_not_runtime_evidence",
                    "Story 2.9 planning capability adoption receipt cannot be used as runtime test evidence",
                )
                continue
            schema = explicit_file_doc.get("schema_version") if isinstance(explicit_file_doc, dict) else None
            if schema not in {EXECUTION_RECEIPT_SCHEMA, MVG_SUMMARY_SCHEMA}:
                _reject(cand_label, "unknown_schema", f"Unsupported prior evidence schema: {schema}")
                continue
            prior_run_dir = cand_path.parent
        elif cand_path.is_dir():
            # Reject a directory missing sealed coverage-receipt.json (including Story 2.9 adoption-only dirs).
            if not (cand_path / "coverage-receipt.json").is_file():
                found_adoption = False
                for probe_name in ("adoption.json", "receipt.json", "capability-adoption.json"):
                    probe = cand_path / probe_name
                    if probe.is_file() and not probe.is_symlink():
                        try:
                            pdoc = codec.strict_json_loads(probe.read_bytes())
                            if is_planning_adoption_payload(pdoc):
                                found_adoption = True
                                break
                        except (OSError, ValueError, codec.CodecError):
                            pass
                if found_adoption:
                    _reject(
                        cand_label,
                        "planning_adoption_not_runtime_evidence",
                        "Directory contains planning adoption receipt, not runtime MVG execution evidence",
                    )
                    continue
                _reject(cand_label, "missing_prior_run_receipt", "Prior run directory missing sealed coverage-receipt.json")
                continue
        else:
            _reject(cand_label, "invalid_candidate", "Candidate must be a run directory or receipt JSON file")
            continue

        # 1. Verify input-manifest.json exists, is uncorrupted, and matches its snapshot_digest.
        manifest_file = prior_run_dir / "input-manifest.json"
        if not manifest_file.is_file() or manifest_file.is_symlink():
            _reject(cand_label, "corrupt_or_missing_input_manifest", "Missing input-manifest.json in prior run directory")
            continue
        try:
            inventory.no_reparse(manifest_file)
            input_manifest = codec.strict_json_loads(manifest_file.read_bytes())
        except (OSError, ValueError, codec.CodecError) as exc:
            _reject(cand_label, "corrupt_or_missing_input_manifest", f"Corrupt input-manifest.json: {exc}")
            continue
        if (
            not isinstance(input_manifest, dict)
            or not isinstance(input_manifest.get("files"), dict)
            or not isinstance(input_manifest.get("snapshot_digest"), str)
        ):
            _reject(cand_label, "corrupt_or_missing_input_manifest", "Invalid input-manifest.json structure")
            continue
        recomputed_snap = compute_snapshot_digest(input_manifest["files"])
        if recomputed_snap != input_manifest["snapshot_digest"]:
            _reject(cand_label, "corrupt_or_missing_input_manifest", "input-manifest.json snapshot_digest does not match files map")
            continue

        # 2. Require a valid sealed coverage-receipt.json (no unsealed summary.json-only fallback!).
        receipt_file = prior_run_dir / "coverage-receipt.json"
        if not receipt_file.is_file() or receipt_file.is_symlink():
            _reject(cand_label, "missing_prior_run_receipt", "Missing sealed coverage-receipt.json in prior run directory")
            continue
        try:
            inventory.no_reparse(receipt_file)
            prior_receipt = codec.strict_json_loads(receipt_file.read_bytes())
        except (OSError, ValueError, codec.CodecError) as exc:
            _reject(cand_label, "corrupt_coverage_receipt", f"Corrupt coverage-receipt.json: {exc}")
            continue
        if is_planning_adoption_payload(prior_receipt):
            _reject(cand_label, "planning_adoption_not_runtime_evidence", "coverage-receipt.json is a planning adoption payload")
            continue
        if not verify_receipt_seal(prior_receipt):
            _reject(cand_label, "corrupt_coverage_receipt", "coverage-receipt.json failed receipt_id integrity seal")
            continue

        prior_summary: dict[str, Any] | None = None
        summary_file = prior_run_dir / "summary.json"
        if summary_file.is_file():
            try:
                inventory.no_reparse(summary_file)
                prior_summary = codec.strict_json_loads(summary_file.read_bytes())
            except (OSError, ValueError, codec.CodecError) as exc:
                _reject(cand_label, "corrupt_summary", f"Corrupt summary.json: {exc}")
                continue
            if is_planning_adoption_payload(prior_summary):
                _reject(cand_label, "planning_adoption_not_runtime_evidence", "summary.json is a planning adoption payload")
                continue
            if not isinstance(prior_summary, dict) or prior_summary.get("schema_version") != MVG_SUMMARY_SCHEMA:
                _reject(cand_label, "unknown_schema", "Unsupported summary.json schema_version")
                continue

        # 3. Verify snapshot_digest, source_revision, workspace_dirty, drift, and state isolation.
        prior_snap_digest = str(prior_receipt.get("snapshot_digest") or "")
        prior_src_rev = str(prior_receipt.get("source_revision") or "")
        prior_dirty = bool(prior_receipt.get("workspace_dirty", False))

        if prior_snap_digest != input_manifest["snapshot_digest"]:
            _reject(cand_label, "inconsistent_prior_snapshot_metadata", "Receipt snapshot_digest disagrees with input-manifest.json")
            continue
        if prior_src_rev != str(input_manifest.get("source_revision") or ""):
            _reject(cand_label, "inconsistent_prior_snapshot_metadata", "Receipt source_revision disagrees with input-manifest.json")
            continue
        if prior_snap_digest != current_identity["snapshot_digest"]:
            _reject(
                cand_label,
                "snapshot_digest_mismatch",
                "Prior run snapshot_digest differs; cross-snapshot evidence splicing is forbidden",
            )
            continue
        if prior_src_rev != current_identity["source_revision"]:
            _reject(cand_label, "source_revision_mismatch", "Prior run source_revision differs from current snapshot")
            continue
        if prior_dirty != bool(current_identity["workspace_dirty"]):
            _reject(cand_label, "workspace_dirty_mismatch", "Prior run workspace_dirty flag differs from current run")
            continue

        pdrift = prior_receipt.get("drift") or {}
        if pdrift.get("drift_detected") or pdrift.get("post_run_valid") is False or pdrift.get("pre_run_valid") is False:
            _reject(cand_label, "prior_run_drifted", "Prior run experienced drift and cannot supply reusable evidence")
            continue
        piso = prior_receipt.get("state_isolation") or {}
        if piso.get("pollution_detected"):
            _reject(cand_label, "prior_run_state_polluted", "Prior run had mutable state pollution and cannot be reused")
            continue

        # Verify every test-relevant file hash matches prior input-manifest.json["files"].
        prior_manifest_files = input_manifest["files"]
        input_mismatch: list[str] = []
        for rel_file, cur_hash in (current_identity.get("relevant_input_hashes") or {}).items():
            prior_hash = prior_manifest_files.get(rel_file, "missing")
            if prior_hash != cur_hash:
                input_mismatch.append(rel_file)
        if input_mismatch:
            _reject(
                cand_label,
                "relevant_input_digest_mismatch",
                f"Test-relevant inputs changed since prior run: {input_mismatch[:5]}",
            )
            continue

        # 4. Locate candidate test entry and check exact identity (never merge same-name/different-input tests).
        prior_entries = list(prior_receipt.get("executed_tests") or [])

        matched_entry: dict[str, Any] | None = None
        for entry in prior_entries:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("id") or "") == test_id:
                matched_entry = entry
                break
        if matched_entry is None:
            _reject(cand_label, "test_not_found_in_prior_run", f"Test {test_id} was not executed in prior run")
            continue

        if matched_entry.get("status") != "passed" or int(matched_entry.get("exit_code", 1)) != 0:
            _reject(cand_label, "prior_test_not_passed", f"Prior test {test_id} did not pass cleanly")
            continue
        if int(matched_entry.get("failed_cases") or 0) > 0 or int(matched_entry.get("skipped_cases") or 0) > 0:
            _reject(cand_label, "prior_test_not_passed", f"Prior test {test_id} had failed or skipped cases")
            continue

        # Verify command_record exists, has no reparse points, and resides inside logs/ci/mvg-acceptance/ owning run dir!
        root_res = root.resolve()
        mvg_logs_root = (root_res / "logs" / "ci" / "mvg-acceptance").resolve()
        allowed_origin_dir, origin_err = _resolve_verified_origin_run_dir(root_res, prior_run_dir, matched_entry)
        if allowed_origin_dir is None:
            _reject(cand_label, "corrupt_or_invalid_raw_report", origin_err)
            continue
        cmd_rec_path = matched_entry.get("command_record")
        if not isinstance(cmd_rec_path, str) or not cmd_rec_path.strip():
            _reject(cand_label, "missing_command_record", "Prior entry lacks command_record")
            continue
        cp = Path(cmd_rec_path)
        if not cp.is_absolute():
            cp = root_res / cp
        try:
            _check_ancestors_no_reparse(cp, stop_at=root_res)
            if os.path.lexists(cp):
                inventory.no_reparse(cp)
            cp_res = cp.resolve()
        except (OSError, ValueError) as exc:
            _reject(cand_label, "unsafe_command_record", f"Unsafe command_record path: {exc}")
            continue
        if mvg_logs_root not in cp_res.parents or allowed_origin_dir not in cp_res.parents:
            _reject(cand_label, "unsafe_command_record", "Prior command_record escapes logs/ci/mvg-acceptance/ owning run directory")
            continue
        if not cp_res.is_file():
            _reject(cand_label, "missing_command_record", "Prior command_record file is missing")
            continue
        try:
            cdoc = codec.strict_json_loads(cp_res.read_bytes())
        except (OSError, ValueError, codec.CodecError) as exc:
            _reject(cand_label, "corrupt_command_record", f"Prior command_record is unreadable: {exc}")
            continue

        # Check embedded test_identity if present, AND cross-check explicit fields & command.json!
        prior_tid = matched_entry.get("test_identity") if isinstance(matched_entry.get("test_identity"), dict) else None
        if prior_tid is not None:
            field_diffs: list[str] = []
            for key in ("kind", "path", "selector", "min_tests", "evidence_level", "test_relevant_input_digest"):
                if prior_tid.get(key) != current_identity.get(key):
                    field_diffs.append(key)
            if field_diffs:
                _reject(
                    cand_label,
                    "test_identity_mismatch",
                    f"Prior test {test_id} differs on identity fields: {field_diffs}",
                )
                continue
            prior_sem = prior_tid.get("verification_semantics") or {}
            if prior_sem != cur_sem:
                _reject(
                    cand_label,
                    "verification_semantics_mismatch",
                    f"Verification semantics differ (prior={prior_sem.get('evidence_authenticity')}, current={cur_sem.get('evidence_authenticity')})",
                )
                continue
            prior_tc = prior_tid.get("toolchain_identity") or {}
            if prior_tc != current_identity.get("toolchain_identity"):
                _reject(cand_label, "toolchain_identity_mismatch", "Toolchain versions/platform differ from prior run")
                continue
            if prior_tid.get("evidence_identity_id") != current_identity.get("evidence_identity_id"):
                _reject(cand_label, "evidence_identity_mismatch", "Canonical evidence_identity_id does not match")
                continue
        else:
            # Fallback check for Story 4.3 sealed coverage-receipt.json that did not embed test_identity.
            if str(matched_entry.get("kind") or "") != kind:
                _reject(cand_label, "test_identity_mismatch", "Test kind differs from prior run")
                continue
            prior_ev_level = _normalize_evidence_level(kind, matched_entry.get("evidence_level"))
            if prior_ev_level != current_identity["evidence_level"]:
                _reject(cand_label, "test_identity_mismatch", "Test evidence_level differs from prior run")
                continue
            prior_env = prior_receipt.get("environment") or {}
            prior_fixture = bool(prior_env.get("protocol_fixture_only", True))
            if prior_fixture != bool(cur_sem.get("protocol_fixture_only", True)):
                _reject(cand_label, "evidence_authenticity_mismatch", "Protocol fixture evidence cannot satisfy real runtime run")
                continue
            prior_auth = str(matched_entry.get("evidence_authenticity") or prior_env.get("evidence_authenticity") or "protocol_fixture")
            if prior_auth != str(cur_sem.get("evidence_authenticity") or "protocol_fixture"):
                _reject(cand_label, "evidence_authenticity_mismatch", "Evidence authenticity differs from prior run")
                continue
            cur_tc = current_identity["toolchain_identity"]
            if (
                str(prior_env.get("dotnet_version") or "unavailable") != cur_tc["dotnet_version"]
                or str(prior_env.get("godot_version") or "unavailable") != cur_tc["godot_version"]
                or str(prior_env.get("os_platform") or "") != cur_tc["os_platform"]
            ):
                _reject(cand_label, "toolchain_identity_mismatch", "Prior toolchain environment differs from current run")
                continue
            if str(cdoc.get("expected") or "") != expected_selector or int(cdoc.get("min_tests") or 0) != min_tests:
                _reject(cand_label, "test_identity_mismatch", "Prior command_record expected selector or min_tests differs")
                continue

        # Explicit authenticity guard: protocol_fixture can NEVER satisfy real_runtime!
        prior_auth_val = str(
            matched_entry.get("evidence_authenticity")
            or (prior_receipt.get("environment") or {}).get("evidence_authenticity")
            or "protocol_fixture"
        )
        if prior_auth_val == "protocol_fixture" and not cur_sem.get("protocol_fixture_only", True):
            _reject(cand_label, "evidence_authenticity_mismatch", "Protocol fixture result cannot satisfy real binary run")
            continue

        # 5. Re-verify raw .trx / results.xml report files from disk!
        raw_ok, raw_ev, raw_reason = _reverify_raw_reports(
            root,
            prior_run_dir,
            matched_entry,
            kind=kind,
            expected=expected_selector,
            min_tests=min_tests,
        )
        if not raw_ok:
            _reject(cand_label, "corrupt_or_invalid_raw_report", raw_reason)
            continue

        # 6. Preserve original_executed_at timestamp (NEVER refresh to now()).
        original_ts = _extract_original_timestamp(root, matched_entry, prior_receipt, prior_summary)
        if not original_ts:
            _reject(cand_label, "missing_original_timestamp", "Prior evidence lacks verifiable original_executed_at timestamp")
            continue

        reused_from_run_id = str(
            matched_entry.get("reused_from_run_id")
            or prior_receipt.get("run_id")
            or prior_run_dir.name
        )
        reused_evidence_id = str(
            matched_entry.get("reused_evidence_id")
            or prior_receipt.get("receipt_id")
        )

        routes = list(requirement_routes or [])
        req_ids = sorted({r["requirement_id"] for r in routes if isinstance(r, dict) and isinstance(r.get("requirement_id"), str)})
        obs_roles = sorted({r["observable_role"] for r in routes if isinstance(r, dict) and r.get("observable_role")})
        passed_cases = max(
            0,
            int(raw_ev.get("tests", 0)) - int(raw_ev.get("failed", 0)) - int(raw_ev.get("skipped", 0)),
        )
        reused_entry = {
            "id": test_id,
            "kind": kind,
            "evidence_level": current_identity["evidence_level"],
            "manifest_evidence_level": current_identity["manifest_evidence_level"],
            "evidence_authenticity": cur_sem.get("evidence_authenticity", "protocol_fixture"),
            "command": list(matched_entry.get("command") or []),
            "command_record": matched_entry.get("command_record"),
            "exit_code": 0,
            "status": "passed",
            "passed_cases": passed_cases,
            "failed_cases": 0,
            "skipped_cases": 0,
            "log_path": matched_entry.get("log_path") or matched_entry.get("log") or "",
            "report_paths": list(raw_ev.get("reports") or matched_entry.get("report_paths") or []),
            "input_authenticity": matched_entry.get("input_authenticity") or {"checked": False, "valid": True, "reason": "reused"},
            "evidence_reason": "reused_verified_same_snapshot_evidence",
            "reused": True,
            "freshly_executed": False,
            "reused_from_run_id": reused_from_run_id,
            "reused_evidence_id": reused_evidence_id,
            "original_executed_at": original_ts,
            "match_reason": "exact_snapshot_input_semantics_and_toolchain_identity_match",
            "referencing_flow_ids": sorted(set(referencing_flow_ids)),
            "requirement_ids": req_ids,
            "observable_roles": obs_roles,
            "requirement_routes": routes,
            "test_identity": current_identity,
            "build_reuse": {
                "reused": False,
                "kind": "dotnet_build" if kind == "dotnet" else "godot_prewarm",
                "reason_code": "skipped_due_to_test_evidence_reuse",
                "reason": "Test execution was satisfied by verified same-snapshot test evidence reuse",
                "build_reuse_implies_test_pass": False,
                "reserved_budget_claimed_as_savings": False,
            },
            "state_isolation": {
                "isolated": True,
                "pollution_detected": False,
                "reason_code": "reused_read_only_evidence",
                "reason": "No child process executed; verified read-only evidence reused",
                "modified_files": [],
                "added_files": [],
                "deleted_files": [],
            },
            "elapsed_seconds": 0.0,
        }
        return {
            "reused": True,
            "reused_entry": reused_entry,
            "rejections": rejections,
            "manual_satisfied_by_machine_reuse": False,
            "planning_adoption_interchangeable": False,
        }

    return {
        "reused": False,
        "reused_entry": None,
        "rejections": rejections,
        "manual_satisfied_by_machine_reuse": False,
        "planning_adoption_interchangeable": False,
    }


# ---------------------------------------------------------------------------
# AC-3: Per-Test Mutable State Isolation & Post-Test Immutability Check
# ---------------------------------------------------------------------------

def prepare_isolated_test_env(base_env: dict[str, str] | None, step_out_dir: Path) -> dict[str, str]:
    """Create fresh per-test isolated user-data and temp directories and return isolated env."""
    step_dir = Path(step_out_dir)
    user_data_dir = step_dir / "isolated-user-data"
    temp_dir = step_dir / "isolated-temp"

    for d in (user_data_dir, temp_dir):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)
    local_dir = user_data_dir / "local"
    config_dir = user_data_dir / "config"
    local_dir.mkdir(parents=True, exist_ok=True)
    config_dir.mkdir(parents=True, exist_ok=True)

    env = dict(base_env if base_env is not None else os.environ)
    env["APPDATA"] = str(user_data_dir)
    env["LOCALAPPDATA"] = str(local_dir)
    env["XDG_DATA_HOME"] = str(user_data_dir)
    env["XDG_CONFIG_HOME"] = str(config_dir)
    env["TEMP"] = str(temp_dir)
    env["TMP"] = str(temp_dir)
    env["NEWROGUE_ISOLATED_USER_DATA"] = str(user_data_dir)
    env["NEWROGUE_ISOLATED_TEMP"] = str(temp_dir)
    env["GDUNIT_STRICT_EXIT_CODE"] = "1"
    return env


def capture_snapshot_file_hashes(execution_root: Path) -> dict[str, str]:
    """Capture sha256 hashes of all tracked/non-regenerable files inside execution_root."""
    hashes: dict[str, str] = {}
    for rel, fp in _walk_safe_files(execution_root, ignore_workspace_dirs=True):
        hashes[rel] = _sha256_file(fp)
    return hashes


def _safe_clean_ephemeral_dir(exec_root: Path, rel_dir: str) -> bool:
    """Safely remove an ephemeral test output dir inside execution_root after verifying zero reparse points."""
    target = safe_path(exec_root, rel_dir)
    if not os.path.lexists(target):
        return False
    _check_ancestors_no_reparse(target, stop_at=exec_root)
    inventory.no_reparse(target)
    if not target.is_dir():
        raise ValueError(f"Unexpected non-directory at ephemeral path in snapshot: {rel_dir}")
    for dirpath, dirnames, filenames in os.walk(target, followlinks=False):
        cur = Path(dirpath)
        inventory.no_reparse(cur)
        for dname in dirnames:
            inventory.no_reparse(cur / dname)
        for fname in filenames:
            inventory.no_reparse(cur / fname)
    shutil.rmtree(target)
    return True


def verify_post_test_isolation(
    execution_root: Path,
    pre_snapshot_hashes: dict[str, str],
    step_out_dir: Path,
) -> dict[str, Any]:
    """Verify a test step did not mutate tracked files or create foreign reparse points inside execution_root."""
    step_dir = Path(step_out_dir)
    exec_root = Path(execution_root).resolve()
    cleaned_ephemeral_dirs: list[str] = []
    try:
        for rel_dir in _EPHEMERAL_TEST_DIRS:
            if _safe_clean_ephemeral_dir(exec_root, rel_dir):
                cleaned_ephemeral_dirs.append(rel_dir)
        post_hashes = capture_snapshot_file_hashes(exec_root)
    except ValueError as exc:
        return {
            "isolated": False,
            "pollution_detected": True,
            "reason_code": "mutable_test_state_pollution_detected",
            "reason": f"Snapshot isolation check failed closed: {exc}",
            "modified_files": [],
            "added_files": [],
            "deleted_files": [],
            "cleaned_ephemeral_dirs": cleaned_ephemeral_dirs,
            "isolated_user_data_dir": str(step_dir / "isolated-user-data"),
            "isolated_temp_dir": str(step_dir / "isolated-temp"),
        }

    pre_keys = set(pre_snapshot_hashes.keys())
    post_keys = set(post_hashes.keys())

    modified = sorted(k for k in (pre_keys & post_keys) if pre_snapshot_hashes[k] != post_hashes[k])
    added = sorted(post_keys - pre_keys)
    deleted = sorted(pre_keys - post_keys)
    polluted = bool(modified or added or deleted)

    return {
        "isolated": not polluted,
        "pollution_detected": polluted,
        "reason_code": "mutable_test_state_pollution_detected" if polluted else "ok",
        "reason": (
            f"Test mutated tracked snapshot state: modified={modified}, added={added}, deleted={deleted}"
            if polluted
            else "snapshot_immutable_and_per_test_dirs_isolated"
        ),
        "modified_files": modified,
        "added_files": added,
        "deleted_files": deleted,
        "cleaned_ephemeral_dirs": cleaned_ephemeral_dirs,
        "isolated_user_data_dir": str(step_dir / "isolated-user-data"),
        "isolated_temp_dir": str(step_dir / "isolated-temp"),
    }


# ---------------------------------------------------------------------------
# AC-5: Deterministic Deduplicated Event Log Writer (with OS file lock)
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _events_file_lock(events_path: Path, timeout_sec: float = 10.0):
    lock_path = events_path.with_name(events_path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    _check_ancestors_no_reparse(lock_path)
    if os.path.lexists(lock_path):
        inventory.no_reparse(lock_path)
    fh = lock_path.open("a+b")
    locked = False
    try:
        fh.seek(0, os.SEEK_END)
        if fh.tell() == 0:
            fh.write(b"\0")
            fh.flush()
        deadline = time.monotonic() + max(0.5, timeout_sec)
        while True:
            try:
                fh.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                locked = True
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out acquiring events log lock: {lock_path}")
                time.sleep(0.02)
        yield
    finally:
        if locked:
            try:
                fh.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        fh.close()


def append_deduplicated_event(events_path: Path, event_payload: dict[str, Any]) -> bool:
    """Append a JSONL event only if its deterministic canonical event_id is not already recorded.

    Uses a sidecar .lock file with Windows msvcrt.locking so concurrent appends never race.
    Returns True if appended, False if deduplicated (already present).
    """
    if not isinstance(event_payload, dict):
        raise ValueError("event_payload must be a dict")
    target = Path(events_path)
    if not target.name.lower().endswith(".jsonl"):
        raise ValueError(f"Events log path must use .jsonl suffix: {target}")
    _check_ancestors_no_reparse(target)
    if os.path.lexists(target):
        inventory.no_reparse(target)

    explicit_id = event_payload.get("event_id")
    if isinstance(explicit_id, str) and explicit_id.strip():
        event_id = explicit_id.strip()
    else:
        canonical_body = {k: v for k, v in event_payload.items() if k not in _VOLATILE_EVENT_FIELDS}
        event_id = codec.canonical_digest(canonical_body)

    with _events_file_lock(target):
        _check_ancestors_no_reparse(target)
        if os.path.lexists(target):
            inventory.no_reparse(target)
        existing_ids: set[str] = set()
        if target.is_file():
            raw_text = target.read_text(encoding="utf-8")
            for line in raw_text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                except ValueError:
                    continue
                if isinstance(parsed, dict) and isinstance(parsed.get("event_id"), str):
                    existing_ids.add(parsed["event_id"])

        if event_id in existing_ids:
            return False

        record = dict(event_payload)
        record["event_id"] = event_id
        record.setdefault("recorded_at", _now())
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            fh.flush()
        return True
