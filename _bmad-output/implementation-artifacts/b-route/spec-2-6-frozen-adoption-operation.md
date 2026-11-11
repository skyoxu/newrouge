---
title: 'Story 2.6: frozen adoption operation and stable identities'
type: 'feature'
created: '2026-11-06'
status: 'done'
baseline_commit: 'f216480fcf181f228aab8ddaaca9bbfe401d6023'
route: 'dispatch'
review_loop_iteration: 0
---

## 原 R11 离线实施交接（历史范围说明）

The user authorized independent offline integration into R11 while the root
continues the single actual Story 2.5 execution. This in-progress status denotes
implementation only. Formal Story 2.6 qualification remains blocked on current
Story 2.5/1.5/1.6 prerequisites and Story 2.5 Step 4/5. No accepted or published
result, default B activation or Task/runtime readiness is established.

Implement only the public review-prepare/review-complete and operation
prepare/reserve/inspect owners already reviewed in frozen i6
504159ee19e1efd9d6a3362d5925d14b406dc4af. Preserve the complete original request,
stable independent allocation/revision counters, current protection/Task/catalog
and scope guards, strict independent semantic review, and fail-closed storage.
No formal target apply/publish, Story 2.7 classifier, unknown retry, budget
refund, model executor, or new lock manager belongs to this work.

## Native proof integration

Continued run.v2 eligibility is consumed through the isolated frozen R10 reader,
at production dc245b3b3d14abd512879369b30692536dfac4fd, under the original
activity and coordinator locks. Preserve the full source-epoch chain, paid
failed reservation, partial/p1 paths, high runtime configuration, and original
handoff/prepared bytes. Never substitute current R11 planning-input reassembly
for the original R5/R10 validation. Reader support identities participate in the
host subject, policy and persistence-boundary freshness checks.

The existing run.v1 path retains its original owner validation. Unknown schema,
source root, currentness drift, incomplete native qualification or missing
independent review fails closed. Prepared/reserved is not publication.

## Tasks & Acceptance

- [x] AC1: complete request/authority/target before-after closure and stable durable
  typed allocations, without new Task identity.
- [x] AC2: original-byte replay, changed-request conflict, explicit reviewed lineage.
- [x] AC3: existing metadata then ordered scope leases; committed/pending collision
  checks and legacy apply/rebind wrappers share the same owner.
- [x] AC4: native, protection, review, source and target rechecks before persistence;
  damaged or unknown evidence is retained and rejected.
- [x] AC5: common codec diagnostics and read-only inspect with explicit resume_ref;
  all formal_adoption/readiness/runtime_verified flags remain false.

Reuse retained i6 bounded offline evidence (scope 14 methods, host-review 37,
final real-store two-process composition and explicit public replan). Run only
the five affected gate methods and new reader/capture interoperation fixtures.
No actual Nx reader, model/API, prepare/reserve/apply/status/generate or shared
resource test is authorized by this offline specification.

Implementation and test evidence will be recorded under logs/ci. Review and
formal acceptance are pending; no commit is authorized before root review.


## 当前统一整合基线 R41（尚未正式验收）

以已完成原生审核的 Story2.5 本地提交 `f216480fcf181f228aab8ddaaca9bbfe401d6023` 为基线，按冻结46文件清单移植 R39 最终2.6与引用角色修复。保留 B40 的 candidate/runtime/common/appserver/CI，不以旧分支覆盖共享实现；ADR索引保留原条目并增加0049。原R39组件27项及其他历史回归只按原源码纪元引用，不能算作R41通过。

Task108历史调试附件缺失保留引用、null摘要和明确告警，不单独阻塞无关操作；当前实际必需输入仍失败关闭，原Task三图不改。R41还需实际整合验证、新保护采集/验证、新声明/subject/host proof，再依次执行公开准备和预留。原R22/R10 producer、13次MVG调用、79/290及unknown全部保持；新增真实项目模型调用0。正式采纳、发布、readiness、运行及默认B未开启，未推送或合并main，未启用Fast或1.5倍速。

## 当前 R41 验证对账（2026-11-08）

上方 R11 离线交接及 R41 整合基线段保留的是当时的范围和待办，不新增当前操作门禁。后续用户已授权实际公开流程及必要回归；本次按原 AC 完成验证，进入原生 Step 4 审核，尚未建立 Story 2.6 正式验收。

- 执行时代码提交为 `6a85c836ae0e7899ddfe5477a904abd817e6d627`，冻结来源为 771 文件／15 目录；下述结果关闭前来源一致。当前文档的状态、勾选与验证记录属于执行后的文档收口，不改生产代码、测试或已冻结请求。
- 同一 `s26-r41-new-plan-02` 的 review-prepare、review-complete、prepare、预留前 inspect、reserve、预留后 inspect 均真实返回 OS 0；保留原请求、固定分配、原 review proof 及全部旧失败／unknown。inspect 不执行 native reader，也不授予运行资格。
- 当前来源的 12 个既有定向方法全部通过：独立 typed revision／既有 Task 身份、同 ID 冲突、完整 lineage、持久化后跨 operation 冲突、command/state owner 冲突、持久化边界复核、proof／target 漂移与 CLI 诊断／非授权输出。零跳过、隔离违规、测试子进程和模型调用。此前同来源的 namespace 8 项、实际 Windows 回执及 inventory/protection 原组件证据保留各自来源限度，不相加成一轮全量通过。
- 可核查的原件索引由本次 `logs/ci/2026-11-08/story26-r41-formal-review/evidence-index.json` 给出；原 Task 108 summary 仍缺失，没有重建原件、推断历史通过、删除引用或改 Task 状态。
- 本次只完成操作冻结／预留的功能验证。正式采纳、目标 apply／publish、frozen-A、readiness、runtime_verified 和默认 B 均未开启；实际服务端模型身份与物理请求总数未知。79/290 及旧 unknown 占用不变，没有新增项目模型调用，也未启用 Fast 或 1.5 倍速。正式结论待 Step 4／5。

## Review Triage Log

| Finding | Verdict | Route | Evidence |
| --- | --- | --- | --- |
| B1 | medium | patch | reader subprocess.run 的 TimeoutExpired 不属于 public/CLI 捕获类别；已追稳定来源路径，无更早转换。 |
| B2 | medium | patch | 只终止直接 reader，真实 R22 transaction-close 会启动 R5 verifier；其父级 watchdog 随 reader 终止，存在子 verifier 继续读的可达调度。未声称实际 orphan。 |
| B3 | medium | patch | _emit 在异常输出及成功输出路径均用 ensure_ascii=False；重定向 cp1252 无法编码合法 Unicode，输出处不在可重试异常转换内。 |
| B4 | medium | patch | policy_identity 未直接绑定 sources/protection 实现；inventory 已有支持规则的间接拒绝，但不能覆盖其余 owner 语义变化。补齐实际依赖而非更改历史证明。 |
| B5 | medium | patch | SourceOnly 只处理 Python loaders，_Audit.check 没有 import 路径记录；可观察的 extension import 未进入其宣称 observed closure。仅补 observable import bytes，不能扩称 OS/DLL 完整性。 |
| B6 | medium | patch | reader 已给出有界 native rejection 原因，public 的普通异常转换只保留 ValueError 类名，丢失可操作的来源/校验原因。须保留有界元数据，不输出 request/bootstrap 或任意全文。 |
| B7 | false | reject | codec 的 resume_ref 本来可为 null，AR-26 明确显式 null 不授权；AC5 的已冻结操作 inspect 已返回实际 resume_ref。没有合同要求在尚未创建操作的每个异常中虚构恢复文件。现有非空原诊断位置必须继续保留。 |
| B8 | medium | patch | 新 Graph schema 只提供结构，plan_relation_checks 未验证节点/边本地关系或委托 native graph owner；独立 formal validation 可漏掉坏端点/重复节点/必要边界关系，需复用已有语义。 |
| B9 | maybe-false | defer | 未验证 medium：检查后原锁打开之间确有路径采样间隔，但 helper 明确要求目录稳定，受支持 managed owners 未证明会在该窗口替换命名空间。需在 Windows 原调用链中证明受支持替换及实际 acquired handle 偏离，不能据泛化 TOCTOU 直接新增原子目录保证。 |
| B10 | low | patch | OperationScopeTests 明确把 sq-* 写在 repository，实际未跟踪 byte-lock 原件已存在。未来 fixture 应使用隔离 owned temp；依用户保留现场指令，不删除已有 sq 原件，也不把它提交为产品。 |
| E1 | medium | patch | target schema/shape 未在 format_map 前拒绝索引/属性格式；IndexError/AttributeError 不在捕获表，随后路径校验来不及转换。 |
| E2 | medium | patch | 与 B3 同一实际输出路径；保留独立裁决，随后同根因合并。 |
| E3 | medium | patch | 与 B2 相同真实 verifier 生命期缺口；describe 在核心分支实际调用未证实，不以 allowlist 充作执行证据。 |
| E4 | medium | patch | 与 B1 同根因；TimeoutExpired 为 SubprocessError，不会被现有通用异常 tuple 捕获。 |
| G1 | medium | patch | 预验证 gap 按原指令采信：维护的 B_ROUTE_RUNTIME_DETERMINISTIC_TESTS 缺新 adoption/native-reader 模块，hard/Windows PR 共用列表；注册确定性断言，不把手工回执当持续 CI 覆盖。 |

全部三层先返回后逐项裁决；以上为修复前结论，不建立正式验收。相同根因仅在独立裁决后合并。旧原生成功、失败、unknown 和既有占用保留，不升级为修复后源码资格。


## R47 原生 Step 4 / Step 5 收口（2026-11-08）

三层原始审核共 15 项逐项裁决：13 项 patch 合并为 10 个同根因修复，B7 按原合同驳回，B9 保留未证实的延后项；不据泛化竞态新增全局门禁。已修复 formatter、Unicode 输出、reader 有界诊断与实际依赖身份、Windows reader/verifier 生命周期、可观察扩展来源、共享 Graph 语义及维护中的 CI selector，未来 fixture 使用独立 TEMP。ADR0051 明确 reader/证据/存储的局部失败边界，不阻塞独立授权工作。

已执行并保留原件：13 项新纯测试（followup02，最终生产代码和所选方法 AST 不变）、12 项真实 Windows/扩展测试（followup03，16 个直接持有子进程）、22 项受影响的既有方法（followup03）。三批均自然 OS0、零跳过/错误/隔离违规并关闭各自源码；合计 47 个不同方法，不冒称一次全量测试或 93 项 CI 已运行。followup03 只改未被纯测试使用的 R19 fixture base 与 ADR 局部范围措辞，旧回执未改写。原 R41 六个真实公开阶段仍按其原 771 文件纪元引用，不重签旧操作或旧资格。

复核及验证原件：`logs/ci/2026-11-08/story26-r47-step4-repair-close/result.json`（SHA256 `6f2c2daaf2d0409147f270506ff7f4385c85182d1b4e1503633f3cfdc05e92fe`）；原三层 finding、逐项 triage、失败、unknown、原操作/claim/proof 均保留。本 Story 的操作冻结与稳定身份 AC1–5 已完成并按原生流程收口；不授予正式采纳、目标 apply/publish、Chapter 5 readiness、运行资格或默认 B。历史 Task108 调试附件仍缺失且保留引用/告警；当前真正必需数据与安全/漂移检查继续失败关闭。

79/290 paid-or-unknown、released=0，不新增项目模型调用；服务端实际模型/推理及物理请求数未知。未修改速度设置，不声称已读取 Fast 状态。仅保存本地工作分支提交，不推送或合并 main；后续 Story 按实际前置与准入继续。

收口时 `git diff --cached --check` 发现新 Graph helper 尾部多一个空行，已仅删除该 LF；完整模块 AST 相同。对应原像与桥接记录为 `logs/ci/2026-11-08/story26-r47-step5-docs/EOF-whitespace-bridge.json`，不改写三批原始来源和测试回执，也不重复无行为变化的测试。
