# acceptance-check 清单（模板）

本文件用于说明 `scripts/sc/acceptance_check.py` 的用途、运行方式、产物位置与关键步骤含义，避免把验收口径写散到各处。

## 1. 前置条件（Windows）

- 已安装 .NET 8 SDK（`dotnet` 可用）
- 已安装 Godot .NET 版本（用于引擎相关测试时的 `--godot-bin`）
- （可选）存在 `.taskmaster/tasks/tasks.json`，用于自动解析 `status == "in-progress"` 的任务 ID

## 2. 常用命令

```powershell
# 全量执行（建议在 CI 或本地验收使用）
py -3 scripts/sc/acceptance_check.py --task-id 10 --godot-bin "$env:GODOT_BIN"

# 仅执行部分步骤（逗号分隔）
py -3 scripts/sc/acceptance_check.py --task-id 10 --only adr,overlay,contracts,arch,build,security

# 启用性能硬门禁：解析 logs/ci/**/headless.log 中最新 [PERF] p95_ms
py -3 scripts/sc/acceptance_check.py --task-id 10 --perf-p95-ms 20
```

## 3. 退出码

- `0`：所有硬门禁步骤通过
- `1`：存在硬门禁失败
- `2`：无法解析任务（缺少任务文件 / 找不到 task id）

## 4. 产物与 SSoT

输出目录固定为：`logs/ci/<YYYY-MM-DD>/sc-acceptance-check/`

核心文件：

- `summary.json`：机器可读汇总（包含 steps 与关键 metrics）
- `report.md`：人类可读报告
- `<step>.log`：命令输出（由 `run_and_capture` 写入）
- 结构化 JSON：如 `architecture-boundary.json`、`security-soft-scan.json`

## 5. 步骤说明（按类别）

### 5.1 `adr`（硬门禁）

检查任务是否满足“至少引用 1 条 Accepted ADR”的最低合规要求：

- 读取任务的 `adrRefs` / `archRefs`
- 校验 ADR 文件存在（`docs/adr/ADR-<id>-*.md`）
- 可选：`--strict-adr-status` 时，任何非 `Accepted` 的 ADR 都会导致失败

### 5.2 `links`（硬门禁）

- 运行：`py -3 scripts/python/task_links_validate.py --mode all`
- 仅在同时存在 `.taskmaster/tasks/tasks_back.json` 与 `.taskmaster/tasks/tasks_gameplay.json` 时启用

### 5.3 `overlay`（硬门禁）

- 运行：`py -3 scripts/python/validate_task_overlays.py`
- 校验 overlay 路径存在，并对 `ACCEPTANCE_CHECKLIST.md` 做 front-matter/章节结构检查
- 对 `tasks_back.json`：每个任务必须提供 `overlay_refs`，且必须包含 `docs/architecture/overlays/<PRD-ID>/08/_index.md` 与 `docs/architecture/overlays/<PRD-ID>/08/ACCEPTANCE_CHECKLIST.md` 两个锚点（防止“任务视图”与“验收/契约 SSoT”漂移）。

### 5.4 `contracts`（硬门禁）

- 运行：`py -3 scripts/python/validate_contracts.py`
- 校验 Contracts 与 Overlay/Test-Refs 的一致性（以脚本输出为准）

### 5.5 `arch`（硬门禁）

- 运行：`py -3 scripts/python/check_architecture_boundary.py --out <json>`
- 校验 `Game.Core/**` 不得依赖 `Godot.*`（保持可单测、可覆盖率门禁）

### 5.6 `build`（硬门禁）

- 运行：`py -3 scripts/sc/build.py NewRouge.csproj --type dev`
- 以 `-warnaserror` 方式构建，确保编译告警不被忽略

### 5.7 `security`（软门禁）

该组步骤**不会**阻断通过，但会写入 `security-soft.json` 供审计与回溯：

- `check-sentry-secrets`：`py -3 scripts/python/check_sentry_secrets.py`（总是 `exit 0`，只输出检测结果）
- `check-domain-contracts`（可选）：
  - 默认尝试：`scripts/python/check_domain_contracts.py`
  - 或通过环境变量指定脚本：`SC_DOMAIN_CONTRACTS_CHECK=<path-to-py>`
  - 若脚本不存在则跳过
- `security-soft-scan`：`py -3 scripts/python/security_soft_scan.py --out <json>`
- `check-encoding-since-today`（可选）：`py -3 scripts/python/check_encoding.py --since-today`（脚本存在才运行）

### 5.8 `tests`（硬门禁）

- 运行：`py -3 scripts/sc/test.py --type all --godot-bin <path>`
- 覆盖 xUnit（领域层）与 GdUnit4/Smoke（引擎层，视项目配置）

### 5.9 `perf`（按需硬门禁）

- 通过 `--perf-p95-ms <ms>` 或 `PERF_P95_THRESHOLD_MS=<ms>` 启用
- 从 `logs/ci/**/headless.log` 提取最新 `[PERF] ... p95_ms=...` 作为门禁依据

