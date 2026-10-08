---
title: 'MVG 候选准入与清洁补位状态机'
type: 'refactor'
created: '2026-10-08'
status: 'done'
baseline_commit: '4f247af77401c92e1d5186362223392f77ea7f1f'
review_loop_iteration: 1
context:
  - C:/buildgame/newrouge/AGENTS.md
  - C:/buildgame/newrouge/.agents/skills/plan-mvg/SKILL.md
  - C:/buildgame/newrouge/docs/workflows/mvg-integration-acceptance.md
  - C:/buildgame/newrouge/docs/adr/ADR-0037-mvg-integration-evidence.md
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** MVG 当前先评选、后语义审查，导致带硬性问题的候选进入评选，最终评选出候选后又整体阻断；候选失败也没有按规则修复和清洁补位。

**Approach:** 将候选准入、问题修复、候选退役和最终评选拆成强制状态机。每个候选先通过确定性与语义硬门禁；单个硬问题最多修复三次，修复后重新检查下一个问题；同一候选修复耗尽则完整退役，并以全新隔离上下文生成替代候选。只有三个正常候选和可比较的有效 incumbent 准备完成后才进入评分评选。

## Boundaries & Constraints

**Always:**

- 进入 MVG 评选的候选不得有硬性问题；候选未获选只能因为评分排名不是第一。
- 硬问题按顺序处理；同一问题最多三次修复机会，修复后重新运行准入检查。
- 候选退役后，替代候选不得读取退役候选的 proposal、修复提示、评审输出或模型工作区。
- 评选阶段只能比较三个已准入候选和一个有效 incumbent；评选必须选出一个可用 winner。
- 候选、修复、退役、补位、评选的身份和次数必须写入 `logs/**`，不得修改任务、Requirement、Capability 或运行时状态。
- 页面点击仍然创建全新 job；只有显式 CLI/run-id 恢复才能继续同一状态机。

**Ask First:**

- 无。候选修复上限、补位规则和评选入口均由本规格固定。

**Never:**

- 不允许将 blocked 候选复制到评选工作区。
- 不允许用旧候选的上下文作为退役候选的替代生成提示。
- 不允许在评选后用语义审查否决唯一 winner；语义硬门禁必须在评选前完成。
- 不允许通过降低校验、改写来源或复用旧评审结果来制造三个候选。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| 初始候选通过 | 新鲜分析输入，准入无硬问题 | 候选进入 admitted 集合 | 记录准入摘要 |
| 候选有硬问题 | 候选 proposal 和可解析问题列表 | 仅把当前问题交给修复上下文；最多三次 | 每次保留问题、修复输出和复检结果 |
| 修复成功 | 修复后的 proposal | 重新从第一个未解决问题开始检查；全部通过后准入 | 不保留旧问题作为阻断 |
| 修复耗尽 | 同一问题三次仍失败 | 候选退役并清理其评选资格 | 生成全新 replacement round，不读取退役上下文 |
| 候选不足三份 | 一个或多个候选退役 | 持续生成清洁 replacement，直到三个 admitted | 若外部 runner/输入故障，保留可恢复状态并停止，不假装评选 |
| 三个候选就绪 | 三个 admitted 候选和可选有效 incumbent | 只运行一次比较评选并选出 winner | 评选格式错误按选择器预算重试，不把语义硬阻断带入评选 |

</frozen-after-approval>

## Code Map

- `scripts/python/plan_mvg.py` -- MVG 候选生成、确定性验证、选择器入口和状态持久化。
- `scripts/python/_mvg_planning_review.py` -- Requirement/flow 语义审查与硬问题分类。
- `scripts/python/_project_health_planning.py` -- 页面 job 阶段编排；保持页面新 job 与显式恢复边界。
- `scripts/python/tests/test_mvg_planning_contract.py` -- 选择、验证和评审契约回归。
- `scripts/python/tests/test_project_health_planning.py` -- 页面规划 job 与恢复回归。
- `.agents/skills/plan-mvg/SKILL.md` -- MVG owning workflow；同步候选准入与评选边界。
- `docs/workflows/mvg-integration-acceptance.md` -- 人类可读的 MVG 规划和运行边界。

## Tasks & Acceptance

**Execution:**

- [x] `scripts/python/plan_mvg.py` -- 实现逐问题三次修复、候选退役和清洁 replacement，且只有三个 admitted 候选进入选择器。
- [x] `scripts/python/plan_mvg.py` / `scripts/python/_mvg_planning_review.py` -- 将语义硬门禁放到候选准入阶段；评选只消费无硬问题候选。
- [x] `scripts/python/tests/test_mvg_planning_contract.py` -- 覆盖修复上限、退役隔离、三候选准入和评选 winner 约束。
- [x] `.agents/skills/plan-mvg/SKILL.md` -- 记录新的候选状态机和恢复边界。
- [x] `docs/workflows/mvg-integration-acceptance.md` -- 同步页面/CLI 的候选准入与评选说明。

**Acceptance Criteria:**

- Given 候选存在硬性问题，when 生成器运行，then 该候选不会写入选择器输入，问题按顺序最多修复三次。
- Given 修复三次仍失败，when 候选退役，then replacement 使用全新 workspace/context，且其输入不包含退役 proposal、findings 或 prompt。
- Given 一个候选退役，when replacement 成功，then 状态机继续直到存在三个 admitted 候选；不会提前进入评选。
- Given 三个 admitted 候选，when 评选运行，then 每个候选均无硬性问题，未获选记录为排名原因而非阻断原因。
- Given runner/输入故障，when 无法继续，then 状态可恢复且不伪造三个候选或评选成功。

## Design Notes

候选标签 `candidate-1..3` 代表评选槽位，不代表一次不可替换的模型调用。退役轮次保存在该槽位的历史日志中，替代 proposal 只写入该槽位当前有效文件；选择器永远只读取当前有效文件。incumbent 只有通过同一正式准入校验才可以作为 D 参与评选。

## Verification

**Commands:**

- `py -3 -m unittest scripts/python/tests/test_mvg_planning_contract.py -v` -- expected: all MVG planning contract tests pass.
- `py -3 -m unittest scripts/python/tests/test_project_health_planning.py -v` -- expected: all planning job tests pass.
- `py -3 -m py_compile scripts/python/plan_mvg.py scripts/python/_mvg_planning_review.py` -- expected: no syntax errors.
