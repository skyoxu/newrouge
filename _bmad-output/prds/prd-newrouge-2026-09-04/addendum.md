# Addendum: Knowledge Control Plane Impact Analysis

## 1. Source And Decision Notes

本附录承接 `docs/code.txt` 的实现提示，但不取代 PRD 或仓库 authority。当前知识控制面基线为 commit `4053008`，其 accepted ADR 为 `docs/adr/ADR-0035-repository-knowledge-control-plane.md`。`knowledge/**` 中的 catalog、snapshot、projection、publication 和 context bundle 都是 derived state，不能成为影响分析的唯一事实源。

## 2. Proposed Phased Shape

### Phase 1: Symbol Index

建立可复现的轻量 symbol index，首版覆盖 C# 的 class、interface、method、event 和 contract。索引条目至少包含 repository-relative path、symbol kind、qualified name、source revision 和 source hash。索引生成失败必须阻止成功报告。

### Phase 2: Dependency Scanner

扫描 `using`、显式引用、继承、接口实现和契约依赖，生成关系类型明确的 evidence。只报告静态可验证关系，不声称完整 call graph。结果排序使用稳定的 path、symbol kind 和 symbol name 顺序。

### Phase 3: Runtime Mapping

对 `.tscn` 的 Node、signal、resource 和脚本绑定做有限解析，并将可验证的 C# 到 Godot 连接加入 `runtime_refs`。解析器应对未知 Godot 语法保守失败，不以启发式名称匹配代替证据。

### Phase 4: Knowledge Binding

使用现有 Locator/publication 只定位候选 knowledge refs，再回读 ADR、Task、Contract、Decision 等源文件并绑定 source hash。Impact 关系不能自动赋予 authority，也不能自动满足 required context class。

## 3. Report And Revision Binding

`impact-report.v1.json` 应绑定：

- `schema_version`
- `repository_revision`
- `analysis_config_revision`
- `target`（输入形式、canonical path、symbol identity）
- `affected_files` 与 `affected_symbols`
- `tests`
- `runtime_refs`
- `knowledge_refs`（type、id/path、source hash）
- `risk_level` 与 `risk_reasons`
- `status`、`failure_reason` 和生成时间

这里的 `repository_revision` 是证据绑定，不是发布 authority。若工作区 dirty 或索引 revision 不匹配，建议返回 `stale_or_untrusted`，并要求直接源读取。

## 4. Risk Classification Notes

风险分类是变更影响的初筛，不是安全或发布门禁。若一个目标跨越多个类别，使用最高风险；无法分类时使用 `unknown`，不能默认为 `low`。ADR、Task、Decision、Freeze 的更严格约束始终优先。

## 5. Test Strategy

- Unit：目标解析、符号索引、关系扫描、稳定排序、风险分类、schema 校验。
- Fixture：Event/Contract、Service、Test、Scene、Node、signal 的最小真实仓库样本。
- Regression：同一 commit 重复运行的 canonical JSON 等价性。
- Failure：目标歧义、缺失索引、损坏 `.tscn`、source hash 不匹配、dirty/revision mismatch。
- Integration：与 `prepare_knowledge_context.py` 和现有 publication/freeze 读取边界验证，但不把 impact report 注入现有 review sidecar。

## 6. Deferred Decisions

- 是否构建跨方法调用图：暂缓，除非真实 pilot 证明静态直接关系不足以支持高风险目标。
- 是否引入 AST 或数据库依赖：暂缓，先复用仓库现有 Python 与文件格式能力。
- 是否在 Chapter 4/5/6 默认流程启用强制门禁：暂缓，先完成 shadow -> semantic decision -> freeze pilot。
- 是否支持跨仓库影响：不在本需求范围内。

