"""Story 4.6 derived B-route Knowledge projection: planning, implementation and runtime identity."""

from __future__ import annotations

import hashlib
import http.client
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/python"))
sys.path.insert(0, str(ROOT / "scripts/python/tests"))

import _b_route_knowledge_projection as projection  # noqa: E402
import _b_route_records as records  # noqa: E402
import query_b_route_knowledge_projection as cli  # noqa: E402


def _junction_or_skip(case: unittest.TestCase, target: Path, link: Path) -> None:
    """Fall back to an unprivileged Windows directory junction when symlinks are not permitted."""
    if os.name != "nt":
        case.skipTest("symlink creation not permitted")
    proc = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                          capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        case.skipTest("symlink and junction creation not permitted")

DIAGNOSTIC_FIELDS = {"reason_code", "stage", "entity_id", "expected", "actual", "resume_ref"}
PYTHON = sys.executable
GIT_ENV = {**os.environ, "GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
           "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
PREFIX = "docs/planning/b-route/"
CATALOG = PREFIX + "catalog.v1.json"
POLICY = PREFIX + "policy.v1.json"
ORIGINS = PREFIX + "task-origins.v1.json"
PLAN = PREFIX + "plans/p/1.json"
COMMIT = PREFIX + "commits/operation-1.json"
MANIFEST = "docs/testing/mvg/m1.json"
PARTS = ("domain_rules", "csharp_adapter", "binding", "scene")


def sha(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def encoded(value) -> bytes:
    return (json.dumps(value, indent=2) + "\n").encode("utf-8")


def part(kind: str) -> dict:
    return {"kind": kind, "applicability": "applicable", "rationale": "Declared responsibility",
            "responsibilities": ["Preserve the documented boundary"]}


def flow_definition(flow_id: str, requirement_id: str) -> dict:
    return {
        "id": flow_id, "requirement_ids": [requirement_id], "entry": "Submit",
        "entry_condition": "A request is available", "success_end": "Return",
        "branches": [{"kind": "return", "rationale": "Retry is allowed",
                      "description": "Return to the entry after a rejected request"}],
        "handoffs": [], "state_owners": [], "parts": [part(kind) for kind in PARTS],
        "observable_result": "The player sees the result", "verification_targets": ["result"],
        "loops": [{"description": "Retry may return to entry", "exit_condition": "The caller accepts or cancels"}],
    }


def seal(receipt: dict) -> dict:
    import _b_route_scope_runner as runner
    runner._seal_receipt(receipt)
    return receipt


class Repo:
    """Synthetic repository with original authorities and a schema-valid committed B-route chain."""

    def __init__(self, root: Path):
        self.root = root

    def write(self, rel: str, data) -> bytes:
        raw = data if isinstance(data, bytes) else encoded(data) if not isinstance(data, str) else data.encode()
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return raw

    def ref(self, rel: str, raw: bytes, schema: str, entity: str, revision: int = 1) -> dict:
        return {"path": rel, "schema_version": schema, "entity_id": entity, "revision": revision,
                "digest": sha(raw), "verification_mode": "raw", "codec_version": None}

    def owned(self, owner: str, rel: str) -> dict:
        return {"owner": owner, "ref": rel, "files": [{"path": rel, "raw_digest": sha((self.root / rel).read_bytes())}]}

    def seed_authorities(self) -> None:
        source = self.write("docs/gdd/source.md", "# Source\nPreserve the result.\n")
        self.write("docs/workflows/chapter3-source-set.json", {"sources": [{"path": "docs/gdd/source.md"}]})
        self.write("docs/planning/semantic-topology/source-blocks.v1.json", {
            "schema_version": "newrouge.source-blocks.v1",
            "blocks": [{"block_id": "SB-1", "source_path": "docs/gdd/source.md",
                        "source_sha256": hashlib.sha256(source).hexdigest()}]})
        self.write("docs/planning/semantic-topology/semantic-requirements.v1.json", {
            "requirements": [
                {"requirement_id": "REQ-1", "source_block_ids": ["SB-1"], "capability_ids": ["CAP-1"],
                 "sink_policy": "task_required"},
                {"requirement_id": "REQ-DEFER", "source_block_ids": ["SB-1"], "capability_ids": [],
                 "sink_policy": "deferred"}]})
        self.write("docs/planning/semantic-topology/capabilities.v1.json", {
            "capabilities": [{"capability_id": "CAP-1", "title": "Core", "requirement_ids": ["REQ-1", "REQ-B1"]}]})
        self.write("docs/planning/semantic-topology/topology-edges.v1.json", {"edges": [
            {"source_type": "source_block", "source_id": "SB-1", "target_type": "requirement",
             "target_id": "REQ-1", "relation": "projects_to"}]})
        self.write(".taskmaster/tasks/tasks.json", {"master": {"tasks": [
            {"id": 1, "title": "Save contract", "status": "done", "dependencies": [],
             "details": "Implements Game.Core/Contracts/Save/Thing.cs and Game.Godot/Scenes/Main.tscn"},
            {"id": 2, "title": "Follow up", "status": "pending", "dependencies": [1], "details": "None"}]}})
        self.write(".taskmaster/tasks/tasks_back.json", [{"id": "B-1", "taskmaster_id": 1}])
        self.write(".taskmaster/tasks/tasks_gameplay.json", [{"id": "G-1", "taskmaster_id": 1}])
        self.write("Game.Core/Contracts/Save/Thing.cs", "namespace Game.Core.Contracts.Save; public sealed class Thing {}\n")
        self.write("Game.Core.Tests/ThingTests.cs", "public sealed class ThingTests {}\n")
        self.write("Tests.Godot/tests/test_c.gd", "extends GdUnitTestSuite\n")
        self.write("docs/adr/ADR-9000-fixture.md", "# ADR fixture\n")
        self.write(MANIFEST, {
            "schema_version": "newrouge.mvg-integration.v1", "mvg_id": "m1", "coverage": {"mode": "full"},
            "flows": [
                {"id": "flow-a", "task_ids": [1], "test_ids": ["t-unit", "t-planned"],
                 "source_paths": ["Game.Core/Contracts/Save/Thing.cs"], "handoffs": []},
                {"id": "flow-c", "task_ids": [2], "test_ids": ["t-gd"]},
                {"id": "flow-future", "status": "planned", "task_ids": [2], "test_ids": ["t-planned"]}],
            "tests": [
                {"id": "t-unit", "kind": "dotnet", "state": "implemented", "evidence_level": "domain-xunit",
                 "path": "Game.Core.Tests/ThingTests.cs"},
                {"id": "t-gd", "kind": "godot", "state": "implemented", "evidence_level": "engine-input",
                 "path": "Tests.Godot/tests/test_c.gd"},
                {"id": "t-planned", "kind": "godot", "state": "planned", "evidence_level": "godot-gdunit",
                 "path": "Tests.Godot/tests/test_future.gd"}]})
        self.write("knowledge/policies/source-exclusions.v1.json",
                   (ROOT / "knowledge/policies/source-exclusions.v1.json").read_bytes())

    def seed_b_route(self, *, default_route: str = "A", second_disposition: str = "other_verification") -> None:
        source_revision = "source-set:" + "0" * 24
        verification_b1 = {"requirement_id": "REQ-B1", "disposition": "flow", "flow_id": "flow-b",
                           "rationale": "Flow", "sink_id": None, "verification_ref": None,
                           "authority_ref": None, "evidence_ids": []}
        if second_disposition == "other_verification":
            verification_b2 = {"requirement_id": "REQ-B2", "disposition": "other_verification", "flow_id": None,
                               "rationale": "Global architecture constraint", "sink_id": "sink-adr",
                               "verification_ref": "docs/adr/ADR-9000-fixture.md", "authority_ref": None,
                               "evidence_ids": []}
            app_b2 = {"requirement_id": "REQ-B2", "disposition": "other_verification",
                      "rationale": "Global architecture constraint",
                      "other_verification_refs": [self.owned("other_verification", "docs/adr/ADR-9000-fixture.md")]}
        else:
            verification_b2 = {"requirement_id": "REQ-B2", "disposition": "source_gap", "flow_id": None,
                               "rationale": "The missing source remains explicit", "sink_id": None,
                               "verification_ref": None, "authority_ref": None, "evidence_ids": []}
            app_b2 = {"requirement_id": "REQ-B2", "disposition": "source_gap",
                      "rationale": "The missing source remains explicit", "other_verification_refs": []}
        verification = [verification_b1, verification_b2]
        plan = {
            "schema_version": "newrouge.b-route-plan.v1", "plan_id": "p", "revision": 1,
            "source_identity": {"manifest_ref": self.owned("source_manifest", "docs/gdd/source.md"),
                                "ledger_ref": self.owned("source_ledger", "docs/workflows/chapter3-source-set.json"),
                                "source_revision": source_revision, "source_manifest_digest": "sha256:" + "0" * 64},
            "requirements": [
                {"requirement_id": "REQ-B1", "source_block_ids": ["SB-1"], "acceptance_intent": "Show result",
                 "non_task_sinks": []},
                {"requirement_id": "REQ-B2", "source_block_ids": ["SB-1"], "acceptance_intent": "Global rule",
                 "non_task_sinks": ["sink-adr"]}],
            "definitions": {"flows": [flow_definition("flow-b", "REQ-B1")], "commands": [], "states": []},
            "logical_references": [], "requirement_verification": verification,
            "requirement_route_memberships": [{"requirement_id": "REQ-B1", "flow_id": "flow-b",
                                               "observable_role": "Observe the result"}],
            "requirement_evidence": [], "evidence_source_refs": [],
            "coverage_table": [{k: v for k, v in row.items() if k != "evidence_ids"} for row in verification],
            "applicability": [{"requirement_id": "REQ-B1", "disposition": "flow", "rationale": "Flow",
                               "other_verification_refs": []}, app_b2],
            "adoption_proof_refs": [self.owned("planning_proof", "docs/gdd/source.md")],
            "lineage": {"previous_plan_ref": None, "change_summary": "Initial declaration", "identity_alignment": []},
        }
        plan_raw = self.write(PLAN, plan)
        policy_raw = self.write(POLICY, {
            "schema_version": "newrouge.b-route-policy.v1", "policy_id": "policy-1", "policy_revision": 1,
            "switch_boundary": {"default_route": default_route, "a_write_allowed": default_route == "A",
                                "allowed_a_operations": ["resume-task"], "authority_refs": []},
            "frozen_a_refs": []})
        origins_raw = self.write(ORIGINS, {"schema_version": "newrouge.b-route-origins.v1",
                                           "origins_id": "task-origins", "revision": 1, "tasks": [],
                                           "frozen_legacy_refs": []})
        plan_ref = self.ref(PLAN, plan_raw, "newrouge.b-route-plan.v1", "p")
        outputs = {POLICY: policy_raw, ORIGINS: origins_raw, PLAN: plan_raw}
        commit_raw = self.write(COMMIT, {
            "schema_version": "newrouge.b-route-commit.v1", "operation_id": "operation-1", "revision": 1,
            "operation_digest": sha(b"frozen operation request"), "scopes": ["scope-1"], "authority": [],
            "targets": [{"path": path, "before_digest": None, "after_digest": sha(raw),
                         "verification_mode": "immutable_bytes", "codec_version": None,
                         "projection_digest": sha(raw)} for path, raw in outputs.items()],
            "plan_refs": [plan_ref], "binding_refs": [], "resolved_definitions": [],
            "result": {"target_paths": list(outputs), "scope_ids": ["scope-1"]}})
        self.write(CATALOG, {
            "schema_version": "newrouge.b-route-catalog.v1", "catalog_id": "catalog", "revision": 1,
            "policy_ref": self.ref(POLICY, policy_raw, "newrouge.b-route-policy.v1", "policy-1"),
            "origins_ref": self.ref(ORIGINS, origins_raw, "newrouge.b-route-origins.v1", "task-origins"),
            "scope_heads": [{"scope_id": "scope-1", "plan_refs": [plan_ref], "binding_refs": [],
                             "receipt_ref": self.ref(COMMIT, commit_raw, "newrouge.b-route-commit.v1", "operation-1")}],
            "definition_owners": [{"kind": "flow", "definition_id": "flow-b", "plan_ref": plan_ref}],
            "task_index": []})

    def git(self, *args: str) -> str:
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, text=True,
                              env=GIT_ENV).stdout.strip()

    def commit_main(self) -> str:
        self.write(".gitignore", "logs/\n")
        self.git("init", "-q")
        self.git("config", "core.autocrlf", "false")
        self.git("add", ".")
        self.git("commit", "-q", "-m", "fixture")
        self.git("branch", "-M", "main")
        return self.git("rev-parse", "HEAD")

    def digest_tree(self, *prefixes: str) -> dict:
        result = {}
        for path in sorted(self.root.rglob("*")):
            rel = path.relative_to(self.root).as_posix()
            if path.is_file() and not rel.startswith((".git/", "logs/")) and (not prefixes or rel.startswith(prefixes)):
                result[rel] = sha(path.read_bytes())
        return result


class ProjectionTestBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.repo = Repo(self.root)
        self.env = patch.dict(os.environ, {}, clear=False)
        self.env.start()
        os.environ.pop("SC_MVG_RECOVERY_ROOT", None)
        os.environ.pop("SC_MVG_RECOVERY_EPOCH", None)

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def build(self, **kwargs):
        kwargs.setdefault("mode", "workspace_preview")
        return projection.build_b_route_knowledge_projection(self.root, **kwargs)

    @staticmethod
    def node(result, layer, node_id):
        return next(n for n in result["layers"][layer] if n["id"] == node_id)

    def assert_six_field(self, diagnostic):
        self.assertEqual(DIAGNOSTIC_FIELDS, set(diagnostic))

    def codes(self, result):
        return {d["reason_code"] for d in result["diagnostics"]}

    def write_run(self, run_id: str, revision, *, fixture=False, status="passed", scope="full",
                  tests=("t-unit", "t-gd"), extra_tests=(), finished="2026-01-02T03:04:05+00:00",
                  tamper=False, workspace_dirty=False):
        manifest_sha = sha((self.root / MANIFEST).read_bytes())
        summary = {"run_id": run_id, "manifest": MANIFEST, "manifest_sha256": manifest_sha, "mode": "run",
                   "status": status, "runtime_verified": status == "passed", "source_revision": revision,
                   "base_commit": revision, "finished_at": finished, "protocol_fixture_only": fixture,
                   "workspace_dirty": workspace_dirty, "snapshot_digest": "sha256:" + "1" * 64}
        levels = {"t-unit": ("dotnet", "domain-xunit", ["flow-a"]), "t-gd": ("gdunit", "engine-input", ["flow-c"])}
        executed = [{"test_id": t, "kind": levels[t][0], "evidence_level": levels[t][1], "status": status,
                     "referencing_flow_ids": levels[t][2], "requirement_ids": []} for t in tests]
        executed += list(extra_tests)
        receipt = seal({"schema_version": "newrouge.b-route-execution-receipt.v1", "receipt_id": "",
                        "run_id": run_id, "scope_id": "scope-1", "source_revision": revision,
                        "runtime_verified": status == "passed", "status": status, "mode": "run",
                        "verified_scope": scope, "execution_strategy_used": "scoped" if scope != "full" else "full",
                        "original_executed_at": finished, "environment": {"protocol_fixture_only": fixture},
                        "executed_tests": executed, "not_run": [],
                        "evidence_tiers": {"domain-xunit": {"count": 1, "passed": 1 if "t-unit" in tests else 0},
                                           "engine-input": {"count": 1, "passed": 1 if "t-gd" in tests else 0}}})
        if tamper:
            receipt["verified_scope"] = "full"
            receipt["executed_tests"].append({"test_id": "t-gd", "status": "passed", "evidence_level": "engine-input",
                                              "referencing_flow_ids": ["flow-c"]})
        base = f"logs/ci/mvg-acceptance/{run_id}"
        self.repo.write(base + "/summary.json", summary)
        self.repo.write(base + "/coverage-receipt.json", receipt)
        return base


class FixtureValidityTests(ProjectionTestBase):
    def test_fixture_records_pass_formal_record_validation(self):
        self.repo.seed_authorities()
        self.repo.seed_b_route()
        for rel in (CATALOG, POLICY, ORIGINS, PLAN, COMMIT):
            with self.subTest(rel=rel):
                result = records.validate_record((self.root / rel).read_bytes(), path=rel)
                self.assertTrue(result.ok, result.to_dict())
        built = self.build()
        self.assertTrue(built["ok"], built["issues"])
        self.assertEqual("valid", built["catalog"]["status"])
        self.assertTrue(all(r["schema_validated"] for r in built["records"]))


class DerivedGraphTests(ProjectionTestBase):
    """AC-1: ten-layer derived chain with separated four dimensions and explicit backlinks."""

    def test_ten_layer_chain_keeps_planning_implementation_runtime_and_evidence_separate(self):
        self.repo.seed_authorities()
        self.repo.seed_b_route()
        before = self.repo.digest_tree()
        result = self.build()
        self.assertEqual(projection.SCHEMA_VERSION, result["schema_version"])
        for layer in ("sources", "requirements", "capabilities", "flows", "four_parts", "tasks",
                      "contracts", "scenes", "obligations"):
            self.assertTrue(result["layers"][layer], layer)
        self.assertIn("impact", result["layers"])
        relations = {(e["from"], e["to"]) for e in result["edges"]}
        self.assertIn(("source:SB-1", "requirement:REQ-1"), relations)
        self.assertIn(("requirement:REQ-1", "capability:CAP-1"), relations)
        self.assertIn(("capability:CAP-1", "flow:flow-b"), relations)
        self.assertIn(("flow:flow-b", "four_part:flow:flow-b"), relations)
        self.assertIn(("flow:flow-a", "task:1"), relations)
        self.assertIn(("task:1", "contract:Game.Core/Contracts/Save/Thing.cs"), relations)
        self.assertIn(("task:1", "scene:Game.Godot/Scenes/Main.tscn"), relations)
        self.assertIn(("flow:flow-a", "obligation:flow-a:t-unit"), relations)
        self.assertIn(("task:2", "task:1"), relations)
        task = self.node(result, "tasks", "1")
        self.assertEqual("done_in_taskmaster", task["implementation_state"])
        self.assertEqual("unverified", task["runtime_state"])
        self.assertEqual("unverified", task["evidence_level"])
        for layer, nodes in result["layers"].items():
            if layer == "impact":
                continue
            for node in nodes:
                self.assertIn(node["planning_state"], projection.PLANNING_STATES)
                self.assertIn(node["implementation_state"], projection.IMPLEMENTATION_STATES)
                self.assertIn(node["runtime_state"], projection.RUNTIME_STATES)
                self.assertIn(node["evidence_level"], projection.EVIDENCE_LEVELS)
        self.assertFalse(result["runtime_verified"])
        self.assertFalse(result["invariants"]["relation_implies_implementation"])
        self.assertEqual(before, self.repo.digest_tree())

    def test_runtime_reports_are_backlinks_preserving_original_timestamps(self):
        self.repo.seed_authorities()
        base = self.write_run("run-1", "0" * 40, finished="2025-05-05T05:05:05+00:00")
        raw = (self.root / base / "summary.json").read_bytes()
        result = self.build()
        link = next(b for b in result["backlinks"] if b["kind"] == "mvg_summary")
        for key in ("kind", "path", "sha256", "run_id", "source_revision", "snapshot_digest",
                    "original_executed_at", "runtime_verified", "evidence_levels"):
            self.assertIn(key, link)
        self.assertEqual(sha(raw), link["sha256"])
        self.assertEqual("2025-05-05T05:05:05+00:00", link["original_executed_at"])
        self.assertEqual("2025-05-05T05:05:05+00:00", link["coverage_receipt"]["original_executed_at"])
        self.assertEqual("valid", link["receipt_state"])
        self.assertFalse(link["credited"])
        self.assertEqual("stale_revision", self.node(result, "flows", "flow-a")["runtime_state"])
        self.assertEqual(raw, (self.root / base / "summary.json").read_bytes())

    def test_cumulative_full_receipt_credits_all_current_flows_never_planned(self):
        self.repo.seed_authorities()
        commit = self.repo.commit_main()
        self.write_run("run-2", commit)
        main = self.build(mode="main")
        for fid in ("flow-a", "flow-c"):
            self.assertEqual("passed_cumulative_mvg", self.node(main, "flows", fid)["runtime_state"], fid)
        self.assertEqual(["unit_deterministic"], self.node(main, "flows", "flow-a")["evidence_levels"])
        self.assertEqual("real_engine_input", self.node(main, "flows", "flow-c")["evidence_level"])
        self.assertEqual("unverified", self.node(main, "flows", "flow-future")["runtime_state"])
        self.assertTrue(main["runtime_verified"], main["issues"])
        preview = self.build(mode="workspace_preview")
        self.assertEqual("workspace_only", self.node(preview, "flows", "flow-a")["runtime_state"])
        self.write_run("run-2", commit, fixture=True)
        fixture = self.build(mode="main")
        self.assertEqual("failed", self.node(fixture, "flows", "flow-a")["runtime_state"])
        self.assertFalse(fixture["runtime_verified"])
        self.write_run("run-2", commit, workspace_dirty=True)
        dirty = self.build(mode="main")
        self.assertEqual("workspace_only", self.node(dirty, "flows", "flow-a")["runtime_state"])

    def test_scoped_receipt_credits_only_executed_flow_and_tampered_receipt_is_rejected(self):
        self.repo.seed_authorities()
        self.repo.seed_b_route()
        commit = self.repo.commit_main()
        other = {"test_id": "ov-1", "kind": "other_verification", "evidence_level": "other-verification",
                 "status": "passed", "requirement_ids": ["REQ-B2"], "referencing_flow_ids": []}
        self.write_run("run-3", commit, scope="scoped", tests=("t-unit",), extra_tests=(other,))
        scoped = self.build(mode="main")
        self.assertEqual("passed_flow_scope", self.node(scoped, "flows", "flow-a")["runtime_state"])
        self.assertEqual("unverified", self.node(scoped, "flows", "flow-c")["runtime_state"])
        self.assertEqual("unverified", self.node(scoped, "flows", "flow-future")["runtime_state"])
        self.assertFalse(scoped["runtime_verified"])
        manifest = next(m for m in scoped["manifests"] if m["path"] == MANIFEST)
        self.assertEqual("passed_flow_scope", manifest["runtime_state"])
        requirement = self.node(scoped, "requirements", "REQ-B2")
        self.assertEqual("passed_other_verification", requirement["runtime_state"])
        self.assertEqual("other_verification", requirement["evidence_level"])
        self.assertEqual("passed_other_verification", self.node(scoped, "obligations", "other:REQ-B2")["runtime_state"])
        self.write_run("run-3", commit, scope="scoped", tests=("t-unit",), tamper=True)
        tampered = self.build(mode="main")
        self.assertEqual("failed", self.node(tampered, "flows", "flow-a")["runtime_state"])
        self.assertFalse(self.node(tampered, "flows", "flow-c")["runtime_state"].startswith("passed_"))
        link = next(b for b in tampered["backlinks"] if b["kind"] == "mvg_summary")
        self.assertEqual("invalid", link["receipt_state"])
        self.assertFalse(link["credited"])
        self.assertIn("digest_mismatch", self.codes(tampered))
        self.repo.write("logs/ci/mvg-acceptance/run-3/coverage-receipt.json", b"{\"broken\": NaN}")
        corrupt = self.build(mode="main")
        self.assertEqual("failed", self.node(corrupt, "flows", "flow-a")["runtime_state"])
        self.assertIn("non_finite_number", self.codes(corrupt))

    def test_newest_runs_are_selected_before_limit(self):
        self.repo.seed_authorities()
        commit = self.repo.commit_main()
        self.write_run("run-0001", "0" * 40)
        self.write_run("run-0002", commit)
        with patch.object(projection, "MAX_RUNTIME_RUNS", 1):
            result = self.build(mode="main")
        self.assertEqual(["logs/ci/mvg-acceptance/run-0002/summary.json"],
                         [b["path"] for b in result["backlinks"] if b["kind"] == "mvg_summary"])
        self.assertEqual("passed_cumulative_mvg", self.node(result, "flows", "flow-a")["runtime_state"])


class ImpactDelegationTests(ProjectionTestBase):
    """AC-1: the impact layer delegates to Story 4.1 compute_impact_closure."""

    def setUp(self):
        super().setUp()
        import test_b_route_impact_closure as impact_fixture
        impact_fixture._build_fixture(self.root)

    def test_filtered_impact_matches_governed_closure_without_sideways_leak(self):
        import _b_route_impact_closure as closure
        for kwargs, roots in (({"task_id": "84"}, ["task:84"]), ({"flow_id": "reward-loop"}, ["flow:reward-loop"])):
            with self.subTest(roots=roots):
                impact = self.build(**kwargs)["layers"]["impact"]
                direct = closure.compute_impact_closure(self.root, change_roots=roots)
                self.assertEqual("_b_route_impact_closure.compute_impact_closure", impact["computed_by"])
                self.assertEqual("computed", impact["status"], impact["diagnostics"])
                self.assertEqual(roots, impact["targets"])
                self.assertEqual(direct["impact_proof_id"], impact["impact_proof_id"])
                expected = {f"{kind}:{item['entity_id']}" for kind, name in closure.REPORTED_LISTS
                            for item in direct[name]}
                self.assertTrue(expected <= set(impact["impacted"]))
                self.assertNotIn("task:7", impact["impacted"])
        task_impact = self.build(task_id="84")["layers"]["impact"]
        self.assertIn("task:128", task_impact["impacted"])
        flow_impact = self.build(flow_id="reward-loop")["layers"]["impact"]
        self.assertNotIn("task:128", flow_impact["impacted"])
        self.assertTrue(task_impact["impact_accounting_only"])
        self.assertFalse(task_impact["runtime_verified"])

    def test_unfiltered_impact_on_governed_scopes_is_nonempty(self):
        impact = self.build()["layers"]["impact"]
        self.assertIn("flow:combat-reward-return", impact["targets"])
        self.assertNotIn("flow:relic-synergy-preview", impact["targets"])
        self.assertEqual("computed", impact["status"], impact["diagnostics"])
        self.assertTrue(impact["impacted"])
        self.assertNotIn("task:7", impact["impacted"])

    def test_legacy_repository_has_empty_impact(self):
        empty = Path(self.temp.name) / "empty"
        empty.mkdir()
        result = projection.build_b_route_knowledge_projection(empty, mode="workspace_preview")
        self.assertEqual("legacy_unmapped", result["status"])
        self.assertEqual([], result["layers"]["impact"]["targets"])
        self.assertEqual([], result["layers"]["impact"]["impacted"])


class ProvenanceTests(ProjectionTestBase):
    """AC-2: snapshot identity, ADR-0035 dirty/untracked check, partial planning, zero pointer mutation."""

    def test_main_reads_committed_tree_and_dirty_edits_never_masquerade_as_main(self):
        self.repo.seed_authorities()
        commit = self.repo.commit_main()
        clean = self.build(mode="main")
        self.assertTrue(clean["provenance"]["is_main_fact"])
        self.assertTrue(clean["provenance"]["trusted_ref_eligible"])
        self.assertEqual(commit, clean["provenance"]["snapshot_commit"])
        tasks = json.loads((self.root / ".taskmaster/tasks/tasks.json").read_text())
        tasks["master"]["tasks"][1]["status"] = "done"
        self.repo.write(".taskmaster/tasks/tasks.json", tasks)
        main = self.build(mode="main")
        self.assertEqual("pending", self.node(main, "tasks", "2")["implementation_state"])
        self.assertTrue(main["provenance"]["dirty_workspace"])
        self.assertFalse(main["provenance"]["is_main_fact"])
        self.assertFalse(main["provenance"]["trusted_ref_eligible"])
        self.assertFalse(main["provenance"]["can_advance_canonical"])
        self.assertEqual("refs/heads/main", main["provenance"]["snapshot_source"])
        preview = self.build(mode="workspace_preview")
        self.assertEqual("done_in_taskmaster", self.node(preview, "tasks", "2")["implementation_state"])
        self.assertFalse(preview["provenance"]["is_main_fact"])
        self.assertEqual("local-workspace", preview["provenance"]["authority_ref"])
        self.assertNotEqual(main["provenance"]["snapshot_digest"], preview["provenance"]["snapshot_digest"])
        import publish_knowledge_catalog
        with self.assertRaises(Exception):
            publish_knowledge_catalog.publish(self.root, "refs/heads/main")
        self.assertFalse((self.root / "knowledge/indexes/current.json").exists())

    def test_untracked_authority_file_revokes_main_fact_using_committed_exclusions(self):
        self.repo.seed_authorities()
        self.repo.seed_b_route(default_route="B")
        self.repo.commit_main()
        clean = self.build(mode="main")
        self.assertTrue(clean["provenance"]["is_main_fact"], clean["warnings"])
        self.assertTrue(clean["default_b_enabled"], clean["issues"])
        self.repo.write("backup/old.md", "# excluded by committed policy\n")
        self.assertTrue(self.build(mode="main")["provenance"]["trusted_ref_eligible"])
        committed = (self.root / projection.SOURCE_EXCLUSIONS_PATH).read_bytes()
        policy = json.loads(committed)
        policy["rules"].append({"id": "dirty", "disposition": "excluded", "path_prefix": "docs/gdd"})
        self.repo.write(projection.SOURCE_EXCLUSIONS_PATH, policy)
        self.repo.write("docs/gdd/new-authority.md", "# untracked authority\n")
        dirty = self.build(mode="main")
        provenance = dirty["provenance"]
        self.assertFalse(provenance["is_main_fact"])
        self.assertFalse(provenance["trusted_ref_eligible"])
        self.assertFalse(provenance["can_advance_canonical"])
        self.assertFalse(dirty["default_b_enabled"])
        self.assertIn("docs/gdd/new-authority.md", provenance["dirty_untracked_paths"])
        self.assertEqual(sha(committed), dirty["knowledge_boundary"]["source_exclusions_sha256"])
        self.assertEqual("refs/heads/main", dirty["knowledge_boundary"]["source_exclusions_source"])
        self.assertEqual("3b_adopted_awaiting_3c", self.node(dirty, "flows", "flow-b")["planning_state"])

    def test_non_git_main_is_not_main_fact_and_workspace_views_bind_identity(self):
        self.repo.seed_authorities()
        result = self.build(mode="main")
        self.assertFalse(result["provenance"]["is_main_fact"])
        self.assertFalse(result["provenance"]["trusted_ref_eligible"])
        self.assertFalse(result["provenance"]["can_advance_canonical"])
        self.assertTrue(result["warnings"])
        self.assert_six_field(result["warnings"][0])
        self.repo.write("logs/ci/project-health-knowledge/topology/workspace-last-attempt.json", {
            "identity": {"kind": "workspace", "revision": "run:attempt-1"}, "available": True})
        for view in ("attempt", "stable", "stabilized"):
            view_result = self.build(mode=view)
            self.assertEqual(view, view_result["provenance"]["workspace_view"])
            self.assertFalse(view_result["provenance"]["is_main_fact"])
        attempt = self.build(mode="attempt")
        self.assertEqual("run:attempt-1", attempt["provenance"]["workspace_topology_identity"]["revision"])

    def test_partial_prefix_is_partial_planning_and_pointers_are_untouched(self):
        self.repo.seed_authorities()
        pointers = {}
        for rel in projection.PROTECTED_POINTERS:
            pointers[rel] = self.repo.write(rel, {"pointer": rel})
        with patch("_project_health_planning.mvg_progress",
                   return_value={"epoch": 0, "completed": 1, "total": 3, "job_status": "running"}):
            result = self.build(mode="workspace_preview")
        self.assertEqual("partial_planning", result["status"])
        self.assertEqual("partial_planning", result["planning_completeness"])
        self.assertFalse(result["planning_complete"])
        self.assertFalse(result["runtime_verified"])
        self.assertTrue(result["ok"])
        for rel, raw in pointers.items():
            self.assertEqual(raw, (self.root / rel).read_bytes())

    def test_main_planning_is_not_tainted_by_local_progress_but_never_claims_complete(self):
        self.repo.seed_authorities()
        self.repo.seed_b_route()
        self.repo.commit_main()
        with patch("_project_health_planning.mvg_progress",
                   return_value={"epoch": 0, "completed": 1, "total": 3, "job_status": "running"}):
            main = self.build(mode="main")
        self.assertNotEqual("partial_planning", main["status"])
        self.assertTrue(main["planning_progress"]["workspace_local_progress"]["partial"])
        self.assertFalse(main["planning_complete"])
        self.assertGreater(main["summary"]["awaiting_3c"], 0)

    def test_invalid_mode_and_filters_raise_structured_diagnostics(self):
        for bad in ("bogus", "", True, None):
            with self.assertRaises(projection.codec.CodecError) as ctx:
                projection.build_b_route_knowledge_projection(self.root, mode=bad)
            self.assert_six_field(ctx.exception.diagnostic.to_dict())
        with self.assertRaises(projection.codec.CodecError):
            projection.build_b_route_knowledge_projection(self.root, mode="main", task_id="../1")

    def test_clean_clone_reads_committed_chain_without_logs(self):
        self.repo.seed_authorities()
        self.repo.seed_b_route()
        self.repo.commit_main()
        clone = Path(self.temp.name) / "clone"
        subprocess.run(["git", "clone", "-q", "--config", "core.autocrlf=false", str(self.root), str(clone)],
                       check=True, capture_output=True, env=GIT_ENV)
        self.assertFalse((clone / "logs").exists())
        for mode in ("main", "workspace_preview"):
            with self.subTest(mode=mode):
                result = projection.build_b_route_knowledge_projection(clone, mode=mode)
                self.assertTrue(result["ok"], result["issues"])
                self.assertEqual("valid", result["catalog"]["status"])
                paths = {r["path"] for r in result["records"]}
                self.assertTrue({CATALOG, PLAN, COMMIT, ORIGINS, POLICY} <= paths)
                self.assertEqual("3b_adopted_awaiting_3c", self.node(result, "flows", "flow-b")["planning_state"])
        self.assertTrue(projection.build_b_route_knowledge_projection(clone, mode="main")["provenance"]["is_main_fact"])
        self.assertFalse((clone / "logs").exists())


class NoTaskAndNonFlowTests(ProjectionTestBase):
    """AC-3: zero-Task formal 3B adoption, legal non-Flow and planned-only resources."""

    def test_zero_task_adoption_projects_awaiting_3c_without_fake_tasks(self):
        self.repo.seed_authorities()
        self.repo.seed_b_route()
        result = self.build()
        self.assertTrue(result["ok"], result["issues"])
        flow = self.node(result, "flows", "flow-b")
        self.assertEqual("3b_adopted_awaiting_3c", flow["planning_state"])
        self.assertEqual("no_task_yet", flow["implementation_state"])
        self.assertEqual("awaiting_3c_task_compilation", flow["verification_destination"])
        self.assertFalse(flow["task_readiness_blocking"])
        self.assertEqual([], flow["task_ids"])
        four = self.node(result, "four_parts", "flow:flow-b")
        self.assertEqual(set(projection.LOGICAL_FOUR_PART), set(four["logical_four_part"]))
        self.assertEqual("The player sees the result",
                         four["logical_four_part"]["user_visible_feedback"]["observable_result"])
        self.assertEqual(["1", "2"], sorted(n["id"] for n in result["layers"]["tasks"]))
        self.assertEqual("3b_adopted_awaiting_3c", self.node(result, "requirements", "REQ-B1")["planning_state"])
        self.assertFalse(result["planning_complete"])

    def test_legal_non_flow_and_deferred_sinks_are_governed_without_tasks(self):
        self.repo.seed_authorities()
        self.repo.seed_b_route()
        result = self.build()
        requirement = self.node(result, "requirements", "REQ-B2")
        self.assertEqual("non_flow_governed", requirement["planning_state"])
        self.assertEqual("not_applicable_non_flow", requirement["implementation_state"])
        self.assertEqual(["docs/adr/ADR-9000-fixture.md"],
                         requirement["verification_destination"]["other_verification_refs"])
        four = self.node(result, "four_parts", "requirement:REQ-B2")
        self.assertEqual("non_flow_governed", four["planning_state"])
        self.assertEqual("other_verification", self.node(result, "obligations", "other:REQ-B2")["obligation_class"])
        self.assertEqual("non_flow_governed", self.node(result, "requirements", "REQ-DEFER")["planning_state"])

    def test_source_gap_is_blocked_never_legal_non_flow(self):
        self.repo.seed_authorities()
        self.repo.seed_b_route(second_disposition="source_gap")
        result = self.build()
        requirement = self.node(result, "requirements", "REQ-B2")
        self.assertEqual("blocked", requirement["planning_state"])
        self.assertNotEqual("non_flow_governed", requirement["planning_state"])
        self.assertEqual("blocked", result["status"])
        self.assertFalse(result["ok"])
        self.assert_six_field(requirement["diagnostics"][0])
        self.assertEqual("unresolved_reference", requirement["diagnostics"][0]["reason_code"])

    def test_planned_resources_are_planned_only_and_never_real_files(self):
        self.repo.seed_authorities()
        result = self.build()
        scene = self.node(result, "scenes", "Game.Godot/Scenes/Main.tscn")
        self.assertTrue(scene["planned_only"])
        self.assertFalse(scene["resource_exists"])
        self.assertEqual("planned_unimplemented", scene["implementation_state"])
        contract = self.node(result, "contracts", "Game.Core/Contracts/Save/Thing.cs")
        self.assertTrue(contract["resource_exists"])
        self.assertFalse(contract["planned_only"])
        planned_test = self.node(result, "obligations", "flow-a:t-planned")
        self.assertEqual("out_of_scope_future", planned_test["obligation_class"])
        self.assertTrue(planned_test["planned_only"])
        self.assertEqual("existing_required", self.node(result, "obligations", "flow-a:t-unit")["obligation_class"])
        future = self.node(result, "flows", "flow-future")
        self.assertEqual("planned_future", future["planning_state"])
        self.assertTrue(future["planned_only"])


class StaleAndRevocationTests(ProjectionTestBase):
    """AC-4: stale proof, pending journals, epoch/reopen revocation and corruption."""

    def test_expired_source_proof_marks_stale_with_six_field_diagnostic(self):
        self.repo.seed_authorities()
        self.repo.seed_b_route()
        self.repo.write("docs/gdd/source.md", "# Source\nChanged after adoption.\n")
        result = self.build()
        self.assertEqual("stale", self.node(result, "flows", "flow-b")["planning_state"])
        stale = [i for i in result["issues"] if i["status"] == "stale" and i["original_locator"] == PLAN]
        self.assertTrue(stale)
        self.assert_six_field(stale[0]["diagnostic"])
        self.assertEqual("input_stale", stale[0]["diagnostic"]["reason_code"])

    def test_corrupt_unknown_missing_invalid_and_tampered_records_block(self):
        def broken_head(r):
            doc = json.loads((r.root / CATALOG).read_text())
            doc["scope_heads"] = {"scope-1": doc["scope_heads"][0]}
            r.write(CATALOG, doc)

        def invalid_record(r):
            doc = json.loads((r.root / CATALOG).read_text())
            doc["unexpected_field"] = True
            r.write(CATALOG, doc)

        cases = {
            "invalid_json": lambda r: r.write(CATALOG, b"{broken"),
            "unknown_schema": lambda r: r.write(CATALOG, {"schema_version": "newrouge.b-route-catalog.v9"}),
            "duplicate_key": lambda r: r.write(CATALOG, b'{"schema_version": "a", "schema_version": "b"}'),
            "non_finite_number": lambda r: r.write(CATALOG, b'{"schema_version": NaN}'),
            "invalid_type": broken_head,
            "unknown_field": invalid_record,
            "digest_mismatch": lambda r: r.write(PLAN, (r.root / PLAN).read_bytes() + b" "),
            "file_not_found": lambda r: (r.root / COMMIT).unlink(),
        }
        for code, mutate in cases.items():
            with self.subTest(code=code):
                self.repo.seed_authorities()
                self.repo.seed_b_route()
                mutate(self.repo)
                result = self.build()
                self.assertEqual("blocked", result["status"])
                self.assertFalse(result["ok"])
                self.assertEqual("blocked", result["catalog"]["status"])
                self.assertIn(code, self.codes(result))
                blocked = [i for i in result["issues"] if i["status"] == "blocked"]
                self.assert_six_field(blocked[0]["diagnostic"])
                self.assertTrue(blocked[0]["original_locator"])
                self.assertFalse(result["default_b_enabled"])

    def test_plan_record_failing_formal_validation_blocks_chain(self):
        self.repo.seed_authorities()
        self.repo.seed_b_route()
        plan = json.loads((self.root / PLAN).read_text())
        plan["requirements"][0]["requirement_id"] = True
        raw = self.repo.write(PLAN, plan)
        catalog = json.loads((self.root / CATALOG).read_text())
        catalog["scope_heads"][0]["plan_refs"][0]["digest"] = sha(raw)
        self.repo.write(CATALOG, catalog)
        result = self.build()
        self.assertEqual("blocked", result["status"])
        plan_record = next(r for r in result["records"] if r["path"] == PLAN)
        self.assertEqual("blocked", plan_record["status"])
        self.assertFalse(plan_record["schema_validated"])

    def test_real_pending_locations_block_with_resume_ref(self):
        self.repo.seed_authorities()
        self.repo.write("logs/ci/b-route-operations/operations/abc/operation.json",
                        {"operation_id": "op-1", "status": "prepared", "resume_ref": "resume:op-1"})
        self.repo.write("logs/ci/b-route-operations/operations/abc/commit.json",
                        {"operation_id": "op-1", "status": "committed"})
        self.repo.write("docs/planning/b-route/capability-apply.pending.json",
                        {"run_id": "r1", "journal_path": "logs/ci/capability-planning/r1/apply-journal.json"})
        self.repo.write("logs/ci/mvg-planning/run-1/apply-journal.json", {"status": "applying"})
        self.repo.write("logs/ci/mvg-planning/run-2/apply-journal.json", {"status": "completed"})
        self.repo.write("logs/ci/b-route-stage5-obligations/op-9/public-sync.pending.json", {"operation_id": "op-9"})
        self.repo.write("logs/ci/b-route-operations/broken.json", b"{")
        result = self.build()
        self.assertEqual("blocked", result["status"])
        by_path = {p["path"]: p for p in result["pending_operations"]}
        self.assertEqual({"logs/ci/b-route-operations/operations/abc/operation.json",
                          "docs/planning/b-route/capability-apply.pending.json",
                          "logs/ci/mvg-planning/run-1/apply-journal.json",
                          "logs/ci/b-route-stage5-obligations/op-9/public-sync.pending.json",
                          "logs/ci/b-route-operations/broken.json"}, set(by_path))
        for entry in by_path.values():
            self.assert_six_field(entry["diagnostic"])
        self.assertEqual("resume:op-1",
                         by_path["logs/ci/b-route-operations/operations/abc/operation.json"]["diagnostic"]["resume_ref"])
        self.assertEqual("logs/ci/capability-planning/r1/apply-journal.json",
                         by_path["docs/planning/b-route/capability-apply.pending.json"]["resume_ref"])
        self.assertEqual("damaged", by_path["logs/ci/b-route-operations/broken.json"]["pending_status"])

    def _job(self, job_id: str, epoch: int, transaction: str | None = None, pointer: bool = True):
        self.repo.write(f"logs/ci/knowledge-planning/{job_id}/job.json",
                        {"job_id": job_id, "action": "mvg", "status": "paused", "mvg_epoch": epoch})
        if pointer:
            self.repo.write("logs/ci/knowledge-planning/mvg-attempt.json", {"job_id": job_id})
        if transaction:
            self.repo.write(f"logs/ci/mvg-planning/{job_id}/run.json", {
                "recovery": {"epoch": epoch},
                "capability_selection": {"selected": [{"checkpoint": {"transaction_id": transaction}}]}})

    def test_mvg_clear_epoch_revokes_local_jobs_but_preserves_formal_adoption_and_audit(self):
        from _mvg_capability_recovery import clear
        self.repo.seed_authorities()
        self.repo.seed_b_route()
        job_id = "planning-" + "a" * 32
        self._job(job_id, 0, "tx-0")
        before_active = self.build()
        self.assertEqual("active", before_active["local_recovery_status"]["jobs"][0]["local_status"])
        formal = self.repo.digest_tree("docs/planning/b-route/", "docs/testing/mvg/")
        clear(self.root)
        result = self.build()
        job = result["local_recovery_status"]["jobs"][0]
        self.assertEqual("revoked", job["local_status"])
        self.assertFalse(job["recoverable"])
        self.assertIn("epoch_invalidated", job["reasons"])
        self.assert_six_field(job["diagnostic"])
        self.assertEqual(formal, self.repo.digest_tree("docs/planning/b-route/", "docs/testing/mvg/"))
        boundary = result["local_clear_boundary"]
        self.assertEqual("valid", boundary["formal_git_adoptions"]["status"])
        self.assertTrue(boundary["formal_adoptions_independent_of_local_epoch"])
        self.assertEqual(["epoch-0.json"], [c["path"] for c in boundary["clear_audit_trail"]])
        self.assertTrue(result["ok"], result["issues"])
        self.assertEqual("3b_adopted_awaiting_3c", self.node(result, "flows", "flow-b")["planning_state"])

    def test_revoked_transaction_never_resurrects_even_without_pointer(self):
        self.repo.seed_authorities()
        self.repo.write("logs/ci/mvg-recovery/registry.json", {
            "schema_version": "newrouge.mvg-completed-registry.v1", "epoch": 0, "entries": [], "revoked": ["tx-9"]})
        self._job("planning-" + "b" * 32, 0, "tx-9", pointer=False)
        job = self.build()["local_recovery_status"]["jobs"][0]
        self.assertEqual("revoked", job["local_status"])
        self.assertIn("transaction_revoked", job["reasons"])

    def test_corrupt_or_invalid_recovery_registry_and_clear_block(self):
        cases = {
            "invalid_json": ("logs/ci/mvg-recovery/registry.json", b"{"),
            "schema_validation_failed": ("logs/ci/mvg-recovery/registry.json",
                                         encoded({"schema_version": "newrouge.mvg-completed-registry.v1",
                                                  "epoch": True, "entries": [], "revoked": []})),
            "duplicate_key": ("logs/ci/mvg-recovery/clears/epoch-0.json", b'{"epoch": 0, "epoch": 1}'),
        }
        for code, (rel, raw) in cases.items():
            with self.subTest(code=code):
                shutil.rmtree(self.root / "logs", ignore_errors=True)
                self.repo.seed_authorities()
                self.repo.write(rel, raw)
                result = self.build()
                self.assertFalse(result["ok"])
                self.assertEqual("blocked", result["local_recovery_status"]["status"])
                self.assertIn(code, self.codes(result))
                self.assert_six_field(result["local_recovery_status"]["diagnostic"])

    def test_registry_entries_without_full_apply_are_partial(self):
        self.repo.seed_authorities()
        self.repo.write("logs/ci/mvg-recovery/registry.json", {
            "schema_version": "newrouge.mvg-completed-registry.v1", "epoch": 0,
            "entries": [{"transaction_id": "tx-1"}], "revoked": []})
        result = self.build()
        self.assertEqual("partial_planning", result["status"])
        self.assertFalse(result["planning_complete"])

    def test_chapter6_reopen_revokes_task_qualification_without_filter(self):
        self.repo.seed_authorities()
        self.repo.write("logs/ci/b-route-reopen/2026-11-26/task-1.json",
                        {"status": "reopened", "task_id": 1, "resume_ref": "resume-task:1"})
        result = self.build()
        task = self.node(result, "tasks", "1")
        self.assertEqual("revoked", task["local_qualification"])
        self.assertEqual("revoked", task["planning_state"])
        self.assert_six_field(task["diagnostics"][0])
        self.assertFalse(result["ok"])
        self.assertEqual("revoked", result["status"])
        targeted = self.build(task_id="1")
        self.assertFalse(targeted["ok"])
        self.assertEqual("revoked", self.node(targeted, "tasks", "1")["planning_state"])
        other = self.build(task_id="2")
        self.assertTrue(other["ok"], other["issues"])

    def test_plan_and_scope_reopen_revokes_without_task_filter(self):
        self.repo.seed_authorities()
        self.repo.seed_b_route()
        self.repo.write("logs/ci/b-route-reopen/plan-p.json",
                        {"status": "reopened", "plan_id": "p", "resume_ref": "resume:p"})
        result = self.build()
        self.assertFalse(result["ok"])
        self.assertEqual("revoked", self.node(result, "flows", "flow-b")["planning_state"])
        self.assertEqual("revoked", self.node(result, "requirements", "REQ-B1")["planning_state"])
        self.assertEqual("revoked", result["catalog"]["scopes"][0]["status"])
        revoked = [i for i in result["issues"] if i["status"] == "revoked"]
        self.assertEqual("conflict", revoked[0]["diagnostic"]["reason_code"])
        self.assertEqual("resume:p", revoked[0]["diagnostic"]["resume_ref"])
        (self.root / "logs/ci/b-route-reopen/plan-p.json").unlink()
        self.repo.write("logs/ci/b-route-reopen/e/scope.json", {"epoch_revoked": True, "scope_ids": ["scope-1"]})
        epoch = self.build()
        self.assertFalse(epoch["ok"])
        self.assertEqual("revoked", self.node(epoch, "flows", "flow-b")["planning_state"])
        self.assertIn("input_stale", {i["diagnostic"]["reason_code"] for i in epoch["issues"] if i["status"] == "revoked"})

    def test_durable_chapter6_stop_loss_revokes_local_task_qualification(self):
        self.repo.seed_authorities()

        def scan(root, task_id, **kwargs):
            return {"has_active_stop_loss": str(task_id) == "1", "blocked_by": "sc_test_retry_stop_loss",
                    "blocking_reason": "repeated", "blocking_run_dir": "logs/ci/2026-11-25/sc-review-pipeline-task-1"}

        with patch("_b_route_chapter6_recovery.scan_durable_recovery_signals", side_effect=scan):
            result = self.build(task_id="1")
        task = self.node(result, "tasks", "1")
        self.assertEqual("revoked", task["local_qualification"])
        self.assertFalse(result["ok"])
        self.assertIn("1", result["chapter6_reopen"]["durable_stop_loss"])
        self.assertEqual("logs/ci/2026-11-25/sc-review-pipeline-task-1", task["diagnostics"][0]["resume_ref"])

    def test_http_clear_reports_formal_adoptions_preserved(self):
        from _project_health_planning_http import _formal_adoption_digests, clear_mvg
        self.repo.seed_authorities()
        self.repo.seed_b_route()
        self.assertIn(COMMIT, _formal_adoption_digests(self.root))

        class Handler:
            def send(self, data, code=200):
                self.data, self.code = data, code

        handler = Handler()
        clear_mvg(handler, self.root, {}, threading.Lock())
        self.assertEqual(200, handler.code)
        self.assertEqual(1, handler.data["epoch"])
        self.assertEqual(0, handler.data["completed"])
        self.assertFalse(handler.data["runtime_verified"])
        self.assertTrue(handler.data["formal_git_adoptions_preserved"])

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
    def test_symlinked_inputs_are_rejected_with_blocking_diagnostic(self):
        self.repo.seed_authorities()
        target = Path(self.temp.name) / "outside"
        target.mkdir()
        (target / "operation.json").write_text(json.dumps({"status": "committed"}))
        link = self.root / "logs/ci/b-route-operations/operations"
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(target, link, target_is_directory=True)
        except OSError:
            _junction_or_skip(self, target, link)
        result = self.build()
        self.assertFalse(result["ok"])
        unsafe = [i for i in result["issues"] if i["diagnostic"]["reason_code"] == "unsafe_path"]
        self.assertTrue(unsafe)
        self.assert_six_field(unsafe[0]["diagnostic"])
        self.assertEqual("path", unsafe[0]["diagnostic"]["stage"])


class ConsumerBoundaryTests(ProjectionTestBase):
    """AC-5: no implicit refresh, logs isolation, legacy fallback, CLI/HTTP parity."""

    def test_legacy_fallback_and_knowledge_boundary(self):
        result = self.build()
        self.assertEqual("legacy_unmapped", result["status"])
        self.assertTrue(result["ok"])
        self.assertFalse(result["planning_complete"])
        self.repo.write("knowledge/policies/source-exclusions.v1.json",
                        (ROOT / "knowledge/policies/source-exclusions.v1.json").read_bytes())
        boundary = self.build()["knowledge_boundary"]
        self.assertTrue(boundary["logs_excluded_from_global_search"])
        self.assertEqual(["chapter3", "chapter5"], boundary["registered_closure_sources"])
        self.assertEqual(["attempt", "stable", "stabilized"], boundary["workspace_views"])
        self.assertTrue(boundary["canonical_requires_trusted_ref"])
        self.assertFalse(boundary["implicit_global_refresh_performed"])

    def test_projection_and_ordinary_consumers_never_refresh_or_publish(self):
        self.repo.seed_authorities()
        with patch("publish_knowledge_catalog.publish") as publish, \
                patch("project_health_knowledge.scan") as scan:
            self.build()
            self.build(mode="main")
        publish.assert_not_called()
        scan.assert_not_called()
        for rel in ("scripts/python/_b_route_knowledge_projection.py", "scripts/python/_b_route_chapter6_gate.py",
                    "scripts/python/_b_route_chapter6_recovery.py", "scripts/python/query_b_route_knowledge_projection.py"):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertNotIn("import publish_knowledge_catalog", text, rel)
            self.assertNotIn("from publish_knowledge_catalog", text, rel)
            self.assertNotIn("refresh_chapter_knowledge(", text, rel)
        import refresh_chapter_knowledge
        self.assertEqual({"chapter3", "chapter5"}, set(refresh_chapter_knowledge.REGISTERED_SOURCES))
        policy = json.loads((ROOT / "knowledge/policies/source-exclusions.v1.json").read_text(encoding="utf-8"))
        prefixes = {rule.get("path_prefix") for rule in policy["rules"] if rule.get("disposition") == "excluded"}
        self.assertTrue({"logs", "backup", "docs/migration"} <= prefixes)

    def test_knowledge_status_and_topology_are_additive_and_read_only(self):
        import project_health_knowledge as knowledge
        from _semantic_topology import load_workspace_topology
        self.repo.seed_authorities()
        self.repo.seed_b_route()
        identity = knowledge.status(self.root, {"tasks": []})["b_route_identity"]
        self.assertTrue(identity["b_route_projection_available"])
        self.assertFalse(identity["implicit_global_refresh_performed"])
        self.assertFalse(identity["provenance"]["is_main_fact"])
        self.assertFalse((self.root / "logs/ci/project-health-knowledge/latest.json").exists())
        self.repo.write("logs/ci/project-health-knowledge/topology/workspace-last-attempt.json", {
            "identity": {"kind": "workspace", "revision": "run:a"}, "available": True,
            "nodes": {}, "edges": [], "problems": []})
        view = load_workspace_topology(self.root, "attempt")
        self.assertEqual({"workspace_view": "attempt", "is_main_fact": False, "can_advance_canonical": False,
                          "trusted_ref_eligible": False}, view["provenance_binding"])
        self.assertEqual("run:a", view["identity"]["revision"])

    def test_mvg_overview_requires_sealed_cumulative_receipt(self):
        from _project_health_mvg_versions import with_runtime_evidence
        self.repo.seed_authorities()
        overview = {"revision": "c" * 40, "manifests": [{"path": MANIFEST, "coverage": {"mode": "full"},
                                                         "sha256": sha((self.root / MANIFEST).read_bytes())}]}

        def evidence():
            return with_runtime_evidence(overview, self.root)["manifests"][0]["evidence"]

        self.write_run("run-3", "c" * 40)
        passed = evidence()
        self.assertEqual("passed", passed["status"])
        self.assertEqual("2026-01-02T03:04:05+00:00", passed["original_executed_at"])
        self.assertEqual(["real_engine_input", "unit_deterministic"], passed["evidence_levels"])
        self.write_run("run-3", "c" * 40, fixture=True)
        fixture = evidence()
        self.assertEqual("failed", fixture["status"])
        self.assertTrue(fixture["protocol_fixture_only"])
        self.write_run("run-3", "c" * 40, scope="scoped", tests=("t-unit",))
        self.assertEqual("partial", evidence()["status"])
        self.write_run("run-3", "c" * 40, tamper=True, scope="scoped", tests=("t-unit",))
        tampered = evidence()
        self.assertEqual("failed", tampered["status"])
        self.assertFalse(tampered["coverage_receipt_valid"])
        self.write_run("run-3", "c" * 40, workspace_dirty=True)
        self.assertNotEqual("passed", evidence()["status"])

    def test_cli_and_dev_cli_parity_reject_writes_and_confine_reports(self):
        self.repo.seed_authorities()
        direct = self.build(mode="workspace_preview")
        proc = subprocess.run([PYTHON, "-B", str(ROOT / "scripts/python/dev_cli.py"), "b-route-knowledge-projection",
                               "--root", str(self.root), "--mode", "workspace_preview"],
                              capture_output=True, text=True, encoding="utf-8", timeout=300,
                              env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(0, proc.returncode, proc.stderr[-2000:])
        payload = json.loads(proc.stdout)
        self.assertEqual(direct["status"], payload["status"])
        self.assertEqual(direct["summary"], payload["summary"])
        for argv in (["--apply"], ["--write"], ["--mode", "bogus"], ["--report", "docs/report.json"],
                     ["--report", "logs/ci/mvg-recovery/registry.json"],
                     ["--report", "logs/ci/project-health-knowledge/runtime/x.json"],
                     ["--report", "logs/ci/mvg-acceptance/run/summary.json"]):
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = cli.main(["--root", str(self.root), "--mode", "workspace_preview", *argv]
                                if argv[0] != "--mode" else ["--root", str(self.root), *argv])
            self.assertEqual(2, code, argv)
            self.assert_six_field(json.loads(buffer.getvalue())["diagnostics"][0])
        self.assertFalse((self.root / "logs/ci/mvg-recovery/registry.json").exists())
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = cli.main(["--root", str(self.root), "--mode", "workspace_preview",
                             "--report", "logs/ci/projection/report.json"])
        self.assertEqual(0, code)
        self.assertTrue((self.root / "logs/ci/projection/report.json").is_file())
        self.repo.write(CATALOG, b"{broken")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(2, cli.main(["--root", str(self.root), "--mode", "workspace_preview"]))
        help_proc = subprocess.run([PYTHON, "-B", str(ROOT / "scripts/python/dev_cli.py"),
                                    "b-route-knowledge-projection", "--help"], capture_output=True, text=True,
                                   encoding="utf-8", timeout=120)
        self.assertEqual(0, help_proc.returncode)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink support required")
    def test_report_symlink_target_is_rejected(self):
        self.repo.seed_authorities()
        outside = Path(self.temp.name) / "outside.json"
        outside.write_text("{}")
        link = self.root / "logs/ci/projection/report.json.tmp"
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(outside, link)
        except OSError:
            outside_dir = Path(self.temp.name) / "outside_dir"
            outside_dir.mkdir()
            _junction_or_skip(self, outside_dir, link)
        with self.assertRaises(projection.codec.CodecError) as ctx:
            projection.write_projection_report(self.root, "logs/ci/projection/report.json", {"ok": True})
        self.assertEqual("unsafe_path", ctx.exception.diagnostic.reason_code.value)
        self.assertEqual("{}", outside.read_text())

    def test_http_endpoint_modes_strict_and_invalid_parameters(self):
        from _project_health_http import handler_factory
        self.repo.seed_authorities()
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler_factory(self.root))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()

        def get(path):
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=60)
            connection.request("GET", path)
            response = connection.getresponse()
            code, raw = response.status, response.read()
            connection.close()
            return code, json.loads(raw)

        base = "/api/knowledge/b-route-projection"
        try:
            code, payload = get(base + "?mode=workspace_preview")
            self.assertEqual(200, code)
            self.assertEqual(projection.SCHEMA_VERSION, payload["schema_version"])
            self.assertEqual(self.build()["summary"], payload["summary"])
            self.assertEqual(400, get(base + "?mode=bogus")[0])
            self.assertEqual(400, get(base + "?mode=")[0])
            self.assertEqual(400, get(base + "?mode=main&mode=workspace_preview")[0])
            for query in ("mode=main&task_id=..%2F1", "mode=main&task_id=", "mode=main&flow_id=",
                          "mode=main&foo=1", "mode=main&task_id=1&task_id=2", "mode=main&strict=yes",
                          "mode=main&strict="):
                with self.subTest(query=query):
                    code, payload = get(base + "?" + query)
                    self.assertEqual(422, code)
                    self.assert_six_field(payload["diagnostics"][0])
            self.repo.write(CATALOG, b"{broken")
            code, payload = get(base + "?mode=workspace_preview")
            self.assertEqual(200, code)
            self.assertEqual("blocked", payload["status"])
            self.assertEqual(422, get(base + "?mode=workspace_preview&strict=1")[0])
            self.assertEqual(200, get(base + "?mode=workspace_preview&strict=false")[0])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == "__main__":
    unittest.main()
