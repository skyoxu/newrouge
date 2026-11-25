# B 路线可执行三类义务 VerificationScope

本文档定义 Story 4.2 的 owner 边界：把 Story 4.1 传递影响、当前采纳交付范围、有效 manifest 与共同 InputSet 合成为具可比较身份、防重分类约束的验证合同（`newrouge.b-route-verification-scope.v1`）。本入口只授权验证责任，不运行测试、不宣告通过、不改 Task 状态、不授予 readiness 或默认启用 B 路线。

## Owner 与入口

- 领域 owner：`scripts/python/_b_route_verification_scope.py`（`build_verification_scope`、`validate_verification_scope`、`revalidate_verification_scope`）。
- 直接 CLI owner：`scripts/python/build_b_route_verification_scope.py`。
- 公共入口：`py -3 -B scripts/python/dev_cli.py b-route-verification-scope (--change-root <root> ... | --impact-proof <path> | --validate-scope <path> | --revalidate-scope <path>) [--root <root>] [--task-id <id> ...] [--plan-id <id> ...] [--flow-id <id> ...] [--manifest <path> ...] [--cumulative-manifest <path> ...] [--scope-delta <path>] [--prior-conclusions <path>] [--operation <op>] [--report <logs/**/*.json>] [--events-log <logs/**/*.jsonl>]`。
- 辅助 schema：`docs/planning/b-route/schemas/verification-scope.schema.json`（`$id` 为 `newrouge.b-route-verification-scope.v1`），只登记在 `_b_route_schema_resources.py` 的 `AUXILIARY`，7 个 `FORMAL` schema 与 `FORMAL` 元组保持不变。

## 退出码语义

- `0`：成功生成并封存合法 VerificationScope（即使 `scope_status=blocked_incomplete_or_broken`、`scope_closable=false`，范围本身仍是诚实有效的验证合同，只是阻断收口）；`--validate-scope` 校验通过；`--revalidate-scope` 判定 `valid=true`。
- `1`：范围无法生成或校验失败（schema 损坏、未知版本、`scope_id` 篡改、非法重分类、缺授权的缩减、过期或篡改的影响证明、报告路径冲突），或复验判定漂移（`valid=false`、`stale=true`）。
- `2`：参数非法（结构化 `invalid_arguments:<reason_code>`），包括任何 `--apply`/`--write`/`--commit`/`--mutate-tasks` 等写入类参数。

## 输入与防裁剪

1. 影响：`--impact-proof` 必须经 `revalidate_impact_proof` 实时复验为 `valid_reused`，否则以 `input_stale` 拒绝；篡改证明按原因码（如 `digest_mismatch`）拒绝；带 `plan_ids_filter` 的证明会裁剪计划，以 `conflict` 拒绝。复验与加载均使用证明 `manifest_paths_filter` 与显式 `--manifest`/`--cumulative-manifest` 的并集，额外 manifest 不被丢弃，`--impact-proof` 与等价 `--change-root` 得同一 `scope_id`。`--change-root` 则重新计算完整闭包。
2. 交付边界：`in_scope_plan_ids`、`in_scope_task_ids`、`in_scope_flow_ids` 展开为 Flow 与 Requirement 边界；计划内 Flow、Stage-5 映射 Flow 与 manifest 任务 Flow 均并入。
3. InputSet：每个 in-scope Task 调用 `_b_route_input_set.resolve_input_set`，未验证的 InputSet 记为阻断缺口；范围级 `input_set_digest` 合并 Task InputSet、`impact_input_digest`、manifest/plan/binding 摘要、交付边界与治理 delta 引用，任务级与计划/Flow 级调用都有真实可校验摘要。
4. manifest：累计基线为 `docs/testing/mvg/*.json` 与 `--cumulative-manifest`，active 为 `--manifest` 与 Stage-5 `manifest_refs`。所有义务取并集，旧或更小的 manifest 与当前可运行状态都不能裁剪 plan/binding 或累计基线已声明的义务；active manifest 声明同一 Flow 却省略基线回归、或 Stage-5 绑定于 active 基线 Flow 的测试缺失时，义务保持 `existing_required`、`blocked` 并记阻断缺口。
5. 记录：`catalog.v1.json` 缺失记 `catalog_missing`，plan/binding 的 `schema_version` 或 `plan_id` 不符记身份缺口，B 路线 in-scope Task/Flow 缺 Stage-5 绑定记 `missing_stage5_binding`。

## 三类义务与混载 Flow

- `existing_required`：累计基线中已实现的受影响回归，或 Stage-5 `existing_required`。测试文件缺失、损坏或 Flow 当前失败/无法启动时仍保留该层级，状态为 `blocked` 并阻断收口。
- `current_new`：当前交付边界内的新增或未完义务。测试或实现对象为 `planned`、缺失或关联计划中实现对象未就绪时为 `pending`/`blocked`，阻断收口；已实现且文件存在时为 `ready_to_execute`。
- `out_of_scope_future`：边界外且无既有基线回归的受影响义务，`blocking_current_delivery=false`、`immediate_execution_required=false`、`claimed_passed=false`，并登记 `follow_up_responsibilities`（入范围时更新 Stage-4/5 绑定、Flow 收口前实施并验证）。
- 同一 Flow 可同时含多个层级（`flow_classifications[].mixed_tiers=true`）。范围外 Flow 一旦进入 `in_scope_*`，其未完义务自动转为 `current_new` 并阻断。
- 防降级：任何 manifest 候选（含就地编辑 active manifest）把 active 基线 Flow 或已实现基线测试标为 `planned`、Stage-5 `existing_required` 所绑 Flow 被标为 `planned`、任何 Stage-5 绑定把它们标为 `out_of_scope_future`、任何 `scope_delta` 把 `existing_required` 或 active 基线 Flow 重分类为 `planned`/`out_of_scope_future`，均以 `conflict` 拒绝。

## 治理 scope delta

- 格式：`{"schema_version": "newrouge.b-route-verification-scope-delta.v1", "changes": [...]}`，每项含 `action`（`reclassify`/`retire`/`remove`/`shrink`）、恰好一个 `obligation_id`/`flow_id`/`test_id`、`reason`，以及可选 `target_tier`、`source_authority_ref`、`anti_weakening_review_ref`。
- 原因经规范化分词匹配，凡含失败、崩溃、无法启动、缺测、未实现测试、flaky、超时、跳过、`n/a`、`todo`、workaround、换绿等伪装说法，或少于 12 个非空白字符，一律 `conflict`。
- `existing_required` 义务与 active 基线 Flow 禁止 `remove`/`shrink`/降级，只允许受治理的 `retire`。
- 任何削弱（退役、移除、缩减或降级重分类）必须同时提供非空可读的来源依据（禁 `logs/**`）与防削弱审阅文件，二者互不相同且都不得指向 delta 文件本身，二者以 `OwnedRef` 摘要写入 `authority_refs.governed_delta_refs` 并进入 `scope_id`；已应用变更记录在 `applied_delta_changes`。

## 未知、非 Flow 与执行分桶

- 4.1 `conservative_expanded=true` 时保留 `unknown_items`，并把全部累计基线已实现回归纳入 `existing_required`；未来 `planned` Flow 仍为 `out_of_scope_future`（入范围则为 `current_new` `pending`），绝不变成可执行测试。
- 影响 MVG Flow 的合法非 Flow 需求随闭包纳入该 Flow 的真实测试，并在 `links_mvg_flow_ids` 记录关联；无 MVG 的纯非 Flow 需求需实质 rationale 与存在的 `other_verification_refs`，缺失即 `blocked`。只有真实存在的 `.py`/`.ps1` 脚本才进入 `executable_tests`（`kind=other_verification`），文档类依据为 `manual_required`。
- `execution_plan` 分列：`executable_tests`（仅当前层级、`state=implemented` 且文件存在的真实测试或脚本）、`pending_obligations`（未实施、损坏或未来跟进）、`manual_obligations`（在 delta 应用后生成：Flow `human_verification` 适用项、Stage-4/5 绑定义务声明的 `human_verification`、manifest `coverage.excluded_claims`、文档类非 Flow 依据）、`other_verification_obligations`。

## 身份、校验与漂移失效

- `scope_id` 为除 `ok`/`status`/`operation`/`reason_code`/`diagnostics`/`report_path`/`metrics`/`generated_at`/`scope_id` 外完整范围内容的规范化摘要；同有效内容恒得同一 `scope_id`。
- `validate_verification_scope` 以辅助 schema（全部对象 `additionalProperties=false`）校验并重算 `scope_id`：未知版本 `unknown_schema`、结构损坏 `schema_validation_failed`、篡改 `digest_mismatch`。即使攻击者重算 `scope_id`，当前层级义务仍为 `pending`/`blocked`、存在阻断待办或 InputSet 无效却声明可收口时以 `conflict` 拒绝，执行分桶与义务不一致或 `impact_input_digest` 与 `partition_digests` 不符同样拒绝。
- 每个义务带 `input_fingerprint`（义务记录与其直接证据：manifest 条目、测试与源/契约文件摘要、计划 Flow 定义与引用规则/状态/命令、绑定映射与义务）。`revalidate_verification_scope` 按原请求重建：`tasks.json` 仅状态变化或无关提交保持 `valid=true`、同一 `scope_id`；相关漂移产生 `replacement_scope_id`，精确列出 `invalidated_obligations`/`invalidated_flows`，受影响的 `prior_conclusions` 标记 `invalidated`，无关结论保留；失效归因同时覆盖 Task InputSet 漂移、新增义务、Flow 义务集合、Requirement、无选择器结论与治理 delta 引用漂移；无法归因的漂移保守地使全部旧结论失效。CLI 以 `--revalidate-scope <path> --prior-conclusions <path>` 传入结论文件（列表或 `{"prior_conclusions": [...]}`）。
- Taskmaster `status` 等易变字段不参与分类与身份，未完成依据来自 manifest `planned`、实现对象可用性与文件存在性。

## 只读与非授权不变量

- 恒定 `scope_authorizes_verification_only=true`、`task_completed=false`、`flow_completed=false`、`milestone_completed=false`、`runtime_verified=false`、`task_status_mutated=false`、`publish_pointer_mutated=false`、`default_b_enabled=false`；所有义务 `claimed_passed=false`。
- 默认严格零写盘；仅在显式提供时独占新建 `logs/**/*.json` 报告并追加 `logs/**/*.jsonl` 事件，拒绝已存在或 `logs/**` 之外的路径。

## 验证

- 单测：`py -3 -B -m unittest scripts.python.tests.test_b_route_verification_scope -v`。
- CI：`run_gate_bundle.py` 与 `.github/workflows/b-route-runtime-deterministic.yml` 纳入上述单测，`test_b_route_runtime_ci.py` 守护接线。
