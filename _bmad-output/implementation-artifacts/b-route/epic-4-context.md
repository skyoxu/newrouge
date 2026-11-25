# Epic 4 Context: 执行真实适用验证并展示可信进度

<!-- Compiled from planning artifacts. Edit freely. Regenerate with compile-epic-context if planning docs change. -->

## Goal

从受治理反向关系计算完整传递影响并形成三类义务 `VerificationScope`，交由真实 xUnit/GdUnit4/MVG 执行器消费并报告实际覆盖、同身份构建与测试复用及局部/Flow/累计里程碑完成判定；在 Knowledge、规划页面与过程观测中诚实展示规划/实施/运行身份、阶段阻塞与统一诊断，并在 Windows 故障与消费者对齐下收口通用 B 链路。

## Stories

- Story 4.1: 从受治理反向关系计算完整传递影响
- Story 4.2: 形成可执行的三类义务VerificationScope
- Story 4.3: 让真实执行器消费范围并报告实际覆盖
- Story 4.4: 在身份匹配时复用构建与共享测试证据
- Story 4.5: 分别核对Task、Flow和累计里程碑完成
- Story 4.6: 派生展示规划、实施与运行身份
- Story 4.7: 在规划页面按真实阶段操作并定位阻塞与恢复
- Story 4.8: 汇集可追溯过程观测与统一诊断
- Story 4.9: 对齐全部生产者消费者与治理文档
- Story 4.10: 在Windows故障与共享变更下核对端到端结论

## Requirements & Constraints

- **完整影响与三类义务（FR-11/12/14，AR-10/11/25）：** 按已提交四部分定义、绑定、契约、测试责任与累计 manifest（含 `planned` Flow 与跨 Capability/共享 Task）计算循环安全传递闭包；未知边保守扩大但不置空、不迫提前实现范围外 `planned`；区分旧回归、本次新增/未完与范围外未来义务，禁将失败旧 Flow 转 `planned`/`future` 换绿。
- **真实执行、身份复用与分层收尾（FR-11/13/16，AR-9/10/17）：** runner 真实消费 `VerificationScope`（或显式记录保守超集），分离构建/预热复用与同条件共享测试去重并隔离可变状态，不刷旧 PASS 时间戳；严格区分单 Task 局部通过、目标 Flow 完成与同一整合 snapshot 累计 `full-MVG`，禁跨 snapshot 拼接报告。
- **派生身份、阶段页面与观测（FR-3/15/16/17，AR-1/16/24/26/28）：** Knowledge/页面分离计划、实现、运行与六类证据等级，绑定 `workspace`/`attempt`/`stable`/`main` 身份且 preview 不推发布指针、Ch6/Review/Recovery 不隐式全局刷 Knowledge；无 Task 3A/3B 不被 Task readiness 阻断；观测区分实测耗时/dispatch 与暂停墙钟/`unknown`/预留，复用公共六字段 `Diagnostic`，不设提速或降成本门槛。
- **消费者对齐与边界（FR-8/9/17，AR-3/5/6/18/19）：** 对齐 Epic 1 消费者矩阵、CLI/Skill/AGENTS 与两份完整文件名 `ADR-0038`；奖励真实生产改造、默认 B 切换与 A 撤权留归 Epic 5。

## Technical Decisions

- 复用 `_b_route_codec.py`、`_b_route_schema_resources.py`（辅助 schema 不改 7 份 `FORMAL`）、`_b_route_flow_graph.py`、`_b_route_input_set.py` 与 `_b_route_operation_scope.py`，不新建规划数据库或第二套 Task/MVG 状态机。
- 复用既有 `run_mvg_acceptance.py`、xUnit/GdUnit4 执行链、`milestone_incremental_handoff.py`、`project_health_*` 与 `logs/**` 事件证据；只读查询零写盘（显式 `--report` 排他写 `logs/**`）。

## Cross-Story Dependencies

承接 Epic 1–3（尤其 2.9/2.10、3.5–3.12）：4.1→4.2→4.3→4.4→4.5；4.6（依 4.1/4.5/3.5/2.9）→4.7（依 4.6/2.10/3.12）→4.8（汇 4.3–4.5/4.7）→4.9→4.10 端到端故障收口并交接 Epic 5。
