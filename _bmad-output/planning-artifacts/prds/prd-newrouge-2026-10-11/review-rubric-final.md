# PRD Quality Review — MVG Capability 增量规划与准入优化

## Review scope

This review applies the BMad PRD quality rubric to `prd.md` and `addendum.md` as they exist in this workspace. It specifically rechecks the prior high-priority concerns: reproducible Capability baseline, insufficient-candidate terminal behavior, Requirement identity/shared evidence, budget semantics, and inline assumption markers. The PRD and addendum were not modified by this review.

## Overall verdict

**Good, with one implementation-blocking clarification.** The prior high findings about the Capability baseline, insufficient-admitted-candidate behavior, and Requirement route/verification identity are substantially resolved: the PRD now binds the 11-Capability file by path, source revision, SHA-256, IDs, and order; defines a blocking terminal state without fallback; and specifies separate composite keys for route membership, authoritative verification, and evidence de-duplication. The remaining material gap is budget operability: the lineage limit is explicit, but the run-level total limit and its owner/configuration are still deferred, so an implementation could either under-protect or unpredictably expand model spend.

## Decision-readiness — adequate

The main workflow decisions are explicit: process one Capability at a time (§3.1), admit only structurally and semantically valid candidates before comparison (§3.1–§3.3), merge one selected increment atomically (§3.1–§3.2), block a Capability when fewer than three admitted candidates remain after bounded repair (§3.1/FR-002), and reopen earlier selections only for evidence-backed real hard conflicts (§3.4). The frozen baseline is now reproducible from `docs/planning/semantic-topology/capabilities.v1.json`, its `source_revision`, SHA-256, and the ordered 11-ID table (§3.1).

The unresolved run-level budget is the only decision that can materially change operational behavior. The PRD requires an explicit run cap, but leaves the numeric value and configuration owner to implementation (§7; addendum §2 and §5). Incumbent handling and cross-Capability reopening are intentionally constrained and are appropriately recorded as scoped open decisions rather than silently invented behavior.

### Findings

- **[high] Run-level budget has no executable value or owner** (§7; addendum “候选数、预算和 incumbent”) — `64` is clearly defined as a single candidate-lineage stop-loss, and silent multiplication by Capability count is forbidden, but the required run-level total cap has no numeric value, config key, accounting scope, or terminal code. Two implementations could therefore both claim conformance while allowing materially different total model calls. *Fix:* define the run-level budget contract before implementation: configuration key, whether it counts retries/preflight/model calls, aggregation across candidates and Capabilities, exhaustion terminal state, and audit fields.

## Substance over theater — strong

The PRD is focused on concrete workflow failure modes rather than template furniture. FR-006–FR-011 address complete evidence transport, deterministic gates, isolated repair lineages, candidate admission, atomic delta replay, and audit/recovery. The addendum adds implementation-level mapping and explicitly rejects prompt-only validation, truncated evidence, and string-concatenated manifests. No unused personas, generic innovation claims, or boilerplate scalability/security NFRs are present.

### Findings

No material findings.

## Strategic coherence — strong

The document has a coherent thesis: MVG represents player-executable operation routes, while Capability is the incremental planning boundary; each selected increment must preserve a cumulative, auditable baseline (§1, §3.1, §3.3). The metrics map to that thesis: clean admission, complete evidence, cumulative safety, multi-route Requirement expression, and recoverability (SM-1–SM-5). The Capability order is explicitly treated as authoritative input order and not product priority, which prevents an accidental product-roadmap claim (§3.1).

### Findings

No material findings.

## Done-ness clarity — adequate

Most FRs have deterministic acceptance consequences: schema/ID/selector checks, bidirectional flow-test bindings, producer/consumer handoffs, hash-bound receipts, atomic merge, and explicit terminal state `selection_blocked_insufficient_admitted_candidates`. Requirement identity rules are concrete enough to test: `(requirement_id, flow_id)`, `requirement_id`, and `(requirement_id, evidence_id)` (§3.2; addendum §3).

Two implementation details remain underspecified. First, the run-level budget must be made executable as noted above. Second, shared evidence has a de-duplication key, but the state transition/allowed values for `requirement_verification.disposition` and the exact representation of “shared scope” are not fixed, leaving some validator behavior to downstream design.

### Findings

- **[medium] Shared-evidence verification contract lacks state-transition and scope fields** (FR-004/FR-005; addendum “Requirement 数据模型建议”) — The keys and no-double-counting rule are clear, but the PRD does not fix the disposition enum/transitions or the machine-readable field that records which route behavior a shared evidence item covers. *Fix:* specify the allowed disposition states/transitions and a required route-scope representation, then add fixtures for one Requirement referenced by two flows with one shared evidence item and one route-specific evidence item.

## Scope honesty — strong

The non-goals are unusually clear for a brownfield workflow change: no GDD or task expansion, no second task/status/MVG lifecycle, no runtime acceptance claim, no silent Capability regrouping, no automatic budget increase, and no UI/API redesign without a separate decision (§4, §5.2). The addendum labels mechanism and migration details as implementation-stage proposals. The user-confirmed default—repair the current increment, explicitly reopen only for evidence-backed hard conflict—is consistently applied.

### Findings

No material findings.

## Downstream usability — adequate

The PRD is usable as a chain-top internal-tool specification: terminology is defined, FR-001–FR-012 and SM-1–SM-6 are continuous, owning scripts/workflows/tests are named (§7; addendum §6), and the baseline table now supplies all 11 Capability IDs and their processing order. The prior “unreproducible 11-Capability baseline” finding is resolved by the path, SHA-256, `source_revision`, ID list, and explicit drift rule (§3.1).

The remaining gap is not Capability identity but story-level verification detail: Chapter 5 readiness is not bound by an artifact/hash in the baseline table, and the shared-evidence disposition contract is still conceptual. These are manageable architecture inputs, but should be fixed before generating implementation stories that claim exact validator behavior.

### Findings

- **[medium] Readiness provenance is not bound to the Capability baseline** (§3.1; §7) — The Capability artifact itself is reproducible, but the PRD does not identify the Chapter 5 readiness/reconciliation artifact and hash that authorized this particular Capability version. A later readiness refresh could therefore be mistaken for the same planning input even when the Capability file hash is unchanged. *Fix:* record the readiness artifact path, version/hash, and the rule for invalidating/rebinding the planning baseline when readiness changes.

## Shape fit — strong

This is correctly shaped as a capability-first internal workflow PRD for maintainers and Knowledge/CLI operators. User journeys would add ceremony without improving the single-operator planning contract. Brownfield constraints, current implementation references, migration boundaries, and the distinction between planning admission and runtime acceptance are all appropriate to the product shape.

### Findings

No material findings.

## Mechanical notes

- **Capability baseline reproducibility:** resolved for the Capability artifact itself. The current file hash was independently checked as `53B0EDBA89E636312447599147A3982D3A4644DAFD6DCBB3BF1E67FA8FE6B61E`, matching §3.1; the file contains `source_revision: source-set:68d145756705834e7b664fcc` and the listed 11 IDs.
- **Insufficient candidates:** resolved. FR-002 defines `selection_blocked_insufficient_admitted_candidates`, forbids invalid-candidate/incumbent fallback, and requires immutable-input recovery with preserved failure reasons.
- **Requirement identity/shared evidence:** substantially resolved. Route membership, authoritative verification, and evidence de-duplication use separate keys; shared evidence does not increase completion counts. The remaining issue is the missing disposition/scope schema noted above.
- **Assumptions:** inline `[ASSUMPTION: ...]` markers now appear at the principal inferred facts in §0, §3.1, §3.3, and §3.4. The §9 index still contains several decision/constraint bullets without corresponding inline markers (for example the candidate-insufficiency and key-separation bullets), so the index is not a strict one-to-one roundtrip of assumptions.
- **Glossary:** stable overall; normalize lowercase `requirement/verification` to `Requirement/verification` in implementation-facing text if the terms become schema names.
- **IDs and cross-references:** FR-001–FR-012 and SM-1–SM-6 are continuous; cited addendum sections and owning paths resolve. No user journeys are present, which fits the single-operator internal-tool shape.

## Severity counts

- critical: 0
- high: 1
- medium: 3
- low: 0
