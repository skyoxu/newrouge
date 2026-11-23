# B 路线 Chapter 5 同源核对与有效 Readiness

Story 3.7 提供 B 路线 Chapter 5 同源定义核对与 readiness 门禁引擎 `scripts/python/_b_route_chapter5_readiness.py` 及公共 CLI `dev_cli.py b-route-chapter5-readiness`（直接入口 `scripts/python/reconcile_b_route_chapter5_readiness.py`），并桥接 `scripts/python/chapter5_semantic_reconciliation.py`（`load_task_readiness`、`validate_chapter5_evidence_freshness`）与 `scripts/python/refresh_chapter_knowledge.py`（`chapter5_closure_evidence`、`run`）。

本入口严格维持 `runtime_verified=false`、`default_b_enabled=false`，不修改 3B `plan` 修订，不引入第二套 Task/MVG 状态机，不改动 7 份 `FORMAL` schema，也不扩充 `ReasonCode`/`Stage`。

## 公共入口与 Windows PowerShell 示例

```powershell
py -3 -B scripts/python/dev_cli.py b-route-chapter5-readiness --help
py -3 -B scripts/python/reconcile_b_route_chapter5_readiness.py --help

# 1. 在业务 scope 租约（guarded_input_set, review_only=True）下执行同源核对并生成冻结 readiness
py -3 -B scripts/python/dev_cli.py b-route-chapter5-readiness `
  --root (Get-Location).Path `
  --stage reconcile `
  --task-id 101 `
  --decisions logs/ci/my-review/chapter5-decisions.json

# 2. P2..P4 Concerns 在 allow_concerns=true 时自动登记 docs/technical-debt.md
py -3 -B scripts/python/dev_cli.py b-route-chapter5-readiness `
  --root (Get-Location).Path `
  --stage reconcile `
  --task-id 101 `
  --decisions logs/ci/my-review/chapter5-decisions.json `
  --record-technical-debt

# 3. 纯只读复验已冻结的 B 路线 readiness 与 InputSet 新鲜度（零落盘、零锁）
py -3 -B scripts/python/dev_cli.py b-route-chapter5-readiness `
  --root (Get-Location).Path `
  --stage verify `
  --task-id 101

# 4. 通过统一 load_task_readiness 桥接检查（无 B 痕迹保 A，存 B 痕迹走 B）
py -3 -B scripts/python/dev_cli.py b-route-chapter5-readiness `
  --root (Get-Location).Path `
  --stage check-readiness `
  --task-id 101
```

## 退出码与输出契约

标准输出为单行确定性 JSON（`schema_version: "newrouge.b-route-chapter5-readiness.v1"`）；冻结产物沿用 Chapter 5 标准路径与格式（`logs/ci/chapter5/reconciliation/task-<id>.json` 与 `logs/ci/chapter5/readiness/task-<id>.json`），并附加 B 路线冻结字段与统一六字段 `Diagnostic`（`reason_code`、`stage`、`entity_id`、`expected`、`actual`、`resume_ref`）。

| 退出码 | 含义 |
| --- | --- |
| `0` | 核对/复验通过（`READY` 或 `allow_concerns=true` 且全部 P2..P4 已登记 `docs/technical-debt.md` 的 `CONCERNS`），`closure_allowed=true`；仍恒定 `runtime_verified=false`、`default_b_enabled=false` |
| `1` | 来源分类非 B/受阻、绑定未达 `stage="5"`、3A 证明失配、Chapter 5 语义遗漏/冲突/无人交接、P0/P1 或降质违规、InputSet 过期（附 `return_stage` 为 `3A`..`5`）、或存在 B 痕迹时缺失 B readiness |
| `2` | CLI 参数错误（非法 `--stage`/`--task-id`/`--lock-mode` 或 `reconcile` 缺 `--decisions`） |

## 核心约束与不变式

1. **前置门禁与租约**：先经 Story 3.3 `resolve_task_origin` 判定 `route="B"`；`reconcile` 在 Story 3.5 `guarded_input_set` 业务 scope 租约（`review_only=True`、绝不持全局写锁）内执行并在落盘前 `revalidate()`；所有适用绑定必须均为已提交 `stage="5"`（`stage="3C"` 阻断归因 `4`，`stage="4"` 阻断归因 `5`）。
2. **只读复用 3A，绝不以 3A 省 5**：只读核验已提交 3A `source_identity` 与 `adoption_proof_refs` / 显式 3A `source_audit` 证明（零模型调用、`model_invocation_count=0`，无关变更不重做 3A），同时仍强制独立核对 Chapter 5 显式 `acceptance_links`、ADR/Overlay/Contract `authority_decisions`、`dependency_decisions`、`overlap_decisions`、Acceptance/`Refs:`、Requirement、非 Flow 去向、依赖与 Stage-5 义务，定位遗漏、冲突与无人交接。
3. **合法未 `done`、`planned` 与三类角色无自锁**：未 `done` 的 Task 与依赖合法；定义明确的 `planned` 对象（`expected_type`、`later_checks`、`responsible_task_ids`）与 `planned` 测试（`path`、`selector`、`evidence_level`、`min_tests>=1`）允许未落盘，不要求假桩且恒标 `implementation_verified=false`、`runtime_verified=false`；按 `producer`/`consumer`/`integration_only_owner` 核查交接，整合 owner 不要求运行时 API 且禁止 `coverage.blocking_task_ids` 或依赖自锁，禁止抹除前置依赖。
4. **旧 `done` 重验义务**：活 `tasks.json` 为 `done` 且存在新义务或 `planned` 测试时，强制标记 `requires_chapter6_reverification=true` 且 `old_done_covers_new_obligations=false`；任何声称免重验的输入直接阻断。
5. **P0/P1 底线与技术债登记**：P0/P1 及 P1 底线类别（`acceptance-refs`、`artifact-integrity`、`planned-only`、`security`、`test-false-green` 等）一律阻断；仅 P2..P4 在 `allow_concerns=true` 且登记至 `docs/technical-debt.md` 后允许 `CONCERNS`；禁止降阈值、关测试或弱化 Acceptance。
6. **精确新鲜度、抗时间戳伪造与桥接边界**：冻结 `input_set_digest`、`applicable_set_digest`、`scope_ids`、`plan_refs`、`binding_refs` 与 `reconciliation_sha256`；复验完全基于内容哈希与实时 InputSet 对比，刷新时间戳或 `mtime` 无法充作有效；无关 Task、活 `status` 或他计划发布不致失效，相关变更按 `3A`..`5` 精确归因；`load_task_readiness` 与 `refresh_chapter_knowledge` 在无 B 痕迹时 100% 保持原 A 行为，存在 B 痕迹时严格走 B 校验，禁止退回 legacy 或凭 `N/A` 放行。
7. **过程观测指标**：固定记录 `active_elapsed_seconds`、`model_invocation_count`、`source_audit_reused`、`reused_3a_proof_count` 与 `return_stage`。
