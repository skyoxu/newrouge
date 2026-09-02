# Maintain Knowledge Base

Use this skill only to inspect, validate, rebuild, or publish **derived repository knowledge artifacts**.

## Non-negotiable boundaries

- Repository source remains authority.
- Do not edit product/runtime/source documents merely to make the knowledge catalog pass.
- Do not fetch, merge, checkout, reset, or otherwise move repository source authority as an implicit maintenance side effect.
- Default trusted ref is `refs/heads/main`.
- Do not promote dirty worktree content as repository facts.
- Do not treat `logs/**` as global knowledge truth.
- Do not create ad-hoc replacement indexes when the registered catalog is stale.
- Consumer workflows must not rebuild global knowledge as an implicit recovery side effect.

## Normal check

```powershell
py -3 scripts/python/build_knowledge_catalog.py
```

This reads committed source from the trusted ref and reports source/module counts without writing derived artifacts.

## Explicit refresh

After maintainer review:

```powershell
py -3 scripts/python/build_knowledge_catalog.py --write
```

Allowed writes are limited to:

- `knowledge/snapshots/**`
- `knowledge/catalogs/**`
- `knowledge/projections/**`

## Locator smoke check

Build/write a current catalog, then submit a request bound to the emitted trusted commit:

```powershell
Get-Content request.json | py -3 scripts/python/knowledge_locator.py
```

A stale snapshot, policy mismatch, projection mismatch, missing source, or source hash drift must return `status=blocked`.

## Consumer rule

Locator candidates are not semantic truth. A trusted consumer must re-read the source, verify the source hash, and record an `accepted` or `rejected` decision using `knowledge-consumption-decision.v1` semantics before claiming a required context class is satisfied.

## Rollback

The initial migration has no runtime dependency. If the knowledge system is unavailable, use the repository's existing direct authority routing from `AGENTS.md`, `docs/PROJECT_DOCUMENTATION_INDEX.md`, and `docs/agents/13-rag-sources-and-session-ssot.md`.
