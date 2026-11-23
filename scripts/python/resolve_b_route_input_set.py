#!/usr/bin/env python3
"""Read-only B-route common InputSet and freshness resolver CLI."""
import sys

sys.dont_write_bytecode = True

import argparse
import json
from pathlib import Path
import re

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
                "explicit --task-id with optional --root/--operation/--candidate-binding/--baseline/--lock-mode/--max-attempts/--report",
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
        help="Positive integer master Task ID",
    )
    parser.add_argument(
        "--operation",
        default=None,
        help="Optional operation name (e.g. implement|resume|route) checked against allowed_a_operations",
    )
    parser.add_argument(
        "--candidate-binding",
        default=None,
        help="Optional repository-relative path to an uncommitted candidate newrouge.b-route-binding.v1 JSON file",
    )
    parser.add_argument(
        "--baseline",
        default=None,
        help="Optional repository-relative path to a prior InputSet JSON report for freshness comparison and return_stage attribution",
    )
    parser.add_argument(
        "--lock-mode",
        choices=("none", "scope"),
        default="none",
        help="Locking mode: 'none' (default, zero writes/locks) or 'scope' (business-scope review_only=True guard with revalidation)",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=input_set.DEFAULT_MAX_ATTEMPTS,
        help="Bounded read retry attempts against transient drift (1..5, default 3)",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Optional new repository-relative logs/ci/.../*.json path; omit for zero disk writes",
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
        lock_mode = input_set._validate_lock_mode(args.lock_mode)
        max_attempts = input_set._validate_max_attempts(args.max_attempts)
    except codec.CodecError as error:
        result = input_set._base_result(None, None)
        result["diagnostics"].append(error.diagnostic.to_dict())
        _emit(result)
        return 2

    if lock_mode == "scope":
        try:
            with input_set.guarded_input_set(
                root_path,
                task_id,
                operation=args.operation,
                candidate_binding=args.candidate_binding,
                baseline=args.baseline,
                max_attempts=max_attempts,
            ) as handle:
                result = handle.revalidate()
        except codec.CodecError as error:
            result = input_set._base_result(task_id, args.operation, lock_mode="scope")
            diag = error.diagnostic.to_dict()
            if diag.get("entity_id") is None:
                diag["entity_id"] = str(task_id)
            result["diagnostics"].append(diag)
            actual_obj = diag.get("actual")
            inferred = (
                actual_obj.get("return_stage")
                if type(actual_obj) is dict and actual_obj.get("return_stage") in input_set.STAGE_RANK
                else input_set._stage_for_diag(diag)
            )
            result["return_stage"] = inferred
    else:
        result = input_set.resolve_input_set(
            root_path,
            task_id,
            operation=args.operation,
            candidate_binding=args.candidate_binding,
            baseline=args.baseline,
            max_attempts=max_attempts,
        )

    if args.report is not None:
        try:
            written = input_set.write_report(root_path, args.report, result)
            result["report_path"] = written
        except codec.CodecError as error:
            blocked = input_set._base_result(task_id, args.operation, lock_mode=lock_mode)
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
