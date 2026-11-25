---
title: 'Story 3.12：让页面实施触发与全入口决定保持一致'
type: 'feature'
created: '2026-11-24'
status: 'done'
baseline_commit: 'beb3c22972bf1948b5a56d597088aae5afca52d2'
story_key: '3-12-让页面实施触发与全入口决定保持一致'
review_loop_iteration: 1
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-3-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 页面实施与运行时触发读取扫描快照而未统一消费 B 路线实施/恢复门禁与动态 InputSet，缺少跨五入口一致性校验及 Epic3 对 Epic4 的诚实交接。
**Approach:** 交付 _b_route_entrypoint_parity.py 与 b-route-entrypoint-parity，打通 _project_health_http.py 与 project_health_runtime.py 复用同一门禁/恢复服务并完成全入口验收与 Epic3 交接，不建 Epic4 进度页或选择性 runner。

## Boundaries & Constraints

**Always:** 页面请求实施/恢复/路由 B Task 时复用与 CLI/direct/resume/route 相同的 gate、当前 InputSet、资格与业务 scope 锁，禁凭摘要、缓存或旧 ready 授权，preview/workspace 禁推进 current/last-known-good/latest.json 或 main 发布身份；相同合法 Flow、合法非 Flow、纯集成 owner 或冻结 A 输入在各真实入口按同一适用差异放行或阻断，禁造 manifest/API/自 done 前置，Task 局部不充 Flow 完成，触发时核对真实 Task 与依赖状态且 default_b_enabled 恒 false；删 origin/manifest/非 Flow 理由、损 journal、断 binding 或增共享 Task 新 plan 时，五入口及底层模块均在副作用前按同一公共原因拒绝或废旧 readiness，难证 scope 保守阻断，禁把 unknown 当 legacy 并覆盖旧 pending；Windows 下完整 apply 后推进状态重放为 no-op 保新状态，未完并发/后编辑严查 raw 前像冲突停，保投影校验与无关变化复用，共享扩集取全锁，相关 pending 未消歧仍阻断且删 marker 不放行；Epic3->Epic4 交接对齐消费者与 CLI/Skill/AGENTS/owning 文档，诚实列未实现的范围接口、完整 Knowledge 展示与奖励试点，禁冒充全迁移或 full-MVG。
**Ask First:** 改 7 FORMAL、扩 ReasonCode/Stage、提前开发 Epic4 选择性 runner/完整进度 UI 或启付费 API。
**Never:** 页面缓存/旧 ready 授权；preview 推进发布指针；unknown 当 legacy；回写新状态或删 marker 绕过阻断；冒充全迁移或 full-MVG。

## I/O & Edge-Case Matrix

| Scenario | Input | Expected | Error |
|---|---|---|---|
| PAGE_SHARED_GATE | 页面触发实施/恢复/路由或 workspace 预览 | 复用同一 gate/InputSet/资格/scope 锁；preview 零推进发布 | 凭摘要/缓存/旧 ready 放行或推进发布阻断 |
| PARITY_APPLICABLE | 合法 Flow/非 Flow/纯集成 owner/冻结 A 经五入口 | 五入口决定与副作用边界一致；局部不充 Flow 完成 | 造 manifest/API/自 done 前置或启默认 B 阻断 |
| TAMPER_BEFORE_FX | 删 origin/manifest/理由、损 journal、断 binding、新 plan | 全公私入口在副作用前按同一公共原因拒绝或废旧 readiness | 漏底层入口、unknown 当 legacy 或漏旧 pending 阻断 |
| WIN_CONCURRENCY | 完整 apply 后推进 vs 未完并发/后编辑/扩集/删 marker | 完整 no-op 保新状态；未完查前像冲突停；扩集取全锁 | 回写旧状态、无关变更误废或删 marker 绕过阻断 |
| EPIC3_HANDOFF | 汇总 Epic3 交付交接 Epic4 | 对齐 CLI/Skill/文档与实测事件，列未实现 Epic4/5 项 | 关系图/样本冒充全迁移或累计 full-MVG 阻断 |

</frozen-after-approval>

## Code Map

- _project_health_http.py:110, project_health_runtime.py:190 -- 页面与运行时边界
- _b_route_chapter6_gate.py:1, _b_route_chapter6_recovery.py:1 -- 门禁、恢复与 scope 锁
- _b_route_defect_routing.py:1, _b_route_chapter7_slice.py:1 -- 缺陷路由与 slice 收口
- compile_b_route_tasks.py:1, _b_route_chapter4_binding.py:1 -- journal 前像与完成保护
- docs/workflows/project-health-knowledge.md:1 -- 页面与发布指针契约

## Tasks & Acceptance

**Execution:**
- [x] scripts/python/_b_route_entrypoint_parity.py, check_b_route_entrypoint_parity.py -- 页面服务、五入口矩阵、并发状态核验与 Epic3->Epic4 交接
- [x] scripts/python: _project_health_http.py, project_health_runtime.py, dev_cli.py, dev_cli_builders.py -- 页面 /api/knowledge/b-route 与 runtime/mvg 接入门禁及零推进保护
- [x] docs/workflows/b-route-entrypoint-parity.md, project-health-knowledge.md, AGENTS.md, stable-public-entrypoints.md, script-entrypoints-index.md, .agents/skills/workflow-chapter6-single-task-daily-loop/SKILL.md -- 文档对齐
- [x] scripts/python/tests/test_b_route_entrypoint_parity.py, test_b_route_runtime_ci.py, run_gate_bundle.py, b-route-runtime-deterministic.yml -- 单测与 CI

**Acceptance Criteria:**
- Given 页面或 CLI/direct/resume/route 请求实施、恢复或路由，when 对比合法四类输入与六类篡改反例，then 全公私入口共用 gate/InputSet/锁在副作用前一致决定且 preview 零推进发布。
- Given Windows 状态推进/未完并发及 Epic3 收尾，when 核验恢复与交接，then 保新状态 no-op、未完查前像阻断、扩集取全锁，对齐文档并诚实列未实现 Epic4/5 能力。

## Spec Change Log

- Step 4 (`review_loop_iteration: 1`): 合入去重补丁 `P-01`..`P-08`（归档 `logs/ci/2026-11-24/story-3-12-step4-triage.md`）：打通运行时/MVG 可重入业务 scope 租约与 `latest.json` 前置门禁；补齐 `project_health_runtime.py` 实时三联、`task-origins.v1.json` 与 `Tests.Godot/` 扫描；在 `handle_page_b_route_trigger` 租约内复验持久止损与反伪装缺陷路由并严格校验布尔/重复键输入；统一跨跳依赖资格与重叠作用域未完 journal 门禁；接入真实 `_b_route_commit.recover` / `resume_journal` 完成重放 no-op 与未完前像冲突核验；动态校验 Epic3 消费者/CLI/文档锚点与报告路径规范；完成 8 组回归套件全绿终验（`logs/ci/2026-11-24/story-3-12-final-verify.log`）。

## Verification

- `py -3 -B -m unittest scripts.python.tests.test_b_route_entrypoint_parity scripts.python.tests.test_b_route_chapter6_recovery scripts.python.tests.test_b_route_chapter6_gate scripts.sc.tests.test_project_health_server scripts.sc.tests.test_project_health_runtime_snapshot scripts.python.tests.test_b_route_runtime_ci -v`
- `py -3 -B -m unittest scripts.python.tests.test_b_route_3b_70k_segmented.TrackBSegmented70kTests.test_01_story25_ast_and_semantic_lock_guard -v`
- `py -3 -B scripts/python/dev_cli.py b-route-entrypoint-parity --help`

## Suggested Review Order

**页面与运行时共享门禁、五入口一致性与 Epic3 交接核心**

- 页面触发服务 `handle_page_b_route_trigger`、实时 3.8/3.9/3.10 门禁与持久止损复验、业务 scope 租约重验与发布指针零推进保护
  [_b_route_entrypoint_parity.py:467](../../../scripts/python/_b_route_entrypoint_parity.py#L467)
  [_b_route_entrypoint_parity.py:822](../../../scripts/python/_b_route_entrypoint_parity.py#L822)
  [_b_route_entrypoint_parity.py:1054](../../../scripts/python/_b_route_entrypoint_parity.py#L1054)

- 运行时与 MVG 清单前置门禁（`latest.json` 读取与快照构建前实时拦截篡改、未决 journal 与未知 origin）
  [_b_route_entrypoint_parity.py:1567](../../../scripts/python/_b_route_entrypoint_parity.py#L1567)
  [_b_route_entrypoint_parity.py:1962](../../../scripts/python/_b_route_entrypoint_parity.py#L1962)

- 跨 `cli`/`direct`/`resume`/`route`/`page` 五入口真实调用与归一化决策一致性核验
  [_b_route_entrypoint_parity.py:2547](../../../scripts/python/_b_route_entrypoint_parity.py#L2547)

- Windows 完成操作重放保新状态 no-op、未完操作原始字节前像冲突阻断、共享任务多计划联合作用域锁与 Epic3->Epic4 诚实交接汇总
  [_b_route_entrypoint_parity.py:2848](../../../scripts/python/_b_route_entrypoint_parity.py#L2848)
  [_b_route_entrypoint_parity.py:2987](../../../scripts/python/_b_route_entrypoint_parity.py#L2987)
  [_b_route_entrypoint_parity.py:3374](../../../scripts/python/_b_route_entrypoint_parity.py#L3374)
  [_b_route_entrypoint_parity.py:3584](../../../scripts/python/_b_route_entrypoint_parity.py#L3584)

**HTTP 服务端、运行时执行器、公共 CLI 与底层恢复/门禁协同**

- `POST /api/knowledge/b-route`、`/api/knowledge/runtime` 与 `/api/knowledge/mvg-run` 严格 JSON 解析、前置门禁与 scope 租约接线
  [_project_health_http.py:45](../../../scripts/python/_project_health_http.py#L45)
  [_project_health_http.py:342](../../../scripts/python/_project_health_http.py#L342)

- 运行时执行器实时读取三联、`task-origins.v1.json` 与 `Tests.Godot/`，并在快照/引擎启动前执行 B 路线门禁与租约保护
  [project_health_runtime.py:143](../../../scripts/python/project_health_runtime.py#L143)
  [project_health_runtime.py:378](../../../scripts/python/project_health_runtime.py#L378)

- 只读五入口一致性与 Epic3 交接 CLI 参数规范校验、排他报告路径防冲突及 `dev_cli` 直通注册
  [check_b_route_entrypoint_parity.py:34](../../../scripts/python/check_b_route_entrypoint_parity.py#L34)
  [check_b_route_entrypoint_parity.py:98](../../../scripts/python/check_b_route_entrypoint_parity.py#L98)
  [dev_cli.py:74](../../../scripts/python/dev_cli.py#L74)
  [dev_cli.py:903](../../../scripts/python/dev_cli.py#L903)

- 跨跳传递依赖资格重算、重叠作用域未完 journal 检查与受阻返回 `plan_refs`/`binding_refs` 透传
  [_b_route_chapter6_recovery.py:404](../../../scripts/python/_b_route_chapter6_recovery.py#L404)
  [_b_route_chapter6_recovery.py:891](../../../scripts/python/_b_route_chapter6_recovery.py#L891)
  [_b_route_chapter6_gate.py:718](../../../scripts/python/_b_route_chapter6_gate.py#L718)

**确定性测试、CI 门禁与治理文档**

- 覆盖矩阵五场景、环回 HTTP 三端点、跨进程 Windows `msvcrt` 锁争用与 Epic3->Epic4 交接负向控制单测集
  [test_b_route_entrypoint_parity.py:318](../../../scripts/python/tests/test_b_route_entrypoint_parity.py#L318)

- 确定性 B 路线运行门禁清单纳管全入口一致性单测
  [run_gate_bundle.py:179](../../../scripts/python/run_gate_bundle.py#L179)

- 页面触发、五入口一致性与 Epic3->Epic4 交接 owner 边界与零写契约说明
  [b-route-entrypoint-parity.md:1](../../../docs/workflows/b-route-entrypoint-parity.md#L1)
