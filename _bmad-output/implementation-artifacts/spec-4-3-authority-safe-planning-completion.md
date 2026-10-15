---
title: 'Story 4.3：权威安全的规划完成报告'
type: 'feature'
created: '2026-10-15'
status: 'done'
baseline_commit: '4a4af4e97adc16db54c4301779f20df98b97f40a'
review_loop_iteration: 0
context:
  - '{project-root}/AGENTS.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-4-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** apply目前直接报告planning_complete，缺少统一汇总全部checkpoint、记账及全局audit；写入目标也需要明确保护权威来源与运行时状态。

**Approach:** 最终报告绑定完整有效链和确定性audit，分别暴露通过项、冲突、义务、证据缺口和runtime状态；apply和恢复均检查规划写入边界。

## Boundaries & Constraints

**Always:** planning_complete仅来自完整链及有效最终机器审计；source_gap/未解硬冲突阻断。planned义务可保留，但不能等同runtime成功。所有越权尝试先拒绝并记日志。

**Ask First:** 无；实施AD-10及既定完成语义。

**Never:** 不更改GDD、Requirement、Taskmaster状态、Contract、测试、游戏或runtime acceptance状态；不把LLM文字、规划proof或页面状态当运行验收；不调用收费模型/Godot/远程Git、不改正式基线。

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
| --- | --- | --- | --- |
| COMPLETE | 全部准入/selection/merge及最终audit有效 | planning_complete明确为真，分类报告完整 | runtime仍未验证 |
| BLOCKED | stale proof/audit、source_gap或未解冲突 | 完成阻断，具体缺口可查询 | 不发布伪成功 |
| OBLIGATIONS | 合法planned测试/entrypoint且未运行 | 规划可完成，义务独立显示 | 不能增加satisfied或runtime_verified |
| AUTHORITY | 非法输出path或journal目标越权 | 写入前拒绝并留receipt | 权威文件bytes不变 |

</frozen-after-approval>

## Code Map

- `scripts/python/plan_mvg.py` -- `validate`生成绑定最终报告；`apply`及journal分支消费相同完成证据。替换直接planning_complete=True，保持稳定返回字段。
- `scripts/python/_mvg_global_audit.py` -- 复用Story4.2最终head/来源/proposal绑定，不另建冲突模型。
- `scripts/python/_mvg_requirement_accounting.py` -- 复用accounted/satisfied/route/evidence投影，其局部planning_complete不单独授权整个run。
- `scripts/python/_planning_apply_journal.py` -- 在MVG调用方检查精确trace/manifest目标与source authority，不影响其他workflow的独立合法journal。
- `scripts/python/_project_health_planning.py`, `_project_health_mvg_versions.py` -- 展示同一完成报告，with_runtime_evidence仍独立匹配正式验收。
- `scripts/python/run_mvg_acceptance.py` -- 正式mode=run/status=passed产出runtime真值，仅读取参考、不改变其规范。
- `scripts/python/tests/test_mvg_planning_completion.py` -- fake runner/public CLI、Knowledge与恶意目标拒绝矩阵。
- `docs/adr/ADR-0005-quality-gates.md` -- Accepted门禁依据。

## Tasks & Acceptance

**Execution:**
- [x] 最终报告与完成授权 -- 整条链和audit为权威。
- [x] apply/recovery输出边界 -- 正常仅写获准trace/manifest/日志；越权零写入。
- [x] Knowledge查询 -- 规划与runtime明确分离。
- [x] 定向矩阵及owning文档 -- 统一已部署迁移边界。

**Acceptance Criteria:**
- Given all checkpoints, proofs, selections, merges and final machine audit are valid, when completion is reported, then passed items, conflicts, obligations, evidence gaps and runtime acceptance are separate.
- Given a planning operation targets protected authority or runtime state, when checked, then it is rejected before writes and logged under logs.

## Design Notes

报告只派生状态，不新增任务或独立MVG生命周期。没有运行证据时明确not_verified而非failed。现有正式runtime receipt可以由原consumer显示，不能被规划动作生成、覆盖或提升。实现引用不能作为运行通过，pending obligation不凭空升级完成计数。

精确白名单由当前run冻结的manifest_path和固定planning trace路径构成，并验证仓库相对安全路径、不可越过symlink、不得碰protected authority。旧completed journal验证原内容/hash，不重新解释为新的权限；新事务和pending恢复写入前强制边界。最终完成receipt须在apply后恢复仍绑定实际manifest/proposal/checkpoint，不依赖缓存布尔值。

实施前调查补充：`_run_dir`目前直接拼接run_id，`FORMAL_TRACE_ROOT`为`docs/testing/mvg/planning`。安全边界需覆盖run标识/日志目录、manifest与trace的完整路径解析，拒绝绝对路径、目录穿越、Windows盘符与symlink逃逸；拒绝日志自身也不得跟随恶意run路径写出logs。CLI/parser/builder和显式reopen所使用的路径仍归同一边界，不应新增旁路。运行时receipt仅可读；非法journal必须先完成所有目标检查再调用任何writer。

同步`workflow.md`5.4、plan-mvg Skill、MVG验收及Knowledge说明，清理本次已实现项的target-only表述，保留未实现能力的准确边界。日志放`logs/ci/2026-10-15/story-4-3/`；实现代理不提交。

当前Knowledge的`build_result`已验证local selected proposal与manifest-bound trace；`build_overview/attach_planning_routes`处理正式trace。应在这些已验证绑定之后附加相同最终完成报告，不以apply-summary中的布尔值替代。历史没有新报告的trace可继续显示描述性记账，完成状态明确unknown/unavailable；不可将旧数据自动补判为完成。`with_runtime_evidence`仍是正式运行证据唯一入口，报告不能影响其判定。

Story4.2引入generation隔离后，apply绑定必须沿每条admission的实际generation查找lineage投影，不能继续固定初代`candidates/<label>/lineage-execution.json`。journal中的冻结完成证据还需覆盖最终audit、reopen history/context及各自内容寻址依赖，防止恢复时仅验证旧selected投影而漏过新增冲突。完成报告必须同时适用于正常初代链与保留早期前缀的替代链；不能只测试不重开的路径。

路径白名单同时拒绝manifest与固定trace碰撞、目录别名及指向受保护文件的链接。安全诊断使用独立、已验证的`logs`目标，不沿被拒绝的run标识或链接写日志；若`logs`本身越界，直接拒绝且明确诊断不可安全落盘，不为了记录错误而越界。既有`rebind-handoff`对当前readiness的合法绑定仍保留；其显式handoff输出也须在规划证据边界内，不得成为任意文件写入入口。journal恢复必须允许自己已写入的合法after-image，不能因初始manifest字节已变化而误判来源漂移。

## Verification

- 完成矩阵/public入口：完整链、stale audit、source_gap、reopen未解冲突、planned义务、runtime未执行。
- 路径/journal越权负例：任务/GDD/Contract/测试/游戏/runtime receipt均不改字节且有诊断。
- 相关checkpoint/journal/Knowledge离线定向回归、`py_compile`及`git diff --check`。

## Implementation Evidence

- `_mvg_planning_completion.py` 从有效选择链、最终 audit、validation/delta 和既有记账生成统一报告；validate、apply/recovery 与绑定 manifest 的 Knowledge 消费相同内容。历史无报告时不可推定完成；runtime 仍由独立验收拥有。
- `_mvg_planning_boundary.py` 统一 run/output/journal/handoff 边界，拒绝 Windows 设备、链接、别名等非法路径，并独立安全记录拒绝证据。沿用 generation/checkpoint/reopen 绑定；同一 journal 冻结完成证据，恢复允许自身合法 after-image。
- `logs/ci/2026-10-15/story-4-3/completion-matrix.txt`：新增 2 项通过，156.314 秒。同一离线 fake runner 链覆盖公开 validate、planned 义务、stale audit、source_gap、协议字段删除、未解决重开、保留初代前缀的第二代替代链、恶意/损坏 journal、audit/context 篡改、中断恢复，以及 Knowledge/runtime 独立匹配。
- `logs/ci/2026-10-15/story-4-3/apply-replay.txt`：既有选择链 apply/replay 回归 1 项通过，43.487 秒。
- `logs/ci/2026-10-15/story-4-3/root-final-focused.xml`：主代理最终独立 12 项通过，其中 7 项路径检查包含真实 Windows junction/hardlink、非法公开 prepare 在读取来源前拒绝及权威文件字节不变；其余为 Knowledge/runtime 与 handoff 回归。
- `logs/ci/2026-10-15/story-4-3/root-knowledge.xml`：既有 Knowledge/runtime 回归 4 项通过。
- `accounting.txt` 中记账测试 19 项通过；另 1 项因 unittest 工作目录下的模块导入失败，其精确定向 pytest 复跑在 `accounting-matrix.xml` 中通过。`accounting-legacy-journal.txt` 同时保留了旧 journal 回归通过及此前入口导入失败的证据。
- 初轮 `py_compile`、`git diff --check` 通过。实施未调用真实模型、Godot 或远程 Git，未改正式产品基线与运行时验收产物。

## Review Fix-through Evidence

- 三层审查已完成，逐项处理见 `logs/ci/2026-10-15/story-4-3/review-triage.md`。所有必修项已落实，未增加新的意图或另建生命周期。
- 证据漂移使 Knowledge 完成授权不可用；损坏链产生可查询 blocked 报告。报告完整结构、hash、audit 引用与内容、内部记账均核验；真实有效 evidence 的 satisfied 正例仍通过。
- blocked 报告保留已确定通过项；无有效 audit 的 proposal 义务明确标记未经审计绑定。运行阶段不再把完成阻断标为 validated；结构验证与正式适用性仍维持现有接口分层。
- run 路径检查与内容扫描分离，消除重复扫描；原子文件消失不误报违规。Windows 枚举未提供链接数时读取实际文件属性，不把未知值当作安全单链接。
- Knowledge 测试由未预注入报告的 overview 开始，验证真实 proposal/trace/manifest 绑定正反例及报告自身篡改。旧 handoff 正向 fixture 已迁移，并保留旧路径拒绝。
- 常规 CI 的路径过滤和离线 smoke 已接入新增实现及两项测试模块；仓库根目录同入口命令 `py -3 -B -m unittest scripts.python.tests.test_mvg_planning_completion scripts.python.tests.test_mvg_planning_boundary_independent -v` 通过 13 项，213.610 秒，详见 `review-fixes-matrix.txt`。
- `review-fixes-handoff.txt`：handoff 定向 1 项通过；`review-fixes-static.json`：编译与差异检查通过。主代理最终复验 12 项通过；受保护来源相对 baseline 的 Git 差异为零。
- 没有 sprint-status 文件，按工作流跳过同步；VS Code 命令不可用，文内保留可点击的审阅路径。尚未执行真实模型全流程或 Godot 运行时验收。

## Suggested Review Order

**完成授权与报告**

- 从公开验证入口追踪完整链与最终审计。
  [plan_mvg.py:6557](../../scripts/python/plan_mvg.py#L6557)
- 统一完成报告，保留阻断原因与未实现义务。
  [_mvg_planning_completion.py:43](../../scripts/python/_mvg_planning_completion.py#L43)
- 核验完整报告、内容与审计绑定，拒绝缓存授权。
  [_mvg_planning_completion.py:93](../../scripts/python/_mvg_planning_completion.py#L93)

**输出边界与恢复**

- 路径与文件属性检查先于规划写入。
  [_mvg_planning_boundary.py:68](../../scripts/python/_mvg_planning_boundary.py#L68)
- 所有 journal 目标通过后才允许恢复写入。
  [_mvg_planning_boundary.py:140](../../scripts/python/_mvg_planning_boundary.py#L140)
- 冻结同一报告，允许自身合法中断后镜像。
  [plan_mvg.py:6785](../../scripts/python/plan_mvg.py#L6785)

**消费与验证**

- Knowledge 证据漂移降级，运行验收保持独立。
  [_project_health_mvg_versions.py:13](../../scripts/python/_project_health_mvg_versions.py#L13)
- 综合离线链验证报告、重开、篡改与恢复。
  [test_mvg_planning_completion.py:25](../../scripts/python/tests/test_mvg_planning_completion.py#L25)
- 实际 Windows junction/hardlink 与公开入口负例。
  [test_mvg_planning_boundary_independent.py:17](../../scripts/python/tests/test_mvg_planning_boundary_independent.py#L17)
- 常规 CI 持续执行新增离线矩阵。
  [planning-production-acceptance.yml:64](../../.github/workflows/planning-production-acceptance.yml#L64)
