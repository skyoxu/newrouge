---
title: 'Story 4.6：派生展示规划、实施与运行身份'
type: 'feature'
created: '2026-11-26'
status: 'done'
review_loop_iteration: 1
baseline_commit: '4c2b8a20f2921fda082239d8020fc7bbceac67f4'
story_key: '4-6-派生展示规划-实施与运行身份'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-4-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
  - '{project-root}/docs/adr/ADR-0035-repository-knowledge-control-plane.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Knowledge、semantic-topology 与 MVG 概览尚未投影 B 路线采纳、四部分、三类义务、传递影响与六类运行证据等级，易将结构关系、部分前缀、无 Task 3B 或工作区预览误读为正式实现、runtime PASS 或 main 事实，或在过期、pending、撤销时缺六字段诊断。
**Approach:** 新增只读 `_b_route_knowledge_projection.py` 与 `b-route-knowledge-projection` 入口，适配 `project_health_knowledge.py`、`_semantic_topology.py`、`_project_health_mvg_versions.py` 与 `_project_health_http.py`，从原始权威与提交链构建十层关系、证据回链与身份边界，保 ADR-0035 门禁与零隐式刷新。

## Boundaries & Constraints

**Always:** 从原始权威与 `catalog.v1.json` 链定位来源/Requirement/Capability/Flow/四部分/Task/契约/场景/义务/影响，显式分开计划、实现、运行与六类 `evidence_level`；关系存在不等于实现，运行结论回链 `summary.json`/`coverage-receipt.json`/`runtime/*.json` 且不刷旧时间，禁反写来源、`catalog.v1.json` 或 `tasks.json`；绑定 `workspace_preview`/`attempt`/`stable`/`stabilized`/`main` 快照、分支与提交身份，已提交前缀标 `partial_planning`，preview 零推进 `current`/`last-known-good`/`latest.json`，dirty 或非 `trusted-ref` 禁发布或充 `main`；无 Task 3B 与合法非 Flow 定位采纳/四部分及验证去向，标 `3b_adopted_awaiting_3c` 与 `planned_only`，不因缺 readiness 阻断、不造假 Task、不把 `planned` 当真文件；proof 过期、pending、epoch/reopen 撤销或漂移时显示 `stale`/`blocked`/`revoked`、公共六字段诊断及原始定位，撤销禁复活，损坏/未知禁算缺失或 PASS，`local clear` 保正式 Git 采纳、累计基线与旧审计；普通 Ch6/Review/Recovery 零隐式全局刷新，注册 Ch3/Ch5 区分 Attempt 与 Successful 且 canonical 须 `trusted-ref`，`logs/**` 仅显式回链、禁入全局检索，保导航与 `legacy_unmapped`。
**Ask First:** 改 7 FORMAL、扩 `ReasonCode`/`Stage`、改 KCP 控制面文件或启付费 API。
**Never:** 关系或 `partial_planning` 充实现/`runtime_verified`；`planned` 充真文件；preview/dirty 推指针或充 `main`；损坏算缺失/PASS；隐式刷 Knowledge 或扩 `logs/**` 入检索。

## I/O & Edge-Case Matrix

| Scenario | Input | Expected | Error |
|---|---|---|---|
| DERIVED_GRAPH | 正式 `catalog`/三联/manifest/契约/场景与回执 | 定位十层关系，分离四维状态与六类证据并回链报告 | 关系当实现、混等级或反写 `tasks.json`/`catalog` 阻断 |
| PROVENANCE | `workspace_preview`/`attempt`/`stable`/`main` 及前缀 | 绑定快照/分支身份，前缀标 `partial_planning`，零推指针 | dirty 或非 `trusted-ref` 冒充/发布 `main` 阻断 |
| NO_TASK_NONFLOW | 无 Task 正式 3B `plan` 或合法非 Flow | 定位采纳/四部分与验证去向，标 `3b_adopted_awaiting_3c` 与 `planned_only` | 缺 readiness 阻断、造假 Task 或 `planned` 当真文件阻断 |
| STALE_CLEAR | proof 过期、pending、epoch/reopen 撤销或 `clear` | 报 `stale`/`blocked`/`revoked` 与六字段诊断；保正式采纳 | 撤销复活、损坏算缺失/PASS 或删正式采纳阻断 |
| CONSUMER_LOGS | 普通 Ch6/Review/Recovery 读取与 Ch3/Ch5 刷新 | 普通消费零全局刷新；保 Attempt/Successful 与日志隔离 | 隐式全局发布、扩 `logs/**` 入全局检索或破导航阻断 |

</frozen-after-approval>

## Code Map

- 投影核心与适配器见 Tasks 首两项。

## Tasks & Acceptance

- [x] `_b_route_knowledge_projection.py`, `query_b_route_knowledge_projection.py`, `dev_cli*.py`
- [x] `project_health_knowledge.py`, `_semantic_topology.py`, `_project_health_mvg_versions.py`, `_project_health_http.py`, `_project_health_planning_http.py`
- [x] `test_b_route_knowledge_projection.py`, `run_gate_bundle.py`, `b-route-runtime-deterministic.yml`, `test_b_route_runtime_ci.py`, `docs/workflows/**`, `AGENTS.md`

**AC:** 十层派生与四维/六类证据分离，绑定快照与 `partial_planning` 保 ADR-0035，支持无 Task 3B 与非 Flow，过期/撤销报六字段诊断且 `clear` 保正式采纳，零隐式刷新且 `logs/**` 不入全局检索。

## Spec Change Log

- P-01..P-07：见 `logs/ci/2026-11-26/story-4-6-step4-triage.md`。

## Suggested Review Order

- 投影核心 → CLI/HTTP 适配 → 测试。

## Verification

- logs/ci/2026-11-26/story-4-6-final-verify.log（13/13 PASS）
