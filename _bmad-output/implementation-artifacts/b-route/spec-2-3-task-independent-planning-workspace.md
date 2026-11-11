---
title: 'Story 2.3：Task 无关且完整的规划输入'
type: 'feature'
created: '2026-11-05'
status: 'done'
baseline_commit: '2d3d3ba7e81dd21ca559614f599e8c633e65945b'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 现有 Capability／MVG prepare 依赖 Chapter5、Task 与 readiness，无法在正式 3B 前置阶段使用合格的 3A 来源完成规划输入准备。另建自由读取管线会破坏来源守恒、审计身份和旧路径门禁。

**Approach:** 为现有两个 prepare 增加显式 `--input-stage 3b` 分支，共用一个确定性输入所有者；缺省保持原有后置语义。冻结完整审计范围、适用约束、复用上下文及有界传输证明，提供只读重验和完整后继 synthesis 请求构造。

## Boundaries & Constraints

**Always:** 逐项满足 B-route epics Story 2.3 AC1–5。正式 3B 必须重算有效、当前、无语义阻塞的独立真实审计资格，不能相信调用方布尔值；来源记账、原始 proof、规则／codec／工具身份均绑定。只写独占任务日志；保存原始字节及历史 batch 身份。所有输入、缺席声明、规则和容量参数参与身份；无关 Git HEAD 不参与。完整适用原文／对象、全局记账／守恒信息、跨批义务及完整前序草案不能丢失，容量不足失败关闭并给 `resume_ref`。

**Never:** 不用 `allow_unready`／draft 绕过正式资格；不要求 Task sinks、全局 Chapter5 witness、代码符号或 Godot 节点；不读取不完整 MVG run/readiness 缓存作为新准入。不分配稳定 Requirement/Capability/Flow ID，不执行候选生成、语义选择、正式采纳、apply 或恢复 journal（后续 Stories）；不冒充最终实施 InputSet。不触碰 main、PR、原恢复 nr、S2、认证、sessions、网络或全局环境；不发送新的真实模型请求。

## I/O & Edge-Case Matrix

| 场景 | 输入／状态 | 预期行为 | 失败处理 |
|---|---|---|---|
| 无 Task 正式准备 | 显式 3b、完整阶段合同、当前合格 3A | 两个既有 prepare 复用同一输入内核，冻结 stage、范围、来源／审计／规则／codec／上下文，零模型调用 | 不隐式读取后置门禁 |
| 上游不合格 | synthetic、遗漏／冲突、执行不完整、陈旧或被篡改 proof | 拒绝；历史 proof 原版本核验，当前资格另外核验 | 可定位诊断与恢复位置，不改原证据 |
| 上下文适用性 | 已有实现／共享能力／Task，或明确合法缺席 | 完整保留对象及原 ID；必需约束不可缺；可选缺席进入身份 | 未知类别、非法路径、坏 JSON／编码、声明与实物矛盾均阻止；不静默剔除 |
| 大范围与 synthesis | 多源、大对象、跨批关系、完整前序草案 | 所选范围的受治理闭包，未知依赖扩大至完整审计范围；无损批次、全局守恒与义务；按最终 wrapper/schema 和实际草案尺寸预检 | 禁止搜索／摘要／截断；不可再分的 core 超限即停止 |
| 重复与相关漂移 | 相同完成输入，或来源／规则／约束／上下文改变 | 未变完成材料只读复用；相关变更新身份并列明确失效依赖；旧材料不覆盖 | 半写／损坏完成材料不修成成功；另用新事件 |
| 旧阶段 | 缺省／显式旧阶段、Capability 显式 resume-evidence | 原有完整输入／receipt／真实模型身份及 Task/readiness 门槛继续生效 | 新 3b 材料不能被旧 generate/apply 当旧 run 消费 |

</frozen-after-approval>

## Code Map

- `_bmad-output/planning-artifacts/b-route/epics.md:848`：唯一 Story 范围与 AC；2.4–2.10 负责后续生成、采纳、恢复及集成，不能提前宣布完成。
- `scripts/python/plan_capabilities.py:269`、`plan_mvg.py:4411`：既有 prepare；在调用 `_planning_scope.round_scope`／Task／readiness／MVG manifest 检查之前路由明确 3b，缺省完整保留。MVG CLI 当前 capabilities/manifest 必填，改为按阶段验证必填，不能削弱旧分支。
- `scripts/python/dev_cli.py:824`、`dev_cli_builders.py:635`：两个公开入口的 parser 与转发；直接脚本和 dev_cli 必须一致。不要新增第二套命令管线。
- 新 `scripts/python/_b_route_planning_input.py`：唯一 3B 所有者，单向依赖 sources/audit/codec/transport。不要反向导入它到上游 fingerprint 模块造成循环。
- `_b_route_source_audit.py:722,972`：`validate_proof` 重建历史完整 proof；现有 verify 分支另验 scope、当前 `tool_identity`、当前 `load_accounted` 和 `make_input`。可提取只读 `verify_current_proof` 共用，不调用会创建新事件的 execute。原 runner／expected_model 从原 request 读取，实际资格由 proof 重算，不让 contract 覆盖。
- `_b_route_sources.py:52,64,213,255`：`checked_path`、Observations、独占日志／事件与 load_accounted；load_accounted 成功不代表审计合格。完整来源 bundle 在 audit.make_input；提案 ID 不升级为正式 ID。
- `_mvg_evidence_transport.py:376,455`：无损传输规划与 plan_errors，可复用。不要使用会过滤输入的 model_context／model_projection，也不要复用会清空输出、隐去对象并冻结 Task 的 build_blinded_analysis_bundle。完整结构对象可以作为无损编码证据，但不得变成摘要。
- `_capability_input_integrity.py:490`：最终序列化请求的 measure_request，实际 encoder，完整 schema 和 reserve；容量逻辑共用，不修改原预算。
- `_b_route_codec.py` 与已有 B-route schemas：严格 JSON、诊断、raw/canonical digest 和版本。prepare 日志不是第七类正式领域记录，不改正式 schema/策略/目录或 ADR0038–0040 门槛。
- `scripts/python/tests/test_planning_dev_cli.py`、现有 source-audit/Task-planning 测试：复用旧路径回归；新矩阵单独测试，不把 stub 阳性称真实审计通过。

## Tasks & Acceptance

**Execution:**
- [x] `_b_route_planning_input.py`：实现显式版本化 3b contract、冻结输入、只读 load/revalidate、内容身份、精确依赖／缺席及有界交付。阶段合同引用审计与明确 scope，约束原文必需且非空列表；上下文逐项声明类别、路径、是否必需、内容格式。支持实现／共享能力／Task 等复用对象，原字段原 ID 全保留；缺席仅限合同允许且可验证的可选项。对显式选定的 Capability／Flow 按有来源和身份、可验证的治理关系计算传递闭包，不能只相信调用者声明的依赖子集；未知依赖保守扩大到完整审计范围。全局记账／守恒 proof 与跨批义务始终完整，不随局部投影丢失。
- [x] `_b_route_source_audit.py`：提取既有当前验证逻辑供调用，保持历史重放合同；若源码依赖变化使旧 proof 当前身份失效，报告原因并保留原始证据，不伪造新版 proof。
- [x] `plan_capabilities.py`、`plan_mvg.py`、`dev_cli.py`、`dev_cli_builders.py`：增加 `--input-stage`（缺省 legacy）与单一 `--planning-contract` 参数，只有 prepare 可使用 3b；3b 拒绝 task-id、allow-unready 等混合门禁。两个直接入口与 dev_cli 均到同一内核。3b 输出使用独立日志命名空间和显式 schema/stage，旧阶段不得读成旧 run。
- [x] `_b_route_planning_input.py`：后继请求构造接口从冻结材料产生批次和 staged-synthesis 请求，固定完整交付模板／schema，携带全局 proof、跨批义务、所有前序草案及身份；记录全覆盖与无损重建证明，对实际返回草案重新预检。没有模型执行与第二套 budget journal。
- [x] `scripts/python/tests/test_b_route_planning_input.py` 及 CLI 测试：实现矩阵正负向与真实 OS 路径边界；断言零模型／runner 子进程调用、无隐式 Task/readiness 门禁读取、写入仅在独占日志。显式声明的 Task 复用上下文允许完整读取并绑定身份，单测完整交付；测试 CLI 壳所需的 Python 子进程单列，不能触发 runner。覆盖有治理证据的局部闭包、跨批依赖及未知依赖扩大。
- [x] `docs/testing/story-2-3-planning-input.md`：记录实际合同／CLI 例子、旧路径兼容、验证范围及当前真实阳性材料缺口；更新 Story 原生状态与证据。

**Acceptance Criteria:**
- 给定保留的真实遗漏／冲突 audit04，prepare 必须因原语义问题或明确相关工具漂移而拒绝，不能把模型发现抹成“合格”。synthetic proof 永不合格。
- 同输入重复 prepare 不创建新模型请求、不改变已完成输入字节；约束、source glob 成员、源码规则、schema、上下文存在性／内容任一相关改变触发可解释失效；无关 commit 和未声明 Task 状态不会触发重做。
- CRLF、尾随空格、空文件、长 JSON、跨批对象、未知嵌套字段均原样守恒；合法大对象可无损分片，core 或完整实际草案超限时停止且保存恢复位置。
- 旧 Capability/MVG 的 prepare/generate/apply、resume-evidence 与完整 receipt 验证测试通过；3b 不生成正式规划记录或旧 run.json。

## Implementation Notes

- 已实现一个 3B owner 与两个既有 prepare 的显式阶段路由；历史 delivery、原始观察分母及逐批模板冻结并只读重验，后继实际草案独占预检，原有预算与语义阻塞未改变。
- 独立规格审核两项已修订后复核关闭。最终源码的新矩阵／CLI 在稳定环境50项运行中全部通过；另有14项旧合同门禁通过。较广524项原始失败保留；稳定环境剩余6项均在独立基线2d3d3ba7上以同样错误复现，记录为未修复基线限制，不宣称全套通过。
- 两份真实audit04历史完整proof重建、原阻塞保留，因相关工具漂移拒绝新准入，零新真实模型请求；真实阳性3B准入未验证。普通令牌ACL问题以已授权提权处理；仅测试进程使用默认本地编码及私有短临时目录，没有改系统设置。
- 原恢复nr、main、PR、S2、凭据和sessions未触及；workflow.md仍为原有raw=HEAD的Git过滤状态差异。实现已由主线程读取最终完整stage diff，冻结意图哈希保持不变。

## Spec Change Log

## Review Triage Log

| ID | 裁定 | 路由 | 证据与处理 |
|---|---|---|---|
| B1 | medium | patch | 共置传输允许同文件范围重排，plan_errors 按其合法原始范围顺序验证，但 reconstruction 误按到达次序要求连续；重复长块已复现合法输入被拒。按源 offset 重建，保留既有完整覆盖校验。 |
| B2 | medium | patch | 普通来源路径 proof-bytes/user.md 合法，却仅因前缀被当 base64；实际解码失败已复现。内部归档表示必须与合法仓库路径无歧义。 |
| B3 | medium | patch | 关系 kind 为数组／对象时，外层 set membership 先抛 TypeError，未走已定义的未知治理扩大范围；已复现。先判类型，保留完整原文后扩大范围。 |
| B4 | false | reject | 审核方澄清其未实际复现且撤回缺陷表述。context.kind 仅是显式证据标签，无消费者据此认定正式 Task 或提取身份；空 Task 集合与 AC2 相容。不可添加未经需求授权的领域 schema 门槛。 |
| B5 | medium | patch | 主线程离线 assembly-seam 探针在 plan_batches 后改变相关 rules.py，prepare 仍发布 prepared；工具身份未在发布前重验，见 review-reproductions-01.json。补既有身份的发布前一致性核对。 |
| B6 | medium | patch | 历史只读 load(revalidate=False) 因当前计数器测量差异而拒绝完整旧 artifact，探针已复现。分离原版本字节／批次完整性与当前容量验证；当前正式消费仍严格重验。 |
| B7 | medium | patch | 已有完成材料后，上游当前性失败返回 blocked，但 invalidated_dependencies 为空；探针已复现。拒绝路径也应列出原准备引用、已知相关漂移和受影响范围。 |
| B8 | medium | patch | event.json 注入写失败后返回 blocked，但 resume_ref 指向仍声称 prepared/0 的原 report；探针已复现。保留部分现场，在可写时另存失败诊断并指向它，不覆盖旧事件。 |
| B9 | medium | patch | successor drafts.json 写失败直接抛 OSError，没有结构化恢复位置；探针已复现。处理已有持久化步骤的 IO 失败并保留部分现场。 |
| B10 | false | reject | 当前仅测试调用 prepare_successor；无生产消费者读 successor event 或把它当 sources.validate_event 权威。该产物是一次请求构造诊断，不是可复用审计／采纳生命周期；正式输入读取已由 load_prepared 完整核验。新增公共恢复 loader 会扩大本 Story 范围。 |
| E1 | medium | patch | 与 B1 同一根因；两文件共享长块时也能复现范围非到达顺序，仍须逐来源 offset 完整重建。 |
| E2 | medium | patch | 与 B2 同一根因；声明上下文也可能使用合法 proof-bytes/ 路径，不能推断编码。 |
| E3 | medium | patch | 与 B3 同一根因；合法 JSON 中未知治理字段的类型不能以未捕获集合成员异常替代保守扩大。 |
| E4 | medium | patch | 与 B9 同一根因；Windows 文件占用／磁盘写失败必须返回阻断及恢复位置。 |
| G1 | medium | patch | 预核实验证缺口：现有多批测试只检查 synthesis，未实际调用 batch 2 successor；删除后续批次前序草案仍可绿。补持久化请求、完整前序草案／身份和实测字节断言。 |
| G2 | medium | defer | 预核实的真实阳性边界缺口：所有成功组装替换只读 seam，原真实材料本来就语义阻塞；不能证明真实合格 proof 通过。沿用当前禁止新增真实调用的指令，保留已知上游材料阻塞，待有合格原始证据再补，不伪造 real 标记。 |

修复复核：13 条 finding 的 9 个根因均已修复，定向 31/31 通过；主线程最终执行 274 项，0 failure/error，1 项 POSIX 对应测试跳过，Windows 实际项通过，相关 8 个源码文件测试前后哈希一致。原边界审核方逐项确认 E1–E4 关闭，验证缺口审核方确认 G1 的 batch2/3 持久请求断言可检出丢草案突变。主线程已读取实际修复 diff，B5–B9 的期间漂移／历史测量／失效范围／写失败均有实际通过回归。G2 仍是明确的真实阳性验证限制，六项旧基线失败继续保留，不作全套回归通过声明。

## Design Notes

正式准入没有“测试模式”。当前真实两个受控 audit04 都有 blocking findings，不能提供正向 3B 材料。单元测试可显式替换只读验证 seam 来测试组装／容量／缓存，但必须隔离标注；另用原始真实和 synthetic 证据验证拒绝。实际真实阳性准入保持未验证，待有合格证据及允许新真实调用后再做。

用户在 `Sentinel_d2142aa9642c81918233a23b880472ed` 明确要求无人值守完成全部 Stories 并自行决策；本轮选择一个完整 Story 的 dispatch 路径，保留完整规格和独立规格审核，依据既有授权继续，未虚构逐项人工批准。没有未决产品意图；所有变更可逆，无迁移／部署／外发。

## Verification

**Commands:**
- 从任务根目录执行 `& 'C:\Program Files\Python312\python.exe' -I -S -B .\run_story23_tests.py <唯一报告标签> test_b_route_planning_input test_planning_dev_cli`。任务 harness 已复用独立 tokenizer/schema 依赖及编码缓存，报告不可覆盖。沿用 Story2.2 的解释器默认本地编码处理 Windows cmd，文档／证据显式 UTF-8；使用任务私有短临时目录，避免测试路径自身触发旧路径上限，不修改系统设置。此 Windows 普通受限令牌读取私有依赖／mode700 临时目录会失败；如需，使用工具的已授权 escalated 执行，不修改 ACL，不重复安装。
- 使用任务独立 Python/deps/cache 的 unittest harness 跑新输入矩阵、CLI 及相关 B-route／旧规划回归；网络连接由 harness 阻断，实际调用数为零。报告执行／通过／跳过数与失败原文。
- 用原始两组 audit04 作只读负向重验；保留源码改变导致的当前身份失效，不宣称旧证据变为当前合格。
- 检查 Git 变更、独占日志、最终请求／schema／实际草案尺寸记录以及完整 source/object 字节重建；按 native Step4 独立三方审查，处理真实问题后 Step5 本地收口，不 push/merge。
