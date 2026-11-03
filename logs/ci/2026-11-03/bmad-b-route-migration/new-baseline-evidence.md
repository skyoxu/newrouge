# B 路线文档链切换后的基线证据

- 核对日期：2026-11-03。
- 当前工作目录：`/workspace/newrouge`。
- 当前分支：`fix/capability-synthesis-input-integrity`。
- 本轮源码身份：`cd925bdcae4b61992320773497f7edb729aac244`。
- 原需求历史基线：`a8a363aa5f4ad09d5032731b0e7dfc5a17b8c89b`。
- 最初本地树：`8f93557d7f5f07b7931e3f4966a2dce04e458344`，仅保留为历史对账身份，不再作为当前代码证据。
- 任务边界：只读基线核对与此证据文件写入；未改源码、Task 三联、ADR、工作流规则，未执行 Chapter 工作流、模型规划、Godot 或业务运行验收。

切换后初次核对 `git status --short` 为空，`git rev-parse HEAD` 与上述当前身份相同，历史 `a8a363...` 对象可读取。后续文档搬迁造成的本地文件变化不属于此处源码行为判据。当前与历史基线的差异统计为154个文件、增加27762行、删除700行；本报告按本次文档合同关联的模块核对，不构成全部差异的逐行代码审核。

## 1 继承与变化的边界

已重新读取当前 `AGENTS.md`。Windows-only、Godot4.5.1、C#、BCL-only Core Contracts、Taskmaster 唯一任务状态、成熟Task身份、单Task Chapter6、累计manifest、防弱化、P1必修和 `logs/**` 证据约束保持。用户已明确本次是路线改变，**不以提速、成本下降或A/B速度优势作成功条件**；以下现存预算和复用行为属于必须保护的治理事实，不转化为新绩效承诺。

当前仍不是 B 的无Task正式路径。新增的完整性、候选生命周期和恢复能力改变了应当复用的技术基线，没有替代本次需要解除的 Task/readiness 循环依赖。

## 2 Capability 输入与模型身份的新基线

| 当前事实 | 当前源码或 owning 文档 | 对本次文档的影响 |
| --- | --- | --- |
| 逐批验证完整 Source Block／Requirement 对象、batch顺序、hash、全部coverage和prepared文件；不以ID齐全代替正文完整 | `_capability_input_integrity.py:114–182`，尤其146–174 | “已有完整性基础”应包括对象级守恒，不能退回字段白名单或正文裁剪 |
| 任务分块携带完整相关master/readiness／Requirement／Source Block对象；关联由声明ID决定，不猜缺失引用 | `_capability_input_integrity.py:194–255,306–447`；Capability Skill Input integrity节 | 无Task前置模式应显式去除Task前置依赖，不能把现有相关Task投影误当完整来源审计范围 |
| 同一来源账本保留，只有严格证明退休专属且无activeRequirement引用的块才可从模型分析派发排除，排除记录可审计 | `_capability_input_integrity.py:71–111,175–180`；Capability Skill | “完整输入”不等于所有阶段重复发送全部已退役正文；完整审计账本、明确排除及最终守恒仍必须成立 |
| 默认Capability runner 已改为认证Codex CLI，无工具，并绑定调用线程rollout中的实际model；缺失或变化fail closed | `codex_isolated_model_runner.py:104–169,242–315,646–664`；`plan_capabilities.py:1165–1185,1707–1713` | 不再把OpenAI API runner描述为默认；静态alias/auto不是实际同模型证明，无自动Copilot/OpenAI fallback |
| analysis与synthesis独立预算；默认analysis2700秒、synthesis1200秒，共享13500秒active-time上限；各stage及修正共享synthesis allowance | 当前 `workflow.md:771–780`；Capability Skill Recovery and cost节 | 保护当前既有预算，不为B增加每节点审批或隐式预算，也不承诺达到某速度 |
| analysis输出实际大小被完整测量，再决定单次或有界多阶段synthesis；每后续stage携完整previous draft、机器检查；最后stage才发布候选 | `codex_isolated_model_runner.py:575–618,642–643`；`openai_isolated_model_runner.py` 的synthesis plan/execute函数；当前Capability Skill | 不再沿用“只能一次最终全包”旧理解；估算不作输出硬上限，真正容量不足仍阻断且不截断 |
| deterministic invalid synthesis每stage最多3次定向修正，完整stage输入/拒绝draft/校验历史保留；transport/容量/预算故障不进入语义修补 | Capability Skill Input integrity节；`codex_isolated_model_runner.py:604–618`调用共享synthesis执行器 | 保持执行错误与语义问题区分，不靠重复三候选解决确定性容量错误 |
| `--resume-evidence` 是操作者显式选择，按原attempt workspace验证完整输入及已接受batch request/response后续synthesis；默认关闭 | `codex_isolated_model_runner.py:461–479,776–789`；Capability Skill | 这是Capability证据恢复，**不能与下述MVG完成checkpoint-only跨执行复用规则混为一谈** |
| Task evidence默认raw，`lossless-v1`仍是prepare时冻结的可选试验 | `docs/workflows/capability-task-evidence.md:1–4,87–121` | 不把可选编码试验写成已全局默认或已验证的理解质量提升 |

以上为源码/文档行为核对；没有实跑Codex、synthesis或输入压缩理解探针。

## 3 MVG 已部署逐Capability三候选与独立worker

当前 `docs/adr/ADR-0039-mvg-completed-capability-recovery.md:3–13` 为 **Accepted**，已经进入架构主参考；`ADR_INDEX_GODOT.md` 现也列出两份0038与0039。原“候选准入0038未进索引”的陈述只保留为历史，不能继续写成当前缺陷。两份0038仍需按完整文件名引用；0037仍是Proposed。

当前默认 `capability-local-selection.v1` 按冻结Capability顺序处理，每当前项三候选从同一accepted seed产生增量，先机器/累计delta/独立语义准入，再对**该项**三候选比较；胜者成为下一项共同seed。accepted seed是只读背景，不是incumbent D或失败fallback。历史whole-candidate/segmented策略只用于明确旧run恢复，不能作为新默认。

直接证据：

- `_mvg_capability_selection.py:14,34–39,410–445` 为当前策略及协调入口。
- `:736–743` 的selector只比较当前三个已准入增量，accepted-seed只读、不拼接、不额外hard veto。
- `:455–473` 在派发前持久reserve；默认run上限192，稳定candidate槽位上限64，进程/lineage变化不重置。
- `:806–824` 在重新检查source、receipt和accepted prefix后准备/提交checkpoint，不能仅靠worker返回成功推进selected。
- `_mvg_capability_worker.py:101–121,130–200` 为独立OS子进程/工作区和parent mailbox；parent掌握reserve/outcome/cost，worker不拥有selected提交权；Windows退出处理终止进程树。

**更新要求：** 当前文档不能只写“整组3候选各自完整append所有Capability后再比较”。Capability组织生成本身仍有A/B/C（可比较incumbent D）的独立流程，MVG逐项selection则无第四候选；两者分清。

## 4 原子checkpoint、完成项复用与epoch

### 4.1 checkpoint与多产物journal不是同一提交边界

`_mvg_capability_checkpoint.py:128–149` 用schema/run/Capability/order/base/proposal/selection-receipt规范tuple构造事务身份，bundle保存accepted seed、delta、accepted及proof/receipt绑定；文件存在不等于committed。

`:310–352` 的 `commit_checkpoint` 一次替换 `run.json` 同时发布checkpoint指针、selected前缀、accepted hash及current清理；`:321–331` 对已提交同事务校验后返回no-op并保留较新head；`:353–379` 对写后异常检查实际落盘状态，结果不明则记录显式recovery evidence。不要把此**单协调器提交点**与已存在trace/manifest/Task多文件apply journal混为一谈，也不要反向声称现基线完全没有原子可见性基础。

### 4.2 跨执行只复用完成项

Accepted ADR0039:7–10以及 `_mvg_capability_recovery.py`：

- `:16–19` 恢复匹配键是完整单项Capability对象canonical hash；对象键序/排版无关，数组顺序、值及类型有关。Git revision/catalog是provenance，不是匹配键；禁止相似度恢复。
- `:161–215` 只注册disk `run.json`已提交且有checkpoint协议的项；staged payload不算完成，legacy prefix不凭空变为可跨run adoption。
- `:247–285` 原proof先在其原冻结envelope下验证；`:288–306` 再核当前相关依赖、accepted边界和delta replay。
- `:310–341` 成功复用写独立 `newrouge.mvg-capability-adoption.v1` receipt并保留原proof，不假造当前run模型准入；不兼容/损坏/撤销项记录原因后fresh generation。
- 新执行的未完成candidate/inspection/repair/selection中间状态不续跑，旧调用保留审计，创建fresh context。复用已提交完成项不等于复用失败或半完成模型状态。

### 4.3 clear与reopen

`_mvg_capability_recovery.py:39–90,94–99` 为持久epoch与activity lock；clear推进epoch并归档旧registry，不递归删除审计或正式baseline；`:52–77` 当前消费检查epoch和撤销。页面进度只显示committed prefix、new/reused、partial_planning，不赋予runtime完成。

`_mvg_global_audit.py:272–320` 为完整链的确定性audit；`:78–109` 要求显式reviewed且source-backed冲突声明；`:111–120` 将普通Requirement/Contract/Flow重叠识别为ordinary_overlap。`:390–429` reopen-plan/reopen必须绑定exact audit/plan/hash、head与输入，存在apply journal则阻断；reopen撤销affected及所有累计successor的资格，保留历史和已付cost，重新进行隔离三候选选择。普通共享依赖不得触发全量reopen。

**文档精度要求：** “成功且输入不变不重跑”应明确为有效且已提交的阶段/完成项复用；不得覆盖ADR0039新执行不恢复未完成模型中间态的规则。纯实现缺陷复用已采纳Flow仍成立；显式reopen、epoch清理或相关依赖变化本就不属于无关变化复用条件。

## 5 Requirement多Flow参与与唯一验证权威

当前新协议将三件事分开：

| 对象 | 唯一键与含义 | 证据 |
| --- | --- | --- |
| `requirement_route_memberships` | `(requirement_id,flow_id)`，每对有非空observable_role；同一Requirement可以参与多个Flow | `_mvg_requirement_routes.py:135–142,167–234` |
| `requirement_verification` | Requirement ID唯一；处置、owner、authorization及权威证据引用唯一归档 | `_mvg_requirement_accounting.py:189–221,224–280` |
| `requirement_evidence` | `(requirement_id,evidence_id)`唯一；可为不同route提供共享/追加证据 | 同文件`:201–220,323–399` |
| `coverage_table` | unique verification的无损兼容投影，不能另开一套owner/disposition | 当前 `workflow.md`5.4；`plan-mvg` Skill的accounting节 |

新run在prepared index/run冻结 `newrouge.requirement-accounting.v1`；删字段不能退回legacy。旧artifact保持原bytes/hash，只做可证明的只读投影，旧owner-only记录不能推断额外route。

`_mvg_requirement_accounting.py:501–528` 对Requirement与evidence pair计数一次，区分accounted和satisfied：

- `implementation_reference`只证明存在，planned test或模型报告不等于通过。
- `verification_record`消费冻结的explicit passed JSON，绑定Requirement、行为、Flow和test。
- `runtime_acceptance`消费正式MVG run receipt、inventory、snapshot manifest及exact manifest/source identity，不以Capability revision或后续Knowledge commit替代。
- satisfied要求全部权威证据有效且覆盖所有route；deferred仍unsatisfied，source_gap虽accounted仍阻断planning completion。

**与原需求的关系：** “保留单一覆盖归属”可且应解释为单一verification/责任权威，不能解读为禁止多个Flow的显式可观察参与。共享依赖引用仍需保持；本变化无需改变用户的B方向或玩法范围。若文档把 `Flow.requirement_ids` 一律写成唯一覆盖归属，应修为“参与关系与唯一验证归属分离”，避免退回历史exclusive-flow-only模型。

## 6 planning complete现在已有可信合同

`_mvg_planning_completion.py:43–90` 已从完整已验证selected/admission/checkpoint链、当前全局machine audit、Requirement accounting、formal applicability生成hash-bound report：

- audit/proof/source_gap/reopened-conflict不满足时阻断；planned tests/entrypoints仍可作为未实现义务。
- passed checks、hard conflicts、obligations、evidence gaps和Requirement accounted/satisfied分别展示。
- `runtime_acceptance.status=not_verified`、`runtime_verified=false`不因planning complete改变。
- `:38–40` legacy trace没有report则completion unavailable，不从旧apply-summary布尔值升级结论。
- validate、apply/recovery、manifest-bound Knowledge应消费同一report，不产生多个完成真相。

因此本次PRD/SPEC不能把“计划完成和运行完成分离”全部写成尚待新增能力；行为目标仍需保持，新工作重点是使该合同承接Task-free语义前置和后置绑定。

## 7 无Task正式规划的循环依赖仍在

- `plan_capabilities.py:99–129` `_readiness_summary`仍调用Chapter5 task readiness；`prepare:269–317`冻结Task scope，`generate:990–994`明确formal_ready false则拒绝；`apply:2225`仍检查formal_ready。
- `plan_mvg.py:4125–4144` `_task_readiness`仍要求current Chapter5 readiness；`:4185` 在prepare输入构建调用；`generate:4679–4680`仍拒绝未ready scope。
- `AGENTS.md:35–36,84–85`及当前owning Skill入口仍描述post-Chapter5规划。

不能因新checkpoint/无损transport/Requirement accounting已存在就判断B路线已经完成。也不能把allow-unready-draft、空Task、旧run replay或已完成项adoption当作新的无Task正式采纳路径。

## 8 当前PRD和SPEC需要更新的具体陈述

| 当前产物位置或主题 | 应采取的事实更新 | 不改变的上游决定 |
| --- | --- | --- |
| `SPEC.md` Constraints中的“实施前对照a8a与本地8f935…”；PRD addendum开头的共同固定根 | 改为当前工作源码基线cd925bd，历史a8a作为原需求来源事实；保留实施开始时继续检查漂移的义务。产物移动后的sources/companions相对路径由主流程统一校验 | B已选，工作分支不等于main，不声称分支内容已合并main |
| addendum“候选admission／完整性模块”概括、当前消费者清单 | 补入ADR0039、Codex runtime identity、staged synthesis、MVG逐项三候选、input envelope／checkpoint／worker／recovery／global audit／accounting／completion模块 | 完整来源、独立审查、预算止损和机器消费者约束保持 |
| addendum“候选0038未列索引”的历史盘点 | 当前索引已列双0038和0039；只保留历史缺陷及实际Proposed/Accepted区别 | 不擅改编号或升级Proposed0037 |
| SPEC“Requirement单一覆盖归属”；workflow-contract首段 | 明确multiple route memberships与唯一verification/owner，禁止重复记账而非禁止多Flow参与 | 共享定义不复制、Requirement计数一次 |
| CAP-8/CAP-10、verification-contract“成功上游不重付／恢复复用” | 明确MVG仅有效committed completion跨执行adoption，unfinished模型状态留审计；Capability显式resume-evidence另按其完整性合同 | 无关变化不重规划、后编辑不覆盖、不得假恢复 |
| migration-and-pilot中的基线与接入批次 | 先盘点当前已部署模块再补Task-free B接口，不重复实现现有checkpoint/accounting；试点保持已确认Reward切片 | 不新增玩法、不全仓GDScript→C#、不变更试点承诺 |
| planning/currentness/UI能力描述 | 当前已有committed-prefix进度、epoch清理与completion report；写为继承，并说明B接入需要一致消费者 | 页面仍派生、不能证明runtime或推进未授权发布 |
| BR/AC过程成本和复用要求 | 采用当前真实reserve、stage/proof/receipt日志作为事实基础，保护预算但不引入“B更快”验收 | 用户明确路线改变，不设速度或成本下降目标 |

## 9 当前语义碰撞判断与验证限度

未发现要求用户重选B方向、重新裁定游戏玩法、放松权威或升级引擎的冲突。发现两处需要明确用词的相容性风险：一是“单一覆盖归属”不能排斥当前合法多Flow参与；二是“成功上游阶段一律恢复”不能绕过ADR0039完成checkpoint-only规则。可通过上述分层定义解决，不需要新增范围审批。

本轮未对154个变更文件全部逐行审核，也未重跑已有logs中的任何测试；已存在历史test report不作为本轮动态验收。新增B前置schema、来源独立审计适配、必需绑定识别和多产物可见性仍需后续设计及实施验证，不能从已有checkpoint或planning_complete推断本次迁移已交付。
