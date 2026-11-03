# B 路线公共记录格式合同（Story 1.4）

状态：本轮公共 schema owner 技术冻结；校验实现尚待本 Story 验证。本格式不启用 B 路线。

用途：统一六类记录、只读 API 及候选关系的实施合同。字段布局是架构明确委托共享 schema owner 的工程细化，原需求／Accepted ADR 的权威不变；不批准正式采纳、Task readiness、journal 发布或迁移启用。可执行字段定义只有同目录所引七份 JSON Schema，不另建消费者私有版本。

## 1. Sources and fixed boundaries

- AGENTS.md；_bmad-output/planning-artifacts/b-route/epics.md:590–637（Story 1.4 AC-1–5）。
- _bmad-output/planning-artifacts/architecture/architecture-newrouge-b-route-2026-11-03/planning-records.md:9–36（六记录、身份、引用、proof）；:40–44（映射及非 Flow）；:77（共享诊断）。
- 同目录 ARCHITECTURE-SPINE.md:225 允许共享 schema/owning 入口细化 JSON 扩展字段及内部拆分。公共身份、阶段、权威和恢复语义仍须落实。
- _bmad-output/specs/spec-newrouge-b-route/workflow-contract.md:5、:15–24、:39–64；SPEC.md 及 verification-contract.md、migration-and-pilot.md；docs/adr/ADR-0040-b-route-stages-authority-and-activation.md。

已定：六个 schema ID、记录目录、唯一写者、plan/binding 独立正整数修订及不可变历史、catalog 单一当前 owner、严格公共文件引用、零 Task 3B、planned、合法循环、唯一 Taskmaster 状态权威、receipt/catalog 无自引用 hash。

以下字段名、布局、枚举拼写、singleton ID、receipt revision 编码及函数签名是本轮冻结的低层选择，并非原需求逐字定义。Story 1.4 不增加业务状态机、执行解释器或第二套完成状态。

## 2. One owner and strict schema execution

使用 JSON Schema Draft 2020-12，六份 records JSON Schema 加 common defs 位于 docs/planning/b-route/schemas/，由 Python 公共服务加载；这不要求创建实际 policy/plan/binding 等记录。所有 object（包括嵌套对象、引用和结果）明确 required 与 additionalProperties:false；组合 schema 使用对应分支的封闭对象，避免用宽泛 extras/metadata 绕过扩展检查。本文中列出的对象字段均必需，允许空数组/null 的位置显式说明，不由解析器补默认值。

生产入口 scripts/python/_b_route_records.py；它加载六份完整 schema 并执行关系校验。身份只由现有 scripts/python/_b_route_codec.py:226 的 SCHEMA_IDENTITY_REGISTRY 拥有；六份 schema 不再复制另一份 entity/revision adapter registry。可向现有 SchemaIdentityAdapter 添加完整 schema/path 描述的关联，或由 records 模块按原 registry 查适配器。schema $id/本地资源只是验证文档索引，不是第二身份 registry。verification-scope 保持现有 None，仍 fail closed，不把它计入六类交付。

必须在 strict_json_loads/validate_json_value 后验证。jsonschema 默认 integer 会接受 1.0，故公共 Validator 的 integer type checker 必须使用 type(value) is int；bool、1.0、"1" 均不接受为 revision/Task ID。现有 validate_task_id、validate_business_id 继续是 join 类型权威。

所有 $ref 只指向本地 $defs 或显式注册的资源；common 可用相对 $id newrouge.b-route-common.v1。使用 referencing.Registry 的拒绝 retrieve 回调，不使用会自动抓取未知 URI 的旧 RefResolver。未知 schema/$ref 返回公共诊断，禁止联网补 schema。现成库已能满足，不新写通用 schema engine。外部来源 URL 仍只沿既有 source 注册，不由 schema 下载。

## 3. Primitive types and references

- S：沿 codec _string 的非空原字符串（type 为 str 且 strip 后非空），返回原值；允许原值带首尾空白，不做 trim/case/Unicode 转换。个别 owning 字段如 business ID 的现有不带首尾空白规则继续单独适用，不能扩大为所有 S 的新规则。
- I：严格正整数；D：sha256: 后接 64 位小写十六进制。
- FileId：S 且可作为一个原样的 Windows/POSIX 可移植文件组件；拒绝 slash、dot/dotdot、device/尾点尾空格等，复用 codec 路径检查。不从标题 slugify 或重分配已有 ID。
- PartKind：domain_rules | csharp_adapter | binding | scene。
- DefinitionKind：flow | command | state。这是逻辑定义类型，不是游戏完成状态。
- PublicRecordRef：原 TypedReference 七字段原样完整保留：

~~~json
{"path":"docs/planning/b-route/plans/p/1.json","schema_version":"newrouge.b-route-plan.v1","entity_id":"p","revision":1,"digest":"sha256:<64 lowercase hex>","verification_mode":"raw","codec_version":null}
~~~

raw 必须 codec_version:null；canonical 必须 codec_version:newrouge.b-route-json.v1。没有默认值，没有缺字段补齐，没有 immutable_bytes 或 task_definition_projection 这两种引用模式。

OwnedRef = {owner:S, ref:S, files:[{path:S, raw_digest:D}]}，三个字段均必需；files 非空。owner 冻结为封闭白名单：source_manifest、source_ledger、planning_proof、manifest、contract、overlay、adr、authority、other_verification、frozen_a_inventory、implementation_reference、verification_record、runtime_acceptance。ref 保存 owning 模块原有 locator/符号，不改成 B TypedReference；files 固定实际解析到的文件 bytes，不改写 owner 自己的 schema、revision、规范化策略或 proof。新增 owner 需修改同一公共定义，不能由调用方注册私有解释。

OwnedRef 是绑定外部依据的描述，不是外部记录新权威。source_manifest 的原 source_revision 是字符串，不能硬转为整数；contract 符号可由 resolve_contract 解析多文件。路径和文件集合须由对应 owner 解析后核对，不能只相信调用者 files。无法解析的必需依据拒绝；1.4 只证明 locator/bytes 关系，不重证 source/proof 业务语义、review/PASS 或 runtime acceptance。若某 locator 不支持，返回明确 unsupported_locator/invalid_reference，不能用成功 stub 接受。

最小可执行 locator 分派（此段为 owner 格式选择）：

- 文件 owner 无 fragment 时只定位文件；文件 bytes 来自统一 candidate-first byte cache，files 必须与实际解析集合逐路径/raw digest 完全相等，不容漏文件、重复路径或附加文件。
- verification_record 使用 _mvg_requirement_accounting.source_record_errors:323–364 的原定位语义：从完整 JSON 或 Markdown fenced json 中提取顶层对象/records 数组；#shared 按记录 evidence_id=="shared" 选择，至少存在匹配项。不把这种 fragment 解释成 JSON Pointer/heading。本 Story 只抽取和定位，不调用该函数完整的 status=passed、coverage 或 runtime 检查。
- implementation_reference 支持原文件及文件 locator；contract 符号显式分派 contract。runtime_acceptance 仅定位其既有文件/记录字节，不运行 runtime_record_errors，不据此判运行通过。
- 其余文件 locator 可明确支持文件本身、#/... 的 RFC 6901 JSON Pointer（对象精确键、数组索引、~0/~1；无效转义/不存在位置拒绝），以及 #L<n> 或 #L<n>-L<m> 的 UTF-8 原文行范围（1 起始且范围存在）。JSON Pointer 与行范围在对应 owner 分支按此语法识别，不对 native verification_record 改义。
- 普通 Markdown heading fragment 暂不自动猜 slug/Unicode 标题映射，返回 unsupported_locator；若 root 冻结已有确定的 heading 解析器，再复用其确切规则。不能把未支持 heading 当整个文件已定位而放行，也不能把合法 native #evidence_id 误拒为 heading。
- contract 沿 _chapter5_contract_bindings.resolve_contract 的现有符号/DTO 闭包规则，但不能直接先执行它的 root 全扫：先证明 contracts 目录/文件的链接根内并通过安全 reader 取 byte cache；候选同路径覆盖磁盘，候选新增 contract 文件加入可见集合。为同一 helper 增加显式预读 sources 参数/纯解析 seam，让旧调用保持默认行为，新适配只解析 cache；不复制第二 resolver，也不调用 disk 分支覆盖候选。每一实际闭包文件按原 bytes 验 raw_digest。helper 自己的原 text/归一化 digest 另保原语义，不拿 raw digest 替代。

LogicalDefinitionUse = {kind:DefinitionKind, definition_id:S, owner_plan_id:FileId, owner_revision:I}。它是记录内语义符号边，不是删减七字段的文件引用；其完整文件身份必须在同一次 catalog owner 上下文解析为 PublicRecordRef。公共 plan_ref、binding_ref、receipt_ref 仍全部使用完整 PublicRecordRef。

## 4. Six record shapes and identity adapters

以下所有路径加前缀 docs/planning/b-route/。schema_version 分别固定 newrouge.b-route-policy.v1、newrouge.b-route-plan.v1、newrouge.b-route-binding.v1、newrouge.b-route-origins.v1、newrouge.b-route-commit.v1、newrouge.b-route-catalog.v1。

| Record/path | Exact top-level required fields | Identity adapter |
| --- | --- | --- |
| policy.v1.json | schema_version, policy_id, policy_revision, switch_boundary, frozen_a_refs | policy_id / policy_revision |
| plans/<plan_id>/<revision>.json | schema_version, plan_id, revision, source_identity, requirements, definitions, logical_references, requirement_verification, requirement_route_memberships, requirement_evidence, evidence_source_refs, coverage_table, applicability, adoption_proof_refs, lineage | plan_id / revision |
| bindings/<plan_id>/<binding_revision>.json | schema_version, plan_id, binding_revision, plan_ref, stage, task_mappings, parts, implementation_objects, obligations, manifest_refs, other_verification_refs | plan_id / binding_revision |
| task-origins.v1.json | schema_version, origins_id, revision, tasks, frozen_legacy_refs | origins_id / revision |
| commits/<operation_id>.json | schema_version, operation_id, revision, operation_digest, scopes, authority, targets, plan_refs, binding_refs, resolved_definitions, result | operation_id / revision |
| catalog.v1.json | schema_version, catalog_id, revision, policy_ref, origins_ref, scope_heads, definition_owners, task_index | catalog_id / revision |

origins_id 明确为常量 task-origins、catalog_id 明确为常量 catalog；字段仍必须出现在文件中。commit revision 明确为常量 1，任何内容变化改用新 operation_id，不为不可变 operation 新造修订生命周期。policy_revision、origins/catalog revision 为 I；发布递增由后续服务核对。这组编码在本合同冻结，不从字段缺失自动推导常量。

plan/binding 受管存储地址中的 revision 必须等于无前导零十进制字段；binding.plan_id 必须等于 plan_ref.entity_id。B 记录存储使用架构规定的规范路径；引用 lookup 可以沿 codec 允许的根内拼写得到规范地址，拒绝冲突别名/重复目标及越界，不额外禁止本来合法的内部引用。lookup 规范化不得重写 payload、引用原字符串或用于 hash 的 bytes。提供 baseline 时核对同实体修订递增、同路径不同 payload 冲突；没有 baseline 不能宣称已证明跨历史单调性。

### Policy, plan and definition children

- switch_boundary = {default_route: A|B, a_write_allowed:bool, allowed_a_operations:[S], authority_refs:[OwnedRef]}。这只记录受审阅政策内容，不在 1.4 启用其效果；允许的旧操作词表需取原入口实际职责，不发明新路由命令。frozen_a_refs:[OwnedRef] 可空，不能从空集合推断 A 资格。
- source_identity = {manifest_ref:OwnedRef, ledger_ref:OwnedRef, source_revision:S, source_manifest_digest:D}。精确核对 source_manifest_digest == manifest.manifest_sha256 == ledger.source_manifest_sha256，source_revision == manifest.source_revision == ledger.source_revision，并保留 source_revision 原字符串。build_source_ledger.build_ledger:509–534 的 manifest_sha256 是 source binding 数组的 native canonical 身份，不是 manifest 文件的 raw SHA；OwnedRef.files[].raw_digest 则独立绑定原文件 bytes，两者不能互换。
- requirements = [{requirement_id:S, source_block_ids:[S], acceptance_intent:S, non_task_sinks:[S]}]；来源块非空且能在所引 ledger.blocks 的 block_id 中定位。non_task_sinks 是原 Requirement 去向身份的明确 ID 投影（不重建其完成权威）；other_verification 的 sink_id 必须在本 Requirement 的该集合中。定义引用既有稳定 Requirement ID，不新造 Task。
- definitions = {flows:[FlowDefinition], commands:[SharedDefinition], states:[SharedDefinition]}。容器可以为空；同类 id 在有效 owner 中唯一。SharedDefinition = {id:S, requirement_ids:[S], responsibility:S, uses:[LogicalDefinitionUse]}。它描述责任，不生成程序 API。
- FlowDefinition 最小布局 = {id:S, requirement_ids:[S], entry:S, entry_condition:S, success_end:S, branches:[{kind:failure|cancel|return,rationale:S,description:S}], handoffs:[{id:S,responsibility:S,state_uses:[LogicalDefinitionUse],result:S}], state_owners:[LogicalDefinitionUse], parts:[PartResponsibility], observable_result:S, verification_targets:[S], loops:[{description:S,exit_condition:S}]}。
- 这只承载明确的逻辑说明及引用，不穷尽未来 Graph/DTO；不要求运行节点已经存在。条件/责任/退出均为文本，不是可执行 DSL。不适用分支须明确理由，不用空值冒充。1.4 校验这些声明和引用；完整图端点、必要可达性、SCC 与退出语义检查仍由 2.4 owning planner 细化公共 schema 后承担，不能在同 v1 添加私有语义。
- PartResponsibility = {kind:PartKind, applicability:applicable|not_applicable, rationale:S, responsibilities:[S]}。每适用 Flow 各 PartKind 恰一行；not_applicable 必须理由，applicable 必须非空责任。binding.parts 是 Task 适用责任，不要求每 Task 机械四拆。
- applicability = [{requirement_id:S, disposition:flow|other_verification|deferred|source_gap, rationale:S, other_verification_refs:[OwnedRef]}]。other_verification 不能只有空数组或 N/A 标签；deferred/source_gap 只表达有据延期/明确缺口，不因此视作已完成。
- requirement_route_memberships 保持已有 {requirement_id,flow_id,observable_role} 键；requirement_evidence 保持已有 {requirement_id,evidence_id,kind,source_ref,covered_behavior,flow_ids,test_ids} 七字段及原 kind 词表 implementation_reference|verification_record|runtime_acceptance。三组既有顶层 keys 不改名，不改变其职责。
- 新增 evidence_source_refs:[OwnedRef] 是公共 schema owner 的明确格式选择，不是原需求已有字段。该数组按 (owner,ref原值) 唯一，为 requirement_evidence.source_ref 及下述非 null verification_ref/authority_ref 提供原 bytes 绑定。verification_record/runtime_acceptance 的 owner 必须等于其 kind；implementation_reference 文件用同名 owner，符号用 contract，且同一证据不得同时命中两个候选 owner。verification_ref 用 other_verification，authority_ref 用 authority。每处 locator 必须有且只有一个对应描述；每个描述必须被这三种 locator 至少一处引用，拒绝缺绑定/未引用附加描述。多个证据使用同一 owner/ref 时共享一份描述和文件 bytes，不重复计完成。source_ref 原值不改，不给证据行增加 raw/PASS 字段。
- requirement_verification 为原七字段处置 {requirement_id:S,disposition:flow|other_verification|deferred|source_gap,flow_id:S|null,rationale:S,sink_id:S|null,verification_ref:S|null,authority_ref:S|null} 加 evidence_ids:[S]，每字段必需。复用 plan_mvg.candidate_routing_schema:1618–1664 的处置分支：flow 要 flow_id，其他三引用均 null；other_verification 要 sink_id/verification_ref、flow_id/authority_ref 为 null；deferred 要 authority_ref，flow_id/sink_id/verification_ref 为 null；source_gap 四个可空引用全部 null。evidence_ids 仍按 (requirement_id,evidence_id) 引用原 evidence 行。
- coverage_table 每行严格等于相同 requirement_verification 行删除 evidence_ids 后的完整七字段对象，逐字段保留 null和值，不能只投影 disposition/flow_id 而丢 sink_id/verification_ref/authority_ref/rationale。此为 Task 无关 3B 公共分支，不把后置旧 coverage 的 capability_ref/task_id/authority_review 等字段自动编造或塞入；它们若由未来拥有阶段需要，须公共兼容性评估/升版或显式公共分支。_mvg_requirement_accounting.accounting_errors 的原逐字段投影一致性可作参考，但不能原样调用旧 Task/运行资格检查声称 3B 语义通过。
- adoption_proof_refs:[OwnedRef] 非空，引用已经独立存在的规划选择/准入依据；不能指向本次 B commit receipt。lineage = {previous_plan_ref:PublicRecordRef|null, change_summary:S, identity_alignment:[{kind:DefinitionKind,previous_id:S,current_id:S,rationale:S}]}；初始计划 previous_plan_ref 必须显式 null，历史引用方向只向旧修订。

### Binding, origins, catalog children

- stage 仅为 3C | 4 | 5（字符串），表示定义层级；不增加 Task 状态/转换规则。plan_ref 必须精确匹配 plan schema、plan_id 和单独的 plan revision。
- TaskMapping = {task_id:I, view_refs:[{view:back|gameplay,business_id:S}], requirement_ids:[S], flow_ids:[S], part_kinds:[PartKind], roles:[producer|consumer|integration_only_owner], obligation_ids:[S]}。TaskJoinContext 明确接收原 master/back/gameplay 三联，调用同一 join 适配器，不把 1 与 "1"/true 混同；视图 business ID 保持原字符串。没有 Task 映射的 3B 不要求三联/readiness，非空映射缺 join 上下文则不能声称关系已验证。
- ImplementationObject = {id:S, kind:command|read_only_state|adapter|binding|scene|resource, availability:planned|existing, responsible_task_ids:[I], expected_type:S, lifecycle:S, target_ref:OwnedRef|null, later_checks:[type|compile|binding|engine]}。planned 可 target_ref:null，责任和以后检查必需；existing 必须可解析 target_ref，但结构通过不证明实现正确。纯集成 owner 不被要求虚构业务对象。
- Obligation = {id:S, requirement_ids:[S], flow_ids:[S], test_ids:[S], responsibility:S, verification_refs:[OwnedRef]}。binding.manifest_refs / other_verification_refs 均为 [OwnedRef]；3C 允许尚未完成 4/5 绑定，5 的实际适用性/manifest/readiness 判定留所属消费者，不在此伪造通过。
- origins.tasks = [{task_id:I, source_refs:[OwnedRef], plan_refs:[PublicRecordRef], binding_refs:[PublicRecordRef]}]；frozen_legacy_refs:[OwnedRef]。空 tasks 合法；有 B Task 时精确核对完整适用 plan 集合及映射。无 Task status 字段。
- catalog.scope_heads = [{scope_id:S, plan_refs:[PublicRecordRef], binding_refs:[PublicRecordRef], receipt_ref:PublicRecordRef}]。
- DefinitionOwner = {kind:DefinitionKind,definition_id:S,plan_ref:PublicRecordRef}；definition_owners:[DefinitionOwner] 按 (kind,definition_id) 唯一。目标 plan 必须确实声明该定义；只看 catalog 选择的当前 owner 修订，不把所有历史 plan 文件当作竞争 owner。
- task_index = [{task_id:I,plan_refs:[PublicRecordRef],binding_refs:[PublicRecordRef]}]。以 catalog.scope_heads 选择的当前 binding 作为反向映射基准，不把候选 map 的全部历史 binding 一起计入；对每 Task，当前 binding 中包含该 Task 的精确 binding 引用集合、所引精确 plan 集合，必须分别与 origins.tasks 和 catalog.task_index 全等，而非仅子集/包含关系。重复矛盾、缺行、多行/多余映射均拒绝；空索引合法。无 status、done、runtime_verified、passed 等完成权威字段。

### Commit children and two different verification modes

- authority = [{path:S,before_digest:D|null,after_digest:D|null}]；显式 null 表示没有该前/后像，不能省字段。后续服务验证实际 authority，本 Story 只核对已提供身份关系。
- targets = [{path:S,before_digest:D|null,after_digest:D,verification_mode:immutable_bytes|task_definition_projection,codec_version:S|null,projection_digest:D}]。
- immutable_bytes 使用 raw bytes，codec_version:null，projection_digest 必须等于 after_digest。task_definition_projection 显式要求新 projection codec ID（冻结为 newrouge.b-route-task-definition.v1），不能借 canonical codec 名暗称已实现投影；本 Story 只冻结字段/枚举，投影计算由后续 owning resolver 实现。
- 此 target.verification_mode 与 PublicRecordRef.verification_mode 是两个不同封闭 schema；绝不把 immutable_bytes 传给 TypedReference，亦不把 canonical 当 Task 定义投影。
- scopes:[S]、plan_refs/binding_refs:[PublicRecordRef]；resolved_definitions:[DefinitionOwner] 冻结该 receipt 操作相关逻辑边的 owner 解析闭包，防止同 plan bytes 被另一 catalog 静默重解释。
- result = {target_paths:[S],scope_ids:[S]}；只概述正式目标身份/作用范围，不存 Task/Flow/游戏运行通过。
- targets 不能包含本 receipt 自身或最终 catalog 输出；plan_refs/binding_refs/authority/结果也不能以当前 catalog after digest 隐式重建该循环。允许固定旧 catalog 前像作为 authority。catalog 必须引用最终 receipt 的完整 TypedReference。

## 5. Cyclic behavior, cross-plan sharing and digest direction

不能把每条语义边直接写成对另一个完整 plan 的带 hash 文件引用：P 与 Q 双向共享时将产生 H(P)=f(H(Q))、H(Q)=g(H(P))。禁止这样的业务关系会额外缩减来源允许的循环/共享范围。

本合同的解法是分层，不改 codec 的 digest 算法：

1. P/Q 内行为图和 LogicalDefinitionUse 使用稳定符号及明确 owner plan_id/revision；它们可以双向、有 SCC/重试/返回，不含对方 whole-file digest，也不含 catalog/本次 receipt 的反向 hash。
2. 先从独立 bytes 计算 P/Q 的 raw/canonical digest。candidate catalog.definition_owners 将每个符号绑定到一个完整、精确的 owner plan TypedReference。
3. 在当前 candidate catalog 上下文解析当前 head 符号、在历史 receipt 冻结映射上下文解析其历史符号（详第8节），检查 kind/ID、owner plan/revision、目标确有定义；缺 owner、错修订、重复 owner 均拒绝，不取首次命中/最新文件猜测。
4. 从 receipt.plan_refs 及 binding 所引 plan 的全部已声明 LogicalDefinitionUse 开始，沿已解析 owner 定义的 uses/state_uses 等实际公共字段递归求闭包；visited key 为 (kind,definition_id,owner_plan_id,owner_revision)，遇回边只停止重复展开，不拒绝业务循环。receipt.resolved_definitions 必须与此相关 owner 解析集合全等，缺项/额外伪绑定拒绝。catalog 可保留无关 scope 的有效 owner，但不能将无关 owner混进本 operation 的闭包。以后 resolver 的 InputSet 同样纳入相关闭包；无关 catalog 条目不变成全仓新鲜度键。

因此文件身份 hash 依赖为 catalog -> receipt -> plans/bindings/policy/origins，catalog -> owner plans，binding -> exact plan；plan 的历史 lineage 只向旧版。业务语义图仍可循环。逻辑符号边不是可独立消费的公共文件引用；所有真正跨文件取 bytes 的身份仍由完整七字段 TypedReference 证明。

同时排除 plan.adoption_proof_ref -> 本次 receipt -> plan 的独立环：plan 只绑定原 planner/admission/selected 的既有 proof；本次正式发布关系由 catalog -> receipt 表达。若既有 proof 自带 digest，验证原 frozen proposal 的原格式，不把包含该 proof 的最终 plan container 冒充被原 proof hash 的对象。

这套两层解析已作为本轮公共格式冻结；不得以业务 DAG 限制替代合法循环，亦不改变 raw/canonical 身份算法。

## 6. Minimal read-only API and resolver behavior

公共接口；不改变现有 verify_content/verify_reference 的 identity-only claim：

~~~python
def validate_record(data: bytes | str | dict, *, path: str | None = None) -> RecordValidation: ...
def validate_bundle(
    records: Mapping[str, bytes],
    *,
    root: Path | None = None,
    catalog_path: str = "docs/planning/b-route/catalog.v1.json",
    baseline: Mapping[str, bytes] | None = None,
    task_join: TaskJoinContext | None = None,
) -> BundleValidation: ...
~~~

- validate_record 不要求所有六类实例同时存在，只证明单记录 schema/身份/给定路径；不把未解析的引用写成 verified。
- validate_bundle 从 candidate catalog 开始取完整必需闭包；3B 不要求 binding/Taskmaster 非空。部分记录调用必须仍是单记录结果，不能用 skip_missing 返回 bundle 关系通过。
- 两遍处理：第一遍对六类 B 记录 strict decode/schema/path/identity 并建立候选索引；第二遍解析 PublicRecordRef、OwnedRef、逻辑 owner、映射及 receipt 约束。候选 map 可以携带被引用的非 B 原 bytes，它们只按所属 owner 检查，不能拿 B schema 改写原格式。递归遍历用 visited identity 防重复，但不以检测到行为循环作为错误。
- 先按精确 path 取候选，再按 root 调用 read_reference_bytes；候选同路径错误 digest 时直接拒绝，不能退回磁盘凑绿。候选不在磁盘存在是正常情形；必需 B 文件引用候选和磁盘都缺失则失败。
- bundle 只收原始 bytes，收到 dict 明确拒绝；不能 json.dumps 后冒充 raw 文件。单记录若接受 dict，只能给 schema/canonical 身份，raw_identity:null；任何需要 raw 身份的引用都不得从 dict 得到 verified。
- CLI 的候选载体按 root 选择为 {records:[{path:S,source_path:S}]}：path 是正式逻辑路径，source_path 是仓库内候选源文件路径；安全读取原 bytes 后传给同一服务。载体不含 schema_version/正式发布身份，不是第七类治理记录，未知字段/重复 path 拒绝。record --repo-root --input [--record-path]；bundle --repo-root --input --catalog-path [--baseline] [--task-master/--task-back/--task-gameplay]；TaskJoinContext 接原三联对象并严格验证。
- 外部 owner ref 通过固定只读 adapter 解析 locator/files，文件 bytes 仍复用安全 reader；不启动 source generation、planner、readiness、模型或引擎。未能解析的必需引用不当作 planned。
- 同一次验证缓存观察到的原始 bytes，发现漂移拒绝；这只是只读观察，不宣称锁、隔离、正式 snapshot、journal 发布或 clone 正式可消费。
- 返回统一 Diagnostic（reason_code/stage/entity_id/expected/actual/resume_ref，空项显式 null），expected/actual 可带 path/json_pointer。新原因只在 codec 的公共 ReasonCode 增补，不建私有枚举。missing_required_field、unknown_field、invalid_enum、duplicate_owner、mapping_mismatch、digest_cycle 等具体新增词表仅由公共 ReasonCode 冻结。
- RecordValidation 的 claim=record_structure_only；BundleValidation 的 claim=candidate_structure_only。分别报告 schema_validated、references_validated、monotonicity_checked；不返回 ready/adopted/runtime_pass，也不升级原 VerificationResult.schema_validated:false。

## 7. Existing code and smallest test families

真实可复用接口：

- scripts/python/_b_route_codec.py：strict_json_loads:167、canonical_digest:204、SchemaIdentityAdapter:215、SCHEMA_IDENTITY_REGISTRY:226、read_reference_bytes:319、TypedReference:351、verify_reference:459、validate_task_id:112、validate_business_id:117。
- scripts/python/_mvg_requirement_routes.py：membership_schema:135、pair_errors:167、route_errors:190；scripts/python/_mvg_requirement_accounting.py：schemas:172、accounting_errors:224。复用键及纯检查，不能带入 legacy 缺字段自动投影。
- scripts/python/_chapter5_contract_bindings.py：resolve_contract:9；build_source_ledger.py：build_ledger:481 只作现有格式来源，不在只读校验时调用生成。
- scripts/python/_mvg_manifest.py：validate_manifest:60 带 Task/实现阶段假设，不作为 3B 通用 validator；scripts/python/_mvg_planning_review.py 的 coverage_errors 同样不能原样提前。scripts/python/_planning_apply_journal.py 仅为未来提交服务的复用点，本 Story 不实现/调用写入。

本 Story 使用一个公共 schema/bundle 测试模块，复用 test_b_route_codec.py 的 reader/identity 基础回归。最小样例族：

1. 六类最小合法 bytes 及闭包；字段缺失/未知、未知 schema、重复 JSON key、NaN/非有限数、bool/1.0/string revision、Task join 错类型、错枚举/路径/实体/revision/digest。
2. plan revision 2 对 binding_revision 7 的合法精确引用及错混反例；原 identity-only 返回保持；verification-scope 仍拒绝。
3. 零 Task bootstrap、3B 没有 binding、空 frozen A/origins/index；planned 缺文件而责任/后续检查完整，反例缺责任；非 Flow 有理由/其他验证及 N/A 空值反例。
4. P/Q 双向 LogicalDefinitionUse、Flow retry/return/loop 说明、共享定义和跨 Capability/多 Flow 关系合法；同 owner 复用不重复计数。重复/缺 owner、指不存在定义、owner 修订不符、扫描历史误报均有反例；不以这里的 fixture 冒充 2.4 的完整 SCC/可达性检查。
5. catalog -> receipt -> targets 的合法 bytes 构造；receipt 目标夹带自身/catalog 输出、plan proof 指本次 receipt、raw dict 无原始 bytes 明确失败。
6. candidate 优先于同路径磁盘及 contract 符号闭包；候选错 digest 不回退；根外 symlink、缺必需 B 文件/未知外部 owner/外部文件集合不符拒绝；schema $ref 未知 URI 被本地拒绝且没有网络调用。#shared native records/fenced JSON、JSON Pointer、行范围及不支持 heading 各有明确结果；不调用 PASS/runtime 证明。native manifest digest 与 raw digest 分别核对，不混用；evidence_source_refs 缺失/重复/未引用拒绝。
7. origins/binding/catalog 按当前 binding 的多 plan Task 集合全等及缺行/多行反例，历史 binding 不误参与；递归 owner 闭包有循环且精确全等。不接受新增状态/PASS键；全程仓库输入/输出树快照相同。baseline 缺失不谎称单调证明，相关 baseline 冲突拒绝。

测试代码最小调用形态（fixture factory 为测试局部，不是新增生产 API）：

~~~python
bundle = make_zero_task_bundle_bytes()
result = validate_bundle(bundle)
assert result.ok and result.claim == "candidate_structure_only"
assert validate_bundle(make_cross_plan_symbol_cycle_bytes()).ok
assert not validate_bundle(make_raw_reference_to_dict_candidate()).ok
assert not validate_bundle(make_receipt_catalog_hash_cycle()).ok
~~~

1.4 应验证 schema/只读解析边界；不重跑付费模型、游戏 TDD 或 journal 崩溃恢复。Windows 真机证据仍按新实现实际触及的文件语义确定，不能把本 Story Linux fixture 冒充 Windows 证据。


## 8. 本轮确定的实现细节

- 唯一执行位置为 docs/planning/b-route/schemas/common.schema.json 和 policy/plan/binding/origins/commit/catalog.schema.json；common 的 $id 为 newrouge.b-route-common.v1。schema owner 变更必须兼容性评估或升版；不允许未来阶段暗增私有 v1 字段。
- OwnedRef 使用上文封闭 owner 白名单及 locator 分派。source_identity 的两个 owner 分别为 source_manifest/source_ledger；adoption_proof_refs 只用 planning_proof 且不能位于 B commits/ 或当前 catalog；manifest_refs 用 manifest。本轮不承诺 Markdown heading locator，明确拒绝。contract 采用同 helper 的 keyword-only sources 纯解析 seam；旧默认调用行为保留。新 seam 的 sources 是完整安全读取的 contract 相对路径至原 bytes 的映射，候选覆盖磁盘，原解析中的换行／text digest 语义保持。
- requirement_verification 与 applicability 按 requirement_id 唯一且域等于 requirements；disposition/rationale 一致。flow 行的 flow_id 与 route memberships 及已声明／catalog-resolved Flow 对齐；evidence_ids 指向同 Requirement 的 evidence，evidence.flow_ids/test_ids 保原值和唯一身份，不伪造运行覆盖。deferred 必须可定位 authority，source_gap 只声明缺口。
- owner closure 分当前 head 与不可变 receipt 两个上下文，使用同一解析算法：扫描 plan.logical_references、commands/states.uses、Flow state_owners/handoffs.state_uses，按 (kind,id) 查映射并校验 pinned owner_plan_id/revision，递归追踪 owner plan；种子 plan 扫描其全部定义用法；递归命中 owner 后只扫描该命中 definition 自身的 uses/state_owners/handoffs.state_uses，以及其所属 plan.logical_references（明确为 plan-wide 公用依赖），不因同文件含另一个无关 definition 就扩张相关闭包。该 owner plan 若也是种子则按种子规则全扫。按精确身份去重终止，允许业务循环。catalog owner 定义域须与 scope_heads 选中的当前 plan 实际定义全等，lineage／附带历史不进入当前 owner 域。
- 每个 receipt 的完整 closure 从其 plan_refs 及 binding_refs 所引 plans 出发，**使用它自己的 resolved_definitions 冻结映射**解析；所得完整集合与该映射全等，所有所引不可变 B 文件仍核 bytes/schema/身份。此步骤证明历史 receipt 的结构自洽，不按当前 catalog 重解释其已被替换目标，也不把旧 plan 的外部来源/proof重证成当前语义准入。历史记录仅为 identity/结构前置；当前 head 所选活跃 plan/binding 才做本次 locator/native来源关系。
- 对每个当前 scope_head，另从它实际选中的 plan_refs/binding_refs 求当前 catalog mapping 下的相关 closure；该集合必须与所引 receipt 冻结映射中同一相关符号的完整 owner 引用一致。receipt 的其他历史 scope/目标条目不进入此当前集合。最小正例：R1提交互不依赖P1+Q1，R2仅将P推进P2，当前Q1仍引R1，应合法；反例：Q1实际依赖P1而当前 owner 改P2，必须暴露相关身份不一致。不得拿同一旧 receipt 的全部历史目标去约束当前无关 scope。
- origins／task_index 的 Task ID 域与当前 bindings.task_mappings 的域相等；每 Task 的完整七字段 plan_ref/binding_ref 集合分别全等，重复行/重复引用拒绝。TaskJoinContext(master,back,gameplay) 读取原三联对象，先 strict JSON/type，再用 codec.validate_task_id/validate_business_id；task_mappings 必须实际 join 到 master 及所列 view/business_id，不接受字符串转换或 bool。非空 Task 映射缺 join context 拒绝；零 Task 不读取三联。
- 非空 TaskMapping 的 view_refs 至少一行，必须实际 join 到同一 master Task 的已给业务视图，不接受 master-only 空引用冒充三联关系。binding.parts 按 kind 唯一；TaskMapping.part_kinds 只能引用本 binding.parts 中 applicability=applicable 的 kind。纯集成 owner 可以没有业务 part（part_kinds=[]，parts=[]），不为凑四部分或虚拟 API 新建对象。该唯一性是公共格式 owner 的明确细化，不是另一个 Task 完成条件。
- 单记录只做结构，但所有 TypedRef 必须经原 TypedReference 构造器核其自身词法／字段；OwnedRef.files 及非 contract 文件 locator、receipt 声明的 target/authority/result 路径复用 codec 的安全相对路径词法。此处不读目标、不解析根内链接、不声称存在或 references_validated；合法根内 ../拼写仍沿公共合同允许。
- 单记录 path 为可选受管逻辑路径。public API 沿上文签名，TaskJoinContext 为公共 adapter。CLI record --repo-root R --input P [--record-path P]；bundle --repo-root R --input P [--catalog-path P] [--baseline P] [--task-master P --task-back P --task-gameplay P]，所有输入文件统一安全读取。catalog-path 默认为 docs/planning/b-route/catalog.v1.json；input/baseline 为封闭 carrier {records:[{path,source_path}]}。只提供部分三联参数拒绝。
- 唯一身份 adapter 为 policy_id/policy_revision、plan_id/revision、plan_id/binding_revision、origins_id/revision、operation_id/revision、catalog_id/revision；origins_id=task-origins，catalog_id=catalog，commit.revision=1。无需额外 public identity registry。
- 新公共 ReasonCode：missing_required_field、unknown_field、invalid_enum、schema_validation_failed、schema_resource_error、dependency_unavailable、unresolved_reference、unsupported_locator、duplicate_owner、mapping_mismatch、digest_cycle。其余复用现有 invalid_type/invalid_reference/identity/revision/digest/conflict 等；Stage 只增加 schema/bundle，不建立私有诊断族。
- baseline 只用于已有字节及可证明实体修订关系：同不可变 plan/binding/commit 路径原 bytes 不可改变，已有实体的新增修订须大于已给 baseline 最大修订；提供不完整历史不冒充全历史证明。lineage.previous_plan_ref 若非 null，必须同 plan_id 且修订更小；不因 current revision>1 且未给全部历史而伪造 previous。record 始终 references_validated=false、monotonicity_checked=false；bundle 成功只证明当前已提供闭包，monotonicity_checked 明示是否给定且验证 baseline。
- targets／authority／result 的路径和摘要关系须一致。当前 head 实际选中目标及不可变 plan/binding/commit 的 immutable_bytes 后像核实际 raw identity；历史 receipt 中已被后续合法 operation 更新的 policy/origins 等固定路径可变目标，仅核其冻结摘要/authority/result结构关系，不能用旧 after 比较当前新路径而误拒无关 scope。结果必须列明未重验的历史可变 targets（operation/path），不能宣称全部历史后像仍新鲜，也不能回写旧 payload。task_definition_projection 本轮只核 codec/字段，绝不把未实现投影计算标 verified；target_projection_verified=false 明示，后续 owning resolver 再计算。targets 和 result.target_paths 均不得含本 receipt／最终 catalog；authority 对当前 catalog 只允许 before_digest，after_digest 必须 null。scope head 的 scope_id 必须在所引 receipt scopes/result.scope_ids 中，所选 plan/binding refs 必须是该 receipt 的已给定关系；不从“存在文件”推断提交发布。
- jsonschema==4.26.0、referencing==0.37.0 使用项目当前已安装版本，独立 requirements；旧 stdlib-only codec 无新增库导入。无可用依赖返回 dependency_unavailable，禁止弱 required-only fallback。

本轮未发现需改变用户玩法、既定阶段／权威或迁移方向的意图缺口。采用用户明确授权的常规技术自决；原生完整 dispatch，仍需实现后真实测试及三层独立审阅。
