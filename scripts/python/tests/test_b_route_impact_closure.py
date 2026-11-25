"""Story 4.1 governed reverse impact closure tests (AC-1..AC-5)."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_PY = ROOT / "scripts" / "python"
if str(SCRIPTS_PY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_PY))

import _b_route_impact_closure as closure  # noqa: E402
import dev_cli  # noqa: E402
import dev_cli_builders  # noqa: E402


DIGEST = "sha256:" + "0" * 64
CONTRACT = "Game.Core/Contracts/Offers/OfferLockSnapshot.cs"
ADAPTER = "Game.Godot/Scripts/Reward/RewardOfferProvider.cs"
SCENE = "Game.Godot/Scenes/Reward.tscn"
FIXTURE = "Tests.Godot/tests/Integration/Mvg/reward_fixture.gd"
INPUT_TEST = "Tests.Godot/tests/Integration/Mvg/test_reward_input_journey.gd"
CORE_TEST = "Game.Core.Tests/Integration/RewardTests.cs"
OV_DOC = "docs/verification/relic-balance.md"
CATALOG = "docs/planning/b-route/catalog.v1.json"


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


def _edge(eid: str, src: str, dst: str) -> dict:
    return {"id": eid, "from": {"flow_id": src, "node_id": "n1"}, "to": {"flow_id": dst, "node_id": "n1"},
            "condition": "c", "responsibility": "r", "owner": _use("command", "ClaimReward", "P1")}


def _plan_p1() -> dict:
    return {
        "schema_version": "newrouge.b-route-plan.v1", "plan_id": "P1", "revision": 1,
        "requirements": [
            {"requirement_id": "FR-1", "source_block_ids": ["SB-1"], "acceptance_intent": "claim", "non_task_sinks": []},
            {"requirement_id": "FR-2", "source_block_ids": ["SB-2"], "acceptance_intent": "loop", "non_task_sinks": [],
             "prior_requirement_ids": ["FR-1"]},
        ],
        "definitions": {
            "flows": [
                {"id": "combat-reward-return", "requirement_ids": ["FR-1"], "source_block_ids": ["SB-1"],
                 "capability_ids": ["cap-reward"], "state_owners": [_use("state", "OfferLock", "P1")],
                 "rule_ids": ["RewardRule"],
                 "graph": {"nodes": [{"id": "n1", "owner": _use("command", "ClaimReward", "P1")}],
                           "edges": [_edge("e1", "combat-reward-return", "reward-loop")]}},
                {"id": "reward-loop", "requirement_ids": ["FR-1", "FR-2"], "source_block_ids": ["SB-2"],
                 "capability_ids": ["cap-reward"], "rule_ids": ["RewardRule"],
                 "graph": {"nodes": [{"id": "n1"}],
                           "edges": [_edge("e2", "reward-loop", "combat-reward-return")]}},
            ],
            "commands": [{"id": "ClaimReward", "requirement_ids": ["FR-1"], "responsibility": "claim",
                          "uses": [_use("state", "OfferLock", "P1")]}],
            "states": [{"id": "OfferLock", "requirement_ids": ["FR-1"], "responsibility": "lock", "uses": []}],
            "rules": [{"id": "RewardRule", "requirement_ids": ["FR-1"], "responsibility": "rule", "uses": []}],
        },
        "applicability": [{"requirement_id": "FR-1", "disposition": "flow", "rationale": "r",
                           "other_verification_refs": []}],
    }


def _plan_p2() -> dict:
    return {
        "schema_version": "newrouge.b-route-plan.v1", "plan_id": "P2", "revision": 3,
        "requirements": [
            {"requirement_id": "FR-10", "source_block_ids": ["SB-10"], "acceptance_intent": "preview", "non_task_sinks": []},
            {"requirement_id": "FR-11", "source_block_ids": ["SB-11"], "acceptance_intent": "balance", "non_task_sinks": []},
        ],
        "definitions": {
            "flows": [
                {"id": "relic-synergy-preview", "requirement_ids": ["FR-10", "FR-1"], "source_block_ids": ["SB-10"],
                 "capability_ids": ["cap-relic"], "state_owners": [_use("state", "OfferLock", "P1")],
                 "rule_uses": [_use("rule", "RewardRule", "P1")],
                 "handoffs": [
                     {"id": "h1", "from": {"flow_id": "relic-synergy-preview", "node_id": "n1"},
                      "to": {"flow_id": "combat-reward-return", "node_id": "n1"},
                      "owner": _use("state", "OfferLock", "P1")},
                     {"id": "h2", "from": {"flow_id": "combat-reward-return", "node_id": "n1"},
                      "to": {"flow_id": "relic-synergy-preview", "node_id": "n1"},
                      "owner": _use("state", "OfferLock", "P1")},
                 ]},
            ],
            "commands": [], "states": [],
        },
        "applicability": [
            {"requirement_id": "FR-10", "disposition": "flow", "rationale": "r", "other_verification_refs": []},
            {"requirement_id": "FR-11", "disposition": "other_verification", "rationale": "non-flow balance",
             "other_verification_refs": [_owned("other_verification", OV_DOC, OV_DOC)]},
        ],
    }


def _binding(pid: str, revision: int, mappings: list, impls: list, obligations: list, ov: list) -> dict:
    return {
        "schema_version": "newrouge.b-route-binding.v1", "plan_id": pid, "binding_revision": revision,
        "plan_ref": _plan_ref(pid), "stage": "5", "task_mappings": mappings, "parts": [],
        "implementation_objects": impls, "obligations": obligations,
        "manifest_refs": [_owned("manifest", "reward", "docs/testing/mvg/reward.json")],
        "other_verification_refs": ov,
    }


def _mapping(tid: int, flows: list, reqs: list, obligations: list) -> dict:
    return {"task_id": tid, "view_refs": [{"view": "gameplay", "business_id": f"G-{tid}"}], "requirement_ids": reqs,
            "flow_ids": flows, "part_kinds": ["domain_rules"], "roles": ["producer"], "obligation_ids": obligations}


def _impl(iid: str, kind: str, availability: str, tasks: list, path: str | None) -> dict:
    return {"id": iid, "kind": kind, "availability": availability, "responsible_task_ids": tasks,
            "expected_type": "T", "lifecycle": "scene", "later_checks": ["type"],
            "target_ref": _owned("implementation_reference", iid, path) if path else None}


def _manifest() -> dict:
    return {
        "schema_version": "newrouge.mvg-integration.v1", "mvg_id": "reward",
        "flows": [
            {"id": "combat-reward-return", "task_ids": [84, 114], "capability_refs": ["cap-reward"],
             "source_paths": [FIXTURE, SCENE],
             "handoffs": [{"producer_task": 84, "consumer_task": 114, "owner_task": 114, "contract_ref": CONTRACT,
                           "behavior": "b", "test_ids": ["reward-core"]}],
             "test_ids": ["reward-core", "reward-input"]},
            {"id": "relic-synergy-preview", "state": "planned", "task_ids": [84, 130],
             "capability_refs": ["cap-relic"], "test_ids": ["relic-preview"]},
        ],
        "tests": [
            {"id": "reward-core", "kind": "dotnet", "state": "implemented", "path": CORE_TEST},
            {"id": "reward-input", "kind": "gdunit", "state": "implemented", "path": INPUT_TEST},
            {"id": "relic-preview", "kind": "gdunit", "state": "planned",
             "path": "Tests.Godot/tests/Integration/Mvg/test_relic_preview.gd"},
        ],
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
    _write(base, "docs/planning/b-route/plans/P2.plan.v1.json", _plan_p2())
    _write(base, "docs/planning/b-route/bindings/P1.stage5.v1.json", _binding(
        "P1", 2,
        [_mapping(84, ["combat-reward-return"], ["FR-1"], ["OB-1"]),
         _mapping(114, ["combat-reward-return", "reward-loop"], ["FR-1", "FR-2"], ["OB-1"])],
        [_impl("reward-adapter", "adapter", "existing", [114], ADAPTER),
         _impl("reward-scene", "scene", "existing", [114], SCENE),
         _impl("offer-contract", "command", "existing", [84], CONTRACT)],
        [{"id": "OB-1", "requirement_ids": ["FR-1"], "flow_ids": ["combat-reward-return"],
          "test_ids": ["reward-core", "reward-input"], "responsibility": "r", "verification_refs": []}],
        []))
    _write(base, "docs/planning/b-route/bindings/P2.stage5.v1.json", _binding(
        "P2", 4,
        [_mapping(84, ["relic-synergy-preview"], ["FR-10", "FR-11"], ["OB-10"]),
         _mapping(130, ["relic-synergy-preview"], ["FR-10"], ["OB-10"])],
        [_impl("relic-preview-panel", "scene", "planned", [130], None)],
        [{"id": "OB-10", "requirement_ids": ["FR-10"], "flow_ids": ["relic-synergy-preview"],
          "test_ids": ["relic-preview"], "responsibility": "r", "verification_refs": []}],
        [_owned("other_verification", OV_DOC, OV_DOC)]))
    _write(base, "docs/planning/b-route/task-origins.v1.json", {
        "schema_version": "newrouge.b-route-origins.v1", "origins_id": "task-origins", "revision": 1,
        "tasks": [{"task_id": 84, "source_refs": [], "plan_refs": [_plan_ref("P1"), _plan_ref("P2")],
                   "binding_refs": []}], "frozen_legacy_refs": []})
    _write(base, "docs/testing/mvg/reward.json", _manifest())
    _write(base, ".taskmaster/tasks/tasks.json", {"master": {"tasks": [
        {"id": 7, "title": "Unrelated", "description": "d", "details": "", "testStrategy": "", "status": "done",
         "dependencies": []},
        {"id": 84, "title": "Offer lock", "description": "d", "details": "", "testStrategy": "",
         "status": "in-progress", "dependencies": []},
        {"id": 114, "title": "Reward scene", "description": "d", "details": "", "testStrategy": "",
         "status": "pending", "dependencies": [84]},
        {"id": 128, "title": "Reward return", "description": "d", "details": "", "testStrategy": "",
         "status": "pending", "dependencies": [114]},
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
    _write(base, OV_DOC, "# Relic balance verification\n")
    _write(base, "docs/readme.md", "# Fixture\n")


def _ids(items: list[dict]) -> set[str]:
    return {item["entity_id"] for item in items}


def _by_id(items: list[dict]) -> dict[str, dict]:
    return {item["entity_id"]: item for item in items}


def _snapshot(base: Path) -> dict[str, bytes]:
    return {str(p.relative_to(base)): p.read_bytes() for p in sorted(base.rglob("*")) if p.is_file()}


class ImpactClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._template_dir = tempfile.TemporaryDirectory(prefix="br-impact-template-")
        cls.template = Path(cls._template_dir.name) / "repo"
        cls.template.mkdir()
        _build_fixture(cls.template)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._template_dir.cleanup()

    def setUp(self) -> None:
        self._work = tempfile.TemporaryDirectory(prefix="br-impact-case-")
        self.root = Path(self._work.name) / "repo"
        shutil.copytree(self.template, self.root)

    def tearDown(self) -> None:
        self._work.cleanup()

    def _edit_json(self, rel: str, mutate, root: Path | None = None) -> None:
        base = root or self.root
        target = base.joinpath(*rel.split("/"))
        doc = json.loads(target.read_text(encoding="utf-8"))
        result = mutate(doc)
        _write(base, rel, doc if result is None else result)

    def _fresh(self, name: str) -> Path:
        target = Path(self._work.name) / name
        shutil.copytree(self.template, target)
        return target

    def test_ac1_governed_reverse_closure_across_capabilities_shared_tasks_and_planned_flows(self) -> None:
        roots = ["rule:P1:RewardRule", "state:OfferLock", "command:ClaimReward", f"contract:{CONTRACT}",
                 f"adapter:{ADAPTER}", f"scene:{SCENE}", f"test_infra:{FIXTURE}"]
        result = closure.compute_impact_closure(self.root, change_roots=roots)
        self.assertTrue(result["ok"], result["diagnostics"])
        self.assertFalse(result["conservative_expanded"], result["unknown_items"])
        flows = _by_id(result["impacted_flows"])
        self.assertTrue({"combat-reward-return", "reward-loop", "relic-synergy-preview"} <= set(flows))
        self.assertEqual("current", flows["combat-reward-return"]["availability"])
        self.assertEqual("planned", flows["relic-synergy-preview"]["availability"])
        self.assertFalse(flows["relic-synergy-preview"]["immediate_regression_required"])
        self.assertTrue({"84", "114", "128", "130"} <= _ids(result["impacted_tasks"]))
        self.assertTrue({"reward-core", "reward-input", "relic-preview"} <= _ids(result["impacted_tests"]))
        self.assertTrue({"FR-1", "FR-10", "FR-11"} <= _ids(result["impacted_requirements"]))
        self.assertIn(OV_DOC, _ids(result["other_verification_sinks"]))
        self.assertTrue({"P1:OB-1", "P2:OB-10"} <= _ids(result["impacted_obligations"]))
        self.assertIn("P2:relic-preview-panel", _ids(result["impacted_implementation_objects"]))
        root_keys = {"rule:P1:RewardRule", "state:P1:OfferLock", "command:P1:ClaimReward", f"contract:{CONTRACT}",
                     f"adapter:{ADAPTER}", f"scene_resource:{SCENE}", f"test_infra:{FIXTURE}"}
        for name in ("impacted_flows", "impacted_tasks", "impacted_tests", "impacted_requirements",
                     "impacted_obligations", "other_verification_sinks"):
            for item in result[name]:
                self.assertTrue(item["root_causes"], item)
                self.assertIn(item["witness_path"][0]["node"], root_keys, item)
                self.assertEqual("change_root", item["witness_path"][0]["via_edge"])
                self.assertTrue(item["plan_revisions"] or item["binding_revisions"] or item["manifest_refs"]
                                or item["source_refs"], item)
        fixture_tests = {i["entity_id"] for i in result["impacted_tests"] if f"test_infra:{FIXTURE}" in i["root_causes"]}
        self.assertTrue({"reward-input", "reward-core"} <= fixture_tests)
        relic = flows["relic-synergy-preview"]
        self.assertIn("plan:P2@3", relic["plan_revisions"])
        self.assertIn("docs/testing/mvg/reward.json", relic["manifest_refs"])
        self.assertEqual("P2", relic["semantic_owner"]["owner_plan_id"])
        graph = closure.build_governed_reverse_graph(self.root)
        self.assertTrue(graph["ok"])
        kinds = {node["entity_kind"] for node in graph["nodes"]}
        self.assertTrue({"contract", "scene_resource", "adapter", "test_infra", "rule", "state", "command",
                         "implementation_object", "obligation", "requirement", "task", "flow", "capability",
                         "other_verification", "manifest", "plan", "source_block", "test", "part"} <= kinds)
        self.assertEqual([], graph["gaps"])

        task_only = closure.compute_impact_closure(self.root, change_roots=["task:84"])
        self.assertTrue(task_only["ok"], task_only["diagnostics"])
        self.assertFalse(task_only["conservative_expanded"], task_only["unknown_items"])
        task_flows = _by_id(task_only["impacted_flows"])
        self.assertEqual("planned", task_flows["relic-synergy-preview"]["availability"])
        self.assertFalse(task_flows["relic-synergy-preview"]["immediate_regression_required"])
        self.assertEqual(["P2:OB-10"], task_flows["relic-synergy-preview"]["obligation_ids"])
        self.assertTrue(task_flows["combat-reward-return"]["immediate_regression_required"])
        task_items = _by_id(task_only["impacted_tasks"])
        self.assertTrue(task_items["84"]["immediate_regression_required"])
        self.assertIn("P1:OB-1", task_items["84"]["obligation_ids"])
        self.assertFalse(task_items["130"]["immediate_regression_required"])
        for item in task_only["impacted_tests"] + task_only["impacted_requirements"]:
            self.assertIn("obligation_ids", item)

        helper = "Tests.Godot/tests/Integration/Mvg/helpers/reward_helper.gd"
        _write(self.root, helper, "extends RefCounted\n")
        _write(self.root, FIXTURE,
               'extends RefCounted\nconst Helper = preload("res://tests/Integration/Mvg/helpers/reward_helper.gd")\n')
        helper_result = closure.compute_impact_closure(self.root, change_roots=[f"test_infra:{helper}"])
        self.assertTrue(helper_result["ok"], helper_result["diagnostics"])
        self.assertFalse(helper_result["conservative_expanded"], helper_result["unknown_items"])
        self.assertIn("reward-input", _ids(helper_result["impacted_tests"]))

        self._edit_json(".taskmaster/tasks/tasks_back.json", lambda d: d[0].update(
            contractRefs=["OfferLockSnapshot", "Game.Core.Contracts.Offers.OfferLockSnapshot"]))
        symbolic = closure.build_governed_reverse_graph(self.root)
        self.assertEqual([], symbolic["gaps"])
        self.assertTrue(any(e["from"] == f"contract:{CONTRACT}" and e["to"] == "task:84"
                            and e["edge_kind"] == "triplet_contractRefs" for e in symbolic["edges"]))
        self._edit_json(".taskmaster/tasks/tasks_back.json", lambda d: d[0].update(contractRefs=["MissingSnapshot"]))
        missing_symbol = closure.compute_impact_closure(self.root, change_roots=["task:84"])
        self.assertIn("unresolved_contract_ref", {u["reason"] for u in missing_symbol["unknown_items"]})
        self.assertTrue(missing_symbol["conservative_expanded"])

    def test_ac2_cycle_termination_deduplication_and_unique_semantic_owner(self) -> None:
        result = closure.compute_impact_closure(
            self.root, change_roots=["rule:RewardRule", "state:OfferLock", "flow:combat-reward-return"])
        self.assertTrue(result["ok"], result["diagnostics"])
        self.assertTrue(result["cycle_witnesses"])
        cycle_nodes = set().union(*(set(c["nodes"]) for c in result["cycle_witnesses"]))
        self.assertTrue({"flow:combat-reward-return", "flow:reward-loop", "flow:relic-synergy-preview"} <= cycle_nodes)
        self.assertTrue(all(c["classification"] == "governed_cycle_terminated" for c in result["cycle_witnesses"]))
        for name in ("impacted_flows", "impacted_tasks", "impacted_requirements", "impacted_obligations"):
            ids = [item["entity_id"] for item in result[name]]
            self.assertEqual(len(ids), len(set(ids)), name)
        self.assertEqual(result["unique_requirement_count"], len(result["impacted_requirements"]))
        self.assertEqual(1, [r["entity_id"] for r in result["impacted_requirements"]].count("FR-1"))
        rules = [r for r in result["shared_rules"] if r["entity_kind"] == "rule"]
        self.assertEqual(["P1:RewardRule"], [r["entity_id"] for r in rules])
        self.assertEqual({"owner_plan_id": "P1", "kind": "rule", "id": "RewardRule", "revision": 1},
                         rules[0]["semantic_owner"])
        state = [r for r in result["shared_rules"] if r["entity_kind"] == "state"]
        self.assertEqual(["P1:OfferLock"], [r["entity_id"] for r in state])
        again = closure.compute_impact_closure(
            self.root, change_roots=["flow:combat-reward-return", "state:OfferLock", "rule:RewardRule"])
        self.assertEqual(result["impact_proof_id"], again["impact_proof_id"])

        plan1 = "docs/planning/b-route/plans/P1.plan.v1.json"
        plan2 = "docs/planning/b-route/plans/P2.plan.v1.json"
        self._edit_json(plan1, lambda d: d["definitions"]["flows"][1]["graph"].update(edges=[]))
        self._edit_json(plan2, lambda d: d["definitions"]["flows"][0].update(
            handoffs=d["definitions"]["flows"][0]["handoffs"][:1]))
        dag = closure.compute_impact_closure(
            self.root, change_roots=["rule:RewardRule", "state:OfferLock", "flow:combat-reward-return"])
        self.assertTrue(dag["ok"], dag["diagnostics"])
        self.assertEqual([], dag["cycle_witnesses"])
        isolated = closure.compute_impact_closure(self.root, change_roots=["flow:reward-loop"])
        self.assertEqual({"reward-loop"}, _ids(isolated["impacted_flows"]))
        self.assertIn("FR-1", _ids(isolated["impacted_requirements"]))

        self._edit_json(plan1, lambda d: d["definitions"]["flows"][1]["graph"].update(loops=[
            {"id": "L1", "anchors": [{"flow_id": "reward-loop", "node_id": "n1"}], "exit_boundary_ids": ["b1"],
             "description": "d", "exit_condition": "c"}]))
        loop = closure.compute_impact_closure(self.root, change_roots=["flow:reward-loop"])
        self.assertEqual([["flow:reward-loop"]], [c["nodes"] for c in loop["cycle_witnesses"]])
        self.assertEqual(["flow:reward-loop#n1"], loop["cycle_witnesses"][0]["topology_nodes"])

        self._edit_json(plan2, lambda d: d["definitions"]["flows"][0].update(
            handoffs=_plan_p2()["definitions"]["flows"][0]["handoffs"]))
        cross = closure.compute_impact_closure(self.root, change_roots=["flow:relic-synergy-preview"])
        self.assertTrue(cross["ok"], cross["diagnostics"])
        self.assertIn(["flow:combat-reward-return", "flow:relic-synergy-preview"],
                      [c["nodes"] for c in cross["cycle_witnesses"]])

        self._edit_json(CATALOG, lambda d: d.update(definition_owners=[
            {"kind": "rule", "definition_id": "RewardRule", "plan_ref": _plan_ref("P1")},
            {"kind": "flow", "definition_id": "relic-synergy-preview", "plan_ref": _plan_ref("P1")}]))
        owned = closure.compute_impact_closure(self.root, change_roots=["flow:relic-synergy-preview"])
        self.assertTrue(owned["ok"], owned["diagnostics"])
        self.assertEqual("P1", _by_id(owned["impacted_flows"])["relic-synergy-preview"]["semantic_owner"]["owner_plan_id"])
        conflicts = [u["entity"] for u in owned["unknown_items"] if u["reason"] == "definition_owner_conflict"]
        self.assertEqual(["flow:relic-synergy-preview"], conflicts)
        self.assertTrue(owned["conservative_expanded"])

    def test_ac3_missing_edge_or_unknown_mapping_expands_conservatively_without_forcing_planned_regressions(self) -> None:
        _write(self.root, "Game.Core/Services/NewService.cs", "public class NewService {}\n")
        unmapped = closure.compute_impact_closure(self.root, change_roots=["Game.Core/Services/NewService.cs"])
        self.assertTrue(unmapped["ok"], unmapped["diagnostics"])
        self.assertTrue(unmapped["conservative_expanded"])
        self.assertEqual(["unmapped_change_root"], [u["reason"] for u in unmapped["unknown_items"]])
        self.assertTrue(unmapped["expansion_reasons"])
        flows = _by_id(unmapped["impacted_flows"])
        self.assertTrue({"combat-reward-return", "reward-loop", "relic-synergy-preview"} <= set(flows))
        self.assertTrue(unmapped["impacted_tasks"] and unmapped["impacted_obligations"])
        self.assertTrue(flows["combat-reward-return"]["immediate_regression_required"])
        self.assertEqual("planned", flows["relic-synergy-preview"]["availability"])
        self.assertFalse(flows["relic-synergy-preview"]["immediate_regression_required"])
        self.assertIn("unmapped_change_root", flows["relic-synergy-preview"]["unknown_flags"])
        planned_tests = [t for t in unmapped["impacted_tests"] if t["availability"] == "planned"]
        self.assertTrue(planned_tests and not any(t["immediate_regression_required"] for t in planned_tests))

        missing = closure.compute_impact_closure(self.root, change_roots=["does/not/exist.cs"])
        self.assertTrue(missing["conservative_expanded"])
        self.assertEqual("unresolvable_change_root", missing["unknown_items"][0]["reason"])
        self.assertTrue(missing["impacted_flows"])

        self._edit_json("docs/planning/b-route/bindings/P2.stage5.v1.json", lambda d: d.update(stage="4"))
        stage = closure.compute_impact_closure(self.root, change_roots=["flow:relic-synergy-preview"])
        self.assertTrue(stage["conservative_expanded"])
        gap = [u for u in stage["unknown_items"] if u["reason"] == "missing_stage5_binding"]
        self.assertEqual(1, len(gap))
        self.assertEqual("5", gap[0]["owning_stage"])
        self.assertEqual("plan:P2", gap[0]["partition_key"])
        self.assertTrue(stage["impacted_flows"])

        def break_target(doc):
            doc["implementation_objects"][0]["target_ref"]["files"][0]["path"] = "Game.Godot/Scripts/Reward/Missing.cs"
        self._edit_json("docs/planning/b-route/bindings/P1.stage5.v1.json", break_target)
        target = closure.compute_impact_closure(self.root, change_roots=["task:114"])
        reasons = {u["reason"] for u in target["unknown_items"]}
        self.assertIn("unresolved_target_ref", reasons)
        self.assertTrue(target["conservative_expanded"])
        expanded = _by_id(target["impacted_flows"])
        self.assertTrue(expanded["combat-reward-return"]["immediate_regression_required"])
        self.assertFalse(expanded["relic-synergy-preview"]["immediate_regression_required"])

        broken = self._fresh("broken-manifest")
        _write(broken, "docs/testing/mvg/broken.json", "{not json")
        corrupt = closure.compute_impact_closure(broken, change_roots=["flow:combat-reward-return"])
        self.assertTrue(corrupt["ok"], corrupt["diagnostics"])
        self.assertTrue(corrupt["conservative_expanded"])
        self.assertIn("manifest_unreadable", {u["reason"] for u in corrupt["unknown_items"]})
        corrupt_flows = _by_id(corrupt["impacted_flows"])
        self.assertTrue(corrupt_flows["combat-reward-return"]["immediate_regression_required"])
        self.assertEqual("planned", corrupt_flows["relic-synergy-preview"]["availability"])
        self.assertFalse(corrupt_flows["relic-synergy-preview"]["immediate_regression_required"])

        no_ov = self._fresh("missing-other-verification")
        (no_ov / OV_DOC).unlink()
        missing_ov = closure.compute_impact_closure(no_ov, change_roots=["task:130"])
        self.assertTrue(missing_ov["conservative_expanded"])
        self.assertIn("unresolved_other_verification_ref", {u["reason"] for u in missing_ov["unknown_items"]})
        sinks = _by_id(missing_ov["other_verification_sinks"])
        self.assertEqual("planned", sinks[OV_DOC]["availability"])

        journal = self._fresh("pending-journal")
        _write(journal, "logs/ci/b-route-operations/operations/abc/operation.json", {"status": "applying"})
        pending = closure.compute_impact_closure(journal, change_roots=[f"contract:{CONTRACT}"])
        self.assertTrue(pending["conservative_expanded"])
        self.assertIn("pending_journal", {u["reason"] for u in pending["unknown_items"]})
        done = self._fresh("completed-journal")
        _write(done, "logs/ci/b-route-operations/operations/abc/operation.json", {"status": "completed"})
        completed = closure.compute_impact_closure(done, change_roots=[f"contract:{CONTRACT}"])
        self.assertFalse(completed["conservative_expanded"], completed["unknown_items"])

        empty = Path(self._work.name) / "empty"
        empty.mkdir()
        blocked = closure.compute_impact_closure(empty, change_roots=["Game.Core/Services/NewService.cs"])
        self.assertFalse(blocked["ok"])
        self.assertFalse(blocked["reused"])
        self.assertEqual("unresolved_reference", blocked["reason_code"])
        self.assertEqual([], blocked["impacted_flows"])

    def test_ac4_selective_partition_revalidation_unrelated_head_catalog_status_vs_corrupt_proof(self) -> None:
        proof = closure.compute_impact_closure(self.root, change_roots=[f"contract:{CONTRACT}", "rule:P1:RewardRule"])
        self.assertTrue(proof["ok"], proof["diagnostics"])
        self.assertIn("plan:P1", proof["covered_partitions"])
        self.assertIn("plan:P2", proof["covered_partitions"])
        for identity in proof["input_identities"]:
            self.assertEqual(set(closure.IDENTITY_FIELDS), set(identity))
        task_rows = [i for i in proof["input_identities"] if i["category"] == "task_definition"]
        self.assertTrue(task_rows)
        self.assertTrue(all(i["normalization_mode"] == "task_definition_projection_no_status" for i in task_rows))

        git = shutil.which("git")
        if git:
            env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1"}
            for args in (["init", "-q"], ["add", "-A"],
                         ["-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "-m", "base"]):
                subprocess.run([git, *args], cwd=self.root, check=True, env=env, capture_output=True)
        self._edit_json(".taskmaster/tasks/tasks.json",
                        lambda d: [t.update(status="done") for t in d["master"]["tasks"] if t["id"] == 84] and None)
        self._edit_json(".taskmaster/tasks/tasks_back.json", lambda d: d[0].update(status="done"))
        _write(self.root, "docs/readme.md", "# Fixture changed\n")
        p3 = _plan_p2()
        p3.update(plan_id="P3", requirements=[{"requirement_id": "FR-30", "source_block_ids": ["SB-30"],
                                               "acceptance_intent": "x", "non_task_sinks": []}],
                  definitions={"flows": [{"id": "map-travel", "requirement_ids": ["FR-30"], "source_block_ids": ["SB-30"]}],
                               "commands": [], "states": []}, applicability=[])
        _write(self.root, "docs/planning/b-route/plans/P3.plan.v1.json", p3)
        _write(self.root, "docs/planning/b-route/bindings/P3.stage5.v1.json", _binding(
            "P3", 1, [_mapping(200, ["map-travel"], ["FR-30"], [])], [], [], []) | {"manifest_refs": []})
        _write(self.root, CATALOG, _catalog(["P1", "P2", "P3"], {84: ["P1", "P2"], 114: ["P1"], 130: ["P2"], 200: ["P3"]}))
        if git:
            subprocess.run([git, "-c", "user.name=t", "-c", "user.email=t@e", "commit", "-q", "-am", "docs"],
                           cwd=self.root, check=True, env=env, capture_output=True)
        reused = closure.revalidate_impact_proof(self.root, proof)
        self.assertTrue(reused["ok"], reused["diagnostics"])
        self.assertEqual("valid_reused", reused["status"])
        self.assertTrue(reused["reused"])
        self.assertEqual([], reused["invalidated_partitions"])
        self.assertEqual([], reused["recomputed_partitions"])
        self.assertEqual(proof["impact_proof_id"], reused["impact_proof_id"])

        _write(self.root, CONTRACT, "namespace Game.Core.Contracts.Offers; public sealed record OfferLockSnapshot(int V);\n")
        changed = closure.revalidate_impact_proof(self.root, proof)
        self.assertTrue(changed["ok"], changed["diagnostics"])
        self.assertEqual("recomputed", changed["status"])
        self.assertFalse(changed["reused"])
        self.assertIn("plan:P1", changed["invalidated_partitions"])
        self.assertIn(f"path:{CONTRACT}", changed["invalidated_partitions"])
        self.assertNotIn("plan:P2", changed["invalidated_partitions"])
        self.assertIn("plan:P2", changed["reused_partitions"])
        self.assertIn("plan:P1", changed["recomputed_partitions"])
        self.assertTrue(changed["impacted_flows"])

        def edit_rule(doc):
            doc["definitions"]["rules"][0]["responsibility"] = "changed rule"
        self._edit_json("docs/planning/b-route/plans/P1.plan.v1.json", edit_rule)
        rule = closure.revalidate_impact_proof(self.root, changed)
        self.assertEqual("recomputed", rule["status"])
        self.assertIn("plan:P1", rule["invalidated_partitions"])
        self.assertNotIn("plan:P2", rule["invalidated_partitions"])

        tampered = json.loads(json.dumps(proof))
        tampered["partition_digests"]["plan:P1"] = "sha256:" + "f" * 64
        unknown = json.loads(json.dumps(proof))
        unknown["schema_version"] = "newrouge.b-route-impact-closure.v0"
        bare = json.loads(json.dumps(proof))
        bare["input_identities"] = [i["locator"] for i in bare["input_identities"]]
        single = json.loads(json.dumps(proof))
        single["input_identities"] = [{"locator": "tasks.json", "raw_digest": DIGEST}]
        forged = json.loads(json.dumps(proof))
        forged["impacted_flows"] = []
        expected = {"digest_mismatch", "unknown_schema", "schema_validation_failed"}
        for case, code in ((tampered, "digest_mismatch"), (unknown, "unknown_schema"), (bare, "schema_validation_failed"),
                           (single, "schema_validation_failed"), (forged, "digest_mismatch")):
            rejected = closure.revalidate_impact_proof(self.root, case)
            self.assertFalse(rejected["ok"])
            self.assertFalse(rejected["reused"])
            self.assertEqual(code, rejected["reason_code"])
            self.assertIn(rejected["reason_code"], expected)

        sealed_root = self._fresh("sealed")
        sealed = closure.compute_impact_closure(sealed_root, change_roots=[f"contract:{CONTRACT}", "rule:P1:RewardRule"])
        self.assertTrue(sealed["ok"], sealed["diagnostics"])
        self.assertTrue(any(i["category"] == "contract" and i["locator"] == CONTRACT for i in sealed["input_identities"]))
        self.assertIn("governance", sealed["partition_digests"])

        def flip_regression(p):
            p["impacted_flows"][0]["immediate_regression_required"] = not p["impacted_flows"][0]["immediate_regression_required"]

        def forge_owner(p):
            p["impacted_flows"][0]["semantic_owner"]["owner_plan_id"] = "PX"

        def forge_witness(p):
            p["impacted_flows"][0]["witness_path"].append({"node": "flow:x", "via_edge": "e", "authority": "a"})

        def forge_raw(p):
            p["input_identities"][0]["raw_digest"] = "sha256:" + "a" * 64

        for mutate in (flip_regression, forge_owner, forge_witness, forge_raw):
            case = json.loads(json.dumps(sealed))
            mutate(case)
            rejected = closure.revalidate_impact_proof(sealed_root, case)
            self.assertFalse(rejected["ok"], mutate.__name__)
            self.assertFalse(rejected["reused"])
            self.assertEqual("digest_mismatch", rejected["reason_code"], mutate.__name__)

        p4 = {"schema_version": "newrouge.b-route-plan.v1", "plan_id": "P4", "revision": 1,
              "requirements": [{"requirement_id": "FR-40", "source_block_ids": ["SB-40"], "acceptance_intent": "a",
                                "non_task_sinks": []}],
              "definitions": {"flows": [{"id": "offer-audit", "requirement_ids": ["FR-40"], "source_block_ids": ["SB-40"]}],
                              "commands": [], "states": []},
              "applicability": []}
        _write(sealed_root, "docs/planning/b-route/plans/P4.plan.v1.json", p4)
        _write(sealed_root, "docs/planning/b-route/bindings/P4.stage5.v1.json", _binding(
            "P4", 1, [_mapping(84, ["offer-audit"], ["FR-40"], [])],
            [_impl("offer-audit-contract", "command", "existing", [84], CONTRACT)], [], []) | {"manifest_refs": []})
        _write(sealed_root, CATALOG, _catalog(["P1", "P2", "P4"], {84: ["P1", "P2", "P4"], 114: ["P1"], 130: ["P2"]}))
        joined = closure.revalidate_impact_proof(sealed_root, sealed)
        self.assertTrue(joined["ok"], joined["diagnostics"])
        self.assertEqual("recomputed", joined["status"])
        self.assertFalse(joined["reused"])
        self.assertIn("plan:P4", joined["invalidated_partitions"])
        self.assertIn("offer-audit", _ids(joined["impacted_flows"]))
        self.assertEqual(sealed["impact_proof_id"], joined["previous_impact_proof_id"])

    def test_ac5_readonly_cli_zero_write_exclusive_report_events_and_zero_authority_mutation(self) -> None:
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUNBUFFERED": "1"}
        cli = [sys.executable, "-B", str(SCRIPTS_PY / "dev_cli.py"), "b-route-impact-closure", "--root", str(self.root)]
        before = _snapshot(self.root)
        proc = subprocess.run(cli + ["--change-root", f"contract:{CONTRACT}"], capture_output=True, text=True, env=env,
                              timeout=120)
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(before, _snapshot(self.root))
        for flag, value in closure.INVARIANT_FLAGS.items():
            self.assertIs(value, payload[flag])
        self.assertIsNone(payload["report_path"])

        report = "logs/ci/story-4-1/impact.json"
        events = "logs/ci/story-4-1/events.jsonl"
        proc = subprocess.run(cli + ["--change-root", f"contract:{CONTRACT}", "--report", report, "--events-log", events],
                              capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        written = (self.root / report).read_text(encoding="utf-8")
        self.assertEqual(proc.stdout.strip(), written.strip())
        self.assertEqual(report, json.loads(written)["report_path"])
        lines = (self.root / events).read_text(encoding="utf-8").splitlines()
        self.assertEqual(1, len(lines))
        event = json.loads(lines[0])
        self.assertEqual("b_route_impact_closure", event["event"])
        self.assertEqual(closure.SCHEMA, event["schema_version"])
        self.assertTrue(event["ok"])
        self.assertIn("active_elapsed_seconds", event)
        for rel in (".taskmaster/tasks/tasks.json", CATALOG, "docs/testing/mvg/reward.json"):
            self.assertEqual(before[str(Path(rel))], (self.root / rel).read_bytes())

        proc = subprocess.run(cli + ["--change-root", f"contract:{CONTRACT}", "--report", report],
                              capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(1, proc.returncode)
        self.assertEqual("conflict", json.loads(proc.stdout)["reason_code"])

        proc = subprocess.run(cli + ["--revalidate-proof", report], capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertEqual("valid_reused", json.loads(proc.stdout)["status"])

        for bad in (["--change-root", "task:08"], ["--apply"], [], ["--change-root", "C:/x"],
                    ["--change-root", "flow:a", "--report", "docs/out.json"],
                    ["--change-root", f"contract:{CONTRACT}", "--revalidate-proof", report],
                    ["--change-root", f"contract:{ADAPTER}"]):
            proc = subprocess.run(cli + bad, capture_output=True, text=True, env=env, timeout=120)
            self.assertEqual(2, proc.returncode, (bad, proc.stdout))
            self.assertFalse(json.loads(proc.stdout)["ok"])

        proc = subprocess.run(cli + ["--revalidate-proof", "logs/ci/story-4-1/missing.json"], capture_output=True,
                              text=True, env=env, timeout=120)
        self.assertEqual(1, proc.returncode, proc.stdout)
        self.assertEqual("file_not_found", json.loads(proc.stdout)["reason_code"])
        after = _snapshot(self.root)
        self.assertEqual({k: v for k, v in before.items() if not k.startswith("logs")},
                         {k: v for k, v in after.items() if not k.startswith("logs")})

        args = dev_cli.build_parser().parse_args(["b-route-impact-closure", "--root", str(self.root),
                                                  "--change-root", "flow:x", "--plan-id", "P1"])
        built = dev_cli_builders.build_b_route_impact_closure_cmd(args)
        self.assertTrue(built[2].endswith("compute_b_route_impact_closure.py"))
        self.assertIn("--plan-id", built)
        args.apply = True
        with self.assertRaises(ValueError):
            dev_cli_builders.build_b_route_impact_closure_cmd(args)
        args.apply = False
        args.revalidate_proof = report
        with self.assertRaises(ValueError):
            dev_cli_builders.build_b_route_impact_closure_cmd(args)
        args.revalidate_proof = None
        args.report = True
        with self.assertRaises(ValueError):
            dev_cli_builders.build_b_route_impact_closure_cmd(args)
        args.report = None
        args.change_root = [True]
        with self.assertRaises(ValueError):
            dev_cli_builders.build_b_route_impact_closure_cmd(args)
        proc = subprocess.run([sys.executable, "-B", str(SCRIPTS_PY / "dev_cli.py"), "b-route-impact-closure", "--help"],
                              capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(0, proc.returncode)
        self.assertIn("--change-root", proc.stdout)
        self.assertFalse(any(self.root.rglob("__pycache__")))


if __name__ == "__main__":
    unittest.main()
