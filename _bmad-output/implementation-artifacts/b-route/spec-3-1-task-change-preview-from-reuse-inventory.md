---
title: 'Story 3.1：从复用盘点形成真实缺口的任务变更预览'
type: 'feature'
created: '2026-11-22'
status: 'done'
baseline_commit: 'fc01327c5fea757cce478ebd072160366d9c9c7a'
story_key: '3-1-从复用盘点形成真实缺口的任务变更预览'
review_loop_iteration: 1
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-3-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 3C 缺少只读复用盘点与缺口预览。
**Approach:** 只读 3C 服务/CLI 消费 3B、3A、三联与基线，输出可审阅 back/gameplay 增量（reuse|update|create|split|merge|retire）及同构 newrouge.b-route-binding.v1（stage="3C"）/newrouge.b-route-origins.v1 草案供 3.2 免翻译消费；落盘与正式 ID 归 3.2。

## Boundaries & Constraints

**Always:** read_committed 读 3B，verify_current_proof 验 3A 并核对 plan.source_identity（manifest_ref/ledger_ref/source_manifest_digest），TaskJoinContext 关联三联。保留成熟 taskmaster_id/business_id/status/历史；create/split 用 candidate_key+task_id=null（正式 ID 归 3.2）；update/split/merge/retire 附范围、来源差异、谱系与理由并防削弱。处理 plan.requirement_verification 的 flow/other_verification（other_verification_refs）/non_task_sinks/deferred（盘点义务不伪造 Flow，deferred 非满足），保持多对多与 Requirement 唯一核算。仅写 logs/** 并重读；3A 失效、漂移或 source_gap 返回 3A/3B 六字段 Diagnostic。
**Ask First:** 扩展 ReasonCode/Stage 或增 schema。
**Never:** 写 tasks*.json/b-route/manifest；Story 号充或预分配 ID；compile_task_triplet 覆盖 status 或退役；机械四拆、按数推缺口或虚构 API；旧 done 证明新义务、预览代 readiness 或弱化 Acceptance。

## I/O & Edge-Case Matrix

| 场景 | 输入 | 期望 |
|---|---|---|
| HAPPY/ZERO | 缺口或全覆 | 双输出（全覆纯 reuse）；零写，readiness=false |
| M2M | 多对多/owner | 唯一核算；不四拆不虚构 API |
| NON_FLOW | 非 Flow | 盘点义务无假 Flow；deferred 不执行 |
| MATURE | 成熟变更/削弱 | 保留属性与理由；阻断覆盖与削弱 |
| GAP_DRIFT | 漂移/3A/source_gap | fail-closed 返回 3A/3B 六字段诊断 |

</frozen-after-approval>

## Code Map

- `_b_route_codec.py:30,84,218,333`、`_b_route_records.py:345,364,1321`、`_b_route_commit.py:926` -- 诊断/join/read_committed。
- `_b_route_protection.py`、`_b_route_preflight.py`、`_b_route_inventory.py` -- 保护/防削弱/重读/盘点。
- `_b_route_source_audit.py:1159`、`_b_route_flow_graph.py`、`_mvg_requirement_routes.py`、`_mvg_requirement_accounting.py` -- 3A/部件图/核算。
- `normalize_task_intents.py`、`chapter3_task_scope.py:19,47`、`compile_task_triplet.py:70` -- 确定性意图规范化（无 LLM/写盘）；区别旧 A reconcile-existing-only，3.1 只读评估 3B 缺口，不改三联或重置 status="pending"。
- `update_mvg_baseline.py:88`、`dev_cli.py:1160`、`dev_cli_builders.py:685`、`run_gate_bundle.py:59` -- 基线/CLI/门禁。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/python/_b_route_task_preview.py` -- 3C 盘点、3A 核验与双输出 -- AC-1..5
- [x] `scripts/python/preview_b_route_task_changes.py`、`scripts/python/dev_cli.py`、`scripts/python/dev_cli_builders.py` -- b-route-task-preview CLI -- AC-1/4/5
- [x] `scripts/python/tests/test_b_route_task_preview.py`、`scripts/python/run_gate_bundle.py` -- 矩阵/零改写/零 pycache 入门禁 -- AC-1..5
- [x] `docs/workflows/b-route-task-preview.md`、`AGENTS.md`、`docs/workflows/stable-public-entrypoints.md`、`docs/workflows/script-entrypoints-index.md` -- 文档与入口同步 -- AC-4

**Acceptance Criteria:**
- AC-1: Given 有效 3B/3A/三联/基线，When 预览，Then 盘点复用、缺口与非 Flow，旧 done 不证明新义务。
- AC-2: Given 多对多与 owner，When 预览，Then 唯一核算，不四拆不虚构 API。
- AC-3: Given 成熟变更或削弱，When 校验，Then 保留属性与谱系理由，阻断覆盖状态与削弱。
- AC-4: Given 校验通过，When 写 logs/**，Then 输出业务增量与 3.2 同构草案，ID 归 3.2，readiness=false。
- AC-5: Given 3A 失效、漂移或 source_gap，When 预览，Then 返回 3A/3B 六字段诊断，零写不弱化 Acceptance。

## Spec Change Log

## Design Notes

契约 newrouge.b-route-task-preview.v1，授权全 false。因 plan.v1 source_identity 仅含 manifest_ref/ledger_ref（无 3A audit report.json），CLI 接 --root/--plan-id/--run-id/--audit-ref/--scope-id 及可选 --protection-ref/--manifest/--change-intents。3.2 同构草案对应 binding.v1(stage="3C")/origins.v1：view_refs(back|gameplay,business_id), requirement_ids, flow_ids, part_kinds(domain_rules|csharp_adapter|binding|scene), roles(producer|consumer|integration_only_owner), obligation_ids, parts, implementation_objects(planned|existing), obligations, manifest_refs, other_verification_refs, source_refs, plan_ref；create/split 用 candidate_key+task_id=null。read_committed 固定原字节并核验 verify_current_proof/source_identity；末尾 Observations.finish 重读，漂移置 stable=false；preview_digest 排除时间戳。

## Verification

**Commands:**
- `py -3 -B -m unittest scripts.python.tests.test_b_route_task_preview -v`
- `py -3 -B scripts/python/dev_cli.py b-route-task-preview --help`
- `py -3 -B scripts/python/run_gate_bundle.py --mode b-route-runtime`

### Step 4 Review & Verification Record

- **Review 修复摘要（P1-P6）：**
  - P1：`origins_preview` 严格 schema 失败阻断、全复用直接 schema 校验，以及 retire/split/merge 吸收任务的 `origins_preview` 清理与 `implementation_objects` 责任过滤。
  - P2：`change_intents` 重复目标/碰撞检测、未知 `flow_id`、无锚点 `source_diff_evidence`、缺失退役 `authority_ref` 与累计 MVG 基线防削弱门禁。
  - P3：旧 `done` 任务禁止满足新增 Requirement/Part、局部实现任务角色保真（不误标为 `integration_only_owner`）及跨计划共享 Flow 解析。
  - P4：可选 `--protection-ref` 完整校验（schema、`capture_complete=true` 与归档观测）、3A 缺失 `source_identity` 阶段归属标注及 `run_id` Windows 保留名拦截。
  - P5：`dev_cli` / `dev_cli_builders` 必填项与只读约束强化。
  - P6：`test_b_route_task_preview.py` 缓存 3A 证明改为固定目录原地复原，消除 `proof.execution` 路径漂移与临时目录泄漏。
- **最终核验记录：** 见 `logs/ci/2026-11-22/story-3-1-final-verify.log`（`test_b_route_task_preview` 13/13 rc=0、0 跳过；`test_01_story25_ast_and_semantic_lock_guard` 1/1 rc=0；`dev_cli.py b-route-task-preview --help` rc=0）与 `logs/ci/2026-11-22/story-3-1-runtime-ci-verify.log`（`test_b_route_runtime_ci` 12/12 rc=0；`test_01_story25_ast_and_semantic_lock_guard` 1/1 rc=0；`dev_cli.py b-route-task-preview --help` rc=0；冻结块未改、15 文件 UTF-8 无 BOM、0 Emoji、16 链接全解析、`scripts/` 下零 `__pycache__`/`.pyc`）。

## Suggested Review Order

**核心入口与编排契约**

- 只读 3C 预览总编排、全 false 授权与确定性摘要
  [`_b_route_task_preview.py:3205`](../../../scripts/python/_b_route_task_preview.py#L3205)

- 契约常量、六字段诊断包装与 Windows 保留名防线
  [`_b_route_task_preview.py:36`](../../../scripts/python/_b_route_task_preview.py#L36)

- 独立只读 CLI 与原子 `report.json` 落盘及 0/1/2 退出码
  [`preview_b_route_task_changes.py:50`](../../../scripts/python/preview_b_route_task_changes.py#L50)

**3B 提交链与 3A 证明现势核验**

- 经 `read_committed` 加载已发布 3B 计划与跨计划共享 Flow
  [`_b_route_task_preview.py:243`](../../../scripts/python/_b_route_task_preview.py#L243)

- 经 `verify_current_proof` 核验 3A 证明并对齐 `source_identity`
  [`_b_route_task_preview.py:356`](../../../scripts/python/_b_route_task_preview.py#L356)

- 阻断 `source_gap` 并保持 Requirement 唯一处置与去重证据
  [`_b_route_task_preview.py:521`](../../../scripts/python/_b_route_task_preview.py#L521)

- 经 `TaskJoinContext` 关联三联并校验可选保护快照
  [`_b_route_task_preview.py:594`](../../../scripts/python/_b_route_task_preview.py#L594)

**复用盘点、意图防冲突与防削弱**

- 校验显式 `change_intents` 冲突、Story ID 与防削弱
  [`_b_route_task_preview.py:863`](../../../scripts/python/_b_route_task_preview.py#L863)

- 累计 MVG 基线防削弱门禁（覆盖四类成熟变更）
  [`_b_route_task_preview.py:2269`](../../../scripts/python/_b_route_task_preview.py#L2269)

- 复用盘点、旧 `done` 隔离、非 Flow 义务与无四拆缺口
  [`_b_route_task_preview.py:2376`](../../../scripts/python/_b_route_task_preview.py#L2376)

**双输出草案构建与并发重读护栏**

- 构建 3.2 同构 `binding.v1`/`origins.v1` 草案并校验 schema
  [`_b_route_task_preview.py:1907`](../../../scripts/python/_b_route_task_preview.py#L1907)

- 末尾重读 3A/3B/主观测快照并独占创建 `logs/**` 运行目录
  [`_b_route_task_preview.py:3411`](../../../scripts/python/_b_route_task_preview.py#L3411)

**CLI 接线、门禁与矩阵单测**

- 注册 `dev_cli.py b-route-task-preview` 与只读派发
  [`dev_cli.py:610`](../../../scripts/python/dev_cli.py#L610)

- `dev_cli_builders` 拒绝写参数并拼装 `-B` 命令
  [`dev_cli_builders.py:855`](../../../scripts/python/dev_cli_builders.py#L855)

- 纳入 `b-route-runtime` 确定性门禁并同步 CI 选择器
  [`run_gate_bundle.py:168`](../../../scripts/python/run_gate_bundle.py#L168)

- 覆盖 5 行矩阵、P1-P6 回归、子进程 0/1/2 与零字节码
  [`test_b_route_task_preview.py:586`](../../../scripts/python/tests/test_b_route_task_preview.py#L586)
