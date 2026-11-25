# B 路线真实执行器消费 VerificationScope 与覆盖回执

本文档定义 Story 4.3 的 owner 边界：改造既有 MVG 执行器消费 Story 4.2 封存的 `VerificationScope`（`newrouge.b-route-verification-scope.v1`），在隔离快照与业务 scope 租约下真实执行声明范围或显式保守超集，并生成带六类证据等级、未运行原因与工具链真实性边界的正式覆盖回执（`newrouge.b-route-execution-receipt.v1`）。不承诺提速，不自动修改 Task 状态，不授予 Task/Flow/里程碑完成或默认启用 B 路线。

## Owner 与入口

- 范围消费与覆盖回执 owner：`scripts/python/_b_route_scope_runner.py`（`run_scoped_mvg`、`inspect_scoped_static_wiring`、`inspect_gdunit_input_authenticity`、`probe_environment`）。
- 子进程与报告证据 owner：`scripts/python/_mvg_execution.py`（`execute_test`、`read_test_evidence`、`run_child`，逐测试落盘 `command.json`、`console.log` 与原始 `.trx`/`results.xml`）。
- 执行入口：`scripts/python/run_mvg_acceptance.py` 与 `py -3 -B scripts/python/dev_cli.py run-mvg-acceptance`。
- 命令构造器：`scripts/python/dev_cli_builders.py`（`build_run_mvg_acceptance_cmd`）。
- 新增参数（不传 `--verification-scope` 时 100% 兼容原有 `run_mvg_acceptance.py` 行为）：
  - `--verification-scope <repo-relative.json>`：经 Story 4.2 校验并实时复验的 `VerificationScope`。
  - `--execution-strategy scoped|conservative_superset`（默认 `scoped`）：`scoped` 仅执行范围声明测试与静态接线；`conservative_superset` 或 4.1 强制保守扩大时执行 manifest 全部已实现测试并显式记录 `superset_executed=true`、`selective_execution_claimed=false` 与 `superset_extra_tests`。
  - `--dotnet-bin <path>`：默认 `DOTNET_BIN` 或 `dotnet`；支持受控协议夹具脚本并诚实标记真实性。
  - `--protocol-fixture`：显式标记协议夹具（脚本/wrapper 路径也会自动检测），恒置 `runtime_verified=false`。
  - `--stop-on-deterministic-failure` / `--no-stop-on-deterministic-failure`（默认开启）：确定性前置（`static-wiring` 或 `domain-xunit`）失败后止损，跳过下游昂贵 `gdunit` 进程并在 `not_run` 记录原因。
  - `--reuse-evidence-from <path>`（可重复）：指定既有同整合快照运行目录或 `coverage-receipt.json` 核验复用共享测试证据（详见[构建与共享证据复用 owner 说明](b-route-evidence-reuse.md)）。
  - `--reuse-build-from <path>`：指定既有运行目录在源内容、工具链与工件摘要一致时复用只读构建/预热工件（不等于测试通过）。
  - `--events-log <logs/.../*.jsonl>`：写入按规范化 `event_id` 去重的执行/复用/拒绝事件日志。

## 消费范围、隔离快照与业务租约

1. 执行前先调用 `validate_verification_scope` 校验 schema、`scope_id` 与内部一致性，再调用 `revalidate_verification_scope` 核对实时新鲜度；未知 schema、篡改 `scope_id` 或已漂移输入直接阻断。
2. 核对 `--manifest` 位于 `VerificationScope.authority_refs` 且磁盘与隔离快照 `manifest_sha256` 一致，且 manifest 未缺少范围必需的已实现测试；缺项或错 manifest 直接阻断。
3. 通过 `_b_route_operation_scope.business_guard(..., review_only=True)` 获取短 metadata 锁并仅持有当前业务 scope（`plan`/`flow`/`task`/`requirement`/`target_paths`）的 Windows `msvcrt` 租约，绝不长占全局 `WRITER_SCOPE`；重叠租约争用以 `conflict` 阻断，互不相交范围可并行。
4. 复用 `prepare_snapshot` 构建 `logs/ci/mvg-acceptance/<run-id>/snapshot`、`input-manifest.json` 与 `snapshot_digest`。

## 正式覆盖回执与防伪 PASS

每次运行输出 `logs/ci/mvg-acceptance/<run-id>/coverage-receipt.json`（`schema_version="newrouge.b-route-execution-receipt.v1"`，含规范化 `receipt_id`）并挂载到 `summary.json`：

- 绑定同一 `scope_id`、`input_set_digest`、`manifest`、`manifest_sha256`、`source_revision` 与 `snapshot_digest`。
- 完整列示 `requested_tests`、`executed_tests`（含精确命令、`command_record`、退出码、用例统计、日志与报告路径）、`not_run`（含 `reason_code`、`reason` 与 `blocking_current_delivery`）、`manual_obligations`（恒 `status="manual_pending"`、`verified_by_runner=false`）与 `out_of_scope_future_obligations`（恒 `claimed_passed=false`）。
- 漏项、空报告、`0` 用例、跳过用例、`planned` 义务、阻断待办、漂移、租约争用或止损均阻断 PASS（`automated_scope_passed=false`、`runtime_verified=false`、退出码 `1`）。
- 失败或无法启动的 `existing_required` 回归保持 `tier="existing_required"`，绝不重分类为 `out_of_scope_future`。

## 六类证据等级与真实性边界

1. `domain-xunit`：C# xUnit 领域测试（保留原 manifest `domain-integration` 映射）。
2. `godot-gdunit`：通用 GdUnit4 引擎测试。
3. `static-wiring`：在隔离快照中核查 `.tscn`、`[ext_resource]`、节点路径、`[connection]` 信号绑定、交互 `Button` 的 `pressed` 接线与 C#/GD 适配器类型及生命周期；断开必要信号或节点绑定必败。
4. `scene-method`：直接调用场景方法的 GdUnit4 测试。
5. `engine-input`：扫描 `.gd` 测试及预加载辅助脚本，区分夹具初始化（`fixture_setup_detected`）与真实引擎输入（`player_action_input_detected`，如 `InputEventAction`/`push_input`/`parse_input_event`），拒绝无真实引擎输入或调用 `*ForTest` 后门/手工 `emit_signal("pressed")` 冒充玩家输入。支持 `--challenge-input` 断线断言反例。
6. `manual`：人工验收义务单独记为 `manual_pending`，不混入自动化通过计数。

## 漂移、止损与协议夹具限制

- 运行前与运行后均执行 `revalidate_verification_scope` 与 manifest 摘要复核；运行中发生漂移时阻断结论（`reason_code="input_stale"`、`runtime_verified=false`）并保留全部已执行步骤。
- 运行前检查范围任务的持久止损信号（`rerun_guard`、`sc_test_retry_stop_loss`、`llm_retry_stop_loss`、`waste_signals` 等）；运行中前置确定性失败按 `--stop-on-deterministic-failure` 止损。
- 回执记录真实 Windows 版本、Python/dotnet/Godot 版本与 `unverified_exclusions`。使用协议夹具脚本时恒标记 `protocol_fixture_only=true`、`evidence_authenticity="protocol_fixture"` 与 `runtime_verified=false`（`status="passed_protocol_fixture_only"`），仅证明适配与报告解析，绝不冒充真实 Godot 玩法通过。

## 验证

- 单测：`py -3 -B -m unittest scripts.python.tests.test_b_route_scope_runner scripts.python.tests.test_b_route_evidence_reuse scripts.python.tests.test_mvg_acceptance -v`。
- CI：`run_gate_bundle.py` 与 `.github/workflows/b-route-runtime-deterministic.yml` 纳入 `test_b_route_scope_runner` 与 `test_b_route_evidence_reuse`，`test_b_route_runtime_ci.py` 守护接线。
