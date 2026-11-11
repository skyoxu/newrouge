# ADR-0042：Capability/MVG共用分段协议与有界无损传输

- Status: Accepted
- Implementation: 用户批准方案；实现与真实资格分别待验，默认B未启用
- Date: 2026-11-07
- Extends: ADR-0038-mvg-candidate-admission、ADR-0039-mvg-completed-capability-recovery、ADR-0040-b-route-stages-authority-and-activation

## 背景

生成阶段已有分批，而综合、独审和评选可能再次拼回完整来源与全部候选。每次官方调用都是独立ephemeral单turn，不能依赖跨请求记忆。用户批准Capability/MVG共用长期分段工作流，单次最终完整序列化输入控制在70000。当前96000是项目保守容量门禁，未被验证为官方硬窗口。

## 决定

1. 使用明确opt-in版本的同一四阶段引擎，宿主持久化每段原字节范围、顺序、SHA-256、候选身份、依赖和父结果。缺段、重复、混版、陈旧、未解决项与unknown阻断；不自动重发。复用原registry/journal/claim/锁及累计计费，不另立可退款权威。
2. 70000约束每次最终完整输入，包含说明、schema、真实官方workspace包装、完整相关原文/业务体和引用。输出另预留26000，输入加预留仍不超过原96000，按原双tokenizer较大值加10%的保守估算逐次检查。它们不是字符限额或服务端实际计费token声明。现有1MiB输入字节门禁不提高。
3. 由真实依赖闭包组织生成/综合/独审和公平joint panels，独立核对完整相关原文、全局覆盖/ID/图边。提取和摘要不能冒充原文无损替代。不可拆全局约束或生成闭包仍超容量时明确阻断，不截断。最终依赖已完整核验的panel证据，不重新拼回全部材料，也不假称与一次读完等价。
4. 固定原两/三候选、盲标、维度、依据和边界，每候选同等核验并覆盖跨段相互影响。最后只能选择原候选，不拼赢家，不以简单分数加总或淘汰赛冒充完整判断。
5. 完整逻辑输入采用固定原v2无损codec的显式input wire v1，严拒其他版本/raw fallback，保完整有序JSON与原文/类型/字符串。实际原输入及完整wrapper、schema、hash由原paid claim和真实receipt绑定；冷回放从原永久归档重建，不靠模型历史。
6. 新物理response citation wire v1只把明确proof字段的完整引用数组编成citation_sets和原行索引。模型必须按新schema真实返回；宿主严格展开后继续原完整语义/身份/分母/原文检查，业务JSON内部同名字段不变。原物理输出、schema和receipt始终保留。禁止事后压缩曾失败输出并改判成功。重复/unused/错索引类型/乱序/错version/缺项/未知字段阻断，无旧wire静默fallback。
7. 新response展开资源政策v1另设有限宿主界：完整展开后紧凑JSON UTF-8至多16MiB，值与键节点合计100000。在任何模型result/table复制前作饱和成本计算，包含表项成本乘实际引用次数及完整结果成本；超过只阻断、无裁剪。这是宿主内存/工作上限，不是模型上下文或追加额度，不能用后验摘要/canonical代替分配前止损。
8. 原Capability96/MVG192、稳定槽位64、campaign290、原时间和unknown占用保持；plan最小8/11只是逻辑节点计划，真正可执行须逐次以原owner的真实当前账本/time/source/epoch检查，不把任何历史79等观察值写成费用权威。达到上限即停，不扩额、换ID或释放unknown。
9. 使用用户要求的官方high配置、无工具、新ephemeral、无历史。记录真实返回的运行配置与完整输入输出绑定；不称服务端实际模型/实际推理/物理请求数/费用已验证。
10. 老Story2.5/R22原合同及已合格候选独立收口，历史proof只归原producer；新协议结果不得冒充旧“一次全部材料”的证明，也不授formal adoption、readiness、默认B启用或发布。

## 验证与结果边界

本地checkpoint c55e3b074fe986d574c163b202c19daf3610fbea记录86/87受影响方法在各自源码纪元通过，唯一MVG原physical输出29262超过26000并保留。新response wire与资源守卫已在Root的723项屏障下实际完成31项定向离线检查，全部通过且源码前后一致；真实模型与native调用仍为0。原失败、预算和证据不改判。后续需新wire定向正反/组合/恢复验证、独立复核及原预算内真实验证后才可声明相应资格。

## 影响

增加显式表示与恢复校验成本，换取完整来源可追溯和有限资源。容量不够时仍可能阻断，不能为减少调用牺牲语义覆盖。实现细节以版本化源码/实际schema为准；治理采纳、实现交付和迁移启用分开。

Root验证证据归档于 `logs/ci/2026-11-07/segmented-response-wire-freeze/`；本ADR状态段仅作测试后事实更新，真实资格与默认B启用仍pending。


## R58 isolated integration status (planned)

Original R23 evidence above retains its original epoch. The R58 combination
with current R57 shared owners is not yet validated or formally enabled.
See `execution-plans/2026-11-10-r23-segmented-to-r58-opt-in-migration.md`.
No model/native/funding authority, default activation or old-proof requalification
is granted by this transplant. Existing ADR-0042 thresholds remain unchanged.
