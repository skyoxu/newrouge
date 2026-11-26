---
title: 'Story 4.9：对齐全部生产者消费者与治理文档'
type: 'feature'
created: '2026-11-26'
status: 'done'
review_loop_iteration: 1
baseline_commit: 'f609eb5f77f5d78edee332c6e60ae9e81792e197'
story_key: '4-9-对齐全部生产者消费者与治理文档'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-4-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Epic 2–4 能力虽已落地，但若不按消费者矩阵逐项核对读写路径、公共合同调用、五态版本处理及 Skill/文档回链，易遗留底层直接入口、共享 Task 盲区、失配的 ADR/参数引用或把摘要误当切换授权。
**Approach:** 新增只读 `_b_route_consumer_alignment.py` 与 `b-route-consumer-alignment`，逐项核对补齐十组消费者、五态版本合同、Skill/owning 文档回链（含完整双 `ADR-0038-*.md` 及 `Proposed`/`Accepted` 区分）和 clean-clone 布局，产出可重建切换前覆盖报告，不改 `workflow.md`、不切默认 B 或撤 A。

## Boundaries & Constraints

**Always:** 逐项核对来源/Ledger/审计、planner、业务视图/三联、4–7、`_mvg_obligations`、CLI/direct/route/resume/页面、manifest/runner/milestone、Knowledge 与项目 Skill，列读写路径、公共 schema/resolver/提交调用、有效输入与正反证据及 Epic 5 剩余项，含共享 Task 与底层直接入口，禁仅据 `workflow.md`、测试 dispatcher 或总摘要宣称覆盖；核对新、旧、合法缺失、损坏与未知版本五态处理，拒删 `origin`/`trace`/`manifest` 降回 legacy，合法非 Flow 仍须理由与 `other_verification_refs`，旧 A 限冻结边界运行，完备迁移输入/输出、身份保留与恢复说明，未满足项阻断切换；对齐校验 `AGENTS.md`、入口索引、owning 文档与 `.agents/skills/**/SKILL.md` 的链接/参数/阶段，保 3A/3B/3C 与 4–7、模型恢复与 journal 恢复、Task/Flow/累计完成及发布身份四组区别，`Proposed` 禁当 `Accepted`，双 `ADR-0038` 用完整文件名，不改质量/分支保护与 `workflow.md`；核对最小治理入 Git、原证据留 `logs/**`、clean-clone 凭 `receipt`/`catalog`/当前文件验一致，不强制全 `logs/**` 提交，`logs/**`/备份/历史禁入全局检索，禁复制公共 codec 或私有解析器；产出只读切换前覆盖报告（`passed`/`blocked`/`not_applicable` 可重建，通用 B 不靠奖励特化，`default_b_enabled=false`、`a_write_retired=false`、试点与切换/退出留 Epic 5、零第二状态机）。
**Ask First:** 改 `workflow.md`、7 FORMAL、`CONTROL_PLANE_PATHS`、分支保护或提前切默认 B/撤 A。
**Never:** 凭文本或摘要宣告覆盖；允删字段降回 legacy；把 `Proposed` 当 `Accepted` 或裸写 `ADR-0038`；强制 `logs/**` 入库或复制 codec；自动切默认 B 或建第二状态机。

## I/O & Edge-Case Matrix

| Scenario | Input | Expected | Error |
|---|---|---|---|
| CONSUMER_MATRIX | 十组消费者含共享 Task 与底层入口 | 列读写路径、公共合同、正反证据与剩余项 | 漏底层入口、漏共享 Task 或靠摘要充证据阻断 |
| FIVE_STATE_VERSION | 新、旧、合法缺失、损坏、未知版本 | 同合同区分拒不明依据，禁删字段降 legacy，旧 A 限冻结边界 | 降级旁路、缺非 Flow 依据或缺迁移说明阻断 |
| DOCS_SKILL_ADR | `AGENTS.md`、入口、owning 文档与 Skill | 链接/参数/阶段一致，保四组边界，`Proposed` 禁当 `Accepted`，双 `ADR-0038-*.md` 完整名 | 裸写 `ADR-0038`、`Proposed` 误判或改 `workflow.md` 阻断 |
| GIT_CLONE_LAYOUT | 最小治理、clean-clone 与检索策略 | 最小依据入 Git、原证据留 `logs/**`、clone 验一致，`logs/**`/备份禁入检索、零私有 codec | 强制 `logs/**` 提交、污染检索或复制 codec 阻断 |
| PRE_SWITCH_REPORT | 全批消费者核对汇总 | 可重建只读报告，通用 B 不靠奖励特化，`default_b_enabled=false` | 自动切默认 B、撤 A 或建第二状态机阻断 |

</frozen-after-approval>

## Code Map

- `_b_route_consumer_alignment.py`, `audit_b_route_consumer_alignment.py`, 8 Skills, 4 guards, `b-route-consumer-alignment.md`

## Tasks & Acceptance

- [x] Engine/CLI, `dev_cli*.py`, 4 guards
- [x] 8 Skills & docs (dual `ADR-0038-*.md`, no `workflow.md` edit)
- [x] Tests, CI paths, `AGENTS.md`

## Spec Change Log

- `P-01..P-10`: reparse/`--report` `xb`; full `GROUPS`+guards; fail-closed `--skip-live-probes`; `workflow.md` `HEAD` check; ADR/Skill/CLI/codec/`_excluded`/CI+tests.
- `D-01`: Dismissed `git restore workflow.md`.

## Suggested Review Order

1. `_b_route_consumer_alignment.py`, `audit_b_route_consumer_alignment.py`
2. 4 writer guards, 8 Skills, `b-route-consumer-alignment.md`
3. `test_b_route_consumer_alignment.py`, CI paths, verify log

## Verification

- `logs/ci/2026-11-26/story-4-9-final-verify.log`
- `logs/ci/2026-11-26/story-4-9-step4-triage.md`
