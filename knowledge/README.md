# newrouge Repository Knowledge Control Plane

This directory contains **derived repository knowledge infrastructure**. It does not replace repository source authority.

## Authority

Repository facts remain owned by their source files, including `AGENTS.md`, Taskmaster, PRD/GDD, ADR/Base/Overlay, `Game.Core/Contracts/**`, workflow documents, execution plans, and decision logs.

The Knowledge Control Plane only answers: **where should a trusted consumer read?**

## Layers

1. `knowledge/snapshots/repository-source-snapshot.v1.json`
   - Trusted-ref source inventory and SHA-256 bindings.
2. `knowledge/catalogs/repository-knowledge-catalog.v1.json`
   - Typed modules, domains, status, visibility, anchors, relations and source hashes.
3. `knowledge/projections/consumer-projections.v1.json`
   - Precomputed eligible module ids per consumer policy.
4. `knowledge/policies/**`
   - Source exclusions and consumer retrieval boundaries.
5. `knowledge/contracts/**`
   - Stable request/result/consumption decision contracts.

Snapshot, catalog and projection files are generated artifacts and MUST NOT become a second SSoT.

## Initial domains

- `toolchain`
- `game-design`
- `game-runtime`
- `delivery`

Domain, visibility, lifecycle and enforcement level are independent dimensions.

## Build

From a clean repository with a local `refs/heads/main`:

```powershell
py -3 scripts/python/build_knowledge_catalog.py
py -3 scripts/python/build_knowledge_catalog.py --write
```

`--write` creates only derived files under `knowledge/snapshots`, `knowledge/catalogs` and `knowledge/projections`.

The trusted source default is `refs/heads/main`. `--authority-ref` exists for validation and controlled migration work; it must not be used to silently promote arbitrary dirty worktree state.

## Locate

The Locator reads JSON from stdin and emits one JSON result to stdout.

It is location-only: candidates contain source path, anchor/line, SHA-256, provenance and rank evidence. Consumers must re-read the source and own semantic acceptance/rejection.

Example request shape:

```json
{
  "schema_version": "newrouge.knowledge-locator-request.v1",
  "request_id": "example-1",
  "consumer": "chapter6",
  "query": "task contract refs overlay",
  "snapshot": {"ref": "refs/heads/main", "commit": "<40-char-commit>"},
  "policy_revision": "newrouge-knowledge-consumer-policies.v1"
}
```

Run:

```powershell
Get-Content request.json | py -3 scripts/python/knowledge_locator.py
```

The Locator fails closed with `status=blocked` when snapshot/policy/projection bindings or source hashes are stale.

## Exclusions

Global semantic knowledge excludes transient or recursively-derived state such as:

- `logs/**`
- `backup/**`
- `docs/migration/**`
- `.godot/**`
- build output
- generated knowledge snapshots/catalogs/projections/indexes

Run/recovery evidence remains available through its existing explicit workflow consumers; it is not promoted to global repository truth.

## Rollout

The initial migration is E1 retrieval-scoped only. Frozen task/session context may be added by consumer adapters, but it must not be described as tenant-safe/runtime E2 isolation.

PhaseA/Hosted Context Gate, HMAC manifests, nonce enforcement, account/project isolation and Ji Mu Yun runtime-specific machinery are intentionally out of scope.
