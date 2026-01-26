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
- ADR-0033: Card Identity and Forms（同一 card_id 的四形态） — `docs/adr/ADR-0033-card-identity-and-forms.md`

---

## 待采纳（Proposed，未冻结）

说明：这些 ADR 仍在评审中，不应作为“最终口径”被引用为硬规则。

- ADR-0017: Quality Intelligence Dashboard and Governance — `docs/adr/ADR-0017-quality-intelligence-dashboard-and-governance.md`
- ADR-0021: C# Domain Layer Architecture — `docs/adr/ADR-0021-csharp-domain-layer-architecture.md`
- ADR-0022: Godot Signal System and Contracts — `docs/adr/ADR-0022-godot-signal-system-and-contracts.md`
- ADR-0031: 构建可复现性与版本锁定（Godot 4.5.1 + NuGet Lock） — `docs/adr/ADR-0031-build-reproducibility-and-version-pinning.md`
- ADR-0032: Save/Resume Policy and Deterministic Outcomes — `docs/adr/ADR-0032-save-resume-determinism.md`

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
