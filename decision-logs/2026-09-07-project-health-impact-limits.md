# Project Health Impact Limits

## Decision

The local investigation page must not create authoritative chapter handoffs. Preserve strict formal Impact behavior; provide separately typed exploratory results and list skipped unsupported C# method signatures.

## Needs Fix

Current main's full source set triggers `unsupported_target: unresolved generic parameter is unsupported` in the formal SymbolIndex member parser. This pre-existing parser limitation is not repaired by relaxing the formal contract. Follow-up: extend supported parameter resolution with qualified/generic fixtures, then run full-main formal analysis with a real frozen context.

The published KCP pointer at observed main 2d40006ad4a67fabf2a8a5ebe651ecfb321202a6 references older main 01395c691a3b48215a85333ead0c278bcf8d8d8e. Follow-up: use the existing governed publication workflow after reviewing source/policy changes; do not auto-publish on query.

## Evidence

- `logs/ci/project-health-knowledge/latest.json`
- `logs/ci/project-health-knowledge/queries/`
- Repair entry: `execution-plans/2026-09-07-project-health-knowledge.md`
