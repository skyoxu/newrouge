---
title: 'KCP Impact Analyzer CLI Production Harness'
type: 'feature'
created: '2026-09-05'
status: 'in-review'
review_loop_iteration: 0
baseline_commit: '9a6afe1e88d6f1a6a85e2c1bb9045ba4678b8b82'
context:
  - '_bmad-output/implementation-artifacts/spec-kcp-impact-analyzer-production-readiness.md'
  - '_bmad-output/implementation-artifacts/spec-kcp-impact-analysis-index-production-readiness.md'
  - 'scripts/python/analyze_impact.py'
  - 'scripts/python/run_gate_bundle.py'
---

<frozen-after-approval reason="human-owned intent 鈥?do not modify unless human renegotiates">

## Intent

**Problem:** Impact Analyzer 鐨勬牳蹇冭涔夊凡閫氳繃 focused unit tests锛屼絾鐢熶骇 CLI 鐨勭湡瀹炴垚鍔熻矾寰勫皻鏈楠岃瘉锛歩ndex discovery銆乫rozen-context binding銆乺eport/run-manifest 鍙戝竷銆佸け璐?artifact 鍜?hard-gate 娉ㄥ唽浠嶇己灏戠鍒扮璇佹嵁銆?
**Approach:** 澧炲姞涓存椂鐪熷疄 Git repository 鐨?CLI harness锛岄獙璇?revision-bound index 涓?frozen context 閫氳繃鍚庣敓鎴愪笉鍙彉 report 鍜?run manifest锛涘悓鏃惰鐩栫ǔ瀹氬け璐ヨ矾寰勪笌 output collision锛屽苟灏嗚娴嬭瘯妯″潡娉ㄥ唽鍒伴粯璁?obligations hard gate銆備繚鎸佹棦鏈?report/run-manifest schema锛屼笉鎺ュ叆 Runtime銆並nowledge producer 鎴?KCP generated state銆?
## Boundaries & Constraints

**Always:** 浣跨敤鍙俊瀹屾暣 Git revision锛沬ndex銆乵anifest銆乫rozen context銆乺eport 涓?run manifest 蹇呴』鏍￠獙 schema銆佽矾寰勩€丼HA-256銆乺evision 鍜?binding锛涜緭鍑轰粎鍐欏叆 `logs/ci/**`锛涙祴璇曞繀椤诲彲鍦?Windows 浣跨敤 `py -3` 杩愯锛涘け璐ュ繀椤?fail-closed 骞惰繑鍥炵ǔ瀹?exit code銆?
**Ask First:** 鑻ラ渶瑕佷慨鏀规棦鏈?report/run-manifest/KCP sidecar schema銆佹敼鍙?index discovery policy銆佸紩鍏ユ柊绗笁鏂逛緷璧栨垨鏀瑰彉 KCP authority/current/LKG/freeze/generated state锛屽厛鏆傚仠骞惰姹傛壒鍑嗐€?
**Never:** 涓嶄慨鏀?`docs/121.txt`锛涗笉瀹炵幇 Runtime Mapping銆並nowledge Binding producer銆丟odot 闆嗘垚鎴栨渶缁?CAP acceptance锛涗笉鏀惧 Locator/Analyzer 鏍￠獙锛涗笉鎻愪氦鐢熸垚鐨?index銆乸ublication銆乻napshot 鎴?frozen context銆?
## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| CLI_SUCCESS | 涓存椂鐪熷疄 Git repo銆佸尮閰?revision 鐨?index銆佹湁鏁?frozen context銆佸敮涓€ output | report 涓?run-manifest 鍘熷瓙鍐欏叆 `logs/ci/**`锛孲HA/revision/binding 涓€鑷达紝exit 0 | N/A |
| INDEX_DISCOVERY | 鏈樉寮忎紶 index锛屼粎瀛樺湪涓€涓尮閰?revision/index identity | 鑷姩鍙戠幇鍞竴 index 骞舵垚鍔熷垎鏋?| 鏃犲尮閰嶈繑鍥?`missing_index`锛涘 identity 杩斿洖 `index_identity_collision` |
| INVALID_HANDOFF | 缂哄け鎴?revision/task/consumer/hash 涓嶅尮閰嶇殑 frozen context | 涓嶆墽琛屽垎鏋愶紝涓嶄骇鐢熸垚鍔?artifact | 绋冲畾 `invalid_kcp_binding`/`revision_mismatch` exit code |
| OUTPUT_COLLISION | output report 宸插瓨鍦?| 涓嶈鐩栧凡鏈?artifact | 绋冲畾 `index_identity_collision` |
| INVALID_TARGET | malformed target JSON 鎴?unsupported target | 澶辫触 report/run-manifest 鍙拷婧笖涓嶅啋鍏呮垚鍔?| 绋冲畾 `unsupported_target` 鎴栧搴?code |

</frozen-after-approval>

## Code Map

- `scripts/python/analyze_impact.py:33-170` -- CLI 鍙傛暟銆乮ndex discovery銆乫rozen binding銆乺eport/run-manifest 鍙戝竷鍙婄ǔ瀹氬け璐ュ鐞嗐€?- `scripts/python/impact_analyzer.py:709-1038` -- Analyzer API銆乺eport validator 涓?failure artifact锛屼綔涓?harness 琚祴鍏ュ彛銆?- `scripts/python/impact_analysis_index.py:1073-1210` -- 姝ｅ紡 index build/reuse/publication 鍏ュ彛锛屾祴璇曞簲澶嶇敤鑰岄潪澶嶅埗銆?- `scripts/python/tests/test_impact_analysis_index_repository_smoke.py:1-220` -- 涓存椂鐪熷疄 Git repo銆佹彁浜ゃ€佹竻鐞嗕笌 source/index fixture 妯″紡銆?- `scripts/python/run_gate_bundle.py:300-345` -- obligations hard gate 娴嬭瘯妯″潡娉ㄥ唽琛ㄣ€?- `scripts/python/tests/test_impact_analyzer.py:1-413` -- Analyzer semantic fixtures銆乥inding helper 涓?report assertions锛屽彲澶嶇敤娴嬭瘯鏁版嵁鏋勯€犮€?
## Tasks & Acceptance

**Execution:**
- [x] `scripts/python/tests/test_analyze_impact_cli.py` -- 鏋勯€犱复鏃剁湡瀹?Git repo锛岃繍琛屾寮?index builder 涓?`analyze_impact.py`锛岃鐩栨垚鍔熴€佽嚜鍔?discovery銆乮nvalid handoff銆乧ollision銆乵alformed target锛屽苟楠岃瘉 report/run-manifest 瀛楄妭鍝堝笇涓?revision binding銆?- [x] `scripts/python/analyze_impact.py` -- 浠呭湪 harness 鏆撮湶鍑虹殑缂洪櫡鑼冨洿鍐呬慨澶嶇ǔ瀹氶敊璇垎绫汇€佸師瀛?publication 鎴栬緭鍏ユ牎楠岋紱淇濇寔鏃㈡湁 schema 涓?fail-closed 璇箟銆?- [x] `scripts/python/run_gate_bundle.py` -- 灏?CLI harness 娉ㄥ唽鍒?obligations hard gate锛岀‘淇濋粯璁ら棬绂佸疄闄呮墽琛岃妯″潡銆?- [x] `_bmad-output/implementation-artifacts/deferred-work.md` -- 鍒犻櫎鏈鏍煎搴旂殑閲嶅寤舵湡鏉＄洰鎴栬拷鍔犲畬鎴愯瘉鎹紝淇濇寔寤舵湡鍒楄〃鍑嗙‘銆?
**Acceptance Criteria:**
- Given 涓存椂鐪熷疄 Git repository 涓庡敮涓€鍖归厤鐨?immutable index锛寃hen 杩愯 CLI 鎴愬姛璺緞锛宼hen exit code 涓?0锛宺eport 鍜?run-manifest 鍧囧瓨鍦ㄤ簬 `logs/ci/**`锛屼笖鍏?revision銆乮ndex identity銆乥inding 涓?SHA-256 鍙浉浜掗獙璇併€?- Given 鏈樉寮忎紶鍏?index锛寃hen 浠呭瓨鍦ㄤ竴涓尮閰?revision/index identity锛宼hen CLI 鑷姩 discovery 骞朵骇鐢熶笌鏄惧紡 index 绛変环鐨勭粨鏋溿€?- Given frozen context 缂哄け銆乻chema 閿欒銆乺evision/task/consumer/hash 涓嶅尮閰嶏紝when 杩愯 CLI锛宼hen 鍦ㄥ垎鏋愬墠 fail-closed锛岃繑鍥炵ǔ瀹氶潪闆?code锛屼笖涓嶄骇鐢熸垚鍔?report銆?- Given output path 宸插瓨鍦紝when 鍐嶆杩愯 CLI锛宼hen 涓嶈鐩栧師鏂囦欢骞惰繑鍥炵ǔ瀹?collision code銆?- Given 榛樿 obligations hard gate锛寃hen 鎵ц闂ㄧ锛宼hen CLI harness 娴嬭瘯妯″潡琚疄闄呭彂鐜板苟閫氳繃銆?
## Spec Change Log

- 2026-09-05: 工件完整性修复勘误：CLI 统一预验证并发布 report/manifest，目录写者锁与 Windows 不覆盖 rename 保护协作进程；早期失败及输出冲突均尝试保留独立失败二件套。原 malformed target 的无工件断言已纠正。此处“原子发布”仅适用于单文件，两文件不是原子事务。真实 Git fixture 使用正式 builder，但 binding 仍为 loader-compatible synthetic fixture，不能证明真实 freeze lineage。完整矩阵和最终退出码见 `logs/ci/2026-09-05/impact-cli-artifact-integrity/`；当前保持 in-review，不作 CAP 总验收声明。

- 2026-09-05: 完成度勘误：重开为 in-review。malformed target 测试断言无工件，与 INVALID_TARGET 要求冲突；并发及部分发布仍未闭环。原冻结块存在真实编码损坏，保留历史字节；修复规格为 spec-kcp-impact-cli-artifact-integrity.md。测试使用 loader-compatible synthetic binding，不符合真实 KCP frozen schema；先前 schema-compatible 措辞撤回。总缺陷见 execution-plans/2026-09-05-kcp-impact-analysis-completion.md。

- 2026-09-05: 复审补齐非 C# source 过滤回归、malformed JSON fail-closed、multi-index discovery collision、run-manifest collision preservation，并将并发 TOCTOU、内部错误 manifest lineage 与真实 freeze schema 衔接登记为后续切片。

- 2026-09-05: 按实现调查结果明确 CLI harness 使用 schema-compatible synthetic binding；真实 freeze artifact lineage 字段对齐保留到后续 KCP integration。

## Design Notes

娴嬭瘯閫氳繃涓存椂浠撳簱鎻愪氦鐪熷疄 source/index 杈撳叆锛岄伩鍏嶇洿鎺ョ鏀瑰綋鍓嶅伐浣滄爲鎴栦緷璧?stale generated state銆傛垚鍔熸柇瑷€浣跨敤鍘熷瀛楄妭 SHA-256锛涘け璐ユ柇瑷€妫€鏌ョǔ瀹氶敊璇?code 涓庝笉浜х敓鎴愬姛 artifact銆傝鍒囩墖鍙獙璇?CLI 鐢熶骇 harness锛屼笉鏀瑰彉 Analyzer銆並CP 鎴?handoff schema銆?
## Scope Clarification

鏈垏鐗囩殑 CLI_SUCCESS 浣跨敤 schema-compatible synthetic binding锛屼粎楠岃瘉 Analyzer CLI銆乮ndex discovery銆乺eport/run-manifest 鍙戝竷涓庣ǔ瀹氬け璐ヨ矾寰勩€傚綋鍓?`freeze_knowledge_context.py` 浜х墿缂哄皯 `task_id`銆乣publication_generation` 涓?`publication_sha256` 绛?binding 瀛楁锛屽洜姝ゆ湰鍒囩墖涓嶅０绉拌鐩栫湡瀹?freeze artifact锛涚湡瀹?schema 琛旀帴鍒楀叆鍚庣画 KCP integration銆?
## Verification

**Commands:**
- `py -3 -m unittest scripts.python.tests.test_analyze_impact_cli -v` -- expected: CLI success and fail-closed integration cases pass.
- `py -3 -m unittest scripts.python.tests.test_impact_analyzer scripts.python.tests.test_impact_analysis_index scripts.python.tests.test_impact_analysis_index_repository_smoke` -- expected: existing Analyzer and Index suites remain green.
- `py -3 -m unittest scripts.python.tests.test_impact_analyzer scripts.python.tests.test_analyze_impact_cli` -- expected: focused producer and CLI harness suites pass.
- `py -3 -m py_compile scripts/python/analyze_impact.py scripts/python/impact_analyzer.py scripts/python/tests/test_analyze_impact_cli.py` -- expected: no syntax errors.
- `git diff --check` -- expected: no whitespace errors and `docs/121.txt` remains untouched.

## Suggested Review Order

**CLI entry and publication**

- 解析参数并驱动生产分析流程
  [`analyze_impact.py:73`](../../scripts/python/analyze_impact.py#L73)

- 保持报告与 manifest 原子发布
  [`analyze_impact.py:119`](../../scripts/python/analyze_impact.py#L119)

**Semantic boundary protection**

- 仅对 C# source 建立符号索引
  [`impact_analyzer.py:151`](../../scripts/python/impact_analyzer.py#L151)

- 复用可信 index 与 binding 校验
  [`impact_analyzer.py:709`](../../scripts/python/impact_analyzer.py#L709)

**Gate and evidence**

- 通过临时真实 Git repo 验证成功与失败路径
  [`test_analyze_impact_cli.py:20`](../../scripts/python/tests/test_analyze_impact_cli.py#L20)

- 确保 harness 进入默认 obligations gate
  [`run_gate_bundle.py:331`](../../scripts/python/run_gate_bundle.py#L331)



