# NewRouge 文档总索引

> 维护口径：Windows-only / Godot 4.5.1 / C# .NET 8 / UTF-8  
> 当前任务 SSoT：`.taskmaster/tasks/tasks.json` + 视图任务文件

## 0. 先读这些
- 项目规则：`AGENTS.md`
- 上手指南：`docs/GETTING_STARTED.md`
- 测试框架：`docs/testing-framework.md`
- 任务主文件：`.taskmaster/tasks/tasks.json`
- 任务视图：`.taskmaster/tasks/tasks_back.json`、`.taskmaster/tasks/tasks_gameplay.json`

## 1. 架构文档

### 1.1 Base（跨切面 SSoT）
- 路径：`docs/architecture/base/`
- 说明：跨切面口径（安全、可观测、运行时、质量门禁）只在 Base 与 ADR 固化。

### 1.2 Overlay（功能纵切）
- 路径：`docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/`
- 当前纵切：M1 Warrior
- 入口：`docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/_index.md`

### 1.3 ADR
- 路径：`docs/adr/`
- 索引：`docs/architecture/ADR_INDEX_GODOT.md`
- 当前关键：
  - `docs/adr/ADR-0032-save-resume-determinism.md`
  - `docs/adr/ADR-0033-card-identity-and-forms.md`

## 2. 产品与设计文档
- PRD 主文档：`docs/prd/PRD-NEWROUGE-GAME-0001.md`
- GDD 主文档：`docs/gdd/GDD-NEWROUGE-V1.md`
- 锁定表：`docs/prd/SSOT-LOCKS-NEWROUGE-V1.md`
- Playtest 脚本：`docs/prd/PLAYTEST-SCRIPT-60MIN-NEWROUGE-V1.md`
- Playtest 分级：`docs/prd/PLAYTEST-ISSUE-GRADING-AND-REVISION-GUIDE-NEWROUGE-V1.md`

## 3. 契约与测试入口
- 契约目录：`Game.Core/Contracts/`
- Core 测试：`Game.Core.Tests/`
- Godot 测试：`Tests.Godot/`
- Overlay 验收清单：`docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/ACCEPTANCE_CHECKLIST.md`

## 4. 工作流与脚本
- 方法论：`docs/workflows/acceptance-semantics-methodology.md`
- 任务语义工具：`scripts/sc/`
- CI/Pipeline 脚本：`scripts/python/`

## 5. 日志与工件
- CI：`logs/ci/<YYYY-MM-DD>/`
- 单测：`logs/unit/<YYYY-MM-DD>/`
- E2E：`logs/e2e/<YYYY-MM-DD>/`
- 性能：`logs/perf/<YYYY-MM-DD>/`

## 6. 当前执行原则
- 不再把 PRD/GDD 作为唯一事实源；以任务主文件与任务视图组合作为交付真相。
- 文档改动必须可回链到 ADR、Overlay、Test-Refs 与任务验收条目。
- 所有关键文档必须通过 UTF-8 / 无 BOM / 无语义乱码门禁。

