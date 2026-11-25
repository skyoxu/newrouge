---
title: 'Story 4.4：在身份匹配时复用构建与共享测试证据'
type: 'feature'
created: '2026-11-26'
status: 'done'
baseline_commit: 'd08d3a8354dad5eea49f464803308ec90befdecb'
story_key: '4-4-在身份匹配时复用构建与共享测试证据'
review_loop_iteration: 1
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-4-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 多 Flow 或重试执行尚未按输入/环境/整合快照身份分别核验构建预热复用与共享测试证据去重，且同次运行顺序测试共享可变数据目录，易重复做无关工作或串染状态。
**Approach:** 新增 _b_route_evidence_reuse.py 并接入 _b_route_scope_runner.py、run_mvg_acceptance.py 与 _mvg_execution.py，分离构建复用与同快照共享测试去重并逐测试隔离可变状态，不建第二套证明或缓存。

## Boundaries & Constraints

**Always:** 构建与预热复用仅在源内容、工具链、环境及工件规则匹配时启用并记来源与理由，复用构建不等于测试通过，保留实际未命中耗时/成本且禁用预算预留宣称省钱；同测试被多 Flow 要求时按测试身份、完整相关输入、验证语义、环境及同一整合 snapshot 核对，仅有效同条件结果可去重引用，保 Requirement 唯一处置与多路线覆盖，不按 Flow 数重计完成，不合并异输入或仅同名测试；逐测试设隔离/重置边界（独立 user:// 与临时目录及快照只读校验），换序或重入禁继承前序可变状态，仅共享只读构建/预热，人工义务禁由机器结果代替；相关来源/契约/规则/snapshot 漂移或 proof 损坏必拒，无关变化不触发语义重做，严守正式 runtime receipt/inventory/snapshot 与 dirty 校验，禁跨快照拼接，规划完成项 adoption 与运行复用各循独立规则；回执与事件列复用 ID/来源/原时间戳、实跑与失效原因，同 event 去重，禁刷旧 PASS 时间戳充新运行，不设提速或降本指标。
**Ask First:** 改 7 FORMAL、扩 ReasonCode/Stage、建第二证明格式或启付费 API。
**Never:** 构建复用当测试通过；按 Flow 数重计或合并同名异输入测试；测试间共享可变状态；跨快照拼证据或刷旧 PASS 时间戳；拿预算预留充省钱。

## I/O & Edge-Case Matrix

| Scenario | Input | Expected | Error |
|---|---|---|---|
| BUILD_REUSE | 多 Flow 或同快照请求相同构建/预热 | 源/工具链/环境匹配才复用并记理由；测试仍独立核验 | 构建复用判测试 PASS 或拿预留充省钱阻断 |
| SHARED_TEST | 同一测试被多当前 Flow 要求或重试 | 身份/相关输入/语义/环境/同 snapshot 匹配才去重且只计一次 | 按 Flow 重计完成或合并异输入/同名测试阻断 |
| STATE_ISOLATION | 测试换序、重入或写可变状态 | 逐测试独立数据/临时目录与重置，零继承可变状态 | 污染后序测试或拿机器共享代人工义务阻断 |
| DRIFT_BOUNDARY | 相关输入/snapshot 漂移、损坏 vs 无关变化 | 相关/跨快照/损坏必拒；无关不误废；分清规划 adoption 与运行复用 | 绕过 snapshot/dirty 校验或跨快照拼接阻断 |
| RECEIPT_EVENTS | 命中复用、重跑或资格未知 | 列复用 ID/来源/原时间、实跑与失效原因；同 event 去重 | 刷旧 PASS 时间戳或设提速/降本门槛阻断 |

</frozen-after-approval>

## Tasks & Acceptance

- [x] `_b_route_evidence_reuse.py`, `_b_route_scope_runner.py`, `run_mvg_acceptance.py`, `_mvg_execution.py`, `dev_cli*.py`
- [x] `docs/workflows/b-route-evidence-reuse.md`, `AGENTS.md`, `test_b_route_evidence_reuse.py`, `test_b_route_runtime_ci.py`, `run_gate_bundle.py`, `b-route-runtime-deterministic.yml`

## Spec Change Log

- 2026-11-26 (Step 4, `review_loop_iteration: 1`): 合入 P-01..P-06（`patch=6`, `defer=0`, `dismiss=1`，`logs/ci/2026-11-26/story-4-4-step4-triage.md`）：放行 `Tests.Godot/Game.Godot` Junction 与 `.uid` 并清理 `logs`/`reports`；完整 `bin`+`obj` 回填、先序零漂移/污染校验与 `--challenge-input` 预热；逐测试 `relevant_paths`、描述符校验与按 Flow 过滤路线；强制封存 `coverage-receipt.json`、归属目录报告重验、`.jsonl`+`msvcrt` 锁与无 scope 阻断；补齐 CI 与验证（`logs/ci/2026-11-26/story-4-4-final-verify.log`）。

## Suggested Review Order

1. `scripts/python/_b_route_evidence_reuse.py`
2. `scripts/python/_b_route_scope_runner.py`, `run_mvg_acceptance.py`, `dev_cli_builders.py`
3. `scripts/python/tests/test_b_route_evidence_reuse.py`, `test_b_route_runtime_ci.py`, `AGENTS.md`, `docs/workflows/b-route-evidence-reuse.md`

## Verification

- `logs/ci/2026-11-26/story-4-4-final-verify.log`（48 tests + CLI `--help` 全部通过）
