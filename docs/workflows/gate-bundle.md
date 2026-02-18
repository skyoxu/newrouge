# Gate Bundle 工作流说明

本文档定义 `scripts/python/run_gate_bundle.py` 的使用口径，用于统一本地与 CI 的硬门/软门执行方式。

## 目标

- 减少分散门禁步骤造成的漂移风险。
- 保持硬门失败即阻断、软门失败可观测但不阻断的策略。
- 为 CI 与本地提供一致的命令入口与结构化日志产物。

## 命令入口

Windows 下统一使用：

```powershell
py -3 scripts/python/run_gate_bundle.py --mode hard --task-files .taskmaster/tasks/tasks_back.json .taskmaster/tasks/tasks_gameplay.json
py -3 scripts/python/run_gate_bundle.py --mode soft --task-files .taskmaster/tasks/tasks_back.json .taskmaster/tasks/tasks_gameplay.json
py -3 scripts/python/run_gate_bundle.py --mode all --task-files .taskmaster/tasks/tasks_back.json .taskmaster/tasks/tasks_gameplay.json
```

参数说明：

- `--mode hard`：执行硬门；任一门禁失败即返回非 0。
- `--mode soft`：执行软门；默认不阻断（如需阻断可加 `--strict-soft`）。
- `--mode all`：先执行硬门，再执行软门，并输出总汇总。
- `--stability-template-hard`：将 `check_acceptance_stability_template.py` 从软门提升为硬门（默认在软门）。
- `--run-id`：可选运行标识；默认自动取 CI RunId（或本地时间戳），用于避免同日覆盖。
- `--retention-days`：运行后自动清理 `runs/` 下超过保留天数的目录（默认 14）。
- `--max-runs-per-day`：每个日期目录最多保留 N 个 run（默认 20，按最近修改时间保留）。
- `--skip-prune-runs`：跳过本次清理（默认执行清理）。
- `--task-files`：视图任务文件列表，供契约相关门禁读取。

## 当前门禁分组（SSoT 以脚本为准）

### Hard Gates

- `check_docs_utf8_integrity.py`
- `check_prd_gdd_semantic_consistency.py`
- `remind_overlay_task_drift.py`
- `check_task_contract_refs.py`
- `check_no_hardcoded_core_events.py`
- `forbid_mirror_path_refs.py`
- `validate_contracts.py`
- `check_domain_contracts.py`
- `check_contract_interface_docs.py`
- `check_test_naming.py`
- `check_gate_bundle_consistency.py`
- `check_workflow_gate_enforcement.py`

### Soft Gates

- `generate_task_contract_test_matrix.py`
- `check_acceptance_stability_template.py`

## CI 接入规范

已接入以下工作流：

- `.github/workflows/windows-quality-gate.yml`
- `.github/workflows/ci-windows.yml`

接入策略：

- 硬门：使用 `run_gate_bundle.py --mode hard`，作为阻断步骤。
- 软门：使用 `run_gate_bundle.py --mode soft`，并设置 `continue-on-error: true`。
- 其他运行时构建/导出/引擎步骤保持独立，不与本脚本耦合，避免一次改动影响面过大。

## 日志与产物

默认输出路径：

- `logs/ci/<YYYY-MM-DD>/gate-bundle/runs/<run-id>/hard/summary.json`
- `logs/ci/<YYYY-MM-DD>/gate-bundle/runs/<run-id>/soft/summary.json`
- `logs/ci/<YYYY-MM-DD>/gate-bundle/runs/<run-id>/summary.json`（`mode=all`）

每个门禁的原始输出会写入同目录下 `<gate-name>.log`，用于快速定位失败根因。
其中 `task_contract_test_matrix` 在 gate bundle 中会写入当前 run 目录（不再默认落盘到 `.taskmaster/docs/`），用于减少跟踪文件噪声。

## 变更规则

当新增或删除门禁时，必须同步更新以下三处：

1. `scripts/python/run_gate_bundle.py`（真实执行口径）
2. 本文档（说明口径）
3. 对应 CI workflow（如需要新增步骤级行为）

不允许只改文档不改脚本，或只改脚本不改文档。

## Workflow 例外白名单

`check_workflow_gate_enforcement.py` 使用独立配置文件维护例外：

- `scripts/python/config/workflow-gate-allowlist.json`

配置项：

- `allowed_direct_scripts`：允许在 workflow 中直接调用、无需经 gate bundle 的脚本。
- `required_bundle_workflows`：必须调用 `run_gate_bundle.py` 的 workflow 清单。

维护规则：

- 新增 workflow 中的 Python 脚本调用前，先判断是否应纳入 gate bundle；
- 仅当脚本明确不属于门禁聚合域（例如发布专用检查）时，才可加入 `allowed_direct_scripts`；
- 修改白名单必须在 PR 描述里说明原因，避免静默扩大绕过范围。
