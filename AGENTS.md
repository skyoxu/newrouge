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
| B 路线阶段／权威／迁移治理 | [ADR-0040（Accepted，未启用）](docs/adr/ADR-0040-b-route-stages-authority-and-activation.md) | 治理定义已采纳；实现及启用待后续交付，现行 A 命令仍有效 |
| B 路线 3A 来源记账 | [来源记账 owner 说明](docs/workflows/b-route-source-accounting.md) | `dev_cli.py b-route-sources --stage prepare\|account`；零 Task 提议与完整记账，不授予独立审计／正式采纳，现行 A 有效 |
| B 路线 3A 独立来源审计 | [来源审计 owner 说明](docs/workflows/b-route-source-audit.md) | `dev_cli.py b-route-sources --stage audit\|verify`；完整来源两步独立审计／只读 proof 复验，不授正式采纳或默认 B 启用 |
| B 路线只读迁移预检 | [预检 owner 说明](docs/workflows/b-route-migration-preflight.md) | `dev_cli.py b-route-preflight`；明确候选／意图／保护原身份，仅新 logs，不调用 apply 或授予启用 |
| B 路线 3C 只读任务变更预览 | [3C 预览 owner 说明](docs/workflows/b-route-task-preview.md) | `dev_cli.py b-route-task-preview`；盘点复用与真实缺口，输出业务增量与 3.2 同构草案，不写三联或分配正式 ID |
| B 路线 3C 受治理三联编译 | [3C 编译 owner 说明](docs/workflows/b-route-task-compilation.md) | `dev_cli.py b-route-task-compile`；九阶段受治理编译三联与 3C 绑定、两段锁合活 status、末推 catalog，不授 readiness/默认 B |
| B 路线统一 Task 来源解析 | [Task 来源解析 owner 说明](docs/workflows/b-route-task-origin-resolution.md) | `dev_cli.py b-route-task-origin`；纯只读零落盘分类 `B`/`A`/`explicit_not_enabled_a`/`blocked`，汇总适用计划集合与 `applicable_set_digest`，不授实施权 |
| B 路线 Chapter 4 绑定细化 | [Chapter 4 绑定细化 owner 说明](docs/workflows/b-route-chapter4-binding.md) | `dev_cli.py b-route-chapter4-binding`；细化生产契约与四部分定义、原始字节 `public-sync-journal`、双态核验与归因，发布 `stage=4` 绑定与 `origins`，不授 readiness/默认 B |
| B 路线共同 InputSet 与新鲜度 | [InputSet 与新鲜度 owner 说明](docs/workflows/b-route-input-set-resolution.md) | `dev_cli.py b-route-input-set`；汇总 3.3 计划集、3.4 绑定/候选单槽、Task 投影、契约/ADR/Overlay/manifest、依赖闭包与环境产 `input_set_digest`，归因 `3A..5`，`guarded_input_set` 仅持业务 scope 租约，不授实施权 |
| B 路线 Stage-5 义务与验证依据绑定 | [Stage-5 义务绑定 owner 说明](docs/workflows/b-route-stage5-obligations.md) | `dev_cli.py b-route-stage5-obligations`；承接 Stage-4/5 绑定与 3.3/3.5 核验，绑有效 manifest/审阅 delta 或合法非 Flow `other_verification_refs`、三类影响扩大、角色无自锁、共享去重与防削弱，发布 `stage="5"` 绑定并末推 catalog，不授 readiness/运行通过 |
| B 路线 Chapter 5 同源核对与 readiness | [Chapter 5 readiness owner 说明](docs/workflows/b-route-chapter5-readiness.md) | `dev_cli.py b-route-chapter5-readiness`；经 3.3 判 B、3.5 `guarded_input_set` 业务 scope 租约、全适用 `stage="5"` 绑定、只读复用 3A 证明并独立核对 Chapter 5 语义，冻 InputSet 产 readiness 并桥接 `load_task_readiness`/`refresh_chapter_knowledge`，守 P1 底线与旧 done 重验，`runtime_verified`/`default_b_enabled` 恒 false |
| B 路线 Chapter 6 统一实施门禁 | [Chapter 6 统一实施门禁 owner 说明](docs/workflows/b-route-chapter6-gate.md) | `dev_cli.py b-route-chapter6-gate`；公共 CLI、直接 Chapter 6、`_mvg_obligations` 与内部脚本共用 3.3→3.5→3.6→3.7 门禁与经密钥+OS 锁验证的父子业务 scope 租约，禁无 trace 放行/旁路/全局锁/隐式刷 Knowledge，`tasks.json` 短锁保定义投影不变，`runtime_verified`/`default_b_enabled` 恒 false |
| B 路线 Chapter 6 恢复与路由重验 | [Chapter 6 恢复与路由重验 owner 说明](docs/workflows/b-route-chapter6-recovery.md) | `resume-task`/`chapter6-route`/`inspect-run` 与 `--resume`/`--fork`/`needs-fix-fast` 共用实时 3.8 门禁、任务与依赖资格重算、运行冻结 InputSet 对账与跨目录持久止损/reopen 防洗白；`--recommendation-only` 严格零写，保后编辑且 `runtime_verified`/`default_b_enabled` 恒 false |
| B 路线缺陷分类与归属阶段路由 | [缺陷分类与归属阶段路由 owner 说明](docs/workflows/b-route-defect-routing.md) | `dev_cli.py b-route-defect-routing`；区分纯实现缺陷与定义/契约/所有权/交接/义务变更，禁弱化验收/N/A/改状态/删测/同义任务与刷 Knowledge，复用有效上游并产 `3A..5` 治理交接与 3.1/3.2 delta 校验，分列局部/运行/人工义务守 P1 底线，`runtime_verified`/`default_b_enabled` 恒 false |
| B 路线目标 slice Chapter 7 收口 | [目标 slice Chapter 7 收口 owner 说明](docs/workflows/b-route-chapter7-slice.md) | `dev_cli.py b-route-chapter7-slice`；按目标 Flow/slice 核对 UI 责任与合法非 UI 依据免等全游，复用匹配当前 InputSet 与测试身份的 Chapter 6 真实引擎输入证据，诚实核对 `.tscn`/适配器接线与人工独立边界，缺口返 `3A..5` 或走 3.1/3.2 保旧 `done` 与原生场景人工区，零刷 Knowledge 且 `runtime_verified`/`default_b_enabled` 恒 false |
| B 路线页面触发与全入口一致性 | [全入口一致性与 Epic3 交接 owner 说明](docs/workflows/b-route-entrypoint-parity.md) | `dev_cli.py b-route-entrypoint-parity` 与 `POST /api/knowledge/b-route`；页面与 `cli`/`direct`/`resume`/`route`/`runtime`/`mvg-run` 共用实时门禁、动态 InputSet、资格与业务 scope 锁，禁凭摘要/缓存/旧 ready 授权且 `preview`/`workspace` 零推进发布指针，含 Windows 并发核验与诚实 Epic3→Epic4 交接，`flow_completed`/`runtime_verified`/`default_b_enabled` 恒 false |
| B 路线受治理完整传递影响闭包 | [影响闭包 owner 说明](docs/workflows/b-route-impact-closure.md) | `dev_cli.py b-route-impact-closure`；从四部分定义、已提交 plan/binding、契约、测试义务、三联依赖与累计 MVG（含 `planned` Flow）反向边环安全去重求完整传递影响，缺边保守扩大不收缩，`--revalidate-proof` 分区选择性复验；只读零改 `tasks.json`/发布指针，`impact_accounting_only` 恒 true 且 `runtime_verified`/`default_b_enabled` 恒 false |
| B 路线可执行三类义务 VerificationScope | [VerificationScope owner 说明](docs/workflows/b-route-verification-scope.md) | `dev_cli.py b-route-verification-scope`；合成 4.1 影响、交付边界、累计/active manifest 与共同 InputSet 为辅助 schema 封存的验证合同，逐义务分 `existing_required`/`current_new`/`out_of_scope_future`，支持同 Flow 混载，拒失败 Flow 转 planned 与借失败/缺测删义务，分列可执行/待实施/人工/非 Flow 桶，同内容同 `scope_id`、漂移废受影响旧结论；只读零改 Task 状态，`runtime_verified`/`default_b_enabled` 恒 false |
| B 路线真实执行器范围消费与覆盖回执 | [范围执行器 owner 说明](docs/workflows/b-route-scope-runner.md) | `dev_cli.py run-mvg-acceptance --verification-scope <path>`；实时校验并消费 `VerificationScope`、隔离快照与短 metadata→业务 scope 租约，支持 `scoped`/`conservative_superset` 策略与止损，分报六类证据等级（含静态 `.tscn` 接线与真实引擎输入核验），产出封存 `coverage-receipt.json`；漏项/空报告/跳过/未完/漂移禁 PASS，协议夹具恒 `runtime_verified=false`，不改 Task 状态 |
| B 路线构建预热复用、共享证据去重与状态隔离 | [构建与共享证据复用 owner 说明](docs/workflows/b-route-evidence-reuse.md) | `dev_cli.py run-mvg-acceptance --verification-scope <path> --reuse-evidence-from <path> --reuse-build-from <path> --events-log <logs/.../*.jsonl>`；分离构建/预热复用与同快照共享测试去重（保唯一计数、Requirement 多路线覆盖与原始 `original_executed_at`，重验原始 `.trx`/`.xml`），逐测试隔离可变数据/临时目录并防快照污染，拒跨快照拼接、损坏与 Story 2.9 规划 adoption 混用，零速度/成本门槛与假省钱声明 |
| B 路线分层完成核对（Task/Flow/累计里程碑） | [分层完成核对 owner 说明](docs/workflows/b-route-completion-verdict.md) | `dev_cli.py b-route-completion-verdict --level task\|flow\|milestone\|non_flow` 与 `milestone_incremental_handoff.py`；分别核对单 Task 局部、目标 Flow（严禁证据等级混代、人工独立签收、专用集成 owner 免自锁）、同 snapshot 累计 `full-MVG`（禁跨 snapshot 拼接与部分充全量、范围外 B 保留后续责任不强迫提前实施）与合法非 Flow `other_verification`，损坏/过期/空/跳测拒并报六字段诊断，零改 `tasks.json`/`catalog.v1.json`/发布指针 |
| Chapter 3 | `workflow.md` 第 3 章 | `.agents/skills/workflow-chapter3-task-triplet-baseline/SKILL.md`；本次 PRD/GDD/planning sources |
| Chapter 4 | `workflow.md` 第 4 章 | `.agents/skills/workflow-chapter4-overlays-contracts-baseline/SKILL.md`；任务三联、相关 Overlay/Contract |
| Chapter 5 | `workflow.md` 第 5 章 | `.agents/skills/workflow-chapter5-semantics-stabilization/SKILL.md`；当前 reconciliation/readiness |
| Capability Planning | `workflow.md` 5.3 | `.agents/skills/plan-capabilities/SKILL.md`；显式 Chapter 5 ready task scope |
| MVG Planning | `workflow.md` 5.4 | `.agents/skills/plan-mvg/SKILL.md`；显式 Capability 文件/version 与目标 manifest |
| Chapter 6 新任务 | `workflow.md` 6.0、6.3；`run-single-task-chapter6` | `.agents/skills/workflow-chapter6-single-task-daily-loop/SKILL.md`；当前 Task/Acceptance、有效 Chapter 5 readiness 与相关权威 |
| Chapter 6 恢复 | `resume-task --recommendation-only` | `chapter6-route --recommendation-only`；仅在决策需要时展开该 run 的 sidecars/events |
| Chapter 7 | `workflow.md` 第 7 章；`docs/gdd/ui-gdd-flow.md` | Chapter 7 Skill、profile guide 与当前 backlog/capability |
| Prototype | `docs/workflows/prototype-lane.md` | 同目录 playbook、prototype-tdd |
| Architecture/Contract | `docs/architecture/ADR_INDEX_GODOT.md` | 相关 ADR、Base/Overlay、`Game.Core/Contracts/**` |
| Knowledge 查看/拓扑 | `docs/workflows/project-health-knowledge.md` | Chapter 3/5 attempt 与 stable 视图；MVG 汇总证据另读 MVG owning doc |
| Testing/MVG | `docs/testing-framework.md` | `docs/workflows/mvg-integration-acceptance.md`、选定 manifest |
| Harness/工作流维护 | `docs/workflows/run-protocol.md` | 当前涉及入口脚本、schema、`docs/workflows/local-hard-checks.md` |
| 显式 plan/decision 工作 | 用户或当前任务绑定的具体文件 | 该文件引用的来源；不按目录时间戳猜测 |
| Antigravity / Gemini 专属编排规范 | [geminiuse.md](geminiuse.md) | 仅适用于 Antigravity（含 `agy` CLI）与 Gemini 会话；Codex、Claude Code 及其他智能体完全忽略该文件 |

B 路线目标为 3A 来源审计 → 3B 无 Task 正式采纳 → 3C 任务承接 → 4–5 绑定／readiness → 6 单 Task → 适用 7 → Flow／累计收尾。阶段、记录权威及 A 冻结／切 B／退 A／补偿条件见上述 Accepted ADR；治理采纳、实现交付和迁移启用分别准入，不据导航或 Build spec 获批切换默认路径。Story 1.2 的纯治理纳管不豁免后续实施。

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

- Capability Planning：`py -3 scripts/python/dev_cli.py plan-capabilities --stage prepare --run-id <id> --task-id <task-id>`
- MVG Planning：`py -3 scripts/python/dev_cli.py plan-mvg --stage prepare --run-id <id> --capabilities docs/planning/semantic-topology/capabilities.v1.json --manifest docs/testing/mvg/<manifest>.json --task-id <task-id>`
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

## Explicit formal B planning context boundary

The existing A workflows remain their own routes. For explicit B-route
operation inspection or published plan/revision context, use
`py -3 scripts/python/dev_cli.py b-route-adoption --stage inspect|read --operation-id <original-id> --context`.
See [adoption owner](docs/workflows/b-route-adoption.md) and
[native planning/status](docs/workflows/b-route-native-planning-status.md).
Formal no-Task 3B depends on its original qualified source/native/review owners;
this link does not require inventing a Task, authorize a model call, or activate
B by default. Completed-unit reuse/epoch/reopen is unsupported through this context observation entrypoint.
A published prefix and retained counts never establish global planning completion,
Task readiness or runtime acceptance. Keep original IDs/resume_ref and blocked
reasons; do not replace missing proof with a Knowledge summary or a fresh run.
