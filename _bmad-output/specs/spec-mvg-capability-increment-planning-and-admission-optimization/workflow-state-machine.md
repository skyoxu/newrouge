# Workflow State Machine

## Current-to-target boundary

当前仓库实现是每个 candidate 顺序 append 全部 Capability，全部完成后才统一选择。本 SPEC 的目标是把选择 checkpoint 下沉到每个 Capability；迁移期间不得把目标状态描述成现状。

## Target sequence

```text
prepare Capability N + accepted baseline
  -> create three isolated candidate lineages
  -> preflight complete inputs and domains
  -> generate increment
  -> deterministic machine gate
  -> repair stable hard issues (max 3 each)
  -> clean lineage restart after issue exhaustion
  -> independent semantic admission
  -> require 3 admitted candidates
  -> comparative selection of the whole increment
  -> hash-bound atomic merge and checkpoint
  -> Capability N+1
  -> final global consistency audit
```

## Candidate and recovery rules

- Candidate scope is the current Capability increment; candidates cannot cross-pollinate prompts, findings, workspaces, or unadmitted proposals.
- A candidate with any unresolved hard issue is excluded from selection. A valid candidate may lose only by comparative rank.
- After three failed repairs for one stable issue, create a new lineage from immutable prepared inputs and accepted predecessors only. Do not pass failed context, findings, prompts, or workspace.
- Runner, schema, transport, and preparation failures are execution failures, not semantic findings.
- A Capability with fewer than three admitted candidates ends as `selection_blocked_insufficient_admitted_candidates`; it does not advance or use an incumbent as a substitute.
- A lineage reaching 64 calls is retired. A run reaching `mvg.run_invocation_limit` (default 192) ends as `run_blocked_budget_exhausted`; both outcomes preserve logs and recovery identity.

## Merge and conflict rules

- Merge is atomic and bound to the accepted baseline hash. Drift invalidates stale candidates.
- Existing routes, handoffs, tests, outcomes, and valid mappings remain unless an explicit authority-backed change exists.
- General overlap, shared Contracts, or repeated Requirement membership is not by itself a conflict.
- A global audit may create an explicit reopen plan only for a source-backed real hard conflict. The plan names affected Capability/flow, evidence, invalidated downstream increments, and replacement selection.

## Audit boundary

Planning completion requires all increment proofs, selection records, merge receipts, and the final machine audit. `runtime_verified` is a separate state produced only by formal MVG runtime acceptance.
