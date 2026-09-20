#!/usr/bin/env python3
"""Prepare and compile Chapter 3 semantic projection candidates.

The script does not bind an LLM provider. An approved Chapter 3 producer reads
the prepared batches and edits the candidate contract. Compilation is fully
deterministic and fail-closed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

ALLOWED_DISPOSITIONS = {
    "atomized", "context", "rationale", "duplicate", "superseded", "deferred",
    "out_of_scope", "adr_owned", "unresolved",
}
KIND_MAP = {
    "FR": "functional",
    "NFR": "non_functional",
    "INV": "invariant",
    "FAIL": "failure",
    "SCOPE": "scope",
    "METRIC": "metric",
    "CONSTRAINT": "constraint",
    "RISK": "risk",
    "CONTEXT": "context",
    "RATIONALE": "rationale",
    "functional": "functional",
    "non_functional": "non_functional",
    "invariant": "invariant",
    "failure": "failure",
    "scope": "scope",
    "metric": "metric",
    "constraint": "constraint",
    "risk": "risk",
    "context": "context",
    "rationale": "rationale",
}
DELIVERY_DEFAULT = {
    "functional": True,
    "non_functional": True,
    "invariant": True,
    "failure": True,
    "scope": True,
    "metric": True,
    "constraint": True,
    "risk": True,
    "context": False,
    "rationale": False,
}
PREFIX = {
    "functional": "FR",
    "non_functional": "NFR",
    "invariant": "INV",
    "failure": "FAIL",
    "scope": "SCOPE",
    "metric": "METRIC",
    "constraint": "CONSTRAINT",
    "risk": "RISK",
    "context": "CONTEXT",
    "rationale": "RATIONALE",
}


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def stable_requirement_id(kind: str, block_ids: list[str], statement: str) -> str:
    raw = kind + chr(0) + chr(0).join(sorted(block_ids)) + chr(0) + statement
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12].upper()
    return f"{PREFIX[kind]}-{digest}"


def _batch_cost(row: dict[str, Any]) -> int:
    # Use serialized character count as a deterministic context-budget proxy.
    return len(json.dumps(row, ensure_ascii=False, separators=(",", ":")))


def build_batches(
    ledger: dict[str, Any],
    max_blocks: int,
    max_chars: int = 24000,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    blocks = [row for row in ledger.get("blocks", []) if isinstance(row, dict)]
    if max_blocks < 1 or max_chars < 1:
        raise ValueError("batch limits must be positive")

    batches: list[dict[str, Any]] = []
    current: list[dict[str, Any]] = []
    current_chars = 0

    def flush() -> None:
        nonlocal current, current_chars
        if not current:
            return
        batch_id = f"BATCH-{len(batches) + 1:04d}"
        batches.append({
            "batch_id": batch_id,
            "first_block_id": current[0]["block_id"],
            "last_block_id": current[-1]["block_id"],
            "input_block_count": len(current),
            "input_char_count": current_chars,
            "max_blocks_per_batch": max_blocks,
            "max_chars_per_batch": max_chars,
            "block_ids": [row["block_id"] for row in current],
            "blocks": current,
            "producer_contract": {
                "ownership": "Only block_ids in this batch may be claimed as primary ownership.",
                "cross_block": "Atoms may reference more source_block_ids when semantics span blocks.",
                "no_silent_loss": "Every owned block requires atoms or one explicit disposition.",
                "context_budget": "The entire batch is bounded deterministically; no source text may be truncated.",
            },
        })
        current = []
        current_chars = 0

    for row in blocks:
        cost = _batch_cost(row)
        if cost > max_chars:
            raise ValueError(
                f"source block {row.get('block_id')} exceeds max_chars_per_batch "
                f"({cost}>{max_chars}); do not truncate it silently"
            )
        if current and (len(current) >= max_blocks or current_chars + cost > max_chars):
            flush()
        current.append(row)
        current_chars += cost
    flush()

    index = {
        "schema_version": "chapter3.semantic-projection-batches.v1",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_revision": ledger.get("source_revision"),
        "source_block_count": len(blocks),
        "batch_count": len(batches),
        "max_blocks_per_batch": max_blocks,
        "max_chars_per_batch": max_chars,
        "batches": [{key: value for key, value in batch.items() if key != "blocks"} for batch in batches],
    }
    return index, batches


def prepare(
    ledger: dict[str, Any],
    max_blocks: int,
    batch_dir: Path,
    max_chars: int = 24000,
) -> tuple[dict[str, Any], dict[str, Any]]:
    index, batches = build_batches(ledger, max_blocks, max_chars)
    batch_dir.mkdir(parents=True, exist_ok=True)
    block_to_batch = {}
    for batch in batches:
        for block_id in batch["block_ids"]:
            block_to_batch[block_id] = batch["batch_id"]
        write_json(batch_dir / f"{batch['batch_id'].lower()}.json", batch)
    results = []
    for block in ledger.get("blocks", []):
        block_id = str(block.get("block_id"))
        results.append({
            "batch_id": block_to_batch.get(block_id),
            "block_id": block_id,
            "atoms": [],
            "disposition": "",
            "delivery_potential": None,
            "decision": None,
        })
    candidate = {
        "schema_version": "chapter3.semantic-projection-candidate.v1",
        "generated_at_utc": index["generated_at_utc"],
        "source_revision": ledger.get("source_revision"),
        "instructions": {
            "producer": "Review every block. Fill atoms or one explicit disposition; never leave the template blank.",
            "allowed_dispositions": sorted(ALLOWED_DISPOSITIONS),
            "allowed_kinds": sorted(set(KIND_MAP)),
            "delivery_potential": "Set a boolean for every block. Keyword hints are hints only and never decide this field.",
            "uncertainty": "Use unresolved explicitly. Delivery-potential unresolved blocks block stable closure.",
            "batch_accounting": "After reviewing a batch, set output_accounted_count to the number of owned blocks explicitly reviewed.",
        },
        "batch_summaries": [{
            "batch_id": row["batch_id"],
            "first_block_id": row["first_block_id"],
            "last_block_id": row["last_block_id"],
            "input_block_count": row["input_block_count"],
            "input_char_count": row["input_char_count"],
            "output_accounted_count": 0,
        } for row in index["batches"]],
        "block_results": results,
        "capabilities": [],
    }
    return index, candidate


def normalize_kind(value: Any) -> str:
    key = str(value or "").strip()
    if key in KIND_MAP:
        return KIND_MAP[key]
    upper = key.upper()
    if upper in KIND_MAP:
        return KIND_MAP[upper]
    raise ValueError(f"unsupported semantic kind: {value}")


def compile_projection(
    ledger: dict[str, Any],
    batches: dict[str, Any],
    candidate: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    source_revision = str(ledger.get("source_revision") or "")
    if str(batches.get("source_revision") or "") != source_revision:
        raise ValueError("semantic batch source_revision does not match source ledger")
    if str(candidate.get("source_revision") or "") != source_revision:
        raise ValueError("semantic candidate source_revision does not match source ledger")

    blocks = {
        str(row.get("block_id")): row
        for row in ledger.get("blocks", [])
        if isinstance(row, dict) and row.get("block_id")
    }
    assigned = {
        str(block_id): str(batch.get("batch_id"))
        for batch in batches.get("batches", [])
        for block_id in batch.get("block_ids", [])
    }
    expected_batches = {
        str(batch.get("batch_id")): batch
        for batch in batches.get("batches", [])
        if isinstance(batch, dict) and batch.get("batch_id")
    }
    summaries = candidate.get("batch_summaries", [])
    if not isinstance(summaries, list):
        raise ValueError("batch_summaries must be a list")
    summary_by_id = {
        str(row.get("batch_id")): row
        for row in summaries if isinstance(row, dict) and row.get("batch_id")
    }
    if set(summary_by_id) != set(expected_batches):
        raise ValueError("candidate batch summaries do not match prepared batches")
    for batch_id, expected in expected_batches.items():
        summary = summary_by_id[batch_id]
        for field in ("first_block_id", "last_block_id", "input_block_count"):
            if summary.get(field) != expected.get(field):
                raise ValueError(f"batch summary mismatch for {batch_id}: {field}")
        if int(summary.get("output_accounted_count") or 0) != int(expected.get("input_block_count") or 0):
            raise ValueError(f"batch {batch_id} output_accounted_count does not reconcile")

    results = candidate.get("block_results", [])
    if not isinstance(results, list):
        raise ValueError("block_results must be a list")
    seen_blocks = set()
    requirements = []
    accounting = []
    by_requirement = {}
    for result in results:
        if not isinstance(result, dict):
            raise ValueError("each block result must be an object")
        block_id = str(result.get("block_id") or "")
        if block_id not in blocks:
            raise ValueError(f"unknown block_id in candidate: {block_id}")
        if block_id in seen_blocks:
            raise ValueError(f"duplicate primary block result: {block_id}")
        seen_blocks.add(block_id)
        batch_id = str(result.get("batch_id") or "")
        if assigned.get(block_id) != batch_id:
            raise ValueError(f"batch ownership mismatch for {block_id}")
        atoms = result.get("atoms", [])
        if not isinstance(atoms, list):
            raise ValueError(f"atoms must be a list for {block_id}")
        disposition = str(result.get("disposition") or "").strip()
        if not isinstance(result.get("delivery_potential"), bool):
            raise ValueError(f"block {block_id} must explicitly set delivery_potential")
        if not atoms and disposition not in ALLOWED_DISPOSITIONS:
            raise ValueError(f"block {block_id} has neither atoms nor valid disposition")
        if atoms and disposition and disposition not in ALLOWED_DISPOSITIONS:
            raise ValueError(f"block {block_id} has invalid disposition {disposition}")
        requirement_ids = []
        for atom in atoms:
            if not isinstance(atom, dict):
                raise ValueError(f"atom for {block_id} must be an object")
            kind = normalize_kind(atom.get("kind"))
            statement = str(atom.get("statement") or "").strip()
            if not statement:
                raise ValueError(f"atom for {block_id} has empty statement")
            source_block_ids = [str(value) for value in atom.get("source_block_ids", [block_id])]
            if not source_block_ids or any(value not in blocks for value in source_block_ids):
                raise ValueError(f"atom for {block_id} has invalid source_block_ids")
            requirement_id = str(atom.get("requirement_id") or "").strip()
            if not requirement_id:
                requirement_id = stable_requirement_id(kind, source_block_ids, statement)
            if requirement_id in by_requirement:
                raise ValueError(f"duplicate requirement_id: {requirement_id}")
            delivery_relevant = atom.get("delivery_relevant")
            if not isinstance(delivery_relevant, bool):
                delivery_relevant = DELIVERY_DEFAULT[kind]
            sinks = atom.get("non_task_sinks", [])
            if not isinstance(sinks, list):
                raise ValueError(f"non_task_sinks must be a list for {requirement_id}")
            row = {
                "requirement_id": requirement_id,
                "kind": kind,
                "statement": statement,
                "source_block_ids": sorted(set(source_block_ids)),
                "delivery_relevant": delivery_relevant,
                "capability_ids": sorted(set(str(value) for value in atom.get("capability_ids", []))),
                "sink_policy": str(atom.get("sink_policy") or "task_or_global_constraint"),
                "status": str(atom.get("status") or "active"),
                "priority": str(atom.get("priority") or "P2").upper(),
                "owner_hint": atom.get("owner_hint"),
                "layer_hint": atom.get("layer_hint"),
                "non_task_sinks": sinks,
            }
            if atom.get("rationale"):
                row["rationale"] = str(atom["rationale"])
            requirements.append(row)
            by_requirement[requirement_id] = row
            requirement_ids.append(requirement_id)
        accounting.append({
            "block_id": block_id,
            "batch_id": batch_id,
            "requirement_ids": requirement_ids,
            "disposition": disposition or ("atomized" if atoms else ""),
            "delivery_potential": bool(result.get("delivery_potential")),
            "decision": result.get("decision"),
        })
    missing = sorted(set(blocks) - seen_blocks)
    if missing:
        raise ValueError("candidate omitted source blocks: " + ", ".join(missing[:20]))

    capabilities_raw = candidate.get("capabilities", [])
    if not isinstance(capabilities_raw, list):
        raise ValueError("capabilities must be a list")
    capabilities = []
    capability_ids = set()
    for raw in capabilities_raw:
        if not isinstance(raw, dict):
            raise ValueError("capability must be an object")
        capability_id = str(raw.get("capability_id") or "").strip()
        title = str(raw.get("title") or "").strip()
        requirement_ids = sorted(set(str(value) for value in raw.get("requirement_ids", [])))
        if not capability_id or not title or not requirement_ids:
            raise ValueError("capability requires capability_id, title, and requirement_ids")
        if capability_id in capability_ids:
            raise ValueError(f"duplicate capability_id: {capability_id}")
        if any(rid not in by_requirement for rid in requirement_ids):
            raise ValueError(f"capability {capability_id} references unknown requirements")
        capability_ids.add(capability_id)
        capabilities.append({
            "capability_id": capability_id,
            "title": title,
            "description": str(raw.get("description") or ""),
            "requirement_ids": requirement_ids,
        })
        for rid in requirement_ids:
            values = set(by_requirement[rid].get("capability_ids", []))
            values.add(capability_id)
            by_requirement[rid]["capability_ids"] = sorted(values)

    edges = []
    edge_keys = set()

    def add_edge(source_type: str, source_id: str, target_type: str, target_id: str, relation: str, **extra: Any) -> None:
        key = (source_type, source_id, target_type, target_id, relation)
        if key in edge_keys:
            return
        edge_keys.add(key)
        edges.append({
            "source_type": source_type,
            "source_id": source_id,
            "target_type": target_type,
            "target_id": target_id,
            "relation": relation,
            **extra,
        })

    for capability in capabilities:
        for rid in capability["requirement_ids"]:
            add_edge("requirement", rid, "capability", capability["capability_id"], "grouped_by")
    for requirement in requirements:
        rid = requirement["requirement_id"]
        for sink in requirement.get("non_task_sinks", []):
            if not isinstance(sink, dict):
                raise ValueError(f"non-task sink for {rid} must be an object")
            sink_type = str(sink.get("type") or "").strip()
            sink_id = str(sink.get("id") or "").strip()
            if sink_type not in {"global_constraint", "quality_gate", "adr", "deferred", "exclusion"} or not sink_id:
                raise ValueError(f"invalid non-task sink for {rid}")
            add_edge("requirement", rid, sink_type, sink_id, str(sink.get("relation") or "governed_by"))

    generated = dt.datetime.now(dt.timezone.utc).isoformat()
    semantic_doc = {
        "schema_version": "newrouge.semantic-requirements.v1",
        "generated_at_utc": generated,
        "source_revision": ledger.get("source_revision"),
        "source_manifest_sha256": ledger.get("source_manifest_sha256"),
        "source_accounting": accounting,
        "requirements": requirements,
    }
    capability_doc = {
        "schema_version": "newrouge.capabilities.v1",
        "generated_at_utc": generated,
        "source_revision": ledger.get("source_revision"),
        "capabilities": capabilities,
    }
    edge_doc = {
        "schema_version": "newrouge.topology-edges.v1",
        "generated_at_utc": generated,
        "source_revision": ledger.get("source_revision"),
        "edges": edges,
    }
    return semantic_doc, capability_doc, edge_doc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)

    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--repo-root", default=".")
    prepare_parser.add_argument("--ledger", default="logs/ci/task-generation/source-blocks.v1.json")
    prepare_parser.add_argument("--max-blocks-per-batch", type=int, default=40)
    prepare_parser.add_argument("--max-chars-per-batch", type=int, default=24000)
    prepare_parser.add_argument("--batch-dir", default="logs/ci/task-generation/semantic-batches")
    prepare_parser.add_argument("--batches-out", default="logs/ci/task-generation/semantic-projection.batches.v1.json")
    prepare_parser.add_argument("--candidate-out", default="logs/ci/task-generation/semantic-projection.candidate.json")

    compile_parser = sub.add_parser("compile")
    compile_parser.add_argument("--repo-root", default=".")
    compile_parser.add_argument("--ledger", default="logs/ci/task-generation/source-blocks.v1.json")
    compile_parser.add_argument("--batches", default="logs/ci/task-generation/semantic-projection.batches.v1.json")
    compile_parser.add_argument("--candidate", default="logs/ci/task-generation/semantic-projection.candidate.json")
    compile_parser.add_argument("--requirements-out", default="logs/ci/task-generation/semantic-requirements.v1.json")
    compile_parser.add_argument("--capabilities-out", default="logs/ci/task-generation/capabilities.v1.json")
    compile_parser.add_argument("--edges-out", default="logs/ci/task-generation/topology-edges.base.v1.json")

    args = parser.parse_args(argv)
    root = Path(args.repo_root).resolve()
    if args.action == "prepare":
        ledger = load_json(root / args.ledger)
        try:
            index, candidate = prepare(
                ledger,
                max(1, args.max_blocks_per_batch),
                root / args.batch_dir,
                max(1, args.max_chars_per_batch),
            )
        except ValueError as exc:
            print(f"semantic_projection_prepare_error={exc}")
            return 2
        write_json(root / args.batches_out, index)
        write_json(root / args.candidate_out, candidate)
        print(
            f"semantic_batches={root / args.batches_out} batches={index['batch_count']} "
            f"blocks={index['source_block_count']} candidate={root / args.candidate_out}"
        )
        return 0
    try:
        semantics, capabilities, edges = compile_projection(
            load_json(root / args.ledger),
            load_json(root / args.batches),
            load_json(root / args.candidate),
        )
    except ValueError as exc:
        print(f"semantic_projection_error={exc}")
        return 2
    write_json(root / args.requirements_out, semantics)
    write_json(root / args.capabilities_out, capabilities)
    write_json(root / args.edges_out, edges)
    print(
        f"semantic_requirements={root / args.requirements_out} requirements={len(semantics['requirements'])} "
        f"capabilities={len(capabilities['capabilities'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
