---
title: 'Story 3.3：统一判定Task来源及完整适用计划集合'
type: 'feature'
created: '2026-11-23'
status: 'done'
baseline_commit: '683e2abc032cf1027a663b39aca2177a1614ca59'
story_key: '3-3-统一判定task来源及完整适用计划集合'
review_loop_iteration: 1
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-3-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 缺公共 Task 来源与适用计划解析器；凭缺 B 痕迹退回旧 A 漏控篡改，共享 Task 易漏多计划责任。
**Approach:** 交付纯只读零落盘 _b_route_task_resolver.py 与 b-route-task-origin，先验 pending 与已提交 policy/catalog/origins 全反向关系，判 A、B、explicit_not_enabled_a 或阻断，汇总适用集合与 applicable_set_digest，不授实施权。

## Boundaries & Constraints

**Always:** 无 --report 时 100% 零目录/锁创建（双读 Observations + 只读 operation_state_graph/_legacy_pending）；旧 capability-apply.pending.json/未完旧 journal（无 scope_id）及已入 commit.json 或存 commit.pending.json 的操作保守阻断 PENDING/UNPUBLISHED，未 apply 的 prepared/reserved 仅阻断重叠业务 scope（task/plan/flow/requirement/command/state）；经 published_bundle 与 TaskJoinContext 全验 policy.v1.json、catalog.v1.json、task-origins.v1.json、receipt 及实际文件；汇总 origins.tasks、catalog.task_index 与活跃 bindings 三方一致且修订可验，返计划/绑定/Requirement 处置/Flow 闭包及 applicable_set_digest；判 A 须反向零 B 义务、无残留 B 引用标签、可读匹配 policy.frozen_a_refs（frozen_a_inventory/authority）冻结 ID/投影(仅排 status/subtasks[].status)/来源 scope 及 allowed_a_operations（无 logs/ clone 中 B 凭正式链通过，候选 A 缺冻结归档必阻断）；未启用仅零 B 痕迹且 ADR-0040 成立时返回；六字段 Diagnostic，execution_authorized/readiness/runtime_verified 恒 false。
**Ask First:** 改 6 FORMAL、扩 ReasonCode/Stage、复制 3.5 InputSet、授 Ch6 实施权或改默认路由。
**Never:** 无 --report 建 logs/locks；凭无 trace/done/旧 readiness 或缺归档猜 A；删 B 归属/篡改策略/缺行/矛盾落为无义务；凭标签豁免非 Flow；写正式记录或修损坏证据。

## I/O & Edge-Case Matrix

| Scenario | Input | Expected | Error |
|---|---|---|---|
| B_MULTI | 单/多计划或新入计划 | 三方一致，返 route=B、引用/处置与新 applicable_set_digest | 缺行/矛盾/删归属 MAPPING_MISMATCH 或 CONFLICT |
| FROZEN_A | 零 B 义务且可读匹配冻结 ID/投影/来源/操作 | 返 route=A（活 status 推进不破匹配，done 不免检） | 新增、漂移、禁操作或缺冻结归档阻断，须走 B |
| CLONE_PEND | 无 logs/ clone；旧 pending/入 commit.json；未 apply 异业务 scope | clone 零写验 B 链；未完阻断；异业务 scope prepared 放行 | 混合态、未知或重叠 pending 报 PENDING/UNPUBLISHED |
| NOT_EN | 零 B 痕迹且 ADR-0040 未启用 | 返 route=explicit_not_enabled_a 与原边界 | 缺治理而有痕迹或 ADR 失效阻断 |
| NON_FLOW | 合法非 Flow 或自由标签 N/A | 返 route=B 及处置，标明须下游定义/影响核对 | 禁标签豁免，定义缺失阻断 |

</frozen-after-approval>

## Code Map

- `_b_route_records.py:364,928,1118,1326`、`_b_route_commit.py:748`、`_b_route_operation_scope.py:17,55,145` -- join/反向/clone/scope
- `_b_route_protection.py:35,93,391,696`、`_b_route_preflight.py:58,175,534,708`、`_b_route_record_owners.py:26` -- 零写/投影/冻结A/pending
- `policy.schema.json:16,51`、`origins.schema.json:16,55`、`chapter3_task_scope.py:12`、`dev_cli.py:620` -- 策略/来源/CLI

## Tasks & Acceptance

**Execution:**
- [x] `scripts/python/_b_route_task_resolver.py` -- 零写分类、反向、冻结 A、pending/clone 与 applicable_set_digest（AC-1..5）
- [x] `scripts/python/resolve_b_route_task_origin.py`、`dev_cli.py`、`dev_cli_builders.py`、`_b_route_adoption_review.py` -- CLI 与策略锚定（AC-1,3,5）
- [x] `scripts/python/tests/test_b_route_task_resolver.py`、`run_gate_bundle.py`、`.github/workflows/b-route-runtime-deterministic.yml`、`test_b_route_runtime_ci.py` -- 单测门禁（AC-1..5）
- [x] `docs/workflows/b-route-task-origin-resolution.md`、`AGENTS.md`、`stable-public-entrypoints.md`、`script-entrypoints-index.md` -- 文档（AC-5）

**Acceptance Criteria:**
- AC-1..2: Given 已启用，When 零写查询，Then 先验治理与语义 pending，匹配完整反向或可读冻结 A 边界。
- AC-3..5: Given 多计划、clone 或非 Flow，When 汇总，Then 返一致适用集合与六字段诊断，不授实施权。

## Spec Change Log

## Design Notes

禁在只读查询调 initialize_lock_namespace；frozen_a_refs 解析 1.5 保护快照/清单与 chapter3-task-scope.json；applicable_set_digest 汇总排序 (task_id, plan_refs, binding_refs, source_refs, resolved_definitions, dispositions)。

## Verification

- `py -3 -B -m unittest scripts.python.tests.test_b_route_task_resolver -v`
- `py -3 -B -m unittest scripts.python.tests.test_b_route_runtime_ci -v`
- `py -3 -B -m unittest scripts.python.tests.test_b_route_records -v`
- `py -3 -B -m unittest scripts.python.tests.test_b_route_adoption_journal -v`
- `py -3 -B -m unittest scripts.python.tests.test_b_route_3b_70k_segmented.TrackBSegmented70kTests.test_01_story25_ast_and_semantic_lock_guard -v`
- `py -3 -B scripts/python/dev_cli.py b-route-task-origin --help`

### Step 4 Review & Verification Record

- **三层审查分诊与收口：** `0` 项 `intent_gap`、`0` 项 `bad_spec`、`5` 组 `patch`（`P-01`..`P-05`）全部修复收口、`0` 项 `defer`，分诊证据归档于 `logs/ci/2026-11-23/story-3-3-step4-triage.md`：
  - `P-01`：按任务作用域收口 `resolved_definitions` 与 `applicable_flow_closure`（拉入映射 Flow 的 `requirement_ids`、消除裸 `next(...)`、取消全计划倾倒），`non_flow_summary` 下游核对标记设为 `bool(has_non_flow or task_na_labels)`。
  - `P-02`：阻断 `origins.tasks`/`catalog.task_index`/`catalog.definition_owners` 重复键，去重 obligations/implementation_objects，核验 `evidence_ids` 与非 `logs/` 外部引用（保留 clean clone receipt 封存 `logs/`），任意 `docs/planning/b-route` 文件均视为 B 痕迹并全验 `managed_traces`，补齐 `adr_diag` 的 `entity_id`。
  - `P-03`：投影前经 `protection._task_state` 验活状态枚举，强制 `capture_complete is True`、非 `historical_evidence_not_proven` 与 `source_set` 实测比对；支持 Markdown `authority` 与完整 `protection-input` 校验、`chapter3-task-scope` `master_path` 约束、`a_write_allowed=False` 拦截非只读操作，且候选 A 任意 `CodecError` 均置 `route_required="B"`。
  - `P-04`：递归扫描子任务与全部引用/标签字段的 B 痕迹；pending 观测覆盖旧目录字节并在在途 commit 抛错前记录 `initial_graph_bytes` 与 `blocking_operations`，空 `business_scopes` 报 `PENDING`；双读漂移基于 `_base_result` 重置；`write_report` 用 UUID 临时文件独占原子写入；CLI 前置校验 `--root` 并对报告写失败输出干净阻断结果。
  - `P-05`：在 `test_b_route_task_resolver.py` 补齐非 Flow 空闭包、多 Flow 兄弟隔离、`source_gap`、`a_write_allowed=False`、`protection-input`、clean clone 候选 A `route_required="B"`、双读重置、非法 `--root` 及 `dev_cli.build_parser().parse_args` 透传回归测试。
- **最终核验记录：** 见 `logs/ci/2026-11-23/story-3-3-final-verify.log`（`test_b_route_task_resolver` 11/11 `rc=0` 0 跳过；`test_b_route_runtime_ci` 12/12 `rc=0`；`test_b_route_records` 100 运行 `OK` `rc=0`；`test_b_route_adoption_journal` 11/11 `rc=0`；`test_01_story25_ast_and_semantic_lock_guard` 1/1 `rc=0`；`dev_cli_help` `rc=0`；7 份 FORMAL schema 0 diff、15 文件 UTF-8 无 BOM/0 Emoji、冻结块 15-38 行未改、`scripts/` 零 `__pycache__`/`.pyc`）。

## Suggested Review Order

**核心只读入口与主分类流程**

- 独立零写 CLI 参数校验、执行分发与错误隔离输出
  [resolve_b_route_task_origin.py:77](../../../scripts/python/resolve_b_route_task_origin.py#L77)

- 统一来源分类主流程、三联状态校验与双读漂移重置
  [_b_route_task_resolver.py:1535](../../../scripts/python/_b_route_task_resolver.py#L1535)

- 可选 `--report` 独占原子落盘，防覆盖与路径逃逸
  [_b_route_task_resolver.py:1946](../../../scripts/python/_b_route_task_resolver.py#L1946)

**Pending 语义、痕迹扫描与 B 路线适用集合**

- 递归扫描任务及子任务残留 B 引用与自由豁免标签
  [_b_route_task_resolver.py:240](../../../scripts/python/_b_route_task_resolver.py#L240)

- 只读 pending 核查、在途 commit 阻断与业务 scope 过滤
  [_b_route_task_resolver.py:359](../../../scripts/python/_b_route_task_resolver.py#L359)

- 经 `Observations` 验非 `logs/` 外部引用并保 clean clone 封存
  [_b_route_task_resolver.py:531](../../../scripts/python/_b_route_task_resolver.py#L531)

- 三方一致性校验、任务级定义闭包、非 Flow 约束与摘要
  [_b_route_task_resolver.py:565](../../../scripts/python/_b_route_task_resolver.py#L565)

**冻结 A 边界核验与策略密码学锚定**

- 冻结 A 边界全验、`protection-input` 校验与强制 `route_required="B"`
  [_b_route_task_resolver.py:1156](../../../scripts/python/_b_route_task_resolver.py#L1156)

- 将 `_b_route_task_resolver.py` 纳入 `policy_observations` 密码学锚定
  [_b_route_adoption_review.py:231](../../../scripts/python/_b_route_adoption_review.py#L231)

**CLI 接线、确定性门禁、测试与文档**

- 注册 `dev_cli.py b-route-task-origin` 只读命令分发入口
  [dev_cli.py:634](../../../scripts/python/dev_cli.py#L634)

- 构建 `-B` 子进程命令并拒绝 `--write`/`--apply` 参数
  [dev_cli_builders.py:910](../../../scripts/python/dev_cli_builders.py#L910)

- 将统一来源解析单测纳入 `b-route-runtime` 确定性门禁
  [run_gate_bundle.py:170](../../../scripts/python/run_gate_bundle.py#L170)

- CI 工作流路径触发新增 `resolve_b_route_task_origin.py`
  [b-route-runtime-deterministic.yml:52](../../../.github/workflows/b-route-runtime-deterministic.yml#L52)

- 覆盖 5 行矩阵、clean clone、多 Flow 与 CLI 回归单测
  [test_b_route_task_resolver.py:675](../../../scripts/python/tests/test_b_route_task_resolver.py#L675)

- Runtime CI 护栏校验新解析器测试与入口注册一致
  [test_b_route_runtime_ci.py:38](../../../scripts/python/tests/test_b_route_runtime_ci.py#L38)

- 统一 Task 来源解析 Owner 文档与 Windows 示例说明
  [b-route-task-origin-resolution.md:7](../../../docs/workflows/b-route-task-origin-resolution.md#L7)

- 根路由与公共入口索引登记 `b-route-task-origin` 边界
  [AGENTS.md:38](../../../AGENTS.md#L38)

- 公共稳定入口清单补录只读解析器契约边界
  [stable-public-entrypoints.md:588](../../../docs/workflows/stable-public-entrypoints.md#L588)

- 脚本入口索引登记 `resolve_b_route_task_origin.py` 说明
  [script-entrypoints-index.md:1818](../../../docs/workflows/script-entrypoints-index.md#L1818)
