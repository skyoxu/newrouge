#!/usr/bin/env python3
"""Stage-true B-route planning page actions shared with the Project Health page and direct callers.

Actions: inspect (read-only), 3a_sources, 3b_capability, 3b_mvg, 3b_adoption, 3c_task_preview,
3c_task_compile and chapter6. 3A/3B run without Taskmaster Tasks or Chapter 5 readiness and never
accept draft/allow_unready bypasses; 3C requires a formally adopted 3B plan; chapter6 always uses the
Story 3.12 unified gate. --invocation-mode new starts a fresh 3B run; resume reuses an existing
recoverable run without resetting its budget.

Exit codes: 0 when the result is ok; 2 when blocked or arguments are invalid. The command never
writes Knowledge publication pointers and never performs an implicit global Knowledge refresh;
--report optionally writes one JSON file strictly under non-reserved logs/**. Automated page
results only prove the UI contract and never certify Godot gameplay or Reward pilot acceptance.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import json
from pathlib import Path

import _b_route_codec as codec
import _b_route_planning_page as page

REQUEST_FLAGS = ("stage", "scope_id", "plan_id", "flow_id", "capability_id", "task_id", "run_id", "operation_id",
                 "attempt_id", "audit_ref", "manifest", "source_set", "prepared", "candidate", "accounted",
                 "request_ref", "planning_contract", "prepared_ref", "planning_profile", "runner", "sub_action",
                 "recovery_target", "protection_ref", "change_intents", "expected_model", "completed_extraction_ref",
                 "citation_guidance")
INT_REQUEST_FLAGS = ("request_budget", "active_budget_seconds", "timeout_seconds")
FORBIDDEN_FLAGS = ("--allow-unready", "--allow-unready-draft", "--draft", "--skip-gate", "--reset-budget",
                   "--switch-task-origin", "--delete-b-origin", "--publish")


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise codec.CodecError(codec.Diagnostic(
            codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.TARGET, None,
            "--action " + "|".join(page.ACTIONS) + " with --mode " + "|".join(page.VALID_MODES), message, None))


def register_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--root", default=".", help="Explicit repository root (defaults to current directory)")
    parser.add_argument("--action", default="inspect", choices=list(page.ACTIONS),
                        help="Page action; inspect is read-only")
    parser.add_argument("--mode", default="workspace_preview", choices=list(page.VALID_MODES),
                        help="Snapshot identity aligned with Story 4.6")
    parser.add_argument("--invocation-mode", default=None, choices=list(page.INVOCATION_MODES),
                        help="3B only: new starts a fresh run; resume keeps the existing run budget")
    parser.add_argument("--recommendation-only", action="store_true", default=None,
                        help="Read-only recommendation (inspect, adoption inspect, chapter6 gate/route/resume)")
    parser.add_argument("--request-json", default=None,
                        help="Complete page request as a strict JSON object; excludes other request flags")
    for name in REQUEST_FLAGS:
        parser.add_argument("--" + name.replace("_", "-"), default=None, dest=name,
                            help=f"Optional page request field {name}")
    for name in INT_REQUEST_FLAGS:
        parser.add_argument("--" + name.replace("_", "-"), default=None, type=int, dest=name,
                            help=f"Optional 3A audit positive integer field {name}")
    parser.add_argument("--report", default=None,
                        help="Optional repository-relative non-reserved logs/**/*.json report path")
    parser.add_argument("--events-log", default=None, dest="events_log",
                        help="Optional repository-relative non-reserved logs/**/*.jsonl stage events log")
    return parser


def build_parser() -> argparse.ArgumentParser:
    return register_arguments(_Parser(description=__doc__, allow_abbrev=False,
                                      formatter_class=argparse.RawDescriptionHelpFormatter))


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":")))


def _failure(diagnostic: dict) -> dict:
    return {"schema_version": page.SCHEMA_VERSION, "ok": False, "status": "invalid_arguments",
            "reason_code": diagnostic["reason_code"], "diagnostics": [diagnostic], "runtime_verified": False,
            "ui_contract_only_not_godot_gameplay": True, "invariants": dict(page.INVARIANTS)}


def build_request(args: argparse.Namespace) -> dict:
    all_flags = REQUEST_FLAGS + INT_REQUEST_FLAGS
    if args.request_json is not None:
        used = [name for name in all_flags if getattr(args, name) is not None]
        if used or args.invocation_mode is not None or args.recommendation_only is not None:
            raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.CONFLICT, codec.Stage.CONTENT, used[0] if used else None,
                                                    "--request-json without other request flags", used, None))
        request = codec.strict_json_loads(args.request_json)
        if not isinstance(request, dict):
            raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.INVALID_TYPE, codec.Stage.CONTENT, None,
                                                    "JSON object request", type(request).__name__, None))
        return request
    request: dict = {"action": args.action, "mode": args.mode}
    if args.invocation_mode is not None:
        request["invocation_mode"] = args.invocation_mode
    if args.recommendation_only:
        request["recommendation_only"] = True
    for name in all_flags:
        value = getattr(args, name)
        if value is not None:
            request[name] = value
    return request


def main(argv=None) -> int:
    sys.dont_write_bytecode = True
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        for value in argv:
            if value.split("=", 1)[0] in FORBIDDEN_FLAGS:
                raise codec.CodecError(codec.Diagnostic(
                    codec.ReasonCode.CONFLICT, codec.Stage.CONTENT, value.split("=", 1)[0].removeprefix("--"),
                    "no gate bypass, budget reset or origin mutation flags", value, None))
        args = build_parser().parse_args(argv)
        if type(args.root) is not str or not args.root.strip():
            raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.PATH, None,
                                                    "nonempty repository root directory path", args.root, None))
        root = Path(args.root)
        request = build_request(args)
        result = page.execute_planning_page_action(root, request, events_log=args.events_log)
        if args.report is not None:
            path = page.write_page_report(root, args.report, result)
            result["report_path"] = path.relative_to(root.resolve()).as_posix()
    except codec.CodecError as err:
        _emit(_failure(err.diagnostic.to_dict()))
        return 2
    _emit(result)
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
