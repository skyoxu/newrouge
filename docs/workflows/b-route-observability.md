# B 路线可追溯过程观测与统一诊断

本文是 Story 4.8 的 owner 说明。共享只读服务 `scripts/python/_b_route_observability.py`（`newrouge.b-route-observability.v1`）同时被以下三端消费，不建分析库、不建第二状态机、不修改任何权威或发布指针：

- CLI：`py -3 -B scripts/python/dev_cli.py b-route-observability [--root <root>] [--operation-id <id>] [--run-id <id>] [--scope-id <id>] [--flow-id <id>] [--stage <stage>] [--task-id <id>] [--events-log <logs/**/*.jsonl> ...] [--baseline-ref <path>] [--verdict-ref <path> ...] [--report <logs/**/*.json>]`（直接入口 `scripts/python/query_b_route_observability.py`）。
- HTTP：只读 `GET /api/knowledge/b-route-observability[?operation_id=&run_id=&scope_id=&flow_id=&stage=&task_id=&baseline_ref=&strict=0|1]`（不取写锁，参数非法/空白/重复/未知返回 `422`）。
- 直接调用：`build_b_route_observability_report(root, ...)` 与页面只读展示 `window.renderBRouteObservability`（折叠面板 `<details data-b-route-observability data-knowledge-readonly>`）。

## 五维汇集与严格唯一计数

从有界 `logs/**` 来源汇集 3A 来源审计（含 `runner_dispatch_count`）、3B 规划运行（`capability_selection.calls`、`candidates/**/lineage-execution.json`、`dispatch-receipts/dispatch-*.json`）、3B/3C/4/5 受治理操作与日志（含 `b-route-task-compilation/**/events.jsonl`）、Chapter 6 本地运行/返工/恢复、`mvg-acceptance` 运行回执及显式 `--events-log`（绝不对 `logs/ci/mvg-planning` 或 `logs/ci/capability-planning` 做 `rglob`，未指定 `--run-id` 时仅检查最新 50 个顶层运行目录，超限时在 `data_gaps` 记录 `bounded_scan_truncated`）：

- 五维索引：`operation_or_run_id`、`scope_or_flow_id`、`stage`、`attempt` 与规范化 `event_id`。
- 相同规范化 `event_id`（算法与 `_b_route_evidence_reuse.append_deduplicated_event` 一致）与重复 `--verdict-ref` 仅计 1 次（过滤与去重在累加耗时/dispatch/复用前完成）；真实重试（不同 `attempt` 或不同运行序次）全部保留。
- 3B 运行内的协调器 `capability_selection.calls` 预留（`reservation_id` + 规范化 `request_identity`）、worker `lineage-execution.json`/投影与对应 `dispatch-receipts/dispatch-*.json` 关联为 **1 笔** 实际调用；`status == "reserved"` 且无执行 outcome 的预留单列于 `reserved_only_not_dispatched`，绝不叠加为多次模型调用，且 `run.json` 汇总耗时不与单笔 dispatch 耗时重复相加。
- 每条事件附 `executor`（`producer`/`runner`/`consumer`）、`original_locator`（仓库相对 POSIX 路径 + `sha256`）、实测活动耗时（严格区分 `0.0` 与 `"unknown"`，拒绝 `bool` 强转）、构建预热计数、同快照重复执行测试检测（事件级与顶层同步填充）、复用来源、`return_stage` 与终止原因。

## 实测、暂停墙钟、预留与 `"unknown"` 分列

- `timing_and_cost_summary` 严格分列：`observed_active_elapsed_seconds`（未实测事件标 `"unknown"`，绝不伪造 `0.0`）、`paused_or_wall_clock_seconds`（恒标 `paused_wall_clock_is_active_elapsed=false`）、`reserved_request_budget`（含 `mvg.run_invocation_limit`）、`observed_actual_dispatches`、`reserved_only_not_dispatched`、`model_estimated_metrics`（恒标 `estimated_not_billed=true`）与 `billed_cost`（无已核验账单回执时恒为 `"unknown"`）。
- `baseline_comparison`：未提供 `--baseline-ref` 时返回 `available=false, comparable=false, status="unknown"`，绝不伪造基线；提供历史基线时校验 `.json` 后缀与 `schema_version`，仅在当前与基线均具备匹配的非空 `scope`/`flow` 及非空义务集合时报告 `comparable=true`，且仅当双方 `overall_active_elapsed_complete=true` 时计算数值耗时差值（否则为 `"unknown"`）。
- `governance_thresholds` 恒为全 `false`：不设提速、降成本、两小时墙钟、固定 Task 数或工时门槛。

## 统一六字段诊断与九类错误隔离

- 所有错误仅复用现有 `_b_route_codec.ReasonCode` 与 `_b_route_codec.Stage` 枚举成员，输出完整六字段 `Diagnostic`（`reason_code`、`stage`、`entity_id`、`expected`、`actual`、`resume_ref`，不适用项序列化为 JSON `null`），`diagnostic_category` 严格由已校验的 `ReasonCode` 与错误来源派生（绝不轻信磁盘原始类别字段，如 `invalid_json`/缺证映射为 `corrupt_reference`、`digest_mismatch`/过期映射为 `drift_or_stale`）。
- 执行/运行器故障恒为 `execution_fault`，永不改写为 `semantic`；同一运行/范围同时存在 `budget`（`budget_exhausted`）与 `semantic`/`execution_fault` 时全部保留，互不掩盖。HTTP `422` 统一经 `normalize_unified_diagnostic` 返回 `reason_code`、`diagnostics` 与 `categories_present`。
- 损坏 JSON/JSONL、未知 `schema_version`（含 JSONL 行与基线）、祖先/悬空重解析点或摘要不符永不静默吞掉，均经去重落入 `diagnostics` 与 `data_gaps` 并使 `ok=false`。
- 页面 `renderBRouteObservability` 仅使用 `textContent` 原样展示 `[diagnostic_category]` 与六字段诊断，缺摘要子对象时渲染 `"unknown"`（不伪造 `0`），展示 `deterministic_stop_loss`，并在面板展开时随 `refresh()` 自动刷新。

## 三类复用严格隔离

`reuse_breakdown`（`cross_class_proof_allowed=false`）将三类复用分桶报告，互不替代、互不互证：

1. `planning_adoption_reuse`：Story 2.9 规划能力采纳复用（`registry.json`、`completed-recovery`、`run.json` 采纳记录），按 `(source_transaction_id, target_run_id, capability_id)` 去重并优先暴露 `revoked`/epoch 失效条目。
2. `apply_idempotent_noop`：Story 2.7/2.8/3.2/3.4/3.6 事务日志与 `.pending.json` 重放，按 `(operation_id, target_path, phase)` 去重（`idempotent_noop` / `applied` / `conflict_blocked`）。
3. `runtime_build_and_test_reuse`：Story 4.4 `coverage-receipt.json` 中的 `dotnet_build`、`godot_prewarm` 与同快照共享测试去重（`shared_test_evidence`），原样保留 `original_executed_at`；若出现跨类互证、缺失 `original_executed_at` 或将旧时间戳刷新为复用运行时间，即以 `conflict` 阻断（`ok=false`），零隐式全局 Knowledge 刷新。

## 缺口、止损、返工与不可抵消的质量底线

- 显式暴露 `data_gaps`、`stop_loss_signals`（`rerun_guard`、`llm_retry_stop_loss`、`sc_test_retry_stop_loss`、`waste_signals`、`deterministic_stop_loss`、`no_progress_retries`）与可定位的 `rework_returns`（`from_stage`、`return_stage`、`defect_class`、`original_locator`）。
- `quality_floor`（`process_metrics_can_offset=false`）核查五类不可抵消退化（覆盖 3A `semantic_blockers`/`unaccounted_blocks`/`omitted_requirements`、3.10 `na_exemption`/`acceptance_weakening`/`test_deletion`/`status_tampering` 及 4.5 `evidence_tier_violations`/`skipped_tests`/`missing_flow_obligations`/`cross_snapshot_splicing_detected`/`forced_premature_future_implementation`）：`source_omission`、`mature_identity_drift`、`unverified_obligation`、`failure_reclassification`、`premature_out_of_scope_implementation`。命中任一退化时 `quality_floor.violated=true` 且 `ok=false`，即使耗时极短、dispatch 为 0 或复用率 100% 亦不得放行。

## 退出码与验证

- 严格只读，拒绝 `--apply`/`--write`/`--commit`/`--publish`/`--mutate-tasks`/`--set-status`/`--refresh-knowledge`；`--report` 仅允许写入非保留 `logs/**/*.json`（拒绝所有生产者目录、按日生产者子树及符号链接/联接点）。
- `ok=true` 退出 `0`；存在损坏日志、跨类复用/时间戳冲突、质量底线退化或参数错误时退出 `2`。
- 验证套件：`scripts/python/tests/test_b_route_observability.py` 与 `scripts/python/tests/js/test_b_route_planning_page_ui.cjs`（经 `test_topology_frontend.py` 执行），已纳入 `run_gate_bundle.py` 与 `.github/workflows/b-route-runtime-deterministic.yml`。
