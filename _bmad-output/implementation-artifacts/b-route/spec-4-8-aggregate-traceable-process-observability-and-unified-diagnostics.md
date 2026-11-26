---
title: 'Story 4.8：汇集可追溯过程观测与统一诊断'
type: 'feature'
created: '2026-11-26'
status: 'done'
review_loop_iteration: 1
baseline_commit: '925d1943ee1196e53eef4ad6a2a1f99eaae21941'
story_key: '4-8-汇集可追溯过程观测与统一诊断'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-4-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 规划、编译、验证与返工事件散落于 `logs/**`，缺五维与 `event_id` 去重汇集入口，易重复计预留/dispatch、混暂停墙钟与活动耗时、混淆三类复用或重解释错误类别。
**Approach:** 新增只读 `_b_route_observability.py` 与 `b-route-observability`（含 `GET /api/knowledge/b-route-observability` 及页面只读展示），汇集阶段事件与六字段 `Diagnostic`，分列实测与 `unknown`/预留、隔离三类复用并守质量底线，不建分析库或第二状态。

## Boundaries & Constraints

**Always:** 按 `operation`/`run`、`scope`/`Flow`、`stage`、`attempt` 与规范化 `event_id` 汇集规划、3C、局部/Flow 验证及返工事件，回链执行者与原证据，报实测活动耗时、实际 dispatch、构建预热/重复测试、复用来源/理由、返回阶段与终止原因；同 `event_id` 只计 1 次而真实重试各保原事件，协调器预留、worker 投影与同笔 dispatch 禁算多笔调用；实测活动耗时与暂停墙钟、`unknown` 分列，预算预留与实测调用、账单费用（未实测标 `unknown`）分列，禁伪造对比基线，禁设提速、降成本、两小时、固定 Task 数或工时门槛；复用唯一 `ReasonCode` 与六字段（空填 `null`），禁页面文案重解释，执行故障禁转语义 finding 且与 `budget` 互不掩盖；严格隔离 2.9 采纳复用、2.7/2.8/3.2 应用幂等 no-op 与 4.4 构建/测试复用的身份与决定，禁跨类互证、禁刷旧 PASS 时间或全局刷 Knowledge；保留数据缺口、`stop-loss`（`rerun_guard`/`llm_retry_stop_loss`/`sc_test_retry_stop_loss`/`waste_signals`）、无进展重试与返工原因，仅允同口径历史参考，过程指标严禁抵消来源遗漏、成熟身份变化、少验义务、失败重分类或提前实现范围外 Flow。
**Ask First:** 改 7 FORMAL、扩 `ReasonCode`/`Stage`、接付费账单 API 或建分析库。
**Never:** 重复计预留+worker+dispatch；墙钟充活动耗时或估算充账单；重解释错误掩盖执行/预算故障；混代三类复用或刷旧时间；以指标抵消退化。

## I/O & Edge-Case Matrix

| Scenario | Input | Expected | Error |
|---|---|---|---|
| DEDUP_TRACE | 五类日志及预留+worker+dispatch | 五维汇集回链原证据；同 `event_id`/dispatch 计 1 次，重试分留 | 同 dispatch 多计、吞重试或丢回链阻断 |
| OBSERVED_UNKNOWN | 含暂停墙钟、预留、缺账单或缺基线 | 分列活动耗时、墙钟、预留与 `unknown`；零速度/成本门槛 | 墙钟充活动耗时、伪造账单/基线或设门槛阻断 |
| UNIFIED_DIAG | 缺治理、未知版本、损坏、漂移、pending、冲突、预算、语义错 | 统一 `ReasonCode` 与六字段（空填 `null`），保原类别 | 文案重解释、执行转语义或掩盖 `budget` 阻断 |
| THREE_REUSES | 2.9 采纳复用、journal no-op 与 4.4 构建/测试复用 | 三类独立标身份与决定；不刷旧时间、不刷 Knowledge | 跨类互证、刷 `original_executed_at` 或写权威阻断 |
| GAPS_STOPLOSS | 缺基线、无进展重试、`stop-loss` 或五类退化 | 保缺口、止损与返工定位；退化时质量底线判阻断 | 吞损坏日志或以指标抵消退化放行阻断 |

</frozen-after-approval>

## Code Map

`_b_route_observability.py`, `query_b_route_observability.py`, `_b_route_planning_page.py`, `_project_health_http.py`, `project_health_planning.js`

## Tasks & Acceptance

- [x] `_b_route_observability.py`, `query_b_route_observability.py`, `dev_cli*.py`
- [x] `_b_route_planning_page.py`, `_project_health_http.py`, `project_health_planning.js`
- [x] tests, CI gates, `docs/workflows/**`, `AGENTS.md`

## Spec Change Log

- Step 4 (`patch=10, defer=0, dismiss=0`): `P-01..P-10` path/reparse/write guards, schema/JSONL/baseline/truncation, 3A/3B calls/reserved/elapsed, filter+dedup gate, strict numerics, diag category/HTTP 422, reuse/ts conflict, 3A/3.10/4.5 quality floor, UI/tests/docs closure.

## Suggested Review Order

`_b_route_observability.py` -> `_b_route_planning_page.py`/`_project_health_http.py` -> `project_health_planning.js` -> tests/docs.

## Verification

- `logs/ci/2026-11-26/story-4-8-final-verify.log`
- `logs/ci/2026-11-26/story-4-8-step4-triage.md`