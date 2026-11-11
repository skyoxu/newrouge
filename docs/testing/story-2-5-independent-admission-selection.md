# Story 2.5：Task 无关准入与有界评选

## 当前实际状态（2026-11-06T02:53:19.114439+00:00）

- 原执行链实现提交 `c845ee81`；34 个代码文件仍与冻结清单一致。新 3A 两阶段真实 high 已通过并按 current proof 复验，报告 SHA-256 为 `c640e0cf61218838d87787f7590c63ed7331b4257328d40952d701e28cab2b03`，不因本次宿主连接中断重跑。
- 独立恢复能力已纳入工作分支 `1d92ace7`：新增 standalone `b_route_worker_recovery.py`，不改旧执行链及 import closure。21 个不同定向方法有通过记录，含完整原 machine/semantic/reservation/protocol/binding gate 下恢复同一 unknown 预留及 admission、原协调器跳过旧 lifecycle；全部为明确的合成离线证据，不能冒称真实 x15 恢复或 AC 通过。原失败及针对性修复记录保留，没有整套重复重跑。
- 原 nx 新入口的只读 inspect163 在原 high/NoSite 环境下通过当前输入、3A 和规则复验，仍以 `dispatch_outcome_unknown` 返回 blocked；未执行 apply。原 21 文件、34 源码和审计 c640 均未变；当前缺少原完成输出、绑定及 worker result，新恢复能力不会生成这些缺失证据。记录见 `logs/ci/2026-11-05/b-route-story-2-5-build/x15-recovery-inspection-163/report.json`；定向测试和独立窄审查见 `logs/ci/2026-11-06/completed-worker-recovery-159/summary.json`，不等同正式 Step4。
- x15 已启动，但 exec-server 断开且原会话 89429 恢复超时。原协调器 PID 10736、worker PID 11576 已消失；不能据此推断模型请求失败或完成。原始错误、进程观察和 21 文件哈希保存在 `x15-host-loss-147/report.json`；复核与私有本地证据归档在 `x15-host-loss-checkpoint-149/report.json`（路径均相对本 Story build 日志目录）。
- 仅 1 次调用预留，`x15:dispatch:1` 结果 unknown；没有完整输出、执行绑定或 dispatch receipt，协议中没有 turn/completed，没有合格候选或 selected。未重发、退款、篡改原账本或重开终态。旧 3B generate 仍先拒绝 unknown outcome 且不能重接 worker；新独立恢复入口仅接受完整原完成证据，当前 x15 不满足；不能用 generate 充当无副作用恢复探针。
- campaign 已关闭阶段计入预算的逻辑调用 48；当前 MVG 阶段保留 192 上限，guard 占用 240/290（不是 240 次实际调用）。未知的 1 次预留仍保留，未释放阶段上限。e15 仅准备、0 次调用，不能在 MVG 未成功时启动。
- v2 有 22 个组件方法及 8 个不同集成方法的通过记录；实际完整字符串封装预检 87646+2000<96000，全量原材料、schema、预算及 high 不变。历史 none/v1 精确重建和 x14 原 222 文件未变的证据继续复用；没有为本次连接故障重复测试。
- 官方返回的是 openai/gpt-6.1-sol/high 运行时配置、ephemeral/readOnly/无工具；服务端实际模型、实际推理、物理请求数及费用仍 unknown。连接中断根因及进程退出码未知，不宣称 AV 已修复。
- Story 2.5 原生 Step 3 尚未完成，Step 4/5 未启动；尚无新两入口真实阳性、固定 winner 或完整 handoff。后续 Story 依赖不能据准备材料或独立组件冒称满足；没有操作 main、推送、合并或接触其他项目。

### v2 完整数据传输：当前冻结检查点

- x14 真实容量终态与两个原准入保留，原阶段11次结算，campaign46/290；没有重开终态或移植proof。新规则尚无真实当前资格，正式Step3/4/5未完成。
- 通用组件22项测试通过；8个不同集成方法已有通过记录。首轮6通过、两个合成入口因旧夹具固定medium被high门禁拒绝，失败原样保留；只改显式合成响应并重跑两失败方法，两者通过。随后仅调整模型文字，明确摘要校验由host执行；其余codec AST完全相同，只复查受影响的两个方法通过，没有重跑22项或前6项。
- v2保完整字段／类型／键序／数组序／原字符串，严格数据AST、碰撞转义、表／摘要和规范重编码；不是代码执行或业务输出补写。旧none/v1的11份实际prompt及两阶段3A的6文件精确重建，原x14全部222文件哈希不变。3A v5/v6 carrier默认仍为v1。
- 原失败完整字符串请求101801+2000超过96000；最终实现重测为87646+2000，原schema／官方workspace字符串包装／计量公式／1MiB及全部调用、时间预算未改。曾将计量包prompt换成对象的91702已明确撤回为counter-only-invalid，不能作为容量解法。新的实际请求仍逐次完整测量，不能预称未来全部可容纳。
- 独立窄工程只读复核未发现可确认缺陷，不是正式Step4。当前旧3A可按历史字节完整重放，但严格current工具漂移门禁拒绝新资格；需要新冻结下真实审计及两入口阳性，绝不把旧证据跨规则冒充通过。详见root-compact-wire-review-freeze-144.json、root-compact-final-preflight-142/report.json及原始各次测试报告。

## 历史生产端修复与继续验收

后续 v6/v7 合成源已明确六种正常/完成后崩溃用例，以及每次强制终止、确认退出、
保留日志启动和重复恢复的顺序。v7 为 5212 字节，SHA-256
`cc5899bfa61f91dda614e13837f2254549d1d3b53a87726a3842a16af10570e3`。
离线逻辑检查为 68 条基础见证、20 条生命周期协议、40 类负向变异，不等于游戏执行。

真实 v7 提取曾返回一个偏差一字节的引用，原严格校验正确拒绝；仅消耗一次宿主
逻辑调用，未执行比较。本次继续阶段累计计入 5 个逻辑槽位，另有此前已关闭两轮的
4 次；物理请求和费用未知。该失败不是新的容量错误，原进程已结束，未重复启动。

现增加可选 `--citation-guidance full-block`，指导无工具 producer 原样复制已给定的
完整 citation_span；仅该模式用紧凑 JSON 降低重复格式开销。默认提示词/请求字节、
输出 schema、validate_citation 和 validate_output 保持原规则；精确合法的局部引用
仍接受，原实际错误引用仍拒绝，没有自动修补模型输出。模式同时绑定请求、阶段
输入身份、工具/提示身份及精确重放；历史默认 proof 仍只读有效，当前工具漂移仍拒绝。

生产端定向 8/8 通过；主线程两个受影响模块共 73 项：72 通过、1 个 POSIX symlink
平台分支跳过，0 failure/error，源文件前后哈希相同。未重复其他无关套件。新模式
本地预检保留了原业务 payload，首提取估计 11295、比较已知部分 20176 tokens，未来
真实输出仍需原 30000 上限逐请求检查。证据为 `citation-guidance-freeze-28.json`、
`root-guidance-diff-review-30.json`、`story25-tests/root-guidance-regression-29.json`
及继续目录 `guided-prospective-v7-01/report.json`。将保存此修复检查点后按持续授权继续，
Story 与正式 Step3/4/5 尚未完成。

## 当前授权与实施检查点

用户已批准 3283 字节修订源及后续同类合成材料的自主修订/验收，并授权实施中适时
提交多个可回滚版本；不合并 main，不扩大到新类别敏感数据，不绕过强制逐次确认。
因此下文“尚未授权”的文字保留为历史阶段记录。真实语义门槛、原生预算与失败关闭
保持不变；失败须先查因并留下证据，不无进展重复调用。

本次继续使用一个独立累计 290 逻辑槽位护栏：每个原生阶段先按其完整原生上限预留，
进程返回并核对持久化计数后才释放未用额度。换材料/修复不会重置本次累计计数。
最初调度器曾在派发前创建空预算标记，已验证当时没有原生 audit/预约/模型调用，
保留原标记并修复；离线检查确认预留/释放、超限拒绝、重复拒绝及损坏记录失败关闭。
证据位于 `logs/ci/2026-11-05/b-route-story-2-5-build/continuation-approved-01/`。

当前本地提交是已完成离线实现的可回滚检查点，不表示 Story 真实验收或正式
Step3/4/5 已完成。真实审计和两个 3B 入口的结果按后续实际记录更新。

## 新草案系统离线检查：未外发

最新拟议材料为 `docs/testing/story-2-5-controlled-acceptance/handoff-v5-draft.md`，
3283 字节，SHA-256 `3b0b7288ce82132d246ba86661d915af1076e1838436a946e42151f37c22b7ec`。
这是尚未获得新外发授权的 toy 数据；旧 132/855 字节材料及 v3/v4 草案均保留。
标题为中性背景，审批/发送状态写在独立元数据；7 个强制段落分别保留 scope、
invariant、constraint、functional、functional、failure、constraint 分类和完整原文。

除既有 finding 外，本轮发现并修正首次 accept 缺 MapReady 断言、内部步数无法观察
挂起、调用关联/重复完成、场景隔离降级为背景、自报 UI 状态不足等明显缺口。
新源要求外部单调时钟的 10000ms 边界包含恢复与独立 UI/持久化日志观察，且超时不因
后续崩溃消失。该边界是新 toy 判据，不改变模型或项目原预算。

本地原生 prepare/account 为 8 个来源块、1 个标题 context、7 个非空提案完成机械
记账；另一个不导入生成器的确定性检查器对实际 candidate 验证 68 条合成见证轨迹，
22 类负向变异均被拒绝。这不是独立 LLM 审核、游戏执行或真实语义准入。本轮模型
调用为 0，没有创建新的 audit 或合格 3B prepared，也未重跑未改源码的宽泛测试。

首提取请求估计 8979 tokens；比较的已知部分为 19485，尚未包含未来真实提取输出，
不能保证最后装入 30000。原 3B 96000/预留 2000、1 MiB 和原时间/调用预算不变；
单批次无修复计划仍为 19 次，原生上限 290，实际新 B 值未知。逐请求容量检查必须
保留，不截断、不扩容。完整逐项核查、拟外发数据、变化及范围边界见
`logs/ci/2026-11-05/b-route-story-2-5-build/v5-systematic-offline-02/offline-review.md`
及同目录 `offline-review-and-egress-proposal.json`。Story 仍为 in-progress。

## 855 字节澄清材料获批后的实际结果

新一轮 `s25-clarified/audit-01` 完成 extraction、comparison 两次真实宿主逻辑调用，
但仍为 `semantic_blocked`、`planning_eligible=false`。F1 指出根线程写入的
“NOT sent or approved”标题是来源状态背景，原投影却原子化该 block 且丢失状态；
F2 指出“first resumed execution able to run the handoff”仍无可观察执行边界。
问题来自根线程准备的测试夹具和投影，不能归因于官方模型调用配置。

按失败即停约束，本轮没有启动两个 3B 入口，没有自动重试。当前 Story 两轮合计
4 次逻辑模型调用；本轮为 2 次。完整 proof 只读重放成功，原生 planning.prepare
再次拒绝未准入输入，原审计文件哈希和原 855 字节材料均未变化。证据为
`logs/ci/2026-11-05/b-route-story-2-5-build/approved-clarified-real-01/closure.json`。

已离线修正原投影：标题作为 context，保留来源状态限定；原文 F2 明确保持 unresolved，
本地记账因此仍返回 blocked，未伪装为合格输入。另备
`docs/testing/story-2-5-controlled-acceptance/handoff-v3-draft.md`，将草案审批状态放在
外部元数据，改用串行 harness 调用、CallComplete 和十步完成边界。十步仅为新 toy
夹具的可观测断言，不是模型调用预算。该新源尚未获外发批准，也没有真实语义审计；
不能预称其会通过。原生 Step3/4/5 和依赖 Story 继续保持未完成状态。

## 2026-11-05 受控真实验收结果

用户批准的一轮真实验收已在 `s25-positive/audit-01` 停止。官方 Codex App Server
完成 extraction、comparison 两次宿主逻辑模型调用；独立临时线程无工具，返回的
运行时配置为 `openai/gpt-6.1-sol / medium`。服务端实际模型、物理请求数及费用未知。
这两次调用不是连通性 smoke；完整输入、输出、协议、receipt 和预算记录均保留。

审计执行完整，但 finding `F-001` 为 `underspecified`：原 132 字节材料没有明确
接受完成、地图返回完成的可观测边界以及重启时点。提案没有遗漏原句，但重复原句
不能解决这些语义边界。`planning_eligible=false`，不能作为合格 3B 输入。
已按“失败即停、不自动新开重试轮次”的批准条件停止；MVG 与 Capability 的真实
调用均为 0，没有将剩余额度当作继续尝试的授权。290 是整轮上限，不是计划消耗量；
原单批次无修复计划为 19 次，实际只执行了前 2 次。

主线程以原始 proof 只读重放成功；原生 `planning.prepare` 对该真实未准入输入返回
blocked，模型/runner 调用均为 0，审计文件哈希未变。证据入口：
`logs/ci/2026-11-05/b-route-story-2-5-build/approved-real-audit-01/closure.json`。
其中记录了逐次请求字节数、哈希、token 估计、原 finding、负向准入结果及未发送的
855 字节澄清草案。草案没有替换原材料，也没有获得新的外发批准。

修复后定向生命周期测试 6/6、独立 G1/G2 复核 4/4 及最终 planning-input 测试
34/34 通过，均无真实模型调用；3 个最小内存变异均被测试捕获。此前 123 项运行中
的 1 failure、1 error 经定向复验修复，未冒称重新完整运行 123 项全绿。旧基线
131 项的 18 failure/24 error 记录仍保留并已与相同基线对照。完整范围见
`root-engineering-closure-26.json`。工程复核不替代真实 AC；Story 仍为 in-progress，
正式原生 Step3/Step4/Step5 未完成，依赖 2.5 的后续 Story 暂不执行。

实现 owner 为 `_b_route_planning_runtime.py` 的纯数据服务。它接入既有
`run_capability_append`、OS worker/mailbox、`generate_selected_capabilities` 和
`_mvg_capability_checkpoint`，没有第二份 selected/预算 journal。
`_planning_execution_binding.py` 是原始 stdout、OS completion 和 App Server
协议的单一重放 owner；3A wrapper 继续使用其原 request/schema 位置和原身份语义。

## 明确入口

先使用 Story 2.3 的 `--input-stage 3b prepare --planning-contract ...`。
prepare 不执行模型。后续执行要求当前合格 prepared、明确 profile 和 run 绑定：

```powershell
py -3 scripts/python/dev_cli.py plan-mvg --stage generate --run-id b25 --input-stage 3b --planning-profile 3b-mvg-v1 --prepared-ref logs/ci/<date>/b-route-planning-input/<run>/<identity>/prepared.json --runner scripts/python/codex_isolated_model_runner.py
py -3 scripts/python/dev_cli.py plan-mvg --stage verify-selection --run-id b25 --input-stage 3b --planning-profile 3b-mvg-v1 --prepared-ref logs/ci/<date>/b-route-planning-input/<run>/<identity>/prepared.json
py -3 scripts/python/dev_cli.py plan-capabilities --stage generate --run-id c25 --input-stage 3b --planning-profile 3b-capabilities-v1 --prepared-ref logs/ci/<date>/b-route-planning-input/<run>/<identity>/prepared.json --runner scripts/python/codex_isolated_model_runner.py
```

这些格式示例不构成外发授权。实际执行前仍需按原授权核对目标服务、私有材料及用途。
native `plan_mvg.py` 和 `plan_capabilities.py` 使用同名子命令及参数。
`review`、`verify-selection`、`status` 读取已有 run；MVG 无 `--candidate` 的
显式 3B `validate` 也是固定选择复验。带 `--candidate` 的 Story 2.4 读取保持
structure-only，不能携带执行 profile 取得准入。`planning-contract` 只属于 prepare。

缺省仍为 legacy。3B 不开放 apply、catalog adoption、align、reopen 或 Task/Flow
运行资格，不接受旧 Task/readiness/manifest/evidence 门禁混用。3B 执行只接受当前
受规则哈希绑定、支持完整 App Server 重放的官方 Codex isolated runner；未知
profile、非官方执行器及结构声明失败关闭。

## 数据、证据与预算

`newrouge.b-route-independent-admission.v1` descriptor 是封闭、可 JSON 序列化的
profile 数据，冻结 planner、prepared 引用、原输入 SHA、完整 frozen SHA、规则/schema
和 profile 默认预算。父进程和真实子进程解析同一 owner。完整 governed closure 作为
一个 admission unit；不生成旧 Capability/Task/manifest。没有派生或重写 frozen 输入
身份，也没有声称实现按 Capability 派生的性能优化。

generation 每 batch 和 synthesis 均保留全部有序原 drafts、原文、全局分母、约束及
只读 seed。加入 seed、修复材料、独立候选/proof 和实际 schema 后重新测量，最终
runner workspace wrapper 也单独测量并在父账中绑定；容量不足不截断。长 Windows
路径在首次执行前阻断，3B 调用产物使用短 `cN/r.json` 路径，不更改系统设置。

结构/图/来源关系复用 `_b_route_candidate.check`。未解决 source_gap 不参选。
独立语义检查逐项绑定 Requirement、完整 Flow 图、条件分支、handoff、四部分、UI、
人工验证和 source 支持，包括显式选定依赖的原 Flow；找不到原依赖正文则阻断。
已有 ID 及 JSON 类型、数组顺序和值保真。每个 generation 输出与独立 review 分别
重放原始 stdout/协议，绑定实际 prompt/schema/output/runtime_configuration。manual、
external、synthetic 声明及非空 requested-model 字符串不能替代该证明。

MVG 必须恰有三个 admitted 候选才比较，Capability profile 保持两个参选对象及其
原 96 次/2700 秒候选/1200 秒 synthesis/13500 秒 run 默认预算。MVG 默认 192 次，
稳定槽位跨进程、scope、修复和 replacement 累计 64 次。每个稳定 issue 最多三次
修复；父账在 fresh replacement 前持久预留，run 共享三轮，每轮每槽位最多一次。
fresh 请求仅从冻结输入和 accepted seed 开始，旧 proposal/finding 不进入新 lineage。
执行/身份/schema 故障独立归类，保留已付及未知调用，不作为业务 issue 耗尽。

既有协调器锁、Windows Job Object、启动门和 run.json 唯一原子提交点保持不变。
原 staged checkpoint 包含完整 accepted seed/delta/selection/graph/proof，未知提交结果
仍由原 checkpoint owner 恢复。3B 不借 legacy cross-run Capability adoption 注册新
payload；共享 epoch 的失效仍被检查。旧 reopen 入口不能将 3B run 转为另一代并重发
预算。重复无进展失败、缺 receipt、相关 drift 均保留证据并阻断。

固定 winner 复验不调用模型、不另选 winner。成功的 `handoff.json` 保留完整候选、
选中 checkpoint/proof 原引用及哈希、固定来源/审计、规则/runner 配置和逐候选 JSON
差异。`formal_adoption/readiness/runtime_verified` 均为 false。宿主逻辑预留数、观察
耗时与 provider 物理次数/实际模型/费用分开；后者保持 `unknown`。

## 本轮验证与剩余范围

从 nx 运行离线 harness：

```powershell
& 'C:\Program Files\Python312\python.exe' -I -S -B ..\run_story25_tests.py <unique-label> test_b_route_planning_runtime
```

`logs/ci/2026-11-05/story25-tests/runtime_final_05.{json,log}` 是本轮最终新测试记录。
`runtime_initial_01`、`runtime_debug_02` 保留最初的实现/装配失败；`runtime_assembly_03`
和 `runtime_full_04` 保留修复后的中间结果。正向 coordinator 测试明确 patch 执行重放
作为装配 seam；stdio replay 使用本地 synthetic server，生产没有对应 bypass。
真实 OS child 用原 descriptor reader 拒绝非法 profile，不允许父进程 monkeypatch
跨进程生效。它们都不是真实服务调用或真实 AC 阳性。

`legacy_wiring_01` 保留旧相关回归的实际结果，其中两个不存在的测试模块名是本轮
命令选择错误；有效旧失败 ID 与主线程 `baseline-native-01` 的交集相同。不能据此
称旧套全绿。原 Windows 深路径 WinError 3 与此前未准入导致的后继阻断保留，未改
旧断言。主线程冻结后使用正确模块名做独立对照及原生三层审核。

当前没有合格真实 3A 阳性输入，本实现轮真实模型调用为 0。真实 AC-1/2/4/5 的
端到端阳性验收、正式下游 2.6 adoption 和主线程原生审核仍 pending；Story 保持
`in-progress`。离线通过仅支持已逐项执行的合同、装配和负向结论。

## 主线程复核后的修复与补测

`review_reproduce_08` 保留修复前的真实离线复现：3 项中，正式 Flow 义务断言失败，
legacy 和 3B 的已提交 checkpoint 重放均触发 enabled 局部名称遮蔽异常。随后将 runtime
检测明确别名为 `runtime_enabled`，保持原 checkpoint `enabled` 协议门禁；正式 Plan
的 Flow 按其实际 entry/success_end/loops 及共享字段生成独立义务，不伪造 auxiliary
的 graph/UI/human 字段。正式 schema 本来就要求 branches/parts，未放宽这些字段。

新增合法正式记录及候选结构 owner 验证、legacy 实际提交重放和两个 profile 的既有
checkpoint 重放回归，验证原文件、指针、receipt 与调用数不变，也不重新发布状态。
有效 profile 的真实 OS 子进程测试，仅在测试子进程中明确装配上游 prepared seam；
生产 descriptor、append、worker、Job Object/启动门、cost/reserve/outcome mailbox、
实际本地 runner 进程与严格 receipt 校验保持原路径。测试观测到 runner 启动前父
run 已持久预留 1 次、输出尚未存在；synthetic receipt 被拒绝后，已付调用仍保留，
无 selector/checkpoint，重复相同失败不再启动 worker。生产没有该 prepared seam。

3B generation 和 review 现也复用原 stage-cost preflight，向父协调器取得实际剩余
run/槽位预算；不另建预算账。`review_fix_targeted_09` 定向 3 项全过。
最终 `review_fix_full_10` 完整新套 **20/20 通过**，0 failure/error/skip，81.172 秒，
真实模型调用为 0；它仍只支持离线合同、装配及负向结论。

再次冻结及源码/schema 前后哈希见
`logs/ci/2026-11-05/b-route-story-2-5-build/implementation-refreeze-11.json`，
保留初次冻结 `implementation-freeze-07.json` 及所有历史测试报告。真实 AC 阳性、
主线程独立全 diff/矩阵回归及原生审核仍按上述边界处理，Story 仍为 in-progress。

## 集中复核修复与严格绑定验证

本轮将结构 owner 的 schema/输入身份检查提取为同一纯入口；schema 合法的图、归属和
关系业务问题返回稳定 finding，继续进入原三次修复循环。输入、schema、receipt 等
执行故障仍关闭，不转换为业务 issue。来源语义域只解析实际选定 Plan/ledger，合法
的非 JSON text 上下文即使文件名为 `.json` 也完整保留。相同 ledger 的同一原 block
精确去重；不同 ledger 的同 ID block 保持各自身份，冲突原文拒绝。

独立 review 的 `source_block_ids` 现指向请求中 `qualified_sources` 提供的完整
ledger 路径/digest/block 身份，不是可跨 ledger 混用的裸 block 名。每个 source
义务只能引用自己的原 block；其他义务受实际适用来源约束。`findings` 必须与 blocked
checks 的独立 finding 对账，逐义务/原来源/真实 finding 构造稳定身份；不一致的
整体 verdict 或未绑定 finding 拒绝。branch 身份按完整原 body 和重复次数确定，
不随数组重排改变，保留合法的多个同 kind 正式 branch 及原新 issue 拒绝门禁。

generation/review/selector 的每份嵌套 binding 均重新匹配原 run 账中的已付槽位、
代际、execution、context、phase、workspace/output 与原 worker 预留；fresh lineage
从实际 run/slot/seed/context 重新计算。完整 OS stdout、协议和生成的 journal/stderr
原字节哈希一起复验。Windows journal 的 CRLF 与 receipt 的 LF 仅比较时核对精确
换行关系，原文件不改写。借用另一槽位或 run 的真实 binding 也不能代替当前证明。

完成后的 generate 为经过原 proof/checkpoint 复验的无写入 no-op，保原耗时和 handoff。
新 verify-selection 仅接受明确 3B profile/prepared 合同，legacy pending 不再返回
验证成功。selector 已完成但未发布 receipt 的中断持久失败关闭，不再付费重发。
Capability 保原 2700 加支持 synthesis 时的 1200 候选活动池、13500 总活动池及 96
请求；不足一秒的适用额度在预留前拒绝。既有 worker 监视循环在适用的 Capability
剩余额度内守护准备/本地验证并回收其独占进程树，已付/unknown 证据保留。MVG 仅保
原逐调用 timeout（含调用者显式值），不移植 Capability 的累计秒数限制。

模型端 generation 仅发送完整实际 `$ref` 闭包 common/flow-graph/planning-candidate
三个 schema，原 schema 与 validator 未改。主线程拥有的 host proof 归档及完整 core
无损编码独立验证，原默认输入上限为 96000；本轮未改变计量 policy、旧 30000 测试
或增加原默认预算。

最终定向记录 `repair_final_17`：仅运行本轮修改所覆盖的 15 项用例，**15/15 通过**，
0 failure/error/skip，105.172 秒，真实 provider/model 调用为 0。新增完整协调器测试
使用实际 OS isolated runner 和明确标注的本地 synthetic stdio 运输；不替换
capture_binding、verify_call、verify_reserved_call 或任何 proof validator，覆盖
三个候选共十次 fixture 预留、真实 selector sandbox 全部材料、checkpoint/handoff、
完成后无写入重放及借用真实其他槽位 binding 的拒绝。时间测试另用明确受控 clock/
账务 seam 观察协调器预留与 worker 实际派发 timeout，一并覆盖未知结局的进程回收。
这些是工程合同/装配证据，不冒充真实 AC 阳性。早期 `repair_*_12` 至 `_16` 的失败和
定向修复结果均保留；主线程负责返回后的完整独立验证。

生成阶段以冻结 DRAFT 合同为基底，为主机已知的 `input_identity`、`stage`、`ordinal`、
有序 `parent_draft_identities` 添加请求专属 `const`。实际 producer 使用严格闭合的
`newrouge.b-route-draft-carrier.v1`：保原 schema_version 及四个元数据，另声明固定的
producer_schema_version，任意完整 content 对象通过非空 content_json 字符串无损运输。
唯一解码器拒绝未知版本／字段、重复键、非 JSON 常量及错误类型；不补写模型内容。
原始 carrier JSON、schema、prompt、协议／receipt 原字节仍由原 binding 保存，独立
canonical-draft.json 保留完整规范草案；计费重放从原 carrier 再解码并逐类型核对。
派发、bound materials 和 reservation 重放均从绑定冻结输入及全部前稿独立重建请求
并复验实际 schema。原 frozen schema、完整 drafts、候选／draft 校验和 legacy 行为不变；
generation、review、selection 的字符串常量／枚举补等价显式类型，语义规则不变。

review 的 wire producer clone 保守省略文档未列出的 `uniqueItems`，仅作为生产 schema
子集兼容性处理，不声称实际服务已因此拒绝。原 review_schema/review_issues 仍严格
强制来源 ID 唯一；重复 ID 的模型输出拒绝，不修补。实际 wire schema 在派发及
bound materials 重放中独立重建并精确核对。


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

## 完整材料共享与最终内容目标

新建原生 3B run 在不可变 `planning_runtime.wire_delivery` 中绑定 `newrouge.b-route-complete-materials-wire.v1`，并纳入 runtime 身份与每次真实请求的预留记录。历史无该字段时仍按原 plain／core 请求和字节复验。公开 `planning.build_request` 继续原完整 root 容量行为；固定版本的 `build_wire_request` 复用同一冻结输入、原容量配置和完整草案链检查，供既有执行路径构造 canonical 材料，最终实际 runner wrapper、schema 与全部可见文件仍在原限制内先测量后预留。

`_b_route_planning_wire.py` 复用原 lossless codec，统一编码完整 generation／admission／selector 材料，不使用投影、摘要或外部定义。canonical 身份与保持字段顺序、JSON 类型和原字符串的字节 digest 分别绑定；严格恢复拒绝未知或混合版本、悬空／循环引用以及内容篡改。原引用形状的用户键和嵌套旧 core 各有独立命名空间。实际 codec、transport 依赖和新 helper 均纳入原规则／工具身份，相关源码变更仍使旧 3A 当前复用失效；历史有效证据不会据此改写。

generation 收到完整候选 schema 引用闭包和明确的 `/properties/content` 最终目标，以及现有投影、owner、引用使用和图结构的技术规则。新指令区分输入无损保留与新业务内容生成；完整前序草案继续作为输入／provenance，不能因而把编排对象复制到最终 content。batch 保留原开放 draft 合同，最终输出继续经过原规范 schema、来源、owner、图、累计 delta 和独立准入。carrier 保留每个实际输出值；主机不删除错误字段、不修复业务内容，不把原 w10 失败输出作为新 seed 或合格候选。

selector 的 A／B／C、accepted-seed 与完整 comparison-context 原宿主文件仍逐字节保留。新模型请求将完整结构化虚拟文件一起共享，sandbox 只携带 prompt／schema，避免再重复发送原 JSON 文件。旧 comparison-context 的中间编码先严格恢复为新 canonical 材料，`decoded_from` 明确标记该转换；原宿主文件的 raw digest 仍单独绑定，不能声称旧编码字节等于新 wire。每次派发和 proof／reservation 复验均从原准入产物、冻结 authority、seed、scope 与盲别名重新构造完整值和原文件，不能只比公共 hash。seed 不参选，候选全准入、固定 winner、唯一 checkpoint 及原预算／超时保持不变。

本修复仅产生离线工程证据。真实 v1 wire、高档位两入口准入与选择仍须主线程取得新当前 3A／prepared 后按剩余同一 campaign 实际执行；不据压缩预测或 synthetic transport 宣称真实验收通过。

宿主虚拟文件在派生文件名前复用既有 profile 别名域与 candidate 双射检查，随后由原 `checked_path` 验证包含关系和 reparse 边界再读字节；该门禁同样覆盖先于 prefix 别名复验发生的 reservation 重放。scope index 在 lookup 前必须是原 scope 域内的真实整数，重哈希的 False 不能冒充 0。这是复用现有路径和元数据合同，不承诺抵御恶意并发拓扑替换。
