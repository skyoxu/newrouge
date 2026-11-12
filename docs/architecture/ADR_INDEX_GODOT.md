# ADR 索引 — Godot + C#（Accepted / Proposed / Superseded / Addenda）

本文件用于快速定位与 Godot + C# 模板相关的 ADR。

唯一口径：`docs/adr/`（以每份 ADR 的状态为准；本索引用于导航与对账）。

---

## 已采纳（Accepted，当前有效）

- ADR-0003: 可观测性与 Release Health（Sentry） — `docs/adr/ADR-0003-observability-release-health.md`
- ADR-0004: 事件总线与契约（CloudEvents 风格） — `docs/adr/ADR-0004-event-bus-and-contracts.md`
- ADR-0005: 质量门禁（Godot + C#） — `docs/adr/ADR-0005-quality-gates.md`
- ADR-0006: Godot 数据存储与持久化（SQLite + ConfigFile） — `docs/adr/ADR-0006-data-storage.md`
- ADR-0007: 端口与适配器（Ports & Adapters） — `docs/adr/ADR-0007-ports-adapters.md`
- ADR-0008: 部署与发布策略（Windows-only） — `docs/adr/ADR-0008-deployment-release.md`
- ADR-0010: 国际化策略（Godot） — `docs/adr/ADR-0010-internationalization.md`
- ADR-0011: 平台与 CI 策略（Windows-only） — `docs/adr/ADR-0011-windows-only-platform-and-ci.md`
- ADR-0012: PR 模板（静态）与审查信息最小集 — `docs/adr/ADR-0012-pr-template-conditional-rendering.md`
- ADR-0015: 性能预算与门禁（Godot 4.5 + C#） — `docs/adr/ADR-0015-performance-budgets-and-gates.md`
- ADR-0018: Godot Runtime and Distribution — `docs/adr/ADR-0018-godot-runtime-and-distribution.md`
- ADR-0019: Godot 4.5 安全基线（Windows Only） — `docs/adr/ADR-0019-godot-security-baseline.md`
- ADR-0020: Contracts 存放位置标准化（SSoT = `Game.Core/Contracts/**`） — `docs/adr/ADR-0020-contract-location-standardization.md`
- ADR-0023: Settings SSoT = ConfigFile (user://) — `docs/adr/ADR-0023-settings-ssot-configfile.md`
- ADR-0024: 模板谱系与命名口径（Template Lineage & Naming） — `docs/adr/ADR-0024-template-lineage-and-naming.md`
- ADR-0025: Godot 测试策略（xUnit + GdUnit4） — `docs/adr/ADR-0025-godot-test-strategy.md`
- ADR-0026: 事件发布失败策略（PublishAsync Failure Semantics） — `docs/adr/ADR-0026-event-publish-failure-strategy.md`
- ADR-0027: 所有权唯一写入口（Ownership Write Entry） — `docs/adr/ADR-0027-ownership-write-entry.md`
- ADR-0028: 事件用途分级（Gameplay vs UI vs Audit/Observability） — `docs/adr/ADR-0028-event-usage-tiering.md`
- ADR-0029: 错误处理口径（Exceptions vs Try*/Result vs Fail-Fast） — `docs/adr/ADR-0029-error-handling-policy.md`
- ADR-0030: Core 线程模型（Single-Thread Core + 明确跨线程边界） — `docs/adr/ADR-0030-core-threading-model.md`
- ADR-0032: Save/Resume Policy and Deterministic Outcomes — `docs/adr/ADR-0032-save-resume-determinism.md`
- ADR-0033: Card Identity and Forms（同一 card_id 的四形态） — `docs/adr/ADR-0033-card-identity-and-forms.md`
- ADR-0034: Security Profile Baseline for Host-Safe Delivery — `docs/adr/ADR-0034-security-profile-host-safe.md`
- ADR-0035: Repository Knowledge Control Plane — `docs/adr/ADR-0035-repository-knowledge-control-plane.md`
- ADR-0038: Semantic Delivery Topology — `docs/adr/ADR-0038-semantic-delivery-topology.md`
- ADR-0038: MVG Candidate Admission Before Selection — `docs/adr/ADR-0038-mvg-candidate-admission.md`
- ADR-0039: MVG 完成项恢复与独立候选生命周期 — `docs/adr/ADR-0039-mvg-completed-capability-recovery.md`
- ADR-0040: B 路线阶段、记录权威与迁移启用治理 — [docs/adr/ADR-0040-b-route-stages-authority-and-activation.md](../adr/ADR-0040-b-route-stages-authority-and-activation.md)。治理定义已采纳，当前未启用；后续实现交付和迁移启用另有条件，现行 A 入口继续有效。

- ADR-0041: B 路线审核修复的宿主资源与元数据恢复边界 — [ADR-0041](../adr/ADR-0041-b-route-review-hardening-resource-and-metadata-boundaries.md)。Accepted 宿主政策，R25 已有定向工程证据；正式 Story 审核另行关闭，默认 B 未激活，原模型预算与历史 producer 资格不变。
- ADR-0042: Capability/MVG 共用分段协议与有界无损传输 — [ADR-0042](../adr/ADR-0042-shared-segmented-planning-protocol.md)。Accepted 技术合同；opt-in 实现交付、真实资格和默认启用分别准入，不据本索引授予正式采纳或默认 B 启用。

---

## 待采纳（Proposed，未冻结）

- ADR-0043: B 路线完整资源管道预检 — [ADR-0043](../adr/ADR-0043-b-route-resource-pipeline-preallocation.md)。回环2实现及离线工程记录已保存；正式复审与启用条件另计。
- ADR-0044: B 路线元数据发布与前缀历史 — [ADR-0044](../adr/ADR-0044-b-route-metadata-journal-publication.md)。回环2实现及离线工程记录已保存；正式复审与启用条件另计。
- ADR-0045: B 路线宿主取消与清理诊断 — [ADR-0045](../adr/ADR-0045-b-route-host-cancellation-diagnostics.md)。回环2实现及离线工程记录已保存；正式复审与启用条件另计。
- ADR-0046: B 路线精确宿主故障源边界 — [ADR-0046](../adr/ADR-0046-b-route-host-fault-source-boundaries.md)。回环2实现及离线工程记录已保存；正式复审与启用条件另计。
- ADR-0047: B 路线合法部分修复、路径与CI — [ADR-0047](../adr/ADR-0047-b-route-legacy-progress-paths-and-ci.md)。回环2实现及离线工程记录已保存；正式复审与启用条件另计。
- ADR-0048: B 路线稳定问题账户及完整资源边界 — [ADR-0048](../adr/ADR-0048-b-route-stable-issues-and-complete-resource-boundaries.md)。回环3必要定向检查已通过；正式审核及启用条件另计。

- ADR-0037: Bounded MVG Integration Evidence — `docs/adr/ADR-0037-mvg-integration-evidence.md`

说明：这些 ADR 仍在评审中，不应作为“最终口径”被引用为硬规则。

- ADR-0017: Quality Intelligence Dashboard and Governance — `docs/adr/ADR-0017-quality-intelligence-dashboard-and-governance.md`
- ADR-0021: C# Domain Layer Architecture — `docs/adr/ADR-0021-csharp-domain-layer-architecture.md`
- ADR-0022: Godot Signal System and Contracts — `docs/adr/ADR-0022-godot-signal-system-and-contracts.md`
- ADR-0031: 构建可复现性与版本锁定（Godot 4.5.1 + NuGet Lock） — `docs/adr/ADR-0031-build-reproducibility-and-version-pinning.md`
- ADR-0036: Local Project Health Investigation Boundary — `docs/adr/ADR-0036-project-health-investigation.md`

---

## 已替代（Superseded，历史参考）

- ADR-0001: 技术栈与版本策略 — `docs/adr/ADR-0001-tech-stack.md`
- ADR-0002: LegacyDesktopShell 安全基线 — `docs/adr/ADR-0002-legacy-desktop-shell-security-baseline.md`
- ADR-0009: 跨平台适配策略（已被 Windows-only 平台策略替代） — `docs/adr/ADR-0009-cross-platform.md`

---

## 元数据异常（待修复）

说明：以下 ADR 的状态字段未被标准格式识别，建议统一其头部元数据（否则索引/脚本会误判）。

- ADR-0016: API 契约与 OpenAPI 基线 — `docs/adr/ADR-0016-api-contracts-openapi.md`

---

## 附录（Addenda）

- ADR-0005 Addendum: Godot+C# 质量门禁补充 — `docs/adr/addenda/ADR-0005-godot-quality-gates-addendum.md`
- ADR-0006 Addendum: Godot 数据存储补充 — `docs/adr/addenda/ADR-0006-godot-data-storage-addendum.md`

- ADR-0049: B 路线当前必需输入与历史调试附件的角色边界 — [docs/adr/ADR-0049-b-route-reference-roles.md](../adr/ADR-0049-b-route-reference-roles.md)。Accepted：v2 保护引用角色边界，27 项检查及真实只读采集／归档复核已通过；默认 A、正式采纳及迁移启用继续遵守原门禁。
- ADR-0050: B 路线补偿审阅的版本化语义材料与原 owner 证明 — [docs/adr/ADR-0050-b-route-compensation-review-materials.md](../adr/ADR-0050-b-route-compensation-review-materials.md)。Accepted 技术决定：完整 host 原像与历史语义 DAG、新辅助 proof/presentation 合同、同 policy v1 精确重放及跨 policy 严格拒绝；新源码实际验证待 Root 执行，不代表正式采纳或启用通过。


## Proposed implementation follow-up; no acceptance inferred

- ADR-0053: Historical adoption-proof-v3 original-owner authentication and explicit public history — [ADR-0053](../adr/ADR-0053-b-route-historical-v3-original-owner.md). Proposed; R57 source-integrated route with null authority default, legacy routes retained, and genuine proof3/public-history/compensation positives not yet executed. No formal Story acceptance or default-B activation.


## Accepted supplementary DATA contract; no financial activation

- ADR-0054: Segmented financial-prefix DATA validation - [ADR-0054](../adr/ADR-0054-segmented-financial-prefix-data.md). Accepted for supplied-byte consistency only; no actual allocation, grant, paid dispatch, native qualification or default-B activation.

- ADR-0055: B 路线固定工作政策的实测校准 — [ADR-0055](../adr/ADR-0055-b-route-fixed-work-policy-calibration.md)。Accepted 本地技术政策：依据完整 DATA 组件计量将当前同账工作界显式定为170M／resource-pipeline.v4；只局部 supersede 原100M，不改变其他资源、模型预算或原生验收门。

- ADR-0056: Cloud published-history compensation - [ADR-0056](../adr/ADR-0056-b-route-published-history-compensation.md). Accepted explicit published-only data/protocol verification with new review profile; no original-owner execution claim, budget increase or Story acceptance.

- ADR-0060: One formal compensation review repair - [ADR-0060](../adr/ADR-0060-one-time-compensation-review-repair.md). Narrow versioned continuation after a completed refusal; preserve original2, allow one explicit additional subscription review, cumulative3; no refund, automatic retry, source re-signing or acceptance inferred.
