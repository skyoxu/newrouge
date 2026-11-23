"""Deterministic tests for Story 3.4 Chapter 4 production contracts and four-part binding refinement.

Covers every row of the Story 3.4 I/O & Edge-Case Matrix (REUSE, PUB_SYNC,
PLANNED, MISMATCH, UI_SLICE), multi-plan shared-Task conservation, crash/recover
on public-sync-journal.json + public-sync.pending.json and commit.json, Story 3.3
resolve_task_origin conservative blocking on public-sync.pending.json, Story 2.8
compensation compatibility (_b_route_compensation.build), clean-clone logs/-free
extract_stage4_semantics(plan, binding), CLI/dev_cli/builder integration, schema
isolation, policy anchoring, and zero __pycache__/.pyc generation.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import base64
import contextlib
import copy
import hashlib
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

import _b_route_adoption as adoption
import _b_route_adoption_review as adoption_review
import _b_route_chapter4_binding as ch4
import _b_route_codec as codec
import _b_route_commit as commit
import _b_route_commit_projection as commit_projection
import _b_route_compensation as compensation
import _b_route_operation_scope as op_scope
import _b_route_records as records
import _b_route_schema_resources as schema_resources
import _b_route_task_resolver as task_resolver
import _planning_apply_journal as journal
import dev_cli
import dev_cli_builders
import refine_b_route_chapter4_binding as ch4_cli


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


def _four_parts(
    *,
    domain: bool = True,
    adapter: bool = True,
    binding: bool = True,
    scene: bool = True,
    scene_no_ui_rationale: str = "Headless core-only flow with no Godot scene or UI obligation.",
) -> list[dict]:
    specs = [
        ("domain_rules", domain, "Core deterministic domain rules."),
        ("csharp_adapter", adapter, "Thin C# scene adapter forwarding commands."),
        ("binding", binding, "Resource and event binding contracts."),
        ("scene", scene, "Godot scene wiring for reward display." if scene else scene_no_ui_rationale),
    ]
    return [
        {
            "kind": kind,
            "applicability": "applicable" if applicable else "not_applicable",
            "rationale": desc if applicable else desc,
            "responsibilities": [desc] if applicable else [],
        }
        for kind, applicable, desc in specs
    ]


class Chapter4RepoFixture:
    """Isolated schema-validated B-route repository with 3B plans, 3C bindings, and real C#/Godot assets."""

    _TEMPLATE_CACHE: dict[tuple, tuple[tempfile.TemporaryDirectory, dict[str, object]]] = {}

    @classmethod
    def clear_template_cache(cls) -> None:
        for tmp_dir, _assets in cls._TEMPLATE_CACHE.values():
            tmp_dir.cleanup()
        cls._TEMPLATE_CACHE.clear()

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.plan_id = "plan-reward"
        self.other_plan_id = "plan-combat"
        self.scope_id = "scope-reward"
        self.other_scope_id = "scope-combat"

    def cleanup(self) -> None:
        self._tmp.cleanup()

    def put(self, rel: str, data: bytes | str) -> bytes:
        raw = data.encode("utf-8") if isinstance(data, str) else data
        target = self.root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        return raw

    def put_json(self, rel: str, value: object) -> bytes:
        return self.put(rel, _encoded(value))

    def read_json(self, rel: str) -> object:
        return json.loads((self.root / rel).read_text(encoding="utf-8"))

    def snapshot_tree(self, prefixes: tuple[str, ...]) -> dict[str, bytes]:
        snap: dict[str, bytes] = {}
        for prefix in prefixes:
            base = self.root / prefix
            if not base.exists():
                continue
            for p in sorted(base.rglob("*")):
                if p.is_file():
                    snap[p.relative_to(self.root).as_posix()] = p.read_bytes()
        return snap

    def build_committed_bundle(
        self,
        *,
        ui_applicable: bool = True,
        include_other_plan: bool = True,
        include_3c_binding: bool = True,
        source_gap_req: bool = False,
        include_non_b_task: bool = False,
        integration_only_task101: bool = False,
        with_compensation_origin: bool = False,
    ) -> dict[str, object]:
        cache_key = (
            ui_applicable,
            include_other_plan,
            include_3c_binding,
            source_gap_req,
            include_non_b_task,
            integration_only_task101,
            with_compensation_origin,
        )
        if cache_key not in self._TEMPLATE_CACHE:
            tmpl_fx = Chapter4RepoFixture()
            assets = tmpl_fx._build_committed_bundle_uncached(
                ui_applicable=ui_applicable,
                include_other_plan=include_other_plan,
                include_3c_binding=include_3c_binding,
                source_gap_req=source_gap_req,
                include_non_b_task=include_non_b_task,
                integration_only_task101=integration_only_task101,
                with_compensation_origin=with_compensation_origin,
            )
            self._TEMPLATE_CACHE[cache_key] = (tmpl_fx._tmp, assets)
        tmpl_dir, cached_assets = self._TEMPLATE_CACHE[cache_key]
        shutil.copytree(Path(tmpl_dir.name), self.root, dirs_exist_ok=True)
        return copy.deepcopy(cached_assets)

    def _build_committed_bundle_uncached(
        self,
        *,
        ui_applicable: bool = True,
        include_other_plan: bool = True,
        include_3c_binding: bool = True,
        source_gap_req: bool = False,
        include_non_b_task: bool = False,
        integration_only_task101: bool = False,
        with_compensation_origin: bool = False,
    ) -> dict[str, object]:
        # 1. Source manifest & ledger.
        src_gdd = self.put("sources/reward-gdd.md", "# Reward Flow\n\nPlayer selects one reward and returns to map.\n")
        source_entries = [{"path": "sources/reward-gdd.md", "source_type": "markdown", "sha256": codec.raw_digest(src_gdd)}]
        manifest_digest = codec.canonical_digest(source_entries)
        source_revision = "source-set:" + manifest_digest[7:31]
        manifest_raw = self.put_json(
            "sources/source-manifest.json",
            {
                "schema_version": "chapter3.source-manifest.v1",
                "source_revision": source_revision,
                "manifest_sha256": manifest_digest,
                "sources": source_entries,
            },
        )
        ledger_raw = self.put_json(
            "sources/source-blocks.json",
            {
                "schema_version": "newrouge.source-blocks.v1",
                "source_revision": source_revision,
                "source_manifest_sha256": manifest_digest,
                "blocks": [
                    {"block_id": "BLK-REWARD-1", "source_path": "sources/reward-gdd.md"},
                    {"block_id": "BLK-COMBAT-1", "source_path": "sources/reward-gdd.md"},
                ],
            },
        )
        proof_raw = self.put_json("evidence/admission-proof.json", {"selected_candidate": "cand-1"})

        # 2. Existing C# contracts, adapter, Godot scene, resource, and Overlay 08.
        event_types_raw = self.put(
            "Game.Core/Contracts/EventTypes.cs",
            "namespace Game.Core.Contracts;\n\n"
            "/// <summary>\n"
            "/// Canonical domain event type constants.\n"
            "/// </summary>\n"
            "public static class EventTypes\n"
            "{\n"
            '    public const string RewardOffered = "core.reward.offered";\n'
            "}\n",
        )
        reward_cmd_raw = self.put(
            "Game.Core/Contracts/Reward/SelectRewardCommand.cs",
            "using System;\n\n"
            "namespace Game.Core.Contracts.Reward;\n\n"
            "/// <summary>\n"
            "/// Production command to select a locked reward option.\n"
            "/// </summary>\n"
            "public sealed record SelectRewardCommand(string RunId, int OptionIndex);\n",
        )
        reward_state_raw = self.put(
            "Game.Core/Contracts/Reward/RewardReadOnlyState.cs",
            "using System.Collections.Generic;\n\n"
            "namespace Game.Core.Contracts.Reward;\n\n"
            "/// <summary>\n"
            "/// Read-only reward state snapshot exposed by RewardStateOwner.\n"
            "/// </summary>\n"
            "public sealed record RewardReadOnlyState(string RunId, IReadOnlyList<string> Options, bool Locked);\n",
        )
        adapter_raw = self.put(
            "Game.Godot/Adapters/RewardSceneAdapter.cs",
            "namespace Game.Godot.Adapters;\n\n"
            "public sealed class RewardSceneAdapter\n"
            "{\n"
            "    public void OnSelectOption(int index) { }\n"
            "}\n",
        )
        scene_raw = self.put(
            "Game.Godot/Scenes/RewardScene.tscn",
            '[gd_scene load_steps=1 format=3]\n\n'
            '[node name="RewardScene" type="Control"]\n\n'
            '[node name="ConfirmButton" type="Button" parent="."]\n',
        )
        resource_raw = self.put(
            "Game.Godot/Resources/RewardTheme.tres",
            '[gd_resource type="Resource" script_class="RewardThemeResource" format=3]\n\n'
            "[resource]\n",
        )
        overlay_raw = self.put(
            "docs/architecture/overlays/PRD-REWARD/08/08-Feature-Slice-Reward.md",
            "---\n"
            "PRD-ID: PRD-REWARD\n"
            "Title: Reward Feature Slice\n"
            "Arch-Refs: [docs/architecture/base/08.md]\n"
            "ADRs: [ADR-0040]\n"
            "Test-Refs: [Game.Core.Tests/RewardTests.cs]\n"
            "---\n\n"
            "# Reward Feature Slice\n\n"
            "This slice preserves reward selection ordering.\n\n"
            "Task coverage:\n\n"
            "- NG-0101, NG-0102\n\n"
            "## Contracts\n\n"
            "- `Game.Core/Contracts/EventTypes.cs`\n"
            "- `Game.Core/Contracts/Reward/SelectRewardCommand.cs`\n"
            "- `Game.Core/Contracts/Reward/RewardReadOnlyState.cs`\n\n"
            "## Complex Invariants Table\n\n"
            "| Invariant | Owner |\n"
            "| --- | --- |\n"
            "| Locked option ordering | RewardStateOwner |\n\n"
            "```csharp\n"
            "// Preserve code block verbatim during overlay merge\n"
            "var locked = true;\n"
            "```\n",
        )

        # 3. Taskmaster triplet (Tasks 101, 102, and optional non-B Task 103).
        master_tasks = [
            {
                "id": 101,
                "title": "Reward Core Commands and State",
                "description": "Implement reward commands and read-only state owner.",
                "status": "pending",
                "priority": "high",
                "dependencies": [],
                "details": "Story: B-ROUTE-plan-reward",
                "testStrategy": "xUnit core tests",
            },
            {
                "id": 102,
                "title": "Reward Adapter and Scene Binding",
                "description": "Wire thin C# adapter and scene bindings.",
                "status": "pending",
                "priority": "medium",
                "dependencies": [101],
                "details": "Story: B-ROUTE-plan-reward",
                "testStrategy": "GdUnit4 scene wiring tests",
            },
        ]
        back_tasks = [
            {
                "id": "NG-0101",
                "taskmaster_id": 101,
                "title": "Reward Core Commands and State",
                "status": "pending",
                "layer": "core",
                "owner": "architecture",
                "labels": ["b-route", "3c-compiled"],
                "contractRefs": ["core.reward.offered"],
                "overlay_refs": ["docs/architecture/overlays/PRD-REWARD/08/08-Feature-Slice-Reward.md"],
                "requirement_ids": ["RQ-REWARD-1", "RQ-COMBAT-1"] if include_other_plan else ["RQ-REWARD-1"],
                "source_refs": ["docs/planning/b-route/plans/plan-reward/1.json"],
                "evidence_refs": ["docs/planning/b-route/bindings/plan-reward/1.json"],
                "acceptance": [
                    "Reward selection preserves option order. Refs: Game.Core/Contracts/Reward/SelectRewardCommand.cs"
                ],
                "semantic_review_tier": "targeted",
            },
            {
                "id": "NG-0102",
                "taskmaster_id": 102,
                "title": "Reward Adapter and Scene Binding",
                "status": "pending",
                "layer": "adapter",
                "owner": "architecture",
                "labels": ["b-route", "3c-compiled"],
                "contractRefs": ["core.reward.offered"],
                "overlay_refs": ["docs/architecture/overlays/PRD-REWARD/08/08-Feature-Slice-Reward.md"],
                "requirement_ids": ["RQ-REWARD-1"],
                "source_refs": ["docs/planning/b-route/plans/plan-reward/1.json"],
                "evidence_refs": ["docs/planning/b-route/bindings/plan-reward/1.json"],
                "acceptance": [
                    "Adapter forwards select command without direct state mutation. Refs: Game.Godot/Adapters/RewardSceneAdapter.cs"
                ],
                "semantic_review_tier": "targeted",
            },
        ]
        gameplay_tasks: list[dict] = []
        if include_non_b_task:
            master_tasks.append(
                {
                    "id": 103,
                    "title": "Legacy Frozen Task",
                    "description": "Unmapped non-B task.",
                    "status": "pending",
                    "priority": "low",
                    "dependencies": [],
                    "details": "Legacy A task",
                    "testStrategy": "Legacy tests",
                }
            )
            back_tasks.append(
                {
                    "id": "NG-0103",
                    "taskmaster_id": 103,
                    "title": "Legacy Frozen Task",
                    "status": "pending",
                    "layer": "core",
                    "owner": "architecture",
                    "labels": ["legacy"],
                    "acceptance": ["Legacy acceptance. Refs: sources/reward-gdd.md"],
                    "semantic_review_tier": "targeted",
                }
            )
        self.put_json(ch4.TRIPLET["master"], {"master": {"tasks": master_tasks}})
        self.put_json(ch4.TRIPLET["back"], back_tasks)
        self.put_json(ch4.TRIPLET["gameplay"], gameplay_tasks)

        # 4. Formal policy, plans, 3C bindings, origins, commit receipt, and catalog.
        policy_doc = {
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
        }
        policy_path = records.BASE + "policy.v1.json"
        policy_raw = self.put_json(policy_path, policy_doc)
        policy_ref = _typed_ref(policy_path, "newrouge.b-route-policy.v1", "policy-main", 1, policy_raw)

        source_identity = {
            "manifest_ref": _owned_ref("source_manifest", "sources/source-manifest.json", [("sources/source-manifest.json", manifest_raw)]),
            "ledger_ref": _owned_ref("source_ledger", "sources/source-blocks.json", [("sources/source-blocks.json", ledger_raw)]),
            "source_revision": source_revision,
            "source_manifest_digest": manifest_digest,
        }
        proof_ref = _owned_ref("planning_proof", "evidence/admission-proof.json", [("evidence/admission-proof.json", proof_raw)])

        reward_parts = _four_parts(scene=ui_applicable)
        reward_flow = {
            "id": "FLOW-REWARD",
            "requirement_ids": ["RQ-REWARD-1"],
            "entry": "EnterRewardScreen",
            "entry_condition": "Combat victory awards reward options.",
            "success_end": "ReturnToMap",
            "branches": [
                {"kind": "failure", "rationale": "Reject invalid option.", "description": "Keep reward screen open."},
                {"kind": "cancel", "rationale": "Allow skip reward.", "description": "Close without granting card."},
                {"kind": "return", "rationale": "Return to map node.", "description": "Navigate back to map."},
            ],
            "handoffs": [],
            "state_owners": [
                {
                    "kind": "state",
                    "definition_id": "STATE-REWARD",
                    "owner_plan_id": self.plan_id,
                    "owner_revision": 1,
                }
            ],
            "parts": reward_parts,
            "observable_result": "Selected reward granted and player returns to map.",
            "verification_targets": ["RewardFlowTests"],
            "loops": [],
        }
        if source_gap_req:
            reward_verif = [
                {
                    "requirement_id": "RQ-REWARD-1",
                    "disposition": "source_gap",
                    "flow_id": None,
                    "rationale": "Missing reward table detail in source.",
                    "sink_id": None,
                    "verification_ref": None,
                    "authority_ref": None,
                    "evidence_ids": [],
                }
            ]
            reward_route_memberships = []
        else:
            reward_verif = [
                {
                    "requirement_id": "RQ-REWARD-1",
                    "disposition": "flow",
                    "flow_id": "FLOW-REWARD",
                    "rationale": "Verified by reward flow.",
                    "sink_id": None,
                    "verification_ref": None,
                    "authority_ref": None,
                    "evidence_ids": [],
                }
            ]
            reward_route_memberships = [
                {
                    "requirement_id": "RQ-REWARD-1",
                    "flow_id": "FLOW-REWARD",
                    "observable_role": "Observe reward selection and map return.",
                }
            ]
        reward_plan = {
            "schema_version": "newrouge.b-route-plan.v1",
            "plan_id": self.plan_id,
            "revision": 1,
            "source_identity": source_identity,
            "requirements": [
                {
                    "requirement_id": "RQ-REWARD-1",
                    "source_block_ids": ["BLK-REWARD-1"],
                    "acceptance_intent": "Reward selection preserves locked order.",
                    "non_task_sinks": [],
                }
            ],
            "definitions": {
                "flows": [reward_flow],
                "commands": [
                    {
                        "id": "CMD-SELECT-REWARD",
                        "requirement_ids": ["RQ-REWARD-1"],
                        "responsibility": "Select one locked reward option through domain command.",
                        "uses": [
                            {
                                "kind": "state",
                                "definition_id": "STATE-REWARD",
                                "owner_plan_id": self.plan_id,
                                "owner_revision": 1,
                            }
                        ],
                    }
                ],
                "states": [
                    {
                        "id": "STATE-REWARD",
                        "requirement_ids": ["RQ-REWARD-1"],
                        "responsibility": "Single authoritative owner of reward options.",
                        "uses": [],
                    }
                ],
            },
            "logical_references": [],
            "requirement_verification": reward_verif,
            "requirement_route_memberships": reward_route_memberships,
            "requirement_evidence": [],
            "evidence_source_refs": [],
            "coverage_table": [{k: v for k, v in row.items() if k != "evidence_ids"} for row in reward_verif],
            "applicability": [
                {
                    "requirement_id": row["requirement_id"],
                    "disposition": row["disposition"],
                    "rationale": row["rationale"],
                    "other_verification_refs": [],
                }
                for row in reward_verif
            ],
            "adoption_proof_refs": [proof_ref],
            "lineage": {
                "previous_plan_ref": None,
                "change_summary": "Initial 3B reward plan adoption.",
                "identity_alignment": [],
            },
        }
        reward_plan_path = records.BASE + f"plans/{self.plan_id}/1.json"
        reward_plan_raw = self.put_json(reward_plan_path, reward_plan)
        reward_plan_ref = _typed_ref(reward_plan_path, "newrouge.b-route-plan.v1", self.plan_id, 1, reward_plan_raw)

        plan_refs_all = [reward_plan_ref]
        binding_refs_all: list[dict] = []
        targets_for_receipt: list[dict] = [
            {
                "path": policy_path,
                "before_digest": None,
                "after_digest": codec.raw_digest(policy_raw),
                "verification_mode": "immutable_bytes",
                "codec_version": None,
                "projection_digest": codec.raw_digest(policy_raw),
            },
            {
                "path": reward_plan_path,
                "before_digest": None,
                "after_digest": codec.raw_digest(reward_plan_raw),
                "verification_mode": "immutable_bytes",
                "codec_version": None,
                "projection_digest": codec.raw_digest(reward_plan_raw),
            },
        ]
        def_owners: list[dict] = [
            {"kind": "command", "definition_id": "CMD-SELECT-REWARD", "plan_ref": reward_plan_ref},
            {"kind": "flow", "definition_id": "FLOW-REWARD", "plan_ref": reward_plan_ref},
            {"kind": "state", "definition_id": "STATE-REWARD", "plan_ref": reward_plan_ref},
        ]

        reward_binding_ref = None
        if include_3c_binding:
            reward_binding = {
                "schema_version": "newrouge.b-route-binding.v1",
                "plan_id": self.plan_id,
                "binding_revision": 1,
                "plan_ref": reward_plan_ref,
                "stage": "3C",
                "task_mappings": [
                    {
                        "task_id": 101,
                        "view_refs": [{"view": "back", "business_id": "NG-0101"}],
                        "requirement_ids": ["RQ-REWARD-1"],
                        "flow_ids": ["FLOW-REWARD"],
                        "part_kinds": ["domain_rules"],
                        "roles": ["integration_only_owner"] if integration_only_task101 else ["producer"],
                        "obligation_ids": ["OBL-REWARD-CORE"],
                    },
                    {
                        "task_id": 102,
                        "view_refs": [{"view": "back", "business_id": "NG-0102"}],
                        "requirement_ids": ["RQ-REWARD-1"],
                        "flow_ids": ["FLOW-REWARD"],
                        "part_kinds": ["csharp_adapter", "binding", "scene"] if ui_applicable else ["csharp_adapter", "binding"],
                        "roles": ["consumer"],
                        "obligation_ids": ["OBL-REWARD-WIRE"],
                    },
                ],
                "parts": reward_parts,
                "implementation_objects": [],
                "obligations": [
                    {
                        "id": "OBL-REWARD-CORE",
                        "requirement_ids": ["RQ-REWARD-1"],
                        "flow_ids": ["FLOW-REWARD"],
                        "test_ids": ["RewardDomainTests"],
                        "responsibility": "Verify deterministic reward selection rules.",
                        "verification_refs": [],
                    },
                    {
                        "id": "OBL-REWARD-WIRE",
                        "requirement_ids": ["RQ-REWARD-1"],
                        "flow_ids": ["FLOW-REWARD"],
                        "test_ids": ["RewardAdapterTests"],
                        "responsibility": "Verify thin adapter wiring.",
                        "verification_refs": [],
                    },
                ],
                "manifest_refs": [],
                "other_verification_refs": [],
            }
            reward_binding_path = records.BASE + f"bindings/{self.plan_id}/1.json"
            reward_binding_raw = self.put_json(reward_binding_path, reward_binding)
            reward_binding_ref = _typed_ref(
                reward_binding_path, "newrouge.b-route-binding.v1", self.plan_id, 1, reward_binding_raw
            )
            binding_refs_all.append(reward_binding_ref)
            targets_for_receipt.append(
                {
                    "path": reward_binding_path,
                    "before_digest": None,
                    "after_digest": codec.raw_digest(reward_binding_raw),
                    "verification_mode": "immutable_bytes",
                    "codec_version": None,
                    "projection_digest": codec.raw_digest(reward_binding_raw),
                }
            )

        other_plan_ref = None
        other_binding_ref = None
        if include_other_plan:
            combat_parts = _four_parts(adapter=False, binding=False, scene=False)
            combat_flow = {
                "id": "FLOW-COMBAT",
                "requirement_ids": ["RQ-COMBAT-1"],
                "entry": "EnterCombat",
                "entry_condition": "Encounter started.",
                "success_end": "CombatEnded",
                "branches": [
                    {"kind": "failure", "rationale": "Defeat.", "description": "End run."},
                    {"kind": "cancel", "rationale": "Flee.", "description": "Exit combat."},
                    {"kind": "return", "rationale": "Victory.", "description": "Enter reward."},
                ],
                "handoffs": [],
                "state_owners": [],
                "parts": combat_parts,
                "observable_result": "Combat completes cleanly.",
                "verification_targets": ["CombatTests"],
                "loops": [],
            }
            combat_verif = [
                {
                    "requirement_id": "RQ-COMBAT-1",
                    "disposition": "flow",
                    "flow_id": "FLOW-COMBAT",
                    "rationale": "Verified by combat flow.",
                    "sink_id": None,
                    "verification_ref": None,
                    "authority_ref": None,
                    "evidence_ids": [],
                }
            ]
            combat_plan = {
                "schema_version": "newrouge.b-route-plan.v1",
                "plan_id": self.other_plan_id,
                "revision": 1,
                "source_identity": source_identity,
                "requirements": [
                    {
                        "requirement_id": "RQ-COMBAT-1",
                        "source_block_ids": ["BLK-COMBAT-1"],
                        "acceptance_intent": "Combat victory hands off cleanly.",
                        "non_task_sinks": [],
                    }
                ],
                "definitions": {"flows": [combat_flow], "commands": [], "states": []},
                "logical_references": [],
                "requirement_verification": combat_verif,
                "requirement_route_memberships": [
                    {
                        "requirement_id": "RQ-COMBAT-1",
                        "flow_id": "FLOW-COMBAT",
                        "observable_role": "Observe combat handoff.",
                    }
                ],
                "requirement_evidence": [],
                "evidence_source_refs": [],
                "coverage_table": [{k: v for k, v in row.items() if k != "evidence_ids"} for row in combat_verif],
                "applicability": [
                    {
                        "requirement_id": "RQ-COMBAT-1",
                        "disposition": "flow",
                        "rationale": "Verified by combat flow.",
                        "other_verification_refs": [],
                    }
                ],
                "adoption_proof_refs": [proof_ref],
                "lineage": {
                    "previous_plan_ref": None,
                    "change_summary": "Initial combat plan.",
                    "identity_alignment": [],
                },
            }
            combat_plan_path = records.BASE + f"plans/{self.other_plan_id}/1.json"
            combat_plan_raw = self.put_json(combat_plan_path, combat_plan)
            other_plan_ref = _typed_ref(
                combat_plan_path, "newrouge.b-route-plan.v1", self.other_plan_id, 1, combat_plan_raw
            )
            plan_refs_all.append(other_plan_ref)
            def_owners.append({"kind": "flow", "definition_id": "FLOW-COMBAT", "plan_ref": other_plan_ref})
            targets_for_receipt.append(
                {
                    "path": combat_plan_path,
                    "before_digest": None,
                    "after_digest": codec.raw_digest(combat_plan_raw),
                    "verification_mode": "immutable_bytes",
                    "codec_version": None,
                    "projection_digest": codec.raw_digest(combat_plan_raw),
                }
            )
            combat_binding = {
                "schema_version": "newrouge.b-route-binding.v1",
                "plan_id": self.other_plan_id,
                "binding_revision": 1,
                "plan_ref": other_plan_ref,
                "stage": "3C",
                "task_mappings": [
                    {
                        "task_id": 101,
                        "view_refs": [{"view": "back", "business_id": "NG-0101"}],
                        "requirement_ids": ["RQ-COMBAT-1"],
                        "flow_ids": ["FLOW-COMBAT"],
                        "part_kinds": ["domain_rules"],
                        "roles": ["producer"],
                        "obligation_ids": ["OBL-COMBAT-1"],
                    }
                ],
                "parts": combat_parts,
                "implementation_objects": [],
                "obligations": [
                    {
                        "id": "OBL-COMBAT-1",
                        "requirement_ids": ["RQ-COMBAT-1"],
                        "flow_ids": ["FLOW-COMBAT"],
                        "test_ids": ["CombatTests"],
                        "responsibility": "Verify combat handoff.",
                        "verification_refs": [],
                    }
                ],
                "manifest_refs": [],
                "other_verification_refs": [],
            }
            combat_binding_path = records.BASE + f"bindings/{self.other_plan_id}/1.json"
            combat_binding_raw = self.put_json(combat_binding_path, combat_binding)
            other_binding_ref = _typed_ref(
                combat_binding_path, "newrouge.b-route-binding.v1", self.other_plan_id, 1, combat_binding_raw
            )
            binding_refs_all.append(other_binding_ref)
            targets_for_receipt.append(
                {
                    "path": combat_binding_path,
                    "before_digest": None,
                    "after_digest": codec.raw_digest(combat_binding_raw),
                    "verification_mode": "immutable_bytes",
                    "codec_version": None,
                    "projection_digest": codec.raw_digest(combat_binding_raw),
                }
            )

        # Build origins.
        origins_tasks: list[dict] = []
        task_index: list[dict] = []
        t101_plans = ([reward_plan_ref] if reward_binding_ref else []) + ([other_plan_ref] if other_binding_ref else [])
        t101_bindings = ([reward_binding_ref] if reward_binding_ref else []) + ([other_binding_ref] if other_binding_ref else [])
        if t101_plans:
            origins_tasks.append(
                {
                    "task_id": 101,
                    "source_refs": [source_identity["manifest_ref"]],
                    "plan_refs": t101_plans,
                    "binding_refs": t101_bindings,
                }
            )
            task_index.append({"task_id": 101, "plan_refs": t101_plans, "binding_refs": t101_bindings})
        if reward_binding_ref is not None:
            origins_tasks.append(
                {
                    "task_id": 102,
                    "source_refs": [source_identity["manifest_ref"]],
                    "plan_refs": [reward_plan_ref],
                    "binding_refs": [reward_binding_ref],
                }
            )
            task_index.append({"task_id": 102, "plan_refs": [reward_plan_ref], "binding_refs": [reward_binding_ref]})

        origins_doc = {
            "schema_version": "newrouge.b-route-origins.v1",
            "origins_id": "task-origins",
            "revision": 1,
            "tasks": origins_tasks,
            "frozen_legacy_refs": [],
        }
        origins_path = records.BASE + "task-origins.v1.json"
        origins_raw = self.put_json(origins_path, origins_doc)
        origins_ref = _typed_ref(origins_path, "newrouge.b-route-origins.v1", "task-origins", 1, origins_raw)
        targets_for_receipt.append(
            {
                "path": origins_path,
                "before_digest": None,
                "after_digest": codec.raw_digest(origins_raw),
                "verification_mode": "immutable_bytes",
                "codec_version": None,
                "projection_digest": codec.raw_digest(origins_raw),
            }
        )

        # Build bootstrap receipt & catalog.
        scopes = [self.scope_id] + ([self.other_scope_id] if include_other_plan else [])
        scopes = sorted(set(scopes))
        resolved_defs = [
            {"kind": "state", "definition_id": "STATE-REWARD", "plan_ref": reward_plan_ref}
        ]
        bootstrap_op_id = "OP-BOOTSTRAP-3C"
        receipt_doc = {
            "schema_version": "newrouge.b-route-commit.v1",
            "operation_id": bootstrap_op_id,
            "revision": 1,
            "operation_digest": codec.canonical_digest({"bootstrap": bootstrap_op_id, "scopes": scopes}),
            "scopes": scopes,
            "authority": [],
            "targets": targets_for_receipt,
            "plan_refs": plan_refs_all,
            "binding_refs": binding_refs_all,
            "resolved_definitions": resolved_defs,
            "result": {
                "target_paths": [t["path"] for t in targets_for_receipt],
                "scope_ids": scopes,
            },
        }
        receipt_path = records.BASE + f"commits/{bootstrap_op_id}.json"
        receipt_raw = self.put_json(receipt_path, receipt_doc)
        receipt_ref = _typed_ref(receipt_path, "newrouge.b-route-commit.v1", bootstrap_op_id, 1, receipt_raw)

        scope_heads = [
            {
                "scope_id": self.scope_id,
                "plan_refs": [reward_plan_ref],
                "binding_refs": [reward_binding_ref] if reward_binding_ref else [],
                "receipt_ref": receipt_ref,
            }
        ]
        if include_other_plan and other_plan_ref and other_binding_ref:
            scope_heads.append(
                {
                    "scope_id": self.other_scope_id,
                    "plan_refs": [other_plan_ref],
                    "binding_refs": [other_binding_ref],
                    "receipt_ref": receipt_ref,
                }
            )
        scope_heads.sort(key=lambda h: h["scope_id"])
        def_owners.sort(key=lambda r: (r["kind"], r["definition_id"]))
        catalog_doc = {
            "schema_version": "newrouge.b-route-catalog.v1",
            "catalog_id": "catalog",
            "revision": 1,
            "policy_ref": policy_ref,
            "origins_ref": origins_ref,
            "scope_heads": scope_heads,
            "definition_owners": def_owners,
            "task_index": task_index,
        }
        catalog_raw = self.put_json(records.CATALOG_PATH, catalog_doc)

        # Verify bootstrap bundle passes strict records.validate_bundle!
        join = adoption._task_context(adoption.Snapshot(self.root))
        valid = records.validate_bundle({}, root=self.root, task_join=join)
        assert valid.ok, f"Bootstrap bundle invalid: {valid.diagnostic}"

        return {
            "event_types_raw": event_types_raw,
            "reward_cmd_raw": reward_cmd_raw,
            "reward_state_raw": reward_state_raw,
            "adapter_raw": adapter_raw,
            "scene_raw": scene_raw,
            "resource_raw": resource_raw,
            "overlay_raw": overlay_raw,
            "reward_plan_ref": reward_plan_ref,
            "reward_binding_ref": reward_binding_ref,
            "other_plan_ref": other_plan_ref,
            "other_binding_ref": other_binding_ref,
            "catalog_raw": catalog_raw,
        }

    def base_reuse_request(self, op_id: str, assets: dict[str, object], *, ui_applicable: bool = True) -> dict:
        req: dict = {
            "schema_version": ch4.REQUEST_SCHEMA,
            "producer": ch4.PRODUCER,
            "operation_id": op_id,
            "plan_id": self.plan_id,
            "scope_id": self.scope_id,
            "reason": "Refine reward 3C binding into Stage-4 production contracts and four-part definitions.",
            "commands": [
                {
                    "id": "CMD-SELECT-REWARD",
                    "owner": "RewardStateOwner",
                    "preconditions": ["Reward session is active and unlocked."],
                    "postconditions": ["Selected option is locked and reward granted once."],
                    "invariants": ["Option ordering stays immutable after generation."],
                    "responsible_task_ids": [101],
                    "availability": "existing",
                    "expected_type": "Game.Core.Contracts.Reward.SelectRewardCommand",
                    "target_ref": _owned_ref(
                        "contract",
                        "Game.Core/Contracts/Reward/SelectRewardCommand.cs",
                        [("Game.Core/Contracts/Reward/SelectRewardCommand.cs", assets["reward_cmd_raw"])],
                    ),
                    "later_checks": ["type", "compile"],
                    "contract_ref": "Game.Core/Contracts/Reward/SelectRewardCommand.cs",
                    "handoff": "RewardSceneAdapter -> SelectRewardCommand -> RewardStateOwner",
                }
            ],
            "read_only_states": [
                {
                    "id": "STATE-REWARD",
                    "single_owner": "RewardStateOwner",
                    "read_only_views": ["RewardReadOnlyState"],
                    "forbidden_direct_writers": ["adapter", "ui"],
                    "responsible_task_ids": [101],
                    "availability": "existing",
                    "expected_type": "Game.Core.Contracts.Reward.RewardReadOnlyState",
                    "target_ref": _owned_ref(
                        "contract",
                        "Game.Core/Contracts/Reward/RewardReadOnlyState.cs",
                        [("Game.Core/Contracts/Reward/RewardReadOnlyState.cs", assets["reward_state_raw"])],
                    ),
                    "later_checks": ["type", "compile"],
                    "contract_ref": "Game.Core/Contracts/Reward/RewardReadOnlyState.cs",
                    "handoff": "RewardStateOwner exposes RewardReadOnlyState snapshot",
                }
            ],
            "adapters": [
                {
                    "id": "ADP-REWARD-SCENE",
                    "dependencies": ["RewardStateOwner", "SelectRewardCommand"],
                    "lifecycle": "Ready -> BindSignals -> ForwardCommands -> ExitTreeUnbind",
                    "arbitrates_domain_rules": False,
                    "direct_state_mutation": False,
                    "responsible_task_ids": [102],
                    "availability": "existing",
                    "expected_type": "Game.Godot.Adapters.RewardSceneAdapter",
                    "target_ref": _owned_ref(
                        "implementation_reference",
                        "Game.Godot/Adapters/RewardSceneAdapter.cs",
                        [("Game.Godot/Adapters/RewardSceneAdapter.cs", assets["adapter_raw"])],
                    ),
                    "later_checks": ["type", "compile", "binding"],
                }
            ],
            "bindings": [
                {
                    "id": "BIND-REWARD-CONTROLS",
                    "control_to_target": [
                        {
                            "control": "ConfirmButton.pressed",
                            "target_object": "RewardSceneAdapter.OnSelectOption",
                            "target_resource": "Game.Godot/Resources/RewardTheme.tres",
                            "via_command": "CMD-SELECT-REWARD",
                            "reads_state": "STATE-REWARD",
                            "direct_state_write": False,
                        }
                    ],
                    "responsible_task_ids": [102],
                    "availability": "existing",
                    "expected_type": "RewardThemeResource",
                    "target_ref": _owned_ref(
                        "implementation_reference",
                        "Game.Godot/Resources/RewardTheme.tres",
                        [("Game.Godot/Resources/RewardTheme.tres", assets["resource_raw"])],
                    ),
                    "later_checks": ["type", "compile", "binding"],
                }
            ],
            "scenes_and_resources": (
                [
                    {
                        "id": "SCENE-REWARD",
                        "kind": "scene",
                        "scene_entry": ["CombatVictory -> RewardScene"],
                        "scene_return": ["RewardSelected -> MapScene"],
                        "responsible_task_ids": [102],
                        "availability": "existing",
                        "expected_type": "Control",
                        "target_ref": _owned_ref(
                            "implementation_reference",
                            "Game.Godot/Scenes/RewardScene.tscn",
                            [("Game.Godot/Scenes/RewardScene.tscn", assets["scene_raw"])],
                        ),
                        "later_checks": ["binding", "engine"],
                    }
                ]
                if ui_applicable
                else []
            ),
            "obligations": [
                {
                    "id": "OBL-REWARD-STAGE4",
                    "requirement_ids": ["RQ-REWARD-1"],
                    "flow_ids": ["FLOW-REWARD"],
                    "test_ids": ["RewardStage4ContractTests"],
                    "responsibility": "Verify Stage-4 command pre/post/inv and read-only state boundary.",
                    "task_ids": [101, 102],
                    "verification_refs": [
                        _owned_ref(
                            "overlay",
                            "docs/architecture/overlays/PRD-REWARD/08/08-Feature-Slice-Reward.md",
                            [("docs/architecture/overlays/PRD-REWARD/08/08-Feature-Slice-Reward.md", assets["overlay_raw"])],
                        )
                    ],
                }
            ],
            "ui_slice": (
                {
                    "applicable": True,
                    "rationale": "Reward screen has interactive selection controls.",
                    "inputs": ["ConfirmButton.pressed", "SkipButton.pressed"],
                    "methods": ["RewardSceneAdapter.OnSelectOption"],
                    "wiring": ["ConfirmButton.pressed -> RewardSceneAdapter.OnSelectOption -> CMD-SELECT-REWARD"],
                    "human_zones": ["layout", "art", "animation"],
                    "modified_zones": [],
                    "direct_state_writes": [],
                }
                if ui_applicable
                else {
                    "applicable": False,
                    "rationale": "Headless core-only flow with no Godot scene or UI obligation.",
                }
            ),
        }
        return req


class Chapter4BindingMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        # Warm the default immutable template cache once per test run.
        warm = Chapter4RepoFixture()
        try:
            warm.build_committed_bundle(ui_applicable=True, include_other_plan=True)
        finally:
            warm.cleanup()

    @classmethod
    def tearDownClass(cls) -> None:
        Chapter4RepoFixture.clear_template_cache()

    def setUp(self) -> None:
        self.fx = Chapter4RepoFixture()
        self.addCleanup(self.fx.cleanup)

    def _run_full_lifecycle(self, op_id: str, request: dict) -> dict:
        req_rel = f"logs/ci/requests/{op_id}.json"
        self.fx.put_json(req_rel, request)
        prep = ch4.prepare(self.fx.root, operation_id=op_id, request_ref=req_rel)
        self.assertEqual("prepared", prep["state"])
        res = ch4.reserve(self.fx.root, operation_id=op_id)
        self.assertEqual("reserved", res["state"])
        insp = ch4.inspect(self.fx.root, operation_id=op_id)
        self.assertEqual("inspected", insp["status"])
        app = commit.execute(self.fx.root, operation_id=op_id, stage="apply")
        self.assertEqual("applied", app["state"])
        ver = commit.execute(self.fx.root, operation_id=op_id, stage="verify")
        self.assertEqual("verified", ver["state"])
        pub = commit.execute(self.fx.root, operation_id=op_id, stage="publish")
        self.assertTrue(pub["published"])
        self.assertEqual("complete", pub["state"])
        return pub

    # --- Matrix Row 1: REUSE + Shared-Task Conservation + Clean-Clone extract_stage4_semantics ---

    def test_reuse_zero_edits_shared_task_conservation_and_clean_clone_semantics(self) -> None:
        assets = self.fx.build_committed_bundle(ui_applicable=True, include_other_plan=True)
        before_code_overlay_triplet = self.fx.snapshot_tree(("Game.Core", "Game.Godot", "docs/architecture", ".taskmaster"))
        old_plan_bytes = (self.fx.root / "docs/planning/b-route/plans/plan-reward/1.json").read_bytes()

        op_id = "OP-CH4-REUSE-001"
        req = self.fx.base_reuse_request(op_id, assets, ui_applicable=True)
        req_rel = f"logs/ci/requests/{op_id}.json"
        self.fx.put_json(req_rel, req)

        # Preview is strictly read-only.
        before_all = self.fx.snapshot_tree(("docs", ".taskmaster", "Game.Core", "Game.Godot"))
        prev = ch4.preview(self.fx.root, operation_id=op_id, request_ref=req_rel)
        self.assertEqual("previewed", prev["status"])
        self.assertFalse(prev["has_public_changes"])
        self.assertFalse(prev["readiness"])
        self.assertFalse(prev["runtime_verified"])
        self.assertFalse(prev["default_b_enabled"])
        self.assertEqual(before_all, self.fx.snapshot_tree(("docs", ".taskmaster", "Game.Core", "Game.Godot")))

        # Run prepare -> publish.
        pub = self._run_full_lifecycle(op_id, req)
        self.assertFalse(pub["readiness"])
        self.assertFalse(pub["runtime_verified"])
        self.assertFalse(pub["default_b_enabled"])

        # Zero changes to Game.Core, Game.Godot, overlays, triplet, or old plan!
        self.assertEqual(
            before_code_overlay_triplet,
            self.fx.snapshot_tree(("Game.Core", "Game.Godot", "docs/architecture", ".taskmaster")),
        )
        self.assertEqual(old_plan_bytes, (self.fx.root / "docs/planning/b-route/plans/plan-reward/1.json").read_bytes())

        # Verify stage=4 binding & single-task applicable parts (Task 101 only has domain_rules!).
        stage4_binding = self.fx.read_json("docs/planning/b-route/bindings/plan-reward/2.json")
        self.assertEqual("4", stage4_binding["stage"])
        self.assertEqual(2, stage4_binding["binding_revision"])
        self.assertEqual([101, 102], [m["task_id"] for m in stage4_binding["task_mappings"]])
        self.assertEqual(4, len(stage4_binding["parts"]))
        self.assertEqual(["domain_rules"], stage4_binding["task_mappings"][0]["part_kinds"])

        # Shared Task 101 preserves plan-combat plan_ref and binding_ref in task-origins and catalog!
        origins = self.fx.read_json("docs/planning/b-route/task-origins.v1.json")
        t101_origin = next(r for r in origins["tasks"] if r["task_id"] == 101)
        self.assertEqual({"plan-combat", "plan-reward"}, {r["entity_id"] for r in t101_origin["plan_refs"]})
        self.assertEqual(
            {"plan-combat": 1, "plan-reward": 2},
            {r["entity_id"]: r["revision"] for r in t101_origin["binding_refs"]},
        )

        # Story 3.3 resolve_task_origin succeeds cleanly and returns both plans for shared Task 101.
        r101 = task_resolver.resolve_task_origin(self.fx.root, 101)
        self.assertTrue(r101["ok"] and r101["stable"])
        self.assertEqual("B", r101["route"])
        self.assertEqual({"plan-combat", "plan-reward"}, {r["entity_id"] for r in r101["plan_refs"]})

        # Clean clone without logs/: extract_stage4_semantics works with zero logs/!
        with tempfile.TemporaryDirectory() as clone_tmp:
            clone_root = Path(clone_tmp)
            for folder in ("docs", "Game.Core", "Game.Godot", ".taskmaster", "sources", "evidence"):
                if (self.fx.root / folder).exists():
                    shutil.copytree(self.fx.root / folder, clone_root / folder)
            self.assertFalse((clone_root / "logs").exists())
            plan_doc = json.loads((clone_root / "docs/planning/b-route/plans/plan-reward/1.json").read_text(encoding="utf-8"))
            binding_doc = json.loads((clone_root / "docs/planning/b-route/bindings/plan-reward/2.json").read_text(encoding="utf-8"))
            sem = ch4.extract_stage4_semantics(plan_doc, binding_doc)
            self.assertEqual(ch4.STAGE4_SEMANTICS_SCHEMA, sem["schema_version"])
            self.assertEqual([101, 102], sem["task_ids"])
            self.assertEqual("RewardStateOwner", sem["commands"][0]["owner"])
            self.assertEqual(["Reward session is active and unlocked."], sem["commands"][0]["preconditions"])
            self.assertEqual("RewardStateOwner", sem["read_only_states"][0]["single_owner"])
            self.assertTrue(sem["adapters"][0]["forbidden_arbitration"])
            self.assertEqual("ConfirmButton.pressed", sem["bindings"][0]["control_to_target"][0]["control"])
            self.assertEqual(["CombatVictory -> RewardScene"], sem["scenes_and_resources"][0]["scene_entry"])
            self.assertTrue(sem["ui_slice"]["applicable"])
            self.assertEqual(["animation", "art", "layout"], sem["ui_slice"]["human_zones"])
            self.assertTrue(sem["ui_slice"]["chapter7_required"])
            self.assertFalse(sem["readiness"])

    def test_reuse_blocks_non_b_task_missing_3c_and_altered_task_id_set(self) -> None:
        # 1. Missing 3C binding -> blocked with return_stage=3C.
        fx_no_3c = Chapter4RepoFixture()
        self.addCleanup(fx_no_3c.cleanup)
        assets_no_3c = fx_no_3c.build_committed_bundle(include_3c_binding=False)
        req_no_3c = fx_no_3c.base_reuse_request("OP-NO-3C", assets_no_3c)
        fx_no_3c.put_json("logs/ci/requests/no3c.json", req_no_3c)
        with self.assertRaises(codec.CodecError) as ctx:
            ch4.preview(fx_no_3c.root, operation_id="OP-NO-3C", request_ref="logs/ci/requests/no3c.json")
        self.assertEqual("3C", ch4.extract_mismatch_attribution(ctx.exception.diagnostic.to_dict())["return_stage"])

        # 2. Altered task_id set / non-B task 103 -> blocked with return_stage=3C.
        assets = self.fx.build_committed_bundle(include_non_b_task=True)
        req = self.fx.base_reuse_request("OP-BAD-TIDS", assets)
        req["task_ids"] = [101, 102, 103]
        self.fx.put_json("logs/ci/requests/badtids.json", req)
        with self.assertRaises(codec.CodecError) as ctx2:
            ch4.preview(self.fx.root, operation_id="OP-BAD-TIDS", request_ref="logs/ci/requests/badtids.json")
        self.assertEqual("3C", ch4.extract_mismatch_attribution(ctx2.exception.diagnostic.to_dict())["return_stage"])

    # --- Matrix Row 2: PUB_SYNC + Raw-Byte Journal Crash/Recover + Story 3.3 Pending Block ---

    def _make_pub_sync_request(self, op_id: str, assets: dict[str, object]) -> dict:
        new_contract_path = "Game.Core/Contracts/Events/RewardClaimedEvent.cs"
        new_contract_text = (
            "using System;\n\n"
            "namespace Game.Core.Contracts.Events;\n\n"
            "/// <summary>\n"
            "/// Event emitted after a reward option is claimed.\n"
            "/// </summary>\n"
            "/// <remarks>\n"
            "/// Uses canonical ADR-0004 EventTypes constant.\n"
            "/// </remarks>\n"
            "public sealed record RewardClaimedEvent(string RunId, int OptionIndex)\n"
            "{\n"
            "    public const string EventType = EventTypes.RewardClaimed;\n"
            "}\n"
        )
        overlay_path = "docs/architecture/overlays/PRD-REWARD/08/08-Feature-Slice-Reward.md"
        overlay_norm = assets["overlay_raw"].decode("utf-8").replace("\r\n", "\n")
        overlay_sha = "sha256:" + hashlib.sha256(overlay_norm.encode("utf-8")).hexdigest()
        req = self.fx.base_reuse_request(op_id, assets, ui_applicable=True)
        req["public_changes"] = {
            "contracts": [
                {
                    "path": new_contract_path,
                    "content": new_contract_text,
                    "expected_before_sha256": None,
                    "event_constants": [{"name": "RewardClaimed", "value": "core.reward.claimed"}],
                }
            ],
            "overlays": [
                {
                    "path": overlay_path,
                    "scaffold_update": {
                        "expected_sha256": overlay_sha,
                        "strict_incremental_patch": True,
                        "sections": [
                            {
                                "heading": "Contracts",
                                "operation": "append",
                                "bullets": [f"`{new_contract_path}`"],
                            }
                        ],
                    },
                }
            ],
            "triplet_ref_sync": [
                {
                    "task_id": 101,
                    "add_contract_refs": ["core.reward.claimed"],
                    "add_overlay_refs": [overlay_path],
                    "add_acceptance": [
                        f"Emit core.reward.claimed after reward claim. Refs: {new_contract_path}"
                    ],
                }
            ],
        }
        # Point obligation verification_ref to the new contract + updated EventTypes.cs post-sync closure!
        new_contract_bytes = new_contract_text.encode("utf-8")
        merged_ev_bytes = ch4._merge_event_types_source(
            assets["event_types_raw"].decode("utf-8"),
            [{"name": "RewardClaimed", "value": "core.reward.claimed"}],
        ).encode("utf-8")
        req["obligations"][0]["verification_refs"] = [
            _owned_ref(
                "contract",
                new_contract_path,
                [
                    ("Game.Core/Contracts/EventTypes.cs", merged_ev_bytes),
                    (new_contract_path, new_contract_bytes),
                ],
            )
        ]
        return req

    def test_pub_sync_crash_recover_public_sync_journal_and_commit_with_live_status_and_33_blocking(self) -> None:
        assets = self.fx.build_committed_bundle(ui_applicable=True, include_other_plan=True)
        op_id = "OP-CH4-PUBSYNC-001"
        req = self._make_pub_sync_request(op_id, assets)
        req_rel = f"logs/ci/requests/{op_id}.json"
        self.fx.put_json(req_rel, req)

        # Ensure raw-byte journal NEVER feeds into JSON journal.create_journal!
        with patch.object(journal, "create_journal", side_effect=AssertionError("must never call create_journal")):
            ch4.prepare(self.fx.root, operation_id=op_id, request_ref=req_rel)
            ch4.reserve(self.fx.root, operation_id=op_id)

            # Advance live Task 101 status BEFORE apply to prove live status merge preserves it!
            master_doc = self.fx.read_json(ch4.TRIPLET["master"])
            master_doc["master"]["tasks"][0]["status"] = "in-progress"
            self.fx.put_json(ch4.TRIPLET["master"], master_doc)

            # 1. Crash mid-way through public-sync-journal (after writing first file)!
            def crash_mid_sync(name: str) -> None:
                if name == "public_sync_after_file:0":
                    raise RuntimeError("simulated power loss mid public-sync")

            with patch.object(ch4, "_checkpoint", side_effect=crash_mid_sync):
                with self.assertRaises(codec.CodecError):
                    commit.execute(self.fx.root, operation_id=op_id, stage="apply")

            # Public-sync pending marker MUST exist and Story 3.3 MUST conservatively block with PENDING!
            j_rel, p_rel = ch4.public_sync_paths(op_id)
            self.assertTrue((self.fx.root / j_rel).is_file())
            self.assertTrue((self.fx.root / p_rel).is_file())
            blocked_33 = task_resolver.resolve_task_origin(self.fx.root, 101)
            self.assertFalse(blocked_33["ok"])
            self.assertEqual("blocked", blocked_33["route"])
            self.assertEqual("pending", blocked_33["diagnostics"][0]["reason_code"])

            # inspect_recovery sees public_sync_partial -> next_stage='apply'.
            rec_info = commit.inspect_recovery(self.fx.root, operation_id=op_id)
            self.assertEqual("public_sync_partial", rec_info["physical_state"])
            self.assertEqual("apply", rec_info["next_stage"])

            # 2. Resume via commit.recover, but crash AGAIN inside commit.json at receipt_durable!
            def crash_at_receipt(name: str) -> None:
                if name == "receipt_durable":
                    raise RuntimeError("simulated crash after receipt write before catalog publish")

            with patch.object(commit, "_checkpoint", side_effect=crash_at_receipt):
                with self.assertRaises(codec.CodecError):
                    commit.recover(self.fx.root, operation_id=op_id)

            # Story 3.3 STILL conservatively blocks with PENDING!
            blocked_33_commit = task_resolver.resolve_task_origin(self.fx.root, 101)
            self.assertFalse(blocked_33_commit["ok"])
            self.assertEqual("blocked", blocked_33_commit["route"])
            self.assertEqual("pending", blocked_33_commit["diagnostics"][0]["reason_code"])

            # 3. Final recover finishes publication cleanly!
            recovered = commit.recover(self.fx.root, operation_id=op_id)
            self.assertTrue(recovered["published"])
            self.assertFalse((self.fx.root / p_rel).exists())
            pub_j_doc = self.fx.read_json(j_rel)
            self.assertEqual("complete", pub_j_doc["phase"])

            # Idempotent second recover returns noop=True!
            noop = commit.recover(self.fx.root, operation_id=op_id)
            self.assertTrue(noop["published"] and noop["noop"])

        # Verify EventTypes.cs updated, Overlay table/prose/code preserved, and live Task status preserved!
        ev_text = (self.fx.root / "Game.Core/Contracts/EventTypes.cs").read_text(encoding="utf-8")
        self.assertIn('RewardClaimed = "core.reward.claimed"', ev_text)
        ov_text = (self.fx.root / "docs/architecture/overlays/PRD-REWARD/08/08-Feature-Slice-Reward.md").read_text(encoding="utf-8")
        self.assertIn("| Locked option ordering | RewardStateOwner |", ov_text)
        self.assertIn("var locked = true;", ov_text)
        self.assertIn("Game.Core/Contracts/Events/RewardClaimedEvent.cs", ov_text)
        live_master = self.fx.read_json(ch4.TRIPLET["master"])
        self.assertEqual("in-progress", live_master["master"]["tasks"][0]["status"])
        live_back = self.fx.read_json(ch4.TRIPLET["back"])
        self.assertIn("core.reward.claimed", live_back[0]["contractRefs"])
        self.assertEqual(2, len(live_back[0]["acceptance"]))

        # Story 3.3 now passes cleanly!
        ok_33 = task_resolver.resolve_task_origin(self.fx.root, 101)
        self.assertTrue(ok_33["ok"] and ok_33["stable"])
        self.assertEqual("B", ok_33["route"])

    def test_pub_sync_blocks_godot_using_empty_dto_empty_interface_drift_and_weak_acceptance(self) -> None:
        assets = self.fx.build_committed_bundle(ui_applicable=True)
        bad_cases = [
            (
                "godot_dependency",
                "using Godot;\nnamespace Game.Core.Contracts.Events;\n/// <summary>Bad.</summary>\npublic sealed record BadEvt(string Id);\n",
            ),
            (
                "non_bcl_using",
                "using Newtonsoft.Json;\nnamespace Game.Core.Contracts.Events;\n/// <summary>Bad.</summary>\npublic sealed record BadEvt(string Id);\n",
            ),
            (
                "empty_dto_positional",
                "namespace Game.Core.Contracts.Events;\n/// <summary>Empty.</summary>\npublic sealed record EmptyDto();\n",
            ),
            (
                "empty_interface",
                "namespace Game.Core.Contracts.Events;\n/// <summary>Empty.</summary>\npublic interface IEmptyContract { }\n",
            ),
        ]
        for label, cs_code in bad_cases:
            with self.subTest(case=label):
                req = self._make_pub_sync_request(f"OP-BAD-{label}", assets)
                req["public_changes"]["contracts"][0]["content"] = cs_code
                req["public_changes"]["contracts"][0]["event_constants"] = []
                req["public_changes"]["triplet_ref_sync"] = []
                req["obligations"][0]["verification_refs"] = []
                self.fx.put_json(f"logs/ci/requests/{label}.json", req)
                with self.assertRaises(codec.CodecError) as ctx:
                    ch4.preview(self.fx.root, operation_id=f"OP-BAD-{label}", request_ref=f"logs/ci/requests/{label}.json")
                self.assertEqual("4", ch4.extract_mismatch_attribution(ctx.exception.diagnostic.to_dict())["return_stage"])

        # Overlay hash drift -> INPUT_STALE, return_stage=4.
        req_drift = self._make_pub_sync_request("OP-DRIFT", assets)
        req_drift["public_changes"]["overlays"][0]["scaffold_update"]["expected_sha256"] = "sha256:" + "0" * 64
        self.fx.put_json("logs/ci/requests/drift.json", req_drift)
        with self.assertRaises(codec.CodecError) as ctx_drift:
            ch4.preview(self.fx.root, operation_id="OP-DRIFT", request_ref="logs/ci/requests/drift.json")
        self.assertEqual(codec.ReasonCode.INPUT_STALE, ctx_drift.exception.diagnostic.reason_code)

        # Weakening Acceptance (dropping existing entry) -> SEMANTIC_ERROR, return_stage=4.
        req_weak = self._make_pub_sync_request("OP-WEAK-ACC", assets)
        req_weak["public_changes"]["triplet_ref_sync"][0]["replace_acceptance"] = [
            "Only new entry. Refs: Game.Core/Contracts/Events/RewardClaimedEvent.cs"
        ]
        self.fx.put_json("logs/ci/requests/weak.json", req_weak)
        with self.assertRaises(codec.CodecError) as ctx_weak:
            ch4.preview(self.fx.root, operation_id="OP-WEAK-ACC", request_ref="logs/ci/requests/weak.json")
        self.assertEqual(codec.ReasonCode.SEMANTIC_ERROR, ctx_weak.exception.diagnostic.reason_code)
        self.assertEqual("4", ch4.extract_mismatch_attribution(ctx_weak.exception.diagnostic.to_dict())["return_stage"])

    # --- Matrix Row 3: PLANNED Dual-State Verification ---

    def test_planned_objects_publish_without_claiming_passed_and_reject_missing_checks_or_fake_nodes(self) -> None:
        assets = self.fx.build_committed_bundle(ui_applicable=True)
        op_id = "OP-CH4-PLANNED-001"
        req = self.fx.base_reuse_request(op_id, assets, ui_applicable=True)
        req["commands"][0]["availability"] = "planned"
        req["commands"][0]["target_ref"] = None
        req["commands"][0]["later_checks"] = ["type", "compile"]
        req["scenes_and_resources"][0]["availability"] = "planned"
        req["scenes_and_resources"][0]["target_ref"] = None
        req["scenes_and_resources"][0]["later_checks"] = ["binding", "engine"]

        pub = self._run_full_lifecycle(op_id, req)
        self.assertTrue(pub["published"])
        self.assertFalse(pub["readiness"])
        self.assertFalse(pub["runtime_verified"])
        plan_doc = self.fx.read_json("docs/planning/b-route/plans/plan-reward/1.json")
        binding_doc = self.fx.read_json("docs/planning/b-route/bindings/plan-reward/2.json")
        sem = ch4.extract_stage4_semantics(plan_doc, binding_doc)
        self.assertEqual({"CMD-SELECT-REWARD", "SCENE-REWARD"}, {o["id"] for o in sem["planned_objects"]})

        # Missing required later_checks on planned -> blocked.
        bad_planned = copy.deepcopy(req)
        bad_planned["operation_id"] = "OP-PLANNED-BAD-CHECKS"
        bad_planned["scenes_and_resources"][0]["later_checks"] = ["type"]  # missing binding & engine!
        self.fx.put_json("logs/ci/requests/bad_planned.json", bad_planned)
        with self.assertRaises(codec.CodecError) as ctx:
            ch4.preview(self.fx.root, operation_id="OP-PLANNED-BAD-CHECKS", request_ref="logs/ci/requests/bad_planned.json")
        self.assertEqual("4", ch4.extract_mismatch_attribution(ctx.exception.diagnostic.to_dict())["return_stage"])

        # Planned claiming passed -> blocked.
        bad_claimed = copy.deepcopy(req)
        bad_claimed["operation_id"] = "OP-PLANNED-CLAIMED"
        bad_claimed["commands"][0]["claimed_passed"] = True
        self.fx.put_json("logs/ci/requests/bad_claimed.json", bad_claimed)
        with self.assertRaises(codec.CodecError):
            ch4.preview(self.fx.root, operation_id="OP-PLANNED-CLAIMED", request_ref="logs/ci/requests/bad_claimed.json")

        # Existing missing file or fake node in .tscn -> blocked.
        fake_raw = self.fx.put("Game.Godot/Scenes/FakeScene.tscn", '[gd_scene format=3]\n[node name="FAKE_NODE" type="Control"]\n')
        bad_fake = self.fx.base_reuse_request("OP-FAKE-NODE", assets, ui_applicable=True)
        bad_fake["scenes_and_resources"][0]["target_ref"] = _owned_ref(
            "implementation_reference", "Game.Godot/Scenes/FakeScene.tscn", [("Game.Godot/Scenes/FakeScene.tscn", fake_raw)]
        )
        self.fx.put_json("logs/ci/requests/fake_node.json", bad_fake)
        with self.assertRaises(codec.CodecError) as ctx_fake:
            ch4.preview(self.fx.root, operation_id="OP-FAKE-NODE", request_ref="logs/ci/requests/fake_node.json")
        self.assertEqual("4", ch4.extract_mismatch_attribution(ctx_fake.exception.diagnostic.to_dict())["return_stage"])

    # --- Matrix Row 4: MISMATCH Attribution (3A / 3B / 3C / 4) ---

    def test_mismatch_attribution_returns_3a_3b_3c_4_with_six_field_diagnostics_and_no_plan_edits(self) -> None:
        # 3A: source_gap requirement.
        fx_3a = Chapter4RepoFixture()
        self.addCleanup(fx_3a.cleanup)
        assets_3a = fx_3a.build_committed_bundle(source_gap_req=True)
        req_3a = fx_3a.base_reuse_request("OP-MIS-3A", assets_3a)
        fx_3a.put_json("logs/ci/requests/mis3a.json", req_3a)
        with self.assertRaises(codec.CodecError) as ctx_3a:
            ch4.preview(fx_3a.root, operation_id="OP-MIS-3A", request_ref="logs/ci/requests/mis3a.json")
        d3a = ctx_3a.exception.diagnostic.to_dict()
        self.assertEqual(DIAGNOSTIC_KEYS, set(d3a))
        self.assertEqual("3A", ch4.extract_mismatch_attribution(d3a)["return_stage"])

        # 3B: unknown command ID + integration_only_owner inventing planned API.
        assets = self.fx.build_committed_bundle(integration_only_task101=True)
        old_plan = (self.fx.root / "docs/planning/b-route/plans/plan-reward/1.json").read_bytes()
        req_3b_unknown = self.fx.base_reuse_request("OP-MIS-3B-UNK", assets)
        req_3b_unknown["commands"][0]["id"] = "CMD-DOES-NOT-EXIST"
        self.fx.put_json("logs/ci/requests/mis3b_unk.json", req_3b_unknown)
        with self.assertRaises(codec.CodecError) as ctx_3b:
            ch4.preview(self.fx.root, operation_id="OP-MIS-3B-UNK", request_ref="logs/ci/requests/mis3b_unk.json")
        self.assertEqual("3B", ch4.extract_mismatch_attribution(ctx_3b.exception.diagnostic.to_dict())["return_stage"])
        self.assertEqual(old_plan, (self.fx.root / "docs/planning/b-route/plans/plan-reward/1.json").read_bytes())

        req_3b_ioo = self.fx.base_reuse_request("OP-MIS-3B-IOO", assets)
        req_3b_ioo["commands"][0]["availability"] = "planned"
        req_3b_ioo["commands"][0]["target_ref"] = None
        self.fx.put_json("logs/ci/requests/mis3b_ioo.json", req_3b_ioo)
        with self.assertRaises(codec.CodecError) as ctx_ioo:
            ch4.preview(self.fx.root, operation_id="OP-MIS-3B-IOO", request_ref="logs/ci/requests/mis3b_ioo.json")
        self.assertEqual("3B", ch4.extract_mismatch_attribution(ctx_ioo.exception.diagnostic.to_dict())["return_stage"])

        # 4: adapter domain arbitration & binding direct state write.
        req_4_arb = self.fx.base_reuse_request("OP-MIS-4-ARB", assets)
        req_4_arb["adapters"][0]["arbitrates_domain_rules"] = True
        self.fx.put_json("logs/ci/requests/mis4_arb.json", req_4_arb)
        with self.assertRaises(codec.CodecError) as ctx_4:
            ch4.preview(self.fx.root, operation_id="OP-MIS-4-ARB", request_ref="logs/ci/requests/mis4_arb.json")
        self.assertEqual("4", ch4.extract_mismatch_attribution(ctx_4.exception.diagnostic.to_dict())["return_stage"])

        req_4_dsw = self.fx.base_reuse_request("OP-MIS-4-DSW", assets)
        req_4_dsw["bindings"][0]["control_to_target"][0]["direct_state_write"] = True
        self.fx.put_json("logs/ci/requests/mis4_dsw.json", req_4_dsw)
        with self.assertRaises(codec.CodecError) as ctx_dsw:
            ch4.preview(self.fx.root, operation_id="OP-MIS-4-DSW", request_ref="logs/ci/requests/mis4_dsw.json")
        self.assertEqual("4", ch4.extract_mismatch_attribution(ctx_dsw.exception.diagnostic.to_dict())["return_stage"])

    # --- Matrix Row 5: UI_SLICE (With UI, Evidence-Backed No-UI, Undeclared Exemption, Human Zone Violation) ---

    def test_ui_slice_no_ui_with_3b_rationale_and_reject_undeclared_exemption_or_human_zone_encroachment(self) -> None:
        # 1. Valid 3B no-UI flow -> succeeds, chapter7_required=False, no Chapter 7 files created.
        assets_no_ui = self.fx.build_committed_bundle(ui_applicable=False, include_other_plan=False)
        req_no_ui = self.fx.base_reuse_request("OP-NO-UI-OK", assets_no_ui, ui_applicable=False)
        pub = self._run_full_lifecycle("OP-NO-UI-OK", req_no_ui)
        self.assertTrue(pub["published"])
        self.assertFalse((self.fx.root / "docs/gdd/ui-gdd-flow.md").exists())
        sem = ch4.extract_stage4_semantics(
            self.fx.read_json("docs/planning/b-route/plans/plan-reward/1.json"),
            self.fx.read_json("docs/planning/b-route/bindings/plan-reward/2.json"),
        )
        self.assertFalse(sem["ui_slice"]["applicable"])
        self.assertFalse(sem["ui_slice"]["chapter7_required"])

        # 2. Undeclared UI exemption on UI-applicable 3B flow -> blocked (return_stage=3B).
        fx_ui = Chapter4RepoFixture()
        self.addCleanup(fx_ui.cleanup)
        assets_ui = fx_ui.build_committed_bundle(ui_applicable=True, include_other_plan=False)
        req_exempt = fx_ui.base_reuse_request("OP-BAD-EXEMPT", assets_ui, ui_applicable=True)
        req_exempt["ui_slice"] = {"applicable": False, "rationale": "Skip UI without 3B basis."}
        fx_ui.put_json("logs/ci/requests/exempt.json", req_exempt)
        with self.assertRaises(codec.CodecError) as ctx_ex:
            ch4.preview(fx_ui.root, operation_id="OP-BAD-EXEMPT", request_ref="logs/ci/requests/exempt.json")
        self.assertEqual("3B", ch4.extract_mismatch_attribution(ctx_ex.exception.diagnostic.to_dict())["return_stage"])

        # 3. Encroaching on human-owned layout/art/animation zone -> blocked (return_stage=4).
        for zone in ("layout", "art", "animation"):
            with self.subTest(zone=zone):
                req_zone = fx_ui.base_reuse_request(f"OP-ZONE-{zone}", assets_ui, ui_applicable=True)
                req_zone["ui_slice"]["modified_zones"] = [zone]
                fx_ui.put_json(f"logs/ci/requests/zone_{zone}.json", req_zone)
                with self.assertRaises(codec.CodecError) as ctx_z:
                    ch4.preview(fx_ui.root, operation_id=f"OP-ZONE-{zone}", request_ref=f"logs/ci/requests/zone_{zone}.json")
                self.assertEqual("4", ch4.extract_mismatch_attribution(ctx_z.exception.diagnostic.to_dict())["return_stage"])

        # 4. UI direct state write -> blocked (return_stage=4).
        req_ui_write = fx_ui.base_reuse_request("OP-UI-WRITE", assets_ui, ui_applicable=True)
        req_ui_write["ui_slice"]["direct_state_writes"] = ["STATE-REWARD"]
        fx_ui.put_json("logs/ci/requests/ui_write.json", req_ui_write)
        with self.assertRaises(codec.CodecError) as ctx_w:
            ch4.preview(fx_ui.root, operation_id="OP-UI-WRITE", request_ref="logs/ci/requests/ui_write.json")
        self.assertEqual("4", ch4.extract_mismatch_attribution(ctx_w.exception.diagnostic.to_dict())["return_stage"])

    # --- Story 2.8 Compensation Compatibility ---

    def test_story_2_8_compensation_build_compatible_with_published_stage4_binding(self) -> None:
        assets = self.fx.build_committed_bundle(ui_applicable=True, include_other_plan=False)

        # Register the bootstrap 3B+3C commit (OP-BOOTSTRAP-3C) as a real terminal adoption operation
        # in the operation store so _b_route_compensation.build verifies its historical receipt chain
        # without any mocking of formal proof validation.
        orig_op_id = "OP-BOOTSTRAP-3C"
        policy_path = records.BASE + "policy.v1.json"
        plan_path = f"{records.BASE}plans/{self.fx.plan_id}/1.json"
        b3c_path = f"{records.BASE}bindings/{self.fx.plan_id}/1.json"
        origins_path = records.BASE + "task-origins.v1.json"
        policy_doc = self.fx.read_json(policy_path)
        plan_doc = self.fx.read_json(plan_path)
        b3c_doc = self.fx.read_json(b3c_path)
        origins_doc = self.fx.read_json(origins_path)
        policy_raw = (self.fx.root / policy_path).read_bytes()
        plan_raw = (self.fx.root / plan_path).read_bytes()
        b3c_raw = (self.fx.root / b3c_path).read_bytes()
        origins_raw = (self.fx.root / origins_path).read_bytes()

        dummy_proof_raw = self.fx.put_json("evidence/orig-handoff.json", {"ok": True})
        dummy_ref = {
            "path": "evidence/orig-handoff.json",
            "schema_version": "fixture.v1",
            "raw_digest": codec.raw_digest(dummy_proof_raw),
        }
        orig_request = {
            "schema_version": "newrouge.b-route-adoption-request.v1",
            "operation_id": orig_op_id,
            "material": {
                "planner": "mvg",
                "run_id": "fixture-run",
                "handoff_ref": dummy_ref,
                "protection_ref": dummy_ref,
                "authority_refs": [dummy_ref],
                "identity_alignment": {
                    "plan": {"mode": "new"},
                    "binding": {"mode": "none"},
                    "requirements": [],
                    "flows": [],
                    "tasks": [],
                },
                "target_templates": [{"payload": {"plan_id": self.fx.plan_id}}],
                "lineage_refs": [],
            },
            "review_ref": dummy_ref,
        }
        orig_targets = [
            {
                "path": policy_path,
                "schema_version": "newrouge.b-route-policy.v1",
                "before_raw_digest": None,
                "after_payload": policy_doc,
                "after_raw_digest": codec.raw_digest(policy_raw),
                "verification_mode": "immutable_bytes",
            },
            {
                "path": plan_path,
                "schema_version": "newrouge.b-route-plan.v1",
                "before_raw_digest": None,
                "after_payload": plan_doc,
                "after_raw_digest": codec.raw_digest(plan_raw),
                "verification_mode": "immutable_bytes",
            },
            {
                "path": b3c_path,
                "schema_version": "newrouge.b-route-binding.v1",
                "before_raw_digest": None,
                "after_payload": b3c_doc,
                "after_raw_digest": codec.raw_digest(b3c_raw),
                "verification_mode": "immutable_bytes",
            },
            {
                "path": origins_path,
                "schema_version": "newrouge.b-route-origins.v1",
                "before_raw_digest": None,
                "after_payload": origins_doc,
                "after_raw_digest": codec.raw_digest(origins_raw),
                "verification_mode": "immutable_bytes",
            },
        ]
        orig_frozen = {
            "request": copy.deepcopy(orig_request),
            "allocations": {
                "plan_id": self.fx.plan_id,
                "plan_revision": 1,
                "binding_revision": 1,
                "requirements": {"RQ-REWARD-1": "RQ-REWARD-1"},
                "flows": {"FLOW-REWARD": "FLOW-REWARD"},
                "task_definitions": {},
            },
            "scope_ids": [self.fx.scope_id],
            "authority_refs": [],
            "targets": orig_targets,
        }
        journal.prepare_operation(
            self.fx.root, operation_id=orig_op_id, request_raw=_encoded(orig_request), frozen=orig_frozen
        )
        orig_op = journal.reserve_operation(self.fx.root, operation_id=orig_op_id)
        boot_receipt = commit_projection.receipt_for_frozen(
            operation_id=orig_op_id,
            frozen=orig_op["frozen"],
            resolved_definitions=[
                {"kind": "state", "definition_id": "STATE-REWARD", "plan_ref": assets["reward_plan_ref"]}
            ],
            catalog_before=None,
        )
        boot_receipt_path = f"{records.BASE}commits/{orig_op_id}.json"
        boot_receipt_raw = commit_projection.serialized(boot_receipt)
        self.fx.put(boot_receipt_path, boot_receipt_raw)
        boot_catalog = self.fx.read_json(records.CATALOG_PATH)
        boot_catalog["scope_heads"][0]["receipt_ref"] = commit_projection.reference(
            boot_receipt_path, boot_receipt_raw
        )
        boot_catalog_raw = commit_projection.serialized(boot_catalog)
        self.fx.put(records.CATALOG_PATH, boot_catalog_raw)
        policy_identity, _pinned = adoption_review.policy_observations()
        boot_intent_rel = commit._paths(orig_op_id)[0]
        boot_intent = commit._seal(
            {
                "schema_version": commit.SCHEMA,
                "operation_id": orig_op_id,
                "frozen_digest": orig_op["frozen_digest"],
                "policy_identity": policy_identity,
                "phase": "complete",
                "before_files": {
                    policy_path: None,
                    plan_path: None,
                    b3c_path: None,
                    origins_path: None,
                    records.CATALOG_PATH: None,
                },
                "files": {},
                "directories": {},
                "trees": {},
                "receipt": boot_receipt,
                "catalog_before": None,
                "origins_before": None,
                "publication_base": None,
                "catalog_after": commit._encode(boot_catalog_raw),
                "catalog_after_digest": codec.raw_digest(boot_catalog_raw),
                "catalog_attempts": [],
                "catalog_frame": None,
            }
        )
        self.fx.put(boot_intent_rel, commit_projection.serialized(boot_intent))
        self.assertTrue(commit.terminal_valid(self.fx.root, orig_op))

        # Now publish our Stage-4 binding via Story 3.4 full lifecycle!
        op_id = "OP-CH4-COMP-001"
        req = self.fx.base_reuse_request(op_id, assets, ui_applicable=True)
        pub = self._run_full_lifecycle(op_id, req)
        self.assertTrue(pub["published"])

        stage4_path = f"{records.BASE}bindings/{self.fx.plan_id}/2.json"
        stage4_raw = (self.fx.root / stage4_path).read_bytes()
        stage4_ref = _typed_ref(stage4_path, "newrouge.b-route-binding.v1", self.fx.plan_id, 2, stage4_raw)

        comp_request = {
            "schema_version": journal.COMPENSATION_REQUEST,
            "producer": "compensation",
            "operation_id": "OP-COMP-AFTER-CH4",
            "compensates": compensation.relation_for(orig_op),
            "selection": {
                "plan_ref": assets["reward_plan_ref"],
                "binding_ref": stage4_ref,
            },
            "reason": "Reviewed compensation retaining Stage-4 binding semantics.",
        }
        with patch.object(compensation, "_original_review", return_value=([], [])):
            _snap, comp_frozen = compensation.build(self.fx.root, comp_request)

        self.assertEqual("compensation", comp_frozen["producer"])
        self.assertEqual(3, comp_frozen["allocations"]["binding_revision"])
        comp_binding_target = next(t for t in comp_frozen["targets"] if t["schema_version"] == "newrouge.b-route-binding.v1")
        self.assertEqual("4", comp_binding_target["after_payload"]["stage"])
        self.assertEqual(3, comp_binding_target["after_payload"]["binding_revision"])
        self.assertEqual(
            [101, 102], [m["task_id"] for m in comp_binding_target["after_payload"]["task_mappings"]]
        )

    # --- CLI, dev_cli, Builders, Schema Isolation, Policy Anchoring, Zero Bytecode ---

    def test_cli_dev_cli_builders_schema_isolation_and_policy_anchoring(self) -> None:
        # 1. Schema isolation: 7 FORMAL untouched, chapter4-binding-operation in AUXILIARY only.
        self.assertEqual(
            ("common", "policy", "plan", "binding", "origins", "commit", "catalog"),
            schema_resources.FORMAL,
        )
        self.assertIn("chapter4-binding-operation", schema_resources.AUXILIARY)
        self.assertNotIn("chapter4-binding-operation", schema_resources.FORMAL)

        # 2. Policy anchoring in _b_route_adoption_review.policy_observations.
        _identity, pinned_files = adoption_review.policy_observations()
        self.assertTrue(any(p.endswith("_b_route_chapter4_binding.py") for p in pinned_files))
        self.assertTrue(any(p.endswith("chapter4-binding-operation.schema.json") for p in pinned_files))

        # 3. CLI full lifecycle + dev_cli --help + builder.
        proc = subprocess.run(
            [sys.executable, "-B", str(SCRIPTS_PY / "dev_cli.py"), "b-route-chapter4-binding", "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("--stage", proc.stdout)

        args = dev_cli.build_parser().parse_args(
            ["b-route-chapter4-binding", "--root", str(self.fx.root), "--stage", "preview", "--operation-id", "OP-CLI-1", "--request", "logs/ci/r.json"]
        )
        built_cmd = dev_cli_builders.build_b_route_chapter4_binding_cmd(args)
        self.assertIn("refine_b_route_chapter4_binding.py", built_cmd[2])
        self.assertIn("--request", built_cmd)

        assets = self.fx.build_committed_bundle(ui_applicable=True, include_other_plan=False)
        op_id = "OP-CLI-E2E-1"
        req = self.fx.base_reuse_request(op_id, assets, ui_applicable=True)
        req_rel = f"logs/ci/requests/{op_id}.json"
        self.fx.put_json(req_rel, req)

        def call_cli(argv: list[str]) -> tuple[int, dict]:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = ch4_cli.main(argv)
            return rc, json.loads(buf.getvalue().strip())

        rc, out = call_cli(["--root", str(self.fx.root), "--stage", "preview", "--operation-id", op_id, "--request", req_rel])
        self.assertEqual(0, rc)
        self.assertEqual("previewed", out["status"])
        rc, out = call_cli(["--root", str(self.fx.root), "--stage", "prepare", "--operation-id", op_id, "--request", req_rel])
        self.assertEqual(0, rc)
        self.assertEqual("prepared", out["state"])
        for stage in ("reserve", "inspect", "apply", "verify", "publish", "read"):
            rc, out = call_cli(["--root", str(self.fx.root), "--stage", stage, "--operation-id", op_id])
            self.assertEqual(0, rc, f"stage={stage} failed: {out}")
            self.assertFalse(out["readiness"])
            self.assertFalse(out["runtime_verified"])
            self.assertFalse(out["default_b_enabled"])
        self.assertTrue(out["stage4_semantics"])
        events_file = self.fx.root / f"logs/ci/b-route-chapter4-binding/{op_id}/events.jsonl"
        self.assertTrue(events_file.is_file())
        events = [json.loads(line) for line in events_file.read_text(encoding="utf-8").splitlines() if line.strip()]
        self.assertEqual(["prepare", "reserve", "apply", "verify", "publish"], [e["stage"] for e in events])

    # --- Step 4 Review Regression Tests (P-01 .. P-08) ---

    def test_p01_pending_durable_crash_recover_and_corrupt_public_sync_journal(self) -> None:
        assets = self.fx.build_committed_bundle(ui_applicable=True, include_other_plan=True)
        op_id = "OP-CH4-PEND-DURABLE"
        req = self.fx.base_reuse_request(op_id, assets, ui_applicable=True)
        req_rel = f"logs/ci/requests/{op_id}.json"
        self.fx.put_json(req_rel, req)
        ch4.prepare(self.fx.root, operation_id=op_id, request_ref=req_rel)
        ch4.reserve(self.fx.root, operation_id=op_id)

        def crash_pending_durable(name: str) -> None:
            if name == "pending_durable":
                raise RuntimeError("simulated crash immediately after commit.pending.json")

        with patch.object(commit, "_checkpoint", side_effect=crash_pending_durable):
            with self.assertRaises(codec.CodecError):
                commit.execute(self.fx.root, operation_id=op_id, stage="apply")

        intent_rel, pending_rel = commit._paths(op_id)
        self.assertFalse((self.fx.root / intent_rel).exists())
        self.assertTrue((self.fx.root / pending_rel).is_file())

        # External Story 3.3 caller still blocks conservatively with pending.
        blocked = task_resolver.resolve_task_origin(self.fx.root, 101)
        self.assertFalse(blocked["ok"])
        self.assertEqual("blocked", blocked["route"])
        self.assertEqual("pending", blocked["diagnostics"][0]["reason_code"])

        # commit.recover must succeed without deadlocking on own commit.pending.json!
        recovered = commit.recover(self.fx.root, operation_id=op_id)
        self.assertTrue(recovered["published"])
        self.assertEqual("complete", recovered["state"])
        self.assertFalse((self.fx.root / pending_rel).exists())

        # Non-dict corrupt public-sync-journal.json fails cleanly with CodecError (no AttributeError).
        op2 = "OP-CH4-CORRUPT-PUBJ"
        req2 = self.fx.base_reuse_request(op2, assets, ui_applicable=True)
        req2_rel = f"logs/ci/requests/{op2}.json"
        self.fx.put_json(req2_rel, req2)
        ch4.prepare(self.fx.root, operation_id=op2, request_ref=req2_rel)
        j_rel, _p_rel = ch4.public_sync_paths(op2)
        self.fx.put(j_rel, "[]\n")
        corrupt_res = task_resolver.resolve_task_origin(self.fx.root, 101)
        self.assertFalse(corrupt_res["ok"])
        self.assertEqual("blocked", corrupt_res["route"])
        self.assertEqual("invalid_type", corrupt_res["diagnostics"][0]["reason_code"])

    def test_p01_p04_inplace_pub_sync_edit_referenced_contract_and_overlay_and_shared_overlay_preservation(self) -> None:
        assets = self.fx.build_committed_bundle(ui_applicable=True, include_other_plan=True)

        # 1. Publish Stage-4 rev 2 so SelectRewardCommand.cs & 08-Feature-Slice-Reward.md are referenced by OwnedRefs!
        op_rev2 = "OP-CH4-REV2-BASE"
        req_rev2 = self.fx.base_reuse_request(op_rev2, assets, ui_applicable=True)
        self._run_full_lifecycle(op_rev2, req_rev2)

        # Set a pre-existing overlay on shared Task 101 (mapped to both plan-combat and plan-reward).
        master_doc = self.fx.read_json(ch4.TRIPLET["master"])
        master_doc["master"]["tasks"][0]["overlay"] = "docs/architecture/overlays/PRD-COMBAT/08/08-Combat.md"
        self.fx.put_json(ch4.TRIPLET["master"], master_doc)

        # 2. Prepare rev 3 editing EXISTING SelectRewardCommand.cs & EXISTING 08-Feature-Slice-Reward.md in-place!
        op_rev3 = "OP-CH4-INPLACE-PUBSYNC"
        updated_cmd_text = (
            "using System;\n\n"
            "namespace Game.Core.Contracts.Reward;\n\n"
            "/// <summary>\n"
            "/// Production command to select a locked reward option (v2 with source tag).\n"
            "/// </summary>\n"
            "public sealed record SelectRewardCommand(string RunId, int OptionIndex, string SourceTag);\n"
        )
        updated_cmd_raw = updated_cmd_text.encode("utf-8")
        overlay_path = "docs/architecture/overlays/PRD-REWARD/08/08-Feature-Slice-Reward.md"
        overlay_norm = assets["overlay_raw"].decode("utf-8").replace("\r\n", "\n")
        overlay_sha = "sha256:" + hashlib.sha256(overlay_norm.encode("utf-8")).hexdigest()
        req_rev3 = self.fx.base_reuse_request(op_rev3, assets, ui_applicable=True)
        req_rev3["commands"][0]["target_ref"] = _owned_ref(
            "contract",
            "Game.Core/Contracts/Reward/SelectRewardCommand.cs",
            [("Game.Core/Contracts/Reward/SelectRewardCommand.cs", updated_cmd_raw)],
        )
        req_rev3["public_changes"] = {
            "contracts": [
                {
                    "path": "Game.Core/Contracts/Reward/SelectRewardCommand.cs",
                    "content": updated_cmd_text,
                    "expected_before_sha256": codec.raw_digest(assets["reward_cmd_raw"]),
                    "event_constants": [{"name": "RewardRefined", "value": "core.reward.refined"}],
                }
            ],
            "overlays": [
                {
                    "path": overlay_path,
                    "scaffold_update": {
                        "expected_sha256": overlay_sha,
                        "strict_incremental_patch": True,
                        "sections": [
                            {
                                "heading": "Contracts",
                                "operation": "append",
                                "bullets": ["In-place Stage-4 rev 3 contract refinement note."],
                            }
                        ],
                    },
                }
            ],
            "triplet_ref_sync": [
                {
                    "task_id": 101,
                    "add_contract_refs": ["core.reward.refined"],
                    "add_overlay_refs": [overlay_path],
                    "add_acceptance": [
                        "SelectRewardCommand carries SourceTag. Refs: Game.Core/Contracts/Reward/SelectRewardCommand.cs"
                    ],
                }
            ],
        }
        # Compute post-sync overlay bytes for obligation verification_ref.
        merged_ov_md = ch4.overlay_patch.apply_scaffold_update_to_existing_markdown(
            current_markdown=overlay_norm,
            scaffold_update=copy.deepcopy(req_rev3["public_changes"]["overlays"][0]["scaffold_update"]),
        )
        if not merged_ov_md.endswith("\n"):
            merged_ov_md += "\n"
        req_rev3["obligations"][0]["verification_refs"] = [
            _owned_ref("overlay", overlay_path, [(overlay_path, merged_ov_md.encode("utf-8"))])
        ]
        req3_rel = f"logs/ci/requests/{op_rev3}.json"
        self.fx.put_json(req3_rel, req_rev3)

        ch4.prepare(self.fx.root, operation_id=op_rev3, request_ref=req3_rel)
        ch4.reserve(self.fx.root, operation_id=op_rev3)

        # Before apply, inspect_recovery must classify untouched (never public_sync_partial).
        untouched = commit.inspect_recovery(self.fx.root, operation_id=op_rev3)
        self.assertEqual("untouched", untouched["physical_state"])
        self.assertEqual("apply", untouched["next_stage"])

        # Crash right after public_sync_applied_durable (before commit.json is written!).
        def crash_after_pub_sync(name: str) -> None:
            if name == "public_sync_applied_durable":
                raise RuntimeError("simulated crash after in-place public-sync before commit intent")

        with patch.object(ch4, "_checkpoint", side_effect=crash_after_pub_sync):
            with self.assertRaises(codec.CodecError):
                commit.execute(self.fx.root, operation_id=op_rev3, stage="apply")

        # Recovery must NOT wedge on DIGETS_MISMATCH / INPUT_STALE for in-place edited Contract/Overlay!
        rec_info = commit.inspect_recovery(self.fx.root, operation_id=op_rev3)
        self.assertEqual("public_sync_applied_pre_commit", rec_info["physical_state"])
        recovered = commit.recover(self.fx.root, operation_id=op_rev3)
        self.assertTrue(recovered["published"])
        self.assertEqual("complete", recovered["state"])

        # Shared Task 101's existing master overlay is preserved, while back overlay_refs & contractRefs are synced.
        live_master = self.fx.read_json(ch4.TRIPLET["master"])
        self.assertEqual(
            "docs/architecture/overlays/PRD-COMBAT/08/08-Combat.md",
            live_master["master"]["tasks"][0]["overlay"],
        )
        self.assertIn("SourceTag", (self.fx.root / "Game.Core/Contracts/Reward/SelectRewardCommand.cs").read_text(encoding="utf-8"))

        # Reject nonexistent add_overlay_refs path.
        bad_ov_req = self.fx.base_reuse_request("OP-BAD-OV-SYNC", assets, ui_applicable=True)
        bad_ov_req["commands"][0]["target_ref"] = _owned_ref(
            "contract", "Game.Core/Contracts/Reward/SelectRewardCommand.cs", [("Game.Core/Contracts/Reward/SelectRewardCommand.cs", updated_cmd_raw)]
        )
        bad_ov_req["obligations"][0]["verification_refs"] = []
        bad_ov_req["public_changes"] = {
            "triplet_ref_sync": [
                {
                    "task_id": 101,
                    "add_overlay_refs": ["docs/architecture/overlays/PRD-REWARD/08/08-Does-Not-Exist.md"],
                }
            ]
        }
        self.fx.put_json("logs/ci/requests/bad_ov_sync.json", bad_ov_req)
        with self.assertRaises(codec.CodecError) as ctx_ov:
            ch4.preview(self.fx.root, operation_id="OP-BAD-OV-SYNC", request_ref="logs/ci/requests/bad_ov_sync.json")
        self.assertEqual(codec.ReasonCode.UNRESOLVED_REFERENCE, ctx_ov.exception.diagnostic.reason_code)

    def test_p05_validate_operations_on_reuse_and_pub_sync_and_missing_public_sync_scope(self) -> None:
        # 1. 2-target (REUSE) Stage-4 op passes adoption.validate_operations.
        assets = self.fx.build_committed_bundle(ui_applicable=True, include_other_plan=True)
        op_reuse = "OP-VALOPS-REUSE"
        req_reuse = self.fx.base_reuse_request(op_reuse, assets, ui_applicable=True)
        self.fx.put_json(f"logs/ci/requests/{op_reuse}.json", req_reuse)
        ch4.prepare(self.fx.root, operation_id=op_reuse, request_ref=f"logs/ci/requests/{op_reuse}.json")
        inv_reuse = journal.operation_inventory(self.fx.root)
        self.assertEqual(2, len(inv_reuse[0]["frozen"]["targets"]))
        adoption.validate_operations(inv_reuse)

        # 2. 5-target (PUB_SYNC) Stage-4 op passes adoption.validate_operations, and stripping a public_sync file scope fails!
        fx2 = Chapter4RepoFixture()
        self.addCleanup(fx2.cleanup)
        assets2 = fx2.build_committed_bundle(ui_applicable=True, include_other_plan=True)
        orig_fx = self.fx
        self.fx = fx2
        try:
            op_pub = "OP-VALOPS-PUBSYNC"
            req_pub = self._make_pub_sync_request(op_pub, assets2)
            fx2.put_json(f"logs/ci/requests/{op_pub}.json", req_pub)
            ch4.prepare(fx2.root, operation_id=op_pub, request_ref=f"logs/ci/requests/{op_pub}.json")
        finally:
            self.fx = orig_fx
        inv_pub = journal.operation_inventory(fx2.root)
        self.assertEqual(5, len(inv_pub[0]["frozen"]["targets"]))
        adoption.validate_operations(inv_pub)

        # Strip one file: scope belonging to public_sync_entries -> must fail with PENDING!
        tampered = copy.deepcopy(inv_pub)
        pub_path = tampered[0]["frozen"]["refinement"]["public_sync_entries"][0]["path"]
        pub_scope = op_scope.resource_scopes(target_paths=[pub_path])[0]
        tampered[0]["frozen"]["scope_ids"] = [s for s in tampered[0]["frozen"]["scope_ids"] if s != pub_scope]
        with self.assertRaises(codec.CodecError) as ctx_strip:
            adoption.validate_operations(tampered)
        self.assertEqual(codec.ReasonCode.PENDING, ctx_strip.exception.diagnostic.reason_code)

    def test_p06_clean_clone_read_rejects_orphan_3c_tampered_unswallowed_event_and_dev_cli_main_e2e(self) -> None:
        assets = self.fx.build_committed_bundle(ui_applicable=True, include_other_plan=False)
        op_id = "OP-DEVCLI-E2E"
        req = self.fx.base_reuse_request(op_id, assets, ui_applicable=True)
        req_rel = f"logs/ci/requests/{op_id}.json"
        self.fx.put_json(req_rel, req)

        # End-to-end execution through dev_cli.main(["b-route-chapter4-binding", ...])!
        for stage, extra in (
            ("preview", ["--request", req_rel]),
            ("prepare", ["--request", req_rel]),
            ("reserve", []),
            ("inspect", []),
            ("apply", []),
            ("verify", []),
            ("publish", []),
            ("read", []),
        ):
            proc = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPTS_PY / "dev_cli.py"),
                    "b-route-chapter4-binding",
                    "--root",
                    str(self.fx.root),
                    "--stage",
                    stage,
                    "--operation-id",
                    op_id,
                    *extra,
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(0, proc.returncode, f"dev_cli stage={stage} failed: {proc.stdout}\n{proc.stderr}")

        def call_cli(root_dir: Path, argv: list[str]) -> tuple[int, dict]:
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = ch4_cli.main(["--root", str(root_dir), *argv])
            return rc, json.loads(buf.getvalue().strip())

        # Clean clone checks (zero logs/ directory):
        with tempfile.TemporaryDirectory() as clone_tmp:
            clone_root = Path(clone_tmp)
            for folder in ("docs", "Game.Core", "Game.Godot", ".taskmaster", "sources", "evidence"):
                if (self.fx.root / folder).exists():
                    shutil.copytree(self.fx.root / folder, clone_root / folder)
            self.assertFalse((clone_root / "logs").exists())

            # 1. Valid published Stage-4 receipt succeeds in clean clone.
            rc_ok, out_ok = call_cli(clone_root, ["--stage", "read", "--operation-id", op_id])
            self.assertEqual(0, rc_ok, out_ok)
            self.assertTrue(out_ok["formal_adoption"])
            self.assertEqual(1, len(out_ok["stage4_semantics"]))

            # 2. 3C-only receipt (OP-BOOTSTRAP-3C) rejected in clean clone!
            rc_3c, out_3c = call_cli(clone_root, ["--stage", "read", "--operation-id", "OP-BOOTSTRAP-3C"])
            self.assertEqual(2, rc_3c)
            self.assertEqual("blocked", out_3c["status"])

            # 3. Orphan receipt not referenced by catalog.scope_heads rejected in clean clone!
            orig_receipt = json.loads((clone_root / f"docs/planning/b-route/commits/{op_id}.json").read_text(encoding="utf-8"))
            orphan_receipt = copy.deepcopy(orig_receipt)
            orphan_receipt["operation_id"] = "OP-ORPHAN-CH4"
            (clone_root / "docs/planning/b-route/commits/OP-ORPHAN-CH4.json").write_bytes(_encoded(orphan_receipt))
            rc_orph, out_orph = call_cli(clone_root, ["--stage", "read", "--operation-id", "OP-ORPHAN-CH4"])
            self.assertEqual(2, rc_orph)
            self.assertEqual("unpublished", out_orph["diagnostics"][0]["reason_code"])

            # 4. Tampered binding bytes rejected in clean clone!
            b_file = clone_root / "docs/planning/b-route/bindings/plan-reward/2.json"
            b_file.write_bytes(b_file.read_bytes() + b"\n")
            rc_tamp, out_tamp = call_cli(clone_root, ["--stage", "read", "--operation-id", op_id])
            self.assertEqual(2, rc_tamp)
            self.assertEqual("blocked", out_tamp["status"])

        # Unswallowed OSError in append_event on mutating stage (publish noop) returns rc=2 blocked!
        with patch.object(ch4, "append_event", side_effect=OSError("disk full")):
            rc_os, out_os = call_cli(self.fx.root, ["--stage", "publish", "--operation-id", op_id])
        self.assertEqual(2, rc_os)
        self.assertEqual("blocked", out_os["status"])
        self.assertIn("OSError", str(out_os["diagnostics"][0]["actual"]))

    def test_p02_iterative_stage4_idempotency_3b_coverage_control_refs_and_3a_source_drift(self) -> None:
        assets = self.fx.build_committed_bundle(ui_applicable=True, include_other_plan=False)

        # 1. Missing 3B command coverage -> return_stage=4.
        req_no_cmd = self.fx.base_reuse_request("OP-NO-CMD", assets, ui_applicable=True)
        req_no_cmd["commands"] = []
        req_no_cmd["bindings"][0]["control_to_target"][0]["via_command"] = None
        self.fx.put_json("logs/ci/requests/no_cmd.json", req_no_cmd)
        with self.assertRaises(codec.CodecError) as ctx_cmd:
            ch4.preview(self.fx.root, operation_id="OP-NO-CMD", request_ref="logs/ci/requests/no_cmd.json")
        self.assertEqual("4", ch4.extract_mismatch_attribution(ctx_cmd.exception.diagnostic.to_dict())["return_stage"])

        # 2. Missing 3B state coverage -> return_stage=4.
        req_no_state = self.fx.base_reuse_request("OP-NO-STATE", assets, ui_applicable=True)
        req_no_state["read_only_states"] = []
        req_no_state["bindings"][0]["control_to_target"][0]["reads_state"] = None
        self.fx.put_json("logs/ci/requests/no_state.json", req_no_state)
        with self.assertRaises(codec.CodecError) as ctx_st:
            ch4.preview(self.fx.root, operation_id="OP-NO-STATE", request_ref="logs/ci/requests/no_state.json")
        self.assertEqual("4", ch4.extract_mismatch_attribution(ctx_st.exception.diagnostic.to_dict())["return_stage"])

        # 3. Invalid ControlBindingEntry.via_command -> return_stage=4.
        req_bad_via = self.fx.base_reuse_request("OP-BAD-VIA", assets, ui_applicable=True)
        req_bad_via["bindings"][0]["control_to_target"][0]["via_command"] = "CMD-NONEXISTENT"
        self.fx.put_json("logs/ci/requests/bad_via.json", req_bad_via)
        with self.assertRaises(codec.CodecError) as ctx_via:
            ch4.preview(self.fx.root, operation_id="OP-BAD-VIA", request_ref="logs/ci/requests/bad_via.json")
        self.assertEqual("4", ch4.extract_mismatch_attribution(ctx_via.exception.diagnostic.to_dict())["return_stage"])

        # 4. Iterative Stage-4 rev 2 -> rev 3 without duplicate stage4:ui:v1| tags!
        self._run_full_lifecycle("OP-ITER-REV2", self.fx.base_reuse_request("OP-ITER-REV2", assets, ui_applicable=True))
        req_rev3 = self.fx.base_reuse_request("OP-ITER-REV3", assets, ui_applicable=True)
        req_rev3["ui_slice"]["rationale"] = "Updated Stage-4 rev 3 UI rationale."
        self._run_full_lifecycle("OP-ITER-REV3", req_rev3)
        b3 = self.fx.read_json("docs/planning/b-route/bindings/plan-reward/3.json")
        self.assertEqual("4", b3["stage"])
        self.assertEqual(3, b3["binding_revision"])
        scene_part = next(p for p in b3["parts"] if p["kind"] == "scene")
        ui_tags = [r for r in scene_part["responsibilities"] if ch4.STAGE4_UI_PREFIX in r]
        self.assertEqual(1, len(ui_tags))
        sem3 = ch4.extract_stage4_semantics(self.fx.read_json("docs/planning/b-route/plans/plan-reward/1.json"), b3)
        self.assertEqual("Updated Stage-4 rev 3 UI rationale.", sem3["ui_slice"]["rationale"])

        # 5. 3A source-manifest.json referenced source file digest drift -> return_stage=3A.
        self.fx.put("sources/reward-gdd.md", "# Drifted Reward GDD\n")
        req_drift = self.fx.base_reuse_request("OP-SRC-DRIFT", assets, ui_applicable=True)
        self.fx.put_json("logs/ci/requests/src_drift.json", req_drift)
        with self.assertRaises(codec.CodecError) as ctx_3a:
            ch4.preview(self.fx.root, operation_id="OP-SRC-DRIFT", request_ref="logs/ci/requests/src_drift.json")
        self.assertEqual("3A", ch4.extract_mismatch_attribution(ctx_3a.exception.diagnostic.to_dict())["return_stage"])

    def test_p03_csharp_lexer_urls_primary_ctor_empty_dto_const_shell_and_strict_existing_asset_extensions(self) -> None:
        assets = self.fx.build_committed_bundle(ui_applicable=True, include_other_plan=False)

        # 1. Contract with "https://..." string literal and "/*" inside "//" comment MUST PASS!
        url_contract = (
            "using System;\n\n"
            "namespace Game.Core.Contracts.Reward;\n\n"
            "/// <summary>\n"
            "/// Contract containing URL string and tricky line comment.\n"
            "/// </summary>\n"
            "// Line comment with /* unclosed block comment token\n"
            "public sealed record RewardUrlCommand(string RunId)\n"
            "{\n"
            '    public string HelpUrl { get; init; } = "https://example.com/rewards/*ok*/";\n'
            "}\n"
        )
        ch4._validate_contract_source("Game.Core/Contracts/Reward/RewardUrlCommand.cs", url_contract, {})

        # 2. Primary-constructor empty DTOs & const-only non-static shell MUST BE REJECTED!
        empty_cases = [
            (
                "primary_record",
                "Game.Core/Contracts/Reward/EmptyDto.cs",
                "namespace Game.Core.Contracts.Reward;\n/// <summary>Empty.</summary>\npublic record EmptyDto();\n",
            ),
            (
                "primary_class",
                "Game.Core/Contracts/Reward/EmptyPrimaryClass.cs",
                "namespace Game.Core.Contracts.Reward;\n/// <summary>Empty.</summary>\npublic class EmptyPrimaryClass();\n",
            ),
            (
                "const_only_shell",
                "Game.Core/Contracts/Events/ConstOnlyShell.cs",
                "namespace Game.Core.Contracts.Events;\n/// <summary>Shell.</summary>\n/// <remarks>Const only.</remarks>\n"
                "public sealed class ConstOnlyShell { public const string EventType = EventTypes.RewardOffered; }\n",
            ),
        ]
        ev_map = {"RewardOffered": "core.reward.offered"}
        for label, rel_cs, code in empty_cases:
            with self.subTest(case=label):
                with self.assertRaises(codec.CodecError) as ctx_empty:
                    ch4._validate_contract_source(rel_cs, code, ev_map)
                self.assertEqual(codec.ReasonCode.SEMANTIC_ERROR, ctx_empty.exception.diagnostic.reason_code)
                self.assertEqual("empty_dto", ctx_empty.exception.diagnostic.actual.get("issue"))
                self.assertEqual("4", ch4.extract_mismatch_attribution(ctx_empty.exception.diagnostic.to_dict())["return_stage"])

        # 3. Non-.cs/.tscn/.tres/.res existing asset rejected with INVALID_REFERENCE (stage 4).
        txt_raw = self.fx.put("Game.Godot/Resources/Notes.txt", "plain text file\n")
        req_txt = self.fx.base_reuse_request("OP-BAD-EXT", assets, ui_applicable=True)
        req_txt["bindings"][0]["target_ref"] = _owned_ref(
            "implementation_reference", "Game.Godot/Resources/Notes.txt", [("Game.Godot/Resources/Notes.txt", txt_raw)]
        )
        self.fx.put_json("logs/ci/requests/bad_ext.json", req_txt)
        with self.assertRaises(codec.CodecError) as ctx_ext:
            ch4.preview(self.fx.root, operation_id="OP-BAD-EXT", request_ref="logs/ci/requests/bad_ext.json")
        self.assertEqual(codec.ReasonCode.INVALID_REFERENCE, ctx_ext.exception.diagnostic.reason_code)
        self.assertEqual("4", ch4.extract_mismatch_attribution(ctx_ext.exception.diagnostic.to_dict())["return_stage"])

        # 4. .tscn with only ';' commented node header rejected with SEMANTIC_ERROR (stage 4).
        commented_tscn = self.fx.put(
            "Game.Godot/Scenes/CommentedScene.tscn",
            '[gd_scene format=3]\n; [node name="RewardScene" type="Control"]\n',
        )
        with self.assertRaises(codec.CodecError) as ctx_tscn:
            ch4._verify_existing_asset_content(
                obj_id="SCENE-COMMENT",
                kind="scene",
                expected_type="Control",
                rel_path="Game.Godot/Scenes/CommentedScene.tscn",
                raw=commented_tscn,
                event_types_map=ev_map,
            )
        self.assertEqual(codec.ReasonCode.SEMANTIC_ERROR, ctx_tscn.exception.diagnostic.reason_code)


if __name__ == "__main__":
    unittest.main()
