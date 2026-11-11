# Story 2.8：公共恢复与受审阅补偿

## 版本化补偿审阅材料

递归补偿继续保存完整 v2 host subject 和全部 `current_files` 原像。依据 [ADR-0050](../adr/ADR-0050-b-route-compensation-review-materials.md)，模型读取一次自包含的完整历史语义 DAG；旧 prompt/request、execution/protocol 等由真实原 owner 精确重放，逐文件角色清单绑定原路径、raw digest、长度与 owner 来源。双角色的语义读取优先，未知或缺失 owner 失败关闭。新 materials/roles/presentation v1 与 verdict/proof v2 明确绑定 full subject 和真实 runner 请求，不把旧 raw 支撑冒称为本次模型已读原文。

同 policy 的 v1 原证明仍使用原完整 request/schema/runtime 合同；跨 policy 原件严格拒绝。旧失败 TEMP 及回执仅供诊断，不能改签或复用于新冻结源码。呈现固定为 `newrouge.b-route-compensation-review-delivery.v1`，直接使用既有 compact-v3 完整 packet，不套 legacy mvg-lossless envelope，不设失败 fallback。新 helper reader 保留原规范重编码／digest／展开门禁；编码、完整解码和有序／类型精确的 roundtrip 共用一个原100M work account。材料编解码和完整 proof 重放在 WRITER 外，proof raw pins 来自已验证的同批 buffers。真实完整 wrapper 的 1 MiB、配置 70k／默认 96k token、32 MiB transcript 与 codec 资源限额不变；容量失败不 dispatch、不重试、不缩减原 pending 场景的语义分母。首代旧呈现已因双 factor 实际失败，原 packet 未持久化，容量不能推定通过；此轮修复新源码的实际容量与正反回归由 Root 独占执行，原源码通过结果不等于本轮通过。

Root后续实际固定capture诊断证明v3完整frame为128170 bytes／保守51465 tokens；plain/v2分别124096／83217 tokens而超70k，不能改选它们。独立cold decode为72272548 work不代表原warm成功。本轮warm呈现改用真实原子 `produce_canonical_roundtrip`：内部私有稳定JSON snapshot、原dumps、完整primitive解码和精确原像等价证明都在同一原100M账内，拒绝输入变化／半输出／类型顺序差异，没有外部witness或skip开关。冷loads/read_prompt仍完整规范重编码，模型header／v3正文、完整packet、proof及所有阈值不改。首代及完整原pending-successor新源实际验证仍待Root，不能拼接两个账户声称通过。

R44 已实现公共恢复与显式 v2 补偿 producer，原 Story 2.8 AC1–5 范围保持。作者只完成源码、测试与 stdlib 静态检查；实际回归、Windows 子进程及前置资格由 Root 冻结源码后执行。原 2.6/2.7 正式前置仍未据此验收，不宣称 readiness、runtime、默认 B 或正式启用。

## 公共入口与恢复

`dev_cli.py b-route-adoption` 与直接 `b_route_adoption.py` 使用相同 owner。`--stage recover-inspect --operation-id <old-id>` 读取原 operation、intent、精确 before/after、receipt/catalog 以及旧 Capability/MVG journal route；返回物理状态与下一原步骤。该事实检查不创建锁元数据、不调模型、不授 admission。`--stage recover` 仅将缺失步骤送回唯一 commit owner 的 apply/verify/publish；已是 after 的目标不重写，真实终态为 no-op。未知编辑、损坏或相关来源/规则漂移保留现场并返回 expected/actual/resume 诊断。

已发布而 pending 未清时，通过保存的 publication 镜像及当前正式链证明原发布，仅清理本操作 marker。无关合法 publication 不被覆盖。旧 Capability/MVG pending 只返回其原 owner/run/journal，必须回到原 apply 的确认、checkpoint、accounting 与 marker 清理合同；未知 scope、null、损坏和 orphan 不获新入口豁免。

## 补偿请求与独立审阅

补偿沿用 review-prepare、review-complete、prepare、reserve 和同一 apply/verify/publish/recover 阶段，通过请求版本明确分派。请求使用 `newrouge.b-route-compensation-request.v2`、`producer: compensation`、新 `operation_id`，以及以下完整字段：

- `compensates`：原 `operation_id`、`frozen_digest`、`request_raw_digest`、原 frozen targets 的 `effects_digest`。
- `selection`：实际正式链中已发布的同 plan `plan_ref`，以及有绑定时不可省略的同 plan `binding_ref`；均为既有完整 typed reference。
- `reason`：非空补偿原因；review-prepare 时不带循环自引用，prepare 时附 owner 生成的 `host_review_ref`。

辅助 envelope 使用 `newrouge.b-route-compensation-operation.v2`，与旧 adoption v1 共用 operation 目录及完整 pending index。六正式 schema、原 v1 原像及已有索引行语义保持。新 producer 不制造 native candidate、native proof 或 approved 布尔；它只能选择既有正式语义并生成新的不可变 plan/binding 修订。需要新规划语义、未发布语义、额外 Task 承接或丢失当前映射时，应回原 adoption 入口。

独立 host review 绑定原 operation/raw request/frozen/effects、原不可变审阅身份、当前正式前像、累计义务、完整旧/当前/新 scope、Task join、来源与新请求。补偿始终需要独立 semantic execution 证据，无 mechanical/approved 捷径；owner 只生成 runner 描述并验证已完成证据，不自行 dispatch。审阅线程必须独立于原 native 与 host review 线程。现有模型请求预算、unknown、epoch/reopen 均不重置。

当前正式内容中的后编辑保留；选择不同字段只有当前字段仍等于原 effects 时才可继续，并拒绝丢失累计 Requirement、定义身份或证据。有 Task 时产生新 binding 与递增 origins；保留完整现有 Task 映射、来源及 frozen legacy refs，不写 Task 状态、定义、Acceptance 或历史。正式 receipt 使用既有 Task projection 校验允许随后合法状态进展。继承语义的真实 source/proof bytes 必须存在并匹配原正式引用；缺失原本地证据会阻断补偿，不虚构证明。

## 精确 pending 接续与 resolution

原 claim 因 authority 漂移仍 pending 时，新补偿只可在原业务锁族下，凭精确且独立审阅的关联接续该一条旧 claim。其他 pending 继续阻断。原 operation、request、marker、index 行及 journal 不改，不伪称旧操作 published。

完整 operation/intent 图由同一次 inventory 构建；terminal 验证不调用 active inventory。拒绝自补偿、环、同旧 claim 的冲突 successor 及缺少正式 proof。只有新补偿完成、marker 清理且实际 receipt/catalog/目标与相关正式来源链成立后，active inventory 才从这些证据派生 `resolved_by(newID)`。旧 ID 的 read/recover 返回这一精确关联，`published` 与 `formal_adoption` 均为 false，不重放旧 effects。补偿自身完成前仍保护其完整 scope。

## 锁与故障边界

长协议、来源与全量 bundle 检查只持原业务 scope 锁，不持全局 metadata/WRITER。短原子替换、索引持久化、catalog 发布与 marker 清理重取原 metadata/WRITER，并比较此前捕获的相关字节。无关 catalog 若在短边界改变，会报 stale，离开全局边界后由下一次调用重算。旧 writer 继续使用同一锁目录及既有顺序，没有第二套 mutex。receipt 不 hash 自身或最终 catalog，catalog 最后发布。

维护 gate 完整选择 `test_b_route_commit_recovery` 和 `test_b_route_compensation` 各一次，保留 funding、OS worker 及原 selectors。测试源码覆盖故障点重启、未知后编辑、旧路由、Task done/Acceptance/history/B 来源、错误旧身份/审阅/scope/current-before、伪 terminal、冲突 claim、实际无关正式 publication 进展，以及 Windows origins/marker sharing refusal 和子进程退出/接续。它们使用明确的合成 native/审阅协议，不授真实 native qualification；执行结果以 Root 的冻结源码报告为准。

机器重启、掉电与任意不合作外部编辑器的隔离尚未实测；不称数据库隔离。本文不授模型费用、主分支合并、外部发布、默认 B 或阶段启用权限。

## Current explicit delivery.v2 / compact-v4 implementation

The new compensation renderer now explicitly selects `newrouge.b-route-compensation-review-delivery.v2` with `newrouge.b-route-compact-literal.v4`; the earlier fixed-v1/v3 notes above describe the preserved historical delivery. ADR-0050 records the new canonical version: only exact residual literal prefixes/duplicate complete leaves gain visible P/C reuse, with every original semantic/audit byte retained and all work charged to the same original100M account. v1/v2/v3 compact canonical behavior stays unchanged. The reader keeps exact delivery.v1/v3 and new delivery.v2/v4 routes, rejecting mixed markers, decoder instructions and bodies without fallback. Semantic packet/material/role/presentation versions and proof bindings are unchanged. Legacy text readability grants no cross-policy proof replay or re-signing; original policy gates remain strict.

The original archived793036-byte packet previously completed atomic work but failed the actual complete-frame70000-token gate at94538; cold did not execute. Root close `2a7e428555b4b7ac8c0459c136b202eccf2d11046c72f6fd9f14b7341443ecaf` is retained. New implementation/tests are author-static only until Root executes them on fresh sources. Original1MiB/70000/default96000/codec limits, Task/status/Acceptance/history/B-source and full-scope obligations remain. This note does not claim fixed-packet fit, pending-successor success, Story2.6/2.7 prerequisites or Story2.8/native acceptance.


## Candidate delivery.v3 / transport.v1 owner view

The candidate material renderer uses an explicit delivery.v3 transport.v1 envelope with the unchanged compact-v4 codec. It retains the complete Packet1 core, replacing at most one largest exact owner-bound original-operation document text with a fixed placeholder. The complete operation object remains visibly present in its semantic frame; the header specifies exact insertion-ordered JSON indent2/ensure_asciiFalse/allow_nanFalse plus LF restoration. Role/provenance, document/raw identities and full-byte equality determine eligibility. All other document text and original fields remain literal. Cold reading independently rederives the unique fixed internal view plan, verifies the restored raw bytes and complete ordered Packet1 digest, and retains the original compact full D+canonicalE. Warm owner production uses a genuine private same-call snapshot, original producer/full decoder, complete envelope and Packet1 exact comparisons, and current-input equality on one account. ADR-0050 specifies the closed fields, deterministic choice and actual-graph allocation preflights.

This is an explicit transport-version change; compact-v1/v2/v3/v4 code and semantic Packet1/material/role/presentation/verdict/proof versions are unchanged. Previous delivery.v1/v3 and delivery.v2/v4 texts remain real reader paths, with mixed versions rejected. Reader compatibility does not authorize cross-policy proof replay or re-signing. All original 100M/64MiB/8MiB/1MiB/70000/default96000 limits, full semantic/audit denominator and current authority gates remain.

The previous v4 eleven targeted methods passed, but its archived full-frame diagnostic remained 73962>70000 tokens; cold did not execute. Root close `bf24d6a0ac1498cbee19c542a1ee612b2060705e6a86e75d72dbff9443365670` is retained as failure. This candidate has only static author checks, with fourteen new transport methods drafted for Root. It is not yet integrated or executed, and establishes no fixed-packet fit, pending-successor success, native readiness or Story acceptance.


## R57 source-integrated historical adoption-v3 route (not qualified)

The R57 successor on recorded base907bd4 adds explicit original proof.v3 history and public-history/qualified-compensation v2 routing; [ADR-0053](../adr/ADR-0053-b-route-historical-v3-original-owner.md) describes the producer/consumer and disclosure boundaries. The earlier delivery-v3 candidate notes above retain their original historical status and concern a different version family. Fresh `review_profile` adoption preparation is rejected in this historical consumer; only the real R56 producer owns that preparation.

Known profile-less proof.v2 uses its original route; explicit `expanded-semantics.v3` proof.v3 uses the real retained R56 owner and separate real R52 original producer in an owned, source-pinned read-only worker. Historical proof/private supports/runtime/archive/binding2 are reverified, without re-running fresh-empty target predicates, `_binding_value03` or a native/model producer. The current compensation owner still checks current-before authority/effects/scopes and pending/journal state. Only the actual worker completion may mint history; caller dictionaries or an approved flag cannot.

The default adjacent authority.v2 has null install inputs and fails before worker release. At this checkpoint genuine proof3 verification, complete positive public history and actual compensation success remain unexecuted. Original thirteen-method regressions are retained as their own scope, without a new-epoch PASS claim. Root must report actual mechanisms, genuine positive evidence, applicable Windows checks, Story2.6/2.7 prerequisites and original Step4/5 separately. No formal adoption/readiness/runtime/defaultB or fiscal release is asserted by this source installation.
