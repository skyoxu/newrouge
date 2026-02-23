#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract task obligations and check acceptance coverage via LLM.

Supports:
- multi-run consensus
- garbled-text precheck (optional hard fail)
- security profile hint (host-safe/strict)
- deterministic post-check to reduce omissions and jitter
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def _bootstrap_imports() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))


_bootstrap_imports()

from _garbled_gate import parse_task_ids_csv, render_top_hits, scan_task_text_integrity  # noqa: E402
from _obligations_guard import (  # noqa: E402
    apply_deterministic_guards,
    build_obligation_prompt,
    normalize_model_status,
    pick_consensus_verdict,
    render_obligations_report,
    safe_prompt_truncate,
)
from _security_profile import build_security_profile_context, resolve_security_profile  # noqa: E402
from _taskmaster import resolve_triplet  # noqa: E402
from _util import ci_dir, repo_root, write_json, write_text  # noqa: E402


def _run_codex_exec(*, prompt: str, out_last_message: Path, timeout_sec: int) -> tuple[int, str, list[str]]:
    exe = shutil.which("codex")
    if not exe:
        return 127, "codex executable not found in PATH\n", ["codex"]
    cmd = [
        exe,
        "exec",
        "-s",
        "read-only",
        "-C",
        str(repo_root()),
        "--output-last-message",
        str(out_last_message),
        "-",
    ]
    try:
        proc = subprocess.run(
            cmd,
            input=prompt,
            text=True,
            encoding="utf-8",
            errors="ignore",
            cwd=str(repo_root()),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        return 124, "codex exec timeout\n", cmd
    except Exception as exc:  # noqa: BLE001
        return 1, f"codex exec failed to start: {exc}\n", cmd
    return proc.returncode or 0, proc.stdout or "", cmd


def _extract_json_object(text: str) -> dict[str, Any]:
    payload = str(text or "").strip()
    try:
        obj = json.loads(payload)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass
    match = re.search(r"\{.*\}", payload, flags=re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model output.")
    obj = json.loads(match.group(0))
    if not isinstance(obj, dict):
        raise ValueError("Model output JSON is not an object.")
    return obj


def _truncate(text: str, *, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


def _normalize_subtasks(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        sid = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        details = str(item.get("details") or "").strip()
        test_strategy = str(item.get("testStrategy") or "").strip()
        if not sid or not title:
            continue
        details = _truncate(re.sub(r"\s+", " ", details).strip(), max_chars=520) if details else ""
        test_strategy = _truncate(re.sub(r"\s+", " ", test_strategy).strip(), max_chars=320) if test_strategy else ""
        out.append(
            {
                "id": sid,
                "title": title,
                "details": details,
                "testStrategy": test_strategy,
            }
        )
    return out


def _is_view_present(view: dict[str, Any] | None) -> bool:
    return isinstance(view, dict) and isinstance(view.get("acceptance"), list)


def _build_source_text_blocks(
    *,
    title: str,
    details: str,
    test_strategy: str,
    subtasks: list[dict[str, str]],
) -> list[str]:
    """Build deterministic source corpus for source_excerpt checks.

    Guardrail: master.title must be present and kept as the first source block.
    """

    title_text = str(title or "").strip()
    if not title_text:
        raise ValueError("master.title is required in source_blocks")

    blocks: list[str] = [title_text, str(details or ""), str(test_strategy or "")]
    for item in subtasks:
        blocks.append(str(item.get("title") or ""))
        blocks.append(str(item.get("details") or ""))
        blocks.append(str(item.get("testStrategy") or ""))

    if not str(blocks[0] or "").strip():
        raise ValueError("source_blocks[0] must be non-empty master.title")
    return blocks


def _collect_auto_escalation_reasons(run_results: list[dict[str, Any]], *, force_task: bool) -> list[str]:
    reasons: list[str] = []
    if force_task:
        reasons.append("forced_task")

    has_fail_vote = any(str(item.get("status") or "").strip().lower() != "ok" for item in run_results)
    if has_fail_vote:
        reasons.append("fail_vote")

    has_timeout = any(int(item.get("rc") or 0) == 124 for item in run_results)
    if has_timeout:
        reasons.append("timeout")

    has_invalid_json = any(str(item.get("error") or "").startswith("invalid_json") for item in run_results)
    if has_invalid_json:
        reasons.append("invalid_json")

    has_exec_or_empty = any(str(item.get("error") or "") == "codex_exec_failed_or_empty" for item in run_results)
    if has_exec_or_empty:
        reasons.append("exec_or_empty")

    ok_votes = sum(1 for item in run_results if str(item.get("status") or "").strip().lower() == "ok")
    fail_votes = len(run_results) - ok_votes
    if ok_votes > 0 and fail_votes > 0:
        reasons.append("jitter")

    seen: set[str] = set()
    out: list[str] = []
    for raw in reasons:
        value = str(raw or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="sc-llm-extract-task-obligations (obligations vs acceptance coverage)")
    parser.add_argument("--task-id", default=None, help="Taskmaster id (e.g. 17). Default: first status=in-progress task.")
    parser.add_argument("--timeout-sec", type=int, default=360, help="codex exec timeout in seconds (default: 360).")
    parser.add_argument("--max-prompt-chars", type=int, default=80_000, help="Max prompt size (default: 80000).")
    parser.add_argument("--consensus-runs", type=int, default=1, help="Run N baseline rounds and use majority status (default: 1).")
    parser.add_argument("--min-obligations", type=int, default=0, help="Deterministic hard gate: minimum obligations count (default: 0).")
    parser.add_argument("--round-id", default="", help="Optional run id suffix for output directory isolation.")
    parser.add_argument("--security-profile", default=None, choices=["strict", "host-safe"], help="Security review profile (default: env SECURITY_PROFILE or host-safe).")
    parser.add_argument("--garbled-gate", default="on", choices=["on", "off"], help="Run garbled-text precheck before LLM (default: on).")
    parser.add_argument("--auto-escalate", default="on", choices=["on", "off"], help="Auto escalate failed/unstable runs to --escalate-max-runs (default: on).")
    parser.add_argument("--escalate-max-runs", type=int, default=3, help="Max runs when auto escalation is triggered (default: 3).")
    parser.add_argument("--escalate-task-ids", default="", help="CSV task ids to force escalation to max runs (e.g. 2,12).")
    args = parser.parse_args()

    try:
        triplet = resolve_triplet(task_id=str(args.task_id) if args.task_id else None)
    except Exception as exc:  # noqa: BLE001
        print(f"SC_LLM_OBLIGATIONS status=fail error=resolve_triplet_failed exc={exc}")
        return 2

    out_dir_name = f"sc-llm-obligations-task-{triplet.task_id}"
    if str(args.round_id or "").strip():
        out_dir_name += f"-round-{str(args.round_id).strip()}"
    out_dir = ci_dir(out_dir_name)

    title = str(triplet.master.get("title") or "").strip()
    details = str(triplet.master.get("details") or "").strip()
    test_strategy = str(triplet.master.get("testStrategy") or "").strip()
    subtasks = _normalize_subtasks(triplet.master.get("subtasks"))

    acceptance_by_view: dict[str, list[Any]] = {}
    if _is_view_present(triplet.back):
        acceptance_by_view["back"] = list((triplet.back or {}).get("acceptance") or [])
    if _is_view_present(triplet.gameplay):
        acceptance_by_view["gameplay"] = list((triplet.gameplay or {}).get("acceptance") or [])

    security_profile = resolve_security_profile(args.security_profile)
    security_profile_context = build_security_profile_context(security_profile)

    summary: dict[str, Any] = {
        "cmd": "sc-llm-extract-task-obligations",
        "task_id": triplet.task_id,
        "title": title,
        "status": None,
        "subtasks_total": len(subtasks),
        "views_present": sorted(acceptance_by_view.keys()),
        "security_profile": security_profile,
        "garbled_gate": str(args.garbled_gate),
        "auto_escalate": str(args.auto_escalate),
        "out_dir": str(out_dir.relative_to(repo_root())).replace("\\", "/"),
        "error": None,
    }

    if str(args.garbled_gate).strip().lower() != "off":
        task_filter: set[int] = set()
        try:
            task_filter.add(int(triplet.task_id))
        except (TypeError, ValueError):
            pass
        precheck = scan_task_text_integrity(task_ids=(task_filter or None))
        write_json(out_dir / "garbled-precheck.json", precheck)
        pre_summary = precheck.get("summary") if isinstance(precheck, dict) else {}
        hits = int((pre_summary or {}).get("suspicious_hits") or 0)
        decode_errors = int((pre_summary or {}).get("decode_errors") or 0)
        parse_errors = int((pre_summary or {}).get("parse_errors") or 0)
        summary["garbled_precheck"] = pre_summary
        if decode_errors > 0 or parse_errors > 0 or hits > 0:
            top_hits = render_top_hits(precheck, limit=8) if isinstance(precheck, dict) else []
            summary["status"] = "fail"
            summary["error"] = "garbled_precheck_failed"
            summary["garbled_top_hits"] = top_hits
            write_json(out_dir / "summary.json", summary)
            report_lines = [
                "# sc-llm-extract-task-obligations report",
                "",
                f"- task_id: {triplet.task_id}",
                "- status: fail",
                "- reason: garbled_precheck_failed",
                f"- suspicious_hits: {hits}",
                f"- decode_errors: {decode_errors}",
                f"- parse_errors: {parse_errors}",
                "",
                "## Top Hits",
                "",
            ]
            report_lines.extend([f"- {line}" for line in top_hits] or ["- (none)"])
            write_text(out_dir / "report.md", "\n".join(report_lines).strip() + "\n")
            write_json(out_dir / "verdict.json", {"task_id": str(triplet.task_id), "status": "fail", "obligations": []})
            print(f"SC_LLM_OBLIGATIONS status=fail reason=garbled_precheck_failed out={out_dir}")
            return 1

    if not acceptance_by_view:
        summary["status"] = "fail"
        summary["error"] = "no_views_present"
        write_json(out_dir / "summary.json", summary)
        write_json(out_dir / "verdict.json", {"task_id": str(triplet.task_id), "status": "fail", "obligations": []})
        write_text(out_dir / "report.md", "# sc-llm-extract-task-obligations report\n\n- status: fail\n- reason: no_views_present\n")
        print(f"SC_LLM_OBLIGATIONS status=fail reason=no_views_present out={out_dir}")
        return 1

    prompt = build_obligation_prompt(
        task_id=str(triplet.task_id),
        title=title,
        master_details=details,
        master_test_strategy=test_strategy,
        subtasks=subtasks,
        acceptance_by_view=acceptance_by_view,
        security_profile=security_profile,
        security_profile_context=security_profile_context,
    )
    prompt = safe_prompt_truncate(prompt, max_chars=int(args.max_prompt_chars))
    write_text(out_dir / "prompt.md", prompt)

    configured_runs = max(1, int(args.consensus_runs))
    max_runs = max(configured_runs, int(args.escalate_max_runs))
    auto_escalate_enabled = str(args.auto_escalate).strip().lower() != "off"
    force_ids = parse_task_ids_csv(args.escalate_task_ids)
    force_for_task = False
    try:
        force_for_task = int(triplet.task_id) in force_ids
    except (TypeError, ValueError):
        force_for_task = False
    target_runs = configured_runs
    auto_escalate_triggered = False
    auto_escalate_reasons: list[str] = []

    run_results: list[dict[str, Any]] = []
    run_verdicts: list[dict[str, Any]] = []
    cmd_ref: list[str] | None = None

    run = 1
    while run <= target_runs:
        run_last = out_dir / f"output-last-message-run-{run:02d}.txt"
        run_trace = out_dir / f"trace-run-{run:02d}.log"
        rc, trace, cmd = _run_codex_exec(prompt=prompt, out_last_message=run_last, timeout_sec=int(args.timeout_sec))
        write_text(run_trace, trace)
        if cmd_ref is None:
            cmd_ref = cmd
        last_message = run_last.read_text(encoding="utf-8", errors="ignore") if run_last.exists() else ""
        parsed: dict[str, Any] | None = None
        err: str | None = None
        if rc != 0 or not last_message.strip():
            err = "codex_exec_failed_or_empty"
        else:
            try:
                parsed = _extract_json_object(last_message)
            except Exception as exc:  # noqa: BLE001
                err = f"invalid_json:{exc}"
        run_status = normalize_model_status((parsed or {}).get("status")) if parsed else "fail"
        run_results.append({"run": run, "rc": rc, "status": run_status, "error": err})
        if parsed:
            run_verdicts.append({"run": run, "status": run_status, "obj": parsed})
            write_json(out_dir / f"verdict-run-{run:02d}.json", parsed)
        run += 1

        if run > target_runs and auto_escalate_enabled and target_runs < max_runs:
            reasons = _collect_auto_escalation_reasons(run_results, force_task=force_for_task)
            if reasons:
                target_runs = max_runs
                auto_escalate_triggered = True
                auto_escalate_reasons = reasons

    ok_votes = sum(1 for item in run_results if item["status"] == "ok")
    fail_votes = len(run_results) - ok_votes
    status = "ok" if ok_votes > fail_votes else "fail"
    selected = pick_consensus_verdict(run_verdicts, target_status=status)
    obj: dict[str, Any] = dict((selected or {}).get("obj") or {"task_id": str(triplet.task_id), "status": "fail", "obligations": []})
    obj["task_id"] = str(triplet.task_id)
    obj["status"] = status

    try:
        source_blocks = _build_source_text_blocks(
            title=title,
            details=details,
            test_strategy=test_strategy,
            subtasks=subtasks,
        )
    except ValueError as exc:
        summary["status"] = "fail"
        summary["error"] = "source_blocks_missing_title"
        summary["deterministic_issues"] = [f"DET_SOURCE_BLOCKS:{exc}"]
        write_json(out_dir / "summary.json", summary)
        write_json(out_dir / "verdict.json", {"task_id": str(triplet.task_id), "status": "fail", "obligations": []})
        write_text(
            out_dir / "report.md",
            "# sc-llm-extract-task-obligations report\n\n- status: fail\n- reason: source_blocks_missing_title\n",
        )
        print(f"SC_LLM_OBLIGATIONS status=fail reason=source_blocks_missing_title out={out_dir}")
        return 1

    obj, det_issues, hard_uncovered, advisory_uncovered = apply_deterministic_guards(
        obj=obj,
        subtasks=subtasks,
        min_obligations=int(args.min_obligations),
        source_text_blocks=source_blocks,
        security_profile=security_profile,
    )
    status = normalize_model_status(obj.get("status"))

    summary["rc"] = 0 if run_verdicts else 1
    summary["cmdline"] = cmd_ref or []
    summary["consensus_runs"] = len(run_results)
    summary["consensus_runs_configured"] = configured_runs
    summary["consensus_votes"] = {"ok": ok_votes, "fail": fail_votes}
    summary["run_results"] = run_results
    summary["auto_escalate"] = {
        "enabled": auto_escalate_enabled,
        "triggered": auto_escalate_triggered,
        "max_runs": max_runs,
        "force_for_task": force_for_task,
        "reasons": auto_escalate_reasons,
    }
    summary["selected_run"] = int((selected or {}).get("run") or 0)
    summary["deterministic_issues"] = det_issues
    summary["hard_uncovered_count"] = len(hard_uncovered)
    summary["advisory_uncovered_count"] = len(advisory_uncovered)
    summary["status"] = status
    if not run_verdicts:
        summary["error"] = "all_runs_failed_or_invalid"

    write_json(out_dir / "summary.json", summary)
    write_json(out_dir / "verdict.json", obj)
    write_text(out_dir / "report.md", render_obligations_report(obj))
    write_text(out_dir / "output-last-message.txt", json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    write_text(
        out_dir / "trace.log",
        (
            f"consensus_runs={len(run_results)}\n"
            f"consensus_runs_configured={configured_runs}\n"
            f"ok_votes={ok_votes}\n"
            f"fail_votes={fail_votes}\n"
            f"selected_run={summary['selected_run']}\n"
            f"security_profile={security_profile}\n"
            f"auto_escalate_enabled={auto_escalate_enabled}\n"
            f"auto_escalate_triggered={auto_escalate_triggered}\n"
            f"auto_escalate_reasons={','.join(auto_escalate_reasons)}\n"
        ),
    )

    ok = status == "ok"
    print(f"SC_LLM_OBLIGATIONS status={'ok' if ok else 'fail'} out={out_dir}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
