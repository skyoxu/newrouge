from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from _overlay_generator_markdown_patch import apply_scaffold_update_to_existing_markdown
from _overlay_generator_patch import build_base_page_from_profile, merge_page_patch
from _overlay_generator_prompting import parse_and_validate_page, parse_and_validate_page_patch, run_codex_exec
from _overlay_generator_runtime import artifact_name as _artifact_name, reset_dir as _reset_dir
from _overlay_generator_scaffold import merge_scaffold_update
from _overlay_generator_scaffold_prompting import parse_and_validate_scaffold_update
from _overlay_generator_support import normalize_relpath, read_text, render_page_markdown, write_json, write_text


def generate_pages(
    *, root: Path, out_dir: Path, prd_id: str, selected_pages: list[dict[str, Any]],
    page_state: dict[str, dict[str, Any]], prompts_dir: Path, page_mode: str, timeout_sec: int,
) -> tuple[Path, list[dict[str, Any]]] | None:
    generated_dir = out_dir / "generated" / prd_id / "08"
    _reset_dir(generated_dir)
    run_records: list[dict[str, object]] = []
    raw_dir = out_dir / "page-outputs"
    trace_dir = out_dir / "page-traces"
    meta_dir = out_dir / "page-meta"
    _reset_dir(raw_dir)
    _reset_dir(trace_dir)
    _reset_dir(meta_dir)
    for page in selected_pages:
        filename = str(page.get("filename") or "")
        state = page_state.get(filename) or {}
        current_page_text = str(state.get("current_page_text") or "")
        page_context = dict(state.get("page_context") or {})
        artifact = _artifact_name(filename)
        prompt_path = prompts_dir / f"{artifact}.prompt.md"
        last_message_path = raw_dir / f"{artifact}.output.json"
        rc, trace_out, cmd = run_codex_exec(
            repo_root=root,
            prompt=read_text(prompt_path),
            out_last_message=last_message_path,
            timeout_sec=timeout_sec,
        )
        write_text(trace_dir / f"{artifact}.trace.log", trace_out)
        write_json(meta_dir / f"{artifact}.meta.json", {"cmd": cmd, "rc": rc, "filename": filename})

        if rc != 0 or not last_message_path.exists():
            write_json(
                out_dir / "summary.json",
                {
                    "status": "fail",
                    "error": "codex_exec_failed",
                    "prd_id": prd_id,
                    "failed_page": filename,
                    "rc": rc,
                },
            )
            print(f"SC_LLM_OVERLAY_GEN status=fail error=codex_exec_failed page={filename} rc={rc} out={out_dir}")
            return None

        try:
            raw_output = read_text(last_message_path)
            output_markdown = ""
            if page_mode == "scaffold":
                scaffold_update = parse_and_validate_scaffold_update(
                    raw_output=raw_output,
                    expected_filename=filename,
                )
                base_page = dict(state.get("scaffold_base_page") or {})
                parsed_page = merge_scaffold_update(base_page, scaffold_update)
                if current_page_text.strip():
                    scaffold_update = dict(scaffold_update)
                    scaffold_update["strict_incremental_patch"] = True
                    scaffold_update["expected_sha256"] = (
                        "sha256:" + hashlib.sha256(current_page_text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")).hexdigest()
                    )
                    output_markdown = apply_scaffold_update_to_existing_markdown(
                        current_markdown=current_page_text,
                        scaffold_update=scaffold_update,
                    )
            elif page_mode == "patch":
                patch_payload = parse_and_validate_page_patch(
                    raw_output=raw_output,
                    expected_filename=filename,
                )
                base_page = build_base_page_from_profile(page, page_context)
                parsed_page = merge_page_patch(base_page, patch_payload)
            else:
                parsed_page = parse_and_validate_page(
                    raw_output=raw_output,
                    expected_filename=filename,
                    expected_page_kind=str(page.get("page_kind") or ""),
                )
        except Exception as exc:  # noqa: BLE001
            write_text(out_dir / f"{artifact}.page-error.txt", str(exc) + "\n")
            write_json(
                out_dir / "summary.json",
                {
                    "status": "fail",
                    "error": "invalid_page_output",
                    "prd_id": prd_id,
                    "failed_page": filename,
                    "detail": str(exc),
                },
            )
            print(f"SC_LLM_OVERLAY_GEN status=fail error=invalid_page_output page={filename} out={out_dir}")
            return None

        if not output_markdown:
            output_markdown = render_page_markdown(parsed_page, prd_id=prd_id)
        write_text(generated_dir / filename, output_markdown)
        run_records.append(
            {
                "filename": filename,
                "prompt_path": normalize_relpath(prompt_path, root=root),
                "output_path": normalize_relpath(last_message_path, root=root),
            }
        )

    return generated_dir, run_records
