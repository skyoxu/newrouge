"""Read-only B-route executable three-tier VerificationScope (Story 4.2).

This module synthesizes a comparable verification contract from:

* a live-revalidated (or freshly computed) Story 4.1 impact proof,
* the current delivery boundary (in-scope plans, tasks and Flows),
* committed catalog plans and Stage-5 bindings,
* cumulative baseline MVG manifests plus active manifests, never cropped by an
  older or smaller manifest or by the current runnable state, and
* the common Story 3.5 InputSet for every in-scope task.

Every obligation is classified item by item into ``existing_required``
(affected old regression, kept in full), ``current_new`` (new or incomplete
work of the current delivery, pending/blocked until real) and
``out_of_scope_future`` (impacted future responsibility, never claimed as
passed). A single Flow may carry several tiers. Reclassifying an active
baseline Flow or a failing regression as planned/future, or removing an
obligation because a test failed, cannot launch, is missing or is flaky, is
rejected. Executable tests, pending work, manual checks and legal non-Flow
verification are separated without fabricating tests, script entrypoints or
PASS claims.

The scope only authorizes verification responsibility. It never runs tests,
mutates Task status, moves publish pointers, or enables the B route.
"""

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import copy
import datetime
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Iterable

import _b_route_codec as codec
import _b_route_impact_closure as closure
import _b_route_input_set as input_set
import _b_route_schema_resources as schema_resources
import _mvg_manifest as mvg_manifest


SCHEMA = "newrouge.b-route-verification-scope.v1"
REVALIDATION_SCHEMA = "newrouge.b-route-verification-scope-revalidation.v1"
VALIDATION_SCHEMA = "newrouge.b-route-verification-scope-validation.v1"
DELTA_SCHEMA = "newrouge.b-route-verification-scope-delta.v1"
PLAN_SCHEMA = "newrouge.b-route-plan.v1"
BINDING_SCHEMA = "newrouge.b-route-binding.v1"
MANIFEST_DIR = closure.MANIFEST_DIR
CATALOG_PATH = closure.CATALOG_PATH

TIERS = ("existing_required", "current_new", "out_of_scope_future")
TIER_RANK = {tier: index for index, tier in enumerate(TIERS)}
CURRENT_TIERS = frozenset({"existing_required", "current_new"})
OPEN_STATUSES = frozenset({"pending", "blocked"})
FORBIDDEN_REASON_TOKENS = frozenset({"broken", "skip", "skipped", "na", "todo", "green", "flaky", "flake",
                                     "timeout", "crash", "fail", "failed", "failure"})
FORBIDDEN_REASON_STEMS = ("fail", "crash", "flak", "timeout", "timedout", "skipped", "workaround", "unlaunchable",
                          "cannotlaunch", "cannotstart", "cannotrun", "cantlaunch", "cantstart", "wontstart",
                          "wontlaunch", "missingtest", "unimplementedtest", "testmissing", "notestexists")
FORBIDDEN_REASON_PHRASES = ("n_a", "no_test", "can_t_launch", "can_t_start", "won_t_start", "not_launch")
MIN_DELTA_REASON_CHARS = 12
GD_LOAD_RE = re.compile(r'\b(?:preload|load)\(\s*"res://([^"]+)"\s*\)')
DELTA_ACTIONS = frozenset({"reclassify", "retire", "remove", "shrink"})
WEAKENING_ACTIONS = frozenset({"retire", "remove", "shrink"})
DELTA_TARGET_TIERS = frozenset(TIERS) | {"planned"}
FUTURE_FOLLOW_UP = ("update_stage4_or_stage5_binding_when_in_scope", "implement_and_verify_before_flow_closure")
SCRIPT_SUFFIXES = (".py", ".ps1")
TRIVIAL_RATIONALES = frozenset({"", "n/a", "na", "none", "tbd", "todo", "-", "null", "r"})
MIN_RATIONALE_LENGTH = 8
EVIDENCE_LEVELS = {"dotnet": ("domain-integration",), "gdunit": ("scene-method", "engine-input")}
DEFAULT_LEVEL = {"dotnet": "domain-integration", "gdunit": "scene-method"}
DEFINITION_FIELDS = {"rule": "rules", "state": "states", "command": "commands"}
REF_KEYS = frozenset({"path", "schema_version", "entity_id", "revision", "digest", "verification_mode", "codec_version"})
VOLATILE_FIELDS = frozenset({"ok", "status", "operation", "reason_code", "diagnostics", "report_path", "metrics",
                             "scope_id", "generated_at"})
INVALID_ARGUMENT_CODES = closure.INVALID_ARGUMENT_CODES | {"invalid_enum"}

INVARIANT_FLAGS = {
    "scope_authorizes_verification_only": True,
    "task_completed": False,
    "flow_completed": False,
    "milestone_completed": False,
    "runtime_verified": False,
    "task_status_mutated": False,
    "publish_pointer_mutated": False,
    "default_b_enabled": False,
}


def _err(code: codec.ReasonCode, expected: Any, actual: Any = None, entity: str | None = None,
         stage: codec.Stage = codec.Stage.CONTENT) -> codec.CodecError:
    return codec.CodecError(codec.Diagnostic(code, stage, entity, expected, actual, None))


def _elapsed(started: float) -> float:
    return round(max(0.0, time.monotonic() - started), 6)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _impl(test: Any) -> bool:
    return type(test) is dict and test.get("state", test.get("status")) == "implemented"


def _planned_flow(flow: dict) -> bool:
    return any(flow.get(k) in ("planned", "future", "out_of_scope_future")
               for k in ("state", "status", "availability"))


def _int_or_none(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _strings(values: Iterable[Any]) -> list[str]:
    return sorted({v for v in values if type(v) is str and v.strip()})


def _disguised_reason(reason: str) -> bool:
    """Return True when a delta reason is trivial or disguises a failing/missing/unlaunchable test as a scope change."""
    if len(re.sub(r"\s", "", reason)) < MIN_DELTA_REASON_CHARS:
        return True
    tokens = re.findall(r"[a-z0-9]+", reason.lower())
    if FORBIDDEN_REASON_TOKENS & set(tokens):
        return True
    compact = "".join(tokens)
    if any(stem in compact for stem in FORBIDDEN_REASON_STEMS):
        return True
    joined = "_" + "_".join(tokens) + "_"
    return any(f"_{phrase}_" in joined or joined.startswith(f"_{phrase}") for phrase in FORBIDDEN_REASON_PHRASES) \
        or "n/a" in reason.lower()


def _manual_checks(value: Any) -> list[str]:
    if type(value) is str and value.strip():
        return [value.strip()]
    if type(value) is list:
        return _strings(value)
    if type(value) is dict and value.get("applicability", "applicable") == "applicable":
        checks = _strings(value.get("checks") or value.get("responsibilities") or [])
        if not checks and type(value.get("responsibility")) is str and value["responsibility"].strip():
            checks = [value["responsibility"].strip()]
        return checks
    return []


# ---------------------------------------------------------------------------
# Context and authoritative record loading
# ---------------------------------------------------------------------------

class _Ctx:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.gaps: list[dict[str, str]] = []
        self.plans: dict[str, dict[str, Any]] = {}
        self.bindings: dict[str, dict[str, Any]] = {}
        self.binding_docs: list[dict[str, Any]] = []
        self.plan_refs: list[dict[str, Any]] = []
        self.binding_refs: list[dict[str, Any]] = []
        self.manifests: dict[str, dict[str, Any]] = {}
        self.baseline_paths: list[str] = []
        self.active_paths: list[str] = []
        self.file_cache: dict[str, str] = {}
        self.flow_evidence_cache: dict[str, str] = {}

    def gap(self, entity: str, reason: str) -> None:
        item = {"entity": entity, "reason": reason}
        if item not in self.gaps:
            self.gaps.append(item)

    def read_json(self, rel: str, *, allow_logs: bool = False) -> Any:
        """Return (doc, raw), None when absent, or False when unreadable/unsafe."""
        try:
            return closure._read_json(self.root, rel, allow_logs=allow_logs)
        except codec.CodecError:
            return False

    def file_digest(self, rel: str) -> str:
        if rel not in self.file_cache:
            value = "absent"
            if closure._file_exists(self.root, rel):
                try:
                    raw = closure._read_bytes(self.root, rel)
                    value = codec.raw_digest(raw) if raw is not None else "absent"
                except codec.CodecError:
                    value = "unreadable"
            self.file_cache[rel] = value
        return self.file_cache[rel]

    def exists(self, rel: str) -> bool:
        return self.file_digest(rel) not in ("absent", "unreadable")

    def nonempty(self, rel: str) -> bool:
        """Live verification files must exist and carry non-whitespace content."""
        if not self.exists(rel):
            return False
        try:
            raw = closure._read_bytes(self.root, rel)
        except codec.CodecError:
            return False
        return bool(raw is not None and raw.strip())


def _ref_ok(ref: Any, schema: str) -> bool:
    if type(ref) is not dict or set(ref) != REF_KEYS or ref.get("schema_version") != schema:
        return False
    if type(ref["revision"]) is not int or ref["revision"] < 1:
        return False
    if type(ref["digest"]) is not str or not closure.DIGEST_RE.fullmatch(ref["digest"]):
        return False
    if any(type(ref[k]) is not str or not ref[k].strip() for k in ("path", "entity_id")):
        return False
    mode, version = ref["verification_mode"], ref["codec_version"]
    return (mode == "raw" and version is None) or (mode == "canonical" and version == codec.CODEC_VERSION)


def _load_records(ctx: _Ctx) -> None:
    loaded = ctx.read_json(CATALOG_PATH)
    if loaded is None:
        ctx.gap(f"catalog:{CATALOG_PATH}", "catalog_missing")
        return
    if loaded is False or type(loaded[0]) is not dict or loaded[0].get("schema_version") != closure.CATALOG_SCHEMA:
        ctx.gap(f"catalog:{CATALOG_PATH}", "catalog_unreadable")
        return
    plan_refs: dict[str, dict] = {}
    binding_refs: dict[tuple[str, str, int], dict] = {}
    for head in loaded[0].get("scope_heads") or []:
        if type(head) is not dict:
            ctx.gap(f"catalog:{CATALOG_PATH}", "malformed_catalog_scope_head")
            continue
        for ref in head.get("plan_refs") or []:
            if not _ref_ok(ref, PLAN_SCHEMA):
                ctx.gap(f"catalog:{CATALOG_PATH}", "malformed_catalog_plan_ref")
                continue
            current = plan_refs.get(ref["entity_id"])
            if current is None or ref["revision"] > current["revision"]:
                plan_refs[ref["entity_id"]] = ref
        for ref in head.get("binding_refs") or []:
            if not _ref_ok(ref, BINDING_SCHEMA):
                ctx.gap(f"catalog:{CATALOG_PATH}", "malformed_catalog_binding_ref")
                continue
            binding_refs[(ref["entity_id"], ref["path"], ref["revision"])] = ref
    for pid in sorted(plan_refs):
        rel = closure._try_path(plan_refs[pid]["path"])
        loaded_plan = ctx.read_json(rel) if rel else False
        if not loaded_plan or type(loaded_plan[0]) is not dict:
            ctx.gap(f"plan:{pid}", "plan_unreadable")
            continue
        doc, raw = loaded_plan
        if doc.get("schema_version") != PLAN_SCHEMA or doc.get("plan_id") != pid:
            ctx.gap(f"plan:{pid}", "plan_identity_mismatch")
            continue
        ctx.plans[pid] = {"plan_id": pid, "revision": _int_or_none(doc.get("revision")), "path": rel,
                          "raw_digest": codec.raw_digest(raw), "doc": doc}
    for key in sorted(binding_refs):
        pid = key[0]
        rel = closure._try_path(binding_refs[key]["path"])
        loaded_binding = ctx.read_json(rel) if rel else False
        if not loaded_binding or type(loaded_binding[0]) is not dict:
            ctx.gap(f"binding:{pid}:{key[1]}", "binding_unreadable")
            continue
        doc, raw = loaded_binding
        if doc.get("schema_version") != BINDING_SCHEMA or doc.get("plan_id") != pid:
            ctx.gap(f"binding:{pid}:{key[1]}", "binding_identity_mismatch")
            continue
        rec = {"plan_id": pid, "stage": doc.get("stage") if type(doc.get("stage")) is str else "unknown",
               "binding_revision": _int_or_none(doc.get("binding_revision")), "path": rel,
               "raw_digest": codec.raw_digest(raw), "doc": doc}
        ctx.binding_docs.append(rec)
        if rec["stage"] == "5":
            current = ctx.bindings.get(pid)
            if current is None or (rec["binding_revision"] or 0) >= (current["binding_revision"] or 0):
                ctx.bindings[pid] = rec
    ctx.plan_refs = [plan_refs[p] for p in sorted(plan_refs)]
    ctx.binding_refs = [binding_refs[k] for k in sorted(binding_refs)]


def _load_manifests(ctx: _Ctx, active: list[str], cumulative: list[str]) -> None:
    files, _dirs, safe = closure._safe_listdir(ctx.root, MANIFEST_DIR)
    if not safe:
        ctx.gap(f"manifest_dir:{MANIFEST_DIR}", "manifest_dir_unsafe")
    baseline = {f"{MANIFEST_DIR}/{name}" for name in files if name.endswith(".json")} | set(cumulative)
    bound: set[str] = set()
    for pid in sorted(ctx.bindings):
        for ref in ctx.bindings[pid]["doc"].get("manifest_refs") or []:
            paths, valid = closure._owned_paths(ref)
            if not valid:
                ctx.gap(f"plan:{pid}", "unresolved_manifest_ref")
            bound.update(paths)
    active_set = set(active) | bound
    for rel in sorted(baseline | active_set):
        loaded = ctx.read_json(rel)
        if not loaded or type(loaded[0]) is not dict or loaded[0].get("schema_version") != closure.MVG_SCHEMA:
            ctx.gap(f"manifest:{rel}", "manifest_unreadable")
            continue
        doc, raw = loaded
        mvg_id = doc.get("mvg_id") if type(doc.get("mvg_id")) is str and doc["mvg_id"].strip() else Path(rel).stem
        roles = (["active"] if rel in active_set else []) + (["baseline"] if rel in baseline else [])
        ctx.manifests[rel] = {"path": rel, "mvg_id": mvg_id, "sha256": mvg_manifest.manifest_sha256(raw),
                              "roles": roles, "doc": doc}
    ctx.baseline_paths = sorted(baseline)
    ctx.active_paths = sorted(active_set)


# ---------------------------------------------------------------------------
# Indexes
# ---------------------------------------------------------------------------

class _Index:
    def __init__(self) -> None:
        self.flows: dict[str, dict[str, Any]] = {}
        self.tests: dict[str, list[dict[str, Any]]] = {}
        self.test_flows: dict[str, set[str]] = {}
        self.baseline_active_flows: set[str] = set()
        self.baseline_impl_tests: set[str] = set()
        self.plan_flow_owner: dict[str, tuple[str, dict]] = {}
        self.plan_flows: dict[str, list[str]] = {}
        self.plan_requirements: dict[str, list[str]] = {}
        self.mapping_flows_by_task: dict[int, set[str]] = {}
        self.mapping_tasks_by_flow: dict[str, set[int]] = {}
        self.mapping_reqs_by_task: dict[int, set[str]] = {}
        self.binding_flows_by_plan: dict[str, set[str]] = {}
        self.flow_plans: dict[str, set[str]] = {}
        self.binding_obligations: list[dict[str, Any]] = []
        self.impl_objects: list[dict[str, Any]] = []


def _flow_info(index: _Index, fid: str) -> dict[str, Any]:
    return index.flows.setdefault(fid, {"entries": [], "test_ids": set(), "task_ids": set(), "requirement_ids": set(),
                                        "planned_in": set(), "active_in": set(), "files": set(), "manifests": set()})


def _index_manifests(ctx: _Ctx, index: _Index) -> None:
    for rel in sorted(ctx.manifests):
        manifest = ctx.manifests[rel]
        doc = manifest["doc"]
        baseline = "baseline" in manifest["roles"]
        local_tests: dict[str, dict] = {}
        for test in doc.get("tests") or []:
            if type(test) is dict and type(test.get("id")) is str and test["id"].strip():
                local_tests[test["id"]] = test
                index.tests.setdefault(test["id"], []).append({"manifest": rel, "doc": test, "baseline": baseline})
        for flow in doc.get("flows") or []:
            if type(flow) is not dict or type(flow.get("id")) is not str or not flow["id"].strip():
                continue
            fid = flow["id"]
            info = _flow_info(index, fid)
            planned = _planned_flow(flow)
            test_ids = closure._str_ids(flow.get("test_ids"))
            for handoff in flow.get("handoffs") or []:
                if type(handoff) is not dict:
                    continue
                test_ids += [t for t in closure._str_ids(handoff.get("test_ids")) if t not in test_ids]
                contract = closure._try_path(handoff.get("contract_ref"))
                if contract:
                    info["files"].add(contract)
            for value in flow.get("source_paths") or []:
                path = closure._try_path(value)
                if path:
                    info["files"].add(path)
            info["entries"].append({"manifest": rel, "doc": flow, "test_ids": list(test_ids)})
            info["test_ids"].update(test_ids)
            info["task_ids"].update(int(t) for t in closure._task_ids(flow.get("task_ids")))
            info["requirement_ids"].update(closure._str_ids(flow.get("requirement_ids")))
            info["manifests"].add(rel)
            if planned:
                info["planned_in"].add(rel)
            for test_id in test_ids:
                index.test_flows.setdefault(test_id, set()).add(fid)
                # Implemented baseline tests are indexed even when the owning Flow was (re)marked planned in place,
                # so an in-place planned reclassification can never hide a cumulative regression.
                if baseline and _impl(local_tests.get(test_id)):
                    index.baseline_impl_tests.add(test_id)
                    if not planned:
                        info["active_in"].add(rel)
    index.baseline_active_flows = {fid for fid, info in index.flows.items() if info["active_in"]}


def _index_records(ctx: _Ctx, index: _Index) -> None:
    for pid in sorted(ctx.plans):
        doc = ctx.plans[pid]["doc"]
        definitions = doc.get("definitions") if type(doc.get("definitions")) is dict else {}
        index.plan_flows[pid] = []
        for flow in definitions.get("flows") or []:
            if type(flow) is dict and type(flow.get("id")) is str and flow["id"].strip():
                index.plan_flows[pid].append(flow["id"])
                index.plan_flow_owner.setdefault(flow["id"], (pid, flow))
                index.flow_plans.setdefault(flow["id"], set()).add(pid)
        index.plan_requirements[pid] = _strings(item.get("requirement_id") for item in doc.get("requirements") or []
                                                if type(item) is dict)
    for pid in sorted(ctx.bindings):
        binding = ctx.bindings[pid]
        doc = binding["doc"]
        flows_here = index.binding_flows_by_plan.setdefault(pid, set())
        for mapping in doc.get("task_mappings") or []:
            if type(mapping) is not dict:
                continue
            tids = closure._task_ids([mapping.get("task_id")])
            if not tids:
                continue
            tid = int(tids[0])
            for fid in closure._str_ids(mapping.get("flow_ids")):
                index.mapping_flows_by_task.setdefault(tid, set()).add(fid)
                index.mapping_tasks_by_flow.setdefault(fid, set()).add(tid)
                index.flow_plans.setdefault(fid, set()).add(pid)
                flows_here.add(fid)
            index.mapping_reqs_by_task.setdefault(tid, set()).update(closure._str_ids(mapping.get("requirement_ids")))
        for item in doc.get("obligations") or []:
            if type(item) is not dict or type(item.get("id")) is not str or not item["id"].strip():
                continue
            meta5 = closure._tag_payload(item.get("responsibility"), closure.STAGE5_OBL_PREFIX,
                                         (closure.STAGE4_OBL_PREFIX,))
            meta4 = closure._tag_payload(item.get("responsibility"), closure.STAGE4_OBL_PREFIX,
                                         (closure.STAGE5_OBL_PREFIX,))
            if meta5.get("__malformed__") or meta4.get("__malformed__"):
                ctx.gap(f"binding_obligation:{pid}:{item['id']}", "malformed_obligation_metadata")
            category = meta5.get("category")
            if category is not None and category not in TIERS:
                ctx.gap(f"binding_obligation:{pid}:{item['id']}", "unknown_obligation_category")
                category = None
            future_flows = set(closure._str_ids(meta5.get("out_of_scope_future_flow_ids")))
            flow_ids = list(dict.fromkeys(closure._str_ids(item.get("flow_ids")) + closure._meta_ids(meta5, "flow_ids")
                                          + closure._meta_ids(meta4, "flow_ids")))
            test_ids = list(dict.fromkeys(closure._str_ids(item.get("test_ids")) + closure._meta_ids(meta5, "test_ids")
                                          + closure._meta_ids(meta4, "test_ids")))
            paths: list[str] = []
            refs_valid = True
            for ref in item.get("verification_refs") or []:
                found, valid = closure._owned_paths(ref)
                paths.extend(found)
                refs_valid = refs_valid and valid
            record = {"plan_id": pid, "id": item["id"], "doc": item, "category": category,
                      "flow_ids": flow_ids, "future_flow_ids": sorted(future_flows), "test_ids": test_ids,
                      "requirement_ids": closure._str_ids(item.get("requirement_ids")),
                      "verification_paths": sorted(set(paths)), "verification_refs_valid": refs_valid,
                      "binding_revision": binding["binding_revision"],
                      "manual_checks": _strings(_manual_checks(meta5.get("human_verification"))
                                                + _manual_checks(meta4.get("human_verification"))
                                                + _manual_checks(item.get("human_verification")))}
            index.binding_obligations.append(record)
            for fid in flow_ids:
                index.flow_plans.setdefault(fid, set()).add(pid)
                if category != "out_of_scope_future" and fid not in future_flows:
                    flows_here.add(fid)
            for test_id in test_ids:
                for fid in flow_ids:
                    index.test_flows.setdefault(test_id, set()).add(fid)
        for item in doc.get("implementation_objects") or []:
            if type(item) is not dict or type(item.get("id")) is not str or not item["id"].strip():
                continue
            target_paths, target_valid = closure._owned_paths(item.get("target_ref")) \
                if item.get("target_ref") is not None else ([], False)
            index.impl_objects.append({
                "plan_id": pid, "id": item["id"], "existing": item.get("availability") == "existing",
                "responsible": sorted({int(t) for t in closure._task_ids(item.get("responsible_task_ids"))}),
                "target_paths": sorted(set(target_paths)), "target_valid": target_valid, "doc": item,
                "binding_revision": binding["binding_revision"]})


def _guard_reclassification(ctx: _Ctx, index: _Index) -> None:
    """Reject planned/future reclassification of active baseline Flows or implemented baseline regressions."""
    for fid in sorted(index.baseline_active_flows):
        planned = sorted(index.flows[fid]["planned_in"])
        if planned:
            raise _err(codec.ReasonCode.CONFLICT,
                       "active baseline Flow is never reclassified as planned by a manifest candidate",
                       {"flow_id": fid, "declared_planned_in": planned}, entity=f"flow:{fid}")
    for test_id in sorted(index.baseline_impl_tests):
        downgraded = sorted(e["manifest"] for e in index.tests.get(test_id, []) if not _impl(e["doc"]))
        if downgraded:
            raise _err(codec.ReasonCode.CONFLICT,
                       "implemented baseline regression test is never reclassified as planned",
                       {"test_id": test_id, "declared_planned_in": downgraded}, entity=f"test:{test_id}")
    for fid in sorted(index.flows):
        for entry in index.flows[fid]["entries"]:
            if not _planned_flow(entry["doc"]):
                continue
            owned = sorted(set(entry["test_ids"]) & index.baseline_impl_tests)
            if owned:
                raise _err(codec.ReasonCode.CONFLICT,
                           "a planned/future Flow never owns implemented cumulative baseline regression tests",
                           {"flow_id": fid, "declared_planned_in": entry["manifest"], "test_ids": owned},
                           entity=f"flow:{fid}")
    for obl in index.binding_obligations:
        if obl["category"] == "existing_required":
            planned = sorted(f for f in obl["flow_ids"] if f in index.flows and index.flows[f]["planned_in"])
            if planned:
                raise _err(codec.ReasonCode.CONFLICT,
                           "a Flow bound by a Stage-5 existing_required obligation is never marked planned/future",
                           {"binding_obligation": f"{obl['plan_id']}:{obl['id']}", "flow_ids": planned},
                           entity=f"binding_obligation:{obl['plan_id']}:{obl['id']}")
    for obl in index.binding_obligations:
        if obl["category"] != "out_of_scope_future" and not obl["future_flow_ids"]:
            continue
        future_flows = set(obl["future_flow_ids"]) | (set(obl["flow_ids"]) if obl["category"] == "out_of_scope_future"
                                                      else set())
        hit_flows = sorted(future_flows & index.baseline_active_flows)
        hit_tests = sorted(set(obl["test_ids"]) & index.baseline_impl_tests) \
            if obl["category"] == "out_of_scope_future" else []
        if hit_flows or hit_tests:
            raise _err(codec.ReasonCode.CONFLICT,
                       "existing_required baseline Flow/test is never downgraded to out_of_scope_future in a binding",
                       {"binding_obligation": f"{obl['plan_id']}:{obl['id']}", "flow_ids": hit_flows,
                        "test_ids": hit_tests}, entity=f"binding_obligation:{obl['plan_id']}:{obl['id']}")


# ---------------------------------------------------------------------------
# Evidence fingerprints
# ---------------------------------------------------------------------------

def _referenced_definitions(ctx: _Ctx, pid: str, flow: dict) -> list[list[Any]]:
    refs: set[tuple[str, str, str]] = set()

    def add(use: Any, default_kind: str | None = None) -> None:
        if type(use) is str and use.strip() and default_kind:
            refs.add((pid, default_kind, use))
        elif type(use) is dict:
            kind = use.get("kind") or default_kind
            ident = use.get("definition_id") or use.get("id")
            owner = use.get("owner_plan_id") if type(use.get("owner_plan_id")) is str else pid
            if kind in DEFINITION_FIELDS and type(ident) is str and ident.strip():
                refs.add((owner, kind, ident))

    for rule in flow.get("rule_ids") or []:
        add(rule, "rule")
    for use in list(flow.get("rule_uses") or []):
        add(use, "rule")
    for use in list(flow.get("state_owners") or []):
        add(use)
    graph = flow.get("graph") if type(flow.get("graph")) is dict else {}
    for node in graph.get("nodes") or []:
        if type(node) is dict:
            for use in [node.get("owner")] + list(node.get("command_uses") or []) + list(node.get("state_uses") or []):
                add(use)
    for link in list(graph.get("edges") or []) + list(flow.get("handoffs") or []):
        if type(link) is dict:
            for use in [link.get("owner")] + list(link.get("state_uses") or []) + list(link.get("command_uses") or []):
                add(use)
    result = []
    for owner, kind, ident in sorted(refs):
        plan = ctx.plans.get(owner)
        found = None
        if plan is not None:
            definitions = plan["doc"].get("definitions") if type(plan["doc"].get("definitions")) is dict else {}
            for item in definitions.get(DEFINITION_FIELDS[kind]) or []:
                if type(item) is dict and item.get("id") == ident:
                    found = item
                    break
        result.append([owner, kind, ident, found])
    return result


def _gd_helpers(ctx: _Ctx, rels: set[str]) -> set[str]:
    """Return GDScript preload/load helper files referenced by the given .gd files (one level deep)."""
    found: set[str] = set()
    for rel in sorted(rels):
        if not rel.endswith(".gd") or not ctx.exists(rel):
            continue
        try:
            raw = closure._read_bytes(ctx.root, rel)
        except codec.CodecError:
            continue
        for match in GD_LOAD_RE.finditer((raw or b"").decode("utf-8", "replace")):
            path = closure._try_path(match.group(1))
            if path:
                found.add(path)
    return found - rels


def _flow_evidence(ctx: _Ctx, index: _Index, fid: str) -> str:
    if fid in ctx.flow_evidence_cache:
        return ctx.flow_evidence_cache[fid]
    info = index.flows.get(fid)
    owner = index.plan_flow_owner.get(fid)
    files = set(info["files"]) if info else set()
    test_files = {closure._try_path(e["doc"].get("path")) for t in (info["test_ids"] if info else ())
                  for e in index.tests.get(t, [])} - {None}
    helpers = _gd_helpers(ctx, files | test_files)
    flow_tasks = set(info["task_ids"] if info else ()) | index.mapping_tasks_by_flow.get(fid, set())
    flow_plans = index.flow_plans.get(fid, set())
    impls = sorted(([i["plan_id"], i["doc"], {p: ctx.file_digest(p) for p in i["target_paths"]}]
                    for i in index.impl_objects if i["plan_id"] in flow_plans and set(i["responsible"]) & flow_tasks),
                   key=closure._dumps)
    pieces = {
        "flow_id": fid,
        "manifest_entries": sorted(([e["manifest"], e["doc"]] for e in info["entries"]), key=closure._dumps)
        if info else [],
        "files": {p: ctx.file_digest(p) for p in sorted(files)},
        "helper_files": {p: ctx.file_digest(p) for p in sorted(helpers)},
        "implementation_objects": impls,
        "plan_definition": [owner[0], owner[1]] if owner else None,
        "referenced_definitions": _referenced_definitions(ctx, owner[0], owner[1]) if owner else [],
        "binding_mappings": sorted(
            ([b["plan_id"], m] for b in ctx.bindings.values() for m in b["doc"].get("task_mappings") or []
             if type(m) is dict and fid in closure._str_ids(m.get("flow_ids"))), key=closure._dumps),
        "binding_obligations": sorted(
            ([o["plan_id"], o["doc"]] for o in index.binding_obligations if fid in o["flow_ids"]), key=closure._dumps),
    }
    ctx.flow_evidence_cache[fid] = codec.canonical_digest(pieces)
    return ctx.flow_evidence_cache[fid]


# ---------------------------------------------------------------------------
# Obligation construction
# ---------------------------------------------------------------------------

def _status_for(tier: str, evidence: str) -> str:
    if tier == "out_of_scope_future":
        return "tracked_future"
    if evidence == "ready":
        return "ready_to_execute"
    if evidence == "manual":
        return "manual_required"
    if evidence == "unimplemented":
        return "pending" if tier == "current_new" else "blocked"
    return "blocked"


def _make_obligation(*, oid: str, tier: str, evidence: str, kind: str, level: str, flow_ids: Iterable[str],
                     requirement_ids: Iterable[str], task_ids: Iterable[int], test_ids: Iterable[str],
                     ov_refs: Iterable[str], owner: dict, authority: dict, reasons: Iterable[str],
                     missing: Iterable[str], evidence_digest: str, extra: dict | None = None) -> dict[str, Any]:
    rec = {
        "obligation_id": oid,
        "tier": tier,
        "status": _status_for(tier, evidence),
        "blocking_current_delivery": tier in CURRENT_TIERS,
        "immediate_execution_required": tier in CURRENT_TIERS,
        "flow_ids": _strings(flow_ids),
        "requirement_ids": _strings(requirement_ids),
        "task_ids": sorted({int(t) for t in task_ids}),
        "test_ids": _strings(test_ids),
        "other_verification_refs": _strings(ov_refs),
        "semantic_owner": owner,
        "execution_kind": kind if tier in CURRENT_TIERS else "future_followup",
        "evidence_level": level,
        "follow_up_responsibilities": list(FUTURE_FOLLOW_UP) if tier == "out_of_scope_future" else [],
        "source_authority": authority,
        "claimed_passed": False,
        "classification_reasons": _strings(reasons),
        "missing_targets": _strings(missing),
        "input_fingerprint": "",
    }
    rec["_evidence"] = evidence
    rec["_base_kind"] = kind
    rec["_evidence_digest"] = evidence_digest
    rec["_extra"] = extra or {}
    return rec


def _authority(ctx: _Ctx, plan_id: str | None, manifest_rel: str | None) -> dict[str, Any]:
    plan = ctx.plans.get(plan_id) if plan_id else None
    binding = ctx.bindings.get(plan_id) if plan_id else None
    manifest = ctx.manifests.get(manifest_rel) if manifest_rel else None
    return {
        "plan_id": plan_id,
        "plan_revision": plan["revision"] if plan else None,
        "binding_revision": binding["binding_revision"] if binding else None,
        "manifest_id": manifest["mvg_id"] if manifest else None,
        "manifest_sha256": manifest["sha256"] if manifest else None,
    }


class _Builder:
    def __init__(self, ctx: _Ctx, index: _Index, proof: dict, scope: dict[str, Any]) -> None:
        self.ctx = ctx
        self.index = index
        self.proof = proof
        self.scope = scope
        self.obligations: dict[str, dict[str, Any]] = {}
        self.impacted = {name: {i.get("entity_id") for i in proof.get(name) or [] if type(i) is dict}
                         for _, name in closure.REPORTED_LISTS}

    # -- shared helpers -------------------------------------------------
    def flow_tasks(self, fid: str) -> set[int]:
        info = self.index.flows.get(fid)
        return set(info["task_ids"] if info else ()) | self.index.mapping_tasks_by_flow.get(fid, set())

    def flow_requirements(self, fid: str) -> set[str]:
        info = self.index.flows.get(fid)
        owner = self.index.plan_flow_owner.get(fid)
        reqs = set(info["requirement_ids"] if info else ())
        if owner:
            reqs |= set(closure._str_ids(owner[1].get("requirement_ids")))
        return reqs

    def owner_plan(self, fids: Iterable[str]) -> str | None:
        for fid in sorted(fids):
            owner = self.index.plan_flow_owner.get(fid)
            if owner:
                return owner[0]
        for fid in sorted(fids):
            plans = sorted(self.index.flow_plans.get(fid, ()))
            if plans:
                return plans[0]
        return None

    def add(self, rec: dict[str, Any]) -> None:
        self.obligations[rec["obligation_id"]] = rec

    # -- candidate sets ---------------------------------------------------
    def candidate_flows(self) -> set[str]:
        flows = {f for f in self.impacted["impacted_flows"] if type(f) is str} | set(self.scope["flows"])
        if self.proof.get("conservative_expanded"):
            flows |= self.index.baseline_active_flows
        return flows

    def tests_of_flow(self, fid: str) -> set[str]:
        info = self.index.flows.get(fid)
        tests = set(info["test_ids"] if info else ())
        for obl in self.index.binding_obligations:
            if fid in obl["flow_ids"]:
                tests |= set(obl["test_ids"])
        return tests

    # -- tests --------------------------------------------------------------
    def build_tests(self, flows: set[str]) -> None:
        candidates: set[str] = set()
        for fid in flows:
            candidates |= self.tests_of_flow(fid)
        candidates |= {t for t in self.impacted["impacted_tests"] if type(t) is str}
        if self.proof.get("conservative_expanded"):
            candidates |= self.index.baseline_impl_tests
        for test_id in sorted(candidates):
            self.add(self.test_obligation(test_id))

    def linked_planned_impls(self, flows: set[str], tasks: set[int]) -> list[str]:
        plans = set()
        for fid in flows:
            plans |= self.index.flow_plans.get(fid, set())
        return sorted(f"implementation_object:{i['plan_id']}:{i['id']}" for i in self.index.impl_objects
                      if not i["existing"] and i["plan_id"] in plans and set(i["responsible"]) & tasks)

    def test_obligation(self, test_id: str) -> dict[str, Any]:
        ctx, index = self.ctx, self.index
        flows = set(index.test_flows.get(test_id, set()))
        tasks: set[int] = set()
        reqs: set[str] = set()
        for fid in flows:
            tasks |= self.flow_tasks(fid)
            reqs |= self.flow_requirements(fid)
        categories = set()
        bound_flows: set[str] = set()
        for obl in index.binding_obligations:
            if test_id in obl["test_ids"]:
                reqs |= set(obl["requirement_ids"])
                bound_flows |= set(obl["flow_ids"])
                if obl["category"]:
                    categories.add(obl["category"])
        stage5_baseline = bool(bound_flows & index.baseline_active_flows)
        entries = index.tests.get(test_id, [])
        impl_entries = sorted((e for e in entries if _impl(e["doc"])), key=lambda e: (not e["baseline"], e["manifest"]))
        ordered = impl_entries or sorted(entries, key=lambda e: (not e["baseline"], e["manifest"]))
        preferred = ordered[0] if ordered else None
        reasons: list[str] = []
        in_scope = bool(flows & self.scope["flows"])
        if test_id in index.baseline_impl_tests:
            tier = "existing_required"
            reasons.append("cumulative_baseline_implemented_regression")
        elif "existing_required" in categories:
            tier = "existing_required"
            reasons.append("stage5_existing_required")
        elif stage5_baseline:
            tier = "existing_required"
            reasons.append("stage5_bound_test_on_active_baseline_flow")
        elif in_scope or "current_new" in categories:
            tier = "current_new"
            reasons.append("current_delivery_boundary" if in_scope else "stage5_current_new")
        else:
            tier = "out_of_scope_future"
            reasons.append("impacted_outside_current_delivery_without_baseline_regression")
        if test_id in self.impacted["impacted_tests"]:
            reasons.append("impacted_by_change_roots")
        missing: list[str] = []
        level = "unimplemented"
        descriptor = None
        if not entries:
            evidence = "unimplemented"
            missing.append(f"manifest_test_declaration:{test_id}")
        elif not impl_entries:
            evidence = "unimplemented"
            missing.append(f"implemented_test:{test_id}")
        else:
            doc = preferred["doc"]
            kind = doc.get("kind")
            path = closure._try_path(doc.get("path"))
            declared_level = doc.get("evidence_level")
            if kind not in EVIDENCE_LEVELS or path is None or (
                    declared_level is not None and declared_level not in EVIDENCE_LEVELS[kind]):
                evidence = "broken"
                missing.append(f"valid_test_descriptor:{test_id}")
            elif not ctx.exists(path):
                evidence = "broken"
                missing.append(f"test_file:{path}")
            else:
                evidence = "ready"
                level = declared_level or DEFAULT_LEVEL[kind]
                selector = doc.get("selector") if type(doc.get("selector")) is str and doc["selector"].strip() else None
                min_tests = doc.get("min_tests") if type(doc.get("min_tests")) is int and doc["min_tests"] >= 1 else None
                challenge = doc.get("challenge") if type(doc.get("challenge")) is str and doc["challenge"].strip() \
                    else None
                descriptor = {"kind": kind, "path": path, "selector": selector, "min_tests": min_tests,
                              "challenge": challenge, "evidence_level": level}
            if tier == "current_new" and evidence == "ready":
                impls = self.linked_planned_impls(flows, tasks)
                if impls:
                    evidence = "unimplemented"
                    level = "unimplemented"
                    missing.extend(impls)
        if tier == "existing_required":
            # Cropping defense: an active (non-baseline) manifest that declares the Flow but omits the regression,
            # or a Stage-5 bound regression missing from every manifest, keeps the obligation and blocks closure.
            cropped = sorted({e["manifest"] for fid in flows for e in index.flows.get(fid, {"entries": []})["entries"]
                              if test_id not in e["test_ids"]
                              and "active" in ctx.manifests.get(e["manifest"], {}).get("roles", [])})
            if cropped:
                ctx.gap(f"test:{test_id}", "baseline_test_cropped_from_active_manifest")
                missing.extend(f"active_manifest_declaration:{rel}" for rel in cropped)
                reasons.append("cropped_regression_kept_and_blocked")
                if evidence == "ready":
                    evidence, level, descriptor = "broken", "unimplemented", None
            if evidence != "ready" and (stage5_baseline or "existing_required" in categories):
                ctx.gap(f"test:{test_id}", "stage5_bound_regression_missing_or_cropped")
        if evidence in ("broken",) and tier == "existing_required":
            reasons.append("baseline_regression_kept_despite_broken_or_missing_test")
        test_files = sorted({closure._try_path(e["doc"].get("path")) for e in entries} - {None})
        evidence_digest = codec.canonical_digest({
            "test_entries": sorted(([e["manifest"], e["doc"]] for e in entries), key=closure._dumps),
            "test_files": {p: ctx.file_digest(p) for p in test_files},
            "flows": [[f, _flow_evidence(ctx, index, f)] for f in sorted(flows)],
        })
        kind = "executable_test" if evidence == "ready" else "pending_implementation"
        owner_pid = self.owner_plan(flows)
        rec = _make_obligation(
            oid=f"test:{test_id}", tier=tier, evidence=evidence, kind=kind, level=level, flow_ids=flows,
            requirement_ids=reqs, task_ids=tasks, test_ids=[test_id], ov_refs=[],
            owner={"owner_plan_id": owner_pid, "kind": "test", "id": test_id},
            authority=_authority(ctx, owner_pid, preferred["manifest"] if preferred else None),
            reasons=reasons, missing=missing, evidence_digest=evidence_digest,
            extra={"descriptor": descriptor})
        return rec

    # -- flows without any declared test -----------------------------------
    def build_flows_without_tests(self, flows: set[str]) -> None:
        for fid in sorted(flows):
            if self.tests_of_flow(fid):
                continue
            in_scope = fid in self.scope["flows"]
            tier = "current_new" if in_scope else "out_of_scope_future"
            reasons = ["current_delivery_boundary" if in_scope else "impacted_outside_current_delivery_without_baseline_regression",
                       "flow_without_declared_tests"]
            owner_pid = self.owner_plan([fid])
            self.add(_make_obligation(
                oid=f"flow:{fid}", tier=tier, evidence="unimplemented", kind="pending_implementation",
                level="unimplemented", flow_ids=[fid], requirement_ids=self.flow_requirements(fid),
                task_ids=self.flow_tasks(fid), test_ids=[], ov_refs=[],
                owner={"owner_plan_id": owner_pid, "kind": "flow", "id": fid},
                authority=_authority(self.ctx, owner_pid, None), reasons=reasons,
                missing=[f"flow_test_declaration:{fid}"], evidence_digest=_flow_evidence(self.ctx, self.index, fid)))

    # -- binding obligations without tests ---------------------------------
    def build_binding_obligations(self, flows: set[str]) -> None:
        for obl in self.index.binding_obligations:
            if obl["test_ids"]:
                continue
            key = f"{obl['plan_id']}:{obl['id']}"
            relevant = key in self.impacted["impacted_obligations"] or set(obl["flow_ids"]) & flows \
                or obl["plan_id"] in self.scope["plans"]
            if not relevant:
                continue
            in_scope = bool(set(obl["flow_ids"]) & self.scope["flows"]) or obl["plan_id"] in self.scope["plans"]
            reasons = []
            if obl["category"]:
                tier = obl["category"]
                reasons.append(f"stage5_{obl['category']}")
                if tier == "out_of_scope_future" and in_scope:
                    tier = "current_new"
                    reasons.append("future_obligation_entered_current_delivery_boundary")
            elif in_scope:
                tier = "current_new"
                reasons.append("current_delivery_boundary")
            elif set(obl["flow_ids"]) & self.index.baseline_active_flows:
                tier = "existing_required"
                reasons.append("binding_obligation_on_active_baseline_flow")
            else:
                tier = "out_of_scope_future"
                reasons.append("impacted_outside_current_delivery_without_baseline_regression")
            paths = obl["verification_paths"]
            missing = []
            if not paths:
                evidence, kind = "unimplemented", "pending_implementation"
                missing.append(f"verification_ref:{key}")
            elif not obl["verification_refs_valid"] or not all(self.ctx.nonempty(p) for p in paths):
                evidence, kind = "broken", "other_verification"
                missing.extend(f"verification_file:{p}" for p in paths if not self.ctx.nonempty(p))
                if not obl["verification_refs_valid"]:
                    missing.append(f"valid_verification_ref:{key}")
            else:
                kind = "other_verification"
                evidence = "ready" if any(p.endswith(SCRIPT_SUFFIXES) for p in paths) else "manual"
            tasks = set()
            for fid in obl["flow_ids"]:
                tasks |= self.flow_tasks(fid)
            level = {"ready": "other-verification", "manual": "manual"}.get(evidence, "unimplemented")
            digest = codec.canonical_digest({"obligation": obl["doc"],
                                             "files": {p: self.ctx.file_digest(p) for p in paths},
                                             "flows": [[f, _flow_evidence(self.ctx, self.index, f)]
                                                       for f in sorted(obl["flow_ids"])]})
            scripts = [p for p in paths if p.endswith(SCRIPT_SUFFIXES)] if evidence == "ready" else []
            self.add(_make_obligation(
                oid=f"binding_obligation:{key}", tier=tier, evidence=evidence, kind=kind, level=level,
                flow_ids=obl["flow_ids"], requirement_ids=obl["requirement_ids"], task_ids=tasks, test_ids=[],
                ov_refs=paths, owner={"owner_plan_id": obl["plan_id"], "kind": "obligation", "id": obl["id"]},
                authority=_authority(self.ctx, obl["plan_id"], None), reasons=reasons, missing=missing,
                evidence_digest=digest,
                extra={"scripts": scripts, "paths": paths, "rationale": obl["doc"].get("responsibility")
                       if type(obl["doc"].get("responsibility")) is str else None, "links": []}))

    # -- implementation objects -----------------------------------------------
    def build_impl_objects(self) -> None:
        for impl in self.index.impl_objects:
            key = f"{impl['plan_id']}:{impl['id']}"
            flows = set()
            reqs: set[str] = set()
            for tid in impl["responsible"]:
                flows |= {f for f in self.index.mapping_flows_by_task.get(tid, set())
                          if impl["plan_id"] in self.index.flow_plans.get(f, set())}
                reqs |= self.index.mapping_reqs_by_task.get(tid, set())
            for fid in flows:
                reqs |= self.flow_requirements(fid)
            scoped = impl["plan_id"] in self.scope["plans"] or bool(set(impl["responsible"]) & self.scope["tasks"]) \
                or bool(flows & self.scope["flows"])
            impacted = key in self.impacted["impacted_implementation_objects"]
            if impl["existing"]:
                broken = not impl["target_valid"] or not impl["target_paths"] or \
                    not all(self.ctx.exists(p) for p in impl["target_paths"])
                if not (broken and (impacted or scoped)):
                    continue
                tier, evidence = "existing_required", "broken"
                reasons = ["existing_implementation_object_with_broken_target"]
                missing = [f"implementation_target:{key}"]
            else:
                if not (impacted or scoped):
                    continue
                tier = "current_new" if scoped else "out_of_scope_future"
                evidence = "unimplemented"
                reasons = ["current_delivery_boundary" if scoped
                           else "impacted_outside_current_delivery_without_baseline_regression",
                           "planned_implementation_object"]
                missing = [f"implementation_object:{key}"]
            digest = codec.canonical_digest({"implementation_object": impl["doc"],
                                             "files": {p: self.ctx.file_digest(p) for p in impl["target_paths"]}})
            self.add(_make_obligation(
                oid=f"implementation_object:{key}", tier=tier, evidence=evidence, kind="pending_implementation",
                level="unimplemented", flow_ids=flows, requirement_ids=reqs, task_ids=impl["responsible"], test_ids=[],
                ov_refs=[], owner={"owner_plan_id": impl["plan_id"], "kind": "implementation_object", "id": impl["id"]},
                authority=_authority(self.ctx, impl["plan_id"], None), reasons=reasons, missing=missing,
                evidence_digest=digest))

    # -- legal non-Flow verification ---------------------------------------------
    def build_other_verification(self) -> None:
        impacted_reqs = self.impacted["impacted_requirements"]
        sinks = self.impacted["other_verification_sinks"]
        for pid in sorted(self.ctx.plans):
            doc = self.ctx.plans[pid]["doc"]
            entries: dict[str, dict[str, Any]] = {}
            for item in doc.get("applicability") or []:
                if type(item) is not dict or item.get("disposition") != "other_verification" \
                        or type(item.get("requirement_id")) is not str:
                    continue
                slot = entries.setdefault(item["requirement_id"], {"paths": set(), "refs": set(), "valid": True,
                                                                   "rationale": None, "raw": []})
                slot["raw"].append(item)
                slot["rationale"] = item.get("rationale") if type(item.get("rationale")) is str else slot["rationale"]
                refs = item.get("other_verification_refs") or []
                if not refs:
                    slot["valid"] = False
                for ref in refs:
                    paths, valid = closure._owned_paths(ref)
                    slot["paths"].update(paths)
                    slot["valid"] = slot["valid"] and valid
                    if type(ref) is dict and type(ref.get("ref")) is str:
                        slot["refs"].add(ref["ref"])
            for item in doc.get("requirement_verification") or []:
                if type(item) is not dict or item.get("disposition") != "other_verification" \
                        or type(item.get("requirement_id")) is not str:
                    continue
                slot = entries.setdefault(item["requirement_id"], {"paths": set(), "refs": set(), "valid": True,
                                                                   "rationale": None, "raw": []})
                slot["raw"].append(item)
                slot["rationale"] = item.get("rationale") if type(item.get("rationale")) is str else slot["rationale"]
                ident = item.get("verification_ref") or item.get("sink_id")
                if type(ident) is not str or not ident.strip():
                    slot["valid"] = False
                    continue
                slot["refs"].add(ident)
                path = closure._try_path(ident) if "/" in ident else None
                if path:
                    slot["paths"].add(path)
                elif "/" in ident:
                    slot["valid"] = False
            for rid in sorted(entries):
                slot = entries[rid]
                in_scope = pid in self.scope["plans"] or rid in self.scope["requirements"]
                if not (in_scope or rid in impacted_reqs or slot["refs"] & sinks):
                    continue
                paths = sorted(slot["paths"])
                rationale = slot["rationale"]
                missing = []
                substantive = type(rationale) is str and rationale.strip().lower() not in TRIVIAL_RATIONALES \
                    and len(rationale.strip()) >= MIN_RATIONALE_LENGTH
                if not substantive:
                    missing.append(f"substantive_rationale:{rid}")
                if not paths or not slot["valid"]:
                    missing.append(f"other_verification_ref:{rid}")
                missing.extend(f"verification_file:{p}" for p in paths if not self.ctx.nonempty(p))
                live = not missing
                if live:
                    evidence = "ready" if any(p.endswith(SCRIPT_SUFFIXES) for p in paths) else "manual"
                else:
                    evidence = "broken"
                if in_scope:
                    tier, reasons = "current_new", ["current_delivery_boundary", "legal_non_flow_requirement"]
                elif live:
                    tier, reasons = "existing_required", ["impacted_live_non_flow_verification",
                                                          "legal_non_flow_requirement"]
                else:
                    tier, reasons = "out_of_scope_future", [
                        "impacted_outside_current_delivery_without_baseline_regression", "legal_non_flow_requirement"]
                links = sorted(fid for fid in self.index.flows if rid in self.flow_requirements(fid))
                level = {"ready": "other-verification", "manual": "manual"}.get(evidence, "unimplemented")
                digest = codec.canonical_digest({"entries": sorted(slot["raw"], key=closure._dumps),
                                                 "files": {p: self.ctx.file_digest(p) for p in paths}})
                scripts = [p for p in paths if p.endswith(SCRIPT_SUFFIXES)] if evidence == "ready" else []
                self.add(_make_obligation(
                    oid=f"other_verification:{pid}:{rid}", tier=tier, evidence=evidence, kind="other_verification",
                    level=level, flow_ids=[], requirement_ids=[rid], task_ids=[], test_ids=[],
                    ov_refs=sorted(slot["refs"] | set(paths)),
                    owner={"owner_plan_id": pid, "kind": "requirement", "id": rid},
                    authority=_authority(self.ctx, pid, None), reasons=reasons, missing=missing,
                    evidence_digest=digest,
                    extra={"scripts": scripts, "rationale": rationale if type(rationale) is str and rationale.strip()
                           else None, "links": links, "paths": paths}))

    def linked_mvg_flows(self) -> set[str]:
        """MVG Flows linked by legal non-Flow requirements; their real regression tests join the candidate set."""
        return {fid for rec in self.obligations.values() if rec["obligation_id"].startswith("other_verification:")
                for fid in rec["_extra"].get("links") or []}

    # -- manual checks ---------------------------------------------------------
    def flow_tier(self, fid: str) -> str:
        tiers = [o["tier"] for o in self.obligations.values() if fid in o["flow_ids"]]
        if tiers:
            return min(tiers, key=lambda t: TIER_RANK[t])
        if fid in self.index.baseline_active_flows:
            return "existing_required"
        return "current_new" if fid in self.scope["flows"] else "out_of_scope_future"

    def build_manual(self, flows: set[str]) -> None:
        manual: list[dict[str, Any]] = []
        for fid in sorted(flows):
            owner = self.index.plan_flow_owner.get(fid)
            block = owner[1].get("human_verification") if owner else None
            if type(block) is not dict or block.get("applicability") != "applicable":
                continue
            checks = [c for c in (block.get("checks") or block.get("responsibilities") or [])
                      if type(c) is str and c.strip()]
            if not checks and type(block.get("responsibility")) is str and block["responsibility"].strip():
                checks = [block["responsibility"]]
            checks = checks or [f"human_verification:{fid}"]
            tier = self.flow_tier(fid)
            digest = codec.canonical_digest({"block": block, "flow": _flow_evidence(self.ctx, self.index, fid)})
            manual.append(_make_obligation(
                oid=f"manual:flow:{fid}", tier=tier, evidence="manual", kind="manual_check", level="manual",
                flow_ids=[fid], requirement_ids=self.flow_requirements(fid), task_ids=self.flow_tasks(fid),
                test_ids=[], ov_refs=[], owner={"owner_plan_id": owner[0], "kind": "flow", "id": fid},
                authority=_authority(self.ctx, owner[0], None), reasons=["applicable_human_verification"],
                missing=[], evidence_digest=digest,
                extra={"source": "human_verification", "responsibilities": checks}))
        for obl in self.index.binding_obligations:
            if not obl["manual_checks"]:
                continue
            key = f"{obl['plan_id']}:{obl['id']}"
            relevant = key in self.impacted["impacted_obligations"] or set(obl["flow_ids"]) & flows \
                or obl["plan_id"] in self.scope["plans"]
            if not relevant:
                continue
            if obl["flow_ids"]:
                tier = min((self.flow_tier(f) for f in obl["flow_ids"]), key=lambda t: TIER_RANK[t])
            elif obl["plan_id"] in self.scope["plans"]:
                tier = "current_new"
            else:
                tier = obl["category"] or "out_of_scope_future"
            tasks: set[int] = set()
            for fid in obl["flow_ids"]:
                tasks |= self.flow_tasks(fid)
            manual.append(_make_obligation(
                oid=f"manual:binding:{key}", tier=tier, evidence="manual", kind="manual_check", level="manual",
                flow_ids=obl["flow_ids"], requirement_ids=obl["requirement_ids"], task_ids=tasks, test_ids=[],
                ov_refs=[], owner={"owner_plan_id": obl["plan_id"], "kind": "obligation", "id": obl["id"]},
                authority=_authority(self.ctx, obl["plan_id"], None), reasons=["stage5_binding_human_verification"],
                missing=[], evidence_digest=codec.canonical_digest({"obligation": obl["doc"]}),
                extra={"source": "human_verification", "responsibilities": list(obl["manual_checks"])}))
        for rel in sorted(self.ctx.manifests):
            manifest = self.ctx.manifests[rel]
            doc = manifest["doc"]
            declared = sorted({f["id"] for f in doc.get("flows") or [] if type(f) is dict
                               and type(f.get("id")) is str} & flows)
            coverage = doc.get("coverage") if type(doc.get("coverage")) is dict else {}
            claims = [c for c in coverage.get("excluded_claims") or [] if type(c) is str and c.strip()]
            if not declared or not claims:
                continue
            tier = min((self.flow_tier(f) for f in declared), key=lambda t: TIER_RANK[t])
            for position, claim in enumerate(claims, start=1):
                digest = codec.canonical_digest({"manifest": rel, "sha": manifest["sha256"], "claim": claim})
                reqs: set[str] = set()
                for fid in declared:
                    reqs |= self.flow_requirements(fid)
                manual.append(_make_obligation(
                    oid=f"manual:manifest:{manifest['mvg_id']}:{position}", tier=tier, evidence="manual",
                    kind="manual_check", level="manual", flow_ids=declared, requirement_ids=reqs, task_ids=[],
                    test_ids=[], ov_refs=[], owner={"owner_plan_id": None, "kind": "manifest",
                                                    "id": manifest["mvg_id"]},
                    authority=_authority(self.ctx, None, rel), reasons=["manifest_excluded_claim"], missing=[],
                    evidence_digest=digest, extra={"source": "manifest_excluded_claim", "responsibilities": [claim]}))
        for rec in manual:
            self.add(rec)


# ---------------------------------------------------------------------------
# Governed scope delta
# ---------------------------------------------------------------------------

def _load_delta(root: Path, delta: Any) -> tuple[dict[str, Any] | None, str | None]:
    if delta is None:
        return None, None
    rel = None
    if type(delta) is str and delta.strip():
        rel = closure._normalize_rel(delta, allow_logs=True)
        raw = closure._read_bytes(root, rel, allow_logs=True)
        if raw is None:
            raise _err(codec.ReasonCode.FILE_NOT_FOUND, "existing scope delta file", rel, entity=rel,
                       stage=codec.Stage.PATH)
        delta = codec.strict_json_loads(raw)
    if type(delta) is not dict:
        raise _err(codec.ReasonCode.INVALID_ARGUMENT, "scope delta object or repository-relative path",
                   type(delta).__name__)
    codec.validate_json_value(delta)
    if delta.get("schema_version") != DELTA_SCHEMA:
        raise _err(codec.ReasonCode.UNKNOWN_SCHEMA, DELTA_SCHEMA, delta.get("schema_version"), stage=codec.Stage.SCHEMA)
    changes = delta.get("changes")
    if type(changes) is not list or not changes or set(delta) - {"schema_version", "changes"}:
        raise _err(codec.ReasonCode.SCHEMA_VALIDATION_FAILED, "scope delta with exactly schema_version and nonempty changes",
                   sorted(delta), stage=codec.Stage.SCHEMA)
    return copy.deepcopy(delta), rel


def _grounded_ref(ctx: _Ctx, value: Any, owner: str, *, allow_logs: bool) -> dict[str, Any] | None:
    if type(value) is not str or not value.strip():
        return None
    try:
        rel = closure._normalize_rel(value, allow_logs=allow_logs)
        raw = closure._read_bytes(ctx.root, rel, allow_logs=allow_logs)
    except codec.CodecError:
        return None
    if raw is None or not raw.strip():
        return None
    return {"owner": owner, "ref": rel, "files": [{"path": rel, "raw_digest": codec.raw_digest(raw)}]}


def _apply_delta(ctx: _Ctx, index: _Index, builder: _Builder, delta: dict[str, Any] | None,
                 delta_path: str | None = None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    applied: list[dict[str, Any]] = []
    refs: list[dict[str, Any]] = []
    if delta is None:
        return applied, refs
    allowed = {"action", "obligation_id", "flow_id", "test_id", "target_tier", "reason", "source_authority_ref",
               "anti_weakening_review_ref"}
    for change in delta["changes"]:
        if type(change) is not dict or set(change) - allowed:
            raise _err(codec.ReasonCode.SCHEMA_VALIDATION_FAILED, sorted(allowed),
                       sorted(change) if type(change) is dict else type(change).__name__, stage=codec.Stage.SCHEMA)
        action = change.get("action")
        if action not in DELTA_ACTIONS:
            raise _err(codec.ReasonCode.INVALID_ENUM, sorted(DELTA_ACTIONS), action)
        selectors = [k for k in ("obligation_id", "flow_id", "test_id") if change.get(k) is not None]
        if len(selectors) != 1 or type(change[selectors[0]]) is not str:
            raise _err(codec.ReasonCode.INVALID_ARGUMENT, "exactly one of obligation_id/flow_id/test_id", change)
        reason = change.get("reason")
        if type(reason) is not str or not reason.strip():
            raise _err(codec.ReasonCode.INVALID_ARGUMENT, "nonempty delta reason", reason)
        selector, value = selectors[0], change[selectors[0]]
        matched = [o for o in builder.obligations.values()
                   if (selector == "obligation_id" and o["obligation_id"] == value)
                   or (selector == "flow_id" and value in o["flow_ids"])
                   or (selector == "test_id" and value in o["test_ids"])]
        if not matched:
            raise _err(codec.ReasonCode.UNRESOLVED_REFERENCE, "delta target present in the computed scope", value)
        if _disguised_reason(reason):
            raise _err(codec.ReasonCode.CONFLICT,
                       "obligations are never removed or downgraded because a test failed, cannot launch, is missing "
                       "or is flaky; a delta reason must be a substantive specification rationale",
                       {"target": value, "reason": reason})
        protected_existing = [o["obligation_id"] for o in matched if o["tier"] == "existing_required"]
        baseline_flow = selector == "flow_id" and value in index.baseline_active_flows
        if action in ("remove", "shrink") and (protected_existing or baseline_flow):
            raise _err(codec.ReasonCode.CONFLICT,
                       "existing_required obligations and active baseline Flows are never removed or shrunk; only a "
                       "governed spec-grounded retire is allowed", {"target": value, "action": action,
                                                                    "obligations": protected_existing})
        target = change.get("target_tier")
        if action == "reclassify":
            if target not in DELTA_TARGET_TIERS:
                raise _err(codec.ReasonCode.INVALID_ENUM, sorted(DELTA_TARGET_TIERS), target)
            effective = "out_of_scope_future" if target == "planned" else target
            weakening = any(TIER_RANK[effective] > TIER_RANK[o["tier"]] for o in matched)
            protected = [o["obligation_id"] for o in matched if o["tier"] == "existing_required"
                         and effective != "existing_required"]
            protected_flow = selector == "flow_id" and value in index.baseline_active_flows and \
                effective != "existing_required"
            if protected or protected_flow:
                raise _err(codec.ReasonCode.CONFLICT,
                           "existing_required obligations and active baseline Flows are never reclassified as planned "
                           "or out_of_scope_future", {"target": value, "obligations": protected})
        else:
            effective = None
            weakening = True
        if weakening:
            source = _grounded_ref(ctx, change.get("source_authority_ref"), "authority", allow_logs=False)
            review = _grounded_ref(ctx, change.get("anti_weakening_review_ref"), "verification_record",
                                   allow_logs=True)
            if source is None or review is None:
                raise _err(codec.ReasonCode.CONFLICT,
                           "weakening scope delta requires a grounded non-log source_authority_ref and a reviewed "
                           "anti_weakening_review_ref", {"target": value, "action": action})
            if source["ref"] == review["ref"] or (delta_path is not None and delta_path in (source["ref"],
                                                                                              review["ref"])):
                raise _err(codec.ReasonCode.CONFLICT,
                           "source_authority_ref, anti_weakening_review_ref and the scope delta file are distinct",
                           {"target": value, "source": source["ref"], "review": review["ref"],
                            "delta_path": delta_path})
            for ref in (source, review):
                if ref not in refs:
                    refs.append(ref)
        for obl in sorted(matched, key=lambda o: o["obligation_id"]):
            applied.append({"obligation_id": obl["obligation_id"], "tier": obl["tier"], "action": action,
                            "reason": reason, "target_tier": effective,
                            "source_authority_ref": change.get("source_authority_ref") if weakening else None,
                            "anti_weakening_review_ref": change.get("anti_weakening_review_ref") if weakening else None})
            if action == "reclassify":
                obl["tier"] = effective
                obl["status"] = _status_for(effective, obl["_evidence"])
                obl["blocking_current_delivery"] = effective in CURRENT_TIERS
                obl["immediate_execution_required"] = effective in CURRENT_TIERS
                obl["execution_kind"] = obl["_base_kind"] if effective in CURRENT_TIERS else "future_followup"
                obl["follow_up_responsibilities"] = list(FUTURE_FOLLOW_UP) if effective == "out_of_scope_future" else []
                obl["classification_reasons"] = _strings(obl["classification_reasons"] + ["governed_scope_delta"])
            else:
                builder.obligations.pop(obl["obligation_id"], None)
    refs.sort(key=lambda r: (r["owner"], r["ref"]))
    return applied, refs


# ---------------------------------------------------------------------------
# Scope assembly
# ---------------------------------------------------------------------------

def _finalize_obligation(rec: dict[str, Any]) -> dict[str, Any]:
    public = {k: v for k, v in rec.items() if not k.startswith("_")}
    body = {k: v for k, v in public.items() if k != "input_fingerprint"}
    public["input_fingerprint"] = codec.canonical_digest({"record": body, "evidence": rec["_evidence_digest"]})
    return public


def _pending_reason(rec: dict[str, Any]) -> str:
    if rec["tier"] == "out_of_scope_future":
        return "future_followup_outside_current_delivery"
    if rec["_evidence"] == "broken":
        return "broken_or_missing_verification_reference"
    return "unimplemented_or_incomplete_obligation"


def _execution_plan(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    executable, pending, manual, other = [], [], [], []
    for rec in records:
        extra = rec["_extra"]
        current = rec["tier"] in CURRENT_TIERS
        if rec["_base_kind"] == "manual_check":
            manual.append({"manual_id": rec["obligation_id"], "tier": rec["tier"], "source": extra["source"],
                           "flow_ids": rec["flow_ids"], "requirement_ids": rec["requirement_ids"],
                           "owner_plan_id": rec["semantic_owner"]["owner_plan_id"],
                           "responsibilities": list(extra["responsibilities"]),
                           "blocking_current_delivery": rec["blocking_current_delivery"]})
        if rec["_base_kind"] == "other_verification":
            other.append({"obligation_id": rec["obligation_id"], "tier": rec["tier"],
                          "requirement_ids": rec["requirement_ids"], "rationale": extra.get("rationale"),
                          "verification_paths": _strings(extra.get("paths") or rec["other_verification_refs"]),
                          "status": rec["status"], "blocking_current_delivery": rec["blocking_current_delivery"],
                          "links_mvg_flow_ids": _strings(extra.get("links") or [])})
            if current and rec["status"] == "manual_required" and rec["obligation_id"].startswith("other_verification:"):
                manual.append({"manual_id": rec["obligation_id"], "tier": rec["tier"],
                               "source": "other_verification_document", "flow_ids": rec["flow_ids"],
                               "requirement_ids": rec["requirement_ids"],
                               "owner_plan_id": rec["semantic_owner"]["owner_plan_id"],
                               "responsibilities": [f"review_other_verification:{p}"
                                                    for p in _strings(extra.get("paths") or [])] or
                                                   [f"review_other_verification:{rec['obligation_id']}"],
                               "blocking_current_delivery": True})
        if current and rec["status"] == "ready_to_execute":
            descriptor = extra.get("descriptor")
            if rec["_base_kind"] == "executable_test" and descriptor:
                executable.append({"test_id": rec["test_ids"][0], "obligation_id": rec["obligation_id"],
                                   "kind": descriptor["kind"], "evidence_level": descriptor["evidence_level"],
                                   "path": descriptor["path"], "selector": descriptor["selector"],
                                   "min_tests": descriptor["min_tests"], "tier": rec["tier"],
                                   "flow_ids": rec["flow_ids"], "requirement_ids": rec["requirement_ids"],
                                   "challenge": descriptor["challenge"]})
            elif rec["_base_kind"] == "other_verification" and extra.get("scripts"):
                scripts = list(extra["scripts"])
                for script in scripts:
                    executable.append({"test_id": rec["obligation_id"] if len(scripts) == 1
                                       else f"{rec['obligation_id']}@{script}",
                                       "obligation_id": rec["obligation_id"],
                                       "kind": "other_verification", "evidence_level": "other-verification",
                                       "path": script, "selector": None, "min_tests": None, "tier": rec["tier"],
                                       "flow_ids": rec["flow_ids"], "requirement_ids": rec["requirement_ids"],
                                       "challenge": None})
        if rec["status"] in OPEN_STATUSES or (rec["status"] == "tracked_future" and rec["_evidence"] != "manual"):
            pending.append({"obligation_id": rec["obligation_id"], "tier": rec["tier"], "status": rec["status"],
                            "reason": _pending_reason(rec), "blocking_current_delivery": rec["blocking_current_delivery"],
                            "missing_targets": rec["missing_targets"], "responsible_task_ids": rec["task_ids"],
                            "flow_ids": rec["flow_ids"], "requirement_ids": rec["requirement_ids"]})
    key = lambda item: (item.get("test_id") or item.get("obligation_id") or item.get("manual_id"),
                        item.get("obligation_id") or "")
    return {"executable_tests": sorted(executable, key=key), "pending_obligations": sorted(pending, key=key),
            "manual_obligations": sorted(manual, key=key), "other_verification_obligations": sorted(other, key=key)}


def _flow_classifications(records: list[dict[str, Any]], scope_flows: set[str]) -> list[dict[str, Any]]:
    flows: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        for fid in rec["flow_ids"]:
            flows.setdefault(fid, []).append(rec)
    result = []
    for fid in sorted(flows):
        recs = flows[fid]
        tiers = {r["tier"] for r in recs if r["_base_kind"] != "manual_check"} or {r["tier"] for r in recs}
        result.append({
            "flow_id": fid,
            "in_current_delivery_scope": fid in scope_flows,
            "has_existing_required": "existing_required" in tiers,
            "has_current_new": "current_new" in tiers,
            "has_out_of_scope_future": "out_of_scope_future" in tiers,
            "mixed_tiers": len(tiers) > 1,
            "blocking_current_delivery": any(r["blocking_current_delivery"] and r["status"] in OPEN_STATUSES
                                             for r in recs),
            "obligation_ids": sorted(r["obligation_id"] for r in recs),
        })
    return result


def _task_input_sets(ctx: _Ctx, tasks: list[int]) -> list[dict[str, Any]]:
    result = []
    for tid in tasks:
        try:
            res = input_set.resolve_input_set(ctx.root, tid)
        except Exception as exc:  # noqa: BLE001 - any resolver failure leaves the task input unverified
            res = {"valid_input_set": False, "route": "blocked", "input_set_digest": None,
                   "diagnostics": [{"reason_code": f"input_set_error:{type(exc).__name__}"}]}
        digest = res.get("input_set_digest")
        valid = res.get("valid_input_set") is True and type(digest) is str and bool(closure.DIGEST_RE.fullmatch(digest))
        route = res.get("route") if type(res.get("route")) is str and res.get("route") else "blocked"
        diags = res.get("diagnostics") or []
        reason = "ok" if valid else str((diags[0] or {}).get("reason_code") if diags and type(diags[0]) is dict
                                        else "input_set_unverified")
        if not valid:
            digest = codec.canonical_digest({"task_id": tid, "route": route, "reason_code": reason,
                                             "unverified_input_set": True})
            ctx.gap(f"task:{tid}", f"task_input_set_unverified:{reason}")
        result.append({"task_id": tid, "input_set_digest": digest, "route": route, "valid_input_set": valid,
                       "reason_code": reason})
    return result


def _scope_body(scope: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in scope.items() if k not in VOLATILE_FIELDS}


def _seal(scope: dict[str, Any]) -> None:
    scope["scope_id"] = codec.canonical_digest(_scope_body(scope))


def _resolve_impact(root_path: Path, *, change_roots: Any, impact_proof: Any,
                    impact_manifest_paths: list[str]) -> dict[str, Any]:
    if (change_roots is None or change_roots == []) == (impact_proof is None):
        raise _err(codec.ReasonCode.INVALID_ARGUMENT, "exactly one of change_roots or impact_proof",
                   {"change_roots": change_roots, "impact_proof": impact_proof is not None})
    if impact_proof is not None:
        result = closure.revalidate_impact_proof(root_path, impact_proof, manifest_paths=impact_manifest_paths,
                                                 operation="verification_scope_impact")
        if not result.get("ok"):
            diag = (result.get("diagnostics") or [{}])[0]
            code = diag.get("reason_code") if type(diag) is dict else None
            try:
                reason = codec.ReasonCode(code)
            except ValueError:
                reason = codec.ReasonCode.SCHEMA_VALIDATION_FAILED
            raise _err(reason, "valid sealed Story 4.1 impact proof", diag, stage=codec.Stage.SCHEMA)
        if result.get("status") != "valid_reused":
            raise _err(codec.ReasonCode.INPUT_STALE,
                       "frozen impact proof must revalidate as valid_reused; recompute it from change_roots",
                       {"status": result.get("status"), "invalidated_partitions": result.get("invalidated_partitions")})
    else:
        result = closure.compute_impact_closure(root_path, change_roots=change_roots,
                                                manifest_paths=impact_manifest_paths,
                                                operation="verification_scope_impact")
        if not result.get("ok"):
            diag = (result.get("diagnostics") or [{}])[0]
            try:
                reason = codec.ReasonCode(diag.get("reason_code"))
            except ValueError:
                reason = codec.ReasonCode.UNRESOLVED_REFERENCE
            raise _err(reason, "computable Story 4.1 impact closure", diag)
    if result.get("plan_ids_filter"):
        raise _err(codec.ReasonCode.CONFLICT,
                   "impact proof must cover every committed plan; a plan filter would crop obligations",
                   result.get("plan_ids_filter"))
    return result


def _normalize_manifests(root_path: Path, values: Any, label: str) -> list[str]:
    if values is None:
        return []
    if type(values) not in (list, tuple):
        raise _err(codec.ReasonCode.INVALID_ARGUMENT, f"{label} list", type(values).__name__)
    result: set[str] = set()
    for value in values:
        if type(value) is not str or not value.strip():
            raise _err(codec.ReasonCode.INVALID_ARGUMENT, f"nonempty {label} path", value)
        rel = closure._normalize_rel(value)
        if not rel.endswith(".json"):
            raise _err(codec.ReasonCode.INVALID_ARGUMENT, f"{label} *.json path", rel, stage=codec.Stage.PATH)
        closure._safe_target(root_path, rel)
        result.add(rel)
    return sorted(result)


def _normalize_ids(values: Any, label: str) -> list[str]:
    if values is None:
        return []
    if type(values) not in (list, tuple):
        raise _err(codec.ReasonCode.INVALID_ARGUMENT, f"{label} list", type(values).__name__)
    result: set[str] = set()
    for value in values:
        if type(value) is not str or not closure.LOOSE_IDENT_RE.fullmatch(value):
            raise _err(codec.ReasonCode.INVALID_ARGUMENT, f"portable {label}", value)
        result.add(value)
    return sorted(result)


def _normalize_tasks(values: Any) -> list[int]:
    if values is None:
        return []
    if type(values) not in (list, tuple):
        raise _err(codec.ReasonCode.INVALID_ARGUMENT, "in_scope_task_ids list", type(values).__name__)
    result: set[int] = set()
    for value in values:
        if type(value) is str and closure.TASK_ID_RE.fullmatch(value):
            value = int(value)
        if type(value) is not int:
            raise _err(codec.ReasonCode.INVALID_ARGUMENT, "strict positive integer task id", value)
        result.add(codec.validate_task_id(value))
    return sorted(result)


def _delivery_scope(ctx: _Ctx, index: _Index, tasks: list[int], plans: list[str], flows: list[str]) -> dict[str, set]:
    scope_flows = set(flows)
    for fid in flows:
        if fid not in index.flows and fid not in index.plan_flow_owner and fid not in index.flow_plans:
            ctx.gap(f"flow:{fid}", "unknown_in_scope_flow")
    for pid in plans:
        if pid not in ctx.plans:
            ctx.gap(f"plan:{pid}", "unknown_in_scope_plan")
        elif pid not in ctx.bindings:
            ctx.gap(f"plan:{pid}", "missing_stage5_binding")
        scope_flows |= set(index.plan_flows.get(pid, [])) | index.binding_flows_by_plan.get(pid, set())
    for tid in tasks:
        scope_flows |= index.mapping_flows_by_task.get(tid, set())
        scope_flows |= {fid for fid, info in index.flows.items() if tid in info["task_ids"]}
    reqs: set[str] = set()
    for fid in scope_flows:
        info = index.flows.get(fid)
        if info:
            reqs |= info["requirement_ids"]
        owner = index.plan_flow_owner.get(fid)
        if owner:
            reqs |= set(closure._str_ids(owner[1].get("requirement_ids")))
    for pid in plans:
        reqs |= set(index.plan_requirements.get(pid, []))
    for tid in tasks:
        reqs |= index.mapping_reqs_by_task.get(tid, set())
    return {"flows": scope_flows, "plans": set(plans), "tasks": set(tasks), "requirements": reqs}


def _build_scope(root_path: Path, *, change_roots: Any, impact_proof: Any, impact_manifest_paths: list[str] | None,
                 tasks: list[int], plans: list[str], flows: list[str], manifests: list[str], cumulative: list[str],
                 delta: dict[str, Any] | None, operation: str, delta_path: str | None = None) -> dict[str, Any]:
    proof_filter: list[str] = []
    if impact_proof is not None and (change_roots is None or change_roots == []):
        impact_proof = closure._load_proof(root_path, impact_proof)
        declared = impact_proof.get("manifest_paths_filter") if type(impact_proof) is dict else None
        if type(declared) is list and all(type(p) is str and p.strip() for p in declared):
            proof_filter = _normalize_manifests(root_path, declared, "impact proof manifest")
    if impact_manifest_paths is None:
        impact_manifest_paths = sorted(set(manifests) | set(cumulative) | set(proof_filter))
    # The exact manifest set of the impact proof is loaded so --impact-proof and --change-root agree on scope_id.
    manifests = sorted(set(manifests) | (set(proof_filter) - set(cumulative)))
    proof = _resolve_impact(root_path, change_roots=change_roots, impact_proof=impact_proof,
                            impact_manifest_paths=impact_manifest_paths)
    ctx = _Ctx(root_path)
    _load_records(ctx)
    _load_manifests(ctx, manifests, cumulative)
    index = _Index()
    _index_manifests(ctx, index)
    _index_records(ctx, index)
    _guard_reclassification(ctx, index)
    scope = _delivery_scope(ctx, index, tasks, plans, flows)
    builder = _Builder(ctx, index, proof, scope)
    builder.build_other_verification()
    candidate_flows = builder.candidate_flows() | builder.linked_mvg_flows()
    builder.build_tests(candidate_flows)
    builder.build_flows_without_tests(candidate_flows)
    builder.build_binding_obligations(candidate_flows)
    builder.build_impl_objects()
    applied, delta_refs = _apply_delta(ctx, index, builder, delta, delta_path)
    builder.build_manual(candidate_flows | {f for o in builder.obligations.values() for f in o["flow_ids"]})
    task_inputs = _task_input_sets(ctx, tasks)
    for item in task_inputs:
        tid = item["task_id"]
        if item["route"] == "B" and tid not in index.mapping_flows_by_task and tid not in index.mapping_reqs_by_task:
            ctx.gap(f"task:{tid}", "missing_stage5_binding")
    for fid in flows:
        owner = index.plan_flow_owner.get(fid)
        if owner and owner[0] not in ctx.bindings:
            ctx.gap(f"flow:{fid}", "missing_stage5_binding")

    records = [builder.obligations[k] for k in sorted(builder.obligations)]
    plan_view = _execution_plan(records)
    classifications = _flow_classifications(records, scope["flows"])
    obligations = [_finalize_obligation(rec) for rec in records]
    gaps = sorted(ctx.gaps, key=lambda g: (g["entity"], g["reason"]))
    open_current = [o for o in obligations if o["tier"] in CURRENT_TIERS and o["status"] in OPEN_STATUSES]
    closable = not open_current and not gaps

    def descriptor(rel: str) -> dict[str, Any]:
        m = ctx.manifests[rel]
        return {"manifest_id": m["mvg_id"], "path": rel, "manifest_sha256": m["sha256"], "roles": sorted(m["roles"])}

    active_refs = [descriptor(r) for r in sorted(ctx.manifests) if "active" in ctx.manifests[r]["roles"]]
    baseline_refs = [descriptor(r) for r in sorted(ctx.manifests) if "baseline" in ctx.manifests[r]["roles"]]
    boundary = {
        "in_scope_plan_ids": sorted(scope["plans"]),
        "in_scope_task_ids": sorted(scope["tasks"]),
        "in_scope_flow_ids": sorted(scope["flows"]),
        "in_scope_requirement_ids": sorted(scope["requirements"]),
        "baseline_manifest_refs": sorted(r["path"] for r in baseline_refs),
        "active_manifest_refs": sorted(r["path"] for r in active_refs),
    }
    impact_binding = {
        "impact_proof_id": proof["impact_proof_id"],
        "impact_input_digest": proof["impact_input_digest"],
        "partition_digests": dict(sorted(proof["partition_digests"].items())),
        "conservative_expanded": bool(proof["conservative_expanded"]),
        "unknown_items": [{k: (u.get(k) if type(u.get(k)) is str and u.get(k).strip() else None)
                           for k in ("entity", "reason", "owning_stage", "authority_ref", "partition_key")}
                          for u in proof.get("unknown_items") or [] if type(u) is dict],
        "expansion_reasons": [r for r in proof.get("expansion_reasons") or [] if type(r) is str and r.strip()],
        "transitive_summary": {
            "flows": len(proof.get("impacted_flows") or []), "tasks": len(proof.get("impacted_tasks") or []),
            "tests": len(proof.get("impacted_tests") or []),
            "requirements": len(proof.get("impacted_requirements") or []),
            "obligations": len(proof.get("impacted_obligations") or []),
            "other_verification": len(proof.get("other_verification_sinks") or []),
            "implementation_objects": len(proof.get("impacted_implementation_objects") or []),
        },
    }
    authority_refs = {
        "plan_refs": copy.deepcopy(ctx.plan_refs),
        "binding_refs": copy.deepcopy(ctx.binding_refs),
        "manifest_refs": active_refs,
        "cumulative_baseline_refs": baseline_refs,
        "governed_delta_refs": delta_refs,
    }
    input_digest = codec.canonical_digest({
        "task_input_set_digests": [[t["task_id"], t["input_set_digest"]] for t in task_inputs],
        "impact_input_digest": proof["impact_input_digest"],
        "manifests": [[r, ctx.manifests[r]["sha256"]] for r in sorted(ctx.manifests)],
        "plans": [[p, ctx.plans[p]["raw_digest"]] for p in sorted(ctx.plans)],
        "bindings": [[b["path"], b["raw_digest"]] for b in sorted(ctx.binding_docs, key=lambda b: b["path"])],
        "delivery_boundary": boundary,
        "governed_delta_refs": delta_refs,
    })
    result: dict[str, Any] = {
        "schema_version": SCHEMA,
        "ok": True,
        "status": "scope_built",
        "operation": operation,
        "reason_code": codec.ReasonCode.OK.value,
        "generated_at": _now(),
        "scope_id": "",
        "input_set_digest": input_digest,
        "task_input_set_digests": task_inputs,
        "request": {
            "change_roots": [{"kind": r["kind"], "id": r["id"]} for r in proof["change_roots"]],
            "impact_manifest_paths": sorted(proof.get("manifest_paths_filter") or []),
            "in_scope_task_ids": list(tasks),
            "in_scope_plan_ids": list(plans),
            "in_scope_flow_ids": list(flows),
            "manifest_paths": list(manifests),
            "cumulative_baseline_manifests": list(cumulative),
            "scope_delta": copy.deepcopy(delta),
        },
        "delivery_boundary": boundary,
        "authority_refs": authority_refs,
        "change_roots": [{"kind": r["kind"], "id": r["id"]} for r in proof["change_roots"]],
        "impact_binding": impact_binding,
        "obligations": obligations,
        "flow_classifications": classifications,
        "execution_plan": plan_view,
        "applied_delta_changes": applied,
        "blocking_gaps": gaps,
        "scope_status": "executable_ready" if closable else "blocked_incomplete_or_broken",
        "scope_closable": closable,
        "all_current_obligations_executable": closable,
        "diagnostics": [],
        "report_path": None,
        "metrics": {},
        **INVARIANT_FLAGS,
    }
    _seal(result)
    schema_resources.validate(result, SCHEMA, auxiliary=True)
    return result


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _blocked(diag: dict[str, Any], operation: Any, started: float, schema: str = SCHEMA) -> dict[str, Any]:
    return {
        "schema_version": schema,
        "ok": False,
        "status": "blocked",
        "operation": operation if type(operation) is str else None,
        "reason_code": diag.get("reason_code"),
        "scope_id": None,
        "scope_status": None,
        "scope_closable": False,
        "diagnostics": [diag],
        "report_path": None,
        "metrics": {"active_elapsed_seconds": _elapsed(started)},
        **INVARIANT_FLAGS,
    }


def _no_reparse_chain(target: Path, rel: str) -> None:
    try:
        for ancestor in reversed((target.parent, *target.parent.parents)):
            closure.inventory.no_reparse(ancestor)
        if os.path.lexists(target):
            closure.inventory.no_reparse(target)
    except ValueError as exc:
        raise _err(codec.ReasonCode.UNSAFE_PATH, "output path without reparse ancestors or leaf", rel, entity=rel,
                   stage=codec.Stage.PATH) from exc


def _write_report(target: Path, rel: str, payload: dict[str, Any]) -> None:
    if os.path.lexists(target):
        raise _err(codec.ReasonCode.CONFLICT, "new non-existing report path", rel, entity=rel, stage=codec.Stage.PATH)
    target.parent.mkdir(parents=True, exist_ok=True)
    _no_reparse_chain(target, rel)
    payload["report_path"] = rel
    try:
        with open(target, "xb") as handle:
            handle.write((closure._dumps(payload) + "\n").encode("utf-8"))
    except FileExistsError as exc:
        payload["report_path"] = None
        raise _err(codec.ReasonCode.CONFLICT, "new non-existing report path", rel, entity=rel,
                   stage=codec.Stage.PATH) from exc
    _no_reparse_chain(target, rel)


def _append_event(target: Path, payload: dict[str, Any], rel: str = "events") -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    _no_reparse_chain(target, rel)
    record = {
        "event": "b_route_verification_scope",
        "schema_version": payload.get("schema_version"),
        "operation": payload.get("operation"),
        "ok": payload.get("ok"),
        "status": payload.get("status"),
        "reason_code": payload.get("reason_code"),
        "scope_id": payload.get("scope_id") or payload.get("old_scope_id"),
        "scope_status": payload.get("scope_status"),
        "report_path": payload.get("report_path"),
        "active_elapsed_seconds": (payload.get("metrics") or {}).get("active_elapsed_seconds"),
    }
    with open(target, "ab") as handle:
        handle.write((closure._dumps(record) + "\n").encode("utf-8"))


def _finish(payload: dict[str, Any], report: tuple[Path, str] | None, events: tuple[Path, str] | None,
            started: float) -> dict[str, Any]:
    payload["metrics"] = {"active_elapsed_seconds": _elapsed(started)}
    if report is not None and payload.get("ok"):
        try:
            _write_report(report[0], report[1], payload)
        except codec.CodecError as err:
            payload = _blocked(err.diagnostic.to_dict(), payload.get("operation"), started,
                               payload.get("schema_version") or SCHEMA)
        except (OSError, ValueError) as exc:
            payload = _blocked(closure._io_diag(exc), payload.get("operation"), started,
                               payload.get("schema_version") or SCHEMA)
    if events is not None:
        try:
            _append_event(events[0], payload, events[1])
        except (codec.CodecError, OSError, ValueError) as exc:
            # A failed audit event never silently passes a successful result.
            if payload.get("ok"):
                diag = exc.diagnostic.to_dict() if isinstance(exc, codec.CodecError) else closure._io_diag(exc)
                payload = _blocked(diag, payload.get("operation"), started, payload.get("schema_version") or SCHEMA)
    return payload


def _load_scope(root_path: Path, scope_or_path: Any) -> dict[str, Any]:
    if type(scope_or_path) is dict:
        codec.validate_json_value(scope_or_path)
        return copy.deepcopy(scope_or_path)
    if type(scope_or_path) is str and scope_or_path.strip():
        rel = closure._normalize_rel(scope_or_path, allow_logs=True)
        raw = closure._read_bytes(root_path, rel, allow_logs=True)
        if raw is None:
            raise _err(codec.ReasonCode.FILE_NOT_FOUND, "existing VerificationScope file", rel, entity=rel,
                       stage=codec.Stage.PATH)
        return codec.strict_json_loads(raw)
    raise _err(codec.ReasonCode.INVALID_ARGUMENT, "VerificationScope object or repository-relative path",
               type(scope_or_path).__name__)


def _check_scope(scope: Any) -> dict[str, Any]:
    if type(scope) is not dict or "schema_version" not in scope:
        raise _err(codec.ReasonCode.SCHEMA_VALIDATION_FAILED, "VerificationScope object with schema_version",
                   type(scope).__name__, stage=codec.Stage.SCHEMA)
    if scope.get("schema_version") != SCHEMA:
        raise _err(codec.ReasonCode.UNKNOWN_SCHEMA, SCHEMA, scope.get("schema_version"), stage=codec.Stage.SCHEMA)
    schema_resources.validate(scope, SCHEMA, auxiliary=True)
    try:
        expected = codec.canonical_digest(_scope_body(scope))
    except (TypeError, ValueError, codec.CodecError) as exc:
        raise _err(codec.ReasonCode.SCHEMA_VALIDATION_FAILED, "canonicalizable scope body", str(exc),
                   stage=codec.Stage.SCHEMA) from exc
    if expected != scope["scope_id"]:
        raise _err(codec.ReasonCode.DIGEST_MISMATCH, "scope_id seals the canonical scope body",
                   {"declared": scope["scope_id"], "recomputed": expected}, stage=codec.Stage.SCHEMA)
    for obl in scope["obligations"]:
        if obl["claimed_passed"] is not False:
            raise _err(codec.ReasonCode.SEMANTIC_ERROR, "claimed_passed=false", obl["obligation_id"])
    ready = {o["obligation_id"] for o in scope["obligations"]
             if o["status"] == "ready_to_execute" and o["tier"] in CURRENT_TIERS}
    for item in scope["execution_plan"]["executable_tests"]:
        if item["obligation_id"] not in ready:
            raise _err(codec.ReasonCode.SEMANTIC_ERROR, "executable tests only for ready current obligations",
                       item["obligation_id"])
    _check_semantics(scope)
    return scope


def _bucket_mismatch(expected: Any, actual: Any, bucket: str) -> codec.CodecError:
    return _err(codec.ReasonCode.SCHEMA_VALIDATION_FAILED, f"execution_plan.{bucket} consistent with obligations",
                {"expected": expected, "actual": actual}, stage=codec.Stage.SCHEMA)


def _check_semantics(scope: dict[str, Any]) -> None:
    """Reject semantically contradictory scopes even when an attacker recomputes scope_id over them."""
    obligations = {o["obligation_id"]: o for o in scope["obligations"]}
    if len(obligations) != len(scope["obligations"]):
        raise _bucket_mismatch("unique obligation ids", len(scope["obligations"]), "obligations")
    plan = scope["execution_plan"]
    open_current = sorted(oid for oid, o in obligations.items() if o["tier"] in CURRENT_TIERS
                          and o["status"] in OPEN_STATUSES)
    blocking_pending = sorted(p["obligation_id"] for p in plan["pending_obligations"] if p["blocking_current_delivery"])
    invalid_inputs = sorted(t["task_id"] for t in scope["task_input_set_digests"] if not t["valid_input_set"])
    expected_closable = not open_current and not scope["blocking_gaps"] and not blocking_pending and not invalid_inputs
    if scope["scope_closable"] != expected_closable or (scope["scope_status"] == "executable_ready") != expected_closable:
        raise _err(codec.ReasonCode.CONFLICT,
                   "scope_closable/scope_status never claim closure while current obligations are pending/blocked, "
                   "blocking pending work remains or the task InputSet is invalid",
                   {"scope_closable": scope["scope_closable"], "scope_status": scope["scope_status"],
                    "open_current": open_current, "blocking_pending": blocking_pending,
                    "invalid_input_sets": invalid_inputs}, stage=codec.Stage.SCHEMA)
    expected_pending = sorted(oid for oid, o in obligations.items() if o["status"] in OPEN_STATUSES
                              or (o["status"] == "tracked_future" and o["evidence_level"] != "manual"))
    actual_pending = sorted(p["obligation_id"] for p in plan["pending_obligations"])
    if expected_pending != actual_pending:
        raise _bucket_mismatch(expected_pending, actual_pending, "pending_obligations")
    for item in plan["pending_obligations"]:
        rec = obligations[item["obligation_id"]]
        if (item["tier"], item["status"], item["blocking_current_delivery"]) != \
                (rec["tier"], rec["status"], rec["blocking_current_delivery"]):
            raise _bucket_mismatch([rec["tier"], rec["status"]], [item["tier"], item["status"]], "pending_obligations")
    expected_exec = sorted(oid for oid, o in obligations.items() if o["tier"] in CURRENT_TIERS
                           and o["status"] == "ready_to_execute")
    actual_exec = sorted({t["obligation_id"] for t in plan["executable_tests"]})
    if expected_exec != actual_exec or any(t["tier"] != obligations[t["obligation_id"]]["tier"]
                                           for t in plan["executable_tests"]):
        raise _bucket_mismatch(expected_exec, actual_exec, "executable_tests")
    expected_manual = sorted(oid for oid, o in obligations.items() if oid.startswith("manual:")
                             or (oid.startswith("other_verification:") and o["tier"] in CURRENT_TIERS
                                 and o["status"] == "manual_required"))
    actual_manual = sorted(m["manual_id"] for m in plan["manual_obligations"])
    if expected_manual != actual_manual or any(m["tier"] != obligations[m["manual_id"]]["tier"]
                                               for m in plan["manual_obligations"]):
        raise _bucket_mismatch(expected_manual, actual_manual, "manual_obligations")
    actual_other = sorted(o["obligation_id"] for o in plan["other_verification_obligations"])
    required_other = sorted(oid for oid, o in obligations.items() if oid.startswith("other_verification:")
                            or o["execution_kind"] == "other_verification")
    if not set(required_other) <= set(actual_other) or not set(actual_other) <= set(obligations):
        raise _bucket_mismatch(required_other, actual_other, "other_verification_obligations")
    for item in plan["other_verification_obligations"]:
        rec = obligations[item["obligation_id"]]
        if (item["tier"], item["status"]) != (rec["tier"], rec["status"]):
            raise _bucket_mismatch([rec["tier"], rec["status"]], [item["tier"], item["status"]],
                                   "other_verification_obligations")
    binding = scope["impact_binding"]
    if codec.canonical_digest({"partition_digests": binding["partition_digests"]}) != binding["impact_input_digest"]:
        raise _err(codec.ReasonCode.DIGEST_MISMATCH, "impact_input_digest matches partition_digests",
                   binding["impact_input_digest"], stage=codec.Stage.SCHEMA)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_verification_scope(root: Any, *, change_roots: Any = None, impact_proof: Any = None,
                             in_scope_task_ids: Any = None, in_scope_plan_ids: Any = None,
                             in_scope_flow_ids: Any = None, manifest_paths: Any = None,
                             cumulative_baseline_manifests: Any = None, scope_delta: Any = None,
                             operation: str = "build_verification_scope", report_path: str | None = None,
                             events_log_path: str | None = None) -> dict[str, Any]:
    """Build a sealed, schema-valid three-tier VerificationScope without mutating repository state."""
    started = time.monotonic()
    report = events = None
    try:
        root_path = closure._validate_root(root)
        operation = closure._validate_operation(operation)
        report, events = closure._validate_outputs(root_path, report_path, events_log_path)
        delta_doc, delta_path = _load_delta(root_path, scope_delta)
        result = _build_scope(
            root_path, change_roots=list(change_roots) if type(change_roots) in (list, tuple) else change_roots,
            impact_proof=impact_proof, impact_manifest_paths=None, tasks=_normalize_tasks(in_scope_task_ids),
            plans=_normalize_ids(in_scope_plan_ids, "plan id"), flows=_normalize_ids(in_scope_flow_ids, "flow id"),
            manifests=_normalize_manifests(root_path, manifest_paths, "manifest"),
            cumulative=_normalize_manifests(root_path, cumulative_baseline_manifests, "cumulative manifest"),
            delta=delta_doc, operation=operation, delta_path=delta_path)
        return _finish(result, report, events, started)
    except codec.CodecError as err:
        payload = _blocked(err.diagnostic.to_dict(), operation, started)
    except (ValueError, OSError) as exc:
        payload = _blocked(closure._io_diag(exc), operation, started)
    return _finish(payload, None, events, started)


def validate_verification_scope(root: Any, scope_or_path: Any) -> dict[str, Any]:
    """Validate schema, invariants and the cryptographic scope_id of a generated or loaded scope."""
    started = time.monotonic()
    try:
        root_path = closure._validate_root(root)
        scope = _check_scope(_load_scope(root_path, scope_or_path))
    except codec.CodecError as err:
        return _blocked(err.diagnostic.to_dict(), "validate_verification_scope", started, VALIDATION_SCHEMA)
    except (ValueError, OSError) as exc:
        return _blocked(closure._io_diag(exc), "validate_verification_scope", started, VALIDATION_SCHEMA)
    return {
        "schema_version": VALIDATION_SCHEMA,
        "ok": True,
        "status": "valid",
        "valid": True,
        "operation": "validate_verification_scope",
        "reason_code": codec.ReasonCode.OK.value,
        "scope_id": scope["scope_id"],
        "scope_status": scope["scope_status"],
        "scope_closable": scope["scope_closable"],
        "diagnostics": [],
        "report_path": None,
        "metrics": {"active_elapsed_seconds": _elapsed(started)},
        **INVARIANT_FLAGS,
    }


def _normalize_conclusions(root_path: Path, prior: Any) -> list[dict[str, Any]]:
    if prior is None:
        return []
    if type(prior) is str and prior.strip():
        rel = closure._normalize_rel(prior, allow_logs=True)
        raw = closure._read_bytes(root_path, rel, allow_logs=True)
        if raw is None:
            raise _err(codec.ReasonCode.FILE_NOT_FOUND, "existing prior conclusions JSON file", rel, entity=rel,
                       stage=codec.Stage.PATH)
        prior = codec.strict_json_loads(raw)
        if type(prior) is dict and set(prior) == {"prior_conclusions"}:
            prior = prior["prior_conclusions"]
    if type(prior) not in (list, tuple):
        raise _err(codec.ReasonCode.INVALID_ARGUMENT, "prior_conclusions list", type(prior).__name__)
    result = []
    for item in prior:
        if type(item) is not dict or type(item.get("conclusion_id")) is not str or not item["conclusion_id"].strip():
            raise _err(codec.ReasonCode.INVALID_ARGUMENT, "prior conclusion object with conclusion_id", item)
        result.append(item)
    return result


def revalidate_verification_scope(root: Any, scope_or_path: Any, *, prior_conclusions: Any = None,
                                  report_path: str | None = None, events_log_path: str | None = None
                                  ) -> dict[str, Any]:
    """Recompute live inputs; same effective inputs keep scope_id, relevant drift invalidates affected conclusions."""
    started = time.monotonic()
    operation = "revalidate_verification_scope"
    report = events = None
    try:
        root_path = closure._validate_root(root)
        report, events = closure._validate_outputs(root_path, report_path, events_log_path)
        old = _check_scope(_load_scope(root_path, scope_or_path))
        conclusions = _normalize_conclusions(root_path, prior_conclusions)
        request = old["request"]
        replacement = None
        replacement_diag = None
        try:
            replacement = _build_scope(
                root_path, change_roots=request["change_roots"], impact_proof=None,
                impact_manifest_paths=list(request["impact_manifest_paths"]), tasks=list(request["in_scope_task_ids"]),
                plans=list(request["in_scope_plan_ids"]), flows=list(request["in_scope_flow_ids"]),
                manifests=list(request["manifest_paths"]), cumulative=list(request["cumulative_baseline_manifests"]),
                delta=_load_delta(root_path, request["scope_delta"])[0] if request["scope_delta"] is not None else None,
                operation=operation)
        except codec.CodecError as err:
            replacement_diag = err.diagnostic.to_dict()
        old_map = {o["obligation_id"]: o for o in old["obligations"]}
        same = replacement is not None and replacement["scope_id"] == old["scope_id"]
        new_map: dict[str, dict[str, Any]] = {}
        task_drift: list[int] = []
        delta_ref_drift = False
        if replacement is None:
            invalidated = sorted(old_map)
            new_ids: list[str] = []
            unattributed = True
        else:
            new_map = {o["obligation_id"]: o for o in replacement["obligations"]}
            invalidated = sorted(oid for oid, obl in old_map.items()
                                 if oid not in new_map or new_map[oid]["input_fingerprint"] != obl["input_fingerprint"])
            new_ids = sorted(set(new_map) - set(old_map))
            old_tasks = {t["task_id"]: t for t in old["task_input_set_digests"]}
            new_tasks = {t["task_id"]: t for t in replacement["task_input_set_digests"]}
            task_drift = sorted(t for t in set(old_tasks) | set(new_tasks) if old_tasks.get(t) != new_tasks.get(t))
            delta_ref_drift = old["authority_refs"]["governed_delta_refs"] != \
                replacement["authority_refs"]["governed_delta_refs"]
            if task_drift:
                invalidated = sorted(set(invalidated) | {oid for oid, obl in old_map.items()
                                                         if set(obl["task_ids"]) & set(task_drift)})
            unattributed = not same and not invalidated and not new_ids and not task_drift and not delta_ref_drift
            if unattributed:
                invalidated = sorted(old_map)
        affected = [old_map[oid] for oid in invalidated] + [new_map[oid] for oid in new_ids]
        invalid_flows = sorted({f for obl in affected for f in obl["flow_ids"]})
        invalid_reqs = {r for obl in affected for r in obl["requirement_ids"]}
        invalid_tests = {t for obl in affected for t in obl["test_ids"]}
        if replacement is not None and not same:
            old_flows = {f["flow_id"]: f for f in old["flow_classifications"]}
            new_flows = {f["flow_id"]: f for f in replacement["flow_classifications"]}
            for fid in set(old_flows) | set(new_flows):
                if old_flows.get(fid) != new_flows.get(fid):
                    invalid_flows = sorted(set(invalid_flows) | {fid})
        invalid_set, flow_set, drift_tasks = set(invalidated), set(invalid_flows), set(task_drift)
        assessed = []
        for item in conclusions:
            reasons = []
            if item.get("scope_id") is not None and item.get("scope_id") != old["scope_id"]:
                reasons.append("scope_id_mismatch")
            selectors = {key: set(_strings(item.get(key) or [])) for key in
                         ("obligation_ids", "flow_ids", "test_ids", "requirement_ids")}
            tasks = {t for t in item.get("task_ids") or [] if type(t) is int}
            if not same:
                if replacement is None:
                    reasons.append("replacement_scope_blocked")
                if invalid_set & selectors["obligation_ids"]:
                    reasons.append("obligation_invalidated")
                if flow_set & selectors["flow_ids"]:
                    reasons.append("flow_invalidated")
                if invalid_tests & selectors["test_ids"]:
                    reasons.append("test_invalidated")
                if invalid_reqs & selectors["requirement_ids"]:
                    reasons.append("requirement_invalidated")
                if drift_tasks & tasks:
                    reasons.append("task_input_set_drift")
                if not any(selectors.values()) and not tasks:
                    reasons.append("selectorless_conclusion_on_drift")
                if delta_ref_drift:
                    reasons.append("governed_delta_ref_drift")
                if unattributed:
                    reasons.append("unattributed_drift")
            assessed.append({"conclusion_id": item["conclusion_id"],
                             "status": "invalidated" if reasons else "retained", "reasons": sorted(set(reasons))})
        payload = {
            "schema_version": REVALIDATION_SCHEMA,
            "ok": True,
            "status": "valid" if same else "stale",
            "operation": operation,
            "reason_code": codec.ReasonCode.OK.value if same else codec.ReasonCode.INPUT_STALE.value,
            "valid": same,
            "stale": not same,
            "same_scope_id": same,
            "old_scope_id": old["scope_id"],
            "replacement_scope_id": replacement["scope_id"] if replacement is not None else None,
            "invalidated_obligations": [] if same else invalidated,
            "invalidated_flows": [] if same else invalid_flows,
            "new_obligations": [] if same else new_ids,
            "task_input_set_drift": [] if same else task_drift,
            "governed_delta_ref_drift": False if same else delta_ref_drift,
            "unattributed_drift": False if same else unattributed,
            "prior_conclusions": assessed,
            "invalidated_prior_conclusions": [c["conclusion_id"] for c in assessed if c["status"] == "invalidated"],
            "retained_prior_conclusions": [c["conclusion_id"] for c in assessed if c["status"] == "retained"],
            "replacement_scope": replacement,
            "replacement_blocked": replacement_diag,
            "scope_status": replacement["scope_status"] if replacement is not None else None,
            "diagnostics": [replacement_diag] if replacement_diag else [],
            "report_path": None,
            "metrics": {},
            **INVARIANT_FLAGS,
        }
        return _finish(payload, report, events, started)
    except codec.CodecError as err:
        payload = _blocked(err.diagnostic.to_dict(), operation, started, REVALIDATION_SCHEMA)
    except (ValueError, OSError) as exc:
        payload = _blocked(closure._io_diag(exc), operation, started, REVALIDATION_SCHEMA)
    return _finish(payload, None, events, started)
