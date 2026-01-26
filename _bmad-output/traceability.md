---
title: "Traceability Matrix"
project: "newrouge"
date: "2026-01-23"
author: "skyo"
sources:
  - docs/prd/PRD-NEWROUGE-GAME-0001.md
  - _bmad-output/gdd.md
  - _bmad-output/epics.md
  - docs/adr/ADR-0032-save-resume-determinism.md
---

# 可追溯对齐表（PRD → GDD → Epics）

目标：在进入更重内容的 game-design 角色前，先把“需求 → 设计 → 交付单元”的映射钉死，降低返工与口径漂移。

## 映射规则

- **PRD**：`docs/prd/PRD-NEWROUGE-GAME-0001.md`
- **GDD**：`_bmad-output/gdd.md`
- **Epics**：`_bmad-output/epics.md`（Epic 1–7）
- **硬口径**：存档/确定性以 `docs/adr/ADR-0032-save-resume-determinism.md` 为准（并在 `project-context.md` 冻结）

---

## 目录级对齐（按 PRD 章节）

| PRD 章节 | PRD 核心承诺（摘要） | GDD 对应章节 | Epics 对应 | 备注（风险/冲突点） |
|---|---|---|---|---|
| 0 范围与止损 | 避免“复刻”，做原创差异化；法律止损 | Goals and Context / USPs | 全部（贯穿） | 需要 game-design 阶段持续检查文本与命名是否“直接映射”同品类 |
| 1 目标与非目标 | 3 Act 闭环、3 角色、30 卡/角、20 遗物、40 事件、共享天赋树、10 难度；非目标：多人/Mod/跨平台 | Executive Summary / Out of Scope | 1–7 | v1 需要卡牌升级系统（仅休整或事件升级；商店不提供升级服务）；升级为“同一张卡的升级态” |
| 2 平台与技术约束 | Windows-only、Godot 4.5/.NET 8、60fps、门禁、可观测性、安全基线 | Target Platform(s) / Technical Specifications | 7（为主） | 这里的门禁/取证口径以 ADR/Base 为 SSoT，不在 GDD 复制阈值细节 |
| 3 体验支柱 | 构筑表达、代价抉择、机制差异、长线策略 | Core Gameplay / Goals and Context | 1–5 | 支柱将直接约束卡牌/事件的“代价感”与可读性设计 |
| 4 核心循环 | 选角→天赋→Act1→节点→三选一→Boss→下一Act→结算 | Core Gameplay / Game Mechanics | 1,2,5 | 必须与存档边界一致：节点前/入战斗为唯一边界 |
| 5 战斗系统 | 回合制战斗与状态交互（PRD 细节） | Game Mechanics / Card Game Specific Design | 1,2 | 需要在 game-design 阶段把“状态词表”与 UI 可读性控制住 |
| 6 角色设计 | 战士怒气 buff、刺客 debuff 工具箱、德鲁伊姿态爆发；每角多流派 | Game Mechanics（角色身份）/ Card Game Specific（卡牌分布） | 3,4 | PRD 写“至少 3 条流派”，GDD/epics 需保持一致（已作为硬约束写入） |
| 7 卡牌系统 | 每角 30 基础卡；起始牌组 10 张（7/2/1）；稀有度；获取方式；卡牌升级 | Card Game Specific Design | 3,4 | v1 做 U1 常规升级（二选一路线，不可逆；特殊事件可改路线）+ Ultimate 终极形态（稀有机会）；升级不计入 30 张基础卡 |
| 8 遗物系统 | 20 个遗物；规则改变/构筑方向优先 | Game Mechanics / Progression and Balance | 4 | 遗物需与三角色机制联动但避免“强度全靠抽到” |
| 9 地图与节点 | 分叉路线图；节点类型；节奏目标 | Level Design Framework | 1,4 | 单局 60 分钟目标会反向约束节点数与战斗时长 |
| 10 事件系统 | 40 事件；同局不重复；跨局重复抑制；事件结构要求 | Level Design Framework / Progression and Balance | 4 | 必须冻结稳定 ID 与文本分离规则，避免后期内容漂移 |
| 11 共享天赋树 | 可无条件重置；影响规则/权重 | Progression and Balance | 5 | 天赋树与 10 难度不强绑定（难度偏数值曲线） |
| 12 难度体系 | 10 档，影响敌人与奖励曲线 | Progression and Balance | 5 | 需要定义“数值影响范围”，避免难度把规则改乱 |
| 13 存档与回退规则 | 节点前存档；战斗初始态；退出重进不刷结果 | Executive Summary（ADR-0032）/ Out of Scope | 1,7 | 这是最高风险承重墙：必须持续以 ADR-0032 约束实现与 QA |
| 14 经济与商店 | 金币/商店等（PRD 细节） | Progression and Balance | 1,4 | 经济是“代价与抉择”的载体，需避免通胀与唯一最优 |
| 15 成功标准 | 验收条目 | Success Metrics | 7 | 需要在门禁脚本与 logs 工件里形成闭环 |
| 16 里程碑 | 交付导向 | Development Epics | 1–7 | Epics 已给出建议顺序 |
| 17 风险清单 | 高风险点 | Executive Summary / Assumptions and Dependencies | 1,7 | 存档确定性、内容规模、可读性与黑暗主题冲突是前三风险 |

---

## 结论（进入 game-design 前的“硬对齐”）

1) 你后续做角色/卡牌/事件设计时，只要能在表里找到它属于哪个 PRD 章节与哪个 Epic，就不容易写散。  
2) 任何会改变存档/确定性边界的想法，必须先改 ADR-0032（否则就是返工雷区）。  
3) v1 做升级的后果：每张卡必须定义清晰的升级差异（可预览）；升级是“显式玩家输入”，不应引入额外 RNG 与不确定性。  
