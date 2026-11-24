---
title: 'Story 3.10：按缺陷类型复用规划或返回定义所属阶段'
type: 'feature'
created: '2026-11-24'
status: 'done'
baseline_commit: '9588165429c289baac28a1840909230cd8e1bbc9'
story_key: '3-10-按缺陷类型复用规划或返回定义所属阶段'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-3-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Chapter 6 修复缺纯实现缺陷与定义变更边界，易盲跑 3A/3B、创同义任务，或借弱化验收、N/A、改状态、删测伪装局部修复。
**Approach:** 交付 _b_route_defect_routing.py 与 b-route-defect-routing，接入 Chapter 6 执行/恢复/路由及 3.1/3.2 交接，不自动重跑上游或增同义任务。

## Boundaries & Constraints

**Always:** 区分纯实现缺陷与定义/契约/所有权/交接/绑定/义务变更并产六字段 Diagnostic 依据；纯实现缺陷引有效 3B 采纳与 Task/Flow 身份，经 3.8/3.9 门禁、Task 映射、有效 readiness、自检与适用回归进修复，免重跑 3A/3B 且不省 readiness 或回归；涉定义、契约、状态所有权、交接/绑定或义务时拒伪装并返 owning stage(3A..5)交治理承接，禁弱化 Acceptance、自由 N/A、越权改 status 或删/关测试；需新 Task 或更新既有 Task 时仅产业务 delta 交 3.1 preview 与 3.2 compile 治理，只接真实新增责任，保旧 ID/done/历史与累计 manifest 及 Task<->Flow 关系，禁同义重复任务，禁旧 done 抵新义务，来源或定义变触发绑定与 readiness 重验；遇复现、无关变或上游有效时复用成果并保 3.9 预算/历史与复现定位，禁借重复候选或刷 Knowledge 掩盖失败，局部不充 Flow/累计完成；报告区分局部 PASS、运行与人工义务，未完保 pending/blocked，守 Needs Fix、P1 底线与防削弱，记耗时/调用/复用/返工，runtime_verified 与 default_b_enabled 恒 false。
**Ask First:** 改 7 FORMAL、扩 ReasonCode/Stage、自动重跑 3A/3B 或启付费 API。
**Never:** 弱化验收/标 N/A/删测伪装；创同义 Task 或直写 tasks.json；清预算/刷 Knowledge 掩盖复现；局部充 Flow/累计完成。

## I/O & Edge-Case Matrix

| Scenario | Input | Expected | Error |
|---|---|---|---|
| IMPL_REUSE | 纯实现缺陷，定义/契约/绑定/义务未变 | 引采纳与 Task/Flow，过 readiness 与回归修复，免重跑 3A/3B | 省 readiness/回归或盲跑 3A/3B 阻断 |
| DEF_RETURN | 涉定义、契约、所有权、交接/绑定或义务 | 拒伪装，返 owning stage(3A..5)产治理交接 | 弱化验收、N/A、改状态或删测阻断 |
| DELTA_GOV | 真实缺口需新 Task 或更新既有 Task | 产业务 delta 交 3.1/3.2，保旧 ID/done/manifest，重验受影响项 | 同义任务、直写三联或旧 done 遮新义务阻断 |
| RECUR_BUDGET | 缺陷复现或无关变，上游仍有效 | 复用上游，保预算/历史并定位复现与返回阶段 | 重复生成候选、刷 Knowledge 或充 Flow 完成阻断 |
| REPORT_FLOOR | 修复局部完成或仍被阻断 | 分局部 PASS/运行/人工义务，未完保 pending/blocked，守 P1 记指标 | 降 P1、关测试或谎报 runtime_verified 阻断 |

</frozen-after-approval>

## Code Map

- _b_route_chapter6_gate.py:1, _b_route_chapter6_recovery.py:1 -- 3.8/3.9 门禁与持久预算
- _b_route_task_preview.py:1, compile_b_route_tasks.py:1 -- 3.1/3.2 去重与治理三联
- run_single_task_chapter6_lane.py:880, resume_task.py:464, chapter6_route.py:293 -- 修复交接消费者
- dev_cli.py:920, dev_cli_builders.py:1 -- b-route-defect-routing CLI
- update_mvg_baseline.py:1, _b_route_protection.py:1 -- 防削弱核对

## Tasks & Acceptance

**Execution:**
- [x] scripts/python/_b_route_defect_routing.py, check_b_route_defect_routing.py -- 分类、反伪装、delta 校验、复现定位与报告
- [x] scripts/python: dev_cli.py, dev_cli_builders.py, run_single_task_chapter6_lane.py, resume_task.py, chapter6_route.py -- CLI 与交接接入
- [x] docs/workflows/b-route-defect-routing.md, AGENTS.md, stable-public-entrypoints.md, script-entrypoints-index.md -- 文档对齐
- [x] scripts/python/tests/test_b_route_defect_routing.py, test_b_route_runtime_ci.py, run_gate_bundle.py, b-route-runtime-deterministic.yml -- 单测与 CI

**Acceptance Criteria:**
- Given 纯实现缺陷且定义/契约/义务未变，when 判修复范围，then 复用采纳与 Task/Flow 经 readiness 和回归修复，免重跑 3A/3B 并留依据。
- Given 涉定义变更、治理 delta、复现或汇报，when 交接或收口，then 返 3A..5 或走 3.1/3.2 保旧资产禁伪装/同义，保预算/P1 并区分局部与运行/人工义务。

## Spec Change Log

## Verification

- `py -3 -B -m unittest scripts.python.tests.test_b_route_defect_routing scripts.python.tests.test_b_route_runtime_ci -v`
- `py -3 -B scripts/python/dev_cli.py b-route-defect-routing --help`

## Suggested Review Order

**缺陷分类、反伪装与治理报告核心**

- 缺陷分类总入口，先检反伪装与策略底线再分流纯实现复用或返 3A..5
  [_b_route_defect_routing.py:1827](../../../scripts/python/_b_route_defect_routing.py#L1827)

- 拦截双视图验收弱化、N/A、越权改 done、删测、跳测与 MVG 基线削弱
  [_b_route_defect_routing.py:698](../../../scripts/python/_b_route_defect_routing.py#L698)

- 零写校验业务增量 delta，阻断同义任务、直写三联与旧 done 遮新义务
  [_b_route_defect_routing.py:1089](../../../scripts/python/_b_route_defect_routing.py#L1089)

- 消费跨日期持久信号定位复现、保留预算并产出紧凑交接摘要
  [_b_route_defect_routing.py:2578](../../../scripts/python/_b_route_defect_routing.py#L2578)

**公共 CLI 与 Chapter 6 消费者接入**

- 独立只读 CLI 与可选新日志落盘封装，默认零写入且严守路径包含
  [check_b_route_defect_routing.py:81](../../../scripts/python/check_b_route_defect_routing.py#L81)

- 注册 `b-route-defect-routing` 公共子命令与参数构造器
  [dev_cli.py:869](../../../scripts/python/dev_cli.py#L869)

- 恢复与路由入口优先阻断伪装定义变更并返回归属阶段，禁写债务台账
  [resume_task.py:717](../../../scripts/python/resume_task.py#L717)

- 路由阻断分支识别伪装变更并输出 `return-to-owning-stage` 紧凑三字段
  [chapter6_route.py:258](../../../scripts/python/chapter6_route.py#L258)

- 单任务编排入口在门禁前后同步 fail-closed 拦截伪装变更
  [run_single_task_chapter6_lane.py:953](../../../scripts/python/run_single_task_chapter6_lane.py#L953)

- 审查流水线各恢复、分叉与新跑分支前置拦截伪装定义变更，拒绝执行步骤
  [run_review_pipeline.py:1855](../../../scripts/sc/run_review_pipeline.py#L1855)

- 6.8 快速修复入口复核缺陷路由，阻断定义变更伪装局部修复
  [llm_review_needs_fix_fast.py:1549](../../../scripts/sc/llm_review_needs_fix_fast.py#L1549)

**单测、CI 与治理文档**

- 覆盖矩阵五场景与 P-01 至 P-06 端到端回归的缓存固件测试集
  [test_b_route_defect_routing.py:65](../../../scripts/python/tests/test_b_route_defect_routing.py#L65)

- 确定性门禁包、CI 触发路径与自检测试显式纳管缺陷路由模块
  [run_gate_bundle.py:177](../../../scripts/python/run_gate_bundle.py#L177)

- 缺陷分类与归属阶段路由 owner 文档、边界约束与交接协议说明
  [b-route-defect-routing.md:1](../../../docs/workflows/b-route-defect-routing.md#L1)
