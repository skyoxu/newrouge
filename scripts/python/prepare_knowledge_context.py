from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


CONSUMERS = ("repository-session", "chapter4", "chapter5", "chapter6", "review")
POLICY_REVISION = "newrouge-knowledge-consumer-policies.v1"
STRUCTURED_SCOPE = re.compile(r"\b[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+\b")
TASK_SCOPE = re.compile(r"\btask\s+(?:id\s*)?\d+\b", re.IGNORECASE)


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


def _consumer_policy(root: Path, consumer: str) -> dict[str, Any] | None:
    try:
        registry = json.loads(
            (root / "knowledge/policies/consumer-policies.v1.json").read_text(encoding="utf-8")
        )
    except (OSError, json.JSONDecodeError):
        return None
    if registry.get("policy_revision") != POLICY_REVISION:
        return None
    return next(
        (
            item
            for item in registry.get("policies", [])
            if isinstance(item, dict) and item.get("consumer") == consumer
        ),
        None,
    )


def _scope_terms(query: str) -> list[str]:
    values: list[str] = []
    for pattern in (STRUCTURED_SCOPE, TASK_SCOPE):
        for match in pattern.finditer(query):
            value = match.group(0).strip()
            folded = value.casefold()
            if value and all(existing.casefold() != folded for existing in values):
                values.append(value)
    return values


def _append_query_plan(
    plan: list[tuple[str | None, str, int | None]],
    seen_queries: set[str],
    *,
    context_class: str,
    query: str,
    limit: int,
) -> None:
    normalized = query.strip()
    folded = normalized.casefold()
    if not normalized or folded in seen_queries:
        return
    seen_queries.add(folded)
    plan.append((context_class, normalized, limit))


def _context_query_plan(policy: dict[str, Any], query: str) -> list[tuple[str | None, str, int | None]]:
    plan: list[tuple[str | None, str, int | None]] = [(None, query, None)]
    term_mapping = policy.get("context_query_terms")
    exact_path_mapping = policy.get("context_query_exact_path_templates")
    if not isinstance(term_mapping, dict) and not isinstance(exact_path_mapping, dict):
        return plan
    try:
        per_class_limit = max(1, int(policy.get("context_query_max_candidates", 4)))
    except (TypeError, ValueError):
        per_class_limit = 4
    scope = _scope_terms(query)
    structured_scope = next((value for value in scope if STRUCTURED_SCOPE.fullmatch(value)), None)
    seen_queries = {query.casefold().strip()}
    for context_class in policy.get("required_context_classes", []):
        if not isinstance(context_class, str):
            continue

        templates = exact_path_mapping.get(context_class) if isinstance(exact_path_mapping, dict) else None
        if structured_scope and isinstance(templates, list):
            for template in templates:
                if not isinstance(template, str) or not template.strip() or "{scope}" not in template:
                    continue
                _append_query_plan(
                    plan,
                    seen_queries,
                    context_class=context_class,
                    query=template.replace("{scope}", structured_scope),
                    limit=per_class_limit,
                )

        terms = term_mapping.get(context_class) if isinstance(term_mapping, dict) else None
        if not isinstance(terms, list):
            continue
        normalized_terms = [str(value).strip() for value in terms if isinstance(value, str) and value.strip()]
        if not normalized_terms:
            continue
        _append_query_plan(
            plan,
            seen_queries,
            context_class=context_class,
            query=" ".join([*scope, *normalized_terms]),
            limit=per_class_limit,
        )
    return plan


def _merge_candidates(
    merged: dict[tuple[str, str], dict[str, Any]],
    order: list[tuple[str, str]],
    candidates: list[Any],
    *,
    context_class: str | None,
    limit: int | None,
) -> None:
    bounded = candidates if limit is None else candidates[:limit]
    for raw in bounded:
        if not isinstance(raw, dict):
            continue
        module_id = raw.get("module_id")
        path = raw.get("path")
        if not isinstance(module_id, str) or not isinstance(path, str):
            continue
        key = (module_id, path)
        if key not in merged:
            candidate = dict(raw)
            candidate["retrieval_context_classes"] = []
            merged[key] = candidate
            order.append(key)
        if context_class is not None:
            classes = merged[key].setdefault("retrieval_context_classes", [])
            if context_class not in classes:
                classes.append(context_class)
                classes.sort()


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

    policy = _consumer_policy(root, consumer)
    if policy is None:
        return _fallback(
            consumer=consumer,
            query=query,
            request_id=rid,
            reason="consumer_policy_invalid",
            snapshot={"ref": ref, "commit": commit},
        )

    merged: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    statuses: list[str] = []
    for plan_index, (context_class, locator_query, limit) in enumerate(_context_query_plan(policy, query)):
        suffix = context_class or "base"
        request = {
            "schema_version": "newrouge.knowledge-locator-request.v1",
            "request_id": f"{rid}:{suffix}:{plan_index}",
            "consumer": consumer,
            "query": locator_query,
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
        statuses.append(locator_status)
        candidates = result.get("candidates")
        if not isinstance(candidates, list):
            return _fallback(
                consumer=consumer,
                query=query,
                request_id=rid,
                reason="knowledge_locator_result_invalid",
                snapshot=request["snapshot"],
            )
        _merge_candidates(
            merged,
            order,
            candidates,
            context_class=context_class,
            limit=limit,
        )

    locator_status = "matched" if "matched" in statuses else "insufficient_match"
    candidates = [merged[key] for key in order]
    return {
        "schema_version": "newrouge.knowledge-context-candidates.v1",
        "mode": "shadow",
        "consumer": consumer,
        "request_id": rid,
        "query": query,
        "status": "shadow_ready",
        "locator_status": locator_status,
        "snapshot": {"ref": ref, "commit": commit},
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
