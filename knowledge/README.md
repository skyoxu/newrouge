# newrouge Repository Knowledge Control Plane

This directory contains **derived repository knowledge infrastructure**. It does not replace repository source authority.

## Authority

Repository facts remain owned by their source files, including `AGENTS.md`, `workflow.md`, Taskmaster, PRD/GDD, ADR/Base/Overlay, `Game.Core/Contracts/**`, workflow documents, execution plans, and decision logs.

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
6. `knowledge/evaluation/queries.v1.json`
   - Repository-real deterministic query suite.

Snapshot, catalog and projection files are generated artifacts and MUST NOT become a second SSoT.

## Initial domains

- `toolchain`
- `game-design`
- `game-runtime`
- `delivery`

Domain, visibility, lifecycle and enforcement level are independent dimensions.

## Source Coverage

The initial catalog intentionally focuses on authority-bearing knowledge, including:

- `AGENTS.md`, `README.md`, `workflow.md`, `DELIVERY_PROFILE.md`
- `docs/agents/**`
- PRD/GDD/game-design docs
- ADR index, ADRs, Base and Overlay architecture
- `Game.Core/Contracts/**`
- Taskmaster task state
- execution plans and decision logs
- stable workflow/testing documentation

It is not a replacement for code search across `Game.Core/**`, `Game.Godot/**`, `Scenes/**`, or assets.

## Build

From a clean repository with a local `refs/heads/main`:

```powershell
py -3 scripts/python/build_knowledge_catalog.py
py -3 scripts/python/build_knowledge_catalog.py --write
py -3 scripts/python/build_knowledge_catalog.py --check
```

`--write` creates only derived files under `knowledge/snapshots`, `knowledge/catalogs` and `knowledge/projections`.

`--check` rebuilds the expected layers in memory and fails if the persisted generated layers are missing, invalid, or stale.

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

## Evaluation

Run repository-real queries only after generated layers exist and pass `--check`:

```powershell
py -3 scripts/python/evaluate_knowledge_queries.py
```

The evaluation suite covers repository rules, workflow authority, ADR navigation, contract authority, delivery/task context and review routing while asserting that transient log/migration/backup paths do not satisfy global knowledge queries.

## Terminal Validation

Kernel/static validation:

```powershell
py -3 scripts/python/validate_knowledge_control_plane.py
```

Full generated-state validation:

```powershell
py -3 scripts/python/validate_knowledge_control_plane.py --require-generated
```

The full form requires:

- generated layers matching current trusted `refs/heads/main`;
- deterministic unit tests;
- repository-real query evaluation.

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

The initial migration is E1 retrieval-scoped only.

Current rollout order:

```text
direct-source baseline
  -> deterministic kernel
  -> repository query evaluation
  -> human routing integration
  -> Chapter/review shadow consumers
  -> bounded freeze contract
  -> publication/current/LKG hardening
```

Frozen task/session context may be added by consumer adapters, but it must not be described as tenant-safe/runtime E2 isolation.

PhaseA/Hosted Context Gate, HMAC manifests, nonce enforcement, account/project isolation and Ji Mu Yun runtime-specific machinery are intentionally out of scope.
