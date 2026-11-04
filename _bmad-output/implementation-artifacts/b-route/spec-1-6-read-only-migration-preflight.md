---
title: 'Story 1.6 只读迁移预检与Epic2交接'
type: 'feature'
created: '2026-11-04'
status: 'done'
route: 'dispatch'
review_loop_iteration: 1
baseline_commit: 952b1d8658e5e3c328ec4cc5b7948bffe77e418a
story_key: '1-6-通过只读预检审阅迁移差异与阻断原因'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/SPRINT-SCOPE.md'
  - '{project-root}/_bmad-output/planning-artifacts/b-route/epics.md'
  - '{project-root}/docs/adr/ADR-0040-b-route-stages-authority-and-activation.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

交付原Story1.6 AC1–6：从公共CLI只读比较明确候选与当前来源、对象、Task和累计义务，定位差异、需审阅项与真实阻断；汇总Epic1交接，不等待未来发布服务。

## Boundaries & Constraints

复用唯一codec／六schema、严格join及1.5定义投影。候选完整原bytes，不调用旧compiler的补默认／status／ID转换；显式reuse/update/new/retire不等于语义批准。机器可核身份／集合／状态／累计削弱，语义来源支持和外部审阅只作未核验输入，不能自报授权。保成熟ID、三联映射、当前状态／历史、B归属和累计义务；合法零Task及planned场景不要求假实施。

不写Task、正式规划、manifest、指针或旧证据，不调用模型、apply、恢复写者、Chapter6或游戏；输出仅全新logs。按本Story只读Harness与AC纳管，不沿用1.1／1.2通用豁免，不制造游戏Task。本Story不是正式publisher、启用判定gate或第七正式治理记录。

未启用须有明确权威依据，不能从文件缺失或候选自报推legacy；当前ADR明确未启用只适用无相反治理痕迹的预启用观察。存在治理痕迹／启用依据而关键policy/catalog/origins缺失或损坏，保守unknown／damaged阻断；结构合法也不证明已提交。没有schema.enabled，不新增该字段。旧pending保留并导航原apply恢复，未知scope阻断；不调用未来journal。T108仍必需missing，1.5正式保护／A五授权false；真实预检可受阻，工具能力可由完整fixture验收。

## I/O & Edge-Case Matrix

| 场景 | 输入 | 期望 |
|---|---|---|
| PREVIEW | 原身份绑定的完整候选／显式意图 | 来源／对象／Task／累计差异、定位和身份；机器与语义待核分列 |
| SAFETY | 成熟ID／状态覆盖、断join、删B归属、无依据退役／减义务 | 公共六字段诊断、实体及阻断；旧done不满足新增义务 |
| GOVERNANCE | 明确未启用／已启用痕迹后缺失、未知版本、旧pending | 区分未启用、合法缺失、未知／损坏／待恢复；无放行授权 |
| FRESHNESS | 输入或目标后编辑、重复预检 | 末尾重读全部观察；漂移废弃结论并给重采位置；重复不生成候选 |
| CLI | 成功、缺输入、坏版本／路径／参数、零Task | JSON及相容0／1／2；Windows真实执行，原文件不变 |
| HANDOFF | 1.1–1.5与本Story实证／未决项 | Epic2输入可追溯；仅Epic1能力完成，不称采纳或游戏通过 |

</frozen-after-approval>

## Code Map

- `_b_route_codec.py:30,83,293`：reason、Diagnostic、安全reader／双身份；不建第二枚举。
- `_b_route_records.py:327,346,1023`：validate_record、TaskJoinContext、validate_bundle；后者必须catalog，无catalog前置候选只单记录验证并明示关系未核验，禁止假造receipt/catalog。
- `_b_route_protection.py:93,131,810,853`：Task投影、累计防削弱、归档verify；compare只对当前工作区，不能伪装候选比较。
- `compile_task_triplet.py:134`：仅参考显式操作，不用normalize_task／main（补status、转ID、retire默认cancelled）。
- `plan_capabilities.py:2200`、`_planning_apply_journal.py:19`：旧marker只有run_id/journal_path，原journal无scope_id；只读定位，不调用写者。
- `dev_cli.py:56,1113`：通用run污染stdout，argparse默认错误非六字段；只对新命令局部路由，保原A行为。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/python/_b_route_preflight.py`：只读服务；严格既有候选载体与显式意图版本（非正式记录），输入绑定盘点／保护／当前目标raw、候选逻辑路径到原件及显式意图，严格形状／重复／路径／版本；完整差异和阻断，重读守护。
- [x] `scripts/python/preflight_b_route_migration.py`、`scripts/python/dev_cli.py`：公共`b-route-preflight`及直接owner入口；root／epics／protection-input／candidate／intents／run-id显式，0可用预览、1输入／迁移阻断、2命令／新输出目录准入失败；新命令参数失败同六字段，单JSON stdout，无pycache。无apply参数。
- [x] `scripts/python/tests/test_b_route_preflight.py`：矩阵行为测试及独立CLI，精确集合／身份／状态／持久结果、实际后编辑、无写入；故障注入须证明命中。
- [x] `docs/workflows/b-route-migration-preflight.md`、`AGENTS.md`、`docs/workflows/stable-public-entrypoints.md`、`docs/workflows/script-entrypoints-index.md`、`.agents/skills/plan-capabilities/SKILL.md`：中文owner说明／真实PowerShell正负样本和help／路由，保原恢复边界；代码／测试／打印英文。
- [x] `.github/workflows/story-1-6-windows.yml`：root独立test分支固定SHA、contents:read、有界专项及8组CLI／原bytes守护，仅合成输出上传，不发真实内部材料。
- [x] `docs/planning/b-route/epic1-handoff.v1.json`：root实证审阅后最小外部交接材料，引用1.1矩阵、ADR、codec／六schema、1.5输入、实际预检报告及未决；完整原始过程留logs，不造第七正式记录。

**Acceptance Criteria:**
- Given原AC1–6，when逐项核对源码／实际正负样本，then全部有真实证据，未实现／未核验／未启用明确。
- Given当前受阻材料和完整fixture，when分别运行预检，then前者保真实阻断而后者证明能力；不会把缺来源／保护认证或语义判断伪装已批准。
- Given新输入与目标bytes，when运行前后核对，then除全新logs外无变更；版本化交接由root单独审阅保存，不由预检写者发布。

## Design Notes

候选载体沿1.4 `{records:[{path,source_path}]}`，新入口另收`--intents`显式外部审阅文件；记录逻辑地址与bytes源地址分离。Task／manifest不强塞B schema。意图逐项绑定scope、实体／ID、operation、before／after locator与raw身份、来源／理由／审阅OwnedRef和未决项；reuse必须无定义变化，new不分配ID，update／retire须与实际差异双向对应，漏声明／冲突均阻断。完整三联后像若未提供沿当前原bytes；提供则三份俱全，禁止候选覆盖当前状态／历史。只验证依据locator与digest不等于语义批准。所有适用载体／意图／source_path／当前目标及来源／治理／pending／保护引用含缺失观察，报告前重读；确定性差异身份排除时间及随机collection，重复预检不产生新的语义差异。


### 回环1：候选原生后像校验（2026-11-04）

候选引用与静态结构必须走原生 owner，不能把当前 Snapshot.collect 当作候选验证。允许最小提取／扩展 `_b_route_inventory.py`、`_mvg_manifest.py`、必要时 `build_source_ledger.py` 的纯只读 I/O seam；默认调用必须保持原行为。复用 Task reference／locator、source-set 路径安全／模式解析／声明与解析成员一致、manifest Task/test/flow/handoff 静态规则，禁止在预检复制第二套规则或创建 shadow repo 写候选。候选覆盖层按完整逻辑 path→原bytes，未覆盖项才读取并观察当前原件；候选新增来源／契约／测试／Task 后像能够彼此解析，不能以逻辑地址磁盘不存在误拒。

Task 三联的 source_refs/test_refs/evidence_refs，manifest source_paths/contract_ref/implemented tests，以及 source-set 声明／模式解析结果全部纳入候选闭包。缺失必需项阻断并定位；planned 测试缺失保既有合法缺失规则。模式枚举复用原 resolver 语义（含 ** 和直接路径），安全检查先于枚举，不能静默改变通配符语义。候选原件、当前回退、缺失观察和匹配目录成员均须末尾重采；前后漂移使结论失效。不得写原树或仓库外 shadow 结构来实现后像。

新增可到达反例：候选新增缺失 Task 引用／manifest source／source-set 来源，未知 manifest test_ids，逃逸及成员不一致模式；同时有候选独有来源、候选新增 Task 供 manifest 引用、合法 planned 缺失的成功例。加入候选依赖后编辑／晚增匹配成员的失效例，断言故障注入实际命中。VG1 顶层与逐项非空 unresolved 必须经公共 CLI exit1/semantic_error/okfalse；VG2 完整当前 MatrixFixture 治理中同路径同ID同revision plan 改正文、不提供候选 catalog，必须经公共 CLI exit1/conflict。不能借其他错误遮蔽上述守卫。

## Implementation Notes

实施分工：实施者完成代码／测试／owning导航并仅运行相关定向测试；root独占Git／远端／CI workflow及实际版本化交接材料、完整回归与原生review，不发布内部原始日志。不得改冻结块或spec／Sprint状态，不另启动其他Story。

2026-11-04 Step3根审计：完整2005行candidate及298行闭包/JSON保留补丁已读。根真实反例证明旧保护闭包不能代当前依赖：新Task必需来源缺失、晚增manifest曾仍ok；现复用1.1当前owner双采，另以canonical保留history/subtask原类型。39 Linux修复全套通过58.395秒。

首轮Windows候选7f43da0bc11b37a3c9a586ff318d709232294e78/run41793345175/job126451568649自然failure，34pass/4fail/1error/0skip、404.261秒未超时；原日志SHA12529dc9a60ab12fe02d5773ce70ccb821fd76ddcee8dda7d506acfba378abfd。已复现并修复物理长路径与8.3根别名导致的CLI非JSON异常和治理扫描诊断遮蔽，保原Fixture.root及所有no-reparse／业务断言。根已读182行该补丁，最终43 Linux全套通过60.329秒，真实Win API/junction仍待第二轮实证。

回环前代码候选c0498a581ec5c5e56a0c277482505b386d8e9f78/run41795092245当时正在自然验证，只公开六个代码/测试/owner说明/workflow文件；本地spec、Sprint、真实交接和所有原始内部日志均未公开。该记录时尚未开始正式Step4；现已完成首轮review并进入回环1。该候选实际无变更预检exit1/stable=true、3440 tracked原bytes不变，T108及旧不完整保护仍阻断；当前102消费者和新增5B入口、588相同owner输入及14交接引用已核对。版本化交接仍draft，未把CI运行状态或Story状态作验收。


回环1实施已交回并冻结。root已全读3237行候选diff（原中段截断已补读），最终源码53预检/0skip 83.949s、46保护/0skip 18.984s、55codec含3Linuxskip、93records含3Linuxskip返回成功，raw与源码前后identity见root-loop1-verification.json；原生59inventory/25manifest默认回归原日志已核。根五例漏检现全部blocked且原bytes不变，VG1/VG2已加独立CLI反例；新manifest仅在原生owner标before不存在时不误报削弱，既有累计原规则保留。

新code-only候选e2124bbe23e9efedceadab406f241203bddfb989，9公开文件/7实际变化，远端逐blob已核；run41800192909/job126473782848自然执行中。仅代码/测试/owner说明/workflow，无内部spec/Sprint/实际handoff/logs发布，main未动。预算由真实新增工作量校准，见windows-budget-loop1.json；不能重复触发同候选或将旧c049成功当新证明。

当前原1.5保护输入的rules_ref inventory摘要e9e4f5…已与本轮37038c…不同，真实公共CLI正确exit1/input_stale（report b4e198605b8c023792546a00de44acf015b89045d3e57a3ecd1634f17330813b），3440tracked原bytes未变，完整当前预检尚未到达；未改旧材料/hash换绿。另行当前owner双采stable/588输入，唯一error仍T108 missing/adoptablefalse；102消费者+5 B provider及16交接OwnedRef已核。此规则陈旧列未决，正式保护/A资格仍false，新Windows/原生review及最终交接尚待。


回环1当前输入补充：保原1.5版本化材料和其input_stale原报告，另显式调用已有capture CLI，在新logs按当前规则采集（stabletrue/capture_completefalse、唯一error T108，3440tracked原bytes不变），raw归档复建通过。准备最小外部只读preview input与绑定意图，不改原文档／hash，不认证正式保护。以此实际公共CLI到达完整当前/候选闭包，exit1/stabletrue，report logs/ci/2026-11-04/b-route-preflight/epic1-loop1-current-20261104T084235Z/report.json rawf89fcb33ffd972639b86f69e37b4ac8cf369a332b3c99212ea89d18c9cb9df06；5个file_not_found诊断均同一T108，另1个capture不完整阻断，五授权全false。独立当前owner588输入raw与该实际报告观察全部相同，当前矩阵与18交接OwnedRef已核。新Windows/原生review仍pending。


回环1最终Windows实证：固定e2124bbe23e9efedceadab406f241203bddfb989/run41800192909/job126473782848自然success，原始98769bytes SHAb853c325080f6f026ec427eca8f8a83c07e452ffb9f8c4ee34438fc5231e63b6。53预检+31原生owner默认检查共84方法零skip；3强制真实短路径/junction方法通过，8独立CLI及原bytes守护通过，3442tracked不变。11环境源码blob全匹配，10Python raw一致，workflow准确CRLF转换；源套775.937秒、controls23.172秒、CLI65.375秒。六矩阵行已按实际raw方法、当前实际受阻报告和18OwnedRef技术核验对账；现进入回环1正式Step4三层，不提前宣Story完成/采纳。


Step4局部patch：三层全部返回后R1-BH1/EC1与R1-BH3、R1-VG1分三组patch；R1-BH2以原报告明确待语义审阅且五授权false反证，审阅者撤回，不制造“路径变化必然减义务”新规则。相同实施者仅改3文件，私有epics owner机械复用、归档manifest按已验原bytes读取、既有delta守住baseline→current真正退役，公共报告字段不增；无-B隔离副本保护回归。root已读252行patch；59预检/59inventory/46保护Linux全过零skip、源码原字节不漂移。新固定代码c665651d0d5742b33ac968a9ad410114b608c32f已正常推同test分支，9blob全验；run41805193575/job126490359965自然执行中，原预算不变，不复跑旧候选。

新源码单独当前capture、外部预览输入及实际公共CLI均仅新logs：实际report logs/ci/2026-11-04/b-route-preflight/epic1-patch1-current-20261104T091227Z/report.json raw9d6c0dbcf5e2c75c38675a4067206e18d66311dca4ffbdde2551f1b25c72cf78，exit1/stabletrue，仅同一T108原件5个missing诊断加capture不完整；五授权false、未启用、pendingabsent，3440tracked不变。588当前输入raw全部匹配、102消费者+5B provider及19交接OwnedRef技术核验通过。原1.5材料、旧capture/预检/CI/前像全部保留；待当前Windows后收口，不以e212旧84方法通过证明patch。


原生Step4最终闭环：固定c665651d0d5742b33ac968a9ad410114b608c32f/run41805193575/job126490359965自然success，原始101992bytes SHA7d3a46cefee8c24eb1fff6ca3be9bbb08e6e675ec8e642f2feea90ba67f21304。59预检+31原生owner默认=90pass/0skip；8CLI/原bytes、三强制短路径/junction及无-B源副本无缓存均通过，3442tracked未变。11源码blob匹配（10Py rawexact/1workflow准确CRLF），suite651.812s/controls29.157s/CLI49.250s。三patch组经源252行delta/完整相关Linux/当前精确Windows验证关闭，无延期；一个误报有明确反证，全部逐条判定保留。当前实际预检9d6c…仍T108/不完整capture阻断，19交接OwnedRef全部核验，五授权false。原证据全部保留；进入Step5只做本地收口，不自动push/PR。

## Spec Change Log

- 回环1／G1（BH1–3、EC1）：非冻结 Design Notes 补候选原生 owner 及只读覆盖／引用／模式枚举／末尾重采方案，避免损坏候选被报 ok。冻结 hash、原 baseline 和需求不变；VG1／VG2 在级联重实施时补独立守卫回归。KEEP：43项既有行为与断言、完整当前双采、canonical history/subtask 类型、严格 ID/join、immutable revision、B 归属保护、五授权 false、零 Task、planned 合法缺失、公共单 JSON／退出码、安全输出、真实8.3别名/junction检查全部保留。KEEP：既有6公开文件与3强制Windows方法及8CLI矩阵不减；原证据和实际T108阻断保留，不拿旧c049 Windows证明新源码。完整13前像与所有旧logs仅本地保存。
- 重实施起点：已在 `logs/ci/2026-11-04/b-route-story-1-6-build/review-loop-1-preservation/working-tree/` 原字节保存上一候选；9个实施／导航路径已安全恢复基线或原不存在状态。可使用该前像作正向保留种子，但必须按修订方案重新推导候选校验，不得直接恢复已知有缺陷实现后宣称完成。root保留workflow／实际handoff所有权，旧handoff仍为先前候选证据。

## Review Triage Log

| Finding | Verdict | 独立判定证据 |
|---|---|---|
| BH1 | medium | 候选三联新增必需 source_refs 未观察，五例根复现 task-missing-ref 得 ok=true、零诊断且原件不变；当前 owner 双采不能代候选后像。 |
| BH2 | medium | 候选 manifest 的缺来源及未知 test_ids 均零诊断；原生 validate_manifest 对同文档分别报 missing source 和 unknown or empty test coverage。 |
| BH3 | medium | 候选来源集合新增 ../outside/*.md 或缺失活动来源均 ok=true；原生 source-set 路径／解析／成员规则仅用于当前文档。 |
| EC1 | medium | 独立根复现 Task／manifest／source-set 候选断链均未观察；该层 guard_snippet 只是建议，未作为现有守卫证据。 |
| VG1 | medium | 验证层预核：两种非空 unresolved 原 CLI exit1/semantic_error，禁用守卫后 exit0/oktrue，43项旧套仍通过；缺失对应回归。 |
| VG2 | medium | 验证层预核：完整当前治理内同路径同ID同revision plan 改正文，原 CLI exit1/conflict，禁用守卫后 exit0，43项旧套仍通过；缺失独立回归。 |


### 回环1独立判定（先逐项、后分组）

| Finding | Verdict | 证据／反证 |
|---|---|---|
| R1-BH1 | medium | 根隔离复现候选epics改规范来源为缺失文件仍ok；真实后编辑钩子命中仍stable/ok，依赖未观察。_candidate_inventory只调用tasks/source_set/manifests，canonical_inputs固定空。 |
| R1-BH2 | false | 原始报告已有source_backed_review_required=true、verified=false、apply_authorized=false；obligation update含前后身份/来源与review locator，语义/审阅false、五授权false。未证明path/selector改变本身是减义务；合同允许待语义审阅的更新。审阅者只读复核后亦撤回原确定性说法。 |
| R1-BH3 | medium | 根复现当前manifest合法追加planned测试、native当前无error且历史归档完整性通过，仍在manifest_refs对当前bytes验旧digest处提前失败，protection_to_current为空。历史OwnedRef命名空间用错；另证明当前真正退役旧testID的native合法文档仍需保累计阻断。 |
| R1-EC1 | medium | 根分别复现缺失候选规范来源和实际后编辑：均未观察、oktrue；公共CLI原证据exit0/empty stderr。建议guard只是建议，非现代码。 |
| R1-VG1 | medium | 验证层预核：仅移除dev_cli最早禁止bytecode赋值，保其他守卫，53项仍过；无-B实际命令原副本0pyc/变异12pyc，均exit0。现测试强制-B且只守合成根，缺实际脚本目录的无-B行为回归。 |

## Verification

`python -B -m unittest discover -s scripts/python/tests -p test_b_route_preflight.py -v`，适用既有codec／records／protection回归；Linux定向套各180秒。真实Windows新套1100秒、原生owner默认31项180秒、独立CLI矩阵240秒、内部1500秒／job30分钟，上游未变源码复用其已有Windows实证；专项执行成功、缺输入、未知版本、路径逃逸、状态覆盖、无依据退役、旧pending、零Task八组CLI；关键平台分支不以skip算通过。root另跑实际仓库预检，保存真实受阻结论／原身份和Epic2交接。全部原日志留logs，不重复同候选CI。

回环前Step3实证（不证明新源码）：候选c0498a581ec5c5e56a0c277482505b386d8e9f78/run41795092245/job126457189931自然success，43 Windows方法零skip，三个强制平台方法通过、8独立CLI预期退出码及原bytes守护通过，3442 tracked未变；suite566.453秒、CLI60.375秒，raw73309bytes SHA5ff916b2b3960fbf6197598f55d4957b01dbdc5aff5803a61fc12b5c4619299d。8源码Git blob一致，7Python raw一致、workflow raw准确对应CRLF转换。最终实际预检按此源码重新取证，仍exit1/stabletrue/T108阻断，3440 tracked不变；新消费者矩阵和15交接OwnedRef已核，技术材料审阅完成，独立原生review尚待。本结论不授采纳／冻结A／运行资格。
