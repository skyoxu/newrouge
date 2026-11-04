---
title: 'Story 1.5 存量保护与冻结A输入'
type: 'feature'
created: '2026-11-03'
status: 'done'
route: 'dispatch'
approval_state: delegated-routine-implementation
review_loop_iteration: 0
baseline_commit: fc9fd0d62dedf4dc70660074c453f4bf420c8650
story_key: '1-5-形成可审阅的成熟成果保护基准与冻结a输入'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/SPRINT-SCOPE.md'
  - '{project-root}/_bmad-output/planning-artifacts/b-route/epics.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

交付原Story1.5 AC1–5的只读保护能力及可审阅输入：保护成熟Task、累计义务、当前状态和历史，供Epic2接收；不凭旧done或缺trace推断A。

## Boundaries & Constraints

本Story是确定性Harness保护输入，AC5禁止新Task；以Story／spec／实证纳管，不造游戏Task或调用Chapter6。三联、游戏、旧证据、默认A和既有兼容不变。原始bytes与语义身份分存；master仍唯一状态权威。投影只删除真实Task及其直接subtasks[]的status，其他嵌套status、Acceptance、依赖、来源、责任、semantic_review_tier、未知字段及数组顺序均保留。

新采集复用1.1并重核报告的来源／测试／历史引用闭包raw；历史报告只作可核验回链／差异，不能当当前证明。保留累计manifest完整对象、映射和人工限制；削弱须来源及显式审阅，不执行apply。冻结A候选逐Task绑定定义、source scope、旧操作候选和审阅依据；无完整已提交反向证明即blocked，不用空清单伪装零Task。

T108历史summary仍missing；ADR0040:88禁止以不可采纳capture认证正式保护基准。交付能力和带未决项的已审候选，不授正式保护／A资格。版本化最小输入是external owner材料，不是第七类policy或状态权威；不生成policy／origins／catalog、journal或receipt，不实现receipt投影复验。用户已委托持续全部Story及常规方案／审阅选择；仅root执行Git、版本化实际审阅和必要独立Windows CI，不发布内部原始日志。

## I/O & Edge-Case Matrix

| 场景 | 输入 | 期望 |
|---|---|---|
| JOIN | 完整三联；错类型／重复／孤儿／无业务映射master | 严格双向join；错误公共诊断，无隐式ID转换 |
| PROJECTION | Task或subtask状态推进；其他定义／未知字段／顺序变化 | 前者只改state/raw；后者改definition；无关其他Task变化不连带失效 |
| CAPTURE | 当前raw、旧1.1报告；缺引用／权限／中途后编辑 | 保存真实bytes、身份、原定位及限制；观察漂移拒绝稳定结论 |
| CUMULATIVE | 原Flow／test／handoff／人工限制；删除／降级／新责任 | 完整保留，差异及审阅要求明确；旧done不满足新增责任 |
| FROZEN_A | 133真实Task；零Task；缺来源／反向治理证明 | 逐项候选blocked或真实空集合；不能自报reviewed授权 |
| COMPARE | 状态推进、定义改动、后编辑／损坏旧snapshot | 保存当前状态及raw；分别报告差异，旧材料不授写入 |
| CLI | 新run正例、坏参数／输入、重复run、真实Windows链接 | 仅新logs写输出；原输入／旧日志不变；失败结构化可定位 |

</frozen-after-approval>

## Code Map

- `_b_route_codec.py`：严格JSON、raw／canonical、安全reader、Diagnostic；投影codec单一常量owner，`_b_route_records.py`保原别名及target_projection_verified=false。
- `_b_route_inventory.py:465,684`：完整join／引用闭包／双采；不以parsed重序列化冒充raw。`TaskJoinContext.indexes()`缺每master映射检查，不可单独当完整join。
- `update_mvg_baseline.py:46,88`：复用累计削弱／审阅规则；不调用apply。人工限制还在manifest.coverage.excluded_claims。
- `_b_route_record_owners.py`：frozen_a_inventory仅核locator／raw；不解释资格。当前无正式policy／catalog／origins不证明legacy。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/python/_b_route_protection.py`：共享纯Task／三联投影、只读保护采集／复核／比较；复用已有身份、join、累计规则，显式false授权结论。
- [x] `scripts/python/capture_b_route_protection.py`：capture／compare／verify所需只读入口；全新logs保存inventory、snapshot及关键raw归档，禁pycache／覆盖。
- [x] `scripts/python/_b_route_codec.py`、`_b_route_records.py`：共用既定projection codec ID，保旧API／算法和receipt限制。
- [x] `scripts/python/tests/test_b_route_protection.py`：矩阵正负、真实变化／无写入、完整当前与零Task、损坏／漂移／历史缺失回归。
- [x] `docs/workflows/b-route-mature-protection.md`及旧record合同必要事实导航：唯一API／文件形状、PowerShell、资格限制。
- [x] `docs/planning/b-route/protection-input.v1.json`：root于实际审阅后保存最小版本／身份引用／逐Task候选、review、未决及Epic2条件；完整采集留logs。
- [x] `.github/workflows/story-1-5-windows.yml`：root按必要范围提供独立test分支、contents:read、固定事件SHA、有界真实测试／CLI，上传仅合成fixture证据。

**Acceptance Criteria:**
- Given原Story1.5，when核验全部矩阵与真实当前材料，then AC1–5均有源码／原始证据，未决历史和正式资格阻断明确。
- Given实际采集及比较，when审阅版本化输入，then raw可核、定义／状态分离、累计义务完整、无写入授权；缺失／损坏不能获得正式资格。
- Given测试结果，when收口，then Linux与真实Windows分别记录，skip不算通过，三联／游戏／旧证据未变。

## Implementation Notes

Step3最终实证：候选fac5aa3d84b7ab664186390fb217ce0f92bdc481/run41715825812/job126195414580自然成功；37保护＋55codec＋93records=185全部通过、0skip，6组真实CLI符合退出码，真实GetShortPathNameW／junction分支执行，3437 tracked无变化。9公开源码blob与当前一致，保护进程178.844秒、37项各有实测时间；raw UTF8 log128053 bytes SHA256=a9b3d650e7c171101d5960940e4b2e886bad28cf3ce11f481e0c8e19e5d4a277。Linux37通过，旧codec52＋3skip／records90＋3skip分别保留不混算。全部矩阵有实际通过方法。

实际材料：原snapshot raw ffbc5f0330ab36d66ed817d6fe5dc58999dfa2ea4987549435b9c5beec5870be；588原件／1415引用／133定义及状态／三完整manifest经根与独立只读材料复核。最小版本化input以固定raw＋pointer绑定完整tasks/frozen_a数组，不复制第二权威。真实CLI capture1／verify0／compare1／duplicate2／badarg2，3651既有文件raw不变。stable不等于完整保护；唯一必需missing仍T108，133A候选均blocked，87历史资格／6source scope未证不是87实文件缺失；五授权false。当前正进入原生Step4，Story状态本身不作验收。

Windows预算校准：首轮34保护方法实际171.968秒未超时，但有真实断言失败，已先修产品别名和注入seam。现新增必要反例及CLI成功路径，保护方法37；Windows保护suite预算定为240秒并新增逐方法实测开始／结束计时，其余套仍180秒，整job10分钟／内部480秒不变。此为已授权测试范围内的执行安排，不豁免断言、不以重跑绿色改写原失败。

2026-11-03 Step3源码与实证复核：root在原件副本复现重签inventory envelope可假称capture_complete，以及删去113项真实状态差异后归档仍通过；已交原实施者最小重建校验，沿原1.1 owning规则，不改冻结意图／Task状态／正式资格。原件和修前反例均保留，不能用自报字段证明采纳。

2026-11-03 首轮真实Windows候选ec494a693b9a00b2337acac7f93861c85cd3f93f/run41713762576/job126188285086自然失败，34保护方法中4方法失败（含6个late子例，总9fail），0skip，171.968秒且未超时；codec55／records93全部通过。CLI根的8.3／long物理别名导致真实writer拒绝，late注入POSIX／Windows表示及permission注入物理身份另待分辨最小修复。9个公开源码blob与该候选一致；原日志UTF8 SHA256=1b61b1b093fe1c64d27a104f5a77dfb73e6a495aebb807f47e9f5e8ea6bc4f24。失败不升级Story状态，不以增加预算代替修断言／产品。

2026-11-04 Step4补丁：仅同一实施者修六组问题，新增manifest成员和source-set原owner关系反例，原11定向通过后再单项通过；当前保护方法46。原真实Windows37方法178.844秒，故本轮补丁验证预算调至300秒，codec／records仍各180秒、内部480秒／job10分钟不变。仅覆盖新增实际反例范围，不放宽断言或改写首轮失败。完整新源码与真实Windows尚待root核验；不能沿用fac5的绿色当最终补丁证明。

## Spec Change Log

## Review Triage Log

三层均完整返回后才裁定；无数量门槛。独立原始探测／搜索／变异输出已原字节保留至本轮logs/review-evidence；以下逐条裁定在分组前完成，提议guard不当成现有代码。

| Finding | Verdict | 验证依据及影响 | 分组／路由 |
|---|---|---|---|
| BH-1 | medium | 原epics仍声明planning/source-0.md，副本删其inventory/raw索引绑定并重签后verify仍ok／complete；同bytes可能仍被其他path去重保存，但该必需path的原件身份无绑定。已读closure_probe.py/原stdout及当前_inventory_rows/_load_snapshot，仅检查自报集合覆盖，未核原声明。 | G2／patch |
| BH-2 | medium | 真实int→bool使definition内容与digest不同，_load_snapshot以Python相等仍接受；manifest未知义务1→true canonical不同却差异为空。已核两原stdout和当前相等分支，类型身份失真。 | G1／patch |
| EC-1 | medium | 独立0→false合法manifest字段反例，两canonical不同、report ok而manifests=[]；当前document==分支忽略JSON类型。与BH-2相同Python值相等根因，原行保留。 | G1／patch |
| EC-2 | medium | 独立重签快照Task id=true对原raw整数1被接受，write=0亦通过dict相等；已核原probe与当前raw-derived/Python比较。全局授权输出仍false，但已核材料不忠实于原类型。 | G1／patch |
| EC-3 | medium | 必需evidence原index仍exists=false／引用missing，删error后重签report/snapshot并complete=true得到ok且无未决诊断；_inventory_identity只从自报diagnostics算adoptable，未按原required关系复核。 | G3／patch |
| VG-1 | medium | 按原生验证层预验证规则信任其全仓搜索＋隔离变异：Task added/removed清空仍37通过，真实CLI [1,2]→[1,3]漏报3/2，原实现清单正确；持久化comparison缺回归保护。 | G4／patch |
| VG-2 | medium | 预验证：仅跳过Flow防削弱仍37通过；两个有效handoff删一条，真实CLI漏flows/flow及weakening标记。旧混合test可被tests/test削弱满足，不能保护独立Flow分支。 | G5／patch |
| VG-3 | medium | 预验证：candidate.a_eligible反转true仍37通过，CLI capture/verify均0且两个blocked候选资格true；全局false不消除逐项信息错误，缺精确is False断言。 | G6／patch |
| P-1 | medium | 补丁复核先以真实单项red证实：discovery／raw仍保manifest，却可删派生manifests／引用／累计数组并重签通过；原义务漏报。按归档discovery＋raw及1.1遍历成功集合重建，修前单项失败、修后及46完整套通过。 | G2／patch |
| P-2 | medium | 补丁复核真实单项red：raw SOURCE_SET.active_sources非空而自报resolved为空，删原source-set-mismatch后重签仍complete；原owner要求error。保原sorted集合关系及error义务，合法不完整归档仍允许archive-integrity-only。修前／后原文保留。 | G3／patch |

原三层8条及补丁复核另2条均为当前保护能力的可复现完整性／验证问题，非本轮spec编辑建议。G1为同一JSON类型相等缺陷的各处表现；G2是原声明集合完整性，G3是已保留missing的必需性判定，二者不因可共享helper而合并；G4–6各为独立验证缺口。最小修复只校验已展示输入／既有owner要求并补定向反例，不新增公共接口／状态权威／权限，均patch，无intent_gap／bad_spec／defer。保已正常工作的双身份、合法status推进、全部旧raw证据、false授权、真实Windows别名／安全guard及原有通过行为。

## Verification

`python -B -m unittest discover -s scripts/python/tests -p test_b_route_protection.py -v`及受改codec／records定向回归，Linux各套180秒；Windows保护suite300秒、codec／records各180秒；CLI正负／重采／比较／输入raw守护。真实Windows10分钟job与内部480秒总预算，必需平台项不可skip；输入只读，输出仅新logs。原失败与未执行项如实留证。

## Final Verification

2026-11-04：最终候选23e8a9d145637547e3ad2e9b17e92825e4da2596，run41788129017/job126434906893自然success，46保护＋55codec＋93records=194通过、0skip，6CLI预期退出码全部符合；真实Windows短路径／junction／占用方法通过，3437 tracked未变。保护套242.172秒，raw日志133346bytes SHA256=7bc21e3f289959da19b07b53f383146ae78e7bed331bed7bbd9ffdb610c19207。9 Git blob一致，5 Python raw完全一致、4说明／workflow检出raw准确对应CRLF转换，不称9 raw完全一致。Linux46通过0skip；最终588当前原件重验及旧archive完整性通过，complete=false／T108保留。

原生三层8条及补丁复核2条分别裁定，六组全修，无defer／loopback，review_loop_iteration=0。材料独立核对133Task／1415引用／3完整manifest／11OwnedRef一致；正式保护与冻结A资格全false，非启用或游戏验收。完整证据见logs/ci/2026-11-03/b-route-story-1-5-build-201113Z/native-review-closure.json。
