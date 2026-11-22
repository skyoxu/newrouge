# B 路线 3C 只读任务变更预览

Story 3.1 提供 `b-route-task-preview`，面向已正式采纳的 3B 规划（`read_committed`）与当前有效 3A 来源审计证明（`verify_current_proof`），盘点既有实现、成熟 Task、多对多 Flow/Requirement 关系与合法非 Flow 义务，仅为真实缺口生成可审阅的 `back`/`gameplay` 业务视图增量以及与 Story 3.2 同构的 `newrouge.b-route-binding.v1`（`stage="3C"`）和 `newrouge.b-route-origins.v1` 草案。

本入口严格只读：不修改 `.taskmaster/tasks/*.json`、不修改 `docs/planning/b-route/**`、不修改累计 MVG manifest、不推进任何发布指针，也不分配永久正整数 Task ID（正式三联编译与永久 Task ID 分配归 Story 3.2）。输出授权字段（`formal_adoption`、`task_triplet_written`、`readiness`、`runtime_verified`、`default_b_enabled`）全部保持 `false`。

## 公共入口与 Windows PowerShell 示例

在仓库根目录使用 Python 3.12 或更高版本执行；所有路径参数采用仓库相对 POSIX 拼写，`--root` 可为 Windows 原生路径。

```powershell
py -3 -B scripts/python/dev_cli.py b-route-task-preview --help
py -3 -B scripts/python/preview_b_route_task_changes.py --help

py -3 -B scripts/python/dev_cli.py b-route-task-preview `
  --root (Get-Location).Path `
  --plan-id reward-return-plan `
  --scope-id scope-reward `
  --audit-ref logs/ci/2026-11-22/b-route-source-audit/run-01/audit-01/report.json `
  --run-id preview-reward-001
$code = $LASTEXITCODE
```

可选附加参数（均为只读校验输入，无 `--write` 或 `--apply` 参数）：

```powershell
py -3 -B scripts/python/dev_cli.py b-route-task-preview `
  --root (Get-Location).Path `
  --plan-id reward-return-plan `
  --scope-id scope-reward `
  --audit-ref logs/ci/2026-11-22/b-route-source-audit/run-01/audit-01/report.json `
  --protection-ref docs/planning/b-route/protection-input.v1.json `
  --manifest docs/testing/mvg/combat-reward-return.json `
  --change-intents logs/ci/my-review/change-intents.json `
  --run-id preview-reward-002
```

## 退出码与输出契约

标准输出为单行确定性 JSON；完整报告以原子替换（`os.replace`）独占写入全新目录 `logs/ci/<UTC-date>/b-route-task-preview/<run-id>/report.json`，禁止覆盖已有 `run-id`。

| 退出码 | 含义 |
| --- | --- |
| `0` | 校验通过且末尾重读无漂移（`ok=true`、`stable=true`）；输出可审阅双份草案，仍不授予写入或 readiness 权限 |
| `1` | 业务/语义/漂移阻断（3A 证明失效或与 `plan.source_identity` 不一致、3B 存在 `source_gap` 或计划未发布、成熟 Task 覆盖或累计基线削弱、运行中途文件漂移）；报告已写入 `logs/**` |
| `2` | CLI 参数错误、非法或已存在的 `run-id` 目录冲突、或独占写入报告失败；返回六字段 `Diagnostic` |

## 核心语义与 3.1 到 3.2 交接边界

1. **3A 与 3B 强制前置核验**：通过 `_b_route_commit.read_committed` 核验已发布 `catalog`/`policy`/`origins`/`plan` 闭包；通过 `_b_route_source_audit.verify_current_proof` 确认 3A `planning_eligible=true`，并核对 `plan.source_identity`（`manifest_ref`、`ledger_ref`、`source_revision`、`source_manifest_digest`）与当前 3A 账本一致。任一失配、缺失或 `source_gap` 均 fail-closed，返回带 `owning_stage`（`3A`/`3B`/`3C`）标注的标准六字段 `Diagnostic`。
2. **多对多、四部分与非 Flow 核算**：保留 `Task <-> Flow` 多对多关系及 `requirement_verification` 唯一权威处置、`requirement_route_memberships` 路线成员与去重 `requirement_evidence`；不按四部分机械四拆、不按任务或节点数量推算缺口；对 `integration_only_owner` 不虚构运行时业务 API；`other_verification` 盘点真实义务与 `other_verification_refs` 而不伪造 Flow，`deferred` 仅登记为未执行且不宣称满足。
3. **成熟成果保护与防削弱**：保留既有 `taskmaster_id`、`business_id`、`status`、`history`、`evidence_refs` 与既有 `acceptance`；旧 `status="done"` 仅证明历史范围，永不证明新增 Requirement/Flow/义务。`update`/`split`/`merge`/`retire` 必须附带 `scope`、`source_diff_evidence`、`lineage` 与 `rationale`，并阻断状态覆盖、ID 复用/改写、Story 号充当 Task ID、无依据退役以及累计 MVG 基线削弱。
4. **3.2 免翻译交接草案**：
   - `view_deltas.back` / `view_deltas.gameplay`：复用 `normalize_task_intents.py` 确定性字段规范生成的 `reuse | update | create | split | merge | retire` 建议；`create` 与 `split` 携带确定性 `candidate_key` 且 `task_id=null`。
   - `binding_preview`：与 `newrouge.b-route-binding.v1`（`stage="3C"`）同构，并在内存中进行 schema 兼容性自检。
   - `origins_preview`：与 `newrouge.b-route-origins.v1` 同构，保留 `frozen_legacy_refs` 与完整 `source_refs`/`plan_refs`/`binding_refs`。
   - `preview_digest`：排除时间戳与运行路径的规范内容摘要，用于 Story 3.2 核对预览前像。
