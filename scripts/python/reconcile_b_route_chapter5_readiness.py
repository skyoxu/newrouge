#!/usr/bin/env python3
"""B-route Chapter 5 same-source reconciliation and readiness CLI."""
import sys

sys.dont_write_bytecode = True

import argparse
import json
from pathlib import Path
import re

import _b_route_chapter5_readiness as service
import _b_route_codec as codec
import _b_route_input_set as input_set
import _b_route_task_resolver as resolver
import chapter5_semantic_reconciliation as ch5


STAGES = ("preview", "reconcile", "verify", "check-readiness", "read")
_RECONCILE_STAGES = frozenset({"preview", "reconcile"})
_READONLY_STAGES = frozenset({"verify", "check-readiness", "read"})


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.INVALID_ARGUMENT,
                codec.Stage.PATH,
                None,
                "explicit --stage (preview|reconcile|verify|check-readiness|read) and --task-id",
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
        "--stage",
        choices=STAGES,
        required=True,
        help="Chapter 5 readiness operation (preview|reconcile|verify|check-readiness|read)",
    )
    parser.add_argument(
        "--task-id",
        required=True,
        help="Positive integer master Task ID",
    )
    parser.add_argument(
        "--decisions",
        default=None,
        help="Repository-relative POSIX path to Chapter 5 semantic reconciliation decisions JSON (preview/reconcile only)",
    )
    parser.add_argument(
        "--operation",
        default=None,
        help="Optional operation name checked against allowed_a_operations",
    )
    parser.add_argument(
        "--audit-ref",
        action="append",
        default=[],
        help="Optional explicit 3A source audit report.json/event.json path for read-only proof verification (repeatable, preview/reconcile only)",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Optional repository-relative logs/... path for reconciliation JSON (output on reconcile; reconciliation input alias on verify/check-readiness/read)",
    )
    parser.add_argument(
        "--readiness-out",
        default=None,
        help="Optional repository-relative logs/... path for readiness JSON (preview/reconcile only)",
    )
    parser.add_argument(
        "--reconciliation",
        default=None,
        help="Optional repository-relative path to reconciliation JSON (verify/check-readiness/read stages)",
    )
    parser.add_argument(
        "--readiness",
        default=None,
        help="Optional repository-relative path to readiness JSON (verify/check-readiness/read stages)",
    )
    parser.add_argument(
        "--lock-mode",
        choices=("none", "scope"),
        default="none",
        help="Locking mode for verify/check-readiness/read: 'none' (default, zero writes/locks) or 'scope' (business-scope review_only=True guard)",
    )
    parser.add_argument(
        "--no-latest",
        action="store_true",
        help="Do not update logs/ci/chapter5/*/latest.json during reconcile",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate reconcile without writing reconciliation/readiness/technical-debt artifacts (preview/reconcile only)",
    )
    parser.add_argument(
        "--record-technical-debt",
        action="store_true",
        help="Record eligible P2..P4 findings in docs/technical-debt.md when allow_concerns=True (preview/reconcile only)",
    )
    parser.add_argument(
        "--require-full-audit-proof",
        action="store_true",
        help="Require at least one full read-only verified 3A source_audit proof (preview/reconcile only)",
    )
    return parser


def build_parser() -> argparse.ArgumentParser:
    return register_arguments(_Parser(description=__doc__, allow_abbrev=False))


def _parse_strict_task_id(raw: str) -> int:
    if type(raw) is not str or re.fullmatch(r"[1-9][0-9]*", raw) is None:
        raise codec.CodecError(
            codec.Diagnostic(
                codec.ReasonCode.INVALID_ARGUMENT,
                codec.Stage.CONTENT,
                None,
                "positive integer --task-id",
                raw,
                None,
            )
        )
    return codec.validate_task_id(int(raw))


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":")))


def _invalid_arg(task_id: int, expected: str, actual) -> None:
    raise codec.CodecError(
        codec.Diagnostic(
            codec.ReasonCode.INVALID_ARGUMENT,
            codec.Stage.PATH,
            str(task_id),
            expected,
            actual,
            None,
        )
    )


def _preview_json_if_file(root_path: Path, raw_rel: str | None) -> dict | None:
    if not raw_rel:
        return None
    try:
        target, _rel = service._validate_log_path(root_path, raw_rel, require_logs=False)
        if not target.is_file():
            return None
        loaded = codec.strict_json_loads(target.read_bytes())
        return loaded if type(loaded) is dict else None
    except (codec.CodecError, OSError):
        return None


def main(argv=None) -> int:
    sys.dont_write_bytecode = True
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
        task_id = _parse_strict_task_id(args.task_id)
        if args.operation is not None:
            resolver._validate_operation(args.operation)
        lock_mode = input_set._validate_lock_mode(args.lock_mode)

        if args.stage in _RECONCILE_STAGES:
            if not args.decisions:
                _invalid_arg(task_id, f"--decisions is required for --stage {args.stage}", None)
            if args.reconciliation is not None:
                _invalid_arg(task_id, f"--reconciliation is not allowed on --stage {args.stage}", args.reconciliation)
            if args.readiness is not None:
                _invalid_arg(task_id, f"--readiness is not allowed on --stage {args.stage}", args.readiness)
        else:
            if args.decisions is not None:
                _invalid_arg(task_id, f"--decisions is only valid on preview/reconcile, not --stage {args.stage}", args.decisions)
            if args.dry_run:
                _invalid_arg(task_id, f"--dry-run is only valid on preview/reconcile, not --stage {args.stage}", True)
            if args.record_technical_debt:
                _invalid_arg(task_id, f"--record-technical-debt is only valid on preview/reconcile, not --stage {args.stage}", True)
            if args.require_full_audit_proof:
                _invalid_arg(task_id, f"--require-full-audit-proof is only valid on preview/reconcile, not --stage {args.stage}", True)
            if args.no_latest:
                _invalid_arg(task_id, f"--no-latest is only valid on preview/reconcile, not --stage {args.stage}", True)
            if args.audit_ref:
                _invalid_arg(task_id, f"--audit-ref is only valid on preview/reconcile, not --stage {args.stage}", list(args.audit_ref))
            if args.readiness_out is not None:
                _invalid_arg(task_id, f"--readiness-out is only valid on preview/reconcile, not --stage {args.stage}", args.readiness_out)
    except codec.CodecError as error:
        payload = {
            "schema_version": service.B_ROUTE_SCHEMA,
            "ok": False,
            "status": "blocked",
            "readiness": "BLOCKED",
            "closure_allowed": False,
            "runtime_verified": False,
            "default_b_enabled": False,
            "diagnostics": [error.diagnostic.to_dict()],
        }
        _emit(payload)
        return 2

    if args.stage in _RECONCILE_STAGES:
        write_artifacts = (args.stage == "reconcile") and (not bool(args.dry_run))
        res = service.reconcile_b_route_chapter5(
            root_path,
            task_id=task_id,
            decisions=args.decisions,
            operation=args.operation,
            audit_refs=list(args.audit_ref or []),
            out_path=args.out,
            readiness_path=args.readiness_out,
            write_artifacts=write_artifacts,
            write_latest=not bool(args.no_latest),
            record_technical_debt=bool(args.record_technical_debt),
            require_full_audit_proof=bool(args.require_full_audit_proof),
        )
        # Strip full embedded docs from stdout summary to keep CLI output compact and deterministic.
        out_payload = {k: v for k, v in res.items() if k not in ("reconciliation_doc", "readiness_doc")}
        _emit(out_payload)
        return 0 if out_payload["ok"] else 1

    rec_arg = args.reconciliation or args.out
    rdy_arg = args.readiness

    if args.stage in ("verify", "read"):
        res = service.verify_b_route_chapter5_readiness(
            root_path,
            task_id=task_id,
            readiness_path=rdy_arg,
            reconciliation_path=rec_arg,
            operation=args.operation,
            lock_mode=lock_mode,
        )
        if args.stage == "verify":
            out_payload = {k: v for k, v in res.items() if k != "readiness_doc"}
        else:
            out_payload = dict(res)
        _emit(out_payload)
        return 0 if out_payload["ok"] else 1

    # check-readiness: unified load_task_readiness bridge (preserves A when zero B traces, enforces B when B traces exist).
    rdy_preview = _preview_json_if_file(root_path, rdy_arg)
    rec_preview = _preview_json_if_file(root_path, rec_arg)
    presence = service.detect_repo_b_route_presence(
        root_path,
        task_id,
        reconciliation=rec_preview,
        readiness=rdy_preview,
    )
    bridged = None
    if presence["has_b_traces"]:
        bridged = service.load_b_route_task_readiness(
            root_path,
            str(task_id),
            readiness_path=rdy_arg,
            reconciliation_path=rec_arg,
            operation=args.operation,
            lock_mode=lock_mode,
        )
    if bridged is not None:
        ok, payload, reason = bridged
    else:
        ok, payload, reason = ch5.load_task_readiness(root_path, str(task_id))
    out_payload = {
        "schema_version": service.B_ROUTE_SCHEMA,
        "ok": bool(ok),
        "status": "ok" if ok else "blocked",
        "task_id": task_id,
        "operation": args.operation,
        "reason": reason,
        "readiness": payload.get("readiness") if isinstance(payload, dict) else None,
        "route": payload.get("route") if isinstance(payload, dict) else None,
        "input_set_digest": payload.get("input_set_digest") if isinstance(payload, dict) else None,
        "reconciliation_path": payload.get("reconciliation_path") if isinstance(payload, dict) else rec_arg,
        "readiness_path": payload.get("readiness_path") if isinstance(payload, dict) else rdy_arg,
        "requires_chapter6_reverification": bool(payload.get("requires_chapter6_reverification", False))
        if isinstance(payload, dict)
        else False,
        "return_stage": payload.get("return_stage") if isinstance(payload, dict) else None,
        "diagnostics": payload.get("diagnostics", []) if isinstance(payload, dict) else [],
        "runtime_verified": False,
        "default_b_enabled": False,
    }
    _emit(out_payload)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
