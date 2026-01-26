---
SPEC-ID: PLAYER-CONFUSION-FIX-TRACKER-NEWROUGE-V1
Title: NewRouge 玩家困惑点 → 修正策略追踪表（v1）
Status: Draft
Owner: skyo
Last Updated: 2026-01-23
Encoding: UTF-8
Applies-To:
  - docs/prd/PRD-NEWROUGE-GAME-0001.md
---

# NewRouge 玩家困惑点 → 修正策略追踪表（v1）

用途：把“玩家困惑点”从散文建议收敛成可追踪条目：每条都能落到具体修正策略与验收点，便于策划/QA/研发按同一表推进与回归。

约束声明：
- 本文档只做文档规格与追踪，不做任何代码实现/dev 操作。
- 本文档不创建任何 `docs/contracts/**` 类型的契约文件。

权威引用：
- v1 逐屏体验规格：`docs/prd/SCREEN-BY-SCREEN-PLAYER-SPECS-NEWROUGE-V1.md`
- v1 锁定项（SSoT）：`docs/prd/SSOT-LOCKS-NEWROUGE-V1.md`
- 文案禁用语境：`docs/prd/COPY-FORBIDDEN-WORDS-QA-CHECKLIST-NEWROUGE-V1.md`
- 术语与按钮文案表：`docs/prd/TERMS-AND-COPY-GLOSSARY-NEWROUGE-V1.md`
- 回归基线：`docs/prd/BALANCE-REGRESSION-BASELINE-NEWROUGE-V1.md`

---

## 1) 状态枚举（仅文档用）

- `SPEC-READY`：修正策略已写成明确规格（可直接验收）。
- `NEEDS-DECISION`：需要决策补充（否则无法验收）。
- `OUT-OF-SCOPE-V1`：明确不在 v1 范围（仅记录，避免反复讨论）。

---

## 2) 追踪表（v1）

| ID | 场景/屏幕 | 玩家困惑点（可复现） | 修正策略（可执行） | 边界条件/注意事项 | 验收点（至少 1 个） | 状态 | 来源入口 |
|---|---|---|---|---|---|---|---|
| UX-001 | MainMenu | 不理解“继续游戏”会加载什么 | 显示“继续=读取自动保存（单槽）”短句；提供摘要（可选） | 不暗示多槽或可刷结果 | `SCREEN-BY-SCREEN` 1) | SPEC-READY | SSoT/ADR-0032 |
| UX-002 | 覆盖确认 | 误操作覆盖进度 | 二次确认 + 默认焦点=取消 + 文案明确“不可撤销” | 破坏性按钮不得用“确定” | `SCREEN-BY-SCREEN` 2) | SPEC-READY | ADR-0032 |
| UX-003 | Continue Gate | 坏档/迁移失败时玩家不知道怎么办 | 阻断 Continue + 可恢复提示 + 提供“查看日志/返回主菜单” | 不允许“带病运行” | `SCREEN-BY-SCREEN` 1) | SPEC-READY | ADR-0032 |
| UX-010 | 难度选择 | 误以为难度绑定天赋树/必须刷元系统 | 明确“难度=数值曲线；不强绑定天赋树” | 避免承诺掉落概率 | `SCREEN-BY-S-S` 3) | SPEC-READY | PRD |
| UX-020 | 路线图 | 不理解“进入节点后不能改路” | 进入节点前明确确认动作；提示存档边界 | 不让玩家误以为可回滚改路 | `SCREEN-BY-S-S` 6) | SPEC-READY | ADR-0032 |
| UX-030 | 事件 | 选项差异不清晰/结果像黑箱 | A/B 必须在代价/收益/倾向上有可读差异；结果必须有摘要 | 文案短，数字与对象明确 | `SCREEN-BY-S-S` 7) | NEEDS-DECISION | 内容侧 |
| UX-031 | 三选一奖励 | 玩家尝试退出重进刷候选 | 显示“候选已锁定（退出不会刷新）” | UI 行为不得推进 RNG | `SCREEN-BY-S-S` 11) | SPEC-READY | ADR-0032 |
| UX-032 | 商店 | 玩家找升级/误以为能升级 | 商店禁止出现升级语境；只出现购买/移除/转换等 | 禁用词扫描必过 | `SCREEN-BY-S-S` 8) | SPEC-READY | SSoT |
| UX-040 | 休整升级 | 玩家不理解“升级不可逆”或误以为可撤销 | 升级界面固定短句“选择后不可逆” | 与路线重选事件区分清楚 | `SCREEN-BY-S-S` 9/12) | SPEC-READY | SSoT |
| UX-041 | 路线重选事件 | 玩家误以为“以后都能随时改路线” | 明确：事件内可切换，离开事件定稿 | 不使用“重置/随时可改”措辞 | `SCREEN-BY-S-S` 12) | SPEC-READY | SSoT |
| UX-042 | Ultimate | 玩家误以为 Ultimate 还能继续升级或换路线 | 固定警告短句：不可逆/不可再升级/不可换路线 | 避免“进阶路线”措辞 | `SCREEN-BY-S-S` 12) | SPEC-READY | SSoT |
| UX-050 | 战斗中退出 | 玩家希望从中途继续 | 明确告知：继续只回到战斗初始状态 | 不出现“断点续打”语境 | `SCREEN-BY-S-S` 10) | SPEC-READY | ADR-0032 |

说明：
- `SCREEN-BY-S-S` 指 `docs/prd/SCREEN-BY-SCREEN-PLAYER-SPECS-NEWROUGE-V1.md`。

