# KCP Impact Analysis 完成计划

- Title: KCP Impact Analysis 完成计划
- Status: active
- Branch: feat/kcp-impact-analysis-prd
- Git Head: faa04e7ebcedde15d28951820a09b8061bc56d71
- Goal: 按 docs/121.txt、SPEC 和 Architecture 逐项补齐功能及验收证据。
- Scope: Impact CLI、Runtime mapper、Knowledge producer、真实 freeze lineage、consumer adapters、CAP 验收；遵守既有 authority 边界。
- Current step: Runtime Mapping 调查完成，已形成 draft 实施规格；整体功能继续保持 active。
- Last completed step: 审查修复后的 CLI 与 LockAndAtomicity 共 41 项通过；此前核心 100 项通过、受归档污染的 smoke 静止重跑通过；独立 4 项导入、gate consistency 通过。
- Stop-loss: 不修改或提交 docs/121.txt，不写 current/LKG/publication/freeze/generated state；不把 synthetic fixture、测试数量或局部 done 当作整体完成。
- Next action: 确认 Runtime 实施规格后先补 RED，再接入 parser/resolver/report/CLI；CLI-05/06 在真实 Knowledge/freeze 集成前收口，最后完成 adapter 和 CAP 总验收。
- Recovery command: git status --short
- Open questions: 后续真实 freeze lineage 从哪些既有只读权威工件解析；本轮不扩 KCP schema。
- Exit criteria: 每项 CAP 有明确实现路径、正负测试、实际运行证据；所有 Needs Fix 已关闭或明确阻止整体完成声明。
- Related ADRs: docs/adr/ADR-0035-repository-knowledge-control-plane.md
- Related decision logs: decision-logs/2026-09-05-kcp-impact-analysis-open-findings.md
- Related task id(s): n/a - repository toolchain feature, not a Taskmaster gameplay task.
- Related run id: impact-cli-artifact-integrity
- Related latest.json: n/a - no task-scoped review pipeline started.
- Related pipeline artifacts: logs/ci/2026-09-05/impact-cli-artifact-integrity/review-triage.md

## 分步推进与报告对账

| 顺序 / 报告要求 | 当前证据 | 状态与下一入口 |
|---|---|---|
| Index 生命周期、source manifest、identity | impact_analysis_index.py、build_impact_index.py、Index 测试文件已存在 | 已实现主体；本轮补收集完整回归退出状态，未宣称全部验收通过 |
| C# resolver、typed edges、tests、risk/report | impact_analyzer.py 和 test_impact_analyzer.py | 受限 C# 子集已有实现；不等于支持全部 CAP-1/3 |
| 1. CLI 失败证据与不可覆盖发布 | analyze_impact.py；CLI-01～04 | 本轮：spec-kcp-impact-cli-artifact-integrity.md |
| CLI discovery/binding 验证 | CLI-05～06、TEST-01 | 紧接本轮收口，先对齐现有策略，再补矩阵 |
| 2. Runtime Mapping | CORE-01 | 解析静态 Scene/Node/script/signal/resource 绑定，正负 fixtures 与真实仓库 smoke |
| 3. Knowledge Binding | CORE-02 | 只读 source reread、ADR/Task/Contract/Decision 来源及 SHA、真实 freeze lineage |
| 4. Existing Adapter Handoff | impact_analysis_handoff.py 已存在；ADAPTER-01～02 | producer→handoff→consumer、revision/hash、resume/fork、crash/manifest 边界验证 |
| 5. Acceptance | ACCEPT-01 | CAP-1～CAP-6、PRD AC 正负矩阵；authority/generated state 不变证据 |

完整缺陷 ID 和恢复入口见配套 decision log。deferred-work.md 是历史追加记录，包含重复和过期内容，不能作为当前完成度清单。

## 本轮验证计划

实现规格：`_bmad-output/implementation-artifacts/spec-kcp-impact-cli-artifact-integrity.md`。

先补早期失败、冲突、写入异常回归，保留 RED；修复后执行 CLI、Analyzer、完整 Index 与 repository smoke，收集最终退出码。独立执行 HardGateRegistrationTests，确认不会因导入顺序隐藏失败。然后验证 gate consistency、recovery docs、diff。

证据目录：`logs/ci/2026-09-05/impact-cli-artifact-integrity/`；测试执行后再登记实际文件和结果，不提前填写 PASS。所有尚未修复 Needs Fix 保留在 decision log；本轮通过后继续 Runtime 主线。

## 本轮实现与用例映射

| 缺陷 / 矩阵 | 实现与已执行验证入口 | 证据 |
|---|---|---|
| CLI-01 / EARLY_FAILURE | 输出边界先于 target/revision；malformed、invalid revision、不可序列化 target 保留失败二件套 | cli-red.log；cli-green.log |
| CLI-02 / INVALID_OUTPUT | logs/ci 字面边界、Windows 保留名、junction 重解析逃逸验证，失败转独立目录 | test_invalid_output_uses_isolated_diagnostics；test_reparse_output_escape_is_rejected_and_preserves_destination |
| CLI-03 / COLLISION | 目录写者锁、复用 atomic_publish_bytes；单件既存、并发两进程胜者哈希一致 | cli-baseline-corrected-red.log（旧实现实际 [0,0]，exit 1）；cli-green.log |
| CLI-04 / PARTIAL_FAILURE | 发布前序列化验证两件、按文件身份与字节补偿、删除失败隔离；保留同字节替换者 | test_manifest_failure_removes_owned_success_and_saves_failure_pair；test_same_bytes_replacement_is_not_removed_by_compensation；test_report_delete_failure_quarantines_owned_report |
| STORAGE_FAILURE / 锁清理 | stdout evidence_saved=false/evidence_error；完整成功二件套的锁清理异常单列 cleanup_warning | test_storage_failure_explicitly_reports_unsaved_evidence；test_lock_cleanup_failure_reports_completed_pair_with_warning |
| TEST-01 | 独立 loader 的测试显式提供 scripts/python 导入路径，不依赖其他测试污染 sys.path | index-import-red.log（exit 1）；index-import-green.log |

初始 RED 包含测试误传绝对 frozen-context 导致的 code 4 和尚不存在发布接口的 AttributeError，不将这些视作产品缺陷证据；修正后通过 logs 内保存的 baseline 及 run_corrected_red.py 重现并发和单件冲突。

边界：文件身份检查不是面对非协作写者的原子 compare-and-delete；进程强杀、reader manifest 协议和真实 freeze lineage 仍在 ADAPTER-01/CORE-02。若存储同时拒绝补偿删除与隔离 rename，stdout 会明确残留 report 路径，不能承诺物理撤销。此类存储故障及外部写者竞争不作本轮完整保证。

## 已收集退出码

- CLI 最终矩阵：`cli-green.log`，16 tests，46.640s，exit 0；成功与失败 manifest 都校验既有 report_sha256 字段。
- 完整 Analyzer/Index/repository smoke：`core-index-smoke.log`，101 tests，331.803s，exit 1。唯一失败为 smoke 最后的 logs_fingerprint 不变断言；运行期间 evidence runner 持续写日志且并行 CLI 归档改变 logs 树。100 项其余测试通过，smoke 的构建/reuse/逐源哈希断言均走到末尾；不将该次完整运行写成 PASS。
- 独立 HardGateRegistrationTests：`index-import-green.log`，4 tests，exit 0；此前 `index-import-red.log` 为 exit 1。
- Gate consistency：`gate-consistency.log`，exit 0。
- Recovery docs 与 diff：`recovery-docs.log`、`diff-check.log`，exit 0；最终文档更新后再复验。
- Repository smoke：改为内存 capture 并暂停工作区写入，定向重跑通过，`repository-smoke-retry.log`，exit 0。保留第一次完整运行的 exit 1，不覆盖失败证据。

## 审查修复完成

三层审查结果与逐项分流见 `review-triage.md`。本轮 patch 均已执行：发布前身份、补偿查询异常与残留诊断、唯一清理 marker、失败锁诊断、根 junction、受控竞争窗口。`review-red.log` 为 8 tests / exit 1；`review-fallback-red.log` 为 1 test / exit 1；最终 `review-green.log` 为 41 tests / 69.150s / exit 0。该次覆盖 CLI 和受影响的 LockAndAtomicity；此前已通过的无关完整核心与 smoke 未重复运行。

CLI-01/02/03 与 TEST-01 关闭。CLI-04 在协作写者及可执行补偿范围内关闭；不可验证身份或系统拒绝撤销时明确报告残留，消费端必须在 ADAPTER-01 完成 manifest/crash 一致性后才可主张完整保证。DOC-01 已追加可读勘误并撤回旧 done，历史冻结块的原始乱码未猜测重写。

## Runtime Mapping 当前入口

## CORE-01 本轮验证证据

- 定向 Runtime/Analyzer/CLI 回归：52/52 通过。
- Index 与 repository smoke：79/79 通过。
- Gate bundle consistency 与 recovery docs：通过。
- 真实仓库静态源读取证据：`logs/ci/2026-09-05/impact-runtime-mapping/real-fixture-evidence.json`，包含 `PrimaryButton.tscn`、`default_theme.tres` 的 SHA-256、绑定锚点和 `runtime_refs` 投影。
- 证据覆盖显式 script、SubResource、稳定 node identity、来源哈希和报告投影；未覆盖动态调用、实例递归或真实 freeze 集成。
- CORE-01 当前可关闭“静态绑定解析”子项，但不关闭完整 CORE-01/ACCEPT-01。

## CORE-02 本轮验证证据

- `knowledge_binding_producer.py` 对四类真实 consumer bundle 执行 source reread：Chapter 4、Chapter 5、Chapter 6、Review 全部通过。
- 每类 evidence 均绑定 request_id、bundle SHA、repository revision 与 source SHA；对应产物位于 `logs/ci/knowledge-context/rollout/`。
- producer、freeze binding integration、knowledge freeze 定向测试：7/7 通过。
- 该证据关闭 producer/source-reread/hash lineage 子项；完整 ADR/Task/Contract/Decision 自动发现及真实 freeze 生产集成仍不关闭 ACCEPT-01。

## ADAPTER-01 本轮验证证据

- `logs/ci/2026-09-05/adapter-handoff/adapter-01-evidence.json` 登记 handoff、Chapter 6 和 Review preflight 结果。
- 相关测试覆盖 partial/invalid/revision mismatch、sidecar/hash lineage、resume/fork identity 和下游步骤阻断；本轮相关测试 95/95 通过。
- ADAPTER-01 的 fail-closed 与 identity 校验子项可关闭；ADAPTER-02 的历史 marathon warn-mode 差异仍开放。

## ADAPTER-02 本轮验证证据

- `fast-ship` 的 delivery profile 明确使用 `agent_review.mode=warn`；fork 建议应生成 pending soft approval request，但不阻断 pipeline。
- 修正 marathon 回归中将 warn 行为误判为 require 的过期断言，保留对 approval request、latest index、execution context 和 summary 状态的校验。
- `scripts/sc/tests/test_run_review_pipeline_marathon.py`：17/17 通过。
- ADAPTER-02 的该历史 warn-mode 差异已关闭；未改变 standard/require 模式的阻断行为。

## CLI-05/06 本轮验证证据

- `logs/ci/2026-09-06/cli-discovery-lineage/cli-05-06-evidence.json` 登记当前 HEAD、`refs/heads/main` 以及 CLI discovery/lineage 验证范围。
- `test_analyze_impact_cli`：23/23 通过。
- 覆盖显式 index、自动 discovery、missing index fail-closed、多 provenance collision、invalid KCP binding、sidecar revision mismatch 和 output collision preservation。
- 测试仍使用 synthetic frozen binding；因此关闭 CLI-05/06 的 CLI discovery/lineage 验证子项，不关闭真实 freeze schema 的 ACCEPT-01。

## ACCEPT-01 真实 main 验收阻塞

- 当前 `main` 为 `40530082e8e4851ee80d6a90a6e72d2b6da3d8f2`，真实 main worktree 不包含 `scripts/python/build_impact_index.py`、`analyze_impact.py` 或 `impact_analysis_handoff.py`。
- 在临时 main worktree 执行 Impact Index builder 的结果为文件不存在；因此无法在 main 上完成真实 `index → analyzer → handoff → consumer` 链路。
- 当前功能分支上的 synthetic/feature-branch 测试不能证明 main 生产验收。ACCEPT-01 保持 OPEN，恢复入口是先将 Impact Analysis 实现合入 main，再用当前 main commit 重新 publish/freeze 并重跑真实链路。

规格：`_bmad-output/implementation-artifacts/spec-kcp-impact-runtime-mapping.md`。调查发现 producer 和 validator 都必须启用既有 binds；scene/resource resolver 当前只验证路径存在，需补 source_kind；索引虽已有 .tscn/.tres/.res，但 .gd 及 Analyzer 代码身份尚未纳入配置。选择将 .gd 作为 opaque 哈希脚本，不扩大到 GDScript 语义分析。

本轮只绑定显式静态事实：局部 Node、实际 ExtResource/SubResource 使用、connection 和已有 C# 影响路径对应的直接 owner。不递归展开实例，不根据同名 signal/event 猜业务调用。使用真实 PrimaryButton/Theme 源码的隔离 Git fixture 取证，不发布当前工作区 KCP state。当前仅完成计划，CORE-01 尚未关闭。
