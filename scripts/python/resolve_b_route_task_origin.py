#!/usr/bin/env python3
"""Read-only zero-write B-route Task origin and applicable plan-set resolver CLI."""
import sys

sys.dont_write_bytecode = True

import argparse
import json
from pathlib import Path
import re

import _b_route_codec as codec
import _b_route_task_resolver as resolver


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.INVALID_ARGUMENT,
                codec.Stage.PATH,
                None,
                "explicit --task-id with optional --root/--operation/--report (strictly read-only)",
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
        help="Positive integer master Task ID to classify",
    )
    parser.add_argument(
        "--operation",
        default=None,
        help="Optional operation name (e.g. implement|resume|route) to check against allowed_a_operations",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Optional new repository-relative logs/ci/.../*.json path; omit for zero disk/lock writes",
    )
    return parser


def build_parser() -> argparse.ArgumentParser:
    return register_arguments(_Parser(description=__doc__, allow_abbrev=False))


def _parse_strict_task_id(raw: str) -> int:
    if type(raw) is not str or re.fullmatch(r"[1-9][0-9]*", raw) is None:
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.INVALID_ARGUMENT,
                codec.Stage.CONTENT,
                None,
                "positive integer --task-id",
                raw,
                None,
            )
        )
    return codec.validate_task_id(int(raw))


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":")))


def main(argv=None) -> int:
    sys.dont_write_bytecode = True
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
        task_id = _parse_strict_task_id(args.task_id)
        if args.operation is not None:
            resolver._validate_operation(args.operation)
    except codec.CodecError as error:
        result = resolver._base_result(None, None)
        result["diagnostics"].append(error.diagnostic.to_dict())
        _emit(result)
        return 2

    result = resolver.resolve_task_origin(
        root_path,
        task_id,
        operation=args.operation,
    )

    if args.report is not None:
        try:
            written = resolver.write_report(root_path, args.report, result)
            result["report_path"] = written
        except codec.CodecError as error:
            blocked = resolver._base_result(task_id, args.operation)
            diag = error.diagnostic.to_dict()
            if diag.get("entity_id") is None:
                diag["entity_id"] = str(task_id)
            blocked["diagnostics"].append(diag)
            _emit(blocked)
            return 2

    _emit(result)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
