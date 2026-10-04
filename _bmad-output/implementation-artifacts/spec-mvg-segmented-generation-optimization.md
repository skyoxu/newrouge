---
title: 'MVG 分段生成与隔离调用优化'
type: 'refactor'
created: '2026-10-04'
status: 'draft'
review_loop_iteration: 0
context:
  - 'scripts/python/plan_mvg.py'
  - 'scripts/sc/_llm_backend.py'
  - 'docs/workflows/mvg-integration-acceptance.md'
  - '.agents/skills/plan-mvg/SKILL.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** MVG 的单次全量 LLM 请求会因读取过大的准备输入、复杂的全量旅程推理或 Windows 子进程超时而失败；失败重试还会重复支付相同的上下文成本。该问题只影响 MVG 规划生成，不应修改 Capability、任务三联、GDD 或正式 MVG manifest。

**Approach:** 将生成拆为身份绑定的 flow、Requirement coverage、entrypoint 和 test 分段。每个分段使用独立的空 LLM sandbox，只接收经本地裁剪的已准备证据；本地代码仅负责并发编排、身份校验、去重合并和不可丢失骨架保留。flow 语义、handoff、测试选择仍由 LLM 决定，随后继续经过现有 deterministic validation、独立 review 和 apply 门禁。

## Boundaries & Constraints

**Always:** 使用准备阶段的固定证据快照；使用环境默认模型和 reasoning 配置；每个分段校验 schema、analysis identity 与 section；限制并发并在 Windows 超时清理完整进程树；保留 coverage/entrypoint skeleton；所有实验 run 写入 `logs/**`；代码、测试、日志文本使用英文，文档使用中文。

**Ask First:** 如需改变 Capability 版本、Requirement 归属、任务状态、正式 manifest、模型后端或 review/apply 策略，必须停止并请求确认。

**Never:** 不使用机器生成替代 Capability；不把分段结果直接写入正式 manifest；不使用上次失败 run 的模型缓存；不让模型扫描完整 `analysis-input`；不把 planned/runtime 验证混为一谈；不为通过验证而发明仓库路径、契约或任务。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| HAPPY_PATH | formal-ready run、固定 Capability 与 127 个任务范围 | 分段输出经 identity 校验，本地合并出 proposal，进入现有 validation | 仅在完整 proposal 通过 deterministic validation 后标记 generated |
| SEGMENT_TIMEOUT | 单个 flow/coverage/test 分段超时 | 终止该分段完整子进程树，不污染其他分段结果 | 保留 attempt receipt，run 进入 execution-blocked，不伪造 proposal |
| INVALID_SEGMENT | JSON、section 或 identity 不匹配 | 拒绝该分段 | 按现有 attempt 预算记录失败，不合并无效数据 |
| PARTIAL_MODEL_OUTPUT | 某段缺少部分 rows | 不删除 skeleton 或已有有效 rows | 交由最终 deterministic validation 报出缺口 |

</frozen-after-approval>

## Code Map

- `scripts/python/plan_mvg.py` -- 分段 prompt、Capability slice、sandbox、并发执行、身份校验与 skeleton 合并。
- `scripts/sc/_llm_backend.py` -- Codex CLI ephemeral 调用、Windows 子进程树超时清理、环境默认模型边界。
- `scripts/python/tests/test_mvg_planning_contract.py` -- 分段 schema、范围分区、合并与 proposal 合同回归。
- `scripts/sc/tests/test_llm_backend.py` -- 后端调用、默认配置和 Windows timeout 清理回归。
- `.agents/skills/plan-mvg/SKILL.md`、`workflow.md`、`docs/workflows/mvg-integration-acceptance.md` -- MVG 分段生成的操作约束与不替代 review/apply 的边界。
- `logs/ci/mvg-planning/<run-id>/` -- 仅作为隔离验证证据；不作为正式基线输入。

## Tasks & Acceptance

**Execution:**
- [ ] `scripts/python/plan_mvg.py` -- 完成分段、空 sandbox、有限并发与失败保留 -- 降低单次上下文和重复重试成本。
- [ ] `scripts/python/tests/test_mvg_planning_contract.py` -- 覆盖每个 active Requirement 恰好分配一次、分段任务边界、identity 拒绝、skeleton 不丢失和 fake-runner 并发编排 -- 防止优化破坏语义守恒。
- [ ] `scripts/sc/_llm_backend.py`、`scripts/sc/tests/test_llm_backend.py` -- 保持环境默认模型与进程树清理 -- 防止孤儿 Codex 进程。
- [ ] 运行全新隔离 MVG generate 并只执行 validate -- 确认 proposal 生成成功后再决定是否 review。

**Acceptance Criteria:**
- Given full prepared evidence, when segmented generation runs, then no model invocation receives the complete `analysis-input` directory as its working context.
- Given a valid segment response, when it is merged, then its identity and section are verified and existing skeleton rows remain present.
- Given timeout/invalid JSON/identity mismatch, when the segment completes, then no invalid output is merged and the run records a bounded failure.
- Given a successful generate, when deterministic validation runs, then all active delivery Requirements and flow-task entrypoints remain accounted for; formal MVG apply is not executed by this optimization test.

## Design Notes

Flow segmentation uses reviewed Capability membership only as an evidence partition; it does not force one flow per Capability. Coverage, entrypoint and test segments consume stable flow IDs after the flow barrier. Independent segment calls may run with a small bounded concurrency, while later sections wait for flow IDs.

## Verification

**Commands:**
- `py.exe -3 -m unittest scripts.python.tests.test_mvg_planning_contract scripts.sc.tests.test_llm_backend` -- expected: all tests pass.
- `py.exe -3 -m py_compile scripts/python/plan_mvg.py` -- expected: no syntax errors.
- `py.exe -3 scripts/python/plan_mvg.py prepare ...` with complete current round task scope -- expected: `formal_ready=true`.
- `py.exe -3 scripts/python/plan_mvg.py generate --run-id <fresh-id> --llm-backend codex-cli` -- expected: either generated proposal or bounded execution-blocked evidence; no formal manifest/task/GDD mutation.
- `git diff --check` -- expected: no whitespace errors.
