---
doc: adr-0032-gap-checklist
source_adr: docs/adr/ADR-0032-save-resume-determinism.md
status: draft
created: 2026-01-24
encoding: UTF-8
purpose: "将 ADR-0032 从 Proposed 推进到 Accepted 的缺口清单（用于 Taskmaster 拆解任务）"
---

# ADR-0032（存档/退出重进/确定性）M1 Gate-0 实现缺口清单

你现在的最大风险不是“写得不够”，而是 **实现与取证没有被任务化并固化到门禁里**：这会让“退出重进不刷结果”的口径在后续改动中悄悄漂移。  
这份清单的目标：把 ADR-0032 的“Implementation Acceptance Criteria（M1 Gate-0）”拆成可执行、可验收、可取证的条目，直接喂给 Taskmaster 做任务分解。

权威来源：`docs/adr/ADR-0032-save-resume-determinism.md`

---

## A. 核心实现缺口（按 Acceptance Criteria 分组）

> 标注规则：  
> - `[MUST]`：不做就不能把 ADR 设为 Accepted  
> - `Evidence`：必须能稳定落到 `logs/**` 的证据路径（或等价字段口径）

### A1) 存档边界实现到位（AC-1）[MUST]

- 需求：节点前存档；进入战斗保存“战斗初始状态”；战斗中不保存中间态；战斗中断继续只回到初始状态。
- 验收：同一场战斗中执行 1–2 次动作后退出，Continue 后回到战斗初始。
- Evidence：
  - `logs/ci/<YYYY-MM-DD>/security/security-audit.jsonl`（至少记录：save.write、save.read、continue.resume、reason）

### A2) 三选一候选集锁定（AC-2）[MUST]

- 需求：首次生成即落盘 `stable_ids[] + display_order[] + provenance`；退出重进后候选集与顺序完全一致；允许重新选择但不得重抽/重滚。
- 验收：同一节点触发三选一，截图记录候选；退出到主菜单→Continue；候选与顺序完全一致。
- Evidence：
  - `logs/ci/<YYYY-MM-DD>/security/security-audit.jsonl`（记录：offer.locked，含 stable_ids 与 display_order 的摘要或 hash）

### A3) 确定性边界（Scope）到位（AC-3）[MUST]

- 需求：纯 UI 行为不得推进 RNG；同一存档点+同一输入序列可复现；RNG streams 拆分并持久化必要状态。
- 验收：在奖励界面反复打开/关闭详情、切页、切卡等 UI 操作，不得导致下一次候选集漂移。
- Evidence：
  - `logs/ci/<YYYY-MM-DD>/security/security-audit.jsonl`（记录：rng.advance 的 caller/area，确保 UI path 不产生 rng.advance）

### A4) 原子写与坏档处置（AC-4）[MUST]

- 需求：autosave 原子写；失败保留上一份；Continue 读档做完整性校验；损坏/不兼容阻断 Continue 并提示。
- 验收：构造坏档（或模拟校验失败）后，Continue 被阻断且提示可操作。
- Evidence：
  - `logs/ci/<YYYY-MM-DD>/security/security-audit.jsonl`（记录：continue.blocked，reason=corrupt/incompatible）

### A5) 迁移门禁到位（AC-5）[MUST]

- 需求：迁移幂等；失败不得写回；失败阻断 Continue 并提示；迁移取证写入 summary.json。
- Evidence：
  - `logs/ci/<YYYY-MM-DD>/save-migrations/<timestamp>/summary.json`

### A6) 审计取证到位（AC-6）[MUST]

- 需求：关键动作写 `user://logs/security/security-audit.jsonl`；字段至少 `{ts, area, action, reason, target, caller}`；自动化测试/门禁结束归档到仓库 `logs/ci/.../security-audit.jsonl`（口径见 `project-context.md`）。
- Evidence：
  - `logs/ci/<YYYY-MM-DD>/security/security-audit.jsonl`

### A7) 自动化验证最小集（AC-7/8/9）[MUST]

- 需求：至少 1 个 xUnit 覆盖候选集锁定不漂移；至少 1 个 headless 冒烟覆盖 Continue 被阻断路径；测试路径稳定可被 PRD Test-Refs 引用；`logs/**` 证据链稳定产出。
- 当前 ADR-0032 已给出 Test-Refs（但尚未验证为真实文件）：
  - `Game.Core.Tests/Determinism/OfferLockingTests.cs`
  - `Game.Core.Tests/Save/SaveResumeBoundaryTests.cs`
  - `Tests.Godot/Smoke/ContinueGateTests.gd`
  - `Tests.Godot/Security/SaveMigrationFailureBlocksContinueTests.gd`
- Evidence：
  - 测试报告与归档日志路径（按 `project-context.md` 口径）

---

## B. 文档与回链缺口（防口径漂移）

- [MUST] PRD 的 `Test-Refs` 目前为空：`docs/prd/PRD-NEWROUGE-GAME-0001.md` 需要补齐到上述真实测试路径（或临时占位但必须后续替换为真实文件）。
- [MUST] 若 ADR-0032 成为 Accepted：必须把 Status 从 Proposed 改为 Accepted，并在 ADR 索引中反映状态变更（`docs/architecture/ADR_INDEX_GODOT.md`）。

---

## C. 建议的 Taskmaster 拆分粒度（直接可转任务）

> 你不用把这些写进 PRD 正文；把它们拆成任务更有效。

1) Offer locking：数据结构 + 持久化 + 恢复一致性 + xUnit  
2) Save boundary：节点前存档 + 战斗初始存档 + 恢复逻辑 + 冒烟  
3) Continue gate：校验/迁移失败阻断 + UX 提示 + 审计  
4) Audit pipeline：user:// 审计写入 + CI 归档到 logs/ci + 字段校验  
5) Test-Refs 对齐：PRD Test-Refs 指向真实文件；禁止重命名已引用路径  
