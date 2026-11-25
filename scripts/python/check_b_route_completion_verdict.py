#!/usr/bin/env python3
"""Read-only B-route completion verdict CLI (separately verifies Task, Flow, Milestone, and non-Flow completion)."""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import json
import time

import _b_route_codec as codec
import _b_route_completion_verdict as verdict_service


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.INVALID_ARGUMENT,
                codec.Stage.PATH,
                None,
                "--level task|flow|milestone|non_flow with level-appropriate --task-id/--flow-id/--manifest/"
                "--verification-scope/--receipt/--chapter7-slice-report/--manual-signoff/--milestone-handoff",
                message,
                None,
            )
        )


def register_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--root",
        default=".",
        help="Explicit repository root (defaults to current working directory)",
    )
    parser.add_argument(
        "--level",
        required=True,
        choices=sorted(verdict_service.VALID_LEVELS),
        help="Completion verification level: task, flow, milestone, or non_flow",
    )
    parser.add_argument(
        "--task-id",
        default=None,
        help="Strict ASCII positive integer master Task ID (required for --level task)",
    )
    parser.add_argument(
        "--flow-id",
        default=None,
        help="Target Flow ID (required for --level flow)",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="Repository-relative MVG manifest JSON path (required for --level milestone)",
    )
    parser.add_argument(
        "--verification-scope",
        default=None,
        help="Repository-relative sealed VerificationScope JSON path",
    )
    parser.add_argument(
        "--receipt",
        action="append",
        default=[],
        help="Repository-relative coverage-receipt.json path or MVG acceptance run dir (repeatable)",
    )
    parser.add_argument(
        "--chapter7-slice-report",
        default=None,
        help="Optional repository-relative Chapter 7 slice report JSON path",
    )
    parser.add_argument(
        "--manual-signoff",
        default=None,
        help="Optional repository-relative grounded manual signoff JSON path (newrouge.b-route-manual-signoff.v1)",
    )
    parser.add_argument(
        "--milestone-handoff",
        default=None,
        help="Optional repository-relative milestone task handoff JSON path",
    )
    parser.add_argument(
        "--operation",
        default="completion_verdict",
        help="Operation label (defaults to completion_verdict)",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Optional new repository-relative logs/**/*.json report path; omit for zero disk writes",
    )
    parser.add_argument(
        "--events-log",
        default=None,
        help="Optional repository-relative logs/**/*.jsonl events log path; omit for zero disk writes",
    )
    return parser


def build_parser() -> argparse.ArgumentParser:
    return register_arguments(_Parser(description=__doc__, allow_abbrev=False))


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":")))


def main(argv=None) -> int:
    sys.dont_write_bytecode = True
    started = time.monotonic()
    try:
        args = build_parser().parse_args(argv)
        if type(args.root) is not str or not args.root.strip():
            raise codec.CodecError(
                codec.Diagnostic(
                    codec.ReasonCode.INVALID_ARGUMENT,
                    codec.Stage.PATH,
                    None,
                    "nonempty repository root directory path",
                    args.root,
                    None,
                )
            )
        result = verdict_service.evaluate_completion_verdict(
            args.root,
            level=args.level,
            task_id=args.task_id,
            flow_id=args.flow_id,
            manifest_path=args.manifest,
            verification_scope_path=args.verification_scope,
            receipt_paths=list(args.receipt or []) or None,
            chapter7_slice_report=args.chapter7_slice_report,
            manual_signoff_path=args.manual_signoff,
            milestone_handoff_path=args.milestone_handoff,
            operation=args.operation,
            report_path=args.report,
            events_log_path=args.events_log,
        )
    except codec.CodecError as err:
        diag = err.diagnostic.to_dict()
        payload = verdict_service._base_verdict_payload(level="unknown", operation="completion_verdict", started=started)
        payload["reason_code"] = diag["reason_code"]
        payload["reason"] = f"invalid_arguments:{diag['reason_code']}"
        payload["diagnostics"] = [diag]
        _emit(payload)
        return 2

    _emit(result)
    if result.get("ok"):
        return 0
    if result.get("reason_code") in verdict_service.INVALID_ARGUMENT_CODES:
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
