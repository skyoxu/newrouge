# NewRouge（Godot + C# / Windows-only）

`newrouge` 是一个基于 **Godot 4.5.x + C#（.NET 8）** 的 Windows 桌面游戏项目骨架：开箱即用、可测试、可导出。

入口与协作规则以 `CLAUDE.md` / `AGENTS.md` 为准；工程化/门禁/脚本入口以 `scripts/**` 为准。

---

## 3 分钟从 0 到导出

1) 安装 Godot .NET（mono）并设置环境：
   - `setx GODOT_BIN C:\Godot\Godot_v4.5.1-stable_mono_win64.exe`
2) 运行最小测试与冒烟（可选示例）：
   - `./scripts/test.ps1 -GodotBin "$env:GODOT_BIN"`（默认不含示例；`-IncludeDemo` 可启用）
   - `./scripts/ci/smoke_headless.ps1 -GodotBin "$env:GODOT_BIN"`
3) 在 Godot Editor 安装 Export Templates（Windows Desktop）。
4) 导出与运行 EXE：
   - `./scripts/ci/export_windows.ps1 -GodotBin "$env:GODOT_BIN" -Output build\NewRouge.exe`
   - `./scripts/ci/smoke_exe.ps1 -ExePath build\NewRouge.exe`

One‑liner（已在 Editor 安装 Export Templates 后）：
- PowerShell：`$env:GODOT_BIN='C:\\Godot\\Godot_v4.5.1-stable_mono_win64.exe'; ./scripts/ci/export_windows.ps1 -GodotBin "$env:GODOT_BIN" -Output build\NewRouge.exe; ./scripts/ci/smoke_exe.ps1 -ExePath build\NewRouge.exe`

## What You Get（模板内容）
- 适配层 Autoload：EventBus/DataStore/Logger/Audio/Time/Input/SqlDb
- 场景分层：ScreenRoot + Overlays；ScreenNavigator（淡入淡出 + Enter/Exit 钩子）
- 安全基线：仅允许 `res://`/`user://` 读取，启动审计 JSONL，HTTP 验证示例
- 可观测性：本地 JSONL（Security/Sentry 占位），性能指标（[PERF] + perf.json）
- 测试体系：xUnit + GdUnit4（示例默认关闭），一键脚本
- 导出与冒烟：Windows-only 脚本与文档

## Quick Links
- Project health dashboard: `docs/workflows/project-health-dashboard.md`
- Script entrypoints index: `docs/workflows/script-entrypoints-index.md`
- Stable public entrypoints: `docs/workflows/stable-public-entrypoints.md`
- Prototype lane guide: `docs/workflows/prototype-lane.md`
- 文档索引：`docs/PROJECT_DOCUMENTATION_INDEX.md`
- 快速开始（开发/测试/导出）：`docs/GETTING_STARTED.md`
- Windows-only 快速指引：`docs/migration/Phase-17-Windows-Only-Quickstart.md`
- FeatureFlags 快速指引：`docs/migration/Phase-18-Staged-Release-and-Canary-Strategy.md`
- 导出清单：`docs/migration/Phase-17-Export-Checklist.md`
- Headless 冒烟：`docs/migration/Phase-12-Headless-Smoke-Tests.md`
- 场景设计：`docs/migration/Phase-8-Scene-Design.md`
- 测试体系：`docs/migration/Phase-10-Unit-Tests.md`
- 安全基线：`docs/migration/Phase-14-Godot-Security-Baseline.md`
- 手动发布指引：`docs/release/WINDOWS_MANUAL_RELEASE.md`
- CI/发布工作流说明：`docs/workflows/`

## Task / ADR / PRD 工具（可选）
- `scripts/python/task_links_validate.py` —— 检查任务与 ADR / 章节 / Overlay 的回链完整性（CI 门禁）。
- `scripts/python/verify_task_mapping.py` —— 抽样检查任务映射元数据完整度（软检查）。
- `scripts/python/validate_task_master_triplet.py` —— 多份任务文件结构一致性校验（结构总检）。
- `scripts/python/prd_coverage_report.py` —— PRD → 任务覆盖报表（软检查）。

## Notes
- DB 后端：默认插件优先；`GODOT_DB_BACKEND=plugin|managed` 可控。
- 示例 UI/测试：默认关闭；设置 `TEMPLATE_DEMO=1` 启用（Examples/**）。

## Feature Flags（特性旗标）
- Autoload：`/root/FeatureFlags`（文件：`Game.Godot/Scripts/Config/FeatureFlags.cs`）
- 环境变量优先生效：
  - 单项：`setx FEATURE_demo_screens 1`
  - 多项：`setx GAME_FEATURES "demo_screens,perf_overlay"`
- 文件配置：`user://config/features.json`（示例：`{"demo_screens": true}`）
- 代码示例：`if (FeatureFlags.IsEnabled("demo_screens")) { /* ... */ }`

## 如何发版（打 tag）
- 确认主分支已包含所需变更：`git status && git push`
- 创建版本标签：`git tag v0.1.1 -m "v0.1.1 release"`
- 推送标签触发发布：`git push origin v0.1.1`
- 工作流：`Windows Release (Tag)` 自动导出并将 `build/NewRouge.exe` 附加到 GitHub Release。
- 如需手动导出：运行 `Windows Release (Manual)` 或 `Windows Export Slim`。

## 自定义应用元数据（图标/公司/描述）
- 文件：`export_presets.cfg` → `[preset.0.options]` 段。
- 关键字段：
  - `application/product_name`（产品名），`application/company_name`（公司名）
  - `application/file_description`（文件描述），`application/*_version`（版本）
  - 图标：`application/icon`（推荐 ICO：`res://icon.ico`；当前为 `res://icon.svg`）
- 修改后，运行 `Windows Export Slim` 或 `Windows Release (Manual)` 验证导出产物。
