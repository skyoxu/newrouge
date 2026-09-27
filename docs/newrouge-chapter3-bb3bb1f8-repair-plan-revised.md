# newrouge Chapter 3 旧数据迁移修正方案（Astra 复核修订版）

- 日期：2026-09-27（北京时间）
- 仓库：skyoxu/newrouge
- 评审分支：chapter3-init-20260926
- 被评审提交：bb3bb1f8e56b5e46351d9b0d144f7e101533546c
- 评审时远端 main：4ddc682be3747793230d7d21ff73e1ea50bf8e40
- 使用对象：本地 Codex；本文件包含修复目标、顺序、边界和验收要求，不依赖本次对话之外的 Skill。
- 状态：修复实施输入；不是已修复证明，也不授权自动合并 main。

## 1. 本次修复目标

让旧 Chapter 3 数据迁移后的来源、Requirement、实际任务和发布拓扑相互一致，使该分支具备可审阅、可合并条件。

本次已确认两个 P1：

1. 提交的规划拓扑仍对应旧语义集合，与新增任务所用的新语义集合不一致。
2. 新增任务集合存在可复现的重复承接与历史填写示例误任务化。

本次不以任务数量、pending 状态、空 test_refs / implementation_files 或暂定依赖判定任务不合格。Chapter 3 可以保留需要 Chapter 4/5 继续细化的任务；不要求本次完成全部 Overlay、契约、Acceptance 稳定化和游戏实现。

## 2. 已核实的事实与修订边界

### 2.1 规划拓扑不一致

在 bb3bb1f8 的 Git 快照上调用仓库现有拓扑加载器得到：

| 项目 | 复核结果 |
| --- | --- |
| 拓扑 freshness | fresh=false |
| 来源哈希问题 | 552 条 source_hash_mismatch |
| 提交的 Source Blocks | 3,156 |
| 提交的 Requirement | 575 |
| 任务视图中的不同 semantic_refs | 1,256 |
| 两套 Requirement ID 交集 | 52；任务引用中 1,204 个不在提交的旧语义集合内 |
| 拓扑任务边 | 575 条 implemented_by 指向 INT-* 视图 ID，而非 tasks.json 主编号 |
| 主任务追踪 | 634 个主任务的 task_trace 均没有 source_blocks |
| 来源集合偏差 | 规划拓扑缺少 _bmad-output/gdd.md，额外包含 _bmad-output/epics.md 与 docs/gdd/ui-gdd-flow.candidates.json |

552 是读取 Git blob 的结果。不要用 Windows checkout 的 CRLF 字节与另一种规范化口径比较后，夸大为全部来源失效。

### 2.2 新任务问题的直接证据

| 新任务 | 旧承接或来源事实 | 必须处理的问题 |
| --- | --- | --- |
| 主任务 433 / INT-0300 | Task 14 主表状态 done，已有 MainMenu 的 New Run、Continue、Quit 验收及实现 | 新任务唯一目标仍是上述三个菜单动作；核对后复用旧承接，不重复安排同一实现 |
| 主任务 398 / INT-0265 | Task 63 主表状态 done，已有 Continue 失败原因和恢复提示要求 | 新任务唯一目标是 failed Continue explains reason，没有新增行为差异；核对后建立正确复用关系 |
| 主任务 490 / INT-0357 | PLAYTEST-ISSUE-GRADING-AND-REVISION-GUIDE-NEWROUGE-V1.md 第 5 节明确是历史填写示例 | 示例第 130–132 行被转为三个 FR 和实施任务；“Translations 只有 README”的陈述也已过时，提交中已有 en.csv 与 zh-CN.csv |

Task 490 中涉及的三个 ID 为 FR-74C15D8FA10C、FR-9B96AB7167DC、FR-72DAE0C83495。必须从来源上下文重新判定；若其中一般性规则在其他权威来源独立成立，应保留那条真实规则及其正确来源，而非将示例整行当成当前缺陷。

Task 63 的主表与旧 gameplay view 有既存状态差异。本次不得凭一张视图的 pending 就认定旧功能未完成，也不把该既存差异列成本次新增缺陷。通过实现、验收和必要测试确认复用；若迁移处理必须同步状态，应单独列出依据和字段差异。

以上样例证明新增集合需要对账，不代表全部 501 个任务错误。

### 2.3 可以保留的工作

- 原有 133 个主任务及旧任务视图条目在被审提交中均未改写。
- ADR-0039 记录的构筑多样性口径及已确认的 GDD 建议性措辞修正，不应因本轮数据修复被撤销。
- 派生 PRD/parts 的大幅变化包含对既有权威源漂移的同步；不能仅凭行数减少认定源需求丢失。
- normalize_task 对显式空 semantic_refs 的保留，以及 legacy-packaging 独立锚点处理，可保留并回归验证。
- godot-elements.json 删除只影响首次扫描的上一索引比较，之后可重建；不是合并阻断项。
- 删除的 project_health_knowledge_config.json 与内置默认配置相同，本次未发现功能损失；无需为通过本方案恢复文件。

## 3. 开始前固定本轮输入

1. 读取当前 AGENTS.md、workflow.md 第 3 章、ADR-0038，以及本次实际需要的脚本和 schema。无需另建一套重型流程。
2. 检查 HEAD、工作区、origin/main 和分支关系；记录实际修复起点。若已存在后续修复，逐项验证，避免覆盖有效修改。
3. 保存原任务三联、ID 映射与规划拓扑的比较基线，证据放在 logs/ci/chapter3-migration-repair/<run-id>/。保护用户未提交内容。
4. 在 logs 中建立一份审阅对照表，记录 source block、Requirement、旧主任务/视图 ID、新主任务/视图 ID、处理方式、理由、实施/验收证据。
5. 本地 logs 中可能存在最终 1,256 条语义的产物；读取并验证后才能使用。它们并未随被评审提交一同提交，另一台机器不能假定这些文件存在。

Windows 只读起点检查：

```powershell
git fetch origin main chapter3-init-20260926
git status --short
git rev-parse HEAD
git merge-base origin/main HEAD
git diff --stat origin/main...HEAD
```

## 4. 修复顺序

### 步骤 A：核准当前完整来源与语义候选

1. 以 docs/workflows/chapter3-source-set.json 及实际权威来源为起点，对账 active_sources 与候选 ledger 的来源集合。
2. 将 _bmad-output/gdd.md 纳入正确范围。不能静默把候选 JSON、epics 或旧辅助文件当成权威来源，也不能为匹配旧 ledger 随意修改 source-set。
3. 使用现有 build_source_ledger 与 Chapter 3 投影入口重新生成或修复本轮 ledger/projection。执行前查看 --help；选择同一组明确的输入输出路径。保留尚有效且来源未变的已审阅块，重新审查受变化影响的块。
4. 从 Task 490 反查投影为何把填写示例转成当前需求。同一批次的示例、历史状态、反例和上下文块应作有限同类检查；不要靠标题关键词批量删需求。
5. 对不构成交付义务的示例，使用现有 schema 支持的来源处置表达 context/duplicate 等，并记录依据。确有交付义务的来源必须有真实语义及承接，不能为了降低任务数全部改成 context 或 non-task sink。

本轮不冻结“最终必须等于 1,256 条”。修正错误投影后，Requirement 数量可以变化，但每个变化必须能解释且不遗漏有效来源。

### 步骤 B：对新增任务逐项做归属对账

审阅范围是本分支新增任务及其直接涉及的旧任务/共享规则。先处理 433、398、490，再核对其余新增任务。对同源同义的任务可以分组处理，但每个新增任务都必须有明确处理结果。

| 处理结果 | 条件 | 写入要求 |
| --- | --- | --- |
| reuse | 旧任务/实现/验收已承接相同行为，无新增差异 | 将有效语义关联到旧主任务；保持真实完成状态，处理重复候选 |
| update | 只是来源、引用或明确允许的元数据修正 | 生成具体字段差异，保留原验收、证据、subtasks 和其他扩展字段 |
| create/change | 有独立的缺失行为或真实增量 | 保留/建立对应任务，写清与旧能力的差异和旧任务关系；旧 done 不代表新行为完成 |
| governed non-task sink | 真实全局规则、质量门或 ADR 所有权 | 绑定具体规则、拥有者和检查依据；不能作为清空 orphan 的通用出口 |
| retire candidate | 重复任务或由错误示例生成，无独立剩余工作 | 按现有支持的取消/退役方式记录原因、替代承接或错误来源；主编号不复用 |
| unresolved | 当前证据不足以裁定 | 保持可见且不声称语义闭包通过；不要编造归属 |

具体要求：

- Task 433 先核对 Task 14 的验收及对应菜单实现；确认相同后复用主编号 14。
- Task 398 先核对 Task 63 的失败提示/恢复行为；确认相同后复用主编号 63。
- Task 490 先修来源处置及错误语义，再处理任务，不能只把任务标 done 解决。
- 不批量取消所有 INT 任务，不重排主编号，不复用已经分配的编号。
- 已取消的候选如因编号保留仍留在三联中，不应继续成为有效交付承接，或保留会污染下游校验的失效 semantic_refs；处置理由保留在审阅记录中。
- 不通过降低 gate、忽略未知引用、伪造测试或随意填写 empty map 使校验变绿。

Chapter 3 阶段可以保留暂定依赖和粗粒度验收。只纠正本次来源与承接错误；不要强制所有 pending 任务立即具备 Godot 运行证明。

### 步骤 C：以审阅后的变更集合写回任务三联

1. 先产出可审阅差异，再使用现有增量编译与导出入口写回。避免把全部旧任务当成新项目重新生成。
2. 通过 taskmaster_id 建立视图 ID 与主编号的明确映射；保留 docs/workflows/chapter3-intent-ids.json 的稳定身份，重复执行不得再次创建同义任务。
3. 新生成候选、已持久化任务视图和最终语义必须一致；不能只修改 task view 而继续用旧 candidate 验证闭包。
4. 检查旧 133 个主任务的信息守恒：允许经过审阅的语义/引用补充；禁止意外丢失状态、验收、subtasks、测试、契约和扩展字段。
5. 若取消重复任务影响依赖，修正直接受影响依赖并保留明确理由。原来指向重复任务的引用不能悬空，也不能自动扩大到不相关任务。

### 步骤 D：生成最终规划拓扑

仅在来源与任务处理完成后生成最终拓扑，避免重新生成后又因对账变化失效。

必须更新为同一轮内容：

- docs/planning/semantic-topology/source-blocks.v1.json
- semantic-requirements.v1.json
- capabilities.v1.json（能力分组可为空）
- topology-edges.v1.json
- topology-manifest.v1.json

要求：

1. 发布的 Requirement 与任务实际使用的当前语义一致；未知语义引用为零。
2. 指向 Task 的规划拓扑边必须解析为 tasks.json 主编号。INT-/NG-/GM- 是视图身份，转换必须有 taskmaster_id 依据，不能按编号尾数猜测。
3. 有效 Requirement 有真实任务或受治理的非任务承接。取消候选、不存在的目标和悬空边不算覆盖。
4. 保留可追溯的 source_revision、source manifest 与 artifact/source hashes。不要手改 expected hash 来掩盖来源变化；不要设置必然在下一次提交失效的“文件绑定自身提交”规则。
5. 校验格式化、CRLF/LF 和 Git 提交内容的实际影响。最终必须按消费者读取的 Git blob 校验成功；本地工作区通过不替代提交验证。
6. 通过现有注册 refresh-knowledge 入口写入 planning artifacts。失败尝试仅更新 Attempt，不能伪装 Latest Successful 或 canonical main 发布。

仓库入口支持 --source-manifest、--ledger、--semantics、--capabilities、--edges、--candidates、--report、--coverage、--triplet-attestation。若本轮使用非默认路径，全部明确传入；不要一部分读本轮文件、一部分落回旧默认文件。

普通 project_health_knowledge.py scan 固定读取本地 refs/heads/main。合并前不能把该命令的旧 main 扫描当成当前修复分支验证。

## 5. 最小验证集

### 5.1 现有结构与局部回归

在仓库根目录运行并记录每个命令退出码；不要仅查看最后一条命令。

```powershell
py -3 scripts/python/validate_task_master_triplet.py
py -3 scripts/python/validate_semantic_review_tier.py --mode conservative
py -3 scripts/python/attest_chapter3_triplet_baseline.py
py -3 -m unittest scripts.python.tests.test_chapter3_semantic_conservation scripts.python.tests.test_semantic_topology scripts.sc.tests.test_project_health_knowledge -q
```

再按本轮实际路径执行 validate_semantic_conservation 的 projection 与 closure，以及 audit_task_candidate_coverage 的当前候选/持久化任务验证。先读取脚本 --help 与调用实现，确认输入正是本轮候选；缺少输入要明确失败，不能拿早期报告替代。

被评审提交曾有 122 项相关单测和三联结构验证通过，仍存在本方案的问题。因此下面的真实数据检查不可省略。

### 5.2 提交快照检查

在候选提交完成后，直接用 GitSnapshot 或 LocalMainSnapshot 的显式候选 ref 调用现有消费者；不要移动真实 main 来假装已经合并。

示例只读检查（PowerShell）：

```powershell
@'
import sys
from pathlib import Path
sys.path.insert(0, "scripts/python")
from _knowledge_catalog_builder import LocalMainSnapshot
from _project_health_tasks import task_details
from _semantic_topology import load_topology_from_snapshot

snapshot = LocalMainSnapshot(Path.cwd(), "HEAD")
view = load_topology_from_snapshot(snapshot, task_details(snapshot), identity_kind="main")
print("Candidate commit:", snapshot.commit)
print("Fresh:", view.get("fresh"))
print("Problems:", view.get("problems"))
print("Summary:", view.get("summary"))
if not view.get("available") or not view.get("fresh") or view.get("problems"):
    raise SystemExit(1)
'@ | py -3 -
```

此处 identity_kind=main 用于在只读候选快照上复现消费者语义，不会发布 Main，也不表示候选已经合并。除了 fresh，还必须检查所有 Task 目标都存在、有效 semantic_refs 均在当前语义集合内、经本轮映射的任务能反查来源块。不要要求每个历史任务都必须已有来源映射。

如果 origin/main 已有新提交，先在隔离合并候选中解决实际差异，再对最终候选树重新执行相同检查。合并后才更新本地 main 并进行正常 Main 页面扫描。

### 5.3 有限反例与幂等检查

围绕本次缺陷检查下列反例。使用临时 fixture/隔离副本，不破坏真实权威文件。

| 反例 | 必须观察到的结果 |
| --- | --- |
| 恢复旧 575 条语义或旧来源哈希 | 消费者报告 stale/concern 或一致性验证失败 |
| 将 Task 边主编号改成未经转换的 INT-* 或不存在编号 | 映射验证失败，不能仅因有一条边就算已承接 |
| 将 Task 490 的历史示例重新标为有效当前需求 | 来源审阅/数据对账明确不通过；不能靠 JSON 合法证明语义正确 |
| 重复执行本轮候选编译与导出 | 不增殖任务、不换号、不覆盖旧生命周期与证据 |
| 有效未实现需求被错误改成 context 或随意挂到 ADR | 审阅拒绝该处置，需求仍需真实承接 |

语义样例需由来源、旧验收与实现对照审阅；测试不能只硬编码“禁止 Task 490”或“任务数必须下降”。只有证实通用脚本缺陷时才补相应行为测试和最小脚本修复，不扩展为全仓门禁重构。

## 6. 完成标准与交付

只有同时满足以下条件才能给出可合并建议：

- 两项 P1 有明确修复结果；433、398、490 的处置可追溯。
- 新增任务均有 reuse/update/create/non-task/retire 等审阅结果，没有未披露的来源误判或重复承接。
- 当前有效来源无未解释遗漏，语义变化有原因；不强行维持原始任务或 Requirement 数量。
- 旧任务信息守恒；新增行为不借旧 done 冒充完成；主编号稳定且取消编号不复用。
- 最终候选 Git 快照的拓扑 available=true、fresh=true，来源哈希与 artifact hashes 通过；任务边解析到实际主编号。
- GDD → 来源块 → Requirement → 主任务的映射能在消费者中实际追踪；仍无来源的历史任务保持明确 unmapped。
- 结构校验、当前语义闭包、持久化任务覆盖、必要反例和幂等验证通过。
- 更新本分支 execution plan/decision checkpoint，解释最终结果；避免正文同时声称“未写任务”和“已闭包”却没有时间/阶段区分。

交付时给出：最终分支与提交、对比最新 main 的变更摘要、任务数及处置统计、上述三个任务的处理证据、最终拓扑摘要、每项验证退出码、仍保留的边界。证据保存在 logs/**，修复代码与最终规划产物按仓库规则提交；无需强制将全部本地运行日志入 Git，但外部复核必须能从提交内容重建关键一致性检查。

本方案不要求恢复可重建的 Godot 索引或默认配置，不要求重新实现游戏功能，也不要求另建新的 MVG。按本次明确缺陷收口后停止扩查，提交供审阅，不自动合并 main。
