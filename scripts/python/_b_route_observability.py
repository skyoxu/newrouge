"""Read-only B-route process observability & unified diagnostics aggregation (Story 4.8).

Aggregates stage events, timing/budget measurements, unified six-field Diagnostics,
three disjoint reuse classes, stop-loss / no-progress retry / rework signals, and
non-offsettable quality-floor checks from bounded repository ``logs/**`` artifacts.

Invariants:
- Strictly read-only (never mutates authority files, Taskmaster, catalog, pointers,
  timestamps, or Knowledge snapshots; never creates an analytics database or a
  second state machine; never triggers an implicit global Knowledge refresh).
- Bounded inspection only: NEVER calls ``rglob`` over ``logs/ci/mvg-planning`` or
  ``logs/ci/capability-planning``.
- Reuses ONLY existing ``_b_route_codec.ReasonCode`` and ``_b_route_codec.Stage``
  members without extending enums or modifying the 7 FORMAL schemas.
- Separates observed active elapsed time, paused wall-clock spans, reserved request
  budgets, verified actual dispatches, model estimates, and ``"unknown"`` billed cost.
- Enforces zero speedup, cost-reduction, two-hour wall-clock, fixed task-count, or
  man-hour gates.
- Process metrics can NEVER offset any of the 5 quality-floor regressions.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import _b_route_codec as codec
import _b_route_inventory as inventory
import _b_route_knowledge_projection as projection
from _b_route_evidence_reuse import _VOLATILE_EVENT_FIELDS


SCHEMA_VERSION = "newrouge.b-route-observability.v1"
BASELINE_SCHEMA_VERSIONS: frozenset[str] = frozenset({
    SCHEMA_VERSION,
    "newrouge.b-route-observability-baseline.v1",
})

MAX_LOG_DATES = 60
MAX_BOUNDED_RUNS = 50
MAX_PLANNER_RUN_DIRS = MAX_BOUNDED_RUNS
MAX_OPERATION_DIRS = 200
MAX_FILES_PER_DIR = 500
MAX_JSONL_LINES = 5000

RESERVED_PRODUCER_PREFIXES: tuple[str, ...] = (
    "logs/ci/capability-planning",
    "logs/ci/mvg-planning",
    "logs/ci/capability-recovery",
    "logs/ci/mvg-recovery",
    "logs/ci/mvg-acceptance",
    "logs/ci/b-route-operations",
    "logs/ci/b-route-sources",
    "logs/ci/b-route-source-audit",
    "logs/ci/b-route-planning-input",
    "logs/ci/b-route-task-preview",
    "logs/ci/b-route-task-compilation",
    "logs/ci/b-route-chapter4-binding",
    "logs/ci/b-route-stage5-obligations",
    "logs/ci/b-route-chapter5-readiness",
    "logs/ci/b-route-defect-routing",
    "logs/ci/b-route-chapter7-slice",
    "logs/ci/b-route-reopen",
    "logs/ci/project-health-knowledge",
    "logs/ci/knowledge-planning",
)

_DATED_RESERVED_EXACT: frozenset[str] = frozenset({
    "b-route-sources",
    "b-route-source-audit",
    "b-route-task-compilation",
})
_DATED_RESERVED_PREFIXES: tuple[str, ...] = (
    "sc-review-pipeline-task-",
    "sc-needs-fix-fast-task-",
)

DIAGNOSTIC_CATEGORIES: tuple[str, ...] = (
    "missing_governance",
    "unknown_version",
    "corrupt_reference",
    "drift_or_stale",
    "pending",
    "conflict",
    "budget",
    "execution_fault",
    "semantic",
)

QUALITY_FLOOR_KINDS: tuple[str, ...] = (
    "source_omission",
    "mature_identity_drift",
    "unverified_obligation",
    "failure_reclassification",
    "premature_out_of_scope_implementation",
)

GOVERNANCE_THRESHOLDS: dict[str, bool] = {
    "speedup_gate_enforced": False,
    "cost_reduction_gate_enforced": False,
    "two_hour_wall_clock_gate_enforced": False,
    "fixed_task_count_gate_enforced": False,
    "man_hour_gate_enforced": False,
}

INVARIANTS: dict[str, bool] = {
    "read_only": True,
    "second_state_machine": False,
    "analytics_database_created": False,
    "implicit_global_refresh_performed": False,
    "pointers_advanced": False,
    "original_timestamps_mutated": False,
    "cross_class_proof_allowed": False,
    **GOVERNANCE_THRESHOLDS,
    "process_metrics_can_offset_quality_floor": False,
    "runtime_verified": False,
    "default_b_enabled": False,
}

_REASON_VALUES = frozenset(item.value for item in codec.ReasonCode)
_STAGE_VALUES = frozenset(item.value for item in codec.Stage)
_DIAG_SIX_KEYS = ("reason_code", "stage", "entity_id", "expected", "actual", "resume_ref")

_REASON_TO_CATEGORY: dict[str, str] = {
    codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING.value: "missing_governance",
    codec.ReasonCode.UNPUBLISHED.value: "missing_governance",
    codec.ReasonCode.FILE_NOT_FOUND.value: "missing_governance",
    codec.ReasonCode.MISSING_REQUIRED_FIELD.value: "missing_governance",
    codec.ReasonCode.UNKNOWN_ENTITY.value: "missing_governance",
    codec.ReasonCode.UNKNOWN_SCHEMA.value: "unknown_version",
    codec.ReasonCode.UNKNOWN_CODEC_VERSION.value: "unknown_version",
    codec.ReasonCode.UNKNOWN_VERIFICATION_MODE.value: "unknown_version",
    codec.ReasonCode.SCHEMA_MISMATCH.value: "unknown_version",
    codec.ReasonCode.INVALID_JSON.value: "corrupt_reference",
    codec.ReasonCode.INVALID_UTF8.value: "corrupt_reference",
    codec.ReasonCode.DUPLICATE_KEY.value: "corrupt_reference",
    codec.ReasonCode.NON_FINITE_NUMBER.value: "corrupt_reference",
    codec.ReasonCode.INVALID_TYPE.value: "corrupt_reference",
    codec.ReasonCode.INVALID_REFERENCE.value: "corrupt_reference",
    codec.ReasonCode.INVALID_DIGEST.value: "corrupt_reference",
    codec.ReasonCode.IDENTITY_UNPROVABLE.value: "corrupt_reference",
    codec.ReasonCode.UNSAFE_PATH.value: "corrupt_reference",
    codec.ReasonCode.PATH_UNPROVABLE.value: "corrupt_reference",
    codec.ReasonCode.READ_ERROR.value: "corrupt_reference",
    codec.ReasonCode.SCHEMA_VALIDATION_FAILED.value: "corrupt_reference",
    codec.ReasonCode.SCHEMA_RESOURCE_ERROR.value: "corrupt_reference",
    codec.ReasonCode.UNRESOLVED_REFERENCE.value: "corrupt_reference",
    codec.ReasonCode.UNSUPPORTED_LOCATOR.value: "corrupt_reference",
    codec.ReasonCode.UNKNOWN_FIELD.value: "corrupt_reference",
    codec.ReasonCode.INVALID_ENUM.value: "corrupt_reference",
    codec.ReasonCode.INVALID_ARGUMENT.value: "corrupt_reference",
    codec.ReasonCode.DIGEST_CYCLE.value: "corrupt_reference",
    codec.ReasonCode.DIGEST_MISMATCH.value: "drift_or_stale",
    codec.ReasonCode.INPUT_STALE.value: "drift_or_stale",
    codec.ReasonCode.REVISION_MISMATCH.value: "drift_or_stale",
    codec.ReasonCode.FILE_CHANGED.value: "drift_or_stale",
    codec.ReasonCode.MAPPING_MISMATCH.value: "drift_or_stale",
    codec.ReasonCode.PENDING.value: "pending",
    codec.ReasonCode.CONFLICT.value: "conflict",
    codec.ReasonCode.DUPLICATE_OWNER.value: "conflict",
    codec.ReasonCode.BUDGET_EXHAUSTED.value: "budget",
    codec.ReasonCode.DEPENDENCY_UNAVAILABLE.value: "execution_fault",
    codec.ReasonCode.SEMANTIC_ERROR.value: "semantic",
}

_KNOWN_SCHEMA_VERSIONS: frozenset[str] = frozenset({
    SCHEMA_VERSION,
    "newrouge.b-route-observability-baseline.v1",
    "newrouge.b-route-3b-intermediate-contract-pin.v1",
    "newrouge.b-route-3b-intermediate-target-pin.v1",
    "newrouge.b-route-3b-pairwise-tournament.v1",
    "newrouge.b-route-3b-segmented-request.v1",
    "newrouge.b-route-3b-segmented-runtime.v1",
    "newrouge.b-route-3b-segmented-selector.v1",
    "newrouge.b-route-3b-segmented-transport.v1",
    "newrouge.b-route-admission-chain.v1",
    "newrouge.b-route-admission-execution.v1",
    "newrouge.b-route-adoption-model-subject.v2",
    "newrouge.b-route-adoption-model-subject.v3",
    "newrouge.b-route-adoption-operation.v1",
    "newrouge.b-route-adoption-operation.v2",
    "newrouge.b-route-adoption-pending.v1",
    "newrouge.b-route-adoption-request.v2",
    "newrouge.b-route-adoption-review-proof.v1",
    "newrouge.b-route-adoption-review-proof.v2",
    "newrouge.b-route-adoption-review-proof.v3",
    "newrouge.b-route-adoption-review-subject.v1",
    "newrouge.b-route-adoption-review-subject.v2",
    "newrouge.b-route-adoption-review-subject.v3",
    "newrouge.b-route-adoption-review-verdict.v1",
    "newrouge.b-route-adoption-review-verdict.v2",
    "newrouge.b-route-adoption-review-verdict.v3",
    "newrouge.b-route-audit-phase-transition.v4",
    "newrouge.b-route-baseline-inventory.v3",
    "newrouge.b-route-binding.v1",
    "newrouge.b-route-candidate-check.v1",
    "newrouge.b-route-candidate.v1",
    "newrouge.b-route-catalog.v1",
    "newrouge.b-route-chapter4-binding-event.v1",
    "newrouge.b-route-chapter4-binding-operation.v1",
    "newrouge.b-route-chapter4-binding-preview.v1",
    "newrouge.b-route-chapter4-binding-request.v1",
    "newrouge.b-route-chapter4-binding.v1",
    "newrouge.b-route-chapter4-public-sync.v1",
    "newrouge.b-route-chapter4-public-sync.v1.pending",
    "newrouge.b-route-chapter5-readiness.v1",
    "newrouge.b-route-chapter6-execution-gate.v1",
    "newrouge.b-route-chapter6-gate-event.v1",
    "newrouge.b-route-chapter6-gate.v1",
    "newrouge.b-route-chapter6-lease-receipt.v1",
    "newrouge.b-route-chapter6-recovery-input-set.v1",
    "newrouge.b-route-chapter6-recovery.v1",
    "newrouge.b-route-chapter7-handoff.v1",
    "newrouge.b-route-chapter7-slice.v1",
    "newrouge.b-route-commit-intent.v1",
    "newrouge.b-route-commit.v1",
    "newrouge.b-route-common.v1",
    "newrouge.b-route-compensation-operation.v2",
    "newrouge.b-route-compensation-preserving-closures.v1",
    "newrouge.b-route-compensation-request.v2",
    "newrouge.b-route-compensation-review-delivery.v1",
    "newrouge.b-route-compensation-review-delivery.v2",
    "newrouge.b-route-compensation-review-delivery.v3",
    "newrouge.b-route-compensation-review-delivery.v4",
    "newrouge.b-route-compensation-review-materials.v1",
    "newrouge.b-route-compensation-review-packet.v1",
    "newrouge.b-route-compensation-review-presentation.v1",
    "newrouge.b-route-compensation-review-proof.v2",
    "newrouge.b-route-compensation-review-repair.v1",
    "newrouge.b-route-compensation-review-roles.v1",
    "newrouge.b-route-compensation-review-subject.v2",
    "newrouge.b-route-compensation-review-transport.v1",
    "newrouge.b-route-compensation-review-transport.v2",
    "newrouge.b-route-compensation-review-verdict.v2",
    "newrouge.b-route-compensation-segment-plan.v1",
    "newrouge.b-route-compensation-segment-preflight.v1",
    "newrouge.b-route-compensation-segmented-delivery.v1",
    "newrouge.b-route-compensation-segmented-execution-plan.v1",
    "newrouge.b-route-compensation-segmented-proof.v1",
    "newrouge.b-route-compensation-segmented-proof.v2",
    "newrouge.b-route-compensation-segmented-verdict.v1",
    "newrouge.b-route-completed-extraction-reuse.v1",
    "newrouge.b-route-completed-review-recovery.v1",
    "newrouge.b-route-completed-worker-recovery.v1",
    "newrouge.b-route-completion-verdict.v1",
    "newrouge.b-route-context-view.v1",
    "newrouge.b-route-defect-handoff.v1",
    "newrouge.b-route-defect-input.v1",
    "newrouge.b-route-defect-routing.v1",
    "newrouge.b-route-draft-carrier.v1",
    "newrouge.b-route-entrypoint-parity.v1",
    "newrouge.b-route-epic3-handoff.v1",
    "newrouge.b-route-execution-receipt.v1",
    "newrouge.b-route-execution-transition.v1",
    "newrouge.b-route-frozen-native-capture.v1",
    "newrouge.b-route-host-fault-source-boundaries.v3",
    "newrouge.b-route-impact-closure.v1",
    "newrouge.b-route-impact-graph.v1",
    "newrouge.b-route-independent-admission.v1",
    "newrouge.b-route-independent-review.v1",
    "newrouge.b-route-indexed-independent-review.v1",
    "newrouge.b-route-input-path-recovery.v1",
    "newrouge.b-route-input-set.v1",
    "newrouge.b-route-issue-account.v1",
    "newrouge.b-route-json.v1",
    "newrouge.b-route-knowledge-projection.v1",
    "newrouge.b-route-known-synthesis-recovery.v1",
    "newrouge.b-route-legacy-manifest-requirement.v3",
    "newrouge.b-route-machine-business-replacement.v1",
    "newrouge.b-route-manual-signoff.v1",
    "newrouge.b-route-migration-preflight.v1",
    "newrouge.b-route-milestone-handoff.v1",
    "newrouge.b-route-mvg-source-epoch.v1",
    "newrouge.b-route-mvg-synthesis-recovery.v1",
    "newrouge.b-route-native-rejection.v1",
    "newrouge.b-route-origins.v1",
    "newrouge.b-route-page-trigger.v1",
    "newrouge.b-route-partial-repair-recovery.v1",
    "newrouge.b-route-plan.v1",
    "newrouge.b-route-planning-candidate.v1",
    "newrouge.b-route-planning-contract.v1",
    "newrouge.b-route-planning-draft.v1",
    "newrouge.b-route-planning-handoff.v1",
    "newrouge.b-route-planning-input.v1",
    "newrouge.b-route-planning-page.v1",
    "newrouge.b-route-planning-prepare-report.v1",
    "newrouge.b-route-planning-relations.v1",
    "newrouge.b-route-planning-request.v1",
    "newrouge.b-route-planning-run.v1",
    "newrouge.b-route-planning-run.v2",
    "newrouge.b-route-policy.v1",
    "newrouge.b-route-preflight-intents.v1",
    "newrouge.b-route-protection-input.v1",
    "newrouge.b-route-protection-snapshot.v3",
    "newrouge.b-route-provider-output-schema.v1",
    "newrouge.b-route-published-history-verification.v1",
    "newrouge.b-route-published-reader.v1",
    "newrouge.b-route-read-only-seed.v1",
    "newrouge.b-route-reader-diagnostic.v1",
    "newrouge.b-route-reader-failure.v1",
    "newrouge.b-route-recovery-funding.v4",
    "newrouge.b-route-recovery-input-set.v1",
    "newrouge.b-route-reopen.v1",
    "newrouge.b-route-repair-delta-intents.v1",
    "newrouge.b-route-repair-scope.v1",
    "newrouge.b-route-resource-pipeline.v4",
    "newrouge.b-route-retained-native-execution-binding.v1",
    "newrouge.b-route-retained-native-execution-binding.v2",
    "newrouge.b-route-retained-native-execution.v1",
    "newrouge.b-route-review-source-policy.v1",
    "newrouge.b-route-review-source-policy.v2",
    "newrouge.b-route-review.v1",
    "newrouge.b-route-run-initialization.v1",
    "newrouge.b-route-runtime-gate.v1",
    "newrouge.b-route-saved-review-bindings-data.v1",
    "newrouge.b-route-segmented-active.v1",
    "newrouge.b-route-segmented-adoption-review-delivery.v1",
    "newrouge.b-route-segmented-adoption-review-header.v1",
    "newrouge.b-route-segmented-adoption-review-plan.v1",
    "newrouge.b-route-segmented-adoption-review-verdict.v1",
    "newrouge.b-route-segmented-birth-claim.v1",
    "newrouge.b-route-segmented-born.v1",
    "newrouge.b-route-segmented-candidate-contract.v1",
    "newrouge.b-route-segmented-candidate-product.v1",
    "newrouge.b-route-segmented-candidate-proof.v1",
    "newrouge.b-route-segmented-claim.v1",
    "newrouge.b-route-segmented-completion.v1",
    "newrouge.b-route-segmented-derived-decisions.v1",
    "newrouge.b-route-segmented-envelope.v1",
    "newrouge.b-route-segmented-host-input.v1",
    "newrouge.b-route-segmented-host.v1",
    "newrouge.b-route-segmented-input-archive.v1",
    "newrouge.b-route-segmented-interaction-domain.v1",
    "newrouge.b-route-segmented-journal.v1",
    "newrouge.b-route-segmented-manifest.v1",
    "newrouge.b-route-segmented-native-run.v1",
    "newrouge.b-route-segmented-output-schema.v1",
    "newrouge.b-route-segmented-paid-reservation.v1",
    "newrouge.b-route-segmented-plan-authority.v1",
    "newrouge.b-route-segmented-plan-producer.v1",
    "newrouge.b-route-segmented-plan.v1",
    "newrouge.b-route-segmented-planning-run.v1",
    "newrouge.b-route-segmented-prompt.v1",
    "newrouge.b-route-segmented-publication.v1",
    "newrouge.b-route-segmented-response-citation-wire.v1",
    "newrouge.b-route-segmented-response-expansion-limits.v1",
    "newrouge.b-route-segmented-response.v1",
    "newrouge.b-route-segmented-run-index.v1",
    "newrouge.b-route-segmented-runner-transport.v1",
    "newrouge.b-route-segmented-runtime-identity.v1",
    "newrouge.b-route-segmented-source-authority.v1",
    "newrouge.b-route-segmented-source-contract.v1",
    "newrouge.b-route-segmented-verified-result.v1",
    "newrouge.b-route-segmented-wire-input.v1",
    "newrouge.b-route-segmented-workflow.v1",
    "newrouge.b-route-selected-design-history.v1",
    "newrouge.b-route-selector-anchor-identity.v1",
    "newrouge.b-route-selector-metadata-transaction.v1",
    "newrouge.b-route-selector-recovery.v1",
    "newrouge.b-route-selector-request-preview.v1",
    "newrouge.b-route-selector-retained-capture.v1",
    "newrouge.b-route-selector-source-epoch.v1",
    "newrouge.b-route-source-accounting.v1",
    "newrouge.b-route-source-audit.v1",
    "newrouge.b-route-source-audit.v1.budget",
    "newrouge.b-route-source-epoch.v1",
    "newrouge.b-route-source-epoch.v2",
    "newrouge.b-route-source-producer-input.v5",
    "newrouge.b-route-sources-candidate.v1",
    "newrouge.b-route-sources-declaration.v1",
    "newrouge.b-route-sources-prepared.v1",
    "newrouge.b-route-sources-report.v1",
    "newrouge.b-route-sources.v1",
    "newrouge.b-route-stage4-semantics.v1",
    "newrouge.b-route-stage5-obligations-event.v1",
    "newrouge.b-route-stage5-obligations-operation.v1",
    "newrouge.b-route-stage5-obligations-preview.v1",
    "newrouge.b-route-stage5-obligations-request.v1",
    "newrouge.b-route-stage5-obligations-semantics.v1",
    "newrouge.b-route-stage5-obligations.v1",
    "newrouge.b-route-stage5-public-sync.v1",
    "newrouge.b-route-stage5-public-sync.v1.pending",
    "newrouge.b-route-task-change-intents.v1",
    "newrouge.b-route-task-compilation-event.v1",
    "newrouge.b-route-task-compilation-operation.v1",
    "newrouge.b-route-task-compilation-request.v1",
    "newrouge.b-route-task-compilation.v1",
    "newrouge.b-route-task-definition.v1",
    "newrouge.b-route-task-origin-resolution.v1",
    "newrouge.b-route-task-origin.v1",
    "newrouge.b-route-task-preview.v1",
    "newrouge.b-route-verification-scope-delta.v1",
    "newrouge.b-route-verification-scope-revalidation.v1",
    "newrouge.b-route-verification-scope-validation.v1",
    "newrouge.b-route-verification-scope.v1",
    "newrouge.b-route-win-concurrency.v1",
    "newrouge.binding-evidence-rollout.v1",
    "newrouge.capabilities.v1",
    "newrouge.capability-alignment-normalization.v1",
    "newrouge.capability-alignment.v1",
    "newrouge.capability-batch-analysis.v1",
    "newrouge.capability-candidate.v1",
    "newrouge.capability-input-freshness.v1",
    "newrouge.capability-model-batch-index.v1",
    "newrouge.capability-model-batch.v1",
    "newrouge.capability-planning-readiness-summary.v1",
    "newrouge.capability-planning-run.v1",
    "newrouge.capability-reference.v1",
    "newrouge.capability-review.v2",
    "newrouge.capability-selection.v1",
    "newrouge.chapter4-semantic-gap-report.v1",
    "newrouge.chapter5-input-fingerprint.v1",
    "newrouge.chapter5-readiness.v1",
    "newrouge.chapter6-element-capture.v1",
    "newrouge.chapter6-semantic-publication.v1",
    "newrouge.isolated-model-runner-receipt.v1",
    "newrouge.isolated-model-runner.v1",
    "newrouge.knowledge-planning-job.v1",
    "newrouge.milestone-change-plan.v1",
    "newrouge.milestone-task-handoff.v1",
    "newrouge.mvg-acceptance.v1",
    "newrouge.mvg-apply-checkpoint-binding.v1",
    "newrouge.mvg-baseline-delta.v1",
    "newrouge.mvg-capability-admission-execution.v1",
    "newrouge.mvg-capability-admission.v1",
    "newrouge.mvg-capability-adoption.v1",
    "newrouge.mvg-capability-append.v1",
    "newrouge.mvg-capability-checkpoint.v1",
    "newrouge.mvg-capability-recovery.v1",
    "newrouge.mvg-capability-selection-input.v1",
    "newrouge.mvg-capability-worker.v1",
    "newrouge.mvg-checkpoint-commit-outcome.v1",
    "newrouge.mvg-checkpoint-conflict.v1",
    "newrouge.mvg-completed-registry.v1",
    "newrouge.mvg-coverage-skeleton.v1",
    "newrouge.mvg-entrypoint-skeleton.v1",
    "newrouge.mvg-evidence-audit.v1",
    "newrouge.mvg-global-audit.v1",
    "newrouge.mvg-input-envelope.v1",
    "newrouge.mvg-inspection-authority.v1",
    "newrouge.mvg-integration.v1",
    "newrouge.mvg-lossless-context.v1",
    "newrouge.mvg-model-context.v1",
    "newrouge.mvg-mutation-probe.v1",
    "newrouge.mvg-planning-completion.v1",
    "newrouge.mvg-planning-input.v1",
    "newrouge.mvg-planning-model-execution.v1",
    "newrouge.mvg-planning-proposal.v1",
    "newrouge.mvg-planning-readiness-summary.v1",
    "newrouge.mvg-planning-run.v1",
    "newrouge.mvg-planning-segment.v1",
    "newrouge.mvg-reconciliation-projection.v1",
    "newrouge.mvg-recovery-registry.v1",
    "newrouge.mvg-reopen-commit.v1",
    "newrouge.mvg-reopen-history.v1",
    "newrouge.mvg-reopen-plan.v1",
    "newrouge.mvg-reopen-transaction.v1",
    "newrouge.mvg-review-evidence.v1",
    "newrouge.mvg-selection-execution-receipt.v1",
    "newrouge.mvg-selection-review.v1",
    "newrouge.mvg-semantic-review.v1",
    "newrouge.mvg-source-conflicts.v1",
    "newrouge.mvg-stage-cost.v1",
    "newrouge.mvg-structured-context.v1",
    "newrouge.mvg-test-context.v1",
    "newrouge.planning-acceptance-fixture.v1",
    "newrouge.planning-analysis-input.v1",
    "newrouge.planning-apply-journal.v1",
    "newrouge.planning-production-acceptance.v1",
    "newrouge.project-health-knowledge.v1",
    "newrouge.project-health-runtime-index.v1",
    "newrouge.project-health-runtime.v1",
    "newrouge.requirement-accounting.v1",
    "newrouge.requirement-routes.v1",
    "newrouge.review-publication.v1",
    "newrouge.sc-needs-fix-fast.v1",
    "newrouge.sc-review-pipeline.v1",
    "newrouge.semantic-reconciliation.v1",
    "newrouge.semantic-requirements.v1",
    "newrouge.source-blocks.v1",
    "newrouge.task-candidates.v1",
    "newrouge.task-evidence.v1",
    "newrouge.task-master-statuses.v1",
    "newrouge.taskmaster-back.v1",
    "newrouge.taskmaster-gameplay.v1",
    "newrouge.taskmaster-master.v1",
    "1.0",
    "1.0.0",
    "1",
})

_EXECUTION_FAULT_KEYWORDS = (
    "runner_crash",
    "runner_fault",
    "execution_fault",
    "process_exit",
    "exit_code",
    "timeout",
    "timed_out",
    "receipt_drift",
    "dispatch_failed",
    "subprocess_error",
    "stop_loss_active",
    "deterministic_stop_loss",
    "delegate_failed",
)

_ID_FILTER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_FS_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_DATE_DIR_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DISPATCH_FILE_RE = re.compile(r"^dispatch-(\d+)\.json$")

_CROSS_CLASS_PLANNING_SOURCES = (
    "planning_adoption",
    "planning_adoption_reuse",
    "apply_journal",
    "apply_idempotent_noop",
    "b-route-operations",
    "completed-recovery",
    "mvg-recovery",
    "capability-recovery",
    "apply-journal.json",
    "registry.json",
)


# ---------------------------------------------------------------------------
# Strict Validation, Path Safety & Diagnostics Helpers
# ---------------------------------------------------------------------------

def _error(code: codec.ReasonCode, stage: codec.Stage, entity: Any, expected: Any, actual: Any,
           resume_ref: str | None = None) -> codec.CodecError:
    return codec.CodecError(codec.Diagnostic(
        code, stage, None if entity is None else str(entity), expected, actual, resume_ref,
    ))


def _is_safe_fs_segment(value: str | None) -> bool:
    """Only plain single-segment names ([A-Za-z0-9._-]+ without '..') may join onto a Path."""
    return (
        type(value) is str
        and bool(value)
        and value not in (".", "..")
        and ".." not in value
        and bool(_FS_SEGMENT_RE.fullmatch(value))
    )


def _validate_root(root: Any) -> Path:
    if not isinstance(root, (str, Path)) or not str(root).strip():
        raise _error(codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.PATH, None,
                     "nonempty repository root directory path", type(root).__name__)
    raw = Path(root)
    try:
        for ancestor in reversed((raw.absolute(), *raw.absolute().parents)):
            inventory.no_reparse(ancestor)
    except ValueError as exc:
        raise _error(codec.ReasonCode.UNSAFE_PATH, codec.Stage.PATH, str(root),
                     "repository root without symlink or reparse point", str(exc)[:200]) from exc
    resolved = raw.resolve()
    if not resolved.is_dir():
        raise _error(codec.ReasonCode.FILE_NOT_FOUND, codec.Stage.PATH, str(root),
                     "existing repository root directory", str(root))
    return resolved


def _check_ancestors_no_reparse(root: Path, target: Path) -> None:
    """Check every existing component from root to target (inclusive) for symlink/reparse points."""
    try:
        rel_parts = target.relative_to(root).parts
    except ValueError as exc:
        raise ValueError(f"Path outside repository root: {target}") from exc
    cur = root
    inventory.no_reparse(cur)
    for part in rel_parts:
        cur = cur / part
        if not os.path.lexists(cur):
            break
        inventory.no_reparse(cur)


def _safe_rel_path(root: Path, value: Any, *, field: str, allow_logs: bool = True) -> tuple[Path, str]:
    """Validate repo-relative path via safe_input + no_reparse BEFORE .resolve()."""
    if type(value) is not str or not value.strip() or value != value.strip():
        raise _error(codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.PATH, field,
                     "nonempty unpadded repository-relative POSIX path",
                     value if type(value) is str else type(value).__name__)
    cleaned = value.removeprefix("./") if value.startswith("./") else value
    try:
        inventory.canonical_path(cleaned, allow_logs=allow_logs)
        target = inventory.safe_input(root, cleaned, allow_logs=allow_logs)
        inventory.no_reparse(target)
    except ValueError as exc:
        raise _error(codec.ReasonCode.UNSAFE_PATH, codec.Stage.PATH, field,
                     "canonical repository-relative path without symlink or reparse point",
                     str(exc)[:200], cleaned) from exc
    return target, cleaned


def _is_reserved_producer_log_path(cleaned: str) -> bool:
    if cleaned in projection.PROTECTED_POINTERS:
        return True
    if any(cleaned == prefix or cleaned.startswith(prefix + "/") for prefix in RESERVED_PRODUCER_PREFIXES):
        return True
    parts = cleaned.split("/")
    if len(parts) >= 4 and parts[0] == "logs" and parts[1] == "ci" and _DATE_DIR_RE.fullmatch(parts[2]):
        sub = parts[3]
        if sub in _DATED_RESERVED_EXACT or any(sub.startswith(p) for p in _DATED_RESERVED_PREFIXES):
            return True
    return False


def validate_reserved_log_write_path(
    root: Path | str,
    rel_path: Any,
    *,
    suffix: str,
    field: str,
) -> tuple[Path, str, Path]:
    """Validate a canonical non-reserved logs/**/*<suffix> write path with ancestor no_reparse BEFORE .resolve()."""
    root_path = _validate_root(root)
    if type(rel_path) is not str or not rel_path.strip() or rel_path != rel_path.strip():
        raise _error(codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.PATH, field,
                     f"nonempty unpadded repository-relative non-reserved logs/**/*{suffix} path",
                     rel_path if type(rel_path) is str else type(rel_path).__name__)
    cleaned = rel_path.removeprefix("./") if rel_path.startswith("./") else rel_path
    if not cleaned.startswith("logs/") or not cleaned.lower().endswith(suffix.lower()):
        raise _error(codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.PATH, field,
                     f"repository-relative logs/**/*{suffix} path", rel_path)
    if _is_reserved_producer_log_path(cleaned):
        raise _error(codec.ReasonCode.UNSAFE_PATH, codec.Stage.PATH, field,
                     "path outside reserved operational and producer log directories", cleaned, cleaned)
    try:
        inventory.canonical_path(cleaned, allow_logs=True)
        target = inventory.safe_input(root_path, cleaned, allow_logs=True)
        inventory.no_reparse(target)
        inventory.no_reparse(target.with_name(target.name + ".tmp"))
        if suffix.lower() == ".jsonl":
            inventory.no_reparse(target.with_name(target.name + ".lock"))
        if os.path.lexists(target) and target.is_dir():
            raise ValueError(f"{field} cannot be a directory")
    except ValueError as exc:
        raise _error(codec.ReasonCode.UNSAFE_PATH, codec.Stage.PATH, field,
                     f"canonical logs/**/*{suffix} without symlink or reparse point",
                     str(exc)[:200], cleaned) from exc
    return target, cleaned, root_path


def _validate_filter(name: str, value: Any) -> str | None:
    if value is None:
        return None
    if type(value) is not str or not value.strip() or value != value.strip():
        raise _error(codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.CONTENT, name,
                     "nonempty unpadded filter string",
                     value if type(value) is str else type(value).__name__)
    if not _ID_FILTER_RE.fullmatch(value):
        raise _error(codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.CONTENT, name,
                     "canonical filter identifier", value)
    return value


def _sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _parse_iso_seconds(value: Any) -> float | None:
    if type(value) is not str or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _finite_nonneg_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    f = float(value)
    if not math.isfinite(f) or f < 0.0:
        return None
    return round(f, 4)


def _positive_or_zero_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def _first_nonneg_int(*values: Any) -> int | None:
    for val in values:
        parsed = _positive_or_zero_int(val)
        if parsed is not None:
            return parsed
    return None


def _first_nonneg_float(*values: Any) -> float | None:
    for val in values:
        parsed = _finite_nonneg_float(val)
        if parsed is not None:
            return parsed
    return None


def _normalize_attempt(value: Any, default: int | str = 1) -> int | str:
    if isinstance(value, bool) or value is None:
        return default
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def _normalize_request_identity(value: Any) -> str | None:
    """Canonicalize a dict/str request_identity without ever calling str(dict)."""
    if value is None:
        return None
    if isinstance(value, dict):
        sha = value.get("request_sha256")
        if isinstance(sha, str) and sha.strip():
            return sha.strip()
        try:
            return codec.canonical_digest(value)
        except (TypeError, ValueError):
            return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _locator(rel_path: str, sha: str | None) -> dict[str, Any]:
    return {"path": rel_path, "sha256": sha}


def classify_diagnostic_category(
    reason_code: str,
    *,
    explicit_category: str | None = None,
    expected: Any = None,
    actual: Any = None,
    producer_error_type: str | None = None,
) -> str:
    """Derive deterministic diagnostic_category strictly from authoritative ReasonCode/error origin."""
    if explicit_category in DIAGNOSTIC_CATEGORIES:
        if reason_code == codec.ReasonCode.DEPENDENCY_UNAVAILABLE.value and explicit_category == "semantic":
            return "execution_fault"
        return explicit_category
    if reason_code == codec.ReasonCode.BUDGET_EXHAUSTED.value:
        return "budget"
    if reason_code == codec.ReasonCode.DEPENDENCY_UNAVAILABLE.value:
        return "execution_fault"
    if producer_error_type:
        low = str(producer_error_type).lower()
        if any(k in low for k in _EXECUTION_FAULT_KEYWORDS):
            return "execution_fault"
        if "budget" in low:
            return "budget"
    blob = f"{expected!r} {actual!r}".lower()
    if reason_code != codec.ReasonCode.SEMANTIC_ERROR.value and any(k in blob for k in _EXECUTION_FAULT_KEYWORDS):
        return "execution_fault"
    return _REASON_TO_CATEGORY.get(reason_code, "conflict")


def normalize_unified_diagnostic(
    value: Any,
    *,
    default_entity: Any = None,
    default_resume_ref: str | None = None,
    original_locator: dict[str, Any] | None = None,
    explicit_category: str | None = None,
    producer_error_type: str | None = None,
) -> dict[str, Any]:
    """Preserve a valid six-field Diagnostic verbatim and derive diagnostic_category strictly from ReasonCode/origin."""
    if (isinstance(value, dict)
            and all(key in value for key in _DIAG_SIX_KEYS)
            and value.get("reason_code") in _REASON_VALUES
            and (value.get("stage") is None or value.get("stage") in _STAGE_VALUES)
            and (value.get("entity_id") is None or type(value.get("entity_id")) is str)
            and (value.get("resume_ref") is None or type(value.get("resume_ref")) is str)):
        rc = value["reason_code"]
        # NEVER trust raw diagnostic_category strings from untrusted disk artifacts!
        cat = classify_diagnostic_category(
            rc,
            explicit_category=explicit_category,
            expected=value.get("expected"),
            actual=value.get("actual"),
            producer_error_type=producer_error_type,
        )
        return {
            "reason_code": rc,
            "stage": value["stage"],
            "entity_id": value["entity_id"],
            "expected": value["expected"],
            "actual": value["actual"],
            "resume_ref": value["resume_ref"],
            "diagnostic_category": cat,
            "original_locator": original_locator,
        }

    # Map non-standard producer error strings/dicts without rewriting execution faults as semantic.
    raw_code = ""
    raw_actual: Any = value
    raw_expected: Any = "valid B-route governance/execution artifact"
    raw_entity = None if default_entity is None else str(default_entity)
    raw_resume = default_resume_ref
    raw_stage: str | None = codec.Stage.TARGET.value
    err_hint = producer_error_type or ""
    if isinstance(value, dict):
        raw_code = str(value.get("reason_code") or value.get("error_code") or value.get("code") or "").strip().lower()
        err_hint = str(value.get("error_type") or value.get("fault_type") or err_hint).strip().lower()
        if value.get("stage") in _STAGE_VALUES:
            raw_stage = value["stage"]
        elif value.get("stage") is None and "stage" in value:
            raw_stage = None
        if isinstance(value.get("entity_id"), str):
            raw_entity = value["entity_id"]
        if isinstance(value.get("resume_ref"), str):
            raw_resume = value["resume_ref"]
        if "expected" in value:
            raw_expected = value["expected"]
        if "actual" in value:
            raw_actual = value["actual"]
    elif isinstance(value, str):
        raw_code = value.strip().lower()

    if raw_code in _REASON_VALUES:
        mapped_code = raw_code
    elif "budget" in raw_code or "budget_exhausted" in err_hint:
        mapped_code = codec.ReasonCode.BUDGET_EXHAUSTED.value
    elif any(k in raw_code or k in err_hint for k in _EXECUTION_FAULT_KEYWORDS):
        mapped_code = codec.ReasonCode.DEPENDENCY_UNAVAILABLE.value
    elif "unknown_schema" in raw_code or "schema_version" in raw_code:
        mapped_code = codec.ReasonCode.UNKNOWN_SCHEMA.value
    elif "missing_proof" in raw_code or "unprovable" in raw_code:
        mapped_code = codec.ReasonCode.IDENTITY_UNPROVABLE.value
    elif "corrupt" in raw_code or "invalid_json" in raw_code:
        mapped_code = codec.ReasonCode.INVALID_JSON.value
    elif "digest" in raw_code:
        mapped_code = codec.ReasonCode.DIGEST_MISMATCH.value
    elif "stale" in raw_code or "drift" in raw_code or "epoch" in raw_code or "revoked" in raw_code:
        mapped_code = codec.ReasonCode.INPUT_STALE.value
    elif "pending" in raw_code:
        mapped_code = codec.ReasonCode.PENDING.value
    elif "missing" in raw_code or "not_found" in raw_code or "governance" in raw_code:
        mapped_code = codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING.value
    elif "semantic" in raw_code or "semantic" in err_hint:
        mapped_code = codec.ReasonCode.SEMANTIC_ERROR.value
    else:
        mapped_code = codec.ReasonCode.CONFLICT.value

    cat = classify_diagnostic_category(
        mapped_code,
        explicit_category=explicit_category,
        expected=raw_expected,
        actual=raw_actual,
        producer_error_type=err_hint or raw_code,
    )
    return {
        "reason_code": mapped_code,
        "stage": raw_stage,
        "entity_id": raw_entity,
        "expected": raw_expected,
        "actual": raw_actual,
        "resume_ref": raw_resume,
        "diagnostic_category": cat,
        "original_locator": original_locator,
    }


def _make_diag(
    code: codec.ReasonCode,
    stage: codec.Stage | None,
    entity_id: Any,
    expected: Any,
    actual: Any,
    resume_ref: str | None = None,
    *,
    original_locator: dict[str, Any] | None = None,
    explicit_category: str | None = None,
) -> dict[str, Any]:
    rc = code.value
    return {
        "reason_code": rc,
        "stage": stage.value if stage is not None else None,
        "entity_id": None if entity_id is None else str(entity_id),
        "expected": expected,
        "actual": actual,
        "resume_ref": resume_ref,
        "diagnostic_category": classify_diagnostic_category(
            rc, explicit_category=explicit_category, expected=expected, actual=actual,
        ),
        "original_locator": original_locator,
    }


def canonical_event_id(event_payload: dict[str, Any]) -> str:
    """Compute canonical event_id identically to _b_route_evidence_reuse.append_deduplicated_event."""
    explicit_id = event_payload.get("event_id")
    if isinstance(explicit_id, str) and explicit_id.strip():
        return explicit_id.strip()
    canonical_body = {k: v for k, v in event_payload.items() if k not in _VOLATILE_EVENT_FIELDS}
    return codec.canonical_digest(canonical_body)


def _rel_posix(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        try:
            return path.resolve().relative_to(root).as_posix()
        except ValueError:
            return path.name


# ---------------------------------------------------------------------------
# Aggregation State & Quality Floor Analyzer
# ---------------------------------------------------------------------------

class _Aggregator:
    def __init__(
        self,
        root: Path,
        *,
        operation_id: str | None = None,
        run_id: str | None = None,
        scope_id: str | None = None,
        flow_id: str | None = None,
        stage: str | None = None,
        task_id: str | None = None,
    ) -> None:
        self.root = root
        self.filter_operation_id = operation_id
        self.filter_run_id = run_id
        self.filter_scope_id = scope_id
        self.filter_flow_id = flow_id
        self.filter_stage = stage
        self.filter_task_id = task_id

        self.events: list[dict[str, Any]] = []
        self._seen_event_ids: set[str] = set()
        self.deduplicated_duplicate_events_count: int = 0

        self.diagnostics: list[dict[str, Any]] = []
        self._seen_diag_keys: set[str] = set()
        self.data_gaps: list[dict[str, Any]] = []
        self._seen_gap_keys: set[str] = set()

        # Hard fail-closed flags (cross-class reuse, timestamp refresh, corrupt/unknown schema, etc.)
        self.has_hard_conflict: bool = False
        self.original_timestamps_preserved: bool = True

        # Timing & budget accumulators
        self.active_elapsed_sum: float = 0.0
        self.measured_event_count: int = 0
        self.unmeasured_event_count: int = 0
        self.wall_clock_spans: list[dict[str, Any]] = []
        self.reserved_budget_entries: list[dict[str, Any]] = []
        self.observed_actual_dispatches: int = 0
        self.reserved_only_not_dispatched: int = 0
        self.correlated_dispatches: list[dict[str, Any]] = []
        self._seen_dispatch_keys: set[tuple[str, str]] = set()
        self.estimated_tokens_in: int = 0
        self.estimated_tokens_out: int = 0
        self.estimated_cost_usd: float = 0.0
        self.has_model_estimates: bool = False
        self.verified_billed_cost: float | None = None
        self.verified_billed_currency: str | None = None

        # Build / prewarm & test execution tracking
        self.build_prewarm_summary: dict[str, int] = {
            "dotnet_build_executed": 0,
            "dotnet_build_reused": 0,
            "godot_prewarm_executed": 0,
            "godot_prewarm_reused": 0,
        }
        self._test_executions: dict[tuple[str, str], dict[str, Any]] = {}
        self._seen_receipt_paths: set[str] = set()

        # Three strictly separate reuse classes (AC-4) with deduplication indexes
        self.planning_adoption_reuse: list[dict[str, Any]] = []
        self._planning_adoption_index: dict[tuple[str, str, str], int] = {}
        self.apply_idempotent_noop: list[dict[str, Any]] = []
        self._seen_journal_keys: set[tuple[str, str, str]] = set()
        self.runtime_build_and_test_reuse: list[dict[str, Any]] = []

        # Stop-loss, no-progress retries & rework returns (AC-5)
        self.stop_loss: dict[str, list[dict[str, Any]]] = {
            "rerun_guard": [],
            "llm_retry_stop_loss": [],
            "sc_test_retry_stop_loss": [],
            "waste_signals": [],
            "deterministic_stop_loss": [],
        }
        self._attempt_history: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.rework_returns: list[dict[str, Any]] = []

        # Quality floor regressions (AC-5)
        self.quality_regressions: list[dict[str, Any]] = []
        self._seen_regression_keys: set[str] = set()

        # Scope / obligation denominator for baseline comparison (AC-2)
        self.observed_scope_ids: set[str] = set()
        self.observed_flow_ids: set[str] = set()
        self.observed_obligation_ids: set[str] = set()

    def matches_filters(
        self,
        *,
        operation_or_run_id: str | None = None,
        scope_or_flow_id: str | None = None,
        stage: str | None = None,
        task_id: Any = None,
    ) -> bool:
        if self.filter_operation_id is not None and operation_or_run_id != self.filter_operation_id:
            return False
        if self.filter_run_id is not None and operation_or_run_id != self.filter_run_id:
            return False
        if self.filter_scope_id is not None and scope_or_flow_id != self.filter_scope_id:
            return False
        if self.filter_flow_id is not None and scope_or_flow_id != self.filter_flow_id:
            return False
        if self.filter_stage is not None and (stage or "").lower() != self.filter_stage.lower():
            return False
        if self.filter_task_id is not None:
            if task_id is None or isinstance(task_id, bool) or str(task_id) != self.filter_task_id:
                return False
        return True

    def add_diagnostic(self, diag: dict[str, Any]) -> None:
        key = codec.canonical_digest({
            "reason_code": diag.get("reason_code"),
            "stage": diag.get("stage"),
            "entity_id": diag.get("entity_id"),
            "expected": diag.get("expected"),
            "actual": diag.get("actual"),
            "resume_ref": diag.get("resume_ref"),
            "diagnostic_category": diag.get("diagnostic_category"),
        })
        if key not in self._seen_diag_keys:
            self._seen_diag_keys.add(key)
            self.diagnostics.append(diag)

    def add_data_gap(self, gap: dict[str, Any]) -> None:
        key = codec.canonical_digest(gap)
        if key not in self._seen_gap_keys:
            self._seen_gap_keys.add(key)
            self.data_gaps.append(gap)

    def add_planning_adoption_record(self, rec: dict[str, Any]) -> None:
        """Deduplicate Story 2.9 planning adoption entries by (source_transaction_id, target_run_id, capability_id)."""
        dedup_key = (
            str(rec.get("source_transaction_id") or ""),
            str(rec.get("target_run_id") or ""),
            str(rec.get("capability_id") or ""),
        )
        # Only deduplicate when at least transaction_id or capability_id is populated.
        if dedup_key != ("", "", ""):
            existing_idx = self._planning_adoption_index.get(dedup_key)
            if existing_idx is not None:
                existing = self.planning_adoption_reuse[existing_idx]
                # Revocation / epoch invalidation always wins over adopted.
                if rec.get("decision") == "revoked" and existing.get("decision") != "revoked":
                    self.planning_adoption_reuse[existing_idx] = rec
                return
            self._planning_adoption_index[dedup_key] = len(self.planning_adoption_reuse)
        self.planning_adoption_reuse.append(rec)

    def add_apply_journal_record(self, rec: dict[str, Any], *, target_path: str, phase: str) -> None:
        """Deduplicate journal entries across .json/.pending.json/operations/<id> by (operation_id, target_path, phase)."""
        jkey = (str(rec.get("operation_id") or ""), target_path, phase)
        if jkey in self._seen_journal_keys:
            return
        self._seen_journal_keys.add(jkey)
        self.apply_idempotent_noop.append(rec)

    def ingest_payload_diagnostics(self, payload: dict[str, Any], *, rel: str, sha: str | None, entity: Any = None) -> None:
        loc = _locator(rel, sha)
        raw_diags = payload.get("diagnostics")
        represented_codes: set[str] = set()
        if isinstance(raw_diags, list):
            for item in raw_diags:
                norm = normalize_unified_diagnostic(
                    item, default_entity=entity or rel, default_resume_ref=rel, original_locator=loc,
                )
                represented_codes.add(norm["reason_code"])
                self.add_diagnostic(norm)
        elif isinstance(raw_diags, dict):
            for key in ("rerun_guard", "llm_retry_stop_loss", "sc_test_retry_stop_loss", "waste_signals"):
                val = raw_diags.get(key)
                if val:
                    self.stop_loss[key].append({
                        "entity_id": str(entity or rel),
                        "locator": rel,
                        "detail": val,
                    })

        # Preserve coexisting budget & semantic/execution diagnostics even when diagnostics array is non-empty!
        if (payload.get("budget_exhausted") is True
                or payload.get("request_budget_exhausted") is True
                or payload.get("selection_block_reason") == "run_blocked_budget_exhausted"):
            self.add_diagnostic(_make_diag(
                codec.ReasonCode.BUDGET_EXHAUSTED, codec.Stage.TARGET, entity or rel,
                "remaining execution request budget",
                {"budget_exhausted": True, "selection_block_reason": payload.get("selection_block_reason")},
                rel, original_locator=loc, explicit_category="budget",
            ))

        if payload.get("execution_fault") or payload.get("runner_fault"):
            fault = payload.get("execution_fault") or payload.get("runner_fault")
            self.add_diagnostic(_make_diag(
                codec.ReasonCode.DEPENDENCY_UNAVAILABLE, codec.Stage.TARGET, entity or rel,
                "successful runner execution", fault, rel,
                original_locator=loc, explicit_category="execution_fault",
            ))

        if payload.get("semantic_error") or payload.get("semantic_findings"):
            sem = payload.get("semantic_error") or payload.get("semantic_findings")
            self.add_diagnostic(_make_diag(
                codec.ReasonCode.SEMANTIC_ERROR, codec.Stage.CONTENT, entity or rel,
                "zero semantic errors", sem, rel,
                original_locator=loc, explicit_category="semantic",
            ))

        # Top-level non-ok reason_code when not already represented in diagnostics list.
        top_rc = payload.get("reason_code")
        if isinstance(top_rc, str) and top_rc and top_rc not in ("ok", "none"):
            norm_top = normalize_unified_diagnostic(
                {
                    "reason_code": top_rc,
                    "stage": payload.get("stage") if payload.get("stage") in _STAGE_VALUES else codec.Stage.TARGET.value,
                    "entity_id": str(entity or rel),
                    "expected": "ok",
                    "actual": payload.get("reason") or payload.get("status") or top_rc,
                    "resume_ref": payload.get("resume_ref") if isinstance(payload.get("resume_ref"), str) else rel,
                    "error_type": payload.get("error_type") or payload.get("fault_type"),
                },
                default_entity=entity or rel, default_resume_ref=rel, original_locator=loc,
            )
            if norm_top["reason_code"] not in represented_codes:
                self.add_diagnostic(norm_top)

    def record_regression(
        self,
        kind: str,
        *,
        entity_id: Any,
        reason_code: codec.ReasonCode,
        detail: Any,
        rel: str,
        sha: str | None,
    ) -> None:
        if kind not in QUALITY_FLOOR_KINDS:
            return
        key = codec.canonical_digest({"kind": kind, "entity_id": str(entity_id or rel), "locator": rel, "detail": detail})
        if key in self._seen_regression_keys:
            return
        self._seen_regression_keys.add(key)
        loc = _locator(rel, sha)
        self.quality_regressions.append({
            "kind": kind,
            "entity_id": None if entity_id is None else str(entity_id),
            "reason_code": reason_code.value,
            "detail": detail,
            "original_locator": loc,
        })
        self.add_diagnostic(_make_diag(
            reason_code, codec.Stage.CONTENT, entity_id or rel,
            f"quality floor satisfied (no {kind})", detail, rel,
            original_locator=loc,
        ))

    def inspect_quality_floor(self, payload: dict[str, Any], *, rel: str, sha: str | None, entity: Any = None) -> None:
        """Inspect any governance/scope/receipt/verdict/handoff/event payload for the 5 quality-floor regressions."""
        ent = entity or payload.get("flow_id") or payload.get("scope_id") or payload.get("task_id") or payload.get("run_id") or rel

        # Track denominator for baseline comparability.
        if isinstance(payload.get("scope_id"), str) and payload["scope_id"].strip():
            self.observed_scope_ids.add(payload["scope_id"].strip())
        if isinstance(payload.get("flow_id"), str) and payload["flow_id"].strip():
            self.observed_flow_ids.add(payload["flow_id"].strip())
        for list_key in ("obligation_ids", "requested_tests"):
            items = payload.get(list_key)
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, str) and item.strip():
                        self.observed_obligation_ids.add(item.strip())
                    elif isinstance(item, dict) and isinstance(item.get("id"), str) and item["id"].strip():
                        self.observed_obligation_ids.add(item["id"].strip())

        def _nonempty_collection(val: Any) -> bool:
            if isinstance(val, list):
                return len(val) > 0
            if isinstance(val, dict):
                return any(
                    (isinstance(v, list) and len(v) > 0)
                    or (isinstance(v, dict) and len(v) > 0)
                    or (v is True)
                    or (_positive_or_zero_int(v) or 0) > 0
                    for v in val.values()
                )
            return (_positive_or_zero_int(val) or 0) > 0

        # Gather violation kinds from 3.10 defect routing arrays if present.
        violation_kinds: set[str] = set()
        for vkey in ("violations", "anti_disguise_violations"):
            vlist = payload.get(vkey)
            if isinstance(vlist, list):
                for vitem in vlist:
                    if isinstance(vitem, dict) and isinstance(vitem.get("kind"), str):
                        violation_kinds.add(vitem["kind"].strip().lower())

        # 1. source_omission (including 3A semantic_blockers, unaccounted_blocks, omitted_requirements)
        omissions = (
            payload.get("omissions")
            or payload.get("missing_sources")
            or payload.get("dropped_source_blocks")
            or payload.get("unmapped_requirements")
            or payload.get("unaccounted_blocks")
            or payload.get("omitted_requirements")
            or payload.get("semantic_blockers")
        )
        omission_count = _positive_or_zero_int(payload.get("omission_count")) or 0
        if (payload.get("source_omission") is True
                or payload.get("conservation_passed") is False
                or _nonempty_collection(omissions)
                or _nonempty_collection(payload.get("semantic_blockers"))
                or _nonempty_collection(payload.get("unaccounted_blocks"))
                or _nonempty_collection(payload.get("omitted_requirements"))
                or (payload.get("schema_version") in ("newrouge.b-route-sources-report.v1", "newrouge.b-route-source-audit.v1")
                    and payload.get("planning_eligible") is False and omission_count > 0)):
            self.record_regression(
                "source_omission", entity_id=ent, reason_code=codec.ReasonCode.SEMANTIC_ERROR,
                detail={
                    "omissions": omissions,
                    "semantic_blockers": payload.get("semantic_blockers"),
                    "unaccounted_blocks": payload.get("unaccounted_blocks"),
                    "omitted_requirements": payload.get("omitted_requirements"),
                    "conservation_passed": payload.get("conservation_passed"),
                },
                rel=rel, sha=sha,
            )

        # 2. mature_identity_drift
        drift_items = (
            payload.get("identity_drift_violations")
            or payload.get("overwritten_task_ids")
            or payload.get("mutated_contract_ids")
            or payload.get("mature_identity_changes")
        )
        if (payload.get("mature_identity_drift") is True
                or payload.get("protected_identity_mutated") is True
                or payload.get("identity_drift") is True
                or _nonempty_collection(drift_items)):
            self.record_regression(
                "mature_identity_drift", entity_id=ent, reason_code=codec.ReasonCode.CONFLICT,
                detail={"drift_items": drift_items, "mature_identity_drift": True},
                rel=rel, sha=sha,
            )

        # 3. unverified_obligation (including 3.10 acceptance_weakening/test_deletion & 4.5 verdict keys)
        cov = payload.get("coverage_summary") if isinstance(payload.get("coverage_summary"), dict) else {}
        unverified_list = payload.get("unverified_obligations") or payload.get("missing_obligations")
        not_run_blocking = _positive_or_zero_int(cov.get("not_run_blocking_count")) or 0
        skipped_count = _positive_or_zero_int(cov.get("skipped_count")) or 0
        has_310_unverified = (
            payload.get("acceptance_weakening") is True
            or _nonempty_collection(payload.get("acceptance_weakening"))
            or payload.get("test_deletion") is True
            or _nonempty_collection(payload.get("test_deletion"))
            or bool(violation_kinds & {
                "acceptance_weakened_or_deleted",
                "acceptance_weakened_against_baseline",
                "test_refs_removed",
                "test_deletion",
                "acceptance_weakening",
            })
        )
        has_45_unverified = (
            _nonempty_collection(payload.get("evidence_tier_violations"))
            or _nonempty_collection(payload.get("skipped_tests"))
            or _nonempty_collection(payload.get("missing_flow_obligations"))
            or payload.get("cross_snapshot_splicing_detected") is True
        )
        if (payload.get("unverified_obligation") is True
                or payload.get("empty_report") is True
                or payload.get("evidence_tier_substituted") is True
                or not_run_blocking > 0
                or skipped_count > 0
                or _nonempty_collection(unverified_list)
                or has_310_unverified
                or has_45_unverified):
            self.record_regression(
                "unverified_obligation", entity_id=ent, reason_code=codec.ReasonCode.REQUIRED_GOVERNANCE_MISSING,
                detail={
                    "not_run_blocking_count": not_run_blocking,
                    "skipped_count": skipped_count,
                    "empty_report": payload.get("empty_report") is True,
                    "evidence_tier_substituted": payload.get("evidence_tier_substituted") is True,
                    "unverified_obligations": unverified_list,
                    "evidence_tier_violations": payload.get("evidence_tier_violations"),
                    "skipped_tests": payload.get("skipped_tests"),
                    "missing_flow_obligations": payload.get("missing_flow_obligations"),
                    "cross_snapshot_splicing_detected": payload.get("cross_snapshot_splicing_detected") is True,
                    "acceptance_weakening": payload.get("acceptance_weakening"),
                    "test_deletion": payload.get("test_deletion"),
                },
                rel=rel, sha=sha,
            )

        # 4. failure_reclassification (including 3.10 na_exemption & status_tampering)
        reclass = payload.get("reclassified_failed_flows") or payload.get("weakening_reasons")
        has_310_reclass = (
            payload.get("na_exemption") is True
            or _nonempty_collection(payload.get("na_exemption"))
            or payload.get("status_tampering") is True
            or _nonempty_collection(payload.get("status_tampering"))
            or bool(violation_kinds & {
                "free_text_na_exemption",
                "illegal_status_done_flip",
                "na_exemption",
                "status_tampering",
            })
        )
        if (payload.get("failure_reclassification") is True
                or payload.get("failed_flow_reclassified_to_planned") is True
                or payload.get("na_exemption_detected") is True
                or _nonempty_collection(reclass)
                or has_310_reclass):
            self.record_regression(
                "failure_reclassification", entity_id=ent, reason_code=codec.ReasonCode.CONFLICT,
                detail={
                    "reclassified_failed_flows": reclass,
                    "na_exemption_detected": payload.get("na_exemption_detected") is True or payload.get("na_exemption") is True,
                    "na_exemption": payload.get("na_exemption"),
                    "status_tampering": payload.get("status_tampering"),
                },
                rel=rel, sha=sha,
            )

        # 5. premature_out_of_scope_implementation (including 4.5 forced_premature_future_implementation)
        premature = payload.get("premature_out_of_scope_flows")
        if (payload.get("premature_out_of_scope_implementation") is True
                or payload.get("out_of_scope_future_implemented") is True
                or payload.get("out_of_scope_future_claimed_complete") is True
                or payload.get("forced_premature_future_implementation") is True
                or _nonempty_collection(payload.get("forced_premature_future_implementation"))
                or _nonempty_collection(premature)):
            self.record_regression(
                "premature_out_of_scope_implementation", entity_id=ent, reason_code=codec.ReasonCode.CONFLICT,
                detail={
                    "premature_out_of_scope_flows": premature,
                    "forced_premature_future_implementation": payload.get("forced_premature_future_implementation"),
                    "out_of_scope_future_implemented": True,
                },
                rel=rel, sha=sha,
            )

    def add_event(
        self,
        *,
        raw_event: dict[str, Any] | None,
        event_id: str | None = None,
        operation_or_run_id: str | None,
        scope_or_flow_id: str | None,
        stage: str,
        attempt: int | str,
        event_type: str,
        status: str,
        executor: dict[str, Any],
        original_locator: dict[str, Any],
        observed_active_elapsed_seconds: float | str,
        paused_or_wall_clock_seconds: float | str = "unknown",
        actual_dispatch_count: int = 0,
        build_prewarm_summary: dict[str, int] | None = None,
        reuse_refs: list[dict[str, Any]] | None = None,
        return_stage: str | None = None,
        termination_reason: str | None = None,
        task_id: Any = None,
        failed_step: str | None = None,
        reason_code: str | None = None,
        issue_count: int | None = None,
        defect_class: str | None = None,
        include_in_active_elapsed_sum: bool = True,
    ) -> bool:
        if not self.matches_filters(
            operation_or_run_id=operation_or_run_id,
            scope_or_flow_id=scope_or_flow_id,
            stage=stage,
            task_id=task_id,
        ):
            return False

        if event_id is not None and event_id.strip():
            eid = event_id.strip()
        elif raw_event is not None:
            eid = canonical_event_id(raw_event)
        else:
            eid = canonical_event_id({
                "operation_or_run_id": operation_or_run_id,
                "scope_or_flow_id": scope_or_flow_id,
                "stage": stage,
                "attempt": attempt,
                "event_type": event_type,
                "status": status,
                "original_locator": original_locator.get("path"),
                "return_stage": return_stage,
                "termination_reason": termination_reason,
            })

        if eid in self._seen_event_ids:
            self.deduplicated_duplicate_events_count += 1
            return False
        self._seen_event_ids.add(eid)

        measured = _finite_nonneg_float(observed_active_elapsed_seconds)
        if measured is not None:
            if include_in_active_elapsed_sum:
                self.active_elapsed_sum = round(self.active_elapsed_sum + measured, 4)
            self.measured_event_count += 1
            active_val: float | str = measured
        else:
            self.unmeasured_event_count += 1
            active_val = "unknown"
            self.add_data_gap({
                "kind": "unmeasured_active_elapsed",
                "locator": original_locator.get("path"),
                "reason_code": codec.ReasonCode.MISSING_REQUIRED_FIELD.value,
                "detail": f"event {eid} has unmeasured observed_active_elapsed_seconds",
            })

        wall_val: float | str = _finite_nonneg_float(paused_or_wall_clock_seconds)
        if wall_val is None:
            wall_val = "unknown"
        else:
            self.wall_clock_spans.append({
                "event_id": eid,
                "operation_or_run_id": operation_or_run_id,
                "stage": stage,
                "paused_or_wall_clock_seconds": wall_val,
                "is_active_elapsed": False,
                "original_locator": original_locator,
            })

        bp = build_prewarm_summary or {
            "dotnet_build_executed": 0,
            "dotnet_build_reused": 0,
            "godot_prewarm_executed": 0,
            "godot_prewarm_reused": 0,
        }
        safe_disp = _positive_or_zero_int(actual_dispatch_count) or 0
        event_obj = {
            "event_id": eid,
            "operation_or_run_id": operation_or_run_id,
            "scope_or_flow_id": scope_or_flow_id,
            "stage": stage,
            "attempt": attempt,
            "task_id": None if (task_id is None or isinstance(task_id, bool)) else str(task_id),
            "event_type": event_type,
            "status": status,
            "executor": {
                "producer": executor.get("producer"),
                "runner": executor.get("runner"),
                "consumer": executor.get("consumer"),
            },
            "original_locator": original_locator,
            "observed_active_elapsed_seconds": active_val,
            "paused_or_wall_clock_seconds": wall_val,
            "actual_dispatch_count": safe_disp,
            "build_prewarm_summary": dict(bp),
            "duplicate_test_executions": [],
            "reuse_refs": list(reuse_refs or []),
            "return_stage": return_stage,
            "termination_reason": termination_reason,
        }
        if not include_in_active_elapsed_sum and measured is not None:
            event_obj["elapsed_rollup_of_dispatches"] = True
        self.events.append(event_obj)

        if return_stage:
            self.rework_returns.append({
                "from_stage": stage,
                "return_stage": str(return_stage),
                "reason_code": reason_code or termination_reason,
                "defect_class": defect_class or (raw_event or {}).get("defect_class"),
                "entity_id": str(task_id or scope_or_flow_id or operation_or_run_id or eid),
                "original_locator": original_locator,
            })

        if status.lower() in ("fail", "failed", "blocked", "stopped", "error", "indeterminate"):
            key_entity = str(task_id or scope_or_flow_id or operation_or_run_id or "")
            if key_entity:
                self._attempt_history.setdefault((key_entity, stage), []).append({
                    "attempt": attempt,
                    "reason_code": reason_code or termination_reason or status,
                    "failed_step": failed_step or "",
                    "issue_count": issue_count,
                    "locator": original_locator.get("path"),
                })
        return True

    def record_model_estimates(self, payload: dict[str, Any]) -> None:
        tok_in = _first_nonneg_int(payload.get("estimated_tokens_in"), payload.get("input_tokens"))
        tok_out = _first_nonneg_int(payload.get("estimated_tokens_out"), payload.get("output_tokens"))
        est_usd = _finite_nonneg_float(payload.get("estimated_cost_usd"))
        if tok_in is not None:
            self.estimated_tokens_in += tok_in
            self.has_model_estimates = True
        if tok_out is not None:
            self.estimated_tokens_out += tok_out
            self.has_model_estimates = True
        if est_usd is not None:
            self.estimated_cost_usd = round(self.estimated_cost_usd + est_usd, 6)
            self.has_model_estimates = True

        # Only accept explicitly verified billing receipts (never estimates/reservations).
        receipt = payload.get("verified_billing_receipt")
        if isinstance(receipt, dict) and receipt.get("verified") is True:
            amt = _finite_nonneg_float(receipt.get("billed_amount"))
            if amt is not None:
                self.verified_billed_cost = round((self.verified_billed_cost or 0.0) + amt, 6)
                self.verified_billed_currency = str(receipt.get("currency") or "USD")

    def compute_no_progress_retries(self) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for (entity_id, stage), hist in sorted(self._attempt_history.items()):
            if len(hist) < 2:
                continue
            for prev, curr in zip(hist, hist[1:]):
                same_failure = (
                    prev["reason_code"] == curr["reason_code"]
                    and prev["failed_step"] == curr["failed_step"]
                )
                non_decreasing_issues = (
                    prev["issue_count"] is not None
                    and curr["issue_count"] is not None
                    and curr["issue_count"] >= prev["issue_count"]
                )
                if same_failure or non_decreasing_issues:
                    results.append({
                        "entity_id": entity_id,
                        "stage": stage,
                        "attempts": [prev["attempt"], curr["attempt"]],
                        "reason_code": curr["reason_code"],
                        "failed_step": curr["failed_step"] or None,
                        "issue_counts": [prev["issue_count"], curr["issue_count"]],
                        "locators": [prev["locator"], curr["locator"]],
                    })
        return results

    def compute_duplicate_test_executions(self) -> list[dict[str, Any]]:
        dups: list[dict[str, Any]] = []
        for (snap, selector), info in sorted(self._test_executions.items()):
            if info["fresh_execution_count"] > 1:
                dups.append({
                    "selector": selector,
                    "snapshot_digest": snap,
                    "fresh_execution_count": info["fresh_execution_count"],
                    "reused_skip_count": info["reused_skip_count"],
                    "run_ids": sorted(info["run_ids"]),
                    "locators": sorted(info["locators"]),
                })
        return dups


# ---------------------------------------------------------------------------
# Bounded Safe Disk Readers
# ---------------------------------------------------------------------------

def _safe_children(
    directory: Path,
    agg: _Aggregator,
    *,
    dirs_only: bool = False,
    files_only: bool = False,
    limit: int = MAX_FILES_PER_DIR,
    sort_by_mtime_desc: bool = False,
) -> list[Path]:
    """Bounded one-level directory listing with ancestor + child reparse-point checks (never rglob)."""
    root = agg.root
    try:
        _check_ancestors_no_reparse(root, directory)
    except ValueError as exc:
        rel = _rel_posix(root, directory)
        diag = _make_diag(
            codec.ReasonCode.UNSAFE_PATH, codec.Stage.PATH, rel,
            "directory and ancestors without symlink or reparse point", str(exc)[:200], rel,
            original_locator=_locator(rel, None),
        )
        agg.add_diagnostic(diag)
        agg.add_data_gap({"kind": "unsafe_path", "locator": rel, "reason_code": diag["reason_code"], "detail": str(exc)[:200]})
        return []
    if not os.path.lexists(directory):
        return []
    if not directory.is_dir():
        return []
    entries: list[tuple[int, str, Path]] = []
    try:
        with os.scandir(directory) as it:
            for entry in it:
                child = Path(entry.path)
                try:
                    inventory.no_reparse(child)
                except ValueError as exc:
                    rel = _rel_posix(root, child)
                    diag = _make_diag(
                        codec.ReasonCode.UNSAFE_PATH, codec.Stage.PATH, rel,
                        "entry without symlink or reparse point", str(exc)[:200], rel,
                        original_locator=_locator(rel, None),
                    )
                    agg.add_diagnostic(diag)
                    agg.add_data_gap({"kind": "unsafe_path", "locator": rel, "reason_code": diag["reason_code"], "detail": str(exc)[:200]})
                    continue
                is_dir = child.is_dir()
                if dirs_only and not is_dir:
                    continue
                if files_only and is_dir:
                    continue
                try:
                    mtime_ns = child.lstat().st_mtime_ns
                except OSError:
                    mtime_ns = 0
                entries.append((mtime_ns, entry.name, child))
    except OSError as exc:
        rel = _rel_posix(root, directory)
        diag = _make_diag(
            codec.ReasonCode.READ_ERROR, codec.Stage.PATH, rel,
            "readable log directory", str(exc)[:200], rel,
            original_locator=_locator(rel, None),
        )
        agg.add_diagnostic(diag)
        agg.add_data_gap({"kind": "unreadable_directory", "locator": rel, "reason_code": diag["reason_code"], "detail": str(exc)[:200]})
        return []

    if sort_by_mtime_desc:
        entries.sort(key=lambda row: (row[0], row[1]), reverse=True)
    else:
        entries.sort(key=lambda row: row[1], reverse=True)
    if len(entries) > limit:
        rel = _rel_posix(root, directory)
        agg.add_data_gap({
            "kind": "bounded_scan_truncated",
            "locator": rel,
            "reason_code": codec.ReasonCode.MISSING_REQUIRED_FIELD.value,
            "detail": f"directory listing truncated at limit={limit} (total={len(entries)})",
            "limit": limit,
            "total_entries": len(entries),
        })
    return [row[2] for row in entries[:limit]]


def _read_strict_json(
    agg: _Aggregator,
    path: Path,
    *,
    validate_schema_version: bool = True,
) -> tuple[dict[str, Any] | None, str | None, str]:
    """Read and strict-decode a JSON object file; emit deduplicated diagnostics on reparse/corruption/unknown schema."""
    root = agg.root
    rel = _rel_posix(root, path)
    try:
        _check_ancestors_no_reparse(root, path)
    except ValueError as exc:
        diag = _make_diag(
            codec.ReasonCode.UNSAFE_PATH, codec.Stage.PATH, rel,
            "regular JSON file and ancestors without symlink or reparse point", str(exc)[:200], rel,
            original_locator=_locator(rel, None),
        )
        agg.add_diagnostic(diag)
        agg.add_data_gap({"kind": "unsafe_path", "locator": rel, "reason_code": diag["reason_code"], "detail": str(exc)[:200]})
        return None, None, rel
    if not os.path.lexists(path):
        return None, None, rel
    if not path.is_file():
        return None, None, rel
    try:
        raw = path.read_bytes()
    except OSError as exc:
        diag = _make_diag(
            codec.ReasonCode.READ_ERROR, codec.Stage.PATH, rel,
            "readable JSON artifact", str(exc)[:200], rel,
            original_locator=_locator(rel, None),
        )
        agg.add_diagnostic(diag)
        agg.add_data_gap({"kind": "read_error", "locator": rel, "reason_code": diag["reason_code"], "detail": str(exc)[:200]})
        return None, None, rel

    sha = _sha256_bytes(raw)
    loc = _locator(rel, sha)
    try:
        data = codec.strict_json_loads(raw)
    except codec.CodecError as err:
        d = err.diagnostic
        diag = _make_diag(
            d.reason_code, d.stage, rel, d.expected, d.actual, rel,
            original_locator=loc,
        )
        agg.add_diagnostic(diag)
        agg.add_data_gap({"kind": "corrupt_json", "locator": rel, "reason_code": diag["reason_code"], "detail": str(d.actual)})
        return None, sha, rel

    if not isinstance(data, dict):
        diag = _make_diag(
            codec.ReasonCode.INVALID_TYPE, codec.Stage.CONTENT, rel,
            "JSON object artifact", type(data).__name__, rel,
            original_locator=loc,
        )
        agg.add_diagnostic(diag)
        agg.add_data_gap({"kind": "corrupt_json", "locator": rel, "reason_code": diag["reason_code"], "detail": type(data).__name__})
        return None, sha, rel

    if validate_schema_version and "schema_version" in data:
        sv = data.get("schema_version")
        if type(sv) is not str or sv not in _KNOWN_SCHEMA_VERSIONS:
            diag = _make_diag(
                codec.ReasonCode.UNKNOWN_SCHEMA, codec.Stage.SCHEMA, rel,
                "known B-route or runtime schema_version", sv, rel,
                original_locator=loc,
                explicit_category="unknown_version",
            )
            agg.add_diagnostic(diag)
            agg.add_data_gap({"kind": "unknown_schema_version", "locator": rel, "reason_code": diag["reason_code"], "detail": str(sv)})
    return data, sha, rel


def _read_strict_jsonl(
    agg: _Aggregator,
    path: Path,
) -> tuple[list[tuple[int, dict[str, Any]]], str | None, str]:
    """Read a JSONL file strictly line-by-line; corrupt lines or unknown schema_version emit diagnostics & data_gaps."""
    root = agg.root
    rel = _rel_posix(root, path)
    try:
        _check_ancestors_no_reparse(root, path)
    except ValueError as exc:
        diag = _make_diag(
            codec.ReasonCode.UNSAFE_PATH, codec.Stage.PATH, rel,
            "regular JSONL file and ancestors without symlink or reparse point", str(exc)[:200], rel,
            original_locator=_locator(rel, None),
        )
        agg.add_diagnostic(diag)
        agg.add_data_gap({"kind": "unsafe_path", "locator": rel, "reason_code": diag["reason_code"], "detail": str(exc)[:200]})
        return [], None, rel
    if not os.path.lexists(path):
        return [], None, rel
    if not path.is_file():
        return [], None, rel
    try:
        raw = path.read_bytes()
    except OSError as exc:
        diag = _make_diag(
            codec.ReasonCode.READ_ERROR, codec.Stage.PATH, rel,
            "readable JSONL events log", str(exc)[:200], rel,
            original_locator=_locator(rel, None),
        )
        agg.add_diagnostic(diag)
        agg.add_data_gap({"kind": "read_error", "locator": rel, "reason_code": diag["reason_code"], "detail": str(exc)[:200]})
        return [], None, rel

    sha = _sha256_bytes(raw)
    loc = _locator(rel, sha)
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        diag = _make_diag(
            codec.ReasonCode.INVALID_UTF8, codec.Stage.DECODE, rel,
            "UTF-8 JSONL file", str(exc)[:200], rel,
            original_locator=loc,
        )
        agg.add_diagnostic(diag)
        agg.add_data_gap({"kind": "corrupt_jsonl", "locator": rel, "reason_code": diag["reason_code"], "detail": "invalid UTF-8"})
        return [], sha, rel

    all_lines = text.splitlines()
    if len(all_lines) > MAX_JSONL_LINES:
        agg.add_data_gap({
            "kind": "bounded_scan_truncated",
            "locator": rel,
            "reason_code": codec.ReasonCode.MISSING_REQUIRED_FIELD.value,
            "detail": f"JSONL lines truncated at limit={MAX_JSONL_LINES} (total={len(all_lines)})",
            "limit": MAX_JSONL_LINES,
            "total_entries": len(all_lines),
        })

    rows: list[tuple[int, dict[str, Any]]] = []
    for line_no, raw_line in enumerate(all_lines[:MAX_JSONL_LINES], start=1):
        stripped = raw_line.strip()
        if not stripped:
            continue
        try:
            parsed = codec.strict_json_loads(stripped)
        except codec.CodecError as err:
            d = err.diagnostic
            diag = _make_diag(
                d.reason_code, d.stage, f"{rel}:{line_no}", d.expected, d.actual, rel,
                original_locator=loc,
            )
            agg.add_diagnostic(diag)
            agg.add_data_gap({"kind": "corrupt_jsonl_line", "locator": f"{rel}:{line_no}", "reason_code": diag["reason_code"], "detail": str(d.actual)})
            continue
        if not isinstance(parsed, dict):
            diag = _make_diag(
                codec.ReasonCode.INVALID_TYPE, codec.Stage.DECODE, f"{rel}:{line_no}",
                "JSON object line", type(parsed).__name__, rel,
                original_locator=loc,
            )
            agg.add_diagnostic(diag)
            agg.add_data_gap({"kind": "corrupt_jsonl_line", "locator": f"{rel}:{line_no}", "reason_code": diag["reason_code"], "detail": type(parsed).__name__})
            continue
        if "schema_version" in parsed:
            sv = parsed.get("schema_version")
            if type(sv) is not str or sv not in _KNOWN_SCHEMA_VERSIONS:
                diag = _make_diag(
                    codec.ReasonCode.UNKNOWN_SCHEMA, codec.Stage.SCHEMA, f"{rel}:{line_no}",
                    "known B-route or runtime schema_version", sv, rel,
                    original_locator=loc,
                    explicit_category="unknown_version",
                )
                agg.add_diagnostic(diag)
                agg.add_data_gap({"kind": "unknown_schema_version", "locator": f"{rel}:{line_no}", "reason_code": diag["reason_code"], "detail": str(sv)})
                continue
        rows.append((line_no, parsed))
    return rows, sha, rel


# ---------------------------------------------------------------------------
# Per-Source Bounded Scanners
# ---------------------------------------------------------------------------

def _wall_clock_from_payload(payload: dict[str, Any]) -> float | str:
    explicit = _first_nonneg_float(
        payload.get("paused_or_wall_clock_seconds"),
        payload.get("wall_clock_seconds"),
    )
    if explicit is not None:
        return explicit
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    m_wall = _first_nonneg_float(
        metrics.get("paused_or_wall_clock_seconds"),
        metrics.get("wall_clock_seconds"),
        metrics.get("total_wall_clock_seconds"),
    )
    if m_wall is not None:
        return m_wall
    t0 = _parse_iso_seconds(payload.get("started_at") or payload.get("generated_at") or payload.get("created_at"))
    t1 = _parse_iso_seconds(payload.get("finished_at") or payload.get("completed_at") or payload.get("updated_at"))
    if t0 is not None and t1 is not None and t1 >= t0:
        return round(t1 - t0, 4)
    return "unknown"


def _active_elapsed_from_payload(payload: dict[str, Any]) -> float | str:
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    val = _first_nonneg_float(
        payload.get("observed_active_elapsed_seconds"),
        payload.get("active_elapsed_seconds"),
        metrics.get("observed_active_elapsed_seconds"),
        metrics.get("active_elapsed_seconds"),
        metrics.get("observed_elapsed_seconds"),
        payload.get("elapsed_seconds"),
    )
    return val if val is not None else "unknown"


def _scan_3a_sources(agg: _Aggregator) -> None:
    ci_root = agg.root / "logs" / "ci"
    candidates: list[Path] = []

    # Direct logs/ci/b-route-source-audit/<run>/<attempt>/report.json
    direct_audit = ci_root / "b-route-source-audit"
    for run_dir in _safe_children(direct_audit, agg, dirs_only=True, limit=MAX_PLANNER_RUN_DIRS):
        if agg.filter_run_id and run_dir.name != agg.filter_run_id:
            continue
        if os.path.lexists(run_dir / "report.json"):
            candidates.append(run_dir / "report.json")
        for att_dir in _safe_children(run_dir, agg, dirs_only=True, limit=50):
            if os.path.lexists(att_dir / "report.json"):
                candidates.append(att_dir / "report.json")

    # Date folders logs/ci/<YYYY-MM-DD>/b-route-sources|b-route-source-audit
    for date_dir in _safe_children(ci_root, agg, dirs_only=True, limit=MAX_LOG_DATES):
        if not _DATE_DIR_RE.fullmatch(date_dir.name):
            continue
        for sub_name in ("b-route-sources", "b-route-source-audit"):
            base = date_dir / sub_name
            for run_dir in _safe_children(base, agg, dirs_only=True, limit=MAX_PLANNER_RUN_DIRS):
                if agg.filter_run_id and run_dir.name != agg.filter_run_id:
                    continue
                if os.path.lexists(run_dir / "report.json"):
                    candidates.append(run_dir / "report.json")
                for child in _safe_children(run_dir, agg, dirs_only=True, limit=50):
                    if os.path.lexists(child / "report.json"):
                        candidates.append(child / "report.json")
                    for leaf in _safe_children(child, agg, dirs_only=True, limit=20):
                        if os.path.lexists(leaf / "report.json"):
                            candidates.append(leaf / "report.json")

    for report_path in candidates:
        data, sha, rel = _read_strict_json(agg, report_path)
        if data is None:
            continue
        run_id = str(data.get("run_id") or report_path.parent.parent.name)
        scope_id = data.get("scope_id") if isinstance(data.get("scope_id"), str) else None
        attempt = _normalize_attempt(
            data.get("attempt_id") if data.get("attempt_id") is not None else data.get("attempt"),
            default=report_path.parent.name,
        )
        disp = _first_nonneg_int(
            data.get("runner_dispatch_count"),
            data.get("actual_dispatches"),
            data.get("dispatches_used"),
        ) or 0
        if not agg.matches_filters(operation_or_run_id=run_id, scope_or_flow_id=scope_id, stage="3A"):
            continue
        newly_added = agg.add_event(
            raw_event=None,
            operation_or_run_id=run_id,
            scope_or_flow_id=scope_id,
            stage="3A",
            attempt=attempt,
            event_type=str(data.get("stage") or "3a_source_audit"),
            status=str(data.get("status") or ("ok" if data.get("ok") or data.get("planning_eligible") else "blocked")),
            executor={
                "producer": "b-route-sources",
                "runner": data.get("runner") or data.get("model"),
                "consumer": "3b-planning-gate",
            },
            original_locator=_locator(rel, sha),
            observed_active_elapsed_seconds=_active_elapsed_from_payload(data),
            paused_or_wall_clock_seconds=_wall_clock_from_payload(data),
            actual_dispatch_count=disp,
            return_stage=data.get("return_stage") if isinstance(data.get("return_stage"), str) else None,
            termination_reason=data.get("termination_reason") or data.get("reason") or data.get("reason_code"),
        )
        if not newly_added:
            continue
        agg.ingest_payload_diagnostics(data, rel=rel, sha=sha, entity=run_id)
        agg.inspect_quality_floor(data, rel=rel, sha=sha, entity=scope_id or run_id)
        agg.record_model_estimates(data)
        if disp > 0:
            agg.observed_actual_dispatches += disp


def _is_receipt_dispatched(rdata: dict[str, Any]) -> bool:
    """Return True only when a dispatch receipt reflects an actual execution (not status=='reserved' without outcome)."""
    r_status = str(rdata.get("status") or "").strip().lower()
    outcome = rdata.get("outcome")
    if r_status == "reserved":
        return isinstance(outcome, dict) and bool(outcome) and str(outcome.get("status") or "").strip().lower() != "reserved"
    return bool(r_status) or (isinstance(outcome, dict) and bool(outcome))


def _scan_3b_planning_runs(agg: _Aggregator) -> None:
    """Bounded 1-level scan of 3B planning runs; NEVER rglob over mvg/capability-planning!"""
    ci_root = agg.root / "logs" / "ci"

    # 1. b-route-planning-input/<run_id>/report.json
    pi_root = ci_root / "b-route-planning-input"
    if agg.filter_run_id and _is_safe_fs_segment(agg.filter_run_id):
        cand = pi_root / agg.filter_run_id
        try:
            _check_ancestors_no_reparse(agg.root, cand)
            pi_dirs = [cand] if os.path.lexists(cand) else []
        except ValueError as exc:
            rel = _rel_posix(agg.root, cand)
            agg.add_diagnostic(_make_diag(
                codec.ReasonCode.UNSAFE_PATH, codec.Stage.PATH, rel,
                "directory without symlink or reparse point", str(exc)[:200], rel,
                original_locator=_locator(rel, None),
            ))
            pi_dirs = []
    else:
        pi_dirs = _safe_children(pi_root, agg, dirs_only=True, limit=MAX_PLANNER_RUN_DIRS, sort_by_mtime_desc=True)

    for rdir in pi_dirs:
        rep = rdir / "report.json"
        if not os.path.lexists(rep):
            continue
        data, sha, rel = _read_strict_json(agg, rep)
        if data is None:
            continue
        rid = str(data.get("run_id") or rdir.name)
        sid = data.get("scope_id") if isinstance(data.get("scope_id"), str) else None
        if not agg.matches_filters(operation_or_run_id=rid, scope_or_flow_id=sid, stage="3B"):
            continue
        newly_added = agg.add_event(
            raw_event=None,
            operation_or_run_id=rid,
            scope_or_flow_id=sid,
            stage="3B",
            attempt=_normalize_attempt(data.get("attempt"), default=1),
            event_type="3b_planning_input",
            status=str(data.get("status") or ("ok" if data.get("ok") else "blocked")),
            executor={"producer": "b-route-planning-input", "runner": None, "consumer": "3b-planner"},
            original_locator=_locator(rel, sha),
            observed_active_elapsed_seconds=_active_elapsed_from_payload(data),
            paused_or_wall_clock_seconds=_wall_clock_from_payload(data),
            termination_reason=data.get("termination_reason") or data.get("reason_code"),
        )
        if newly_added:
            agg.ingest_payload_diagnostics(data, rel=rel, sha=sha, entity=rid)
            agg.inspect_quality_floor(data, rel=rel, sha=sha, entity=rid)

    # 2. capability-planning/<run_id> and mvg-planning/<run_id> (bounded newest N=50)
    for family in ("capability-planning", "mvg-planning"):
        fam_root = ci_root / family
        if agg.filter_run_id and _is_safe_fs_segment(agg.filter_run_id):
            cand = fam_root / agg.filter_run_id
            try:
                _check_ancestors_no_reparse(agg.root, cand)
                run_dirs = [cand] if os.path.lexists(cand) else []
            except ValueError as exc:
                rel = _rel_posix(agg.root, cand)
                agg.add_diagnostic(_make_diag(
                    codec.ReasonCode.UNSAFE_PATH, codec.Stage.PATH, rel,
                    "directory without symlink or reparse point", str(exc)[:200], rel,
                    original_locator=_locator(rel, None),
                ))
                run_dirs = []
        else:
            run_dirs = _safe_children(fam_root, agg, dirs_only=True, limit=MAX_PLANNER_RUN_DIRS, sort_by_mtime_desc=True)

        for rdir in run_dirs:
            if rdir.name in ("recovery", "clears"):
                continue
            run_json_path = rdir / "run.json"
            run_data, run_sha, run_rel = (None, None, _rel_posix(agg.root, run_json_path))
            if os.path.lexists(run_json_path):
                run_data, run_sha, run_rel = _read_strict_json(agg, run_json_path)

            run_id = str((run_data or {}).get("run_id") or rdir.name)
            scope_id = (run_data or {}).get("scope_id") if isinstance((run_data or {}).get("scope_id"), str) else None
            if not agg.matches_filters(operation_or_run_id=run_id, scope_or_flow_id=scope_id, stage="3B"):
                continue

            # Alias map unifies coordinator reservation_id, canonical request_identity, dispatch_id, and dispatch-<n> into 1 key.
            alias_to_canon: dict[str, str] = {}
            reservations_by_key: dict[str, dict[str, Any]] = {}
            worker_proj_by_key: dict[str, list[str]] = {}
            receipts_by_key: dict[str, tuple[dict[str, Any], str | None, str]] = {}

            def _resolve_or_register_key(
                *,
                reservation_id: Any = None,
                request_identity: Any = None,
                dispatch_id: Any = None,
                number: Any = None,
                fallback: str | None = None,
            ) -> str | None:
                aliases: list[str] = []
                res_s = reservation_id.strip() if isinstance(reservation_id, str) and reservation_id.strip() else None
                req_s = _normalize_request_identity(request_identity)
                did_s = dispatch_id.strip() if isinstance(dispatch_id, str) and dispatch_id.strip() else None
                num_i = _positive_or_zero_int(number)
                num_s = f"dispatch-{num_i}" if num_i is not None else None
                for a in (res_s, req_s, did_s, num_s):
                    if a:
                        aliases.append(a)
                if not aliases and fallback:
                    aliases.append(fallback)
                if not aliases:
                    return None
                for a in aliases:
                    if a in alias_to_canon:
                        canon = alias_to_canon[a]
                        for b in aliases:
                            alias_to_canon.setdefault(b, canon)
                        return canon
                canon = aliases[0]
                for a in aliases:
                    alias_to_canon[a] = canon
                return canon

            reserved_budget_ceiling: int | None = None
            logical_reserved_count = 0

            if isinstance(run_data, dict):
                agg.ingest_payload_diagnostics(run_data, rel=run_rel, sha=run_sha, entity=run_id)
                agg.inspect_quality_floor(run_data, rel=run_rel, sha=run_sha, entity=run_id)
                agg.record_model_estimates(run_data)

                sel = run_data.get("capability_selection") if isinstance(run_data.get("capability_selection"), dict) else {}
                for budget_key in ("mvg.run_invocation_limit", "run_invocation_limit", "request_budget", "logical_reserved_calls"):
                    val = _positive_or_zero_int(run_data.get(budget_key))
                    if val is not None:
                        reserved_budget_ceiling = max(reserved_budget_ceiling or 0, val)
                sel_inv = _positive_or_zero_int(sel.get("total_invocations"))
                if sel_inv is not None:
                    logical_reserved_count = max(logical_reserved_count, sel_inv)
                lrc = _positive_or_zero_int(run_data.get("logical_reserved_calls"))
                if lrc is not None:
                    logical_reserved_count = max(logical_reserved_count, lrc)

                # Real 3B coordinator capability_selection.calls + legacy reservation arrays.
                coord_rows: list[Any] = []
                if isinstance(sel.get("calls"), list):
                    coord_rows.extend(sel["calls"])
                for list_key in ("reservations", "candidate_attempts", "reserved_dispatches"):
                    rows = run_data.get(list_key)
                    if isinstance(rows, list):
                        coord_rows.extend(rows)

                for idx, row in enumerate(coord_rows, start=1):
                    if not isinstance(row, dict):
                        continue
                    num = _first_nonneg_int(row.get("number"), row.get("dispatch_number"))
                    dkey = _resolve_or_register_key(
                        reservation_id=row.get("reservation_id"),
                        request_identity=row.get("request_identity"),
                        dispatch_id=row.get("dispatch_id"),
                        number=num if num is not None else idx,
                    )
                    if dkey is not None:
                        reservations_by_key[dkey] = row

                # Extract Class 1 (Story 2.9) planning adoption items from selected checkpoints.
                for step in sel.get("selected", []) if isinstance(sel.get("selected"), list) else []:
                    if not isinstance(step, dict) or step.get("kind") != "adoption":
                        continue
                    adopt = step.get("adoption") if isinstance(step.get("adoption"), dict) else {}
                    # Cross-class guard: planning adoption must never claim runtime build/test or apply journal reuse.
                    claimed_cls = str(adopt.get("reuse_class") or "").strip().lower()
                    if claimed_cls in ("runtime_build_and_test_reuse", "apply_idempotent_noop"):
                        agg.has_hard_conflict = True
                        agg.add_diagnostic(_make_diag(
                            codec.ReasonCode.CONFLICT, codec.Stage.CONTENT, run_id,
                            "planning_adoption_reuse class only", claimed_cls, run_rel,
                            original_locator=_locator(run_rel, run_sha), explicit_category="conflict",
                        ))
                        continue
                    agg.add_planning_adoption_record({
                        "reuse_class": "planning_adoption_reuse",
                        "source_run_id": adopt.get("source_run_id"),
                        "source_transaction_id": adopt.get("source_transaction_id"),
                        "target_run_id": run_id,
                        "capability_id": adopt.get("capability_id") or (step.get("record") or {}).get("capability_id"),
                        "decision": "adopted",
                        "reason": adopt.get("reason") or "committed_capability_checkpoint_adopted",
                        "original_locator": _locator(run_rel, run_sha),
                    })

            # Bounded 1-2 level inspection of worker projections (candidates/ or seg/): projection.json & lineage-execution.json
            def _ingest_worker_file(pfile: Path, fallback_name: str) -> None:
                pdata, _psha, prel = _read_strict_json(agg, pfile)
                if not isinstance(pdata, dict):
                    return
                res_ids = pdata.get("reservation_ids")
                if isinstance(res_ids, list) and res_ids:
                    for rid_item in res_ids:
                        if isinstance(rid_item, str) and rid_item.strip():
                            dkey = _resolve_or_register_key(reservation_id=rid_item.strip())
                            if dkey is not None:
                                worker_proj_by_key.setdefault(dkey, []).append(prel)
                    return
                num = _first_nonneg_int(pdata.get("number"), pdata.get("dispatch_number"))
                dkey = _resolve_or_register_key(
                    reservation_id=pdata.get("reservation_id"),
                    request_identity=pdata.get("request_identity"),
                    dispatch_id=pdata.get("dispatch_id"),
                    number=num,
                    fallback=fallback_name,
                )
                if dkey is not None:
                    worker_proj_by_key.setdefault(dkey, []).append(prel)

            for proj_dir_name in ("candidates", "seg"):
                pdir = rdir / proj_dir_name
                for child in _safe_children(pdir, agg, limit=100):
                    if child.is_dir():
                        for fname in ("lineage-execution.json", "projection.json"):
                            cand_file = child / fname
                            if os.path.lexists(cand_file):
                                _ingest_worker_file(cand_file, child.name)
                        # Bounded 1-level child workspaces inside candidates/<label>/<sub_dir>/lineage-execution.json
                        for sub in _safe_children(child, agg, dirs_only=True, limit=20):
                            for rel_leaf in ("lineage-execution.json", "projection.json"):
                                lf = sub / rel_leaf
                                if os.path.lexists(lf):
                                    _ingest_worker_file(lf, sub.name)
                    elif child.suffix == ".json":
                        _ingest_worker_file(child, child.stem)

            # Bounded 1-level inspection of dispatch-receipts/dispatch-*.json
            dr_dir = rdir / "dispatch-receipts"
            for rfile in _safe_children(dr_dir, agg, files_only=True, limit=200):
                m = _DISPATCH_FILE_RE.fullmatch(rfile.name)
                if not m:
                    continue
                rdata, rsha, rrel = _read_strict_json(agg, rfile)
                if rdata is None:
                    continue
                num = _first_nonneg_int(rdata.get("number"), rdata.get("dispatch_number"))
                if num is None:
                    num = int(m.group(1))
                dkey = _resolve_or_register_key(
                    reservation_id=rdata.get("reservation_id"),
                    request_identity=rdata.get("request_identity"),
                    dispatch_id=rdata.get("dispatch_id"),
                    number=num,
                )
                if dkey is not None:
                    receipts_by_key[dkey] = (rdata, rsha, rrel)

            # Correlate into unique logical dispatches (Reservation + Worker Projection + Dispatch Receipt = 1 call!)
            all_keys = sorted(set(reservations_by_key) | set(worker_proj_by_key) | set(receipts_by_key))
            run_actual_dispatches = 0
            run_reserved_only = 0
            run_has_measured = False

            for dkey in all_keys:
                dedup_tuple = (run_id, dkey)
                if dedup_tuple in agg._seen_dispatch_keys:
                    continue
                agg._seen_dispatch_keys.add(dedup_tuple)
                res_row = reservations_by_key.get(dkey)
                proj_rels = worker_proj_by_key.get(dkey, [])
                rec_tuple = receipts_by_key.get(dkey)
                sources: list[str] = []
                if res_row is not None and run_data is not None:
                    sources.append(run_rel)
                for prel in proj_rels:
                    if prel not in sources:
                        sources.append(prel)

                dispatched = False
                eff_payload: dict[str, Any] | None = None
                eff_sha: str | None = run_sha
                eff_rel: str = run_rel

                if rec_tuple is not None:
                    rdata, rsha, rrel = rec_tuple
                    sources.append(rrel)
                    eff_payload, eff_sha, eff_rel = rdata, rsha, rrel
                    dispatched = _is_receipt_dispatched(rdata)
                elif res_row is not None:
                    outcome = res_row.get("outcome")
                    row_status = str(res_row.get("status") or "").strip().lower()
                    if isinstance(outcome, dict) and outcome and str(outcome.get("status") or "").strip().lower() != "reserved":
                        dispatched = True
                        eff_payload = {**res_row, **outcome}
                    elif row_status not in ("", "reserved"):
                        dispatched = True
                        eff_payload = res_row

                if dispatched and eff_payload is not None:
                    d_elapsed = _active_elapsed_from_payload(eff_payload)
                    newly_added = agg.add_event(
                        raw_event=None,
                        event_id=eff_payload.get("event_id") if isinstance(eff_payload.get("event_id"), str) else None,
                        operation_or_run_id=run_id,
                        scope_or_flow_id=scope_id,
                        stage="3B",
                        attempt=_normalize_attempt(
                            eff_payload.get("attempt") if eff_payload.get("attempt") is not None else eff_payload.get("number"),
                            default=1,
                        ),
                        event_type="3b_model_dispatch",
                        status=str(eff_payload.get("status") or "ok"),
                        executor={
                            "producer": family,
                            "runner": eff_payload.get("runner") or eff_payload.get("model") or eff_payload.get("provider"),
                            "consumer": "3b-coordinator",
                        },
                        original_locator=_locator(eff_rel, eff_sha),
                        observed_active_elapsed_seconds=d_elapsed,
                        paused_or_wall_clock_seconds=_wall_clock_from_payload(eff_payload),
                        actual_dispatch_count=1,
                        return_stage=eff_payload.get("return_stage") if isinstance(eff_payload.get("return_stage"), str) else None,
                        termination_reason=eff_payload.get("termination_reason") or eff_payload.get("reason_code"),
                    )
                    if newly_added:
                        agg.ingest_payload_diagnostics(eff_payload, rel=eff_rel, sha=eff_sha, entity=f"{run_id}:{dkey}")
                        agg.record_model_estimates(eff_payload)
                        run_actual_dispatches += 1
                        agg.observed_actual_dispatches += 1
                        if isinstance(d_elapsed, float):
                            run_has_measured = True
                        agg.correlated_dispatches.append({
                            "run_id": run_id,
                            "dispatch_key": dkey,
                            "counted_as": 1,
                            "dispatched": True,
                            "correlated_sources": sources,
                            "original_locator": _locator(eff_rel, eff_sha),
                        })
                else:
                    # Reservation, worker projection, or status=="reserved" stub without an actual execution outcome.
                    run_reserved_only += 1
                    agg.reserved_only_not_dispatched += 1
                    agg.correlated_dispatches.append({
                        "run_id": run_id,
                        "dispatch_key": dkey,
                        "counted_as": 0,
                        "dispatched": False,
                        "reserved_only": True,
                        "correlated_sources": sources,
                        "original_locator": _locator(eff_rel, eff_sha),
                    })

            extra_reserved = max(0, logical_reserved_count - run_actual_dispatches - run_reserved_only)
            if extra_reserved > 0:
                run_reserved_only += extra_reserved
                agg.reserved_only_not_dispatched += extra_reserved

            if reserved_budget_ceiling is not None or logical_reserved_count > 0:
                agg.reserved_budget_entries.append({
                    "run_id": run_id,
                    "family": family,
                    "reserved_request_budget": reserved_budget_ceiling if reserved_budget_ceiling is not None else logical_reserved_count,
                    "logical_reserved_calls": logical_reserved_count,
                    "observed_actual_dispatches": run_actual_dispatches,
                    "reserved_only_not_dispatched": run_reserved_only,
                    "original_locator": _locator(run_rel, run_sha),
                })

            if isinstance(run_data, dict):
                run_elapsed = _active_elapsed_from_payload(run_data)
                fallback_disp = 0 if (receipts_by_key or reservations_by_key) else (_positive_or_zero_int(run_data.get("dispatches_used")) or 0)
                newly_run = agg.add_event(
                    raw_event=None,
                    operation_or_run_id=run_id,
                    scope_or_flow_id=scope_id,
                    stage="3B",
                    attempt=_normalize_attempt(run_data.get("attempt"), default=1),
                    event_type=f"{family}_run",
                    status=str(run_data.get("selection_status") or run_data.get("status") or run_data.get("phase") or "unknown"),
                    executor={"producer": family, "runner": run_data.get("runner"), "consumer": "b-route-adoption"},
                    original_locator=_locator(run_rel, run_sha),
                    observed_active_elapsed_seconds=run_elapsed,
                    paused_or_wall_clock_seconds=_wall_clock_from_payload(run_data),
                    actual_dispatch_count=fallback_disp,
                    return_stage=run_data.get("return_stage") if isinstance(run_data.get("return_stage"), str) else None,
                    termination_reason=run_data.get("selection_block_reason") or run_data.get("termination_reason") or run_data.get("reason_code"),
                    # Never double-sum run.json roll-up elapsed time on top of per-dispatch receipts!
                    include_in_active_elapsed_sum=not run_has_measured,
                )
                if newly_run and fallback_disp > 0:
                    agg.observed_actual_dispatches += fallback_disp

            # Bounded 1-level apply-journal.json inside run dir -> Class 2 reuse
            aj_path = rdir / "apply-journal.json"
            if os.path.lexists(aj_path):
                _ingest_apply_journal(agg, aj_path, default_op_id=run_id)

            # Bounded 1-level completed-recovery/*.json -> Class 1 reuse evidence
            cr_dir = rdir / "completed-recovery"
            for cfile in _safe_children(cr_dir, agg, files_only=True, limit=50):
                if not cfile.name.endswith(".json"):
                    continue
                cdata, csha, crel = _read_strict_json(agg, cfile)
                if cdata is None:
                    continue
                csel = cdata.get("capability_selection") if isinstance(cdata.get("capability_selection"), dict) else {}
                chead = csel.get("checkpoint_head") if isinstance(csel.get("checkpoint_head"), dict) else {}
                agg.add_planning_adoption_record({
                    "reuse_class": "planning_adoption_reuse",
                    "source_run_id": cdata.get("run_id") or run_id,
                    "source_transaction_id": chead.get("transaction_id") or cdata.get("transaction_id"),
                    "target_run_id": cdata.get("target_run_id"),
                    "capability_id": cdata.get("capability_id"),
                    "decision": "revoked" if cdata.get("revoked") is True or cdata.get("epoch_invalidated") is True else "adopted",
                    "reason": "completed_recovery_revoked" if cdata.get("revoked") is True else "completed_recovery_snapshot_available",
                    "original_locator": _locator(crel, csha),
                })

    # 3. Story 2.9 recovery registries & epoch clears (Class 1 reuse)
    cleared_epochs: set[int] = set()
    for clear_dir_rel in ("logs/ci/mvg-planning/clears", "logs/ci/capability-planning/clears"):
        cdir = agg.root / clear_dir_rel
        for cf in _safe_children(cdir, agg, files_only=True, limit=50):
            if not cf.name.endswith(".json"):
                continue
            cdata, _csha, _crel = _read_strict_json(agg, cf)
            if isinstance(cdata, dict):
                ep = _positive_or_zero_int(cdata.get("cleared_epoch"))
                if ep is not None:
                    cleared_epochs.add(ep)

    for reg_rel in (
        "logs/ci/mvg-recovery/registry.json",
        "logs/ci/capability-recovery/registry.json",
        "logs/ci/mvg-planning/recovery/registry.json",
        "logs/ci/capability-planning/recovery/registry.json",
    ):
        reg_path = agg.root / reg_rel
        if not os.path.lexists(reg_path):
            continue
        reg_data, reg_sha, rel = _read_strict_json(agg, reg_path)
        if not isinstance(reg_data, dict):
            continue
        reg_epoch = _positive_or_zero_int(reg_data.get("epoch"))
        revoked_set = set(reg_data.get("revoked") or []) if isinstance(reg_data.get("revoked"), list) else set()
        for entry in reg_data.get("entries", []) if isinstance(reg_data.get("entries"), list) else []:
            if not isinstance(entry, dict):
                continue
            tx = entry.get("transaction_id")
            ancestry = set(entry.get("ancestry") or []) if isinstance(entry.get("ancestry"), list) else set()
            ent_epoch = _positive_or_zero_int(entry.get("epoch"))
            epoch_invalid = (
                entry.get("epoch_invalidated") is True
                or (reg_epoch is not None and ent_epoch is not None and ent_epoch < reg_epoch)
                or (ent_epoch is not None and ent_epoch in cleared_epochs)
            )
            is_revoked = (tx in revoked_set) or bool(ancestry & revoked_set) or entry.get("revoked") is True or epoch_invalid
            src_run = entry.get("run_id")
            if agg.filter_run_id and src_run != agg.filter_run_id and entry.get("target_run_id") != agg.filter_run_id:
                continue
            if agg.filter_stage and agg.filter_stage.lower() != "3b":
                continue
            agg.add_planning_adoption_record({
                "reuse_class": "planning_adoption_reuse",
                "source_run_id": src_run,
                "source_transaction_id": tx,
                "target_run_id": entry.get("target_run_id"),
                "capability_id": entry.get("capability_id"),
                "decision": "revoked" if is_revoked else "adopted",
                "reason": (
                    "epoch_invalidated" if epoch_invalid
                    else "transaction_or_ancestry_revoked" if is_revoked
                    else "registered_committed_capability_checkpoint"
                ),
                "original_locator": _locator(rel, reg_sha),
            })


def _extract_journal_targets(data: dict[str, Any]) -> list[tuple[str, str | None]]:
    targets: list[tuple[str, str | None]] = []
    for key in ("entries", "targets"):
        rows = data.get(key)
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    trel = row.get("path") or row.get("target_path")
                    after_sha = row.get("after_sha256")
                    if isinstance(trel, str) and trel.strip():
                        targets.append((trel.strip(), after_sha if isinstance(after_sha, str) else None))
                elif isinstance(row, str) and row.strip():
                    targets.append((row.strip(), None))
    if not targets and isinstance(data.get("target_path"), str) and data["target_path"].strip():
        targets.append((data["target_path"].strip(), data.get("after_sha256") if isinstance(data.get("after_sha256"), str) else None))
    return targets


def _ingest_apply_journal(agg: _Aggregator, path: Path, *, default_op_id: str | None = None) -> None:
    """Inspect a journal/operation record read-only and classify Class 2 apply_idempotent_noop."""
    data, sha, rel = _read_strict_json(agg, path)
    if data is None:
        return
    op_id = str(data.get("operation_id") or default_op_id or path.stem)
    sv = str(data.get("schema_version") or "")
    stage = "3C" if "task-compilation" in sv or "task-preview" in rel else (
        "4" if "chapter4" in sv or "chapter4" in rel else (
            "5" if "stage5" in sv or "stage5" in rel or "chapter5" in rel else "3B"
        )
    )
    scope_id = data.get("scope_id") if isinstance(data.get("scope_id"), str) else None
    if not agg.matches_filters(
        operation_or_run_id=op_id,
        scope_or_flow_id=scope_id,
        stage=stage,
        task_id=data.get("task_id"),
    ):
        return

    status = str(data.get("status") or "").lower()
    phase = str(data.get("phase") or ("pending" if path.name.endswith(".pending.json") else status or "unknown")).lower()
    replay = str(data.get("replay_decision") or data.get("apply_decision") or data.get("decision") or "").lower()

    is_journal = (
        sv == "newrouge.planning-apply-journal.v1"
        or "apply-journal" in path.name
        or path.name.endswith(".pending.json")
        or "b-route-operations" in rel
        or sv.endswith("-operation.v1")
        or sv.endswith("-operation.v2")
        or sv.endswith("public-sync.v1")
        or sv.endswith("public-sync.v1.pending")
    )

    newly_added = agg.add_event(
        raw_event=None,
        operation_or_run_id=op_id,
        scope_or_flow_id=scope_id,
        stage=stage,
        attempt=_normalize_attempt(
            data.get("attempt") if data.get("attempt") is not None else data.get("revision"),
            default=1,
        ),
        event_type=str(data.get("event_type") or data.get("operation_kind") or sv or "governed_operation"),
        status=status or ("pending" if path.name.endswith(".pending.json") else "ok" if data.get("ok") else "unknown"),
        executor={"producer": "b-route-commit", "runner": None, "consumer": "b-route-catalog"},
        original_locator=_locator(rel, sha),
        observed_active_elapsed_seconds=_active_elapsed_from_payload(data),
        paused_or_wall_clock_seconds=_wall_clock_from_payload(data),
        reuse_refs=[{"reuse_class": "apply_idempotent_noop", "operation_id": op_id}] if is_journal else [],
        return_stage=data.get("return_stage") if isinstance(data.get("return_stage"), str) else None,
        termination_reason=data.get("termination_reason") or data.get("reason") or data.get("reason_code"),
        task_id=data.get("task_id"),
    )
    if not newly_added:
        return

    agg.ingest_payload_diagnostics(data, rel=rel, sha=sha, entity=op_id)
    agg.inspect_quality_floor(data, rel=rel, sha=sha, entity=op_id)

    if is_journal:
        targets = _extract_journal_targets(data)
        all_match_after = False
        if targets:
            matched = 0
            checked = 0
            for trel, after_sha in targets:
                if after_sha is None:
                    continue
                checked += 1
                try:
                    tpath = inventory.safe_input(agg.root, trel, allow_logs=True)
                    inventory.no_reparse(tpath)
                    if tpath.is_file() and _sha256_bytes(tpath.read_bytes()) == after_sha:
                        matched += 1
                except (ValueError, OSError):
                    pass
            all_match_after = (checked > 0 and matched == checked)

        if replay in ("noop", "idempotent_noop") or data.get("idempotent_noop") is True or (status == "complete" and all_match_after):
            decision = "idempotent_noop"
            reason = str(data.get("reason") or "target_bytes_match_after_sha256")
        elif status in ("conflict", "blocked", "failed", "pending") or phase == "pending" or replay in ("conflict", "conflict_blocked"):
            decision = "conflict_blocked"
            reason = str(data.get("reason") or status or phase or "conflict_or_pending_journal")
        else:
            decision = "applied"
            reason = str(data.get("reason") or status or "journal_applied")

        target_key = ",".join(sorted(t[0] for t in targets)) if targets else rel
        agg.add_apply_journal_record(
            {
                "reuse_class": "apply_idempotent_noop",
                "operation_id": op_id,
                "phase": phase,
                "target_path": target_key,
                "journal_locator": _locator(rel, sha),
                "decision": decision,
                "reason": reason,
                "original_locator": _locator(rel, sha),
            },
            target_path=target_key,
            phase=phase,
        )


def _scan_governed_operations(agg: _Aggregator) -> None:
    ci_root = agg.root / "logs" / "ci"

    # logs/ci/b-route-operations/*.json (incl. *.pending.json) and operations/<hash>/*.json
    ops_root = ci_root / "b-route-operations"
    for f in _safe_children(ops_root, agg, files_only=True, limit=MAX_OPERATION_DIRS):
        if f.name.endswith(".json"):
            _ingest_apply_journal(agg, f)
    ops_sub = ops_root / "operations"
    if agg.filter_operation_id:
        op_hash = hashlib.sha256(agg.filter_operation_id.encode("utf-8")).hexdigest()
        cand_dirs = [ops_sub / op_hash]
        if _is_safe_fs_segment(agg.filter_operation_id):
            cand_dirs.append(ops_sub / agg.filter_operation_id)
        op_dirs: list[Path] = []
        for d in cand_dirs:
            try:
                _check_ancestors_no_reparse(agg.root, d)
                if os.path.lexists(d):
                    op_dirs.append(d)
            except ValueError as exc:
                rel = _rel_posix(agg.root, d)
                agg.add_diagnostic(_make_diag(
                    codec.ReasonCode.UNSAFE_PATH, codec.Stage.PATH, rel,
                    "directory without symlink or reparse point", str(exc)[:200], rel,
                    original_locator=_locator(rel, None),
                ))
    else:
        op_dirs = _safe_children(ops_sub, agg, dirs_only=True, limit=MAX_OPERATION_DIRS)
    for odir in op_dirs:
        for f in _safe_children(odir, agg, files_only=True, limit=50):
            if f.name.endswith(".json"):
                _ingest_apply_journal(agg, f, default_op_id=odir.name)

    # Bounded 2-level scan for 3C task-compilation events.jsonl (both direct and dated logs/ci/<YYYY-MM-DD>/b-route-task-compilation)
    tc_roots: list[Path] = [ci_root / "b-route-task-compilation"]
    for date_dir in _safe_children(ci_root, agg, dirs_only=True, limit=MAX_LOG_DATES):
        if _DATE_DIR_RE.fullmatch(date_dir.name):
            tc_roots.append(date_dir / "b-route-task-compilation")
    for tc_base in tc_roots:
        for item in _safe_children(tc_base, agg, limit=MAX_OPERATION_DIRS):
            if item.is_file() and item.name.endswith(".jsonl"):
                _ingest_events_jsonl(agg, item, default_stage="3C")
            elif item.is_dir():
                for child in _safe_children(item, agg, files_only=True, limit=50):
                    if child.name.endswith(".jsonl"):
                        _ingest_events_jsonl(agg, child, default_stage="3C", default_run_id=item.name)
                    elif child.name.endswith(".json"):
                        _ingest_apply_journal(agg, child, default_op_id=item.name)

    # Bounded 2-level scan for 3C preview, Ch4 binding, Stage-5 obligations, Ch5 readiness, Ch7 slice, defect-routing, reopen
    stage_dirs = (
        ("b-route-task-preview", "3C"),
        ("b-route-chapter4-binding", "4"),
        ("b-route-stage5-obligations", "5"),
        ("b-route-chapter5-readiness", "5"),
        ("b-route-defect-routing", "rework"),
        ("b-route-reopen", "rework"),
        ("b-route-chapter7-slice", "7"),
    )
    for folder, stage_label in stage_dirs:
        base = ci_root / folder
        for item in _safe_children(base, agg, limit=MAX_OPERATION_DIRS):
            files_to_read: list[Path] = []
            if item.is_file() and item.name.endswith(".json"):
                files_to_read.append(item)
            elif item.is_dir():
                for child in _safe_children(item, agg, files_only=True, limit=50):
                    if child.name.endswith(".json"):
                        files_to_read.append(child)
                    elif child.name.endswith(".jsonl"):
                        _ingest_events_jsonl(agg, child, default_stage=stage_label, default_run_id=item.name)
            for fpath in files_to_read:
                data, sha, rel = _read_strict_json(agg, fpath)
                if data is None:
                    continue
                op_or_run = str(data.get("operation_id") or data.get("run_id") or fpath.parent.name)
                scope_or_flow = data.get("flow_id") or data.get("scope_id")
                scope_str = str(scope_or_flow) if scope_or_flow is not None else None
                if not agg.matches_filters(
                    operation_or_run_id=op_or_run,
                    scope_or_flow_id=scope_str,
                    stage=stage_label,
                    task_id=data.get("task_id"),
                ):
                    continue
                newly_added = agg.add_event(
                    raw_event=data if data.get("event_id") else None,
                    operation_or_run_id=op_or_run,
                    scope_or_flow_id=scope_str,
                    stage=stage_label,
                    attempt=_normalize_attempt(data.get("attempt"), default=1),
                    event_type=str(data.get("event_type") or data.get("defect_class") or folder),
                    status=str(data.get("status") or ("ok" if data.get("ok") else "blocked")),
                    executor={"producer": folder, "runner": data.get("runner"), "consumer": data.get("return_stage") or "downstream"},
                    original_locator=_locator(rel, sha),
                    observed_active_elapsed_seconds=_active_elapsed_from_payload(data),
                    paused_or_wall_clock_seconds=_wall_clock_from_payload(data),
                    return_stage=data.get("return_stage") if isinstance(data.get("return_stage"), str) else None,
                    termination_reason=data.get("termination_reason") or data.get("reason") or data.get("reason_code"),
                    task_id=data.get("task_id"),
                    reason_code=data.get("reason_code") if isinstance(data.get("reason_code"), str) else None,
                    defect_class=data.get("defect_class") if isinstance(data.get("defect_class"), str) else None,
                )
                if newly_added:
                    agg.ingest_payload_diagnostics(data, rel=rel, sha=sha, entity=op_or_run)
                    agg.inspect_quality_floor(data, rel=rel, sha=sha, entity=scope_or_flow or op_or_run)
                    agg.record_model_estimates(data)


def _scan_chapter6_and_runtime(agg: _Aggregator) -> None:
    ci_root = agg.root / "logs" / "ci"

    # 1. logs/ci/<YYYY-MM-DD>/sc-review-pipeline-task-* and sc-needs-fix-fast-task-*
    for date_dir in _safe_children(ci_root, agg, dirs_only=True, limit=MAX_LOG_DATES):
        if not _DATE_DIR_RE.fullmatch(date_dir.name):
            continue
        for rdir in _safe_children(date_dir, agg, dirs_only=True, limit=MAX_OPERATION_DIRS):
            if not (rdir.name.startswith("sc-review-pipeline-task-") or rdir.name.startswith("sc-needs-fix-fast-task-")):
                continue
            m = re.search(r"-task-(\d+)", rdir.name)
            dir_task_id = m.group(1) if m else None
            if agg.filter_task_id and dir_task_id != agg.filter_task_id:
                continue

            summary_path = rdir / "summary.json"
            marathon_path = rdir / "marathon-state.json"
            ctx_path = rdir / "execution-context.json"
            summary, sum_sha, sum_rel = _read_strict_json(agg, summary_path) if os.path.lexists(summary_path) else (None, None, "")
            marathon, mar_sha, mar_rel = _read_strict_json(agg, marathon_path) if os.path.lexists(marathon_path) else (None, None, "")
            ctx, _ctx_sha, _ctx_rel = _read_strict_json(agg, ctx_path) if os.path.lexists(ctx_path) else (None, None, "")

            primary = summary or marathon or ctx
            if not isinstance(primary, dict):
                continue
            primary_rel = sum_rel if summary is not None else (mar_rel if marathon is not None else _rel_posix(agg.root, ctx_path))
            primary_sha = sum_sha if summary is not None else mar_sha
            rid = str(primary.get("run_id") or rdir.name)
            tid_raw = primary.get("task_id") if primary.get("task_id") is not None else dir_task_id
            tid = None if (tid_raw is None or isinstance(tid_raw, bool)) else str(tid_raw)
            sf = primary.get("flow_id") or primary.get("scope_id")
            sf_str = str(sf) if isinstance(sf, str) else None

            if not agg.matches_filters(operation_or_run_id=rid, scope_or_flow_id=sf_str, stage="6", task_id=tid):
                continue

            resume_cnt = _positive_or_zero_int(marathon.get("resume_count")) if isinstance(marathon, dict) else None
            attempt_val = _normalize_attempt(
                primary.get("attempt"),
                default=(resume_cnt + 1) if resume_cnt is not None else 1,
            )
            newly_added = agg.add_event(
                raw_event=None,
                operation_or_run_id=rid,
                scope_or_flow_id=sf_str,
                stage="6",
                attempt=attempt_val,
                event_type=str(primary.get("cmd") or ("needs_fix_fast" if "needs-fix-fast" in rdir.name else "sc_review_pipeline")),
                status=str(primary.get("status") or "unknown"),
                executor={"producer": "chapter6-local", "runner": primary.get("runner"), "consumer": "chapter6-recovery"},
                original_locator=_locator(primary_rel, primary_sha),
                observed_active_elapsed_seconds=_active_elapsed_from_payload(primary),
                paused_or_wall_clock_seconds=_wall_clock_from_payload(primary),
                return_stage=primary.get("return_stage") if isinstance(primary.get("return_stage"), str) else None,
                termination_reason=primary.get("reason") or primary.get("stop_reason") or primary.get("reason_code"),
                task_id=tid,
                failed_step=str(primary.get("failed_step") or "") or None,
                reason_code=str(primary.get("reason_code") or primary.get("reason") or "") or None,
                issue_count=_positive_or_zero_int(primary.get("issue_count")),
            )
            if newly_added:
                for src, src_rel, src_sha in ((summary, sum_rel, sum_sha), (marathon, mar_rel, mar_sha), (ctx, _ctx_rel, _ctx_sha)):
                    if isinstance(src, dict):
                        agg.ingest_payload_diagnostics(src, rel=src_rel, sha=src_sha, entity=tid or rid)
                        agg.inspect_quality_floor(src, rel=src_rel, sha=src_sha, entity=tid or rid)
                        rsn = str(src.get("reason") or src.get("stop_reason") or "")
                        if rsn.startswith("rerun_blocked:"):
                            agg.stop_loss["rerun_guard"].append({"entity_id": tid or rid, "locator": src_rel, "detail": rsn})

            re_path = rdir / "run-events.jsonl"
            if os.path.lexists(re_path):
                _ingest_events_jsonl(agg, re_path, default_stage="6", default_run_id=rid, default_task_id=tid)

    # 2. logs/ci/project-health-knowledge/runtime/*.json
    rt_dir = ci_root / "project-health-knowledge" / "runtime"
    for rfile in _safe_children(rt_dir, agg, files_only=True, limit=MAX_PLANNER_RUN_DIRS, sort_by_mtime_desc=True):
        if not rfile.name.endswith(".json") or rfile.name == "latest.json":
            continue
        data, sha, rel = _read_strict_json(agg, rfile)
        if data is None:
            continue
        rid = str(data.get("run_id") or rfile.stem)
        sf = data.get("flow_id") or data.get("scope_id")
        sf_str = str(sf) if isinstance(sf, str) else None
        if not agg.matches_filters(operation_or_run_id=rid, scope_or_flow_id=sf_str, stage="6", task_id=data.get("task_id")):
            continue
        newly_added = agg.add_event(
            raw_event=None,
            operation_or_run_id=rid,
            scope_or_flow_id=sf_str,
            stage="6",
            attempt=_normalize_attempt(data.get("attempt"), default=1),
            event_type="project_health_runtime",
            status=str(data.get("status") or "unknown"),
            executor={"producer": "project-health-runtime", "runner": data.get("runner"), "consumer": "knowledge-backlink"},
            original_locator=_locator(rel, sha),
            observed_active_elapsed_seconds=_active_elapsed_from_payload(data),
            paused_or_wall_clock_seconds=_wall_clock_from_payload(data),
            termination_reason=data.get("reason") or data.get("reason_code"),
            task_id=data.get("task_id"),
        )
        if newly_added:
            agg.ingest_payload_diagnostics(data, rel=rel, sha=sha, entity=rid)
            agg.inspect_quality_floor(data, rel=rel, sha=sha, entity=rid)


def _is_cross_class_runtime_claim(item: dict[str, Any]) -> str | None:
    """Detect attempts to supply Story 2.9 planning adoption or apply journals as runtime build/test reuse."""
    for key in ("reuse_class", "source_class", "source_kind", "evidence_source", "reused_from", "reused_from_path", "source_locator", "reused_from_run_id"):
        val = item.get(key)
        if isinstance(val, str):
            low = val.strip().lower()
            for marker in _CROSS_CLASS_PLANNING_SOURCES:
                if marker in low:
                    return f"{key}={val}"
        elif isinstance(val, dict):
            p = str(val.get("path") or "").lower()
            for marker in _CROSS_CLASS_PLANNING_SOURCES:
                if marker in p:
                    return f"{key}.path={val.get('path')}"
    return None


def _ingest_coverage_receipt(agg: _Aggregator, path: Path) -> None:
    """Ingest Story 4.3/4.4 coverage-receipt.json (build/prewarm, shared test reuse, stop_loss, quality floor)."""
    rel_check = _rel_posix(agg.root, path)
    if rel_check in agg._seen_receipt_paths:
        return
    data, sha, rel = _read_strict_json(agg, path)
    if data is None:
        return
    run_id = str(data.get("run_id") or path.parent.name)
    scope_id = data.get("scope_id") if isinstance(data.get("scope_id"), str) else None
    flow_id = data.get("flow_id") if isinstance(data.get("flow_id"), str) else None
    snapshot_digest = str(data.get("snapshot_digest") or "unknown")

    if not agg.matches_filters(
        operation_or_run_id=run_id,
        scope_or_flow_id=flow_id or scope_id,
        stage="flow_verify",
        task_id=data.get("task_id"),
    ):
        # Also allow scope_id match when flow_id is distinct and filter_scope_id was requested.
        if not (agg.filter_scope_id and scope_id == agg.filter_scope_id and agg.matches_filters(
            operation_or_run_id=run_id, scope_or_flow_id=scope_id, stage="flow_verify", task_id=data.get("task_id")
        )):
            return

    agg._seen_receipt_paths.add(rel)

    metrics = data.get("metrics") if isinstance(data.get("metrics"), dict) else {}
    obs_disp = _positive_or_zero_int(metrics.get("observed_dispatches")) or 0
    res_disp = _positive_or_zero_int(metrics.get("reserved_dispatches"))

    # Pre-compute local build/prewarm & reuse lists, then commit ONLY if add_event returns True!
    bp_local = {
        "dotnet_build_executed": 0,
        "dotnet_build_reused": 0,
        "godot_prewarm_executed": 0,
        "godot_prewarm_reused": 0,
    }
    reuse_refs: list[dict[str, Any]] = []
    pending_runtime_reuse: list[dict[str, Any]] = []
    pending_conflicts: list[dict[str, Any]] = []
    pending_tests: list[tuple[str, str, bool]] = []

    run_timestamps: set[str] = {
        str(data[k]).strip()
        for k in ("finished_at", "generated_at", "completed_at", "executed_at")
        if isinstance(data.get(k), str) and data[k].strip()
    }

    ba = data.get("build_artifacts") if isinstance(data.get("build_artifacts"), dict) else {}
    for kind, exec_key, reuse_key in (
        ("dotnet_build", "dotnet_build_executed", "dotnet_build_reused"),
        ("godot_prewarm", "godot_prewarm_executed", "godot_prewarm_reused"),
    ):
        entry = ba.get(kind)
        if not isinstance(entry, dict):
            continue
        if entry.get("reused") is True:
            cross_hit = _is_cross_class_runtime_claim(entry)
            if cross_hit is not None:
                pending_conflicts.append(_make_diag(
                    codec.ReasonCode.CONFLICT, codec.Stage.CONTENT, f"{run_id}:{kind}",
                    "runtime build/prewarm reuse evidence only (cross-class proof forbidden)",
                    cross_hit, rel, original_locator=_locator(rel, sha), explicit_category="conflict",
                ))
                pending_runtime_reuse.append({
                    "reuse_class": "runtime_build_and_test_reuse",
                    "run_id": run_id,
                    "receipt_locator": _locator(rel, sha),
                    "reused_from_run_id": entry.get("reused_from_run_id") or entry.get("source_run_id"),
                    "kind": kind,
                    "original_executed_at": entry.get("original_executed_at") or entry.get("built_at"),
                    "decision": "rejected",
                    "reason": f"cross_class_reuse_forbidden:{cross_hit}",
                })
                continue
            orig_b_ts = entry.get("original_executed_at") or entry.get("built_at")
            if isinstance(orig_b_ts, str) and orig_b_ts.strip() and orig_b_ts.strip() in run_timestamps and entry.get("reused_from_run_id") != run_id:
                pending_conflicts.append(_make_diag(
                    codec.ReasonCode.CONFLICT, codec.Stage.CONTENT, f"{run_id}:{kind}",
                    "preserved original_executed_at distinct from reusing run timestamp",
                    {"original_executed_at": orig_b_ts, "run_timestamps": sorted(run_timestamps)},
                    rel, original_locator=_locator(rel, sha), explicit_category="conflict",
                ))
                agg.original_timestamps_preserved = False
            bp_local[reuse_key] += 1
            rec = {
                "reuse_class": "runtime_build_and_test_reuse",
                "run_id": run_id,
                "receipt_locator": _locator(rel, sha),
                "reused_from_run_id": entry.get("reused_from_run_id") or entry.get("source_run_id"),
                "kind": kind,
                "original_executed_at": orig_b_ts,
                "decision": "reused",
                "reason": entry.get("reason") or f"{kind}_identity_matched",
            }
            pending_runtime_reuse.append(rec)
            reuse_refs.append({"reuse_class": "runtime_build_and_test_reuse", "kind": kind, "reused_from_run_id": rec["reused_from_run_id"]})
        elif entry.get("executed") is True or entry.get("status") in ("ok", "passed", "built", "executed"):
            bp_local[exec_key] += 1

    for item in data.get("executed_tests", []) if isinstance(data.get("executed_tests"), list) else []:
        if not isinstance(item, dict):
            continue
        selector = str(item.get("selector") or item.get("id") or "")
        if not selector:
            continue
        if item.get("reused") is True:
            cross_hit = _is_cross_class_runtime_claim(item)
            if cross_hit is not None:
                pending_conflicts.append(_make_diag(
                    codec.ReasonCode.CONFLICT, codec.Stage.CONTENT, item.get("id") or selector,
                    "runtime shared test reuse evidence only (cross-class proof forbidden)",
                    cross_hit, rel, original_locator=_locator(rel, sha), explicit_category="conflict",
                ))
                pending_runtime_reuse.append({
                    "reuse_class": "runtime_build_and_test_reuse",
                    "run_id": run_id,
                    "receipt_locator": _locator(rel, sha),
                    "reused_from_run_id": item.get("reused_from_run_id") or item.get("source_run_id"),
                    "kind": "shared_test_evidence",
                    "test_id": item.get("id"),
                    "original_executed_at": item.get("original_executed_at"),
                    "decision": "rejected",
                    "reason": f"cross_class_reuse_forbidden:{cross_hit}",
                })
                continue
            orig_ts = item.get("original_executed_at")
            if type(orig_ts) is not str or not orig_ts.strip():
                pending_conflicts.append(_make_diag(
                    codec.ReasonCode.CONFLICT, codec.Stage.CONTENT, item.get("id") or selector,
                    "nonempty preserved original_executed_at on reused runtime test evidence",
                    orig_ts, rel, original_locator=_locator(rel, sha), explicit_category="conflict",
                ))
                agg.original_timestamps_preserved = False
            elif orig_ts.strip() in run_timestamps and item.get("reused_from_run_id") != run_id:
                pending_conflicts.append(_make_diag(
                    codec.ReasonCode.CONFLICT, codec.Stage.CONTENT, item.get("id") or selector,
                    "preserved original_executed_at from source run (must not refresh to reusing run timestamp)",
                    {"original_executed_at": orig_ts, "run_timestamps": sorted(run_timestamps)},
                    rel, original_locator=_locator(rel, sha), explicit_category="conflict",
                ))
                agg.original_timestamps_preserved = False
            pending_tests.append((snapshot_digest, selector, True))
            rec = {
                "reuse_class": "runtime_build_and_test_reuse",
                "run_id": run_id,
                "receipt_locator": _locator(rel, sha),
                "reused_from_run_id": item.get("reused_from_run_id") or item.get("source_run_id"),
                "kind": "shared_test_evidence",
                "test_id": item.get("id"),
                "original_executed_at": orig_ts,
                "decision": "reused",
                "reason": item.get("reuse_reason") or "same_snapshot_shared_test_deduplicated",
            }
            pending_runtime_reuse.append(rec)
            reuse_refs.append({"reuse_class": "runtime_build_and_test_reuse", "kind": "shared_test_evidence", "test_id": item.get("id"), "original_executed_at": orig_ts})
        else:
            pending_tests.append((snapshot_digest, selector, False))

    for rej in data.get("reuse_rejections", []) if isinstance(data.get("reuse_rejections"), list) else []:
        if not isinstance(rej, dict):
            continue
        pending_runtime_reuse.append({
            "reuse_class": "runtime_build_and_test_reuse",
            "run_id": run_id,
            "receipt_locator": _locator(rel, sha),
            "reused_from_run_id": rej.get("reused_from_run_id") or rej.get("source_run_id"),
            "kind": rej.get("kind") or "shared_test_evidence",
            "test_id": rej.get("test_id") or rej.get("id"),
            "original_executed_at": rej.get("original_executed_at"),
            "decision": "rejected",
            "reason": rej.get("reason") or rej.get("reason_code") or "reuse_rejected",
        })

    # Add event FIRST; gate all aggregate counter mutations on newly_added == True!
    newly_added = agg.add_event(
        raw_event=None,
        operation_or_run_id=run_id,
        scope_or_flow_id=flow_id or scope_id,
        stage="flow_verify",
        attempt=_normalize_attempt(data.get("attempt"), default=1),
        event_type="mvg_coverage_receipt",
        status=str(data.get("status") or "unknown"),
        executor={
            "producer": "b-route-scope-runner",
            "runner": (data.get("environment") or {}).get("runner") if isinstance(data.get("environment"), dict) else "run-mvg-acceptance",
            "consumer": "b-route-completion-verdict",
        },
        original_locator=_locator(rel, sha),
        observed_active_elapsed_seconds=_active_elapsed_from_payload(data),
        paused_or_wall_clock_seconds=_wall_clock_from_payload(data),
        actual_dispatch_count=obs_disp,
        build_prewarm_summary=bp_local,
        reuse_refs=reuse_refs,
        termination_reason=data.get("reason") or data.get("reason_code"),
        task_id=data.get("task_id"),
        reason_code=data.get("reason_code") if isinstance(data.get("reason_code"), str) else None,
    )
    if not newly_added:
        return

    agg.ingest_payload_diagnostics(data, rel=rel, sha=sha, entity=scope_id or run_id)
    agg.inspect_quality_floor(data, rel=rel, sha=sha, entity=scope_id or run_id)
    for cdiag in pending_conflicts:
        agg.has_hard_conflict = True
        agg.add_diagnostic(cdiag)

    sl = data.get("stop_loss")
    if isinstance(sl, dict) and sl.get("triggered") is True:
        agg.stop_loss["deterministic_stop_loss"].append({
            "entity_id": scope_id or run_id,
            "locator": rel,
            "source": sl.get("source"),
            "signals": sl.get("signals") or [],
            "failed_prerequisite_id": sl.get("failed_prerequisite_id"),
            "skipped_test_ids": sl.get("skipped_test_ids") or [],
        })

    for k, v in bp_local.items():
        agg.build_prewarm_summary[k] += v
    agg.runtime_build_and_test_reuse.extend(pending_runtime_reuse)
    for snap, selector, is_reused in pending_tests:
        slot = agg._test_executions.setdefault((snap, selector), {
            "fresh_execution_count": 0,
            "reused_skip_count": 0,
            "run_ids": set(),
            "locators": set(),
        })
        slot["run_ids"].add(run_id)
        slot["locators"].add(rel)
        if is_reused:
            slot["reused_skip_count"] += 1
        else:
            slot["fresh_execution_count"] += 1

    if res_disp is not None:
        agg.reserved_budget_entries.append({
            "run_id": run_id,
            "family": "mvg-acceptance",
            "reserved_request_budget": res_disp,
            "logical_reserved_calls": res_disp,
            "observed_actual_dispatches": obs_disp,
            "reserved_only_not_dispatched": max(0, res_disp - obs_disp),
            "original_locator": _locator(rel, sha),
        })
    if obs_disp > 0:
        agg.observed_actual_dispatches += obs_disp


def _scan_mvg_acceptance(agg: _Aggregator) -> None:
    acc_root = agg.root / "logs" / "ci" / "mvg-acceptance"
    if agg.filter_run_id and _is_safe_fs_segment(agg.filter_run_id):
        cand = acc_root / agg.filter_run_id
        try:
            _check_ancestors_no_reparse(agg.root, cand)
            run_dirs = [cand] if os.path.lexists(cand) else []
        except ValueError as exc:
            rel = _rel_posix(agg.root, cand)
            agg.add_diagnostic(_make_diag(
                codec.ReasonCode.UNSAFE_PATH, codec.Stage.PATH, rel,
                "directory without symlink or reparse point", str(exc)[:200], rel,
                original_locator=_locator(rel, None),
            ))
            run_dirs = []
    else:
        run_dirs = _safe_children(acc_root, agg, dirs_only=True, limit=MAX_PLANNER_RUN_DIRS, sort_by_mtime_desc=True)

    for rdir in run_dirs:
        receipt_path = rdir / "coverage-receipt.json"
        if os.path.lexists(receipt_path):
            _ingest_coverage_receipt(agg, receipt_path)
            continue
        summary_path = rdir / "summary.json"
        if os.path.lexists(summary_path):
            data, sha, rel = _read_strict_json(agg, summary_path)
            if data is None:
                continue
            rid = str(data.get("run_id") or rdir.name)
            sf = data.get("flow_id") or data.get("scope_id")
            sf_str = str(sf) if isinstance(sf, str) else None
            if not agg.matches_filters(operation_or_run_id=rid, scope_or_flow_id=sf_str, stage="flow_verify", task_id=data.get("task_id")):
                continue
            newly_added = agg.add_event(
                raw_event=None,
                operation_or_run_id=rid,
                scope_or_flow_id=sf_str,
                stage="flow_verify",
                attempt=_normalize_attempt(data.get("attempt"), default=1),
                event_type="mvg_acceptance_summary",
                status=str(data.get("status") or "unknown"),
                executor={"producer": "run-mvg-acceptance", "runner": "mvg-runner", "consumer": "b-route-completion-verdict"},
                original_locator=_locator(rel, sha),
                observed_active_elapsed_seconds=_active_elapsed_from_payload(data),
                paused_or_wall_clock_seconds=_wall_clock_from_payload(data),
                termination_reason=data.get("reason") or data.get("reason_code"),
                task_id=data.get("task_id"),
            )
            if newly_added:
                agg.ingest_payload_diagnostics(data, rel=rel, sha=sha, entity=rid)
                agg.inspect_quality_floor(data, rel=rel, sha=sha, entity=rid)


def _ingest_events_jsonl(
    agg: _Aggregator,
    path: Path,
    *,
    default_stage: str = "unknown",
    default_run_id: str | None = None,
    default_task_id: str | None = None,
) -> None:
    rows, sha, rel = _read_strict_jsonl(agg, path)
    loc = _locator(rel, sha)
    for _line_no, ev in rows:
        et = str(ev.get("event_type") or "stage_event")
        stage = str(ev.get("stage") or (
            "milestone_verify" if et == "completion_verdict_evaluated" and ev.get("level") == "milestone"
            else "flow_verify" if et in ("completion_verdict_evaluated", "mvg_run_completed", "test_executed", "test_reused")
            else "planning_page" if et == "b_route_page_stage_action"
            else default_stage
        ))
        op_or_run = str(ev.get("operation_id") or ev.get("run_id") or default_run_id or path.stem)
        scope_or_flow = ev.get("flow_id") or ev.get("scope_id")
        sf_str = str(scope_or_flow) if scope_or_flow is not None else None
        task_val = ev.get("task_id") if ev.get("task_id") is not None else default_task_id
        attempt = _normalize_attempt(
            ev.get("attempt") if ev.get("attempt") is not None else ev.get("attempt_id"),
            default=1,
        )
        disp = _first_nonneg_int(ev.get("actual_dispatch_count"), ev.get("observed_dispatches")) or 0

        # Gate ALL counter, diagnostics, estimates & quality-floor mutations on filter match + event_id dedup!
        newly_added = agg.add_event(
            raw_event=ev,
            event_id=ev.get("event_id") if isinstance(ev.get("event_id"), str) else None,
            operation_or_run_id=op_or_run,
            scope_or_flow_id=sf_str,
            stage=stage,
            attempt=attempt,
            event_type=et,
            status=str(ev.get("status") or ev.get("verdict_status") or ("ok" if ev.get("ok") else "blocked" if ev.get("ok") is False else "recorded")),
            executor={
                "producer": ev.get("producer") or et,
                "runner": ev.get("runner") or ev.get("action"),
                "consumer": ev.get("consumer") or "observability",
            },
            original_locator=loc,
            observed_active_elapsed_seconds=_active_elapsed_from_payload(ev),
            paused_or_wall_clock_seconds=_wall_clock_from_payload(ev),
            actual_dispatch_count=disp,
            return_stage=ev.get("return_stage") if isinstance(ev.get("return_stage"), str) else None,
            termination_reason=ev.get("termination_reason") or ev.get("reason") or ev.get("reason_code"),
            task_id=task_val,
            failed_step=str(ev.get("failed_step") or "") or None,
            reason_code=ev.get("reason_code") if isinstance(ev.get("reason_code"), str) else None,
            issue_count=_positive_or_zero_int(ev.get("issue_count")),
        )
        if not newly_added:
            continue
        if disp > 0:
            agg.observed_actual_dispatches += disp
        agg.ingest_payload_diagnostics(ev, rel=rel, sha=sha, entity=ev.get("entity_id") or op_or_run or rel)
        agg.inspect_quality_floor(ev, rel=rel, sha=sha, entity=sf_str or op_or_run or rel)
        agg.record_model_estimates(ev)


def _ingest_verdict_or_scope_ref(agg: _Aggregator, path: Path, rel: str) -> None:
    if not os.path.lexists(path):
        agg.add_diagnostic(_make_diag(
            codec.ReasonCode.FILE_NOT_FOUND, codec.Stage.PATH, rel,
            "existing verdict/scope/receipt/handoff JSON file", "missing", rel,
            original_locator=_locator(rel, None),
        ))
        agg.add_data_gap({"kind": "missing_verdict_ref", "locator": rel, "reason_code": codec.ReasonCode.FILE_NOT_FOUND.value, "detail": "file not found"})
        return
    data, sha, _ = _read_strict_json(agg, path)
    if data is None:
        return
    sv = str(data.get("schema_version") or "")
    if sv == "newrouge.b-route-execution-receipt.v1":
        _ingest_coverage_receipt(agg, path)
        return
    ent = str(data.get("scope_id") or data.get("flow_id") or data.get("run_id") or rel)
    op_or_run = str(data.get("operation_id") or data.get("run_id") or ent)
    sf = data.get("flow_id") or data.get("scope_id")
    sf_str = str(sf) if isinstance(sf, str) and sf.strip() else None
    stage = "milestone_verify" if data.get("level") == "milestone" else "flow_verify"
    newly_added = agg.add_event(
        raw_event=None,
        operation_or_run_id=op_or_run,
        scope_or_flow_id=sf_str,
        stage=stage,
        attempt=_normalize_attempt(data.get("attempt"), default=1),
        event_type=sv or "verdict_or_scope_artifact",
        status=str(data.get("verdict_status") or data.get("status") or ("ok" if data.get("ok") else "blocked")),
        executor={"producer": sv or "verdict", "runner": None, "consumer": "observability"},
        original_locator=_locator(rel, sha),
        observed_active_elapsed_seconds=_active_elapsed_from_payload(data),
        paused_or_wall_clock_seconds=_wall_clock_from_payload(data),
        return_stage=data.get("return_stage") if isinstance(data.get("return_stage"), str) else None,
        termination_reason=data.get("reason") or data.get("reason_code"),
        task_id=data.get("task_id"),
        reason_code=data.get("reason_code") if isinstance(data.get("reason_code"), str) else None,
    )
    if not newly_added:
        return
    agg.ingest_payload_diagnostics(data, rel=rel, sha=sha, entity=ent)
    agg.inspect_quality_floor(data, rel=rel, sha=sha, entity=ent)


# ---------------------------------------------------------------------------
# Baseline Comparison (AC-2)
# ---------------------------------------------------------------------------

def _evaluate_baseline(
    agg: _Aggregator,
    root: Path,
    baseline_ref: str | None,
    *,
    current_active_elapsed: float | str,
    current_active_complete: bool,
    current_dispatches: int,
) -> dict[str, Any]:
    if baseline_ref is None:
        agg.add_data_gap({
            "kind": "missing_baseline",
            "locator": None,
            "reason_code": codec.ReasonCode.MISSING_REQUIRED_FIELD.value,
            "detail": "no_comparable_baseline_supplied",
        })
        return {
            "available": False,
            "comparable": False,
            "status": "unknown",
            "reason": "no_comparable_baseline_supplied",
            "baseline_ref": None,
            "factual_deltas": None,
            "is_gate": False,
        }

    bpath, brel = _safe_rel_path(root, baseline_ref, field="baseline_ref", allow_logs=True)
    if not brel.lower().endswith(".json"):
        raise _error(codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.PATH, "baseline_ref",
                     "repository-relative .json path", brel, brel)
    if not os.path.lexists(bpath):
        agg.add_diagnostic(_make_diag(
            codec.ReasonCode.FILE_NOT_FOUND, codec.Stage.PATH, brel,
            "existing historical baseline JSON file", "missing", brel,
            original_locator=_locator(brel, None),
        ))
        return {
            "available": False,
            "comparable": False,
            "status": "unknown",
            "reason": "baseline_file_not_found",
            "baseline_ref": brel,
            "factual_deltas": None,
            "is_gate": False,
        }

    bdata, bsha, _ = _read_strict_json(agg, bpath)
    if bdata is None:
        return {
            "available": False,
            "comparable": False,
            "status": "corrupt",
            "reason": "baseline_corrupt_json",
            "baseline_ref": brel,
            "factual_deltas": None,
            "is_gate": False,
        }

    bsv = bdata.get("schema_version")
    if type(bsv) is not str or bsv not in BASELINE_SCHEMA_VERSIONS:
        agg.add_diagnostic(_make_diag(
            codec.ReasonCode.UNKNOWN_SCHEMA, codec.Stage.SCHEMA, brel,
            sorted(BASELINE_SCHEMA_VERSIONS), bsv, brel,
            original_locator=_locator(brel, bsha),
            explicit_category="unknown_version",
        ))
        agg.add_data_gap({
            "kind": "unknown_schema_version",
            "locator": brel,
            "reason_code": codec.ReasonCode.UNKNOWN_SCHEMA.value,
            "detail": str(bsv),
        })
        return {
            "available": False,
            "comparable": False,
            "status": "unknown_schema",
            "reason": "baseline_unknown_schema_version",
            "baseline_ref": _locator(brel, bsha),
            "factual_deltas": None,
            "is_gate": False,
        }

    # Strict comparability: BOTH current and baseline MUST have matching non-empty scope/flow AND non-empty obligations!
    if agg.filter_scope_id:
        cur_scope: str | None = agg.filter_scope_id
    elif agg.filter_flow_id:
        cur_scope = agg.filter_flow_id
    elif len(agg.observed_scope_ids) == 1:
        cur_scope = sorted(agg.observed_scope_ids)[0]
    elif len(agg.observed_scope_ids) == 0 and len(agg.observed_flow_ids) == 1:
        cur_scope = sorted(agg.observed_flow_ids)[0]
    else:
        cur_scope = None
    base_denom = bdata.get("denominator") if isinstance(bdata.get("denominator"), dict) else {}
    base_scope = bdata.get("scope_id") or bdata.get("flow_id") or base_denom.get("scope_or_flow_id")
    if isinstance(base_scope, str):
        base_scope = base_scope.strip() or None
    else:
        base_scope = None

    cur_obligations = sorted(agg.observed_obligation_ids)
    base_obligations_raw = (
        bdata.get("obligation_ids") if isinstance(bdata.get("obligation_ids"), list)
        else base_denom.get("obligation_ids")
    )
    base_obligations = (
        sorted(str(x).strip() for x in base_obligations_raw if isinstance(x, str) and x.strip())
        if isinstance(base_obligations_raw, list)
        else []
    )

    mismatches: list[str] = []
    if cur_scope is None:
        mismatches.append("current_missing_single_scope_or_flow")
    if base_scope is None:
        mismatches.append("baseline_missing_scope_or_flow")
    if cur_scope is not None and base_scope is not None and str(base_scope) != str(cur_scope):
        mismatches.append(f"scope_mismatch:{base_scope}!={cur_scope}")
    if not cur_obligations:
        mismatches.append("current_missing_obligation_denominator")
    if not base_obligations:
        mismatches.append("baseline_missing_obligation_denominator")
    if cur_obligations and base_obligations and base_obligations != cur_obligations:
        mismatches.append(f"obligation_denominator_mismatch:{len(base_obligations)}!={len(cur_obligations)}")

    if mismatches:
        return {
            "available": True,
            "comparable": False,
            "status": "not_comparable",
            "reason": "baseline_denominator_mismatch",
            "mismatch_details": mismatches,
            "baseline_ref": _locator(brel, bsha),
            "factual_deltas": None,
            "is_gate": False,
        }

    base_timing = bdata.get("timing_and_cost_summary") if isinstance(bdata.get("timing_and_cost_summary"), dict) else bdata
    base_active = _finite_nonneg_float(base_timing.get("observed_active_elapsed_seconds"))
    base_complete = base_timing.get("overall_active_elapsed_complete") is True
    base_disp = _positive_or_zero_int(base_timing.get("observed_actual_dispatches"))

    # Only compute numeric elapsed delta when BOTH current and baseline have overall_active_elapsed_complete == True!
    active_delta: float | str = (
        round(current_active_elapsed - base_active, 4)
        if (current_active_complete and base_complete and isinstance(current_active_elapsed, float) and base_active is not None)
        else "unknown"
    )
    disp_delta: int | str = (
        current_dispatches - base_disp
        if base_disp is not None
        else "unknown"
    )
    return {
        "available": True,
        "comparable": True,
        "status": "comparable_historical_reference",
        "reason": "same_denominator_historical_reference",
        "baseline_ref": _locator(brel, bsha),
        "factual_deltas": {
            "observed_active_elapsed_seconds_delta": active_delta,
            "observed_actual_dispatches_delta": disp_delta,
            "baseline_observed_active_elapsed_seconds": base_active if base_active is not None else "unknown",
            "baseline_overall_active_elapsed_complete": base_complete,
            "baseline_observed_actual_dispatches": base_disp if base_disp is not None else "unknown",
        },
        "is_gate": False,
    }


# ---------------------------------------------------------------------------
# Public Entrypoints
# ---------------------------------------------------------------------------

def build_b_route_observability_report(
    root: Path | str,
    *,
    operation_id: str | None = None,
    run_id: str | None = None,
    scope_id: str | None = None,
    flow_id: str | None = None,
    stage: str | None = None,
    task_id: str | None = None,
    events_logs: list[str] | None = None,
    baseline_ref: str | None = None,
    verdict_or_scope_refs: list[str] | None = None,
) -> dict[str, Any]:
    """Build a read-only 5-axis process observability & unified diagnostics report."""
    root_path = _validate_root(root)
    f_op = _validate_filter("operation_id", operation_id)
    f_run = _validate_filter("run_id", run_id)
    f_scope = _validate_filter("scope_id", scope_id)
    f_flow = _validate_filter("flow_id", flow_id)
    f_stage = _validate_filter("stage", stage)
    f_task = _validate_filter("task_id", str(task_id) if type(task_id) is int else task_id)

    validated_events_logs: list[tuple[Path, str]] = []
    seen_ev_rels: set[str] = set()
    for raw_ev in events_logs or []:
        ev_path, ev_rel = _safe_rel_path(root_path, raw_ev, field="events_log", allow_logs=True)
        if not ev_rel.lower().endswith(".jsonl"):
            raise _error(codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.PATH, "events_log",
                         "repository-relative .jsonl path", ev_rel, ev_rel)
        if ev_rel not in seen_ev_rels:
            seen_ev_rels.add(ev_rel)
            validated_events_logs.append((ev_path, ev_rel))

    validated_verdict_refs: list[tuple[Path, str]] = []
    seen_vr_rels: set[str] = set()
    for raw_vr in verdict_or_scope_refs or []:
        vr_path, vr_rel = _safe_rel_path(root_path, raw_vr, field="verdict_ref", allow_logs=True)
        if not vr_rel.lower().endswith(".json"):
            raise _error(codec.ReasonCode.INVALID_ARGUMENT, codec.Stage.PATH, "verdict_ref",
                         "repository-relative .json path", vr_rel, vr_rel)
        if vr_rel not in seen_vr_rels:
            seen_vr_rels.add(vr_rel)
            validated_verdict_refs.append((vr_path, vr_rel))

    agg = _Aggregator(
        root_path,
        operation_id=f_op,
        run_id=f_run,
        scope_id=f_scope,
        flow_id=f_flow,
        stage=f_stage,
        task_id=f_task,
    )

    # Scan bounded repository log sources (NEVER rglob on mvg-planning / capability-planning).
    _scan_3a_sources(agg)
    _scan_3b_planning_runs(agg)
    _scan_governed_operations(agg)
    _scan_chapter6_and_runtime(agg)
    _scan_mvg_acceptance(agg)

    for ev_path, ev_rel in validated_events_logs:
        if not os.path.lexists(ev_path):
            agg.add_diagnostic(_make_diag(
                codec.ReasonCode.FILE_NOT_FOUND, codec.Stage.PATH, ev_rel,
                "existing .jsonl events log", "missing", ev_rel,
                original_locator=_locator(ev_rel, None),
            ))
            agg.add_data_gap({"kind": "missing_events_log", "locator": ev_rel, "reason_code": codec.ReasonCode.FILE_NOT_FOUND.value, "detail": "file not found"})
        else:
            _ingest_events_jsonl(agg, ev_path)

    for vr_path, vr_rel in validated_verdict_refs:
        _ingest_verdict_or_scope_ref(agg, vr_path, vr_rel)

    # Compute duplicate fresh test executions and attach per-event as well as top-level!
    duplicate_test_executions = agg.compute_duplicate_test_executions()
    if duplicate_test_executions:
        for ev in agg.events:
            ev_path_str = (ev.get("original_locator") or {}).get("path")
            if ev_path_str:
                ev["duplicate_test_executions"] = [
                    dup for dup in duplicate_test_executions if ev_path_str in dup["locators"]
                ]

    # Build 5-axis indexes
    by_op_or_run: dict[str, list[str]] = {}
    by_scope_or_flow: dict[str, list[str]] = {}
    by_stage: dict[str, list[str]] = {}
    by_attempt: dict[str, list[str]] = {}
    by_event_id: dict[str, dict[str, Any]] = {}

    for ev in agg.events:
        eid = ev["event_id"]
        op_key = str(ev["operation_or_run_id"] or "unscoped")
        sf_key = str(ev["scope_or_flow_id"] or "unscoped")
        st_key = str(ev["stage"] or "unknown")
        at_key = str(ev["attempt"])
        by_op_or_run.setdefault(op_key, []).append(eid)
        by_scope_or_flow.setdefault(sf_key, []).append(eid)
        by_stage.setdefault(st_key, []).append(eid)
        by_attempt.setdefault(at_key, []).append(eid)
        by_event_id[eid] = {
            "operation_or_run_id": ev["operation_or_run_id"],
            "scope_or_flow_id": ev["scope_or_flow_id"],
            "stage": ev["stage"],
            "attempt": ev["attempt"],
            "event_type": ev["event_type"],
            "status": ev["status"],
            "original_locator": ev["original_locator"],
        }

    # Timing & cost summary (AC-2)
    observed_active_total: float | str = (
        round(agg.active_elapsed_sum, 4) if agg.measured_event_count > 0 else "unknown"
    )
    overall_active_complete = (agg.measured_event_count > 0 and agg.unmeasured_event_count == 0)
    wall_clock_total: float | str = (
        round(sum(item["paused_or_wall_clock_seconds"] for item in agg.wall_clock_spans), 4)
        if agg.wall_clock_spans else "unknown"
    )
    reserved_budget_total: int | str = (
        sum(int(item["reserved_request_budget"]) for item in agg.reserved_budget_entries)
        if agg.reserved_budget_entries else "unknown"
    )

    timing_and_cost_summary = {
        "observed_active_elapsed_seconds": observed_active_total,
        "measured_event_count": agg.measured_event_count,
        "unmeasured_event_count": agg.unmeasured_event_count,
        "overall_active_elapsed_complete": overall_active_complete,
        "paused_or_wall_clock_seconds": wall_clock_total,
        "paused_wall_clock_is_active_elapsed": False,
        "wall_clock_spans": agg.wall_clock_spans,
        "reserved_request_budget": reserved_budget_total,
        "reserved_budget_breakdown": agg.reserved_budget_entries,
        "observed_actual_dispatches": agg.observed_actual_dispatches,
        "reserved_only_not_dispatched": agg.reserved_only_not_dispatched,
        "correlated_dispatches": agg.correlated_dispatches,
        "coordinator_reservation_plus_worker_plus_dispatch_deduplicated": True,
        "model_estimated_metrics": {
            "estimated_not_billed": True,
            "available": agg.has_model_estimates,
            "estimated_tokens_in": agg.estimated_tokens_in if agg.has_model_estimates else "unknown",
            "estimated_tokens_out": agg.estimated_tokens_out if agg.has_model_estimates else "unknown",
            "estimated_cost_usd": agg.estimated_cost_usd if agg.has_model_estimates else "unknown",
        },
        "billed_cost": agg.verified_billed_cost if agg.verified_billed_cost is not None else "unknown",
        "billed_cost_currency": agg.verified_billed_currency,
        "billed_cost_verified": agg.verified_billed_cost is not None,
    }

    baseline_comparison = _evaluate_baseline(
        agg, root_path, baseline_ref,
        current_active_elapsed=observed_active_total,
        current_active_complete=overall_active_complete,
        current_dispatches=agg.observed_actual_dispatches,
    )

    # Reuse breakdown (AC-4: strictly disjoint 3 classes)
    reuse_breakdown = {
        "cross_class_proof_allowed": False,
        "original_timestamps_preserved": agg.original_timestamps_preserved,
        "planning_adoption_reuse": agg.planning_adoption_reuse,
        "apply_idempotent_noop": agg.apply_idempotent_noop,
        "runtime_build_and_test_reuse": agg.runtime_build_and_test_reuse,
        "counts": {
            "planning_adoption_reuse": len(agg.planning_adoption_reuse),
            "apply_idempotent_noop": len(agg.apply_idempotent_noop),
            "runtime_build_and_test_reuse": len(agg.runtime_build_and_test_reuse),
        },
    }

    # Stop-loss, no-progress retries
    no_progress_retries = agg.compute_no_progress_retries()
    stop_loss_signals = {
        "rerun_guard": agg.stop_loss["rerun_guard"],
        "llm_retry_stop_loss": agg.stop_loss["llm_retry_stop_loss"],
        "sc_test_retry_stop_loss": agg.stop_loss["sc_test_retry_stop_loss"],
        "waste_signals": agg.stop_loss["waste_signals"],
        "deterministic_stop_loss": agg.stop_loss["deterministic_stop_loss"],
        "no_progress_retries": no_progress_retries,
        "active_count": (
            len(agg.stop_loss["rerun_guard"])
            + len(agg.stop_loss["llm_retry_stop_loss"])
            + len(agg.stop_loss["sc_test_retry_stop_loss"])
            + len(agg.stop_loss["waste_signals"])
            + len(agg.stop_loss["deterministic_stop_loss"])
            + len(no_progress_retries)
        ),
    }

    # Quality floor (AC-5: non-offsettable)
    reg_kinds = {r["kind"] for r in agg.quality_regressions}
    quality_floor = {
        "violated": bool(agg.quality_regressions),
        "process_metrics_can_offset": False,
        "regressions": agg.quality_regressions,
        "checks": {kind: (kind in reg_kinds) for kind in QUALITY_FLOOR_KINDS},
    }

    # Diagnostics grouping (AC-3)
    diagnostics_by_category: dict[str, list[dict[str, Any]]] = {cat: [] for cat in DIAGNOSTIC_CATEGORIES}
    for diag in agg.diagnostics:
        cat = diag["diagnostic_category"]
        diagnostics_by_category.setdefault(cat, []).append(diag)
    categories_present = sorted(cat for cat, items in diagnostics_by_category.items() if items)

    # Determine overall ok/status deterministically: corrupt/unsafe/unknown-version logs, hard conflicts, or quality-floor regressions fail closed!
    blocking_categories = {"corrupt_reference", "unknown_version"}
    blocking_diags = [d for d in agg.diagnostics if d["diagnostic_category"] in blocking_categories]
    ok = (not quality_floor["violated"]) and (not blocking_diags) and (not agg.has_hard_conflict)
    status = "ok" if ok else "blocked"

    if ok:
        top_reason_code = codec.ReasonCode.OK.value
    elif agg.quality_regressions:
        top_reason_code = agg.quality_regressions[0]["reason_code"]
    elif blocking_diags:
        top_reason_code = blocking_diags[0]["reason_code"]
    elif agg.has_hard_conflict:
        top_reason_code = codec.ReasonCode.CONFLICT.value
    elif agg.diagnostics:
        top_reason_code = agg.diagnostics[0]["reason_code"]
    else:
        top_reason_code = codec.ReasonCode.CONFLICT.value

    return {
        "schema_version": SCHEMA_VERSION,
        "ok": ok,
        "status": status,
        "reason_code": top_reason_code,
        "filters": {
            "operation_id": f_op,
            "run_id": f_run,
            "scope_id": f_scope,
            "flow_id": f_flow,
            "stage": f_stage,
            "task_id": f_task,
        },
        "denominator": {
            "scope_or_flow_id": (
                f_scope
                or f_flow
                or (sorted(agg.observed_scope_ids)[0] if len(agg.observed_scope_ids) == 1 else None)
                or (sorted(agg.observed_flow_ids)[0] if len(agg.observed_scope_ids) == 0 and len(agg.observed_flow_ids) == 1 else None)
            ),
            "scope_ids": sorted(agg.observed_scope_ids),
            "flow_ids": sorted(agg.observed_flow_ids),
            "obligation_ids": sorted(agg.observed_obligation_ids),
        },
        "events": agg.events,
        "event_count": len(agg.events),
        "deduplicated_duplicate_events_count": agg.deduplicated_duplicate_events_count,
        "retry_attempts_preserved": True,
        "axes": {
            "by_operation_or_run_id": by_op_or_run,
            "by_scope_or_flow_id": by_scope_or_flow,
            "by_stage": by_stage,
            "by_attempt": by_attempt,
            "by_event_id": by_event_id,
        },
        "timing_and_cost_summary": timing_and_cost_summary,
        "baseline_comparison": baseline_comparison,
        "governance_thresholds": dict(GOVERNANCE_THRESHOLDS),
        "build_prewarm_summary": dict(agg.build_prewarm_summary),
        "duplicate_test_executions": duplicate_test_executions,
        "reuse_breakdown": reuse_breakdown,
        "stop_loss_signals": stop_loss_signals,
        "rework_returns": agg.rework_returns,
        "data_gaps": agg.data_gaps,
        "quality_floor": quality_floor,
        "diagnostics": agg.diagnostics,
        "categories_present": categories_present,
        "diagnostics_by_category": diagnostics_by_category,
        "implicit_global_refresh_performed": False,
        "runtime_verified": False,
        "default_b_enabled": False,
        "invariants": dict(INVARIANTS),
    }


def write_observability_report(root: Path, report_rel: str, payload: dict[str, Any]) -> Path:
    """Write an optional observability report strictly under non-reserved logs/**/*.json."""
    target, _cleaned, root_path = validate_reserved_log_write_path(
        root, report_rel, suffix=".json", field="report",
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        _check_ancestors_no_reparse(root_path, target)
        tmp = target.with_name(target.name + ".tmp")
        inventory.no_reparse(tmp)
    except ValueError as exc:
        raise _error(codec.ReasonCode.UNSAFE_PATH, codec.Stage.PATH, "report",
                     "report parent and .tmp sibling without symlink or reparse point",
                     str(exc)[:200], report_rel) from exc
    data = json.dumps(payload, ensure_ascii=True, allow_nan=False, indent=2, sort_keys=False) + "\n"
    with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(data)
    os.replace(tmp, target)
    return target
