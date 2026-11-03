"""Behavioral evidence for the Story 1.4 public record contract."""

from __future__ import annotations

from copy import deepcopy
import builtins
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import _b_route_codec as codec
import _b_route_records as records


REPOSITORY = Path(__file__).resolve().parents[3]
PREFIX = "docs/planning/b-route/"
CATALOG = PREFIX + "catalog.v1.json"
POLICY = PREFIX + "policy.v1.json"
ORIGINS = PREFIX + "task-origins.v1.json"
PARTS = ("domain_rules", "csharp_adapter", "binding", "scene")
DIAGNOSTIC_FIELDS = {"reason_code", "stage", "entity_id", "expected", "actual", "resume_ref"}


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical(value):
    return digest(json.dumps(value, ensure_ascii=False, sort_keys=True,
                             separators=(",", ":")).encode("utf-8"))


def plan_path(plan_id="p", revision=2):
    return PREFIX + f"plans/{plan_id}/{revision}.json"


def binding_path(plan_id="p", revision=7):
    return PREFIX + f"bindings/{plan_id}/{revision}.json"


def logical(kind, definition_id, plan_id, revision):
    return {"kind": kind, "definition_id": definition_id,
            "owner_plan_id": plan_id, "owner_revision": revision}


def part(kind):
    return {"kind": kind, "applicability": "applicable", "rationale": "Declared responsibility",
            "responsibilities": ["Preserve the documented boundary"]}


def flow(flow_id, requirement_id):
    return {
        "id": flow_id, "requirement_ids": [requirement_id], "entry": "Submit",
        "entry_condition": "A request is available", "success_end": "Return",
        "branches": [{"kind": "return", "rationale": "Retry is allowed",
                      "description": "Return to the entry after a rejected request"}],
        "handoffs": [], "state_owners": [], "parts": [part(kind) for kind in PARTS],
        "observable_result": "The caller observes the result", "verification_targets": ["result"],
        "loops": [{"description": "Retry may return to entry",
                   "exit_condition": "The caller accepts or cancels"}],
    }


class MatrixFixture:
    """Construct independently hashed bytes, without calling production validators."""

    def __init__(self):
        self.artifacts = {}
        self.models = {}
        self.bindings = {}
        self.current_plans = []
        self.current_bindings = []
        self.hooks = {}
        self.ref_changes = {}
        self.resolved = []
        self.operation_id = "operation-1"
        self.artifacts["sources/input.md"] = b"# Requirement\nPreserve the result.\n"
        source_binding = [{"path": "sources/input.md", "source_type": "markdown",
                           "sha256": digest(self.artifacts["sources/input.md"])}]
        self.native_digest = canonical(source_binding)
        self.source_revision = "source-set:" + self.native_digest[7:31]
        self.artifacts["sources/manifest.json"] = encoded({
            "schema_version": "chapter3.source-manifest.v1", "source_revision": self.source_revision,
            "manifest_sha256": self.native_digest, "sources": source_binding,
        })
        self.artifacts["sources/ledger.json"] = encoded({
            "schema_version": "newrouge.source-blocks.v1", "source_revision": self.source_revision,
            "source_manifest_sha256": self.native_digest,
            "blocks": [{"block_id": "BLOCK-1", "source_path": "sources/input.md"}],
        })
        self.artifacts["evidence/admission.json"] = encoded({"selected_candidate": "candidate-1"})
        self.policy = {
            "schema_version": "newrouge.b-route-policy.v1", "policy_id": "policy-1",
            "policy_revision": 1, "switch_boundary": {
                "default_route": "A", "a_write_allowed": True,
                "allowed_a_operations": ["resume-task"], "authority_refs": [],
            }, "frozen_a_refs": [],
        }
        self.add_plan()
        self.last_documents = {}

    def owned(self, owner, reference, paths=None):
        paths = paths or [reference.split("#", 1)[0]]
        return {"owner": owner, "ref": reference,
                "files": [{"path": path, "raw_digest": digest(self.artifacts[path])}
                          for path in paths]}

    def add_plan(self, plan_id="p", revision=2):
        path = plan_path(plan_id, revision)
        rid = "REQ-" + plan_id
        verification = {
            "requirement_id": rid, "disposition": "source_gap", "flow_id": None,
            "rationale": "The missing source remains explicit", "sink_id": None,
            "verification_ref": None, "authority_ref": None, "evidence_ids": [],
        }
        self.models[path] = {
            "schema_version": "newrouge.b-route-plan.v1", "plan_id": plan_id, "revision": revision,
            "source_identity": {
                "manifest_ref": self.owned("source_manifest", "sources/manifest.json"),
                "ledger_ref": self.owned("source_ledger", "sources/ledger.json"),
                "source_revision": self.source_revision, "source_manifest_digest": self.native_digest,
            },
            "requirements": [{"requirement_id": rid, "source_block_ids": ["BLOCK-1"],
                              "acceptance_intent": "Preserve the result", "non_task_sinks": ["sink-1"]}],
            "definitions": {"flows": [], "commands": [], "states": []},
            "logical_references": [], "requirement_verification": [verification],
            "requirement_route_memberships": [], "requirement_evidence": [],
            "evidence_source_refs": [],
            "coverage_table": [{key: value for key, value in verification.items()
                                if key != "evidence_ids"}],
            "applicability": [{"requirement_id": rid, "disposition": "source_gap",
                               "rationale": verification["rationale"], "other_verification_refs": []}],
            "adoption_proof_refs": [self.owned("planning_proof", "evidence/admission.json")],
            "lineage": {"previous_plan_ref": None, "change_summary": "Initial declaration",
                        "identity_alignment": []},
        }
        self.current_plans = [other for other in self.current_plans
                              if self.models[other]["plan_id"] != plan_id] + [path]
        return path

    def set_disposition(self, path, disposition, **changes):
        model = self.models[path]
        row = model["requirement_verification"][0]
        row.update(disposition=disposition, rationale="Explicit " + disposition,
                   flow_id=None, sink_id=None, verification_ref=None, authority_ref=None)
        row.update(changes)
        model["coverage_table"] = [{key: value for key, value in row.items() if key != "evidence_ids"}]
        model["applicability"][0].update(disposition=disposition, rationale=row["rationale"])

    def add_flow(self, path, flow_id=None):
        model = self.models[path]
        rid = model["requirements"][0]["requirement_id"]
        flow_id = flow_id or "flow-" + model["plan_id"]
        model["definitions"]["flows"].append(flow(flow_id, rid))
        self.set_disposition(path, "flow", flow_id=flow_id)
        model["requirement_route_memberships"].append({
            "requirement_id": rid, "flow_id": flow_id, "observable_role": "Observe the result",
        })
        return flow_id

    def add_binding(self, plan_id="p", revision=7, target_plan=None, task_id=11):
        target_plan = target_plan or next(path for path in self.current_plans
                                        if self.models[path]["plan_id"] == plan_id)
        path = binding_path(plan_id, revision)
        rid = self.models[target_plan]["requirements"][0]["requirement_id"]
        self.bindings[path] = {
            "schema_version": "newrouge.b-route-binding.v1", "plan_id": plan_id,
            "binding_revision": revision, "plan_ref": None, "stage": "3C",
            "task_mappings": [{
                "task_id": task_id,
                "view_refs": [{"view": "back", "business_id": f"BACK-{task_id}"},
                              {"view": "gameplay", "business_id": f"GAME-{task_id}"}],
                "requirement_ids": [rid], "flow_ids": [], "part_kinds": ["domain_rules"],
                "roles": ["integration_only_owner"], "obligation_ids": [],
            }],
            "parts": [part("domain_rules")], "implementation_objects": [],
            "obligations": [], "manifest_refs": [], "other_verification_refs": [],
        }, target_plan
        self.current_bindings = [other for other in self.current_bindings
                                 if self.bindings[other][0]["plan_id"] != plan_id] + [path]
        return path

    def use_cycle(self):
        p = plan_path()
        q = self.add_plan("q", 1)
        for path, name in ((p, "p-state"), (q, "q-state")):
            model = self.models[path]
            model["definitions"]["states"] = [{
                "id": name, "requirement_ids": [model["requirements"][0]["requirement_id"]],
                "responsibility": "Own the shared state", "uses": [],
            }]
        self.models[p]["logical_references"] = [logical("state", "q-state", "q", 1)]
        self.models[q]["definitions"]["states"][0]["uses"] = [logical("state", "p-state", "p", 2)]
        self.resolved = [("state", "p-state", p), ("state", "q-state", q)]
        return p, q

    def reference(self, path, output):
        value = json.loads(output[path])
        family = value["schema_version"].split("b-route-", 1)[1].split(".v", 1)[0]
        identity_fields = {
            "policy": ("policy_id", "policy_revision"), "plan": ("plan_id", "revision"),
            "binding": ("plan_id", "binding_revision"), "origins": ("origins_id", "revision"),
            "commit": ("operation_id", "revision"), "catalog": ("catalog_id", "revision"),
        }
        entity, revision = identity_fields[family]
        ref = {"path": path, "schema_version": value["schema_version"], "entity_id": value[entity],
               "revision": value[revision], "digest": digest(output[path]),
               "verification_mode": "raw", "codec_version": None}
        ref.update(self.ref_changes.get(path, {}))
        if ref["verification_mode"] == "canonical" and "digest" not in self.ref_changes.get(path, {}):
            ref["digest"] = canonical(value)
        return ref

    def render(self):
        output = dict(self.artifacts)
        documents = {}

        def put(path, value):
            value = deepcopy(value)
            if path in self.hooks:
                self.hooks[path](value)
            documents[path] = value
            output[path] = encoded(value)

        put(POLICY, self.policy)
        for path, value in self.models.items():
            put(path, value)
        for path, (value, target) in self.bindings.items():
            value = deepcopy(value)
            value["plan_ref"] = self.reference(target, output)
            put(path, value)
        by_task = {}
        for path in self.current_bindings:
            binding = documents[path]
            for mapping in binding["task_mappings"]:
                task_id = mapping["task_id"]
                row = by_task.setdefault(task_id, {"task_id": task_id, "plan_refs": [], "binding_refs": []})
                pref = binding["plan_ref"]
                if pref not in row["plan_refs"]:
                    row["plan_refs"].append(pref)
                row["binding_refs"].append(self.reference(path, output))
        task_rows = list(by_task.values())
        put(ORIGINS, {
            "schema_version": "newrouge.b-route-origins.v1", "origins_id": "task-origins", "revision": 1,
            "tasks": [{**deepcopy(row), "source_refs": [
                self.owned("source_manifest", "sources/manifest.json")]} for row in task_rows],
            "frozen_legacy_refs": [],
        })
        owner_rows = []
        for path in self.current_plans:
            for family, kind in (("flows", "flow"), ("commands", "command"), ("states", "state")):
                owner_rows.extend({"kind": kind, "definition_id": item["id"],
                                   "plan_ref": self.reference(path, output)}
                                  for item in documents[path]["definitions"][family])
        target_paths = [POLICY, ORIGINS, *self.current_plans, *self.current_bindings]
        commit_path = PREFIX + f"commits/{self.operation_id}.json"
        pref = [self.reference(path, output) for path in self.current_plans]
        bref = [self.reference(path, output) for path in self.current_bindings]
        put(commit_path, {
            "schema_version": "newrouge.b-route-commit.v1", "operation_id": self.operation_id,
            "revision": 1, "operation_digest": digest(b"frozen operation request"),
            "scopes": ["scope-main"], "authority": [],
            "targets": [{"path": path, "before_digest": None, "after_digest": digest(output[path]),
                         "verification_mode": "immutable_bytes", "codec_version": None,
                         "projection_digest": digest(output[path])} for path in target_paths],
            "plan_refs": pref, "binding_refs": bref,
            "resolved_definitions": [{"kind": kind, "definition_id": name,
                                      "plan_ref": self.reference(path, output)}
                                     for kind, name, path in self.resolved],
            "result": {"target_paths": target_paths, "scope_ids": ["scope-main"]},
        })
        put(CATALOG, {
            "schema_version": "newrouge.b-route-catalog.v1", "catalog_id": "catalog", "revision": 1,
            "policy_ref": self.reference(POLICY, output), "origins_ref": self.reference(ORIGINS, output),
            "scope_heads": [{"scope_id": "scope-main", "plan_refs": pref, "binding_refs": bref,
                             "receipt_ref": self.reference(commit_path, output)}],
            "definition_owners": owner_rows, "task_index": deepcopy(task_rows),
        })
        self.last_documents = documents
        return output

    def join(self, ids=(11,)):
        return records.TaskJoinContext(
            {"master": {"tasks": [{"id": task_id, "status": "pending", "title": "Existing task"}
                                  for task_id in ids]}},
            [{"id": f"BACK-{task_id}", "taskmaster_id": task_id, "status": "pending"} for task_id in ids],
            [{"id": f"GAME-{task_id}", "taskmaster_id": task_id, "status": "pending"} for task_id in ids],
        )


def mixed_scope_bytes(*, shared_dependency=False):
    first = MatrixFixture()
    first.models.clear()
    first.current_plans.clear()
    p1, q1 = first.add_plan("p", 1), first.add_plan("q", 1)
    for path, name, plan_id in ((p1, "p-state", "p"), (q1, "q-state", "q")):
        first.models[path]["definitions"]["states"] = [{
            "id": name, "requirement_ids": ["REQ-" + plan_id],
            "responsibility": "Own the documented state", "uses": []}]
        first.models[path]["logical_references"] = [logical("state", name, plan_id, 1)]
    if shared_dependency:
        first.models[q1]["logical_references"].append(logical("state", "p-state", "p", 1))
    first.resolved = [("state", "p-state", p1), ("state", "q-state", q1)]
    first.artifacts["evidence/retired-proof.json"] = b'{"historical":"independent proof"}\n'
    first.models[p1]["adoption_proof_refs"] = [
        first.owned("planning_proof", "evidence/retired-proof.json")]
    old = first.render()
    r1path = PREFIX + "commits/operation-1.json"
    r1 = json.loads(old[r1path])
    r1["scopes"] = ["scope-p", "scope-q"]
    r1["result"]["scope_ids"] = ["scope-p", "scope-q"]
    old[r1path] = encoded(r1)

    second = MatrixFixture()
    second.models[plan_path()]["definitions"]["states"] = [{
        "id": "p-state", "requirement_ids": ["REQ-p"],
        "responsibility": "The current state definition", "uses": []}]
    second.models[plan_path()]["logical_references"] = [logical("state", "p-state", "p", 2)]
    second.resolved = [("state", "p-state", plan_path())]
    second.operation_id = "operation-2"
    second.policy["policy_revision"] = 2
    second.hooks[ORIGINS] = lambda value: value.update(revision=2)
    current = second.render()
    r2path = PREFIX + "commits/operation-2.json"
    r2 = json.loads(current[r2path])
    r2["scopes"] = ["scope-p"]
    r2["result"]["scope_ids"] = ["scope-p"]
    current[r2path] = encoded(r2)
    output = {**old, **current}
    del output["evidence/retired-proof.json"]
    catalog = json.loads(current[CATALOG])
    catalog["revision"] = 2
    catalog["scope_heads"] = [
        {"scope_id": "scope-p", "plan_refs": [second.reference(plan_path(), output)],
         "binding_refs": [], "receipt_ref": second.reference(r2path, output)},
        {"scope_id": "scope-q", "plan_refs": [first.reference(q1, output)],
         "binding_refs": [], "receipt_ref": first.reference(r1path, output)},
    ]
    catalog["definition_owners"] = [
        {"kind": "state", "definition_id": "p-state", "plan_ref": second.reference(plan_path(), output)},
        {"kind": "state", "definition_id": "q-state", "plan_ref": first.reference(q1, output)},
    ]
    output[CATALOG] = encoded(catalog)
    return output


def scoped_dependency_bytes(*, global_dependency=False, include_global=False):
    fixture = MatrixFixture()
    p, q, r = plan_path(), fixture.add_plan("q", 1), fixture.add_plan("r", 1)
    dependency = logical("state", "z", "r", 1)
    fixture.models[p]["logical_references"] = [logical("command", "x", "q", 1)]
    fixture.models[q]["definitions"]["commands"] = [
        {"id": "x", "requirement_ids": ["REQ-q"], "responsibility": "The imported command", "uses": []},
        {"id": "y", "requirement_ids": ["REQ-q"], "responsibility": "Another command",
         "uses": [dependency]}]
    fixture.models[r]["definitions"]["states"] = [
        {"id": "z", "requirement_ids": ["REQ-r"], "responsibility": "Own state z", "uses": []}]
    if global_dependency:
        fixture.models[q]["logical_references"] = [dependency]
    output = fixture.render()

    def receipt(operation_id, scopes, plans, resolved):
        target_paths = [POLICY, ORIGINS, *plans]
        result = {
            "schema_version": "newrouge.b-route-commit.v1", "operation_id": operation_id,
            "revision": 1, "operation_digest": digest(operation_id.encode()),
            "scopes": scopes, "authority": [],
            "targets": [{"path": path, "before_digest": None, "after_digest": digest(output[path]),
                         "verification_mode": "immutable_bytes", "codec_version": None,
                         "projection_digest": digest(output[path])} for path in target_paths],
            "plan_refs": [fixture.reference(path, output) for path in plans], "binding_refs": [],
            "resolved_definitions": [{"kind": kind, "definition_id": name,
                                      "plan_ref": fixture.reference(path, output)}
                                     for kind, name, path in resolved],
            "result": {"target_paths": target_paths, "scope_ids": scopes},
        }
        path = PREFIX + f"commits/{operation_id}.json"
        output[path] = encoded(result)
        return path

    other = receipt("operation-1", ["scope-q", "scope-r"], [q, r], [("state", "z", r)])
    selected = [("command", "x", q)]
    if include_global:
        selected.append(("state", "z", r))
    own = receipt("operation-2", ["scope-p"], [p], selected)
    catalog = json.loads(output[CATALOG])
    catalog["scope_heads"] = [
        {"scope_id": scope, "plan_refs": [fixture.reference(plan, output)], "binding_refs": [],
         "receipt_ref": fixture.reference(operation, output)}
        for scope, plan, operation in (("scope-p", p, own), ("scope-q", q, other), ("scope-r", r, other))]
    output[CATALOG] = encoded(catalog)
    return output


def directory_link(link, target):
    if os.name == "nt":
        subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(link), str(target)],
                       check=True, capture_output=True)
    else:
        link.symlink_to(target, target_is_directory=True)


class RecordAssertions(unittest.TestCase):
    def assert_valid(self, result, claim="candidate_structure_only"):
        self.assertTrue(result.ok, result.to_dict())
        self.assertEqual(result.claim, claim)
        self.assertTrue(result.schema_validated)
        self.assertFalse(result.target_projection_verified)
        self.assertEqual(set(result.diagnostic.to_dict()), DIAGNOSTIC_FIELDS)
        self.assertEqual(result.diagnostic.reason_code.value, "ok")
        payload = result.to_dict()
        for forbidden in ("ready", "adopted", "runtime_pass", "runtime_verified", "published"):
            self.assertNotIn(forbidden, payload)

    def assert_invalid(self, result, *codes):
        self.assertFalse(result.ok, result.to_dict())
        self.assertEqual(set(result.diagnostic.to_dict()), DIAGNOSTIC_FIELDS)
        if codes:
            self.assertIn(result.diagnostic.reason_code.value, codes, result.to_dict())
        self.assertFalse(result.references_validated)
        self.assertFalse(result.target_projection_verified)


class RecordSchemaTests(RecordAssertions):
    def test_all_six_records_have_one_structure_claim_and_explicit_limits(self):
        fixture = MatrixFixture()
        fixture.add_binding()
        bundle = fixture.render()
        for path, document in fixture.last_documents.items():
            with self.subTest(path=path):
                result = records.validate_record(bundle[path], path=path)
                self.assert_valid(result, "record_structure_only")
                self.assertFalse(result.references_validated)
                self.assertFalse(result.monotonicity_checked)
                self.assertEqual(result.content_identity.raw_digest, digest(bundle[path]))
                self.assertEqual(result.content_identity.canonical_digest, canonical(document))

    def test_missing_unknown_fields_and_invalid_enum_have_specific_diagnostics(self):
        fixture = MatrixFixture()
        fixture.render()
        cases = [
            (lambda value: value.pop("policy_id"), "missing_required_field"),
            (lambda value: value.update(private_consumer=True), "unknown_field"),
            (lambda value: value["switch_boundary"].update(private_consumer=True), "unknown_field"),
            (lambda value: value["switch_boundary"].update(default_route="legacy"), "invalid_enum"),
        ]
        for mutate, code in cases:
            with self.subTest(code=code, mutation=mutate):
                value = deepcopy(fixture.policy)
                mutate(value)
                self.assert_invalid(records.validate_record(encoded(value), path=POLICY), code)

    def test_unknown_version_does_not_fetch_schema_over_network(self):
        value = deepcopy(MatrixFixture().policy)
        value["schema_version"] = "https://invalid.example/schema.v2"
        with patch("urllib.request.urlopen", side_effect=AssertionError("Network access is forbidden")):
            self.assert_invalid(records.validate_record(encoded(value)), "unknown_schema")

    def test_strict_json_rejects_duplicate_keys_nonfinite_and_bad_utf8(self):
        for raw, code in ((b'{"schema_version":1,"schema_version":2}', "duplicate_key"),
                          (b'{"x":NaN}', "non_finite_number"), (b'{"x":1e999}', "non_finite_number"),
                          (b"\xff", "invalid_utf8")):
            with self.subTest(raw=raw):
                self.assert_invalid(records.validate_record(raw), code)

    def test_revision_and_task_id_never_coerce_bool_float_or_string(self):
        for invalid in (True, False, 1.0, "1", 0, -1):
            with self.subTest(revision=invalid):
                value = deepcopy(MatrixFixture().policy)
                value["policy_revision"] = invalid
                self.assert_invalid(records.validate_record(value), "invalid_type", "schema_validation_failed")
        for invalid in (True, 11.0, "11"):
            with self.subTest(task_id=invalid):
                fixture = MatrixFixture()
                bpath = fixture.add_binding()
                fixture.bindings[bpath][0]["task_mappings"][0]["task_id"] = invalid
                fixture.render()
                self.assert_invalid(records.validate_record(encoded(fixture.last_documents[bpath]), path=bpath),
                                    "invalid_type", "schema_validation_failed")

    def test_identity_fields_are_explicit_and_singletons_are_fixed(self):
        fixture = MatrixFixture()
        fixture.render()
        for path, field, bad in ((ORIGINS, "origins_id", "another"),
                                 (CATALOG, "catalog_id", "another"),
                                 (PREFIX + "commits/operation-1.json", "revision", 2)):
            with self.subTest(path=path):
                value = deepcopy(fixture.last_documents[path])
                del value[field]
                self.assert_invalid(records.validate_record(value), "missing_required_field")
                value[field] = bad
                self.assert_invalid(records.validate_record(value), "invalid_enum", "schema_validation_failed")

    def test_paths_preserve_independent_revisions_and_reject_nonportable_identity(self):
        fixture = MatrixFixture()
        bpath = fixture.add_binding()
        output = fixture.render()
        self.assert_valid(records.validate_record(output[bpath], path=bpath), "record_structure_only")
        for path in (PREFIX + "bindings/p/2.json", PREFIX + "bindings/p/07.json",
                     PREFIX + "plans/p/02.json"):
            raw = output[bpath] if "bindings" in path else output[plan_path()]
            with self.subTest(path=path):
                self.assert_invalid(records.validate_record(raw, path=path))
        for identity in ("CON", "NUL.txt", "bad/name", "..", "bad.", "bad "):
            with self.subTest(identity=identity):
                value = deepcopy(fixture.models[plan_path()])
                value["plan_id"] = identity
                self.assert_invalid(records.validate_record(value))

    def test_single_record_reuses_typed_reference_path_syntax_without_reading_target(self):
        fixture = MatrixFixture()
        bpath = fixture.add_binding()
        fixture.render()
        for unsafe in ("C:/outside.json", "../outside.json", "/outside.json",
                       "inside/../../outside.json", "folder\\outside.json", "NUL.json"):
            with self.subTest(path=unsafe), patch.object(codec, "read_reference_bytes",
                    side_effect=AssertionError("Single-record validation must not read targets")):
                value = deepcopy(fixture.last_documents[bpath])
                value["plan_ref"]["path"] = unsafe
                result = records.validate_record(value, path=bpath)
                self.assert_invalid(result, "unsafe_path")
                self.assertEqual(result.diagnostic.actual["json_pointer"], "/plan_ref/path")

    def test_single_record_checks_owned_file_and_noncontract_locator_path_syntax(self):
        for field, unsafe in (("file", "C:/outside.json"), ("file", "../outside.json"),
                              ("ref", "/outside.json#/decision"),
                              ("ref", "inside/../../outside.json#L1")):
            with self.subTest(field=field, path=unsafe), patch(
                    "_b_route_record_owners.resolve_owned_ref",
                    side_effect=AssertionError("Single-record validation must not resolve owners")):
                value = deepcopy(MatrixFixture().policy)
                owned = {"owner": "authority", "ref": "evidence/authority.json#/decision",
                         "files": [{"path": "evidence/authority.json", "raw_digest": digest(b"declaration")} ]}
                if field == "file":
                    owned["files"][0]["path"] = unsafe
                else:
                    owned["ref"] = unsafe
                value["switch_boundary"]["authority_refs"] = [owned]
                self.assert_invalid(records.validate_record(value), "unsafe_path")

    def test_single_record_checks_receipt_target_authority_and_result_path_syntax(self):
        fixture = MatrixFixture()
        fixture.render()
        cpath = PREFIX + "commits/operation-1.json"
        for field, unsafe in (("targets", "C:/outside.json"), ("authority", "../outside.json"),
                              ("result", "/outside.json")):
            with self.subTest(field=field), patch.object(codec, "read_reference_bytes",
                    side_effect=AssertionError("Single-record validation must not read receipt targets")):
                value = deepcopy(fixture.last_documents[cpath])
                if field == "targets":
                    value["targets"][0]["path"] = unsafe
                elif field == "authority":
                    value["authority"] = [{"path": unsafe, "before_digest": None, "after_digest": None}]
                else:
                    value["result"]["target_paths"][0] = unsafe
                self.assert_invalid(records.validate_record(value, path=cpath), "unsafe_path")

    def test_single_record_keeps_internal_relative_aliases_and_contract_symbols_unresolved(self):
        fixture = MatrixFixture()
        bpath = fixture.add_binding()
        fixture.render()
        binding = deepcopy(fixture.last_documents[bpath])
        binding["plan_ref"]["path"] = PREFIX + "plans/p/../p/2.json"
        policy = deepcopy(fixture.policy)
        policy["switch_boundary"]["authority_refs"] = [
            {"owner": "authority", "ref": "evidence/nested/../proof.json#L1",
             "files": [{"path": "evidence/nested/../proof.json", "raw_digest": digest(b"declaration")}]},
            {"owner": "contract", "ref": "global::Newrouge.Contracts.Claim",
             "files": [{"path": "Game.Core/Contracts/nested/../Claim.cs", "raw_digest": digest(b"declaration")}]}]
        cpath = PREFIX + "commits/operation-1.json"
        receipt = deepcopy(fixture.last_documents[cpath])
        receipt["targets"][0]["path"] = "artifacts/nested/../result.json"
        receipt["authority"] = [{"path": "artifacts/nested/../input.json", "before_digest": None,
                                 "after_digest": None}]
        receipt["result"]["target_paths"][0] = "artifacts/nested/../result.json"
        for value, path in ((binding, bpath), (policy, POLICY), (receipt, cpath)):
            before = deepcopy(value)
            with self.subTest(path=path), patch.object(codec, "read_reference_bytes",
                    side_effect=AssertionError("Only schema resources may be read")), patch(
                    "_b_route_record_owners.resolve_owned_ref",
                    side_effect=AssertionError("Owner symbols must remain unresolved")):
                result = records.validate_record(value, path=path)
                self.assert_valid(result, "record_structure_only")
                self.assertFalse(result.references_validated)
                self.assertFalse(result.monotonicity_checked)
                self.assertEqual(value, before)

    def test_generic_strings_preserve_whitespace_and_dict_has_no_raw_identity(self):
        fixture = MatrixFixture()
        value = deepcopy(fixture.policy)
        value["policy_id"] = " policy identity "
        value["switch_boundary"]["allowed_a_operations"] = [" resume-task "]
        result = records.validate_record(value)
        self.assert_valid(result, "record_structure_only")
        self.assertIsNone(result.content_identity.raw_digest)
        self.assertEqual(result.content_identity.canonical_digest, canonical(value))
        self.assertEqual(value["policy_id"], " policy identity ")

    def test_codec_identity_results_are_not_upgraded_to_schema_acceptance(self):
        result = codec.verify_content({"schema_version": codec.PLAN_SCHEMA, "plan_id": "p", "revision": 2})
        self.assertTrue(result.ok)
        self.assertFalse(result.to_dict()["schema_validated"])
        self.assertEqual(result.to_dict()["claim"], "content_identity_only")
        unknown = codec.verify_content({"schema_version": "newrouge.b-route-verification-scope.v1",
                                        "scope_id": "scope", "revision": 1})
        self.assertFalse(unknown.ok)
        self.assertEqual(unknown.diagnostic.reason_code.value, "identity_unprovable")

    def test_unknown_schema_resource_is_rejected_offline(self):
        source = REPOSITORY / "docs/planning/b-route/schemas"
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            for schema in source.glob("*.schema.json"):
                value = json.loads(schema.read_bytes())
                if schema.name == "policy.schema.json":
                    value["$ref"] = "https://invalid.example/unavailable.schema.json"
                (target / schema.name).write_bytes(encoded(value))
            with patch.object(records, "SCHEMA_DIRECTORY", target), patch(
                    "urllib.request.urlopen", side_effect=AssertionError("Schema must stay offline")):
                self.assert_invalid(records.validate_record(MatrixFixture().policy), "schema_resource_error")

    def test_missing_schema_dependency_never_falls_back_to_required_only(self):
        source = REPOSITORY / "docs/planning/b-route/schemas"
        original_import = builtins.__import__
        def blocked(name, *args, **kwargs):
            if name.split(".", 1)[0] in {"jsonschema", "referencing"}:
                raise ImportError("Dependency is unavailable in this fixture")
            return original_import(name, *args, **kwargs)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            for schema in source.glob("*.schema.json"):
                (target / schema.name).write_bytes(schema.read_bytes())
            with patch.object(records, "SCHEMA_DIRECTORY", target), patch("builtins.__import__", side_effect=blocked):
                self.assert_invalid(records.validate_record(MatrixFixture().policy), "dependency_unavailable")


class CandidateBundleTests(RecordAssertions):
    def test_importing_one_definition_does_not_import_unrelated_sibling_dependencies(self):
        self.assert_valid(records.validate_bundle(scoped_dependency_bytes()))

    def test_owner_plan_global_dependencies_remain_in_the_recursive_closure(self):
        self.assert_invalid(records.validate_bundle(scoped_dependency_bytes(global_dependency=True)))
        self.assert_valid(records.validate_bundle(
            scoped_dependency_bytes(global_dependency=True, include_global=True)))

    def test_unrelated_scope_advance_keeps_historical_receipt_and_mutable_targets(self):
        output = mixed_scope_bytes()
        result = records.validate_bundle(output)
        self.assert_valid(result)
        omitted = result.to_dict()["historical_targets_not_revalidated"]
        self.assertIn({"operation_id": "operation-1", "path": POLICY}, omitted)
        self.assertIn({"operation_id": "operation-1", "path": ORIGINS}, omitted)
        self.assertNotIn({"operation_id": "operation-2", "path": POLICY}, omitted)

    def test_current_shared_dependency_cannot_hide_behind_historical_receipt(self):
        self.assert_invalid(records.validate_bundle(mixed_scope_bytes(shared_dependency=True)),
                            "revision_mismatch", "mapping_mismatch", "invalid_reference")

    def test_current_mutable_target_bytes_still_must_match_receipt(self):
        output = mixed_scope_bytes()
        output[POLICY] += b" "
        self.assert_invalid(records.validate_bundle(output), "digest_mismatch")

    def test_current_mutable_target_cannot_claim_another_after_image(self):
        fixture = MatrixFixture()
        cpath = PREFIX + "commits/operation-1.json"
        def wrong_after(value):
            target = next(row for row in value["targets"] if row["path"] == POLICY)
            target["after_digest"] = digest(b"a different current policy")
            target["projection_digest"] = target["after_digest"]
        fixture.hooks[cpath] = wrong_after
        self.assert_invalid(records.validate_bundle(fixture.render()), "digest_mismatch")

    def test_zero_task_bootstrap_requires_no_binding_join_or_readiness(self):
        fixture = MatrixFixture()
        output = fixture.render()
        result = records.validate_bundle(output)
        self.assert_valid(result)
        self.assertTrue(result.references_validated)
        self.assertFalse(result.monotonicity_checked)
        self.assertFalse(any("bindings/" in path or "readiness" in path for path in output))
        self.assertEqual(fixture.last_documents[ORIGINS]["tasks"], [])
        self.assertEqual(fixture.last_documents[CATALOG]["task_index"], [])

    def test_candidates_require_original_bytes_even_when_raw_hash_could_be_recreated(self):
        fixture = MatrixFixture()
        output = fixture.render()
        output[plan_path()] = deepcopy(fixture.last_documents[plan_path()])
        self.assert_invalid(records.validate_bundle(output), "invalid_type", "identity_unprovable")

    def test_candidate_bytes_shadow_disk_and_wrong_hash_never_falls_back(self):
        fixture = MatrixFixture()
        output = fixture.render()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / plan_path()
            path.parent.mkdir(parents=True)
            path.write_bytes(b'{"invalid":"disk"}')
            self.assert_valid(records.validate_bundle(output, root=root))
            path.write_bytes(output[plan_path()])
            changed = dict(output)
            changed[plan_path()] = output[plan_path()] + b" "
            self.assert_invalid(records.validate_bundle(changed, root=root), "digest_mismatch")

    def test_root_internal_reference_alias_is_preserved_without_rewriting_hash_input(self):
        fixture = MatrixFixture()
        alias = PREFIX + "plans/p/../p/2.json"
        fixture.ref_changes[plan_path()] = {"path": alias}
        output = fixture.render()
        before = dict(output)
        self.assert_valid(records.validate_bundle(output))
        self.assertEqual(output, before)
        self.assertEqual(json.loads(output[CATALOG])["scope_heads"][0]["plan_refs"][0]["path"], alias)

    def test_candidate_bytes_override_disk_when_reference_uses_directory_alias(self):
        fixture = MatrixFixture()
        fixture.ref_changes[plan_path()] = {"path": PREFIX + "plans/alias/2.json"}
        output = fixture.render()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / (PREFIX + "plans/p")
            target.mkdir(parents=True)
            (target / "2.json").write_bytes(b'{"stale":"disk value must not win"}')
            directory_link(root / (PREFIX + "plans/alias"), target)
            self.assert_valid(records.validate_bundle(output, root=root))

    def test_bundle_api_reads_disk_without_changing_bytes_mtimes_or_candidate_map(self):
        fixture = MatrixFixture()
        output = fixture.render()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for path, data in output.items():
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            before = {path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
                      for path in root.rglob("*") if path.is_file()}
            candidate = dict(output)
            self.assert_valid(records.validate_bundle({}, root=root))
            self.assert_valid(records.validate_bundle(candidate, root=root))
            after = {path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
                     for path in root.rglob("*") if path.is_file()}
            self.assertEqual(after, before)
            self.assertEqual(candidate, output)

    def test_bundle_reader_accepts_internal_directory_link(self):
        fixture = MatrixFixture()
        output = fixture.render()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage = root / "storage"
            storage.mkdir()
            link = root / PREFIX.rstrip("/")
            link.parent.mkdir(parents=True)
            directory_link(link, storage)
            for path, data in output.items():
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            self.assert_valid(records.validate_bundle({}, root=root))

    def test_bundle_reader_rejects_external_directory_link_even_with_matching_bytes(self):
        fixture = MatrixFixture()
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root, storage = base / "repository", base / "outside"
            root.mkdir()
            storage.mkdir()
            link = root / PREFIX.rstrip("/")
            link.parent.mkdir(parents=True)
            directory_link(link, storage)
            for path, data in fixture.render().items():
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            self.assert_invalid(records.validate_bundle({}, root=root), "unsafe_path", "path_unprovable")

    def test_required_record_and_owned_file_missing_are_not_planned(self):
        for missing in (POLICY, ORIGINS, plan_path(), "sources/ledger.json", "evidence/admission.json"):
            fixture = MatrixFixture()
            output = fixture.render()
            del output[missing]
            with self.subTest(missing=missing):
                self.assert_invalid(records.validate_bundle(output),
                                    "unresolved_reference", "file_not_found", "required_governance_missing")

    def test_reference_schema_entity_revision_digest_and_explicit_mode_are_checked(self):
        cases = [
            ({"entity_id": "someone-else"}, ("unknown_entity",)),
            ({"revision": 3}, ("revision_mismatch",)),
            ({"digest": digest(b"different")}, ("digest_mismatch",)),
            ({"schema_version": "newrouge.b-route-binding.v1"},
             ("schema_mismatch", "invalid_reference", "invalid_enum")),
            ({"verification_mode": "immutable_bytes"},
             ("invalid_enum", "unknown_verification_mode", "schema_validation_failed")),
        ]
        for change, codes in cases:
            with self.subTest(change=change):
                fixture = MatrixFixture()
                fixture.ref_changes[plan_path()] = change
                self.assert_invalid(records.validate_bundle(fixture.render()), *codes)
        fixture = MatrixFixture()
        fixture.ref_changes[plan_path()] = {"verification_mode": "canonical", "codec_version": codec.CODEC_VERSION}
        self.assert_valid(records.validate_bundle(fixture.render()))

    def test_source_native_digest_and_string_revision_are_separate_from_raw_bytes(self):
        fixture = MatrixFixture()
        output = fixture.render()
        self.assertNotEqual(fixture.native_digest, digest(output["sources/manifest.json"]))
        self.assert_valid(records.validate_bundle(output))
        for field, wrong in (("source_manifest_digest", digest(output["sources/manifest.json"])),
                             ("source_revision", "another-source-set")):
            with self.subTest(field=field):
                fixture = MatrixFixture()
                fixture.models[plan_path()]["source_identity"][field] = wrong
                self.assert_invalid(records.validate_bundle(fixture.render()))

    def test_requirement_source_blocks_must_exist_in_native_ledger(self):
        fixture = MatrixFixture()
        fixture.models[plan_path()]["requirements"][0]["source_block_ids"] = ["missing-block"]
        self.assert_invalid(records.validate_bundle(fixture.render()))

    def test_verification_projection_includes_all_seven_fields(self):
        for field, wrong in (("sink_id", "sink-2"), ("authority_ref", "evidence/check-b.json"),
                             ("verification_ref", "evidence/check-b.json"), ("rationale", "different")):
            with self.subTest(field=field):
                fixture = MatrixFixture()
                fixture.artifacts["evidence/check-a.json"] = b'{"basis":"first"}\n'
                fixture.artifacts["evidence/check-b.json"] = b'{"basis":"second"}\n'
                model = fixture.models[plan_path()]
                if field == "authority_ref":
                    fixture.set_disposition(plan_path(), "deferred", authority_ref="evidence/check-a.json")
                    model["evidence_source_refs"] = [
                        fixture.owned("authority", "evidence/check-a.json")]
                else:
                    fixture.set_disposition(plan_path(), "other_verification", sink_id="sink-1",
                                            verification_ref="evidence/check-a.json")
                    model["requirements"][0]["non_task_sinks"].append("sink-2")
                    own = fixture.owned("other_verification", "evidence/check-a.json")
                    model["evidence_source_refs"] = [own]
                    model["applicability"][0]["other_verification_refs"] = [own]
                model["coverage_table"][0][field] = wrong
                self.assert_invalid(records.validate_bundle(fixture.render()), "mapping_mismatch")

    def test_legal_nonflow_preserves_sink_and_other_verification_without_runtime_claim(self):
        fixture = MatrixFixture()
        fixture.artifacts["evidence/check.json"] = encoded({"status": "not-run", "record": "future check"})
        path = plan_path()
        fixture.set_disposition(path, "other_verification", sink_id="sink-1",
                                verification_ref="evidence/check.json")
        own = fixture.owned("other_verification", "evidence/check.json")
        fixture.models[path]["evidence_source_refs"] = [own]
        fixture.models[path]["applicability"][0]["other_verification_refs"] = [own]
        self.assert_valid(records.validate_bundle(fixture.render()))
        fixture.models[path]["requirement_verification"][0]["sink_id"] = "not-a-sink"
        fixture.models[path]["coverage_table"][0]["sink_id"] = "not-a-sink"
        self.assert_invalid(records.validate_bundle(fixture.render()))

    def test_nonflow_label_or_empty_evidence_does_not_grant_exemption(self):
        fixture = MatrixFixture()
        fixture.set_disposition(plan_path(), "other_verification", sink_id="sink-1",
                                verification_ref="evidence/missing.json")
        self.assert_invalid(records.validate_bundle(fixture.render()))
        fixture = MatrixFixture()
        fixture.models[plan_path()]["applicability"][0]["rationale"] = "An inconsistent independent claim"
        self.assert_invalid(records.validate_bundle(fixture.render()), "mapping_mismatch")

    def test_flow_loop_and_cross_plan_recursive_owner_closure_are_legal(self):
        fixture = MatrixFixture()
        fixture.add_flow(plan_path())
        fixture.use_cycle()
        self.assert_valid(records.validate_bundle(fixture.render()))

    def test_current_owner_domain_is_exact_and_history_does_not_add_an_owner(self):
        fixture = MatrixFixture()
        old = fixture.add_plan("p", 1)
        fixture.models[old]["definitions"]["states"] = [
            {"id": "shared", "requirement_ids": ["REQ-p"], "responsibility": "Old owner", "uses": []}]
        new = fixture.add_plan("p", 2)
        fixture.models[new]["definitions"]["states"] = [
            {"id": "shared", "requirement_ids": ["REQ-p"], "responsibility": "Current owner", "uses": []}]
        self.assert_valid(records.validate_bundle(fixture.render()))
        for mutate in (lambda value: value["definition_owners"].clear(),
                       lambda value: value["definition_owners"].append(deepcopy(value["definition_owners"][0])),
                       lambda value: value["definition_owners"][0].update(definition_id="missing")):
            with self.subTest(mutate=mutate):
                fixture.hooks[CATALOG] = mutate
                self.assert_invalid(records.validate_bundle(fixture.render()))

    def test_recursive_closure_missing_extra_and_owner_revision_drift_are_rejected(self):
        for variant in ("missing", "extra", "wrong_revision"):
            with self.subTest(variant=variant):
                fixture = MatrixFixture()
                p, q = fixture.use_cycle()
                if variant == "missing":
                    fixture.resolved = fixture.resolved[:1]
                elif variant == "extra":
                    fixture.models[q]["definitions"]["commands"].append({
                        "id": "unused", "requirement_ids": ["REQ-q"],
                        "responsibility": "An unrelated definition", "uses": []})
                    fixture.resolved.append(("command", "unused", q))
                else:
                    fixture.models[p]["logical_references"][0]["owner_revision"] = 2
                self.assert_invalid(records.validate_bundle(fixture.render()))

    def test_planned_object_can_be_absent_but_responsibility_and_checks_are_required(self):
        fixture = MatrixFixture()
        bpath = fixture.add_binding()
        binding = fixture.bindings[bpath][0]
        binding["stage"] = "4"
        binding["implementation_objects"] = [{
            "id": "adapter", "kind": "adapter", "availability": "planned",
            "responsible_task_ids": [11], "expected_type": "RewardAdapter",
            "lifecycle": "Owned by the scene", "target_ref": None, "later_checks": ["type", "compile"],
        }]
        self.assert_valid(records.validate_bundle(fixture.render(), task_join=fixture.join()))
        for field in ("responsible_task_ids", "later_checks"):
            with self.subTest(field=field):
                candidate = deepcopy(binding["implementation_objects"][0])
                binding["implementation_objects"][0][field] = []
                self.assert_invalid(records.validate_bundle(fixture.render(), task_join=fixture.join()))
                binding["implementation_objects"][0] = candidate

    def test_existing_object_requires_a_real_locator_and_bytes(self):
        fixture = MatrixFixture()
        bpath = fixture.add_binding()
        fixture.artifacts["Game.Core/Adapter.cs"] = b"public sealed class Adapter {}\n"
        obj = {"id": "adapter", "kind": "adapter", "availability": "existing",
               "responsible_task_ids": [11], "expected_type": "Adapter",
               "lifecycle": "Owned by the scene", "target_ref": fixture.owned(
                   "implementation_reference", "Game.Core/Adapter.cs"), "later_checks": ["compile"]}
        fixture.bindings[bpath][0]["implementation_objects"] = [obj]
        self.assert_valid(records.validate_bundle(fixture.render(), task_join=fixture.join()))
        obj["target_ref"] = None
        self.assert_invalid(records.validate_bundle(fixture.render(), task_join=fixture.join()))

    def test_origin_and_catalog_cannot_store_task_status_or_runtime_pass(self):
        for path, field in ((ORIGINS, "status"), (ORIGINS, "runtime_verified"),
                            (CATALOG, "passed"), (CATALOG, "task_status")):
            with self.subTest(path=path, field=field):
                fixture = MatrixFixture()
                fixture.hooks[path] = lambda value, name=field: value.update({name: True})
                self.assert_invalid(records.validate_bundle(fixture.render()), "unknown_field")

    def test_receipt_excludes_itself_and_catalog_in_targets_and_results(self):
        cpath = PREFIX + "commits/operation-1.json"
        for forbidden in (cpath, CATALOG):
            for place in ("targets", "result"):
                with self.subTest(forbidden=forbidden, place=place):
                    fixture = MatrixFixture()
                    def inject(value, path=forbidden, area=place):
                        if area == "targets":
                            value["targets"].append({
                                "path": path, "before_digest": None, "after_digest": digest(b"output"),
                                "verification_mode": "immutable_bytes", "codec_version": None,
                                "projection_digest": digest(b"output")})
                            value["result"]["target_paths"].append(path)
                        else:
                            value["result"]["target_paths"].append(path)
                    fixture.hooks[cpath] = inject
                    self.assert_invalid(records.validate_bundle(fixture.render()), "digest_cycle")

    def test_receipt_old_catalog_before_is_allowed_but_current_after_is_not(self):
        cpath = PREFIX + "commits/operation-1.json"
        fixture = MatrixFixture()
        fixture.hooks[cpath] = lambda value: value["authority"].append({
            "path": CATALOG, "before_digest": digest(b"old catalog"), "after_digest": None})
        self.assert_valid(records.validate_bundle(fixture.render()))
        fixture.hooks[cpath] = lambda value: value["authority"].append({
            "path": CATALOG, "before_digest": None, "after_digest": digest(b"new catalog")})
        self.assert_invalid(records.validate_bundle(fixture.render()), "digest_cycle")

    def test_target_modes_are_distinct_and_projection_is_never_claimed(self):
        fixture = MatrixFixture()
        cpath = PREFIX + "commits/operation-1.json"
        def projection(value):
            target = value["targets"][0]
            target.update(verification_mode="task_definition_projection",
                          codec_version="newrouge.b-route-task-definition.v1",
                          projection_digest=digest(b"not computed by this story"))
        fixture.hooks[cpath] = projection
        result = records.validate_bundle(fixture.render())
        self.assert_valid(result)
        self.assertFalse(result.target_projection_verified)
        fixture.hooks[cpath] = lambda value: value["targets"][0].update(verification_mode="canonical")
        self.assert_invalid(records.validate_bundle(fixture.render()), "invalid_enum", "schema_validation_failed")

    def test_target_bytes_result_paths_and_scope_relationships_are_checked(self):
        cpath = PREFIX + "commits/operation-1.json"
        for mutate in (lambda value: value["targets"][0].update(after_digest=digest(b"wrong")),
                       lambda value: value["result"]["target_paths"].pop(),
                       lambda value: value["result"].update(scope_ids=["other-scope"])):
            with self.subTest(mutate=mutate):
                fixture = MatrixFixture()
                fixture.hooks[cpath] = mutate
                self.assert_invalid(records.validate_bundle(fixture.render()))

    def test_adoption_proof_cannot_point_to_current_commit(self):
        fixture = MatrixFixture()
        fixture.models[plan_path()]["adoption_proof_refs"] = [{
            "owner": "planning_proof", "ref": PREFIX + "commits/operation-1.json",
            "files": [{"path": PREFIX + "commits/operation-1.json", "raw_digest": digest(b"cycle")}],
        }]
        self.assert_invalid(records.validate_bundle(fixture.render()), "digest_cycle")

    def test_baseline_reports_its_limit_and_preserves_immutable_bytes(self):
        fixture = MatrixFixture()
        output = fixture.render()
        self.assert_valid(records.validate_bundle(output))
        checked = records.validate_bundle(output, baseline=dict(output))
        self.assert_valid(checked)
        self.assertTrue(checked.monotonicity_checked)
        baseline = dict(output)
        baseline[plan_path()] = output[plan_path()] + b" "
        self.assert_invalid(records.validate_bundle(output, baseline=baseline), "conflict")
        older = MatrixFixture()
        older.models.clear()
        older.current_plans.clear()
        older.add_plan("p", 1)
        self.assert_invalid(records.validate_bundle(older.render(), baseline=output),
                            "revision_mismatch", "conflict")

    def test_baseline_checks_current_revision_without_treating_old_history_as_new(self):
        first = MatrixFixture()
        first.add_binding()
        baseline = first.render()
        next_fixture = deepcopy(first)
        next_fixture.operation_id = "operation-2"
        next_fixture.hooks[ORIGINS] = lambda value: value.update(revision=2)
        next_fixture.hooks[CATALOG] = lambda value: value.update(revision=2)
        old = next_fixture.add_plan("p", 1)
        new = next_fixture.add_plan("p", 3)
        next_fixture.models[new]["lineage"]["previous_plan_ref"] = first.reference(plan_path(), baseline)
        next_fixture.add_binding("p", 8, target_plan=new)
        self.assertIn(old, next_fixture.models)
        result = records.validate_bundle(next_fixture.render(), baseline=baseline,
                                         task_join=next_fixture.join())
        self.assert_valid(result)
        self.assertTrue(result.monotonicity_checked)


class TaskJoinTests(RecordAssertions):
    def fixture(self):
        fixture = MatrixFixture()
        fixture.add_binding()
        fixture.add_plan("q", 1)
        fixture.add_binding("q", 3)
        return fixture

    def test_task_mapping_requires_at_least_one_real_business_view(self):
        fixture = MatrixFixture()
        bpath = fixture.add_binding()
        mapping = fixture.bindings[bpath][0]["task_mappings"][0]
        mapping["view_refs"] = []
        master = {"master": {"tasks": [{"id": 11, "status": "pending"}]}}
        empty_views = records.TaskJoinContext(master, [], [])
        self.assert_invalid(records.validate_bundle(fixture.render(), task_join=empty_views),
                            "schema_validation_failed")
        mapping["view_refs"] = [{"view": "back", "business_id": "BACK-11"}]
        one_view = records.TaskJoinContext(master, [{"id": "BACK-11", "taskmaster_id": 11}], [])
        self.assert_valid(records.validate_bundle(fixture.render(), task_join=one_view))

    def test_task_part_references_require_declared_applicable_responsibilities(self):
        for variant in ("undeclared", "not_applicable"):
            with self.subTest(variant=variant):
                fixture = MatrixFixture()
                bpath = fixture.add_binding()
                binding = fixture.bindings[bpath][0]
                if variant == "undeclared":
                    binding["parts"] = []
                else:
                    binding["parts"] = [{"kind": "domain_rules", "applicability": "not_applicable",
                                         "rationale": "This binding has no domain responsibility",
                                         "responsibilities": []}]
                output = fixture.render()
                self.assert_invalid(records.validate_record(output[bpath], path=bpath), "mapping_mismatch")
                self.assert_invalid(records.validate_bundle(output, task_join=fixture.join()), "mapping_mismatch")

    def test_binding_part_kinds_are_unique_even_when_applicability_conflicts(self):
        for variant in ("identical", "contradictory"):
            with self.subTest(variant=variant):
                fixture = MatrixFixture()
                bpath = fixture.add_binding()
                binding = fixture.bindings[bpath][0]
                duplicate = deepcopy(binding["parts"][0])
                if variant == "contradictory":
                    duplicate.update(applicability="not_applicable", responsibilities=[],
                                     rationale="This binding has no domain responsibility")
                binding["parts"].append(duplicate)
                output = fixture.render()
                self.assert_invalid(records.validate_record(output[bpath], path=bpath), "mapping_mismatch")
                self.assert_invalid(records.validate_bundle(output, task_join=fixture.join()), "mapping_mismatch")

    def test_integration_only_owner_can_have_no_business_parts_or_objects(self):
        fixture = MatrixFixture()
        bpath = fixture.add_binding()
        binding = fixture.bindings[bpath][0]
        binding["parts"] = []
        binding["task_mappings"][0]["part_kinds"] = []
        self.assertEqual(binding["task_mappings"][0]["roles"], ["integration_only_owner"])
        self.assertEqual(binding["implementation_objects"], [])
        self.assert_valid(records.validate_bundle(fixture.render(), task_join=fixture.join()))

    def test_current_multi_plan_join_accepts_pending_task_and_excludes_history(self):
        fixture = self.fixture()
        old = fixture.add_plan("p", 1)
        fixture.add_binding("p", 6, target_plan=old)
        fixture.current_plans.remove(old)
        fixture.current_plans.append(plan_path())
        fixture.current_bindings.remove(binding_path("p", 6))
        fixture.current_bindings.append(binding_path())
        self.assert_valid(records.validate_bundle(fixture.render(), task_join=fixture.join()))

    def test_shared_task_supports_multiple_flows_with_one_shared_definition_owner(self):
        fixture = MatrixFixture()
        p, q = plan_path(), fixture.add_plan("q", 1)
        primary = fixture.add_flow(p, "flow-primary")
        secondary = fixture.add_flow(p, "flow-secondary")
        other = fixture.add_flow(q, "flow-other")
        fixture.models[p]["definitions"]["states"] = [{
            "id": "shared-state", "requirement_ids": ["REQ-p"],
            "responsibility": "One state owner serves both plans", "uses": []}]
        for path in (p, q):
            for definition in fixture.models[path]["definitions"]["flows"]:
                definition["state_owners"] = [logical("state", "shared-state", "p", 2)]
        fixture.resolved = [("state", "shared-state", p)]
        bp = fixture.add_binding()
        bq = fixture.add_binding("q", 1)
        fixture.bindings[bp][0]["task_mappings"][0]["flow_ids"] = [primary, secondary]
        fixture.bindings[bq][0]["task_mappings"][0]["flow_ids"] = [other]
        output = fixture.render()
        self.assert_valid(records.validate_bundle(output, task_join=fixture.join()))
        owners = json.loads(output[CATALOG])["definition_owners"]
        self.assertEqual(sum(row["definition_id"] == "shared-state" for row in owners), 1)
        self.assertEqual(len(json.loads(output[ORIGINS])["tasks"]), 1)

    def test_nonempty_mapping_requires_real_triplet_context(self):
        fixture = self.fixture()
        self.assert_invalid(records.validate_bundle(fixture.render()), "unresolved_reference", "mapping_mismatch")

    def test_matching_origins_and_index_cannot_add_noncurrent_historical_obligations(self):
        fixture = self.fixture()
        old = fixture.add_plan("p", 1)
        old_binding = fixture.add_binding("p", 6, target_plan=old)
        fixture.current_plans.remove(old)
        fixture.current_plans.append(plan_path())
        fixture.current_bindings.remove(old_binding)
        fixture.current_bindings.append(binding_path())
        output = fixture.render()
        old_plan_ref = fixture.reference(old, output)
        old_binding_ref = fixture.reference(old_binding, output)
        def add_history(value, container):
            value[container][0]["plan_refs"].append(deepcopy(old_plan_ref))
            value[container][0]["binding_refs"].append(deepcopy(old_binding_ref))
        fixture.hooks[ORIGINS] = lambda value: add_history(value, "tasks")
        fixture.hooks[CATALOG] = lambda value: add_history(value, "task_index")
        self.assert_invalid(records.validate_bundle(fixture.render(), task_join=fixture.join()),
                            "mapping_mismatch")

    def test_reverse_join_is_full_equality_not_origins_index_agreement(self):
        for field, mutation in (("plan_refs", "remove"), ("binding_refs", "remove"),
                                ("plan_refs", "duplicate"), ("binding_refs", "duplicate"),
                                ("task_id", "extra_task")):
            with self.subTest(field=field, mutation=mutation):
                fixture = self.fixture()
                def corrupt(value, container, name=field, change=mutation):
                    row = value[container][0]
                    if change == "remove":
                        row[name].pop()
                    elif change == "duplicate":
                        row[name].append(deepcopy(row[name][0]))
                    else:
                        copy = deepcopy(row)
                        copy["task_id"] = 99
                        value[container].append(copy)
                fixture.hooks[ORIGINS] = lambda value: corrupt(value, "tasks")
                fixture.hooks[CATALOG] = lambda value: corrupt(value, "task_index")
                self.assert_invalid(records.validate_bundle(fixture.render(), task_join=fixture.join()),
                                    "mapping_mismatch", "invalid_reference", "schema_validation_failed")

    def test_wrong_view_business_id_master_type_or_orphan_never_coerces(self):
        fixture = self.fixture()
        output = fixture.render()
        for invalid in ("11", True, 11.0):
            with self.subTest(master_id=invalid):
                join = records.TaskJoinContext(
                    {"master": {"tasks": [{"id": invalid, "status": "pending"}]}},
                    [{"id": "BACK-11", "taskmaster_id": 11}],
                    [{"id": "GAME-11", "taskmaster_id": 11}])
                self.assert_invalid(records.validate_bundle(output, task_join=join))
        for business, linked in ((11, 11), ("BACK-OTHER", 11), ("BACK-11", 99), (" BACK-11 ", 11)):
            with self.subTest(business=business, linked=linked):
                join = records.TaskJoinContext(
                    {"master": {"tasks": [{"id": 11, "status": "pending"}]}},
                    [{"id": business, "taskmaster_id": linked}],
                    [{"id": "GAME-11", "taskmaster_id": 11}])
                self.assert_invalid(records.validate_bundle(output, task_join=join))

    def test_invalid_join_id_types_report_original_context_and_exact_pointer(self):
        fixture = self.fixture()
        output = fixture.render()
        cases = (
            ("master", "id", True, "/task_join/master/master/tasks/0/id", "positive integer", "bool"),
            ("back", "taskmaster_id", "11", "/task_join/back/0/taskmaster_id", "positive integer", "str"),
            ("gameplay", "id", 11, "/task_join/gameplay/0/id", "nonempty string", "int"),
        )
        for context, field, invalid, pointer, expected_type, actual_type in cases:
            with self.subTest(context=context, field=field):
                original = fixture.join()
                values = {name: deepcopy(getattr(original, name)) for name in ("master", "back", "gameplay")}
                rows = values[context]["master"]["tasks"] if context == "master" else values[context]
                rows[0][field] = invalid
                result = records.validate_bundle(output, task_join=records.TaskJoinContext(**values))
                self.assert_invalid(result, "invalid_type")
                diagnostic = result.diagnostic.to_dict()
                self.assertEqual(diagnostic["stage"], "content")
                for side, detail in (("expected", expected_type), ("actual", actual_type)):
                    self.assertEqual(diagnostic[side], {"context": "task_join." + context,
                                                       "json_pointer": pointer, "value": detail})
                    self.assertNotIn("path", diagnostic[side])
                self.assertIsNone(diagnostic["entity_id"])
                self.assertIsNone(diagnostic["resume_ref"])

    def test_join_decode_failures_identify_the_logical_context_without_file_paths(self):
        fixture = self.fixture()
        output = fixture.render()
        for context, invalid, code in (("master", b"{", "invalid_json"),
                                       ("back", b"\xff", "invalid_utf8"),
                                       ("gameplay", b'[{"id":"first","id":"duplicate"}]', "duplicate_key")):
            with self.subTest(context=context):
                original = fixture.join()
                values = {name: getattr(original, name) for name in ("master", "back", "gameplay")}
                values[context] = invalid
                result = records.validate_bundle(output, task_join=records.TaskJoinContext(**values))
                self.assert_invalid(result, code)
                diagnostic = result.diagnostic.to_dict()
                self.assertEqual(diagnostic["stage"], "decode")
                for side in ("expected", "actual"):
                    self.assertEqual(diagnostic[side]["context"], "task_join." + context)
                    self.assertEqual(diagnostic[side]["json_pointer"], "/task_join/" + context)
                    self.assertEqual(set(diagnostic[side]), {"context", "json_pointer", "value"})
                self.assertIsNone(diagnostic["resume_ref"])


class OwnedReferenceTests(RecordAssertions):
    def test_owned_locator_alias_binds_canonical_candidate_bytes_without_disk_shadow(self):
        fixture = MatrixFixture()
        fixture.models[plan_path()]["adoption_proof_refs"] = [
            fixture.owned("planning_proof", "proof-alias/admission.json", ["evidence/admission.json"])]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "evidence"
            evidence.mkdir()
            stale = b"Stale disk evidence must not replace the candidate bytes.\n"
            (evidence / "admission.json").write_bytes(stale)
            directory_link(root / "proof-alias", evidence)
            self.assert_valid(records.validate_bundle(fixture.render(), root=root))
            fixture.models[plan_path()]["adoption_proof_refs"][0]["files"][0]["raw_digest"] = digest(stale)
            self.assert_invalid(records.validate_bundle(fixture.render(), root=root), "digest_mismatch")

    def test_non_b_admission_schema_inside_b_directory_keeps_its_own_format(self):
        fixture = MatrixFixture()
        path = PREFIX + "proofs/admission.json"
        fixture.artifacts[path] = encoded({"schema_version": "existing.admission-proof.v1",
                                          "selected": "candidate-1"})
        fixture.models[plan_path()]["adoption_proof_refs"] = [fixture.owned("planning_proof", path)]
        self.assert_valid(records.validate_bundle(fixture.render()))

    def evidence_fixture(self):
        fixture = MatrixFixture()
        fence = chr(96) * 3
        payload = {"records": [{"evidence_id": "shared", "status": "not-run",
                                "covered_behavior": "A declaration, not runtime evidence"}]}
        fixture.artifacts["evidence/shared.md"] = (
            "# Shared evidence\n" + fence + "json\n" + json.dumps(payload) + "\n" + fence + "\n"
        ).encode("utf-8")
        model = fixture.models[plan_path()]
        model["requirement_evidence"] = [{
            "requirement_id": "REQ-p", "evidence_id": "evidence-1", "kind": "verification_record",
            "source_ref": "evidence/shared.md#shared", "covered_behavior": "Declared result",
            "flow_ids": [], "test_ids": [],
        }]
        model["requirement_verification"][0]["evidence_ids"] = ["evidence-1"]
        model["evidence_source_refs"] = [fixture.owned("verification_record", "evidence/shared.md#shared")]
        return fixture

    def test_native_fenced_evidence_id_is_not_a_heading_or_runtime_pass(self):
        fixture = self.evidence_fixture()
        self.assert_valid(records.validate_bundle(fixture.render()))
        fixture.artifacts["evidence/shared.md"] = b"# shared\nThere is no native evidence record.\n"
        fixture.models[plan_path()]["evidence_source_refs"] = [
            fixture.owned("verification_record", "evidence/shared.md#shared")]
        self.assert_invalid(records.validate_bundle(fixture.render()), "unresolved_reference", "invalid_reference")

    def test_evidence_source_binding_is_unique_complete_and_not_an_escape_hatch(self):
        for variant in ("missing", "duplicate", "unreferenced", "raw_mismatch"):
            with self.subTest(variant=variant):
                fixture = self.evidence_fixture()
                refs = fixture.models[plan_path()]["evidence_source_refs"]
                if variant == "missing":
                    refs.clear()
                elif variant == "duplicate":
                    refs.append(deepcopy(refs[0]))
                elif variant == "unreferenced":
                    refs.append(fixture.owned("other_verification", "evidence/admission.json"))
                else:
                    refs[0]["files"][0]["raw_digest"] = digest(b"disk content")
                self.assert_invalid(records.validate_bundle(fixture.render()))

    def test_owned_file_sets_and_owner_whitelist_are_exact(self):
        for variant in ("extra", "duplicate", "unknown_owner"):
            with self.subTest(variant=variant):
                fixture = MatrixFixture()
                own = fixture.models[plan_path()]["adoption_proof_refs"][0]
                if variant == "extra":
                    own["files"].append({"path": "sources/input.md",
                                         "raw_digest": digest(fixture.artifacts["sources/input.md"])})
                elif variant == "duplicate":
                    own["files"].append(deepcopy(own["files"][0]))
                else:
                    own["owner"] = "private_runtime_bypass"
                self.assert_invalid(records.validate_bundle(fixture.render()))

    def test_json_pointer_native_fragments_and_line_spans_have_distinct_rules(self):
        fixture = MatrixFixture()
        fixture.artifacts["evidence/tree.json"] = encoded({"a/b": {"~key": ["first", "second"]}})
        fixture.artifacts["evidence/lines.md"] = b"# Heading\nSecond line\nThird line\n"
        for locator in ("evidence/tree.json#/a~1b/~0key/1", "evidence/lines.md#L2-L3"):
            with self.subTest(locator=locator):
                fixture.models[plan_path()]["adoption_proof_refs"] = [fixture.owned("planning_proof", locator)]
                self.assert_valid(records.validate_bundle(fixture.render()))
        for locator in ("evidence/tree.json#/a~2b", "evidence/tree.json#/absent",
                        "evidence/lines.md#L2-L99", "evidence/lines.md#L0"):
            with self.subTest(locator=locator):
                fixture.models[plan_path()]["adoption_proof_refs"] = [fixture.owned("planning_proof", locator)]
                self.assert_invalid(records.validate_bundle(fixture.render()))
        fixture.models[plan_path()]["adoption_proof_refs"] = [
            fixture.owned("planning_proof", "evidence/lines.md#heading")]
        self.assert_invalid(records.validate_bundle(fixture.render()), "unsupported_locator")

    def test_external_evidence_candidate_does_not_fall_back_to_disk_fragment(self):
        fixture = self.evidence_fixture()
        output = fixture.render()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            disk = root / "evidence/shared.md"
            disk.parent.mkdir(parents=True)
            disk.write_bytes(output["evidence/shared.md"])
            fixture.artifacts["evidence/shared.md"] = b"# shared\nNo matching native record remains.\n"
            fixture.models[plan_path()]["evidence_source_refs"] = [
                fixture.owned("verification_record", "evidence/shared.md#shared")]
            self.assert_invalid(records.validate_bundle(fixture.render(), root=root),
                                "unresolved_reference", "invalid_reference")

    def contract_fixture(self):
        fixture = MatrixFixture()
        paths = ["Game.Core/Contracts/Claim.cs", "Game.Core/Contracts/Payload.cs"]
        fixture.artifacts[paths[0]] = b"public sealed record Claim(Payload Value);\r\n"
        fixture.artifacts[paths[1]] = b"public sealed record Payload(int Amount);\r\n"
        model = fixture.models[plan_path()]
        model["requirement_evidence"] = [{
            "requirement_id": "REQ-p", "evidence_id": "contract-1", "kind": "implementation_reference",
            "source_ref": "Claim", "covered_behavior": "Production contract", "flow_ids": [], "test_ids": [],
        }]
        model["requirement_verification"][0]["evidence_ids"] = ["contract-1"]
        model["evidence_source_refs"] = [fixture.owned("contract", "Claim", paths)]
        return fixture, paths

    def test_contract_symbol_closure_uses_candidate_overrides_and_new_files(self):
        fixture, paths = self.contract_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            disk = root / paths[0]
            disk.parent.mkdir(parents=True)
            disk.write_bytes(b"public sealed record Claim(OldPayload Value);\n")
            (root / "Game.Core/Contracts/OldPayload.cs").write_bytes(
                b"public sealed record OldPayload(int Amount);\n")
            self.assert_valid(records.validate_bundle(fixture.render(), root=root))
            fixture.models[plan_path()]["evidence_source_refs"][0]["files"][0]["raw_digest"] = digest(disk.read_bytes())
            self.assert_invalid(records.validate_bundle(fixture.render(), root=root), "digest_mismatch")

    def test_contract_directory_alias_keeps_candidate_only_dto_in_the_closure(self):
        fixture, paths = self.contract_fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            storage = root / "contract-storage"
            storage.mkdir()
            link = root / "Game.Core/Contracts"
            link.parent.mkdir(parents=True)
            directory_link(link, storage)
            (storage / "Claim.cs").write_bytes(fixture.artifacts[paths[0]])
            self.assertFalse((storage / "Payload.cs").exists())
            self.assert_valid(records.validate_bundle(fixture.render(), root=root))
            self.assertFalse((storage / "Payload.cs").exists())

    def test_contract_closure_rejects_root_external_directory_link(self):
        fixture, paths = self.contract_fixture()
        del fixture.artifacts[paths[1]]
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root, outside = base / "repository", base / "outside"
            contract_dir = root / "Game.Core/Contracts"
            contract_dir.mkdir(parents=True)
            outside.mkdir()
            external = outside / "Payload.cs"
            external.write_bytes(b"public sealed record Payload(int Amount);\r\n")
            link = contract_dir / "external"
            directory_link(link, outside)
            fixture.models[plan_path()]["evidence_source_refs"][0]["files"][1] = {
                "path": "Game.Core/Contracts/external/Payload.cs", "raw_digest": digest(external.read_bytes())}
            self.assert_invalid(records.validate_bundle(fixture.render(), root=root),
                                "unsafe_path", "path_unprovable")


class CommandLineReadOnlyTests(RecordAssertions):
    def run_cli(self, root, *arguments):
        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, "-B", str(REPOSITORY / "scripts/python/validate_b_route_records.py"),
             *arguments, "--repo-root", str(root)], cwd=root, env=environment,
            text=True, encoding="utf-8", capture_output=True, timeout=30)

    def write_inputs(self, root, bundle):
        rows = []
        for index, (logical_path, data) in enumerate(bundle.items()):
            source = f"inputs/{index}.json"
            target = root / source
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            rows.append({"path": logical_path, "source_path": source})
        (root / "carrier.json").write_bytes(encoded({"records": rows}))
        return rows

    def tree(self, root):
        return {path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
                for path in root.rglob("*") if path.is_file()}

    def test_record_and_bundle_cli_share_public_claims_and_never_write_inputs(self):
        fixture = MatrixFixture()
        output = fixture.render()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = self.write_inputs(root, output)
            policy_source = next(row["source_path"] for row in rows if row["path"] == POLICY)
            before = self.tree(root)
            for arguments, claim in (
                (("record", "--input", policy_source, "--record-path", POLICY), "record_structure_only"),
                (("bundle", "--input", "carrier.json", "--catalog-path", CATALOG), "candidate_structure_only"),
            ):
                with self.subTest(arguments=arguments):
                    completed = self.run_cli(root, *arguments)
                    self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                    payload = json.loads(completed.stdout)
                    self.assertTrue(payload["ok"], payload)
                    self.assertEqual(payload["claim"], claim)
            self.assertEqual(self.tree(root), before)

    def test_cli_negative_diagnostics_and_partial_triplet_fail_without_writes(self):
        fixture = MatrixFixture()
        output = fixture.render()
        output[plan_path()] += b" "
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write_inputs(root, output)
            before = self.tree(root)
            completed = self.run_cli(root, "bundle", "--input", "carrier.json")
            self.assertNotEqual(completed.returncode, 0)
            payload = json.loads(completed.stdout)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["diagnostic"]["reason_code"], "digest_mismatch")
            partial = self.run_cli(root, "bundle", "--input", "carrier.json",
                                   "--task-master", "inputs/0.json")
            self.assertNotEqual(partial.returncode, 0)
            partial_payload = json.loads(partial.stdout)
            self.assertFalse(partial_payload["ok"])
            self.assertEqual(self.tree(root), before)

    def test_carrier_rejects_duplicate_unknown_fields_and_root_escape(self):
        fixture = MatrixFixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            rows = self.write_inputs(root, fixture.render())
            for value in ({"records": rows + [deepcopy(rows[0])]},
                          {"records": rows, "private_options": {"skip_missing": True}},
                          {"records": [{"path": POLICY, "source_path": "../outside.json"}]}):
                with self.subTest(carrier=value):
                    (root / "carrier.json").write_bytes(encoded(value))
                    before = self.tree(root)
                    completed = self.run_cli(root, "bundle", "--input", "carrier.json")
                    self.assertNotEqual(completed.returncode, 0)
                    self.assertFalse(json.loads(completed.stdout)["ok"])
                    self.assertEqual(self.tree(root), before)


if __name__ == "__main__":
    unittest.main()
