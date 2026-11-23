#!/usr/bin/env python3
"""Governed 3C triplet compilation and 3C binding nine-stage CLI; no default B activation."""
import sys

sys.dont_write_bytecode = True

import argparse
from dataclasses import replace
import json
from pathlib import Path

import _b_route_codec as codec
import _b_route_commit as commit
import _b_route_records as records
import _b_route_task_compilation as service
import _planning_apply_journal as journal


STAGES = (
    "prepare",
    "reserve",
    "inspect",
    "apply",
    "verify",
    "publish",
    "read",
    "recover-inspect",
    "recover",
)
FLAGS = {
    "readiness": False,
    "runtime_verified": False,
    "default_b_enabled": False,
}


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.INVALID_ARGUMENT,
                codec.Stage.PATH,
                None,
                "explicit b-route-task-compile stage arguments",
                message,
                None,
            )
        )


def register_arguments(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser.add_argument("--root", default=".", help="Explicit repository root")
    parser.add_argument(
        "--stage",
        choices=STAGES,
        required=True,
        help="Governed 3C task compilation stage (prepare|reserve|inspect|apply|verify|publish|read|recover-inspect|recover)",
    )
    parser.add_argument("--operation-id", required=True, help="Stable portable operation ID (FileId)")
    parser.add_argument(
        "--request",
        default=None,
        help="Repository-relative POSIX path to task compilation request JSON (prepare stage only)",
    )
    parser.set_defaults(func=run)
    return parser


def build_parser() -> argparse.ArgumentParser:
    return register_arguments(_Parser(description=__doc__, allow_abbrev=False))


def _blocked(diagnostic: codec.Diagnostic, operation_id: str | None) -> dict:
    if isinstance(operation_id, str):
        try:
            operation_id.encode("utf-8")
        except UnicodeEncodeError:
            operation_id = None
    if diagnostic.entity_id is None and operation_id is not None:
        diagnostic = replace(diagnostic, entity_id=operation_id)
    return {
        "status": "blocked",
        "producer": service.PRODUCER,
        "operation_id": operation_id,
        "scope_ids": None,
        "state": None,
        "formal_adoption": False,
        "chapter4_5_required": True,
        "chapter6_authorized": False,
        **FLAGS,
        "diagnostics": [diagnostic.to_dict()],
    }


def _emit(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=True, allow_nan=False))


def _execute(args: argparse.Namespace) -> dict:
    codec.validate_json_value(args.operation_id)
    service._validate_file_id(args.operation_id, "operation_id")
    if args.stage not in STAGES:
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.INVALID_ARGUMENT,
                codec.Stage.PATH,
                args.operation_id,
                "|".join(STAGES),
                args.stage,
            )
        )
    if (args.stage == "prepare") != (args.request is not None):
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.INVALID_ARGUMENT,
                codec.Stage.PATH,
                args.operation_id,
                "--request is required on prepare only and forbidden on all other stages",
                {"stage": args.stage, "request_supplied": args.request is not None},
            )
        )
    root = Path(args.root).resolve()
    op_id = args.operation_id
    commit_stage = args.stage in ("apply", "verify", "publish", "read", "recover-inspect", "recover")

    if args.stage == "prepare":
        value = service.prepare(root, operation_id=op_id, request_ref=args.request)
    elif args.stage == "reserve":
        value = service.reserve(root, operation_id=op_id)
    elif args.stage == "inspect":
        value = service.inspect(root, operation_id=op_id)
    elif args.stage == "read":
        graph = journal.operation_state_graph(root)
        if op_id in graph["resolved_by"]:
            value = commit._resolved_result(op_id, graph["resolved_by"][op_id])
        else:
            inv_map = {r["operation_id"]: r for r in journal.operation_inventory(root)}
            if op_id in inv_map:
                op_row = inv_map[op_id]
                if op_row["schema_version"] != service.OPERATION_SCHEMA:
                    raise codec.CodecError(
                        codec.Diagnostic(
                            codec.ReasonCode.SCHEMA_MISMATCH,
                            codec.Stage.BUNDLE,
                            op_id,
                            service.OPERATION_SCHEMA,
                            op_row["schema_version"],
                            journal._operation_ref(op_id),
                        )
                    )
                if not commit.terminal_valid(root, op_row):
                    raise codec.CodecError(
                        codec.Diagnostic(
                            codec.ReasonCode.UNPUBLISHED,
                            codec.Stage.BUNDLE,
                            op_id,
                            "published terminal task_compilation operation",
                            "unpublished",
                            journal._operation_ref(op_id),
                        )
                    )
            receipt_path = records.BASE + "commits/" + op_id + ".json"
            raw = codec.read_reference_bytes(root, receipt_path)
            checked = records.validate_record(raw, path=receipt_path)
            if not checked.ok:
                raise codec.CodecError(checked.diagnostic)
            receipt = codec.strict_json_loads(raw)
            if receipt["operation_id"] != op_id:
                raise codec.CodecError(
                    codec.Diagnostic(
                        codec.ReasonCode.CONFLICT,
                        codec.Stage.BUNDLE,
                        op_id,
                        "receipt matching operation_id",
                        receipt["operation_id"],
                        receipt_path,
                    )
                )
            if not any(t["verification_mode"] == "task_definition_projection" for t in receipt["targets"]):
                raise codec.CodecError(
                    codec.Diagnostic(
                        codec.ReasonCode.SCHEMA_MISMATCH,
                        codec.Stage.BUNDLE,
                        op_id,
                        "task_compilation receipt with task_definition_projection targets",
                        receipt_path,
                        receipt_path,
                    )
                )
            read_scopes = [s for s in receipt["scopes"] if not s.startswith("file:")] or receipt["scopes"]
            value = commit.read_committed(root, scope_ids=read_scopes)
    elif args.stage == "recover-inspect":
        value = commit.inspect_recovery(root, operation_id=op_id)
    elif args.stage == "recover":
        value = commit.recover(root, operation_id=op_id)
        try:
            event_log = service.append_event(
                root,
                op_id,
                "recover",
                str(value.get("state") or value.get("status") or "recovered"),
                {"published": value.get("published"), "noop": value.get("noop")},
            )
            value = {**value, "event_log": event_log}
        except OSError:
            pass
    else:
        value = commit.execute(root, operation_id=op_id, stage=args.stage)
        try:
            event_log = service.append_event(
                root,
                op_id,
                args.stage,
                str(value.get("state") or args.stage),
                {"published": value.get("published"), "noop": value.get("noop")},
            )
            value = {**value, "event_log": event_log}
        except OSError:
            pass

    codec.validate_json_value(value)
    if type(value) is not dict:
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.INVALID_TYPE,
                codec.Stage.BUNDLE,
                op_id,
                "service result object",
                type(value).__name__,
            )
        )
    for key, expected_val in FLAGS.items():
        if value.get(key, False) is not expected_val:
            raise codec.CodecError(
                codec.Diagnostic(
                    codec.ReasonCode.CONFLICT,
                    codec.Stage.BUNDLE,
                    op_id,
                    FLAGS,
                    {k: value.get(k) for k in FLAGS},
                )
            )
    if commit_stage:
        expected_formal = value.get("published") is True or value.get("status") == "committed"
        if value.get("formal_adoption", False) is not expected_formal:
            raise codec.CodecError(
                codec.Diagnostic(
                    codec.ReasonCode.CONFLICT,
                    codec.Stage.BUNDLE,
                    op_id,
                    "formal_adoption only for validated committed publication",
                    args.stage,
                )
            )
    return {
        "producer": service.PRODUCER,
        "chapter4_5_required": True,
        "chapter6_authorized": False,
        **value,
        **FLAGS,
    }


def run(args: argparse.Namespace) -> int:
    sys.dont_write_bytecode = True
    operation_id = getattr(args, "operation_id", None)
    try:
        value = _execute(args)
    except codec.CodecError as error:
        if isinstance(operation_id, str) and getattr(args, "root", None):
            try:
                service._validate_file_id(operation_id, "operation_id")
                service.append_event(
                    Path(args.root).resolve(),
                    operation_id,
                    str(getattr(args, "stage", "unknown")),
                    "blocked",
                    {"reason_code": error.diagnostic.reason_code.value},
                )
            except (codec.CodecError, OSError, ValueError):
                pass
        _emit(_blocked(error.diagnostic, operation_id))
        return 2
    except (OSError, ValueError, TypeError, KeyError, AttributeError, RuntimeError) as error:
        _emit(
            _blocked(
                codec.Diagnostic(
                    codec.ReasonCode.IDENTITY_UNPROVABLE,
                    codec.Stage.BUNDLE,
                    operation_id,
                    "complete governed task compilation operation",
                    f"{type(error).__name__}: {error}",
                ),
                operation_id,
            )
        )
        return 2
    _emit(value)
    return 2 if value.get("status") == "blocked" else 0


def _operation_hint(arguments: list[str]) -> str | None:
    for index, argument in enumerate(arguments):
        if argument.startswith("--operation-id="):
            return argument.split("=", 1)[1]
        if argument == "--operation-id" and index + 1 < len(arguments):
            return arguments[index + 1]
    return None


def main(argv=None) -> int:
    sys.dont_write_bytecode = True
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        args = build_parser().parse_args(arguments)
    except codec.CodecError as error:
        _emit(_blocked(error.diagnostic, _operation_hint(arguments)))
        return 2
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
