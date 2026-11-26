---
title: 'Story 4.10：在 Windows 故障与共享变更下核对端到端结论'
type: 'feature'
created: '2026-11-26'
status: 'done'
review_loop_iteration: 1
baseline_commit: '7af0290dab3f5272fd10122a5c3067927ef92f9f'
story_key: '4-10-在windows故障与共享变更下核对端到端结论'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-4-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 单模块测试无法完全暴露真实 Windows 文件占用、进程强杀重启、发布前后中断与跨 scope/多 Flow 共享变更下的混合提交、资格复活或跨快照拼接通过风险。
**Approach:** 新增 `_b_route_e2e_fault_matrix.py` 与 `b-route-e2e-matrix`，在真实 Windows 下串联 Epic 2–4 正式入口注入六阶段故障、共享 Task/Flow 演进、共享证据隔离与页面/Knowledge/观测一致性验证，产出 Epic 5 交接报告，不把协议夹具当奖励验收、不切默认 B。

## Boundaries & Constraints

**Always:** 在真实 Windows 控制文件占用（`msvcrt` 锁）、子进程退出/重启、发布前后故障与状态并发，注入 `prepare`/`reserve`/`apply`/`verify`/`publish`/`recover` 失败点并调真实读/执行入口，确保完整可验证提交或明确阻断，部分写、待清 pending 与损坏 journal 禁混合消费，保后编辑与当前 Task 状态，拒同 ID 异内容，禁以模拟异常冒充真实 Windows 占用/持久化验证并列未测边界；核对共享 Task 跨 scope 加新 plan、漂移与旧未知 pending 经五入口及正式读链的一致阻断与原合同恢复，无关 scope 照常继续，禁删 marker/origin/manifest 或伪 `N/A` 绕过，核对集成 owner 与合法非 Flow 正反例；串联影响、scope、runner 与收尾核对共享变更触及旧 Flow A 与范围外未实现 B 再将 B 入范围：A 失败修后全回归，B 范围外先保未来责任不宣通过、入范围未完阻断，声明范围与覆盖一致，禁重分类旧失败或用旧 manifest 消除、不强迫提前实现范围外 Flow；核对多 Flow 共享测试同条件隔离复用、拒异 snapshot 拼累计通过，拒空/跳过/方法调用冒充引擎输入或人工检查，`partial`/`critical`/单 Flow 标真实范围，协议夹具只记适配证据；核对页面、Knowledge 与观测在失败、epoch/reopen 与恢复下展示、诊断及指针一致，撤销资格不复活，`preview`/`attempt` 不污染 `stable`/`main`，Ch6/Review/Recovery 零隐式全局刷新，未知与实测预算/费用/耗时分列且不抵消失败；产出 Epic 5 交接报告，明列奖励生产适配、双路径真实 Windows/Godot/C# 证据、默认 B 切换与 A 退出待 Epic 5。
**Ask First:** 改 `workflow.md`、7 FORMAL、`CONTROL_PLANE_PATHS` 或提前切默认 B/退 A。
**Never:** 用 mock 异常冒充真实 Windows 锁/故障；混合消费部分写/pending；删治理字段或重分类失败；跨 snapshot 拼通过或拿协议夹具充 Godot 证据；让撤销复活或切默认 B。

## I/O & Edge-Case Matrix

| Scenario | Input | Expected | Error |
|---|---|---|---|
| WIN_FAULTS | 真实 Windows 锁、子进程退出与六阶段故障 | 原子提交或明确阻断，保后编辑与 Task 状态，拒同 ID 异内容 | 混合消费部分写/pending 或 mock 冒充实测阻断 |
| SHARED_SCOPE | 共享 Task 加新 plan、漂移与旧未知 pending | 全入口一致失效相关 readiness、保无关 scope、恢复原合同 | 删 marker/origin/manifest、伪 `N/A` 或错放非 Flow 阻断 |
| FLOW_AB_EVOLVE | 共享变更触及旧 Flow A 与范围外 B 后 B 入范围 | A 失败修后全回归；B 先保责任、入范围未完阻断 | 重分类失败、范围失配或强迫提前实现阻断 |
| SNAPSHOT_TIERS | 多 Flow 共享测试、异 snapshot 及空/跳/方法报告 | 同快照隔离共享，拒跨 snapshot 拼接与伪引擎/人工证据 | 跨快照拼通过或协议夹具冒充 Godot 阻断 |
| PARITY_HANDOFF | 失败、epoch/reopen、恢复及 Epic 5 交接 | 三视图一致，撤销不复活、零刷指针，明列待 Epic 5 项 | 资格复活、污染 `main`/`stable` 或提前切 B 阻断 |

</frozen-after-approval>

## Tasks

- [x] Matrix service, CLI, `dev_cli`, Group 10 registry
- [x] E2E tests, gate bundle, CI paths
- [x] Owner doc, entrypoints, Epic 4 closure

## Spec Change Log

- `P-01..P-10`: mid-`prepare`/`reserve` hooks; Ch5 readiness, 5-entry parity, `resume_journal`, delete-`.pending`; Flow A launch fail/`older_rel`/Phase-2 `rc!=0`; `verified_scope`/splicing; zero-refresh & 4.6–4.8 parity; handoff/registry; reserved paths/cleanup; 6-key CLI tests; docs/CI & closure.

## Suggested Review Order

1. `_b_route_e2e_fault_matrix.py`, `verify_b_route_e2e_fault_matrix.py`, `_b_route_consumer_alignment.py`
2. `test_b_route_e2e_fault_matrix.py`, docs, CI

## Verification

- `logs/ci/2026-11-26/story-4-10-step4-triage.md`
- `logs/ci/2026-11-26/story-4-10-final-verify.log`
- `logs/ci/2026-11-26/b-route-e2e-matrix-final.json`
