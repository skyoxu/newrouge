---
title: 'Story 2.9：已提交完成规划复用与 epoch/reopen 撤销'
type: 'feature'
created: '2026-11-10'
status: 'in-review'
baseline_commit: '3896a650dcf6ceaa0cad2c5ee3bc9bc0020e0914'
original_candidate_baseline_commit: 'dacd713984f91deed4ad80826d22459b819ffc06'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/docs/adr/ADR-0039-mvg-completed-capability-recovery.md'
---

<frozen-after-approval reason="原 Story2.9 五项 AC；用户授权在 Epic2 原范围内自主定稿，不增设要求">

## Intent

**Problem:** 当前 B3B 明确跳过完成项 register/adopt；其 scope 是完整规划闭包，不能直接当 legacy scope.capability，也不能把历史候选冒充已完成单项。

**Approach:** 在原 ADR0039 registry/checkpoint/adoption 与 B owner 间补窄适配；完整单项输入作为匹配键，原 proof、当前相关依赖及 delta 分别复验，保留 epoch、reopen、预算和原始审计。

## Boundaries & Constraints

**Always:** 原 Story2.9 范围及 AC1–5 全部保留。正式前置为 2.3、2.5、2.7、2.8；离线规格/实现不冒充前置通过。只从真实 run.json 已提交项登记；协调器保持唯一 checkpoint 提交权。复用原锁、持久 epoch、撤销后继、独立 adoption receipt 与诊断。真实费用、失败、unknown、稳定槽位和 run/lineage 预算保留；新进程不重置。

**Never:** 新建 registry/生命周期/权限载体，复用新 MVG 的未完成候选，删改历史 proof 或伪造新 admission/runtime 证明；用 scope ID、关系摘要、HEAD/catalog 元数据作完整对象键。无唯一完整原行的历史项保持 miss/fresh，不补造字段或新增全局阻塞。Capability 显式 resume-evidence 与 2.8 文件 journal 保持原合同。不得改冻结中的 R56/R57 现场、默认 B 或 main。

## I/O & Edge-Case Matrix

| 情形 | 输入/状态 | 结果 | 诊断 |
| --- | --- | --- | --- |
| 规范化一致 | 原完整行仅键序/排版改变 | 原键可命中，仍验旧 proof/当前依赖 | 保留原字节身份 |
| 无法绑定单项 | 多目标、无完整原行或多个匹配行 | 不登记/不命中，走原 fresh | 原因可定位，不阻断其他目标 |
| 上游已完成、下游失败 | 原 committed item 仍有效 | 只补缺失成果 | 原槽位、调用和失败不归零 |

## 原始验收标准

Refs: FR-5；FR-13（规划成果复用部分）；FR-16；NFR-E-3；NFR-E-4；NFR-E-5；AR-9；AR-10；AR-15；AR-24；AR-27；AC-BR-06；AC-BR-09；AC-BR-20。

**AC-1**

**Given** 历史单Capability完成项由原run.json提交，单项完整规范化内容与当前目标匹配，
**When** 尝试新执行adoption，
**Then** 以完整单项对象规范化内容hash匹配，验证原冻结proof，再检当前相关依赖和累计delta，写独立adoption receipt，
**And** Git／catalog元信息不是匹配键，不用相似度；内容命中不跳proof或当前兼容性，不伪造本run新的语义admission。

**AC-2**

**Given** 仅有prepared bundle、候选／修复／检查／评选中间态或不完整提交，
**When** 开始新的MVG执行，
**Then** 不作为可跨新执行复用完成项；从有效冻结输入按既有流程重新产生缺失成果，
**And** 已付调用、失败／预算历史保留，稳定槽位与run预算不因新进程／lineage重置；下游失败不使未变有效上游自动重跑。

**AC-3**

**Given** 原proof损坏、依赖／delta不兼容或只发生无关提交，
**When** 核对恢复资格，
**Then** 损坏／相关变化拒绝并定位，真正无关HEAD、其他Task status或catalog条目变化不单独使内容匹配失败，
**And** 历史proof的原版本／raw身份不重写；运行证据有效性仍须后续相应完整身份检查，不能用规划adoption证明游戏运行。

**AC-4**

**Given** 执行本地clear／epoch推进或显式reopen，
**When** 重新读取恢复、显示、提交和发布资格，
**Then** 沿原操作锁核对持久epoch，reopen撤销受影响项及后继，不恢复已撤销资格，
**And** 保原审计，local clear不自动删除Git中的正式采纳／累计基线；source-backed语义变化按治理更新相关采纳和绑定。

**AC-5**

**Given** 操作者指定Capability --resume-evidence或恢复应用journal，
**When** 选择恢复入口，
**Then** 分别按其完整准备输入／历史batch／receipt合同或2.8文件应用合同处理，诊断明确适用恢复类型，
**And** 不把这些许可泛化为新MVG执行未完成候选复用；记录实际复用来源／理由、调用数、耗时及未知值。

</frozen-after-approval>

## Code Map

- `scripts/python/_b_route_planning_input.py:63–115,121–256`：复用原 scope 选择、完整 context/source JSON/原字节、governed_closure 与冻结输入；不新增输入 schema。
- `scripts/python/_b_route_planning_runtime.py:146–197,594–597,1411–1494,2285–2295`：增加本地单项/依赖/delta 适配与真实 adoption proof/handoff 分支；保留 fresh B 验证，不伪造 model_draft/至少一次调用。
- `scripts/python/_mvg_capability_recovery.py:16–19,107–336`：复用完整对象键、committed/source/replay/adoption/epoch/revoke，仅分派 B owner；历史 proof 与当前兼容性分离。
- `scripts/python/_mvg_capability_selection.py:178–236,282–385,673–715,1072`：复用原前缀、候选 proof、唯一 selected/checkpoint 提交；替换 B 排除及裸 legacy merge。
- `scripts/python/_mvg_capability_checkpoint.py:128–149,208–273`、`_mvg_global_audit.py`、`plan_mvg.py`：沿用原事务、祖先、epoch/消费者，只有真实接线缺口才局部改动。
- `scripts/python/_b_route_candidate.py:96–275`、`_b_route_record_owners.py`、原 graph owner：复用相关 Requirement/源块、类型引用、Flow/非 Flow/共享依赖和 accepted delta 核验。
- `scripts/python/tests/test_mvg_capability_recovery.py`、`mvg_recovery_retained_checks.py`、`test_mvg_recovery_review_integration.py`：复用适用历史机制证据；B 组合缺口放 `test_b_route_completed_reuse.py`。

## Tasks & Acceptance

**Execution:**
- [ ] `scripts/python/_b_route_planning_runtime.py`；必要时其无写权限 helper `scripts/python/_b_route_completed_reuse.py`：从单 target 冻结合同和完整原文行/locator 推导键与相关依赖，接原 B delta/当前重放。
- [ ] `scripts/python/_mvg_capability_recovery.py`：在原 committed 登记、历史来源复验、当前 replay/adoption 入口局部分派 B；保原 receipt/不可变 snapshot/事务与撤销。
- [ ] `scripts/python/_mvg_capability_selection.py` 与 runtime：完成真实 adoption selected/proof/execution/handoff 组合，保原 commit_checkpoint/assert_epoch 及 fresh 路径。
- [ ] `scripts/python/_mvg_capability_recovery.py`、`scripts/python/_mvg_global_audit.py`、`scripts/python/plan_mvg.py`：检查 adoption 是否经过原 active-chain；仅修实际遗漏，不新建状态机或全局门禁。
- [ ] `scripts/python/tests/test_b_route_completed_reuse.py` 及实际受影响旧测试：单项正向、损坏/相关漂移、真无关元信息、未提交排除、epoch/reopen/后继、下游失败及三类恢复入口。新增测试模块才注册一次 `scripts/python/run_gate_bundle.py` selector。
- [ ] `docs/workflows/mvg-integration-acceptance.md`、本 spec、`sprint-status.yaml`：同步真实已交付边界、复用原因/原证据/实际成本/unknown；原生 Step4/5 后才宣告完成。

**Acceptance Criteria:** 原始 AC1–5 在冻结块中逐字保留；上列任务与矩阵不替代或增加原系统验收。

## Implementation Notes

- followup03：只在新 `night-handoff/story29-r60-implementation-followup-03` 提供 02 之上的最小覆盖文件；支持原合同允许的完整根 JSON 对象（空 JSON Pointer）及明确声明的 shared_capability 完整 context，不因 kind/3A closure 外位置强制 miss。唯一 target、原完整行/raw/proof 检查保留，不递归匹配嵌套引用、不增加 schema 或正文启发式。源码、针对测试及文档仅已编写，未执行、未安装；02/r60 保持冻结，状态与真实前置不变。

- followup02：Root/独立只读审核确认 candidate01 的 P1 历史规则放宽与 P2 合法 constraint 不能 reopen；candidate01 冻结，新候选改在 `night-handoff/story29-r60-implementation-followup-02`。删除裸历史 bool ContextVar，原 `check_originals` 仅显式选择业务输入当前性；同源 runtime/planning rules 与 epoch 始终核对，旧 source epoch 只走既有真实 transition/original-validator，未支持项局部 miss/fresh。source-conflict 复用原合同明确声明且实际完整冻结的 constraint/context 原文及 raw/citation，不新增来源 owner。新增针对方法仅已编写、未执行，正式前置与完成状态不变。

- 2026-11-10：只读 `r60`，向 `night-handoff/story29-r60-implementation-candidate-01` 准备完整候选文件；没有写入基线、运行测试/模型/Git、执行验收或标记完成。正式前置 2.3/2.5/2.7/2.8 及原五项 AC 保留，2.10 依赖 2.1–2.9。
- 候选 helper 无持久写入权；从原单 target 合同、既有完整根 JSON 对象/顶层数组/`capabilities` 容器及明确声明的 shared_capability 完整 context 与冻结原字节推导完整对象键。无法唯一绑定时保留 fresh 诊断。复用原 registry、不可变 prefix snapshot、checkpoint、receipt、epoch/revoke 与预算账本，没有新建输入/candidate schema 或生命周期。
- B 当前重放采用既有 external envelope 与原结构/引用/Requirement/来源/关系/graph owner；历史候选及 proof 保留原字节和原政策字段。selected/proof/execution/handoff 识别 adoption，零新增调用仅属于已复验的 adoption，fresh 仍要求原真实 model-draft 及付费绑定。
- 原全局 audit 的 B 缺口限定为原 prepared 文件、Flow 容器、来源 locator、run descriptor 与原 reopen context/review 合同的分派；沿用同一 reopen transaction/revoke，不增加全局指纹门禁、Task 实施或 Epic4 扩围。
- 新测试模块与唯一 gate selector 仅已编写；实施者没有执行。Root 须先静态审阅完整差异，再按 Verification 的原本地小夹具、最小方法集与真实前置顺序取证；合成协议不得冒充模型/native 验收。

## Spec Change Log

## Review Triage Log

- Root followup02 / P1：candidate01 的 `historical_input` 裸布尔上下文能绕开 recorded rules 与 epoch；本候选已删除该上下文并接回同源严格规则比较及原旧 source owner。实现与必要方法待 Root 独立验证，不记通过。
- Root followup02 / P2：candidate01 `_mvg_global_audit._source` 将合法 required constraint 排除在 3A source closure 外；本候选按原冻结合同声明及完整文档/evidence/raw/citation 接回，新增独立 constraint audit→reopen 行为方法。待验证，不记通过。

## Design Notes

本轮实施边界：以 `C:/Users/Administrator/Documents/Codex/2026-11-05/task/r60` 为只读基线，仅向 `C:/Users/Administrator/Documents/Codex/2026-11-05/task/night-handoff/story29-r60-implementation-candidate-01` 生成完整候选源码/patch；Root 独占仓库写入、Git、项目验证及真实调用，实施者不启动测试、子进程或预算动作。

恢复键是原完整 Capability **输入对象**，不是新分配的正式定义。仅在原 frozen contract 明确唯一 Capability target、既有受支持 JSON 文档容器能唯一定位完整原行和真实字节/locator，且原 selected checkpoint/proof 覆盖该闭包时适配。保未知字段、数组、值及类型；不把任意含 ID 的嵌套引用当完整定义。原 proof 仍为 whole-closure proof，键、证明覆盖和当前兼容性各有职责；不改签成 single-item proof。无唯一绑定的旧数据自然 miss/fresh。

当前依赖由 governed_closure、原 candidate/typed-ref/源块/关系/graph owner 给出，并用原 B merge/preservation 重放完整 delta；不拿全局 input_identity/文件清单/HEAD 作本地键，也不因“元信息”名义删相关语义。旧 envelope 按原版本复验，当前 envelope 按当前合同复验，正式前置与最终全局审计保留。

本次调查结论无需新增输入/candidate 字段、持久语义或额外防御。若实现证明必须扩展，先报告具体必要性，由干净 Astra max 独立评判；只暂停新增部分，其他已授权工作继续。

## Verification

- 先用单个真实本地 coordinator/checkpoint/receipt 小夹具走准备、提交、恢复读取、终态；明确夹具不等于真实 native/模型资格。
- `python -m unittest test_b_route_completed_reuse`：执行新增 B 组合的最小方法集，核实原对象键、原 proof 与独立 receipt；用受控 SourceOnly/独立 TEMP 宿主提供既有依赖。
- `python -m unittest test_mvg_capability_recovery` 及受影响 wiring 方法：按变更实际挑选旧方法，复用未变源/夹具/环境的已有效证据，不默认全量。
- 失败方法先取独立通过，再决定必要组合。偶发外部问题有界恢复并保累计账本，不把 unknown 或缺证据算通过。
- 原 Step4 独立审核/修复；满足 2.3/2.5/2.7/2.8 真实前置后，从正式 B 入口验证完成项复用、零新增模型调用的实际指标、reopen/epoch 及 Capability resume-evidence/文件 journal 区分，再 Step5 本地可回滚收口；不 merge main。


## 当前独立集成记录（2026-11-11）

R63 以最新 3896a650 建立独立分支，精确移入 R60 当前候选的十二文件边界及三项历史 generation schema helper 修复；只合并 gate 的 completed-reuse 注册与 2.9 sprint 行，保留最新 2.7/2.8 公共层。没有复制继承 workflow.md、本机 authority DATA、旧 source-map 或运行回执。

历史 11 个 scoped 方法与两个 schema 方法仅按原时代覆盖复用。原 Root-01 功能失败保留；Root-02 仍因终态缺失保持 Pending Evidence，不改成失败或通过，也不恢复其原 fixture。新集成尚未取得行为验证或正式验收。后续如需同一既有 coordinator 的新验证，必须明确为新源码/新隔离 fixture 的有界定向尝试，不重放旧未知操作；2.8 正式前置未完成前不做 2.9 正式收口。

### 2026-11-11 原生三层审核逐项裁决

| ID／来源 | 原发现 | 裁决／路线 | Root 核对依据与边界 |
| --- | --- | --- | --- |
| B1 blind | 历史 wire 复用隐式检查当前原件 | high / patch | `verified_prefix(check_originals=False)`仍经 generation.verify_dispatch_receipts:757→runtime.verify_reserved_call:2101/2125，重读当前state且selector未传原模式；当前真实默认wire可达。需沿既有链传相应state/模式，保留原证据和规则验证。 |
| B2 blind | reopen写pending后旧wire selected索引失败 | high / patch | audit:621先写pending，:629重验；runtime:2101重新加载磁盘state，:1863索引selected。原归档已保留prior_state，缺正确代际接线；不能跳过receipt或复活旧资格。 |
| B3 blind | 闭包外新Requirement分母使完成项miss | maybe-false / defer | 拒绝确实发生：candidate:146完整当前分母、reuse:151保留完整结果边界。尚未证明这是原AC3承诺的无关HEAD/Task status/catalog元数据，而不是实际3A分母变化造成的不兼容。要把它变成自动重写out-of-scope结果的新义务，须先证明当前完整治理闭包与原单项语义及全部验证分母均不变；本轮不新增该重基协议或阻塞。保留当前明确miss/fresh，不宣称支持此扩展。 |
| B4 blind | .json扩展名盖过显式text格式 | medium / patch | helper:64–68对所有.json强制解析；planning_input:84–86合法接受text格式context，故合法文本context可能破坏唯一绑定。应遵守显式format，只对未声明的源文件按原扩展名推断。 |
| B5 blind | 同文件闭包内依赖Capability被丢弃 | high / patch | helper:122删除整个capabilities数组；planning_input:177–193可产生含传递Capability的真实治理闭包，已绑定同文件依赖行的业务字段可能被忽略。保留闭包内完整行，无法证明无关的材料不能自动省略；已证明无关的其他Capability仍不因排版/元数据失效。 |
| B6 blind | 全局冲突域遗漏已选Plan中的Flow | high / patch | audit:40–41只列本候选definitions；candidate.check_owners:178–192已验证当前和显式selected依赖的唯一有效owner。原有效Flow冲突可在audit:177被误拒，需复用已有有效owner域，不能扫描未选历史catalog。 |
| B7 blind | Capability没有新增public audit/reopen命令 | false / reject | standalone入口缺失属实，但原owning doc:67–71明确plan-mvg；原MVG projection:549–551纳入adoption来源transaction，revoke:236–260按ancestry跨planner撤销，B消费重验。干净Astra max判定不应增加该入口作为2.9前置；不声称已验证跨planner真实执行。详见独立assessment。 |
| B8 blind | 合法blocked重开评审当成执行故障 | medium / patch | runtime.review_issues:429–433把所有reopen_review_errors一律抛异常，audit:314–316同时包含合法blocked语义结论；schema允许blocked。应将合法未解决结论交既有有界语义修复，错误绑定/缺失分母继续拒绝，不把blocked当准入。 |
| B9 blind | 传递Capability冲突不能映射受影响单元 | high / patch | audit:165–166仅scope直接ID，:65仅直接交集；planning_input闭包entities含已证明传递依赖。需从原闭包映射受影响scope，不引入新图/隐式依赖。 |
| B10 blind | B audit回执漏planned义务 | medium / patch | audit:384–387只投影legacy字段，新B分支已可达而B implementation_objects/later_checks位于content。原完整proposal仍存在，不能把空投影当无后续义务；补现有回执投影，不增加运行资格或实际Task实施。 |
| E1 edge | 默认wire的reopen提交后无法收口 | high / patch | 独立同根印证B2；原fixture.complete_source默认complete_wire=False。单列裁决后纳入同根wire历史验证修复。 |
| G1 verification-gap | 未执行带reopen_context的B replacement链 | high / patch | filed gap按原流程预验证；四单例只到pending/clear。补原本地synthetic transport下真实prepare_dispatch/bound_materials的单scope续接，不新增provider调用或全量。 |
| G2 verification other | indexed proof fixture缺lineage.generation | medium / patch | Root已读test_indexed_review:225–252，:232只有context/identity；runtime:1502无条件读generation。补原fixture必需字段，保留policy篡改负向断言，定向复验该方法。 |

### 审核修复检查点

基线7b806df7。13个发现逐项裁决后，仅实施已证明的最小原合同修复；
14项DATA/实际owner投影与负向检查OS0通过，indexed policy夹具单独复验通过。
新current-wire完整reopen、replacement请求和跨代历史复用测试已写入，尚待执行。
四个原单例按7b原范围保留；不把它们扩展为当前完整修复或官方模型资格。
2.8正式前置仍pending，Story2.9未正式收口。


## 2026-11-11：历史 reservation 模式透传后续修复

R63 8505729f 的原 gen2 续接已自然 OS0，保留旧10+新增10本地协议调用；证据 Task/logs/ci/2026-11-11/story29-r63-retained-gen2-01。原超时记录不改为通过。其尾段 related-drift 场景拒绝复用但报 semantic_error，尚未走到 unrelated-context adoption。只读源码发现 selector 的 check_originals=False 未经 verify_bound_reservation 传给 verify_reserved_call，candidate proof reservation 也存在相同模式接缝。R65从8505729f隔离修复该透传，默认 True、原回执、身份、unknown拒绝与当前准入门保持。未新增恢复系统、缓存或指纹门。原异常trace观察300秒超时，未取得第一异常栈；不把静态因果结论称为已观察首异常。

四项新模式/默认严格/unknown与原generation-state定向检查已PASS/OS0：Task/logs/ci/2026-11-11/story29-r65-historical-mode-data-01。源码身份已变化，原20-call旧fixture不冒充新源码验证；下一步仅用新源码的新定向fixture完成source/related-drift/unrelated-adopt，不重跑全套或真实模型。Story正式验收仍待前置及必要原生审核收口。


新定向样本第一轮保留 known OS2（847.83秒）：10个新源码本地调用已完成/selected，随后新fixture的长target ID在run_location路径容量门拒绝，尚未创建目标或派发。仅缩短未启动的两个测试目标ID为cw-rel/cw-unrel；生产模块与其rules身份不变，复用原保存10-call source与已准备related输入继续尾段，不重做已完成调用。该错误不视为模式修复已通过。


### 2026-11-11：原完成 source 的定向尾段通过

修复提交 `ae0e2917` 的生产模块保持不变；`7d0bbfe9` 只缩短未创建的目标 ID 并记录前轮失败。后续使用同一已完成 source 和原 related prepared 输入执行尾段，不重做 source 或 related prepare。真实本地入口证明：相关依赖变化得到 `recovery_current_dependencies_incompatible`、走 generate_fresh 且没有派发；恢复原相关依赖后，仅修改无关 Capability/Task 信息，得到 adoption receipt 与原生复核链，目标调用数为零。原 10 次已完成本地调用保持不变。

证据为 Task `logs/ci/2026-11-11/story29-r65-retained-tail-01/result.json` 与 `unit.json`：实际持有的 worker OS exit 0、Job 已静止、365.563 秒、passed=true；新增本地协议调用和项目模型调用均为零。该结果单独补齐前轮失败后的尾段，原 847.83 秒失败记录仍保留。既有四项模式/默认严格/unknown/generation-state 定向通过按实际覆盖范围复用，未重新运行全套。

这是当前源码的本地真实入口证据，不是外部模型资格或 Story 正式验收。Story 2.9 的正式 Step 4/5 仍须满足 2.3、2.5、2.7、2.8 前置；目前 2.8 未完成。原 R60 Root-02 只有 started 的记录仍为 Pending Evidence，不推断终态、不重放。

### 2026-11-12 Cloud continuation23: original eligibility and real acceptance boundary

The8 relevant native/reuse/checkpoint/audit/test files remain byte-identical to f94847e2; applicable earlier narrow results are reused without rerunning the coordinator or promoting synthetic protocol evidence. The actual original m4 checkpoint is retained and its1,140,425-byte prepared input matches its frozen identity. The scope is all/ids=[], registry epoch0/entries0; the real current binding owner correctly returns b_route_recovery_requires_single_capability_target. No item was registered or relabeled. Original public native status returned execution_transition_absolute_root_required; the raw output and subsequent reporter parse failure are retained, child exit not saved/unknown, command not repeated.

A true positive cross-run single-item adoption/epoch/reopen acceptance still needs an actual committed single-Capability input/proof and current dependency replay. The all-scope publication cannot supply that by renaming it. Current production native initialization requires Windows, while this selected Cloud executor is Linux without a configured Windows target. This is an existing runtime/original AC boundary, not an added policy or missing subscription allowance. No new product defect, model call, budget reset or old unknown replay occurred. Story remains in-progress. Evidence and exact existing command forms: logs/ci/2026-11-12/cloud-epic2-recovery-23/REPORT.md and native-eligibility-observation.json.

### 2026-11-12 continuation24: new complete input and actual current accounting

The genuine existing controlled source is available. A new explicit one-Capability context covers its entire unchanged source, with no historical m4 relabeling or formal allocation. Actual public3A prepare and account02 succeed with1 file/8 blocks/7 proposals and unchanged original business proposals/normalized block identities. Account01's caller string prepared_ref error remains; only the exact typed path/raw_digest reference was corrected in a new deterministic attempt. No registry/native run/model call is created. The pending-audit contract is not a formal prepared input or approval.

Actual old/current audit comparison shows Python/packages/transitive-tool identity drift and an incomplete raw old audit prefix in the recovery dataset. The existing fresh audit path is available; one complete-source extraction and global comparison require2 logical reviews on the intended current subscribed native host. Neither was reserved/dispatched. Exact preflight requests fit45113/67821 UTF8 upper-bound tokens at the existing96000/1MiB limits; the comparison still needs actual extraction remeasurement. Linux-bound audit cannot be silently requalified as Windows current proof. The Windows4-test fixture job succeeded independently with zero models; it intentionally carries no model credentials. No paid API/fiscal issuer/new governance or broad suite is needed. Real current audit/native generation and positive adoption/epoch/reopen remain pending, Story status unchanged. Evidence and concrete commands: logs/ci/2026-11-12/cloud-epic2-recovery-24/REPORT.md.

## Paused transfer checkpoint25 (2026-11-12)

The user stopped all new business/model/test execution to hand over to another AI assistant. Source/evidence preservation commit a4cced184e50c6e1d61a74ea44bb74c18f3a82af is based on0c4d16c1. Read docs/handoff/2026-11-12/cloud-continuation/HANDOFF-OTHER-AI-2026-11-12.md and logs/ci/2026-11-12/cloud-epic2-recovery-25/REPORT.md; they supersede earlier prospective execution instructions, not the original frozen ACs.

The genuine source audit completed both official phases before the Linux adapter, public0/2 occupied. Its full protocol and121 original tool identities are preserved. Formal3B prepare actually exited1 at the278315-byte common-core UTF8 upper-bound probe+2000>96000 before native/model dispatch. The necessary narrow Linux initial-publication adapter was independently assessed and10 focused controls passed before the stop. It changes transitive tool identity, so the old eligible audit is historical; no changed-source audit, native call, committed single-Capability item or new registry entry exists. User chose to keep current network settings: no official encoding table fetched, no accurate token count or offline transport fix claimed.

Previous real compensation/read/clone and four Windows synthetic-upstream controls remain valid within their original scope, not whole-Epic acceptance. Source-audit2 and compensation original2+added1 occupancy/failures/unknowns are unchanged. No more execution is authorized until the user resumes; preserve original Story2.8 AC1–5,2.9 AC1–5 and2.10 AC1–6/prerequisites. No Fast/API/main/Aliyun/S2/full-suite or unknown replay. The four unrelated initial EOL-status paths remain excluded.
