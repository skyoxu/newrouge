---
title: 'Story 4.5：分别核对Task、Flow和累计里程碑完成'
type: 'feature'
created: '2026-11-26'
status: 'done'
baseline_commit: 'cdf4a3daa12097901702186b094ac25ca535c7e3'
story_key: '4-5-分别核对task-flow和累计里程碑完成'
review_loop_iteration: 1
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-4-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 单 Task 局部自检、单 Flow/pilot/critical 结果与跨快照报告易被冒充目标 Flow 或累计 full-MVG 里程碑通过，既有 milestone_incremental_handoff 尚未消费三类义务与覆盖回执。
**Approach:** 新增 _b_route_completion_verdict.py 与 b-route-completion-verdict 只读入口并适配 milestone_incremental_handoff.py，按三类义务、证据等级与同一 snapshot 分别核对 Task、Flow 与累计里程碑完成，不在 catalog 存通过态或建第二状态机。

## Boundaries & Constraints

**Always:** 单 Task 局部成功仅满足其对应局部责任，若所属 Flow 其他必需实现、Chapter 7 或验证未齐，Flow 保 pending/blocked 并列缺项，禁因旧 done、结构关系、planned 或既有可运行代码忽略本次新增义务；目标 Flow 完成须所有当前必需义务、受影响旧回归、适用 Chapter 7 与适用人工检查均具当前身份有效证据才通过，真实引擎输入、场景方法、静态连线与人工等级严禁混代，专用集成 owner 免自身先 done 前置；单 Flow、pilot、critical 或 partial 结果标真实范围，仅当前累计必测、组合测试与人工义务在同一整合 snapshot 满足才称累计 full-MVG，禁拼接异 snapshot 报告，缺任一必需项不授累计通过；旧 Flow A 失败须修后完整回归，范围外 B 保定义/绑定更新与后续责任免提前实施、迁入本次范围则未完阻断，禁按能否运行重分类换绿，退役或减义务续走显式防削弱；manifest/scope/InputSet/receipt 损坏过期或报告为空/跳过/未执行时拒绝并报六字段诊断，合法非 Flow 按已采纳 other_verification 判断，Task 状态仍归 Taskmaster 且零改 catalog。
**Ask First:** 改 7 FORMAL、扩 ReasonCode/Stage、在 catalog 存通过态或启付费 API。
**Never:** 局部绿充 Flow 完成；低阶证据代高阶输入或人工；跨 snapshot 拼累计 full-MVG；按可运行态重分类失败 Flow；写 Task 状态或建第二生命周期。

## I/O & Edge-Case Matrix

| Scenario | Input | Expected | Error |
|---|---|---|---|
| TASK_VS_FLOW | 单 Task 局部绿但同 Flow 其他项未齐 | 仅满足本 Task；Flow 保 pending/blocked 列缺项 | 凭旧 done、planned 或旧代码放行 Flow 阻断 |
| TARGET_FLOW | 目标 Flow 实现、Ch7 与对应等级证据齐备 | 身份与等级全配才判 Flow 完成；专用 owner 免自锁 | 方法/静态代引擎输入、机器代人工或自锁阻断 |
| CUMULATIVE_MVG | 单 Flow/critical/partial 或跨 snapshot 报告 | 部分标真实范围；仅同 snapshot 全齐判累计 full-MVG | 跨 snapshot 拼接或缺项宣累计通过阻断 |
| HANDOFF_AB | 旧 A 失败及范围外 B，或 B 迁入本次范围 | A 阻断须修；B 在外免提前实现、入内未完阻断 | 按可运行态重分类或无防削弱删退旧测阻断 |
| CORRUPT_NONFLOW | 损坏/过期依据、空/跳测及合法非 Flow | 拒不明范围并报六字段诊断；非 Flow 按 other_verification 判 | 放行空/过期报告、写 tasks.json 或污 catalog 阻断 |

</frozen-after-approval>

## Code Map

- `milestone_incremental_handoff.py`, `_b_route_verification_scope.py`, `_b_route_scope_runner.py`, `_b_route_chapter7_slice.py`, `_b_route_evidence_reuse.py`

## Tasks & Acceptance

- [x] `_b_route_completion_verdict.py`, `check_b_route_completion_verdict.py`, `milestone_incremental_handoff.py`, `dev_cli*.py`
- [x] `run_mvg_acceptance.py`, `_b_route_scope_runner.py`, `run_gate_bundle.py`, `b-route-runtime-deterministic.yml`, `test_b_route_completion_verdict.py`, `test_b_route_runtime_ci.py`, `docs/workflows/**`

**AC:** 四层分别核对（Task/Flow/累计 full-MVG/合法非 Flow），禁等级混代与跨快照拼接，保范围外 B 责任，损坏/空/跳测拒并报六字段诊断，零改 Task 状态与 catalog。

## Spec Change Log

- 2026-11-26 (`review_loop_iteration=1`): Step 4 修复 `P-01`..`P-06`（`story-4-5-step4-triage.md`: `patch=6, defer=0, dismiss=1`）：兼容 64-hex `snapshot_digest` 与 `input-manifest.json`/`mode=run`/`static-wiring` 核验；纯非 Flow 保 `runtime_verified=false`；补齐 `task` 多任务映射与跨源 `dedicated_owners`；补齐 `milestone` 省略报告实时 Ch7、`authority_refs`、`verified_scope=partial`、`validate_task_handoff`、报告先于事件写入及隔离临时目录对齐；4 套 `test_milestone_*` 纳入 CI 门禁。

## Suggested Review Order

1. `_b_route_completion_verdict.py` -> 2. `milestone_incremental_handoff.py`, `check_b_route_completion_verdict.py` -> 3. `run_mvg_acceptance.py`, `_b_route_scope_runner.py` -> 4. `test_b_route_completion_verdict.py`, `run_gate_bundle.py`, `b-route-runtime-deterministic.yml`, `test_b_route_runtime_ci.py`

## Verification

- `logs/ci/2026-11-26/story-4-5-final-verify.log`（10/10 PASS）
