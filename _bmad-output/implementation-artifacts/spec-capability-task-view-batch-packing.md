---
title: 'Capability 任务视图无损分批与 Codex 请求预检'
type: 'bugfix'
created: '2026-10-17'
status: 'done'
baseline_commit: '5ca7103d6d9e0e5919618928131c88083eb94c2e'
review_loop_iteration: 0
context:
  - '.agents/skills/plan-capabilities/SKILL.md'
  - 'docs/workflows/project-health-knowledge.md'
---

<frozen-after-approval reason="延续已授权的 Capability 页面工作流修复">

## Intent

**Problem:** `Generate Capability from local inputs` 的分批模型请求反复携带完整 `tasks_back.json` 与 `tasks_gameplay.json`，导致每个 Codex CLI 请求超过 1,048,576 字符硬限制；当前 token allowance 无法解除该限制，候选重试也无法修复确定性超限。

**Approach:** 以每个 authoritative Requirement batch 为边界，完整分配所有任务视图行到其引用的一个或多个 batch；不删字段、不截断正文。所有 Codex 最终 stdin 请求在任何模型调用前按真实序列化文本检查字符、字节和 token 限制，任一超限即零调用失败。

## Boundaries & Constraints

**Always:** 保持任务视图行及字段完整；关联多个 batch 的行可完整重复；无明确 Requirement 关联的行完整进入首个 batch。校验任务视图覆盖、行数、引用归属和 prepared hash；分批与 synthesis 的精确请求都须先预检。不得耗费真实模型调用来发现尺寸错误。

**Ask First:** 改变 Capability 权威来源、任务语义、token allowance 或 CLI 硬限制。

**Never:** 截断、摘要替代或丢弃任务/Acceptance/test 字段；提高字符上限；重试相同超限请求；调用真实模型验证确定性打包逻辑。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
| --- | --- | --- | --- |
| 跨批次任务 | 一任务引用多个 batch 的 Requirements | 完整原行出现在每个关联 batch，无字段变化 | 覆盖证明不一致则零模型调用失败 |
| 无 Requirement 引用 | 任务视图行无有效关联 | 完整原行进入首个 batch | 仍参与精确请求尺寸预检 |
| CLI 字符上限 | 任一最终 stdin 大于 1,048,576 字符 | 不开始任何模型调用 | 记录确定性 oversized 错误及请求尺寸 |

</frozen-after-approval>

## Code Map

- `scripts/python/_capability_input_integrity.py` -- `validate_batches`, `compact_file_section`, `measure_request`; 增加完整 task-view row 的确定性分配和覆盖证据。
- `scripts/python/openai_isolated_model_runner.py` -- `batched_workspace_parts`, `_run_batched_session`; batch 请求构造和 API 预检。
- `scripts/python/codex_isolated_model_runner.py` -- `_run_batched_codex`, `_run_codex_request`; 所有 CLI stdin 的精确限制检查必须先于 executable 启动。
- `scripts/python/copilot_isolated_model_runner.py` -- 共用 batching builder 的调用点，确保既有单 batch/多 batch边界不回归。
- `scripts/python/tests/test_capability_input_integrity.py` -- 当前 fake runner、完整字段和零调用预检测试。
- 失败证据：`%TEMP%/nrp/67895e1fe4de/logs/ci/capability-planning/planning-67895e1fe4de4ede9fc63e36ddc7d896/analysis-input/`；只读，不改写。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/python/_capability_input_integrity.py` 与测试 -- 按关联分配完整 task-view rows；验证跨 batch 重复、孤立行、精确字段保真、遗漏/篡改阻断。
- [x] `scripts/python/openai_isolated_model_runner.py`、`scripts/python/codex_isolated_model_runner.py` 与测试 -- 对每个最终序列化请求预检字符上限、UTF-8 字节、token 与 continuation reserve；保证任一请求超限时整轮模型调用数为零。
- [x] `scripts/python/copilot_isolated_model_runner.py` 与相关回归 -- 验证共用 batch scope 在现有支持范围内保持无损且超限 fail-closed。
- [x] 用保留的失败输入执行离线 preflight；不调用模型，并将请求尺寸、batch 归属和完整性结果写入 `logs/**`。

**Acceptance Criteria:**

- Given 两个关联 batch 和完整任务视图，when 准备请求，then 任务行按显式 Requirement refs 完整复制到相关 batch，所有原字段值、数组顺序和正文均保留且可证明无重无漏（跨 batch 合法重复除外）。
- Given 任一 Codex batch 或 synthesis stdin 超过 CLI 字符上限，when 执行 preflight，then runner 在启动 Codex 或 API 请求前失败，模型调用数为零并记录尺寸。
- Given 所有请求通过 preflight，when fake runner 执行，then 实际送出的请求 hash 与预检 hash 一致。

## Verification

**Commands:**
- `py -3 -m unittest scripts.python.tests.test_capability_input_integrity` -- expected: all targeted cases pass.
- `py -3 -m unittest scripts.python.tests.test_planning_audit_repair` -- expected: relevant planner and preflight regressions pass.
- `py -3 -m py_compile scripts/python/_capability_input_integrity.py scripts/python/openai_isolated_model_runner.py scripts/python/codex_isolated_model_runner.py scripts/python/copilot_isolated_model_runner.py` -- expected: no syntax errors.
- Offline Codex preflight against preserved failed input -- expected: every request is within exact CLI limits or deterministically blocked; `model_invoked=false`.
- `git diff --check` -- expected: no whitespace errors.

## Suggested Review Order

**完整性与分批边界**

- 先验证权威批次覆盖与哈希绑定
  [`_capability_input_integrity.py:37`](../../scripts/python/_capability_input_integrity.py#L37)

- 再检查任务视图按引用完整分配
  [`_capability_input_integrity.py:125`](../../scripts/python/_capability_input_integrity.py#L125)

**模型请求预检**

- 检查结构化 schema 的有界容量计算
  [`_capability_input_integrity.py:249`](../../scripts/python/_capability_input_integrity.py#L249)

- 检查 OpenAI 分批与 synthesis 请求
  [`openai_isolated_model_runner.py:463`](../../scripts/python/openai_isolated_model_runner.py#L463)

- 检查 Codex 全轮零调用预检
  [`codex_isolated_model_runner.py:109`](../../scripts/python/codex_isolated_model_runner.py#L109)

**回归验证**

- 查看完整字段、跨批与超限测试
  [`test_capability_input_integrity.py:136`](../../scripts/python/tests/test_capability_input_integrity.py#L136)
