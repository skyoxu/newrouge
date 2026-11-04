---
title: 'Story 2.1：累计来源 Ledger 与 Requirement／验收意图提议'
type: 'feature'
created: '2026-11-04'
status: 'done'
baseline_commit: '8f13efd02d44ad234eb2c739ad09d59248346f7b'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-2-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 现有 Chapter 3 能登记来源、解析 Ledger 和分批投影，但缺少 B 路线无 Task 的完整原字节证明、显式验收意图、提议身份和真实阶段观测；直接套用后置 Task／readiness 会使尚未实施的需求消失。

**Approach:** 提供薄的 3A 来源记账入口，复用现有累计注册、解析、稳定块身份、完整对象／无损传输和投影守恒。先准备完整输入，再消费明确语义提议；输出逐块 Requirement／验收意图或有依据去向及未决问题。只有新的 logs 产物，不形成正式采纳。

## Boundaries & Constraints

**Always:** 对照本轮 `epics.md:750–797` 的 AC1–5 及其 Refs；以 `chapter3-source-set.json` 的现行累计注册为起点，显式新增／退役并保留历史，不复活三份已退役 GDD。保原生文本 hash／块 ID 的既有语义，同时另存原 bytes 和身份，不能混用。每个来源、语义块和跨批引用可定位；原文、顺序、文件／块 hash、全局记账与未知完整保留。Requirement 提议包含来源块、明确验收意图和非 Task 去向；新 proposal 与正式持久 ID 区分，已知旧身份保回链。accounted 不代表 satisfied；语义提议及有定位依据的退役也不等于独立审计或正式批准。

**Never:** 要求假 Task／Chapter 5 witness／现有场景，按旧 Task 状态裁来源，启发式编造验收意图或把数量当覆盖。不得改游戏、任务三联、累计 manifest、现有采纳／源注册或旧 proof，不调用模型、apply／发布／恢复、Knowledge stable、默认 B 切换或 A 退役。不能创建第七类正式记录或提前分配正式规划身份。T108 缺失及 Epic1 五项 false 原样保留；若实际来源引用缺失原件则明确失败，不伪造。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| 零 Task 完整记账 | 累计注册＋明确新增；每块显式提议／去向 | 完整 Ledger、验收意图、逐块 accounting；不读 Task 作为准入 | 没有 Task／readiness 仍合法 |
| 共享／其他验证／延期／范围外 | 跨块投影或明确原因及来源定位 | 保累计责任、原文和提议，不声称满足或正式验证归属 | 缺理由／未知／歧义保留 unresolved，阻断完整结论 |
| 长对象／跨批／空来源 | 完整 UTF-8 原文，含 CRLF／尾空白及空 JSON | 原 bytes 可重建，完整对象不截断；空或未解析来源有显式文件级去向或未决 | 缺批／重复／乱序／遗漏／不完整引用／容量不足阻断 |
| 漂移／损坏／非法退役 | 读取失败、无依据退役、glob 成员或输入变化 | 定位受影响文件／块及重审范围；保原来源和证据 | 结构化诊断，不静默缩源或继续成功 |
| 重复／失败／危险输出 | 相同 event、已有目录、越界／junction／源别名 | 不覆盖旧文件；安全准入后的成功／失败均有真实终态事件 | 同 event 不重复入账；参数／输出准入失败退出 2 |

</frozen-after-approval>

## Code Map

- `scripts/python/build_source_ledger.py:387/420/488/511/590`：原生 parser、add 稳定块 ID／delta、累计 patterns／显式退役、glob。复用这些 owner；必要时增加默认行为不变的只读 byte／JSON callback，不复制 resolver。原生 `read_text` 和 `rstrip()` 意味着文本 hash 不证明原始 bytes。
- `scripts/python/project_semantics_from_sources.py:96/269/399`：无 Task 的完整 block batching、候选准备及逐块 compile。prepare 会删除既有 batch 文件，只能用于全新本轮目录；compile 丢掉 acceptance_intent，B 层明确保留它并使用 proposal key，不改变旧消费者输出。
- `scripts/python/validate_semantic_conservation.py:41`：复用 projection 校验，不调用 Task closure／covered。其 `sha256_file` 同样基于 read_text；若增加只读 callback，保持旧换行及 hash 语义和默认路径，不能误称 raw。
- `scripts/python/_mvg_evidence_transport.py:376/455`、`_mvg_lossless_context.py:53/188`：复用原文切片、顺序、逐字符重建和 request-local 还原；不沿 Task 过滤的 `_capability_input_integrity.project_source_batch`，不引入 MVG 任务准入。
- `scripts/python/_b_route_codec.py`：唯一 strict JSON／raw digest／安全读取／公共诊断；`_b_route_inventory.py`、`_b_route_protection.py` 的原祖先／reparse 和输出保护可复用。原根别名与真正 junction 分别处理。
- `docs/workflows/b-route-record-contract.md:77–90`、`docs/planning/b-route/schemas/plan.schema.json:16–74`：正式 source identity／Requirement 合同；本轮仅兼容交接数据，不生成 plan 或新 schema owner。
- 现有 `test_chapter3_semantic_conservation.py`、`test_milestone_incremental_hotfixes.py`、`test_mvg_evidence_transport.py`：累计、完整 JSON 切片、稳定身份、batch 所有权、原文传输的默认行为回归。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/python/_b_route_sources.py`：新增唯一 3A 编排 owner；prepare／account 两阶段、明确 declaration／proposal 载体、原字节归档及末尾重读、守恒／提议／诊断／事件。只使用独立新 logs，不写版本化 source-set。
- [x] `scripts/python/build_source_ledger.py`、`scripts/python/validate_semantic_conservation.py`：仅在安全观察读取确需时增加可选只读 seam，原入口默认语义不变；必要的退役及 prior active_sources 检查沿原 owner，不复制另一套累计规则。
- [x] `scripts/python/account_b_route_sources.py`、`scripts/python/dev_cli.py`：直接入口与 `b-route-sources` 同 owner；严格参数、单 JSON／退出码及最早禁止字节码。help 说明阶段和不具备正式采纳权限。
- [x] `scripts/python/tests/test_b_route_sources.py`：验证矩阵及独立 CLI 正负例，真实故障注入／跨阶段漂移／重复 event／完整对象及原文件保护；有真实 Windows 短路径／junction 检查，Linux 不冒充通过。
- [x] `scripts/python/tests/test_milestone_incremental_hotfixes.py`：修正 Windows 原生控制暴露的既有测试夹具 hash 口径；显式 CRLF，使用现有 normalized digest，保原正负断言及生产校验不变。
- [x] `docs/workflows/b-route-source-accounting.md`、`AGENTS.md`、`workflow.md`、`docs/workflows/stable-public-entrypoints.md`、`docs/workflows/script-entrypoints-index.md`：唯一 owner 用法和 3A 路由，明确 prepare／完整记账／独立审计／正式采纳不同，现行 A 有效。
- [x] `.github/workflows/story-2-1-windows.yml`：协调器负责专用独立代码测试分支、固定 SHA 检出、最小权限、精确测试／CLI／真实 Windows 路径检查、仅本轮合成日志和原字节守卫。实施 agent 不做 Git／远端操作。
- [x] 当前 spec／`sprint-status.yaml`：仅协调器同步当前原生阶段并保留全部证据，不发布内部材料；收口本地提交由原生 Step5 执行，不充当前置实施门禁。

**Acceptance Criteria:**
- Given 无 Task 和 readiness 的显式累计输入，when prepare＋account 完整执行，then AC1 的每个文件／块身份、定位、提议／验收意图或理由均能独立核对，不要求后置对象。
- Given 共享、其他验证、延期、范围外和未决来源，when 逐块核对，then AC2 的累计责任和所有未决明确保留，完整记账与满足／语义审计结论分离。
- Given 长对象、多批及 CRLF／空白，when 生成和故障修改输入，then AC3 证明原 bytes、完整对象、顺序／引用／全局守恒；截断、缺批、重复和无法重建均失败。
- Given 源、声明、候选或准备产物发生漂移／损坏及无依据退役，when 复验，then AC4 定位影响和重审范围，旧成果／注册／三联／manifest／proof 原字节不变。
- Given 成功、失败或重复 attempt，when 读取事件及 stdout，then AC5 的 run／scope／stage／attempt、实测 active elapsed、明确零模型 dispatch、reuse／termination 真实且同 event 不重计；未知显式 unknown。

## Implementation Notes

2026-11-04／协调器：实施者完成新 owner／入口／最小读取 seam／20方法及导航。完整1479行初始diff已独立读取；当前Linux新方法19pass＋1真实Windows专属skip，原生54＋10＋37全pass；root独立17次CLI正负调用通过。3439保护文件初验不变，真实prepare的5观察／19产物raw绑定核验通过，仅活动GDD一份139块，保三历史退役，未记账／独立审计／正式采纳均false。文档改中文并修导航表格pipe；不改冻结意图。

2026-11-04／Windows第一轮：代码专用1a4fc1fa42d56310582ff7ed9806d85e51ec7c0f，run41812029915/job126513369851自然failure。101原生控制100pass／1fail，新20方法与17CLI未运行，不计作通过。81706bytes原始日志SHA65f32c209b128245d9fe959bfc73e4dcdcd62fc238c7bf317c9527155c9414e7完整保留。根因可执行复现：旧fixture用raw _file_sha构造证据，但生产validate_milestone_regressions要求normalized_file_sha；强制CRLF时旧断言同样失败。仅测试fixture显式CRLF并改用现有normalized owner，原所有正负断言和生产Chapter6代码不变；10项定向回归通过。增加该测试文件至本轮技术范围、CI源码身份记录；保护原始前像并明确一份已授权测试fixture变更，不伪称3439全未改。

2026-11-04／最终Step3验收：JSON错误仅补精确entity_id，唯一codec原reason/stage/expected/actual不变；新增2方法。root重读含全部未追踪的1867行full diff及之后workflow两行环境守卫patch，当前Linux22中21pass/1Windows-only skip、独立17CLI及两种公共解码反例均通过。第三轮固定a3dbdc5df32651f95c23cccf8cabaa29253b6e05/run41813417201/job126518060308自然success，110652bytes原始SHAf1c395f0df63a08a671a8b41780c5bec531041bb763d5e2d3c17abdcd64e0f9d逐项核验：101原生＋21source=122实际pass，1POSIX-only skip单列，强制Windows方法/17CLI/14源码blob（13rawexact+1精确CRLF）/3447tracked无变/无缓存通过，明确清除子进程bytecode环境覆盖。所有5矩阵行都有当前Windows实际通过方法，POSIX对应在Linux实际通过；原T108与五false未变。3438非owned文件不变，1原生控制fixture明示三行兼容修正；未修改生产Chapter6。原生三层评审尚未开始，Story保持in-progress，不把CI绿当独立审计或正式采纳。生命周期本地提交留Step5，避免把后置收口写成Step3自前置。

2026-11-04／原生Step4收口：三层均独立完成，9条原评审逐条先判定（8medium／1false），root另1条medium经独立矛盾缓存复现；随后8组最小patch回同一实施者，无defer／intent_gap／bad_spec，review_loop_iteration仍0。保16文件两轮完整前像，未丢dirty。365行合并patch完整核读，原有effective／previous逻辑共用，真实输入优先重建，不新增公开格式／字段／入口／权威。Linux30方法29pass＋1Windows-only skip、原生101pass、17CLI、两help及最终真实prepare均通过；当前实际源一份139块／3历史退役，5原输入和19产物绑定验证，accounting_complete/独立审计/正式采纳false，无-B也无缓存。最终固定edd061fdf97982f37437db33e1aa439f405f3222/run41817232590/job126530968843自然success；115243bytes原始SHA2e65e22b987dbba21a619b353389266508a641eef80d947e1f9e3060811dccb6，101原生＋29source=130实际pass，1POSIX-only skip单列，强制8.3/junction、17CLI、14Gitblob（13rawexact＋1精确CRLF）、3447tracked不变／无缓存均核验。8组对应真实Windows反例均pass；原误报由新写失败1与既有partial准入2区分反证。3438非owned文件不变，1旧控制fixture仅已说明三行CRLF修正；Task／游戏／manifest／Epic1旧材料及T108缺失／五false保留。进入Step5仅本地收口，不推进B启用或A退役、不推内部资料。

## Spec Change Log

## Review Triage Log

| Finding | Verdict | 独立证据／反证 |
|---|---|---|
| BH1 | medium | 大写UNRESOLVED的context atom被放行；root隔离复现exit0/complete=true/unresolved=[]。原生status会strip/casefold，B前置判断未对齐。 |
| BH2 | medium | --previous仅核旧注册retirements，未核上轮声明的完整retired_sources；root复现旧退役从有效集合消失且原source重新进入manifest。旧raw proof仍在，问题是有效累计退役静默撤销，不声称历史bytes丢失。 |
| BH3 | false | 公开doc:76的exit2指参数/输出准入及既有冲突/partial event；新准入后终态写失败明确partial_write不声称持久化。root注入first write失败exit1，随后同key既有partial再用exit2，正好符合两种不同状态，不能把新失败等同既有partial准入。 |
| EC1 | medium | root复现历史docs/*.md退役＋显式docs/nested/new.md新增，prepare/account均成功但manifest只有keep.txt；前置Path.glob组件匹配与原生retire fnmatch跨slash匹配不同。edge guard_snippet为建议guard，判定依据实际源码和复现。 |
| EC2 | medium | root分别复现padded block unresolved且non-delivery，以及大写context atom unresolved，都exit0/complete=true。与BH1同规范化错位根因，但本条独立包含block去向结果。 |
| EC3 | medium | root以object statement复现exit0/complete=true且requirement-proposals保留object，原生中间语义却str()转成文本，两份交接类型分歧；需明确非空文本。 |
| EC4 | medium | root以empty JSON文件和object reason＋真实raw引用复现complete=true，file_accounting保存非文本reason；不能证明现有合同要求的明确文字理由。 |
| EC5 | medium | root以output_accounted_count=input+0.5复现complete=true；原生int()丢小数后当精确守恒。B声明批总数须真实整数，不能靠coercion校正。 |
| VG1 | medium | 按原生规则接受pre-verified gap：跨批共享同proposal非空intent冲突缺回归；仅绕过body一致性guard，123现有测试122pass/1Windows-only skip但冲突falseaccept。原实现拒绝，变异后保留后一个intent。原始JSON证据已核读保留，不重复变异全量。 |
| ROOT1 | medium | 独立合成复现：实际source-set及prepared.source_registration均登记docs/source.md与docs/other.md；仅将派生scope及Ledger/batch/transport缓存重建为source.md并重算临时artifact digest，原注册和来源bytes不变，account仍exit0/complete=true。receiver使用cached effective_patterns而未从实际注册/声明owner复算，raw hash自一致不能证明累计范围一致。 |

## Design Notes

技术决策：无剩余产品意图缺口；核心流程无不可逆写入，远端只限用户已授权专项测试分支／CI；影响新 owner／CLI／测试／导航及现有 parser 的最小 seam，故 dispatch。BMAD Story／spec 跟踪工具开发，并执行适用来源与守恒规则；不借 1.2 纯治理豁免，也不制造游戏 Task 或强调后置 Chapter6。

CLI 采用 `--stage prepare|account --root <repo> --run-id <id> --scope-id <id> --attempt-id <id>`。prepare 必须显式 `--source-set <path>`，可有 `--declaration <path>`、`--previous <prepared-ref>` 及 batch／transport 容量；account 必须 `--prepared <path>`、`--candidate <path>`。路径／ID 严格且无危险默认。新产物目录 `logs/ci/<UTC-date>/b-route-sources/<run-id>/<attempt-id>/<stage>/` 排他创建。成功 0、可定位输入／记账阻断 1、参数／输出准入或同 event 冲突 2；参数错误不承诺无法写入的持久日志。

prepare 保存 native manifest／ledger、原文 bytes 及 raw identities、完整 batch index／内容／transport proof、待填写 candidate 和 report。account 复验全部准备身份、原始来源及集合成员、原始解码／批数据和候选绑定后调用 native compile／projection。显式候选带验收意图及 source-backed disposition；prepare 不生成“已审阅”语义。纯规则拼接占位验收不算完成。未知输出仍保留来源和局部提议，`accounting_complete=false`；`satisfied`、独立审计、正式采纳均不授予。

declaration 是版本化本轮载体，不是第七类正式记录：显式 additions、retirements，每个新退役有非空理由与可定位原字节来源／审阅依据。沿既有累计 owner 计算有效输入；保旧退役及被移除来源定位，缺理由、冲突、未声明消失阻断。仅核定位和身份，不自证语义审阅。源码注册更新仍留显式受治理操作，本工具不写。

提议的 `proposal_id` 属明确 proposal namespace，`prior_requirement_ids` 仅旧身份回链；`source_block_ids`／`acceptance_intent`／`non_task_sinks` 与既有正式交接语义一致。native compile 所需中间 requirement key 使用 proposal key，不将确定性 key 宣称成正式分配。文件级空／未解析范围有明确去向或 unresolved，不能靠零 block 从全局分母消失。原生文本 hash／块 ID 保持兼容；原 bytes 归档覆盖 CRLF、尾空白和未形成语义块的字符。长对象整块进入 semantic batching，传输层可分片但须由既有 validator 完整还原；容量不足明确失败，不能截断或用摘要替代。

原生复用细化：Task-free transport context 使用 `chapter5:{}` 和 `evidence:[{path,sha256,text}]`，可有真实 proposal requirements，但不传 scoped evidence schema／model_text。沿 `plan_transport(..., phase='inspect', schema_version=TRANSPORT_SCHEMA)` 与原 `plan_errors`；probe 使用 `_capability_input_integrity.measure_request` 核含 schema 的最终请求，零 dispatch。语义完整对象预算与传输请求预算分别验证；分片可还原不代表每次请求已见完整对象或语义正确。parser 可从 `parse_source` 抽出纯文本 helper，原 wrapper 保默认；B 层用同一安全 bytes 的 universal-newline 文本视图；projection 可选 hash callback 返回该文本 hash，不能拿 raw digest 代替。

每个准入后的终态保存不可重复 event key `(run_id,scope_id,stage,attempt_id)`、实测单调活动秒数、零 dispatch／非账单预算、明确 reuse_reason／termination_reason；同 key 再运行不改原 report／event 或重复计数，部分写入须诊断而不假装完成。新 attempt 可重新核对；不实现采纳 journal／自动恢复。所有已观察文件／不存在状态及 glob 成员在结尾重读，漂移使结论失效。

协调器独立核对完整 diff、原始测试输出与 AC；Linux 定向回归后，构造只含本轮实现／测试／owner 说明和专项 workflow 的代码分支，以已公开 1.6 代码候选为底，不推本地内部历史。记录完整远端 SHA／每文件 blob、runner 实际来源及所有测试终态；Windows 要真实运行，不以旧 CI 代证。

## Verification

**Commands:**
- `py -3 -B -m unittest discover -s scripts/python/tests -p test_b_route_sources.py -v`：新行为和矩阵通过；Windows 强制真实路径检查无跳过，Linux 如实标注平台限制。
- `py -3 -B -m unittest discover -s scripts/python/tests -p test_chapter3_semantic_conservation.py -v`：原生累计／解析／批处理默认行为保持。
- `py -3 -B -m unittest discover -s scripts/python/tests -p test_milestone_incremental_hotfixes.py -v`：显式退休和累计防丢失默认回归。
- `py -3 -B -m unittest discover -s scripts/python/tests -p test_mvg_evidence_transport.py -v`：原文传输／完整还原默认回归；若复用 seam 未改该模块，可选出确切相关现有控制，不重复无关重型测试。
- `py -3 scripts/python/dev_cli.py b-route-sources --help` 及直接入口：帮助可用；独立合成根目录 prepare／account、未决／损坏／缺输入／无依据退役／输出冲突／同 event／长对象／零 Task CLI 正负例，核单 JSON、退出码、产物 raw 和原文件不变（包括无 `-B` 的脚本副本）。
- 对真实现行 source-set 执行只读 prepare，核默认只含当前注册的 GDD，保三份历史退役，不以未审 candidate 宣称完整或 3B ready；原 Task／游戏／manifest 和 Epic1 历史材料 hash 不变。
