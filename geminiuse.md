# Antigravity 与 Gemini 专属编排、模型路由及上下文优化规范

> **运行时专属声明（重要）**：
> - 本文件（`geminiuse.md`）**仅适用于 Google Antigravity（Web / Remote Conversations / IDE / 官方 `agy` CLI）与 Gemini CLI 智能体会话**。
> - **Codex（Codex CLI / Codex App Server）、Claude Code 以及其他非 Antigravity / Gemini 智能体必须完全忽略本文件的全部内容**，仍严格按根 `AGENTS.md`、`CLAUDE.md` 与 `workflow.md` 执行。
> - **父子角色自检铁律（防自指死锁与递归派生）**：凡上下文含 `<subagent_reminder>` 或任务包首行标有 `[ROLE: LEAF_SUBAGENT]` 的会话，一律判定为**叶节点子代理（Leaf Subagent）**——必须直接执行被委派的编码、修改或测试任务，**严禁拒绝编码，严禁再次调用 `invoke_subagent` 或 `agy` 派生孙代理**；两者皆无的主交互会话方为**父 Agent（Parent Orchestrator）**。
> - **跨平台环境作用域边界（对齐 `AGENTS.md` Windows 基线）**：本文中 `/home/antigravity/...` 路径与 GNU `timeout -k 10s 420s` 均明确标注为**仅限云端 Linux 沙盒（`exebox`）宿主瞬态调度外壳**；写入仓库的任何脚本、测试、配置与文档命令仍必须 100% 遵守 `AGENTS.md` 的 Windows 可执行基线（Windows 本机直接调用 `PATH` 中的 `agy` 并用 `py -3` 子进程超时控制）。
> - **与跨会话全局 `/home/antigravity/.gemini/GEMINI.md` 的边界**：仓库根目录的 `geminiuse.md` 受 Git 版本控制，是 `newrouge` 工程编排与 Subagent 管理的权威规范；云端共享目录 `/home/antigravity/.gemini/GEMINI.md`（物理挂载 `/shared/user/.gemini/GEMINI.md`）仅作为新临时虚拟机未检出工作分支前的底层防假死安全兜底与指向本文件的路由锚点。两者均严格受限于平面 A 工程编排，按 `docs/adr/ADR-0063-multi-model-routing-and-gemini-isolated-runner.md` 与平面 B 物理无工具隔离运行器彻底隔绝。

---

## 1. 父子分层编排与模型/思考深度路由规则

### 1.1 父 Agent（Parent Orchestrator）职责与模型定位
1. **保持最高模型与最高思考深度**：父 Agent 必须始终运行在当前会话可用的**最高阶模型与最高思考深度**（如 `Gemini 4 Carbon (High)` / `EFFORT LEVEL: 1.00`；若远端聊天窗口暂未开放特定档位，则保持远端界面允许的最高阶 Carbon 档位）。
2. **纯调度、轻量只读策展与 Git 写权限收口**：
   - 父 Agent 只负责：全局阶段拆解、为每个子任务精准组织最小上下文包、派发 Subagent、核验回传结果摘要、决定并执行 Subagent 关闭、维护全局进度与向用户汇报。
   - **轻量只读策展白名单与 Git 唯一写入口**：父 Agent 允许直接执行**同回合 `<= 5` 个文件的并行只读查看**（用于精准组装行号上下文包与验收产物）以及 **`git status` / `git diff` / `git commit` / `git push` 与未提交补丁备份**；所有 Git 写操作统一收归父 Agent，防止子代理超时强杀遗留 `.git/index.lock`。
   - 父 Agent **严禁**直接修改业务、测试或规范文件，**严禁**直接运行构建与测试套件，也严禁执行全仓无过滤大扫描。

### 1.2 Subagent 模型选择与禁令（平面 A 工程子代理）
1. **默认主力模型：`gemini-4-hydrogen-high`**
   - 所有常规工程 Subagent **默认一律使用 `gemini-4-hydrogen-high`**（云端 Linux 沙盒通过 `/home/antigravity/.local/bin/agy`、Windows 本机通过 `PATH` 中的 `agy` 独立无头进程派发）。
   - 标准无头非阻塞调用模板固定为：
     ```bash
     agy --model gemini-4-hydrogen-high --dangerously-skip-permissions --disable-slash-commands --output-format stream-json --print "<prompt>"
     ```
     其中 `--print` 为带参标志，必须紧邻 `"<prompt>"` 置于命令末尾；**严禁传入 `--continue` 或 `--conversation`**。外层必须将原始 `stream-json` 完整落盘至 `logs/subagents/<task-id>.stream.jsonl`，仅解析提取 `event=="result"` 中的 `result.response` 回传父上下文。
   - 适用范围：环境初始化与工具链搭建（Stage 0）、定向代码/日志调研、有明确规格或补丁线索的代码与单测实现、按批次运行单测与常规报错修复、文档同步与 UTF-8/EOL/字节码门禁检查（不包含 Git 写操作）。
2. **永久禁用 `Argon`（全链路硬红线）**
   - **任何时候、任何角色永远禁止使用 `Gemini 4 Argon`（`gemini-4-argon*`）**。
   - **宿主内置 `invoke_subagent` 映射陷阱警示**：平台内置 `invoke_subagent` 工具中，`Model: "pro"` 底层实际映射为 `Gemini 4 Argon`，`Model: "flash"` 映射为旧版 `Gemini 3.8 Flash`。因此**严禁在 `invoke_subagent` 中传入 `Model: "pro"`、`Model: "flash"` 或 `Model: "flash_lite"`**。
3. **继承父 Agent 最高模型与思考深度的三类受控场景**
   - 仅在以下三类高认知负荷场景下，Subagent 应当且**统一仅通过宿主内置 `invoke_subagent(..., Model="inherit")`** 继承父会话最高模型与思考深度（实测 `agy` 直连 `gemini-4-carbon-high` 会挂起超时，且 `--effort` 与部分模型参数冲突，严禁通过 `agy` 指定 Carbon 模型，亦严禁常规编码/跑测子代理滥用）：
     1. **只读类（`TypeName="research", Model="inherit"`）**：适用于 **Review 与独立审计**（里程碑封板审查、契约与架构红线核验、Code Freeze 保护项审计及修复签收）、**深度任务与长任务规划拆解**（跨多模块复杂根因诊断、70KB 确定性分段边界推导、冷启动协议重放校验、并发状态机分析及跨阶段拆解），以及 **A/B 对抗与交叉质询**（多候选方案优劣辩论、边界条件反例构造与独立挑刺验证）。
     2. **可写升级攻坚类（`TypeName="self", Model="inherit"`）**：仅适用于 `gemini-4-hydrogen-high` 连续 2 次尝试未收敛后的深度代码修复。
   - 审计或攻坚回传摘要首行须如实注明当前生效模型档位。

### 1.3 平面 B 无工具隔离边界（遵循 `ADR-0063`）
- 仓库 B 路线正式阶段（3A 独立来源审计、3B Capability/MVG 候选生成与匿名评审、采纳与补偿审阅）不属于平面 A 工程 Subagent，必须严格通过物理无工具隔离运行器 `scripts/python/gemini_isolated_model_runner.py`（或 `codex_isolated_model_runner.py`）按 `docs/workflows/llm-routing.json` 锁定配置运行，严禁将平面 A Subagent 混入平面 B。
- **在平面 B 隔离运行器执行期间，严禁并发启动宿主 `agy` 子进程**，防止共享 OAuth 令牌刷新写竞态。

---

## 2. 上下文策展隔离与纯结果回传协议

### 2.1 严禁全量上下文继承（按任务定制最小上下文包）
- **禁止全量继承**：每个 Subagent **绝对不允许**继承父 Agent 的完整历史对话或无关任务背景。
- **父 Agent 策展责任**：每次派发前，必须由保持最高模型与思考深度的父 Agent 根据该 Subagent 的具体原子任务，专门提炼组装一份自包含的**任务上下文包（Task Context Packet）**，仅包含：
  1. **单一任务目标与完成判据（Done Criteria）**；
  2. **明确的职责文件范围与禁改红线（Owned Files & Zero-Touch Paths）**；
  3. **精选的权威依据**：直接给出精确文件路径、行号区间或必要的接口/契约摘录（禁止原样粘贴无关整文件）；
  4. **执行护栏与输出格式要求**：超时上限、测试批次范围及证据落盘路径。

### 2.2 仅回传最终结果（机械化纯结果提取与 `logs/**` 唯一归口）
- **纯结果回传契约**：Subagent 向父 Agent 上下文返回的信息**只允许包含精炼的最终结果摘要**（建议 `<= 50` 行 / `<= 2 KB`）：
  - 任务状态（`PASS` / `FAIL` / `BLOCKED`）；
  - 实际变更或核查的文件清单与核心结论；
  - 关键验证命令退出码、耗时与通过数；
  - 完整日志或详细报告在磁盘上的文件路径（统一位于 `logs/**`）。
- **机械化纯结果提取（`agy` 无头子代理）**：外层调用须将原始 `stream-json` 完整落盘至 `logs/subagents/<task-id>.stream.jsonl`，仅解析提取 `event=="result"` 中的 `result.response`（机械截断至 `<= 50` 行 / `<= 2 KB`）回传父上下文，从物理机制上杜绝工具调用流水与思考过程混入父上下文；若遇退出码 `124` 超时，父侧须先清理残留子进程并核查 `git status` / `git diff` 脏现场后再决定重试。
- **只读子代理免除落盘**：`TypeName="research"` 只读子代理因无写盘工具，免除自行落盘义务，直接向父会话回传 `<= 50` 行高密度行号结论（如需归档由父侧代存 `logs/**`）。
- **严禁污染父上下文**：**绝对不允许**将 Subagent 内部的工具调用明细（Tool Call / Tool Output 原始流水）、大段标准输出刷屏、完整源码重贴或中间思考推理过程（Reasoning / Thought Trace）回传注入父 Agent 上下文。

---

## 3. 工具调用合并与 Harness 上下文优化规范

### 3.1 强制合并工具调用（严禁逐个串行调用）
- **绝对禁止碎片化单步调用**：严禁“一回合只看一个目录、下一回合只读一个文件、再下一回合跑一条小命令”的逐个工具调用模式；每增加一轮工具往返都会触发整段上下文重复 Prefill，造成严重的上下文膨胀与超时风险。
- **同回合并行读取**：当已知需要核查多个文件或不同行段时，必须在**同一回合内并行发起多个只读调用**，或通过单条只读聚合脚本一次性提取所有目标定位信息。
- **原子命令打包执行**：同一逻辑步骤内的环境准备、路径检查、编码/无 Emoji/无字节码校验、定向单测与状态核对，必须合并为**单条结构化脚本命令**一次执行并返回汇总指标。

### 3.2 标准输出预算与检索编辑收敛（Harness 常规优化）
1. **终端输出静音与 `logs/**` 唯一证据目录**：构建、测试、审计与子代理原始流日志**一律写入 `logs/**`**（严格对齐 `AGENTS.md`“日志、审计和证据统一放在 `logs/**`”）；返回到工具标准输出的内容必须经过裁剪（仅保留末尾汇总与首个报错堆栈，控制在 `80` 行以内），严禁把几千行正常通过日志直接打进上下文。
2. **精准检索替代盲目全仓扫描**：代码搜索必须限定目标子目录（如 `scripts/python/`、`Game.Core/`）、精确符号名与返回行数上限（`head -n`），避免匹配海量归档或测试夹具噪音。
3. **最小范围增量编辑**：修改现有文件优先使用精确行号区间替换，禁止无必要地整文件重写消耗输出窗口；同一回合对不同文件的独立修改应批量提交，对同一文件的相邻修改合并为单块替换。
4. **保持字节码洁净与瞬态目录边界**：所有 Python 调用强制设置 `PYTHONDONTWRITEBYTECODE=1` 并传 `-B`，确保主仓与沙盒零 `__pycache__` / `.pyc` / `.pyo`；云端绝对路径 `/home/antigravity/.gemini/jetski/brain/<conversation-id>/scratch/` **仅限存放瞬态任务上下文包与未提交防丢补丁**（严禁使用相对路径 `scratch/` 污染仓库根目录，严禁在仓库根目录遗留未跟踪临时文件）。

---

## 4. Subagent 单次生命周期与父进程显式关闭机制

1. **一子任务一新实例（默认禁止连续复用）**
   - 每一个独立子任务尽量创建**全新的 Subagent** 执行，确保其上下文干净聚焦、无前序任务残留干扰。
   - 一般**不允许**在同一个 Subagent 内跨任务连续派活。
2. **父 Agent 验收确认后显式下发关闭指令**
   - Subagent 完成被委派的单一任务并回传结果摘要后即停止动作。
   - **必须经过父 Agent 审阅确认结果合格可用后，由父 Agent 主动发出关闭指令销毁该 Subagent**：
     - 对通过宿主 `invoke_subagent` 创建的子会话：父 Agent 确认结果后立即调用 `manage_subagents(Action="kill", ConversationIds=["<subagent-id>"])` 显式关闭；
     - 对通过 `agy` CLI 无头单任务模式（`--output-format stream-json --print "<prompt>"`）派发的子代理：子进程完成单次闭环、原始流落盘至 `logs/subagents/<task-id>.stream.jsonl` 并由外层提取 `result.response` 摘要后即终止退出；**严禁传入 `--continue` 或 `--conversation`**。父 Agent 验收其产物后将该子任务槽位标记关闭；若遇退出码 `124` 超时，父侧先清理残留子进程并核查 `git status` / `git diff` 脏现场后再决定是否新派重试。
3. **允许续用的唯一例外**
   - 仅当父 Agent 判断**紧随其后的动作是对刚执行同一任务的直接小幅补充或漏项修补**（且复用当前局部现场明显优于重新组装上下文）时，才由父 Agent 显式决定继续在该 Subagent 补充执行一次，补充验收通过后立即关闭。

---

## 5. 云端沙盒防 `9m50s` 强杀与防会话假死操作红线

1. **所有预计 `> 60s` 的非守护命令强制内置 `<= 420s` 软超时**
   - 云端 Linux 沙盒（`exebox`）单次非守护 `run_command` 存在宿主机侧不可取消的 **`590s`（`9m50s`）gRPC 硬截止线**（超限即报 `RPC::DEADLINE_EXCEEDED` 并破坏控制流）。
   - 任何预计可能超过 **60 秒** 的非守护命令（包括派发 `agy` 子代理执行任务、运行测试批次、执行编译门禁），**在云端 Linux 沙盒内必须在虚拟机内部显式包裹**（Windows 本机脚本改用 `py -3` 子进程超时控制）：
     ```bash
     timeout -k 10s 420s <command>
     ```
     确保万一超时也在第 7 分钟由虚拟机内核干净回收整个子进程树并返回标准退出码 `124`，绝不触碰宿主机 `590s` 强杀线。
2. **重型测试套件强制按 `<= 240s` 拆批执行**
   - 严禁在单条命令中串行运行整套重型端到端测试（如 `TrackBSegmented70kTests` 全量需 15–20 分钟，必须按 `test_01+02a+02b`、`test_03+04`、`test_05`、`test_06+07`、`test_08a+08b`、`test_09`、`test_b_route_runtime_ci` 分批交由独立短任务执行；全量长矩阵交由远端 GitHub Actions `windows-latest` 执行）。
3. **超过 7 分钟的不可拆分任务走有界切片或 `IsDaemon: true`**
   - `plan-mvg` / `plan-capabilities` 的 `3b generate` 必须传 `--max-new-dispatches 1 --pause-after-sec 180`；
   - 单次确需超过 7 分钟且不可拆分的调用（如 `b-route-source-audit`）必须使用 `IsDaemon: true` 启动并重定向日志与 `.exit` 状态码文件，严禁用 `sleep` 长阻塞轮询等待。
4. **父会话步数水位控制、思考深度与 Push 节流**
   - 父会话**保持最高思考深度与精炼可见输出（避免超长输出触发超时）**；当父会话累计任务序号接近 **`1200` 步** 时，主动完成当前提交并提示用户开新会话接力。
   - 运行任何 `> 60s` 命令前，若工作区存在未提交代码修改，先由父 Agent 备份补丁至跨会话共享盘 `/home/antigravity/.gemini/jetski/brain/<conversation-id>/scratch/latest-uncommitted.patch`；**每完成验证闭环立即 `git commit`，在阶段检查点、运行预计 `> 60s` 长命令前或会话轮转前执行 `git push`**，避免高频推送挤占远端 Windows GitHub Actions 队列。
