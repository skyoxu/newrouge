# 项目文档索引（newrouge）

> 最后更新：2026-01-19  
> 项目定位：Godot 4.5 + C#/.NET 8（Windows-only）  
> 口径说明：以 Godot + C# 为唯一运行时口径；`migration/**` 仅作为历史/材料库，不作为当前实现依据。

---

## Quick Links（先看这些）

- 项目总览与一键命令：`../README.md`
- AI/协作规则（SSoT）：`../CLAUDE.md`、`../AGENTS.md`
- 快速开始（开发/测试/导出）：`GETTING_STARTED.md`
- 测试框架与门禁说明：`testing-framework.md`
- 文档导航（Base 骨干）：`architecture/base/00-README.md`
- CI/发布工作流说明：`workflows/`

---

## 1) 入口文档（SSoT）

- `../README.md`：模板简介、Quick Links、常用命令
- `../CLAUDE.md`：单一真相（AI 助手/架构/门禁/日志规范）
- `../AGENTS.md`：协作与编码规范（Windows only、UTF-8、日志与取证）

---

## 2) Getting Started（开始开发）

- `GETTING_STARTED.md`：从 0 到可跑/可测/可导出
- `testing-framework.md`：xUnit + GdUnit4 + 覆盖率/门禁（Windows）

---

## 3) 架构文档（Base-Clean，arc42 12 章）

目录：`architecture/base/`

- `architecture/base/00-README.md`：Base 导航与维护说明
- `architecture/base/01-introduction-and-goals-v2.md`：约束与目标（Godot+C# 口径）
- `architecture/base/02-security-baseline-godot-v2.md`：安全基线（Godot 运行时）
- `architecture/base/03-observability-sentry-logging-v2.md`：可观测性与 Release Health（Sentry）
- `architecture/base/04-system-context-c4-event-flows-v2.md`：系统上下文、容器与事件流（Signals/Contracts）
- `architecture/base/05-data-models-and-storage-ports-v2.md`：数据模型与存储端口
- `architecture/base/06-runtime-view-loops-state-machines-error-paths-v2.md`：运行时视图与状态机/错误路径
- `architecture/base/07-dev-build-and-gates-v2.md`：开发/构建/质量门禁（Windows）
- `architecture/base/08-crosscutting-and-feature-slices.base.md`：08 章模板（Base 禁止具体纵切）
- `architecture/base/09-performance-and-capacity-v2.md`：性能与容量（帧时间 P95 门禁）
- `architecture/base/10-i18n-ops-release-v2.md`：i18n 与发布运维（Windows-only）
- `architecture/base/11-risks-and-technical-debt-v2.md`：风险与技术债
- `architecture/base/12-glossary-v2.md`：术语表

---

## 4) ADR（架构决策记录）

目录：`adr/`

- `architecture/ADR_INDEX_GODOT.md`：当前 Godot 口径的 ADR 索引（Accepted + Addenda）
- `adr/guide.md`：ADR 编写指南

---

## 5) Workflows（CI/协作手册）

目录：`workflows/`

- `workflows/doc-stack-convergence-guide.md`：文档口径收敛（Base/Migration 扫描、取证与验证）
- `workflows/serena-mcp-command-reference.md`：Serena / Codex CLI 常用命令
- `workflows/superclaude-command-reference.md`：SuperClaude 工作流说明
- `workflows/task-master-superclaude-integration.md`：Taskmaster + SuperClaude 集成

---

## 6) Migration（历史对照与资料库）

目录：`migration/`（历史/材料库；不作为当前实现依据）

- `migration/MIGRATION_INDEX.md`
- `migration/Phase-12-Headless-Smoke-Tests.md`
- `migration/Phase-17-Windows-Only-Quickstart.md`
- `migration/Phase-17-Export-Checklist.md`
- `migration/Phase-18-Staged-Release-and-Canary-Strategy.md`

---

## 7) Scripts & CI（可执行入口）

### PowerShell（Windows）

- `../scripts/ci/quality_gate.ps1`：一键门禁入口（调用 Python gates，可选导出/冒烟/性能门禁）
- `../scripts/ci/smoke_headless.ps1`：Godot headless 冒烟（产出 `logs/ci/**`）
- `../scripts/ci/export_windows.ps1`：导出 Windows EXE
- `../scripts/ci/check_perf_budget.ps1`：解析 `[PERF]` 标记并做 P95 门禁
- `../scripts/ci/verify_base_clean.ps1`：Base-Clean 校验（禁止 Base 出现 PRD-ID/具体 08 内容）

### Python（py -3）

- `../scripts/python/quality_gates.py`：本地/CI 统一门禁编排（dotnet + gdunit + encoding 等）
- `../scripts/python/check_sentry_secrets.py`：Sentry Secrets 软门禁（Step Summary）
- `../scripts/python/check_encoding.py`：UTF-8/疑似乱码扫描（写入 `logs/ci/<YYYY-MM-DD>/encoding/**`）
- `../scripts/python/scan_doc_stack_terms.py`：旧技术栈术语扫描（用于文档收敛取证）
- `../scripts/python/task_links_validate.py`：任务 ↔ ADR/章节/Overlay 回链校验（CI 门禁）
- `../scripts/python/verify_task_mapping.py`：抽样检查任务映射元数据完整度（软检查）
- `../scripts/python/validate_task_master_triplet.py`：多份任务文件结构总检（本地/后续 CI）
- `../scripts/python/prd_coverage_report.py`：PRD→任务覆盖报表（软检查）

---

## 8) 日志与工件（排障入口）

- 统一目录：`logs/**`（单元/引擎冒烟/CI/性能/审计）
- 建议先看：`logs/ci/<YYYY-MM-DD>/`（门禁与扫描报告）

---

## 9) PRD（产品需求文档）

目录：`prd/`

- `prd/PRD-NEWROUGE-GAME-0001.md`：黑暗卡牌肉鸽（3角色+天赋树）
- `prd/SSOT-LOCKS-NEWROUGE-V1.md`：v1 设计锁定表（SSoT，口径冻结）
- `prd/EVENT-ID-CATALOG-NEWROUGE-V1.md`：v1 事件 ID 目录与落地优先级
- `prd/CARD-ID-CATALOG-NEWROUGE-V1.md`：v1 卡牌 ID 目录（内容身份证）
- `prd/RELIC-ID-CATALOG-NEWROUGE-V1.md`：v1 遗物 ID 目录（内容身份证）
- `prd/CONTENT-POWER-BOUNDS-AND-COMBO-RULES-NEWROUGE-V1.md`：v1 内容强度边界与组合禁区
- `prd/CONTENT-AUTHORING-ENTRY-NEWROUGE-V1.md`：v1 内容作者单一入口（制作顺序与依赖）
- `prd/CONTENT-REVIEW-CHECKLIST-NEWROUGE-V1.md`：v1 内容验收清单（P0/P1）
- `prd/MECHANICS-EDGE-CASES-SSOT-NEWROUGE-V1.md`：v1 机制边界与反例 SSOT（防歧义返工）
- `prd/PLAYER-FEEDBACK-EXPLAINABILITY-NEWROUGE-V1.md`：v1 可解释反馈输出规格（事件/奖励/升级/存档）
- `prd/BALANCE-REGRESSION-BASELINE-NEWROUGE-V1.md`：v1 平衡与内容回归基线（最小必跑包）
- `prd/SCREEN-BY-SCREEN-PLAYER-SPECS-NEWROUGE-V1.md`：v1 逐屏玩家体验规格（闭环可执行版）
- `prd/NARRATIVE-AND-COPY-STYLE-GUIDE-NEWROUGE-V1.md`：v1 叙事与文案风格指南（禁用语境止损）
- `prd/TERMS-AND-COPY-GLOSSARY-NEWROUGE-V1.md`：v1 全局术语与按钮文案表（防同义词漂移）
- `prd/COPY-FORBIDDEN-WORDS-QA-CHECKLIST-NEWROUGE-V1.md`：v1 文案禁用语境清单（P0）
- `prd/PLAYER-CONFUSION-FIX-TRACKER-NEWROUGE-V1.md`：v1 玩家困惑点→修正策略追踪表
- `prd/PLAYTEST-SCRIPT-60MIN-NEWROUGE-V1.md`：v1 60 分钟试玩脚本与记录表
- `prd/PLAYTEST-ISSUE-GRADING-AND-REVISION-GUIDE-NEWROUGE-V1.md`：v1 试玩问题分级与回填指引

---

## 10) GDD（游戏设计文档）

目录：`gdd/`

- `gdd/GDD-NEWROUGE-V1.md`：NewRouge v1 GDD（工作版；与 PRD 互相引用，便于拆任务与验收）
