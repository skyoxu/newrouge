# ADR-0049: B 路线当前必需输入与历史调试附件的角色边界

- Status: Accepted
- Date: 2026-11-07
- Scope: B route inventory / mature protection reference roles
- Authority: 用户明确说明 Task 信息用于服务调试，不能因无关历史附件缺失阻塞当前任务，并授权最小通用 inventory/protection 修复；本决定已由 Root 完成定向验证及只读采集／归档复核；正式采纳和默认启用继续遵守原门禁。

## 背景与问题

旧 inventory 将每条 Task `evidence_refs` 和当前必需来源／测试同样视为必需文件。一个无关 Task 的历史调试附件缺失，因而能使全量保护 `capture_complete=false`，继续阻塞其他操作。Task 原记录、状态与原历史运行是否有证明，是必须保留的事实；附件能否成为当前操作的前置条件，应由当前操作实际需要的输入合同决定。

本决定补充 ADR-0040 对历史证据限制的解释，不整体替代其阶段、权威、冻结 A、正式采纳或迁移启用条件。旧报告中的缺失事实及当时 v1 结论继续保留，不能补造原件、用旧 done 代替证据、改 Task 状态或改写旧回执。

## 决定与版本合同

1. 新采集使用 `newrouge.b-route-baseline-inventory.v2` 与 `newrouge.b-route-protection-snapshot.v2`。引用角色由 owning field 重建，新增 `reference_role` 字符串与 `required` 布尔值；不引入公共配置、Task 标记、兼容层或额外规划权威。
2. Task `evidence_refs` 固定为 `historical-debug-attachment`／false。附件存在时读取并归档原 bytes；缺失时保存原引用、owner 文件、JSON pointer、原 Task／master join、`state=missing`、null raw 身份及 `missing-input` warning。缺失不代表历史运行成功，也不单独使当前采集不完整。
3. Task source／test、manifest source／contract／已实现 test 为 `current-input`／true。显式 planned manifest test 为 `planned-input`／false，仍不宣称已实现。其余当前必需读入及 owner 校验继续生效；同一路径存在多种角色时，历史读取不能豁免当前必需读取。模板／非文件引用保持原 unknown 限制。
4. 仅附件缺失被分类为非阻断观察。不安全路径、逃逸、大小写别名、链接／reparse、不可读文件和观察到的漂移仍拒绝。附件存在／缺失／变化均参与内容身份与稳定性核验，不静默忽略原历史数据。
5. 保护复核复用原 owner 从 Task／manifest 原 bytes 重建角色及引用，并复核缺失 warning；删诊断、降级角色、删引用或只重签摘要不能获得有效归档。`capture_complete` 仍由稳定采集、完整当前必需输入、有效 inventory 与可重建三联共同决定。
6. 当前 reader 只支持 v2 和 `inventory.rule_identity()` 返回的当前已安装五项实现／CLI raw 摘要集合；采集与复核共用这个 owner。旧、缺失、删改或被替换的 rules 即使加齐 v2 角色字段、修改全部版本并重签摘要，也不能冒充当前受支持规则。旧 v1 schema 仍拒绝；无旧规则兼容或自动升级入口，需要当前材料时使用新 run ID 重新采集。旧原件及解释保持不动，原回执不自动升格。
7. rules 精确匹配和原 bytes 派生重建限定归档在当前支持规则下的语义解释，不认证 `collection` 事件来源或物理新 capture 是否执行。普通可变 JSON 摘要可重算、当前 rules 可复制，不能作为不可伪造的采集来源证明。归档 `verify` 不证明工作区仍相同或 fresh currentness；后者仍由新采集／compare 和具体操作门禁负责，不引入执行证书或额外用户确认门槛。

精确字段及缺失行为由 [inventory owning contract](../workflows/b-route-baseline-inventory.md#v2-引用角色合同) 定义；[protection owning contract](../workflows/b-route-mature-protection.md) 规定归档索引、身份及只读复核。

## 仍然必需的保证

当前功能输入、来源、Task 身份及原已有数据、当前定义／状态／累计义务、实际适用的 native 审计与独立审阅继续验证。若具体操作需要某份原运行证据，该 owner 必须把它作为当前输入读取核验；历史字段角色不提供豁免。必要 protected before／after／rollback、scope、currentness、租约、冲突与不覆写保证不变。

完整采集不等于正式保护基准、frozen-A 资格、正式采纳、readiness、运行验收或默认 B 启用。所有保护授权继续 false，冻结候选仍须完整已提交反向治理证明；缺失历史仍列 `historical_evidence_not_proven`。此次作者修改不执行实际 capture、adoption、review、reserve、模型调用或迁移，不解除其他 Story 正式前置及既有 unknown／预算约束。

## 验证义务

定向正反例覆盖历史附件存在／缺失、原定位与 null 身份／warning 保留、必需来源／测试缺失、同路径必需读取优先、不安全／reparse／不可读路径、历史附件漂移、归档重建角色、删 warning 或降级角色后重签、旧 v1 明确拒绝及差异观测；另覆盖保留完整五项 legacy rules 与 collection、补齐当前 v2 形状后完整重签，以及缺／删／改／替换 rules。原 Task 与历史日志 bytes 不变；只读复核不修补原材料。作者仅作文本／AST／hash 静态核对，项目测试、实际集成和此提案收口由 Root 负责，未执行的验证不能写成通过。


## Root 验证与收口（2026-11-07）

依据用户对 Task 调试信息用途的明确澄清及实施自主决策授权，接受本角色边界。14 项新增正反检查及 13 项必要现有功能回归全部通过，无跳过、隔离违规或新增真实模型调用。真实 v2 只读采集与公开归档复核均返回成功；原 Task 三联原始摘要不变，Task 108 历史 summary 仍缺失且保留原引用、null 身份及 warning。旧 v1 失败归档不作改写。

接受决定不表示 Story 2.6、formal protection、frozen-A、adoption、readiness、runtime 或默认 B 启用通过；对应授权继续 false。归档复核只证明支持规则下的原字节完整性，后续具体操作仍关闭当前来源与必要前置条件。代码和测试未在验证后修改；本节、状态及 ADR 索引为验证后的文档收口。

执行结果及代码／文档版本区别见 [Root 收口证据](../../logs/ci/2026-11-07/reference-roles-checkpoint/summary.json)。
