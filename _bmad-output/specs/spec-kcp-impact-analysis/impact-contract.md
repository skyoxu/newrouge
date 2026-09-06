# Impact Contract

## Impact Object Model

The report models one target and typed edges. It is evidence, not an authority graph.

```json
{
  "target": {
    "kind": "event",
    "identity": "RewardOfferPresentedEvent",
    "canonical_path": "Game.Core/Contracts/Events/RewardOfferPresentedEvent.cs"
  },
  "impact_edges": [
    {
      "from": "RewardService",
      "to": "RewardOfferPresentedEvent",
      "relation": "consumes",
      "source_path": "Game.Core/Services/RewardService.cs"
    }
  ]
}
```

## Relation Types

| Relation | Meaning |
| --- | --- |
| `references` | A file or symbol references another source symbol. |
| `implements` | A type implements an interface or contract. |
| `inherits` | A type inherits from another type. |
| `consumes` | A system or symbol consumes an Event or exposed contract; the edge is consumer -> consumed event/contract. |
| `binds` | A Scene, Node, script, signal, or resource has a declared binding. |
| `tests` | A test file or symbol covers a production target or acceptance behavior. |
| `documents` | An ADR, Task, Contract, or Decision documents or constrains the target. |

Every edge should carry enough path, symbol, or stable-ID data for a reviewer to re-read the source directly.

## Report Envelope

`impact-report.v1.json` contains `schema_version`, `repository_revision`, `trusted_ref`, `index_id`, `index_sha256`, `analyzer_implementation_revision`, `analysis_config_revision`, `toolchain`, `status`, `target`, mandatory `knowledge_binding` for coding/review consumers, `affected_files`, `affected_symbols`, `impact_edges`, `tests`, `runtime_refs`, `knowledge_refs`, `risk_level`, `risk_policy_revision`, `matched_risk_rules`, `risk_reasons`, `generated_at`, and `failure_reason`.

The report is written by:

```powershell
py -3 scripts/python/analyze_impact.py --target <target>
```

Default output:

```text
logs/ci/<YYYY-MM-DD>/impact-analysis/<run-id>/impact-report.v1.json
```

The run directory also contains `run-manifest.v1.json`; consumers discover reports through this manifest rather than a fixed path or local date. Index artifacts use `logs/ci/<YYYY-MM-DD>/impact-analysis/indexes/<index_id>/impact-index.v1.json` plus `index-manifest.v1.json`.

Failure statuses must distinguish target ambiguity, unavailable index, stale/revision mismatch, source read failure, and unsupported target behavior. A failure is never represented as an empty successful impact set.

## V1 Unsupported Evidence

The analyzer does not infer runtime dynamic dispatch, reflection discovery, generated code relationships, editor-only Godot state, or external package dependency graphs. It does not add Neo4j, SQLite graph storage, Roslyn full compiler integration, a Godot editor plugin, or a visual graph UI.
