---
title: MVG Capability 增量规划与准入优化
status: final
created: 2026-10-11
updated: 2026-10-11
---

# PRD: MVG Capability 增量规划与准入优化

## 0. 文档目的

本文定义 NewRouge 仓库中 MVG（Minimum Viable Game）规划工作流的优化目标：以当前已选 Capability 版本为主输入，逐个 Capability 生成、修复、审查和评选 MVG 增量，再合并为累计操作动线集合。本文面向工作流维护者、Knowledge/CLI 用户和后续架构与实现阶段。它描述行为和验收结果；具体脚本、JSON schema 和迁移方案见 [addendum.md](addendum.md)。

范围基于 2026-10-11 仓库现实：当前 Capability 文件包含 11 个 Capability；现行流程在每个独立候选中依次处理完整 Capability 列表，最后才比较完整候选；Requirement 的 coverage 目前按全局唯一归属校验。最近的单 Capability 定向测试证明完整证据传输已能通过，但模型生成仍可能在机器准入前因 selector、handoff、Contract/测试边界等格式或结构问题被拦截。**[ASSUMPTION: 11 个 Capability 和现有 133 个任务在本 PRD 实施期间保持不变；变化必须由其 owning workflow 提供新版本。]**

## 1. 愿景与目标用户

MVG 应表达玩家可执行的不同操作动线，而不是按技术模块机械拆分的任务清单。Capability 是逐次规划边界；MVG flow 是可跨越多个 Capability 的玩家旅程。工作流应使每个 Capability 的增量可以独立生成与比较，同时保留所有已确认的累计路线，并能解释每次选择、修复、冲突和合并。

主要用户是运行或维护本仓库规划工作流的开发者。他们需要快速定位失败阶段、避免不合格结构进入语义准入、保护已选累计结果，并在不扩充游戏 GDD 或 Taskmaster 任务的前提下完善 MVG。

## 2. 术语

- **Capability**：由 Capability 规划产物定义的语义分组，是本工作流逐次处理的主输入边界；不是 MVG flow，也不要求一对一转换成 flow。
- **MVG**：描述可验证玩家操作动线及其依赖的累计 manifest。
- **flow / 操作动线**：一个具有可观察结果、必要 handoff、测试和证据绑定的玩家旅程。
- **增量**：当前 Capability 对已确认累计 MVG 的新增或经授权的扩展；不包含重写整份独立 MVG。
- **准入**：候选可以参与比较选择前必须通过的确定性格式/引用/累计校验，以及独立语义硬检查。
- **Requirement 路线引用**：Requirement 与一个或多个不同操作动线之间的关联。多个路线引用同一 Requirement 是允许的，不自动代表重复完成或冲突。
- **累计基线**：依次合并已选择 Capability 增量后的单一 MVG manifest。
- **硬问题**：会使输入不可信、proposal 不可解析/不可追溯、动线结构无效或语义与权威来源冲突，因而不能准入的问题。

## 3. 功能需求

### 3.1 逐 Capability 的累计规划

**描述：** 工作流按显式选定 Capability 文件中的顺序逐项处理。每次只为当前 Capability 建立候选集；后续 Capability 读取已确认的累计 MVG，并可扩展已有 flow 或创建有证据支持的新路线。

**冻结基线：** 本 PRD 使用 `docs/planning/semantic-topology/capabilities.v1.json` 的 SHA-256 `53B0EDBA89E636312447599147A3982D3A4644DAFD6DCBB3BF1E67FA8FE6B61E`，`source_revision` 为 `source-set:68d145756705834e7b664fcc`。处理顺序和 ID 为：

| 顺序 | Capability ID | 标题 |
|---:|---|---|
| 1 | `CAP-CORE-FOUNDATION` | Core Foundation and Contracts |
| 2 | `CAP-RUN-CONTINUITY` | Run Continuity and Resume |
| 3 | `CAP-COMBAT-EXECUTION` | Combat Runtime and Deck Lifecycle |
| 4 | `CAP-ENEMY-INTENT` | Enemy Intent and Resolution |
| 5 | `CAP-RUN-MAP-ROUTING` | Run Entry and Map Routing |
| 6 | `CAP-NODE-EXPERIENCES` | Node Experiences and Rewards |
| 7 | `CAP-COMBAT-INTERACTION` | Combat Interaction and Feedback |
| 8 | `CAP-RELIC-POWER-POTION` | Relics, Powers, and Potions |
| 9 | `CAP-RUN-SUMMARY` | Settlement and Run Summary |
| 10 | `CAP-DELIVERY-GOVERNANCE` | Quality, Security, and Delivery Governance |
| 11 | `CAP-LOCALIZATION-ACCESSIBILITY` | Localization and Accessibility |

该顺序是当前 Capability 产物的权威输入顺序，不代表产品优先级；文件 hash 或顺序变化时必须启动新的规划基线，不得把新文件伪装成同一版本。**[ASSUMPTION: 上述 Capability 文件在本 PRD 实施期间保持冻结。]** 每个 Capability 还必须绑定 Chapter 5 readiness 产物的路径、版本/hash 和 ready 判定；ready 证据漂移时，当前基线失效并阻止生成。

#### FR-001：单 Capability 候选生成

工作流必须为当前 Capability 生成三个独立上下文的 MVG 增量候选；不得要求每个候选从头重建所有 Capability 的完整 MVG。**[ASSUMPTION: 三个候选沿用当前仓库的候选数量约定，除非后续成本证据触发显式变更。]**

**可验收结果：**
- 一个候选只声明当前 Capability 范围内的增量，且绑定 Capability ID、文件哈希、Requirement 范围、准备证据身份和累计基线哈希。
- 三个候选彼此隔离；候选之间不共享模型上下文、未准入 proposal、prompt、finding 或 workspace。
- 同一 Capability 处理期间不启动下一 Capability。
- 每个 Capability 完成评选并合并后，工作流才进入顺序中的下一个 Capability。

#### FR-002：增量评选与累计合并

工作流必须在当前 Capability 的三个合格候选之间进行比较，选出一个增量，并将其以可审计、可重放的方式合并到累计 MVG。

**可验收结果：**
- 只有通过准入的候选可见于比较器；候选不能因硬问题而参与比较。
- 未入选的合格候选只能因为相对评分较低而落选。
- 选择记录绑定候选 proposal 哈希、Capability 身份、基线哈希、评分输入/输出和模型 receipt。
- 合并后累计 manifest 通过完整确定性校验；合并失败不改变已确认基线。
- 同一候选/同一基线的恢复不得重复应用增量。
- 如果修复和 replacement 结束后合格候选少于三个，当前 Capability 进入 `selection_blocked_insufficient_admitted_candidates` 终态；不使用不合格候选补位、不自动把 incumbent 当作缺失候选、不推进下一个 Capability。恢复必须从 immutable prepared inputs 重新开始，并保留失败原因。

#### FR-003：累计路线连续性

当前 Capability 的候选必须把已确认 MVG 作为只读累计上下文；可以在有依据时扩展现有 flow，但不得静默删除、弱化或改写已确认路线、handoff、测试和 outcome。

**可验收结果：**
- 新增、扩展、替换或退役累计内容均有精确对象地址和准备好的来源依据。
- 无权威变更依据时，旧的有效映射和测试保持不变。
- 增量合并使用候选基线哈希做并发/漂移检测；基线变化时旧候选不能直接应用。

### 3.2 Requirement 与多条操作路线

#### FR-004：允许跨路线重复引用 Requirement

同一 Requirement 可以被多个不同操作动线引用，因为不同 MVG flow 表达不同用户路径。系统不得仅因路线引用重复而拒绝候选。

**可验收结果：**
- Requirement-to-flow 关联支持一对多/多对多，并能区分路线成员关系与验证/完成状态。
- 某 Requirement 出现在多个 flow 中时，各 flow 必须说明该 Requirement 在本路线中的具体可观察作用，不得以重复引用替代路线行为。
- 全局 coverage 汇总能够指出 Requirement 被哪些 flow 引用及其权威验证/处置证据，且不把路线引用数计成多次完成。
- 未知 Requirement、无效 flow 引用或重复的同一关联仍被拒绝。

#### FR-005：Requirement 语义所有权与验证记账

工作流必须保留 Requirement 的权威来源和可审计验证状态，同时允许多个路线引用；路线引用不得自动创建第二份独立 Requirement，也不得覆盖权威 GDD/Requirement 定义。

**最小记账契约：** `requirement_route_memberships` 的唯一键为 `(requirement_id, flow_id)`；同一键重复是结构错误。`requirement_verification` 的唯一键为 `requirement_id`，每个 Requirement 只能有一条权威 disposition；验证证据以 `(requirement_id, evidence_id)` 去重，允许多个 flow 共享同一证据，但报告必须标明共享范围。路线引用数量不得增加 Requirement 的完成计数；旧 `coverage_table` 迁移时保留唯一权威 verification 行，并将旧 owner 转成 route membership/owner metadata。

**可验收结果：**
- 规划结果能区分“Requirement 归属/路线引用”与“Requirement 的验证 disposition/evidence”。
- 一个 Requirement 可由多个 flow 提及，但总览不会因重复引用而丢失、重复计数或被标为多次完成。
- `flow`、`other_verification`、`deferred`、`source_gap` 等处置仍由合法证据支持；不允许通过删掉重复行逃避路线覆盖。

### 3.3 生成前质量门与准入

#### FR-006：生成输入与证据完整性门

模型调用前，工作流必须确定当前 Capability 的完整核心输入、辅助证据、累计基线、schema 和路径域都可被当前调用消费；不能截断或以摘要替代源证据。

**可验收结果：**
- 输入、证据分片、路径、hash、行号引用和 runner receipt 的完整性在生成/审查调用前验证。
- 证据分片按顺序可精确重组，所有字符均有唯一来源；缺失、重复、乱序、越界或 hash 不匹配均在调用前阻断。
- 所有必要批次通过 preflight 后才开始该阶段的模型调用。
- 核心上下文或全部证据检查结果无法在 runner 限制内完整传输时，run 明确失败并报告阶段/大小，不静默裁剪。
- 失败 proposal 的 transport 产物不能被新上下文复用。

#### FR-007：进入语义准入前的机器完整性检查

语义准入调用必须只接收格式和结构已通过确定性校验的 proposal。模型提示文字不能代替 schema 和本地验证。

**可验收结果：**
- 输出 JSON 可解析、schema/identity 正确、必填字段齐全、无未知字段、枚举和基本类型有效。
- Flow、test、coverage、entrypoint、review ID 满足唯一性和合法 ID 规则；引用对象必须属于当前 prepared snapshot 或明确允许的 planned 域。
- C# selector 只能是从对应测试源码识别出的类名；方法名、方法列表、过滤表达式和 wildcard 不得进入语义准入。
- Test 必须归属有效 flow；Flow 引用的 test 必须存在且范围一致。
- 每个 handoff 必须具备真实 producer/consumer/owner、行为、已准备 Contract 以及关联测试；只有当 flow 存在真实跨系统边界时才要求 handoff，不得强造 handoff。
- Existing verified entrypoint 必须在准备证据中存在且 symbol 可验证；planned entrypoint/test 必须具备真实 owner、路径/目标、输入状态、断言和实现验收。
- 所有 Requirement 路线关联和 verification disposition 都在当前 Capability 与冻结累计范围内；重复路线引用允许，但同一关联重复、引用越界或丢失权威 Requirement 记录不允许。
- 任一机器问题未修复时不启动独立语义审查；机器检查结果和阻断位置可定位到字段/对象。

#### FR-008：局部修复与上下文重启

机器门或独立语义硬检查发现问题时，工作流必须尝试在当前 Capability 内局部修复，不得把不合格候选送去评选。

**可验收结果：**
- 对稳定硬问题逐项修复，每个问题最多三次；每次只修改目标对象及必要依赖。**[ASSUMPTION: 三次修复和现行 64 次 lineage stop-loss 在首版保持不变，不通过提高预算掩盖结构问题。]**
- 每次修复后重新执行机器校验；仅当前硬问题减少且没有新增机器/语义缺陷时，修复才原子接受。
- 修复不得改动无关有效路线、coverage、handoff 或测试。
- 三次仍无法修复时，当前 lineage 退役；新上下文只读取不可变准备输入和已确认累计基线，不读取失败上下文内容。
- 不能因失败跳过 Capability。达到既有 lineage 总调用 stop-loss 时应停止并分类为预算/执行失败，不宣称语义失败或自动扩大预算。
- 输入准备、证据完整性和 runner 执行故障与候选内容硬问题分开分类；前者不得让模型尝试修数据源。

### 3.4 跨 Capability 冲突与最终审计

#### FR-009：跨 Capability 冲突治理

默认由当前 Capability 的增量适配已确认累计路线。只有全局审计发现有权威证据支持的真实硬冲突时，才允许显式重开受影响的早期选择。

**可验收结果：**
- 不因一般重复、共享 Contract、共同 Requirement 或路线交叉自动判为冲突。
- 冲突报告区分：重复引用、路线重叠、owner/Contract 不一致、真实互斥语义和证据不足。
- 重开早期选择必须记录冲突证据、受影响 Capability/flow、重开理由、失效的下游增量和重选结果；不得静默重选。**[ASSUMPTION: 全局审计可以区分局部可修复问题与必须重开的真实权威冲突。]**
- 不允许静默自动改写历史选择；未解决硬冲突时累计 MVG 不可标记完成。

#### FR-010：整批完成后的全局一致性审计

全部 Capability 增量完成后，工作流必须对最终累计 MVG 执行一次全局机器审计，检查局部准入无法独立判断的跨路线关系。

**可验收结果：**
- 审计覆盖累计路线、Requirement 多路线引用、handoff producer/consumer、共享 Contract、test 所属关系、基线变更、来源完整性和身份链。
- 全局审计不得把局部通过等同于游戏运行时已验证；`runtime_verified` 只能由正式 MVG acceptance 运行产生。
- 审计报告提供通过项、真实硬冲突、待实现义务、证据缺口和未执行的运行时验证，彼此分类。
- 只有全局硬检查通过且所有增量 proof/selection/merge receipt 可重放时，累计结果才标记为规划完成。

### 3.5 记录、恢复与边界

#### FR-011：端到端过程可审计与可恢复

工作流必须将准备、模型调用、修复、准入、评选、合并、重启、冲突重开和最终审计记录到 run 日志中，并允许从一致的已提交阶段恢复。

**可验收结果：**
- 每个事件记录 Capability、候选/lineage、阶段、attempt、错误类型、开始/结束结果、输入输出 hash 和前置基线身份。
- 恢复只能复用 hash 完全匹配且本工作流允许复用的已接受阶段；用户发起新 run 时不复用旧模型证据。
- 日志能解释候选为何不能进入准入、为何某候选落选、为何某增量未合并或为何需重开早期选择。
- 工作流产物与游戏运行时状态、任务状态分离；运行状态不得被规划候选写回。
- 每次 Capability 选择 checkpoint 必须记录候选集合、准入结果、选择结果、输入/基线 hash、合并 receipt 和下一 Capability 的 seed；少于三个合格候选时记录上述终态而不产生 checkpoint。

#### FR-012：保持项目权威来源和任务范围

MVG 优化不得扩充游戏 GDD、Requirement 或现有 133 个任务，也不得把派生产物错误提升为权威输入。

**可验收结果：**
- Capability 是当前 MVG 生成的显式选定主输入；GDD/Requirement、Chapter 5 readiness、Taskmaster 三联、Contract、测试和 manifest 按其权威角色提供佐证。
- 任何 requirement/任务源变化必须经相应 owning workflow，不由 MVG 推断并新增任务。
- 不改变 Chapter 6/7 的任务执行和游戏运行时代码。
- 按当前知识库与本地规划约定记录派生产物，不隐式将本机缓存或临时候选变成 canonical main 产物。

## 4. 非目标

- 不增加、重写或扩充 GDD 中的游戏玩法、Requirement 或现有 133 个 Task。
- 不修改游戏代码、资源、Godot 场景、运行时玩法或实际 runtime acceptance。
- 不把一个 Capability 固定转换成一个 flow；也不把每个 Task 转换成运行时入口。
- 不因重复 Requirement 路线引用而自动复制 Requirement 本身、测试结果或完成状态。
- 不让被机器拒绝的候选进入比较选择；不允许比较器替代硬性准入。
- 不依赖 prompt 保证格式，不通过截断/摘要来规避上下文限制。
- 不要求 Knowledge UI 必须在本 PRD 实施；UI 暴露方式属于待决实现边界。

## 5. MVP 范围

### 5.1 包含

- 用 11 个当前 Capability 对现有规划数据做兼容性分析和迁移设计。
- 构建逐 Capability、三个候选、准入后选择、原子累计合并的工作流。
- 支持 Requirement 与多个操作路线关联，同时保留权威 requirement/verification 记账。
- 将可确定的 schema、selector、ID、引用和 flow/test/handoff 关系校验前移到语义审查之前。
- 依据完整当前来源进行候选生成和审查，保留不截断的 hash-bound 证据传输。
- 局部三次修复、干净 lineage 重启、停止损失和可恢复审计日志。
- 全 Capability 完成后的累计一致性审计及与 runtime acceptance 状态的明确区分。
- 对旧 `coverage_table` 独占归属数据进行兼容读取/迁移方案；禁止无损失迁移前覆盖原 manifest。

### 5.2 不包含

- 修改当前游戏 GDD 或创建额外游戏任务。
- 自动改变 Capability 分组或自动重新生成 Capability。
- 新建第二套任务状态、第二套 Chapter 5 或独立 MVG 生命周期。
- 自动解除当前 candidate/repair/lineage 的模型调用上限。
- 在没有明确决策前重做网页 UI、Knowledge 拓扑页面或本地服务 API。
- 把“计划准入”显示为“运行时通过”。

## 6. 成功指标

- **SM-1（准入洁净度）**：进入独立语义准入的 proposal 中，schema、ID、selector、引用、flow/test/handoff 结构类错误为 0。验证 FR-006 至 FR-008。
- **SM-2（完整性）**：接受的每个 increment 都有完整 Requirement/证据/基线 identity 和可验证 receipt；被截断或身份不匹配的输入进入模型语义审查次数为 0。验证 FR-006、FR-011。
- **SM-3（累计安全）**：每次选择和合并均可重放；没有基线 hash 匹配或没有 proof 的增量被应用次数为 0。验证 FR-002、FR-003、FR-011。
- **SM-4（路线表达）**：同一 Requirement 可由多个不同 flow 引用，且全局报告能区分路线成员关系与权威验证记账。验证 FR-004、FR-005。
- **SM-5（恢复边界）**：硬问题修复、lineage 重启和跨 Capability 重开均有事件记录；失败 lineage 的上下文内容复用次数为 0。验证 FR-008、FR-009、FR-011。
- **SM-6（成本与时长可见）**：每 Capability 记录模型调用数、阶段耗时、重试原因和结果；每次 run 开始前绑定显式总调用上限并记录其来源，达到上限必须阻断且可恢复。反指标：为追求准入率而降低完整性校验、绕过硬问题或放宽证据约束。

## 7. 约束与依赖

- 必须沿用 `docs/workflows/mvg-integration-acceptance.md`、`workflow.md` 第 5.4 章和 `.agents/skills/plan-mvg/SKILL.md` 的 owning boundaries，并在批准后统一更新。
- 当前脚本入口包含 `scripts/python/plan_mvg.py`、`scripts/python/_mvg_capability_generation.py`、`scripts/python/_mvg_capability_append.py` 和 proposal/admission 校验路径。
- Requirement 与 flow 的多对多关联会影响现有 manifest schema、coverage validator、delta/apply、Knowledge 汇总和测试夹具；不能只改 prompt 或一处 validator。
- 输入完整性继续使用隔离 runner、完整传输、hash/receipt 和 preflight；不得固定指定不同于环境默认的模型。
- 预算、三次修复及三个候选是当前工作流参数。64 次 stop-loss 仍是单个 candidate lineage 的上限；逐 Capability 拆分不得静默把它乘以 Capability 数量。每次 run 必须在开始前取得正整数 `mvg.run_invocation_limit`（配置文件或操作员输入；首版默认值为 `192`，即三个 candidate lineage 各 64 次的总上限），并将该值、来源和 `run_id` 写入运行元数据；统计范围包含该 run 的生成、证据检查、修复和语义准入调用，跨所有候选与 Capability 汇总。缺少或无效上限则拒绝启动，达到上限则进入可恢复的 `run_blocked_budget_exhausted` 终态，不得静默扩大预算或把预算耗尽伪装成语义拒绝。
- 运行环境和仓库操作遵从 AGENTS.md；执行记录落入 `logs/**`。

## 8. 开放问题

1. 首版不把全范围 incumbent 作为第四个候选；当前 accepted MVG 只作为只读累计底座。若未来要比较 incumbent，必须先抽取相同 Capability scope 的 delta 并通过同一准入门。
2. 首版复用当前比较器，但选择输入必须是同一 Capability scope 的合格增量，并同时评价增量质量、累计影响和路线连续性；不得按 JSON 顺序或候选编号决定胜负。
3. 多 flow 引用同一 Requirement 时，哪些路线需要各自独立测试，哪些可以共享一项验证证据？建议由语义边界和可观察行为决定，不机械要求每条路线复制测试。
4. 知识库页面是否需要展示逐 Capability 进度、候选、失败类型和历史选择，或首版仅通过现有页面和 run artifacts 提供操作？
5. 全局审计触发显式重开时，使用哪一种受控操作入口以及如何取得操作者确认，留给架构/UX 阶段；任何入口都必须保留冲突证据、影响范围和下游重建计划。

## 9. 假设索引

- §0/§5：当前 Capability 数量和任务范围以 2026-10-11 工作区现状为基线；MVG 优化不创建游戏任务。
- §3.1：每个 Capability 使用三个候选，沿用仓库当前 candidate 数量；如果未来调整，需根据实测成本重新确认。
- §3.3：每个硬问题三次修复、lineage 当前调用 stop-loss 沿用仓库现行政策，不在本 PRD 提高。
- §3.4：跨 Capability 冲突默认只修当前增量；只有证据支持的全局硬冲突才显式重开早期选择。
- §6：质量指标要求失败数为零，但首版没有新的时间/费用数值目标。
- §3.1：Capability 基线冻结为 `capabilities.v1.json` 的路径、source revision、hash、11 个 ID 和给定顺序；变更启动新的规划基线。
- §3.1/§3.3：候选不足时阻断当前 Capability；不使用不合格候选或 incumbent 补位，失败 lineage 不得跳过 Capability。
- §3.2：路线成员关系与权威验证记账分离，分别按 `(requirement_id, flow_id)`、`requirement_id` 和 `(requirement_id, evidence_id)` 去重。
- §3.4：跨 Capability 默认修当前增量，真实硬冲突才显式重开早期选择；重开必须有证据和完整影响记录。
- §7/§8：共享 evidence 的 disposition/route-scope 字段、页面进度呈现和全局冲突重开入口留给架构/实现阶段；incumbent 角色、选择 rubric、run-level 预算键和耗尽终态已按首版规则收敛。
