#!/usr/bin/env python3
"""Thin offline adoption prepare/reserve/inspect entry; no publication authority."""
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
    parser.add_argument("--stage", choices=("review-prepare", "review-complete", "prepare", "reserve", "inspect"), required=True)
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
    if args.stage not in ("review-prepare", "review-complete", "prepare", "reserve", "inspect"):
        raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.INVALID_ARGUMENT,
            entity_id=args.operation_id, expected="prepare|reserve|inspect", actual=args.stage))
    if (args.stage in ("review-prepare", "prepare")) != (args.request is not None):
        raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.INVALID_ARGUMENT,
            entity_id=args.operation_id, expected="--request on review-prepare or prepare only",
            actual={"stage": args.stage, "request_supplied": args.request is not None}))
    service = importlib.import_module("_b_route_adoption")
    root = Path(args.root).absolute()
    if args.stage == "review-prepare":
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
    if any(value.get(key, False) is not False for key in FLAGS):
        raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.CONFLICT,
            entity_id=args.operation_id, expected=FLAGS,
            actual={key: value.get(key) for key in FLAGS}))
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
