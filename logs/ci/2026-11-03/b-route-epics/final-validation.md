# B路线 Epic／Story最终文档校验

**结果：PASS，0项未关闭检查；epics.md保持draft，等待最终C完成工作流。**

范围为已批准的5个Epic、49个Story、256组验收场景。逐项对账18条FR、11项质量约束、28项架构要求及23项原始AC；原始证据与批准快照均保存。此校验不等于实现、Chapter5就绪或Windows／Godot运行验收。

## FR验收意图覆盖

| FR | 核对结论 | Story／AC定位 |
| --- | --- | --- |
| FR-1 完整来源记账 | 累计来源、逐块去向、验收意图及无损分批；未选Flow／Task的需求保留。 | Story 2.1 AC-1、Story 2.1 AC-2、Story 2.1 AC-3、Story 2.1 AC-4、Story 2.3 AC-3、Story 5.2 AC-1、Story 5.2 AC-6 |
| FR-2 独立来源审计前移 | 独立审计以完整来源定界，捕捉首轮遗漏；Chapter5继续Task／契约核对，相关变化复验。 | Story 2.2 AC-1、Story 2.2 AC-2、Story 2.2 AC-3、Story 2.2 AC-4、Story 2.2 AC-5、Story 3.7 AC-1 |
| FR-3 零 Task 的正式规划与合法非 Flow 去向 | 无Task／witness正式准备与采纳、零Task bootstrap、合法非Flow及必需依据缺失反例。 | Story 2.3 AC-1、Story 2.3 AC-2、Story 2.4 AC-4、Story 2.7 AC-4、Story 2.10 AC-1、Story 5.2 AC-6 |
| FR-4 Flow 语义及四部分职责 | 起终点／分支／循环／四部分／owner与多路线关系，机器检查与独立语义准入分开。 | Story 2.4 AC-1、Story 2.4 AC-2、Story 2.4 AC-3、Story 2.4 AC-4、Story 2.4 AC-5、Story 2.5 AC-1、Story 3.4 AC-1 |
| FR-5 持久采纳与稳定身份 | 持久身份与不可变修订、采纳差异、catalog提交及恢复；Task／契约承接保同Flow身份。 | Story 2.6 AC-1、Story 2.6 AC-2、Story 2.7 AC-2、Story 2.7 AC-3、Story 2.7 AC-4、Story 2.8 AC-1、Story 2.8 AC-2、Story 2.9 AC-1、Story 3.2 AC-2 |
| FR-6 从真实缺口生成或复用任务三联 | 复用盘点→真实缺口→业务视图审阅编译，完整三联／Acceptance／依赖与状态保护。 | Story 3.1 AC-1、Story 3.1 AC-2、Story 3.1 AC-3、Story 3.1 AC-4、Story 3.2 AC-1、Story 3.2 AC-2、Story 3.2 AC-3、Story 5.3 AC-1、Story 5.3 AC-2、Story 5.3 AC-3 |
| FR-7 分阶段细化四部分与绑定 | 3B逻辑、3C Task、4–5命令／只读状态／契约／资源／义务逐步细化，planned不冒实现。 | Story 2.4 AC-1、Story 3.2 AC-2、Story 3.4 AC-1、Story 3.4 AC-2、Story 3.4 AC-3、Story 3.4 AC-4、Story 3.6 AC-1、Story 3.6 AC-2、Story 3.6 AC-3、Story 3.6 AC-4、Story 3.6 AC-5 |
| FR-8 一致的 readiness 与验证适用性 | 共同输入、readiness、Flow／非Flow与owner适用差异；缺失／过期／损坏同源拒绝。 | Story 3.3 AC-1、Story 3.3 AC-2、Story 3.3 AC-3、Story 3.3 AC-4、Story 3.5 AC-1、Story 3.5 AC-2、Story 3.5 AC-3、Story 3.5 AC-4、Story 3.6 AC-1、Story 3.6 AC-2、Story 3.6 AC-3、Story 3.6 AC-4、Story 3.7 AC-1、Story 3.7 AC-2、Story 3.7 AC-3、Story 3.7 AC-4、Story 3.7 AC-5、Story 3.8 AC-1、Story 3.8 AC-2 |
| FR-9 全入口消费与局部修复 | CLI／direct／resume／route／页面共享门禁；纯实现修复复用，定义变化返owning stage。 | Story 3.8 AC-1、Story 3.8 AC-2、Story 3.8 AC-3、Story 3.8 AC-4、Story 3.8 AC-5、Story 3.9 AC-1、Story 3.9 AC-2、Story 3.9 AC-3、Story 3.9 AC-4、Story 3.9 AC-5、Story 3.10 AC-1、Story 3.10 AC-2、Story 3.10 AC-3、Story 3.10 AC-4、Story 3.10 AC-5、Story 3.12 AC-1、Story 3.12 AC-2、Story 3.12 AC-3、Story 3.12 AC-4 |
| FR-10 提前声明 UI 义务并由 Chapter 7 收口 | 前置UI义务，目标Chapter7复用6证据与治理补缺，不等全游戏，输入等级及人工分开。 | Story 2.4 AC-5、Story 3.4 AC-5、Story 3.11 AC-1、Story 3.11 AC-2、Story 3.11 AC-3、Story 3.11 AC-4、Story 3.11 AC-5、Story 5.7 AC-3、Story 5.7 AC-7 |
| FR-11 两层验证与完成边界 | 局部自检与Flow／累计收尾分别核对；全部必需与人工义务满足才可声明相应范围完成。 | Story 3.8 AC-4、Story 4.3 AC-2、Story 4.3 AC-3、Story 4.4 AC-1、Story 4.4 AC-2、Story 4.4 AC-3、Story 4.5 AC-1、Story 4.5 AC-2、Story 4.5 AC-3、Story 4.5 AC-4、Story 4.5 AC-5 |
| FR-12 真实的影响范围与三类义务 | 完整传递影响含planned，三类责任、真实覆盖与共享A／B反例，不重分类换绿。 | Story 4.1 AC-1、Story 4.1 AC-2、Story 4.1 AC-3、Story 4.2 AC-1、Story 4.2 AC-2、Story 4.2 AC-3、Story 4.2 AC-4、Story 4.2 AC-5、Story 4.3 AC-1、Story 4.3 AC-2、Story 4.5 AC-3、Story 4.5 AC-4、Story 4.10 AC-3 |
| FR-13 分别证明规划稳定、应用幂等和证据复用 | 规划稳定、应用幂等、运行证据有效性独立证明；后编辑／当前状态保留与同snapshot累计。 | Story 2.6 AC-1、Story 2.6 AC-2、Story 2.7 AC-6、Story 2.8 AC-1、Story 2.8 AC-2、Story 2.8 AC-3、Story 2.8 AC-4、Story 2.9 AC-1、Story 2.9 AC-2、Story 2.9 AC-3、Story 2.9 AC-4、Story 3.2 AC-3、Story 3.2 AC-4、Story 4.4 AC-1、Story 4.4 AC-2、Story 4.4 AC-3、Story 4.4 AC-4、Story 4.4 AC-5、Story 4.5 AC-3 |
| FR-14 存量保护与有界兼容 | 成熟身份／状态／累计义务保护，B不可降A，默认切换、门禁与实际退役分开，补偿保后编辑。 | Story 1.5 AC-1、Story 1.5 AC-2、Story 1.5 AC-3、Story 1.5 AC-4、Story 1.5 AC-5、Story 3.1 AC-3、Story 3.2 AC-3、Story 3.2 AC-4、Story 3.3 AC-1、Story 3.3 AC-2、Story 3.3 AC-3、Story 5.8 AC-1、Story 5.8 AC-2、Story 5.8 AC-3、Story 5.8 AC-4、Story 5.8 AC-5、Story 5.8 AC-6、Story 5.8 AC-7、Story 5.9 AC-1、Story 5.9 AC-2、Story 5.9 AC-3、Story 5.9 AC-4、Story 5.9 AC-5、Story 5.10 AC-1、Story 5.10 AC-2、Story 5.10 AC-3、Story 5.10 AC-4、Story 5.10 AC-5、Story 5.10 AC-6、Story 5.11 AC-1、Story 5.11 AC-4 |
| FR-15 Knowledge 与操作入口一致 | Knowledge仅派生，计划／实现／运行和workspace／attempt／stable／main身份分开，页面阶段真实。 | Story 3.12 AC-1、Story 4.6 AC-1、Story 4.6 AC-2、Story 4.6 AC-3、Story 4.6 AC-4、Story 4.6 AC-5、Story 4.7 AC-1、Story 4.7 AC-2、Story 4.7 AC-3、Story 4.7 AC-4、Story 4.7 AC-5、Story 4.8 AC-3、Story 4.9 AC-1、Story 4.9 AC-2、Story 4.9 AC-3 |
| FR-16 有界完整输入与失败成本 | 完整有界输入、独立worker及持久预算、完成项限定复用，实测过程事件且无提速门槛。 | Story 2.1 AC-3、Story 2.1 AC-5、Story 2.3 AC-3、Story 2.5 AC-2、Story 2.5 AC-3、Story 2.9 AC-1、Story 2.9 AC-2、Story 2.9 AC-3、Story 2.9 AC-4、Story 2.9 AC-5、Story 4.8 AC-1、Story 4.8 AC-2、Story 4.8 AC-3、Story 4.8 AC-4、Story 4.8 AC-5、Story 5.7 AC-6 |
| FR-17 生产者与消费者完整迁移 | 实际生产者／消费者逐项矩阵，真实格式／入口／文档／Skill对齐，版本管理及显式ADR演进。 | Story 1.1 AC-2、Story 1.2 AC-1、Story 1.2 AC-2、Story 1.2 AC-3、Story 1.2 AC-4、Story 1.2 AC-5、Story 3.2 AC-6、Story 3.12 AC-5、Story 4.9 AC-1、Story 4.9 AC-2、Story 4.9 AC-3、Story 4.9 AC-4、Story 4.9 AC-5、Story 5.8 AC-6、Story 5.10 AC-4 |
| FR-18 奖励真实切片及两条迁移路径 | 同combat-reward-return的无Task与存量增量证明，必要生产命令／只读状态／C#薄适配和真实Windows证据。 | Story 5.1 AC-1、Story 5.1 AC-2、Story 5.1 AC-3、Story 5.1 AC-4、Story 5.1 AC-5、Story 5.2 AC-1、Story 5.2 AC-2、Story 5.2 AC-3、Story 5.2 AC-4、Story 5.2 AC-5、Story 5.2 AC-6、Story 5.3 AC-1、Story 5.3 AC-2、Story 5.3 AC-3、Story 5.3 AC-4、Story 5.3 AC-5、Story 5.4 AC-1、Story 5.4 AC-2、Story 5.4 AC-3、Story 5.4 AC-4、Story 5.4 AC-5、Story 5.5 AC-1、Story 5.5 AC-2、Story 5.5 AC-3、Story 5.5 AC-4、Story 5.5 AC-5、Story 5.6 AC-1、Story 5.6 AC-2、Story 5.6 AC-3、Story 5.6 AC-4、Story 5.6 AC-5、Story 5.7 AC-1、Story 5.7 AC-2、Story 5.7 AC-3、Story 5.7 AC-4、Story 5.7 AC-5、Story 5.7 AC-6、Story 5.7 AC-7 |

## 质量、架构及原始AC覆盖

| 条目 | 核对结论 | Story／AC定位 |
| --- | --- | --- |
| NFR-E-1 | 既有Windows／Godot／C#、BCL-only及原生场景边界。 | Story 1.3 AC-5、Story 3.4 AC-2、Story 5.4 AC-1、Story 5.5 AC-2、Story 5.7 AC-1 |
| NFR-E-2 | Taskmaster唯一任务状态，来源／契约／manifest／报告各守权威，Knowledge派生。 | Story 1.2 AC-2、Story 3.2 AC-1、Story 4.5 AC-5、Story 4.6 AC-1 |
| NFR-E-3 | 相关输入精确失效，无关提交／状态不全仓重做；运行仍守原snapshot合同。 | Story 2.2 AC-3、Story 3.5 AC-1、Story 3.5 AC-2、Story 3.5 AC-3、Story 3.5 AC-4、Story 4.1 AC-4、Story 4.4 AC-4 |
| NFR-E-4 | 当前前后像、幂等／冲突、恢复与后编辑／新进度保护。 | Story 2.6 AC-2、Story 2.6 AC-3、Story 2.6 AC-4、Story 2.7 AC-1、Story 2.7 AC-6、Story 2.8 AC-1、Story 2.8 AC-2、Story 2.8 AC-3、Story 2.8 AC-4、Story 2.8 AC-5、Story 3.2 AC-3、Story 3.2 AC-4 |
| NFR-E-5 | 完整原文／守恒、容量／预算停止、独立admission、不恢复未完成模型状态。 | Story 2.1 AC-3、Story 2.3 AC-3、Story 2.5 AC-1、Story 2.5 AC-2、Story 2.5 AC-3、Story 2.5 AC-4、Story 2.9 AC-2 |
| NFR-E-6 | 证据等级、实际覆盖、人工、隔离与累计同snapshot。 | Story 4.3 AC-2、Story 4.3 AC-3、Story 4.4 AC-2、Story 4.4 AC-3、Story 4.4 AC-4、Story 4.5 AC-1、Story 4.5 AC-2、Story 4.5 AC-3、Story 4.5 AC-4、Story 4.5 AC-5、Story 5.7 AC-7 |
| NFR-E-7 | 成熟身份／状态／历史、质量P1／NeedsFix及累计防削弱保留。 | Story 1.2 AC-5、Story 1.5 AC-1、Story 1.5 AC-2、Story 3.8 AC-4、Story 4.9 AC-3、Story 5.10 AC-2、Story 5.10 AC-4 |
| NFR-E-8 | UTF-8中文文档、英文代码／打印，最小治理版本化，原始证据logs。 | Story 1.3 AC-5、Story 2.7 AC-2、Story 4.9 AC-4 |
| NFR-E-9 | 局部修复／UI复用、无隐式Knowledge全刷、未来责任不提前实施、奖励范围有界。 | Story 3.10 AC-1、Story 3.10 AC-2、Story 3.10 AC-3、Story 3.10 AC-4、Story 3.10 AC-5、Story 3.11 AC-1、Story 3.11 AC-2、Story 4.2 AC-3、Story 4.6 AC-5、Story 5.1 AC-3 |
| NFR-E-10 | 实测／unknown／去重／返工，不设速度、费用下降、固定任务数／时长目标。 | Story 2.1 AC-5、Story 2.5 AC-3、Story 4.8 AC-1、Story 4.8 AC-2、Story 4.8 AC-3、Story 4.8 AC-4、Story 4.8 AC-5、Story 5.7 AC-6 |
| NFR-E-11 | 共同诊断、未知／损坏阻断，预览／发布身份和部分规划／运行结论分开。 | Story 1.3 AC-4、Story 3.3 AC-1、Story 3.8 AC-2、Story 4.6 AC-2、Story 4.7 AC-2、Story 4.8 AC-3 |
| AR-1 | 权威方向与治理ADR。 | Story 1.2 AC-2、Story 1.2 AC-3、Story 4.6 AC-1、Story 4.6 AC-5 |
| AR-2 | 阶段分别验证，3B不要求Task／readiness。 | Story 1.2 AC-1、Story 2.3 AC-1、Story 3.7 AC-1、Story 3.7 AC-2、Story 3.7 AC-3 |
| AR-3 | 共享codec／版本化形状与单一提交服务。 | Story 1.3 AC-1、Story 1.3 AC-2、Story 1.3 AC-3、Story 1.3 AC-4、Story 1.3 AC-5、Story 1.4 AC-1、Story 1.4 AC-2、Story 1.4 AC-3、Story 1.4 AC-4、Story 1.4 AC-5、Story 2.7 AC-2、Story 2.7 AC-3 |
| AR-4 | 稳定身份、唯一owner与route／evidence分离。 | Story 2.4 AC-3、Story 2.6 AC-1、Story 2.6 AC-2、Story 3.2 AC-2 |
| AR-5 | 先治理链后分类，B不可通过丢标识变A。 | Story 3.3 AC-1、Story 3.3 AC-2、Story 3.3 AC-3、Story 3.3 AC-4、Story 3.3 AC-5、Story 5.8 AC-2、Story 5.8 AC-5、Story 5.9 AC-1、Story 5.9 AC-2 |
| AR-6 | 全真实入口同源InputSet与门禁。 | Story 3.5 AC-1、Story 3.5 AC-2、Story 3.5 AC-3、Story 3.5 AC-4、Story 3.5 AC-5、Story 3.6 AC-1、Story 3.6 AC-2、Story 3.6 AC-3、Story 3.6 AC-4、Story 3.6 AC-5、Story 3.8 AC-1、Story 3.8 AC-2、Story 3.9 AC-1、Story 3.9 AC-2、Story 3.12 AC-1、Story 3.12 AC-2、Story 3.12 AC-3 |
| AR-7 | 三联review／compile，状态属Taskmaster且合并当前状态。 | Story 3.1 AC-1、Story 3.1 AC-2、Story 3.1 AC-3、Story 3.1 AC-4、Story 3.2 AC-1、Story 3.2 AC-2、Story 3.2 AC-3、Story 3.2 AC-4 |
| AR-8 | journal／receipt／最后catalog及恢复一致性。 | Story 2.6 AC-1、Story 2.6 AC-2、Story 2.6 AC-3、Story 2.6 AC-4、Story 2.6 AC-5、Story 2.7 AC-1、Story 2.7 AC-2、Story 2.7 AC-3、Story 2.7 AC-4、Story 2.7 AC-5、Story 2.7 AC-6、Story 2.8 AC-1、Story 2.8 AC-2、Story 2.8 AC-3、Story 2.8 AC-4、Story 2.8 AC-5 |
| AR-9 | 完成项adoption、worker／父协调、预算／epoch／reopen。 | Story 2.5 AC-2、Story 2.5 AC-3、Story 2.5 AC-4、Story 2.9 AC-1、Story 2.9 AC-2、Story 2.9 AC-3、Story 2.9 AC-4、Story 2.9 AC-5 |
| AR-10 | 相关InputSet与正式runtime snapshot分别核对。 | Story 3.5 AC-1、Story 3.5 AC-2、Story 3.5 AC-3、Story 3.5 AC-4、Story 4.4 AC-4、Story 4.5 AC-3 |
| AR-11 | 影响及执行共享范围，三类义务和真实覆盖。 | Story 4.1 AC-1、Story 4.1 AC-2、Story 4.1 AC-3、Story 4.2 AC-2、Story 4.2 AC-3、Story 4.2 AC-4、Story 4.3 AC-1、Story 4.3 AC-2、Story 4.5 AC-2、Story 4.5 AC-3、Story 4.5 AC-4 |
| AR-12 | 四部分／状态owner／循环／类型与阶段责任。 | Story 2.4 AC-1、Story 2.4 AC-2、Story 3.4 AC-1、Story 3.4 AC-2、Story 3.4 AC-3、Story 3.4 AC-4 |
| AR-13 | 修复路由、UI复用及证据等级。 | Story 3.10 AC-1、Story 3.10 AC-2、Story 3.10 AC-3、Story 3.10 AC-4、Story 3.10 AC-5、Story 3.11 AC-1、Story 3.11 AC-2、Story 3.11 AC-3、Story 3.11 AC-4、Story 3.11 AC-5、Story 4.5 AC-2 |
| AR-14 | 奖励唯一生产边界、原生场景、RNG／存档和必要契约变化。 | Story 5.1 AC-1、Story 5.1 AC-2、Story 5.1 AC-3、Story 5.1 AC-4、Story 5.1 AC-5、Story 5.4 AC-1、Story 5.4 AC-2、Story 5.4 AC-3、Story 5.4 AC-4、Story 5.4 AC-5、Story 5.5 AC-1、Story 5.5 AC-2、Story 5.5 AC-3、Story 5.5 AC-4、Story 5.5 AC-5、Story 5.6 AC-1、Story 5.6 AC-2、Story 5.6 AC-3、Story 5.6 AC-4、Story 5.6 AC-5 |
| AR-15 | 完整来源／候选准入／持久预算／实际观测。 | Story 2.1 AC-1、Story 2.1 AC-2、Story 2.1 AC-3、Story 2.1 AC-4、Story 2.1 AC-5、Story 2.2 AC-1、Story 2.2 AC-2、Story 2.2 AC-3、Story 2.2 AC-4、Story 2.5 AC-3、Story 4.8 AC-1、Story 4.8 AC-2、Story 4.8 AC-3、Story 4.8 AC-4、Story 4.8 AC-5 |
| AR-16 | 派生展示、统一诊断与发布隔离。 | Story 4.6 AC-1、Story 4.6 AC-2、Story 4.6 AC-3、Story 4.6 AC-4、Story 4.6 AC-5、Story 4.7 AC-1、Story 4.7 AC-2、Story 4.7 AC-3、Story 4.7 AC-4、Story 4.7 AC-5、Story 4.8 AC-3 |
| AR-17 | 现有Windows／Python、共享锁／scope保护与实际故障验证。 | Story 1.3 AC-5、Story 2.6 AC-3、Story 2.7 AC-6、Story 2.8 AC-5、Story 4.10 AC-1 |
| AR-18 | 五批推进，切B／退A条件分开，代码清理与补偿保真。 | Story 1.2 AC-3、Story 5.8 AC-1、Story 5.8 AC-2、Story 5.8 AC-3、Story 5.8 AC-4、Story 5.8 AC-5、Story 5.8 AC-6、Story 5.8 AC-7、Story 5.9 AC-1、Story 5.9 AC-2、Story 5.9 AC-3、Story 5.9 AC-4、Story 5.9 AC-5、Story 5.10 AC-1、Story 5.10 AC-2、Story 5.10 AC-3、Story 5.10 AC-4、Story 5.10 AC-5、Story 5.10 AC-6、Story 5.11 AC-1、Story 5.11 AC-2、Story 5.11 AC-3、Story 5.11 AC-4、Story 5.11 AC-5 |
| AR-19 | 六记录形状／写者、独立修订、owner与无Task bootstrap。 | Story 1.4 AC-1、Story 1.4 AC-2、Story 1.4 AC-3、Story 1.4 AC-4、Story 2.6 AC-1、Story 2.6 AC-2、Story 2.6 AC-3、Story 2.6 AC-4、Story 2.6 AC-5、Story 2.7 AC-2、Story 2.7 AC-3、Story 2.7 AC-4、Story 2.7 AC-5、Story 3.2 AC-2 |
| AR-20 | 路径／严格JSON／类型／规范化与raw proof。 | Story 1.3 AC-1、Story 1.3 AC-2、Story 1.3 AC-3、Story 1.3 AC-4、Story 1.3 AC-5、Story 1.4 AC-1、Story 1.4 AC-5 |
| AR-21 | status allowlist、冻结验证模式、no-op保新状态。 | Story 1.5 AC-1、Story 3.2 AC-3、Story 3.2 AC-4、Story 3.5 AC-2、Story 3.5 AC-3 |
| AR-22 | 零Task正式采纳、分类与非Flow验证。 | Story 1.4 AC-3、Story 2.7 AC-4、Story 3.3 AC-1、Story 3.3 AC-2、Story 3.3 AC-3、Story 3.6 AC-1、Story 3.6 AC-2、Story 3.6 AC-3、Story 3.6 AC-4 |
| AR-23 | prepare/reserve/apply/verify/publish/recover，scope租约及无全局长锁。 | Story 2.6 AC-3、Story 2.7 AC-1、Story 2.7 AC-2、Story 2.7 AC-3、Story 2.7 AC-4、Story 2.7 AC-5、Story 2.7 AC-6、Story 2.8 AC-1、Story 2.8 AC-2、Story 2.8 AC-3、Story 2.8 AC-4、Story 2.8 AC-5 |
| AR-24 | 旧pending／journal、clone验证、clear／reopen历史保留。 | Story 3.3 AC-4、Story 2.8 AC-3、Story 2.9 AC-4、Story 3.9 AC-2、Story 3.9 AC-5 |
| AR-25 | VerificationScope v1、实际runner回执与同snapshot共享。 | Story 4.1 AC-1、Story 4.1 AC-2、Story 4.1 AC-3、Story 4.1 AC-4、Story 4.1 AC-5、Story 4.2 AC-1、Story 4.2 AC-2、Story 4.2 AC-3、Story 4.2 AC-4、Story 4.2 AC-5、Story 4.3 AC-1、Story 4.3 AC-2、Story 4.3 AC-3、Story 4.3 AC-4、Story 4.3 AC-5、Story 4.4 AC-2、Story 4.4 AC-3 |
| AR-26 | 公共六字段诊断和真实阶段事件生产／汇集。 | Story 1.3 AC-4、Story 2.1 AC-5、Story 4.8 AC-1、Story 4.8 AC-2、Story 4.8 AC-3、Story 4.8 AC-4、Story 4.8 AC-5 |
| AR-27 | 当前cd925bd代码事实与已存在输入／worker／checkpoint能力继承。 | Story 1.1 AC-1、Story 1.1 AC-2、Story 2.3 AC-5、Story 2.5 AC-2、Story 2.5 AC-3、Story 2.9 AC-1、Story 2.9 AC-2、Story 2.9 AC-3、Story 2.9 AC-4、Story 2.9 AC-5 |
| AR-28 | 全消费者与启用前失败反例，治理和写者边界。 | Story 4.9 AC-1、Story 4.9 AC-2、Story 4.9 AC-3、Story 4.9 AC-4、Story 4.9 AC-5、Story 4.10 AC-1、Story 4.10 AC-2、Story 4.10 AC-3、Story 4.10 AC-4、Story 4.10 AC-5、Story 4.10 AC-6、Story 5.8 AC-3、Story 5.10 AC-3、Story 5.10 AC-4 |
| AC-BR-01 | 按原始验收意图及对应当前Story/AC核对。 | Story 2.10 AC-1、Story 3.2 AC-1、Story 5.2 AC-6、Story 5.3 AC-1 |
| AC-BR-02 | 按原始验收意图及对应当前Story/AC核对。 | Story 2.2 AC-1、Story 2.1 AC-3 |
| AC-BR-03 | 按原始验收意图及对应当前Story/AC核对。 | Story 2.4 AC-1、Story 2.4 AC-2、Story 3.4 AC-1 |
| AC-BR-04 | 按原始验收意图及对应当前Story/AC核对。 | Story 3.2 AC-2、Story 3.4 AC-3、Story 5.3 AC-2 |
| AC-BR-05 | 按原始验收意图及对应当前Story/AC核对。 | Story 2.4 AC-3、Story 3.1 AC-2、Story 3.2 AC-2 |
| AC-BR-06 | 按原始验收意图及对应当前Story/AC核对。 | Story 2.6 AC-2、Story 2.7 AC-6、Story 2.9 AC-1、Story 3.2 AC-4 |
| AC-BR-07 | 按原始验收意图及对应当前Story/AC核对。 | Story 2.8 AC-1、Story 2.8 AC-2、Story 3.2 AC-4、Story 5.8 AC-3 |
| AC-BR-08 | 按原始验收意图及对应当前Story/AC核对。 | Story 3.8 AC-1、Story 3.8 AC-2、Story 3.9 AC-1、Story 3.9 AC-2、Story 3.12 AC-3 |
| AC-BR-09 | 按原始验收意图及对应当前Story/AC核对。 | Story 2.2 AC-3、Story 3.5 AC-2、Story 3.5 AC-3、Story 4.4 AC-4 |
| AC-BR-10 | 按原始验收意图及对应当前Story/AC核对。 | Story 3.8 AC-4、Story 4.5 AC-1、Story 4.5 AC-2 |
| AC-BR-11 | 按原始验收意图及对应当前Story/AC核对。 | Story 4.1 AC-1、Story 4.1 AC-3、Story 4.2 AC-2、Story 4.2 AC-3、Story 4.3 AC-1、Story 4.3 AC-2 |
| AC-BR-12 | 按原始验收意图及对应当前Story/AC核对。 | Story 3.11 AC-3、Story 4.3 AC-3、Story 5.7 AC-1、Story 5.7 AC-7 |
| AC-BR-13 | 按原始验收意图及对应当前Story/AC核对。 | Story 3.11 AC-1、Story 3.11 AC-2、Story 3.11 AC-4、Story 4.5 AC-2 |
| AC-BR-14 | 按原始验收意图及对应当前Story/AC核对。 | Story 1.5 AC-1、Story 1.5 AC-2、Story 3.2 AC-3、Story 4.9 AC-2 |
| AC-BR-15 | 按原始验收意图及对应当前Story/AC核对。 | Story 3.3 AC-2、Story 3.6 AC-5、Story 5.3 AC-1 |
| AC-BR-16 | 按原始验收意图及对应当前Story/AC核对。 | Story 4.6 AC-1、Story 4.6 AC-2、Story 4.6 AC-5、Story 4.7 AC-1、Story 4.7 AC-5、Story 4.9 AC-1、Story 4.9 AC-3 |
| AC-BR-17 | 按原始验收意图及对应当前Story/AC核对。 | Story 4.4 AC-1、Story 4.4 AC-2、Story 4.4 AC-3、Story 4.4 AC-4、Story 4.5 AC-3 |
| AC-BR-18 | 按原始验收意图及对应当前Story/AC核对。 | Story 5.2 AC-1、Story 5.2 AC-2、Story 5.2 AC-3、Story 5.2 AC-6、Story 5.3 AC-1、Story 5.3 AC-2、Story 5.4 AC-1、Story 5.4 AC-2、Story 5.5 AC-1、Story 5.6 AC-1、Story 5.6 AC-2、Story 5.7 AC-1、Story 5.7 AC-2、Story 5.7 AC-7 |
| AC-BR-19 | 按原始验收意图及对应当前Story/AC核对。 | Story 1.4 AC-1、Story 1.4 AC-3、Story 1.4 AC-5、Story 3.3 AC-1、Story 3.3 AC-4、Story 4.9 AC-2 |
| AC-BR-20 | 按原始验收意图及对应当前Story/AC核对。 | Story 2.1 AC-5、Story 4.8 AC-1、Story 4.8 AC-2、Story 4.8 AC-5、Story 5.7 AC-6 |
| AC-BR-21 | 按原始验收意图及对应当前Story/AC核对。 | Story 2.4 AC-4、Story 3.6 AC-1、Story 3.6 AC-2、Story 3.6 AC-3、Story 3.12 AC-2、Story 3.12 AC-3 |
| AC-BR-22 | 按原始验收意图及对应当前Story/AC核对。 | Story 4.2 AC-3、Story 4.5 AC-4、Story 4.10 AC-3、Story 5.7 AC-4 |
| AC-BR-23 | 按原始验收意图及对应当前Story/AC核对。 | Story 3.10 AC-1、Story 3.10 AC-2、Story 3.10 AC-3、Story 3.10 AC-4、Story 3.9 AC-5 |

## Story粒度和依赖

| Story | 验收组数 | 独立可交付边界 | 前置 |
| --- | --- | --- | --- |
| 1.1 生成可复查的当前基线与消费者盘点 | 5 | 只读盘点报告；不等待正式planner。 | 当前仓库 |
| 1.2 明确B阶段顺序、记录权威及迁移启用规则 | 5 | 已确认治理决定落ADR／路由；真实审阅条件保留。 | 1.1 |
| 1.3 统一核验文件引用与规范化内容身份 | 5 | 公共身份／引用核验，独立于全结构与发布。 | 1.1, 1.2 |
| 1.4 按唯一公共schema校验六类规划记录 | 5 | 六类既定合同的候选校验；不实例化未来计划或数据库。 | 1.3 |
| 1.5 形成可审阅的成熟成果保护基准与冻结A输入 | 5 | 当前存量保护及冻结A输入审阅。 | 1.1, 1.2, 1.3, 1.4 |
| 1.6 通过只读预检审阅迁移差异与阻断原因 | 6 | 只读CLI预检及交接，不调用未来写者。 | 1.1, 1.2, 1.3, 1.4, 1.5 |
| 2.1 在Task之前形成累计来源Ledger与需求验收意图 | 5 | 来源Ledger与需求提议，不先建Task。 | 1.1, 1.2, 1.3, 1.4, 1.5, 1.6 |
| 2.2 从完整来源独立审计遗漏与冲突 | 5 | 完整来源独立审计及有效复用。 | 2.1 |
| 2.3 准备Task无关且完整的规划输入 | 5 | 既有planner的Task无关输入适配。 | 2.1, 2.2 |
| 2.4 描述可审阅的Flow及合法非Flow验证去向 | 5 | 逻辑Flow／非Flow候选与结构核对。 | 2.3 |
| 2.5 通过独立准入与有界评选选出可采纳候选 | 5 | 复用现有worker／admission／预算，不新建生命周期。 | 2.3, 2.4 |
| 2.6 冻结采纳操作并持久分配稳定身份 | 5 | 冻结请求／身份／pending即可独立验证，不先授权发布。 | 2.5, 1.5, 1.6 |
| 2.7 一致提交采纳目标并以catalog发布 | 6 | 完整发布或安全阻断可独立验收，自动recover在后续增加。 | 2.6 |
| 2.8 按journal恢复中断并保留后编辑 | 5 | 同一提交服务recover／补偿。 | 2.7 |
| 2.9 复用已提交完成规划并遵守epoch与reopen撤销 | 5 | 现有完成项registry／adoption的阶段适配。 | 2.3, 2.5, 2.7, 2.8 |
| 2.10 从正式规划入口完成零Task采纳与跨会话复验 | 6 | 现有CLI正式采纳端到端，不等待Task／页面新功能。 | 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9 |
| 3.1 从复用盘点形成真实缺口的任务变更预览 | 5 | 真实缺口业务delta预览。 | 2.10 |
| 3.2 受治理编译三联与3C绑定并保留当前任务状态 | 6 | 原三联编译／绑定接共享提交，仅校验3C必要项。 | 3.1, 2.6, 2.7, 2.8 |
| 3.3 统一判定Task来源及完整适用计划集合 | 5 | 公共来源分类，可独立诊断但不授实施权限。 | 3.2 |
| 3.4 在Chapter4细化生产契约与四部分实施定义 | 5 | 当前Task四部分实施定义及必要契约治理。 | 3.2, 3.3 |
| 3.5 构造共同InputSet并精确判断新鲜度 | 5 | 公共相关输入／资格接口，不依赖新runner。 | 3.3, 3.4 |
| 3.6 绑定真实MVG义务或合法其他验证依据 | 5 | 既有manifest／其他验证绑定，可用保守累计集合。 | 3.4, 3.5 |
| 3.7 在Chapter5核对同源定义并形成有效readiness | 5 | 现有Chapter5一致性和同源readiness。 | 3.5, 3.6 |
| 3.8 让直接Chapter6与公共CLI消费统一实施门禁 | 5 | direct／CLI真实副作用门禁与现有单Task流程。 | 3.7, 2.8 |
| 3.9 在恢复与route入口重验当前输入和任务资格 | 5 | resume／route接同一门禁，推荐不自动执行。 | 3.8 |
| 3.10 按缺陷类型复用规划或返回定义所属阶段 | 5 | 缺陷分类、复用或返回owning stage。 | 3.1, 3.2, 3.7, 3.8, 3.9 |
| 3.11 按目标slice收口Chapter7并复用已验证UI | 5 | 目标Chapter7 slice，保真实／人工证据边界。 | 3.4, 3.6, 3.7, 3.8, 3.9, 3.10 |
| 3.12 让页面实施触发与全入口决定保持一致 | 5 | 页面实施调用边界和全入口一致性，非完整Knowledge UI。 | 3.3, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11 |
| 4.1 从受治理反向关系计算完整传递影响 | 5 | 注册反向边／传递影响，无新数据库。 | 3.12 |
| 4.2 形成可执行的三类义务VerificationScope | 5 | 当前验证范围合同及三类义务。 | 4.1, 3.6, 3.7 |
| 4.3 让真实执行器消费范围并报告实际覆盖 | 5 | 既有真实runner范围／回执适配，无新测试框架。 | 4.2 |
| 4.4 在身份匹配时复用构建与共享测试证据 | 5 | 现有工件／证据复用身份及状态隔离。 | 4.3, 2.9, 3.5 |
| 4.5 分别核对Task、Flow和累计里程碑完成 | 5 | 原Flow／milestone结果核对，不新增状态权威。 | 4.2, 4.3, 4.4, 3.11 |
| 4.6 派生展示规划、实施与运行身份 | 5 | 既有KCP派生及trusted-ref边界。 | 4.1, 4.5, 3.5, 2.9 |
| 4.7 在规划页面按真实阶段操作并定位阻塞与恢复 | 5 | 现有页面调用／阶段适配，前置服务已齐。 | 4.6, 2.10, 3.12 |
| 4.8 汇集可追溯过程观测与统一诊断 | 5 | 既有阶段事件汇集与公共诊断。 | 4.3, 4.4, 4.5, 4.7, 2.10, 3.12 |
| 4.9 对齐全部生产者消费者与治理文档 | 5 | 依据既定矩阵逐项对账；各核心能力此前交付。 | 4.5, 4.6, 4.7, 4.8, 3.12 |
| 4.10 在Windows故障与共享变更下核对端到端结论 | 6 | 本批通用协议跨入口故障验证，复用已有工具，不依赖奖励特定改造。 | 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9 |
| 5.1 固定奖励真实变更与存量复用边界 | 5 | 只读真实奖励变化／复用盘点。 | 4.10 |
| 5.2 在无变更Task时正式采纳奖励规划 | 6 | 当前输入正式无Task采纳与独立性证明。 | 5.1, 2.10, 4.7 |
| 5.3 以存量增量路径承接真实任务和实施绑定 | 5 | 原三联／4–5工具承接该真实变化。 | 5.2, 3.12 |
| 5.4 实现奖励受控生产命令与只读状态边界 | 5 | 命令／只读状态局部实现，不等待场景适配才验收。 | 5.3 |
| 5.5 将原生Reward场景接入必要C#薄适配 | 5 | 必要C#原生Reward接线和当前会话输入。 | 5.4 |
| 5.6 使奖励重入与Continue沿既有存档边界恢复 | 5 | 接既有Continue／存档边界，不重构保存架构。 | 5.4, 5.5 |
| 5.7 以Windows真实输入完成奖励双路径取证 | 7 | 真实Windows证据与既有机制proof对账，不重跑整套规划。 | 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 4.10 |
| 5.8 在证据齐备后切换新增需求默认入口为B | 7 | 本次候选演练先行，切B不以A全退役为前置。 | 5.7, 4.9, 4.10 |
| 5.9 核对A退出资格并交付统一门禁能力 | 5 | 只读资格／门禁能力独立验收。 | 5.8, 4.9 |
| 5.10 在条件成熟后实际撤权并清理A写入兼容 | 6 | 真实退出动作有独立当前条件，未成熟blocked；仅清理无消费者的A写路径。 | 5.8, 5.9, 4.9 |
| 5.11 以补偿回退反例收口迁移与完成声明 | 5 | 可核对有界A未退役事实，不依赖5.10完成，不宣告Epic整体通过。 | 5.7, 5.8, 5.9 |

## Epic价值与独立性

- **Epic 1：** 维护者可独立审阅迁移与保护基准。只读预检可用，未声称后续正式采纳／实施已可用。
- **Epic 2：** 规划者可独立完成无Task正式采纳及恢复。只消费自身阶段必要输入，不等待3C／readiness／新页面。
- **Epic 3：** 实施者按采纳定义承接任务、进入4–7并安全恢复。可沿既有完整适用manifest执行；不依赖Epic4选择性runner或完整Knowledge展示。
- **Epic 4：** 验证者执行真实适用范围，操作者看到可信进度／诊断。通用协议／消费者可验证，不等待奖励特定迁移完成。
- **Epic 5：** 玩家获得保原规则的生产Reward边界；维护者按真实证据切换及有条件退A。没有未来Epic依赖；5.10未满足外部真实条件时明确blocked，不能被5.9或5.11代验。

## 共享文件与分批理由

- **schema / codec：** Epic1公共定义；后续引用或受治理升版。共享形状是预检所需的先行合同，各消费者不复制私有解释。
- **journal / apply / locks：** Epic2正式采纳提交服务；Epic3绑定／三联适配。不同阶段职责与风险交接，公共服务只有一处；先正式采纳、后Task消费是产品顺序。
- **planner / gate / runner：** Epic2语义输入；Epic3实施身份；Epic4范围及实际覆盖。有明确用户结果与负例边界，Epic3可用已有完整执行，不反向等待新runner。
- **CLI / pages / docs：** 各阶段同步本入口；Epic4覆盖对账；Epic5业务切换。先通用能力反馈再真实试点启用，复用同一服务而非重复新增组件。

## 限制与状态

- 旧SPEC不生成Story的陈述是上一委托边界，本次用户另行授权并逐项批准。
- 稿件中当前本轮仅编写Story等语句说明此次文档撰写范围；不得拿这些注记替代未来真实实施／运行证据。
- 5.10实际退出须真实条件成熟，未成熟blocked；文档通过不代表运行条件已满足。
- 原始来源／Taskmaster／契约／manifest／runtime报告权威保留，Knowledge派生，不增规划数据库。
- 当前没有创建真实Task、实施、付费模型规划、Windows／Godot运行验收、默认B切换、A退役或远端发布。

全部模板占位、编号、256组Given／When／Then／And、只依赖此前Story、批准正文与十份来源哈希均通过机械核对。批准内容未被本轮校验改写。完整结构化证据见 `final-validation.json`。

最终C只完成文档工作流并将状态置final；实际Task映射、实施与验收属于后续另行执行的阶段。

## 最终完成确认

用户随后以最终 C 确认完成文档工作流；`epics.md` 已从 `draft` 置为 `final`，四个步骤均标记完成。上文 draft 描述保留为校验完成时的历史状态；批准的全部 Story 正文未改写。完成仅涉及文档交付，不代表真实 Task／实施／运行就绪或路线切换。
