# B 路线 3C 受治理三联编译与绑定

Story 3.2 提供 `b-route-task-compile`（`producer="task_compilation"`），承接 Story 3.1 的 `ok=true`、`stable=true` 只读任务变更预览，经 `compile_task_triplet.py` / `build_taskmaster_tasks.py` 与严格 `TaskJoinContext` 编译 Taskmaster 三联，并复用共享 journal/commit/recover 协议发布 `newrouge.b-route-binding.v1`（`stage="3C"`）、`newrouge.b-route-origins.v1`、`commits/<op>.json`，最后推进 `docs/planning/b-route/catalog.v1.json`。

本入口严格保留三项授权边界（`readiness=false`、`runtime_verified=false`、`default_b_enabled=false`）、旧 A `docs/workflows/chapter3-task-scope.json`、Taskmaster 唯一状态权与累计 MVG manifest；3C 编译完成后，进入 Chapter 6 仍须完成 Chapter 4–5 细化与 readiness。

## 公共入口与九阶段生命周期

直接 owner 为 `scripts/python/compile_b_route_tasks.py`，公共 CLI 为 `py -3 -B scripts/python/dev_cli.py b-route-task-compile`。九个显式阶段如下：

1. `prepare`：重验 3.1 预览、3A `verify_current_proof`、3B `read_committed`、可选保护/manifest 防削弱与旧 A `chapter3-task-scope.json`；**仅本阶段**分配永久 `taskmaster_id`（`max+1`）与 `NG-xxxx`/`GM-xxxx` 入 `allocations`，锁定三联定义投影（`newrouge.b-route-task-definition.v1`，仅排除 `status` 与直系 `subtasks[].status`）以及 `binding`/`origins` 的 `immutable_bytes`，不写任何三联或正式规划文件。
2. `reserve`：在 `business_guard` + 短 `writer_boundary` 下复核输入并将操作状态推进为 `reserved`。
3. `inspect`：只读核对前像差异与投影状态，不写文件。
4. `apply`：经共享 `_b_route_commit.execute(..., stage="apply")` 初入旧+新 `resource_scopes` 锁写 `commit.json` 时，重读活三联、核验定义投影、合并活 `status`/`subtasks[].status`、封存实际 `before`/`after`/`projection_digest` 入 `commit.json` 与 receipt 草案，并原子写入三联与 `binding`/`origins`（不推 `catalog.v1.json`）；冻结后再改三联（含 `status`）立即阻断。
5. `verify`：核验全部目标为精确 after 字节，写入不可变 `docs/planning/b-route/commits/<op>.json` 并生成 `catalog_after` 草案，仍不推 `catalog.v1.json`。
6. `publish`：最后原子推进 `docs/planning/b-route/catalog.v1.json`，验证完整已发布闭包并清理 `commit.pending.json`；已 `terminal_valid` 的同内容重放返回 `noop=true`，保留活 `status` 并容忍后续受治理任务新增。
7. `read`：按 receipt 作用域调用 `read_committed` 只读校验已提交闭包；`_PublishedBundle.receipt` 识别新 `current_receipts` 接替的三联投影并按单 Task 核验绑定投影，无当前 receipt 直改 `tasks*.json` 立即阻断。
8. `recover-inspect`：只读探测物理落盘状态与下一步阶段。
9. `recover`：经共享 `_b_route_commit.recover` 从中断点前滚至完成，或在已完成时返回 `noop=true`。

## Windows PowerShell 示例

```powershell
py -3 -B scripts/python/dev_cli.py b-route-task-compile --help

py -3 -B scripts/python/dev_cli.py b-route-task-compile `
  --root (Get-Location).Path `
  --stage prepare `
  --operation-id OP-3C-REWARD-001 `
  --request logs/ci/my-review/task-compile-request.json

foreach ($stage in @("reserve", "inspect", "apply", "verify", "publish", "read")) {
  py -3 -B scripts/python/dev_cli.py b-route-task-compile `
    --root (Get-Location).Path `
    --stage $stage `
    --operation-id OP-3C-REWARD-001
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
```

## 退出码、事件与 Schema 边界

- 退出码 `0` 表示当前阶段成功（单行确定性 JSON stdout）；退出码 `2` 表示阻断或参数/冲突错误，输出标准六字段 `Diagnostic`，写前阻断保持零改写。
- 状态推进事件（`prepare`/`reserve`/`apply`/`verify`/`publish`/`recover`）追加写入 `logs/ci/b-route-task-compilation/<operation-id>/events.jsonl`；只读阶段（`inspect`/`recover-inspect`/`read`）不落盘。
- 操作辅助 schema 位于 `docs/planning/b-route/schemas/task-compilation-operation.schema.json`，仅注册于 `_b_route_schema_resources.AUXILIARY`，六类 `FORMAL` schema 保持不变。
