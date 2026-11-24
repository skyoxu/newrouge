#!/usr/bin/env python3
"""Read-only B-route Chapter 6 defect routing, anti-disguise guard, and governed handoff CLI."""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import json
from pathlib import Path
import time

import _b_route_chapter6_gate as gate
import _b_route_codec as codec
import _b_route_defect_routing as defect_routing
import _b_route_task_resolver as resolver


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.INVALID_ARGUMENT,
                codec.Stage.PATH,
                None,
                "explicit --task-id with optional --root/--run-dir/--defect-input/--delta-intents/--fix-through/--report",
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
        "--run-dir",
        default=None,
        help="Optional Chapter 6 run directory for baseline, failure, and review inspection",
    )
    parser.add_argument(
        "--defect-input",
        default=None,
        help="Optional JSON file describing changed paths, gap categories, or proposed repair edits",
    )
    parser.add_argument(
        "--delta-intents",
        default=None,
        help="Optional JSON file with business-view repair task delta intents validated under Story 3.1/3.2 governance",
    )
    parser.add_argument(
        "--fix-through",
        default="P1",
        help="Must-fix severity floor (P1, P2, or P3; P0 is rejected because P1 is the minimum floor)",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="Optional new repository-relative logs/ci/.../*.json path; omit for zero disk writes",
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
    except codec.CodecError as error:
        d = error.diagnostic.to_dict()
        blocked = {
            "schema_version": defect_routing.SCHEMA,
            "ok": False,
            "task_id": None,
            "route": "blocked",
            "legacy_a_passthrough": False,
            "defect_class": "invalid_arguments",
            "action": "blocked",
            "local_repair_allowed": False,
            "reruns_3a_3b": False,
            "owning_stage": "3C",
            "return_stage": "3C",
            "reason_code": d["reason_code"],
            "reason": f"invalid_arguments:{d['reason_code']}",
            "diagnostics": [d],
            "governed_handoff": None,
            "delta_governance": None,
            "metrics": {
                "active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6),
                "model_invocation_count": 0,
                "durable_model_invocation_count": 0,
                "reused_upstream_artifacts": 0,
                "rework_count": 0,
            },
            "flow_completed": False,
            "cumulative_milestone_completed": False,
            "global_knowledge_refresh": "forbidden",
            "report_path": None,
            **defect_routing.INVARIANT_FLAGS,
        }
        _emit(blocked)
        return 2

    result = defect_routing.evaluate_defect_routing(
        root_path,
        task_id,
        run_dir=args.run_dir,
        defect_input=args.defect_input,
        delta_intents=args.delta_intents,
        fix_through=args.fix_through,
    )

    if args.report is not None:
        try:
            written = defect_routing.write_report(root_path, args.report, result)
            result["report_path"] = written
        except codec.CodecError as error:
            d = error.diagnostic.to_dict()
            if d.get("entity_id") is None:
                d["entity_id"] = str(task_id)
            blocked = {
                "schema_version": defect_routing.SCHEMA,
                "ok": False,
                "task_id": task_id,
                "route": "blocked",
                "legacy_a_passthrough": False,
                "defect_class": "invalid_arguments",
                "action": "blocked",
                "local_repair_allowed": False,
                "reruns_3a_3b": False,
                "owning_stage": "5",
                "return_stage": "5",
                "reason_code": d["reason_code"],
                "reason": f"invalid_report_path:{d['reason_code']}",
                "diagnostics": [d],
                "governed_handoff": None,
                "delta_governance": None,
                "metrics": {
                    "active_elapsed_seconds": round(max(0.0, time.monotonic() - started), 6),
                    "model_invocation_count": 0,
                    "durable_model_invocation_count": 0,
                    "reused_upstream_artifacts": 0,
                    "rework_count": 0,
                },
                "flow_completed": False,
                "cumulative_milestone_completed": False,
                "global_knowledge_refresh": "forbidden",
                "report_path": None,
                **defect_routing.INVARIANT_FLAGS,
            }
            _emit(blocked)
            return 2

    _emit(result)
    if result["ok"]:
        return 0
    if result.get("reason_code") in ("invalid_argument", "invalid_type", "invalid_enum", "invalid_digest", "unsafe_path", "invalid_json"):
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
