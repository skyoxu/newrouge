---
title: 'Story 3.3：准入、重放与最终审计的记账守恒'
type: 'feature'
created: '2026-10-15'
status: 'done'
baseline_commit: 'e4b1e148c725387125e79e1cd56fdf03c6c27ac9'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 记账模型存在并不代表全部消费边界都保护它；中间累计状态或 journal 恢复可能绕过最终检查，旧产物的读取迁移也可能改变哈希或完成计数。

**Approach:** 在现有机器准入、累计 proof 重建、checkpoint/journal 恢复和最终确定性审计复用同一记账校验，证明无损迁移与唯一完成计数。

## Boundaries & Constraints

**Always:** 基于 Story 3.1/3.2 的唯一模型，不新建第二套记账。验证完整当前累计范围及每个中间前缀；错误在语义调用或目标写入前阻断。

**Ask First:** 无；按既定 AD-4/5/6/10 与 Story 3.3 验收实施。

**Never:** 不改 GDD、Requirement、任务三联、Capability、正式 MVG manifest、游戏文件；不调用收费模型、Godot 或远程 Git；不修改旧 hash-bound 对象来通过迁移，不把 planned/implemented 测试当成已通过。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
| --- | --- | --- | --- |
| ADMISSION | 缺权威处置、重复键、未知/未准备证据或 flow/test 范围错误 | 机器拒绝，语义 runner 调用为零 | 输出字段与对象 |
| PREFIX | 最终对象正确但累计中间状态不合法 | proof/checkpoint 恢复拒绝 | 原前驱不变 |
| JOURNAL | 待恢复事务携带坏新记账 | 任何目标写入前拒绝 | 目标及 journal 权威保持原样 |
| LEGACY | 无新字段的旧 checkpoint、trace、completed journal | 原 hash/处置/owner/证据与完成计数守恒，路线独立可查询 | 不原地升级 |

</frozen-after-approval>

## Code Map

- `scripts/python/_mvg_requirement_accounting.py`, `_mvg_requirement_routes.py` -- 复用前两项共享投影及验证器，不复制状态语义；确定最终代码后补必要参数。
- `scripts/python/plan_mvg.py` -- `validate_proposal` 已加载冻结来源，`candidate_admission_errors/validate` 接入前置及最终统一检查；`apply` journal 分支先于普通 validate，须在恢复目标写入前验证。
- `scripts/python/_mvg_capability_generation.py` -- `machine/final_machine` 复用 validator；`append_proof_errors` 每次重建 revised 后核验累计记账，最终合法不替代中间合法。
- `scripts/python/_mvg_capability_selection.py`, `_mvg_capability_checkpoint.py` -- `candidate_artifacts/verified_prefix/verify_published_chain` 与 committed replay；保持旧 payload/hash，独立副本投影。
- `scripts/python/_planning_apply_journal.py` -- 沿用现有 journal authority/binding，不扩大允许写入集合。
- `scripts/python/tests/test_mvg_requirement_accounting.py`, `test_mvg_checkpoint_replay.py`, `test_mvg_checkpoint_journal.py`, `test_mvg_requirement_routes.py` -- 复用离线矩阵及 public fake runner。
- `docs/adr/ADR-0005-quality-gates.md` -- Accepted 门禁依据。

## Tasks & Acceptance

**Execution:**
- [x] 统一校验实际准入/最终机器审计入口 -- 所有新增硬错误先于语义调用。
- [x] 逐前缀 proof/replay 与 journal 校验 -- 错误先于累计目标写入。
- [x] legacy 真实路径守恒夹具 -- 原始 hash 与计数不变。
- [x] owning docs 同步已部署边界 -- 不声称全局冲突重开或 runtime 完成。

**Acceptance Criteria:**
- Given a proposal or cumulative delta, when accounting validation runs, then every active Requirement has one disposition, unique route/evidence keys, prepared resolvable sources and consistent bidirectional flow/test scope.
- Given a legacy projection and its migrated read view, when real replay is performed, then original hashes, authoritative dispositions and completion counts are conserved and route memberships remain separately queryable.

## Design Notes

仅补实际入口遗漏；若 Story 3.2 已接通某处，增加证明而不重复重构。新协议 fail closed，旧协议先验证原 hash 再只读投影。限定当前冻结 scope，不能扩大 pilot。所有中间状态与最终状态使用同一边界。共享证据可服务多个 flow，不要求机械复制测试；不同路线行为仍需明确证据范围。`source_gap` 阻断 planning_complete，但不得变成新的 Requirement 或 Task。

全局来源冲突/reopen 与最终权威报告归 Epic 4；本项最终审计指完整累计记账检查，不增加最终 LLM 语义否决。全部测试离线，日志放 `logs/ci/2026-10-15/story-3-3/`。实现代理不提交。

实施入口核实：Story 3.2 已接通最终 `validate_proposal`、默认生成机器门与可信 trace 汇总；重点补 `append_proof_errors` 的逐中间前缀校验，以及 `apply` 的 journal 快速分支。journal 恢复期间原目标可能已部分写入，不得机械重跑会拒绝自身合法写入的全部原始 freshness；须验证冻结准备副本、同一处置/路线/证据规则、原 proposal/proof 及 journal 实际目标 payload 的绑定。新协议不能降级；历史 journal/checkpoint 先验证原 hash，使用独立只读投影，不回写升级。测试用例应实际穿过公共消费入口，且 malformed 输入返回确定性诊断，不以生成 schema 理想输入为前提。尽量复用已存在的公共 fixture，每一慢链只验证与该边界相关的对象，避免重复启动整个已通过套件。

## Verification

- 新 accounting admission/replay 定向矩阵，覆盖全部四行及零语义调用、零目标写入断言。
- 受影响 checkpoint replay/journal、route/accounting 与最终 validate 定向回归。
- 改动模块 `py_compile`；`git diff --check`。

结果：三层独立审查完成，11 类直接修补已落实。初始矩阵 5 项与受影响回归 8 项通过；审查后 `planning_contract` 完整模块 137 项通过，真实恢复/legacy/journal 扩展矩阵 6 项通过，主代理独立复验 4 项通过。公共准入矩阵先断言基础 proposal 合法，再精确断言每类错误及零模型调用；恢复矩阵覆盖已重新封装哈希的非法中间前缀、协议降级、处置授权、结果形状和合法部分写入。旧 completed journal 的真实验证证据满足计数为 1，重复恢复后保持 1，原 journal/proposal/review/trace bytes 不变。编译和差异检查通过。全部证据见 `logs/ci/2026-10-15/story-3-3/verification-progress.md` 与 `review-triage.md`；原失败日志保留。未调用付费模型、Godot 或远程 Git。全局 audit/reopen 及最终完成报告仍由 Epic 4 实施。

## Suggested Review Order

**统一准入与重放**

- 同一边界复用冻结 owner、处置、授权和证据规则。
  [_mvg_requirement_accounting.py:405](../../scripts/python/_mvg_requirement_accounting.py#L405)
- 完整对象与覆盖投影使用相同规则，限定投影差异。
  [_mvg_planning_review.py:74](../../scripts/python/_mvg_planning_review.py#L74)
- 每个累计前缀都验证，最终合法不能隐藏中间错误。
  [_mvg_capability_generation.py:794](../../scripts/python/_mvg_capability_generation.py#L794)

**写入前保护**

- 语义门先做机器准入，坏输入不调用模型。
  [plan_mvg.py:500](../../scripts/python/plan_mvg.py#L500)
- journal 绑定冻结来源及实际 payload，完整检查后恢复。
  [plan_mvg.py:6670](../../scripts/python/plan_mvg.py#L6670)

**定向证据**

- 合法输入逐项变异，断言具体诊断和零调用。
  [test_mvg_requirement_accounting.py:412](../../scripts/python/tests/test_mvg_requirement_accounting.py#L412)
- 真实恢复拒绝非法前缀，原状态不变。
  [test_mvg_checkpoint_replay.py:40](../../scripts/python/tests/test_mvg_checkpoint_replay.py#L40)
- 篡改零写入与历史非零满足计数守恒。
  [test_mvg_checkpoint_journal.py:131](../../scripts/python/tests/test_mvg_checkpoint_journal.py#L131)
