---
title: '收敛任务详情的信息密度'
type: 'feature'
created: '2026-09-08'
status: 'done'
review_loop_iteration: 0
context: ['C:/buildgame/newrouge/AGENTS.md', 'C:/buildgame/newrouge/project-context.md', 'C:/buildgame/newrouge/docs/workflows/project-health-knowledge.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 任务 115 的导航递归展开集成测试所引用的主场景，混入全局配置及共享卡牌候选；完整 JSON 再次重复全部数据，用户难以识别实际修改入口。

**Approach:** 默认显示直接相关的核心场景、脚本、配置记录、素材线索与任务测试。间接依赖和推断候选放进默认折叠的更多关联；完整 JSON、引用链与限制放进默认折叠的原始证据。通用规则适用于所有任务，不为 115 写专属过滤名单。

## Boundaries & Constraints

**Always:** 保留上一轮未提交改动。遵循 Accepted ADR-0035；导航继续绑定同一 main revision，静态引用不等于运行观测。保留所有已发现的证据，只改变分组与默认展示。中文文档和沟通，英文代码、测试及页面文案。

**Ask First:** 扩大扫描权限，改变任务映射或游戏规则。

**Never:** 自动提交、回退或推送；启动全量 Godot；用关键词排序冒充已确认任务归属；为了简洁隐藏运行失败或来源 revision；将共享 ID 候选提升为直接关联。

## I/O & Edge-Case Matrix

| 情况 | 输入 | 期望 | 边界 |
| --- | --- | --- | --- |
| 明确场景映射 | 115 映射 Reward，测试引用 Main 等 | Reward、附着脚本及直接资源为核心 | 测试环境场景属于更多关联 |
| 未明确映射 | 只有测试符号或共享 ID 候选 | 展示测试与核心关联缺失状态 | 不将猜测提升为直接归属 |
| 共享配置表 | 显式记录 ID 可定位字段 | 默认只列匹配记录字段 | 无精确匹配时只列路径，不展示全表 |
| 重复和多路径 | 同一文件可由核心和间接路径到达 | 核心列表去重，证据不丢失 | 不依赖集合遍历顺序 |
| 原始证据 | 用户主动展开 | 可查看完整任务 JSON、链与限制 | 默认折叠，源码查看仍可返回任务 |
| 运行失败或快照变化 | 既有运行失败、源码 revision 不同 | 失败摘要可见；拒绝混合 revision | 保留验证按钮与返回功能 |

</frozen-after-approval>

## Code Map

- `scripts/python/_project_health_navigation.py`：build_navigation 当前从任务根及测试文件双阶段各遍历五跳，再共享卡 ID 扩展；保留完整图，另派生可解释的核心/更多分组，不依赖既有单一路径决定核心归属。
- `scripts/python/_project_health_tasks.py`：godot.scenes 为验证过的明确静态映射，candidates 仅测试线索；沿用此差别，不新增映射。
- `Game.Godot/Scenes/Reward.tscn`、`RewardScene.gd`：只读实例。场景直接挂脚本，脚本引用兜底卡图及翻译表。动态卡图赋值仍不可宣称节点运行观测。
- `Tests.Godot/tests/Scenes/Reward/test_reward_scene_route_roundtrip.gd`：只读证据。引用 Main、Map、Combat、Event 等测试环境，不能据此归属整个游戏。
- `scripts/python/project_health_knowledge.js`：renderNavigation 当前五类全量列表，renderTaskDetail 还重复场景链接并直接输出完整 JSON。改分层渲染与折叠原始证据，复用 sourceLink 的 revision 校验和返回路径。
- `scripts/python/project_health_knowledge.html`、`.css`：弹窗结构与响应式约束；修改工具表面，不重做整个页面。
- `scripts/sc/tests/test_project_health_navigation.py`：既有精确字段、节点路径、资源链测试，新增核心边界、去重与字段筛选回归。

## Tasks & Acceptance

**Execution:**
- [ ] 导航模块：派生核心集合，只包含明确任务生产路径、明确场景附着脚本和它们直接引用的配置/素材；资源内的素材链可继续解析，测试环境不向核心传播。
- [ ] 配置字段：独立保留完整证据字段，派生匹配记录的摘要字段；匹配 ID 只能来自任务明确内容或核心源码，不能从间接共享表反向扩散。无匹配给出未定位提示。
- [ ] 页面：核心入口置前，更多关联和原始证据默认关闭；配置、节点属性与引用链按需展开，避免重复完整 JSON 和场景入口。验证按钮、失败状态、来源保持可见。
- [ ] 回归：先失败测试后实现；覆盖矩阵，验证 115 核心不含 Main/Combat/Shop，保留 Reward 和兜底卡图；24 候选仍可在更多关联查到。
- [ ] 文档与证据：更新使用说明；浏览器截图及点击回归放 logs，记录改前/改后的核心与完整关联数量。

**Acceptance Criteria:**
- Given 115 已扫描，when 首次打开详情，then 无需滚过全局配置表即可看到 Reward 核心入口和任务验证操作。
- Given 更多关联和原始证据，when 用户展开，then 可查看完整来源且无证据删除。
- Given 配置包含多个记录，when 只有一个明确 ID 匹配，then 默认字段不包含其他记录。
- Given 源码查看返回，when 返回详情，then 恢复核心布局和验证按钮；不同 revision 源码仍被拒绝。

## Spec Change Log

- 已获用户批准，在既有未提交改动上完成核心关联分组、记录字段筛选和默认折叠展示。115 实际 70 项入口收敛为 7 项核心与测试，其余 63 项按需展开。65 项 Python 测试、JS 语法、浏览器 T24/T115 展开返回与 revision 校验通过；桌面和窄屏截图在 `logs/ci/2026-09-08/project-health-navigation/focused-task-115*.png`。未提交。

## Design Notes

直接相关是可解释的结构关系，不表示语义验收通过。无明确映射时宁可显示未确认，也不把集成测试引用的所有场景升为核心。不以任意截断前若干项代替范围判断。

## Verification

- Python 导航、knowledge、server、dev_cli 相关单测全部通过。
- `node --check scripts/python/project_health_knowledge.js` 与 `git diff --check` 通过。
- 浏览器验证 115、24 的默认折叠、展开、源码返回及失败/验证入口；检查桌面与窄视口无文本溢出。使用已有服务和浏览器工具，不新增依赖。
