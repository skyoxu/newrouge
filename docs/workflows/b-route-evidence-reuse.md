# B 路线构建预热复用、共享测试证据去重与可变状态隔离

本文档定义 Story 4.4 的 owner 边界：在既有 MVG 执行器与运行证据读取路径（`logs/ci/mvg-acceptance/<run-id>/summary.json`、`coverage-receipt.json`、`input-manifest.json` 及原始 `.trx`/`results.xml`）上实现按身份核验的构建/预热复用、同整合快照共享测试去重与逐测试可变状态隔离。不新建第二套 Task/MVG 完成缓存或第二证明格式，不设置提速或成本下降门槛，不把构建复用当测试通过，不把规划完成项 adoption 混充运行测试证据，不自动写 Task 状态或默认启用 B 路线。

## Owner 与入口

- 核心复用与状态隔离 owner：`scripts/python/_b_route_evidence_reuse.py`
  - 构建/预热身份与复用：`compute_build_artifact_identity`、`evaluate_build_reuse`、`load_prior_build_record`
  - 共享测试身份与跨运行同快照复用：`compute_test_evidence_identity`、`evaluate_test_evidence_reuse`、`collect_requirement_route_coverage`
  - 逐测试可变状态隔离与快照只读核验：`prepare_isolated_test_env`、`capture_snapshot_file_hashes`、`verify_post_test_isolation`
  - 确定性事件去重：`append_deduplicated_event`
  - 校验边界：`verify_receipt_seal`、`is_planning_adoption_payload`
- 执行器集成：`scripts/python/_b_route_scope_runner.py`、`scripts/python/run_mvg_acceptance.py`、`scripts/python/_mvg_execution.py`、`scripts/python/dev_cli.py`、`scripts/python/dev_cli_builders.py`。
- 公共 CLI 参数（`dev_cli.py run-mvg-acceptance --verification-scope <path> ...`，未带 `--verification-scope` 传入以下参数一律 fail-closed）：
  - `--reuse-evidence-from <path>`（可重复）：指定既有 `logs/ci/mvg-acceptance/<prior-run>` 目录或已封存 `coverage-receipt.json` 进行同快照共享测试证据核验复用。
  - `--reuse-build-from <path>`：指定既有 `logs/ci/mvg-acceptance/<prior-run>` 目录在源内容、工具链与完整 `bin`/`obj` 或 `.godot` 工件哈希匹配时复用只读构建/预热输出。
  - `--events-log <logs/.../*.jsonl>`：将构建评估、测试执行/复用、拒绝原因与运行结论按规范化 `event_id` 经侧车 `.lock`（Windows `msvcrt.locking`）去重写入 `.jsonl` 事件日志。

## AC-1：构建/预热复用与测试结果复用严格分离

1. `dotnet_build` 身份哈希隔离快照内全部 `.cs`/`.csproj`/`.sln`/`Directory.Build.*`/`global.json`/`nuget.config`、`dotnet_version`、`configuration` 与完整编译输出（`Game.Core` 与 `Game.Core.Tests` 的 `bin/<config>/**` 与 `obj/**`，含 `.dll`/`.deps.json`/`.runtimeconfig.json`/`testhost*`/`project.assets.json` 等）。仅当完全匹配、先序运行零漂移且零快照污染且工件完整存在时，后续 `dotnet test` 才可传入 `--no-build` 并记录 `source_run_id`、`source_step_id`、`original_created_at` 与 `match_reason`。
2. `godot_prewarm` 身份哈希 `.cs`/`.gd`/`.tscn`/`.tres`/`project.godot`/`Tests.Godot/project.godot`、`Tests.Godot/addons/gdUnit4/**`（排除可再生 `.import` 与 `.gd.uid`/`.cs.uid`）、`godot_version` 与 `.godot` 预热缓存。仅当匹配且缓存存在时才跳过重复 `--prewarm`。
3. 构建/预热复用绝不跳过测试执行，也绝不等于测试通过（`build_reuse_implies_test_pass=false`）。未命中构建的真实耗时如实记入 `metrics.missed_build_elapsed_seconds` 与 `metrics.observed_elapsed_seconds`，区分 `reserved_dispatches` 与 `observed_dispatches`，绝不以预算预留相减宣称省钱（`reserved_budget_claimed_as_savings=false`）。

## AC-2：同整合快照多 Flow 共享测试去重与唯一计数

1. 运行内多 Flow 共享同一测试时，仅在完整测试身份（`test_id`/`kind`/`path`/`selector`/`min_tests`/`evidence_level`/`challenge`）一致时去重只执行一次，挂接全部 `referencing_flow_ids` 与仅属于当前 Flow 集合的 Requirement 唯一验证处置及多路线 `observable_roles`。`coverage_summary.unique_executed_test_count` 只计一次，不按 Flow 数量膨胀完成计数（`flow_count_inflation_prevented=true`）。
2. 跨运行 `--reuse-evidence-from` 必须全部满足：
   - 既有 `input-manifest.json` 与已封存 `coverage-receipt.json`（重验 `receipt_id` 封存、零漂移、零污染且 `command_record` 位于归属运行目录内）完整无篡改；不接受未封存 `summary.json` 单独降级回退；
   - 重新解析磁盘原始 `.trx`/`results.xml`（经 `read_test_evidence`）全部通过，防摘要篡改冒充 PASS；
   - 精确匹配 `snapshot_digest`、`source_revision`、`workspace_dirty`（严禁跨整合快照拼接证据）；
   - 精确匹配 `test_relevant_input_digest`、验证语义（`challenge`/`input_authenticity`/`evidence_authenticity`，协议夹具结果永不能满足真实二进制运行）与工具链身份；
   - 仅同名或同类名但 `path`/`selector`/`min_tests`/`evidence_level`/相关输入/快照不同的测试一律拒绝合并。

## AC-3：逐测试可变状态隔离与人工义务独立

1. `run_mvg_acceptance.py` 与 `_b_route_scope_runner.py` 均为每个测试步骤与 challenge 步骤创建全新隔离目录 `isolated-user-data`（`APPDATA`/`LOCALAPPDATA`/`XDG_DATA_HOME`/`XDG_CONFIG_HOME`）与 `isolated-temp`（`TEMP`/`TMP`），绝不在顺序测试间共享可变用户数据目录。
2. 每次测试结束后执行 `verify_post_test_isolation`，核查隔离快照内受跟踪业务文件是否被测试篡改；一旦发现状态污染，立即以 `status="blocked"`、`reason_code="mutable_test_state_pollution_detected"` fail-closed 并中止后续测试，防止换序或重入继承脏状态。
3. 仅允许共享只读构建/预热工件；人工义务恒保持 `status="manual_pending"` 与 `manual_satisfied_by_machine_reuse=false`，即使自动化测试 100% 复用或通过也不得由机器结果代替。

## AC-4：漂移/损坏拒绝、无关变化稳定与 Story 2.9 分离

1. 相关源码、契约、规则、场景、测试、`snapshot_digest`、`workspace_dirty` 任一漂移，或 `coverage-receipt.json`/`input-manifest.json`/原始 `.trx`/`.xml` 损坏均拒绝复用，并在 `reuse_rejections` 中记录结构化 `entity_id`/`candidate`/`reason_code`/`reason`。
2. 真正位于整合快照与测试相关输入之外的无关变化（例如 `logs/**` 新增无关日志或未改变 `snapshot_digest` 与 `test_relevant_input_digest` 的外部元数据）不误废有效同快照复用。
3. 显式拒绝将 Story 2.9 规划完成项 adoption 回执（如 `newrouge.mvg-capability-adoption.v1` 或正式规划记录）作为运行测试证据传入（`reason_code="planning_adoption_not_runtime_evidence"`，`planning_adoption_interchangeable=false`）。

## AC-5：原时间戳保留、事件去重与零速度/成本门槛

1. 每条复用测试在 `coverage-receipt.json` 与 `summary.json` 中必须保留原始 `original_executed_at`、设置 `reused=true`、`freshly_executed=false`、`reused_from_run_id`、`reused_evidence_id`、`match_reason`，严禁以当前时间刷新旧 PASS 时间戳冒充新运行。
2. `--events-log` 经 `append_deduplicated_event` 按规范化 `event_id` 写入，重复发射相同事件自动去重不写重复行。
3. 覆盖回执恒声明 `speedup_or_cost_gate_enforced=false`、`reserved_budget_claimed_as_savings=false`、`build_reuse_implies_test_pass=false`、`manual_satisfied_by_machine_reuse=false`、`planning_adoption_interchangeable=false`。

## 验证

- 单测：`py -3 -B -m unittest scripts.python.tests.test_b_route_evidence_reuse scripts.python.tests.test_b_route_scope_runner scripts.python.tests.test_mvg_acceptance -v`。
- CI：`run_gate_bundle.py` 与 `.github/workflows/b-route-runtime-deterministic.yml` 纳入 `test_b_route_evidence_reuse`，`test_b_route_runtime_ci.py` 守护接线。
