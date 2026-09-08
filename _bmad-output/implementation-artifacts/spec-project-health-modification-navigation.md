---
title: '任务级游戏修改导航'
type: 'feature'
created: '2026-09-08'
status: 'done'
baseline_commit: '14e2d3297830d6a34382c97a21d962ec3e063440'
review_loop_iteration: 0
context: ['C:/buildgame/newrouge/AGENTS.md', 'C:/buildgame/newrouge/project-context.md', 'C:/buildgame/newrouge/docs/testing-framework.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

用户已同意继续：让用户读任务详情就知道如何通过配置、场景、脚本和测试修改游戏，同时看到节点与素材关系。先以 T24 初始牌组和 T115 Reward 为实例，再用通用规则覆盖其他任务。用户追加授权：已有配置但代码仍同义硬编码时顺手修复。

## Boundaries & Constraints

**Always:** 只基于扫描的本地 main 同一 revision 构造导航；遵循 Accepted ADR-0035、ADR-0007。配置字段展示精确 JSON Pointer、当前值、原文引用位置。静态直接引用、符号或共享 ID 候选、真实运行观测必须区分。中文沟通与文档，代码和页面文本英文。使用 apply_patch 保留已有改动；日志与测试证据在 logs。先写失败测试再实现新增行为。

**Ask First:** 改变现有玩法规则、扩大来源权限。

**Never:** 从测试通过臆造配置/素材已经运行使用；不能把初始十张独立卡与 5+4+1 数据当作同义替换；不放宽正式 KCP/Impact，不自动提交或推送，不运行全量 Godot 验证。

## I/O & Edge-Case Matrix

| 情况 | 输入 | 期望 | 处理 |
| --- | --- | --- | --- |
| 配置引用 | 范围内源码引用 JSON | 字段、值、引用行、证据链 | 生效时机未知时明确说明 |
| 节点资源 | tscn 属性经 subresource 或 tres 指向素材 | NodePath、属性及资源链 | 循环有界，无挂起 |
| 动态绑定 | 脚本动态赋值纹理 | 展示源码和素材线索 | 不伪造精确节点绑定 |
| 缺失/越界 | 未扫描路径或非法路径 | 不读取任意工作区文件 | 标注限制 |
| 硬编码冲突 | 配置与旧服务规则不同 | 不自动改变玩法 | decision log 与后续入口 |

</frozen-after-approval>

## Code Map

- `scripts/python/_project_health_navigation.py`：上一阶段未提交草稿，尚未接入；可保留，但补充测试验证，删除无用 readers 重复计算。references、fields、scene_nodes、build_navigation 为现有入口。跨 tres 资源、instance 属性解析和候选后遍历需要补齐。测试命令只能标为建议。
- `scripts/python/project_health_knowledge.py`：scan 仅补充 cs/gd/tscn/tres，漏掉卡牌 JSON；增加限定配置后缀与资产路径清单。task 分支按需构造导航，避免每次扫描为所有任务建图。
- `scripts/python/_knowledge_catalog_builder.py`：DirectorySnapshot 的扩展需维持有界来源和内容身份；避免把二进制当 UTF8。
- `scripts/python/project_health_knowledge.js` 与 HTML：task 弹窗现仅 JSON 和链接；增配置、代码、节点、素材、测试分区，用 textContent 防注入。sourceLink 仅用于可打开的文本。
- `Game.Core/Data/m1-warrior-starting-deck.json`、`m1-card-definitions.json`、`m1-card-pools.json`：数据表；Main.gd、CombatScene.cs、RewardOfferProvider.cs 为实际读取线索。
- `Game.Core/Services/WarriorStartingDeckService.cs`、`CardPoolCatalog.cs`：疑似硬编码，但必须对比规则。T24 旧服务十张不同卡，测试与 PRD 7普通+2优良+1精英约束；JSON 5+4+1，不能无依据迁移。
- `Game.Godot/Scenes/Reward.tscn`、`Game.Godot/Scripts/RewardScene.gd`：ArtButton 动态纹理；静态关系未知必须如实显示。
- `Game.Godot/Scripts/Main.gd`：`_resolve_reward_entry_title` 三种 card_choice 固定显示 3-Choice，而真实卡数已读取 config.pick；改标题为读取同一 pick，默认仍为 3。这是可保持默认玩法的同义修复，补充 pick=1/2/3 的窄 GdUnit 测试。若引擎不可用，明确报告运行验证缺口。CardPoolCatalog 与 JSON 缺失 shop/Act2/3、稀有度与 pool ID 差异，不直接替换。

## Tasks & Acceptance

**Execution:**
- [x] 扫描器与导航模块：补配置、来源清单、证据链、节点资源解析和保守边界。
- [x] 页面：可读的修改导航，保留完整原始详情；不暴露二进制源码接口。
- [x] 测试：覆盖矩阵及 T24/T115 真实来源；运行相关 Python 回归与 JS 语法检查。
- [x] 配置硬编码审计：修复有充分证据的同义重复；不同玩法保留并记录后续入口。
- [x] 文档：更新 project-health-knowledge 使用说明，记录验证证据和未解决问题。

**Acceptance Criteria:**
- Given 已重新扫描 main，when 打开任务详情，then 有 revision 绑定的配置/场景/素材/代码/验证入口，缺失关联有说明。
- Given T115 动态图片加载，when 查看节点关系，then 静态未解析的绑定不会被标记为真实运行观测。
- Given 配置驱动修复，when 改变输入配置，then 行为相应变化且既有语义测试通过；无可安全替换项时展示审计结论。

## Spec Change Log

- 2026-09-08：三层审查后的局部修复补齐缺失根引用、空格路径与大小写、多行资源及深度预算、跨快照源码保护、完整详情返回；补精确列号与 NodePath 验证。保持静态候选语义和现有玩法不变。审查及浏览器证据：`logs/ci/2026-09-08/project-health-navigation/`。

## Design Notes

已有继续授权适用于同一任务草稿，无需重复审批。引用链为修改导航而非语义验收。共享卡 ID 只能建立候选关联。对未能安全统一的规则，按仓库要求先写 decision log，再写 execution plan。

## Verification

- `py -3 -m unittest scripts.sc.tests.test_project_health_knowledge scripts.sc.tests.test_project_health_server scripts.sc.tests.test_dev_cli_project_health_commands -v`
- 新导航测试、`node --check scripts/python/project_health_knowledge.js`、`git diff --check`
- 修改 C# 时跑匹配的 xUnit；实际 main scan 与 task 24/115 结果保存 logs。不将未提交代码说成 main 证据。

实际结果：64 项 Python 回归通过；奖励标题 GdUnit 两项通过（修改前配置数量断言已真实失败）；JS、diff、恢复文档校验通过。Chrome 实际验证 T24/T115 导航、源码返回、验证按钮恢复和 revision 漂移拒绝。未进行全量 Godot 批量验证；保留未提交工作区供审阅。

## Suggested Review Order

- 从任务来源构造保守证据链，区分直接引用与候选。
  [_project_health_navigation.py:157](../../scripts/python/_project_health_navigation.py#L157)
- 场景节点资源解析有界，无法解析时显式说明。
  [_project_health_navigation.py:46](../../scripts/python/_project_health_navigation.py#L46)
- 扫描清单与文本分离，保持来源范围。
  [project_health_knowledge.py:171](../../scripts/python/project_health_knowledge.py#L171)
- 源码打开验证 revision，返回恢复完整任务操作。
  [project_health_knowledge.js:50](../../scripts/python/project_health_knowledge.js#L50)
- 奖励标题读取已有 pick 配置。
  [Main.gd:553](../../Game.Godot/Scripts/Main.gd#L553)
- 精确位置、节点层级、路径和资源边界回归。
  [test_project_health_navigation.py:12](../../scripts/sc/tests/test_project_health_navigation.py#L12)
- 不同玩法来源保留明确后续入口。
  [configuration-audit.md:1](../../decision-logs/2026-09-08-project-health-configuration-audit.md#L1)
