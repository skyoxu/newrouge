#!/usr/bin/env python3
"""Refresh registered Chapter closure topology without weakening KCP authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from _semantic_topology import TOPOLOGY_ARTIFACTS, build_topology_view, unavailable_topology
from validate_semantic_conservation import validate as validate_semantic_conservation

TOPOLOGY_RUNTIME_DIR = Path("logs/ci/project-health-knowledge/topology")
ATTEMPT_PATH = TOPOLOGY_RUNTIME_DIR / "workspace-last-attempt.json"
LEGACY_ATTEMPT_PATH = TOPOLOGY_RUNTIME_DIR / "workspace-latest.json"
STABLE_PATH = TOPOLOGY_RUNTIME_DIR / "workspace-latest-successful.json"
REGISTERED_SOURCES = {"chapter3", "chapter5"}


def load_json(path: Path, default: Any = None) -> Any:
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    """Atomically replace JSON so a failed refresh cannot corrupt prior stable state."""
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
            try:
                tmp.unlink()
            except OSError:
                pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _snapshot_file(path: Path) -> bytes | None:
    return path.read_bytes() if path.is_file() else None


def _restore_file(path: Path, snapshot: bytes | None) -> None:
    if snapshot is None:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".restore.tmp")
    try:
        tmp.write_bytes(snapshot)
        tmp.replace(path)
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


def closure_evidence(
    root: Path,
    source: str,
    ledger: dict[str, Any],
    semantics: dict[str, Any],
    candidates: dict[str, Any],
    persisted_report: dict[str, Any],
) -> tuple[dict[str, Any], bool, str]:
    """Re-validate Chapter 3 closure and bind refresh to the exact current artifacts."""
    if source != "chapter3":
        passed = persisted_report.get("status") == "passed"
        return persisted_report, passed, "legacy_registered_source"

    recomputed, _edges = validate_semantic_conservation(
        root, ledger, semantics, "closure", candidates
    )
    errors: list[str] = []
    if persisted_report.get("schema_version") != "chapter3.semantic-conservation-report.v1":
        errors.append("invalid_report_schema")
    if persisted_report.get("stage") != "closure":
        errors.append("closure_stage_required")
    if str(persisted_report.get("source_revision") or "") != str(ledger.get("source_revision") or ""):
        errors.append("report_source_revision_mismatch")
    if str(persisted_report.get("source_manifest_sha256") or "") != str(ledger.get("source_manifest_sha256") or ""):
        errors.append("report_source_manifest_mismatch")
    if persisted_report.get("status") != recomputed.get("status"):
        errors.append("report_status_mismatch")
    if persisted_report.get("blocking_counts", {}) != recomputed.get("blocking_counts", {}):
        errors.append("report_blocking_counts_mismatch")

    passed = not errors and recomputed.get("status") == "passed"
    if passed:
        return recomputed, True, "verified_closure"

    effective = dict(recomputed)
    blocking = dict(effective.get("blocking_counts", {}))
    blocking["closure_evidence_invalid"] = 1
    effective["blocking_counts"] = blocking
    effective["status"] = "blocked"
    details = dict(effective.get("details", {}))
    details["closure_evidence_errors"] = errors or ["recomputed_closure_blocked"]
    effective["details"] = details
    return effective, False, ",".join(errors or ["recomputed_closure_blocked"])


def workspace_revision(
    source: str,
    trigger_run_id: str,
    source_revision: str,
    conservation_report: dict[str, Any],
) -> str:
    binding = {
        "source": source,
        "trigger_run_id": trigger_run_id,
        "source_revision": source_revision,
        "report_status": conservation_report.get("status"),
        "blocking_counts": conservation_report.get("blocking_counts", {}),
    }
    raw = json.dumps(binding, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "workspace:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def task_details_from_candidates(candidates: dict[str, Any]) -> list[dict[str, Any]]:
    details = []
    for row in candidates.get("candidates", []):
        if not isinstance(row, dict) or row.get("id") is None:
            continue
        task = dict(row)
        task["id"] = str(row["id"])
        details.append({"task": task, "mappings": {}, "godot": {"status": "unmapped", "scenes": []}})
    return details


def view_problems(report: dict[str, Any], triplet_status: str) -> list[dict[str, Any]]:
    problems = []
    for family, count in report.get("blocking_counts", {}).items():
        if isinstance(count, int) and count > 0:
            problems.append({"kind": family, "count": count})
    if triplet_status != "passed":
        problems.append({"kind": "triplet_baseline_not_passed", "status": triplet_status})
    return problems


def build_workspace_view(
    source: str,
    trigger_run_id: str,
    source_manifest: dict[str, Any],
    ledger: dict[str, Any],
    semantics: dict[str, Any],
    capabilities: dict[str, Any],
    edges: dict[str, Any],
    candidates: dict[str, Any],
    report: dict[str, Any],
    triplet_status: str,
    view_kind: str,
) -> dict[str, Any]:
    source_revision = str(
        ledger.get("source_revision")
        or source_manifest.get("source_revision")
        or semantics.get("source_revision")
        or "unknown"
    )
    revision = workspace_revision(source, trigger_run_id, source_revision, report)
    identity = {
        "kind": "workspace",
        "revision": revision,
        "trigger_run_id": trigger_run_id,
        "chapter_source": source,
        "source_revision": source_revision,
    }
    manifest = {
        "schema_version": "newrouge.semantic-topology-manifest.v1",
        "source_revision": source_revision,
        "source_manifest_sha256": source_manifest.get("manifest_sha256")
        or ledger.get("source_manifest_sha256"),
        "schema_revision": "v1",
        "generator_revision": "chapter-closure-refresh-v1",
        "artifacts": {},
    }
    view = build_topology_view(
        identity,
        manifest,
        ledger,
        semantics,
        capabilities,
        edges,
        task_details_from_candidates(candidates),
        view_problems(report, triplet_status),
    )
    report_passed = report.get("status") == "passed"
    closure_passed = report_passed and triplet_status == "passed"
    view["workspace_view"] = view_kind
    view["chapter_run"] = {
        "source": source,
        "trigger_run_id": trigger_run_id,
        "conservation_status": report.get("status", "unknown"),
        "triplet_status": triplet_status,
        "closure_passed": closure_passed,
    }
    view["status"] = "passed" if closure_passed else "concern"
    if not closure_passed:
        view["fresh"] = False
    return view


def copy_planning_artifacts(
    root: Path,
    source_manifest: dict[str, Any],
    ledger_path: Path,
    semantics_path: Path,
    capabilities_path: Path,
    edges_path: Path,
) -> dict[str, Any]:
    destinations = {
        "source_blocks": root / TOPOLOGY_ARTIFACTS["source_blocks"],
        "requirements": root / TOPOLOGY_ARTIFACTS["requirements"],
        "capabilities": root / TOPOLOGY_ARTIFACTS["capabilities"],
        "edges": root / TOPOLOGY_ARTIFACTS["edges"],
    }
    sources = {
        "source_blocks": ledger_path,
        "requirements": semantics_path,
        "capabilities": capabilities_path,
        "edges": edges_path,
    }
    manifest_path = root / TOPOLOGY_ARTIFACTS["manifest"]
    snapshots = {
        path: _snapshot_file(path)
        for path in [*destinations.values(), manifest_path]
    }
    try:
        artifact_hashes = {}
        for key, destination in destinations.items():
            source_path = sources[key]
            if not source_path.is_file():
                raise ValueError(f"missing topology source artifact: {source_path}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, destination)
            artifact_hashes[destination.relative_to(root).as_posix()] = "sha256:" + sha256_bytes(destination.read_bytes())
        manifest = {
            "schema_version": "newrouge.semantic-topology-manifest.v1",
            "source_revision": source_manifest.get("source_revision"),
            "source_manifest_sha256": source_manifest.get("manifest_sha256"),
            "schema_revision": "v1",
            "generator_revision": "chapter3-semantic-conservation-v1",
            "artifacts": artifact_hashes,
        }
        # Do not write repository_revision here: the generated topology is
        # committed after this step, so binding it to the pre-commit HEAD would make
        # the just-committed topology immediately stale. Keep the observed source
        # checkout only as audit metadata; canonical freshness is bound later by KCP
        # publication plus per-source hashes.
        source_repository_revision = source_manifest.get("repository_revision")
        if isinstance(source_repository_revision, str) and source_repository_revision:
            manifest["source_repository_revision"] = source_repository_revision
        write_json(manifest_path, manifest)
        return manifest
    except Exception:
        for path, snapshot in snapshots.items():
            try:
                _restore_file(path, snapshot)
            except OSError:
                pass
        raise


def git_result(root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
        check=True,
    )
    return result.stdout.strip()


def publication_eligibility(root: Path) -> tuple[bool, str]:
    try:
        branch = git_result(root, ["branch", "--show-current"])
        dirty = git_result(root, ["status", "--porcelain"])
        head = git_result(root, ["rev-parse", "HEAD"])
        main = git_result(root, ["rev-parse", "refs/heads/main"])
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"git_state_unavailable:{exc}"
    if branch != "main":
        return False, f"trusted_ref_required:branch={branch or 'detached'}"
    if dirty:
        return False, "dirty_worktree"
    if head != main:
        return False, "head_not_local_main"
    return True, "eligible"


def current_generation(root: Path) -> str | None:
    payload = load_json(root / "knowledge/indexes/current.json", {})
    value = payload.get("generation_id") if isinstance(payload, dict) else None
    return str(value) if value else None


def maybe_publish(root: Path, requested: bool) -> tuple[str, str]:
    if not requested:
        return "deferred", "not_requested"
    eligible, reason = publication_eligibility(root)
    if not eligible:
        return "deferred", reason
    result = subprocess.run(
        ["py", "-3", "scripts/python/publish_knowledge_catalog.py", "--publish"],
        cwd=root,
        text=True,
        capture_output=True,
        encoding="utf-8",
        timeout=300,
        check=False,
    )
    if result.returncode != 0:
        return "failed", (result.stderr or result.stdout)[-1200:]
    return "published", "trusted_ref_publication_complete"


def partial_attempt(
    source: str,
    trigger_run_id: str,
    reason: str,
    missing: list[str],
) -> dict[str, Any]:
    raw = source + chr(0) + trigger_run_id + chr(0) + reason
    revision = "workspace:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    payload = unavailable_topology("workspace", revision, reason)
    payload["identity"].update({
        "trigger_run_id": trigger_run_id,
        "chapter_source": source,
        "source_revision": "unknown",
    })
    payload["workspace_view"] = "last_attempt"
    payload["status"] = "concern"
    payload["problems"] = [{"kind": "missing_refresh_input", "path": path} for path in missing]
    payload["chapter_run"] = {
        "source": source,
        "trigger_run_id": trigger_run_id,
        "conservation_status": "unavailable",
        "triplet_status": "unknown",
        "closure_passed": False,
    }
    return payload


def _mark_attempt_refresh_failure(
    root: Path,
    attempt: dict[str, Any],
    family: str,
    reason: str,
) -> bool:
    """Best-effort: make Project Health Last Attempt show the refresh failure."""
    attempt["status"] = "concern"
    attempt["fresh"] = False
    problems = attempt.setdefault("problems", [])
    if isinstance(problems, list):
        problems.append({
            "kind": "knowledge_refresh_failed",
            "failure_family": family,
            "reason": reason,
        })
    chapter_run = attempt.setdefault("chapter_run", {})
    if isinstance(chapter_run, dict):
        chapter_run["closure_passed"] = False
        chapter_run["knowledge_refresh_status"] = "failed"
        chapter_run["knowledge_refresh_failure_family"] = family
    try:
        write_json(root / ATTEMPT_PATH, attempt)
        write_json(root / LEGACY_ATTEMPT_PATH, attempt)
    except OSError:
        return False
    return True


def _refresh_failure_summary(
    root: Path,
    *,
    source: str,
    trigger_run_id: str,
    topology_revision: str | None,
    semantic_triplet_closure_passed: bool,
    family: str,
    reason: str,
    attempt_written: bool,
) -> dict[str, Any]:
    return {
        "schema_version": "chapter-knowledge-refresh-summary.v1",
        "source": source,
        "trigger_run_id": trigger_run_id,
        "topology_revision": topology_revision,
        "semantic_triplet_closure_passed": semantic_triplet_closure_passed,
        "closure_passed": False,
        "chapter_closure_status": "knowledge_refresh_failed",
        "local_refresh_status": "failed",
        "local_refresh_failure_family": family,
        "local_refresh_reason": reason,
        "planning_artifact_status": "blocked_by_knowledge_refresh",
        "publication_status": "deferred",
        "publication_reason": "knowledge_refresh_failed",
        "current_generation_id": current_generation(root),
        "attempt_path": ATTEMPT_PATH.as_posix() if attempt_written else None,
        "stable_path": None,
    }


def run(
    root: Path,
    *,
    source: str,
    trigger_run_id: str,
    refresh_local: bool,
    write_planning: bool,
    publish_if_eligible: bool,
    triplet_status: str,
    source_manifest_path: Path,
    ledger_path: Path,
    semantics_path: Path,
    capabilities_path: Path,
    edges_path: Path,
    candidates_path: Path,
    report_path: Path,
) -> dict[str, Any]:
    if source not in REGISTERED_SOURCES:
        raise ValueError(f"unregistered closure producer: {source}")
    required = [
        source_manifest_path, ledger_path, semantics_path, capabilities_path,
        edges_path, candidates_path, report_path,
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        reason = "partial Chapter closure: required refresh inputs are missing"
        if refresh_local:
            attempt = partial_attempt(source, trigger_run_id, reason, missing)
            try:
                write_json(root / ATTEMPT_PATH, attempt)
                write_json(root / LEGACY_ATTEMPT_PATH, attempt)
            except OSError as exc:
                return _refresh_failure_summary(
                    root,
                    source=source,
                    trigger_run_id=trigger_run_id,
                    topology_revision=attempt.get("identity", {}).get("revision"),
                    semantic_triplet_closure_passed=False,
                    family="attempt_refresh_failed",
                    reason=str(exc),
                    attempt_written=False,
                )
        return {
            "schema_version": "chapter-knowledge-refresh-summary.v1",
            "source": source,
            "trigger_run_id": trigger_run_id,
            "topology_revision": None,
            "closure_passed": False,
            "local_refresh_status": "attempt_refreshed_partial" if refresh_local else "skipped",
            "planning_artifact_status": "blocked_by_closure",
            "publication_status": "deferred",
            "publication_reason": "missing_refresh_inputs",
            "current_generation_id": current_generation(root),
            "attempt_path": ATTEMPT_PATH.as_posix() if refresh_local else None,
            "stable_path": None,
            "missing_inputs": missing,
        }

    source_manifest = load_json(source_manifest_path, {})
    ledger = load_json(ledger_path, {})
    semantics = load_json(semantics_path, {})
    capabilities = load_json(capabilities_path, {})
    edges = load_json(edges_path, {})
    candidates = load_json(candidates_path, {})
    persisted_report = load_json(report_path, {})
    report, closure_evidence_passed, closure_evidence_reason = closure_evidence(
        root, source, ledger, semantics, candidates, persisted_report
    )
    semantic_triplet_closure_passed = (
        closure_evidence_passed and triplet_status == "passed"
    )

    attempt = build_workspace_view(
        source, trigger_run_id, source_manifest, ledger, semantics, capabilities,
        edges, candidates, report, triplet_status, "last_attempt",
    )
    attempt.setdefault("chapter_run", {})["closure_evidence_status"] = (
        "verified" if closure_evidence_passed else "blocked"
    )
    attempt["chapter_run"]["closure_evidence_reason"] = closure_evidence_reason
    local_status = "skipped"
    attempt_written = False
    stable_snapshot = _snapshot_file(root / STABLE_PATH)
    if refresh_local:
        try:
            write_json(root / ATTEMPT_PATH, attempt)
            attempt_written = True
            write_json(root / LEGACY_ATTEMPT_PATH, attempt)
        except OSError as exc:
            return _refresh_failure_summary(
                root,
                source=source,
                trigger_run_id=trigger_run_id,
                topology_revision=attempt.get("identity", {}).get("revision"),
                semantic_triplet_closure_passed=semantic_triplet_closure_passed,
                family="attempt_refresh_failed",
                reason=str(exc),
                attempt_written=attempt_written,
            )
        local_status = "attempt_refreshed"
        if semantic_triplet_closure_passed:
            stable = build_workspace_view(
                source, trigger_run_id, source_manifest, ledger, semantics, capabilities,
                edges, candidates, report, triplet_status, "latest_successful",
            )
            try:
                write_json(root / STABLE_PATH, stable)
            except OSError as exc:
                _mark_attempt_refresh_failure(
                    root, attempt, "stable_refresh_failed", str(exc)
                )
                return _refresh_failure_summary(
                    root,
                    source=source,
                    trigger_run_id=trigger_run_id,
                    topology_revision=attempt.get("identity", {}).get("revision"),
                    semantic_triplet_closure_passed=True,
                    family="stable_refresh_failed",
                    reason=str(exc),
                    attempt_written=True,
                )
            local_status = "stable_refreshed"

    stable_required = write_planning or publish_if_eligible
    closure_passed = semantic_triplet_closure_passed and (
        local_status == "stable_refreshed"
        if refresh_local
        else not stable_required
    )

    planning_status = "not_requested"
    if write_planning:
        if not closure_passed:
            planning_status = "blocked_by_closure"
        else:
            try:
                copy_planning_artifacts(
                    root, source_manifest, ledger_path, semantics_path, capabilities_path, edges_path
                )
            except (OSError, ValueError) as exc:
                try:
                    _restore_file(root / STABLE_PATH, stable_snapshot)
                except OSError:
                    pass
                _mark_attempt_refresh_failure(
                    root, attempt, "planning_topology_refresh_failed", str(exc)
                )
                return _refresh_failure_summary(
                    root,
                    source=source,
                    trigger_run_id=trigger_run_id,
                    topology_revision=attempt.get("identity", {}).get("revision"),
                    semantic_triplet_closure_passed=True,
                    family="planning_topology_refresh_failed",
                    reason=str(exc),
                    attempt_written=attempt_written,
                )
            planning_status = "written"

    if closure_passed:
        publication_status, publication_reason = maybe_publish(root, publish_if_eligible)
    else:
        publication_status, publication_reason = "deferred", "closure_not_passed"
    summary = {
        "schema_version": "chapter-knowledge-refresh-summary.v1",
        "source": source,
        "trigger_run_id": trigger_run_id,
        "topology_revision": attempt.get("identity", {}).get("revision"),
        "semantic_triplet_closure_passed": semantic_triplet_closure_passed,
        "closure_evidence_status": "verified" if closure_evidence_passed else "blocked",
        "closure_evidence_reason": closure_evidence_reason,
        "closure_passed": closure_passed,
        "chapter_closure_status": "passed" if closure_passed else "concern",
        "local_refresh_status": local_status,
        "local_refresh_failure_family": None,
        "planning_artifact_status": planning_status,
        "publication_status": publication_status,
        "publication_reason": publication_reason,
        "current_generation_id": current_generation(root),
        "attempt_path": ATTEMPT_PATH.as_posix() if refresh_local else None,
        "stable_path": STABLE_PATH.as_posix() if refresh_local and closure_passed else None,
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--source", choices=sorted(REGISTERED_SOURCES), required=True)
    parser.add_argument("--trigger-run-id", required=True)
    parser.add_argument("--refresh-local", action="store_true")
    parser.add_argument("--write-planning-artifacts", action="store_true")
    parser.add_argument("--publish-if-eligible", action="store_true")
    parser.add_argument("--triplet-status", choices=["passed", "blocked", "unknown"], default="unknown")
    parser.add_argument("--source-manifest", default="logs/ci/task-generation/source-manifest.v1.json")
    parser.add_argument("--ledger", default="logs/ci/task-generation/source-blocks.v1.json")
    parser.add_argument("--semantics", default="logs/ci/task-generation/semantic-requirements.v1.json")
    parser.add_argument("--capabilities", default="logs/ci/task-generation/capabilities.v1.json")
    parser.add_argument("--edges", default="logs/ci/task-generation/topology-edges.v1.json")
    parser.add_argument("--candidates", default="logs/ci/task-generation/task-candidates.enriched.json")
    parser.add_argument("--report", default="logs/ci/task-generation/semantic-conservation-report.json")
    args = parser.parse_args(argv)
    root = Path(args.repo_root).resolve()
    try:
        summary = run(
            root,
            source=args.source,
            trigger_run_id=args.trigger_run_id,
            refresh_local=args.refresh_local,
            write_planning=args.write_planning_artifacts,
            publish_if_eligible=args.publish_if_eligible,
            triplet_status=args.triplet_status,
            source_manifest_path=root / args.source_manifest,
            ledger_path=root / args.ledger,
            semantics_path=root / args.semantics,
            capabilities_path=root / args.capabilities,
            edges_path=root / args.edges,
            candidates_path=root / args.candidates,
            report_path=root / args.report,
        )
    except ValueError as exc:
        print(json.dumps({
            "schema_version": "chapter-knowledge-refresh-summary.v1",
            "source": args.source,
            "trigger_run_id": args.trigger_run_id,
            "local_refresh_status": "failed",
            "publication_status": "deferred",
            "publication_reason": str(exc),
        }, ensure_ascii=False))
        return 2
    print(json.dumps(summary, ensure_ascii=False))
    if summary["local_refresh_status"] == "failed" or summary["publication_status"] == "failed":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
