# Technical Debt Register

This file is updated by scripts/sc/run_review_pipeline.py.

- P0/P1 findings stay in the must-fix path and should not be parked here.
- Only P2/P3/P4 items from sc-llm-review are recorded here, grouped by task.

## Maintenance Rules

- The block between BEGIN/END AUTO:RUN_REVIEW_PIPELINE_TECHNICAL_DEBT is auto-managed. Do not hand-edit task sections there unless you are doing emergency cleanup.
- P0/P1 items are not technical-debt parking items in this workflow. They stay on the must-fix path.
- A task section is cleared by rerunning py -3 scripts/sc/run_review_pipeline.py --task-id <id> after the low-priority review findings are resolved. The next successful sc-llm-review replaces that task section.
- Do not mix transient blockers, environment failures, or approval pauses into this file. This register is only for low-priority review debt that can be scheduled intentionally.

<!-- BEGIN AUTO:RUN_REVIEW_PIPELINE_TECHNICAL_DEBT -->
<!-- END AUTO:RUN_REVIEW_PIPELINE_TECHNICAL_DEBT -->

## MVG 工作流夹具维护（2026-10-14，P2，已关闭）

- 修复 `scripts/python/tests/test_project_health_planning.py` 中两个既有生产消费者夹具：`test_capability_then_mvg_use_actual_planner_stages_without_mutating_main`、`test_mvg_consumes_capabilities_already_committed_in_main`。夹具 planned test 输出不满足当前 append schema，导致候选零准入。该对象已有 `test_refs`，不能用缺字段解释；需按实际 schema 分支修正夹具并复验完整消费者链，禁止放宽生产准入门槛。
- 证据：本轮三层复审及 `_bmad-output/implementation-artifacts/spec-mvg-review-receipts-and-recovery-hardening.md`。本轮修补的输入/回执/门禁定向测试通过，以上两项在此前 HEAD 已失败；付费模型未调用。
- Story 2.1 已定位为假 runner 的测试路径不在 prepared schema 的允许清单，改用 `PlanningAcceptanceTests.cs`；两个 Knowledge 生产消费者回归通过，并验证 apply 后合法 manifest 可展示、manifest/readiness/prepared Capability/journal 篡改继续被拒绝。没有降低生产 validator。

## MVG segment 夹具维护（2026-10-15，P2）

- `test_mvg_segment_scope.py` 七项既有测试的 fragment 路径与 prepared-reference enum 不一致，另有断言仍要求 pattern 而当前 schema 使用 enum。应对齐夹具和 schema 合约，保留路径与范围门禁；不要为了测试通过放宽准入。
- 在 Story 3.1 修改前的 HEAD 直接内存加载 `plan_mvg.py` 复现相同错误；证据：`logs/ci/2026-10-15/story-3-1/head-segment-baseline.log`。本轮路线/Knowledge/契约定向回归另行验证，不把这七项标记为通过。

## MVG recovery 夹具断言维护（2026-10-16，P2）

- `test_public_recovery_rejects_prefix_scope_and_receipt_tampering_without_models` 把 `review`、`validate`、`apply` 都断言为抛出异常，但既有 `validate` 对 selected-chain 错误返回 `formal_applicable=false`、`formal_blockers` 与未完成报告。后续应分别检查各公共 API 的阻断合约，不应改变生产 API 或放宽校验来满足测试。
- 证据：`logs/ci/2026-10-16/mvg-chapter5-lossless-transport/tamper-single.xml`；对照基线提交 `8383b7a2091e23680d7b071bbc0e631aa886ff64` 的 `plan_mvg.py::validate`，该捕获与返回行为在本轮修改前已存在。本轮不再重复此慢测试，不将其记作通过。
