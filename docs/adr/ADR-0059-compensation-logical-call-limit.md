# ADR-0059: Compensation call limits without a new fiscal issuer

- Status: Accepted implementation scope; no new model/fiscal authorization
- Date: 2026-11-12
- Scope: Story2.8; supersedes ADR-0058's fixed funding issuer and live fiscal replay condition
- Authority: Existing Epic2 authorization and explicit user request to review unnecessary governance; clean Astra max independent necessity/proportionality assessment

## Evidence and decision

Original Story2.8 AC4 requires a new reviewed operation against current before-state, effects, scope and identity while retaining history/post-edits. The existing workflow retains actual budget/unknown constraints. Neither requires a compensation-specific issuer. ADR-0057 explicitly avoids imposing Capability/MVG fiscal issuers on compensation. The nonexistent `_b_route_compensation_budget_owner.py` gate first appeared in7c820200, not in exported original material. Its absence is a design dependency we introduced, not a missing migrated configuration. Read-only use never wrote a fiscal ledger, but unnecessarily depended on an installed live issuer implementing write methods. Remove that gate and its unused factory module/source pins.

Use the existing official runner and an explicit `--model-request-budget` on segmented execute. The parameter is solely a caller-set upper bound for logical App Server turns across this operation/plan's entire lifetime. It is not permission to incur new fees, a funding entitlement, a claim of old-owner identity or proof of campaign balance. The actual operator must already have applicable authorization and account for the relevant accumulated budget and unknowns before supplying it. Never default the parameter to the number of nodes or derive it from historical290/83/181. Current instructions do not grant a new numerical paid allowance.

The original CLI-derived plan fixes N nodes and no node is automatically retried. A positive exact integer ceiling must cover the full N. Before the first intent, persist the ceiling and exact operation/plan identity once; subsequent invocation cannot increase, replace or reset it. Every durable intent consumes its fixed node slot, including failed/unknown attempts. Reentry never grants a fresh allowance. Each runner invocation still gets its existing budget1. N is a maximum logical dispatch count; actual provider requests, billing and monetary cost remain unknown rather than inferred from that counter.

Without the explicit parameter, execute can verify an already completed prefix but returns authorization_required at the first undispatched node, before writing an admission/intent or invoking the runner. Read-only resume returns ready at an undispatched node. Any intent without a verified completed publication stays pending/unknown; execution/output/result files alone do not establish completion. No refund, ledger settlement, old STOP removal, replacement ID or automatic unknown replay is added.

Completed replay and proof/history consumption verify the sealed original call-limit reference, request/schema/measurement, independent runtime/output/result and completed reference without a live fiscal owner. Proof explicitly states the logical-only budget claim. It neither settles old financial unknowns nor grants subsequent dispatch. Full current-source rederivation, same work account, exact original semantics and actual-parent per-segment capacity remain unchanged.

## Actual budget boundary

Restored Host1/2/3 allocations each have dispatch_cap1. Host1/2 retain STOP and no verified outcome; Host3's original intent has owner_verified_completed. They cannot fund the new compensation's two nodes. Canonical Unit Root-02 config/ledger were genuinely absent at the source. Historical83 paid-or-unknown and181 overlapping guard under cap290 are not a fresh available balance and are not added together. The one-comparison recovery-funding module and Capability/MVG DATA prefix helper are not general dispatch grants.

Actual paid execution remains unperformed. A necessary operator decision, if not recoverable from existing authorization, is which applicable budget covers the two new logical review calls and its authorized accumulated limit/current occupancy. No amount or model price is guessed, no credentials are requested, and no new pool or blanket finance platform is introduced.
