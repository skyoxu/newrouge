# 项目健康仪表盘（newrouge 对齐版）

本文档定义 `F:\newrouge` 当前可执行的 project-health 入口与产物。

## 可用能力

- `detect-project-stage`：检测仓库阶段与任务三件套状态。
- `doctor-project`：检查仓库基线（入口文件、测试工程、任务三件套等）。
- `check-directory-boundaries`：执行目录边界硬规则与告警检查。
- `project-health-scan`：串行执行上述三项并刷新仪表盘产物。
- `serve-project-health`：本地启动 `127.0.0.1` 仪表盘服务。

## 推荐命令（Windows）

```powershell
py -3 scripts/python/dev_cli.py detect-project-stage
py -3 scripts/python/dev_cli.py doctor-project
py -3 scripts/python/dev_cli.py check-directory-boundaries
py -3 scripts/python/dev_cli.py project-health-scan
py -3 scripts/python/dev_cli.py serve-project-health --port 8765
```

## 直接脚本入口

```powershell
py -3 scripts/python/detect_project_stage.py
py -3 scripts/python/doctor_project.py
py -3 scripts/python/check_directory_boundaries.py
py -3 scripts/python/project_health_scan.py
py -3 scripts/python/serve_project_health.py --port 8765
```

## 产物路径

- `logs/ci/project-health/latest.json`
- `logs/ci/project-health/latest.html`
- `logs/ci/project-health/server.json`
- `logs/ci/project-health/detect-project-stage.latest.json`
- `logs/ci/project-health/doctor-project.latest.json`
- `logs/ci/project-health/check-directory-boundaries.latest.json`
- `logs/ci/<YYYY-MM-DD>/project-health/`（历史快照）

## 执行边界

- `project-health-scan` 是 project-health 主入口。
- `serve-project-health` 仅用于本地，不接入 CI。
- `--serve` 在 CI 环境会被拒绝并返回失败。
- 本仓已接入 `run-local-hard-checks` 协议链，可在仓库级硬门中统一消费 project-health 结果。
