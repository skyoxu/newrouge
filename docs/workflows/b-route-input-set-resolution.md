# B 路线共同 InputSet 构造与新鲜度判定

Story 3.5 提供唯一共同 InputSet 与新鲜度判定引擎 `scripts/python/_b_route_input_set.py` 及公共 CLI `dev_cli.py b-route-input-set`（直接入口 `scripts/python/resolve_b_route_input_set.py`）。本入口汇总 Story 3.3 适用计划集合、Story 3.4 绑定（支持显式 `--candidate-binding` 单槽替换）、Task 定义投影、ADR/Overlay/Contracts、MVG manifest 或合法非 Flow `other_verification`、传递依赖闭包与 policy/codec/环境规则，产出确定性 `input_set_digest`，并在对比基线时精确输出失效项与最早所属 `return_stage`（`3A`、`3B`、`3C`、`4`、`5`）。

默认 `--lock-mode none` 且省略 `--report` 时 100% 零目录、零文件、零锁创建；仅在显式 `--lock-mode scope`（或 Python `guarded_input_set`）下持有业务 scope 租约（`business_guard(..., review_only=True)`，绝不持全局 `writer:planning` 长锁），并在进入租约与 `revalidate()` 时强制重验。本入口恒不授予 `execution_authorized`、`readiness`、`runtime_verified` 或 `default_b_enabled`。

## 公共入口与 Windows PowerShell 示例

在仓库根目录使用 Python 3.12 或更高版本执行；`--root` 可为 Windows 原生路径，省略时默认当前目录。

```powershell
py -3 -B scripts/python/dev_cli.py b-route-input-set --help
py -3 -B scripts/python/resolve_b_route_input_set.py --help

# 纯只读零落盘解析（不创建任何 logs/locks 目录或文件）
py -3 -B scripts/python/dev_cli.py b-route-input-set `
  --root (Get-Location).Path `
  --task-id 1 `
  --operation implement
$code = $LASTEXITCODE

# 显式对比基线并判定新鲜度与 return_stage
py -3 -B scripts/python/dev_cli.py b-route-input-set `
  --root (Get-Location).Path `
  --task-id 1 `
  --baseline logs/ci/2026-11-23/input-set-t1-base.json

# 显式候选 binding 单槽替换（标记 uses_candidate_binding=true，保留其他计划已提交绑定）
py -3 -B scripts/python/dev_cli.py b-route-input-set `
  --root (Get-Location).Path `
  --task-id 1 `
  --candidate-binding logs/ci/2026-11-23/candidate-binding.json

# 业务 scope 租约模式（review_only=True，无全局长锁，进入与 revalidate 重验）
py -3 -B scripts/python/dev_cli.py b-route-input-set `
  --root (Get-Location).Path `
  --task-id 1 `
  --lock-mode scope

# 可选显式落盘报告（仅接受全新的 logs/ci/.../*.json 路径，禁止覆盖）
py -3 -B scripts/python/dev_cli.py b-route-input-set `
  --root (Get-Location).Path `
  --task-id 1 `
  --report logs/ci/2026-11-23/input-set-t1.json
```

## 退出码与输出契约

标准输出为单行确定性 JSON（`schema_version: "newrouge.b-route-input-set.v1"`）；全部诊断遵循统一六字段 `Diagnostic`（`reason_code`、`stage`、`entity_id`、`expected`、`actual`、`resume_ref`）。

| 退出码 | 含义 |
| --- | --- |
| `0` | InputSet 完备、末尾双读无漂移（`ok=true`、`stable=true`），且若提供 `--baseline` 则新鲜度匹配（`freshness.fresh=true`）；仍不授予任何实施/readiness/运行权限 |
| `1` | 3.3 阻断/pending 冲突、缺失或损坏输入、候选 binding 校验失配、未知或循环依赖、持续双读漂移、或对比 `--baseline` 失效（`freshness.fresh=false`，附 `invalidated_items` 与 `return_stage`） |
| `2` | CLI 参数错误（非法 `--task-id`/`--operation`/`--lock-mode`/`--max-attempts`）或 `--report` 路径越界/已存在冲突 |

## 核心算法与不变约束

1. **先验 Story 3.3**：每次解析均先调用 `resolve_task_origin` 验证来源分类（`B`/`A`/`explicit_not_enabled_a`）、旧 `capability-apply.pending.json`、commit/public-sync pending、重叠业务 scope 及适用计划集；3.3 阻断则直接 fail closed。
2. **显式候选 binding 单槽替换**：`--candidate-binding` 仅允许用于 `route="B"`，必须通过 `binding.schema.json`（`validate_record`）、对应已提交 `plan_ref`、`TaskJoinContext` 映射及所有 `OwnedRef` 实时落盘实证；仅替换对应 `plan_id` 槽位、保留其他计划已提交绑定，并显式标记 `uses_candidate_binding=true` 与 `committed=false`，绝不冒充已提交。
3. **条目完备与 clean clone 兼容**：每条 InputSet 记录包含 `category`、`locator`、`raw_digest`、`normalization_mode`、`codec_version`、`normalized_digest`、`return_stage`、`sealed_log`、`committed` 与 `details`。在无 `logs/` 的 clean clone 中，已提交记录引用且经 receipt `authority` 封存的 `logs/` 历史文件保留封存 `raw_digest` 并与原仓产出完全一致的 `input_set_digest`；非 `logs/` 权威文件一律实读核验。
4. **无关变更零误伤与实时依赖资格**：`input_set_digest` 仅由各条目的规范化摘要计算，绝不哈希整份 `catalog.v1.json`/`task-origins.v1.json`/`tasks*.json` 或 Git `HEAD`：`task_definition_projection` 仅排除 `status` 与直接 `subtasks[].status`（禁止扩展可变白名单），`task-origins` 验真后仅取本 Task 切片（排除 `origins.revision`），MVG manifest 校验显式解耦活 `status` 与 `blocking_task_ids` 防止同流兄弟 Task 推进误阻。自身与依赖的实时 `status` 单独上报于 `dependency_eligibility`（未 `done` 合法，绝不复制进新权威）。
5. **传递依赖闭包与归因阶梯**：递归遍历 `dependencies`/`depends_on` 依赖链并纳入跨计划定义与生产者投影；未知依赖（`UNKNOWN_ENTITY`）或循环依赖（`DIGEST_CYCLE`）一律阻断。对比基线按 `3A < 3B < 3C < 4 < 5` 取全部失效项中最早所属阶段作为 `return_stage`。
6. **有界重读与 `guarded_input_set`**：默认只读模式在瞬时漂移时有界重读（默认最多 3 次）收敛，持续漂移则阻断；`guarded_input_set` 仅通过 `business_guard(..., review_only=True)` 持有业务 scope 租约（不持 `writer:planning` 全局写锁），并在进入租约与 `revalidate()` 时重验 pending、漂移与 `input_set_digest`。
