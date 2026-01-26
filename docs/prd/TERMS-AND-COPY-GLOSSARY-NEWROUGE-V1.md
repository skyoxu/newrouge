---
SPEC-ID: TERMS-AND-COPY-GLOSSARY-NEWROUGE-V1
Title: NewRouge v1 全局术语与按钮文案表（卡牌肉鸽）
Status: Draft
Owner: skyo
Last Updated: 2026-01-23
Encoding: UTF-8
Applies-To:
  - docs/prd/PRD-NEWROUGE-GAME-0001.md
---

# TERMS-AND-COPY-GLOSSARY-NEWROUGE-V1：全局术语与按钮文案表（v1）

用途：统一 v1 的核心术语与按钮文案，避免“同一概念多种说法”导致玩家与团队误解，并支撑 NewRouge 的高风险口径：
- 单槽 autosave + Continue
- 退出重进不刷结果（候选集锁定，UI 不推进 RNG）
- 升级不可逆（U1 二选一；Ultimate 不可逆）
- 商店不升级（任何升级语境禁止出现在商店）

约束声明：
- 本文档只做文档规格，不做任何代码实现/dev 操作。
- 本文档不创建任何 `docs/contracts/**` 类型的契约文件。

权威引用：
- v1 锁定项（SSoT）：`docs/prd/SSOT-LOCKS-NEWROUGE-V1.md`
- 逐屏体验规格：`docs/prd/SCREEN-BY-SCREEN-PLAYER-SPECS-NEWROUGE-V1.md`
- 文案风格指南（禁用语境）：`docs/prd/NARRATIVE-AND-COPY-STYLE-GUIDE-NEWROUGE-V1.md`
- 可解释反馈输出规格：`docs/prd/PLAYER-FEEDBACK-EXPLAINABILITY-NEWROUGE-V1.md`
- 存档/确定性：`docs/adr/ADR-0032-save-resume-determinism.md`

---

## 1) 必须统一的术语（团队与玩家共用）

- `MainMenu`：主菜单
- `Continue`：继续游戏（读取单槽 autosave）
- `New Game`：新游戏
- `autosave`：自动保存（单槽）
- `run`：一次游戏进程（从开始到失败/通关/放弃结束）
- `Act`：章节（Act1/Act2/Act3）
- `node`：节点（路线图上的一次进入）
- `Act Map`：分叉路线图
- `event`：事件（事件节点）
- `shop`：商店（禁止升级语境）
- `rest`：休整（包含“免费升级 1 张”选项）
- `reward`：奖励结算（含三选一/多选一）
- `candidate set`：候选集（必须锁定）
- `offer locking`：候选集锁定（退出重进不刷新）
- `battle initial state`：战斗初始状态（战斗中断后继续只回到此状态）
- `U1`：常规升级（一次升级，Route A/B 二选一不可逆）
- `Route A / Route B`：升级路线（仅 U1 有路线）
- `Ultimate`：终极形态（稀有机会；不可逆；不可再升级；不可换路线）

---

## 2) 按钮文案（v1 建议固定）

说明：按钮文案一旦用于 UI，应当保持一致（Translations 统一维护）；不要用“同义词”替换。

### 2.1 MainMenu

- `新游戏`
- `继续游戏`
- `设置`（可选）
- `退出`

### 2.2 Overwrite Confirm（覆盖确认，危险操作）

- 标题：`覆盖进度？`
- 正文（建议）：`将覆盖当前自动保存进度，且不可撤销。`
- 按钮：`取消`（默认焦点） / `确认覆盖`

### 2.3 Difficulty Select（难度选择）

- 标题：`难度`
- 说明（建议短句）：`难度影响敌人与奖励曲线。`
- 补充（建议短句）：`难度与天赋树不强绑定。`
- 按钮：`确认` / `返回`

### 2.4 Hero Select（角色选择）

- 标题：`选择角色`
- 按钮：`确认` / `返回`

### 2.5 Meta（天赋树）

- 标题：`天赋树`
- 按钮：`重置天赋` / `返回`
- 重置确认（若有）：`取消`（默认焦点） / `确认重置`

### 2.6 Act Map（路线图）

- 主动作：`进入节点`
- 次动作：`返回`（或 `取消`）

### 2.7 Event（事件）

- 主动作：`确认选择`
- 次动作：`返回`（若允许；但不得破坏节点前存档边界）

### 2.8 Shop（商店）

- 主动作（示例）：`购买`
- 服务（示例）：`移除` / `转换` / `重铸`
- 离开：`离开商店`

硬禁区：
- 商店内禁止出现任何“升级”相关按钮或同义词（见禁用词清单）。

### 2.9 Rest（休整）

- 选项（示例）：`恢复` / `升级` / `离开`
- 升级说明（建议短句）：`免费升级 1 张卡牌（不可逆）。`

### 2.10 Rewards（三选一/多选一奖励）

- 标题：`选择奖励`
- 主动作：`确认选择`
- 若允许跳过：`跳过`（可选，但必须明确不会刷新候选）

候选锁定提示短句（二选一）：
- `候选已锁定（退出不会刷新）。`
- `候选固定（退出不会改变）。`

### 2.11 Upgrade（升级：U1/重选/Ultimate）

U1（Route A/B）：
- 标题：`升级（二选一）`
- 警告短句：`选择后不可逆。`
- 按钮：`选择路线 A` / `选择路线 B` / `返回`

路线重选事件：
- 标题：`重选路线`
- 提示短句：`事件内可随意切换，离开事件时定稿。`
- 按钮：`应用路线 A` / `应用路线 B` / `确认并离开`

Ultimate：
- 标题：`终极形态`
- 警告短句：`不可逆。不可再升级。不可换路线。`
- 按钮：`确认进阶` / `返回`

---

## 3) 错误提示文案槽位（统一格式）

所有可恢复错误提示建议包含：
- 标题（短）
- 正文（短，给可操作建议）
- 动作按钮（1–2 个）
- 错误码（可选但强烈建议）

错误码建议格式（示例）：`NR-SAVE-0001` / `NR-MIGRATION-0001` / `NR-CONTENT-0001`

危险操作按钮规范（v1）：
- 任何会删除/覆盖 autosave 的动作：
  - 必须提供 `取消`
  - 默认焦点必须在 `取消`
  - 破坏性按钮文案必须明确（例如 `确认覆盖`），不得使用含糊词（例如“确定”）

---

## 4) 禁用词（快速入口）

- 一页速扫清单：`docs/prd/COPY-FORBIDDEN-WORDS-QA-CHECKLIST-NEWROUGE-V1.md`

