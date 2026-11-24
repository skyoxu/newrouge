---
title: 'Story 3.8：让直接Chapter6与公共CLI消费统一实施门禁'
type: 'feature'
created: '2026-11-24'
status: 'done'
baseline_commit: 'f359d87e5075866b1259f7cb019ea36615d721e8'
story_key: '3-8-让直接chapter6与公共cli消费统一实施门禁'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-3-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** CLI、直接 Chapter 6 脚本与 _mvg_obligations 未共用 B 门禁，无 trace 易返 current，换入口或删依据可旁路，缺租约、复验与写保护。
**Approach:** 交付 _b_route_chapter6_gate.py 与 b-route-chapter6-gate，在 dev_cli、run_single_task_chapter6_lane、_mvg_obligations 及直接入口接统一门禁与复验(3.9 接 resume/route)。

## Boundaries & Constraints

**Always:** 共用门禁(3.3→3.5 guarded_input_set→3.6 stage="5" 义务或非 Flow other_verification_refs→3.7 readiness)，ASCII 正整数验 task_id 且排除 schemas/** 误判；有效 B 接受 Flow(三类责任)或零影响非 Flow，不求先 done、无自锁，旧 done 含 requires_reverification 必重验；冻结 A 限 policy.frozen_a_refs 用原依据，纯 explicit_not_enabled_a 保原行为，_mvg_obligations 先过门禁禁无 trace 返 current；缺/损/旧/未知依据、删标识/manifest、N/A、改标签或调 Code Map 脚本均在调模型/写盘前阻断，返同一六字段 Diagnostic、reason_code 与 return_stage(3A..5)；守锁顺序(短 metadata→排序 scope_ids)，禁长持 writer:planning(无关并发)，父子经密钥哈希+OS 锁实测凭据重入防自锁与伪造，副作用前复验漂移或 pending 即停；状态写经短锁写 tasks.json 唯一权威并验定义投影不变(test_refs 无变零写，B 禁在 6 改 test_refs，acceptance_check 禁对 B checkout 三联)；保 TDD、自检、Needs Fix、P1 与 rerun_guard/stop-loss 及历史，定义返 3A..5，局部不跑全 MVG，局部 PASS/planned/空/跳过不升完成，禁刷 Knowledge(--skip-project-health)或改需求，记执行/复用/返工，runtime_verified/default_b_enabled 恒 false。
**Ask First:** 改 7 FORMAL、扩 ReasonCode/Stage、改 3.9 协议或启付费 API。
**Never:** 无 trace 放行；旁路；持全局锁或信未验变量；局部充 runtime_verified；重置历史或刷 Knowledge。

## I/O & Edge-Case Matrix

| Scenario | Input | Expected | Error |
|---|---|---|---|
| CLI_DIRECT | 有效 B(未 done)经 CLI 与直接入口 | 共用门禁进单 Task；冻结 A 守边界 | 无 trace 返 current 或不一致阻断 |
| BYPASS_BLK | 缺/损/旧依据、删标识/manifest、N/A 或内部脚本 | 调模型/写盘前阻断，返同一 code/stage | 退 legacy、写盘或调模型阻断 |
| SCOPE_LOCK | 业务租约，无关并发 vs InputSet/pending 变 | 无关推进，子进程验真重入；漂移前停 | 持全局锁、伪造凭据或跨漂移写阻断 |
| LOCAL_QUAL | TDD、自检、Needs Fix、P1 与局部回归 | 保闭环不跑全 MVG，局部不升完成 | 降阈值、关测试或谎报 runtime_verified 阻断 |
| STOPLOSS | 定义缺口或 rerun_guard 等止损 | 保恢复点/budget，返 3A..5，零刷 Knowledge | 重置历史、盲跑 6.7 或刷 Knowledge 阻断 |

</frozen-after-approval>

## Code Map

- _b_route_task_resolver.py:553, _b_route_input_set.py:3533 -- 3.3/3.5
- _b_route_stage5_obligations.py:710, _b_route_chapter5_readiness.py:2974 -- 3.6/3.7
- _b_route_operation_scope.py:346, _mvg_capability_checkpoint.py:399 -- 锁/OS 锁
- _mvg_obligations.py:26, run_single_task_chapter6_lane.py:878, dev_cli.py:922 -- CLI/编排
- scripts/sc: check_tdd_execution_plan, llm_generate_tests_from_acceptance_refs, build/tdd, run_review_pipeline, llm_review_needs_fix_fast, _llm_review_engine, acceptance_check, test; scripts/python: update_task_test_refs_from_acceptance_refs, apply_chapter7_status_patch, run_single_task_light_lane

## Tasks & Acceptance

**Execution:**
- [x] scripts/python/_b_route_chapter6_gate.py, check_b_route_chapter6_gate.py, dev_cli.py, dev_cli_builders.py -- 门禁、租约、状态写、事件与 CLI
- [x] scripts/python/_mvg_obligations.py, run_single_task_chapter6_lane.py -- 禁无 trace 放行、复验与禁刷 Knowledge
- [x] Code Map 脚本 -- 门禁、写保护与 TDD/P1/止损
- [x] scripts/python/tests/test_b_route_chapter6_gate.py, test_b_route_runtime_ci.py, docs/workflows/b-route-chapter6-gate.md -- 单测、CI 与文档

**Acceptance Criteria:**
- Given 有效 B(未 done)或冻结 A，when 经 CLI 或直接入口执行，then 共用门禁与租约进单 Task，_mvg_obligations 不误放行，无关并发且局部不充完成。
- Given 缺/损/旧依据、删标识/manifest、N/A、内部脚本、漂移或止损，when 实施或跨边界，then 调模型/写盘前阻断返同一 code/stage(3A..5)，保止损/budget 且零刷 Knowledge。

## Spec Change Log

## Verification

- `py -3 -B -m unittest scripts.python.tests.test_b_route_chapter6_gate scripts.python.tests.test_b_route_runtime_ci -v`
- `py -3 -B scripts/python/dev_cli.py b-route-chapter6-gate --help`

## Suggested Review Order

**统一门禁核心与业务租约重入**

- 统一评估 3.3 至 3.7 门禁链并输出六字段阻断诊断
  [_b_route_chapter6_gate.py:1359](../../../scripts/python/_b_route_chapter6_gate.py#L1359)

- 父子凭据验真与排序业务 scope 租约，副作用前复验防漂移
  [_b_route_chapter6_gate.py:1964](../../../scripts/python/_b_route_chapter6_gate.py#L1964)

- 短锁写 tasks.json 唯一状态权威并守定义投影与 test_refs 边界
  [_b_route_chapter6_gate.py:2343](../../../scripts/python/_b_route_chapter6_gate.py#L2343)

- 公共只读门禁 CLI 入口，拒绝写盘参数并输出统一诊断
  [check_b_route_chapter6_gate.py:77](../../../scripts/python/check_b_route_chapter6_gate.py#L77)

**公共 CLI、主编排与 MVG 义务防旁路**

- 公共 dev_cli 接入只读门禁直通与单任务执行前置门禁
  [dev_cli.py:326](../../../scripts/python/dev_cli.py#L326)

- 禁止 _mvg_obligations 无 trace 返 current，强制先过统一门禁
  [_mvg_obligations.py:77](../../../scripts/python/_mvg_obligations.py#L77)

- Chapter 6 主编排在租约保护下运行并禁隐式刷新 Knowledge
  [run_single_task_chapter6_lane.py:880](../../../scripts/python/run_single_task_chapter6_lane.py#L880)

- 排除静态 schemas 误判 B 轨迹并注册策略观测点
  [_b_route_task_resolver.py:1692](../../../scripts/python/_b_route_task_resolver.py#L1692)

**直接执行与写保护脚本收口**

- TDD、单测生成与局部测试入口接入严格 task_id 校验与门禁复验
  [tdd.py:782](../../../scripts/sc/build/tdd.py#L782)

- 自检与验收入口阻断旁路并禁对 B 仓库 checkout 三联
  [acceptance_check.py:69](../../../scripts/sc/acceptance_check.py#L69)

- test_refs、状态补丁、轻量车道与 Knowledge 入口补齐门禁保护
  [update_task_test_refs_from_acceptance_refs.py:125](../../../scripts/python/update_task_test_refs_from_acceptance_refs.py#L125)

- 评审管道与 Needs Fix 编排在调模型及落盘前接入统一门禁
  [run_review_pipeline.py:1855](../../../scripts/sc/run_review_pipeline.py#L1855)

**测试、CI 与治理文档**

- 覆盖 P-01 至 P-07 全场景门禁、租约、防旁路与止损单测
  [test_b_route_chapter6_gate.py:482](../../../scripts/python/tests/test_b_route_chapter6_gate.py#L482)

- 纳入确定性 CI 门禁清单并校验公共入口与策略一致性
  [test_b_route_runtime_ci.py:254](../../../scripts/python/tests/test_b_route_runtime_ci.py#L254)

- 定义统一 Chapter 6 实施门禁 owner 契约、只读命令与边界说明
  [b-route-chapter6-gate.md:3](../../../docs/workflows/b-route-chapter6-gate.md#L3)
