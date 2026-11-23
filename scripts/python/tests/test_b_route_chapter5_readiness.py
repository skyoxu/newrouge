"""Deterministic tests for Story 3.7 B-route Chapter 5 same-source reconciliation and readiness.

Covers every row of the Story 3.7 I/O & Edge-Case Matrix (RECONCILE_OK, PLANNED_ROLE,
STALE_SCOPED, DONE_REVERIFY, NEEDS_FIX_P1), 3A read-only reuse without skipping Chapter 5,
guarded_input_set business-scope leasing (no global writer lock), stage<5 blocking (4/5),
anti-timestamp-spoofing, anti-N/A and anti-legacy-fallback, load_task_readiness and
refresh_chapter_knowledge bridges (preserving A-only repos untouched), CLI/dev_cli/builder
wiring, and zero __pycache__ generation. Uses setUpClass base-fixture caching for speed.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS_PY = Path(__file__).resolve().parents[1]
REPO_ROOT = SCRIPTS_PY.parents[1]
if str(SCRIPTS_PY) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_PY))

import _b_route_chapter4_binding as ch4_binding
import _b_route_chapter5_readiness as ch5_b
import _b_route_codec as codec
import _b_route_input_set as input_set
import _b_route_records as records
import _b_route_stage5_obligations as s5_obls
import _mvg_manifest as mvg_manifest
import chapter5_semantic_reconciliation as ch5
import dev_cli
import dev_cli_builders
import reconcile_b_route_chapter5_readiness as ch5_b_cli
import refresh_chapter_knowledge as refresh_mod


DIAGNOSTIC_KEYS = {"reason_code", "stage", "entity_id", "expected", "actual", "resume_ref"}


def _encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _typed_ref(path: str, schema_version: str, entity_id: str, revision: int, raw: bytes) -> dict:
    return {
        "path": path,
        "schema_version": schema_version,
        "entity_id": entity_id,
        "revision": revision,
        "digest": codec.raw_digest(raw),
        "verification_mode": "raw",
        "codec_version": None,
    }


def _owned_ref(owner: str, ref: str, files: list[tuple[str, bytes]]) -> dict:
    return {
        "owner": owner,
        "ref": ref,
        "files": [{"path": p, "raw_digest": codec.raw_digest(raw)} for p, raw in files],
    }


def _four_parts() -> list[dict]:
    return [
        {
            "kind": "domain_rules",
            "applicability": "applicable",
            "rationale": "Deterministic core reward domain rules.",
            "responsibilities": ["Deterministic core reward domain rules."],
        },
        {
            "kind": "csharp_adapter",
            "applicability": "not_applicable",
            "rationale": "Headless domain scope without Godot adapter requirement.",
            "responsibilities": [],
        },
        {
            "kind": "binding",
            "applicability": "not_applicable",
            "rationale": "No UI control binding required in this slice.",
            "responsibilities": [],
        },
        {
            "kind": "scene",
            "applicability": "not_applicable",
            "rationale": "No Godot scene required in this slice.",
            "responsibilities": [],
        },
    ]


def _stage4_lifecycle(meta: dict) -> str:
    return "Stage-4 lifecycle | " + ch4_binding.STAGE4_LIFECYCLE_PREFIX + json.dumps(
        meta, ensure_ascii=True, separators=(",", ":")
    )


def _stage5_resp(plain: str, s5_meta: dict, s4_meta: dict) -> str:
    return (
        f"{plain} | {s5_obls.STAGE5_OBL_PREFIX}"
        + json.dumps(s5_meta, ensure_ascii=True, separators=(",", ":"))
        + f" | {ch4_binding.STAGE4_OBL_PREFIX}"
        + json.dumps(s4_meta, ensure_ascii=True, separators=(",", ":"))
    )


def _put(root: Path, rel: str, data: bytes | str) -> bytes:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return raw


def _put_json(root: Path, rel: str, value: object) -> bytes:
    return _put(root, rel, _encoded(value))


def _build_b_route_base_repo(
    root: Path,
    *,
    mode: str = "flow",  # "flow" | "nonflow"
    binding_stage: str = "5",
    include_planned: bool = True,
    task101_status: str = "in-progress",
    task102_status: str = "pending",
    task103_status: str = "pending",
) -> dict:
    """Create a complete schema-validated B-route repo with committed 3B plan, Stage-5 binding, and MVG manifest."""
    # 1. Sources, manifest, ledger, proofs, technical-debt register, ADR.
    gdd_raw = _put(root, "sources/reward-gdd.md", "# Reward Flow\n\nSelect reward and return to map deterministically.\n")
    src_entries = [{"path": "sources/reward-gdd.md", "source_type": "markdown", "sha256": codec.raw_digest(gdd_raw)}]
    manifest_digest = codec.canonical_digest(src_entries)
    source_revision = "source-set:" + manifest_digest[7:31]
    src_manifest_raw = _put_json(
        root,
        "sources/source-manifest.json",
        {
            "schema_version": "chapter3.source-manifest.v1",
            "source_revision": source_revision,
            "manifest_sha256": manifest_digest,
            "sources": src_entries,
        },
    )
    src_ledger_raw = _put_json(
        root,
        "sources/source-blocks.json",
        {
            "schema_version": "newrouge.source-blocks.v1",
            "source_revision": source_revision,
            "source_manifest_sha256": manifest_digest,
            "blocks": [
                {"block_id": "BLK-REWARD-1", "source_path": "sources/reward-gdd.md"},
                {"block_id": "BLK-OTHER-1", "source_path": "sources/reward-gdd.md"},
                {"block_id": "BLK-NONFLOW-1", "source_path": "sources/reward-gdd.md"},
            ],
        },
    )
    proof_raw = _put_json(root, "evidence/admission-proof.json", {"selected_candidate": "cand-1", "independent_audit": True})
    other_verif_raw = _put(
        root,
        "docs/testing/nonflow-checklist.md",
        "# Non-Flow Deterministic Audit Checklist\n\nVerified offline without MVG gameplay flow.\n",
    )
    _put(
        root,
        "docs/technical-debt.md",
        "# Technical Debt Register\n\n<!-- BEGIN AUTO:RUN_REVIEW_PIPELINE_TECHNICAL_DEBT -->\n<!-- END AUTO:RUN_REVIEW_PIPELINE_TECHNICAL_DEBT -->\n",
    )
    _put(
        root,
        "docs/adr/ADR-0004-event-bus-and-contracts.md",
        "# ADR-0004: Event Bus and Contracts\n\n- Status: Accepted\n\nContracts live in Game.Core/Contracts and remain BCL-only.\n",
    )

    # 2. Contracts, services, tests, overlay.
    _put(
        root,
        "Game.Core/Contracts/EventTypes.cs",
        'namespace Game.Core.Contracts;\npublic static class EventTypes\n{\n    public const string RewardOffered = "core.reward.offered";\n}\n',
    )
    cmd_rel = "Game.Core/Contracts/Reward/SelectRewardCommand.cs"
    cmd_raw = _put(
        root,
        cmd_rel,
        "using System;\nnamespace Game.Core.Contracts.Reward;\npublic sealed record SelectRewardCommand(string RunId, int OptionIndex);\n",
    )
    _put(root, "Game.Core/Services/RewardService.cs", "namespace Game.Core.Services;\npublic sealed class RewardService {}\n")
    _put(root, "Game.Core/Services/OtherService.cs", "namespace Game.Core.Services;\npublic sealed class OtherService {}\n")
    _put(root, "Game.Core.Tests/Reward/RewardFlowTests.cs", "public class RewardFlowTests {}\n")
    _put(root, "Game.Core.Tests/Other/OtherTests.cs", "public class OtherTests {}\n")
    overlay_rel = "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-reward.md"
    _put(
        root,
        overlay_rel,
        "---\nPRD-ID: PRD-NEWROUGE-GAME-0001\nTitle: Reward\nStatus: Draft\nADRs: [ADR-0004]\n---\n\n# Reward Overlay\nRefers to ADR-0004.\n",
    )

    # Note: planned test path & planned object path intentionally DO NOT exist on disk!
    planned_test_rel = "Game.Core.Tests/Reward/PlannedRewardEdgeTests.cs"
    planned_obj_rel = "Game.Core/Services/PlannedRewardGuard.cs"

    # 3. Taskmaster triplet: Tasks 101 (producer), 102 (consumer), 103 (integration_only_owner), and 201 (unrelated plan).
    t101_acc = (
        ["Verify non-flow documentation rule. Refs: docs/testing/nonflow-checklist.md"]
        if mode == "nonflow"
        else (
            [
                "Produce locked reward offer. Refs: Game.Core.Tests/Reward/RewardFlowTests.cs",
                f"Enforce planned reward edge guard. Refs: {planned_test_rel}",
            ]
            if include_planned
            else ["Produce locked reward offer. Refs: Game.Core.Tests/Reward/RewardFlowTests.cs"]
        )
    )
    master_tasks = [
        {
            "id": 101,
            "title": "Reward producer task",
            "status": task101_status,
            "dependencies": [],
            "details": "Producer task details.",
            "contractRefs": [] if mode == "nonflow" else ["core.reward.offered"],
            "overlay": overlay_rel,
            "testStrategy": "xUnit domain tests",
        },
        {
            "id": 102,
            "title": "Reward consumer task",
            "status": task102_status,
            "dependencies": [101],
            "details": "Consumer task details.",
            "contractRefs": [] if mode == "nonflow" else ["core.reward.offered"],
            "overlay": overlay_rel,
            "testStrategy": "xUnit domain tests",
        },
        {
            "id": 103,
            "title": "Reward integration verification owner",
            "status": task103_status,
            "dependencies": [101, 102],
            "details": "Integration-only owner; no runtime API required.",
            "contractRefs": [],
            "overlay": overlay_rel,
            "testStrategy": "MVG integration verification",
        },
        {
            "id": 201,
            "title": "Unrelated task in another plan",
            "status": "pending",
            "dependencies": [],
            "details": "Unrelated task.",
            "contractRefs": [],
            "overlay": overlay_rel,
            "testStrategy": "xUnit",
        },
    ]
    back_rows = [
        {
            "id": "NG-0101",
            "taskmaster_id": 101,
            "title": "Reward producer task",
            "status": task101_status,
            "depends_on": [],
            "acceptance": t101_acc,
            "contractRefs": [] if mode == "nonflow" else ["core.reward.offered"],
            "overlay_refs": [overlay_rel],
            "adr_refs": ["ADR-0004"],
        },
        {
            "id": "NG-0102",
            "taskmaster_id": 102,
            "title": "Reward consumer task",
            "status": task102_status,
            "depends_on": ["NG-0101"],
            "acceptance": ["Consume reward offer. Refs: Game.Core.Tests/Reward/RewardFlowTests.cs"],
            "contractRefs": [] if mode == "nonflow" else ["core.reward.offered"],
            "overlay_refs": [overlay_rel],
            "adr_refs": ["ADR-0004"],
        },
        {
            "id": "NG-0103",
            "taskmaster_id": 103,
            "title": "Reward integration verification owner",
            "status": task103_status,
            "depends_on": ["NG-0101", "NG-0102"],
            "acceptance": ["Verify reward integration handoff. Refs: Game.Core.Tests/Reward/RewardFlowTests.cs"],
            "contractRefs": [],
            "overlay_refs": [overlay_rel],
            "adr_refs": ["ADR-0004"],
        },
        {
            "id": "NG-0201",
            "taskmaster_id": 201,
            "title": "Unrelated task in another plan",
            "status": "pending",
            "depends_on": [],
            "acceptance": ["Unrelated acceptance. Refs: Game.Core.Tests/Other/OtherTests.cs"],
            "contractRefs": [],
            "overlay_refs": [overlay_rel],
        },
    ]
    _put_json(root, ".taskmaster/tasks/tasks.json", {"master": {"tasks": master_tasks}})
    _put_json(root, ".taskmaster/tasks/tasks_back.json", back_rows)
    _put_json(root, ".taskmaster/tasks/tasks_gameplay.json", [])

    # 4. MVG manifest (with implemented test + optional planned test; owner 103 is NOT in blocking_task_ids!).
    manifest_tests = [
        {
            "id": "test-reward-flow",
            "kind": "dotnet",
            "evidence_level": "domain-integration",
            "path": "Game.Core.Tests/Reward/RewardFlowTests.cs",
            "selector": "RewardFlowTests",
            "state": "implemented",
            "min_tests": 1,
        }
    ]
    flow_test_ids = ["test-reward-flow"]
    if include_planned:
        manifest_tests.append(
            {
                "id": "test-reward-edge-planned",
                "kind": "dotnet",
                "evidence_level": "domain-integration",
                "path": planned_test_rel,
                "selector": "PlannedRewardEdgeTests",
                "state": "planned",
                "min_tests": 1,
            }
        )
        flow_test_ids.append("test-reward-edge-planned")

    blockers = []
    if task101_status != "done":
        blockers.append(101)
    if task102_status != "done":
        blockers.append(102)
    # Task 103 is dedicated integration_only_owner, so NEVER in blocking_task_ids!

    mvg_manifest_path = "docs/testing/mvg/reward-baseline.json"
    mvg_manifest_raw = _put_json(
        root,
        mvg_manifest_path,
        {
            "schema_version": mvg_manifest.SCHEMA,
            "mvg_id": "mvg-reward-baseline",
            "coverage": {
                "mode": "pilot",
                "scope_id": "reward-scope",
                "required_flow_ids": ["flow-reward-select"],
                "blocking_task_ids": sorted(blockers),
                "excluded_claims": ["Manual animation polish verified separately."],
            },
            "flows": [
                {
                    "id": "flow-reward-select",
                    "task_ids": [101, 102, 103],
                    "outcome": "Player selects reward and returns to map.",
                    "source_paths": ["Game.Core/Services/RewardService.cs"],
                    "test_ids": flow_test_ids,
                    "handoffs": [
                        {
                            "producer_task": 101,
                            "consumer_task": 102,
                            "owner_task": 103,
                            "contract_ref": cmd_rel,
                            "behavior": "SelectRewardCommand hands locked reward choice to map return.",
                            "test_ids": ["test-reward-flow"],
                        }
                    ],
                }
            ],
            "tests": manifest_tests,
        },
    )

    # 5. Formal B-route records: policy, plan-reward, plan-other, bindings, origins, commit receipt, catalog.
    policy_path = records.BASE + "policy.v1.json"
    policy_raw = _put_json(
        root,
        policy_path,
        {
            "schema_version": "newrouge.b-route-policy.v1",
            "policy_id": "policy-main",
            "policy_revision": 1,
            "switch_boundary": {
                "default_route": "A",
                "a_write_allowed": True,
                "allowed_a_operations": ["resume-task"],
                "authority_refs": [],
            },
            "frozen_a_refs": [],
        },
    )
    policy_ref = _typed_ref(policy_path, "newrouge.b-route-policy.v1", "policy-main", 1, policy_raw)

    src_manifest_owned = _owned_ref("source_manifest", "sources/source-manifest.json", [("sources/source-manifest.json", src_manifest_raw)])
    src_ledger_owned = _owned_ref("source_ledger", "sources/source-blocks.json", [("sources/source-blocks.json", src_ledger_raw)])
    proof_owned = _owned_ref("planning_proof", "evidence/admission-proof.json", [("evidence/admission-proof.json", proof_raw)])
    other_verif_owned = _owned_ref("other_verification", "docs/testing/nonflow-checklist.md", [("docs/testing/nonflow-checklist.md", other_verif_raw)])
    mvg_manifest_owned = _owned_ref("manifest", mvg_manifest_path, [(mvg_manifest_path, mvg_manifest_raw)])
    cmd_owned = _owned_ref("contract", cmd_rel, [(cmd_rel, cmd_raw)])
    planned_obj_owned = None

    if mode == "nonflow":
        verif_row = {
            "requirement_id": "REQ-NONFLOW-1",
            "disposition": "other_verification",
            "flow_id": None,
            "rationale": "Deterministic non-flow checklist rule verified offline with zero gameplay Flow impact.",
            "sink_id": "SINK-DOC-CHECK",
            "verification_ref": "docs/testing/nonflow-checklist.md",
            "authority_ref": None,
            "evidence_ids": [],
        }
        plan_doc = {
            "schema_version": "newrouge.b-route-plan.v1",
            "plan_id": "plan-reward",
            "revision": 1,
            "lineage": {"previous_plan_ref": None, "change_summary": "Initial 3B non-flow plan.", "identity_alignment": []},
            "source_identity": {
                "source_revision": source_revision,
                "source_manifest_digest": manifest_digest,
                "manifest_ref": src_manifest_owned,
                "ledger_ref": src_ledger_owned,
            },
            "adoption_proof_refs": [proof_owned],
            "requirements": [
                {
                    "requirement_id": "REQ-NONFLOW-1",
                    "source_block_ids": ["BLK-NONFLOW-1"],
                    "acceptance_intent": "Verify non-flow documentation rule.",
                    "non_task_sinks": ["SINK-DOC-CHECK"],
                }
            ],
            "definitions": {"flows": [], "commands": [], "states": []},
            "logical_references": [],
            "requirement_verification": [verif_row],
            "requirement_route_memberships": [],
            "requirement_evidence": [],
            "evidence_source_refs": [other_verif_owned],
            "coverage_table": [{k: v for k, v in verif_row.items() if k != "evidence_ids"}],
            "applicability": [
                {
                    "requirement_id": "REQ-NONFLOW-1",
                    "disposition": "other_verification",
                    "rationale": verif_row["rationale"],
                    "other_verification_refs": [other_verif_owned],
                }
            ],
        }
    else:
        verif_row = {
            "requirement_id": "REQ-REWARD-1",
            "disposition": "flow",
            "flow_id": "flow-reward-select",
            "rationale": "Verified by reward selection MVG flow.",
            "sink_id": None,
            "verification_ref": None,
            "authority_ref": None,
            "evidence_ids": ["EV-REWARD-1"],
        }
        plan_doc = {
            "schema_version": "newrouge.b-route-plan.v1",
            "plan_id": "plan-reward",
            "revision": 1,
            "lineage": {"previous_plan_ref": None, "change_summary": "Initial 3B reward plan.", "identity_alignment": []},
            "source_identity": {
                "source_revision": source_revision,
                "source_manifest_digest": manifest_digest,
                "manifest_ref": src_manifest_owned,
                "ledger_ref": src_ledger_owned,
            },
            "adoption_proof_refs": [proof_owned],
            "requirements": [
                {
                    "requirement_id": "REQ-REWARD-1",
                    "source_block_ids": ["BLK-REWARD-1"],
                    "acceptance_intent": "Player selects reward and returns to map.",
                    "non_task_sinks": [],
                }
            ],
            "definitions": {
                "flows": [
                    {
                        "id": "flow-reward-select",
                        "requirement_ids": ["REQ-REWARD-1"],
                        "entry": "RewardScreen.Enter",
                        "entry_condition": "Combat victory offers locked rewards.",
                        "success_end": "MapScreen.Return",
                        "branches": [
                            {"kind": "failure", "rationale": "Reject invalid choice.", "description": "Keep reward screen open."},
                            {"kind": "cancel", "rationale": "Allow skip reward.", "description": "Close without granting card."},
                            {"kind": "return", "rationale": "Return to map node.", "description": "Navigate back to map."},
                        ],
                        "handoffs": [],
                        "state_owners": [
                            {
                                "kind": "state",
                                "definition_id": "state-reward",
                                "owner_plan_id": "plan-reward",
                                "owner_revision": 1,
                            }
                        ],
                        "parts": _four_parts(),
                        "observable_result": "Deterministic reward choice applied and returned to map.",
                        "verification_targets": ["RewardFlowTests"],
                        "loops": [],
                    }
                ],
                "commands": [
                    {
                        "id": "cmd-select-reward",
                        "requirement_ids": ["REQ-REWARD-1"],
                        "responsibility": "Select locked reward option.",
                        "uses": [
                            {
                                "kind": "state",
                                "definition_id": "state-reward",
                                "owner_plan_id": "plan-reward",
                                "owner_revision": 1,
                            }
                        ],
                    }
                ],
                "states": [
                    {
                        "id": "state-reward",
                        "requirement_ids": ["REQ-REWARD-1"],
                        "responsibility": "Locked reward offer read-only state.",
                        "uses": [],
                    }
                ],
            },
            "logical_references": [],
            "requirement_verification": [verif_row],
            "requirement_route_memberships": [
                {
                    "requirement_id": "REQ-REWARD-1",
                    "flow_id": "flow-reward-select",
                    "observable_role": "Observe reward selection and map return.",
                }
            ],
            "requirement_evidence": [
                {
                    "requirement_id": "REQ-REWARD-1",
                    "evidence_id": "EV-REWARD-1",
                    "kind": "implementation_reference",
                    "source_ref": cmd_rel,
                    "covered_behavior": "Locked reward selection command contract.",
                    "flow_ids": ["flow-reward-select"],
                    "test_ids": ["test-reward-flow"],
                }
            ],
            "evidence_source_refs": [cmd_owned],
            "coverage_table": [{k: v for k, v in verif_row.items() if k != "evidence_ids"}],
            "applicability": [
                {
                    "requirement_id": "REQ-REWARD-1",
                    "disposition": "flow",
                    "rationale": verif_row["rationale"],
                    "other_verification_refs": [],
                }
            ],
        }

    plan_path = records.BASE + "plans/plan-reward/1.json"
    plan_raw = _put_json(root, plan_path, plan_doc)
    plan_ref = _typed_ref(plan_path, "newrouge.b-route-plan.v1", "plan-reward", 1, plan_raw)

    # Binding for plan-reward.
    if mode == "nonflow":
        s4_meta = {"stage": "4", "task_ids": [101], "test_ids": []}
        s5_meta = {
            "stage": "5",
            "category": "current_new",
            "task_ids": [101],
            "newly_assigned_task_ids": [],
            "manifest_flow_ids": [],
            "non_catalog_flow_ids": [],
            "out_of_scope_future_flow_ids": [],
            "planned_test_ids": [],
            "has_new_obligation": False,
            "requires_reverification_on_done": False,
            "dedup_key": "plan-reward:OBL-NONFLOW-1",
        }
        binding_doc = {
            "schema_version": "newrouge.b-route-binding.v1",
            "plan_id": "plan-reward",
            "binding_revision": 1,
            "plan_ref": plan_ref,
            "stage": binding_stage,
            "task_mappings": [
                {
                    "task_id": 101,
                    "view_refs": [{"view": "back", "business_id": "NG-0101"}],
                    "requirement_ids": ["REQ-NONFLOW-1"],
                    "flow_ids": [],
                    "part_kinds": ["domain_rules"],
                    "roles": ["producer"],
                    "obligation_ids": ["OBL-NONFLOW-1"],
                }
            ],
            "parts": _four_parts(),
            "implementation_objects": [],
            "obligations": [
                {
                    "id": "OBL-NONFLOW-1",
                    "requirement_ids": ["REQ-NONFLOW-1"],
                    "flow_ids": [],
                    "test_ids": [],
                    "responsibility": _stage5_resp("Run non-flow checklist audit.", s5_meta, s4_meta),
                    "verification_refs": [other_verif_owned],
                }
            ],
            "manifest_refs": [],
            "other_verification_refs": [other_verif_owned],
        }
    else:
        impl_objects = [
            {
                "id": "obj-cmd-select-reward",
                "kind": "command",
                "availability": "existing",
                "responsible_task_ids": [101],
                "target_ref": cmd_owned,
                "expected_type": "Game.Core.Contracts.Reward.SelectRewardCommand",
                "lifecycle": _stage4_lifecycle(
                    {
                        "owner": "RewardService",
                        "contract_ref": cmd_rel,
                        "preconditions": ["Reward offered"],
                        "postconditions": ["Reward locked"],
                        "invariants": ["Deterministic selection"],
                        "handoff": {"owner": "RewardService", "owner_task": 103},
                    }
                ),
                "later_checks": ["type", "compile"],
            }
        ]
        if include_planned:
            impl_objects.append(
                {
                    "id": "obj-planned-reward-guard",
                    "kind": "read_only_state",
                    "availability": "planned",
                    "responsible_task_ids": [101],
                    "target_ref": planned_obj_owned,
                    "expected_type": "Game.Core.Services.PlannedRewardGuard",
                    "lifecycle": _stage4_lifecycle(
                        {
                            "single_owner": "RewardService",
                            "read_only_views": ["RewardGuardView"],
                            "forbidden_direct_writers": ["adapter", "ui"],
                        }
                    ),
                    "later_checks": ["type", "compile"],
                }
            )
        s4_meta = {"stage": "4", "task_ids": [101, 102, 103], "test_ids": flow_test_ids}
        s5_meta = {
            "stage": "5",
            "category": "current_new",
            "task_ids": [101, 102, 103],
            "newly_assigned_task_ids": [101],
            "manifest_flow_ids": ["flow-reward-select"],
            "non_catalog_flow_ids": [],
            "out_of_scope_future_flow_ids": [],
            "planned_test_ids": ["test-reward-edge-planned"] if include_planned else [],
            "has_new_obligation": True,
            "requires_reverification_on_done": True,
            "dedup_key": "plan-reward:OBL-REWARD-1",
        }
        binding_doc = {
            "schema_version": "newrouge.b-route-binding.v1",
            "plan_id": "plan-reward",
            "binding_revision": 1,
            "plan_ref": plan_ref,
            "stage": binding_stage,
            "task_mappings": [
                {
                    "task_id": 101,
                    "view_refs": [{"view": "back", "business_id": "NG-0101"}],
                    "requirement_ids": ["REQ-REWARD-1"],
                    "flow_ids": ["flow-reward-select"],
                    "part_kinds": ["domain_rules"],
                    "roles": ["producer"],
                    "obligation_ids": ["OBL-REWARD-1"],
                },
                {
                    "task_id": 102,
                    "view_refs": [{"view": "back", "business_id": "NG-0102"}],
                    "requirement_ids": ["REQ-REWARD-1"],
                    "flow_ids": ["flow-reward-select"],
                    "part_kinds": ["domain_rules"],
                    "roles": ["consumer"],
                    "obligation_ids": ["OBL-REWARD-1"],
                },
                {
                    "task_id": 103,
                    "view_refs": [{"view": "back", "business_id": "NG-0103"}],
                    "requirement_ids": ["REQ-REWARD-1"],
                    "flow_ids": ["flow-reward-select"],
                    "part_kinds": ["domain_rules"],
                    "roles": ["integration_only_owner"],
                    "obligation_ids": ["OBL-REWARD-1"],
                },
            ],
            "parts": _four_parts(),
            "implementation_objects": impl_objects,
            "obligations": [
                {
                    "id": "OBL-REWARD-1",
                    "requirement_ids": ["REQ-REWARD-1"],
                    "flow_ids": ["flow-reward-select"],
                    "test_ids": flow_test_ids,
                    "responsibility": _stage5_resp("Verify reward flow via MVG manifest.", s5_meta, s4_meta),
                    "verification_refs": [mvg_manifest_owned],
                }
            ],
            "manifest_refs": [mvg_manifest_owned],
            "other_verification_refs": [],
        }

    binding_path = records.BASE + "bindings/plan-reward/1.json"
    binding_raw = _put_json(root, binding_path, binding_doc)
    binding_ref = _typed_ref(binding_path, "newrouge.b-route-binding.v1", "plan-reward", 1, binding_raw)

    # Unrelated second plan (plan-other, task 201) to prove scoped invalidation!
    other_verif_2 = {
        "requirement_id": "REQ-OTHER-1",
        "disposition": "other_verification",
        "flow_id": None,
        "rationale": "Unrelated non-flow verification in separate plan.",
        "sink_id": "SINK-OTHER",
        "verification_ref": "docs/testing/nonflow-checklist.md",
        "authority_ref": None,
        "evidence_ids": [],
    }
    other_plan_doc = {
        "schema_version": "newrouge.b-route-plan.v1",
        "plan_id": "plan-other",
        "revision": 1,
        "lineage": {"previous_plan_ref": None, "change_summary": "Unrelated plan.", "identity_alignment": []},
        "source_identity": {
            "source_revision": source_revision,
            "source_manifest_digest": manifest_digest,
            "manifest_ref": src_manifest_owned,
            "ledger_ref": src_ledger_owned,
        },
        "adoption_proof_refs": [proof_owned],
        "requirements": [
            {
                "requirement_id": "REQ-OTHER-1",
                "source_block_ids": ["BLK-OTHER-1"],
                "acceptance_intent": "Unrelated acceptance.",
                "non_task_sinks": ["SINK-OTHER"],
            }
        ],
        "definitions": {"flows": [], "commands": [], "states": []},
        "logical_references": [],
        "requirement_verification": [other_verif_2],
        "requirement_route_memberships": [],
        "requirement_evidence": [],
        "evidence_source_refs": [other_verif_owned],
        "coverage_table": [{k: v for k, v in other_verif_2.items() if k != "evidence_ids"}],
        "applicability": [
            {
                "requirement_id": "REQ-OTHER-1",
                "disposition": "other_verification",
                "rationale": other_verif_2["rationale"],
                "other_verification_refs": [other_verif_owned],
            }
        ],
    }
    other_plan_path = records.BASE + "plans/plan-other/1.json"
    other_plan_raw = _put_json(root, other_plan_path, other_plan_doc)
    other_plan_ref = _typed_ref(other_plan_path, "newrouge.b-route-plan.v1", "plan-other", 1, other_plan_raw)
    other_binding_doc = {
        "schema_version": "newrouge.b-route-binding.v1",
        "plan_id": "plan-other",
        "binding_revision": 1,
        "plan_ref": other_plan_ref,
        "stage": "5",
        "task_mappings": [
            {
                "task_id": 201,
                "view_refs": [{"view": "back", "business_id": "NG-0201"}],
                "requirement_ids": ["REQ-OTHER-1"],
                "flow_ids": [],
                "part_kinds": ["domain_rules"],
                "roles": ["producer"],
                "obligation_ids": ["OBL-OTHER-1"],
            }
        ],
        "parts": _four_parts(),
        "implementation_objects": [],
        "obligations": [
            {
                "id": "OBL-OTHER-1",
                "requirement_ids": ["REQ-OTHER-1"],
                "flow_ids": [],
                "test_ids": [],
                "responsibility": _stage5_resp(
                    "Unrelated verification.",
                    {"stage": "5", "category": "current_new", "task_ids": [201], "dedup_key": "plan-other:OBL-OTHER-1"},
                    {"stage": "4", "task_ids": [201], "test_ids": []},
                ),
                "verification_refs": [other_verif_owned],
            }
        ],
        "manifest_refs": [],
        "other_verification_refs": [other_verif_owned],
    }
    other_binding_path = records.BASE + "bindings/plan-other/1.json"
    other_binding_raw = _put_json(root, other_binding_path, other_binding_doc)
    other_binding_ref = _typed_ref(other_binding_path, "newrouge.b-route-binding.v1", "plan-other", 1, other_binding_raw)

    # Origins.
    origins_tasks = [
        {"task_id": 101, "source_refs": [src_manifest_owned], "plan_refs": [plan_ref], "binding_refs": [binding_ref]},
        {"task_id": 201, "source_refs": [src_manifest_owned], "plan_refs": [other_plan_ref], "binding_refs": [other_binding_ref]},
    ]
    if mode != "nonflow":
        origins_tasks.insert(
            1,
            {"task_id": 102, "source_refs": [src_manifest_owned], "plan_refs": [plan_ref], "binding_refs": [binding_ref]},
        )
        origins_tasks.insert(
            2,
            {"task_id": 103, "source_refs": [src_manifest_owned], "plan_refs": [plan_ref], "binding_refs": [binding_ref]},
        )
    origins_path = records.BASE + "task-origins.v1.json"
    origins_raw = _put_json(
        root,
        origins_path,
        {
            "schema_version": "newrouge.b-route-origins.v1",
            "origins_id": "task-origins",
            "revision": 1,
            "tasks": sorted(origins_tasks, key=lambda r: r["task_id"]),
            "frozen_legacy_refs": [],
        },
    )
    origins_ref = _typed_ref(origins_path, "newrouge.b-route-origins.v1", "task-origins", 1, origins_raw)

    # Definition owners & commit receipt.
    def_owners = []
    if mode != "nonflow":
        def_owners = [
            {"kind": "flow", "definition_id": "flow-reward-select", "plan_ref": plan_ref},
            {"kind": "command", "definition_id": "cmd-select-reward", "plan_ref": plan_ref},
            {"kind": "state", "definition_id": "state-reward", "plan_ref": plan_ref},
        ]

    def _imm_target(rel_p: str, raw_b: bytes) -> dict:
        dg = codec.raw_digest(raw_b)
        return {
            "path": rel_p,
            "before_digest": None,
            "after_digest": dg,
            "verification_mode": "immutable_bytes",
            "codec_version": None,
            "projection_digest": dg,
        }

    commit_targets = [
        _imm_target(policy_path, policy_raw),
        _imm_target(plan_path, plan_raw),
        _imm_target(binding_path, binding_raw),
        _imm_target(other_plan_path, other_plan_raw),
        _imm_target(other_binding_path, other_binding_raw),
        _imm_target(origins_path, origins_raw),
    ]
    commit_path = records.BASE + "commits/OP-INIT-001.json"
    commit_doc = {
        "schema_version": "newrouge.b-route-commit.v1",
        "operation_id": "OP-INIT-001",
        "revision": 1,
        "operation_digest": codec.canonical_digest({"op": "OP-INIT-001", "mode": mode, "stage": binding_stage}),
        "scopes": ["scope-reward", "scope-other"],
        "authority": [
            {"path": "sources/source-manifest.json", "before_digest": None, "after_digest": codec.raw_digest(src_manifest_raw)},
            {"path": "sources/source-blocks.json", "before_digest": None, "after_digest": codec.raw_digest(src_ledger_raw)},
        ],
        "targets": commit_targets,
        "plan_refs": [plan_ref, other_plan_ref],
        "binding_refs": [binding_ref, other_binding_ref],
        "resolved_definitions": [d for d in def_owners if d["kind"] == "state"],
        "result": {
            "target_paths": [t["path"] for t in commit_targets],
            "scope_ids": ["scope-reward", "scope-other"],
        },
    }
    commit_raw = _put_json(root, commit_path, commit_doc)
    commit_ref = _typed_ref(commit_path, "newrouge.b-route-commit.v1", "OP-INIT-001", 1, commit_raw)

    # Catalog.
    task_index = [
        {
            "task_id": row["task_id"],
            "plan_refs": row["plan_refs"],
            "binding_refs": row["binding_refs"],
        }
        for row in sorted(origins_tasks, key=lambda r: r["task_id"])
    ]
    catalog_doc = {
        "schema_version": "newrouge.b-route-catalog.v1",
        "catalog_id": "catalog",
        "revision": 1,
        "policy_ref": policy_ref,
        "origins_ref": origins_ref,
        "scope_heads": [
            {
                "scope_id": "scope-reward",
                "plan_refs": [plan_ref],
                "binding_refs": [binding_ref],
                "receipt_ref": commit_ref,
            },
            {
                "scope_id": "scope-other",
                "plan_refs": [other_plan_ref],
                "binding_refs": [other_binding_ref],
                "receipt_ref": commit_ref,
            },
        ],
        "definition_owners": def_owners,
        "task_index": task_index,
    }
    _put_json(root, records.CATALOG_PATH, catalog_doc)

    return {
        "plan_path": plan_path,
        "binding_path": binding_path,
        "other_plan_path": other_plan_path,
        "other_binding_path": other_binding_path,
        "mvg_manifest_path": mvg_manifest_path,
        "cmd_rel": cmd_rel,
        "overlay_rel": overlay_rel,
        "planned_test_rel": planned_test_rel,
        "planned_obj_rel": planned_obj_rel,
        "gdd_rel": "sources/reward-gdd.md",
    }


def _decisions_for_task101(mode: str = "flow", include_planned: bool = True) -> dict:
    if mode == "nonflow":
        return {
            "acceptance_links": [
                {
                    "acceptance_index": 1,
                    "requirement_ids": ["REQ-NONFLOW-1"],
                    "authority_refs": ["docs/testing/nonflow-checklist.md"],
                    "test_refs": ["docs/testing/nonflow-checklist.md"],
                }
            ],
            "authority_decisions": [
                {
                    "authority_ref": "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-reward.md",
                    "status": "compatible",
                    "rationale": "Overlay matches non-flow scope.",
                },
                {
                    "authority_ref": "ADR-0004",
                    "status": "compatible",
                    "rationale": "ADR-0004 contract boundary is preserved.",
                },
            ],
            "dependency_decisions": [],
            "overlap_decisions": [],
        }
    links = [
        {
            "acceptance_index": 1,
            "requirement_ids": ["REQ-REWARD-1"],
            "authority_refs": ["core.reward.offered", "ADR-0004"],
            "test_refs": ["Game.Core.Tests/Reward/RewardFlowTests.cs"],
        }
    ]
    if include_planned:
        links.append(
            {
                "acceptance_index": 2,
                "requirement_ids": ["REQ-REWARD-1"],
                "authority_refs": ["ADR-0004"],
                "test_refs": ["Game.Core.Tests/Reward/PlannedRewardEdgeTests.cs"],
            }
        )
    return {
        "acceptance_links": links,
        "authority_decisions": [
            {
                "authority_ref": "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-reward.md",
                "status": "compatible",
                "rationale": "Overlay matches Stage-4/5 reward definitions.",
            },
            {
                "authority_ref": "ADR-0004",
                "status": "compatible",
                "rationale": "Event constants and BCL-only contract comply with ADR-0004.",
            },
            {
                "authority_ref": "core.reward.offered",
                "status": "compatible",
                "rationale": "Core event constant matches reward producer contract.",
            },
            {
                "authority_ref": "Game.Core/Contracts/Reward/SelectRewardCommand.cs",
                "status": "compatible",
                "rationale": "SelectRewardCommand is BCL-only and matches Stage-4 definition.",
            },
        ],
        "dependency_decisions": [],
        "overlap_decisions": [],
    }


def _decisions_for_task102() -> dict:
    return {
        "acceptance_links": [
            {
                "acceptance_index": 1,
                "requirement_ids": ["REQ-REWARD-1"],
                "authority_refs": ["core.reward.offered"],
                "test_refs": ["Game.Core.Tests/Reward/RewardFlowTests.cs"],
            }
        ],
        "authority_decisions": [
            {
                "authority_ref": "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-reward.md",
                "status": "compatible",
                "rationale": "Overlay matches consumer scope.",
            },
            {
                "authority_ref": "ADR-0004",
                "status": "compatible",
                "rationale": "Consumer observes ADR-0004 event bus boundary.",
            },
            {
                "authority_ref": "core.reward.offered",
                "status": "compatible",
                "rationale": "Consumer handles core.reward.offered contract.",
            },
        ],
        "dependency_decisions": [
            {
                "dependency_id": 101,
                "action": "keep",
                "relation": "producer_consumer",
                "dependency_reason": "Consumer task 102 depends on producer task 101 handoff.",
                "dependency_evidence": ["flow-reward-select handoff 101->102"],
            }
        ],
        "overlap_decisions": [],
    }


def _decisions_for_task103() -> dict:
    return {
        "acceptance_links": [
            {
                "acceptance_index": 1,
                "requirement_ids": ["REQ-REWARD-1"],
                "authority_refs": ["ADR-0004"],
                "test_refs": ["Game.Core.Tests/Reward/RewardFlowTests.cs"],
            }
        ],
        "authority_decisions": [
            {
                "authority_ref": "docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-reward.md",
                "status": "compatible",
                "rationale": "Overlay matches integration verification owner scope.",
            },
            {
                "authority_ref": "ADR-0004",
                "status": "compatible",
                "rationale": "Integration owner requires no runtime API under ADR-0004.",
            },
        ],
        "dependency_decisions": [
            {
                "dependency_id": 101,
                "action": "keep",
                "relation": "producer_consumer",
                "dependency_reason": "Integration owner verifies producer task 101.",
                "dependency_evidence": ["flow-reward-select handoff producer=101"],
            },
            {
                "dependency_id": 102,
                "action": "keep",
                "relation": "producer_consumer",
                "dependency_reason": "Integration owner verifies consumer task 102.",
                "dependency_evidence": ["flow-reward-select handoff consumer=102"],
            },
        ],
        "overlap_decisions": [],
    }


class BRouteChapter5ReadinessTests(unittest.TestCase):
    _cache_dir: tempfile.TemporaryDirectory[str]
    _flow_template: Path
    _flow_meta: dict
    _nonflow_template: Path
    _nonflow_meta: dict

    @classmethod
    def setUpClass(cls) -> None:
        cls._cache_dir = tempfile.TemporaryDirectory(prefix="b_route_ch5_readiness_base_")
        base = Path(cls._cache_dir.name).resolve()
        cls._flow_template = base / "flow_repo"
        cls._flow_meta = _build_b_route_base_repo(cls._flow_template, mode="flow", binding_stage="5", include_planned=True)
        cls._nonflow_template = base / "nonflow_repo"
        cls._nonflow_meta = _build_b_route_base_repo(cls._nonflow_template, mode="nonflow", binding_stage="5", include_planned=False)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._cache_dir.cleanup()

    def _clone(self, kind: str = "flow") -> tuple[Path, dict]:
        tmp = tempfile.TemporaryDirectory(prefix=f"b_route_ch5_{kind}_")
        self.addCleanup(tmp.cleanup)
        dst = Path(tmp.name).resolve() / "repo"
        src = self._flow_template if kind == "flow" else self._nonflow_template
        meta = self._flow_meta if kind == "flow" else self._nonflow_meta
        shutil.copytree(src, dst)
        return dst, copy.deepcopy(meta)

    def _assert_invariants(self, payload: dict) -> None:
        self.assertIs(payload["runtime_verified"], False)
        self.assertIs(payload["default_b_enabled"], False)
        for d in payload.get("diagnostics", []):
            self.assertEqual(set(d.keys()), DIAGNOSTIC_KEYS)
        if "metrics" in payload:
            m = payload["metrics"]
            self.assertGreaterEqual(m["active_elapsed_seconds"], 0.0)
            self.assertEqual(m["model_invocation_count"], 0)
            self.assertIn("source_audit_reused", m)
            self.assertIn("return_stage", m)

    # ------------------------------------------------------------------
    # Row 1: RECONCILE_OK (happy path, 3A reuse, non-Flow, omissions/conflicts/unowned/stage<5)
    # ------------------------------------------------------------------
    def test_01_reconcile_ok_freezes_input_set_reuses_3a_and_preserves_3b_plan(self) -> None:
        root, meta = self._clone("flow")
        plan_before = (root / meta["plan_path"]).read_bytes()
        guard_calls: list[dict] = []
        orig_guarded = input_set.guarded_input_set

        def spy_guarded(*args, **kwargs):
            guard_calls.append({"args": args, "kwargs": kwargs})
            return orig_guarded(*args, **kwargs)

        with patch.object(input_set, "guarded_input_set", side_effect=spy_guarded):
            res = ch5_b.reconcile_b_route_chapter5(
                root,
                task_id=101,
                decisions=_decisions_for_task101(),
                operation="implement",
            )

        self._assert_invariants(res)
        self.assertTrue(res["ok"], res["diagnostics"])
        self.assertEqual(res["readiness"], "READY")
        self.assertTrue(res["closure_allowed"])
        self.assertEqual(res["route"], "B")
        self.assertEqual(len(guard_calls), 1, "reconcile must execute under guarded_input_set")
        self.assertTrue(res["source_audit_reuse"]["reused"])
        self.assertEqual(res["metrics"]["model_invocation_count"], 0)
        self.assertTrue(res["metrics"]["source_audit_reused"])
        self.assertIsNone(res["return_stage"])
        self.assertRegex(res["input_set_digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertRegex(res["applicable_set_digest"], r"^sha256:[0-9a-f]{64}$")
        self.assertRegex(res["reconciliation_sha256"], r"^sha256:[0-9a-f]{64}$")
        self.assertTrue(res["scope_ids"])
        self.assertEqual(len(res["plan_refs"]), 1)
        self.assertEqual(len(res["binding_refs"]), 1)

        # 3B plan must NEVER be modified!
        self.assertEqual((root / meta["plan_path"]).read_bytes(), plan_before)

        # Read-only verify passes and bridges load_task_readiness + refresh_chapter_knowledge.
        ver = ch5_b.verify_b_route_chapter5_readiness(root, task_id=101)
        self._assert_invariants(ver)
        self.assertTrue(ver["ok"], ver["diagnostics"])
        self.assertTrue(ver["fresh"])

        ok_load, rdy_payload, reason_load = ch5.load_task_readiness(root, "101")
        self.assertTrue(ok_load, reason_load)
        self.assertEqual(rdy_payload["readiness"], "READY")
        self.assertEqual(rdy_payload["input_set_digest"], res["input_set_digest"])

        refresh_summary = refresh_mod.run(
            root,
            source="chapter5",
            trigger_run_id="RUN-B-CH5-001",
            refresh_local=True,
            write_planning=False,
            publish_if_eligible=False,
            triplet_status="unknown",
            source_manifest_path=root / "logs/ci/task-generation/source-manifest.v1.json",
            ledger_path=root / "logs/ci/task-generation/source-blocks.v1.json",
            semantics_path=root / "logs/ci/task-generation/semantic-requirements.v1.json",
            capabilities_path=root / "logs/ci/task-generation/capabilities.v1.json",
            edges_path=root / "logs/ci/task-generation/topology-edges.v1.json",
            candidates_path=root / "logs/ci/task-generation/task-candidates.enriched.json",
            report_path=root / "logs/ci/task-generation/semantic-conservation-report.json",
            reconciliation_path=root / res["reconciliation_path"],
            readiness_path=root / res["readiness_path"],
        )
        self.assertTrue(refresh_summary["closure_passed"], refresh_summary)

    def test_02_reconcile_ok_legal_non_flow_without_mvg_manifest(self) -> None:
        root, _meta = self._clone("nonflow")
        res = ch5_b.reconcile_b_route_chapter5(
            root,
            task_id=101,
            decisions=_decisions_for_task101(mode="nonflow", include_planned=False),
        )
        self._assert_invariants(res)
        self.assertTrue(res["ok"], res["diagnostics"])
        self.assertEqual(res["readiness"], "READY")
        ok_load, payload, reason = ch5.load_task_readiness(root, "101")
        self.assertTrue(ok_load, reason)
        self.assertEqual(payload["route"], "B")

    def test_03_reconcile_blocks_3a_bypass_omissions_conflicts_unowned_handoffs_and_stage_lt_5(self) -> None:
        # (a) Attempting to skip Chapter 5 via 3A blocks!
        root, _meta = self._clone("flow")
        dec_skip = _decisions_for_task101()
        dec_skip["skip_chapter5_reconciliation"] = True
        r_skip = ch5_b.reconcile_b_route_chapter5(root, task_id=101, decisions=dec_skip, write_artifacts=False)
        self._assert_invariants(r_skip)
        self.assertFalse(r_skip["ok"])
        self.assertEqual(r_skip["readiness"], "BLOCKED")
        self.assertEqual(r_skip["return_stage"], "5")

        # (b) Omission (missing acceptance_links covering REQ-REWARD-1) blocks!
        dec_omit = _decisions_for_task101()
        dec_omit["acceptance_links"] = []
        r_omit = ch5_b.reconcile_b_route_chapter5(root, task_id=101, decisions=dec_omit, write_artifacts=False)
        self._assert_invariants(r_omit)
        self.assertFalse(r_omit["ok"])
        self.assertEqual(r_omit["readiness"], "BLOCKED")

        # (c) Authority conflict blocks with return_stage="4"!
        dec_conflict = _decisions_for_task101()
        dec_conflict["authority_decisions"][1]["status"] = "conflict"
        dec_conflict["authority_decisions"][1]["rationale"] = "Conflicts with ADR-0004 boundary."
        r_conf = ch5_b.reconcile_b_route_chapter5(root, task_id=101, decisions=dec_conflict, write_artifacts=False)
        self._assert_invariants(r_conf)
        self.assertFalse(r_conf["ok"])
        self.assertEqual(r_conf["return_stage"], "4")

        # (d) Unowned handoff in Stage-4 implementation_object blocks with return_stage="4"!
        root_unowned, meta_u = self._clone("flow")
        bdoc = json.loads((root_unowned / meta_u["binding_path"]).read_text(encoding="utf-8"))
        bdoc["implementation_objects"][0]["lifecycle"] = _stage4_lifecycle(
            {"owner": "RewardService", "contract_ref": meta_u["cmd_rel"], "handoff": {"owner": ""}}
        )
        _recommit_binding(root_unowned, meta_u["binding_path"], bdoc)
        r_unowned = ch5_b.reconcile_b_route_chapter5(
            root_unowned, task_id=101, decisions=_decisions_for_task101(), write_artifacts=False
        )
        self._assert_invariants(r_unowned)
        self.assertFalse(r_unowned["ok"])
        self.assertEqual(r_unowned["return_stage"], "4")

        # (e) Binding stage="4" blocks with return_stage="5", and stage="3C" blocks with return_stage="4"!
        for stage_val, expected_ret in (("4", "5"), ("3C", "4")):
            tmp = tempfile.TemporaryDirectory(prefix=f"b_route_ch5_stage_{stage_val}_")
            self.addCleanup(tmp.cleanup)
            sroot = Path(tmp.name).resolve() / "repo"
            _build_b_route_base_repo(sroot, mode="flow", binding_stage=stage_val, include_planned=True)
            r_stage = ch5_b.reconcile_b_route_chapter5(
                sroot, task_id=101, decisions=_decisions_for_task101(), write_artifacts=False
            )
            self._assert_invariants(r_stage)
            self.assertFalse(r_stage["ok"])
            self.assertEqual(r_stage["return_stage"], expected_ret)

    # ------------------------------------------------------------------
    # Row 2: PLANNED_ROLE (non-done, explicit planned objects/tests, 3 roles, no self-lock, no stubs)
    # ------------------------------------------------------------------
    def test_04_planned_role_all_three_roles_ready_without_stubs_or_self_lock(self) -> None:
        root, meta = self._clone("flow")
        # Confirm planned object and planned test DO NOT exist on disk!
        self.assertFalse((root / meta["planned_obj_rel"]).exists())
        self.assertFalse((root / meta["planned_test_rel"]).exists())

        # Producer (101, in-progress), Consumer (102, pending), Integration-only owner (103, pending, no runtime API).
        for tid, dec in (
            (101, _decisions_for_task101()),
            (102, _decisions_for_task102()),
            (103, _decisions_for_task103()),
        ):
            res = ch5_b.reconcile_b_route_chapter5(root, task_id=tid, decisions=dec)
            self._assert_invariants(res)
            self.assertTrue(res["ok"], f"task {tid} failed: {res['diagnostics']}")
            self.assertEqual(res["readiness"], "READY")
            self.assertFalse(res["role_handoff_summary"]["self_lock_detected"])
            self.assertFalse(res["planned_summary"]["implementation_verified"])
            self.assertFalse(res["planned_summary"]["runtime_verified"])
            if tid == 101:
                self.assertEqual(len(res["planned_summary"]["planned_objects"]), 1)
                self.assertEqual(len(res["planned_summary"]["planned_tests"]), 1)
            if tid == 103:
                self.assertIn("integration_only_owner", res["role_handoff_summary"]["roles"])

        # Reconcile must NEVER create fake stubs on disk!
        self.assertFalse((root / meta["planned_obj_rel"]).exists())
        self.assertFalse((root / meta["planned_test_rel"]).exists())

    def test_05_planned_role_blocks_incomplete_planned_erased_prereq_and_self_lock(self) -> None:
        # (a) Attempting to erase required prerequisite dependency (101 on consumer 102) blocks with return_stage="3C"!
        root, meta = self._clone("flow")
        dec_erase = _decisions_for_task102()
        dec_erase["dependency_decisions"][0]["action"] = "remove"
        r_erase = ch5_b.reconcile_b_route_chapter5(root, task_id=102, decisions=dec_erase, write_artifacts=False)
        self._assert_invariants(r_erase)
        self.assertFalse(r_erase["ok"])
        self.assertEqual(r_erase["return_stage"], "3C")

        # (b) Incomplete planned object (expected_type="N/A") blocks with return_stage="4"!
        root_p, meta_p = self._clone("flow")
        bdoc = json.loads((root_p / meta_p["binding_path"]).read_text(encoding="utf-8"))
        bdoc["implementation_objects"][1]["expected_type"] = "N/A"
        _recommit_binding(root_p, meta_p["binding_path"], bdoc)
        r_inc = ch5_b.reconcile_b_route_chapter5(root_p, task_id=101, decisions=_decisions_for_task101(), write_artifacts=False)
        self._assert_invariants(r_inc)
        self.assertFalse(r_inc["ok"])
        self.assertEqual(r_inc["return_stage"], "4")

        # (c) Integration-only owner self-locked in coverage.blocking_task_ids blocks with return_stage="5"!
        root_sl, meta_sl = self._clone("flow")
        mdoc = json.loads((root_sl / meta_sl["mvg_manifest_path"]).read_text(encoding="utf-8"))
        mdoc["coverage"]["blocking_task_ids"] = [101, 102, 103]
        _recommit_manifest(root_sl, meta_sl["mvg_manifest_path"], meta_sl["binding_path"], mdoc)
        r_sl = ch5_b.reconcile_b_route_chapter5(root_sl, task_id=103, decisions=_decisions_for_task103(), write_artifacts=False)
        self._assert_invariants(r_sl)
        self.assertFalse(r_sl["ok"])
        self.assertEqual(r_sl["return_stage"], "5")

    # ------------------------------------------------------------------
    # Row 3: STALE_SCOPED (relevant 3A..5 stale vs unrelated valid, anti-timestamp, anti-N/A, anti-legacy)
    # ------------------------------------------------------------------
    def test_06_stale_scoped_unrelated_changes_stay_valid_while_relevant_return_3a_to_5(self) -> None:
        root, meta = self._clone("flow")
        res = ch5_b.reconcile_b_route_chapter5(root, task_id=101, decisions=_decisions_for_task101())
        self.assertTrue(res["ok"], res["diagnostics"])

        # Unrelated changes: modify unrelated task 201 definition & status, sibling task 102 status,
        # and advance catalog/origins revisions -> Task 101 readiness stays VALID!
        master_path = root / ".taskmaster/tasks/tasks.json"
        master = json.loads(master_path.read_text(encoding="utf-8"))
        for t in master["master"]["tasks"]:
            if t["id"] == 201:
                t["title"] = "Modified unrelated task 201 title"
                t["status"] = "done"
            elif t["id"] == 102:
                t["status"] = "done"
            elif t["id"] == 101:
                t["status"] = "pending"
        _put_json(root, ".taskmaster/tasks/tasks.json", master)

        ver_unrelated = ch5_b.verify_b_route_chapter5_readiness(root, task_id=101)
        self._assert_invariants(ver_unrelated)
        self.assertTrue(ver_unrelated["ok"], ver_unrelated["diagnostics"])
        self.assertTrue(ver_unrelated["fresh"])

        # Relevant change (4): modify C# contract -> stale, return_stage="4"!
        # Even refreshing generated_at_utc on readiness.json cannot spoof freshness!
        root_c4, meta_c4 = self._clone("flow")
        r4 = ch5_b.reconcile_b_route_chapter5(root_c4, task_id=101, decisions=_decisions_for_task101())
        self.assertTrue(r4["ok"])
        _put(
            root_c4,
            meta_c4["cmd_rel"],
            "using System;\nnamespace Game.Core.Contracts.Reward;\npublic sealed record SelectRewardCommand(string RunId, int OptionIndex, bool Extra);\n",
        )
        # Attempt timestamp spoofing on readiness.json!
        rdy_file = root_c4 / r4["readiness_path"]
        rdy_doc = json.loads(rdy_file.read_text(encoding="utf-8"))
        rdy_doc["generated_at_utc"] = "2099-01-01T00:00:00+00:00"
        _put_json(root_c4, r4["readiness_path"], rdy_doc)

        ver_c4 = ch5_b.verify_b_route_chapter5_readiness(root_c4, task_id=101)
        self._assert_invariants(ver_c4)
        self.assertFalse(ver_c4["ok"])
        self.assertFalse(ver_c4["fresh"])
        self.assertEqual(ver_c4["return_stage"], "4")

        # Relevant change (3A): modify source GDD -> stale, return_stage="3A"!
        root_3a, meta_3a = self._clone("flow")
        r3a = ch5_b.reconcile_b_route_chapter5(root_3a, task_id=101, decisions=_decisions_for_task101())
        self.assertTrue(r3a["ok"])
        _put(root_3a, meta_3a["gdd_rel"], "# Reward Flow\n\nChanged source requirement!\n")
        ver_3a = ch5_b.verify_b_route_chapter5_readiness(root_3a, task_id=101)
        self._assert_invariants(ver_3a)
        self.assertFalse(ver_3a["ok"])
        self.assertEqual(ver_3a["return_stage"], "3A")

        # Relevant change (3C): modify Task 101 definition -> stale, return_stage="3C"!
        root_3c, _meta_3c = self._clone("flow")
        r3c = ch5_b.reconcile_b_route_chapter5(root_3c, task_id=101, decisions=_decisions_for_task101())
        self.assertTrue(r3c["ok"])
        m3c = json.loads((root_3c / ".taskmaster/tasks/tasks.json").read_text(encoding="utf-8"))
        m3c["master"]["tasks"][0]["title"] = "Changed Task 101 title"
        _put_json(root_3c, ".taskmaster/tasks/tasks.json", m3c)
        ver_3c = ch5_b.verify_b_route_chapter5_readiness(root_3c, task_id=101)
        self._assert_invariants(ver_3c)
        self.assertFalse(ver_3c["ok"])
        self.assertEqual(ver_3c["return_stage"], "3C")

        # Relevant change (5): modify MVG manifest -> stale, return_stage="5"!
        root_5, meta_5 = self._clone("flow")
        r5 = ch5_b.reconcile_b_route_chapter5(root_5, task_id=101, decisions=_decisions_for_task101())
        self.assertTrue(r5["ok"])
        m5 = json.loads((root_5 / meta_5["mvg_manifest_path"]).read_text(encoding="utf-8"))
        m5["flows"][0]["outcome"] = "Changed manifest outcome."
        _put_json(root_5, meta_5["mvg_manifest_path"], m5)
        ver_5 = ch5_b.verify_b_route_chapter5_readiness(root_5, task_id=101)
        self._assert_invariants(ver_5)
        self.assertFalse(ver_5["ok"])
        self.assertEqual(ver_5["return_stage"], "5")

    def test_07_stale_scoped_forbids_na_exemption_and_legacy_fallback_while_preserving_a_only(self) -> None:
        # (a) Free-text mvg:N/A label on a Flow Task blocks!
        root_na, _meta_na = self._clone("flow")
        m_na = json.loads((root_na / ".taskmaster/tasks/tasks.json").read_text(encoding="utf-8"))
        m_na["master"]["tasks"][0]["details"] = "Labels: mvg:N/A\nAttempt to exempt MVG."
        _put_json(root_na, ".taskmaster/tasks/tasks.json", m_na)
        r_na = ch5_b.reconcile_b_route_chapter5(root_na, task_id=101, decisions=_decisions_for_task101(), write_artifacts=False)
        self._assert_invariants(r_na)
        self.assertFalse(r_na["ok"])
        self.assertEqual(r_na["return_stage"], "5")

        # (b) B-route repo missing B readiness MUST block (never fall back to legacy)!
        root_miss, _ = self._clone("flow")
        ok_m, payload_m, reason_m = ch5.load_task_readiness(root_miss, "101")
        self.assertFalse(ok_m)
        self.assertIn("b_route_chapter5_readiness_missing", reason_m)
        self.assertEqual(payload_m["route"], "B")

        # (c) B-route task holding legacy A-format readiness MUST block (never fall back to legacy)!
        fake_rec = {"schema_version": ch5.RECONCILIATION_SCHEMA, "task_id": "101", "global_audit_completed": True, "summary": {"blocking_count": 0}}
        fake_rdy = {
            "schema_version": ch5.READINESS_SCHEMA,
            "task_id": "101",
            "readiness": "READY",
            "closure_allowed": True,
            "reconciliation_sha256": "sha256:" + ch5._canonical_sha(fake_rec),
        }
        _put_json(root_miss, "logs/ci/chapter5/reconciliation/task-101.json", fake_rec)
        _put_json(root_miss, "logs/ci/chapter5/readiness/task-101.json", fake_rdy)
        ok_leg, _p_leg, reason_leg = ch5.load_task_readiness(root_miss, "101")
        self.assertFalse(ok_leg)
        self.assertIn("b_route_readiness_required_no_legacy_fallback", reason_leg)

        # (d) Partial/damaged B governance (missing catalog.v1.json) MUST block (never fall back to legacy)!
        root_dmg, _ = self._clone("flow")
        (root_dmg / records.CATALOG_PATH).unlink()
        ok_d, p_d, reason_d = ch5.load_task_readiness(root_dmg, "101")
        self.assertFalse(ok_d)
        self.assertIn("b_route_origin_blocked", reason_d)
        self.assertEqual(p_d["route"], "blocked")

        # (e) Pure legacy A-only repo (zero B traces) reports has_b_traces=False and keeps legacy path!
        with tempfile.TemporaryDirectory(prefix="legacy_a_only_") as tmp:
            aroot = Path(tmp).resolve()
            pres = ch5_b.detect_repo_b_route_presence(aroot, 1)
            self.assertFalse(pres["has_b_traces"])
            ok_a, _p_a, reason_a = ch5.load_task_readiness(aroot, "1")
            self.assertFalse(ok_a)
            self.assertEqual(reason_a, "chapter5_readiness_missing")

    # ------------------------------------------------------------------
    # Row 4: DONE_REVERIFY (status=done + new obligation/planned test)
    # ------------------------------------------------------------------
    def test_08_done_reverify_marks_chapter6_reverification_and_blocks_exemption_claims(self) -> None:
        root, _meta = self._clone("flow")
        master = json.loads((root / ".taskmaster/tasks/tasks.json").read_text(encoding="utf-8"))
        master["master"]["tasks"][0]["status"] = "done"
        _put_json(root, ".taskmaster/tasks/tasks.json", master)

        # Reconciling old done Task with new obligation & planned test -> READY + requires_chapter6_reverification=True!
        res = ch5_b.reconcile_b_route_chapter5(root, task_id=101, decisions=_decisions_for_task101())
        self._assert_invariants(res)
        self.assertTrue(res["ok"], res["diagnostics"])
        self.assertEqual(res["readiness"], "READY")
        self.assertTrue(res["requires_chapter6_reverification"])
        self.assertIs(res["old_done_covers_new_obligations"], False)

        # Claiming exemption from reverification MUST block!
        dec_exempt = _decisions_for_task101()
        dec_exempt["claim_skip_reverification"] = True
        r_ex = ch5_b.reconcile_b_route_chapter5(root, task_id=101, decisions=dec_exempt, write_artifacts=False)
        self._assert_invariants(r_ex)
        self.assertFalse(r_ex["ok"])
        self.assertEqual(r_ex["readiness"], "BLOCKED")
        self.assertEqual(r_ex["return_stage"], "5")

        # Dynamic live transition: task reconciled while in-progress -> later marked done -> verify reports requires_chapter6_reverification=True!
        root2, _ = self._clone("flow")
        r_init = ch5_b.reconcile_b_route_chapter5(root2, task_id=101, decisions=_decisions_for_task101())
        self.assertTrue(r_init["ok"])
        self.assertFalse(r_init["requires_chapter6_reverification"])
        m2 = json.loads((root2 / ".taskmaster/tasks/tasks.json").read_text(encoding="utf-8"))
        m2["master"]["tasks"][0]["status"] = "done"
        _put_json(root2, ".taskmaster/tasks/tasks.json", m2)
        ok_live, live_rdy, _reason = ch5.load_task_readiness(root2, "101")
        self.assertTrue(ok_live)
        self.assertTrue(live_rdy["requires_chapter6_reverification"])
        self.assertIs(live_rdy["old_done_covers_new_obligations"], False)

    # ------------------------------------------------------------------
    # Row 5: NEEDS_FIX_P1 (P0/P1 floor, P2..P4 debt register, anti-downgrade)
    # ------------------------------------------------------------------
    def test_09_needs_fix_p1_floor_technical_debt_and_anti_downgrade(self) -> None:
        root, _meta = self._clone("flow")

        # (a) P0 and P1 findings ALWAYS block even with allow_concerns=True!
        for sev in ("P0", "P1"):
            dec = _decisions_for_task101()
            dec["allow_concerns"] = True
            dec["findings"] = [
                {"finding_id": f"F-{sev}-01", "priority": sev, "category": "review", "reason": f"Must fix {sev} issue."}
            ]
            r = ch5_b.reconcile_b_route_chapter5(
                root, task_id=101, decisions=dec, write_artifacts=False, record_technical_debt=True
            )
            self._assert_invariants(r)
            self.assertFalse(r["ok"])
            self.assertEqual(r["readiness"], "BLOCKED")
            self.assertFalse(r["closure_allowed"])

        # (b) P2 finding in a P1-floor category (security) STILL blocks!
        dec_sec = _decisions_for_task101()
        dec_sec["allow_concerns"] = True
        dec_sec["findings"] = [
            {"finding_id": "F-SEC-01", "priority": "P2", "category": "security", "reason": "Security floor violation."}
        ]
        r_sec = ch5_b.reconcile_b_route_chapter5(root, task_id=101, decisions=dec_sec, write_artifacts=False)
        self.assertFalse(r_sec["ok"])
        self.assertEqual(r_sec["readiness"], "BLOCKED")

        # (c) P2 finding with allow_concerns=True WITHOUT technical-debt recording blocks!
        dec_p2 = _decisions_for_task101()
        dec_p2["allow_concerns"] = True
        dec_p2["findings"] = [
            {"finding_id": "F-P2-DOC-01", "priority": "P2", "category": "style", "reason": "Minor naming cleanup."}
        ]
        r_unrec = ch5_b.reconcile_b_route_chapter5(
            root, task_id=101, decisions=dec_p2, write_artifacts=False, record_technical_debt=False
        )
        self.assertFalse(r_unrec["ok"])
        self.assertEqual(r_unrec["readiness"], "BLOCKED")

        # (d) P2 finding with allow_concerns=True AND record_technical_debt=True -> CONCERNS, closure_allowed=True!
        r_rec = ch5_b.reconcile_b_route_chapter5(
            root, task_id=101, decisions=dec_p2, write_artifacts=True, record_technical_debt=True
        )
        self._assert_invariants(r_rec)
        self.assertTrue(r_rec["ok"], r_rec["diagnostics"])
        self.assertEqual(r_rec["readiness"], "CONCERNS")
        self.assertTrue(r_rec["closure_allowed"])
        self.assertIn("F-P2-DOC-01", (root / "docs/technical-debt.md").read_text(encoding="utf-8"))

        # Verify passes while recorded in docs/technical-debt.md, and FAILS CLOSED if deleted!
        ver_ok = ch5_b.verify_b_route_chapter5_readiness(root, task_id=101)
        self.assertTrue(ver_ok["ok"])
        _put(root, "docs/technical-debt.md", "# Technical Debt Register\n\nCleared.\n")
        ver_gone = ch5_b.verify_b_route_chapter5_readiness(root, task_id=101)
        self.assertFalse(ver_gone["ok"])
        self.assertEqual(ver_gone["return_stage"], "5")

        # (e) Quality downgrades (lower_thresholds, disable_tests, weaken_acceptance, fix_through=P0) ALL block!
        for mut in (
            {"lower_thresholds": True},
            {"disable_tests": True},
            {"weaken_acceptance": True},
            {"fix_through": "P0"},
        ):
            dec_bad = _decisions_for_task101()
            dec_bad.update(mut)
            r_bad = ch5_b.reconcile_b_route_chapter5(root, task_id=101, decisions=dec_bad, write_artifacts=False)
            self._assert_invariants(r_bad)
            self.assertFalse(r_bad["ok"], f"downgrade {mut} must block")
            self.assertEqual(r_bad["readiness"], "BLOCKED")

    # ------------------------------------------------------------------
    # CLI, dev_cli, builder & zero-pycache wiring
    # ------------------------------------------------------------------
    def test_10_cli_dev_cli_and_builder_end_to_end(self) -> None:
        root, _meta = self._clone("flow")
        dec_rel = "logs/ci/ch5-decisions-101.json"
        _put_json(root, dec_rel, _decisions_for_task101())

        # dev_cli_builders
        from types import SimpleNamespace
        args_obj = SimpleNamespace(
            root=str(root),
            stage="reconcile",
            task_id="101",
            decisions=dec_rel,
            operation="implement",
            out=None,
            readiness_out=None,
            reconciliation=None,
            readiness=None,
            lock_mode=None,
            audit_ref=[],
            no_latest=False,
            dry_run=False,
            record_technical_debt=False,
            require_full_audit_proof=False,
        )

        built = dev_cli_builders.build_b_route_chapter5_readiness_cmd(args_obj)
        self.assertIn("reconcile_b_route_chapter5_readiness.py", built[2])
        self.assertIn("--decisions", built)

        env = dict(os.environ)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONPATH"] = os.pathsep.join([str(SCRIPTS_PY), str(SCRIPTS_PY / "tests")])

        # --help via dev_cli.py
        help_proc = subprocess.run(
            [sys.executable, "-B", str(SCRIPTS_PY / "dev_cli.py"), "b-route-chapter5-readiness", "--help"],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(help_proc.returncode, 0, help_proc.stderr)
        self.assertIn("--stage", help_proc.stdout)

        # reconcile via dev_cli.py
        rec_proc = subprocess.run(
            [
                sys.executable,
                "-B",
                str(SCRIPTS_PY / "dev_cli.py"),
                "b-route-chapter5-readiness",
                "--root",
                str(root),
                "--stage",
                "reconcile",
                "--task-id",
                "101",
                "--decisions",
                dec_rel,
            ],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(rec_proc.returncode, 0, rec_proc.stdout + rec_proc.stderr)
        rec_out = json.loads(rec_proc.stdout)
        self._assert_invariants(rec_out)
        self.assertEqual(rec_out["readiness"], "READY")

        # verify, read & check-readiness via dev_cli.py
        for stg in ("verify", "read", "check-readiness"):
            proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPTS_PY / "dev_cli.py"),
                    "b-route-chapter5-readiness",
                    "--root",
                    str(root),
                    "--stage",
                    stg,
                    "--task-id",
                    "101",
                ],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, f"{stg} failed: {proc.stdout + proc.stderr}")
            out = json.loads(proc.stdout)
            self.assertTrue(out["ok"])
            self.assertIs(out["runtime_verified"], False)
            self.assertIs(out["default_b_enabled"], False)

        # dev_cli.build_parser() registers b-route-chapter5-readiness cleanly with cmd_b_route_chapter5_readiness.
        parser = dev_cli.build_parser()
        parsed = parser.parse_args(
            ["b-route-chapter5-readiness", "--root", str(root), "--stage", "check-readiness", "--task-id", "101"]
        )
        self.assertIs(parsed.func, dev_cli.cmd_b_route_chapter5_readiness)

        # Missing --decisions on reconcile exits 2.
        rc_bad = ch5_b_cli.main(["--root", str(root), "--stage", "reconcile", "--task-id", "101"])
        self.assertEqual(rc_bad, 2)

        # Cross-stage invalid flags on check-readiness / read exit 2 with INVALID_ARGUMENT!
        for stg in ("check-readiness", "read"):
            for bad_flag in (
                ["--decisions", dec_rel],
                ["--dry-run"],
                ["--record-technical-debt"],
                ["--require-full-audit-proof"],
            ):
                bad_proc = subprocess.run(
                    [
                        sys.executable,
                        "-B",
                        str(SCRIPTS_PY / "dev_cli.py"),
                        "b-route-chapter5-readiness",
                        "--root",
                        str(root),
                        "--stage",
                        stg,
                        "--task-id",
                        "101",
                        *bad_flag,
                    ],
                    capture_output=True,
                    text=True,
                    env=env,
                    check=False,
                )
                self.assertEqual(bad_proc.returncode, 2, f"{stg} {bad_flag}: {bad_proc.stdout + bad_proc.stderr}")
                bad_out = json.loads(bad_proc.stdout)
                self.assertEqual(bad_out["diagnostics"][0]["reason_code"], "invalid_argument")

        # Custom --out alone and custom --readiness-out pairing work across check-readiness and read!
        custom_rec = "logs/ci/custom-pair/rec-101.json"
        custom_rdy = "logs/ci/custom-pair/rdy-101.json"
        p_out_only = subprocess.run(
            [
                sys.executable,
                "-B",
                str(SCRIPTS_PY / "dev_cli.py"),
                "b-route-chapter5-readiness",
                "--root",
                str(root),
                "--stage",
                "reconcile",
                "--task-id",
                "101",
                "--decisions",
                dec_rel,
                "--out",
                custom_rec,
            ],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(p_out_only.returncode, 0, p_out_only.stdout + p_out_only.stderr)
        ok_auto_pair, payload_auto, reason_auto = ch5.load_task_readiness(root, "101")
        self.assertTrue(ok_auto_pair, reason_auto)
        self.assertEqual(payload_auto.get("reconciliation_path"), custom_rec)

        p_both = subprocess.run(
            [
                sys.executable,
                "-B",
                str(SCRIPTS_PY / "dev_cli.py"),
                "b-route-chapter5-readiness",
                "--root",
                str(root),
                "--stage",
                "reconcile",
                "--task-id",
                "101",
                "--decisions",
                dec_rel,
                "--out",
                custom_rec,
                "--readiness-out",
                custom_rdy,
            ],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        self.assertEqual(p_both.returncode, 0, p_both.stdout + p_both.stderr)
        for stg in ("check-readiness", "read"):
            p_fwd = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPTS_PY / "dev_cli.py"),
                    "b-route-chapter5-readiness",
                    "--root",
                    str(root),
                    "--stage",
                    stg,
                    "--task-id",
                    "101",
                    "--readiness",
                    custom_rdy,
                    "--operation",
                    "implement",
                    "--lock-mode",
                    "scope",
                ],
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )
            self.assertEqual(p_fwd.returncode, 0, f"{stg} custom pair failed: {p_fwd.stdout + p_fwd.stderr}")
            fwd_out = json.loads(p_fwd.stdout)
            self.assertTrue(fwd_out["ok"])
            self.assertEqual(fwd_out["reconciliation_path"], custom_rec)

    # ------------------------------------------------------------------
    # Step 4 P-02..P-06 Hardening Tests
    # ------------------------------------------------------------------
    def test_11_p02_schema_dir_exclusion_non_ascii_task_id_and_refresh_negative_closure(self) -> None:
        # (a) A-only repo WITH committed docs/planning/b-route/schemas/*.schema.json keeps has_b_traces=False!
        with tempfile.TemporaryDirectory(prefix="a_only_with_schemas_") as tmp:
            aroot = Path(tmp).resolve()
            _put_json(aroot, "docs/planning/b-route/schemas/plan.schema.json", {"$schema": "https://json-schema.org/draft/2020-12/schema"})
            pres = ch5_b.detect_repo_b_route_presence(aroot, 1)
            self.assertFalse(pres["has_b_traces"], pres)
            ok_a, _p_a, reason_a = ch5.load_task_readiness(aroot, "1")
            self.assertFalse(ok_a)
            self.assertEqual(reason_a, "chapter5_readiness_missing")

        # (b) Non-ASCII superscript "¹" and empty task_id on B-route repo fail closed without legacy fallback!
        root, meta = self._clone("flow")
        for bad_tid in ("\u00b9", "", "abc"):
            ok_l, _pl, reason_l = ch5.load_task_readiness(root, bad_tid)
            self.assertFalse(ok_l)
            self.assertIn("b_route_task_id_invalid", reason_l)
            ok_f, reason_f = ch5.validate_chapter5_evidence_freshness(
                root, task_id=bad_tid, reconciliation={}, readiness={}
            )
            self.assertFalse(ok_f)
            self.assertIn("b_route_task_id_invalid", reason_f)
            rep_c, ok_c, reason_c = refresh_mod.chapter5_closure_evidence(
                root,
                {},
                {},
                {"task_id": bad_tid},
                {"task_id": bad_tid},
                source_manifest_path=root / "logs/ci/task-generation/source-manifest.v1.json",
                ledger_path=root / "logs/ci/task-generation/source-blocks.v1.json",
                semantics_path=root / "logs/ci/task-generation/semantic-requirements.v1.json",
            )
            self.assertFalse(ok_c)
            self.assertEqual(rep_c["status"], "blocked")
            self.assertIn("b_route_task_id_invalid", reason_c)

        # (c) refresh_chapter_knowledge.run negative closure: stale B-route readiness & write_planning without Ch3!
        res = ch5_b.reconcile_b_route_chapter5(root, task_id=101, decisions=_decisions_for_task101())
        self.assertTrue(res["ok"], res["diagnostics"])
        rec_p = root / res["reconciliation_path"]
        rdy_p = root / res["readiness_path"]

        # write_planning=True on b_route_pure_ch5 without legacy Ch3 files fails closed cleanly (no FileNotFoundError).
        wp_summary = refresh_mod.run(
            root,
            source="chapter5",
            trigger_run_id="RUN-WP-FAIL",
            refresh_local=True,
            write_planning=True,
            publish_if_eligible=False,
            triplet_status="unknown",
            source_manifest_path=root / "logs/ci/task-generation/source-manifest.v1.json",
            ledger_path=root / "logs/ci/task-generation/source-blocks.v1.json",
            semantics_path=root / "logs/ci/task-generation/semantic-requirements.v1.json",
            capabilities_path=root / "logs/ci/task-generation/capabilities.v1.json",
            edges_path=root / "logs/ci/task-generation/topology-edges.v1.json",
            candidates_path=root / "logs/ci/task-generation/task-candidates.enriched.json",
            report_path=root / "logs/ci/task-generation/semantic-conservation-report.json",
            reconciliation_path=rec_p,
            readiness_path=rdy_p,
        )
        self.assertFalse(wp_summary["closure_passed"])
        self.assertEqual(wp_summary["local_refresh_failure_family"], "planning_topology_refresh_failed")
        self.assertIn("b_route_pure_ch5_missing_legacy_ch3_topology_artifacts", wp_summary["local_refresh_reason"])

        # Mutate contract -> stale B-route readiness must NOT pass refresh_chapter_knowledge.run!
        _put(
            root,
            meta["cmd_rel"],
            "using System;\nnamespace Game.Core.Contracts.Reward;\npublic sealed record SelectRewardCommand(string RunId, int OptionIndex, int Drift);\n",
        )
        stale_summary = refresh_mod.run(
            root,
            source="chapter5",
            trigger_run_id="RUN-STALE",
            refresh_local=True,
            write_planning=False,
            publish_if_eligible=False,
            triplet_status="unknown",
            source_manifest_path=root / "logs/ci/task-generation/source-manifest.v1.json",
            ledger_path=root / "logs/ci/task-generation/source-blocks.v1.json",
            semantics_path=root / "logs/ci/task-generation/semantic-requirements.v1.json",
            capabilities_path=root / "logs/ci/task-generation/capabilities.v1.json",
            edges_path=root / "logs/ci/task-generation/topology-edges.v1.json",
            candidates_path=root / "logs/ci/task-generation/task-candidates.enriched.json",
            report_path=root / "logs/ci/task-generation/semantic-conservation-report.json",
            reconciliation_path=rec_p,
            readiness_path=rdy_p,
        )
        self.assertFalse(stale_summary["closure_passed"])
        self.assertIn("return_stage=4", stale_summary["closure_evidence_reason"])

        # Legacy A readiness on B-route Task fails closed in validate_chapter5_evidence_freshness!
        root_leg, _ = self._clone("flow")
        fake_rec = {"schema_version": ch5.RECONCILIATION_SCHEMA, "task_id": "101", "global_audit_completed": True, "summary": {"blocking_count": 0}}
        fake_rdy = {"schema_version": ch5.READINESS_SCHEMA, "task_id": "101", "readiness": "READY", "closure_allowed": True}
        ok_vf, reason_vf = ch5.validate_chapter5_evidence_freshness(
            root_leg, task_id="101", reconciliation=fake_rec, readiness=fake_rdy
        )
        self.assertFalse(ok_vf)
        self.assertIn("b_route_readiness_required_no_legacy_fallback", reason_vf)

    def test_12_p03_dry_run_zero_write_lease_ordering_backslash_and_scoped_debt(self) -> None:
        root, _meta = self._clone("flow")
        debt_path = root / "docs/technical-debt.md"
        debt_before = debt_path.read_bytes()

        # (a) --dry-run (write_artifacts=False) + record_technical_debt=True MUST NOT write docs/technical-debt.md!
        dec_p2 = _decisions_for_task101()
        dec_p2["allow_concerns"] = True
        dec_p2["findings"] = [
            {
                "finding_id": "F-P2-DRY-01",
                "priority": "P2",
                "category": "style",
                "reason": r"Check path C:\foo\1\bar without crashing regex.",
            }
        ]
        r_dry = ch5_b.reconcile_b_route_chapter5(
            root, task_id=101, decisions=dec_p2, write_artifacts=False, record_technical_debt=True
        )
        self.assertTrue(r_dry["ok"], r_dry["diagnostics"])
        self.assertEqual(r_dry["readiness"], "CONCERNS")
        self.assertEqual(debt_path.read_bytes(), debt_before, "dry-run must never touch docs/technical-debt.md")
        self.assertIsNone(r_dry["reconciliation_path"])
        self.assertIsNone(r_dry["readiness_path"])

        # (b) Verify handle.revalidate() runs BEFORE record_technical_debt_findings!
        events: list[str] = []
        orig_rec_debt = ch5_b.record_technical_debt_findings
        orig_guarded = input_set.guarded_input_set

        from contextlib import contextmanager

        @contextmanager
        def spy_guarded(*args, **kwargs):
            with orig_guarded(*args, **kwargs) as h:
                orig_reval = h.revalidate

                def spy_reval():
                    events.append("revalidate")
                    return orig_reval()

                h.revalidate = spy_reval
                yield h

        def spy_rec_debt(*args, **kwargs):
            events.append("record_debt")
            return orig_rec_debt(*args, **kwargs)

        with patch.object(input_set, "guarded_input_set", side_effect=spy_guarded), patch.object(
            ch5_b, "record_technical_debt_findings", side_effect=spy_rec_debt
        ):
            r_ord = ch5_b.reconcile_b_route_chapter5(
                root, task_id=101, decisions=dec_p2, write_artifacts=True, record_technical_debt=True
            )
        self.assertTrue(r_ord["ok"], r_ord["diagnostics"])
        self.assertEqual(events[:2], ["revalidate", "record_debt"])

        # (c) Backslash message safety & preserving newline before next Task section!
        ch5_b.record_technical_debt_findings(
            root, 102, [{"finding_id": "F-P2-T102", "priority": "P2", "category": "style", "reason": "Task 102 item"}]
        )
        ch5_b.record_technical_debt_findings(
            root,
            101,
            [{"finding_id": "F-P2-BS-02", "priority": "P2", "category": "style", "reason": r"Updated C:\new\1\g<0> path"}],
        )
        debt_text = debt_path.read_text(encoding="utf-8")
        self.assertIn(r"Updated C:\new\1\g<0> path", debt_text)
        self.assertIn("\n### Task 102 (B-route Chapter 5 Concerns)\n", debt_text)

        # (d) Exact Task-scoped {finding_id=...} matching: Task 102's ID or raw substring outside token MUST NOT pass for Task 101!
        ok_cross, _rec_c, miss_c = ch5_b.verify_technical_debt_recorded(root, 101, [{"finding_id": "F-P2-T102"}])
        self.assertFalse(ok_cross)
        self.assertEqual(miss_c, ["F-P2-T102"])
        ok_sub, _rec_s, miss_s = ch5_b.verify_technical_debt_recorded(root, 101, [{"finding_id": "F-P2-BS"}])
        self.assertFalse(ok_sub)
        self.assertEqual(miss_s, ["F-P2-BS"])
        ok_exact, rec_e, miss_e = ch5_b.verify_technical_debt_recorded(root, 101, [{"finding_id": "F-P2-BS-02"}])
        self.assertTrue(ok_exact)
        self.assertEqual(rec_e, ["F-P2-BS-02"])
        self.assertEqual(miss_e, [])

    def test_13_p04_decisions_schema_merge_findings_and_extra_file_freshness(self) -> None:
        root, _meta = self._clone("flow")

        # (a) Non-list, duplicate keys, and out-of-range acceptance_index ALL block!
        dec_bad_type = _decisions_for_task101()
        dec_bad_type["authority_decisions"] = {"not": "a list"}
        r_bt = ch5_b.reconcile_b_route_chapter5(root, task_id=101, decisions=dec_bad_type, write_artifacts=False)
        self.assertFalse(r_bt["ok"])
        self.assertEqual(r_bt["return_stage"], "5")

        dec_dup = _decisions_for_task101()
        dec_dup["acceptance_links"].append(copy.deepcopy(dec_dup["acceptance_links"][0]))
        r_dup = ch5_b.reconcile_b_route_chapter5(root, task_id=101, decisions=dec_dup, write_artifacts=False)
        self.assertFalse(r_dup["ok"])

        dec_oor = _decisions_for_task101()
        dec_oor["acceptance_links"].append(
            {"acceptance_index": 99, "requirement_ids": ["REQ-REWARD-1"], "authority_refs": ["ADR-0004"], "test_refs": []}
        )
        r_oor = ch5_b.reconcile_b_route_chapter5(root, task_id=101, decisions=dec_oor, write_artifacts=False)
        self.assertFalse(r_oor["ok"])

        # (b) Merge BOTH findings AND review_findings (P1 in review_findings is NOT dropped when findings is non-empty)!
        dec_merge = _decisions_for_task101()
        dec_merge["allow_concerns"] = True
        dec_merge["findings"] = [{"finding_id": "F-P2-M1", "priority": "P2", "category": "style", "reason": "Minor style"}]
        dec_merge["review_findings"] = [{"finding_id": "F-P1-M2", "priority": "P1", "category": "review", "reason": "Must-fix P1 in review_findings"}]
        r_merge = ch5_b.reconcile_b_route_chapter5(root, task_id=101, decisions=dec_merge, write_artifacts=False)
        self.assertFalse(r_merge["ok"])
        self.assertEqual(r_merge["readiness"], "BLOCKED")
        self.assertTrue(any(f.get("finding_id") == "F-P1-M2" for f in r_merge["reconciliation_doc"]["findings"]))

        # (c) Extra decisions-referenced test_ref file drift -> return_stage="5"; extra ADR drift -> return_stage="4"!
        _put(root, "docs/adr/ADR-0099-extra-decision-rule.md", "# ADR-0099\n\nInitial text.\n")
        dec_extra = _decisions_for_task101()
        dec_extra["acceptance_links"][0]["authority_refs"].append("ADR-0099")
        dec_extra["authority_decisions"].append(
            {"authority_ref": "ADR-0099", "status": "compatible", "rationale": "Complies with ADR-0099."}
        )
        r_ex = ch5_b.reconcile_b_route_chapter5(root, task_id=101, decisions=dec_extra)
        self.assertTrue(r_ex["ok"], r_ex["diagnostics"])

        # Mutate existing test file -> stale with return_stage="5"!
        _put(root, "Game.Core.Tests/Reward/RewardFlowTests.cs", "public class RewardFlowTests { /* mutated */ }\n")
        ok_t, reason_t = ch5_b.validate_b_route_readiness_freshness(
            root, task_id="101", reconciliation=r_ex["reconciliation_doc"], readiness=r_ex["readiness_doc"]
        )
        self.assertFalse(ok_t)
        self.assertIn("return_stage=5", reason_t)

        # Restore test file and mutate extra ADR-0099 -> stale with return_stage="4"!
        _put(root, "Game.Core.Tests/Reward/RewardFlowTests.cs", "public class RewardFlowTests {}\n")
        _put(root, "docs/adr/ADR-0099-extra-decision-rule.md", "# ADR-0099\n\nMutated text!\n")
        ver_adr = ch5_b.verify_b_route_chapter5_readiness(root, task_id=101)
        self.assertFalse(ver_adr["ok"])
        self.assertEqual(ver_adr["return_stage"], "4")

    def test_14_p05_per_task_req_scoping_logical_handoff_contract_and_strict_refs(self) -> None:
        # (a) Multi-line acceptance Refs: parsed, while README.md and planned_objects rejected as fake test_refs!
        root, _meta = self._clone("flow")
        _put(root, "README.md", "# Readme\n")
        back_p = root / ".taskmaster/tasks/tasks_back.json"
        back_rows = json.loads(back_p.read_text(encoding="utf-8"))
        back_rows[0]["acceptance"][0] = (
            "Produce locked reward offer. Refs: Game.Core.Tests/Reward/RewardFlowTests.cs\nAdditional context line."
        )
        _put_json(root, ".taskmaster/tasks/tasks_back.json", back_rows)
        r_ml = ch5_b.reconcile_b_route_chapter5(root, task_id=101, decisions=_decisions_for_task101(), write_artifacts=False)
        self.assertTrue(r_ml["ok"], r_ml["diagnostics"])

        # Fake test_ref pointing to README.md MUST be rejected!
        dec_readme = _decisions_for_task101()
        dec_readme["acceptance_links"][0]["test_refs"] = ["README.md"]
        r_rm = ch5_b.reconcile_b_route_chapter5(root, task_id=101, decisions=dec_readme, write_artifacts=False)
        self.assertFalse(r_rm["ok"])
        self.assertTrue(any(f.get("status") == "untraceable_acceptance" for f in r_rm["reconciliation_doc"]["findings"]))

        # Fake test_ref pointing to planned_object (NOT planned_test) MUST be rejected!
        dec_pobj = _decisions_for_task101()
        dec_pobj["acceptance_links"][0]["test_refs"] = ["Game.Core/Services/PlannedRewardGuard.cs"]
        r_po = ch5_b.reconcile_b_route_chapter5(root, task_id=101, decisions=dec_pobj, write_artifacts=False)
        self.assertFalse(r_po["ok"])
        self.assertTrue(any(f.get("status") == "untraceable_acceptance" for f in r_po["reconciliation_doc"]["findings"]))

        # (b) Stage-4 implementation_object logical event contract_ref ("core.reward.offered") resolves via
        # _chapter5_contract_bindings.resolve_contract into authority_scope["contracts"] and requires authority_decisions!
        root_lc, meta_lc = self._clone("flow")
        # Remove core.reward.offered from Task 101 contractRefs so it comes ONLY from Stage-4 lifecycle contract_ref.
        m_lc = json.loads((root_lc / ".taskmaster/tasks/tasks.json").read_text(encoding="utf-8"))
        m_lc["master"]["tasks"][0]["contractRefs"] = []
        _put_json(root_lc, ".taskmaster/tasks/tasks.json", m_lc)
        b_lc = json.loads((root_lc / ".taskmaster/tasks/tasks_back.json").read_text(encoding="utf-8"))
        b_lc[0]["contractRefs"] = []
        _put_json(root_lc, ".taskmaster/tasks/tasks_back.json", b_lc)
        bdoc_lc = json.loads((root_lc / meta_lc["binding_path"]).read_text(encoding="utf-8"))
        bdoc_lc["implementation_objects"][0]["lifecycle"] = _stage4_lifecycle(
            {
                "owner": "RewardService",
                "contract_ref": "core.reward.offered",
                "preconditions": ["Reward offered"],
                "postconditions": ["Reward locked"],
                "invariants": ["Deterministic selection"],
                "handoff": {"owner": "RewardService", "owner_task": 103},
            }
        )
        _recommit_binding(root_lc, meta_lc["binding_path"], bdoc_lc)
        dec_lc_miss = _decisions_for_task101()
        dec_lc_miss["acceptance_links"][0]["authority_refs"] = ["ADR-0004"]
        dec_lc_miss["authority_decisions"] = [
            row for row in dec_lc_miss["authority_decisions"] if row["authority_ref"] != "core.reward.offered"
        ]
        r_lc_miss = ch5_b.reconcile_b_route_chapter5(root_lc, task_id=101, decisions=dec_lc_miss, write_artifacts=False)
        self.assertFalse(r_lc_miss["ok"])
        self.assertTrue(
            any(
                f.get("authority_ref") == "core.reward.offered" and f.get("status") == "needs_human_decision"
                for f in r_lc_miss["reconciliation_doc"]["findings"]
            )
        )
        dec_lc_ok = copy.deepcopy(dec_lc_miss)
        dec_lc_ok["authority_decisions"].append(
            {"authority_ref": "core.reward.offered", "status": "compatible", "rationale": "Logical event contract verified."}
        )
        r_lc_ok = ch5_b.reconcile_b_route_chapter5(root_lc, task_id=101, decisions=dec_lc_ok, write_artifacts=False)
        self.assertTrue(r_lc_ok["ok"], r_lc_ok["diagnostics"])

        # (c) Handoff owner_task outside flow["task_ids"] blocks (return_stage="5"),
        # and unknown Stage-4 handoff owner_task triggers direct Chapter 5 unowned_handoff!
        root_own, meta_own = self._clone("flow")
        mdoc_o = json.loads((root_own / meta_own["mvg_manifest_path"]).read_text(encoding="utf-8"))
        mdoc_o["flows"][0]["handoffs"][0]["owner_task"] = 201  # exists in master_tasks, NOT in flow["task_ids"]!
        _recommit_manifest(root_own, meta_own["mvg_manifest_path"], meta_own["binding_path"], mdoc_o)
        r_own = ch5_b.reconcile_b_route_chapter5(root_own, task_id=101, decisions=_decisions_for_task101(), write_artifacts=False)
        self.assertFalse(r_own["ok"])
        self.assertEqual(r_own["return_stage"], "5")
        self.assertTrue(
            bool(r_own["diagnostics"])
            or any(f.get("status") == "unowned_handoff" for f in r_own.get("reconciliation_doc", {}).get("findings", []))
        )

        # Direct Chapter 5 unowned_handoff finding when manifest syntax passes but Stage-4 handoff owner_task is unknown.
        bdoc_bad_own = json.loads((root_lc / meta_lc["binding_path"]).read_text(encoding="utf-8"))
        bdoc_bad_own["implementation_objects"][0]["lifecycle"] = _stage4_lifecycle(
            {
                "owner": "RewardService",
                "contract_ref": "core.reward.offered",
                "preconditions": ["Reward offered"],
                "postconditions": ["Reward locked"],
                "invariants": ["Deterministic selection"],
                "handoff": {"owner": "RewardService", "owner_task": 99999},
            }
        )
        _recommit_binding(root_lc, meta_lc["binding_path"], bdoc_bad_own)
        r_bad_own = ch5_b.reconcile_b_route_chapter5(root_lc, task_id=101, decisions=dec_lc_ok, write_artifacts=False)
        self.assertFalse(r_bad_own["ok"])
        self.assertEqual(r_bad_own["return_stage"], "4")
        self.assertTrue(
            any(f.get("status") == "unowned_handoff" for f in r_bad_own.get("reconciliation_doc", {}).get("findings", []))
        )

        # (d) Shared multi-task obligation with sibling requirement does NOT block Task 101!
        root_sib, meta_sib = self._clone("flow")
        pdoc = json.loads((root_sib / meta_sib["plan_path"]).read_text(encoding="utf-8"))
        pdoc["requirements"].append(
            {
                "requirement_id": "REQ-SIBLING-2",
                "source_block_ids": ["BLK-REWARD-1"],
                "acceptance_intent": "Sibling consumer requirement.",
                "non_task_sinks": [],
            }
        )
        sib_ev = copy.deepcopy(pdoc["requirement_evidence"][0])
        sib_ev["requirement_id"] = "REQ-SIBLING-2"
        sib_ev["evidence_id"] = "EV-SIBLING-2"
        pdoc["requirement_evidence"].append(sib_ev)
        sib_verif = {
            "requirement_id": "REQ-SIBLING-2",
            "disposition": "flow",
            "flow_id": "flow-reward-select",
            "rationale": "Verified by reward selection MVG flow for sibling consumer.",
            "sink_id": None,
            "verification_ref": None,
            "authority_ref": None,
            "evidence_ids": ["EV-SIBLING-2"],
        }
        pdoc["requirement_verification"].append(sib_verif)
        pdoc["coverage_table"].append({k: v for k, v in sib_verif.items() if k != "evidence_ids"})
        pdoc["applicability"].append(
            {"requirement_id": "REQ-SIBLING-2", "disposition": "flow", "rationale": sib_verif["rationale"], "other_verification_refs": []}
        )
        pdoc["definitions"]["flows"][0]["requirement_ids"].append("REQ-SIBLING-2")
        pdoc["requirement_route_memberships"].append(
            {"requirement_id": "REQ-SIBLING-2", "flow_id": "flow-reward-select", "observable_role": "Sibling consumer"}
        )
        bdoc = json.loads((root_sib / meta_sib["binding_path"]).read_text(encoding="utf-8"))
        bdoc["task_mappings"][1]["requirement_ids"] = ["REQ-SIBLING-2"]
        bdoc["obligations"][0]["requirement_ids"] = ["REQ-REWARD-1", "REQ-SIBLING-2"]
        _recommit_plan_and_binding(root_sib, meta_sib["plan_path"], pdoc, meta_sib["binding_path"], bdoc)
        r_sib = ch5_b.reconcile_b_route_chapter5(root_sib, task_id=101, decisions=_decisions_for_task101(), write_artifacts=False)
        self.assertTrue(r_sib["ok"], r_sib["diagnostics"])
        self.assertNotIn("REQ-SIBLING-2", r_sib["reconciliation_doc"]["acceptance_coverage"])

    def test_15_p06_3a_source_audit_proof_replay_and_policy_pinning(self) -> None:
        root, meta = self._clone("flow")

        # (a) --require-full-audit-proof without any 3A source_audit proof blocks with return_stage="3A"!
        r_miss = ch5_b.reconcile_b_route_chapter5(
            root, task_id=101, decisions=_decisions_for_task101(), write_artifacts=False, require_full_audit_proof=True
        )
        self.assertFalse(r_miss["ok"])
        self.assertEqual(r_miss["return_stage"], "3A")

        # (b) Valid 3A source_audit artifact matching live source digest passes under --require-full-audit-proof!
        gdd_digest = codec.raw_digest((root / meta["gdd_rel"]).read_bytes())
        manifest_doc = json.loads((root / "sources/source-manifest.json").read_text(encoding="utf-8"))
        valid_audit_rel = "logs/ci/3a-proof/audit-valid.json"
        _put_json(
            root,
            valid_audit_rel,
            {
                "schema_version": "newrouge.b-route-source-audit.v1",
                "satisfied": True,
                "execution_complete": True,
                "independent_audit": True,
                "semantic_blockers": [],
                "findings": [],
                "source_manifest_digest": manifest_doc["manifest_sha256"],
                "sources": [{"path": meta["gdd_rel"], "raw_digest": gdd_digest}],
                "exit_code": 0,
            },
        )
        r_ok = ch5_b.reconcile_b_route_chapter5(
            root,
            task_id=101,
            decisions=_decisions_for_task101(),
            audit_refs=[valid_audit_rel],
            require_full_audit_proof=True,
        )
        self.assertTrue(r_ok["ok"], r_ok["diagnostics"])
        self.assertEqual(r_ok["source_audit_reuse"]["verified_full_audit_refs"], [valid_audit_rel])

        # (c) Drifted source digest in 3A proof blocks with return_stage="3A"!
        drifted_audit_rel = "logs/ci/3a-proof/audit-drifted.json"
        _put_json(
            root,
            drifted_audit_rel,
            {
                "schema_version": "newrouge.b-route-source-audit.v1",
                "satisfied": True,
                "execution_complete": True,
                "independent_audit": True,
                "semantic_blockers": [],
                "findings": [],
                "sources": [{"path": meta["gdd_rel"], "raw_digest": "sha256:" + "0" * 64}],
                "exit_code": 0,
            },
        )
        r_drift = ch5_b.reconcile_b_route_chapter5(
            root,
            task_id=101,
            decisions=_decisions_for_task101(),
            audit_refs=[drifted_audit_rel],
            write_artifacts=False,
            require_full_audit_proof=True,
        )
        self.assertFalse(r_drift["ok"])
        self.assertEqual(r_drift["return_stage"], "3A")

        # (d) Unsatisfied / blocking 3A proof blocks with return_stage="3A"!
        blocked_audit_rel = "logs/ci/3a-proof/audit-blocked.json"
        _put_json(
            root,
            blocked_audit_rel,
            {
                "schema_version": "newrouge.b-route-source-audit.v1",
                "satisfied": False,
                "execution_complete": True,
                "independent_audit": True,
                "semantic_blockers": [{"finding_id": "3A-BLK-1"}],
                "findings": [{"finding_id": "3A-BLK-1", "severity": "blocking"}],
                "sources": [{"path": meta["gdd_rel"], "raw_digest": gdd_digest}],
                "exit_code": 1,
            },
        )
        r_blk = ch5_b.reconcile_b_route_chapter5(
            root,
            task_id=101,
            decisions=_decisions_for_task101(),
            audit_refs=[blocked_audit_rel],
            write_artifacts=False,
            require_full_audit_proof=True,
        )
        self.assertFalse(r_blk["ok"])
        self.assertEqual(r_blk["return_stage"], "3A")

        # (e) Policy observations pin both _chapter5_contract_bindings.py and _b_route_chapter5_readiness.py!
        import _b_route_adoption_review as adoption_review
        _ident, pinned_files = adoption_review.policy_observations()
        pinned_names = {Path(k).name for k in pinned_files}
        self.assertIn("_chapter5_contract_bindings.py", pinned_names)
        self.assertIn("_b_route_chapter5_readiness.py", pinned_names)


def _recommit_plan_and_binding(
    root: Path, plan_rel: str, plan_doc: dict, binding_rel: str, binding_doc: dict
) -> None:
    """Helper to update a plan and binding together and re-seal typed refs in origins/commit/catalog."""
    praw = _put_json(root, plan_rel, plan_doc)
    pref = _typed_ref(plan_rel, "newrouge.b-route-plan.v1", plan_doc["plan_id"], plan_doc["revision"], praw)
    binding_doc["plan_ref"] = pref
    braw = _put_json(root, binding_rel, binding_doc)
    bref = _typed_ref(binding_rel, "newrouge.b-route-binding.v1", binding_doc["plan_id"], binding_doc["binding_revision"], braw)

    origins_path = records.BASE + "task-origins.v1.json"
    origins = json.loads((root / origins_path).read_text(encoding="utf-8"))
    for t in origins["tasks"]:
        t["plan_refs"] = [pref if r["entity_id"] == plan_doc["plan_id"] else r for r in t["plan_refs"]]
        t["binding_refs"] = [bref if r["entity_id"] == binding_doc["plan_id"] else r for r in t["binding_refs"]]
    origins_raw = _put_json(root, origins_path, origins)
    origins_ref = _typed_ref(origins_path, "newrouge.b-route-origins.v1", "task-origins", origins["revision"], origins_raw)

    commit_path = records.BASE + "commits/OP-INIT-001.json"
    commit_doc = json.loads((root / commit_path).read_text(encoding="utf-8"))
    for tgt in commit_doc["targets"]:
        if tgt["path"] == plan_rel:
            dg = codec.raw_digest(praw)
            tgt["after_digest"] = dg
            tgt["projection_digest"] = dg
        elif tgt["path"] == binding_rel:
            dg = codec.raw_digest(braw)
            tgt["after_digest"] = dg
            tgt["projection_digest"] = dg
        elif tgt["path"] == origins_path:
            dg = codec.raw_digest(origins_raw)
            tgt["after_digest"] = dg
            tgt["projection_digest"] = dg
    commit_doc["plan_refs"] = [pref if r["entity_id"] == plan_doc["plan_id"] else r for r in commit_doc["plan_refs"]]
    commit_doc["binding_refs"] = [bref if r["entity_id"] == binding_doc["plan_id"] else r for r in commit_doc["binding_refs"]]
    for drow in commit_doc.get("resolved_definitions", []):
        if drow.get("plan_ref", {}).get("entity_id") == plan_doc["plan_id"]:
            drow["plan_ref"] = pref
    commit_raw = _put_json(root, commit_path, commit_doc)
    commit_ref = _typed_ref(commit_path, "newrouge.b-route-commit.v1", "OP-INIT-001", 1, commit_raw)

    cat = json.loads((root / records.CATALOG_PATH).read_text(encoding="utf-8"))
    cat["origins_ref"] = origins_ref
    for h in cat["scope_heads"]:
        h["plan_refs"] = [pref if r["entity_id"] == plan_doc["plan_id"] else r for r in h["plan_refs"]]
        h["binding_refs"] = [bref if r["entity_id"] == binding_doc["plan_id"] else r for r in h["binding_refs"]]
        h["receipt_ref"] = commit_ref
    for trow in cat["task_index"]:
        trow["plan_refs"] = [pref if r["entity_id"] == plan_doc["plan_id"] else r for r in trow["plan_refs"]]
        trow["binding_refs"] = [bref if r["entity_id"] == binding_doc["plan_id"] else r for r in trow["binding_refs"]]
    for drow in cat["definition_owners"]:
        if drow["plan_ref"]["entity_id"] == plan_doc["plan_id"]:
            drow["plan_ref"] = pref
    _put_json(root, records.CATALOG_PATH, cat)


def _recommit_binding(root: Path, binding_rel: str, binding_doc: dict) -> None:
    """Helper to update a binding and re-seal its typed ref in origins/commit/catalog."""
    braw = _put_json(root, binding_rel, binding_doc)
    bref = _typed_ref(binding_rel, "newrouge.b-route-binding.v1", binding_doc["plan_id"], binding_doc["binding_revision"], braw)

    origins_path = records.BASE + "task-origins.v1.json"
    origins = json.loads((root / origins_path).read_text(encoding="utf-8"))
    for t in origins["tasks"]:
        t["binding_refs"] = [bref if r["entity_id"] == binding_doc["plan_id"] else r for r in t["binding_refs"]]
    origins_raw = _put_json(root, origins_path, origins)
    origins_ref = _typed_ref(origins_path, "newrouge.b-route-origins.v1", "task-origins", origins["revision"], origins_raw)

    commit_path = records.BASE + "commits/OP-INIT-001.json"
    commit_doc = json.loads((root / commit_path).read_text(encoding="utf-8"))
    for tgt in commit_doc["targets"]:
        if tgt["path"] == binding_rel:
            dg = codec.raw_digest(braw)
            tgt["after_digest"] = dg
            tgt["projection_digest"] = dg
        elif tgt["path"] == origins_path:
            dg = codec.raw_digest(origins_raw)
            tgt["after_digest"] = dg
            tgt["projection_digest"] = dg
    commit_doc["binding_refs"] = [bref if r["entity_id"] == binding_doc["plan_id"] else r for r in commit_doc["binding_refs"]]
    commit_raw = _put_json(root, commit_path, commit_doc)
    commit_ref = _typed_ref(commit_path, "newrouge.b-route-commit.v1", "OP-INIT-001", 1, commit_raw)

    cat = json.loads((root / records.CATALOG_PATH).read_text(encoding="utf-8"))
    cat["origins_ref"] = origins_ref
    for h in cat["scope_heads"]:
        h["binding_refs"] = [bref if r["entity_id"] == binding_doc["plan_id"] else r for r in h["binding_refs"]]
        h["receipt_ref"] = commit_ref
    for trow in cat["task_index"]:
        trow["binding_refs"] = [bref if r["entity_id"] == binding_doc["plan_id"] else r for r in trow["binding_refs"]]
    _put_json(root, records.CATALOG_PATH, cat)


def _recommit_manifest(root: Path, manifest_rel: str, binding_rel: str, manifest_doc: dict) -> None:
    """Helper to update an MVG manifest and re-seal its OwnedRef inside the Stage-5 binding."""
    mraw = _put_json(root, manifest_rel, manifest_doc)
    new_digest = codec.raw_digest(mraw)
    bdoc = json.loads((root / binding_rel).read_text(encoding="utf-8"))
    for obl in bdoc["obligations"]:
        for vref in obl["verification_refs"]:
            if vref.get("owner") in ("manifest", "mvg_manifest"):
                for frow in vref["files"]:
                    if frow["path"] == manifest_rel:
                        frow["raw_digest"] = new_digest
    for mref in bdoc.get("manifest_refs", []):
        for frow in mref.get("files", []):
            if frow["path"] == manifest_rel:
                frow["raw_digest"] = new_digest
    _recommit_binding(root, binding_rel, bdoc)


if __name__ == "__main__":
    unittest.main()
