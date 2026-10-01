"""Chapter 6 consumer of applied MVG verification obligation bindings."""
from pathlib import Path
from typing import Any

from _planning_skill_common import file_sha, load_json, repo_path

TRACE_ROOT = Path("docs/testing/mvg/planning")


def applicable_milestone_plans(root: Path, task_id: str, manifest_ref: str) -> list[Path]:
    plans = []
    revision = load_json(root / "logs/ci/task-generation/source-manifest.v1.json", {}).get("source_revision")
    for path in sorted((root / "docs/planning/milestones").rglob("*.json")):
        payload = load_json(path, {})
        if payload.get("schema_version") != "newrouge.milestone-change-plan.v1":
            continue
        if (str(payload.get("baseline_manifest") or "") != manifest_ref
            and (not revision or (payload.get("source_identity") or {}).get("source_revision") != revision)):
            continue
        if any(str(c.get("owner_task_id") or c.get("target_task_id")) == str(task_id)
               for c in payload.get("changes", []) if isinstance(c, dict)):
            plans.append(path)
    return plans


def check_task_obligations(root: Path, task_id: str) -> tuple[bool, str, dict[str, Any]]:
    """Fail closed without consulting transient planning run logs."""
    traces = [load_json(path, {}) for path in sorted((root / TRACE_ROOT).glob("*.json"))]
    handoff_paths = set()
    active = {}
    for trace in traces:
        ref = str(trace.get("applied_manifest_path") or "")
        if ref:
            path = repo_path(root, ref)
            if path.is_file() and file_sha(path) == trace.get("applied_manifest_sha256"):
                active[ref] = trace.get("applied_manifest_sha256")
    for trace in traces:
        ref = str(trace.get("applied_manifest_path") or "")
        if not ref:
            continue
        if ref in active and active[ref] != trace.get("applied_manifest_sha256"):
            continue  # A later applied cumulative plan owns this manifest.
        involved = {str(t) for f in (trace.get("manifest_candidate") or {}).get("flows", []) for t in f.get("task_ids", [])}
        if str(task_id) not in involved:
            continue
        path = repo_path(root, ref)
        if not path.is_file() or file_sha(path) != trace.get("applied_manifest_sha256"):
            return False, "mvg_applied_manifest_drift", trace
        binding = (trace.get("handoff_bindings") or {}).get(str(task_id), {})
        if binding.get("manifest_sha256") != trace.get("applied_manifest_sha256"):
            return False, "mvg_obligation_binding_required", trace
        from chapter5_semantic_reconciliation import load_task_readiness, readiness_path_for_task
        ok, _, reason = load_task_readiness(root, task_id)
        readiness = readiness_path_for_task(root, task_id)
        if not ok or file_sha(readiness) != binding.get("chapter5_readiness_sha256"):
            return False, "mvg_bound_readiness_stale:" + reason, trace
        plans = applicable_milestone_plans(root, task_id, ref)
        if binding.get("kind") == "ordinary":
            if plans:
                return False, "mvg_milestone_handoff_required", trace
        elif binding.get("kind") == "milestone":
            from milestone_incremental_handoff import validate_task_handoff
            handoff_path = repo_path(root, str(binding.get("path") or ""))
            if not handoff_path.is_file() or file_sha(handoff_path) != binding.get("sha256"):
                return False, "mvg_milestone_handoff_stale", trace
            ok, reason, handoff = validate_task_handoff(root, handoff_path, task_id)
            if not ok or handoff.get("baseline_manifest_sha256") != trace.get("applied_manifest_sha256"):
                return False, "mvg_milestone_handoff_invalid:" + reason, trace
            if plans and any(p.relative_to(root).as_posix() != binding.get("change_plan_path") for p in plans):
                return False, "mvg_milestone_scope_changed", trace
            handoff_paths.add(binding["path"])
        else:
            return False, "mvg_obligation_binding_invalid", trace
    return True, "current", {"milestone_handoff_paths": sorted(handoff_paths)}
