# Repository Guide

本文件是 `newrouge` 的全局约束与任务路由层。不要把它扩展成完整命令手册，也不要在会话启动时预加载所有工作流文档。

## 项目标识与全局不变量

- Repository: `newrouge`
- Product: Windows-only Godot 4.5.1 + C# 单机项目
- 默认交付姿态: `fast-ship`
- 默认安全姿态: `host-safe`
- 与用户沟通使用中文；代码、脚本、测试、注释、打印文本使用英文。
- Windows 为目标环境；Python 命令使用 `py -3`；文档读写 UTF-8；不使用 Emoji。
- 日志、审计和运行证据写入 `logs/**`。
- 非 trivial 工作需要显式步骤和可恢复进度；跨 session、阶段迁移、工作流/harness 控制面改造使用 `execution-plans/**`。
- 不保留无用兼容层；旧格式兼容只能服务真实历史数据，不得成为第二套权威。

## 权威与保护边界

- Chapter 顺序保持 Chapter 3 → 4 → 5（按需）→ 6 → 7；Chapter 5 `BLOCKED` 阻断 Chapter 6。
- Taskmaster 三联继续拥有任务状态；Review、MVG、Technical Debt、Knowledge 不能自行写 Task done。
- Taskmaster 三联:
  - `.taskmaster/tasks/tasks.json`
  - `.taskmaster/tasks/tasks_back.json`
  - `.taskmaster/tasks/tasks_gameplay.json`
- PRD: `.taskmaster/docs/prd.txt`、`docs/prd/**`
- ADR: `docs/adr/ADR-*.md`、`docs/architecture/ADR_INDEX_GODOT.md`
- Base architecture: `docs/architecture/base/**`
- Overlay: `docs/architecture/overlays/<PRD-ID>/08/**`
- Contract SSoT: `Game.Core/Contracts/**`；必须 BCL-only，不引用 `Godot.*`。
- Domain logic: `Game.Core/**`；Godot adapter: `Game.Godot/**` 与 adapter 层。
- Testing authority: `docs/testing-framework.md`
- Run/recovery protocol: `docs/workflows/run-protocol.md`
- Chapter 6 hard checks 必须使用 `--skip-project-health`；该参数不跳过 gate bundle、dotnet、GdUnit/smoke。
- 不隐式刷新 Project Health、全局 Knowledge catalog 或 publication。
- Knowledge shadow/handoff 是可选读取与冻结基础设施，不替代直接权威来源。
- Persistent Harness、run/turn、append-only events、artifact integrity、resume/fork/abort、profile lock、approval、rerun guard、deterministic reuse 与 stop-loss 均为保留协议。

## 按任务读取路由

先读与当前任务匹配的入口，再读取该入口要求的直接来源。跨领域任务取必要路由的并集，不限制只能选一行。不要按目录时间戳猜“当前任务”，也不要把最新 plan/decision 默认当成当前工作。

| 任务范围 | 首要入口 | 按需补充 |
| --- | --- | --- |
| 项目身份/状态 | `README.md` | 当前任务三联或用户明确指定状态文件 |
| Chapter 3 | `workflow.md` 第 3 章 | `.agents/skills/workflow-chapter3-task-triplet-baseline/SKILL.md`；本次 PRD/GDD/planning sources |
| Chapter 4 | `workflow.md` 第 4 章 | `.agents/skills/workflow-chapter4-overlays-contracts-baseline/SKILL.md`；任务三联、相关 Overlay/Contract |
| Chapter 5 | `workflow.md` 第 5 章 | `.agents/skills/workflow-chapter5-semantics-stabilization/SKILL.md`；当前 reconciliation/readiness |
| Chapter 6 新任务 | `workflow.md` 6.0、6.3；`run-single-task-chapter6` | `.agents/skills/workflow-chapter6-single-task-daily-loop/SKILL.md`；当前 Task/Acceptance 和相关权威 |
| Chapter 6 恢复 | `resume-task --recommendation-only` | `chapter6-route --recommendation-only`；仅按需要展开该 run 的 sidecars/events |
| Chapter 7 | `workflow.md` 第 7 章、`docs/gdd/ui-gdd-flow.md` | Chapter 7 Skill、profile guide |
| Prototype | `docs/workflows/prototype-lane.md` | 同目录 playbook、prototype-tdd |
| Architecture/Contract | `docs/architecture/ADR_INDEX_GODOT.md` | 相关 ADR、Base/Overlay、`Game.Core/Contracts/**` |
| Testing/MVG | `docs/testing-framework.md` | `docs/workflows/mvg-integration-acceptance.md`、选定 manifest |
| Harness/工作流维护 | `docs/workflows/run-protocol.md` | 当前涉及入口脚本、schema、`docs/workflows/local-hard-checks.md` |
| 显式 plan/decision 工作 | 用户或当前任务绑定的具体文件 | 该文件引用的当前来源 |

## Chapter 6 快速入口

- 新任务：
  - `py -3 scripts/python/dev_cli.py run-single-task-chapter6 --task-id <id> --godot-bin "$env:GODOT_BIN" --delivery-profile fast-ship`
- 恢复：
  - `py -3 scripts/python/dev_cli.py resume-task --task-id <id> --recommendation-only`
  - `py -3 scripts/python/dev_cli.py chapter6-route --task-id <id> --recommendation-only`
- 只有 compact recovery 无法支持当前决定时，才展开 `latest.json`、summary、repair guide、agent review 或 run-events。
- 无历史 run 时走现有新任务逻辑，不伪造 latest。
- 用户指定多个任务或没有唯一 task id 时，只用明确指令和真实任务三联定位；无法唯一定位再请求澄清。

## Knowledge 与 Review 上下文

- 直接权威来源路径始终可用：当前 Task、Requirement、Acceptance、相关 ADR/Overlay/Contract。
- 可选 Knowledge shadow/handoff 继续遵守 `docs/workflows/knowledge-context-shadow.md` 与 `docs/workflows/knowledge-context-freeze.md`。
- `shadow_ready`、排名或 handoff 校验通过不等于语义完备。
- Chapter 6 只可在 RED 前做 bounded Knowledge 查询；RED/GREEN/REFACTOR 中发生实质范围变化时停止本序列并建立新的显式 preflight/context revision。
- Review handoff 使用独立 `consumer=review` 上下文；不得修改旧 frozen consumer 来绕过边界。

## 测试与完成规则

- 领域逻辑使用 xUnit（`Game.Core.Tests/**`）。
- 场景与引擎胶水使用 GdUnit4（`Tests.Godot/**`）。
- Acceptance 必须引用真实行为证据；机器错误、timeout、缺报告不能冒充行为 RED 或通过。
- 人工体验证据不能由模型代签。
- 不通过关闭测试、缩小已承诺范围或写字符串存在性测试取得假绿。
- 6.8 final-pass 与 6.9 hard checks 保留；局部验证不能替代最终适用范围检查。
- 任何 Task done 仍通过既有 Taskmaster 完成路径，不由 Review、Technical Debt、MVG 或 Knowledge 直接写入。

## 文档与维护

- 详细命令放到 owning workflow/doc，不在根文件复制。
- 修改工作流规则时，同阶段同步更新消费者、配置、schema/fallback validator 与对应测试。
- 历史日志是证据，不是当前指令；仅在当前 Task、恢复对象、ADR 或冻结来源显式引用时展开。
- source 缺失时回退直接权威来源；不能用摘要猜测缺失边界。
