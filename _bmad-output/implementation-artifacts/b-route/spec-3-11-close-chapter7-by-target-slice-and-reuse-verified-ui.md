---
title: 'Story 3.11：按目标slice收口Chapter7并复用已验证UI'
type: 'feature'
created: '2026-11-24'
status: 'done'
baseline_commit: '115dab29bde5ad2559758ac6c96bc61600b73419'
story_key: '3-11-按目标slice收口chapter7并复用已验证ui'
review_loop_iteration: 1
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-3-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Chapter 7 默认扫全局完成任务，未消费 B 路线目标 Flow/slice 声明的 UI 责任与匹配当前 InputSet 的 Chapter 6 证据，易等全游、生同义任务或拿静态接线充运行输入。
**Approach:** 交付 _b_route_chapter7_slice.py 与 b-route-chapter7-slice，适配 run_chapter7_ui_wiring、run_chapter7_backlog_gap 及状态补丁，不建新 UI 框架。

## Boundaries & Constraints

**Always:** 按目标 Flow/slice 核对声明的入口/返回、真实输入、反馈、四部分绑定与人工义务，免等全游；有效非 UI 依据返 not_applicable，禁凭缺字段跳实际 UI；匹配当前 InputSet 与测试身份的 Chapter 6 UI 证据复用实现与义务并保 Task/Flow 身份及证据定位，禁生同义 Task/义务，过期、异条件、纯静态接线或纯方法调用不充真实引擎输入；关键绑定断开、类型/生命周期不符或证据空/跳过/未执行时标失败或保 pending 定位，禁拿 planned/连线充运行通过，人工视觉/手感独立保留，局部 UI 收口不充 Flow 全完成；UI 缺口涉定义返 3A..5，涉任务走 3.1/3.2 审阅/编译，状态补丁守 Taskmaster 权威与共享锁，保成熟状态/历史及原生 .tscn 人工区，禁直写三联新义务或清旧 done；存目标 slice 证据与交接，分列已验/待跑/人工/阻断且全引用回溯绑定/原证，保后续 Flow/累计收尾责任，对齐 CLI/Skill/profile 文档，禁刷全局 Knowledge，default_b_enabled 恒 false。
**Ask First:** 改 7 FORMAL、扩 ReasonCode/Stage、新建 UI 框架/重做视觉或启付费 API。
**Never:** 等全游收口；静态接线/planned 充真实输入；生同义 Task 或清旧 done；刷全局 Knowledge 或冒充 Flow 全完成。

## I/O & Edge-Case Matrix

| Scenario | Input | Expected | Error |
|---|---|---|---|
| SLICE_SCOPE | 目标 Flow/slice 声明 UI vs 合法无 UI | 仅核该 slice 入口/输入/反馈/绑定/人工；无 UI 返不适用 | 等全游或凭缺字段跳 UI 阻断 |
| EVIDENCE_REUSE | Chapter 6 证据匹配 InputSet vs 过期/静态 | 复用匹配证据保身份；拒过期/异条件/纯静态充输入 | 生同义 Task 或静态充输入阻断 |
| HONEST_WIRING | 绑定断开、类型/生命周期不符或空/跳过 | 失败或保 pending 定位，保人工义务，局部不充 Flow 全完成 | planned/连线充通过或抹人工阻断 |
| GOV_GAP_PATCH | UI 定义缺口、任务缺口或状态补丁 | 定义返 3A..5，任务走 3.1/3.2，补丁守锁保旧 done 与 .tscn | 直写三联、覆人工区或清旧 done 阻断 |
| HANDOFF_NOKCP | 生成目标 slice 报告与交接 | 列已验/待跑/人工/阻断回溯绑定与原证，零刷 Knowledge | 断链引用、丢累计责任或刷 Knowledge 阻断 |

</frozen-after-approval>

## Code Map

- run_chapter7_ui_wiring.py:1, run_chapter7_backlog_gap.py:1, apply_chapter7_status_patch.py:50 -- Chapter 7 管线
- _chapter7_profile.py:1, docs/workflows/chapter7-profile.json:1 -- slice 配置
- _b_route_chapter6_gate.py:1, _b_route_defect_routing.py:1 -- InputSet 与缺口归因
- _b_route_task_preview.py:1, compile_b_route_tasks.py:1 -- 3.1/3.2 治理补缺
- .agents/skills/workflow-chapter7-ui-wiring-closure/SKILL.md:1 -- Chapter 7 Skill

## Tasks & Acceptance

**Execution:**
- [x] scripts/python/_b_route_chapter7_slice.py, check_b_route_chapter7_slice.py -- 目标 slice 收口、证据匹配、接线核对与零刷 Knowledge 交接
- [x] scripts/python: run_chapter7_ui_wiring.py, run_chapter7_backlog_gap.py, apply_chapter7_status_patch.py, dev_cli.py, dev_cli_builders.py -- slice 参数与保护
- [x] .agents/skills/workflow-chapter7-ui-wiring-closure/SKILL.md, docs/workflows/b-route-chapter7-slice.md, AGENTS.md, stable-public-entrypoints.md, script-entrypoints-index.md -- 文档对齐
- [x] scripts/python/tests/test_b_route_chapter7_slice.py, test_b_route_runtime_ci.py, run_gate_bundle.py, b-route-runtime-deterministic.yml -- 单测与 CI

**Acceptance Criteria:**
- Given 目标 Flow/slice 声明 UI 或合法无 UI 且有 Chapter 6 证据，when 跑目标 slice 收口，then 仅核该 slice 并复用匹配真证据，禁等全游、生同义任务或拿静态充输入。
- Given 断链/空跳过证据或真实缺口，when 核对与补缺，then 保 pending/失败与人工义务，返 3A..5 或走 3.1/3.2 保旧 done 与原生场景，产回溯交接且零刷 Knowledge。

## Spec Change Log

## Verification

- `py -3 -B -m unittest scripts.python.tests.test_b_route_chapter7_slice scripts.python.tests.test_chapter7_ui_wiring scripts.python.tests.test_chapter7_backlog_gap scripts.python.tests.test_b_route_defect_routing scripts.python.tests.test_b_route_runtime_ci -v`
- `py -3 -B scripts/python/dev_cli.py b-route-chapter7-slice --help`

## Suggested Review Order

**目标 Slice 收口核心、证据复用与接线核对**

- 按目标 Flow/slice 评估实时 3.8 门禁与声明 UI 义务、合法非 UI 证明校验、3A..5 缺口路由与 3.1/3.2 受治理变更草案生成
  [_b_route_chapter7_slice.py:2424](../../../scripts/python/_b_route_chapter7_slice.py#L2424)
  [_b_route_chapter7_slice.py:2279](../../../scripts/python/_b_route_chapter7_slice.py#L2279)

- 严格匹配当前 InputSet 与测试 SHA-256 的 Chapter 6 真实引擎输入证据复用，拦截静态接线、纯方法调用与失败运行证据
  [_b_route_chapter7_slice.py:1721](../../../scripts/python/_b_route_chapter7_slice.py#L1721)

- 递归解析 `.tscn` 实例与 `.cs`/`.gd` 适配器节点绑定、类型继承兼容、生命周期及原生场景人工区哈希保护，排他写入可选报告
  [_b_route_chapter7_slice.py:1078](../../../scripts/python/_b_route_chapter7_slice.py#L1078)
  [_b_route_chapter7_slice.py:736](../../../scripts/python/_b_route_chapter7_slice.py#L736)
  [_b_route_chapter7_slice.py:4211](../../../scripts/python/_b_route_chapter7_slice.py#L4211)

**公共 CLI 与 Chapter 7 管线适配**

- 只读目标 slice 收口 CLI 参数校验、阻断载荷与退出码契约
  [check_b_route_chapter7_slice.py:33](../../../scripts/python/check_b_route_chapter7_slice.py#L33)
  [check_b_route_chapter7_slice.py:155](../../../scripts/python/check_b_route_chapter7_slice.py#L155)

- `dev_cli` 直通分发、`b-route-chapter7-slice` 子命令注册与 Chapter 7 slice/flow 参数透传
  [dev_cli.py:70](../../../scripts/python/dev_cli.py#L70)
  [dev_cli.py:816](../../../scripts/python/dev_cli.py#L816)
  [dev_cli.py:886](../../../scripts/python/dev_cli.py#L886)

- Chapter 7 UI 编排多 slice 聚合收口、禁止回退全游扫描、`--create-tasks` 受治理阻断草案与 `artifact-manifest.json` 校验
  [run_chapter7_ui_wiring.py:540](../../../scripts/python/run_chapter7_ui_wiring.py#L540)
  [run_chapter7_ui_wiring.py:552](../../../scripts/python/run_chapter7_ui_wiring.py#L552)
  [run_chapter7_ui_wiring.py:664](../../../scripts/python/run_chapter7_ui_wiring.py#L664)

- Backlog 缺口分析按目标 slice/Flow 过滤并复用已验证 B 路线 UI 义务防止生成同义任务
  [run_chapter7_backlog_gap.py:310](../../../scripts/python/run_chapter7_backlog_gap.py#L310)
  [run_chapter7_backlog_gap.py:334](../../../scripts/python/run_chapter7_backlog_gap.py#L334)

- 状态补丁在业务 scope 租约内跨三联全视图校验并禁止清除成熟 `done` 状态
  [apply_chapter7_status_patch.py:84](../../../scripts/python/apply_chapter7_status_patch.py#L84)
  [apply_chapter7_status_patch.py:118](../../../scripts/python/apply_chapter7_status_patch.py#L118)

**确定性测试、CI 门禁与治理文档**

- 覆盖矩阵五场景与 `P-01`..`P-08` 实时门禁回归单测集
  [test_b_route_chapter7_slice.py:330](../../../scripts/python/tests/test_b_route_chapter7_slice.py#L330)

- Backlog 缺口 slice 过滤、锚点覆盖复用与阻断不误抑单测集
  [test_chapter7_backlog_gap.py:37](../../../scripts/python/tests/test_chapter7_backlog_gap.py#L37)

- 确定性 B 路线运行门禁清单纳管目标 slice 与 backlog-gap 单测
  [run_gate_bundle.py:178](../../../scripts/python/run_gate_bundle.py#L178)

- 目标 slice Chapter 7 收口 owner 边界、零写保证与五项收口契约说明
  [b-route-chapter7-slice.md:1](../../../docs/workflows/b-route-chapter7-slice.md#L1)
