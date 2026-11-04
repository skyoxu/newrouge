#!/usr/bin/env python3
"""Preview explicit B-route migration bytes without applying or publishing."""
import sys
sys.dont_write_bytecode = True

import argparse
import json
from pathlib import Path

import _b_route_codec as codec
import _b_route_preflight as service


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise codec.CodecError(codec.Diagnostic(codec.ReasonCode.INVALID_ARGUMENT,
            expected="explicit root/epics/protection-input/candidate/intents/run-id; no apply option",
            actual=message))


def parser():
    result = Parser(description=__doc__, allow_abbrev=False)
    result.add_argument("--root", type=Path, required=True, help="Explicit repository root")
    result.add_argument("--epics", required=True, help="Repository-relative POSIX epics path")
    result.add_argument("--protection-input", required=True, help="Story 1.5 protection input path")
    result.add_argument("--candidate", required=True, help="Original path/source_path carrier")
    result.add_argument("--intents", required=True, help="Versioned external intent and raw input bindings")
    result.add_argument("--run-id", required=True, help="Fresh logs run ID; existing runs are never overwritten")
    return result


def main(argv=None):
    output = None
    try:
        args = parser().parse_args(argv)
        output = service.create_run_directory(args.root, args.run_id)
    except codec.CodecError as error:
        result = {"ok": False, "diagnostics": [error.diagnostic.to_dict()], "report_path": None,
                  "authorization": dict(service.protection.AUTHORIZATION)}
        print(json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(",", ":")))
        return 2
    result = service.preflight(args.root, args.epics, args.protection_input, args.candidate, args.intents)
    report_path = None
    result["report_path"] = None
    try:
        # The Story 1.5 guard checks every original ancestor before comparing
        # physical identities; caller and output may use different 8.3 spellings.
        relative_output = service.protection._output_relative_path(args.root.absolute(), output)
        report_path = relative_output + "/report.json"
        result["report_path"] = report_path
        service.inventory.safe_input(args.root.absolute(), report_path, allow_logs=True)
        with (output / "report.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result, stream, ensure_ascii=True, allow_nan=False, indent=2)
            stream.write("\n")
    except (OSError, ValueError, codec.CodecError) as error:
        result["ok"] = False
        result["diagnostics"].append(error.diagnostic.to_dict() if isinstance(error, codec.CodecError)
            else codec.Diagnostic(codec.ReasonCode.CONFLICT, codec.Stage.PATH,
                expected="new writable report", actual=type(error).__name__, resume_ref=report_path).to_dict())
        print(json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(",", ":")))
        return 2
    print(json.dumps(result, ensure_ascii=True, allow_nan=False, separators=(",", ":")))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
