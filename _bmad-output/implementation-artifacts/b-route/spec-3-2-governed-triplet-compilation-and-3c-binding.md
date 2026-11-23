---
title: 'Story 3.2：受治理编译三联与3C绑定并保留当前任务状态'
type: 'feature'
created: '2026-11-22'
status: 'done'
baseline_commit: 'e3e048a131643144b33cf2cd5eba41e496021429'
story_key: '3-2-受治理编译三联与3c绑定并保留当前任务状态'
review_loop_iteration: 1
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-3-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 3.1 仅预览，缺三联编译与 3C 绑定。
**Approach:** 接 producer="task_compilation" 与 b-route-task-compile 九阶段，复编译与共享 journal/commit/recover，定真 ID、两段锁合活 status、末推 catalog.v1.json。

## Boundaries & Constraints

**Always:** 消费 ok/stable 3.1 与请求，重验 3A verify_current_proof、3B read_committed 及保护/manifest 防削弱；经 compile_task_triplet/build_taskmaster_tasks 与 TaskJoinContext，仅 prepare 配 taskmaster_id(max+1)+NG/GM 入 allocations 并锁三联投影(仅排 status/subtasks[].status；binding/origins 用 immutable_bytes)，写 semantic_review_tier 与回链；apply 初入旧+新 resource_scopes 锁写 commit.json 时重读活三联、验投影合活 status 封存 before/after/projection_digest 入 commit.json 与 commits/<op>.json，冻结后再变阻断，末推 catalog.v1.json；_PublishedBundle.receipt 识别新 current_receipts 接替的三联投影并按单 Task 验绑定投影，无当前 receipt 直改 tasks*.json 阻断；terminal_valid 返 noop=True 留活 status 容他任务，recover 前滚；辅助 schema 仅入 AUXILIARY（6 FORMAL 不动）；保三授权 false、旧 A chapter3_task_scope、Taskmaster 状态权与 manifest，Ch6 需 Ch4-5，事件写 logs/**。
**Ask First:** 改 FORMAL、扩 ReasonCode/Stage、改投影排除集、启 readiness/默认 B。
**Never:** 另造状态机/journal；直改 tasks*.json 取证；origins/catalog 抄 status 或降 A；单文件/无 pending 证完成；放行损坏/capability-apply.pending.json/无据 retire/削弱；吞活 status 或承诺提速。

## I/O & Edge-Case Matrix

| Scenario | Input | Expected | Error |
|---|---|---|---|
| HAPPY | 有效 3.1/3A/3B | prepare 定 ID+投影，发三联/3C/commit，末推 catalog | 验真/直改阻断 |
| SHARED | 共享/跨计划 | origins 合并、task_index 全、同 Flow、新 receipt 接替不破旧计划 | 碰撞 CONFLICT |
| LIVE | commit.json 前 status 推进 | apply 锁内验投影合活 status 封存证明 | 定义变/冻结后变 CONFLICT |
| RECOVER | 中断/重调 | recover 前滚；同内容 noop=True 留活 status 容他任务 | 异内容/篡改 CONFLICT |
| BLOCK | 损坏/pending/无据 retire/削弱 | 写前阻断，保旧 A/manifest | 零改写，六字段诊断 |

</frozen-after-approval>

## Code Map

- `_b_route_schema_resources.py:13`、`_b_route_operation_scope.py:17,55`、`_b_route_protection.py:93`、`_b_route_records.py:364,901,1209,1345` -- schema/锁/跨计划接替
- `_planning_apply_journal.py:416,461`、`_b_route_commit_projection.py:88`、`_b_route_commit.py:512,607,759,899` -- 两段冻结/commit/recover
- `_b_route_task_preview.py:3205`、`compile_task_triplet.py:70`、`build_taskmaster_tasks.py:185`、`chapter3_task_scope.py:12`、`dev_cli.py:610` -- 3.1/编译/旧A/CLI

## Tasks & Acceptance

**Execution:**
- [x] `docs/planning/b-route/schemas/task-compilation-operation.schema.json`、`_b_route_schema_resources.py` -- AUXILIARY（AC-1/3/5）
- [x] `scripts/python/_b_route_task_compilation.py`、`compile_b_route_tasks.py`、`dev_cli.py`、`dev_cli_builders.py` -- 适配与 CLI（AC-1..6）
- [x] `scripts/python/_b_route_records.py`、`_planning_apply_journal.py`、`_b_route_commit_projection.py`、`_b_route_commit.py` -- 两段合并/接替/recover/noop（AC-1..5）
- [x] `scripts/python/tests/test_b_route_task_compilation.py`、`test_b_route_runtime_ci.py`、`run_gate_bundle.py`、`.github/workflows/b-route-runtime-deterministic.yml` -- 单测门禁（AC-1..6）
- [x] `docs/workflows/b-route-task-compilation.md`、`AGENTS.md`、`stable-public-entrypoints.md`、`script-entrypoints-index.md` -- 文档（AC-6）

**Acceptance Criteria:**
- AC-1..2: Given 有效预览与请求，When 编译发布，Then 严 join、写 tier/回链、不降 A 不抄 status、新 receipt 接替不破旧计划、直改阻断。
- AC-3..4: Given 并发或恢复，When apply/recover，Then 两段合活 status 封存证明，冻结后冲突，重放 noop=True。
- AC-5..6: Given 治理门禁，When 核验，Then 阻断异常、catalog 末推、Ch6 需 4-5、事件写 logs/**。

## Spec Change Log

## Design Notes

prepare 冻 allocations 与三联投影(newrouge.b-route-task-definition.v1)，apply 合活 status 封存 raw+projection 入 commit.json；receipt 放行新 current_receipts 接替且绑定单 Task 投影一致的三联；事件落 logs/ci/b-route-task-compilation/<op>/events.jsonl。

## Verification

- `py -3 -B -m unittest scripts.python.tests.test_b_route_task_compilation -v`
- `py -3 -B -m unittest scripts.python.tests.test_b_route_commit_projection -v`
- `py -3 -B -m unittest scripts.python.tests.test_b_route_commit -v`
- `py -3 -B scripts/ci/run_b_route_windows_recovery_checks.py`
- `py -3 -B -m unittest scripts.python.tests.test_b_route_records -v`
- `py -3 -B -m unittest scripts.python.tests.test_b_route_runtime_ci -v`
- `py -3 -B -m unittest scripts.python.tests.test_b_route_3b_70k_segmented.TrackBSegmented70kTests.test_01_story25_ast_and_semantic_lock_guard -v`
- `py -3 -B scripts/python/dev_cli.py b-route-task-compile --help`

### Step 4 Review & Verification Record

- **三层审查分诊与收口（`Gemini 4 Carbon High`：`blind-hunter`、`edge-case-hunter`、`verification-gap`）：** `0` 项 `intent_gap`、`0` 项 `bad_spec`、`10` 项 `patch`（`P-01`..`P-10`）全部修复收口、`0` 项 `defer`，分诊证据归档于 `logs/ci/2026-11-22/story-3-2-step4-triage.md`：
  - `P-01`..`P-02`：`_b_route_adoption.validate_operations` 显式校验 `TASK_COMPILATION_SCHEMA` 分支；`_b_route_adoption_review.policy_observations` 密码学锚定 `_b_route_task_preview.py` 与 `_b_route_task_compilation.py`。
  - `P-03`..`P-04`：`_b_route_commit_projection._head_selections` 隔离 3C 共享容器 `file:` 作用域并按单 Task 维护 `binding_refs`；`_b_route_records._verify_superseded_task_projections` 支持三计划连续接替校验与虚拟化 `self.bytes`。
  - `P-05`..`P-06`：`_b_route_task_compilation` 补齐 `reuse` 回链与 `proposed_fields` 黑名单、严格依赖与 `lineage` 解析、子任务按 `id` 精确合并活 `status` 与视图枚举校验、锚定 `chapter3-task-scope.json` 及 3A/GDD 观测、兼容 `prepare->reserve` 活状态推进与发布后幂等重放、收敛 `inspect` 漂移诊断。
  - `P-07`..`P-10`：`_b_route_commit` 补齐单视图未改动识别与 `read_committed` 预写守卫；`compile_b_route_tasks.py --stage read` 校验 `terminal_valid` 并采用最佳努力事件写入；收紧 `task-compilation-operation.schema.json`；在 `test_b_route_task_compilation.py` 补齐全部回归断言。
- **最终核验记录：** 见 `logs/ci/2026-11-22/story-3-2-final-verify.log`（`test_b_route_task_compilation` 7/7 `rc=0`、0 跳过；`test_b_route_commit_projection` 9/9 `rc=0`；`windows_recovery_and_compensation_controls` 独立复跑 4/4 `passed` `rc=0`；`test_b_route_records` 100 运行 `OK` `rc=0`；`test_b_route_adoption_journal` 11/11 `rc=0`；`test_b_route_runtime_ci` 12/12 `rc=0`；`test_01_story25_ast_and_semantic_lock_guard` 1/1 `rc=0`；`dev_cli_help` `rc=0`；6 类 FORMAL schema 0 diff、22 文件 UTF-8 无 BOM/0 Emoji、冻结块 15-38 行未改、`scripts/` 零 `__pycache__`/`.pyc`）。

## Suggested Review Order

**核心入口与九阶段编排**

- 独立九阶段 CLI、只读终端校验与最佳努力事件落盘
  [compile_b_route_tasks.py:99](../../../scripts/python/compile_b_route_tasks.py#L99)

- 九阶段编译总构建：验 3A/3B/3.1、定 ID 与冻结目标
  [_b_route_task_compilation.py:1098](../../../scripts/python/_b_route_task_compilation.py#L1098)

- 幂等 `prepare`/`reserve` 执行流与 `prepare->reserve` 活状态兼容
  [_b_route_task_compilation.py:1572](../../../scripts/python/_b_route_task_compilation.py#L1572)

- `inspect` 漂移诊断与提交后快照观测核验
  [_b_route_task_compilation.py:1799](../../../scripts/python/_b_route_task_compilation.py#L1799)

**永久 ID 分配、三联编译与活状态合并**

- 仅在 `prepare` 分配 `taskmaster_id` 与业务 ID 并防碰撞
  [_b_route_task_compilation.py:515](../../../scripts/python/_b_route_task_compilation.py#L515)

- 编译视图与主任务，写入回链、`semantic_review_tier` 并防削弱
  [_b_route_task_compilation.py:664](../../../scripts/python/_b_route_task_compilation.py#L664)

- 生成 3C `binding.v1` 与 `origins.v1` 不可变目标
  [_b_route_task_compilation.py:977](../../../scripts/python/_b_route_task_compilation.py#L977)

- 按 `id` 精确合并活任务及子任务 `status` 并校验枚举
  [_b_route_task_compilation.py:263](../../../scripts/python/_b_route_task_compilation.py#L263)

**两段冻结、跨计划接替与恢复控制**

- `apply` 两段锁内合并活 `status`、封存证明与 `recover` 前滚
  [_b_route_commit.py:903](../../../scripts/python/_b_route_commit.py#L903)

- 单视图未改动识别与 `read_committed` 预写阻断守卫
  [_b_route_commit.py:971](../../../scripts/python/_b_route_commit.py#L971)

- 3C 共享容器 `scope` 隔离与单 Task 投影头选择
  [_b_route_commit_projection.py:71](../../../scripts/python/_b_route_commit_projection.py#L71)

- 三计划连续接替单 Task 投影校验与虚拟化字节读取
  [_b_route_records.py:1266](../../../scripts/python/_b_route_records.py#L1266)

**辅助 Schema、Journal 与策略锚定**

- 3C 操作辅助 Schema 严格约束三联投影与目标结构
  [task-compilation-operation.schema.json:1](../../../docs/planning/b-route/schemas/task-compilation-operation.schema.json#L1)

- 仅将辅助 Schema 注册至 `AUXILIARY`，零改动 FORMAL
  [_b_route_schema_resources.py:14](../../../scripts/python/_b_route_schema_resources.py#L14)

- 扩展共享 Journal 支持 `task_compilation` 与投影目标校验
  [_planning_apply_journal.py:117](../../../scripts/python/_planning_apply_journal.py#L117)

- 台账校验 `TASK_COMPILATION_SCHEMA` 分支与范围约束
  [_b_route_adoption.py:440](../../../scripts/python/_b_route_adoption.py#L440)

- `policy_observations` 密码学锚定 3C 预览与编译模块
  [_b_route_adoption_review.py:137](../../../scripts/python/_b_route_adoption_review.py#L137)

**CLI 接线、确定性门禁、测试与文档**

- 注册 `dev_cli.py b-route-task-compile` 快速派发与命令入口
  [dev_cli.py:622](../../../scripts/python/dev_cli.py#L622)

- 构建 `-B` 子进程命令并校验参数约束
  [dev_cli_builders.py:887](../../../scripts/python/dev_cli_builders.py#L887)

- 纳入 `b-route-runtime` 确定性门禁与 CI 路径过滤
  [run_gate_bundle.py:169](../../../scripts/python/run_gate_bundle.py#L169)

- 覆盖 5 行矩阵、P-01..P-10 回归与零字节码子进程单测
  [test_b_route_task_compilation.py:773](../../../scripts/python/tests/test_b_route_task_compilation.py#L773)

- 3C 受治理编译 Owner 文档与九阶段 Windows 示例
  [b-route-task-compilation.md:7](../../../docs/workflows/b-route-task-compilation.md#L7)
