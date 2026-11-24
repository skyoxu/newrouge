#!/usr/bin/env python3
"""Read-only B-route target-slice Chapter 7 UI closure, evidence reuse, and governed handoff CLI."""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import json
from pathlib import Path
import time

import _b_route_chapter7_slice as ch7_slice
import _b_route_codec as codec
import _b_route_task_resolver as resolver


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.INVALID_ARGUMENT,
                codec.Stage.PATH,
                None,
                "at least one of --flow-id, --slice, or --task-id with optional --root/--profile/--evidence-dir/--ui-evidence/--gap-input/--report",
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
        "--flow-id",
        default=None,
        help="Target committed B-route Flow ID to close without waiting for the whole game",
    )
    parser.add_argument(
        "--slice",
        default=None,
        help="Target Chapter 7 profile bucket name (e.g., reward_flow)",
    )
    parser.add_argument(
        "--task-id",
        action="append",
        default=[],
        help="Strict ASCII positive integer master Task ID (repeatable)",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Optional Chapter 7 profile JSON path (defaults to docs/workflows/chapter7-profile.json)",
    )
    parser.add_argument(
        "--evidence-dir",
        default=None,
        help="Optional repository-contained directory to scan for Chapter 6 / runtime UI evidence",
    )
    parser.add_argument(
        "--ui-evidence",
        default=None,
        help="Optional repository-contained JSON file with Chapter 6 / runtime UI evidence records",
    )
    parser.add_argument(
        "--gap-input",
        default=None,
        help="Optional repository-contained JSON file describing UI gaps, task deltas, or scene patches",
    )
    parser.add_argument(
        "--operation",
        default=None,
        help="Optional operation ID for B-route InputSet / gate evaluation",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Optional new repository-relative logs/ci/.../*.json path; omit for strictly zero disk writes",
    )
    return parser


def build_parser() -> argparse.ArgumentParser:
    return register_arguments(_Parser(description=__doc__, allow_abbrev=False))


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":")))


def _blocked_cli_payload(diag: dict, *, started: float, reason: str) -> dict:
    return {
        "schema_version": ch7_slice.SCHEMA,
        "ok": False,
        "route": "blocked",
        "target_slice": None,
        "target_flow_id": None,
        "target_task_ids": [],
        "ui_applicability": "unknown",
        "reason_code": diag["reason_code"],
        "reason": reason,
        "return_stage": "4",
        "diagnostics": [diag],
        "verified_items": [],
        "pending_items": [],
        "manual_items": [],
        "blocked_items": [],
        "reused_ui_obligations": [],
        "rejected_evidence": [],
        "governed_gap_routing": [],
        "proposed_governed_deltas": None,
        "native_scene_manual_regions_preserved": True,
        "flow_all_required_obligations_completed": False,
        "flow_completed": False,
        "cumulative_milestone_completed": False,
        "downstream_flow_obligations_preserved": True,
        "cumulative_milestone_obligations_preserved": True,
        "task_triplet_written": False,
        "global_knowledge_refresh": "not_performed",
        "report_path": None,
        "handoff": {
            "schema_version": ch7_slice.HANDOFF_SCHEMA,
            "target_slice": None,
            "target_flow_id": None,
            "target_task_ids": [],
            "ui_applicability": "unknown",
            "verified_items": [],
            "pending_items": [],
            "manual_items": [],
            "blocked_items": [],
            "reused_ui_obligations": [],
            "governed_gap_routing": [],
            "proposed_governed_deltas": None,
            "downstream_flow_obligations_preserved": True,
            "cumulative_milestone_obligations_preserved": True,
            "flow_all_required_obligations_completed": False,
            "flow_completed": False,
            "cumulative_milestone_completed": False,
            "global_knowledge_refresh": "not_performed",
            **ch7_slice.INVARIANT_FLAGS,
        },
        "metrics": {
            "active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6),
            "model_invocation_count": 0,
        },
        **ch7_slice.INVARIANT_FLAGS,
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
        root_path = resolver._validate_root(Path(args.root))
        if args.report is not None:
            ch7_slice.validate_report_path(root_path, args.report)
        result = ch7_slice.evaluate_chapter7_slice(
            root_path,
            flow_id=args.flow_id,
            slice_name=args.slice,
            task_ids=list(args.task_id or []),
            profile_path=args.profile,
            evidence_dir=args.evidence_dir,
            ui_evidence=args.ui_evidence,
            gap_input=args.gap_input,
            operation=args.operation,
        )
    except codec.CodecError as error:
        d = error.diagnostic.to_dict()
        _emit(_blocked_cli_payload(d, started=started, reason=f"invalid_arguments:{d['reason_code']}"))
        return 2

    if args.report is not None:
        try:
            written = ch7_slice.write_report(root_path, args.report, result)
            result["report_path"] = written
        except codec.CodecError as error:
            d = error.diagnostic.to_dict()
            _emit(_blocked_cli_payload(d, started=started, reason=f"invalid_report_path:{d['reason_code']}"))
            return 2

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


if __name__ == "__main__":
    raise SystemExit(main())
