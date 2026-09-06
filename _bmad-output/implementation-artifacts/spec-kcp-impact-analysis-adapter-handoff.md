---
title: 'KCP Impact Analysis Adapter Handoff'
type: 'feature'
created: '2026-09-04'
status: 'done'
review_loop_iteration: 0
baseline_commit: '576dbb611a76a14419bf45da38478ffed4737d7d'
context:
  - '_bmad-output/specs/spec-kcp-impact-analysis/SPEC.md'
  - '_bmad-output/architectures/architecture-kcp-impact-analysis/ARCHITECTURE-SPINE.md'
  - '_bmad-output/architectures/architecture-kcp-impact-analysis/architecture-details.md'
  - 'docs/workflows/knowledge-context-freeze.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** KCP Impact Analysis 已有设计，但 Chapter 6 和 Review 尚不能接收或验证 frozen context、impact report 与 Git revision，可能在证据缺失或绑定错误时继续进入 RED 或评审。

**Approach:** 增加一个共享、只读、fail-closed 的 handoff validator，并让 Chapter 6 orchestrator 与 Review pipeline 通过同一三参数契约接入。第一阶段采用显式 opt-in：三参数必须全有或全无；全有时必须在任何编码、测试或评审步骤前通过验证，全无时保持现有流程，后续 enforce rollout 另行决策。

## Boundaries & Constraints

**Always:** 将 `--frozen-context`、`--impact-report`、`--revision` 视为原子参数组；验证仓库内路径、schema/state、真实 SHA-256、report status/revision、task/consumer、`knowledge_binding` 与 index binding；失败使用稳定 exit code，且不得启动 RED、test、acceptance 或 LLM review。Resume/fork 只能复用相同 hash identity。

**Ask First:** 若必须修改现有 `summary.json`、`execution-context.json`、`latest.json` schema，或将 opt-in 改为默认强制 enforce，必须先取得用户批准。

**Never:** 不实现完整 index/resolver/analyzer；不修改 frozen context；不回退 current/LKG；不把参数传给不认识它们的子命令；不关闭测试。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Legacy opt-out | 三参数全部缺失 | 保持现有 Chapter 6/Review 行为 | 无 |
| Valid handoff | 三参数齐全且所有 hash/revision/binding 匹配 | Chapter 6 可进入 RED；Review 可构造并运行步骤 | 无 |
| Partial handoff | 只提供一项或两项 | 任何下游步骤前停止 | `invalid_kcp_binding`, exit 11 |
| Revision mismatch | CLI revision 与 report/frozen context 不一致 | 停止且不产生成功 sidecar | `revision_mismatch`, exit 7 |
| Invalid binding | 文件缺失、JSON/schema/state/hash、task 或 consumer 不匹配 | 停止且不运行下游命令 | 对应 exit 5 或 11 |
| Resume/fork mismatch | 新输入与 source run identity 不一致 | 禁止复用旧结果 | fail closed，稳定诊断 |

</frozen-after-approval>

## Code Map

- `scripts/python/impact_analysis_handoff.py` -- 共享路径、JSON、SHA-256、revision、task/consumer 与 binding 验证器。
- `scripts/python/dev_cli.py` -- `run-single-task-chapter6` parser 增加三参数，不在入口复制验证逻辑。
- `scripts/python/dev_cli_builders.py::build_run_single_task_chapter6_cmd` -- 将三参数原样转发到 Chapter 6 orchestrator。
- `scripts/python/run_single_task_chapter6_lane.py::main` -- initial route 成功后、任何 check-tdd/RED/review 前执行 handoff guard；`build_review_pipeline_cmd` 与 fork builder 转发同一参数组。
- `scripts/sc/_pipeline_helpers.py::build_parser` -- Review pipeline 的真实 parser；接收三参数。
- `scripts/sc/run_review_pipeline.py::main` -- 在 `_allocate_out_dir`、persist、step build 与 prerequisite 前校验；resume/fork 对 source handoff identity 做 exact-match。
- `scripts/sc/tests/test_dev_cli_recovery_commands.py` -- dev CLI 参数转发覆盖。
- `scripts/python/tests/test_run_single_task_chapter6_lane.py` -- RED 前阻断、review/fork 转发及有效输入覆盖。
- `scripts/sc/tests/test_run_review_pipeline_preflight.py` -- standalone Review 的 fail-closed 与“零下游步骤”覆盖。
- `scripts/sc/tests/test_run_review_pipeline_marathon.py` -- resume/fork identity 复用与 mismatch 覆盖。

## Tasks & Acceptance

**Execution:**
- [x] 上述测试文件 -- 添加 valid、partial、missing、binding mismatch 与参数转发测试。
- [x] `scripts/python/impact_analysis_handoff.py` -- 实现共享验证结果模型、稳定 exit code 与 exact-byte SHA-256 校验。
- [x] Chapter 6 入口与 builders -- 增加参数转发，在 RED/review 前调用 guard，失败时停止且不执行下游。
- [x] Review parser 与 main -- 增加 preflight、resume/fork identity 校验，不改变现有公共 sidecar schema。
- [x] 相关回归测试 -- 验证无参数旧流程、self-check、forbidden command、pipeline sidecar 与 artifact schema 不退化。

**Acceptance Criteria:**
- Given 三参数齐全且绑定有效，when 运行 Chapter 6 或 Review，then 参数被精确传递且只有在 preflight 通过后才执行下游步骤。
- Given 任一 handoff 校验失败，when 运行 consumer，then 返回稳定非零 exit code，且 RED、test、acceptance、LLM review 均未启动。
- Given resume/fork 请求，when handoff hash identity 与 source run 不完全一致，then 禁止复用并输出稳定诊断。
- Given 三参数全部缺失，when 运行现有命令，then 既有行为与 sidecar schema 保持不变。

## Spec Change Log

## Design Notes

共享 validator 是唯一 schema/hash 校验源；dev CLI 和两个 orchestrator 只负责参数收集、调用与失败传播。Handoff identity 至少包含 revision、frozen context exact-byte SHA-256、impact report exact-byte SHA-256、report index ID/SHA-256 和 knowledge binding hash。若现有 sidecar 不允许承载 identity，使用 Impact Analysis 私有 manifest，不扩展现有 KCP/Review authority schema。

## Verification

**Commands:**
- `py -3 scripts/sc/tests/test_dev_cli_recovery_commands.py` -- 参数转发与旧命令兼容通过。
- `py -3 scripts/python/tests/test_run_single_task_chapter6_lane.py` -- Chapter 6 guard、顺序和 fail-closed 通过。
- `py -3 scripts/sc/tests/test_run_review_pipeline_preflight.py` -- Review preflight 在任何步骤前正确阻断。
- `py -3 scripts/sc/tests/test_run_review_pipeline_marathon.py` -- resume/fork identity 行为通过。
- `py -3 scripts/python/validate_knowledge_control_plane.py --require-generated` -- KCP generated state 未被破坏。

## Suggested Review Order

**Handoff validation**

- 先看共享校验器，确认三参数原子性与 fail-closed 规则。
  [`impact_analysis_handoff.py:54`](../../scripts/python/impact_analysis_handoff.py#L54)

- 检查 Chapter 6 在任何 RED 或 Review 前阻断无效绑定。
  [`run_single_task_chapter6_lane.py:797`](../../scripts/python/run_single_task_chapter6_lane.py#L797)

**Review integration**

- 检查 Review parser 与 preflight 时序，确保不会先创建成功运行记录。
  [`run_review_pipeline.py:1850`](../../scripts/sc/run_review_pipeline.py#L1850)

- 检查 resume/fork 的私有 identity 比对与复用边界。
  [`run_review_pipeline.py:1969`](../../scripts/sc/run_review_pipeline.py#L1969)

**Tests and compatibility**

- 查看 validator 场景测试与精确哈希断言。
  [`test_impact_analysis_handoff.py:12`](../../scripts/python/tests/test_impact_analysis_handoff.py#L12)

- 查看 Chapter 6 参数转发和旧流程兼容回归。
  [`test_run_single_task_chapter6_lane.py:34`](../../scripts/python/tests/test_run_single_task_chapter6_lane.py#L34)
