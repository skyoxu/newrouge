# B 路线 Stage-5 真实 MVG 义务或合法其他验证依据绑定

Story 3.6 提供 `b-route-stage5-obligations`（`producer="stage5_obligations"`），承接已提交的 3B 规划（`newrouge.b-route-plan.v1`）与 Stage-4/5 绑定（`newrouge.b-route-binding.v1`，禁止跳过 Stage 4），经 `published_bundle`、Story 3.3 `resolve_task_origin`（全部守恒 Task 判 `B`）与 Story 3.5 `resolve_input_set`（含候选单槽替换与 pre-sync）核验后，绑定有效 MVG manifest/审阅 delta 或合法非 Flow `other_verification_refs`，经共享 `_b_route_commit` 协议发布 `stage="5"` 绑定、`task-origins.v1.json` 与 `commits/<op>.json`，最后原子推进 `docs/planning/b-route/catalog.v1.json`。

本入口恒定保持 `readiness=false`、`runtime_verified=false`、`default_b_enabled=false`，不修改旧 `plan`、不改变 Stage-4 既定 `task_id` 集/四部分/`implementation_objects`、保留既有义务末尾的 `STAGE4_OBL_PREFIX`（避免误报 `return_stage="4"`）、不复制活 `status` 入权威记录，且保留共享 Task 上其他计划的 `plan_refs`/`binding_refs`；Stage-5 义务语义编码于 `STAGE5_OBL_PREFIX`（`stage5:obl:v1|`），可由 `extract_stage5_semantics(plan, binding)` 在无 `logs/` 的干净克隆中直接解析。

## 公共入口与十阶段生命周期

直接 owner 为 `scripts/python/bind_b_route_stage5_obligations.py`，公共 CLI 为 `py -3 -B scripts/python/dev_cli.py b-route-stage5-obligations`：

1. `preview`：纯只读零落盘，校验 Stage-4/5 前置、`resolve_task_origin`、manifest/delta 防削弱、非 Flow 合法豁免、影响分析与保守扩大、角色交接与无自锁、共享去重、旧 `done` 重验标记、审阅退休及 Story 3.5 `resolve_input_set`。
2. `prepare`：冻结请求、单调 `binding_revision`、目标前后像、Task `input_set_digest` 及可选原始字节 manifest `public_sync_entries`，不写任何正式记录或 manifest。
3. `reserve`：在 `commit.read_operation_context(operation_id)`、`business_guard` 与短 `writer_boundary` 下复验并推进状态为 `reserved`。
4. `inspect`：只读核对权威引用、公共同步 manifest 与正式目标状态。
5. `apply`：若有显式 `manifest_deltas`，先在 `writer_boundary` 下经 base64 原始字节 `public-sync-journal.json` + `public-sync.pending.json` 前滚写入经 `update_mvg_baseline.apply_delta` 校验的新 manifest，再经 `_b_route_commit.execute(..., stage="apply")` 写入 `bindings/<plan_id>/<rev>.json` 与 `task-origins.v1.json`。
6. `verify`：核验全部目标精确字节，写入不可变 `docs/planning/b-route/commits/<op>.json` 与 `catalog_after` 草案。
7. `publish`：原子推进 `docs/planning/b-route/catalog.v1.json`，校验完整已发布闭包并清理 `commit.pending.json` 与 `public-sync.pending.json`。
8. `read`：按 receipt 作用域调用 `read_committed` 并附加 `extract_stage5_semantics` 派生视图（基于活 `tasks.json` 现算 `requires_reverification`，不回写权威）。
9. `recover-inspect`：只读探测 `public-sync-journal.json` 与 `commit.json` 的物理状态及下一步阶段。
10. `recover`：按原始身份从 `public-sync-journal.json` 或 `commit.json` 中断点前滚恢复至发布完成。

## 关键约束与验证规则

- **Flow/回归与 manifest 校验**：Flow、担 MVG 交接/集成/回归或触达既有 Flow 的 Task 必绑有效 manifest（验 `raw_digest`、`manifest_sha256`、解耦活 `status` 的 `_validate_mvg_manifest_decoupled` 及完整 Flow/test/Requirement 责任），禁止凭标签/N/A 豁免。`obligations[].requirement_ids`/`flow_ids` 严格保持为 `plan.requirements` 与已覆盖 `catalog.definition_owners` 子集；非 catalog 累计 Flow 与 `out_of_scope_future` Flow 记入 `STAGE5_OBL_PREFIX` 及 `manifest_refs`/`test_ids`，避免 `MAPPING_MISMATCH`。
- **合法非 Flow 豁免**：仅当 3B `applicability` 实质理由、`adoption_proof_refs`、真实 `other_verification_refs`、InputSet 齐备且显式证明零 Flow 影响时免造 Flow/manifest；标签、空值、`N/A`、`source_gap` 或删除依据一律阻断。
- **影响分析与保守扩大**：非 Flow 触达既有 Flow（`source_paths`/`contract_ref`/测试/消费链）必绑回归；反向影响未知时按完整累计 manifest 范围保守扩大（不等 Epic 4），严格分列 `existing_required`、`current_new`、`out_of_scope_future` 三类，禁止缩窄、禁止逼未来提前实现、无累计依据不可证即阻断。
- **三类角色与无自锁**：按 `producer`/`consumer`/`integration_only_owner` 核验交接与依赖；整合 owner 不要求运行时 API 且禁止将自身 `done` 设为前置死锁；保留全部前置依赖，区分合法未实现（`planned`/未 `done`）与定义缺失（阻断）。
- **共享去重、旧 `done` 与审阅减义务**：共享沿唯一 `requirement_verification`、`(requirement_id, flow_id)` 与去重键计数，拒绝重计；新义务或 `planned` 测试不被旧 `done` 覆盖（派生标 `requires_reverification=true`，禁复制 `status` 入权威）；减少或退休既有义务/测试/依据必须具真实规格文件 `authority_ref` 与 `status="reviewed"` 理由。

## Windows PowerShell 示例

```powershell
py -3 -B scripts/python/dev_cli.py b-route-stage5-obligations --help

py -3 -B scripts/python/dev_cli.py b-route-stage5-obligations `
  --root (Get-Location).Path `
  --stage preview `
  --operation-id OP-S5-REWARD-001 `
  --request logs/ci/my-review/stage5-request.json

py -3 -B scripts/python/dev_cli.py b-route-stage5-obligations `
  --root (Get-Location).Path `
  --stage prepare `
  --operation-id OP-S5-REWARD-001 `
  --request logs/ci/my-review/stage5-request.json

foreach ($stage in @("reserve", "inspect", "apply", "verify", "publish", "read")) {
  py -3 -B scripts/python/dev_cli.py b-route-stage5-obligations `
    --root (Get-Location).Path `
    --stage $stage `
    --operation-id OP-S5-REWARD-001
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

## 事件、补偿与 Schema 边界

- 状态推进事件追加至 `logs/ci/b-route-stage5-obligations/<operation-id>/events.jsonl`；只读阶段（`preview`/`inspect`/`recover-inspect`/`read`）不写事件。
- 辅助 schema 位于 `docs/planning/b-route/schemas/stage5-obligations-operation.schema.json`，仅注册于 `_b_route_schema_resources.AUXILIARY`，7 份 `FORMAL` schema 保持不变。
- Stage-5 操作参与 `validate_operations` 与 `operation_state_graph` 治理校核，并严格守恒 `task_mappings` 中的 `task_id` 集合，使 Story 2.8 `_b_route_compensation.build` 在补偿既有 3B 采纳操作时能够完整保留并推进已发布的 Stage-5 `binding_ref`；相关实现与规则同时由 `_b_route_adoption_review.py` 策略锚定。
