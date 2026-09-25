# Project Health: Knowledge + Impact

## Design → Delivery Topology

The existing loopback service exposes a read-only `/knowledge/topology` view and `/api/knowledge/topology?mode=main|workspace`.

- Main topology is identity/revision-bound to the scanned local `refs/heads/main` snapshot.
- Workspace/Chapter-run topology is preview-only and uses a separate workspace/run identity. It cannot overwrite the main `latest.json`, KCP publication pointer, or runtime-verified main evidence.
- Missing topology artifacts are a valid migration state and render as `legacy_unmapped`; the page does not infer or fabricate Requirement/Capability mappings.
- Capability is optional grouping. Requirements may route directly to Task/global constraint/quality gate/ADR-owned sink.
- The page is read-only and does not create or modify Requirement, Task or Acceptance.
- Scene details may display `Trace to design` through governed Task relationships. The trace is navigation/evidence only and does not convert static/runtime attachment into acceptance proof.
- `Trace to design` entries are clickable node-level links into `/knowledge/topology?focus=<kind>:<id>`. Topology node details expose related-node links so Task/Capability/Requirement/Source Block navigation is reversible.
- Existing task-view `acceptance[]` entries appear as read-only Acceptance nodes even before Chapter 5 semantic-origin edges exist; their `topology_origin` remains `unmapped` until an explicit governed edge is present.
- The Orphan filter consumes the backend `sink_resolved` result; a Requirement that only reaches a Capability with no delivery sink remains visible as orphan.
- Knowledge query candidates that resolve a topology node display its node id/type, related Task ids and original authority source path/hash, with a link into the focused topology view.

The registered structural source is `docs/planning/semantic-topology/**`.

### Chapter 3 / Chapter 5 Workspace refresh

Registered closure producers use the unified Chapter Knowledge refresh hook rather than writing Project Health/KCP state ad hoc.

- Chapter 3 records **Workspace → Last attempt** at run start through `refresh-knowledge --begin-run`, then refreshes it again at run end with available topology/gate evidence. An interrupted run therefore remains visible instead of silently leaving no attempt record.
- Chapter 3 and Chapter 5 both record **Workspace → Last attempt** at run start. Scripted Chapter 5 automation uses `run-chapter5-guarded`, which guarantees the final refresh even when the wrapped child fails. Every Chapter 3/5 run may refresh Last Attempt with its run identity, partial topology, failures and conservation concerns.
- Only closure PASS may advance **Workspace → Latest successful**. Chapter 5 closure additionally requires the current full input fingerprint to match reconciliation/readiness, including semantic requirements, Task/Acceptance/dependency surface, and Overlay/Contract/ADR authority hashes/review.
- For Chapter 3, refresh re-validates the current ledger/semantics/candidates at `stage=closure`, requires the persisted conservation report to match the same source revision/source manifest/blocking counts, recomputes semantic-sink task coverage, and requires a passed triplet-baseline attestation whose hashes match the current three Taskmaster files. A projection-stage, stale, blocked, or mismatched artifact cannot promote Latest Successful.
- Failed/partial attempts never overwrite Latest Successful.
- Stable/planning promotion is failure-atomic: planning topology write failures restore the previous Latest Successful and the previous planning artifacts instead of leaving a partial promotion.
- Attempt/Stable write failures are explicit `knowledge_refresh_failed` concerns with a concrete failure family. A `stable_refresh_failed` result keeps Chapter closure in concern/failed state and canonical publication deferred even if semantic conservation and triplet validation already passed.
- Workspace identity remains `workspace:<digest>` / run-bound and never advances main `latest.json`, runtime-verified main evidence, KCP `current`, or `last-known-good`.
- `publication_deferred` is a normal result for non-main/dirty/non-publishable runs and does not by itself fail Chapter 3.
- The topology page exposes Workspace `Last attempt / Latest successful / Latest Chapter 5 stabilized` views. `Latest successful` remains the cross-producer closure view, while `Latest Chapter 5 stabilized` preserves the last Chapter 5 reconciliation/readiness closure even if a later Chapter 3 run succeeds.
- Canonical publication remains trusted-ref/main-only. Recovery, Chapter 6, Review and ordinary consumers must not use publication as an implicit repair action.

Unified entrypoint:

```powershell
py -3 scripts/python/dev_cli.py refresh-knowledge --source chapter3 --trigger-run-id <run-id> --refresh-local --triplet-status <passed|blocked|unknown>
```

Use `--write-planning-artifacts` only after closure PASS to promote stable topology files under `docs/planning/semantic-topology/**`; use `--publish-if-eligible` only when trusted-ref publication is intended.



## MVG 与 Chapter 3 的展示边界

| 需要查看的关系 | 当前入口 | 能证明什么 |
| --- | --- | --- |
| Chapter 3 来源 → Requirement → 可选 Capability → Task → Acceptance | `/knowledge/topology`，Main 或 Workspace | 来源与交付映射；Chapter 3/5 的 Attempt/Successful/Stabilized 状态 |
| Task → Scene/Script/Test 与任务运行结果 | `/knowledge/` 任务详情及验证按钮 | 对应任务及所选 revision 的局部证据 |
| MVG → Flow → Handoff owner → Tasks/Tests → 同版本运行结果 | `/knowledge/scenes` 的 GDD versions and cumulative playability、`/api/knowledge/mvg-overview`、manifest 与运行摘要 | 展示当前 main 的累计流程、责任边界与精确匹配当前 revision/manifest 的运行状态；人工试玩另行确认 |

`Verify local main`、`Verify workspace`、`Verify selected` 和 `Audit all gameplay tasks` 仍是任务验证能力；全部任务局部验证成功不能替代 MVG manifest 的整合运行。Source/Requirement/Task 拓扑也不自动生成 MVG flow 或 handoff。`m1-critical` 与 `m1-full` 的范围和阻断任务以选定 manifest 为准，不能从页面绿色状态推断 full-MVG 已通过。

`/knowledge/scenes` 按 Chapter 3 来源集列出 GDD 候选版本，版本身份为 GDD 路径加当前 main 内容 SHA-256。只有已发布、fresh、与扫描 main 同 revision 的语义拓扑中，来源块哈希和 Taskmaster 主编号同时对得上，页面才展示该版本关联的任务及其 Overlay/Contract/ADR 引用。场景、Node 和资源只经任务已验证的静态脚本附着关联，不能推断由该版本创建，也不证明运行时可达或可玩。未发布拓扑时 GDD 标为 `unmapped`，不会按名称或 Git 时间猜测归属；旧 GDD 的历史修订需要另外发布来源证据，当前 main 单一扫描无法复原。

MVG manifest 仍是跨 GDD 版本的累计范围。页面列出每条 flow 的任务、handoff、owner、契约、测试与关联的所有已追踪版本；未归属任务仍留在累计清单内。只有运行摘要的 manifest 内容哈希、main revision、运行模式与干净快照全部一致且 `runtime_verified=true`，才显示 `passed`。阻断任务、动态路线和主观试玩须单独核对；视图本身不写任务或验收状态。

## Godot 场景图投影

Knowledge 页面提供只读 Godot 场景图。扫描从 `project.godot` 的 `application/run/main_scene` 开始，确定性解析 `.tscn`、`.cs`、`.gd` 与资源路径，结果绑定扫描 revision 并通过 `/api/knowledge/scene-graph` 提供。循环使用 visited 集合终止；动态加载标记为 `dynamic-unknown`，未确认入口标记为 `unreachable-candidate`，不等同于运行时绝对不可达。用户浏览不调用大模型、不执行游戏或修改源文件。页面支持场景树、未确认场景列表及 Node/脚本/资源详情。

素材列表中的 PNG/JPEG/WebP 相对路径支持悬停预览与点击打开图片。图片接口按导航 revision 读取 Git blob，要求路径属于扫描素材清单，单图最大 16 MiB；目录摘要及其他格式暂不提供图片预览。任务 18（战斗场景 UI 与绑定）可在 `More associations → Assets` 查看卡图及敌人图线索。

任务详情默认仅列出明确任务来源、映射场景、附着脚本及直接配置/素材引用。集成测试环境、间接依赖和共享 ID 候选保留在默认折叠的 `More associations`；完整 JSON 与解析限制位于 `Original task and evidence`。配置默认仅列有明确记录 ID 匹配的字段，无法定位记录时保留源码入口。节点属性及引用证据按需展开。运行状态、失败原因和验证按钮保持可见。

这是 workflow 2.4 现有本地服务下的二级页面 `/knowledge/`，不是第二个服务，也不改 chapter 3–7 的技能调用协议。

## 启动与使用

```powershell
py -3 scripts/python/dev_cli.py serve-project-health
```

打开输出 URL，在首页点击 `Knowledge + Impact`。首次点击 `Scan local main`。旧版纯静态服务不会被误复用；新服务选择另一个空闲端口，不强行结束旧进程。

扫描只读取本地 `refs/heads/main` tree，不 fetch、checkout 或建立 worktree。无 Git 时读取配置指定的目录范围并使用内容摘要身份。不会读取当前功能分支或修改任务。页面显示完整来源身份与扫描时间；失败保留上一次成功结果。

1. 在顶部输入中文需求、英文符号或文件路径，选择知识 consumer，点击查询。
2. 查看知识候选位置、GDD 补充来源及实际执行的 query。候选可点击打开该 main 快照原文。
3. 点击一个精确 Impact target，查看关联文件、场景绑定、测试线索、风险与解析遗漏。自然语言不直接充当 symbol ID。
4. 查看任务列表；每页固定 20 条，顶部与底部都有首/前/后/末页、页码输入跳转。点击 id 展开完整任务及映射附加字段。
5. 根据证据形成修改范围与回归测试建议，再用 prompt 串回现有 chapter 流程。

## 任务修改导航

点击任务 ID 后，在完整原始详情之前显示配置、代码、场景节点、素材和建议验证五个分区。配置 JSON 字段给出精确 JSON Pointer、当前值、值所在行列与原文；可展开同一 main 快照源码，使用 `Back to task navigation` 返回。读取位置仅是静态引用线索，生效时机需要查看 reader，不能推断自动热更新。

导航按请求构造，扫描仅缓存限定文本与素材路径清单。配置限定为 JSON、TRES、CFG、INI、CSV、YAML；非 JSON 不推断字段。素材只展示路径和使用线索，不通过源码接口公开二进制。未扫描的引用明确标注；目录模式仍按内容摘要绑定，Git 模式始终读取同一个 main revision。

节点属性可以追踪 ExtResource/SubResource 和跨 TRES 资源链，并识别场景 instance 引用；循环与深度有界。动态赋值、实例内部覆盖及运行创建节点仍可能无法定位。`static_reference` 为直接文本引用，`static_candidate` 为测试符号或共享卡 ID 关联，所有素材均保留 `runtime_observed=false`，即使任务已有通过的运行测试。

T24 可从声明测试、服务符号和共享卡 ID 找到初始牌组数据候选；T115 可看到 Reward 场景节点、动态纹理脚本线索及素材。测试命令明确标为 `suggested_not_executed`，不会自动运行。JSON 5+4+1 与旧服务十张独立卡不能互换；卡池也存在未统一的范围差异，参见 `decision-logs/2026-09-08-project-health-configuration-audit.md` 和对应 execution plan。

新增回归：`py -3 -m unittest scripts.sc.tests.test_project_health_navigation -v`；本次证据：`logs/ci/2026-09-08/modification-navigation/`。

导航源码链接同时校验响应 revision；若其他页面已重新扫描，拒绝混用不同快照并提示重新打开任务。来源链、反向字面引用与素材使用线索中的已扫描文本路径也可点击，原始行号保留。资源属性支持多行数组/字典；深度、展开数量、资源循环和缺失引用均显示未解析原因。目录模式仍省略超过 4 MiB 的文件，包括大素材；Git 的素材路径清单没有此大小限制。建议测试筛选器由文件名生成，执行前应核对实际测试类型与匹配数量，零测试不能视为验证通过。

## Gameplay 运行时验证

任务详情提供 `Verify local main` 和 `Verify workspace`。main 模式从扫描 commit 导出独立副本，一批任务共用一个副本串行执行；未提交工作区修改不再阻挡 main 验证。workspace 模式复制当前 Git 跟踪文件及未忽略的新文件，记录 SHA-256 清单，以 `workspace:<digest>` 标识实际运行输入。工作区测试选择仍使用已扫描任务的测试引用，修改任务引用后应先更新任务来源。

两种模式都只在副本中生成导入、编译与测试产物。副本、输入清单和测试报告保留于 `logs/ci/project-health-knowledge/runtime/` 供审阅，不自动删除。默认忽略的本地依赖不会被复制，构建应从源码和锁定依赖恢复。main 结果写 `runtime/latest.json`；工作区结果单独写 `runtime/workspace-latest.json`，不能产生或覆盖 main 的 `runtime_verified`。页面显示最近一次工作区快照的时间、内容身份和结果，并不宣称其适用于后续编辑。

批次锁覆盖 CLI 和页面调用。全局超时包含副本准备；任务超时终止该运行器的进程树。main 通过要求有效任务报告、正数测试计数、零失败错误，以及运行结束时输入未变化、main 与 scan revision 一致。源码路径不会切换、stash、checkout 或要求先提交。

CLI：`py -3 scripts/python/project_health_runtime.py --godot-bin "$env:GODOT_BIN" --task-id 18 --mode main`；将 `main` 改成 `workspace` 可验证工作区快照。

`Verify gameplay runtime` 是独立操作，不会在普通 main 扫描中自动启动 Godot。运行前必须设置 `GODOT_BIN`，批量任务默认串行执行，并同时受单任务超时和全局超时约束。只有扫描任务中存在且能定位到扫描源的 `Tests.Godot/**` 测试文件或目录才会启动；仅有 Godot/GdUnit 策略线索或人工场景映射的任务记录为 `runtime_unverified`。

每项证据写入 `logs/ci/project-health-knowledge/runtime/`，包含 task id、扫描 main revision、测试路径、场景、状态、起止时间及失败原因。页面状态按 `runtime_verified > static_attached > candidate > unmapped` 合并；运行失败且静态接入成立时显示 `runtime_failed_static_attached`。`runtime_verified` 还要求运行输入与扫描的 local main 内容一致、证据字段完整且执行期间 scan revision 未变化。无 Git 目录摘要不能产生 `runtime_verified`。

任务详情中的 `Verify this task runtime` 可定向验证一个任务。同一扫描 revision 下，定向结果只替换该 task id 的旧证据并保留其他任务证据；批量验证会替换该 revision 的运行时索引。

任务表支持跨分页多选。`Select page` 选择当前页，`Clear selection` 清空全部选择，`Verify selected` 只验证已选且具备运行资格的任务。顶部 `Verify eligible runtime tasks` 遍历已有任务级 Godot 证据线索的任务；`Audit all gameplay tasks` 遍历 `tasks_gameplay.json` 中所有能映射到主任务的任务。有任务级 GdUnit 引用时执行测试，否则写入 `runtime_unverified` 证据并保留静态或 candidate 状态。任务运行、扫描或查询期间，服务公开只读 operation 状态，页面据此锁定全部交互；其他已打开页面也会通过轮询进入锁定状态。

全量脚本入口：`py -3 scripts/python/project_health_runtime.py --repo-root . --godot-bin "$env:GODOT_BIN" --all-gameplay`。

## 配置与来源

页面配置编辑器使用内置默认值；独立加载不依赖扫描结果。点击扫描先校验并保存编辑器当前配置，再扫描；配置为空、损坏、越界或必要来源缺失时退出并保留旧结果。配置文件为 `scripts/python/project_health_knowledge_config.json`。

配置编辑器直接显示在页面中，不需要展开折叠面板。`Save local configuration` 只保存配置，`Scan local main` 才会用新配置重建扫描结果。状态统计项可点击并在服务端分页前筛选任务列表；再次点击当前统计项或使用 `Clear filter` 恢复全部任务。

- `source_paths`: 明确的文件或目录范围；默认包含任务三联、PRD/GDD、架构、契约、运行时和测试。`docs/planning/semantic-topology` 是固定的可选结构源：main 尚未包含时显示 `legacy_unmapped`，不会作为缺失配置阻断扫描。禁止根目录、logs、Git 元数据和越界路径。扫描与探索查询共享同一内容集。

- `gdd_paths`: 多个仓库相对路径，支持 UTF-8 `.md` / `.txt` / `.json`。路径必须存在于扫描的 main；不支持任意本地绝对路径、PDF/DOCX、软链接或浏览器任意文件读取。缺失项会显示为不可用。
- `query_aliases`: 中文术语到短查询数组。每个别名作为独立 query 执行，原始输入保留。默认提供奖励/Reward、存档/Save、战斗/Combat；不是自动翻译或跨语言向量检索。
- `task_scene_bindings`: 人工审查的 task 与场景节点/脚本/实现标记映射。扫描验证其结构，无法自动证明设计语义。

GDD 配置真正参与补充检索，但不会悄悄改变 KCP consumer policy、全局索引发布或 freeze 权威。位于既有 KCP 路由中的 GDD 也可正常成为知识候选。任意路径 GDD 显示为 supplementary-design-source，不能直接冒充正式冻结上下文。

## SSOT 合并

任务列表与计数只读 `tasks.json.master.tasks[]`。通过 `tasks_back[].taskmaster_id` / `tasks_gameplay[].taskmaster_id` 关联视图；相同字段名从映射输出中剔除，完整保留 tasks.json 的值，包含 null/空值。两个视图的独有字段分别展示，不互相覆盖。视图 id 与 SSOT id 同名，因此按要求不再显示其值；映射来源由 tasks_back / tasks_gameplay 容器标识。

## Godot 能做到什么

| 状态 | 证据 | 不能据此声称 |
| --- | --- | --- |
| static_attached | 明确任务声明 + 真实 `.tscn` 节点 script 赋值 + 脚本中实现标记存在 | 已运行、业务正确、验收通过 |
| candidate | 任务 test_refs 等指向的测试直接引用生产场景 | 场景已实现这个任务 |
| unmapped | 当前规则未找到对应关系 | 功能不存在 |

默认以任务 115 为可审查的映射实例：`Reward.tscn` 根节点挂载 `RewardScene.gd`，脚本含 `_claim_reward(...)` 实现。该声明只认定静态接入，并非重新验收任务 115。节点路径 `.` 表示根节点。配置失效会列入 invalid_declarations，不继续标记静态接入。

当前不推断任意 C# 调用链、动态 GDScript 调度、运行时创建 Node、autoload 可达性、继承场景覆盖或资源反射；也不因 `status=done`、同名词、契约引用或测试通过就认定已实装。若要提高覆盖率，应逐任务补经过审查的映射；运行验证需另接带 main SHA 的实际 Godot 执行证据。

## 查询与正式交接的边界

前置查询复用知识 builder/locator、Impact target resolver 与分析规则，从同一选定内容集构造探索视图，不创建正式 immutable index。页面结果采用单独 preview schema，`handoff_eligible=false`。不会自动 accept/freeze、publish、restore 或调用 codex exec。

轻量 C# 解析器无法识别部分方法参数。探索模式跳过这些方法并输出路径/行号/原因，仍保留其他证据；正式 analyzer 继续严格失败，而且探索实例不能生成正式报告。页面的 published pointer matches 只比较提交号，不等于对 publication envelope 的完整验证。

正式交接依然使用现有 `prepare_knowledge_context.py`、候选语义选择、`freeze_knowledge_context.py`、`analyze_impact.py` 与 handoff 校验。此页面不替代这些入口。

## CLI 与证据

```powershell
py -3 scripts/python/project_health_knowledge.py scan
py -3 scripts/python/project_health_knowledge.py status
py -3 scripts/python/project_health_knowledge.py tasks --page 2
py -3 scripts/python/project_health_knowledge.py task --task-id 115
'{"query":"奖励确认","consumer":"repository-session"}' | py -3 scripts/python/project_health_knowledge.py query
'{"query":"RewardScene","target":{"type":"file","id":"Game.Godot/Scripts/RewardScene.gd"}}' | py -3 scripts/python/project_health_knowledge.py query
```

证据与缓存在 `logs/ci/project-health-knowledge/`。成功扫描写 latest.json，查询保存独立 JSON。快照不会自动删除，避免销毁历史证据；占用空间随 main 版本数量增长。中断后如果遗留 scan.lock，确认没有正在运行的扫描进程后再人工移除该空锁目录。

服务只绑定 127.0.0.1；Host 检查、同源 Origin、会话 token 和固定 CLI 参数约束写入口。API 不接受任意命令、分支、快照路径或网页指定输出文件。只允许打开扫描 allowlist 内的源码文本，不提供编辑器 OS 命令或任意文件下载。

测试：`py -3 -m unittest discover -s scripts/sc/tests -p "test_project_health*.py"`；Impact 回归：`py -3 -m unittest discover -s scripts/python/tests -p "test_impact_analyzer.py"`。
### Chapter 6 resource knowledge

Chapter 6 is a **read-only global Knowledge consumer**. Global Project Health scans, task-resource link generation, catalog rebuilds, and KCP publication are explicit maintainer operations outside the Chapter 6 execution/recovery path.

The Chapter 6 capture command is task-local only:

```powershell
py -3 scripts/python/dev_cli.py chapter6-knowledge --task-id 18
```

It reads already-available Project Health/resource evidence when present and writes candidates under `logs/ci/chapter6-knowledge/task-18/`. It does **not** call `project-health-scan`, `generate-knowledge-links`, `init-knowledge-catalog`, `refresh-knowledge`, or `publish_knowledge_catalog.py`; it does not modify Taskmaster knowledge refs and does not advance KCP `current` / `last-known-good`.

The legacy `--write-task-refs` flag is rejected. If a maintainer explicitly wants to rebuild resource links/catalog or publish global Knowledge, run those commands separately outside Chapter 6 and record that maintenance action as explicit/manual.

### Chapter 6 element capture

`chapter6-knowledge` writes `logs/ci/chapter6-knowledge/task-<id>/knowledge-capture-candidate.json` plus task-local `documentation-gaps.md`. The capture records changed or previously linked Godot scenes, scripts, configs, and assets with `verified`, `inferred`, or `unmapped` status. Scene/static evidence remains evidence only; it must not be promoted to Acceptance proof or global Knowledge automatically.
