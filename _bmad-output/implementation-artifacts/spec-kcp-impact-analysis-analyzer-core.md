---
title: 'KCP Impact Analyzer Core'
type: 'feature'
created: '2026-09-04'
status: 'done'
review_loop_iteration: 0
baseline_commit: '33d400ae6eb4a2afc1fde4e79dd89ebb86dc69c1'
context:
  - '_bmad-output/specs/spec-kcp-impact-analysis/SPEC.md'
  - '_bmad-output/specs/spec-kcp-impact-analysis/impact-contract.md'
  - '_bmad-output/specs/spec-kcp-impact-analysis/rollout-and-verification.md'
  - '_bmad-output/architectures/architecture-kcp-impact-analysis/ARCHITECTURE-SPINE.md'
  - '_bmad-output/architectures/architecture-kcp-impact-analysis/architecture-details.md'
  - 'scripts/python/impact_analysis_index.py'
  - 'scripts/python/impact_analysis_handoff.py'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 当前仓库已有可验证的 revision-bound Impact Index，但还没有面向消费者的 Analyzer；因此无法把文件、C# 符号、测试和知识引用解析为可审查的影响证据，也无法生成契约要求的风险报告。

**Approach:** 在现有 Index Core 之上实现一个只读、确定性的 Analyzer Core：构建受限 C# 符号视图，提供严格 TargetResolver，扫描可静态证明的依赖与测试引用，执行风险规则，并输出带 index/KCP lineage 的 `impact-report.v1.json` 与 run manifest。

## Boundaries & Constraints

**Always:** 使用完整 Git revision、已验证的 Impact Index 和工作树 clean/hash 证据；路径、符号、关系、数组和 JSON 均稳定排序；成功报告必须带显式且通过 `impact_analysis_handoff.validate_handoff` 的 frozen-context/decision-set binding；失败必须 fail-closed 并返回稳定错误码；报告和 manifest 只能原子写入 `logs/ci/**`。

**Ask First:** 若需要扩大 `impact_analysis_config.v1.json` 的 source classes/scan roots、改变既有 report/handoff schema、修改 KCP authority/current/LKG/freeze，或需要引入 Roslyn、数据库、Godot editor/plugin，必须暂停请求批准。

**Never:** 不修改业务源、任务、ADR、Contract、Decision、冻结工件或 publication；不推断动态 dispatch、reflection、generated/editor-only state、外部依赖或完整 call graph；不实现 Godot Runtime Mapping、Knowledge Binding producer 或 Chapter 4/5/6 默认 enforce。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| RESOLVE_UNIQUE | 完整 revision、有效 index、唯一 file/class/method/event/contract target | 返回 canonical path、identity、source hash 和 resolution method | N/A |
| RESOLVE_AMBIGUOUS | 未限定 namespace 的重复符号或不完整 overload | 不选择候选，生成失败报告 | `ambiguous_target` |
| DEPENDENCY_SCAN | C# `using`、继承、接口实现、Contract/Event 声明与消费 | 生成去重且稳定排序的 typed edges | 无法证明的关系省略；解析错误为 `source_read_failure` |
| KCP_BINDING_MISMATCH | frozen context、report revision 或 hash 不一致 | 不生成成功报告 | `invalid_kcp_binding` 或 `revision_mismatch` |
| INDEX_UNAVAILABLE | 缺失、过期、碰撞或不匹配的 index | 不运行分析、不生成空成功集 | 传播 Index 稳定错误码 |

</frozen-after-approval>

## Code Map

- `scripts/python/impact_analysis_index.py:302-385` -- Git-tree snapshot、blob 读取、revision 与 worktree 证据；Analyzer 必须复用，不复制读取逻辑。
- `scripts/python/impact_analysis_index.py:573-727` -- source manifest、source kind 和 index schema 验证；符号/依赖输入只能来自 included manifest entries。
- `scripts/python/impact_analysis_index.py:1157-1365` -- index identity、exact reuse 与 immutable publication；Analyzer 只消费验证后的 artifact。
- `scripts/python/impact_analysis_handoff.py:56-158` -- frozen context、decision set、revision、index SHA 的共享 fail-closed 校验。
- `_bmad-output/specs/spec-kcp-impact-analysis/impact-contract.md:1-70` -- report envelope、固定 relation types、失败语义和输出目录契约。
- `_bmad-output/architectures/architecture-kcp-impact-analysis/architecture-details.md:102-170` -- TargetResolver 输入、canonical identity、别名和 ambiguity 规则。
- `_bmad-output/architectures/architecture-kcp-impact-analysis/architecture-details.md:172-245` -- Analyzer pipeline、edge canonicalization、risk 与 KCP 插入点。
- `scripts/python/tests/test_impact_analysis_index.py:335-410` -- fixture repository 与 deterministic artifact 测试模式，可复用构造临时 Git source universe。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/python/impact_analyzer.py` -- 实现 source/index preflight、受限 C# symbol extraction、TargetResolver、dependency/test edge collection、risk classification 和 canonical report model。
- [x] `scripts/python/analyze_impact.py` -- 实现 `--target`、`--revision`、`--trusted-ref`、`--index`、`--frozen-context`、`--output` CLI，生成隔离 run manifest 并原子发布成功/失败报告。
- [x] `scripts/python/tests/test_impact_analyzer.py` -- 覆盖唯一/歧义/缺失 target、C# symbol/dependency/test mapping、risk、KCP binding、stale index、determinism 和 failure codes。
- [x] `scripts/python/tests/fixtures/impact-analyzer/**` -- 提供最小 C#、task/ADR 和 handoff fixtures，证明 evidence path/hash 可回读。

**Acceptance Criteria:**
- Given 同一完整 revision、index 和 target，when 运行两次 Analyzer，then 除 run UUID 和时间外 report 内容 byte-equivalent，且所有 edge 按 canonical tuple 排序。
- Given唯一 file/class/interface/method/event/contract target，when 执行 resolver，then 返回唯一 canonical target；重复或不完整输入返回明确 failure，不猜测。
- Given可静态证明的 using、继承、接口、Contract/Event 消费和 `Refs:` 测试引用，when 分析，then 只生成固定 relation types，并携带 evidence path/anchor/hash。
- Given Contract/Event/save/Core、Service/System、UI-only 或证据不足目标，when 分类风险，then 分别得到规定的 `high`、`medium`、`low` 或 `unknown` 及匹配规则/原因。
- Given有效 frozen context 与 decision binding，when 生成成功报告，then 报告含 `knowledge_binding`、index identity、revision、risk 和 run manifest；binding 不匹配时不产生成功状态。
- Given缺失/过期 index、脏工作树、不可读 source、歧义 target 或 unsupported dynamic evidence，when 执行 CLI，then 返回稳定非零码且不发布伪成功空集。

## Spec Change Log

## Design Notes

Analyzer Core 只做文本级、可证明的 v1 解析：C# declaration/using/继承/接口/Contract/Event 依赖和测试 `Refs:`。TargetResolver 先 exact path，再 kind-scoped canonical symbol；资源、Scene、signal、node 等 Runtime target 留给后续切片。成功报告的 KCP binding 由调用方提供，Analyzer 只验证和复制，不检索或改变语义决策。

## Verification

**Commands:**
- `py -3 -m unittest scripts.python.tests.test_impact_analyzer` -- expected: focused analyzer tests pass.
- `py -3 scripts/python/analyze_impact.py --help` -- expected: CLI documents required revision/index/target and stable failures.
- `py -3 -m unittest scripts.python.tests.test_impact_analysis_index scripts.python.tests.test_impact_analysis_index_repository_smoke scripts.python.tests.test_impact_analyzer` -- expected: Index and Analyzer suites pass together.
- `git diff --check` -- expected: no whitespace errors and no generated artifacts outside `logs/ci/**`.

## Suggested Review Order

**Analyzer preflight and resolution**

- Reuses immutable index/blob evidence and validates aliases before analysis.
  [`impact_analyzer.py:270`](../../scripts/python/impact_analyzer.py#L270)

- Resolves exact paths and qualified symbols without heuristic guessing.
  [`impact_analyzer.py:184`](../../scripts/python/impact_analyzer.py#L184)

**Evidence collection and risk**

- Emits bounded, typed edges with endpoint and anchor validation.
  [`impact_analyzer.py:228`](../../scripts/python/impact_analyzer.py#L228)

- Collects deterministic source/test/runtime/document evidence and classifies risk.
  [`impact_analyzer.py:316`](../../scripts/python/impact_analyzer.py#L316)

- Validates the report envelope and required KCP binding before publication.
  [`impact_analyzer.py:404`](../../scripts/python/impact_analyzer.py#L404)

**CLI and immutable artifacts**

- Publishes isolated success or failure reports with run manifests atomically.
  [`analyze_impact.py:73`](../../scripts/python/analyze_impact.py#L73)

- Keeps handoff error codes aligned with Analyzer binding failures.
  [`impact_analysis_handoff.py:13`](../../scripts/python/impact_analysis_handoff.py#L13)

**Verification**

- Exercises resolution, risk, ambiguity, missing index, binding mismatch, and edge safety.
  [`test_impact_analyzer.py:8`](../../scripts/python/tests/test_impact_analyzer.py#L8)

- Supplies minimal C# fixtures for repeatable analyzer evidence.
  [`TestService.cs:1`](../../scripts/python/tests/fixtures/impact-analyzer/TestService.cs#L1)
