# 项目能力状态总览（NewRouge）

本文档用于快速确认本仓在“脚本入口、文档索引、流程能力”上的当前状态。

## 已具备能力

- 仓库级硬校验统一入口：`py -3 scripts/python/dev_cli.py run-local-hard-checks`
- 项目健康能力链：
  - `detect-project-stage`
  - `doctor-project`
  - `check-directory-boundaries`
  - `project-health-scan`
  - `serve-project-health`
- 任务级评审流水线：`py -3 scripts/sc/run_review_pipeline.py --task-id <id>`
- 质量门禁聚合：`py -3 scripts/python/run_gate_bundle.py --mode hard|soft|all`
- 任务语义与验收工具链：`scripts/sc/llm_*.py`

## 已对齐文档

- `docs/workflows/business-repo-upgrade-guide.md`
- `docs/workflows/template-upgrade-protocol.md`
- `docs/workflows/project-health-dashboard.md`
- `docs/workflows/local-hard-checks.md`
- `docs/workflows/stable-public-entrypoints.md`
- `docs/workflows/script-entrypoints-index.md`

## 运行验证基线

- `py -3 scripts/python/project_health_scan.py --repo-root .` 返回 `status=ok`
- `py -3 scripts/python/dev_cli.py run-local-hard-checks --run-id <id>` 可生成完整 run 产物
- `py -3 scripts/sc/run_review_pipeline.py --task-id <id> --dry-run ...` 返回 `status=ok`

## 持续维护建议

- 新增脚本时同步更新 `script-entrypoints-index`，避免“有脚本无入口”。
- 升级模板时优先检查 4 份工作流文档，再检查脚本闭包依赖。
- 每次任务批次结束后执行一次 `project-health-scan`，优先清理 warn 项。
