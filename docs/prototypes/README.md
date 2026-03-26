# Prototype Workspace

Purpose: hold lightweight, pre-task exploration records before work is promoted into the formal task pipeline.

Use this directory when the question is still whether a mechanic, UI flow, architecture option, or prompt workflow is worth turning into a formal task.

## Files
- `TEMPLATE.md`
  - Copy this when starting a new prototype.
- `<date>-<slug>.md`
  - One prototype record per exploration topic.

## Required Minimum Fields
Every prototype record should contain:
- hypothesis
- scope
- success criteria
- evidence
- decision

## Decision Values
- `discard`
  - The idea failed; remove or abandon it.
- `archive`
  - Keep notes/evidence, but do not promote it yet.
- `promote`
  - Convert the result into formal task work.

## Promotion Checklist
When a prototype is promoted, follow up outside this directory:
1. Create or update real `.taskmaster/tasks/*.json` entries.
2. Add overlay refs, test refs, and acceptance refs.
3. Add formal contracts if domain boundaries changed.
4. Run the correct `DELIVERY_PROFILE` path instead of treating the prototype as done.

## Non-Goals
- This directory is not a substitute for `execution-plans/`.
- This directory is not a substitute for `decision-logs/`.
- This directory is not where completed formal work should live.
