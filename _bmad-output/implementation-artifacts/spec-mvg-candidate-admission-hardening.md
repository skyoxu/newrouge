---
title: 'MVG 候选准入状态机加固'
type: 'bugfix'
created: '2026-10-09'
status: 'in-review'
baseline_commit: '4f247af77401c92e1d5186362223392f77ea7f1f'
review_loop_iteration: 0
context:
  - 'C:/buildgame/newrouge/AGENTS.md'
  - 'C:/buildgame/newrouge/.agents/skills/plan-mvg/SKILL.md'
  - 'C:/buildgame/newrouge/docs/workflows/mvg-integration-acceptance.md'
---

<frozen-after-approval reason="用户已批准完整修复审查发现的 P1/P2 问题">

## Intent

**Problem:** MVG 候选准入已能阻止明显的硬问题，但恢复、中断、候选文件漂移和 replacement 预算仍可能破坏准入不变量。

**Approach:** 加固 issue 身份、全局预算、退役事件恢复、selector 前证明校验、publication execution 校验和页面候选复用；所有失败都保留可审计状态并 fail closed。

## Boundaries & Constraints

**Always:** 三个独立候选必须先 admitted；每个硬问题最多三次修复；replacement 使用全新 lineage；selector 只接收证明完整且 hash 一致的候选；页面恢复只能复用本地当前有效产物；不修改任务、GDD、Capability 或游戏代码。

**Ask First:** 无。

**Never:** 不放宽 deterministic/semantic gate，不把 runner 错误转成语义问题，不复用退役上下文，不恢复无 admission proof 的旧 selected 结果。

## I/O & Edge-Case Matrix

| Scenario | Expected behavior |
|---|---|
| Issue 顺序变化但旧 issue 仍存在 | 不得删除旧 issue，不得提前进入下一 issue |
| candidate-retired 已落盘后进程中断 | 恢复为退役状态并创建 clean replacement |
| selector.json 已落盘但 run.json 未更新 | 校验 hash 后直接恢复 selector 结果 |
| replacement 持续失败 | 到达全局 replacement budget 后 fail closed |
| admitted proposal/proof 漂移 | selector 前阻断，不调用 selector |
| selected run 缺 proof | review/generate 快速恢复阻断，不走旧旁路 |
| publication 缺 execution receipt | 不恢复为准入成功，重新执行或阻断 |

</frozen-after-approval>

## Code Map

- `scripts/python/plan_mvg.py` -- issue 队列、candidate lineage、replacement、selector、准入 publication 和 selected review。
- `scripts/python/_project_health_planning.py` -- 页面 job 的候选复用筛选。
- `scripts/python/_mvg_planning_review.py` -- execution receipt 和 runner identity 校验。
- `scripts/python/tests/test_mvg_planning_contract.py` -- 状态机、准入证明和 selector 恢复回归。
- `scripts/python/tests/test_planning_audit_repair.py` -- publication、review 和失败预算回归。
- `scripts/python/tests/test_project_health_planning.py` -- 页面候选复用和 proof 过滤回归。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/python/plan_mvg.py` -- 加固恢复、selector、proof、replacement 和错误分类。
- [x] `scripts/python/_project_health_planning.py` -- 页面复用只接受 admitted 且 proof/hash 完整的候选。
- [x] `scripts/python/tests/*.py` -- 增加 issue reorder、retired recovery、selector recovery、artifact drift 和 publication receipt 回归。
- [x] `workflow.md` 与 MVG owning 文档 -- 记录全局 stop-loss、proof fail-closed 和 legacy 兼容边界。

**Acceptance Criteria:**
- Given issue 顺序发生变化，when 旧 issue 仍在输出中，then 旧 issue 继续计数且不能被删除。
- Given 三候选或 selector 在持久化边界中断，when 恢复，then 只复用 hash 校验通过的 durable artifact。
- Given replacement 持续失败，when 达到全局预算，then 工作流有界阻断并保存 stop reason。
- Given admission proof、execution receipt 或 proposal hash 缺失/漂移，when selector 或 review 执行，then fail closed。

## Verification

**Commands:**
- `py -3 -m py_compile scripts/python/plan_mvg.py scripts/python/_project_health_planning.py`
- `py -3 -m unittest scripts.python.tests.test_mvg_planning_contract scripts.python.tests.test_planning_audit_repair scripts.python.tests.test_project_health_planning -q`
- `git diff --check`

## Design Notes

旧 `segmented=False` 仅保留给已有 fixture 的兼容测试；页面和 CLI 正式入口继续使用 segmented candidate admission。若后续要删除兼容路径，应另行迁移测试 fixture。
