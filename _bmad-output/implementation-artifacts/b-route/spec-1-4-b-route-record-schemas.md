---
title: 'Story 1.4 六类公共记录只读校验'
type: 'feature'
created: '2026-11-03'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: f4964fdfa0167f9e66b08319aeaa655700e378ea
approval_state: delegated-routine-implementation
story_key: '1-4-按唯一公共schema校验六类规划记录'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/SPRINT-SCOPE.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-newrouge-b-route-2026-11-03/planning-records.md'
  - '{project-root}/docs/workflows/b-route-record-contract.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

以唯一离线公共 schema 校验 policy／plan／binding／origins／commit／catalog 及候选引用关系，落实 B epics 1.4 AC1–5。具体字段和可执行关系采用 context 中的公共格式合同；低层格式由本轮 schema owner 冻结，不冒充原需求逐字定义。

## Boundaries & Constraints

按本 Story 自身的确定性 Harness 维护范围纳管，不新增游戏 Task 或调用 Chapter6。原1.3真实 Windows54通过；保三联、游戏、旧proof、canonical算法和七字段TypedRef。六类adapter补在原registry；verification-scope仍无adapter。新schema封闭全部嵌套字段，严格integer、离线拒绝未知资源，不引入第二身份／诊断owner。通用安全路径兼容根内合法别名；六类受管存储路径须精确。

只证明声明形状、来源定位／bytes及已给定引用一致性。单记录claim=record_structure_only；bundle=candidate_structure_only；显式区分schema、references与baseline单调性。无baseline不声称历史已证。planned可缺目标，existing须定位；不证明循环终止、代码类型／runtime／准入／发布。仅候选，不生成实际六类业务记录，不实现InputSet／journal／Task投影计算／切B／退A。

用户已授权持续全部Story、常规判断及必要独立分支提交／推送和真实Windows验证；root负责这些操作，实施agent不执行Git／远端操作或改spec状态。本Story无用户可感知意图缺口，无生产数据迁移；API足迹需dispatch。原生spec常规批准选择由明确委托执行，非另一次人工投票。

## I/O & Edge-Case Matrix

| 场景 | 输入 | 期望 |
|---|---|---|
| SCHEMA | 六类合法；未知版本／字段／枚举、缺字段、重复键、非有限数、bool／float／str修订 | 合法通过，其余公共诊断含定位；无隐式转换 |
| IDENTITY | plan2与binding7；错误实体／修订／路径／摘要 | 独立精确身份；错误拒绝；旧identity-only结果不升级 |
| BOOTSTRAP | 零Task、空origins／冻结A、无binding的3B | 合法；不要求witness或假Task |
| DECLARATIONS | Flow循环／跨plan共享、非Flow依据；4／5planned；existing | 合法共享与循环不误拒；缺owner／责任／依据／现有目标拒绝 |
| REFERENCES | candidate原bytes、同路径disk；坏摘要、dict伪raw、缺必需文件、owner定位失败 | candidate优先且不fallback凑绿；无原bytes不得核raw；共同失败 |
| JOINS | 多plan Task反向映射、历史记录；缺行、重复、错误ID类型 | 当前bindings双向全集相等；历史不污染当前；严格master／view join |
| RECEIPT | catalog引receipt；receipt含自身／最终catalog输出hash | 前者精确验证；后者拒绝；无状态／PASS新权威 |
| READONLY | 单记录／bundle CLI正负、Windows真实reader及junction | 输出同公共结果／退出码；输入树不变；仅logs有证据 |

</frozen-after-approval>

## Code Map

- `_b_route_codec.py`：复用strict decode、raw/canonical、安全reader及Diagnostic；仅扩原adapter／ReasonCode／Stage，旧调用无jsonschema依赖。
- `plan_mvg.py:1598–1657`原七字段routing；`_mvg_requirement_accounting.py:172,272,328`证据键／coverage完整投影／native fragment，勿套旧Task覆盖门禁到3B。
- `build_source_ledger.py:514–534` native字符串revision与manifest摘要；`_chapter5_contract_bindings.py:9`只借定位规则，rawbytes仍独立安全核验，不运行生成器。
- 公共格式合同含独立源码复核后冻结的owner闭包、严格join、schema字段和接口；不是用实现报告自证。

## Tasks & Acceptance

**Execution:**
- [x] `docs/planning/b-route/schemas/*.schema.json`：六类＋common唯一Draft202012定义，所有扩展封闭。
- [x] `scripts/python/_b_route_records.py`、`_b_route_codec.py`：离线validator、单记录／bundle、精确引用／闭包／反向join及baseline；集中诊断。
- [x] `scripts/python/_chapter5_contract_bindings.py`：同resolver增加keyword-only预读bytes seam，保旧默认解析／native text hash；新adapter用安全candidate cache，不复制解析器。
- [x] `scripts/python/validate_b_route_records.py`：record／bundle只读CLI，候选载体固定、禁pycache、结构化失败。
- [x] `scripts/python/requirements-b-route.txt`：冻结已有jsonschema4.26.0／referencing0.37.0；缺库fail closed，不升级工具链。
- [x] `scripts/python/tests/test_b_route_records.py`、`test_b_route_codec.py`：全部矩阵正负例与1.3回归；原已交付功能不削弱，扩adapter只更新原None假设。
- [x] `docs/workflows/b-route-record-contract.md`、`b-route-record-validation.md`、`b-route-reference-verification.md`：公共字段／owner边界和Windows API／CLI说明；同步现行六adapter与identity-only边界，不复制第二字段映射。
- [x] `.github/workflows/story-1-4-windows.yml`：仅独立test/b-route-story-1-4-windows-2026-11-03 push，contents:read、固定事件SHA；新旧单测及CLI／真实Windows必需项，限定本轮logs上传，原始失败保留。

**Acceptance Criteria:**
- Given单记录或完整候选闭包，when公共API／CLI校验，then原Story AC1–5及全部矩阵成立，六类唯一schema及原registry／共同诊断可查。
- Given未发布候选及缺baseline，when返回成功，then不宣称已采纳／可消费／Task readiness／runtime或历史单调性；Taskmaster状态权威不变。
- Given实际验证，when审核证据，then逐矩阵存在已运行通过的测试，Linux与真实Windows分别记录，未执行／skip不作通过，正式输入无写入。

## Implementation Notes

2026-11-03 Step3开始前后设计复核补正：receipt曾跨scope提交后，部分scope可更新而其他scope保旧head；公共合同第8节将当前head closure与历史receipt冻结mapping自洽分开，避免把无关旧目标套当前owner而误拒。保持冻结意图、候选只读范围与原AC不变，无新增产品／权限决定。独立复核来源story14_design_review/closure_check；保留原冻结前像和本次修订证据。

2026-11-03：历史receipt可变policy/origins目标只保冻结结构关系，不以旧after覆盖或约束当前新operation；当前所选与不可变目标仍实际核raw，结果显式列历史未重验项。该实现细化已纳入公共合同，保持原Frozen Intent。

2026-11-03 Step3根代理反例核验：非空Task映射能以空view_refs及空业务view回避strict join，part_kinds能指未声明part；均返回ok/references_validated。公共合同明确非空映射至少一个真实view、part引用须已声明适用责任；同kind责任唯一为本轮schema owner格式细化，仍允许纯集成owner空parts。保原矩阵、零Task及冻结意图；已将最小修复/回归交原实施agent。原始反例结果保存root-join-reference-probes.json，未借测试数量替代事实。

2026-11-03：root实测单记录binding含C:/outside.json TypedRef仍schema通过；已要求所有声明路径在单记录阶段复用1.3词法，不读target且references仍false。共享格式一致性修复；冻结意图未变，原反例root-record-reference-path-probe.json留存。

2026-11-03：首轮真实Windows候选4b4beb712d7dd023877afac83715c1b9643de86f，run41690030579/job126105873137实际72 records＋54 codec无skip、12CLI及9必需Windows reader/junction方法通过，18Gitblob一致；原job日志SHA256=88126ec8736edece40fcdf54f41d682ed5bf35f222417c0392bef6c029da7638。root后续核AC2发现非法三联ID诊断缺源context/pointer，原实施agent保持判断/ReasonCode/stage补定位并新增2方法6子例；Linux74通过无skip。该补丁新候选45192431bf55a9b254153e4e29fd6078993fed8a已正常快进独立test branch，run41690800797待真实结果；旧72通过不替代新候选。

2026-11-03：第二轮Windows候选45192431bf55a9b254153e4e29fd6078993fed8a run41690800797/job126108539570真实失败。records74全部通过，codec54中53通过、test_same_size_overwrite_during_final_path_resolution_is_rejected返回ok而失败；12CLI和9必需Windows方法通过，18Gitblob均匹配。codec及其原测试与首轮完全同blob；原log SHA256=26773344b9c3b1a149ea0b57e4ed74e682bd052da4cbc7526d375719fed31eac。尚无该次写入／stat样本，不能归因为时间量化／缓存或无害flaky；正在保原断言做限定Windows原test诊断。Step3保持in-progress，不进入Step4，不以重跑绿色替代失败消歧。

2026-11-03：为消歧第二轮真实失败，仅专用workflow诊断候选470089d9e431a6fae3d9cb634b86816c020fd8c8已正常快进，run41692633924。最多16次原失败test，子进程60秒，return-frame观测不改reader／原测试／时间／返回tuple；日志只在单项结束后序列化，保原fullsuite失败，全部通过也只记未复现。当前根因未定，所有草稿／原失败证据保留。实际安装Core/BMM6.12.4，planning_artifacts与implementation_artifacts显式b-route；本Story renderer已调用一次，不能伪造安装/配置或把缓存当源码。为应对云重置保存明确in-progress的独立恢复检查点，不等于Story验收或Task／runtime状态。

2026-11-03：有界诊断run41692633924的16次原方法均未复现，不能清除第二轮失败。root另以真实同长度字节改写＋还原mtime、固定相同metadata样本构造确定性反例，旧reader返回ok；因此在原stat／路径／birthtime检查外增加同一无缓冲句柄二读字节比较，新增反例先红后绿。候选e314f46477a3060ae8bde0d549549640e1e09542在run41694371920/job126120925011实跑records74通过、codec55中54通过1失败、0skip；新增反例和原late-overwrite已通过。失败为旧early-overwrite测试的ctime必须不同前提，两个真实fd ctime均1793730651625173900，前置FILE_CHANGED业务断言已经通过。12CLI及9必需Windows项通过，原rawlog SHA256=8a11109ad13ed291bde9c80aa4953eb040b6abf4982af04567146797da81083c。此事实不证明第二轮的具体机制；正在按实际平台合同修正不成立的测试前提并保留拒绝变化的功能要求。Step3继续in-progress，不用单项通过清除整体失败。

2026-11-03 Step3最终验证：原early-overwrite不可靠ctime唯一性前提改为更强的单次实际字节改写、等长度／还原mtime与三次FD采样断言，FILE_CHANGED及其他metadata比较负例全保留；未用skip、sleep或强制新时间值。Linux当前源码records74／74、codec52通过＋3真实Windows专项skip；真实Windows候选4c85268c045d922e7946c4f094668d94ce2871dc，run41695807890/job126125894999，在Windows2025Server／Python3.12.10实跑74＋55全通过、0skip，12CLI正负与9必需Windows方法通过，无输入变化／pycache。19个runner源码Gitblob与当前本地匹配，原始checkout raw身份另记不混同。全部8矩阵行有实际通过方法；原job log SHA256=6263d228b8d504c400f3038e9d01986937aeff7abb20ba0066dd518c13017a18。所有旧失败证据保留，不宣称已确定第二轮精确机制或任意并发隔离。根已审原完整diff所有段及此后逐项delta，判断依据为源码与原始测试输出。

2026-11-03 路径修复技术裁定：不能将实施计划的raw locator“每个词法仓外entry都禁止”升级成新口径。根真实POSIX原codec正对照证明：公共根内L可经仓外既存alias链最终指回根内既存目标并被原owner允许；公共输入direct-external/../仍先在外部segment拒绝。补丁按公共输入各segment的实际终点保持containment，低层目标链完整解析并保可证明回仓兼容。对Windows扩展namespace，全程保raw target表示，只对samefile已证明的完整既存base建立比较拼写；不重解释未经证明的missing tail。未知reparse、权限、循环及预算耗尽拒绝。前述为原冻结“合法根内引用”要求的实现澄清，非新增安全或产品政策；真实Windows回归仍待执行。

## Spec Change Log

## Review Triage Log

| Finding | Verdict | 原始证据与裁定 | 分组／路由 |
|---|---|---|---|
| BH-1 projection target 可绕过不可变 B 原字节 | medium | root 以缺失 plans/absent/1.json、projection mode＋任意digest重现 ok/references_validated；receipt仅 immutable 分支读取目标。架构 planning-records.md:36 明确不可变plan/binding/receipt用immutable_bytes，Taskmaster／业务视图才用定义投影。现有投影字段延期不授权 B target 绕过字节检查；原反例 root-review-target-mode-probe.json。 | G1／patch：将投影目标限于已有三联实际目标并保留合法延期投影的false claim；不新增模式／投影计算。 |
| BH-2 Windows 未落盘候选大小写冲突 | medium | lookup将resolved路径转str，constructor用该str区分候选；缺失尾部保留输入大小写，普通Windows同目标大小写等价，两个候选可逃过既有冲突guard。已核CPython3.12.10 ntpath及Python／微软原文，属于静态确定的比较遗漏；尚未原生Windows运行此具体反例，不能冒充已复现，修复后需真实回归。合同73要求拒绝同实际目标的冲突别名且不改payload/hash。 | G2／patch：仅修内部目标比较，保实体ID／受管路径原拼写、candidate优先和链接语义，增加原生Windows必跑反例。 |
| EC-1 Windows candidate path case equality | medium | 与BH-2同一lookup str键缺陷；该层亦明确Windows未实跑。根按上述实际代码与主源确认默认Windows可达后果；不会据Linux双文件成功声称原生复现。 | G2／patch，与BH-2同根因，单独保留此行。 |
| VG-1 bundle缓存后的漂移无回归保护 | medium | 依原生规则信任本层已核测试／全仓搜索及变异证据：stable改no-op仍74通过；最终复查前改ledger，现实现file_changed、去掉复查则ok。CLI调用者的观测稳定性可在无测试报警下失守。 | G3／patch：加真实缓存后改写输入、返回前拒绝且references_validated=false的确定性回归，不改产品行为。 |
| VG-2 CLI完整三联参数接线缺成功验证 | medium | 依原生规则信任本层完整测试搜索及变异证据：把三参数都误读master仍现CLI测试通过，而合法非空API fixture实际CLI原版成功、变异invalid_type。用户公开CLI可在错误接线后拒绝合法绑定。 | G4／patch：完整三联subprocess成功＋错误业务映射失败，保无写入检查。 |
| ROOT-P1 首轮补丁仍可经Task别名逃入B namespace | medium | root真实根内dangling Task文件symlink指向缺失plans/ghost/1.json，projection任意digest仍ok/references_validated；原反例root-post-patch-projection-alias-probe.json。只按原Task路径whitelist、原target拼写及已加载records判断不能覆盖未加载的实际B目标。 | G1／patch补正：按实际目标及实际受管namespace身份封堵，保合法非B Task别名与原延期投影边界。 |
| ROOT-P2 Windows链接夹具根含8.3别名 | medium | run41700073106/job126140714358在file-alias方法4子例于业务调用前的resolve相等断言失败：RUNNER~1与runneradmin前缀不同；84项中该1方法失败、其余83及codec55、12CLI／12mandatory真实通过、0skip。原rawlog SHA256=19b59addeefd3c7e11cd33854915ffc37a2eb14c545b79cf284a7d04c1aad7c0。 | G5／patch：仅将该存在的temp根strict resolve后再构造链接，保全部原断言，不改产品路径策略；新候选8cc2ad0实跑前不可作通过。 |
| ROOT-P3 缺失目标的partial resolve不能作实际身份 | high | 精确CPython3.12.10 raw ntpath.py:690–692展开readlink后立即返回，访问错误也可被non-strict吞掉。真实Win41700727700仅观察到fixture前提失败，尚无原生API越权实跑；根另锁定5032a2eb旧service blob，真实POSIX链接＋仅注入该已观察的partial-return形状，B目标与外部nested-prefix两种bundle均从拒绝变ok/references_validated，portable控制原件partial-resolve-control.py/json明示限制。故实际地址/containment guard存在可达控制流缺陷，不按报告自证。 | G5／patch（与ROOT-P2共享错误的单次resolve完整性前提）：同一私有missing-target walker逐组件lstat/readlink/现存prefix严格证明、保原..顺序，权限/循环/未知reparse/预算耗尽拒绝；不扩公共API、不改codec既存reader/Python/权限。新Windowss实跑前不作修复完成。 |
| ROOT-DOC owning doc仍声称只有plan adapter | low | 旧公开页reference-verification.md:35–37描述与同registry已落实六adapter实际代码矛盾；content/reference用户会误判policy等不支持身份。保留raw/eol前像后仅直接改两段，明示1.3沿革、当前六adapter、verification-scope仍None、identity-only不升schema/runtime/采纳，并链接现行owner合同。根已读精确两行段落diff，其他原bytes保留。 | G6／patch：直接事实更正已读；无代码／公共surface变化，不为doc-only新增测试。 |

全部三层已返回后逐条裁定，之后才合并同根因；共5原始layer finding；根复核另有ROOT-P1、ROOT-P2、ROOT-P3及ROOT-DOC，按原4根因及新增non-strict解析完整性根因（含夹具及service guard）及现行文档事实更正分别跟踪，无数量门槛。上述均有既定架构／公共合同可直接解决，最小更正不增加公共API或新状态权威，不改frozen intent，不需intent_gap／bad_spec重派生。投影模式和路径比较的现有guard缺漏属于已展示输入的局部补正；两项验证缺口仅加可执行回归。此轮无defer；若原生Windows揭示不同实际行为，将按新证据重判，不能拿静态判断伪称执行通过。


### 最终修复核验（2026-11-03）

原三层所有finding及根复核追加项逐项保留原verdict；以下为修复后的实证闭合，不改写旧失败或用状态自证。无延期、无未验证保留项。

| 组 | finding | 修复／实际核验 | 结果 |
|---|---|---|---|
| G1 | BH-1、ROOT-P1 | 投影限现有三联实际身份，B singleton／namespace不能借根内别名跳过immutable bytes；file及directory别名、缺失／错bytes负例均实际执行。 | 已闭合 |
| G2 | BH-2、EC-1 | Native Path比较键保实体／payload原大小写；各自合法p/P候选冲突、UPPER-PLAN＋junction正例、case alias候选优先均Windows实跑。 | 已闭合 |
| G3 | VG-1 | 缓存ledger后、最终stable前真实改写，返回file_changed／references_validated=false；原no-op变异控制已检出。 | 已闭合 |
| G4 | VG-2 | 完整三联CLI subprocess正例与错误business映射反例，结果／退出码及无写入核验实际通过。 | 已闭合 |
| G5 | ROOT-P2、ROOT-P3 | readlink＋strict已存parent samefile证明缺失目标；私有逐component walker不依赖non-strict partial resolve；真实Win外部终点拒绝／原codec回仓兼容通过，权限／未知reparse／extended不支持后缀／预算为明确控制注入；循环与链接复用正负例通过。 | 已闭合 |
| G6 | ROOT-DOC | 旧owning doc仅两段事实改为六adapter及verification-scope仍None，并保identity-only限制；其余原bytes和LF逐字节复核。 | 已闭合 |

真实Windows候选221d22a08c18b45a19867e5b817c97ce4b039a53，run41705225421/job126158630262自然成功：93records＋55codec全部通过，0skip；12CLI／12必需Windows方法通过。runner19源码Gitblob与恢复后原工作区一致，额外owning-doc blob为d68196f6d83bd7899cacc42b2942a8b85a1edff2。93方法进程34.078秒、55方法进程2.579秒，均在原180秒预算内；未放宽预算或断言。原始log SHA256=4f0359f7e0baaf34f67752b671b03c58956faa18272e5c3ac80a5af406933ce6。Linux原完整回归93=90pass＋3真实Windowsskip、55=52pass＋3真实Windowsskip分别保留，模拟不代原生。

执行环境恢复后21项现场与断开前完整raw清单一致，无活动本轮单测，故未重复运行已验证代码；3412个其余tracked原文件不变，Task三联／游戏／旧proof／默认路径未改。已按实际安装的BMAD Core/BMM6.12.4原生Step5收口；spec done／Sprint review仅为Story视图，不表示B启用、A退出、正式基准采纳或Task/runtime完成。T108原件缺失与旧inventory adoptable=false保持。

## Verification

`python -B -m unittest discover -s scripts/python/tests -p test_b_route_records.py -v`，并跑`test_b_route_codec.py`回归；每套180秒。独立CLI正负／raw身份／无写入及candidate影子反例。Windows job预算10分钟，库安装与单测实际计时；必需Windows项不能skip。root逐段审diff、逐矩阵读原始输出、核Task／旧proof／默认入口raw身份及远端tested blob。


Step3原始证据目录：`../../../logs/ci/2026-11-03/b-route-story-1-4-build-172705Z/`，最终Windows原始输出、逐方法／逐blob／逐矩阵核验、Linux全套及原失败各自留档，状态不是验收证据。

本地最终原件：[Windows原始日志](../../../logs/ci/2026-11-03/b-route-story-1-4-build-172705Z/windows-run-41705225421/job-126158630262.recovered-k2qfv6fl.log)；[逐方法／逐blob核验JSON](../../../logs/ci/2026-11-03/b-route-story-1-4-build-172705Z/windows-run-41705225421/job-126158630262.recovered-k2qfv6fl.verified.json)。日志仅留本地，不重试曾被拒的公开披露。
