# B 路线统一 Task 来源与适用计划解析

Story 3.3 提供只读零落盘公共解析器 `scripts/python/_b_route_task_resolver.py` 与公共 CLI `dev_cli.py b-route-task-origin`（直接入口 `scripts/python/resolve_b_route_task_origin.py`），在消费任务前统一先验 pending 与已提交 `policy`/`catalog`/`origins` 完整反向关系，判定单条 `task_id` 属于 `B`、`A`、`explicit_not_enabled_a` 还是 `blocked`，并汇总完整适用计划集合与 `applicable_set_digest`。

本入口严格只读：不传 `--report` 时 100% 零目录、零文件、零锁创建（严禁调用 `initialize_lock_namespace` 或任何写锁）；不写三联或正式记录、不修复损坏证据，且 `execution_authorized`、`readiness`、`runtime_verified`、`default_b_enabled` 恒为 `false`。

## 公共入口与 Windows PowerShell 示例

在仓库根目录使用 Python 3.12 或更高版本执行；`--root` 可为 Windows 原生路径，省略时默认当前目录。

```powershell
py -3 -B scripts/python/dev_cli.py b-route-task-origin --help
py -3 -B scripts/python/resolve_b_route_task_origin.py --help

# 纯只读零落盘查询（不创建任何 logs/locks 目录或文件）
py -3 -B scripts/python/dev_cli.py b-route-task-origin `
  --root (Get-Location).Path `
  --task-id 1 `
  --operation implement
$code = $LASTEXITCODE

# 可选显式落盘报告（仅接受全新的 logs/ci/.../*.json 路径，禁止覆盖）
py -3 -B scripts/python/dev_cli.py b-route-task-origin `
  --root (Get-Location).Path `
  --task-id 1 `
  --operation implement `
  --report logs/ci/2026-11-23/task-origin-t1.json
```

## 退出码与输出契约

标准输出为单行确定性 JSON；全部诊断遵循统一六字段 `Diagnostic`（`reason_code`、`stage`、`entity_id`、`expected`、`actual`、`resume_ref`）。

| 退出码 | 含义 |
| --- | --- |
| `0` | 校验通过且末尾双读无漂移（`ok=true`、`stable=true`）；`route` 为 `B`、`A` 或 `explicit_not_enabled_a`，仍不授予任何实施/readiness/运行权限 |
| `1` | 治理缺失或损坏、pending/混合态冲突、反向索引三方不一致、冻结 A 漂移/禁操作/缺归档、非 Flow 定义缺失、或双读漂移阻断（`ok=false`、`route="blocked"`） |
| `2` | CLI 参数错误（非法 `--task-id`/`--operation`）或 `--report` 路径非法/已存在冲突 |

## 分类规则与适用集合语义

1. **零写双读与 Pending 语义**：通过 `Observations` 双读与只读 `operation_state_graph` / `_legacy_pending` 检查状态。旧 `capability-apply.pending.json`、未完旧 journal（无 `scope_id`）及已入 `commit.json` 或存 `commit.pending.json` 的 B 路线操作一律保守阻断（`PENDING` / `UNPUBLISHED`）；尚未 `apply` 的 `prepared` / `reserved` 操作仅在业务 scope（`task`/`plan`/`flow`/`requirement`/`command`/`state` 或所属 `scope_id`）与当前 Task 重叠或未知时阻断，异业务 scope 放行。
2. **Route `B` 与多计划适用集合**：经 `published_bundle` 与 `TaskJoinContext` 全验已提交 `policy.v1.json`、`catalog.v1.json`、`task-origins.v1.json`、receipt 及实际文件；强制 `origins.tasks`、`catalog.task_index` 与活跃 `bindings` 三方一致且修订/摘要可验。汇总完整 `plan_refs`、`binding_refs`、`source_refs`、`resolved_definitions`（含递归 Flow/Command/State 闭包）、权威 `dispositions` 与按排序规范摘要计算的 `applicable_set_digest`。无 `logs/` 的 clean clone 中，B 路线凭已提交正式链与 receipt 封存通过。
3. **合法非 Flow 与禁标签豁免**：`other_verification` 与 `deferred` 须由已提交 `plan.requirement_verification` 与已解析 `verification_ref`/`authority_ref` 支撑，返回 `route="B"` 及对应处置并标明须下游定义与影响核对；禁止凭 Task 自由标签（如 `N/A`、`non-flow`）豁免 Flow/MVG 义务，定义缺失或 `source_gap` 一律阻断。
4. **Route `A`（冻结 A 边界）**：须满足反向零 B 义务、无残留 B 引用或自由豁免标签、可读匹配 `policy.frozen_a_refs`（Story 1.5 保护快照/清单与 `chapter3-task-scope.json`）中的冻结 Task ID、定义投影（仅排除 `status` 与直接 `subtasks[].status`）、来源 scope 及 `policy.switch_boundary.allowed_a_operations`。活 `status` 推进不破坏匹配，但 `done` 不免检；新增、漂移、禁操作、残留 B 痕迹或在 clean clone 中缺失冻结归档一律阻断并指向需走 B 路线。
5. **Route `explicit_not_enabled_a`**：仅当全库零 B 痕迹（无 `docs/planning/b-route/` 托管记录、无 B operation 记录、无 Task B 痕迹）且 `docs/adr/ADR-0040-b-route-stages-authority-and-activation.md` 为有效 `Accepted` 且保留未启用条款时返回；缺治理却有痕迹或 ADR-0040 失效一律阻断。
