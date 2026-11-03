# 架构对抗审阅

- Verdict: Pass
- Severity counts: P0=0, P1=0, P2=0
- 审阅对象：`ARCHITECTURE-SPINE.md`、`planning-records.md` 的目标架构合同。
- 范围：检验能否构造遵守全部已声明 AD、却发生跨单元不兼容、绕过、死锁或损坏复用的实现；不将新增 B 能力尚未实现记为缺陷。

## 对抗结果

本轮未找到成立的可执行反例。以下攻击均需要违反已有合同才能产生故障，因此不记 finding。

| 攻击 | 反例尝试 | 已有阻断条件 |
| --- | --- | --- |
| 各阶段各造一种公共格式 | 3B 将 revision 同时用于 plan 与 binding，3C 自行解析；或分别定义 Flow／共享状态 owner | 主干 AD-3 与伴随合同「记录与写入归属」要求同一 schema／codec 先于消费者落地；两类修订分别引用，Flow／共享命令／状态唯一 owner，冲突阻断。不能以缺少完整 JSON Schema 代码判定消费者有权另造格式。 |
| 缺来源退回 A，或零 Task 初始化循环 | 删 origins／trace 后走旧入口；bootstrap 为满足 Task 门禁制造假 Task | AD-2、5、6 与「Task 来源分类和非 Flow」要求先验证 policy／catalog／origins，冻结 A 定义与完整反向索引共同分类；「记录与写入归属」明确允许空 origins／空冻结 A 集合，仅 Task 消费才路由分类。 |
| Task 状态变化污染语义身份或 journal 回放倒退进度 | 一方对整份 task 文件 raw hash 判断新鲜度，另一方忽略状态；恢复将历史 after 覆盖当前 done | AD-7、10 与「引用、类型及内容身份」区分原始提交证明、每 Task 定义投影及实时资格；初版只允许排除 Task／subtask 的 status。完成操作只复验，不重写；未完成操作按严格前像停止／重新派生。两种不兼容实现不能同时满足这些条款。 |
| 多 scope 提交与执行互相穿越 | 对共享 Task 增加新 plan 时仅锁新 scope；消费旧 catalog 后跨越并发绑定替换；持 metadata 锁等待长期任务 | 「共享 apply 与恢复协议」明确要求共享 Task 当前和新增 scope 的完整租约集合，同 scope 绑定替换与执行租约互斥；metadata 锁短持有、按稳定 scope 次序取租约、取不到返回冲突，副作用／恢复边界重验。依赖变化不能被称为无关 scope 变化而豁免。 |
| journal／catalog 半提交被 clone 或旧消费者使用 | receipt 写成便放行；删 pending；只检查 B marker 而忽略 capability apply marker；恢复覆盖后编辑 | AD-8 与共享协议要求目标／authority 复验后才发布单一 catalog；消费者复验 receipt、实际相关目标和 catalog 前后身份，适用 pending 先恢复消歧。旧 capability marker 明确纳入 gate，clone 不因 logs／pending 缺失就豁免提交链核验。 |
| 清理后复活撤销候选，或清理误删正式采纳 | 用相同内容命中跳过 epoch／reopen；反向把 local clear 当作撤销版本化语义／累计回归授权 | AD-9、伴随合同 L63 区分本地恢复／显示／发布资格和正式采纳／基线；旧 checkpoint 只可作为历史冻结 proof，不能伪装当前准入；正式来源语义改变仍须更新／失效采纳及绑定。该区分符合 ADR-0039。 |
| recommend 冒充实际选择范围，或共享测试去重漏验新义务 | 执行器忽略 VerificationScope，报告只列已通过测试；旧 Flow PASS 代替新增义务；拼接不同 snapshot | AD-10、11 与「影响与执行范围接口」要求真实执行同一范围或更大保守集合，并回执 requested／executed／not_run／manual／coverage；三类义务分别保留，同一 Flow 可同时有既有和新增义务。共享测试去重包含输入、语义、环境及同一整合 snapshot，缺项／跳过／新增未完不得 PASS。 |

## 核实范围与限制

核对了 SPEC 及验证 companion 对相关输入、三类义务、两层验证和恢复的约束；实际源码抽查了 `scripts/python/_mvg_capability_recovery.py` 的 epoch／revoke／历史核验、`scripts/python/_mvg_global_audit.py` 的 source-backed reopen 边界、`scripts/python/_mvg_requirement_accounting.py` 的正式 receipt／inventory／snapshot 核验，以及 `scripts/python/_mvg_execution.py` 的实际测试选择和正向报告证据。该抽查用于确认继承边界，没有把旧实现中的能力等同于新增 B 实现完成。

本次未运行 Windows／Godot／故障注入测试，也未实施 schema、提交服务或消费者适配。Pass 表示当前目标合同未发现需要架构回补的实际漏洞；后续实现仍须履行主干 AD-17 与伴随合同末尾已规定的默认切换前反例验证。
