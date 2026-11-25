# B 路线分层完成核对（单 Task、目标 Flow、累计 full-MVG 与合法非 Flow）

本文档定义 Story 4.5 的 owner 边界：在既有 Taskmaster、Stage-5 绑定、累计 MVG manifest、`VerificationScope`（Story 4.2）、`coverage-receipt.json`（Story 4.3/4.4）、原始 `.trx`/`results.xml` 报告、Chapter 7 目标 slice 收口（Story 3.11）与 `milestone_incremental_handoff.py` 之上，分别核对单 Task 局部完成、目标 Flow 完成、累计 `full-MVG` 里程碑完成与合法非 Flow `other_verification` 完成。不修改 `.taskmaster/tasks/tasks.json`、不在 `catalog.v1.json` 保存通过态、不推进发布指针、不建立第二状态机，也不默认启用 B 路线。

## Owner 与入口

- 核心核对服务：`scripts/python/_b_route_completion_verdict.py`（`SCHEMA = "newrouge.b-route-completion-verdict.v1"`，`MANUAL_SIGNOFF_SCHEMA = "newrouge.b-route-manual-signoff.v1"`）
  - 公共 API：`evaluate_completion_verdict(root, *, level, task_id=None, flow_id=None, manifest_path=None, verification_scope_path=None, receipt_paths=None, chapter7_slice_report=None, manual_signoff_path=None, milestone_handoff_path=None, operation="completion_verdict", report_path=None, events_log_path=None)`
- 只读 CLI 入口：`scripts/python/check_b_route_completion_verdict.py`，经 `py -3 -B scripts/python/dev_cli.py b-route-completion-verdict --level task|flow|milestone|non_flow ...` 调用。
  - 严格只读，拒绝 `--apply`/`--write`/`--commit`/`--mutate-tasks`/`--publish`/`--set-status`/`--mark-done`/`--claim-passed`/`--retire`。
  - 未传 `--report` 与 `--events-log` 时严格零落盘；`--report` 仅允许写入 `logs/**/*.json` 新文件（独占 `"xb"`），`--events-log` 经 `append_deduplicated_event` 按确定性 `event_id` 去重写入 `logs/**/*.jsonl`。
  - 退出码：`0` 表示所请求层级已获正式证明；`1` 表示阻断、未完成、过期、损坏、仅协议夹具或人工待签；`2` 表示 CLI 参数或路径非法。
- 里程碑交接适配：`scripts/python/milestone_incremental_handoff.py`
  - `build_task_handoff` / `validate_task_handoff` 新增可选 `verification_scope_path` 与 `b_route_verification_scope` 绑定（未传时 100% 保持既有行为）。
  - `validate_milestone_regressions` 支持可选 `verification_scope_path` / `receipt_paths` / `manifest_path` / `manual_signoff_path`，并新增 `validate_b_route_milestone_completion` 合并 handoff、三类义务与覆盖回执。

## AC-1：单 Task 局部通过与所属 Flow 完成严格分离

1. `--level task` 仅核对目标 Task 自身局部义务（`existing_required` + `current_new`），绝不因 `tasks.json` 旧 `done` 状态、结构关系、`planned` 占位或既有可运行代码豁免本次新增义务。
2. 即使该单 Task 自身局部义务 100% 满足（`task_local_satisfied=true`），核对器仍会检查 Stage-5 绑定、累计 manifest 与 `VerificationScope` 中关联的全部 Flow：只要同 Flow 存在任一未完成兄弟 Task、交接、未实现/未验证 `current_new` 义务、缺失 Chapter 7 UI 收口或未签人工项，`flow_completed` 恒为 `false`，`flow_status` 保持 `pending`/`blocked` 并精确列出 `missing_flow_obligations`（`missing_tasks`、`missing_tests`、`missing_implementations`、`missing_chapter7_slices`、`pending_manual_obligations`）。

## AC-2：目标 Flow 完成、证据等级严禁混代与专用集成 owner 免自锁

1. `--level flow` 实时校验并重验 `VerificationScope`（`validate_verification_scope` + `revalidate_verification_scope`）、验封 `coverage-receipt.json` 并从磁盘重新解析原始 `.trx`/`results.xml`（`_reverify_raw_reports`），同时核对适用 Chapter 7 UI 收口。
2. 严格执行证据等级不混代：
   - 要求 `engine-input` 的义务必须具真实 `engine-input` 且 `input_authenticity.player_action_input_detected=true`，严禁用 `scene-method` 或 `static-wiring` 顶替；
   - `scene-method` 严禁用 `static-wiring` 顶替；
   - `domain-xunit`/`domain-integration` 必须具重新解析通过的原始 `.trx`；
   - 协议夹具（`protocol_fixture_only=true` / `evidence_authenticity="protocol_fixture"`）永不满足真实运行 `flow_completed=true` 或 `runtime_verified=true`（仅置 `protocol_fixture_satisfied_only=true` 并阻断）；
   - 适用人工检查项必须提供绑定精确 `scope_id`、`snapshot_digest`、`manual_id`、审阅人与实质说明（`>= 12` 字符且不含 skip/waive 占位词）的 `newrouge.b-route-manual-signoff.v1`，机器测试永不替代人工（缺失时报告 `automated_flow_passed=true`、`manual_pending=true`、`flow_completed=false`）。
3. 专用集成 owner 豁免：结合 `_mvg_manifest._dedicated_integration_owner_task_ids` 与 Stage-5 绑定 `integration_only_owner` 角色，仅承担集成归属而非 `producer`/`consumer` 参与方的任务不因自身 `tasks.json` 尚未 `done` 阻断 Flow 验证或完成；非 `done` 的 `producer`/`consumer` 参与方任务仍阻断。

## AC-3：累计 full-MVG 里程碑完成与禁止跨 snapshot 拼接

1. `--level milestone` 要求累计 manifest 为 `coverage.mode == "full"`；传入 `pilot`/`critical`/`single_flow` 或部分范围结果时如实标注 `verified_scope`，且 `cumulative_full_mvg_completed=false`、`milestone_completed=false`。
2. 传入多份 `coverage-receipt.json` 时，所有回执必须共享完全一致的 `snapshot_digest`、`source_revision` 与 `workspace_dirty=false`（并匹配当前干净 Git `HEAD`）。一旦发现任意两份回执来自不同 snapshot 或 revision，立即以 `ReasonCode.CONFLICT`（`reason="cross_snapshot_report_splicing_forbidden"`、`cross_snapshot_splicing_detected=true`）fail-closed，严禁跨 snapshot 拼接绿灯报告。
3. 仅当非专用集成 owner 的参与任务全部 `done`、累计全部 `existing_required` + `current_new` + 跨 Flow 组合/交接测试与 `other_verification` 在同一干净整合 snapshot 上以真实二进制（`runtime_verified=true`、零 `not_run_blocking`、零跳过、零空报告）全部通过，且全部适用人工义务也在同一 `snapshot_digest` 签收后，才授 `cumulative_full_mvg_completed=true` 与 `milestone_completed=true`。

## AC-4：里程碑交接合并（失败旧 Flow A 与范围外/迁入范围 Flow B）

1. 受共享改动影响的旧 Flow A（`existing_required`）若失败或缺失，立即阻断 Flow A 与累计里程碑（`failed_existing_flows`），严禁将其重分类为 `planned` 或 `out_of_scope_future` 换绿，必须修复后在同 snapshot 完整回归。
2. 确实位于当前交付边界之外的受影响 Flow B（`out_of_scope_future`）保留定义/绑定更新与 `follow_up_responsibilities`（记入 `out_of_scope_future_tracked`、`forced_premature_future_implementation=false`），其自身状态保持 `completed=false`，不强迫提前实现以阻塞当前里程碑。
3. 一旦 Flow B 迁入当前交付边界（`current_new`），其任一未实现或未验证义务立即同时阻断 Flow B 与累计里程碑。旧 Flow/测试退役或减义务继续走 Story 4.2 显式防削弱审阅 delta。

## AC-5：损坏/过期/空报告拒绝、合法非 Flow 核对与零权威修改

1. 任意损坏、未知 schema、篡改封口、过期 `manifest`/`VerificationScope`/`InputSet`/`coverage-receipt.json`，或空/跳过/未执行的 `.trx`/`results.xml` 报告一律 fail-closed，并返回标准六字段 `Diagnostic`（`reason_code`、`stage`、`entity_id`、`expected`、`actual`、`resume_ref`）。
2. `--level non_flow` 核对合法非 Flow 需求：要求已提交规划中存在实质 `disposition="other_verification"` 豁免理由与匹配当前 `InputSet`/`snapshot_digest` 的真实 `other_verification` 通过证据；若 Story 4.1/4.2 范围显示该改动同时影响了 MVG Flow，必须一并通过受影响 MVG 回归。
3. 全流程恒声明 `task_status_mutated=false`、`catalog_mutated=false`、`publish_pointer_mutated=false`、`default_b_enabled=false`。

## 验证

- 单测：`py -3 -B -m unittest scripts.python.tests.test_b_route_completion_verdict scripts.python.tests.test_milestone_incremental_workflow scripts.python.tests.test_milestone_authority_regression scripts.python.tests.test_milestone_incremental_hotfixes scripts.python.tests.test_milestone_two_stage_integration scripts.python.tests.test_b_route_runtime_ci -v`。
- CLI：`py -3 -B scripts/python/dev_cli.py b-route-completion-verdict --help`。
