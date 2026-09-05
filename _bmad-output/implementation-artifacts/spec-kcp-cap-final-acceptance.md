---
title: 'KCP CAP-1 through CAP-6 Final Acceptance'
type: 'feature'
created: '2026-09-05'
status: 'in-progress'
review_loop_iteration: 0
baseline_commit: 'c4853a2'
context:
  - 'docs/121.txt'
  - 'execution-plans/2026-09-05-kcp-impact-analysis-completion.md'
  - '_bmad-output/implementation-artifacts/spec-kcp-consumer-rollout-hardening.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

完成 docs/121.txt 对应的 CAP-1～CAP-6 最终验收，建立逐项、可审计的真实仓库证据矩阵，并关闭或明确记录所有 adapter hardening 剩余项。

## Boundaries & Constraints

**Always:** 使用真实仓库与真实 bundle/freeze/sidecar/report/handoff 证据；保留正负测试；不修改 KCP authority/generated state；未满足项必须保持 OPEN。

**Never:** 不把 synthetic fixture、局部单测或 KCP terminal PASS 当作 CAP 总验收；不放宽 schema、threshold 或负向约束。

## Tasks & Acceptance

- [ ] 建立 CAP-1～CAP-6 验收矩阵，记录实现入口、正向/负向测试、真实证据和结论。
- [ ] 补齐并验证 TOCTOU、resume/fork、report/manifest consistency。
- [ ] 对 Chapter 4/5/6/Review 执行 shadow→decision→freeze→binding→impact→handoff preflight 链。
- [ ] 更新 execution plan、decision log、deferred-work，准确关闭已完成项并保留 OPEN 项。
- [ ] 运行 impact、knowledge、handoff、Chapter 6 和 KCP final gates。

Given 每个 CAP 有真实正负证据，when final audit runs, then matrix status is PASS only for fully evidenced CAPs.
Given 任一 CAP 缺少真实闭环证据，when final audit runs, then it remains OPEN and overall completion is not claimed.

</frozen-after-approval>

## Code Map

- `scripts/python/tests/` impact/knowledge/handoff suites
- `scripts/python/run_binding_evidence_rollout.py`
- `scripts/python/validate_knowledge_control_plane.py`
- `execution-plans/2026-09-05-kcp-impact-analysis-completion.md`
- `decision-logs/2026-09-05-kcp-impact-analysis-open-findings.md`
- `_bmad-output/implementation-artifacts/deferred-work.md`

## Verification

- impact/analyzer/runtime/CLI tests
- knowledge/freeze/handoff/rollout tests
- `py -3 scripts/python/validate_knowledge_control_plane.py --require-generated`
- `git diff --check`

</analysis>

