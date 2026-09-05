---
title: 'KCP Impact Runtime Mapping'
type: 'feature'
created: '2026-09-05'
status: 'draft'
review_loop_iteration: 0
baseline_commit: 'faa04e7ebcedde15d28951820a09b8061bc56d71'
context:
  - '_bmad-output/architectures/architecture-kcp-impact-analysis/architecture-details.md'
  - 'execution-plans/2026-09-05-kcp-impact-analysis-completion.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** CORE-01 尚无生产实现；当前 Analyzer 不产生 Runtime 关系，validator 拒绝非空 runtime_refs。

**Approach:** 从已验证索引源码解析 Godot 静态绑定，接入 resolver、分析与报告校验，覆盖 CAP-1/2/3 的 Runtime 子集。

## Boundaries & Constraints

**Always:** 遵守 ADR-0035、ADR-0022；证据带路径、行号、SHA，方向为 owner→bound target；使用既有 binds/报告字段、稳定排序及退出码。仅允许配置声明的来源；.gd 只作有哈希的脚本目标，不解析或执行。

**Ask First:** 改报告 schema、关系端点矩阵、风险策略或引入依赖。

**Never:** 推断动态调用、反射或完整运行时流程；写 KCP/generated state；实现 Knowledge producer；修改或提交 docs/121.txt；自动 push。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| OWNER | scene/.tres 目标 | 返回本文件实际 node/script/resource/connection 绑定及直接入边；声明但未使用的资源不算绑定 | 非法所选文件失败 |
| CODE | C# 目标及已有可验证影响路径 | 关联直接绑定这些脚本的 owner；保留代码边与绑定边，不伪造 Scene→Event 消费 | 无绑定可为空 |
| IDENTITY | scene 路径内 node/signal 身份 | 唯一精确解析并带源哈希；scene/resource 须匹配来源类型 | missing/ambiguous/unsupported |
| INVALID | 重复 ID、悬空资源/节点、畸形相关文件 | 诊断失败，不能空成功 | source_read_failure |
| UNSUPPORTED | 相关绑定仅 UID、动态表达式或排除来源 | 不猜测关系；二进制 .res 仅作哈希目标 | unsupported_target |
| REPORT | 重复、漏项或伪造 runtime_refs | runtime_refs 必须精确等于规范 binds 投影 | invalid_manifest |

</frozen-after-approval>

## Code Map

- `scripts/python/impact_analyzer.py`：TargetResolver、analyze 排序前插入点、_edge/_sort_edges、validate_report_document；复用已验证 sources/hashes。
- `scripts/python/impact_analysis_config.v1.json`：已有 .tscn/.tres/.res；需补 .gd 哈希来源和 analyzer/新模块 identity_files。
- `scripts/python/tests/test_impact_analyzer.py`：analyzer_for/binding fixtures；保留无 Runtime 输入回归。
- `Game.Godot/Examples/Components/PrimaryButton.tscn`：真实 Script 绑定；`Game.Godot/Themes/default_theme.tres`：真实 SubResource 引用。

## Tasks & Acceptance

**Execution:**
- [ ] `scripts/python/tests/test_impact_runtime.py`：先覆盖矩阵；字符串/注释伪引用、同名不同场景、稳定排序和哈希负例。
- [ ] `scripts/python/impact_runtime.py`：有界文本解析、局部对象身份、引用筛选与错误归属；不执行源码。
- [ ] `scripts/python/impact_analyzer.py`：类型正确的 resolver、Runtime 拼接、严格投影校验；knowledge_refs 继续受现阶段约束。
- [ ] `scripts/python/impact_analysis_config.v1.json`：补来源和工具身份、推进配置/Analyzer 实现版本；旧缺少绑定的索引明确失效，不改 index schema。
- [ ] `scripts/python/tests/test_analyze_impact_cli.py`、`scripts/python/tests/test_impact_analysis_index.py`：更新工具复制 fixtures；正式 builder→CLI 验证 Runtime 及失败工件。
- [ ] `scripts/python/run_gate_bundle.py`：注册 Runtime 测试并更新注册断言；执行计划按证据登记 CORE-01 范围。

**Acceptance Criteria:**
- Given Event→C# consumer 与显式场景绑定，when 分析 Event，then 输出独立且可追溯的代码边和 Runtime 边，不将绑定当作业务调用证明。
- Given 同一 revision/target，when 重复分析，then 除时间外证据一致，runtime_refs 投影精确。
- Given 真实 PrimaryButton 与 Theme 源文件的临时 Git fixture，when 正式 builder/CLI 执行，then 源码哈希、绑定锚点和报告/manifest 哈希均可重读验证。

## Spec Change Log

## Design Notes

Node 身份为 `scene-path::node:<relative-node-path>`，根用 `.`；signal 为 `scene-path::signal:<node-path>:<signal-name>`，仅解析显式 connection 中出现的信号。连接表示接收 node→发射 signal；method 保留在行号来源中，不宣称方法真实可调用。SubResource 为 `file-path::subresource:<id>`；PackedScene 引用的终点 kind 为 resource。

候选文件只取目标文件及声明了目标/已验证 C# 影响脚本路径的直接 owner，不递归展开场景实例或资源图。所选文件完整验证局部声明和使用；无关文件错误不污染当前报告。解析须区分字符串、注释、section 和实际引用，拒绝相关无法确定的语法。res:// 按仓库 project.godot 根转换；不得将未索引资源解释为无影响。

## Verification

- `py -3 -m unittest scripts.python.tests.test_impact_runtime scripts.python.tests.test_impact_analyzer scripts.python.tests.test_analyze_impact_cli -v`
- `py -3 -m unittest scripts.python.tests.test_impact_analysis_index scripts.python.tests.test_impact_analysis_index_repository_smoke`
- `py -3 scripts/python/check_gate_bundle_consistency.py`
- `py -3 scripts/python/validate_recovery_docs.py --dir all`
- `git diff --check`

证据写入 `logs/ci/2026-09-05/impact-runtime-mapping/`；测试输出先内存收集再归档，smoke 期间暂停其他写入。真实 KCP freeze 集成与 CAP 总验收仍开放。
