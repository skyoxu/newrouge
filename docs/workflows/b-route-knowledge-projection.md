# B 路线派生规划、实施与运行身份投影

本文是 Story 4.6 的 owner 说明。入口为只读命令 `py -3 scripts/python/dev_cli.py b-route-knowledge-projection` 与 HTTP `GET /api/knowledge/b-route-projection`，二者共用 `scripts/python/_b_route_knowledge_projection.py` 的 `build_b_route_knowledge_projection`。

## 边界

- 只读派生：从原始权威（Chapter 3 来源集、semantic-topology、Taskmaster 三联、MVG manifest、契约与场景文件）与已提交 `docs/planning/b-route/catalog.v1.json` 链构建投影，不反写来源、`catalog.v1.json`、`tasks.json`，不推进 `knowledge/indexes/current.json`、`last-known-good.json`、`logs/ci/project-health-knowledge/latest.json` 或 `runtime/latest.json`。
- 不修改 7 个 FORMAL schema、`ReasonCode`/`Stage` 枚举或 KCP 控制面文件；`ADR-0035` 的 trusted-ref 门禁与 `source-exclusions.v1.json` 只被只读核对。
- 普通 Chapter 6、Review、Recovery 消费者零隐式全局刷新；注册刷新仍只由 `refresh_chapter_knowledge`（`chapter3`/`chapter5`）负责，并区分 Attempt、Latest Successful 与 Stabilized 工作区视图。

## 十层关系与四维状态

投影输出 `sources`、`requirements`、`capabilities`、`flows`、`four_parts`、`tasks`、`contracts`、`scenes`、`obligations` 与 `impact` 十层，以及 `edges`。每个节点独立携带：

- `planning_state`：`legacy_unmapped`、`3b_adopted_awaiting_3c`、`partial_planning`、`3c_compiled`、`stage4_bound`、`stage5_bound`、`non_flow_governed`、`planned_future`、`stale`、`blocked`、`revoked`。
- `implementation_state`：`no_task_yet`、`pending`、`in_progress`、`done_in_taskmaster`、`planned_unimplemented`、`not_applicable_non_flow`；结构关系永不推出 `implemented`。
- `runtime_state`：`unverified`、`passed_local_task`、`passed_flow_scope`、`passed_cumulative_mvg`、`passed_other_verification`、`failed`、`stale_revision`、`workspace_only`。
- `evidence_level`：`real_engine_input`、`scene_method`、`static_tscn_wiring`、`unit_deterministic`、`other_verification`、`manual_independent`、`unverified`。

运行报告（`logs/ci/mvg-acceptance/*/summary.json`、`coverage-receipt.json`、`runtime/latest.json`、`runtime/workspace-latest.json`）只作为 `backlinks` 回链，按目录名从新到旧选取后再截断，保留原始 `original_executed_at`。记入运行状态须同时满足：manifest 为 `newrouge.mvg-integration.v1` 且哈希一致、revision 与快照一致、`mode=run`、非协议夹具、`workspace_dirty` 为假；存在 `coverage-receipt.json` 时必须严格解析并通过 `receipt_id` 封签复验，损坏或篡改的回执不回退采信 `summary.json` 并报六字段诊断。`scoped`/`partial`/`critical` 回执只把必需测试真实执行且通过的 Flow 记为 `passed_flow_scope`，未执行与 `planned` Flow 保持 `unverified`，绝不记 `passed_cumulative_mvg`；仅封签回执声明完整范围且覆盖全部当前 Flow 时才记 `passed_cumulative_mvg`。合法非 Flow 的 `other_verification` 通过记 `passed_other_verification` 与 `other_verification` 证据。`runtime/latest.json` 沿用 `apply_runtime_results` 的完整性规则；`real_engine_input` 仅在封签回执明确证明时给出，否则通过的 GdUnit 场景测试记 `scene_method`。工作区模式只记 `workspace_only`。

`impact` 层直接委托 Story 4.1 的 `_b_route_impact_closure.compute_impact_closure`：根节点取自 `--flow-id`/`--capability-id`/`--task-id`/`--scope-id`（scope 展开为其 plan），无过滤时取全部已投影的受治理 plan/Flow/Task 根，`legacy_unmapped` 时为空。保留方向性 `ACCOUNTING_EDGES`（共享 Capability/SourceBlock 不横向扩散）、Task `dependencies`、`command`/`state`/`rule` 定义与缺边保守扩大（`conservative_expansions`）。`main` 模式在工作区 dirty 或 HEAD 不等于 main 时，先把已提交 `refs/heads/main` 的相关文件物化到临时目录再计算，dirty 编辑不进入 main 影响结论。

## 快照身份

- `main`：存在 `.git` 时从 `refs/heads/main` 已提交树读取（`snapshot_source=refs/heads/main`），dirty 修改不会进入 main 节点。按 ADR-0035 以 `git status --porcelain -uall` 同时检查已跟踪修改与未跟踪文件，并按已提交树中的 `source-exclusions.v1.json` 排除 `logs/**` 等非权威路径；任何权威来源、契约、场景、任务或规划文件 dirty/未跟踪即 `dirty_workspace=true`。`trusted_ref_eligible`、`is_main_fact` 与 `can_advance_canonical` 仅在存在 main、HEAD 等于 main 且无 dirty 时为真；缺少 `refs/heads/main` 时回退工作区并标 `is_main_fact=false` 与六字段警告。阻断、策略/目录校验失败或 main 非事实时 `default_b_enabled` 恒为假。
- `workspace_preview`、`attempt`、`stable`、`stabilized`：读取工作区，`authority_ref=local-workspace`，恒 `is_main_fact=false`、`trusted_ref_eligible=false`、`can_advance_canonical=false`；后三者绑定对应工作区拓扑身份。
- `snapshot_digest` 覆盖本次读取的全部非日志输入摘要。工作区模式存在未完成的规划前缀（`mvg_progress` 未完成、能力作业未完成或 `mvg-recovery/registry.json` 存在未完整应用的条目）时标 `partial_planning`；`main` 模式不让工作区本地进度污染已提交状态，只在 `planning_progress.workspace_local_progress` 中单列。`planning_complete` 在 `legacy_unmapped`/`blocked`/`revoked`/`partial_planning`、存在 `3b_adopted_awaiting_3c`、存在孤立 Requirement 或本地部分检查点时恒为假，`runtime_verified=false`。

## 无 Task 3B、非 Flow 与 planned

- 正式 3B `plan` 已采纳但尚无 3C `binding` 与 Task 时，Flow 与四部分标 `3b_adopted_awaiting_3c`、`no_task_yet`，验证去向为 `awaiting_3c_task_compilation`，`task_readiness_blocking=false`，不合成假 Task。
- 合法非 Flow（`other_verification_refs` 或 `deferred`/`global_constraint`/`quality_gate`/`adr`/`other_verification` 去向）标 `non_flow_governed` 与 `not_applicable_non_flow`，不要求 Flow、场景或 Task readiness；`source_gap` 或未解决去向一律 `blocked` 并报六字段诊断，不算合法非 Flow。
- 快照中不存在的 `planned` Flow、契约、场景或测试一律 `planned_only=true`、`resource_exists=false`。

## 过期、pending、撤销与 local clear

- 治理/运行/恢复 JSON 一律严格解析（拒绝重复键、`NaN`/`Infinity`、非对象根）；损坏 JSON、未知 `schema_version`、`_b_route_records.validate_record` 失败（`catalog.v1.json`、`policy.v1.json`、`task-origins.v1.json`、plan、binding、commit）、`scope_heads` 非列表或条目畸形、缺失引用记录或摘要不符一律 `blocked`，绝不降为 `legacy_unmapped` 或 `passed`。符号链接、junction 与大小写别名路径报 `unsafe_path` 阻断诊断，不当作缺失。
- plan/binding 绑定的来源或 proof 字节变化时标 `stale`（`input_stale`）。
- 真实 pending 位置：`logs/ci/b-route-operations/*.json` 与 `operations/*/*.json`、`docs/planning/b-route/capability-apply.pending.json` 与 `docs/planning/semantic-topology/capability-apply.pending.json`、一层 `logs/ci/mvg-planning/*/apply-journal.json` 与 `logs/ci/capability-planning/*/apply-journal.json`、有界 1-2 层 `logs/ci/b-route-chapter4-binding/**` 与 `logs/ci/b-route-stage5-obligations/**` 非终态 journal/`*.pending.json`；未解决或损坏者报 `blocked`（`pending`）并携带 `resume_ref`。
- 本地 MVG/Capability 恢复登记严格校验 `registry.json` 与 `clears/epoch-*.json`（损坏或结构非法即阻断）；epoch 变化、事务被撤销或被 clear 归档的作业（含仅有 `planning-*/job.json` 而无指针者）标 `revoked` 且不可恢复。
- `logs/ci/b-route-reopen/**` 持久标记与 Chapter 6 恢复解析一致，支持 `task_id(s)`、`plan_id(s)`、`scope_id(s)` 与 `global`（或空目标即全局），`epoch_revoked` 报 `input_stale`，其余报 `conflict`；另经 `scan_durable_recovery_signals` 只读读取持久 Chapter 6 止损。命中的 Task、plan、Flow 与 scope 即使未指定 `--task-id` 也标 `revoked`，并使顶层 `ok=false`（`status=revoked`）。
- `local_clear_boundary` 证明正式 Git 采纳与累计 MVG 基线只依赖自身链路、跨 `mvg-clear` epoch 保持有效，清理审计保持完整；`mvg-clear` 返回附加 `formal_git_adoptions_preserved`，核对范围含 `catalog.v1.json`、`task-origins.v1.json`、`policy.v1.json`、`plans/`、`bindings/`、`commits/`、`receipts/` 与 `docs/testing/mvg/*.json`。

## 退出码与 HTTP

- CLI：`ok=true`（`ok`、`partial_planning`、`legacy_unmapped`）退出 `0`；阻断、撤销或参数非法退出 `2`；拒绝 `--apply`、`--write`、`--commit`、`--publish`、`--mutate-tasks`、`--set-status`；`--report` 仅允许 `logs/**/*.json`，且拒绝运行态目录（`mvg-recovery`、`project-health-knowledge`、`b-route-operations`、`b-route-reopen`、`mvg-acceptance`、`mvg-planning`、`capability-planning`、`knowledge-planning`、`b-route-chapter4-binding`、`b-route-stage5-obligations`）与目标或 `.tmp` 兄弟为符号链接的路径。
- HTTP：默认 `200` 返回结构化结果（含 `status=blocked` 与 `diagnostics`），`strict=1|true` 阻断时返回 `422`；查询参数按 `keep_blank_values` 严格解析：未知或空 `mode`、重复 `mode` 返回 `400`，未知参数名、重复参数、空过滤值、非法过滤参数与 `strict` 取值非 `0`/`1`/`true`/`false` 返回 `422`；响应 JSON 禁止 `NaN`。

## 验证

- 单测：`py -3 -B -m unittest scripts.python.tests.test_b_route_knowledge_projection -v`，已纳入 `run_gate_bundle.py` 的 `B_ROUTE_RUNTIME_DETERMINISTIC_TESTS` 与 `b-route-runtime-deterministic.yml`。
- CLI：`py -3 -B scripts/python/dev_cli.py b-route-knowledge-projection --help`。
