from __future__ import annotations

from pathlib import Path
from typing import Any

from _overlay_candidate_store import overlay_dir, resolve_candidate_pages, verify_inputs
from _overlay_generator_diff import build_diff_summary, render_diff_summary_markdown
from _overlay_generator_runtime import write_verified_pages
from _overlay_generator_support import compare_overlay_dirs, normalize_relpath, write_json, write_text


def apply_candidate_pages(
    *, repo_root: Path, out_dir: Path, context: dict[str, Any], pages: list[str], candidate_from: str = "",
) -> dict[str, Any]:
    if not pages:
        raise ValueError("No selected candidate pages")
    resolved = resolve_candidate_pages(repo_root=repo_root, context=context, pages=pages, candidate_from=candidate_from)
    write_json(out_dir / "inputs.json", {**context, "selected_pages": pages, "mode": "apply", "candidate_from": candidate_from})
    target = overlay_dir(repo_root, context["prd_id"])
    generated = out_dir / "applied-candidate" / context["prd_id"] / "08"
    generated.mkdir(parents=True, exist_ok=True)
    for name, item in resolved.items():
        (generated / name).write_bytes(item["content"])
    scope = set(pages)
    diff_summary = build_diff_summary(generated, target, include_filenames=scope)
    comparison = compare_overlay_dirs(generated, target, include_filenames=scope)
    write_json(out_dir / "diff-summary.json", diff_summary)
    write_text(out_dir / "diff-summary.md", render_diff_summary_markdown(diff_summary))
    verify_inputs(repo_root, context)
    write_verified_pages(target, {name: item["content"] for name, item in resolved.items()},
                         {name: item["original"] for name, item in resolved.items()})
    diff_files = {item["filename"]: item for item in diff_summary["files"]}
    results = [{
        "page": name, "filename": name, "rc": 0, "child_status": "ok", "child_mode": "apply",
        "failure_type": "", "child_error": "", "diff_status": diff_files[name]["status"],
        "similarity_ratio": diff_files[name]["similarity_ratio"],
        **{key: item[key] for key in ("candidate_manifest_path", "candidate_manifest_sha256")},
    } for name, item in resolved.items()]
    summary = {
        "status": "ok", "mode": "apply", "prd_id": context["prd_id"], "page_mode": context["page_mode"],
        "selected_pages": pages, "page_count": len(pages), "success_count": len(pages), "failure_count": 0,
        "model_executed": False, "results": results, "page_runs": results,
        "generated_dir": normalize_relpath(generated, root=repo_root),
        "existing_overlay_dir": normalize_relpath(target, root=repo_root),
        "applied_to": normalize_relpath(target, root=repo_root), "comparison": comparison,
        "diff_summary_path": normalize_relpath(out_dir / "diff-summary.json", root=repo_root),
        "diff_markdown_path": normalize_relpath(out_dir / "diff-summary.md", root=repo_root),
        "diff_counts": {key: diff_summary[key] for key in ("unchanged_count", "modified_count", "added_count", "removed_count")},
    }
    write_json(out_dir / "summary.json", summary)
    write_text(out_dir / "report.md", render_diff_summary_markdown(diff_summary))
    return summary


def run_candidate_apply(
    *, repo_root: Path, out_dir: Path, context: dict[str, Any], pages: list[str], candidate_from: str, label: str,
) -> int:
    try:
        apply_candidate_pages(repo_root=repo_root, out_dir=out_dir, context=context, pages=pages, candidate_from=candidate_from)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        write_json(out_dir / "summary.json", {
            "status": "fail", "mode": "apply", "error": "candidate_apply_blocked", "detail": str(exc),
            "prd_id": context["prd_id"], "selected_pages": pages, "model_executed": False,
            "page_count": len(pages), "success_count": 0, "failure_count": len(pages),
            "next_action": "Run simulate for the affected pages, review the saved candidates, then apply that run.",
        })
        print(f"{label} status=fail error=candidate_apply_blocked detail={exc} out={out_dir}")
        return 1
    print(f"{label} status=ok mode=apply pages={len(pages)} model_executed=false out={out_dir}")
    return 0
