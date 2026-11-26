#!/usr/bin/env python3
"""Read-only B-route process observability & unified diagnostics CLI (Story 4.8).

Aggregates stage events across 3A, 3B, 3C, Chapter 4-7, Flow/MVG runner, completion
verdicts, and rework logs along 5 axes (operation/run, scope/flow, stage, attempt,
canonical event_id) with strict single-counting, observed vs paused/reserved/unknown
timing/cost separation, verbatim six-field Diagnostics, three disjoint reuse classes,
stop-loss/no-progress signals, and non-offsettable quality-floor checks.

Exit codes: 0 when ok is true; 2 when blocked (corrupt log, quality-floor regression,
or invalid arguments). Strictly read-only by default; --report optionally writes one
JSON file under non-reserved logs/**/*.json.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import json
from pathlib import Path

import _b_route_codec as codec
import _b_route_observability as obs


FORBIDDEN_MUTATION_FLAGS = (
    "--apply",
    "--write",
    "--commit",
    "--publish",
    "--mutate-tasks",
    "--set-status",
    "--refresh-knowledge",
)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise codec.CodecError(codec.Diagnostic(
            codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.TARGET, None,
            "valid read-only b-route-observability options", message, None,
        ))


def register_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--root", default=".", help="Explicit repository root (defaults to current directory)")
    parser.add_argument("--operation-id", default=None, help="Filter by operation_id")
    parser.add_argument("--run-id", default=None, help="Filter by run_id")
    parser.add_argument("--scope-id", default=None, help="Filter by scope_id")
    parser.add_argument("--flow-id", default=None, help="Filter by flow_id")
    parser.add_argument("--stage", default=None, help="Filter by stage (e.g. 3A, 3B, 3C, 4, 5, 6, 7, flow_verify, rework)")
    parser.add_argument("--task-id", default=None, help="Filter by task_id")
    parser.add_argument("--events-log", action="append", default=None, dest="events_logs",
                        help="Repeatable repository-relative logs/**/*.jsonl file to include in aggregation")
    parser.add_argument("--baseline-ref", default=None,
                        help="Optional repository-relative historical baseline JSON for same-denominator reference")
    parser.add_argument("--verdict-ref", action="append", default=None, dest="verdict_refs",
                        help="Repeatable repository-relative VerificationScope/receipt/verdict/handoff JSON to inspect")
    parser.add_argument("--report", default=None,
                        help="Optional repository-relative non-reserved logs/**/*.json report path")
    return parser


def build_parser() -> argparse.ArgumentParser:
    return register_arguments(_Parser(
        description=__doc__,
        allow_abbrev=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    ))


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":")))


def _failure(diagnostic: dict) -> dict:
    unified = obs.normalize_unified_diagnostic(diagnostic)
    return {
        "schema_version": obs.SCHEMA_VERSION,
        "ok": False,
        "status": "invalid_arguments",
        "reason_code": unified["reason_code"],
        "diagnostics": [unified],
        "categories_present": [unified["diagnostic_category"]],
        "governance_thresholds": dict(obs.GOVERNANCE_THRESHOLDS),
        "implicit_global_refresh_performed": False,
        "runtime_verified": False,
        "default_b_enabled": False,
        "invariants": dict(obs.INVARIANTS),
    }


def main(argv: list[str] | None = None) -> int:
    sys.dont_write_bytecode = True
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        for token in argv:
            flag = token.split("=", 1)[0]
            if flag in FORBIDDEN_MUTATION_FLAGS:
                raise codec.CodecError(codec.Diagnostic(
                    codec.ReasonCode.CONFLICT, codec.Stage.CONTENT, flag.removeprefix("--"),
                    "read-only b-route-observability CLI (no mutation/publish/refresh flags)", token, None,
                ))
        args = build_parser().parse_args(argv)
        if type(args.root) is not str or not args.root.strip():
            raise codec.CodecError(codec.Diagnostic(
                codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.PATH, None,
                "nonempty repository root directory path", args.root, None,
            ))
        root = Path(args.root)
        payload = obs.build_b_route_observability_report(
            root,
            operation_id=args.operation_id,
            run_id=args.run_id,
            scope_id=args.scope_id,
            flow_id=args.flow_id,
            stage=args.stage,
            task_id=args.task_id,
            events_logs=args.events_logs,
            baseline_ref=args.baseline_ref,
            verdict_or_scope_refs=args.verdict_refs,
        )
        if args.report is not None:
            report_path = obs.write_observability_report(root, args.report, payload)
            payload["report_path"] = report_path.relative_to(root.resolve()).as_posix()
    except codec.CodecError as err:
        _emit(_failure(err.diagnostic.to_dict()))
        return 2
    _emit(payload)
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
