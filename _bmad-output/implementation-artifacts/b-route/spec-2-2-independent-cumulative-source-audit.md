---
title: 'Story 2.2：完整累计来源的独立遗漏与冲突审计'
type: 'feature'
created: '2026-11-04'
status: 'in-progress'
baseline_commit: '2f7d36bdb6e1e0f9f3201a3df3c38bfb2dab6624'
route: 'dispatch'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/epic-2-context.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Story 2.1 只证明完整来源的机械记账；首轮提议漏掉、误归类的交接仍须从原文独立发现，不能按已有 Requirement／Flow／Task 引用缩小审计。

**Approach:** 在现有来源入口增加薄的独立审计与只读复验阶段，消费有效 prepare／account 证据。隔离、无工具的新模型会话先从完整原文提取义务，再核对首轮提议；机器复验范围、定位、执行及冻结 proof，分别表达审计完成、语义阻断和后续可用性。

## Boundaries & Constraints

**Always:** 对照 `epics.md:798–849` AC1–5 及其 Refs。完整累计 manifest、全部 Ledger 块及空文件是分母；缺 Task／readiness／所选 Flow 不影响审计范围。原 bytes／顺序／块身份与提议验收意图完整保留。finding 必须有来源 path、raw digest、块及精确原文定位、当前输入身份、分类／严重性、返回责任和受影响提议；完全未投影可明确列空提议并标遗漏，不能编造正式 ID。未知、欠定义及未决阻断项保留；延期／范围外须有效来源依据及明确独立审阅，不凭自报 PASS 消除。真实过程证据留 logs，机器完整性不宣称证明任意业务语义正确。

**Never:** 修改 Task 三联／游戏／累计 manifest／正式 source-set／旧 proof；创建第七类正式记录、分配规划 ID、apply／publish／readiness／Knowledge stable、启用默认 B 或退役 A；替代 Chapter5 Task Acceptance／ADR／Overlay／契约／绑定审查。T108 仍缺、正式保护资格及 Epic1 五项权限仍 false。不得把 synthetic runner 结果称真实模型语义验证。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|---|---|---|---|
| 未投影交接 | 零 Task；首投影把原文交接漏掉或误归 context | 独立提取不接触首投影；核对发现并准确引用交接，审计可完成但规划阻断 | 空受影响提议合法；不按引用缩源 |
| 冲突／未知／延期 | 跨来源矛盾、欠定义、无依据 defer／out-of-scope | 保 finding 与 owner；严重阻断不因已记账／模型接受消失 | 错引用、假依据、缺明确审阅均拒绝 |
| 完成项复用 | 完整已持久审计，来源／提议／parser／规则／工具／指定模型身份匹配 | 独立复验原 proof 后零 dispatch 复用；无关 HEAD／Task status 不影响 | proof 缺失、损坏、partial／失败不能复用 |
| 有关变化 | 单来源／提议／工具或规则变化；跨来源关系 | 按真实依赖闭包失效：未变文件独立提取可复用，变更文件提取及全局比较重审 | 未知依赖保守阻断，不拼旧全局结论 |
| 容量／预算／执行 | 完整请求超限、预算不足、子进程超时或非法输出 | 不截断；区分 capacity、budget/time、execution、semantic；记录实测耗时和可观测 dispatch | 调用前预检；持久预留失败／unknown 不退账，换 attempt 不重置预算 |
| 安全／漂移／重复 | 原文／glob 漂移、proof 别名／junction、事件重复 | 只写独占当前 logs；源及所有旧文件不变；同事件复验后返回原报告 | 参数／输出冲突 2，定位阻断 1，成功 0；失败也留真实终态，无法持久化显式 partial |
| 下游复验 | 新会话显式报告引用及当前来源／规则 | 机器验证冻结输入／输出／执行 proof、当前身份和阻断 findings；不需要 Task | 只读复验不刷新旧 readiness；阻断报告不能充当有效 3A 准入 |

</frozen-after-approval>

## Code Map

- `scripts/python/_b_route_sources.py:228/389/525`：唯一 prepare／account owner，已有安全 Observations、原 bytes 归档、完成 event 和实际注册重新推导。提取只读公共验证 seam，供审计核全部 event 产物及重新解析；旧 prepare／account 行为、退出及零模型合同保持。
- `scripts/python/chapter5_semantic_reconciliation.py:117/213/294`：完整原文逐块独立 Extraction B 思路／纯校验可复用；`:770/883/912` fingerprint／reconcile 带 Task／authority／readiness，禁止直接调用来做 3A。
- `scripts/python/_mvg_evidence_transport.py:252/376/547`、`_capability_input_integrity.py:490`：复用无损／容量思想及最终请求测量；旧 audit hard issue 强制已有 Requirement／Flow，须用薄的来源寻址合同，不能套空 ID。
- `scripts/python/_planning_skill_common.py:517/574` 与 `codex_isolated_model_runner.py:640/668`：复用实际隔离 runner 描述／子进程生命周期、无工具验证及模型 receipt；固定 workspace 只含本请求的受限快照。Codex 当前可执行且 --describe 成功；认证／模型调用未验证。runner 的 environment-default 不是实际模型身份。
- `_b_route_codec.py`／`_b_route_inventory.py`：唯一诊断与安全路径／junction规则；不另造错误枚举。`_mvg_capability_generation.py:673/728/748` 的预检、请求身份和协调器复验作参考；不导入 Task／Capability 生命周期。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/python/_b_route_source_audit.py`（新）— 唯一审计 owner；`_b_route_sources.py` 提供共享只读输入／event 验证，扩展现有 `--stage audit|verify`；直接入口与 `dev_cli.py` 共用，不增第二套 CLI／记录权威。旧 prepare／account 回归保持。
- [x] 审计输入 — 显式 `--accounted <report.json>` 定位持久 account 及其真实 request／prepare／candidate；重新核所有冻结文件、当前原 bytes／glob、原生完整解析／注册推导及机械 accounting。允许已终态但仍有 unresolved 的合法 account 进入审计，保持原未决；损坏结构与缺 proof 阻断。首投影只进入第二步。
- [ ] 独立执行 — 每个完整来源文件（含全部块／空文件）独立 extraction；之后全局 comparison 读取全部原文、全部 extraction 和完整提议／验收意图／去向。每步 fresh 无工具隔离 runner，复用公共生命周期；输出严格 schema 和逐文件／逐块分母核验。模型产出义务、finding 和明确 disposition 审阅，不用关键词／相似度造语义结论。全局依赖包含全部来源；完整请求若装不下，明确 capacity 阻断，不截断或悄换摘要。
- [x] proof／事件 — 精确 prompt、schema、输入、runner 及协调器捕获的实际结果／receipt／输出原 bytes 绑定；schema／引文／完整覆盖由协调器复验，忽略模型自报 approved。显式 `--runner` 和 `--expected-model`，实际 identity／no-tools／完成计数须经可信本地 runner 的 receipt 与执行结果核对，default 别名不得冒充实际模型。公开报告区分 execution_complete、semantic_blockers、planning_eligible（不等于 formal_adoption）；所有原 account 未决合并入阻断。
- [x] 完成复用 — `--audit-ref` 显式选择原终态；复验原所有 proof／执行输出及当前适用身份。全量一致复用；仅来源变化时可复用未变文件的完整原独立 extraction，始终重做受影响全局 comparison；只变首投影可复用 extraction。parser／审计 schema／prompt／相关 owner 与 transitive runner 工具 bytes、结果相关 Python／依赖版本、指定及原实际模型身份均绑定。HEAD／Task status／时间戳不是有效性条件。损坏原 proof 明确拒绝，不自动当未命中重跑。
- [x] 预算与观测 — 每 run／scope 持久固定 request／活动预算和逐次 reservation，跨日期／attempt／进程不能归零、调高或并发超支；仅调用前短 metadata 保护，不持全局锁等模型。预留秒数是保守许可不是实际时间／账单；记录实际单调耗时、已观察 runner／model dispatch（不可知则 unknown）、复用来源／原因、返回及终止分类。相同 event 不重计，partial 不当完成重用。新输出仅 `logs/ci/<date>/b-route-source-audit/<run>/<attempt>/` 及对应 run 预算证据。
- [x] `scripts/python/tests/test_b_route_source_audit.py`（新）及必要受控 fixture — 逐行覆盖 matrix、实际 OS synthetic runner 生命周期／无 Task／多文件遗漏与冲突／预算跨 attempt、正负 CLI、exact replay；坏引用、缺／重复／乱序块、假 PASS、proof／规则／parser／相关工具损坏，相关变化及无关状态对照。独立 fixture 必须标明 synthetic。验证不写游戏、Task、旧证据。
- [x] `docs/workflows/b-route-source-audit.md`（新）、现有来源说明、`AGENTS.md`／`workflow.md`／稳定入口与脚本索引 — 只更新本能力 owner／使用合同，说明两步独立性、真实／synthetic 区别、状态／预算／复用限制和 Chapter5 责任；无启用声明。
- [x] `.github/workflows/story-2-2-windows.yml`（新，由协调器）— 只独立测试分支 push，contents:read／固定 github.sha／无凭据持久化；运行本 Story＋直接受影响回归、CLI 正负、真实 Windows junction／短路径拒绝；上传仅本轮 synthetic logs。只发布实现／测试／owner 说明／专用 workflow 的代码包，不发布内部 spec／Sprint／原始证据／全历史。


**Acceptance Criteria:**
- 用受控零 Task 原始需求故意漏投影交接；实际独立模型提取／比较须定位遗漏与原文并保阻断，另测跨来源冲突。保存真实模型身份、输入／输出和协调器验证；synthetic 测试只证明编排，不能代此项。真实 backend 不可用时如实阻塞，不记完成。
- 后续调用可只读验证完整已完成且无阻断报告的新鲜度；有 findings 的有效执行报告仍可定位但不得当准入。原 account 未决不可由审计 PASS 抹除。
- 仅实现文件完成且真实矩阵测试通过才进 native review；协调器读取完整 diff、原生三层 review、修复及最终回归／Windows 证据后按 Step5 收口。spec／Sprint／CI／Git 均归协调器，实施 agent 只动上述实现／测试／说明／必要入口导航，不提交／推送／另起 agent。

## Implementation Notes

当前停在原生 Step3，`in-progress`；独立执行机制已经实现，但真实模型验收仍阻塞，所以该任务保留未勾选。尚未进入 Step4 三层 review／Step5，不据 CI 或阶段状态宣布完成，也不启动依赖本项的下一 Story。

已新增唯一审计 owner、严格输入／引文／输出／执行 proof、完整文件独立 extraction＋全源 comparison、依赖闭包复用、跨 attempt/date 的固定预算及持久 reservation。既有 prepare／account 保持原合同。协调器的真实受控反例促成四类修复：删除预算证据不能退账、fresh workspace／step proof 结束前复验、坏 candidate 仍保存原有失败快照、仅审计 Python 子进程禁写 bytecode。生产／Task／旧证据／默认 B／退 A 无改动。

Linux 相关套件实际执行176项：174 PASS、2个真实 Windows 专用 skip；独立 CLI v2 的29次调用通过。第一轮 Windows run41828857551实际173 PASS、2 FAIL、1 POSIX skip，两个真实 Windows 方法已 PASS，CLI未运行；原始失败日志保留。两项失败是测试的路径预期：合法 root 别名 canonicalize，以及后端工具精确 host path＋raw digest 校验。只更正这两处测试入口，保留断言、安全检查与反例；两项 Linux 定向回归 PASS。

第二轮真实 Windows [run41831324047](https://github.com/skyoxu/newrouge/actions/runs/41831324047) 自然成功：176实际执行、175 PASS、1 POSIX skip，两个真实 junction／短路径方法 PASS；29次独立 synthetic CLI PASS。协调器从原始日志逐方法重数，核对17个被测文件的 Git blob／原 bytes（workflow checkout CRLF 单列），3452 tracked 原 bytes不变、无新增脚本 bytecode。原始日志158303字节，SHA256 `7f8a0f682ac8c089c7445506d6a6dad1d779d572ad69df6df504e9319c7e2bb1`；[原始日志](../../../logs/ci/2026-11-04/b-route-story-2-2-build/windows-run-41831324047-job-126578946400.log)、[核验记录](../../../logs/ci/2026-11-04/b-route-story-2-2-build/windows-run2-verified.json)、[逐方法明细](../../../logs/ci/2026-11-04/b-route-story-2-2-build/windows-run2-method-results.json)。这组模型结果全部 synthetic，真实 Windows 平台结果不会代替真实模型语义结论。

独立代码测试分支 `test/b-route-story-2-2-windows-2026-11-04` 的候选为 `18f54b10a4a2811eb8c167bc6289791d43c2c3e5`；只发布11份实现／测试／owner说明／专项workflow，不含本 spec、Sprint、内部日志、恢复材料或完整本地历史。用户已授权这类专项 CI，覆盖 Step3 默认 no remote 规则的这一具体边界；main、PR、merge、force 均未操作。本地 baseline／HEAD 保持 `2f7d36bdb6e1e0f9f3201a3df3c38bfb2dab6624`。

真实模型仍未完成：一次获批准的精确 CLI 探针已越过客户端只读状态目录初始化问题，但继承代理明确返回 `HTTP CONNECT 403` 至 `wss://chatgpt.com/backend-api/codex/responses`，自动 transport fallback 仍无输出，45秒预算后回收本次进程组。无真实模型输出／语义 receipt，实际 model dispatch unknown。当前托管策略 restricted/enforced，未允许该后端；本工具集没有修改配置能力。停止进一步模型请求，不绕过 proxy/TLS/DNS，不复制凭据或迁移 CODEX_HOME。须由受支持的环境配置流程提供获准后端连通性及客户端可写状态，再恢复本项实际模型遗漏／冲突验收；[精确阻塞记录](../../../logs/ci/2026-11-04/b-route-story-2-2-build/actual-model-backend-blocker.json)。

更广 MVG 的3项既有失败已由当前 helper 和精确 baseline 原 helper 分别窄跑，均2 FAIL／1 ERROR；原始输出在 `root-baseline-attribution/`。未算通过、未禁用，也未扩大本 Story 去修改。T108 历史原件仍缺、保护基准不可采纳、Epic1五项权限 false 保持。

## Spec Change Log

## Review Triage Log

## Design Notes

调研两位独立 agent 的源码与原合同结果一致：无必须询问用户的产品意图缺口。采用 per-file 完整独立提取＋全源比较属于常规实施选择；无安全局部比较证明时全源比较本就全部相关，不能假装保留旧全局结论。审计不引入 MVG 三候选／评选（2.5）或正式采纳恢复（2.9）。不可逆范围仅用户已授权的实际模型消耗与独立代码测试分支 CI；不扩大网络权限或披露内部材料。

本 Story 继续以 Story／spec／原始工具链证据纳管，不制造游戏 Task；不自动继承1.1或1.2豁免，依据本轮实际 Task-free 3A 工具合同自行判断。完整 spec 为单一审计目标，超过原生建议体积时，按用户“完成所有 Story、自行选择、不必再问”的明确授权保留全体合同；由独立 spec review 降低遗漏风险，非虚构新的用户确认。

## Verification

- `py -3 -B -m unittest discover -s scripts/python/tests -p test_b_route_source_audit.py -v`：全部当前适用方法运行通过；平台 skip 单列，真实 Windows 方法必须在 Windows 实际 PASS。
- `py -3 -B -m unittest discover -s scripts/python/tests -p test_b_route_sources.py -v` 加直接改动 helper／runner 的相关已有回归：原合同保持；不运行无关游戏／全量生产任务。
- 协调器独立 CLI 及实际受控模型：确认全源遗漏、跨来源冲突、无 Task／旧文件保护、容量零 dispatch、失败／复用终态，以及实际模型证明与 synthetic Windows 证明分别成立。时间、调用和账单 unknown 如实记录。
