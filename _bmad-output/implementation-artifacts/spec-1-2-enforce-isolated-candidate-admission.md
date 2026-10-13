---
title: 'Story 1.2：强制隔离候选准入'
type: feature
created: '2026-10-14'
status: done
baseline_commit: 20901815ebce3cc5a20075beb31af0384b5c1817
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-1-1-freeze-capability-input-envelope.md'
---

## Intent

为冻结的 Capability 建立三个相互隔离的候选槽位，并确保只有通过确定性机器检查和独立语义准入的候选才能进入评选。

## Boundaries & Constraints

- 每个候选使用独立 lineage、workspace、调用回执和输入副本；候选不得读取其他候选的 prompt、proposal、finding 或未准入产物。
- 机器检查先于语义准入，覆盖 schema、身份、ID、selector、引用域、Requirement 范围、flow/test 绑定、handoff 和累计 delta。
- 机器拒绝不伪装成语义 verdict，也不能进入评选；准入证明和 execution receipt 必须与 proposal hash 绑定。
- 不修改 GDD、Requirement、Taskmaster 三联、Capability、游戏代码或 Godot 资源。

## Verification

- `py -3 -m unittest scripts.python.tests.test_mvg_planning_contract -v`：133/133 通过。
- 覆盖三候选独立 workspace、跨候选污染阻断、准入前机器 gate、语义准入 receipt、selector 输入身份、候选退役恢复、execution failure 分类和 admitted-only selection。
- `py -3 -m py_compile scripts/python/plan_mvg.py scripts/python/_mvg_planning_review.py`：通过。
- `git diff --check`：通过。

## Evidence Map

- 候选状态机与准入 gate：`scripts/python/plan_mvg.py`
- 候选生成与独立调用：`scripts/python/_mvg_capability_generation.py`
- 语义 review 与 execution receipt：`scripts/python/_mvg_planning_review.py`
- 状态机回归：`scripts/python/tests/test_mvg_planning_contract.py`
- 页面恢复筛选：`scripts/python/_project_health_planning.py`

## Result

Story 1.2 的验收条件由当前实现和 133 项回归共同证明，无需新增代码补丁。候选只有在无硬问题且证据完整时才进入评选；候选不足时保持可恢复阻断，不伪造成功。

## Suggested Review Order

**准入状态机**

- 从候选 gate 入口检查硬问题集合和 admitted-only 边界
  [`plan_mvg.py:407`](../../scripts/python/plan_mvg.py#L407)

- 查看语义 gate 如何绑定 proposal、review 和 execution receipt
  [`plan_mvg.py:485`](../../scripts/python/plan_mvg.py#L485)

**验证**

- 查看完整状态机回归集合
  [`test_mvg_planning_contract.py:1`](../../scripts/python/tests/test_mvg_planning_contract.py#L1)
