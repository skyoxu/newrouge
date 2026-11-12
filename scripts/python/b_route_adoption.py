#!/usr/bin/env python3
"""Shared adoption and explicit commit stages; no default-route activation."""
import sys

# Inspect must not create bytecode before importing any repository module.
sys.dont_write_bytecode = True

import argparse
from dataclasses import replace
import importlib
import json
from pathlib import Path

import _b_route_codec as codec


FLAGS = {"formal_adoption": False, "readiness": False, "runtime_verified": False}

CONTEXT_HELP = ("--context on inspect/read presents original operation/plan/revision references; "
    "inspect is read-only; read retains its original coordination lock metadata. "
    "Completed-unit reuse/epoch/reopen is unsupported here. No default B activation.")


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.INVALID_ARGUMENT,
            expected="adoption/commit/recover stage arguments", actual=message))


def register_arguments(parser):
    parser.add_argument("--root", default=".")
    parser.add_argument("--origin-profile", help="Existing finite profile; origin-prepare only")
    parser.add_argument("--stage", choices=("origin-prepare", "review-prepare", "review-segmented-preflight", "review-complete", "prepare", "reserve", "inspect",
                                          "apply", "verify", "publish", "read", "recover-inspect", "recover"), required=True)
    parser.add_argument("--context", action="store_true",
        help="Include original retained/published context; inspect/read only, no reuse or resume")
    parser.epilog = CONTEXT_HELP
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--request", help="Complete request reference; review-prepare, review-segmented-preflight or prepare only")
    parser.add_argument('--compensation-review-delivery', choices=(
        'newrouge.b-route-compensation-review-delivery.v3',
        'newrouge.b-route-compensation-review-delivery.v4',
        'newrouge.b-route-qualified-compensation-review-delivery.v1',
        'newrouge.b-route-qualified-compensation-review-delivery.v2',
        'newrouge.b-route-qualified-compensation-review-delivery.v3'),
        help='Explicit compensation review transport; segmented preflight requires qualified delivery.v3')
    parser.set_defaults(func=run)
    return parser


def build_parser():
    return register_arguments(_Parser(description=__doc__))


def _blocked(diagnostic, operation_id):
    if isinstance(operation_id, str):
        try:
            operation_id.encode("utf-8")
        except UnicodeEncodeError:
            operation_id = None
    if diagnostic.entity_id is None and operation_id is not None:
        diagnostic = replace(diagnostic, entity_id=operation_id)
    return {"status": "blocked", "operation_id": operation_id,
        "scope_ids": None, "state": None, **FLAGS,
        "diagnostics": [diagnostic.to_dict()]}


def _emit(value):
    print(json.dumps(value, ensure_ascii=True, allow_nan=False))


def _context_view(args, value, *, receipt=None, receipt_ref=None):
    """Present existing owner identity; never persist or grant reuse eligibility."""
    from copy import deepcopy
    codec.validate_json_value(value)
    if type(value) is not dict:
        raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.INVALID_TYPE,
            entity_id=args.operation_id, expected="service result object",
            actual=type(value).__name__))
    boundary = {"global_planning_completion": "not_established",
        "completed_unit_reuse": "unsupported",
        "reuse_reason": "Completed-unit reuse belongs to the native planner coordinator; operation context only presents retained references",
        "native_resume_performed": False, "default_B_activated": False}
    if receipt is None:
        if value["operation_id"] != args.operation_id:
            raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.CONFLICT,
                entity_id=args.operation_id, expected="same original operation",
                actual=value["operation_id"], resume_ref=value.get("resume_ref")))
        context = {"kind": "retained_operation", "operation_id": value["operation_id"],
            "resume_ref": value["resume_ref"], "state": value["state"],
            "scope_ids": value["scope_ids"], "allocations": value["allocations"],
            "request_digest": value["request_digest"], "frozen_digest": value["frozen_digest"],
            "eligibility": "not granted; original reserve/current-proof gates remain required"}
    else:
        if sorted(value["scope_ids"]) != sorted(receipt["scopes"]):
            raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.CONFLICT,
                entity_id=args.operation_id, expected=receipt["scopes"],
                actual=value["scope_ids"], resume_ref=receipt_ref["path"]))
        original_paths = {receipt_ref["path"],
            *(ref["path"] for ref in receipt["plan_refs"]),
            *(ref["path"] for ref in receipt["binding_refs"])}
        missing = original_paths - set(value["formal_paths"])
        if missing:
            raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.INPUT_STALE,
                entity_id=args.operation_id,
                expected="original receipt and plan/binding refs in protected formal closure",
                actual=sorted(missing), resume_ref=receipt_ref["path"]))
        context = {"kind": "published_operation", "operation_id": receipt["operation_id"],
            "receipt_revision": receipt["revision"], "operation_digest": receipt["operation_digest"],
            "receipt_ref": receipt_ref, "resume_ref": receipt_ref["path"],
            "scope_ids": receipt["scopes"], "plan_refs": receipt["plan_refs"],
            "binding_refs": receipt["binding_refs"],
            "catalog_raw_digest": value["catalog_raw_digest"],
            "input_set_digest": value["input_set_digest"],
            "formal_paths": value["formal_paths"],
            "eligibility": "published reader result only; no completed-unit reuse grant"}
    return {**value, "context": deepcopy({"schema_version":
        "newrouge.b-route-context-view.v1", **context, **boundary})}


def _execute(args):
    codec.validate_json_value(args.operation_id)
    codec.validate_business_id(args.operation_id)
    context_requested = getattr(args, "context", False)
    if type(context_requested) is not bool or context_requested and args.stage not in ("inspect", "read"):
        raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.INVALID_ARGUMENT,
            entity_id=args.operation_id, expected="--context on inspect/read only", actual=args.stage))
    if args.stage == 'origin-prepare':
        if (args.request is not None or getattr(args, 'origin_profile', None) is None
                or getattr(args, 'compensation_review_delivery', None) is not None):
            raise ValueError('origin-prepare requires only explicit finite profile and target root')
        from _b_route_qualified_origin import prepare_origin
        return prepare_origin(Path(args.root).absolute(), operation_id=args.operation_id, profile=args.origin_profile)
    if getattr(args, 'origin_profile', None) is not None:
        raise ValueError('origin-profile is only accepted by origin-prepare')
    if args.stage not in ("review-prepare", "review-segmented-preflight", "review-complete", "prepare", "reserve", "inspect", "apply", "verify", "publish", "read", "recover-inspect", "recover"):
        raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.INVALID_ARGUMENT,
            entity_id=args.operation_id, expected="prepare|reserve|inspect", actual=args.stage))
    if (args.stage in ("review-prepare", "review-segmented-preflight", "prepare")) != (args.request is not None):
        raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.INVALID_ARGUMENT,
            entity_id=args.operation_id, expected="--request on review-prepare, review-segmented-preflight or prepare only",
            actual={"stage": args.stage, "request_supplied": args.request is not None}))
    compensation_delivery = getattr(args, 'compensation_review_delivery', None)
    if compensation_delivery is not None and args.stage not in ('review-prepare','review-segmented-preflight'):
        raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.INVALID_ARGUMENT,
            entity_id=args.operation_id, expected='delivery selection on compensation review-prepare only',
            actual=args.stage))
    commit_stage = args.stage in ("apply", "verify", "publish", "read", "recover-inspect", "recover")
    service = importlib.import_module("_b_route_commit" if commit_stage else "_b_route_adoption")
    root = Path(args.root).absolute()
    if args.stage == "read":
        journal = importlib.import_module('_planning_apply_journal')
        graph = journal.operation_state_graph(root)
        if args.operation_id in graph['resolved_by']:
            resolved = service._resolved_result(args.operation_id, graph['resolved_by'][args.operation_id])
            if context_requested:
                raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.CONFLICT,
                    entity_id=args.operation_id,
                    expected="original receipt context; resolved operations retain their successor route",
                    actual="resolved_by", resume_ref=resolved.get("resume_ref")))
            return resolved
        records = importlib.import_module('_b_route_records')
        path = records.BASE + 'commits/' + args.operation_id + '.json'
        def read_receipt():
            try:
                return codec.read_reference_bytes(root, path)
            except codec.CodecError as error:
                if error.diagnostic.resume_ref is not None:
                    raise
                raise codec.CodecError(replace(error.diagnostic, resume_ref=path)) from error
        raw = read_receipt()
        checked = records.validate_record(raw, path=path)
        if not checked.ok:
            raise codec.CodecError(checked.diagnostic)
        receipt = codec.strict_json_loads(raw)
        if context_requested and receipt['operation_id'] != args.operation_id:
            raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.CONFLICT,
                entity_id=args.operation_id, expected="receipt for original operation ID",
                actual=receipt['operation_id'], resume_ref=path))
        value = service.read_committed(root, scope_ids=receipt['scopes'])
        if context_requested:
            if read_receipt() != raw:
                raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.INPUT_STALE,
                    entity_id=args.operation_id, expected="unchanged original receipt bytes",
                    actual="receipt changed during protected read", resume_ref=path))
            value = _context_view(args, value, receipt=receipt,
                receipt_ref={"path": path, "raw_digest": codec.raw_digest(raw)})
    elif args.stage == 'recover-inspect':
        value = service.inspect_recovery(root, operation_id=args.operation_id)
    elif args.stage == 'recover':
        value = service.recover(root, operation_id=args.operation_id)
    elif commit_stage:
        value = service.execute(root, operation_id=args.operation_id, stage=args.stage)
    elif args.stage == 'review-segmented-preflight':
        value=service.preflight_segmented_compensation(root,operation_id=args.operation_id,
            request_ref=args.request,compensation_delivery=compensation_delivery)
    elif args.stage == "review-prepare":
        delivery_kwargs = {} if compensation_delivery is None else {'compensation_delivery': compensation_delivery}
        value = service.prepare_review(root, operation_id=args.operation_id, request_ref=args.request, **delivery_kwargs)
    elif args.stage == "review-complete":
        value = service.complete_review(root, operation_id=args.operation_id)
    elif args.stage == "prepare":
        value = service.prepare(root, operation_id=args.operation_id, request_ref=args.request)
    elif args.stage == "reserve":
        value = service.reserve(root, operation_id=args.operation_id)
    else:
        value = service.inspect(root, operation_id=args.operation_id)
        if context_requested:
            value = _context_view(args, value)
    codec.validate_json_value(value)
    if type(value) is not dict:
        raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.INVALID_TYPE,
            entity_id=args.operation_id, expected="service result object", actual=type(value).__name__))
    forbidden = {key: default for key, default in FLAGS.items() if not commit_stage or key != 'formal_adoption'}
    if any(value.get(key, False) is not False for key in forbidden):
        raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.CONFLICT,
            entity_id=args.operation_id, expected=FLAGS,
            actual={key: value.get(key) for key in FLAGS}))
    if commit_stage:
        if value.get('formal_adoption', False) is not (value.get('published') is True or value.get('status') == 'committed'):
            raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.CONFLICT,
                expected='formal claim only for validated committed publication', actual=args.stage))
        return {**value, **forbidden}
    return {**value, **FLAGS}


def run(args):
    """Shared by direct CLI and programmatic dev_cli parser dispatch."""
    sys.dont_write_bytecode = True
    operation_id = getattr(args, "operation_id", None)
    try:
        value = _execute(args)
    except codec.CodecError as error:
        _emit(_blocked(error.diagnostic, operation_id))
        return 2
    except ImportError as error:
        _emit(_blocked(codec.Diagnostic(codec.ReasonCode.DEPENDENCY_UNAVAILABLE,
            expected="installed adoption service and its existing dependencies",
            actual=type(error).__name__), operation_id))
        return 2
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
        _emit(_blocked(codec.Diagnostic(codec.ReasonCode.IDENTITY_UNPROVABLE,
            expected="readable supported adoption operation", actual=type(error).__name__), operation_id))
        return 2
    _emit(value)
    return 2 if value.get("status") == "blocked" else 0


def _operation_hint(arguments):
    for index, argument in enumerate(arguments):
        if argument.startswith("--operation-id="):
            return argument.split("=", 1)[1]
        if argument == "--operation-id" and index + 1 < len(arguments):
            return arguments[index + 1]
    return None


def main(argv=None):
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
