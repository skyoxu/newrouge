---
id: SPEC-kcp-impact-analysis
companions:
  - impact-contract.md
  - rollout-and-verification.md
  - ../../prds/prd-newrouge-2026-09-04/prd.md
  - ../../prds/prd-newrouge-2026-09-04/addendum.md
  - ../../../AGENTS.md
  - ../../../project-context.md
sources:
  - ../../../docs/code.txt
---

> **Canonical contract.** This SPEC and its companions define the bounded contract for Knowledge Control Plane Impact Analysis in `newrouge`.

# Knowledge Control Plane Impact Analysis

## Why

The migrated Knowledge Control Plane explains why a change is made and which authority constrains it, but AI still lacks reliable evidence of what a code, contract, or Scene change affects. A repository-local Impact Analysis Layer is needed before coding and review to expose affected code, tests, Runtime references, knowledge references, and risk without turning dependency evidence into authority.

## Capabilities

- **CAP-1**
  - **intent:** Resolve a file, class, interface, method, event, contract, scene, or resource target to a canonical repository location.
  - **success:** A unique target resolves deterministically; ambiguous, missing, or unreadable targets return an explicit diagnostic failure.

- **CAP-2**
  - **intent:** Represent a target and its affected surface as typed impact edges across files, symbols, tests, Runtime references, and knowledge references.
  - **success:** A versioned report contains stable target fields, edge relation types, source paths, and repository revision binding.

- **CAP-3**
  - **intent:** Detect statically verifiable code dependencies, test coverage, and bounded Godot Scene/Node/signal/resource relationships.
  - **success:** Repeated analysis on the same revision produces equivalent evidence; unverified dynamic relationships are not reported as facts.

- **CAP-4**
  - **intent:** Bind impact evidence to existing ADR, Task, Contract, and Decision sources while preserving Knowledge Control Plane authority.
  - **success:** Each knowledge reference is path/ID and source-hash traceable, and cannot alter semantic acceptance, freeze, publication, Locator, or review authority.

- **CAP-5**
  - **intent:** Classify change risk and emit a machine-readable impact report for coding and review consumers.
  - **success:** `scripts/python/analyze_impact.py` produces `logs/ci/<YYYY-MM-DD>/impact-analysis/<run-id>/impact-report.v1.json` with `high`, `medium`, `low`, or `unknown` risk, reasons, status, failure details, and revision/index/KCP lineage bindings.

- **CAP-6**
  - **intent:** Insert impact evidence after knowledge freeze and before coding, and alongside review context before review, using an observe-only rollout.
  - **success:** The workflow consumes the report without mutating business source or changing publication, current/LKG, Locator, freeze, semantic decisions, or review authority.

## Constraints

- Scope is repository-local `newrouge` on Windows with Godot 4.5.1, C#/.NET 8, and repository-relative paths.
- Impact is evidence, not authority. ADR, Task, Contract, Decision, and Freeze remain authoritative.
- Analysis is read-only and fail-closed on ambiguity, missing/stale index, source read failure, dirty state, or revision mismatch.
- V1 relation types are fixed to `references`, `implements`, `inherits`, `consumes`, `binds`, `tests`, and `documents`.
- The canonical entrypoint is `scripts/python/analyze_impact.py`; default output is under `logs/ci/impact-analysis/`.
- Existing Knowledge Control Plane publication and freeze contracts must remain unchanged during the initial rollout.
- Detailed object fields, relation semantics, and unsupported cases are defined in `impact-contract.md`.

## Non-goals

- Full CodeGraph, AST database, class graph, method graph, or call graph.
- Autonomous refactoring or automatic edits to source, Scene, documents, or authority artifacts.
- Neo4j, SQLite graph database, Roslyn full compiler integration, Godot editor plugin, or visual dependency graph UI in v1.
- Runtime dynamic dispatch, reflection discovery, generated-code inference, editor-only Godot state, or external package dependency graphs in v1.
- Replacing Knowledge Control Plane authority, semantic decisions, publication, Locator, or freeze.
- Cross-repository analysis or SaaS workspace/tenant governance.

## Success signal

Before changing a target such as `RewardOfferPresentedEvent`, an AI consumer can read one revision-bound report and answer which code, tests, Runtime references, ADR/Task constraints, and risk require review. The report is deterministic and auditable, while all authority and freeze decisions remain in the existing control plane.

## Assumptions

- The first consumers are repository-local AI coding and review workflows; no external service or cross-repository graph is required.

## Open Questions

- Is `impact-report.v1.schema.json` a Phase 1 deliverable or initially script-validated only?
- Which canonical Runtime relation fixture is required for Phase 3 acceptance?
- Should Review sidecar integration be a separate contract and requirement after shadow validation?
