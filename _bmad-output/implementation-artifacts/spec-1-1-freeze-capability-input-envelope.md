---
title: 'Story 1.1：冻结 Capability 输入封套'
type: feature
created: '2026-10-13'
status: done
baseline_commit: a18e6be1a2018852c3987fc8d755e92007c3062b
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
  - '{project-root}/docs/adr/ADR-0005-quality-gates.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

现有准备阶段冻结了多数文件，却没有统一记录本次运行、Capability 顺序和完整 Chapter 5 身份，必需证据缺失也可能被略过。补齐可重验的输入封套，让候选在模型调用前确认消费相同、完整的权威输入。

## Boundaries & Constraints

**Always:** 复用现有准备、freshness 和完整传输机制；文件使用 UTF-8；证据放在 `logs/**`；先写失败测试。来源版本与内容哈希决定身份，无关 Git 提交仅属于 provenance。

**Ask First:** 改变产品范围或权威来源时停止。

**Never:** 修改 GDD、Requirement、任务三联、游戏资源或验收状态；重生成 Capability；执行付费全流程；提前实施评选、共享累计 checkpoint 或预算迁移。

## I/O & Edge-Case Matrix

| 情况 | 输入 | 结果 |
|---|---|---|
| 正常 | 正式 ready 与完整引用 | 固定封套、顺序、证据和 predecessor |
| 漂移 | 来源、顺序或候选副本改变 | 模型零调用，报告具体身份 |
| 缺失 | 必需文件或正式 readiness 缺失 | 阻断；事件标识和 planned 文件不冒充必需现存文件 |
| 超限 | 辅助文本超过请求容量 | 连续分片完整重组；核心超限则阻断 |
| 跨运行 | 相同来源但不同 run ID | 拒绝旧传输回执 |

</frozen-after-approval>

## Code Map

- `scripts/python/plan_mvg.py`：`prepare()` 与 `_validate_input_freshness()` 已绑定原源和复制件；生成前调用 freshness。
- `scripts/python/_mvg_capability_generation.py`：`capability_scopes()` 保留原顺序；`complete_scope_context()` 与 `generate_append()` 构造候选输入。
- `scripts/python/_mvg_evidence_transport.py`：已有连续区间、逐字符重组、context/request 哈希检查，复用而不重写。
- `scripts/python/chapter5_semantic_reconciliation.py`：只读复用 readiness/reconciliation 路径、extraction 快照及现有身份校验。
- `scripts/python/planning_acceptance_fixture.py`：独立 fixture，避免读取真实仓库或未提交日志。

## Tasks & Acceptance

**Execution:**

- [x] `scripts/python/tests/test_mvg_input_envelope.py`：先覆盖矩阵、准备期间漂移和无关提交推进。
- [x] `scripts/python/_mvg_input_envelope.py`：集中构造与重验封套；明确必需引用与上下文引用。
- [x] `scripts/python/plan_mvg.py`：复制完整 Chapter 5 快照；将封套纳入 analysis identity；记录路径、哈希、来源版本、有序 Capability/Requirement scope、inventory、现有 manifest 身份或明确缺省；准备结束重验，失败不得标记 prepared。
- [x] `scripts/python/_mvg_capability_generation.py`：核对候选复制件；输入带 run/envelope identity，使传输回执绑定本次运行；恢复不得静默重封旧输入。
- [x] `scripts/python/tests/test_mvg_evidence_transport.py`：补跨 run 回执拒绝；复验既有完整传输与规划回归。

**Acceptance Criteria:**

- Given 两个 Capability，When prepare 完成，Then 封套保存原顺序索引、readiness 快照身份、全部必需证据及 predecessor 内容身份。
- Given 任一绑定内容改变，When 生成或恢复，Then 在模型 dispatch 前阻断并落盘具体 drift。
- Given 完整超限证据，When 分片，Then 每个字符恰好重组一次，另一 run 的回执不能通过。

## Spec Change Log

## Design Notes

封套嵌入现有 `analysis-index.json`，纳入统一 canonical identity，避免第二套权威索引。候选必须使用该身份及快照，不能从活跃目录重读替代。Chapter 5 继续沿用现有 schema/cache key/input fingerprint，不发明新 readiness。

保留显式 draft 准备入口，缺 readiness 仍不得进入正式生成。必需证据包括显式 evidence-ref、来源文件、正式 readiness 及现有 baseline 的必需依赖；planned 义务与事件 ID 保留分类，不因文件不存在误判。

## Verification

- `py -3 -m unittest discover -s scripts/python/tests -p test_mvg_input_envelope.py -v`
- `py -3 -m unittest discover -s scripts/python/tests -p test_mvg_evidence_transport.py -v`
- `py -3 -m unittest discover -s scripts/python/tests -p test_planning_audit_repair.py -v`

期望：定向测试通过，缺失/漂移/跨 run 用例模型调用为零；日志写入 `logs/ci/2026-10-13/mvg-story-1-1/`。本轮不宣称完整 MVG 工作流或运行时验收通过。

2026-10-14 补充验证：输入封套、规划契约与累计生成合计 209 项通过；最终消费者与回执定向验证 36 项通过，其中输入封套 29 项。日志位于 `logs/ci/2026-10-14/mvg-review-repair/`。新增回归覆盖新运行删除封套、复制失败和重试的最新回执、详细漂移诊断保留，以及状态 scope/manifest 身份镜像、旧版同 schema 无封套运行兼容、Acceptance `Refs` 的 Markdown 标记与尾随标点清理。累计生成夹具使用真实 Chapter 5 reconciliation 与 prepare，不绕过 freshness；缺失、漂移和跨 run 用例均证明在模型 dispatch 前零调用阻断。

既有失败记录：规划审计原有执行失败测试使用过期预算/phase 断言，本轮已适配明确不足候选阻断与当前 append worker 边界，单项通过。项目健康规划的两个既有 fake runner fixture 输出与现行测试 schema 不匹配，分别为 `test_capability_then_mvg_use_actual_planner_stages_without_mutating_main` 与 `test_mvg_consumes_capabilities_already_committed_in_main`；对象已有 `test_refs`，不能将失败归因为缺少该字段。这两个夹具问题尚未修复，未通过放宽封套或准入校验处理；不能宣称完整项目健康规划测试全绿。

后续状态：Story 2.1 已修复上述夹具的未准备测试路径，完整 Knowledge planning 39 项通过。前段保留为本规格交付时的历史验证记录；当前证据见 `logs/ci/2026-10-14/story-2-1/`。

静态验证：目标模块 `py_compile` 与 `git diff --check` 通过。未修改 GDD、Requirement、Taskmaster 三联、游戏代码、Godot 资源或运行时验收状态；未执行付费模型全流程。

## Suggested Review Order

**输入封套与身份**

- 先看封套构造和角色分类
  [`_mvg_input_envelope.py:35`](../../scripts/python/_mvg_input_envelope.py#L35)

- 再看统一 freshness 与失败回执
  [`_mvg_input_envelope.py:195`](../../scripts/python/_mvg_input_envelope.py#L195)

**准备与候选边界**

- 查看 prepare 如何冻结完整输入
  [`plan_mvg.py:4034`](../../scripts/python/plan_mvg.py#L4034)

- 查看候选恢复如何拒绝漂移副本
  [`plan_mvg.py:4654`](../../scripts/python/plan_mvg.py#L4654)

- 查看每次模型调用前的重验
  [`_mvg_capability_generation.py:417`](../../scripts/python/_mvg_capability_generation.py#L417)

- 查看恢复链路对缺失封套的 fail-closed 分支
  [`_project_health_planning.py:373`](../../scripts/python/_project_health_planning.py#L373)

**验证证据**

- 查看封套矩阵和零调用回归
  [`test_mvg_input_envelope.py:35`](../../scripts/python/tests/test_mvg_input_envelope.py#L35)

- 查看传输身份与跨运行拒绝
  [`test_mvg_evidence_transport.py:203`](../../scripts/python/tests/test_mvg_evidence_transport.py#L203)

- 查看累计生成集成回归
  [`test_mvg_capability_append.py:399`](../../scripts/python/tests/test_mvg_capability_append.py#L399)

- 查看旧运行兼容与封套缺失回归
  [`test_mvg_input_envelope.py:60`](../../scripts/python/tests/test_mvg_input_envelope.py#L60)
  [`test_project_health_planning.py:210`](../../scripts/python/tests/test_project_health_planning.py#L210)
