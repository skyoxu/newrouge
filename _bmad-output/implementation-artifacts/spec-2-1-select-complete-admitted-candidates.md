---
title: 'Story 2.1：只评选完整的准入候选集合'
type: 'feature'
created: '2026-10-14'
status: 'draft'
baseline_commit: '905db329a1b738d2ab4196f71e87a0ebfbe58710'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/epics.md'
  - '{project-root}/scripts/python/plan_mvg.py'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 当前代码仍是三条候选各自处理全部 Capability 后再比较，尚未实现逐 Capability 的三候选评选。

**Approach:** 将评选放在当前 Capability 的三个增量候选全部准入之后，选定结果作为下一 Capability 的累计输入。不足时保持累计基线不变，写入可恢复的阻断原因和候选清单。

## Boundaries & Constraints

**Always:** 只有当前 Capability 的三个独立增量候选全部通过机器与语义准入后才能进入 selection；已接受累计基线只作为只读 seed，不得成为第四候选或 fallback；阻断状态和证据必须落盘。

**Ask First:** 若未来需要允许少于三个候选评选，必须先修改 Epic 2 规格和对应审计口径。

**Never:** 不降低现有准入校验，不把失败候选作为评选输入，不修改 Capability、Requirement、任务三联、GDD 或正式 MVG manifest。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|----------------------------|----------------|
| COMPLETE_SET | 三个候选均 admitted | 继续构造匿名 selection 输入 | N/A |
| INCOMPLETE_SET | 一个或多个候选未 admitted | 不创建可评选集合，累计基线不变 | `selection_blocked_insufficient_admitted_candidates`，保存 `run.json` 与 `model-execution.json` |

</frozen-after-approval>

## Code Map

- `scripts/python/plan_mvg.py` -- 生成候选后汇总准入状态，并在 selection 前执行集合门禁。
- `scripts/python/tests/test_mvg_planning_contract.py` -- 规划契约和状态机回归测试。
- `scripts/python/_mvg_capability_generation.py` -- 当前逐 Capability append worker，需提供单项生成/准入接口给 coordinator。

## Tasks & Acceptance

**Execution:**
- [ ] 完成逐 Capability coordinator 与单项 worker 设计，明确和 Story 2.2/2.3 checkpoint 的边界。
- [ ] `scripts/python/plan_mvg.py` -- 每项恰好三个 admitted increments 后评选，累计基线不参与竞争。
- [ ] `scripts/python/tests/test_mvg_planning_contract.py` -- 验证每项三候选、只读 seed、不足阻断与下一项消费选定结果。

**Acceptance Criteria:**
- Given 少于三个 admitted 候选，when 生成阶段准备进入 selection，then 状态为 blocked，原因为 `selection_blocked_insufficient_admitted_candidates`，且不推进累计基线。
- Given 当前 Capability 的三个 admitted increments，when selection 构造输入，then 只评选三个候选，已接受累计基线不作为第四候选或缺失候选补位。

## Implementation Status

本轮先修复现有整批流程的阻断回执、恢复状态与输入兼容性，不能据此认定 Story 2.1 已完成。本规格纠正了草案中“incumbent 可作为第四比较对象”的错误表述，以已批准 Epic 2 为准。逐 Capability 评选迁移尚未实施；不宣称完成全部 Epic 或页面全流程。

## Verification

**Commands:**
- `py -3 -m unittest scripts.python.tests.test_mvg_planning_contract.MvgPlanningContractTests.test_selection_blocks_explicitly_when_three_admitted_candidates_are_unavailable` -- expected: OK
- `py -3 -m py_compile scripts/python/plan_mvg.py` -- expected: SUCCESS
- `git diff --check` -- expected: SUCCESS
