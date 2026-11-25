#!/usr/bin/env python3
"""Read-only B-route governed reverse impact closure and selective proof revalidation CLI."""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import json
import time

import _b_route_codec as codec
import _b_route_impact_closure as closure


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.INVALID_ARGUMENT,
                codec.Stage.PATH,
                None,
                "--change-root <root> (repeatable) or --revalidate-proof <path> with optional "
                "--root/--plan-id/--manifest/--operation/--report/--events-log",
                message,
                None,
            )
        )


def register_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--root", default=".", help="Explicit repository root (defaults to current working directory)")
    parser.add_argument(
        "--change-root",
        action="append",
        default=[],
        help="Change root such as contract:<path>, rule:<plan>:<id>, state:<id>, command:<id>, flow:<id>, "
        "task:<id>, test:<id>, requirement:<id>, impl:<id>, or a plain repository-relative path (repeatable)",
    )
    parser.add_argument("--plan-id", action="append", default=[], help="Restrict committed plans to these plan IDs (repeatable)")
    parser.add_argument("--manifest", action="append", default=[], help="Additional cumulative MVG manifest path (repeatable)")
    parser.add_argument(
        "--revalidate-proof",
        default=None,
        help="Existing impact proof JSON path to revalidate per partition instead of computing a new closure",
    )
    parser.add_argument(
        "--operation",
        default=None,
        help="Operation label recorded in events (defaults to impact_closure or impact_revalidation)",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Optional new repository-relative logs/**/*.json report path; omit for zero disk writes",
    )
    parser.add_argument(
        "--events-log",
        default=None,
        help="Optional repository-relative logs/**/*.jsonl events path; omit for zero disk writes",
    )
    return parser


def build_parser() -> argparse.ArgumentParser:
    return register_arguments(_Parser(description=__doc__, allow_abbrev=False))


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":")))


def _invalid(expected: str, actual) -> codec.CodecError:
    return codec.CodecError(codec.Diagnostic(codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.PATH, None,
                                             expected, actual, None))


def main(argv=None) -> int:
    sys.dont_write_bytecode = True
    started = time.monotonic()
    try:
        args = build_parser().parse_args(argv)
        if type(args.root) is not str or not args.root.strip():
            raise _invalid("nonempty repository root directory path", args.root)
        change_roots = list(args.change_root or [])
        if not change_roots and args.revalidate_proof is None:
            raise _invalid("at least one --change-root or --revalidate-proof", {"change_roots": change_roots})
        if change_roots and args.revalidate_proof is not None:
            raise _invalid("either --change-root or --revalidate-proof, not both",
                           {"change_roots": change_roots, "revalidate_proof": args.revalidate_proof})
        if args.revalidate_proof is not None:
            if args.plan_id:
                raise _invalid("--plan-id is taken from the proof during revalidation", args.plan_id)
            result = closure.revalidate_impact_proof(
                args.root,
                args.revalidate_proof,
                manifest_paths=list(args.manifest) if args.manifest else None,
                operation=args.operation if args.operation is not None else "impact_revalidation",
                report_path=args.report,
                events_log_path=args.events_log,
            )
        else:
            result = closure.compute_impact_closure(
                args.root,
                change_roots=change_roots,
                manifest_paths=list(args.manifest or []),
                plan_ids=list(args.plan_id or []),
                operation=args.operation if args.operation is not None else "impact_closure",
                report_path=args.report,
                events_log_path=args.events_log,
            )
        _emit(result)
        if result.get("ok"):
            return 0
        if result.get("reason_code") in closure.INVALID_ARGUMENT_CODES:
            return 2
        return 1
    except codec.CodecError as err:
        diag = err.diagnostic.to_dict()
        payload = {
            "schema_version": closure.SCHEMA,
            "ok": False,
            "status": "blocked",
            "reason_code": diag["reason_code"],
            "reason": f"invalid_arguments:{diag['reason_code']}",
            "reused": False,
            "impact_proof_id": None,
            "report_path": None,
            "diagnostics": [diag],
            "metrics": {"active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6)},
            **closure.INVARIANT_FLAGS,
        }
        _emit(payload)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
