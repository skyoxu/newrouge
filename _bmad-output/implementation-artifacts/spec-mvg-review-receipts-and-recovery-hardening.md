---
title: 'MVG 审查修补：失败回执与恢复门禁'
type: 'bugfix'
created: '2026-10-14'
status: 'done'
baseline_commit: '905db329a1b738d2ab4196f71e87a0ebfbe58710'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
---

<frozen-after-approval reason="用户已授权按审查结果修补并验证">

## Intent

修复现有 MVG 流程在准备失败、候选不足和恢复时暴露的错误回执及旧结果绕过。输入保护保持严格，旧运行兼容以实际封套标记为准。本项是当前流程加固，不替代 Story 2.1 的逐 Capability 评选迁移。

## Boundaries & Constraints

**Always:** 失败回执记录本次问题；恢复读取持久化 run；不足三个准入候选不得评选或发布；保留旧证据用于诊断；机器与语义准入不放宽。

**Ask First:** 修改权威来源或正式产品范围。

**Never:** 修改任务三联、GDD、Capability、游戏代码/资源、正式 MVG manifest 或运行时验收状态；执行付费全流程；推送。

## I/O & Edge-Case Matrix

| 情况 | 输入 | 结果 |
| --- | --- | --- |
| 旧 run | 同名 schema、无封套标记 | 沿用旧 freshness，不误判缺封套 |
| 新 run | 封套标记 null 或封套删除 | 严格校验阻断 |
| prepare 重试 | 旧失败后新复制错误 | 最新回执；不发布 run |
| prepare 最终漂移 | 来源在复制期间改变 | 保留具体 drift 和 analysis identity |
| 候选不足 | terminal append 或 replacement 耗尽 | 明确 selection block，保留候选错误与 stop reason |
| 旧 winner | blocked run 留有 proposal/review/journal | review/validate/apply 均拒绝，证据不变 |
| 损坏回执 | model-execution JSON 无效 | 仍落盘 blocked，记录历史回执读取错误 |

</frozen-after-approval>

## Code Map

- `scripts/python/plan_mvg.py`：prepare 统一回执、输入 gate、候选不足诊断、后续发布门禁。
- `scripts/python/_project_health_planning.py`：封套判别与 durable run 恢复；保留当前本地 authority freshness。
- `scripts/python/tests/test_mvg_input_envelope.py`：准备失败、重试、漂移和同 schema 兼容。
- `scripts/python/tests/test_mvg_planning_contract.py`：真实 generate 阻断、replacement 耗尽与旧 winner 保护。
- `scripts/python/tests/test_project_health_planning.py`：恢复状态和本地来源保护。
- `scripts/python/tests/test_planning_audit_repair.py`：现行执行错误分类断言。

## Tasks & Acceptance

- [x] 收敛 prepare 回执，覆盖前期/复制/最终漂移与同 run 重试。
- [x] 区分旧 run 与新 envelope-bound run，不通过 schema 猜测。
- [x] 恢复候选统一消费持久化状态；旧 caller 不覆盖 admission/proof identity。
- [x] 两类候选不足路径使用同一门禁，保留 backend、attempts 和原审计字段。
- [x] 拦截 review/validate/apply 消费旧 winner，先于模型或 journal resume。
- [x] 对修补运行定向测试与静态检查；保留真实未通过夹具的边界。

Given prepare 失败后重试，when 本次错误发生，then 回执只描述本次错误，最终 freshness 明细不被泛化异常覆盖。

Given blocked selection 留有旧发布产物，when review/validate/apply 执行，then 模型、验证器和 journal resume 均不调用，所有证据文件保持不变。

Given 旧 caller 与磁盘 run 不一致，when 恢复，then 以磁盘 admission/hash 为准，并仍校验本地权威来源。

## Design Notes

旧、新 run 共用 `newrouge.mvg-planning-run.v1`，因此封套 key 的存在才是严格校验信号，null 标记不能回退旧路径。封套本身和 authority_inputs 分别保护 checkout 快照及当前来源，不删除后者。

先前将当前整批候选诊断补丁归为 Story 2.1 的记录已纠正。逐 Capability 评选规格保持 draft；本项结束不能把目标架构标记完成。

## Verification

证据目录：`logs/ci/2026-10-14/mvg-review-repair/`。

- 三模块定向回归：209 项通过，含真实 prepared append/proof fixture。
- 最终输入/消费者/回执回归：36 项通过。
- 损坏回执、旧 winner 门禁、审计执行错误：3 项通过。
- replacement exhaustion 的 durable 状态/回执：1 项通过。
- 最后追加门禁后的规划契约与审计回归：174 项全部通过。
- `py_compile` 和 `git diff --check`：通过。

未执行付费模型或 Godot 运行时。两个既有 project-health fake runner fixture 尚与现行 schema 不匹配，不能宣称全仓测试通过。

后续状态：Story 2.1 已定位并修复夹具的未准备测试路径，Knowledge planning 39 项通过；本段原声明保留为当时的验证边界，不代表当前仍有该夹具故障。当前证据见 `logs/ci/2026-10-14/story-2-1/`。

三层复审发现的旧 winner 绕过、损坏回执阻止落盘和 replacement exhaustion 验证缺口均已修复，并补充定向测试。它们的证据分别保存在 `final-block-gate-tests.txt`、`replacement-exhaustion-test.txt` 和 `post-gate-regression.txt`。

## Suggested Review Order

- prepare 最新回执与详细漂移保护。
  [plan_mvg.py:4219](../../scripts/python/plan_mvg.py#L4219)
- 候选不足、历史 winner 与审计字段。
  [plan_mvg.py:4348](../../scripts/python/plan_mvg.py#L4348)
- 恢复统一使用 durable run。
  [_project_health_planning.py:372](../../scripts/python/_project_health_planning.py#L372)
- 消费端拒绝 blocked selection。
  [plan_mvg.py:6363](../../scripts/python/plan_mvg.py#L6363)
- 真实 generate、损坏回执与旧发布绕过测试。
  [test_mvg_planning_contract.py:100](../../scripts/python/tests/test_mvg_planning_contract.py#L100)
