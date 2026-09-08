---
title: 'Project Health 本地配置驱动扫描'
type: 'feature'
created: '2026-09-07'
status: 'done'
baseline_commit: '68d6d28b0361d116b18740b372c24a888ccdc142'
review_loop_iteration: 0
context: []
---

<frozen-after-approval reason="human-owned intent">

## Intent

当前扫描先拉远程 main、在深目录完整检出 worktree，导致 Windows 长路径阻断任务刷新。页面配置加载又依赖成功扫描，首次失败时无法看到已有默认配置。

改为仅从本地来源读取，并由有效配置决定后续扫描。Git 仓库绑定本地 main 提交；无 Git 仓库读取指定根目录。取消 fetch 和完整 checkout。配置先独立加载和校验，然后扫描，成功后才替换页面结果。

## Boundaries & Constraints

**Always:** Git 模式读取本地 refs/heads/main 的提交对象，不读取当前功能分支或未提交业务文件。无 Git 模式标识来源为目录，并用选中内容的摘要标识结果，不伪造 Git 提交。默认配置可直接显示，已有错误配置不得被默认值悄悄覆盖。任务主状态以配置指向的 tasks.json 为准，视图只补映射。保留同源、token、路径边界、单操作锁和失败保留旧结果机制。

**Ask First:** 需要改变正式 Impact、KCP publication 或 freeze 的校验契约时暂停，不借此次探索页面改动放宽正式门禁。

**Never:** 拉远程、切分支、创建 worktree、完整检出、读取配置范围外的业务源、将 logs 当作知识源、自动接受候选、把探索结果用于正式 handoff、自动提交推送。

## I/O & Edge-Case Matrix

| 场景 | 输入 | 行为 | 错误处理 |
|---|---|---|---|
| Git 来源 | 本地 main 存在 | 固定提交，按配置从 Git 对象读取 | 当前分支和工作区不改变 |
| Git 无 main | 仓库存在但无本地 main | 退出 | 不回退到 HEAD 或远程 |
| 无 Git | 独立根目录 | 仅读取配置选中的本地文件 | Git 不可用与仓库损坏不得误当无 Git |
| 首次访问 | 尚无扫描结果 | 仍展示默认配置 | 提示尚未扫描，配置仍可编辑 |
| 配置缺失 | 未创建配置文件 | 使用内置默认配置 | 不自动写入业务文件 |
| 配置无效 | 空白、空对象、错误 JSON、非法路径或缺失必要来源 | 扫描前退出 | 显示具体错误，不刷新成功时间 |
| 修改配置 | 编辑后点击扫描 | 先校验并应用编辑值，再扫描 | 不悄悄使用旧配置 |
| 扫描失败 | 任意中间步骤失败 | 保留上次完整结果 | 不把旧数据标为新结果 |

</frozen-after-approval>

## Code Map

- `scripts/python/project_health_knowledge.py`: scan 当前依赖 fetch/worktree；CLI 的非 scan 分支先读 latest.json，导致配置无法独立加载。query 当前依赖持久化 index 和 snapshot 路径。
- `scripts/python/_project_health_tasks.py`: task_details 当前从磁盘固定目录读取三联，需要接入选定来源和配置路径。
- `scripts/python/_knowledge_catalog_builder.py`: GitSnapshot 和 build_layers 可复用的提交读取、分类和 projection 逻辑。
- `scripts/python/impact_analysis_index.py`, `scripts/python/impact_analyzer.py`: 正式索引要求 Git identity；探索分支应复用解析能力而不伪造正式索引身份。
- `scripts/python/_project_health_http.py`: 固定路由、token、操作锁；增加独立配置读取入口。
- `scripts/python/project_health_knowledge_config.json`: 已有 GDD、scene binding、query aliases 默认值；扩展来源范围与任务路径声明。
- `scripts/python/project_health_knowledge.js`, `.html`: 初始化依赖 loadStatus；扫描按钮文案含 Fetch，需同步实际行为。
- `scripts/sc/tests/test_project_health_knowledge.py`: 现有 HTTP、任务和探索行为回归入口。
- `docs/adr/ADR-0036-project-health-investigation.md`: 当前 Proposed 决策写明 fetch/worktree，需对齐新方案。

## Tasks & Acceptance

**Execution:**
- [x] 配置文件及 CLI：提供默认来源配置、严格校验和独立读取；必要任务/策略来源必须可读取，禁止日志和越界来源。
- [x] 扫描及任务读取：添加本地 main 对象与无 Git 目录的有界读取路径，移除 fetch/worktree 依赖。
- [x] 探索查询：使 Catalog、任务和 Impact 使用同一选中内容集合；保留非 handoff 标记及正式校验边界。
- [x] HTTP 和页面：首次加载配置不依赖 latest；扫描校验当前编辑值；更新按钮和来源标签，明确错误与旧结果。
- [x] 运行时任务筛选：以 `tasks_gameplay.json` 为候选集合，按 `taskmaster_id` 去重；只有任务级 `Tests.Godot/**` 引用、明确的 Godot/GdUnit 验收或测试策略、或经审查的场景映射才进入运行时资格判断，且 `Game.Core.Tests/**` 不得产生 `runtime_verified`。
- [x] 分层验证与状态合并：默认串行执行有任务级断言的 Godot/GdUnit 测试；通过且证据完整并绑定当前本地 main SHA 时标记 `runtime_verified`。未通过或不具备运行资格时继续静态检测，再依次落到 `static_attached`、`candidate`、`unmapped`；运行失败且静态接入有效时显示 `runtime_failed_static_attached`。
- [x] 运行证据与止损：运行时验证不得修改任务文件或游戏源文件，只向 `logs/**` 写证据；任务证据至少包含 task id、main revision、测试路径、场景、状态、起止时间和证据路径。设置单任务超时与全局超时，默认串行，失败原因必须在页面和 JSON 中可见。
- [x] 独立验证入口：页面保留单独的 `Verify gameplay runtime` 按钮和 `/api/knowledge/runtime` 接口，不把运行验证混入普通 main 扫描，并支持单任务定向验证。
- [x] 文档与决策：记录本地来源语义、默认配置、无 Git 内容身份和 Windows 路径行为。
- [x] 回归测试：覆盖矩阵、main/功能分支隔离、无远程可运行、长文件路径无需检出、配置范围缩小后数据变化及失败不覆盖旧结果。

**Acceptance Criteria:**
- Given 当前分支含与 main 不同任务状态，when 扫描，then 页面显示 main 的状态且没有 fetch、checkout、worktree 子命令。
- Given 无 Git 根目录和有效配置，when 扫描和查询，then 任务及探索结果可用，来源明确为目录摘要。
- Given 页面首次打开且 latest 不存在，when 初始化，then 配置非空；when 配置被清空或损坏并点击扫描，then 明确退出且旧结果不变。
- Given 本仓真实来源，when 扫描完成，then HTTP 状态、任务数、来源身份与选中来源一致，不因未选中的长路径文件失败。
- Given `tasks_gameplay.json` 中存在重复 id、纯治理任务、仅 Core 测试任务和 Godot 任务，when 选择运行时候选，then 按 `taskmaster_id` 去重，只运行具备任务级 Godot/GdUnit 断言的任务，且仅 Core 测试不会产生运行时通过状态。
- Given 任务级 Godot 测试通过，when 证据的 main SHA 与当前本地 main 一致且必需字段完整，then 页面显示 `runtime_verified`；任一条件缺失时不得显示该状态。
- Given 任务级 Godot 测试失败或超时，when 静态场景、节点、脚本和 witness 匹配，then 页面显示 `runtime_failed_static_attached` 并保留失败原因；静态匹配失败时继续降级到 `candidate` 或 `unmapped`，同时保留 `runtime_failed` 或 `runtime_unverified` 证据字段。
- Given 用户点击 `Verify gameplay runtime`，when 批量验证执行，then Godot 任务默认串行且受单任务与全局超时约束，只写 `logs/**`，不修改任务三联或游戏源文件。

## Design Notes

配置与事实来源分开：配置来自当前本地设置，业务事实来自本地 main 或无 Git 根目录。读取 Git 对象不等于落盘 checkout；探索缓存只保存所需内容与证据，不复制完整仓库。默认配置不得把任意仓库目录或日志作为来源兜底。正式 KCP 发布与冻结流程不变。

运行时状态采用证据优先级 `runtime_verified > static_attached > candidate > unmapped`。运行失败不是一个可被降级隐藏的状态修饰：静态接入同时成立时使用 `runtime_failed_static_attached`，否则在最终静态状态旁保留结构化 `runtime_failed`。没有任务级运行测试时记录 `runtime_unverified`。Godot 进程启动成功本身不构成任务通过，必须由任务级 GdUnit 断言的退出结果证明。

`tasks.json` 与两个视图文件仍属于扫描和任务详情的三联来源；批量运行时验证的候选主集合仅使用 `tasks_gameplay.json`。`tasks_back.json` 不参与启动 Godot，但仍参与 SSOT 映射展示和一致性审查。

## Spec Change Log

- 2026-09-08：补充 gameplay 运行时验证的候选筛选、revision 绑定、证据完整性、失败可见性、分层状态、串行与超时策略，以及独立页面入口。
- 2026-09-08：补充跨分页任务多选、选中任务批量验证、明确的全量遍历文案、批次摘要，以及跨页面 operation 锁定。

## Verification

- `py -3 -m unittest scripts.sc.tests.test_project_health_knowledge scripts.sc.tests.test_project_health_server scripts.sc.tests.test_dev_cli_project_health_commands -v`
- 运行涉及的 Impact 解析回归与 `git diff --check`。
- 重启本项目 8780 服务，实际请求配置、扫描、任务接口；确认任务来自本地 main，配置失败时不执行扫描。证据写入 `logs/ci/`。
- 检查页面初始配置及错误显示；浏览器自动化可用时执行真实按钮回归，否则明确报告验证边界。

## Suggested Review Order

**运行证据与状态边界**

- 从候选筛选到 revision 绑定、超时和证据合并的主流程。
  [`project_health_runtime.py:158`](../../scripts/python/project_health_runtime.py#L158)

- 运行前核对当前 Godot 输入与扫描 main，防止错误归因。
  [`project_health_runtime.py:131`](../../scripts/python/project_health_runtime.py#L131)

- 页面状态只接受完整、同 revision 且文件一致的运行证据。
  [`project_health_knowledge.py:182`](../../scripts/python/project_health_knowledge.py#L182)

**服务与页面入口**

- 独立 runtime 路由负责 GODOT_BIN、任务参数和宿主超时。
  [`_project_health_http.py:124`](../../scripts/python/_project_health_http.py#L124)

- 批量与单任务按钮共享受控验证接口并展示失败原因。
  [`project_health_knowledge.js:47`](../../scripts/python/project_health_knowledge.js#L47)

- 操作说明定义状态语义、证据位置与定向验证行为。
  [`project-health-knowledge.md:21`](../../docs/workflows/project-health-knowledge.md#L21)

**回归证据**

- 输入漂移测试锁定 feature/main 隔离和 fail-closed 行为。
  [`test_project_health_knowledge.py:133`](../../scripts/sc/tests/test_project_health_knowledge.py#L133)

- HTTP 测试覆盖缺失环境变量、task_id 转发和长时预算。
  [`test_project_health_knowledge.py:444`](../../scripts/sc/tests/test_project_health_knowledge.py#L444)
