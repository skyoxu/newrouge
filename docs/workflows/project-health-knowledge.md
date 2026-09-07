# Project Health: Knowledge + Impact

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

## 配置与来源

页面配置编辑器使用内置默认值；独立加载不依赖扫描结果。点击扫描先校验并保存编辑器当前配置，再扫描；配置为空、损坏、越界或必要来源缺失时退出并保留旧结果。配置文件为 `scripts/python/project_health_knowledge_config.json`。

- `source_paths`: 明确的文件或目录范围；默认包含任务三联、架构、契约、运行时和测试。禁止根目录、logs、Git 元数据和越界路径。扫描与探索查询共享同一内容集。

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
