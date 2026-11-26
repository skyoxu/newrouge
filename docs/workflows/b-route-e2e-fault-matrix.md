# B 路线 Windows 故障注入与共享变更端到端核对（Story 4.10）

本文是 Story 4.10 的 owner 说明。共享只读端到端核对服务 `scripts/python/_b_route_e2e_fault_matrix.py`（`newrouge.b-route-e2e-fault-matrix.v1`）与公共 CLI `py -3 -B scripts/python/dev_cli.py b-route-e2e-matrix`（直接入口 `scripts/python/verify_b_route_e2e_fault_matrix.py`）用于在隔离临时 Windows 目录内串联 Epic 2–4 正式入口，注入真实 Windows 锁争用与六阶段子进程退出/重启故障，核对跨 scope 共享 Task 演进、Flow A/B 共享变更演进、共享测试证据隔离与真伪鉴别、以及规划页面/Knowledge 投影/过程观测一致性，并结合 Story 4.9 只读消费者对齐审计产出可重建的 Epic 4 -> Epic 5 交接就绪报告。本入口对目标 `--root` 严格只读，不修改业务权威文件、不切默认 B、不退役 A 写入兼容、不隐式刷新 Knowledge，绝不把协议夹具冒充为真实 Godot/C# 奖励验收证据。

- 公共 CLI：`py -3 -B scripts/python/dev_cli.py b-route-e2e-matrix [--root <root>] [--skip-fault-harness] [--report <logs/**/*.json>]`
- 直接入口：`py -3 -B scripts/python/verify_b_route_e2e_fault_matrix.py [--root <root>] [--skip-fault-harness] [--report <logs/**/*.json>]`
- 禁止标志：拒绝 `--apply`、`--switch-default-b`、`--retire-a`、`--write-tasks`、`--publish`、`--refresh-knowledge`、`--write`、`--commit`、`--mutate-tasks`、`--set-status`（退出码 `2`）。
- `--skip-fault-harness` 严格 fail-closed：跳过隔离临时 Windows 故障与共享变更活体矩阵时，`epic4_capabilities_verified=false`、`ok=false`，输出六字段诊断并以退出码 `2` 退出，绝不宣称通过。
- `--report` 预检与防覆盖约束：仅允许仓库相对非保留 `logs/**/*.json`（拒绝所有生产者保留目录、带日期生产者子树、已存在文件与符号链接/联接点），并采用原子新建写入，确保磁盘 JSON 与 stdout JSON 一致。

## 一、真实 Windows 锁争用与六阶段故障注入（AC-1）

在 `os.name == "nt"` 环境下启动真实子进程持有真实 `msvcrt.locking` OS 字节锁（`capability-coordinator.lock`），以 `taskkill /F /T` 强杀子进程验证锁争用阻断与 OS 自动释放；并在全部 6 个提交生命周期阶段执行真实子进程中断与恢复核对：

1. `prepare`：子进程准备阶段中止、正常准备、同 `operation_id` 同内容幂等重放、同 `operation_id` 异内容确定性 `conflict` 拒绝。
2. `reserve`：预留阶段中止与重启幂等恢复，校验不提前写正式目标且活体任务状态不变。
3. `apply`：部分目标落盘后中止（`after_target:0`），核对 `_b_route_commit.read_committed`、Knowledge 投影、规划页面与 Chapter 6 门禁一致阻断零混合消费；核对人工后编辑原样保留不被覆盖；干净状态经 `recover` 续跑完成发布。
4. `verify`：回执落盘而 `catalog.v1.json` 尚未发布时中止，核对回执不构成发布；注入截断损坏 journal，核对确定性阻断且零静默修复。
5. `publish`：`catalog.v1.json` 替换后、`commit.pending.json` 清理前中止，核对待清 `.pending` 仍阻断消费，恢复清理后 `catalog.v1.json` 字节原样保留。
6. `recover`：恢复中途再次崩溃并重启，核对最终原子发布、再次 `recover` 为纯 `noop` 且不重写正式目标、完成后同 ID 异内容仍拒、`tasks.json` 既有 `done`/`in-progress` 活体状态全程保留。

### 实测平台证据与未测 Windows 边界

- 报告输出 `platform_evidence`：`os_name`、`platform`、`python_version`、`used_real_windows_msvcrt_lock`、`used_real_child_process_termination`、`mock_os_exception_claimed_as_windows_proof=false`，严禁用 mock 异常冒充真实 Windows 锁或持久化验证。
- 报告显式列明用户态 CI 无法模拟的 `untested_windows_boundaries`：
  - `hardware_power_loss_and_disk_controller_write_cache_flush`（硬件断电与磁盘写缓存未落盘）
  - `windows_kernel_bugcheck_bsod_or_unexpected_host_reboot`（Windows 内核蓝屏或宿主机硬重启）
  - `ntfs_filter_driver_antivirus_async_quarantine_or_volume_unplug`（NTFS 过滤驱动/杀软异步隔离或卷热拔出）
  - `bitlocker_volume_lock_or_smb_network_share_disconnect`（BitLocker 卷锁定或 SMB 网络共享断链）
  - `real_godot_451_windows_gui_input_and_csharp_reward_runtime`（真实 Godot 4.5.1 窗口输入与 C# 奖励生产运行链路，归 Epic 5）

## 二、共享 Task 多 Scope、漂移、旧 Pending 与防绕过（AC-2）

- 核对共享 Task 在 Scope 1 基础上被新采纳 Scope 2 接入时，`applicable_set_digest` 在 `_b_route_task_resolver`、`_b_route_input_set`、Chapter 6 门禁、`resume-task`/`chapter6-route`、页面触发与 Knowledge 投影上一致扩张并失效旧单计划 readiness，同时无关 Scope 3 照常不受影响。
- 核对来源漂移仅阻断受影响 scope；注入旧未知 `apply-journal.json` / `capability-apply.pending.json` 阻断并指向 `resume_ref`，按 `plan_capabilities.apply` 原合同清理后 B 路线 scope 保持完整。
- 反绕过负控：删除 `task-origins.v1.json`、删除 MVG manifest、删除 commit 回执或注入伪 `N/A`/`mvg:n/a` 标签，均严格保持 `blocked`，绝不静默降级为旧 A 或误判通过。
- 正反例核对：专用 `integration_only_owner` 任务在合法绑定下不造成 Flow 自锁、缺少合法绑定时阻断；合法非 Flow `other_verification` 在 `rationale` 与 `other_verification_refs` 完整时通过、缺失或损坏时阻断。

## 三、Flow A/B 共享变更演进（AC-3）

串联 Story 4.1（影响闭包）→ 4.2（VerificationScope）→ 4.3（范围执行器）→ 4.5（分层完成核对）：

- 阶段 1（`Flow B` 在当前交付边界外）：共享契约变更同时命中已实现 `Flow A`（`existing_required`）与未实现 `planned` `Flow B`（`out_of_scope_future`）；`Flow A` 启动或执行失败时 4.3/4.5 严格阻断，拒绝将失败 `Flow A` 重分类为 `planned` 或换用旧 manifest 掩盖失败；修复 `Flow A` 后其协议夹具全回归通过（`runtime_verified=false`、`environment.protocol_fixture_only=true`、`environment.evidence_authenticity="protocol_fixture"`），`Flow B` 保留在 `out_of_scope_future` 中不宣称通过也不强迫提前实现。
- 阶段 2（将 `Flow B` 移入当前交付边界但尚未实现/测试）：重建 `VerificationScope` 后 `Flow B` 进入 `current_new`，完成核对确定性阻断直至实现与验证补齐，且声明范围与 `coverage-receipt.json` 一致。

## 四、共享证据复用、隔离与真伪鉴别（AC-4）

- 多 Flow 共享测试在同一快照内仅执行 1 次，且每个测试均获得独立可变目录（`APPDATA`/`LOCALAPPDATA`/`TEMP`）零状态串扰与零快照污染；同快照复用保留原始 `original_executed_at`。
- 不同 `snapshot_digest` / `source_revision` 回执拼接累计 `full-MVG` 里程碑时，确定性触发 `cross_snapshot_splicing_detected` 阻断。
- 空测试报告（`total=0`）、跳过测试（`skipped>0`）、无真实 `InputEvent` 的场景方法直调、`ForTest` 后门及缺少独立人工签收，一律阻断冒充 `engine_real_input` 或 `manual_independent`；单 Flow/`partial`/`critical` 显式标明真实范围，协议夹具恒定 `runtime_verified=false`。

## 五、三视图一致性与零隐式刷新（AC-5）

- 在失败、`mvg-clear` epoch 递增、Story 2.9 `reopen` 撤销与 journal 恢复场景下，规划页面（`_b_route_planning_page`）、Knowledge 投影（`_b_route_knowledge_projection`）与过程观测（`_b_route_observability`）保持快照身份、`ReasonCode` 与六字段 `Diagnostic` 一致。
- 被 epoch 或 `reopen` 撤销的运行在重复 `resume` 或页面刷新下永不复活；`workspace_preview`/`attempt` 模式保持 `knowledge/indexes/current.json`、`last-known-good.json`、`latest.json` 与 `refs/heads/main` 字节完全不变；Chapter 6/Review/Recovery 零隐式全局刷新。
- 过程观测严格分列 `unknown` 费用与实测活动耗时/暂停墙钟/预留预算，且快速零调度过程指标严禁抵消质量底线违例（`ok=false`、`process_metrics_can_offset=false`）。

## 六、Epic 4 -> Epic 5 交接就绪清单（AC-6）

`epic5_handoff_readiness_report` 汇总实时 Story 4.9 对齐结论（见[消费者对齐与切换前审计 owner 说明](b-route-consumer-alignment.md)）与 AC-1..AC-5 端到端结果，固定 `protocol_fixture_is_not_reward_gameplay_acceptance=true`、`runtime_verified=false`、`default_b_enabled=false`、`a_write_compatibility_retired=false`，并显式将以下 4 项留待 Epic 5：

1. `reward_production_csharp_thin_adapter_and_controlled_command`（Stories 5.1–5.6）
2. `reward_dual_path_real_windows_godot_csharp_evidence`（Stories 5.2、5.3、5.7）
3. `conditional_default_b_switch_for_new_requirements`（Story 5.8）
4. `independent_a_exit_gate_and_actual_revocation`（Stories 5.9–5.11）

验证套件：`scripts/python/tests/test_b_route_e2e_fault_matrix.py`，已纳入 `scripts/python/run_gate_bundle.py`、`scripts/python/tests/test_b_route_runtime_ci.py` 与 `.github/workflows/b-route-runtime-deterministic.yml`。
