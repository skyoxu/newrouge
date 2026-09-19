# MVG 集成验收

本入口验证同一版本中多个功能提交组合后的行为。保留功能任务、Chapter 6 内置 review、现有交付 profile 门禁和 MVG 级知识库刷新节奏。不引入 Epic，也不自动修改任务状态。设计依据见 ADR-0037。

## 在现有章节中接入

| 阶段 | 补充动作 | 产物和检查 |
| --- | --- | --- |
| Chapter 3 任务编排 | 为跨任务链路指定整合责任。已有功能任务能承担就复用；无人承担时才通过现有任务三联流程补集成任务。 | manifest 的 task_ids 和 handoff 的 owner_task 必须引用真实任务。治理任务可以不属于玩家旅程。 |
| Chapter 4 契约基线 | 明确每次交接的生产方、消费方、归属任务、契约引用和可观察行为。 | 每条 handoff 至少关联一个测试；引用现有契约，不复制字段正文。 |
| Chapter 5 语义稳定化 | 检查 planned 测试是否有明确行为，补齐已有任务的验收引用。 | 继续使用现有 Refs/overlay 校验，不增加第二套任务状态。 |
| Chapter 6 开发和收尾 | 功能实现时逐步落地链路测试，改动时按建议优先回归；MVG 收尾在整合版本运行全部必测项。 | 精确提交或工作区摘要、执行命令、原始报告、summary.json。 |
| Chapter 7 UI 接线 | 为关键链路准备真实场景、引擎输入、状态等待与清理。 | 区分 scene-method 和 engine-input 证据；视觉、手感与空间可用性仍由人验收。 |

最初的“开发前就绪检查”拆入上述 Chapter 3/4/5，不再新建独立的重型流程。`plan` 只能发现清单结构和引用缺口，不能证明任务拆分合理或产品验收完整。

## 清单与责任

当前清单分三层：

- `docs/testing/mvg/reward-pilot.json`：单一奖励链路 pilot，仅用于窄范围示例与反例实验。
- `docs/testing/mvg/m1-critical.json`：当前默认可执行的多 flow critical regression，只引用 Taskmaster 中已 `done` 的关键 Continue/Resume 与 Combat→Reward→Return 边界。
- `docs/testing/mvg/m1-full.json`：M1 自动化 full-scope 目标 inventory。它把 New Run→Map、Map→Node、Continue/Resume、Combat→Reward→Return 全部列入范围；只要 scoped task 仍非 `done`，就必须把对应 task id 写入 `coverage.blocking_task_ids`，`run` 模式会 fail-closed，不能产生 full runtime_verified。

每个 manifest 必须包含 `coverage`：`mode`、`scope_id`、与 flow 顺序完全一致的 `required_flow_ids`、真实的 `blocking_task_ids` 和非空 `excluded_claims`。这让“跑完整个当前清单”与“整个 M1 MVG 已覆盖”成为两个不同命题。

扩展时复制其结构，替换 mvg_id、coverage、flows 和 tests，并逐条核对范围：

- flow：可观察 outcome、真实 task_ids、显式 source_paths、handoffs、test_ids。
- handoff：producer_task / consumer_task / owner_task、contract_ref、behavior、test_ids。
- test：唯一 id、kind（dotnet/gdunit）、state（planned/implemented）、仓库相对 path、evidence_level、min_tests；dotnet 还需测试类 selector。
- planned 允许测试文件暂不存在；run 必须全部 implemented 且文件存在。implemented 只表示实现已存在，不表示通过。

清单验证器检查归属、任务引用、测试覆盖关系和文件存在性，但不理解行为语义。事件契约引用表示交接设计来源，不代表测试已断言事件总线发布。跨层真实性需看测试实际调用路径。测试入口不得使用重建领域模型的 fake 作为生产集成证据。

## Windows 命令

```powershell
# 默认清单现在是可执行的 M1 critical scope：
py -3 scripts/python/dev_cli.py run-mvg-acceptance --mode plan
py -3 scripts/python/dev_cli.py run-mvg-acceptance --mode recommend --base origin/main
py -3 scripts/python/dev_cli.py run-mvg-acceptance --mode run --snapshot commit --revision HEAD --godot-bin $env:GODOT_BIN --challenge-input
# 目标 full scope：T59/T60 未 done 时只能 plan，run 必须 fail-closed：
py -3 scripts/python/dev_cli.py run-mvg-acceptance --manifest docs/testing/mvg/m1-full.json --mode plan --snapshot commit --revision HEAD
# 开发中的未提交改动：
py -3 scripts/python/dev_cli.py run-mvg-acceptance --mode run --snapshot workspace --godot-bin $env:GODOT_BIN
```

可通过 `--manifest <repo-relative.json>` 选择其他 MVG。正式收尾优先 commit 模式；workspace 模式记录文件内容摘要，不得冒充某个提交的验证。运行器将输入复制到独立快照，隔离 user:// 数据，复用 xUnit 和现有 GdUnit4 Windows Junction 入口。全局预算默认 900 秒，可用 `--timeout-sec` 调整；超时不是缺陷被检测的证据。

每次输出到 `logs/ci/mvg-acceptance/<run-id>/`。plan/recommend 返回成功时 runtime_verified 仍为 false。run 只有所有清单测试实际执行、达到 min_tests、零失败、零跳过且进程成功，才会标记 runtime_verified=true。缺报告、空报告、错误测试选择、计数不一致、重复用例结果和准备失败均阻断。测试类/套件身份精确匹配，不接受近似名称。摘要只代表该清单范围与该输入版本，不能自动写任务 done。

## 奖励旅程试点

领域测试组合真实 CardPoolCatalog、CardPoolSelectionService 和 DeterministicOfferService，验证相同上下文重新进入时奖励锁定稳定。引擎测试实例化真实 Main 与 EventBus，通过准备接口建立已结束战斗的奖励状态，随后使用 Viewport InputEventAction 激活 UI，验证选择一张卡、领取入口移除、金币准确增加配置金额、领取剩余奖励后返回地图。独立 scene-method 套件向真实结算入口重复提交同一领卡/金币请求，验证第二次拒绝且资源只增加一次。

准备/观察接口可以读取状态；触发领取不能直接调用业务方法或手工 emit pressed。等待以界面/领域状态为条件，使用有上限的逐帧轮询，超时输出场景与状态；清理节点、输入和语言设置。此测试主动设置按钮焦点，不证明导航顺序、鼠标命中、遮挡、OS 输入或存档重载，也不证明完整战斗流程。

`--challenge-input` 在基线通过后断开领取入口的 pressed 接线。必须出现实际断言失败才认定发现缺陷；运行器缺失、编译错误或超时不算。这个反例用于检验旅程确实依赖 UI 接线，不修改生产代码。

新增其他旅程时遵循同一结构：隔离种子/存档和起始场景 → 输入动作 → 有界状态等待 → 跨层结果断言 → 清理。优先选启动到首场战斗、失败重开、结算到地图等真实高风险链路，不为每个任务强造旅程。

## 影响建议与边界

recommend 比较 Git 改动与清单中 source_paths、contract_ref、测试路径，输出命中链路及文件证据。commit 模式的清单和比较终点均绑定 --revision，不混入当前工作区；workspace 模式明确标记包含工作区改动。未知文件、无映射或取不到比较范围时回退到 full-mvg。这里的 `full-mvg` 仅表示“运行当前选中 manifest 的全部 required_tests”；输出同时携带 `manifest_coverage_mode`、`manifest_scope_id` 和 `manifest_blocking_task_ids`。只有 coverage.mode=full、blocking_task_ids 为空且对应 run 真正 runtime_verified，才有资格描述为该 scope 的 full-MVG 运行证据。所有情况下 required_tests 保持完整；related-first 仅表示优先级建议，当前执行器仍运行全部清单测试。

这是一层独立的回归建议，不是完整调用图，也不替代正式 Impact/KCP。需要覆盖新场景引用、动态加载或信号边时，以真实链路测试和显式路径补充映射；不要把“没有找到边”解释成“不受影响”。无需按任务刷新知识库。

## 可选测试强度实验

```powershell
py -3 scripts/python/run_mvg_mutation_probe.py --snapshot commit --revision HEAD
```

该实验仅在隔离快照中对 RewardEntryModifierPipeline 的两个金币边界施加已知变异。先验证原始基线，再逐个运行冻结的测试，最后恢复快照源码。输出 killed / survived / unverified 及原始证据到 `logs/ci/mvg-mutation/`。这不是全程序变异覆盖率，不作为默认门禁；survived 要调查测试缺口或等价变异，不能自动认定业务错误。可在高风险函数开发时运行，亦可在 MVG 收尾抽样，不必都推迟到收尾。

挖空回填保留为低频人工组织实验：固定原提交、契约和验收测试，在独立临时分支/快照隐藏一个小实现；让实现者仅按契约回填，独立评估者运行冻结测试和额外边界测试。记录原版本、隐藏范围、可见上下文、用例变化和反例。禁止为了通过而修改冻结测试；成功不证明语义完备，失败也要区分规格不足与实现失败。当前不提供自动回填代理或默认门禁。

## CI 与人工验收

`.github/workflows/mvg-integration.yml` 对相关改动先 plan 校验 `m1-full` 目标 inventory，再运行 commit/workspace 两份 `m1-critical` 多 flow 范围，并在 committed critical run 上执行奖励输入断线反例；变异实验仍仅手动选择。只要 `m1-full.coverage.blocking_task_ids` 非空，CI 不得把 critical 通过解释为 full-MVG runtime verified。它不修改分支保护或既有 profile 门禁。构建日志、JUnit/TRX 与摘要一起留存。视觉/手感/平衡/性能代表性仍需要人确认；机器报告不能替代试玩结论。

同一次快照执行仅在首个 Godot 套件预热，成功后后续套件和接线反例复用构建；每套件仍单独启动进程并隔离报告。已有质量流水线负责统一恢复文档门禁，MVG CI 不重复直接调用该门禁。
