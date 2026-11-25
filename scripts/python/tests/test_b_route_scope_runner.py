"""Story 4.3 real runner VerificationScope consumption & coverage receipt tests (AC-1..AC-5)."""
from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS_PY = ROOT / "scripts" / "python"
TESTS_DIR = SCRIPTS_PY / "tests"
for _entry in (SCRIPTS_PY, TESTS_DIR):
    if str(_entry) not in sys.path:
        sys.path.insert(0, str(_entry))

import _b_route_codec as codec  # noqa: E402
import _b_route_operation_scope as op_scope  # noqa: E402
import _b_route_scope_runner as scope_runner  # noqa: E402
import _b_route_verification_scope as vs  # noqa: E402
import dev_cli_builders  # noqa: E402
import run_mvg_acceptance  # noqa: E402


DIGEST = "sha256:" + "0" * 64
CONTRACT = "Game.Core/Contracts/Offers/OfferLockSnapshot.cs"
MAP_CONTRACT = "Game.Core/Contracts/Map/MapRouteSnapshot.cs"
ADAPTER = "Game.Godot/Scripts/Reward/RewardOfferProvider.cs"
SCENE = "Game.Godot/Scenes/Reward.tscn"
FIXTURE = "Tests.Godot/tests/Integration/Mvg/reward_fixture.gd"
INPUT_TEST = "Tests.Godot/tests/Integration/Mvg/test_reward_input_journey.gd"
SCENE_METHOD_TEST = "Tests.Godot/tests/Integration/Mvg/test_reward_scene_method.gd"
GDUNIT_TEST = "Tests.Godot/tests/Integration/Mvg/test_reward_gdunit.gd"
MAP_SCENE_TEST = "Tests.Godot/tests/Integration/Mvg/test_map_scene.gd"
CORE_TEST = "Game.Core.Tests/Integration/RewardTests.cs"
MAP_CORE_TEST = "Game.Core.Tests/Integration/MapRouteTests.cs"
REWARD_MANIFEST = "docs/testing/mvg/reward.json"
M1_MANIFEST = "docs/testing/mvg/m1-alt.json"
CATALOG = "docs/planning/b-route/catalog.v1.json"
COMBAT = "combat-reward-return"
MAP_FLOW = "map-route-flow"
RELIC = "relic-synergy-preview"


PROTOCOL_FIXTURE_SCRIPT = r'''
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
mode = os.environ.get("TEST_FIXTURE_MODE", "pass")
inv_log = os.environ.get("TEST_FIXTURE_INVOCATIONS", "")
mutate_file = os.environ.get("TEST_FIXTURE_MUTATE_FILE", "")
fail_selector = os.environ.get("TEST_FIXTURE_FAIL_SELECTOR", "")
challenge = os.environ.get("MVG_INPUT_CHALLENGE", "")

def log_call(entry):
    if inv_log:
        Path(inv_log).parent.mkdir(parents=True, exist_ok=True)
        with open(inv_log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

if args and args[0] == "test":
    # dotnet protocol fixture
    selector = ""
    results_dir = ""
    for i, tok in enumerate(args):
        if tok == "--filter" and i + 1 < len(args):
            selector = args[i + 1].removeprefix("FullyQualifiedName~")
        elif tok == "--results-directory" and i + 1 < len(args):
            results_dir = args[i + 1]
    log_call({"kind": "dotnet", "selector": selector, "cwd": os.getcwd()})
    if mutate_file:
        Path(mutate_file).write_text("// mid-run contract drift\npublic sealed class OfferLockSnapshot { public int V = 2; }\n", encoding="utf-8")
    out = Path(results_dir) / "results.trx"
    out.parent.mkdir(parents=True, exist_ok=True)
    if mode == "empty":
        out.write_text("<TestRun/>", encoding="utf-8")
        sys.exit(0)
    if mode == "skipped":
        out.write_text(
            f'<TestRun><UnitTestResult testName="{selector}.TestSkipped" outcome="NotExecuted"/></TestRun>',
            encoding="utf-8",
        )
        sys.exit(0)
    if mode == "fail_dotnet" or (fail_selector and fail_selector == selector):
        out.write_text(
            f'<TestRun><UnitTestResult testName="{selector}.TestCase" outcome="Failed"/>'
            '<Counters total="1" passed="0" failed="1"/></TestRun>',
            encoding="utf-8",
        )
        sys.exit(1)
    out.write_text(
        f'<TestRun><UnitTestResult testName="{selector}.TestCase" outcome="Passed"/>'
        '<Counters total="1" passed="1" failed="0"/></TestRun>',
        encoding="utf-8",
    )
    sys.exit(0)
else:
    # gdunit protocol fixture
    add_path = ""
    rd = ""
    for i, tok in enumerate(args):
        if tok == "--add" and i + 1 < len(args):
            add_path = args[i + 1]
        elif tok == "--rd" and i + 1 < len(args):
            rd = args[i + 1]
    suite = Path(add_path).stem
    log_call({"kind": "gdunit", "suite": suite, "challenge": challenge, "cwd": os.getcwd()})
    out = Path(rd) / "report_1" / "results.xml"
    out.parent.mkdir(parents=True, exist_ok=True)
    if challenge == "disconnect-reward-input":
        out.write_text(
            f'<testsuites tests="1"><testsuite name="{suite}" tests="1" failures="1">'
            f'<testcase classname="{suite}" name="test_input_journey">'
            '<failure message="MVG_REWARD_INPUT_DID_NOT_OPEN_CHOICES">MVG_REWARD_INPUT_DID_NOT_OPEN_CHOICES</failure>'
            '</testcase></testsuite></testsuites>',
            encoding="utf-8",
        )
        sys.exit(1)
    if mode == "empty":
        out.write_text(f'<testsuites tests="0"><testsuite name="{suite}" tests="0"/></testsuites>', encoding="utf-8")
        sys.exit(0)
    if mode == "skipped":
        out.write_text(
            f'<testsuites tests="1"><testsuite name="{suite}" tests="1" skipped="1">'
            f'<testcase classname="{suite}" name="test_skip"><skipped/></testcase></testsuite></testsuites>',
            encoding="utf-8",
        )
        sys.exit(0)
    if mode == "fail_gdunit":
        out.write_text(
            f'<testsuites tests="1"><testsuite name="{suite}" tests="1" failures="1">'
            f'<testcase classname="{suite}" name="test_fail"><failure>boom</failure></testcase>'
            '</testsuite></testsuites>',
            encoding="utf-8",
        )
        sys.exit(1)
    out.write_text(
        f'<testsuites tests="1"><testsuite name="{suite}" tests="1">'
        f'<testcase classname="{suite}" name="test_pass"/></testsuite></testsuites>',
        encoding="utf-8",
    )
    sys.exit(0)
'''


def _ref(schema: str, path: str, entity: str, revision: int = 1) -> dict:
    return {
        "path": path,
        "schema_version": schema,
        "entity_id": entity,
        "revision": revision,
        "digest": DIGEST,
        "verification_mode": "raw",
        "codec_version": None,
    }


def _plan_ref(pid: str) -> dict:
    return _ref("newrouge.b-route-plan.v1", f"docs/planning/b-route/plans/{pid}.plan.v1.json", pid)


def _binding_ref(pid: str) -> dict:
    return _ref("newrouge.b-route-binding.v1", f"docs/planning/b-route/bindings/{pid}.stage5.v1.json", pid)


def _owned(owner: str, ref: str, *paths: str) -> dict:
    return {"owner": owner, "ref": ref, "files": [{"path": p, "raw_digest": DIGEST} for p in paths]}


def _use(kind: str, definition_id: str, owner: str) -> dict:
    return {"kind": kind, "definition_id": definition_id, "owner_plan_id": owner, "owner_revision": 1}


def _write(base: Path, rel: str, content) -> Path:
    target = base.joinpath(*rel.split("/"))
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, (dict, list)):
        text = json.dumps(content, ensure_ascii=False, indent=2) + "\n"
    else:
        text = str(content)
    target.write_text(text, encoding="utf-8")
    return target


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    ).stdout.strip()


def _valid_tscn(*, connected: bool = True) -> str:
    conn = '\n[connection signal="pressed" from="ClaimButton" to="." method="OnClaimPressed"]\n' if connected else "\n"
    return (
        '[gd_scene load_steps=2 format=3]\n'
        f'[ext_resource type="Script" path="res://{ADAPTER}" id="1_script"]\n'
        '[node name="RewardRoot" type="Control"]\n'
        'script = ExtResource("1_script")\n'
        '[node name="ClaimButton" type="Button" parent="."]\n'
        'text = "Claim"\n'
        + conn
    )


def _valid_adapter() -> str:
    return (
        "using Godot;\n"
        "public partial class RewardOfferProvider : Control\n"
        "{\n"
        "    public override void _Ready()\n"
        "    {\n"
        '        var btn = GetNode<Button>("ClaimButton");\n'
        "    }\n"
        "    public void OnClaimPressed() {}\n"
        "}\n"
    )


def _valid_engine_input_gd() -> str:
    return (
        "extends GdUnitTestSuite\n"
        f'const Fixture = preload("res://{FIXTURE}")\n'
        "func test_reward_claim_via_engine_input():\n"
        "    var fx = Fixture.prepare_reward_scene()\n"
        "    var ev = InputEventAction.new()\n"
        '    ev.action = "ui_accept"\n'
        "    ev.pressed = true\n"
        "    get_viewport().push_input(ev)\n"
        "    assert_bool(true).is_true()\n"
    )


def _seed_repo(root: Path, *, include_extra_tiers: bool = False, include_planned_current: bool = False) -> Path:
    """Create a real git repo with B-route plans, bindings, catalog, scenes, tests, and protocol fixture."""
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")

    _write(root, CONTRACT, "public sealed class OfferLockSnapshot { public int V = 1; }\n")
    _write(root, MAP_CONTRACT, "public sealed class MapRouteSnapshot { public int V = 1; }\n")
    _write(root, ADAPTER, _valid_adapter())
    _write(root, SCENE, _valid_tscn(connected=True))
    _write(root, FIXTURE, "static func prepare_reward_scene():\n    return null\n")
    _write(root, INPUT_TEST, _valid_engine_input_gd())
    _write(
        root,
        SCENE_METHOD_TEST,
        "extends GdUnitTestSuite\nfunc test_scene_method():\n    var node = Node.new()\n    node.call('OnClaimPressed')\n",
    )
    _write(
        root,
        GDUNIT_TEST,
        "extends GdUnitTestSuite\nfunc test_gdunit_basic():\n    assert_bool(true).is_true()\n",
    )
    _write(
        root,
        MAP_SCENE_TEST,
        "extends GdUnitTestSuite\nfunc test_map_scene():\n    assert_bool(true).is_true()\n",
    )
    _write(root, CORE_TEST, "public class RewardTests { [Fact] public void TestCase() {} }\n")
    _write(root, MAP_CORE_TEST, "public class MapRouteTests { [Fact] public void TestCase() {} }\n")

    tasks = {
        "master": {
            "tasks": [
                {"id": 84, "title": "Reward Core", "status": "done", "dependencies": []},
                {"id": 114, "title": "Reward UI", "status": "done", "dependencies": [84]},
                {"id": 60, "title": "Map Route", "status": "done", "dependencies": []},
                {"id": 130, "title": "Relic Future", "status": "pending", "dependencies": [84]},
            ]
        }
    }
    _write(root, ".taskmaster/tasks/tasks.json", tasks)
    _write(root, ".taskmaster/tasks/tasks_back.json", [
        {"id": "B-84", "taskmaster_id": 84, "status": "done", "contractRefs": [CONTRACT], "overlay_refs": [], "test_refs": [CORE_TEST]},
        {"id": "B-60", "taskmaster_id": 60, "status": "done", "contractRefs": [MAP_CONTRACT], "overlay_refs": [], "test_refs": [MAP_CORE_TEST]},
    ])
    _write(root, ".taskmaster/tasks/tasks_gameplay.json", [
        {"id": "G-84", "taskmaster_id": 84, "status": "done", "contractRefs": [CONTRACT], "overlay_refs": [], "test_refs": [CORE_TEST]},
        {"id": "G-114", "taskmaster_id": 114, "status": "done", "contractRefs": [], "overlay_refs": [], "test_refs": [INPUT_TEST]},
        {"id": "G-60", "taskmaster_id": 60, "status": "done", "contractRefs": [MAP_CONTRACT], "overlay_refs": [], "test_refs": [MAP_SCENE_TEST]},
    ])

    p1 = {
        "schema_version": "newrouge.b-route-plan.v1",
        "plan_id": "P1",
        "revision": 1,
        "requirements": [
            {"requirement_id": "FR-1", "source_block_ids": ["SB-1"], "acceptance_intent": "claim", "non_task_sinks": []},
        ],
        "definitions": {
            "flows": [
                {
                    "id": COMBAT,
                    "requirement_ids": ["FR-1"],
                    "source_block_ids": ["SB-1"],
                    "capability_ids": ["cap-reward"],
                    "state_owners": [_use("state", "OfferLock", "P1")],
                    "rule_ids": ["RewardRule"],
                    "human_verification": {
                        "applicability": "applicable",
                        "checks": ["Verify reward offer layout visually on Windows"],
                    },
                },
            ],
            "commands": [{"id": "ClaimReward", "requirement_ids": ["FR-1"], "responsibility": "claim", "uses": [_use("state", "OfferLock", "P1")]}],
            "states": [{"id": "OfferLock", "requirement_ids": ["FR-1"], "responsibility": "lock", "uses": []}],
            "rules": [{"id": "RewardRule", "requirement_ids": ["FR-1"], "responsibility": "rule", "uses": []}],
        },
        "applicability": [{"requirement_id": "FR-1", "disposition": "flow", "rationale": "r", "other_verification_refs": []}],
    }
    p2 = {
        "schema_version": "newrouge.b-route-plan.v1",
        "plan_id": "P2",
        "revision": 1,
        "requirements": [
            {"requirement_id": "FR-60", "source_block_ids": ["SB-60"], "acceptance_intent": "map", "non_task_sinks": []},
        ],
        "definitions": {
            "flows": [
                {
                    "id": MAP_FLOW,
                    "requirement_ids": ["FR-60"],
                    "source_block_ids": ["SB-60"],
                    "capability_ids": ["cap-map"],
                    "state_owners": [_use("state", "MapState", "P2")],
                },
            ],
            "commands": [],
            "states": [{"id": "MapState", "requirement_ids": ["FR-60"], "responsibility": "map", "uses": []}],
        },
        "applicability": [{"requirement_id": "FR-60", "disposition": "flow", "rationale": "r", "other_verification_refs": []}],
    }
    _write(root, "docs/planning/b-route/plans/P1.plan.v1.json", p1)
    _write(root, "docs/planning/b-route/plans/P2.plan.v1.json", p2)

    combat_test_ids = ["reward-core", "reward-input"]
    tests_list = [
        {
            "id": "reward-core",
            "kind": "dotnet",
            "state": "implemented",
            "evidence_level": "domain-integration",
            "path": CORE_TEST,
            "selector": "Game.Core.Tests.Integration.RewardTests",
            "min_tests": 1,
        },
        {
            "id": "reward-input",
            "kind": "gdunit",
            "state": "implemented",
            "evidence_level": "engine-input",
            "path": INPUT_TEST,
            "min_tests": 1,
            "challenge": "disconnect-reward-input",
        },
        {
            "id": "map-core",
            "kind": "dotnet",
            "state": "implemented",
            "evidence_level": "domain-integration",
            "path": MAP_CORE_TEST,
            "selector": "Game.Core.Tests.Integration.MapRouteTests",
            "min_tests": 1,
        },
        {
            "id": "map-scene",
            "kind": "gdunit",
            "state": "implemented",
            "evidence_level": "scene-method",
            "path": MAP_SCENE_TEST,
            "min_tests": 1,
        },
    ]
    if include_extra_tiers:
        combat_test_ids.append("reward-scene-method")
        tests_list.append(
            {
                "id": "reward-scene-method",
                "kind": "gdunit",
                "state": "implemented",
                "evidence_level": "scene-method",
                "path": SCENE_METHOD_TEST,
                "min_tests": 1,
            }
        )
    if include_planned_current:
        combat_test_ids.append("reward-bonus-planned")
        tests_list.append({
            "id": "reward-bonus-planned",
            "kind": "dotnet",
            "state": "planned",
            "evidence_level": "domain-integration",
            "path": "Game.Core.Tests/Integration/RewardBonusPlannedTests.cs",
            "selector": "Game.Core.Tests.Integration.RewardBonusPlannedTests",
            "min_tests": 1,
        })

    manifest = {
        "schema_version": "newrouge.mvg-integration.v1",
        "mvg_id": "reward-m1",
        "coverage": {
            "mode": "critical",
            "scope_id": "reward-m1",
            "required_flow_ids": [COMBAT, MAP_FLOW],
            "blocking_task_ids": [],
            "excluded_claims": ["Visual feel remains manual verification."],
        },
        "flows": [
            {
                "id": COMBAT,
                "outcome": "Claim reward and return",
                "task_ids": [84, 114],
                "requirement_ids": ["FR-1"],
                "source_paths": [SCENE, ADAPTER, FIXTURE],
                "handoffs": [
                    {
                        "producer_task": 84,
                        "consumer_task": 114,
                        "owner_task": 114,
                        "contract_ref": CONTRACT,
                        "behavior": "claim once",
                        "test_ids": ["reward-core"],
                    }
                ],
                "test_ids": combat_test_ids,
            },
            {
                "id": MAP_FLOW,
                "outcome": "Map routing",
                "task_ids": [60],
                "requirement_ids": ["FR-60"],
                "source_paths": [MAP_CONTRACT],
                "handoffs": [
                    {
                        "producer_task": 60,
                        "consumer_task": 60,
                        "owner_task": 60,
                        "contract_ref": MAP_CONTRACT,
                        "behavior": "route",
                        "test_ids": ["map-core"],
                    }
                ],
                "test_ids": ["map-core", "map-scene"],
            },
        ],
        "tests": tests_list,
    }
    _write(root, REWARD_MANIFEST, manifest)

    # Alternate smaller manifest (for disjoint lease / missing-test negative tests)
    alt_manifest = {
        "schema_version": "newrouge.mvg-integration.v1",
        "mvg_id": "m1-alt",
        "coverage": {
            "mode": "pilot",
            "scope_id": "m1-alt",
            "required_flow_ids": [MAP_FLOW],
            "blocking_task_ids": [],
            "excluded_claims": ["Visual feel remains manual verification."],
        },
        "flows": [copy.deepcopy(manifest["flows"][1])],
        "tests": [copy.deepcopy(tests_list[2]), copy.deepcopy(tests_list[3])],
    }
    _write(root, M1_MANIFEST, alt_manifest)

    b1 = {
        "schema_version": "newrouge.b-route-binding.v1",
        "plan_id": "P1",
        "binding_revision": 1,
        "plan_ref": _plan_ref("P1"),
        "stage": "5",
        "task_mappings": [
            {
                "task_id": 84,
                "view_refs": [{"view": "gameplay", "business_id": "G-84"}],
                "requirement_ids": ["FR-1"],
                "flow_ids": [COMBAT],
                "part_kinds": ["domain_rules"],
                "roles": ["producer"],
                "obligation_ids": ["OB-1"],
            },
            {
                "task_id": 114,
                "view_refs": [{"view": "gameplay", "business_id": "G-114"}],
                "requirement_ids": ["FR-1"],
                "flow_ids": [COMBAT],
                "part_kinds": ["ui_adapter"],
                "roles": ["consumer"],
                "obligation_ids": ["OB-1"],
            },
        ],
        "parts": [],
        "implementation_objects": [
            {
                "id": "reward-scene",
                "kind": "scene",
                "availability": "existing",
                "responsible_task_ids": [114],
                "expected_type": "Control",
                "lifecycle": "scene",
                "later_checks": ["type"],
                "target_ref": _owned("implementation_reference", "reward-scene", SCENE),
            },
            {
                "id": "reward-adapter",
                "kind": "adapter",
                "availability": "existing",
                "responsible_task_ids": [114],
                "expected_type": "RewardOfferProvider",
                "lifecycle": "scene",
                "later_checks": ["type"],
                "target_ref": _owned("implementation_reference", "reward-adapter", ADAPTER),
            },
        ],
        "obligations": [
            {
                "id": "OB-1",
                "flow_ids": [COMBAT],
                "test_ids": list(combat_test_ids),
                "requirement_ids": ["FR-1"],
                "responsibility": "Verify reward flow end-to-end",
                "verification_refs": [],
            },
        ],
        "manifest_refs": [_owned("manifest", "reward-m1", REWARD_MANIFEST)],
        "other_verification_refs": [],
    }
    b2 = {
        "schema_version": "newrouge.b-route-binding.v1",
        "plan_id": "P2",
        "binding_revision": 1,
        "plan_ref": _plan_ref("P2"),
        "stage": "5",
        "task_mappings": [
            {
                "task_id": 60,
                "view_refs": [{"view": "gameplay", "business_id": "G-60"}],
                "requirement_ids": ["FR-60"],
                "flow_ids": [MAP_FLOW],
                "part_kinds": ["domain_rules"],
                "roles": ["producer"],
                "obligation_ids": ["OB-60"],
            },
        ],
        "parts": [],
        "implementation_objects": [],
        "obligations": [
            {
                "id": "OB-60",
                "flow_ids": [MAP_FLOW],
                "test_ids": ["map-core", "map-scene"],
                "requirement_ids": ["FR-60"],
                "responsibility": "Verify map route flow",
                "verification_refs": [],
            },
        ],
        "manifest_refs": [_owned("manifest", "m1-alt", M1_MANIFEST)],
        "other_verification_refs": [],
    }
    _write(root, "docs/planning/b-route/bindings/P1.stage5.v1.json", b1)
    _write(root, "docs/planning/b-route/bindings/P2.stage5.v1.json", b2)

    policy = {"schema_version": "newrouge.b-route-policy.v1", "policy_id": "policy", "revision": 1}
    _write(root, "docs/planning/b-route/policy.v1.json", policy)
    _write(
        root,
        "docs/planning/b-route/task-origins.v1.json",
        {
            "schema_version": "newrouge.b-route-origins.v1",
            "origins_id": "task-origins",
            "revision": 1,
            "tasks": [
                {"task_id": 84, "source_refs": [], "plan_refs": [_plan_ref("P1")], "binding_refs": [_binding_ref("P1")]},
                {"task_id": 114, "source_refs": [], "plan_refs": [_plan_ref("P1")], "binding_refs": [_binding_ref("P1")]},
                {"task_id": 60, "source_refs": [], "plan_refs": [_plan_ref("P2")], "binding_refs": [_binding_ref("P2")]},
            ],
            "frozen_legacy_refs": [],
        },
    )
    catalog = {
        "schema_version": "newrouge.b-route-catalog.v1",
        "catalog_id": "catalog",
        "revision": 2,
        "policy_ref": _ref("newrouge.b-route-policy.v1", "docs/planning/b-route/policy.v1.json", "policy"),
        "origins_ref": _ref("newrouge.b-route-origins.v1", "docs/planning/b-route/task-origins.v1.json", "task-origins"),
        "scope_heads": [
            {
                "scope_id": "scope-P1",
                "plan_refs": [_plan_ref("P1")],
                "binding_refs": [_binding_ref("P1")],
                "receipt_ref": _ref("newrouge.b-route-commit.v1", "docs/planning/b-route/commits/P1.json", "P1"),
            },
            {
                "scope_id": "scope-P2",
                "plan_refs": [_plan_ref("P2")],
                "binding_refs": [_binding_ref("P2")],
                "receipt_ref": _ref("newrouge.b-route-commit.v1", "docs/planning/b-route/commits/P2.json", "P2"),
            },
        ],
        "definition_owners": [],
        "task_index": [
            {"task_id": 60, "plan_refs": [_plan_ref("P2")], "binding_refs": [_binding_ref("P2")]},
            {"task_id": 84, "plan_refs": [_plan_ref("P1")], "binding_refs": [_binding_ref("P1")]},
            {"task_id": 114, "plan_refs": [_plan_ref("P1")], "binding_refs": [_binding_ref("P1")]},
        ],
    }
    _write(root, CATALOG, catalog)

    fixture_path = root / "tools" / "protocol_fixture_runner.py"
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(PROTOCOL_FIXTURE_SCRIPT, encoding="utf-8")

    _git(root, "add", ".")
    _git(root, "commit", "-qm", "seed-story-4-3")
    return fixture_path


def _build_scope_file(
    root: Path,
    rel_out: str,
    *,
    change_roots: list[str],
    flows: list[str],
    manifests: list[str],
    tasks: list[int] | None = None,
    plans: list[str] | None = None,
) -> dict:
    res = vs.build_verification_scope(
        root,
        change_roots=change_roots,
        in_scope_flow_ids=flows,
        in_scope_task_ids=tasks or [],
        in_scope_plan_ids=plans or [],
        manifest_paths=manifests,
        report_path=rel_out,
    )
    assert res["ok"], f"build_verification_scope failed: {res}"
    return res


def _run_mvg(root: Path, argv: list[str], env_extra: dict[str, str] | None = None) -> tuple[int, dict, dict]:
    parser = argparse.ArgumentParser()
    run_mvg_acceptance.register_arguments(parser)
    args = parser.parse_args(argv)
    prior_dirs = set((root / "logs/ci/mvg-acceptance").glob("*")) if (root / "logs/ci/mvg-acceptance").is_dir() else set()
    old_env = dict(os.environ)
    if env_extra:
        os.environ.update(env_extra)
    try:
        rc = run_mvg_acceptance.run(args, root=root)
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    after_dirs = set((root / "logs/ci/mvg-acceptance").glob("*"))
    new_dirs = sorted(after_dirs - prior_dirs)
    assert len(new_dirs) == 1, f"Expected 1 new run dir, got {new_dirs}"
    run_dir = new_dirs[0]
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    receipt = json.loads((run_dir / "coverage-receipt.json").read_text(encoding="utf-8"))
    return rc, summary, receipt


class ScopeRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nr_s43_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def test_ac1_scoped_vs_conservative_superset_consumes_scope_snapshot_and_business_lease(self):
        fixture = _seed_repo(self.root)
        scope = _build_scope_file(
            self.root,
            "logs/ci/scopes/ac1-narrow.json",
            change_roots=["state:OfferLock"],
            flows=[COMBAT],
            manifests=[REWARD_MANIFEST],
            plans=["P1"],
        )
        self.assertEqual(scope["scope_status"], "executable_ready")

        # 1. Scoped execution: ONLY the 2 declared tests for combat-reward-return run!
        inv_scoped = self.root / "logs/ci/inv-scoped.jsonl"
        rc, summary, receipt = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac1-narrow.json",
                "--execution-strategy", "scoped",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
            ],
            env_extra={"TEST_FIXTURE_INVOCATIONS": str(inv_scoped)},
        )
        self.assertEqual(rc, 0)
        self.assertEqual(receipt["schema_version"], scope_runner.RECEIPT_SCHEMA)
        self.assertEqual(receipt["scope_id"], scope["scope_id"])
        self.assertEqual(receipt["input_set_digest"], scope["input_set_digest"])
        self.assertEqual(summary["scope_id"], scope["scope_id"])
        self.assertEqual(summary["input_set_digest"], scope["input_set_digest"])
        self.assertTrue(receipt["snapshot_digest"])
        self.assertTrue(Path(summary["input_manifest"]).is_file())
        self.assertTrue(receipt["lease"]["acquired"])
        self.assertFalse(receipt["lease"]["uses_global_writer_lock"])
        self.assertEqual(receipt["execution_strategy_used"], "scoped")
        self.assertTrue(receipt["selective_execution_claimed"])
        self.assertFalse(receipt["superset_executed"])
        self.assertEqual(receipt["superset_extra_tests"], [])
        exec_ids = [t["id"] for t in receipt["executed_tests"]]
        self.assertEqual(set(exec_ids), {"static-wiring:scoped", "reward-core", "reward-input"})
        inv_rows = [json.loads(line) for line in inv_scoped.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(inv_rows), 2)

        # 2. Conservative superset execution: all 4 tests in manifest run & extra 2 explicitly listed!
        inv_super = self.root / "logs/ci/inv-superset.jsonl"
        rc2, _sum2, rec2 = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac1-narrow.json",
                "--execution-strategy", "conservative_superset",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
            ],
            env_extra={"TEST_FIXTURE_INVOCATIONS": str(inv_super)},
        )
        self.assertEqual(rc2, 0)
        self.assertEqual(rec2["execution_strategy_used"], "conservative_superset")
        self.assertTrue(rec2["superset_executed"])
        self.assertFalse(rec2["selective_execution_claimed"])
        self.assertEqual(rec2["superset_extra_tests"], ["map-core", "map-scene"])
        exec_ids2 = {t["id"] for t in rec2["executed_tests"]}
        self.assertEqual(exec_ids2, {"static-wiring:scoped", "reward-core", "reward-input", "map-core", "map-scene"})
        inv_rows2 = [json.loads(line) for line in inv_super.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(inv_rows2), 4)

        # Verify dev_cli_builders forwards all Story 4.3 arguments cleanly.
        ns = argparse.Namespace(
            root=str(self.root),
            manifest=REWARD_MANIFEST,
            mode="run",
            snapshot="workspace",
            revision="HEAD",
            base="",
            godot_bin=str(fixture),
            dotnet_bin=str(fixture),
            timeout_sec=120,
            challenge_input=False,
            verification_scope="logs/ci/scopes/ac1-narrow.json",
            execution_strategy="conservative_superset",
            protocol_fixture=True,
            stop_on_deterministic_failure=False,
        )
        built = dev_cli_builders.build_run_mvg_acceptance_cmd(ns)
        self.assertIn("--verification-scope", built)
        self.assertIn("--execution-strategy", built)
        self.assertIn("--protocol-fixture", built)
        self.assertIn("--no-stop-on-deterministic-failure", built)

        # 3. End-to-end subprocess via dev_cli.py run-mvg-acceptance --verification-scope ...
        proc = subprocess.run(
            [
                sys.executable,
                "-B",
                str(SCRIPTS_PY / "dev_cli.py"),
                "run-mvg-acceptance",
                "--root",
                str(self.root),
                "--mode",
                "run",
                "--manifest",
                REWARD_MANIFEST,
                "--verification-scope",
                "logs/ci/scopes/ac1-narrow.json",
                "--execution-strategy",
                "scoped",
                "--dotnet-bin",
                str(fixture),
                "--godot-bin",
                str(fixture),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        cli_out = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(cli_out["scope_id"], scope["scope_id"])
        self.assertFalse(cli_out["runtime_verified"])
        self.assertTrue(cli_out["automated_scope_passed"])
        self.assertTrue(Path(cli_out["coverage_receipt"]).is_file())

        # 4. Plan/recommend mode populates summary["recommendation"] and lists all scheduled checks in not_run!
        rc_plan, sum_plan, rec_plan = _run_mvg(
            self.root,
            [
                "--mode", "recommend",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac1-narrow.json",
            ],
        )
        self.assertEqual(rc_plan, 0)
        self.assertEqual(rec_plan["status"], "recommended")
        self.assertFalse(rec_plan["runtime_verified"])
        self.assertIn("recommendation", sum_plan)
        plan_nr_ids = {item["id"] for item in rec_plan["not_run"]}
        self.assertTrue({"static-wiring:scoped", "reward-core", "reward-input"} <= plan_nr_ids)

        # 5. Automatic conservative_superset when scope impact_binding.conservative_expanded=True!
        exp_scope = _build_scope_file(
            self.root,
            "logs/ci/scopes/ac1-conservative-expanded.json",
            change_roots=["contract:" + CONTRACT],
            flows=[COMBAT],
            manifests=[REWARD_MANIFEST],
            plans=["P1"],
        )
        # Re-seal with conservative_expanded=True in a separate repo-free impact test via patched revalidate.
        ce_doc = copy.deepcopy(exp_scope)
        ce_doc["impact_binding"]["conservative_expanded"] = True
        ce_doc["impact_binding"]["expansion_reasons"] = ["missing_reverse_edge"]
        vs._seal(ce_doc)
        _write(self.root, "logs/ci/scopes/ac1-ce-forced.json", ce_doc)
        from unittest.mock import patch
        with patch.object(
            vs,
            "revalidate_verification_scope",
            return_value={"ok": True, "valid": True, "stale": False, "invalidated_obligations": [], "invalidated_flows": [], "replacement_scope_id": ce_doc["scope_id"]},
        ):
            rc_ce, _, rec_ce = _run_mvg(
                self.root,
                [
                    "--mode", "run",
                    "--manifest", REWARD_MANIFEST,
                    "--verification-scope", "logs/ci/scopes/ac1-ce-forced.json",
                    "--execution-strategy", "scoped",
                    "--dotnet-bin", str(fixture),
                    "--godot-bin", str(fixture),
                ],
            )
        self.assertEqual(rc_ce, 0)
        self.assertEqual(rec_ce["execution_strategy_used"], "conservative_superset")
        self.assertTrue(rec_ce["superset_executed"])
        self.assertFalse(rec_ce["selective_execution_claimed"])
        self.assertEqual(rec_ce["superset_extra_tests"], ["map-core", "map-scene"])
        expected_map_flow_key = op_scope.resource_scopes(flow_ids=[MAP_FLOW])[0]
        self.assertIn(expected_map_flow_key, rec_ce["lease"]["scope_keys"])
        self.assertIn("task:60", rec_ce["lease"]["scope_keys"])

    def test_ac2_coverage_receipt_handles_failed_skipped_empty_pending_manual_and_blocks_false_pass(self):
        # Part A: executable_ready scope (ZERO pending obligations) proving empty TRX, skipped JUnit XML,
        # and missing_godot_bin EACH independently block PASS without dropping existing_required to future!
        ready_root = Path(self.temp.name).resolve() / "ready_repo"
        ready_root.mkdir(parents=True, exist_ok=True)
        ready_fixture = _seed_repo(ready_root, include_planned_current=False)
        ready_scope = _build_scope_file(
            ready_root,
            "logs/ci/scopes/ac2-ready.json",
            change_roots=["state:OfferLock"],
            flows=[COMBAT],
            manifests=[REWARD_MANIFEST],
            plans=["P1"],
        )
        self.assertEqual(ready_scope["scope_status"], "executable_ready")
        self.assertTrue(ready_scope["scope_closable"])
        self.assertEqual(ready_scope["execution_plan"]["pending_obligations"], [])

        # A1: Empty TRX/XML report blocks PASS independently.
        rc_empty, _, rec_empty = _run_mvg(
            ready_root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac2-ready.json",
                "--dotnet-bin", str(ready_fixture),
                "--godot-bin", str(ready_fixture),
                "--no-stop-on-deterministic-failure",
            ],
            env_extra={"TEST_FIXTURE_MODE": "empty"},
        )
        self.assertEqual(rc_empty, 1)
        self.assertFalse(rec_empty["automated_scope_passed"])
        self.assertFalse(rec_empty["runtime_verified"])
        self.assertEqual(rec_empty["out_of_scope_future_obligations"], [])
        self.assertEqual(
            next(x for x in rec_empty["executed_tests"] if x["id"] == "reward-core")["tier"],
            "existing_required",
        )

        # A2: Skipped JUnit XML case blocks PASS independently.
        rc_skip, _, rec_skip = _run_mvg(
            ready_root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac2-ready.json",
                "--dotnet-bin", str(ready_fixture),
                "--godot-bin", str(ready_fixture),
                "--no-stop-on-deterministic-failure",
            ],
            env_extra={"TEST_FIXTURE_MODE": "skipped"},
        )
        self.assertEqual(rc_skip, 1)
        self.assertFalse(rec_skip["automated_scope_passed"])
        self.assertFalse(rec_skip["runtime_verified"])
        self.assertGreater(rec_skip["coverage_summary"]["skipped_count"], 0)
        self.assertEqual(rec_skip["out_of_scope_future_obligations"], [])

        # A3: Missing godot_bin blocks PASS independently while preserving existing_required tier.
        rc_nogd, _, rec_nogd = _run_mvg(
            ready_root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac2-ready.json",
                "--dotnet-bin", str(ready_fixture),
                "--godot-bin", "",
            ],
        )
        self.assertEqual(rc_nogd, 1)
        self.assertEqual(rec_nogd["status"], "blocked")
        self.assertFalse(rec_nogd["automated_scope_passed"])
        self.assertFalse(rec_nogd["runtime_verified"])
        self.assertEqual(rec_nogd["out_of_scope_future_obligations"], [])
        nr_gd = next(x for x in rec_nogd["not_run"] if x["id"] == "reward-input")
        self.assertEqual(nr_gd["reason_code"], "missing_godot_bin")
        self.assertEqual(nr_gd["tier"], "existing_required")
        self.assertTrue(nr_gd["blocking_current_delivery"])

        # Part B: Failed existing_required regression + planned current_new + manual_obligations!
        fixture = _seed_repo(self.root, include_planned_current=True)
        _build_scope_file(
            self.root,
            "logs/ci/scopes/ac2-pending.json",
            change_roots=["state:OfferLock"],
            flows=[COMBAT],
            manifests=[REWARD_MANIFEST],
            plans=["P1"],
        )
        rc_fail, _, rec_fail = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac2-pending.json",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
                "--no-stop-on-deterministic-failure",
            ],
            env_extra={"TEST_FIXTURE_MODE": "fail_dotnet"},
        )
        self.assertEqual(rc_fail, 1)
        self.assertEqual(rec_fail["status"], "blocked")
        self.assertFalse(rec_fail["automated_scope_passed"])
        self.assertFalse(rec_fail["runtime_verified"])

        # Existing regression stays tier="existing_required" & status="failed", NEVER reclassified to out_of_scope_future!
        core_exec = next(item for item in rec_fail["executed_tests"] if item["id"] == "reward-core")
        self.assertEqual(core_exec["tier"], "existing_required")
        self.assertEqual(core_exec["status"], "failed")
        self.assertEqual(rec_fail["out_of_scope_future_obligations"], [])

        # Planned current_new obligation appears in requested_tests and not_run with blocking_current_delivery=True!
        req_ids = {item["id"] for item in rec_fail["requested_tests"]}
        self.assertIn("reward-bonus-planned", req_ids)
        planned_nr = next(item for item in rec_fail["not_run"] if item["id"] == "reward-bonus-planned")
        self.assertTrue(planned_nr["blocking_current_delivery"])
        self.assertGreaterEqual(rec_fail["coverage_summary"]["not_run_blocking_count"], 1)

        # Manual obligations remain manual_pending and verified_by_runner=False!
        self.assertGreaterEqual(len(rec_fail["manual_obligations"]), 1)
        for m in rec_fail["manual_obligations"]:
            self.assertEqual(m["evidence_level"], "manual")
            self.assertEqual(m["status"], "manual_pending")
            self.assertFalse(m["verified_by_runner"])

    def test_ac3_six_evidence_tiers_static_wiring_disconnect_and_engine_input_vs_method_or_fortest_backdoor(self):
        fixture = _seed_repo(self.root, include_extra_tiers=True)
        _build_scope_file(
            self.root,
            "logs/ci/scopes/ac3-full-tiers.json",
            change_roots=["state:OfferLock"],
            flows=[COMBAT],
            manifests=[REWARD_MANIFEST],
            plans=["P1"],
        )

        # 1. Distinct evidence tiers without double-counting + --challenge-input sealed in coverage_receipt!
        rc, summary, receipt = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac3-full-tiers.json",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
                "--challenge-input",
            ],
        )
        self.assertEqual(rc, 0)
        self.assertTrue(receipt["automated_scope_passed"])
        for tier in scope_runner.SIX_EVIDENCE_TIERS:
            self.assertIn(tier, receipt["evidence_tiers"])
        for active_tier in ("domain-xunit", "static-wiring", "scene-method", "engine-input"):
            self.assertEqual(receipt["evidence_tiers"][active_tier]["count"], 1, active_tier)
        self.assertGreaterEqual(receipt["evidence_tiers"]["manual"]["count"], 1)
        # scene-method and engine-input MUST NOT double-count into godot-gdunit!
        self.assertEqual(receipt["evidence_tiers"]["godot-gdunit"]["count"], 0)
        total_tier_count = sum(v["count"] for v in receipt["evidence_tiers"].values())
        self.assertEqual(
            total_tier_count,
            len(receipt["executed_tests"]) + len(receipt["not_run"]) + len(receipt["manual_obligations"]),
        )
        # Exercise all 6 distinct tiers directly including general godot-gdunit without double-counting.
        self.assertEqual(scope_runner.normalize_evidence_tier("gdunit", "godot-gdunit"), "godot-gdunit")
        self.assertEqual(scope_runner.normalize_evidence_tier("gdunit", ""), "godot-gdunit")
        six_summary = scope_runner._build_evidence_tiers_summary(
            [
                {"kind": "dotnet", "evidence_level": "domain-xunit", "status": "passed"},
                {"kind": "gdunit", "evidence_level": "godot-gdunit", "status": "passed"},
                {"kind": "static-wiring", "evidence_level": "static-wiring", "status": "passed"},
                {"kind": "gdunit", "evidence_level": "scene-method", "status": "passed"},
                {"kind": "gdunit", "evidence_level": "engine-input", "status": "passed"},
            ],
            [],
            [{"manual_id": "m1", "evidence_level": "manual"}],
        )
        for tier in scope_runner.SIX_EVIDENCE_TIERS:
            self.assertEqual(six_summary[tier]["count"], 1, tier)
        self.assertEqual(sum(v["count"] for v in six_summary.values()), 6)

        input_exec = next(item for item in receipt["executed_tests"] if item["id"] == "reward-input")
        self.assertEqual(input_exec["evidence_level"], "engine-input")
        self.assertTrue(input_exec["input_authenticity"]["valid"])
        self.assertTrue(input_exec["input_authenticity"]["player_action_input_detected"])
        self.assertTrue(input_exec["input_authenticity"]["fixture_setup_detected"])
        self.assertFalse(input_exec["input_authenticity"]["forbidden_backdoor_detected"])
        self.assertTrue(summary["challenges"][0]["defect_detected"])
        # Challenge result is sealed inside coverage_receipt!
        self.assertEqual(len(receipt["challenges"]), 1)
        self.assertTrue(receipt["challenges"][0]["defect_detected"])
        tampered = copy.deepcopy(receipt)
        tampered["challenges"][0]["defect_detected"] = False
        orig_rid = receipt["receipt_id"]
        scope_runner._seal_receipt(tampered)
        self.assertNotEqual(tampered["receipt_id"], orig_rid)

        # 2. C# string literal "res://..." preserved across _strip_comments (never truncated at //)!
        cs_sample = 'var p = "res://Game.Godot/Scenes/Reward.tscn"; // real comment\nvar x = 1;\n'
        cs_clean = scope_runner._strip_comments(cs_sample, is_cs=True, mask_strings=False)
        self.assertIn('"res://Game.Godot/Scenes/Reward.tscn"', cs_clean)
        self.assertNotIn("real comment", cs_clean)

        # 3. Disconnecting [connection signal="pressed" ...] in Reward.tscn MUST fail static-wiring!
        _write(self.root, SCENE, _valid_tscn(connected=False))
        _build_scope_file(
            self.root,
            "logs/ci/scopes/ac3-disconnected.json",
            change_roots=["state:OfferLock"],
            flows=[COMBAT],
            manifests=[REWARD_MANIFEST],
            plans=["P1"],
        )
        rc_disc, _, rec_disc = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac3-disconnected.json",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
            ],
        )
        self.assertEqual(rc_disc, 1)
        self.assertFalse(rec_disc["automated_scope_passed"])
        self.assertFalse(rec_disc["static_wiring"]["wiring_static_ok"])
        sw_exec = next(item for item in rec_disc["executed_tests"] if item["id"] == "static-wiring:scoped")
        self.assertEqual(sw_exec["status"], "failed")
        self.assertTrue(any(f["failure_kind"] == "disconnected_signal_binding" for f in rec_disc["static_wiring"]["findings"]))

        # 4. Partial multi-Button disconnect: btnA connected programmatically, btnB disconnected -> MUST catch btnB!
        multi_btn_scene = (
            '[gd_scene load_steps=2 format=3]\n'
            f'[ext_resource type="Script" path="res://{ADAPTER}" id="1_script"]\n'
            '[node name="RewardRoot" type="Control"]\n'
            'script = ExtResource("1_script")\n'
            '[node name="ClaimButton" type="Button" parent="."]\n'
            'text = "Claim"\n'
            '[node name="SkipButton" type="Button" parent="."]\n'
            'text = "Skip"\n'
        )
        multi_btn_adapter = (
            "using Godot;\n"
            "public partial class RewardOfferProvider : Control\n"
            "{\n"
            "    public override void _Ready()\n"
            "    {\n"
            '        var btnA = GetNode<Button>("ClaimButton");\n'
            "        btnA.Pressed += OnClaimPressed;\n"
            "    }\n"
            "    public void OnClaimPressed() {}\n"
            "}\n"
        )
        _write(self.root, SCENE, multi_btn_scene)
        _write(self.root, ADAPTER, multi_btn_adapter)
        sw_partial = scope_runner.inspect_scoped_static_wiring(
            self.root, scene_paths=[SCENE], adapter_paths=[ADAPTER], binding_objects=[]
        )
        self.assertFalse(sw_partial["wiring_static_ok"])
        disconnected_nodes = {
            f["node_path"] for f in sw_partial["findings"] if f["failure_kind"] == "disconnected_signal_binding"
        }
        self.assertIn("SkipButton", disconnected_nodes)
        self.assertNotIn("ClaimButton", disconnected_nodes)

        # 5. Restore scene/adapter; string-literal "InputEventAction" & bare InputEventAction.new() without dispatch rejected!
        _write(self.root, SCENE, _valid_tscn(connected=True))
        _write(self.root, ADAPTER, _valid_adapter())
        _write(
            self.root,
            INPUT_TEST,
            'extends GdUnitTestSuite\nfunc test_str_spoof():\n    var s = "InputEventAction push_input(ev)"\n    assert_str(s).is_not_empty()\n',
        )
        str_auth = scope_runner.inspect_gdunit_input_authenticity(self.root, INPUT_TEST, "engine-input")
        self.assertFalse(str_auth["valid"])
        self.assertFalse(str_auth["player_action_input_detected"])

        _write(
            self.root,
            INPUT_TEST,
            "extends GdUnitTestSuite\nfunc test_bare_event():\n    var _e = InputEventAction.new()\n    assert_object(_e).is_not_null()\n",
        )
        bare_auth = scope_runner.inspect_gdunit_input_authenticity(self.root, INPUT_TEST, "engine-input")
        self.assertFalse(bare_auth["valid"])
        self.assertTrue(bare_auth["input_construct_detected"])
        self.assertFalse(bare_auth["input_dispatch_detected"])
        self.assertFalse(bare_auth["player_action_input_detected"])

        # 6. Plain method call -> engine-input authenticity fails end-to-end!
        _write(
            self.root,
            INPUT_TEST,
            "extends GdUnitTestSuite\nfunc test_fake_input():\n    var p = Node.new()\n    p.call('OnClaimPressed')\n",
        )
        _build_scope_file(
            self.root,
            "logs/ci/scopes/ac3-method-spoof.json",
            change_roots=["state:OfferLock"],
            flows=[COMBAT],
            manifests=[REWARD_MANIFEST],
            plans=["P1"],
        )
        rc_meth, _, rec_meth = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac3-method-spoof.json",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
            ],
        )
        self.assertEqual(rc_meth, 1)
        self.assertFalse(rec_meth["automated_scope_passed"])
        meth_exec = next(item for item in rec_meth["executed_tests"] if item["id"] == "reward-input")
        self.assertEqual(meth_exec["status"], "failed")
        self.assertFalse(meth_exec["input_authenticity"]["valid"])
        self.assertEqual(meth_exec["input_authenticity"]["reason"], "engine_input_missing_real_player_input_event")

        # 7. Backdoor rejections: PascalCase ClaimRewardForTest(), snake_case claim_for_test(), and .call("ClaimForTest")!
        for label, gd_body in [
            ("pascal_fortest", "extends GdUnitTestSuite\nfunc test_bd():\n    var ev = InputEventAction.new()\n    get_viewport().push_input(ev)\n    ClaimRewardForTest()\n"),
            ("snake_fortest", "extends GdUnitTestSuite\nfunc test_bd():\n    var ev = InputEventAction.new()\n    get_viewport().push_input(ev)\n    claim_for_test()\n"),
            ("call_fortest", 'extends GdUnitTestSuite\nfunc test_bd():\n    var ev = InputEventAction.new()\n    get_viewport().push_input(ev)\n    node.call("ClaimForTest")\n'),
        ]:
            with self.subTest(backdoor=label):
                _write(self.root, INPUT_TEST, gd_body)
                bd_auth = scope_runner.inspect_gdunit_input_authenticity(self.root, INPUT_TEST, "engine-input")
                self.assertFalse(bd_auth["valid"])
                self.assertTrue(bd_auth["forbidden_backdoor_detected"])

        _write(
            self.root,
            INPUT_TEST,
            "extends GdUnitTestSuite\nfunc test_backdoor():\n    var ev = InputEventAction.new()\n    get_viewport().push_input(ev)\n    ClaimRewardForTest()\n",
        )
        _build_scope_file(
            self.root,
            "logs/ci/scopes/ac3-backdoor.json",
            change_roots=["state:OfferLock"],
            flows=[COMBAT],
            manifests=[REWARD_MANIFEST],
            plans=["P1"],
        )
        rc_bd, _, rec_bd = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac3-backdoor.json",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
            ],
        )
        self.assertEqual(rc_bd, 1)
        self.assertFalse(rec_bd["automated_scope_passed"])
        bd_exec = next(item for item in rec_bd["executed_tests"] if item["id"] == "reward-input")
        self.assertEqual(bd_exec["status"], "failed")
        self.assertTrue(bd_exec["input_authenticity"]["forbidden_backdoor_detected"])

    def test_ac4_mid_run_drift_windows_lease_contention_and_stop_loss_preserve_observed_steps(self):
        fixture = _seed_repo(self.root)
        scope_p1 = _build_scope_file(
            self.root,
            "logs/ci/scopes/ac4-p1.json",
            change_roots=["state:OfferLock"],
            flows=[COMBAT],
            manifests=[REWARD_MANIFEST],
            plans=["P1"],
        )
        scope_p2 = _build_scope_file(
            self.root,
            "logs/ci/scopes/ac4-p2.json",
            change_roots=["state:MapState"],
            flows=[MAP_FLOW],
            manifests=[M1_MANIFEST],
            plans=["P2"],
        )

        # 1. Cross-process Windows msvcrt business lease contention: overlapping blocks, disjoint succeeds!
        p1_keys = scope_runner._compute_business_scope_keys(scope_p1, REWARD_MANIFEST)
        ready_file = self.root / "logs/ci/lease-ready.txt"
        stop_file = self.root / "logs/ci/lease-stop.txt"
        holder_code = (
            "import json, sys, time\n"
            "from pathlib import Path\n"
            f"sys.path.insert(0, {str(SCRIPTS_PY)!r})\n"
            "import _b_route_operation_scope as op_scope\n"
            "root = Path(sys.argv[1])\n"
            "keys = json.loads(sys.argv[2])\n"
            "ready = Path(sys.argv[3])\n"
            "stop = Path(sys.argv[4])\n"
            "with op_scope.business_guard(root, keys, review_only=True):\n"
            "    ready.parent.mkdir(parents=True, exist_ok=True)\n"
            "    ready.write_text('held', encoding='utf-8')\n"
            "    while not stop.exists():\n"
            "        time.sleep(0.05)\n"
        )
        holder = subprocess.Popen(
            [sys.executable, "-B", "-c", holder_code, str(self.root), json.dumps(list(p1_keys)), str(ready_file), str(stop_file)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            deadline = time.monotonic() + 10.0
            while not ready_file.exists() and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertTrue(ready_file.exists(), "Lease holder failed to acquire Windows msvcrt business lease")

            # Overlapping scope P1 MUST block with conflict!
            rc_overlap, _, rec_overlap = _run_mvg(
                self.root,
                [
                    "--mode", "run",
                    "--manifest", REWARD_MANIFEST,
                    "--verification-scope", "logs/ci/scopes/ac4-p1.json",
                    "--dotnet-bin", str(fixture),
                    "--godot-bin", str(fixture),
                ],
            )
            self.assertEqual(rc_overlap, 1)
            self.assertEqual(rec_overlap["status"], "blocked")
            self.assertEqual(rec_overlap["reason_code"], "conflict")
            self.assertTrue(rec_overlap["lease"]["lock_conflict"])
            self.assertFalse(rec_overlap["lease"]["uses_global_writer_lock"])

            # Disjoint scope P2 MUST succeed concurrently while P1 lease is held!
            rc_disjoint, _, rec_disjoint = _run_mvg(
                self.root,
                [
                    "--mode", "run",
                    "--manifest", M1_MANIFEST,
                    "--verification-scope", "logs/ci/scopes/ac4-p2.json",
                    "--dotnet-bin", str(fixture),
                    "--godot-bin", str(fixture),
                ],
            )
            self.assertEqual(rc_disjoint, 0)
            self.assertTrue(rec_disjoint["lease"]["acquired"])
            self.assertTrue(rec_disjoint["automated_scope_passed"])
        finally:
            stop_file.write_text("release", encoding="utf-8")
            holder.wait(timeout=10)
            if holder.stdout:
                holder.stdout.close()
            if holder.stderr:
                holder.stderr.close()

        # 2. Intra-run deterministic stop-loss: failing domain-xunit halts downstream gdunit & preserves observed steps!
        inv_sl = self.root / "logs/ci/inv-stoploss.jsonl"
        rc_sl, _, rec_sl = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac4-p1.json",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
                "--stop-on-deterministic-failure",
            ],
            env_extra={"TEST_FIXTURE_MODE": "fail_dotnet", "TEST_FIXTURE_INVOCATIONS": str(inv_sl)},
        )
        self.assertEqual(rc_sl, 1)
        self.assertEqual(rec_sl["status"], "blocked")
        self.assertTrue(rec_sl["stop_loss"]["triggered"])
        self.assertEqual(rec_sl["stop_loss"]["source"], "intra_run_deterministic_failure")
        self.assertEqual(rec_sl["stop_loss"]["skipped_test_ids"], ["reward-input"])
        self.assertTrue(any(item["id"] == "reward-core" and item["status"] == "failed" for item in rec_sl["executed_tests"]))
        nr_input = next(item for item in rec_sl["not_run"] if item["id"] == "reward-input")
        self.assertEqual(nr_input["reason_code"], "deterministic_stop_loss")
        self.assertIn("stopped_by_deterministic_stop_loss", nr_input["reason"])
        inv_sl_rows = [json.loads(line) for line in inv_sl.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual([r["kind"] for r in inv_sl_rows], ["dotnet"])

        # 3. Mid-run contract drift invalidates verdict while preserving already-executed tests!
        rc_drift, _, rec_drift = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac4-p1.json",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
            ],
            env_extra={"TEST_FIXTURE_MUTATE_FILE": str(self.root / CONTRACT)},
        )
        self.assertEqual(rc_drift, 1)
        self.assertEqual(rec_drift["status"], "blocked")
        self.assertEqual(rec_drift["reason_code"], "input_stale")
        self.assertTrue(rec_drift["drift"]["drift_detected"])
        self.assertFalse(rec_drift["runtime_verified"])
        self.assertTrue(any(item["id"] == "reward-core" for item in rec_drift["executed_tests"]))

        # 4. Durable task rerun_guard stop-loss blocks BEFORE spawning tests!
        _write(self.root, CONTRACT, "public sealed class OfferLockSnapshot { public int V = 1; }\n")
        time.sleep(0.05)
        _write(
            self.root,
            "logs/ci/2026-11-26/sc-review-pipeline-task-84-run1/summary.json",
            {
                "run_id": "run1",
                "status": "fail",
                "reason": "rerun_blocked:deterministic_red",
                "diagnostics": {"rerun_guard": {"blocked": True}},
            },
        )
        inv_dur = self.root / "logs/ci/inv-durable-sl.jsonl"
        rc_dur, _, rec_dur = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac4-p1.json",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
            ],
            env_extra={"TEST_FIXTURE_INVOCATIONS": str(inv_dur)},
        )
        self.assertEqual(rc_dur, 1)
        self.assertEqual(rec_dur["status"], "blocked")
        self.assertEqual(rec_dur["reason_code"], "stop_loss_active")
        self.assertTrue(rec_dur["stop_loss"]["triggered"])
        self.assertEqual(rec_dur["stop_loss"]["source"], "durable_task_signal")
        self.assertFalse(inv_dur.exists(), "Durable stop-loss must prevent spawning child processes")
        dur_nr_ids = {item["id"] for item in rec_dur["not_run"]}
        self.assertTrue({"static-wiring:scoped", "reward-core", "reward-input"} <= dur_nr_ids)

        # 5. Durable stop-loss with other_verification script also records other_verification in not_run!
        ov_root = Path(self.temp.name).resolve() / "ov_sl_repo"
        ov_root.mkdir(parents=True, exist_ok=True)
        ov_fixture = _seed_repo(ov_root)
        ov_script = "scripts/python/check_ov_sample.py"
        _write(ov_root, ov_script, "print('ov_ok')\n")
        p1_ov = json.loads((ov_root / "docs/planning/b-route/plans/P1.plan.v1.json").read_text(encoding="utf-8"))
        p1_ov["requirements"].append(
            {"requirement_id": "FR-OV", "source_block_ids": ["SB-1"], "acceptance_intent": "ov", "non_task_sinks": []}
        )
        p1_ov["applicability"].append(
            {"requirement_id": "FR-OV", "disposition": "other_verification", "rationale": "script", "other_verification_refs": [ov_script]}
        )
        _write(ov_root, "docs/planning/b-route/plans/P1.plan.v1.json", p1_ov)
        b1_ov = json.loads((ov_root / "docs/planning/b-route/bindings/P1.stage5.v1.json").read_text(encoding="utf-8"))
        b1_ov["other_verification_refs"] = [_owned("other_verification", "FR-OV", ov_script)]
        _write(ov_root, "docs/planning/b-route/bindings/P1.stage5.v1.json", b1_ov)
        _git(ov_root, "add", ".")
        _git(ov_root, "commit", "-qm", "add-other-verification")
        _build_scope_file(
            ov_root,
            "logs/ci/scopes/ac4-ov.json",
            change_roots=["state:OfferLock", "requirement:FR-OV"],
            flows=[COMBAT],
            manifests=[REWARD_MANIFEST],
            plans=["P1"],
        )
        _write(
            ov_root,
            "logs/ci/2026-11-26/sc-review-pipeline-task-84-run1/summary.json",
            {
                "run_id": "run1",
                "status": "fail",
                "reason": "rerun_blocked:deterministic_red",
                "diagnostics": {"rerun_guard": {"blocked": True}},
            },
        )
        rc_ov_sl, _, rec_ov_sl = _run_mvg(
            ov_root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac4-ov.json",
                "--dotnet-bin", str(ov_fixture),
                "--godot-bin", str(ov_fixture),
            ],
        )
        self.assertEqual(rc_ov_sl, 1)
        self.assertEqual(rec_ov_sl["reason_code"], "stop_loss_active")
        ov_nr_kinds = {item["kind"] for item in rec_ov_sl["not_run"]}
        self.assertIn("static-wiring", ov_nr_kinds)
        self.assertIn("other_verification", ov_nr_kinds)

        # 6. --snapshot commit --revision <old_sha> MUST block when workspace scope_id mismatches old commit snapshot!
        snap_root = Path(self.temp.name).resolve() / "snap_commit_repo"
        snap_root.mkdir(parents=True, exist_ok=True)
        snap_fixture = _seed_repo(snap_root)
        old_sha = _git(snap_root, "rev-parse", "HEAD")
        _write(snap_root, CONTRACT, "public sealed class OfferLockSnapshot { public int V = 99; }\n")
        _build_scope_file(
            snap_root,
            "logs/ci/scopes/ac4-workspace-newer.json",
            change_roots=["state:OfferLock"],
            flows=[COMBAT],
            manifests=[REWARD_MANIFEST],
            plans=["P1"],
        )
        rc_old, _, rec_old = _run_mvg(
            snap_root,
            [
                "--mode", "run",
                "--snapshot", "commit",
                "--revision", old_sha,
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac4-workspace-newer.json",
                "--dotnet-bin", str(snap_fixture),
                "--godot-bin", str(snap_fixture),
            ],
        )
        self.assertEqual(rc_old, 1)
        self.assertEqual(rec_old["status"], "blocked")
        self.assertEqual(rec_old["reason_code"], "input_stale")
        self.assertFalse(rec_old["runtime_verified"])
        self.assertTrue(rec_old["drift"]["drift_detected"])

    def test_ac5_reconstructable_receipt_bad_scope_rejection_and_protocol_fixture_never_claims_godot_runtime_verified(self):
        fixture = _seed_repo(self.root)
        scope = _build_scope_file(
            self.root,
            "logs/ci/scopes/ac5-valid.json",
            change_roots=["state:OfferLock"],
            flows=[COMBAT],
            manifests=[REWARD_MANIFEST],
            plans=["P1"],
        )

        # 1. Unknown schema_version rejected
        bad_schema = copy.deepcopy(scope)
        bad_schema["schema_version"] = "newrouge.b-route-verification-scope.v999"
        _write(self.root, "logs/ci/scopes/bad-schema.json", bad_schema)
        rc1, _, rec1 = _run_mvg(
            self.root,
            ["--mode", "run", "--manifest", REWARD_MANIFEST, "--verification-scope", "logs/ci/scopes/bad-schema.json"],
        )
        self.assertEqual(rc1, 1)
        self.assertEqual(rec1["status"], "blocked")
        self.assertEqual(rec1["reason_code"], "unknown_schema")

        # 2. Tampered scope_id rejected
        bad_id = copy.deepcopy(scope)
        bad_id["scope_id"] = "sha256:" + "f" * 64
        _write(self.root, "logs/ci/scopes/bad-id.json", bad_id)
        rc2, _, rec2 = _run_mvg(
            self.root,
            ["--mode", "run", "--manifest", REWARD_MANIFEST, "--verification-scope", "logs/ci/scopes/bad-id.json"],
        )
        self.assertEqual(rc2, 1)
        self.assertEqual(rec2["status"], "blocked")
        self.assertEqual(rec2["reason_code"], "digest_mismatch")

        # 3. Wrong / unlisted --manifest rejected
        rc3, _, rec3 = _run_mvg(
            self.root,
            ["--mode", "run", "--manifest", "docs/testing/mvg/nonexistent.json", "--verification-scope", "logs/ci/scopes/ac5-valid.json"],
        )
        self.assertEqual(rc3, 1)
        self.assertEqual(rec3["status"], "blocked")
        self.assertEqual(rec3["reason_code"], "manifest_mismatch")

        # 4. Manifest listed in cumulative_baseline_refs but missing scope-required tests rejected!
        rc4, _, rec4 = _run_mvg(
            self.root,
            ["--mode", "run", "--manifest", M1_MANIFEST, "--verification-scope", "logs/ci/scopes/ac5-valid.json"],
        )
        self.assertEqual(rc4, 1)
        self.assertEqual(rec4["status"], "blocked")
        self.assertEqual(rec4["reason_code"], "missing_required_test")

        # 5. Protocol fixture proves adapter/parsing only: automated_scope_passed=True, runtime_verified=False!
        rc5, summary5, rec5 = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac5-valid.json",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
            ],
        )
        self.assertEqual(rc5, 0)
        self.assertEqual(rec5["status"], "passed_protocol_fixture_only")
        self.assertTrue(rec5["automated_scope_passed"])
        self.assertFalse(rec5["runtime_verified"])
        self.assertFalse(summary5["runtime_verified"])
        self.assertTrue(rec5["environment"]["protocol_fixture_only"])
        self.assertEqual(rec5["environment"]["evidence_authenticity"], "protocol_fixture")
        self.assertEqual(rec5["environment"]["godot_bin_kind"], "protocol_fixture")
        self.assertTrue(rec5["environment"]["python_version"])
        if os.name == "nt":
            self.assertTrue(rec5["environment"]["windows_version"].startswith("Windows-"))
        self.assertTrue(any("protocol_fixture_only" in e for e in rec5["environment"]["unverified_exclusions"]))

        # Reconstructable provenance: command.json, console.log, and raw TRX/XML exist on disk for every executed test!
        for item in rec5["executed_tests"]:
            self.assertTrue(Path(item["command_record"]).is_file(), item["id"])
            self.assertTrue(Path(item["log_path"]).is_file(), item["id"])
            self.assertTrue(item["report_paths"], item["id"])
            for rp in item["report_paths"]:
                self.assertTrue(Path(rp).is_file(), rp)

        # Invariant flags strictly false!
        for flag, expected in scope_runner.INVARIANT_FLAGS.items():
            self.assertIs(rec5[flag], expected)
            self.assertIs(rec5["INVARIANT_FLAGS"][flag], expected)

        # 6. Windows PATHEXT .cmd fake binary on PATH (without .cmd suffix) -> protocol_fixture_only=True, runtime_verified=False!
        cmd_dir = self.root / "fake_path_bin"
        cmd_dir.mkdir(parents=True, exist_ok=True)
        cmd_wrapper = cmd_dir / "custom_godot_runner.cmd"
        cmd_wrapper.write_text(f'@echo off\r\n"{sys.executable}" -B "{fixture}" %*\r\n', encoding="utf-8")
        dotnet_cmd_wrapper = cmd_dir / "custom_dotnet_runner.cmd"
        dotnet_cmd_wrapper.write_text(f'@echo off\r\n"{sys.executable}" -B "{fixture}" %*\r\n', encoding="utf-8")
        pathext_path = str(cmd_dir) + os.pathsep + os.environ.get("PATH", "")
        rc6, sum6, rec6 = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac5-valid.json",
                "--dotnet-bin", "custom_dotnet_runner",
                "--godot-bin", "custom_godot_runner",
            ],
            env_extra={"PATH": pathext_path},
        )
        self.assertEqual(rc6, 0)
        self.assertEqual(rec6["status"], "passed_protocol_fixture_only")
        self.assertTrue(rec6["automated_scope_passed"])
        self.assertFalse(rec6["runtime_verified"])
        self.assertFalse(sum6["runtime_verified"])
        self.assertTrue(rec6["environment"]["protocol_fixture_only"])
        self.assertEqual(rec6["environment"]["godot_bin_kind"], "protocol_fixture")
        self.assertTrue(rec6["environment"]["godot_resolved_bin"].lower().endswith(".cmd"))

        # 7. Non-scoped run_mvg_acceptance with --protocol-fixture / .py wrapper keeps runtime_verified=False!
        parser_ns = argparse.ArgumentParser()
        run_mvg_acceptance.register_arguments(parser_ns)
        args_ns = parser_ns.parse_args([
            "--mode", "run",
            "--manifest", REWARD_MANIFEST,
            "--dotnet-bin", str(fixture),
            "--godot-bin", str(fixture),
            "--protocol-fixture",
        ])
        prior_ns = set((self.root / "logs/ci/mvg-acceptance").glob("*"))
        rc_ns = run_mvg_acceptance.run(args_ns, root=self.root)
        after_ns = sorted(set((self.root / "logs/ci/mvg-acceptance").glob("*")) - prior_ns)
        self.assertEqual(rc_ns, 0)
        sum_ns = json.loads((after_ns[0] / "summary.json").read_text(encoding="utf-8"))
        self.assertTrue(sum_ns["protocol_fixture_only"])
        self.assertFalse(sum_ns["runtime_verified"])
        self.assertEqual(sum_ns["status"], "passed_protocol_fixture_only")


if __name__ == "__main__":
    unittest.main()
