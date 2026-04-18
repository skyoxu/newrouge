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
  - Game.Core.Tests/Tasks/Task0009AcceptanceTests.cs
  - Game.Core.Tests/Services/RngStreamRegistryDeterminismTests.cs
  - Game.Core.Tests/Services/RngStreamRegistryStateRestoreTests.cs
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
- [ ] autosave 写失败路径可解释并可取证，至少覆盖 `temp_write_failed` 与 `atomic_replace_failed`，且失败后保留上一份有效 autosave。
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


## Task28 Contract/Test Backlinks
- Task: `T28 Create ActConfig data model and loader`
- ADR-Refs: `ADR-0006`, `ADR-0031`, `ADR-0021`
- Contract-Refs:
  - `Game.Core/Contracts/Config/ActConfig.cs`
  - `Game.Core/Contracts/Config/ActConfigLoadResult.cs`
  - `Game.Core/Contracts/Interfaces/IActConfigProvider.cs`
  - `Game.Core/Contracts/Events/ActConfigLoadedEvent.cs` (`core.act.config.loaded`)
- Test-Refs:
  - `Game.Core.Tests/Tasks/Task0028AcceptanceTests.cs`
  - `Game.Core.Tests/Services/ActConfigLoaderTests.cs`
  - `Game.Core.Tests/Services/ActConfigLoaderSchemaVersionTests.cs`
- Evidence:
  - `logs/ci/<date>/task-0028.json`
- Checklist:
  - `ActConfig` includes `schema_version/act_id/node_graph/pools/encounters`
  - schema validation failure is deterministic and assertable
  - overlay contracts/testing documents both contain the same Task28 refs

## Task5 ADR Mapping
- ADR-0021
- ADR-0029

## Task30 ADR Mapping
- ADR-0010
- ADR-0020
- ADR-0021

## Task30 Serialization Semantics
- RelicDefinition serialized keys must be exactly: `relic_id`, `name_key`, `description_key`, `tags`.
- RelicInstance serialized keys must be exactly: `instance_id`, `modifiers`.
- Missing required keys or renamed keys must fail acceptance (`ACC:T30.1`).
- Refs: `Game.Core.Tests/Tasks/Task0030AcceptanceTests.cs`

## Task9 Governance Evidence (Non-semantic)
- This block is governance traceability evidence only and is not a Task 9 RNG behavior acceptance condition.
- ADR-0032 back-link check: pass. Evidence: logs/ci/evidence/task-0009-adr-0032-backlink.json
- ADR-0021 back-link check: pass. Evidence: logs/ci/evidence/task-0009-adr-0021-backlink.json

## Task39 Translation Traceability
- Task: `T39 Populate translations for M1 cards, relics, events`
- ADR-Refs: `ADR-0010`
- Test-Refs:
  - `Tests.Godot/tests/Tasks/test_task0039_acceptance.gd`
  - `Game.Core.Tests/Tasks/Task0039AcceptanceTests.cs`
- Evidence script:
  - `scripts/python/verify_m1_translations.py`



- Task39 Acceptance:
- `ACC:T39.1`: Extract complete M1 visible-text baseline from real sources (cards/relics/events/runtime-visible M1 UI text, not prompts-only); every extracted key must exist in `en.csv` and `zh-CN.csv` with valid values (non-empty, non-key-echo, non-placeholder-garbled).
- `ACC:T39.2`: In Task39-scoped cards/relics/events data and all runtime-visible M1 UI text (prompts/menu labels/button texts/event option texts/other player-facing labels), visible text must render via translation keys; hardcoded visible human-readable literals fail acceptance.
- `ACC:T39.3`: M1 locale output correctness is acceptance-critical: for `en` and `zh-CN`, runtime-visible M1 UI text must resolve to non-empty, non-key-echo, non-placeholder values from translation resources; locale-switch refresh timing/mechanism is out of scope for Task39.
- `ACC:T39.4`: M1 visible-text coverage must be reproducible from source extraction: `required_keys` derived from cards/relics/events/runtime-visible UI sources, and `missing_keys` must be empty for both `en` and `zh-CN`.

## Task20 Test-Refs (Shop Lock / No Upgrade Context)
- Task: `T20 Implement shop scene with inventory locking and no upgrade context`
- Test-Refs:
  - `Tests.Godot/tests/Tasks/test_task0020_acceptance.gd`
  - `Game.Core.Tests/Tasks/Task0020AcceptanceTests.cs`
- Coverage-Tags:
  - `shop_purchase`
  - `shop_inventory_lock`
  - `shop_no_upgrade_copy`
  - `reenter_persistence`
- Checklist:
  - Must load `Game.Godot/Scenes/Shop.tscn` and keep locked inventory stable across re-enter.
  - Must reject duplicate purchase and invalid offer id purchase.
  - Must keep shop UI/service texts free of upgrade context.


## Task26 Difficulty Contract And Immutability Evidence
- Task 26 / T26 traceability scope: difficulty configuration contract and run-start immutability.
- ADR-Refs: `ADR-0023`, `ADR-0032`, `ADR-0021`
- Test-Refs:
  - `Tests.Godot/tests/Tasks/test_task0026_acceptance.gd`
  - `Game.Core.Tests/Tasks/Task0026AcceptanceTests.cs`
- Checklist:
  - run metadata persists `difficulty_id`, `label_key`, `description_key`, `ruleset_id` from selected difficulty snapshot
  - post-start mutation requests are rejected or leave stored values unchanged
