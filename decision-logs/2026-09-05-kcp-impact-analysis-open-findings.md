# KCP Impact Analysis 未关闭缺陷

- Title: KCP Impact Analysis 未关闭缺陷
- Date: 2026-09-05
- Status: accepted
- Supersedes: none
- Superseded by: none
- Branch: feat/kcp-impact-analysis-prd
- Git Head: 8e751d1a0303ed343691aabb67f9b0d394914f59
- Why now: 用户要求按 docs/121.txt 补齐剩余实现；前次 CLI done 声明存在验收缺口。
- Context: 本次完整 UTF-8 读取 docs/121.txt，并对照当前代码；报告针对旧提交，其缺失结论不能直接套用当前 HEAD。当前已有 Index/C# Analyzer，但 Runtime、Knowledge producer、真实 freeze 集成和总验收仍开放。
- Decision: 按 CLI 工件完整性、Runtime、Knowledge/真实 freeze、adapter 端到端、CAP 总验收顺序推进；每项以实现和测试证据关闭。旧 CLI 规格先重开并追加勘误；不把 synthetic binding 描述为真实 frozen schema compatible。
- Consequences: 本轮完成只关闭工件完整性子集，报告总缺陷继续由执行计划追踪。保留 docs/121.txt 且不纳入提交；不修改 generated state、不自动 push。
- Recovery impact: 后续从配套执行计划恢复，不能从历史 done 或重复 deferred 条目推定整体完成。
- Validation: CLI 完整性 16 项回归及独立 4 项导入回归通过；完整 101 项套件出现 1 项 smoke logs 指纹污染失败，保留退出 1；静止工作区定向 smoke 重跑 exit 0。最终证据按配套执行计划登记。
- Related ADRs: docs/adr/ADR-0035-repository-knowledge-control-plane.md
- Related execution plans: execution-plans/2026-09-05-kcp-impact-analysis-completion.md
- Related task id(s): n/a - repository toolchain feature, not a Taskmaster gameplay task.
- Related run id: impact-cli-artifact-integrity
- Related latest.json: n/a - no task review pipeline invoked.
- Related pipeline artifacts: logs/ci/2026-09-05/impact-cli-artifact-integrity/planning-audit.md

## 缺陷登记（状态以本轮关闭判定为准）

| ID | 问题 | 修复入口 |
|---|---|---|
| CLI-01 | target/revision 早期失败不产失败二件套；现有测试断言错误行为 | 本轮规格 |
| CLI-02 | 未验证的 output 可能被异常处理写入；report 与 manifest 可重名 | 本轮规格 |
| CLI-03 | manifest 单独存在、report 单独存在、并发创建均缺少完整保护 | 本轮规格 |
| CLI-04 | 第二件失败或 internal_error 可遗留、覆盖、错配工件 | 本轮规格 |
| CLI-05 | discovery 未完整校验候选 manifest；与 trusted_ref 的选择规则需澄清 | Knowledge/真实集成前单独收口，不暗改策略 |
| CLI-06 | binding schema/task/consumer/hash/lineage 矩阵、显式 index 成功等价性未充分验证 | CLI 后续验证及真实 freeze 集成 |
| DOC-01 | CLI 规格正文编码损坏；done 与断言不一致；deferred 重复和过期 | 本轮追加可读勘误，执行计划统一状态 |
| TEST-01 | 独立 HardGateRegistrationTests 曾有 builder import 错误；完整 Index 退出状态缺失 | 本轮完整验证，失败先定位 |
| CORE-01 | Scene/Node/signal/resource/binds 未完成 | Runtime Mapping |
| CORE-02 | ADR/Task/Contract/Decision producer 未完成；真实 freeze 字段与 loader 不兼容 | Knowledge producer 与 lineage 对齐 |
| ADAPTER-01 | TOCTOU、resume/fork identity、真实 mains、manifest reader/crash 一致性未闭环 | adapter 端到端验证 |
| ADAPTER-02 | 历史 marathon warn-mode 期望差异尚未重新验证 | adapter 定向验证 |
| ACCEPT-01 | CAP-1～CAP-6 完整功能尚无端到端通过证据 | 最终验收 |

进程强杀与可捕获 I/O 失败分开验收。仅修 writer 不足以证明 adapter 不会消费缺少 manifest 的 report。

## 本轮处置证据

CLI-01～CLI-04 的规格内实现与回归已完成；三层 review 后的 patch 通过 `review-green.log` 的 41 项回归。目录锁保护协作 CLI；dev/inode/ctime/mtime 与字节比对不能作为面对非协作进程的原子删除证明。身份不可验证、存储拒绝删除与隔离时明确输出残留路径，该物理撤销限制保留给 ADAPTER-01 reader/manifest 验收处理。

TEST-01 的独立导入问题已修并通过 4 项回归。完整运行 exit 1 的唯一失败是本轮 evidence runner 与并行归档污染 repository smoke 的全 logs 指纹；已改 runner 为先内存捕获、测试退出后归档，失败模块在静止工作区定向重跑 exit 0，不跳过断言。

DOC-01 已追加中文勘误并撤回旧完成度及真实 schema compatible 说法；原冻结块编码损坏保留历史字节。CLI-05/06、CORE-01/02、ADAPTER-01/02、ACCEPT-01 持续开放，其修复入口和证据映射在配套执行计划。

## 本轮关闭判定

## CORE-01 追加证据

- `logs/ci/2026-09-05/impact-runtime-mapping/real-fixture-evidence.json` 记录真实 `PrimaryButton.tscn` 与 `default_theme.tres` 的源码哈希、绑定边、行号锚点和 runtime_refs 投影。
- Runtime、Analyzer、CLI 定向回归 52/52；Index 与 repository smoke 79/79；gate consistency 与 recovery docs 通过。
- 该证据关闭 CORE-01 的静态 Scene/Node/Resource 解析子项；动态调用、实例递归、真实 freeze lineage 和端到端 ACCEPT-01 仍开放，不能将 CORE-01 整体标记为完成。

## CORE-02 追加证据

- 四类 consumer binding rollout 均通过 source reread 与 SHA 校验：Chapter 4、Chapter 5、Chapter 6、Review。
- producer、freeze binding integration、knowledge freeze 定向测试 7/7 通过。
- 已关闭 source reread、request/revision/bundle/source hash lineage 子项；ADR/Task/Contract/Decision 的完整自动发现和真实 freeze 生产闭环仍属于开放项。

## ADAPTER-01 追加证据

- `logs/ci/2026-09-05/adapter-handoff/adapter-01-evidence.json` 记录 handoff、Chapter 6、Review preflight 的真实执行范围。
- 相关 95 项测试通过，覆盖原子参数、fail-closed、sidecar lineage、resume/fork identity 和下游步骤阻断。
- ADAPTER-01 的已覆盖子项关闭；ADAPTER-02 仍因 marathon warn-mode 期望差异保持 OPEN。

## ADAPTER-02 追加证据

- `fast-ship` 的 `agent_review.mode=warn` 语义为写入 soft approval request 但不阻断 pipeline；`standard` 的 require 语义保持阻断。
- 修正过期 marathon 断言后，`test_run_review_pipeline_marathon` 17/17 通过。
- ADAPTER-02 的 warn-mode 期望差异已关闭；ACCEPT-01 仍等待完整端到端验收。

## CLI-05/06 追加证据

- `logs/ci/2026-09-06/cli-discovery-lineage/cli-05-06-evidence.json` 记录 23/23 CLI 回归和真实 HEAD/trusted-ref。
- discovery、missing index、provenance collision、binding/revision/sidecar lineage 与 output collision 均有覆盖。
- synthetic frozen binding 边界保持明确；真实 freeze schema 对齐仍属于 ACCEPT-01 开放项。

## ACCEPT-01 真实 main 阻塞证据

- 临时 main worktree（`40530082e8e4851ee80d6a90a6e72d2b6da3d8f2`）执行 builder 失败：`scripts/python/build_impact_index.py` 在 main 不存在。
- `git ls-tree main scripts/python` 仅能发现 freeze 入口，未发现 Impact Analysis builder/analyzer/handoff 实现。
- 因此当前 branch 的 CAP/CLI/Runtime/Knowledge 证据不能升级为 main 的生产端到端 PASS；ACCEPT-01 保持 OPEN，需先完成合并或在 main 集成对应实现。

- CLI-01、CLI-02、CLI-03、TEST-01：已关闭，有实现和实际执行的回归证据。
- CLI-04：协作写者、可补偿 I/O 路径已关闭；物理存储拒绝和非协作写者的消费安全转由仍开放的 ADAPTER-01 验收，不能宣称普遍无残留。
- DOC-01：可读勘误与错误完成声明已处理；原冻结块与历史 deferred 保留，当前状态由本计划登记。
- 仍有 Needs Fix：CLI-05/06（包括已知 index/binding 与原始 revision 的失败追溯）、CORE-01/02、ADAPTER-01、ACCEPT-01。ADAPTER-02 的 warn-mode 差异已关闭；整体 KCP Impact Analysis 未完成。
