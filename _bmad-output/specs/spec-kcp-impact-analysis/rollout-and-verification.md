# Rollout And Verification

## Delivery phases

1. **Symbol Index** - index C# class, interface, method, event, and contract symbols with repository revision and source hash.
2. **Dependency Scanner** - detect `using`, references, inheritance, interface implementation, and contract dependencies with stable ordering.
3. **Runtime Mapping** - parse bounded `.tscn` Node, signal, resource, and script bindings that are directly verifiable.
4. **Knowledge Binding** - locate candidate ADR/Task/Contract/Decision sources through the existing control plane, then re-read and hash-bind them.

Each phase requires focused tests and failure evidence before the next phase expands scope.

## Workflow placement

Coding: `Task -> Knowledge Freeze -> Impact Analysis -> Coding`.

Review: `Review Context Freeze + Impact Report -> Review`.

The initial rollout is shadow/observe-only. It must not add `--enforce` to Chapter 4/5/6 or Review defaults, expand a frozen context silently, or modify existing review sidecar schemas.

## Verification matrix

| Contract | Verification |
| --- | --- |
| Target resolution | Unique symbol/path fixtures plus ambiguity and missing-target tests. |
| Impact object model | JSON schema/shape tests and stable relation ordering. |
| Dependency evidence | Event, interface, inheritance, and service fixtures. |
| Test mapping | Production-to-unit and Task acceptance fixtures. |
| Runtime mapping | Scene/Node/signal fixture with explicit source path evidence. |
| Knowledge binding | ADR/Task/Contract/Decision source reread and hash checks. |
| Risk | Contract/Event/save/Core = high; Service/System = medium; UI-only = low; uncertain = unknown. |
| Failure safety | Missing index, stale revision, dirty state, unreadable source, malformed Scene, and unsupported dynamic behavior. |
| Determinism | Repeat same target and revision; compare canonical JSON. |
| Authority boundary | Confirm report cannot alter Locator, publication, current/LKG, semantic decisions, freeze, or review authority. |

## Acceptance mapping

- **AC-001:** Event/Contract target yields consumer, test, and ADR/Task evidence.
- **AC-002:** Contract/Event/save/Core target yields `high` risk with reasons.
- **AC-003:** Explicit Scene connection yields a `binds` Runtime edge; uncertain links are omitted or failed closed.
- **AC-004:** Review reads the report without authority or freeze mutation.
- **AC-005:** Same revision is deterministic; invalid inputs return diagnosed failure.
- **AC-006:** Reports and indexes remain derived evidence and direct source routing remains valid.

