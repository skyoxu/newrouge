---
title: 'Story 3.9：在恢复与route入口重验当前输入和任务资格'
type: 'feature'
created: '2026-11-24'
status: 'done'
baseline_commit: 'c608424bff7856e1b0921064483121461d6ea6bc'
story_key: '3-9-在恢复与route入口重验当前输入和任务资格'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-3-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** resume_task、chapter6_route 与恢复入口未重验实时 InputSet、readiness、义务与资格，旧缓存或删 marker/新 lineage 易放行失格或无进展恢复，且推荐仍写盘。
**Approach:** 交付 _b_route_chapter6_recovery.py，接入 resume_task、chapter6_route、_chapter6_recovery_common、inspect_run 及恢复入口(run_review_pipeline --resume/--fork、llm_review_needs_fix_fast)，守只读推荐与止损。

## Boundaries & Constraints

**Always:** 推荐或恢复前先经 3.8 门禁复验 InputSet、readiness、Stage-5 义务与实时 Task/依赖资格，再定位恢复动作；recommendation-only 零副作用(禁写 active-task、technical-debt.md 或启动执行)，缓存 ready/ok 不跳实时依据，explicit_not_enabled_a 保紧凑输出兼容；来源/规则/契约/绑定/plan 变或 pending/损坏(capability-apply.pending.json、未决 B 操作与旧 apply-journal)用同六字段 Diagnostic 与 reason_code 拒恢复并定位 return_stage(3A..5)或原 journal resume_ref，未知 scope 阻断，旧 A/done 不遮新 B 责任(requires_chapter6_reverification)，模型证据与文件应用恢复各守原合同；仅 status 推进或无关 scope/HEAD 变保成果且不改旧 after，重算资格，禁凭 Task ID/HEAD/整文件 hash 复用，不拒未 done；遇绑定替换、新 plan 加入或后编辑，在恢复边界冻本 run InputSet 并按锁序(短 metadata→业务 scope_ids，禁长占 metadata/全局锁)持保护，冲突或漂移即停禁混用半新半旧，前像/当前状态校验保后编辑与新进度；遇失败、重试预算、rerun_guard/stop-loss 或 2.9 epoch/reopen 撤销，保预算与历史，禁借新 lineage、换入口、刷 Knowledge 或删 marker 洗白信号(跨目录扫持久 run)；对齐 help、Skill 与文档，runtime_verified/default_b_enabled 恒 false。
**Ask First:** 改 7 FORMAL、扩 ReasonCode/Stage、改 3.10 协议或启付费 API。
**Never:** 推荐写盘/记债；信缓存跳门禁；凭整文件 hash/HEAD 复用；混用半新半旧；新 run 或删 marker 洗白止损/reopen。

## I/O & Edge-Case Matrix

| Scenario | Input | Expected | Error |
|---|---|---|---|
| REC_READONLY | 有效 B run 调推荐 vs 显式恢复 | 先验实时 InputSet/readiness/义务/资格；推荐零写 | 推荐写盘或凭缓存放行阻断 |
| STALE_PEND | 来源/契约/绑定/plan 变、pending 或旧 done 遇新义务 | 同 code 拒恢复，定位 3A..5 或原 journal | 旧 A/done 遮新责任或未知 scope 放行阻断 |
| STATUS_HEAD | 仅 status 推进或无关 scope/HEAD 变，未 done | 保成果，重算实时依赖资格并准恢复 | 凭整文件 hash 误杀或拒未 done 阻断 |
| MID_DRIFT | 绑定替换、新 plan 加入或后编辑进恢复边界 | 短 metadata 锁取业务 scope，冲突停并保后编辑 | 混用半新半旧或长占 metadata 锁阻断 |
| BUDGET_REOPEN | 失败/止损预算或 reopen 撤销，删 marker/开新 run | 保历史预算与信号，跨 lineage 拒洗白 | 删 marker/换入口/新 run 清除止损阻断 |

</frozen-after-approval>

## Code Map

- _b_route_chapter6_gate.py:1, _b_route_input_set.py:3533 -- 3.8 门禁/租约
- resume_task.py:173,414,763, chapter6_route.py:257,468, _chapter6_recovery_common.py:37,258, inspect_run.py:203 -- 推荐/路由
- scripts/sc: run_review_pipeline.py:1897,2080,2420, llm_review_needs_fix_fast.py:1520 -- 恢复/fork/止损
- _b_route_operation_scope.py:299,375, _b_route_completed_reuse.py:1 -- journal/锁/撤销
- .agents/skills/workflow-chapter6-single-task-daily-loop/SKILL.md:39 -- Skill/CLI

## Tasks & Acceptance

**Execution:**
- [x] scripts/python/_b_route_chapter6_recovery.py -- 重验、无进展/reopen 检测、冻结对账与 journal 定位
- [x] scripts/python: resume_task.py, chapter6_route.py, _chapter6_recovery_common.py, inspect_run.py -- 重验、零写与兼容
- [x] scripts/sc: run_review_pipeline.py, llm_review_needs_fix_fast.py; dev_cli.py -- 恢复对账、防洗白与 help
- [x] .agents/skills/workflow-chapter6-single-task-daily-loop/SKILL.md, docs/workflows/b-route-chapter6-recovery.md, scripts/python/tests/test_b_route_chapter6_recovery.py, test_b_route_runtime_ci.py -- 文档、单测与 CI

**Acceptance Criteria:**
- Given 已有 run 与 sidecar，when 调推荐或恢复，then 先重验实时 InputSet/readiness/义务与资格，推荐零副作用，仅 status/无关 HEAD 变可恢复且不拒未 done。
- Given 定义/plan 变、pending/损坏、冲突、止损或 reopen 撤销(含删 marker/新 run)，when 恢复，then 返同一 code 与 3A..5/journal 阻断，保后编辑与历史并对齐文档。

## Spec Change Log

## Verification

- `py -3 -B -m unittest scripts.python.tests.test_b_route_chapter6_recovery scripts.python.tests.test_resume_task scripts.python.tests.test_chapter6_route scripts.python.tests.test_b_route_runtime_ci -v`
- `py -3 -B scripts/python/dev_cli.py resume-task --help`

## Suggested Review Order

**实时恢复重验、基线冻结与止损核心**

- 统一重验 3.8 门禁、任务资格、pending、基线漂移、2.9 撤销与持久止损
  [_b_route_chapter6_recovery.py:1587](../../../scripts/python/_b_route_chapter6_recovery.py#L1587)

- 严检全部 legacy/B journal 与后编辑前像冲突，保留用户改动
  [_b_route_chapter6_recovery.py:309](../../../scripts/python/_b_route_chapter6_recovery.py#L309)

- 跨日期目录扫描持久止损与产品源码指纹，通过 run 清零并保历史
  [_b_route_chapter6_recovery.py:1314](../../../scripts/python/_b_route_chapter6_recovery.py#L1314)

- 按短 metadata 至并集业务 scope 锁序持租约、冻基线并跨边界复验
  [_b_route_chapter6_recovery.py:2193](../../../scripts/python/_b_route_chapter6_recovery.py#L2193)

**推荐、路由与巡检零副作用入口**

- 推荐与恢复摘要接入实时重验、持久兜底，recommendation-only 严格零写
  [resume_task.py:464](../../../scripts/python/resume_task.py#L464)

- 路由入口支持 --latest 解析 task_id、实时重验与止损分层路由
  [chapter6_route.py:293](../../../scripts/python/chapter6_route.py#L293)

- 巡检入口 fail-closed 拦截 B 阻断与非 ASCII task_id，禁跳过与吞异常
  [inspect_run.py:1007](../../../scripts/python/inspect_run.py#L1007)

- 紧凑输出保持 explicit_not_enabled_a 兼容并补充 B 阻断归因三字段
  [_chapter6_recovery_common.py:261](../../../scripts/python/_chapter6_recovery_common.py#L261)

**恢复执行入口与联合租约收口**

- fresh/--resume/--fork 前置零写门禁、--fork 源基线对账与联合租约复验
  [run_review_pipeline.py:2516](../../../scripts/sc/run_review_pipeline.py#L2516)

- 6.8 入口前置查持久止损与源基线，纳入联合租约按轮次复验漂移
  [llm_review_needs_fix_fast.py:1465](../../../scripts/sc/llm_review_needs_fix_fast.py#L1465)

- 单任务编排排除自身 out_dir 后执行实时恢复与持久止损预检
  [run_single_task_chapter6_lane.py:972](../../../scripts/python/run_single_task_chapter6_lane.py#L972)

**测试、CI 与治理文档**

- 覆盖矩阵五场景与 P-01 至 P-05 回归的缓存固件单测集
  [test_b_route_chapter6_recovery.py:257](../../../scripts/python/tests/test_b_route_chapter6_recovery.py#L257)

- 确定性 CI 路径与选择清单显式纳管恢复核心模块与测试
  [test_b_route_runtime_ci.py:228](../../../scripts/python/tests/test_b_route_runtime_ci.py#L228)

- 恢复与路由重验 owner 文档、只读边界与 anti-whitewash 契约说明
  [b-route-chapter6-recovery.md:1](../../../docs/workflows/b-route-chapter6-recovery.md#L1)
