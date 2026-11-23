---
title: 'Story 3.5：构造共同InputSet并精确判断新鲜度'
type: 'feature'
created: '2026-11-23'
status: 'done'
baseline_commit: '3aef15ee48b1c91c8bf385cffb2e4e209041d297'
story_key: '3-5-构造共同inputset并精确判断新鲜度'
review_loop_iteration: 1
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-3-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 缺唯一 InputSet 与新鲜度算法，整份 catalog/tasks 或 HEAD 误伤无关变更，漏检漂移或持全局锁又放行陈旧依据或阻塞并发。
**Approach:** 交付 _b_route_input_set.py 与 b-route-input-set，汇总 3.3 计划集、3.4 绑定、Task 投影、契约/ADR/Overlay/manifest、依赖闭包与环境产 input_set_digest，判新鲜度、返阶段与 scope 重验。

## Boundaries & Constraints

**Always:** 算法仅此一处；先调 3.3 验来源、pending(旧 capability-apply.pending.json、commit/public-sync pending 与重叠 scope)及适用集；显式候选 binding 必过 binding.schema.json、plan_ref 与 OwnedRef 实证，仅替对应 plan_id 槽位(保他已提交绑定)并标 uses_candidate_binding=true；收齐 source/Ledger/Requirement、plan/binding 修订(含递归 resolved_definitions 与 Stage-4 语义；clean clone 中 logs/ 保收据封存 raw_digest，非 logs/ 实读核验)、Task 定义与 Acceptance(task_definition_projection 仅排 status 与直接 subtasks[].status，禁扩 mutable，raw proof 保原模式)、ADR/Overlay/Game.Core/Contracts/**、manifest(验 schema/Flow/Test/文件与 Task 存在及 manifest_sha256，解耦活 status 与 blocking_task_ids 防兄弟推进误阻)或合法非 Flow other_verification、传递依赖闭包(依赖链与跨计划定义/生产者投影，未知/循环保守扩闭包，不可证阻断)及 policy/codec/环境；task-origins 验真后仅取本 Task 切片(排 origins.revision)入摘要；每条保 locator、raw_digest、normalization_mode、codec_version 与 normalized_digest，禁漏未知或损坏项；status、无关 Task、他计划推 catalog/origins 或 HEAD 不改 input_set_digest，单报实时依赖资格且未 done 合法，禁复制 status 入新权威；对比基线出失效项与 return_stage(3A..5)；默认只读零建锁并有界重读抗漂移，guarded_input_set 仅持业务 scope 租约(review_only=True，无全局长锁)并在进入与 revalidate() 重验；六字段 Diagnostic，readiness/runtime_verified/execution_authorized/default_b_enabled 恒 false。
**Ask First:** 改 7 FORMAL、扩 ReasonCode/Stage、加第二套算法或依赖未建 Epic 4 runner/页面。
**Never:** 用整份 catalog/origins/tasks hash 或 HEAD 当新鲜度键；因同流 status 拒判 manifest；候选冒充已提交；跳过缺失项；无 --report/--lock-mode scope 写盘建锁；将输入合法当 readiness。

## I/O & Edge-Case Matrix

| Scenario | Input | Expected | Error |
|---|---|---|---|
| FULL_SET | 3.3/3.4 有效 Task(含 clean clone/候选 binding) | 齐备定位/raw/规范化摘要与 digest；候选替单槽标未提交 | 缺失、损坏或候选失配阻断 |
| STATUS_NOOP | 推自身/同流 status、改无关 Task、他计划推 catalog/origins/HEAD | digest 不变且 manifest 不因 status 拒判；返实时资格 | 禁误判过期或复制 status |
| REL_INVALID | 改 Acceptance、依赖、契约/绑定、manifest、来源或规则 | digest 改变，列失效项并返 return_stage(3A..5) | 未知/循环依赖不可证阻断 |
| DRIFT_LOCK | 漂移、pending 或 guarded_input_set 重验 | 瞬时漂移重读收敛；持续漂移/pending 阻断；仅持业务 scope | 失配报 INPUT_STALE/PENDING |
| CALLER_PARITY | 独立调用或可选 --report | 同构 JSON、同 digest 与六字段诊断，无 --report 零写 | 越界或已存在拒覆写 |

</frozen-after-approval>

## Code Map

- `_b_route_task_resolver.py:359,565,1535` -- 3.3/pending
- `_b_route_chapter4_binding.py:1229`、`_chapter5_contract_bindings.py:1` -- 契约
- `_b_route_protection.py:93`、`_b_route_records.py:364,758,1118` -- 投影
- `_mvg_manifest.py:15,60`、`validate_overlay_execution.py:141`、`_b_route_adoption_review.py:200` -- 环境
- `_b_route_operation_scope.py:55,375` -- scope

## Tasks & Acceptance

**Execution:**
- [x] `scripts/python/_b_route_input_set.py` -- InputSet、依赖闭包、manifest/origins 归一化、return_stage 与 guarded_input_set（AC-1..5）
- [x] `scripts/python/resolve_b_route_input_set.py` -- CLI、builders 与锚定（AC-1,4,5）
- [x] `scripts/python/tests/test_b_route_input_set.py` -- 矩阵、clean clone、候选槽位、同流 status 与重验门禁（AC-1..5）
- [x] `docs/workflows/b-route-input-set-resolution.md` -- 说明与索引（AC-5）

**Acceptance Criteria:**
- Given 有效 B(或冻结 A)Task，when 只读解析或对比基线，then 零建锁产 input_set_digest，无关 status/catalog/origins/HEAD 不失效，相关变化归因 3A..5。
- Given guarded_input_set 跨边界，when 重叠 scope 漂移或存在 pending，then 无全局长锁并在进入与 revalidate() 阻断。

## Spec Change Log

## Verification

- `py -3 -B -m unittest scripts.python.tests.test_b_route_input_set scripts.python.tests.test_b_route_runtime_ci -v`
- `py -3 -B scripts/python/dev_cli.py b-route-input-set --help`

### Step 4 Review & Verification Record

- 审查分类归档：`logs/ci/2026-11-23/story-3-5-step4-triage.md`（`intent_gap=0`、`bad_spec=0`、`patch=7`、`defer=0`）。
- 补丁闭环摘要：`P-01`（MVG `manifest_refs` 去重合并 `committed` 并统一写 `mvg_manifest_normalized`，改为按 binding 校验 Stage-5 Flow 覆盖）、`P-02`（收据 `authority` 传递 BFS 封存索引、`has_log` 同样严校 `owner`/语法与落盘实证、补采 `adoption_proof_refs`/`applicability`/`requirement_evidence`）、`P-03`（候选 binding 重算 `origins_slice`/`resolved_definitions`/`dependency_producer` 并拦截 `source_gap`/空映射/缺失日志）、`P-04`（补全 `_resolve_once` 观测面、统一 `resource_scopes` 归一化并复核传递依赖与 Flow peer 的 pending、补采传递依赖引用与 `contractRefs` fail closed）、`P-05`（`compare_input_sets` 字段类型前置校验、拆分 `binding_3c_mappings` 与去掩蔽 Stage-5 `obligations` 归因）、`P-06`（`--lock-mode scope` 陈旧基线与 `--lock-mode none` 完全同构并封装租约异常）、`P-07`（单测扩展至 14 项并全绿）。
- 最终验证日志：`logs/ci/2026-11-23/story-3-5-final-verify.log`：
  - `test_b_route_input_set`：14/14 通过（0 skipped）
  - `test_b_route_task_resolver`：11/11 通过（0 skipped）
  - `test_b_route_runtime_ci`：12/12 通过（0 skipped）
  - `test_b_route_records`：100 运行全部通过（14 skipped 为本机非管理员 symlink 跳过）
  - `test_b_route_adoption_journal`：11/11 通过（0 skipped）
  - `test_01_story25_ast_and_semantic_lock_guard`：1/1 通过（0 skipped）
  - `dev_cli.py b-route-input-set --help`：`rc=0`

## Suggested Review Order

### 公共 CLI 入口与分发

直接 CLI 参数注册与双模式执行分发
  [resolve_b_route_input_set.py:100](../../../scripts/python/resolve_b_route_input_set.py#L100)
统一 `dev_cli` 子命令路由与命令构建器
  [dev_cli.py:703](../../../scripts/python/dev_cli.py#L703)
  [dev_cli_builders.py:958](../../../scripts/python/dev_cli_builders.py#L958)

### 核心 InputSet 构造与新鲜度判定

规范化摘要计算与基线类型校验对比
  [_b_route_input_set.py:306](../../../scripts/python/_b_route_input_set.py#L306)
  [_b_route_input_set.py:501](../../../scripts/python/_b_route_input_set.py#L501)
传递收据封存索引与 `OwnedRef` 实证校验
  [_b_route_input_set.py:655](../../../scripts/python/_b_route_input_set.py#L655)
  [_b_route_input_set.py:846](../../../scripts/python/_b_route_input_set.py#L846)
状态解耦 MVG 校验、依赖闭包与契约采集
  [_b_route_input_set.py:952](../../../scripts/python/_b_route_input_set.py#L952)
  [_b_route_input_set.py:1157](../../../scripts/python/_b_route_input_set.py#L1157)
  [_b_route_input_set.py:1234](../../../scripts/python/_b_route_input_set.py#L1234)
候选 binding 校验与完整闭包重算
  [_b_route_input_set.py:1458](../../../scripts/python/_b_route_input_set.py#L1458)
  [_b_route_input_set.py:1644](../../../scripts/python/_b_route_input_set.py#L1644)
单轮只读解析、有界重读与业务 scope 租约
  [_b_route_input_set.py:1970](../../../scripts/python/_b_route_input_set.py#L1970)
  [_b_route_input_set.py:3200](../../../scripts/python/_b_route_input_set.py#L3200)
  [_b_route_input_set.py:3399](../../../scripts/python/_b_route_input_set.py#L3399)

### 确定性测试与说明文档

覆盖矩阵与补丁边界的 14 项确定性单测
  [test_b_route_input_set.py:945](../../../scripts/python/tests/test_b_route_input_set.py#L945)
Story 3.5 命令契约与算法边界说明
  [b-route-input-set-resolution.md:1](../../../docs/workflows/b-route-input-set-resolution.md#L1)
