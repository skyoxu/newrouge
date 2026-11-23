# B 路线 Chapter 4 生产契约与四部分实施定义细化

Story 3.4 提供 `b-route-chapter4-binding`（`producer="chapter4_binding"`），承接已提交的 3B 规划（`newrouge.b-route-plan.v1`）与 3C/4 绑定（`newrouge.b-route-binding.v1`），经 `published_bundle` 与 Story 3.3 `resolve_task_origin` 核验目标 Task 全为 `B` 且无冲突后，将逻辑定义细化为生产命令（前置/后置/不变式）、只读状态与唯一所有者、C# 薄适配依赖/生命周期、控件至对象/资源绑定、场景进出、UI 切片与 `layout`/`art`/`animation` 人工区保护以及测试义务，经共享 `_b_route_commit` 协议发布 `stage="4"` 绑定、`task-origins.v1.json` 与 `commits/<op>.json`，最后原子推进 `docs/planning/b-route/catalog.v1.json`。

本入口恒定保持 `readiness=false`、`runtime_verified=false`、`default_b_enabled=false`，不修改旧 `plan`、不改变 3C/4 既定 `task_id` 集合、不丢弃共享 Task 上其他计划的 `plan_refs`/`binding_refs`；Stage-4 语义编码于正式 `binding` 的 `lifecycle`/`parts`/`obligations` 字段中，可由 `extract_stage4_semantics(plan, binding)` 在无 `logs/` 的干净克隆中直接解析。

## 公共入口与十阶段生命周期

直接 owner 为 `scripts/python/refine_b_route_chapter4_binding.py`，公共 CLI 为 `py -3 -B scripts/python/dev_cli.py b-route-chapter4-binding`：

1. `preview`：纯只读零落盘，校验 3B+3C/4、`resolve_task_origin`、双态（`planned`/`existing`）、BCL-only 契约、Overlay 合并、UI 人工区与错配归因（返回 `3A`/`3B`/`3C`/`4`）。
2. `prepare`：核验并冻结操作请求、单调 `binding_revision`、目标前后像及可选原始字节 `public_sync_entries`，不写任何源码、Overlay、三联或正式规划文件。
3. `reserve`：在 `commit.read_operation_context(operation_id)`、`business_guard` 与短 `writer_boundary` 下复验并推进状态为 `reserved`。
4. `inspect`：只读核对权威引用、公共同步文件与正式目标状态。
5. `apply`：若有显式 `public_changes`，先在 `writer_boundary` 下通过 base64 原始字节 `public-sync-journal.json` + `public-sync.pending.json`（不经 JSON `create_journal`）前滚写入 BCL 契约、`EventTypes.cs` 与 sha256 增量合并 Overlay，再经 `_b_route_commit.execute(..., stage="apply")` 写入 `bindings/<plan_id>/<rev>.json`、`task-origins.v1.json` 及可选保活投影同步后的三联。
6. `verify`：核验全部目标为精确 after 字节，写入不可变 `docs/planning/b-route/commits/<op>.json` 与 `catalog_after` 草案。
7. `publish`：原子推进 `docs/planning/b-route/catalog.v1.json`，校验完整已发布闭包并清理 `commit.pending.json` 与 `public-sync.pending.json`。
8. `read`：按 receipt 作用域调用 `read_committed` 并附加 `extract_stage4_semantics(plan, binding)` 派生视图。
9. `recover-inspect`：只读探测 `public-sync-journal.json` 与 `commit.json` 的物理状态及下一步阶段。
10. `recover`：按原始身份从 `public-sync-journal.json` 或 `commit.json` 中断点前滚恢复至发布完成，不弱化 Acceptance。

## 关键约束与归因规则

- **优先复用与原始字节同步**：`REUSE` 路径零修改源码、Overlay 与三联；仅显式声明 `public_changes` 时执行原始字节同步。`public-sync.pending.json` 存在或 `public-sync-journal.json` 未完成期间，Story 3.3 `resolve_task_origin` 保守阻断返回 `PENDING`/`UNPUBLISHED`。
- **双态核验**：`planned` 须具备责任 Task、期望类型、生命周期/交接与按类型必选 `later_checks`，不得宣称通过或造假节点；`existing` 须实证磁盘 `.cs`/`.tscn`/`.tres` 摘要、真实符号/节点/资源类型与 BCL-only 边界（禁止 `Godot.*`、非 BCL `using`、空接口、空 DTO）。
- **UI 切片与人工区**：UI 适用时分列 `inputs`/`methods`/`wiring` 与受保护人工区 `layout`/`art`/`animation`，禁止适配裁决、UI 直写状态或侵入人工区；仅 3B 有明确无 UI 依据时免除 UI 且不生成 Chapter 7。
- **错配归因**：来源/缺口返 `3A`，3B 定义/单所有者/未声明 UI 豁免/非 producer 造 API 返 `3B`，非 B Task/缺 3C/改 `task_id` 集返 `3C`，契约/Overlay/双态/适配/人工区/弱化 Acceptance 返 `4`，拒发并输出六字段 `Diagnostic`。

## Windows PowerShell 示例

```powershell
py -3 -B scripts/python/dev_cli.py b-route-chapter4-binding --help

py -3 -B scripts/python/dev_cli.py b-route-chapter4-binding `
  --root (Get-Location).Path `
  --stage preview `
  --operation-id OP-CH4-REWARD-001 `
  --request logs/ci/my-review/chapter4-request.json

py -3 -B scripts/python/dev_cli.py b-route-chapter4-binding `
  --root (Get-Location).Path `
  --stage prepare `
  --operation-id OP-CH4-REWARD-001 `
  --request logs/ci/my-review/chapter4-request.json

foreach ($stage in @("reserve", "inspect", "apply", "verify", "publish", "read")) {
  py -3 -B scripts/python/dev_cli.py b-route-chapter4-binding `
    --root (Get-Location).Path `
    --stage $stage `
    --operation-id OP-CH4-REWARD-001
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

## 事件、补偿与 Schema 边界

- 状态推进事件追加至 `logs/ci/b-route-chapter4-binding/<operation-id>/events.jsonl`；只读阶段（`preview`/`inspect`/`recover-inspect`/`read`）不写事件。
- 辅助 schema 位于 `docs/planning/b-route/schemas/chapter4-binding-operation.schema.json`，仅注册于 `_b_route_schema_resources.AUXILIARY`，7 份 `FORMAL` schema 保持不变。
- 发布后的 `stage="4"` 绑定、receipt 与 `allocations` 原生兼容 Story 2.8 `_b_route_compensation.build`。
