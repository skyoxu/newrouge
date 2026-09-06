---
title: 'KCP Impact Analyzer Semantic Correctness'
type: 'feature'
created: '2026-09-05'
status: 'done'
review_loop_iteration: 1
baseline_commit: '1fda7fd910e006d0b87c4f0381e4cf477d0a1ce2'
context:
  - 'docs/121.txt'
  - '_bmad-output/specs/spec-kcp-impact-analysis/SPEC.md'
  - '_bmad-output/specs/spec-kcp-impact-analysis/impact-contract.md'
  - '_bmad-output/architectures/architecture-kcp-impact-analysis/architecture-details.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Analyzer Core 已有 C# resolver、依赖扫描、风险分类和 report model，但 method identity、alias 信任、code/test evidence、风险规则及 schema validation 仍会误报或漏报，尚不能可靠证明 CAP-1、CAP-2、CAP-3 的 C# 子集和 AC-002。

**Approach:** 不扩展 Runtime/Knowledge 范围，将 Analyzer 收敛为受限、确定性、fail-closed 的 C# impact engine：唯一解析目标，生成可回读 typed evidence，按最高适用规则分类风险，并完整校验成功 report。

## Boundaries & Constraints

**Always:** 复用 trusted Git blob、Impact Index 和稳定错误码；exact identity 优先于 alias；alias 仅限 event/contract、kind-scoped 且落在 `Game.Core/Contracts/**`；method identity 必须含 namespace/type/name/arity/完整参数；edge 必须校验 endpoint、anchor、SHA、去重与顺序；Contract/Event/save/Core=high，Service/System=medium，仅可证明 UI-only=low，否则 unknown；遵循 ADR-0004、ADR-0005、ADR-0020。

**Ask First:** 若需改变 report/handoff 契约、relation matrix、KCP authority/freeze/current/LKG/Locator、sidecar schema，或引入 Roslyn/数据库/Godot plugin，暂停请求批准。

**Never:** 不实现 Node/signal/resource/connection Runtime Mapping 或 KCP Knowledge Binding producer；不把 `.tscn` basename、任意文档字符串、注释或字符串字面量当 evidence；不修改业务源或 authority；不推断 dynamic dispatch、reflection、generated state 或完整 call graph。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| STATIC_ANALYSIS | 唯一 C# target 与可证明依赖/测试 | canonical target、typed edges、risk、valid report | N/A |
| UNSAFE_INPUT | 不完整 overload、重名、非法 alias、malformed report | 不猜测、不接受成功工件 | 稳定 target/manifest/binding 错误码 |

</frozen-after-approval>

## Code Map

- `scripts/python/impact_analyzer.py:101-228` -- `SymbolIndex`/`TargetResolver`；修复参数规范化、scope、exact-before-alias 和 Contracts 限制。
- `scripts/python/impact_analyzer.py:231-386` -- typed edges、C# dependency/test evidence、risk；移除 Runtime/Knowledge 误报。
- `scripts/python/impact_analyzer.py:273-317` -- index/source/alias preflight；alias 改读同一 `GitTreeSnapshot` blob。
- `scripts/python/impact_analyzer.py:420-490` -- report/binding validation；所有 malformed shape 必须稳定拒绝。
- `scripts/python/tests/test_impact_analyzer.py` -- 当前 7 个窄测试；扩展 resolver/evidence/risk/report/determinism 覆盖。
- `_bmad-output/implementation-artifacts/deferred-work.md` -- CLI harness、Runtime、Knowledge、最终 Acceptance 已另行登记。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/python/impact_analyzer.py` -- 实现词法安全的受限 symbol/method normalization、exact/alias resolver 和 trusted alias；不支持构造显式失败。
- [x] `scripts/python/impact_analyzer.py` -- 生成可证明的 references、using、inherits、implements、Event/Contract consumes、unit/test-symbol 与分行 `Refs:` test edges；删除伪 Runtime/Knowledge evidence。
- [x] `scripts/python/impact_analyzer.py` -- 实现最高风险优先规则，并完整校验 report target、arrays、edges、hash、lineage、risk 与 binding。
- [x] `scripts/python/tests/test_impact_analyzer.py` 和 fixtures -- 覆盖 overload/alias/歧义、注释误报、dependency/test mapping、风险表、malformed report 和 deterministic projection。
- [x] `_bmad-output/implementation-artifacts/spec-kcp-impact-analysis-analyzer-core.md` -- 让既有完成声明与真实 semantic test evidence 对齐，不改变 frozen 边界。

**Acceptance Criteria:**
- Given 唯一或歧义的 file/class/interface/qualified method/event/contract 与 alias fixture，when 解析，then 唯一结果含 canonical path/blob SHA；缺失限定、重名、跨 kind/非 Contracts alias 和不支持签名稳定失败。
- Given using/reference、inheritance/implementation、Event/Contract consumer、unit test symbol 与分行 `Refs:` fixture，when 分析，then 仅生成固定 relation、合法 endpoint、可回读 path/anchor/SHA，排序去重稳定；注释、字符串、`.tscn` 和文档提及不产 evidence。
- Given Contract/Event/save/Core、Service/System、UI-only、混合及不足证据目标，when 分类，then 最高等级为 high、medium、low 或 unknown，rules/reasons 稳定完整。
- Given malformed target、edge、array、hash、lineage、risk 或 binding，when 验证，then 返回稳定 `invalid_manifest`/`invalid_kcp_binding`，不得泄漏 `KeyError`。
- Given 同一 inputs 但迭代顺序不同，when 分析，then排除 `generated_at` 后 evidence canonical-equivalent；只声明 AC-001 code/test 子集，完整 AC-001、AC-003、CAP-4 仍未完成。

## Spec Change Log

- 2026-09-05: semantic correctness hardening completed; parser, resolver, evidence, risk, report validation and deterministic projection are covered by 14 focused tests. Runtime and Knowledge producer arrays remain empty by design.
- 2026-09-05: review-loop patches completed; raw/interpolated raw strings, duplicate identities, unsupported type forms, interface/abstract methods, namespace-safe inheritance, narrow references and using evidence, same-line Refs, conflicting edge payloads, indexed edge universe/hash checks, report item coherence, and target-only risk precedence are covered by 23 focused tests.
- 2026-09-05: final review patch fixes completed; alias bytes are read from trusted Git blobs, generic base parameters are tolerated without global parser failure, nested namespace/local-function ownership is bounded, using aliases are evidenced, report test/path coherence is enforced, and invalid target paths fail as `invalid_manifest`.
- 2026-09-05: final复审验证通过；focused Analyzer suite 23/23 green，py_compile 与 git diff --check 通过。补丁仅涉及语义解析、证据边界与 report 校验，Runtime/Knowledge producer 仍未实现。

## Design Notes

受限 parser 先屏蔽注释/字符串，再按平衡分隔符处理泛型和参数；无法安全规范化的 function pointer、dynamic、unresolved generic 返回 `unsupported_target`。Runtime/Knowledge arrays 保持空。

## Verification

**Commands:**
- `py -3 -m unittest scripts.python.tests.test_impact_analyzer -v` -- 23 tests pass after final semantic review patches.

## Suggested Review Order

**Trusted input and resolution**

- 以可信 Git blob 固定分析输入
  [`impact_analyzer.py:713`](../../scripts/python/impact_analyzer.py#L713)

- 统一符号、泛型与命名空间解析
  [`impact_analyzer.py:101`](../../scripts/python/impact_analyzer.py#L101)

**Evidence and risk semantics**

- 仅生成可证明 typed edges
  [`impact_analyzer.py:760`](../../scripts/python/impact_analyzer.py#L760)

- 按最高适用规则稳定分类风险
  [`impact_analyzer.py:700`](../../scripts/python/impact_analyzer.py#L700)

**Report integrity**

- 拒绝不一致或伪造报告证据
  [`impact_analyzer.py:920`](../../scripts/python/impact_analyzer.py#L920)

**Verification and deferred scope**

- 聚焦测试覆盖语义边界
  [`test_impact_analyzer.py:1`](../../scripts/python/tests/test_impact_analyzer.py#L1)

- 记录 Runtime、Knowledge 与 CLI 后续切片
  [`deferred-work.md:1`](deferred-work.md#L1)
- `py -3 -m unittest scripts.python.tests.test_impact_analyzer -v` -- expected: semantic suites 全绿。
- `py -3 -m unittest scripts.python.tests.test_impact_analyzer -v` -- 23 tests pass after review-loop patch fixes。
- `py -3 -m unittest scripts.python.tests.test_impact_analysis_index scripts.python.tests.test_impact_analysis_index_repository_smoke scripts.python.tests.test_impact_analyzer` -- expected: 联合回归全绿。
- `py -3 -m py_compile scripts/python/impact_analyzer.py scripts/python/tests/test_impact_analyzer.py` -- expected: 无语法错误。
- `git diff --check` -- expected: 无 whitespace 错误，`docs/121.txt` 未修改、未提交。
