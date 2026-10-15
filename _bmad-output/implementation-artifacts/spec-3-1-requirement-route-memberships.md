---
title: 'Story 3.1：独立持久化 Requirement 路线成员关系'
type: 'feature'
created: '2026-10-15'
status: 'done'
baseline_commit: '3ef20e01d8b82f663c425e2392bea141bfd15fdf'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-3-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 现有覆盖检查把一个 Requirement 出现在多个 flow 当成错误，且覆盖表同时承担路线与唯一验证职责，无法忠实表达多条操作动线。

**Approach:** 新增独立 `requirement_route_memberships`，按 `(requirement_id, flow_id)` 唯一，保留每条路线的可观察角色。继续完整保留唯一 `coverage_table` 权威行，旧 owner 确定性投影成路线，不改变原始 Requirement。

## Boundaries & Constraints

**Always:** 准入前机器验证新投影；默认生成、累计 append、修复、checkpoint、正式 planning trace 与 Knowledge 消费路径一致。旧 hash-bound 产物只做读取投影，不原地改写。

**Ask First:** 无；字段细节按 AD-6 的既定键和不变量收敛。

**Never:** 不增加或重分配 GDD、Requirement、Capability、任务三联；不修改正式 MVG baseline 或游戏文件；不以路线数量增加完成计数；不提前声称 Story 3.2/3.3 的完整验证记账已完成。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
| --- | --- | --- | --- |
| MULTI_ROUTE | 一个 Requirement 在两个 flow，各有明确角色 | 保存两条 membership，一条权威 coverage；下一 seed 与 Knowledge 投影可查询 | N/A |
| BAD_PAIR | 重复 pair、未知 Requirement/flow、flow 不含该 Requirement 或空角色 | 机器拒绝，不能进入语义准入；原始 delta 重复不能被 merge 吞掉 | 返回对象定位错误 |
| LEGACY | 没有 membership 字段的旧 coverage | 保留所有原行字段，投影原 flow owner 与原 rationale；重复迁移结果相同 | 显式存在的坏 membership 不自动补齐 |
| CUMULATIVE | 后续 Capability 为已有 Requirement 新增路线 | 保留旧角色与 owner，允许新 pair，不能重复新增权威 coverage | 修复不得删除或改写无关旧路线 |

</frozen-after-approval>

## Code Map

- `scripts/python/_mvg_capability_generation.py` -- 默认 `append_output_schema`、`generate_append.request`、`review_projection`、`repair_scope_errors`；新路线使用累计 Requirement 范围，coverage 仍只新增当前项的唯一权威行。
- `scripts/python/_mvg_capability_append.py` -- `merge_append` 和 `preservation_errors`；合并前验证 delta pair，合并按二元键，保护已接受角色。
- `scripts/python/_mvg_planning_review.py` -- `coverage_errors` 当前拒绝 `flow_requirement_multiple_routes`；替换为独立 membership 检查，保留 `coverage_requirement_duplicate`。语义审查的 Requirement review 仍按唯一权威记录计数。
- `scripts/python/plan_mvg.py` -- `merge_planning_segments`、`validate_segment_routing`、`validate_proposal`、`build_delta` 和 `apply`；保留稳定入口及旧 run 的 hash，默认生成 schema 应实际消费新字段。
- `scripts/python/_mvg_requirement_routes.py` -- 新共享 schema、无损 legacy 读取投影及 pair 验证器；最小 row 为 `requirement_id`、`flow_id`、`observable_role`，旧 owner 原字段留在 coverage。
- `scripts/python/_project_health_mvg_versions.py`, `scripts/python/_project_health_planning.py` -- 只从绑定正确 manifest 路径/hash 的正式 planning trace 或本地选定 proposal 投影路线；无可信 trace 不猜额外角色。
- `scripts/python/tests/test_mvg_requirement_routes.py` -- 新路线、迁移、修复保护、默认生成与 Knowledge 定向验收。
- `scripts/python/tests/test_mvg_planning_contract.py`, `scripts/python/tests/test_mvg_segment_scope.py`, `scripts/python/tests/test_mvg_capability_append.py` -- 更新多路线旧负断言和公共离线 runner，保留重复 coverage/pair 的拒绝。
- `docs/adr/ADR-0005-quality-gates.md` -- Accepted；测试、门禁及证据的既有依据。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/python/_mvg_requirement_routes.py` -- 冻结 schema 与迁移/验证 -- 分离路线和权威覆盖。
- [x] `scripts/python/_mvg_capability_generation.py`, `scripts/python/_mvg_capability_append.py`, `scripts/python/plan_mvg.py`, `scripts/python/_mvg_planning_review.py` -- 接入真实默认生成、累计、修复与前置机器检查 -- 不只新增孤立 helper。
- [x] `scripts/python/_project_health_mvg_versions.py`, `scripts/python/_project_health_planning.py` -- 输出有来源绑定的可查询路线 -- 完成消费闭环。
- [x] `scripts/python/tests/test_mvg_requirement_routes.py` 与相关既有测试 -- 覆盖矩阵、public 生成准入和 trace/Knowledge 持久化 -- 证明无损与坏数据拒绝。
- [x] `workflow.md`, `.agents/skills/plan-mvg/SKILL.md`, `docs/workflows/mvg-integration-acceptance.md` -- 更新已部署边界 -- 唯一验证/evidence 新模型仍归后续 Story。

**Acceptance Criteria:**
- Given one Requirement participates in distinct flows, when projected, then one membership per unique pair records its observable role without duplicating authoritative coverage.
- Given legacy coverage, when projected for a new run or read-only consumption, then the owner and all original authority/evidence fields are conserved and existing checkpoint hashes remain unchanged.

## Design Notes

执行边界：仅使用离线 fake runner；不运行收费模型、Godot 或远程 Git 操作。证据写入 `logs/ci/2026-10-15/story-3-1/`。实现代理不自行提交，由协调者完成审查后本地提交。

新字段显式存在时验证其真实内容，缺失才走旧 owner 迁移。只能从旧 flow coverage 的原说明字段迁移角色：优先非空 rationale，兼容当前有效格式中的 coverage 原文，不猜其他引用的语义。真实新增路线必须给出自己的角色。默认新生成 schema 强制字段；历史只读投影不能借迁移绕过新输出门槛。正式 trace 已随 proposal 原子发布，可持久化 membership 而不为这一 Story 扩大运行时 manifest 协议；Knowledge 仅采用与当前 manifest 完全匹配的 trace。已接受路线和唯一 coverage 不因追加新 pair 被覆盖。

审查修补：旧 owner 投影使用 `legacy_owner_only` 来源标记，只有显式补全并通过全部 pair 校验才升级为完整新路线；新协议拒绝缺字段、旧投影伪装和未知版本，并绑定 prepared index 与 run state。下一轮冻结继承旧非运行时处置及其授权/证据来源；trace 必须绑定真实 Requirement 权威及实际 applied manifest。审查投影从角色变化开始，对 Requirement peers 与 entrypoint links 联合求闭包。

## Verification

- `py -3 -m unittest discover -s scripts/python/tests -p test_mvg_requirement_routes.py` -- expected: OK
- `py -3 -m unittest scripts.python.tests.test_mvg_planning_contract scripts.python.tests.test_mvg_input_envelope scripts.python.tests.test_project_health_mvg_versions` -- expected: OK；实际命令与计数见证据。
- 默认 public generate、checkpoint、review/validate、trace/Knowledge 与 legacy replay 离线定向验证 -- expected: OK，无真实模型调用。
- `py -3 -m py_compile scripts/python/_mvg_requirement_routes.py scripts/python/_mvg_planning_review.py scripts/python/plan_mvg.py` -- expected: SUCCESS
- `git diff --check` -- expected: SUCCESS

审查后定向验证：路线矩阵 20 项、contract/envelope/Knowledge overview 172 项、真实 Knowledge Capability→MVG 生命周期 1 项通过。新矩阵包含旧 apply→trace→下一轮 prepare、legacy 标记升级、本地展示五种绑定篡改拒绝。原 segment 整组的七项 anchor/schema 失败已在未修改 HEAD 内存加载复现；不把既有失败误报为本补丁通过，详见 `logs/ci/2026-10-15/story-3-1/verification-summary.md` 与后续 fix-through 证据。

最后补充：checkpoint/recovery 定向 5 项通过；兼容批次原 37 项中 33 项通过，4 个旧协议 fixture 残留新 checkpoint 字段导致失败，适配后四项定向通过；完整 legacy trace→新 run 生成及协议状态篡改 2 项通过；trace 形状边界 2 项通过。编译与 diff 检查通过。全部使用离线 fake runner。

## Suggested Review Order

- 从唯一权威覆盖之外建立独立路线协议。
  [_mvg_requirement_routes.py:13](../../scripts/python/_mvg_requirement_routes.py#L13)
- 检查历史 trace、实际 manifest 与 Requirement 权威绑定。
  [_mvg_requirement_routes.py:37](../../scripts/python/_mvg_requirement_routes.py#L37)
- 审查角色变化及共享边界的联合闭包。
  [_mvg_capability_generation.py:49](../../scripts/python/_mvg_capability_generation.py#L49)
- 检查旧记录继承及原字段守恒。
  [_mvg_capability_generation.py:95](../../scripts/python/_mvg_capability_generation.py#L95)
- 查看重复 pair 拒绝与完整新协议升级。
  [plan_mvg.py:2765](../../scripts/python/plan_mvg.py#L2765)
- 查看 Knowledge 可信投影与运行时状态隔离。
  [_project_health_mvg_versions.py:11](../../scripts/python/_project_health_mvg_versions.py#L11)
- 最后检查实际生成、重放、迁移及篡改测试。
  [test_mvg_requirement_routes.py:30](../../scripts/python/tests/test_mvg_requirement_routes.py#L30)
