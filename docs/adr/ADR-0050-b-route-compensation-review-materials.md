# ADR-0050: B 路线补偿审阅的版本化语义材料与原 owner 证明

- Status: Accepted
- Date: 2026-11-08
- Scope: Story 2.8 compensation review presentation / persisted auxiliary proof contracts
- Authority: 用户既定全权实施授权；Root 完整阅读并批准 [版本化设计](../../../night-handoff/story28-r44-pending-review-size-diagnostic/versioned-design.md)，随后明确同 policy v1 精确重放、跨 policy 严格拒绝及新增技术合同 ADR。实现验证尚待 Root 在最终源码屏障下执行。

## 问题与合同演进

实际合成协议失败发生在第三代补偿 `COMP-successor` 的审阅准备后。完整 subject 为 48,181,934 bytes；其中 `current_files` 携带旧 subject、重复 prompt/request 和 execution 的 stdout/protocol，逐代约放大八倍。真实 request 为 48,150,481 bytes，单次 turn/start 已超过原 32 MiB transcript 上限，也超过原 1 MiB 请求上限。此事实属于呈现合同的递归重复，不是模型重试或增加额度的依据。原失败材料、分母和回执保留，详见 [只读诊断](../../../night-handoff/story28-r44-pending-review-size-diagnostic/report.md)。

本决定扩展 ADR-0040 与 planning-records 的辅助审阅合同，并承接 ADR-0041 的资源及 metadata 边界；不替代六个正式记录 schema，不迁移原 operation/index，不更改正式采纳、原 Task 权威或阶段启用门禁。

## 新版本合同

完整 `newrouge.b-route-compensation-review-subject.v2` 与其 `current_files` 原始 bytes、结构及摘要继续保存。模型请求改为自包含语义 DAG：

- `newrouge.b-route-compensation-review-materials.v1`：每个历史 subject 的非 `current_files` 语义字段完整保留；历史 native/prepared/protection、原 request/preview/effects、当前计划、Task、Acceptance/history、来源与完整 scope 均保留。语义原件按精确 raw digest 去重，所有 frame/路径/历史图关系保留，不按路径合并不同时刻的 Task bytes。
- `newrouge.b-route-compensation-review-roles.v1`：逐文件记录 subject 身份、原路径、raw digest、byte 长度、全部角色和语义节点关系。host-only 角色只能由真实原 operation、原 host_review_ref、原 owner 认可的版本与固定 support 集合、精确 raw pins 派生。未知、缺失、冲突或不可重放证据失败关闭；同路径同 bytes 的语义角色优先，不能用 support 角色省略语义原件。
- `newrouge.b-route-compensation-review-presentation.v1`：绑定 full subject、materials、roles、完整检查分母与 policy。它不包含输出／proof／真实 request digest，避免 hash 循环。
- `newrouge.b-route-compensation-review-verdict.v2` 与 `newrouge.b-route-compensation-review-proof.v2`：显式声明 `complete_semantic_materials_with_owner_verified_host_evidence`，绑定上述摘要。proof 进一步绑定真实 request raw digest、schema/output/support 原像和实际独立 high/no-tools runtime 协议。新结果不声称模型读取了所有旧 protocol/stdout 原始 bytes。

`materials.json`、`roles.json`、`presentation.json` 位于原 review home 的 `w/` 外；`w/` 仍仅有实际 prompt/schema/output，防止 runner workspace wrapper 再次重复载入材料。模型 prompt 固定使用 `newrouge.b-route-compensation-review-delivery.v1` marker，直接以既有 compact-v3 无损编码完整 packet，并携完整 decoder 指令；不再包裹 legacy mvg-lossless wire envelope。冷 helper reader 严格验证 marker、完整 decoder 与 v3 body，保留原完整 canonical re-encoding、digest、AST／展开／深度门禁。同次render采用下述原子producer等价证明，完整生产／解码／精确比较仍共用原100M账户。新 owner、decoder 及传递依赖纳入 policy pins。新增辅助合同使用 owner 的 closed-shape 验证，不注册为六个正式记录 schema。

### 首代呈现失败后的固定 delivery 修正

Root 实际 `review-materials-stage1-01` 在新源873稳定屏障下运行首个方法，结果 1 error、其余七个方法未执行，尚未持久化首代 COMP-one 材料。初稿套用通用 planning wire 时，fresh envelope 的 encode/restore canonical 校验对同一 packet 连续 factor 两次；每次 reservation 为 58,986,853，两次下界已超过原100M。失败原结果 SHA256 `47163f4990deb25e435da65ee23718860e167d9e9a20c495c122de32090e1b83` 保留。完整 canonical packet 未落盘、原像不能恢复，未伪造体积或容量测量。

Root 据此批准上述固定 direct compact-v3 delivery；这不是失败后的自动 fallback，不改共享 wire／compact／runner／资源 owner，不关闭 canonical 检查、不拆分账户、不增加限额、不删原语义或缩 seed。实际完整 request 的 bytes／70k token 与 codec work 仍须由 Root 在本次最终新源下量测。详见 [静态诊断与提案](../../../night-handoff/story28-r44-material-codec-diagnostic/repair-proposal.md)。

### 原子 canonical producer roundtrip 的技术补充

上述记录描述第一次direct修正的授权范围；随后原同账完整冷重编码再次真实耗尽。Root完成固定capture的三项独立诊断：plain完整frame保守124096 tokens、v2为83217，均超70000；原v3完整frame为128170 bytes／51465 tokens，独立cold decode加exact比较为72272548 work。source873和15份既有tokenizer/cache前后闭合；诊断close SHA `eed07b17384befbb358d7b353fdd281a1bb941dfc1cf0a9e7c2e1cacc2a1f199`。这些独立账户不能拼成原warm成功，也不是Story验收。

Root因此另行明确授权最窄共享codec API `produce_canonical_roundtrip(value,schema,work)`：原JSON/type/depth/node/byte门禁之后，按原展开/cache上限和同一work账户先保留复制资源，建立模块私有稳定snapshot和有序／类型精确JSON原像。只调用本模块已绑定的真实原dumps生产C，完整保留原parse/keysets/refs/usage/restore/digest gates，再精确验证restored与snapshot、当前输入的JSON逐字相同。由C=E(snapshot)且restored=snapshot推出E(restored)=C，复用的是同次真实canonical生产证明，不是caller批准或省略规范性条件。

API不接受外部text/body、approved布尔、producer、可转移witness或skip开关；不缓存／序列化／跨action传递结果。私有snapshot、原像及解码cache合计先受原64MiB／nodes／depth界限检查，所有真实序列化／复制／parse／比较继续计费；半输出、资源不足、输入变异、类型／顺序差异都拒绝。公开冷loads签名、完整canonical重编码、异常保护和既有v1/v2/v3拒绝条件不变。helper冷read_prompt也保持不变；warm render只消费本次原子结果，最后仍比较实际完整packet和restored。v3正文、模型header、schema与proof绑定不变，源码policy自然改变，旧proof不改签或升级。

作者只作静态门禁对账和测试编写；首代／原pending第三代在此新源下是否满足同账100M仍须Root实际执行。不得提高上限、删义务或缩原fixture来获得成功。

## v1 与 policy 的精确边界

同 policy 的历史 v1 proof 仍由原 v1 prompt/schema/request、原 machine／semantic 规则、原 receipt/stdout/protocol/runtime 和独立线程门禁验证。它不能按新 packet 重放或自动改名升级。测试中在新冻结源码下逐阶段生成的 synthetic archive 是同 policy 正例；它不冒称真实历史运行。

跨 policy 的既有原件严格拒绝：原 subject 的 policy 必须与已安装 owner 精确一致。添加本 owner 会改变 policy，因此旧失败 TEMP 原件只用于诊断，不能直接作为新源 proof、重签或改写为新 policy。若未来需要跨 policy 历史验证，必须另行提供明确授权、版本绑定的完整原 owner 源码／schema／解释器身份与验证权威；当前聚合 hash 不能反推出旧实现，也不允许任意运行时 import 或临时兼容豁免。

## 资源、写入与验证责任

原 1 MiB request、配置的 70k／默认 96k token、32 MiB transcript 以及 codec encoded/expanded/work/node 上限保持。实际完整 wrapper+schema 在持久化前通过原 byte/token 计量；容量失败不 dispatch、不 retry、不缩分母、不重置预算。材料推导、lossless 编解码、完整旧协议及 bundle 验证均在 WRITER 外完成。短 writer 只比较同次已校验的原始文件与 policy pins，支持文件 proof 摘要来自实际验证的同批 buffers。

原 Task/status/Acceptance/history、B 来源、累积义务、旧 marker/partial intent/operation/index 行及 unknown bytes 不改变；旧 pending 仍只由实际 owner 的精确 successor 正式链派生 resolution。

七组验证覆盖原像与全历史语义／真实 wrapper、owner 角色与双角色优先、语义删改、同 policy v1 exact replay 与跨 policy 拒绝、新合同和协议摘要漂移、未改资源边界及写前容量失败、原精确 partial-pending successor 场景。作者只做静态 AST/JSON/hash 检查，实际容量与整条成功路径由 Root 执行；静态检查不构成 Story 2.8 验收或 native 资格。

## Explicit compact-v4 and delivery-v2 residual-prefix contract

Root authorized this narrow versioned implementation on the recorded local checkpoint `66b232b849ce2f11122fa250b493065072b9dd78`. The fixed 793036-byte archived packet retained every original semantic/audit field. Its previous v3 atomic action completed at95526286/100M; the complete211138-byte warm frame was rejected at94538 conservative tokens by the original70000 gate. Cold was not run. Root close `2a7e428555b4b7ac8c0459c136b202eccf2d11046c72f6fd9f14b7341443ecaf` preserves that failure. These observations do not qualify a current review or complete Story2.8.

`newrouge.b-route-compact-literal.v4` adds only a deterministic canonical residual-prefix selection rule using the existing visible P/C data grammar. v1/v2/v3 keep their original schema identities, instructions, producers and cold canonical rules; v3 is never silently reinterpreted under the new rule. v4 first performs the original v3 packing/factoring once, then examines only residual literal value leaves. It preserves original phrase definitions and indexes, appending complete literal definitions for profitable exact residual prefixes or duplicate full leaves. Lexicographically adjacent distinct leaves provide exact LCP candidates; there are no per-offset suffix copies, all-pairs scans, hash-only equality, external dictionaries or omitted original bytes. Existing P/C restoration preserves raw strings, JSON type/order/float/signed-zero semantics and all request/material/proof identities.

One adjacent prefix per distinct leaf plus duplicate full leaves bounds candidate copies by twice the distinct residual character count. Selection uses actual occurrences from one fixed longest/lex-ordered matcher; benefit filtering does not change its winners. The replacement pass uses that same matcher, so overlap cannot manufacture extra occurrences. A conservative full spelling benefit includes the new definition, reference digits, quotes, separators and concat boundaries. All comparisons, sort/moves, exact hash/equality reserves, slices, matcher/index/metadata allocations, traversal, rendering and cleanup credits are prepaid in the caller's original100M account. Local maps clear in `finally` without another spend masking a primary refusal/MemoryError. This is a finite logical/work bound, not a64MiB process-RSS claim. Existing8MiB encoded,64MiB expanded/cache, nodes/depth and final request1MiB/70000/default96000 limits stay unchanged. Full atomic E+D+ordered/type-exact current-input comparison and cold D+canonicalE remain mandatory.

`newrouge.b-route-compensation-review-delivery.v2` explicitly selects compact-v4. `read_prompt` also retains exact delivery.v1/compact-v3 reading, selected only from its explicit marker and matching complete decoder/body schema. Mixed or unknown markers/decoder/body versions reject; there is no parse-failure fallback. The semantic materials/roles/presentation/packet v1 and verdict/proof v2 contents and meanings do not change. Installed review policy already pins both changed owners; normal new review generation and verification bind the actual new prompt/request/schema/output raw identities. Legacy delivery-reader compatibility is distinct from proof compatibility: same-policy original proof.v1 uses its original exact saved verifier; cross-policy old proofs, including old materials-proof.v2, still fail the original `read_subject` policy gate. No old evidence is re-signed, upgraded or automatically replayed under a different producer.

This is a static implementation record. New small tests and genuine fixed-packet atomic/warm/cold fit remain for Root's independent source-bound execution. The prior94538-token refusal is unchanged; no saving, performance, capacity, formal acceptance, native qualification or readiness result is claimed by writing this version.


## Delivery-v3 / transport-v1 transparent original-operation view (candidate)

Root authorized this owner-only candidate after the source-bound v4 targeted eleven methods passed, while the unchanged archived 793036-byte packet still failed the complete-frame capacity gate: atomic 98736346/100M, warm 99273625/100M, 174727 bytes and 73962 conservative tokens against 70000. Cold was not executed. Root close `bf24d6a0ac1498cbee19c542a1ee612b2060705e6a86e75d72dbff9443365670` remains the failed observation. This amendment does not upgrade that evidence or promise capacity.

The new explicit `newrouge.b-route-compensation-review-delivery.v3` header selects `newrouge.b-route-compensation-review-transport.v1`, encoded by the unchanged compact-v4 grammar/producer. The envelope has exactly four ordered fields: `schema_version`, `original_packet_ordered_digest`, `packet_core`, and `views`. It is a versioned transport representation of Packet1, not a new semantic packet, proof, operation, or generic compact syntax. All compact-v1/v2/v3/v4 implementations and defaults stay unchanged. The reader retains explicit delivery.v1/compact-v3 and delivery.v2/compact-v4 Packet1 routes; mixed or unknown headers, decoder instructions, transport versions, and body schemas reject without fallback.

`views` contains zero or one closed `original-operation-json2-lf.v1` row. Its only possible source is `['materials','frames',i,'semantic_fields','original_operation']`; its only possible destination is `['materials','documents',j,'text']`. Eligibility comes from the complete current frame's `semantic:original_operation` file role, original operation version/ID/path, exact owner provenance, `document_ref`, raw digest and raw byte correspondence. The source complete operation object stays visibly printed in the same envelope. It is serialized with insertion order, `ensure_ascii=False`, `indent=2`, default JSON separators, `allow_nan=False` and exactly one final LF. The resulting strict UTF-8 bytes must equal the COMPLETE original document text bytes before any replacement. No digest, base64 fragment, client length, hidden archive or external lookup substitutes that source.

Select the largest eligible exact document by actual UTF-8 size, then frame index and document index. Ineligible formatting (including CRLF), a different owner role or a nonmatching complete document remains literal. Only that destination becomes the exact ordered placeholder `{'schema_version':'newrouge.b-route-compensation-json2-placeholder.v1','view':0}`. The rest of Packet1, every frame/file/role/raw identity, every original field, and document order remain unchanged. Full restoration executes the original Packet1 validator, exact restored raw count/digest and the complete original packet ordered digest. A zero-view envelope also carries the complete Packet1. Closed fixed paths cannot access a filesystem, point to another view, overlap a source object or form a view dependency cycle. Unknown/missing/duplicate/reordered view metadata, bool/negative/out-of-range indexes, changed owner provenance, placeholders or versions fail closed.

The envelope's original packet digest is over strict UTF-8 of complete insertion-ordered compact JSON (`ensure_ascii=False`, separators `(',',':')`, `allow_nan=False`), not the sorted semantic `canonical_digest`. This independently binds key order, bool/int/float and signed zero. Cold reads execute the original complete compact decoder and the genuine unchanged compact-v4 producer canonical re-encoding on one caller work account, then restore/validate Packet1, verify its ordered digest and rederive the unique owner view plan. This private adapter calls the original `_decode_complete` and `_ATOMIC_PRODUCER`; it introduces no generic skip flag, decoder grammar change or caller witness.

Warm production makes one actual private Packet1 JSON snapshot and immutable ordered text witness in this call. It derives an envelope solely from that private data, freezes its complete ordered JSON witness, invokes the genuine unchanged compact-v4 producer and complete original decoder on the same account, and proves both restored and current private envelopes equal the frozen witness. It restores Packet1 and proves its COMPLETE ordered JSON equals the original witness, then separately compares the current caller Packet1. The envelope digest was computed from that exact original witness; full restored packet equality proves its digest without hashing the same full packet again. This is the same local canonical argument as the existing atomic producer, with an owner-bound envelope and explicit external live-data credits. There is no caller-supplied text, approved boolean, cross-action cache, new work account, or omission of full decode/exact/current-input checks. Failed encoding/decoding/formatting, input mutation, work refusal and MemoryError publish no prompt.

Actual graph preflights precede snapshot/ordered JSON and formatter allocations. For source metric `m`, JSON2 byte bound is `G=m[5]+4*m[1]*(m[2]+1)+1`: actual compact JSON wire bytes plus conservative indentation/separator/LF allowance. Strict UTF-8 comparison is prepaid from that graph-derived bound, never `raw_bytes`. Owner live checks conservatively include caller/private graphs, envelope and decoded graphs, immutable JSON witnesses, copied header/body, generated text/UTF-8 buffers and copy-on-write shells; formatter text is credited by `6*G+2` plus transient raw buffers. These are logical retained-data bounds under the existing metric, not a Python RSS guarantee. Original graph/node/depth/64MiB and encoded8MiB limits remain; all added metadata walks, ranking/moves, dictionary copies, serializations, UTF-8, hashing and comparisons debit the original work account before the corresponding operation. No cleanup spend replaces a primary exception. The original validator remains intact. Final full frame still passes the original encoded preflight; real request1MiB/70000/default96000 gates and all model/host budgets remain unchanged.

The candidate changes only the material helper, associated resource test additions and these implementation contract notes. Installed policy already pins the helper and compact owner. New requests/proofs bind the actual new prompt/request and current policy; older delivery readability confers no cross-policy proof replay, resigning or historical qualification. Same-policy proof.v1 remains its original saved verifier route. Full subject/current_files, original semantic DAG, Task/Acceptance/history/B-source/scope and original effects remain unmodified. Source integration, new tests, exact archived-packet atomic/warm/cold capacity and formal acceptance require Root's separate source-bound execution. Author work is static only.


## Explicit adoption-proof-v3 historical-owner follow-up (proposed)

[ADR-0053](ADR-0053-b-route-historical-v3-original-owner.md) records the R57 source-integrated, separately versioned historical route for original adoption `expanded-semantics.v3` / proof.v3 and qualified public-history/compensation v2. This is distinct from this ADR's compensation delivery.v3/transport.v1 codec view. The actual original R56 policy/owner, distinct original R52 producer and complete original proof/runtime/raw archive are verified as history; no old ticket is re-signed under current policy and no fresh-empty/current-target admission is replayed to authenticate recorded historical absence. Current compensation authority/current-before/scopes remain separately checked.

The default authority.v2 remains null and rejects before historical-worker release. Real proof-v3/public-history/compensation positives and formal acceptance have not run at this checkpoint. Existing legacy thirteen-method compatibility remains a separate verification scope; integration or neutral predicates do not count as its runtime pass. All original evidence, resource/fiscal bounds and original AC are retained.
### Qualified v2 的实际保留量（2026-11-11）

当前 owner 在 derive 返回后将完整历史 auth 按原 ordered JSON 加一个 LF
冻结为实际 `historical-auth.json` bytes，释放重复对象图。该产物原文完整，
不作为摘要、caller approval 或新身份令牌；原重派生、持久化与完整比较继续适用。
SavedHistory 与 saved context 按实际 graphs/buffers 计量，不再把已释放图计入。

warm 编码保持独立私有 snapshot 和 immutable original；编码阶段保留 body
的一个原8MiB预留。producer 返回后释放 snapshot，完整 decoder、validation
和 restored/current 双 ordered exact 依次执行；最终 frame 的保留量在结束
比较临时值生命周期后、真正 join 前检查。原通用 atomic API、冷 canonical
重编码、64MiB/8MiB/100M 门禁以及完整 wrapper 的1MiB/70k与输出预留不变。

Qualified v2 warm render 的输入只做原 JSON/type/node/depth/bytes 预检；完整语义
校验在实际 D(E(snapshot)) 上执行，并用完整 ordered exact 绑定回输入、独立核对
当前 packet。所有拒绝均在返回 prompt 前，省去同次输入的重复语义验证；不取消
完整 decoder、冷 canonical 重编码或原资源限额。prepare08 的100M失败保留，
两项受影响正反复验证据为 `story28-r62-render-retention-tests-03/result.json`，
不代表真实大材料或 Story 已通过。

### 实际编码预算缺口：单次归一化

prepare09仍在原100M账户内明确拒绝，位置为真实substring query的第二遍全表
归一化。经干净Astra max评判，`lengths_for_leaf`利用最长后缀起点单调不减，
每个输出位置只在终值已确定时写入，消除重复raw-end写入及第二遍全表扫描。
原完整返回表、append/epoch、schema/canonical、收费单位与资源限额不变；
每项实际新操作仍在同一work账户预付，不能据此保证每种输入都更便宜。

原BulkSubstringQueryTests七项通过；只对加入v4完整canonical差分与实际
charged/charged-1边界的两个方法再做定向复验，均自然OS0通过。证据：
`story28-r62-substring-one-pass-01/result.json`、
`story28-r62-substring-one-pass-02/result.json`。未运行全资源套件，
这仍不是原现场prepare、模型或Story正式通过证据。
