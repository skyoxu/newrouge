# Input Reconciliation - docs/code.txt

## Extracted and represented

- P1 standalone platform capability: KCP-IMPACT-001.
- Problem: Knowledge Control Plane explains why a change is made, but not what the changed code object affects.
- Goal: bounded Impact Context across code, tests, runtime, and knowledge.
- Non-goals: full CodeGraph, replacement of Knowledge Control Plane, autonomous refactoring.
- Target resolution: file, class, interface, method, event, contract, scene, resource.
- Evidence: direct references, dependency relationships, tests, Godot runtime links, knowledge refs.
- Risk levels: high, medium, low, with unknown for insufficient evidence.
- Workflow placement: after freeze and before coding; alongside review context before review.
- Artifact: versioned JSON under `logs/ci/impact-analysis/`.
- Authority rule: impact evidence does not confer authority.
- Four proposed phases and acceptance criteria.

## Deliberate adaptations

- Added `status`, `failure_reason`, repository revision, and auditability fields to make fail-closed behavior consumable.
- Added `unknown` risk for ambiguous or insufficiently evidenced targets; this prevents silent low-risk classification.
- Kept exact schema, relation enumerations, and sidecar integration in the addendum/deferred decisions because they require an implementation contract and may affect existing ADRs or workflow schemas.
- Used current main commit `4053008` as the explicit knowledge baseline, based on the user's request to account for recent knowledge-control-plane commits.

## Gaps to resolve downstream

- Decide whether a standalone report schema is a Phase 1 deliverable.
- Define the canonical Runtime relation fixture before Phase 3 acceptance.
- Update Review sidecar contracts only through a separate requirement/ADR if integration is approved.

