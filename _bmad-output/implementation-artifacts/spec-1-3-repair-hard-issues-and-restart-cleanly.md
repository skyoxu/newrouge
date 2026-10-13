---
title: 'Story 1.3：修复硬问题并干净重启候选 lineage'
type: feature
created: '2026-10-14'
status: done
baseline_commit: 2478d730
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-1-2-enforce-isolated-candidate-admission.md'
---

## Intent

让候选硬问题按稳定身份逐项修复，并在单个问题三次修复仍失败时退役当前 lineage、创建完全干净的 replacement，直到得到三个可准入候选或遇到有界阻断。

## Boundaries & Constraints

- 每个稳定硬问题最多接受三次局部修复；每次修复绑定当前 proposal hash、问题身份、目标对象和依赖范围。
- 修复后重新执行机器检查，再按未解决问题队列继续；不得删除仍存在的问题或借重排绕过计数。
- replacement 只能读取不可变 prepared envelope 和已接受 predecessor；不得读取退役 proposal、prompt、finding、review、transport 或 workspace。
- runner、输入或预算故障保持原错误类型并持久化可恢复状态；不得将其伪装成语义问题，也不得静默跳过 Capability。

## Verification

- `py -3 -m unittest scripts.python.tests.test_mvg_planning_contract -q`：133/133 通过。
- `py -3 -m unittest scripts.python.tests.test_mvg_capability_append -q`：45/45 通过。
- 关键回归覆盖：
  - `test_admission_retires_after_three_failed_repairs_and_replacement_is_clean`
  - `test_candidate_has_unfinished_repair_stops_at_three_attempts`
  - `test_repeated_repair_execution_failure_still_restarts_after_three_attempts`
  - `test_three_repairs_then_clean_restart_same_capability`
  - `test_repair_protects_another_valid_mapping_in_same_capability`
  - `test_candidate_runner_failure_uses_clean_retry_without_previous_seed`
- `py -3 -m py_compile scripts/python/plan_mvg.py scripts/python/_mvg_capability_generation.py scripts/python/_mvg_planning_review.py scripts/python/_project_health_planning.py`：通过。
- `git diff --check`：通过。

## Evidence Map

- issue 队列、稳定身份和修复预算：`scripts/python/plan_mvg.py`
- 局部修复输入与候选 lineage 调用：`scripts/python/_mvg_capability_generation.py`
- 机器/语义准入问题分类：`scripts/python/_mvg_planning_review.py`
- 状态机和 clean replacement 回归：`scripts/python/tests/test_mvg_planning_contract.py`
- 追加式三次修复与上下文隔离回归：`scripts/python/tests/test_mvg_capability_append.py`

## Result

Story 1.3 的验收条件由当前状态机实现和 178 项定向回归共同证明。修复预算是每个稳定问题三次，lineage 耗尽后才创建 clean replacement；未达到三个 admitted 候选时不会进入评选。

## Suggested Review Order

**修复与 replacement**

- 查看稳定问题身份、计数和有序推进
  [`plan_mvg.py:178`](../../scripts/python/plan_mvg.py#L178)

- 查看退役 lineage 如何生成不可污染的 replacement
  [`plan_mvg.py:285`](../../scripts/python/plan_mvg.py#L285)

- 查看追加式生成如何隔离 repair seed 与 clean retry
  [`_mvg_capability_generation.py:417`](../../scripts/python/_mvg_capability_generation.py#L417)

**验证**

- 查看状态机边界回归
  [`test_mvg_planning_contract.py:1`](../../scripts/python/tests/test_mvg_planning_contract.py#L1)

- 查看 Capability 追加修复回归
  [`test_mvg_capability_append.py:1`](../../scripts/python/tests/test_mvg_capability_append.py#L1)
