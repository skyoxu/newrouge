"""Read-only B-route consumer alignment & pre-switch governance audit (Story 4.9).

Reconciles all ten consumer groups and every (path, symbol) entry from
``_b_route_inventory.GROUPS`` plus Epic 2-4 producers/consumers via real AST and file
verification (never text/summary claims), runs live five-state version contract and
anti-downgrade probes, validates AGENTS.md / entrypoint indexes / B-route owning docs /
governed Skills / ADR governance (including Proposed vs Accepted separation and dual
full-filename ADR-0038-*.md), verifies minimal versioned Git layout vs logs/** via
clean-clone simulation, checks Knowledge search exclusions via
``_knowledge_catalog_builder._excluded`` and zero duplicate codec/formal schema parsers,
and emits a reconstructable pre-switch coverage report.

Invariants:
- Strictly read-only (zero authority writes, zero workflow.md edits, zero implicit
  Knowledge refresh, zero second state machine).
- ``default_b_enabled`` is always ``False``; ``a_write_compatibility_retired`` is
  always ``False``; ``runtime_verified`` is always ``False``.
- ``--skip-live-probes`` fails closed (``ok=False``, ``epic4_alignment_ready=False``).
- Epic 5 pilot, Windows Godot dual-path Reward evidence, default-B switch, and A exit
  remain explicitly open in ``epic5_remaining_gates``.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import _b_route_chapter6_gate as ch6_gate
import _b_route_codec as codec
import _b_route_inventory as inventory
import _b_route_knowledge_projection as projection
import _b_route_observability as observability
import _b_route_records as records
import _b_route_schema_resources as schema_resources
import _b_route_task_resolver as task_resolver
import _b_route_verification_scope as verification_scope
import _knowledge_catalog_builder as knowledge_catalog_builder
import chapter3_task_scope


SCHEMA_VERSION = "newrouge.b-route-consumer-alignment.v1"

EPIC5_REMAINING_GATES: tuple[str, ...] = (
    "reward_gap_and_no_task_3b_adoption",
    "reward_incremental_3c_and_production_csharp_adapter",
    "reward_windows_godot_dual_path_runtime_evidence",
    "governed_default_b_switch_for_new_work",
    "independent_a_exit_gate_and_revocation",
)

INVARIANTS: dict[str, bool] = {
    "read_only": True,
    "default_b_enabled": False,
    "a_write_compatibility_retired": False,
    "second_state_machine_created": False,
    "summary_only_claim_rejected": True,
    "workflow_md_mutated": False,
    "implicit_global_refresh_performed": False,
    "runtime_verified": False,
}

# ADRs whose docs/adr/ADR-*.md bodies are Proposed (never Accepted).
BODY_PROPOSED_ADRS: tuple[str, ...] = (
    "ADR-0016",
    "ADR-0017",
    "ADR-0036",
    "ADR-0037",
    "ADR-0043",
    "ADR-0044",
    "ADR-0045",
    "ADR-0046",
    "ADR-0047",
    "ADR-0048",
    "ADR-0053",
)

# All ADRs listed as Proposed in ADR_INDEX_GODOT.md (plus BODY_PROPOSED_ADRS).
PROPOSED_ADRS: tuple[str, ...] = (
    "ADR-0016",
    "ADR-0017",
    "ADR-0021",
    "ADR-0022",
    "ADR-0031",
    "ADR-0036",
    "ADR-0037",
    "ADR-0043",
    "ADR-0044",
    "ADR-0045",
    "ADR-0046",
    "ADR-0047",
    "ADR-0048",
    "ADR-0053",
)

DUAL_ADR_0038_FILES: tuple[str, ...] = (
    "docs/adr/ADR-0038-semantic-delivery-topology.md",
    "docs/adr/ADR-0038-mvg-candidate-admission.md",
)

GOVERNED_SKILLS: tuple[str, ...] = (
    ".agents/skills/workflow-chapter3-task-triplet-baseline/SKILL.md",
    ".agents/skills/workflow-chapter4-overlays-contracts-baseline/SKILL.md",
    ".agents/skills/workflow-chapter5-semantics-stabilization/SKILL.md",
    ".agents/skills/workflow-chapter6-single-task-daily-loop/SKILL.md",
    ".agents/skills/workflow-chapter7-ui-wiring-closure/SKILL.md",
    ".agents/skills/plan-capabilities/SKILL.md",
    ".agents/skills/plan-mvg/SKILL.md",
    ".agents/skills/maintain-knowledge-base/SKILL.md",
)

# Per-Skill mandatory governance tokens: every single governed Skill must individually
# declare its B-route entrypoint, the A-default-until-Epic-5 rule, and relevant boundaries.
PER_SKILL_REQUIRED_TOKENS: dict[str, tuple[str, ...]] = {
    ".agents/skills/workflow-chapter3-task-triplet-baseline/SKILL.md": (
        "b-route-sources",
        "b-route-task-compile",
        "Epic 5",
        "journal",
        "workspace_preview",
        "ADR-0038-semantic-delivery-topology.md",
        "ADR-0038-mvg-candidate-admission.md",
    ),
    ".agents/skills/workflow-chapter4-overlays-contracts-baseline/SKILL.md": (
        "b-route-task-origin",
        "b-route-chapter4-binding",
        "Epic 5",
        "journal",
        "workspace_preview",
        "full-MVG",
        "ADR-0038-semantic-delivery-topology.md",
        "ADR-0038-mvg-candidate-admission.md",
    ),
    ".agents/skills/workflow-chapter5-semantics-stabilization/SKILL.md": (
        "b-route-input-set",
        "b-route-stage5-obligations",
        "b-route-chapter5-readiness",
        "Epic 5",
        "journal",
        "workspace_preview",
        "full-MVG",
    ),
    ".agents/skills/workflow-chapter6-single-task-daily-loop/SKILL.md": (
        "b-route-chapter6-gate",
        "b-route-defect-routing",
        "b-route-completion-verdict",
        "Epic 5",
        "journal",
        "workspace_preview",
        "full-MVG",
    ),
    ".agents/skills/workflow-chapter7-ui-wiring-closure/SKILL.md": (
        "b-route-chapter7-slice",
        "b-route-chapter6-gate",
        "b-route-completion-verdict",
        "Epic 5",
        "journal",
        "workspace_preview",
        "full-MVG",
    ),
    ".agents/skills/plan-capabilities/SKILL.md": (
        "--input-stage 3b",
        "b-route-adoption",
        "Epic 5",
        "apply-journal.json",
        "workspace_preview",
        "full-MVG",
    ),
    ".agents/skills/plan-mvg/SKILL.md": (
        "--input-stage 3b",
        "b-route-adoption",
        "Epic 5",
        "apply-journal.json",
        "workspace_preview",
        "full-MVG",
    ),
    ".agents/skills/maintain-knowledge-base/SKILL.md": (
        "b-route-knowledge-projection",
        "b-route-planning-page",
        "b-route-observability",
        "b-route-consumer-alignment",
        "Epic 5",
        "workspace_preview",
        "current.json",
        "last-known-good.json",
        "refs/heads/main",
    ),
}

REQUIRED_WORKFLOW_PROTECTIONS: tuple[str, ...] = (
    ".github/workflows/b-route-runtime-deterministic.yml",
    ".github/workflows/windows-quality-gate.yml",
    ".github/workflows/ci-windows.yml",
    ".github/workflows/publish-knowledge-catalog.yml",
)

MIGRATION_DOC_PATH = "docs/workflows/b-route-consumer-alignment.md"
MIGRATION_REQUIRED_SECTIONS: tuple[str, ...] = (
    "input_contract",
    "output_contract",
    "identity_preservation",
    "recovery_procedure",
)

# Expanded producer/operational directories forbidden for --report output.
ALIGNMENT_RESERVED_REPORT_PREFIXES: tuple[str, ...] = (
    *observability.RESERVED_PRODUCER_PREFIXES,
    "logs/ci/chapter5",
    "logs/ci/task-generation",
    "logs/ci/active-tasks",
    "logs/ci/active-prototypes",
    "logs/ci/b-route-locks",
    "logs/ci/b-route-baseline-inventory",
)

_ALIGNMENT_DATED_RESERVED_NAMES: frozenset[str] = frozenset({
    "b-route-sources",
    "b-route-source-audit",
    "b-route-task-compilation",
    "b-route-operations",
    "b-route-planning-input",
    "b-route-task-preview",
    "b-route-chapter4-binding",
    "b-route-stage5-obligations",
    "b-route-chapter5-readiness",
    "b-route-defect-routing",
    "b-route-chapter7-slice",
    "b-route-reopen",
    "b-route-locks",
    "b-route-baseline-inventory",
    "chapter5",
    "task-generation",
    "active-tasks",
    "active-prototypes",
    "capability-planning",
    "mvg-planning",
    "capability-recovery",
    "mvg-recovery",
    "mvg-acceptance",
    "project-health-knowledge",
    "knowledge-planning",
})

_DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Explicit legacy/compatibility allowlist for json.loads in pre-existing B-route modules
# (reading non-formal legacy logs, NDJSON lines, CLI stdout, or Story 2.5 AST-locked files).
# Any NEW *b_route*.py introducing private json.loads outside _b_route_codec.py is blocked.
LEGACY_JSON_LOADS_ALLOWLIST: frozenset[str] = frozenset({
    "_b_route_codec.py",
    "_b_route_inventory.py",
    "_b_route_3b_segmented_input.py",
    "_b_route_chapter5_readiness.py",
    "_b_route_chapter6_gate.py",
    "_b_route_chapter6_recovery.py",
    "_b_route_chapter7_slice.py",
    "_b_route_compact_literal.py",
    "_b_route_compensation_review_materials.py",
    "_b_route_defect_routing.py",
    "_b_route_entrypoint_parity.py",
    "_b_route_evidence_reuse.py",
    "_b_route_execution_transition.py",
    "_b_route_frozen_native_reader.py",
    "_b_route_partial_generation_recovery.py",
    "_b_route_planning_page.py",
    "_b_route_planning_runtime.py",
    "_b_route_qualified_compensation_materials.py",
    "_b_route_qualified_compensation_materials_v2.py",
    "_b_route_qualified_history_host.py",
    "_b_route_qualified_history_host_v3.py",
    "_b_route_recovery_funding.py",
    "_b_route_segmented_fiscal_prefix.py",
    "_b_route_segmented_requests.py",
    "_b_route_segmented_runtime.py",
    "_b_route_synthesis_recovery.py",
    "b_route_worker_recovery.py",
    "capture_b_route_protection.py",
    "inventory_b_route_baseline.py",
    "preflight_b_route_migration.py",
})

PUBLIC_CONTRACT_MODULES: frozenset[str] = frozenset({
    "_b_route_codec",
    "_b_route_records",
    "_b_route_schema_resources",
    "_b_route_task_resolver",
    "_b_route_task_preview",
    "_b_route_task_compilation",
    "_b_route_input_set",
    "_b_route_commit",
    "_b_route_commit_projection",
    "_b_route_chapter4_binding",
    "_b_route_stage5_obligations",
    "_b_route_chapter5_readiness",
    "_b_route_chapter6_gate",
    "_b_route_chapter6_recovery",
    "_b_route_defect_routing",
    "_b_route_chapter7_slice",
    "_b_route_entrypoint_parity",
    "_b_route_impact_closure",
    "_b_route_verification_scope",
    "_b_route_scope_runner",
    "_b_route_evidence_reuse",
    "_b_route_completion_verdict",
    "_b_route_knowledge_projection",
    "_b_route_planning_page",
    "_b_route_observability",
    "_b_route_consumer_alignment",
    "_b_route_inventory",
    "_b_route_protection",
    "_b_route_preflight",
    "_b_route_operation_scope",
    "_b_route_planning_runtime",
    "_b_route_sources",
    "_b_route_source_audit",
    "_b_route_adoption",
    "_b_route_completed_reuse",
    "_mvg_manifest",
    "_mvg_obligations",
    "_mvg_capability_worker",
    "_mvg_capability_checkpoint",
    "_mvg_capability_recovery",
    "_mvg_execution",
    "_planning_apply_journal",
})

# Narrowed to true multi-plan / shared-Task resolution & aggregation tokens only.
_SHARED_TASK_TOKENS: frozenset[str] = frozenset({
    "resolve_task_origin",
    "applicable_plans",
    "applicable_set_digest",
    "applicable_plan_ids",
    "resolve_input_set",
    "compute_input_set_digest",
    "guarded_input_set",
    "evaluate_chapter6_gate",
    "guarded_chapter6_execution",
    "enforce_internal_script_gate",
    "compute_impact_closure",
    "build_verification_scope",
    "validate_verification_scope",
    "run_scoped_mvg",
    "evaluate_test_evidence_reuse",
    "evaluate_completion_verdict",
    "build_b_route_knowledge_projection",
    "execute_planning_page_action",
    "build_b_route_observability_report",
    "handle_page_b_route_trigger",
    "task_mappings",
    "shared_task",
    "multi_plan",
})

# Concrete item-by-item consumer registry covering EVERY (path, symbol) entry across all
# 10 groups in _b_route_inventory.GROUPS plus all Epic 2-4 producers, direct scripts,
# query CLIs, HTTP/UI handlers, and governance docs (>= 60 concrete entries).
CONSUMER_REGISTRY: tuple[dict[str, Any], ...] = (
    # ======================== Group 1: source-ledger-audit ========================
    {
        "consumer_id": "source_ledger_direct_builder",
        "group": "source-ledger-audit",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/build_source_ledger.py",
        "symbol": "resolve_sources",
        "actual_read_paths": ("docs/workflows/chapter3-source-set.json", "docs/prd/**", "docs/gdd/**"),
        "actual_write_paths": ("logs/ci/task-generation/source-blocks.v1.json",),
        "required_contract_modules": (),
        "required_call_tokens": ("resolve_sources", "SUPPORTED_SUFFIXES"),
        "shared_task_expected": False,
        "valid_input_contract": "Explicit source patterns without logs/** traversal.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_inventory.py", "test_valid_baseline_preserves_original_inventory_and_distinguishes_git_history"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_inventory.py", "test_exact_status_differences_and_equal_states_excluded"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work",),
    },
    {
        "consumer_id": "project_semantics_prepare_direct",
        "group": "source-ledger-audit",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/project_semantics_from_sources.py",
        "symbol": "prepare",
        "actual_read_paths": ("logs/ci/task-generation/source-blocks.v1.json", "docs/prd/**", "docs/gdd/**"),
        "actual_write_paths": ("logs/ci/task-generation/**",),
        "required_contract_modules": (),
        "required_call_tokens": ("prepare",),
        "shared_task_expected": False,
        "valid_input_contract": "Deterministic bounded batching over complete Source Block Ledger (legacy A lane).",
        "pass_evidence_refs": (("scripts/python/tests/test_chapter3_semantic_conservation.py", "test_copy_planning_artifacts_hashes_canonical_lf_bytes"),),
        "fail_evidence_refs": (("scripts/python/tests/test_chapter3_semantic_conservation.py", "test_triplet_attestation_binds_current_task_file_hashes"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work",),
    },
    {
        "consumer_id": "project_semantics_compile_direct",
        "group": "source-ledger-audit",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/project_semantics_from_sources.py",
        "symbol": "compile_projection",
        "actual_read_paths": ("logs/ci/task-generation/**",),
        "actual_write_paths": ("logs/ci/task-generation/semantic-requirements.v1.json",),
        "required_contract_modules": (),
        "required_call_tokens": ("compile_projection",),
        "shared_task_expected": False,
        "valid_input_contract": "Compiles reviewed Source Block batch projections with lossless block accounting.",
        "pass_evidence_refs": (("scripts/python/tests/test_chapter3_semantic_conservation.py", "test_copy_planning_artifacts_hashes_canonical_lf_bytes"),),
        "fail_evidence_refs": (("scripts/python/tests/test_chapter3_semantic_conservation.py", "test_triplet_attestation_binds_current_task_file_hashes"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work",),
    },
    {
        "consumer_id": "validate_semantic_conservation_direct",
        "group": "source-ledger-audit",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/validate_semantic_conservation.py",
        "symbol": "validate",
        "actual_read_paths": ("logs/ci/task-generation/**", ".taskmaster/tasks/*.json"),
        "actual_write_paths": ("logs/ci/task-generation/**",),
        "required_contract_modules": (),
        "required_call_tokens": ("validate",),
        "shared_task_expected": False,
        "valid_input_contract": "Verifies complete Source Block accounting and Requirement sink conservation.",
        "pass_evidence_refs": (("scripts/python/tests/test_chapter3_semantic_conservation.py", "test_copy_planning_artifacts_hashes_canonical_lf_bytes"),),
        "fail_evidence_refs": (("scripts/python/tests/test_chapter3_semantic_conservation.py", "test_triplet_attestation_binds_current_task_file_hashes"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work",),
    },
    {
        "consumer_id": "audit_task_candidate_coverage_direct",
        "group": "source-ledger-audit",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/audit_task_candidate_coverage.py",
        "symbol": "audit",
        "actual_read_paths": ("logs/ci/task-generation/**", ".taskmaster/tasks/*.json"),
        "actual_write_paths": ("logs/ci/task-generation/coverage-report.json",),
        "required_contract_modules": (),
        "required_call_tokens": ("audit",),
        "shared_task_expected": False,
        "valid_input_contract": "Audits active delivery Requirement sink coverage against task candidates.",
        "pass_evidence_refs": (("scripts/python/tests/test_chapter3_task_generation.py", "test_requirement_extraction_should_skip_reference_only_blocks"),),
        "fail_evidence_refs": (("scripts/python/tests/test_chapter3_task_generation.py", "test_task_intents_should_split_large_source_groups_by_topic_and_size"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work",),
    },
    {
        "consumer_id": "source_3a_accounting",
        "group": "source-ledger-audit",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_b_route_sources.py",
        "symbol": "prepare",
        "actual_read_paths": ("docs/workflows/chapter3-source-set.json", "docs/prd/**", "docs/gdd/**"),
        "actual_write_paths": ("logs/ci/b-route-sources/**",),
        "required_contract_modules": ("_b_route_codec", "_b_route_inventory"),
        "required_call_tokens": ("prepare", "load_prepared"),
        "shared_task_expected": False,
        "valid_input_contract": "Versioned chapter3-source-set.json + authoritative PRD/GDD files; zero Task invention.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_source_audit.py", "test_complete_zero_task_os_lifecycle_verify_and_exact_replay"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_audit_recovery.py", "test_semantic_environment_domain_low_and_unreviewed_code_changes_block"),),
        "remaining_epic5_items": ("reward_gap_and_no_task_3b_adoption",),
    },
    {
        "consumer_id": "source_3a_independent_audit",
        "group": "source-ledger-audit",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_b_route_source_audit.py",
        "symbol": "request_record",
        "actual_read_paths": ("logs/ci/b-route-sources/**", "docs/workflows/chapter3-source-set.json"),
        "actual_write_paths": ("logs/ci/b-route-source-audit/**",),
        "required_contract_modules": ("_b_route_codec",),
        "required_call_tokens": ("request_record", "producer_input"),
        "shared_task_expected": False,
        "valid_input_contract": "Hash-bound 3A prepared/accounted source bundle; independent two-step audit without Task creation.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_source_audit.py", "test_complete_zero_task_os_lifecycle_verify_and_exact_replay"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_review_source_policy.py", "test_per_obligation_nonempty_subset_passes_without_requiring_all_allowed_sources"),),
        "remaining_epic5_items": ("reward_gap_and_no_task_3b_adoption",),
    },
    {
        "consumer_id": "source_3a_cli",
        "group": "source-ledger-audit",
        "entrypoint_kind": "public_cli",
        "module_path": "scripts/python/account_b_route_sources.py",
        "symbol": "main",
        "actual_read_paths": ("docs/workflows/chapter3-source-set.json",),
        "actual_write_paths": ("logs/ci/b-route-sources/**", "logs/ci/b-route-source-audit/**"),
        "required_contract_modules": ("_b_route_sources",),
        "required_call_tokens": ("main",),
        "shared_task_expected": False,
        "valid_input_contract": "dev_cli.py b-route-sources --stage prepare|account|audit|verify.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_source_audit.py", "test_complete_zero_task_os_lifecycle_verify_and_exact_replay"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_audit_partial_reuse.py", "test_partial_original_reuse_new_comparison_native_verify_and_tamper_rejection"),),
        "remaining_epic5_items": ("reward_gap_and_no_task_3b_adoption",),
    },
    {
        "consumer_id": "b_route_preflight_cli",
        "group": "source-ledger-audit",
        "entrypoint_kind": "public_cli",
        "module_path": "scripts/python/preflight_b_route_migration.py",
        "symbol": "main",
        "actual_read_paths": ("docs/workflows/chapter3-source-set.json", "docs/planning/b-route/**"),
        "actual_write_paths": ("logs/ci/**",),
        "required_contract_modules": ("_b_route_preflight",),
        "required_call_tokens": ("main",),
        "shared_task_expected": False,
        "valid_input_contract": "Read-only migration preflight preview; zero apply/Task writes.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_preflight.py", "test_success_exact_changes_identities_semantic_limits_and_no_writes"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_preflight.py", "test_repeated_preview_has_same_identity_and_no_candidate_generation"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work",),
    },
    # ======================== Group 2: capability-mvg ========================
    {
        "consumer_id": "plan_capabilities_direct",
        "group": "capability-mvg",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/plan_capabilities.py",
        "symbol": "prepare",
        "actual_read_paths": ("docs/workflows/chapter3-source-set.json", "logs/ci/b-route-sources/**"),
        "actual_write_paths": ("logs/ci/capability-planning/**",),
        "required_contract_modules": ("_b_route_operation_scope", "_b_route_planning_runtime"),
        "required_call_tokens": ("prepare", "scope_guard", "cli_stage", "--input-stage"),
        "shared_task_expected": False,
        "valid_input_contract": "Explicit --input-stage 3b for task-free B-route or Chapter 5 ready scope for legacy A.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_planning_input.py", "test_zero_task_complete_bytes_unknown_fields_and_read_only_reuse"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_planning_page.py", "test_3b_requires_accepted_3a_evidence_and_blocks_without_delegation"),),
        "remaining_epic5_items": ("reward_gap_and_no_task_3b_adoption", "governed_default_b_switch_for_new_work"),
    },
    {
        "consumer_id": "plan_mvg_direct",
        "group": "capability-mvg",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/plan_mvg.py",
        "symbol": "prepare",
        "actual_read_paths": ("docs/planning/semantic-topology/capabilities.v1.json", "docs/testing/mvg/*.json"),
        "actual_write_paths": ("logs/ci/mvg-planning/**", "docs/testing/mvg/*.json"),
        "required_contract_modules": ("_mvg_manifest", "_b_route_operation_scope", "_b_route_planning_runtime"),
        "required_call_tokens": ("prepare", "scope_guard", "cli_stage", "--input-stage"),
        "shared_task_expected": False,
        "valid_input_contract": "Explicit capability version + manifest or --input-stage 3b task-free flow graph.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_candidate.py", "test_complete_planned_reentry_scc_and_optional_unreachable_node"),),
        "fail_evidence_refs": (("scripts/python/tests/test_mvg_global_audit_boundaries.py", "test_source_citations_preserve_original_line_endings_and_bom"),),
        "remaining_epic5_items": ("reward_gap_and_no_task_3b_adoption", "governed_default_b_switch_for_new_work"),
    },
    {
        "consumer_id": "b_route_adoption_cli",
        "group": "capability-mvg",
        "entrypoint_kind": "public_cli",
        "module_path": "scripts/python/b_route_adoption.py",
        "symbol": "main",
        "actual_read_paths": ("docs/planning/b-route/**", "logs/ci/b-route-operations/**"),
        "actual_write_paths": ("docs/planning/b-route/**", "logs/ci/b-route-operations/**"),
        "required_contract_modules": ("_b_route_codec", "_b_route_adoption"),
        "required_call_tokens": ("main", "register_arguments"),
        "shared_task_expected": False,
        "valid_input_contract": "Reviewed 3B adoption operation; catalog.v1.json published last.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_adoption_cli.py", "test_non_object_review_subject_is_blocked_through_both_public_entries"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_adoption_journal.py", "test_same_id_changed_complete_request_and_unsafe_freeze_reject_before_write"),),
        "remaining_epic5_items": ("reward_gap_and_no_task_3b_adoption",),
    },
    {
        "consumer_id": "b_route_commit_service",
        "group": "capability-mvg",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_b_route_commit.py",
        "symbol": "read_operation_context",
        "actual_read_paths": ("docs/planning/b-route/**", "logs/ci/b-route-operations/**"),
        "actual_write_paths": ("docs/planning/b-route/**",),
        "required_contract_modules": ("_b_route_codec", "_b_route_records"),
        "required_call_tokens": ("read_operation_context",),
        "shared_task_expected": False,
        "valid_input_contract": "Sealed commit intent + journal recovery preserving post-edits; catalog.v1.json last.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_commit.py", "test_raw_commit_write_uses_the_existing_atomic_path_capacity"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_commit_recovery.py", "test_prepared_unreserved_operation_reports_reserve_and_blocks_recover"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work",),
    },
    # ======================== Group 3: worker-checkpoint-recovery ========================
    {
        "consumer_id": "mvg_capability_worker",
        "group": "worker-checkpoint-recovery",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_mvg_capability_worker.py",
        "symbol": "run_candidate",
        "actual_read_paths": ("logs/ci/mvg-planning/**",),
        "actual_write_paths": ("logs/ci/mvg-planning/**/candidates/**",),
        "required_contract_modules": (),
        "required_call_tokens": ("run_candidate",),
        "shared_task_expected": False,
        "valid_input_contract": "Isolated OS subprocess candidate worker bounded by coordinator reservation budget.",
        "pass_evidence_refs": (("scripts/python/tests/test_mvg_capability_worker.py", "test_real_workers_commit_and_new_run_reuses_without_model_dispatch"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_worker_recovery.py", "test_unknown_missing_completion_is_blocked_and_byte_preserved"),),
        "remaining_epic5_items": ("reward_gap_and_no_task_3b_adoption",),
    },
    {
        "consumer_id": "mvg_capability_checkpoint",
        "group": "worker-checkpoint-recovery",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_mvg_capability_checkpoint.py",
        "symbol": "commit_checkpoint",
        "actual_read_paths": ("logs/ci/mvg-planning/**",),
        "actual_write_paths": ("logs/ci/mvg-planning/**/run.json",),
        "required_contract_modules": (),
        "required_call_tokens": ("commit_checkpoint", "coordinator_lock"),
        "shared_task_expected": False,
        "valid_input_contract": "Atomic run.json pointer commit after canonical checkpoint bundle verification.",
        "pass_evidence_refs": (("scripts/python/tests/test_mvg_capability_recovery.py", "test_full_individual_content_key_preserves_types_values_and_array_order"),),
        "fail_evidence_refs": (("scripts/python/tests/test_mvg_recovery_fixthrough.py", "test_existing_apply_journal_holds_activity_lock_through_all_writes"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "mvg_capability_recovery",
        "group": "worker-checkpoint-recovery",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_mvg_capability_recovery.py",
        "symbol": "try_adopt",
        "actual_read_paths": ("logs/ci/mvg-planning/**", "logs/ci/mvg-recovery/**"),
        "actual_write_paths": ("logs/ci/mvg-recovery/**",),
        "required_contract_modules": ("_b_route_completed_reuse",),
        "required_call_tokens": ("try_adopt",),
        "shared_task_expected": False,
        "valid_input_contract": "Completed-checkpoint cross-run adoption obeying Story 2.9 epoch and reopen revocations.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_completed_reuse.py", "test_original_archived_generation_is_used_after_pending_clears_selected"),),
        "fail_evidence_refs": (("scripts/python/tests/test_mvg_capability_recovery.py", "test_epoch_clear_survives_restart_and_rejects_late_publication"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "b_route_completed_reuse",
        "group": "worker-checkpoint-recovery",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_b_route_completed_reuse.py",
        "symbol": "replay_delta",
        "actual_read_paths": ("logs/ci/mvg-planning/**",),
        "actual_write_paths": (),
        "required_contract_modules": (),
        "required_call_tokens": ("replay_delta", "dependency"),
        "shared_task_expected": False,
        "valid_input_contract": "Deterministic canonical dependency and delta verification before Story 2.9 adoption.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_completed_reuse.py", "test_original_archived_generation_is_used_after_pending_clears_selected"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_completed_reuse.py", "test_historical_mode_and_given_state_reach_original_receipt_verifier"),),
        "remaining_epic5_items": (),
    },
    # ======================== Group 4: business-triplet ========================
    {
        "consumer_id": "normalize_task_intents_direct",
        "group": "business-triplet",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/normalize_task_intents.py",
        "symbol": "main",
        "actual_read_paths": ("logs/ci/task-generation/**", ".taskmaster/tasks/*.json"),
        "actual_write_paths": ("logs/ci/task-generation/task-intents.v1.json",),
        "required_contract_modules": (),
        "required_call_tokens": ("main",),
        "shared_task_expected": False,
        "valid_input_contract": "Normalizes coarse legacy Chapter 3 task intents preserving stable intent_key.",
        "pass_evidence_refs": (("scripts/python/tests/test_chapter3_task_generation.py", "test_task_intents_should_split_large_source_groups_by_topic_and_size"),),
        "fail_evidence_refs": (("scripts/python/tests/test_chapter3_task_generation.py", "test_requirement_extraction_should_skip_reference_only_blocks"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work",),
    },
    {
        "consumer_id": "compile_task_triplet_direct",
        "group": "business-triplet",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/compile_task_triplet.py",
        "symbol": "main",
        "actual_read_paths": ("logs/ci/task-generation/**", ".taskmaster/tasks/*.json", "docs/planning/b-route/**"),
        "actual_write_paths": (".taskmaster/tasks/tasks_back.json", ".taskmaster/tasks/tasks_gameplay.json"),
        "required_contract_modules": (),
        "required_call_tokens": ("main", "_guard_active_b_route_direct_write"),
        "shared_task_expected": False,
        "valid_input_contract": "Legacy direct triplet writer gated fail-closed whenever active B-route governance is present.",
        "pass_evidence_refs": (("scripts/python/tests/test_chapter3_closeout_routes.py", "test_real_incremental_compile_export_preserves_existing_task"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_consumer_alignment.py", "test_p02_direct_writers_block_under_active_b_route_and_allow_pure_legacy"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work", "independent_a_exit_gate_and_revocation"),
    },
    {
        "consumer_id": "build_taskmaster_tasks_direct",
        "group": "business-triplet",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/build_taskmaster_tasks.py",
        "symbol": "main",
        "actual_read_paths": (".taskmaster/tasks/tasks_back.json", ".taskmaster/tasks/tasks_gameplay.json", "docs/planning/b-route/**"),
        "actual_write_paths": (".taskmaster/tasks/tasks.json",),
        "required_contract_modules": (),
        "required_call_tokens": ("main", "_guard_active_b_route_direct_write"),
        "shared_task_expected": False,
        "valid_input_contract": "Legacy tasks.json exporter gated fail-closed whenever active B-route governance is present.",
        "pass_evidence_refs": (("scripts/python/tests/test_chapter3_closeout_routes.py", "test_real_incremental_compile_export_preserves_existing_task"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_consumer_alignment.py", "test_p02_direct_writers_block_under_active_b_route_and_allow_pure_legacy"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work", "independent_a_exit_gate_and_revocation"),
    },
    {
        "consumer_id": "audit_task_triplet_delivery_direct",
        "group": "business-triplet",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/audit_task_triplet_delivery.py",
        "symbol": "find_view_task",
        "actual_read_paths": (".taskmaster/tasks/*.json",),
        "actual_write_paths": (),
        "required_contract_modules": (),
        "required_call_tokens": ("find_view_task",),
        "shared_task_expected": False,
        "valid_input_contract": "Read-only triplet delivery audit matching master task IDs to back/gameplay views.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_inventory.py", "test_valid_baseline_preserves_original_inventory_and_distinguishes_git_history"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_inventory.py", "test_exact_status_differences_and_equal_states_excluded"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "triplet_validator_direct",
        "group": "business-triplet",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/validate_task_master_triplet.py",
        "symbol": "validate_taskmaster_mapping",
        "actual_read_paths": (".taskmaster/tasks/tasks.json", ".taskmaster/tasks/tasks_back.json", ".taskmaster/tasks/tasks_gameplay.json"),
        "actual_write_paths": (),
        "required_contract_modules": (),
        "required_call_tokens": ("validate_taskmaster_mapping",),
        "shared_task_expected": False,
        "valid_input_contract": "Strict master id <-> business view taskmaster_id join validation.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_task_compilation.py", "test_happy_nine_stage_lifecycle_catalog_last_and_direct_edit_blocked"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_task_resolver.py", "test_b_multi_blocks_missing_origin_row_tampered_policy_and_stripped_b_ownership"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "b_route_task_preview_cli",
        "group": "business-triplet",
        "entrypoint_kind": "public_cli",
        "module_path": "scripts/python/preview_b_route_task_changes.py",
        "symbol": "main",
        "actual_read_paths": ("docs/planning/b-route/**", ".taskmaster/tasks/*.json"),
        "actual_write_paths": ("logs/ci/b-route-task-preview/**",),
        "required_contract_modules": ("_b_route_codec", "_b_route_task_preview"),
        "required_call_tokens": ("main",),
        "shared_task_expected": False,
        "valid_input_contract": "Adopted 3B plan -> read-only reuse/gap preview without mutating triplet or allocating IDs.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_task_preview.py", "test_happy_gap_creation_dual_outputs_and_no_permanent_ids"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_task_preview.py", "test_zero_gap_100_percent_reuse_emits_pure_reuse_and_direct_schema_valid_binding"),),
        "remaining_epic5_items": ("reward_incremental_3c_and_production_csharp_adapter",),
    },
    {
        "consumer_id": "b_route_task_compile_cli",
        "group": "business-triplet",
        "entrypoint_kind": "public_cli",
        "module_path": "scripts/python/compile_b_route_tasks.py",
        "symbol": "main",
        "actual_read_paths": ("docs/planning/b-route/**", ".taskmaster/tasks/*.json"),
        "actual_write_paths": (".taskmaster/tasks/*.json", "docs/planning/b-route/**"),
        "required_contract_modules": ("_b_route_codec", "_b_route_task_compilation"),
        "required_call_tokens": ("main",),
        "shared_task_expected": False,
        "valid_input_contract": "Reviewed 3.1 preview delta -> governed triplet + Stage 3C binding preserving live Task status.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_task_compilation.py", "test_happy_nine_stage_lifecycle_catalog_last_and_direct_edit_blocked"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_task_compilation.py", "test_schema_registration_keeps_formal_untouched_and_registers_auxiliary"),),
        "remaining_epic5_items": ("reward_incremental_3c_and_production_csharp_adapter",),
    },
    {
        "consumer_id": "b_route_task_origin_resolver",
        "group": "business-triplet",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_b_route_task_resolver.py",
        "symbol": "resolve_task_origin",
        "actual_read_paths": ("docs/planning/b-route/**", ".taskmaster/tasks/*.json", "docs/adr/ADR-0040-b-route-stages-authority-and-activation.md"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_codec", "_b_route_records", "_b_route_inventory"),
        "required_call_tokens": ("resolve_task_origin", "applicable_set_digest"),
        "shared_task_expected": True,
        "valid_input_contract": "Zero-write Task classification into B / bounded frozen A / explicit_not_enabled_a / blocked with multi-plan union.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_task_resolver.py", "test_b_multi_single_and_multi_plan_changes_applicable_set_digest"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_task_resolver.py", "test_b_multi_blocks_missing_origin_row_tampered_policy_and_stripped_b_ownership"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work", "independent_a_exit_gate_and_revocation"),
    },
    {
        "consumer_id": "b_route_task_origin_cli",
        "group": "business-triplet",
        "entrypoint_kind": "public_cli",
        "module_path": "scripts/python/resolve_b_route_task_origin.py",
        "symbol": "main",
        "actual_read_paths": ("docs/planning/b-route/**", ".taskmaster/tasks/*.json"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_codec", "_b_route_task_resolver"),
        "required_call_tokens": ("main", "resolve_task_origin"),
        "shared_task_expected": True,
        "valid_input_contract": "Public CLI wrapper over Story 3.3 resolve_task_origin.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_task_resolver.py", "test_b_multi_single_and_multi_plan_changes_applicable_set_digest"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_task_resolver.py", "test_b_multi_blocks_missing_origin_row_tampered_policy_and_stripped_b_ownership"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work",),
    },
    # ======================== Group 5: chapter4-5 ========================
    {
        "consumer_id": "llm_generate_overlays_batch_direct",
        "group": "chapter4-5",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/sc/llm_generate_overlays_batch.py",
        "symbol": "main",
        "actual_read_paths": ("docs/prd/**", "docs/architecture/overlays/**", "docs/planning/b-route/**"),
        "actual_write_paths": ("docs/architecture/overlays/**", "logs/ci/**"),
        "required_contract_modules": (),
        "required_call_tokens": ("main", "_guard_active_b_route_direct_write"),
        "shared_task_expected": False,
        "valid_input_contract": "Direct overlay batch generator gated fail-closed on --apply when B-route governance is active.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_chapter4_binding.py", "test_reuse_zero_edits_shared_task_conservation_and_clean_clone_semantics"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_consumer_alignment.py", "test_p02_direct_writers_block_under_active_b_route_and_allow_pure_legacy"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work",),
    },
    {
        "consumer_id": "b_route_chapter4_binding",
        "group": "chapter4-5",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_b_route_chapter4_binding.py",
        "symbol": "public_sync_paths",
        "actual_read_paths": ("docs/planning/b-route/**", "Game.Core/Contracts/**", "docs/architecture/overlays/**"),
        "actual_write_paths": ("docs/planning/b-route/bindings/**", "docs/planning/b-route/catalog.v1.json"),
        "required_contract_modules": ("_b_route_codec", "_b_route_records", "_b_route_task_resolver"),
        "required_call_tokens": ("resolve_task_origin", "public_sync_paths"),
        "shared_task_expected": True,
        "valid_input_contract": "Stage-3C binding + production contracts/four-part defs -> Stage-4 binding with raw-byte journal recovery.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_chapter4_binding.py", "test_reuse_zero_edits_shared_task_conservation_and_clean_clone_semantics"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_chapter4_binding.py", "test_reuse_blocks_non_b_task_missing_3c_and_altered_task_id_set"),),
        "remaining_epic5_items": ("reward_incremental_3c_and_production_csharp_adapter",),
    },
    {
        "consumer_id": "b_route_chapter4_binding_cli",
        "group": "chapter4-5",
        "entrypoint_kind": "public_cli",
        "module_path": "scripts/python/refine_b_route_chapter4_binding.py",
        "symbol": "main",
        "actual_read_paths": ("docs/planning/b-route/**", "Game.Core/Contracts/**"),
        "actual_write_paths": ("docs/planning/b-route/bindings/**", "docs/planning/b-route/catalog.v1.json"),
        "required_contract_modules": ("_b_route_codec", "_b_route_chapter4_binding"),
        "required_call_tokens": ("main",),
        "shared_task_expected": False,
        "valid_input_contract": "Public CLI wrapper over Story 3.4 Stage-4 binding refinement.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_chapter4_binding.py", "test_reuse_zero_edits_shared_task_conservation_and_clean_clone_semantics"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_chapter4_binding.py", "test_reuse_blocks_non_b_task_missing_3c_and_altered_task_id_set"),),
        "remaining_epic5_items": ("reward_incremental_3c_and_production_csharp_adapter",),
    },
    {
        "consumer_id": "b_route_input_set_resolver",
        "group": "chapter4-5",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_b_route_input_set.py",
        "symbol": "compute_input_set_digest",
        "actual_read_paths": ("docs/planning/b-route/**", ".taskmaster/tasks/*.json", "Game.Core/Contracts/**", "docs/testing/mvg/*.json"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_codec", "_b_route_task_resolver", "_b_route_operation_scope"),
        "required_call_tokens": ("compute_input_set_digest", "resolve_task_origin"),
        "shared_task_expected": True,
        "valid_input_contract": "Common InputSet across all applicable plans/bindings/contracts/ADRs/manifests/deps with 3A..5 drift attribution.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_input_set.py", "test_01_full_set_b_route_and_clean_clone_parity"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_input_set.py", "test_02_legal_non_flow_other_verification_and_not_enabled_a"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "b_route_input_set_cli",
        "group": "chapter4-5",
        "entrypoint_kind": "public_cli",
        "module_path": "scripts/python/resolve_b_route_input_set.py",
        "symbol": "main",
        "actual_read_paths": ("docs/planning/b-route/**", ".taskmaster/tasks/*.json"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_codec", "_b_route_input_set"),
        "required_call_tokens": ("main", "resolve_input_set"),
        "shared_task_expected": True,
        "valid_input_contract": "Public CLI wrapper over Story 3.5 resolve_input_set.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_input_set.py", "test_01_full_set_b_route_and_clean_clone_parity"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_input_set.py", "test_02_legal_non_flow_other_verification_and_not_enabled_a"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "b_route_stage5_obligations",
        "group": "chapter4-5",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_b_route_stage5_obligations.py",
        "symbol": "build",
        "actual_read_paths": ("docs/planning/b-route/**", "docs/testing/mvg/*.json"),
        "actual_write_paths": ("docs/planning/b-route/bindings/**", "docs/planning/b-route/catalog.v1.json"),
        "required_contract_modules": ("_b_route_codec", "_b_route_task_resolver", "_b_route_input_set"),
        "required_call_tokens": ("build", "resolve_task_origin", "extract_stage5_semantics"),
        "shared_task_expected": True,
        "valid_input_contract": "Stage-4/5 binding + manifest or legal non-Flow other_verification_refs with anti-weakening and shared-Task dedup.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_stage5_obligations.py", "test_flow_bind_full_lifecycle_conserves_stage4_and_multiplan_without_false_stage4_drift"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_stage5_obligations.py", "test_flow_bind_with_update_mvg_baseline_delta_public_sync_and_crash_recovery"),),
        "remaining_epic5_items": ("reward_incremental_3c_and_production_csharp_adapter",),
    },
    {
        "consumer_id": "b_route_stage5_obligations_cli",
        "group": "chapter4-5",
        "entrypoint_kind": "public_cli",
        "module_path": "scripts/python/bind_b_route_stage5_obligations.py",
        "symbol": "main",
        "actual_read_paths": ("docs/planning/b-route/**", "docs/testing/mvg/*.json"),
        "actual_write_paths": ("docs/planning/b-route/bindings/**", "docs/planning/b-route/catalog.v1.json"),
        "required_contract_modules": ("_b_route_codec", "_b_route_stage5_obligations"),
        "required_call_tokens": ("main",),
        "shared_task_expected": False,
        "valid_input_contract": "Public CLI wrapper over Story 3.6 Stage-5 obligation binding.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_stage5_obligations.py", "test_flow_bind_full_lifecycle_conserves_stage4_and_multiplan_without_false_stage4_drift"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_stage5_obligations.py", "test_flow_bind_with_update_mvg_baseline_delta_public_sync_and_crash_recovery"),),
        "remaining_epic5_items": ("reward_incremental_3c_and_production_csharp_adapter",),
    },
    {
        "consumer_id": "b_route_chapter5_readiness",
        "group": "chapter4-5",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_b_route_chapter5_readiness.py",
        "symbol": "reconcile_b_route_chapter5",
        "actual_read_paths": ("docs/planning/b-route/**", ".taskmaster/tasks/*.json", "logs/ci/b-route-source-audit/**"),
        "actual_write_paths": ("logs/ci/chapter5/readiness/**", "logs/ci/chapter5/reconciliation/**"),
        "required_contract_modules": ("_b_route_codec", "_b_route_task_resolver", "_b_route_input_set"),
        "required_call_tokens": ("reconcile_b_route_chapter5", "resolve_task_origin", "guarded_input_set"),
        "shared_task_expected": True,
        "valid_input_contract": "All applicable Stage-5 bindings + frozen common InputSet + P1 floor -> Task readiness (never runtime PASS).",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_chapter5_readiness.py", "test_01_reconcile_ok_freezes_input_set_reuses_3a_and_preserves_3b_plan"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_chapter5_readiness.py", "test_02_reconcile_ok_legal_non_flow_without_mvg_manifest"),),
        "remaining_epic5_items": ("reward_incremental_3c_and_production_csharp_adapter",),
    },
    {
        "consumer_id": "b_route_chapter5_readiness_cli",
        "group": "chapter4-5",
        "entrypoint_kind": "public_cli",
        "module_path": "scripts/python/reconcile_b_route_chapter5_readiness.py",
        "symbol": "main",
        "actual_read_paths": ("docs/planning/b-route/**", ".taskmaster/tasks/*.json"),
        "actual_write_paths": ("logs/ci/chapter5/**",),
        "required_contract_modules": ("_b_route_codec", "_b_route_chapter5_readiness"),
        "required_call_tokens": ("main",),
        "shared_task_expected": False,
        "valid_input_contract": "Public CLI wrapper over Story 3.7 Chapter 5 reconciliation and readiness.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_chapter5_readiness.py", "test_01_reconcile_ok_freezes_input_set_reuses_3a_and_preserves_3b_plan"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_chapter5_readiness.py", "test_02_reconcile_ok_legal_non_flow_without_mvg_manifest"),),
        "remaining_epic5_items": ("reward_incremental_3c_and_production_csharp_adapter",),
    },
    {
        "consumer_id": "chapter5_authority_scope_direct",
        "group": "chapter4-5",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/chapter5_semantic_reconciliation.py",
        "symbol": "build_task_authority_scope",
        "actual_read_paths": (".taskmaster/tasks/*.json", "docs/planning/b-route/**", "docs/adr/**"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_task_resolver",),
        "required_call_tokens": ("build_task_authority_scope", "resolve_task_origin"),
        "shared_task_expected": True,
        "valid_input_contract": "Direct Chapter 5 authority scope builder honoring Story 3.3 task-origin.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_chapter5_readiness.py", "test_01_reconcile_ok_freezes_input_set_reuses_3a_and_preserves_3b_plan"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_chapter5_readiness.py", "test_02_reconcile_ok_legal_non_flow_without_mvg_manifest"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work",),
    },
    {
        "consumer_id": "chapter5_fingerprint_direct",
        "group": "chapter4-5",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/chapter5_semantic_reconciliation.py",
        "symbol": "build_chapter5_input_fingerprint",
        "actual_read_paths": (".taskmaster/tasks/*.json", "docs/planning/b-route/**", "logs/ci/chapter5/**"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_task_resolver",),
        "required_call_tokens": ("build_chapter5_input_fingerprint", "resolve_task_origin"),
        "shared_task_expected": True,
        "valid_input_contract": "Direct Chapter 5 input fingerprint builder bridged to B-route common InputSet.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_chapter5_readiness.py", "test_01_reconcile_ok_freezes_input_set_reuses_3a_and_preserves_3b_plan"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_chapter5_readiness.py", "test_02_reconcile_ok_legal_non_flow_without_mvg_manifest"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work",),
    },
    {
        "consumer_id": "chapter5_reconciliation_direct",
        "group": "chapter4-5",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/chapter5_semantic_reconciliation.py",
        "symbol": "reconcile",
        "actual_read_paths": (".taskmaster/tasks/*.json", "docs/planning/b-route/**", "logs/ci/chapter5/**"),
        "actual_write_paths": ("logs/ci/chapter5/**",),
        "required_contract_modules": ("_b_route_task_resolver",),
        "required_call_tokens": ("reconcile", "resolve_task_origin"),
        "shared_task_expected": True,
        "valid_input_contract": "Direct Chapter 5 reconciliation honoring Story 3.3 task-origin and Story 3.7 readiness bridge.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_chapter5_readiness.py", "test_01_reconcile_ok_freezes_input_set_reuses_3a_and_preserves_3b_plan"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_chapter5_readiness.py", "test_02_reconcile_ok_legal_non_flow_without_mvg_manifest"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work",),
    },
    # ======================== Group 6: chapter6-direct-resume-route ========================
    {
        "consumer_id": "b_route_chapter6_gate",
        "group": "chapter6-direct-resume-route",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_b_route_chapter6_gate.py",
        "symbol": "evaluate_chapter6_gate",
        "actual_read_paths": ("docs/planning/b-route/**", ".taskmaster/tasks/*.json", "logs/ci/chapter5/readiness/**"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_codec", "_b_route_task_resolver", "_b_route_input_set"),
        "required_call_tokens": ("evaluate_chapter6_gate", "guarded_chapter6_execution", "resolve_task_origin"),
        "shared_task_expected": True,
        "valid_input_contract": "Unified 3.3->3.5->3.6->3.7 live gate + scoped business lease + status-only tasks.json write guard.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_chapter6_gate.py", "test_cli_direct_valid_flow_nonflow_and_integration_owner_parity"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_chapter6_gate.py", "test_cli_direct_old_done_surfaces_reverification"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work",),
    },
    {
        "consumer_id": "b_route_chapter6_gate_cli",
        "group": "chapter6-direct-resume-route",
        "entrypoint_kind": "public_cli",
        "module_path": "scripts/python/check_b_route_chapter6_gate.py",
        "symbol": "main",
        "actual_read_paths": ("docs/planning/b-route/**", ".taskmaster/tasks/*.json"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_codec", "_b_route_chapter6_gate"),
        "required_call_tokens": ("main", "evaluate_chapter6_gate"),
        "shared_task_expected": True,
        "valid_input_contract": "Public read-only CLI wrapper over Story 3.8 Chapter 6 execution gate.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_chapter6_gate.py", "test_cli_direct_valid_flow_nonflow_and_integration_owner_parity"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_chapter6_gate.py", "test_cli_direct_old_done_surfaces_reverification"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "ch6_mvg_obligations_gate",
        "group": "chapter6-direct-resume-route",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_mvg_obligations.py",
        "symbol": "check_task_obligations",
        "actual_read_paths": ("docs/testing/mvg/**", "docs/planning/b-route/**"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_chapter6_gate",),
        "required_call_tokens": ("check_task_obligations", "enforce_internal_script_gate"),
        "shared_task_expected": True,
        "valid_input_contract": "Underlying obligation check wired to live Story 3.8 Chapter 6 gate (no trace-free bypass).",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_chapter6_gate.py", "test_cli_direct_valid_flow_nonflow_and_integration_owner_parity"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_chapter6_gate.py", "test_cli_direct_old_done_surfaces_reverification"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "ch6_direct_single_task_lane",
        "group": "chapter6-direct-resume-route",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/run_single_task_chapter6_lane.py",
        "symbol": "main",
        "actual_read_paths": (".taskmaster/tasks/*.json", "docs/planning/b-route/**", "logs/ci/chapter5/readiness/**"),
        "actual_write_paths": ("logs/ci/**",),
        "required_contract_modules": ("_b_route_chapter6_gate",),
        "required_call_tokens": ("main", "guarded_chapter6_execution"),
        "shared_task_expected": True,
        "valid_input_contract": "Direct Chapter 6 lane enforcing live Story 3.8 gate and scoped business lease.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_chapter6_gate.py", "test_cli_direct_valid_flow_nonflow_and_integration_owner_parity"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_entrypoint_parity.py", "test_ac1_live_loopback_http_b_route_runtime_and_mvg_endpoints_enforce_gate_stop_loss_anti_disguise_and_zero_publish"),),
        "remaining_epic5_items": ("reward_incremental_3c_and_production_csharp_adapter",),
    },
    {
        "consumer_id": "ch6_direct_resume_task",
        "group": "chapter6-direct-resume-route",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/resume_task.py",
        "symbol": "main",
        "actual_read_paths": ("logs/ci/**", "docs/planning/b-route/**", ".taskmaster/tasks/*.json"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_chapter6_recovery", "_b_route_defect_routing"),
        "required_call_tokens": ("main",),
        "shared_task_expected": False,
        "valid_input_contract": "Direct resume-task with zero-write --recommendation-only and live Story 3.9 revalidation.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_chapter6_recovery.py", "test_01_rec_readonly_zero_write_and_never_trusts_cached_ready"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_chapter6_recovery.py", "test_02_explicit_not_enabled_a_passthrough_zero_write_and_invalid_task_id"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "ch6_direct_route",
        "group": "chapter6-direct-resume-route",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/chapter6_route.py",
        "symbol": "main",
        "actual_read_paths": ("logs/ci/**", "docs/planning/b-route/**", ".taskmaster/tasks/*.json"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_chapter6_recovery", "_b_route_chapter6_gate", "_b_route_defect_routing"),
        "required_call_tokens": ("main", "detect_b_route_presence"),
        "shared_task_expected": False,
        "valid_input_contract": "Direct chapter6-route honoring live Story 3.8/3.9/3.10 gates and durable stop-loss.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_chapter6_recovery.py", "test_01_rec_readonly_zero_write_and_never_trusts_cached_ready"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_defect_routing.py", "test_ac1_blocks_skip_readiness_skip_regressions_and_blind_3a_3b_rerun"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "ch6_direct_inspect_run",
        "group": "chapter6-direct-resume-route",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/inspect_run.py",
        "symbol": "main",
        "actual_read_paths": ("logs/ci/**", "docs/planning/b-route/**"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_chapter6_gate", "_b_route_chapter6_recovery"),
        "required_call_tokens": ("main", "detect_b_route_presence"),
        "shared_task_expected": False,
        "valid_input_contract": "Direct inspect-run revalidating B-route presence and durable stop-loss without trusting cached ok flags.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_chapter6_recovery.py", "test_01_rec_readonly_zero_write_and_never_trusts_cached_ready"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_chapter6_recovery.py", "test_02_explicit_not_enabled_a_passthrough_zero_write_and_invalid_task_id"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "b_route_defect_routing",
        "group": "chapter6-direct-resume-route",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_b_route_defect_routing.py",
        "symbol": "evaluate_defect_routing",
        "actual_read_paths": ("docs/planning/b-route/**", ".taskmaster/tasks/*.json", "logs/ci/**"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_codec", "_b_route_task_resolver", "_b_route_chapter6_gate"),
        "required_call_tokens": ("evaluate_defect_routing", "applicable_set_digest"),
        "shared_task_expected": True,
        "valid_input_contract": "Classifies pure implementation defects vs 3A..5 definition/contract/ownership changes; forbids N/A or test deletion.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_defect_routing.py", "test_ac1_impl_reuse_pure_implementation_admitted_zero_writes"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_defect_routing.py", "test_ac1_blocks_skip_readiness_skip_regressions_and_blind_3a_3b_rerun"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "b_route_defect_routing_cli",
        "group": "chapter6-direct-resume-route",
        "entrypoint_kind": "public_cli",
        "module_path": "scripts/python/check_b_route_defect_routing.py",
        "symbol": "main",
        "actual_read_paths": ("docs/planning/b-route/**", ".taskmaster/tasks/*.json"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_codec", "_b_route_defect_routing"),
        "required_call_tokens": ("main", "evaluate_defect_routing"),
        "shared_task_expected": False,
        "valid_input_contract": "Public CLI wrapper over Story 3.10 defect classification and return-stage routing.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_defect_routing.py", "test_ac1_impl_reuse_pure_implementation_admitted_zero_writes"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_defect_routing.py", "test_ac1_blocks_skip_readiness_skip_regressions_and_blind_3a_3b_rerun"),),
        "remaining_epic5_items": (),
    },
    # ======================== Group 7: chapter7 ========================
    {
        "consumer_id": "ch7_direct_ui_wiring",
        "group": "chapter7",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/run_chapter7_ui_wiring.py",
        "symbol": "main",
        "actual_read_paths": ("docs/workflows/chapter7-profile.json", "docs/planning/b-route/**", "Game.Godot/**"),
        "actual_write_paths": ("logs/ci/**",),
        "required_contract_modules": ("_b_route_chapter6_gate", "_b_route_chapter7_slice"),
        "required_call_tokens": ("main", "detect_b_route_presence"),
        "shared_task_expected": False,
        "valid_input_contract": "Direct Chapter 7 UI wiring supporting target-slice closure and Story 3.1/3.2 delta candidates.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_chapter7_slice.py", "test_ac1_slice_scope_evaluates_target_slice_without_waiting_for_whole_game_zero_writes"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_chapter7_slice.py", "test_ac1_legal_non_ui_scope_returns_not_applicable_with_proof"),),
        "remaining_epic5_items": ("reward_windows_godot_dual_path_runtime_evidence",),
    },
    {
        "consumer_id": "ch7_direct_backlog_gap",
        "group": "chapter7",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/run_chapter7_backlog_gap.py",
        "symbol": "main",
        "actual_read_paths": ("docs/workflows/chapter7-profile.json", "docs/planning/b-route/**", ".taskmaster/tasks/*.json"),
        "actual_write_paths": ("logs/ci/**",),
        "required_contract_modules": ("_b_route_chapter6_gate", "_b_route_chapter7_slice"),
        "required_call_tokens": ("main", "detect_b_route_presence"),
        "shared_task_expected": False,
        "valid_input_contract": "Direct Chapter 7 backlog gap reusing verified B-route UI evidence and preserving mature done tasks.",
        "pass_evidence_refs": (("scripts/python/tests/test_chapter7_backlog_gap.py", "test_slice_filter_and_b_route_verified_ui_reuse_prevent_synonymous_tasks"),),
        "fail_evidence_refs": (("scripts/python/tests/test_chapter7_backlog_gap.py", "test_stopword_filtering_and_failed_slice_do_not_falsely_suppress_gaps"),),
        "remaining_epic5_items": ("reward_windows_godot_dual_path_runtime_evidence",),
    },
    {
        "consumer_id": "ch7_direct_status_patch",
        "group": "chapter7",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/apply_chapter7_status_patch.py",
        "symbol": "main",
        "actual_read_paths": (".taskmaster/tasks/*.json", "docs/planning/b-route/**"),
        "actual_write_paths": (".taskmaster/tasks/*.json",),
        "required_contract_modules": ("_b_route_codec", "_b_route_task_resolver", "_b_route_chapter6_gate"),
        "required_call_tokens": ("main", "apply_patch_contract"),
        "shared_task_expected": False,
        "valid_input_contract": "Status-only Chapter 7 patch preserving mature done status across all triplet views under B-route leases.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_chapter7_slice.py", "test_ac1_slice_scope_evaluates_target_slice_without_waiting_for_whole_game_zero_writes"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_chapter7_slice.py", "test_ac1_legal_non_ui_scope_returns_not_applicable_with_proof"),),
        "remaining_epic5_items": ("reward_windows_godot_dual_path_runtime_evidence",),
    },
    {
        "consumer_id": "ch7_direct_create_tasks",
        "group": "chapter7",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/create_chapter7_tasks_from_ui_candidates.py",
        "symbol": "create_tasks",
        "actual_read_paths": ("docs/workflows/chapter7-profile.json", ".taskmaster/tasks/*.json", "docs/planning/b-route/**"),
        "actual_write_paths": (".taskmaster/tasks/*.json",),
        "required_contract_modules": (),
        "required_call_tokens": ("create_tasks", "_guard_active_b_route_direct_write"),
        "shared_task_expected": False,
        "valid_input_contract": "Legacy Chapter 7 task creator gated fail-closed whenever active B-route governance is present.",
        "pass_evidence_refs": (("scripts/python/tests/test_chapter7_ui_wiring.py", "test_collect_should_join_done_master_tasks_and_extract_ui_wiring_features"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_consumer_alignment.py", "test_p02_direct_writers_block_under_active_b_route_and_allow_pure_legacy"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work",),
    },
    {
        "consumer_id": "b_route_chapter7_slice_cli",
        "group": "chapter7",
        "entrypoint_kind": "public_cli",
        "module_path": "scripts/python/check_b_route_chapter7_slice.py",
        "symbol": "main",
        "actual_read_paths": ("docs/planning/b-route/**", "Game.Godot/**", "logs/ci/**"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_chapter7_slice", "_b_route_codec"),
        "required_call_tokens": ("main",),
        "shared_task_expected": False,
        "valid_input_contract": "Read-only target-slice Chapter 7 UI closure with honest .tscn/adapter wiring and manual boundary.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_chapter7_slice.py", "test_ac1_slice_scope_evaluates_target_slice_without_waiting_for_whole_game_zero_writes"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_chapter7_slice.py", "test_ac1_legal_non_ui_scope_returns_not_applicable_with_proof"),),
        "remaining_epic5_items": ("reward_windows_godot_dual_path_runtime_evidence",),
    },
    # ======================== Group 8: manifest-runner-handoff ========================
    {
        "consumer_id": "mvg_manifest_validator",
        "group": "manifest-runner-handoff",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_mvg_manifest.py",
        "symbol": "validate_manifest",
        "actual_read_paths": ("docs/testing/mvg/*.json",),
        "actual_write_paths": (),
        "required_contract_modules": (),
        "required_call_tokens": ("validate_manifest", "manifest_sha256"),
        "shared_task_expected": False,
        "valid_input_contract": "Cumulative MVG manifest structural, handoff, and normalized digest verification.",
        "pass_evidence_refs": (("scripts/python/tests/test_mvg_acceptance.py", "test_strict_gdunit_exit_allows_only_proven_post_success_shutdown_crash"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_verification_scope.py", "test_ac1_scope_contract_binds_identity_input_set_impact_proof_and_resists_old_manifest_cropping"),),
        "remaining_epic5_items": ("reward_windows_godot_dual_path_runtime_evidence",),
    },
    {
        "consumer_id": "mvg_acceptance_direct_runner",
        "group": "manifest-runner-handoff",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/run_mvg_acceptance.py",
        "symbol": "main",
        "actual_read_paths": ("docs/testing/mvg/*.json", "logs/ci/**"),
        "actual_write_paths": ("logs/ci/mvg-acceptance/**",),
        "required_contract_modules": ("_b_route_evidence_reuse", "_b_route_inventory", "_b_route_scope_runner"),
        "required_call_tokens": ("main", "run_scoped_mvg"),
        "shared_task_expected": True,
        "valid_input_contract": "Real MVG runner consuming sealed VerificationScope with isolated snapshot and coverage-receipt.json.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_scope_runner.py", "test_ac1_scoped_vs_conservative_superset_consumes_scope_snapshot_and_business_lease"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_evidence_reuse.py", "test_ac2_multi_flow_shared_test_deduplicates_once_and_rejects_same_name_different_selector_or_input"),),
        "remaining_epic5_items": ("reward_windows_godot_dual_path_runtime_evidence",),
    },
    {
        "consumer_id": "mvg_execution_engine",
        "group": "manifest-runner-handoff",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_mvg_execution.py",
        "symbol": "execute_test",
        "actual_read_paths": ("Game.Core.Tests/**", "Tests.Godot/**"),
        "actual_write_paths": ("logs/ci/mvg-acceptance/**",),
        "required_contract_modules": (),
        "required_call_tokens": ("execute_test",),
        "shared_task_expected": False,
        "valid_input_contract": "Per-test isolated execution producing raw TRX/XML and console logs without mutating snapshot.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_scope_runner.py", "test_ac1_scoped_vs_conservative_superset_consumes_scope_snapshot_and_business_lease"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_evidence_reuse.py", "test_ac1_build_and_prewarm_reuse_require_matching_identity_and_never_imply_test_pass_or_fake_cost_savings"),),
        "remaining_epic5_items": ("reward_windows_godot_dual_path_runtime_evidence",),
    },
    {
        "consumer_id": "milestone_incremental_handoff_direct",
        "group": "manifest-runner-handoff",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/milestone_incremental_handoff.py",
        "symbol": "build_task_handoff",
        "actual_read_paths": ("docs/testing/mvg/*.json", "logs/ci/**"),
        "actual_write_paths": ("logs/ci/**",),
        "required_contract_modules": ("_b_route_verification_scope", "_b_route_completion_verdict", "_b_route_inventory"),
        "required_call_tokens": ("build_task_handoff", "evaluate_completion_verdict"),
        "shared_task_expected": True,
        "valid_input_contract": "Cumulative milestone handoff delegating B-route verification to Story 4.2/4.5.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_completion_verdict.py", "test_ac1_single_task_local_pass_satisfies_task_only_while_incomplete_flow_stays_blocked_with_missing_items"),),
        "fail_evidence_refs": (("scripts/python/tests/test_milestone_incremental_workflow.py", "test_done_task_extension_requires_change_owner_or_explicit_reopen"),),
        "remaining_epic5_items": ("reward_windows_godot_dual_path_runtime_evidence",),
    },
    {
        "consumer_id": "b_route_impact_closure",
        "group": "manifest-runner-handoff",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_b_route_impact_closure.py",
        "symbol": "compute_impact_closure",
        "actual_read_paths": ("docs/planning/b-route/**", ".taskmaster/tasks/*.json", "docs/testing/mvg/*.json"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_codec", "_b_route_inventory"),
        "required_call_tokens": ("compute_impact_closure", "task_mappings"),
        "shared_task_expected": True,
        "valid_input_contract": "Cycle-safe reverse-relation transitive impact closure with conservative expansion on missing edges.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_impact_closure.py", "test_ac1_governed_reverse_closure_across_capabilities_shared_tasks_and_planned_flows"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_impact_closure.py", "test_ac2_cycle_termination_deduplication_and_unique_semantic_owner"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "b_route_impact_closure_cli",
        "group": "manifest-runner-handoff",
        "entrypoint_kind": "public_cli",
        "module_path": "scripts/python/compute_b_route_impact_closure.py",
        "symbol": "main",
        "actual_read_paths": ("docs/planning/b-route/**", ".taskmaster/tasks/*.json"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_codec", "_b_route_impact_closure"),
        "required_call_tokens": ("main", "compute_impact_closure"),
        "shared_task_expected": True,
        "valid_input_contract": "Public CLI wrapper over Story 4.1 compute_impact_closure.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_impact_closure.py", "test_ac1_governed_reverse_closure_across_capabilities_shared_tasks_and_planned_flows"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_impact_closure.py", "test_ac2_cycle_termination_deduplication_and_unique_semantic_owner"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "b_route_verification_scope",
        "group": "manifest-runner-handoff",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_b_route_verification_scope.py",
        "symbol": "validate_verification_scope",
        "actual_read_paths": ("docs/planning/b-route/**", "docs/testing/mvg/*.json", "docs/planning/b-route/schemas/verification-scope.schema.json"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_codec", "_b_route_impact_closure", "_b_route_schema_resources"),
        "required_call_tokens": ("validate_verification_scope", "build_verification_scope"),
        "shared_task_expected": True,
        "valid_input_contract": "Sealed auxiliary three-tier VerificationScope forbidding failing-flow reclassification and test deletion.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_verification_scope.py", "test_ac1_scope_contract_binds_identity_input_set_impact_proof_and_resists_old_manifest_cropping"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_verification_scope.py", "test_ac2_three_tier_classification_mixed_tier_flow_and_blocks_reclassifying_failed_flow_to_planned"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "b_route_verification_scope_cli",
        "group": "manifest-runner-handoff",
        "entrypoint_kind": "public_cli",
        "module_path": "scripts/python/build_b_route_verification_scope.py",
        "symbol": "main",
        "actual_read_paths": ("docs/planning/b-route/**", "docs/testing/mvg/*.json"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_codec", "_b_route_verification_scope"),
        "required_call_tokens": ("main", "build_verification_scope"),
        "shared_task_expected": True,
        "valid_input_contract": "Public CLI wrapper over Story 4.2 build_verification_scope.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_verification_scope.py", "test_ac1_scope_contract_binds_identity_input_set_impact_proof_and_resists_old_manifest_cropping"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_verification_scope.py", "test_ac2_three_tier_classification_mixed_tier_flow_and_blocks_reclassifying_failed_flow_to_planned"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "b_route_scope_runner",
        "group": "manifest-runner-handoff",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_b_route_scope_runner.py",
        "symbol": "run_scoped_mvg",
        "actual_read_paths": ("docs/testing/mvg/*.json", "logs/ci/**"),
        "actual_write_paths": ("logs/ci/mvg-acceptance/**",),
        "required_contract_modules": ("_b_route_codec", "_b_route_verification_scope", "_b_route_evidence_reuse"),
        "required_call_tokens": ("run_scoped_mvg", "validate_verification_scope"),
        "shared_task_expected": True,
        "valid_input_contract": "Real MVG scope execution under isolated snapshot & business-scope lease producing coverage-receipt.json.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_scope_runner.py", "test_ac1_scoped_vs_conservative_superset_consumes_scope_snapshot_and_business_lease"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_scope_runner.py", "test_ac2_coverage_receipt_handles_failed_skipped_empty_pending_manual_and_blocks_false_pass"),),
        "remaining_epic5_items": ("reward_windows_godot_dual_path_runtime_evidence",),
    },
    {
        "consumer_id": "b_route_evidence_reuse",
        "group": "manifest-runner-handoff",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_b_route_evidence_reuse.py",
        "symbol": "evaluate_test_evidence_reuse",
        "actual_read_paths": ("logs/ci/mvg-acceptance/**",),
        "actual_write_paths": ("logs/ci/**",),
        "required_contract_modules": ("_b_route_codec", "_b_route_inventory"),
        "required_call_tokens": ("evaluate_test_evidence_reuse", "evaluate_build_reuse"),
        "shared_task_expected": True,
        "valid_input_contract": "Same-snapshot build/prewarm reuse and shared test deduplication preserving original_executed_at.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_evidence_reuse.py", "test_ac1_build_and_prewarm_reuse_require_matching_identity_and_never_imply_test_pass_or_fake_cost_savings"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_evidence_reuse.py", "test_ac2_multi_flow_shared_test_deduplicates_once_and_rejects_same_name_different_selector_or_input"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "b_route_completion_verdict",
        "group": "manifest-runner-handoff",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_b_route_completion_verdict.py",
        "symbol": "evaluate_completion_verdict",
        "actual_read_paths": ("docs/planning/b-route/**", "docs/testing/mvg/*.json", "logs/ci/**"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_codec", "_b_route_verification_scope", "_b_route_inventory"),
        "required_call_tokens": ("evaluate_completion_verdict", "validate_verification_scope"),
        "shared_task_expected": True,
        "valid_input_contract": "Strict separation of Task-local, target-Flow, cumulative full-MVG milestone, and legal non-Flow completion.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_completion_verdict.py", "test_ac1_single_task_local_pass_satisfies_task_only_while_incomplete_flow_stays_blocked_with_missing_items"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_completion_verdict.py", "test_ac2_target_flow_completion_enforces_tier_non_substitution_manual_signoff_and_integration_owner_exemption"),),
        "remaining_epic5_items": ("reward_windows_godot_dual_path_runtime_evidence",),
    },
    {
        "consumer_id": "b_route_completion_verdict_cli",
        "group": "manifest-runner-handoff",
        "entrypoint_kind": "public_cli",
        "module_path": "scripts/python/check_b_route_completion_verdict.py",
        "symbol": "main",
        "actual_read_paths": ("docs/planning/b-route/**", "docs/testing/mvg/*.json", "logs/ci/**"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_codec", "_b_route_completion_verdict"),
        "required_call_tokens": ("main", "evaluate_completion_verdict"),
        "shared_task_expected": True,
        "valid_input_contract": "Public CLI wrapper over Story 4.5 evaluate_completion_verdict.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_completion_verdict.py", "test_ac1_single_task_local_pass_satisfies_task_only_while_incomplete_flow_stays_blocked_with_missing_items"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_completion_verdict.py", "test_ac2_target_flow_completion_enforces_tier_non_substitution_manual_signoff_and_integration_owner_exemption"),),
        "remaining_epic5_items": (),
    },
    # ======================== Group 9: knowledge-planning-page ========================
    {
        "consumer_id": "build_knowledge_catalog_direct",
        "group": "knowledge-planning-page",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/build_knowledge_catalog.py",
        "symbol": "main",
        "actual_read_paths": ("knowledge/policies/**", "docs/**", "Game.Core/**"),
        "actual_write_paths": ("knowledge/generated/**",),
        "required_contract_modules": (),
        "required_call_tokens": ("main",),
        "shared_task_expected": False,
        "valid_input_contract": "Trusted-ref Knowledge catalog builder enforcing source-exclusions.v1.json (logs/backup/migration excluded).",
        "pass_evidence_refs": (("scripts/python/tests/test_knowledge_publication.py", "test_publish_creates_immutable_generation_current_and_lkg"),),
        "fail_evidence_refs": (("scripts/python/tests/test_knowledge_publication.py", "test_check_blocks_when_bound_control_plane_artifact_drifts"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "publish_knowledge_catalog_direct",
        "group": "knowledge-planning-page",
        "entrypoint_kind": "direct_script",
        "module_path": "scripts/python/publish_knowledge_catalog.py",
        "symbol": "publish",
        "actual_read_paths": ("knowledge/policies/**", "knowledge/evaluation/**"),
        "actual_write_paths": ("knowledge/indexes/current.json", "knowledge/indexes/last-known-good.json"),
        "required_contract_modules": (),
        "required_call_tokens": ("publish",),
        "shared_task_expected": False,
        "valid_input_contract": "Sole trusted-ref KCP publisher advancing current.json and last-known-good.json after evaluation PASS.",
        "pass_evidence_refs": (("scripts/python/tests/test_knowledge_publication.py", "test_publish_creates_immutable_generation_current_and_lkg"),),
        "fail_evidence_refs": (("scripts/python/tests/test_knowledge_publication.py", "test_check_blocks_when_bound_control_plane_artifact_drifts"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "b_route_knowledge_projection",
        "group": "knowledge-planning-page",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_b_route_knowledge_projection.py",
        "symbol": "build_b_route_knowledge_projection",
        "actual_read_paths": ("docs/planning/b-route/**", ".taskmaster/tasks/*.json", "knowledge/policies/source-exclusions.v1.json"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_codec", "_b_route_records"),
        "required_call_tokens": ("build_b_route_knowledge_projection", "task_mappings"),
        "shared_task_expected": True,
        "valid_input_contract": "Ten-layer read-only derived projection separating planning/impl/runtime states and workspace vs main.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_knowledge_projection.py", "test_ten_layer_chain_keeps_planning_implementation_runtime_and_evidence_separate"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_knowledge_projection.py", "test_fixture_records_pass_formal_record_validation"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "query_b_route_knowledge_projection_cli",
        "group": "knowledge-planning-page",
        "entrypoint_kind": "public_cli",
        "module_path": "scripts/python/query_b_route_knowledge_projection.py",
        "symbol": "main",
        "actual_read_paths": ("docs/planning/b-route/**", ".taskmaster/tasks/*.json"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_codec", "_b_route_knowledge_projection"),
        "required_call_tokens": ("main", "build_b_route_knowledge_projection"),
        "shared_task_expected": True,
        "valid_input_contract": "Read-only public CLI wrapper over Story 4.6 derived knowledge projection.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_knowledge_projection.py", "test_ten_layer_chain_keeps_planning_implementation_runtime_and_evidence_separate"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_knowledge_projection.py", "test_fixture_records_pass_formal_record_validation"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "b_route_planning_page",
        "group": "knowledge-planning-page",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_b_route_planning_page.py",
        "symbol": "execute_planning_page_action",
        "actual_read_paths": ("docs/planning/b-route/**", "logs/ci/**"),
        "actual_write_paths": ("logs/ci/**",),
        "required_contract_modules": ("_b_route_codec", "_b_route_knowledge_projection", "_b_route_entrypoint_parity"),
        "required_call_tokens": ("execute_planning_page_action", "build_b_route_knowledge_projection"),
        "shared_task_expected": True,
        "valid_input_contract": "Stage-true 3A/3B/3C/Ch6 page actions with budget-preserving resume and zero pointer publication.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_planning_page.py", "test_no_task_no_readiness_enables_3a_3b_while_3c_and_chapter6_block"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_planning_page.py", "test_3b_requires_accepted_3a_evidence_and_blocks_without_delegation"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "query_b_route_planning_page_cli",
        "group": "knowledge-planning-page",
        "entrypoint_kind": "public_cli",
        "module_path": "scripts/python/query_b_route_planning_page.py",
        "symbol": "main",
        "actual_read_paths": ("docs/planning/b-route/**", "logs/ci/**"),
        "actual_write_paths": ("logs/ci/**",),
        "required_contract_modules": ("_b_route_codec", "_b_route_planning_page"),
        "required_call_tokens": ("main", "execute_planning_page_action"),
        "shared_task_expected": True,
        "valid_input_contract": "Public CLI wrapper over Story 4.7 stage-true planning page backend.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_planning_page.py", "test_no_task_no_readiness_enables_3a_3b_while_3c_and_chapter6_block"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_planning_page.py", "test_3b_requires_accepted_3a_evidence_and_blocks_without_delegation"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "b_route_observability",
        "group": "knowledge-planning-page",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_b_route_observability.py",
        "symbol": "build_b_route_observability_report",
        "actual_read_paths": ("logs/ci/**", "docs/planning/b-route/**"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_codec", "_b_route_inventory", "_b_route_knowledge_projection"),
        "required_call_tokens": ("build_b_route_observability_report",),
        "shared_task_expected": True,
        "valid_input_contract": "Bounded 5-axis process observability, unified six-field diagnostics, and non-offsettable quality floor.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_observability.py", "test_ac1_five_axis_aggregation_dedup_retries_and_dispatch_correlation"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_observability.py", "test_ac2_observed_vs_paused_reserved_unknown_baselines_and_zero_gates"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "query_b_route_observability_cli",
        "group": "knowledge-planning-page",
        "entrypoint_kind": "public_cli",
        "module_path": "scripts/python/query_b_route_observability.py",
        "symbol": "main",
        "actual_read_paths": ("logs/ci/**", "docs/planning/b-route/**"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_codec", "_b_route_observability"),
        "required_call_tokens": ("main", "build_b_route_observability_report"),
        "shared_task_expected": True,
        "valid_input_contract": "Read-only public CLI wrapper over Story 4.8 process observability aggregator.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_observability.py", "test_ac1_five_axis_aggregation_dedup_retries_and_dispatch_correlation"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_observability.py", "test_ac2_observed_vs_paused_reserved_unknown_baselines_and_zero_gates"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "project_health_http_server",
        "group": "knowledge-planning-page",
        "entrypoint_kind": "http_or_ui",
        "module_path": "scripts/python/_project_health_http.py",
        "symbol": "handler_factory",
        "actual_read_paths": ("docs/planning/b-route/**", "logs/ci/**"),
        "actual_write_paths": ("logs/ci/**",),
        "required_contract_modules": (
            "_b_route_entrypoint_parity",
            "_b_route_knowledge_projection",
            "_b_route_planning_page",
            "_b_route_observability",
        ),
        "required_call_tokens": ("handler_factory", "handle_page_b_route_trigger", "build_b_route_observability_report"),
        "shared_task_expected": True,
        "valid_input_contract": "HTTP endpoints for b-route projection, planning-page, observability, and Story 3.12 page trigger parity.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_entrypoint_parity.py", "test_ac1_live_loopback_http_b_route_runtime_and_mvg_endpoints_enforce_gate_stop_loss_anti_disguise_and_zero_publish"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_entrypoint_parity.py", "test_ac1_rogue_runner_mutating_publication_pointer_in_workspace_preview_is_blocked"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "project_health_planning_jobs",
        "group": "knowledge-planning-page",
        "entrypoint_kind": "http_or_ui",
        "module_path": "scripts/python/_project_health_planning.py",
        "symbol": "run_job",
        "actual_read_paths": ("docs/planning/semantic-topology/**", "logs/ci/**"),
        "actual_write_paths": ("logs/ci/knowledge-planning/**",),
        "required_contract_modules": (),
        "required_call_tokens": ("run_job",),
        "shared_task_expected": False,
        "valid_input_contract": "Background planning job runner; workspace preview never advances KCP current/LKG pointers.",
        "pass_evidence_refs": (("scripts/python/tests/test_project_health_planning.py", "test_checkout_reads_latest_main_and_ignores_dirty_feature_files"),),
        "fail_evidence_refs": (("scripts/python/tests/test_project_health_planning.py", "test_evidence_hydration_accepts_relative_repository_root"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work",),
    },
    {
        "consumer_id": "project_health_planning_ui",
        "group": "knowledge-planning-page",
        "entrypoint_kind": "http_or_ui",
        "module_path": "scripts/python/project_health_planning.js",
        "symbol": None,
        "actual_read_paths": ("/api/knowledge/b-route-planning", "/api/knowledge/b-route-observability"),
        "actual_write_paths": (),
        "required_contract_modules": (),
        "required_call_tokens": ("mountBRouteStagePanel", "renderBRouteObservability", "/api/knowledge/b-route-planning"),
        "shared_task_expected": False,
        "valid_input_contract": "Read-only diagnostics and stage-true planning UI using textContent without pointer mutation.",
        "pass_evidence_refs": (("scripts/python/tests/test_topology_frontend.py", "test_planning_buttons_refresh_data_and_keep_compact_results"),),
        "fail_evidence_refs": (("scripts/python/tests/js/test_b_route_planning_page_ui.cjs", "observabilityVerbatimDiagnosticsAndReadonlyCollapse"),),
        "remaining_epic5_items": (),
    },
    # ======================== Group 10: cli-skill-routing-examples ========================
    {
        "consumer_id": "dev_cli_dispatcher",
        "group": "cli-skill-routing-examples",
        "entrypoint_kind": "public_cli",
        "module_path": "scripts/python/dev_cli.py",
        "symbol": "main",
        "actual_read_paths": ("scripts/python/**",),
        "actual_write_paths": (),
        "required_contract_modules": (),
        "required_call_tokens": (
            "b-route-sources",
            "b-route-adoption",
            "b-route-task-origin",
            "b-route-chapter6-gate",
            "b-route-verification-scope",
            "b-route-completion-verdict",
            "b-route-knowledge-projection",
            "b-route-planning-page",
            "b-route-observability",
            "b-route-consumer-alignment",
        ),
        "shared_task_expected": False,
        "valid_input_contract": "Public CLI routing all B-route subcommands with zero-bytecode read-only dispatch.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_entrypoint_parity.py", "test_ac1_live_loopback_http_b_route_runtime_and_mvg_endpoints_enforce_gate_stop_loss_anti_disguise_and_zero_publish"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_observability.py", "test_ac1_five_axis_aggregation_dedup_retries_and_dispatch_correlation"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work",),
    },
    {
        "consumer_id": "dev_cli_builders_shared",
        "group": "cli-skill-routing-examples",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/dev_cli_builders.py",
        "symbol": None,
        "actual_read_paths": (),
        "actual_write_paths": (),
        "required_contract_modules": (),
        "required_call_tokens": (
            "build_b_route_chapter6_gate_cmd",
            "build_b_route_verification_scope_cmd",
            "build_b_route_observability_cmd",
            "build_b_route_consumer_alignment_cmd",
        ),
        "shared_task_expected": False,
        "valid_input_contract": "Strict command-line argument builders forbidding mutation/switch flags on read-only commands.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_consumer_alignment.py", "test_ac5_pre_switch_report_invariants_and_cli_forbids_switch_flags"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_knowledge_projection.py", "test_ten_layer_chain_keeps_planning_implementation_runtime_and_evidence_separate"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "b_route_entrypoint_parity",
        "group": "cli-skill-routing-examples",
        "entrypoint_kind": "shared_library_gate",
        "module_path": "scripts/python/_b_route_entrypoint_parity.py",
        "symbol": "handle_page_b_route_trigger",
        "actual_read_paths": ("docs/planning/b-route/**", "logs/ci/**"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_codec", "_b_route_chapter6_gate"),
        "required_call_tokens": ("handle_page_b_route_trigger", "guarded_chapter6_execution"),
        "shared_task_expected": True,
        "valid_input_contract": "Five-entrypoint parity (cli, direct, resume, route, page) with identical live gate and leases.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_entrypoint_parity.py", "test_ac1_live_loopback_http_b_route_runtime_and_mvg_endpoints_enforce_gate_stop_loss_anti_disguise_and_zero_publish"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_entrypoint_parity.py", "test_ac1_rogue_runner_mutating_publication_pointer_in_workspace_preview_is_blocked"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work",),
    },
    {
        "consumer_id": "b_route_entrypoint_parity_cli",
        "group": "cli-skill-routing-examples",
        "entrypoint_kind": "public_cli",
        "module_path": "scripts/python/check_b_route_entrypoint_parity.py",
        "symbol": "main",
        "actual_read_paths": ("docs/planning/b-route/**", "logs/ci/**"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_codec", "_b_route_entrypoint_parity"),
        "required_call_tokens": ("main",),
        "shared_task_expected": False,
        "valid_input_contract": "Public CLI wrapper over Story 3.12 five-entrypoint parity audit.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_entrypoint_parity.py", "test_ac1_live_loopback_http_b_route_runtime_and_mvg_endpoints_enforce_gate_stop_loss_anti_disguise_and_zero_publish"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_entrypoint_parity.py", "test_ac1_rogue_runner_mutating_publication_pointer_in_workspace_preview_is_blocked"),),
        "remaining_epic5_items": (),
    },
    {
        "consumer_id": "b_route_consumer_alignment_cli",
        "group": "cli-skill-routing-examples",
        "entrypoint_kind": "public_cli",
        "module_path": "scripts/python/audit_b_route_consumer_alignment.py",
        "symbol": "main",
        "actual_read_paths": ("scripts/python/**", "docs/**", ".agents/skills/**", "knowledge/policies/**"),
        "actual_write_paths": (),
        "required_contract_modules": ("_b_route_codec", "_b_route_consumer_alignment"),
        "required_call_tokens": ("main", "audit_b_route_consumer_alignment"),
        "shared_task_expected": False,
        "valid_input_contract": "Read-only Story 4.9 consumer alignment & pre-switch audit CLI (fail-closed on --skip-live-probes).",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_consumer_alignment.py", "test_ac1_live_consumer_matrix_all_ten_groups_and_mutation_blocking"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_consumer_alignment.py", "test_ac5_pre_switch_report_invariants_and_cli_forbids_switch_flags"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work",),
    },
    {
        "consumer_id": "agents_and_skills_governance",
        "group": "cli-skill-routing-examples",
        "entrypoint_kind": "skill_or_doc",
        "module_path": "AGENTS.md",
        "symbol": None,
        "actual_read_paths": ("docs/workflows/b-route-*.md", ".agents/skills/**/SKILL.md", "docs/adr/ADR-*.md"),
        "actual_write_paths": (),
        "required_contract_modules": (),
        "required_call_tokens": (
            "b-route-sources",
            "b-route-task-origin",
            "b-route-chapter6-gate",
            "b-route-verification-scope",
            "b-route-completion-verdict",
            "b-route-knowledge-projection",
            "b-route-planning-page",
            "b-route-observability",
            "b-route-consumer-alignment",
        ),
        "shared_task_expected": False,
        "valid_input_contract": "Repository routing table aligned with implemented B-route entrypoints without mutating workflow.md.",
        "pass_evidence_refs": (("scripts/python/tests/test_agent_context_routing.py", "test_root_routing_is_task_scoped_and_cross_domain_composable"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_runtime_ci.py", "test_pr_paths_include_selected_tests_and_actual_pipe_fixture_owners"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work", "independent_a_exit_gate_and_revocation"),
    },
    {
        "consumer_id": "workflow_md_static_doc",
        "group": "cli-skill-routing-examples",
        "entrypoint_kind": "skill_or_doc",
        "runtime_gate_applicable": False,
        "module_path": "workflow.md",
        "symbol": None,
        "actual_read_paths": (),
        "actual_write_paths": (),
        "required_contract_modules": (),
        "required_call_tokens": (),
        "shared_task_expected": False,
        "valid_input_contract": "Pure static non-executable workflow doc; zero runtime gate execution (audited for immutability in AC-3).",
        "pass_evidence_refs": (("scripts/python/tests/test_agent_context_routing.py", "test_workflow_does_not_reintroduce_global_agent_index_preload"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_consumer_alignment.py", "test_ac3_docs_skills_adr_alignment_and_negative_controls"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work", "independent_a_exit_gate_and_revocation"),
    },
    {
        "consumer_id": "stable_public_entrypoints_doc",
        "group": "cli-skill-routing-examples",
        "entrypoint_kind": "skill_or_doc",
        "module_path": "docs/workflows/stable-public-entrypoints.md",
        "symbol": None,
        "actual_read_paths": (),
        "actual_write_paths": (),
        "required_contract_modules": (),
        "required_call_tokens": ("b-route-consumer-alignment", "ADR-0038-semantic-delivery-topology.md", "ADR-0038-mvg-candidate-admission.md"),
        "shared_task_expected": False,
        "valid_input_contract": "Public entrypoint catalog synchronized with implemented dev_cli subcommands.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_consumer_alignment.py", "test_ac3_docs_skills_adr_alignment_and_negative_controls"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_runtime_ci.py", "test_pr_paths_include_selected_tests_and_actual_pipe_fixture_owners"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work",),
    },
    {
        "consumer_id": "script_entrypoints_index_doc",
        "group": "cli-skill-routing-examples",
        "entrypoint_kind": "skill_or_doc",
        "module_path": "docs/workflows/script-entrypoints-index.md",
        "symbol": None,
        "actual_read_paths": (),
        "actual_write_paths": (),
        "required_contract_modules": (),
        "required_call_tokens": ("audit_b_route_consumer_alignment.py", "b-route-consumer-alignment"),
        "shared_task_expected": False,
        "valid_input_contract": "Script entrypoint index covering direct and public CLI scripts.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_consumer_alignment.py", "test_ac3_docs_skills_adr_alignment_and_negative_controls"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_runtime_ci.py", "test_pr_paths_include_selected_tests_and_actual_pipe_fixture_owners"),),
        "remaining_epic5_items": ("governed_default_b_switch_for_new_work",),
    },
    {
        "consumer_id": "mvg_integration_acceptance_doc",
        "group": "cli-skill-routing-examples",
        "entrypoint_kind": "skill_or_doc",
        "module_path": "docs/workflows/mvg-integration-acceptance.md",
        "symbol": None,
        "actual_read_paths": (),
        "actual_write_paths": (),
        "required_contract_modules": (),
        "required_call_tokens": ("run-mvg-acceptance", "Proposed ADR-0037"),
        "shared_task_expected": False,
        "valid_input_contract": "MVG integration acceptance owning doc preserving Proposed ADR-0037 distinction.",
        "pass_evidence_refs": (("scripts/python/tests/test_b_route_consumer_alignment.py", "test_ac3_docs_skills_adr_alignment_and_negative_controls"),),
        "fail_evidence_refs": (("scripts/python/tests/test_b_route_runtime_ci.py", "test_pr_paths_include_selected_tests_and_actual_pipe_fixture_owners"),),
        "remaining_epic5_items": ("reward_windows_godot_dual_path_runtime_evidence",),
    },
)


def _diag(
    code: codec.ReasonCode,
    stage: codec.Stage,
    entity_id: str | None,
    expected: Any,
    actual: Any,
    resume_ref: str | None = None,
) -> dict[str, Any]:
    return codec.Diagnostic(code, stage, entity_id, expected, actual, resume_ref).to_dict()


def _sha256_bytes(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _safe_read_bytes(root: Path, rel: str, *, allow_logs: bool = False) -> bytes:
    """Safely read a repository-relative file via safe_input + ancestor no_reparse + lexists."""
    target = inventory.safe_input(root, rel, allow_logs=allow_logs)
    observability._check_ancestors_no_reparse(root, target)
    if not os.path.lexists(target):
        raise FileNotFoundError(rel)
    inventory.no_reparse(target)
    if target.is_dir():
        raise IsADirectoryError(rel)
    return target.read_bytes()


def _safe_existing_file(root: Path, rel: str, *, allow_logs: bool = False) -> tuple[bool, codec.ReasonCode | None, str | None]:
    """Check whether rel is an existing non-reparse regular file under root."""
    try:
        target = inventory.safe_input(root, rel, allow_logs=allow_logs)
        observability._check_ancestors_no_reparse(root, target)
        if not os.path.lexists(target):
            return False, codec.ReasonCode.FILE_NOT_FOUND, f"missing: {rel}"
        inventory.no_reparse(target)
        if not target.is_file():
            return False, codec.ReasonCode.READ_ERROR, f"not a regular file: {rel}"
        return True, None, None
    except ValueError as exc:
        return False, codec.ReasonCode.UNSAFE_PATH, str(exc)[:200]
    except OSError as exc:
        return False, codec.ReasonCode.READ_ERROR, str(exc)[:200]


def _classify_read_exc(exc: Exception) -> codec.ReasonCode:
    if isinstance(exc, ValueError):
        return codec.ReasonCode.UNSAFE_PATH
    if isinstance(exc, FileNotFoundError):
        return codec.ReasonCode.FILE_NOT_FOUND
    if isinstance(exc, UnicodeDecodeError):
        return codec.ReasonCode.INVALID_UTF8
    return codec.ReasonCode.READ_ERROR


def _safe_dir_ready(root: Path, rel_dir: str) -> tuple[Path | None, dict[str, Any] | None]:
    """Validate a repo-relative directory via safe_input + ancestor no_reparse before listing."""
    try:
        target = inventory.safe_input(root, rel_dir, allow_logs=False)
        observability._check_ancestors_no_reparse(root, target)
        if not os.path.lexists(target):
            return None, None
        inventory.no_reparse(target)
        if not target.is_dir():
            return None, _diag(
                codec.ReasonCode.READ_ERROR,
                codec.Stage.PATH,
                rel_dir,
                f"regular directory {rel_dir}",
                "not_a_directory",
                rel_dir,
            )
        return target, None
    except ValueError as exc:
        return None, _diag(
            codec.ReasonCode.UNSAFE_PATH,
            codec.Stage.PATH,
            rel_dir,
            f"safe directory {rel_dir} without symlink/reparse",
            str(exc)[:200],
            rel_dir,
        )
    except OSError as exc:
        return None, _diag(
            codec.ReasonCode.READ_ERROR,
            codec.Stage.PATH,
            rel_dir,
            f"readable directory {rel_dir}",
            str(exc)[:200],
            rel_dir,
        )


def _extract_python_ast_info(raw: bytes) -> tuple[set[str], set[str], set[str], set[str], int]:
    """Return (top_and_nested_defs, imported_modules, identifiers, string_literals, stmt_count)."""
    tree = ast.parse(raw.decode("utf-8-sig"))
    defs: set[str] = set()
    imports: set[str] = set()
    names: set[str] = set()
    strings: set[str] = set()
    non_doc_stmts = 0

    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            continue
        if isinstance(node, ast.Pass):
            continue
        non_doc_stmts += 1

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defs.add(node.name)
            names.add(node.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split(".")[0])
                imports.add(node.module)
                names.add(node.module.split(".")[0])
            for alias in node.names:
                names.add(alias.name)
                if alias.asname:
                    names.add(alias.asname)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
                imports.add(alias.name)
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            strings.add(node.value)
            if node.value in PUBLIC_CONTRACT_MODULES:
                imports.add(node.value)
    return defs, imports, names, strings, non_doc_stmts


def _verify_test_evidence_ref(root: Path, test_path: str, exact_symbol: str) -> tuple[bool, str]:
    """Require an exact existing test method/function name (reject generic 'test_' prefixes)."""
    if not exact_symbol or exact_symbol in {"test", "test_"}:
        return False, f"generic test ref {exact_symbol!r} rejected; exact test method name required"
    try:
        raw = _safe_read_bytes(root, test_path, allow_logs=False)
    except (OSError, ValueError) as exc:
        return False, f"unreadable test file {test_path}: {exc}"
    try:
        text = raw.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        return False, f"non-utf8 test file {test_path}: {exc}"
    if test_path.endswith(".py"):
        try:
            tree = ast.parse(text)
        except SyntaxError as exc:
            return False, f"syntax error in {test_path}: {exc}"
        matches = [
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == exact_symbol
        ]
        if not matches:
            return False, f"exact test function {exact_symbol!r} not found in {test_path}"
        return True, f"{test_path}::{exact_symbol}"
    fn_pattern = re.compile(rf"\bfunction\s+{re.escape(exact_symbol)}\s*\(")
    if fn_pattern.search(text) and "assert" in text:
        return True, f"{test_path}::{exact_symbol}"
    return False, f"exact JS test function {exact_symbol!r} not found in {test_path}"


def validate_consumer_claim(claim: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    """Explicitly reject summary-only, workflow.md-only, or dispatcher-only coverage claims."""
    diagnostics: list[dict[str, Any]] = []
    if not isinstance(claim, dict):
        diagnostics.append(_diag(
            codec.ReasonCode.INVALID_TYPE,
            codec.Stage.CONTENT,
            "consumer_claim",
            "dict with itemized consumers array",
            type(claim).__name__,
            None,
        ))
        return False, diagnostics

    claim_basis = str(claim.get("claim_basis") or "").strip().lower()
    if claim_basis in {"summary_only", "workflow_md_only", "dispatcher_only", "story_text_only"}:
        diagnostics.append(_diag(
            codec.ReasonCode.SEMANTIC_ERROR,
            codec.Stage.CONTENT,
            "consumer_claim",
            "item-by-item verified consumer matrix across all 10 groups",
            claim_basis,
            None,
        ))
        return False, diagnostics

    items = claim.get("consumers")
    if not isinstance(items, list) or len(items) < len(inventory.GROUPS):
        diagnostics.append(_diag(
            codec.ReasonCode.MISSING_REQUIRED_FIELD,
            codec.Stage.CONTENT,
            "consumer_claim",
            f"itemized consumers list covering all {len(inventory.GROUPS)} groups",
            len(items) if isinstance(items, list) else type(items).__name__,
            None,
        ))
        return False, diagnostics

    covered_groups = {
        row.get("group")
        for row in items
        if isinstance(row, dict) and row.get("status") in {"passed", "not_applicable"}
    }
    expected_groups = {g[0] for g in inventory.GROUPS}
    missing = sorted(expected_groups - covered_groups)
    if missing:
        diagnostics.append(_diag(
            codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
            codec.Stage.CONTENT,
            "consumer_claim",
            sorted(expected_groups),
            {"missing_groups": missing},
            None,
        ))
        return False, diagnostics

    kinds = {row.get("entrypoint_kind") for row in items if isinstance(row, dict)}
    if "direct_script" not in kinds:
        diagnostics.append(_diag(
            codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
            codec.Stage.CONTENT,
            "consumer_claim",
            "must include direct underlying scripts (not dispatcher-only)",
            sorted(k for k in kinds if isinstance(k, str)),
            None,
        ))
        return False, diagnostics

    return True, diagnostics


def _audit_consumer_matrix(root: Path) -> dict[str, Any]:
    """AC-1: Item-by-item AST/file reconciliation of all 10 groups & 100% of inventory.GROUPS."""
    diagnostics: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    group_names = tuple(row[0] for row in inventory.GROUPS)
    group_map: dict[str, list[dict[str, Any]]] = {g: [] for g in group_names}

    for spec in CONSUMER_REGISTRY:
        cid = spec["consumer_id"]
        group = spec["group"]
        mod_path = spec["module_path"]
        symbol = spec["symbol"]
        runtime_applicable = bool(spec.get("runtime_gate_applicable", True))
        item_diags: list[dict[str, Any]] = []
        sha = None
        public_contracts: list[str] = []
        shared_task_supported = False
        verified_pass_refs: list[str] = []
        verified_fail_refs: list[str] = []

        try:
            raw = _safe_read_bytes(root, mod_path, allow_logs=False)
            sha = _sha256_bytes(raw)
        except (OSError, ValueError) as exc:
            item_diags.append(_diag(
                _classify_read_exc(exc),
                codec.Stage.PATH,
                cid,
                f"readable consumer file {mod_path}",
                str(exc)[:200],
                mod_path,
            ))
            raw = None

        if raw is not None:
            if mod_path.endswith(".py"):
                try:
                    defs, imports, names, strings, stmt_count = _extract_python_ast_info(raw)
                except (SyntaxError, UnicodeDecodeError) as exc:
                    item_diags.append(_diag(
                        codec.ReasonCode.INVALID_UTF8 if isinstance(exc, UnicodeDecodeError) else codec.ReasonCode.INVALID_JSON,
                        codec.Stage.CONTENT,
                        cid,
                        "valid UTF-8 Python module",
                        str(exc)[:200],
                        mod_path,
                    ))
                    defs, imports, names, strings, stmt_count = set(), set(), set(), set(), 0

                if stmt_count < 2:
                    item_diags.append(_diag(
                        codec.ReasonCode.SEMANTIC_ERROR,
                        codec.Stage.CONTENT,
                        cid,
                        "non-stub consumer implementation (summary-only stub rejected)",
                        f"stmt_count={stmt_count}",
                        mod_path,
                    ))

                if symbol and symbol not in (defs | names):
                    item_diags.append(_diag(
                        codec.ReasonCode.MISSING_REQUIRED_FIELD,
                        codec.Stage.CONTENT,
                        cid,
                        f"Python symbol {symbol}",
                        "missing",
                        mod_path,
                    ))

                own_mod = Path(mod_path).stem
                effective_mods = imports | ({own_mod} if own_mod in PUBLIC_CONTRACT_MODULES else set())
                public_contracts = sorted(effective_mods & PUBLIC_CONTRACT_MODULES)

                missing_mods = [m for m in spec["required_contract_modules"] if m not in effective_mods]
                if missing_mods:
                    item_diags.append(_diag(
                        codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
                        codec.Stage.CONTENT,
                        cid,
                        list(spec["required_contract_modules"]),
                        {"missing_contract_modules": missing_mods},
                        mod_path,
                    ))

                all_tokens = names | strings | imports
                missing_tokens = [tok for tok in spec["required_call_tokens"] if tok not in all_tokens]
                if missing_tokens:
                    item_diags.append(_diag(
                        codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
                        codec.Stage.CONTENT,
                        cid,
                        list(spec["required_call_tokens"]),
                        {"missing_call_tokens": missing_tokens},
                        mod_path,
                    ))

                shared_task_supported = bool(all_tokens & _SHARED_TASK_TOKENS)
                if spec["shared_task_expected"] and not shared_task_supported:
                    item_diags.append(_diag(
                        codec.ReasonCode.SEMANTIC_ERROR,
                        codec.Stage.CONTENT,
                        cid,
                        "shared-Task multi-scope handling via public resolver/gate/closure",
                        "not_detected",
                        mod_path,
                    ))
            else:
                try:
                    text = raw.decode("utf-8-sig")
                except UnicodeDecodeError as exc:
                    item_diags.append(_diag(
                        codec.ReasonCode.INVALID_UTF8,
                        codec.Stage.DECODE,
                        cid,
                        "valid UTF-8 document/script",
                        str(exc)[:200],
                        mod_path,
                    ))
                    text = ""
                if not text.strip():
                    item_diags.append(_diag(
                        codec.ReasonCode.SEMANTIC_ERROR,
                        codec.Stage.CONTENT,
                        cid,
                        "nonempty consumer document/script",
                        "empty",
                        mod_path,
                    ))
                if symbol and symbol not in text:
                    item_diags.append(_diag(
                        codec.ReasonCode.MISSING_REQUIRED_FIELD,
                        codec.Stage.CONTENT,
                        cid,
                        f"symbol {symbol}",
                        "missing",
                        mod_path,
                    ))
                missing_tokens = [tok for tok in spec["required_call_tokens"] if tok not in text]
                if missing_tokens:
                    item_diags.append(_diag(
                        codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
                        codec.Stage.CONTENT,
                        cid,
                        list(spec["required_call_tokens"]),
                        {"missing_tokens": missing_tokens},
                        mod_path,
                    ))
                shared_task_supported = any(tok in text for tok in _SHARED_TASK_TOKENS)

        for test_file, sym_name in spec["pass_evidence_refs"]:
            ok_ref, detail = _verify_test_evidence_ref(root, test_file, sym_name)
            if ok_ref:
                verified_pass_refs.append(detail)
            else:
                item_diags.append(_diag(
                    codec.ReasonCode.UNRESOLVED_REFERENCE,
                    codec.Stage.REFERENCE,
                    cid,
                    f"existing pass test evidence {test_file}::{sym_name}",
                    detail,
                    test_file,
                ))

        for test_file, sym_name in spec["fail_evidence_refs"]:
            ok_ref, detail = _verify_test_evidence_ref(root, test_file, sym_name)
            if ok_ref:
                verified_fail_refs.append(detail)
            else:
                item_diags.append(_diag(
                    codec.ReasonCode.UNRESOLVED_REFERENCE,
                    codec.Stage.REFERENCE,
                    cid,
                    f"existing fail/negative test evidence {test_file}::{sym_name}",
                    detail,
                    test_file,
                ))

        if item_diags:
            status = "blocked"
        elif not runtime_applicable:
            status = "not_applicable"
        else:
            status = "passed"
        diagnostics.extend(item_diags)
        row = {
            "consumer_id": cid,
            "group": group,
            "entrypoint_kind": spec["entrypoint_kind"],
            "runtime_gate_applicable": runtime_applicable,
            "module_path": mod_path,
            "symbol": symbol,
            "sha256": sha,
            "actual_read_paths": list(spec["actual_read_paths"]),
            "actual_write_paths": list(spec["actual_write_paths"]),
            "public_contracts_used": public_contracts,
            "shared_task_multi_scope_supported": shared_task_supported,
            "valid_input_contract": spec["valid_input_contract"],
            "pass_evidence_refs": verified_pass_refs,
            "fail_evidence_refs": verified_fail_refs,
            "status": status,
            "remaining_epic5_items": list(spec["remaining_epic5_items"]),
            "diagnostics": item_diags,
        }
        entries.append(row)
        if group in group_map:
            group_map[group].append(row)

    # Verify 100% of _b_route_inventory.GROUPS (path, symbol) pairs are covered!
    registered_pairs = {(r["module_path"], r["symbol"]) for r in entries}
    registered_paths = {r["module_path"] for r in entries}
    expected_inventory_pairs: list[tuple[str, str | None]] = [
        (p, s)
        for _g, _d, _a, _e, pairs in inventory.GROUPS
        for p, s in pairs
    ]
    missing_inventory_pairs = [
        {"path": p, "symbol": s}
        for p, s in expected_inventory_pairs
        if (s is not None and (p, s) not in registered_pairs) or (s is None and p not in registered_paths)
    ]
    if missing_inventory_pairs:
        diagnostics.append(_diag(
            codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
            codec.Stage.BUNDLE,
            "inventory_groups_coverage",
            f"all {len(expected_inventory_pairs)} (path, symbol) entries from _b_route_inventory.GROUPS",
            {"missing_inventory_entries": missing_inventory_pairs},
            None,
        ))

    missing_groups = [g for g in group_names if not group_map.get(g)]
    if missing_groups:
        diagnostics.append(_diag(
            codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
            codec.Stage.BUNDLE,
            "consumer_matrix",
            list(group_names),
            {"missing_groups": missing_groups},
            None,
        ))

    passed_count = sum(1 for row in entries if row["status"] == "passed")
    blocked_count = sum(1 for row in entries if row["status"] == "blocked")
    na_count = sum(1 for row in entries if row["status"] == "not_applicable")
    direct_count = sum(1 for row in entries if row["entrypoint_kind"] == "direct_script" and row["status"] == "passed")
    shared_task_count = sum(1 for row in entries if row["shared_task_multi_scope_supported"] and row["status"] == "passed")

    group_summary = {
        g: {
            "total": len(rows),
            "passed": sum(1 for r in rows if r["status"] == "passed"),
            "blocked": sum(1 for r in rows if r["status"] == "blocked"),
            "not_applicable": sum(1 for r in rows if r["status"] == "not_applicable"),
            "consumer_ids": [r["consumer_id"] for r in rows],
        }
        for g, rows in group_map.items()
    }

    return {
        "ok": blocked_count == 0 and not missing_groups and not missing_inventory_pairs,
        "summary_only_claim_rejected": True,
        "groups_expected": len(group_names),
        "groups_covered": sum(1 for g in group_names if group_map.get(g)),
        "inventory_entries_expected": len(expected_inventory_pairs),
        "inventory_entries_covered": len(expected_inventory_pairs) - len(missing_inventory_pairs),
        "total_consumers": len(entries),
        "passed_count": passed_count,
        "blocked_count": blocked_count,
        "not_applicable_count": na_count,
        "direct_underlying_scripts_verified": direct_count,
        "shared_task_multi_scope_consumers_verified": shared_task_count,
        "group_summary": group_summary,
        "consumers": entries,
        "diagnostics": diagnostics,
    }


def _encoded_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _put_file(root: Path, rel: str, data: bytes | str) -> bytes:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    dest = root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    return raw


def _typed_ref(path: str, schema_version: str, entity_id: str, revision: int, raw: bytes) -> dict[str, Any]:
    return {
        "path": path,
        "schema_version": schema_version,
        "entity_id": entity_id,
        "revision": revision,
        "digest": codec.raw_digest(raw),
        "verification_mode": "raw",
        "codec_version": None,
    }


def _owned_ref(owner: str, ref: str, files: list[tuple[str, bytes]]) -> dict[str, Any]:
    return {
        "owner": owner,
        "ref": ref,
        "files": [{"path": p, "raw_digest": codec.raw_digest(raw)} for p, raw in files],
    }


def _probe_four_parts() -> list[dict[str, Any]]:
    return [
        {
            "kind": kind,
            "applicability": "applicable" if applicable else "not_applicable",
            "rationale": desc,
            "responsibilities": [desc] if applicable else [],
        }
        for kind, applicable, desc in (
            ("domain_rules", True, "Deterministic core domain logic."),
            ("csharp_adapter", True, "Thin C# command adapter."),
            ("binding", True, "Contract and event bindings."),
            ("scene", False, "No scene needed for this synthetic probe."),
        )
    ]


def _probe_flow(flow_id: str, req_ids: list[str]) -> dict[str, Any]:
    return {
        "id": flow_id,
        "requirement_ids": req_ids,
        "entry": f"enter:{flow_id}",
        "entry_condition": f"ready:{flow_id}",
        "success_end": f"done:{flow_id}",
        "branches": [
            {"kind": "failure", "rationale": "Reject invalid command.", "description": "Abort cleanly."},
            {"kind": "cancel", "rationale": "Allow cancel.", "description": "Return safely."},
            {"kind": "return", "rationale": "Return to caller.", "description": "Exit flow."},
        ],
        "handoffs": [],
        "state_owners": [],
        "parts": _probe_four_parts(),
        "observable_result": f"observed:{flow_id}",
        "verification_targets": [f"verify:{flow_id}"],
        "loops": [],
    }


def _build_minimal_committed_b_repo(
    tmp_root: Path,
    source_root: Path,
    *,
    include_task_bindings: bool = True,
    multi_plan_shared_task: bool = True,
    include_non_flow_req: bool = True,
    frozen_a_scope_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Materialize a minimal schema-valid committed B-route repo (zero logs/** needed)."""
    adr_rel = task_resolver.ADR_0040
    adr_raw = _put_file(tmp_root, adr_rel, _safe_read_bytes(source_root, adr_rel, allow_logs=False))

    schemas_dir, schemas_err = _safe_dir_ready(source_root, "docs/planning/b-route/schemas")
    if schemas_err is not None:
        raise ValueError(f"Unsafe schemas directory: {schemas_err['actual']}")
    if schemas_dir is not None:
        for schema_file in sorted(schemas_dir.glob("*.schema.json")):
            rel_s = f"docs/planning/b-route/schemas/{schema_file.name}"
            _put_file(tmp_root, rel_s, _safe_read_bytes(source_root, rel_s, allow_logs=False))
    excl_rel = "knowledge/policies/source-exclusions.v1.json"
    excl_ok, _, _ = _safe_existing_file(source_root, excl_rel, allow_logs=False)
    if excl_ok:
        _put_file(tmp_root, excl_rel, _safe_read_bytes(source_root, excl_rel, allow_logs=False))

    gdd_rel = "docs/gdd/probe-domain.md"
    gdd_raw = _put_file(tmp_root, gdd_rel, "# Probe Domain\n\nDeterministic probe source.\n")
    other_v_rel = "docs/testing/probe-static-check.md"
    other_v_raw = _put_file(tmp_root, other_v_rel, "# Probe Static Verification\n\nDeterministic non-flow rule.\n")
    manifest_rel = "docs/planning/sources/probe-manifest.json"
    ledger_rel = "docs/planning/sources/probe-ledger.json"
    proof_rel = "docs/planning/sources/probe-proof.json"
    gdd_dg = codec.raw_digest(gdd_raw)
    manifest_raw = _put_file(tmp_root, manifest_rel, _encoded_json({
        "schema_version": "chapter3.source-manifest.v1",
        "source_revision": "probe-rev-1",
        "manifest_sha256": gdd_dg,
        "sources": [{"path": gdd_rel, "raw_digest": gdd_dg}],
    }))
    ledger_raw = _put_file(tmp_root, ledger_rel, _encoded_json({
        "schema_version": "chapter3.source-blocks.v1",
        "source_revision": "probe-rev-1",
        "source_manifest_sha256": gdd_dg,
        "blocks": [
            {"block_id": "BLK-P-1", "path": gdd_rel},
            {"block_id": "BLK-P-2", "path": gdd_rel},
            {"block_id": "BLK-P-NF", "path": gdd_rel},
        ],
    }))
    proof_raw = _put_file(tmp_root, proof_rel, _encoded_json({"schema_version": "probe.proof.v1", "verdict": "approved"}))

    m_ref = _owned_ref("source_manifest", manifest_rel, [(manifest_rel, manifest_raw)])
    l_ref = _owned_ref("source_ledger", ledger_rel, [(ledger_rel, ledger_raw)])
    p_ref = _owned_ref("planning_proof", proof_rel, [(proof_rel, proof_raw)])
    ov_ref = _owned_ref("other_verification", other_v_rel, [(other_v_rel, other_v_raw)])
    src_ref = _owned_ref("authority", gdd_rel, [(gdd_rel, gdd_raw)])

    master_tasks = [
        {"id": 101, "title": "Shared Probe Task", "status": "pending", "dependencies": []},
        {"id": 201, "title": "Frozen A Probe Task", "status": "pending", "dependencies": []},
        {"id": 202, "title": "Unregistered Task", "status": "pending", "dependencies": []},
    ]
    back_tasks = [
        {"id": "NG-0101", "taskmaster_id": 101, "title": "Shared Probe Task", "status": "pending"},
        {"id": "NG-0201", "taskmaster_id": 201, "title": "Frozen A Probe Task", "status": "pending"},
        {"id": "NG-0202", "taskmaster_id": 202, "title": "Unregistered Task", "status": "pending"},
    ]
    _put_file(tmp_root, task_resolver.TRIPLET["master"], _encoded_json({"master": {"tasks": master_tasks}}))
    _put_file(tmp_root, task_resolver.TRIPLET["back"], _encoded_json(back_tasks))
    _put_file(tmp_root, task_resolver.TRIPLET["gameplay"], _encoded_json([]))

    frozen_a_refs: list[dict[str, Any]] = []
    if frozen_a_scope_ids:
        scope_rel = task_resolver.CHAPTER3_TASK_SCOPE
        scope_raw = _put_file(tmp_root, scope_rel, _encoded_json({
            "schema_version": "chapter3.task-scope.v1",
            "mode": "reconcile-existing-only",
            "master_path": task_resolver.TRIPLET["master"],
            "expected_master_task_count": len(master_tasks),
            "allowed_numeric_task_ids": list(frozen_a_scope_ids),
        }))
        frozen_a_refs.append(_owned_ref("authority", scope_rel, [(scope_rel, scope_raw)]))

    def _make_plan(plan_id: str, flow_id: str, req_id: str, blk_id: str, *, with_non_flow: bool = False) -> dict[str, Any]:
        reqs = [{
            "requirement_id": req_id,
            "source_block_ids": [blk_id],
            "acceptance_intent": f"Deliver {req_id}.",
            "non_task_sinks": [],
        }]
        rv = [{
            "requirement_id": req_id,
            "disposition": "flow",
            "flow_id": flow_id,
            "rationale": f"Covered by {flow_id}.",
            "sink_id": None,
            "verification_ref": None,
            "authority_ref": None,
            "evidence_ids": [],
        }]
        ev_refs: list[dict[str, Any]] = []
        app = [{
            "requirement_id": req_id,
            "disposition": "flow",
            "rationale": f"Covered by {flow_id}.",
            "other_verification_refs": [],
        }]
        if with_non_flow:
            reqs.append({
                "requirement_id": "REQ-NONFLOW-PROBE",
                "source_block_ids": ["BLK-P-NF"],
                "acceptance_intent": "Static non-flow invariant.",
                "non_task_sinks": ["static-probe-check"],
            })
            rv.append({
                "requirement_id": "REQ-NONFLOW-PROBE",
                "disposition": "other_verification",
                "flow_id": None,
                "rationale": "Verified by deterministic static check.",
                "sink_id": "static-probe-check",
                "verification_ref": other_v_rel,
                "authority_ref": None,
                "evidence_ids": [],
            })
            ev_refs.append(ov_ref)
            app.append({
                "requirement_id": "REQ-NONFLOW-PROBE",
                "disposition": "other_verification",
                "rationale": "Verified by deterministic static check.",
                "other_verification_refs": [ov_ref],
            })
        return {
            "schema_version": "newrouge.b-route-plan.v1",
            "plan_id": plan_id,
            "revision": 1,
            "source_identity": {
                "manifest_ref": m_ref,
                "ledger_ref": l_ref,
                "source_revision": "probe-rev-1",
                "source_manifest_digest": gdd_dg,
            },
            "requirements": reqs,
            "definitions": {"flows": [_probe_flow(flow_id, [req_id])], "commands": [], "states": []},
            "logical_references": [],
            "requirement_verification": rv,
            "requirement_route_memberships": [{"requirement_id": req_id, "flow_id": flow_id, "observable_role": "primary"}],
            "requirement_evidence": [],
            "evidence_source_refs": ev_refs,
            "coverage_table": [{k: v for k, v in row.items() if k != "evidence_ids"} for row in rv],
            "applicability": app,
            "adoption_proof_refs": [p_ref],
            "lineage": {"previous_plan_ref": None, "change_summary": f"Probe {plan_id}.", "identity_alignment": []},
        }

    plans_spec: list[tuple[str, dict[str, Any]]] = [
        ("docs/planning/b-route/plans/plan-alpha/1.json",
         _make_plan("plan-alpha", "flow-alpha", "REQ-ALPHA-1", "BLK-P-1", with_non_flow=include_non_flow_req)),
    ]
    if multi_plan_shared_task:
        plans_spec.append((
            "docs/planning/b-route/plans/plan-beta/1.json",
            _make_plan("plan-beta", "flow-beta", "REQ-BETA-1", "BLK-P-2", with_non_flow=False),
        ))

    policy_doc = {
        "schema_version": "newrouge.b-route-policy.v1",
        "policy_id": "policy-probe",
        "policy_revision": 1,
        "switch_boundary": {
            "default_route": "A",
            "a_write_allowed": True,
            "allowed_a_operations": ["implement", "resume", "route"],
            "authority_refs": [_owned_ref("adr", adr_rel, [(adr_rel, adr_raw)])],
        },
        "frozen_a_refs": frozen_a_refs,
    }
    policy_raw = _put_file(tmp_root, task_resolver.POLICY_PATH, _encoded_json(policy_doc))
    policy_ref = _typed_ref(task_resolver.POLICY_PATH, "newrouge.b-route-policy.v1", "policy-probe", 1, policy_raw)

    plan_refs: dict[str, dict[str, Any]] = {}
    plan_raws: dict[str, bytes] = {}
    definition_owners: list[dict[str, Any]] = []
    for rel, pdoc in plans_spec:
        raw = _put_file(tmp_root, rel, _encoded_json(pdoc))
        plan_raws[rel] = raw
        pref = _typed_ref(rel, "newrouge.b-route-plan.v1", pdoc["plan_id"], 1, raw)
        plan_refs[rel] = pref
        for flow in pdoc["definitions"]["flows"]:
            definition_owners.append({"kind": "flow", "definition_id": flow["id"], "plan_ref": pref})

    binding_refs: dict[str, dict[str, Any]] = {}
    binding_raws: dict[str, bytes] = {}
    if include_task_bindings:
        for rel, pdoc in plans_spec:
            pid = pdoc["plan_id"]
            fid = pdoc["definitions"]["flows"][0]["id"]
            rid = pdoc["requirements"][0]["requirement_id"]
            brel = f"docs/planning/b-route/bindings/{pid}/1.json"
            bdoc = {
                "schema_version": "newrouge.b-route-binding.v1",
                "plan_id": pid,
                "binding_revision": 1,
                "plan_ref": plan_refs[rel],
                "stage": "3C",
                "task_mappings": [{
                    "task_id": 101,
                    "view_refs": [{"view": "back", "business_id": "NG-0101"}],
                    "requirement_ids": [rid],
                    "flow_ids": [fid],
                    "part_kinds": ["domain_rules"],
                    "roles": ["producer"],
                    "obligation_ids": [],
                }],
                "parts": _probe_four_parts(),
                "implementation_objects": [],
                "obligations": [],
                "manifest_refs": [],
                "other_verification_refs": [ov_ref] if (pid == "plan-alpha" and include_non_flow_req) else [],
            }
            braw = _put_file(tmp_root, brel, _encoded_json(bdoc))
            binding_raws[brel] = braw
            binding_refs[brel] = _typed_ref(brel, "newrouge.b-route-binding.v1", pid, 1, braw)

    origins_tasks = (
        [{
            "task_id": 101,
            "source_refs": [src_ref],
            "plan_refs": list(plan_refs.values()),
            "binding_refs": list(binding_refs.values()),
        }]
        if include_task_bindings
        else []
    )
    origins_doc = {
        "schema_version": "newrouge.b-route-origins.v1",
        "origins_id": "task-origins",
        "revision": 1,
        "tasks": origins_tasks,
        "frozen_legacy_refs": [],
    }
    origins_raw = _put_file(tmp_root, task_resolver.ORIGINS_PATH, _encoded_json(origins_doc))
    origins_ref = _typed_ref(task_resolver.ORIGINS_PATH, "newrouge.b-route-origins.v1", "task-origins", 1, origins_raw)

    targets = []
    for rel, raw in [
        (task_resolver.POLICY_PATH, policy_raw),
        (task_resolver.ORIGINS_PATH, origins_raw),
        *plan_raws.items(),
        *binding_raws.items(),
    ]:
        dg = codec.raw_digest(raw)
        targets.append({
            "path": rel,
            "before_digest": None,
            "after_digest": dg,
            "projection_digest": dg,
            "verification_mode": "immutable_bytes",
            "codec_version": None,
        })

    op_id = "op-probe-alignment-001"
    receipt_rel = f"docs/planning/b-route/commits/{op_id}.json"
    receipt_doc = {
        "schema_version": "newrouge.b-route-commit.v1",
        "operation_id": op_id,
        "revision": 1,
        "operation_digest": codec.canonical_digest({"op": op_id}),
        "scopes": ["scope-probe"],
        "authority": [
            {"path": manifest_rel, "before_digest": codec.raw_digest(manifest_raw), "after_digest": codec.raw_digest(manifest_raw)},
            {"path": ledger_rel, "before_digest": codec.raw_digest(ledger_raw), "after_digest": codec.raw_digest(ledger_raw)},
            {"path": proof_rel, "before_digest": codec.raw_digest(proof_raw), "after_digest": codec.raw_digest(proof_raw)},
        ],
        "targets": targets,
        "plan_refs": list(plan_refs.values()),
        "binding_refs": list(binding_refs.values()),
        "resolved_definitions": [],
        "result": {"target_paths": [row["path"] for row in targets], "scope_ids": ["scope-probe"]},
    }
    receipt_raw = _put_file(tmp_root, receipt_rel, _encoded_json(receipt_doc))
    receipt_ref = _typed_ref(receipt_rel, "newrouge.b-route-commit.v1", op_id, 1, receipt_raw)

    catalog_doc = {
        "schema_version": "newrouge.b-route-catalog.v1",
        "catalog_id": "catalog",
        "revision": 1,
        "policy_ref": policy_ref,
        "origins_ref": origins_ref,
        "scope_heads": [{
            "scope_id": "scope-probe",
            "plan_refs": list(plan_refs.values()),
            "binding_refs": list(binding_refs.values()),
            "receipt_ref": receipt_ref,
        }],
        "definition_owners": definition_owners,
        "task_index": [
            {"task_id": row["task_id"], "plan_refs": row["plan_refs"], "binding_refs": row["binding_refs"]}
            for row in origins_tasks
        ],
    }
    catalog_raw = _put_file(tmp_root, task_resolver.CATALOG_PATH, _encoded_json(catalog_doc))
    return {
        "plans": plans_spec,
        "plan_refs": plan_refs,
        "binding_refs": binding_refs,
        "policy_doc": policy_doc,
        "catalog_doc": catalog_doc,
        "catalog_raw": catalog_raw,
        "receipt_ref": receipt_ref,
        "receipt_rel": receipt_rel,
        "manifest_rel": manifest_rel,
    }


def _validate_probe_bundle(tmp_root: Path) -> records.BundleValidation:
    bundle_map = {
        p.relative_to(tmp_root).as_posix(): p.read_bytes()
        for p in (tmp_root / "docs/planning/b-route").rglob("*.json")
        if "schemas/" not in p.relative_to(tmp_root).as_posix()
    }
    task_join = records.TaskJoinContext(
        master=codec.strict_json_loads((tmp_root / task_resolver.TRIPLET["master"]).read_bytes()),
        back=codec.strict_json_loads((tmp_root / task_resolver.TRIPLET["back"]).read_bytes()),
        gameplay=codec.strict_json_loads((tmp_root / task_resolver.TRIPLET["gameplay"]).read_bytes()),
    )
    return records.validate_bundle(bundle_map, root=tmp_root, task_join=task_join)


def _audit_five_state_and_migration(root: Path, *, probe_temp_contracts: bool) -> dict[str, Any]:
    """AC-2: Live five-state version contract probes, anti-downgrade, and migration doc audit."""
    diagnostics: list[dict[str, Any]] = []
    probes: dict[str, dict[str, Any]] = {}

    migration_doc_ok = True
    missing_sections: list[str] = []
    try:
        mig_raw = _safe_read_bytes(root, MIGRATION_DOC_PATH, allow_logs=False)
        mig_text = mig_raw.decode("utf-8-sig")
        for sec in MIGRATION_REQUIRED_SECTIONS:
            if sec not in mig_text:
                missing_sections.append(sec)
        if missing_sections:
            migration_doc_ok = False
            diagnostics.append(_diag(
                codec.ReasonCode.MISSING_REQUIRED_FIELD,
                codec.Stage.CONTENT,
                MIGRATION_DOC_PATH,
                list(MIGRATION_REQUIRED_SECTIONS),
                {"missing_sections": missing_sections},
                MIGRATION_DOC_PATH,
            ))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        migration_doc_ok = False
        diagnostics.append(_diag(
            _classify_read_exc(exc),
            codec.Stage.PATH,
            MIGRATION_DOC_PATH,
            "format migration documentation with input/output/identity/recovery contracts",
            str(exc)[:200],
            MIGRATION_DOC_PATH,
        ))

    if not probe_temp_contracts:
        diagnostics.append(_diag(
            codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
            codec.Stage.BUNDLE,
            "probe:live_probes_skipped",
            "live five-state version contract and anti-downgrade probes executed",
            "skip_live_probes",
            None,
        ))
        return {
            "ok": False,
            "live_probes_executed": False,
            "legacy_a_bounded_to_frozen_scope": False,
            "anti_downgrade_verified": False,
            "migration_doc": {
                "path": MIGRATION_DOC_PATH,
                "ok": migration_doc_ok,
                "missing_sections": missing_sections,
            },
            "states": {},
            "diagnostics": diagnostics,
        }

    with tempfile.TemporaryDirectory(prefix="nr-b-align-probes-") as tmpdir:
        tmp_base = Path(tmpdir)

        # State 1: new_b_format (valid v1 records + shared Task across 2 plans)
        b_root = tmp_base / "new_b"
        b_root.mkdir()
        built = _build_minimal_committed_b_repo(
            b_root, root, include_task_bindings=True, multi_plan_shared_task=True,
        )
        plan_path, plan_doc = built["plans"][0]
        rec_val = records.validate_record(plan_doc, path=plan_path)
        bundle_val = _validate_probe_bundle(b_root)
        origin_b = task_resolver.resolve_task_origin(b_root, 101, operation="implement")
        applicable_plans = origin_b.get("applicable_plans") or origin_b.get("plan_refs") or []
        state_new_ok = (
            bool(rec_val.ok)
            and bool(bundle_val.ok)
            and origin_b.get("ok") is True
            and origin_b.get("route") == "B"
            and len(applicable_plans) == 2
            and origin_b.get("runtime_verified") is False
            and origin_b.get("default_b_enabled") is False
        )
        probes["new_b_format"] = {
            "ok": state_new_ok,
            "route": origin_b.get("route"),
            "shared_task_applicable_plan_count": len(applicable_plans),
            "runtime_verified": origin_b.get("runtime_verified"),
            "default_b_enabled": origin_b.get("default_b_enabled"),
        }
        if not state_new_ok:
            diagnostics.append(_diag(
                codec.ReasonCode.CONFLICT,
                codec.Stage.BUNDLE,
                "probe:new_b_format",
                "valid v1 B-route bundle with shared Task route=B and 2 applicable plans",
                probes["new_b_format"],
                None,
            ))

        # State 2: legacy_a_format (explicit_not_enabled_a + policy.v1.json frozen_a_refs enforcement)
        not_en_root = tmp_base / "legacy_not_enabled"
        not_en_root.mkdir()
        _put_file(not_en_root, task_resolver.ADR_0040, _safe_read_bytes(root, task_resolver.ADR_0040, allow_logs=False))
        _put_file(not_en_root, task_resolver.TRIPLET["master"], _encoded_json({
            "master": {"tasks": [{"id": 1, "title": "Legacy Task", "status": "pending", "dependencies": []}]},
        }))
        _put_file(not_en_root, task_resolver.TRIPLET["back"], _encoded_json([
            {"id": "NG-0001", "taskmaster_id": 1, "title": "Legacy Task", "status": "pending"},
        ]))
        _put_file(not_en_root, task_resolver.TRIPLET["gameplay"], _encoded_json([]))
        origin_not_en = task_resolver.resolve_task_origin(not_en_root, 1, operation="implement")

        # Policy with explicit frozen_a_refs restricting legacy A to Task 201 only -> Task 202 must block!
        frozen_policy_root = tmp_base / "frozen_a_policy"
        frozen_policy_root.mkdir()
        _build_minimal_committed_b_repo(
            frozen_policy_root,
            root,
            include_task_bindings=True,
            multi_plan_shared_task=False,
            frozen_a_scope_ids=[201],
        )
        origin_outside_frozen = task_resolver.resolve_task_origin(frozen_policy_root, 202, operation="implement")
        origin_unreg = task_resolver.resolve_task_origin(b_root, 202, operation="implement")
        origin_forbid_op = task_resolver.resolve_task_origin(b_root, 202, operation="replan")
        scope_ids = chapter3_task_scope.allowed_ids({
            "schema_version": "chapter3.task-scope.v1",
            "mode": "reconcile-existing-only",
            "master_path": task_resolver.TRIPLET["master"],
            "expected_master_task_count": 1,
            "allowed_numeric_task_ids": [1],
        })
        legacy_a_ok = (
            origin_not_en.get("ok") is True
            and origin_not_en.get("route") == "explicit_not_enabled_a"
            and origin_outside_frozen.get("ok") is False
            and origin_outside_frozen.get("route") == "blocked"
            and origin_unreg.get("ok") is False
            and origin_unreg.get("route") == "blocked"
            and origin_forbid_op.get("ok") is False
            and origin_forbid_op.get("route") == "blocked"
            and scope_ids == {1}
        )
        probes["legacy_a_format"] = {
            "ok": legacy_a_ok,
            "explicit_not_enabled_route": origin_not_en.get("route"),
            "outside_frozen_a_refs_route": origin_outside_frozen.get("route"),
            "unbounded_non_frozen_route": origin_unreg.get("route"),
            "forbidden_a_op_route": origin_forbid_op.get("route"),
            "legacy_a_bounded_to_frozen_scope": legacy_a_ok,
        }
        if not legacy_a_ok:
            diagnostics.append(_diag(
                codec.ReasonCode.CONFLICT,
                codec.Stage.BUNDLE,
                "probe:legacy_a_format",
                "explicit_not_enabled_a for clean A repo and blocked for tasks outside frozen_a_refs",
                probes["legacy_a_format"],
                None,
            ))

        # State 3: legal_absence (pre-3C no-Task 3B adoption + legal non-Flow with rationale & refs)
        pre3c_root = tmp_base / "pre_3c"
        pre3c_root.mkdir()
        built_3b = _build_minimal_committed_b_repo(
            pre3c_root, root, include_task_bindings=False, multi_plan_shared_task=False, include_non_flow_req=True,
        )
        proj_3b = projection.build_b_route_knowledge_projection(pre3c_root, mode="workspace_preview")
        proj_3b_text = json.dumps(proj_3b, ensure_ascii=True)
        ch6_3b = ch6_gate.evaluate_chapter6_gate(pre3c_root, 101)

        bad_nf_no_rationale = copy.deepcopy(built_3b["plans"][0][1])
        for row in bad_nf_no_rationale["applicability"]:
            if row["disposition"] == "other_verification":
                row["rationale"] = ""
        res_no_rat = records.validate_record(bad_nf_no_rationale, path=built_3b["plans"][0][0])

        bad_nf_no_refs = copy.deepcopy(built_3b["plans"][0][1])
        for row in bad_nf_no_refs["applicability"]:
            if row["disposition"] == "other_verification":
                row["other_verification_refs"] = []
        res_no_refs = records.validate_record(bad_nf_no_refs, path=built_3b["plans"][0][0])

        legal_abs_ok = (
            proj_3b.get("ok") is True
            and "3b_adopted_awaiting_3c" in proj_3b_text
            and ch6_3b.get("ok") is False
            and not res_no_rat.ok
            and not res_no_refs.ok
        )
        probes["legal_absence"] = {
            "ok": legal_abs_ok,
            "pre_3c_projection_ok": proj_3b.get("ok"),
            "pre_3c_marker_present": "3b_adopted_awaiting_3c" in proj_3b_text,
            "pre_3c_ch6_blocked": ch6_3b.get("ok") is False,
            "non_flow_missing_rationale_rejected": not res_no_rat.ok,
            "non_flow_missing_refs_rejected": not res_no_refs.ok,
        }
        if not legal_abs_ok:
            diagnostics.append(_diag(
                codec.ReasonCode.SEMANTIC_ERROR,
                codec.Stage.SCHEMA,
                "probe:legal_absence",
                "pre-3C allowed in projection without inventing Tasks; non-Flow requires rationale + other_verification_refs",
                probes["legal_absence"],
                None,
            ))

        # State 4: corrupted_input (truncated JSON, NaN, duplicate key, digest tamper)
        corrupt_codes: dict[str, str | None] = {}
        for label, payload in (
            ("truncated", b'{"schema_version":'),
            ("nan", b'{"value": NaN}'),
            ("duplicate_key", b'{"a": 1, "a": 2}'),
        ):
            try:
                codec.strict_json_loads(payload)
                corrupt_codes[label] = None
            except codec.CodecError as err:
                corrupt_codes[label] = err.diagnostic.reason_code.value

        tamper_root = tmp_base / "tamper"
        shutil.copytree(b_root, tamper_root)
        target_plan = tamper_root / plan_path
        target_plan.write_bytes(target_plan.read_bytes() + b" ")
        origin_tampered = task_resolver.resolve_task_origin(tamper_root, 101, operation="implement")
        tamper_codes = [d.get("reason_code") for d in origin_tampered.get("diagnostics", [])]
        corrupt_ok = (
            corrupt_codes["truncated"] == codec.ReasonCode.INVALID_JSON.value
            and corrupt_codes["nan"] == codec.ReasonCode.NON_FINITE_NUMBER.value
            and corrupt_codes["duplicate_key"] == codec.ReasonCode.DUPLICATE_KEY.value
            and origin_tampered.get("ok") is False
            and origin_tampered.get("route") == "blocked"
            and codec.ReasonCode.DIGEST_MISMATCH.value in tamper_codes
        )
        probes["corrupted_input"] = {
            "ok": corrupt_ok,
            "json_error_codes": corrupt_codes,
            "tampered_route": origin_tampered.get("route"),
            "tampered_reason_codes": tamper_codes,
        }
        if not corrupt_ok:
            diagnostics.append(_diag(
                codec.ReasonCode.INVALID_JSON,
                codec.Stage.DECODE,
                "probe:corrupted_input",
                "deterministic rejection of truncated/NaN/duplicate JSON and digest mismatch",
                probes["corrupted_input"],
                None,
            ))

        # State 5: unknown_schema_version (plan v999, catalog v999, verification-scope v999)
        bad_plan_ver = dict(plan_doc)
        bad_plan_ver["schema_version"] = "newrouge.b-route-plan.v999"
        res_bad_plan = records.validate_record(bad_plan_ver, path=plan_path)

        bad_cat_ver = dict(built["catalog_doc"])
        bad_cat_ver["schema_version"] = "newrouge.b-route-catalog.v999"
        res_bad_cat = records.validate_record(bad_cat_ver, path=task_resolver.CATALOG_PATH)

        bad_scope_res = verification_scope.validate_verification_scope(
            b_root, {"schema_version": "newrouge.b-route-verification-scope.v999"},
        )
        bad_scope_codes = {
            d.get("reason_code") for d in bad_scope_res.get("diagnostics", []) if isinstance(d, dict)
        }
        if isinstance(bad_scope_res.get("reason_code"), str):
            bad_scope_codes.add(bad_scope_res["reason_code"])
        unknown_ver_ok = (
            not res_bad_plan.ok
            and not res_bad_cat.ok
            and bad_scope_res.get("ok") is False
            and res_bad_plan.diagnostic.reason_code == codec.ReasonCode.UNKNOWN_SCHEMA
            and res_bad_cat.diagnostic.reason_code == codec.ReasonCode.UNKNOWN_SCHEMA
            and codec.ReasonCode.UNKNOWN_SCHEMA.value in bad_scope_codes
        )
        probes["unknown_schema_version"] = {
            "ok": unknown_ver_ok,
            "plan_v999_rejected": not res_bad_plan.ok,
            "catalog_v999_rejected": not res_bad_cat.ok,
            "scope_v999_rejected": bad_scope_res.get("ok") is False,
            "scope_v999_reason_codes": sorted(c for c in bad_scope_codes if c),
        }
        if not unknown_ver_ok:
            diagnostics.append(_diag(
                codec.ReasonCode.UNKNOWN_SCHEMA,
                codec.Stage.SCHEMA,
                "probe:unknown_schema_version",
                "deterministic rejection of unknown schema_version v999 with unknown_schema",
                probes["unknown_schema_version"],
                None,
            ))

        # Anti-downgrade probes: stripping origins, manifest, or commit trace MUST block!
        strip_origins_root = tmp_base / "strip_origins"
        shutil.copytree(b_root, strip_origins_root)
        (strip_origins_root / task_resolver.ORIGINS_PATH).unlink()
        origin_stripped = task_resolver.resolve_task_origin(strip_origins_root, 101, operation="implement")
        gate_stripped = ch6_gate.evaluate_chapter6_gate(strip_origins_root, 101)

        strip_manifest_root = tmp_base / "strip_manifest"
        shutil.copytree(b_root, strip_manifest_root)
        (strip_manifest_root / built["manifest_rel"]).unlink()
        origin_manifest_stripped = task_resolver.resolve_task_origin(strip_manifest_root, 101, operation="implement")
        gate_manifest_stripped = ch6_gate.evaluate_chapter6_gate(strip_manifest_root, 101)

        strip_trace_root = tmp_base / "strip_trace"
        shutil.copytree(b_root, strip_trace_root)
        (strip_trace_root / built["receipt_rel"]).unlink()
        origin_trace_stripped = task_resolver.resolve_task_origin(strip_trace_root, 101, operation="implement")
        gate_trace_stripped = ch6_gate.evaluate_chapter6_gate(strip_trace_root, 101)

        trace_only_root = tmp_base / "trace_only"
        trace_only_root.mkdir()
        _put_file(trace_only_root, task_resolver.ADR_0040, _safe_read_bytes(root, task_resolver.ADR_0040, allow_logs=False))
        _put_file(trace_only_root, task_resolver.TRIPLET["master"], _encoded_json({
            "master": {"tasks": [{"id": 101, "title": "Traced Task", "status": "pending", "dependencies": [], "plan_refs": ["plan-alpha"]}]},
        }))
        _put_file(trace_only_root, task_resolver.TRIPLET["back"], _encoded_json([
            {"id": "NG-0101", "taskmaster_id": 101, "title": "Traced Task", "status": "pending"},
        ]))
        _put_file(trace_only_root, task_resolver.TRIPLET["gameplay"], _encoded_json([]))
        origin_trace_only = task_resolver.resolve_task_origin(trace_only_root, 101, operation="implement")

        anti_downgrade_ok = (
            origin_stripped.get("ok") is False
            and origin_stripped.get("route") == "blocked"
            and gate_stripped.get("ok") is False
            and origin_manifest_stripped.get("ok") is False
            and origin_manifest_stripped.get("route") == "blocked"
            and gate_manifest_stripped.get("ok") is False
            and origin_trace_stripped.get("ok") is False
            and origin_trace_stripped.get("route") == "blocked"
            and gate_trace_stripped.get("ok") is False
            and origin_trace_only.get("ok") is False
            and origin_trace_only.get("route") == "blocked"
        )
        probes["anti_downgrade"] = {
            "ok": anti_downgrade_ok,
            "stripped_origins_route": origin_stripped.get("route"),
            "stripped_origins_gate_ok": gate_stripped.get("ok"),
            "stripped_manifest_route": origin_manifest_stripped.get("route"),
            "stripped_manifest_gate_ok": gate_manifest_stripped.get("ok"),
            "stripped_trace_route": origin_trace_stripped.get("route"),
            "stripped_trace_gate_ok": gate_trace_stripped.get("ok"),
            "residual_trace_without_governance_route": origin_trace_only.get("route"),
        }
        if not anti_downgrade_ok:
            diagnostics.append(_diag(
                codec.ReasonCode.CONFLICT,
                codec.Stage.BUNDLE,
                "probe:anti_downgrade",
                "stripping origins/manifest/trace must return blocked and never downgrade to legacy A",
                probes["anti_downgrade"],
                None,
            ))

    all_ok = migration_doc_ok and all(p.get("ok") is True for p in probes.values())
    return {
        "ok": all_ok,
        "live_probes_executed": True,
        "legacy_a_bounded_to_frozen_scope": bool(probes["legacy_a_format"]["ok"]),
        "anti_downgrade_verified": bool(probes["anti_downgrade"]["ok"]),
        "migration_doc": {
            "path": MIGRATION_DOC_PATH,
            "ok": migration_doc_ok,
            "missing_sections": missing_sections,
        },
        "states": probes,
        "diagnostics": diagnostics,
    }


def _collect_dev_cli_subparsers() -> dict[str, set[str]]:
    """Introspect real dev_cli.build_parser() subcommands and their registered flags."""
    import dev_cli

    parser = dev_cli.build_parser()
    result: dict[str, set[str]] = {}
    for action in parser._actions:
        if hasattr(action, "choices") and isinstance(action.choices, dict):
            for sub_name, sub_parser in action.choices.items():
                if not hasattr(sub_parser, "_actions"):
                    continue
                flags: set[str] = set()
                for sub_act in sub_parser._actions:
                    for opt in getattr(sub_act, "option_strings", ()):
                        flags.add(opt)
                result[str(sub_name)] = flags
    return result


# CJK-safe ASCII lookaround for bare ADR-0038 without full filename suffix.
_BARE_ADR_0038_RE = re.compile(
    r"(?<![A-Za-z0-9_-])ADR-0038(?!-(?:mvg-candidate-admission|semantic-delivery-topology)\.md)"
)
_MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)#\s]+)(?:#[^)]*)?\)")
# Match ALL dev_cli.py <subcommand> invocations across docs and Skills.
_DEV_CLI_CMD_RE = re.compile(r"dev_cli\.py\s+([a-z][a-z0-9-]*)([^\n`\"']*)")
_FLAG_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9_-])(--[a-z][a-z0-9-]*)")
_FORBIDDEN_FLAG_LINE_RE = re.compile(
    r"(?:禁止标志|拒绝|forbid|forbidden|must reject|never accept|rejects?\s+`?--)",
    re.IGNORECASE,
)
_FENCE_LINE_RE = re.compile(r"^\s*```")
_LITERAL_ESCAPED_NEWLINE_RE = re.compile(r"(?:```\\n|\\n\s*$)")


def _extract_adr_body_status(text: str) -> str:
    """Strictly parse ADR Status lines; preserve conflicts & unrecognized statuses (never as accepted)."""
    declarations: list[str] = []
    for _line_no, line in inventory.markdown_status_lines(text):
        match = re.match(r"^\s*(?:[-*]\s+)?(?:\*\*)?(?:status|状态)(?:\*\*)?\s*[:：]\s*(.+?)\s*$", line, re.I)
        if not match:
            continue
        raw_val = match[1].strip("*` ").casefold()
        token = re.fullmatch(
            r"(accepted|proposed|superseded|deprecated|rejected|draft)(?:\s*[（(][^）)]*[）)])?",
            raw_val,
        )
        if token:
            declarations.append(token[1])
        else:
            declarations.append("unrecognized")
    if not declarations:
        return "missing"
    states = set(declarations)
    if len(states) > 1:
        return "conflict"
    return next(iter(states))


def _check_workflow_md_immutability(root: Path) -> tuple[bool, list[dict[str, Any]]]:
    """Read-only verification of workflow.md: CRLF-normalized HEAD comparison + b-route injection scan."""
    diags: list[dict[str, Any]] = []
    mutated = False
    try:
        wf_raw = _safe_read_bytes(root, "workflow.md", allow_logs=False)
    except (OSError, ValueError) as exc:
        diags.append(_diag(
            _classify_read_exc(exc),
            codec.Stage.PATH,
            "workflow.md",
            "readable workflow.md without reparse",
            str(exc)[:200],
            "workflow.md",
        ))
        return False, diags

    wf_norm = wf_raw.replace(b"\r\n", b"\n")
    if b"b-route-consumer-alignment" in wf_norm:
        mutated = True
        diags.append(_diag(
            codec.ReasonCode.CONFLICT,
            codec.Stage.CONTENT,
            "workflow.md",
            "workflow.md must not contain injected b-route-consumer-alignment CLI commands",
            "b_route_cli_injected",
            "workflow.md",
        ))

    git_dir = root / ".git"
    if os.path.lexists(git_dir):
        try:
            proc = subprocess.run(
                ["git", "-C", str(root), "show", "HEAD:workflow.md"],
                capture_output=True,
                check=False,
                timeout=15,
            )
            if proc.returncode == 0:
                head_norm = proc.stdout.replace(b"\r\n", b"\n")
                if wf_norm != head_norm:
                    mutated = True
                    diags.append(_diag(
                        codec.ReasonCode.CONFLICT,
                        codec.Stage.CONTENT,
                        "workflow.md",
                        _sha256_bytes(head_norm),
                        {"disk_lf_sha256": _sha256_bytes(wf_norm), "reason": "workflow_md_mutated_vs_head"},
                        "workflow.md",
                    ))
        except (OSError, subprocess.SubprocessError) as exc:
            diags.append(_diag(
                codec.ReasonCode.READ_ERROR,
                codec.Stage.CONTENT,
                "workflow.md",
                "readable git HEAD:workflow.md",
                str(exc)[:200],
                "workflow.md",
            ))
    return mutated, diags


def _parse_adr_index_sections(index_text: str) -> list[tuple[str, str]]:
    """Split ADR_INDEX_GODOT.md into (heading, body) for EVERY '## ' section (including tail sections)."""
    sections: list[tuple[str, str]] = []
    cur_heading: str | None = None
    cur_lines: list[str] = []
    for line in index_text.splitlines():
        if line.startswith("## "):
            if cur_heading is not None:
                sections.append((cur_heading, "\n".join(cur_lines)))
            cur_heading = line[3:].strip()
            cur_lines = []
        elif cur_heading is not None:
            cur_lines.append(line)
    if cur_heading is not None:
        sections.append((cur_heading, "\n".join(cur_lines)))
    return sections


def _audit_docs_skills_and_adrs(root: Path) -> dict[str, Any]:
    """AC-3: Verify AGENTS.md, entrypoints, owning docs, Skills, 4 boundaries, workflow.md, and ADR status."""
    diagnostics: list[dict[str, Any]] = []
    subparsers = _collect_dev_cli_subparsers()

    b_route_owning_docs: list[str] = []
    wf_dir, wf_dir_err = _safe_dir_ready(root, "docs/workflows")
    if wf_dir_err is not None:
        diagnostics.append(wf_dir_err)
    elif wf_dir is not None:
        for item in sorted(wf_dir.glob("b-route-*.md")):
            b_route_owning_docs.append(f"docs/workflows/{item.name}")

    example_docs: list[str] = []
    ex_dir, ex_dir_err = _safe_dir_ready(root, "examples")
    if ex_dir_err is not None:
        diagnostics.append(ex_dir_err)
    elif ex_dir is not None:
        for item in sorted(ex_dir.rglob("*.md")):
            example_docs.append(item.relative_to(root).as_posix())

    checked_docs: list[str] = [
        "AGENTS.md",
        "docs/workflows/stable-public-entrypoints.md",
        "docs/workflows/script-entrypoints-index.md",
        "docs/workflows/mvg-integration-acceptance.md",
        *b_route_owning_docs,
        *GOVERNED_SKILLS,
        *example_docs,
    ]
    seen_docs: list[str] = []
    for doc_rel in checked_docs:
        if doc_rel not in seen_docs:
            seen_docs.append(doc_rel)

    broken_links: list[dict[str, str]] = []
    invalid_cli_flags: list[dict[str, Any]] = []
    bare_adr_0038_hits: list[dict[str, Any]] = []
    fence_errors: list[dict[str, Any]] = []
    per_skill_failures: list[dict[str, Any]] = []
    doc_texts: dict[str, str] = {}

    for doc_rel in seen_docs:
        try:
            raw = _safe_read_bytes(root, doc_rel, allow_logs=False)
            text = raw.decode("utf-8-sig")
            doc_texts[doc_rel] = text
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            diagnostics.append(_diag(
                _classify_read_exc(exc),
                codec.Stage.PATH,
                doc_rel,
                "readable UTF-8 governance doc or skill",
                str(exc)[:200],
                doc_rel,
            ))
            continue

        # 1. Verify markdown links resolve to real non-reparse repo files.
        base_dir = Path(doc_rel).parent
        for match in _MD_LINK_RE.finditer(text):
            href = match.group(1).strip()
            if not href or href.startswith(("http://", "https://", "mailto:", "file://", "#")):
                continue
            if any(ch in href for ch in ("<", ">", "*", "{", "}")):
                continue
            resolved_rel = Path(os.path.normpath((base_dir / href).as_posix())).as_posix()
            if resolved_rel.startswith(".."):
                broken_links.append({"doc": doc_rel, "link": href, "reason": "escapes_repo"})
                continue
            try:
                is_log_link = resolved_rel == "logs" or resolved_rel.startswith("logs/")
                target = inventory.safe_input(root, resolved_rel, allow_logs=is_log_link)
                observability._check_ancestors_no_reparse(root, target)
                if not is_log_link:
                    if not os.path.lexists(target):
                        broken_links.append({"doc": doc_rel, "link": href, "resolved": resolved_rel, "reason": "missing"})
                    else:
                        inventory.no_reparse(target)
            except (ValueError, OSError) as exc:
                broken_links.append({"doc": doc_rel, "link": href, "reason": str(exc)[:120]})

        # 2. Verify ALL documented dev_cli.py subcommands & flags against real argparse definitions.
        for line_no, line in enumerate(text.splitlines(), 1):
            if _FORBIDDEN_FLAG_LINE_RE.search(line):
                continue
            for cmd_match in _DEV_CLI_CMD_RE.finditer(line):
                sub_name = cmd_match.group(1)
                tail = cmd_match.group(2)
                if sub_name not in subparsers:
                    invalid_cli_flags.append({
                        "doc": doc_rel,
                        "line": line_no,
                        "subcommand": sub_name,
                        "reason": "unregistered_subcommand",
                    })
                    continue
                known_flags = subparsers[sub_name]
                segment = re.split(r"[;。；，]|&&|\|\|", tail, maxsplit=1)[0]
                for flag_match in _FLAG_TOKEN_RE.finditer(segment):
                    flag = flag_match.group(1)
                    if flag in ("--help", "--"):
                        continue
                    if flag not in known_flags:
                        invalid_cli_flags.append({
                            "doc": doc_rel,
                            "line": line_no,
                            "subcommand": sub_name,
                            "flag": flag,
                            "reason": "unknown_flag",
                        })

        # 3. Check for CJK-safe bare ADR-0038 across ALL scanned docs/skills/examples.
        for line_no, line in enumerate(text.splitlines(), 1):
            if _BARE_ADR_0038_RE.search(line):
                bare_adr_0038_hits.append({"doc": doc_rel, "line": line_no, "text": line.strip()[:160]})

        # 4. Verify code-fence balance and zero literal escaped '\n' artifacts on Skills and consumer alignment doc.
        if doc_rel in GOVERNED_SKILLS or doc_rel == MIGRATION_DOC_PATH:
            fence_count = sum(1 for ln in text.splitlines() if _FENCE_LINE_RE.match(ln))
            if fence_count % 2 != 0:
                fence_errors.append({"doc": doc_rel, "reason": "unbalanced_code_fence", "fence_lines": fence_count})
            for line_no, ln in enumerate(text.splitlines(), 1):
                if _LITERAL_ESCAPED_NEWLINE_RE.search(ln):
                    fence_errors.append({
                        "doc": doc_rel,
                        "line": line_no,
                        "reason": "literal_escaped_newline_artifact",
                        "text": ln.strip()[:120],
                    })

        # 5. Per-Skill mandatory boundary coverage (emptying/stripping ANY single Skill fails AC-3).
        if doc_rel in PER_SKILL_REQUIRED_TOKENS:
            missing_skill_tokens = [tok for tok in PER_SKILL_REQUIRED_TOKENS[doc_rel] if tok not in text]
            if not text.strip() or missing_skill_tokens:
                per_skill_failures.append({
                    "skill": doc_rel,
                    "empty": not bool(text.strip()),
                    "missing_tokens": missing_skill_tokens,
                })

    for item in broken_links:
        diagnostics.append(_diag(
            codec.ReasonCode.UNRESOLVED_REFERENCE,
            codec.Stage.REFERENCE,
            item["doc"],
            "resolvable repository link",
            item,
            item["doc"],
        ))
    for item in invalid_cli_flags:
        diagnostics.append(_diag(
            codec.ReasonCode.INVALID_ARGUMENT,
            codec.Stage.CONTENT,
            f"{item['doc']}::{item['subcommand']}",
            "registered dev_cli subcommand and argparse flag",
            item,
            item["doc"],
        ))
    for hit in bare_adr_0038_hits:
        diagnostics.append(_diag(
            codec.ReasonCode.INVALID_REFERENCE,
            codec.Stage.CONTENT,
            hit["doc"],
            "explicit full filenames ADR-0038-semantic-delivery-topology.md and ADR-0038-mvg-candidate-admission.md",
            hit,
            hit["doc"],
        ))
    for err in fence_errors:
        diagnostics.append(_diag(
            codec.ReasonCode.SEMANTIC_ERROR,
            codec.Stage.CONTENT,
            err["doc"],
            "balanced markdown code fences without literal escaped \\n artifacts",
            err,
            err["doc"],
        ))
    for fail in per_skill_failures:
        diagnostics.append(_diag(
            codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
            codec.Stage.CONTENT,
            fail["skill"],
            list(PER_SKILL_REQUIRED_TOKENS.get(fail["skill"], ())),
            fail,
            fail["skill"],
        ))

    # 6. Verify the 4 mandatory boundary distinctions across governed docs & skills.
    combined_gov_text = "\n".join(
        doc_texts.get(p, "")
        for p in ("AGENTS.md", MIGRATION_DOC_PATH, *GOVERNED_SKILLS)
    )
    boundaries = {
        "3A_3B_3C_vs_4_to_7_boundary": (
            "b-route-sources" in combined_gov_text
            and "b-route-adoption" in combined_gov_text
            and "b-route-task-compile" in combined_gov_text
            and "b-route-chapter4-binding" in combined_gov_text
            and "b-route-chapter6-gate" in combined_gov_text
            and "b-route-chapter7-slice" in combined_gov_text
        ),
        "model_resume_vs_journal_recovery_boundary": (
            "journal" in combined_gov_text.lower()
            and ("public-sync-journal" in combined_gov_text or "apply-journal.json" in combined_gov_text)
            and "resume" in combined_gov_text.lower()
        ),
        "task_vs_flow_vs_cumulative_milestone_completion_boundary": (
            "b-route-completion-verdict" in combined_gov_text
            and "full-MVG" in combined_gov_text
            and "b-route-verification-scope" in combined_gov_text
        ),
        "workspace_preview_attempt_vs_main_publication_boundary": (
            "workspace_preview" in combined_gov_text
            and "current.json" in combined_gov_text
            and "last-known-good.json" in combined_gov_text
            and "refs/heads/main" in combined_gov_text
        ),
    }
    for b_name, b_ok in boundaries.items():
        if not b_ok:
            diagnostics.append(_diag(
                codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
                codec.Stage.CONTENT,
                b_name,
                "explicit governance boundary distinction preserved in docs and skills",
                False,
                MIGRATION_DOC_PATH,
            ))

    # 7. Strict ADR status, full ADR_INDEX_GODOT.md section parsing, and dual ADR-0038 audit.
    adr_statuses: dict[str, str] = {}
    adr_anomalies: list[dict[str, str]] = []
    adr_dir, adr_dir_err = _safe_dir_ready(root, "docs/adr")
    if adr_dir_err is not None:
        diagnostics.append(adr_dir_err)
    elif adr_dir is not None:
        for adr_file in sorted(adr_dir.glob("ADR-*.md")):
            rel = f"docs/adr/{adr_file.name}"
            try:
                raw = _safe_read_bytes(root, rel, allow_logs=False)
                st = _extract_adr_body_status(raw.decode("utf-8-sig"))
                adr_statuses[rel] = st
                if st in {"conflict", "unrecognized", "missing"}:
                    adr_anomalies.append({"file": rel, "status": st})
                    diagnostics.append(_diag(
                        codec.ReasonCode.CONFLICT if st == "conflict" else codec.ReasonCode.SEMANTIC_ERROR,
                        codec.Stage.CONTENT,
                        rel,
                        "single recognized ADR status (Accepted/Proposed/Superseded/Deprecated/Rejected/Draft)",
                        st,
                        rel,
                    ))
            except (OSError, ValueError, UnicodeDecodeError) as exc:
                adr_statuses[rel] = "unreadable"
                adr_anomalies.append({"file": rel, "status": "unreadable"})
                diagnostics.append(_diag(
                    _classify_read_exc(exc),
                    codec.Stage.PATH,
                    rel,
                    "readable UTF-8 ADR file without reparse",
                    str(exc)[:200],
                    rel,
                ))

    dual_0038_present_list: list[str] = []
    for rel_38 in DUAL_ADR_0038_FILES:
        ok_38, code_38, msg_38 = _safe_existing_file(root, rel_38, allow_logs=False)
        if ok_38:
            dual_0038_present_list.append(rel_38)
        else:
            diagnostics.append(_diag(
                code_38 or codec.ReasonCode.FILE_NOT_FOUND,
                codec.Stage.PATH,
                rel_38,
                "existing non-reparse ADR-0038 file",
                msg_38,
                rel_38,
            ))
    dual_0038_present = len(dual_0038_present_list) == len(DUAL_ADR_0038_FILES)

    adr_0040_status = adr_statuses.get(task_resolver.ADR_0040, "missing")
    if adr_0040_status != "accepted":
        diagnostics.append(_diag(
            codec.ReasonCode.CONFLICT,
            codec.Stage.CONTENT,
            task_resolver.ADR_0040,
            "accepted",
            adr_0040_status,
            task_resolver.ADR_0040,
        ))

    proposed_misclassified: list[dict[str, str]] = []
    index_rel = "docs/architecture/ADR_INDEX_GODOT.md"
    accepted_sections_combined = ""
    parsed_index_sections: list[tuple[str, str]] = []
    try:
        index_text = _safe_read_bytes(root, index_rel, allow_logs=False).decode("utf-8-sig")
        parsed_index_sections = _parse_adr_index_sections(index_text)
        accepted_bodies = [
            body
            for heading, body in parsed_index_sections
            if ("accepted" in heading.casefold() or "已采纳" in heading)
            and "proposed" not in heading.casefold()
            and "待采纳" not in heading
        ]
        accepted_sections_combined = "\n".join(accepted_bodies)
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        diagnostics.append(_diag(
            _classify_read_exc(exc),
            codec.Stage.PATH,
            index_rel,
            "readable ADR_INDEX_GODOT.md",
            str(exc)[:200],
            index_rel,
        ))

    discovered_proposed_ids = {
        Path(rel).name.split("-", 2)[0] + "-" + Path(rel).name.split("-", 2)[1]
        for rel, st in adr_statuses.items()
        if st in {"proposed", "draft"} and len(Path(rel).name.split("-")) >= 2
    }
    body_proposed_set = set(BODY_PROPOSED_ADRS) | discovered_proposed_ids
    all_tracked_proposed = sorted(set(PROPOSED_ADRS) | body_proposed_set)

    for adr_id in all_tracked_proposed:
        if adr_id in body_proposed_set:
            matching_files = [p for p in adr_statuses if Path(p).name.startswith(adr_id + "-")]
            for rel in matching_files:
                if adr_statuses[rel] == "accepted":
                    proposed_misclassified.append({"adr": adr_id, "file": rel, "where": "adr_body", "status": "accepted"})
        if re.search(rf"(?<![A-Za-z0-9_-]){re.escape(adr_id)}(?![A-Za-z0-9_-])", accepted_sections_combined):
            proposed_misclassified.append({"adr": adr_id, "file": index_rel, "where": "adr_index_accepted_section", "status": "accepted"})

    # Also block any governed doc claiming a Proposed ADR is Accepted on the same line.
    accepted_claim_re = re.compile(r"(?:accepted|已采纳)", re.IGNORECASE)
    for doc_rel, text in doc_texts.items():
        if doc_rel == MIGRATION_DOC_PATH:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            if "proposed" in line.casefold() or "未采纳" in line or "绝不被当作" in line or "禁当" in line:
                continue
            if not accepted_claim_re.search(line):
                continue
            for adr_id in all_tracked_proposed:
                if re.search(rf"(?<![A-Za-z0-9_-]){re.escape(adr_id)}(?![A-Za-z0-9_-])", line):
                    proposed_misclassified.append({
                        "adr": adr_id,
                        "file": f"{doc_rel}:{line_no}",
                        "where": "governance_doc_accepted_claim",
                        "status": "accepted",
                    })

    for item in proposed_misclassified:
        diagnostics.append(_diag(
            codec.ReasonCode.CONFLICT,
            codec.Stage.CONTENT,
            item["adr"],
            "Proposed ADR must never be classified as Accepted",
            item,
            item["file"],
        ))

    # 8. Verify .github/workflows quality/branch protection workflows exist via safe_input + no_reparse.
    missing_workflows: list[str] = []
    for wf in REQUIRED_WORKFLOW_PROTECTIONS:
        ok_wf, code_wf, msg_wf = _safe_existing_file(root, wf, allow_logs=False)
        if not ok_wf:
            missing_workflows.append(wf)
            diagnostics.append(_diag(
                code_wf or codec.ReasonCode.FILE_NOT_FOUND,
                codec.Stage.PATH,
                wf,
                "existing non-reparse GitHub Actions quality/branch protection workflow",
                msg_wf,
                wf,
            ))

    # 9. Real workflow.md immutability check (read-only CRLF-normalized HEAD comparison + injection scan).
    workflow_md_mutated, wf_diags = _check_workflow_md_immutability(root)
    diagnostics.extend(wf_diags)

    return {
        "ok": len(diagnostics) == 0,
        "docs_checked_count": len(seen_docs),
        "skills_checked": list(GOVERNED_SKILLS),
        "broken_links": broken_links,
        "invalid_cli_flags": invalid_cli_flags,
        "bare_adr_0038_hits": bare_adr_0038_hits,
        "fence_errors": fence_errors,
        "per_skill_failures": per_skill_failures,
        "dual_adr_0038_present": dual_0038_present,
        "adr_0040_status": adr_0040_status,
        "adr_anomalies": adr_anomalies,
        "adr_index_sections_parsed": len(parsed_index_sections),
        "tracked_proposed_adrs": all_tracked_proposed,
        "proposed_adrs_misclassified_as_accepted": proposed_misclassified,
        "boundaries": boundaries,
        "workflow_protections_present": len(missing_workflows) == 0,
        "workflow_md_mutated": workflow_md_mutated,
        "diagnostics": diagnostics,
    }


def _iter_assignment_targets(node: ast.AST) -> list[tuple[str, ast.AST | None]]:
    """Extract (var_name, value_node) from both ast.Assign and ast.AnnAssign."""
    pairs: list[tuple[str, ast.AST | None]] = []
    if isinstance(node, ast.Assign):
        for target in node.targets:
            if isinstance(target, ast.Name):
                pairs.append((target.id, node.value))
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        pairs.append((node.target.id, node.value))
    return pairs


def _is_functional_enum_call(val: ast.AST | None) -> bool:
    if not isinstance(val, ast.Call):
        return False
    func = val.func
    if isinstance(func, ast.Name) and func.id in {"Enum", "StrEnum", "IntEnum"}:
        return True
    if isinstance(func, ast.Attribute) and func.attr in {"Enum", "StrEnum", "IntEnum"}:
        return True
    return False


def _audit_git_layout_clean_clone_and_codec(root: Path, *, probe_temp_contracts: bool) -> dict[str, Any]:
    """AC-4: Minimal Git layout vs logs/**, clean-clone check, exclusions, and zero duplicate codec/reward hacks."""
    diagnostics: list[dict[str, Any]] = []

    # 1. Verify versioned minimal governance tree exists via safe_input + no_reparse.
    formal_missing: list[str] = []
    for name in schema_resources.FORMAL:
        rel_s = f"docs/planning/b-route/schemas/{name}.schema.json"
        ok_s, code_s, msg_s = _safe_existing_file(root, rel_s, allow_logs=False)
        if not ok_s:
            formal_missing.append(rel_s)
            diagnostics.append(_diag(
                code_s or codec.ReasonCode.FILE_NOT_FOUND,
                codec.Stage.SCHEMA,
                rel_s,
                "7 FORMAL B-route schemas versioned in Git",
                msg_s,
                rel_s,
            ))

    required_gov_files = (
        "docs/workflows/chapter3-source-set.json",
        "knowledge/policies/source-exclusions.v1.json",
        "knowledge/policies/consumer-policies.v1.json",
    )
    missing_gov_files: list[str] = []
    for mg in required_gov_files:
        ok_g, code_g, msg_g = _safe_existing_file(root, mg, allow_logs=False)
        if not ok_g:
            missing_gov_files.append(mg)
            diagnostics.append(_diag(
                code_g or codec.ReasonCode.FILE_NOT_FOUND,
                codec.Stage.PATH,
                mg,
                "versioned minimal governance file",
                msg_g,
                mg,
            ))

    # 2. Verify Knowledge search exclusions via policy AND live _knowledge_catalog_builder._excluded probe.
    excluded_prefixes: set[str] = set()
    exclusions_ok = False
    builder_excluded_probe: dict[str, bool] = {}
    excl_rel = "knowledge/policies/source-exclusions.v1.json"
    try:
        excl_doc = codec.strict_json_loads(_safe_read_bytes(root, excl_rel, allow_logs=False))
        for rule in excl_doc.get("rules", []):
            if isinstance(rule, dict) and rule.get("disposition") == "excluded":
                pref = rule.get("path_prefix")
                if isinstance(pref, str):
                    excluded_prefixes.add(pref.strip("/"))
        required_exclusions = {"logs", "backup", "docs/migration"}
        missing_exclusions = sorted(required_exclusions - excluded_prefixes)
        builder_excluded_probe = {
            "logs/ci/x.json": bool(knowledge_catalog_builder._excluded("logs/ci/x.json", excl_doc)),
            "backup/x.md": bool(knowledge_catalog_builder._excluded("backup/x.md", excl_doc)),
            "docs/migration/x.md": bool(knowledge_catalog_builder._excluded("docs/migration/x.md", excl_doc)),
        }
        builder_ok = all(builder_excluded_probe.values())
        exclusions_ok = len(missing_exclusions) == 0 and builder_ok
        if missing_exclusions or not builder_ok:
            diagnostics.append(_diag(
                codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
                codec.Stage.CONTENT,
                excl_rel,
                {"required_exclusions": sorted(required_exclusions), "builder_excluded": True},
                {"missing_exclusions": missing_exclusions, "builder_excluded_probe": builder_excluded_probe},
                excl_rel,
            ))
    except (OSError, ValueError, codec.CodecError) as exc:
        diagnostics.append(_diag(
            _classify_read_exc(exc) if not isinstance(exc, codec.CodecError) else exc.diagnostic.reason_code,
            codec.Stage.DECODE,
            excl_rel,
            "valid knowledge/policies/source-exclusions.v1.json",
            str(exc)[:200],
            excl_rel,
        ))

    # 3. Clean-clone verification with an EMPTY logs/ directory (fail-closed when skipped!).
    clean_clone_verified = False
    clean_clone_details: dict[str, Any] = {
        "executed": False,
        "clean_clone_verified": False,
        "bundle_valid": False,
        "projection_valid": False,
    }
    if not probe_temp_contracts:
        diagnostics.append(_diag(
            codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
            codec.Stage.BUNDLE,
            "clean_clone_without_logs",
            "clean-clone probe with empty logs/ executed",
            "skip_live_probes",
            None,
        ))
    else:
        with tempfile.TemporaryDirectory(prefix="nr-b-clean-clone-") as tmpdir:
            clone_root = Path(tmpdir) / "clone"
            clone_root.mkdir()
            (clone_root / "logs").mkdir()
            _build_minimal_committed_b_repo(
                clone_root, root, include_task_bindings=True, multi_plan_shared_task=True, include_non_flow_req=True,
            )
            logs_files_count = sum(1 for _ in (clone_root / "logs").rglob("*") if _.is_file())
            clone_schemas_dir = clone_root / "docs/planning/b-route/schemas"
            loaded_schemas = schema_resources.resources(clone_schemas_dir, auxiliary=True)
            schemas_checked_ok = True
            try:
                import jsonschema

                for name in schema_resources.FORMAL:
                    s_raw = _safe_read_bytes(clone_root, f"docs/planning/b-route/schemas/{name}.schema.json", allow_logs=False)
                    s_obj = codec.strict_json_loads(s_raw)
                    jsonschema.Draft202012Validator.check_schema(s_obj)
            except Exception:
                schemas_checked_ok = False
            bundle_res = _validate_probe_bundle(clone_root)
            proj_res = projection.build_b_route_knowledge_projection(clone_root, mode="workspace_preview")
            clean_clone_verified = (
                logs_files_count == 0
                and len(loaded_schemas) >= len(schema_resources.FORMAL)
                and schemas_checked_ok
                and bool(bundle_res.ok)
                and proj_res.get("ok") is True
            )
            clean_clone_details = {
                "executed": True,
                "clean_clone_verified": clean_clone_verified,
                "empty_logs_file_count": logs_files_count,
                "schemas_loaded": len(loaded_schemas),
                "clone_schemas_valid": schemas_checked_ok,
                "bundle_valid": bool(bundle_res.ok),
                "projection_valid": proj_res.get("ok") is True,
                "requires_logs_committed_in_git": False,
            }
            if not clean_clone_verified:
                diagnostics.append(_diag(
                    codec.ReasonCode.CONFLICT,
                    codec.Stage.BUNDLE,
                    "clean_clone_without_logs",
                    "versioned governance and schemas validate cleanly with empty logs/",
                    clean_clone_details,
                    None,
                ))

    # 4. Zero duplicate codec / formal schema owners / unapproved json.loads across ALL scripts/python/*b_route*.py.
    duplicate_codec_violations: list[dict[str, Any]] = []
    reward_hack_violations: list[dict[str, Any]] = []
    scripts_py, scripts_py_err = _safe_dir_ready(root, "scripts/python")
    if scripts_py_err is not None:
        diagnostics.append(scripts_py_err)
    elif scripts_py is not None:
        for py_file in sorted(scripts_py.glob("*b_route*.py")):
            rel = f"scripts/python/{py_file.name}"
            try:
                raw = _safe_read_bytes(root, rel, allow_logs=False)
                tree = ast.parse(raw.decode("utf-8-sig"))
            except (OSError, ValueError, SyntaxError, UnicodeDecodeError) as exc:
                diagnostics.append(_diag(
                    _classify_read_exc(exc) if not isinstance(exc, SyntaxError) else codec.ReasonCode.INVALID_JSON,
                    codec.Stage.CONTENT,
                    rel,
                    "parseable Python module without reparse",
                    str(exc)[:200],
                    rel,
                ))
                continue

            if py_file.name != "_b_route_codec.py":
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef) and node.name in {"ReasonCode", "Stage"}:
                        duplicate_codec_violations.append({"file": rel, "kind": "duplicate_enum_class", "symbol": node.name})
                    elif isinstance(node, ast.FunctionDef) and node.name == "strict_json_loads":
                        duplicate_codec_violations.append({"file": rel, "kind": "duplicate_codec_function", "symbol": node.name})
                    elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                        for var_name, val in _iter_assignment_targets(node):
                            if var_name in {"ReasonCode", "Stage"} and _is_functional_enum_call(val):
                                duplicate_codec_violations.append({"file": rel, "kind": "duplicate_functional_enum", "symbol": var_name})
                            if var_name in {"CODEC_VERSION", "PROJECTION_CODEC"} and isinstance(val, ast.Constant) and isinstance(val.value, str):
                                duplicate_codec_violations.append({"file": rel, "kind": "duplicate_codec_constant", "symbol": var_name})
                    elif (
                        py_file.name not in LEGACY_JSON_LOADS_ALLOWLIST
                        and isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and node.func.attr == "loads"
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "json"
                    ):
                        duplicate_codec_violations.append({
                            "file": rel,
                            "kind": "unapproved_private_json_loads",
                            "symbol": f"json.loads@L{node.lineno}",
                        })

            if py_file.name != "_b_route_schema_resources.py":
                for node in ast.walk(tree):
                    if isinstance(node, (ast.Assign, ast.AnnAssign)):
                        for var_name, val in _iter_assignment_targets(node):
                            if var_name == "FORMAL" and isinstance(val, (ast.Tuple, ast.List, ast.Set)):
                                elems = {
                                    e.value for e in val.elts
                                    if isinstance(e, ast.Constant) and isinstance(e.value, str)
                                }
                                if {"common", "policy", "plan", "binding", "origins", "commit", "catalog"} <= elems:
                                    duplicate_codec_violations.append({"file": rel, "kind": "duplicate_formal_schema_registry", "symbol": "FORMAL"})

            # Check for Reward-only bypass/exemption hacks in generic B-route modules.
            if py_file.name != "_b_route_consumer_alignment.py":
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        lname = node.name.lower()
                        if "reward" in lname and any(tok in lname for tok in ("bypass", "exempt", "skip", "hack", "override")):
                            reward_hack_violations.append({"file": rel, "symbol": node.name, "line": node.lineno})

    for viol in duplicate_codec_violations:
        diagnostics.append(_diag(
            codec.ReasonCode.DUPLICATE_OWNER,
            codec.Stage.CONTENT,
            viol["file"],
            "single canonical codec (_b_route_codec.py) and formal schema registry (_b_route_schema_resources.py)",
            viol,
            viol["file"],
        ))
    for viol in reward_hack_violations:
        diagnostics.append(_diag(
            codec.ReasonCode.CONFLICT,
            codec.Stage.CONTENT,
            viol["file"],
            "generic B-route gates without Reward-only bypass/exemption hacks",
            viol,
            viol["file"],
        ))

    return {
        "ok": len(diagnostics) == 0,
        "formal_schemas_present": len(formal_missing) == 0,
        "minimal_governance_files_present": len(missing_gov_files) == 0,
        "logs_excluded_from_knowledge_search": exclusions_ok,
        "excluded_prefixes_checked": sorted(excluded_prefixes & {"logs", "backup", "docs/migration"}),
        "knowledge_builder_excluded_probe": builder_excluded_probe,
        "clean_clone_verified": clean_clone_verified,
        "clean_clone": clean_clone_details,
        "duplicate_codec_violations": duplicate_codec_violations,
        "zero_duplicate_codec_verified": len(duplicate_codec_violations) == 0,
        "generic_b_route_ready_without_reward_hacks": len(reward_hack_violations) == 0,
        "reward_hack_violations": reward_hack_violations,
        "diagnostics": diagnostics,
    }


def _is_alignment_reserved_report_path(cleaned: str) -> bool:
    if any(cleaned == prefix or cleaned.startswith(prefix + "/") for prefix in ALIGNMENT_RESERVED_REPORT_PREFIXES):
        return True
    parts = cleaned.split("/")
    if len(parts) >= 4 and parts[0] == "logs" and parts[1] == "ci" and _DATE_DIR_RE.fullmatch(parts[2]):
        sub = parts[3]
        if sub in _ALIGNMENT_DATED_RESERVED_NAMES:
            return True
        if any(sub.startswith(p) for p in observability._DATED_RESERVED_PREFIXES):
            return True
    return False


def validate_alignment_report_path(root: Path | str, report_rel: Any) -> tuple[Path, str, Path]:
    """Pre-validate --report path: non-reserved logs/**/*.json, no reparse, and no overwrite."""
    target, cleaned, root_path = observability.validate_reserved_log_write_path(
        root, report_rel, suffix=".json", field="report",
    )
    if _is_alignment_reserved_report_path(cleaned):
        raise codec.CodecError(codec.Diagnostic(
            codec.ReasonCode.UNSAFE_PATH,
            codec.Stage.PATH,
            "report",
            "path outside reserved operational and producer log directories",
            cleaned,
            cleaned,
        ))
    if os.path.lexists(target):
        raise codec.CodecError(codec.Diagnostic(
            codec.ReasonCode.CONFLICT,
            codec.Stage.TARGET,
            "report",
            "non-existing report path (no overwrite)",
            cleaned,
            cleaned,
        ))
    return target, cleaned, root_path


def audit_b_route_consumer_alignment(
    root: Path | str,
    *,
    probe_temp_contracts: bool = True,
) -> dict[str, Any]:
    """Run the full Story 4.9 read-only consumer alignment and pre-switch audit."""
    root_resolved = observability._validate_root(root)

    ac1 = _audit_consumer_matrix(root_resolved)
    ac2 = _audit_five_state_and_migration(root_resolved, probe_temp_contracts=probe_temp_contracts)
    ac3 = _audit_docs_skills_and_adrs(root_resolved)
    ac4 = _audit_git_layout_clean_clone_and_codec(root_resolved, probe_temp_contracts=probe_temp_contracts)

    all_diagnostics: list[dict[str, Any]] = [
        *ac1["diagnostics"],
        *ac2["diagnostics"],
        *ac3["diagnostics"],
        *ac4["diagnostics"],
    ]
    epic4_alignment_ready = bool(ac1["ok"] and ac2["ok"] and ac3["ok"] and ac4["ok"])

    evidence_locators = [
        {
            "consumer_id": row["consumer_id"],
            "group": row["group"],
            "module_path": row["module_path"],
            "sha256": row["sha256"],
            "pass_evidence_refs": row["pass_evidence_refs"],
            "fail_evidence_refs": row["fail_evidence_refs"],
            "status": row["status"],
        }
        for row in ac1["consumers"]
    ]

    invariants = dict(INVARIANTS)
    invariants["workflow_md_mutated"] = bool(ac3["workflow_md_mutated"])

    pre_switch_coverage_report = {
        "counts": {
            "total_consumers": ac1["total_consumers"],
            "passed": ac1["passed_count"],
            "blocked": ac1["blocked_count"],
            "not_applicable": ac1["not_applicable_count"],
            "groups_covered": ac1["groups_covered"],
            "groups_expected": ac1["groups_expected"],
        },
        "group_summary": ac1["group_summary"],
        "evidence_locators": evidence_locators,
        "generic_b_route_ready_without_reward_hacks": ac4["generic_b_route_ready_without_reward_hacks"],
        "epic4_alignment_ready": epic4_alignment_ready,
        "switch_blocked": True,
        "switch_blocked_reasons": (
            list(EPIC5_REMAINING_GATES)
            if epic4_alignment_ready
            else ["epic4_consumer_alignment_blocked", *EPIC5_REMAINING_GATES]
        ),
        "default_b_enabled": False,
        "a_write_compatibility_retired": False,
        "second_state_machine_created": False,
        "epic5_remaining_gates": list(EPIC5_REMAINING_GATES),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "ok": epic4_alignment_ready,
        "status": "passed" if epic4_alignment_ready else "blocked",
        "consumer_matrix": ac1,
        "five_state_version_contract": ac2,
        "docs_skills_adr_alignment": ac3,
        "git_layout_and_codec_audit": ac4,
        "pre_switch_coverage_report": pre_switch_coverage_report,
        "diagnostics": all_diagnostics,
        "default_b_enabled": False,
        "a_write_compatibility_retired": False,
        "second_state_machine_created": False,
        "runtime_verified": False,
        "implicit_global_refresh_performed": False,
        "invariants": invariants,
    }


def write_alignment_report(root: Path | str, report_rel: str, payload: dict[str, Any]) -> Path:
    """Write an optional alignment audit report strictly under non-reserved logs/**/*.json without overwrite."""
    target, cleaned, root_path = validate_alignment_report_path(root, report_rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        observability._check_ancestors_no_reparse(root_path, target)
        inventory.no_reparse(target)
    except ValueError as exc:
        raise codec.CodecError(codec.Diagnostic(
            codec.ReasonCode.UNSAFE_PATH,
            codec.Stage.PATH,
            "report",
            "report parent and target without symlink or reparse point",
            str(exc)[:200],
            cleaned,
        )) from exc
    payload["report_path"] = cleaned
    data = (json.dumps(payload, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=False) + "\n").encode("utf-8")
    try:
        with open(target, "xb") as handle:
            handle.write(data)
    except FileExistsError as exc:
        raise codec.CodecError(codec.Diagnostic(
            codec.ReasonCode.CONFLICT,
            codec.Stage.TARGET,
            "report",
            "non-existing report path (no overwrite)",
            cleaned,
            cleaned,
        )) from exc
    except OSError as exc:
        raise codec.CodecError(codec.Diagnostic(
            codec.ReasonCode.READ_ERROR,
            codec.Stage.TARGET,
            "report",
            "writable non-reserved report path",
            str(exc)[:200],
            cleaned,
        )) from exc
    return target
