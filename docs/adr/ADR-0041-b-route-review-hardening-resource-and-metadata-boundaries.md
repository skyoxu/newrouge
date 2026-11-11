# ADR-0041：B 路线审核修复的宿主资源与元数据恢复边界

- Status: Accepted
- Date: 2026-11-07
- Scope: Story 2.5 / R25 后继实现；Root 定向验证通过，正式 Story 审核另行关闭
- References: [ADR-0038](ADR-0038-mvg-candidate-admission.md)、[ADR-0039](ADR-0039-mvg-completed-capability-recovery.md)、[ADR-0040](ADR-0040-b-route-stages-authority-and-activation.md)、[R25 实施计划](../../_bmad-output/implementation-artifacts/b-route/spec-2-5-independent-admission-bounded-selection.md)

## 背景

正式审核发现：语义迁移检查未关闭本地 helper 依赖；修复缺少可重放的字段域；selector 多文件准备和 intent→父预留之间缺少可前进的崩溃恢复；v3 重复前缀编码及 v2/v3 DAG 展开缺少分配前资源限制。异常清理还可能掩盖原错误和部分输出，未知耗时被误写成零。

原 R22 producer、原三候选、13 次实际请求、资格与 unknown 原件保留。此 ADR 不把历史资格重签给 R25，不更改 ADR-0038/0039 的预算和唯一 selected/checkpoint 所有者，不启用默认 B 路线。

## 决定草案

1. 语义等价按原语义根函数的实际静态依赖闭包比较，包括 `semantic_domain`、`source_key`、其本地 helper、常量与导入绑定。冻结输入读取及请求构造是显式运输/宿主边界，不宣称这些逻辑未变。公共模块仅 `run_isolated_model` 故障边界可有意改变；其他顶层语句及实际引用的纯 helper 必须保持，不将整个公共模块加入宽泛 allowlist。
2. 修复策略为 `newrouge.b-route-repair-scope.v1`。域由原 proposal、宿主 machine diagnostic、语义义务 ID 及原图直接引用导出。模型 rationale 不提供域权限。Requirement 原投影、来源身份、选定依赖和无关 Flow/四部分保持原值；无法定位时拒绝。新机器问题或当前 issue 未减少会拒绝修复，原重试/替换预算照常消耗。准入重放须从同槽位、同 lineage、更早的真实完成预留确认原稿和 finding，递归关闭修复链。
3. 元数据事务版本为 `newrouge.b-route-selector-metadata-transaction.v1`，只扩展原 selector recovery owner。事务先持久化原 source/anchor/epoch/record 身份、精确前后镜像、父 owner 创建的原预留 row、唯一临时文件名。操作均在原 coordinator 锁和 s1 namespace 内执行；已知前态/后态可幂等完成。临时文件须是该事务预定字节的完整值或前缀，原样移入有限证据文件保存；陌生临时文件仍阻断。旧未 journal 的半成品不能凭空补证明。
4. `reconcile` 只恢复元数据，模型调用为零。intent 已有而父 row 缺失不证明未 dispatch；恢复保守完成原第 13 号预留，保留全部占用并以 unknown 终止，不授权新 attempt，不释放额度或重新生成候选。原完成回执不会改成 unknown。该限制针对证据不确定的当前恢复对象，不是平台永久禁止恢复。
5. 宿主资源政策为 `newrouge.b-route-compact-host-resources.v1`，独立于未改的 v1/v2/v3 wire 语法。编码输入上限 8 MiB；展开的保守文本/转义计量总额上限 64 MiB（包括 phrase/shared 缓存与最终值）；展开节点最多 1,000,000，依赖/语法/数据深度最多 128。此计量是分配前保守上界，不是进程 RSS 保证，也不是原模型 1 MiB 窗口。v3 编码工作上限 100,000,000，计入重复前缀扫描、逐字符比较、可见文本证明，以及确定性字面匹配器的构造、转移、失败链接遍历和扫描。达到资源上限明确拒绝，无截断、自动换 codec 或预算扩容。小输入规范字节不变；旧 proof 仍由其原 producer 验证，不能将新政策强加后重签旧证据。
6. 清理异常与原异常分别保存，已经读到的输出按原字节持久化。未知 host 耗时记 `null`，Capability 剩余时间沿原已预留 timeout 保守扣除；可信零仍为零。原费用、unknown 和独立时钟不改。

## 验证与后果

2026-11-07 计量修正：Root 静读发现把任意整数固定计 32 字节及遗漏空对象括号会低估展开。exact-int 现按 bit_length 与大于 log10(2) 的有理上界计算十进制位数并计负号，取 max(32, 上界)，不先构造 str(int)；对象/数组括号和分隔符均进入保守计量。字符串及键先检查 len×6 的饱和上界，再做严格 UTF-8 编码。自建边界样本 {"x":"aaaaaaaaaa"} 的保守成本由有缺陷的 72 修正为 74（62 值、10 键及分隔符、2 括号）；旧 PASS 作为历史实现证据保留，不冒称当前计量结果。资源版本和 64 MiB 等阈值不变，wire 字节、模型/token/调用预算也不变；新增大整数、空容器和编码前止损反例待 Root 定向执行。

实现者仅完成 AST、静态方法计数和文件哈希，未执行测试。磁盘故障注入、DAG/phrase/深度/工作边界、修复域、异常证据及 Windows 真实等待点测试的实际结果和失败历史以 Root 任务日志为准；本轮计量修正仍待 Root 定向复核。100,000,000 是确定性工作量界，不能据此承诺固定墙钟耗时；实际最终 wrapper 仍须经过原容量计量与请求预留。

2026-11-07 字面匹配修正：Root 的 `codec-retained-15` 纯检查发现旧 selector 原包（SHA256 `91784631802598c780450d2178d3297b0757ade18749adda76abdbeab5df1190`）在 canonical 重编码时被 regex 长度乘积预收费拒绝；原包及失败证据保留。现用反向 trie 和失败链接缓存每个状态的最小原备选序号，先反向记录各起点的胜出项，再前向跳过已消费区间。对 codec 的非空字面 phrase 域，行为仍为 escaped-literal regex 的最左起点、同起点原列表首项、非重叠匹配；没有动态 regex 或备用路径。每个构造/转移/失败遍历/扫描步骤都在原共享计数器内，100,000,000 不变。phrase 顺序、保留规则、grammar、digest 与渲染逻辑不变；新增小型差分 oracle 和构造/扫描早停测试，由 Root 执行。Root 已执行26/26个受影响资源、差分及v3方法，并用旧329024字节提示的完整packet完成摘要及精确规范重编码检查，均通过；原100m界限未扩。该纯检查和合成差分仍不属于模型或原 native proof 资格。

此规则会更早拒绝超资源或无法证明修复域的输入，需要 Root 评估实际材料和定向测试。原 high、无工具、原 2/192/96、64 槽位、三次 issue 修复、三轮 replacement、时间限制及 campaign 护栏保持。新的 current 资格、正式采纳、readiness、Task/Flow 运行和 Story 完成均未由本实现授予。

Root 已依据已执行的定向资源/元数据/修复边界测试接受本宿主政策。决策接受、工程验证、原生资格、正式采纳与默认 B 启用分别判断；不重签旧证明或授予运行权限。实际证据见 `logs/ci/2026-11-07/story25-r25-review-checkpoint/`。
