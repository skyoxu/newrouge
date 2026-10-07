#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _overlay_generator_diff import build_diff_summary, render_diff_summary_markdown
from _overlay_generator_prompting import (
    build_overlay_page_patch_prompt,
    build_overlay_page_prompt,
)
from _overlay_generator_runtime import (
    artifact_name as _artifact_name,
    prepare_page_runtime_state as _prepare_page_runtime_state,
    reset_dir as _reset_dir,
    select_pages as _select_pages,
    reserve_output_dir,
)
from _overlay_generator_scaffold import select_pages_by_family
from _overlay_generator_scaffold_prompting import (
    build_overlay_page_scaffold_prompt,
)
from _overlay_generator_support import (
    build_default_overlay_profile,
    build_task_digest,
    compare_overlay_dirs,
    discover_companion_docs,
    discover_existing_overlay_profile,
    infer_prd_id,
    load_task_payloads,
    normalize_relpath,
    parse_prd_docs_csv,
    read_text,
    validate_required_prd_docs,
    write_json,
    write_text,
)
from _overlay_candidate_store import build_candidate_inputs, invalidate_default_candidate, save_candidate
from _overlay_candidate_apply import run_candidate_apply
from _overlay_generator_execution import generate_pages
from _util import ci_dir, repo_root


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate/update overlay docs from a PRD and fixed task triplet using codex exec.")
    parser.add_argument("--prd", required=True, help="Primary PRD markdown path.")
    parser.add_argument("--prd-id", default="", help="Overlay PRD-ID. If omitted, infer from task overlay refs.")
    parser.add_argument(
        "--prd-docs",
        default="",
        help="Additional PRD markdown paths, comma-separated. Example: PRD_V3_TRACEABILITY_MATRIX.md,PRD_V3_RULES_FREEZE.md",
    )
    parser.add_argument("--timeout-sec", type=int, default=900, help="codex exec timeout in seconds.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Validate inputs and emit prompt/artifacts without calling codex.")
    mode.add_argument("--apply", action="store_true", help="Apply saved simulate candidates without running the model.")
    parser.add_argument("--candidate-from", default="", help="Optional simulate run/batch directory. Otherwise use its recorded candidate pointers.")
    parser.add_argument("--page-filter", default="", help="Optional comma-separated overlay filenames to generate, e.g. _index.md,ACCEPTANCE_CHECKLIST.md")
    parser.add_argument(
        "--page-family",
        default="all",
        choices=["all", "core", "contracts", "feature", "governance", "routing"],
        help="Optional page family selector applied before --page-filter.",
    )
    parser.add_argument(
        "--page-mode",
        default="scaffold",
        choices=["scaffold", "patch", "replace"],
        help="Single-page generation mode. Default: scaffold.",
    )
    parser.add_argument("--run-suffix", default="", help="Optional log directory suffix. If omitted, generate a unique run suffix.")
    return parser


def _default_run_suffix() -> str:
    from _overlay_generator_runtime import default_run_suffix

    return default_run_suffix()


def _build_output_dir_name(prd_id: str, run_suffix: str) -> str:
    from _overlay_generator_runtime import build_output_dir_name

    return build_output_dir_name(prd_id, run_suffix, default_suffix=_default_run_suffix())


def main() -> int:
    args = _build_parser().parse_args()
    if args.candidate_from and not args.apply:
        print("SC_LLM_OVERLAY_GEN status=fail error=candidate_from_requires_apply")
        return 2
    root = repo_root()
    prd_path = Path(args.prd)
    if not prd_path.is_absolute():
        prd_path = (root / prd_path).resolve()
    if not prd_path.exists():
        print(f"SC_LLM_OVERLAY_GEN status=fail error=prd_not_found path={prd_path}")
        return 2

    tasks_json, tasks_back, tasks_gameplay = load_task_payloads(root)
    prd_id = infer_prd_id(args.prd_id, tasks_json, tasks_back, tasks_gameplay)
    out_dir = reserve_output_dir(ci_dir(_build_output_dir_name(prd_id, args.run_suffix)))

    companion_paths = discover_companion_docs(
        prd_path,
        repo_root=root,
        explicit_paths=parse_prd_docs_csv(args.prd_docs),
    )
    missing_required_docs = validate_required_prd_docs(
        prd_id=prd_id,
        companion_paths=companion_paths,
        expected_doc_names=parse_prd_docs_csv(args.prd_docs),
    )
    if missing_required_docs:
        write_json(
            out_dir / "summary.json",
            {
                "status": "fail",
                "error": "missing_required_prd_docs",
                "prd_id": prd_id,
                "missing_required_prd_docs": missing_required_docs,
            },
        )
        print(
            "SC_LLM_OVERLAY_GEN status=fail error=missing_required_prd_docs "
            f"prd_id={prd_id} missing={','.join(missing_required_docs)} out={out_dir}"
        )
        return 2

    candidate_context = build_candidate_inputs(
        repo_root=root, prd_path=prd_path, companion_paths=companion_paths, prd_id=prd_id, page_mode=args.page_mode,
    )
    tasks_json, tasks_back, tasks_gameplay = load_task_payloads(root)
    companion_docs = [
        {
            "path": normalize_relpath(path, root=root),
            "excerpt": read_text(path),
        }
        for path in companion_paths
    ]

    profile = discover_existing_overlay_profile(root, prd_id)
    profile_locked = bool(profile)
    if not profile:
        profile = build_default_overlay_profile(prd_id)
    selected_pages = select_pages_by_family(profile, args.page_family)
    selected_pages = _select_pages(selected_pages, args.page_filter)
    if not selected_pages:
        write_json(
            out_dir / "summary.json",
            {
                "status": "fail",
                "error": "page_filter_matched_nothing",
                "prd_id": prd_id,
                "page_filter": args.page_filter,
            },
        )
        print(f"SC_LLM_OVERLAY_GEN status=fail error=page_filter_matched_nothing prd_id={prd_id} out={out_dir}")
        return 2

    if args.apply:
        return run_candidate_apply(
            repo_root=root, out_dir=out_dir, context=candidate_context,
            pages=[str(page['filename']) for page in selected_pages], candidate_from=args.candidate_from,
            label="SC_LLM_OVERLAY_GEN",
        )
    task_digest = build_task_digest(prd_id, tasks_json, tasks_back, tasks_gameplay)
    prd_text = read_text(prd_path)
    prompts_dir = out_dir / "page-prompts"
    _reset_dir(prompts_dir)
    current_dir = root / "docs" / "architecture" / "overlays" / prd_id / "08"
    base_files = {
        str(page['filename']): (current_dir / str(page['filename'])).read_bytes()
        if (current_dir / str(page['filename'])).exists() else None
        for page in selected_pages
    }
    page_state = _prepare_page_runtime_state(
        selected_pages=selected_pages,
        current_dir=current_dir,
        task_digest=task_digest,
    )
    page_prompts: list[dict[str, object]] = []
    for page in selected_pages:
        filename = str(page.get("filename") or "")
        state = page_state.get(filename) or {}
        current_page_path = state.get("current_page_path") or (current_dir / filename)
        current_page_text = str(state.get("current_page_text") or "")
        page_context = dict(state.get("page_context") or {})
        scaffold_base_page = dict(state.get("scaffold_base_page") or {})
        try:
            if args.page_mode == "scaffold":
                prompt = build_overlay_page_scaffold_prompt(
                    prd_path=prd_path,
                    prd_text=prd_text,
                    prd_id=prd_id,
                    companion_docs=companion_docs,
                    page=page,
                    page_context=page_context,
                    base_page=scaffold_base_page,
                    current_page_text=current_page_text,
                )
            elif args.page_mode == "patch":
                prompt = build_overlay_page_patch_prompt(
                    prd_path=prd_path,
                    prd_text=prd_text,
                    prd_id=prd_id,
                    companion_docs=companion_docs,
                    page=page,
                    page_context=page_context,
                    current_page_text=current_page_text,
                )
            else:
                prompt = build_overlay_page_prompt(
                    prd_path=prd_path,
                    prd_text=prd_text,
                    prd_id=prd_id,
                    companion_docs=companion_docs,
                    page=page,
                    page_context=page_context,
                    current_page_text=current_page_text,
                )
        except ValueError as exc:
            write_json(out_dir / "summary.json", {"status": "fail", "error": "page_source_context_incomplete", "failed_page": filename, "detail": str(exc)})
            print(f"SC_LLM_OVERLAY_GEN status=fail error=page_source_context_incomplete page={filename} detail={exc}")
            return 2
        prompt_path = prompts_dir / f"{_artifact_name(filename)}.prompt.md"
        write_text(prompt_path, prompt)
        page_prompts.append(
            {
                "filename": filename,
                "prompt_path": normalize_relpath(prompt_path, root=root),
                "current_page_exists": current_page_path.exists(),
                "page_mode": args.page_mode,
            }
        )
    write_json(
        out_dir / "inputs.json",
        {
            "prd_path": normalize_relpath(prd_path, root=root),
            "prd_id": prd_id,
            "mode": "dry-run" if args.dry_run else ("apply" if args.apply else "simulate"),
            "profile_locked": profile_locked,
            "companion_docs": [item["path"] for item in companion_docs],
            "profile": profile,
            "selected_pages": [str(page.get("filename") or "") for page in selected_pages],
            "page_prompts": page_prompts,
            "page_family": args.page_family,
            "page_mode": args.page_mode,
        },
    )

    if args.dry_run:
        summary = {
            "status": "ok",
            "mode": "dry-run",
            "prd_id": prd_id,
            "profile_locked": profile_locked,
            "companion_docs": [item["path"] for item in companion_docs],
            "profile_page_count": len(profile),
            "selected_page_count": len(selected_pages),
            "task_cluster_count": len(task_digest.get("overlay_clusters") or []),
            "page_prompt_dir": normalize_relpath(prompts_dir, root=root),
            "page_family": args.page_family,
            "page_mode": args.page_mode,
        }
        write_json(out_dir / "summary.json", summary)
        write_text(out_dir / "report.md", json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        print(f"SC_LLM_OVERLAY_GEN status=ok mode=dry-run prd_id={prd_id} out={out_dir}")
        return 0

    invalidate_default_candidate(root, candidate_context, [str(page['filename']) for page in selected_pages])
    generated = generate_pages(
        root=root, out_dir=out_dir, prd_id=prd_id, selected_pages=selected_pages,
        page_state=page_state, prompts_dir=prompts_dir, page_mode=args.page_mode, timeout_sec=int(args.timeout_sec),
    )
    if generated is None:
        return 1
    generated_dir, run_records = generated
    existing_dir = current_dir
    diff_scope = {str(page.get("filename") or "") for page in selected_pages}
    comparison = compare_overlay_dirs(generated_dir, existing_dir, include_filenames=diff_scope)
    diff_summary = build_diff_summary(generated_dir, existing_dir, include_filenames=diff_scope)
    write_json(out_dir / "diff-summary.json", diff_summary)
    write_text(out_dir / "diff-summary.md", render_diff_summary_markdown(diff_summary))
    summary = {
        "status": "ok",
        "mode": "simulate",
        "prd_id": prd_id,
        "generated_dir": normalize_relpath(generated_dir, root=root),
        "existing_overlay_dir": normalize_relpath(existing_dir, root=root) if existing_dir.exists() else "",
        "profile_locked": profile_locked,
        "page_family": args.page_family,
        "page_mode": args.page_mode,
        "selected_pages": [str(page.get("filename") or "") for page in selected_pages],
        "page_runs": run_records,
        "comparison": comparison,
        "diff_summary_path": normalize_relpath(out_dir / "diff-summary.json", root=root),
        "diff_markdown_path": normalize_relpath(out_dir / "diff-summary.md", root=root),
        "diff_counts": {
            "unchanged_count": diff_summary["unchanged_count"],
            "modified_count": diff_summary["modified_count"],
            "added_count": diff_summary["added_count"],
            "removed_count": diff_summary["removed_count"],
        },
    }

    try:
        summary.update(save_candidate(
            repo_root=root, out_dir=out_dir, context=candidate_context,
            base_files=base_files, generated_dir=generated_dir,
        ))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        write_json(out_dir / "summary.json", {"status": "fail", "error": "candidate_save_blocked", "detail": str(exc)})
        print(f"SC_LLM_OVERLAY_GEN status=fail error=candidate_save_blocked detail={exc} out={out_dir}")
        return 1

    write_json(out_dir / "summary.json", summary)
    write_text(out_dir / "report.md", json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(
        "SC_LLM_OVERLAY_GEN status=ok "
        f"mode=simulate prd_id={prd_id} "
        f"generated={generated_dir} overlap={comparison['filename_overlap']}/{comparison['existing_count']} out={out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
