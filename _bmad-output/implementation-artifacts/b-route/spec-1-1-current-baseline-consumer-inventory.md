---
title: 'Story 1.1 可复查基线与消费者盘点'
type: 'feature'
created: '2026-11-03'
status: 'done'
route: 'dispatch'
review_loop_iteration: 1
verification_scope: linux-and-native-windows-passed
verified_source_commit: 4aa86ba42eb2e06da84b2e40a87b099faca23be5
windows_workflow_commit: 337693441f7f021f034a7a260ef101d2a526c806
windows_verification_run: 41660349813
story_key: '1-1-生成可复查的当前基线与消费者盘点'
candidate: c5538a284037b9d06984f04fd997bc061ff2ca5f
baseline_commit: c5538a284037b9d06984f04fd997bc061ff2ca5f
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/SPRINT-SCOPE.md'
  - '{project-root}/logs/ci/2026-11-03/b-route-story-1-1-build/research.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

提供独立只读命令，固定当前输入、存量与消费者，区分已有能力和B缺口。Refs: B路线epics Story1.1 AC-1–5、FR-14/17、AC-BR-14/16。

## Boundaries & Constraints

保留ID、状态、历史和累计义务；master是状态权威。输出仅写新建logs运行目录。原始报告不覆盖，正式保护基准交1.5；不做来源语义审计、模型规划、Task写入、发布、切B或退A。脚本与测试遵守英文约定。本Story按用户已确认的工具链前置方案，以Story／Build spec／AC及原始测试证据跟踪，不新增或修改Taskmaster、不调用Chapter6；不改游戏代码、场景或存档。此决定仅适用1.1，完成不代表游戏Task或B路线运行完成。

## I/O & Edge-Case Matrix

| 场景 | 输入 | 结果／处置 |
|---|---|---|
| 正常 | 显式来源、三联、manifest、入口 | JSON/Markdown报告，保原始定位 |
| 缺损 | 缺失、坏格式、坏join、失效定位 | 具体诊断，非零退出，不作可采纳基线 |
| 重采 | 同内容 | 内容身份稳定；事件及时间另记 |
| 漂移 | 采集中输入集合、bytes或Git身份变化 | unstable，非零退出，要求重采 |
| 旧报告存在 | 相同输出位置 | 拒绝覆盖，保原证据 |

</frozen-after-approval>

## Code Map

以下均相对`scripts/python/`：

- `_planning_skill_common.py`：复用file_sha/canonical_sha/repo_path；atomic_json只写新日志。normalized_file_sha另列。
- `build_source_ledger.py`：复用resolve_sources及source-set读取，不调用写入／语义生成入口。
- `audit_task_triplet_delivery.py`：沿master.id→view.taskmaster_id，先查坏ID／重复；`_mvg_manifest.py`仅read/validate，非运行证明。
- `research.md`列出消费者及禁止调用的写入口；继承已有worker/checkpoint/recovery。

## Tasks & Acceptance

**Execution:**

- [x] `scripts/python/_b_route_inventory.py`：采集Git、十份canonical输入及AGENTS/ADR/Base/Overlay、source-set声明、三联和累计manifest；建立可核定位的消费者矩阵；前后重读完整集合，输出诊断与稳定内容身份。
- [x] `scripts/python/inventory_b_route_baseline.py`：独立CLI，显式root/epics/run-id；安全限定新logs目录，输出JSON/Markdown及退出码，不接planner或页面写链。
- [x] `scripts/python/tests/test_b_route_inventory.py`：fixture验证矩阵、路径边界、只读性、漂移、换行与Git特殊文件名。
- [x] `docs/workflows/b-route-baseline-inventory.md`：Windows运行及失败处置示例；保持默认路线。

**Acceptance Criteria:**

- Given当前仓库，when盘点，then分列完整HEAD/分支、声明代码基线、raw digest、工作区差异与采集身份，历史提交不冒当前。
- Given消费者，when生成矩阵，then每行含文件／符号定位、读写职责、A/目标B差异、后续Epic；覆盖research所列全部类别，ADR状态读正文。
- Given存量，when按原join读取，then保Task状态／历史及Flow/test身份与证据；状态差异只报告。
- Given异常或重采，when保存，then符合I/O矩阵且权威文件、旧报告及发布指针原字节不变。

## Implementation Notes

最终补丁验证：两轮原生三路评审的30项finding及后续WIN-1／WIN-2 patch已处理。最终测试源`4aa86ba42eb2e06da84b2e40a87b099faca23be5`在Linux和真实Windows均59项通过，Windows无跳过；真实CLI双采、缺损诊断、拒绝覆盖及输入／输出父目录junction均通过。原生产模块及CLI没有因Windows测试修复而改变；仅测试按解析身份注入故障并断言实际命中，原业务断言保留。按原生Step5将本spec置done，范围内Sprint保持review供后续审阅；不改变Taskmaster状态。最终Windows原始job日志与矩阵核对在`logs/ci/2026-11-03/b-route-story-1-1-windows-ci/run-41660349813/`，Linux最终回归在`logs/ci/2026-11-03/b-route-story-1-1-windows-ci/test-fix-20261103T150316Z/`。历史T108缺失仍使真实盘点adoptable=false，不补造原报告，也不把本Story完成称为B路线／游戏运行完成。以下实施记录按历史保留。

Round1回补后的当前验证：43项fixture全绿，状态比较反转及空Markdown两个mutation均被断言拒绝；587 inputs／102 consumers／38 ADR／3 manifests／1,415 refs。双采内容身份相同、事件不同；既有文件原字节未变，新增仅logs。唯一error是历史`logs/ci/2026-05-06/sc-build-tdd/summary.json`缺失，真实报告稳定但invalid／adoptable=false／退出1；此为如实记录存量缺口，不补造数据。首轮闭包不完整的stable报告已被本轮报告替代，不得用于1.5。最终Linux证据：`logs/ci/2026-11-03/b-route-story-1-1-build/final-verification-20261103T105723Z/summary.json`。原生Windows未验证。

首轮实现新增纯读模块、CLI、21项fixture测试和使用说明；报告覆盖325 inputs、216 consumers、3 manifests、38 ADR。113项状态差异仅报告。Linux验证日志已保存；Windows验证仍未完成。

2026-11-03：用户已确认仅Story1.1采用工具链前置跟踪，并明确授权继续实施／验证。此前“必须先创建Task”的判断收窄为适用Chapter6入口的门禁；不扩展到其他Story。原草案及已有未提交上下文已备份到logs中的implementation运行目录。

## Spec Change Log

2026-11-03，round1 bad_spec回补：B1/B2显示消费者与Task证据闭包定义不够具体，导致可采纳结论遗漏真实输入。首轮四份实现已归档到`/workspace/newrouge-b-story-1-1/logs/ci/2026-11-03/b-route-story-1-1-build/implementation-20261103T102006Z/archive-v1`并撤回待重推导。KEEP：独立只读CLI、新logs目录不覆盖、双次发现／raw bytes／Git-z与blob身份、原始三联和累计manifest、状态差异只报告、既有worker恢复能力不重建；保留所有首轮证据，禁止改Task／游戏数据或降低AC。

## Review Triage Log

| Finding | Verdict | Route | Evidence |
|---|---|---|---|
| B1 | medium | bad_spec | 实际存在plan-capabilities/plan-mvg技能及sc Chapter4生成器，当前DISCOVERY/GROUPS均未覆盖；消费者清单不完整。 |
| B2 | medium | bad_spec | Task原始行虽保留，test_refs及evidence_refs没有存在性／raw身份闭包；成熟测试改变不进入采集身份。 |
| B3 | medium | patch | fixture新增master3且两视图均缺失仍stable；audit_task_triplet_delivery.py:223要求至少一侧映射。 |
| B4 | medium | patch | fixture同一视图重复BACK-9映射不同master仍stable；没有核验业务ID自身。 |
| B5 | medium | patch | fixture master2删除status仍stable；仅比较get值，没有拒绝缺失／坏类型状态。 |
| B6 | medium | patch | fixture移除ADR正文状态仍stable；unrecognized未进入诊断；冲突声明同样须保未知。 |
| B7 | medium | patch | fixture第十来源改为planning//source-0.md仍stable，仅九个实际文件；未拒绝非规范路径。 |
| B8 | medium | patch | safe_input仅精确匹配logs/.git，Windows大小写别名能到相同禁用目录。 |
| E1 | medium | patch | fixture新增合法examples/helper.py得到Missing Python symbol:<document>；文档型Python条目应免符号查找。 |
| E2 | medium | patch | 独立复现同B6，缺ADR状态没有诊断且返回可采纳。 |
| E3 | medium | patch | 独立复现同B5，未被manifest引用的master状态损坏仍获可采纳。 |
| E4 | medium | patch | 独立检查同B8；Windows路径别名与目标平台边界不符。 |
| E5 | medium | patch | 脚本无3.12最低版本门禁；is_junction缺失时直接跳过，老Windows Python的目录reparse指向仓库内非logs位置可绕过输出边界。 |
| V1 | medium | patch | 验证层实测!=变异为==仍全部21项通过；差异数量相同不能证明内容正确，需精确断言两端状态／pointer。 |
| V2 | medium | patch | 验证层实测Markdown返回空字符串仍全部21项通过；需读取实际保存的Markdown核对动态内容。 |


### Round 2

| Finding | Verdict | Route | Evidence |
|---|---|---|---|
| R2-B1 | medium | patch | read缓存命中在safe_input前，先evidence_refs缓存logs、再test_refs读取同路径可绕过角色权限；须每次先验证。 |
| R2-B2 | high | patch | 三个git diff未显式禁ext-diff/textconv；Git外部驱动可实际写额外文件，违反只读边界。 |
| R2-B3 | medium | patch | 发现集合可空；删除Chapter技能目录后没有必需入口诊断，仍可采纳；AGENTS明确路由五章技能。 |
| R2-B4 | medium | patch | required=False将ValueError路径安全失败降为warning，planned symlink可被采纳；只有可选FileNotFound可警告。 |
| R2-B5 | medium | patch | ADR扫描全体行未排除fence/comment；示例中的Accepted可替代真实声明。 |
| R2-B6 | medium | patch | git超时抛TimeoutExpired，CLI仅捕获OSError/ValueError/UnicodeError；不能保存失败证据。 |
| R2-B7 | medium | patch | CLI先create_run_directory后Git顶层校验；--root repo/planning写到真实仓库logs以外的planning/logs。 |
| R2-B8 | medium | patch | 所有example都进UTF8文本consumer；合法PNG资源引起invalid-consumer-locator，应保raw而不作文本入口。 |
| R2-B9 | low | patch | JSON已有完整Git changes，Markdown只列HEAD/branch；直接渲染现有差异字段可补人工审阅定位。 |
| R2-B10 | low | patch | Markdown cell仅转义pipe/newline；<date>渲染成标签，原始模板定位不可见；直接HTML转义。 |
| R2-E1 | medium | patch | 与R2-B6同根因，Git TimeoutExpired可传播并留空目录。 |
| R2-E2 | medium | patch | discover os.walk没有onerror，权限拒绝会静默遗漏authority子树且稳定可采纳；safe_source_pattern同样需可见失败。 |
| R2-E3 | medium | patch | 与R2-B7同根因，nested root先写planning/logs后拒绝，不符合真正仓库logs边界。 |
| R2-V1 | medium | patch | 验证层内存禁用全部manifest reference仍43项通过；原fixture被Task/source-set/authority重复覆盖，需专属未跟踪引用与漂移断言。 |
| R2-V2 | medium | patch | 验证层从GROUPS删try_adopt仍43项通过；fixture及类别预期都依赖同一实现清单，须独立路径／符号断言。 |

### Native Windows follow-up

2026-11-03，原生Step4 patch跟进：原implementation子agent在当前会话不可恢复（agent列表仅当前root），按Step4 fallback由主agent应用最小补丁。Windows run `41659061158`的透明路径跟踪确认两项测试mock的短／长路径身份不一致：`RUNNER~1`与`runneradmin`解析后为同一目标；read_bytes mock调用170次、词法命中0次／解析身份命中2次，source walk调用11次、词法命中0次／解析身份命中1次。reparse反例自身已正确拒绝，问题不是生产盘点工具吞掉权限异常。

| Finding | Verdict | Route | Evidence |
|---|---|---|---|
| WIN-1 | medium | patch | 两项测试按原始Path词法相等注入故障，Windows临时目录8.3别名使mock漏命中；只改测试比较为resolve身份，并新增故障注入实际执行断言，保留adoptable=false／具体诊断／resolver不得执行等原断言。原临时根路径仍保留，未消除别名反例。 |
| WIN-2 | medium | patch | 专用CI把缺失epics强制断言为failure.json，与CLI及使用说明“可建立报告时保存inventory+诊断”的合同不符；改为核对退出1、不可采纳及明确请求路径的错误诊断，拒绝旧epics回退。生产脚本未变，CI只在独立测试分支。 |

最小测试补丁固定源提交`4aa86ba42eb2e06da84b2e40a87b099faca23be5`；相对其父`241543d9c6e56859314e0d52a0459958501b4105`仅改`test_b_route_inventory.py`。Linux59项全部通过（14.273秒），证据`logs/ci/2026-11-03/b-route-story-1-1-windows-ci/test-fix-20261103T150316Z/`。run `41659061158`是修复前故障诊断，不能当最终全套通过；最终候选的run `41660349813`已成功，三项独立测试、59项全套及真实CLI／junction均通过。日志下载域名政策限制未绕过；原始job日志通过授权GitHub连接器留存，本轮目录之外的历史日志已从上传规则排除。

## Design Notes

Round1重新推导细则（保持冻结意图）：

- 消费者清单显式包含`.agents/skills/plan-capabilities/**`、`plan-mvg/**`和实际Chapter4入口`scripts/sc/llm_generate_overlays_batch.py`；按真实文件／符号定位，不能仅有同类别的替代条目。发现的合法Python文档／示例不查找`<document>`伪符号。
- 沿三联已有`test_refs`及`evidence_refs`记录每个原引用、所属文件／JSON pointer、原Task ID与master join；存在的实际文件进入双读与raw摘要闭包。`source_refs`等带行号路径按已有合同定位，不把事件ID当文件。历史`<date>`模板、未交付历史证据及缺失引用明确记为unknown／missing并说明，不捏造证明；必需输入无法核验不得给可采纳基线。日志仅可按已有明确证据引用只读定位，禁止全扫logs或把本次输出反向作为来源，保留原始记录。
- 三联检查双向join、每视图自身非空唯一ID及master ID／taskmaster_id、status存在且为合法原始字符串；规则与现有master编译合同／业务视图状态一致，合法差异仅报告，绝不规范化回写。
- ADR正文无状态或互相冲突的声明进入unknown诊断，不能stable可采纳。规范化相对路径拒绝重复分隔符及Windows大小写／尾点空格别名，唯一性按真实规范路径核对；输入及输出检查junction/reparse点不随Python缺少is_junction而失效。
- 测试必须精确断言完整状态差异集合及相同状态不入集合，并读取实际保存的Markdown，核对动态定位、职责与失败诊断。加入以上每个实测反例；保留首轮正负与只读测试。原生Windows仍未验证，不能借Linux断言冒充。

内容身份包含输入与规则身份，排除事件／时间／绝对工作目录。raw与Git blob换行身份分列；入口矩阵采用可核查清单，不声称自动证明语义完备。只读采集不承诺外部并发写者隔离。

## Verification

最终结论（2026-11-03 UTC）：固定测试源`4aa86ba42eb2e06da84b2e40a87b099faca23be5`，Windows workflow `337693441f7f021f034a7a260ef101d2a526c806`的run `41660349813`／attempt1自然结束success。Windows Server2025／NTFS、Python3.12.10、Git2.56.0.windows.4；59项全套PASS、0skip，单测进程263.912秒。三项独立测试也PASS，路径跟踪及新增命中断言证明两个故障注入确实执行，原不可采纳／拒绝resolver断言成立。真实CLI双采内容身份相同、事件不同，均只因既有T108历史文件missing返回1且stable=true／adoptable=false；重复run-id退出2且旧报告不变；缺失epics退出1，inventory.json明确missing-input／invalid-epics指向所请求路径，无旧epics回退。真实NTFS输入junction被拒绝并留下reparse诊断，输出父junction退出2且目标空目录无写入。全部既有tracked源文件raw摘要及Git状态前后相同。五行I/O矩阵均有已运行且通过的测试，详见`logs/ci/2026-11-03/b-route-story-1-1-windows-ci/run-41660349813/matrix-audit-final.json`及原始job日志。

最终原始证据：同目录`job-126001574165.log`、`summary.json`、`jobs.json`、`artifacts.json`及hash清单；job日志本地SHA256为`2a236ff01bb471e887d02a124a790b7d87ab076fa4e7eb31b3dac810625c6872`。GitHub artifact `13242266782`成功上传，平台报告ZIP SHA256为`a759cb6ad57a7500c631ea2e95e8b5407e69bbc11e2a0befdf1b3afe31b81fd4`，保留至2026-11-17T15:11:50Z；本云环境因明确Domain forbidden策略未本地下载／解压ZIP，不声称已本地核验ZIP或全部Windows JSON字节。平台结论由已取回的原始job日志、实际检查断言及成功artifact元数据支持。历史报告缺失不是本Story工具功能失败；正式保护材料及未解决历史运行证明由Story1.5审阅，不能把invalid采集报告当正式可采纳基线。

以下是按时间保留的历史验证，未修复时的in-review／Windows pending／failure描述不覆盖上述最终结果。

2026-11-03 Windows CI首轮：专用workflow提交`abcc7dd27b8c4047eb3b4650641fa524b40f59fb`，固定被测代码`bad70a5e446b2c4f3263d3e8c1fd2d1c6781b65f`，run `41649303346`／attempt 1已自然结束为failure。Windows Server 2025、Python 3.12.10、Git 2.56.0.windows.4；单测子进程触及workflow的240秒上限而被终止，没有完整59项结果，不能据此判断断言失败或测试卡死。后续真实仓库CLI及真实junction探针未执行。runner打印的保护检查为源文件及Git状态未变。原始job日志、远端artifact元数据及来源明确的runner摘要保存在`logs/ci/2026-11-03/b-route-story-1-1-windows-ci/run-41649303346/`；artifact `13235614619`已上传成功，但本云环境下载签名文件地址被网络策略403拒绝，尚未本地读取／核验ZIP或其中unit.stderr。没有改网络策略、重新触发或伪造历史报告；spec保持in-review，Sprint保持review，Windows验收未完成。此前阿里云Windows执行环境交接提示失效：该服务器属于jimuyun，本Story未访问它。

最终结果优先：`logs/ci/2026-11-03/b-route-story-1-1-build/final-verification-20261103T111539Z/summary.json`，59项PASS、两个mutation被拒绝，CLI双采稳定／同内容不同事件、既有文件无变化。更早的43／40／21项记录保留为历史。原生Windows CLI及junction实测未运行，当前环境为Linux，因此按Step4验证边界停止，不宣布完整验收完成。

当前结果以`logs/ci/2026-11-03/b-route-story-1-1-build/final-verification-20261103T105723Z/summary.json`及同目录原始日志为准：43项通过，两个mutation被杀死；以下21项为首轮历史记录。Windows仍未运行。

实施后执行：`py -3 -m unittest discover -s scripts/python/tests -p test_b_route_inventory.py`，全部通过；Windows运行独立CLI，核对报告、非零退出及无副作用。Linux检查不替代Windows证据。实际Linux验证：21项fixture测试通过；真实仓库双次采集stable且内容身份相同、事件不同；重复目录退出2，缺失epics退出1。3,419个既有文件原字节不变。原始证据见logs/ci/2026-11-03/b-route-story-1-1-build/implementation-verification-1/。原生Windows CLI未运行，当前Linux环境无法提供；不宣称平台验收完成。
