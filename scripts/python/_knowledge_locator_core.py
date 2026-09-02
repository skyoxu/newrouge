"""Deterministic, location-only retrieval for newrouge repository knowledge."""
from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

POLICY_EXACT_PATH_BONUS = 128


def tokens(query: str) -> list[str]:
    parts = re.findall(r"[a-z0-9]+(?:[._:-][a-z0-9]+)*|[\u3400-\u9fff]+", query.casefold())
    result: list[str] = []
    for part in parts:
        values = [part]
        if re.fullmatch(r"[\u3400-\u9fff]+", part) and len(part) > 2:
            values += [part[i:i + 2] for i in range(len(part) - 1)]
        for value in values:
            if value and value not in result:
                result.append(value)
    return result


def _explicit(query: str, module: dict[str, Any]) -> bool:
    folded = query.casefold().strip()
    path = str(module.get("source_path", "")).casefold()
    values = {path, PurePosixPath(path).name.casefold(), str(module.get("module_id", "")).casefold(), str(module.get("title", "")).casefold()}
    return folded in values or any(len(folded) >= 6 and folded in value for value in values if value)


def _policy_allows(module: dict[str, Any], query: str, policy: dict[str, Any]) -> bool:
    if not module.get("semantic_eligible", True):
        return False
    if module.get("status") not in policy.get("statuses", ["active"]):
        return False
    if module.get("lifecycle") not in policy.get("lifecycles", ["repository-source"]):
        return False
    path = str(module.get("source_path", ""))
    if path not in policy.get("exact_paths", []) and not any(path.startswith(prefix) for prefix in policy.get("path_prefixes", [])):
        return False
    if policy.get("historical_mode") == "exact-only" and module.get("status") == "historical" and not _explicit(query, module):
        return False
    if policy.get("historical_mode") == "forbidden" and module.get("status") == "historical":
        return False
    visibility = module.get("visibility", {})
    allowed = set(policy.get("visibility", []))
    return any(visibility.get(domain) in allowed for domain in policy.get("domains", []))


def _best_location(module: dict[str, Any], query_tokens: list[str]) -> tuple[str, int, int]:
    content = str(module.get("content", ""))
    lines = content.splitlines()
    best_line, best_score = 1, -1
    for index, line in enumerate(lines, 1):
        folded = line.casefold()
        score = sum(token in folded for token in query_tokens)
        if score > best_score:
            best_line, best_score = index, score
    for anchor in module.get("anchors", []):
        if isinstance(anchor, dict) and anchor.get("line_start", 0) <= best_line <= anchor.get("line_end", 0):
            return str(anchor.get("anchor", "document")), best_line, best_line
    return str(module.get("anchor", "document")), best_line, best_line


def locate(request: dict[str, Any], catalog: dict[str, Any], policy: dict[str, Any], eligible_ids: set[str], max_candidates: int) -> dict[str, Any]:
    query = request.get("query")
    if not isinstance(query, str) or not query.strip() or max_candidates < 1:
        return {"status": "insufficient_match", "candidates": []}
    qtokens = tokens(query)
    ranked: dict[str, tuple[int, str, dict[str, Any]]] = {}
    by_id = {module.get("module_id"): module for module in catalog.get("modules", []) if isinstance(module, dict)}
    base: list[tuple[int, dict[str, Any]]] = []
    exact_policy_paths = set(policy.get("exact_paths", []))
    for module in by_id.values():
        module_id = module.get("module_id")
        if module_id not in eligible_ids or not _policy_allows(module, query, policy):
            continue
        source_path = str(module.get("source_path", ""))
        title = str(module.get("title", ""))
        searchable = " ".join((source_path, str(module_id), title, str(module.get("content", "")))).casefold()
        matches = sum(token in searchable for token in qtokens)
        coverage = matches / max(1, len(qtokens))
        phrase = query.casefold().strip() in searchable
        exact = _explicit(query, module)
        if not exact and not phrase and coverage < 0.5:
            continue
        path_folded = source_path.casefold()
        title_folded = title.casefold()
        path_token_matches = sum(token in path_folded for token in qtokens)
        title_token_matches = sum(token in title_folded for token in qtokens)
        score = matches * 10
        score += path_token_matches * 8
        score += title_token_matches * 8
        if phrase:
            score += 25
        if exact:
            score += 100
        policy_exact_path = source_path in exact_policy_paths
        entrypoint_token_matches = path_token_matches + title_token_matches
        policy_entrypoint_boosted = policy_exact_path and entrypoint_token_matches > 0
        if policy_entrypoint_boosted:
            score += POLICY_EXACT_PATH_BONUS
        anchor, line_start, line_end = _best_location(module, qtokens)
        ranked[str(module_id)] = (score, source_path.casefold(), {
            "module_id": module_id,
            "path": source_path,
            "anchor": anchor,
            "line_start": line_start,
            "line_end": line_end,
            "source_sha256": module["source_sha256"],
            "primary_domain": module["primary_domain"],
            "status": module["status"],
            "provenance": ["catalog-v1", catalog["source_snapshot"]["ref"]],
            "rank_evidence": {
                "strategy": "hybrid-token",
                "score": score,
                "token_matches": matches,
                "confidence": "high" if exact or (phrase and coverage == 1) else "medium",
                "policy_exact_path": policy_exact_path,
                "entrypoint_token_matches": entrypoint_token_matches,
                "policy_exact_path_bonus": POLICY_EXACT_PATH_BONUS if policy_entrypoint_boosted else 0,
            },
        })
        base.append((score, module))
    for score, module in base:
        for relation in module.get("relations", []):
            related = by_id.get(relation.get("target")) if isinstance(relation, dict) else None
            if not related or related.get("module_id") in ranked or related.get("module_id") not in eligible_ids:
                continue
            if not _policy_allows(related, query, policy):
                continue
            anchor, line_start, line_end = _best_location(related, qtokens)
            relation_score = max(1, min(9, score // 20))
            ranked[related["module_id"]] = (relation_score, related["source_path"].casefold(), {
                "module_id": related["module_id"], "path": related["source_path"], "anchor": anchor,
                "line_start": line_start, "line_end": line_end, "source_sha256": related["source_sha256"],
                "primary_domain": related["primary_domain"], "status": related["status"],
                "provenance": ["catalog-v1", catalog["source_snapshot"]["ref"]],
                "rank_evidence": {"strategy": "relation-expansion", "score": relation_score, "token_matches": 0, "confidence": "medium"},
            })
    ordered = sorted(ranked.values(), key=lambda item: (-item[0], item[1]))
    return {"status": "matched" if ordered else "insufficient_match", "candidates": [item[2] for item in ordered[:max_candidates]]}
