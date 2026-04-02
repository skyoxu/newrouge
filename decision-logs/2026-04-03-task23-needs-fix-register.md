# Task23-NeedsFix-Register

- Title: Task23-NeedsFix-Register
- Date: 2026-04-03
- Status: accepted
- Supersedes: none
- Superseded by: none
- Branch: task/T23
- Git Head: 31d43c8b58ffbeee62c837fe5975f79516dc8fff
- Why now: CI hard gate failed because newly added recovery docs missed required metadata, and Task 23 still carries one semantic soft-review needs-fix.
- Context: Task 23 deterministic gates are green but semantic-equivalence soft review remains open in fast mode.
- Decision: Keep fast-mode progression with explicit carry-over registration, enforce schema-compliant recovery docs, and defer strict semantic convergence to follow-up.
- Consequences: CI hard gate can pass on recovery-doc validation; unresolved semantic item remains visible and auditable.
- Recovery impact: `resume-task` and document recovery chain will include this deferred item with concrete commands.
- Validation: Pass `py -3 scripts/python/validate_recovery_docs.py --dir all` and keep Task 23 deterministic checks green.
- Related ADRs: `docs/adr/ADR-0010-translation-keys-and-i18n-conventions.md`
- Related execution plans: `execution-plans/2026-04-03-task23-needs-fix-followup.md`
- Related task id(s): `23`
- Related run id: `23913335951`
- Related latest.json: `logs/ci/2026-04-03/sc-review-pipeline-task-23/latest.json`
- Related pipeline artifacts: `logs/ci/2026-04-03/sc-llm-review-task-23/summary.json`, `logs/ci/2026-04-03/sc-acceptance-check-task-23/summary.json`

## Summary

- Deterministic gates are green for Task 23 in fast mode.
- LLM soft review still reports one unresolved item from `semantic-equivalence-auditor`.
- This item is a wording/scope convergence issue, not a deterministic blocker.

## Open Needs-Fix

1. Agent: `semantic-equivalence-auditor`  
   Severity: `P1` (semantic wording scope)  
   Finding: acceptance wording for Task 23 is still considered too narrow or too abstract in scope expression (scripts range / prefix wording), even after behavior tests pass.

## Impact Assessment

- Fast mode: non-blocking (soft review only).
- Strict semantic mode: potentially blocking until wording converges.

## Decision

- Keep current deterministic implementation and test evidence.
- Defer final wording convergence to a dedicated semantic cleanup pass.
- Record this as an explicit carry-over item before continuing task flow.

## Evidence

- `logs/ci/2026-04-03/sc-llm-review-task-23/summary.json`
- `logs/ci/2026-04-03/sc-llm-review-task-23/review-semantic-equivalence-auditor.md`
- `logs/ci/2026-04-02/sc-review-pipeline-task-23-fb6346d54f24466c967bacb34c009d15/summary.json`
- `logs/ci/2026-04-02/sc-acceptance-check-task-23/summary.json`
