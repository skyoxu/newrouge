---
title: 'Story 2.8：共享提交恢复与受审阅补偿'
type: 'feature'
created: '2026-11-08'
status: 'in-progress'
route: 'dispatch'
baseline_commit: 'db1f4409d538e56eabedd4d1bce5bff9e0f34a1c'
review_loop_iteration: 0
context: []
---

## Cloud continuation: published history (2026-11-12)

Original AC4 remains unchanged. Under the user's explicit direction and a clean
Astra max proportionality assessment, [ADR-0056](../../../../docs/adr/ADR-0056-b-route-published-history-compensation.md)
adds a distinct published-only Cloud history verifier and explicit review v3
profile. It verifies genuine publication and exact saved evidence/full recorded
public semantics, and does not claim execution of the original owner. Old proof
and reader meanings, all current compensation gates, independent new review,
Task/status/Acceptance/history/B-source and budget obligations remain.

Actual Cloud factory/build and full public prepare reached the unchanged
capacity gate: final full request316310 bytes; genuine render147247600/170M.
Complete cold canonical reading and focused profile/publication/owned-before
checks have separate passing evidence. The current UTF8 upper-bound counter
rejects316310+2000 at70000; original prepare11's101371-token failure is retained.
No new provider review, real compensation reserve/apply/publication or formal
Story acceptance follows. Complete results and failed attempts are preserved in
`logs/ci/2026-11-12/cloud-epic2-recovery-15/REPORT.md`. Status remains in-progress.

<frozen-after-approval reason="按用户既定全权实施授权由 Root 确认；原始 AC1–5 范围不变">

## Intent

完整落实原始 Story 2.8 AC1–5：同一公共提交服务按实际文件恢复缺失步骤，未知编辑保留并阻断；旧 pending 回到原 apply 合同；补偿使用新受审阅操作，以当前前像、原副作用和实际完整 scope 保留历史、后编辑、当前 Task 状态及 B 来源。覆盖已绑定 Task 的 plan/binding/origins 同步，不能以 plan-only 缩减 AC4。

## Boundaries & Constraints

始终复用唯一 commit 引擎、既有 journal、原锁序及六正式 schema。原 v1 语义和原 operation/index 行不可改；补偿用严格版本化辅助 v2 envelope/frozen 分派，新 ID 追加索引行。scope 由当前正式链推导，不接受调用者自报授权。独立 review 绑定完整当前前像、原副作用、累计义务、Task join、来源及新请求。

补偿只能选择实际正式链验证的既有 plan/binding 语义/refs并生成必要的合法治理/不可变修订；若需要新 planning 语义，诊断回原真实 adoption 入口。保留当前 Task done/status、定义、Acceptance、历史和 B origins；会丢失原 BTask 映射/history 的 delta 拒绝。

after 跳过，完整发布 no-op，receipt 不 hash 自身或最终 catalog，catalog 最后发布。禁止假 nativePlan/proof、approved 布尔捷径、覆盖后编辑、旧 before 直还、删除 B 来源降 A、擦证据重试、模型候选恢复、新模型调用或预算/epoch/reopen 重置。

长检查不持全局 writer/metadata 等待，短副作用重取原保护并重验；不得只在外层增加无锁 preflight 却把原长全量检查留在 writer callback。源码只写隔离 R44；Root 独占实际测试、CLI、native、模型和 Git 执行。原 2.6/2.7 正式前置未通过，不据离线代码宣称正式验收、readiness/runtime 或默认 B。

## I/O & Edge-Case Matrix

| 场景 | 输入 | 预期行为 |
| --- | --- | --- |
| 未写/仅 marker | 原 reserved 请求及真实 before | 新鲜原 admission 后补缺步 |
| 部分写/已写未发布 | 完整 intent 与 exact before/after | after 跳过，仅补合法步骤 |
| 已发布未清理 | 保存的发布镜像及实际正式链 | 仅清本操作 marker；保留无关后续发布 |
| 完整同内容 | 真实终态及有效相关来源 | no-op，不重写已完成副作用 |
| 编辑/损坏/相关漂移 | 未知 bytes/规则/引用 | 原现场保留，统一 expected/actual/resume 诊断 |
| 旧 marker/journal | Capability/MVG 原身份 | 原 owner route；未知 scope 保守阻断 |
| 受审阅补偿 | 新 ID、当前前像、原 effects、实际 scope | 同引擎新修订，同步绑定/origins，保状态/Acceptance/B 来源 |
| 未授权/过期补偿 | 旧 ID、缺 review、错误 scope/前像 | 写前拒绝，不退旧格式 A |
| Windows 故障/竞争 | 占用、退出、重启、清理失败 | 完整提交或明确阻断；无混合消费，无关 scope 可推进 |

</frozen-after-approval>

## Code Map

- `scripts/python/_b_route_commit.py`：唯一副作用 owner；事实分类、恢复、补偿准入分派、正式读取和终态。
- `scripts/python/_b_route_operation_scope.py`：原 pending/legacy 合同、精确补偿关联、同锁族业务租约及短 writer 边界；复用 `_b_route_operation_leases.py`，不新增 mutex。
- `scripts/python/_planning_apply_journal.py`、`scripts/python/_b_route_schema_resources.py`、`docs/planning/b-route/schemas/compensation-operation.schema.json`：闭合辅助协议及版本分派，共用原 operation 目录和完整 index，旧 v1/六正式 schema 保持。
- `scripts/python/_b_route_compensation.py`：从当前正式链派生补偿前像、原 effects、旧/当前/新 scope、合法既有语义及新修订；不复制提交引擎。
- `scripts/python/_b_route_adoption_review.py`、`scripts/python/_b_route_adoption.py`：明确 producer 的独立 subject/support/规则身份及公共 allocation claim；真正 adoption 仍走原 native 准入。
- `scripts/python/_b_route_commit_projection.py`、`scripts/python/_b_route_records.py`：显式验证补偿与既有正式 refs/新修订来源，统一 receipt/catalog/read；不把 source 校验改成跳过或自报。
- `scripts/python/b_route_adoption.py`：direct/dev_cli 共 owner；新 `scripts/python/tests/test_b_route_commit_recovery.py`、`scripts/python/tests/test_b_route_compensation.py` 与固定 `scripts/python/tests/fixtures/b_route_commit_process.py` 验证恢复、补偿及真实 IO/锁。

## Tasks & Acceptance

- [ ] `scripts/python/_b_route_commit.py`、`scripts/python/_b_route_operation_scope.py`：依真实目标/receipt/catalog/完整 authority 分类和有界补缺；legacy 返回原 owner，不改旧历史。
- [ ] `docs/planning/b-route/schemas/compensation-operation.schema.json`、`scripts/python/_b_route_schema_resources.py`、`scripts/python/_planning_apply_journal.py`：严格辅助 request/frozen/envelope 与明确 producer 分派，共用 allocation/index；未知版本/字段/错绑写前拒绝。
- [ ] `scripts/python/_b_route_compensation.py`、`scripts/python/_b_route_adoption_review.py`、`scripts/python/_b_route_adoption.py`：完整 AC4 的当前正式链派生、独立审阅和新 ID；包含绑定 Task 的合法正例与保留义务。
- [ ] `scripts/python/_b_route_commit_projection.py`、`scripts/python/_b_route_records.py`：复用六正式 schema/唯一写入，验证新修订的既有语义来源、receipt、catalog-last 和实际读链。
- [ ] `scripts/python/_planning_apply_journal.py`、`scripts/python/_b_route_operation_scope.py`、`scripts/python/_b_route_commit.py`：精确关联旧 stale pending；仅从新补偿真实 terminal 派生 resolved_by；拒绝环/自补偿/冲突，旧原始历史不改。
- [ ] `scripts/python/_b_route_operation_scope.py`、`scripts/python/_b_route_commit.py`：同原锁族持业务保护做长检查；原 metadata/WRITER 只保短写和 catalog 边界。旧 writers 不改，相关内容在短边界重验；无关 catalog 推进则离开 writer 重算或明确 stale。
- [ ] `scripts/python/b_route_adoption.py`、`scripts/python/tests/test_b_route_commit_recovery.py`、`scripts/python/tests/test_b_route_compensation.py`、`scripts/python/tests/fixtures/b_route_commit_process.py`：共享入口及每行 I/O 矩阵正反例，故障重启、占用、原 pending 接续、后编辑/Task done/B 来源保留和实际无关 scope 进展。
- [ ] `scripts/python/run_gate_bundle.py`、`scripts/python/tests/test_b_route_runtime_ci.py`、`docs/workflows/story-2-8-public-recovery.md`：完整新模块注册一次，保 funding/OSworker selectors，文档如实列明边界；Root 执行实际验证、前置资格与原生 Step4/5。

Given 完整原 authority 和 before/after 有效，When recover，Then 只补合法缺步且保原请求/分配。
Given 未知后编辑或相关来源/规则损坏，When 恢复/补偿，Then 写前停止并保全部证据。
Given 旧 pending 未消歧，When 新入口检查，Then 返回原 apply 合同且相关读取持续阻断。
Given Task 已完成且存在后续合法修改，When 新受审阅补偿发布，Then 当前状态/Acceptance/后编辑/B 来源保留，绑定与 origins 一致。
Given 旧 claim 因 authority 漂移而 pending，When 精确绑定的新补偿合法完成，Then 仅由真实正式证据派生 resolution，旧 claim 不伪称发布且其他 pending 不获豁免。
Given 故障或竞争，When 恢复及读取，Then 同一正式链完整可读或明确阻断，无关 scope 不因长检查等待全局锁。

## Implementation Notes

2026-11-08 Root补充实施记录：source873固定capture benchmark的v3完整frame为128170 bytes／保守51465 tokens；plain/v2超70000，cold独立72272548 work不能拼接原warm失败。Root明确授权shared compact owner的genuine atomic producer roundtrip：私有稳定有序／类型精确JSON snapshot、原dumps及全部primitive decoder门禁，同一原100M账内以exact snapshot证明canonical等价；冷loads/read_prompt仍完整重编码，不开放caller text／approved／witness／skip入口。v3 header、完整语义／proof、原阈值及上方冻结Intent均不变，不升级旧proof；本次新源首代／第三代实际通过与否仍由Root唯一执行验证。

2026-11-08 Root 技术修复范围：实际 `COMP-successor` 合成协议因递归携带旧 review 支撑形成 48,150,481-byte request 而被原 transcript guard 拒绝。Root 完整阅读并批准 [版本化设计](../../../../night-handoff/story28-r44-pending-review-size-diagnostic/versioned-design.md)，授权补偿／审阅 owner、一个确定性材料 helper、相关测试及辅助合同文档的最小产品修复；不重新渲染 nativeBuild 工作流，不更改上方冻结 Intent。实现新增完整历史语义 DAG、原 owner 派生角色与显式 presentation/verdict/proof 版本；原 full subject/current_files、业务分母、pending 原件和资源预算保持。作者仍只做静态检查，Root 绑定最终全源码实际验证。

当前 Step3 状态（2026-11-08，Root）：恢复及 v2 补偿 producer、公共接线和 35 项新测试已编写。验证后重新 pin 的来源窗口已在明确的五文件范围修复，并新增五项负向/原 pending 用例。Root 已完整读取初始差异及此次窄修，合入 R41 固定锁目录初始化修复。当前组合源码首批六项实际检查全部通过，754 个来源的收口核验稳定、无 skip/隔离拒绝/子进程/模型调用；其中五项属于新用例，一项是 CI 定向回归。其余 30 项新用例（含四项 Windows 进程测试）及 23 项定向旧回归仍待执行，不提前计作通过。旧 smoke-01 未执行且失效，原始记录保留。正式 2.6/2.7 前置、原生 Step4/5 及 2.8 正式验收均未完成。

以下保留原 Step2/原型阶段的历史记录；其中“尚未编写/实现”只描述当时状态，不代表当前完成结论。

原先仅恢复增量的作者草稿已逐字保存在 `logs/ci/2026-11-08/story28-r44-author/draft-intent-pre-native-01.md`，SHA256 `78ace821ee0ac393d34f99f42d4516e1463416e6c08fb0b191c4ed23e40bd7c2`；其中 AC4 open 是进度而非用户排除。

已 authored core 和 14 个新 recovery 测试方法；只做 AST/JSON/hash，未执行任何项目代码。补偿 producer 尚未编写；完整 AC4 仍待实施。Root 已完整读取实际 rendered workflow/Step1/Step2/template，并完成独立调查及下列技术裁决；本文件在审批重读前保持 draft。

此前 raw-source 步骤阅读不算原生流程执行；Root 已 exact-once render，本作者只读其 workflow，未重复执行。原型 core、原像和静态 checkpoint 保留，不重置；后续按真实完整计划调整。

真实 Step2 调查记录：`night-handoff/story28-r44-plan-investigation-01.json`（任务根相对路径），SHA256 `584fdeb6a98d65a6303c28c7985e6bbdc7c5e1b9a22e1d7afaecf2a3911cd8ce`。未发现只能由用户决定的意图缺口；辅助协议、producer 分派、锁边界属于技术选择。当前只在隔离分支写代码，没有实际补偿、外发、删除或迁移。正式前置仍未验收，不能以规格准入替代运行资格。

规格保留同一完整用户目标；不因 token 建议拆掉 AC4。最终 token 数与已授予自主实施权限的 checkpoint 决策由 Root 单独记录。源码基线为直接由 Git 取得的完整 `db1f4409d538e56eabedd4d1bce5bff9e0f34a1c`；当前 dirty 内容是本次明确授权的作者草稿，旧未批准英文部分范围已完整留档，不当作用户排除。

## Design Notes

[ADR-0050](../../../docs/adr/ADR-0050-b-route-compensation-review-materials.md) 记录本轮持久化辅助审阅合同：新 materials/roles/presentation v1 与 compensation verdict/proof v2 绑定 full subject、真实 request/schema/output；所有历史语义原件完整自包含，host-only 支撑由原 owner 精确验证，语义双角色优先、未知角色失败关闭。同 policy v1 按原 request/runtime 精确重放；跨 policy 原件严格拒绝，不改签旧失败 TEMP 或冒称旧完整 raw 已在新 request 阅读。原 1 MiB／配置70k／默认96k／32MiB／codec 上限不变，材料及完整协议校验在 WRITER 外完成，短边界只比较同批校验所得 pins。

补偿不能只支持已 terminal 原操作。旧操作因 authority 漂移仍 pending 时，原 `_new_pending` 会阻断同 scope；这是必须显式处理的完整 AC4 场景。

新 v2 envelope 与独立 review 必须精确绑定 `compensates` 的旧 ID、frozen/raw 身份、原 effects、完整旧/当前/新 scope 和 current-before。仅在同一原业务锁族下核对这些已审阅关联，才能允许该新补偿与被关联旧 claim 接续；不能删除旧 marker、修改旧 index/journal、伪称原操作 published 或忽略任意 ID。其他 pending 仍阻断，新补偿自己的 pending 在真实完整发布前持续保护。

补偿真实 terminal、receipt/catalog/实际目标及相关来源链成立后，active inventory 只从该不可变正式证据派生旧 operation 的 `resolved_by(compID)`；read/recover 返回此精确关联诊断，不重新施加旧 effects。不能接受 caller 自报 resolution，也不能释放模型 unknown/预算。验证应基于一次读取的完整 operation/intent 图，以固定的本地事实及正式发布证据求关联，禁止 active-inventory -> terminal -> active-inventory 递归，拒绝自补偿、环、同旧 claim 的冲突关联和缺 proof。

测试必须包括 stale pending 的合法接续、未review/错 oldID/frozen/effects/scope/current-before/伪 terminal 的拒绝、其他 pending 不获免责、补偿发布前后原历史 raw 不变、重启后由正式证据派生 resolution。这些关系在 Step2 调查时尚未实现；当前已有作者实现，真实验证结果仍待 Root 执行。

## Spec Change Log

- 2026-11-08：Root 批准递归补偿 review 呈现的最小版本化产品修复；新增 ADR-0050 与上述 Implementation/Design 说明。冻结 Intent 和 AC1–5 原范围逐字保留；未重渲染工作流、未改旧证据，实际容量／最终新源码回归待 Root 独占执行。

## Review Triage Log

## Verification

作者仅 stdlib AST/JSON/SHA256。Root 执行 targeted recovery/compensation、原 commit/journal/scope/review/CLI/CI 回归及真实 Windows sharing/process；原 2.6/2.7 前置与新源码证据绑定必须真实成立。未实测的机器重启、掉电及任意外部编辑器隔离列为未覆盖，不称数据库隔离。


## R57 historical proof-v3 implementation checkpoint (not acceptance)

This outside-frozen-block note records the R57 source successor on recorded907bd4, without changing the original Intent, AC1–5, matrix, frozen approval, baseline_commit or older execution notes. The fifteen-file historical-v3 integration and its null default authority are source state, not a completed positive replay. See [ADR-0053](../../../docs/adr/ADR-0053-b-route-historical-v3-original-owner.md) and the Story2.8 owner document.

The added route authenticates explicit adoption proof.v3 through the exact real R56 original owner and distinct real R52 producer, then carries a versioned complete PUBLIC semantic history with separately authenticated private proof bytes. Original v2/profile-less and legacy thirteen-method paths remain. It does not re-sign old proof under current policy, reconstruct private proof from public digests, or rerun fresh-empty/current-target admission to validate historical bytes. Current compensation effects/authority/pending checks remain separate.

Root installation must supply exact source/schema/interpreter/producer authority before real historical-worker release; the checked-in null default is intentionally rejected. Genuine proof3/public-history/compensation positive execution, current compatibility tests, prerequisites and formal Step4/Step5 remain pending. No source integration, static peer review, mock/neutral predicate, H3 semantic verdict or test-source presence is a formal Story2.8 result.


## 当前收口与最小修复检查点（2026-11-11）

原 Story2.7 已在 e831cbc6 完成 Step4/Step5；R62 以此最新提交为基线。R57 已实际安装的原 R56 authority DATA 在 R62 本地复用，未重签旧 proof 或修改冻结 R56。prepare01 以明确 OS2 结束于 tokenizer 读取权限；原 reader 独立依赖预检 OS0 后，prepare02 在工具批准的执行上下文自然 OS2，进一步复现原合法完整 capsule adoption proof 引用与当前披露适配冲突。两次失败原件保留，均无项目模型调用，不是未知操作，不据此重复全量。

独立范围评判：Task/night-handoff/story28-capsule-alias-scope-Astra-20261111/assessment.md。最小修复仅识别真实 plan 顶层 adoption_proof_refs 的 proof-only 用途，拒绝同值其他用途，完整 native 及现有冷白名单不变。新定向检查与修复后的真实 prepare03 仍须各自取得实际结果；没有提前宣称 2.8 正式验收。旧失败/unknown 与 83/181/290/0 账本保留。

后续实际记录：3896a650 的五项 capsule 定向检查通过，prepare03 越过原 capsule 拒绝后明确 OS2，停于 SourceSet 缺少材料角色。诊断04 仍是已知失败的自然 OS2，仅收齐该帧所有 18 项，确认唯一缺角色项为现有完整 SourceSet；不把诊断当通过。独立范围评判见 Task/night-handoff/story28-source-set-role-scope-Astra-20261111/assessment.md。

当前 SourceSet 角色修复只连接真实 v3 owner 的语义身份、当前相关 receipt/preview authority 及完整当前 capture，使用既有 semantic 角色与 work 账，不以历史 before 替换当前版本。四个新增 DATA 方法已有独立通过证据：source-set-role-01 中三项通过；其一个预期路径误用未散列操作名，按原 owning location 修正后仅在 source-set-role-02 重测该项通过，原 batch 失败保留。证据位于 Task/logs/ci/2026-11-11。未重跑全量，真实准备05及其容量、后续审阅/补偿/恢复/read 和正式验收仍待实际执行。

真实 prepare05 仍自然 OS2：Root 初稿误将 receipt schema 写成未注册的 commit-receipt.v1，实际正式记录是 newrouge.b-route-commit.v1，安全门禁继续拒绝。现按实际注册身份修正，并在 DATA 夹具增加现有 registry 对照；先单独正例 source-set-role-03 通过，再仅复验其余三个受影响方法 source-set-role-04 通过。旧 DATA/prepare 结果不改写，真实准备06仍待执行。
## 2026-11-11 最小材料生命周期修复

基线 `6f5277ab570356ce0b49f64198d8ab210d6e1b73`。原 prepare06/07
已知 OS2 失败保留，原模型调用数与账本不变。干净 Astra max 范围评判允许
将完整 auth 冻结为既有 ordered+LF 原始 bytes，并把 body/frame 的预留分到
实际分配阶段；不增加新 registry、worker、指纹或全 codec/RSS 证明门槛。
原 snapshot、完整解码、validation、双 exact 及全部原资源限额保留。

`story28-r62-render-retention-tests-02` 的六项定向本地测试已自然 OS0 通过；
完整 wrapper/原现场 prepare、独立真实评审和恢复验收仍待完成，Story 仍未正式验收。

### 同一调用的重复语义验证（prepare08之后）

真实 prepare08 已进入 genuine encoder，随后在原100M账户耗尽；原失败与账本保留。
经同一干净 Astra max 续评，仅取消 warm render 对输入的重复 qualified validate。
JSON资源预检、原像、私有snapshot、真实E、完整D、restored语义验证及双exact仍在
任何prompt返回前执行；完整还原语义有效且与输入精确相同证明原输入，不新增缓存。
两项受影响正反检查实际OS0通过：
`logs/ci/2026-11-11/story28-r62-render-retention-tests-03/result.json`。
前七项适用证据保留，未重跑全套；下一真实prepare仍待执行，Story未正式验收。

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


### 2026-11-11：有界缓存的容量回退复用

原 prepare10 的 100M 工作预算耗尽与所有原失败保留。独立 Astra 评判批准最窄生命周期与原地转交修复：仍先检查完整 owner 加 8MiB body admission，仅临时 cache context 排除尚未生成的 body；cache 在 body 格式化之前关闭。仅本实例 capacity sentinel 完全退栈后，已完成的 exact counts/by_id 原地交给原 count pass，命中不重复渲染，未命中仍执行原 literal/hash/equality/收费和发布。没有新增 sidecache、扩容、复制 maps，或把后续 legacy rows 称为受 cache 上限证明。原文、canonical、完整 E/D、语义与双 exact 校验及 64MiB/8MiB/100M 原门保持；不声称峰值 RSS 恒等。

八项受影响本地测试通过，覆盖四版本完整 canonical、部分命中与孤立 counts entry、真实 work/MemoryError 不重试、生命周期及原 full roundtrip。实际 OS0/Job quiescence 证据：Task/logs/ci/2026-11-11/story28-r62-partial-cache-tests-01/{result,unit}.json。完整原 packet E 与真实 prepare/Story2.8 正式验收仍未通过，新增模型调用为 0。


### 2026-11-11：已完成 leaf 的广义后缀自动机

partial-key 修复的原完整 packet E-only probe 仍在原 100M 账户耗尽，after-share remaining=13,693,044，失败位于后续 leaf 的 SAM state 追加；原失败保留。独立 Astra 依据实际成本同意在原内部索引使用 generalized-SAM：每 leaf 从 root 开始，已有精确前缀 transition 复用；目标长度过长时保留完整 clone/redirect/link 处理；无 edge 仍用原 extend。只索引已完成 leaf 的 Unicode 子串并集，epoch、poison、原候选与完整 canonical 语义不变，不建立新 codec/API/哈希或提高限额。22 项受影响逐位置/穷举/完整 canonical/epoch/预算中断/clone 失败测试通过，实际 OS0，证据 Task/logs/ci/2026-11-11/story28-r62-generalized-substring-tests-01/{result,unit}.json。完整原 packet 的新 E 与正式 prepare 仍待实测。

100M 是 ADR0041/0050 继承的本地防耗尽工作政策，并非官方模型硬窗口；当前仍原样保留。


### 2026-11-11：精确结构键与无临时字符串表示

缓存仍使用原 owner 的 counts/by_id 两张表，结构键保留完整类型、顺序、signed-zero 与原 scalar 引用，哈希碰撞仍进行完整比较并预付实际工作及临时共存额度。新键只保存原数据和已精确 intern 的子键；不建立指纹准入或外部缓存。仅 exact-str 的长度改用原 repr 上界扣除实际引号数，不构造已经不使用的 repr buffer；非字符串 repr 路径不变。容量回退清空结构表示再走原 literal 分支，不混用两类键。每个真实 string-reference marker 由原 indices 表复用，逐出现计数和原输入 floors 不折扣。

Task v4 七项受影响检查通过，复用仍适用的 v2/v3 机制证据；完整保存 packet 的 share 建键已没有容量回退，但原 100M E 仍失败。原失败与阶段记录保留，算法安装不代表真实 prepare 或 Story 验收。

干净 Astra max 的另一份独立政策评判允许一次固定 300M／180 秒 DATA 校准。实际 E、D、纯语义验证、双 ordered/type-exact 与完整 frame 组件正常 OS0／Job 静止，包含原已耗 49,333,580 后总量 166,927,907，frame 313,176 bytes，耗时约 6.86 秒；证据为 Task/logs/ci/2026-11-11/story28-v4-work-calibration-01/{result,unit}.json。仅使用原现场保留量标量，没有伪造 Derived／private graph，故不等同于原 owner render、RSS 资格或 native prepare；最终 1MiB／70k 门仍须真实验证。当前算法检查点仍保留生产 100M；如采纳测得的 170M 候选，必须另行显式 supersede 已接受的资源合同并保存独立提交。

永久仓库的八项新分支回归已在实际 R62 codec 上通过，OS0／Job 静止，0 errors／0 failures；证据 Task/logs/ci/2026-11-11/story28-r62-structural-share-tests-01/{result,unit}.json。既有未变的资源／atomic 检查继续按适用范围复用，不重跑全套。

### 2026-11-11：显式固定工作政策

独立 Astra 复核了完整组件和原保留量／同账后缀，支持按实际166,927,907取下一档170M。依据新 ADR-0055，当前共享 codec 政策显式升级 resource-pipeline.v4，局部 supersede ADR0041／0050 的现行100M数值；旧历史、收费单位、64MiB／8MiB及全部原验证保持。此项是正式本地资源合同变更，不是声称原合同从未存在，也不改变模型次数／预算。源码与政策独立保存；受影响定向验证和原生 prepare 的结果另记，组件通过仍不等同 Story 验收。

170M 新源码的16项定向检查执行15通过／1失败，原结果保留在 Task/logs/ci/2026-11-11/story28-r62-policy-targeted-01。失败是测试的 mock side_effect 增加调用帧，导致实际回退观察未触发；只将该钩子改为直接替换，保留全部断言和产品代码。该项单独复验1通过／OS0／Job静止，证据 story28-r62-policy-singleton-02；未把原16项改成通过，也未重跑全量。新共享表示的既有测试只按实际操作同步，保留完整原像、类型顺序、同账拒绝、主异常和清理边界。

保存组件 frame 的预检恢复了现有 tokenizer 的原读取权限后，按默认96k门得到保守100,433 tokens；这还不是完整 runner request／schema，真实输入准入仍待原 owner，不能据组件通过宣称模型可调用。原失败、原预算与所有实际容量门保持。

### 2026-11-11：原生 prepare11 的真实终态与容量诊断

冻结 b24e1dfd 的原操作 NativeV15Origin03Compensation01 在原监督进程自然 OS2 返回。实际 genuine Derived／owner render 已完成，原同账户166,939,774／170M，frame313,388 bytes；证据 Task/logs/ci/2026-11-11/story28-r62-public-prepare-11/genuine-render-complete.json。随后真正完整runner请求在原容量门被拒：输入估算101,371＋输出预留2,000大于70,000，request316,309 bytes。原result／traceback／失败保留，零项目模型调用；没有获得prepare或Story通过结论。

修正了这一实际容量ValueError在qualified owner缺少边界翻译而被外层误包装为identity_unprovable的问题：现在保持invalid_argument及完整byte／token预算详情，正向artifact路径不变，不放宽容量。两个定向边界检查实际OS0／Job静止通过，证据 Task/logs/ci/2026-11-11/story28-r62-capacity-diagnostic-01。此修复不需要重跑完整旧链，仍不等同正式验收。后续补偿专用容量profile须先有适用官方运行时元数据并显式记录政策；Cap/MVG70k与共享默认不改，未据模型名推断服务端窗口。

### 2026-11-12 Cloud continuation22: genuine formal compensation published

The independent ADR0060 repair preserves the original exhausted2-slot plan/refusal/unknown and adds one explicitly authorized subscription review, cumulative3. Full original protocols and known source preimages are verified as DATA; the approved business body remains exact, while a fresh official high/normal-tier turn approved all seven governance checks. Genuine proof.v2 sealed and public prepare/reserve/apply/verify/publish/read all passed for NativeV15Origin03Compensation01. Plan revision2 and receipt revision1 are published; public formal_adoption=true, readiness/runtime/defaultB=false. The original operation is resolved, no active operation/pending marker remains, and original34 review records plus old receipt/operation bytes are unchanged. Catalog revision2 is an authorized publication result.

Evidence: `logs/ci/2026-11-12/cloud-epic2-recovery-22/REPORT.md`, final-state-audit.json and56 passing affected tests in final-targeted-04.txt. All prior failures remain; no retry/reset/full suite or fiscal action occurred. This actual Linux Cloud result does not complete original Windows/native AC5 or whole-Story/Epic acceptance. No further review is needed for the now-resolved compensation and its three logical slots are occupied.

### 2026-11-12 continuation24: four actual Windows controls

The existing Windows runtime workflow now has a bounded selector. At commit92c55325, run43211116759/attempt1 executed WindowsRecoveryTests plus WindowsCompensationTests:4 passed/no skips/287.578s/zero model calls, broad suite skipped. This establishes their actual Windows process-exit/restart, origins sharing refusal, pending deletion/cleanup and resolution behavior. Native/review upstream factories are synthetic; all cross-scope, reboot/power-loss, real provider-chain or whole-Story acceptance is not inferred. Original Story2.8 hasAC1–5; this is corresponding AC5 evidence and a partial2.10AC6 contribution. Current actual compensation stays published and its proof/source/budgets unchanged. Full result and artifact/local-transfer limits: logs/ci/2026-11-12/cloud-epic2-recovery-24/REPORT.md and windows-actual-summary.json.
