---
title: 'KCP Impact CLI 工件完整性修复'
type: 'bugfix'
created: '2026-09-05'
status: 'done'
review_loop_iteration: 0
baseline_commit: '8e751d1a0303ed343691aabb67f9b0d394914f59'
context:
  - 'execution-plans/2026-09-05-kcp-impact-analysis-completion.md'
  - '_bmad-output/specs/spec-kcp-impact-analysis/impact-contract.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** CLI 早期失败缺少证据，写入冲突及异常可能覆盖或错配 report/manifest；旧 harness 的 done 声明不成立。

**Approach:** 统一成功与失败的工件写入入口，验证输出边界，独占发布并处理可捕获的部分失败，补齐对应回归。

## Boundaries & Constraints

**Always:** 遵守 ADR-0035 和 Architecture AD-8/10/15；仅写 `logs/ci/**`；保留既有工件；保持状态码、schema 与 authority 边界。测试使用临时 Git 仓库和 synthetic binding，明确其不能证明真实 freeze 集成。

**Ask First:** 需要变更 schema、discovery 策略或 KCP 契约时先确认。

**Never:** 修改 `docs/121.txt`、generated state，自动 push，或将本轮通过称为 CAP 总验收完成。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| SUCCESS | 有效输入、空闲输出 | 完整 report 后发布 manifest，哈希一致 | exit 0 |
| EARLY_FAILURE | 非法 target/revision | 安全输出处保留失败二件套 | 既有非零 code |
| INVALID_OUTPUT | 越界、重解析逃逸、保留文件名 | 拒绝原路径；安全隔离目录保存诊断 | path_outside_repository 或 collision |
| COLLISION | report 或 manifest 已存在；并发写者 | 原字节不变，失败证据使用独立目录 | index_identity_collision |
| PARTIAL_FAILURE | 第二件发布异常 | 不留可误用的成功 report；不绑定旧工件 | internal_error；隔离失败证据 |
| STORAGE_FAILURE | 诊断目录也不可写 | stdout 明确说明证据未保存 | 非零退出，不宣称已落盘 |

</frozen-after-approval>

## Code Map

- `scripts/python/analyze_impact.py`：`main` 的输入顺序、两条异常路径和两件发布是修复中心。
- `scripts/python/impact_analyzer.py`：`failure_report`、`atomic_write_json`；后者使用覆盖写入，检查调用者后替换。
- `scripts/python/impact_analysis_index.py`：`atomic_publish_bytes` 提供 Windows 不覆盖 rename、fsync 和验证；复用其机制。
- `scripts/python/tests/test_analyze_impact_cli.py`：正式 builder fixture；纠正 malformed 测试的无工件断言。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/python/tests/test_analyze_impact_cli.py`：先补矩阵回归，保留失败证据。
- [x] `scripts/python/analyze_impact.py`、`scripts/python/impact_analyzer.py`：统一发布与诊断，先验证路径再赋予写入资格；序列化并验证两件后发布，保护并发写者。
- [x] `scripts/python/tests/test_impact_analysis_index.py`：复核独立运行的 import 问题，保证完整验证能执行，不跳过失败。
- [x] `_bmad-output/implementation-artifacts/spec-kcp-impact-analyzer-cli-production-harness.md`：补中文勘误，保留原冻结块历史；修复验收后再核定状态。
- [x] `execution-plans/2026-09-05-kcp-impact-analysis-completion.md`：更新缺陷与测试证据映射；持续保留未完成项。

**Acceptance Criteria:**
- Given 两个 CLI 同时发布同一输出，when 完成竞争，then 最多一个成功，胜者工件字节和哈希保持一致。
- Given 可捕获的写入异常，when 命令返回，then 没有成功孤立 report，也没有 manifest 指向其他运行工件。
- Given 所有本轮回归通过，when 更新完成度，then 只关闭有实现与测试证据的条目，Runtime 与真实 KCP 集成仍开放。

## Spec Change Log

## Design Notes

沿用先 report 后 manifest 的既有协议；两文件不是文件系统原子事务。目录级写者协调和不覆盖发布共同保护并发；补偿只能清理可证明属于本次运行的工件。进程强杀时的 reader 完整性属于后续 adapter 验收，不能凭本轮测试宣称已解决。

## Verification

- `py -3 -m unittest scripts.python.tests.test_analyze_impact_cli -v`
- `py -3 -m unittest scripts.python.tests.test_impact_analyzer scripts.python.tests.test_impact_analysis_index scripts.python.tests.test_impact_analysis_index_repository_smoke`
- `py -3 scripts/python/check_gate_bundle_consistency.py`
- `py -3 scripts/python/validate_recovery_docs.py --dir all`
- `git diff --check`

全部收集退出码；证据归档到 `logs/ci/2026-09-05/impact-cli-artifact-integrity/`。

审查修复后 `review-green.log`：CLI 与 LockAndAtomicity 41 tests，exit 0。原核心 101 项运行有 1 项归档污染失败，定向 smoke 重跑通过；完整历史与限定见执行计划。物理存储拒绝身份查询、删除或隔离时只能明确报告残留，不能承诺物理撤销；非协作写者与强杀后的消费安全仍待 adapter 验收。

## Suggested Review Order

**入口与发布**

- 先检查输出资格，再进入分析和失败证据流程。
  [analyze_impact.py:214](../../scripts/python/analyze_impact.py#L214)
- 双工件验证、互斥与补偿集中在同一入口。
  [analyze_impact.py:94](../../scripts/python/analyze_impact.py#L94)
- 发布前保存身份，清理诊断独占写入。
  [impact_analysis_index.py:896](../../scripts/python/impact_analysis_index.py#L896)

**异常与证据**

- 身份不可验证时保留原件并明确报告残留。
  [analyze_impact.py:158](../../scripts/python/analyze_impact.py#L158)
- 隔离重试保留前次诊断和报告哈希。
  [analyze_impact.py:187](../../scripts/python/analyze_impact.py#L187)

**回归**

- 临时 Git 仓库验证正式 CLI 的成功与失败路径。
  [test_analyze_impact_cli.py:23](../../scripts/python/tests/test_analyze_impact_cli.py#L23)
- 暂停首位写者，明确覆盖发布窗口内的竞争。
  [test_analyze_impact_cli.py:431](../../scripts/python/tests/test_analyze_impact_cli.py#L431)
