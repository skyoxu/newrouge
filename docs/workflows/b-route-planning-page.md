# B 路线规划页面按真实阶段操作、定位阻塞与恢复

本文是 Story 4.7 的 owner 说明。共享服务 `scripts/python/_b_route_planning_page.py`（`newrouge.b-route-planning-page.v1`）同时被以下三端消费，三端决定、六字段诊断与可恢复态一致：

- CLI：`py -3 -B scripts/python/dev_cli.py b-route-planning-page --root <root> --action <action> --mode <mode> [...]`（直接入口 `scripts/python/query_b_route_planning_page.py`）。
- HTTP：只读 `GET /api/knowledge/b-route-planning?mode=<mode>[&scope_id=&flow_id=&capability_id=&task_id=&run_id=&operation_id=][&strict=1]` 与受保护的 `POST /api/knowledge/b-route-planning`。
- 直接调用：`inspect_planning_page_state(root, ...)` 与 `execute_planning_page_action(root, request)`。

## 边界

- 旧 A 合同 `POST /api/knowledge/planning`（`{action: 'capability'|'mvg', manifest?}`）保持不变；本服务不建第二状态机，不改 7 个 FORMAL schema、`ReasonCode`/`Stage` 枚举或控制面。
- 页面自动化测试只证明交互合同：所有结果恒 `ui_contract_only_not_godot_gameplay=true`、`runtime_verified=false`，不得充当 Godot 玩法或奖励试点证据。
- 预览、恢复、推荐与实施动作前后对 `knowledge/indexes/current.json`、`knowledge/indexes/last-known-good.json`、`logs/ci/project-health-knowledge/latest.json`、`logs/ci/project-health-knowledge/runtime/latest.json` 与 `refs/heads/main` 做哈希比对，任何变化即以 `conflict` 阻断；零隐式全局 Knowledge 扫描、发布或 refresh。

## 真实阶段门控（`stage_gates`）

| 门控 | 允许条件 | 不依赖 |
| --- | --- | --- |
| `stage_3a_sources` | `docs/workflows/chapter3-source-set.json` 可读且登记来源非空（`mode=main` 时读取已提交 `refs/heads/main` 快照而非工作区脏文件）；动作委托 `dev_cli.py b-route-sources`（`prepare`/`account`/`audit`/`verify`，含 `AUDIT_ARGUMENTS`） | Task、`.taskmaster/tasks/**`、Chapter 5 readiness |
| `stage_3b_planning` | 3A 门控通过且存在 `planning_eligible=true` 的 3A 独立来源审计报告（有界扫描 `logs/ci/<date>/b-route-source-audit/<run>/<attempt>/report.json`、`logs/ci/b-route-source-audit/<run>/<attempt>/report.json` 及 `verify/report.json`，未审计 `account` 不解锁）；动作委托 `plan_capabilities.py`/`plan_mvg.py --input-stage 3b` 与 `b-route-adoption` | Task、Chapter 5 readiness；永不传 `--allow-unready-draft`/`--task-id` |
| `stage_3c_tasks` | `catalog.v1.json` 中存在正式采纳且有效的 3B `plan`，目标 scope 无损坏或未决 pending | Chapter 5 readiness |
| `stage_6_implement` | 指定 `task_id` 时经 Story 3.12 `_b_route_entrypoint_parity.handle_page_b_route_trigger` 只读 gate 判定，按适用区分 B、冻结 A 与合法非 Flow（`other_verification_refs`，不强造 Flow/场景要求） | 页面摘要或缓存 |

被拒门控均携带六字段 `Diagnostic`（`reason_code`、`stage`、`entity_id`、`expected`、`actual`、`resume_ref`），仅使用现有 `ReasonCode`/`Stage` 值。

## 协调器进度（`coordinator_progress`）

只做一层有界读取（`logs/ci/{capability,mvg}-planning/<run_id>/run.json`、`_mvg_capability_recovery.registry(root)`、`clears/epoch-*.json`、`logs/ci/b-route-reopen`、`logs/ci/b-route-operations/operations/<sha256(operation_id)>`），绝不对 `logs/ci/mvg-planning` 或 `logs/ci/capability-planning` 做递归 glob：

- `committed_prefix`：已提交选择检查点；未完成时 `partial_planning=true`，恒 `planning_complete=false`、`runtime_verified=false`。
- `candidate_states`：候选中间态标 `candidate_in_progress` 或 `candidate_uncommitted`，恒 `adopted=false`，禁作已采纳。
- `budget_summary`：如实报告 `request_budget`、`mvg.run_invocation_limit`、`total_invocations`、`dispatches_used`、`repair_attempts` 与 `budget_exhausted`（`selection_block_reason == run_blocked_budget_exhausted`、`request_budget_exhausted=true` 或已达上限时不可恢复）。
- `revoked_runs`：`mvg-clear` epoch/归档失效、`reopen_transactions` 或 `logs/ci/b-route-reopen` 撤销的 run 标 `revoked=true`、`recoverable=false`，页面永不据其填绿。
- `recoverable_operations`：可恢复的 planner run、页面 job、pending journal 与 `--operation-id` 指定的采纳操作（按 `sha256(operation_id)` 定位），携带原样诊断、`resume_ref` 与 `original_locator`。

## 动作与 `invocation_mode`

| `action` | 委托 | 只读推荐 |
| --- | --- | --- |
| `inspect` | 本服务只读状态；`recovery_target` 可为 `state`、`chapter6_resume`、`chapter6_route`、`adoption`（`b-route-adoption --stage inspect --context`） | 恒 `recommendation_only=true`，显式 `false` 被拒 |
| `3a_sources` | `account_b_route_sources.py --stage prepare|account|audit|verify`（支持 `expected_model`/`completed_extraction_ref`/`request_budget`/`active_budget_seconds`/`timeout_seconds`/`citation_guidance`） | 否 |
| `3b_capability` / `3b_mvg` | `plan_capabilities.py` / `plan_mvg.py --input-stage 3b` | 否 |
| `3b_adoption` | `b_route_adoption.py --stage ...` | `inspect`、`recover-inspect` |
| `3c_task_preview` / `3c_task_compile` | 先过 `stage_3c_tasks`，再委托 `preview_b_route_task_changes.py`（支持 `protection_ref`/`change_intents`）/ `compile_b_route_tasks.py`（`prepare` 需 `request_ref`） | `compile` 的 `inspect`、`recover-inspect` |
| `chapter6` | `handle_page_b_route_trigger`（`sub_action` 为 `gate`/`execute`/`resume`/`route`） | `gate`/`resume`/`route` 默认是，`execute` 需 `recommendation_only=false` |

- `invocation_mode=new`（默认）：支持 `prepare`（需 `planning_contract`，核验 `logs/ci/b-route-planning-input/<run_id>` 与 `logs/ci/{capability,mvg}-planning/<run_id>` 均不存在）与首次 `generate`（需 `prepared_ref` 与 `planning_profile`，核验 `run.json` 尚不存在），已有槽位以 `conflict` 阻断，绝不复用旧槽位。
- `invocation_mode=resume`：要求已有 `run.json`，允许 `generate`/`review`/`status`/`verify-selection`；自动从 `run.json` 补齐 `prepared_ref`/`planning_profile`（显式传入不一致时报 `conflict`）；调用前核对 epoch、归档、reopen 与预算：失效报 `input_stale` 或 `conflict`，预算耗尽报 `budget_exhausted`；通过后沿用原 run，不传任何预算参数，不重置 `request_budget`、`candidate_attempts` 或 `repair_attempts`。
- 拒绝字段：`allow_unready`、`allow_unready_draft`、`draft`、`skip_gate`、`reset_budget`、`switch_task_origin`、`set_task_route`、`delete_b_origin`、`summary_override`、`forged_resume_command` 以及 Story 3.12 的 `SPOOFED_CLIENT_CACHE_KEYS`/`FORBIDDEN_BYPASS_KEYS`；`request_budget`/`active_budget_seconds`/`timeout_seconds` 仅允许用于 `3a_sources`（且禁布尔/非正整数）；NaN、空白字符串、未知字段、未知 `schema_version`、路径穿越与重解析点均以六字段诊断拒绝（路径先经 `_b_route_inventory.safe_input` 与 `no_reparse` 校验）。

## HTTP 与锁

- `GET` 不获取 `operation` 写锁，作业运行期间进度与诊断仍可读；未知/重复/空白参数返回 `422`，未知或重复 `mode` 返回 `400`，`strict=1` 在 `ok=false` 时返回 `422`。
- `POST` 需回环 `Host`、同源 `Origin`、`X-Project-Health-Token` 与严格 JSON；只读请求直接执行，变更动作获取单飞 `operation` 锁，忙时返回 `409`；结果 `ok` 返回 `200`，否则 `422`。

## 页面

- `project_health_planning.js` 提供 `formatBRouteDiagnostic`（仅 `textContent`）、`bRouteModeFor`、`loadBRoutePlanningState`、`invokeBRoutePlanningAction`、`renderBRouteProgressSummary` 与 `mountBRouteStagePanel`。
- 拓扑页 `#b-route-stage-panel` 按 `#topology-identity` 映射身份（`main` 对 `main`，工作区对 `attempt`/`stable`/`stabilized`），按阶段渲染 3A、3B（`Start New 3B Run` 与 `Resume Selected Run (preserves budget)` 分离）、3C 与 Chapter 6（只读推荐与执行分离）。
- 场景页 `#b-route-planning-progress` 区分已提交前缀与未提交候选，展示预算/撤销原因与六字段诊断，不影响原有 MVG 进度与清除。
- 知识页任务详情在存在 `b_route_identity` 时只读展示来源（`B`/`A`/`non_flow_governed`），提供 `Inspect recovery/route (read-only)` 与 `Run B-route gate check`，不提供切换来源或删除 B 标识的控件。

## 退出码与验证

CLI 在 `ok` 时退出 `0`，阻断或参数无效时退出 `2`；`--report` 仅写入非保留的 `logs/**/*.json`，`--events-log <logs/**/*.jsonl>` 按确定性 `event_id` 去重追加阶段事件（均拒绝符号链接/联接点及生产者保留目录/按日保留子树，写入异常折叠为六字段 `Diagnostic`）。

- `scripts/python/tests/test_b_route_planning_page.py`
- `scripts/python/tests/js/test_b_route_planning_page_ui.cjs`（经 `test_topology_frontend.py` 执行）
- 均由 `run_gate_bundle.py` 与 `.github/workflows/b-route-runtime-deterministic.yml` 纳入。
