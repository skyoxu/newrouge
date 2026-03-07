---
PRD-ID: PRD-NEWROUGE-GAME-0001
Title: 08 可观测性与审计（M1）
Status: Draft
ADR-Refs:
  - ADR-0003-observability-release-health
  - ADR-0019-godot-security-baseline
  - ADR-0032-save-resume-determinism
  - ADR-0005-quality-gates
Arch-Refs:
  - CH02
  - CH03
  - CH07
Test-Refs:
  - Game.Core.Tests/Observability/StructuredLoggerTests.cs
  - Tests.Godot/tests/Adapters/Security/test_audit_log_jsonl.gd
  - Game.Core.Tests/Tasks/Task0056AcceptanceTests.cs
  - Game.Core.Tests/Tasks/Task0057AcceptanceTests.cs
---

# 08 可观测性与审计（M1）

## 1. 目标
M1 可观测性目标是让“确定性、可追溯、可回放”成为可验证事实，而不是口头承诺。

## 2. 审计日志硬要求
- 审计日志采用 JSONL，一行一个 JSON 对象。
- 关键字段至少包含：`ts`, `area`, `action`, `reason`, `target`, `caller`。
- 安全、存档、候选集锁定、Continue 阻断等关键路径必须记录。

## 3. 关键事件取证
- 候选集首次锁定：记录锁定来源、候选标识与顺序。
- Continue 阻断：记录阻断原因（坏档、迁移失败、校验失败）。
- 存档边界写入：记录节点前写入与战斗初始写入。
- autosave 失败路径：至少区分 `write_temp` 与 `replace_target` 两个动作，并能映射 `temp_write_failed`、`atomic_replace_failed` 等 reason code。
- 非法操作拒绝：记录路径越权、违规出网等安全拒绝事件；与存档相关时至少能回溯 `path_outside_user_scope`、`path_contains_traversal`、`extension_not_allowed`。
- 范围边界：Task12 先保证结构化 evidence 可被调用方与测试读取；统一 JSONL 持久化与 gate integration 由 T56 承接，避免把“审计链落盘”误判为 Task12 本体。

## 4. 门禁任务对齐
- T56: Audit JSONL validation + gate integration。
  - 验证 JSONL schema 与关键字段存在性。
  - 失败输出必须可定位到行号与原因。
- T57: Traceability gate for ADR/Chapter/Overlay links。
  - 验证 ADR/章节/Overlay 回链一致性。
  - 验证 Test-Refs 可追溯。

## 5. 日志产物路径
- CI：`logs/ci/<YYYY-MM-DD>/`
- 单测：`logs/unit/<YYYY-MM-DD>/`
- 引擎/冒烟：`logs/e2e/<YYYY-MM-DD>/`
- 性能：`logs/perf/<YYYY-MM-DD>/`

## 6. 失败优先级
- 若审计日志缺失关键字段，视为硬失败。
- 若 Continue 阻断路径无取证，视为硬失败。
- 若回链断裂（ADR/Overlay/Test-Refs 不一致），视为硬失败。

