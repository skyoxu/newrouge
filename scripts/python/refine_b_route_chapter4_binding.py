#!/usr/bin/env python3
"""Governed Chapter 4 production contract and four-part binding CLI; no default B activation."""
import sys

sys.dont_write_bytecode = True

import argparse
from dataclasses import replace
import json
from pathlib import Path

import _b_route_chapter4_binding as service
import _b_route_codec as codec
import _b_route_commit as commit
import _b_route_commit_projection as projection
import _b_route_records as records
import _planning_apply_journal as journal


STAGES = (
    "preview",
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
                "explicit b-route-chapter4-binding stage arguments",
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
        help="Governed Chapter 4 binding stage (preview|prepare|reserve|inspect|apply|verify|publish|read|recover-inspect|recover)",
    )
    parser.add_argument("--operation-id", required=True, help="Stable portable operation ID (FileId)")
    parser.add_argument(
        "--request",
        default=None,
        help="Repository-relative POSIX path to chapter4 binding request JSON (preview/prepare stages only)",
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
    diag_dict = diagnostic.to_dict()
    attribution = service.extract_mismatch_attribution(diag_dict)
    return {
        "status": "blocked",
        "producer": service.PRODUCER,
        "operation_id": operation_id,
        "scope_ids": None,
        "state": None,
        "formal_adoption": False,
        "return_stage": attribution["return_stage"] if attribution else None,
        "mismatch_attribution": attribution,
        **FLAGS,
        "diagnostics": [diag_dict],
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
    needs_request = args.stage in ("preview", "prepare")
    if needs_request != (args.request is not None):
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.INVALID_ARGUMENT,
                codec.Stage.PATH,
                args.operation_id,
                "--request is required on preview/prepare only and forbidden on all other stages",
                {"stage": args.stage, "request_supplied": args.request is not None},
            )
        )
    root = Path(args.root).resolve()
    op_id = args.operation_id
    commit_stage = args.stage in ("apply", "verify", "publish", "read", "recover-inspect", "recover")

    if args.stage == "preview":
        value = service.preview(root, operation_id=op_id, request_ref=args.request)
    elif args.stage == "prepare":
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
                            "published terminal chapter4_binding operation",
                            "unpublished",
                            journal._operation_ref(op_id),
                        )
                    )
            catalog_raw = codec.read_reference_bytes(root, records.CATALOG_PATH)
            catalog_doc = codec.strict_json_loads(catalog_raw)
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
            receipt_ref = projection.reference(receipt_path, raw)
            records._publication_history(root, catalog_raw=catalog_raw, receipt_ref=receipt_ref)
            if op_id not in inv_map:
                selected_receipts = [head["receipt_ref"] for head in catalog_doc.get("scope_heads", [])]
                if receipt_ref not in selected_receipts:
                    raise codec.CodecError(
                        codec.Diagnostic(
                            codec.ReasonCode.UNPUBLISHED,
                            codec.Stage.BUNDLE,
                            op_id,
                            "published receipt selected by catalog.scope_heads",
                            receipt_path,
                            records.CATALOG_PATH,
                        )
                    )
            read_scopes = [s for s in receipt["scopes"] if not s.startswith("file:")] or receipt["scopes"]
            value = commit.read_committed(root, scope_ids=read_scopes)
            # Attach clean-clone extract_stage4_semantics directly from published formal records.
            target_paths = {row["path"] for row in receipt["targets"]}
            stage4_semantics_list = []
            for bref in receipt["binding_refs"]:
                if bref["path"] not in target_paths:
                    continue
                b_raw = codec.read_reference_bytes(root, bref["path"])
                b_checked = records.validate_record(b_raw, path=bref["path"])
                if not b_checked.ok:
                    raise codec.CodecError(b_checked.diagnostic)
                b_doc = codec.strict_json_loads(b_raw)
                b_digest = (
                    codec.raw_digest(b_raw)
                    if bref["verification_mode"] == "raw"
                    else codec.canonical_digest(b_doc)
                )
                if b_digest != bref["digest"]:
                    raise codec.CodecError(
                        codec.Diagnostic(
                            codec.ReasonCode.DIGEST_MISMATCH,
                            codec.Stage.REFERENCE,
                            op_id,
                            bref["digest"],
                            b_digest,
                            bref["path"],
                        )
                    )
                if b_doc.get("stage") == "4":
                    p_ref = b_doc["plan_ref"]
                    p_raw = codec.read_reference_bytes(root, p_ref["path"])
                    p_checked = records.validate_record(p_raw, path=p_ref["path"])
                    if not p_checked.ok:
                        raise codec.CodecError(p_checked.diagnostic)
                    p_doc = codec.strict_json_loads(p_raw)
                    p_digest = (
                        codec.raw_digest(p_raw)
                        if p_ref["verification_mode"] == "raw"
                        else codec.canonical_digest(p_doc)
                    )
                    if p_digest != p_ref["digest"]:
                        raise codec.CodecError(
                            codec.Diagnostic(
                                codec.ReasonCode.DIGEST_MISMATCH,
                                codec.Stage.REFERENCE,
                                op_id,
                                p_ref["digest"],
                                p_digest,
                                p_ref["path"],
                            )
                        )
                    stage4_semantics_list.append(service.extract_stage4_semantics(p_doc, b_doc))
            if not stage4_semantics_list:
                raise codec.CodecError(
                    codec.Diagnostic(
                        codec.ReasonCode.SCHEMA_MISMATCH,
                        codec.Stage.BUNDLE,
                        op_id,
                        "at least one stage=4 binding target produced by receipt",
                        [bref["path"] for bref in receipt["binding_refs"]],
                        receipt_path,
                    )
                )
            value = {**value, "stage4_semantics": stage4_semantics_list}
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
        except OSError as exc:
            raise codec.CodecError(
                codec.Diagnostic(
                    codec.ReasonCode.IDENTITY_UNPROVABLE,
                    codec.Stage.BUNDLE,
                    op_id,
                    "writable chapter4 binding event audit log",
                    f"{type(exc).__name__}: {exc}",
                    f"{service.EVENTS_BASE}/{op_id}/events.jsonl",
                )
            ) from exc
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
        except OSError as exc:
            raise codec.CodecError(
                codec.Diagnostic(
                    codec.ReasonCode.IDENTITY_UNPROVABLE,
                    codec.Stage.BUNDLE,
                    op_id,
                    "writable chapter4 binding event audit log",
                    f"{type(exc).__name__}: {exc}",
                    f"{service.EVENTS_BASE}/{op_id}/events.jsonl",
                )
            ) from exc

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
        **value,
        **FLAGS,
    }


def run(args: argparse.Namespace) -> int:
    sys.dont_write_bytecode = True
    operation_id = getattr(args, "operation_id", None)
    try:
        value = _execute(args)
    except codec.CodecError as error:
        if (
            isinstance(operation_id, str)
            and getattr(args, "root", None)
            and getattr(args, "stage", None) not in ("preview", "inspect", "recover-inspect", "read")
        ):
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
                    "complete governed chapter4 binding operation",
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
