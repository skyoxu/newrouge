---
title: 'Story 2.3：幂等重放与 checkpoint 冲突证据'
type: 'feature'
created: '2026-10-15'
status: 'done'
baseline_commit: 'c9c97ba36cfbccf4650f4a65835eb08a979573dd'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 2.2 已提供原子选定 checkpoint，但已提交事务的直接重放仍可能被当成 stale base；冲突只有一般错误，缺少按事务关联的证据。

**Approach:** 识别已提交事务，在完整验证 canonical payload、receipt 和累计前驱后返回 no-op。冲突保留结构化证据并停止，禁止重复合并或回退已接受状态。

## Boundaries & Constraints

**Always:** 同事务身份只有 canonical JSON 完全相同才可重用；恢复验证发生在模型调用前；下一 Capability 消费已记录 accepted baseline；证据放入 `logs/**`。

**Ask First:** 无，实施现有 Epic 2 已批准的恢复契约。

**Never:** 不修改 GDD、Requirement、Capability、任务三联、正式 MVG manifest 或游戏文件；不新增平行生命周期；不将 Python 数值或布尔相等当成 canonical 相等；不把新页面点击变成旧 run 恢复。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
| --- | --- | --- | --- |
| IDENTICAL_REPLAY | 已提交事务，canonical 内容相同，包括不同 JSON 键序/空白 | 明确 no-op，不增加 selected、delta 或预算；较早事务不回退最新 head | N/A |
| IDENTITY_CONFLICT | 相同事务 ID，payload 内容或类型不同 | 拒绝重放，保留原 checkpoint 和 accepted projection | 写入事务 ID、原因、期望/实际 hash 的冲突证据 |
| RECEIPT_OR_PREDECESSOR | receipt 缺失/改变或前驱 hash 改变 | CLI/Knowledge 均拒绝重用，不调用模型 | 持久化可定位的冲突证据 |
| PREFIX_RECOVERY | 第一项已提交，第二项尚未 dispatch | 从第一项 accepted seed 继续；第一项不重选、不重复计费 | 输入不匹配则 fail closed |

</frozen-after-approval>

## Code Map

- `scripts/python/_mvg_capability_checkpoint.py` -- `prepare_checkpoint`, `verify_checkpoint`, `commit_checkpoint` 当前 bundle 与唯一提交点；沿用协议和 OS 锁，补 canonical equality、committed replay 和冲突 evidence helper。
- `scripts/python/_mvg_capability_selection.py` -- `verified_prefix` 恢复和最终链验证的共同入口；`generate_selected_capabilities` 推进点；复用已有 receipt/proof/lineage 校验，不建立第二个 coordinator。
- `scripts/python/plan_mvg.py` -- public generate 在锁内先解决未知提交结果；journal 恢复有独立冻结绑定。只在共同 helper 无法覆盖时调整接线。
- `scripts/python/tests/test_mvg_capability_append.py` -- 公共离线 runner fixture、混合胜者和中断恢复可复用。
- `scripts/python/tests/test_mvg_checkpoint_replay.py` -- 新增专用 helper/public replay、冲突和下一项 seed 测试，避免重复执行无关 fixture。
- `scripts/python/_project_health_planning.py` -- Knowledge 通过共同 prefix validator 查询可恢复结果；优先复用，不增加 UI 状态权威。
- `workflow.md`, `.agents/skills/plan-mvg/SKILL.md`, `docs/workflows/mvg-integration-acceptance.md`, `docs/workflows/project-health-knowledge.md` -- 验证后同步 replay 已部署边界。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/python/_mvg_capability_checkpoint.py` -- 完整 canonical replay 判定与结构化冲突证据 -- 保证相同身份只被应用一次。
- [x] `scripts/python/_mvg_capability_selection.py` -- 接入恢复验证和冲突证据 -- 保留最新 accepted 链和明确失败原因。
- [x] `scripts/python/tests/test_mvg_checkpoint_replay.py` -- 覆盖矩阵以及较早事务重放、类型差异、真实前缀恢复 -- 独立证明 public 行为和零额外调用。
- [x] `workflow.md`, `.agents/skills/plan-mvg/SKILL.md`, `docs/workflows/mvg-integration-acceptance.md`, `docs/workflows/project-health-knowledge.md` -- 更新 Story 2.3 当前能力 -- 保持稳定入口和页面说明一致。

**Acceptance Criteria:**
- Given an existing committed transaction, when an identical canonical payload is replayed, then replay is a no-op and the next Capability uses the recorded accepted baseline.
- Given a conflicting payload, missing receipt or changed predecessor, when recovery checks the transaction, then it records an identity conflict without changing the accepted projection or invoking a model.

## Design Notes

重放只识别已提交 `selected` 成员；孤立 prepared bundle 不能作为已提交结果。存在后继时也验证完整前缀后再 no-op，不能回退 head。canonical hash 对 JSON 类型敏感，忽略序列化空白和对象键序；数组顺序仍保留。错误证据是诊断 sidecar，不是新的 authority。Story 2.2 的不确定提交恢复与 apply journal 绑定必须保持。

生产直接重放同样复用共同 prefix validator，检查冻结 scope、原始 seed、候选/proof/selection 和调用账本。协议标记、prepared index 和固定 run 布局共同防止删字段降级。已占用位置的新身份关联原/实际 transaction；诊断对非法路径和类型安全，明确 `hash_subject`，同一异常只记一次。accepted hash 冲突也保留精确期望/实际 hash。

## Verification

- `py -3 -m unittest discover -s scripts/python/tests -p test_mvg_checkpoint_replay.py` -- expected: OK
- `py -3 -m unittest scripts.python.tests.test_mvg_capability_append.CapabilityAppendTests.test_public_checkpoint_unknown_commit_outcome_never_rolls_back scripts.python.tests.test_mvg_capability_append.CapabilityAppendTests.test_public_checkpoint_rechecks_predecessor_after_staging scripts.python.tests.test_mvg_capability_append.CapabilityAppendTests.test_public_legacy_selected_prefix_recovers_without_checkpoint_protocol` -- expected: OK
- `py -3 -m unittest discover -s scripts/python/tests -p test_mvg_checkpoint_journal.py` -- expected: OK if replay changes affect journal validation; otherwise reuse the completed Story 2.2 journal regression with explicit scope rationale.
- `py -3 -m py_compile scripts/python/_mvg_capability_checkpoint.py scripts/python/_mvg_capability_selection.py` -- expected: SUCCESS
- `git diff --check` -- expected: SUCCESS

审查修补后的实际结果：回放专用 15 项通过（114.446 秒）；Story 2.2 指定回归 3 项通过（78.332 秒）；journal 3 项通过（188.595 秒）。Windows 大写目录与删除全部协议标记专项、异常 Path 诊断专项通过。编译与 diff 检查通过。所有会话已结束，证据见 `logs/ci/2026-10-15/story-2-3/`。

## Suggested Review Order

**回放与权威验证**

- 已提交事务复用完整验证链，保持最新累计状态。
  [_mvg_capability_checkpoint.py:207](../../scripts/python/_mvg_capability_checkpoint.py#L207)
- 明确区分重复提交与首次提交。
  [_mvg_capability_checkpoint.py:309](../../scripts/python/_mvg_capability_checkpoint.py#L309)
- 公共恢复入口记录链损坏与 accepted hash 冲突。
  [_mvg_capability_selection.py:160](../../scripts/python/_mvg_capability_selection.py#L160)

**诊断与验证证据**

- 类型安全的冲突 sidecar 保留原始验证错误。
  [_mvg_capability_checkpoint.py:20](../../scripts/python/_mvg_capability_checkpoint.py#L20)
- 离线覆盖幂等、身份冲突、真实前缀恢复与零额外调用。
  [test_mvg_checkpoint_replay.py:18](../../scripts/python/tests/test_mvg_checkpoint_replay.py#L18)
