---
title: 'Story 1.3 公共只读引用codec'
type: 'feature'
created: '2026-11-03'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: bfe6e3731035ab48e61b55291dd94919f2830ee2
approval_state: delegated-routine-implementation
story_key: '1-3-统一核验文件引用与规范化内容身份'
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/b-route/SPRINT-SCOPE.md'
  - '{project-root}/_bmad-output/planning-artifacts/architecture/architecture-newrouge-b-route-2026-11-03/planning-records.md'
  - '{project-root}/logs/ci/2026-11-03/b-route-story-1-3-build-163111Z/research.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

统一JSON、类型化文件引用、raw／canonical身份及公共诊断，交付一处纯模块和可独立调用的只读入口，满足B epics 1.3 AC1–5。

## Boundaries & Constraints

采用现行Harness维护路由，不继承1.1/1.2例外或声称Task准入；master无可复用未完成Task。保留七个既有dirty、三联、游戏、历史proof及原canonical_sha。只读正式数据；英文代码／测试／输出、中文说明，日志只进新logs。按新增明确授权，可在独立测试／实施分支提交并推送经范围核对的本Story代码及已批准成果检查点；不得改main、force、PR或merge；不交付1.4完整schema、journal、InputSet、默认B或A退出。

已知schema用唯一受管registry，当前仅plan身份有充分类型合同；其他缺adapter返回identity_unprovable，绝不猜ID／revision或宣称验证通过。后续由1.4扩展同一owner。用户已授权常规技术判断及继续实施；真实Windows证据未获得前不得宣称平台验收完成。

## I/O & Edge-Case Matrix

| 场景 | 输入 | 期望 |
|---|---|---|
| STRICT | 重复键、非法UTF8、NaN/Infinity/1e999、非法基础类型 | 拒绝；嵌套扩展同名schema键保留 |
| TYPES | bool/int、Task字符串ID、plan ID/修订错误 | 类型严格，无强转 |
| IDENTITY | 键序/排版改变；数组/类型/Unicode/字符串空白改变 | 前者canonical同，后者不同；raw另存 |
| REF | 丢身份、坏digest/模式/codec版本、未知schema | 无默认，公共诊断 |
| TARGET | 合法plan；未知实体；已知无adapter | 精确核对；拒绝；无法证明不通过 |
| PATH | 绝对/驱动器/UNC/URL/越界/根外链接；合法根内链接 | 前者拒绝或无法证明，后者允许 |
| RESULT | 成功/失败/不适用；CLI正负例 | 六诊断字段齐全，不适用null，非零失败，零正式写入 |
| PLATFORM | Windows词法及实际I/O/junction | 分别取证；Linux模拟不算Windows通过 |

</frozen-after-approval>

## Code Map

- `_planning_skill_common.py:58`复用canonical算法，不改旧调用。
- `_mvg_structured_context.py:11`借严格解析；`_mvg_manifest.py:21`借containment，勿额外禁根内链接。
- `planning-records.md:18–30,77`公共身份/诊断；细节及纳管证据见context research。

## Tasks & Acceptance

**Execution:**
- [x] `scripts/python/_b_route_codec.py`：唯一codec／registry／TypedReference／诊断，公共纯API。
- [x] `scripts/python/verify_b_route_reference.py`：只读content/reference CLI，stdout JSON，禁pycache。
- [x] `scripts/python/tests/test_b_route_codec.py`：全部矩阵正负例、旧canonical黄金值与无写入。
- [x] `docs/workflows/b-route-reference-verification.md`：中文API／Windows命令／真实能力边界。

- [x] `.github/workflows/story-1-3-windows.yml`：按新增明确授权交付独立Windows专项CI，固定事件SHA、逐CLI原始输出、必需Windows项不得skip；已验证版本纳入正式评审。

**Acceptance Criteria:**
- Given文件或内存JSON，when公共核验，then严格解码/类型、raw及带版本canonical、引用/实体核对与诊断符合矩阵和原AC1–4。
- Given调用方，when消费结果，then同一ReasonCode/Diagnostic六字段；区分content/reference，schema_validated=false，不能授予采纳/Task/提交成功。
- Given定向测试，when验证，then覆盖全部矩阵，证明不写正式数据、无Godot/模型/数据库，Windows未测项明确保留。

## Implementation Notes

2026-11-03：已新增四份交付文件；实际补丁已逐段核读，公共codec保原canonical算法、单一registry、严格类型及诊断，CLI只读。最终Linux43项=40通过/3真实Windows专项skip，8组独立CLI正负例匹配。首轮Unicode路径诊断码不一致已在代码统一为invalid_utf8，原断言与180秒预算保留。旧文件/历史proof未改变。证据见`logs/ci/2026-11-03/b-route-story-1-3-implementation-163701Z/`。

测试任务仍未勾选：PLATFORM矩阵三项真实Windows测试未运行，不能用Linux或旧Story报告补齐。按原生Step3 Matrix Test Audit，未运行的覆盖项算缺失；当前停留Step3 in-progress，未进入正式Step4/5、未宣布Story完成。只读实施内复核不替代原生Step4。新CI仅为logs下草案，未改实际workflow或运行。需要明确批准本Story专用五文件测试分支提交/推送及单次Windows CI后才能补证；其他范围保持原约束。

## Spec Change Log

- 2026-11-03：用户新明确批准四实现文件＋专用workflow的独立测试分支提交／推送及真实Windows验证、必要修复，并要求按依赖持续完成全部Story、主动管理云环境重置风险。原Git限制按本次明确重新授权更新，仅受审范围的独立分支检查点；main／force／覆盖他人／PR／merge仍禁止。原字节前像与授权原文保存于`logs/ci/2026-11-03/b-route-story-1-3-windows-165605Z/`，不伪造额外人工批准。

## Review Triage Log

2026-11-03 原生Step4：三层上下文隔离审阅已全部返回后统一分类；无发现数量下限。edge返回[]。逐项裁定如下，均为本Story最小patch，无意图／spec回补、无延期。

| ID | verdict | route | 独立证据与影响 |
|---|---|---|---|
| B1 | medium | patch | CLI在引用文件读取异常时outer catch未传已知args.reference；损坏JSON由verify_reference(bytes)返回path=null亦未补定位。根代理实际执行../reference.json及AGENTS.md两反例，均非零且path=null，调用者无法从公共结果定位输入；见native-blind-finding-verification.json。保留已有target path，仅在无法取得target时补引用文件path。 |
| V1 | medium | patch | verification-gap层已验证：ContentIdentity.to_dict为公共序列化边界，而CLI测试只断言模式/诊断/退出码；raw/canonical交换的回归不会失败，会使消费者保存错误内容身份。为content、raw/canonical reference成功输出直接断言target原字节digest、canonical digest及codec版本，保持两digest fixture不同。 |

## Verification

`python -B -m unittest discover -s scripts/python/tests -p test_b_route_codec.py -v`及CLI正负fixture；每次预算180秒，原始输出写本轮logs。逐行矩阵审计、diff/白名单/既有七文件SHA核对。真实Windows尚无执行环境；需要外部授权时先交可审补丁和最小运行方案，保持未完成，不以Linux代证。

## 真实 Windows 补证与 Step3 结论

2026-11-03：经新增明确授权，独立测试分支发布五文件；父基线4aa86与实施bfe的运行代码/测试相同，仅3份BMAD元数据和旧1.1专用CI不同。初始77e1067b run41679804228失败，保留原始记录；workflow-only诊断5639a837 run41680440578确认路径stat/fd fstat的ctime字段语义不同。最小修复保同来源完整ctime、Windows跨来源birthtime身份和末次fd观察；原43方法AST不改，新增10项。新注入helper按resolved身份匹配且断言2次path/3次fd实际命中。

最终真实Windows源码e00f6cd911a9b28a4c8b584651095bbf4af7b500，run41681799055/job126077091869：53项全部通过/无skip；8组CLI原始正负例/退出码匹配；12次稳定重写trace全部ok。代码、测试、说明及workflow Git blob与本地候选逐个匹配。根代理审计原始输出，未用绿色状态或旧报告代证，PLATFORM矩阵已满足。证据位于`logs/ci/2026-11-03/b-route-story-1-3-windows-165605Z/run-41681799055/`。先前“待授权／平台未运行／测试未勾选”为当时历史状态，已由本次明确授权和真实补证取代；当前将进入原生Step4，尚未宣布Story完成。

2026-11-03（Step4 patch）：B1/V1最小修复已完成，CLI保留输入reference文件定位并优先保留已解析target；成功输出直接断言raw/canonical/codec。根代理完整Linux54项=51通过/3Windows skip；隔离复制只交换to_dict两digest的mutation按预期失败，证明新断言能拦回归，正式源码未变。最新待测候选27b8a521c3fbce9339b3b91262c87795e45c42bb已正常快进独立测试分支；其真实Windows复测尚待结果。先前e00f6cd9的53通过是对应旧候选的真实历史，不替代新候选验收。

## 原生 Build Step5 收尾

2026-11-03：B1/V1 patch后的最终真实Windows候选27b8a521c3fbce9339b3b91262c87795e45c42bb，run41683158284/job126081834004，54项全部通过、无skip；8CLI正负及12稳定重写全部匹配。根代理核对原始job输出与本地五文件Git blob，原日志SHA256=cb22cfaae1233c82bcb840d78d86825e34f430bbaa78dc00e8c7aad0e5290d89。Linux完整54项51通过/3Win skip和Windows54通过分别陈述；隔离序列化交换mutation按预期失败。三层正式评审已完成，两项medium patch修复验证，无延期，无未解决intent/spec缺口。

按原生Step5置spec done、B范围Sprint本Story review；不改变Task/运行/Epic或默认B状态。用户新增明确授权独立分支提交/推送及按依赖继续全部Story，并要求管理云重置风险；因此保存已批准1.2与1.3为分离Git检查点、普通推送独立实施分支，禁止main/force/PR/merge。原bfe基线已另存backup/b-route-source-bfe6e373-2026-11-03。原生BMAD Core/BMM 6.12.4真实安装，planning_artifacts与implementation_artifacts均显式指向b-route；云恢复不得伪造安装/cache，按官方恢复后继续当前范围。原始失败、诊断、修复和审阅证据全部保留在logs/ci/2026-11-03/b-route-story-1-3-windows-165605Z/及同日关联实施目录。
