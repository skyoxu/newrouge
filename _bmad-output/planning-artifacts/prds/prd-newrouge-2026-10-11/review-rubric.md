# PRD Quality Review — MVG Capability 增量规划与准入优化

## Overall verdict

**adequate，带高优先级修订项。** 这是一份形态匹配内部工作流的 PRD：它清楚描述了当前流程与目标流程的差异，且对逐 Capability 生成、三候选准入、Requirement 多路线引用、唯一验证记账、局部修复和真实硬冲突显式重开给出了可验收方向。当前还不宜直接作为实现放行依据，主要因为 11 个 Capability 的基线身份/顺序不可复现，三候选无法全部准入时没有完成与停止语义，且 Requirement 验证唯一性与预算语义仍停留在概念或开放问题层面。

## Decision-readiness — adequate

核心决策已经写成行为要求：按 Capability 顺序增量处理（§3.1），只有准入候选可比较并原子合并（§3.1），路线引用与验证记账分离（§3.2），跨 Capability 默认局部修复、只有证据支持的真实硬冲突才显式重开（§3.4）。addendum 的“当前仓库现实 / PRD 目标”表（addendum §1）也让迁移方向可以被决策者快速理解。

但实现放行所需的几项决定仍未闭合。11 个 Capability 只以数量和“显式选定文件”出现，没有文件路径、版本/hash、ID 及顺序；候选预算、incumbent 是否参与比较、选择 rubric 和全局冲突重开入口在 §8 仍是开放问题，addendum §2/§5 还明确指出 64 次预算的累计语义未定。

### Findings

- **high** 11 Capability 基线无法复现（§0/§5.1；addendum §1）— 文档只说“当前 Capability 文件包含 11 个 Capability”，没有给出 canonical 路径、版本/hash、完整 ID 列表或处理顺序，决策者无法确认迁移覆盖面。*Fix:* 绑定冻结的 Capability 文件路径、版本/hash、11 个 ID 与顺序，并引用对应 Chapter 5 readiness 或生成产物。
- **high** 候选不足时没有可执行决策（FR-001/FR-002/FR-008；addendum §2）— PRD 要求每个 Capability 有“三个合格候选”，但未规定修复/stop-loss 后少于三个候选时是重试、停止当前 Capability、使用 incumbent，还是标记 run 失败。*Fix:* 定义候选数量不足的状态、停止条件、恢复边界和审计记录；不要让“达到选择条件”成为隐含条件。
- **medium** 现实差异有清晰叙述，但证据定位不足（§0；addendum §1）— 表格准确说明了现有顺序、coverage、准入和恢复差异，但“最近第三 Capability 21 批证据检查通过”等现实依据没有 run/log/hash 引用。*Fix:* 为每个现状断言附可重放的日志、测试或 manifest 证据 ID，并注明观察日期与范围。

## Substance over theater — strong

内容明显服务于工作流问题，而不是模板填充。§3 的 FR 直接处理 proposal 结构门、证据完整性、delta replay、路线成员关系、验证 disposition、lineage 隔离和冲突审计；addendum 进一步给出当前实现与目标差异、数据模型候选和回归证明方向。没有无决策作用的 persona、创新或泛化 NFR 段落，且“计划准入不等于 runtime acceptance”在 §4/§6 被明确区分。

### Findings

- **medium** 成本目标被有意延后，但成功标准因此不完整（SM-6；addendum §2/§5）— “记录调用数和耗时”是可观测性要求，不是成本/时长完成阈值；addendum 已指出逐 Capability 复制 64 次预算可能放大总成本。*Fix:* 在实现放行前至少确定 run-level 预算上限、确认点和超限结果；若确实延期，应把它明确列为 MVP 外的验收缺口。

## Strategic coherence — adequate

PRD 有统一主张：MVG 表达玩家可执行的操作动线，Capability 只是逐次规划边界，累计 baseline 通过可审计增量推进（§1、§3.1）。SM-1 至 SM-5 分别验证准入洁净度、输入完整性、累计安全、路线表达和恢复边界，和这一主张一致；§4/§5 也保持了不改 GDD、Taskmaster、运行时代码的范围纪律。

战略取舍仍缺少对 11 个 Capability 顺序的理由。当前顺序被当作输入事实，文档没有说明它是既有权威顺序、依赖拓扑顺序还是仅为迁移顺序；因此无法判断该顺序是否服务于“累计路线连续性”这一主张，或只是复刻当前实现。

### Findings

- **medium** Capability 顺序缺少战略依据（§3.1、§5.1）— “按显式选定 Capability 文件中的顺序”保留了顺序，却没有说明顺序的权威来源、依赖约束和变更政策。*Fix:* 在基线清单中注明顺序来源及不可变/可变规则；若顺序只是兼容迁移策略，明确其与产品路线优先级无关。

## Done-ness clarity — adequate

FR-001 至 FR-012 均有验收结果，且大量条件是机器可判定的：hash/receipt、ID/selector、flow-test 双向归属、handoff producer/consumer、基线漂移、原子合并和审计分类。§6 的 SM 也回链 FR，addendum §7/§8 给出“格式错误不进入 semantic call”“delta 失败不部分写入”等回归证明方向，工程师能据此建立测试矩阵。

仍有三处会阻碍“完成”的判定：三候选不足时无终态；多路线共享验证时的唯一证据身份、去重键和计数规则未定义；SM-6 没有数值阈值。此外，“有依据”“完整”“必要”等词在跨来源场景下需要绑定具体证据字段或 validator 规则。

### Findings

- **high** Requirement 验证唯一性仍不可执行（FR-004/FR-005；addendum §3）— 文档正确要求路线 membership 与 verification disposition 分离，也禁止重复完成计数，但只给出建议性字段名，没有定义 Requirement、route、verification evidence 的唯一键、共享证据的计数规则或迁移后的反向校验。*Fix:* 规定稳定主键/复合键、verification disposition 状态转移与去重算法，并为“同 Requirement 多 flow、共享一项证据、重复同一关联”各给出验收夹具。
- **medium** 部分“完成”条件仍依赖未定义词（FR-003/FR-006/FR-007）— “有依据”“完整核心输入”“真实 producer/consumer”“必要批次”等没有对应字段级判据。*Fix:* 将这些词映射到 prepared-input 清单、source hash、owner/Contract 状态和 preflight 结果码。

## Scope honesty — strong

范围边界写得诚实：§4 明确排除游戏玩法、任务、运行时 acceptance、第二套生命周期、静默重选和 prompt-only 方案；§5.2 再次声明不自动提高预算、不在无决策时重做 UI，并明确规划准入不等于运行时通过。addendum 开头把机制和迁移内容标为“待架构/实现阶段验证的建议”，§8 的五项开放问题也没有伪装成已决定事项。§9 提供了假设索引，能让读者识别日期基线、候选数、修复次数和冲突策略的前提。

### Findings

- **medium** 假设有索引但缺少内联标记和来源回链（§0、§3、§5、§6、§8、§9）— 清单要求推断使用 `[ASSUMPTION]` 标记并可往返核对；本 PRD 主要依靠“§x”索引，读者在正文中不能立即区分已确认事实与日期基线假设。*Fix:* 对 11 Capability 数量、133 个任务、三候选、64 次 stop-loss 和“当前顺序”加内联 `[ASSUMPTION]` 或直接引用冻结来源，并保持 §9 一一对应。

## Downstream usability — adequate

作为链顶内部工作流 PRD，它提供了稳定术语、连续 FR-001 至 FR-012、SM-1 至 SM-6、明确的 owning workflow/脚本/测试边界（§7；addendum §6），也说明不需要为单操作员工作流强行增加用户旅程。FR 与 SM 之间的回链足以支持初步架构和测试拆分。

下游仍无法仅凭该 PRD 生成可复核的 Capability 迁移任务：11 个 Capability 的身份和顺序未列出，Requirement route membership 与 verification 的字段/主键仍是 addendum 的建议，三候选/预算/选择器的缺口也会影响 story 的验收条件。§8 的开放问题如果不在架构阶段收敛，容易把决策转移给实现者。

### Findings

- **high** 缺少可消费的 Capability 基线清单（§0、§5.1、§7）— 架构、迁移和测试无法为每个 Capability 建立稳定回链，也无法验证“11 个”是否覆盖完整。*Fix:* 增加带 ID、顺序、来源 hash、Chapter 5 readiness 绑定和预期增量边界的基线表；表格成为唯一引用入口。
- **high** Requirement 路线与验证模型尚未达到 story 级清晰度（FR-004/FR-005；addendum §3）— 概念拆分明确，但缺少稳定字段、唯一性约束、共享证据范围和旧 `coverage_table` 到新模型的逐项映射。*Fix:* 在架构输入中补充最小数据契约和迁移验收样例，PRD 至少固定这些不可改变的语义不变量。

## Shape fit — strong

这是面向工作流维护者、CLI/Knowledge 用户的内部工具/技术能力 PRD，采用 capability-first 的需求形态合适。它没有为了模板增加消费者 persona 或命名用户旅程，而是把操作员真正关心的失败阶段、证据完整性、恢复、累计保护和审计解释写进 FR；§1、§4、§7 的受众、非目标和边界彼此一致。对 brownfield 现实也有明确当前实现差异表和脚本/测试落点。

### Findings

无。

## Mechanical notes

- Glossary 基本稳定：Capability、MVG、flow/操作动线、增量、准入、累计基线、硬问题均在 §2 定义并按同一含义使用；正文偶尔混用小写 `requirement/verification` 与首字母大写 `Requirement`，实现文档应统一。
- ID 连续性良好：FR-001 至 FR-012、SM-1 至 SM-6 无重复或缺号；没有 UJ，因此不存在命名 protagonist 缺失。
- Assumptions Index 存在且覆盖主要假设，但正文没有对应 `[ASSUMPTION]` 内联标签，往返校验应在下一轮修订时补齐。
- 必要结构适配内部工作流：目标/术语、功能需求、非目标、MVP、成功指标、约束依赖、开放问题和假设均存在；缺少用户旅程在本产品形态下不是缺陷。

## Severity counts

- critical: 0
- high: 6
- medium: 7
- low: 0
