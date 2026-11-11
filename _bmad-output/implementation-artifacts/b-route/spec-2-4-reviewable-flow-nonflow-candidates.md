---
title: 'Story 2.4：可审阅的 Flow 与合法非 Flow 候选'
type: 'feature'
created: '2026-11-05'
status: 'done'
baseline_commit: '1339eb6a40413bf37491eac0a2f793c68dafec3c'
route: 'dispatch'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** 已有 3B 冻结输入，但旧 planner 仍不能在无 Task 时读取完整逻辑候选；现有 Flow 合同只有循环说明文本，不能检验实际图、责任及累计验证关系。

**Approach:** 沿 Capability 的 validate-candidate 与 MVG 的 validate 增加显式 3b 读取分支，共用一个候选结构 owner 和公开版本化辅助 schema。完整描述 Flow／职责／非 Flow 去向，验证声明图与关系；本 Story 交付原 AC 明确允许的读取路径，实际生成、独立 admission、评选归 2.5。

## Boundaries & Constraints

**Always:** 满足 B-route epics Story 2.4 AC1–5；先默认当前重验有效 prepared，再精确绑定候选 input_identity。完整保留来源、临时 proposal 身份和既有身份、四部分适用职责、状态所有者、交接、UI 输入／反馈／进入返回及适用人工义务。确定性结论限于声明与引用结构，真实语义由 2.5 独立审阅。保三组 Requirement 键、唯一权威处置、多路线角色、共享证据去重和精确 coverage_table 投影。所有写入限独占 logs，失败关闭、保现场、给诚实诊断与恢复位置。

**Never:** 不要求 Task／readiness、实际 C# 符号／场景已创建；不机械四拆或节点转 Task，不强制 DAG、每 SCC 外出边、所有节点必达终止或可执行退出 DSL。不以空标签授 N/A，不把结构通过称为采纳、readiness、Flow 完成或运行证明。不分配持久正式 ID，不写正式 plan／catalog／receipt，不制造 adoption proof，不改既有六类记录 v1 的接受语义，不凭上下文类别标签声称 published/current owner。不得新增真实模型请求；不触碰 main、PR 合并、nr、S2、凭据、sessions、认证或网络设置。

## I/O & Edge-Case Matrix

| 场景 | 输入／状态 | 结果 | 失败处理 |
|---|---|---|---|
| 完整直接候选 | 当前合格 prepared、完整 manual/external envelope | 两 planner 同 owner 检查；保完整来源／身份、Flow 图与职责，输出 candidate_structure_only | 不制造 DRAFT 历史；标签仅为声明，不证明上游无模型 |
| 模型 DRAFT 候选 | 明确模型类型、完整有序原 DRAFT 链 | 原 schema、同 input_identity、连续 ordinal/stage、全部 parent identities 和最终内容绑定 | 截断／错序／篡改拒绝；不得自动降级 external，不构造额外下一次请求 |
| 图与循环 | 分支、重试、自环、跨 Flow、边界后重入 | 端点、owner、必要可达性、SCC、退出说明与边界对应；内部 ID 按 Flow 限定 | 未知端点／重复身份／无主责任／必要目标不可达拒绝；边界可在 SCC 内且仍有后继 |
| 累计关系 | 一 Requirement 多 Flow、跨 Capability、共享定义／证据 | 单一验证处置、完整 memberships、去重证据、唯一有效 owner；七字段投影一致 | 不自动 legacy 投影；重复权威／缺路线／错证据范围／owner 冲突拒绝 |
| 非 Flow 与缺口 | other_verification／deferred／source_gap | 来源理由、适用性、其他验证义务或明确 unresolved；保 UI／人工责任 | 空字段／仅标签／未解析必需引用拒绝；缺口不被记为完成或 Task 豁免 |
| planned 与历史 | 未创建对象、既有快照、重复或漂移输入 | planned 可合法描述；既有 ID 保留；当前性重验，未变完成检查可只读复用 | 旧阶段门禁保持；相关变化阻断／新身份，旧证据不覆盖，无关 HEAD 不单独失效 |

</frozen-after-approval>

## Code Map

- `_bmad-output/planning-artifacts/b-route/epics.md:897–944`：本 Story 原 AC；2.5 才做实际模型／receipt／独立 admission／候选选择；2.6 才持久分配与采纳。`docs/workflows/b-route-record-contract.md:82–98,120–129` 指定四部分、三关系键、文本条件与允许循环，并将图细化留给本 Story。
- `scripts/python/_b_route_planning_input.py` 的 load_prepared／build_request／prepare_successor：默认当前重验；build_request 的 DRAFT 链检查可提取纯 helper 供读取共用，不改变冻结 v1 schema。直接 manual/external 文件不要求虚构模型链。读取最终候选不用 prepare_successor，不做下一次 synthesis 容量预检。
- 新 `scripts/python/_b_route_candidate.py`：唯一候选内容／图 owner，单向依赖输入 owner、codec、公开辅助 schema 与纯关系检查；不得反向导入 planner，或读取 Task／自由搜索来源。
- `scripts/python/plan_capabilities.py:2457`、`plan_mvg.py:7291`、`dev_cli.py:824`、`dev_cli_builders.py:635,676`：现有 3b 只放行 prepare。精确增加 validate-candidate／validate 分支，在旧 _load_run／Task／manifest 前路由；planning-contract 仍仅 prepare，generate/review/apply 不整体放开。沿用 prepare_from_cli 的 lexical root 校验，不先 resolve 掩盖 root junction；实际 Windows 路径边界回归保留。
- `docs/planning/b-route/schemas/common.schema.json:24,765,789,872`：复用 String、PartKind、PartResponsibility、LogicalDefinitionUse 和 Requirement 关系定义；新逻辑 owner key 不冒充已分配 plan ID／修订。现有 plan.schema.json 没有 nodes/edges，不可把文字 loops 当 SCC 覆盖。
- 新公开辅助 `flow-graph.schema.json`、`planning-candidate.schema.json`：各有独立 v1 `$id`；复用现有公开定义，明确是辅助输入格式，非第七类正式记录，不放宽 plan.v1 的 adoption_proof_refs。
- `_b_route_records.py:118–160`：离线 schema loader 当前硬编码 common＋六记录。将通用资源加载提取到 `_b_route_schema_resources.py`，或等价共用单一 loader；正式六记录入口资格与辅助资源注册分开。资源按实际字节 digest 参与缓存／候选规则身份；旧 formal-only 调用不因缺少新辅助资源而失效，未知 ref 不走网络。
- `_b_route_records.py:235–270,714–831`：纯唯一性、精确 coverage 投影、owner／关系规则可提取复用；完整 validate_bundle 要 catalog/receipt／TaskJoin，不能把它变成未采纳候选前置。
- `_b_route_record_owners.resolve_owned_ref:111` 接受纯 read_bytes；_b_route_records._Bytes:560 在 root=None 时无磁盘回退。既有引用只从 prepared 冻结 bytes map 解析精确版本／digest／闭包，不自由读取当前 catalog。快照匹配不是 published/current 权威验证。
- `_mvg_requirement_routes.pair_errors:167/route_errors:190`、`_mvg_requirement_accounting.accounting_errors:224/accounting_summary:501`：复用纯关系与去重规则，显式提供三组键；不要调用旧自动补投影、Task/runtime boundary_errors 或 validate_manifest（后者即使 executable=False 也读 Taskmaster）。
- `_b_route_sources.py` 的 Observations／checked_path／独占日志及 `_b_route_codec.py` 的严格 JSON、诊断、raw/canonical 身份：保全原字节，不统一 trim 字符串，不新增另一套来源读取管线。

## Tasks & Acceptance

**Execution:**
- [x] `docs/planning/b-route/schemas/flow-graph.schema.json`、`docs/planning/b-route/schemas/planning-candidate.schema.json`、`scripts/python/_b_route_schema_resources.py`／`scripts/python/_b_route_records.py`：公开辅助版本、单一离线解析及缓存身份。候选包含完整 envelope／input_identity／明确 provenance；内容覆盖来源、逻辑定义／owner、Flow 结构、四部分适用职责、Requirement 三关系与兼容投影、非 Flow／UI／人工义务。新 proposed owner／逻辑键和已存在 ID 区分，不借用正式采纳 metadata。
- [x] `_b_route_candidate.py`：读取并当前重验 prepared，严格解析完整候选；manual/external 与 model_draft 为明确分支，禁止解析失败自动降级。模型链才共用原 DRAFT 外壳／完整链检查，最终 content 必须对应实际候选。仅确认本次读取 dispatch=0；外部来源与模型执行历史保声明／unknown，不把匹配 input_identity 当成作者已读全部原文的证明。
- [x] `_b_route_candidate.py`：完整结构与图索引，节点／边／边界按 Flow 限定且不歧义；端点和状态／命令／交接责任须解析到已声明唯一 owner。图允许跨 Flow、同节点多边界角色与重入；对明确必要目标检查从入口及相关循环位置的可达性。用真正 SCC 算法识别自环／多节点环，循环说明通过锚点与声明退出边界关联，可一条说明覆盖多个循环；边界可在 SCC 内，不要求无后继或每 SCC 外出边。输出有限声明图事实，不证明运行一定退出。
- [x] `_b_route_candidate.py`：当前候选定义与显式选定冻结依赖按类型／ID 唯一 owner，未选历史修订不竞争 owner；精确既有引用只证明冻结内容匹配。已解析图缺少必需外部端点时拒绝或明确未解决，不造假节点。按当前受治理 scope 核对适用完整 Requirement 去向，保全全局记账分母与 scope 外清单，不把合法范围外项目自动改成获批延期。临时 proposal 保临时身份，prior_requirement_ids 仅作回链。
- [x] `_b_route_candidate.py`：复用纯三关系校验及七字段 coverage 投影；唯一 verification、完整 Requirement×Flow memberships、同 Requirement 证据复合键去重，跨路线共享不重复计完成。非 Flow 需来源依据和验证／authority／unresolved；结构层只验声明、引用与对应关系，语义真实性留 2.5。planned／已有引用／运行证明和 UI 人工义务明确区分。
- [x] `plan_capabilities.py`、`plan_mvg.py`、`dev_cli.py`、`dev_cli_builders.py`：分别沿 validate-candidate／validate 支持 `--input-stage 3b --prepared-ref ... --candidate ...`，保既有 run-id 作调用标识；缺省 legacy 不变。输出及只读复用限新日志命名空间；输入／schema／工具漂移拒绝或新身份，写失败返回诚实现场位置，旧事件不补写。
- [x] `scripts/python/tests/test_b_route_candidate.py`、相关 schema/CLI 回归：逐行覆盖矩阵；含实际 SCC、成功边界在 SCC 内、同内部 ID 跨 Flow、同节点多角色、可选不可达节点不被强制必终止、未知/重复端点、缺 owner／退出对应、共享去重／投影漂移、非 Flow/空标签、原字符串空白与 IDs、字节篡改／同长 schema 改动缓存失效、旧 formal-only 资源兼容、写失败、当前输入绑定、model 链错序／截断且无降级。成功组装显式 seam，实际 synthetic／原真实负向拒绝分开，不冒称真实准入。
- [x] `docs/testing/story-2-4-flow-candidates.md` 与公开 record owning docs：记录精确格式、CLI、可判定范围、planned/运行及 candidate/adoption 区别、真实阳性缺口与实际测试结果。更新原生 spec/sprint 并本地收口，不推送。

**Acceptance Criteria:**
- Given 当前合格 prepared 与完整候选，when 通过任一 3b 读取入口，then 同一结构 owner 核对完整身份、声明图与累计关系，planned 对象无需实际创建，且不授任何采纳／readiness／运行资格。
- Given 自环、合法循环、成功／取消／返回后重入或跨 Capability Flow，when 做 SCC／引用／必要可达性检查，then 合法边界在 SCC 内仍通过；错误端点、无主责任、必要不可达或未关联退出说明失败，报告准确的有限检查范围。
- Given 一个 Requirement 多 Flow／共享证据或合法非 Flow，when 核对，then 只保一个权威处置与精确兼容投影，源理由和所有适用义务保留，source_gap 不成为完成。
- Given 旧正式记录／legacy planner 与冻结历史 proof，when 新辅助资源及候选检查加入，then 旧 v1 接受语义／门禁不变，无需伪造 Task、catalog 或 adoption proof；已知六项基线失败按原证据保留，不把定向通过说成全套绿。

## Implementation Notes

读取分支与公开辅助格式已实现。主线程读取实际基线 diff 后复现 S3-1：任意 JSON context 被错误当成当前 Requirement 域；现已修复为当前审计 proposals 与显式 selected 有效依赖，按各自 ledger 核对 scope，历史闭包仅保原字节及引用完整性。未修改冻结意图或原正式 v1 接受语义。

实际冻结回归 context_frozen10 为 170/170，无失败、错误或跳过；候选 33、CLI 13、正式 records 93、3B input 31。矩阵六行逐项核实到实际通过 test ID，源文件前后哈希一致。主线程扩大回归及旧基线对照另列：原 root-frozen-06 的 5 项 legacy errors 在 2d3d3ba 独立旧基线精确重现，不能据定向通过声称全套绿。真实合格 3A/3B 阳性准入仍未验证，没有新真实模型请求。

原生 Step4 审核和 Step5 状态/本地提交在后续各自阶段执行；本节不宣称已经审核或提交完成。

## Spec Change Log

## Review Triage Log

| Finding | Verdict | Route | Evidence |
|---|---|---|---|
| B1 | medium | patch | 最终 DRAFT content 用 Python 等号比较，布尔 true 与整数 1 被视为相同。主线程原链探针通过而 canonical JSON 身份不同；须精确绑定 JSON 内容。 |
| B2 | medium | patch | planned 对象仅保 later_checks=[engine] 仍通过，丢失原 AC 与 owning doc 指定的类型、编译、绑定义务；在现有封闭枚举上保完整检查集合并覆盖遗漏。 |
| B3 | false | reject | capability_ids 是尚未采纳候选的声明逻辑标签，不是带 schema/修订/digest 的已发布 Capability 引用；公开说明明确不授正式 owner 权威，返回仍为 candidate_structure_only。把标签替换为 NONEXISTENT 只改变该声明，不产生正式身份或采纳；其来源语义真实性由原 2.5 独立审阅承担。没有证据表明此处声称已解析 existing 实体，建议新增 Capability registry 会增加合同外公共机制。 |
| B4 | medium | patch | 声明的 State 虽全局可解析，Flow 的 state_owners 为空仍可使用该 State；Flow 层完整责任清单会与节点/交接使用分离。核对实际使用与显式 Flow 声明对应，保共享 owner，不分配新身份。 |
| B5 | medium | patch | 主线程在 SECOND 中放置仅属于 FLOW 的 handoff，因任意位置的边存在而通过。与已有 edge 归属规则一致，handoff 至少一个端点须属于所载 Flow。 |
| B6 | low | patch | 平行声明边不同 ID/条件合法，但 adjacency set 把四条边统计为三条；finite graph facts 报告错误。只修正计数，不拒绝合法平行边。 |
| B7 | medium | patch | 精确选定的 plan 内 source_ref=not-frozen.txt 且无对应 OwnedRef 仍通过；纯记录本地验证不检查完整证据绑定。复用已有纯 plan_evidence_checks，保 frozen bytes 闭包及历史完整性，勿引 Task/catalog/current 门槛。 |
| B8 | medium | patch | 选定 Requirement 的旧 ledger path 在所属 manifest.sources 完全缺失仍用于 scope 核对；主线程删空 manifest 绑定并重绑原字节后通过。要求唯一所属 source binding 后才用路径判定 scope。 |
| B9 | high | patch | 主线程修改缓存 report/event 的 formal_adoption、runtime_verified、node_count 并重算报告 digest 后，读取返回这些伪造标记。validate_event 仅证明内部自洽，须与本次新计算的完整报告/固定标记及实际候选原字节绑定，失败不修复旧事件。 |
| B10 | medium | patch | Kosaraju 第二遍 reachable 先重遍已处理分量再减 seen；主线程 1000/2000/4000 节点 DAG 为 0.117/0.501/2.012 秒，呈平方增长。第二遍遍历中排除已见节点，补长 DAG 正确性/线性工作量回归，避免易碎壁钟阈值。 |
| E1 | low | patch | 独立边界层也复现四条声明边被统计为三条，与 B6 同一实际计数缺陷；本行先独立裁定，之后才合并。 |
| G1 | medium | patch | 覆盖层预验证：仅移除循环到 required boundary 检查，46 项候选/CLI 仍全过；entry 可达 success 但已进入自环仅可到可选 cancel 的反例会被误收。增加精确负向回归。 |
| G2 | medium | patch | 覆盖层预验证：两个 builder 均删除 --input-stage 3b 后，46 项仍全过，但生成命令运行退出 2。执行两条实际 builder 参数列表并断言成功，精确检查 selector/值。 |
| G3 | medium | patch | 覆盖层预验证：现有重复节点是完全相同对象，schema.uniqueItems 已拒绝，不能保护同 ID 不同正文的语义唯一性。移除 node key guard 后专门反例会误收；增加不同 responsibility/owner 正文回归。 |

## Design Notes

采用原 AC 的“读取完整候选”分支，不在本轮执行生成；后续 2.5 可接既有隔离执行／预算协调器，不能为读取手工候选伪造 batch/synthesis 历史。模型 DRAFT 输入若存在则保原有全链合同。真实 3A 合格阳性材料仍缺失，当前禁止新真实调用；所有阳性 seam 仅验证组装／结构，不能填补真实准入证据。

成功边界不是无后继 sink：`entry → act → success → entry` 是合法重入候选；SCC 可包含 success，机器仅证明声明边界可达。条件、责任与 source 支持是否充分由独立语义审阅判断，不引入关键词黑名单、通用 trim、四 Task 规则或任意程序终止证明。

公开图辅助格式承载完整逻辑数据，不改变旧正式 plan.v1 的字段接受集合。后续 2.6 采纳必须通过明确的正式 schema／引用合同保全该图及其身份，不能把完整图丢成文字摘要或只留不可移植日志；本 Story 不伪造正式记录来提前完成该集成。

图遍历与 SCC 使用现有标准库实现，避免新增依赖；长链／长环不应因 Python 递归深度形成任意输入上限。身份按限定元组处理，不能用可能相撞的字符串拼接替代。

用户已明确无人值守完成全部 Stories 并自行作技术决定；本轮无未决产品意图、迁移或外发，公开格式／CLI 选择属于可逆实现决策。使用完整 dispatch 规格与独立规格复核，继续沿原授权执行，不虚构逐项人工批准。

## Verification

**Commands:**
- 从仓库 nx 目录运行 `& 'C:\Program Files\Python312\python.exe' -I -S -B ..\run_story24_tests.py <unique-label> test_b_route_candidate test_planning_dev_cli test_b_route_records`；使用任务私有既有 schema/tokenizer/cache，继承默认 Windows 本地编码处理 cmd，证据 UTF-8，私有短临时目录与禁止子进程字节码写入，必要提权但不改 ACL／系统设置。
- 最终源码冻结后主线程跑本 Story 全矩阵、公共 schema／六记录回归、3B 输入及明确旧门禁回归，记录真实执行／失败／skip、源码前后哈希与项目模型调用范围；保留原失败，不替换旧断言拿绿。
- 主线程读取实际完整 diff 和矩阵覆盖，再做原生三层审核／逐项裁定／验证修复，按 Step5 本地提交。真实正向准入仍单列未验证，服务端实际模型／物理请求数未知。

主线程冻结复核 root-context-11：280 项实际执行，275 通过、0 failure、5 legacy errors、0 skip；5 项堆栈与旧基线逐项相同。本轮 33 项候选矩阵及 14 项明确旧门禁均通过，11 份本轮源码/schema 前后字节哈希一致。原生三层审核开始，尚未提交。

## Native Step4 Closure

三层共 14 条逐项裁定后，B3 以公开逻辑声明与正式引用的区别驳回；其余 13 条归为 12 组最小修复并验证。B1 精确 JSON 身份、B2 四项后续义务、B4 状态声明、B5 交接归属、B6/E1 平行边计数、B7 依赖证据、B8 manifest 绑定、B9 缓存重算及原候选绑定、B10 线性 SCC 和 G1–G3 测试缺口均已闭合。E1 与 G1–G3 由原独立审核层复核，无残留；四次变异均被新断言捕获。没有扩大正式记录合同、增加 Capability registry 或修改冻结意图。

最终主线程 root-review-final-12：291 项实际执行，286 通过，0 failure、5 已在旧基线精确重现的 legacy errors、0 skip。本轮候选 44 项、原六行矩阵覆盖与 14 项旧门禁全部通过；11 份源码/schema 前后原字节哈希相同。主线程原反例重放确认非法输入与缓存篡改拒绝、合法平行边保留、被篡改旧事件不修复。完整证据位于 logs/ci/2026-11-05/b-route-story-2-4-build 与 story24-tests；不得说整套 legacy 测试全绿。

真实合格 3A/3B 阳性准入仍未验证，且未新增项目真实模型请求；上游声明不是执行证明，服务端实际模型及物理请求数仍 unknown。下一步仅原生 Step5 本地状态/提交收口，不推送或合并。
