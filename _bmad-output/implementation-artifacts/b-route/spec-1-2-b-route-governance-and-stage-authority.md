---
title: 'Story 1.2 B阶段、权威与启用治理'
type: 'chore'
created: '2026-11-03'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
story_key: '1-2-明确b阶段顺序-记录权威及迁移启用规则'
baseline_commit: bfe6e3731035ab48e61b55291dd94919f2830ee2
approval_state: delegated-governance-adoption-approved
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/SPRINT-SCOPE.md'
  - '{project-root}/logs/ci/2026-11-03/b-route-story-1-2-build/research.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

将已确认的B阶段顺序、权威及迁移启用边界落实为可审阅ADR和导航。承接Story1.2 AC-1–5、FR-14/17；不重新选择架构。

## Boundaries & Constraints

保留来源语义、Taskmaster唯一状态、Core契约、累计manifest及原始证据权威；Knowledge仍派生。两份0038和0039用完整文件名继承，不整体废止A。明确治理已定义、实现待交付、启用待条件三者不同。

实施须先获本spec批准，再产出Proposed全文。全文展示后用户已明确委托代理内部技术审阅、判断并持续完成本Story；须按此授权记录真实来源，经独立来源核对及治理审阅才可采纳Accepted，并在原生Build评审通过后收口，不虚构额外人类投票。不得改游戏程序、既有Task身份／状态／历史或质量阈值，不造3A/B/C命令、不切默认B／退A／发布／推送。本阶段不提交Git、不创建PR或合并；T108缺失如实保留。

已批准的本Story纳管：仅Story／Build spec／ADR审阅和证据跟踪，不新增Taskmaster任务、不改三联、不进Chapter6；此安排仅限1.2纯治理文本，不继承1.1例外，不豁免后续实现。

</frozen-after-approval>


## Code Map

- `docs/adr/ADR-0038-semantic-delivery-topology.md:21`：仅对B演进顺序条款；其余权威保留。另两份完整继承名见research。
- `docs/architecture/ADR_INDEX_GODOT.md`：正文状态为准；落盘前已重查0040空缺并分配，采纳后同步状态导航。
- `workflow.md:204,514,1684`、`AGENTS.md:30`：现行A入口；增加目标B说明，不改执行路径。
- `docs/workflows/stable-public-entrypoints.md:7`：保留既有命令，仅补治理导航。
- `scripts/sc/_acceptance_steps.py:34,47,55`：裸0038解析有歧义；状态检查不等于审阅采纳，不为调用Task检查虚造ID。旧ADR guide的Node工具不存在。

## Tasks & Acceptance

**Execution:**

本Story纳管及spec已批准；Proposed全文已展示，用户随后明确委托内部判断、采纳及完成Story。以下前三项为起草阶段记录，最后一项记录本次授权下的治理采纳。

- [x] `docs/adr/ADR-0040-b-route-stages-authority-and-activation.md`：新增Proposed，编号落盘前重查；覆盖阶段、权威、继承、冻结A／切B／退A／补偿条件。
- [x] `docs/architecture/ADR_INDEX_GODOT.md`：新增准确状态和完整文件链接。
- [x] `AGENTS.md`、`workflow.md`、`docs/workflows/stable-public-entrypoints.md`：同步定义／待实现／待启用导航，保留A命令。
- [x] 上述ADR及索引：Proposed全文已展示；按用户随后明确委托，经独立来源审阅采纳Accepted，记录授权原文和真实审阅依据并同步导航；未把采纳解释为B实现或启用。

**Acceptance Criteria:**

- Given已确认来源，when审阅阶段表，then涵盖3A审计、3B无Task采纳、3C承接、4–5绑定／readiness、6单Task、适用7及Flow／累计收尾；3B不需场景，6不需本Task已done。
- Given规划记录，when核对权威，then采纳从属来源，无新数据库或第二状态机，既有worker／恢复规则保留。
- Given迁移说明，when核对启用，then默认B等待后续消费者／恢复反例／奖励双路径，A冻结和退出各有条件，补偿保后编辑及B来源。
- GivenADR治理状态，when读取导航，then未采纳时准确显示Proposed，采纳后准确显示Accepted且仍未启用；只有具备实际授权与治理审阅准入后才完成本Story。
- Given文档变更，when核对范围，then技术基线、P1／测试及分支保护不变，无提速／成本／Task数量门槛。

## Implementation Notes

2026-11-03：完整加载frontmatter三份context和SPEC全部七份companion，核实0040未占用后新增Proposed全文。ADR保留两份0038及0039的Accepted正文与完整文件继承，仅提出B范围Chapter顺序演进；同步四份导航，现行A命令及执行路径未改。治理采纳、实现交付和迁移启用分别表述；T108历史缺失原样保留。本次按已批准的1.2纯治理纳管跟踪，不写Taskmaster／不进入Chapter6，Sprint保留实施前已有in-progress状态。

起草阶段历史记录（已由文末新授权取代）：ADR与索引全文供用户审阅，当时尚无针对该全文的明确采纳，因此ADR保持Proposed，最后一项保持未勾选，spec及Story均未完成。Build spec批准不代替ADR采纳；Accepted及实际审阅依据须待用户明确采纳后再更新。

## Spec Change Log

- 2026-11-03（本次重新授权）：frozen采纳权限按用户完整正文展示后的明确委托更新；不再要求第二次人工确认。禁止Git提交／推送／PR／合并及产品、Task、启用边界不变。治理采纳经独立来源审阅，Story收口仍须原生Step4；不是用状态绿自证。

- 2026-11-03：仅更新实施勾选、记录和验证；frozen-after-approval区块及批准边界未改。新增ADR及导航的审阅快照、diff、raw SHA-256和结果位于`logs/ci/2026-11-03/b-route-story-1-2-governance-implementation/`。

## Review Triage Log

2026-11-03（原生Step4）：已在处理任何层结果前同时派发blind-hunter、edge-case-hunter、verification-gap，均明确指定gpt-6.1-sol／ultra。按用户“不以发现数量驱动”指令移除数量下限；三层原始返回分别为“未发现已确认的问题”、“[]”、“No verification gaps found.”。无finding需要分级、修补或延期；review_loop_iteration保持0。原始结果与派发快照见`logs/ci/2026-11-03/b-route-story-1-2-build/adoption-and-final-review-20261103T161146Z/`。这只是本Story治理变更审阅，不代表运行验收。

只读交叉复核发现并已修正一项P2导航时态：workflow第9章明确“迁移启用后”才以正式冻结A边界限制后续实施／恢复，避免把待交付冻结清单误作当前A的新前置；其余五组AC与继承／启用边界未发现必修缺漏。该复核不是用户全文采纳。

起草阶段历史记录（已由文末新授权取代）：全文采纳当时待用户审阅；机器状态及链接通过不作为采纳凭证。T108缺失及Story1.5正式保护基准审阅责任继续保留，无补造历史证据。

2026-11-03：独立只读草案复核未发现必须修正的P0／P1／P2；核对了阶段／非Flow／权威、完整ADR继承、迁移时态及现行A命令保留。该复核和根目录定向检查记录在`logs/ci/2026-11-03/b-route-story-1-2-build/resumed-sol-ultra-20261103T155158Z/`；仅支持提交Proposed全文供用户审阅，不代表原生Step4或Story已完成。

## Verification

`git diff --check`及改动白名单核对；使用`read_adr_status(Path)`定向读取候选与继承正文，逐个核对链接和索引。人工逐项对照上述AC及用户ADR审阅原文，机器状态绿不替代采纳。记录diff／hash及结果到新logs目录；无程序变更不调用Chapter6、游戏测试或Windows CI。

起草阶段历史验证（已由文末新授权后验证取代）：0040当时为Proposed，两份0038及0039均Accepted；新增／变更治理导航的22个本地链接目标存在。最终白名单、现行命令保留、前像／后像及五组AC对照结果见该目录的`verification.json`和`verification.md`。本次验证只证明文档一致性；AC-4的用户全文采纳仍pending，不宣称完整Story验收通过。

## 本次授权后的恢复与采纳

2026-11-03：上述“待用户全文采纳”均为先前Proposed交付时的历史状态。用户收到完整正文后，以Sentinel_39fadc89f544819196b438f6f3b5d7c7明确委托代理按建议持续完成整个Story并自行判断。代理据此独立核对权威来源，采纳0040治理定义并同步导航；不虚构额外人类投票。frozen区块仅按本次明确重新授权更新采纳边界，其余禁止提交Git／推送／PR／合并、Task／游戏及迁移限制保留。原始授权、候选全文前像及来源核对保存于`logs/ci/2026-11-03/b-route-story-1-2-build/adoption-and-final-review-20261103T161146Z/`。下一步为原生Step4三层评审，尚不以此次状态更新单独宣布Story完成。

2026-11-03（新授权后）：0040定向读取为Accepted，三份继承ADR仍为Accepted且原始字节未变；31个本地Markdown链接目标存在；3409个tracked文件与实施起点逐字节对照，仅四份获批导航发生变化，三联／游戏／来源均保留。全部原有fenced命令块逐项相同、diff检查通过、Git index为空。记录见`logs/ci/2026-11-03/b-route-story-1-2-build/adoption-and-final-review-20261103T161146Z/step3-verification.json`。AC1–5逐条来源核对及本次真实授权支持治理采纳；仍待Step4原生评审，未宣称B运行完成。

## 原生 Build 收尾

2026-11-03：Step3任务与AC1–5已核对；Step4三层评审均返回，无确认缺陷／验证缺口，无延期项。Step5将spec置done，将B范围Sprint的本Story置review；该状态不等于Task、运行、Epic或默认B完成。按用户仍有效的“不提交Git”限制，覆盖Step5默认本地提交动作：本次不git add、不commit，也不push／PR／merge；不是权限失败，不另要求常规确认。没有启动其他Story。T108历史缺失由后续1.5继续审阅，未宣布capture可采纳。

最终定向验证、完整diff、文件哈希和AC对照见`logs/ci/2026-11-03/b-route-story-1-2-build/adoption-and-final-review-20261103T161146Z/final-verification.json`及`README.md`。fast／service tier无可用回读接口，不能宣称已开启；三个原生评审及独立来源审阅均以gpt-6.1-sol／ultra显式派发。
