## Executive Summary

### Core Concept

NewRouge 是一款“黑暗主题”的单人卡牌构筑 roguelike：玩家在 3 Act 分叉地图中推进，节点由战斗/精英/事件/商店/休整组成，通过奖励三选一逐步构筑牌组与遗物引擎，目标是在单局约 60 分钟内完成通关或在失败中积累长线进展。

首发包含 3 个机制差异明显的角色：战士（怒气作为状态型 buff 而非第二资源条）、刺客（擅长给敌人叠加多种 debuff 并围绕 debuff 做增幅/引爆）、德鲁伊（姿态/状态的持久 buff 与切换后的定点爆发）。元系统为“共享天赋树”，支持无条件重置，鼓励玩家反复试验流派；难度体系 10 档以数值曲线为主，不与天赋树强绑定。单局 60 分钟的黑暗卡牌肉鸽，用共享可重置天赋树鼓励流派实验，并用确定性反刷随机的存档契约保护玩家信任。

### Game Type

**Type:** Card Game (`card-game`)  
**Structure Tags:** Roguelike（run-based，3 Acts，branching map）

### Determinism & Save/Resume Contract（ADR-0032）

本项目将“退出重进不刷结果”作为硬约束，以保护玩家信任并支持 QA 复现（参考 ADR-0032）：

- 单槽自动存档：仅维护一个系统自动存档；主菜单提供唯一入口 Continue Game 读取该槽；新开一局允许覆盖旧存档但必须二次确认且不可撤销。
- 自动存档生命周期：Continue 仅在“进行中的 run 且校验通过”时可用；run 结束（死亡/通关）必须作废 autosave，Continue 不得回到已结束 run。
- 战斗保存边界：节点前存档；进入战斗仅保存“战斗初始状态”；战斗中绝不保存中间态；任何战斗中断后的继续游戏只能回到战斗初始状态。
- 严格确定性定义：不重抽不重滚；同 seed + 同输入序列 = 同一结果（玩家操作不同可导致不同结果）；对“三选一”场景，退出重进后候选集必须固定不变（允许重新选择，但候选项集合不变）。
- 确定性的边界（Scope）：仅“会影响局势的玩家输入”计入输入序列；纯 UI 行为不得推进 RNG 或改变候选集。
- 候选集锁定粒度（Lock granularity）：所有“三选一”必须持久化候选项的稳定 ID 列表与展示顺序；退出重进后保持完全一致，只允许重新选择。
- 存档一致性与坏档处置：自动存档写入必须原子化；Continue 读档必须做完整性校验；损坏/不兼容时必须阻止 Continue 并提示。
- RNG 流拆分：RNG 按系统拆分（run/combat/event/loot）；并在存档点持久化必要 RNG 状态，确保退出重进不改变候选集与战斗初始局面。
- 可审计性证据：每次存档写入/读档/迁移/阻断 Continue（含原因）都必须写入结构化审计记录，便于复现与客服排障（审计产物遵循 `logs/**` 口径）。

### Top Risks（摘要级）

- R1 退出重进规则被误解 | Mitigation: 主菜单/帮助/战斗开始三处统一解释 | Acceptance: 三处文案一致且可被引用
- R2 确定性被 UI/实现细节破坏 | Mitigation: UI 不推进 RNG + 候选集落盘（ID+顺序+来源） | Acceptance: 重载候选集与顺序完全一致
- R3 单槽覆盖误操作 | Mitigation: New Run 覆盖二次确认默认取消 | Acceptance: 无“一键误删”
- R4 坏档/迁移失败扩大损坏 | Mitigation: 原子写入 + 校验失败阻断 Continue + 幂等迁移失败不写回 | Acceptance: 不崩溃、不半加载、有 `logs/**` 证据

### Failure Mode Checklist（Save/Resume & Determinism）

- Autosave 写入必须 atomic；失败必须保留上一份 autosave。
- Continue 必须做 integrity 校验；corrupted/incompatible 必须阻断 Continue 并给出明确提示。
- Migrations 必须 idempotent；失败不得写回；并产出 `logs/ci/<YYYY-MM-DD>/save-migrations/<timestamp>/summary.json`。
- 只有 gameplay-affecting inputs 才推进 RNG；纯 UI inputs 不得推进。
- RNG streams 拆分（run/combat/event/loot），并在存档边界持久化必要状态。
- “三选一”必须持久化 stable IDs + display order + provenance；重载必须完全一致（含顺序）。

