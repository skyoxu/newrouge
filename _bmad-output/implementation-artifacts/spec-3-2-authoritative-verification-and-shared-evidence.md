---
title: 'Story 3.2：唯一权威验证与共享证据记账'
type: 'feature'
created: '2026-10-15'
status: 'done'
baseline_commit: '465d93ca8501b387db89563444f1bdf25fec5650'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 路线已经独立，但缺少可查询的唯一验证处置与去重共享证据；消费者仍容易把路线、测试引用或计划准入当成完成。

**Approach:** 建立按 Requirement 唯一的 `requirement_verification` 和按 `(requirement_id, evidence_id)` 唯一的 `requirement_evidence`，沿用路线投影与可信 planning trace。统一投影 `accounted`、`satisfied` 和缺口，保留旧处置、授权与证据。

## Boundaries & Constraints

**Always:** 新字段贯穿默认增量生成、合并、修复、checkpoint、trace、下一轮 seed 和 Knowledge；先机器验证。旧产物只读迁移、保存原字段与 hash，不原地修改既有 checkpoint。

**Ask First:** 无；按 AD-6 落实已批准的分离记账，不改变外部产品范围。

**Never:** 不修改 GDD、Requirement、任务三联、Capability、正式 MVG manifest 或游戏文件；不调用收费模型、Godot、远程 Git；不将测试代码存在或计划通过解释为 runtime_verified；不通过复制路线或证据增加完成计数。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
| --- | --- | --- | --- |
| SHARED | 一个 Requirement 两条路线、同一证据 | 两条路线、一条权威验证、一条去重证据；完成至多计一次 | N/A |
| DISPOSITIONS | flow / other_verification / deferred / source_gap | 独立输出 accounted/satisfied；前两者有全部权威证据才满足，deferred 未满足且保留授权，source_gap 阻断完成 | 不把计划测试提升为证据 |
| BAD_EVIDENCE | 重复键、未知 ID、空行为、范围错误、未准备/漂移来源 | 进入语义准入前拒绝并定位对象 | 接受前驱不变 |
| LEGACY | 旧 coverage 含 owner、授权和 verification_ref | 无损迁移、处置及已有真实证据守恒；缺证据明确未满足 | 不能从 flow/test 列表猜出已验证 |

</frozen-after-approval>

## Code Map

- `scripts/python/_mvg_requirement_routes.py` -- 复用 Story 3.1 的 legacy 投影、可信 trace 与路线键；不重复迁移链。
- `scripts/python/_mvg_requirement_accounting.py` -- 新共享 schema、无损投影、唯一键/证据校验及汇总；以纯函数统一计数语义。
- `scripts/python/_mvg_planning_review.py` -- `coverage_errors`、`prepared_evidence_errors`；复用 prepared index 的 files/authority_inputs 与真实副本 hash 校验。
- `scripts/python/_mvg_capability_generation.py` -- `append_output_schema`、`request`、`review_projection`、`complete_scope_context`、`repair_scope_errors`；新处置仅新增 Requirement，累计证据可服务已有路线。
- `scripts/python/_mvg_capability_append.py`, `scripts/python/plan_mvg.py` -- `merge_append`、`preservation_errors`、`merge_planning_segments`、`validate_proposal`、`seed_proposal` 的实际链路。新字段随 proposal 完整写入正式 trace；正式 runtime manifest/delta 协议不扩张。公共恢复保留旧 hash。
- `scripts/python/_project_health_mvg_versions.py`, `scripts/python/_project_health_planning.py` -- 复用 Story 3.1 的 manifest path/hash 绑定 trace；同一 accounting 汇总供页面消费，正式运行证据仍由 `with_runtime_evidence` 授权。
- `scripts/python/tests/test_mvg_requirement_accounting.py` -- 矩阵、默认生成、累计共享和可信 trace/Knowledge 验证；复用 append、planning contract、additive verification 的离线夹具。
- `docs/adr/ADR-0005-quality-gates.md` -- Accepted，门禁与日志依据。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/python/_mvg_requirement_accounting.py` -- 冻结最小 schema、迁移与纯计数 -- 唯一处置及共享证据可独立查询。
- [x] `scripts/python/_mvg_capability_generation.py`, `scripts/python/_mvg_capability_append.py`, `scripts/python/plan_mvg.py`, `scripts/python/_mvg_planning_review.py` -- 接通默认生成和累计保护 -- 非孤立 helper。
- [x] `scripts/python/_project_health_mvg_versions.py`, `scripts/python/_project_health_planning.py` -- 发布可信记账汇总 -- 不授予运行时状态。
- [x] `scripts/python/tests/test_mvg_requirement_accounting.py` 及受影响夹具 -- 验证矩阵及实际生成/持久化 -- 防止重复计数与证据丢失。
- [x] `workflow.md`, `.agents/skills/plan-mvg/SKILL.md`, `docs/workflows/mvg-integration-acceptance.md` -- 同步当前字段与计数边界。

**Acceptance Criteria:**
- Given shared evidence supports distinct routes, when accounting is projected, then the Requirement has one authoritative disposition and each evidence pair is counted once with its covered behavior and routes.
- Given the four dispositions, when reported, then accounted and satisfied are separate, source_gap blocks planning completion, and planned verification never grants runtime acceptance.

## Design Notes

最小验证行保留原处置及 owner/authority/rationale 字段，增加引用的 `evidence_ids`。证据行使用 requirement_id/evidence_id/source_ref/covered_behavior/flow_ids/test_ids；来源 hash 由准备索引核验，不信任模型自报。明确区分拟议测试义务与现存权威来源，代码存在不等于运行通过。source_gap 可以登记处置（accounted），但 satisfied=false、planning_complete=false。

实施时先确定并固化最小证据类型/有效性契约：`implementation_reference` 只说明代码或测试存在，不能满足验证；`verification_record` 必须解析到冻结的明确验证记录并解释覆盖行为；`runtime_acceptance` 仅接受现有正式 MVG receipt 的 manifest/revision/status 绑定。允许文档型非运行时验证记录，不按文件后缀猜测已通过。`satisfied` 仅为对应 Requirement 的证据满足投影，不提升整个 MVG 的 `runtime_verified`。证据字段的可选值用显式 null/空数组保持 CLI 严格 schema 可用，不接受模型自报 satisfied/runtime_verified。

`requirement_verification` 是新投影权威；旧 coverage 兼容读取必须无损且与显式新字段一致，不能产生第二个可独立漂移的权威。缺字段才迁移，显式坏字段不得静默回填。旧 flow 行无文件证据，不能靠迁移制造 satisfied。旧 other_verification 原 fragment 与授权字段保留；证据共享必须说明行为和路线，所有路线须属于该 Requirement。下一轮从匹配正式 trace 读取既有记账；找不到可信来源则不猜已完成。只增加记账投影，不变更现有运行时验收规范。

沿用 Story 3.1 的协议绑定方式为新 run 冻结 accounting 协议，prepared index/run state 必须一致；删除新字段不能降级。旧准备产物和 checkpoint 不原地升级。默认 append 可生成四种处置；flow 仍遵守已有 owner 关系，other_verification/deferred 保留既有准备证据/授权门，source_gap 明确未完成。每轮只新增当前 `new_requirement_ids` 的权威记录；允许向已有 Requirement 增加经验证据，不能覆盖已接受行或共享证据。新证据参与 review 闭包和完整来源传输，不能因缩小投影丢掉关联 owner 或 flow。

全部验证使用离线 fake runner，证据放 `logs/ci/2026-10-15/story-3-2/`，实现代理不自行提交。更全面的准入/重放/最终审计守恒归 Story 3.3，本项必须保证新增字段本身在实际链路中有效。

审查补充：`implementation_reference` 保留可追溯引用，不属于必须运行通过的权威证明集合；追加有效证明后允许满足。新证据直接扩展 Requirement 审查闭包，即使该 Requirement 没有 flow。新 trace 记录 accounting 协议，不能删除字段后降级；显式权威行须覆盖已有 coverage。来源统一 canonical 仓库相对路径，独立读取规范化 UTF-8 内容核对身份并保留原字节 hash 审计。正式运行凭据固定读取同运行目录的 `input-manifest.json` 和 `snapshot/<manifest>`，复用正式 snapshot digest 与 manifest 字节 hash，核对 main/workspace 身份及冻结目标路径；不得借用 Capability 生成版本或后来的展示 commit 作为运行版本。

## Verification

- `py -3 -m unittest discover -s scripts/python/tests -p test_mvg_requirement_accounting.py` -- expected: OK。
- 受影响 planning contract、additive verification、Requirement routes 和 Knowledge 定向回归 -- expected: OK。
- 默认 public generate/checkpoint/trace/下一轮 seed 离线定向测试 -- expected: OK，无真实模型调用。
- `py -3 -m py_compile` 检查所有改动模块；`git diff --check` -- expected: SUCCESS。

结果：初始定向回归 222 项中 219 项通过，三个旧 Knowledge 模拟输出夹具补必填字段后定向通过；三层审查发现的直接补丁全部修复。修后 merge/envelope 38 项通过，公共 generate/checkpoint/apply/replay/Knowledge/next-seed 1 项通过；主代理额外复验 4 项通过。main/workspace 正式回执使用真实生产者的离线结构；共享证据去重、四处置、坏来源和 legacy 矩阵均已通过。编译及 whitespace 检查通过。原始失败和修后日志均保留在 `logs/ci/2026-10-15/story-3-2/`，逐条对应关系见 `verification-progress.md`，审查处置见 `review-triage.md`。未执行付费模型、Godot 或远程 Git。

## Suggested Review Order

**权威处置与证据**

- 先看统一记账校验与 coverage 一致性。
  [\_mvg_requirement_accounting.py:220](../../scripts/python/_mvg_requirement_accounting.py#L220)
- 正式回执绑定真实 snapshot 与 manifest 字节。
  [\_mvg_requirement_accounting.py:54](../../scripts/python/_mvg_requirement_accounting.py#L54)
- 独立来源校验与唯一满足计数。
  [\_mvg_requirement_accounting.py:418](../../scripts/python/_mvg_requirement_accounting.py#L418)

**实际生成与消费**

- 审查闭包包含无 flow 的新增证据。
  [\_mvg_capability_generation.py:51](../../scripts/python/_mvg_capability_generation.py#L51)
- 累计合并保留处置和旧证据。
  [\_mvg_capability_append.py:83](../../scripts/python/_mvg_capability_append.py#L83)
- Knowledge 复用可信 trace，不授予运行成功。
  [\_project_health_mvg_versions.py:13](../../scripts/python/_project_health_mvg_versions.py#L13)

**验证与边界**

- 离线矩阵覆盖共享、迁移、异常及公共链路。
  [test_mvg_requirement_accounting.py:49](../../scripts/python/tests/test_mvg_requirement_accounting.py#L49)
- 工作流说明区分 planned、satisfied 与 runtime。
  [mvg-integration-acceptance.md:29](../../docs/workflows/mvg-integration-acceptance.md#L29)
