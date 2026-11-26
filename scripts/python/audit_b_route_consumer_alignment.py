#!/usr/bin/env python3
"""Read-only B-route consumer alignment & pre-switch audit CLI (Story 4.9).

Reconciles all ten consumer groups (including direct underlying scripts and shared-Task
multi-scope consumers), executes live five-state version contract and anti-downgrade
probes, validates AGENTS.md / entrypoint indexes / B-route owning docs / governed
Skills / ADR governance (Proposed vs Accepted, dual ADR-0038-*.md), verifies
clean-clone minimal Git governance without logs/**, Knowledge exclusions, and zero
duplicate codec/formal schema parsers, and emits a reconstructable pre-switch coverage
report.

Strictly read-only. Never edits workflow.md, never switches default B, never retires
A write compatibility, never creates a second state machine, and never refreshes
Knowledge implicitly. Exit 0 when all Epic 4 alignment checks pass; exit 2 when
blocked, when --skip-live-probes is passed, or when arguments/paths are invalid.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import json
from pathlib import Path

import _b_route_codec as codec
import _b_route_consumer_alignment as alignment
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
            "valid read-only b-route-consumer-alignment options",
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
        "--skip-live-probes",
        action="store_true",
        default=False,
        help="Skip isolated tempdir five-state contract and clean-clone live probes (fails closed with exit 2)",
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
        "schema_version": alignment.SCHEMA_VERSION,
        "ok": False,
        "status": "blocked",
        "reason_code": diagnostic["reason_code"],
        "diagnostics": [diagnostic],
        "default_b_enabled": False,
        "a_write_compatibility_retired": False,
        "second_state_machine_created": False,
        "runtime_verified": False,
        "implicit_global_refresh_performed": False,
        "invariants": dict(alignment.INVARIANTS),
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
                    "read-only b-route-consumer-alignment CLI (no switch/write/publish/refresh flags)",
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
            alignment.validate_alignment_report_path(root_resolved, args.report)
        payload = alignment.audit_b_route_consumer_alignment(
            root_resolved,
            probe_temp_contracts=not bool(args.skip_live_probes),
        )
        if args.report is not None:
            alignment.write_alignment_report(root_resolved, args.report, payload)
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
    _emit(payload)
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
