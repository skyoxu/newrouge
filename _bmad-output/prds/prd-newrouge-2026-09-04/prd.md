---
title: Knowledge Control Plane Impact Analysis
status: final
created: 2026-09-04
updated: 2026-09-04
requirement_id: KCP-IMPACT-001
project: newrouge
source: docs/code.txt
knowledge_baseline: 4053008
---

# Knowledge Control Plane Impact Analysis

## 1. Overview

Knowledge Control Plane Impact Analysis 是 `newrouge` 知识控制面的下一层平台能力。它为 AI 开发者和 Review consumer 提供变更影响证据，回答“修改这个目标会影响什么”，但不替代现有 authority、semantic decision 或 freeze 机制。

| Field | Value |
| --- | --- |
| Requirement ID | KCP-IMPACT-001 |
| Type | Platform Capability |
| Priority | P1 |
| Scope | [ASSUMPTION] Repository-local Windows Godot 4.5.1 + C# project |
| Knowledge baseline | `4053008` (`Knowledge Control Plane Migration`) |

## 2. Background And Problem

当前 Knowledge Control Plane 已覆盖 Task、Acceptance、ADR、Contract、Decision、Freeze，并能回答变更的意图、约束和语义边界。根据 `docs/knowledge/migration-final-audit.md`，Chapter 4、5、6 和 Review 的候选上下文已经完成显式语义决策与 hash-bound freeze。

但是，开发者在修改代码对象时还缺少影响面证据。例如修改 `Game.Core/Contracts/RewardOfferPresentedEvent.cs` 时，现有知识层可以定位 ADR、任务和契约，却不能可靠地列出消费该 Event 的代码、受影响测试、Godot Scene、Runtime flow，以及关联的知识引用。

没有这层证据，AI 可能遗漏测试或运行时连接，也可能把“被调用”误读成“架构权威”。

## 3. Goal

建立轻量、可审计、仓库内运行的 Impact Analysis Layer，使 AI 在编码和 Review 前能够获得以下变更影响上下文：

`Change Target -> Affected Surface -> Code / Tests / Runtime / Knowledge`

首个版本必须输出可追溯的影响证据和风险等级，支持从文件、符号、契约、Scene 或资源开始分析，并与 Knowledge Control Plane 做引用绑定。

## 4. Users And Use Cases

### UC-1 Before Coding

AI 开发者指定一个目标（例如 Event、接口或 Scene），读取影响报告，确认需要重新检查的消费者、测试、Runtime 引用和知识约束，然后再开始编码。

### UC-2 Before Review

Review consumer 读取绑定到变更目标的影响报告，扩大检查范围并识别风险；报告只能提供 evidence，不能改变 review authority、已冻结上下文或验收结论。

## 5. Scope And Boundaries

### 5.1 In Scope

- 文件、class、interface、method、event、contract、scene、resource 的目标解析。
- C# 直接引用、`using`、继承、接口实现和契约依赖的影响发现。
- 测试到生产代码的影响映射。
- `.tscn`、Node、signal、resource 与 C# 目标之间的有限 Runtime 映射。
- 通过现有 Knowledge Control Plane 绑定 ADR、Task、Decision 等知识引用。
- 基于变更目标类型的 deterministic 风险分类。
- 生成仓库内 JSON 影响报告和审计证据。

### 5.2 Non-Goals

- 不实现完整 CodeGraph、AST 数据库、class graph、method graph 或 call graph。
- 不替代 Knowledge Control Plane，也不决定 Authority、Architecture、Design 或 Acceptance。
- 不进行 autonomous refactoring，不自动修改代码、Scene 或文档。
- 不引入 SaaS workspace isolation、tenant governance、phase service 或 sandbox governance。
- 不把生成的索引、报告或 catalog 变成 repository authority。

## 6. Functional Requirements

### FR-001 Target Resolution

系统必须接受以下目标类型：`file`、`class`、`interface`、`method`、`event`、`contract`、`scene`、`resource`。符号目标必须解析到仓库中的 canonical path；无法唯一解析时必须返回可诊断的失败，而不是猜测。

### FR-002 Symbol Impact Detection

系统必须发现目标的直接引用、`using` 依赖、继承关系、接口实现关系和契约依赖，并将结果区分为 affected files 与 affected symbols。引用关系是影响证据，不是 authority 结论。

### FR-003 Test Impact Mapping

系统必须将受影响的生产代码或契约映射到相关测试文件、测试符号和可识别的 Task acceptance tests。无法建立映射时必须明确报告缺口。

### FR-004 Runtime Impact Mapping

系统必须支持有限的 Godot Runtime 映射：C# code、`.tscn`、Node、signal、resource 之间的可识别引用。Runtime 证据必须包含来源路径和关系类型，不能声称发现未验证的调用图。

### FR-005 Knowledge Binding

系统必须把影响目标绑定到现有 Knowledge Control Plane 可定位的知识引用，至少支持 ADR、Task、Contract 和 Decision 的类型与稳定 ID。每条引用必须保留 source path 或稳定定位信息。

### FR-006 Risk Classification

系统必须输出 deterministic `risk_level`：

- `high`：Contract、Event、save format、Core domain 目标。
- `medium`：Service、System 目标。
- `low`：仅 UI 目标。
- `unknown`：目标无法可靠归类或证据不足，必须要求人工判断。

分类不能覆盖更严格的 ADR、Task、Decision 或 Freeze 要求。

### FR-007 Report Contract

系统必须生成版本化 JSON 报告，包含 `schema_version`、`status`、`target`、`affected_files`、`affected_symbols`、`tests`、`runtime_refs`、`knowledge_refs`、`risk_level` 和失败时的 `failure_reason`。报告必须包含生成时间、分析输入摘要和可复现的 repository revision 绑定信息。

### FR-008 Deterministic And Fail-Closed Behavior

相同 repository revision、目标和分析配置必须产生稳定排序和等价结果。索引缺失、目标歧义、源文件读取失败或 revision 不一致时，系统必须返回可诊断的非成功状态，不得静默降级为不完整的“无影响”。

### FR-009 Workflow Integration

编码前流程必须支持：`Task -> Knowledge Freeze -> Impact Analysis -> Coding`。

Review 前流程必须支持：`Review Context Freeze + Impact Report -> Review`。

Impact Analysis 不得在没有显式新决策的情况下扩展已冻结 context，也不得改变 publication、current/LKG、Locator 或 freeze 的状态。

### FR-010 Evidence Boundary

默认产物写入 `logs/ci/impact-analysis/`，至少包含 `impact-report.v1.json`。报告、索引和扫描结果均属于 derived evidence；它们不能覆盖 `AGENTS.md`、Taskmaster、PRD、ADR、Base、Overlay、Contracts 或 Decision 的 authority。

## 7. Non-Functional Requirements

### NFR-001 Auditability

报告必须能够追溯目标、仓库 revision、输入索引版本、知识引用和风险分类依据；失败也必须留下英文诊断文本和日志路径。

### NFR-002 Repository Safety

分析器只读仓库源文件和已声明的生成索引，不得自动写入业务源、修改 authority 文档或执行重构。

### NFR-003 Reproducibility

在同一 commit 和相同配置下，报告结构、排序和风险结果必须可复现；所有路径必须使用仓库相对路径。

### NFR-004 Compatibility

首版必须适配 Windows-only、Godot 4.5.1、C#/.NET 8 仓库约束，复用现有 Python 入口和 Knowledge Control Plane 合约，不引入不必要的第三方依赖。

### NFR-005 Performance

首版针对单目标、局部依赖和有限 Runtime 映射优化；不以全仓库 AST 或完整调用图为前置条件。性能门槛沿用现有 ADR/Base/门禁口径，不在本 PRD 重复阈值正文。

## 8. Output Contract

报告路径：`logs/ci/impact-analysis/impact-report.v1.json`

最小结构：

```json
{
  "schema_version": "newrouge.impact-analysis.v1",
  "repository_revision": "<git commit>",
  "status": "ok",
  "target": {},
  "affected_files": [],
  "affected_symbols": [],
  "tests": [],
  "runtime_refs": [],
  "knowledge_refs": [],
  "risk_level": "high",
  "failure_reason": null
}
```

字段的详细来源、关系枚举和兼容策略属于实现合约，见 `addendum.md`；定稿前应转化为独立 schema/ADR（如确实改变现有口径）。

## 9. Acceptance Criteria

### AC-001 Contract/Event Impact

给定 `RewardOfferPresentedEvent` 或其 canonical contract path，系统输出至少一条可验证的 code consumer、相关 tests 和 ADR/Task knowledge reference；每条结果带 source path 或稳定 ID。

### AC-002 High-Risk Classification

给定 Contract、Event、save format 或 Core domain 目标，报告输出 `risk_level = high`；分类理由可审计，且不改变现有 authority。

### AC-003 Runtime Evidence

给定存在明确连接的 `RewardPanel.tscn` 与目标 Event，报告输出包含 Scene、Node 或 signal 的 runtime reference；无法确认的关系不得伪造为已发现。

### AC-004 Review Boundary

Review consumer 能读取 impact report，但报告不能改变 review authority、semantic decisions、freeze、publication、current/LKG 或 Locator 状态。

### AC-005 Determinism And Failure

在同一 commit 和配置下重复分析得到稳定等价结果；目标歧义、缺失索引或 revision 不一致时返回明确失败状态，并写入 `logs/ci/impact-analysis/`。

### AC-006 Derived-Evidence Boundary

报告、索引和扫描结果不会被 Knowledge Control Plane 当作新的 authority；现有直接源读取和 fail-closed fallback 继续有效。

## 10. Success Metrics And Counter-Metrics

Success：在编码或 Review 前，AI 能够从一个目标得到“谁依赖它、哪些测试受影响、哪些 Runtime 引用存在、哪些 ADR/Task 约束它、风险是什么”的可审计答案。

Counter-metrics：

- 误报的消费者、测试或 Runtime 引用增加 Review 噪声。
- 分析器把影响关系误读为 authority，造成错误的设计或验收决策。
- 生成索引过期而未被检测，导致遗漏影响面。
- 分析耗时或全仓扫描成本阻碍正常编码流程。

## 11. Delivery And Rollout

首版按 addendum 中的四个阶段交付：Symbol Index、Dependency Scanner、Runtime Mapping、Knowledge Binding。每阶段都必须先有针对性测试和失败证据，再扩大范围。

首轮采用 observe-only / shadow 方式，与现有直接 source routing 并行。只有在报告稳定、revision 绑定和失败关闭行为得到验证后，才讨论将 Impact Analysis 作为 Chapter 4/5/6 或 Review 的强制门禁；本 PRD 不授权接入 `--enforce`。

## 12. Authority And References

- `docs/adr/ADR-0035-repository-knowledge-control-plane.md`：Knowledge Control Plane authority、derived boundary、Locator 与 freeze 约束。
- `docs/knowledge/migration-final-audit.md`：迁移后的 publication、freeze 和 consumer pilot 现状。
- `docs/workflows/knowledge-context-shadow.md`：shadow candidate 与 fallback 边界。
- `docs/workflows/knowledge-context-freeze.md`：source reread、semantic decision、hash-bound freeze 合约。
- `AGENTS.md`：仓库目录、Windows、Godot/C#、测试和日志规则。
- `docs/prd/PRD-NEWROUGE-GAME-0001.md`：游戏领域的产品和 Runtime authority。
- `Game.Core/Contracts/**`：契约 authority。

## 13. Open Questions

- 首版是否需要独立的 `impact-report.v1.schema.json`，还是先由脚本内部校验后再提取 schema？Owner：平台维护者；在 Phase 1 完成前决定。
- Runtime 映射是否需要覆盖资源间间接引用？Owner：架构维护者；以真实 pilot 证据决定，不默认扩大到完整图。
- 是否将报告接入 Review sidecar？Owner：Review workflow 维护者；必须另行更新 sidecar contract 和测试，本 PRD 当前不做。

