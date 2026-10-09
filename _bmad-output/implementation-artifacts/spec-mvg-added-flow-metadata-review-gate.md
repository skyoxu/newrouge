---
title: 'MVG 新增 flow 映射字段的修改依据校验'
type: 'bugfix'
created: '2026-10-09'
status: 'done'
baseline_commit: '1c9730472b7c3c28ce2f80dd3a1242e763bed0e5'
review_loop_iteration: 0
context:
  - '{project-root}/.agents/skills/plan-mvg/SKILL.md'
  - '{project-root}/docs/adr/ADR-0005-quality-gates.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 旧 flow 缺少 `requirement_ids` / `capability_refs` 时，新增映射且不提供 `change_reviews` 仍通过本地检查，随后被语义准入拒绝。本轮三个候选反复遇到此类问题，最小复现返回空错误列表。

**Approach:** 修正字段存在性和值比较，让新增、移除和修改都受既有依据检查保护。先写失败测试，再修实现，最后验证 dispatcher 的局部重试和相关回归。

## Boundaries & Constraints

**Always:** 遵循 ADR-0005；证据在 `logs/**`，代码和日志英文。保留 CLI schema、prepared 引用检查、独立语义批准及现有修复预算。

**Ask First:** 扩展需求归属政策、修改累计基线任务、重新启动页面整轮生成或发布。

**Never:** 修改任务三联、GDD、Capability、MVG；合成授权；通过放宽审查拿绿；复用已停止候选作新结果；把回归通过说成页面整轮通过。

## I/O & Edge-Case Matrix

| 场景 | 输入 | 预期行为 | 错误 |
| --- | --- | --- | --- |
| 新增字段 | 旧对象无字段，候选新增非空或空数组，无依据 | 拒绝分段 | 既有 `segment_flow_change_review_missing:<id>` |
| 移除或修改 | 已有字段变化，无依据 | 拒绝 | 同上 |
| 无变化 | 字段存在性与值相同 | 不报依据缺失 | 其他检查照常 |
| 合规依据 | 当前 flow、prepared authority、reviewed 状态和理由齐全 | 本地依据检查通过 | 独立审查仍判断规格支持性 |
| 非法依据 | 跨 flow、重复、未审阅或未准备 | 拒绝 | 既有路由/引用错误 |
| 持续无依据 | 重试仍不合规 | 有界退出，不能合并 | 不消耗独立语义审查 |

</frozen-after-approval>

## Code Map

- `scripts/python/plan_mvg.py:1660`：`validate_segment_routing` 的 `key in incumbent` 遗漏字段新增。复用现有错误码，不新增状态机或兼容层。
- `scripts/python/plan_mvg.py:1633`：已有 review 身份、重复、状态与理由检查；`validate_segment_references` 保护 prepared authority。
- `scripts/python/plan_mvg.py:2155`：merger 保留依据并清理过期理由，不改此保护。
- `scripts/python/tests/test_mvg_segment_scope.py`：schema-aware dispatcher fixture 和局部重试用例；现有 fixture 总带映射字段，缺少旧格式场景。
- `logs/ci/mvg-page-test/run-2026-10-09T12-16-19-038Z/final.json`：已停止 job，锁释放，无 JS 错误；仅作诊断，不参与新生成。

## Tasks & Acceptance

**Execution:**

- [x] `scripts/python/tests/test_mvg_segment_scope.py`：加入矩阵单元场景及缺字段 dispatcher 的重试/持续失败/成功合并用例，先记录 RED。
- [x] `scripts/python/plan_mvg.py`：修正存在性和值检测，保持引用、预算、独立审查不变。
- [x] `docs/workflows/mvg-integration-acceptance.md`：如说明缺失，仅补充新增字段也属于变更。
- [x] `logs/ci/2026-10-09/mvg-added-flow-metadata-review-gate/`：记录红绿与回归证据，不覆写 producer 状态。

**Acceptance Criteria:**

- Given 旧 flow 缺映射字段，when 候选新增且无依据，then 分段在独立语义调用前被拦截。Refs: `scripts/python/tests/test_mvg_segment_scope.py`。
- Given 首次缺依据、再次修正，when dispatcher 重试，then 仅重试相关 flow，合并保留依据。Refs: 同上。
- Given 修复始终不合规，when 预算耗尽，then 不生成可准入提案。Refs: 同上。
- Given 合规分段，when 独立准入，then 原有规格支持性校验继续有效。Refs: `scripts/python/tests/test_mvg_planning_contract.py`。

## Spec Change Log

## Verification

- `py -3 -m pytest scripts/python/tests/test_mvg_segment_scope.py -q`：先 RED 后 GREEN。
- `py -3 -m pytest scripts/python/tests/test_mvg_segment_scope.py scripts/python/tests/test_mvg_planning_contract.py scripts/python/tests/test_mvg_acceptance.py -q --junitxml=logs/ci/2026-10-09/mvg-added-flow-metadata-review-gate/regression.xml`：相关回归全绿。
- `git diff --check`：无空白错误。

仅验证确定性路径，不重新点击按钮。服务保留 `http://127.0.0.1:8767`。

## Verification Results

- 修复前：3 项失败、22 项通过，确认失败来自本次遗漏。
- 修复后：25 项分段测试通过；相关回归由实施代理和主代理分别运行，均为 166 项通过。
- 独立边界审查和验证审查无阻断项。盲审建议未构成本次必修缺陷，既有 CLI schema、prepared 引用及独立准入保护未改变。
- 证据：[verification.md](../../logs/ci/2026-10-09/mvg-added-flow-metadata-review-gate/verification.md)、[red-confirmed.txt](../../logs/ci/2026-10-09/mvg-added-flow-metadata-review-gate/red-confirmed.txt)、[root-regression.xml](../../logs/ci/2026-10-09/mvg-added-flow-metadata-review-gate/root-regression.xml)。

## Suggested Review Order

- 核心检查同时比较字段存在性和值，新增字段不再漏检。
  [plan_mvg.py:1661](../../scripts/python/plan_mvg.py#L1661)
- 累计基线规则明确新增或移除空数组也是变更。
  [mvg-integration-acceptance.md:129](../../docs/workflows/mvg-integration-acceptance.md#L129)
- 旧格式 dispatcher 验证局部修复、有界失败及依据保留。
  [test_mvg_segment_scope.py:166](../../scripts/python/tests/test_mvg_segment_scope.py#L166)
- 字段矩阵验证新增、移除、清空和未变化的情况。
  [test_mvg_segment_scope.py:261](../../scripts/python/tests/test_mvg_segment_scope.py#L261)
