# Epic 3 Context: 按已采纳定义承接任务并一致实施与恢复

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

承接 Epic 2 零 Task 正式采纳，盘点既有实现、成熟 Task、共享能力与验证义务，仅为真实缺口生成或复用三联，经共享提交发布 3C/4/5 绑定与统一 InputSet/readiness；使 CLI、直接 Chapter 6、resume/route 与页面触发共用门禁，按缺陷类型复用规划或返 owning stage，并按目标 slice 收口 Chapter 7 UI。

## Stories

- Story 3.1: 从复用盘点形成真实缺口的任务变更预览
- Story 3.2: 受治理编译三联与3C绑定并保留当前任务状态
- Story 3.3: 统一判定Task来源及完整适用计划集合
- Story 3.4: 在Chapter4细化生产契约与四部分实施定义
- Story 3.5: 构造共同InputSet并精确判断新鲜度
- Story 3.6: 绑定真实MVG义务或合法其他验证依据
- Story 3.7: 在Chapter5核对同源定义并形成有效readiness
- Story 3.8: 让直接Chapter6与公共CLI消费统一实施门禁
- Story 3.9: 在恢复与route入口重验当前输入和任务资格
- Story 3.10: 按缺陷类型复用规划或返回定义所属阶段
- Story 3.11: 按目标slice收口Chapter7并复用已验证UI
- Story 3.12: 让页面实施触发与全入口决定保持一致

## Requirements & Constraints

- **缺口与保护（FR-6/14，AR-4/7/21）：** 先盘点再经业务视图与三联编译承接缺口，禁直写 `tasks.json` 或将 Story 号当 Task ID；保成熟 ID/状态/历史与累计 manifest，旧 `done` 不证新义务，更新/拆合/退役须有差异与防削弱审阅。
- **四部分与多对多（FR-7/10，AR-12/13）：** 3B 定逻辑四部分，3C 绑 Task，4–5 细化生产命令、只读状态、唯一所有者、C# 薄适配与资源绑定；保 Task<->Flow 多对多及 Requirement 唯一处置/路线/共享证据去重，不四拆/不造 API，planned 不称已实现。
- **统一门禁（FR-8/9，AR-5/6/22/24）：** 先验已提交 `policy`/`catalog`/`origins` 与反向索引再判 A/B，缺失/损坏/未知或 pending（含旧 `capability-apply.pending.json`）均阻断，禁缺 trace 退回 legacy。Flow/MVG 绑有效 manifest；合法非 Flow 无 MVG 凭采纳理由与其他验证放行，影响 Flow 仍绑回归；进 6 不要求本 Task 已 `done`，防 owner 自依赖。
- **新鲜度与底线（FR-13/16，AR-8/9/10/17/26）：** InputSet 绑来源、采纳/绑定修订、Task 定义投影（仅排除 status）、契约/ADR/Overlay、依赖闭包、规则与环境；无关 HEAD/catalog/他状态不失效。纯实现缺陷复用规划；改定义/契约/所有权返 owning stage。保 TDD、P1、Needs Fix、rerun_guard 与实测观测，不设提速门槛。

## Technical Decisions

- 复用 `_b_route_codec.py`/`_b_route_records.py` 六类记录与 `TaskJoinContext`；`tasks.json` 管唯一状态，新记录不复制状态，不建数据库。
- 写者复用 `_b_route_commit.py`/`_planning_apply_journal.py`（短 metadata 锁→稳定 scope 租约，长调用不持全局锁），合并状态并验前后像/投影，全验后发布 `catalog.v1.json`。
- 全入口共用 resolver/gate 与六字段 `Diagnostic`；Ch6 不刷 Knowledge，preview 不推发布指针。

## Cross-Story Dependencies

Epic 1 交付治理/codec/保护/预检；Epic 2（至 2.10）交付 3A 审计、3B 采纳与提交/恢复。Epic 3：3.1→3.2（依 2.6–2.8）→3.3→3.4→3.5→3.6→3.7→3.8（依 2.8）→3.9→3.10（汇 3.1/3.2/3.7–3.9）→3.11→3.12。Epic 4 接续影响/`VerificationScope`/Knowledge；Epic 5 完成奖励试点与默认 B 切换。
