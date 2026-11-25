"""Story 4.4 identity-verified build/prewarm reuse, shared test evidence deduplication,
and per-test mutable state isolation tests (AC-1..AC-5)."""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
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
import _b_route_evidence_reuse as evidence_reuse  # noqa: E402
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
MAP_SCENE_TEST = "Tests.Godot/tests/Integration/Mvg/test_map_scene.gd"
CORE_TEST = "Game.Core.Tests/Integration/RewardTests.cs"
MAP_CORE_TEST = "Game.Core.Tests/Integration/MapRouteTests.cs"
REWARD_MANIFEST = "docs/testing/mvg/reward.json"
CATALOG = "docs/planning/b-route/catalog.v1.json"
COMBAT = "combat-reward-return"
MAP_FLOW = "map-route-flow"


REUSE_FIXTURE_SCRIPT = r'''
import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
inv_log = os.environ.get("TEST_FIXTURE_INVOCATIONS", "")
fail_selector = os.environ.get("TEST_FIXTURE_FAIL_SELECTOR", "")
fail_suite = os.environ.get("TEST_FIXTURE_FAIL_SUITE", "")
assert_clean_state = os.environ.get("TEST_FIXTURE_ASSERT_CLEAN_STATE", "") == "1"
pollute_rel = os.environ.get("TEST_FIXTURE_POLLUTE_SNAPSHOT_REL", "")
pollute_selector = os.environ.get("TEST_FIXTURE_POLLUTE_SELECTOR", "")

def log_call(entry):
    if inv_log:
        Path(inv_log).parent.mkdir(parents=True, exist_ok=True)
        with open(inv_log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")

def check_and_write_isolated_state(label):
    appdata = Path(os.environ.get("APPDATA", ""))
    tempdir = Path(os.environ.get("TEMP", ""))
    user_marker = appdata / "mutable_save_state.txt"
    tmp_marker = tempdir / "mutable_temp_state.txt"
    leaked = user_marker.exists() or tmp_marker.exists()
    appdata.mkdir(parents=True, exist_ok=True)
    tempdir.mkdir(parents=True, exist_ok=True)
    user_marker.write_text(f"written-by:{label}\n", encoding="utf-8")
    tmp_marker.write_text(f"temp-by:{label}\n", encoding="utf-8")
    return leaked, str(appdata), str(tempdir)

if args and args[0] == "test":
    selector = ""
    results_dir = ""
    no_build = "--no-build" in args
    for i, tok in enumerate(args):
        if tok == "--filter" and i + 1 < len(args):
            selector = args[i + 1].removeprefix("FullyQualifiedName~")
        elif tok == "--results-directory" and i + 1 < len(args):
            results_dir = args[i + 1]
    leaked, appdata_s, temp_s = check_and_write_isolated_state(selector)
    if not no_build:
        for rel, body in (
            ("Game.Core/bin/Debug/net8.0/Game.Core.dll", b"FAKE-CORE-DLL-V1"),
            ("Game.Core/obj/project.assets.json", b'{"version": 3, "targets": {}}\n'),
            ("Game.Core.Tests/bin/Debug/net8.0/Game.Core.Tests.dll", b"FAKE-DOTNET-ASSEMBLY-V1"),
            ("Game.Core.Tests/bin/Debug/net8.0/Game.Core.Tests.deps.json", b'{"runtimeTarget": {"name": ".NETCoreApp,Version=v8.0"}}\n'),
            ("Game.Core.Tests/bin/Debug/net8.0/Game.Core.Tests.runtimeconfig.json", b'{"runtimeOptions": {"tfm": "net8.0"}}\n'),
            ("Game.Core.Tests/bin/Debug/net8.0/testhost.dll", b"FAKE-TESTHOST-V1"),
            ("Game.Core.Tests/obj/project.assets.json", b'{"version": 3, "targets": {}}\n'),
            ("Game.Core.Tests/obj/Game.Core.Tests.csproj.nuget.dgspec.json", b'{"format": 1}\n'),
        ):
            p = Path(rel)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(body)
    else:
        required_for_no_build = (
            "Game.Core.Tests/bin/Debug/net8.0/Game.Core.Tests.dll",
            "Game.Core.Tests/bin/Debug/net8.0/Game.Core.Tests.deps.json",
            "Game.Core.Tests/bin/Debug/net8.0/Game.Core.Tests.runtimeconfig.json",
            "Game.Core.Tests/obj/project.assets.json",
        )
        missing_art = [r for r in required_for_no_build if not Path(r).is_file()]
        if missing_art:
            out = Path(results_dir) / "results.trx"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                f'<TestRun><UnitTestResult testName="{selector}.TestCase" outcome="Failed"/>'
                '<Counters total="1" passed="0" failed="1"/></TestRun>',
                encoding="utf-8",
            )
            sys.exit(1)
    if pollute_rel and (not pollute_selector or pollute_selector == selector):
        target = Path(pollute_rel)
        target.write_text(target.read_text(encoding="utf-8") + "// polluted by test\n", encoding="utf-8")
    log_call({
        "kind": "dotnet",
        "selector": selector,
        "no_build": no_build,
        "appdata": appdata_s,
        "temp": temp_s,
        "leaked": leaked,
        "cwd": os.getcwd(),
    })
    out = Path(results_dir) / "results.trx"
    out.parent.mkdir(parents=True, exist_ok=True)
    if (assert_clean_state and leaked) or (fail_selector and fail_selector == selector):
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
    add_path = ""
    rd = ""
    prewarm = "--prewarm" in args
    challenge_mode = os.environ.get("MVG_INPUT_CHALLENGE", "") == "disconnect-reward-input"
    for i, tok in enumerate(args):
        if tok == "--add" and i + 1 < len(args):
            add_path = args[i + 1]
        elif tok == "--rd" and i + 1 < len(args):
            rd = args[i + 1]
    suite = Path(add_path).stem
    leaked, appdata_s, temp_s = check_and_write_isolated_state(suite)
    if prewarm:
        cache = Path("Tests.Godot/.godot/uid_cache.bin")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(b"FAKE-GODOT-PREWARM-CACHE-V1")
    log_call({
        "kind": "gdunit",
        "suite": suite,
        "prewarm": prewarm,
        "challenge": challenge_mode,
        "appdata": appdata_s,
        "temp": temp_s,
        "leaked": leaked,
        "cwd": os.getcwd(),
    })
    out = Path(rd) / "report_1" / "results.xml"
    out.parent.mkdir(parents=True, exist_ok=True)
    if challenge_mode:
        out.write_text(
            f'<testsuites tests="1"><testsuite name="{suite}" tests="1" failures="1">'
            f'<testcase classname="{suite}" name="test_reward_claim_via_engine_input">'
            '<failure>MVG_REWARD_INPUT_DID_NOT_OPEN_CHOICES</failure></testcase>'
            '</testsuite></testsuites>',
            encoding="utf-8",
        )
        sys.exit(1)
    if (assert_clean_state and leaked) or (fail_suite and fail_suite == suite):
        out.write_text(
            f'<testsuites tests="1"><testsuite name="{suite}" tests="1" failures="1">'
            f'<testcase classname="{suite}" name="test_fail"><failure>failed</failure></testcase>'
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


def _valid_tscn() -> str:
    return (
        '[gd_scene load_steps=2 format=3]\n'
        f'[ext_resource type="Script" path="res://{ADAPTER}" id="1_script"]\n'
        '[node name="RewardRoot" type="Control"]\n'
        'script = ExtResource("1_script")\n'
        '[node name="ClaimButton" type="Button" parent="."]\n'
        'text = "Claim"\n'
        '[connection signal="pressed" from="ClaimButton" to="." method="OnClaimPressed"]\n'
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


def _seed_repo(
    root: Path,
    *,
    shared_test_across_flows: bool = False,
    reverse_tests: bool = False,
    extra_unscoped_task: bool = False,
) -> Path:
    """Create a real git repo with B-route plans, bindings, catalog, scenes, tests, and fixture runner."""
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")

    _write(root, ".gitignore", "logs/\n")
    _write(root, "project.godot", "[application]\nconfig/name=\"newrouge\"\n")
    _write(root, "Tests.Godot/project.godot", "[application]\nconfig/name=\"newrouge-tests\"\n")
    _write(root, "Game.Core.Tests/Game.Core.Tests.csproj", "<Project Sdk=\"Microsoft.NET.Sdk\"></Project>\n")
    _write(root, CONTRACT, "public sealed class OfferLockSnapshot { public int V = 1; }\n")
    _write(root, MAP_CONTRACT, "public sealed class MapRouteSnapshot { public int V = 1; }\n")
    _write(root, ADAPTER, _valid_adapter())
    _write(root, SCENE, _valid_tscn())
    _write(root, FIXTURE, "static func prepare_reward_scene():\n    return null\n")
    _write(root, INPUT_TEST, _valid_engine_input_gd())
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
            ] + (
                [{"id": 999, "title": "Unrelated Backlog Task", "status": "pending", "dependencies": []}]
                if extra_unscoped_task else []
            )
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
        "applicability": [{"requirement_id": "FR-1", "disposition": "flow", "rationale": "primary flow", "other_verification_refs": []}],
        "requirement_verification": [{"requirement_id": "FR-1", "disposition": "flow", "primary_flow_id": COMBAT}],
        "requirement_route_memberships": [
            {"requirement_id": "FR-1", "flow_id": COMBAT, "observable_role": "Primary reward claim state"},
        ] + (
            [{"requirement_id": "FR-1", "flow_id": MAP_FLOW, "observable_role": "Post-claim map transition lock"}]
            if shared_test_across_flows else []
        ),
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
                    "requirement_ids": ["FR-60"] + (["FR-1"] if shared_test_across_flows else []),
                    "source_block_ids": ["SB-60"],
                    "capability_ids": ["cap-map"],
                    "state_owners": [_use("state", "MapState", "P2")],
                },
            ],
            "commands": [],
            "states": [{"id": "MapState", "requirement_ids": ["FR-60"], "responsibility": "map", "uses": []}],
        },
        "applicability": [{"requirement_id": "FR-60", "disposition": "flow", "rationale": "map flow", "other_verification_refs": []}],
        "requirement_verification": [{"requirement_id": "FR-60", "disposition": "flow", "primary_flow_id": MAP_FLOW}],
        "requirement_route_memberships": [
            {"requirement_id": "FR-60", "flow_id": MAP_FLOW, "observable_role": "Map route advancement"},
        ],
    }
    _write(root, "docs/planning/b-route/plans/P1.plan.v1.json", p1)
    _write(root, "docs/planning/b-route/plans/P2.plan.v1.json", p2)

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
            "id": "map-core",
            "kind": "dotnet",
            "state": "implemented",
            "evidence_level": "domain-integration",
            "path": MAP_CORE_TEST,
            "selector": "Game.Core.Tests.Integration.MapRouteTests",
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
            "id": "map-scene",
            "kind": "gdunit",
            "state": "implemented",
            "evidence_level": "scene-method",
            "path": MAP_SCENE_TEST,
            "min_tests": 1,
        },
    ]
    if reverse_tests:
        tests_list = list(reversed(tests_list))

    map_flow_test_ids = ["reward-core", "map-core", "map-scene"] if shared_test_across_flows else ["map-core", "map-scene"]
    manifest = {
        "schema_version": "newrouge.mvg-integration.v1",
        "mvg_id": "reward-m1",
        "coverage": {
            "mode": "critical",
            "scope_id": "reward-m1",
            "required_flow_ids": [COMBAT, MAP_FLOW],
            "blocking_task_ids": [],
            "excluded_claims": ["Full campaign balance"],
        },
        "flows": [
            {
                "id": COMBAT,
                "outcome": "Claim reward and return to map",
                "task_ids": [84, 114],
                "requirement_ids": ["FR-1"],
                "test_ids": ["reward-core", "reward-input"],
                "source_paths": [CONTRACT, ADAPTER, SCENE, FIXTURE],
                "handoffs": [
                    {
                        "producer_task": 84,
                        "consumer_task": 114,
                        "owner_task": 114,
                        "contract_ref": CONTRACT,
                        "behavior": "claim once",
                        "test_ids": ["reward-core", "reward-input"],
                    }
                ],
            },
            {
                "id": MAP_FLOW,
                "outcome": "Advance map route after reward",
                "task_ids": [60],
                "requirement_ids": ["FR-60"] + (["FR-1"] if shared_test_across_flows else []),
                "test_ids": map_flow_test_ids,
                "source_paths": [MAP_CONTRACT],
                "handoffs": [
                    {
                        "producer_task": 60,
                        "consumer_task": 60,
                        "owner_task": 60,
                        "contract_ref": MAP_CONTRACT,
                        "behavior": "advance map route",
                        "test_ids": map_flow_test_ids,
                    }
                ],
            },
        ],
        "tests": tests_list,
    }
    _write(root, REWARD_MANIFEST, manifest)

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
                "test_ids": ["reward-core", "reward-input"],
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
                "requirement_ids": ["FR-60"] + (["FR-1"] if shared_test_across_flows else []),
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
                "test_ids": map_flow_test_ids,
                "requirement_ids": ["FR-60"] + (["FR-1"] if shared_test_across_flows else []),
                "responsibility": "Verify map route flow",
                "verification_refs": [],
            },
        ],
        "manifest_refs": [_owned("manifest", "reward-m1", REWARD_MANIFEST)],
        "other_verification_refs": [],
    }
    _write(root, "docs/planning/b-route/bindings/P1.stage5.v1.json", b1)
    _write(root, "docs/planning/b-route/bindings/P2.stage5.v1.json", b2)
    _write(root, "docs/planning/b-route/policy.v1.json", {"schema_version": "newrouge.b-route-policy.v1", "policy_id": "policy", "revision": 1, "active_route": "A"})
    _write(root, "docs/planning/b-route/commits/P1.json", {"schema_version": "newrouge.b-route-commit.v1", "operation_id": "P1", "revision": 1})
    _write(root, "docs/planning/b-route/commits/P2.json", {"schema_version": "newrouge.b-route-commit.v1", "operation_id": "P2", "revision": 1})
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

    fixture_path = root / "tools" / "reuse_fixture_runner.py"
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(REUSE_FIXTURE_SCRIPT, encoding="utf-8")

    _git(root, "add", ".")
    _git(root, "commit", "-qm", "seed-story-4-4")
    return fixture_path


def _build_scope(root: Path, rel_out: str, *, flows: list[str], plans: list[str], change_roots: list[str]) -> dict:
    res = vs.build_verification_scope(
        root,
        change_roots=change_roots,
        in_scope_flow_ids=flows,
        in_scope_task_ids=[],
        in_scope_plan_ids=plans,
        manifest_paths=[REWARD_MANIFEST],
        report_path=rel_out,
    )
    assert res["ok"], f"build_verification_scope failed: {res}"
    return res


def _run_mvg(root: Path, argv: list[str], env_extra: dict[str, str] | None = None) -> tuple[int, Path, dict, dict]:
    parser = argparse.ArgumentParser()
    run_mvg_acceptance.register_arguments(parser)
    args = parser.parse_args(argv)
    mvg_root = root / "logs/ci/mvg-acceptance"
    prior_dirs = set(mvg_root.glob("*")) if mvg_root.is_dir() else set()
    old_env = dict(os.environ)
    if env_extra:
        os.environ.update(env_extra)
    try:
        rc = run_mvg_acceptance.run(args, root=root)
    finally:
        os.environ.clear()
        os.environ.update(old_env)
    after_dirs = set(mvg_root.glob("*"))
    new_dirs = sorted(after_dirs - prior_dirs)
    assert len(new_dirs) == 1, f"Expected 1 new run dir, got {new_dirs}"
    run_dir = new_dirs[0]
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    receipt_path = run_dir / "coverage-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.is_file() else {}
    return rc, run_dir, summary, receipt


class EvidenceReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nr_s44_")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.aux_temp = tempfile.TemporaryDirectory(prefix="nr_s44_aux_")
        self.addCleanup(self.aux_temp.cleanup)
        self.aux_dir = Path(self.aux_temp.name).resolve()

    def test_ac1_build_and_prewarm_reuse_require_matching_identity_and_never_imply_test_pass_or_fake_cost_savings(self):
        fixture = _seed_repo(self.root)
        _build_scope(
            self.root,
            "logs/ci/scopes/ac1-both.json",
            flows=[COMBAT, MAP_FLOW],
            plans=["P1", "P2"],
            change_roots=["state:OfferLock", "state:MapState"],
        )

        # 1. Intra-run build & prewarm reuse: first dotnet builds DLL, second gets --no-build;
        # first gdunit runs --prewarm, second skips --prewarm.
        inv_log = self.root / "logs/ci/ac1-inv.jsonl"
        rc, run1_dir, _sum1, rec1 = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac1-both.json",
                "--execution-strategy", "scoped",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
            ],
            env_extra={"TEST_FIXTURE_INVOCATIONS": str(inv_log)},
        )
        self.assertEqual(rc, 0)
        calls = [json.loads(line) for line in inv_log.read_text(encoding="utf-8").splitlines() if line.strip()]
        dotnet_calls = [c for c in calls if c["kind"] == "dotnet"]
        gdunit_calls = [c for c in calls if c["kind"] == "gdunit"]
        self.assertEqual([c["no_build"] for c in dotnet_calls], [False, True])
        self.assertEqual([c["prewarm"] for c in gdunit_calls], [True, False])

        by_id = {item["id"]: item for item in rec1["executed_tests"]}
        self.assertFalse(by_id["map-core"]["build_reuse"]["reused"])
        self.assertTrue(by_id["reward-core"]["build_reuse"]["reused"])
        self.assertEqual(by_id["reward-core"]["build_reuse"]["match_reason"], "matching_dotnet_source_and_toolchain_identity")
        self.assertEqual(by_id["reward-core"]["build_reuse"]["source_run_id"], rec1["run_id"])
        self.assertEqual(by_id["reward-core"]["build_reuse"]["source_step_id"], "map-core")
        self.assertTrue(by_id["reward-core"]["build_reuse"]["original_created_at"])

        self.assertFalse(by_id["map-scene"]["build_reuse"]["reused"])
        self.assertTrue(by_id["reward-input"]["build_reuse"]["reused"])
        self.assertEqual(by_id["reward-input"]["build_reuse"]["match_reason"], "matching_godot_source_and_toolchain_identity")
        self.assertFalse(rec1["build_reuse_implies_test_pass"])
        self.assertFalse(rec1["reserved_budget_claimed_as_savings"])
        self.assertFalse(rec1["metrics"]["reserved_budget_claimed_as_savings"])
        self.assertFalse(rec1["metrics"]["speedup_or_cost_gate_enforced"])
        self.assertEqual(rec1["metrics"]["reserved_dispatches"], 4)
        self.assertEqual(rec1["metrics"]["observed_dispatches"], 4)
        self.assertEqual(rec1["metrics"]["build_reuses"], 2)
        self.assertGreaterEqual(rec1["metrics"]["missed_build_elapsed_seconds"], 0.0)

        # Verify complete bin + obj build artifacts are hashed in build_artifacts.dotnet_build.
        dotnet_art_files = rec1["build_artifacts"]["dotnet_build"]["artifact_files"]
        self.assertIn("Game.Core.Tests/bin/Debug/net8.0/Game.Core.Tests.dll", dotnet_art_files)
        self.assertIn("Game.Core.Tests/bin/Debug/net8.0/Game.Core.Tests.deps.json", dotnet_art_files)
        self.assertIn("Game.Core.Tests/bin/Debug/net8.0/Game.Core.Tests.runtimeconfig.json", dotnet_art_files)
        self.assertIn("Game.Core.Tests/obj/project.assets.json", dotnet_art_files)
        self.assertIn("Game.Core/obj/project.assets.json", dotnet_art_files)

        # 2. Cross-run --reuse-build-from hydrates complete bin+obj & prewarm outputs;
        # failing dotnet OR failing downstream GdUnit suite STILL FAILS!
        inv_log2 = self.root / "logs/ci/ac1-inv2.jsonl"
        run1_rel = run1_dir.relative_to(self.root).as_posix()
        rc2, run2_dir, _sum2, rec2 = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac1-both.json",
                "--execution-strategy", "scoped",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
                "--reuse-build-from", run1_rel,
            ],
            env_extra={
                "TEST_FIXTURE_INVOCATIONS": str(inv_log2),
                "TEST_FIXTURE_FAIL_SELECTOR": "Game.Core.Tests.Integration.RewardTests",
            },
        )
        self.assertEqual(rc2, 1)
        self.assertFalse(rec2["automated_scope_passed"])
        self.assertFalse(rec2["runtime_verified"])
        self.assertFalse(rec2["build_reuse_implies_test_pass"])
        by_id2 = {item["id"]: item for item in rec2["executed_tests"]}
        self.assertTrue(by_id2["reward-core"]["build_reuse"]["reused"])
        self.assertEqual(by_id2["reward-core"]["status"], "failed")
        self.assertTrue((run2_dir / "snapshot/Game.Core.Tests/bin/Debug/net8.0/Game.Core.Tests.deps.json").is_file())
        self.assertTrue((run2_dir / "snapshot/Game.Core.Tests/bin/Debug/net8.0/Game.Core.Tests.runtimeconfig.json").is_file())
        self.assertTrue((run2_dir / "snapshot/Game.Core.Tests/obj/project.assets.json").is_file())
        calls2 = [json.loads(line) for line in inv_log2.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertTrue(all(c["no_build"] for c in calls2 if c["kind"] == "dotnet"))

        # 2b. Cross-run --reuse-build-from with passing dotnet + TEST_FIXTURE_FAIL_SUITE failing downstream GdUnit!
        inv_log2b = self.root / "logs/ci/ac1-inv2b.jsonl"
        rc2b, _run2b_dir, _sum2b, rec2b = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac1-both.json",
                "--execution-strategy", "scoped",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
                "--reuse-build-from", run1_rel,
            ],
            env_extra={
                "TEST_FIXTURE_INVOCATIONS": str(inv_log2b),
                "TEST_FIXTURE_FAIL_SUITE": "test_reward_input_journey",
            },
        )
        self.assertEqual(rc2b, 1)
        self.assertFalse(rec2b["automated_scope_passed"])
        self.assertFalse(rec2b["build_reuse_implies_test_pass"])
        by_id2b = {item["id"]: item for item in rec2b["executed_tests"]}
        self.assertTrue(by_id2b["reward-input"]["build_reuse"]["reused"])
        self.assertEqual(by_id2b["reward-input"]["status"], "failed")
        calls2b = [json.loads(line) for line in inv_log2b.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertTrue(all(not c["prewarm"] for c in calls2b if c["kind"] == "gdunit"))

        # 2c. When baseline gdunit suites are reused without staging prewarm, --challenge-input runs with prewarm=True!
        inv_chal = self.root / "logs/ci/ac1-chal.jsonl"
        rc_ch, _ch_dir, _sum_ch, rec_ch = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac1-both.json",
                "--execution-strategy", "scoped",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
                "--reuse-evidence-from", run1_rel,
                "--challenge-input",
            ],
            env_extra={"TEST_FIXTURE_INVOCATIONS": str(inv_chal)},
        )
        self.assertEqual(rc_ch, 0)
        chal_calls = [json.loads(line) for line in inv_chal.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(chal_calls), 1)
        self.assertTrue(chal_calls[0]["challenge"])
        self.assertTrue(chal_calls[0]["prewarm"])
        self.assertTrue(rec_ch["challenges"][0]["defect_detected"])

        # 3. Direct identity mismatch on a clean copy: dotnet + godot_prewarm source and toolchain version misses.
        snap_copy = self.aux_dir / "ac1-snap-copy"
        shutil.copytree(run1_dir / "snapshot", snap_copy)
        prior_rec = rec1["build_artifacts"]["dotnet_build"]
        mismatch_tc = evidence_reuse.evaluate_build_reuse(
            snap_copy,
            kind="dotnet_build",
            toolchain_env={**rec1["environment"], "dotnet_version": "9.0.100"},
            prior_build_record=prior_rec,
        )
        self.assertFalse(mismatch_tc["reused"])
        self.assertEqual(mismatch_tc["reason_code"], "build_toolchain_or_env_mismatch")
        (snap_copy / CONTRACT).write_text("public sealed class OfferLockSnapshot { public int V = 99; }\n", encoding="utf-8")
        mismatch_src = evidence_reuse.evaluate_build_reuse(
            snap_copy,
            kind="dotnet_build",
            toolchain_env=rec1["environment"],
            prior_build_record=prior_rec,
        )
        self.assertFalse(mismatch_src["reused"])
        self.assertEqual(mismatch_src["reason_code"], "build_source_digest_mismatch")

        # Godot prewarm toolchain version miss + source miss.
        prior_prewarm = rec1["build_artifacts"]["godot_prewarm"]
        snap_copy_gd = self.aux_dir / "ac1-snap-copy-gd"
        shutil.copytree(run1_dir / "snapshot", snap_copy_gd)
        mismatch_gd_ver = evidence_reuse.evaluate_build_reuse(
            snap_copy_gd,
            kind="godot_prewarm",
            toolchain_env={**rec1["environment"], "godot_version": "4.6.0.stable"},
            prior_build_record=prior_prewarm,
        )
        self.assertFalse(mismatch_gd_ver["reused"])
        self.assertEqual(mismatch_gd_ver["reason_code"], "build_toolchain_or_env_mismatch")
        (snap_copy_gd / SCENE).write_text(_valid_tscn() + "; changed\n", encoding="utf-8")
        mismatch_gd_src = evidence_reuse.evaluate_build_reuse(
            snap_copy_gd,
            kind="godot_prewarm",
            toolchain_env=rec1["environment"],
            prior_build_record=prior_prewarm,
        )
        self.assertFalse(mismatch_gd_src["reused"])
        self.assertEqual(mismatch_gd_src["reason_code"], "build_source_digest_mismatch")

    def test_ac2_multi_flow_shared_test_deduplicates_once_and_rejects_same_name_different_selector_or_input(self):
        fixture = _seed_repo(self.root, shared_test_across_flows=True)
        _build_scope(
            self.root,
            "logs/ci/scopes/ac2-shared.json",
            flows=[COMBAT, MAP_FLOW],
            plans=["P1", "P2"],
            change_roots=["state:OfferLock", "state:MapState"],
        )

        # 1. Intra-run multi-Flow shared test: reward-core is referenced by BOTH Flows, executed ONCE!
        inv1 = self.root / "logs/ci/ac2-inv1.jsonl"
        rc1, run1_dir, _sum1, rec1 = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac2-shared.json",
                "--execution-strategy", "scoped",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
            ],
            env_extra={"TEST_FIXTURE_INVOCATIONS": str(inv1)},
        )
        self.assertEqual(rc1, 0)
        calls1 = [json.loads(line) for line in inv1.read_text(encoding="utf-8").splitlines() if line.strip()]
        reward_core_calls = [c for c in calls1 if c.get("selector") == "Game.Core.Tests.Integration.RewardTests"]
        self.assertEqual(len(reward_core_calls), 1)

        by_id1 = {item["id"]: item for item in rec1["executed_tests"]}
        rc_entry = by_id1["reward-core"]
        self.assertEqual(rc_entry["referencing_flow_ids"], [COMBAT, MAP_FLOW])
        self.assertIn("FR-1", rc_entry["requirement_ids"])
        self.assertIn("Primary reward claim state", rc_entry["observable_roles"])
        self.assertIn("Post-claim map transition lock", rc_entry["observable_roles"])
        # Single-Flow reward-input MUST exclude MAP_FLOW Requirement route roles!
        ri_entry = by_id1["reward-input"]
        self.assertEqual(ri_entry["referencing_flow_ids"], [COMBAT])
        self.assertIn("Primary reward claim state", ri_entry["observable_roles"])
        self.assertNotIn("Post-claim map transition lock", ri_entry["observable_roles"])
        self.assertTrue(all(r["flow_id"] == COMBAT for r in ri_entry["requirement_routes"]))

        self.assertEqual(rec1["coverage_summary"]["unique_executed_test_count"], 5)  # static-wiring + 4 unique tests
        self.assertTrue(rec1["coverage_summary"]["flow_count_inflation_prevented"])
        self.assertGreater(
            rec1["coverage_summary"]["referencing_flow_link_count"],
            rec1["coverage_summary"]["unique_executed_test_count"],
        )

        # 2. Cross-run same-snapshot reuse: 0 child test processes invoked!
        inv2 = self.root / "logs/ci/ac2-inv2.jsonl"
        run1_rel = run1_dir.relative_to(self.root).as_posix()
        rc2, _run2_dir, _sum2, rec2 = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac2-shared.json",
                "--execution-strategy", "scoped",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
                "--reuse-evidence-from", run1_rel,
            ],
            env_extra={"TEST_FIXTURE_INVOCATIONS": str(inv2)},
        )
        self.assertEqual(rc2, 0)
        self.assertFalse(inv2.exists())
        self.assertEqual(rec2["reuse_summary"]["reused_test_count"], 4)
        self.assertEqual(rec2["metrics"]["observed_dispatches"], 0)
        self.assertEqual(rec2["metrics"]["reused_dispatches"], 4)

        # 2b. Narrow Flow-1 run -> wider Flow-1+2 run on SAME snapshot reuses Flow-1 tests via per-test relevant_paths!
        narrow_root = self.aux_dir / "ac2-narrow-to-wide"
        narrow_root.mkdir()
        narrow_fixture = _seed_repo(narrow_root, shared_test_across_flows=False)
        _build_scope(
            narrow_root,
            "logs/ci/scopes/narrow-flow1.json",
            flows=[COMBAT],
            plans=["P1"],
            change_roots=["state:OfferLock"],
        )
        _build_scope(
            narrow_root,
            "logs/ci/scopes/wide-flow12.json",
            flows=[COMBAT, MAP_FLOW],
            plans=["P1", "P2"],
            change_roots=["state:OfferLock", "state:MapState"],
        )
        rc_n1, run_n1_dir, _s_n1, rec_n1 = _run_mvg(
            narrow_root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/narrow-flow1.json",
                "--execution-strategy", "scoped",
                "--dotnet-bin", str(narrow_fixture),
                "--godot-bin", str(narrow_fixture),
            ],
        )
        self.assertEqual(rc_n1, 0)
        self.assertEqual(rec_n1["metrics"]["observed_dispatches"], 2)
        inv_wide = narrow_root / "logs/ci/ac2-wide.jsonl"
        rc_w, _run_w_dir, _s_w, rec_w = _run_mvg(
            narrow_root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/wide-flow12.json",
                "--execution-strategy", "scoped",
                "--dotnet-bin", str(narrow_fixture),
                "--godot-bin", str(narrow_fixture),
                "--reuse-evidence-from", run_n1_dir.relative_to(narrow_root).as_posix(),
            ],
            env_extra={"TEST_FIXTURE_INVOCATIONS": str(inv_wide)},
        )
        self.assertEqual(rc_w, 0)
        self.assertEqual(rec_w["reuse_summary"]["reused_test_count"], 2)
        self.assertEqual(sorted(rec_w["reuse_summary"]["reused_test_ids"]), ["reward-core", "reward-input"])
        self.assertEqual(rec_w["metrics"]["observed_dispatches"], 2)
        wide_calls = [json.loads(line) for line in inv_wide.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(wide_calls), 2)

        # 3. Reject same test_id when selector, path, min_tests, evidence_level, or authenticity differs!
        snap = run1_dir / "snapshot"
        base_id = copy.deepcopy(rc_entry["test_identity"])
        for label, mutate in [
            ("selector", lambda d: d.update(selector="Game.Core.Tests.Integration.OtherTests")),
            ("path", lambda d: d.update(path=MAP_CORE_TEST)),
            ("min_tests", lambda d: d.update(min_tests=3)),
            ("evidence_level", lambda d: d.update(evidence_level="scene-method")),
            ("real_runtime_vs_fixture", lambda d: d["verification_semantics"].update(protocol_fixture_only=False, evidence_authenticity="real_runtime")),
        ]:
            cand_id = copy.deepcopy(base_id)
            mutate(cand_id)
            cand_id["evidence_identity_id"] = codec.canonical_digest(cand_id)
            ev = evidence_reuse.evaluate_test_evidence_reuse(
                self.root,
                snap,
                test_spec={"id": "reward-core", "kind": "dotnet", "path": cand_id["path"], "selector": cand_id["selector"], "min_tests": cand_id["min_tests"]},
                current_identity=cand_id,
                candidate_run_dirs=[run1_rel],
                referencing_flow_ids=[COMBAT],
            )
            self.assertFalse(ev["reused"], f"Should reject mismatched {label}")
            self.assertTrue(ev["rejections"], f"Should record rejection for {label}")

    def test_ac3_per_test_mutable_state_isolation_across_order_and_reentry_and_manual_never_replaced(self):
        fixture = _seed_repo(self.root)
        _build_scope(
            self.root,
            "logs/ci/scopes/ac3-iso.json",
            flows=[COMBAT, MAP_FLOW],
            plans=["P1", "P2"],
            change_roots=["state:OfferLock", "state:MapState"],
        )

        # 1. Normal order + strict clean-state assertion inside every child process!
        inv1 = self.root / "logs/ci/ac3-inv1.jsonl"
        rc1, run1_dir, _sum1, rec1 = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac3-iso.json",
                "--execution-strategy", "scoped",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
            ],
            env_extra={
                "TEST_FIXTURE_INVOCATIONS": str(inv1),
                "TEST_FIXTURE_ASSERT_CLEAN_STATE": "1",
            },
        )
        self.assertEqual(rc1, 0)
        calls1 = [json.loads(line) for line in inv1.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len(calls1), 4)
        self.assertTrue(all(not c["leaked"] for c in calls1))
        self.assertEqual(len({c["appdata"] for c in calls1}), 4)
        self.assertEqual(len({c["temp"] for c in calls1}), 4)

        # 2. Legacy non-scope mode also isolates per-test APPDATA/TEMP cleanly on re-entry!
        inv_legacy = self.root / "logs/ci/ac3-legacy.jsonl"
        rc_leg, _leg_dir, _sum_leg, _ = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
            ],
            env_extra={
                "TEST_FIXTURE_INVOCATIONS": str(inv_legacy),
                "TEST_FIXTURE_ASSERT_CLEAN_STATE": "1",
            },
        )
        self.assertEqual(rc_leg, 0)
        leg_calls = [json.loads(line) for line in inv_legacy.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(len({c["appdata"] for c in leg_calls}), 4)
        self.assertTrue(all(not c["leaked"] for c in leg_calls))

        # 3. Reversed test order in a fresh repo also passes with zero inherited state.
        rev_root = self.aux_dir / "reversed"
        rev_root.mkdir()
        rev_fixture = _seed_repo(rev_root, reverse_tests=True)
        _build_scope(
            rev_root,
            "logs/ci/scopes/ac3-rev.json",
            flows=[COMBAT, MAP_FLOW],
            plans=["P1", "P2"],
            change_roots=["state:OfferLock", "state:MapState"],
        )
        rc_rev, _rev_dir, _sum_rev, _rec_rev = _run_mvg(
            rev_root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac3-rev.json",
                "--execution-strategy", "scoped",
                "--dotnet-bin", str(rev_fixture),
                "--godot-bin", str(rev_fixture),
            ],
            env_extra={"TEST_FIXTURE_ASSERT_CLEAN_STATE": "1"},
        )
        self.assertEqual(rc_rev, 0)

        # 4. Rogue test polluting tracked snapshot file fails closed & aborts downstream tests!
        rc_pol, _pol_dir, _sum_pol, rec_pol = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac3-iso.json",
                "--execution-strategy", "scoped",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
            ],
            env_extra={
                "TEST_FIXTURE_POLLUTE_SNAPSHOT_REL": CONTRACT,
                "TEST_FIXTURE_POLLUTE_SELECTOR": "Game.Core.Tests.Integration.MapRouteTests",
            },
        )
        self.assertEqual(rc_pol, 1)
        self.assertEqual(rec_pol["status"], "blocked")
        self.assertEqual(rec_pol["reason_code"], "mutable_test_state_pollution_detected")
        self.assertTrue(rec_pol["state_isolation"]["pollution_detected"])
        self.assertIn("map-core", rec_pol["state_isolation"]["polluted_tests"])
        self.assertTrue(any(nr["reason_code"] == "mutable_test_state_pollution_detected" for nr in rec_pol["not_run"]))

        # 5. Even when 100% of automated tests are reused, manual_obligations stay manual_pending!
        run1_rel = run1_dir.relative_to(self.root).as_posix()
        rc_reused, _re_dir, _sum_re, rec_re = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac3-iso.json",
                "--execution-strategy", "scoped",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
                "--reuse-evidence-from", run1_rel,
            ],
        )
        self.assertEqual(rc_reused, 0)
        self.assertFalse(rec_re["manual_satisfied_by_machine_reuse"])
        self.assertGreaterEqual(len(rec_re["manual_obligations"]), 1)
        for m in rec_re["manual_obligations"]:
            self.assertEqual(m["status"], "manual_pending")
            self.assertFalse(m["verified_by_runner"])

        # 6. Legitimate Windows junction Tests.Godot/Game.Godot -> ../Game.Godot + .gd.uid allowed;
        # foreign junction or unexpected file fails closed!
        iso_snap = self.aux_dir / "ac3-junction-snap"
        shutil.copytree(run1_dir / "snapshot", iso_snap)
        pre_h = evidence_reuse.capture_snapshot_file_hashes(iso_snap)
        # Create benign Godot 4.5 .gd.uid & ephemeral logs/reports dirs.
        (iso_snap / (INPUT_TEST + ".uid")).write_text("uid://fake123\n", encoding="utf-8")
        (iso_snap / "logs/e2e/run.log").parent.mkdir(parents=True, exist_ok=True)
        (iso_snap / "logs/e2e/run.log").write_text("ephemeral\n", encoding="utf-8")
        (iso_snap / "Tests.Godot/reports/r.xml").parent.mkdir(parents=True, exist_ok=True)
        (iso_snap / "Tests.Godot/reports/r.xml").write_text("<r/>\n", encoding="utf-8")
        if os.name == "nt":
            junc = iso_snap / "Tests.Godot" / "Game.Godot"
            target = iso_snap / "Game.Godot"
            proc_j = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(junc), str(target)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(proc_j.returncode, 0, proc_j.stderr or proc_j.stdout)
        iso_ok = evidence_reuse.verify_post_test_isolation(iso_snap, pre_h, self.aux_dir / "iso-step-ok")
        self.assertTrue(iso_ok["isolated"], iso_ok)
        self.assertFalse(iso_ok["pollution_detected"], iso_ok)
        self.assertFalse((iso_snap / "logs").exists())
        self.assertFalse((iso_snap / "Tests.Godot/reports").exists())

        if os.name == "nt":
            foreign_dir = self.aux_dir / "ac3-foreign-target"
            foreign_dir.mkdir(exist_ok=True)
            foreign_junc = iso_snap / "Tests.Godot" / "ForeignLink"
            proc_fj = subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(foreign_junc), str(foreign_dir)],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(proc_fj.returncode, 0, proc_fj.stderr or proc_fj.stdout)
            iso_bad = evidence_reuse.verify_post_test_isolation(iso_snap, pre_h, self.aux_dir / "iso-step-bad")
            self.assertFalse(iso_bad["isolated"])
            self.assertTrue(iso_bad["pollution_detected"])
            # Remove junctions cleanly before TemporaryDirectory cleanup.
            subprocess.run(["cmd", "/c", "rmdir", str(foreign_junc)], capture_output=True, check=False)
            subprocess.run(["cmd", "/c", "rmdir", str(iso_snap / "Tests.Godot" / "Game.Godot")], capture_output=True, check=False)

        # 7. Unscoped run_mvg_acceptance MUST fail closed (rc=1) when reuse/events flags are passed without --verification-scope!
        rc_unscoped, _u_dir, sum_u, _ = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
                "--reuse-evidence-from", run1_rel,
            ],
        )
        self.assertEqual(rc_unscoped, 1)
        self.assertEqual(sum_u["status"], "blocked")
        self.assertIn("--verification-scope", sum_u["reason"])

    def test_ac4_drift_cross_snapshot_corrupt_xml_and_planning_adoption_rejected_while_irrelevant_metadata_reuses(self):
        fixture = _seed_repo(self.root, extra_unscoped_task=True)
        _build_scope(
            self.root,
            "logs/ci/scopes/ac4-scope.json",
            flows=[COMBAT],
            plans=["P1"],
            change_roots=["state:OfferLock"],
        )
        rc1, run1_dir, _sum1, rec1 = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac4-scope.json",
                "--execution-strategy", "scoped",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
            ],
        )
        self.assertEqual(rc1, 0)
        run1_rel = run1_dir.relative_to(self.root).as_posix()

        # 1. Irrelevant change outside integration snapshot (new unrelated file under logs/**) still reuses!
        _write(self.root, "logs/unrelated/extra-note.txt", "disjoint log artifact\n")
        inv_irr = self.root / "logs/ci/ac4-irr.jsonl"
        rc_irr, _irr_dir, _sum_irr, rec_irr = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac4-scope.json",
                "--execution-strategy", "scoped",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
                "--reuse-evidence-from", run1_rel,
            ],
            env_extra={"TEST_FIXTURE_INVOCATIONS": str(inv_irr)},
        )
        self.assertEqual(rc_irr, 0)
        self.assertFalse(inv_irr.exists())
        self.assertEqual(rec_irr["reuse_summary"]["reused_test_count"], 2)

        # Copy snap1 cleanly (never mutate run1_dir/snapshot in place!) and verify tasks.json status-only change
        # does NOT change test_relevant_input_digest, AND end-to-end _run_mvg after tasks.json status-only change
        # keeps VerificationScope valid and hits --reuse-build-from while strictly preserving snapshot_digest checks!
        snap1 = run1_dir / "snapshot"
        snap1_copy = self.aux_dir / "ac4-snap1-copy"
        shutil.copytree(snap1, snap1_copy)
        t_spec = {"id": "reward-core", "kind": "dotnet", "path": CORE_TEST, "selector": "Game.Core.Tests.Integration.RewardTests", "min_tests": 1, "evidence_level": "domain-integration"}
        id_before = evidence_reuse.compute_test_evidence_identity(
            snap1_copy,
            test_spec=t_spec,
            snapshot_digest=rec1["snapshot_digest"],
            source_revision=rec1["source_revision"],
            workspace_dirty=rec1["workspace_dirty"],
            toolchain_env=rec1["environment"],
            verification_semantics={"evidence_authenticity": "protocol_fixture", "protocol_fixture_only": True},
        )
        tasks_p = snap1_copy / ".taskmaster/tasks/tasks.json"
        tdata = json.loads(tasks_p.read_text(encoding="utf-8"))
        tdata["master"]["tasks"][0]["status"] = "in-progress"
        tasks_p.write_text(json.dumps(tdata, indent=2) + "\n", encoding="utf-8")
        id_after = evidence_reuse.compute_test_evidence_identity(
            snap1_copy,
            test_spec=t_spec,
            snapshot_digest=rec1["snapshot_digest"],
            source_revision=rec1["source_revision"],
            workspace_dirty=rec1["workspace_dirty"],
            toolchain_env=rec1["environment"],
            verification_semantics={"evidence_authenticity": "protocol_fixture", "protocol_fixture_only": True},
        )
        self.assertEqual(id_before["test_relevant_input_digest"], id_after["test_relevant_input_digest"])

        # End-to-end _run_mvg after live tasks.json status-only change on an unrelated task:
        # scope stays valid & build/prewarm reuse hits while snapshot_digest remains strictly enforced!
        live_tasks_p = self.root / ".taskmaster/tasks/tasks.json"
        orig_tasks_text = live_tasks_p.read_text(encoding="utf-8")
        live_tdata = json.loads(orig_tasks_text)
        live_tdata["master"]["tasks"][-1]["status"] = "in-progress"
        live_tasks_p.write_text(json.dumps(live_tdata, indent=2) + "\n", encoding="utf-8")
        try:
            inv_st = self.root / "logs/ci/ac4-status-only.jsonl"
            rc_st, _st_dir, _sum_st, rec_st = _run_mvg(
                self.root,
                [
                    "--mode", "run",
                    "--manifest", REWARD_MANIFEST,
                    "--verification-scope", "logs/ci/scopes/ac4-scope.json",
                    "--execution-strategy", "scoped",
                    "--dotnet-bin", str(fixture),
                    "--godot-bin", str(fixture),
                    "--reuse-build-from", run1_rel,
                    "--reuse-evidence-from", run1_rel,
                ],
                env_extra={"TEST_FIXTURE_INVOCATIONS": str(inv_st)},
            )
            self.assertEqual(rc_st, 0)
            self.assertFalse(rec_st["drift"]["drift_detected"])
            self.assertEqual(rec_st["metrics"]["build_reuses"], 2)
            # Formal runtime snapshot check is never bypassed when workspace tasks.json changes snapshot_digest.
            self.assertTrue(any(r["reason_code"] == "snapshot_digest_mismatch" for r in rec_st["reuse_rejections"]))
        finally:
            live_tasks_p.write_text(orig_tasks_text, encoding="utf-8")

        # 2. Story 2.9 planning adoption receipt is strictly rejected as runtime evidence!
        adoption_rel = "logs/ci/fake-planning-adoption.json"
        _write(self.root, adoption_rel, {
            "schema_version": "newrouge.mvg-capability-adoption.v1",
            "operation_id": "op-2-9",
            "adopted": True,
        })
        rc_ad, _ad_dir, _sum_ad, rec_ad = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac4-scope.json",
                "--execution-strategy", "scoped",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
                "--reuse-evidence-from", adoption_rel,
                "--reuse-build-from", adoption_rel,
            ],
        )
        self.assertEqual(rc_ad, 0)
        self.assertFalse(rec_ad["planning_adoption_interchangeable"])
        self.assertEqual(rec_ad["reuse_summary"]["reused_test_count"], 0)
        self.assertTrue(
            any(r["reason_code"] == "planning_adoption_not_runtime_evidence" for r in rec_ad["reuse_rejections"])
        )

        # 3. Tampered raw .trx, missing .trx, tampered results.xml, sibling-report smuggling,
        # and summary-only (missing coverage-receipt.json) are ALL rejected!
        core_id = next(x["test_identity"] for x in rec1["executed_tests"] if x["id"] == "reward-core")
        input_id = next(x["test_identity"] for x in rec1["executed_tests"] if x["id"] == "reward-input")
        input_spec = {"id": "reward-input", "kind": "gdunit", "path": INPUT_TEST, "min_tests": 1, "evidence_level": "engine-input"}

        tampered_dir = self.root / "logs/ci/mvg-acceptance/tampered-xml-run"
        shutil.copytree(run1_dir, tampered_dir)
        tampered_trx = tampered_dir / "reward-core" / "results.trx"
        tampered_trx.write_text(
            '<TestRun><UnitTestResult testName="Game.Core.Tests.Integration.RewardTests.TestCase" outcome="Failed"/>'
            '<Counters total="1" passed="0" failed="1"/></TestRun>',
            encoding="utf-8",
        )
        tampered_xml = tampered_dir / "reward-input" / "current" / "report_1" / "results.xml"
        tampered_xml.write_text(
            '<testsuites tests="1"><testsuite name="test_reward_input_journey" tests="1" failures="1">'
            '<testcase classname="test_reward_input_journey" name="test_fail"><failure>bad</failure></testcase>'
            '</testsuite></testsuites>',
            encoding="utf-8",
        )
        t_rec = json.loads((tampered_dir / "coverage-receipt.json").read_text(encoding="utf-8"))
        for entry in t_rec["executed_tests"]:
            if entry["id"] == "reward-core":
                entry["report_paths"] = [str(tampered_trx)]
                entry["command_record"] = str(tampered_dir / "reward-core" / "command.json")
            elif entry["id"] == "reward-input":
                entry["report_paths"] = [str(tampered_xml)]
                entry["command_record"] = str(tampered_dir / "reward-input" / "command.json")
        scope_runner._seal_receipt(t_rec)
        (tampered_dir / "coverage-receipt.json").write_text(json.dumps(t_rec, indent=2) + "\n", encoding="utf-8")

        ev_tamper = evidence_reuse.evaluate_test_evidence_reuse(
            self.root,
            snap1,
            test_spec=t_spec,
            current_identity=core_id,
            candidate_run_dirs=[tampered_dir.relative_to(self.root).as_posix()],
            referencing_flow_ids=[COMBAT],
        )
        self.assertFalse(ev_tamper["reused"])
        self.assertEqual(ev_tamper["rejections"][0]["reason_code"], "corrupt_or_invalid_raw_report")

        # Tampered GdUnit results.xml rejected!
        ev_tamper_xml = evidence_reuse.evaluate_test_evidence_reuse(
            self.root,
            snap1,
            test_spec=input_spec,
            current_identity=input_id,
            candidate_run_dirs=[tampered_dir.relative_to(self.root).as_posix()],
            referencing_flow_ids=[COMBAT],
        )
        self.assertFalse(ev_tamper_xml["reused"])
        self.assertEqual(ev_tamper_xml["rejections"][0]["reason_code"], "corrupt_or_invalid_raw_report")

        # Missing .trx file rejected!
        tampered_trx.unlink()
        ev_missing_trx = evidence_reuse.evaluate_test_evidence_reuse(
            self.root,
            snap1,
            test_spec=t_spec,
            current_identity=core_id,
            candidate_run_dirs=[tampered_dir.relative_to(self.root).as_posix()],
            referencing_flow_ids=[COMBAT],
        )
        self.assertFalse(ev_missing_trx["reused"])
        self.assertEqual(ev_missing_trx["rejections"][0]["reason_code"], "corrupt_or_invalid_raw_report")

        # Sibling-run report smuggling (reused=False pointing at run1_dir's raw report) rejected!
        sibling_dir = self.root / "logs/ci/mvg-acceptance/sibling-smuggle-run"
        shutil.copytree(run1_dir, sibling_dir)
        s_rec = json.loads((sibling_dir / "coverage-receipt.json").read_text(encoding="utf-8"))
        for entry in s_rec["executed_tests"]:
            if entry["id"] == "reward-core":
                entry["command_record"] = str(sibling_dir / "reward-core" / "command.json")
                entry["report_paths"] = [str(run1_dir / "reward-core" / "results.trx")]
        scope_runner._seal_receipt(s_rec)
        (sibling_dir / "coverage-receipt.json").write_text(json.dumps(s_rec, indent=2) + "\n", encoding="utf-8")
        ev_sibling = evidence_reuse.evaluate_test_evidence_reuse(
            self.root,
            snap1,
            test_spec=t_spec,
            current_identity=core_id,
            candidate_run_dirs=[sibling_dir.relative_to(self.root).as_posix()],
            referencing_flow_ids=[COMBAT],
        )
        self.assertFalse(ev_sibling["reused"])
        self.assertEqual(ev_sibling["rejections"][0]["reason_code"], "corrupt_or_invalid_raw_report")

        # Missing coverage-receipt.json (unsealed summary.json-only directory) rejected!
        summary_only_dir = self.root / "logs/ci/mvg-acceptance/summary-only-run"
        shutil.copytree(run1_dir, summary_only_dir)
        (summary_only_dir / "coverage-receipt.json").unlink()
        ev_sum_only = evidence_reuse.evaluate_test_evidence_reuse(
            self.root,
            snap1,
            test_spec=t_spec,
            current_identity=core_id,
            candidate_run_dirs=[summary_only_dir.relative_to(self.root).as_posix()],
            referencing_flow_ids=[COMBAT],
        )
        self.assertFalse(ev_sum_only["reused"])
        self.assertEqual(ev_sum_only["rejections"][0]["reason_code"], "missing_prior_run_receipt")

        # Corrupt receipt seal is rejected too!
        corrupt_dir = self.root / "logs/ci/mvg-acceptance/corrupt-seal-run"
        shutil.copytree(run1_dir, corrupt_dir)
        c_rec = json.loads((corrupt_dir / "coverage-receipt.json").read_text(encoding="utf-8"))
        c_rec["receipt_id"] = "sha256:" + "f" * 64
        (corrupt_dir / "coverage-receipt.json").write_text(json.dumps(c_rec, indent=2) + "\n", encoding="utf-8")
        ev_corrupt = evidence_reuse.evaluate_test_evidence_reuse(
            self.root,
            snap1,
            test_spec=t_spec,
            current_identity=core_id,
            candidate_run_dirs=[corrupt_dir.relative_to(self.root).as_posix()],
            referencing_flow_ids=[COMBAT],
        )
        self.assertFalse(ev_corrupt["reused"])
        self.assertEqual(ev_corrupt["rejections"][0]["reason_code"], "corrupt_coverage_receipt")

        # 4. Relevant contract change -> new snapshot -> cross-snapshot splicing strictly rejected!
        _write(self.root, CONTRACT, "public sealed class OfferLockSnapshot { public int V = 2; }\n")
        _build_scope(
            self.root,
            "logs/ci/scopes/ac4-drifted.json",
            flows=[COMBAT],
            plans=["P1"],
            change_roots=["state:OfferLock"],
        )
        inv_drift = self.root / "logs/ci/ac4-drift.jsonl"
        rc_dr, _dr_dir, _sum_dr, rec_dr = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac4-drifted.json",
                "--execution-strategy", "scoped",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
                "--reuse-evidence-from", run1_rel,
            ],
            env_extra={"TEST_FIXTURE_INVOCATIONS": str(inv_drift)},
        )
        self.assertEqual(rc_dr, 0)
        self.assertEqual(rec_dr["reuse_summary"]["reused_test_count"], 0)
        self.assertTrue(inv_drift.exists())
        self.assertTrue(any(r["reason_code"] == "snapshot_digest_mismatch" for r in rec_dr["reuse_rejections"]))

    def test_ac5_original_pass_timestamp_preserved_events_deduplicated_and_cli_wired(self):
        fixture = _seed_repo(self.root)
        _build_scope(
            self.root,
            "logs/ci/scopes/ac5-scope.json",
            flows=[COMBAT],
            plans=["P1"],
            change_roots=["state:OfferLock"],
        )
        rc1, run1_dir, _sum1, rec1 = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac5-scope.json",
                "--execution-strategy", "scoped",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
            ],
        )
        self.assertEqual(rc1, 0)
        run1_by_id = {item["id"]: item for item in rec1["executed_tests"]}
        orig_core_ts = run1_by_id["reward-core"]["original_executed_at"]
        orig_input_ts = run1_by_id["reward-input"]["original_executed_at"]
        self.assertTrue(orig_core_ts)
        self.assertTrue(orig_input_ts)

        time.sleep(0.06)

        # Invoke end-to-end via dev_cli.py run-mvg-acceptance with --reuse-evidence-from & --events-log!
        run1_rel = run1_dir.relative_to(self.root).as_posix()
        events_rel = "logs/ci/story-4-4-events.jsonl"
        cmd = [
            sys.executable, "-B", str(SCRIPTS_PY / "dev_cli.py"),
            "run-mvg-acceptance",
            "--root", str(self.root),
            "--mode", "run",
            "--manifest", REWARD_MANIFEST,
            "--verification-scope", "logs/ci/scopes/ac5-scope.json",
            "--execution-strategy", "scoped",
            "--dotnet-bin", str(fixture),
            "--godot-bin", str(fixture),
            "--reuse-evidence-from", run1_rel,
            "--events-log", events_rel,
        ]
        proc2 = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", timeout=60, check=False)
        self.assertEqual(proc2.returncode, 0, proc2.stderr or proc2.stdout)
        cli2 = json.loads(proc2.stdout.strip().splitlines()[-1])
        rec2 = json.loads(Path(cli2["coverage_receipt"]).read_text(encoding="utf-8"))
        rec2_by_id = {item["id"]: item for item in rec2["executed_tests"]}

        # Original timestamps MUST be preserved verbatim (never refreshed to run2's finished_at!).
        self.assertTrue(rec2_by_id["reward-core"]["reused"])
        self.assertFalse(rec2_by_id["reward-core"]["freshly_executed"])
        self.assertEqual(rec2_by_id["reward-core"]["original_executed_at"], orig_core_ts)
        self.assertNotEqual(rec2_by_id["reward-core"]["original_executed_at"], rec2["finished_at"])
        self.assertEqual(rec2_by_id["reward-core"]["reused_from_run_id"], rec1["run_id"])
        self.assertEqual(rec2_by_id["reward-core"]["reused_evidence_id"], rec1["receipt_id"])
        self.assertEqual(rec2_by_id["reward-input"]["original_executed_at"], orig_input_ts)

        # All five Story 4.4 invariant flags must be False!
        for flag in (
            "build_reuse_implies_test_pass",
            "manual_satisfied_by_machine_reuse",
            "planning_adoption_interchangeable",
            "speedup_or_cost_gate_enforced",
            "reserved_budget_claimed_as_savings",
        ):
            self.assertIs(rec2[flag], False)

        events_file = self.root / events_rel
        lines_after_run2 = [json.loads(ln) for ln in events_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
        self.assertGreaterEqual(len(lines_after_run2), 3)

        # Re-run identical reuse against the SAME events-log -> zero duplicate event rows!
        proc3 = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", timeout=60, check=False)
        self.assertEqual(proc3.returncode, 0, proc3.stderr or proc3.stdout)
        cli3 = json.loads(proc3.stdout.strip().splitlines()[-1])
        rec3 = json.loads(Path(cli3["coverage_receipt"]).read_text(encoding="utf-8"))
        lines_after_run3 = [json.loads(ln) for ln in events_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
        self.assertEqual(len(lines_after_run3), len(lines_after_run2))
        self.assertGreater(rec3["reuse_summary"]["events_deduplicated"], 0)

        # Direct append_deduplicated_event check.
        ev_file = self.root / "logs/ci/direct-events.jsonl"
        sample = {"event_type": "test_evidence_reused", "test_id": "reward-core", "reused_evidence_id": "sha256:abc"}
        self.assertTrue(evidence_reuse.append_deduplicated_event(ev_file, sample))
        self.assertFalse(evidence_reuse.append_deduplicated_event(ev_file, sample))
        self.assertEqual(len([ln for ln in ev_file.read_text(encoding="utf-8").splitlines() if ln.strip()]), 1)

        # Verify dev_cli_builders forwards all Story 4.4 arguments cleanly.
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
            verification_scope="logs/ci/scopes/ac5-scope.json",
            execution_strategy="scoped",
            protocol_fixture=True,
            stop_on_deterministic_failure=True,
            reuse_evidence_from=[run1_rel, "logs/ci/mvg-acceptance/other"],
            reuse_build_from=run1_rel,
            events_log=events_rel,
        )
        built = dev_cli_builders.build_run_mvg_acceptance_cmd(ns)
        self.assertEqual(built.count("--reuse-evidence-from"), 2)
        self.assertIn("--reuse-build-from", built)
        self.assertIn("--events-log", built)

        # Reject non-.jsonl --events-log and empty --events-log (and verify dev_cli_builders forwards "").
        ns_empty = copy.deepcopy(ns)
        ns_empty.events_log = ""
        ns_empty.reuse_build_from = ""
        built_empty = dev_cli_builders.build_run_mvg_acceptance_cmd(ns_empty)
        self.assertIn("--events-log", built_empty)
        self.assertIn("--reuse-build-from", built_empty)

        rc_bad_ev, _bad_ev_dir, _bad_ev_sum, rec_bad_ev = _run_mvg(
            self.root,
            [
                "--mode", "run",
                "--manifest", REWARD_MANIFEST,
                "--verification-scope", "logs/ci/scopes/ac5-scope.json",
                "--dotnet-bin", str(fixture),
                "--godot-bin", str(fixture),
                "--events-log", "logs/ci/not-jsonl.json",
            ],
        )
        self.assertEqual(rc_bad_ev, 1)
        self.assertEqual(rec_bad_ev["reason_code"], "unsafe_path")


if __name__ == "__main__":
    unittest.main()
