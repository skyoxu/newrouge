#!/usr/bin/env python3
"""Validate semantic-topology structure without creating task or semantic facts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from _knowledge_catalog_builder import LocalMainSnapshot
from _semantic_topology import load_topology_from_snapshot


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--require-available", action="store_true")
    args = parser.parse_args(argv)
    root = args.repo_root.resolve()
    view = load_topology_from_snapshot(LocalMainSnapshot(root), [])
    if not view.get("available"):
        status = "blocked" if args.require_available else "legacy_unmapped"
        print(json.dumps({
            "status": status,
            "reason": view.get("reason"),
            "identity": view.get("identity"),
        }, ensure_ascii=False))
        return 1 if args.require_available else 0
    blocking = list(view.get("problems", []))
    status = "passed" if view.get("fresh") and not blocking else "blocked"
    print(json.dumps({
        "status": status,
        "identity": view.get("identity"),
        "summary": view.get("summary"),
        "problems": view.get("problems", []),
    }, ensure_ascii=False))
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
