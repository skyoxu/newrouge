# Project Health Impact Limits

- Title: Project Health Impact Limits and Recovery Metadata Repair
- Date: 2026-09-07
- Status: accepted
- Supersedes: n/a - initial scoped decision
- Superseded by: n/a - active decision
- Branch: feat/project-health-knowledge-impact
- Git Head: 814a1e010579c24a543d26115f3cb2d337bcd355
- Why now: PR 166 CI exposed missing recovery metadata while formal Impact limitations remain open.
- Context: Focused feature tests did not include the repository recovery documentation gate.
- Decision: Follow both recovery templates, preserve existing validator requirements and keep exploration separate from formal handoff.
- Consequences: Both recovery documents gain explicit provenance and continuation fields; no runtime or authority policy is relaxed.
- Recovery impact: Validate execution plans and decision logs before publishing further changes.
- Validation: Run py -3 scripts/python/validate_recovery_docs.py --dir all; remote CI remains the Windows verification authority.
- Related ADRs: docs/adr/ADR-0036-project-health-investigation.md
- Related execution plans: execution-plans/2026-09-07-project-health-knowledge.md
- Related task id(s): n/a - repository tooling, not a gameplay Taskmaster task
- Related run id: 34104776509
- Related latest.json: logs/ci/project-health-knowledge/latest.json
- Related pipeline artifacts: logs/ci/2026-09-07/gate-bundle/runs/gh-34104776509-a1/hard/summary.json

## Decision

The local investigation page must not create authoritative chapter handoffs. Preserve strict formal Impact behavior; provide separately typed exploratory results and list skipped unsupported C# method signatures.

## Needs Fix

Current main's full source set triggers `unsupported_target: unresolved generic parameter is unsupported` in the formal SymbolIndex member parser. This pre-existing parser limitation is not repaired by relaxing the formal contract. Follow-up: extend supported parameter resolution with qualified/generic fixtures, then run full-main formal analysis with a real frozen context.

The published KCP pointer at observed main 2d40006ad4a67fabf2a8a5ebe651ecfb321202a6 references older main 01395c691a3b48215a85333ead0c278bcf8d8d8e. Follow-up: use the existing governed publication workflow after reviewing source/policy changes; do not auto-publish on query.

## Evidence

- `logs/ci/project-health-knowledge/latest.json`
- `logs/ci/project-health-knowledge/queries/`
- Repair entry: `execution-plans/2026-09-07-project-health-knowledge.md`
