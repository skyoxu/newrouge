from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

from _knowledge_catalog_builder import GitSnapshot, build_layers


def _atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", delete=False, dir=path.parent, suffix=".tmp") as handle:
        handle.write(text)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build newrouge repository knowledge layers from a trusted git ref.")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--authority-ref", default="refs/heads/main")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    root = args.repository_root.resolve()
    policies = json.loads((root / "knowledge/policies/consumer-policies.v1.json").read_text(encoding="utf-8"))
    exclusions = json.loads((root / "knowledge/policies/source-exclusions.v1.json").read_text(encoding="utf-8"))
    snapshot, catalog, projections = build_layers(GitSnapshot(root, args.authority_ref), exclusions, policies)
    outputs = {
        root / "knowledge/snapshots/repository-source-snapshot.v1.json": snapshot,
        root / "knowledge/catalogs/repository-knowledge-catalog.v1.json": catalog,
        root / "knowledge/projections/consumer-projections.v1.json": projections,
    }
    if args.write:
        for path, value in outputs.items():
            _atomic_json(path, value)
    print(json.dumps({
        "status": "ok",
        "authority_ref": args.authority_ref,
        "commit": snapshot["commit"],
        "sources": len(snapshot["sources"]),
        "modules": len(catalog["modules"]),
        "written": args.write,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
