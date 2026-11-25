---
title: 'Story 4.3：让真实执行器消费范围并报告实际覆盖'
type: 'feature'
created: '2026-11-26'
status: 'done'
baseline_commit: '18e86926e5ae80dc75246a193ba1d2e4caec79f3'
story_key: '4-3-让真实执行器消费范围并报告实际覆盖'
review_loop_iteration: 1
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-4-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 既有 MVG 执行器仅跑整份 manifest 或给排序建议，尚未真实消费 VerificationScope、隔离 snapshot 与业务租约，也缺区分六类证据等级、未运行原因、超集与协议夹具边界的正式覆盖回执。
**Approach:** 新增 _b_route_scope_runner.py 并改造 run_mvg_acceptance.py、_mvg_execution.py 与 dev_cli 入口，真实消费 VerificationScope 执行测试并产出覆盖回执，不承诺提速且兼容原模式。

## Boundaries & Constraints

**Always:** 真实消费 scope_id/input_set_digest、当前 formal manifest、声明测试与环境，固定整合 snapshot 与业务租约，不只改 recommend 排序，运行更大累计集合须显式记实际超集而不称选择性执行；正式回执列 requested_tests、executed_tests、not_run 及原因、manual_obligations、结果证据与覆盖，绑同 scope/InputSet/manifest/snapshot，漏项、空报告、跳过、planned 或未完禁判 PASS，旧回归失败或无法启动禁转 future；按实际对象与关键输入分别报领域 xUnit、Godot GdUnit4、静态接线、场景方法、真实引擎输入与人工六类证据等级，断绑定必败，区分夹具初始化与玩家动作，禁以测试后门或假 runner 冒充生产路径；运行或恢复边界漂移、租约占用或已知确定性失败/stop-loss 时阻断结论并保已观察结果，沿既有停止信号止损，遵循短 metadata 锁与业务租约而不长占全局锁；支持小范围、超集与坏范围核对，进程调用、报告解析与覆盖回执可重建，拒未知 schema/错 manifest/缺必测项，协议夹具仅证适配解析不冒充真实 Godot 通过，随证据记 Windows/工具版本与未验限制。
**Ask First:** 改 7 FORMAL、扩 ReasonCode/Stage、承诺提速门槛或启付费 API。
**Never:** 仅改排序充选择性执行；漏项/空报告/跳过/未完判 PASS；旧失败转 future；假 runner/后门充引擎输入；长占全局锁或关测换绿。

## I/O & Edge-Case Matrix

| Scenario | Input | Expected | Error |
|---|---|---|---|
| CONSUME_SCOPE | 有效 VerificationScope（小范围或超集）与工具链 | 真实绑 scope/manifest/环境/snapshot 与租约；超集显式标注非选择性执行 | 仅改排序或把超集称选择性执行阻断 |
| COVERAGE_RECEIPT | 含运行、失败、未运行、待实施与人工义务 | 回执绑同四元组，列请求/执行/未跑原因与人工项 | 漏项、空报告、跳过、未完判 PASS 或旧失败转 future 阻断 |
| EVIDENCE_TIERS | 领域、场景方法、静态接线、引擎输入与断线挑战 | 六类证据等级分明；断绑定必败；分清初始化与玩家动作 | 假 runner、后门或方法调用充引擎输入阻断 |
| DRIFT_STOPLOSS | 边界漂移、租约争用或确定性失败/stop-loss | 阻断结论并保已观察结果；按信号止损，不占全局锁 | 忽略漂移/占用、占全局锁或跳回归阻断 |
| PROVENANCE | 小范围、超集、坏范围及协议 fake runner | 调用、解析与回执可重建；拒坏范围；协议夹具禁宣玩法通过并记版本 | 放行坏范围或拿协议夹具充真实 Godot 通过阻断 |

</frozen-after-approval>

## Code Map

- `_b_route_scope_runner.py`, `run_mvg_acceptance.py`, `_mvg_execution.py` -- 范围执行、快照、租约与回执
- `_b_route_verification_scope.py`, `_b_route_chapter7_slice.py`, `_b_route_operation_scope.py` -- 复验、接线与租约

## Tasks & Acceptance

**Execution:**
- [x] `_b_route_scope_runner.py`, `run_mvg_acceptance.py`, `_mvg_execution.py`, `dev_cli*.py` -- 执行器与入口
- [x] `b-route-scope-runner.md` 等文档；单测、`run_gate_bundle.py` 与 CI 门禁

**Acceptance Criteria:**
- Given 有效范围，when 运行小范围或超集，then 绑四元组与租约，产六类回执，断接线必败且漏项/空报告/未完禁 PASS。
- Given 漂移、争用、止损、坏范围或夹具，when 核对，then 阻断保已观察结果、止损未跑项、拒坏范围，夹具不宣真过。

## Spec Change Log

- Step 4（patch=6，见 `logs/ci/2026-11-26/story-4-3-step4-triage.md`）：租约内/快照复验、超集租约、完整 manifest/非空运行门禁、掩码逐按钮接线、`--version`/PATHEXT/六类去重、`not_run` 与 challenge 封存；意图未变。

## Suggested Review Order

1. `_b_route_scope_runner.py`（租约/复验、`probe_environment`、输入/接线与回执）
2. `run_mvg_acceptance.py`、`_mvg_execution.py`、`dev_cli.py`
3. 单测、`run_gate_bundle.py` 与 CI

## Verification

- `test_b_route_scope_runner`, `test_mvg_acceptance`, `test_b_route_verification_scope`, `test_b_route_runtime_ci`, `test_01_story25_ast_and_semantic_lock_guard`, `dev_cli.py run-mvg-acceptance --help`
