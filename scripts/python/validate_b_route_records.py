#!/usr/bin/env python3
"""Print read-only B-route record and candidate-bundle validation as JSON."""

import sys

sys.dont_write_bytecode = True

import argparse
import json
from pathlib import Path

from _b_route_codec import (
    CodecError, Diagnostic, ReasonCode, Stage, read_reference_bytes,
    strict_json_loads, validate_reference_path,
)
from _b_route_records import (
    TaskJoinContext, bundle_failure, record_failure, validate_bundle,
    validate_record,
)


class _Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise CodecError(Diagnostic(
            ReasonCode.INVALID_ARGUMENT,
            expected="record/bundle arguments", actual="invalid CLI arguments",
        ))


def _invalid(expected, actual, *, path=None, pointer=None):
    raise CodecError(Diagnostic(
        ReasonCode.INVALID_ARGUMENT, Stage.DECODE,
        expected={"value": expected, "path": path, "json_pointer": pointer},
        actual=actual,
    ))


def _read(root, path):
    try:
        return read_reference_bytes(root, path)
    except CodecError as error:
        diagnostic = error.diagnostic
        raise CodecError(Diagnostic(
            diagnostic.reason_code, diagnostic.stage, diagnostic.entity_id,
            {"path": path, "value": diagnostic.expected},
            diagnostic.actual, diagnostic.resume_ref,
        )) from None


def _load_carrier(root, path):
    """Read raw candidate bytes without treating the carrier as a B record."""
    value = strict_json_loads(_read(root, path))
    if type(value) is not dict or set(value) != {"records"}:
        _invalid("carrier object with only records", "invalid carrier fields", path=path)
    if type(value["records"]) is not list:
        _invalid("records array", type(value["records"]).__name__, path=path, pointer="/records")
    records = {}
    targets = set()
    for index, row in enumerate(value["records"]):
        pointer = "/records/" + str(index)
        if type(row) is not dict or set(row) != {"path", "source_path"}:
            _invalid("path/source_path object", "invalid carrier row", path=path, pointer=pointer)
        logical = validate_reference_path(row["path"])
        source = validate_reference_path(row["source_path"])
        # Preserve path spelling here: resolving symlinks before '..' can lead
        # somewhere different from lexical normalization. The shared service
        # rejects duplicate actual targets using its contained path resolver.
        target = logical
        if target in targets:
            _invalid("unique candidate paths", "duplicate candidate path", path=path, pointer=pointer + "/path")
        targets.add(target)
        records[logical] = _read(root, source)
    return records


def _parser():
    parser = _Parser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True, parser_class=_Parser)
    record = commands.add_parser("record", help="Validate one record schema and identity")
    record.add_argument("--repo-root", type=Path, required=True)
    record.add_argument("--input", required=True, help="Repository-relative POSIX source path")
    record.add_argument("--record-path", help="Optional exact managed logical record path")
    bundle = commands.add_parser("bundle", help="Validate a complete candidate reference closure")
    bundle.add_argument("--repo-root", type=Path, required=True)
    bundle.add_argument("--input", required=True, help="Repository-relative POSIX carrier path")
    bundle.add_argument("--catalog-path", default="docs/planning/b-route/catalog.v1.json")
    bundle.add_argument("--baseline", help="Optional repository-relative POSIX baseline carrier path")
    bundle.add_argument("--task-master", help="Optional original master JSON path; requires both views")
    bundle.add_argument("--task-back", help="Optional original back-view JSON path; requires master/gameplay")
    bundle.add_argument("--task-gameplay", help="Optional original gameplay-view JSON path; requires master/back")
    return parser


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    mode = arguments[0] if arguments and arguments[0] in ("record", "bundle") else None
    record_path = None
    try:
        args = _parser().parse_args(arguments)
        mode = args.mode
        if mode == "record":
            record_path = args.record_path
            data = _read(args.repo_root, args.input)
            result = validate_record(data, path=record_path)
        else:
            joins = [args.task_master, args.task_back, args.task_gameplay]
            if any(value is not None for value in joins) and not all(value is not None for value in joins):
                _invalid("all three Taskmaster paths or none", "partial Taskmaster context")
            records = _load_carrier(args.repo_root, args.input)
            baseline = _load_carrier(args.repo_root, args.baseline) if args.baseline is not None else None
            task_join = None
            if all(value is not None for value in joins):
                master, back, gameplay = [
                    strict_json_loads(_read(args.repo_root, path)) for path in joins
                ]
                task_join = TaskJoinContext(master, back, gameplay)
            result = validate_bundle(
                records, root=args.repo_root, catalog_path=args.catalog_path,
                baseline=baseline, task_join=task_join,
            )
    except CodecError as error:
        result = (bundle_failure(error.diagnostic) if mode == "bundle"
                  else record_failure(error.diagnostic, path=record_path))
    print(json.dumps(result.to_dict(), ensure_ascii=True, allow_nan=False, separators=(",", ":")))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
