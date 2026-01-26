---
PRD-ID: PRD-NEWROUGE-GAME-0001
Title: 08 章功能纵切索引（M1：Warrior）
Status: Draft
Updated: true
ADR-Refs:
  - ADR-0005-quality-gates
  - ADR-0010-internationalization
  - ADR-0011-windows-only-platform-and-ci
  - ADR-0019-godot-security-baseline
  - ADR-0020-contract-location-standardization
  - ADR-0025-godot-test-strategy
  - ADR-0033-card-identity-and-forms
Test-Refs:
  - Game.Core.Tests/Determinism/OfferLockingTests.cs # planned
  - Game.Core.Tests/Save/SaveResumeBoundaryTests.cs # planned
  - Game.Core.Tests/Cards/CardIdentityAndFormsTests.cs # planned
  - Tests.Godot/Smoke/ContinueGateTests.gd # planned
---

本目录为 `PRD-NEWROUGE-GAME-0001` 的 08 章功能纵切（Feature Slice），当前仅覆盖 **M1：Warrior 最小可玩纵切**。

原则：
- 08 章只写“功能纵切”：实体/事件/SLI/门禁/验收/测试对齐。
- 阈值/策略以 Base 与 ADR 为准；本目录只引用，不复制。

入口：
- 纵切说明：`08-Feature-Slice-M1-Warrior.md`
- 验收清单：`ACCEPTANCE_CHECKLIST.md`

