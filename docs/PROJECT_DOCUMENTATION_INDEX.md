# NewRouge 文档索引

本文件是本仓文档导航的入口，口径以 Windows-only + Godot 4.5.x + C#(.NET 8) 为准。

## 会话重置后建议阅读顺序

1. `README.md`
2. `AGENTS.md`
3. `docs/PROJECT_DOCUMENTATION_INDEX.md`
4. `docs/testing-framework.md`
5. `DELIVERY_PROFILE.md`
6. `docs/workflows/local-hard-checks.md`
7. `docs/workflows/project-health-dashboard.md`
8. `execution-plans/` 下最新文件
9. `decision-logs/` 下最新文件

## 核心事实源（SSoT）

- 任务三件套：`.taskmaster/tasks/tasks.json`、`.taskmaster/tasks/tasks_back.json`、`.taskmaster/tasks/tasks_gameplay.json`
- ADR：`docs/adr/ADR-*.md`、`docs/architecture/ADR_INDEX_GODOT.md`
- Base 架构：`docs/architecture/base/**`
- Overlay 纵切：`docs/architecture/overlays/**/08/**`
- 测试规范：`docs/testing-framework.md`

## 工作流文档入口

- 仓库升级指南：`docs/workflows/business-repo-upgrade-guide.md`
- 模板升级协议：`docs/workflows/template-upgrade-protocol.md`
- 项目健康看板：`docs/workflows/project-health-dashboard.md`
- 本地硬校验：`docs/workflows/local-hard-checks.md`
- 稳定入口清单：`docs/workflows/stable-public-entrypoints.md`
- 脚本入口索引：`docs/workflows/script-entrypoints-index.md`

## 主要脚本入口

- 仓库级硬门：`py -3 scripts/python/dev_cli.py run-local-hard-checks`
- 项目健康扫描：`py -3 scripts/python/dev_cli.py project-health-scan`
- 项目健康服务：`py -3 scripts/python/dev_cli.py project-health-scan --serve`
- 任务评审流水线：`py -3 scripts/sc/run_review_pipeline.py --task-id <id>`

## 证据与产物

- CI 与本地校验：`logs/ci/<YYYY-MM-DD>/`
- 单元测试：`logs/unit/<YYYY-MM-DD>/`
- 引擎/E2E：`logs/e2e/<YYYY-MM-DD>/`
- 性能：`logs/perf/<YYYY-MM-DD>/`
