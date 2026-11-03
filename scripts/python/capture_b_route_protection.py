#!/usr/bin/env python3
"""Capture, verify or compare read-only mature protection candidates in new logs."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

import _b_route_codec as codec
import _b_route_inventory as inventory
import _b_route_protection as protection


class _ArgumentError(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _ArgumentError(message)


def _write(output: Path, name: str, value: dict) -> None:
    with (output / name).open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    for command in ("capture", "verify", "compare"):
        child = subparsers.add_parser(command)
        child.add_argument("--root", required=True, type=Path)
        child.add_argument("--run-id", required=True)
        if command in ("capture", "compare"):
            child.add_argument("--epics", required=True)
            child.add_argument("--historical-inventory")
        if command == "verify":
            child.add_argument("--snapshot", required=True)
        if command == "compare":
            child.add_argument("--baseline", required=True)
    output = None
    try:
        args = parser.parse_args(argv)
        inventory.require_runtime()
        root = args.root.absolute()
        if not root.is_dir():
            raise _ArgumentError("Repository root must be an existing directory")
        inventory.validate_git_root(root)
        output = protection.create_run_directory(root, args.run_id)
        if args.command == "capture":
            capture = protection.collect_protection(root, args.epics, historical_inventory=args.historical_inventory)
            protection.write_capture(output, capture)
            result = {"ok": capture.snapshot["capture_complete"], "command": args.command,
                "output": output.relative_to(root).as_posix(), "snapshot_digest": capture.snapshot["snapshot_digest"],
                "capture_complete": capture.snapshot["capture_complete"], "stable": capture.snapshot["stable"],
                "inventory_diagnostics": capture.snapshot["inventory"]["diagnostics"],
                "diagnostics": capture.snapshot["diagnostics"], "authorization": dict(protection.AUTHORIZATION)}
            if not result["ok"]:
                result["diagnostics"] = list(result["diagnostics"]) + [
                    codec.Diagnostic(codec.ReasonCode.IDENTITY_UNPROVABLE, codec.Stage.CONTENT,
                        expected={"path": item.get("location"), "value": "valid current inventory input"},
                        actual={"path": item.get("location"), "code": item.get("code"), "message": item.get("message")},
                        resume_ref=item.get("location")).to_dict()
                    for item in result["inventory_diagnostics"] if item.get("severity") == "error"]
        elif args.command == "compare":
            compared = protection.compare_protection(root, args.baseline, args.epics,
                historical_inventory=args.historical_inventory)
            protection.write_capture(output, compared.current)
            _write(output, "comparison.json", compared.report)
            result = {**compared.report, "command": args.command, "output": output.relative_to(root).as_posix()}
        else:
            result = {**protection.verify_protection(root, args.snapshot), "command": args.command,
                "output": output.relative_to(root).as_posix()}
            _write(output, "verification.json", result)
        _write(output, "result.json", result)
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result["ok"] else 1
    except (_ArgumentError, codec.CodecError, OSError, ValueError) as error:
        if isinstance(error, codec.CodecError):
            diagnostic = error.diagnostic.to_dict()
        else:
            diagnostic = codec.Diagnostic(codec.ReasonCode.INVALID_ARGUMENT if output is None else codec.ReasonCode.IDENTITY_UNPROVABLE,
                codec.Stage.CONTENT, expected="valid read-only protection command and inputs",
                actual=str(error)).to_dict()
        result = {"ok": False, "diagnostics": [diagnostic], "authorization": dict(protection.AUTHORIZATION)}
        if output is not None:
            try:
                _write(output, "failure.json", result)
            except OSError:
                pass
        print(json.dumps(result, ensure_ascii=False))
        return 2 if output is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
