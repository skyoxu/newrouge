---
title: 'Story 2.5：Task 无关候选的独立准入与有界评选'
type: 'feature'
created: '2026-11-05'
status: 'done'
baseline_commit: '9bc2738111354e708ecfde7c8be0b3f2eba44ff0'
route: 'dispatch'
review_loop_iteration: 5
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

- 2026-11-07 回环2当前对账：独立 r26 已整合 AST/完整编码共享工作预算、内层 lossless 分配前门禁、三类原子元数据发布及多次前缀恢复、写入前只读见证、仅传原镜像的动作作用域、Windows 停止握手与宿主故障旁路证据、精确 host 源守卫、legacy 累计部分修复及真实原子路径容量。原 provider/protocol/high/no-tools 与全部模型/调用/时间阈值保持；未读取 UI 速度设置，未开启 Fast。
- Root 已有184个不同方法的实际通过记录，来自明确记录的多个源码屏障，而非一次整套测试。runtime-07 为32/32、34次直接合成进程启动；hardening-08 为63/63，含源清单8、写入前见证/材料作用域负向2、selector16、原 hardening29及三类发布恢复8。另有原真实 R5 两份源码对当前纯 host 守卫的正向比对，以及已去重的包名 CI 冒烟1项。CI两个 PowerShell 块仅作语法解析；无完整 YAML 解析器或托管 CI 执行记录。
- 精确旧329024字节 packet 的 compact 摘要与规范重编码通过，政策计量88319616/100000000；完整 wire 在展开/缓存保守上界74033516处拒绝，阈值仍67108864。该拒绝与全部先前夹具/ACL/路径/发布失败均保留，不能称新策略完全兼容、实际 heap/CPU 耗尽或原 R22 资格失效。当前原生/工程证据继续分开。
- 本轮原始记录、屏障、失败源码与控制脚本已归档在 `logs/ci/2026-11-07/story25-loop2-review-checkpoint/`，manifest SHA为 `5dea17bde220e21014b5880f1c3ebadd2e649a4ce1e1d547075941c2693e3b3f`；对账见其 `summary/report.md`。本轮真实模型调用0，campaign仍79/290、released0，旧unknown与R22资格不改；正式Step4下一轮独立复审和Step5尚未完成，未激活默认B、正式采纳、readiness或运行资格。下面各早期记录仍按历史时点保留。

- 2026-11-07 最新：原 m4 已在冻结 R22/6d4ab1c3cba67bebe98f75c9462af613bf9d739a 下完成三候选准入后的唯一评选及 selected checkpoint；原 V18 07:01:18 UTC 自然 OS0。Root 只读资格命令也以外部 held-process OS0 完成，正式原生 Step 4 现在进入审核，尚未标为 Story 完成。下面旧检查点按其历史时点保留。

- 2026-11-06 V11 当前检查点：原 c4 已通过原生生成与两候选比较，22:17:14 UTC 返回 `phase=generated/selection_status=selected`，选中 candidate-2；proposal SHA 为 `bf124b112bfc7b7c2ab13a014c1d7031397c0241095ed7a42fc3bf982fc68636`。原子 checkpoint transaction 为 `70e87097eb4a8b11c75ccc438cb3c99c1f6a52c132949c5c6fb2e974313e2899`。这是真实选定检查点，不等于完整资格或 Story 完成。
- 第11号 selector 原始结果 completed、exit0、47秒；原第6号已知失败、旧 v15 unknown 和全部账本均保留。累计已付费或未知逻辑占用为 66/290，release=0，完整 MVG192 预留保持。官方返回的执行线程配置为 high、无工具；服务端实际模型、实际推理档位、物理请求数及费用仍未知。
- 原监督进程4972及子进程6016继续执行选定后的完整 native 校验；本记录时尚无 qualified terminal 或真实自然 OS exit 回执。m4 未启动，正式 Step4/5 尚未开始。后续 V16 控制器仅离线审核并归档为 `6469e17d4f35245600f4b6db517d156b242b33da`，真实性能未测；实际启动仍以前述合格终态及 held-handle OS exit0 为前置。以下执行记录保留原历史时点，不代表当前终态。

- V4 当前续接（2026-11-06）：`s25-v4-comparison-successor-high/compare-01` 已以一次新的比较真实完成，231.016 秒、exit0，原提取和新比较的完整原生 proof/current 校验通过，8 个来源块无 semantic blocker，planning_eligible=true。仅证明当前来源审计资格；旧 v15 比较仍 unknown，其 31 文件与 v3 权威字节未变，没有退款。
- 截至该审计终态累计 55 个已付费或未知逻辑槽位，保留 240/290 原 guard。官方完整协议返回 openai/gpt-6.1-sol/high 运行时配置；服务端实际模型/推理、物理请求及费用仍 unknown。实现提交 `822492644b70151283a8de60285ec2c84ca247cd`，终态证据提交 `079287a45cef010fc5789fbf37ff8d450efe385c`。
- 原生 3B 冻结输入 i4 已准备，identity `sha256:ca51aa929b8a29089c302f08eb9c0a7bfd0876026b31d5d7b2dee9b7c939fb48`。c4/m4 首次完整 wrapper 估算分别 64599/64596 tokens，另保留 2000，均未截断且低于 96000。Capability c4 已以独立永久 claim 启动，原 Cap96 保留，当前尚不宣称候选/选择合格；MVG m4 尚未启动，须 Cap 真正合格且实际 k<=43，topup7+k<=50 才能完整预留 MVG192。
- R7 `d7d0dad0` 的 c4 第4号独立审核已真实完成，31项 approved、findings为空；第1候选由原协调器正式准入。第5号为第2候选真实完成的 batch，输出 raw SHA `ffac881cfef08028ac5d7ca25b433dd1493b1f041449f70bad8b6e9fb2f25423`；第6号 synthesis 原协议明确 failed/invalid_json_schema（数组 const），并非 unknown。全部6槽保留，当前累计61个已付费或未知逻辑槽位，没有退款。
- 独立 R8 工作分支 `build/b-route-synthesis-recovery-2026-11-06` 保存 `5ac0c54d` 与 `f828d861` 两个可回滚提交；显式版本化 provider schema 仅编译传输约束，原8个语义 owner 函数源码不变，完整原 schema/有序草案仍由宿主严格验证。source epoch 保留 R7 原 proof 及已完成 batch 的真实身份，新执行绑定实际 R8，不重签旧结果。原生 synthesis-1 恢复记录已 committed，后续链校验进行中，尚无新的模型调用或最终选择资格。说明见 `docs/workflows/b-route-known-synthesis-recovery.md`。
- 时间核算沿原生合同：第2候选已耗251.25+408.219=659.469秒，在2700候选池及1200综合池公式内剩3240.531秒，单次综合仍不超过1200及worker剩余期限。`2700-run.active_elapsed` 得到的299.593秒不是该原生候选剩余公式；全程2400.407秒宿主 active 时钟保留且不重置。
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
- [x] `_b_route_planning_runtime.py` 与原输入/候选owner：明确阶段化数据服务与身份合同，完整请求/seed/原稿传输、当前性与累计delta/语义门禁、必要只读handoff；原raw/source/schema/模型协议不伪造，source_gap阻断资格。
- [x] `_mvg_capability_append.py`、`_mvg_capability_generation.py`、`_mvg_capability_worker.py`：把3B数据服务接到原控制循环/OS进程；持久预算写前预留，worker无提交权；窄replacement申请保三轮与稳定槽位，旧默认行为不变。
- [x] `_mvg_capability_selection.py`、`_mvg_capability_checkpoint.py` 及 planner相关函数：同一协调器独立父机复验／比较／唯一原子selected checkpoint，固定winner、完整seed/prefix、unknown提交及失败关闭；默认预算与epoch/reopen不重置。
- [x] `_planning_execution_binding.py`／原3A执行校验：共用可复验原始执行绑定，精确JSON与真实runtime配置；正式3A原收据接受语义不被放宽。manual/external输入不能凭结构报告取得真实执行资格。
- [x] `plan_capabilities.py`、`plan_mvg.py`、`dev_cli.py`、`dev_cli_builders.py`：明确3B阶段与prepared/run绑定，两入口保旧默认与预算；最终验证只复验不换winner，输出可定位handoff，日志以外不写正式plan/catalog。
- [x] 新 `scripts/python/tests/test_b_route_planning_runtime.py` 及相关真实OS worker/预算/receipt/CLI/checkpoint回归：逐行验证矩阵。覆盖实际子进程边界与无提交权、少于三MVG候选不调用selector、预算和替换不重置、干净新lineage、不完整/错序草案与容量、schema/哈希/真实配置/协议篡改、同ID不同JSON类型、失败不换winner/不无进展重发、断点/占用/unknown outcome、旧legacy门禁。阳性seam与真实请求分开标注，无公共测试bypass。
- [x] `docs/testing/story-2-5-independent-admission-selection.md`、原owner说明与原生spec/sprint：记录格式、入口、实际结果、计数范围及真实阳性缺口；完整图和身份留给2.6正式采纳，不推送。

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

### 2026-11-07 原合同正式三层审核：第1轮

三层全部返回后，先逐条裁定再分组。与旧工程行不是同一位置/同一claim，未冒用carried。Floor算式行不是缺陷。以下为独立逐条裁定；R1为核实B9时另发现的问题。

| ID | Verdict | Route | Evidence |
|---|---|---|---|
| S4-B1 | high | bad_spec | execution_transition:205–217 仅比较8个函数，遗漏 semantic_domain/source_key；Root用原函数AST和只把返回改为 flows[:1], source_blocks 的内存变异，门禁仍成功。多Flow完整独立义务可被漏算；committed manifest只约束字节，未补语义依赖闭包。见 semantic-helper-flow-truncation.json；不将该局部复现冒称整条native攻击。 |
| S4-B2 | false | reject | 该接口文档122–128绑定“此安装版本”，没有签发已人工审核目标的凭证。既存reuse在193–200绑定完整old/current/transition，漂移即拒；132–133保持同一high语义合同，177/217–219仅复用原提取，新compare仍真实执行。当前B完整committed源的允许变更集又排除audit/source/recovery，未证明所称旧资格跨身份接受。 |
| S4-B3 | medium | bad_spec | selector_recovery:476–513 多文件prepare可在claim/record/run后、committed前中断；484/499拒占用namespace，389–395要求完整marker，现有Root capture亦先validate不能补此窗口。保账安全，但无合法前进路径；需显式原事务pre/postimage恢复，不重发模型。 |
| S4-B4 | medium | bad_spec | authorize:543–546先独占写intent，selection:603–622后提交row13；中间中断可留下12 calls+intent，再授权xb拒绝。不能凭12+intent就推断没有外发，需原owner证明提交阶段、保守占用及有限幂等完成；现有入口未提供。 |
| S4-B5 | medium | bad_spec | selector_recovery:452–473自身run.json.UUID.tmp可在replace前遗留，而324–337 finite新增集合将其判unknown_new_file；无journal provenance/reconciliation。需逐字绑定原事务临时物、保留隔离证据并拒陌生文件，不能删除或笼统放行。 |
| S4-B6 | medium | bad_spec | compact_literal:185–190枚举重复prefix并逐字符比较，仅v3分支514–515触发；selector_prompt先render/dumps，selection:978才容量检查。真实受治理业务数据仍可触发超线性编码；未证明本次m4最坏复杂度，也未影响固定v2路径。需确定性工作上限及代表性验证。 |
| S4-B7 | medium | bad_spec | compact loads:667–677先展开phrase/shared再验digest/canonical，v2/v3 earlier DAG防循环不防fanout；_unshare deepcopy/_unpack_text join前无展开预算。输入SHA/receipt限制了信任边界，故不称远程漏洞或既有proof无效；仍须在分配前限制资源并显式区分编码/展开预算，不截断原文。 |
| S4-B8 | medium | patch | planning_common:728–749异常路径先cancel后persist；cancel:632 cleanup-incomplete和633 wait TimeoutExpired可达，且无finally，导致原失败/已捕获输出未持久化。应独立保存原异常与cleanup异常并保partial证据；不能把本次正常成功误称受影响。 |
| S4-B9 | false | reject | 缺host log确写active_elapsed_seconds=0，但所称当前3B恢复时间多发未成立：runtime fail_execution_closed=True，append blocked后selection832–837 terminal，666–679拒重入；独立worker deadline及coordinator555–564单调累计未退款。另按真实的错误0记录新增S4-R1，不以附近问题代替此条反证。 |
| S4-B10 | medium | bad_spec | selector recovery16方法未真正执行磁盘prepare故障矩阵；155–175的intent测试mock validation/read/path/_durable，只证明重复拒绝。已有真实完整成功不能覆盖S4-B3/B4/B5的持久写入窗口；补原磁盘事务注入与unknown保留对照，不广泛重跑。 |
| S4-E1 | medium | bad_spec | runtime:803–807未传repair_check；append:265–266仅存在callback才查修复域，preservation:182–185对read-only seed直接空，machine和完整新semantic审核不能证明未改其他仍合法内容。旧plan-mvg合同第85行明确拒无关修复；需要3B真实owner导出的issue/依赖域及复验。 |
| S4-G1 | medium | patch | Other finding按普通项核实：Windows actual path用capture.communicate，旧test_planning_main_audit_fixes:181–208只mock proc.communicate。gap reviewer短真实child复现旧KB/new produced no output，H静态链一致；应改真实边界注入并保OS回收断言，不仅删测试或sleep30s。 |
| S4-R1 | medium | patch | worker:141–145将无可信host耗时记成0，虽不构成S4-B9所称预算绕过，仍违反真实耗时报告并干扰reserved fallback。缺证据须保unknown/保守原预留，不能把未知写成已知0；成功回执和未知调用费用保持原样。 |

所有survivor再分组：语义迁移依赖闭包（B1）；prepare多产物恢复及故障矩阵（B3/B10）；intent/parent提交恢复（B4）；journal临时物归属（B5）；v3编码工作界（B6）；v2/v3展开预算（B7）；3B修复域（E1）；cleanup证据持久化（B8）；Windows真实中断测试（G1）；未知耗时（R1）。存在bad_spec，按先级回到非冻结实现计划，patch项保留于KEEP，不在此轮越过回环直接收口。

保留指令KEEP：原R22生产源码、完整V18自然OS0/qualification、原3候选及原13调用、累计79/290、旧v15 unknown和全部失败原字节、完整源/业务/语义检查、high与原预算均保留。用户明确要求保存冻结现场，因此不原地反转已作为真实证明根的生产树；在独立后继工作分支重新导出修复，旧证明仍只归其原producer，不重签为新规则。Step5仍pending。



### R35 正式三路逐项裁决（回环5）

全部三层返回后先逐项裁决、再按根因分组；原 findings 均保留。

| ID | Verdict | Route | Evidence |
|---|---|---|---|
| R5-B1 | false | reject | common:638 的 strict UTF8 私有 helper probe 确实抛线程异常，但不是当前公开调用路径。唯一生产构造点 common:793 来自 Popen 的 errors=replace；execution_log 路径则显式 text=False、删除 encoding/errors。坏字节不会在这些真实调用的 decode 中抛该 UnicodeDecodeError。两个 reviewer probe 导入项目源码，另行如实登记，不算有效协议验收。 |
| R5-B2 | medium | defer | carried R2-B7：同一 Windows output reader 累积 chunks 后 join，无 stdout 字节上限；代码仍与原记录一致。保留 medium/defer，跳过重复验证，不再修补或登记。 |
| R5-B3 | medium | defer | carried R3-B7、R4-B5：同一 stderr.readline 在 2MiB 保留门禁前分配完整行；代码未变。保留原 verdict/route，跳过重复验证，不重新登记。 |
| R5-B4 | medium | defer | carried R3-B7：同一 stderr 循环逐行 sum(map(len, stderr)) 的重复扫描已包含于原记录；代码未变。保留原 medium/defer，不重新验证、修补、登记。 |
| R5-B5 | medium | bad_spec | repair_scope_errors:754 将 admission_machine 返回的第一个错误当完整集合。candidate.check_graph:270–277 顺序检查 ui 与 human_verification；schema 允许 responsibilities=[]，业务检查拒绝 applicable+空责任。修复已有 UI 缺陷可显露原 human_verification 缺陷，新旧首错误集合差会误报 repair_new_machine_issue。须区分真实新增与已有被遮蔽缺陷，同时继续拒绝不可证明的新增错误和越界修复。 |
| R5-B6 | medium | defer | MVG remaining_time=None 导致 worker 生命周期无整体 deadline；模型级 timeout 不能终止模型外 preparation 卡死。已只读核对 baseline 9bc 的 selection:602/run_candidate:130/153，原实现同样没有 worker 生命周期 timeout；属于既有宿主存活风险，不是本轮新引入。新的限时/unknown 终止合同需独立处理；本次 bad_spec 使下级入口暂不执行，尚未追加 deferred 登记。 |
| R5-B7 | medium | patch | run_gate_bundle 的专用 PR/硬门禁选择确实漏四个 codec 模块共57方法。当前普通 PR 工作流未另外执行它们；影响被修改的 codec 将来回归。最小修正是补既有选择和维护断言，不新增公开入口。 |
| R5-B8 | medium | patch | 同一 selector 漏四个 source audit/reuse/recovery/policy 模块共77方法。只有一条旧固定分支工作流执行 source_audit，不覆盖普通 PR/main，也不含其余三组。补维护选择与断言；不把历史覆盖当当前执行。 |
| R5-B9 | low | reject | 直接固定版本但 transitive closure 未 hash lock 属实；记录 pip report 不等于锁定。已沿实际调用检查，无正式 hermetic closure SLA 或已发生的 resolver 漂移故障；未来罕见兼容漂移的完整跨平台 wheel/hash 锁需要持续维护，超过直接修正。按 low 且日常不易触发、修正复杂而拒绝；不声称 hosted CI 或安装通过。 |
| R5-B10 | low | reject | 72MB diff 中归档重复使代码审查更费时属实；本次已按原字节和逐文件哈希区分1253个历史相同段与89个变化段，未观察到功能失效。建立外部 artifact 服务/删除历史证据或仓库去重并非直接修正，日常代码消费不读取这些归档；以 low/复杂且罕见的开发体验问题拒绝，不删除原件或外传。 |
| R5-E1 | medium | defer | carried R2-B7：同一 stdout chunks/join 无限保留，原记录与当前代码一致。保留 medium/defer，跳过验证，不再修补登记。 |
| R5-E2 | medium | defer | carried R3-B7/R4-E1：同一无界 stderr.readline 分配，原记录与当前代码一致。保留 medium/defer，跳过验证，不再登记。 |
| R5-G1 | medium | patch | verification-gap 预核实证据按原生规则直接采信：handoff:2241 的 changes_from_selected 没有 distinct-candidate 完整交接断言；已有 assembly/protocol 使用相同内容，json_delta 单测只查非空，改成交接[]仍可通过。补真实完成选择后逐候选对 winner 的精确 path/before/after 断言，不重做已准入真实候选。 |


### R40 正式审核逐项裁决（pass 6，回环仍为 5）

三层全部返回后先逐项裁决，再分组。补丁未完成前不作正式验收。

| ID | Verdict | Route | Evidence |
|---|---|---|---|
| R6-B1 | medium | defer | app_server 的两个 reader.start 在 RPC try/finally 之前；资源耗尽导致 start 抛错时，已创建的子进程和首个线程绕过清理。原基线已有同样启动顺序，并非本次改动引入；需独立生命周期修复及启动失败测试。 |
| R6-B2 | medium | defer | carried R2-B7/R5-B2：同一 Windows 输出 reader 无界累积并 join，现代码仍与原记录一致；沿用原裁决，不重复验证、修补或登记。 |
| R6-B3 | medium | defer | carried R3-B7/R5-B3/B4：stderr 的无界 readline 和逐次 sum 都已登记，现代码仍与原记录一致；沿用原裁决，不重复验证、修补或登记。 |
| R6-B4 | medium | defer | live 仅累计服务端行，而 replay 对含客户端 prompt/schema/host 元数据的完整序列化 transcript 用同一上限；因此完成后仍可能因完整体积失败关闭。原基线已有同一计数差异；无虚假成功或退款，但会损失已执行工作。 |
| R6-B5 | medium | defer | 终止 helper 在直接子进程已退出时返回，reader 取消不等于所有继承管道的后代都终止；现测试也未证明这一点。原基线的同一 helper 已如此，需独立拥有进程树的生命周期设计，不能把当前有界 reader 退出说成后代清理证明。 |
| R6-B6 | medium | defer | block_byte_span 对每个 block 重建完整源文件的字符到字节映射；新 span_table 仍调用它。原基线 make_input 已逐 block 调同一完整扫描，故 O(B*S) 性能问题原已存在；大文件/多块会延迟审计，应单独缓存每份冻结源的映射。 |
| R6-B7 | medium | patch | 维护 selector 的完整列表及三个实际 CI 调用者均未执行 recovery_funding 模块；现有维护路径会漏掉资金独占、unknown、结算及并发回归。最小修复为加入完整模块并补维护断言，不改预算或入口。 |
| R6-B8 | medium | patch | 专用 workflow 的 path filter 虽提到 mvg_capability_worker，但执行 selector 没有该模块，仍不执行现有 worker 提交/复用/中断回归。最小修复为加入共享完整模块及维护断言。 |
| R6-B9 | low | reject | carried R4-B9/R5-B9：同一依赖安装行仍只固定直接版本而不锁全部传递依赖；沿用 low/reject。未发生已证实的解析漂移，完整跨平台 hash lock 超过直接修正且日常罕见，不重复验证或增加复杂性。 |
| R6-B10 | medium | defer | live/replay 使用普通 json.loads，重复键会覆盖且可接受非有限常量；精确协议语义可在解析前丢失。原基线已有相同解码方式；原字节哈希仍保留，不能据此声称严格 JSON，需独立为两个入口增加严格解码和负向测试。 |
| R6-E1 | medium | patch | 可达 schema 合法 handoff 连接两个已有节点但缺 graph edge，canonical check_graph 返回 handoff ID 的确切业务诊断；repair_domain 无该 ID 映射，repairability 在重试保护区前抛 unresolved。最窄修复仅对已经重新验证为原宿主 finding 的这一精确 predicate 返回不可局部修复，走既有有限替换；其他未知、身份和 schema 错误继续抛错。 |
| R6-G1 | medium | patch | verification-gap 已预核实，直接采信不复查：现序列测试手工注入 machine_repair_check，生产 generate_append 的接线被删仍不失败。增加真实生产调用路径的 UI 缺陷→原已隐藏 human 缺陷→最终准入测试，保留账本并断言未替换；不能仅做 AST 或重复手工 callback 测试。 |

## Spec Change Log

- 2026-11-07 回环5实施内澄清：R5-B5 最小纯 owner 重构例外仅限 candidate.check_graph 的原 Flow-local 前置谓词抽取及 append 的内部机器修复回调接线。旧日志中 canonical AST 逐字保持要求对此二函数明确例外，行为/接口约束与其余 canonical 函数不放宽。避免为了保持字面AST而动态重建 code/globals 或复制业务规则。KEEP：原断言顺序、首错误诊断、真实 unique/resolve 和严格准入；原旧 producer/验证器/资格不改写；Root 针对重构和真实 append 正反路径验证。

- 2026-11-07 回环5：R5-B5 发现修复首个机器业务缺陷后显露旧缺陷被误拒；补充非冻结修复合同，必须用真实原始候选谓词证明既有/新增，不能把首错误当完整集合；R5-B7/B8/G1 的较低入口在本回环并入计划，覆盖CI维护和有区别候选交接。避免通过简单放宽错误集合而接受新缺陷。KEEP：R35 当前45项实际通过和732源文件冻结、失败夹具和原记录；fresh provider policy、live high、immutable/source/schema 门禁、局部修复/clean replacement、原子初始化、私有 CI 环境；R30原80项及之前各源纪元证明；原R22/MVG和R10/Capability真实资格、原候选/3A proof、旧unknown、79/290/released0、原预算/claim/锁/稳定ID；原资源容量门禁不提高、不截断；high/无工具、Fast和1.5倍不启用、无main合并/推送。原stdout/stderr carried不重复处理。

- 2026-11-07 回环4：R4-B1/B2/B3/B4及GO1修正fresh producer策略、live high、真实机器业务问题替换、完整初始化发布及CI私有tokenizer环境；B7/G1/B8补维护选集和直接触发路径。避免重现已经实际失败的provider schema形态、默认effort混入、业务问题在替换前抛出、无run.json的权威半目录及缺tokenizer门禁。只改非冻结计划。KEEP：原R22/MVG与dc245b3/Capability各自真实producer、13/11逻辑native记录及原三候选/两候选、79/290且released0、所有unknown/失败/原预算/阶段时钟/claim；R25/26/30原分支与80项分源纪元实际通过、两个完整离线协议结果不重标为当前原生资格；原资源门限8MiB/64MiB/1m/128/100m及96k总门禁/70k未来分段、96/192/64/三轮限额；11关键canonical函数、原3A proof、完整来源/审计/遗漏冲突检测、high/无工具/Fast关闭/不合并main。旧stdout及stderr后续项已经一次登记，不重复。

- 2026-11-07审核回环3：R3-B1/B2补全实际输入及selector资源前置预留；B3/E1稳定问题账户与完整review证据分离；B4无局部owner业务阻塞进入原有界clean replacement；B5/E2与B6保全主异常及独立清理；B9/B10/G1/G2接通必要CI检查和路径。各坏状态见原逐条表。KEEP：原R22/MVG及dc245b3/Cap各自producer、原候选/回执/unknown与79/290；原全部失败字节、原8语义owner及当前11关键段、原限额/high/无工具/Fast不操作/不合并main均保留。独立r30后继重导出，不反转冻结原现场，不给旧proof改签新代码资格。

- 2026-11-07审核回环2：R2-B1/B2/B3/B4/B5/B6/B8/B9/B10/E1/E2触发非冻结计划重导出，修正原事务多次中断与发布、全链资源门禁、宿主取消/异常保全、原子临时路径及legacy进展；R2-G1 CI补丁与既有stdout风险延后条目保留。已知坏状态见逐条证据。KEEP：原R22全部真实资格和unknown不改；10398及102个分纪元通过方法、原329024字节兼容性、原100m/资源与模型额度、高推理/无工具/不合main均保留。使用独立后继工作分支，不原地反转任何冻结producer或原真实证据；不把准备/静态/旧资格重签为新current资格。

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

### R25正式复审逐条裁定（审核回环2）

三层全部返回后逐条核对，再分组；与旧行不是同位置同claim的未冒用carried。检验缺口层按规则信任其预核实证据。

| ID | Verdict | Route | Evidence |
|---|---|---|---|
| R2-B1 | medium | bad_spec | selector_recovery:608–622 将每个操作的所有临时前缀放入唯一 evidence.bin；第一次保留前缀A后再次写tmp并中断为AB，第二次核对要求A==AB而拒绝。两者均为可信after前缀，现无前进路径；保留所有旧字节及nonce/前后像验证。 |
| R2-B2 | medium | bad_spec | selector_recovery:632–635 调_durable(exclusive=True)；455–463在最终journal路径直接xb/write/fsync，非原子发布。中断留下半JSON，_journal:507先严格读取而reconcile:745–746依赖它，尚未触碰目标也无法合法关闭。需原子发布和可信未发布阶段恢复；不能从缺journal推断未知请求未执行。 |
| R2-B3 | medium | bad_spec | compact.loads:932–935 只先限制8MiB，再完整ast.parse后数节点。约两百万个短标量可低于字节限而先建超百万AST；node/depth拒绝执行过晚。需在完整AST构造前做有界语法预检，不执行数据或改变合法规范字节。 |
| R2-B4 | medium | bad_spec | compact._share:550–585 对每个容器多次_literal全子树，_EncodingWork仅在后继_pack_text创建。深链加大叶字符串可满足64MiB/128深度输入而在建Counter键时反复分配大量文本，越过编码工作上限。需共同预算在这些渲染前计量，保持确定性和旧packet字节。 |
| R2-B5 | medium | bad_spec | planning_wire.decode:39在identity检查前调用restore_lossless_context；lossless_context._restore:124–133对向后$mvg_ref做deepcopy，concat也先join。compact预检把内层标记视普通JSON，不能界定其实际展开；向后无环二叉引用仍有指数副本。信任绑定限制了攻击面，不将其称远程漏洞，但新B-route纯decoder仍需展开前检查。 |
| R2-B6 | medium | bad_spec | planning_wire.encode:26–30先lossless_context、restore和多次完整text序列化，后续render才进入compact门禁。大/深材料可在受限codec之前消耗资源；需在该入口和变换阶段共享有界预检，不能截断或拿摘要替代原文。 |
| R2-B7 | medium | defer | 真实既有stdout无字节上限：新Windows reader:597–606累积并join；但baseline9bc的run_isolated_model已用无字节限proc.communicate（包括错误路径），同一噪声runner内存风险已存在。未证明本Story把原有有界流变为无界流；按既存风险延后，不能声称已解决。 |
| R2-B8 | medium | bad_spec | Windows reader:597循环无停止握手；cancel:628单次CancelSynchronousIo后join。若取消落在已返回read1与下一read1之间，当时没有pending IO，线程仍可能进入新阻塞读。先terminate通常令EOF，但子进程已退出/终止失败而仍有写端时不保证；需阻止后续读并有界取消/退出确认。 |
| R2-B9 | medium | bad_spec | App Server finally:485–502的终止/关闭原已无独立保护；本Story新增取消及cleanup_incomplete显式raise又使原protocol/timeout异常被替换。新清理分支必须分别尽力执行并保存原失败及清理诊断，不能把正常completed-turn或旧proof误判为新通过。 |
| R2-B10 | medium | bad_spec | hardening测试已覆盖prepare各操作窗口与reservation在intent后一个窗口；unknown事务没有故障窗口测试。已核对真实磁盘测试与_journal的三种不同postimage：它们的状态/收费断言有差异；新publication和多次中断修正需以最小代表性reservation/unknown故障对照关闭这些义务，不能只重复通用写函数断言。 |
| R2-E1 | medium | bad_spec | runtime.run_location:1740–1742只估protocol名；实际worker->preflight_dispatch->check_workspace_request使用common.atomic_json的runner-input-integrity.json.pid.tid.uuid.tmp。以r25根和30字符合法run_id，protocol252通过而最短该tmp262，早期门禁遗漏自身Windows边界。需覆盖真实最坏文件/临时名而非改变OS设置。 |
| R2-E2 | medium | bad_spec | append:275以repair_check存在作为要求语义issue立刻消失的条件，失败则280退回旧proposal。legacy generation:1373–1377原已传repair_scope_errors（只核修复域），故合法分步改进现在被丢失并仍消费尝试。此为真实旧路径回归，不能仅改spec消除文字矛盾；3B专属策略须显式隔离并保旧进展。 |
| R2-G1 | medium | patch | 预核实Broken-verification gap：新RuntimeTests:87–95检2/96及3/192，但run_gate_bundle:305–389和planning-production-acceptance.yml:70,73的正常确定性selectors不包含该模块，生产脚本:163–184走legacy。profile回归可逃过已检查CI；需把已有确定性3B检查接入维护入口及所需依赖，避免真实模型调用。 |

分组按具体根因分别保留：临时前缀证据、journal发布、AST预构造、共享渲染计费、内层DAG展开、wire入口前置限制、既存stdout资源、读取消握手、App Server异常保全、事务测试缺口、完整原子路径容量、legacy语义进展及CI接线。共同文件或共同改法不充当合并理由。存在bad_spec，回环2；其余不提前处理为完成。

范围局限：生产代码当前路径已追踪，未机械穷举所有归档脚本/测试分支。保留完整diff与各层原意见，不称全面穷举。


### R30正式第四轮逐项裁决与回环4

三路均返回后逐项核实，再分组；carried按原裁决跳过。原三路全文仍在本会话，固定diff/claims与结构化裁决保留于任务日志。

| ID | Verdict | Route | Evidence |
|---|---|---|---|
| R4-B1 | medium | bad_spec | fresh create_run:2044–2062仅启用issue policy，非测试源码仅两类显式历史恢复赋值provider policy；generation_schema仍构造parent_draft_identities数组const，invoke_data:1053–1063不编译，最终turn/start直接外发。原c4第6号原回执对此同形字段实际invalid_json_schema；并非断言每次必败。新run应显式激活已有策略，原canonical host等式及历史回执保持。 |
| R4-B2 | medium | bad_spec | operate:2010、prepare_dispatch:1766和runner_invoke:80均不要求requested high；AppServer:72允许None，validate_execution期望None跳过核对。其他合法前置均满足、ambient unset时可走环境默认effort，违反用户明确high。共同live dispatch在reservation前核对已捕获runner配置与当前执行环境high，保留通用历史验证器按原期望重放；不声称服务端实际推理。 |
| R4-B3 | medium | bad_spec | candidate schema允许同id不同responsibility的两个Command；check_owners:223产生宿主SEMANTIC_ERROR/entity tuple，machine:167–178在身份校验后返回真实business issue；repair_domain:560–600不能映射tuple，append:212在内层try外抛异常，越过225有限替换。必须重新验证宿主诊断及不可变来源边界，只让已证实无局部owner的业务问题有限替换，schema/identity/source/dependency/执行错误仍失败关闭。 |
| R4-B4 | medium | bad_spec | 原生两个CLI经operate:1983–1987先create_run后coordinator_lock；2060–2062逐个发布目录、frozen、run。中断于run写前占用权威目录，重入跳create并在1988读取失败；无父锁或无run.json恢复owner。使用独占临时初始化命名空间及完整发布、竞争不覆盖；不把旧未知或半成品猜作未执行，不删除现场。 |
| R4-B5 | medium | defer | carried R3-B7：同一stderr.readline无限行分配及sum重复扫描，当前AppServer该段仍与已裁决原段相同；保留medium/defer，按原生规则跳过验证，不再修补或登记。原R3实际已一次登记，收据246a0d48a0fdb6b3d8b463616105d2c17069dca020f5e2e9f27ee08293f72621。 |
| R4-B6 | false | reject | 两处len(str(path))确会低估非BMP，但描述的正式恢复越界不可达于当前固定原现场：selector anchor:175–201封闭原artifact_root，普通run_location UTF16最坏尾200覆盖selector165；m1固定原run/append及transition:853–857精确比较真实root，先于672 mkdir。当前固定根为ASCII，不能移到任意Unicode根仍通过原证明。m1保守尾201比原门禁长1不等于真实suffix越界；未建立合法原身份并实际超259的路径，不能据通用算术误差宣称正式恢复失败。 |
| R4-B7 | medium | patch | 专用provider/review/synthesis/partial/path/worker/source-epoch套件未在当前选集或其他workflow选择；对应正式恢复路由仍在runtime:114–127、1096、1161–1176、1223、1361。当前runtime/hardening有部分覆盖，不能称完全零覆盖；但原batch复用、unknown/claim及历史source负例维护检查缺口真实。与G1同选集根因，补必要套件及实际执行记录，不机械重跑全部历史证明。 |
| R4-B8 | low | patch | 专用job paths确遗漏_capability_input_integrity（两个runner直接导入）、_llm_backend及test_codex_isolated_model_runner；直接补正路径。旧quality main PR无paths且hard:451选择同组选集，故并非逃脱全部PR门禁；准确影响是专用依赖环境和归档job未触发。 |
| R4-B9 | low | reject | 直接版本固定但transitive closure未完整hash锁定为真；现有pip --report并always上传已记录每轮真实安装闭包，未观察解析失败或正式要求跨时间hermetic闭包。现实新增损害限于罕见依赖漂移，完整锁生成/更新/平台wheel维护超过直接补正，按原生low且不常见规则拒绝，不把report称锁或声称hosted测试通过。 |
| R4-B10 | false | reject | 当前明确in-review且formal_story_acceptance=false，Step4/5尚待执行不是冒称完成。新wrapper拒原329024B包已按64MiB/100m策略如实记录，不截断；两个完整材料小样本实际Capability/MVG原coordinator协议控制已通过。原R22真实证明仅按原producer解释，与当前离线修复分层；原AC不要求把历史真实run伪造成当前源码新原生资格。后续正式收口必须新索引并区别原资格/当前离线，不编辑旧qualified回执。 |
| R4-E1 | medium | defer | carried R3-B7，同R4-B5：无限长stderr行的同一位置、同一claim、代码仍相同；沿用裁决，跳过再验证，不再次登记或修补。 |
| R4-G1 | medium | patch | 预核实Broken-verification gap：runtime:1169 extra_synthesis改False会使保留两draft/一batch分支不迭代并返回未绑定payload；未选择的test_b_route_mvg_recovery_wiring:106检查ordinal3/原draft/完整chain，其他所选测试未覆盖此激活。信任该层证据，不重做验证。将wiring纳维护选集，保留该测试上游stub边界，不称native准入。 |
| R4-GO1 | medium | bad_spec | 旧hard原已通过test_mvg_planning_contract无skip要求jsonschema，故不能把它说成新增；但新hard选CompactWireTests:1738严格要求真实双tokenizer计数，缺tiktoken时integrity:509返回bytes_upper_bound必不匹配。旧quality/manual job只setup-python，未提供新tokenizer/编码缓存，专用job私有venv不能跨runner供给。需为新增runtime组所有实际CI入口提供同一私有依赖/编码准备或等价隔离，不放松计数断言；尚无hosted执行，不宣称其已失败。 |

## Design Notes

复用现有状态所有者；stage/profile适配数据与校验，不能因旧形状不合适就另写选择循环。独立语义要覆盖所有Requirement及Flow条件/交接/四部分/来源支持，完整性/共享证据/保留规则由同一结构owner确定性检查，两者不互相冒充。

三轮replacement是原合同，不是提高64或192的理由。保原run共享round、每slot每轮一次及相关事件，稳定issue修复和执行失败各有原分类；没有真实执行数据不得伪造issue耗尽。宿主预约的逻辑调用与provider物理dispatch/费用分别报告，unknown不能记为0。

当前没有真实合格3A阳性材料；模型调用仅在父线程最新明确授权及既有披露范围内执行，新增私有载荷先列明服务/文件类别/内容/次数/用途。可完成代码、离线合同/OS隔离/负向与明确阳性装配seam，必须保留真实端到端验收未验证；不允许把本Story状态收为done并声称真实AC1/2/4/5已通过。用户已委托无人值守技术决定，可独立完成可逆规格/实现，不反复询问普通实现选择；该委托不扩大载荷授权，不能通过换入口规避既有外发限制。

## 第1轮正式审核后的当前实施计划（R25，优先于历史实施记述）

这是非冻结bad_spec回环，原用户意图/AC、baseline和预算保持。工作根仅 `C:/Users/Administrator/Documents/Codex/2026-11-05/task/r25`，工作分支 `build/b-route-story25-review-hardening-2026-11-07`，base `6d4ab1c3cba67bebe98f75c9462af613bf9d739a`。R22原producer树及原native/unknown/费用现场必须保持不动；R23分段和R24下游是其他独立工作区，不读写其现场。本轮只修改R25项目文件，禁止main、远程、git提交、凭据/sessions、认证/网络/安全设置。不得启动真实模型、native CLI、真实项目capture或测试；Root独占一切实际测试和真实资格操作。实现者可以用标准库AST检查、静态方法计数及哈希，只报告AST，不冒称测试已执行。不要启动子代理。需新增说明/测试时写中文说明。

### 当前 Code Map

- `scripts/python/_b_route_execution_transition.py`：205–217只选8个函数的语义不变检查；source manifests仍应完整关闭、各历史producer仍按旧规则验原件。新增严格语义helper依赖关闭，不以当前自报hash证明语义等价；覆盖semantic_domain/source_key及其实际语义依赖，允许有意改变的纯运输/宿主故障逻辑不应被伪称语义不变。
- `scripts/python/_b_route_planning_runtime.py`：803–807的3B append未提供repair_check；182–187 read-only seed preservation不等于保留当前proposal无关有效段。旧通用`_mvg_capability_generation.repair_scope_errors`针对另一业务形状，不能直接套用。`review_issues`/`machine`的host生成issue、实际候选内容和原依赖图是修复域的来源；模型rationale不得扩大域。
- `scripts/python/_b_route_selector_recovery.py`：prepare476–513，authorize531–546，_durable452–473，_old_files_close324–337；原父`_mvg_capability_selection.reserve`603–622先after authorization再写row。须扩展原owner的明确版本化元数据事务，不另建收费权威或把不确定请求重发。
- `scripts/python/_b_route_compact_literal.py`：v3 _pack_text185–190可能超线性，loads667–677在摘要/canonical检查前展开phrase/shared；原v1/v2/v3规范字节与旧source producer保留。
- `scripts/python/_planning_skill_common.py`：cancel632/633可抛出，使728–749异常路径跳过persist_execution；保留原异常与cleanup失败两条原因、原始输出和真实时间。
- `scripts/python/_mvg_capability_worker.py`：141–145无可信host耗时却写0；selection.remaining_time30–46已有reserved fallback，不能将未知当已知0。原fail_closed/独立deadline/持续coordinator计时仍保留，未发现当前原生额度绕过。
- `scripts/python/tests/test_planning_main_audit_fixes.py`：181–208中断仅注入proc.communicate，Windows改走_WindowsRunnerOutput.communicate。需真实等待点注入，保真实OS child/reader/终止/wait，短自限fixture取代30秒sleep。
- `scripts/python/tests/test_b_route_selector_recovery.py`：现16方法主要mock边界，无真正prepare磁盘故障矩阵。新增必要on-disk合成故障注入，不访问真实Nx。

### 具体实现与必要验证草案

1. 为S4-B1实现有根据的语义依赖闭包防漂移；至少两Flow helper-only裁剪和source_key/helper-only变异负向；未变化原语义函数/原历史source保持阳性。不得只新增一个self-reported语义hash，也不得宽放source allowlist。
2. 为S4-E1提供3B issue/字段/对象/直接依赖域的严格repair_check，并在准入与相应replay中绑定需要的原before/after材料。当前issue减少且无新机器问题才可接受；无关但仍合法Flow/Requirement/来源/四部分不能被悄改。无法定位域时失败关闭而非放全域。保原三次issue/64槽位/三替换，禁止将retired材料带入fresh。
3. 为S4-B3/B4/B5/B10建立原owner的元数据reconcile：durable journal记录精确preimage/intended postimage、原source/epoch/claim/父row身份及临时物列表；只在原锁/唯一namespace下幂等完成或保留可证明前态。逐窗口测试claim/record/run/committed和intent→parent row，以及部分写入/不明tmp/同时恢复。陌生tmp仍阻断；自有tmp需journal字节与身份闭合后保留审计，不能按名字删除。旧未journal事务若证据不足只能如实blocked，不伪造原证据或自动换ID。
4. 任何可能已dispatch的request都保unknown和全部占用；metadata reconcile本身零模型，绝不释放预留、授权新attempt、重生成原候选。缺parent row不能单独作为未执行证明；必要时保守收费并明确终止，不能把恢复边界描述成平台永久禁止。旧完成的原13请求/旧unknown原字节不改，真实来源仍归R22。
5. S4-B6以确定性工作计数或可证明有界且保规范结果的算法控制v3重复prefix成本，在真实最终计量前可安全阻断；不能隐式换codec、只降低测试数据或抬时间/容量预算。小正常输入输出与原规范逐字一致，真实重复模式必要验证应有明确短上限。
6. S4-B7在join/base64/deepcopy之前以饱和长度/节点/深度分析限制展开，不把wrong SHA/canonical后验当止损。明确版本化资源政策和编码大小/展开大小不同的事实；原全部原文无损保留，超资源明确阻断、无截断。不要武断把展开限制设1MiB误认既有模型窗口；选择并记录可审查的有限宿主资源预算，证明原已合法小样本不变，旧proof仍使用旧producer验证，不重签。新增小体积DAG fanout/phrase链、深度、边界、非canonical负向；不造可能耗尽机器的测试。
7. S4-B8/G1/R1：异常清理失败仍持久化partial证据/原错误/cleanup错误和实际或unknown耗时。中断测试注入当前实际等待点，保真实child回收；补cancel自身抛错的证据持久化测试；缺log不得0，保留reserved fallback和原费用。
8. 只新增/改直接覆盖以上源码的合成测试与中文说明，Root接手后定向执行。保存完整失败、源码hash、method分母，禁止假装131旧baseline全绿。原真实成功V18是历史冻结producer证明；不因本轮离线修复宣称新source已取得真实资格。后续Root会决定历史验原与必要新验证，预算和high不变。

### KEEP与未完成标记

真实当前campaign79/290、release0只是Root最后观察，不是本分支新费用权威或可花额度许可。禁止把它写死进生产判断。所有原native资格、三候选、原13请求/原3A proof/旧unknown由原owner保存；不重跑已准入候选。R25的修复/资源/恢复测试在实际执行前均pending，本轮不得把spec标done、不得更新正式采纳或readiness，也不做Step5提交。实现完成后报告所有实际改动、静态hash/方法数、未完成事项和资源政策选择，等待Root执行必要验证。



### R26正式复审逐条裁定（审核回环3）

三层全部返回后逐项裁定，再按具体根因分组。原裁定先保存于Task JSON；此前文档同步未匹配CRLF标题，本次补入相同原行，不改变判定或事后制造核实。无carried；原完整diff及claims原件保留。

| ID | Verdict | Route | Evidence |
|---|---|---|---|
| R3-B1 | medium | bad_spec | planning_input:285在prepare→plan_batches:318首次measured前调用legacy factor，build_wire_request同路径；字符串内括号span不受JSON深度限制，32,768字符可产生268,447,808字符切片总量。后续wire门禁不能撤销分配。此为静态可达资源覆盖缺口，未声称实际OOM或远程攻击。 |
| R3-B2 | medium | bad_spec | runtime._selector_files:1334/1340及selection:944先legacy factor/restore后wire.render/preflight；公开preview及真实selector均调用。普通候选已有wire校验，但多候选比较会再次聚合并因子化；typed retained使用固定原owner而非当前prompt重验。未声称任意恶意材料通过完整准入；新全链资源政策在这些实际聚合调用前缺少预留。 |
| R3-B3 | medium | bad_spec | review_issues:394–396把自由rationale和obligation哈希计入code；obligations:274–278又绑定完整branch。append:272–283据issue_key集合把改写措辞或部分branch修复后仍存在的同一阻塞当新问题并丢弃进展。重排测试只覆盖数组逆序、完全清除问题，不覆盖这些条件。 |
| R3-B4 | medium | bad_spec | 合法review可阻塞cumulative或selected-only义务；repair_domain:481–522无可变owner即raise，下一次propose在付费前失败，append:293–297将其作输入准备错误终止。生成候选的跨域冲突可能需fresh replacement；目前未区分不可局部修复的业务问题与输入/执行错误，绕过合同的有限替换路径。不得授权修改selected原文或伪造3次修复。 |
| R3-B5 | medium | bad_spec | common:773–775的finally未保护persist_execution；已启动runner超时/中断且atomic_json失败时OSError替换主异常。基线也有该问题，但本轮新helper在terminate/capture失败后继续到此，新增路径仍破坏本轮明确的原异常保全承诺。修复仅保主异常与附带诊断，成功路径日志失败仍失败。 |
| R3-B6 | medium | bad_spec | worker:267–275顺序taskkill/wait无独立保护；当前新增taskkill(timeout=10)和候选deadline使仍活child在原错误后进入清理。taskkill TimeoutExpired可跳过wait并覆盖原deadline；需逐阶段尽力执行、保主异常及无主异常时失败关闭。旧机制亦有风险，但新超时触发为本Story暴露。 |
| R3-B7 | medium | defer | stderr.readline无限长单行、2Mi字符检查晚于整行分配及重复sum，在baseline AppServer:336–339已存在；本次stop-loop不增加数据接受量。独立于已延后的stdout总量问题，不宣称已修复。 |
| R3-B8 | medium | defer | stderr线程读取/解码异常不入incoming，stdout合法且OS0仍可能成功；baseline:336–340已无异常通道，当前stop-loop未新增此成功接受路径。为独立既存捕获风险，不当作本轮新协议问题。 |
| R3-B9 | medium | patch | 新PR工作流只选RuntimeTests，遗漏同模块的真实binding/coordinator类以及stdio/inherited-pipe模块；缺口层G1/G2已预核实，需接入现有确定性检查。 |
| R3-B10 | medium | patch | 新工作流paths缺_mvg_planning_review/_mvg_worker_lifetime/b_route_worker_recovery及stdio/inheritedpipe测试和AppServer fixture，相关单独修改会跳过该门禁；直接补已有owner路径，不新增运行权限。 |
| R3-E1 | medium | bad_spec | 与B3分别核实：rationale变化直接改变review_issues code；append将该新code拒绝并回退旧proposal。该缺陷不是此前已修复的数组顺序问题。 |
| R3-E2 | medium | bad_spec | 与B5分别核实：cleanup_after_error的persist未shield，原timeout/interrupt被日志OSError取代；基线已有，但新增尽力清理继续路径需履行异常保全。 |
| R3-G1 | medium | patch | 预核实：CI仅RuntimeTests；positive assembly替换verify_*，真实child仅反例；ReviewFix/CompleteWire/CompactWire实际binding→reservation→checkpoint正例不在PR。改变capture_binding的实际payload可逃过已选检查。 |
| R3-G2 | medium | patch | 预核实：stdio shutdown大尾流/晚错误/截止及真实后代持管测试不在正常PR；手工workers和直接活child中断不是同一场景。应接入既有两模块及其显式high fixture环境。 |

共有9个具体根因组；存在bad_spec，因此进入回环3。实现和定向验证见最新记录；patch/defer不冒称在先前回环已处理完成。
## Verification


### 2026-11-07 回环3当前工程验证（原正式审核仍待收口）

本轮必要改动及任务实现已完成。80个不同作者方法在明确分批/源码纪元通过，不是一次全套或全仓测试：core-01为61项，pipes-02为7项，origin-04为9项，r30的mvg-05为2项，独立r34的capability-06为1项。两处最终718份源码/schema/显式规则字节相同，实际输出和TEMP隔离，均自然OS0且源码屏障稳定。生成、准入、预留、selector和checkpoint仍使用生产验证器；model stdio是显式high合成响应，不是新增官方模型验收。

另有5项真实原R5来源对照及当前精确pin检查通过；原Capability资格清单277文件的哈希全部相符。多跳来源回放的重复递归已修复，9项定向控制覆盖实际函数体与合成叶验证，不能冒充真实原生资格。两个PowerShell run块实际语法解析无错；没有完整YAML解析器或hosted CI执行结论。

保留原R22/MVG及dc245b3/Capability各自producer、原proof/receipt/handoff、旧unknown和累计79/290占用；本轮新增官方CLI验收调用0，未释放旧占用。原329024字节packet的旧compact通过及新完整wire保守拒绝仍按原纪元保留，未改为通过。旧资格文件的formal_story_acceptance=false保持历史原值；正式Story审核完成应另记新收口记录，不能改签旧producer。

执行汇总将随本轮检查点保存在 `logs/ci/2026-11-07/story25-loop3-review-checkpoint/summary/`；原完整R26正式diff仍保留在Task的 `logs/ci/2026-11-07/story25-r26-formal-review/review.diff`，SHA256为1385c840c4b09452bb28def721a263a732fb4857eeefdafda5d202852f5261e3。原始大diff不重复嵌入新Git归档；逐条裁定、claims原件、屏障、结果及控制脚本分别保全。

当前仅满足进入正式Step4的工程条件；Step4裁定、Step5及sprint最终同步仍未完成。formal adoption、readiness、Task/Flow runtime及默认B均未启用。

### 2026-11-07 R26 回环2实际对账

184个不同方法分批通过，包名CI重复项已去重，32项完整运行时/compact控制及63项源/恢复控制均自然OS0并保持源码稳定。原真实R5宿主两文件对当前纯守卫另作正向检查；不是原native或模型复跑。原packet的compact通过、完整wire保守上界拒绝同时保留。完整范围、源码纪元、失败与未执行项见本文件顶部当前状态及 `logs/ci/2026-11-07/story25-loop2-review-checkpoint/summary/report.md`；不据历史测试声称全体本轮通过。工程回滚提交为 `4323f6eb94cea0bbf8599f2bd55800fe378667a3`，正式Step4复审与Step5仍待关闭。

### 2026-11-07 R25 工程修正实际检查点

Root 已完成 102 个不同定向方法的通过记录（多源码纪元，非单轮全量）。编码资源修正 54/54；两个完整协调器合成控制另有实际协议/OS/生产 binding 与 checkpoint 阳性。所有失败、harness 窄修及 72→74 自建成本修正保留，未执行方法不计通过。新增模型调用 0；campaign 最后观察 79/290、release0。证据见 `logs/ci/2026-11-07/story25-r25-review-checkpoint/report.md`、`summary.json` 与 manifest。

后续 v3 matcher 26/26 通过，原329024字节提示的完整packet摘要与精确规范重编码检查通过；原100m阈值不扩，误拒绝15与旧05ab源码保留。此1项兼容性检查单列，不计作新增unittest或原生资格。

S4-B1/B3/B4/B5/B6/B7/B8/B10/E1/G1/R1 已有实现及受影响定向证据；B2/B9 原裁定保留。Root 自检 S4-R2 发现并修复 reader 构造器在异常保存边界外，专门测试通过。资源计数 exact-int/空容器/编码前止损修正为 B7 具体实现闭环，不改变原政策阈值和 wire。测试夹具 medium→high 只是合成返回配置对齐，生产 high 从未下调。

原 R22 原生资格按原冻结 producer 继续有效，不重做候选/selector/3A；R25 离线成功不声明 R25 当前原生 qualification。正式复审及 Step5 仍未结束，formal adoption/readiness/runtime authority 不授予。

### 2026-11-07 原合同真实原生资格与 Step 4 准入

- 原 V18 仅追加 `m4:dispatch:13` selector，没有重新生成任何已准入候选，也未重跑已有效的 3A。三个原候选准入保留，盲标 A 对应原 candidate-2；原生返回 `winner-chain`、3 candidates、1 capability，checkpoint 已提交，完整 handoff 与选定内容经原严格 verifier 关闭。
- 真实来源链为 R22/s1 → R19/m1 → R10，原 c1 的 R10 证明、c2/c3 的 R19 证明及失败/unknown 原字节保留；不把历史证明重签为 R22。原 R19 全检查捕获具真实 held OS0，R22 原 owner 关闭历史原件并完整验证新 selector，不以自报布尔值代替证据。
- 原 native supervisor 的自然 OS0 回执 SHA-256 `ac0bb566e6317444be308b386758ad837af1e3f545204365eeb5097f6cb13080`；terminal `2d145b3afcae7bbd20482d14ddc6341cc1ee4d3c9ae1b8d8c59d1fccababa8d6` 本身明确不授资格，必须绑定该独立回执。Root 再执行固定只读 `verify-selector`，实际 held metadata OS0 回执 `f26443eab9714aedeb45efa784420ae673cbe4ff82718976bed75288f75b3634`，qualified 记录 `af853ce0ea84812ae30c5cf94f04ef174c5da3046ad06da0b3289f0b0e7ba36a`。证据在 Task `logs/ci/2026-11-07/story25-v18-qualification/verify-01/`；Root 未凭进程消失或模型 completed 冒称资格。
- 原生 m4 13 次宿主逻辑调用全部 completed；campaign 累计已付或未知占用 79/290，释放 0。旧 v15 unknown 及所有失败保留。qualification 新增模型调用 0、完整 MVG 复跑 0。配置证据为官方返回的运行时 high，不宣称服务端真实模型、实际推理、物理请求数或费用已验证。
- R22 必要离线检查已有 24 项 recovery/epoch PASS、14 项 codec PASS 与真实旧 admission 捕获/外部 OS0；最终实际完整 wrapper 92747 输入估算加 2000 原预留为 94747，低于原 96000 门禁，未截断。原 frozen intent、预算、独立语义和失败关闭标准不变。历史测试在其原源码纪元保留，不将旧 baseline 的失败改称全绿。
- 原 Capability 的 11 次原生资格及自然 OS0 经固定 metadata guard 保留；不重复完整 Cap 模型或 protocol 验收。selected/handoff 仍不授 formal adoption、readiness 或 Task/Flow runtime authority。新 R23 分段方案在独立分支离线实施，不替换本轮旧合同结果；其诊断或测试不是本 Story 原生验收。
- 正式三层审核与 Step 5 尚未完成；此段只记录原 Step 3 真实资格及进入 Step 4 的依据。

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

## 2026-11-06 R8 恢复验证记录（尚非最终验收）

- 实际执行源码冻结为 `f828d861fab8e879c9069adfeb218d81c0d8b43c`，R7 `d7d0dad0` 及原 R5 源码均保留。`continue_story25_synthesis_recovery_v4.py` 的零模型预检、正式恢复准备及准备后原生 proof/prefix 校验通过；`synthesis-1/record.json` raw SHA 为 `80b34a156033b1d6078155a839c8f7a12f961cebf9ec7ebc40357dbf6cd5693b`。下一次允许的综合仍是原 c4/candidate-2/gen1/execution1 的 global7/local3，不重做已完成 batch，不释放旧失败或 unknown。
- 新 producer schema 模块最初13项通过；认证旧 legacy 请求的策略修复后，新增及直接受影响3项通过；实际分派源码根检查新增1项通过。共15个不同方法；8个原语义 owner 函数源码与 R7 精确相同。source epoch 最初5项通过，Windows正斜杠路径追加1项通过。综合恢复最初10项通过，原生 selected-prefix 形状修复追加3项通过。各项均为明确离线合成证据，不当作实际模型准入。
- 既有 `test_b_route_planning_runtime` 的原单次59项运行保留54项通过、4 failure及1 error的完整记录。两项因运行期间源码变化触发规则漂移，另三项受合成测试默认推理环境／测试 harness 子进程清理白名单影响。仅修两处测试局部环境与独立 v2 harness，5个受影响方法在冻结生产源码上单次复测全部通过，约615秒，source manifest前后相同；未重跑其余54项，不称为新单次59项全绿。59个不同方法现有通过证据，均为0真实模型调用。原记录：任务根 `logs/ci/2026-11-06/planning-runtime-r8/module-01.json`；复测：同目录 `failed-02.json`（raw SHA `cda5bc6b543b4c5d41251cf135bda3185838311374e75fbda4642ba38e763f2e`）及 `targeted-repair-02.md`。Windows清理仅限当前 harness 自己创建且经出生时间重核的子进程，未触碰旧PID、其他项目或服务器进程。
- c4 真实续接宿主已启动并写入永久 stage claim；截至本记录尚无 global7 receipt，不把宿主启动当模型完成。m4 尚未启动。正式两候选／三候选选择、Step4审核及Step5收口仍须实际终态。

- 2026-11-07 第1次正式审核回环：触发S4-B1/B3/B4/B5/B6/B7/B10/E1；修订非冻结实现计划，明确语义依赖闭包、原事务恢复/临时物归属、资源界和3B修复域，并纳入B8/G1/R1异常证据与测试修正。已知坏状态为门禁漏依赖/崩溃后无前进路径/编码资源无界/无关修复及丢失异常证据。KEEP见逐条审核末段，原冻结意图一字节不改；独立后继分支保旧现场，不将旧资格冒充新代码资格。

## 审核回环2当前实现计划（独立后继）

原冻结意图不变；当前 R22 原生资格与 R25/10398 的全部正向检查点保持原目录。下列变更全部属于工程修正，不制造 current 原生资格、采纳或默认 B 权限。

1. 资源链：在构建完整 AST、lossless 因子化/恢复/完整序列化和compact sharing之前建立预算；内层向后引用、concat、source/lines/escaped-object等原语在展开前饱和核算。完整编码共享计量，不只计后半段v3匹配。不改 wire grammar、字段、顺序、数据或hash；不截断、不回退编码。8MiB编码、64MiB展开、1m节点、128深度和100m工作界不扩；若需要更精确政策须显式版本并说明，模型96k/70k/输出/调用/时间上限不变。旧329024字节原包和已有正常小样本作为明确兼容性对照；若新全链门禁合法拒绝更大逻辑材料，报告完整计量和限制，不伪称通过。
2. 元数据：原子且独占地发布完整transaction journal；中断发布的原始字节可定位保留，只有原source/anchor/nonce/完整前后像和阶段可证时才续接。支持多次不同合法前缀的保留/幂等完成。原coordinator锁、raw CAS、未知占用和release0不变；不得从缺journal/行或PID消失推断请求未执行，不改ID盲重发。补代表性prepare/reservation/unknown发布及操作窗口、多次中断和篡改拒绝，不写只镜像内部函数的测试。
3. 宿主：Windows reader停止握手及有界重复取消/退出确认，防read间隙漏取消；App Server逐项尽力清理并保原异常和明确host诊断。成功协议/返回的模型输出/原raw journal/无工具/high门禁不弱化。stdout总量限为既存延后风险，本轮不悄悄新增或放宽该政策。
4. 源守卫：精确分离允许变化的host故障类/函数与App Server finally；所有非故障协议body、validator、semantic helper和纯公共helper继续严格绑定。不能为让测试通过放宽整个模块或把原proof重签为新规则。新source/policy必须真实冻结。
5. 兼容与入口：移除本轮自行增加的每次修复必须完全消除当前issue门槛；3B仍严格限制有实际目标变化的修复域，所有profile保留合法累计部分进展与原三次预算，最终仍必须通过完整独立语义准入。fresh-run容量检查覆盖真实最坏原子临时名及协议/输出路径，不修改OS设置。把既有确定性3B运行时/硬化检查接入维护CI入口，完整记录实际选择范围、依赖和未执行项；不得触发真实模型CI。
6. 验证只由Root串行执行，先定向负例和已知原packet，后必要的完整绑定控制；复用未受影响的102方法旧纪元证据，不冒称全套新通过。各写者只在独立克隆和明确文件边界写代码，不运行测试/项目导入/native/model/Git；Root统一集成、冻结、执行与提交。正式Step4重审、Step5仍pending。


## 审核回环3当前实施计划（优先于历史实施记录）

Root实施复核补充（2026-11-07）：首批61方法、Windows管道7方法及原pin纯guard5项已分别通过，均为独立证据范围。对新增verify_repair_origin实际函数体的合成叶验证诊断发现，generation parent与同源review各递归一次，使深度1/2/4/8产生1/3/15/255次回放；它不构成原生资格。修正必须在本次栈帧中先完整验证generation parent，然后严格对齐review的原parent/issue并复用同一已完成的边，仍逐份核验review绑定与完整内容；不得跨行动缓存权威。总工作界沿用slot64、profile96/192推导，不能新增可调模型额度。补多跳、frame篡改、未知与周期拒绝控制后再执行受影响验证及两个profile正向协调器，不重跑原native。该项属于本轮Step3实现缺陷修复，不改冻结意图、不提前宣称Step4/5完成。

本节仅修改非冻结工程计划；原冻结批准块保持原字节。当前正式Story未通过，旧R22资格仍只属于原producer。继承原Tasks & Acceptance全部要求，以下任务须实际通过定向验证后才关闭。

1. 所有实际legacy factor/restore入口先进入既有资源预留，包括planning_input.serialize_request、build_wire_request、冻结输入重验、runtime selector虚拟文件及真实selection比较文件；共享同一次构建计量，避免只检查后半段或重复重置。保留legacy字节与命名空间，不能通过改旧lossless_context、截断、缓存authority或提高限额绕过。本轮已知原packet全链保守拒绝仍保留，不强求它按新政策通过。
2. 稳定业务issue账户与完整评审证明分离。自由rationale改写和局部分支内容修复不得仅因此被视为新缺陷；完整review obligations/check数、分支同kind多重性、来源支持、实际字段scope及raw review哈希仍严格验证。身份必须由宿主依据冻结来源和可辨识逻辑owner派生，模型不得自报或把不同来源/义务合并。不得改原review owner后声称其unchanged；如通过新3B账户适配实现，历史legacy身份完全保持，版本和材料绑定显式记录。保留真实新增缺陷拒绝、三次修复与最终独立无阻塞准入。
3. 不可局部修复的业务问题必须与输入/执行错误区分。对真实cumulative/selected-only无可变owner，绝不修改选定原文或扩大任意scope；有限地退休当前候选并经原replacement预留进入clean context，沿用原round/slot/run预算及已接受前缀。不能伪计已做3次修复、退款unknown、无限重试或把无owner当批准。数据/身份/执行错误仍失败关闭。
4. common超时/中断清理中的日志写失败不得取代主异常；附带可观察诊断，成功路径日志失败仍失败。worker stdin关闭、taskkill/kill、Job关闭、wait/reap分别尽力执行，保持原失败、无主失败则显式清理失败；只处理本次拥有的child，有限deadline不能被绕开。对应源码守卫应精确绑定经审阅的新故障owner AST，其他协议/语义/预算守卫严格不变，不能加笼统allowlist。
5. 新Windows确定性PR门禁纳入已有协议/正向真实binding协调器、checkpoint/review/complete/compact/deadline、stdio shutdown和后代持管测试；路径触发覆盖其owner、测试及fixture。使用high合成fixture、受控短TEMP、原依赖来源，无APIsecret/真实模型/登录/网络设置变更。实际本地定向运行与未执行hosted CI必须分别报告；不得用大范围重复测试替代针对性验证。
6. Root为唯一实际项目测试、Git集成和原证据检查owner。实施者只做源码、AST/哈希/静态检查；禁止运行项目imports/helper、测试、native/model或修改Git/冻结材料。可按用户要求并行委派互不覆盖文件，须在独立副本操作并把精确路径与哈希交给Root集成。资源、语义、宿主、CI分别独立；涉及共享runtime/selection文件由一个owner整合，不并行写同文件。返回所改内容、静态验证及未完成风险，不将AST-only当测试通过。

KEEP：原R22完整真实资格、原3候选/13调用、累计79/290、release0和旧unknown不动；R25/10398和R26/4323、184个分纪元方法及所有失败原字节保留；完整源/分支/命名空间/分母/引用/独立评审与凭据隔离不弱化；96k/70k/输出、8MiB/64MiB/1m/128/100m及原调用/时间限不扩；不重做原3A或已准入候选。原八个语义owner若需修改必须真实版本化，不能放宽“unchanged”守卫后重签旧proof。high/无工具/Fast关闭/不合并main。

## 回环4当前实施计划（优先于历史未完成项的状态叙述）

本段是回环4唯一新增写入授权和验证计划；继承既有AC与约束，冻结块保持原始字节。Root将原r30/f9cdab现场、代码和证据冻结保留，在独立r35工作分支上重衍必要实现，绝不对原producer执行reset、覆盖、删除或伪造当前资格。旧代码中已经证明有效的部分原样保留，新写入仅限下列已证实缺口。旧下级patch在此次回环重衍时一并解决，不宣称它们原已完成。

1. Fresh run显式激活已有PROVIDER_SCHEMA_POLICY并绑定完整请求、canonical主机校验；测试经create_run真实初态进入batch/synthesis producer，空/单/双parent均使用现有兼容schema、原canonical顺序/重复/type不放松；历史policy absent仍原样验证，不补写旧state或回执。
2. Live 3B dispatch在reservation及外发前同时核对runner description/captured backend_info与当前请求环境要求high。共同prepare_dispatch覆盖worker与selector，必要时operate早报；不得把这条新live规则加进通用历史verify_call/validate_execution而拒绝旧合法回执。不读取认证或sessions，不更改服务端/网络/Fast设置，不把请求配置称服务端实际模型推理。缺失/low/config-vs-current环境不一致必须在before_call之前失败。现有driver已设置high，不能为测试成功降低档位。
3. 原machine/身份/完整候选结构及语义owner保持权威。无局部位置的真实业务机器问题必须可以进入原有限clean replacement；在原始frozen/immutable检查与重新计算宿主issue确认后才分类，不能仅凭code前缀、self-reported detail或捕获所有SEMANTIC_ERROR/unresolved。已证实例为同id不同Command导致tuple owner诊断。schema/input identity/draft provenance/source revision/manifest/dependency ID/revision/digest及执行异常仍失败关闭，包括它们与业务重复并存时。原three repairs/three replacement/64/96/192和unknown占用完全保留，替换不能修改selected originals或清空累计账本。
4. 初始化在显式独占的新staging命名空间完成所有冻结材料、state和必要初始元数据，再不可覆盖地发布完整权威run目录。中断前不能让不存在run.json的权威目录出现；中断残片保留为非权威证据，可在未外发前另建独占初始化，不假定旧权威半目录/未知请求未执行，不自动删除或采用它们。竞争发布不覆盖已有目录；有效已存在run继续走原coordinator锁/身份验证，旧partial/foreign目标失败关闭。测试关键写点故障、真实竞争、部分原目录、unknown ledger不变与完整发布后重入，不靠sleep或减弱隔离变绿。
5. CI维持共享显式runtime选集，补真实用到的provider/review/partial/path/MVG prepare/synthesis/wiring/worker/source epoch负例；wiring要保留完整三draft与original prefix断言。新runtime组每个实际CI caller均应获得官方来源的任务/runner私有依赖与双编码缓存，不污染现有系统Python；复用共享准备逻辑优于三处漂移，不放松真实tokenizer断言或偷偷skip。既有hard其他命令/权限/证据不能削弱；不为安装便利换镜像、改网络或执行现场安装。只落地未来CI准备代码和静态/离线控制，hosted执行和实际安装报告仍明确待跑。补_capability_input_integrity、_llm_backend、对应runner测试及新增准备owner路径。根据真实工作量核查timeout，不宣称未经执行的hosted job成功。
6. Root是唯一实际项目导入/测试/helper/native/Git/集成owner。实施agent可在r35上述最小源码、配套离线测试、ADR/owner文档范围写入，可按用户并行授权把互不覆盖文件交给独立作者，但必须明确文件owner；作者只能文本/AST/哈希静态核对，不运行项目导入/测试/helpers/native/model，不写Git/原r30或其他项目/现场。Lead统一冻结写入清单后交Root执行。原80项、旧184/102项、R22原资格只能按原source epoch引用，不直接算本轮新通过。

### 回环4新增任务（Root实际验证后才勾选）

- [ ] R4-entry：新run策略与high共同边界实现，真实create/prepare调用路径及历史兼容正负控制通过。
- [ ] R4-business：tuple机器业务问题经真实候选owner校验后有限替换，immutable/source/schema/执行错误和混合错误拒绝；不重做付费候选。
- [ ] R4-publish：完整初始化原子发布与竞争/中断/旧partial/unknown保留控制通过。
- [ ] R4-CI：必要恢复选集、官方私有依赖/编码准备的所有实际caller和路径触发已接线，定向控制实际执行且证据说明stub/静态边界。
- [ ] R4-review：Root检查实际diff、原冻结块和来源边界，必要回归通过，再执行原生Step4三路独立复审，不能在此预勾。

### 回环4必要验证

新增入口/发布/业务分类测试必须实际执行；受改动影响的provider、runtime live prepare、原historical binding/source transition、append替换及CI selector测试择必要范围运行。新增纳入维护的恢复套件需要原有效证据复用与本轮必要执行区分，防止一次次重跑完整真实验收。只有新代码或失败要求才扩大测试。继承原80项可复用不受影响的控制，完整离线profile协议只有变化确实影响该组合且局部控制不足时才重跑，不能将测试夹具/叶边界mock当原native资格。任何实际模型验收仍受原79/290累计预算和原合同准入；本轮修复没有新增付费调用计划。

KEEP：原R22/MVG与dc245b3/Capability各自真实producer、13/11逻辑native记录及原三候选/两候选、79/290且released0、所有unknown/失败/原预算/阶段时钟/claim；R25/26/30原分支与80项分源纪元实际通过、两个完整离线协议结果不重标为当前原生资格；原资源门限8MiB/64MiB/1m/128/100m及96k总门禁/70k未来分段、96/192/64/三轮限额；11关键canonical函数、原3A proof、完整来源/审计/遗漏冲突检测、high/无工具/Fast关闭/不合并main。旧stdout及stderr后续项已经一次登记，不重复。


## 回环4 Root 实际验证与 Step3 收口（2026-11-07）

当前45个不同方法已实际通过，保留最初 setup／夹具失败与各自源码版本，不把混合失败记录重写为整轮通过。当前 Capability 与 MVG fresh 完整合成协议分别自然 OS0，732文件清单相同且稳定；两者均保留本轮新默认 policy，覆盖生成、原业务／协议绑定、准入、selector、checkpoint。新增真实项目模型调用0，原campaign占用79/290、unknown及原真实资格冻结不变；此结果不是R35真实模型重新资格。

原 Tasks & Acceptance 的实施任务及六行冻结矩阵已逐项对账，详见 [Step3矩阵与执行方法索引](../../../logs/ci/2026-11-07/story25-loop4-verification/step3-matrix-audit.md) 和 [原始版本／通过方法／失败保留摘要](../../../logs/ci/2026-11-07/story25-loop4-verification/summary.json)。原R30的80项和原R22／R10真实证明保留原epoch，不自动计为本轮全套。源码与测试验证后未修改；本节仅记录状态。

CI八项控制、私有准备PowerShell语法及三份实际caller YAML语法／基本结构通过；未安装新依赖或执行hosted CI。本轮尚待原生Step4三方正式审核及Step5收口；formal adoption、readiness、runtime及默认B启用继续不授予。被冻结的人类意图与baseline保持原始字节／值。


## 回环5唯一当前实施计划（旧现场全部保存）

在全新独立 r40 工作分支从 Root 保存的 R35 checkpoint 安全重新派生；原 r35、真实 producer 和旧 proof 不执行 reset、删除或覆盖。沿用已验证实现，只针对下列证实的缺口派生最窄修正。这一节覆盖旧 r35 写入授权，其他已有合同及被冻结 Intent 均保持。

1. repair_scope_errors 不得把 admission_machine 的首错误当所有旧错误。对修复后出现的机器业务错误，按原候选及同一真实业务谓词辨别原已存在但被先前错误遮蔽的失败；只允许可证明旧有的失败继续按原 issue/round/call 合同推进。真正新引入、无法证明旧有或不可定位的错误仍拒绝。不得借由移除 machine 检查、广泛吞异常、硬编码 UI 特例、修改原候选、放宽 schema/source/identity/execution 或扩大 repair domain 通过。证实既有缺陷也不代表它已修好或可以准入。
2. 必要正负回归：同一有效 schema 候选中 UI 与 human_verification 均有真实业务缺陷；修好UI允许显露旧human错误；只修旧human后可继续原验证。修UI同时新引入原先有效human错误必须拒绝；无关业务缺陷、非法来源/schema/身份/执行混合、越域及无进展保持拒绝。保留 canonical validators 既有行为与接口。
3. CI维护常量补 test_b_route_compact_literal、test_b_route_compact_literal_v3、test_b_route_tuplecompact_v2、test_b_route_input_compact_runtime、test_b_route_source_audit、test_b_route_audit_partial_reuse、test_b_route_audit_recovery、test_b_route_review_source_policy。补维护断言，沿用现有私有 Python/cache/输出隔离及逻辑预算；不运行安装或修改现有环境，不新增公开配置。
4. 给 completed handoff 构造 distinct 且真正 valid/admitted 的候选，精确检查全部 comparisons 的 winner-relative path/before/after，包含赢家自身无差异及非赢家实际差异；不能只直接测试 json_delta 或与自身重算结果比较，也不修改已准入真实候选。
5. Root 是唯一实际项目导入、helper、测试、native、模型调用和 Git owner。实现者仅在 r40 的上述 production/test/必要 owner 文档做最小文本/AST/hash 静态实现，返回写入清单、源哈希、静态结果和未完成项；不要运行项目、测试、子进程、模型、Git、安装或改变网络/认证/安全设置。不得写 r35/r36/r37/r39/nx 或共同证据。允许已获用户授权的互不重叠静态协作，但先明确文件 owner。
6. Root 审核真实 diff 后选择受影响的必要正负测试；继承原源纪元的有效记录，不因新增方法重复整个 profile 或已完成候选。真实验收模型调用计划新增0；如确需真实调用仍遵守原79/290累计与预留/unknown合同，不自动扩额。正式原生 Step4/5 尚未完成，不能提前称 Story 验收。

### 回环5待 Root 验证

- [x] R5-business：已遮蔽旧错误与真实新增错误区分，正负及原边界测试实际通过。
- [x] R5-CI：八组维护选择与调用端维护断言通过，原隔离不变。
- [x] R5-handoff：区别候选的完整交接精确差异测试通过。
- [x] R5-review：完整差异、六行矩阵及原生Step4/5正式收口；不提前勾选。

KEEP：R35 当前45项实际通过和732源文件冻结、失败夹具和原记录；fresh provider policy、live high、immutable/source/schema 门禁、局部修复/clean replacement、原子初始化、私有 CI 环境；R30原80项及之前各源纪元证明；原R22/MVG和R10/Capability真实资格、原候选/3A proof、旧unknown、79/290/released0、原预算/claim/锁/稳定ID；原资源容量门禁不提高、不截断；high/无工具、Fast和1.5倍不启用、无main合并/推送。原stdout/stderr carried不重复处理。


### 回环5纯谓词 owner 的受控实现澄清

仅允许 _b_route_candidate.check_graph 把原每 Flow 前置断言抽为单一纯 flow_local_predicates owner；顺序、unique/resolve、条件、entity/expected/actual 诊断及原 canonical require 首错行为必须不变。before witness 与 canonical 必须调用同一 owner；不复制规则、动态 FunctionType/exec、全局 monkeypatch 或吞非预期异常。该 witness 不授予 admission，只证明某个修复后错误在未改 before 已存在；结构/来源/schema/身份/执行检查仍先严格通过。未被该 owner 完整证明的错误继续失败关闭，不以未收集到的错误推定不存在。

_mvg_capability_append.run_capability_append 内另有旧首错误差集，会先于既有 repair_check 重复误拒，允许为其增加内部可选机器修复验证 callback；legacy 未提供时保持原差集，3B 明确绑定同一 owner 的判断。原 preservation 错误的新增仍必须独立拒绝，不能由机器回调豁免；回调必须返回受验证的明确错误集合或 boolean，不接受任意 truthy、异常、缺失证据。不得因此改变调用/round/counter/unknown/ledger/schema、公用 CLI/JSON、历史 replay 准入。至少通过真实 append 路径证明 masked-old 的连续修复可完成，new-human 缺陷与 preservation/immutable 混合仍拒绝。

这一澄清是当前非冻结实施计划的最窄例外，不表示原 check_graph 函数体哈希保持；Root 新证据必须记录实际新 source epoch，旧真实 qualification 仍原 source epoch。实现者继续静态检查，Root 执行项目测试。


## 回环5 Root实际Step3验证（正式审核仍待收口）

29个不同必要方法实际通过：原core-01保留9项，单个负向断言修正后followup-02的1+18项通过，最终一个distinct候选完整交接通过。原失败是UNKNOWN-OWNER按既有合同返回明确拒绝而非抛异常；生产代码未为测试放宽。原始失败及逐字节原测试的hash验证重建件均已注明来源保留。当前736源清单稳定，独立静态复核未确认新P0/P1/P2，但这不代替正式三路Step4。

当前旧错误见证与canonical共用纯owner，新增/不可证明/越域/preservation仍拒绝；旧producer及真实资格不改写。29项通过不是当前源码原生模型重签，实际项目验收模型调用新增0、campaign79/290、released0、旧unknown不动。六行矩阵、逐方法ID/结果/屏障/源hash见 logs/ci/2026-11-07/story25-loop5-verification。正式Story验收尚未发生；接着执行原生Step4/Step5。


## R40 正式审核补丁实际收口（pass 6）

原三层审核全部完成，12 条意见先逐项裁决，再按根因分组。三个补丁组已实际验证：共享 CI 纳入资金和 worker 完整测试模块；精确原宿主 handoff-edge finding 使用既有有限替换；生产 generate_append 接线以真实 append/machine/repair/账本路径覆盖 UI→旧 human→准入。不是手工注入被测 callback 的替代验证。

本轮只执行新增与受影响检查，具体方法、分母、源码和结果见 logs/ci/2026-11-07/story25-loop5-review-patches/summary.json。旧 29 项及失败/修正记录按其原源码纪元保留，不重新声称为一次全套通过。六项初次登记的历史缺陷及 carried stdout/stderr 原裁决保留；无新的当前补丁问题待修复，无意图或合同回环，回环计数仍为 5。

原 R22/MVG 与 R10/Capability 实际资格、3A proof、已选候选、旧 unknown、79/290 占用和 released0 不变。本轮新增真实项目模型验收调用 0；合成验证不冒充新真实模型资格。formal adoption、readiness、Task/Flow runtime 和默认 B 均未开启。Step5 状态及本地可回滚提交随后另记，未远程推送或合并 main。


## 当前最终状态：Story 2.5 原生 Step4/Step5 已收口

三层正式审核、逐条裁决、三组最小补丁及必要定向验证已完成；六项历史缺陷按原流程登记，原 carried 缺陷不重复登记。Story 实施验收完成，仍不授予正式 B 采纳、readiness 或 Task/Flow 运行资格。当前补丁的实际分母和原29项/更早回归均按其原源码纪元留存，未合称本轮全套通过。

原 R22/MVG 和 R10/Capability 的真实资格由原冻结 producer 与原回执支持，不改签为当前源码；原 qualified.json 中 formal_story_acceptance=false 保持原件不变。本次正式 Story 关闭另存 Root closeout，明确区分原生执行资格与审核后的实施验收。没有新增真实项目模型验收调用，没有释放 unknown，campaign 保持79/290；没有远程推送或 main 合并。
