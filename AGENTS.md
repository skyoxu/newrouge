# Repository Guide

本文件是 `newrouge` 的路由层，不承载大段细节。稳定规则放到 `docs/agents/**`、`docs/workflows/**`、`docs/adr/**`、`docs/architecture/**`。

## 项目标识

- Repository: `newrouge`
- Product: Windows-only Godot 4.5.1 + C# 单机项目
- 默认交付姿态: `fast-ship`
- 默认安全姿态: `host-safe`
- 升级对齐基线: `docs/workflows/business-repo-upgrade-guide.md`

## 不可协商规则

- 与用户沟通统一使用中文。
- 默认环境是 Windows，命令必须可在 Windows 执行。
- 文档读写统一 UTF-8。
- 不使用 Emoji。
- 代码、脚本、测试、注释、打印文本统一英文。
- 日志、审计和证据统一放在 `logs/**`。
- 非 trivial 任务必须显式分步并持续更新进度。
- 不保留无用兼容层，过期路径应清理。
- Review `Needs Fix` 按当前 fix-through 与 P1 floor 处理：必修项先修；允许延期的 findings 进入 `docs/technical-debt.md`。只有真实政策/权威/不可逆决定才写 Decision Log，只有跨 session、顺序协调、迁移或分阶段恢复需要才写 Execution Plan。

## Context Reset 与按任务读取

Context Reset 后先读取本文件，再按当前任务范围选择首要入口；不要固定预加载一组无关文档，也不要用“目录中最新 plan/decision”猜测当前任务。跨领域任务取必要路由的并集。

| 任务范围 | 首要入口 | 按需补充 |
| --- | --- | --- |
| 项目身份/状态 | `README.md` | 当前任务三联或用户明确指定的状态文件 |
| Chapter 3 | `workflow.md` 第 3 章 | `.agents/skills/workflow-chapter3-task-triplet-baseline/SKILL.md`；本次 PRD/GDD/planning sources |
| Chapter 4 | `workflow.md` 第 4 章 | `.agents/skills/workflow-chapter4-overlays-contracts-baseline/SKILL.md`；任务三联、相关 Overlay/Contract |
| Chapter 5 | `workflow.md` 第 5 章 | `.agents/skills/workflow-chapter5-semantics-stabilization/SKILL.md`；当前 reconciliation/readiness |
| Chapter 6 新任务 | `workflow.md` 6.0、6.3；`run-single-task-chapter6` | `.agents/skills/workflow-chapter6-single-task-daily-loop/SKILL.md`；当前 Task/Acceptance、有效 Chapter 5 readiness 与相关权威 |
| Chapter 6 恢复 | `resume-task --recommendation-only` | `chapter6-route --recommendation-only`；仅在决策需要时展开该 run 的 sidecars/events |
| Chapter 7 | `workflow.md` 第 7 章；`docs/gdd/ui-gdd-flow.md` | Chapter 7 Skill、profile guide 与当前 backlog/capability |
| Prototype | `docs/workflows/prototype-lane.md` | 同目录 playbook、prototype-tdd |
| Architecture/Contract | `docs/architecture/ADR_INDEX_GODOT.md` | 相关 ADR、Base/Overlay、`Game.Core/Contracts/**` |
| Knowledge 查看/拓扑 | `docs/workflows/project-health-knowledge.md` | Chapter 3/5 attempt 与 stable 视图；MVG 汇总证据另读 MVG owning doc |
| Testing/MVG | `docs/testing-framework.md` | `docs/workflows/mvg-integration-acceptance.md`、选定 manifest |
| Harness/工作流维护 | `docs/workflows/run-protocol.md` | 当前涉及入口脚本、schema、`docs/workflows/local-hard-checks.md` |
| 显式 plan/decision 工作 | 用户或当前任务绑定的具体文件 | 该文件引用的来源；不按目录时间戳猜测 |

历史日志是证据而不是当前指令。被当前 Task、ADR、冻结来源、恢复对象或显式 plan/decision 引用时再展开；source 缺失且影响边界判断时 fail closed，不用摘要猜测替代。

## 权威来源

优先使用以下来源，不要随意重建索引。

- Taskmaster 三联:
  - `.taskmaster/tasks/tasks.json`
  - `.taskmaster/tasks/tasks_back.json`
  - `.taskmaster/tasks/tasks_gameplay.json`
- PRD:
  - `.taskmaster/docs/prd.txt`
  - `docs/prd/**`
- ADR:
  - `docs/adr/ADR-*.md`
  - `docs/architecture/ADR_INDEX_GODOT.md`
- Base 架构:
  - `docs/architecture/base/**`
- Overlay:
  - `docs/architecture/overlays/<PRD-ID>/08/**`
- 测试规则:
  - `docs/testing-framework.md`
- 交付与执行协议:
  - `DELIVERY_PROFILE.md`
  - `docs/workflows/run-protocol.md`
  - `docs/workflows/local-hard-checks.md`
- Chapter 7:
  - `docs/gdd/ui-gdd-flow.md`
  - `docs/workflows/chapter7-profile.json`
  - `docs/workflows/chapter7-profile-guide.md`
  - `docs/workflows/templates/chapter7-profile.template.json`
  - `docs/workflows/templates/chapter7-profile.minimal.example.json`

## 核心入口

根文件只保留稳定入口；Chapter 3–7、Prototype、MVG 与维护命令的完整参数和阶段说明按上表读取 owning docs，不在这里重复维护。

- Chapter 6 新任务：`py -3 scripts/python/dev_cli.py run-single-task-chapter6 --task-id <task-id> --godot-bin <godot-bin> --delivery-profile <profile>`
- Chapter 6 恢复：`py -3 scripts/python/dev_cli.py resume-task --task-id <task-id> --recommendation-only`
- Chapter 6 路由：`py -3 scripts/python/dev_cli.py chapter6-route --task-id <task-id> --recommendation-only`
- 仓库硬检查：`py -3 scripts/python/dev_cli.py run-local-hard-checks --skip-project-health --godot-bin <godot-bin>`

详细入口索引：
- `workflow.md`：Chapter 3 → 7 的阶段规则与 owning 命令。
- `docs/workflows/stable-public-entrypoints.md`：稳定公共入口及恢复边界。
- `docs/workflows/script-entrypoints-index.md`：脚本入口索引。
- `docs/workflows/prototype-lane.md`：Prototype。
- `docs/workflows/mvg-integration-acceptance.md`：MVG 与 Mutation。

## Recovery Stop-Loss Signals

- `rerun_guard`: 确定性路径已经给出停止信号，不要盲目重开 `6.7`。
- `llm_retry_stop_loss`: 确定性已绿，且首轮长时 LLM 已超时；优先走窄化收敛而非全量重跑。
- `sc_test_retry_stop_loss`: 同一运行内重复单测重试已证明无效；先修单测根因再继续。
- `waste_signals`: 在已知单测/根因失败后仍发生引擎链路消耗；应先止损再执行后续步骤。

## 架构与契约规则

- 契约 SSoT 在 `Game.Core/Contracts/**`。
- 契约代码必须 BCL-only，不得引用 `Godot.*`。
- 领域逻辑在 `Game.Core/**`。
- Godot 适配在 `Game.Godot/**` 与 adapter 层。
- 功能纵切仅放在 `docs/architecture/overlays/<PRD-ID>/08/**`。
- 若阈值、契约、安全口径、发布策略改变，必须新增或 supersede ADR。

## 测试规则

- 领域逻辑: xUnit（`Game.Core.Tests/**`）。
- 场景与引擎胶水: GdUnit4（`Tests.Godot/**`）。
- 禁止通过关闭测试拿绿灯。
- acceptance 条目必须有 `Refs:`，并与 tasks 视图与 overlay 回链一致。

## 任务视图规则

- 真实任务文件在 `.taskmaster/tasks/**`。
- 跨文件映射固定:
  - `tasks.json.master.tasks[].id`
  - `tasks_back.json[].taskmaster_id`
  - `tasks_gameplay.json[].taskmaster_id`
- `semantic_review_tier` 必须写入真实视图文件，不仅是示例文件。

## 文档规则

- 保持仓库标识为 `newrouge`，清理过期模板名与无效示例。
- 不在 overlay 复制 Base/ADR 的阈值正文。
- 契约字段用路径引用，不做文档内重复粘贴。\n

## 里程碑增量边界

- 新里程碑继续使用现有 Chapter 3→6 与 MVG 流程，不创建第二套任务状态或独立 MVG 生命周期。
- Chapter 3 `add` 必须从版本化 `docs/workflows/chapter3-source-set.json` 保留累计来源；退役来源必须显式声明。
- 已存在任务 ID 不得被候选默认值覆盖；update/reuse/retire 必须来自可审阅变更计划。
- Chapter 4 只改受影响页面/任务；成熟 Overlay 的稀疏更新默认合并。
- Chapter 6 仍为单任务实施；若任务属于里程碑增量，优先消费经 Chapter 5 绑定的 milestone handoff，不自行扩大范围。
- MVG manifest 是累计回归基线；旧 flow/test 只有在有规格依据的显式 retire 中才能移除。
