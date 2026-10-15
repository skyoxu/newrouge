---
title: 'Story 4.2：全局冲突审计与显式重开闭包'
type: 'feature'
created: '2026-10-15'
status: 'done'
baseline_commit: '46533252e1e2c8264ed58628bb7144abc719af62'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 选定链缺少明确的全局来源冲突与历史重开接口，不能把普通重叠误作冲突，也不能直接覆盖已接受历史。

**Approach:** 在既有审查/冻结来源证据上生成绑定的确定性全局审计；真实硬冲突才允许显式 reopen 计划，保留旧链并重新生成受影响的累计后继。

## Boundaries & Constraints

**Always:** 默认修当前增量。重开必须绑定同一 run、audit、head、来源引用与受影响 Capability/flow；默认使最早受影响项及全部后继失效。替代仍经三候选准入、比较和原子提交。

**Ask First:** 仅真实来源权威需变更时交由拥有者决策；本项不得自行更改产品来源。

**Never:** 不把重复 Requirement、共享 Contract 或路线重叠当冲突；不新增最终整批 LLM否决，不猜自然语言矛盾；不覆写旧 evidence/checkpoint、不清空费用；不改游戏或正式基线、不调用收费模型/引擎/远程Git。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
| --- | --- | --- | --- |
| OVERLAP | 多 flow引用相同Requirement或Contract，无矛盾证据 | 记为普通重叠，不重开 | N/A |
| CONFLICT | 真实审查提供来源绑定的矛盾与受影响项 | audit列硬冲突，完成阻断；显式计划给出全后继闭包 | 缺证据/漂移拒绝 |
| REOPEN | 已审查计划、准确head及来源身份 | 锁内原子切换活动前缀，旧链归档，替代顺序明确 | 旧事务保持原样 |
| STALE | changed head、来源、预算或已有apply journal | 不执行reopen | 写诊断、无活动链变更 |

</frozen-after-approval>

## Code Map

- `scripts/python/_mvg_global_audit.py` -- 新共享审计/冲突来源校验与闭包计算，不实现自然语言判断器。
- `scripts/python/_mvg_capability_selection.py` -- 完成全部checkpoint后审计；`verified_prefix/verify_published_chain` 验活动链；reopen替代目录/lineage必须带新attempt身份，不能固定r1覆盖旧候选。
- `scripts/python/_mvg_capability_checkpoint.py` -- 复用coordinator_lock及run.json唯一提交点，旧payload/receipt不可变；新选择自然产生新transaction。
- `scripts/python/plan_mvg.py`, `dev_cli.py`, `dev_cli_builders.py` -- 稳定入口增加显式audit/计划/执行操作，参数消费精确run/plan/hash；保留generate/review/validate/apply行为。
- `scripts/python/_mvg_evidence_transport.py`, `_mvg_planning_review.py` -- 复用既有审查hard issue、完整来源/hash/citation链；不能只凭模型文字或文件存在授权重开。
- `scripts/python/update_mvg_baseline.py` -- `_reviewed_authority`及change_reviews只验证既有授权，不替代冲突证据，不放宽累计保护。
- `scripts/python/tests/test_mvg_global_audit.py` -- 真实离线checkpoint链和fake runner，覆盖闭包/来源/替代/费用守恒。
- `scripts/python/tests/test_mvg_global_audit_boundaries.py` -- 原始换行/BOM、累计冲突解决边界、闭包分支及坏类型的独立窄回归。
- `docs/adr/ADR-0005-quality-gates.md` -- Accepted门禁依据。

## Tasks & Acceptance

**Execution:**
- [x] 共享全局审计与来源绑定 -- 区分普通重叠和真实硬冲突。
- [x] 显式reopen计划/执行及所有后继闭包 -- 活动链与历史证据分离。
- [x] 替代候选复用现有生命周期 -- 新隔离上下文且不退款。
- [x] 定向矩阵/CLI与owning文档 -- 证明真实恢复和拒绝行为。

**Acceptance Criteria:**
- Given repeated Requirements, shared Contracts or overlapping flows without contradictory authority, when audited, then no checkpoint is reopened.
- Given a source-backed hard conflict, when an explicit reopen plan is executed, then evidence, affected objects, all invalidated descendants, replacement order and replacement selections are persisted without mutating historical records.

## Design Notes

审计只消费已经存在的独立审查或显式来源冲突声明，验证其来源hash、精确行引用、被影响对象及当前链身份，不另调用模型发明冲突。无法证明是硬冲突的报告为证据缺口，不能自动重开。正常完整链可以没有冲突声明；这表示当前已审核来源中无已报告硬冲突，不声称机器理解全部自然语言。

首版无确定性rebase证明能力，固定使全部累计后继失效，不留“看起来无关”后继。执行时如存在pending或completed apply journal则拒绝，需新的规划run处理已发布基线，不改既有journal。reopen保留run总账与原candidate lineage历史；新尝试身份进入workspace、receipt、call ledger及validator。绝不能覆盖固定scope目录或把旧已准入候选当新候选。

全局audit receipt绑定proposal/head/冻结输入，变更立即失效。最终报告权限由Story4.3消费。日志放`logs/ci/2026-10-15/story-4-2/`，实现代理不提交。

实施前调查补充：当前`candidate_artifacts`把workspace固定为`candidates/<label>/scope-N`，调用数按candidate+Capability聚合，lineage固定`<label>-r1`；`verified_prefix`、selector恢复、最终`accepted-chain`发布也共享这些假设。reopen必须让新的generation/attempt身份贯穿目录、admission、调用筛选、selection及最终proof发布，同时保留原candidate累计预算和旧lineage历史，不可只改目录名。旧generation的selection/proof/payload保留原路径和bytes，活动`proposal.json`只作当前投影；归档不得引用之后会被覆盖的证据文件。计划执行前后调用同一完整prefix校验，按实际文件写入故障测试原子切换与无付费恢复。

## Verification

- 全局audit矩阵：普通重叠、真实来源冲突、缺引用/漂移、精确闭包。
- 显式reopen离线真实链：旧证据bytes不变、新候选隔离、费用不减、全后继重选及stale/journal拒绝。
- 改动模块`py_compile`；`git diff --check`。

三层审查后的必修项已修补。增强真实离线链4项通过（173.431秒），独立边界5项通过；主代理另复验8项窄测通过。覆盖原始换行/BOM、累计冲突解决边界、实际请求传输、未解决冲突阻断、三次修复及干净重启、完整历史依赖篡改拒绝、checkpoint后中断免费恢复、apply/journal回放。编译和diff检查通过。证据位于`logs/ci/2026-10-15/story-4-2/`，没有收费模型、引擎或远程操作。

## Suggested Review Order

**审计与明确授权**

- 从公开审计和重开入口理解来源绑定。
  [\_mvg_global_audit.py:480](../../scripts/python/_mvg_global_audit.py#L480)
- 历史完整复验，保留真实冲突来源和费用。
  [\_mvg_global_audit.py:174](../../scripts/python/_mvg_global_audit.py#L174)
- 唯一原子切换保留原链，替代使用新generation。
  [\_mvg_global_audit.py:406](../../scripts/python/_mvg_global_audit.py#L406)

**恢复与发布绑定**

- 从已提交checkpoint重建历史选择投影。
  [\_mvg_capability_selection.py:732](../../scripts/python/_mvg_capability_selection.py#L732)
- journal冻结活动和历史证明依赖。
  [plan_mvg.py:6661](../../scripts/python/plan_mvg.py#L6661)

**定向验证**

- 真实离线链覆盖来源、冲突、中断和发布恢复。
  [test_mvg_global_audit.py:72](../../scripts/python/tests/test_mvg_global_audit.py#L72)
- 原始换行和累计解决边界独立回归。
  [test_mvg_global_audit_boundaries.py:15](../../scripts/python/tests/test_mvg_global_audit_boundaries.py#L15)
