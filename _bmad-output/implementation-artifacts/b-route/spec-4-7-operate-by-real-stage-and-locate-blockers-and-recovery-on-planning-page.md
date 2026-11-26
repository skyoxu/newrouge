---
title: 'Story 4.7：在规划页面按真实阶段操作并定位阻塞与恢复'
type: 'feature'
created: '2026-11-26'
status: 'done'
review_loop_iteration: 1
baseline_commit: '3730f61f0d46a2ca6569fa19266f4379fc78f926'
story_key: '4-7-在规划页面按真实阶段操作并定位阻塞与恢复'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-4-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 规划页面默认把前置规划锁在后置 Task/Chapter 5 readiness 之后，尚未按 B 路线真实阶段（无 Task 3A/3B、3C 与 Ch6）门控按钮、区分新建与保预算恢复，并原样展示公共六字段诊断。
**Approach:** 新增 `_b_route_planning_page.py`、`b-route-planning-page` 与 `/api/knowledge/b-route-planning`，消费已实现 3A/3B/3C/3.12 服务与 4.6 派生投影，适配 `project_health_planning.js`、`project_health_topology*`、`project_health_scenes.html`、`project_health_mvg_versions.js` 与 `project_health_knowledge.js`，保视觉布局与旧 A 按钮兼容，不造第二状态机。

## Boundaries & Constraints

**Always:** 无 Task/readiness 且来源适用时，页面触发 3A 或 3B 直调 Task 无关正式入口，阶段名/输入/输出与 CLI 一致，禁走 `draft`/`allow_unready` 旁路，3C 与 Ch6 动作仅前置满足才可执行；消费协调器、checkpoint、epoch 与 `catalog.v1.json` 展示当前阶段、已完成范围、阻塞原因与 `resume_ref`，候选中间态禁作已采纳，`partial_planning` 禁作 `planning_complete` 或 runtime PASS，禁读旧撤销填绿，新建创全新 run，`resume` 选现有可恢复 run 且不重置预算；展示公共服务同一 `reason_code`/`stage`/`entity`/`expected`/`actual`/`resume_ref` 与原始定位，区分只读推荐（`recommendation_only`）与执行，禁凭摘要造权限或恢复指令，实施走 3.12 门禁并按适用区分旧 A、B 与合法非 Flow；`workspace`/`attempt`/`stable`/`main` 身份与 4.6 一致，预览零写 canonical 指针，恢复/实施零隐式全局 refresh，禁自由切 Task 来源或删 B 标识；页面、CLI 与直接服务在无 Task 规划、缺依据、未知版本、非 Flow、pending/budget 上决定一致，自动化页面测试只证交互合同、禁充 Godot 玩法或奖励试点证据。
**Ask First:** 改 7 FORMAL、扩 `ReasonCode`/`Stage`、建新控制面或启付费 API。
**Never:** 缺 readiness 禁 3A/3B 或走 `allow_unready`；候选/`partial_planning` 充已采纳/完成或重置预算；凭摘要造指令；改切 Task 来源或删 B 标识；UI 测试充引擎玩法证据。

## I/O & Edge-Case Matrix

| Scenario | Input | Expected | Error |
|---|---|---|---|
| STAGE_3AB | 无 Task/readiness 但来源适用，点 3A/3B 或未就绪 3C/Ch6 | 3A/3B 调无 Task 正式入口；3C/Ch6 仅前置满足可点 | 缺 readiness 禁 3A/3B 或走 `allow_unready` 阻断 |
| PREFIX_RESUME | 已提交前缀、候选进行中、预算耗尽、新建 vs `resume` | 显 `partial_planning` 与 `resume_ref`；新建新 run，`resume` 保预算 | 候选充采纳、读旧撤销填绿或重置预算阻断 |
| DIAG_RECOVERY | 查看失败/可恢复操作，触发推荐 vs 恢复/实施 | 原样六字段诊断与定位；区分推荐/执行；实施走 3.12 门禁 | 凭摘要造指令或绕 3.12 门禁阻断 |
| IDENTITY_GUARD | `workspace`/`attempt` 预览或 `stable`/`main` 操作 | 与 4.6 身份一致；零写发布指针；零隐式全局 refresh | 预览写指针、隐式刷 Knowledge 或删切 B 标识阻断 |
| PARITY_HONESTY | 页面/CLI/直接服务面对无 Task、缺依据、未知版本、非 Flow、pending/budget | 三端决定、六字段诊断与可恢复态一致；诚实标交互合同 | 三端分歧或把 UI 测试称作 Godot 玩法证据阻断 |

</frozen-after-approval>

## Code Map

- `_b_route_planning_page.py`, `query_b_route_planning_page.py`, `_project_health_http.py`, `project_health_planning.js`, `project_health_topology*`, `project_health_mvg_versions.js`, `project_health_knowledge.js`

## Tasks & Acceptance

- [x] `_b_route_planning_page.py`, `query_b_route_planning_page.py`, `dev_cli*.py`, `_project_health_http.py`
- [x] `project_health_planning.js`, `project_health_topology*`, `project_health_scenes.html`, `project_health_mvg_versions.js`, `project_health_knowledge.js`
- [x] `test_b_route_planning_page.py`, `test_b_route_planning_page_ui.cjs`, `test_topology_frontend.py`, `run_gate_bundle.py`, `b-route-runtime-deterministic.yml`, `test_b_route_runtime_ci.py`, `docs/workflows/**`, `AGENTS.md`

**AC:** 无 Task 3A/3B 按真实阶段可执行且 3C/Ch6 受真实门控，显前缀与候选边界，`resume` 保预算，原样六字段诊断并区分推荐/执行，与 4.6 身份一致且三端对等。

## Spec Change Log
- `P-01`..`P-05`（`story-4-7-step4-triage.md`）

## Suggested Review Order
- `_b_route_planning_page.py`, `_project_health_http.py`, `project_health_*.js`, `test_b_route_planning_page*`

## Verification
- logs/ci/2026-11-26/story-4-7-final-verify.log（10/10 PASS）
