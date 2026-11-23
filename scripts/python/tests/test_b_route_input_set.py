"""Deterministic tests for Story 3.5 common InputSet construction and freshness evaluation.

Covers every row of the Story 3.5 I/O & Edge-Case Matrix (FULL_SET, STATUS_NOOP,
REL_INVALID, DRIFT_LOCK, CALLER_PARITY), clean clones without logs/, explicit
--candidate-binding single-slot replacement + uses_candidate_binding=True,
sibling Flow Task status -> done NOT breaking MVG manifest validation,
other-plan origins.revision / catalog.revision / Git HEAD advances NOT changing
input_set_digest, all 5 return_stage values (3A, 3B, 3C, 4, 5), unknown and
cyclic dependency rejection, guarded_input_set business_guard(review_only=True)
and revalidate(), and dev_cli.main(["b-route-input-set", ...]) end-to-end.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import contextlib
import copy
import importlib
import io
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

import _b_route_adoption_review as adoption_review
import _b_route_codec as codec
import _b_route_input_set as input_set
import _b_route_operation_scope as op_scope
import _b_route_protection as protection
import _b_route_records as records
import _b_route_task_resolver as resolver
import dev_cli
import dev_cli_builders
import resolve_b_route_input_set as input_set_cli
from tests.test_b_route_task_resolver import (
    ResolverRepoBuilder,
    _build_binding_doc,
    _build_plan_doc,
    _create_unapplied_operation,
    _encoded,
    _four_parts,
    _make_flow,
    _owned_ref,
    _typed_ref,
)


DIAGNOSTIC_KEYS = {"reason_code", "stage", "entity_id", "expected", "actual", "resume_ref"}
AUTH_KEYS = ("execution_authorized", "readiness", "runtime_verified", "default_b_enabled")


def _stage4_lifecycle(meta: dict) -> str:
    return "Stage-4 lifecycle | STAGE4_META:" + json.dumps(meta, ensure_ascii=True, separators=(",", ":"))


def _build_base_template(root: Path) -> dict:
    """Build one complete schema-valid multi-plan B-route repo template."""
    builder = ResolverRepoBuilder(root)
    src = builder.write_sources_and_proof(use_log_proof=True)

    # ADRs
    adr4_rel = "docs/adr/ADR-0004-event-bus-and-contracts.md"
    adr4_raw = builder.put(adr4_rel, "# ADR-0004\n\n- Status: Accepted\n\nEvent bus and BCL-only contracts.\n")

    # BCL-only C# contracts (EventTypes + primary event + transitive DTO)
    ev_types_rel = "Game.Core/Contracts/EventTypes.cs"
    ev_types_raw = builder.put(
        ev_types_rel,
        (
            "namespace Game.Core.Contracts;\n\n"
            "/// <summary>\n"
            "/// Canonical domain event type constants.\n"
            "/// </summary>\n"
            "public static class EventTypes\n"
            "{\n"
            '    public const string RewardGranted = "core.reward.granted";\n'
            "}\n"
        ),
    )
    dto_rel = "Game.Core/Contracts/RewardPayloadDto.cs"
    dto_raw = builder.put(
        dto_rel,
        (
            "namespace Game.Core.Contracts;\n\n"
            "/// <summary>\n"
            "/// Deterministic reward payload DTO.\n"
            "/// </summary>\n"
            "public sealed record RewardPayloadDto(string RewardId, int Amount);\n"
        ),
    )
    ev_rel = "Game.Core/Contracts/RewardGrantedEvent.cs"
    ev_raw = builder.put(
        ev_rel,
        (
            "namespace Game.Core.Contracts;\n\n"
            "/// <summary>\n"
            "/// Raised when a combat reward is granted.\n"
            "/// </summary>\n"
            "/// <remarks>Uses EventTypes.RewardGranted.</remarks>\n"
            "public sealed record RewardGrantedEvent(RewardPayloadDto Payload)\n"
            "{\n"
            "    public const string EventType = EventTypes.RewardGranted;\n"
            "}\n"
        ),
    )

    # Overlay
    ov_rel = "docs/architecture/overlays/PRD-TEST-0001/08/08-reward.md"
    ov_raw = builder.put(
        ov_rel,
        (
            "---\n"
            "PRD-ID: PRD-TEST-0001\n"
            "Title: Reward Flow Overlay\n"
            "ADRs: [ADR-0004]\n"
            "---\n\n"
            "# Reward Slice\n\n"
            "Contract: `Game.Core/Contracts/RewardGrantedEvent.cs`.\n"
        ),
    )

    # Implemented test referenced by MVG manifest
    test_rel = "Game.Core.Tests/RewardMvgTests.cs"
    test_raw = builder.put(
        test_rel,
        (
            "namespace Game.Core.Tests;\n\n"
            "public sealed class RewardMvgTests\n"
            "{\n"
            "    public void RewardFlowPasses() { }\n"
            "}\n"
        ),
    )

    # MVG manifest covering flow-reward with Task 1 and sibling Task 2 (both initially pending)
    mvg_rel = "docs/testing/mvg/reward-mvg.json"
    mvg_doc = {
        "schema_version": "newrouge.mvg-integration.v1",
        "mvg_id": "reward-mvg",
        "coverage": {
            "mode": "pilot",
            "scope_id": "reward-scope",
            "required_flow_ids": ["flow-reward"],
            "excluded_claims": ["Manual animation polish excluded."],
            "blocking_task_ids": [1, 2],
        },
        "flows": [
            {
                "id": "flow-reward",
                "task_ids": [1, 2],
                "outcome": "Reward granted deterministically.",
                "source_paths": [src["gdd_rel"]],
                "test_ids": ["test-reward-domain"],
                "handoffs": [
                    {
                        "producer_task": 2,
                        "consumer_task": 1,
                        "owner_task": 1,
                        "contract_ref": ev_rel,
                        "behavior": "Task 2 produces payload; Task 1 grants reward.",
                        "test_ids": ["test-reward-domain"],
                    }
                ],
            }
        ],
        "tests": [
            {
                "id": "test-reward-domain",
                "kind": "dotnet",
                "evidence_level": "domain-integration",
                "state": "implemented",
                "path": test_rel,
                "selector": "RewardMvgTests",
                "min_tests": 1,
            }
        ],
    }
    mvg_raw = builder.put_json(mvg_rel, mvg_doc)
    mvg_owned = _owned_ref("manifest", mvg_rel, [(mvg_rel, mvg_raw)])

    # Taskmaster triplet: Task 1 depends on Task 2; Task 3 is non-Flow; Task 4 is unrelated.
    master_tasks = [
        {
            "id": 1,
            "title": "Grant combat reward",
            "description": "Implement reward grant flow.",
            "status": "pending",
            "priority": "high",
            "dependencies": [2],
            "overlay": ov_rel,
            "subtasks": [{"id": "1", "title": "Wire reward grant", "status": "pending"}],
        },
        {
            "id": 2,
            "title": "Build reward payload",
            "description": "Produce deterministic reward offer payload.",
            "status": "pending",
            "priority": "high",
            "dependencies": [],
        },
        {
            "id": 3,
            "title": "Static audit governance rule",
            "description": "Enforce deterministic static audit check.",
            "status": "pending",
            "priority": "medium",
            "dependencies": [],
        },
        {
            "id": 4,
            "title": "Unrelated combat task",
            "description": "Independent task in another plan.",
            "status": "pending",
            "priority": "low",
            "dependencies": [],
        },
    ]
    back_tasks = [
        {
            "id": "NG-0001",
            "taskmaster_id": 1,
            "title": "Grant combat reward",
            "description": "Implement reward grant flow.",
            "status": "pending",
            "depends_on": ["NG-0002"],
            "adr_refs": ["ADR-0004"],
            "overlay_refs": [ov_rel],
            "contractRefs": ["core.reward.granted"],
            "acceptance": [f"Reward grant emits core.reward.granted. Refs: {test_rel}"],
        },
        {
            "id": "NG-0002",
            "taskmaster_id": 2,
            "title": "Build reward payload",
            "description": "Produce deterministic reward offer payload.",
            "status": "pending",
            "depends_on": [],
            "adr_refs": ["ADR-0004"],
            "overlay_refs": [],
            "contractRefs": [],
            "acceptance": [f"Payload builds deterministically. Refs: {test_rel}"],
        },
        {
            "id": "NG-0003",
            "taskmaster_id": 3,
            "title": "Static audit governance rule",
            "description": "Enforce deterministic static audit check.",
            "status": "pending",
            "depends_on": [],
            "adr_refs": [],
            "overlay_refs": [],
            "contractRefs": [],
            "acceptance": [f"Static audit passes. Refs: {src['other_v_rel']}"],
        },
        {
            "id": "NG-0004",
            "taskmaster_id": 4,
            "title": "Unrelated combat task",
            "description": "Independent task in another plan.",
            "status": "pending",
            "depends_on": [],
            "adr_refs": [],
            "overlay_refs": [],
            "contractRefs": [],
            "acceptance": [f"Unrelated check passes. Refs: {test_rel}"],
        },
    ]
    gameplay_tasks = [
        {
            "id": "GM-0101",
            "taskmaster_id": 1,
            "title": "Grant combat reward gameplay view",
            "description": "Gameplay acceptance for reward grant.",
            "status": "pending",
            "depends_on": [],
            "acceptance": [f"Player receives reward deterministically. Refs: {test_rel}"],
        }
    ]
    builder.write_triplet(
        master_tasks=master_tasks,
        back_tasks=back_tasks,
        gameplay_tasks=gameplay_tasks,
    )

    # Plan 1: plan-shared (owns state-reward-pool, referenced by plan-reward)
    plan_shared_rel = "docs/planning/b-route/plans/plan-shared/1.json"
    plan_shared_doc = _build_plan_doc(
        plan_id="plan-shared",
        revision=1,
        source_manifest_ref=src["manifest_ref"],
        source_ledger_ref=src["ledger_ref"],
        source_revision=src["source_revision"],
        source_manifest_digest=src["source_manifest_digest"],
        proof_ref=src["proof_ref"],
        requirements=[
            {
                "requirement_id": "REQ-SHARED-1",
                "source_block_ids": ["BLK-REWARD-1"],
                "acceptance_intent": "Shared reward pool state remains authoritative.",
                "non_task_sinks": ["sink-shared-state"],
            }
        ],
        flows=[],
        commands=[],
        states=[
            {
                "id": "state-reward-pool",
                "requirement_ids": ["REQ-SHARED-1"],
                "responsibility": "Owns deterministic reward pool state.",
                "uses": [],
            }
        ],
        logical_references=[],
        requirement_verification=[
            {
                "requirement_id": "REQ-SHARED-1",
                "disposition": "other_verification",
                "flow_id": None,
                "rationale": "Shared state invariant verified by deterministic static rule.",
                "sink_id": "sink-shared-state",
                "verification_ref": src["other_v_rel"],
                "authority_ref": None,
                "evidence_ids": [],
            }
        ],
        requirement_route_memberships=[],
        requirement_evidence=[],
        evidence_source_refs=[src["other_v_owned"]],
    )

    # Plan 2: plan-reward (owns flow-reward + cmd-grant-reward, uses state-reward-pool from plan-shared)
    state_use = {
        "kind": "state",
        "definition_id": "state-reward-pool",
        "owner_plan_id": "plan-shared",
        "owner_revision": 1,
    }
    plan_reward_rel = "docs/planning/b-route/plans/plan-reward/1.json"
    plan_reward_doc = _build_plan_doc(
        plan_id="plan-reward",
        revision=1,
        source_manifest_ref=src["manifest_ref"],
        source_ledger_ref=src["ledger_ref"],
        source_revision=src["source_revision"],
        source_manifest_digest=src["source_manifest_digest"],
        proof_ref=src["proof_ref"],
        requirements=[
            {
                "requirement_id": "REQ-REWARD-1",
                "source_block_ids": ["BLK-REWARD-1"],
                "acceptance_intent": "Grant reward deterministically after combat.",
                "non_task_sinks": [],
            }
        ],
        flows=[_make_flow("flow-reward", ["REQ-REWARD-1"], state_uses=[state_use])],
        commands=[
            {
                "id": "cmd-grant-reward",
                "requirement_ids": ["REQ-REWARD-1"],
                "responsibility": "Execute deterministic reward grant.",
                "uses": [state_use],
            }
        ],
        states=[],
        logical_references=[state_use],
        requirement_verification=[
            {
                "requirement_id": "REQ-REWARD-1",
                "disposition": "flow",
                "flow_id": "flow-reward",
                "rationale": "Verified by flow-reward.",
                "sink_id": None,
                "verification_ref": None,
                "authority_ref": None,
                "evidence_ids": [],
            }
        ],
        requirement_route_memberships=[
            {"requirement_id": "REQ-REWARD-1", "flow_id": "flow-reward", "observable_role": "primary"}
        ],
        requirement_evidence=[],
        evidence_source_refs=[],
    )

    # Plan 3: plan-audit (legal non-Flow other_verification for Task 3)
    plan_audit_rel = "docs/planning/b-route/plans/plan-audit/1.json"
    plan_audit_doc = _build_plan_doc(
        plan_id="plan-audit",
        revision=1,
        source_manifest_ref=src["manifest_ref"],
        source_ledger_ref=src["ledger_ref"],
        source_revision=src["source_revision"],
        source_manifest_digest=src["source_manifest_digest"],
        proof_ref=src["proof_ref"],
        requirements=[
            {
                "requirement_id": "REQ-AUDIT-1",
                "source_block_ids": ["BLK-AUDIT-1"],
                "acceptance_intent": "Static audit governance verified without player Flow.",
                "non_task_sinks": ["sink-static-audit"],
            }
        ],
        flows=[],
        commands=[],
        states=[],
        logical_references=[],
        requirement_verification=[
            {
                "requirement_id": "REQ-AUDIT-1",
                "disposition": "other_verification",
                "flow_id": None,
                "rationale": "Pure static governance rule without player journey Flow.",
                "sink_id": "sink-static-audit",
                "verification_ref": src["other_v_rel"],
                "authority_ref": None,
                "evidence_ids": [],
            }
        ],
        requirement_route_memberships=[],
        requirement_evidence=[],
        evidence_source_refs=[src["other_v_owned"]],
    )

    # Plan 4: plan-unrelated (independent plan for Task 4)
    plan_unrel_rel = "docs/planning/b-route/plans/plan-unrelated/1.json"
    plan_unrel_doc = _build_plan_doc(
        plan_id="plan-unrelated",
        revision=1,
        source_manifest_ref=src["manifest_ref"],
        source_ledger_ref=src["ledger_ref"],
        source_revision=src["source_revision"],
        source_manifest_digest=src["source_manifest_digest"],
        proof_ref=src["proof_ref"],
        requirements=[
            {
                "requirement_id": "REQ-UNREL-1",
                "source_block_ids": ["BLK-COMBAT-1"],
                "acceptance_intent": "Unrelated combat telemetry.",
                "non_task_sinks": ["sink-unrel"],
            }
        ],
        flows=[],
        commands=[],
        states=[],
        logical_references=[],
        requirement_verification=[
            {
                "requirement_id": "REQ-UNREL-1",
                "disposition": "other_verification",
                "flow_id": None,
                "rationale": "Independent telemetry check.",
                "sink_id": "sink-unrel",
                "verification_ref": src["other_v_rel"],
                "authority_ref": None,
                "evidence_ids": [],
            }
        ],
        requirement_route_memberships=[],
        requirement_evidence=[],
        evidence_source_refs=[src["other_v_owned"]],
    )

    # Pre-compute plan refs to build bindings.
    p_shared_ref = _typed_ref(plan_shared_rel, "newrouge.b-route-plan.v1", "plan-shared", 1, _encoded(plan_shared_doc))
    p_reward_ref = _typed_ref(plan_reward_rel, "newrouge.b-route-plan.v1", "plan-reward", 1, _encoded(plan_reward_doc))
    p_audit_ref = _typed_ref(plan_audit_rel, "newrouge.b-route-plan.v1", "plan-audit", 1, _encoded(plan_audit_doc))
    p_unrel_ref = _typed_ref(plan_unrel_rel, "newrouge.b-route-plan.v1", "plan-unrelated", 1, _encoded(plan_unrel_doc))

    # Binding for plan-shared (stage 3C, maps Task 1)
    b_shared_rel = "docs/planning/b-route/bindings/plan-shared/1.json"
    b_shared_doc = _build_binding_doc(
        plan_id="plan-shared",
        binding_revision=1,
        plan_ref=p_shared_ref,
        stage="3C",
        task_mappings=[
            {
                "task_id": 1,
                "view_refs": [
                    {"view": "back", "business_id": "NG-0001"},
                    {"view": "gameplay", "business_id": "GM-0101"},
                ],
                "requirement_ids": ["REQ-SHARED-1"],
                "flow_ids": [],
                "part_kinds": ["domain_rules"],
                "roles": ["consumer"],
                "obligation_ids": ["obl-shared-1"],
            }
        ],
        obligations=[
            {
                "id": "obl-shared-1",
                "requirement_ids": ["REQ-SHARED-1"],
                "flow_ids": [],
                "test_ids": [],
                "responsibility": "Preserve shared reward pool state.",
                "verification_refs": [src["other_v_owned"]],
            }
        ],
        other_verification_refs=[src["other_v_owned"]],
    )

    # Binding for plan-reward (stage 4, maps Task 1 and sibling Task 2, binds MVG manifest)
    b_reward_rel = "docs/planning/b-route/bindings/plan-reward/1.json"
    b_reward_doc = _build_binding_doc(
        plan_id="plan-reward",
        binding_revision=1,
        plan_ref=p_reward_ref,
        stage="4",
        task_mappings=[
            {
                "task_id": 1,
                "view_refs": [
                    {"view": "back", "business_id": "NG-0001"},
                    {"view": "gameplay", "business_id": "GM-0101"},
                ],
                "requirement_ids": ["REQ-REWARD-1"],
                "flow_ids": ["flow-reward"],
                "part_kinds": ["domain_rules", "binding"],
                "roles": ["consumer"],
                "obligation_ids": ["obl-reward-1"],
            },
            {
                "task_id": 2,
                "view_refs": [{"view": "back", "business_id": "NG-0002"}],
                "requirement_ids": ["REQ-REWARD-1"],
                "flow_ids": ["flow-reward"],
                "part_kinds": ["domain_rules"],
                "roles": ["producer"],
                "obligation_ids": ["obl-reward-1"],
            },
        ],
        obligations=[
            {
                "id": "obl-reward-1",
                "requirement_ids": ["REQ-REWARD-1"],
                "flow_ids": ["flow-reward"],
                "test_ids": ["test-reward-domain"],
                "responsibility": "Verify combat reward grant flow end-to-end.",
                "verification_refs": [],
            }
        ],
        implementation_objects=[
            {
                "id": "obj-cmd-grant-reward",
                "kind": "command",
                "availability": "planned",
                "responsible_task_ids": [1],
                "expected_type": "Game.Core.Contracts.RewardGrantedEvent",
                "lifecycle": _stage4_lifecycle(
                    {
                        "owner": "RewardService",
                        "preconditions": ["combat_won"],
                        "postconditions": ["reward_granted"],
                        "invariants": ["deterministic_offer"],
                        "contract_ref": "core.reward.granted",
                    }
                ),
                "target_ref": None,
                "later_checks": ["type", "compile"],
            },
            {
                "id": "obj-state-payload",
                "kind": "read_only_state",
                "availability": "planned",
                "responsible_task_ids": [2],
                "expected_type": "Game.Core.Contracts.RewardPayloadDto",
                "lifecycle": _stage4_lifecycle(
                    {
                        "single_owner": "RewardPayloadBuilder",
                        "read_only_views": ["RewardPayloadDto"],
                        "forbidden_direct_writers": ["adapter", "ui"],
                    }
                ),
                "target_ref": None,
                "later_checks": ["type", "compile"],
            },
        ],
    )
    b_reward_doc["manifest_refs"] = [mvg_owned]

    # Binding for plan-audit (stage 4, non-Flow Task 3, other_verification_refs)
    b_audit_rel = "docs/planning/b-route/bindings/plan-audit/1.json"
    b_audit_doc = _build_binding_doc(
        plan_id="plan-audit",
        binding_revision=1,
        plan_ref=p_audit_ref,
        stage="4",
        task_mappings=[
            {
                "task_id": 3,
                "view_refs": [{"view": "back", "business_id": "NG-0003"}],
                "requirement_ids": ["REQ-AUDIT-1"],
                "flow_ids": [],
                "part_kinds": ["domain_rules"],
                "roles": ["integration_only_owner"],
                "obligation_ids": ["obl-audit-1"],
            }
        ],
        obligations=[
            {
                "id": "obl-audit-1",
                "requirement_ids": ["REQ-AUDIT-1"],
                "flow_ids": [],
                "test_ids": [],
                "responsibility": "Verify deterministic static audit rule.",
                "verification_refs": [src["other_v_owned"]],
            }
        ],
        other_verification_refs=[src["other_v_owned"]],
    )

    # Binding for plan-unrelated (stage 3C, Task 4)
    b_unrel_rel = "docs/planning/b-route/bindings/plan-unrelated/1.json"
    b_unrel_doc = _build_binding_doc(
        plan_id="plan-unrelated",
        binding_revision=1,
        plan_ref=p_unrel_ref,
        stage="3C",
        task_mappings=[
            {
                "task_id": 4,
                "view_refs": [{"view": "back", "business_id": "NG-0004"}],
                "requirement_ids": ["REQ-UNREL-1"],
                "flow_ids": [],
                "part_kinds": ["domain_rules"],
                "roles": ["integration_only_owner"],
                "obligation_ids": ["obl-unrel-1"],
            }
        ],
        obligations=[
            {
                "id": "obl-unrel-1",
                "requirement_ids": ["REQ-UNREL-1"],
                "flow_ids": [],
                "test_ids": [],
                "responsibility": "Unrelated telemetry check.",
                "verification_refs": [src["other_v_owned"]],
            }
        ],
        other_verification_refs=[src["other_v_owned"]],
    )

    b_shared_ref = _typed_ref(b_shared_rel, "newrouge.b-route-binding.v1", "plan-shared", 1, _encoded(b_shared_doc))
    b_reward_ref = _typed_ref(b_reward_rel, "newrouge.b-route-binding.v1", "plan-reward", 1, _encoded(b_reward_doc))
    b_audit_ref = _typed_ref(b_audit_rel, "newrouge.b-route-binding.v1", "plan-audit", 1, _encoded(b_audit_doc))
    b_unrel_ref = _typed_ref(b_unrel_rel, "newrouge.b-route-binding.v1", "plan-unrelated", 1, _encoded(b_unrel_doc))

    origins_tasks = [
        {
            "task_id": 1,
            "source_refs": [src["source_owned"]],
            "plan_refs": [p_reward_ref, p_shared_ref],
            "binding_refs": [b_reward_ref, b_shared_ref],
        },
        {
            "task_id": 2,
            "source_refs": [src["source_owned"]],
            "plan_refs": [p_reward_ref],
            "binding_refs": [b_reward_ref],
        },
        {
            "task_id": 3,
            "source_refs": [src["source_owned"]],
            "plan_refs": [p_audit_ref],
            "binding_refs": [b_audit_ref],
        },
        {
            "task_id": 4,
            "source_refs": [src["source_owned"]],
            "plan_refs": [p_unrel_ref],
            "binding_refs": [b_unrel_ref],
        },
    ]

    # Seal all log files in receipt.authority so clean clones without logs/ verify cleanly.
    authority_pins = [
        (src["manifest_rel"], src["manifest_raw"]),
        (src["ledger_rel"], src["ledger_raw"]),
        (src["proof_rel"], src["proof_raw"]),
    ]

    committed = builder.commit_bundle(
        operation_id="op-base-001",
        plans=[
            (plan_shared_rel, plan_shared_doc),
            (plan_reward_rel, plan_reward_doc),
            (plan_audit_rel, plan_audit_doc),
            (plan_unrel_rel, plan_unrel_doc),
        ],
        bindings=[
            (b_shared_rel, b_shared_doc),
            (b_reward_rel, b_reward_doc),
            (b_audit_rel, b_audit_doc),
            (b_unrel_rel, b_unrel_doc),
        ],
        origins_tasks=origins_tasks,
        authority_pins=authority_pins,
        scope_map={
            "scope-reward": ([plan_shared_rel, plan_reward_rel], [b_shared_rel, b_reward_rel]),
            "scope-audit": ([plan_audit_rel], [b_audit_rel]),
            "scope-unrelated": ([plan_unrel_rel], [b_unrel_rel]),
        },
        catalog_revision=1,
    )

    return {
        "src": src,
        "adr4_rel": adr4_rel,
        "ev_types_rel": ev_types_rel,
        "dto_rel": dto_rel,
        "ev_rel": ev_rel,
        "ov_rel": ov_rel,
        "test_rel": test_rel,
        "mvg_rel": mvg_rel,
        "mvg_doc": mvg_doc,
        "plans": {
            "plan-shared": (plan_shared_rel, plan_shared_doc),
            "plan-reward": (plan_reward_rel, plan_reward_doc),
            "plan-audit": (plan_audit_rel, plan_audit_doc),
            "plan-unrelated": (plan_unrel_rel, plan_unrel_doc),
        },
        "bindings": {
            "plan-shared": (b_shared_rel, b_shared_doc),
            "plan-reward": (b_reward_rel, b_reward_doc),
            "plan-audit": (b_audit_rel, b_audit_doc),
            "plan-unrelated": (b_unrel_rel, b_unrel_doc),
        },
        "origins_tasks": origins_tasks,
        "authority_pins": authority_pins,
        "committed": committed,
    }


def _recommit_template(
    root: Path,
    meta: dict,
    *,
    operation_id: str,
    catalog_revision: int,
    plans: dict[str, tuple[str, dict]],
    bindings: dict[str, tuple[str, dict]],
    origins_tasks: list[dict] | None = None,
    authority_pins: list[tuple[str, bytes]] | None = None,
    allowed_a_operations: list[str] | None = None,
    policy_revision: int = 1,
) -> dict:
    builder = ResolverRepoBuilder(root)
    plan_list = list(plans.values())
    binding_list = list(bindings.values())

    plan_refs = {
        doc["plan_id"]: _typed_ref(rel, "newrouge.b-route-plan.v1", doc["plan_id"], doc["revision"], _encoded(doc))
        for rel, doc in plan_list
    }
    binding_refs = {
        doc["plan_id"]: _typed_ref(
            rel, "newrouge.b-route-binding.v1", doc["plan_id"], doc["binding_revision"], _encoded(doc)
        )
        for rel, doc in binding_list
    }

    if origins_tasks is None:
        src_owned = _owned_ref(
            "authority",
            meta["src"]["gdd_rel"],
            [(meta["src"]["gdd_rel"], (root / meta["src"]["gdd_rel"]).read_bytes())],
        )
        origins_tasks = [
            {
                "task_id": 1,
                "source_refs": [src_owned],
                "plan_refs": [plan_refs["plan-reward"], plan_refs["plan-shared"]],
                "binding_refs": [binding_refs["plan-reward"], binding_refs["plan-shared"]],
            },
            {
                "task_id": 2,
                "source_refs": [src_owned],
                "plan_refs": [plan_refs["plan-reward"]],
                "binding_refs": [binding_refs["plan-reward"]],
            },
            {
                "task_id": 3,
                "source_refs": [src_owned],
                "plan_refs": [plan_refs["plan-audit"]],
                "binding_refs": [binding_refs["plan-audit"]],
            },
            {
                "task_id": 4,
                "source_refs": [src_owned],
                "plan_refs": [plan_refs["plan-unrelated"]],
                "binding_refs": [binding_refs["plan-unrelated"]],
            },
        ]

    # Build committed bundle while keeping policy_revision stable unless explicitly bumped.
    adr_raw = builder.write_adr_0040(valid=True)
    policy_doc = {
        "schema_version": "newrouge.b-route-policy.v1",
        "policy_id": "policy-main",
        "policy_revision": policy_revision,
        "switch_boundary": {
            "default_route": "A",
            "a_write_allowed": True,
            "allowed_a_operations": (
                list(allowed_a_operations) if allowed_a_operations is not None else ["implement", "resume", "route"]
            ),
            "authority_refs": [_owned_ref("adr", resolver.ADR_0040, [(resolver.ADR_0040, adr_raw)])],
        },
        "frozen_a_refs": [],
    }
    policy_raw = builder.put_json(resolver.POLICY_PATH, policy_doc)
    policy_ref = _typed_ref(resolver.POLICY_PATH, "newrouge.b-route-policy.v1", "policy-main", policy_revision, policy_raw)

    plan_raw_by_path: dict[str, bytes] = {}
    plan_refs_by_path: dict[str, dict] = {}
    for rel, doc in plan_list:
        raw = builder.put_json(rel, doc)
        plan_raw_by_path[rel] = raw
        plan_refs_by_path[rel] = _typed_ref(rel, "newrouge.b-route-plan.v1", doc["plan_id"], doc["revision"], raw)

    binding_raw_by_path: dict[str, bytes] = {}
    binding_refs_by_path: dict[str, dict] = {}
    for rel, doc in binding_list:
        raw = builder.put_json(rel, doc)
        binding_raw_by_path[rel] = raw
        binding_refs_by_path[rel] = _typed_ref(
            rel, "newrouge.b-route-binding.v1", doc["plan_id"], doc["binding_revision"], raw
        )

    origins_doc = {
        "schema_version": "newrouge.b-route-origins.v1",
        "origins_id": "task-origins",
        "revision": catalog_revision,
        "tasks": origins_tasks,
        "frozen_legacy_refs": [],
    }
    origins_raw = builder.put_json(resolver.ORIGINS_PATH, origins_doc)
    origins_ref = _typed_ref(
        resolver.ORIGINS_PATH, "newrouge.b-route-origins.v1", "task-origins", catalog_revision, origins_raw
    )

    definition_owners: list[dict] = []
    for rel, doc in plan_list:
        pref = plan_refs_by_path[rel]
        for kind, plural in (("flow", "flows"), ("command", "commands"), ("state", "states")):
            for defn in doc["definitions"][plural]:
                definition_owners.append({"kind": kind, "definition_id": defn["id"], "plan_ref": pref})
    owners_index = {(row["kind"], row["definition_id"]): row for row in definition_owners}
    use_fields = {"kind", "definition_id", "owner_plan_id", "owner_revision"}
    resolved_defs: dict[tuple[str, str], dict] = {}
    for _rel, doc in plan_list:
        for child in records._walk(doc):
            if type(child) is dict and set(child) == use_fields:
                key = (child["kind"], child["definition_id"])
                if key in owners_index:
                    resolved_defs[key] = owners_index[key]

    scope_map = {
        "scope-reward": (
            [plans["plan-shared"][0], plans["plan-reward"][0]],
            [bindings["plan-shared"][0], bindings["plan-reward"][0]],
        ),
        "scope-audit": ([plans["plan-audit"][0]], [bindings["plan-audit"][0]]),
        "scope-unrelated": ([plans["plan-unrelated"][0]], [bindings["plan-unrelated"][0]]),
    }
    scopes = sorted(scope_map.keys())
    targets: list[dict] = []
    for rel, raw in [
        (resolver.POLICY_PATH, policy_raw),
        (resolver.ORIGINS_PATH, origins_raw),
        *list(plan_raw_by_path.items()),
        *list(binding_raw_by_path.items()),
    ]:
        dg = codec.raw_digest(raw)
        targets.append(
            {
                "path": rel,
                "before_digest": None,
                "after_digest": dg,
                "projection_digest": dg,
                "verification_mode": "immutable_bytes",
                "codec_version": None,
            }
        )
    pins = authority_pins if authority_pins is not None else meta["authority_pins"]
    authority_rows = [
        {"path": p, "before_digest": codec.raw_digest(raw), "after_digest": codec.raw_digest(raw)}
        for p, raw in pins
    ]
    receipt_rel = f"docs/planning/b-route/commits/{operation_id}.json"
    receipt_doc = {
        "schema_version": "newrouge.b-route-commit.v1",
        "operation_id": operation_id,
        "revision": 1,
        "operation_digest": codec.canonical_digest({"op": operation_id, "rev": catalog_revision}),
        "scopes": scopes,
        "authority": authority_rows,
        "targets": targets,
        "plan_refs": list(plan_refs_by_path.values()),
        "binding_refs": list(binding_refs_by_path.values()),
        "resolved_definitions": list(resolved_defs.values()),
        "result": {"target_paths": [row["path"] for row in targets], "scope_ids": scopes},
    }
    receipt_raw = builder.put_json(receipt_rel, receipt_doc)
    receipt_ref = _typed_ref(receipt_rel, "newrouge.b-route-commit.v1", operation_id, 1, receipt_raw)
    scope_heads = [
        {
            "scope_id": sid,
            "plan_refs": [plan_refs_by_path[p] for p in scope_map[sid][0]],
            "binding_refs": [binding_refs_by_path[b] for b in scope_map[sid][1]],
            "receipt_ref": receipt_ref,
        }
        for sid in scopes
    ]
    task_index = [
        {"task_id": row["task_id"], "plan_refs": row["plan_refs"], "binding_refs": row["binding_refs"]}
        for row in origins_tasks
    ]
    catalog_doc = {
        "schema_version": "newrouge.b-route-catalog.v1",
        "catalog_id": "catalog",
        "revision": catalog_revision,
        "policy_ref": policy_ref,
        "origins_ref": origins_ref,
        "scope_heads": scope_heads,
        "definition_owners": definition_owners,
        "task_index": task_index,
    }
    catalog_raw = builder.put_json(resolver.CATALOG_PATH, catalog_doc)
    return {"catalog_raw": catalog_raw, "receipt_ref": receipt_ref}


class InputSetResolutionTests(unittest.TestCase):
    """Comprehensive deterministic tests for Story 3.5."""

    _template_dir: tempfile.TemporaryDirectory[str]
    _template_root: Path
    _template_meta: dict

    @classmethod
    def setUpClass(cls) -> None:
        cls._template_dir = tempfile.TemporaryDirectory(prefix="b_route_input_set_tpl_")
        cls._template_root = Path(cls._template_dir.name) / "repo"
        cls._template_root.mkdir(parents=True, exist_ok=True)
        cls._template_meta = _build_base_template(cls._template_root)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._template_dir.cleanup()

    def _clone_repo(self) -> tuple[tempfile.TemporaryDirectory[str], Path, dict]:
        tmp = tempfile.TemporaryDirectory(prefix="b_route_input_set_case_")
        self.addCleanup(tmp.cleanup)
        dst = Path(tmp.name) / "repo"
        shutil.copytree(self._template_root, dst)
        return tmp, dst, copy.deepcopy(self._template_meta)

    def _assert_non_auth_and_diags(self, payload: dict) -> None:
        for flag in AUTH_KEYS:
            self.assertIs(payload[flag], False, flag)
            self.assertIs(payload["authorization"][flag], False, flag)
        for diag in payload["diagnostics"]:
            self.assertEqual(set(diag.keys()), DIAGNOSTIC_KEYS)

    # ------------------------------------------------------------------
    # 1. FULL_SET: complete inventory, clean clone parity, tamper rejection
    # ------------------------------------------------------------------
    def test_01_full_set_b_route_and_clean_clone_parity(self) -> None:
        _tmp, root, meta = self._clone_repo()
        res = input_set.resolve_input_set(root, 1, operation="implement")
        self._assert_non_auth_and_diags(res)
        self.assertTrue(res["ok"], res["diagnostics"])
        self.assertTrue(res["stable"])
        self.assertTrue(res["valid_input_set"])
        self.assertEqual(res["route"], "B")
        self.assertFalse(res["uses_candidate_binding"])
        self.assertIsNone(res["candidate_binding"])
        self.assertIsNotNone(res["input_set_digest"])
        self.assertEqual(res["read_attempts"], 1)
        self.assertFalse(res["uses_global_writer_lock"])

        # Verify every item carries full locator/raw/normalization/codec/normalized metadata.
        categories = {row["category"] for row in res["items"]}
        for required_cat in (
            "source",
            "source_manifest",
            "source_ledger",
            "source_identity",
            "plan",
            "resolved_definitions",
            "binding",
            "stage4_semantics",
            "task_origins",
            "task_definition",
            "dependency_task",
            "dependency_producer",
            "adr",
            "overlay",
            "contract",
            "mvg_manifest",
            "policy",
            "codec",
            "environment",
        ):
            self.assertIn(required_cat, categories, f"missing category {required_cat}")

        for item in res["items"]:
            self.assertEqual(set(item.keys()), input_set._ITEM_REQUIRED_KEYS)
            self.assertRegex(item["raw_digest"], r"^sha256:[0-9a-f]{64}$")
            self.assertRegex(item["normalized_digest"], r"^sha256:[0-9a-f]{64}$")
            self.assertTrue(item["codec_version"])
            self.assertTrue(item["normalization_mode"])
            self.assertIn(item["return_stage"], input_set.STAGE_ORDER)

        # Verify transitive C# contract DTO (RewardPayloadDto.cs) was resolved!
        contract_locs = {row["locator"] for row in res["items"] if row["category"] == "contract"}
        self.assertIn(meta["ev_rel"], contract_locs)
        self.assertIn(meta["dto_rel"], contract_locs)

        # Verify dependency_eligibility reports live status honestly and allows non-done deps.
        dep_elig = res["dependency_eligibility"]
        self.assertEqual(dep_elig["status_authority"], resolver.TRIPLET["master"])
        self.assertEqual(dep_elig["self_live_status"], "pending")
        self.assertFalse(dep_elig["self_done_required"])
        self.assertEqual(dep_elig["direct_dependency_ids"], [2])
        self.assertEqual(dep_elig["transitive_dependency_ids"], [2])
        self.assertFalse(dep_elig["all_dependencies_done"])
        self.assertEqual(dep_elig["non_done_dependency_ids"], [2])
        self.assertTrue(dep_elig["unmet_dependencies_allowed"])

        # Clean clone: delete logs/ completely and verify byte-identical digest + zero logs/ creation!
        shutil.rmtree(root / "logs")
        self.assertFalse((root / "logs").exists())
        clone_res = input_set.resolve_input_set(root, 1, operation="implement")
        self._assert_non_auth_and_diags(clone_res)
        self.assertTrue(clone_res["ok"], clone_res["diagnostics"])
        self.assertTrue(clone_res["stable"])
        self.assertFalse((root / "logs").exists(), "clean clone read-only call must NOT create logs/")
        self.assertEqual(clone_res["input_set_digest"], res["input_set_digest"])
        self.assertTrue(clone_res["clean_clone_sealed_logs"])
        self.assertTrue(any(row["sealed_log"] for row in clone_res["items"]))

        # Clean clone must still live-verify non-log files (tampering GDD fails closed).
        (root / meta["src"]["gdd_rel"]).write_text("# Tampered GDD\n", encoding="utf-8")
        tampered = input_set.resolve_input_set(root, 1, operation="implement")
        self._assert_non_auth_and_diags(tampered)
        self.assertFalse(tampered["ok"])
        self.assertIsNone(tampered["input_set_digest"])
        self.assertEqual(tampered["return_stage"], "3A")

    # ------------------------------------------------------------------
    # 2. FULL_SET: legal non-Flow other_verification & explicit_not_enabled_a
    # ------------------------------------------------------------------
    def test_02_legal_non_flow_other_verification_and_not_enabled_a(self) -> None:
        _tmp, root, meta = self._clone_repo()
        res = input_set.resolve_input_set(root, 3)
        self._assert_non_auth_and_diags(res)
        self.assertTrue(res["ok"], res["diagnostics"])
        self.assertEqual(res["route"], "B")
        cats = {row["category"] for row in res["items"]}
        self.assertIn("other_verification", cats)
        self.assertNotIn("mvg_manifest", cats)

        # Deleting other_verification file blocks fail-closed.
        (root / meta["src"]["other_v_rel"]).unlink()
        blocked = input_set.resolve_input_set(root, 3)
        self._assert_non_auth_and_diags(blocked)
        self.assertFalse(blocked["ok"])
        self.assertIsNone(blocked["input_set_digest"])

        # Pure explicit_not_enabled_a repo (zero B traces + Accepted ADR-0040).
        with tempfile.TemporaryDirectory(prefix="b_route_not_enabled_") as tmp_a:
            root_a = Path(tmp_a)
            b = ResolverRepoBuilder(root_a)
            b.write_adr_0040(valid=True)
            b.write_triplet(
                master_tasks=[{"id": 1, "title": "Legacy Task", "status": "pending", "dependencies": []}],
                back_tasks=[{"id": "NG-0001", "taskmaster_id": 1, "title": "Legacy Task", "status": "pending", "depends_on": []}],
                gameplay_tasks=[],
            )
            res_a = input_set.resolve_input_set(root_a, 1)
            self._assert_non_auth_and_diags(res_a)
            self.assertTrue(res_a["ok"], res_a["diagnostics"])
            self.assertEqual(res_a["route"], "explicit_not_enabled_a")
            self.assertIsNotNone(res_a["input_set_digest"])
            self.assertFalse((root_a / "logs").exists())

    # ------------------------------------------------------------------
    # 3. FULL_SET: explicit --candidate-binding single-slot replacement & guards
    # ------------------------------------------------------------------
    def test_03_candidate_binding_single_slot_replacement_and_rejection(self) -> None:
        _tmp, root, meta = self._clone_repo()
        base = input_set.resolve_input_set(root, 1)
        self.assertTrue(base["ok"])

        # Build a schema-valid uncommitted candidate binding for plan-reward ONLY (rev 2, stage 4).
        cand_doc = copy.deepcopy(meta["bindings"]["plan-reward"][1])
        cand_doc["binding_revision"] = 2
        cand_doc["obligations"][0]["responsibility"] = "Candidate refined reward verification."
        cand_rel = "logs/ci/2026-11-23/candidate-plan-reward.json"
        (root / cand_rel).parent.mkdir(parents=True, exist_ok=True)
        (root / cand_rel).write_bytes(_encoded(cand_doc))

        cand_res = input_set.resolve_input_set(root, 1, candidate_binding=cand_rel)
        self._assert_non_auth_and_diags(cand_res)
        self.assertTrue(cand_res["ok"], cand_res["diagnostics"])
        self.assertTrue(cand_res["uses_candidate_binding"])
        self.assertEqual(cand_res["candidate_binding"]["plan_id"], "plan-reward")
        self.assertEqual(cand_res["candidate_binding"]["binding_revision"], 2)
        self.assertIs(cand_res["candidate_binding"]["committed"], False)
        self.assertNotEqual(cand_res["input_set_digest"], base["input_set_digest"])

        # Verify single-slot replacement: plan-reward is candidate (committed=False), plan-shared stays committed=True!
        bindings_by_loc = {r["locator"]: r for r in cand_res["items"] if r["category"] == "binding"}
        self.assertIs(bindings_by_loc["binding:plan-reward"]["committed"], False)
        self.assertEqual(bindings_by_loc["binding:plan-reward"]["details"]["binding_revision"], 2)
        self.assertIs(bindings_by_loc["binding:plan-shared"]["committed"], True)
        self.assertEqual(bindings_by_loc["binding:plan-shared"]["details"]["binding_revision"], 1)

        # Reject invalid schema (unknown field)
        bad_schema = copy.deepcopy(cand_doc)
        bad_schema["extra_illegal_field"] = True
        bad_schema_rel = "logs/ci/2026-11-23/bad-schema-cand.json"
        (root / bad_schema_rel).write_bytes(_encoded(bad_schema))
        r_bad_schema = input_set.resolve_input_set(root, 1, candidate_binding=bad_schema_rel)
        self.assertFalse(r_bad_schema["ok"])
        self.assertEqual(r_bad_schema["diagnostics"][0]["reason_code"], codec.ReasonCode.UNKNOWN_FIELD.value)

        # Reject mismatched plan_ref digest
        bad_plan = copy.deepcopy(cand_doc)
        bad_plan["plan_ref"]["digest"] = "sha256:" + ("0" * 64)
        bad_plan_rel = "logs/ci/2026-11-23/bad-plan-cand.json"
        (root / bad_plan_rel).write_bytes(_encoded(bad_plan))
        r_bad_plan = input_set.resolve_input_set(root, 1, candidate_binding=bad_plan_rel)
        self.assertFalse(r_bad_plan["ok"])
        self.assertEqual(r_bad_plan["diagnostics"][0]["reason_code"], codec.ReasonCode.REVISION_MISMATCH.value)

        # Reject tampered OwnedRef inside candidate binding
        bad_owned = copy.deepcopy(cand_doc)
        bad_owned["manifest_refs"][0]["files"][0]["raw_digest"] = "sha256:" + ("f" * 64)
        bad_owned_rel = "logs/ci/2026-11-23/bad-owned-cand.json"
        (root / bad_owned_rel).write_bytes(_encoded(bad_owned))
        r_bad_owned = input_set.resolve_input_set(root, 1, candidate_binding=bad_owned_rel)
        self.assertFalse(r_bad_owned["ok"])
        self.assertEqual(r_bad_owned["diagnostics"][0]["reason_code"], codec.ReasonCode.DIGEST_MISMATCH.value)

        # Reject candidate binding for an inapplicable plan_id
        wrong_plan = copy.deepcopy(meta["bindings"]["plan-unrelated"][1])
        wrong_plan["binding_revision"] = 2
        wrong_plan_rel = "logs/ci/2026-11-23/wrong-plan-cand.json"
        (root / wrong_plan_rel).write_bytes(_encoded(wrong_plan))
        r_wrong_plan = input_set.resolve_input_set(root, 1, candidate_binding=wrong_plan_rel)
        self.assertFalse(r_wrong_plan["ok"])
        self.assertEqual(r_wrong_plan["diagnostics"][0]["reason_code"], codec.ReasonCode.MAPPING_MISMATCH.value)

    # ------------------------------------------------------------------
    # 4. STATUS_NOOP: self/sibling status -> done, unrelated Task, other plan
    #    advancing catalog.revision & origins.revision, and Git HEAD advance
    # ------------------------------------------------------------------
    def test_04_status_noop_sibling_done_unrelated_task_other_plan_and_git_head(self) -> None:
        _tmp, root, meta = self._clone_repo()
        base = input_set.resolve_input_set(root, 1)
        self.assertTrue(base["ok"])
        base_digest = base["input_set_digest"]

        # 1) Advance Task 1 status & subtask status + sibling Flow Task 2 status -> done
        #    + modify unrelated Task 4 + add unrelated Task 5.
        master_doc = json.loads((root / resolver.TRIPLET["master"]).read_text(encoding="utf-8"))
        back_doc = json.loads((root / resolver.TRIPLET["back"]).read_text(encoding="utf-8"))
        for row in master_doc["master"]["tasks"]:
            if row["id"] == 1:
                row["status"] = "in-progress"
                row["subtasks"][0]["status"] = "done"
            elif row["id"] == 2:
                row["status"] = "done"
            elif row["id"] == 4:
                row["title"] = "Updated unrelated combat task title"
        master_doc["master"]["tasks"].append(
            {"id": 5, "title": "Brand new unrelated task", "status": "pending", "dependencies": []}
        )
        for row in back_doc:
            if row["taskmaster_id"] == 1:
                row["status"] = "in-progress"
            elif row["taskmaster_id"] == 2:
                row["status"] = "done"
            elif row["taskmaster_id"] == 4:
                row["title"] = "Updated unrelated combat task title"
        back_doc.append(
            {
                "id": "NG-0005",
                "taskmaster_id": 5,
                "title": "Brand new unrelated task",
                "status": "pending",
                "depends_on": [],
            }
        )
        (root / resolver.TRIPLET["master"]).write_bytes(_encoded(master_doc))
        (root / resolver.TRIPLET["back"]).write_bytes(_encoded(back_doc))

        # 2) Advance unrelated plan-unrelated to rev 2 -> bumps origins.revision & catalog.revision to 2!
        new_plans = copy.deepcopy(meta["plans"])
        new_bindings = copy.deepcopy(meta["bindings"])
        u_doc = copy.deepcopy(new_plans["plan-unrelated"][1])
        u_doc["revision"] = 2
        u_doc["lineage"]["change_summary"] = "Unrelated plan rev 2."
        u_rel = "docs/planning/b-route/plans/plan-unrelated/2.json"
        new_plans["plan-unrelated"] = (u_rel, u_doc)
        u_ref = _typed_ref(u_rel, "newrouge.b-route-plan.v1", "plan-unrelated", 2, _encoded(u_doc))
        ub_doc = copy.deepcopy(new_bindings["plan-unrelated"][1])
        ub_doc["binding_revision"] = 2
        ub_doc["plan_ref"] = u_ref
        ub_rel = "docs/planning/b-route/bindings/plan-unrelated/2.json"
        new_bindings["plan-unrelated"] = (ub_rel, ub_doc)
        _recommit_template(
            root,
            meta,
            operation_id="op-unrelated-rev2",
            catalog_revision=2,
            plans=new_plans,
            bindings=new_bindings,
        )

        # 3) Advance Git HEAD with a real commit on an unrelated file.
        git_env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        }
        subprocess.run(["git", "init"], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (root / "UNRELATED_NOTE.txt").write_text("v1\n", encoding="utf-8")
        subprocess.run(["git", "add", "UNRELATED_NOTE.txt"], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "commit", "-m", "v1"], cwd=root, env=git_env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        (root / "UNRELATED_NOTE.txt").write_text("v2\n", encoding="utf-8")
        subprocess.run(["git", "add", "UNRELATED_NOTE.txt"], cwd=root, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["git", "commit", "-m", "v2"], cwd=root, env=git_env, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        # Re-resolve Task 1 against baseline -> MUST remain 100% FRESH and identical digest!
        after = input_set.resolve_input_set(root, 1, baseline=base)
        self._assert_non_auth_and_diags(after)
        self.assertTrue(after["ok"], after["diagnostics"])
        self.assertTrue(after["stable"])
        self.assertEqual(after["input_set_digest"], base_digest)
        self.assertTrue(after["freshness"]["compared"])
        self.assertTrue(after["freshness"]["fresh"])
        self.assertEqual(after["freshness"]["status"], "fresh")
        self.assertEqual(after["freshness"]["invalidated_items"], [])
        self.assertIsNone(after["return_stage"])

        # Live dependency eligibility reflects Task 2 -> done and Task 1 -> in-progress in real time!
        self.assertEqual(after["dependency_eligibility"]["self_live_status"], "in-progress")
        self.assertTrue(after["dependency_eligibility"]["all_dependencies_done"])
        self.assertEqual(after["dependency_eligibility"]["dependencies"][0]["live_status"], "done")

    # ------------------------------------------------------------------
    # 5. REL_INVALID: all 5 return_stage values (3A, 3B, 3C, 4, 5)
    # ------------------------------------------------------------------
    def test_05_rel_invalid_all_five_return_stages(self) -> None:
        # --- Stage 3A: source / manifest / ledger revision change ---
        _tmp_3a, root_3a, meta_3a = self._clone_repo()
        base_3a = input_set.resolve_input_set(root_3a, 1)
        self.assertTrue(base_3a["ok"])

        gdd_rel = meta_3a["src"]["gdd_rel"]
        new_gdd_raw = b"# Reward v2\n\nUpdated source rules.\n"
        (root_3a / gdd_rel).write_bytes(new_gdd_raw)
        new_src_digest = codec.raw_digest(new_gdd_raw)
        new_m_raw = _encoded(
            {
                "schema_version": "chapter3.source-manifest.v1",
                "source_revision": "src-rev-002",
                "manifest_sha256": new_src_digest,
                "sources": [{"path": gdd_rel, "raw_digest": new_src_digest}],
            }
        )
        new_l_raw = _encoded(
            {
                "schema_version": "chapter3.source-blocks.v1",
                "source_revision": "src-rev-002",
                "source_manifest_sha256": new_src_digest,
                "blocks": [
                    {"block_id": "BLK-REWARD-1", "path": gdd_rel},
                    {"block_id": "BLK-AUDIT-1", "path": gdd_rel},
                    {"block_id": "BLK-DEFER-1", "path": gdd_rel},
                    {"block_id": "BLK-COMBAT-1", "path": gdd_rel},
                ],
            }
        )
        new_m_rel = "logs/ci/source-3a/source-manifest-v2.json"
        new_l_rel = "logs/ci/source-3a/source-blocks-v2.json"
        (root_3a / new_m_rel).write_bytes(new_m_raw)
        (root_3a / new_l_rel).write_bytes(new_l_raw)
        new_m_ref = _owned_ref("source_manifest", new_m_rel, [(new_m_rel, new_m_raw)])
        new_l_ref = _owned_ref("source_ledger", new_l_rel, [(new_l_rel, new_l_raw)])

        plans_3a = copy.deepcopy(meta_3a["plans"])
        bindings_3a = copy.deepcopy(meta_3a["bindings"])
        p_rew = copy.deepcopy(plans_3a["plan-reward"][1])
        p_rew["revision"] = 2
        p_rew["source_identity"] = {
            "manifest_ref": new_m_ref,
            "ledger_ref": new_l_ref,
            "source_revision": "src-rev-002",
            "source_manifest_digest": new_src_digest,
        }
        p_rew_rel = "docs/planning/b-route/plans/plan-reward/2.json"
        plans_3a["plan-reward"] = (p_rew_rel, p_rew)
        p_rew_ref = _typed_ref(p_rew_rel, "newrouge.b-route-plan.v1", "plan-reward", 2, _encoded(p_rew))
        b_rew = copy.deepcopy(bindings_3a["plan-reward"][1])
        b_rew["binding_revision"] = 2
        b_rew["plan_ref"] = p_rew_ref
        b_rew_rel = "docs/planning/b-route/bindings/plan-reward/2.json"
        bindings_3a["plan-reward"] = (b_rew_rel, b_rew)
        _recommit_template(
            root_3a,
            meta_3a,
            operation_id="op-src-3a-rev2",
            catalog_revision=2,
            plans=plans_3a,
            bindings=bindings_3a,
            authority_pins=[
                *meta_3a["authority_pins"],
                (new_m_rel, new_m_raw),
                (new_l_rel, new_l_raw),
            ],
        )
        res_3a = input_set.resolve_input_set(root_3a, 1, baseline=base_3a)
        self.assertFalse(res_3a["ok"])
        self.assertTrue(res_3a["valid_input_set"])
        self.assertFalse(res_3a["freshness"]["fresh"])
        self.assertEqual(res_3a["return_stage"], "3A")

        # --- Stage 3B: plan semantic change (same source_identity) ---
        _tmp_3b, root_3b, meta_3b = self._clone_repo()
        base_3b = input_set.resolve_input_set(root_3b, 1)
        plans_3b = copy.deepcopy(meta_3b["plans"])
        bindings_3b = copy.deepcopy(meta_3b["bindings"])
        p_rew_3b = copy.deepcopy(plans_3b["plan-reward"][1])
        p_rew_3b["revision"] = 2
        p_rew_3b["definitions"]["flows"][0]["observable_result"] = "observable:flow-reward-v2"
        p_rew_3b_rel = "docs/planning/b-route/plans/plan-reward/2.json"
        plans_3b["plan-reward"] = (p_rew_3b_rel, p_rew_3b)
        p_rew_3b_ref = _typed_ref(p_rew_3b_rel, "newrouge.b-route-plan.v1", "plan-reward", 2, _encoded(p_rew_3b))
        b_rew_3b = copy.deepcopy(bindings_3b["plan-reward"][1])
        b_rew_3b["binding_revision"] = 2
        b_rew_3b["plan_ref"] = p_rew_3b_ref
        b_rew_3b_rel = "docs/planning/b-route/bindings/plan-reward/2.json"
        bindings_3b["plan-reward"] = (b_rew_3b_rel, b_rew_3b)
        _recommit_template(
            root_3b,
            meta_3b,
            operation_id="op-plan-3b-rev2",
            catalog_revision=2,
            plans=plans_3b,
            bindings=bindings_3b,
        )
        res_3b = input_set.resolve_input_set(root_3b, 1, baseline=base_3b)
        self.assertFalse(res_3b["ok"])
        self.assertTrue(res_3b["valid_input_set"])
        self.assertEqual(res_3b["return_stage"], "3B")

        # --- Stage 3C: Task Acceptance / dependency definition change ---
        _tmp_3c, root_3c, meta_3c = self._clone_repo()
        base_3c = input_set.resolve_input_set(root_3c, 1)
        back_3c = json.loads((root_3c / resolver.TRIPLET["back"]).read_text(encoding="utf-8"))
        back_3c[0]["acceptance"].append(f"Reward choice locks deterministically. Refs: {meta_3c['test_rel']}")
        (root_3c / resolver.TRIPLET["back"]).write_bytes(_encoded(back_3c))
        res_3c = input_set.resolve_input_set(root_3c, 1, baseline=base_3c)
        self.assertFalse(res_3c["ok"])
        self.assertTrue(res_3c["valid_input_set"])
        self.assertEqual(res_3c["return_stage"], "3C")

        # --- Stage 4: Contract / ADR / Overlay change ---
        _tmp_4, root_4, meta_4 = self._clone_repo()
        base_4 = input_set.resolve_input_set(root_4, 1)
        (root_4 / meta_4["dto_rel"]).write_text(
            "namespace Game.Core.Contracts;\n\npublic sealed record RewardPayloadDto(string RewardId, int Amount, int Tier);\n",
            encoding="utf-8",
        )
        res_4 = input_set.resolve_input_set(root_4, 1, baseline=base_4)
        self.assertFalse(res_4["ok"])
        self.assertTrue(res_4["valid_input_set"])
        self.assertEqual(res_4["return_stage"], "4")
        self.assertTrue(any(row["locator"] == meta_4["dto_rel"] for row in res_4["freshness"]["invalidated_items"]))

        # --- Stage 5: MVG manifest / policy / rules environment change ---
        _tmp_5, root_5, meta_5 = self._clone_repo()
        base_5 = input_set.resolve_input_set(root_5, 1)
        mvg_5 = copy.deepcopy(meta_5["mvg_doc"])
        mvg_5["tests"][0]["min_tests"] = 2
        mvg_5_raw = _encoded(mvg_5)
        (root_5 / meta_5["mvg_rel"]).write_bytes(mvg_5_raw)
        mvg_5_owned = _owned_ref("manifest", meta_5["mvg_rel"], [(meta_5["mvg_rel"], mvg_5_raw)])
        cand_5 = copy.deepcopy(meta_5["bindings"]["plan-reward"][1])
        cand_5["stage"] = "5"
        cand_5["binding_revision"] = 2
        cand_5["manifest_refs"] = [mvg_5_owned]
        bindings_5 = copy.deepcopy(meta_5["bindings"])
        bindings_5["plan-reward"] = ("docs/planning/b-route/bindings/plan-reward/2.json", cand_5)
        _recommit_template(
            root_5,
            meta_5,
            operation_id="op-mvg-stage5-rev2",
            catalog_revision=2,
            plans=meta_5["plans"],
            bindings=bindings_5,
        )
        res_5 = input_set.resolve_input_set(root_5, 1, baseline=base_5)
        self.assertFalse(res_5["ok"])
        self.assertTrue(res_5["valid_input_set"])
        self.assertEqual(res_5["return_stage"], "5")

        # Also verify rules/environment change triggers return_stage="5"!
        _tmp_env, root_env, _meta_env = self._clone_repo()
        base_env = input_set.resolve_input_set(root_env, 1)
        with patch.object(adoption_review, "policy_observations", return_value=("sha256:" + ("a" * 64), {})):
            res_env = input_set.resolve_input_set(root_env, 1, baseline=base_env)
        self.assertFalse(res_env["ok"])
        self.assertTrue(res_env["valid_input_set"])
        self.assertEqual(res_env["return_stage"], "5")

    # ------------------------------------------------------------------
    # 6. REL_INVALID error path: unknown and cyclic dependency rejection
    # ------------------------------------------------------------------
    def test_06_unknown_and_cyclic_dependency_rejection(self) -> None:
        # Unknown integer dependency
        _t1, r1, _m1 = self._clone_repo()
        m1 = json.loads((r1 / resolver.TRIPLET["master"]).read_text(encoding="utf-8"))
        m1["master"]["tasks"][0]["dependencies"] = [999]
        (r1 / resolver.TRIPLET["master"]).write_bytes(_encoded(m1))
        res_u1 = input_set.resolve_input_set(r1, 1)
        self._assert_non_auth_and_diags(res_u1)
        self.assertFalse(res_u1["ok"])
        self.assertIsNone(res_u1["input_set_digest"])
        self.assertEqual(res_u1["diagnostics"][0]["reason_code"], codec.ReasonCode.UNKNOWN_ENTITY.value)
        self.assertEqual(res_u1["return_stage"], "3C")

        # Unknown business-view dependency
        _t2, r2, _m2 = self._clone_repo()
        b2 = json.loads((r2 / resolver.TRIPLET["back"]).read_text(encoding="utf-8"))
        b2[0]["depends_on"] = ["NG-9999"]
        (r2 / resolver.TRIPLET["back"]).write_bytes(_encoded(b2))
        res_u2 = input_set.resolve_input_set(r2, 1)
        self.assertFalse(res_u2["ok"])
        self.assertEqual(res_u2["diagnostics"][0]["reason_code"], codec.ReasonCode.UNKNOWN_ENTITY.value)

        # Direct self-cycle Task 1 -> Task 1
        _t3, r3, _m3 = self._clone_repo()
        m3 = json.loads((r3 / resolver.TRIPLET["master"]).read_text(encoding="utf-8"))
        m3["master"]["tasks"][0]["dependencies"] = [1]
        (r3 / resolver.TRIPLET["master"]).write_bytes(_encoded(m3))
        res_c1 = input_set.resolve_input_set(r3, 1)
        self.assertFalse(res_c1["ok"])
        self.assertEqual(res_c1["diagnostics"][0]["reason_code"], codec.ReasonCode.DIGEST_CYCLE.value)
        self.assertEqual(res_c1["return_stage"], "3C")

        # Transitive cycle Task 1 -> Task 2 -> Task 1
        _t4, r4, _m4 = self._clone_repo()
        m4 = json.loads((r4 / resolver.TRIPLET["master"]).read_text(encoding="utf-8"))
        m4["master"]["tasks"][1]["dependencies"] = [1]
        (r4 / resolver.TRIPLET["master"]).write_bytes(_encoded(m4))
        res_c2 = input_set.resolve_input_set(r4, 1)
        self.assertFalse(res_c2["ok"])
        self.assertEqual(res_c2["diagnostics"][0]["reason_code"], codec.ReasonCode.DIGEST_CYCLE.value)
        self.assertEqual(res_c2["return_stage"], "3C")

    # ------------------------------------------------------------------
    # 7. DRIFT_LOCK: transient drift retry, persistent drift, and pending
    # ------------------------------------------------------------------
    def test_07_drift_reread_convergence_persistent_drift_and_pending(self) -> None:
        _t1, root, _m1 = self._clone_repo()
        state = {"count": 0}

        def _transient_mutate(attempt: int) -> None:
            state["count"] += 1
            if attempt == 1:
                doc = json.loads((root / resolver.TRIPLET["master"]).read_text(encoding="utf-8"))
                doc["master"]["tasks"][3]["title"] = "Transient write during attempt 1"
                (root / resolver.TRIPLET["master"]).write_bytes(_encoded(doc))

        res_conv = input_set.resolve_input_set(root, 1, max_attempts=3, before_reread=_transient_mutate)
        self._assert_non_auth_and_diags(res_conv)
        self.assertTrue(res_conv["ok"], res_conv["diagnostics"])
        self.assertTrue(res_conv["stable"])
        self.assertEqual(res_conv["read_attempts"], 2)

        # Persistent drift across all attempts must fail closed.
        def _persistent_mutate(attempt: int) -> None:
            doc = json.loads((root / resolver.TRIPLET["master"]).read_text(encoding="utf-8"))
            doc["master"]["tasks"][3]["title"] = f"Persistent write attempt {attempt}"
            (root / resolver.TRIPLET["master"]).write_bytes(_encoded(doc))

        res_drift = input_set.resolve_input_set(root, 1, max_attempts=3, before_reread=_persistent_mutate)
        self._assert_non_auth_and_diags(res_drift)
        self.assertFalse(res_drift["ok"])
        self.assertFalse(res_drift["stable"])
        self.assertIsNone(res_drift["input_set_digest"])
        self.assertEqual(res_drift["read_attempts"], 3)
        self.assertTrue(any(d["reason_code"] == codec.ReasonCode.FILE_CHANGED.value for d in res_drift["diagnostics"]))

        # Overlapping unapplied prepared operation on task:1 blocks with PENDING.
        _t2, root_p, _m2 = self._clone_repo()
        _create_unapplied_operation(root_p, operation_id="op-overlap-t1", scope_ids=["task:1"])
        res_pend = input_set.resolve_input_set(root_p, 1)
        self.assertFalse(res_pend["ok"])
        self.assertEqual(res_pend["diagnostics"][0]["reason_code"], codec.ReasonCode.PENDING.value)

        # Non-overlapping unapplied prepared operation on task:4 is allowed.
        _t3, root_no, _m3 = self._clone_repo()
        _create_unapplied_operation(root_no, operation_id="op-other-t4", scope_ids=["task:4"])
        res_no = input_set.resolve_input_set(root_no, 1)
        self.assertTrue(res_no["ok"], res_no["diagnostics"])

        # Legacy capability-apply.pending.json blocks conservatively.
        _t4, root_leg, _m4 = self._clone_repo()
        cap_p = root_leg / op_scope.CAP_PENDING
        cap_p.parent.mkdir(parents=True, exist_ok=True)
        cap_p.write_text('{"run_id":"r1","journal_path":"logs/ci/capability-planning/r1/apply-journal.json"}\n', encoding="utf-8")
        res_leg = input_set.resolve_input_set(root_leg, 1)
        self.assertFalse(res_leg["ok"])

    # ------------------------------------------------------------------
    # 8. DRIFT_LOCK: guarded_input_set (business_guard review_only=True + revalidate)
    # ------------------------------------------------------------------
    def test_08_guarded_input_set_business_scope_only_and_revalidate(self) -> None:
        _tmp, root, meta = self._clone_repo()
        captured_guard_calls: list[dict] = []
        orig_business_guard = op_scope.business_guard

        @contextlib.contextmanager
        def _spy_business_guard(r, scope_ids, *, operation_id=None, compensation_frozen=None, review_only=False):
            captured_guard_calls.append(
                {
                    "scope_ids": tuple(scope_ids),
                    "review_only": review_only,
                    "has_global_writer": op_scope.WRITER_SCOPE in scope_ids,
                }
            )
            with orig_business_guard(
                r,
                scope_ids,
                operation_id=operation_id,
                compensation_frozen=compensation_frozen,
                review_only=review_only,
            ):
                yield

        with patch.object(op_scope, "business_guard", side_effect=_spy_business_guard):
            with input_set.guarded_input_set(root, 1) as handle:
                self.assertEqual(len(captured_guard_calls), 1)
                self.assertIs(captured_guard_calls[0]["review_only"], True)
                self.assertIs(captured_guard_calls[0]["has_global_writer"], False)
                self.assertEqual(handle.lock_mode, "scope")
                self.assertFalse(handle.uses_global_writer_lock)
                self.assertNotIn(op_scope.WRITER_SCOPE, handle.scope_ids)

                # Confirm writer:planning lock dir was NOT created!
                writer_lock_dir = root / op_scope.STORE / "locks" / "scopes" / op_scope._hash(op_scope.WRITER_SCOPE)
                self.assertFalse(writer_lock_dir.exists())

                # Sibling Task 2 status -> done inside lease keeps revalidate() passing!
                m_doc = json.loads((root / resolver.TRIPLET["master"]).read_text(encoding="utf-8"))
                m_doc["master"]["tasks"][1]["status"] = "done"
                (root / resolver.TRIPLET["master"]).write_bytes(_encoded(m_doc))
                reval = handle.revalidate()
                self.assertTrue(reval["ok"])
                self.assertEqual(reval["input_set_digest"], handle.input_set_digest)
                self.assertTrue(reval["dependency_eligibility"]["all_dependencies_done"])

                # Mutating a relevant contract inside lease causes revalidate() to fail closed with INPUT_STALE!
                (root / meta["dto_rel"]).write_text(
                    "namespace Game.Core.Contracts;\n\npublic sealed record RewardPayloadDto(string RewardId, int Amount, bool Mutated);\n",
                    encoding="utf-8",
                )
                with self.assertRaises(codec.CodecError) as ctx:
                    handle.revalidate()
                self.assertEqual(ctx.exception.diagnostic.reason_code, codec.ReasonCode.INPUT_STALE)

        # Entry revalidation also catches drift occurring between pre-lock resolve and lease entry!
        _tmp2, root2, meta2 = self._clone_repo()

        def _drift_before_entry() -> None:
            (root2 / meta2["dto_rel"]).write_text(
                "namespace Game.Core.Contracts;\n\npublic sealed record RewardPayloadDto(string RewardId, int Amount, bool EntryDrift);\n",
                encoding="utf-8",
            )

        with self.assertRaises(codec.CodecError) as entry_ctx:
            with input_set.guarded_input_set(root2, 1, before_enter_revalidate=_drift_before_entry):
                pass
        self.assertEqual(entry_ctx.exception.diagnostic.reason_code, codec.ReasonCode.INPUT_STALE)

    # ------------------------------------------------------------------
    # 9. CALLER_PARITY: Python API, direct CLI, dev_cli, --report, policy anchor
    # ------------------------------------------------------------------
    def test_09_caller_parity_cli_dev_cli_report_and_policy_anchor(self) -> None:
        _tmp, root, meta = self._clone_repo()
        shutil.rmtree(root / "logs")
        self.assertFalse((root / "logs").exists())

        api_res = input_set.resolve_input_set(root, 1, operation="implement")
        self.assertTrue(api_res["ok"])
        self.assertFalse((root / "logs").exists())

        # Direct CLI
        buf_direct = io.StringIO()
        with contextlib.redirect_stdout(buf_direct):
            rc_direct = input_set_cli.main(["--root", str(root), "--task-id", "1", "--operation", "implement"])
        self.assertEqual(rc_direct, 0)
        direct_res = json.loads(buf_direct.getvalue())
        self.assertFalse((root / "logs").exists())

        # dev_cli.main(["b-route-input-set", ...])
        buf_dev = io.StringIO()
        with contextlib.redirect_stdout(buf_dev):
            rc_dev = dev_cli.main(["b-route-input-set", "--root", str(root), "--task-id", "1", "--operation", "implement"])
        self.assertEqual(rc_dev, 0)
        dev_res = json.loads(buf_dev.getvalue())
        self.assertFalse((root / "logs").exists())

        # Strict structural and digest parity across all three callers!
        self.assertEqual(direct_res, api_res)
        self.assertEqual(dev_res, api_res)

        # --report writes once under logs/ci/... and refuses overwrite or escape.
        report_rel = "logs/ci/2026-11-23/input-set-t1.json"
        buf_rep = io.StringIO()
        with contextlib.redirect_stdout(buf_rep):
            rc_rep = dev_cli.main(["b-route-input-set", "--root", str(root), "--task-id", "1", "--report", report_rel])
        self.assertEqual(rc_rep, 0)
        rep_out = json.loads(buf_rep.getvalue())
        self.assertEqual(rep_out["report_path"], report_rel)
        self.assertTrue((root / report_rel).is_file())

        # Refuses overwrite
        buf_dup = io.StringIO()
        with contextlib.redirect_stdout(buf_dup):
            rc_dup = dev_cli.main(["b-route-input-set", "--root", str(root), "--task-id", "1", "--report", report_rel])
        self.assertEqual(rc_dup, 2)
        self.assertEqual(json.loads(buf_dup.getvalue())["diagnostics"][0]["reason_code"], codec.ReasonCode.CONFLICT.value)

        # Refuses out-of-bounds report path
        buf_esc = io.StringIO()
        with contextlib.redirect_stdout(buf_esc):
            rc_esc = dev_cli.main(["b-route-input-set", "--root", str(root), "--task-id", "1", "--report", "docs/illegal.json"])
        self.assertEqual(rc_esc, 2)
        self.assertEqual(json.loads(buf_esc.getvalue())["diagnostics"][0]["reason_code"], codec.ReasonCode.UNSAFE_PATH.value)

        # --baseline fresh (exit 0) and --lock-mode scope (exit 0)
        buf_fresh = io.StringIO()
        with contextlib.redirect_stdout(buf_fresh):
            rc_fresh = dev_cli.main([
                "b-route-input-set",
                "--root",
                str(root),
                "--task-id",
                "1",
                "--baseline",
                report_rel,
                "--lock-mode",
                "scope",
            ])
        self.assertEqual(rc_fresh, 0)
        fresh_out = json.loads(buf_fresh.getvalue())
        self.assertTrue(fresh_out["freshness"]["fresh"])
        self.assertEqual(fresh_out["lock_mode"], "scope")

        # Mutate contract -> --baseline returns exit 1 with return_stage="4"
        (root / meta["dto_rel"]).write_text(
            "namespace Game.Core.Contracts;\n\npublic sealed record RewardPayloadDto(string RewardId, int Amount, string Extra);\n",
            encoding="utf-8",
        )
        buf_stale = io.StringIO()
        with contextlib.redirect_stdout(buf_stale):
            rc_stale = dev_cli.main(["b-route-input-set", "--root", str(root), "--task-id", "1", "--baseline", report_rel])
        self.assertEqual(rc_stale, 1)
        stale_out = json.loads(buf_stale.getvalue())
        self.assertFalse(stale_out["ok"])
        self.assertFalse(stale_out["freshness"]["fresh"])
        self.assertEqual(stale_out["return_stage"], "4")

        # Builder rejects write/apply flags and _b_route_input_set.py is anchored in policy_observations.
        class _BadArgs:
            root = "."
            task_id = "1"
            write = True
            apply = False

        with self.assertRaises(ValueError):
            dev_cli_builders.build_b_route_input_set_cmd(_BadArgs())

        _identity, policy_files = adoption_review.policy_observations()
        self.assertTrue(any(Path(p).name == "_b_route_input_set.py" for p in policy_files))

    # ------------------------------------------------------------------
    # 10. Governed Frozen-A (route="A") + reject --candidate-binding on non-B
    # ------------------------------------------------------------------
    def test_10_governed_frozen_a_route_and_reject_candidate_binding_on_non_b(self) -> None:
        inv_mod = importlib.import_module("test_b_route_inventory")
        inv_fixture = inv_mod.InventoryTests(methodName="runTest")
        inv_fixture.setUp()
        self.addCleanup(inv_fixture.tearDown)
        root = inv_fixture.root
        epics = inv_fixture.epics

        master = inv_fixture.load(resolver.TRIPLET["master"])
        master["master"]["tasks"][0]["subtasks"] = [{"id": "1.1", "title": "Sub A", "status": "pending"}]
        inv_fixture.dump(resolver.TRIPLET["master"], master)

        capture = protection.collect_protection(root, epics)
        self.assertTrue(capture.snapshot["stable"], capture.snapshot["diagnostics"])
        snap_dir = root / "logs/ci/2026-11-23/b-route-protection/frozen-a-inputset"
        snap_dir.mkdir(parents=True, exist_ok=False)
        protection.write_capture(snap_dir, capture)
        snap_rel = "logs/ci/2026-11-23/b-route-protection/frozen-a-inputset/snapshot.json"
        snap_raw = (root / snap_rel).read_bytes()

        frozen_ids = sorted(t["id"] for t in master["master"]["tasks"])
        frozen_tid = frozen_ids[0]
        scope_doc = {
            "schema_version": "chapter3.task-scope.v1",
            "mode": "reconcile-existing-only",
            "master_path": resolver.TRIPLET["master"],
            "expected_master_task_count": len(frozen_ids),
            "allowed_numeric_task_ids": frozen_ids,
        }
        builder = ResolverRepoBuilder(root)
        scope_raw = builder.put_json(resolver.CHAPTER3_TASK_SCOPE, scope_doc)

        next_tid = max(frozen_ids) + 1
        master["master"]["tasks"].append({"id": next_tid, "title": "New B Task", "status": "pending", "dependencies": []})
        back = inv_fixture.load(resolver.TRIPLET["back"])
        back.append({"id": f"NG-{next_tid:04d}", "taskmaster_id": next_tid, "title": "New B Task", "status": "pending"})
        inv_fixture.dump(resolver.TRIPLET["master"], master)
        inv_fixture.dump(resolver.TRIPLET["back"], back)

        src = builder.write_sources_and_proof(use_log_proof=True)
        plan_rel = "docs/planning/b-route/plans/plan-b/1.json"
        plan_doc = _build_plan_doc(
            plan_id="plan-b",
            revision=1,
            source_manifest_ref=src["manifest_ref"],
            source_ledger_ref=src["ledger_ref"],
            source_revision=src["source_revision"],
            source_manifest_digest=src["source_manifest_digest"],
            proof_ref=src["proof_ref"],
            requirements=[
                {
                    "requirement_id": "REQ-B-1",
                    "source_block_ids": ["BLK-REWARD-1"],
                    "acceptance_intent": "B task requirement.",
                    "non_task_sinks": [],
                }
            ],
            flows=[_make_flow("flow-b", ["REQ-B-1"])],
            commands=[],
            states=[],
            logical_references=[],
            requirement_verification=[
                {
                    "requirement_id": "REQ-B-1",
                    "disposition": "flow",
                    "flow_id": "flow-b",
                    "rationale": "B flow.",
                    "sink_id": None,
                    "verification_ref": None,
                    "authority_ref": None,
                    "evidence_ids": [],
                }
            ],
            requirement_route_memberships=[{"requirement_id": "REQ-B-1", "flow_id": "flow-b", "observable_role": "primary"}],
            requirement_evidence=[],
            evidence_source_refs=[],
        )
        plan_raw = builder.put_json(plan_rel, plan_doc)
        plan_ref = _typed_ref(plan_rel, "newrouge.b-route-plan.v1", "plan-b", 1, plan_raw)

        binding_rel = "docs/planning/b-route/bindings/plan-b/1.json"
        binding_doc = _build_binding_doc(
            plan_id="plan-b",
            binding_revision=1,
            plan_ref=plan_ref,
            stage="3C",
            task_mappings=[
                {
                    "task_id": next_tid,
                    "view_refs": [{"view": "back", "business_id": f"NG-{next_tid:04d}"}],
                    "requirement_ids": ["REQ-B-1"],
                    "flow_ids": ["flow-b"],
                    "part_kinds": ["domain_rules"],
                    "roles": ["producer"],
                    "obligation_ids": [],
                }
            ],
            obligations=[],
        )
        binding_raw = builder.put_json(binding_rel, binding_doc)
        binding_ref = _typed_ref(binding_rel, "newrouge.b-route-binding.v1", "plan-b", 1, binding_raw)

        frozen_a_refs = [
            _owned_ref("frozen_a_inventory", snap_rel, [(snap_rel, snap_raw)]),
            _owned_ref("authority", resolver.CHAPTER3_TASK_SCOPE, [(resolver.CHAPTER3_TASK_SCOPE, scope_raw)]),
        ]
        builder.commit_bundle(
            operation_id="op-frozen-a-iset",
            plans=[(plan_rel, plan_doc)],
            bindings=[(binding_rel, binding_doc)],
            origins_tasks=[
                {
                    "task_id": next_tid,
                    "source_refs": [src["source_owned"]],
                    "plan_refs": [plan_ref],
                    "binding_refs": [binding_ref],
                }
            ],
            frozen_a_refs=frozen_a_refs,
            allowed_a_operations=["implement", "resume", "route"],
            a_write_allowed=True,
            authority_pins=[
                (src["manifest_rel"], src["manifest_raw"]),
                (src["ledger_rel"], src["ledger_raw"]),
                (src["proof_rel"], src["proof_raw"]),
                (snap_rel, snap_raw),
            ],
            scope_map={"scope-b": ([plan_rel], [binding_rel])},
        )

        res_a = input_set.resolve_input_set(root, frozen_tid, operation="implement")
        self._assert_non_auth_and_diags(res_a)
        self.assertTrue(res_a["ok"], res_a["diagnostics"])
        self.assertEqual(res_a["route"], "A")
        self.assertIsNotNone(res_a["input_set_digest"])
        cats = {row["category"] for row in res_a["items"]}
        self.assertTrue({"policy", "frozen_a", "source", "task_definition", "codec", "environment"} <= cats)

        # Advancing live status on Frozen-A task keeps input_set_digest identical!
        master_live = inv_fixture.load(resolver.TRIPLET["master"])
        t_row = next(t for t in master_live["master"]["tasks"] if t["id"] == frozen_tid)
        t_row["status"] = "in-progress"
        t_row["subtasks"][0]["status"] = "done"
        inv_fixture.dump(resolver.TRIPLET["master"], master_live)
        res_a_prog = input_set.resolve_input_set(root, frozen_tid, operation="resume", baseline=res_a)
        self.assertTrue(res_a_prog["ok"], res_a_prog["diagnostics"])
        self.assertTrue(res_a_prog["freshness"]["fresh"])
        self.assertEqual(res_a_prog["input_set_digest"], res_a["input_set_digest"])

        # Reject --candidate-binding on route == "A" with CONFLICT!
        res_a_cand = input_set.resolve_input_set(
            root, frozen_tid, operation="implement", candidate_binding=binding_rel
        )
        self.assertFalse(res_a_cand["ok"])
        self.assertEqual(res_a_cand["diagnostics"][0]["reason_code"], codec.ReasonCode.CONFLICT.value)

        # Also reject --candidate-binding on explicit_not_enabled_a with CONFLICT!
        with tempfile.TemporaryDirectory(prefix="b_route_nea_cand_") as tmp_nea:
            root_nea = Path(tmp_nea)
            b_nea = ResolverRepoBuilder(root_nea)
            b_nea.write_adr_0040(valid=True)
            b_nea.write_triplet(
                master_tasks=[{"id": 1, "title": "Legacy", "status": "pending", "dependencies": []}],
                back_tasks=[{"id": "NG-0001", "taskmaster_id": 1, "title": "Legacy", "status": "pending", "depends_on": []}],
                gameplay_tasks=[],
            )
            dummy_rel = "logs/ci/2026-11-23/dummy-cand.json"
            (root_nea / dummy_rel).parent.mkdir(parents=True, exist_ok=True)
            (root_nea / dummy_rel).write_text("{}\n", encoding="utf-8")
            res_nea_cand = input_set.resolve_input_set(root_nea, 1, candidate_binding=dummy_rel)
            self.assertFalse(res_nea_cand["ok"])
            self.assertEqual(res_nea_cand["diagnostics"][0]["reason_code"], codec.ReasonCode.CONFLICT.value)

    # ------------------------------------------------------------------
    # 11. MVG manifest validation, per-binding Stage-5 Flow, duplicate refs
    # ------------------------------------------------------------------
    def test_11_mvg_manifest_validation_stage5_per_binding_and_duplicate_refs(self) -> None:
        # 1) Invalid MVG manifest (validate_manifest errors -> SCHEMA_VALIDATION_FAILED)
        _t1, root1, meta1 = self._clone_repo()
        bad_mvg = copy.deepcopy(meta1["mvg_doc"])
        bad_mvg["tests"][0]["path"] = "Game.Core.Tests/DoesNotExistTests.cs"
        bad_mvg_raw = _encoded(bad_mvg)
        (root1 / meta1["mvg_rel"]).write_bytes(bad_mvg_raw)
        b_rew1 = copy.deepcopy(meta1["bindings"]["plan-reward"][1])
        b_rew1["binding_revision"] = 2
        b_rew1["manifest_refs"] = [_owned_ref("manifest", meta1["mvg_rel"], [(meta1["mvg_rel"], bad_mvg_raw)])]
        bindings1 = copy.deepcopy(meta1["bindings"])
        bindings1["plan-reward"] = ("docs/planning/b-route/bindings/plan-reward/2.json", b_rew1)
        _recommit_template(
            root1, meta1, operation_id="op-bad-mvg", catalog_revision=2, plans=meta1["plans"], bindings=bindings1
        )
        r_bad_mvg = input_set.resolve_input_set(root1, 1)
        self.assertFalse(r_bad_mvg["ok"])
        self.assertEqual(r_bad_mvg["diagnostics"][0]["reason_code"], codec.ReasonCode.SCHEMA_VALIDATION_FAILED.value)

        # 2) Uncovered Stage-5 Flow (stage="5" with Flow obligation & empty manifest_refs -> UNRESOLVED_REFERENCE)
        _t2, root2, meta2 = self._clone_repo()
        b_rew2 = copy.deepcopy(meta2["bindings"]["plan-reward"][1])
        b_rew2["binding_revision"] = 2
        b_rew2["stage"] = "5"
        b_rew2["manifest_refs"] = []
        bindings2 = copy.deepcopy(meta2["bindings"])
        bindings2["plan-reward"] = ("docs/planning/b-route/bindings/plan-reward/2.json", b_rew2)
        _recommit_template(
            root2, meta2, operation_id="op-uncovered-s5", catalog_revision=2, plans=meta2["plans"], bindings=bindings2
        )
        r_uncov = input_set.resolve_input_set(root2, 1)
        self.assertFalse(r_uncov["ok"])
        self.assertEqual(r_uncov["diagnostics"][0]["reason_code"], codec.ReasonCode.UNRESOLVED_REFERENCE.value)

        # 3) Multi-plan Stage-5 non-Flow (plan-shared) + Stage-4 Flow (plan-reward without manifest yet) -> PASSES!
        _t3, root3, meta3 = self._clone_repo()
        b_shared3 = copy.deepcopy(meta3["bindings"]["plan-shared"][1])
        b_shared3["binding_revision"] = 2
        b_shared3["stage"] = "5"
        b_rew3 = copy.deepcopy(meta3["bindings"]["plan-reward"][1])
        b_rew3["binding_revision"] = 2
        b_rew3["stage"] = "4"
        b_rew3["manifest_refs"] = []
        bindings3 = copy.deepcopy(meta3["bindings"])
        bindings3["plan-shared"] = ("docs/planning/b-route/bindings/plan-shared/2.json", b_shared3)
        bindings3["plan-reward"] = ("docs/planning/b-route/bindings/plan-reward/2.json", b_rew3)
        _recommit_template(
            root3, meta3, operation_id="op-multi-s5-nonflow", catalog_revision=2, plans=meta3["plans"], bindings=bindings3
        )
        r_multi = input_set.resolve_input_set(root3, 1)
        self.assertTrue(r_multi["ok"], r_multi["diagnostics"])
        self.assertEqual(r_multi["route"], "B")

        # 4) Duplicate manifest_refs (in candidate obligation verification_refs + manifest_refs + committed binding)
        #    MUST preserve normalization_mode="mvg_manifest_normalized" and committed=False!
        _t4, root4, meta4 = self._clone_repo()
        mvg_raw4 = (root4 / meta4["mvg_rel"]).read_bytes()
        mvg_owned4 = _owned_ref("manifest", meta4["mvg_rel"], [(meta4["mvg_rel"], mvg_raw4)])
        # Also bind the same manifest in committed plan-shared so a committed ref follows the candidate ref!
        b_shared4 = copy.deepcopy(meta4["bindings"]["plan-shared"][1])
        b_shared4["binding_revision"] = 2
        b_shared4["manifest_refs"] = [mvg_owned4]
        bindings4 = copy.deepcopy(meta4["bindings"])
        bindings4["plan-shared"] = ("docs/planning/b-route/bindings/plan-shared/2.json", b_shared4)
        _recommit_template(
            root4, meta4, operation_id="op-dup-mvg-comm", catalog_revision=2, plans=meta4["plans"], bindings=bindings4
        )
        cand4 = copy.deepcopy(meta4["bindings"]["plan-reward"][1])
        cand4["binding_revision"] = 2
        cand4["obligations"][0]["verification_refs"] = [mvg_owned4]
        cand4["manifest_refs"] = [mvg_owned4]
        cand4_rel = "logs/ci/2026-11-23/cand-dup-mvg.json"
        (root4 / cand4_rel).parent.mkdir(parents=True, exist_ok=True)
        (root4 / cand4_rel).write_bytes(_encoded(cand4))
        r_dup = input_set.resolve_input_set(root4, 1, candidate_binding=cand4_rel)
        self.assertTrue(r_dup["ok"], r_dup["diagnostics"])
        mvg_items = [row for row in r_dup["items"] if row["category"] == "mvg_manifest"]
        self.assertEqual(len(mvg_items), 1)
        self.assertEqual(mvg_items[0]["normalization_mode"], "mvg_manifest_normalized")
        self.assertIs(mvg_items[0]["committed"], False)

    # ------------------------------------------------------------------
    # 12. Chained 3B -> 3C -> Stage-4 clean clone transitive receipt seals
    # ------------------------------------------------------------------
    def test_12_chained_3b_3c_stage4_clean_clone_transitive_receipt_seals(self) -> None:
        _tmp, root, meta = self._clone_repo()
        # Receipt 1 (3B): already created as op-base-001 sealing manifest/ledger/proof logs.
        r1_rel = "docs/planning/b-route/commits/op-base-001.json"
        r1_raw = (root / r1_rel).read_bytes()

        # Receipt 2 (3C): pins ONLY Receipt 1 (NOT the 3B log files directly!).
        b_shared_2 = copy.deepcopy(meta["bindings"]["plan-shared"][1])
        b_shared_2["binding_revision"] = 2
        bindings_3c = copy.deepcopy(meta["bindings"])
        bindings_3c["plan-shared"] = ("docs/planning/b-route/bindings/plan-shared/2.json", b_shared_2)
        _recommit_template(
            root,
            meta,
            operation_id="op-chain-3c",
            catalog_revision=2,
            plans=meta["plans"],
            bindings=bindings_3c,
            authority_pins=[(r1_rel, r1_raw)],
        )
        r2_rel = "docs/planning/b-route/commits/op-chain-3c.json"
        r2_raw = (root / r2_rel).read_bytes()

        # Receipt 3 (Stage-4): pins ONLY Receipt 2 (scope head now points to op-chain-s4!).
        b_rew_2 = copy.deepcopy(meta["bindings"]["plan-reward"][1])
        b_rew_2["binding_revision"] = 2
        bindings_s4 = copy.deepcopy(bindings_3c)
        bindings_s4["plan-reward"] = ("docs/planning/b-route/bindings/plan-reward/2.json", b_rew_2)
        _recommit_template(
            root,
            meta,
            operation_id="op-chain-s4",
            catalog_revision=3,
            plans=meta["plans"],
            bindings=bindings_s4,
            authority_pins=[(r2_rel, r2_raw)],
        )

        # Resolve WITH logs/ first, then delete logs/ completely and verify clean-clone parity!
        with_logs = input_set.resolve_input_set(root, 1)
        self.assertTrue(with_logs["ok"], with_logs["diagnostics"])
        self.assertTrue(any(row["category"] == "adoption_proof" for row in with_logs["items"]))

        shutil.rmtree(root / "logs")
        self.assertFalse((root / "logs").exists())
        clean_clone = input_set.resolve_input_set(root, 1)
        self.assertTrue(clean_clone["ok"], clean_clone["diagnostics"])
        self.assertEqual(clean_clone["input_set_digest"], with_logs["input_set_digest"])
        self.assertFalse((root / "logs").exists())
        self.assertTrue(
            {meta["src"]["manifest_rel"], meta["src"]["ledger_rel"], meta["src"]["proof_rel"]}
            <= set(clean_clone["clean_clone_sealed_logs"])
        )

    # ------------------------------------------------------------------
    # 13. Candidate binding closure recomputation + source_gap / missing logs
    # ------------------------------------------------------------------
    def test_13_candidate_binding_closure_recomputation_and_strict_rejections(self) -> None:
        _tmp, root, meta = self._clone_repo()

        # Add a flow-bonus definition owned by plan-unrelated (initially NOT in Task 1's resolved_definitions),
        # and add a source_gap requirement to plan-reward so we can test candidate rejection of source_gap.
        plans_ext = copy.deepcopy(meta["plans"])
        p_unrel = copy.deepcopy(plans_ext["plan-unrelated"][1])
        p_unrel["revision"] = 2
        p_unrel["requirements"].append(
            {
                "requirement_id": "REQ-BONUS-1",
                "source_block_ids": ["BLK-COMBAT-1"],
                "acceptance_intent": "Cross-plan bonus flow requirement.",
                "non_task_sinks": [],
            }
        )
        p_unrel["definitions"]["flows"].append(_make_flow("flow-bonus", ["REQ-BONUS-1"]))
        p_unrel["requirement_verification"].append(
            {
                "requirement_id": "REQ-BONUS-1",
                "disposition": "flow",
                "flow_id": "flow-bonus",
                "rationale": "Cross-plan bonus flow.",
                "sink_id": None,
                "verification_ref": None,
                "authority_ref": None,
                "evidence_ids": [],
            }
        )
        p_unrel["applicability"].append(
            {
                "requirement_id": "REQ-BONUS-1",
                "disposition": "flow",
                "rationale": "Cross-plan bonus flow.",
                "other_verification_refs": [],
            }
        )
        p_unrel["coverage_table"].append(
            {k: v for k, v in p_unrel["requirement_verification"][-1].items() if k != "evidence_ids"}
        )
        p_unrel["requirement_route_memberships"].append(
            {"requirement_id": "REQ-BONUS-1", "flow_id": "flow-bonus", "observable_role": "primary"}
        )
        p_unrel_rel = "docs/planning/b-route/plans/plan-unrelated/2.json"
        plans_ext["plan-unrelated"] = (p_unrel_rel, p_unrel)
        p_unrel_ref = _typed_ref(p_unrel_rel, "newrouge.b-route-plan.v1", "plan-unrelated", 2, _encoded(p_unrel))

        p_rew = copy.deepcopy(plans_ext["plan-reward"][1])
        p_rew["revision"] = 2
        p_rew["requirements"].append(
            {
                "requirement_id": "REQ-GAP-1",
                "source_block_ids": ["BLK-REWARD-1"],
                "acceptance_intent": "Unresolved source gap.",
                "non_task_sinks": [],
            }
        )
        p_rew["requirement_verification"].append(
            {
                "requirement_id": "REQ-GAP-1",
                "disposition": "source_gap",
                "flow_id": None,
                "rationale": "Missing upstream source specification.",
                "sink_id": None,
                "verification_ref": None,
                "authority_ref": None,
                "evidence_ids": [],
            }
        )
        p_rew["applicability"].append(
            {
                "requirement_id": "REQ-GAP-1",
                "disposition": "source_gap",
                "rationale": "Missing upstream source specification.",
                "other_verification_refs": [],
            }
        )
        p_rew["coverage_table"].append(
            {k: v for k, v in p_rew["requirement_verification"][-1].items() if k != "evidence_ids"}
        )
        p_rew_rel = "docs/planning/b-route/plans/plan-reward/2.json"
        plans_ext["plan-reward"] = (p_rew_rel, p_rew)
        p_rew_ref = _typed_ref(p_rew_rel, "newrouge.b-route-plan.v1", "plan-reward", 2, _encoded(p_rew))

        # Update MVG manifest to also cover flow-bonus so candidate binding passes manifest coverage.
        mvg_ext = copy.deepcopy(meta["mvg_doc"])
        mvg_ext["coverage"]["required_flow_ids"] = ["flow-reward", "flow-bonus"]
        mvg_ext["flows"].append(
            {
                "id": "flow-bonus",
                "task_ids": [1, 2],
                "outcome": "Bonus flow passes.",
                "source_paths": [meta["src"]["gdd_rel"]],
                "test_ids": ["test-reward-domain"],
                "handoffs": [
                    {
                        "producer_task": 2,
                        "consumer_task": 1,
                        "owner_task": 1,
                        "contract_ref": meta["ev_rel"],
                        "behavior": "Task 2 produces bonus payload; Task 1 applies bonus.",
                        "test_ids": ["test-reward-domain"],
                    }
                ],
            }
        )
        mvg_ext_raw = _encoded(mvg_ext)
        (root / meta["mvg_rel"]).write_bytes(mvg_ext_raw)
        mvg_ext_owned = _owned_ref("manifest", meta["mvg_rel"], [(meta["mvg_rel"], mvg_ext_raw)])

        bindings_ext = copy.deepcopy(meta["bindings"])
        b_unrel = copy.deepcopy(bindings_ext["plan-unrelated"][1])
        b_unrel["binding_revision"] = 2
        b_unrel["plan_ref"] = p_unrel_ref
        bindings_ext["plan-unrelated"] = ("docs/planning/b-route/bindings/plan-unrelated/2.json", b_unrel)

        b_rew = copy.deepcopy(bindings_ext["plan-reward"][1])
        b_rew["binding_revision"] = 2
        b_rew["plan_ref"] = p_rew_ref
        b_rew["manifest_refs"] = [mvg_ext_owned]
        bindings_ext["plan-reward"] = ("docs/planning/b-route/bindings/plan-reward/2.json", b_rew)

        _recommit_template(
            root, meta, operation_id="op-ext-closure", catalog_revision=2, plans=plans_ext, bindings=bindings_ext
        )
        base = input_set.resolve_input_set(root, 1)
        self.assertTrue(base["ok"], base["diagnostics"])
        base_by_loc = {(r["category"], r["locator"]): r for r in base["items"]}
        self.assertNotIn(("plan", "plan:plan-unrelated"), base_by_loc)

        # Candidate binding adds flow-bonus to Task 1 AND updates Task 2's implementation object!
        cand = copy.deepcopy(b_rew)
        cand["binding_revision"] = 3
        cand["task_mappings"][0]["flow_ids"] = ["flow-reward", "flow-bonus"]
        cand["implementation_objects"][1]["expected_type"] = "Game.Core.Contracts.RewardPayloadDtoV2"
        cand_rel = "logs/ci/2026-11-23/cand-closure-recompute.json"
        (root / cand_rel).parent.mkdir(parents=True, exist_ok=True)
        (root / cand_rel).write_bytes(_encoded(cand))

        res_cand = input_set.resolve_input_set(root, 1, candidate_binding=cand_rel)
        self.assertTrue(res_cand["ok"], res_cand["diagnostics"])
        cand_by_loc = {(r["category"], r["locator"]): r for r in res_cand["items"]}
        # 1) task_origins slice updated + committed=False
        self.assertIs(cand_by_loc[("task_origins", "task_origins:task:1")]["committed"], False)
        self.assertNotEqual(
            cand_by_loc[("task_origins", "task_origins:task:1")]["normalized_digest"],
            base_by_loc[("task_origins", "task_origins:task:1")]["normalized_digest"],
        )
        # 2) resolved_definitions recomputed + newly referenced plan-unrelated loaded!
        self.assertIn(("plan", "plan:plan-unrelated"), cand_by_loc)
        self.assertNotEqual(
            cand_by_loc[("resolved_definitions", "resolved_definitions:task:1")]["normalized_digest"],
            base_by_loc[("resolved_definitions", "resolved_definitions:task:1")]["normalized_digest"],
        )
        # 3) dependency_producer for Task 2 substituted cand_doc!
        self.assertIs(cand_by_loc[("dependency_producer", "dependency_producer:task:2")]["committed"], False)
        self.assertNotEqual(
            cand_by_loc[("dependency_producer", "dependency_producer:task:2")]["normalized_digest"],
            base_by_loc[("dependency_producer", "dependency_producer:task:2")]["normalized_digest"],
        )

        # Reject candidate mapping a source_gap requirement!
        cand_gap = copy.deepcopy(b_rew)
        cand_gap["binding_revision"] = 3
        cand_gap["task_mappings"][0]["requirement_ids"] = ["REQ-REWARD-1", "REQ-GAP-1"]
        cand_gap_rel = "logs/ci/2026-11-23/cand-source-gap.json"
        (root / cand_gap_rel).write_bytes(_encoded(cand_gap))
        r_gap = input_set.resolve_input_set(root, 1, candidate_binding=cand_gap_rel)
        self.assertFalse(r_gap["ok"])
        self.assertEqual(r_gap["diagnostics"][0]["reason_code"], codec.ReasonCode.SEMANTIC_ERROR.value)

        # Reject candidate with empty requirement_ids & flow_ids without integration_only_owner role!
        cand_empty = copy.deepcopy(b_rew)
        cand_empty["binding_revision"] = 3
        cand_empty["task_mappings"][0]["requirement_ids"] = []
        cand_empty["task_mappings"][0]["flow_ids"] = []
        cand_empty["task_mappings"][0]["roles"] = ["consumer"]
        cand_empty_rel = "logs/ci/2026-11-23/cand-empty-map.json"
        (root / cand_empty_rel).write_bytes(_encoded(cand_empty))
        r_empty = input_set.resolve_input_set(root, 1, candidate_binding=cand_empty_rel)
        self.assertFalse(r_empty["ok"])
        self.assertEqual(r_empty["diagnostics"][0]["reason_code"], codec.ReasonCode.SEMANTIC_ERROR.value)

        # Reject candidate referencing an absent clean-clone logs/ file (even when sealed in receipt!)
        cand_log = copy.deepcopy(b_rew)
        cand_log["binding_revision"] = 3
        cand_log["other_verification_refs"] = [meta["src"]["proof_ref"]]
        cand_log_rel = "docs/planning/tmp-cand-sealed-log.json"
        (root / cand_log_rel).write_bytes(_encoded(cand_log))
        shutil.rmtree(root / "logs")
        r_missing_log = input_set.resolve_input_set(root, 1, candidate_binding=cand_log_rel)
        self.assertFalse(r_missing_log["ok"])
        self.assertEqual(r_missing_log["diagnostics"][0]["reason_code"], codec.ReasonCode.FILE_NOT_FOUND.value)

    # ------------------------------------------------------------------
    # 14. Scope-lock stale baseline parity, transitive pending, uppercase plan,
    #     3C-in-Stage-4 & Stage-5 obligations attribution, baseline types, contractRefs
    # ------------------------------------------------------------------
    def test_14_scope_stale_parity_transitive_pending_uppercase_plan_3c_5_attribution_and_types(self) -> None:
        # 1) --lock-mode scope + stale --baseline MUST match --lock-mode none full payload!
        _t1, root1, meta1 = self._clone_repo()
        base_rep = "logs/ci/2026-11-23/base-parity.json"
        buf_b = io.StringIO()
        with contextlib.redirect_stdout(buf_b):
            self.assertEqual(
                dev_cli.main(["b-route-input-set", "--root", str(root1), "--task-id", "1", "--report", base_rep]), 0
            )
        (root1 / meta1["dto_rel"]).write_text(
            "namespace Game.Core.Contracts;\n\npublic sealed record RewardPayloadDto(string RewardId, int Amount, int Rev);\n",
            encoding="utf-8",
        )
        buf_none = io.StringIO()
        with contextlib.redirect_stdout(buf_none):
            rc_none = dev_cli.main(
                ["b-route-input-set", "--root", str(root1), "--task-id", "1", "--baseline", base_rep, "--lock-mode", "none"]
            )
        buf_scope = io.StringIO()
        with contextlib.redirect_stdout(buf_scope):
            rc_scope = dev_cli.main(
                ["b-route-input-set", "--root", str(root1), "--task-id", "1", "--baseline", base_rep, "--lock-mode", "scope"]
            )
        self.assertEqual(rc_none, 1)
        self.assertEqual(rc_scope, 1)
        out_none = json.loads(buf_none.getvalue())
        out_scope = json.loads(buf_scope.getvalue())
        self.assertEqual(out_scope["lock_mode"], "scope")
        self.assertTrue(out_scope["valid_input_set"])
        self.assertEqual(out_scope["input_set_digest"], out_none["input_set_digest"])
        self.assertEqual(out_scope["freshness"], out_none["freshness"])
        self.assertEqual(out_scope["return_stage"], out_none["return_stage"])
        self.assertEqual(out_scope["items"], out_none["items"])

        # Lease acquisition OSError/ValueError wraps into structured CodecError!
        with patch.object(op_scope, "business_guard", side_effect=OSError("simulated lock error")):
            with self.assertRaises(codec.CodecError) as lease_ctx:
                with input_set.guarded_input_set(root1, 1):
                    pass
            self.assertEqual(lease_ctx.exception.diagnostic.reason_code, codec.ReasonCode.CONFLICT)

        # 2) Pending op on transitive dependency Task 2 blocks Task 1 with PENDING!
        _t2, root2, _m2 = self._clone_repo()
        _create_unapplied_operation(root2, operation_id="op-dep-task2", scope_ids=["task:2"])
        res_dep_pend = input_set.resolve_input_set(root2, 1)
        self.assertFalse(res_dep_pend["ok"])
        self.assertEqual(res_dep_pend["diagnostics"][0]["reason_code"], codec.ReasonCode.PENDING.value)

        # 3) Uppercase plan_id used as scope_id normalizes via op_scope.resource_scopes for guarded_input_set!
        _t3, root3, _m3 = self._clone_repo()
        b3 = ResolverRepoBuilder(root3)
        src3 = b3.write_sources_and_proof(use_log_proof=True)
        p_up_rel = "docs/planning/b-route/plans/PLAN-UPPER-1/1.json"
        p_up_doc = _build_plan_doc(
            plan_id="PLAN-UPPER-1",
            revision=1,
            source_manifest_ref=src3["manifest_ref"],
            source_ledger_ref=src3["ledger_ref"],
            source_revision=src3["source_revision"],
            source_manifest_digest=src3["source_manifest_digest"],
            proof_ref=src3["proof_ref"],
            requirements=[
                {
                    "requirement_id": "REQ-UP-1",
                    "source_block_ids": ["BLK-AUDIT-1"],
                    "acceptance_intent": "Uppercase plan scope normalization.",
                    "non_task_sinks": ["sink-up"],
                }
            ],
            flows=[],
            commands=[],
            states=[],
            logical_references=[],
            requirement_verification=[
                {
                    "requirement_id": "REQ-UP-1",
                    "disposition": "other_verification",
                    "flow_id": None,
                    "rationale": "Static rule.",
                    "sink_id": "sink-up",
                    "verification_ref": src3["other_v_rel"],
                    "authority_ref": None,
                    "evidence_ids": [],
                }
            ],
            requirement_route_memberships=[],
            requirement_evidence=[],
            evidence_source_refs=[src3["other_v_owned"]],
        )
        p_up_ref = _typed_ref(p_up_rel, "newrouge.b-route-plan.v1", "PLAN-UPPER-1", 1, _encoded(p_up_doc))
        b_up_rel = "docs/planning/b-route/bindings/PLAN-UPPER-1/1.json"
        b_up_doc = _build_binding_doc(
            plan_id="PLAN-UPPER-1",
            binding_revision=1,
            plan_ref=p_up_ref,
            stage="4",
            task_mappings=[
                {
                    "task_id": 3,
                    "view_refs": [{"view": "back", "business_id": "NG-0003"}],
                    "requirement_ids": ["REQ-UP-1"],
                    "flow_ids": [],
                    "part_kinds": ["domain_rules"],
                    "roles": ["integration_only_owner"],
                    "obligation_ids": ["obl-up-1"],
                }
            ],
            obligations=[
                {
                    "id": "obl-up-1",
                    "requirement_ids": ["REQ-UP-1"],
                    "flow_ids": [],
                    "test_ids": [],
                    "responsibility": "Verify uppercase plan.",
                    "verification_refs": [src3["other_v_owned"]],
                }
            ],
            other_verification_refs=[src3["other_v_owned"]],
        )
        b_up_ref = _typed_ref(b_up_rel, "newrouge.b-route-binding.v1", "PLAN-UPPER-1", 1, _encoded(b_up_doc))
        shutil.rmtree(root3 / "docs/planning/b-route")
        b3.commit_bundle(
            operation_id="op-upper-plan",
            plans=[(p_up_rel, p_up_doc)],
            bindings=[(b_up_rel, b_up_doc)],
            origins_tasks=[
                {
                    "task_id": 3,
                    "source_refs": [src3["source_owned"]],
                    "plan_refs": [p_up_ref],
                    "binding_refs": [b_up_ref],
                }
            ],
            authority_pins=[
                (src3["manifest_rel"], src3["manifest_raw"]),
                (src3["ledger_rel"], src3["ledger_raw"]),
                (src3["proof_rel"], src3["proof_raw"]),
            ],
            scope_map={"PLAN-UPPER-1": ([p_up_rel], [b_up_rel])},
            catalog_revision=1,
        )
        with input_set.guarded_input_set(root3, 3, operation_id="op-caller-id") as handle_up:
            self.assertTrue(all(s == s.lower() for s in handle_up.scope_ids))
            self.assertNotIn("PLAN-UPPER-1", handle_up.scope_ids)
            reval_up = handle_up.revalidate()
            self.assertTrue(reval_up["ok"])

        # 4) 3C mapping change inside Stage-4 binding returns "3C"; Stage-5 obligations change returns "5"!
        _t4, root4, meta4 = self._clone_repo()
        base4 = input_set.resolve_input_set(root4, 1)
        b_rew_3c = copy.deepcopy(meta4["bindings"]["plan-reward"][1])
        b_rew_3c["binding_revision"] = 2
        b_rew_3c["task_mappings"][0]["part_kinds"] = ["domain_rules", "binding", "csharp_adapter"]
        bindings_3c_in_4 = copy.deepcopy(meta4["bindings"])
        bindings_3c_in_4["plan-reward"] = ("docs/planning/b-route/bindings/plan-reward/2.json", b_rew_3c)
        _recommit_template(
            root4, meta4, operation_id="op-3c-in-s4", catalog_revision=2, plans=meta4["plans"], bindings=bindings_3c_in_4
        )
        res_3c_in_4 = input_set.resolve_input_set(root4, 1, baseline=base4)
        self.assertFalse(res_3c_in_4["ok"])
        self.assertTrue(res_3c_in_4["valid_input_set"])
        self.assertEqual(res_3c_in_4["return_stage"], "3C")

        # Promote to Stage-5 and modify ONLY obligations -> MUST return "5" (not masked as "4")!
        _t5, root5, meta5 = self._clone_repo()
        base5 = input_set.resolve_input_set(root5, 1)
        b_rew_s5 = copy.deepcopy(meta5["bindings"]["plan-reward"][1])
        b_rew_s5["binding_revision"] = 2
        b_rew_s5["stage"] = "5"
        b_rew_s5["obligations"][0]["responsibility"] = "Updated Stage-5 obligation responsibility."
        bindings_s5_obl = copy.deepcopy(meta5["bindings"])
        bindings_s5_obl["plan-reward"] = ("docs/planning/b-route/bindings/plan-reward/2.json", b_rew_s5)
        _recommit_template(
            root5, meta5, operation_id="op-s5-obl", catalog_revision=2, plans=meta5["plans"], bindings=bindings_s5_obl
        )
        res_s5_obl = input_set.resolve_input_set(root5, 1, baseline=base5)
        self.assertFalse(res_s5_obl["ok"])
        self.assertTrue(res_s5_obl["valid_input_set"])
        self.assertEqual(res_s5_obl["return_stage"], "5")

        # 5) Malformed baseline item types raise structured CodecError(SCHEMA_VALIDATION_FAILED)!
        for field_name, bad_val in (
            ("category", ["unhashable"]),
            ("locator", 12345),
            ("normalization_mode", ""),
            ("codec_version", None),
            ("normalized_digest", 999),
            ("return_stage", ["4"]),
            ("committed", "true"),
        ):
            bad_base = copy.deepcopy(base5)
            bad_base["items"][0][field_name] = bad_val
            with self.assertRaises(codec.CodecError) as bad_ctx:
                input_set.compare_input_sets(bad_base, base5)
            self.assertEqual(
                bad_ctx.exception.diagnostic.reason_code,
                codec.ReasonCode.SCHEMA_VALIDATION_FAILED,
                f"field {field_name} must raise SCHEMA_VALIDATION_FAILED",
            )

        # 6) Malformed/empty/unresolvable contractRefs fail closed (INVALID_REFERENCE, return_stage="4")!
        _t6, root6, _m6 = self._clone_repo()
        back6 = json.loads((root6 / resolver.TRIPLET["back"]).read_text(encoding="utf-8"))
        back6[1]["contractRefs"] = [""]  # on transitive dep Task 2!
        (root6 / resolver.TRIPLET["back"]).write_bytes(_encoded(back6))
        r_bad_cref = input_set.resolve_input_set(root6, 1)
        self.assertFalse(r_bad_cref["ok"])
        self.assertEqual(r_bad_cref["diagnostics"][0]["reason_code"], codec.ReasonCode.INVALID_REFERENCE.value)
        self.assertEqual(r_bad_cref["return_stage"], "4")


if __name__ == "__main__":
    unittest.main()
