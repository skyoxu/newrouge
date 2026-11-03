#!/usr/bin/env python3
"""Write a read-only baseline inventory into a new logs run directory."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Local imports must not create caches outside the new logs run directory.
sys.dont_write_bytecode = True

from _b_route_inventory import GitCommandTimeout, collect_inventory, create_run_directory, markdown, require_runtime, validate_git_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path, help="Explicit repository root")
    parser.add_argument("--epics", required=True, help="Explicit repository-relative canonical epics file")
    parser.add_argument("--run-id", required=True, help="New run ID; existing directories are never reused")
    args = parser.parse_args(argv)
    try:
        require_runtime()
        if not args.root.is_dir():
            raise ValueError("Repository root does not exist")
        validate_git_root(args.root)
        output = create_run_directory(args.root, args.run_id)
    except (OSError, ValueError) as exc:
        print(f"INVENTORY OUTPUT ERROR: {exc}")
        return 2
    try:
        report = collect_inventory(args.root, args.epics)
        # Exclusive creation preserves any unexpected pre-existing evidence too.
        with (output / "inventory.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        with (output / "inventory.md").open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(markdown(report))
        print(f"INVENTORY {report['status']}: {output}")
        return 0 if report["adoptable"] else 1
    except (OSError, ValueError, UnicodeError) as exc:
        failure = {"status": "invalid", "adoptable": False, "error": str(exc),
                   "diagnostics": [{"code": "git-timeout" if isinstance(exc, GitCommandTimeout) else "inventory-failed",
                                    "severity": "error", "message": str(exc)}]}
        with (output / "failure.json").open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(failure, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        print(f"INVENTORY INPUT ERROR: {exc}; evidence: {output}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
