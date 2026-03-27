# NewRouge (Godot 4.5.1 + C#)

`newrouge` 是一个 Windows-only 的 Godot 4.5.1 + C#（.NET 8）单机项目模板。

## 项目姿态

- Delivery profile: `fast-ship`
- Security profile: `host-safe`
- 运行平台: Windows Desktop

## Quick Links

- 项目健康面板: `docs/workflows/project-health-dashboard.md`
- 脚本入口索引: `docs/workflows/script-entrypoints-index.md`
- 稳定公共入口: `docs/workflows/stable-public-entrypoints.md`
- 原型工作流: `docs/workflows/prototype-lane.md`
- 本地硬检查: `docs/workflows/local-hard-checks.md`

## 快速开始（Windows）

1. 安装 Godot .NET 4.5.1 与 .NET 8 SDK。
2. 设置 Godot 可执行路径。
   - PowerShell: `$env:GODOT_BIN = "C:\\Godot\\Godot_v4.5.1-stable_mono_win64.exe"`
3. 恢复并构建。
   - `dotnet restore NewRouge.sln`
   - `dotnet build NewRouge.sln -c Debug`
4. 可选：执行本地硬检查。
   - `py -3 scripts/python/dev_cli.py run-local-hard-checks --godot-bin "$env:GODOT_BIN"`

## 核心命令

- 任务恢复（推荐入口）:
  - `py -3 scripts/python/dev_cli.py resume-task --task-id <task-id>`
- 任务级评审流水线:
  - `py -3 scripts/sc/run_review_pipeline.py --task-id <task-id> --godot-bin "$env:GODOT_BIN"`
- 门禁聚合（仅 hard）:
  - `py -3 scripts/python/run_gate_bundle.py --mode hard --task-files .taskmaster/tasks/tasks_back.json .taskmaster/tasks/tasks_gameplay.json`

## 核心路径

- Taskmaster 三联文件:
  - `.taskmaster/tasks/tasks.json`
  - `.taskmaster/tasks/tasks_back.json`
  - `.taskmaster/tasks/tasks_gameplay.json`
- PRD 输入:
  - `.taskmaster/docs/prd.txt`
  - `docs/prd/**`
- 架构与决策:
  - `docs/architecture/base/**`
- `docs/architecture/overlays/<PRD-ID>/08/**`
  - `docs/adr/ADR-*.md`
- 运行日志与证据:
  - `logs/**`

## 工程基线

- 契约 SSoT: `Game.Core/Contracts/**`
- 契约仅允许 BCL，不允许引用 `Godot.*`
- 领域逻辑放在 `Game.Core/**`
- 引擎适配放在 `Game.Godot/**`
- 文档与任务通过 ADR + Base + Overlay + Refs 保持回链一致
