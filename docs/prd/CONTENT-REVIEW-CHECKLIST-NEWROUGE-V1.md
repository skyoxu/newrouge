---
SPEC-ID: CONTENT-REVIEW-CHECKLIST-NEWROUGE-V1
Title: NewRouge v1 内容制作验收清单（P0/P1）
Status: Draft
Owner: skyo
Last Updated: 2026-01-23
Encoding: UTF-8
Applies-To:
  - docs/prd/PRD-NEWROUGE-GAME-0001.md
---

# NewRouge v1 内容制作验收清单（P0/P1）

用途：给策划/内容制作/QA 一份 v1 的“内容可上线”检查清单，覆盖：
- 数据一致性（ID、引用、翻译 key）
- 玩法边界（锁定项不退化）
- 可取证性（存档/候选集锁定/审计证据链）

约束声明：
- 本文档只做文档规格，不做任何代码实现/dev 操作。
- 本文档不创建任何 `docs/contracts/**` 类型的契约文件。

权威引用：
- v1 锁定表（SSoT）：`docs/prd/SSOT-LOCKS-NEWROUGE-V1.md`
- 内容稳定 ID：`_bmad-output/content-id-standard.md`
- 内容登记表：`_bmad-output/content-registry.md`
- 存档/确定性：`docs/adr/ADR-0032-save-resume-determinism.md`
- 项目硬口径：`project-context.md`
- 组合禁区：`docs/prd/CONTENT-POWER-BOUNDS-AND-COMBO-RULES-NEWROUGE-V1.md`

---

## P0（Stop-Ship）：触发任一条直接拒绝合入

### 0) ID 与引用（稳定性）

- [ ] `content_id` 符合语法（全小写 ASCII + `.` 分层 + slug 仅 `[a-z0-9_]+`）。
- [ ] `content_id` 在 `_bmad-output/content-registry.md` 可检索到（新增前已登记）。
- [ ] 不复用已发布 ID；若“改语义/重做”，必须新增新 ID，并保留旧 ID 的墓碑/迁移说明（不得静默覆盖）。

### 1) 翻译与可见文本（禁止硬编码）

- [ ] 所有可见文本均有 Translations key 规划，且 key 由 `content_id` 派生（见 `_bmad-output/content-id-standard.md`）。
- [ ] 任何 UI/文案不得出现“商店升级/战斗中断点续打/退出重进刷结果”等误导性语境（见 SSoT 锁定项）。

### 2) 确定性与退出重进（反刷随机）

- [ ] 若涉及三选一/多选一奖励：候选集锁定字段满足 `stable_ids + display_order + provenance`，退出重进候选集与顺序不变（ADR-0032）。
- [ ] UI 行为不推进 RNG；“事件内路线切换”等纯输入不触发随机推进（ADR-0032）。

### 3) 卡牌升级系统（v1 锁定项）

- [ ] 商店不提供升级（任何形式都不行）。
- [ ] U1 升级为 Route A/B 二选一且不可逆；Ultimate 不可逆且不可换路线。
- [ ] 升级态不生成新 card_id；升级以实例字段表达（`upgrade_tier/upgrade_route`）。

### 4) 组合禁区（系统级破坏）

- [ ] 不存在无上限递归触发、无限资源、常驻免疫、控制链锁死等“禁区组合”（见 `CONTENT-POWER-BOUNDS...`）。

---

## P1（必须修正）：影响体验一致性/可维护性

### 1) 内容规模与投放一致性

- [ ] 内容规模不偏离 v1 规划（角色/卡牌/事件/遗物/难度/天赋树），新增内容不暗示不存在系统。
- [ ] 事件投放遵循：同局不重复边界=event_id；跨局重复抑制策略存在（参数不在内容侧散落）。

### 2) 可解释性与可读性

- [ ] 文案简短明确；结果摘要能用 1–2 句解释“代价/收益/为什么发生”。
- [ ] 复杂效果必须可被 UI 清晰表达（尤其是：debuff 叠加、姿态切换、怒气状态 buff）。

### 3) 取证与日志对齐（内容侧验收点）

- [ ] 涉及存档/候选集锁定/覆盖确认等关键路径，必须能产出可归档的证据（日志路径口径见 `project-context.md` 与 ADR-0032）。

---

## 最小验收产物（建议随 PR/变更一起提交）

- [ ] 更新 `_bmad-output/content-registry.md`（登记表为 SSoT）
- [ ] 更新或新增事件目录对账（如新增 event_id）：`docs/prd/EVENT-ID-CATALOG-NEWROUGE-V1.md`
- [ ] 如涉及高风险口径（确定性/存档/安全）：引用或新增 ADR，并补齐 Test-Refs 与 `logs/**` 证据链

