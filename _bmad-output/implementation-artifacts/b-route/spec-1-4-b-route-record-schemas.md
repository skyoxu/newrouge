---
title: 'Story 1.4 六类公共记录只读校验'
type: 'feature'
created: '2026-11-03'
status: 'in-progress'
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
- [ ] `docs/planning/b-route/schemas/*.schema.json`：六类＋common唯一Draft202012定义，所有扩展封闭。
- [ ] `scripts/python/_b_route_records.py`、`_b_route_codec.py`：离线validator、单记录／bundle、精确引用／闭包／反向join及baseline；集中诊断。
- [ ] `scripts/python/_chapter5_contract_bindings.py`：同resolver增加keyword-only预读bytes seam，保旧默认解析／native text hash；新adapter用安全candidate cache，不复制解析器。
- [ ] `scripts/python/validate_b_route_records.py`：record／bundle只读CLI，候选载体固定、禁pycache、结构化失败。
- [ ] `scripts/python/requirements-b-route.txt`：冻结已有jsonschema4.26.0／referencing0.37.0；缺库fail closed，不升级工具链。
- [ ] `scripts/python/tests/test_b_route_records.py`、`test_b_route_codec.py`：全部矩阵正负例与1.3回归；原已交付功能不削弱，扩adapter只更新原None假设。
- [ ] `docs/workflows/b-route-record-contract.md`、`b-route-record-validation.md`：公共字段／owner边界和Windows API／CLI说明。
- [ ] `.github/workflows/story-1-4-windows.yml`：仅独立test/b-route-story-1-4-windows-2026-11-03 push，contents:read、固定事件SHA；新旧单测及CLI／真实Windows必需项，限定本轮logs上传，原始失败保留。

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

## Spec Change Log

## Review Triage Log

## Verification

`python -B -m unittest discover -s scripts/python/tests -p test_b_route_records.py -v`，并跑`test_b_route_codec.py`回归；每套180秒。独立CLI正负／raw身份／无写入及candidate影子反例。Windows job预算10分钟，库安装与单测实际计时；必需Windows项不能skip。root逐段审diff、逐矩阵读原始输出、核Task／旧proof／默认入口raw身份及远端tested blob。
