---
title: 'Project Health 本地配置驱动扫描'
type: 'feature'
created: '2026-09-07'
status: 'in-progress'
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
- [ ] 配置文件及 CLI：提供默认来源配置、严格校验和独立读取；必要任务/策略来源必须可读取，禁止日志和越界来源。
- [ ] 扫描及任务读取：添加本地 main 对象与无 Git 目录的有界读取路径，移除 fetch/worktree 依赖。
- [ ] 探索查询：使 Catalog、任务和 Impact 使用同一选中内容集合；保留非 handoff 标记及正式校验边界。
- [ ] HTTP 和页面：首次加载配置不依赖 latest；扫描校验当前编辑值；更新按钮和来源标签，明确错误与旧结果。
- [ ] 文档与决策：记录本地来源语义、默认配置、无 Git 内容身份和 Windows 路径行为。
- [ ] 回归测试：覆盖矩阵、main/功能分支隔离、无远程可运行、长文件路径无需检出、配置范围缩小后数据变化及失败不覆盖旧结果。

**Acceptance Criteria:**
- Given 当前分支含与 main 不同任务状态，when 扫描，then 页面显示 main 的状态且没有 fetch、checkout、worktree 子命令。
- Given 无 Git 根目录和有效配置，when 扫描和查询，then 任务及探索结果可用，来源明确为目录摘要。
- Given 页面首次打开且 latest 不存在，when 初始化，then 配置非空；when 配置被清空或损坏并点击扫描，then 明确退出且旧结果不变。
- Given 本仓真实来源，when 扫描完成，then HTTP 状态、任务数、来源身份与选中来源一致，不因未选中的长路径文件失败。

## Spec Change Log

## Design Notes

配置与事实来源分开：配置来自当前本地设置，业务事实来自本地 main 或无 Git 根目录。读取 Git 对象不等于落盘 checkout；探索缓存只保存所需内容与证据，不复制完整仓库。默认配置不得把任意仓库目录或日志作为来源兜底。正式 KCP 发布与冻结流程不变。

## Verification

- `py -3 -m unittest scripts.sc.tests.test_project_health_knowledge scripts.sc.tests.test_project_health_server scripts.sc.tests.test_dev_cli_project_health_commands -v`
- 运行涉及的 Impact 解析回归与 `git diff --check`。
- 重启本项目 8780 服务，实际请求配置、扫描、任务接口；确认任务来自本地 main，配置失败时不执行扫描。证据写入 `logs/ci/`。
- 检查页面初始配置及错误显示；浏览器自动化可用时执行真实按钮回归，否则明确报告验证边界。
