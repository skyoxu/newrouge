#!/usr/bin/env python3
"""Read-only 3C reuse inventory and real-gap task-change preview CLI."""
import sys
sys.dont_write_bytecode = True

import argparse
import json
import os
from pathlib import Path

import _b_route_codec as codec
import _b_route_task_preview as service


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.INVALID_ARGUMENT,
                codec.Stage.PATH,
                None,
                {
                    "owning_stage": "3C",
                    "path": None,
                    "value": "explicit --root/--plan-id/--run-id/--audit-ref/--scope-id (no write/apply flag)",
                },
                {"owning_stage": "3C", "path": None, "value": message},
                None,
            )
        )


def register_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--root", type=Path, required=True, help="Explicit repository root")
    parser.add_argument("--plan-id", required=True, help="Committed 3B plan_id to preview")
    parser.add_argument("--run-id", required=True, help="Fresh logs run ID; existing runs are never overwritten")
    parser.add_argument("--audit-ref", required=True, help="Repository-relative POSIX path to 3A source audit report.json")
    parser.add_argument("--scope-id", required=True, help="Explicit scope_id matching 3A audit and committed 3B catalog head")
    parser.add_argument("--protection-ref", default=None, help="Optional repository-relative POSIX path to Story 1.5 protection snapshot or protection-input")
    parser.add_argument("--manifest", default=None, help="Optional repository-relative POSIX path to cumulative MVG manifest baseline")
    parser.add_argument("--change-intents", default=None, help="Optional repository-relative POSIX path to explicit task change intents JSON")
    return parser


def build_parser() -> argparse.ArgumentParser:
    result = Parser(description=__doc__, allow_abbrev=False)
    return register_arguments(result)


def main(argv=None) -> int:
    output = None
    try:
        args = build_parser().parse_args(argv)
        output = service.create_run_directory(args.root, args.run_id)
    except codec.CodecError as error:
        result = {
            "schema_version": service.SCHEMA,
            "ok": False,
            "stable": False,
            "preview_digest": None,
            "diagnostics": [error.diagnostic.to_dict()],
            "report_path": None,
            "authorization": dict(service.AUTHORIZATION),
        }
        print(json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(",", ":")))
        return 2

    try:
        result = service.preview_task_changes(
            args.root,
            plan_id=args.plan_id,
            scope_id=args.scope_id,
            audit_ref=args.audit_ref,
            protection_ref=args.protection_ref,
            manifest_ref=args.manifest,
            change_intents_ref=args.change_intents,
        )
    except Exception as error:
        result = {
            "schema_version": service.SCHEMA,
            "ok": False,
            "stable": False,
            "preview_digest": None,
            "diagnostics": [
                service._diag(
                    codec.ReasonCode.IDENTITY_UNPROVABLE,
                    owning_stage="3C",
                    stage=codec.Stage.BUNDLE,
                    entity_id=args.plan_id,
                    expected="completed task-change preview report",
                    actual=f"{type(error).__name__}: {error}",
                    resume_ref=args.audit_ref,
                )
            ],
            "authorization": dict(service.AUTHORIZATION),
        }

    report_path = None
    result["report_path"] = None
    temporary = output / "report.json.tmp"
    try:
        root_resolved = args.root.resolve(strict=True)
        relative_output = service.protection._output_relative_path(root_resolved, output)
        report_path = relative_output + "/report.json"
        result["report_path"] = report_path
        service.inventory.safe_input(root_resolved, report_path, allow_logs=True)
        payload = json.dumps(result, ensure_ascii=True, allow_nan=False, indent=2) + "\n"
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
        os.replace(temporary, output / "report.json")
    except (OSError, ValueError, codec.CodecError) as error:
        result["ok"] = False
        result["stable"] = False
        result.setdefault("preview_digest", None)
        result["diagnostics"].append(
            error.diagnostic.to_dict()
            if isinstance(error, codec.CodecError)
            else service._diag(
                codec.ReasonCode.CONFLICT,
                owning_stage="3C",
                stage=codec.Stage.PATH,
                entity_id=args.run_id,
                expected="new writable atomic report.json",
                actual=type(error).__name__,
                resume_ref=report_path,
                path=report_path,
            )
        )
        print(json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(",", ":")))
        return 2
    finally:
        temporary.unlink(missing_ok=True)

    print(json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(",", ":")))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
