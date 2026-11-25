#!/usr/bin/env python3
"""Read-only B-route five-entrypoint parity, page gate verifier, and Epic 3 -> Epic 4 handoff CLI."""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import json
import os
from pathlib import Path
import time

import _b_route_codec as codec
import _b_route_entrypoint_parity as parity
import _b_route_task_resolver as resolver


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.INVALID_ARGUMENT,
                codec.Stage.PATH,
                None,
                "--task-id <id> and/or --epic3-handoff with optional --root/--operation/--report/--handoff-report",
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
        "--task-id",
        action="append",
        default=[],
        help="Strict ASCII positive integer master Task ID to check across all five entrypoints (repeatable)",
    )
    parser.add_argument(
        "--operation",
        default=None,
        help="Optional B-route operation name for parity evaluation",
    )
    parser.add_argument(
        "--epic3-handoff",
        action="store_true",
        help="Emit the honest Epic 3 -> Epic 4 handoff summary aligning consumers, CLI, Skills, and docs",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Optional new repository-relative logs/ci/.../*.json path for parity report; omit for zero disk writes",
    )
    parser.add_argument(
        "--handoff-report",
        default=None,
        help="Optional new repository-relative logs/ci/.../*.json path for Epic 3 handoff report; omit for zero disk writes",
    )
    return parser


def build_parser() -> argparse.ArgumentParser:
    return register_arguments(_Parser(description=__doc__, allow_abbrev=False))


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":")))


def _blocked_cli_payload(diag: dict, *, started: float, reason: str) -> dict:
    return {
        "schema_version": parity.SCHEMA,
        "ok": False,
        "parity_ok": False,
        "route": "blocked",
        "admitted": False,
        "reason_code": diag["reason_code"],
        "public_reason_code": diag["reason_code"],
        "reason": reason,
        "blocked_by": "b_route_chapter6_gate",
        "return_stage": "5",
        "flow_completed": False,
        "self_done_required": False,
        "report_path": None,
        "diagnostics": [diag],
        "metrics": {"active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6)},
        **parity.INVARIANT_FLAGS,
    }


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
        task_ids = list(args.task_id or [])
        if not task_ids and not args.epic3_handoff:
            raise codec.CodecError(
                codec.Diagnostic(
                    codec.ReasonCode.INVALID_ARGUMENT,
                    codec.Stage.PATH,
                    None,
                    "at least one --task-id or --epic3-handoff",
                    {"task_ids": task_ids, "epic3_handoff": bool(args.epic3_handoff)},
                    None,
                )
            )
        root_path = resolver._validate_root(Path(args.root))
        rep_target: Path | None = None
        rep_norm: str | None = None
        hrep_target: Path | None = None
        hrep_norm: str | None = None
        if args.report is not None:
            rep_target, rep_norm = parity.validate_report_path(root_path, args.report)
        if args.handoff_report is not None:
            hrep_target, hrep_norm = parity.validate_report_path(root_path, args.handoff_report)
        if rep_target is not None and hrep_target is not None:
            if os.path.normcase(str(rep_target.resolve())) == os.path.normcase(str(hrep_target.resolve())):
                raise codec.CodecError(
                    codec.Diagnostic(
                        codec.ReasonCode.CONFLICT,
                        codec.Stage.PATH,
                        None,
                        "distinct --report and --handoff-report output paths",
                        {"report": rep_norm, "handoff_report": hrep_norm},
                        rep_norm,
                    )
                )

        if args.epic3_handoff and not task_ids:
            result = parity.build_epic3_to_epic4_handoff(root_path, task_ids=None)
            if args.handoff_report is not None:
                parity.write_report(root_path, args.handoff_report, result)
            elif args.report is not None:
                parity.write_report(root_path, args.report, result)
            _emit(result)
            return 0 if result["ok"] else 1

        if len(task_ids) == 1 and not args.epic3_handoff:
            result = parity.evaluate_entrypoint_parity(
                root_path,
                task_id=task_ids[0],
                operation=args.operation,
            )
            if args.report is not None:
                parity.write_report(root_path, args.report, result)
            _emit(result)
            if result["ok"]:
                return 0
            if result.get("reason_code") in (
                "invalid_argument",
                "invalid_type",
                "invalid_enum",
                "invalid_digest",
                "unsafe_path",
                "invalid_json",
            ):
                return 2
            return 1

        evaluations = [
            parity.evaluate_entrypoint_parity(root_path, task_id=tid, operation=args.operation)
            for tid in task_ids
        ]
        handoff = (
            parity.build_epic3_to_epic4_handoff(root_path, task_ids=task_ids)
            if args.epic3_handoff
            else None
        )
        all_ok = all(item.get("ok") for item in evaluations) and (handoff is None or bool(handoff.get("ok")))
        result = {
            "schema_version": parity.SCHEMA,
            "ok": all_ok,
            "parity_ok": all(item.get("parity_ok") for item in evaluations),
            "evaluations": evaluations,
            "epic3_handoff": handoff,
            "flow_completed": False,
            "self_done_required": False,
            "report_path": None,
            "diagnostics": [d for item in evaluations for d in (item.get("diagnostics") or [])]
            + (list(handoff.get("diagnostics") or []) if handoff else []),
            "metrics": {"active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6)},
            **parity.INVARIANT_FLAGS,
        }
        if args.handoff_report is not None and handoff is not None:
            parity.write_report(root_path, args.handoff_report, handoff)
        if args.report is not None:
            parity.write_report(root_path, args.report, result)
        _emit(result)
        return 0 if result["ok"] else 1
    except codec.CodecError as err:
        d = err.diagnostic.to_dict()
        _emit(_blocked_cli_payload(d, started=started, reason=f"invalid_arguments:{d['reason_code']}"))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
