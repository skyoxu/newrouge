---
title: 'Story 3.7：在Chapter5核对同源定义并形成有效readiness'
type: 'feature'
created: '2026-11-24'
status: 'done'
baseline_commit: 'e6e98ddb426d14f9920ed1088612d453a5a65585'
story_key: '3-7-在chapter5核对同源定义并形成有效readiness'
review_loop_iteration: 1
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-3-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 缺 B 路线 Chapter 5 同源核对与 readiness 门禁，易以 3A 省 5、凭时间戳或 N/A 放行、误阻未 done/planned/整合 owner、缺 B 落 legacy，且旧 done 绕新义务。
**Approach:** 交付 _b_route_chapter5_readiness.py 与 b-route-chapter5-readiness，桥接 chapter5_semantic_reconciliation/refresh，基于 InputSet、3A 与 3C/4/5 绑定产 readiness。

## Boundaries & Constraints

**Always:** 经 3.3 判 B、经 3.5 guarded_input_set 持业务 scope 租约通过，且适用绑定全为已提交 stage="5"(未达阻断归因 4/5)；只读复验 3A 来源身份/证明(未变复用，无关变化不重做 3A)，仍独立核对 Chapter 5 语义(显式 acceptance_links、ADR/Contract authority_decisions、dependency_decisions、overlap_decisions)，核对 Acceptance/Refs、Requirement、非 Flow 去向、ADR/Overlay/Contract、依赖与 Stage-5 义务，定位遗漏、冲突与无人交接；冻结 input_set_digest、applicable_set_digest、scope_ids、plan_refs、binding_refs 与 reconciliation_sha256，桥接 load_task_readiness 与 refresh_chapter_knowledge 同格式复验(无 B 痕迹保 A，存 B 痕迹走 B)，禁刷时间戳、禁改 3B plan 修订或增第二套状态；未 done 合法，planned 对象/测试定义明确即可未落盘(禁造假桩或标已实现/runtime_verified)，按三类角色核查且禁造自锁；输入缺失/损坏/过期以六字段 Diagnostic 阻断归因 return_stage(3A..5)，无关 Task/status/他计划发布不失效，缺 B 禁落 legacy，N/A 阻断，旧 done 遇 requires_reverification 标 requires_chapter6_reverification=true；守 P0/P1 底线，仅 P2..P4 在 allow_concerns 且记入 docs/technical-debt.md 准延期，禁降阈值/关测试/弱化 Acceptance；记 active_elapsed_seconds、model_invocation_count、复用与 return_stage，runtime_verified/default_b_enabled 恒 false。
**Ask First:** 改 7 FORMAL、扩 ReasonCode/Stage、加付费调用或改 3B plan。
**Never:** 以 3A 省 5；刷时间戳充有效；拒未 done 或逼 planned 造假桩；造自锁；缺 B 落 legacy 或 N/A 放行；旧 done 绕新义务；放行 P0/P1 或降质换绿。

## I/O & Edge-Case Matrix

| Scenario | Input | Expected | Error |
|---|---|---|---|
| RECONCILE_OK | 3A 可复验+3C/4/5 齐备+显式核对通过 | 冻 InputSet/scope 产 READY，复用 3A | 遗漏、冲突或无人交接阻断 |
| PLANNED_ROLE | 未 done+明确 planned 对象/测试+三类角色 | READY，无自锁，不求假桩 | 定义残缺或抹前置阻断 |
| STALE_SCOPED | 改契约/绑定/manifest/来源 vs 改无关项 | 相关失效返 3A..5；无关仍有效 | 刷时间戳、N/A 或落 legacy 阻断 |
| DONE_REVERIFY | status=done 但含新义务/planned 测试 | 标 requires_chapter6_reverification=true | 声称免重验阻断 |
| NEEDS_FIX_P1 | P0/P1 vs allow_concerns+P2..P4 记债 | P0/P1 阻断；P2..P4 记债 CONCERNS | 降阈值、关测试或弱化阻断 |

</frozen-after-approval>

## Code Map

- `_b_route_input_set.py:501,3200,3399` -- InputSet/租约
- `_b_route_stage5_obligations.py:710`、`_b_route_chapter4_binding.py:1229` -- Stage-4/5
- `chapter5_semantic_reconciliation.py:575,883,1498,1574` -- Ch5/load_task_readiness
- `refresh_chapter_knowledge.py:116`、`run_chapter5_guarded.py:37` -- guarded/refresh
- `docs/technical-debt.md:1`、`chapter6_route.py:40` -- P1/记债

## Tasks & Acceptance

**Execution:**
- [x] `scripts/python/_b_route_chapter5_readiness.py` -- 核对、无自锁、P1 底线、新鲜度、计量与桥接（AC-1..5）
- [x] `scripts/python/reconcile_b_route_chapter5_readiness.py` -- CLI 与 chapter5/refresh 适配（AC-1..5）
- [x] `scripts/python/tests/test_b_route_chapter5_readiness.py` -- 单测、桥接与 CI（AC-1..5）
- [x] `docs/workflows/b-route-chapter5-readiness.md` -- 说明与索引（AC-2,5）

**Acceptance Criteria:**
- Given 3A 与 3C/4/5 有效(含未 done、明确 planned 与三类角色)，when 核对 Chapter 5，then 复用 3A 并核对同源语义，冻 InputSet 产 readiness，无关变化不失效。
- Given 缺失/过期、B 残缺、N/A、旧 done 遇新义务或 P0/P1，when 查 readiness，then 阻断归因 3A..5，禁退 legacy 或降质换绿，P2..P4 记债并记指标。

## Spec Change Log

## Verification

- `py -3 -B -m unittest scripts.python.tests.test_b_route_chapter5_readiness scripts.python.tests.test_b_route_runtime_ci -v`
- `py -3 -B scripts/python/dev_cli.py b-route-chapter5-readiness --help`

### Step 4 Review & Verification Record

- 审查分类归档：`logs/ci/2026-11-24/story-3-7-step4-triage.md`（`intent_gap=0`、`bad_spec=0`、`patch=7`、`defer=0`）。
- 补丁闭环摘要：`P-01`（`dev_cli.py` 唯一注册 `cmd_b_route_chapter5_readiness` 与 `b-route-chapter5-readiness` 解析器并复用 `build_b_route_chapter5_readiness_cmd(args)[3:]`，拒绝 `verify`/`check-readiness`/`read` 上的跨阶段非法参数并返回 `INVALID_ARGUMENT` (`rc=2`)，贯通 `--operation`/`--readiness`/`--out`/`--reconciliation`/`--lock-mode`，在 `readiness_doc` 持久化 `reconciliation_path` 且不改写 `reconciliation_sha256`，以 `inventory.safe_input(..., allow_logs=True)` 与 `inventory.no_reparse` 加固 Windows 短路径与符号链接/联接防护）、`P-02`（`detect_repo_b_route_presence` 排除仓库模板目录 `docs/planning/b-route/schemas/**` 保纯 A 路由，以严格 ASCII `re.fullmatch(r"[1-9][0-9]*", ...)` 替换 `.isdigit()` 并在存在 B 痕迹时对非法 `task_id` 立即 fail-closed，加固 `refresh_chapter_knowledge.py` `b_route_pure_ch5` 模式绑定 `stable_input_hash`、通过 `verify_b_route_closure_evidence` 复验实时新鲜度后再提升或复用 `CHAPTER5_STABLE_PATH`，并在 `write_planning=True` 缺旧 Ch3 拓扑时显式阻断）、`P-03`（在 `guarded_input_set` 租约内复核 `resolve_task_origin` 断言 `route=="B"` 与 `applicable_set_digest` 一致，将 `handle.revalidate()` 前置于包含 `record_technical_debt_findings` 在内的全部写盘动作，保证 `--dry-run`/`preview` 零写入 `docs/technical-debt.md` 同时完成 P2..P4 资格校验，修复 lambda 替换避免反斜杠转义与标题粘连，收紧 `verify_technical_debt_recorded` 至目标 Task 受管段内精确 `{finding_id=...}`）、`P-04`（收紧 `acceptance_links`/`authority_decisions`/`dependency_decisions`/`overlap_decisions`/`findings`/`review_findings` 结构、重复键与 `acceptance_index` 范围校验，合并保留 `findings` 与 `review_findings`，记录并复验 `decision_referenced_file_digests` 归因 Contract/ADR/Overlay 漂移至 `"4"`、测试及其他文件漂移至 `"5"`）、`P-05`（按 `(plan_id, requirement_id)` 精确收敛当前 Task 映射 Requirement 的覆盖率、3B `requirement_verification`/`applicability` 存在性（缺失归因 `"3B"`）与非 N/A 理由，避免共享义务误阻兄弟 Requirement 并阻断无 `integration_only_owner` 的空需求空义务，校验 Flow handoff `owner_task` 属 `flow["task_ids"]` 与 `master_tasks`、角色对齐及 Stage-4 逻辑事件 `contract_ref` 解析进入 `authority_scope["contracts"]`，`_REFS_RE` 启用 `re.MULTILINE` 并将 `test_refs` 严格限定为已绑定 Stage-5 manifest 测试、真实测试文件或已绑定 `other_verification_refs`）、`P-06`（新增 `_verify_3a_source_audit` 同时复验完整 3A `event.json`/`report.json` 包与独立 `newrouge.b-route-source-audit.v1` 证明并在 `--require-full-audit-proof` 缺失、`satisfied!=True`/阻断 finding 或来源摘要漂移时 fail-closed 返回 `return_stage="3A"`，`policy_observations()` 锚定 `_chapter5_contract_bindings.py`，并在 `.github/workflows/b-route-runtime-deterministic.yml` 与 `test_b_route_runtime_ci.py` 补齐 `_chapter5_contract_bindings.py`、`run_chapter5_guarded.py`、`chapter5_semantic_reconciliation.py` 与 `refresh_chapter_knowledge.py` 路径过滤）、`P-07`（扩充 `test_10`..`test_15` 覆盖全部 `P-01`..`P-06` 行为至 15 项全绿，完成 8 项并行终验并收口规格、冲刺状态与提交前完整性核验）。
- 最终验证日志：`logs/ci/2026-11-24/story-3-7-final-verify.log`（每项原始日志位于 `logs/ci/2026-11-24/s37-checks/`）：
  - `test_b_route_chapter5_readiness`：15/15 通过（0 skipped）
  - `test_b_route_stage5_obligations`：15/15 通过（0 skipped）
  - `test_b_route_input_set`：14/14 通过（0 skipped）
  - `test_b_route_runtime_ci`：12/12 通过（0 skipped）
  - `test_chapter5_semantic_reconciliation`：25/25 通过（0 skipped）
  - `test_knowledge_chapter5_routing`：1/1 通过（0 skipped）
  - `test_01_story25_ast_and_semantic_lock_guard`：1/1 通过（0 skipped）
  - `dev_cli.py b-route-chapter5-readiness --help`：`rc=0`

## Suggested Review Order

### 公共 CLI 入口与分发

Stage-5 Chapter 5 核对 CLI 参数校验、跨阶段非法参数阻断与分发
  [reconcile_b_route_chapter5_readiness.py:120](../../../scripts/python/reconcile_b_route_chapter5_readiness.py#L120)
  [reconcile_b_route_chapter5_readiness.py:169](../../../scripts/python/reconcile_b_route_chapter5_readiness.py#L169)
统一 `dev_cli` 子命令注册与命令构建器
  [dev_cli.py:682](../../../scripts/python/dev_cli.py#L682)
  [dev_cli.py:737](../../../scripts/python/dev_cli.py#L737)
  [dev_cli.py:1309](../../../scripts/python/dev_cli.py#L1309)
  [dev_cli_builders.py:1015](../../../scripts/python/dev_cli_builders.py#L1015)

### 核心同源核对、3A 证明复验与 P1 记债底线

仓库 B 路线痕迹判定与 3A `source_audit` 只读复验
  [_b_route_chapter5_readiness.py:307](../../../scripts/python/_b_route_chapter5_readiness.py#L307)
  [_b_route_chapter5_readiness.py:480](../../../scripts/python/_b_route_chapter5_readiness.py#L480)
`docs/technical-debt.md` 受管段 P2..P4 记债与精确回查
  [_b_route_chapter5_readiness.py:1255](../../../scripts/python/_b_route_chapter5_readiness.py#L1255)
  [_b_route_chapter5_readiness.py:1309](../../../scripts/python/_b_route_chapter5_readiness.py#L1309)
核心 `reconcile_b_route_chapter5`（租约复核、同源语义、无自锁、旧 done 重验与冻结）与闭环复验
  [_b_route_chapter5_readiness.py:1501](../../../scripts/python/_b_route_chapter5_readiness.py#L1501)
  [_b_route_chapter5_readiness.py:4178](../../../scripts/python/_b_route_chapter5_readiness.py#L4178)

### Chapter 5 与 Knowledge 桥接、策略锚定

`chapter5_semantic_reconciliation.py` 同格式新鲜度与 `load_task_readiness` 桥接
  [chapter5_semantic_reconciliation.py:1498](../../../scripts/python/chapter5_semantic_reconciliation.py#L1498)
  [chapter5_semantic_reconciliation.py:1610](../../../scripts/python/chapter5_semantic_reconciliation.py#L1610)
`refresh_chapter_knowledge.py` `b_route_pure_ch5` 实时新鲜度复验与稳定态提升门禁
  [refresh_chapter_knowledge.py:117](../../../scripts/python/refresh_chapter_knowledge.py#L117)
  [refresh_chapter_knowledge.py:894](../../../scripts/python/refresh_chapter_knowledge.py#L894)
  [refresh_chapter_knowledge.py:1074](../../../scripts/python/refresh_chapter_knowledge.py#L1074)
`policy_observations()` 策略哈希锚定（含 `_chapter5_contract_bindings.py`）
  [_b_route_adoption_review.py:137](../../../scripts/python/_b_route_adoption_review.py#L137)
  [_b_route_adoption_review.py:171](../../../scripts/python/_b_route_adoption_review.py#L171)

### 确定性测试、CI 矩阵与说明文档

覆盖矩阵与 `P-01`..`P-07` 的 15 项确定性单测
  [test_b_route_chapter5_readiness.py:1110](../../../scripts/python/tests/test_b_route_chapter5_readiness.py#L1110)
  [test_b_route_chapter5_readiness.py:1604](../../../scripts/python/tests/test_b_route_chapter5_readiness.py#L1604)
确定性 CI 矩阵与路径过滤器测试
  [test_b_route_runtime_ci.py:38](../../../scripts/python/tests/test_b_route_runtime_ci.py#L38)
  [test_b_route_runtime_ci.py:253](../../../scripts/python/tests/test_b_route_runtime_ci.py#L253)
Story 3.7 命令契约、桥接规则与边界说明
  [b-route-chapter5-readiness.md:1](../../../docs/workflows/b-route-chapter5-readiness.md#L1)
