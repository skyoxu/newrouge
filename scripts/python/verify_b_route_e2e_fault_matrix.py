#!/usr/bin/env python3
"""Read-only B-route E2E Windows fault & shared-change matrix CLI (Story 4.10).

Executes real Windows msvcrt lock contention, child process termination/restarts
across all six commit lifecycle stages, shared-Task multi-scope & drift parity,
Flow A/B impact-to-verdict evolution, shared test evidence reuse & authenticity
rejections, and Planning Page / Knowledge Projection / Observability parity inside
isolated ephemeral workspaces, reconciling live Story 4.9 consumer alignment to
emit a reconstructable Epic 4 -> Epic 5 handoff readiness report.

Strictly read-only on --root. Forbids --apply, --switch-default-b, --retire-a,
--write-tasks, --publish, --refresh-knowledge, --write, --commit, --mutate-tasks,
and --set-status. Exit 0 when all Epic 4 E2E checks pass; exit 2 when blocked,
when --skip-fault-harness is passed, or when arguments/paths are invalid.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import json
import subprocess

import _b_route_codec as codec
import _b_route_e2e_fault_matrix as e2e_matrix
import _b_route_observability as observability


FORBIDDEN_MUTATION_FLAGS = (
    "--apply",
    "--switch-default-b",
    "--retire-a",
    "--write-tasks",
    "--publish",
    "--refresh-knowledge",
    "--write",
    "--commit",
    "--mutate-tasks",
    "--set-status",
)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise codec.CodecError(codec.Diagnostic(
            codec.ReasonCode.INVALID_ARGUMENT,
            codec.Stage.TARGET,
            None,
            "valid read-only b-route-e2e-matrix options",
            message,
            None,
        ))


def register_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument(
        "--root",
        default=".",
        help="Explicit repository root directory (defaults to current directory)",
    )
    parser.add_argument(
        "--skip-fault-harness",
        action="store_true",
        default=False,
        help="Skip live Windows fault and shared-change ephemeral harness (fails closed with exit 2)",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Optional non-existing repository-relative non-reserved logs/**/*.json report output path",
    )
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
    return {
        "schema_version": e2e_matrix.SCHEMA_VERSION,
        "ok": False,
        "status": "blocked",
        "reason_code": diagnostic["reason_code"],
        "epic4_capabilities_verified": False,
        "diagnostics": [diagnostic],
        **e2e_matrix.INVARIANTS,
        "invariants": dict(e2e_matrix.INVARIANTS),
    }


def main(argv: list[str] | None = None) -> int:
    sys.dont_write_bytecode = True
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        for token in argv:
            flag = token.split("=", 1)[0]
            if flag in FORBIDDEN_MUTATION_FLAGS:
                raise codec.CodecError(codec.Diagnostic(
                    codec.ReasonCode.CONFLICT,
                    codec.Stage.CONTENT,
                    flag.removeprefix("--"),
                    "read-only b-route-e2e-matrix CLI (no switch/write/publish/refresh flags)",
                    token,
                    None,
                ))
        args = build_parser().parse_args(argv)
        if type(args.root) is not str or not args.root.strip():
            raise codec.CodecError(codec.Diagnostic(
                codec.ReasonCode.INVALID_ARGUMENT,
                codec.Stage.PATH,
                None,
                "nonempty repository root directory path",
                args.root,
                None,
            ))
        root_resolved = observability._validate_root(args.root)
        if args.report is not None:
            e2e_matrix.validate_e2e_report_path(root_resolved, args.report)
        payload = e2e_matrix.run_b_route_e2e_fault_matrix(
            root_resolved,
            include_fault_harness=not bool(args.skip_fault_harness),
        )
        if args.report is not None:
            e2e_matrix.write_e2e_report(root_resolved, args.report, payload)
    except codec.CodecError as err:
        _emit(_failure(err.diagnostic.to_dict()))
        return 2
    except ValueError as err:
        diag = codec.Diagnostic(
            codec.ReasonCode.UNSAFE_PATH,
            codec.Stage.PATH,
            None,
            "valid canonical repository path without reparse",
            str(err)[:200],
            None,
        ).to_dict()
        _emit(_failure(diag))
        return 2
    except OSError as err:
        diag = codec.Diagnostic(
            codec.ReasonCode.READ_ERROR,
            codec.Stage.PATH,
            None,
            "accessible repository path",
            str(err)[:200],
            None,
        ).to_dict()
        _emit(_failure(diag))
        return 2
    except (RuntimeError, subprocess.SubprocessError) as err:
        diag = codec.Diagnostic(
            codec.ReasonCode.CONFLICT,
            codec.Stage.BUNDLE,
            None,
            "completed read-only b-route-e2e-matrix verification without subprocess/runtime error",
            str(err)[:200],
            None,
        ).to_dict()
        _emit(_failure(diag))
        return 2
    _emit(payload)
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
