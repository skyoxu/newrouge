#!/usr/bin/env python3
"""Read-only B-route Chapter 6 unified execution gate CLI."""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import json
from pathlib import Path
import time

import _b_route_chapter6_gate as gate
import _b_route_codec as codec
import _b_route_input_set as input_set
import _b_route_task_resolver as resolver


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.INVALID_ARGUMENT,
                codec.Stage.PATH,
                None,
                "explicit --task-id with optional --root/--operation/--lock-mode/--expected-input-set-digest/--report",
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
        required=True,
        help="Strict ASCII positive integer master Task ID",
    )
    parser.add_argument(
        "--operation",
        default=None,
        help="Optional operation name checked against allowed_a_operations",
    )
    parser.add_argument(
        "--lock-mode",
        choices=("none", "scope"),
        default="none",
        help="Locking mode: 'none' (default, zero writes/locks) or 'scope' (business-scope lease only)",
    )
    parser.add_argument(
        "--expected-input-set-digest",
        default=None,
        help="Optional expected sha256:<64 hex> InputSet digest for boundary drift verification",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Optional repository-relative logs/ci/.../*.json path; omit for zero disk writes",
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
        root_path = resolver._validate_root(Path(args.root))
        task_id = gate.parse_strict_task_id(args.task_id)
        if args.operation is not None:
            resolver._validate_operation(args.operation)
        lock_mode = input_set._validate_lock_mode(args.lock_mode)
    except codec.CodecError as error:
        d = error.diagnostic.to_dict()
        blocked = gate._blocked_result(
            task_id=None,
            operation=None,
            consumer="b-route-chapter6-gate",
            lock_mode="none",
            route="blocked",
            reason_code=d["reason_code"],
            reason=f"invalid_arguments:{d['reason_code']}",
            return_stage=gate._extract_return_stage_from_diag(d, default="5"),
            diagnostics=[d],
            started=started,
        )
        _emit(blocked)
        return 2

    result = gate.evaluate_chapter6_gate(
        root_path,
        task_id,
        operation=args.operation,
        expected_input_set_digest=args.expected_input_set_digest,
        consumer="b-route-chapter6-gate",
        lock_mode=lock_mode,
    )

    if args.report is not None:
        try:
            written = gate.write_report(root_path, args.report, result)
            result["report_path"] = written
        except codec.CodecError as error:
            d = error.diagnostic.to_dict()
            if d.get("entity_id") is None:
                d["entity_id"] = str(task_id)
            blocked = gate._blocked_result(
                task_id=task_id,
                operation=args.operation,
                consumer="b-route-chapter6-gate",
                lock_mode=lock_mode,
                route="blocked",
                reason_code=d["reason_code"],
                reason=f"invalid_report_path:{d['reason_code']}",
                return_stage="5",
                diagnostics=[d],
                started=started,
            )
            _emit(blocked)
            return 2

    _emit(result)
    if result["ok"]:
        return 0
    if result.get("reason_code") in ("invalid_argument", "invalid_type", "invalid_enum", "invalid_digest"):
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
