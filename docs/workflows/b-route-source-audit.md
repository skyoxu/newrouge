# B 路线 3A 独立来源审计

`_b_route_source_audit.py` 是审计 owner，通过既有 `account_b_route_sources.py` 与 `dev_cli.py b-route-sources --stage audit|verify` 进入。来源 prepare／account 仍由 `_b_route_sources.py` 唯一拥有；其共享只读接口重新验证终态 event、全部产物、原字节／glob、原生完整解析、注册推导和机械 accounting。合法但仍含 unresolved 的 account 可以进入审计，其未决项始终进入最终阻断。

本入口不需要 Task、Chapter 5 readiness 或所选 Flow。只写新 logs 和同一 run 的预算证据；不写来源注册、累计 manifest、Task 三联、游戏、正式规划记录、Knowledge stable 或旧 proof，不启用默认 B。T108 历史证据缺失、正式保护资格及 Epic 1 五项 false 权限保持不变。

## 两步独立性

1. 每个完整来源文件在 fresh 无工具 runner 会话中独立提取。请求含该文件全部原 bytes（base64）、原文、原生块和顺序，不含首投影。空文件也进入文件分母。
2. 全局比较在另一个 fresh 无工具会话中读取全部原文、全部 extraction、完整首投影、验收意图及去向。全局依赖是全部来源，不能只看已引用的 Requirement／Flow／Task。完整请求无法容纳时直接 capacity 阻断，不截断、不替换摘要。

模型提供义务、遗漏／冲突／未知等 finding 和明确的 disposition 审阅。协调器严格复验 JSON schema、逐文件／逐块／逐义务分母及顺序、已存在提议 ID、原字节 digest、精确 UTF-8 byte range 与 quote、块内定位、责任和阻断分类。完全未投影可使用空 `affected_proposal_ids` 并设 `unprojected=true`。模型自报 approved／PASS 不授予资格；额外 schema 字段直接拒绝。延期／范围外接受必须附来源原文依据及独立审阅理由。机器只能证明结构、定位和执行完整性，不能证明任意业务语义正确。

## 运行

Windows Python 3.12+，使用仓库 B 路线依赖安装合同（`requirements-b-route.txt`）。runner、accounted、audit-ref 都采用精确仓库相对 POSIX 路径；根短路径按既有合同解析为真实根，后代别名、symlink 和 junction 拒绝。attempt-id 不得使用预算目录保留名 `reservations`。显式选择可信本地 runner；其 transitive Python 源码、相关可执行文件、Python 与结果相关依赖版本均绑定到审计 identity。

```powershell
py -3 scripts/python/dev_cli.py b-route-sources --stage audit --root C:/work/newrouge --run-id reward-audit --scope-id reward --attempt-id audit-01 --accounted logs/ci/<date>/b-route-sources/source-review/account-01/account/report.json --runner scripts/python/codex_isolated_model_runner.py --expected-model <actual-model-identity>
```

audit 可选 `--citation-guidance full-block`，向无工具 producer 追加指导：复制所引用块提供的完整 `citation_span`，保留 quote 尾部换行、回车、空格及标点，避免自行计算局部 UTF-8 偏移。该模式绑定到原始请求、阶段输入身份、工具／提示词身份与精确 proof 重放；仅该模式的模型 workspace `input.json`／`schema.json` 使用紧凑 JSON，完整保留对象、顺序、类型及原文字符串。未指定时保持原默认提示词及序列化字节。prepare／account 拒绝该审计参数，未知模式在 reservation／dispatch 前拒绝。指导不新增业务准入条件，也不放宽原引用校验；精确合法的局部引用仍有效。verify 默认从被验证的原始请求读取模式，历史请求没有该字段时仍按原默认重放。

新建 full-block 审计绑定 `producer_schema_policy=input-identity-span-ref.v6`，沿用 v5 完整 producer 输入的请求本地无损共享，并追加下文独立分类与不确定项保留指令。实际输出仍沿用 v4 的 span-ref 语义及 producer schema 子集：顶层与 finding 的已知 `input_identity` 常量、字符串类型、必需字段、const／enum、对象闭合与范围保持；仅 producer schema 省略字符串 `pattern`／`minLength`，最终规范校验继续拒绝空字段和仅空白字段。这不证明某个关键词不受服务支持，也不推定实际助手输出上限。

v5 的实际 `input.json` 是显式 `newrouge.b-route-source-producer-input.v5` carrier，包含策略、阶段、原 canonical input_identity 和 `complete_materials`。它复用既有严格完整材料 helper／lossless codec，共享完整 files、原文、raw_base64、blocks、机械 candidate／proposals／accounting、全部实际 extraction 和 span map；不删除字段、改变 JSON 类型／顺序或用摘要替换原文。原 `phase_input`、canonical 身份和业务分母保持不变。模型提示明确区分请求本地 `$mvg_ref`／转义字面键与输出 `span_ref` 的冻结来源定位空间；完整定义随请求送入，不要求工具或外部缓存。

内部纯接口 `decode_producer_input(actual_input, policy, *, expected=None)` 恢复完整原 phase 公共字段及 producer_transport。v5 内层完整保留 v4 producer 输入，包括原 v4 span map；外 carrier／策略才标记 v5。省略 expected 只做内部完整性检查和内容查看，不授原始来源权威；v5 提供独立重建的 canonical phase_request 时，还精确核对全部值、类型、顺序及原 span 材料。旧策略继续原输入语义及后续字节／协议门禁，不把 v5 的顺序约束加到旧 plain 输入。prepare 与 proof／verify 均按捕获策略重建同一实际 carrier，原始 prompt／schema／最终 runner wrapper、计量、持久预留、实际 raw 输出和协议分别绑定；新派发的策略或输入 delivery 混用在预留前拒绝。超限仍先于派发拒绝，不提高原请求设置、受控任务 30000／1MiB 或 high／调用预算。

实际输入保留全部原文、原始 bytes、对象和类型，另附按原文件／块顺序编号的 `span-000001` 引用表，每项包含来源 path、raw digest、block_id 和精确字节范围。模型自行选择完整块的 `span_ref` 或原有完整 literal 引用；主机只将模型选中的引用严格展开为该范围的原字节，不选择依据、不修正 literal、不补写业务字段。未知或混合引用失败关闭，合法局部 literal 引用仍被原校验接受。原始模型输出和协议完整保留，`canonical-output.json` 明确是模型所选冻结来源引用的解码视图，报告与 proof 均标注来源。

proof 从冻结原始输入独立重建引用表、实际输入／schema／prompt，并验证原字节、计量、receipt 和协议后再解码，继续执行未改动的规范输出与引用／业务校验。旧 v4 保留其完整 plain producer 输入，v3 保留原字符串限制；v2、v1 及无 policy 的历史记录也分别使用原 schema、输入和提示字节，不以当前默认策略解释旧证明。未知／混合版本、悬空／循环引用、原始输入／摘要／span map 篡改、跨策略复用或解码视图篡改均失败关闭。默认模式及阶段业务身份保持原样，无新增 CLI 参数；传输共享不减少完整输入、分母或原每文件 extraction 加一次 global comparison。相关工具源码漂移照常阻止旧 current proof 复用，历史有效记录不改写。

`--expected-model` 必须与可信 runner receipt 的实际 `model_identity` 完全相等（包括有值的 provider 前缀）；不接受 `environment-default` 或 `default` 代称。`--describe` 只证明 runner 合同，不能证明认证或模型调用成功。每次执行须有协调器捕获的 OS 完成结果、实际模型 identity evidence、无工具 receipt、单次完成／dispatch 计数及精确输出。失败或观察不到 provider dispatch 时写 `unknown`，不冒称零调用或已知账单。

受控任务仅可在其子进程显式设置 `NEWROGUE_CODEX_REASONING_EFFORT=high`，通过官方新 ephemeral 线程请求 high；未设置时保持原 CLI、请求和证明字节，其他值（包括新的 low 请求）在实际执行前拒绝。可信 description 的可选 `requested_reasoning_effort` 进入工具／复用身份；3A 使用捕获的 runner.json，3B 使用 reservation 哈希绑定的 runner_info，要求协议原请求与独立返回的 `reasoningEffort` 均为 high，防止子进程丢失环境而退回默认。历史 low 仅按原捕获配置只读重放并保留 low 标记，不能充作 high 证据；重放不读取当前环境。此选项不改变模型、原预算、无工具／只读边界或全局配置，provider 实际模型、物理请求及费用仍未知。

Codex runner 使用官方 App Server 的 stdio 协议，在独立目录创建 ephemeral 线程，绑定 `thread/start` 实际返回的 model、modelProvider、reasoningEffort、thread ID 与本次 turn ID。`official-codex-runtime-bound.v1` 回执只验证运行时配置，明确记录 `model_identity_scope=runtime_configuration`、`provider_reported_model=null`、`provider_identity_verified=false`、`provider_dispatch_count=unknown`，不得表述为服务端实际模型身份已验证。完整主机输入输出协议、最终完整请求、严格 schema、输出和工具限制摘要均绑定哈希，协调器在执行和复用时重建验证；请求参数、助手文本、stderr 与保存的 sessions/rollout 均不能代替运行时响应。缺证、跨线程、改路由、失败、工具调用及输入输出不符均失败关闭。OpenAI API runner 仍直接绑定真实 `response.model` 与响应 ID；两类证据的范围分别标注。

实际接收的服务端 error.message 或 error.additionalDetails 首次包含 `max_output_tokens` 时，先保留原始 journal，再立即失败并经原清理路径终止自有子进程树，不等待相同内部重试耗尽；不读取任意助手文本判错，也不改变网络设置或退款已预留调用。其他通知遵循原行为：原本允许的 legacy transient 通知仍可完成；v2 `method=error` 即使标记 willRetry，最终严格 replay 仍拒绝，未扩大其接受语义。provider 物理重试及费用保持 unknown。

无工具限制使用进程级 feature 开关及线程级嵌套 config，逐一禁用已有 MCP 并核查新线程清单。官方模型目录可能强制启用 code mode，因此 runner 通过官方支持的临时 `model_catalog_json`，仅将客户端工具能力改为 direct、禁用 shell/patch/实验工具/多代理；保留各模型 slug、指令及其余元数据。原始模型目录、受限目录摘要和启动命令一并记录以便复核；不修改全局配置、认证、网络、权限或已有会话。逻辑请求计数表示 App Server turn；服务端内部请求次数保持 unknown。

每个 audit step 仅将 `input.json`、`schema.json`、`prompt.txt` 放入固定受限 workspace，再使用公共隔离 runner 生命周期。保存完整最终可见 request、schema、prompt、measurement、原始模型 output bytes、OS stdout 原 bytes／returncode／耗时、receipt 和 reservation。模型调用期间不持全局 metadata 锁。

输出为独占目录 `logs/ci/<UTC-date>/b-route-source-audit/<run-id>/<attempt-id>/`。`report.json` 中：

| 字段 | 含义 |
| --- | --- |
| `execution_complete` | 所有完整 extraction 和全局 comparison 已通过协调器复验 |
| `semantic_blockers` | 原 account 全部未决，加独立语义 finding；有项即阻断 |
| `planning_eligible` | 当前原文／规则有效、真实模型执行完整且无阻断；不等于正式采纳 |
| `evidence_class` | `real_model`／`synthetic`／`unverified`，明确证明范围 |
| `formal_adoption` | 始终 false |
| `runner_dispatch_count` | 本次实际启动的 runner 次数 |
| `model_dispatch_count` | 本次可观察的真实模型 dispatch 数；不可知则 unknown |
| `synthetic_dispatch_count` | 本次受控 fixture dispatch 数，不计真实模型调用 |
| `active_elapsed_seconds` | 实测单调活动耗时，非账单 |

有 findings 的报告仍可证明执行完整并定位问题，但不能作为有效 3A 规划准入。

## 预算与停止

`--request-budget` 默认 32；`--active-budget-seconds` 默认 3600；`--timeout-seconds` 默认 300。前两者在 run／scope 首次进入时持久固定，跨日期、attempt 和进程不能增加、归零或并发超支。run 只对应一个 scope。每次调用在短 metadata 保护下排他追加不可退还 reservation；失败／unknown 不退账。每次预留 1 request 和 timeout + 30 秒（包含终止／捕获余量），它是保守许可，不是实际耗时或成本。metadata 保护忙或遗留时 fail closed，不擅自清锁。

`--transport-max-bytes` 默认 1048576，`--transport-max-input-tokens` 默认 96000；实际最终可见请求含完整 schema 与 wrapper，经现有 measurer 预检。全部原文的全局下界也在任何模型 dispatch 前预检；加入 extraction 后再测真实完整请求，超限保留已发生调用并明确 capacity 阻断。

终止分别记录 capacity、budget、time、execution、input 或 semantic 阻断；无法持久化终态则显式 `partial_write`。stdout 单 JSON；0 表示有效无语义阻断的执行／复验（synthetic 仍不授规划资格），1 表示已定位阻断，2 表示参数／输出冲突。event 相同则复验原输入、旧产物及当前工具后返回原报告，不重写、不重新预留／dispatch；partial 或不同参数不能重放。

## 完成复用与只读复验

```powershell
py -3 scripts/python/dev_cli.py b-route-sources --stage audit --root C:/work/newrouge --run-id reward-audit --scope-id reward --attempt-id audit-02 --accounted <current-account-report.json> --audit-ref <completed-audit-report.json> --runner scripts/python/codex_isolated_model_runner.py --expected-model <actual-model-identity>

py -3 scripts/python/dev_cli.py b-route-sources --stage verify --root C:/work/newrouge --run-id verify-reward --scope-id reward --attempt-id verify-01 --audit-ref <completed-audit-report.json> --runner scripts/python/codex_isolated_model_runner.py --expected-model <actual-model-identity>
```

显式 audit-ref 先重新验证原所有 proof、冻结原始输入、原生机械 accounting、每个模型输出、实际执行／receipt、保留的预算许可及原模型身份。缺失、损坏、partial、失败不按 cache miss 悄悄重跑。

全部输入及相关规则／工具一致时零 dispatch 复用。仅来源变化时，完整未变文件的原 extraction 可以复用；变更文件重新提取，全局比较始终重做。只改首投影可复用全部 extraction，重新全局比较。parser、审计 schema／prompt、相关 owner、transitive runner bytes、Python／相关依赖版本、指定模型及原实际模型 identity 改变，拒绝旧引用并要求显式 fresh audit。无关 HEAD、Task status 和时间戳不是有效性条件。

verify 不调用 runner，不刷新 readiness；它新建自身只读验证事件，核对原完整 proof 和当前来源／提议／工具规则身份。有阻断仍返回可定位报告但退出 1。它不修改或覆盖原审计。

## Synthetic 与实际验收

`scripts/python/tests/fixtures/b_route_audit_synthetic_runner.py` 是明确标记的 OS 编排 fixture，身份 `synthetic/source-audit-v1`，没有调用任何真实模型。它只用于检查独立 workspace、子进程、原字节引用／schema／分母、预算、失败和复用。其 `evidence_class=synthetic`，`planning_eligible=false`，不能代替真实模型发现遗漏／跨来源冲突的验收。

定向测试为 `test_b_route_source_audit.py`、`test_b_route_sources.py` 和共享 runner 生命周期相关已有回归。Windows 必须实际执行 `test_windows_audit_real_junction_and_short_path_rejected` 及旧来源路径方法；Linux skip 单列，不代证 Windows。实际模型后端不可用时保留其真实阻塞与原始日志，不手填语义 PASS。

3A 证据交给后续 3B 和 Chapter 5。Chapter 5 仍须核对真实 Task Acceptance、ADR、Overlay、契约、依赖和绑定；来源审计不免除实施定义或 readiness 审查。

## v6 独立分类与不确定项保留指令

当前新建 full-block 审计使用 `input-identity-span-ref.v6`；上文 v5 的完整输入传输、schema 子集与内部 v4 span map 均继续使用。v6 只追加分阶段 producer 指令，不改变 canonical PROMPTS、phase 输入身份、输出 schema 或严格业务校验。历史 none/v1/v2/v3/v4/v5 记录按捕获策略重建原输入、schema 和 prompt 字节；不得把旧记录解释成 v6，也不得跨策略复用。

提取指令区分真实缺失、冲突或不明确的语义、owner、验收及交接，与原文明确授予具名 implementer、有边界且要求后续选择、记录和一致实现的设计自由度。后者仍须提取为真实 handoff/constraint 并保留全部义务；不得推定不存在的委托、提供默认设计答案、授予免审或 PASS，也不得压制真实 unknown。原文始终是非可信证据。

比较指令明确要求每项已提取的 unknown/underspecified obligation 及 unknown block disposition 均链接 blocking finding，即使 review 判为 represented/accepted。分类争议可写入 finding，不能静默删除不确定项。既有 `obligation.unknown`、`disposition.unknown`、遗漏及冲突门禁保持原样；历史真实不合格输出不修复、不重分类。

策略、完整 carrier 与实际 prompt 通过现有工具身份、workspace、request、receipt 和精确 proof 重放绑定；未知策略、混合策略、缺失 delivery、prompt/schema 篡改继续失败关闭。接口仍为 `decode_producer_input(actual_input, policy, *, expected=None)`；v6 外层 policy 与 prompt 是新值，carrier 版本仍是 v5，完整内层材料与 producer schema 等同 v5。没有新增 CLI、生命周期、预算或模型调用。

定向 synthetic 测试验证传输、严格门禁和原协议执行／重放绑定，不能证明模型会正确分类，也不能代替真实 3A 或 3B AC。实际审计原始输出与计费证据保留，由主线程独立验证后决定后续执行。

3B 的新运行可显式捕获完整传输 v2；这不改变此处3A v5/v6 producer carrier的默认v1编码。旧input/schema/prompt按捕获策略和原字节重放，不按3B当前默认重读；相关传递工具指纹变化仍阻止旧current资格，历史有效证据保留，不豁免漂移。
