---
title: '项目健康知识库行动型搜索'
type: 'feature'
created: '2026-09-11'
status: 'done'
baseline_commit: '85c3d7bbc0f9bbe6d06ba725fd3851305a4d6f9c'
review_loop_iteration: 0
context: ['C:/buildgame/newrouge/AGENTS.md', 'C:/buildgame/newrouge/docs/agents/13-rag-sources-and-session-ssot.md']
---

<frozen-after-approval reason="human-owned intent - do not modify unless human renegotiates">

## Intent

**Problem:** 当前知识库查询以前排文档和海量 Impact 候选为主，不能直接回答用户应修改哪个任务、配置、读取代码和测试；低相关关系扩展还会掩盖真正入口。

**Approach:** 在既有确定性扫描和资源关联之上生成按任务、配置、代码、测试分组的行动型结果，按直接命中和证据强度排序并控制噪声；保留原始知识和 Impact 数据供深入查看。

## Boundaries & Constraints

**Always:** 结果绑定扫描 revision；使用通用 token、任务三联和资源证据链，不为特定查询写死答案；优先直接标题/路径命中、已确认任务资源关联、读取代码和直接测试；保持响应向后兼容；代码、测试和页面文本使用英文。

**Ask First:** 改变正式 KCP/Impact handoff 门禁；扩大扫描来源；引入外部模型或服务。

**Never:** 修改任务文件或游戏业务源文件；把推断关系伪装成已确认关系；因搜索词未命中而生成不存在的配置、代码或测试；提交或推送。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Action query | `Warrior starter deck` | 前排包含相关任务、deck 配置、读取服务和直接测试 | 无对应分组时返回空数组，不伪造 |
| Exact path | `Game.Core/Data/m1-warrior-starting-deck.json` | 文件置顶，并串联相关任务、读取代码和测试 | 路径不在扫描源时保持普通探索结果 |
| Domain query | 奖励或存档语义 | 结果聚焦对应领域，避免被卡组或泛化 ADR 污染 | 弱关系降权并限制展示数量 |
| Language mismatch | 中文词但无配置别名 | 返回明确的低命中结果和已执行查询 | 不做隐式机器翻译 |
| Stale snapshot | 扫描 revision 不等于当前 HEAD | 响应明确标记 snapshot stale 和两个 revision | 不把旧结果陈述为当前工作区事实 |

</frozen-after-approval>

## Code Map

- `scripts/python/project_health_knowledge.py:287` -- `query` 当前聚合 catalog、GDD 和 Impact；在此接入行动型分组、排序、截断元数据和 revision 新鲜度。
- `scripts/python/_project_health_navigation.py` -- 已有任务级配置、reader、场景、素材和测试证据构造逻辑；搜索应复用输出语义而非另造关系规则。
- `docs/knowledge/generated/task-resource-links.json` -- Chapter 6 生成的任务资源关联，包含 task_id 与 catalog entry 回链。
- `docs/knowledge/catalog/knowledge-catalog.json` -- 项目资源功能、调参、影响与证据的结构化来源。
- `.taskmaster/tasks/tasks.json` 与两个视图文件 -- 任务标识、标题和测试引用的权威来源；本次只读。
- `scripts/python/project_health_knowledge.js:291` -- 查询 UI 当前只展示 knowledge、GDD 和 Impact；增加清晰的任务/配置/代码/测试入口及过期提示。
- `scripts/python/project_health_knowledge.html` -- 搜索结果分区容器，保持现有页面布局并避免原始 JSON 成为主要答案。
- `scripts/sc/tests/test_project_health_knowledge.py` -- 现有扫描、查询与任务详情回归入口；先增加失败测试覆盖排序、证据链、无命中和 stale 状态。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/sc/tests/test_project_health_knowledge.py` -- 先添加行动型搜索契约与排序失败测试，固定通用行为和边界。
- [x] `scripts/python/project_health_knowledge.py` -- 聚合任务及导航证据，输出 `actionable_results`、截断统计和快照新鲜度。
- [x] `scripts/python/project_health_knowledge.js`、`scripts/python/project_health_knowledge.html`、样式文件 -- 按任务、配置、代码、测试呈现行动入口，弱结果退居其次。
- [x] 重新扫描并执行代表性查询 -- 保存查询证据，评估前五命中、任务编号、证据链、噪声和领域隔离。

**Acceptance Criteria:**
- Given 当前 main 快照，when 搜索 `Warrior starter deck`，then 前五行动入口包含任务 24 或 95、`m1-warrior-starting-deck.json`、读取服务及相关测试。
- Given 奖励和存档两类查询，when 查看行动结果，then 各自优先相关任务与修改入口，且卡组结果不占据前排。
- Given 精确配置路径，when 查询，then 该路径为首要配置入口，并展示可追溯的任务、reader 和测试关系。
- Given 过期快照，when 查询，then API 和页面均明确警告，不影响探索但不误称当前事实。
- Given 既有调用方，when 读取旧字段，then `knowledge`、`impact_targets` 和正式 handoff 语义保持可用且未放宽。

## Spec Change Log

## Design Notes

行动型结果是对已有证据的确定性投影，不是 RAG 回答生成。排序强度依次为精确任务/路径命中、已确认任务资源链、直接 reader/test、设计文档、关系扩展和泛化 Impact。每组返回总数与截断数量，防止候选规模被隐藏。

## Verification

**Commands:**
- `py -3 -m unittest scripts.sc.tests.test_project_health_knowledge -v` -- 预期全部通过。
- `node --check scripts/python/project_health_knowledge.js` -- 预期无语法错误。
- `py -3 scripts/python/project_health_knowledge.py scan --repo-root .` -- 预期快照 revision 与本地 main 一致。
- 对 `Warrior starter deck`、`Reward card selection`、`save resume determinism`、`战士初始卡组` 和精确配置路径执行查询 -- 预期符合验收标准并生成 `logs/**` 证据。
- `git diff --check` -- 预期无空白错误。

## Suggested Review Order

**Search aggregation**

- ����ѯ����������ֲ��ϲ����
  [`project_health_knowledge.py:343`](../../scripts/python/project_health_knowledge.py#L343)

- ����ж�������������ʶ�
  [`project_health_knowledge.py:482`](../../scripts/python/project_health_knowledge.py#L482)

**Evidence navigation**

- �������񵼺�֤����
  [`_project_health_navigation.py:1`](../../scripts/python/_project_health_navigation.py#L1)

**User interface**

- �����ж��������ھ���
  [`project_health_knowledge.js:291`](../../scripts/python/project_health_knowledge.js#L291)

- �ṩ����������
  [`project_health_knowledge.html:19`](../../scripts/python/project_health_knowledge.html#L19)

**Verification**

- �������򡢱����Ϳ��ձ߽�
  [`test_project_health_knowledge.py:643`](../../scripts/sc/tests/test_project_health_knowledge.py#L643)
