---
title: 'Story 2.2：提交确定性的 Capability checkpoint'
type: 'feature'
created: '2026-10-14'
status: 'done'
baseline_commit: '3dd8426a14ac44f77b3f211c94080a80e9954956'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 2.1 已完成逐 Capability 选择，但 coordinator 仍只更新 `run.json` 的 selected 列表，没有独立、可验证的选定 checkpoint。中断可能留下无法判断的部分状态。

**Approach:** 为每个选定 Capability 建立 hash-bound checkpoint，事务身份由 schema、run、Capability、顺序、base、proposal 和 selection receipt 的 canonical tuple 派生。checkpoint 完整准备后，仅通过一次原子替换 `run.json` 同时提交 checkpoint 指针与 selected 状态；失败保留旧 accepted baseline 并记录明确状态。

## Boundaries & Constraints

**Always:** checkpoint payload 必须包含与 identity 相同的 tuple、选定 delta、accepted seed、proposal/proof/receipt hash 和结果 hash；base hash 漂移必须拒绝；所有过程证据写入 `logs/**`。

**Ask First:** 无。

**Never:** 不修改 GDD、Requirement、Capability、任务三联、正式 MVG manifest 或游戏代码；不把 checkpoint 误称为 Story 2.3 的幂等 replay；不使用 prompt 代替 identity 或原子写入。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|----------------------------|----------------|
| SELECTED | 已通过准入的当前 selection 与同一 accepted base | 写入 committed checkpoint，selected 状态绑定 checkpoint | N/A |
| STALE_BASE | selection base 与当前 accepted base 不同 | 不推进 selected 或 accepted baseline | 写入 blocked reason |
| WRITE_INTERRUPTION | checkpoint 临时写入或可见状态推进中断 | 旧 selected/accepted 状态保持有效 | 保留 pending/failed 证据，不产生半个 checkpoint |

</frozen-after-approval>

## Code Map

- `scripts/python/_mvg_capability_selection.py` -- 当前逐 Capability selection coordinator 与 selected chain 推进点。
- `scripts/python/plan_mvg.py` -- prepare 冻结 checkpoint 协议；public generate 在首次状态修改前取得 OS 锁，锁内重新读取状态；proposal、selection receipt 和 freshness 校验复用点。
- `scripts/python/_mvg_input_envelope.py` -- 所有 envelope 消费路径重验 checkpoint 协议，防止 Knowledge 恢复被降级。
- `scripts/python/_planning_skill_common.py` -- canonical hash 与 atomic JSON 写入工具。
- `scripts/python/tests/test_mvg_capability_append.py` -- 新 checkpoint 身份、旧基线和中断定向测试。
- `workflow.md`, `.agents/skills/plan-mvg/SKILL.md`, `docs/workflows/mvg-integration-acceptance.md` -- 当前策略和后续 Story 边界。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/python/_mvg_capability_checkpoint.py` -- 实现 tuple、payload 校验和原子 checkpoint commit -- 保证选定增量身份可重验。
- [x] `scripts/python/_mvg_capability_selection.py` -- 在推进 selected chain 前提交 checkpoint，并拒绝 stale base -- 防止半成品累计状态。
- [x] `scripts/python/tests/test_mvg_capability_append.py` -- 覆盖 happy path、stale base 与写入中断 -- 验证 I/O 矩阵。
- [x] `scripts/python/plan_mvg.py`, `scripts/python/_mvg_input_envelope.py`, `scripts/python/tests/test_mvg_input_envelope.py` -- 协议冻结及 busy 时零写入/零调用 -- 防止降级与并发覆盖。
- [x] `workflow.md`, `.agents/skills/plan-mvg/SKILL.md`, `docs/workflows/mvg-integration-acceptance.md` -- 说明 Story 2.2 checkpoint 已部署、replay 仍归 Story 2.3 -- 防止能力边界误读。

**Acceptance Criteria:**
- Given selected Capability delta, when checkpoint commits, then deterministic transaction ID and identical tuple are persisted before selected state advances.
- Given a stale base or changed selection receipt, when commit is attempted, then no selected/accepted baseline advances and a blocked reason is retained.
- Given an interruption during checkpoint publication, when the run is inspected, then the last committed selected baseline remains usable and no partial payload is accepted.

## Design Notes

Checkpoint payload、delta、accepted seed 与选定结果保存在 run 内不可变 bundle，存在本身只代表 prepared。`run.json` 是唯一可见 commit：一次 atomic replace 同时写入 checkpoint 指针、selected 列表、accepted hash 和 current 清理。提交前复制状态，不提前修改共享 state；提交失败后外层错误持久化不得意外提交新基线。Full same-ID replay and conflicting payload handling are implemented and tested by Story 2.3.

新 prepare 将 `checkpoint_strategy=capability-selected-checkpoint.v1`、`checkpoint_schema_version=newrouge.mvg-capability-checkpoint.v1` 同时写入已 hash 绑定的 index 和 run。旧 Story 2.1 run 没有该协议字段时保持原恢复策略；新 run 删除或修改协议字段必须在模型调用前失败，不凭字段缺失降级。

审查修补后：提交异常且磁盘回读失败时，只写 uncertainty sidecar 并停止，禁止通用错误持久化覆盖已提交指针；恢复在 public generate 的锁内先重新读取磁盘并完整验链。staging 后重验所有前驱 checkpoint、proof 和 receipt。apply journal 首次原子落盘时冻结 selected projection 与 evidence hash；恢复先校验绑定，允许 journal 自己写出的 manifest 变化和显式 handoff 可变字段。

## Verification

**Commands:**
- `py -3 -m unittest discover -s scripts/python/tests -p test_mvg_capability_append.py` -- expected: OK
- `py -3 -m py_compile scripts/python/_mvg_capability_checkpoint.py scripts/python/_mvg_capability_selection.py` -- expected: SUCCESS
- `git diff --check` -- expected: SUCCESS

**Review fixes:** 三个独立审查层均已完成；六项有效发现全部按 patch 修补，无范围决策或延期。证据见 `logs/ci/2026-10-15/story-2-2/review-triage.md`、`fix-through-summary.md`、`checkpoint-journal-verification.json`。

规划契约 137 项、输入封装与 Knowledge 合计 71 项通过；journal 三项公共测试及双删除组合补验通过。异常回读、前驱 bundle/proof 漂移、public stale base/receipt、旧协议前缀恢复和完整七字段 tuple 定向验证通过。所有模型执行使用离线 fixture，没有运行收费生成流程或 Godot 运行时验收。

最终完整 append 回归：71 项，723.667 秒，全部通过，无跳过或禁用。加强后的四项错误原因定向断言另行通过。矩阵覆盖完整：事务身份与 happy path、public stale base/receipt、bundle/pointer 写入前后异常、进程中断及未知提交结果均有实际执行的成功测试。

## Suggested Review Order

**唯一提交点与恢复**

- 公共入口先取锁、重读状态，解决未知提交结果。
  [plan_mvg.py:4457](../../scripts/python/plan_mvg.py#L4457)
- 完整 bundle 准备后，原子提交指针和累计状态。
  [_mvg_capability_checkpoint.py:141](../../scripts/python/_mvg_capability_checkpoint.py#L141)
- 提交结果不明时，先验磁盘链，再允许写状态。
  [_mvg_capability_checkpoint.py:26](../../scripts/python/_mvg_capability_checkpoint.py#L26)
- 前缀校验同时绑定候选、receipt 和每个 checkpoint。
  [_mvg_capability_selection.py:122](../../scripts/python/_mvg_capability_selection.py#L122)

**正式发布恢复与验证**

- journal 原子冻结证据，恢复拒绝漂移。
  [plan_mvg.py:6451](../../scripts/python/plan_mvg.py#L6451)
- 故障注入证明已提交指针不被旧内存回滚。
  [test_mvg_capability_append.py:528](../../scripts/python/tests/test_mvg_capability_append.py#L528)
- 篡改和合法 handoff 重放共同覆盖 apply 边界。
  [test_mvg_checkpoint_journal.py:15](../../scripts/python/tests/test_mvg_checkpoint_journal.py#L15)
