# ADR-0038: MVG Candidate Admission Before Selection

- Status: Accepted
- Date: 2026-10-09
- Context: A candidate with semantic hard findings could previously enter comparative selection and be rejected only during the later review stage.
- Decision:
  - Run deterministic completeness, cumulative-delta, and independent semantic admission before comparative selection.
  - Repair hard issues serially, with at most three repair attempts per stable issue identity. Exhaustion retires the lineage.
  - Generate replacements from immutable prepared inputs in a fresh lineage; retired proposals, findings, prompts, and segments are not inputs to replacement generation.
  - Do not invoke selection until three candidates are admitted. Selection rows are viable; non-winning candidates lose only by comparative rank.
  - An incumbent may participate only after the same admission checks. Final review verifies the selected candidate's hash-bound admission evidence and cannot replace the winner.
  - Runner, schema, identity, and input failures remain recoverable execution failures and are not converted into semantic findings.
  - Persist a three-round replacement stop-loss and a 64-invocation per-lineage stop-loss. Hitting the lineage cap with unresolved issues is an execution-budget failure, not proof that each issue exhausted its repair allowance.
  - Bind candidate reuse and selection recovery to proposal, proof, execution-receipt, lineage, and selection-input hashes. Runs without complete proof fail closed.
- Consequences: Candidate planning may take longer and can produce more durable evidence, but blocked candidates cannot contaminate selection and a selected result cannot be invalidated by a post-selection semantic fallback.
- References: `.agents/skills/plan-mvg/SKILL.md`, `docs/workflows/mvg-integration-acceptance.md`, `docs/planning/semantic-topology/`
