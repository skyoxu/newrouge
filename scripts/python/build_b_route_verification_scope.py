#!/usr/bin/env python3
"""Read-only B-route executable three-tier VerificationScope CLI (build, validate, revalidate)."""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import json
import time

import _b_route_codec as codec
import _b_route_verification_scope as scope_service


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.INVALID_ARGUMENT,
                codec.Stage.PATH,
                None,
                "--change-root <root> (repeatable) or --impact-proof <path>, or --validate-scope <path>, or "
                "--revalidate-scope <path>, with optional --root/--task-id/--plan-id/--flow-id/--manifest/"
                "--cumulative-manifest/--scope-delta/--prior-conclusions/--operation/--report/--events-log",
                message,
                None,
            )
        )


def register_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--root", default=".", help="Explicit repository root (defaults to current working directory)")
    parser.add_argument("--change-root", action="append", default=[],
                        help="Story 4.1 change root such as contract:<path>, state:<id>, flow:<id> or a plain "
                             "repository-relative path (repeatable); computes a fresh impact closure")
    parser.add_argument("--impact-proof", default=None,
                        help="Existing Story 4.1 impact proof JSON path; it must revalidate as valid_reused")
    parser.add_argument("--task-id", action="append", default=[], help="In-scope task id of the current delivery (repeatable)")
    parser.add_argument("--plan-id", action="append", default=[], help="In-scope committed plan id (repeatable)")
    parser.add_argument("--flow-id", action="append", default=[], help="In-scope Flow id (repeatable)")
    parser.add_argument("--manifest", action="append", default=[], help="Active MVG manifest path (repeatable)")
    parser.add_argument("--cumulative-manifest", action="append", default=[],
                        help="Additional cumulative baseline MVG manifest path (repeatable)")
    parser.add_argument("--scope-delta", default=None,
                        help="Governed scope delta JSON path (newrouge.b-route-verification-scope-delta.v1)")
    parser.add_argument("--validate-scope", default=None, help="Validate an existing VerificationScope JSON path")
    parser.add_argument("--revalidate-scope", default=None,
                        help="Revalidate an existing VerificationScope JSON path against live inputs")
    parser.add_argument("--prior-conclusions", default=None,
                        help="Optional repository-relative JSON file with prior conclusions (list or "
                             "{\"prior_conclusions\": [...]}) assessed by --revalidate-scope")
    parser.add_argument("--operation", default=None, help="Operation label (defaults to build_verification_scope)")
    parser.add_argument("--report", default=None,
                        help="Optional new repository-relative logs/**/*.json report path; omit for zero disk writes")
    parser.add_argument("--events-log", default=None,
                        help="Optional repository-relative logs/**/*.jsonl events path; omit for zero disk writes")
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
        modes = [name for name, active in (("build", bool(args.change_root) or args.impact_proof is not None),
                                           ("validate", args.validate_scope is not None),
                                           ("revalidate", args.revalidate_scope is not None)) if active]
        if len(modes) != 1:
            raise _invalid("exactly one mode: --change-root/--impact-proof, --validate-scope or --revalidate-scope",
                           modes)
        if modes[0] == "build" and args.change_root and args.impact_proof is not None:
            raise _invalid("either --change-root or --impact-proof, not both", args.impact_proof)
        build_only = (args.task_id or args.plan_id or args.flow_id or args.manifest or args.cumulative_manifest
                      or args.scope_delta is not None or args.operation is not None)
        if modes[0] != "build" and build_only:
            raise _invalid("scope build options are taken from the scope during validation/revalidation",
                           {"mode": modes[0]})
        if modes[0] != "revalidate" and args.prior_conclusions is not None:
            raise _invalid("--prior-conclusions is only valid with --revalidate-scope", {"mode": modes[0]})
        if modes[0] == "validate":
            if args.report is not None or args.events_log is not None:
                raise _invalid("--validate-scope is strictly zero-write", {"report": args.report})
            result = scope_service.validate_verification_scope(args.root, args.validate_scope)
            _emit(result)
            return 0 if result.get("ok") else _failure_code(result)
        if modes[0] == "revalidate":
            result = scope_service.revalidate_verification_scope(
                args.root, args.revalidate_scope, prior_conclusions=args.prior_conclusions,
                report_path=args.report, events_log_path=args.events_log)
            _emit(result)
            if result.get("ok") and result.get("valid"):
                return 0
            return 1 if result.get("ok") else _failure_code(result)
        result = scope_service.build_verification_scope(
            args.root,
            change_roots=list(args.change_root) or None,
            impact_proof=args.impact_proof,
            in_scope_task_ids=list(args.task_id),
            in_scope_plan_ids=list(args.plan_id),
            in_scope_flow_ids=list(args.flow_id),
            manifest_paths=list(args.manifest),
            cumulative_baseline_manifests=list(args.cumulative_manifest),
            scope_delta=args.scope_delta,
            operation=args.operation if args.operation is not None else "build_verification_scope",
            report_path=args.report,
            events_log_path=args.events_log,
        )
        _emit(result)
        return 0 if result.get("ok") else _failure_code(result)
    except codec.CodecError as err:
        diag = err.diagnostic.to_dict()
        _emit({
            "schema_version": scope_service.SCHEMA,
            "ok": False,
            "status": "blocked",
            "reason_code": diag["reason_code"],
            "reason": f"invalid_arguments:{diag['reason_code']}",
            "scope_id": None,
            "report_path": None,
            "diagnostics": [diag],
            "metrics": {"active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6)},
            **scope_service.INVARIANT_FLAGS,
        })
        return 2


def _failure_code(result: dict) -> int:
    return 2 if result.get("reason_code") in scope_service.INVALID_ARGUMENT_CODES else 1


if __name__ == "__main__":
    raise SystemExit(main())
