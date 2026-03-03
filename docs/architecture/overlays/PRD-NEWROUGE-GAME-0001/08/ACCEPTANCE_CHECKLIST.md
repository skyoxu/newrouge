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
  - ADR-0031
  - ADR-0011
Test-Refs:
  - logs/ci/2026-02-12/docs-utf8-gate/summary.json
  - logs/ci/2026-02-12/sc-check-acceptance-garbled/summary.json
  - logs/ci/2026-02-14/sc-semantic-gate-all/summary.json
---

# 08章验收清单（M1: Warrior）

## 一、文档完整性验收
- [ ] Overlay 08 目录下索引、纵切、契约、测试、可观测性、验收清单 6 个文档齐全。
- [ ] Front matter 字段完整：`PRD-ID`、`Title`、`Status`、`ADR-Refs`、`Test-Refs`。
- [ ] 文档为 UTF-8（可读语义，不允许语义级乱码）。
- [ ] `_index.md` 与本清单中的文档列表一致。

## 二、架构设计验收
- [ ] M1 纵切范围明确：Warrior + Act1 最小闭环 + Continue Gate。
- [ ] 升级口径符合 ADR-0033：同 `card_id` 四形态，U1 二选一，Ultimate 不可逆。
- [ ] 存档口径符合 ADR-0032：单槽、节点前/战斗初始保存、战斗中不保存中间态。
- [ ] 状态推进遵循 Command-only 入口，不允许 UI 隐式推进决定性状态。

## 三、代码实现验收
- [ ] 契约落盘在 `Game.Core/Contracts/**`，Core 不依赖 Godot API。
- [ ] 奖励候选集锁定包含可审计标识（stable ids / order / provenance）。
- [ ] Continue 阻断路径可解释并可取证（坏档、迁移失败、校验失败）。
- [ ] 商店不提供升级入口，升级只允许在休整/特殊事件发生。

## 四、测试框架验收
- [ ] xUnit 覆盖：候选集锁定、存档边界、卡牌身份与形态。
- [ ] Headless/Godot 覆盖：Continue Gate 关键路径。
- [ ] 证据写入 `logs/unit`、`logs/e2e`、`logs/ci`。
- [ ] acceptance 与语义门禁对齐通过。

## 五、回链与门禁验收
- [ ] 任务 `T56` 覆盖：Audit JSONL validation + gate integration。
- [ ] 任务 `T57` 覆盖：Traceability gate for ADR/Chapter/Overlay links。
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

## 七、Task1 Evidence Path Template（Task1 环境证据路径模板，ACC:T1.3）
- `logs/ci/<YYYY-MM-DD>/env-evidence/godot-bin-env.txt`
- `logs/ci/<YYYY-MM-DD>/env-evidence/godot-version.txt`
- `logs/ci/<YYYY-MM-DD>/env-evidence/godot-bin-version.txt`
- `logs/ci/<YYYY-MM-DD>/env-evidence/dotnet-version.txt`
- `logs/ci/<YYYY-MM-DD>/env-evidence/dotnet-sdks.txt`
- `logs/ci/<YYYY-MM-DD>/env-evidence/dotnet-restore.txt`
- `logs/ci/<YYYY-MM-DD>/env-evidence/packages-lock-exists.txt`
- `logs/ci/<YYYY-MM-DD>/env-evidence/windows-only-check.txt`
- `logs/ci/<YYYY-MM-DD>/env-evidence/utf8-check.txt`

## Task53 Test-Refs (Headless Smoke Runner)
- logs/ci/<date>/task-0053.json
- logs/ci/<date>/smoke/<timestamp>/headless.out.log
- logs/ci/<date>/smoke/<timestamp>/headless.err.log
- logs/ci/<date>/smoke/<timestamp>/summary.json
- Game.Core.Tests/Tasks/Task53HeadlessRunnerCliValidationTests.cs
- Game.Core.Tests/Tasks/Task53HeadlessRunnerArtifactsSummaryTests.cs
- Game.Core.Tests/Tasks/Task53HeadlessRunnerPermissiveModeTests.cs

## Task54 Gate Notes
- Task: `T54 Integrate GdUnit4 suites into quality_gates.py`
- ADR-Refs: `ADR-0005`, `ADR-0011`, `ADR-0024`
- Chapter-Refs: `CH06`, `CH07`, `CH10`
- Test-Refs:
  - `Tests.Godot/tests/Integration/test_quality_gates_gdunit_suite_wiring.gd`
  - `Tests.Godot/tests/Integration/test_gdunit_junit_artifact_export.gd`
  - `Game.Core.Tests/Tasks/Task54GdUnitGatePolicyTests.cs`
  - `Game.Core.Tests/Tasks/Task54QualityGateSummaryTests.cs`
  - `Game.Core.Tests/Tasks/Task54GdUnitSuiteSelectionTests.cs`
  - `Game.Core.Tests/Tasks/Task54CiDecisionSyncTests.cs`
  - `Tests.Godot/tests/ci/test_gdunit_suite_wiring.gd`
  - `Game.Core.Tests/Tasks/Task32AcceptanceTests.cs`
- Checklist:
  - Summary JSON must include suite status, gate level, and overall decision.
  - GdUnit suites `adapters/security` are hard gate; `integration/ui` are soft gate.
  - `task-0054.json` must be generated and linked by task evidence refs.

## Task13 ADR 回链
- Task: `T13 Set up Godot autoloads and composition root`
- ADR-Refs: `ADR-0007`, `ADR-0021`, `ADR-0022`
- Test-Refs:
  - `Game.Core.Tests/Tasks/Task13AdrBacklinkTests.cs`
  - `Tests.Godot/tests/Tasks/test_task0013_composition_root_acceptance.gd`
  - `Tests.Godot/tests/Scenes/Smoke/test_main_scene_smoke.gd`
