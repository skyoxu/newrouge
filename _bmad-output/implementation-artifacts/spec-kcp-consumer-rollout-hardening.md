---
title: 'KCP Consumer Rollout and Adapter Hardening'
type: 'feature'
created: '2026-09-05'
status: 'done'
review_loop_iteration: 0
baseline_commit: '39fddfa'
context:
  - '_bmad-output/implementation-artifacts/spec-kcp-binding-evidence-handoff.md'
  - '_bmad-output/implementation-artifacts/spec-kcp-impact-analysis-adapter-handoff.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

完成 sidecar binding evidence 在 Chapter 4/5/6/Review 的真实 consumer rollout，并补齐 adapter 的 resume/fork、TOCTOU、manifest consistency 验证；不改变 report schema 或 KCP authority。

## Boundaries & Constraints

**Always:** consumer 必须显式传递 frozen context、impact report、revision、sidecar；失败在 RED/LLM/review 前终止；路径、SHA、consumer/task identity 严格绑定。

**Never:** 不修改 current/LKG/publication/generated state；不自动接受候选；不把 synthetic harness 当真实 rollout 证据。

## Tasks & Acceptance

- [x] Chapter 4/5/6/Review 入口统一传递并校验 sidecar.
- [x] handoff 测试覆盖 resume/fork identity、TOCTOU 替换、manifest/report mismatch.
- [x] 真实仓库 bundle 执行四类 consumer rollout，记录 logs/ci 证据.
- [x] 更新 deferred-work 与执行计划，明确剩余 CAP 验收入口.

Given sidecar 被替换或 manifest SHA 不匹配，when consumer preflight runs, then it fails before downstream execution.
Given valid frozen context/report/sidecar/revision, when each consumer preflight runs, then it passes for chapter4, chapter5, chapter6, and review.
Given legacy invocation without sidecar, when compatibility mode is explicitly selected, then existing validation remains unchanged.

</frozen-after-approval>

## Code Map

- `scripts/python/impact_analysis_handoff.py`
- `scripts/python/analyze_impact.py`
- `scripts/python/run_single_task_light_lane.py`
- `scripts/python/chapter6_route.py`
- `scripts/python/tests/test_impact_analysis_handoff.py`
- `scripts/python/tests/test_run_single_task_chapter6_lane.py`

## Verification

- `py -3 -m unittest scripts.python.tests.test_impact_analysis_handoff scripts.python.tests.test_run_single_task_chapter6_lane -v`
- 四类真实 consumer preflight 证据
- `git diff --check`


