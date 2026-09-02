from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


CONSUMERS = ("repository-session", "chapter4", "chapter5", "chapter6", "review")
POLICY_REVISION = "newrouge-knowledge-consumer-policies.v1"


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="\n",
        delete=False,
        dir=path.parent,
        suffix=".tmp",
    ) as handle:
        handle.write(text)
        temporary = Path(handle.name)
    os.replace(temporary, path)


def _fallback(
    *,
    consumer: str,
    query: str,
    request_id: str,
    reason: str,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": "newrouge.knowledge-context-candidates.v1",
        "mode": "shadow",
        "consumer": consumer,
        "request_id": request_id,
        "query": query,
        "status": "fallback_required",
        "locator_status": "unavailable",
        "snapshot": snapshot,
        "policy_revision": POLICY_REVISION,
        "semantic_decision_required": True,
        "freeze_state": "unfrozen",
        "candidates": [],
        "fallback": {
            "required": True,
            "reason": reason,
            "authority_route": "docs/agents/13-rag-sources-and-session-ssot.md",
        },
    }


def _request_id(consumer: str, query: str, commit: str | None) -> str:
    seed = f"{consumer}\0{query}\0{commit or 'missing'}".encode("utf-8")
    return "shadow-" + hashlib.sha256(seed).hexdigest()[:16]


def _run_locator(root: Path, request: dict[str, Any]) -> tuple[int, dict[str, Any] | None, str]:
    completed = subprocess.run(
        [sys.executable, str(root / "scripts/python/knowledge_locator.py"), "--repository-root", str(root)],
        input=json.dumps(request, ensure_ascii=False),
        text=True,
        encoding="utf-8",
        capture_output=True,
        check=False,
        cwd=root,
    )
    if completed.returncode != 0:
        return completed.returncode, None, completed.stderr.strip() or "knowledge_locator_failed"
    try:
        return 0, json.loads(completed.stdout), ""
    except json.JSONDecodeError:
        return 1, None, "knowledge_locator_invalid_json"


def prepare(root: Path, *, consumer: str, query: str, request_id: str | None = None) -> dict[str, Any]:
    snapshot_path = root / "knowledge/snapshots/repository-source-snapshot.v1.json"
    required_generated = [
        snapshot_path,
        root / "knowledge/catalogs/repository-knowledge-catalog.v1.json",
        root / "knowledge/projections/consumer-projections.v1.json",
        root / "knowledge/policies/consumer-policies.v1.json",
    ]
    if not all(path.is_file() for path in required_generated):
        rid = request_id or _request_id(consumer, query, None)
        return _fallback(
            consumer=consumer,
            query=query,
            request_id=rid,
            reason="generated_knowledge_missing",
        )

    try:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        rid = request_id or _request_id(consumer, query, None)
        return _fallback(
            consumer=consumer,
            query=query,
            request_id=rid,
            reason="source_snapshot_invalid",
        )

    commit = snapshot.get("commit")
    ref = snapshot.get("ref")
    rid = request_id or _request_id(consumer, query, commit if isinstance(commit, str) else None)
    if not isinstance(commit, str) or not isinstance(ref, str):
        return _fallback(
            consumer=consumer,
            query=query,
            request_id=rid,
            reason="source_snapshot_invalid",
            snapshot=snapshot if isinstance(snapshot, dict) else None,
        )

    request = {
        "schema_version": "newrouge.knowledge-locator-request.v1",
        "request_id": rid,
        "consumer": consumer,
        "query": query,
        "snapshot": {"ref": ref, "commit": commit},
        "policy_revision": POLICY_REVISION,
    }
    returncode, result, error = _run_locator(root, request)
    if returncode or result is None:
        return _fallback(
            consumer=consumer,
            query=query,
            request_id=rid,
            reason=error or "knowledge_locator_failed",
            snapshot=request["snapshot"],
        )
    if result.get("status") == "blocked":
        return _fallback(
            consumer=consumer,
            query=query,
            request_id=rid,
            reason="knowledge_locator_blocked",
            snapshot=request["snapshot"],
        )

    locator_status = str(result.get("status") or "insufficient_match")
    candidates = result.get("candidates")
    if not isinstance(candidates, list):
        return _fallback(
            consumer=consumer,
            query=query,
            request_id=rid,
            reason="knowledge_locator_result_invalid",
            snapshot=request["snapshot"],
        )

    return {
        "schema_version": "newrouge.knowledge-context-candidates.v1",
        "mode": "shadow",
        "consumer": consumer,
        "request_id": rid,
        "query": query,
        "status": "shadow_ready",
        "locator_status": locator_status,
        "snapshot": request["snapshot"],
        "policy_revision": POLICY_REVISION,
        "semantic_decision_required": True,
        "freeze_state": "unfrozen",
        "candidates": candidates,
        "fallback": {
            "required": False,
            "reason": None,
            "authority_route": "docs/agents/13-rag-sources-and-session-ssot.md",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a non-authoritative shadow knowledge candidate bundle for a newrouge workflow consumer."
    )
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--consumer", choices=CONSUMERS, required=True)
    parser.add_argument("--query", required=True)
    parser.add_argument("--request-id")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="Return non-zero when generated knowledge is unavailable or blocked. Default shadow mode is non-blocking.",
    )
    args = parser.parse_args()
    root = args.repository_root.resolve()
    bundle = prepare(
        root,
        consumer=args.consumer,
        query=args.query,
        request_id=args.request_id,
    )
    if args.output:
        output = args.output if args.output.is_absolute() else root / args.output
        _atomic_json(output, bundle)
    print(json.dumps(bundle, ensure_ascii=False, indent=2, sort_keys=True))
    return 2 if args.enforce and bundle["status"] == "fallback_required" else 0


if __name__ == "__main__":
    raise SystemExit(main())
