---
title: 'Story 2.1：只评选完整的准入候选集合'
type: 'feature'
created: '2026-10-14'
status: 'done'
baseline_commit: '905db329a1b738d2ab4196f71e87a0ebfbe58710'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-2-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 当前代码仍是三条候选各自处理全部 Capability 后再比较，尚未实现逐 Capability 的三候选评选。

**Approach:** 将评选放在当前 Capability 的三个增量候选全部准入之后，选定结果作为下一 Capability 的累计输入。不足时保持累计基线不变，写入可恢复的阻断原因和候选清单。

## Boundaries & Constraints

**Always:** 只有当前 Capability 的三个独立增量候选全部通过机器与语义准入后才能进入 selection；已接受累计基线只作为只读 seed，不得成为第四候选或 fallback；阻断状态和证据必须落盘。

**Ask First:** 若未来需要允许少于三个候选评选，必须先修改 Epic 2 规格和对应审计口径。

**Never:** 不降低现有准入校验，不把失败候选作为评选输入，不修改 Capability、Requirement、任务三联、GDD 或正式 MVG manifest。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|----------------------------|----------------|
| COMPLETE_SET | 三个候选均 admitted | 继续构造匿名 selection 输入 | N/A |
| INCOMPLETE_SET | 一个或多个候选未 admitted | 不创建可评选集合，累计基线不变 | `selection_blocked_insufficient_admitted_candidates`，保存 `run.json` 与 `model-execution.json` |

</frozen-after-approval>

## Code Map

- `scripts/python/plan_mvg.py`：`generate` 默认仍整批比较；复用 selector schema/validator、执行回执与阻断 helper。新策略须显式版本路由，保留旧 run 的必要恢复，不允许新 run 回退旧策略。
- `scripts/python/_mvg_capability_generation.py`：`generate_append` 提取显式单 scope/accepted seed 接口；复用完整传输、修复和准入。`append_proof_errors` 当前从原始 seed 回放全部 records，不能只校验最后一项。
- `scripts/python/_mvg_capability_append.py`：候选局部 ledger 与三次修复引擎；候选准入不能推进共享基线。
- `scripts/python/_project_health_planning.py`：`_mvg_valid_candidates` 恢复必须识别新路径的当前项与已选前缀。

## Design Notes

coordinator 持有原始 seed、已选 records/scopes 前缀及累计 proposal。每项三个 worker 从同一 seed 生成；候选 proof 组合已选前缀和本项 record，按冻结来源推导的期望前缀重验。最终混合 winner chain 应能复用现有 review/validate，不能伪造全批语义审查。

本故事提供持久化选择与前缀恢复；确定性事务 tuple、原子提交和 replay 冲突留给 2.2/2.3，不宣称完成。计费仍保持有界：不能因每项新 workspace 而静默重置总限制；64 是单 lineage 上限，聚合执行应如实记录各 lineage 成本。完整全局预算状态机属于 Epic 4。

## Tasks & Acceptance

**Execution:**
- [x] `_mvg_capability_generation.py`、`_mvg_capability_append.py`：提供单项 worker，保持来源、前缀、repair、semantic proof 校验，不裁剪权威输入。
- [x] `plan_mvg.py`：默认逐项 coordinator，三个准入后仅 A/B/C 比较；prompt 不要求未来覆盖，不生成 D；绑定 scope/order/base 和候选 hash。
- [x] `_project_health_planning.py`：恢复重验前缀与当前项证据，页面 fresh 点击仍新 run；失败保留已选前缀，不推进。
- [x] `workflow.md` 5.4、`.agents/skills/plan-mvg/SKILL.md`、`docs/workflows/mvg-integration-acceptance.md`：同步已部署边界，不提前声称事务保证。
- [x] `scripts/python/tests/`：公开入口假 runner 定向测试与既有回归；修复直接受迁移影响的 fixture，禁止降低 validator。证据放 `logs/**`。

**Acceptance Criteria:**
- Given 少于三个 admitted 候选，when 生成阶段准备进入 selection，then 状态为 blocked，原因为 `selection_blocked_insufficient_admitted_candidates`，且不推进累计基线。
- Given 当前 Capability 的三个 admitted increments，when selection 构造输入，then 只评选三个候选，已接受累计基线不作为第四候选或缺失候选补位。
- Given 两项 Capability，when 第一项选定，then 第二项三个 worker 使用相同 winner seed，最终混合 chain 可由 review/validate 重验。
- Given 前缀、scope 或回执 hash 被篡改，when 恢复或评选，then 在模型调用前拒绝并保留证据。

## Implementation Status

已接入默认 `capability-local-selection.v1`，完成三层审查后的定向修补：候选槽位/workspace/lineage 强绑定；执行失败隔离并区分可恢复与终态；不足候选的诊断回执保留；selector 完整输入超限在调用前停止；最终 proposal/proof 和成本从选中记录重算。run 调用预留为收费权威，中断后仅补足落后计数，不返还预算或重置修复机会。Knowledge 支持只有已选前缀的恢复，页面 fresh 点击仍创建新 run；manifest 缺失或变为目录返回失效。损坏诊断回执不能阻断状态落盘。

未运行付费模型或游戏验收，未修改任务三联、正式 manifest、游戏资源或 Capability 基线。当前超大比较输入明确阻断，不截断来源；完整分段比较容量方案、原子 checkpoint、幂等 replay 与全局预算状态机仍按后续故事实施。

## Verification

**Commands:**
- `py -3 -m unittest discover -s scripts/python/tests -p test_mvg_capability_append.py` -- expected: OK
- `py -3 -m unittest discover -s scripts/python/tests -p test_mvg_planning_contract.py` -- expected: OK
- 新 coordinator 和 Knowledge 恢复定向测试 -- expected: OK
- `py -3 -m py_compile scripts/python/plan_mvg.py` -- expected: SUCCESS
- `git diff --check` -- expected: SUCCESS

**Evidence:** `logs/ci/2026-10-14/story-2-1/`：Capability append 54、planning contract 137、Knowledge planning 40、planning audit 37、input envelope 29 项通过，另加损坏/非对象回执 2 项定向，共 299 项。矩阵 COMPLETE_SET/INCOMPLETE_SET 由公开入口 mixed-winner 与 incomplete-prefix 测试覆盖；额外验证候选克隆、lineage/成本、来源、scope、receipt 与 apply 输出篡改，失败槽隔离、selector 准备超限、run 预算终态、收费中断、只有前缀的 Knowledge 恢复和页面 fresh 新运行。使用严格 schema 的假 runner，不调用付费模型。`py_compile`、`git diff --check` 通过。

## Suggested Review Order

**逐项调度与身份验证**

- 从公共入口区分新策略与旧运行恢复。
  [plan_mvg.py:4453](../../scripts/python/plan_mvg.py#L4453)
- 三个准入增量共享 seed，胜者推进下一项。
  [_mvg_capability_selection.py:273](../../scripts/python/_mvg_capability_selection.py#L273)
- 强绑定候选槽位、workspace、lineage 和 proof。
  [_mvg_capability_selection.py:29](../../scripts/python/_mvg_capability_selection.py#L29)

**恢复与预算边界**

- 重验前缀并保守补记中断收费，不返还预算。
  [_mvg_capability_selection.py:121](../../scripts/python/_mvg_capability_selection.py#L121)
- 从选中项重算最终 proof 和累计成本。
  [_mvg_capability_selection.py:244](../../scripts/python/_mvg_capability_selection.py#L244)
- 网页恢复保留前缀，fresh 点击继续新建运行。
  [_project_health_planning.py:213](../../scripts/python/_project_health_planning.py#L213)

**验证与部署边界**

- 公共入口覆盖混合胜者、预算中断与篡改拒绝。
  [test_mvg_capability_append.py](../../scripts/python/tests/test_mvg_capability_append.py)
- 验证网页恢复及 manifest 缺失的失效行为。
  [test_project_health_planning.py:384](../../scripts/python/tests/test_project_health_planning.py#L384)
- 标明已部署选择能力和后续事务边界。
  [mvg-integration-acceptance.md:141](../../docs/workflows/mvg-integration-acceptance.md#L141)
