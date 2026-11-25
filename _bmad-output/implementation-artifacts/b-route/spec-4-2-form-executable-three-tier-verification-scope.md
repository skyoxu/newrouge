---
title: 'Story 4.2：形成可执行的三类义务VerificationScope'
type: 'feature'
created: '2026-11-26'
status: 'done'
baseline_commit: '216ef4566cd30a938db72c80510a2890c65bec09'
story_key: '4-2-形成可执行的三类义务verificationscope'
review_loop_iteration: 1
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-4-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 4.1 传递影响尚未与当前交付范围、有效 manifest 及共同 InputSet 合成为具可比较身份与防重分类约束的验证合同，旧回归、本次新增/未完与范围外未来责任易混淆或被转 planned 换绿。
**Approach:** 在既有辅助 schema 与公共 codec 上注册 newrouge.b-route-verification-scope.v1，交付 _b_route_verification_scope.py 与 b-route-verification-scope CLI，冻结三类义务、执行分桶与漂移失效检验，不重造 manifest 权威或捏造假测。

## Boundaries & Constraints

**Always:** 核对 4.1 影响、当前采纳交付范围、有效 manifest 与 InputSet，绑定 schema_version、scope_id、input_set_digest、plan/binding/manifest/累计基线引用、变更根、影响证明、声明测试与人工责任，用稳定 Flow/test/Requirement 身份，禁以旧 manifest 或可运行态裁剪当前责任；逐义务分为旧受影响回归（existing_required，完整保留）、本次新增/未完（current_new，未完保 pending/blocked 并阻断收口）与范围外未来（out_of_scope_future，登记定义/绑定更新及后续责任且不宣通过），支持同 Flow 混载旧与新增义务，禁把整个失败或既有 Flow 转 planned/future 换绿；共享改动影响旧 Flow A 与范围外未实现 B 时，A 须修后完整回归，B 在外保责任不宣通过、入范围后未完阻断，合法范围缩减须来源与防削弱 delta 审阅，禁借失败/启动不了/缺测删义务；未知保守扩大仍保三类责任，影响 Flow 的非 Flow 绑真实 MVG 回归、无 MVG 按 other_verification 处理，分列可执行测试、待实施与人工检查，不捏造 PASS 或脚本入口；同有效内容产同 scope_id，相关漂移产新范围并废受影响旧结论，拒未知/损坏版本，仅授权验证责任且零改 Task 状态。
**Ask First:** 改 7 FORMAL、扩 ReasonCode/Stage、造新状态机或启付费 API。
**Never:** 旧 manifest 裁责任；失败 Flow 转 planned/future；借失败/缺测删义务；捏造假测或 PASS；以范围充完成或改状态。

## I/O & Edge-Case Matrix

| Scenario | Input | Expected | Error |
|---|---|---|---|
| SCOPE_CONTRACT | 4.1 影响、当前范围、有效 manifest 与 InputSet | 绑定稳定身份、基线、影响证明、声明测试与人工责任 | 旧 manifest 或可运行态裁责任阻断 |
| THREE_TIERS | 含旧回归、本次未完、范围外未来及混合 Flow | 旧回归保留，未完阻断，未来记后续责任；支持同 Flow 混载 | 整个失败 Flow 转 planned/future 阻断 |
| SHARED_AB | 共享改动及于旧 A 与范围外 B，后 B 入范围 | A 留必测回归；B 在外不宣通过、入内阻断；缩减须审阅 | 借失败/无法启动/缺测移除阻断 |
| EXEC_BUCKETS | 未知映射、及 Flow 非 Flow 与无 MVG 非 Flow | 未知扩大保三类；分列可执行、待实施与人工检查 | 捏造假脚本入口或 PASS 阻断 |
| IDENTITY_DRIFT | 同输入重算 vs 相关漂移 vs 未知/损坏版本 | 同内容同 scope_id；漂移废受影响旧结论；拒损坏，零改状态 | 篡改复用、沿用旧结论或宣完成阻断 |

</frozen-after-approval>


## Code Map

- _b_route_verification_scope.py -- 分类、防降级、分桶与漂移核验
- _b_route_impact_closure.py, _b_route_input_set.py -- 影响证明与 InputSet

## Tasks & Acceptance

**Execution:**
- [x] verification-scope.schema.json, _b_route_schema_resources.py -- 辅助 schema
- [x] _b_route_verification_scope.py, build_b_route_verification_scope.py, dev_cli*.py -- 实现与 CLI
- [x] b-route-verification-scope.md 等入口文档；单测、run_gate_bundle.py 与 CI 门禁

**Acceptance Criteria:**
- Given 4.1 影响、交付范围、manifest 与 InputSet 可验，when 生成 VerificationScope，then 绑完整身份与三类义务（保同 Flow 混载、旧 A 回归与 B 迁入阻断，防削弱重分类），分列三类执行桶且不造假测。
- Given 重算或输入漂移/损坏，when 校验复验，then 同内容同 scope_id，相关漂移废受影响旧结论，拒损坏版本且不改状态或宣完成。

## Spec Change Log

- Step 4 fix-through（patch=6，见 logs/ci/2026-11-26/story-4-2-step4-triage.md）：裁剪/就地 planned 防御、证明 manifest 透传、delta 加固、语义校验与复验归因；意图未变。

## Suggested Review Order

1. `_guard_reclassification`、`_apply_delta`、`_check_semantics`、`revalidate_verification_scope`
2. schema 新增 defs 与 `--prior-conclusions`
3. Step 4 回归测试

## Verification

- `py -3 -B -m unittest scripts.python.tests.test_b_route_verification_scope -v`；`dev_cli.py b-route-verification-scope --help`