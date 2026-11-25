#!/usr/bin/env python3
"""Read-only B-route derived Knowledge projection (planning, implementation, runtime identity).

Exit codes: 0 when the projection is ok (status ok, partial_planning or legacy_unmapped);
2 when the projection is blocked (corrupt, pending, or revoked target) or arguments are invalid.
The command never writes repository authorities, Taskmaster files, B-route records, or Knowledge
publication pointers; --report optionally writes one JSON file strictly under logs/**.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import json
from pathlib import Path

import _b_route_codec as codec
import _b_route_knowledge_projection as projection

FORBIDDEN_FLAGS = ("--apply", "--write", "--commit", "--publish", "--mutate-tasks", "--set-status")


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise codec.CodecError(codec.Diagnostic(
            codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.TARGET, None,
            "--mode workspace_preview|attempt|stable|stabilized|main with optional "
            "--scope-id/--flow-id/--capability-id/--task-id/--report", message, None))


def register_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--root", default=".", help="Explicit repository root (defaults to current directory)")
    parser.add_argument("--mode", default="main", choices=list(projection.VALID_MODES),
                        help="Snapshot identity: workspace_preview, attempt, stable, stabilized, or main")
    parser.add_argument("--scope-id", default=None, help="Optional B-route catalog scope filter")
    parser.add_argument("--flow-id", default=None, help="Optional target Flow ID")
    parser.add_argument("--capability-id", default=None, help="Optional target Capability ID")
    parser.add_argument("--task-id", default=None, help="Optional target master Task ID")
    parser.add_argument("--report", default=None,
                        help="Optional repository-relative logs/**/*.json report path; omit for zero disk writes")
    return parser


def build_parser() -> argparse.ArgumentParser:
    return register_arguments(_Parser(description=__doc__, allow_abbrev=False,
                                      formatter_class=argparse.RawDescriptionHelpFormatter))


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":")))


def _failure(diagnostic: dict) -> dict:
    return {"schema_version": projection.SCHEMA_VERSION, "ok": False, "status": "invalid_arguments",
            "reason_code": diagnostic["reason_code"], "diagnostics": [diagnostic],
            "invariants": dict(projection.INVARIANTS)}


def main(argv=None) -> int:
    sys.dont_write_bytecode = True
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        for value in argv:
            if value.split("=", 1)[0] in FORBIDDEN_FLAGS:
                raise codec.CodecError(codec.Diagnostic(
                    codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.TARGET, None,
                    "read-only projection without write/mutation flags", value, None))
        args = build_parser().parse_args(argv)
        if type(args.root) is not str or not args.root.strip():
            raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.PATH, None,
                                                    "nonempty repository root directory path", args.root, None))
        root = Path(args.root)
        result = projection.build_b_route_knowledge_projection(
            root, mode=args.mode, scope_id=args.scope_id, flow_id=args.flow_id,
            capability_id=args.capability_id, task_id=args.task_id)
        if args.report is not None:
            path = projection.write_projection_report(root, args.report, result)
            result["report_path"] = path.relative_to(root.resolve()).as_posix()
    except codec.CodecError as err:
        _emit(_failure(err.diagnostic.to_dict()))
        return 2
    _emit(result)
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
