---
title: 'Story 3.6：绑定真实MVG义务或合法其他验证依据'
type: 'feature'
created: '2026-11-23'
status: 'done'
baseline_commit: '8af9d4cc1658c2d502b7f3d501065680876a2689'
story_key: '3-6-绑定真实mvg义务或合法其他验证依据'
review_loop_iteration: 1
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-3-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 缺 Stage-5 义务绑定，Flow/回归易被旧/错 manifest 或标签漏掉，非 Flow 被迫造 Flow 或凭空 N/A，未知影响被缩窄或逼未来提前实现，且共享重计、旧 done 盖新义务。
**Approach:** 交付 _b_route_stage5_obligations.py 与 b-route-stage5-obligations，结合 InputSet、manifest/delta 防削弱与共享提交发 stage="5" 绑定及投影。

## Boundaries & Constraints

**Always:** 具已提交 stage="4"|"5" 绑定，Task 经 3.3 判 B 且候选经 3.5 resolve_input_set(含候选槽与 pre-sync)通过，守 task_id 集、Stage-4 四部分与对象守恒(兼容 2.8 补偿，保 STAGE4_OBL_PREFIX 免误报 return_stage="4")；Flow 或担 MVG 交接/集成/回归(禁凭标签免)必绑有效 manifest(验 raw_digest、manifest_sha256 与解耦校验；可选经 public-sync-journal 同步过 update_mvg_baseline 审阅的 delta)、Flow/test/Req 责任；obligations 的 requirement_ids/flow_ids 属 plan.requirements 与已覆盖 catalog.definition_owners 子集(非 catalog 与未来 Flow 记入 STAGE5_OBL_PREFIX 及 manifest_refs/test_ids，防 MAPPING_MISMATCH)；非 Flow 仅在 3B applicability 理由、adoption_proof_refs、真实 other_verification_refs 与 InputSet 齐备且零 Flow 影响时免造 Flow/manifest，标签/空值/N/A/source_gap/删依据阻断；非 Flow 触达 Flow(source_paths/contract_ref/测试/消费链)绑回归，反向未知按完整累计范围保守扩大(不等 Epic 4)，分 existing_required、current_new、out_of_scope_future 三类，禁缩窄或逼未来实现，不可证阻断；按 producer/consumer/integration_only_owner 验交接与依赖，整合 owner 不求 API 且禁造自锁，保前置并区分未实现(planned/未 done 合法)与定义缺失(阻断)；共享沿唯一 requirement_verification、(requirement_id,flow_id)与去重键计数，新义务或 planned 测试不被旧 done 覆盖(标 requires_reverification=true，禁复制 status 入权威)，减义务必具规格 authority_ref 与 reviewed 理由；经 _b_route_commit.py 增修订、保他计划引用并末推 catalog.v1.json，readiness/runtime_verified/default_b_enabled 恒 false。
**Ask First:** 改 7 FORMAL、扩 ReasonCode/Stage、加 Epic 4 选择性执行或改 3B plan。
**Never:** 跳 Stage 4；凭标签/空值/N/A 免验；缩窄或逼未来实现；造自锁；旧 done 盖新义务；无审阅减义务；当 readiness/运行证据。

## I/O & Edge-Case Matrix

| Scenario | Input | Expected | Error |
|---|---|---|---|
| FLOW_BIND | Flow/实影响+manifest/delta | 发 stage="5"、manifest_refs、责任并推 catalog | 缺/旧/错 manifest 或漏测阻断 |
| NONFLOW_OK | 非 Flow+理由/证明/other_verification_refs+零影响 | 绑非 Flow 义务免造 Flow/manifest | 标签/空值/N/A/source_gap 阻断 |
| IMPACT_EXP | 非 Flow 触达 Flow 或反向未知 | 绑回归或扩至累计范围并分三类 | 缩窄、逼未来实现或不可证阻断 |
| ROLE_DEP | 三类角色+未 done/planned | 验交接与依赖，无自身 done 死锁 | 抹前置或定义缺失阻断 |
| DEDUP_RET | 共享、旧 done 遇新义务或减义务 | 去重不重计，标重验，审阅规格准退休 | 重计、无依据减义务或 pending 阻断 |

</frozen-after-approval>

## Code Map

- `binding.schema.json:19,254`、`_b_route_records.py:934` -- Stage-5/子集
- `_b_route_chapter4_binding.py:391,1229`、`_b_route_task_resolver.py:412` -- Stage-4/sync
- `_b_route_input_set.py:952,1458,2737` -- manifest/InputSet
- `_mvg_manifest.py:37,179`、`update_mvg_baseline.py:46,88` -- 角色/影响/防削弱
- `_b_route_commit.py:97,1060`、`_b_route_commit_projection.py:71` -- 提交/投影

## Tasks & Acceptance

**Execution:**
- [x] `scripts/python/_b_route_stage5_obligations.py` -- 辅助 schema、核验、三类影响、无自锁、去重、防削弱、提交恢复与锚定（AC-1..5）
- [x] `scripts/python/bind_b_route_stage5_obligations.py` -- CLI 入口（AC-1..5）
- [x] `scripts/python/tests/test_b_route_stage5_obligations.py` -- 单测与 CI（AC-1..5）
- [x] `docs/workflows/b-route-stage5-obligations.md` -- 说明与索引（AC-5）

**Acceptance Criteria:**
- Given Flow/实影响或非 Flow Task，when 预览或绑 Stage-5，then 实影响绑 manifest 与三类责任，零影响绑 other_verification_refs，缺/旧 manifest、N/A 或缩窄阻断。
- Given 多角色、共享、旧 done 或减义务，when 提 stage="5"，then 无自锁、不重计、旧 done 不盖新义务、无审阅禁减义务，末推 catalog 且不授 readiness/运行通过。

## Spec Change Log

## Verification

- `py -3 -B -m unittest scripts.python.tests.test_b_route_stage5_obligations scripts.python.tests.test_b_route_runtime_ci -v`
- `py -3 -B scripts/python/dev_cli.py b-route-stage5-obligations --help`

### Step 4 Review & Verification Record

- 审查分类归档：`logs/ci/2026-11-23/story-3-6-step4-triage.md`（`intent_gap=0`、`bad_spec=0`、`patch=7`、`defer=0`）。
- 补丁闭环摘要：`P-01`（`detected_non_authoritative_labels` 全计划无条件阻断 `mvg:N/A` 标签，非 Flow 严格校验 `adoption_proof_refs`、实质性 `applicability`/`requirement_verification` 理由、`evidence_source_refs`、`other_verification`/`authority` 引用覆盖及 Step-11 保留/审阅退休）、`P-02`（`_collect_task_touched_paths` 补采 `acceptance[]` `Refs:` 与 `test_refs`，自动发现并解耦校验仓库现有 `docs/testing/mvg/*.json`，对齐 Flow 计划 `touched_consumer_chains` 跨 manifest 匹配）、`P-03`（由 `STAGE5_OBL_PREFIX` 还原 `prior_effective_flows` 用于 `remove_flow` 防削弱与 `is_new_obl`，补齐单 Task 义务守恒与 `remove_task_obligation`，追踪 `newly_assigned_task_ids` 并阻断 done Task 在新增/修改/重分配义务或 planned 测试上的 `skip_reverification=True`，拒绝 `logs/` 退休 `authority_ref` 并持久化 `OwnedRef(owner="authority")` 与 `retired_items`）、`P-04`（CLI 入口前置 `_guard_stage5_operation` 拒绝非 Stage-5 操作并报 `SCHEMA_MISMATCH`，`--stage read` 逐项复验 `manifest_refs` 的 `raw_digest` 与解耦 manifest 结构）、`P-05`（`_b_route_input_set.py` 修正候选叠加层对共享 manifest 路径的优先权与 `_observe_owned_ref_items` 传递，解析 `stage5:obl:v1|` `non_catalog_flow_ids`，拆分 `stage4_obligation_meta` 使 Stage-4→Stage-5 审阅退休精确归因 `return_stage="5"`）、`P-06`（`policy_observations()` 锚定 `_mvg_manifest.py` 与 `update_mvg_baseline.py`，`.github/workflows/b-route-runtime-deterministic.yml` 补全路径过滤，文档补齐 `validate_operations` 与 `compensation.build` 说明）、`P-07`（补齐 `P-01`..`P-06`、多操作 `public_sync_entries`、补偿保留/推进 `stage="5"` `binding_ref` 及跨计划归因单测至 15 项并全绿，完成 8 项终验与文档收口）。
- 最终验证日志：`logs/ci/2026-11-23/story-3-6-final-verify.log`（每项原始日志位于 `logs/ci/2026-11-23/s36-checks/`）：
  - `test_b_route_stage5_obligations`：15/15 通过（0 skipped）
  - `test_b_route_input_set`：14/14 通过（0 skipped）
  - `test_b_route_task_resolver`：11/11 通过（0 skipped）
  - `test_b_route_runtime_ci`：12/12 通过（0 skipped）
  - `test_b_route_records`：100 运行全部通过（14 skipped 为本机非管理员 symlink 跳过）
  - `test_b_route_adoption_journal`：11/11 通过（0 skipped）
  - `test_01_story25_ast_and_semantic_lock_guard`：1/1 通过（0 skipped）
  - `dev_cli.py b-route-stage5-obligations --help`：`rc=0`

## Suggested Review Order

### 公共 CLI 入口与分发

Stage-5 操作类型守卫、10 阶段分发与 `--stage read` manifest 实证复验
  [bind_b_route_stage5_obligations.py:103](../../../scripts/python/bind_b_route_stage5_obligations.py#L103)
  [bind_b_route_stage5_obligations.py:123](../../../scripts/python/bind_b_route_stage5_obligations.py#L123)
统一 `dev_cli` 子命令路由与命令构建器
  [dev_cli.py:670](../../../scripts/python/dev_cli.py#L670)
  [dev_cli.py:720](../../../scripts/python/dev_cli.py#L720)
  [dev_cli_builders.py:992](../../../scripts/python/dev_cli_builders.py#L992)

### 核心 Stage-5 义务绑定、影响扩大与防削弱

辅助操作与请求 Schema（含 `remove_task_obligation`）
  [stage5-obligations-operation.schema.json:1](../../../docs/planning/b-route/schemas/stage5-obligations-operation.schema.json#L1)
`public-sync-journal` 原始字节同步与 Stage-5 语义提取
  [_b_route_stage5_obligations.py:402](../../../scripts/python/_b_route_stage5_obligations.py#L402)
  [_b_route_stage5_obligations.py:710](../../../scripts/python/_b_route_stage5_obligations.py#L710)
解耦 manifest 校验、`OwnedRef` 实证与 Task 触达路径提取
  [_b_route_stage5_obligations.py:897](../../../scripts/python/_b_route_stage5_obligations.py#L897)
  [_b_route_stage5_obligations.py:1104](../../../scripts/python/_b_route_stage5_obligations.py#L1104)
核心 `build`（Flow/非 Flow 校验、三类影响扩大、角色交接无自锁、去重与防削弱退休）
  [_b_route_stage5_obligations.py:1180](../../../scripts/python/_b_route_stage5_obligations.py#L1180)
`prepare`/`inspect`/共享提交上下文与双态观测核验
  [_b_route_stage5_obligations.py:3160](../../../scripts/python/_b_route_stage5_obligations.py#L3160)
  [_b_route_stage5_obligations.py:3380](../../../scripts/python/_b_route_stage5_obligations.py#L3380)

### InputSet、共享提交与操作治理联动

Stage-5 非 catalog Flow 解析、候选叠加层优先权与 `return_stage="5"` 归因
  [_b_route_input_set.py:74](../../../scripts/python/_b_route_input_set.py#L74)
  [_b_route_input_set.py:2623](../../../scripts/python/_b_route_input_set.py#L2623)
多操作 `public_sync_entries` 校验、提交投影与 journal 纳管
  [_b_route_adoption.py:579](../../../scripts/python/_b_route_adoption.py#L579)
  [_b_route_commit.py:101](../../../scripts/python/_b_route_commit.py#L101)
  [_planning_apply_journal.py:121](../../../scripts/python/_planning_apply_journal.py#L121)
  [_b_route_task_resolver.py:412](../../../scripts/python/_b_route_task_resolver.py#L412)

### 确定性测试、CI 锚定与说明文档

覆盖矩阵与 `P-01`..`P-07` 的 15 项确定性单测
  [test_b_route_stage5_obligations.py:1002](../../../scripts/python/tests/test_b_route_stage5_obligations.py#L1002)
确定性 CI 矩阵与路径过滤器测试
  [test_b_route_runtime_ci.py:38](../../../scripts/python/tests/test_b_route_runtime_ci.py#L38)
Story 3.6 命令契约、补偿兼容性与边界说明
  [b-route-stage5-obligations.md:1](../../../docs/workflows/b-route-stage5-obligations.md#L1)
