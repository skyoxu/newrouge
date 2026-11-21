"""Deterministic <=70k UTF-8 byte 3B segmented runtime driver across Stages 1-6a.

Implements bounded rolling batch generation (Stage 1/2), tree-reduce and final
candidate synthesis (Stage 3), bounded single-delta repair without draft_chain
snowballing (Stage 4), deterministic segmented indexed independent admission
review with host full-denominator aggregation (Stage 5), and compact/segmented
anonymous candidate selection (Stage 6a).
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
import json
from pathlib import Path
from typing import Any

import _b_route_3b_segmented_input as seg_input
import _b_route_candidate as candidate
import _b_route_codec as codec
import _b_route_compact_literal as compact
import _b_route_planning_input as planning
import _b_route_planning_wire as wire
import _b_route_sources as sources
from _planning_skill_common import atomic_json, canonical_sha, file_sha, load_json

_ACTIVE_SHOULD_PAUSE: ContextVar[Any] = ContextVar("_ACTIVE_SHOULD_PAUSE", default=None)


@contextmanager
def slice_pause_guard(should_pause: Any):
    """Bind an inter-dispatch pause predicate across worker/inline call stacks."""
    token = _ACTIVE_SHOULD_PAUSE.set(should_pause)
    try:
        yield
    finally:
        _ACTIVE_SHOULD_PAUSE.reset(token)

SEGMENTED_RUNTIME_POLICY = "newrouge.b-route-3b-segmented-runtime.v1"
SEGMENTED_SELECTOR_POLICY = "newrouge.b-route-3b-segmented-selector.v1"
MAX_WORKSPACE_PAYLOAD_BYTES = seg_input.MAX_WORKSPACE_PAYLOAD_BYTES
CONTEXT_TOKEN_LIMIT = seg_input.CONTEXT_TOKEN_LIMIT
MAX_ROLLING_DRAFT_BYTES = 6_500
MAX_INTERMEDIATE_DRAFT_BYTES = 18_000
MAX_STAGE3_SHARD_BYTES = 24_000


def is_segmented_state(state: dict | None) -> bool:
    return isinstance(state, dict) and state.get("b_route_segmented_runtime_policy") == SEGMENTED_RUNTIME_POLICY


def segmented_call_root(workspace: Path, number: int) -> Path:
    """Short deterministic call directory keeping Windows paths well below 259 chars."""
    return workspace / "seg" / f"{number:03d}"


def _compact_bytes_len(value) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8"))


def _authoritative_core_summary(frozen: dict) -> dict:
    """Compact lossless authoritative core (without 359 KB 3A intermediate logs)."""
    inputs = frozen["inputs"]
    gp = inputs["global_proof"]
    return {
        "input_identity": frozen["input_identity"],
        "contract_ref": inputs["contract_ref"],
        "contract": deepcopy(inputs["contract"]),
        "closure": deepcopy(inputs["closure"]),
        "constraints": [
            {"path": row["path"], "format": row["format"], "raw_digest": row["raw_digest"], "text": row["text"]}
            for row in inputs["constraints"]
        ],
        "contexts": [
            {
                **{
                    k: deepcopy(row[k])
                    for k in ("kind", "path", "required", "format", "absence", "raw_digest")
                    if k in row
                },
                **({"value": deepcopy(row["value"])} if "value" in row else ({"text": row["text"]} if "text" in row else {})),
            }
            for row in inputs["contexts"]
        ],
        "evidence": deepcopy(inputs["evidence"]),
        "global_proof_authority": {
            "audit_ref": gp["audit_ref"],
            "manifest": deepcopy(gp["manifest"]),
            "report": deepcopy(gp["report"]),
            "unresolved": deepcopy(gp["unresolved"]),
            "ledger": deepcopy(gp["ledger"]),
            "proposals": deepcopy(gp["proposals"]),
            "accounting": deepcopy(gp["accounting"]),
        },
        "dependencies_files": deepcopy(inputs["dependencies"]["files"]),
    }


def _slim_authoritative_projections(frozen: dict) -> dict:
    """Compact authoritative source-identity pins and verbatim requirements for Stage 3 synthesis."""
    inputs = frozen["inputs"]
    gp = inputs["global_proof"]
    deps = inputs["dependencies"]["files"]
    manifest_path = next(
        (
            k
            for k in sorted(deps)
            if any(tok in Path(k).name.lower() for tok in ("source-manifest", "source_manifest"))
        ),
        None,
    )
    ledger_path = next(
        (
            k
            for k in sorted(deps)
            if any(
                tok in Path(k).name.lower()
                for tok in ("source-blocks", "source-ledger", "source_blocks", "source_ledger")
            )
        ),
        None,
    )
    return {
        "source_identity_pins": {
            "manifest_path": manifest_path,
            "manifest_raw_digest": deps.get(manifest_path) if manifest_path else None,
            "ledger_path": ledger_path,
            "ledger_raw_digest": deps.get(ledger_path) if ledger_path else None,
            "source_revision": gp["manifest"]["source_revision"],
            "source_manifest_digest": gp["manifest"]["manifest_sha256"],
        },
        "verbatim_requirements": [
            {
                "requirement_id": row["proposal_id"],
                "source_block_ids": deepcopy(row["source_block_ids"]),
                "acceptance_intent": row["acceptance_intent"],
                "non_task_sinks": deepcopy(row["non_task_sinks"]),
                "prior_requirement_ids": deepcopy(row["prior_requirement_ids"]),
            }
            for row in gp["proposals"]["proposals"]
        ],
    }


def _compact_candidate_projection(proposal: dict) -> dict:
    """Project candidate without intermediate draft_chain blobs while binding digests."""
    prov = proposal["provenance"]
    return {
        "schema_version": proposal["schema_version"],
        "input_stage": proposal["input_stage"],
        "input_identity": proposal["input_identity"],
        "proposal_sha256": canonical_sha(proposal),
        "provenance_summary": {
            "kind": prov["kind"],
            "declaration": prov["declaration"],
            "upstream_model_history": prov["upstream_model_history"],
            "draft_count": len(prov["draft_chain"]),
            "draft_identities": [codec.canonical_digest(d) for d in prov["draft_chain"]],
            "final_draft_identity": prov["final_draft_identity"],
        },
        "content": deepcopy(proposal["content"]),
    }


def segmented_generation_carrier_schema(
    frozen: dict, *, stage: str, ordinal: int, parent_draft_identities: list[str]
) -> dict:
    import _b_route_planning_runtime as runtime

    schema = deepcopy(frozen["inputs"]["delivery"]["output_schema"])
    schema["properties"]["input_identity"]["const"] = frozen["input_identity"]
    schema["properties"]["stage"]["const"] = stage
    schema["properties"]["ordinal"]["const"] = ordinal
    schema["properties"]["parent_draft_identities"]["const"] = list(parent_draft_identities)
    return runtime.generation_carrier_schema(schema)


_COMPILED_BASE_SCHEMA_CACHE: dict[str, dict] = {}


def segmented_provider_generation_schema(
    frozen: dict, *, stage: str, ordinal: int, parent_draft_identities: list[str]
) -> dict:
    import _b_route_planning_runtime as runtime

    ident = frozen["input_identity"]
    base_compiled = _COMPILED_BASE_SCHEMA_CACHE.get(ident)
    if base_compiled is None:
        base_compiled = runtime.compile_provider_schema(
            runtime.generation_carrier_schema(deepcopy(frozen["inputs"]["delivery"]["output_schema"]))
        )
        _COMPILED_BASE_SCHEMA_CACHE[ident] = base_compiled
    compiled = deepcopy(base_compiled)
    compiled["properties"]["input_identity"]["const"] = ident
    compiled["properties"]["stage"]["const"] = stage
    compiled["properties"]["ordinal"]["const"] = ordinal
    compiled["properties"]["parent_draft_identities"] = runtime.compile_provider_schema(
        {
            **deepcopy(frozen["inputs"]["delivery"]["output_schema"]["properties"]["parent_draft_identities"]),
            "const": list(parent_draft_identities),
        }
    )
    return compiled


def segmented_indexed_review_schema(
    state: dict,
    frozen: dict,
    *,
    proposal_sha256: str,
    seg_obligations: list[dict],
    seg_sources: list[dict],
    directive: dict | None = None,
) -> dict:
    """Build compact provider schema for a deterministic slice of obligations/sources."""
    import _b_route_planning_runtime as runtime

    ob_count = len(seg_obligations)
    src_count = len(seg_sources)
    check_row = {
        "type": "object",
        "properties": {
            "id": {"type": "integer", "minimum": 0, "maximum": max(ob_count - 1, 0)},
            "verdict": {"type": "string", "enum": ["approved", "blocked"]},
            "rationale": {"type": "string", "minLength": 1},
            "source_block_ids": {
                "type": "array",
                "minItems": 1,
                "maxItems": max(src_count, 1),
                "items": {"type": "integer", "minimum": 0, "maximum": max(src_count - 1, 0)},
            },
        },
        "required": ["id", "verdict", "rationale", "source_block_ids"],
        "additionalProperties": False,
    }
    props: dict = {
        "schema_version": {"type": "string", "const": runtime.INDEXED_REVIEW},
        "input_identity": {"type": "string", "const": runtime.descriptor(state)["input_identity"]},
        "runtime_identity": {"type": "string", "const": state["runtime_identity"]},
        "proposal_sha256": {"type": "string", "const": proposal_sha256},
        "verdict": {
            "type": "string",
            "enum": ["approved", "blocked"],
            "description": "blocked iff any item in checks (or reopen_reviews) has verdict=='blocked'; otherwise approved.",
        },
        "findings": {
            "type": "array",
            "items": {"type": "string", "minLength": 1},
            "description": "Exact deduplicated verbatim rationale strings copied from checks (and reopen_reviews) whose verdict=='blocked'; [] when approved.",
        },
        "checks": {
            "type": "array",
            "minItems": ob_count,
            "maxItems": ob_count,
            "items": check_row,
        },
    }
    if directive is not None:
        variants = [
            {
                "type": "object",
                "properties": {
                    "conflict_id": {"type": "string", "const": issue["id"]},
                    "plan_sha256": {"type": "string", "const": directive["plan"]["sha256"]},
                    "verdict": {"type": "string", "enum": ["resolved", "blocked"]},
                    "rationale": {"type": "string", "minLength": 1},
                },
                "required": ["conflict_id", "plan_sha256", "verdict", "rationale"],
                "additionalProperties": False,
            }
            for issue in directive["conflicts"]
            if issue["id"] in directive["resolution_required_conflict_ids"]
        ]
        props["reopen_reviews"] = {
            "type": "array",
            "items": {"anyOf": variants}
            if variants
            else {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            "minItems": len(variants),
            "maxItems": len(variants),
        }
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


def decode_segmented_review_slice(
    state: dict,
    frozen: dict,
    raw_value: dict,
    seg_obligations: list[dict],
    seg_sources: list[dict],
    *,
    proposal_sha256: str,
    directive: dict | None = None,
) -> dict:
    """Validate and decode one indexed review segment into canonical obligation checks."""
    import jsonschema

    schema = segmented_indexed_review_schema(
        state,
        frozen,
        proposal_sha256=proposal_sha256,
        seg_obligations=seg_obligations,
        seg_sources=seg_sources,
        directive=directive,
    )
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(raw_value))
    if errors:
        raise ValueError("b_route_segmented_review_schema_invalid:" + ";".join(e.message for e in errors))
    rows = raw_value["checks"]
    seen_ids = set()
    decoded_checks = []
    for row in sorted(rows, key=lambda item: item["id"]):
        idx = row["id"]
        if idx in seen_ids or not (0 <= idx < len(seg_obligations)):
            raise ValueError("b_route_segmented_review_duplicate_or_oob_id")
        seen_ids.add(idx)
        src_indices = row["source_block_ids"]
        if len(set(src_indices)) != len(src_indices):
            raise ValueError("b_route_segmented_review_duplicate_source_index")
        obligation = seg_obligations[idx]
        permitted = set(obligation["source_block_ids"])
        cited = []
        for s_idx in src_indices:
            if not (0 <= s_idx < len(seg_sources)):
                raise ValueError("b_route_segmented_review_oob_source_index")
            src_id = seg_sources[s_idx]["id"]
            if src_id not in permitted:
                raise ValueError("b_route_segmented_review_unpermitted_source")
            cited.append(src_id)
        if not row["rationale"].strip():
            raise ValueError("b_route_segmented_review_empty_rationale")
        decoded_checks.append(
            {
                "id": obligation["id"],
                "verdict": row["verdict"],
                "rationale": row["rationale"],
                "source_block_ids": cited,
            }
        )
    if len(seen_ids) != len(seg_obligations):
        raise ValueError("b_route_segmented_review_incomplete_slice")
    reopen_blocked = (
        [r["rationale"] for r in raw_value.get("reopen_reviews", []) if r["verdict"] == "blocked"]
        if directive is not None
        else []
    )
    blocked_rationales = list(
        dict.fromkeys([c["rationale"] for c in decoded_checks if c["verdict"] == "blocked"] + reopen_blocked)
    )
    findings = raw_value["findings"]
    if (
        len(set(findings)) != len(findings)
        or any(not f.strip() for f in findings)
        or bool(findings) != bool(blocked_rationales)
        or (raw_value["verdict"] == "blocked") != bool(blocked_rationales)
    ):
        raise ValueError("b_route_segmented_review_findings_mismatch")
    result = {
        "checks": decoded_checks,
        "findings": blocked_rationales,
        "verdict": raw_value["verdict"],
    }
    if directive is not None:
        result["reopen_reviews"] = deepcopy(raw_value["reopen_reviews"])
    return result


def _finalize_materials_and_measure(
    state: dict,
    frozen: dict,
    materials: dict,
    provider_schema: dict,
    *,
    compact_schema_file: bool = False,
    work=None,
) -> tuple[dict, str, int]:
    """Seal materials_identity, render wire prompt, and measure full workspace_payload bytes."""
    import _b_route_planning_runtime as runtime

    payload = deepcopy(materials)
    payload["segmented_runtime_policy"] = SEGMENTED_RUNTIME_POLICY
    payload["wire_delivery"] = runtime.wire_delivery(state) or wire.CURRENT_SCHEMA
    payload["input_compact_policy"] = state.get("b_route_input_compact_policy") or compact.CURRENT_SCHEMA
    account_policy = runtime.issue_account_policy(state)
    if account_policy is not None:
        payload["issue_account_policy"] = account_policy
    business_policy = runtime.machine_business_policy(state)
    if business_policy is not None:
        payload["machine_business_policy"] = business_policy
    if payload["phase"] == "generation":
        payload["output_schema_policy"] = runtime.PROVIDER_SCHEMA_POLICY
    directive = runtime.reopen_directive(state, frozen, payload.get("generation", 1))
    if directive is not None:
        payload["reopen_context"] = directive
    payload["actual_output_schema"] = provider_schema
    payload.pop("materials_identity", None)
    payload["materials_identity"] = canonical_sha(payload)
    work = compact._work(work)
    prompt_text = runtime.materials_prompt(payload, work=work)
    ws_text = seg_input._runner_wrapper_text(
        prompt_text, provider_schema, compact_schema_file=compact_schema_file
    )
    ws_utf8_len = len(ws_text.encode("utf-8"))
    exact_req_bytes = len(
        json.dumps(
            {"prompt": ws_text, "output_schema": provider_schema},
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )
    ws_bytes = max(ws_utf8_len, exact_req_bytes)
    mat_key = (
        codec.raw_digest(prompt_text.encode("utf-8")),
        canonical_sha(provider_schema),
        state.get("runtime_identity"),
        state.get("run_id"),
        runtime.wire_delivery(state),
        frozen.get("input_identity"),
        canonical_sha(frozen.get("reopen") or {}),
        canonical_sha(state.get("reopen") or {}),
    )
    _bounded_put(_VERIFIED_MATERIALS_CACHE, mat_key, deepcopy(payload), 256)
    return payload, prompt_text, ws_bytes


def _bounded_put(cache: dict, key, value, maxsize: int) -> None:
    if key in cache:
        cache.pop(key, None)
    elif len(cache) >= maxsize:
        cache.pop(next(iter(cache)), None)
    cache[key] = value


_GEN_SCHEMAS_CACHE: dict | None = None
_GEN_TARGET_CACHE: dict | None = None


def _cached_generation_schemas() -> dict:
    global _GEN_SCHEMAS_CACHE
    if _GEN_SCHEMAS_CACHE is None:
        import _b_route_planning_runtime as runtime

        _GEN_SCHEMAS_CACHE = runtime.generation_schemas()
    return _GEN_SCHEMAS_CACHE


def _cached_generation_target() -> dict:
    global _GEN_TARGET_CACHE
    if _GEN_TARGET_CACHE is None:
        import _b_route_planning_runtime as runtime

        _GEN_TARGET_CACHE = runtime.generation_target()
    return _GEN_TARGET_CACHE


def _fits_turn_budget(ws_bytes: int, frozen: dict) -> bool:
    reserved = int(frozen["inputs"]["contract"]["limits"]["reserved_tokens"])
    return ws_bytes <= MAX_WORKSPACE_PAYLOAD_BYTES and ws_bytes + reserved <= CONTEXT_TOKEN_LIMIT


def _assert_under_70k(ws_bytes: int, frozen: dict, label: str) -> None:
    reserved = int(frozen["inputs"]["contract"]["limits"]["reserved_tokens"])
    if ws_bytes > MAX_WORKSPACE_PAYLOAD_BYTES:
        raise ValueError(f"b_route_segmented_payload_exceeds_70k:{label}:{ws_bytes}")
    if ws_bytes + reserved > CONTEXT_TOKEN_LIMIT:
        raise ValueError(f"b_route_segmented_token_bound_exceeds_96k:{label}:{ws_bytes + reserved}")


def _is_def_item_in_repair_domain(allowed_paths: set, family: str, idx: int) -> bool:
    return any(
        len(p) >= 2 and p[:2] == ("definitions", family) and (len(p) == 2 or p[2] == idx)
        for p in allowed_paths
    )


def _slim_repair_prior_projection(
    prior: dict, frozen: dict, issue: dict, *, subfield_slim: bool = False
) -> dict:
    """Compact prior candidate projection preserving full repair_domain items and digest stubs elsewhere."""
    import _b_route_planning_runtime as runtime

    base_proj = _compact_candidate_projection(prior)
    allowed_paths = runtime.repair_domain(prior, frozen, issue)
    content = deepcopy(base_proj["content"])
    defs = content.get("definitions")
    keep_base_keys = {
        "id",
        "proposed_owner_key",
        "requirement_ids",
        "capability_ids",
        "source_block_ids",
    }
    if isinstance(defs, dict):
        for family in ("flows", "commands", "states"):
            items = defs.get(family)
            if not isinstance(items, list):
                continue
            slim_items = []
            for idx, row in enumerate(items):
                if _is_def_item_in_repair_domain(allowed_paths, family, idx):
                    if (
                        subfield_slim
                        and isinstance(row, dict)
                        and ("definitions", family) not in allowed_paths
                        and ("definitions", family, idx) not in allowed_paths
                    ):
                        allowed_subfields = {
                            p[3]
                            for p in allowed_paths
                            if len(p) >= 4 and p[:3] == ("definitions", family, idx)
                        }
                        slim_row = {}
                        for k, v in row.items():
                            if k in keep_base_keys or k in allowed_subfields:
                                slim_row[k] = v
                            elif isinstance(v, (dict, list)):
                                slim_row[k] = {"_subfield_stub_sha256": canonical_sha(v)}
                            else:
                                slim_row[k] = v
                        slim_items.append(slim_row)
                    else:
                        slim_items.append(row)
                else:
                    stub = {"id": row.get("id"), f"{family[:-1]}_sha256": canonical_sha(row)}
                    if "requirement_ids" in row:
                        stub["requirement_ids"] = list(row["requirement_ids"])
                    if "proposed_owner_key" in row:
                        stub["proposed_owner_key"] = row["proposed_owner_key"]
                    slim_items.append(stub)
            defs[family] = slim_items
    out = {**base_proj, "content": content, "slim_repair_projection": True}
    if subfield_slim:
        out["slim_repair_subfield"] = True
    return out


def _rehydrate_slim_repair_content(
    content: dict, prior_content: dict, *, allow_subfield: bool = False
) -> dict:
    """Deterministically rehydrate slim-repair digest stubs (and subfield stubs when allowed)."""
    out = deepcopy(content)
    if not isinstance(out, dict) or not isinstance(prior_content, dict):
        return out
    defs = out.get("definitions")
    prior_defs = prior_content.get("definitions")
    if not isinstance(defs, dict) or not isinstance(prior_defs, dict):
        return out
    for family in ("flows", "commands", "states"):
        items = defs.get(family)
        orig_items = prior_defs.get(family)
        if not isinstance(items, list) or not isinstance(orig_items, list) or len(items) != len(orig_items):
            continue
        sha_key = f"{family[:-1]}_sha256"
        allowed_stub_keys = {"id", sha_key, "requirement_ids", "proposed_owner_key"}
        for idx, (row, orig_row) in enumerate(zip(items, orig_items)):
            if not isinstance(row, dict) or not isinstance(orig_row, dict):
                continue
            if (
                sha_key in row
                and sha_key not in orig_row
                and set(row.keys()) <= allowed_stub_keys
                and row.get("id") == orig_row.get("id")
                and row.get(sha_key) == canonical_sha(orig_row)
                and (
                    "requirement_ids" not in row
                    or (
                        "requirement_ids" in orig_row
                        and row["requirement_ids"] == orig_row["requirement_ids"]
                    )
                )
                and (
                    "proposed_owner_key" not in row
                    or (
                        "proposed_owner_key" in orig_row
                        and row["proposed_owner_key"] == orig_row["proposed_owner_key"]
                    )
                )
            ):
                items[idx] = deepcopy(orig_row)
            elif allow_subfield:
                for k, v in list(row.items()):
                    if (
                        k in orig_row
                        and isinstance(v, dict)
                        and set(v.keys()) == {"_subfield_stub_sha256"}
                        and v["_subfield_stub_sha256"] == canonical_sha(orig_row[k])
                    ):
                        row[k] = deepcopy(orig_row[k])
    return out


_REPAIR_ITEM_STUB_KEYS = ("flow_sha256", "command_sha256", "state_sha256")


def _contains_subfield_stub(value: object) -> bool:
    """Return True when any nested dict carries a slim-repair subfield stub key."""
    stack = [value]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if "_subfield_stub_sha256" in cur:
                return True
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return False


def _contains_repair_stub(content: object) -> bool:
    """Return True when definitions still hold slim-repair item digests or subfield stubs."""
    if not isinstance(content, dict):
        return False
    defs = content.get("definitions")
    if not isinstance(defs, dict):
        return False
    for family in ("flows", "commands", "states"):
        items = defs.get(family)
        if not isinstance(items, list):
            continue
        sha_key = f"{family[:-1]}_sha256"
        for row in items:
            if isinstance(row, dict) and sha_key in row:
                return True
    stack: list = [defs]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            if "_subfield_stub_sha256" in cur or any(k in cur for k in _REPAIR_ITEM_STUB_KEYS):
                return True
            stack.extend(cur.values())
        elif isinstance(cur, list):
            stack.extend(cur)
    return False


def _expected_repair_draft(raw_decoded: dict, prior_content: dict, root_request: dict) -> dict:
    """Deterministically derive the retained repair draft from the sealed raw decoded carrier.

    The sealed raw output keeps slim-repair stubs; the retained draft carries fully rehydrated
    content so that draft_chain[-1].content equals the proposal content. Non-slim repairs must
    never echo stubs, subfield stubs are only resolved when explicitly requested, and any stub
    left unresolved after rehydration is rejected. The raw_decoded dict is never mutated.
    """
    import _b_route_planning_runtime as runtime

    slim_fb = bool(root_request.get("slim_repair_fallback"))
    slim_sub = bool(root_request.get("slim_repair_subfield"))
    compact_pin = bool(root_request.get("compact_contract_pin"))
    if (slim_sub and not (slim_fb and compact_pin)) or (compact_pin and not slim_fb):
        raise ValueError("b_route_segmented_repair_step_invalid")
    raw_content = raw_decoded["content"]
    if not slim_fb:
        if _contains_repair_stub(raw_content) or not runtime.same_json(
            _rehydrate_slim_repair_content(raw_content, prior_content, allow_subfield=True),
            raw_content,
        ):
            raise ValueError("b_route_segmented_unsolicited_repair_stub")
        return raw_decoded
    if not slim_sub and _contains_subfield_stub(raw_content):
        raise ValueError("b_route_segmented_unsolicited_repair_stub")
    rehydrated = _rehydrate_slim_repair_content(raw_content, prior_content, allow_subfield=slim_sub)
    if _contains_repair_stub(rehydrated):
        raise ValueError("b_route_segmented_unresolved_repair_stub")
    return {**raw_decoded, "content": rehydrated}


def _validated_review_projection_level(root_req: dict) -> tuple[bool, int]:
    """Validate the review scoped-projection flag and canonical projection_level."""
    scoped_val = root_req.get("scoped_proposal_projection", False)
    if type(scoped_val) is not bool:
        raise ValueError("b_route_segmented_review_materials_mismatch")
    if "projection_level" in root_req:
        lvl = root_req["projection_level"]
        if not scoped_val or type(lvl) is not int or lvl not in (2, 3):
            raise ValueError("b_route_segmented_review_materials_mismatch")
        return True, lvl
    return scoped_val, 1 if scoped_val else 0


def _validate_generation_request_flags(req: dict, materials: dict) -> None:
    """Enforce the strict slim-repair request flag lattice on sealed generation materials."""
    flags = ("slim_repair_fallback", "compact_contract_pin", "slim_repair_subfield")
    for key in flags:
        if key in req and (type(req[key]) is not bool or req[key] is not True):
            raise ValueError("b_route_segmented_generation_contract_changed")
    is_repair = (
        materials.get("repair_issue") is not None
        and req.get("synthesis_role") == "bounded_repair"
    )
    if "slim_repair_fallback" in req and not is_repair:
        raise ValueError("b_route_segmented_generation_contract_changed")
    if "compact_contract_pin" in req and not (is_repair and req.get("slim_repair_fallback") is True):
        raise ValueError("b_route_segmented_generation_contract_changed")
    if "slim_repair_subfield" in req and req.get("compact_contract_pin") is not True:
        raise ValueError("b_route_segmented_generation_contract_changed")



def _collect_directive_strings(value, out: set[str] | None = None) -> set[str]:
    if out is None:
        out = set()
    if isinstance(value, str):
        if value:
            out.add(value)
    elif isinstance(value, dict):
        for k, v in value.items():
            if isinstance(k, str) and k:
                out.add(k)
            _collect_directive_strings(v, out)
    elif isinstance(value, list):
        for item in value:
            _collect_directive_strings(item, out)
    return out


def _generation_contract_for_request(root_req: dict) -> tuple[dict, dict]:
    if (
        root_req.get("stage") == "batch"
        or root_req.get("synthesis_role") in ("rolling_compaction", "tree_reduce")
        or bool(root_req.get("compact_contract_pin"))
    ):
        return (
            {
                "schema_version": seg_input.INTERMEDIATE_CONTRACT_PIN_SCHEMA,
                "content_contract_sha256": canonical_sha(_cached_generation_schemas()),
            },
            {
                "schema_version": seg_input.INTERMEDIATE_TARGET_PIN_SCHEMA,
                "final_content_target_sha256": canonical_sha(_cached_generation_target()),
            },
        )
    return _cached_generation_schemas(), _cached_generation_target()


def _build_generation_materials(
    state: dict,
    frozen: dict,
    *,
    base_seed: dict,
    slot: str,
    generation_no: int,
    execution_no: int,
    lineage_id: str,
    context: int,
    root_req: dict,
    prior_projection: dict | None = None,
    issue: dict | None = None,
    repair_scope: dict | None = None,
    work=None,
) -> tuple[dict, dict, str, int]:
    import _b_route_planning_runtime as runtime

    provider_schema = segmented_provider_generation_schema(
        frozen,
        stage=root_req["stage"],
        ordinal=root_req["ordinal"],
        parent_draft_identities=root_req["parent_draft_identities"],
    )
    seed_projection = {
        "schema_version": base_seed["schema_version"],
        "input_identity": base_seed["input_identity"],
        "seed_sha256": canonical_sha(base_seed),
        "formal_adoption": False,
    }
    content_contract, final_target = _generation_contract_for_request(root_req)
    materials = {
        "schema_version": runtime.PROFILE,
        "phase": "generation",
        "root_request": root_req,
        "root_input_identity": frozen["input_identity"],
        "accepted_seed": seed_projection,
        "proposal": None,
        "prior_candidate": prior_projection,
        "repair_issue": deepcopy(issue) if issue is not None else None,
        "lineage_context": context,
        "content_contract": content_contract,
        "final_content_target": final_target,
        "runtime_identity": state["runtime_identity"],
        "run_id": state["run_id"],
        "slot": slot,
        "generation": generation_no,
        "execution": execution_no,
        "lineage_identity": lineage_id,
    }
    if issue is not None:
        materials["repair_scope_policy"] = runtime.REPAIR_SCOPE_POLICY
        materials["repair_scope"] = repair_scope
    sealed, prompt_text, ws_bytes = _finalize_materials_and_measure(
        state, frozen, materials, provider_schema, compact_schema_file=False, work=work
    )
    return sealed, provider_schema, prompt_text, ws_bytes


def _scoped_review_prior(
    prior_projection: dict | None, issue: dict | None = None, *, level: int = 2
) -> dict | None:
    """Compact prior_candidate projection for Stage 5 review at level >= 2."""
    del issue
    if prior_projection is None or level <= 0:
        return prior_projection
    if level < 2:
        return prior_projection
    return {
        "schema_version": prior_projection["schema_version"],
        "input_stage": prior_projection["input_stage"],
        "input_identity": prior_projection["input_identity"],
        "proposal_sha256": prior_projection["proposal_sha256"],
        "provenance_summary": deepcopy(prior_projection["provenance_summary"]),
        "content_sha256": canonical_sha(prior_projection["content"]),
        "compact_review_prior": True,
    }


def _trim_graph_to_budget(graph: dict, max_bytes: int = 40_000) -> dict:
    """Deterministically trim graph nodes/edges to fit max_bytes while keeping boundaries/loops/digests."""
    if _compact_bytes_len(graph) <= max_bytes:
        return graph
    orig_nodes = list(graph.get("nodes") or [])
    orig_edges = list(graph.get("edges") or [])
    boundaries = deepcopy(graph.get("boundaries", []))
    loops = deepcopy(graph.get("loops", []))
    extra = {k: deepcopy(v) for k, v in graph.items() if k not in ("nodes", "edges", "boundaries", "loops")}
    orig_sha = canonical_sha(graph)
    total = len(orig_nodes) + len(orig_edges)

    def _edge_endpoint(edge: object, side: str) -> object:
        if not isinstance(edge, dict):
            return None
        end = edge.get(side)
        return end.get("node_id") if isinstance(end, dict) else None

    def _build(mid: int) -> dict:
        if total <= 0:
            n_cnt, e_cnt = 0, 0
        else:
            n_cnt = min(len(orig_nodes), (len(orig_nodes) * mid) // total)
            e_cnt = min(len(orig_edges), mid - n_cnt)
        kept_nodes = orig_nodes[:n_cnt]
        kept_ids = {n.get("id") for n in kept_nodes if isinstance(n, dict)}
        kept_edges = [
            e
            for e in orig_edges[:e_cnt]
            if _edge_endpoint(e, "from") in kept_ids and _edge_endpoint(e, "to") in kept_ids
        ]
        return {
            **extra,
            "nodes": deepcopy(kept_nodes),
            "edges": deepcopy(kept_edges),
            "boundaries": boundaries,
            "loops": loops,
            "nodes_total": len(orig_nodes),
            "edges_total": len(orig_edges),
            "graph_sha256": orig_sha,
            "graph_trimmed": True,
            "edges_kept_valid": True,
        }

    lo, hi = 0, total
    best = _build(0)
    while lo <= hi:
        mid = (lo + hi) // 2
        cand = _build(mid)
        if _compact_bytes_len(cand) <= max_bytes:
            best = cand
            lo = mid + 1
        else:
            hi = mid - 1
    if _compact_bytes_len(best) > max_bytes:
        raise ValueError("b_route_segmented_graph_trim_insufficient")
    return best


def _scoped_review_proposal(
    proposal_proj: dict,
    seg_obs: list[dict],
    *,
    directive: dict | None = None,
    level: int = 1,
    seg_sources: list[dict] | None = None,
) -> dict:
    """Keep targeted obligation bodies and digest stubs elsewhere according to projection level."""
    if level <= 0:
        return proposal_proj
    targeted_flow_ids = {
        ob["target"][1]
        for ob in seg_obs
        if isinstance(ob.get("target"), list)
        and len(ob["target"]) >= 2
        and ob["target"][0] in ("flow", "flow_branch", "flow_part")
    }
    targeted_flow_aspects: dict[str, set[str]] = {}
    for ob in seg_obs:
        tgt = ob.get("target")
        if not isinstance(tgt, list) or len(tgt) < 2:
            continue
        kind, fid = tgt[0], tgt[1]
        if kind == "flow" and len(tgt) >= 3 and isinstance(tgt[2], str):
            targeted_flow_aspects.setdefault(fid, set()).add(tgt[2])
        elif kind == "flow_part":
            targeted_flow_aspects.setdefault(fid, set()).add("parts")
        elif kind == "flow_branch":
            targeted_flow_aspects.setdefault(fid, set()).add("branches")

    targeted_req_ids = {
        ob["target"][1]
        for ob in seg_obs
        if isinstance(ob.get("target"), list)
        and len(ob["target"]) >= 2
        and ob["target"][0] == "requirement"
    }
    directive_tokens = _collect_directive_strings(directive) if directive is not None else set()
    out = deepcopy(proposal_proj)
    content = out.get("content", {})
    defs = content.get("definitions") if isinstance(content.get("definitions"), dict) else content
    flows = defs.get("flows")
    if isinstance(flows, list):
        reopen_matched_flow_ids = set()
        if directive_tokens:
            for fl in flows:
                fid = fl.get("id")
                f_reqs = set(fl.get("requirement_ids", []))
                if (isinstance(fid, str) and fid in directive_tokens) or bool(f_reqs & directive_tokens):
                    if isinstance(fid, str):
                        reopen_matched_flow_ids.add(fid)
            if not reopen_matched_flow_ids and len(flows) <= 16:
                reopen_matched_flow_ids = {
                    fl["id"] for fl in flows if isinstance(fl.get("id"), str)
                }
        scoped_flows = []
        for fl in flows:
            fid = fl.get("id")
            f_reqs = set(fl.get("requirement_ids", []))
            if level == 1:
                if (
                    fid in targeted_flow_ids
                    or fid in reopen_matched_flow_ids
                    or (targeted_req_ids and (f_reqs & targeted_req_ids) and len(flows) <= 8)
                ):
                    scoped_flows.append(fl)
                else:
                    stub = {
                        "id": fid,
                        "requirement_ids": list(fl.get("requirement_ids", [])),
                        "flow_sha256": canonical_sha(fl),
                    }
                    if "proposed_owner_key" in fl:
                        stub["proposed_owner_key"] = fl["proposed_owner_key"]
                    scoped_flows.append(stub)
            else:
                if fid in targeted_flow_ids or fid in reopen_matched_flow_ids:
                    fl_orig_sha = canonical_sha(fl)
                    fl_out = deepcopy(fl)
                    aspects = targeted_flow_aspects.get(fid, set())
                    if fid not in reopen_matched_flow_ids:
                        if "graph" not in aspects and isinstance(fl_out.get("graph"), dict):
                            g = fl_out["graph"]
                            fl_out["graph"] = {
                                "nodes_count": len(g.get("nodes", [])),
                                "edges_count": len(g.get("edges", [])),
                                "boundaries": deepcopy(g.get("boundaries", [])),
                                "loops": deepcopy(g.get("loops", [])),
                                "graph_sha256": canonical_sha(g),
                            }
                        if "graph" in aspects:
                            if "parts" not in aspects and isinstance(fl_out.get("parts"), list):
                                fl_out["parts"] = [
                                    {
                                        "kind": p.get("kind"),
                                        "applicability": p.get("applicability"),
                                        "part_sha256": canonical_sha(p),
                                    }
                                    for p in fl_out["parts"]
                                ]
                            if "branches" not in aspects and isinstance(fl_out.get("branches"), list):
                                fl_out["branches"] = [
                                    {
                                        "kind": b.get("kind"),
                                        "applicability": b.get("applicability"),
                                        "boundary_ids": deepcopy(b.get("boundary_ids", [])),
                                        "branch_sha256": canonical_sha(b),
                                    }
                                    for b in fl_out["branches"]
                                ]
                    if level >= 3:
                        whole_flow = not aspects
                        if whole_flow:
                            aspects = {
                                k
                                for k in fl_out
                                if k not in ("id", "proposed_owner_key", "requirement_ids")
                            }
                        l3_fl = {
                            "id": fid,
                            "flow_sha256": fl_orig_sha,
                        }
                        if "proposed_owner_key" in fl:
                            l3_fl["proposed_owner_key"] = fl["proposed_owner_key"]
                        if "requirement_ids" in fl:
                            l3_fl["requirement_ids"] = list(fl["requirement_ids"])
                        for asp in sorted(aspects):
                            if asp in fl_out:
                                l3_fl[asp] = fl_out[asp]
                        if isinstance(l3_fl.get("graph"), dict) and "graph" in aspects:
                            l3_fl["graph"] = _trim_graph_to_budget(
                                l3_fl["graph"], max_bytes=32_000 if whole_flow else 40_000
                            )
                        fl_out = l3_fl
                    scoped_flows.append(fl_out)
                else:
                    stub = {
                        "id": fid,
                        "requirement_ids": list(fl.get("requirement_ids", [])),
                        "flow_sha256": canonical_sha(fl),
                    }
                    for k in (
                        "proposed_owner_key",
                        "capability_ids",
                        "source_block_ids",
                        "entry_condition",
                        "observable_result",
                    ):
                        if k in fl:
                            stub[k] = deepcopy(fl[k])
                    scoped_flows.append(stub)
        defs["flows"] = scoped_flows

    if level >= 2 and isinstance(content, dict):
        req_tables = (
            "requirements",
            "requirement_verification",
            "coverage_table",
            "requirement_route_memberships",
            "applicability",
        )
        source_obs_keys = {
            ob["target"][1]
            for ob in seg_obs
            if isinstance(ob.get("target"), list)
            and len(ob["target"]) >= 2
            and ob["target"][0] == "source"
        }
        source_block_ids_needed = (
            {
                s["block_id"]
                for s in (seg_sources or [])
                if s.get("id") in source_obs_keys and isinstance(s.get("block_id"), str)
            }
            if source_obs_keys
            else set()
        )
        req_rows = content.get("requirements")
        source_req_ids = (
            {
                r["requirement_id"]
                for r in req_rows
                if isinstance(r, dict)
                and isinstance(r.get("requirement_id"), str)
                and (set(r.get("source_block_ids", [])) & source_block_ids_needed)
            }
            if (source_block_ids_needed and isinstance(req_rows, list))
            else set()
        )
        keep_req_ids = targeted_req_ids if targeted_req_ids else source_req_ids
        if targeted_req_ids and source_req_ids:
            keep_req_ids = targeted_req_ids | source_req_ids
        if not keep_req_ids and isinstance(flows, list):
            keep_req_ids = {
                rid
                for fl in flows
                if isinstance(fl, dict)
                and (fl.get("id") in targeted_flow_ids or fl.get("id") in reopen_matched_flow_ids)
                for rid in (fl.get("requirement_ids") or [])
                if isinstance(rid, str)
            }
        omitted_digests: dict[str, dict] = {}
        for sec in req_tables:
            rows = content.get(sec)
            if not isinstance(rows, list):
                continue
            filtered = [
                row
                for row in rows
                if not isinstance(row, dict)
                or "requirement_id" not in row
                or row.get("requirement_id") in keep_req_ids
            ]
            if len(filtered) != len(rows):
                omitted_digests[sec] = {
                    "total_count": len(rows),
                    "sha256": canonical_sha(rows),
                }
                content[sec] = filtered
        if omitted_digests:
            content["omitted_requirement_table_digests"] = omitted_digests
    return out


def _plan_review_segments(
    state: dict,
    frozen: dict,
    *,
    base_seed: dict,
    proposal: dict,
    slot: str,
    generation_no: int,
    execution_no: int,
    lineage_id: str,
    context: int,
    prior_projection: dict | None,
    issue: dict | None,
) -> list[tuple[dict, dict, str, list[dict], list[dict]]]:
    """Deterministically partition obligations/qualified_sources so every review call <= 70,000 bytes."""
    import _b_route_planning_runtime as runtime

    all_obligations = runtime.obligations(proposal, frozen)
    all_sources = runtime.qualified_sources(proposal, frozen)
    source_by_id = {row["id"]: row for row in all_sources}
    directive = runtime.reopen_directive(state, frozen, generation_no)
    prop_sha = canonical_sha(proposal)
    proposal_proj = _compact_candidate_projection(proposal)
    seed_proj = {
        "schema_version": base_seed["schema_version"],
        "input_identity": base_seed["input_identity"],
        "seed_sha256": canonical_sha(base_seed),
        "formal_adoption": False,
    }
    review_common_hdr = {
        k: v
        for k, v in frozen["transport"]["common_header"].items()
        if k in ("input_identity", "contract_ref", "source_inventory")
    }
    reserved = int(frozen["inputs"]["contract"]["limits"]["reserved_tokens"])

    def build_slice(
        start: int, end: int, seg_idx: int, *, level: int = 0
    ) -> tuple[dict, dict, str, int, list[dict], list[dict]]:
        seg_obs = deepcopy(all_obligations[start:end])
        needed_src_ids = {sid for ob in seg_obs for sid in ob["source_block_ids"]}
        seg_srcs = [deepcopy(source_by_id[sid]) for sid in sorted(needed_src_ids) if sid in source_by_id]
        if not seg_srcs and all_sources:
            seg_srcs = [deepcopy(all_sources[0])]
        seg_directive = directive if start == 0 else None
        schema = segmented_indexed_review_schema(
            state,
            frozen,
            proposal_sha256=prop_sha,
            seg_obligations=seg_obs,
            seg_sources=seg_srcs,
            directive=seg_directive,
        )
        use_scoped = level >= 1
        active_prop = (
            _scoped_review_proposal(
                proposal_proj,
                seg_obs,
                directive=seg_directive,
                level=level,
                seg_sources=seg_srcs,
            )
            if use_scoped
            else proposal_proj
        )
        if prior_projection is None or level == 0:
            active_prior = prior_projection
        elif level == 1:
            active_prior = _scoped_review_proposal(
                prior_projection, seg_obs, directive=seg_directive, level=1
            )
        else:
            active_prior = _scoped_review_prior(prior_projection, issue, level=level)
        root_req = {
            "schema_version": seg_input.SEGMENTED_REQUEST_SCHEMA,
            "input_identity": frozen["input_identity"],
            "stage": "independent_admission",
            "segment_index": seg_idx,
            "obligation_range": [start, end],
            "total_obligations": len(all_obligations),
            "scoped_proposal_projection": use_scoped,
            "common_header": review_common_hdr if use_scoped else frozen["transport"]["common_header"],
        }
        if level >= 2:
            root_req["projection_level"] = level
        materials = {
            "schema_version": runtime.PROFILE,
            "phase": "independent_admission",
            "root_request": root_req,
            "root_input_identity": frozen["input_identity"],
            "accepted_seed": seed_proj,
            "proposal": active_prop,
            "prior_candidate": active_prior,
            "repair_issue": deepcopy(issue) if issue is not None else None,
            "lineage_context": context,
            "obligations": seg_obs,
            "qualified_sources": seg_srcs,
            "review_source_policy": runtime.REVIEW_SOURCE_POLICY,
            "runtime_identity": state["runtime_identity"],
            "run_id": state["run_id"],
            "slot": slot,
            "generation": generation_no,
            "execution": execution_no,
            "lineage_identity": lineage_id,
        }
        if seg_directive is not None:
            materials["reopen_context"] = deepcopy(seg_directive)
        sealed, prompt_text, ws_bytes = _finalize_materials_and_measure(
            state, frozen, materials, schema, compact_schema_file=True
        )
        return sealed, schema, prompt_text, ws_bytes, seg_obs, seg_srcs

    total = len(all_obligations)
    if total == 0:
        return []

    # Fast path: check if entire review fits in a single segment with full proposal
    full_mat, full_sch, full_prm, full_bytes, full_obs, full_srcs = build_slice(
        0, total, 1, level=0
    )
    if _fits_turn_budget(full_bytes, frozen):
        return [(full_mat, full_sch, full_prm, full_obs, full_srcs)]

    segments = []
    idx = 0
    sticky_level = 0
    eff_limit = min(MAX_WORKSPACE_PAYLOAD_BYTES, CONTEXT_TOKEN_LIMIT - reserved)
    while idx < total:
        seg_no = len(segments) + 1
        use_level = min(sticky_level, 2)
        s_mat, s_sch, s_prm, s_bytes, s_obs, s_srcs = build_slice(
            idx, idx + 1, seg_no, level=use_level
        )
        if not _fits_turn_budget(s_bytes, frozen):
            for cand_level in (1, 2, 3):
                if cand_level <= use_level:
                    continue
                use_level = cand_level
                s_mat, s_sch, s_prm, s_bytes, s_obs, s_srcs = build_slice(
                    idx, idx + 1, seg_no, level=use_level
                )
                if _fits_turn_budget(s_bytes, frozen):
                    break
            sticky_level = max(sticky_level, min(use_level, 2))
        _assert_under_70k(s_bytes, frozen, f"review-seg-{seg_no}-single")
        best_end = idx + 1
        best_pack = (s_mat, s_sch, s_prm, s_obs, s_srcs)

        if idx + 1 < total and use_level < 3:
            per_ob_est = max(80.0, (full_bytes - s_bytes) / max(1, total - 1))
            est_more = max(1, int(max(0, eff_limit - s_bytes) / per_ob_est * 0.9))
            guess = min(total, idx + 1 + est_more)
            g_mat, g_sch, g_prm, g_bytes, g_obs, g_srcs = build_slice(
                idx, guess, seg_no, level=use_level
            )
            if _fits_turn_budget(g_bytes, frozen):
                best_end = guess
                best_pack = (g_mat, g_sch, g_prm, g_obs, g_srcs)
                low = guess + 1
                high = total
                step = max(2, est_more // 2)
                while guess + step <= total:
                    probe_end = min(guess + step, total)
                    c_mat, c_sch, c_prm, c_bytes, c_obs, c_srcs = build_slice(
                        idx, probe_end, seg_no, level=use_level
                    )
                    if _fits_turn_budget(c_bytes, frozen):
                        best_end = probe_end
                        best_pack = (c_mat, c_sch, c_prm, c_obs, c_srcs)
                        low = probe_end + 1
                        if probe_end == total:
                            high = total - 1
                            break
                        step *= 2
                    else:
                        high = probe_end - 1
                        break
            else:
                low = idx + 2
                high = guess - 1
            while low <= high:
                mid = (low + high) // 2
                c_mat, c_sch, c_prm, c_bytes, c_obs, c_srcs = build_slice(
                    idx, mid, seg_no, level=use_level
                )
                if _fits_turn_budget(c_bytes, frozen):
                    best_end = mid
                    best_pack = (c_mat, c_sch, c_prm, c_obs, c_srcs)
                    low = mid + 1
                else:
                    high = mid - 1
        segments.append(best_pack)
        idx = best_end
    return segments


def generate_segmented_append(
    root: Path,
    state: dict,
    workspace: Path,
    *,
    invoke_factory,
    before_call,
    checkpoint,
    scope_index=None,
    accepted_seed=None,
    selected_records=None,
    cost_budget=None,
    replacement=None,
    should_pause=None,
) -> dict:
    """Execute <=70k segmented Stages 1-5 inside run_capability_append."""
    import _b_route_planning_runtime as runtime
    from _mvg_capability_append import SlicePauseRequested, run_capability_append

    frozen = runtime.frozen_input(root, state, prepared=workspace / "analysis-input")
    all_scopes = runtime.scopes(state, workspace / "analysis-input")
    base = (
        runtime.seed(state, workspace / "analysis-input")
        if accepted_seed is None
        else deepcopy(accepted_seed)
    )
    ledger = load_json(workspace / "capability-append/append-ledger.json", {})
    prior_local_calls = list(ledger.get("calls") or [])
    count = [ledger.get("total_invocations", 0)]
    repair_origin = [None]
    last_generation_calls_by_proposal: dict[str, list[dict]] = {}

    def check_cost(phase: str, evidence_calls: int) -> None:
        if cost_budget is None:
            return
        costs = workspace / "capability-append/stage-costs"
        if len(prior_local_calls) > count[0] and (costs / f"{count[0] + 1}-{phase}.json").is_file():
            return
        from _mvg_capability_generation import stage_cost_preflight

        budget = cost_budget(phase, known_evidence_calls=evidence_calls)
        stage_cost_preflight(
            costs / f"{count[0] + 1}-{phase}.json",
            phase=phase,
            evidence_calls=evidence_calls,
            **budget,
        )

    def _replay_completed_call(
        call_no: int,
        sealed_materials: dict,
        provider_schema: dict,
        ws_text: str,
        phase: str,
    ) -> tuple[dict, dict] | None:
        if call_no > len(prior_local_calls):
            return None
        local_row = prior_local_calls[call_no - 1]
        if local_row.get("number") != call_no or local_row.get("phase") != phase:
            raise ValueError("b_route_segmented_replay_call_mismatch")
        call_dir = segmented_call_root(workspace, call_no)
        res_id = local_row.get("reservation_id")
        if res_id:
            coord_calls = (state.get("capability_selection") or {}).get("calls", [])
            matches = [row for row in coord_calls if row.get("reservation_id") == res_id]
            if len(matches) != 1:
                raise ValueError("b_route_segmented_replay_reservation_missing")
            coord_row = matches[0]
            resolved_run_dir = next((p for p in workspace.parents if (p / "run.json").is_file()), None)
            if resolved_run_dir is None:
                resolved_run_dir = runtime.run_location(
                    root, runtime.descriptor(state)["planner"], state["run_id"]
                )
            binding = verify_segmented_reserved_call(
                resolved_run_dir, coord_row, state=state, check_originals=False
            )
            if binding is None or (coord_row.get("outcome") or {}).get("status") != "completed":
                raise ValueError("b_route_segmented_replay_outcome_not_completed")
            req_id = coord_row.get("request_identity") or {}
            actual_sha = codec.raw_digest(ws_text.encode("utf-8"))
            if (
                req_id.get("actual_request_sha256") != actual_sha
                or req_id.get("fresh_lineage_identity") != sealed_materials.get("lineage_identity")
                or not runtime.same_json(
                    codec.strict_json_loads(Path(binding["schema_path"]).read_bytes()),
                    provider_schema,
                )
            ):
                raise ValueError("b_route_segmented_replay_request_changed")
            raw_val = _verified_call_output(binding, readonly=True)
            if sealed_materials["phase"] == "generation":
                decoded = load_json(call_dir / "canonical-draft.json")
                if not runtime.same_json(_cached_decode_generation_carrier(raw_val), decoded):
                    raise ValueError("b_route_generation_canonical_draft_changed")
                return decoded, binding
            return raw_val, binding
        out_path = call_dir / "r.json"
        if not out_path.is_file():
            raise ValueError("b_route_segmented_replay_output_missing")
        schema_path = call_dir / "output-schema.json"
        if schema_path.is_file() and not runtime.same_json(
            codec.strict_json_loads(schema_path.read_bytes()), provider_schema
        ):
            raise ValueError("b_route_segmented_replay_schema_changed")
        raw_val = codec.strict_json_loads(out_path.read_bytes())
        binding_path = call_dir / f"execution-binding-{call_no}-r.json"
        if binding_path.is_file():
            binding = codec.strict_json_loads(binding_path.read_bytes())
        else:
            binding = {
                "workspace": str(call_dir),
                "output_path": str(out_path),
                "request_payload": ws_text,
            }
        if sealed_materials["phase"] == "generation":
            draft_path = call_dir / "canonical-draft.json"
            decoded = (
                load_json(draft_path)
                if draft_path.is_file()
                else runtime.decode_generation_carrier(raw_val)
            )
            return decoded, binding
        return raw_val, binding

    def execute_call(
        sealed_materials: dict,
        provider_schema: dict,
        prompt_text: str,
        phase: str,
        call,
        *,
        compact_schema_file: bool = False,
    ) -> tuple[dict, dict]:
        count[0] += 1
        call_no = count[0]
        ws_text = seg_input._runner_wrapper_text(
            prompt_text, provider_schema, compact_schema_file=compact_schema_file
        )
        _assert_under_70k(len(ws_text.encode("utf-8")), frozen, f"{phase}-{call_no}")
        replayed = _replay_completed_call(call_no, sealed_materials, provider_schema, ws_text, phase)
        if replayed is not None:
            return replayed
        effective_pause = should_pause if should_pause is not None else _ACTIVE_SHOULD_PAUSE.get()
        if effective_pause is not None and effective_pause():
            count[0] -= 1
            raise SlicePauseRequested("b_route_slice_pause_requested")
        call_dir = segmented_call_root(workspace, call_no)
        output, execution = invoke_factory(call_dir)(
            prompt_text,
            call_no,
            output_name="r.json",
            output_schema_path=call_dir / "output-schema.json",
            output_schema=provider_schema,
            before_dispatch=lambda request_identity=None: call(phase, request_identity),
        )
        raw_value = codec.strict_json_loads(output.read_bytes())
        binding = execution.get("execution_binding")
        if not isinstance(binding, dict):
            raise ValueError("b_route_real_execution_binding_missing")
        runtime.verify_call(binding)
        if len(binding["request_payload"].encode("utf-8")) > MAX_WORKSPACE_PAYLOAD_BYTES:
            raise ValueError("b_route_segmented_actual_binding_exceeded_70k")
        if sealed_materials["phase"] == "generation":
            decoded = runtime.decode_generation_carrier(raw_value)
            atomic_json(call_dir / "canonical-draft.json", decoded)
            return decoded, binding
        return raw_value, binding

    def propose(scope, accepted, prior, issue, context, call):
        runtime.validate_input(root, workspace, state)
        live_ledger = load_json(workspace / "capability-append/append-ledger.json", {})
        live_current = live_ledger.get("current") or {}
        if "propose_start_call" in live_current:
            count[0] = int(live_current["propose_start_call"])
        slot = state["runtime_slot"]
        generation_no = state.get("capability_selection", {}).get("generation", 1)
        execution_no = state.get("runtime_execution", 1)
        lineage_id = runtime.lineage_identity(state, base, slot, context, generation_no, execution_no)
        batches = frozen["transport"]["batches"]

        if prior is not None and issue is not None:
            # Stage 4: Bounded segmented single-delta repair without duplicating historical draft_chain
            repair_origin[0] = (
                (prior, runtime.obligations(prior, frozen), runtime.semantic_domain(prior, frozen)[0], issue)
                if issue.get("account_policy") is not None
                else None
            )
            check_cost("inspect", 1)
            prior_sha = canonical_sha(prior)
            prior_calls = last_generation_calls_by_proposal.get(prior_sha)
            if prior_calls is None:
                cur_delta = live_current.get("delta") or {}
                if (
                    isinstance(cur_delta.get("generation_calls"), list)
                    and canonical_sha(live_current.get("proposal")) == prior_sha
                    and len(cur_delta["generation_calls"]) == len(prior["provenance"]["draft_chain"])
                ):
                    prior_calls = list(cur_delta["generation_calls"])
            if prior_calls is None:
                raise ValueError("b_route_segmented_repair_prior_calls_missing")
            prior_chain = deepcopy(prior["provenance"]["draft_chain"])
            parent_ids = planning.validate_draft_chain(frozen, prior_chain)
            repair_ordinal = len(prior_chain) + 1
            repair_scope = runtime.repair_scope_metadata(prior, frozen, issue)
            prior_proj = _compact_candidate_projection(prior)
            root_req = {
                "schema_version": seg_input.SEGMENTED_REQUEST_SCHEMA,
                "input_identity": frozen["input_identity"],
                "stage": "synthesis",
                "synthesis_role": "bounded_repair",
                "ordinal": repair_ordinal,
                "common_header": frozen["transport"]["common_header"],
                "parent_draft_identities": parent_ids,
            }
            def _build_repair_rung(rung_req: dict, rung_prior: dict):
                # Each escalation rung is an independent candidate request: it gets its own
                # bounded request work account (same convention as Stage 1-3 builders), so
                # rejected oversized rungs never drain the account of the final sealed request.
                with runtime.request_resources() as work:
                    return _build_generation_materials(
                        state,
                        frozen,
                        base_seed=accepted,
                        slot=slot,
                        generation_no=generation_no,
                        execution_no=execution_no,
                        lineage_id=lineage_id,
                        context=context,
                        root_req=rung_req,
                        prior_projection=rung_prior,
                        issue=issue,
                        repair_scope=repair_scope,
                        work=work,
                    )

            sealed, prov_schema, prompt_text, ws_bytes = _build_repair_rung(root_req, prior_proj)
            if not _fits_turn_budget(ws_bytes, frozen):
                slim_hdr = {
                    k: v
                    for k, v in frozen["transport"]["common_header"].items()
                    if k in ("input_identity", "contract_ref", "contract", "source_inventory")
                }
                slim_req = {**root_req, "common_header": slim_hdr}
                sealed, prov_schema, prompt_text, ws_bytes = _build_repair_rung(slim_req, prior_proj)
            if not _fits_turn_budget(ws_bytes, frozen):
                slim_hdr = {
                    k: v
                    for k, v in frozen["transport"]["common_header"].items()
                    if k in ("input_identity", "contract_ref", "contract", "source_inventory")
                }
                slim_req = {**root_req, "common_header": slim_hdr, "slim_repair_fallback": True}
                slim_prior = _slim_repair_prior_projection(prior, frozen, issue)
                sealed, prov_schema, prompt_text, ws_bytes = _build_repair_rung(slim_req, slim_prior)
            if not _fits_turn_budget(ws_bytes, frozen):
                slim_req = {**slim_req, "compact_contract_pin": True}
                sealed, prov_schema, prompt_text, ws_bytes = _build_repair_rung(slim_req, slim_prior)
            if not _fits_turn_budget(ws_bytes, frozen):
                slim_req = {**slim_req, "slim_repair_subfield": True}
                slim_prior = _slim_repair_prior_projection(prior, frozen, issue, subfield_slim=True)
                sealed, prov_schema, prompt_text, ws_bytes = _build_repair_rung(slim_req, slim_prior)
            _assert_under_70k(ws_bytes, frozen, f"repair-{repair_ordinal}")
            # execute_call returns the raw decoded carrier both on fresh dispatch and on
            # slice-resume replay (sealed r.json and canonical-draft.json stay raw), so the
            # same deterministic rehydration applies on every path.
            raw_repair_draft, repair_binding = execute_call(
                sealed, prov_schema, prompt_text, "repair", call
            )
            repair_draft = _expected_repair_draft(
                raw_repair_draft, prior["content"], sealed["root_request"]
            )
            drafts = [*prior_chain, repair_draft]
            planning.validate_draft_chain(frozen, drafts)
            executions = [*prior_calls, repair_binding]
        else:
            # Stage 1/2: Segmented batch generation with bounded rolling window state
            repair_origin[0] = None
            check_cost("inspect", len(batches))
            drafts: list[dict] = []
            executions: list[dict] = []
            window_terminals: list[dict] = []
            rolling_draft: dict | None = None
            window_index = 1

            for batch in batches:
                ordinal = batch["ordinal"]
                parent_ids = [codec.canonical_digest(d) for d in drafts]
                rolling_state = None
                if rolling_draft is not None:
                    rolling_state = {
                        "window_index": window_index,
                        "previous_ordinal": rolling_draft["ordinal"],
                        "previous_draft_identity": codec.canonical_digest(rolling_draft),
                        "completed_window_identities": [
                            codec.canonical_digest(w) for w in window_terminals
                        ],
                        "rolling_content": rolling_draft["content"],
                    }
                elif window_terminals:
                    rolling_state = {
                        "window_index": window_index,
                        "completed_window_identities": [
                            codec.canonical_digest(w) for w in window_terminals
                        ],
                    }

                def _batch_budget_hint() -> dict:
                    return {
                        "target_compact_bytes": MAX_INTERMEDIATE_DRAFT_BYTES,
                        "rule": (
                            "Emit concise structured planning index strictly preserving exact source_identity "
                            "(manifest_ref, ledger_ref, source_revision, source_manifest_digest), exact "
                            "proposals/requirements fields (id, source_block_ids, acceptance_intent, "
                            "non_task_sinks, prior_requirement_ids), file paths/raw_digest, and flow/entity/"
                            "boundary/handoff/obligation IDs; omit long scenario transcripts and duplicate prose."
                        ),
                    }

                def make_batch_call(rs, *, include_budget_hint: bool = True):
                    req = {
                        "schema_version": seg_input.SEGMENTED_REQUEST_SCHEMA,
                        "input_identity": frozen["input_identity"],
                        "stage": "batch",
                        "ordinal": ordinal,
                        "common_header": frozen["transport"]["common_header"],
                        "batch_parts": batch["parts"],
                        "rolling_state": rs,
                        "parent_draft_identities": parent_ids,
                    }
                    if include_budget_hint:
                        req["intermediate_draft_budget"] = _batch_budget_hint()
                    with runtime.request_resources() as work:
                        return _build_generation_materials(
                            state,
                            frozen,
                            base_seed=accepted,
                            slot=slot,
                            generation_no=generation_no,
                            execution_no=execution_no,
                            lineage_id=lineage_id,
                            context=context,
                            root_req=req,
                            work=work,
                        )

                sealed, prov_schema, prompt_text, ws_bytes = make_batch_call(rolling_state, include_budget_hint=True)
                if not _fits_turn_budget(ws_bytes, frozen) and rolling_draft is not None:
                    # Roll over window immediately so payload stays strictly <= 70,000 bytes and <= 96,000 tokens
                    window_terminals.append(rolling_draft)
                    rolling_draft = None
                    window_index += 1
                    rolling_state = {
                        "window_index": window_index,
                        "completed_window_identities": [
                            codec.canonical_digest(w) for w in window_terminals
                        ],
                    }
                    sealed, prov_schema, prompt_text, ws_bytes = make_batch_call(rolling_state, include_budget_hint=True)
                if not _fits_turn_budget(ws_bytes, frozen):
                    sealed, prov_schema, prompt_text, ws_bytes = make_batch_call(rolling_state, include_budget_hint=False)
                _assert_under_70k(ws_bytes, frozen, f"batch-{ordinal}")
                draft, binding = execute_call(sealed, prov_schema, prompt_text, "generate", call)
                drafts.append(draft)
                planning.validate_draft_chain(frozen, drafts)
                executions.append(binding)

                if _compact_bytes_len(draft["content"]) > MAX_ROLLING_DRAFT_BYTES:
                    window_terminals.append(draft)
                    rolling_draft = None
                    window_index += 1
                else:
                    rolling_draft = draft

            if rolling_draft is not None:
                window_terminals.append(rolling_draft)

            # Stage 3: Tree-reduce / compact window terminals until final synthesis fits <= 70k / 96k
            active_windows = [
                {"ordinal": w["ordinal"], "identity": codec.canonical_digest(w), "content": w["content"]}
                for w in window_terminals
            ]
            auth_core = _authoritative_core_summary(frozen)
            slim_proj = _slim_authoritative_projections(frozen)

            def _shard_value_chunks(key: str, val, max_chunk_bytes: int) -> list[dict]:
                if isinstance(val, list) and len(val) > 1:
                    chunks: list[dict] = []
                    cur_items: list = []
                    start_idx = 0
                    for idx, item in enumerate(val):
                        cand = {key: [*cur_items, item], "_sharded_key": key, "_slice": [start_idx, idx + 1]}
                        if cur_items and _compact_bytes_len(cand) > max_chunk_bytes:
                            chunks.append({key: cur_items, "_sharded_key": key, "_slice": [start_idx, idx]})
                            cur_items = [item]
                            start_idx = idx
                        else:
                            cur_items.append(item)
                    if cur_items:
                        chunks.append({key: cur_items, "_sharded_key": key, "_slice": [start_idx, len(val)]})
                    if len(chunks) > 1:
                        return chunks
                if isinstance(val, dict) and val:
                    sub_shards = _shard_dict_chunks(val, max_chunk_bytes=max_chunk_bytes)
                    if len(sub_shards) > 1:
                        return [{key: sub, "_sharded_key": key} for sub in sub_shards]
                if isinstance(val, str) and len(val) > 1:
                    text_chunks: list[dict] = []
                    pos = 0
                    total_len = len(val)
                    while pos < total_len:
                        lo, hi, best = 1, total_len - pos, 1
                        while lo <= hi:
                            mid = (lo + hi) // 2
                            probe = {key: val[pos : pos + mid], "_sharded_key": key, "_char_range": [pos, pos + mid]}
                            if _compact_bytes_len(probe) <= max_chunk_bytes:
                                best = mid
                                lo = mid + 1
                            else:
                                hi = mid - 1
                        text_chunks.append({key: val[pos : pos + best], "_sharded_key": key, "_char_range": [pos, pos + best]})
                        pos += best
                    if len(text_chunks) > 1:
                        return text_chunks
                return [{key: val}]

            def _shard_dict_chunks(obj: dict, *, max_chunk_bytes: int) -> list[dict]:
                chunks: list[dict] = []
                cur: dict = {}
                for k, v in obj.items():
                    cand = {**cur, k: v}
                    if _compact_bytes_len(cand) <= max_chunk_bytes:
                        cur = cand
                        continue
                    if cur:
                        chunks.append(cur)
                        cur = {}
                    single = {k: v}
                    if _compact_bytes_len(single) <= max_chunk_bytes:
                        cur = single
                    else:
                        sub_parts = _shard_value_chunks(k, v, max_chunk_bytes)
                        if len(sub_parts) > 1:
                            chunks.extend(sub_parts)
                        else:
                            chunks.append(single)
                if cur:
                    chunks.append(cur)
                return chunks

            def _shard_oversized_window(win: dict, *, max_chunk_bytes: int) -> list[dict]:
                content_obj = win["content"]
                if not isinstance(content_obj, dict) or _compact_bytes_len(content_obj) <= max_chunk_bytes:
                    return [win]
                raw_chunks = _shard_dict_chunks(content_obj, max_chunk_bytes=max_chunk_bytes)
                if len(raw_chunks) <= 1:
                    return [win]
                total_shards = len(raw_chunks)
                return [
                    {
                        "ordinal": win["ordinal"],
                        "identity": win["identity"],
                        **({"parent_shard": win["shard"]} if "shard" in win else {}),
                        "shard": f"{s_idx}/{total_shards}",
                        "content": chunk,
                    }
                    for s_idx, chunk in enumerate(raw_chunks, 1)
                ]

            def make_synth_call(
                win_items: list[dict],
                role: str,
                auth_mode: bool | str,
                *,
                target_compact_bytes: int | None = None,
            ):
                synth_ordinal = len(drafts) + 1
                parent_ids = [codec.canonical_digest(d) for d in drafts]
                hdr = (
                    {
                        k: v
                        for k, v in frozen["transport"]["common_header"].items()
                        if k in ("input_identity", "contract_ref", "source_inventory")
                    }
                    if role == "tree_reduce"
                    else frozen["transport"]["common_header"]
                )
                req = {
                    "schema_version": seg_input.SEGMENTED_REQUEST_SCHEMA,
                    "input_identity": frozen["input_identity"],
                    "stage": "synthesis",
                    "synthesis_role": role,
                    "ordinal": synth_ordinal,
                    "common_header": hdr,
                    "window_drafts": win_items,
                    "parent_draft_identities": parent_ids,
                }
                if role == "tree_reduce":
                    req["compaction_target"] = {
                        "target_compact_bytes": int(target_compact_bytes or MAX_INTERMEDIATE_DRAFT_BYTES),
                        "hard_max_compact_bytes": MAX_STAGE3_SHARD_BYTES,
                        "purpose": (
                            "Deduplicate and compact window_drafts so final_synthesis fits alongside the 38KB "
                            "candidate schema closure. Preserve exact source_identity paths/digests/revision, "
                            "exact proposals/requirements fields, file paths/raw_digest, and concise flow/"
                            "entity/boundary/handoff/obligation IDs; drop verbose scenario transcripts and duplicate prose."
                        ),
                    }
                if auth_mode is True or auth_mode == "full":
                    req["authoritative_core"] = auth_core
                elif auth_mode == "slim":
                    req["authoritative_projections"] = slim_proj
                elif auth_mode not in (False, "none"):
                    raise ValueError(f"b_route_segmented_unknown_auth_mode:{auth_mode}")
                with runtime.request_resources() as work:
                    return _build_generation_materials(
                        state,
                        frozen,
                        base_seed=accepted,
                        slot=slot,
                        generation_no=generation_no,
                        execution_no=execution_no,
                        lineage_id=lineage_id,
                        context=context,
                        root_req=req,
                        work=work,
                    )

            def _try_final_synthesis(win_items: list[dict]):
                for mode in ("full", "slim", False):
                    cand = make_synth_call(win_items, "final_synthesis", mode)
                    if _fits_turn_budget(cand[3], frozen):
                        return cand
                return None

            empty_final_bytes = make_synth_call([], "final_synthesis", False)[3]
            reserved_toks = int(frozen["inputs"]["contract"]["limits"]["reserved_tokens"])
            eff_budget = min(MAX_WORKSPACE_PAYLOAD_BYTES, CONTEXT_TOKEN_LIMIT - reserved_toks)
            hard_final_window_cap = max(8_000, eff_budget - empty_final_bytes - 4_000)
            default_compact_target = max(8_000, min(MAX_INTERMEDIATE_DRAFT_BYTES, int(hard_final_window_cap * 0.72)))

            MAX_STAGE3_REDUCE_ROUNDS = 16
            reduce_rounds = 0
            single_compact_attempts = 0
            ready_final = _try_final_synthesis(active_windows)
            while ready_final is None:
                if reduce_rounds >= MAX_STAGE3_REDUCE_ROUNDS:
                    break
                reduce_rounds += 1
                group_start = 0
                group_end = 0
                best_reduce = None

                if len(active_windows) > 1:
                    # Prefer largest prefix >= 2 fitting tree_reduce; otherwise check any adjacent pair >= 2
                    for k in range(2, len(active_windows) + 1):
                        cand_k = make_synth_call(
                            active_windows[:k],
                            "tree_reduce",
                            False,
                            target_compact_bytes=default_compact_target,
                        )
                        if _fits_turn_budget(cand_k[3], frozen):
                            group_start, group_end = 0, k
                            best_reduce = cand_k
                        else:
                            break
                    if best_reduce is None:
                        for start_i in range(1, len(active_windows) - 1):
                            cand_pair = make_synth_call(
                                active_windows[start_i : start_i + 2],
                                "tree_reduce",
                                False,
                                target_compact_bytes=default_compact_target,
                            )
                            if _fits_turn_budget(cand_pair[3], frozen):
                                group_start, group_end = start_i, start_i + 2
                                best_reduce = cand_pair
                                break

                if best_reduce is None:
                    # Either len == 1 still > final_synthesis budget, or every pair > tree_reduce 70k budget.
                    # Compact the largest single window (or shard it deterministically if > tree_reduce budget).
                    single_compact_attempts += 1
                    target_idx = max(
                        range(len(active_windows)),
                        key=lambda i: _compact_bytes_len(active_windows[i]["content"]),
                    )
                    target_b = (
                        default_compact_target
                        if single_compact_attempts == 1
                        else max(6_000, default_compact_target // min(single_compact_attempts, 3))
                    )
                    cand_single = make_synth_call(
                        [active_windows[target_idx]],
                        "tree_reduce",
                        False,
                        target_compact_bytes=target_b,
                    )
                    if _fits_turn_budget(cand_single[3], frozen):
                        group_start, group_end = target_idx, target_idx + 1
                        best_reduce = cand_single
                    else:
                        shards = _shard_oversized_window(
                            active_windows[target_idx], max_chunk_bytes=MAX_STAGE3_SHARD_BYTES
                        )
                        if len(shards) > 1:
                            active_windows = [
                                *active_windows[:target_idx],
                                *shards,
                                *active_windows[target_idx + 1 :],
                            ]
                            ready_final = _try_final_synthesis(active_windows)
                            continue
                        group_start, group_end = target_idx, target_idx + 1
                        best_reduce = cand_single

                r_sealed, r_sch, r_prm, r_bytes = best_reduce
                _assert_under_70k(r_bytes, frozen, f"tree-reduce-{len(drafts) + 1}")
                prev_slice_bytes = sum(
                    _compact_bytes_len(w["content"]) for w in active_windows[group_start:group_end]
                )
                reduced_draft, reduced_binding = execute_call(
                    r_sealed, r_sch, r_prm, "generate", call
                )
                drafts.append(reduced_draft)
                planning.validate_draft_chain(frozen, drafts)
                executions.append(reduced_binding)
                new_win = {
                    "ordinal": reduced_draft["ordinal"],
                    "identity": codec.canonical_digest(reduced_draft),
                    "content": reduced_draft["content"],
                }
                active_windows = [
                    *active_windows[:group_start],
                    new_win,
                    *active_windows[group_end:],
                ]
                ready_final = _try_final_synthesis(active_windows)
                if (
                    ready_final is None
                    and group_end - group_start == 1
                    and len(active_windows) == 1
                    and _compact_bytes_len(new_win["content"]) >= prev_slice_bytes
                    and single_compact_attempts >= 2
                ):
                    shard_cap = max(8_000, min(MAX_STAGE3_SHARD_BYTES, prev_slice_bytes // 3))
                    shards = _shard_oversized_window(new_win, max_chunk_bytes=shard_cap)
                    if len(shards) > 1:
                        active_windows = shards

            if ready_final is not None:
                final_sealed, final_sch, final_prm, final_bytes = ready_final
            else:
                for mode in ("full", "slim", False):
                    final_sealed, final_sch, final_prm, final_bytes = make_synth_call(
                        active_windows, "final_synthesis", mode
                    )
                    if _fits_turn_budget(final_bytes, frozen):
                        break
            _assert_under_70k(final_bytes, frozen, f"final-synthesis-{len(drafts) + 1}")
            synth_draft, synth_binding = execute_call(
                final_sealed, final_sch, final_prm, "generate", call
            )
            drafts.append(synth_draft)
            planning.validate_draft_chain(frozen, drafts)
            executions.append(synth_binding)

        proposal = {
            "schema_version": candidate.SCHEMA,
            "input_stage": "3b",
            "input_identity": frozen["input_identity"],
            "provenance": {
                "kind": "model_draft",
                "declaration": "Complete original model draft chain; execution separately replayed",
                "upstream_model_history": "declared_model",
                "draft_chain": drafts,
                "final_draft_identity": codec.canonical_digest(drafts[-1]),
            },
            "content": deepcopy(drafts[-1]["content"]),
        }
        last_generation_calls_by_proposal[canonical_sha(proposal)] = list(executions)
        return {
            "candidate": proposal,
            "generation_calls": executions,
            "lineage": {
                "context": context,
                "identity": lineage_id,
                "slot": slot,
                "generation": generation_no,
                "execution": execution_no,
            },
        }

    def prepare_repair_origin(scope, accepted, prior, issue, context):
        del scope, accepted, context
        if prior is not None and issue is not None and issue.get("account_policy") is not None:
            repair_origin[0] = (
                prior,
                runtime.obligations(prior, frozen),
                runtime.semantic_domain(prior, frozen)[0],
                issue,
            )
        else:
            repair_origin[0] = None

    def semantic(scope, accepted, proposal, call, context):
        # Stage 5: Deterministic <=70k segmented independent admission review
        runtime.validate_input(root, workspace, state)
        live_ledger = load_json(workspace / "capability-append/append-ledger.json", {})
        live_pending = (live_ledger.get("current") or {}).get("pending_semantic")
        if isinstance(live_pending, dict) and "semantic_start_call" in live_pending:
            count[0] = int(live_pending["semantic_start_call"])
        slot = state["runtime_slot"]
        generation_no = state.get("capability_selection", {}).get("generation", 1)
        execution_no = state.get("runtime_execution", 1)
        lineage_id = runtime.lineage_identity(state, base, slot, context, generation_no, execution_no)
        prior_proj = (
            _compact_candidate_projection(repair_origin[0][0]) if repair_origin[0] is not None else None
        )
        prior_issue = repair_origin[0][3] if repair_origin[0] is not None else None
        planned = _plan_review_segments(
            state,
            frozen,
            base_seed=accepted,
            proposal=proposal,
            slot=slot,
            generation_no=generation_no,
            execution_no=execution_no,
            lineage_id=lineage_id,
            context=context,
            prior_projection=prior_proj,
            issue=prior_issue,
        )
        check_cost("review", max(len(planned) - 1, 0))
        directive = runtime.reopen_directive(state, frozen, generation_no)
        prop_sha = canonical_sha(proposal)

        all_checks: list[dict] = []
        reopen_reviews = None
        review_executions: list[dict] = []
        for seg_idx, (s_mat, s_sch, s_prm, s_obs, s_srcs) in enumerate(planned):
            raw_rev, rev_binding = execute_call(
                s_mat, s_sch, s_prm, "semantic", call, compact_schema_file=True
            )
            decoded_slice = decode_segmented_review_slice(
                state,
                frozen,
                raw_rev,
                s_obs,
                s_srcs,
                proposal_sha256=prop_sha,
                directive=directive if seg_idx == 0 else None,
            )
            all_checks.extend(decoded_slice["checks"])
            if "reopen_reviews" in decoded_slice:
                reopen_reviews = decoded_slice["reopen_reviews"]
            review_executions.append(rev_binding)

        full_obligations = runtime.obligations(proposal, frozen)
        if len(all_checks) != len(full_obligations) or [c["id"] for c in all_checks] != [
            ob["id"] for ob in full_obligations
        ]:
            raise ValueError("b_route_segmented_review_denominator_mismatch")

        reopen_blocked = [
            r["rationale"] for r in (reopen_reviews or []) if r["verdict"] == "blocked"
        ]
        blocked_findings = list(
            dict.fromkeys(
                [c["rationale"] for c in all_checks if c["verdict"] == "blocked"]
                + reopen_blocked
            )
        )
        aggregated_review = {
            "schema_version": runtime.REVIEW,
            "input_identity": runtime.descriptor(state)["input_identity"],
            "runtime_identity": state["runtime_identity"],
            "proposal_sha256": prop_sha,
            "verdict": "blocked" if blocked_findings else "approved",
            "findings": blocked_findings,
            "checks": all_checks,
        }
        if reopen_reviews is not None:
            aggregated_review["reopen_reviews"] = reopen_reviews

        issues = runtime.account_review_issues(
            state, proposal, frozen, aggregated_review, origin=repair_origin[0]
        )
        bound = {
            "review": aggregated_review,
            "obligations": full_obligations,
            "runtime_identity": state["runtime_identity"],
            "lineage_context": context,
            "segmented_review_policy": SEGMENTED_RUNTIME_POLICY,
            "review_executions": review_executions,
        }
        if directive is not None:
            bound["reopen_context"] = directive
        return {
            "issues": issues,
            "proof": bound,
            "execution": review_executions[0],
        }

    result = run_capability_append(
        workspace / "capability-append",
        scopes=all_scopes,
        seed=base,
        identity=state["runtime_identity"],
        propose=propose,
        machine=lambda scope, accepted, proposal: _segmented_append_machine(root, state, proposal),
        semantic=semantic,
        final_machine=lambda proposal: runtime.admission_machine(root, state, proposal),
        before_call=before_call,
        checkpoint=checkpoint,
        merge=runtime.merge,
        preserve=runtime.preservation,
        repair_check=lambda before, after, issue, **kwargs: _segmented_repair_scope_errors(
            root, state, before, after, issue, **kwargs
        ),
        machine_repair_check=lambda before, after: _segmented_machine_repair_errors(root, state, before, after),
        replacement=replacement,
        fail_execution_closed=True,
        repairability=(
            lambda before, issue: _segmented_append_repairability(
                before, frozen, issue, root=root, state=state
            )
        )
        if runtime.issue_account_policy(state) is not None
        else None,
        prepare_repair_origin=prepare_repair_origin,
    )
    if result["status"] == "admitted":
        proof = runtime.admission_proof(state, base, all_scopes, result["records"], result["accepted"])
        execution = runtime.aggregate_execution(
            state, result["accepted"], proof, result["total_invocations"]
        )
        atomic_json(workspace / "proposal.json", result["accepted"])
        atomic_json(workspace / "admission-review.json", proof)
        atomic_json(workspace / "admission-execution.json", execution)
        result["proof"] = proof
    return result


# ---------------------------------------------------------------------------
# Stage 6a: Compact / Segmented Anonymous Selection
# ---------------------------------------------------------------------------


def _selector_authority_denominator(frozen: dict) -> dict:
    """Authoritative source/requirement denominator without 359 KB 3A process logs."""
    inputs = frozen["inputs"]
    gp = inputs["global_proof"]
    ledger_blocks = gp.get("ledger", {}).get("blocks", [])
    proposals_rows = gp.get("proposals", {}).get("proposals", [])
    return {
        "input_identity": frozen["input_identity"],
        "contract_ref": inputs["contract_ref"],
        "scope": deepcopy(inputs["contract"].get("scope")),
        "closure": deepcopy(inputs["closure"]),
        "source_inventory": deepcopy(inputs["source_inventory"]),
        "global_proof_denominator": {
            "audit_ref": gp["audit_ref"],
            "manifest": deepcopy(gp["manifest"]),
            "report": deepcopy(gp["report"]),
            "unresolved": deepcopy(gp["unresolved"]),
            "source_block_ids": [
                row["block_id"]
                for row in ledger_blocks
                if isinstance(row, dict) and "block_id" in row
            ],
            "proposal_ids": [
                row["proposal_id"]
                for row in proposals_rows
                if isinstance(row, dict) and "proposal_id" in row
            ],
        },
        "constraint_digests": [
            {k: row[k] for k in ("path", "format", "raw_digest") if k in row}
            for row in inputs["constraints"]
        ],
        "context_digests": [
            {k: row[k] for k in ("kind", "path", "raw_digest") if k in row}
            for row in inputs["contexts"]
        ],
        "evidence_digests": [
            {k: row[k] for k in ("path", "sha256") if k in row}
            for row in inputs["evidence"]
        ],
        "dependency_file_count": len(inputs["dependencies"]["files"]),
    }


def _candidate_selector_projection(proposal: dict, *, level: int = 0) -> dict:
    del level
    return _compact_candidate_projection(proposal)


def _candidate_tournament_digest(proposal: dict, *, raw_digest: str, slim: bool = False) -> dict:
    base_proj = _compact_candidate_projection(proposal)
    content = base_proj["content"]
    defs = content.get("definitions", {})
    counts = {
        "requirements": len(content.get("requirements", [])),
        "flows": len(defs.get("flows", [])),
        "commands": len(defs.get("commands", [])),
        "states": len(defs.get("states", [])),
        "coverage_table": len(content.get("coverage_table", [])),
        "implementation_objects": len(content.get("implementation_objects", [])),
        "unresolved": len(content.get("unresolved", [])),
    }
    summary = {
        "schema_version": base_proj["schema_version"],
        "input_stage": base_proj["input_stage"],
        "input_identity": base_proj["input_identity"],
        "proposal_sha256": base_proj["proposal_sha256"],
        "raw_digest": raw_digest,
        "provenance_summary": base_proj["provenance_summary"],
        "counts": counts,
    }
    if not slim:
        summary["structural_ids"] = {
            "requirement_ids": [
                r.get("requirement_id") for r in content.get("requirements", [])[:64] if isinstance(r, dict)
            ],
            "flow_ids": [f.get("id") for f in defs.get("flows", [])[:64] if isinstance(f, dict)],
            "command_ids": [c.get("id") for c in defs.get("commands", [])[:64] if isinstance(c, dict)],
            "state_ids": [s.get("id") for s in defs.get("states", [])[:64] if isinstance(s, dict)],
            "implementation_object_ids": [
                o.get("id") for o in content.get("implementation_objects", [])[:64] if isinstance(o, dict)
            ],
        }
    return summary


def complete_segmented_context(frozen: dict, scope: dict, base: dict, proposal: dict | None = None) -> dict:
    """Build compact lossless authoritative comparison context without 359 KB 3A logs."""
    seed_proj = {
        "schema_version": base["schema_version"],
        "input_identity": base["input_identity"],
        "seed_sha256": canonical_sha(base),
        "formal_adoption": False,
    }
    prop_summary = (
        {
            "proposal_sha256": canonical_sha(proposal),
            "final_draft_identity": proposal["provenance"]["final_draft_identity"],
        }
        if proposal is not None
        else None
    )
    return {
        "segmented_selector_policy": SEGMENTED_SELECTOR_POLICY,
        "frozen_authority": _selector_authority_denominator(frozen),
        "scope": deepcopy(scope),
        "accepted_seed": seed_proj,
        "proposal_summary": prop_summary,
    }


def _segmented_selector_files(
    state: dict,
    frozen: dict,
    scope: dict,
    base: dict,
    proposals: dict,
    aliases: dict,
    *,
    level: int = 0,
    work=None,
) -> tuple[dict, dict[str, bytes], dict[str, dict]]:
    import _b_route_planning_runtime as runtime
    from _mvg_evidence_transport import MODEL_ENCODING

    runtime.check_selector_aliases(state, aliases)
    work = compact._work(work)
    comparison = {
        alias: complete_segmented_context(frozen, scope, base, proposals[label])
        for alias, label in aliases.items()
    }
    encoded_comparison = wire.factor_lossless_context(comparison, work=work)
    raw_comparison = (json.dumps(encoded_comparison, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    restored = wire.restore_lossless_context(codec.strict_json_loads(raw_comparison), work=work)
    if wire.text(restored, work=work) != wire.text(comparison, work=work):
        raise ValueError("b_route_segmented_selector_comparison_reconstruction_changed")

    raw_files: dict[str, bytes] = {"comparison-context.json": raw_comparison}
    files: dict[str, dict] = {
        "comparison-context.json": {
            "raw_digest": codec.raw_digest(raw_comparison),
            "decoded_from": MODEL_ENCODING,
            "value": restored,
        }
    }
    raw_seed = (json.dumps(base, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    raw_files["accepted-seed.json"] = raw_seed
    files["accepted-seed.json"] = {
        "raw_digest": codec.raw_digest(raw_seed),
        "value": {
            "schema_version": base["schema_version"],
            "input_identity": base["input_identity"],
            "seed_sha256": canonical_sha(base),
            "formal_adoption": False,
        },
    }
    for alias, label in aliases.items():
        raw_prop = (json.dumps(proposals[label], ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        raw_files[alias + ".json"] = raw_prop
        files[alias + ".json"] = {
            "raw_digest": codec.raw_digest(raw_prop),
            "value": _candidate_selector_projection(proposals[label], level=level),
        }
    return encoded_comparison, raw_files, files


PAIRWISE_TOURNAMENT_SCHEMA = "newrouge.b-route-3b-pairwise-tournament.v1"
SELECTOR_FULL_SIDECAR_NAME = "segmented-selector-materials.json"
PAIRWISE_TOURNAMENT_MANIFEST_NAME = "pairwise-tournament-manifest.json"


def _slim_comparison_denominator(frozen: dict, *, ultra_slim: bool = False) -> dict:
    denom = _selector_authority_denominator(frozen)
    if not ultra_slim:
        return denom
    gp = denom["global_proof_denominator"]
    return {
        "input_identity": denom["input_identity"],
        "contract_ref": denom["contract_ref"],
        "scope": denom["scope"],
        "source_inventory_count": len(denom["source_inventory"]),
        "global_proof_denominator": {
            "audit_ref": gp["audit_ref"],
            "source_block_count": len(gp["source_block_ids"]),
            "proposal_count": len(gp["proposal_ids"]),
        },
        "dependency_file_count": denom["dependency_file_count"],
    }


def _segmented_selector_full_and_effective(
    state: dict,
    frozen: dict,
    scope: dict,
    public: dict,
    base: dict,
    proposals: dict,
    aliases: dict,
    workspace: Path,
    *,
    work=None,
    persist_sidecar: bool = True,
) -> tuple[dict, dict]:
    import _b_route_planning_runtime as runtime

    disk_comp = sources.checked_path(workspace, "comparison-context.json").read_bytes()
    disk_seed = sources.checked_path(workspace, "accepted-seed.json").read_bytes()
    if canonical_sha(codec.strict_json_loads(disk_seed)) != canonical_sha(base):
        raise ValueError("b_route_segmented_selector_seed_artifact_changed")
    disk_props: dict[str, bytes] = {}
    for alias, label in aliases.items():
        disk_path = sources.checked_path(workspace, alias + ".json")
        raw_bytes = disk_path.read_bytes()
        if canonical_sha(codec.strict_json_loads(raw_bytes)) != canonical_sha(proposals[label]):
            raise ValueError("b_route_segmented_selector_candidate_artifact_changed:" + alias)
        disk_props[alias] = raw_bytes

    schema = runtime.selection_schema(state)
    disk_comp_sha = canonical_sha(codec.strict_json_loads(disk_comp))
    encoded_comparison, _, files = _segmented_selector_files(
        state, frozen, scope, base, proposals, aliases, level=0, work=work
    )
    if disk_comp_sha != canonical_sha(encoded_comparison):
        raise ValueError("b_route_segmented_selector_comparison_artifact_changed")
    files["comparison-context.json"]["raw_digest"] = codec.raw_digest(disk_comp)
    files["accepted-seed.json"]["raw_digest"] = codec.raw_digest(disk_seed)
    for alias, raw_bytes in disk_props.items():
        files[alias + ".json"]["raw_digest"] = codec.raw_digest(raw_bytes)
    full_materials = {
        "wire_delivery": runtime.wire_delivery(state) or wire.CURRENT_SCHEMA,
        "phase": "selection",
        "segmented_selector_policy": SEGMENTED_SELECTOR_POLICY,
        "input_compact_policy": compact.ATOM_SCHEMA,
        "runtime_identity": state["runtime_identity"],
        "run_id": state["run_id"],
        "scope": deepcopy(scope),
        "identity": deepcopy(public),
        "files": files,
    }
    full_materials["materials_identity"] = canonical_sha(full_materials)
    full_prompt = segmented_selector_prompt(full_materials, work=work)
    full_ws_text = seg_input._runner_wrapper_text(full_prompt, schema, compact_schema_file=False)
    full_ws_bytes = max(
        len(full_ws_text.encode("utf-8")),
        int(runtime.measure_actual(frozen, full_ws_text, schema)["request_bytes"]),
    )
    if _fits_turn_budget(full_ws_bytes, frozen):
        return full_materials, full_materials

    sidecar_path = workspace / SELECTOR_FULL_SIDECAR_NAME
    full_sha = canonical_sha(full_materials)
    if persist_sidecar:
        atomic_json(sidecar_path, full_materials)
    else:
        if not sidecar_path.is_file():
            raise ValueError("b_route_segmented_selector_sidecar_missing")
        if canonical_sha(load_json(sidecar_path)) != full_sha:
            raise ValueError("b_route_segmented_selector_sidecar_changed")

    chosen_index = None
    last_bytes = 0
    for slim_flag, ultra_denom in ((False, False), (True, False), (True, True)):
        cand_index = {
            "wire_delivery": runtime.wire_delivery(state) or wire.CURRENT_SCHEMA,
            "phase": "selection",
            "tournament_mode": True,
            "segmented_selector_policy": SEGMENTED_SELECTOR_POLICY,
            "input_compact_policy": compact.ATOM_SCHEMA,
            "runtime_identity": state["runtime_identity"],
            "run_id": state["run_id"],
            "scope": deepcopy(scope),
            "identity": deepcopy(public),
            "full_materials_sha256": full_sha,
            "comparison_denominator": _slim_comparison_denominator(frozen, ultra_slim=ultra_denom),
            "accepted_seed": deepcopy(files["accepted-seed.json"]),
            "candidate_summaries": {
                alias: _candidate_tournament_digest(
                    proposals[label],
                    raw_digest=codec.raw_digest(disk_props[alias]),
                    slim=slim_flag,
                )
                for alias, label in aliases.items()
            },
        }
        cand_index["materials_identity"] = canonical_sha(cand_index)
        idx_prompt = segmented_selector_prompt(cand_index, work=work)
        idx_ws_text = seg_input._runner_wrapper_text(idx_prompt, schema, compact_schema_file=False)
        idx_ws_bytes = max(
            len(idx_ws_text.encode("utf-8")),
            int(runtime.measure_actual(frozen, idx_ws_text, schema)["request_bytes"]),
        )
        last_bytes = idx_ws_bytes
        if _fits_turn_budget(idx_ws_bytes, frozen):
            chosen_index = cand_index
            break
    if chosen_index is None:
        _assert_under_70k(last_bytes, frozen, "segmented_selector_tournament_index")
    return chosen_index, full_materials


def segmented_selector_materials(
    state: dict,
    frozen: dict,
    scope: dict,
    public: dict,
    base: dict,
    proposals: dict,
    aliases: dict,
    workspace: Path,
    *,
    work=None,
    persist_sidecar: bool = True,
) -> dict:
    import _b_route_planning_runtime as runtime

    disk_comp = sources.checked_path(workspace, "comparison-context.json").read_bytes()
    disk_seed = sources.checked_path(workspace, "accepted-seed.json").read_bytes()
    disk_props = {
        alias: sources.checked_path(workspace, alias + ".json").read_bytes() for alias in aliases
    }
    mat_cache_key = None
    if work is None and not persist_sidecar:
        sidecar_path = workspace / SELECTOR_FULL_SIDECAR_NAME
        mat_cache_key = (
            state.get("runtime_identity"),
            state.get("run_id"),
            runtime.wire_delivery(state),
            frozen.get("input_identity"),
            canonical_sha(scope),
            canonical_sha(public),
            codec.raw_digest(disk_comp),
            codec.raw_digest(disk_seed),
            tuple((k, codec.raw_digest(v)) for k, v in sorted(disk_props.items())),
            file_sha(sidecar_path) if sidecar_path.is_file() else None,
        )
        cached_mat = _SELECTOR_MATERIALS_CACHE.get(mat_cache_key)
        if cached_mat is not None:
            return deepcopy(cached_mat)

    effective, _ = _segmented_selector_full_and_effective(
        state,
        frozen,
        scope,
        public,
        base,
        proposals,
        aliases,
        workspace,
        work=work,
        persist_sidecar=persist_sidecar,
    )
    if mat_cache_key is not None:
        _bounded_put(_SELECTOR_MATERIALS_CACHE, mat_cache_key, deepcopy(effective), 16)
    return effective


_SELECTOR_MATERIALS_CACHE: dict[tuple, dict] = {}
_SELECTOR_PROMPT_CACHE: dict[str, str] = {}


def segmented_selector_prompt(materials: dict, *, work=None) -> str:
    prompt_key = canonical_sha(materials) if work is None else None
    if prompt_key is not None:
        cached = _SELECTOR_PROMPT_CACHE.get(prompt_key)
        if cached is not None:
            return cached
    aliases = list(materials["identity"]["candidates"])
    if materials.get("tournament_synthesis"):
        bracket_winner = materials["pairwise_verdicts"]["bracket_winner"]
        instruction = (
            "Synthesize the final admitted candidate selection across "
            + ", ".join(aliases)
            + " from verified pairwise tournament verdicts in pairwise_verdicts, candidate_summaries, and "
            "comparison_denominator (bound to full_materials_sha256). accepted_seed is read-only context and is "
            "never a candidate or fallback. All candidates passed machine and independent semantic admission; "
            "return only viable reviews, no additional hard veto. You MUST select pairwise_verdicts.bracket_winner ("
            + str(bracket_winner)
            + ") at rank 1 (selected == bracket_winner) and assign unique consecutive ranks 1.."
            + str(len(aliases))
            + " with grounded rationales. No tools."
        )
    elif materials.get("tournament_mode"):
        instruction = (
            "Tournament index for admitted increments "
            + ", ".join(aliases)
            + " bound to segmented-selector-materials.json via full_materials_sha256 and comparison_denominator. "
            "accepted_seed is read-only context and is never a candidate or fallback. Return strict selection JSON "
            "with unique consecutive ranks; the winner ranks 1. No tools."
        )
    else:
        instruction = (
            "Compare only the admitted increments in "
            + ", ".join(alias + ".json" for alias in aliases)
            + ". accepted-seed.json is read-only context and is never a candidate or fallback. "
            "All candidates share the same frozen input and base. Do not demand future Capability coverage. "
            "Rank source fidelity, journey coherence, affected handoffs, verification feasibility and cumulative impact. "
            "Select one candidate without mixing. Read comparison-context.json for complete authoritative source, "
            "ledger, proposals, accounting, constraints and contexts. All candidates passed machine and independent "
            "semantic admission; return only viable reviews, no additional hard veto. Blind order/labels convey no "
            "quality. Return strict selection JSON with unique consecutive ranks; the winner ranks 1. No tools."
        )
    rendered = wire.render(
        instruction,
        materials,
        materials.get("wire_delivery", wire.CURRENT_SCHEMA),
        compact_schema=compact.ATOM_SCHEMA,
        work=work,
    )
    if prompt_key is not None:
        _bounded_put(_SELECTOR_PROMPT_CACHE, prompt_key, rendered, 16)
    return rendered


_CHECKED_SELECTOR_MATERIALS_CACHE: dict[tuple, dict] = {}


def _reconstruct_selector_expected_and_full(
    root: Path,
    run_dir: Path,
    state: dict,
    index: int,
    workspace: Path,
    *,
    check_originals: bool = True,
) -> tuple[dict, dict, dict[str, dict]]:
    import _b_route_planning_runtime as runtime
    from _mvg_capability_selection import candidate_artifacts, selection_identity

    frozen = runtime.frozen_input(root, state, check_originals=check_originals)
    units = runtime.scopes(state, run_dir / "analysis-input")
    if type(index) is not int or not (0 <= index < len(units)):
        raise ValueError("b_route_selector_scope_index_invalid")
    ledger = state["capability_selection"]
    selected = ledger.get("selected", [])
    current = ledger.get("current")
    step = current if current is not None and current["order_index"] == index else selected[index]
    aliases = step["aliases"]
    runtime.check_selector_aliases(state, aliases)

    base, prefix = runtime.seed(state, run_dir / "analysis-input"), []
    for prior_index, prior in enumerate(selected[:index]):
        proposal, proof, _ = candidate_artifacts(
            root,
            run_dir,
            state,
            units,
            prior_index,
            base,
            prefix,
            prior["admissions"][prior["selected_candidate"]],
            check_originals=check_originals,
        )
        base = proposal
        prefix.append(proof["records"][-1])
    proposals: dict[str, dict] = {}
    proofs: dict[str, dict] = {}
    for label in runtime.labels(state):
        prop_val, proof_val, _ = candidate_artifacts(
            root,
            run_dir,
            state,
            units,
            index,
            base,
            prefix,
            step["admissions"][label],
            check_originals=check_originals,
        )
        proposals[label] = prop_val
        proofs[label] = proof_val
    identity = selection_identity(state, units[index], index, base, step["admissions"], aliases)
    public = {key: value for key, value in identity.items() if key != "candidates"}
    public["candidates"] = {
        alias: {key: value for key, value in row.items() if key != "lineage"}
        for alias, row in identity["candidates"].items()
    }
    expected_effective, full_materials = _segmented_selector_full_and_effective(
        state,
        frozen,
        units[index],
        public,
        base,
        proposals,
        aliases,
        workspace,
        persist_sidecar=False,
    )
    return expected_effective, full_materials, proofs


def _build_tournament_synthesis_materials(index_materials: dict, pairwise_verdicts: dict) -> dict:
    synth = {
        k: deepcopy(v)
        for k, v in index_materials.items()
        if k != "materials_identity"
    }
    synth["tournament_mode"] = True
    synth["tournament_synthesis"] = True
    synth["pairwise_verdicts"] = deepcopy(pairwise_verdicts)
    synth["materials_identity"] = canonical_sha(synth)
    return synth


def check_segmented_selector_materials(
    root: Path,
    run_dir: Path,
    state: dict,
    materials: dict,
    workspace: Path,
    *,
    check_originals: bool = True,
) -> dict:
    import _b_route_planning_runtime as runtime

    frozen = runtime.frozen_input(root, state, check_originals=check_originals)
    units = runtime.scopes(state, run_dir / "analysis-input")
    index = materials["identity"]["order_index"]
    if type(index) is not int or not (0 <= index < len(units)):
        raise ValueError("b_route_selector_scope_index_invalid")
    if (
        materials.get("segmented_selector_policy") != SEGMENTED_SELECTOR_POLICY
        or materials.get("input_compact_policy") != compact.ATOM_SCHEMA
    ):
        raise ValueError("b_route_segmented_selector_policy_invalid")
    ledger = state["capability_selection"]
    selected = ledger.get("selected", [])
    current = ledger.get("current")
    step = current if current is not None and current["order_index"] == index else selected[index]
    aliases = step["aliases"]
    runtime.check_selector_aliases(state, aliases)

    sel_cache_key = None
    if index == 0:
        try:
            dep_files = [
                run_dir / "analysis-input/b-route-prepared.json",
                workspace / "accepted-seed.json",
            ]
            for alias in aliases:
                dep_files.append(workspace / f"{alias}.json")
            sidecar_file = workspace / SELECTOR_FULL_SIDECAR_NAME
            if sidecar_file.is_file():
                dep_files.append(sidecar_file)
            for label in runtime.labels(state):
                adm = step["admissions"][label]
                for k in ("proposal_path", "proof_path", "execution_path"):
                    dep_files.append(sources.checked_path(run_dir, adm[k]))
                dep_files.append(
                    sources.checked_path(run_dir, adm["workspace"]) / "capability-append/append-ledger.json"
                )
            if all(p.is_file() for p in dep_files):
                ledger_step_sig = canonical_sha(
                    {
                        "binding": ledger.get("binding"),
                        "order": ledger.get("order"),
                        "index": step.get("order_index"),
                        "aliases": step.get("aliases"),
                        "admissions": step.get("admissions"),
                    }
                )
                sel_cache_key = (
                    str(root.resolve()),
                    str(run_dir.resolve()),
                    str(workspace.resolve()),
                    state.get("runtime_identity"),
                    state.get("run_id"),
                    ledger_step_sig,
                    canonical_sha(state.get("reopen_contexts") or []),
                    frozen["input_identity"],
                    check_originals,
                    wire.text(materials),
                    tuple((str(p), file_sha(p)) for p in dep_files),
                )
                cached_expected = _CHECKED_SELECTOR_MATERIALS_CACHE.get(sel_cache_key)
                if cached_expected is not None:
                    return deepcopy(cached_expected)
        except Exception:
            sel_cache_key = None

    expected, _, _ = _reconstruct_selector_expected_and_full(
        root, run_dir, state, index, workspace, check_originals=check_originals
    )
    if materials.get("tournament_synthesis"):
        if not expected.get("tournament_mode") or not isinstance(materials.get("pairwise_verdicts"), dict):
            raise ValueError("b_route_segmented_selector_tournament_unactivated")
        expected_target = _build_tournament_synthesis_materials(expected, materials["pairwise_verdicts"])
    else:
        expected_target = expected
    if wire.text(materials) != wire.text(expected_target):
        raise ValueError("b_route_segmented_selector_materials_changed")
    if sel_cache_key is not None:
        _bounded_put(_CHECKED_SELECTOR_MATERIALS_CACHE, sel_cache_key, deepcopy(expected_target), 16)
    return expected_target


def _pairwise_selection_schema(pair: list[str]) -> dict:
    row = {
        "type": "object",
        "properties": {
            "candidate": {"type": "string", "enum": list(pair)},
            "rank": {"type": "integer", "minimum": 1, "maximum": 2},
            "verdict": {"type": "string", "const": "viable"},
            "rationale": {"type": "string", "minLength": 1},
        },
        "required": ["candidate", "rank", "verdict", "rationale"],
        "additionalProperties": False,
    }
    fields = {
        "status": {"type": "string", "const": "selected"},
        "selected": {"type": "string", "enum": list(pair)},
        "candidate_reviews": {"type": "array", "items": row, "minItems": 2, "maxItems": 2},
    }
    return {"type": "object", "properties": fields, "required": list(fields), "additionalProperties": False}


def _pairwise_selection_errors(pair: list[str], selection: dict) -> list[str]:
    import jsonschema

    if not isinstance(selection, dict):
        return ["b_route_pairwise_selection_not_object"]
    errors = list(jsonschema.Draft202012Validator(_pairwise_selection_schema(pair)).iter_errors(selection))
    rows = selection.get("candidate_reviews", [])
    if (
        errors
        or {row.get("candidate") for row in rows if isinstance(row, dict)} != set(pair)
        or {row.get("rank") for row in rows if isinstance(row, dict)} != {1, 2}
        or any(
            row["rank"] != 1
            for row in rows
            if isinstance(row, dict) and row.get("candidate") == selection.get("selected")
        )
    ):
        return ["b_route_pairwise_selection_invalid"]
    return []


def _pairwise_diff_projection(
    left: str,
    left_entry: dict,
    right: str,
    right_entry: dict,
    *,
    max_changed_bytes: int,
) -> dict:
    left_val = left_entry["value"]
    right_val = right_entry["value"]
    left_content = left_val["content"]
    right_content = right_val["content"]
    left_defs = left_content.get("definitions", {})
    right_defs = right_content.get("definitions", {})

    sections = (
        ("flows", left_defs.get("flows", []), right_defs.get("flows", []), "id"),
        ("requirements", left_content.get("requirements", []), right_content.get("requirements", []), "requirement_id"),
        ("commands", left_defs.get("commands", []), right_defs.get("commands", []), "id"),
        ("states", left_defs.get("states", []), right_defs.get("states", []), "id"),
        (
            "coverage_table",
            left_content.get("coverage_table", []),
            right_content.get("coverage_table", []),
            "requirement_id",
        ),
        (
            "implementation_objects",
            left_content.get("implementation_objects", []),
            right_content.get("implementation_objects", []),
            "id",
        ),
    )

    shared_identical_counts: dict[str, int] = {}
    changed_left: dict[str, list] = {}
    changed_right: dict[str, list] = {}
    overflow_changed_digests: dict[str, list[dict]] = {}
    used_bytes = 0

    for sec_name, l_rows, r_rows, key_field in sections:
        l_map = {
            str(r.get(key_field, f"idx_{i}")): r
            for i, r in enumerate(l_rows)
            if isinstance(r, dict)
        }
        r_map = {
            str(r.get(key_field, f"idx_{i}")): r
            for i, r in enumerate(r_rows)
            if isinstance(r, dict)
        }
        all_ids = sorted(set(l_map) | set(r_map))
        identical_count = 0
        for item_id in all_ids:
            lv = l_map.get(item_id)
            rv = r_map.get(item_id)
            l_sha = canonical_sha(lv) if lv is not None else None
            r_sha = canonical_sha(rv) if rv is not None else None
            if l_sha == r_sha:
                identical_count += 1
                continue
            entry_pair = {"id": item_id, left: lv, right: rv}
            item_bytes = _compact_bytes_len(entry_pair)
            if used_bytes + item_bytes <= max_changed_bytes:
                if lv is not None:
                    changed_left.setdefault(sec_name, []).append(deepcopy(lv))
                if rv is not None:
                    changed_right.setdefault(sec_name, []).append(deepcopy(rv))
                used_bytes += item_bytes
            else:
                overflow_changed_digests.setdefault(sec_name, []).append(
                    {"id": item_id, left + "_sha256": l_sha, right + "_sha256": r_sha}
                )
        shared_identical_counts[sec_name] = identical_count

    return {
        "projection_mode": "lossless_summary_plus_changed_definitions",
        "candidates": {
            left: {
                "raw_digest": left_entry["raw_digest"],
                "proposal_sha256": left_val["proposal_sha256"],
                "provenance_summary": deepcopy(left_val["provenance_summary"]),
                "changed_sections": changed_left,
                "unresolved": deepcopy(left_content.get("unresolved", [])[:16]),
            },
            right: {
                "raw_digest": right_entry["raw_digest"],
                "proposal_sha256": right_val["proposal_sha256"],
                "provenance_summary": deepcopy(right_val["provenance_summary"]),
                "changed_sections": changed_right,
                "unresolved": deepcopy(right_content.get("unresolved", [])[:16]),
            },
        },
        "shared_identical_counts": shared_identical_counts,
        "overflow_changed_digests": overflow_changed_digests,
    }


def _render_pair_prompt(pair_mat: dict, *, work=None) -> str:
    left, right = pair_mat["identity"]["pair"]
    instruction = (
        f"Compare only admitted candidates {left} and {right} against comparison_denominator "
        "(bound to full_materials_sha256). accepted-seed.json is read-only context and never a candidate. "
        "All candidates passed machine and independent semantic admission; return only viable reviews, "
        "no additional hard veto. Blind labels convey no quality. Return strict pairwise selection JSON "
        "with unique consecutive ranks 1..2; the winner ranks 1. No tools."
    )
    return wire.render(
        instruction,
        pair_mat,
        pair_mat["wire_delivery"],
        compact_schema=compact.ATOM_SCHEMA,
        work=work,
    )


def _build_pair_materials_and_prompt(
    state: dict,
    frozen: dict,
    index_materials: dict,
    full_materials: dict,
    pair_no: int,
    left: str,
    right: str,
    *,
    work=None,
) -> tuple[dict, str, dict]:
    import _b_route_planning_runtime as runtime

    pair = [left, right]
    pair_schema = _pairwise_selection_schema(pair)
    full_pair_files = {
        "accepted-seed.json": deepcopy(full_materials["files"]["accepted-seed.json"]),
        left + ".json": deepcopy(full_materials["files"][left + ".json"]),
        right + ".json": deepcopy(full_materials["files"][right + ".json"]),
    }

    def measure_candidate_pair(files_obj: dict, denom_obj: dict) -> tuple[dict, str, int]:
        mat = {
            "wire_delivery": index_materials["wire_delivery"],
            "phase": "selection_pair",
            "segmented_selector_policy": SEGMENTED_SELECTOR_POLICY,
            "input_compact_policy": compact.ATOM_SCHEMA,
            "runtime_identity": state["runtime_identity"],
            "run_id": state["run_id"],
            "scope": deepcopy(index_materials["scope"]),
            "identity": {
                **deepcopy(index_materials["identity"]),
                "pair": pair,
                "pair_index": pair_no,
            },
            "full_materials_sha256": index_materials["full_materials_sha256"],
            "comparison_denominator": deepcopy(denom_obj),
            "files": files_obj,
        }
        mat["materials_identity"] = canonical_sha(mat)
        prm = _render_pair_prompt(mat, work=work)
        ws_text = seg_input._runner_wrapper_text(prm, pair_schema, compact_schema_file=False)
        eff = max(
            len(ws_text.encode("utf-8")),
            int(runtime.measure_actual(frozen, ws_text, pair_schema)["request_bytes"]),
        )
        return mat, prm, eff

    p_mat, p_prm, p_eff = measure_candidate_pair(
        full_pair_files, index_materials["comparison_denominator"]
    )
    if _fits_turn_budget(p_eff, frozen):
        return p_mat, p_prm, pair_schema

    for ultra_denom, budget_cap in ((False, 36_000), (True, 28_000), (True, 16_000), (True, 6_000)):
        denom = _slim_comparison_denominator(frozen, ultra_slim=ultra_denom)
        diff_proj = _pairwise_diff_projection(
            left,
            full_materials["files"][left + ".json"],
            right,
            full_materials["files"][right + ".json"],
            max_changed_bytes=budget_cap,
        )
        compact_files = {
            "accepted-seed.json": deepcopy(full_materials["files"]["accepted-seed.json"]),
            "pair-diff.json": diff_proj,
            "candidate-summaries.json": {
                left: deepcopy(index_materials["candidate_summaries"][left]),
                right: deepcopy(index_materials["candidate_summaries"][right]),
            },
        }
        p_mat, p_prm, p_eff = measure_candidate_pair(compact_files, denom)
        if _fits_turn_budget(p_eff, frozen):
            return p_mat, p_prm, pair_schema

    _assert_under_70k(p_eff, frozen, f"selector-pair-{pair_no}")
    return p_mat, p_prm, pair_schema


def make_segmented_selector_factory(
    root: Path, run_dir: Path, state: dict, config: dict, *, should_pause=None
):
    """Return selector_factory dispatching single <=70k call or 3-turn pairwise + synthesis tournament."""
    import _b_route_planning_runtime as runtime
    from _mvg_capability_append import RunBudgetExhausted, SlicePauseRequested
    from _mvg_capability_worker import runner_invoke

    frozen = runtime.frozen_input(root, state)

    def selector_factory(workspace: Path, *, outcome):
        class HostMailbox:
            reservation = None

            def request(self, kind, **kwargs):
                if kind != "outcome":
                    raise ValueError("b_route_coordinator_mailbox_kind_invalid")
                return outcome(kwargs["reservation_id"], kwargs["outcome"])

        def invoke(
            prompt: str,
            attempt: int,
            *,
            output_name: str,
            output_schema_path: Path,
            output_schema: dict,
            before_dispatch,
        ):
            effective_pause = should_pause if should_pause is not None else _ACTIVE_SHOULD_PAUSE.get()
            index_materials = wire.read_prompt(prompt, runtime.wire_delivery(state))
            if not index_materials.get("tournament_mode"):
                ws_text = seg_input._runner_wrapper_text(prompt, output_schema, compact_schema_file=False)
                eff_bytes = max(
                    len(ws_text.encode("utf-8")),
                    int(runtime.measure_actual(frozen, ws_text, output_schema)["request_bytes"]),
                )
                _assert_under_70k(eff_bytes, frozen, "selector-single-turn")
                if effective_pause is not None and effective_pause():
                    raise SlicePauseRequested("b_route_slice_pause_requested")
                return runner_invoke(root, run_dir, state, workspace, config, HostMailbox())(
                    prompt,
                    attempt,
                    output_name=output_name,
                    output_schema_path=output_schema_path,
                    output_schema=output_schema,
                    before_dispatch=before_dispatch,
                )

            # 3-turn Pairwise + Final Synthesis Tournament when 3-candidate materials exceed 70k / 96k
            aliases = list(index_materials["identity"]["candidates"].keys())
            ledger = state["capability_selection"]
            limit = state.get("mvg.run_invocation_limit", 192)

            sidecar_path = workspace / SELECTOR_FULL_SIDECAR_NAME
            if not sidecar_path.is_file():
                raise ValueError("b_route_segmented_selector_sidecar_missing")
            full_materials = load_json(sidecar_path)
            if canonical_sha(full_materials) != index_materials.get("full_materials_sha256"):
                raise ValueError("b_route_segmented_selector_sidecar_changed")

            attempts_list = ledger["current"]["selection_attempts"]
            target_attempt_len = (
                len(attempts_list)
                if any(row.get("attempt") == attempt for row in attempts_list)
                else (len(attempts_list) + 1)
            )
            reservation_ids: list[str] = []
            bindings_list: list[dict] = []

            def before_dispatch_dedup(request_identity=None):
                res = before_dispatch(request_identity=request_identity)
                while len(attempts_list) > target_attempt_len:
                    attempts_list.pop()
                atomic_json(run_dir / "run.json", state)
                reservation_ids.append(res["reservation_id"])
                return res

            def _replay_selector_call(
                expected_binding_path: Path, expected_prompt: str, expected_schema: dict
            ) -> tuple[dict, dict] | None:
                rel_binding = expected_binding_path.relative_to(run_dir).as_posix()
                matches = [
                    row
                    for row in ledger.get("calls", [])
                    if (row.get("request_identity") or {}).get("execution_binding_path") == rel_binding
                    and row.get("phase") == "selection"
                ]
                if not matches:
                    return None
                if len(matches) != 1:
                    raise ValueError("b_route_segmented_selector_duplicate_reservation")
                coord_row = matches[0]
                binding = verify_segmented_reserved_call(
                    run_dir, coord_row, state=state, check_originals=False
                )
                if binding is None or (coord_row.get("outcome") or {}).get("status") != "completed":
                    raise ValueError("b_route_segmented_selector_reserved_call_failed")
                req_id = coord_row.get("request_identity") or {}
                expected_ws_text = seg_input._runner_wrapper_text(
                    expected_prompt, expected_schema, compact_schema_file=False
                )
                if (
                    req_id.get("actual_request_sha256") != codec.raw_digest(expected_ws_text.encode("utf-8"))
                    or req_id.get("selection_input_sha256") != ledger["current"].get("input_sha256")
                    or not runtime.same_json(
                        codec.strict_json_loads(Path(binding["schema_path"]).read_bytes()),
                        expected_schema,
                    )
                ):
                    raise ValueError("b_route_segmented_selector_replay_changed")
                return coord_row, binding

            def run_pair(pair_no: int, left: str, right: str, *, remaining_turns: int) -> dict:
                pair = [left, right]
                _, pair_prompt, pair_schema = _build_pair_materials_and_prompt(
                    state, frozen, index_materials, full_materials, pair_no, left, right
                )
                pair_dir = workspace / f"p{pair_no}"
                replayed = _replay_selector_call(
                    pair_dir / f"execution-binding-{attempt}-o.json",
                    pair_prompt,
                    pair_schema,
                )
                if replayed is not None:
                    coord_row, binding = replayed
                    parsed = codec.strict_json_loads(Path(binding["output_path"]).read_bytes())
                    errs = _pairwise_selection_errors(pair, parsed)
                    if errs:
                        raise ValueError("b_route_pairwise_selection_output_invalid:" + ";".join(errs))
                    reservation_ids.append(coord_row["reservation_id"])
                    bindings_list.append(binding)
                    return parsed
                if limit - ledger["total_invocations"] < remaining_turns:
                    raise RunBudgetExhausted("run_blocked_budget_exhausted")
                if effective_pause is not None and effective_pause():
                    raise SlicePauseRequested("b_route_slice_pause_requested")
                out_path, exec_res = runner_invoke(root, run_dir, state, pair_dir, config, HostMailbox())(
                    pair_prompt,
                    attempt,
                    output_name="o.json",
                    output_schema_path=pair_dir / "output-schema.json",
                    output_schema=pair_schema,
                    before_dispatch=before_dispatch_dedup,
                )
                parsed = codec.strict_json_loads(out_path.read_bytes())
                errs = _pairwise_selection_errors(pair, parsed)
                if errs:
                    raise ValueError("b_route_pairwise_selection_output_invalid:" + ";".join(errs))
                bindings_list.append(exec_res["execution_binding"])
                return parsed

            total_turns = len(aliases)
            p1_parsed = run_pair(1, aliases[0], aliases[1], remaining_turns=total_turns)
            champ = p1_parsed["selected"]
            pairwise_verdicts: dict = {
                "pair_1": {"pair": [aliases[0], aliases[1]], "result": p1_parsed},
            }
            for idx, challenger in enumerate(aliases[2:], 2):
                pn_parsed = run_pair(
                    idx, champ, challenger, remaining_turns=total_turns - (idx - 1)
                )
                pairwise_verdicts[f"pair_{idx}"] = {"pair": [champ, challenger], "result": pn_parsed}
                champ = pn_parsed["selected"]
            pairwise_verdicts["bracket_winner"] = champ

            synth_materials = _build_tournament_synthesis_materials(index_materials, pairwise_verdicts)
            turn3_prompt = segmented_selector_prompt(synth_materials)
            turn3_ws_text = seg_input._runner_wrapper_text(
                turn3_prompt, output_schema, compact_schema_file=False
            )
            turn3_eff = max(
                len(turn3_ws_text.encode("utf-8")),
                int(runtime.measure_actual(frozen, turn3_ws_text, output_schema)["request_bytes"]),
            )
            _assert_under_70k(turn3_eff, frozen, "selector-turn3-synthesis")

            if limit - ledger["total_invocations"] < 1:
                raise RunBudgetExhausted("run_blocked_budget_exhausted")
            if effective_pause is not None and effective_pause():
                raise SlicePauseRequested("b_route_slice_pause_requested")

            turn3_out_path, turn3_exec = runner_invoke(
                root, run_dir, state, workspace, config, HostMailbox()
            )(
                turn3_prompt,
                attempt,
                output_name=output_name,
                output_schema_path=output_schema_path,
                output_schema=output_schema,
                before_dispatch=before_dispatch_dedup,
            )
            turn3_parsed = codec.strict_json_loads(turn3_out_path.read_bytes())
            sel_errs = runtime.selection_errors(state, turn3_parsed)
            if sel_errs:
                raise ValueError("b_route_tournament_synthesis_output_invalid:" + ";".join(sel_errs))
            if turn3_parsed.get("selected") != champ:
                raise ValueError("b_route_tournament_synthesis_bracket_mismatch")
            bindings_list.append(turn3_exec["execution_binding"])

            manifest = {
                "schema_version": PAIRWISE_TOURNAMENT_SCHEMA,
                "segmented_selector_policy": SEGMENTED_SELECTOR_POLICY,
                "attempt": attempt,
                "full_materials_sha256": index_materials["full_materials_sha256"],
                "reservation_ids": reservation_ids,
                "bindings": bindings_list,
                "pairwise_verdicts": pairwise_verdicts,
                "bracket_winner": champ,
                "final_selected": turn3_parsed["selected"],
            }
            atomic_json(workspace / PAIRWISE_TOURNAMENT_MANIFEST_NAME, manifest)
            return turn3_out_path, turn3_exec

        return invoke

    return selector_factory



# ---------------------------------------------------------------------------
# Coordinator Dispatch Preflight & Proof Replay Verifiers
# ---------------------------------------------------------------------------


_VERIFIED_MATERIALS_CACHE: dict[tuple, dict] = {}
_VERIFIED_CALL_CACHE: dict[tuple, dict] = {}
_DISK_JSON_SHA_CACHE: dict[tuple[str, str], tuple[dict, str]] = {}
_WIRE_PROMPT_CACHE: dict[tuple[str, str], dict] = {}
_PROOF_ERRORS_CACHE: dict[tuple, list[str]] = {}
_DECODED_CARRIER_CACHE: dict[str, dict] = {}
_VERIFIED_RESERVED_CALL_CACHE: dict[tuple, bool] = {}
_ADMISSION_MACHINE_CACHE: dict[tuple, list[dict]] = {}


def cached_admission_machine(
    root: Path, state: dict, proposal: dict, *, check_originals: bool = True
) -> list[dict]:
    """Cache deterministic candidate.check while always running live frozen_input checks."""
    import _b_route_planning_runtime as runtime
    import _b_route_sources as sources

    frozen = runtime.frozen_input(root, state, check_originals=check_originals)
    prepared_ref = runtime.descriptor(state)["prepared_ref"]
    raw_index_path = Path(root) / Path(prepared_ref).parent / "raw-index.json"
    raw_index_sha = file_sha(raw_index_path) if raw_index_path.is_file() else None
    policy = runtime.machine_business_policy(state)
    key = (
        str(Path(root).resolve()),
        state.get("runtime_identity"),
        prepared_ref,
        raw_index_sha,
        frozen["input_identity"],
        canonical_sha(proposal),
        policy,
    )
    cached = _ADMISSION_MACHINE_CACHE.get(key)
    if cached is not None:
        return deepcopy(cached)
    if policy is not None:
        store = candidate.frozen_bytes(root, prepared_ref, frozen, sources.Observations(root))
        runtime.immutable_candidate_checks(proposal, frozen, store)
    result = runtime.machine(root, state, proposal, check_originals=False)
    _bounded_put(_ADMISSION_MACHINE_CACHE, key, deepcopy(result), 32)
    return result


def _segmented_append_machine(root: Path, state: dict, proposal: dict) -> list[dict]:
    """Convert candidate CodecError into a machine issue so run_capability_append can replace cleanly."""
    import _b_route_planning_runtime as runtime

    try:
        return runtime.admission_machine(root, state, proposal)
    except codec.CodecError as exc:
        diagnostic = exc.diagnostic
        identity = {
            "reason": diagnostic.reason_code.value,
            "entity": diagnostic.entity_id,
            "expected": diagnostic.expected,
        }
        return [
            {
                "code": "b_route_machine:" + canonical_sha(identity),
                "path": "candidate:" + str(diagnostic.entity_id or "content"),
                "detail": diagnostic.to_dict(),
            }
        ]


def _segmented_append_repairability(
    before: dict, frozen: dict, issue: dict, *, root: Path, state: dict
) -> bool:
    """Return False on CodecError so immutable-projection or schema failures trigger fresh slot replacement."""
    import _b_route_planning_runtime as runtime

    try:
        return bool(runtime.repair_is_local(before, frozen, issue, root=root, state=state))
    except codec.CodecError:
        return False


def _segmented_repair_scope_errors(
    root: Path, state: dict, before: dict, after: dict, issue: dict, **kwargs
) -> list[str]:
    """Reject a repair draft on CodecError instead of aborting the append run."""
    import _b_route_planning_runtime as runtime

    try:
        return runtime.repair_scope_errors(root, state, before, after, issue, **kwargs)
    except codec.CodecError:
        return ["repair_new_machine_issue"]


def _segmented_machine_repair_errors(root: Path, state: dict, before: dict, after: dict) -> list[str]:
    """Reject a machine repair draft on CodecError instead of aborting the append run."""
    import _b_route_planning_runtime as runtime

    try:
        return runtime.machine_repair_errors(root, state, before, after)
    except codec.CodecError:
        return ["repair_new_machine_issue"]


def _cached_decode_generation_carrier(raw_value: dict) -> dict:
    import _b_route_planning_runtime as runtime

    key = canonical_sha(raw_value)
    cached = _DECODED_CARRIER_CACHE.get(key)
    if cached is not None:
        return cached
    decoded = runtime.decode_generation_carrier(raw_value)
    _bounded_put(_DECODED_CARRIER_CACHE, key, decoded, 192)
    return decoded


def _cached_json_and_sha(path: Path) -> tuple[dict, str]:
    raw_sha = file_sha(path)
    key = (str(path), raw_sha)
    cached = _DISK_JSON_SHA_CACHE.get(key)
    if cached is not None:
        return cached[0], cached[1]
    obj = load_json(path)
    c_sha = canonical_sha(obj)
    if path.stat().st_size <= 1_000_000:
        _bounded_put(_DISK_JSON_SHA_CACHE, key, (obj, c_sha), 32)
    return obj, c_sha


def _cached_read_prompt(prompt_text: str, delivery, *, readonly: bool = False) -> dict:
    key = (codec.raw_digest(prompt_text.encode("utf-8")), str(delivery))
    cached = _WIRE_PROMPT_CACHE.get(key)
    if cached is not None:
        return cached if readonly else deepcopy(cached)
    parsed = wire.read_prompt(prompt_text, delivery)
    _bounded_put(_WIRE_PROMPT_CACHE, key, deepcopy(parsed), 192)
    return parsed


def _verified_call_output(binding: dict, *, readonly: bool = False) -> dict:
    import _b_route_planning_runtime as runtime

    out_path = Path(binding["output_path"])
    s_path = Path(binding["schema_path"])
    if out_path.is_file() and s_path.is_file():
        key = (
            binding.get("binding_sha256"),
            canonical_sha(binding),
            str(out_path),
            file_sha(out_path),
            str(s_path),
            file_sha(s_path),
        )
        cached = _VERIFIED_CALL_CACHE.get(key)
        if cached is not None:
            return cached if readonly else deepcopy(cached)
    else:
        key = None
    raw_value = runtime.verify_call(binding)
    if key is not None:
        _bounded_put(_VERIFIED_CALL_CACHE, key, deepcopy(raw_value), 192)
    return raw_value


def verify_segmented_materials(
    binding: dict, state: dict, frozen: dict, *, readonly: bool = False
) -> dict:
    """Verify wire-rendered segmented materials from a captured binding."""
    import _b_route_planning_runtime as runtime

    p_path = Path(binding["prompt_path"])
    s_path = Path(binding["schema_path"])
    cache_key = None
    if p_path.is_file() and s_path.is_file():
        cache_key = (
            str(p_path),
            file_sha(p_path),
            str(s_path),
            file_sha(s_path),
            state.get("runtime_identity"),
            state.get("run_id"),
            runtime.wire_delivery(state),
            frozen.get("input_identity"),
            canonical_sha(frozen.get("reopen") or {}),
            canonical_sha(state.get("reopen") or {}),
        )
        cached = _VERIFIED_MATERIALS_CACHE.get(cache_key)
        if cached is not None:
            return cached if readonly else deepcopy(cached)

    prompt_bytes = p_path.read_bytes()
    prompt = prompt_bytes.decode("utf-8")
    schema_on_disk = codec.strict_json_loads(s_path.read_bytes())
    content_key = (
        codec.raw_digest(prompt_bytes),
        canonical_sha(schema_on_disk),
        state.get("runtime_identity"),
        state.get("run_id"),
        runtime.wire_delivery(state),
        frozen.get("input_identity"),
        canonical_sha(frozen.get("reopen") or {}),
        canonical_sha(state.get("reopen") or {}),
    )
    cached_by_content = _VERIFIED_MATERIALS_CACHE.get(content_key)
    if cached_by_content is not None:
        if cache_key is not None:
            _bounded_put(_VERIFIED_MATERIALS_CACHE, cache_key, cached_by_content, 256)
        return cached_by_content if readonly else deepcopy(cached_by_content)

    materials = wire.read_prompt(prompt, runtime.wire_delivery(state))
    if materials.get("segmented_runtime_policy") != SEGMENTED_RUNTIME_POLICY:
        raise ValueError("b_route_segmented_materials_policy_missing")
    expected_identity = canonical_sha({k: v for k, v in materials.items() if k != "materials_identity"})
    if (
        materials.get("materials_identity") != expected_identity
        or materials.get("root_input_identity") != frozen["input_identity"]
        or materials.get("runtime_identity") != state["runtime_identity"]
        or materials.get("run_id") != state["run_id"]
    ):
        raise ValueError("b_route_segmented_materials_identity_changed")
    if not runtime.same_json(materials.get("actual_output_schema"), schema_on_disk):
        raise ValueError("b_route_segmented_materials_schema_changed")
    if prompt != runtime.materials_prompt(materials):
        raise ValueError("b_route_segmented_materials_prompt_changed")
    if materials["phase"] == "generation":
        req = materials["root_request"]
        expected_schema = segmented_provider_generation_schema(
            frozen,
            stage=req["stage"],
            ordinal=req["ordinal"],
            parent_draft_identities=req["parent_draft_identities"],
        )
        exp_contract, exp_target = _generation_contract_for_request(req)
        if (
            not runtime.same_json(schema_on_disk, expected_schema)
            or not runtime.same_json(materials.get("content_contract"), exp_contract)
            or not runtime.same_json(materials.get("final_content_target"), exp_target)
        ):
            raise ValueError("b_route_segmented_generation_contract_changed")
        _validate_generation_request_flags(req, materials)
    elif materials["phase"] == "independent_admission":
        _validated_review_projection_level(materials["root_request"])
        directive = runtime.reopen_directive(state, frozen, materials.get("generation", 1))
        seg_directive = (
            directive
            if materials["root_request"]["obligation_range"][0] == 0
            else None
        )
        expected_schema = segmented_indexed_review_schema(
            state,
            frozen,
            proposal_sha256=materials["proposal"]["proposal_sha256"],
            seg_obligations=materials["obligations"],
            seg_sources=materials["qualified_sources"],
            directive=seg_directive,
        )
        if not runtime.same_json(schema_on_disk, expected_schema):
            raise ValueError("b_route_segmented_review_schema_mismatch")
    else:
        raise ValueError("b_route_segmented_materials_phase_invalid")
    stored = deepcopy(materials)
    _bounded_put(_VERIFIED_MATERIALS_CACHE, content_key, stored, 256)
    if cache_key is not None:
        _bounded_put(_VERIFIED_MATERIALS_CACHE, cache_key, stored, 256)
    return stored if readonly else materials


def _governed_gemini_model_for_root(root: Path) -> str | None:
    import os
    from _gemini_cli_protocol import FORBIDDEN_MODEL_ALIASES

    routing_path = None
    if os.environ.get("NEWROGUE_ALLOW_TEST_MODEL_OVERRIDE") == "1":
        env_routing = str(os.environ.get("NEWROGUE_LLM_ROUTING_PATH") or "").strip()
        if env_routing:
            routing_path = Path(env_routing).resolve()
    if routing_path is None and root is not None:
        cand = Path(root) / "docs/workflows/llm-routing.json"
        if cand.is_file():
            routing_path = cand.resolve()
    if routing_path is None:
        repo_routing = (Path(__file__).resolve().parents[2] / "docs/workflows/llm-routing.json")
        if repo_routing.is_file():
            routing_path = repo_routing
    if routing_path is None or not routing_path.is_file():
        return None
    routing = codec.strict_json_loads(routing_path.read_bytes())
    plane_b = routing.get("plane_b") if isinstance(routing, dict) else None
    runners = plane_b.get("runners") if isinstance(plane_b, dict) else None
    gemini_cfg = runners.get("gemini") if isinstance(runners, dict) else None
    model = str(gemini_cfg.get("model") or "").strip() if isinstance(gemini_cfg, dict) else ""
    if not model or any(ch.isspace() for ch in model) or model.casefold() in FORBIDDEN_MODEL_ALIASES:
        raise ValueError("b_route_governed_gemini_model_missing")
    return model


def _binding_session_and_model(root: Path, binding: dict) -> tuple[str, str, str, str]:
    receipt = binding.get("receipt")
    if not isinstance(receipt, dict):
        raise ValueError("b_route_binding_receipt_missing")
    evidence_list = receipt.get("model_identity_evidence")
    if not isinstance(evidence_list, list) or len(evidence_list) != 1 or not isinstance(evidence_list[0], dict):
        raise ValueError("b_route_binding_evidence_invalid")
    ev = evidence_list[0]
    thread_id = ev.get("thread_id") or ev.get("session_id")
    turn_id = ev.get("turn_id")
    provider = str(ev.get("model_provider") or receipt.get("model_provider") or "")
    model = str(ev.get("model") or receipt.get("model") or "")
    if not isinstance(thread_id, str) or not thread_id.strip():
        raise ValueError("b_route_binding_thread_id_missing")
    if not isinstance(turn_id, str) or not turn_id.strip():
        raise ValueError("b_route_binding_turn_id_missing")
    runner_info = binding.get("runner_info") or {}
    runner_name = Path(str(runner_info.get("runner") or "")).name
    if provider.casefold() == "google" or runner_name == "gemini_isolated_model_runner.py":
        gov_model = _governed_gemini_model_for_root(root)
        if gov_model is not None and (model != gov_model or runner_info.get("model") != gov_model):
            raise ValueError(f"b_route_gemini_model_ungoverned:{model}:expected:{gov_model}")
    return thread_id, turn_id, provider, model


def _enforce_disjoint_sessions(
    root: Path,
    bindings: list[dict],
    *,
    seen_threads: set[str] | None = None,
    seen_turns: set[str] | None = None,
    expected_provider_model: tuple[str, str] | None = None,
    context_label: str,
) -> tuple[set[str], set[str], tuple[str, str] | None]:
    threads = set() if seen_threads is None else seen_threads
    turns = set() if seen_turns is None else seen_turns
    prov_model = expected_provider_model
    for binding in bindings:
        tid, uid, prov, mod = _binding_session_and_model(root, binding)
        if tid in threads:
            raise ValueError(f"b_route_reused_session_thread:{context_label}:{tid}")
        if uid in turns:
            raise ValueError(f"b_route_reused_session_turn:{context_label}:{uid}")
        threads.add(tid)
        turns.add(uid)
        if prov_model is None:
            prov_model = (prov, mod)
        elif prov_model != (prov, mod):
            raise ValueError(
                f"b_route_inconsistent_model:{context_label}:{prov}/{mod}:expected:{prov_model[0]}/{prov_model[1]}"
            )
    return threads, turns, prov_model


def prepare_segmented_dispatch(
    root: Path,
    run_dir: Path,
    state: dict,
    runner: Path,
    workspace: Path,
    prompt_path: Path,
    schema_path: Path,
    output_path: Path,
    attempt: int,
    binding_path: Path,
    *,
    timeout_sec: int,
) -> tuple[dict, str, dict]:
    """Enforce <= 70,000 UTF-8 bytes and <= 96,000 tokens on EVERY model dispatch."""
    import _b_route_planning_runtime as runtime
    from _mvg_capability_generation import dispatch_request_identity
    from openai_isolated_model_runner import workspace_payload

    runtime.require_live_high(state, runner)
    if Path(runner).name == "gemini_isolated_model_runner.py":
        gov_model = _governed_gemini_model_for_root(root)
        info_model = state.get("runner_configuration", {}).get("backend_info", {}).get("model")
        if gov_model is not None and info_model != gov_model:
            raise ValueError(f"b_route_gemini_model_ungoverned:{info_model}:expected:{gov_model}")

    frozen = runtime.frozen_input(root, state)
    actual = workspace_payload(
        workspace,
        prompt_path=prompt_path,
        output_path=output_path,
        max_bytes=MAX_WORKSPACE_PAYLOAD_BYTES,
    )
    actual_bytes = len(actual.encode("utf-8"))
    schema = codec.strict_json_loads(schema_path.read_bytes())
    measurement = runtime.measure_actual(frozen, actual, schema)
    measurement["workspace_payload_utf8_bytes"] = actual_bytes
    measurement["max_workspace_payload_bytes"] = MAX_WORKSPACE_PAYLOAD_BYTES
    _assert_under_70k(
        max(actual_bytes, int(measurement["request_bytes"])), frozen, "prepare_segmented_dispatch"
    )

    request = dispatch_request_identity(
        run_dir,
        runner,
        workspace=workspace,
        prompt_path=prompt_path,
        output_path=output_path,
        output_schema=schema_path,
        attempt=attempt,
    )
    request.update(
        planning_profile=runtime.descriptor(state)["profile"],
        runtime_identity=state["runtime_identity"],
        segmented_runtime_policy=SEGMENTED_RUNTIME_POLICY,
        execution_binding_path=binding_path.relative_to(run_dir).as_posix(),
        actual_request_sha256=codec.raw_digest(actual.encode("utf-8")),
        measurement=measurement,
        requested_timeout_sec=timeout_sec,
        runner_path=str(runner),
        runner_info_sha256=canonical_sha(state["runner_configuration"]["backend_info"]),
        wire_delivery=runtime.wire_delivery(state),
    )

    instruction = prompt_path.read_text(encoding="utf-8")
    if instruction.startswith("Use complete governed originals"):
        materials = verify_segmented_materials(
            {"prompt_path": str(prompt_path), "schema_path": str(schema_path)},
            state,
            frozen,
            readonly=True,
        )
        if materials["phase"] == "generation":
            if materials.get("repair_issue") is not None:
                r_scope = materials.get("repair_scope")
                prior_c = materials.get("prior_candidate")
                if (
                    materials.get("repair_scope_policy") != runtime.REPAIR_SCOPE_POLICY
                    or not isinstance(prior_c, dict)
                    or not isinstance(r_scope, dict)
                    or r_scope.get("policy") != runtime.REPAIR_SCOPE_POLICY
                    or r_scope.get("before_sha256") != prior_c.get("proposal_sha256")
                    or r_scope.get("issue_sha256") != canonical_sha(materials["repair_issue"])
                ):
                    raise ValueError("b_route_segmented_repair_dispatch_policy_invalid")
            elif (
                materials.get("prior_candidate") is not None
                or materials.get("repair_scope_policy") is not None
                or materials.get("repair_scope") is not None
            ):
                raise ValueError("b_route_generation_unbound_prior_candidate")
        request["fresh_lineage_identity"] = materials["lineage_identity"]
        request["synthesis"] = (
            materials["phase"] == "generation" and materials["root_request"]["stage"] == "synthesis"
        )
    else:
        materials = wire.read_prompt(instruction, runtime.wire_delivery(state))
        if materials.get("phase") == "selection":
            check_segmented_selector_materials(
                root, run_dir, state, materials, workspace.parents[2]
            )
            if instruction != segmented_selector_prompt(materials) or not runtime.same_json(
                schema, runtime.selection_schema(state)
            ):
                raise ValueError("b_route_segmented_selector_dispatch_changed")
            request["segmented_selector_policy"] = SEGMENTED_SELECTOR_POLICY
        elif materials.get("phase") == "selection_pair":
            pair = materials["identity"]["pair"]
            pair_no = materials["identity"]["pair_index"]
            comp_ws = workspace.parents[3]
            if workspace.parents[2].name != f"p{pair_no}":
                raise ValueError("b_route_segmented_selector_pair_workspace_changed")
            expected_index, full_materials, _ = _reconstruct_selector_expected_and_full(
                root, run_dir, state, materials["identity"]["order_index"], comp_ws
            )
            if not expected_index.get("tournament_mode"):
                raise ValueError("b_route_segmented_selector_tournament_unactivated")
            expected_pair_mat, expected_pair_prompt, expected_pair_schema = _build_pair_materials_and_prompt(
                state, frozen, expected_index, full_materials, pair_no, pair[0], pair[1]
            )
            if (
                wire.text(materials) != wire.text(expected_pair_mat)
                or instruction != expected_pair_prompt
                or not runtime.same_json(schema, expected_pair_schema)
            ):
                raise ValueError("b_route_segmented_selector_pair_dispatch_changed")
            request["segmented_selector_policy"] = SEGMENTED_SELECTOR_POLICY
        else:
            raise ValueError("b_route_segmented_dispatch_unknown_phase")

    request["request_sha256"] = canonical_sha(
        {k: v for k, v in request.items() if k != "request_sha256"}
    )
    return request, actual, measurement


def verify_segmented_reserved_call(
    run_dir: Path, row: dict, *, state: dict | None = None, check_originals: bool = True
):
    import base64
    import _b_route_planning_runtime as runtime
    from _capability_input_integrity import REPORT_NAME
    from _planning_skill_common import _runner_prefix

    root = run_dir.parents[3]
    request = row["request_identity"]
    res_cache_key = None
    if row.get("outcome", {}).get("status") == "completed":
        try:
            resolved_probe = runtime._reserved_state(run_dir, row, state)
            ws_dir = sources.checked_path(run_dir, request["workspace"])
            b_file = sources.checked_path(run_dir, request["execution_binding_path"])
            o_file = sources.checked_path(run_dir, request["output_path"])
            p_file = sources.checked_path(run_dir, request["prompt_path"])
            s_file = sources.checked_path(run_dir, request["schema_path"])
            sidecar_file = run_dir / "dispatch-receipts" / f"dispatch-{row['number']}.json"
            prep_file = run_dir / "analysis-input/b-route-prepared.json"
            cd_file = b_file.parent / "canonical-draft.json"
            routing_file = root / "docs/workflows/llm-routing.json"
            if (
                ws_dir.is_dir()
                and b_file.is_file()
                and o_file.is_file()
                and p_file.is_file()
                and s_file.is_file()
                and p_file.read_bytes().startswith(b"Use complete governed originals")
            ):
                ws_sig = tuple(
                    (p.relative_to(ws_dir).as_posix(), file_sha(p))
                    for p in sorted(ws_dir.rglob("*"))
                    if p.is_file()
                )
                res_cache_key = (
                    str(run_dir.resolve()),
                    canonical_sha(row),
                    resolved_probe.get("runtime_identity"),
                    resolved_probe.get("run_id"),
                    runtime.wire_delivery(resolved_probe),
                    canonical_sha(resolved_probe.get("reopen_contexts") or []),
                    file_sha(sidecar_file) if sidecar_file.is_file() else None,
                    file_sha(b_file),
                    file_sha(o_file),
                    file_sha(p_file),
                    file_sha(s_file),
                    file_sha(prep_file) if prep_file.is_file() else None,
                    file_sha(cd_file) if cd_file.is_file() else None,
                    file_sha(routing_file) if routing_file.is_file() else None,
                    ws_sig,
                )
                if _VERIFIED_RESERVED_CALL_CACHE.get(res_cache_key) is True:
                    return codec.strict_json_loads(b_file.read_bytes())
        except Exception:
            res_cache_key = None

    if canonical_sha({k: v for k, v in request.items() if k != "request_sha256"}) != request["request_sha256"]:
        raise ValueError("b_route_dispatch_request_changed")
    workspace = sources.checked_path(run_dir, request["workspace"])
    sources.checked_path(run_dir, request["output_path"])
    for field in ("prompt_path", "schema_path", "execution_binding_path"):
        sources.checked_path(run_dir, request[field])
    for relative, digest in request["input_files"].items():
        path = sources.checked_path(workspace, relative)
        if file_sha(path) != digest:
            raise ValueError("b_route_dispatch_inputs_changed:" + relative)
    bound = row.get("outcome")
    if bound is None:
        raise ValueError("b_route_dispatch_outcome_unknown")
    sidecar = load_json(run_dir / "dispatch-receipts" / f"dispatch-{row['number']}.json", None)
    expected = {k: v for k, v in row.items() if k != "outcome"}
    if sidecar is not None and canonical_sha(sidecar) not in {
        canonical_sha(expected),
        canonical_sha({**expected, **bound}),
    }:
        raise ValueError("b_route_dispatch_outcome_changed")
    if bound.get("status") == "failed":
        if not bound.get("error_type") or not bound.get("error_class"):
            raise ValueError("b_route_dispatch_failure_invalid")
        return None
    if bound.get("status") != "completed":
        raise ValueError("b_route_dispatch_outcome_unknown")
    output = sources.checked_path(run_dir, request["output_path"])
    binding_path = sources.checked_path(run_dir, request["execution_binding_path"])
    binding = codec.strict_json_loads(binding_path.read_bytes())
    req_payload_bytes = len(binding["request_payload"].encode("utf-8"))
    if (
        Path(binding["workspace"]) != workspace
        or Path(binding["output_path"]) != output
        or Path(binding["prompt_path"]) != sources.checked_path(run_dir, request["prompt_path"])
        or Path(binding["schema_path"]) != sources.checked_path(run_dir, request["schema_path"])
        or codec.raw_digest(binding["request_payload"].encode("utf-8")) != request["actual_request_sha256"]
        or req_payload_bytes > MAX_WORKSPACE_PAYLOAD_BYTES
        or binding["measurement"] != request["measurement"]
        or file_sha(output) != bound.get("output_sha256")
        or canonical_sha(binding["runner_info"]) != request["runner_info_sha256"]
        or not runtime.same_json(
            bound.get("active_elapsed_seconds"), binding["host_execution"]["active_elapsed_seconds"]
        )
    ):
        raise ValueError("b_route_dispatch_binding_changed")
    _binding_session_and_model(root, binding)
    raw_value = _verified_call_output(binding, readonly=True)
    instruction = Path(binding["prompt_path"]).read_text(encoding="utf-8")
    state = runtime._reserved_state(run_dir, row, state)
    if request.get("wire_delivery") != runtime.wire_delivery(state):
        raise ValueError("b_route_reserved_wire_delivery_changed")
    frozen, frozen_sha = _cached_json_and_sha(run_dir / "analysis-input/b-route-prepared.json")
    _assert_under_70k(
        max(req_payload_bytes, int(binding["measurement"]["request_bytes"])),
        frozen,
        "verify_segmented_reserved_call",
    )
    if instruction.startswith("Use complete governed originals"):
        materials = verify_segmented_materials(binding, state, frozen, readonly=True)
        if materials["phase"] == "generation":
            desc = runtime.descriptor(state)
            if frozen_sha != desc["frozen_sha256"] or frozen["input_identity"] != desc["input_identity"]:
                raise ValueError("b_route_reserved_frozen_input_changed")
            canonical = _cached_decode_generation_carrier(raw_value)
            if not runtime.same_json(load_json(binding_path.parent / "canonical-draft.json"), canonical):
                raise ValueError("b_route_generation_canonical_draft_changed")
    else:
        materials = _cached_read_prompt(instruction, runtime.wire_delivery(state))
        if materials.get("phase") == "selection":
            check_segmented_selector_materials(
                root,
                run_dir,
                state,
                materials,
                workspace.parents[2],
                check_originals=check_originals,
            )
            if instruction != segmented_selector_prompt(materials) or not runtime.same_json(
                load_json(Path(binding["schema_path"])), runtime.selection_schema(state)
            ):
                raise ValueError("b_route_segmented_selector_reserved_changed")
            if runtime.selection_errors(state, raw_value):
                raise ValueError("b_route_segmented_selector_output_invalid")
            if materials.get("tournament_synthesis") and (
                raw_value.get("selected") != materials["pairwise_verdicts"].get("bracket_winner")
            ):
                raise ValueError("b_route_tournament_synthesis_bracket_mismatch")
        elif materials.get("phase") == "selection_pair":
            pair = materials["identity"]["pair"]
            pair_no = materials["identity"]["pair_index"]
            comp_ws = workspace.parents[3]
            if workspace.parents[2].name != f"p{pair_no}":
                raise ValueError("b_route_segmented_selector_pair_workspace_changed")
            expected_index, full_materials, _ = _reconstruct_selector_expected_and_full(
                root,
                run_dir,
                state,
                materials["identity"]["order_index"],
                comp_ws,
                check_originals=check_originals,
            )
            if not expected_index.get("tournament_mode"):
                raise ValueError("b_route_segmented_selector_tournament_unactivated")
            expected_pair_mat, expected_pair_prompt, expected_pair_schema = _build_pair_materials_and_prompt(
                state, frozen, expected_index, full_materials, pair_no, pair[0], pair[1]
            )
            if (
                wire.text(materials) != wire.text(expected_pair_mat)
                or instruction != expected_pair_prompt
                or not runtime.same_json(load_json(Path(binding["schema_path"])), expected_pair_schema)
                or _pairwise_selection_errors(pair, raw_value)
            ):
                raise ValueError("b_route_segmented_selector_pair_reserved_changed")
        else:
            raise ValueError("b_route_segmented_reserved_unknown_phase")

    expected_command = [
        *_runner_prefix(Path(request["runner_path"]), suppress_bytecode=True),
        "--workspace",
        str(workspace),
        "--prompt-file",
        str(sources.checked_path(run_dir, request["prompt_path"])),
        "--output",
        str(output),
        "--timeout-sec",
        str(request["timeout_sec"]),
        "--output-schema",
        str(sources.checked_path(run_dir, request["schema_path"])),
        "--model-request-budget",
        "1",
    ]
    if binding["host_execution"]["command"] != expected_command:
        raise ValueError("b_route_host_execution_command_changed")
    raw_proto = base64.b64decode(
        binding["receipt"]["model_identity_evidence"][0]["protocol_jsonl_base64"], validate=True
    )
    allowed = set(request["input_files"]) | {output.name, REPORT_NAME}
    for path in workspace.rglob("*"):
        if path.is_file() and path.relative_to(workspace).as_posix() not in allowed:
            if (
                path.name not in binding["generated_outputs"]
                or not runtime.execution_output_name(path.name, output.name)
                or (
                    path.name.endswith((".app-server.jsonl", ".gemini-stream.jsonl"))
                    and path.read_bytes().replace(b"\r\n", b"\n") != raw_proto
                )
            ):
                raise ValueError("b_route_dispatch_unreserved_input_or_output:" + path.name)
    if res_cache_key is not None:
        _bounded_put(_VERIFIED_RESERVED_CALL_CACHE, res_cache_key, True, 256)
    return binding


def verify_segmented_selector_reservation(
    run_dir: Path,
    state: dict,
    scope: dict,
    index: int,
    step: dict,
    receipt: dict,
    comparison_workspace: Path,
    output: Path,
    *,
    check_originals: bool = True,
) -> None:
    import _b_route_planning_runtime as runtime

    root = run_dir.parents[3]
    binding = receipt["execution_binding"]
    prompt = Path(binding["prompt_path"]).read_text(encoding="utf-8")
    materials = _cached_read_prompt(prompt, runtime.wire_delivery(state))
    expected_index, full_materials, candidate_proofs = _reconstruct_selector_expected_and_full(
        root, run_dir, state, index, comparison_workspace, check_originals=check_originals
    )

    seen_threads: set[str] = set()
    seen_turns: set[str] = set()
    prov_model: tuple[str, str] | None = None
    for label in runtime.labels(state):
        prf = candidate_proofs[label]
        for rec in prf.get("records", []):
            if rec.get("kind") == "adoption":
                continue
            cand_bindings = [
                *rec["delta"]["generation_calls"],
                *(rec["proof"].get("review_executions") or [rec["execution"]]),
            ]
            seen_threads, seen_turns, prov_model = _enforce_disjoint_sessions(
                root,
                cand_bindings,
                seen_threads=seen_threads,
                seen_turns=seen_turns,
                expected_provider_model=prov_model,
                context_label=f"selector_candidate:{label}",
            )

    public = {key: value for key, value in step["input_identity"].items() if key != "candidates"}
    public["candidates"] = {
        alias: {key: value for key, value in cand.items() if key != "lineage"}
        for alias, cand in step["input_identity"]["candidates"].items()
    }
    tournament_required = bool(expected_index.get("tournament_mode"))
    manifest_path = comparison_workspace / PAIRWISE_TOURNAMENT_MANIFEST_NAME
    sidecar_path = comparison_workspace / SELECTOR_FULL_SIDECAR_NAME

    if not tournament_required:
        if manifest_path.exists() or materials.get("tournament_mode") or materials.get("phase") != "selection":
            raise ValueError("b_route_segmented_selector_unexpected_tournament")
        sandbox = comparison_workspace / "llm-sandbox" / f"attempt-{step['attempt']}" / "selection"
        row = runtime.verify_bound_reservation(
            run_dir,
            state,
            binding,
            candidate_slot=None,
            scope_id=scope["capability_id"],
            phase="selection",
            generation=step.get("generation", 1),
            execution=step.get("execution", 1),
            expected_workspace=sandbox,
            expected_output=output,
            reservation_id=step["reservation_id"],
            check_originals=check_originals,
        )
        if (
            wire.text(materials) != wire.text(expected_index)
            or prompt != segmented_selector_prompt(materials)
            or row["request_identity"].get("selection_input_sha256") != step["input_sha256"]
            or not runtime.same_json(
                {"scope": materials["scope"], "identity": materials["identity"]},
                {"scope": scope, "identity": public},
            )
            or not runtime.same_json(
                codec.strict_json_loads(Path(binding["schema_path"]).read_bytes()),
                runtime.selection_schema(state),
            )
        ):
            raise ValueError("b_route_segmented_selector_reserved_materials_changed")
        _enforce_disjoint_sessions(
            root,
            [binding],
            seen_threads=seen_threads,
            seen_turns=seen_turns,
            expected_provider_model=prov_model,
            context_label="selector_single_turn",
        )
        return

    if not manifest_path.is_file() or not sidecar_path.is_file():
        raise ValueError("b_route_segmented_selector_tournament_manifest_missing")
    full_sha = canonical_sha(full_materials)
    if canonical_sha(load_json(sidecar_path)) != full_sha:
        raise ValueError("b_route_segmented_selector_sidecar_changed")
    manifest = load_json(manifest_path)
    aliases = list(step["aliases"].keys())
    bindings_list = manifest.get("bindings")
    reservation_ids = manifest.get("reservation_ids")
    if (
        manifest.get("schema_version") != PAIRWISE_TOURNAMENT_SCHEMA
        or manifest.get("segmented_selector_policy") != SEGMENTED_SELECTOR_POLICY
        or manifest.get("attempt") != step["attempt"]
        or manifest.get("full_materials_sha256") != full_sha
        or not isinstance(bindings_list, list)
        or not isinstance(reservation_ids, list)
        or len(bindings_list) != len(aliases)
        or len(reservation_ids) != len(aliases)
        or reservation_ids[-1] != step["reservation_id"]
        or not runtime.same_json(bindings_list[-1], binding)
    ):
        raise ValueError("b_route_segmented_selector_tournament_manifest_invalid")

    replayed_verdicts: dict = {}
    champ = aliases[0]
    for pair_no, challenger in enumerate(aliases[1:], 1):
        b_pair = bindings_list[pair_no - 1]
        res_pair = reservation_ids[pair_no - 1]
        pair_sandbox = comparison_workspace / f"p{pair_no}" / "llm-sandbox" / f"attempt-{step['attempt']}" / "o"
        row_pair = runtime.verify_bound_reservation(
            run_dir,
            state,
            b_pair,
            candidate_slot=None,
            scope_id=scope["capability_id"],
            phase="selection",
            generation=step.get("generation", 1),
            execution=step.get("execution", 1),
            expected_workspace=pair_sandbox,
            expected_output=pair_sandbox / "o.json",
            reservation_id=res_pair,
            check_originals=check_originals,
        )
        if row_pair["request_identity"].get("selection_input_sha256") != step["input_sha256"]:
            raise ValueError("b_route_segmented_selector_pair_input_sha_changed")
        pair_mat = _cached_read_prompt(
            Path(b_pair["prompt_path"]).read_text(encoding="utf-8"), runtime.wire_delivery(state)
        )
        expected_pair = [champ, challenger]
        if (
            pair_mat.get("phase") != "selection_pair"
            or pair_mat.get("identity", {}).get("pair") != expected_pair
            or pair_mat.get("identity", {}).get("pair_index") != pair_no
        ):
            raise ValueError("b_route_segmented_selector_bracket_inconsistent")
        pair_out = _verified_call_output(b_pair)
        if _pairwise_selection_errors(expected_pair, pair_out):
            raise ValueError("b_route_segmented_selector_pair_output_invalid")
        replayed_verdicts[f"pair_{pair_no}"] = {"pair": expected_pair, "result": pair_out}
        champ = pair_out["selected"]
    replayed_verdicts["bracket_winner"] = champ

    t3_sandbox = comparison_workspace / "llm-sandbox" / f"attempt-{step['attempt']}" / "selection"
    row_t3 = runtime.verify_bound_reservation(
        run_dir,
        state,
        binding,
        candidate_slot=None,
        scope_id=scope["capability_id"],
        phase="selection",
        generation=step.get("generation", 1),
        execution=step.get("execution", 1),
        expected_workspace=t3_sandbox,
        expected_output=output,
        reservation_id=step["reservation_id"],
        check_originals=check_originals,
    )
    expected_t3_materials = _build_tournament_synthesis_materials(expected_index, replayed_verdicts)
    t3_out = _verified_call_output(binding)
    if (
        wire.text(materials) != wire.text(expected_t3_materials)
        or prompt != segmented_selector_prompt(materials)
        or row_t3["request_identity"].get("selection_input_sha256") != step["input_sha256"]
        or not runtime.same_json(
            {"scope": materials["scope"], "identity": materials["identity"]},
            {"scope": scope, "identity": public},
        )
        or not runtime.same_json(
            codec.strict_json_loads(Path(binding["schema_path"]).read_bytes()),
            runtime.selection_schema(state),
        )
        or runtime.selection_errors(state, t3_out)
        or t3_out.get("selected") != champ
        or manifest.get("bracket_winner") != champ
        or manifest.get("final_selected") != champ
        or not runtime.same_json(manifest.get("pairwise_verdicts"), replayed_verdicts)
    ):
        raise ValueError("b_route_segmented_selector_tournament_synthesis_invalid")

    _enforce_disjoint_sessions(
        root,
        bindings_list,
        seen_threads=seen_threads,
        seen_turns=seen_turns,
        expected_provider_model=prov_model,
        context_label="selector_tournament",
    )


def verify_segmented_proof_reservations(
    root: Path, state: dict, proof: dict, *, admission: dict | None = None, check_originals: bool = True
) -> None:
    import _b_route_planning_runtime as runtime
    from _mvg_capability_selection import scope_workspace

    run_dir = runtime.run_location(root, runtime.descriptor(state)["planner"], state["run_id"])
    for index, record in enumerate(proof["records"]):
        if record.get("kind") == "adoption":
            continue
        line = record["delta"]["lineage"]
        slot, attempt, execution = line["slot"], line["generation"], line["execution"]
        if slot not in runtime.labels(state) or (
            admission is not None
            and (
                slot != admission["candidate"]
                or attempt != admission.get("generation", 1)
                or execution != admission.get("execution", 1)
            )
        ):
            raise ValueError("b_route_proof_candidate_slot_changed")
        expected_lineage = runtime.lineage_identity(
            state, proof["seed"], slot, record["context"], attempt, execution
        )
        if line["identity"] != expected_lineage or line["context"] != record["context"]:
            raise ValueError("b_route_proof_fresh_lineage_changed")
        workspace = scope_workspace(run_dir, slot, index, attempt, execution)
        local = load_json(workspace / "capability-append/append-ledger.json")
        review_bindings = record["proof"].get("review_executions") or [record["execution"]]
        if not review_bindings or not runtime.same_json(review_bindings[0], record["execution"]):
            raise ValueError("b_route_segmented_review_primary_binding_mismatch")
        review_binding_shas = {b["binding_sha256"] for b in review_bindings}

        for binding in [*record["delta"]["generation_calls"], *review_bindings]:
            output = Path(binding["output_path"])
            if not output.is_relative_to(workspace):
                raise ValueError("b_route_proof_candidate_workspace_changed")
            rows = [
                row
                for row in state["capability_selection"].get("calls", [])
                if row.get("request_identity", {}).get("output_path")
                == output.relative_to(run_dir).as_posix()
            ]
            if len(rows) != 1:
                raise ValueError("b_route_proof_charged_reservation_missing")
            request = rows[0]["request_identity"]
            number = request["attempt"]
            prompt_path = Path(binding["prompt_path"])
            if not prompt_path.is_relative_to(workspace):
                raise ValueError("b_route_proof_request_path_changed")
            prompt_path = sources.checked_path(run_dir, prompt_path.relative_to(run_dir).as_posix())
            materials = _cached_read_prompt(
                prompt_path.read_text(encoding="utf-8"), runtime.wire_delivery(state), readonly=True
            )
            call_root = segmented_call_root(workspace, number)
            sandbox = call_root / "llm-sandbox" / f"attempt-{number}" / "r"
            if (
                Path(binding["prompt_path"]) != sandbox / f"prompt-{number}-r.txt"
                or Path(binding["schema_path"]) != sandbox / "output-schema.json"
            ):
                raise ValueError("b_route_proof_request_path_changed")
            phase = (
                "semantic"
                if binding["binding_sha256"] in review_binding_shas
                else ("repair" if materials.get("repair_issue") is not None else "generate")
            )
            row = runtime.verify_bound_reservation(
                run_dir,
                state,
                binding,
                candidate_slot=slot,
                scope_id=record["scope"]["capability_id"],
                phase=phase,
                generation=attempt,
                execution=execution,
                expected_workspace=sandbox,
                expected_output=sandbox / "r.json",
                check_originals=check_originals,
            )
            if (
                request["execution_binding_path"]
                != (call_root / f"execution-binding-{number}-r.json").relative_to(run_dir).as_posix()
                or request.get("fresh_lineage_identity") != expected_lineage
                or materials.get("lineage_identity") != expected_lineage
                or materials.get("lineage_context") != record["context"]
                or materials.get("slot") != slot
                or materials.get("generation") != attempt
                or materials.get("execution") != execution
                or not any(
                    call.get("reservation_id") == row["reservation_id"]
                    and call.get("number") == number
                    and call.get("context") == record["context"]
                    and call.get("phase") == phase
                    for call in local.get("calls", [])
                )
            ):
                raise ValueError("b_route_proof_local_reservation_changed")


def _proposal_from_draft_prefix(frozen: dict, draft_prefix: list[dict]) -> dict:
    return {
        "schema_version": candidate.SCHEMA,
        "input_stage": "3b",
        "input_identity": frozen["input_identity"],
        "provenance": {
            "kind": "model_draft",
            "declaration": "Complete original model draft chain; execution separately replayed",
            "upstream_model_history": "declared_model",
            "draft_chain": deepcopy(draft_prefix),
            "final_draft_identity": codec.canonical_digest(draft_prefix[-1]),
        },
        "content": deepcopy(draft_prefix[-1]["content"]),
    }


def _verify_segmented_repair_origin(
    root: Path,
    state: dict,
    frozen: dict,
    prior_full: dict,
    materials: dict,
    binding: dict,
    *,
    seen: set[str] | None = None,
    _work=None,
    check_originals: bool = True,
) -> None:
    """Close segmented Stage 4 repair prior_candidate and repair_issue against earlier paid reservations."""
    import _b_route_planning_runtime as runtime

    seen = set() if seen is None else seen
    _work = runtime._RepairOriginWork(state) if _work is None else _work
    _work.enter()
    identity = binding["binding_sha256"]
    if identity in seen or len(seen) >= 64:
        raise ValueError("b_route_repair_origin_cycle_or_limit")
    seen.add(identity)
    try:
        run_dir = runtime.run_location(root, runtime.descriptor(state)["planner"], state["run_id"])
        calls = state["capability_selection"]["calls"]
        if type(calls) is not list or len(calls) > _work.run_limit:
            raise ValueError("b_route_repair_origin_run_limit")
        _work.spend(len(calls))
        matches = [
            row
            for row in calls
            if run_dir / row["request_identity"]["output_path"] == Path(binding["output_path"])
        ]
        if len(matches) != 1:
            raise ValueError("b_route_repair_current_reservation_missing")
        current = matches[0]
        _work.check_calls(calls, current.get("candidate"))

        issue = materials["repair_issue"]
        drafts = prior_full["provenance"]["draft_chain"]
        if type(drafts) is not list or not drafts or len(drafts) > 64:
            raise ValueError("b_route_repair_origin_draft_limit")
        planning.validate_draft_chain(frozen, drafts)
        if not runtime.same_json(prior_full["content"], drafts[-1]["content"]):
            raise ValueError("b_route_repair_prior_content_changed")

        earlier: list[tuple[int, dict, dict]] = []
        for row in calls:
            _work.spend()
            if (
                row["number"] >= current["number"]
                or row.get("candidate") != current.get("candidate")
                or row.get("generation", 1) != current.get("generation", 1)
                or row.get("execution", 1) != current.get("execution", 1)
                or (row.get("outcome") or {}).get("status") != "completed"
            ):
                continue
            req = row["request_identity"]
            if req.get("fresh_lineage_identity") != materials["lineage_identity"]:
                continue
            _work.spend()
            retained = verify_segmented_reserved_call(
                run_dir, row, state=state, check_originals=check_originals
            )
            data = verify_segmented_materials(retained, state, frozen, readonly=True)
            if data.get("lineage_context") == materials["lineage_context"]:
                earlier.append((row["number"], retained, data))

        final_binding = None
        final_materials = None
        for d_idx, draft in enumerate(drafts):
            _work.spend()
            expected_parents = [codec.canonical_digest(d) for d in drafts[:d_idx]]
            found = []
            stub_errors: list[str] = []
            for _, retained, data in earlier:
                _work.spend()
                if data["phase"] != "generation":
                    continue
                decoded = _cached_decode_generation_carrier(_verified_call_output(retained, readonly=True))
                req = data["root_request"]
                if req.get("ordinal") != d_idx + 1 or req.get("parent_draft_identities") != expected_parents:
                    continue
                if data.get("repair_issue") is not None and d_idx >= 1:
                    try:
                        decoded = _expected_repair_draft(
                            decoded,
                            drafts[d_idx - 1]["content"],
                            req,
                        )
                    except (ValueError, KeyError, TypeError) as exc:
                        msg = str(exc)
                        if msg.startswith("b_route_segmented_"):
                            stub_errors.append(msg)
                        continue
                if runtime.same_json(decoded, draft):
                    found.append((retained, data))
            if not found:
                if stub_errors:
                    raise ValueError(stub_errors[0])
                raise ValueError("b_route_repair_prior_not_original_paid_output")
            final_binding, final_materials = found[0]

        prior_gen_verified = False
        prior_frame_full = None
        if final_materials.get("repair_issue") is not None:
            if len(drafts) < 2:
                raise ValueError("b_route_repair_prior_chain_too_short")
            before_prior = _proposal_from_draft_prefix(frozen, drafts[:-1])
            runtime.check_repair_policy(
                {**final_materials, "prior_candidate": before_prior},
                required=True,
                frozen=frozen,
            )
            if runtime.repair_scope_errors(
                root,
                state,
                before_prior,
                prior_full,
                final_materials["repair_issue"],
                check_originals=check_originals,
            ):
                raise ValueError("b_route_repair_prior_scope_invalid")
            _verify_segmented_repair_origin(
                root,
                state,
                frozen,
                before_prior,
                final_materials,
                final_binding,
                seen=seen,
                _work=_work,
                check_originals=check_originals,
            )
            prior_gen_verified = True
            prior_frame_full = {
                "prior_candidate": before_prior,
                "repair_issue": final_materials["repair_issue"],
                "repair_scope_policy": final_materials["repair_scope_policy"],
                "repair_scope": final_materials["repair_scope"],
            }

        if issue.get("path") == "semantic-review":
            prior_sha = canonical_sha(prior_full)
            directive = runtime.reopen_directive(state, frozen, materials.get("generation", 1))
            full_obs = runtime.obligations(prior_full, frozen)
            rev_rows = [
                (num, retained, data)
                for num, retained, data in earlier
                if data["phase"] == "independent_admission"
                and data["proposal"]["proposal_sha256"] == prior_sha
            ]
            # Group contiguous/ordered review segments covering [0..len(full_obs))
            issues: list[dict] = []
            by_start: dict[int, list[tuple[int, dict, dict]]] = {}
            for num, retained, data in rev_rows:
                start_idx = data["root_request"]["obligation_range"][0]
                by_start.setdefault(start_idx, []).append((num, retained, data))
            for _, start_ret, start_data in by_start.get(0, []):
                chain_segs = [(start_ret, start_data)]
                cursor = start_data["root_request"]["obligation_range"][1]
                while cursor < len(full_obs):
                    next_candidates = [
                        (r, d)
                        for n, r, d in by_start.get(cursor, [])
                        if d["root_request"]["total_obligations"] == len(full_obs)
                    ]
                    if not next_candidates:
                        break
                    nxt_ret, nxt_data = next_candidates[-1]
                    chain_segs.append((nxt_ret, nxt_data))
                    cursor = nxt_data["root_request"]["obligation_range"][1]
                if cursor != len(full_obs):
                    continue
                agg_checks: list[dict] = []
                agg_reopen = None
                for s_idx, (s_ret, s_data) in enumerate(chain_segs):
                    if runtime.issue_account_policy(state) is not None:
                        if prior_frame_full is not None and prior_frame_full["repair_issue"].get("account_policy") is not None:
                            prior_base_proj = _compact_candidate_projection(prior_frame_full["prior_candidate"])
                            s_scoped, s_level = _validated_review_projection_level(s_data["root_request"])
                            if not s_scoped:
                                expected_s_prior = prior_base_proj
                            elif s_level == 1:
                                expected_s_prior = _scoped_review_proposal(
                                    prior_base_proj,
                                    s_data["obligations"],
                                    directive=directive if s_idx == 0 else None,
                                    level=1,
                                )
                            else:
                                expected_s_prior = _scoped_review_prior(
                                    prior_base_proj,
                                    prior_frame_full["repair_issue"],
                                    level=s_level,
                                )
                            if not runtime.same_json(s_data.get("prior_candidate"), expected_s_prior):
                                raise ValueError("b_route_review_issue_account_origin_changed")
                            runtime.check_review_origin_frame(
                                {**s_data, "prior_candidate": prior_frame_full["prior_candidate"]},
                                prior_frame_full,
                                generation_verified=prior_gen_verified,
                            )
                        else:
                            runtime.check_review_origin_frame(
                                s_data, prior_frame_full, generation_verified=prior_gen_verified
                            )
                    dec = decode_segmented_review_slice(
                        state,
                        frozen,
                        _verified_call_output(s_ret, readonly=True),
                        s_data["obligations"],
                        s_data["qualified_sources"],
                        proposal_sha256=prior_sha,
                        directive=directive if s_idx == 0 else None,
                    )
                    agg_checks.extend(dec["checks"])
                    if "reopen_reviews" in dec:
                        agg_reopen = dec["reopen_reviews"]
                if [c["id"] for c in agg_checks] != [ob["id"] for ob in full_obs]:
                    continue
                reopen_blk = [r["rationale"] for r in (agg_reopen or []) if r["verdict"] == "blocked"]
                blk_findings = list(
                    dict.fromkeys([c["rationale"] for c in agg_checks if c["verdict"] == "blocked"] + reopen_blk)
                )
                agg_rev = {
                    "schema_version": runtime.REVIEW,
                    "input_identity": runtime.descriptor(state)["input_identity"],
                    "runtime_identity": state["runtime_identity"],
                    "proposal_sha256": prior_sha,
                    "verdict": "blocked" if blk_findings else "approved",
                    "findings": blk_findings,
                    "checks": agg_checks,
                }
                if agg_reopen is not None:
                    agg_rev["reopen_reviews"] = agg_reopen
                first_data = chain_segs[0][1]
                origin_val = (
                    runtime.review_account_origin(
                        {**first_data, "prior_candidate": prior_frame_full["prior_candidate"]},
                        frozen,
                    )
                    if (
                        first_data.get("prior_candidate") is not None
                        and prior_frame_full is not None
                    )
                    else runtime.review_account_origin(first_data, frozen)
                )
                issues.extend(
                    runtime.account_review_issues(state, prior_full, frozen, agg_rev, origin=origin_val)
                )
        else:
            issues = runtime.admission_machine(root, state, prior_full, check_originals=check_originals)
        if not any(runtime.same_json(row, issue) for row in issues):
            raise ValueError("b_route_repair_issue_not_original_host_finding")
    finally:
        seen.remove(identity)


def segmented_proof_errors(
    root: Path, state: dict, proposal: dict, proof: dict, *, check_originals: bool = True
) -> list[str]:
    """Replay segmented admission proof, draft chain, repairs, session disjointness, and full review denominator."""
    import _b_route_planning_runtime as runtime

    try:
        frozen = runtime.frozen_input(root, state, check_originals=check_originals)
        expected_scopes = [runtime.scope_value(frozen)]
        records = proof["records"]
        if len(records) != 1 or proof["scopes"] != expected_scopes:
            raise ValueError("b_route_admission_scope_invalid")
        record = records[0]
        if record.get("kind") == "adoption":
            from _b_route_completed_reuse import replay_delta
            from _mvg_capability_recovery import verify_adoption_record

            run_dir = runtime.run_location(root, runtime.descriptor(state)["planner"], state["run_id"])
            if (
                canonical_sha(proof)
                != canonical_sha(runtime.admission_proof(state, proof["seed"], expected_scopes, records, proposal))
                or record.get("scope") != expected_scopes[0]
                or record.get("base_sha256") != canonical_sha(proof["seed"])
                or record.get("proposal_sha256") != canonical_sha(proposal)
                or record.get("record_sha256")
                != canonical_sha({key: value for key, value in record.items() if key != "record_sha256"})
                or canonical_sha(
                    replay_delta(
                        root,
                        state,
                        run_dir / "analysis-input",
                        proof["seed"],
                        record["delta"],
                        expected_scopes[0],
                        check_originals=check_originals,
                    )
                )
                != canonical_sha(proposal)
            ):
                raise ValueError("b_route_adoption_chain_changed")
            verify_adoption_record(
                root,
                state,
                run_dir / "analysis-input",
                expected_scopes[0],
                proof["seed"],
                proposal,
                record,
                check_originals=check_originals,
            )
            return []

        if (
            canonical_sha(proof)
            != canonical_sha(runtime.admission_proof(state, proof["seed"], expected_scopes, records, proposal))
            or record["scope"] != expected_scopes[0]
            or record["base_sha256"] != canonical_sha(proof["seed"])
            or record["proposal_sha256"] != canonical_sha(proposal)
            or record["record_sha256"] != canonical_sha({k: v for k, v in record.items() if k != "record_sha256"})
            or canonical_sha(runtime.merge(proof["seed"], record["delta"])) != canonical_sha(proposal)
        ):
            raise ValueError("b_route_admission_chain_changed")
        if proposal["provenance"]["kind"] != "model_draft":
            raise ValueError("b_route_admission_requires_real_model_draft")
        directive = runtime.reopen_directive(state, frozen, record["delta"]["lineage"]["generation"])
        if record["proof"].get("reopen_context") != directive:
            raise ValueError("b_route_admission_reopen_context_changed")

        verify_segmented_proof_reservations(root, state, proof, check_originals=check_originals)

        routing_file = Path(root) / "docs/workflows/llm-routing.json"
        routing_sha = file_sha(routing_file) if routing_file.is_file() else None
        prop_sha = canonical_sha(proposal)
        prf_sha = canonical_sha(proof)
        frozen_reopen_sha = canonical_sha(frozen.get("reopen") or {})
        state_reopen_sha = canonical_sha(state.get("reopen") or {})
        proof_cache_key = (
            str(root),
            state.get("runtime_identity"),
            state.get("run_id"),
            frozen["input_identity"],
            check_originals,
            prop_sha,
            prf_sha,
            frozen_reopen_sha,
            state_reopen_sha,
            routing_sha,
        )
        cached_errs = _PROOF_ERRORS_CACHE.get(proof_cache_key)
        if cached_errs is None and not check_originals:
            cached_errs = _PROOF_ERRORS_CACHE.get(
                (
                    str(root),
                    state.get("runtime_identity"),
                    state.get("run_id"),
                    frozen["input_identity"],
                    True,
                    prop_sha,
                    prf_sha,
                    frozen_reopen_sha,
                    state_reopen_sha,
                    routing_sha,
                )
            )
        if cached_errs is not None:
            return list(cached_errs)

        generation_calls = record["delta"]["generation_calls"]
        drafts = proposal["provenance"]["draft_chain"]
        if len(generation_calls) != len(drafts):
            raise ValueError("b_route_generation_execution_incomplete")
        planning.validate_draft_chain(frozen, drafts)

        review_bindings = record["proof"].get("review_executions") or [record["execution"]]
        _enforce_disjoint_sessions(
            root,
            [*generation_calls, *review_bindings],
            context_label="candidate_proof",
        )

        saw_repair = False
        generation_origin_verified = False
        last_repair_frame_full: dict | None = None
        origin_work = runtime._RepairOriginWork(state)

        for idx, (draft, binding) in enumerate(zip(drafts, generation_calls)):
            materials = verify_segmented_materials(binding, state, frozen, readonly=True)
            raw_decoded_draft = _cached_decode_generation_carrier(_verified_call_output(binding, readonly=True))
            if materials.get("repair_issue") is not None and idx >= 1:
                expected_draft = _expected_repair_draft(
                    raw_decoded_draft,
                    _proposal_from_draft_prefix(frozen, drafts[:idx])["content"],
                    materials["root_request"],
                )
            else:
                expected_draft = raw_decoded_draft
            if canonical_sha(expected_draft) != canonical_sha(draft):
                raise ValueError("b_route_generation_draft_execution_changed")
            req_bytes = len(binding["request_payload"].encode("utf-8"))
            _assert_under_70k(
                max(req_bytes, int(binding["measurement"]["request_bytes"])),
                frozen,
                f"segmented_generation_replay_{idx + 1}",
            )
            req = materials["root_request"]
            expected_parents = [codec.canonical_digest(d) for d in drafts[:idx]]
            if (
                req["ordinal"] != idx + 1
                or req["parent_draft_identities"] != expected_parents
                or materials["lineage_identity"] != record["delta"]["lineage"]["identity"]
                or materials["lineage_context"] != record["context"]
            ):
                raise ValueError("b_route_segmented_generation_chain_mismatch")

            if materials.get("repair_issue") is not None:
                saw_repair = True
                if (
                    idx < 1
                    or draft["stage"] != "synthesis"
                    or req.get("synthesis_role") != "bounded_repair"
                    or not isinstance(materials.get("prior_candidate"), dict)
                ):
                    raise ValueError("b_route_segmented_repair_step_invalid")
                prior_full = _proposal_from_draft_prefix(frozen, drafts[:idx])
                after_full = _proposal_from_draft_prefix(frozen, drafts[: idx + 1])
                if not req.get("slim_repair_fallback") and not runtime.same_json(
                    after_full["content"], draft["content"]
                ):
                    raise ValueError("b_route_segmented_unsolicited_repair_stub")
                expected_prior_proj = (
                    _slim_repair_prior_projection(
                        prior_full,
                        frozen,
                        materials["repair_issue"],
                        subfield_slim=bool(req.get("slim_repair_subfield")),
                    )
                    if req.get("slim_repair_fallback")
                    else _compact_candidate_projection(prior_full)
                )
                if not runtime.same_json(materials["prior_candidate"], expected_prior_proj):
                    raise ValueError("b_route_segmented_repair_prior_projection_changed")
                full_mat = {**materials, "prior_candidate": prior_full}
                runtime.check_repair_policy(full_mat, required=True, frozen=frozen)
                scope_errs = runtime.repair_scope_errors(
                    root,
                    state,
                    prior_full,
                    after_full,
                    materials["repair_issue"],
                    check_originals=check_originals,
                )
                if scope_errs:
                    raise ValueError("b_route_repair_replay_rejected:" + ";".join(scope_errs))
                _verify_segmented_repair_origin(
                    root,
                    state,
                    frozen,
                    prior_full,
                    materials,
                    binding,
                    _work=origin_work,
                    check_originals=check_originals,
                )
                generation_origin_verified = True
                last_repair_frame_full = {
                    "prior_candidate": prior_full,
                    "repair_issue": materials["repair_issue"],
                    "repair_scope_policy": materials["repair_scope_policy"],
                    "repair_scope": materials["repair_scope"],
                }
            else:
                if saw_repair:
                    raise ValueError("b_route_segmented_non_repair_after_repair_forbidden")
                runtime.check_repair_policy(materials, required=True, frozen=frozen)

        prop_sha = canonical_sha(proposal)
        proposal_proj = _compact_candidate_projection(proposal)
        replayed_checks: list[dict] = []
        replayed_reopen = None
        first_review_materials: dict | None = None
        for seg_idx, rev_binding in enumerate(review_bindings):
            rev_req_bytes = len(rev_binding["request_payload"].encode("utf-8"))
            _assert_under_70k(
                max(rev_req_bytes, int(rev_binding["measurement"]["request_bytes"])),
                frozen,
                f"segmented_review_replay_{seg_idx + 1}",
            )
            rev_mat = verify_segmented_materials(rev_binding, state, frozen, readonly=True)
            if seg_idx == 0:
                first_review_materials = rev_mat
            seg_directive = directive if seg_idx == 0 else None
            scoped_flag, proj_level = _validated_review_projection_level(rev_mat["root_request"])
            expected_rev_prop = (
                _scoped_review_proposal(
                    proposal_proj,
                    rev_mat["obligations"],
                    directive=seg_directive,
                    level=proj_level,
                    seg_sources=rev_mat["qualified_sources"],
                )
                if scoped_flag
                else proposal_proj
            )
            if (
                rev_mat["phase"] != "independent_admission"
                or rev_mat["proposal"]["proposal_sha256"] != prop_sha
                or not runtime.same_json(rev_mat["proposal"], expected_rev_prop)
                or rev_mat["lineage_identity"] != record["delta"]["lineage"]["identity"]
            ):
                raise ValueError("b_route_segmented_review_materials_mismatch")

            if runtime.issue_account_policy(state) is not None:
                if (
                    last_repair_frame_full is not None
                    and last_repair_frame_full["repair_issue"].get("account_policy") is not None
                ):
                    prior_base_proj = _compact_candidate_projection(last_repair_frame_full["prior_candidate"])
                    if not scoped_flag:
                        expected_rev_prior = prior_base_proj
                    elif proj_level == 1:
                        expected_rev_prior = _scoped_review_proposal(
                            prior_base_proj, rev_mat["obligations"], directive=seg_directive, level=1
                        )
                    else:
                        expected_rev_prior = _scoped_review_prior(
                            prior_base_proj, last_repair_frame_full["repair_issue"], level=proj_level
                        )
                    if not runtime.same_json(rev_mat.get("prior_candidate"), expected_rev_prior):
                        raise ValueError("b_route_review_issue_account_origin_changed")
                    runtime.check_review_origin_frame(
                        {**rev_mat, "prior_candidate": last_repair_frame_full["prior_candidate"]},
                        last_repair_frame_full,
                        generation_verified=generation_origin_verified,
                    )
                else:
                    runtime.check_review_origin_frame(
                        rev_mat, last_repair_frame_full, generation_verified=generation_origin_verified
                    )

            decoded_slice = decode_segmented_review_slice(
                state,
                frozen,
                _verified_call_output(rev_binding, readonly=True),
                rev_mat["obligations"],
                rev_mat["qualified_sources"],
                proposal_sha256=prop_sha,
                directive=seg_directive,
            )
            replayed_checks.extend(decoded_slice["checks"])
            if "reopen_reviews" in decoded_slice:
                replayed_reopen = decoded_slice["reopen_reviews"]

        full_obligations = runtime.obligations(proposal, frozen)
        if [c["id"] for c in replayed_checks] != [ob["id"] for ob in full_obligations]:
            raise ValueError("b_route_segmented_replayed_review_denominator_mismatch")
        reopen_blocked = [
            r["rationale"] for r in (replayed_reopen or []) if r["verdict"] == "blocked"
        ]
        blocked_findings = list(
            dict.fromkeys(
                [c["rationale"] for c in replayed_checks if c["verdict"] == "blocked"]
                + reopen_blocked
            )
        )
        expected_review = {
            "schema_version": runtime.REVIEW,
            "input_identity": runtime.descriptor(state)["input_identity"],
            "runtime_identity": state["runtime_identity"],
            "proposal_sha256": prop_sha,
            "verdict": "blocked" if blocked_findings else "approved",
            "findings": blocked_findings,
            "checks": replayed_checks,
        }
        if replayed_reopen is not None:
            expected_review["reopen_reviews"] = replayed_reopen
        if (
            record["proof"]["runtime_identity"] != state["runtime_identity"]
            or record["proof"]["obligations"] != full_obligations
            or record["proof"]["lineage_context"] != record["context"]
            or record["delta"]["lineage"]["context"] != record["context"]
            or canonical_sha(expected_review) != canonical_sha(record["proof"]["review"])
        ):
            raise ValueError("b_route_independent_proof_execution_changed")

        review_origin = (
            runtime.review_account_origin(
                {**first_review_materials, "prior_candidate": last_repair_frame_full["prior_candidate"]},
                frozen,
            )
            if (
                first_review_materials is not None
                and first_review_materials.get("prior_candidate") is not None
                and last_repair_frame_full is not None
            )
            else (
                runtime.review_account_origin(first_review_materials, frozen)
                if first_review_materials is not None
                else None
            )
        )
        final_errs = runtime.admission_machine(
            root, state, proposal, check_originals=check_originals
        ) + runtime.account_review_issues(
            state, proposal, frozen, record["proof"]["review"], origin=review_origin
        )
        _bounded_put(_PROOF_ERRORS_CACHE, proof_cache_key, list(final_errs), 32)
        return final_errs
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, IndexError) as exc:
        return ["b_route_admission_invalid:" + str(exc)]

