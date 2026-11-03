#!/usr/bin/env python3
"""Print read-only B-route content/reference identity results as JSON."""

import sys

sys.dont_write_bytecode = True

import argparse
import json
from pathlib import Path

from _b_route_codec import (
    CodecError, Diagnostic, ReasonCode, failure_result,
    read_reference_bytes, verify_content_file, verify_reference,
)


class _Parser(argparse.ArgumentParser):
    def error(self, _message):
        raise CodecError(Diagnostic(ReasonCode.INVALID_ARGUMENT,
                                    expected="content/reference arguments", actual="invalid CLI arguments"))


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    kind = arguments[0] if arguments and arguments[0] in ("content", "reference") else None
    try:
        parser = _Parser(description=__doc__)
        commands = parser.add_subparsers(dest="mode", required=True, parser_class=_Parser)
        content = commands.add_parser("content", help="Check strict JSON content identity")
        content.add_argument("--repo-root", required=True, type=Path)
        content.add_argument("--path", required=True, help="Repository-relative POSIX record path")
        reference = commands.add_parser("reference", help="Check a complete typed reference and its target")
        reference.add_argument("--repo-root", required=True, type=Path)
        reference.add_argument("--reference", required=True, help="Repository-relative POSIX typed-reference JSON path")
        args = parser.parse_args(arguments)
        kind = args.mode
        if kind == "content":
            result = verify_content_file(args.repo_root, args.path)
        else:
            result = verify_reference(args.repo_root, read_reference_bytes(args.repo_root, args.reference))
    except CodecError as error:
        result = failure_result(kind, error.diagnostic)
    print(json.dumps(result.to_dict(), ensure_ascii=True, allow_nan=False, separators=(",", ":")))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
