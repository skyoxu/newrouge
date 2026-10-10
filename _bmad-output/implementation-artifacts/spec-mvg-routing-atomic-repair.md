---
title: MVG 路由与原子修复
type: bugfix
created: '2026-10-10'
status: in-review
baseline_commit: 334522347358a1b209f9b486b4d67156aa94569f
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/.agents/skills/plan-mvg/SKILL.md'
---

<frozen-after-approval reason="用户已批准复验后的方案及定向测试">

## Intent

修复当前 MVG 分段生成的需求范围扩散、反复污染和关联结构失配。当前 Capability 是唯一 Capability 输入；三个候选独立生成整体路由，机器强制结构和范围，LLM 判断语义，准入后才评选。

## Boundaries & Constraints

保留 `flow.requirement_ids` 的覆盖含义；共享上下文不能自动声明覆盖。旧 flow/test 的累计回归行为保留，元数据变更仍需来源说明与独立审查。缺少非运行时验证依据时明确报告缺口，不创建 sink、伪造延期或修改上游。

只修改规划实现、定向测试及 owning 文档；不改任务三联、Requirement、Capability、游戏代码。只测试本地确定性逻辑与 schema-aware 模型替身，不调用真实 LLM、不启动完整工作流、不提交、不重启服务。

## I/O & Edge-Case Matrix

| 输入 | 期望 |
| --- | --- |
| 两个旧 flow 共享 Capability | 按逐需求证据限定候选关联，不能把整组给两个 flow；LLM 先产生候选级整体覆盖路由 |
| 路由遗漏、重复、越界、错误 flow | CLI schema 和本地门禁拒绝；三个候选不能共享生成路由或失败上下文 |
| 旧 flow 元数据缺失 | 显式补映射、提供 change review；缺失不能解释为所有需求均可认领 |
| 最终基线恢复 task/handoff/test | coverage/entrypoint/test 消费恢复后的同一 flow，而非恢复前对象 |
| 修复目标 A，仍有原问题 B | 接纳解决 A 且不引入新确定性问题的受限补丁；无需 B 同时解决 |
| 修复修改无关行或破坏既有映射 | 拒绝并保留旧 proposal 与有效分段，计入 A 的三次修复机会 |
| 三次失败或候选退役 | 次数不因问题顺序变化而重置；新上下文即时补位，保留其他槽位 |
| schema/routing 内部重试和调用预算 | 调用统一落盘，64 上限不再被开放式 overflow 绕过；执行预算不足明确报告而非伪称三次语义失败 |

</frozen-after-approval>

## Code Map

- `scripts/python/plan_mvg.py`：`invoke_segmented` 在 Capability scope 与旧 flow 相交后复制整组 requirements；修复重跑整个 batch；`preserve_frozen_manifest_baseline` 后期恢复结构；`generate` 等待全部初始结果再串行补位；调用 counter 的 overflow 可达 150 次。
- `scripts/python/_mvg_planning_review.py`：覆盖唯一性及独立语义会计门禁；保留，不以删门禁换成功。
- `scripts/python/update_mvg_baseline.py`：累计 delta 来源约束；保留。
- `scripts/python/tests/test_mvg_segment_scope.py`：真实 dispatcher、CLI schema 验证和模型替身，扩充 shared Capability、关联恢复与拒绝补丁场景。
- `scripts/python/tests/test_mvg_planning_contract.py`：稳定 issue、三次退役、预算、隔离与恢复；适配修复语义。
- `docs/workflows/mvg-integration-acceptance.md`、`docs/workflows/project-health-knowledge.md`、`workflow.md` 5.4、`.agents/skills/plan-mvg/SKILL.md`：同步上述实际执行边界。
- 只读证据：`C:/Users/weiruan/AppData/Local/Temp/nrp/d0606abb303a/logs/ci/mvg-planning/planning-d0606abb303a4bdca1b71322e7a44bad`，现已手动停止。测试 fixture 不得依赖此目录存在。
- 约束：ADR-0005（Accepted）、现有 run-protocol；日志写 `logs/ci/2026-10-10/mvg-routing-repair/`。

## Tasks & Acceptance

- [ ] 先建立能失败的 self-contained 定向测试并保存 RED 证据。
- [ ] 新增候选内整体路由阶段与严格输出 schema；路由产生于 LLM，机器不能按任务数生成结论；必要时支持受限路由修复。
- [ ] 收紧旧 flow 证据到逐 Requirement，路由绑定各分段 schema；允许上下文共享，不允许覆盖归属扩散。
- [ ] 在生成关联 sections 前完成最终基线投影，禁止后期静默改写它们的 flow 输入。
- [ ] 使用当前 proposal hash 绑定受限修复；按行/字段约束输出和原子接纳，保留未受影响有效映射；失败补丁不得变成后续 seed/cache。
- [ ] 修复次数覆盖内部 routing 重试；计数持久化；硬预算与说明一致；退役槽位立即独立补位，替身验证无失败上下文继承。
- [ ] 同步 owning 文档、运行定向回归及静态检查，标记实际验证边界。

给定任意候选输入，整体路由先完整且范围正确才能展开分段。给定多个既有问题，修复只改变当前问题的明确依赖域，成功减少该问题并不污染已有效行。给定旧结构恢复，所有关联证据针对最终结构验证。给定无合法验证来源的 NFR，报告来源缺口而非伪造运行覆盖。给定三个未准入结果，选择器不能运行。

## Verification

`py -3 -m unittest discover -s scripts/python/tests -p test_mvg_segment_scope.py -v`

`py -3 -m unittest discover -s scripts/python/tests -p test_mvg_planning_contract.py -v`

必要时只运行受影响的 delta/admission 定向文件；不执行整个工作流。保存 RED/GREEN 输出、`py_compile`、`git diff --check` 与审查结果。
