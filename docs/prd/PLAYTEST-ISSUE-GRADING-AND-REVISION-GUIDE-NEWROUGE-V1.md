---
SPEC-ID: PLAYTEST-ISSUE-GRADING-AND-REVISION-GUIDE-NEWROUGE-V1
Title: NewRouge 试玩问题分级与文档回填指引（v1）
Status: Draft
Owner: skyo
Last Updated: 2026-01-23
Encoding: UTF-8
Applies-To:
  - docs/prd/PRD-NEWROUGE-GAME-0001.md
---

# NewRouge 试玩问题分级与文档回填指引（v1）

用途：把试玩中观察到的问题快速分级（P0/P1/P2）并定位“该回填到哪份文档/哪类规格”，避免：
- 试玩发现了问题但无法形成可执行改动
- 口径只停留在讨论，未形成单一事实来源（SSoT）
- 修了表现但没修规则/文案/锁定项，导致下一版复发

约束声明：
- 本文档只做文档整改指引，不做任何代码实现/dev 操作。
- 本文档不创建任何 `docs/contracts/**` 类型的契约文件。

关联入口：
- 试玩脚本（60 分钟）：`docs/prd/PLAYTEST-SCRIPT-60MIN-NEWROUGE-V1.md`
- v1 锁定项（SSoT）：`docs/prd/SSOT-LOCKS-NEWROUGE-V1.md`
- 逐屏体验规格：`docs/prd/SCREEN-BY-SCREEN-PLAYER-SPECS-NEWROUGE-V1.md`
- 禁用语境清单：`docs/prd/COPY-FORBIDDEN-WORDS-QA-CHECKLIST-NEWROUGE-V1.md`
- 可解释反馈输出：`docs/prd/PLAYER-FEEDBACK-EXPLAINABILITY-NEWROUGE-V1.md`

---

## 1) 分级规则（P0/P1/P2）

### P0（必须阻塞）

满足任一条即为 P0：
1) 破坏硬锁定项（SSoT）  
   - 例如：商店出现升级语境；U1 被描述为可逆；Ultimate 可换路线；战斗中出现中间态继续；退出重进可刷结果。
2) 破坏确定性与取证  
   - 例如：同一存档点三选一候选集漂移；UI 行为推进 RNG；Continue 在坏档/迁移失败时仍放行。
3) 玩家无法闭环  
   - 关键路径不可达/卡死：新游戏→路线图→节点→战斗/事件→奖励→继续推进。
4) 可读性导致策略误判（且无法通过文案/展示修正）  
   - 例如：升级不可逆提示缺失；玩家误以为能刷候选；错误提示不可操作。

### P1（应尽快修复）

满足任一条即为 P1：
1) 玩家“能玩但持续误解”  
   - 例如：不理解 Continue 的边界；不理解“战斗初始状态”意味着什么；把天赋树重置误解为“卡牌升级重置”。
2) 内容投放可见性不足  
   - 新内容在 2–3 局内几乎不可见，导致教学与节奏目标落空。
3) 文案过长或术语漂移  
   - 同一概念多种说法，导致玩家找不到按钮或误解系统。

### P2（加分项）

满足任一条即为 P2：
1) 更顺的默认文案与提示（不改变规则）  
2) 更清晰的数值/状态展示（仍保持可解释）  
3) 更好的“玩家自救提示”（不引入新系统）

---

## 2) 问题分类（用于归因与回填）

每条试玩问题建议至少标注：`分级` + `分类` + `复现步骤` + `证据` + `建议回填点`。

### C1 存档与确定性（Continue/Offer locking）

优先回填到：
- `docs/adr/ADR-0032-save-resume-determinism.md`
- `docs/prd/SSOT-LOCKS-NEWROUGE-V1.md`
- `docs/prd/PLAYER-FEEDBACK-EXPLAINABILITY-NEWROUGE-V1.md`

### C2 升级系统（休整/U1/重选/Ultimate）

优先回填到：
- `docs/prd/SSOT-LOCKS-NEWROUGE-V1.md`
- `docs/prd/MECHANICS-EDGE-CASES-SSOT-NEWROUGE-V1.md`
- `docs/prd/TERMS-AND-COPY-GLOSSARY-NEWROUGE-V1.md`

### C3 商店与服务语境（商店不升级）

优先回填到：
- `docs/prd/SCREEN-BY-SCREEN-PLAYER-SPECS-NEWROUGE-V1.md`
- `docs/prd/COPY-FORBIDDEN-WORDS-QA-CHECKLIST-NEWROUGE-V1.md`

### C4 文案与术语一致性（Translations）

优先回填到：
- `docs/prd/NARRATIVE-AND-COPY-STYLE-GUIDE-NEWROUGE-V1.md`
- `docs/prd/TERMS-AND-COPY-GLOSSARY-NEWROUGE-V1.md`

### C5 内容生产与投放（ID/事件目录/验收）

优先回填到：
- `_bmad-output/content-registry.md`
- `docs/prd/EVENT-ID-CATALOG-NEWROUGE-V1.md`
- `docs/prd/CONTENT-REVIEW-CHECKLIST-NEWROUGE-V1.md`

---

## 3) 回填流程（建议 20 分钟内完成一次闭环）

1) 记录问题：按试玩脚本的表格记录证据（截图/录屏/日志路径）  
2) 定级：按本文件第 1 节判定 P0/P1/P2  
3) 归类：选 C1–C5（可多选，但必须给出主类）  
4) 选择回填点：按第 2 节定位到具体文档  
5) 修订文档：把口径写死（必要时同步更新 SSoT/ADR/禁用词清单）  
6) 复测最小用例：优先复测涉及的高风险屏（MainMenu/Reward/Upgrade/Shop/Continue Gate）  

---

## 4) 问题单模板（可直接复制）

| 分级 | 分类 | 场景/屏幕 | 复现步骤（按键序列/选择） | 预期 | 实际 | 证据（截图/录屏/日志路径） | 建议回填文档 | 修订结论 |
|---|---|---|---|---|---|---|---|---|

---

## 5) 一次填写示例（纸面走查，未启动游戏）

说明：
- 这不是“真实试玩问题单”，而是一次 **文档走查 + 文本扫描** 的示例，用于演示如何按本指南分级与回填。
- 对应走查报告：`logs/ci/2026-01-25/playtest/newrouge--playtest--issues--paper-audit--2026-01-25.md`

| 分级 | 分类 | 场景/屏幕 | 复现步骤（按键序列/选择） | 预期 | 实际 | 证据（截图/录屏/日志路径） | 建议回填文档 | 修订结论 |
|---|---|---|---|---|---|---|---|---|
| P1 | C4 文案与术语一致性 | 全局（Translations） | 文档走查：检查 `Game.Godot/Translations` 是否已有可用文本资源 | 所有可见文本可从 Translations 配置获得 | 当前仅有 `Game.Godot/Translations/README.md`（缺少实际文本资源） | `logs/ci/2026-01-25/playtest/newrouge--playtest--issues--paper-audit--2026-01-25.md` | `project-context.md`、`docs/prd/TERMS-AND-COPY-GLOSSARY-NEWROUGE-V1.md` | 需要补齐最小 Translations 资源后再做真实试玩校验 |
| P1 | C1 存档与确定性 | Continue/三选一 | 文档走查：确认 ADR-0032 已为 Accepted；检查“Implementation Acceptance Criteria（M1 Gate-0）”是否已任务化并可取证 | 有可执行的任务分解入口 | 已生成缺口清单，但仍需任务化与实现/取证 | `.taskmaster/docs/adr-0032-gap-checklist.md` | `docs/adr/ADR-0032-save-resume-determinism.md` | 用 Taskmaster 拆任务并推进到可验收证据与 `logs/**` 证据链 |
| P2 | C4 文案禁用语境 | 文档扫描范围 | 文本扫描：全仓 `docs/**` 扫禁用词 | 禁用词仅出现在“规则/反例/清单”中 | 命中点来自规则与反例文档（预期）；另有历史 overlay/migration 文档含“刷新”等旧语境 | `logs/ci/2026-01-25/playtest/newrouge--playtest--issues--paper-audit--2026-01-25.md` | `docs/prd/COPY-FORBIDDEN-WORDS-QA-CHECKLIST-NEWROUGE-V1.md` | 建议将“玩家可见文本”扫描限定到 Translations 资源目录，避免误报与噪音 |
