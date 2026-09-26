---
title: '修复 Chapter 3 旧版锚点与语义闭包混用'
type: 'bugfix'
created: '2026-09-27'
status: 'done'
baseline_commit: '67375484466610b75996b73791008d45bf69820b3'
review_loop_iteration: 0
context:
  - 'C:/buildgame/newrouge/docs/adr/ADR-0038-semantic-delivery-topology.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 1,256 个有效交付 Requirement 已写入真实任务，但两个旧版 P0/P1 兼容锚点同时出现在 `requirement_ids` 和 `semantic_refs`，被当前语义闭包当作未知 Requirement，导致报告阻断和知识库工作区拓扑不能推进。

**Approach:** 保留 `INT-0500`、`INT-0501` 的任务身份、验收与旧版锚点，在当前语义映射中明确保持空 `semantic_refs`；让旧版包装审计通过其独立的显式锚点归属确认覆盖，不以旧版 ID 冒充当前语义 Requirement。

## Boundaries & Constraints

**Always:** 保留现有工作区改动、501 个生成任务及其 Taskmaster 映射；先做失败回归测试；验证 1,256/1,256 当前 Requirement 均有真实任务或已确认非任务汇、未知语义引用为零、三联验证通过；工作区刷新按 Chapter 3 注册入口执行。

**Ask First:** 若修复需要改变两个兼容任务的验收、优先级、状态，或把它们归入新的当前语义 Requirement，先请用户决策。

**Never:** 不删除这两个兼容任务，不用关键词推断语义归属，不改 Godot 游戏运行时代码，不把脏工作区发布为 Main 知识事实。

## I/O & Edge-Case Matrix

| 场景 | 输入 / 状态 | 预期结果 | 错误处理 |
|------|-------------|----------|----------|
| 当前语义覆盖 | 1,256 个有效 Requirement 与任务视图 | 1,256 个均有真实归属 | 缺失或未知引用阻断 |
| 旧版包装 | 有效旧锚点只在兼容任务 `requirement_ids` 中 | P0/P1 包装覆盖，语义引用仍为空 | 未显式归属的旧锚点继续阻断 |
| 三联重建 | 显式空 `semantic_refs` 的兼容候选 | 不回填旧 `requirement_ids` 到 `semantic_refs` | 结构错误阻断 |

</frozen-after-approval>

## Code Map

- `scripts/python/audit_task_candidate_coverage.py`：`audit_semantic` 当前旧包装只从语义覆盖块推断；`audit_persisted_semantic_coverage` 读取任务视图。
- `scripts/python/compile_task_triplet.py`：`normalize_task` 使用 `or`，会把显式空的 `semantic_refs` 回退到 `requirement_ids`。
- `scripts/python/validate_semantic_conservation.py`：闭包以 `semantic_refs` 为主，显式空列表不会误读兼容锚点。
- `scripts/python/tests/test_chapter3_semantic_conservation.py`：现有覆盖审计、持久化语义映射及三联回归测试位置。
- `logs/ci/task-generation/task-candidates.kpi-advisory.v2.json`：兼容候选 `INT-0500`、`INT-0501`；需只删除其旧锚点语义声明。
- `.taskmaster/tasks/tasks_back.json`：两个已持久化兼容任务；`tasks.json` 为导出视图，必须通过构建脚本重建。
- `logs/ci/task-generation/semantic-requirements.kpi-advisory.v1.json`：已审查的 1,256 个当前 Requirement；不修改。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/python/tests/test_chapter3_semantic_conservation.py`：先写兼容锚点与空语义引用的失败测试。
- [x] `scripts/python/audit_task_candidate_coverage.py`、`scripts/python/compile_task_triplet.py`：分别修正旧版包装覆盖和显式空引用的保留。
- [x] `logs/ci/task-generation/task-candidates.kpi-advisory.v2.json`、`.taskmaster/tasks/tasks_back.json`：仅修正两个兼容任务的 `semantic_refs`；保留 `requirement_ids` 与生命周期字段。
- [x] `.taskmaster/tasks/tasks.json`：经权威任务视图重建，随后重跑闭包、覆盖、三联与工作区知识刷新。

**Acceptance Criteria:**
- Given 现有 1,256 个有效交付 Requirement，when 校验持久化任务视图，then 全部归属且没有未知语义引用。
- Given 两个旧版兼容任务，when 重建三联并运行旧版包装审计，then P0/P1 显式锚点被覆盖且不会进入当前语义边。
- Given 校验全绿，when 运行 Chapter 3 工作区刷新，then Latest Successful 可推进而 Main 发布仍延后。

## Spec Change Log

## Verification

**Commands:**
- `py -3 -m unittest scripts.python.tests.test_chapter3_semantic_conservation`：新增测试先红后绿。
- `py -3 scripts/python/validate_semantic_conservation.py --stage closure --ledger logs/ci/task-generation/source-blocks.kpi-advisory.v1.json --candidates logs/ci/task-generation/task-candidates.kpi-advisory.v2.json --semantics logs/ci/task-generation/semantic-requirements.kpi-advisory.v1.json --out logs/ci/task-generation/semantic-conservation-kpi-advisory-closure.json`：阻断数为零。
- `py -3 scripts/python/audit_task_candidate_coverage.py --semantics logs/ci/task-generation/semantic-requirements.kpi-advisory.v1.json --candidates logs/ci/task-generation/task-candidates.kpi-advisory.v2.json`：当前语义与旧版包装均通过。
- `py -3 scripts/python/attest_chapter3_triplet_baseline.py`：绑定当前三联文件哈希并通过。

## Suggested Review Order

**语义边界**

- 保留显式空语义引用，避免旧版锚点污染当前闭包。
  [`compile_task_triplet.py:92`](../../scripts/python/compile_task_triplet.py#L92)

- 旧版 P0/P1 包装通过兼容字段或 Source Block 桥接，不伪造语义边。
  [`audit_task_candidate_coverage.py:207`](../../scripts/python/audit_task_candidate_coverage.py#L207)

**回归验证**

- 测试覆盖显式空引用、兼容锚点和 Source Block 桥接三种路径。
  [`test_chapter3_semantic_conservation.py:38`](../../scripts/python/tests/test_chapter3_semantic_conservation.py#L38)
