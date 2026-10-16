# Workflow State Machine

## Current-to-target boundary

现有实现已有逐 Capability 选择和原子 checkpoint。本次增量引入完整候选生命周期子进程、仅完成项恢复、逐项页面展示和清理。旧 run 的 proof 保持不可变，不把目标能力描述成已部署。

## Target sequence

```text
prepare Capability N + accepted baseline
  -> canonical individual Capability hash lookup
  -> reuse committed compatible result OR start fresh candidate lifecycle
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
  -> publish partial planning projection
  -> discard process/model contexts
  -> Capability N+1
  -> final global consistency audit
```

## Candidate and recovery rules

- Candidate scope is the current Capability increment; candidates cannot cross-pollinate prompts, findings, workspaces, or unadmitted proposals.
- A candidate with any unresolved hard issue is excluded from selection. A valid candidate may lose only by comparative rank.
- After three failed repairs for one stable issue, create a new lineage from immutable prepared inputs and accepted predecessors only. Do not pass failed context, findings, prompts, or workspace.
- Runner, schema, transport, and preparation failures are execution failures, not semantic findings.
- A Capability with fewer than three admitted candidates ends as `selection_blocked_insufficient_admitted_candidates`; it does not advance or use an incumbent as a substitute.
- The stable run-level candidate slot/chain reaching 64 calls stops; replacement lineage, process and Capability changes do not reset it or grant another budget. A run reaching `mvg.run_invocation_limit` (default 192) ends as `run_blocked_budget_exhausted`; both outcomes preserve logs and recovery identity.
- New execution restores only completed Capability checkpoints. Unfinished admissions, repair or selection attempts are audit-only and never input to a new execution. Reservations stay charged; restarting a worker does not reset a run budget.
- Same individual Capability hash permits completed-result lookup, independent of Git/catalog hashes. Different hash always regenerates; similarity comparison is forbidden. Cumulative compatibility and integrity remain deterministic gates.

## Merge and conflict rules

- Merge is atomic and bound to the accepted baseline hash. Drift invalidates stale candidates.
- Existing routes, handoffs, tests, outcomes, and valid mappings remain unless an explicit authority-backed change exists.
- General overlap, shared Contracts, or repeated Requirement membership is not by itself a conflict.
- A global audit may create an explicit reopen plan only for a source-backed real hard conflict. The plan names affected Capability/flow, evidence, invalidated downstream increments, and replacement selection.

## Audit boundary

Planning completion requires all increment proofs, selection records, merge receipts, and the final machine audit. `runtime_verified` is a separate state produced only by formal MVG runtime acceptance.
