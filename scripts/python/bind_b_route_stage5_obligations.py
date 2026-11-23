#!/usr/bin/env python3
"""Governed Stage-5 MVG obligations or legal other_verification binding CLI; no default B activation."""
import sys

sys.dont_write_bytecode = True

import argparse
from dataclasses import replace
import json
from pathlib import Path

import _b_route_codec as codec
import _b_route_commit as commit
import _b_route_commit_projection as projection
import _b_route_records as records
import _b_route_stage5_obligations as service
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
                "explicit b-route-stage5-obligations stage arguments",
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
        help="Governed Stage-5 obligations stage (preview|prepare|reserve|inspect|apply|verify|publish|read|recover-inspect|recover)",
    )
    parser.add_argument("--operation-id", required=True, help="Stable portable operation ID (FileId)")
    parser.add_argument(
        "--request",
        default=None,
        help="Repository-relative POSIX path to stage5 obligations request JSON (preview/prepare stages only)",
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


def _guard_stage5_operation(root: Path, op_id: str) -> dict:
    """Verify op_id (if present in operation inventory) belongs to stage5_obligations."""
    graph = journal.operation_state_graph(root)
    inv_map = {r["operation_id"]: r for r in graph["operations"]}
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
    return graph


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

    if args.stage == "preview":
        value = service.preview(root, operation_id=op_id, request_ref=args.request)
    elif args.stage == "prepare":
        value = service.prepare(root, operation_id=op_id, request_ref=args.request)
    elif args.stage == "reserve":
        value = service.reserve(root, operation_id=op_id)
    elif args.stage == "inspect":
        value = service.inspect(root, operation_id=op_id)
    elif args.stage == "read":
        graph = _guard_stage5_operation(root, op_id)
        if op_id in graph["resolved_by"]:
            value = commit._resolved_result(op_id, graph["resolved_by"][op_id])
        else:
            inv_map = {r["operation_id"]: r for r in graph["operations"]}
            if op_id in inv_map:
                op_row = inv_map[op_id]
                if not commit.terminal_valid(root, op_row):
                    raise codec.CodecError(
                        codec.Diagnostic(
                            codec.ReasonCode.UNPUBLISHED,
                            codec.Stage.BUNDLE,
                            op_id,
                            "published terminal stage5_obligations operation",
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
            # Load live master tasks (read-only) to evaluate requires_reverification without copying status.
            master_raw = codec.read_reference_bytes(root, service.TRIPLET["master"])
            master_doc = codec.strict_json_loads(master_raw)
            master_tasks = {row["id"]: row for row in master_doc["master"]["tasks"]}
            target_paths = {row["path"] for row in receipt["targets"]}
            stage5_semantics_list = []
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
                if b_doc.get("stage") == "5":
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
                    manifests_map = {}
                    for mref in b_doc.get("manifest_refs", []):
                        m_files = mref.get("files") if type(mref) is dict else None
                        if type(m_files) is not list or not m_files:
                            raise codec.CodecError(
                                codec.Diagnostic(
                                    codec.ReasonCode.INVALID_REFERENCE,
                                    codec.Stage.REFERENCE,
                                    op_id,
                                    "nonempty manifest_ref.files",
                                    mref,
                                    bref["path"],
                                )
                            )
                        for frow in m_files:
                            m_rel = codec.validate_reference_path(frow["path"])
                            m_raw = codec.read_reference_bytes(root, m_rel)
                            actual_dg = codec.raw_digest(m_raw)
                            if actual_dg != frow["raw_digest"]:
                                raise codec.CodecError(
                                    codec.Diagnostic(
                                        codec.ReasonCode.DIGEST_MISMATCH,
                                        codec.Stage.REFERENCE,
                                        op_id,
                                        frow["raw_digest"],
                                        actual_dg,
                                        m_rel,
                                    )
                                )
                            m_doc, _m_sha = service._validate_manifest_decoupled(
                                root=root,
                                manifest_rel=m_rel,
                                manifest_raw=m_raw,
                                master_tasks=master_tasks,
                                entity_id=m_rel,
                            )
                            manifests_map[m_rel] = m_doc
                    stage5_semantics_list.append(
                        service.extract_stage5_semantics(
                            p_doc, b_doc, master_tasks=master_tasks, manifests=manifests_map
                        )
                    )
            if not stage5_semantics_list:
                raise codec.CodecError(
                    codec.Diagnostic(
                        codec.ReasonCode.SCHEMA_MISMATCH,
                        codec.Stage.BUNDLE,
                        op_id,
                        "at least one stage=5 binding target produced by receipt",
                        [bref["path"] for bref in receipt["binding_refs"]],
                        receipt_path,
                    )
                )
            value = {**value, "stage5_semantics": stage5_semantics_list}
    elif args.stage == "recover-inspect":
        _guard_stage5_operation(root, op_id)
        value = commit.inspect_recovery(root, operation_id=op_id)
    elif args.stage == "recover":
        _guard_stage5_operation(root, op_id)
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
                    "writable stage5 obligations event audit log",
                    f"{type(exc).__name__}: {exc}",
                    f"{service.EVENTS_BASE}/{op_id}/events.jsonl",
                )
            ) from exc
    else:
        _guard_stage5_operation(root, op_id)
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
                    "writable stage5 obligations event audit log",
                    f"{type(exc).__name__}: {exc}",
                    f"{service.EVENTS_BASE}/{op_id}/events.jsonl",
                )
            ) from exc
    return {
        "status": value.get("status", "ok"),
        "producer": service.PRODUCER,
        **value,
        **FLAGS,
    }


def run(args: argparse.Namespace) -> int:
    try:
        payload = _execute(args)
    except codec.CodecError as error:
        _emit(_blocked(error.diagnostic, getattr(args, "operation_id", None)))
        return 2 if error.diagnostic.reason_code is codec.ReasonCode.INVALID_ARGUMENT else 1
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        diagnostic = codec.Diagnostic(
            codec.ReasonCode.IDENTITY_UNPROVABLE,
            codec.Stage.BUNDLE,
            getattr(args, "operation_id", None),
            "complete governed stage5 obligations stage",
            f"{type(error).__name__}: {error}",
            None,
        )
        _emit(_blocked(diagnostic, getattr(args, "operation_id", None)))
        return 1
    _emit(payload)
    return 1 if payload.get("status") == "blocked" else 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except codec.CodecError as error:
        _emit(_blocked(error.diagnostic, None))
        return 2
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
