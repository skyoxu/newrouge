from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from _knowledge_locator_core import locate


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _git_blob_hash(root: Path, commit: str, path: str) -> str | None:
    completed = subprocess.run(["git", "-C", str(root), "show", f"{commit}:{path}"], capture_output=True, check=False)
    return hashlib.sha256(completed.stdout).hexdigest() if completed.returncode == 0 else None


def _fresh(root: Path, catalog: dict[str, Any]) -> bool:
    snapshot = catalog.get("source_snapshot", {})
    ref = snapshot.get("ref")
    commit = snapshot.get("commit")
    if not isinstance(ref, str) or not isinstance(commit, str):
        return False
    current = subprocess.run(["git", "-C", str(root), "rev-parse", ref], capture_output=True, text=True, encoding="utf-8", check=False)
    if current.returncode or current.stdout.strip() != commit:
        return False
    for source in snapshot.get("sources", []):
        if not isinstance(source, dict):
            return False
        if _git_blob_hash(root, commit, str(source.get("path", ""))) != source.get("sha256"):
            return False
    return True


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Locate authoritative newrouge repository knowledge without synthesizing answers.")
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--catalog", type=Path, default=Path("knowledge/catalogs/repository-knowledge-catalog.v1.json"))
    parser.add_argument("--policies", type=Path, default=Path("knowledge/policies/consumer-policies.v1.json"))
    parser.add_argument("--projections", type=Path, default=Path("knowledge/projections/consumer-projections.v1.json"))
    parser.add_argument("--max-candidates", type=int, default=12)
    args = parser.parse_args()
    root = args.repository_root.resolve()
    rooted = lambda path: path if path.is_absolute() else root / path
    request = json.load(sys.stdin)
    catalog = json.loads(rooted(args.catalog).read_text(encoding="utf-8"))
    policies = json.loads(rooted(args.policies).read_text(encoding="utf-8"))
    projections = json.loads(rooted(args.projections).read_text(encoding="utf-8"))
    snapshot = catalog.get("source_snapshot", {})
    policy = next((item for item in policies.get("policies", []) if item.get("consumer") == request.get("consumer")), None)
    projection = next((item for item in projections.get("projections", []) if item.get("consumer") == request.get("consumer")), None)
    bindings_ok = (
        projections.get("source_snapshot_id") == snapshot.get("snapshot_id")
        and projections.get("catalog_sha256") == _canonical_hash(catalog)
        and projections.get("policy_revision") == policies.get("policy_revision") == request.get("policy_revision")
        and projections.get("policy_sha256") == _canonical_hash(policies)
        and request.get("snapshot") == {"ref": snapshot.get("ref"), "commit": snapshot.get("commit")}
    )
    if policy is None or projection is None or not bindings_ok or not _fresh(root, catalog):
        status, candidates = "blocked", []
    else:
        maximum = min(args.max_candidates, int(policy.get("max_candidates", args.max_candidates)))
        core = locate(request, catalog, policy, set(projection.get("eligible_module_ids", [])), maximum)
        status, candidates = core["status"], core["candidates"]
    print(json.dumps({
        "schema_version": "newrouge.knowledge-locator-result.v1",
        "request_id": request.get("request_id"),
        "status": status,
        "snapshot": request.get("snapshot"),
        "policy_revision": request.get("policy_revision"),
        "candidates": candidates,
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
