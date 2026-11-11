---
title: 'Story 2.5：Task 无关候选的独立准入与有界评选'
type: 'feature'
created: '2026-11-05'
status: 'in-progress'
baseline_commit: '9bc2738111354e708ecfde7c8be0b3f2eba44ff0'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 3B 已有完整冻结输入和候选结构 owner，但 generate/review 仍依赖旧 Task/readiness；结构报告不能证明实际执行或独立语义准入。

**Approach:** 沿既有 Capability/MVG runner、隔离 worker、admission、selection/checkpoint 增加明确的 3B 输入及数据服务适配，先完成确定性完整性／累计 delta 和独立语义硬门禁，再比较合格候选；最终只复验固定 winner，输出可供 2.6 使用的完整只读 handoff。

## Boundaries & Constraints

**Always:** 遵守 Story2.5 原 AC1–5、ADR-0038-mvg-candidate-admission 和 ADR-0039。每个参选候选绑定完整原输入、proposal、独立 proof、真实执行 receipt、lineage、规则及 selection input。保完整原文、全部有序草案和 accepted seed；每个实际请求单独测量、先持久预留再 dispatch。MVG 保三个合格候选、独立 OS 进程与工作区、只读 seed、协调器父机器复验及唯一原子提交点；稳定 issue 三次修复、稳定槽位64、run默认192和三轮 replacement 均不因进程／lineage／scope 改变而重置。Capability 保原96请求及时间默认预算，不误用MVG192。相关 drift、身份／schema／输入／执行故障失败关闭并与业务 finding 分开；同一失败不无进展重复执行。报告真实耗时和宿主可核对的逻辑调用，服务端实际模型、物理请求／费用未知即 unknown。

**Never:** 不重写或另建 worker/admission/selected/checkpoint 生命周期，不造 Task、manifest 或 formal_ready 绕旧门禁，不把 retired 内容／finding／prompt 带入 fresh replacement。不要把旧 incumbent/seed 作为额外参选者，不用 worker 自报成功推进 selected，不以最后审阅换 winner 或回退不合格候选。结构通过、manual/external 声明、synthetic receipt 均不冒充真实独立准入，不授 catalog 采纳／readiness／Flow 运行资格，不分配正式身份。模型外发仅限已明确授权和披露的目标、载荷及用途；新的私有载荷或其他受保护动作先报告具体范围，未获授权前不执行。不得读取 credentials/sessions、修改认证/网络/安全设置、触碰 nr/S2/main 或推送合并；真实执行阳性以实际证据为准，不因离线通过声称原真实证据 AC 已完成。

## I/O & Edge-Case Matrix

| 场景 | 输入／状态 | 预期 | 失败处理 |
|---|---|---|---|
| 明确3B公共路径 | 当前合格 prepared、完整模型候选链、明确 planner/profile | 两入口复用现有生命周期；无 Task/readiness；完整原输入及 seed 进入每个实际阶段 | legacy 混用、缺材料、未知 profile、current drift 在调用前拒绝；不伪造 ready |
| 先准入后比较 | 结构／delta 合格、独立语义覆盖 Requirement/Flow分支/交接/四部分/来源 | 全部参选者有相同完整合同的独立 proof/receipt；MVG恰三个合格后比较；seed不参选 | source_gap、硬 finding、缺真实 execution/identity 不参选，不把执行故障说成业务 issue 耗尽 |
| 真实子进程与预算 | OS worker/mailbox、稳定槽位、已付调用、并发与异常退出 | 只由协调器原子预留、父机复验、提交 selected/checkpoint；已付/unknown outcome不抹账 | 64/192、Capability96及原时间限制、三issue修复／三轮替换止损；重启不扩容 |
| 干净替换 | 稳定 issue 三次失败或调用／预算止损 | 既有 round账与 fresh lineage；每轮每槽位最多一次replacement；只有冻结输入与已接受 seed | retired提案/修复上下文不泄入新候选；run共享round不按Capability重新发放 |
| 固定 winner 与恢复 | proposal/proof/receipt/model配置/input 任一篡改或提交中断 | 重验原选中哈希、完整执行协议、epoch/reopen和唯一checkpoint | 保原证据/后编辑/未知提交状态；拒绝且不换winner；相同无进展失败不重发 |
| 下游只读交接 | 已由现有run原子提交的完成选择 | 定位完整内容、固定来源/审计、admission/execution、规则/配置、身份及可比delta | 缺原proof/相关漂移拒绝；selected不是正式B采纳或运行验证 |

</frozen-after-approval>

## 当前执行状态

- V4 当前续接（2026-11-06）：`s25-v4-comparison-successor-high/compare-01` 已以一次新的比较真实完成，231.016 秒、exit0，原提取和新比较的完整原生 proof/current 校验通过，8 个来源块无 semantic blocker，planning_eligible=true。仅证明当前来源审计资格；旧 v15 比较仍 unknown，其 31 文件与 v3 权威字节未变，没有退款。
- 截至该审计终态累计 55 个已付费或未知逻辑槽位，保留 240/290 原 guard。官方完整协议返回 openai/gpt-6.1-sol/high 运行时配置；服务端实际模型/推理、物理请求及费用仍 unknown。实现提交 `822492644b70151283a8de60285ec2c84ca247cd`，终态证据提交 `079287a45cef010fc5789fbf37ff8d450efe385c`。
- 原生 3B 冻结输入 i4 已准备，identity `sha256:ca51aa929b8a29089c302f08eb9c0a7bfd0876026b31d5d7b2dee9b7c939fb48`。c4/m4 首次完整 wrapper 估算分别 64599/64596 tokens，另保留 2000，均未截断且低于 96000。Capability c4 已以独立永久 claim 启动，原 Cap96 保留，当前尚不宣称候选/选择合格；MVG m4 尚未启动，须 Cap 真正合格且实际 k<=43，topup7+k<=50 才能完整预留 MVG192。
- 下列较早记录均为其各自冻结时点的历史证据，不推翻上述新审计资格，也不将来源审计或准备误称 Story2.5 完成。正式 Step3 候选/选择及 Step4/5 收口仍待实际结果。

- 原执行链 `c845ee81` 与真实两阶段 high 审计 `c640e0cf61218838d87787f7590c63ed7331b4257328d40952d701e28cab2b03` 的原件保留。收尾修复已纳入 `f2f90cc3`：仅 transport、其 stdio 测试及合成 child 三文件改变，其余原31文件一致。旧审计仍是旧规则的真实历史证据；由于相关工具字节已改变，不把它当新规则 current proof。当前没有新的真实模型调用或资格；未来3B必须先有完整新 current 审计，不弱化漂移门禁。
- 独立恢复能力已纳入工作分支 `1d92ace7`：新增 standalone `b_route_worker_recovery.py`，不改旧执行链及 import closure。21 个不同定向方法有通过记录，含完整原 machine/semantic/reservation/protocol/binding gate 下恢复同一 unknown 预留及 admission、原协调器跳过旧 lifecycle；全部为明确的合成离线证据，不能冒称真实 x15 恢复或 AC 通过。原失败及针对性修复记录保留，没有整套重复重跑。
- 原 nx 新入口的只读 inspect163 在原 high/NoSite 环境下通过当前输入、3A 和规则复验，仍以 `dispatch_outcome_unknown` 返回 blocked；未执行 apply。原 21 文件、34 源码和审计 c640 均未变；当前缺少原完成输出、绑定及 worker result，新恢复能力不会生成这些缺失证据。记录见 `logs/ci/2026-11-05/b-route-story-2-5-build/x15-recovery-inspection-163/report.json`；定向测试和独立窄审查见 `logs/ci/2026-11-06/completed-worker-recovery-159/summary.json`，不等同正式 Step4。
- x15 已启动，但 exec-server 断开且原会话 89429 恢复超时。原协调器 PID 10736、worker PID 11576 已消失；不能据此推断模型请求失败或完成。原始错误、进程观察和 21 文件哈希保存在 `x15-host-loss-147/report.json`；复核与私有本地证据归档在 `x15-host-loss-checkpoint-149/report.json`（路径均相对本 Story build 日志目录）。
- 仅 1 次调用预留，`x15:dispatch:1` 结果 unknown；没有完整输出、执行绑定或 dispatch receipt，协议中没有 turn/completed，没有合格候选或 selected。未重发、退款、篡改原账本或重开终态。旧 3B generate 仍先拒绝 unknown outcome 且不能重接 worker；新独立恢复入口仅接受完整原完成证据，当前 x15 不满足；不能用 generate 充当无副作用恢复探针。
- campaign 已关闭阶段计入预算的逻辑调用 48，原 192 总预留继续保留，guard 占用 240/290（不是实际调用次数），没有释放 unknown 预留或总池。根在既有自主实施授权内变更任务调度顺序：原先预计划、尚未调用的独立 Capability e15 通过 task scheduler v2 获分同池内完整96，原 x15 的96为不可再花费的责任预留（unknown1+未发95），旧 x15 的后续授权调度被永久禁止；原 run、192 started 及21原文件不改。这不是以新 ID 重试旧未知请求，也不改变原生限制或 Story AC。决策、离线验证及独立复核见 campaign-v2-implementation-170、campaign-v2-checkpoint-178 和 campaign-v2-independent-final-migration-review-177。
- v2 有 22 个组件方法及 8 个不同集成方法的通过记录；实际完整字符串封装预检 87646+2000<96000，全量原材料、schema、预算及 high 不变。历史 none/v1 精确重建和 x14 原 222 文件未变的证据继续复用；没有为本次连接故障重复测试。
- 官方返回的是 openai/gpt-6.1-sol/high 运行时配置、ephemeral/readOnly/无工具；服务端实际模型、实际推理、物理请求数及费用仍 unknown。连接中断根因及进程退出码未知，不宣称 AV 已修复。
- e15 于 2026-11-06T04:11:22Z 单次启动，04:29:23Z 原生返回 blocked/host2，共3次逻辑调用。前两次generation completed；第3次独立semantic评审的真实协议已有 turn/completed，但 runner 因 App Server 未在收尾时限退出而失败，未形成准入或handoff。原完整失败及52个已记账逻辑槽位（历史48+x15 unknown1+e15 3）、v2 settled/no-release 和本地归档见 e15-real-terminal-182/report.json。当前guard仍240/290。官方线程返回的 openai/gpt-6.1-sol/high 仅是运行时配置，服务端实际身份、物理请求及费用仍unknown；没有重开e15或伪造完成回执。独立r4工作树仅诊断和测试收尾修复，不改旧34源码、审计c640或原失败文件。
- Story 2.5 原生 Step 3 尚未完成，Step 4/5 未启动；尚无新两入口真实阳性、固定 winner 或完整 handoff。后续 Story 依赖不能据准备材料或独立组件冒称满足；没有操作 main、推送、合并或接触其他项目。

## Code Map

- 当前 Step3 收尾修复：官方 App Server 在 completed-turn 后可能仍写 stdout；先 wait 再 drain bounded queue 会造成可复现的合成子进程阻塞。独立 r4 的干净 OS RED、13个不同 stdio 方法及6个既有 replay 方法分批通过，根完整审阅差异并经独立窄复核后纳入 f2f90cc3。现改为持续验证尾部直到 EOF，再在原请求剩余 deadline 内等待自然零退出；保留 late error/tool/auth/reroute/max_output_tokens、大小上限、high/无工具和完整重放，不把 terminate 当成功，不增加原请求／原生预算。合成复现不证明真实 e15 唯一根因，旧 e15 失败和52个记账槽位不改；正式Step3/4/5仍未完成。记录见 shutdown-fix-integrated-186。

- 当前窄范围 Step3 容量修复：既有 x14 已真实终态且原件保留；不重启或清除 terminal，不将容量故障计为业务 issue 耗尽。独立工作树只交付通用、纯数据的 `_b_route_compact_literal.py`、其测试和说明；根线程唯一集成 `_b_route_planning_wire.py`、`_b_route_planning_input.py`、`_b_route_planning_runtime.py`、对应 runtime 测试及本说明。保持旧 none/v1、3A producer carrier 和 canonical 机器／独立语义校验的原字节；新建明确 v2 完整输入表示，使用请求内有序字段表、可逆短键及紧凑数据 literal。解析只接受 JSON 值，拒绝重复键、执行表达式、未知／混合版本、类型／索引／表／摘要或原始字节篡改；旧 public v1 decoder 不放宽。
- 原官方 `workspace_payload`、原 schema、原 `measure_actual` 公式和 96000／2000／1MiB、high、192／96／290 及全部时间／修复／替换预算不改。先用完整原 x14 超限请求证明逐字恢复全部材料，并对真正完整字符串 wrapper 重新计量；把计量包的 prompt 换成对象得到的 91702 已登记 counter-only-invalid，不作为方案或通过证据。
- 只对新 v2 generation 明确生产者必须精确保留每个原 Requirement 的 source_block_ids、acceptance_intent、non_task_sinks、prior_requirement_ids；这是已有机器合同的指引，不补写模型输出、不提供样例答案。旧 none/v1 prompt 不追加该新指引；原非法提案继续被拒绝。generation／admission／selector 均依捕获 delivery 绑定并精确重放，当前默认 v2 不用于解释旧记录。
- 传递工具身份包含上述模块，所以修复后旧3A及两个 x14 准入仍保留为旧冻结版本的真实证据，不能冒充新规则下当前资格。根先完成针对性离线验证、历史字节检查、全部差异阅读和新冻结，严格重验当前资格；必要的新两阶段3A和新原生3B属于已授权同类材料，累计46/290继续，不重置账本。正式 Step3/4/5 仍未完成。

- 当前窄范围 Step3 修复覆盖下方已完成的范围。唯一实施者仅可改 `_b_route_source_audit.py`、对应定向测试、既有 audit fixture 和 `docs/workflows/b-route-source-audit.md`。根拥有源夹具、任务脚本、实际请求、Spec／证据、冻结和提交。实施者不得调用模型／网络、操作 Git 或修改其他生产文件。
- 实际 v14/audit-01 报告和两个原 workspace/output.json 不可改。提取 `delegated-protocol-parameters` 的 statement 明确将参数留给指定实施者选择，却标 kind=underspecified；比较依据源认为是已表示的设计交接，却没有 finding。原 `validate_output` 正确以 obligation.unknown 拒绝。ADR-0040:26–29,35 和 epics:809,843–846,867,915–916,941–944 说明当前阶段无需预定实现符号或协议拼写；不能豁免缺失语义、来源冲突或未分配责任。
- 增加明确版本化的 producer 指引策略（v6 或等价独立身份），沿用 v5 完整材料传输。保留原 canonical PROMPTS、schema、phase payload identity、validator 和不确定项保留门禁。none/v1/v2/v3/v4/v5 历史 input/schema/prompt/proof 重建字节不变；不重定义历史常量或改写已保存输出取绿。
- 新提取指引须区分真实 unknown/underspecified 语义需求（缺失／冲突的必需行为、owner、验收约束或未解决交接）与明确有界、分配给 owner 且要求下游选定并记录一致实现的设计自由度。后者保留为真实 handoff/constraint，并保留全部语义义务；不能推断不存在的委托、把笼统 PASS／免审声明当权威或压掉真实 unknown。完整原文仍是非可信数据，不是指令。不提供样例专用答案或协议默认值。
- 新比较指引须明确：每条实际提取 kind=unknown/underspecified 及 unknown block disposition 均必须保留 finding，即使 represented。可在 finding 解释分类疑议，不能静默消除。保全部真实遗漏／冲突检查、精确引用和完整 review 行，不由宿主重分类或修补输出。
- 新 producer prompt／policy 和完整 carrier 通过既有身份绑定真实执行与重放，拒绝未知／混合版本。复用 v5 无损 codec 和输出 schema，不另建生命周期。相关源码漂移照常令旧 current proof 失效，历史只读重放按捕获策略。high、无工具、30000／1MiB、原生2／192／96、campaign290、超时与 reserve 不变。
- 仅验证受影响项：旧 v5 及更早 prompt/input/schema 字节兼容；新指引送达且绑定重放；实际 v14 不确定提取与 represented／空 finding 比较仍严格拒绝；合法保留 unknown finding 和真实遗漏／冲突的控制项仍为阻断；未知／混合／新 policy 篡改在派发前失败。必要时以新策略跑完整 synthetic 原生 audit 执行／重放，明确0外部模型；复用不相关已有效检查。报告文件哈希、去重方法／结果及局限后停止写入。确定性指引检查不证明真实模型分类或语义验收通过。

- 当前新增修复范围优先于下方已完成的 3B/v4 范围：唯一实施者仅改
  `_b_route_source_audit.py`、必要的通用 wire helper 接缝、对应 source-audit
  定向测试及既有两个 audit fixture、`docs/workflows/b-route-source-audit.md`。
  根线程拥有实际 v11 合成材料、prepare/account、任务脚本、模型调用、Spec／日志、
  冻结及提交。不得改 3B 生命周期或已完成的业务门禁；不得运行模型、网络或提交。
- 已有 `9057898c` 是可回滚代码检查点。新当前 high 两阶段审计实际完成但语义
  阻断，campaign25/290；观测接口／startup 与取消范围待在同类合成源内澄清。
  关键实际容量为本轮 compare/measurement.json 的 29378/30000，而非更早的约25k。
  拟补 ABI 草案新增874B，后续真实 extraction 大小未知。先离线解决重复传输，
  再由根线程重新冻结当前代码、同一授权类别源和真实2阶段；不得靠扩大预算或截断。
- 新增明确的 source producer v5 策略，将完整 producer 输入作版本化、请求本地
  无损共享。复用现有严格 lossless codec／通用完整材料 helper，不另写删字段投影。
  共享范围包括完整原 files／text／raw字节表示／blocks、机械 candidate／proposals／
  accounting、全部真实 extraction 和原 span map；每个原值、JSON类型、顺序、
  未知合法嵌套字段和字符串可准确恢复。保原完整 phase_input 及 canonical identity，
  新实际 wire 身份／策略／schema／prompt／measurement／原raw协议仍分别精确绑定。
- v5 仅改变 producer 输入的传输表示；实际输出保持既有 span-ref 语义及 v4 的
  producer-only string constraint compatibility subset，规范 schema 和原
  validate_output／validate_citation／独立语义 finding 不变。不新增或补业务值，
  不复用旧 extraction 充当新源结果，不把解码内容冒充服务端原始输出。
  原 none/v1/v2/v3/v4 的输入／prompt／schema／output／proof重建字节必须全部保持；
  不通过重新定义旧 v4 常量将其悄悄指向 v5。未知／混合版本、引用／摘要／映射及
  原始输入篡改失败关闭；旧策略重放只用捕获策略，不读当前默认策略解释历史。
- 为任务 prepare 及现有内部使用者提供一个明确纯解码／检查接缝，以检查 v5 真实
  producer carrier 恢复出的全部原 canonical/span材料；不能为方便把旧公开字段
  静默替换成缺失内容。Root 的离线 helper 会在最终稳定 API 后适配，旧现场不改。
  如 actual input.json 改为 envelope，模型提示必须完整说明请求本地引用、原始源
  字段及 span-ref 的不同命名空间；不可要求模型用工具或猜外部定义。
- prepare_step、verify_step、current proof 复验均必须从原始 phase 输入／捕获策略
  重建同一 v5完整wire，先完整实际 runner wrapper 计量、再原持久预留和 dispatch。
  比较仍为全部实际 extraction＋完整全局来源，原每文件提取＋一次global comparison
  的计费次数／调度所有权不变。原30000/1MiB、high、原两调用和campaign290均不变。
  相关源码／helper指纹照常改变并阻止旧 current proof 复用，不能为省调用弱化漂移门禁。
- 定向验证：以实际已保存 v10 comparison 输入或完整同型fixture证明完整值恢复与
  原实际wrapper字节／token节省（不得称新v11实际容量已通过）；类型／顺序／字面ref、
  未知嵌套值、坏／混合版本、摘要／ref／span map篡改拒绝；v4及更早字节保持；
  v5 fake协议完整 execute＋原执行绑定／回放，规范错误引文／空字段仍拒绝；
  真正最终wrapper超限在预留前拒绝。只跑新增及受影响方法，保原失败日志。
  输出最终精确文件哈希、方法去重清单、旧字节检查与稳定接口，停止写入交根。

- CURRENT Step 3 repair (supersedes the completed v4-only repair scope below):
  the sole implementer may change `_b_route_planning_input.py`,
  `_b_route_planning_runtime.py`, `_mvg_capability_selection.py`, the existing
  lossless evidence transport helper or one narrow new 3B wire helper, their
  targeted tests and directly affected workflow documentation. Root alone owns
  actual calls, evidence, spec changes, freezing and commits. No model/network
  calls, Git staging/commits, external transfers or concurrent current-tree writer.
- Grounding: native MVG w10 is terminal selection-blocked after two completed high
  generation calls; admission/selection/Capability never started. Campaign 23/290.
  Record `native-w10-failure-offline-triage-85.json` contains the original synthesis
  schema rejection: extra content.prior_drafts and content.synthesis_context.
  Its diagnostic owner check also found a planning_proof locator grouped three
  paths while that owner resolves the referenced single file; another grouped
  five audit paths and the Markdown source was incorrectly claimed as the C#
  contract owner. Follow each actual owner resolver, never a guessed file set.
  Preserve all raw output and charged journals. These
  failed outputs may be offline diagnostics, never repaired/admitted/reused as
  generation seeds. Fix the next producer contract, not canonical validation.
- Separate final proposal content from incoming orchestration. Generation must
  receive the entire canonical candidate schema with its reference closure and
  an explicit target `/properties/content`: final synthesis content_json encodes
  only that content object. Original prior drafts and synthesis transport stay
  intact as input/provenance; copying them into content is not required or valid.
  The carrier codec still preserves every actual output value and rejects bad
  schema unchanged. Batch drafts retain the original open draft contract; do not
  close it to final candidate fields. State exact canonical owner/reference/file
  set rules already expressed by the frozen input and validators. Do not invent
  game features or add example answers tuned to this fixture. Future results
  still pass all original schema, owner, graph, flow, source, delta and admission
  gates, and a failed output is never silently stripped or host-repaired.
- Keep the historical generation instruction byte-identical only for historical
  no-wire delivery. New wire instructions must explicitly distinguish lossless
  preservation of DELIVERED input/actual-output codec values from generation of
  NEW target business content. The old phrase "content_json must encode the
  complete original content object ... Do not summarize or omit fields" must not
  imply copying all incoming orchestration into new content. Refer explicitly to
  final_content_target for synthesis, retain the open batch contract, preserve
  applicable business meaning/IDs/source links and allow concise responsibility
  statements without repetition of unrelated scenario narration or input/schema
  inventories. This never permits missing obligations or host output repair.
- Offline complete-material forecast `task/night-handoff/materials-size-forecast.json`
  shows next canonical synthesis 106240 input tokens; admission plain 231565;
  whole-material exact reference sharing 69802 (known wrapper forecast 72048).
  Original max96000, reserve2000, max1MiB remain. Reuse proven lossless_context /
  restore_lossless_context across the ENTIRE request materials, not just core,
  without model_context projection, omitted fields, truncation, gzip/base64,
  raw-log substitution or summaries. All values/types/order/unknown nested fields,
  original complete drafts, qualified sources, proposals and obligations survive
  a type-sensitive byte-equivalent JSON roundtrip. Reference namespaces must be
  unambiguous even for literal ref-like user keys and nested legacy encoded core.
- Producer guidance must expose existing cross-field machine contracts as data-only
  technical metadata, without sending production source or modifying validators:
  `_b_route_records.plan_relation_checks` requires coverage_table[requirement_id]
  equal the ENTIRE corresponding requirement_verification object minus evidence_ids
  (including exact rationale), and applicability disposition/rationale must match
  that same verification row exactly. All three domains equal the governed
  Requirement set. `plan_evidence_checks` requires exactly one allowed owner/locator
  for each evidence or nonnull verification/authority locator and no unused
  evidence_source_refs; do not add source/account/audit refs merely as decoration.
  `_b_route_record_owners.resolve_owned_ref` requires files exactly equal the
  resolver result: ordinary file/fragment owners resolve one source file; contract
  means a real frozen Game.Core/Contracts C# declaration, never a Markdown test
  source. `_b_route_candidate.check_graph` permits exactly ONE required entry
  boundary per Flow and nonempty required successes; every graph endpoint, use,
  handoff and state owner resolves, branches correspond to boundary kinds, all
  declared obligations retain actual source support. These rules explain known
  w10 defects, not an answer fixture; do not host-derive or fix business content.
  Test the new guidance/metadata is delivered and replay-bound, while original
  invalid projections, unused refs, owner mismatches and multi-entry still fail.
- Introduce a narrowly versioned new 3B wire delivery. Keep canonical material
  identity distinct from and bound to actual wire digest, schema, prompt, runtime,
  reservation and receipt. Decode once in a common strict path for generation,
  admission, dispatch, proof/reservation replay; reject unknown/mixed versions,
  dangling/cyclic refs, material/digest/schema/metadata tampering. Reconstruct the
  full expected originals at every existing boundary, not merely the digest.
  Existing plain/core delivery and historical prepared/replay bytes must remain
  exact; explicitly version the new path in immutable runtime/request metadata.
- planning.build_request currently measures the full canonical root BEFORE wire
  sharing; simply encoding invoke_data cannot fix this. Add a narrow pure canonical
  construction seam with identical frozen/capacity/config/draft-chain checks for
  the versioned native wire path. Existing public build_request retains its exact
  measurement/failure behavior. Measure the FINAL encoded actual runner wrapper
  plus schema/files before reservation/dispatch under unchanged original limits.
  This is not an unchecked generic bypass or new request-budget owner.
- Cover selector now as well: retain original A/B/C, accepted-seed and complete
  comparison-context artifacts unchanged on host. New delivery can encode their
  complete structured virtual file contents together once in the prompt; do not
  also send duplicate raw file copies in the model sandbox. Preserve every
  original field including evidence text/raw strings, original proposals/drafts,
  admitted proof identities, frozen authority and seed. No field projection.
  Preserve blind aliases, seed never candidate, all-admit-before-select, exact
  cardinality and fixed-winner/checkpoint semantics. Reconstruct and compare full
  decoded selector inputs against original admitted artifact bytes and reserved
  scope/public identity, not public hashes alone. Measure the exact new selector
  wrapper before reservation. Legacy selector layout/replay remains unchanged.
- Selector host-file reconstruction must validate the exact existing profile alias
  key domain and candidate-label bijection BEFORE deriving or reading any filename.
  This also applies during reservation replay: verified_prefix calls
  verify_reservations before its later current/selected alias checks, and the new
  check_selector_materials reads step.aliases from the mutable ledger. A post-edited
  absolute/traversal alias must fail before selector_materials can read
  workspace/(alias+'.json'), even when the original bound prompt still has valid
  aliases. Reuse the existing alias-domain source, not a new naming contract.
  Add a narrow no-outside-read negative using a harmless synthetic/spied path;
  never try a credential/session path. Ordinary valid selectors stay unchanged.
  Original host files themselves must pass the existing contained-path/reparse
  checks before bytes are read; sandbox input enumeration does not cover those
  host sibling artifacts in the new virtual-file path. Reuse checked_path rather
  than introducing a second filesystem policy or hostile-topology guarantees.
  Also require selector identity.order_index to be an actual int within the known
  scope domain before lookup/reconstruction. Python False equals 0 in current-step
  selection; rebuilding expected selection_identity from that untrusted False
  would otherwise accept rehashed false metadata until the later receipt check,
  wasting a dispatch. A rehashed False-for-0 negative must reject before reservation;
  transport digests do not confer authority on an altered metadata type.
- Additional offline sizing: `task/night-handoff/w10-candidate-machine-review.json`
  forecasts three same-shaped original failed candidates at 96925 tokens including
  reserve if nested comparison encoding remains opaque; decode that original
  comparison transport into the explicitly new canonical model materials before
  outer sharing and the forecast is 63679. All complete values, types, ordering
  and original source strings must roundtrip. This does NOT mean old encoded file
  serialization bytes equal the new wire. Keep original host files/raw hashes
  unchanged and replay them exactly; explicitly reconstruct the new canonical
  selection material from those originals. Do not require a redundant copy of
  the old intermediate transport envelope in the new prompt. This is a synthetic
  same-shape forecast, not a guarantee for three actual different candidates;
  always measure the actual final wrapper. Definitions 59371B are actual business
  Flow/command/state structures, not schema duplication; never delete them merely
  to fit. Only the two invalid orchestration content fields were extraneous.
- Bind any new transport helper to runtime rule/tool identity. Production changes
  invalidate current conservative source-audit tool identity: preserve the already
  valid 3A proof as history, do not falsely claim current reuse or weaken drift.
  Root will freeze/review first, then obtain new current 3A/prepared input and a
  distinct controlled native attempt within the SAME remaining campaign budget.
  No resetting paid repair/replacement budgets or retagging failed w10 as success.
- Targeted offline tests must cover complete large prior drafts above the old
  root limit whose exact encoded final wrapper fits; false versus 0, Unicode,
  order, unknown nested/ref-like fields, material/schema/ref/version tampering;
  actual wrapper over bytes/tokens/reserve limit rejected before reservation;
  old plain/core byte compatibility; both native profile paths through existing
  coordinators with complete selector reconstruction and negative tamper cases;
  explicit final-content target while bad output extras remain rejected unchanged.
  Reuse already effective unrelated tests. Keep high/no-tools/real execution
  bindings and native 2/192/96, 64 slot, timing/timeout and cumulative290 budgets.
  Report exact changes, focused tests, source hashes and residual limitations;
  do not claim real acceptance or change worker/admission/selected/checkpoint
  ownership, frozen intent, auth/network/global dependencies, main or remote state.

- Current Step 3 repair ownership: only `_b_route_source_audit.py`, `_codex_app_server.py`,
  the corresponding source-audit/stdio tests and their two existing fixture files,
  plus `docs/workflows/b-route-source-audit.md`. Root owns actual calls, spec/logs,
  commits and the current worktree. No external model calls by implementer.
- Evidence high-schema-shape-repair-plan-71.json: v9/v10 independent extraction and
  a 525-byte transport-only expected object under the EXACT v10 schema failed
  max_output_tokens at actual high; the tiny status-only high schema passed.
  This does not prove a schema keyword is unsupported. Do not claim a root cause
  or numeric output cap without evidence. All failed bytes/charges remain.
- Add producer policy input-identity-span-ref.v4. It preserves v3 span transport,
  complete canonical payload, canonical output schema/validation, literal partial
  citations, raw output and independent decoding. Its API-facing producer schema
  alone recursively omits string `pattern` and `minLength`; types, required fields,
  const/enum, array/object closure, ranges and every final canonical validation stay.
  This is a constrained-decoder compatibility subset experiment, NOT a relaxation
  of semantic/citation admission. Old none/v1/v2/v3 schemas, prompt/input/proof bytes
  and replay remain exact; bind new delivered schema/policy into identity and replay.
  Do not alter historical v3 expected schema by redefining it through v4 behavior.
- New requests use v4, while both captured v3 and v4 get exact span-reference handling.
  Test historical v3 byte preservation, new schema difference, whitespace/empty
  canonical field rejection, literal/unknown-ref/tamper rejection and full fixture
  execution/replay. Reuse already effective unrelated tests; no larger suite here.
- In the live official App Server receive path, on the first observed server error
  whose actual error.message or error.additionalDetails reports max_output_tokens,
  fail closed promptly, preserve that journal/error and terminate only its owned
  subprocess tree. Do not wait through identical internal retries. This does not
  modify network settings or claim a physical retry count. Other transient retry
  notices retain existing behavior. Add an OS stdio fixture test proving prompt
  cleanup before timeout and an unrelated transient-retry success control.
- Keep high and all input/runtime/tool/raw-output bindings. Do not change auth,
  sessions, global/network settings, original 2/192/96 or cumulative 290 budgets,
  worker/admission/selected/checkpoint owners, main or remote state. Freeze changed
  files and targeted results when done, without committing or claiming actual AC.



- high 是实际执行要求，不能只验 App Server 自己的请求／返回一致：共享 validate_execution 需接收可选 expected_reasoning_effort，由当时可信 runner description 的 requested_reasoning_effort 提供；若要求 high，实际重建 proof 必须同时记录原捕获 high 请求及 RPC2 high 返回，缺请求、medium／low 均拒绝。3A live/replay 从捕获 runner.json 传期望，不读取当前环境解释历史；3B verify_call 从 hash 绑定的 runner_info 传期望。tool_identity/current-reuse 也必须绑定可选期望档，拒绝跨 high／默认档复用；默认无期望不增字段、旧证明原样。历史捕获 low 仅允许只读核对其原期望／返回，不作为本任务 high 验收。需负向测试防止 parent describe=high 而 child 丢环境退成默认／low 或 proof 缺 high 请求的情况。此强验证只绑定原实际配置，不声称服务端实际推理或模型已被证明。

- 最新用户约束覆盖先前 low 试验：此后 NewRogue 真实执行与验收固定 high，不允许降 low；low 试验已终止且未产生合格证据，累计 11/290。`NEWROGUE_CODEX_REASONING_EFFORT` 新请求仅接受未设／精确 high，本任务驱动必须显式 high，description 和 actual RPC2 均如实记录并在 turn/start 前核对 high。历史 replay 仅对原捕获 low/high 配置及当时返回做一致性检查，不读当前环境，不把旧 low／medium 证据冒充 high；默认未设仍保持旧字节供历史／其他通用调用。本任务不得再发 low 验收。

- 为解决输出截断，优先在保持完整输入、原 native 2 次审计调用及累计 290 上限内减少重复输出，不能截断、漏审或把实际调用数改小。新增仅 full-block producer 使用的版本化 `input-identity-span-ref.v3` 无损引文传输：原 canonical phase_input、输出 schema、validate_output、validate_citation、语义 finding 与业务门禁保持。producer_input 是原请求的深复制并只追加明确 transport 元数据：按完整原 files／blocks 的稳定顺序分配 `span-000001` 等唯一引用，映射到同一冻结源的 path、raw_digest、block_id、byte_start／end；原完整 payload／原文不改。producer schema 的每个 citation/basis 槽允许 `{span_ref:<已声明枚举>}` 或原完整 literal citation 两种严格闭合分支，合法局部 literal 引用继续允许；不新增业务准入限制。

- 新 wire prompt 明确优先选择已提供引用、仍独立提取／比较全部原文件及全部必需 review 行，不要求重复抄写长 quote；仅传输层引用映射，不能代模型选择语义证据。decoder 先严格验证实际 wire schema，再只在规定 citation/basis 位置把模型选中的引用映回同一冻结源已知 byte span／原 quote；不推断、不补业务字段、不修错 literal 引用。未知／重复映射、跨源替换、混合 ref+literal、错误版本／schema、无效别名必须拒绝。原 wire JSON／receipt／协议逐字节归档并先按原 raw bytes 验证执行；canonical extraction/comparison 是显式解码视图，不得冒称服务端实际返回了展开的原文 quote。现有 canonical 产物可保存解码视图，报告／proof 身份明确记 `model-selected frozen-source span references`。

- verify_step 与完整 proof 重放必须从原捕获策略、原冻结 expected phase 输入独立重建 producer_input、映射、wire schema 与 wire prompt，验证其原始序列化和完整请求哈希／measurement／真实 raw 绑定后独立解码，再执行原 canonical 规则及聚合比较。默认、无 policy、旧 v1/v2 的 prompt/schema/input/output 原字节重放保持；未知策略失败关闭，不跨策略复用。规范 PROMPTS、CITATION_GUIDANCE、phase_input 和 canonical validators 不为新格式改语义；用独立 wire prompt helper 与版本身份绑定追加指导，不能让旧 proof 依赖当前策略。全部原文件仍进入每个原阶段，仍是一次完整 file extraction 加一次 global comparison，不新增轮次或省略未知／冲突检测。

- 离线检查需证明任意 UTF-8、CRLF／bare-CR、非 ASCII 和同 block_id 跨文件引文精确映回原字节；所有 canonical 字段／顺序／类型不丢、literal partial 保持、原错误 literal 仍拒绝；raw/canonical 不可替换，历史 v1/v2 精确重放，篡改映射／schema／策略／输入／输出均拒绝。使用同一非空完整 fixture 对比 literal 与引用 wire 的字节／token 规模，明确这只是机械压缩测量，不能冒充真实服务通过。先跑新增和受影响定向检查再冻结；主线程做一次必要独立回归、high 元数据核验后再外发，实际结果为准。

- 历史 low 试验已由上述 high 明确约束覆盖；保留其不可变检查点和失败证据，不得用作 high 验收。

- 官方结构化输出只支持闭合对象，但 canonical DRAFT 的 content 明确允许完整未知 JSON 字段；不能以闭合 content 删除未知字段或收窄合同。仅 3B generation 实际生产 schema 使用版本化无损 carrier：保留原 schema_version 及四个独立推导的 metadata const，另有显式固定的 producer_schema_version；content 用非空 content_json:string 传输。carrier 顶层严格闭合，完整原始模型 JSON、schema、prompt、协议、receipt 与预算仍由原执行绑定归档。唯一 codec 严格解析 content_json 为原 content 对象，拒绝重复键、非 JSON 常量、错误类型、未知 carrier 版本/字段；不补业务值、不修模型语义。原 canonical draft、完整前序 drafts 与原始 carrier 同时保留。此后仍经过原 validate_draft_chain/candidate/admission。proof 复验必须独立从真实 raw carrier 解码、核对 canonical draft，不能把解码后的对象冒充原始响应，也不能用合成 receipt 代替执行；变更纳入 runtime rules 和实际 producer schema 身份。review/selection 业务语义与 worker、预算、selected/checkpoint 生命周期不变。若其他官方不支持关键词需从 producer 去掉，必须仍在原 host 校验器中严格执行，实际 wire schema 与 canonical schema 分别精确绑定，不修改原 frozen schema。离线验收须覆盖任意未知嵌套 JSON 的逐类型无损 round trip、错误 carrier/raw/canonical 替换、父稿顺序和已知四 metadata、两个 profile 的完整 OS/绑定/预算/selected 流程；源代码冻结后主线程做针对性独立验证再外发。

- 真实 `s25-v8-guided/audit-01` 首次提取被官方服务拒绝：`invalid_json_schema`，`schema_version` 的 const 缺显式 `type`。不是容量错误；本轮实际比较与 3B 未调用，累计保守计费槽为 8/290。原失败输出和协议不能修补或覆盖。
- 生产 schema 的等价类型声明：3A 新 full-block 使用新版本 policy，为既有字符串 schema_version const 显式声明 string；旧 v1 以及无 policy 的历史 proof 按原字节重放，未知 policy 拒绝，规范 schema/引文/业务校验不变。3B generation 的独立派生 schema 同样补 schema_version string；review/selection 的字符串 const/enum 全部显式 string。不能替模型填充或修改语义输出、不能修改 frozen prepared 或正式 schema 资源。针对所有实际生产 schema 离线检查缺类型常量/枚举，覆盖类型、policy 降级/篡改、旧 proof 重放以及两个 profile 的完整 OS 本地协议测试，只运行本次受影响检查。

- `scripts/python/_b_route_sources.py`／`_b_route_source_audit.py`：真实无工具 producer 的局部引用曾偏差一字节；可选 full-block 指导及紧凑模型 JSON 绑定原始请求、阶段输入/工具/提示身份和精确重放，默认字节与原引用/输出 schema、校验不变，不修补模型输出，不新增业务准入门槛。

- `_bmad-output/planning-artifacts/b-route/epics.md:946–993` 是原 AC；`docs/adr/ADR-0038-mvg-candidate-admission.md`／`ADR-0039-mvg-completed-capability-recovery.md` 拥有有效生命周期和预算。主上下文为已验证缓存 `epic-2-context.md`；前置 2.3/2.4 已 done。原 2.4 Spec 的 Code Map/Tasks/Design Notes 已读，保其公开辅助 schema 和唯一 owner。
- `scripts/python/_b_route_planning_input.py:405,421,454,699`：复用 validate_draft_chain、build_request、load_prepared、prepare_successor。当前校验依赖完整原档、lossless transport、相关工具/schema及审计；successor只预检不计费。运行阶段增加 seed/独立候选/proof 等材料时必须测量实际完整请求，绑定额外材料身份，不能照抄原 template measurement。
- `scripts/python/_b_route_candidate.py:409,437,448`：唯一结构/图/关系 owner，精确JSON内容、冻结依赖、既有与 proposed 身份、strict current validation。复用纯 check；公共 validate 写独占日志。3B语义门禁须额外禁止未解决 source_gap 参选，不能把其结构合法当满意。保持 frozen snapshot/content match 与 published/current 权威的区别。
- 新 `scripts/python/_b_route_planning_runtime.py`（可按同一 owner 拆纯数据服务）：只负责 3B 输入/profile、请求/schema、机器与累计保留、独立语义/proof、selection projection及只读 handoff。用不可变、可序列化、白名单 stage/profile 让父进程和真实子进程解析相同服务；不要只在父进程 monkeypatch，不引任意模块注入或第二份运行/预算日志。全局完整来源／分母和受治理闭包继承 2.3；单位/前缀范围必须来自真实受治理材料，未知关系回退完整范围，不能伪造 Capability。若派生分阶段输入必须有自身可验证身份并绑定根输入；不得修改已验证 frozen 字典而保旧 input_identity，最终全局机器复验覆盖原请求全部适用义务。
- `scripts/python/_mvg_capability_append.py:28,87,136–260`：复用既有修复／退休／账本控制循环；为 merge/preservation 等旧 payload 专属检查增加窄服务接缝，legacy默认不变。`_mvg_capability_generation.py:195,347–451,1022–1040,1222,1380–1516` 的 seed/scopes/envelope/Task/机器/proof逻辑需明确3B数据适配，不能生成假的旧对象。只读 seed、完整所有草案和累计关系均保真。
- `scripts/python/_mvg_capability_worker.py:51,101,130–201`：保 OS child/cwd、启动门、Windows Job Object、job digest/PID、产物三件hash和 mailbox reserve/cost/outcome；子进程本身只产候选。`_mvg_worker_lifetime.py` 原进程树约束不变。阶段适配不得令 worker 写父 run.json/selected/checkpoint。
- `scripts/python/_mvg_capability_selection.py:34,48,101,111,167,418–820`：保原协调器的持久预留、父机器复验、selected原子提交及prefix重放；仅输入/seed/scopes/proof/比较投影等数据接缝识别profile。`_mvg_capability_checkpoint.py:273,310` 继续唯一staged payload／run.json原子点和unknown outcome恢复，不另建journal。新payload仍保全部图/身份/原proof，不丢成摘要。
- `scripts/python/plan_mvg.py:287,311,5625–5662`：fresh_replacement_lineage 与 reserve_replacement_round 可复用。**当前local路径:4930提前return，append:208只有context重启，无显式三轮账，不能假称已经继承。** 在即将fresh replacement处用窄回调/mailbox向协调器申请并先持久化；不是付费model调用，不借reopen generation伪造lineage。旧语义为run内共享round，每round可给每slot一次replacement，slot间不是合计只能替换三次；跨Capability不重获三轮，保run级slot depth/事件。
- 新 `scripts/python/_planning_execution_binding.py` 或等价单一纯owner：提取 `_b_route_source_audit.py:380–423 validate_execution` 的严格 stdout/OS completion/`_codex_app_server.replay` 检查，保持原3A证明不变；3B generation各batch/synthesis、独立reviewer、selector、最终复验共用精确 prompt/schema/output/protocol 绑定。`_mvg_planning_review.py:282–294` 当前仅descriptor/hash/非空model，不能把它当协议重放。官方 `codex_isolated_model_runner.py:477` description为environment-default，`plan_mvg.py:1082–1092` 只识别auto等；新增真实字面回归，不能把请求model当响应身份。只核验实际返回runtime_configuration，provider model/物理次数保持unknown，不重设provider-only门槛。
- `scripts/python/plan_mvg.py:409,508` 的 admission、`:6316–6354` 固定winner复验、`_mvg_capability_selection.py:654,736–743` 的先准入三候选与seed合同均须保留。`:932 ranked_semantic_fallback_candidates` 只是legacy inspection，3B不得用作回退。Capability旧review `plan_capabilities.py:1566–1572,1757–1771` 的结构两候选/后修正文不能直接当3B合格选择；3B先做独立准入，保持其原默认请求/时间上限，不把MVG三候选/192误套为所有Capability路径新门槛。
- `scripts/python/dev_cli.py`、`dev_cli_builders.py:635,678–705` 和两 planner main：默认legacy。精确开放3B generate/review/最终验证/status，绑定prepared与profile/已存在run，不整体放开apply/正式adoption；planning-contract仍属prepare。调用前按 lexical root检查，不resolve掩盖junction。不读取Taskmaster/readiness弥补缺口。非法混用拒绝，不静默忽略阶段参数。

## Tasks & Acceptance

**Execution:**
- [x] 原 3A producer 可选引用指导：全块定位复制、紧凑无损模型输入、模式/身份/重放绑定、默认历史字节保持、未知模式和 prepare/account 前置拒绝；真实错误引用仍拒绝。定向 8/8；两受影响模块 72 通过、1 POSIX 平台跳过，0 failure/error。真实新审计结果另验。
- [ ] `_b_route_planning_runtime.py` 与原输入/候选owner：明确阶段化数据服务与身份合同，完整请求/seed/原稿传输、当前性与累计delta/语义门禁、必要只读handoff；原raw/source/schema/模型协议不伪造，source_gap阻断资格。
- [ ] `_mvg_capability_append.py`、`_mvg_capability_generation.py`、`_mvg_capability_worker.py`：把3B数据服务接到原控制循环/OS进程；持久预算写前预留，worker无提交权；窄replacement申请保三轮与稳定槽位，旧默认行为不变。
- [ ] `_mvg_capability_selection.py`、`_mvg_capability_checkpoint.py` 及 planner相关函数：同一协调器独立父机复验／比较／唯一原子selected checkpoint，固定winner、完整seed/prefix、unknown提交及失败关闭；默认预算与epoch/reopen不重置。
- [ ] `_planning_execution_binding.py`／原3A执行校验：共用可复验原始执行绑定，精确JSON与真实runtime配置；正式3A原收据接受语义不被放宽。manual/external输入不能凭结构报告取得真实执行资格。
- [ ] `plan_capabilities.py`、`plan_mvg.py`、`dev_cli.py`、`dev_cli_builders.py`：明确3B阶段与prepared/run绑定，两入口保旧默认与预算；最终验证只复验不换winner，输出可定位handoff，日志以外不写正式plan/catalog。
- [ ] 新 `scripts/python/tests/test_b_route_planning_runtime.py` 及相关真实OS worker/预算/receipt/CLI/checkpoint回归：逐行验证矩阵。覆盖实际子进程边界与无提交权、少于三MVG候选不调用selector、预算和替换不重置、干净新lineage、不完整/错序草案与容量、schema/哈希/真实配置/协议篡改、同ID不同JSON类型、失败不换winner/不无进展重发、断点/占用/unknown outcome、旧legacy门禁。阳性seam与真实请求分开标注，无公共测试bypass。
- [ ] `docs/testing/story-2-5-independent-admission-selection.md`、原owner说明与原生spec/sprint：记录格式、入口、实际结果、计数范围及真实阳性缺口；完整图和身份留给2.6正式采纳，不推送。

**Acceptance Criteria:**
- Given 当前完整冻结输入，when 任一明确3B入口执行准入/比较，then 沿既有执行生命周期获得结构、独立语义和receipt逐项绑定，且不要求Task/readiness；缺任一真实证明不得qualified。
- Given MVG逐Capability执行、修复/替换与中断，when 取得三个可参选候选或停止，then 原OS隔离、父机复验、稳定64/run192、三issue修复与三round账均保真，Cap原96/时间预算独立；任何新进程/lineage/scope不得扩容。
- Given 所选证据/输入相关漂移或任一提交不确定，when 最终验证/恢复，then 保原文件并诚实阻断，不换winner、复活中间候选或重复无进展调用；相关hash和epoch/reopen均有效。
- Given 已原子提交的选择，when 下游读取，then 可定位完整内容、来源/审计、独立proof/执行、规则配置及可比差异；selected始终不等于正式B采纳、readiness或运行通过。

## Implementation Notes

以下为历史工程检查点，保留当时的失败、计数和资格边界；当前情况以本文件“当前执行状态”及对应原始报告为准。

- 显式 profile `3b-mvg-v1`、`3b-capabilities-v1` 在原协调器和真实 OS worker 中解析同一可序列化数据服务。native planner 与 dev_cli 开放 generate/review/verify-selection/status；MVG 不带 candidate 的最终 validate 绑定已有 run。prepare 与结构读取保留各自原 owner。
- 复用原 append 修复/退休控制、协调器预留、稳定槽位、Job Object/启动门、锁和 staged/run.json checkpoint 提交。fresh replacement 前经父 mailbox 持久预留共享轮次；执行故障独立停止，不消耗业务 issue 修复额度或无进展重发。
- 保守使用完整原 governed closure 作为准入单元，不派生或修改 frozen 输入，不伪造 Capability/Task/manifest。完整 drafts/seed/raw source/proof 均保留。独立审阅覆盖全部 Requirement、Flow 条件/交接/四部分、选定原 Flow 依赖及来源；逐 generation/reviewer/selector 绑定并重放精确请求和原 OS/协议证据。
- MVG 保持三个候选、稳定槽位 64 次、run 默认 192 次；Capability 保持两个候选、run 96 次及其原时间默认预算。官方 environment-default 只作为请求配置；资格还须来自实际返回的 runtime identity 与协议证据。provider 模型/物理次数/费用保持 unknown。最终 handoff 保留完整所选内容、原证据引用和可比较 JSON 差异；formal_adoption/readiness/runtime_verified 均为 false。
- 初次冻结的 `runtime_final_05` 离线验证为 17 项、0 failure/error/skip、0 真实模型调用，早期失败原样保留。正向装配 seam、本地 synthetic stdio 均明确标注，不作为真实准入阳性。3A wrapper 经共享重放 owner 保持原接受语义。
- `legacy_wiring_01` 跑了 174 项，包含原 Windows 深路径/准入失败及本轮误选两个不存在测试模块的 loader error。该次有效失败 ID 均位于主线程精确基线 `baseline-native-01`，但模块集合不同，不能声称全套等价或全绿。未修改旧断言。
- 初次源码/schema 哈希见 `logs/ci/2026-11-05/b-route-story-2-5-build/implementation-freeze-07.json`。主线程复核指出的 checkpoint enabled 名称遮蔽与选定正式 Flow 的实际字段义务已补修复及复现测试；新增有效 profile 的真实 OS 子进程，经明确的测试输入装配 seam 进入原 cost/reserve mailbox，并由生产校验器拒绝 synthetic receipt。修复后的最终测试及再次冻结记录另列于验证说明，不改历史报告。
- 复核修复后的 `review_fix_full_10` 完整新套 20/20 通过，0 failure/error/skip，81.172 秒，0 真实模型调用；再次冻结见 `implementation-refreeze-11.json`。修复前复现 `review_reproduce_08` 和定向修复验证 `review_fix_targeted_09` 原样保留。
- 主线程负责原生独立 diff/矩阵检查与三层审核。Sprint/Story 保持 in-progress：目前没有合格真实 3A 阳性输入，真实 AC-1/2/4/5 端到端阳性仍 pending，本轮未执行真实模型外发或 2.6 正式采纳。

## Spec Change Log

- 2026-11-05：按父线程最新继续实施指令，将草案的绝对真实调用暂停改为严格遵守已明确授权和披露范围；新增私有载荷及受保护动作先报告。不改变预算、真实证据要求、禁止读取会话或正式发布的边界。

## Review Triage Log

工程预验收审核已收齐三路；以下逐条裁定先于分组。真实验收仍 pending，尚未宣称原生 Step3 全完成或 Step4/5 收口。

| ID | Verdict | Evidence |
|---|---|---|
| B1 | high | machine 直接传播候选 semantic_error，append 在已有调用后按 append_execution_failure 终止，合法机器业务问题没有进入三次修复。root-review-reproductions 的 B1 已复现；保持 schema/输入/执行故障失败关闭。 |
| B2 | medium | 两个合法选定 Plan 共用来源 ledger；真实 candidate.check 已通过，21 条义务只有20个唯一ID，review 的条数和唯一性不可同时满足。见 B2 原生 fixture 复现。 |
| B3 | medium | format=text 的 docs/plain.json 已通过原生 prepared/candidate owner，但 semantic_domain 因扩展名强制解析并抛 invalid_json。见 B3 复现；仅显式选定 owner/ledger 需要 JSON 解析。 |
| B4 | false | 分支重排确会改义务哈希，但“重置修复计数”不成立：append:262–269 检测新 semantic issue 后拒绝修复，保留原 issue/counter。另记实际存在的误拒绝问题 R1，不以附近缺陷代替本条反证。 |
| B5 | high | B2 来源义务引用 B1 仍被 review_issues 接受；根与依赖账的同名 block 也在 union 中丢失 namespace。原生 fixture 的 B5 复现接受空 issues；需义务对应的可辨识来源支持。 |
| B6 | medium | 两个不同 overall findings 均生成 semantic_review_blocked:overall，append 对两者使用同 issue_key；新问题无法被 repair_new_semantic_issue 区分。B6 已复现。 |
| B7 | high | candidate_artifacts 仅绑定顶层三件产物到槽位；proof_errors 只在每个 binding 自报 workspace 内重放，未把其 binding 对到本槽位已付 reservation，lineage 也只相互比较而未重算 slot。独立 charge 验证不能排除引用另一候选 genuine proof。 |
| B8 | medium | 已 selected 的 generate 在检查早退前执行 persist，3B persist 会增长 active_elapsed_seconds；handoff 序列化该字段，而 operate 要求原 handoff 精确相同，故重复无调用 generate 可破坏后续 handoff 复验。 |
| B9 | high | 两个 native verify-selection 在 legacy 默认路径落入 _load_run，未选中 state 实际均退出0并打印 pending；root B9 两入口已复现。应要求明确3B执行合同。 |
| B10 | high | run_candidate 的 while 只处理 mailbox/poll，没有剩余时间检查。3B 现以完整 generation monotonic 记 run active time，却仅在 reserve 检查；准备/tokenizer/本地验证卡住时不能执行约定时间止损。 |
| E1 | medium | 与B3相同的可达格式反例；root 已用 format=text context 与原生 candidate.check 复验。 |
| E2 | medium | 与B2相同的合法共用 ledger；root 原生 candidate 复现21条/20唯一ID。 |
| E3 | high | selector outcome 完成后、selection-receipt 写入前中断，3B 恢复保留 current；selection:786 将running改interrupted后进入793新尝试，并未要求进展，已付调用会再次发出。 |
| E4 | medium | legacy Capability _remaining_attempt_budget:804 明确 candidate_budget+synthesis_timeout；官方 description supports_synthesis_budget=True。3B把所有候选活动截在2700，未保留原额外1200 synthesis allowance。 |
| G1 | medium | 预核实测试缺口：阳性装配替换 verify_call/verify_reserved_call，真实worker仅负向，直接协议测试绕 capture_binding。缺少生产捕获→binding→reservation 的有效离线 round trip。 |
| G2 | medium | 预核实测试缺口：目前只断言次数/默认值，没有受控时钟、已消费时间下的父预留timeout及实际worker timeout、耗尽拒发断言。需补原路径边界验证。 |
| R1 | medium | B4的实际坏结果：相同 branch 重排令 ID 改变，append:262–269 把它当新 semantic issue 拒绝，既有问题虽未重置计数，却会误拒无新问题的修复。稳定 issue 身份应脱离报告数组位置，同时保全部分支义务。 |
| R2 | medium | 有效 elapsed 可为小数；剩余候选/总时间0.5秒时 max(1,int(min(...))) 仍预留并派发1秒。旧 helper:810会拒绝不足1秒的请求；新路径需要相同拒发边界。 |

完整工程分组及原始复现见 `logs/ci/2026-11-05/b-route-story-2-5-build/root-engineering-review-triage.json`、`root-review-reproductions.json`。修复路由为完成 Step3 缺失实现/测试，不冒称真实验收或正式审核里程碑已完成。

## Design Notes

复用现有状态所有者；stage/profile适配数据与校验，不能因旧形状不合适就另写选择循环。独立语义要覆盖所有Requirement及Flow条件/交接/四部分/来源支持，完整性/共享证据/保留规则由同一结构owner确定性检查，两者不互相冒充。

三轮replacement是原合同，不是提高64或192的理由。保原run共享round、每slot每轮一次及相关事件，稳定issue修复和执行失败各有原分类；没有真实执行数据不得伪造issue耗尽。宿主预约的逻辑调用与provider物理dispatch/费用分别报告，unknown不能记为0。

当前没有真实合格3A阳性材料；模型调用仅在父线程最新明确授权及既有披露范围内执行，新增私有载荷先列明服务/文件类别/内容/次数/用途。可完成代码、离线合同/OS隔离/负向与明确阳性装配seam，必须保留真实端到端验收未验证；不允许把本Story状态收为done并声称真实AC1/2/4/5已通过。用户已委托无人值守技术决定，可独立完成可逆规格/实现，不反复询问普通实现选择；该委托不扩大载荷授权，不能通过换入口规避既有外发限制。

## Verification

### v2 完整数据传输：当前冻结检查点

- x14 真实容量终态与两个原准入保留，原阶段11次结算，campaign46/290；没有重开终态或移植proof。新规则尚无真实当前资格，正式Step3/4/5未完成。
- 通用组件22项测试通过；8个不同集成方法已有通过记录。首轮6通过、两个合成入口因旧夹具固定medium被high门禁拒绝，失败原样保留；只改显式合成响应并重跑两失败方法，两者通过。随后仅调整模型文字，明确摘要校验由host执行；其余codec AST完全相同，只复查受影响的两个方法通过，没有重跑22项或前6项。
- v2保完整字段／类型／键序／数组序／原字符串，严格数据AST、碰撞转义、表／摘要和规范重编码；不是代码执行或业务输出补写。旧none/v1的11份实际prompt及两阶段3A的6文件精确重建，原x14全部222文件哈希不变。3A v5/v6 carrier默认仍为v1。
- 原失败完整字符串请求101801+2000超过96000；最终实现重测为87646+2000，原schema／官方workspace字符串包装／计量公式／1MiB及全部调用、时间预算未改。曾将计量包prompt换成对象的91702已明确撤回为counter-only-invalid，不能作为容量解法。新的实际请求仍逐次完整测量，不能预称未来全部可容纳。
- 独立窄工程只读复核未发现可确认缺陷，不是正式Step4。当前旧3A可按历史字节完整重放，但严格current工具漂移门禁拒绝新资格；需要新冻结下真实审计及两入口阳性，绝不把旧证据跨规则冒充通过。详见root-compact-wire-review-freeze-144.json、root-compact-final-preflight-142/report.json及原始各次测试报告。

### High runtime and lossless citation wire checkpoint

- New executions require high. The actual official ephemeral thread configuration returned
  openai/gpt-6.1-sol / high, readOnly and no tools; metadata probe started zero turns.
  This is runtime configuration, not provider actual-model/reasoning attestation.
- Span-reference v3 retains complete canonical inputs and reconstructs exact source citations
  only in separately verified decoded views. Raw provider output is retained unchanged.
  Historical v1/v2 schema and prompt bytes, literal partial citations and canonical validation remain enforced.
- Root reviewed the complete 11-file production/test/documentation diff. Offline regression
  ran 86 tests: 85 passed; one obsolete test injection hook failed before its mutations ran.
  Only that hook was updated; its targeted rerun passed. Both runs retained unchanged source snapshots.
  The failed result and a permissions-only launch failure are retained, not overwritten.
- Root evidence: root-span-ref-regression-62.json, root-span-ref-drift-recheck-64.json,
  root-high-span-review-65.json and official-runtime-high-config-only/report.json.
  Parent independent offline review reported no confirmed P0/P1/P2 within its frozen scope.
- No real high source audit/3B acceptance or Step 4/5 completion is claimed here.
  Campaign remains charged 11/290 before the next authorized same-scope audit.



### 可选官方运行配置检查点

- 两次 typed v8 均终态 max_output_tokens，间隔 185 秒；各保守计 1 槽，累计 10/290。
  未取得完整 assistant 输出，比较及 3B 未启动；原始协议／失败字节未修补。
- 只在本任务子进程显式请求官方目录默认 low；未设时 description、命令、线程请求和
  原 proof 字节保持原样。实际返回不符在 turn/start 前拒绝，历史重放只读捕获配置。
- 主线程已读全部 6 文件差异并核对安全常量、命令、runner 原执行逻辑不变；独立回归
  34/34 通过，0 failure/error/skip、0 模型，27 份源码前后字节一致。
  证据为 root-optional-reasoning-review-52.json 及 root-reasoning-regression-53.json。
- 官方 metadata-only 核验成功：openai/gpt-6.1-sol / low、ephemeral、readOnly、无工具，
  严格禁止并确认没有 turn/start，模型 turn 为 0。CLI 0.160.1 和原二进制 SHA 未变；
  此为运行时配置，服务端实际模型／物理请求／费用仍未知。
- Story 继续 in-progress；本提交是可回滚运行配置边界，尚未冒称真实 AC 或 Step4/5 完成。



### 显式类型与无损传输检查点

- s25-v8-guided 首次提取终态为 invalid_json_schema，缺 schema_version 显式类型。
  同一逻辑调用内另有四条 CLI 重连通知（输出上限、超时、TLS）；物理请求与费用未知。
  比较和 3B 均未启动，原失败全部字节及计费 1 槽保留，累计 8/290。
- 3A v2 为生产 schema 补等价 string 类型，默认、无 policy 及旧 v1 原样重放；
  3B 闭合 carrier 无损运输未知 JSON，原响应与 canonical draft 分开归档并独立复验。
  review 仅 wire 保守省略 uniqueItems，原 host 仍严格拒绝重复来源 ID。
- 主线程读完本轮全部生产／测试／owner／说明差异，AST 检查与原始失败字节核对通过；
  独立回归 50/50 通过，0 failure/error/skip、0 外部模型，源码前后字节一致。
  证据为 root-carrier-diff-review-44.json、root-carrier-regression-45.json 及其 source 报告。
- 原 frozen intent、正式 schema、默认预算和严格语义门禁不变。此提交为 in-progress
  可回滚版本；同一 v8 合成材料真实验收及正式 Step4/5 仍待实际执行。



### 前一版请求常量检查点

- 3A v1 将已知请求摘要固定为 const；原规范 schema、引文、业务规则及历史 proof 不变。
- 3B 从完整原始请求和前序草案推导 input_identity、stage、ordinal、有序 parent_draft_identities。
- 该版独立回归 83/83 通过，0 failure/error/skip、0 模型派发；22 份源码前后字节一致。
  证据为 root-producer-regression-36.json 及其 source 报告。
- v8 是 5761 字节同类合成材料；原离线见证及候选投影检查按相同原字节显式复用，
  不冒充真实验收。该检查点当时累计 7/290 个逻辑槽，真实 AC 与 Step4/5 尚未完成。

### 可回滚生产端引用指导修复

- v7 完成了六种完成后崩溃用例及停止/退出确认/保留日志启动/重复恢复的离线协议。
  一次真实提取因模型引用偏差一字节被严格拒绝，比较未派发；继续阶段累计 5 槽位。
- 可选 full-block 指导及紧凑模型 workspace JSON 已绑定模式、输入/工具/提示身份和
  精确 proof 重放；默认原字节和原引用/输出校验不变，不自动修补模型输出。
- 定向 8/8；主线程两个受影响模块 73 项，72 通过、1 个 POSIX 平台分支跳过，
  0 failure/error，22 个源文件前后哈希未变。历史 s25-v6 完整阻断 proof 可只读重放，
  当前资格仍因两个相关工具的真实漂移而拒绝。未重复不相关宽泛验证。
- 新模式的本地输入检查证明原业务 payload 完整不变，原真实错误引用仍被拒绝；
  首提取估计 11295、比较已知部分 20176，仍用原 30000 上限，不预称未来真实合格。
- 本次可回滚提交仍是 in-progress 检查点；真实阳性 AC、正式 Step3/4/5 未提前完成。

### 当前授权与可回滚实施检查点

- 用户批准 3283 字节修订材料以及以后同类范围自主修订/验收，无需重复询问；不得
  扩大新类别敏感资料或绕过强制逐次确认。实施中适时提交多个可回滚版本，不合并 main。
- 新继续阶段使用累计 290 逻辑槽位护栏，阶段按原生上限预留，核对真实持久化计数
  后释放未用额度；换材料不重置计数。护栏最初的空标记错误发生在原生派发之前，
  已保存现场、证实零调用、修复并通过离线计数/超限/重复/损坏记录检查。
- 当前提交仅保存已完成离线实现及夹具的检查点，不提前标记真实 AC 或正式
  Step3/4/5 完成；后续按真实结果继续。旧“未授权/需确认”段落是对应历史时点记录。

### 新草案系统离线检查：未外发

- 最新拟议源 `docs/testing/story-2-5-controlled-acceptance/handoff-v5-draft.md` 为 3283 字节，
  SHA-256 `3b0b7288ce82132d246ba86661d915af1076e1838436a946e42151f37c22b7ec`。
  旧已批准源、真实失败及中间草案保留；新源仍无外发授权。
- 已逐项覆盖原 F-001、F1、F2，并修正 v3/v4 离线检查发现的首次 MapReady、内部步数
  挂起、独立观察、调用关联、场景隔离和分型问题。审批状态保存在外部元数据；
  只有标题是 context，7 个强制段落有完整分类、原文和 scope 关联。
- 原生 prepare/account 完成机械记账，分离逻辑检查器验证 68 条合成见证轨迹并拒绝
  22 类负向变异；不等同独立 LLM 审核、生产执行或真实语义准入。源码未改，复用此前
  针对性测试；本轮模型调用为 0，未创建新 audit 或合格 3B prepared。
- 首提取估计 8979 tokens，比较已知部分 19485，后者不含未来真实提取输出。
  原 30000/96000、1 MiB、时间和调用预算未变，逐请求超限即停；19 仅为单批次
  无修复计划，290 仍是原生上限，新 B 值尚未知。完整离线报告及范围为
  `logs/ci/2026-11-05/b-route-story-2-5-build/v5-systematic-offline-02/offline-review.md`。
- 冻结意图未变；真实阳性 AC 与正式 Step3/4/5 仍未完成，Story 保持 in-progress。

### 855 字节澄清材料获批后的实际结果

- `s25-clarified/audit-01` 已完成两次真实宿主逻辑调用，但 F1 为来源状态背景误分类，
  F2 为“首次能够交接”的时机仍缺可观察边界；planning_eligible=false。
  两项问题均属于根线程编写的测试夹具/投影准备，官方调用配置实际工作正常。
- 已按失败即停停止；没有启动两个 3B 入口，也没有自动外发重试。Story 两轮
  合计 4 次逻辑模型调用，本轮 2 次。原始 proof 已只读重放，原生 planning.prepare
  拒绝该真实未准入输入，原审计文件和原 855 字节源未变化。
- 证据入口为 `logs/ci/2026-11-05/b-route-story-2-5-build/approved-clarified-real-01/closure.json`。
  本地修正投影保留标题状态为 context，并显式保留 F2 unresolved，未将结构记账
  冒称语义准入。另备 `docs/testing/story-2-5-controlled-acceptance/handoff-v3-draft.md`，
  使用串行调用、CallComplete 和十步边界，仅为未发送、未独立语义验收的新 toy 草案。
  新源需要新范围授权才可外发；未降低语义门槛，未更改 frozen intent。
- 正式原生 Step3/4/5 仍未完成，Story 为 in-progress，依赖 Story 未启动；
  未为未修改的生产源码重复运行已通过的离线测试。

### 2026-11-05 已批准真实验收的实际结果

- 用户批准的原 132 字节测试源经官方 Codex/ChatGPT 完成两次宿主逻辑调用，
  `s25-positive/audit-01` 的完整真实执行 proof 已只读重放。原文 SHA-256 为
  `7a49d2eda9e57b1a45ff227380ece083afdfcae5ed0c71588bf13acc4c917d22`。
- 真实审计 finding `F-001` 指出接受/返回完成边界及重启时点未明确；
  `execution_complete=true`、`independent_audit=true`、`planning_eligible=false`。
  原生规划 prepare 确认拒绝该输入，零新增模型调用，原审计全部文件哈希不变。
- 按已批准的失败即停条件终止本轮，未启动两个 3B 入口、未自动重试。
  290 是上限；实际 2 次，原单批次无修复计划 19 次。服务端实际模型、物理请求数、
  费用仍未知，独立返回的 `openai/gpt-6.1-sol / medium` 仅为运行时配置。
- `logs/ci/2026-11-05/b-route-story-2-5-build/approved-real-audit-01/closure.json`
  保存请求/输出哈希、计数、finding 与负向准入证据；同目录 855 字节的澄清草案
  仅供审阅，没有发送或替换原材料。新的资料范围及新一轮真实执行仍需另行批准。
- 最终受影响生命周期测试 6/6、独立缺口复核 4/4、planning-input 34/34 通过。
  复核范围及历史失败如实记录于 `root-engineering-closure-26.json`；不冒称完整
  123 项或旧基线 131 项全绿。冻结意图不变；真实 AC1/2/4/5 未完成，正式原生
  Step3/4/5 未完成，Story 保持 in-progress，后续依赖 Story 暂不执行。

**Commands:**
- 从nx运行 `& 'C:\Program Files\Python312\python.exe' -I -S -B ..\run_story25_tests.py <unique-label> test_b_route_planning_runtime`；复用已验证的任务私有依赖/编码缓存，短私有TEMP、默认Windows命令编码、UTF-8证据，必要时提权但不改ACL。新harness只换Story25证据命名空间；本轮实现代理仅离线测试，任何真实调用由主线程先核对已授权载荷/服务/用途范围，新的私有载荷先报告。
- 实现冻结后主线程核对实际完整diff、每矩阵行真实执行通过、源码前后哈希，再跑相关3A/3B、原OS worker/预算/selected checkpoint/CLI/receipt及明确旧门禁；保所有失败，不能改旧断言取绿。已验证的旧baseline失败单列对照，不说全套绿。
- 原生三层审核逐条裁定并验证；独立review可用离线内存变异确认关键断言。缺少合格真实材料／证据时，真实端到端验收保持pending，后续仅按既有明确授权及实际证据更新；不运行 `run_real_story22_acceptance.py` 或更换入口重试。

## Smaller atomic-record fixture checkpoint

The v9 synthetic reward/restart source is a NEW test fixture with one atomic Commit(R)
record. It is not equivalent to v8's two-record semantics, and it does not make any v8
audit or game scenario pass. Story 2.5 original AC1-5 (B-route epics lines 946-993) concern
independent planning admission, native isolation/budget/selection and proof integrity;
they do not require the locally invented six-prefix/two-record game schedule.

The current source remains complete and nonempty, with seven first-projection atoms,
an explicit entry/guard/execution/finalization Flow, recovery handoff and resource owners.
Independent offline consistency checks cover 34 call witnesses, 22 restart controls and
31 rejected negative mutations. These are toy-contract consistency checks, not game
execution or model semantic acceptance. Every original paragraph remains in the first
projection and acceptance intent; no current qualified proof is fabricated or reused.
Evidence: v9-systematic-offline-02/local-state.json and separate-offline-check.json.

Before v9 actual dispatch, the shared campaign is charged 13/290: one high v8 extraction
failed max_output_tokens and one tiny high structured diagnostic passed. Actual provider
model/reasoning, physical requests and billing remain unknown. Real v9 audit and both
3B entries remain pending. Native 2/192/96 ceilings, high, no tools, original transport
and timing budgets, genuine omission/conflict checks and failure-closed gates remain.

## Compact atomic fixture: final scope checkpoint

The v9 high extraction also failed max_output_tokens, charged one host logical
reservation and produced no qualified input; comparison and both 3B entries stayed
unstarted. Its original protocol/output bytes are retained. Shared campaign: 14/290.

V10 is a NEW smaller fixture, not proof of v8/v9 game semantics. It retains atomic
unique reward/return, idempotent accept, both resume states, an explicit four-part
Flow and resource ownership, independent complete UI/journal observations within a
deadline, and both append-crash recoveries with confirmed process exit/start. The
self-added post-completion/extra-cycle schedule is outside this fixture. Story 2.5
AC1-5, real omission/conflict detection, official high/no-tools bindings, original
OS workers, selection/checkpoint and native budgets are unchanged.

Current offline evidence: v10-systematic-offline-02. Its nine call witnesses and three
restart traces were checked for this source. The 29 applicable unchanged atomic-rule
negative cases are explicitly REUSED from v9, not claimed newly executed. Two
post-completion-specific negatives were excluded. This is toy consistency only,
not game execution, independent model acceptance or a qualified prepared input.
Only after a new current real 3A proof may either native 3B acceptance entry start.

## Versioned producer subset and first-error stop checkpoint

The v4 producer-only string-constraint subset and first-observed output-limit stop
have been independently diff-reviewed across all seven changed files. Implementer
ran ten targeted methods; root ran the seven existing stdio methods excluded from
that set: all 17 distinct methods passed, with no network or model calls. The root
run's 28 runtime/schema/test source snapshots were unchanged. History check 74
reproduces original none/v1/v2/v3 schema/input/prompt bytes and leaves canonical
validators, replay, high configuration and all actual audit bytes unchanged.

This does not show v4 actually solves the provider failure. Shared campaign remains
16/290; no current qualified input or real 3B model call exists. Runtime configured
high is required; provider actual model/reasoning, physical requests and billing
are unknown. Root will first compare one tiny changed-schema diagnostic, then use
the unchanged canonical source audit only if that succeeds. Original failure and
budget records remain, and no native selection/checkpoint budget is increased.

## Actual high two-phase audit: retained finding and journal-scope clarification

The v4 real extraction and global comparison both completed under high and their
original bindings/canonical validation. Actual comparison measured 25,515 input
tokens within the unchanged 30,000 limit. The report is execution_complete=true,
planning_eligible=false: F-001 asks the source owner to make test/journal lifetime
explicit. Two host logical reservations were charged; campaign now 19/290. This
is a genuine retained semantic-blocked result, not a passed 3A/3B acceptance.

The source now explicitly provisions a distinct empty J for each scenario, permits
a different journal at scenario boundaries, and forbids reset/share within the
scenario. Full original projection and acceptance intent were regenerated through
native prepare/account; no old finding or model output was edited. Current offline
check: nine call witnesses, three restart traces, five distinct scenario journals,
two newly rejected scope negatives and 29 explicitly reused atomic-rule negatives.
This is toy consistency, not game/model acceptance. The revised source requires a
new real two-phase proof before either 3B entry can start.

Controlled diagnostic note: the raw source catalog hashes differed only because
fetched_at changed. All models, actual restricted catalog hashes and thread config
were equal. This supports the producer subset observation, without identifying
which keyword caused the failure or asserting backend model identity.

## Worker dependency visibility: verified task-only correction

The first original MVG run v10 stopped in its OS worker before any model reservation:
current audit identity differed only in optional package visibility. Native startup
automatically exposed the user site (pytest and its optional dependency metadata),
whereas the isolated coordinator had not exposed it. The strict drift gate correctly
rejected this context; the failed run, worker log and zero charged count are retained.

Only the NewRogue child process environment now adds PYTHONNOUSERSITE=1. Explicit high
and the existing approved dependency paths remain. No installed/global Python,
production source, authentication/network configuration or other project was changed.
Offline probe 80 shows exact identity equality with this process scope; actual worker
verification 81 reloads the same complete current prepared input and qualified 3A
proof with sockets/model calls blocked. The already-passed 3A is reused, not rerun.

A controlled corrected-environment attempt uses fresh native w10/d10 directories,
preserving failed v10 and unused c10 unchanged. Old model reservations were zero;
original 192/96 native ceilings and shared 290 campaign remain, charged 21 before
continuation. This is a material verified startup correction, not a reset of paid
repair/replacement budgets or adoption of a failed candidate. See record 82 and the
task-orchestration snapshots. Full native 3B acceptance remains pending.
