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


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.INVALID_ARGUMENT,
            expected="review-prepare|review-complete|prepare|reserve|inspect arguments", actual=message))


def register_arguments(parser):
    parser.add_argument("--root", default=".")
    parser.add_argument('--origin-profile', help='Finite profile; origin-prepare only')
    parser.add_argument("--stage", choices=("origin-prepare", "review-prepare", "review-complete", "prepare", "reserve", "inspect",
                                          "apply", "verify", "publish", "read"), required=True)
    parser.add_argument("--operation-id", required=True)
    parser.add_argument("--request", help="Complete request reference; review-prepare or prepare only")
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


def _execute(args):
    codec.validate_json_value(args.operation_id)
    codec.validate_business_id(args.operation_id)
    if args.stage == 'origin-prepare':
        if args.request is not None or args.origin_profile is None:
            raise ValueError('origin-prepare requires only explicit finite profile and target root')
        from _b_route_qualified_origin import prepare_origin
        return prepare_origin(Path(args.root).absolute(), operation_id=args.operation_id, profile=args.origin_profile)
    if getattr(args, 'origin_profile', None) is not None:
        raise ValueError('origin-profile is only accepted by origin-prepare')
    if args.stage not in ("review-prepare", "review-complete", "prepare", "reserve", "inspect", "apply", "verify", "publish", "read"):
        raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.INVALID_ARGUMENT,
            entity_id=args.operation_id, expected="prepare|reserve|inspect", actual=args.stage))
    if (args.stage in ("review-prepare", "prepare")) != (args.request is not None):
        raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.INVALID_ARGUMENT,
            entity_id=args.operation_id, expected="--request on review-prepare or prepare only",
            actual={"stage": args.stage, "request_supplied": args.request is not None}))
    commit_stage = args.stage in ("apply", "verify", "publish", "read")
    service = importlib.import_module("_b_route_commit" if commit_stage else "_b_route_adoption")
    root = Path(args.root).absolute()
    if args.stage == "read":
        records = importlib.import_module('_b_route_records')
        path = records.BASE + 'commits/' + args.operation_id + '.json'
        raw = codec.read_reference_bytes(root, path)
        checked = records.validate_record(raw, path=path)
        if not checked.ok:
            raise codec.CodecError(checked.diagnostic)
        value = service.read_committed(root, scope_ids=codec.strict_json_loads(raw)['scopes'])
    elif commit_stage:
        value = service.execute(root, operation_id=args.operation_id, stage=args.stage)
    elif args.stage == "review-prepare":
        value = service.prepare_review(root, operation_id=args.operation_id, request_ref=args.request)
    elif args.stage == "review-complete":
        value = service.complete_review(root, operation_id=args.operation_id)
    elif args.stage == "prepare":
        value = service.prepare(root, operation_id=args.operation_id, request_ref=args.request)
    elif args.stage == "reserve":
        value = service.reserve(root, operation_id=args.operation_id)
    else:
        value = service.inspect(root, operation_id=args.operation_id)
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
