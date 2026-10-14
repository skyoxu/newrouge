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

## MVG 工作流夹具维护（2026-10-14，P2）

- 修复 `scripts/python/tests/test_project_health_planning.py` 中两个既有生产消费者夹具：`test_capability_then_mvg_use_actual_planner_stages_without_mutating_main`、`test_mvg_consumes_capabilities_already_committed_in_main`。夹具 planned test 输出不满足当前 append schema，导致候选零准入。该对象已有 `test_refs`，不能用缺字段解释；需按实际 schema 分支修正夹具并复验完整消费者链，禁止放宽生产准入门槛。
- 证据：本轮三层复审及 `_bmad-output/implementation-artifacts/spec-mvg-review-receipts-and-recovery-hardening.md`。本轮修补的输入/回执/门禁定向测试通过，以上两项在此前 HEAD 已失败；付费模型未调用。
