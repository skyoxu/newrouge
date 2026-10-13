# Capability Baseline

本表是 SPEC 的冻结输入清单，不是新的 Capability 产物。文件变更、顺序变更或 hash 变化必须创建新的规划基线。

- **Source:** `docs/planning/semantic-topology/capabilities.v1.json`
- **Source revision:** `source-set:68d145756705834e7b664fcc`
- **SHA-256:** `53B0EDBA89E636312447599147A3982D3A4644DAFD6DCBB3BF1E67FA8FE6B61E`
- **Count:** 11
- **Readiness binding:** 每个 ID 必须绑定同一 Chapter 5 readiness snapshot 的 path, version/hash, and `ready` verdict before generation.

| Order | Capability ID | Title |
|---:|---|---|
| 1 | `CAP-CORE-FOUNDATION` | Core Foundation and Contracts |
| 2 | `CAP-RUN-CONTINUITY` | Run Continuity and Resume |
| 3 | `CAP-COMBAT-EXECUTION` | Combat Runtime and Deck Lifecycle |
| 4 | `CAP-ENEMY-INTENT` | Enemy Intent and Resolution |
| 5 | `CAP-RUN-MAP-ROUTING` | Run Entry and Map Routing |
| 6 | `CAP-NODE-EXPERIENCES` | Node Experiences and Rewards |
| 7 | `CAP-COMBAT-INTERACTION` | Combat Interaction and Feedback |
| 8 | `CAP-RELIC-POWER-POTION` | Relics, Powers, and Potions |
| 9 | `CAP-RUN-SUMMARY` | Settlement and Run Summary |
| 10 | `CAP-DELIVERY-GOVERNANCE` | Quality, Security, and Delivery Governance |
| 11 | `CAP-LOCALIZATION-ACCESSIBILITY` | Localization and Accessibility |

The order is an input dependency order, not a product priority ranking. A readiness hash mismatch blocks generation rather than silently reusing the old baseline.
