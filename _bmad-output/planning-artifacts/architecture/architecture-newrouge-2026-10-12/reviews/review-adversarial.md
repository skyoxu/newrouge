# MVG Architecture Spine Adversarial Review

## Review Basis

This review treats each AD as the architecture contract and asks whether two independent implementations can both satisfy its written rules yet make observably different lifecycle or audit decisions. The linked SPEC and companion documents were checked; where they already settle a detail, it is not repeated as a finding. The findings below concern remaining ambiguity in the spine's binding rules and their unresolved companion details.

## Findings

### [High] Lifecycle state ownership has no normative transition contract

- **Location:** `ARCHITECTURE-SPINE.md:31-41, 121-127`
- **Trigger:** A candidate reaches three failed repairs for the same stable issue, or a run resumes after a worker/runner interruption.
- **Two conforming implementations:** Unit A keeps a candidate in `repairing` until the coordinator emits a `lineage_retired` receipt, then automatically allocates a replacement lineage. Unit B has the coordinator move the candidate directly to `restart_required`; a later resume command allocates the replacement. Both keep all transitions in one coordinator, keep workers receipt-only, and preserve append-only evidence. The spine requires coordinator ownership and says it prevents incompatible transitions, but does not enumerate the candidate/run states or define the transition and resume rules. The linked state-machine companion specifies a clean restart after issue exhaustion, but does not define these lifecycle state identities or the receipt-to-state projection.
- **Consequence:** Resume, retry, and terminal-state behavior differs across implementations. An interrupted run can allocate a replacement automatically in one implementation and remain nonterminal awaiting an operator in another; tooling cannot reliably classify or recover the same ledger.
- **Fix:** Bind a versioned lifecycle contract listing run, candidate-slot, lineage, and Capability-checkpoint states; allowed transitions; the owning coordinator operation for each transition; and recovery behavior for every interruption point. Define whether replacement allocation is an immediate transition or an explicit resume action.

### [High] Checkpoint transaction identity is not derivable from a shared rule

- **Location:** `ARCHITECTURE-SPINE.md:61-65, 119-124`
- **Trigger:** Apply is interrupted after its durable transaction record is written, then a separate implementation or upgraded coordinator resumes using the same accepted baseline, proposal, and execution receipt.
- **Two conforming implementations:** Unit A defines transaction identity as a persisted random ID allocated before writes. Unit B derives it from `(run_id, capability_id, baseline_hash, proposal_hash, receipt_hash)`. Both bind the three hashes named by AD-5, write atomically, and are idempotent when asked to recover the same transaction ID. The spine requires a stable ID and content hash, but does not define the ID's fields, derivation, or how a recovering implementation finds the identity of an already-started transaction from its input envelope.
- **Consequence:** The same logical merge can be recognized as an existing transaction by one implementation and as an unknown/new transaction by the other. Cross-version recovery may block, create duplicate checkpoint records, or fail to prove that an already-applied increment is the same transaction. The companion specifies hash binding and replay safety but leaves transaction identity derivation unspecified.
- **Fix:** Define a versioned checkpoint transaction schema and deterministic identity tuple, including run, Capability/order position, accepted baseline hash, selected proposal hash, and receipt hash. Specify the durable write order and the recovery lookup rule; reject an identity whose stored payload differs from its tuple.

### [Medium] Requirement accounting does not define disposition-to-completion semantics

- **Location:** `ARCHITECTURE-SPINE.md:67-71, 124-127, 166-167`
- **Trigger:** A Requirement is present on multiple routes, or is classified as non-runtime, deferred, or a source gap, and a Knowledge/report projection computes whether it is complete.
- **Two conforming implementations:** Unit A emits one authoritative `requirement_id` record and marks it complete only when its authoritative disposition's required evidence is satisfied; shared route evidence is deduplicated. Unit B also emits one record keyed by `requirement_id`, but derives completion from any passing route-specific evidence and treats deferred/source-gap as nonblocking for the aggregate. Both keep route membership keyed by `(requirement_id, flow_id)`, verification keyed by Requirement, deduplicate `(requirement_id, evidence_id)`, and record covered behavior. AD-6 and `requirement-accounting.md` establish these identities and uniqueness, but do not specify the disposition vocabulary or the completion/blocking projection for each disposition.
- **Consequence:** The same proposal can appear complete in one Knowledge summary and incomplete or blocked in another, despite identical route, verification, and evidence rows. This can also make admission and final audit disagree without a structural validation failure.
- **Fix:** Add a normative disposition enum and a table mapping each disposition to required authority/evidence, route requirements, completion count, and blocking behavior. Require every consumer to derive its projection from that table and test shared-evidence and non-runtime cases against common fixtures.

### [High] Budget accounting at the runner boundary is not fully pinned in AD-7

- **Location:** `ARCHITECTURE-SPINE.md:73-77, 121-124`
- **Trigger:** A semantic or evidence-inspection runner starts and times out, returns malformed output, or fails during response transport; the run is then resumed.
- **Two conforming implementations:** Unit A charges the lineage and run budgets when a model invocation is durably issued, including timeout, malformed response, and transport failure after issue. Unit B charges only when a usable model response is persisted, treating failed invocations as runner retries. Both cap a lineage at 64 calls, bind a positive run limit across candidates and Capabilities, preserve recovery evidence, and classify the failure as execution rather than semantic rejection. The SPEC and Skill identify the call families included, but the spine does not define the charge point for an invocation whose response is not accepted or whether recovery may retry that same invocation without another charge.
- **Consequence:** Identical failures can exhaust the run budget in one implementation and leave budget available in another. Repeated resumes may therefore reach different terminal states and perform different amounts of model work under the same configured limit.
- **Fix:** Define the budget unit as a durable invocation attempt, state the exact event at which it is charged, and distinguish pre-invocation preparation failures from issued invocations with unusable responses. Persist the charge before dispatch and specify that recovery reuses a completed receipt or charges a newly issued attempt; never infer a free retry from an absent response.

### [High] Reopen plans lack a canonical downstream invalidation closure

- **Location:** `ARCHITECTURE-SPINE.md:85-89, 155-169`
- **Trigger:** Global audit finds a source-backed hard conflict in an early Capability whose selected flow is referenced by later accepted increments.
- **Two conforming implementations:** Unit A invalidates every later Capability checkpoint because each later increment was generated against the cumulative predecessor baseline. Unit B invalidates only increments whose flow/handoff dependency graph reaches the changed flow and retains the other later checkpoints. Both record source evidence, affected Capability/flow, invalidated downstream increments, and replacement selections; both preserve old selections as history and block completion until the conflict is resolved. The state-machine companion requires downstream invalidation, but neither it nor AD-9 defines whether “downstream” means all later checkpoints in the ordered cumulative chain or only semantic dependents.
- **Consequence:** Reopen can produce different accepted cumulative baselines, replacement candidate sets, and recovery effort for the same conflict. Retaining a checkpoint whose baseline was built from an invalidated predecessor risks applying a selection against an ancestry it no longer has; invalidating all later checkpoints can instead discard valid work when dependency semantics allow a narrower closure.
- **Fix:** Define the invalidation closure over explicit checkpoint ancestry and semantic dependencies. At minimum, every descendant of an invalidated checkpoint must be invalidated; any narrower retention rule must prove that its bound baseline and accepted-predecessor set remain valid. Persist the computed closure and replacement order in the reopen plan schema, and make validation recompute it.

## Paired Implementation Summary

The two hypothetical units agree on all explicit AD boundaries: one coordinator owns lifecycle changes, workers remain isolated and receipt-producing, deterministic gates precede admission, merges bind the named hashes, Requirement keys remain separate, budgets are finite, and reopen requires a source-backed global conflict. They initially disagreed on lifecycle transition timing, cross-version transaction recognition, Requirement completion projections, failed-invocation charging, and the reopen invalidation set. Those differences were addressed by the current spine's state table and AD-5 through AD-9.

## Final Recheck

**Verdict:** Pass after fixes

The final spine now binds the previously ambiguous cases:

- Run, slot, lineage, and checkpoint states and allowed transitions are enumerated, including clean restart and resume constraints.
- Checkpoint identity is deterministically derived from the canonical transaction tuple; recovery verifies the stored tuple and canonical payload.
- Requirement dispositions project to separate `accounted` and `satisfied` results, with explicit behavior for `flow`, `other_verification`, `deferred`, and `source_gap`.
- Budget is durably reserved before dispatch; dispatched failures are charged, preparation failures are not, and only an exact completed receipt is reusable.
- Reopen invalidates all later cumulative descendants unless deterministic rebase proves the exact base and predecessor set remain valid.

No remaining pair of conforming implementations was found that could diverge on these decisions without violating an explicit AD. Shared-evidence schema details remain intentionally deferred, while AD-6 binds the keys and counting invariants.
