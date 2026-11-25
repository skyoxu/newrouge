"""Story 4.5 completion verdict tests (AC-1..AC-5): separate Task-local, target-Flow,
cumulative full-MVG milestone, and legal non-Flow completion verification."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
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

import _b_route_chapter7_slice as ch7_slice  # noqa: E402
import _b_route_codec as codec  # noqa: E402
import _b_route_completion_verdict as cv  # noqa: E402
import _b_route_input_set as input_set_mod  # noqa: E402
import _b_route_scope_runner as scope_runner  # noqa: E402
import _b_route_verification_scope as vs  # noqa: E402
import dev_cli  # noqa: E402
import dev_cli_builders  # noqa: E402
import milestone_incremental_handoff as handoff_mod  # noqa: E402
from _mvg_manifest import manifest_sha256  # noqa: E402

CONTRACT = "Game.Core/Contracts/Offers/OfferLockSnapshot.cs"
MAP_CONTRACT = "Game.Core/Contracts/Map/MapRouteSnapshot.cs"
SHOP_CONTRACT = "Game.Core/Contracts/Shop/ShopOfferSnapshot.cs"
ADAPTER = "Game.Godot/Scripts/Reward/RewardOfferProvider.cs"
SCENE = "Game.Godot/Scenes/Reward.tscn"
INPUT_TEST = "Tests.Godot/tests/Integration/Mvg/test_reward_input_journey.gd"
MAP_SCENE_TEST = "Tests.Godot/tests/Integration/Mvg/test_map_scene.gd"
SHOP_SCENE_TEST = "Tests.Godot/tests/Integration/Mvg/test_shop_scene.gd"
CORE_TEST = "Game.Core.Tests/Integration/RewardTests.cs"
MAP_CORE_TEST = "Game.Core.Tests/Integration/MapRouteTests.cs"
SHOP_CORE_TEST = "Game.Core.Tests/Integration/ShopTests.cs"
NONFLOW_SCRIPT = "scripts/python/verify_nonflow_budget.py"
CATALOG = "docs/planning/b-route/catalog.v1.json"

FLOW_A = "combat-reward-return"
FLOW_B = "shop-purchase-flow"
FLOW_C = "map-route-flow"
FULL_MANIFEST = "docs/testing/mvg/m1-full.json"
PILOT_MANIFEST = "docs/testing/mvg/reward-pilot.json"


def _write(root: Path, rel: str, content: str | dict | list) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, (dict, list)):
        text = json.dumps(content, ensure_ascii=False, indent=2) + "\n"
    else:
        text = content
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    ).stdout.strip()


def _use(kind: str, definition_id: str, plan_id: str) -> dict:
    return {"kind": kind, "definition_id": definition_id, "owner_plan_id": plan_id, "owner_revision": 1}


def _owned(owner: str, ref: str, *paths: str) -> dict:
    digest = "sha256:" + "0" * 64
    return {"owner": owner, "ref": ref, "files": [{"path": p, "raw_digest": digest} for p in paths]}


def _ref(root: Path, schema: str, rel: str, entity_id: str, revision: int = 1) -> dict:
    doc = json.loads((root / rel).read_text(encoding="utf-8"))
    return {
        "path": rel,
        "schema_version": schema,
        "entity_id": entity_id,
        "revision": revision,
        "digest": codec.canonical_digest(doc),
        "verification_mode": "canonical",
        "codec_version": codec.CODEC_VERSION,
    }


def _seal_receipt(receipt: dict) -> dict:
    body = {k: v for k, v in receipt.items() if k not in scope_runner._VOLATILE_RECEIPT_FIELDS}
    receipt["receipt_id"] = codec.canonical_digest(body)
    return receipt


def _write_raw_trx(root: Path, run_dir_rel: str, step_id: str, selector: str, *, passed: int = 1, failed: int = 0, skipped: int = 0) -> str:
    rel = f"{run_dir_rel}/{step_id}/results.trx"
    total = passed + failed + skipped
    if total == 0:
        xml = '<TestRun><Counters total="0" passed="0" failed="0"/></TestRun>'
    else:
        outcome = "Passed" if (failed == 0 and skipped == 0) else ("Failed" if failed > 0 else "NotExecuted")
        xml = (
            f'<TestRun><UnitTestResult testName="{selector}.TestCase" outcome="{outcome}"/>'
            f'<Counters total="{total}" passed="{passed}" failed="{failed}" notExecuted="{skipped}"/></TestRun>'
        )
    _write(root, rel, xml)
    return rel


def _write_raw_gdunit_xml(root: Path, run_dir_rel: str, step_id: str, suite_name: str, *, tests: int = 1, failures: int = 0, skipped: int = 0) -> str:
    rel = f"{run_dir_rel}/{step_id}/results.xml"
    case_body = ""
    if tests > 0:
        if failures > 0:
            case_body = f'<testcase name="test_case" classname="{suite_name}"><failure message="failed"/></testcase>'
        elif skipped > 0:
            case_body = f'<testcase name="test_case" classname="{suite_name}"><skipped/></testcase>'
        else:
            case_body = f'<testcase name="test_case" classname="{suite_name}"/>'
    xml = f'<testsuites><testsuite name="{suite_name}" tests="{tests}" failures="{failures}" errors="0" skipped="{skipped}">{case_body}</testsuite></testsuites>'
    _write(root, rel, xml)
    return rel


def _make_receipt(
    root: Path,
    run_id: str,
    *,
    scope: dict,
    manifest_rel: str,
    snapshot_digest: str,
    source_revision: str,
    executed_tests: list[dict],
    workspace_dirty: bool = False,
    protocol_fixture_only: bool = False,
    runtime_verified: bool = True,
    not_run: list[dict] | None = None,
    manual_obligations: list[dict] | None = None,
    skipped_count: int = 0,
    drift_detected: bool = False,
    pollution_detected: bool = False,
) -> str:
    run_dir_rel = f"logs/ci/mvg-acceptance/{run_id}"
    m_sha = manifest_sha256((root / manifest_rel).read_bytes()) if (root / manifest_rel).is_file() else None
    passed_count = sum(1 for t in executed_tests if t.get("status") == "passed")
    failed_count = sum(1 for t in executed_tests if t.get("status") != "passed")
    not_run_list = list(not_run or [])
    receipt = {
        "schema_version": scope_runner.RECEIPT_SCHEMA,
        "receipt_id": "",
        "run_id": run_id,
        "scope_id": scope["scope_id"],
        "input_set_digest": scope["input_set_digest"],
        "manifest": manifest_rel,
        "manifest_sha256": m_sha,
        "source_revision": source_revision,
        "snapshot_digest": snapshot_digest,
        "workspace_dirty": workspace_dirty,
        "mode": "run",
        "status": "passed" if (failed_count == 0 and skipped_count == 0 and not drift_detected and not pollution_detected) else "failed",
        "reason_code": "ok" if failed_count == 0 else "failed",
        "reason": "ok" if failed_count == 0 else "failed",
        "automated_scope_passed": failed_count == 0 and skipped_count == 0,
        "runtime_verified": bool(runtime_verified) and not protocol_fixture_only and failed_count == 0,
        "execution_strategy_used": "scoped",
        "superset_executed": False,
        "selective_execution_claimed": True,
        "superset_extra_tests": [],
        "requested_tests": [t["id"] for t in executed_tests],
        "executed_tests": executed_tests,
        "not_run": not_run_list,
        "manual_obligations": list(manual_obligations or []),
        "out_of_scope_future_obligations": [],
        "challenges": [],
        "drift": {
            "pre_run_valid": True,
            "post_run_valid": not drift_detected,
            "drift_detected": drift_detected,
            "invalidated_obligations": [],
            "invalidated_flows": [],
            "replacement_scope_id": None,
        },
        "state_isolation": {
            "per_test_dirs_isolated": not pollution_detected,
            "pollution_detected": pollution_detected,
            "polluted_tests": ["polluted-test"] if pollution_detected else [],
            "checks": [],
        },
        "coverage_summary": {
            "requested_count": len(executed_tests) + len(not_run_list),
            "executed_count": len(executed_tests),
            "unique_executed_test_count": len(executed_tests),
            "passed_count": passed_count,
            "failed_count": failed_count,
            "skipped_count": skipped_count,
            "not_run_blocking_count": sum(1 for n in not_run_list if n.get("blocking_current_delivery")),
            "not_run_future_count": sum(1 for n in not_run_list if not n.get("blocking_current_delivery")),
            "manual_pending_count": len(manual_obligations or []),
            "all_requested_automated_passed": failed_count == 0 and skipped_count == 0,
        },
        "environment": {
            "protocol_fixture_only": protocol_fixture_only,
            "evidence_authenticity": "protocol_fixture" if protocol_fixture_only else "real_runtime",
        },
        "diagnostics": [],
        "generated_at": "2026-11-26T00:00:00Z",
        "finished_at": "2026-11-26T00:00:05Z",
    }
    _seal_receipt(receipt)
    _write(root, f"{run_dir_rel}/input-manifest.json", {
        "mode": "main",
        "source_revision": source_revision,
        "snapshot_digest": snapshot_digest,
        "files": {},
    })
    rel = f"{run_dir_rel}/coverage-receipt.json"
    _write(root, rel, receipt)
    return rel


def _seed_repo(
    root: Path,
    *,
    task114_status: str = "done",
    owner200_status: str = "in-progress",
    task84_status: str = "done",
    include_flow_b_in_manifest: bool = True,
    flow_b_implemented: bool = True,
    include_nonflow_plan: bool = False,
    task84_planned_new_test: bool = False,
) -> str:
    """Seed a clean git repo with B-route plans, bindings, catalog, tasks, and full/pilot manifests."""
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")

    _write(root, ".gitignore", "logs/\n")
    _write(root, "project.godot", '[application]\nconfig/name="newrouge"\n')
    _write(root, "Tests.Godot/project.godot", '[application]\nconfig/name="newrouge-tests"\n')
    _write(root, CONTRACT, "public sealed class OfferLockSnapshot { public int V = 1; }\n")
    _write(root, MAP_CONTRACT, "public sealed class MapRouteSnapshot { public int V = 1; }\n")
    _write(root, SHOP_CONTRACT, "public sealed class ShopOfferSnapshot { public int V = 1; }\n")
    _write(root, ADAPTER, "using Godot;\npublic partial class RewardOfferProvider : Control { public void OnClaimPressed() {} }\n")
    _write(root, SCENE, '[gd_scene load_steps=1 format=3]\n[node name="RewardRoot" type="Control"]\n')
    _write(root, INPUT_TEST, 'extends GdUnitTestSuite\nfunc test_reward_input():\n    var ev = InputEventAction.new()\n    get_viewport().push_input(ev)\n')
    _write(root, MAP_SCENE_TEST, "extends GdUnitTestSuite\nfunc test_map_scene():\n    assert_bool(true).is_true()\n")
    _write(root, SHOP_SCENE_TEST, "extends GdUnitTestSuite\nfunc test_shop_scene():\n    assert_bool(true).is_true()\n")
    _write(root, CORE_TEST, "public class RewardTests { [Fact] public void TestCase() {} }\n")
    _write(root, MAP_CORE_TEST, "public class MapRouteTests { [Fact] public void TestCase() {} }\n")
    _write(root, SHOP_CORE_TEST, "public class ShopTests { [Fact] public void TestCase() {} }\n")
    _write(root, NONFLOW_SCRIPT, "print('nonflow ok')\n")

    master_rows = [
        {"id": 84, "title": "Reward Core", "status": task84_status, "dependencies": []},
        {"id": 114, "title": "Reward UI", "status": task114_status, "dependencies": [84]},
        {"id": 60, "title": "Map Route", "status": "done", "dependencies": []},
        {"id": 70, "title": "Shop Core", "status": "done" if flow_b_implemented else "pending", "dependencies": []},
        {"id": 200, "title": "Dedicated Integration Owner", "status": owner200_status, "dependencies": []},
    ]
    _write(root, ".taskmaster/tasks/tasks.json", {"master": {"tasks": master_rows}})
    _write(root, ".taskmaster/tasks/tasks_back.json", [
        {"id": "B-84", "taskmaster_id": 84, "status": task84_status, "contractRefs": [CONTRACT], "overlay_refs": [], "test_refs": [CORE_TEST]},
        {"id": "B-60", "taskmaster_id": 60, "status": "done", "contractRefs": [MAP_CONTRACT], "overlay_refs": [], "test_refs": [MAP_CORE_TEST]},
        {"id": "B-70", "taskmaster_id": 70, "status": "done" if flow_b_implemented else "pending", "contractRefs": [SHOP_CONTRACT], "overlay_refs": [], "test_refs": [SHOP_CORE_TEST]},
    ])
    _write(root, ".taskmaster/tasks/tasks_gameplay.json", [
        {"id": "G-114", "taskmaster_id": 114, "status": task114_status, "contractRefs": [CONTRACT], "overlay_refs": [], "test_refs": [INPUT_TEST]},
        {"id": "G-60", "taskmaster_id": 60, "status": "done", "contractRefs": [MAP_CONTRACT], "overlay_refs": [], "test_refs": [MAP_SCENE_TEST]},
        {"id": "G-70", "taskmaster_id": 70, "status": "done" if flow_b_implemented else "pending", "contractRefs": [SHOP_CONTRACT], "overlay_refs": [], "test_refs": [SHOP_SCENE_TEST]},
        {"id": "G-200", "taskmaster_id": 200, "status": owner200_status, "contractRefs": [], "overlay_refs": [], "test_refs": []},
    ])

    p1 = {
        "schema_version": "newrouge.b-route-plan.v1",
        "plan_id": "P1",
        "revision": 1,
        "requirements": [
            {"requirement_id": "FR-1", "source_block_ids": ["SB-1"], "acceptance_intent": "claim reward", "non_task_sinks": []},
        ],
        "definitions": {
            "flows": [
                {
                    "id": FLOW_A,
                    "requirement_ids": ["FR-1"],
                    "source_block_ids": ["SB-1"],
                    "capability_ids": ["cap-reward"],
                    "state_owners": [_use("state", "OfferLock", "P1")],
                    "ui": {"applicability": "applicable", "scene_refs": [SCENE]},
                    "human_verification": {
                        "applicability": "applicable",
                        "checks": ["Verify reward claim feel on Windows"],
                    },
                },
            ],
            "commands": [{"id": "ClaimReward", "requirement_ids": ["FR-1"], "responsibility": "claim", "uses": [_use("state", "OfferLock", "P1")]}],
            "states": [{"id": "OfferLock", "requirement_ids": ["FR-1"], "responsibility": "lock", "uses": []}],
        },
        "applicability": [{"requirement_id": "FR-1", "disposition": "flow", "rationale": "primary flow", "other_verification_refs": []}],
        "requirement_verification": [{"requirement_id": "FR-1", "disposition": "flow", "primary_flow_id": FLOW_A}],
        "requirement_route_memberships": [{"requirement_id": "FR-1", "flow_id": FLOW_A, "observable_role": "Reward claim state"}],
    }
    p2 = {
        "schema_version": "newrouge.b-route-plan.v1",
        "plan_id": "P2",
        "revision": 1,
        "requirements": [
            {"requirement_id": "FR-60", "source_block_ids": ["SB-60"], "acceptance_intent": "map route", "non_task_sinks": []},
        ],
        "definitions": {
            "flows": [
                {
                    "id": FLOW_C,
                    "requirement_ids": ["FR-60"],
                    "source_block_ids": ["SB-60"],
                    "capability_ids": ["cap-map"],
                    "state_owners": [_use("state", "MapState", "P2")],
                },
            ],
            "commands": [],
            "states": [{"id": "MapState", "requirement_ids": ["FR-60"], "responsibility": "map", "uses": []}],
        },
        "applicability": [{"requirement_id": "FR-60", "disposition": "flow", "rationale": "map flow", "other_verification_refs": []}],
        "requirement_verification": [{"requirement_id": "FR-60", "disposition": "flow", "primary_flow_id": FLOW_C}],
        "requirement_route_memberships": [{"requirement_id": "FR-60", "flow_id": FLOW_C, "observable_role": "Map route advancement"}],
    }
    p3 = {
        "schema_version": "newrouge.b-route-plan.v1",
        "plan_id": "P3",
        "revision": 1,
        "requirements": [
            {"requirement_id": "FR-70", "source_block_ids": ["SB-70"], "acceptance_intent": "shop purchase", "non_task_sinks": []},
        ],
        "definitions": {
            "flows": [
                {
                    "id": FLOW_B,
                    "requirement_ids": ["FR-70"],
                    "source_block_ids": ["SB-70"],
                    "capability_ids": ["cap-shop"],
                    "state_owners": [_use("state", "OfferLock", "P1"), _use("state", "ShopState", "P3")],
                },
            ],
            "commands": [],
            "states": [{"id": "ShopState", "requirement_ids": ["FR-70"], "responsibility": "shop", "uses": [_use("state", "OfferLock", "P1")]}],
        },
        "applicability": [{"requirement_id": "FR-70", "disposition": "flow", "rationale": "shop flow", "other_verification_refs": []}],
        "requirement_verification": [{"requirement_id": "FR-70", "disposition": "flow", "primary_flow_id": FLOW_B}],
        "requirement_route_memberships": [{"requirement_id": "FR-70", "flow_id": FLOW_B, "observable_role": "Shop offer lock"}],
    }
    _write(root, "docs/planning/b-route/plans/P1.plan.v1.json", p1)
    _write(root, "docs/planning/b-route/plans/P2.plan.v1.json", p2)
    _write(root, "docs/planning/b-route/plans/P3.plan.v1.json", p3)

    p1_ref = _ref(root, "newrouge.b-route-plan.v1", "docs/planning/b-route/plans/P1.plan.v1.json", "P1")
    p2_ref = _ref(root, "newrouge.b-route-plan.v1", "docs/planning/b-route/plans/P2.plan.v1.json", "P2")
    p3_ref = _ref(root, "newrouge.b-route-plan.v1", "docs/planning/b-route/plans/P3.plan.v1.json", "P3")

    b1 = {
        "schema_version": "newrouge.b-route-binding.v1",
        "plan_id": "P1",
        "plan_ref": p1_ref,
        "binding_revision": 1,
        "stage": "5",
        "parts": [],
        "manifest_refs": [_owned("manifest", "reward-pilot", PILOT_MANIFEST)],
        "other_verification_refs": [],
        "task_mappings": [
            {"task_id": 84, "requirement_ids": ["FR-1"], "flow_ids": [FLOW_A], "role": "producer", "obligation_ids": ["OB-84-NEW"] if task84_planned_new_test else []},
            {"task_id": 114, "requirement_ids": ["FR-1"], "flow_ids": [FLOW_A], "role": "consumer"},
            {"task_id": 200, "requirement_ids": ["FR-1"], "flow_ids": [FLOW_A], "role": "integration_only_owner", "integration_only_owner": True},
        ],
        "contract_bindings": [{"contract_ref": CONTRACT, "flow_ids": [FLOW_A], "task_ids": [84, 114]}],
        "implementation_objects": (
            [
                {
                    "id": "reward-lock-v2",
                    "kind": "domain_service",
                    "availability": "planned",
                    "responsible_task_ids": [84],
                    "expected_type": "RewardLockV2",
                    "lifecycle": "domain",
                    "later_checks": ["type"],
                    "target_ref": None,
                }
            ]
            if task84_planned_new_test
            else []
        ),
        "obligations": (
            [
                {
                    "id": "OB-84-NEW",
                    "flow_ids": [FLOW_A],
                    "requirement_ids": ["FR-1"],
                    "task_ids": [84],
                    "test_ids": ["reward-core-new-planned"],
                    "responsibility": "new task 84 test obligation",
                    "verification_refs": [],
                }
            ]
            if task84_planned_new_test
            else []
        ),
    }
    b2 = {
        "schema_version": "newrouge.b-route-binding.v1",
        "plan_id": "P2",
        "plan_ref": p2_ref,
        "binding_revision": 1,
        "stage": "5",
        "parts": [],
        "manifest_refs": [_owned("manifest", "m1-full", FULL_MANIFEST)],
        "other_verification_refs": [],
        "implementation_objects": [],
        "task_mappings": [{"task_id": 60, "requirement_ids": ["FR-60"], "flow_ids": [FLOW_C], "role": "producer"}],
        "contract_bindings": [{"contract_ref": MAP_CONTRACT, "flow_ids": [FLOW_C], "task_ids": [60]}],
        "obligations": [],
    }
    b3 = {
        "schema_version": "newrouge.b-route-binding.v1",
        "plan_id": "P3",
        "plan_ref": p3_ref,
        "binding_revision": 1,
        "stage": "5",
        "parts": [],
        "manifest_refs": [_owned("manifest", "m1-full", FULL_MANIFEST)],
        "other_verification_refs": [],
        "implementation_objects": [],
        "task_mappings": [{"task_id": 70, "requirement_ids": ["FR-70"], "flow_ids": [FLOW_B], "role": "producer"}],
        "contract_bindings": [{"contract_ref": SHOP_CONTRACT, "flow_ids": [FLOW_B], "task_ids": [70]}],
        "obligations": (
            []
            if flow_b_implemented
            else [
                {
                    "id": "OB-SHOP-UNIMPL",
                    "flow_ids": [FLOW_B],
                    "requirement_ids": ["FR-70"],
                    "task_ids": [70],
                    "test_ids": ["shop-core-planned"],
                    "responsibility": "shop flow planned obligation",
                    "verification_refs": [],
                }
            ]
        ),
    }
    _write(root, "docs/planning/b-route/bindings/P1.binding.v1.json", b1)
    _write(root, "docs/planning/b-route/bindings/P2.binding.v1.json", b2)
    _write(root, "docs/planning/b-route/bindings/P3.binding.v1.json", b3)

    scope_heads = [
        {
            "scope_id": "S1",
            "plan_refs": [_ref(root, "newrouge.b-route-plan.v1", "docs/planning/b-route/plans/P1.plan.v1.json", "P1")],
            "binding_refs": [_ref(root, "newrouge.b-route-binding.v1", "docs/planning/b-route/bindings/P1.binding.v1.json", "P1")],
        },
        {
            "scope_id": "S2",
            "plan_refs": [_ref(root, "newrouge.b-route-plan.v1", "docs/planning/b-route/plans/P2.plan.v1.json", "P2")],
            "binding_refs": [_ref(root, "newrouge.b-route-binding.v1", "docs/planning/b-route/bindings/P2.binding.v1.json", "P2")],
        },
        {
            "scope_id": "S3",
            "plan_refs": [_ref(root, "newrouge.b-route-plan.v1", "docs/planning/b-route/plans/P3.plan.v1.json", "P3")],
            "binding_refs": [_ref(root, "newrouge.b-route-binding.v1", "docs/planning/b-route/bindings/P3.binding.v1.json", "P3")],
        },
    ]

    if include_nonflow_plan:
        p4 = {
            "schema_version": "newrouge.b-route-plan.v1",
            "plan_id": "P4",
            "revision": 1,
            "requirements": [
                {"requirement_id": "NFR-BUDGET", "source_block_ids": ["SB-NF"], "acceptance_intent": "budget check", "non_task_sinks": [NONFLOW_SCRIPT]},
            ],
            "definitions": {"flows": [], "commands": [], "states": []},
            "applicability": [
                {
                    "requirement_id": "NFR-BUDGET",
                    "disposition": "other_verification",
                    "rationale": "Governance script check outside player gameplay journey",
                    "other_verification_refs": [_owned("other_verification", NONFLOW_SCRIPT, NONFLOW_SCRIPT)],
                }
            ],
            "requirement_verification": [{"requirement_id": "NFR-BUDGET", "disposition": "other_verification", "verification_ref": NONFLOW_SCRIPT}],
            "requirement_route_memberships": [],
        }
        _write(root, "docs/planning/b-route/plans/P4.plan.v1.json", p4)
        p4_ref = _ref(root, "newrouge.b-route-plan.v1", "docs/planning/b-route/plans/P4.plan.v1.json", "P4")
        b4 = {
            "schema_version": "newrouge.b-route-binding.v1",
            "plan_id": "P4",
            "plan_ref": p4_ref,
            "binding_revision": 1,
            "stage": "5",
            "parts": [],
            "manifest_refs": [],
            "implementation_objects": [],
            "task_mappings": [],
            "contract_bindings": [],
            "other_verification_refs": [_owned("other_verification", NONFLOW_SCRIPT, NONFLOW_SCRIPT)],
            "obligations": [
                {
                    "id": "OB-NONFLOW-BUDGET",
                    "flow_ids": [],
                    "requirement_ids": ["NFR-BUDGET"],
                    "responsibility": "non-flow budget verification script",
                    "verification_refs": [_owned("other_verification", NONFLOW_SCRIPT, NONFLOW_SCRIPT)],
                }
            ],
        }
        _write(root, "docs/planning/b-route/bindings/P4.binding.v1.json", b4)
        scope_heads.append({
            "scope_id": "S4",
            "plan_refs": [_ref(root, "newrouge.b-route-plan.v1", "docs/planning/b-route/plans/P4.plan.v1.json", "P4")],
            "binding_refs": [_ref(root, "newrouge.b-route-binding.v1", "docs/planning/b-route/bindings/P4.binding.v1.json", "P4")],
        })

    _write(root, CATALOG, {"schema_version": "newrouge.b-route-catalog.v1", "scope_heads": scope_heads})

    # Pilot manifest (1 flow: FLOW_A)
    pilot_blockers = sorted(t for t, st in ((84, task84_status), (114, task114_status)) if st != "done")
    pilot_doc = {
        "schema_version": "newrouge.mvg-integration.v1",
        "mvg_id": "reward-pilot",
        "coverage": {
            "mode": "pilot",
            "scope_id": "reward-pilot",
            "required_flow_ids": [FLOW_A],
            "blocking_task_ids": pilot_blockers,
            "excluded_claims": ["Pilot covers reward flow only, not full milestone"],
        },
        "flows": [
            {
                "id": FLOW_A,
                "outcome": "Claim reward via engine input",
                "task_ids": [84, 114, 200],
                "requirement_ids": ["FR-1"],
                "source_paths": [CONTRACT, ADAPTER, SCENE],
                "test_ids": ["reward-core", "reward-input"],
                "handoffs": [
                    {
                        "producer_task": 84,
                        "consumer_task": 114,
                        "owner_task": 200,
                        "contract_ref": CONTRACT,
                        "behavior": "Reward offer locks and claims via engine input",
                        "test_ids": ["reward-core", "reward-input"],
                    }
                ],
            }
        ],
        "tests": [
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
            },
        ],
    }
    _write(root, PILOT_MANIFEST, pilot_doc)

    # Full manifest (3 flows: FLOW_A, FLOW_C, FLOW_B or third flow)
    third_flow_id = FLOW_B if include_flow_b_in_manifest else "continue-resume-flow"
    third_task_id = 70 if include_flow_b_in_manifest else 60
    full_blockers = sorted({
        t for t, st in (
            (84, task84_status),
            (114, task114_status),
            (60, "done"),
            (70, "done" if flow_b_implemented else "pending"),
        )
        if st != "done" and (t != 70 or include_flow_b_in_manifest)
    })
    full_doc = {
        "schema_version": "newrouge.mvg-integration.v1",
        "mvg_id": "m1-full",
        "coverage": {
            "mode": "full",
            "scope_id": "m1-full",
            "required_flow_ids": [FLOW_A, FLOW_C, third_flow_id],
            "blocking_task_ids": full_blockers,
            "excluded_claims": ["Manual playtest checks require explicit signoff"],
        },
        "flows": [
            pilot_doc["flows"][0],
            {
                "id": FLOW_C,
                "outcome": "Advance map route",
                "task_ids": [60],
                "requirement_ids": ["FR-60"],
                "source_paths": [MAP_CONTRACT],
                "test_ids": ["map-core", "map-scene"],
                "handoffs": [
                    {
                        "producer_task": 60,
                        "consumer_task": 60,
                        "owner_task": 60,
                        "contract_ref": MAP_CONTRACT,
                        "behavior": "Map state updates",
                        "test_ids": ["map-core", "map-scene"],
                    }
                ],
            },
            {
                "id": third_flow_id,
                "outcome": "Shop purchase or continue flow",
                "task_ids": [third_task_id],
                "requirement_ids": ["FR-70"] if include_flow_b_in_manifest else ["FR-60"],
                "source_paths": [SHOP_CONTRACT],
                "test_ids": ["shop-core", "shop-scene"],
                "handoffs": [
                    {
                        "producer_task": third_task_id,
                        "consumer_task": third_task_id,
                        "owner_task": third_task_id,
                        "contract_ref": SHOP_CONTRACT,
                        "behavior": "Shop purchase completes cleanly",
                        "test_ids": ["shop-core", "shop-scene"],
                    }
                ],
            },
        ],
        "tests": [
            pilot_doc["tests"][0],
            pilot_doc["tests"][1],
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
            {
                "id": "shop-core",
                "kind": "dotnet",
                "state": "implemented",
                "evidence_level": "domain-integration",
                "path": SHOP_CORE_TEST,
                "selector": "Game.Core.Tests.Integration.ShopTests",
                "min_tests": 1,
            },
            {
                "id": "shop-scene",
                "kind": "gdunit",
                "state": "implemented",
                "evidence_level": "scene-method",
                "path": SHOP_SCENE_TEST,
                "min_tests": 1,
            },
        ],
    }
    _write(root, FULL_MANIFEST, full_doc)

    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed story 4.5 test repo")
    return _git(root, "rev-parse", "HEAD")


def _build_full_passing_entries(root: Path, run_id: str, *, include_shop: bool = True, fail_ids: set[str] | None = None) -> list[dict]:
    fail_ids = fail_ids or set()
    run_dir = f"logs/ci/mvg-acceptance/{run_id}"
    entries: list[dict] = []

    def add_dotnet(tid: str, sel: str):
        failed = tid in fail_ids
        trx = _write_raw_trx(root, run_dir, tid, sel, passed=0 if failed else 1, failed=1 if failed else 0)
        entries.append({
            "id": tid,
            "kind": "dotnet",
            "evidence_level": "domain-xunit",
            "evidence_authenticity": "real_runtime",
            "status": "failed" if failed else "passed",
            "passed_cases": 0 if failed else 1,
            "failed_cases": 1 if failed else 0,
            "skipped_cases": 0,
            "report_paths": [trx],
            "command": ["dotnet", "test", "--filter", f"FullyQualifiedName~{sel}"],
            "input_authenticity": {"checked": False, "valid": True, "reason": "domain_xunit"},
        })

    def add_gdunit(tid: str, suite: str, level: str, *, player_input: bool = False):
        failed = tid in fail_ids
        xml = _write_raw_gdunit_xml(root, run_dir, tid, suite, tests=1, failures=1 if failed else 0)
        entries.append({
            "id": tid,
            "kind": "gdunit",
            "evidence_level": level,
            "evidence_authenticity": "real_runtime",
            "status": "failed" if failed else "passed",
            "passed_cases": 0 if failed else 1,
            "failed_cases": 1 if failed else 0,
            "skipped_cases": 0,
            "report_paths": [xml],
            "command": ["godot", "--add", f"{suite}.gd"],
            "input_authenticity": {
                "checked": level == "engine-input",
                "valid": True,
                "player_action_input_detected": player_input,
                "reason": "verified_real_input" if player_input else "scene_method",
            },
        })

    add_dotnet("reward-core", "Game.Core.Tests.Integration.RewardTests")
    add_gdunit("reward-input", "test_reward_input_journey", "engine-input", player_input=True)
    add_dotnet("map-core", "Game.Core.Tests.Integration.MapRouteTests")
    add_gdunit("map-scene", "test_map_scene", "scene-method", player_input=False)
    if include_shop:
        add_dotnet("shop-core", "Game.Core.Tests.Integration.ShopTests")
        add_gdunit("shop-scene", "test_shop_scene", "scene-method", player_input=False)
    return entries


def _write_ch7_report(
    root: Path,
    rel: str,
    flow_id: str,
    input_set_digest: str,
    *,
    ok: bool = True,
    task_ids: list[int] | None = None,
    manual_items: list[dict] | None = None,
) -> str:
    tis: dict[str, dict] = {}
    for tid in (task_ids if task_ids is not None else [84, 114]):
        live = input_set_mod.resolve_input_set(root, tid)
        if live.get("input_set_digest"):
            tis[str(tid)] = {
                "input_set_digest": live["input_set_digest"],
                "gate_ok": bool(ok),
            }
    _write(root, rel, {
        "schema_version": ch7_slice.SCHEMA,
        "ok": ok,
        "target_flow_id": flow_id,
        "input_set_digest": input_set_digest,
        "ui_applicability": "applicable",
        "task_input_sets": tis,
        "wiring_inspection": {
            "wiring_static_ok": ok,
            "scenes_inspected": [SCENE],
            "adapters_inspected": [ADAPTER],
            "findings": [] if ok else [{"code": "missing_signal"}],
        },
        "governed_gap_routing": [],
        "verified_items": [{"id": "ui-reward-claim"}],
        "pending_items": [] if ok else [{"id": "ui-reward-pending"}],
        "blocked_items": [],
        "manual_items": list(manual_items or []),
    })
    return rel


def _write_manual_signoff(
    root: Path,
    rel: str,
    scope: dict,
    snapshot_digest: str,
    *,
    status: str = "approved",
    notes: str = "Verified reward claim animation, layout, and controller input feel on Windows build.",
    reviewer: str = "qa-lead-alice",
    extra_manual_ids: list[str] | None = None,
) -> str:
    manual_ids = [
        m["manual_id"]
        for m in ((scope.get("execution_plan") or {}).get("manual_obligations") or [])
        if isinstance(m, dict) and m.get("manual_id")
    ]
    for eid in (extra_manual_ids or []):
        if eid not in manual_ids:
            manual_ids.append(eid)
    _write(root, rel, {
        "schema_version": cv.MANUAL_SIGNOFF_SCHEMA,
        "scope_id": scope["scope_id"],
        "snapshot_digest": snapshot_digest,
        "reviewer": reviewer,
        "entries": [
            {
                "manual_id": mid,
                "status": status,
                "notes": notes,
                "signed_at": "2026-11-26T00:05:00Z",
            }
            for mid in manual_ids
        ],
    })
    return rel


class CompletionVerdictTests(unittest.TestCase):
    def test_ac1_single_task_local_pass_satisfies_task_only_while_incomplete_flow_stays_blocked_with_missing_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            head = _seed_repo(root, task114_status="pending", owner200_status="in-progress")
            scope = vs.build_verification_scope(
                root,
                change_roots=[f"contract:{CONTRACT}"],
                in_scope_task_ids=[84],
                in_scope_flow_ids=[FLOW_A],
                manifest_paths=[PILOT_MANIFEST],
                report_path="logs/ci/scopes/ac1-scope.json",
            )
            self.assertTrue(scope["ok"], scope)

            # Only Task 84's local test reward-core ran and passed; reward-input & Task 114 & Ch7 & manual are missing.
            run_dir = "logs/ci/mvg-acceptance/run-ac1"
            trx = _write_raw_trx(root, run_dir, "reward-core", "Game.Core.Tests.Integration.RewardTests")
            receipt_rel = _make_receipt(
                root,
                "run-ac1",
                scope=scope,
                manifest_rel=PILOT_MANIFEST,
                snapshot_digest="sha256:" + "a" * 64,
                source_revision=head,
                executed_tests=[{
                    "id": "reward-core",
                    "kind": "dotnet",
                    "evidence_level": "domain-xunit",
                    "evidence_authenticity": "real_runtime",
                    "status": "passed",
                    "passed_cases": 1,
                    "failed_cases": 0,
                    "skipped_cases": 0,
                    "report_paths": [trx],
                    "command": ["dotnet", "test", "--filter", "FullyQualifiedName~Game.Core.Tests.Integration.RewardTests"],
                }],
            )

            verdict = cv.evaluate_completion_verdict(
                root,
                level="task",
                task_id=84,
                manifest_path=PILOT_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac1-scope.json",
                receipt_paths=[receipt_rel],
            )
            self.assertTrue(verdict["ok"], verdict)
            self.assertTrue(verdict["task_local_satisfied"])
            self.assertFalse(verdict["flow_completed"])
            self.assertEqual("pending", verdict["flow_status"])
            self.assertFalse(verdict["cumulative_full_mvg_completed"])
            self.assertFalse(verdict["milestone_completed"])
            missing = verdict["missing_flow_obligations"]
            self.assertIn(114, missing["missing_tasks"])
            self.assertNotIn(200, missing["missing_tasks"])  # dedicated integration owner exempted
            self.assertIn("reward-input", missing["missing_tests"])
            self.assertTrue(missing["missing_chapter7_slices"])
            self.assertTrue(missing["pending_manual_obligations"])

            # Pending/unverified sibling task_id=114 MUST fail task_local_satisfied (no fallback to Task 84's passed test!)
            v114 = cv.evaluate_completion_verdict(
                root,
                level="task",
                task_id=114,
                manifest_path=PILOT_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac1-scope.json",
                receipt_paths=[receipt_rel],
            )
            self.assertFalse(v114["ok"])
            self.assertFalse(v114["task_local_satisfied"])
            self.assertFalse(v114["flow_completed"])

            # Protocol-fixture receipt MUST NOT satisfy task_local_satisfied!
            run_dir_fix = "logs/ci/mvg-acceptance/run-ac1-fixture"
            trx_fix = _write_raw_trx(root, run_dir_fix, "reward-core", "Game.Core.Tests.Integration.RewardTests")
            rec_fix = _make_receipt(
                root,
                "run-ac1-fixture",
                scope=scope,
                manifest_rel=PILOT_MANIFEST,
                snapshot_digest="sha256:" + "a" * 64,
                source_revision=head,
                executed_tests=[{
                    "id": "reward-core",
                    "kind": "dotnet",
                    "evidence_level": "domain-xunit",
                    "evidence_authenticity": "protocol_fixture",
                    "status": "passed",
                    "passed_cases": 1,
                    "failed_cases": 0,
                    "skipped_cases": 0,
                    "report_paths": [trx_fix],
                    "command": ["dotnet", "test", "--filter", "FullyQualifiedName~Game.Core.Tests.Integration.RewardTests"],
                }],
                protocol_fixture_only=True,
                runtime_verified=False,
            )
            v84_fix = cv.evaluate_completion_verdict(
                root,
                level="task",
                task_id=84,
                manifest_path=PILOT_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac1-scope.json",
                receipt_paths=[rec_fix],
            )
            self.assertFalse(v84_fix["ok"])
            self.assertFalse(v84_fix["task_local_satisfied"])
            self.assertTrue(v84_fix["protocol_fixture_satisfied_only"])

        # Negative sub-case: old 'done' status in tasks.json CANNOT waive a planned current_new obligation on Task 84!
        with tempfile.TemporaryDirectory() as tmp2:
            root2 = Path(tmp2)
            head2 = _seed_repo(root2, task84_status="done", task114_status="done", task84_planned_new_test=True)
            scope2 = vs.build_verification_scope(
                root2,
                change_roots=[f"contract:{CONTRACT}"],
                in_scope_task_ids=[84],
                in_scope_flow_ids=[FLOW_A],
                manifest_paths=[PILOT_MANIFEST],
                report_path="logs/ci/scopes/ac1-planned-scope.json",
            )
            self.assertTrue(scope2["ok"], scope2)
            run_dir2 = "logs/ci/mvg-acceptance/run-ac1-planned"
            trx2 = _write_raw_trx(root2, run_dir2, "reward-core", "Game.Core.Tests.Integration.RewardTests")
            rec2 = _make_receipt(
                root2,
                "run-ac1-planned",
                scope=scope2,
                manifest_rel=PILOT_MANIFEST,
                snapshot_digest="sha256:" + "b" * 64,
                source_revision=head2,
                executed_tests=[{
                    "id": "reward-core",
                    "kind": "dotnet",
                    "evidence_level": "domain-xunit",
                    "evidence_authenticity": "real_runtime",
                    "status": "passed",
                    "passed_cases": 1,
                    "failed_cases": 0,
                    "skipped_cases": 0,
                    "report_paths": [trx2],
                    "command": ["dotnet", "test", "--filter", "FullyQualifiedName~Game.Core.Tests.Integration.RewardTests"],
                }],
            )
            verdict2 = cv.evaluate_completion_verdict(
                root2,
                level="task",
                task_id=84,
                manifest_path=PILOT_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac1-planned-scope.json",
                receipt_paths=[rec2],
            )
            self.assertFalse(verdict2["ok"])
            self.assertFalse(verdict2["task_local_satisfied"])
            self.assertFalse(verdict2["flow_completed"])

    def test_ac2_target_flow_completion_enforces_tier_non_substitution_manual_signoff_and_integration_owner_exemption(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            head = _seed_repo(root, task114_status="done", owner200_status="in-progress")
            scope = vs.build_verification_scope(
                root,
                change_roots=[f"contract:{CONTRACT}"],
                in_scope_task_ids=[84, 114, 200],
                in_scope_flow_ids=[FLOW_A],
                manifest_paths=[PILOT_MANIFEST],
                report_path="logs/ci/scopes/ac2-scope.json",
            )
            self.assertTrue(scope["ok"], scope)
            snap = "sha256:" + "1" * 64
            ch7_rel = _write_ch7_report(root, "logs/ci/ch7/reward-slice.json", FLOW_A, scope["input_set_digest"], ok=True)
            manual_rel = _write_manual_signoff(root, "logs/ci/manual/reward-signoff.json", scope, snap)

            # (a) Tier substitution forbidden: scene-method CANNOT satisfy engine-input!
            bad_entries = _build_full_passing_entries(root, "run-ac2-bad-tier", include_shop=False)
            for item in bad_entries:
                if item["id"] == "reward-input":
                    item["evidence_level"] = "scene-method"
                    item["input_authenticity"] = {"checked": False, "valid": True, "player_action_input_detected": False}
            bad_rec = _make_receipt(root, "run-ac2-bad-tier", scope=scope, manifest_rel=PILOT_MANIFEST, snapshot_digest=snap, source_revision=head, executed_tests=bad_entries)
            v_bad_tier = cv.evaluate_completion_verdict(
                root,
                level="flow",
                flow_id=FLOW_A,
                manifest_path=PILOT_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac2-scope.json",
                receipt_paths=[bad_rec],
                chapter7_slice_report=ch7_rel,
                manual_signoff_path=manual_rel,
            )
            self.assertFalse(v_bad_tier["ok"])
            self.assertFalse(v_bad_tier["flow_completed"])
            self.assertTrue(v_bad_tier["evidence_tier_violations"])
            self.assertEqual("evidence_tier_substitution_forbidden", v_bad_tier["reason"])

            # (b) Protocol fixture receipt CANNOT satisfy real runtime flow_completed!
            good_entries = _build_full_passing_entries(root, "run-ac2-fixture", include_shop=False)
            fixture_rec = _make_receipt(
                root, "run-ac2-fixture", scope=scope, manifest_rel=PILOT_MANIFEST,
                snapshot_digest=snap, source_revision=head, executed_tests=good_entries,
                protocol_fixture_only=True, runtime_verified=False,
            )
            v_fixture = cv.evaluate_completion_verdict(
                root,
                level="flow",
                flow_id=FLOW_A,
                manifest_path=PILOT_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac2-scope.json",
                receipt_paths=[fixture_rec],
                chapter7_slice_report=ch7_rel,
                manual_signoff_path=manual_rel,
            )
            self.assertFalse(v_fixture["ok"])
            self.assertTrue(v_fixture["protocol_fixture_satisfied_only"])
            self.assertFalse(v_fixture["runtime_verified"])
            self.assertFalse(v_fixture["flow_completed"])

            # (c) Real runtime WITHOUT manual signoff -> automated_flow_passed=True, manual_pending=True, flow_completed=False!
            real_entries = _build_full_passing_entries(root, "run-ac2-real", include_shop=False)
            real_rec = _make_receipt(
                root, "run-ac2-real", scope=scope, manifest_rel=PILOT_MANIFEST,
                snapshot_digest=snap, source_revision=head, executed_tests=real_entries,
                protocol_fixture_only=False, runtime_verified=True,
            )
            v_no_manual = cv.evaluate_completion_verdict(
                root,
                level="flow",
                flow_id=FLOW_A,
                manifest_path=PILOT_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac2-scope.json",
                receipt_paths=[real_rec],
                chapter7_slice_report=ch7_rel,
            )
            self.assertFalse(v_no_manual["ok"])
            self.assertTrue(v_no_manual["automated_flow_passed"])
            self.assertTrue(v_no_manual["manual_pending"])
            self.assertFalse(v_no_manual["flow_completed"])

            # (d) Real runtime + Ch7 + Manual signoff + dedicated integration owner 200 STILL in-progress -> PASS!
            v_pass = cv.evaluate_completion_verdict(
                root,
                level="flow",
                flow_id=FLOW_A,
                manifest_path=PILOT_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac2-scope.json",
                receipt_paths=[real_rec],
                chapter7_slice_report=ch7_rel,
                manual_signoff_path=manual_rel,
            )
            self.assertTrue(v_pass["ok"], v_pass)
            self.assertTrue(v_pass["flow_completed"])
            self.assertTrue(v_pass["runtime_verified"])
            self.assertIn(200, v_pass["dedicated_integration_owner_task_ids"])
            self.assertEqual([], v_pass["blocking_participant_task_ids"])
            self.assertFalse(v_pass["cumulative_full_mvg_completed"])
            self.assertEqual("single_flow", v_pass["verified_scope"])

            # (e) Forbidden manual note tokens ("skip" / "n/a") MUST be rejected; CJK substantive notes MUST be accepted!
            bad_skip_manual = _write_manual_signoff(
                root, "logs/ci/manual/bad-skip.json", scope, snap,
                notes="We decided to skip manual verification because tests looked fine.",
            )
            v_skip_note = cv.evaluate_completion_verdict(
                root, level="flow", flow_id=FLOW_A, manifest_path=PILOT_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac2-scope.json", receipt_paths=[real_rec],
                chapter7_slice_report=ch7_rel, manual_signoff_path=bad_skip_manual,
            )
            self.assertFalse(v_skip_note["ok"])
            self.assertEqual("semantic_error", v_skip_note["reason_code"])

            bad_na_manual = _write_manual_signoff(
                root, "logs/ci/manual/bad-na.json", scope, snap,
                notes="Marked as N/A for this verification run.",
            )
            v_na_note = cv.evaluate_completion_verdict(
                root, level="flow", flow_id=FLOW_A, manifest_path=PILOT_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac2-scope.json", receipt_paths=[real_rec],
                chapter7_slice_report=ch7_rel, manual_signoff_path=bad_na_manual,
            )
            self.assertFalse(v_na_note["ok"])
            self.assertEqual("semantic_error", v_na_note["reason_code"])

            cjk_manual = _write_manual_signoff(
                root, "logs/ci/manual/cjk-ok.json", scope, snap,
                reviewer="测试负责人张明",
                notes="已在真机环境逐项核验奖励领取手感与界面按钮响应无异常。",
            )
            v_cjk = cv.evaluate_completion_verdict(
                root, level="flow", flow_id=FLOW_A, manifest_path=PILOT_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac2-scope.json", receipt_paths=[real_rec],
                chapter7_slice_report=ch7_rel, manual_signoff_path=cjk_manual,
            )
            self.assertTrue(v_cjk["ok"], v_cjk)
            self.assertTrue(v_cjk["flow_completed"])

            # (f) static-wiring CANNOT substitute for scene-method on FLOW_C!
            scope_c = vs.build_verification_scope(
                root,
                change_roots=[f"contract:{MAP_CONTRACT}"],
                in_scope_task_ids=[60],
                in_scope_flow_ids=[FLOW_C],
                manifest_paths=[FULL_MANIFEST],
                report_path="logs/ci/scopes/ac2-flowc-scope.json",
            )
            self.assertTrue(scope_c["ok"], scope_c)
            sw_run = "run-ac2-sw-sub"
            sw_dir = f"logs/ci/mvg-acceptance/{sw_run}"
            sw_rep = f"{sw_dir}/static-wiring/report.json"
            _write(root, sw_rep, {"wiring_static_ok": True, "scenes_inspected": [SCENE], "adapters_inspected": [ADAPTER], "findings": []})
            map_trx = _write_raw_trx(root, sw_dir, "map-core", "Game.Core.Tests.Integration.MapRouteTests")
            rec_sw_sub = _make_receipt(
                root, sw_run, scope=scope_c, manifest_rel=FULL_MANIFEST,
                snapshot_digest=snap, source_revision=head,
                executed_tests=[
                    {
                        "id": "map-core", "kind": "dotnet", "evidence_level": "domain-xunit",
                        "evidence_authenticity": "real_runtime", "status": "passed",
                        "passed_cases": 1, "failed_cases": 0, "skipped_cases": 0, "report_paths": [map_trx],
                        "command": ["dotnet", "test", "--filter", "FullyQualifiedName~Game.Core.Tests.Integration.MapRouteTests"],
                    },
                    {
                        "id": "map-scene", "kind": "static-wiring", "evidence_level": "static-wiring",
                        "evidence_authenticity": "real_static_inspection", "status": "passed",
                        "passed_cases": 2, "failed_cases": 0, "skipped_cases": 0,
                        "log_path": sw_rep, "report_paths": [sw_rep],
                    },
                ],
            )
            v_sw_sub = cv.evaluate_completion_verdict(
                root, level="flow", flow_id=FLOW_C, manifest_path=FULL_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac2-flowc-scope.json", receipt_paths=[rec_sw_sub],
            )
            self.assertFalse(v_sw_sub["ok"])
            self.assertEqual("evidence_tier_substitution_forbidden", v_sw_sub["reason"])
            self.assertTrue(v_sw_sub["evidence_tier_violations"])

        # (g) Cross-source owner+consumer (pending) MUST block Flow (NOT exempted like pure integration_only_owner)!
        with tempfile.TemporaryDirectory() as tmp_oc:
            root_oc = Path(tmp_oc)
            head_oc = _seed_repo(root_oc, task114_status="done", owner200_status="pending")
            # Make Task 200 BOTH owner_task AND consumer_task in pilot manifest handoff!
            p_doc = json.loads((root_oc / PILOT_MANIFEST).read_text(encoding="utf-8"))
            p_doc["flows"][0]["handoffs"][0]["consumer_task"] = 200
            p_doc["coverage"]["blocking_task_ids"] = [200]
            _write(root_oc, PILOT_MANIFEST, p_doc)
            _git(root_oc, "add", "-A")
            _git(root_oc, "commit", "-q", "-m", "make 200 owner and consumer")
            head_oc = _git(root_oc, "rev-parse", "HEAD")

            scope_oc = vs.build_verification_scope(
                root_oc,
                change_roots=[f"contract:{CONTRACT}"],
                in_scope_task_ids=[84, 114, 200],
                in_scope_flow_ids=[FLOW_A],
                manifest_paths=[PILOT_MANIFEST],
                report_path="logs/ci/scopes/ac2-oc-scope.json",
            )
            self.assertTrue(scope_oc["ok"], scope_oc)
            snap_oc = "sha256:" + "9" * 64
            ch7_oc = _write_ch7_report(root_oc, "logs/ci/ch7/oc-slice.json", FLOW_A, scope_oc["input_set_digest"], ok=True)
            man_oc = _write_manual_signoff(root_oc, "logs/ci/manual/oc-manual.json", scope_oc, snap_oc)
            oc_entries = _build_full_passing_entries(root_oc, "run-ac2-oc", include_shop=False)
            rec_oc = _make_receipt(
                root_oc, "run-ac2-oc", scope=scope_oc, manifest_rel=PILOT_MANIFEST,
                snapshot_digest=snap_oc, source_revision=head_oc, executed_tests=oc_entries,
            )
            v_oc = cv.evaluate_completion_verdict(
                root_oc, level="flow", flow_id=FLOW_A, manifest_path=PILOT_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac2-oc-scope.json", receipt_paths=[rec_oc],
                chapter7_slice_report=ch7_oc, manual_signoff_path=man_oc,
            )
            self.assertFalse(v_oc["ok"])
            self.assertNotIn(200, v_oc["dedicated_integration_owner_task_ids"])
            self.assertIn(200, v_oc["blocking_participant_task_ids"])

    def test_ac3_cumulative_full_mvg_requires_full_mode_same_snapshot_and_rejects_cross_snapshot_splicing_or_partial(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            head = _seed_repo(root, task114_status="done", owner200_status="in-progress")
            scope_full = vs.build_verification_scope(
                root,
                change_roots=[f"contract:{CONTRACT}"],
                in_scope_task_ids=[84, 114, 60, 70, 200],
                in_scope_flow_ids=[FLOW_A, FLOW_C, FLOW_B],
                manifest_paths=[FULL_MANIFEST],
                cumulative_baseline_manifests=[FULL_MANIFEST],
                report_path="logs/ci/scopes/ac3-full-scope.json",
            )
            self.assertTrue(scope_full["ok"], scope_full)
            snap1 = "sha256:" + "2" * 64
            snap2 = "sha256:" + "3" * 64
            manual_rel = _write_manual_signoff(root, "logs/ci/manual/ac3-manual.json", scope_full, snap1)

            all_entries = _build_full_passing_entries(root, "run-ac3-full", include_shop=True)
            rec_full = _make_receipt(
                root, "run-ac3-full", scope=scope_full, manifest_rel=FULL_MANIFEST,
                snapshot_digest=snap1, source_revision=head, executed_tests=all_entries,
            )

            # (a) Non-full manifest (pilot) CANNOT claim cumulative full-MVG!
            v_pilot = cv.evaluate_completion_verdict(
                root,
                level="milestone",
                manifest_path=PILOT_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac3-full-scope.json",
                receipt_paths=[rec_full],
                manual_signoff_path=manual_rel,
            )
            self.assertFalse(v_pilot["ok"])
            self.assertEqual("pilot", v_pilot["verified_scope"])
            self.assertFalse(v_pilot["cumulative_full_mvg_completed"])
            self.assertFalse(v_pilot["milestone_completed"])

            # (b) Cross-snapshot splicing (snap1 + snap2) MUST fail closed with CONFLICT!
            part1_entries = _build_full_passing_entries(root, "run-ac3-part1", include_shop=False)
            rec_p1 = _make_receipt(
                root, "run-ac3-part1", scope=scope_full, manifest_rel=FULL_MANIFEST,
                snapshot_digest=snap1, source_revision=head, executed_tests=part1_entries[:2],
            )
            part2_entries = _build_full_passing_entries(root, "run-ac3-part2", include_shop=True)
            rec_p2 = _make_receipt(
                root, "run-ac3-part2", scope=scope_full, manifest_rel=FULL_MANIFEST,
                snapshot_digest=snap2, source_revision=head, executed_tests=part2_entries[2:],
            )
            v_splice = cv.evaluate_completion_verdict(
                root,
                level="milestone",
                manifest_path=FULL_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac3-full-scope.json",
                receipt_paths=[rec_p1, rec_p2],
                manual_signoff_path=manual_rel,
            )
            self.assertFalse(v_splice["ok"])
            self.assertTrue(v_splice["cross_snapshot_splicing_detected"])
            self.assertEqual("conflict", v_splice["reason_code"])
            self.assertEqual("cross_snapshot_report_splicing_forbidden", v_splice["reason"])
            self.assertFalse(v_splice["cumulative_full_mvg_completed"])
            self.assertFalse(v_splice["milestone_completed"])

            # (c) Dirty workspace receipt rejected with verified_scope="partial"!
            dirty_entries = _build_full_passing_entries(root, "run-ac3-dirty", include_shop=True)
            rec_dirty = _make_receipt(
                root, "run-ac3-dirty", scope=scope_full, manifest_rel=FULL_MANIFEST,
                snapshot_digest=snap1, source_revision=head, executed_tests=dirty_entries,
                workspace_dirty=True,
            )
            v_dirty = cv.evaluate_completion_verdict(
                root,
                level="milestone",
                manifest_path=FULL_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac3-full-scope.json",
                receipt_paths=[rec_dirty],
                manual_signoff_path=manual_rel,
            )
            self.assertFalse(v_dirty["ok"])
            self.assertEqual("partial", v_dirty["verified_scope"])
            self.assertFalse(v_dirty["cumulative_full_mvg_completed"])

            # (c2) Missing Chapter 7 UI closure MUST block level="milestone" when --chapter7-slice-report is omitted!
            v_no_ch7 = cv.evaluate_completion_verdict(
                root,
                level="milestone",
                manifest_path=FULL_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac3-full-scope.json",
                receipt_paths=[rec_full],
                manual_signoff_path=manual_rel,
            )
            self.assertFalse(v_no_ch7["ok"])
            self.assertEqual("partial", v_no_ch7["verified_scope"])
            self.assertFalse(v_no_ch7["milestone_completed"])
            self.assertTrue(v_no_ch7["missing_flow_obligations"]["missing_chapter7_slices"])
            self.assertFalse(v_no_ch7["flow_verdicts"][FLOW_A]["flow_completed"])

            # (d) Full mode + same clean snapshot (raw 64-hex without sha256: prefix!) + Ch7 + manual signoff -> PASS!
            raw_snap = "2" * 64
            ch7_full = _write_ch7_report(root, "logs/ci/ch7/ac3-full-slice.json", FLOW_A, scope_full["input_set_digest"], ok=True)
            manual_raw = _write_manual_signoff(root, "logs/ci/manual/ac3-raw-manual.json", scope_full, raw_snap)
            raw_entries = _build_full_passing_entries(root, "run-ac3-raw64", include_shop=True)
            rec_raw = _make_receipt(
                root, "run-ac3-raw64", scope=scope_full, manifest_rel=FULL_MANIFEST,
                snapshot_digest=raw_snap, source_revision=head, executed_tests=raw_entries,
            )
            v_full = cv.evaluate_completion_verdict(
                root,
                level="milestone",
                manifest_path=FULL_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac3-full-scope.json",
                receipt_paths=[rec_raw],
                chapter7_slice_report=ch7_full,
                manual_signoff_path=manual_raw,
            )
            self.assertTrue(v_full["ok"], v_full)
            self.assertEqual("full", v_full["verified_scope"])
            self.assertTrue(v_full["cumulative_full_mvg_completed"])
            self.assertTrue(v_full["milestone_completed"])
            self.assertTrue(v_full["runtime_verified"])
            self.assertIn(200, v_full["dedicated_integration_owner_task_ids"])

            # (e) Critical manifest reports verified_scope="critical" and CANNOT claim full-MVG!
            crit_rel = "docs/testing/mvg/m1-critical.json"
            full_doc_copy = json.loads((root / FULL_MANIFEST).read_text(encoding="utf-8"))
            crit_doc = copy.deepcopy(full_doc_copy)
            crit_doc["mvg_id"] = "m1-critical"
            crit_doc["coverage"]["mode"] = "critical"
            crit_doc["coverage"]["scope_id"] = "m1-critical"
            crit_doc["flows"] = crit_doc["flows"][:2]
            crit_doc["coverage"]["required_flow_ids"] = [FLOW_A, FLOW_C]
            crit_doc["tests"] = crit_doc["tests"][:4]
            _write(root, crit_rel, crit_doc)
            scope_crit = vs.build_verification_scope(
                root,
                change_roots=[f"contract:{CONTRACT}"],
                in_scope_task_ids=[84, 114, 60, 200],
                in_scope_flow_ids=[FLOW_A, FLOW_C],
                manifest_paths=[crit_rel],
                report_path="logs/ci/scopes/ac3-crit-scope.json",
            )
            self.assertTrue(scope_crit["ok"], scope_crit)
            crit_entries = _build_full_passing_entries(root, "run-ac3-crit", include_shop=False)
            rec_crit = _make_receipt(
                root, "run-ac3-crit", scope=scope_crit, manifest_rel=crit_rel,
                snapshot_digest=snap1, source_revision=head, executed_tests=crit_entries,
            )
            manual_crit = _write_manual_signoff(root, "logs/ci/manual/ac3-crit-manual.json", scope_crit, snap1)
            v_crit = cv.evaluate_completion_verdict(
                root,
                level="milestone",
                manifest_path=crit_rel,
                verification_scope_path="logs/ci/scopes/ac3-crit-scope.json",
                receipt_paths=[rec_crit],
                manual_signoff_path=manual_crit,
            )
            self.assertFalse(v_crit["ok"])
            self.assertEqual("critical", v_crit["verified_scope"])
            self.assertFalse(v_crit["cumulative_full_mvg_completed"])

    def test_ac4_milestone_handoff_blocks_failed_flow_a_preserves_out_of_scope_flow_b_until_in_scope_and_enforces_anti_weakening(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Flow B is NOT in the cumulative manifest yet (out_of_scope_future) and unimplemented.
            head = _seed_repo(root, task114_status="done", owner200_status="in-progress", include_flow_b_in_manifest=False, flow_b_implemented=False)

            # Build scope where Flow A & C are existing_required, Flow B is impacted via shared OfferLock state but out_of_scope_future!
            scope_out = vs.build_verification_scope(
                root,
                change_roots=[f"contract:{CONTRACT}", "state:P1:OfferLock"],
                in_scope_task_ids=[84, 114, 60, 200],
                in_scope_flow_ids=[FLOW_A, FLOW_C],
                manifest_paths=[FULL_MANIFEST],
                cumulative_baseline_manifests=[FULL_MANIFEST],
                report_path="logs/ci/scopes/ac4-out-scope.json",
            )
            self.assertTrue(scope_out["ok"], scope_out)
            snap = "sha256:" + "4" * 64
            manual_rel = _write_manual_signoff(root, "logs/ci/manual/ac4-manual.json", scope_out, snap)

            # (a) Old Flow A fails -> blocks Flow A & milestone; Flow B stays out_of_scope_future without premature impl!
            fail_entries = _build_full_passing_entries(root, "run-ac4-fail-a", include_shop=True, fail_ids={"reward-core"})
            rec_fail_a = _make_receipt(
                root, "run-ac4-fail-a", scope=scope_out, manifest_rel=FULL_MANIFEST,
                snapshot_digest=snap, source_revision=head, executed_tests=fail_entries,
            )
            v_fail = handoff_mod.validate_b_route_milestone_completion(
                root,
                verification_scope_path="logs/ci/scopes/ac4-out-scope.json",
                receipt_paths=[rec_fail_a],
                manifest_path=FULL_MANIFEST,
                manual_signoff_path=manual_rel,
            )
            self.assertFalse(v_fail["ok"])
            self.assertIn(FLOW_A, v_fail["failed_existing_flows"])
            self.assertFalse(v_fail["milestone_completed"])
            self.assertFalse(v_fail["forced_premature_future_implementation"])
            tracked_b = [f for f in v_fail["out_of_scope_future_tracked"] if f["flow_id"] == FLOW_B]
            self.assertEqual(1, len(tracked_b))
            self.assertFalse(tracked_b[0]["completed"])
            self.assertTrue(tracked_b[0]["follow_up_responsibilities"])

            # (b) Anti-weakening: trying to reclassify failing Flow A as planned/out_of_scope_future via delta is REJECTED!
            bad_delta = {
                "schema_version": vs.DELTA_SCHEMA,
                "changes": [
                    {
                        "action": "reclassify",
                        "target_type": "flow",
                        "target_id": FLOW_A,
                        "target_tier": "planned",
                        "reason": "Temporarily move failing reward flow to planned for green build",
                    }
                ],
            }
            _write(root, "logs/ci/scopes/bad-delta.json", bad_delta)
            weakened = vs.build_verification_scope(
                root,
                change_roots=[f"contract:{CONTRACT}"],
                in_scope_task_ids=[84, 114],
                in_scope_flow_ids=[FLOW_A],
                manifest_paths=[FULL_MANIFEST],
                cumulative_baseline_manifests=[FULL_MANIFEST],
                scope_delta="logs/ci/scopes/bad-delta.json",
            )
            self.assertFalse(weakened["ok"])

            # (c) Fix Flow A -> full cumulative milestone PASSES while Flow B remains out_of_scope_future (completed=False)!
            ch7_ac4 = _write_ch7_report(root, "logs/ci/ch7/ac4-slice.json", FLOW_A, scope_out["input_set_digest"], ok=True)
            pass_entries = _build_full_passing_entries(root, "run-ac4-pass-a", include_shop=True)
            rec_pass_a = _make_receipt(
                root, "run-ac4-pass-a", scope=scope_out, manifest_rel=FULL_MANIFEST,
                snapshot_digest=snap, source_revision=head, executed_tests=pass_entries,
            )
            ok_reg, reason_reg = handoff_mod.validate_milestone_regressions(
                root,
                {"required_regressions": ["reward-core", "reward-input"]},
                None,
                verification_scope_path="logs/ci/scopes/ac4-out-scope.json",
                receipt_paths=[rec_pass_a],
                manifest_path=FULL_MANIFEST,
                manual_signoff_path=manual_rel,
                chapter7_slice_report=ch7_ac4,
            )
            self.assertTrue(ok_reg, reason_reg)

            # (c2) Missing required_regressions in handoff MUST fail milestone verdict!
            ok_missing_reg, reason_missing_reg = handoff_mod.validate_milestone_regressions(
                root,
                {"required_regressions": ["reward-core", "missing-regression-test"]},
                None,
                verification_scope_path="logs/ci/scopes/ac4-out-scope.json",
                receipt_paths=[rec_pass_a],
                manifest_path=FULL_MANIFEST,
                manual_signoff_path=manual_rel,
                chapter7_slice_report=ch7_ac4,
            )
            self.assertFalse(ok_missing_reg)
            self.assertTrue(reason_missing_reg)

            # (c3) build_task_handoff & validate_task_handoff with verification_scope_path + drift rejection!
            cp_path = _write(root, "logs/ci/handoffs/ac4-change-plan.json", {
                "schema_version": handoff_mod.CHANGE_PLAN_SCHEMA,
                "source_identity": {"source_revision": head},
                "baseline_manifest": FULL_MANIFEST,
                "changes": [
                    {
                        "change_id": "CHG-84",
                        "action": "extend",
                        "target_task_id": "84",
                        "owner_task_id": "84",
                        "reopen_task": True,
                        "reason": "Extend reward lock behavior for milestone",
                        "requirement_ids": ["FR-1"],
                        "impact": {"tasks": ["84", "114"], "contracts": [CONTRACT]},
                        "verification": {
                            "required_regressions": ["reward-core", "reward-input"],
                            "planned_tests": ["reward-core"],
                            "manual_obligations": [],
                        },
                    }
                ],
            })
            rd_path = _write(root, "logs/ci/handoffs/ac4-readiness-84.json", {
                "schema_version": "newrouge.chapter5-readiness.v1",
                "task_id": "84",
                "closure_allowed": True,
                "input_fingerprint": "sha256:" + "8" * 64,
            })
            h_doc = handoff_mod.build_task_handoff(
                root,
                plan_path=cp_path,
                task_id="84",
                readiness_path=rd_path,
                verification_scope_path=root / "logs/ci/scopes/ac4-out-scope.json",
            )
            h_path = _write(root, "logs/ci/handoffs/ac4-handoff-84.json", h_doc)
            h_ok, h_reason, _ = handoff_mod.validate_task_handoff(root, h_path, "84")
            self.assertTrue(h_ok, h_reason)

            # Evaluate milestone verdict with validated milestone_handoff_path -> PASS!
            v_handoff_ok = cv.evaluate_completion_verdict(
                root,
                level="milestone",
                manifest_path=FULL_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac4-out-scope.json",
                receipt_paths=[rec_pass_a],
                chapter7_slice_report=ch7_ac4,
                manual_signoff_path=manual_rel,
                milestone_handoff_path="logs/ci/handoffs/ac4-handoff-84.json",
            )
            self.assertTrue(v_handoff_ok["ok"], v_handoff_ok)
            self.assertTrue(v_handoff_ok["milestone_completed"])

            # Mutate handoff scope_id -> validate_task_handoff AND verdict MUST reject drift!
            drifted_h = copy.deepcopy(h_doc)
            drifted_h["b_route_verification_scope"]["scope_id"] = "sha256:" + "0" * 64
            drifted_h_path = _write(root, "logs/ci/handoffs/ac4-handoff-drifted.json", drifted_h)
            dh_ok, dh_reason, _ = handoff_mod.validate_task_handoff(root, drifted_h_path, "84")
            self.assertFalse(dh_ok)
            self.assertEqual("milestone_handoff_scope_identity_drift", dh_reason)
            v_handoff_drift = cv.evaluate_completion_verdict(
                root,
                level="milestone",
                manifest_path=FULL_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac4-out-scope.json",
                receipt_paths=[rec_pass_a],
                chapter7_slice_report=ch7_ac4,
                manual_signoff_path=manual_rel,
                milestone_handoff_path="logs/ci/handoffs/ac4-handoff-drifted.json",
            )
            self.assertFalse(v_handoff_drift["ok"])
            self.assertEqual("input_stale", v_handoff_drift["reason_code"])

            # (d) Move Flow B into current delivery boundary -> unimplemented Flow B immediately blocks BOTH Flow B and milestone!
            scope_in = vs.build_verification_scope(
                root,
                change_roots=[f"contract:{CONTRACT}", "state:P1:OfferLock"],
                in_scope_task_ids=[84, 114, 60, 70, 200],
                in_scope_flow_ids=[FLOW_A, FLOW_C, FLOW_B],
                manifest_paths=[FULL_MANIFEST],
                cumulative_baseline_manifests=[FULL_MANIFEST],
                report_path="logs/ci/scopes/ac4-in-scope.json",
            )
            self.assertTrue(scope_in["ok"], scope_in)
            pass_entries_in = _build_full_passing_entries(root, "run-ac4-in-b", include_shop=True)
            rec_in = _make_receipt(
                root, "run-ac4-in-b", scope=scope_in, manifest_rel=FULL_MANIFEST,
                snapshot_digest=snap, source_revision=head, executed_tests=pass_entries_in,
            )
            manual_in = _write_manual_signoff(root, "logs/ci/manual/ac4-in-manual.json", scope_in, snap)
            v_in = handoff_mod.validate_b_route_milestone_completion(
                root,
                verification_scope_path="logs/ci/scopes/ac4-in-scope.json",
                receipt_paths=[rec_in],
                manifest_path=FULL_MANIFEST,
                manual_signoff_path=manual_in,
            )
            self.assertFalse(v_in["ok"])
            self.assertFalse(v_in["milestone_completed"])
            self.assertFalse(v_in["cumulative_full_mvg_completed"])
            self.assertIn(FLOW_B, v_in["flow_verdicts"])
            self.assertFalse(v_in["flow_verdicts"][FLOW_B]["flow_completed"])

    def test_ac5_corrupt_stale_empty_skipped_rejected_with_six_field_diagnostics_legal_nonflow_verified_and_zero_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            head = _seed_repo(root, task114_status="done", owner200_status="in-progress", include_nonflow_plan=True)
            tasks_sha_before = _sha_file(root / ".taskmaster/tasks/tasks.json")
            catalog_sha_before = _sha_file(root / CATALOG)

            scope = vs.build_verification_scope(
                root,
                change_roots=[f"contract:{CONTRACT}"],
                in_scope_task_ids=[84, 114, 200],
                in_scope_flow_ids=[FLOW_A],
                manifest_paths=[PILOT_MANIFEST],
                report_path="logs/ci/scopes/ac5-scope.json",
            )
            self.assertTrue(scope["ok"], scope)
            snap = "sha256:" + "5" * 64

            # (a) Tampered receipt seal rejected with 6-field Diagnostic
            good_entries = _build_full_passing_entries(root, "run-ac5-tamper", include_shop=False)
            rec_tamper = _make_receipt(
                root, "run-ac5-tamper", scope=scope, manifest_rel=PILOT_MANIFEST,
                snapshot_digest=snap, source_revision=head, executed_tests=good_entries,
            )
            tamper_doc = json.loads((root / rec_tamper).read_text(encoding="utf-8"))
            tamper_doc["reason"] = "tampered_after_seal"
            _write(root, rec_tamper, tamper_doc)
            v_tamper = cv.evaluate_completion_verdict(
                root, level="flow", flow_id=FLOW_A, manifest_path=PILOT_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac5-scope.json", receipt_paths=[rec_tamper],
            )
            self.assertFalse(v_tamper["ok"])
            self.assertEqual("digest_mismatch", v_tamper["reason_code"])
            d0 = v_tamper["diagnostics"][0]
            self.assertEqual({"reason_code", "stage", "entity_id", "expected", "actual", "resume_ref"}, set(d0.keys()))

            # (b) Empty TRX (0 tests) & skipped TRX rejected with 6-field Diagnostic
            run_empty = "logs/ci/mvg-acceptance/run-ac5-empty"
            empty_trx = _write_raw_trx(root, run_empty, "reward-core", "Game.Core.Tests.Integration.RewardTests", passed=0, failed=0, skipped=0)
            rec_empty = _make_receipt(
                root, "run-ac5-empty", scope=scope, manifest_rel=PILOT_MANIFEST,
                snapshot_digest=snap, source_revision=head,
                executed_tests=[{
                    "id": "reward-core", "kind": "dotnet", "evidence_level": "domain-xunit",
                    "evidence_authenticity": "real_runtime", "status": "passed",
                    "passed_cases": 1, "failed_cases": 0, "skipped_cases": 0, "report_paths": [empty_trx],
                    "command": ["dotnet", "test", "--filter", "FullyQualifiedName~Game.Core.Tests.Integration.RewardTests"],
                }],
            )
            v_empty = cv.evaluate_completion_verdict(
                root, level="flow", flow_id=FLOW_A, manifest_path=PILOT_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac5-scope.json", receipt_paths=[rec_empty],
            )
            self.assertFalse(v_empty["ok"])
            self.assertEqual({"reason_code", "stage", "entity_id", "expected", "actual", "resume_ref"}, set(v_empty["diagnostics"][0].keys()))

            run_skip = "logs/ci/mvg-acceptance/run-ac5-skip"
            skip_trx = _write_raw_trx(root, run_skip, "reward-core", "Game.Core.Tests.Integration.RewardTests", passed=0, failed=0, skipped=1)
            rec_skip = _make_receipt(
                root, "run-ac5-skip", scope=scope, manifest_rel=PILOT_MANIFEST,
                snapshot_digest=snap, source_revision=head,
                executed_tests=[{
                    "id": "reward-core", "kind": "dotnet", "evidence_level": "domain-xunit",
                    "evidence_authenticity": "real_runtime", "status": "passed",
                    "passed_cases": 1, "failed_cases": 0, "skipped_cases": 1, "report_paths": [skip_trx],
                    "command": ["dotnet", "test", "--filter", "FullyQualifiedName~Game.Core.Tests.Integration.RewardTests"],
                }],
                skipped_count=1,
            )
            v_skip = cv.evaluate_completion_verdict(
                root, level="flow", flow_id=FLOW_A, manifest_path=PILOT_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac5-scope.json", receipt_paths=[rec_skip],
            )
            self.assertFalse(v_skip["ok"])
            self.assertEqual("conflict", v_skip["reason_code"])

            # (b2) Empty & skipped GdUnit results.xml on disk MUST fail closed with 6-field Diagnostic!
            run_gd_empty = "logs/ci/mvg-acceptance/run-ac5-gd-empty"
            empty_xml = _write_raw_gdunit_xml(root, run_gd_empty, "reward-input", "test_reward_input_journey", tests=0, failures=0, skipped=0)
            rec_gd_empty = _make_receipt(
                root, "run-ac5-gd-empty", scope=scope, manifest_rel=PILOT_MANIFEST,
                snapshot_digest=snap, source_revision=head,
                executed_tests=[{
                    "id": "reward-input", "kind": "gdunit", "evidence_level": "engine-input",
                    "evidence_authenticity": "real_runtime", "status": "passed",
                    "passed_cases": 1, "failed_cases": 0, "skipped_cases": 0, "report_paths": [empty_xml],
                    "command": ["godot", "--add", "test_reward_input_journey.gd"],
                    "input_authenticity": {"checked": True, "valid": True, "player_action_input_detected": True},
                }],
            )
            v_gd_empty = cv.evaluate_completion_verdict(
                root, level="flow", flow_id=FLOW_A, manifest_path=PILOT_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac5-scope.json", receipt_paths=[rec_gd_empty],
            )
            self.assertFalse(v_gd_empty["ok"])
            self.assertEqual({"reason_code", "stage", "entity_id", "expected", "actual", "resume_ref"}, set(v_gd_empty["diagnostics"][0].keys()))

            run_gd_skip = "logs/ci/mvg-acceptance/run-ac5-gd-skip"
            skip_xml = _write_raw_gdunit_xml(root, run_gd_skip, "reward-input", "test_reward_input_journey", tests=1, failures=0, skipped=1)
            rec_gd_skip = _make_receipt(
                root, "run-ac5-gd-skip", scope=scope, manifest_rel=PILOT_MANIFEST,
                snapshot_digest=snap, source_revision=head,
                executed_tests=[{
                    "id": "reward-input", "kind": "gdunit", "evidence_level": "engine-input",
                    "evidence_authenticity": "real_runtime", "status": "passed",
                    "passed_cases": 1, "failed_cases": 0, "skipped_cases": 0, "report_paths": [skip_xml],
                    "command": ["godot", "--add", "test_reward_input_journey.gd"],
                    "input_authenticity": {"checked": True, "valid": True, "player_action_input_detected": True},
                }],
            )
            v_gd_skip = cv.evaluate_completion_verdict(
                root, level="flow", flow_id=FLOW_A, manifest_path=PILOT_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac5-scope.json", receipt_paths=[rec_gd_skip],
            )
            self.assertFalse(v_gd_skip["ok"])
            self.assertEqual({"reason_code", "stage", "entity_id", "expected", "actual", "resume_ref"}, set(v_gd_skip["diagnostics"][0].keys()))

            # (c) Pure legal non-Flow verification (level="non_flow") passes with runtime_verified=False!
            nf_scope = vs.build_verification_scope(
                root,
                change_roots=["requirement:NFR-BUDGET"],
                in_scope_plan_ids=["P4"],
                report_path="logs/ci/scopes/ac5-nonflow-scope.json",
            )
            self.assertTrue(nf_scope["ok"], nf_scope)
            ov_log = "logs/ci/mvg-acceptance/run-ac5-nf/other-ov/console.log"
            _write(root, ov_log, "nonflow ok\n")
            ov_oids = [
                o["obligation_id"]
                for o in nf_scope["obligations"]
                if o.get("execution_kind") == "other_verification" or o.get("evidence_level") == "other-verification"
            ]
            self.assertTrue(ov_oids, nf_scope["obligations"])
            rec_nf = _make_receipt(
                root, "run-ac5-nf", scope=nf_scope, manifest_rel=PILOT_MANIFEST,
                snapshot_digest=snap, source_revision=head,
                runtime_verified=False,
                protocol_fixture_only=False,
                executed_tests=[{
                    "id": NONFLOW_SCRIPT,
                    "obligation_id": ov_oids[0],
                    "obligation_ids": ov_oids,
                    "kind": "other_verification",
                    "evidence_level": "other-verification",
                    "evidence_authenticity": "real_runtime",
                    "status": "passed",
                    "exit_code": 0,
                    "passed_cases": 1,
                    "failed_cases": 0,
                    "skipped_cases": 0,
                    "log_path": ov_log,
                    "script_path": NONFLOW_SCRIPT,
                }],
            )
            v_nf = cv.evaluate_completion_verdict(
                root,
                level="non_flow",
                verification_scope_path="logs/ci/scopes/ac5-nonflow-scope.json",
                receipt_paths=[rec_nf],
                report_path="logs/ci/verdicts/ac5-nonflow-report.json",
                events_log_path="logs/ci/verdicts/ac5-events.jsonl",
            )
            self.assertTrue(v_nf["ok"], v_nf)
            self.assertTrue(v_nf["non_flow_completed"])
            self.assertFalse(v_nf["runtime_verified"])
            self.assertEqual("non_flow", v_nf["verified_scope"])
            self.assertFalse(v_nf["task_status_mutated"])
            self.assertFalse(v_nf["catalog_mutated"])
            self.assertFalse(v_nf["publish_pointer_mutated"])
            self.assertFalse(v_nf["default_b_enabled"])
            self.assertTrue((root / "logs/ci/verdicts/ac5-nonflow-report.json").is_file())

            # Deduplicated event log: re-running same verdict does NOT append duplicate line!
            v_nf_dup = cv.evaluate_completion_verdict(
                root,
                level="non_flow",
                verification_scope_path="logs/ci/scopes/ac5-nonflow-scope.json",
                receipt_paths=[rec_nf],
                events_log_path="logs/ci/verdicts/ac5-events.jsonl",
            )
            self.assertTrue(v_nf_dup["ok"])
            ev_lines = [ln for ln in (root / "logs/ci/verdicts/ac5-events.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
            self.assertEqual(1, len(ev_lines))

            # Non-Flow impacting an MVG Flow blocks when impacted MVG regression is missing OR runtime_verified=False,
            # and passes ONLY when runtime_verified=True + impacted MVG tests + manual signoff are satisfied!
            nf_impact_scope = vs.build_verification_scope(
                root,
                change_roots=["requirement:NFR-BUDGET", f"contract:{CONTRACT}"],
                in_scope_plan_ids=["P4"],
                manifest_paths=[PILOT_MANIFEST],
                report_path="logs/ci/scopes/ac5-nonflow-impacted-scope.json",
            )
            self.assertTrue(nf_impact_scope["ok"], nf_impact_scope)
            ov_log2 = "logs/ci/mvg-acceptance/run-ac5-nf-imp/other-ov/console.log"
            _write(root, ov_log2, "nonflow ok\n")
            ov_oids2 = [
                o["obligation_id"]
                for o in nf_impact_scope["obligations"]
                if o.get("execution_kind") == "other_verification" or o.get("evidence_level") == "other-verification"
            ]
            self.assertTrue(ov_oids2, nf_impact_scope["obligations"])
            rec_nf_imp = _make_receipt(
                root, "run-ac5-nf-imp", scope=nf_impact_scope, manifest_rel=PILOT_MANIFEST,
                snapshot_digest=snap, source_revision=head,
                executed_tests=[{
                    "id": NONFLOW_SCRIPT,
                    "obligation_id": ov_oids2[0],
                    "obligation_ids": ov_oids2,
                    "kind": "other_verification",
                    "evidence_level": "other-verification",
                    "evidence_authenticity": "real_runtime",
                    "status": "passed",
                    "exit_code": 0,
                    "passed_cases": 1,
                    "failed_cases": 0,
                    "skipped_cases": 0,
                    "log_path": ov_log2,
                    "script_path": NONFLOW_SCRIPT,
                }],
            )
            v_nf_imp = cv.evaluate_completion_verdict(
                root,
                level="non_flow",
                verification_scope_path="logs/ci/scopes/ac5-nonflow-impacted-scope.json",
                receipt_paths=[rec_nf_imp],
            )
            self.assertFalse(v_nf_imp["ok"])
            self.assertIn(FLOW_A, v_nf_imp["failed_existing_flows"])

            # Now provide impacted MVG tests with runtime_verified=False -> MUST STILL BLOCK!
            imp_entries_no_rt = _build_full_passing_entries(root, "run-ac5-nf-imp-nort", include_shop=False)[:2]
            ov_log3 = "logs/ci/mvg-acceptance/run-ac5-nf-imp-nort/other-ov/console.log"
            _write(root, ov_log3, "nonflow ok\n")
            imp_entries_no_rt.append({
                "id": NONFLOW_SCRIPT, "obligation_id": ov_oids2[0], "obligation_ids": ov_oids2,
                "kind": "other_verification", "evidence_level": "other-verification",
                "evidence_authenticity": "real_runtime", "status": "passed", "exit_code": 0,
                "passed_cases": 1, "failed_cases": 0, "skipped_cases": 0,
                "log_path": ov_log3, "script_path": NONFLOW_SCRIPT,
            })
            rec_nf_nort = _make_receipt(
                root, "run-ac5-nf-imp-nort", scope=nf_impact_scope, manifest_rel=PILOT_MANIFEST,
                snapshot_digest=snap, source_revision=head,
                runtime_verified=False,
                executed_tests=imp_entries_no_rt,
            )
            manual_nf_imp = _write_manual_signoff(root, "logs/ci/manual/nf-imp-manual.json", nf_impact_scope, snap)
            v_nf_nort = cv.evaluate_completion_verdict(
                root, level="non_flow", manifest_path=PILOT_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac5-nonflow-impacted-scope.json",
                receipt_paths=[rec_nf_nort], manual_signoff_path=manual_nf_imp,
            )
            self.assertFalse(v_nf_nort["ok"])
            self.assertEqual("flow_impacting_non_flow_requires_real_runtime_verified_receipt", v_nf_nort["reason"])

            # End-to-end subprocess dev_cli.py b-route-completion-verdict: rc=0, rc=1, --apply rc=2
            proc_ok = subprocess.run(
                [
                    sys.executable, "-B", str(SCRIPTS_PY / "dev_cli.py"),
                    "b-route-completion-verdict",
                    "--root", str(root),
                    "--level", "non_flow",
                    "--verification-scope", "logs/ci/scopes/ac5-nonflow-scope.json",
                    "--receipt", rec_nf,
                ],
                capture_output=True, text=True, check=False, timeout=30,
            )
            self.assertEqual(0, proc_ok.returncode, proc_ok.stderr + proc_ok.stdout)
            ok_out = json.loads(proc_ok.stdout)
            self.assertTrue(ok_out["non_flow_completed"])
            self.assertFalse(ok_out["runtime_verified"])

            proc_fail = subprocess.run(
                [
                    sys.executable, "-B", str(SCRIPTS_PY / "dev_cli.py"),
                    "b-route-completion-verdict",
                    "--root", str(root),
                    "--level", "non_flow",
                    "--verification-scope", "logs/ci/scopes/ac5-nonflow-impacted-scope.json",
                    "--receipt", rec_nf_imp,
                ],
                capture_output=True, text=True, check=False, timeout=30,
            )
            self.assertEqual(1, proc_fail.returncode, proc_fail.stderr + proc_fail.stdout)

            proc_apply = subprocess.run(
                [
                    sys.executable, "-B", str(SCRIPTS_PY / "dev_cli.py"),
                    "b-route-completion-verdict",
                    "--root", str(root),
                    "--level", "non_flow",
                    "--apply",
                ],
                capture_output=True, text=True, check=False, timeout=30,
            )
            self.assertEqual(2, proc_apply.returncode, proc_apply.stderr + proc_apply.stdout)

            # (d) Stale VerificationScope rejected after mutating contract
            _write(root, CONTRACT, "public sealed class OfferLockSnapshot { public int V = 2; }\n")
            v_stale = cv.evaluate_completion_verdict(
                root, level="flow", flow_id=FLOW_A, manifest_path=PILOT_MANIFEST,
                verification_scope_path="logs/ci/scopes/ac5-scope.json", receipt_paths=[rec_nf],
            )
            self.assertFalse(v_stale["ok"])
            self.assertEqual("input_stale", v_stale["reason_code"])
            self.assertEqual({"reason_code", "stage", "entity_id", "expected", "actual", "resume_ref"}, set(v_stale["diagnostics"][0].keys()))

            # (e) CLI smoke + forbidden write flags + zero mutation check
            with self.assertRaises(ValueError):
                dev_cli_builders.build_b_route_completion_verdict_cmd(
                    argparse.Namespace(root=str(root), level="flow", apply=True)
                )
            proc_bad = subprocess.run(
                [sys.executable, "-B", str(SCRIPTS_PY / "dev_cli.py"), "b-route-completion-verdict", "--level", "invalid"],
                capture_output=True, text=True, check=False, timeout=30,
            )
            self.assertEqual(2, proc_bad.returncode)

            self.assertEqual(tasks_sha_before, _sha_file(root / ".taskmaster/tasks/tasks.json"))
            self.assertEqual(catalog_sha_before, _sha_file(root / CATALOG))


if __name__ == "__main__":
    unittest.main()
