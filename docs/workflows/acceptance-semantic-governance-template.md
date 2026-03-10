# Acceptance Semantic/Governance Template v1

## 目的
将任务验收条目拆分为两类，避免语义门禁被流程条目污染：

- `semantic`：任务业务语义本体（功能行为、失败语义、契约模型）
- `governance`：流程与回链治理（ADR、checklist、marker、traceability、result-json refs）

## 适用范围
- `tasks_back.json` / `tasks_gameplay.json` 的 `acceptance`
- `sc-llm-align-acceptance-semantics`
- `sc-semantic-gate-all`
- `sc-llm-check-subtasks-coverage`

## 编写规则
1. `semantic` 条目必须可证伪：缺字段、错误状态、拒绝路径、未变化约束等可触发失败。
2. `semantic` 条目只描述任务本体，不描述 ADR/checklist/marker/result-json 解析要求。
3. `governance` 条目只做治理，不承载业务语义。
4. `Refs:` 继续保留在原条目末尾，不改变格式。

## 最小模板
### Semantic acceptance（建议）
- 必须定义/实现 `<核心对象或行为>`，满足 `<关键字段或行为>`；缺失任一项即失败。 Refs: `<test path>`
- 当 `<负路径条件>` 触发时，系统必须 `<拒绝/不推进/返回错误>`；否则失败。 Refs: `<test path>`
- `<契约/模型>` 的关键结构必须与任务描述一致；不一致即失败。 Refs: `<test path>`

### Governance acceptance（建议）
- ADR 回链完整且可解析。 Refs: `<test path or log path>`
- Overlay/Test-Refs 路径可追踪。 Refs: `<test path or log path>`
- 审计 marker 存在且可解析。 Refs: `<test path>`

## Task30 示例（精简）
### Semantic
- RelicDefinition 缺少 `relic_id/name_key/description_key/tags` 任一键时必须失败。 Refs: `Game.Core.Tests/Tasks/Task0030AcceptanceTests.cs`
- RelicInstance 缺少 `instance_id/modifiers` 任一键时必须失败。 Refs: `Game.Core.Tests/Tasks/Task0030AcceptanceTests.cs`

### Governance
- ADR 映射与 checklist 对齐。 Refs: `Game.Core.Tests/Tasks/Task0030AcceptanceTests.cs`
- Overlay 的 Test-Refs 包含任务测试路径。 Refs: `Game.Core.Tests/Tasks/Task0030AcceptanceTests.cs`

