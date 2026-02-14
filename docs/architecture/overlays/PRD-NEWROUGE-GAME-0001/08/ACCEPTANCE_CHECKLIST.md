---
PRD-ID: PRD-NEWROUGE-GAME-0001
Title: 08章验收清单（M1: Warrior）
Status: Draft
ADR-Refs:
  - ADR-0005
  - ADR-0019
  - ADR-0025
  - ADR-0032
  - ADR-0033
Test-Refs:
  - logs/ci/2026-02-12/docs-utf8-gate/summary.json
  - logs/ci/2026-02-12/sc-check-acceptance-garbled/summary.json
  - logs/ci/2026-02-14/sc-semantic-gate-all/summary.json
---

# 08章验收清单（M1: Warrior）

## 一、文档完整性验收
- [ ] Overlay 08 下索引、纵切、契约、测试、可观测、验收清单 6 个文档齐全。
- [ ] Front matter 字段完整：`PRD-ID`、`Title`、`Status`、`ADR-Refs`、`Test-Refs`。
- [ ] 所有文档为 UTF-8、无 BOM、无语义乱码。
- [ ] `_index.md` 与本清单中的文档列表一致。

## 二、架构设计验收
- [ ] M1 纵切范围明确：Warrior + Act1 最小闭环 + Continue Gate。
- [ ] 升级口径符合 ADR-0033：同 `card_id` 四形态，U1 二选一，Ultimate 不可逆。
- [ ] 存档口径符合 ADR-0032：单槽、节点前/战斗初始保存、战斗中无中间态保存。
- [ ] 状态推进遵循 Command-only 入口，不允许 UI 隐式推进决定性状态。

## 三、代码实现验收
- [ ] 契约落盘在 `Game.Core/Contracts/**`，Core 不依赖 Godot API。
- [ ] 奖励候选集锁定包含可审计标识（stable ids / order / provenance）。
- [ ] Continue 阻断路径可解释并可取证（坏档、迁移失败、校验失败）。
- [ ] 商店无升级语境，Rest/事件具备升级入口。

## 四、测试框架验收
- [ ] xUnit 覆盖：候选集锁定、存档边界、卡牌身份与形态。
- [ ] Headless/Godot 覆盖：Continue Gate 关键路径。
- [ ] 日志证据写入 `logs/unit`、`logs/e2e`、`logs/ci`。
- [ ] 任务语义与 acceptance 对齐通过语义门禁。

## 五、回链与门禁验收
- [ ] 任务 `T56` 已覆盖：Audit JSONL validation + gate integration。
- [ ] 任务 `T57` 已覆盖：Traceability gate for ADR/Chapter/Overlay links。
- [ ] Overlay 文档可被 `overlay_refs` 稳定命中。
- [ ] ADR/CH/Overlay/Test-Refs 回链一致且可校验。

## 六、Test-Refs 分层

**Real（当前已有证据）**
- `logs/ci/2026-02-12/docs-utf8-gate/summary.json`
- `logs/ci/2026-02-12/sc-check-acceptance-garbled/summary.json`
- `logs/ci/2026-02-14/sc-semantic-gate-all/summary.json`

**Planned（后续实现落地）**
- `Game.Core.Tests/Determinism/OfferLockingTests.cs`
- `Game.Core.Tests/Save/SaveResumeBoundaryTests.cs`
- `Game.Core.Tests/Cards/CardIdentityAndFormsTests.cs`
- `Tests.Godot/Smoke/ContinueGateTests.gd`
- `Game.Core.Tests/Tasks/Task0056AcceptanceTests.cs`
- `Game.Core.Tests/Tasks/Task0057AcceptanceTests.cs`
