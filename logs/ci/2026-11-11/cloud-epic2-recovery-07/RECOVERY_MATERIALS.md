# Epic 2 一次性恢复资料清单

本清单覆盖 Story 2.8–2.10 与已批准的付费分段。P1 只阻塞其注明的原操作/付费路线；不阻塞源码修复和独立夹具检查。P2 为可选复用/调查资料，不升级为验收前置。不要再次索取已验证的 batch01/batch02。

根别名：`Task` 为原任务根；`T=Task/story27-r52-v15-empty-target-native01`；`N=Task/nx`；`R` 必须由真实 run/config 指定，不默认等于 T。以下路径均相对相应别名。

## 一次收件规则

一次性静态读取已列锚点，再按其真实 JSON typed refs、proof.files、capture.files/directories、snapshot.raw_files、config pin arrays、checkpoint/registry/journal pointers 递归到无新增相关引用。保留原 bytes、顺序、缺失与 raw SHA256；每条缺件同时记录它来自哪个原文件/字段。不要执行 driver、Root-only 脚本、模型或财政操作。若同一路径有不同历史版本，按各自原 digest 保留，不能覆盖成最新文件。不要扫描或打包整个 Task/用户目录。

现已确定：新补偿 NativeV15Origin03Compensation01 关联原 NativeV15Origin03；selected plan 是 PLAN-bed480ce3e404b2cbaf5514d80a7f941 revision1，binding_ref=null。这不表示当前相关 binding/Task 可省略，它们按真实 catalog/origins 仍须保留。

## A0 / available：2.8 failure/locator

根：`Repo`。状态：batch01 verified; batch02 request verified, source excerpt has declared provenance limits。敏感程度：already screened/public。

路径：

- `logs/ci/2026-11-11/story28-r62-public-prepare-11/{result.json,unit.json,traceback.txt,genuine-render-complete.json}`
- `logs/migration/2026-11-11/recovery-batch02/{driver-definitions.txt,MANIFEST.json}`
- `logs/ci/b-route-requests/native-v15-origin03-compensation-01/request.json`

用途：Byte-verified natural OS2/zero-call failure and retained static request/target definitions; do not request again.

适用条件：Required only for the named existing-operation route

## A1 / P1：2.8 compensation/current formal state; 2.10 published reading

根：`T`。状态：not supplied。敏感程度：high。

路径：

- `docs/planning/b-route/{catalog.v1.json,policy.v1.json,task-origins.v1.json}`
- `docs/planning/b-route/plans/PLAN-bed480ce3e404b2cbaf5514d80a7f941/1.json`

用途：Actual selected original meaning, current formal chain, later revisions and non-log authority.

适用条件：Required only for the named existing-operation route

闭包规则：Follow actual catalog heads, plan/binding/receipt refs, source/Requirement/Task refs and non-log receipt authority to fixed point. Preserve current bytes and recorded absences; do not substitute journal before images.

## A2 / P1：2.8 exact operation and pending inventory

根：`T`。状态：not supplied。敏感程度：high。

路径：

- `logs/ci/b-route-operations/pending.json`
- `logs/ci/b-route-operations/operations/98aa98a912402629817c45fc29be487f6e15f97460110c8527694fcf1a9c4659/operation.json`
- `logs/ci/b-route-operations/operations/<all operation IDs in actual inventory>/{operation.json,commit.json,commit.pending.json}`

用途：Complete index/operation pair and actual partial side effects; code validates this target inventory.

适用条件：Required only for the named existing-operation route

闭包规则：Include only existing sidecars; include the failed new compensation namespace only if it actually exists. Also follow actual legacy pending/apply-journal refs returned by current inventory, without executing recovery.

## A3 / P1：2.8 original-v3 cold authentication

根：`T`。状态：not supplied。敏感程度：high。

路径：

- `logs/ci/b-route-adoption-reviews/98aa98a912402629817c45fc29be487f6e15f97460110c8527694fcf1a9c4659/{review.json,subject.json,request.txt,execution.json,w/prompt.txt,w/schema.json,w/output.json}`
- `logs/ci/b-route-origin-captures/98aa98a912402629817c45fc29be487f6e15f97460110c8527694fcf1a9c4659/capsule.json`
- `logs/ci/b-route-retained-executions/98aa98a912402629817c45fc29be487f6e15f97460110c8527694fcf1a9c4659/binding.json`
- `logs/ci/2026-11-09/b-route-requests/native-v15-origin03-request-01/request.json`

用途：Original NativeV15Origin03 request, independent review and exact retained native evidence.

适用条件：Required only for the named existing-operation route

闭包规则：Original operation host_review_ref, proof.files and material.handoff_ref/protection_ref control exact paths. Include only referenced version-specific materials/roles/presentation/historical-auth when that proof family requires them. Execution JSON contains embedded stdout/protocol: no duplicate external files unless actually referenced.

## A4 / P1：2.8 historical protection and current Task preservation

根：`T`。状态：not supplied。敏感程度：high。

路径：

- `<original request material.protection_ref.path>`
- `<snapshot directory>/inventory.json`
- `<snapshot.raw_files[*].artifact where exists=true>`
- `<actual current task/master/back/gameplay files and Acceptance/history referenced by formal chain>`

用途：Full original raw archive versus real current target/Task state.

适用条件：Required only for the named existing-operation route

闭包规则：Follow snapshot/raw inventory refs to fixed point; preserve complete original bytes and explicit exists=false entries. Current target files must be collected independently of old archive bytes.

## B1 / P1：2.8 original fixed producer proof

根：`Task`。状态：not supplied。敏感程度：high。

路径：

- `logs/ci/2026-11-09/story27-r52-atomic-review-prepare-01/* (only 6 pinned members listed separately)`
- `logs/ci/2026-11-09/story27-r52-atomic-review-prepare-seal-01/config.json`
- `logs/ci/2026-11-09/b-route-requests/native-v15-origin02-request-02/request.json`
- `logs/ci/2026-11-09/story27-r52-atomic-review-prepare-supervision-01/<4 pinned JSON files>`
- `night-handoff/story27-r52-atomic-review-prepare-thin-controls-01/<3 pinned files>`
- `night-handoff/story27-r52-public-review-prepare-host-followup02/review_prepare_host.draft.py`

用途：Exact old producer inputs consumed by actual R56 execution03 owner.

适用条件：Required only for the named existing-operation route

闭包规则：All 15 exact PINS paths and their SHA256 are in historical-producer-fixed-inputs.json. Add original config referenced inputs/source/runtime lists and actually consumed dependency files. Do not execute any Root-only script.

## B2 / P1：2.8 native/source chain and real completed planning support

根：`N`。状态：not supplied。敏感程度：high。

路径：

- `logs/ci/mvg-planning/m4/{run.json,handoff.json,accepted-chain/admission-review.json}`
- `<handoff.original_prepared_ref>`
- `logs/ci/mvg-planning/m4/recovery/{m1,s1}/record.json`
- `logs/ci/mvg-recovery/registry.json`
- `docs/testing/story-2-5-controlled-acceptance/exclusive-resolution-v15.md`
- `docs/workflows/chapter3-source-set.json`

用途：Native capsule/run, source epochs, actual accepted checkpoint/receipt/admission and immutable prepared bytes.

适用条件：Required only for the named existing-operation route

闭包规则：Collect all paths from native_capture.files/directories, original prepared, run.json, m1/s1 recovery records and their predecessor archives; preserve source and dependency raw pins. No unfinished candidate is reused as completed.

## B3 / P1：2.8 original qualifications and source support

根：`Task`。状态：not supplied。敏感程度：high。

路径：

- `logs/ci/2026-11-07/story25-v18-qualification/verify-01/qualified.json`
- `logs/ci/2026-11-07/story25-r40-formal-closeout/formal-acceptance.json`
- `logs/ci/2026-11-08/story26-r47-native-step5-close/result.json`

用途：Finite qualified-origin raw pins; derived whitelist extracts are not these originals.

适用条件：Required only for the named existing-operation route

闭包规则：Only original-owner qualifications actually present in its QUALIFICATIONS and referenced closure. Two SOURCE_SUPPORT files under logs/ci/2026-11-06/b-route-sources/s25-v15-exclusive-offline/prepare-02/prepare/{source-manifest.json,source-blocks.json} must come from T/archive or exact retained original source root as the original proof says.

## B4 / P1：2.8 original historical owner

根：`Task`。状态：not supplied。敏感程度：high。

路径：

- `r62/scripts/python/qualified-historical-owner-authority.v2.json`

用途：Populated installed authority metadata (not account authentication) with source/schema/interpreter pins.

适用条件：Required only for the named existing-operation route

闭包规则：Compare r56 source/schema pins against already migrated source first; only missing/mismatched original files need transfer. R52 reader hash already matches public source; do not resend. Fixed R5/R10/R19/R22 Git commit/tree/production-blob/attributes closure is needed only when their original reader actually runs; exact IDs are listed in the report. No whole .git config or full raw log history.

## C1 / P1：2.9 actual completed-unit reuse and epoch/reopen

根：`R`。状态：not supplied。敏感程度：high。

路径：

- `logs/ci/{mvg-planning,capability-planning}/<actually selected original run>/run.json`
- `logs/ci/mvg-recovery/registry.json`
- `<registry entry.state_path>`
- `<selected checkpoint/receipt/admission/execution refs>`
- `<actual run>/analysis-input/<complete immutable prepared inputs>`
- `<actual run>/{completed-recovery,adoptions,reopen-history}/<referenced members>`
- `logs/ci/mvg-recovery/clears/epoch-<referenced epoch>.json`

用途：Original committed completed item, full single-item normalized input, current relevant dependencies and original epoch/revocation/cost history.

适用条件：Required only for the named existing-operation route

闭包规则：Start from real native run/registry pointers; take checkpoint objects, run-state snapshots, proof/request/schema/output/embedded protocol and actual generation archives to fixed point. SC_MVG_RECOVERY_ROOT or run.recovery.store, if configured, identifies the real store. Do not silently take default empty registry. New legitimate acceptance does not require reusing an old local test fixture.

## C2 / P2：Reuse prior local checks / settle the old R60 test outcome

根：`Task`。状态：not supplied。敏感程度：medium to high。

路径：

- `logs/ci/2026-11-11/story29-r63-retained-gen2-01/{result.json,unit.json}`
- `logs/ci/2026-11-11/story29-r65-retained-tail-01/{result.json,unit.json}`
- `logs/ci/2026-11-11/story210-r64-entrypoint-focused-01/{result.json,unit.json}`
- `<actual original R60 Root-02 started/control ref and any existing terminal/held exit receipt>`

用途：Reuse covered local checks; avoid blindly repeating an unknown old run.

适用条件：Optional for new independent source/fixture checks. Needed only to close/reuse that old run; absence keeps its outcome and liabilities unknown.

闭包规则：Original R60 Root-02 record basename is not identified by available files; do not invent it or equate it with the separate fiscal HOME Root-02. Follow existing start/control record, not a newly run replacement.

## D1 / P1：Paid segmented financial owner and outside occupancy

根：`Task`。状态：named Root-02 directory/config/ledger reported absent; actual canonical owner location still unresolved。敏感程度：high。

路径：

- `story29-unit-profile-allocation-Root-02/config.json`
- `<actual canonical config Root_authority.path>`
- `<actual canonical config budget_snapshot.path>`
- `<canonical namespace>/ledger/{000001.json,<all existing contiguous events>,STOP.json}`
- `<canonical namespace>/prefix-init.json (if existing)`
- `<original budget owner _closed_chain/_host3_graph/_budget referenced existing namespaces>`

用途：Actual paid/unknown/overlapping guard graph and campaign liabilities; preserve released0.

适用条件：Root-02/config 已明确缺失，仅记录，不重复索取。一次收集真实现存 canonical owner/config 及其引用的占用图；仅新付费动作依赖该闭包。

闭包规则：Read original owner static source and actual config/ref graph in the same collection pass. If the named root is absent, report absence and every existing reference to it plus the real owner graph location; do not make a replacement config/ledger. Copy no active lock/lease as permission.

## D2 / P1：Paid segmented owner source/control prerequisites

根：`Task`。状态：not supplied。敏感程度：high。

路径：

- `night-handoff/story29-unit-profile-funding-issuer-followup06/Root_unit_profile_issuer.draft.py`
- `story29-host2-controller-draft-01/host2_controller.py`
- `night-handoff/story23-segmented-financial-prefix-store-followup03-draft/segmented_financial_prefix_store.py`
- `night-handoff/story23-segmented-financial-prefix-validator-draft-01/segmented_financial_prefix.py`
- `<actual canonical config source_files/input_files/runtime_files refs>`

用途：Original linked financial implementation/actual role closure; current candidate alone is not live authority.

适用条件：Required only for the named existing-operation route

闭包规则：Compare any same-named migrated archive using original SHA256 before reuse. Obtain only missing or different original revisions referenced by real config; no arbitrary current-code overwrite, carrier/seal/registry prerequisite or original script execution.

## D3 / P1：Paid segmented native birth/prefix/journal

根：`R`。状态：not supplied。敏感程度：high。

路径：

- `logs/ci/{mvg-planning,capability-planning}/<actual segmented run>/run.json`
- `<actual run>/b/{plan.json,initial-run.json}; <actual born_ref.path>`
- `<actual run>/q/n<ordinal>/{claim.json,complete-claim.json,result.json,<exact archived request inputs/output/schema/execution>}`
- `logs/ci/mvg-recovery/registry.json`
- `logs/ci/mvg-recovery/activity/segmented-journals/<actual referenced journal>.json`
- `<existing STOP/unknown/held terminal receipt for actual reservation>`

用途：Cross-check original fiscal intent with native debit/claim/born/paid outcome and exact complete requests.

适用条件：Required only for the named existing-operation route

闭包规则：Read actual immutable plan, native and registry pointers, all extant unsettled claims and exact journal before/after targets. Collect request input_archive_ref and actual result/protocol dependencies, not arbitrary whole run caches. Before birth, legitimately absent native files remain absent.

## D4 / P2：Reuse already completed metadata09 checks

根：`Task`。状态：not supplied。敏感程度：medium to high。

路径：

- `logs/ci/2026-11-11/story23-r59-metadata-role-09/result.json`
- `night-handoff/story23-metadata-role09-20261111/out/worker/result.json`
- `<their actual referenced source/dependency manifest and held terminal receipts>`
- `logs/ci/2026-11-09/story27-r56-zero03-review-prepare-seal-02/config.json`

用途：Retain metadata09 success within original scope; never call it paid qualification.

适用条件：Optional unless the actual paid host/config explicitly references it. Do not rerun metadata09 or demand all 66 child outputs/486 files for unrelated Story2.8/2.9 work.

## E0 / P1：新真实3B规划与2.10全链的来源/独立审计输入

根为实际 `R`。需要原完整 planning contract、`contract.audit_ref`、`prepared_ref`/`handoff.original_prepared_ref`，及其实际 prepare 目录的 `inputs.json`、`raw-index.json`、`output-schema.json` 和冻结 batch templates；收齐审计 report/bundle/extraction/comparison/step execution 指向的原文件与完整累计业务来源、constraints、contexts。

实际 `_b_route_planning_input.assemble` 要求 `evidence_class=real_model`、完整独立审计、planning_eligible=true、无 semantic blockers。这是已有 owner 合同，不是新门。先复用现有适用真实 proof 与相同公有来源；历史2.2的 actual_model_semantics_verified=false 记录保持原覆盖限制，不能改判为真实语义通过。如果原来根本不存在真实 audit，应一次报告“无现存适用原件”，不造证据，也不把可选调试资料当额外前置。该组仅用于新真实规划/完整验收，不阻塞已有正式 published read 或本地源码/CLI/夹具检查。

## E1 / P2：Capacity investigation shortcuts

根：`Task`。状态：not supplied。敏感程度：medium to high。

路径：

- `<existing saved complete final request/frame/packet, if ever persisted>`
- `<existing official capacity-only metadata receipt with CLI version/effective model/provider/context window/cache timestamp>`

用途：Avoid recomputing full old render and assess an explicit compensation-only policy.

适用条件：Only existing data. A saved full frame is not required if it never existed; original source excerpt is sufficient for target/request location. Current cloud applicability and authorized policy remain separate.

## B1 的全部15个固定 producer 路径

以下来自已迁移 R56 原 owner 的 AST 常量解析，未导入或执行原模块。每个对应 raw SHA256 见同目录 `historical-producer-fixed-inputs.json`。这些资料仅用于原 v3 历史重放，不是公共 published read 的通用要求。

- `Task/logs/ci/2026-11-09/story27-r52-atomic-review-prepare-seal-01/config.json`
- `Task/logs/ci/2026-11-09/story27-r52-atomic-review-prepare-01/reader-stdout.bin`
- `Task/logs/ci/2026-11-09/story27-r52-atomic-review-prepare-01/reader-stderr.bin`
- `Task/logs/ci/2026-11-09/story27-r52-atomic-review-prepare-01/actual-native-capture.json`
- `Task/logs/ci/2026-11-09/story27-r52-atomic-review-prepare-01/reader-held-started.json`
- `Task/logs/ci/2026-11-09/story27-r52-atomic-review-prepare-01/reader-held-terminal.json`
- `Task/logs/ci/2026-11-09/story27-r52-atomic-review-prepare-01/stop.json`
- `Task/logs/ci/2026-11-09/story27-r52-atomic-review-prepare-supervision-01/result.json`
- `Task/night-handoff/story27-r52-public-review-prepare-host-followup02/review_prepare_host.draft.py`
- `Task/night-handoff/story27-r52-atomic-review-prepare-thin-controls-01/manifest.json`
- `Task/night-handoff/story27-r52-atomic-review-prepare-thin-controls-01/run_review_prepare.Root-only.py`
- `Task/night-handoff/story27-r52-atomic-review-prepare-thin-controls-01/control_common.py`
- `Task/logs/ci/2026-11-09/story27-r52-atomic-review-prepare-supervision-01/supervisor-started.json`
- `Task/logs/ci/2026-11-09/story27-r52-atomic-review-prepare-supervision-01/child-started.json`
- `Task/logs/ci/2026-11-09/story27-r52-atomic-review-prepare-supervision-01/child-terminal.json`

另外：旧02原请求为 `Task/logs/ci/2026-11-09/b-route-requests/native-v15-origin02-request-02/request.json`；原03请求为 `T/logs/ci/2026-11-09/b-route-requests/native-v15-origin03-request-01/request.json`。后者与已取得的新补偿请求是不同原件；新补偿的 compensates.request_raw_digest 也不是新请求自身的 SHA256。

## B4 原 Git 对象：只取 verifier 真正检查的生产闭包

- R5：`988022094381c2b190b30c7702ed77aadda3805a`
- R10：`dc245b3b3d14abd512879369b30692536dfac4fd`
- R19：`1d126b85b908ba1eea4b27ceeb8a9669a771e6f3`
- R22：`6d4ab1c3cba67bebe98f75c9462af613bf9d739a`

仅在实际 original native reader 路线需要时收其 commit/tree、生产 blob、.gitattributes 和生产工作树原 bytes；r7/r8/r9 仅在实际祖先 frame 引用时补相应对象。不要打包整个 .git、远端认证配置或无关历史日志；原 commit 不能用公开 snapshot commit 冒充。R52 reader 所需 raw hash 已在现有迁移分支逐字匹配，不需重传；r56 其他源码/schema 先按 authority pins 比对，只有缺失/不同版本才收。

## 不属于“传文件即可解决”的环境事项

- 原 Win32 Job/process/文件身份和 Story2.10 AC6 需要受支持 Windows 执行；复制绝对路径、活动 lock、lease 或 PID 不能恢复原权限。
- 未来模型调用使用云端正式认证。此前本地 CLI 显示登录但服务端 metadata 返回401；不索取旧密码/令牌/密钥。新认证不能替代旧 proof 或账本。
- 70k 容量政策变更需适用的官方当前运行时依据与明确政策。原日志只证明101371+2000>70000，不能证明大窗口可用。
- 官方编码下载403保持原限制；不索取/转运 tokenizer cache 来绕过它。

## 一次反馈与发布边界

交接方一次反馈：已找到并收齐的精确路径/大小/摘要、逐项 missing（含原引用字段）、P1/P2 场景、真实 owner/run 根。若固定 Root-02 目录不存在，说明已有引用和真实财政 owner 所在处；不得创建新目录/账本来代替。原 R60 测试 Root-02 与财政 namespace 的 Root-02 不能仅凭名字合并。

模型完整输入输出、原保护归档、Task 和账本通常为高敏业务资料：只采用用户授权、筛查后的非 main 交接。未筛查内容不自动公开。这里不请求或读取任何密码、token、key、auth 文件、session、cookie 或私钥。

源码/CLI修复、真实空目标拒绝检查、隔离恢复夹具均继续独立推进。原操作恢复、旧run重用、付费分段各自只等待其 P1 条目；P2 缺失不阻止其他工作。

原83 paid-or-unknown／181重叠guard／cap290／released0只作历史报告；不相加为独立支出，不冒称当前账本已经复核。
