"""Story 4.2 executable three-tier VerificationScope tests (AC-1..AC-5)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_PY = ROOT / "scripts" / "python"
TESTS_DIR = SCRIPTS_PY / "tests"
for _entry in (SCRIPTS_PY, TESTS_DIR):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

import _b_route_impact_closure as closure  # noqa: E402
import _b_route_schema_resources as schema_resources  # noqa: E402
import _b_route_verification_scope as vs  # noqa: E402
import dev_cli  # noqa: E402
import dev_cli_builders  # noqa: E402


DIGEST = "sha256:" + "0" * 64
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
CONTRACT = "Game.Core/Contracts/Offers/OfferLockSnapshot.cs"
ADAPTER = "Game.Godot/Scripts/Reward/RewardOfferProvider.cs"
SCENE = "Game.Godot/Scenes/Reward.tscn"
FIXTURE = "Tests.Godot/tests/Integration/Mvg/reward_fixture.gd"
INPUT_TEST = "Tests.Godot/tests/Integration/Mvg/test_reward_input_journey.gd"
CORE_TEST = "Game.Core.Tests/Integration/RewardTests.cs"
MAP_TEST = "Game.Core.Tests/Tasks/Task0060AcceptanceTests.cs"
MAP_SOURCE = "Game.Core/Services/MapNodeRouteOwnershipService.cs"
OV_DOC = "docs/verification/relic-balance.md"
OV_SCRIPT = "scripts/verify/relic_balance_check.py"
CLAIM_DOC = "docs/verification/claim-audit.md"
CATALOG = "docs/planning/b-route/catalog.v1.json"
REWARD_MANIFEST = "docs/testing/mvg/reward.json"
P1_BINDING = "docs/planning/b-route/bindings/P1.stage5.v1.json"
P2_PLAN = "docs/planning/b-route/plans/P2.plan.v1.json"
COMBAT = "combat-reward-return"
RELIC = "relic-synergy-preview"


def _ref(schema: str, path: str, entity: str, revision: int = 1) -> dict:
    return {"path": path, "schema_version": schema, "entity_id": entity, "revision": revision,
            "digest": DIGEST, "verification_mode": "raw", "codec_version": None}


def _plan_ref(pid: str) -> dict:
    return _ref("newrouge.b-route-plan.v1", f"docs/planning/b-route/plans/{pid}.plan.v1.json", pid)


def _binding_ref(pid: str) -> dict:
    return _ref("newrouge.b-route-binding.v1", f"docs/planning/b-route/bindings/{pid}.stage5.v1.json", pid)


def _owned(owner: str, ref: str, *paths: str) -> dict:
    return {"owner": owner, "ref": ref, "files": [{"path": p, "raw_digest": DIGEST} for p in paths]}


def _use(kind: str, definition_id: str, owner: str) -> dict:
    return {"kind": kind, "definition_id": definition_id, "owner_plan_id": owner, "owner_revision": 1}


def _plan_p1() -> dict:
    return {
        "schema_version": "newrouge.b-route-plan.v1", "plan_id": "P1", "revision": 1,
        "requirements": [
            {"requirement_id": "FR-1", "source_block_ids": ["SB-1"], "acceptance_intent": "claim", "non_task_sinks": []},
            {"requirement_id": "FR-2", "source_block_ids": ["SB-2"], "acceptance_intent": "loop", "non_task_sinks": []},
        ],
        "definitions": {
            "flows": [
                {"id": COMBAT, "requirement_ids": ["FR-1"], "source_block_ids": ["SB-1"],
                 "capability_ids": ["cap-reward"], "state_owners": [_use("state", "OfferLock", "P1")],
                 "rule_ids": ["RewardRule"],
                 "human_verification": {"applicability": "applicable",
                                        "checks": ["Reward offer presentation stays stable on re-entry"]}},
                {"id": "reward-loop", "requirement_ids": ["FR-2"], "source_block_ids": ["SB-2"],
                 "capability_ids": ["cap-reward"]},
            ],
            "commands": [{"id": "ClaimReward", "requirement_ids": ["FR-1"], "responsibility": "claim",
                          "uses": [_use("state", "OfferLock", "P1")]}],
            "states": [{"id": "OfferLock", "requirement_ids": ["FR-1"], "responsibility": "lock", "uses": []}],
            "rules": [{"id": "RewardRule", "requirement_ids": ["FR-1"], "responsibility": "rule", "uses": []}],
        },
        "applicability": [{"requirement_id": "FR-1", "disposition": "flow", "rationale": "r",
                           "other_verification_refs": []}],
        "requirement_verification": [{"requirement_id": "FR-1", "disposition": "other_verification",
                                      "verification_ref": CLAIM_DOC,
                                      "rationale": "Claim audit trail review for reward claims"}],
    }


def _plan_p2() -> dict:
    return {
        "schema_version": "newrouge.b-route-plan.v1", "plan_id": "P2", "revision": 3,
        "requirements": [
            {"requirement_id": "FR-10", "source_block_ids": ["SB-10"], "acceptance_intent": "preview", "non_task_sinks": []},
            {"requirement_id": "FR-11", "source_block_ids": ["SB-11"], "acceptance_intent": "balance", "non_task_sinks": []},
            {"requirement_id": "FR-12", "source_block_ids": ["SB-12"], "acceptance_intent": "script", "non_task_sinks": []},
        ],
        "definitions": {
            "flows": [
                {"id": RELIC, "requirement_ids": ["FR-10", "FR-1"], "source_block_ids": ["SB-10"],
                 "capability_ids": ["cap-relic"], "state_owners": [_use("state", "OfferLock", "P1")],
                 "rule_uses": [_use("rule", "RewardRule", "P1")]},
            ],
            "commands": [], "states": [],
        },
        "applicability": [
            {"requirement_id": "FR-10", "disposition": "flow", "rationale": "r", "other_verification_refs": []},
            {"requirement_id": "FR-11", "disposition": "other_verification", "rationale": "Non-flow balance review",
             "other_verification_refs": [_owned("other_verification", OV_DOC, OV_DOC)]},
            {"requirement_id": "FR-12", "disposition": "other_verification",
             "rationale": "Scripted relic balance verification",
             "other_verification_refs": [_owned("other_verification", OV_SCRIPT, OV_SCRIPT)]},
        ],
    }


def _binding(pid: str, revision: int, mappings: list, impls: list, obligations: list, ov: list) -> dict:
    return {
        "schema_version": "newrouge.b-route-binding.v1", "plan_id": pid, "binding_revision": revision,
        "plan_ref": _plan_ref(pid), "stage": "5", "task_mappings": mappings, "parts": [],
        "implementation_objects": impls, "obligations": obligations,
        "manifest_refs": [_owned("manifest", "reward", REWARD_MANIFEST)],
        "other_verification_refs": ov,
    }


def _mapping(tid: int, flows: list, reqs: list, obligations: list) -> dict:
    return {"task_id": tid, "view_refs": [{"view": "gameplay", "business_id": f"G-{tid}"}], "requirement_ids": reqs,
            "flow_ids": flows, "part_kinds": ["domain_rules"], "roles": ["producer"], "obligation_ids": obligations}


def _impl(iid: str, kind: str, availability: str, tasks: list, path: str | None) -> dict:
    return {"id": iid, "kind": kind, "availability": availability, "responsible_task_ids": tasks,
            "expected_type": "T", "lifecycle": "scene", "later_checks": ["type"],
            "target_ref": _owned("implementation_reference", iid, path) if path else None}


def _test(tid: str, kind: str, state: str, path: str, selector: str | None = None) -> dict:
    item = {"id": tid, "kind": kind, "state": state,
            "evidence_level": "domain-integration" if kind == "dotnet" else "engine-input",
            "path": path, "min_tests": 1}
    if selector:
        item["selector"] = selector
    return item


def _reward_manifest() -> dict:
    return {
        "schema_version": "newrouge.mvg-integration.v1", "mvg_id": "reward",
        "coverage": {"excluded_claims": ["Subjective reward presentation quality remains a human check."]},
        "flows": [
            {"id": COMBAT, "task_ids": [84, 114], "capability_refs": ["cap-reward"],
             "source_paths": [FIXTURE, SCENE], "requirement_ids": ["FR-1"],
             "handoffs": [{"producer_task": 84, "consumer_task": 114, "owner_task": 114, "contract_ref": CONTRACT,
                           "behavior": "b", "test_ids": ["reward-core"]}],
             "test_ids": ["reward-core", "reward-input"]},
            {"id": RELIC, "state": "planned", "task_ids": [84, 130],
             "capability_refs": ["cap-relic"], "test_ids": ["relic-preview"]},
        ],
        "tests": [
            _test("reward-core", "dotnet", "implemented", CORE_TEST, "Game.Core.Tests.Integration.RewardTests"),
            _test("reward-input", "gdunit", "implemented", INPUT_TEST),
            _test("relic-preview", "gdunit", "planned", "Tests.Godot/tests/Integration/Mvg/test_relic_preview.gd"),
        ],
    }


def _m1_manifest() -> dict:
    return {
        "schema_version": "newrouge.mvg-integration.v1", "mvg_id": "m1-full",
        "coverage": {"excluded_claims": ["Human gameplay approval remains separate."]},
        "flows": [{"id": "map-node-owned-flow", "task_ids": [7], "source_paths": [MAP_SOURCE], "handoffs": [],
                   "requirement_ids": ["FR-90"], "test_ids": ["map-route-domain"]}],
        "tests": [_test("map-route-domain", "dotnet", "implemented", MAP_TEST,
                        "Game.Core.Tests.Tasks.Task0060AcceptanceTests")],
    }


def _write(base: Path, rel: str, value) -> None:
    target = base.joinpath(*rel.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)
    data = value if isinstance(value, str) else json.dumps(value, indent=2)
    target.write_bytes(data.encode("utf-8"))


def _catalog(plans: list[str], tasks: dict[int, list[str]]) -> dict:
    return {
        "schema_version": "newrouge.b-route-catalog.v1", "catalog_id": "catalog", "revision": len(plans),
        "policy_ref": _ref("newrouge.b-route-policy.v1", "docs/planning/b-route/policy.v1.json", "policy"),
        "origins_ref": _ref("newrouge.b-route-origins.v1", "docs/planning/b-route/task-origins.v1.json", "task-origins"),
        "scope_heads": [{"scope_id": f"scope-{p}", "plan_refs": [_plan_ref(p)], "binding_refs": [_binding_ref(p)],
                         "receipt_ref": _ref("newrouge.b-route-commit.v1", f"docs/planning/b-route/commits/{p}.json", p)}
                        for p in plans],
        "definition_owners": [],
        "task_index": [{"task_id": t, "plan_refs": [_plan_ref(p) for p in ps], "binding_refs": [_binding_ref(p) for p in ps]}
                       for t, ps in sorted(tasks.items())],
    }


def _build_fixture(base: Path) -> None:
    _write(base, CATALOG, _catalog(["P1", "P2"], {84: ["P1", "P2"], 114: ["P1"], 130: ["P2"]}))
    _write(base, "docs/planning/b-route/plans/P1.plan.v1.json", _plan_p1())
    _write(base, P2_PLAN, _plan_p2())
    _write(base, P1_BINDING, _binding(
        "P1", 2,
        [_mapping(84, [COMBAT], ["FR-1"], ["OB-1"]),
         _mapping(114, [COMBAT, "reward-loop"], ["FR-1", "FR-2"], ["OB-1"])],
        [_impl("reward-adapter", "adapter", "existing", [114], ADAPTER),
         _impl("reward-scene", "scene", "existing", [114], SCENE),
         _impl("offer-contract", "command", "existing", [84], CONTRACT)],
        [{"id": "OB-1", "requirement_ids": ["FR-1"], "flow_ids": [COMBAT],
          "test_ids": ["reward-core", "reward-input"], "responsibility": "r", "verification_refs": []}],
        []))
    _write(base, "docs/planning/b-route/bindings/P2.stage5.v1.json", _binding(
        "P2", 4,
        [_mapping(84, [RELIC], ["FR-10", "FR-11"], ["OB-10"]),
         _mapping(130, [RELIC], ["FR-10"], ["OB-10"])],
        [_impl("relic-preview-panel", "scene", "planned", [130], None)],
        [{"id": "OB-10", "requirement_ids": ["FR-10"], "flow_ids": [RELIC],
          "test_ids": ["relic-preview"], "responsibility": "r", "verification_refs": []}],
        [_owned("other_verification", OV_DOC, OV_DOC)]))
    _write(base, "docs/planning/b-route/task-origins.v1.json", {
        "schema_version": "newrouge.b-route-origins.v1", "origins_id": "task-origins", "revision": 1,
        "tasks": [{"task_id": 84, "source_refs": [], "plan_refs": [_plan_ref("P1"), _plan_ref("P2")],
                   "binding_refs": []}], "frozen_legacy_refs": []})
    _write(base, REWARD_MANIFEST, _reward_manifest())
    _write(base, "docs/testing/mvg/m1-full.json", _m1_manifest())
    _write(base, ".taskmaster/tasks/tasks.json", {"master": {"tasks": [
        {"id": 7, "title": "Map", "description": "d", "details": "", "testStrategy": "", "status": "done",
         "dependencies": []},
        {"id": 84, "title": "Offer lock", "description": "d", "details": "", "testStrategy": "",
         "status": "in-progress", "dependencies": []},
        {"id": 114, "title": "Reward scene", "description": "d", "details": "", "testStrategy": "",
         "status": "pending", "dependencies": [84]},
        {"id": 128, "title": "Reward return", "description": "d", "details": "", "testStrategy": "",
         "status": "pending", "dependencies": [114]},
        {"id": 130, "title": "Relic preview", "description": "d", "details": "", "testStrategy": "",
         "status": "pending", "dependencies": [84]},
    ], "metadata": {}}})
    _write(base, ".taskmaster/tasks/tasks_back.json", [
        {"id": "B-84", "taskmaster_id": 84, "status": "in-progress", "contractRefs": [CONTRACT],
         "overlay_refs": [], "test_refs": [CORE_TEST]}])
    _write(base, ".taskmaster/tasks/tasks_gameplay.json", [
        {"id": "G-114", "taskmaster_id": 114, "status": "pending", "contractRefs": [], "overlay_refs": [],
         "test_refs": [INPUT_TEST]}])
    _write(base, CONTRACT, "namespace Game.Core.Contracts.Offers; public sealed record OfferLockSnapshot;\n")
    _write(base, ADAPTER, "public partial class RewardOfferProvider {}\n")
    _write(base, SCENE, "[gd_scene format=3]\n")
    _write(base, FIXTURE, "extends RefCounted\n")
    _write(base, INPUT_TEST, 'extends GdUnitTestSuite\nconst Fixture = preload("res://Tests.Godot/tests/Integration/Mvg/reward_fixture.gd")\n')
    _write(base, CORE_TEST, "public class RewardTests {}\n")
    _write(base, MAP_TEST, "public class Task0060AcceptanceTests {}\n")
    _write(base, MAP_SOURCE, "public sealed class MapNodeRouteOwnershipService {}\n")
    _write(base, OV_DOC, "# Relic balance verification\n")
    _write(base, OV_SCRIPT, "print('relic balance check')\n")
    _write(base, CLAIM_DOC, "# Claim audit\n")
    _write(base, "docs/planning/source-revision.md", "# Source revision descoping relic preview\n")
    _write(base, "logs/reviews/anti-weakening-review.md", "# Anti-weakening review approved\n")
    _write(base, "docs/readme.md", "# Fixture\n")


def _by_id(scope: dict) -> dict[str, dict]:
    return {o["obligation_id"]: o for o in scope["obligations"]}


def _flows(scope: dict) -> dict[str, dict]:
    return {f["flow_id"]: f for f in scope["flow_classifications"]}


def _snapshot(base: Path) -> dict[str, bytes]:
    return {str(p.relative_to(base)): p.read_bytes() for p in sorted(base.rglob("*")) if p.is_file()}


class VerificationScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._template_dir = tempfile.TemporaryDirectory(prefix="br-vscope-template-")
        cls.template = Path(cls._template_dir.name) / "repo"
        cls.template.mkdir()
        _build_fixture(cls.template)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._template_dir.cleanup()

    def setUp(self) -> None:
        self._work = tempfile.TemporaryDirectory(prefix="br-vscope-case-")
        self.root = Path(self._work.name) / "repo"
        shutil.copytree(self.template, self.root)

    def tearDown(self) -> None:
        self._work.cleanup()

    def _edit_json(self, rel: str, mutate) -> None:
        target = self.root.joinpath(*rel.split("/"))
        doc = json.loads(target.read_text(encoding="utf-8"))
        result = mutate(doc)
        _write(self.root, rel, doc if result is None else result)

    def _build(self, **kwargs) -> dict:
        kwargs.setdefault("change_roots", [f"contract:{CONTRACT}"])
        return vs.build_verification_scope(self.root, **kwargs)

    def _ok(self, scope: dict) -> dict:
        self.assertTrue(scope["ok"], scope.get("diagnostics"))
        return scope

    def _blocked(self, scope: dict, code: str) -> None:
        self.assertFalse(scope["ok"], scope.get("scope_status"))
        self.assertEqual(code, scope["reason_code"], scope["diagnostics"])
        self.assertIsNone(scope["scope_id"])

    def test_ac1_scope_contract_binds_identity_input_set_impact_proof_and_resists_old_manifest_cropping(self) -> None:
        proof = closure.compute_impact_closure(self.root, change_roots=[f"contract:{CONTRACT}"])
        self.assertTrue(proof["ok"], proof["diagnostics"])
        scope = self._ok(self._build(change_roots=None, impact_proof=proof, in_scope_flow_ids=[COMBAT]))
        self.assertEqual(vs.SCHEMA, scope["schema_version"])
        self.assertRegex(scope["scope_id"], DIGEST_RE)
        self.assertRegex(scope["input_set_digest"], DIGEST_RE)
        self.assertEqual(proof["impact_proof_id"], scope["impact_binding"]["impact_proof_id"])
        self.assertEqual(proof["impact_input_digest"], scope["impact_binding"]["impact_input_digest"])
        self.assertEqual([{"kind": "contract", "id": CONTRACT}], scope["change_roots"])
        self.assertEqual(["P1", "P2"], [r["entity_id"] for r in scope["authority_refs"]["plan_refs"]])
        self.assertEqual(2, len(scope["authority_refs"]["binding_refs"]))
        baseline = {r["path"] for r in scope["authority_refs"]["cumulative_baseline_refs"]}
        self.assertEqual({REWARD_MANIFEST, "docs/testing/mvg/m1-full.json"}, baseline)
        self.assertIn(COMBAT, scope["delivery_boundary"]["in_scope_flow_ids"])
        self.assertIn("FR-1", scope["delivery_boundary"]["in_scope_requirement_ids"])
        schema_resources.validate(scope, vs.SCHEMA, auxiliary=True)
        self.assertTrue(vs.validate_verification_scope(self.root, scope)["valid"])
        for flag, value in vs.INVARIANT_FLAGS.items():
            self.assertIs(value, scope[flag])
        obligations = _by_id(scope)
        self.assertEqual("existing_required", obligations["test:reward-core"]["tier"])
        self.assertEqual(COMBAT, obligations["test:reward-core"]["flow_ids"][0])
        self.assertEqual("reward", obligations["test:reward-core"]["source_authority"]["manifest_id"])
        self.assertEqual("P1", obligations["test:reward-core"]["source_authority"]["plan_id"])
        self.assertEqual(2, obligations["test:reward-core"]["source_authority"]["binding_revision"])
        self.assertTrue(all(o["claimed_passed"] is False for o in scope["obligations"]))
        fresh = self._ok(self._build(in_scope_flow_ids=[COMBAT]))
        self.assertEqual(scope["scope_id"], fresh["scope_id"])

        # An older, smaller active manifest never crops cumulative baseline obligations.
        old = _reward_manifest()
        old["mvg_id"] = "reward-old"
        old["flows"] = [dict(old["flows"][0], test_ids=["reward-core"], handoffs=[])]
        old["tests"] = [old["tests"][0]]
        _write(self.root, "docs/testing/mvg-history/reward-old.json", old)
        cropped = self._ok(self._build(in_scope_flow_ids=[COMBAT],
                                       manifest_paths=["docs/testing/mvg-history/reward-old.json"]))
        self.assertIn("test:reward-input", _by_id(cropped))
        self.assertEqual("existing_required", _by_id(cropped)["test:reward-input"]["tier"])
        active = {r["path"]: r["roles"] for r in cropped["authority_refs"]["manifest_refs"]}
        self.assertEqual(["active"], active["docs/testing/mvg-history/reward-old.json"])
        self.assertNotEqual(scope["scope_id"], cropped["scope_id"])

        # A plan-filtered proof would crop obligations and is rejected.
        filtered = closure.compute_impact_closure(self.root, change_roots=[f"contract:{CONTRACT}"], plan_ids=["P1"])
        self._blocked(self._build(change_roots=None, impact_proof=filtered), "conflict")
        # Tampered and stale frozen proofs are rejected rather than trusted.
        tampered = json.loads(json.dumps(proof))
        tampered["impacted_flows"] = tampered["impacted_flows"][:1]
        self._blocked(self._build(change_roots=None, impact_proof=tampered), "digest_mismatch")
        _write(self.root, CONTRACT, "namespace Game.Core.Contracts.Offers; public sealed record OfferLockSnapshot(int V);\n")
        self._blocked(self._build(change_roots=None, impact_proof=proof), "input_stale")
        self._blocked(vs.build_verification_scope(self.root), "invalid_argument")
        self._blocked(self._build(impact_proof=proof), "invalid_argument")

        # Task-scoped scopes bind the common InputSet of every in-scope task.
        tasked = self._ok(self._build(in_scope_task_ids=[114]))
        self.assertEqual([114], [t["task_id"] for t in tasked["task_input_set_digests"]])
        self.assertRegex(tasked["task_input_set_digests"][0]["input_set_digest"], DIGEST_RE)
        if not tasked["task_input_set_digests"][0]["valid_input_set"]:
            self.assertIn("task:114", {g["entity"] for g in tasked["blocking_gaps"]})
            self.assertFalse(tasked["scope_closable"])
        self.assertIn("reward-loop", tasked["delivery_boundary"]["in_scope_flow_ids"])

    def test_ac2_three_tier_classification_mixed_tier_flow_and_blocks_reclassifying_failed_flow_to_planned(self) -> None:
        def add_new_test(doc):
            doc["flows"][0]["test_ids"].append("reward-claim-new")
            doc["tests"].append(_test("reward-claim-new", "gdunit", "planned",
                                      "Tests.Godot/tests/Integration/Mvg/test_reward_claim_new.gd"))
        self._edit_json(REWARD_MANIFEST, add_new_test)
        scope = self._ok(self._build(in_scope_flow_ids=[COMBAT]))
        obligations = _by_id(scope)
        core, new, relic = obligations["test:reward-core"], obligations["test:reward-claim-new"], \
            obligations["test:relic-preview"]
        self.assertEqual(("existing_required", "ready_to_execute"), (core["tier"], core["status"]))
        self.assertEqual(("current_new", "pending"), (new["tier"], new["status"]))
        self.assertTrue(new["blocking_current_delivery"])
        self.assertEqual(("out_of_scope_future", "tracked_future"), (relic["tier"], relic["status"]))
        self.assertFalse(relic["blocking_current_delivery"])
        self.assertFalse(relic["immediate_execution_required"])
        self.assertTrue(relic["follow_up_responsibilities"])
        combat = _flows(scope)[COMBAT]
        self.assertTrue(combat["mixed_tiers"])
        self.assertTrue(combat["has_existing_required"] and combat["has_current_new"])
        self.assertTrue(combat["blocking_current_delivery"])
        self.assertEqual("blocked_incomplete_or_broken", scope["scope_status"])
        self.assertFalse(scope["scope_closable"])
        executable = {t["test_id"] for t in scope["execution_plan"]["executable_tests"]}
        self.assertEqual({"reward-core", "reward-input"}, executable)
        self.assertIn("test:reward-claim-new", {p["obligation_id"] for p in scope["execution_plan"]["pending_obligations"]})

        # A broken/missing baseline test stays existing_required and blocks; it is never cropped.
        (self.root / INPUT_TEST).unlink()
        broken = self._ok(self._build(in_scope_flow_ids=[COMBAT]))
        failing = _by_id(broken)["test:reward-input"]
        self.assertEqual(("existing_required", "blocked"), (failing["tier"], failing["status"]))
        self.assertIn(f"test_file:{INPUT_TEST}", failing["missing_targets"])
        self.assertNotIn("reward-input", {t["test_id"] for t in broken["execution_plan"]["executable_tests"]})

        # Reclassifying the failing active Flow or its regression test to planned is rejected.
        candidate = _reward_manifest()
        candidate["mvg_id"] = "reward-next"
        candidate["flows"][0]["state"] = "planned"
        _write(self.root, "docs/testing/mvg-candidates/reward-next.json", candidate)
        self._blocked(self._build(manifest_paths=["docs/testing/mvg-candidates/reward-next.json"]), "conflict")
        downgraded = _reward_manifest()
        downgraded["mvg_id"] = "reward-down"
        downgraded["tests"][1]["state"] = "planned"
        _write(self.root, "docs/testing/mvg-candidates/reward-down.json", downgraded)
        self._blocked(self._build(manifest_paths=["docs/testing/mvg-candidates/reward-down.json"]), "conflict")
        refs = {"source_authority_ref": "docs/planning/source-revision.md",
                "anti_weakening_review_ref": "logs/reviews/anti-weakening-review.md"}
        delta = {"schema_version": vs.DELTA_SCHEMA, "changes": [
            {"action": "reclassify", "flow_id": COMBAT, "target_tier": "planned", "reason": "descoped", **refs}]}
        self._blocked(self._build(in_scope_flow_ids=[COMBAT], scope_delta=delta), "conflict")

        def downgrade_binding(doc):
            tag = "stage5:obl:v1|" + json.dumps({"category": "out_of_scope_future",
                                                 "out_of_scope_future_flow_ids": [COMBAT]})
            doc["obligations"].append({"id": "OB-F", "requirement_ids": ["FR-1"], "flow_ids": [COMBAT],
                                       "test_ids": [], "responsibility": tag, "verification_refs": []})
        self._edit_json(P1_BINDING, downgrade_binding)
        self._blocked(self._build(in_scope_flow_ids=[COMBAT]), "conflict")

    def test_ac3_shared_change_old_flow_a_regression_future_flow_b_transition_into_scope_and_anti_weakening_delta(self) -> None:
        shared = ["state:OfferLock"]
        outside = self._ok(self._build(change_roots=shared, in_scope_flow_ids=[COMBAT]))
        obligations = _by_id(outside)
        self.assertEqual("existing_required", obligations["test:reward-core"]["tier"])
        self.assertEqual("existing_required", obligations["test:reward-input"]["tier"])
        self.assertEqual(("out_of_scope_future", "tracked_future"),
                         (obligations["test:relic-preview"]["tier"], obligations["test:relic-preview"]["status"]))
        self.assertEqual("executable_ready", outside["scope_status"], outside["blocking_gaps"])
        self.assertTrue(outside["scope_closable"])
        self.assertFalse(_flows(outside)[RELIC]["blocking_current_delivery"])
        self.assertNotIn("relic-preview", {t["test_id"] for t in outside["execution_plan"]["executable_tests"]})

        inside = self._ok(self._build(change_roots=shared, in_scope_flow_ids=[COMBAT, RELIC]))
        relic = _by_id(inside)["test:relic-preview"]
        self.assertEqual(("current_new", "pending", True), (relic["tier"], relic["status"],
                                                             relic["blocking_current_delivery"]))
        self.assertEqual("existing_required", _by_id(inside)["test:reward-core"]["tier"])
        self.assertTrue(_flows(inside)[RELIC]["blocking_current_delivery"])
        self.assertEqual("blocked_incomplete_or_broken", inside["scope_status"])
        self.assertNotEqual(outside["scope_id"], inside["scope_id"])

        by_task = self._ok(self._build(change_roots=shared, in_scope_task_ids=[130]))
        task_obligations = _by_id(by_task)
        self.assertEqual("current_new", task_obligations["test:relic-preview"]["tier"])
        panel = task_obligations["implementation_object:P2:relic-preview-panel"]
        self.assertEqual(("current_new", "pending"), (panel["tier"], panel["status"]))
        self.assertFalse(by_task["scope_closable"])

        refs = {"source_authority_ref": "docs/planning/source-revision.md",
                "anti_weakening_review_ref": "logs/reviews/anti-weakening-review.md"}
        scoped = {"change_roots": shared, "in_scope_flow_ids": [COMBAT, RELIC]}
        for reason in ("missing_test", "test_failed", "cannot_launch", "flaky"):
            delta = {"schema_version": vs.DELTA_SCHEMA, "changes": [
                {"action": "retire", "test_id": "relic-preview", "reason": reason, **refs}]}
            self._blocked(self._build(scope_delta=delta, **scoped), "conflict")
        delta = {"schema_version": vs.DELTA_SCHEMA, "changes": [
            {"action": "retire", "test_id": "relic-preview", "reason": "descoped_by_source_revision"}]}
        self._blocked(self._build(scope_delta=delta, **scoped), "conflict")
        delta = {"schema_version": vs.DELTA_SCHEMA, "changes": [
            {"action": "reclassify", "test_id": "reward-core", "target_tier": "out_of_scope_future",
             "reason": "descoped_by_source_revision", **refs}]}
        self._blocked(self._build(scope_delta=delta, **scoped), "conflict")
        self._blocked(self._build(scope_delta={"schema_version": "newrouge.unknown.v0", "changes": []}, **scoped),
                      "unknown_schema")
        delta = {"schema_version": vs.DELTA_SCHEMA, "changes": [
            {"action": "retire", "test_id": "relic-preview", "reason": "descoped_by_source_revision", **refs}]}
        governed = self._ok(self._build(scope_delta=delta, **scoped))
        self.assertNotIn("test:relic-preview", _by_id(governed))
        self.assertEqual(["test:relic-preview"], [c["obligation_id"] for c in governed["applied_delta_changes"]])
        self.assertEqual({"docs/planning/source-revision.md", "logs/reviews/anti-weakening-review.md"},
                         {r["ref"] for r in governed["authority_refs"]["governed_delta_refs"]})
        self.assertEqual("existing_required", _by_id(governed)["test:reward-core"]["tier"])
        self.assertTrue(vs.validate_verification_scope(self.root, governed)["valid"])

    def test_ac4_unknown_conservative_expansion_legal_nonflow_and_separate_executable_pending_manual_buckets(self) -> None:
        unknown = self._ok(self._build(change_roots=["docs/readme.md"]))
        self.assertTrue(unknown["impact_binding"]["conservative_expanded"])
        self.assertTrue(unknown["impact_binding"]["unknown_items"])
        obligations = _by_id(unknown)
        self.assertEqual("existing_required", obligations["test:map-route-domain"]["tier"])
        self.assertEqual("existing_required", obligations["test:reward-core"]["tier"])
        self.assertEqual("out_of_scope_future", obligations["test:relic-preview"]["tier"])
        executable = unknown["execution_plan"]["executable_tests"]
        self.assertNotIn("relic-preview", {t["test_id"] for t in executable})
        for item in executable:
            self.assertTrue((self.root / item["path"]).is_file(), item)
            self.assertIn(item["tier"], ("existing_required", "current_new"))

        pure = self._ok(self._build(change_roots=["requirement:FR-12"]))
        self.assertFalse([o for o in pure["obligations"] if o["obligation_id"].startswith("test:")])
        script = _by_id(pure)["other_verification:P2:FR-12"]
        self.assertEqual(("existing_required", "ready_to_execute", "other_verification"),
                         (script["tier"], script["status"], script["execution_kind"]))
        self.assertEqual([{"kind": "other_verification", "path": OV_SCRIPT}],
                         [{"kind": t["kind"], "path": t["path"]} for t in pure["execution_plan"]["executable_tests"]])

        linked = self._ok(self._build(change_roots=["requirement:FR-1"]))
        self.assertEqual("existing_required", _by_id(linked)["test:reward-core"]["tier"])
        audit = [o for o in linked["execution_plan"]["other_verification_obligations"]
                 if o["obligation_id"] == "other_verification:P1:FR-1"][0]
        self.assertIn(COMBAT, audit["links_mvg_flow_ids"])

        def add_broken_nonflow(doc):
            doc["requirements"] += [
                {"requirement_id": "FR-13", "source_block_ids": ["SB-13"], "acceptance_intent": "m", "non_task_sinks": []},
                {"requirement_id": "FR-14", "source_block_ids": ["SB-14"], "acceptance_intent": "t", "non_task_sinks": []}]
            doc["applicability"] += [
                {"requirement_id": "FR-13", "disposition": "other_verification", "rationale": "Missing scripted check",
                 "other_verification_refs": [_owned("other_verification", "scripts/verify/missing_check.py",
                                                    "scripts/verify/missing_check.py")]},
                {"requirement_id": "FR-14", "disposition": "other_verification", "rationale": "n/a",
                 "other_verification_refs": [_owned("other_verification", OV_DOC, OV_DOC)]}]
        self._edit_json(P2_PLAN, add_broken_nonflow)
        planned = self._ok(self._build(change_roots=[f"contract:{CONTRACT}"], in_scope_plan_ids=["P2"]))
        by_id = _by_id(planned)
        self.assertEqual(("current_new", "blocked"), (by_id["other_verification:P2:FR-13"]["tier"],
                                                      by_id["other_verification:P2:FR-13"]["status"]))
        self.assertEqual("blocked", by_id["other_verification:P2:FR-14"]["status"])
        self.assertIn("substantive_rationale:FR-14", by_id["other_verification:P2:FR-14"]["missing_targets"])
        self.assertEqual("manual_required", by_id["other_verification:P2:FR-11"]["status"])
        self.assertEqual("ready_to_execute", by_id["other_verification:P2:FR-12"]["status"])
        self.assertEqual(("current_new", "pending"), (by_id["test:relic-preview"]["tier"],
                                                      by_id["test:relic-preview"]["status"]))
        plan = planned["execution_plan"]
        executable_ids = {t["obligation_id"] for t in plan["executable_tests"]}
        pending_ids = {p["obligation_id"] for p in plan["pending_obligations"]}
        manual_ids = {m["manual_id"] for m in plan["manual_obligations"]}
        self.assertFalse(executable_ids & pending_ids)
        self.assertIn("other_verification:P2:FR-12", executable_ids)
        self.assertNotIn("missing_check.py", json.dumps(plan["executable_tests"]))
        self.assertTrue({"test:relic-preview", "other_verification:P2:FR-13",
                         "implementation_object:P2:relic-preview-panel"} <= pending_ids)
        self.assertIn("manual:flow:combat-reward-return", manual_ids)
        self.assertIn("manual:manifest:reward:1", manual_ids)
        self.assertIn("other_verification:P2:FR-11", manual_ids)
        self.assertEqual({"other_verification:P2:FR-11", "other_verification:P2:FR-12", "other_verification:P2:FR-13",
                          "other_verification:P2:FR-14"},
                         {o["obligation_id"] for o in plan["other_verification_obligations"]
                          if o["obligation_id"].startswith("other_verification:P2:")})
        self.assertEqual("blocked_incomplete_or_broken", planned["scope_status"])

    def test_ac5_deterministic_scope_id_drift_invalidation_schema_rejection_and_zero_status_mutation(self) -> None:
        before = _snapshot(self.root)
        scoped = {"in_scope_flow_ids": [COMBAT]}
        first = self._ok(self._build(**scoped))
        second = self._ok(self._build(**scoped))
        self.assertEqual(first["scope_id"], second["scope_id"])
        self.assertEqual(before, _snapshot(self.root))

        tampered = json.loads(json.dumps(first))
        tampered["obligations"][0]["missing_targets"].append("forged")
        self.assertEqual("digest_mismatch", vs.validate_verification_scope(self.root, tampered)["reason_code"])
        unknown = dict(first, schema_version="newrouge.b-route-verification-scope.v0")
        self.assertEqual("unknown_schema", vs.validate_verification_scope(self.root, unknown)["reason_code"])
        broken = {k: v for k, v in first.items() if k != "execution_plan"}
        self.assertEqual("schema_validation_failed", vs.validate_verification_scope(self.root, broken)["reason_code"])
        claimed = json.loads(json.dumps(first))
        claimed["obligations"][0]["claimed_passed"] = True
        claimed["scope_id"] = vs.codec.canonical_digest(vs._scope_body(claimed))
        self.assertEqual("schema_validation_failed", vs.validate_verification_scope(self.root, claimed)["reason_code"])

        conclusions = [
            {"conclusion_id": "c-combat", "scope_id": first["scope_id"], "obligation_ids": ["test:reward-core"]},
            {"conclusion_id": "c-relic", "scope_id": first["scope_id"], "obligation_ids": ["test:relic-preview"]},
        ]
        same = vs.revalidate_verification_scope(self.root, first, prior_conclusions=conclusions)
        self.assertTrue(same["valid"] and same["same_scope_id"], same)
        self.assertEqual([], same["invalidated_obligations"])
        self.assertEqual([], same["invalidated_prior_conclusions"])

        def finish_task(doc):
            doc["master"]["tasks"][1]["status"] = "done"
        self._edit_json(".taskmaster/tasks/tasks.json", finish_task)
        _write(self.root, "docs/readme.md", "# Fixture updated by an unrelated commit\n")
        status_only = vs.revalidate_verification_scope(self.root, first, prior_conclusions=conclusions)
        self.assertTrue(status_only["valid"], status_only)
        self.assertEqual([], status_only["invalidated_prior_conclusions"])

        _write(self.root, CONTRACT, "namespace Game.Core.Contracts.Offers; public sealed record OfferLockSnapshot(int V);\n")
        drift = vs.revalidate_verification_scope(self.root, first, prior_conclusions=conclusions)
        self.assertTrue(drift["ok"], drift)
        self.assertFalse(drift["valid"])
        self.assertTrue(drift["stale"])
        self.assertNotEqual(first["scope_id"], drift["replacement_scope_id"])
        self.assertIn("test:reward-core", drift["invalidated_obligations"])
        self.assertNotIn("test:relic-preview", drift["invalidated_obligations"])
        self.assertIn(COMBAT, drift["invalidated_flows"])
        self.assertEqual(["c-combat"], drift["invalidated_prior_conclusions"])
        self.assertEqual(["c-relic"], drift["retained_prior_conclusions"])
        self.assertTrue(vs.validate_verification_scope(self.root, drift["replacement_scope"])["valid"])
        for flag, value in vs.INVARIANT_FLAGS.items():
            self.assertIs(value, drift[flag])
        tasks_doc = json.loads((self.root / ".taskmaster/tasks/tasks.json").read_text(encoding="utf-8"))
        self.assertEqual("done", tasks_doc["master"]["tasks"][1]["status"])
        self.assertEqual("pending", tasks_doc["master"]["tasks"][2]["status"])

        cli = [sys.executable, "-B", str(SCRIPTS_PY / "dev_cli.py"), "b-route-verification-scope", "--root", str(self.root)]
        report = "logs/ci/vscope/scope.json"
        proc = subprocess.run(cli + ["--change-root", f"contract:{CONTRACT}", "--flow-id", COMBAT, "--flow-id", RELIC,
                                     "--report", report, "--events-log", "logs/ci/vscope/events.jsonl"],
                              capture_output=True, text=True, timeout=300)
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["scope_closable"])
        self.assertEqual(report, payload["report_path"])
        self.assertTrue((self.root / "logs/ci/vscope/events.jsonl").is_file())
        proc = subprocess.run(cli + ["--validate-scope", report], capture_output=True, text=True, timeout=300)
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        proc = subprocess.run(cli + ["--change-root", f"contract:{CONTRACT}", "--report", report],
                              capture_output=True, text=True, timeout=300)
        self.assertEqual(1, proc.returncode, proc.stdout)
        self.assertEqual("conflict", json.loads(proc.stdout)["reason_code"])
        proc = subprocess.run(cli + ["--change-root", f"contract:{CONTRACT}", "--apply"],
                              capture_output=True, text=True, timeout=300)
        self.assertEqual(2, proc.returncode, proc.stdout)
        stored = json.loads((self.root / report).read_text(encoding="utf-8"))
        stored["scope_status"] = "executable_ready"
        _write(self.root, "logs/ci/vscope/forged.json", stored)
        proc = subprocess.run(cli + ["--validate-scope", "logs/ci/vscope/forged.json"],
                              capture_output=True, text=True, timeout=300)
        self.assertEqual(1, proc.returncode, proc.stdout)
        args = dev_cli.build_parser().parse_args(["b-route-verification-scope", "--root", str(self.root),
                                                  "--change-root", f"contract:{CONTRACT}"])
        self.assertIn("--change-root", dev_cli_builders.build_b_route_verification_scope_cmd(args))
        args.apply = True
        with self.assertRaises(ValueError):
            dev_cli_builders.build_b_route_verification_scope_cmd(args)
        proc = subprocess.run([sys.executable, "-B", str(SCRIPTS_PY / "dev_cli.py"), "b-route-verification-scope",
                               "--help"], capture_output=True, text=True, timeout=120)
        self.assertEqual(0, proc.returncode)
        self.assertIn("--revalidate-scope", proc.stdout)
        self.assertIn("verification-scope", schema_resources.AUXILIARY)
        self.assertEqual(("common", "policy", "plan", "binding", "origins", "commit", "catalog"), schema_resources.FORMAL)

    # ------------------------------------------------------------------
    # Step 4 fix-through regressions (P-01..P-06)
    # ------------------------------------------------------------------

    def test_ac1_m1_full_cropping_defense_impact_proof_manifest_parity_and_catalog_gaps(self) -> None:
        cropped = _m1_manifest()
        cropped["flows"][0]["test_ids"] = []
        _write(self.root, "docs/testing/mvg-history/m1-cropped.json", cropped)
        scope = self._ok(self._build(change_roots=[MAP_SOURCE],
                                     manifest_paths=["docs/testing/mvg-history/m1-cropped.json"]))
        regression = _by_id(scope)["test:map-route-domain"]
        self.assertEqual(("existing_required", "blocked"), (regression["tier"], regression["status"]))
        self.assertIn("test:map-route-domain", {g["entity"] for g in scope["blocking_gaps"]})
        self.assertFalse(scope["scope_closable"])
        self.assertNotIn("map-route-domain", {t["test_id"] for t in scope["execution_plan"]["executable_tests"]})

        extra = "docs/testing/mvg-history/reward-old.json"
        old = _reward_manifest()
        old["mvg_id"] = "reward-old"
        _write(self.root, extra, old)
        proof = closure.compute_impact_closure(self.root, change_roots=[f"contract:{CONTRACT}"], manifest_paths=[extra])
        self.assertTrue(proof["ok"], proof["diagnostics"])
        via_roots = self._ok(self._build(manifest_paths=[extra], in_scope_flow_ids=[COMBAT]))
        via_proof = self._ok(self._build(change_roots=None, impact_proof=proof, manifest_paths=[extra],
                                         in_scope_flow_ids=[COMBAT]))
        proof_only = self._ok(self._build(change_roots=None, impact_proof=proof, in_scope_flow_ids=[COMBAT]))
        _write(self.root, "logs/ci/vscope/proof.json", proof)
        via_file = self._ok(self._build(change_roots=None, impact_proof="logs/ci/vscope/proof.json",
                                        in_scope_flow_ids=[COMBAT]))
        self.assertEqual({via_roots["scope_id"]}, {via_proof["scope_id"], proof_only["scope_id"], via_file["scope_id"]})
        bare = closure.compute_impact_closure(self.root, change_roots=[f"contract:{CONTRACT}"])
        self._blocked(self._build(change_roots=None, impact_proof=bare, manifest_paths=[extra]), "input_stale")

        def rename(doc):
            doc["plan_id"] = "PX"
        self._edit_json(P2_PLAN, rename)
        mismatch = self._ok(self._build())
        self.assertIn({"entity": "plan:P2", "reason": "plan_identity_mismatch"}, mismatch["blocking_gaps"])
        (self.root / CATALOG).unlink()
        missing = self._ok(self._build())
        self.assertIn({"entity": f"catalog:{CATALOG}", "reason": "catalog_missing"}, missing["blocking_gaps"])
        self.assertFalse(missing["scope_closable"])

    def test_ac2_in_place_planned_edit_of_active_manifest_flow_is_rejected(self) -> None:
        def mark_state(doc):
            doc["flows"][0]["state"] = "planned"
        self._edit_json(REWARD_MANIFEST, mark_state)
        self._blocked(self._build(in_scope_flow_ids=[COMBAT]), "conflict")
        self._edit_json(REWARD_MANIFEST, lambda doc: doc["flows"][0].update(state="future"))
        self._blocked(self._build(in_scope_flow_ids=[COMBAT]), "conflict")
        self._edit_json(REWARD_MANIFEST, lambda doc: doc["flows"][0].pop("state") and None)
        self._ok(self._build(in_scope_flow_ids=[COMBAT]))

        self._edit_json("docs/testing/mvg/m1-full.json", lambda doc: doc["flows"][0].update(status="planned"))
        self._blocked(self._build(change_roots=[MAP_SOURCE]), "conflict")
        self._edit_json("docs/testing/mvg/m1-full.json", lambda doc: doc["flows"][0].pop("status") and None)

        def existing_on_planned(doc):
            tag = "stage5:obl:v1|" + json.dumps({"category": "existing_required"})
            doc["obligations"].append({"id": "OB-E", "requirement_ids": ["FR-10"], "flow_ids": [RELIC],
                                       "test_ids": [], "responsibility": tag, "verification_refs": []})
        self._edit_json("docs/planning/b-route/bindings/P2.stage5.v1.json", existing_on_planned)
        self._blocked(self._build(in_scope_flow_ids=[COMBAT]), "conflict")

    def test_ac3_flow_b_entering_by_flow_id_alone_and_hardened_anti_weakening_delta(self) -> None:
        shared = ["state:OfferLock"]
        flow_only = self._ok(self._build(change_roots=shared, in_scope_flow_ids=[RELIC]))
        obligations = _by_id(flow_only)
        relic = obligations["test:relic-preview"]
        self.assertEqual(("current_new", "pending", True), (relic["tier"], relic["status"],
                                                             relic["blocking_current_delivery"]))
        panel = obligations["implementation_object:P2:relic-preview-panel"]
        self.assertEqual(("current_new", "pending"), (panel["tier"], panel["status"]))
        self.assertIn("FR-10", panel["requirement_ids"])
        self.assertTrue(_flows(flow_only)[RELIC]["blocking_current_delivery"])
        self.assertFalse(flow_only["scope_closable"])
        self.assertEqual("existing_required", obligations["test:reward-core"]["tier"])

        refs = {"source_authority_ref": "docs/planning/source-revision.md",
                "anti_weakening_review_ref": "logs/reviews/anti-weakening-review.md"}
        scoped = {"change_roots": shared, "in_scope_flow_ids": [COMBAT, RELIC]}

        def delta(**override) -> dict:
            change = {"action": "retire", "test_id": "relic-preview", "reason": "descoped_by_source_revision", **refs}
            change.update(override)
            return {"schema_version": vs.DELTA_SCHEMA, "changes": [change]}

        for bad in ({"source_authority_ref": "docs/planning/missing-authority.md"},
                    {"anti_weakening_review_ref": "logs/reviews/missing-review.md"},
                    {"source_authority_ref": "logs/reviews/anti-weakening-review.md"},
                    {"anti_weakening_review_ref": "docs/planning/source-revision.md"},
                    {"reason": "test failed in CI"}, {"reason": "cannot launch godot"}, {"reason": "n/a"},
                    {"reason": "Flaky on the Windows runner"}, {"reason": "skipped until the scene exists"},
                    {"reason": "missing tests for relic preview"},
                    {"action": "remove", "test_id": "reward-core"}, {"action": "shrink", "test_id": "reward-core"}):
            with self.subTest(bad=bad):
                self._blocked(self._build(scope_delta=delta(**bad), **scoped), "conflict")
        delta_rel = "docs/planning/scope-delta.json"
        _write(self.root, delta_rel, delta(source_authority_ref=delta_rel))
        self._blocked(self._build(scope_delta=delta_rel, **scoped), "conflict")
        _write(self.root, "docs/planning/empty-authority.md", "   \n")
        self._blocked(self._build(scope_delta=delta(source_authority_ref="docs/planning/empty-authority.md"), **scoped),
                      "conflict")
        governed = self._ok(self._build(scope_delta=delta(), **scoped))
        self.assertNotIn("test:relic-preview", _by_id(governed))
        retired = self._ok(self._build(scope_delta=delta(test_id="reward-core"), **scoped))
        self.assertNotIn("test:reward-core", _by_id(retired))
        self.assertEqual(["existing_required"], [c["tier"] for c in retired["applied_delta_changes"]])
        self.assertTrue(vs.validate_verification_scope(self.root, retired)["valid"])

    def test_ac4_nonflow_links_mvg_tests_multi_script_other_verification_and_binding_manual_checks(self) -> None:
        linked = self._ok(self._build(change_roots=["requirement:FR-1"]))
        audit = [o for o in linked["execution_plan"]["other_verification_obligations"]
                 if o["obligation_id"] == "other_verification:P1:FR-1"][0]
        self.assertIn(COMBAT, audit["links_mvg_flow_ids"])
        self.assertNotIn("reward-loop", audit["links_mvg_flow_ids"])
        self.assertTrue({"reward-core", "reward-input"}
                        <= {t["test_id"] for t in linked["execution_plan"]["executable_tests"]})

        second = "scripts/verify/relic_balance_second.py"
        _write(self.root, second, "print('second relic balance check')\n")

        def multi(doc):
            doc["applicability"][2]["other_verification_refs"].append(_owned("other_verification", second, second))
        self._edit_json(P2_PLAN, multi)
        pure = self._ok(self._build(change_roots=["requirement:FR-12"]))
        entry = [o for o in pure["execution_plan"]["other_verification_obligations"]
                 if o["obligation_id"] == "other_verification:P2:FR-12"][0]
        self.assertEqual(sorted([OV_SCRIPT, second]), entry["verification_paths"])
        self.assertEqual({OV_SCRIPT, second}, {t["path"] for t in pure["execution_plan"]["executable_tests"]
                                               if t["obligation_id"] == "other_verification:P2:FR-12"})
        self.assertTrue(vs.validate_verification_scope(self.root, pure)["valid"])
        _write(self.root, second, "   \n")
        blank = self._ok(self._build(change_roots=["requirement:FR-12"]))
        self.assertIn(f"verification_file:{second}", _by_id(blank)["other_verification:P2:FR-12"]["missing_targets"])
        self.assertNotIn(second, {t["path"] for t in blank["execution_plan"]["executable_tests"]})

        def human(doc):
            tag = "stage5:obl:v1|" + json.dumps({"category": "current_new",
                                                 "human_verification": ["Reviewer confirms reward pacing"]})
            doc["obligations"].append({"id": "OB-H", "requirement_ids": ["FR-1"], "flow_ids": [COMBAT],
                                       "test_ids": [], "responsibility": tag, "verification_refs": []})
        self._edit_json(P1_BINDING, human)
        manual = self._ok(self._build(in_scope_flow_ids=[COMBAT]))
        items = {m["manual_id"]: m for m in manual["execution_plan"]["manual_obligations"]}
        self.assertEqual(["Reviewer confirms reward pacing"], items["manual:binding:P1:OB-H"]["responsibilities"])

    def test_ac5_semantic_tampering_and_cli_prior_conclusions_drift_invalidation(self) -> None:
        first = self._ok(self._build(in_scope_flow_ids=[COMBAT, RELIC]))
        forged = json.loads(json.dumps(first))
        forged.update(scope_status="executable_ready", scope_closable=True, all_current_obligations_executable=True,
                      blocking_gaps=[])
        forged["scope_id"] = vs.codec.canonical_digest(vs._scope_body(forged))
        self.assertEqual("conflict", vs.validate_verification_scope(self.root, forged)["reason_code"])
        bucket = json.loads(json.dumps(first))
        bucket["execution_plan"]["pending_obligations"] = []
        bucket["scope_id"] = vs.codec.canonical_digest(vs._scope_body(bucket))
        self.assertEqual("schema_validation_failed", vs.validate_verification_scope(self.root, bucket)["reason_code"])
        metrics = json.loads(json.dumps(first))
        metrics["metrics"] = {"claimed_passed": True}
        self.assertEqual("schema_validation_failed", vs.validate_verification_scope(self.root, metrics)["reason_code"])
        digest = json.loads(json.dumps(first))
        digest["impact_binding"]["impact_input_digest"] = DIGEST
        digest["scope_id"] = vs.codec.canonical_digest(vs._scope_body(digest))
        self.assertEqual("digest_mismatch", vs.validate_verification_scope(self.root, digest)["reason_code"])

        cli = [sys.executable, "-B", str(SCRIPTS_PY / "dev_cli.py"), "b-route-verification-scope", "--root", str(self.root)]
        report = "logs/ci/vscope/rule-scope.json"
        proc = subprocess.run(cli + ["--change-root", f"contract:{CONTRACT}", "--flow-id", COMBAT, "--report", report],
                              capture_output=True, text=True, timeout=300)
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        scope_id = json.loads(proc.stdout)["scope_id"]
        prior = "logs/ci/vscope/prior.json"
        _write(self.root, prior, {"prior_conclusions": [
            {"conclusion_id": "c-combat", "scope_id": scope_id, "obligation_ids": ["test:reward-core"]},
            {"conclusion_id": "c-claim", "scope_id": scope_id, "obligation_ids": ["other_verification:P1:FR-1"]},
            {"conclusion_id": "c-any", "scope_id": scope_id}]})
        revalidate = cli + ["--revalidate-scope", report, "--prior-conclusions", prior]
        proc = subprocess.run(revalidate, capture_output=True, text=True, timeout=300)
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertEqual([], json.loads(proc.stdout)["invalidated_prior_conclusions"])

        def drift_rule(doc):
            doc["definitions"]["rules"][0]["responsibility"] = "rule revised by an authoritative source change"
        self._edit_json("docs/planning/b-route/plans/P1.plan.v1.json", drift_rule)
        proc = subprocess.run(revalidate, capture_output=True, text=True, timeout=300)
        self.assertEqual(1, proc.returncode, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["stale"])
        self.assertEqual(["c-any", "c-combat"], sorted(payload["invalidated_prior_conclusions"]))
        self.assertEqual(["c-claim"], payload["retained_prior_conclusions"])
        proc = subprocess.run(cli + ["--validate-scope", report, "--prior-conclusions", prior],
                              capture_output=True, text=True, timeout=300)
        self.assertEqual(2, proc.returncode, proc.stdout)
        args = dev_cli.build_parser().parse_args(["b-route-verification-scope", "--root", str(self.root),
                                                  "--revalidate-scope", report, "--prior-conclusions", prior])
        self.assertIn("--prior-conclusions", dev_cli_builders.build_b_route_verification_scope_cmd(args))


class VerificationScopeStage5InputSetTests(unittest.TestCase):
    """AC5 on a real published Stage-5 fixture whose task InputSet is valid."""

    def test_ac5_valid_stage5_task_input_set_survives_status_only_change_with_identical_scope_id(self) -> None:
        import test_b_route_stage5_obligations as stage5_tests  # noqa: PLC0415 - heavy fixture loaded lazily

        fx = stage5_tests.Stage5RepoFixture()
        self.addCleanup(fx.cleanup)
        helper = stage5_tests.Stage5ObligationsTests()
        helper.fx = fx
        assets = fx.build_committed_stage4(mode="flow", include_other_plan=True)
        request = helper._flow_request("OP-VS-AC5", assets)
        self.assertTrue(stage5_tests._run_full_lifecycle(fx, "OP-VS-AC5", request,
                                                         include_preview=False)["publish"]["published"])
        roots = ["contract:Game.Core/Contracts/EventTypes.cs"]
        first = vs.build_verification_scope(fx.root, change_roots=roots, in_scope_task_ids=[101])
        self.assertTrue(first["ok"], first.get("diagnostics"))
        self.assertEqual([(101, "B", True)], [(t["task_id"], t["route"], t["valid_input_set"])
                                              for t in first["task_input_set_digests"]])
        self.assertTrue(vs.validate_verification_scope(fx.root, first)["valid"])
        tasks = fx.read_json(".taskmaster/tasks/tasks.json")
        for task in tasks["master"]["tasks"]:
            if task["id"] == 101:
                task["status"] = "done"
        fx.put_json(".taskmaster/tasks/tasks.json", tasks)
        second = vs.build_verification_scope(fx.root, change_roots=roots, in_scope_task_ids=[101])
        self.assertTrue(second["ok"], second.get("diagnostics"))
        self.assertTrue(second["task_input_set_digests"][0]["valid_input_set"])
        self.assertEqual(first["scope_id"], second["scope_id"])
        same = vs.revalidate_verification_scope(fx.root, first)
        self.assertTrue(same["valid"] and same["same_scope_id"], same)
        self.assertFalse(same["task_status_mutated"])


if __name__ == "__main__":
    unittest.main()
