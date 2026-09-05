---
title: 'KCP Binding Evidence Handoff Integration'
type: 'feature'
created: '2026-09-05'
status: 'in-progress'
review_loop_iteration: 0
baseline_commit: '7f624f5'
context:
  - '_bmad-output/implementation-artifacts/spec-kcp-impact-analysis-adapter-handoff.md'
  - 'scripts/python/knowledge_binding_producer.py'
  - 'scripts/python/impact_analysis_handoff.py'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

将只读 `knowledge-binding-evidence.v1` sidecar 接入 Impact run manifest 与 handoff 校验，完成 producer→freeze→consumer 的可验证链路，同时保持 `impact-analysis.v1` report schema 不变。

## Boundaries & Constraints

**Always:** sidecar 必须绑定 request_id、source bundle SHA、repository revision 和每个 source SHA；保持 authority/generated state 不变；错误 fail-closed。

**Never:** 不修改 report schema、KCP current/LKG/publication、冻结工件字段；不自动接受候选；不推断 source。

## Tasks & Acceptance

- [ ] `impact_analysis_handoff.py`：增加可选 sidecar 参数与严格校验。
- [ ] `analyze_impact.py`：manifest 可记录 sidecar path/SHA，缺失时保持兼容。
- [ ] tests：覆盖四 consumer、SHA/revision/request mismatch、缺失 sidecar、旧 manifest 兼容。
- [ ] 运行 Runtime/Analyzer/CLI/Index/Knowledge/hand-off 全部回归。

Given 有效 sidecar，when handoff 校验，then revision、request、bundle SHA 和 source SHA 全部通过。
Given sidecar 被篡改或与 frozen context 不一致，when handoff 校验，then 稳定失败且不启动后续 consumer。
Given 未提供 sidecar，when 旧 manifest 校验，then 保持现有兼容行为。

</frozen-after-approval>

## Code Map

- `scripts/python/knowledge_binding_producer.py`: `produce_binding`、`validate_binding_evidence`
- `scripts/python/impact_analysis_handoff.py`: `validate_handoff` 与 CLI `main`
- `scripts/python/analyze_impact.py`: report/run-manifest 发布路径
- `scripts/python/tests/test_impact_analysis_handoff.py`、`test_analyze_impact_cli.py`

## Verification

- `py -3 -m unittest scripts.python.tests.test_knowledge_binding_producer scripts.python.tests.test_impact_analysis_handoff scripts.python.tests.test_analyze_impact_cli -v`
- `py -3 scripts/python/validate_knowledge_control_plane.py --require-generated`
- `git diff --check`

