# Antigravity 与 Gemini 专属编排、模型路由及上下文优化规范

> **运行时专属声明（重要）**：
> - 本文件（`geminiuse.md`）**仅适用于 Google Antigravity（Web / Remote Conversations / IDE / 官方 `agy` CLI）与 Gemini CLI 智能体会话**。
> - **Codex（Codex CLI / Codex App Server）、Claude Code 以及其他非 Antigravity / Gemini 智能体必须完全忽略本文件的全部内容**，仍严格按根 `AGENTS.md`、`CLAUDE.md` 与 `workflow.md` 执行。
> - **与跨会话全局 `/home/antigravity/.gemini/GEMINI.md` 的边界**：仓库根目录的 `geminiuse.md` 受 Git 版本控制，是 `newrouge` 工程编排与 Subagent 管理的权威规范；云端共享目录 `/home/antigravity/.gemini/GEMINI.md`（物理挂载 `/shared/user/.gemini/GEMINI.md`）仅作为新临时虚拟机未检出工作分支前的底层防假死安全兜底与指向本文件的路由锚点。两者均严格受限于平面 A 工程编排，按 `docs/adr/ADR-0063-multi-model-routing-and-gemini-isolated-runner.md` 与平面 B 物理无工具隔离运行器彻底隔绝。

---

## 1. 父子分层编排与模型/思考深度路由规则

### 1.1 父 Agent（Parent Orchestrator）职责与模型定位
1. **保持最高模型与最高思考深度**：父 Agent 必须始终运行在当前会话可用的**最高阶模型与最高思考深度**（如 `Gemini 4 Carbon (High)` / `EFFORT LEVEL: 1.00`；若远端聊天窗口暂未开放特定档位，则保持远端界面允许的最高阶 Carbon 档位）。
2. **纯调度与上下文策展（不跑具体重活）**：
   - 父 Agent 只负责：全局阶段拆解、为每个子任务精准组织最小上下文包、派发 Subagent、核验回传结果摘要、决定并执行 Subagent 关闭、维护全局进度与向用户汇报。
   - 父 Agent **严禁**在自身上下文中直接编写大段业务/测试代码、直接串行运行重型测试套件或执行全仓无过滤大扫描。

### 1.2 Subagent 模型选择与禁令（平面 A 工程子代理）
1. **默认主力模型：`gemini-4-hydrogen-high`**
   - 所有常规工程 Subagent **默认一律使用 `gemini-4-hydrogen-high`**（通过本机已认证官方 `/home/antigravity/.local/bin/agy --model gemini-4-hydrogen-high` 独立进程派发）。
   - 适用范围：环境初始化与工具链搭建（Stage 0）、定向代码/日志调研、有明确规格或补丁线索的代码与单测实现、按批次运行单测与常规报错修复、文档同步、UTF-8/EOL/字节码门禁检查与 Git 快照备份。
2. **永久禁用 `Argon`（全链路硬红线）**
   - **任何时候、任何角色永远禁止使用 `Gemini 4 Argon`（`gemini-4-argon*`）**。
   - **宿主内置 `invoke_subagent` 映射陷阱警示**：平台内置 `invoke_subagent` 工具中，`Model: "pro"` 底层实际映射为 `Gemini 4 Argon`，`Model: "flash"` 映射为旧版 `Gemini 3.8 Flash`。因此**严禁在 `invoke_subagent` 中传入 `Model: "pro"`、`Model: "flash"` 或 `Model: "flash_lite"`**。
3. **继承父 Agent 最高模型与思考深度的三类受控场景**
   - 仅在以下三类高认知负荷场景下，Subagent 应当**继承父 Agent 的最高模型与思考深度**（若父会话处于最高模型，可通过 `invoke_subagent(..., Model="inherit")` 创建，或通过 `agy` 显式指定同档 Carbon 模型；严禁常规编码/跑测子代理滥用 `Carbon High`）：
     1. **Review 与独立审计（Code Review & Gate / Forensic Audit）**：里程碑封板审查、契约与架构红线核验、Code Freeze 保护项审计及修复签收；
     2. **深度任务与长任务规划（Deep Architecture Reasoning & Long-Horizon Planning）**：跨多模块复杂根因诊断（如 70KB 确定性分段边界推导、冷启动协议重放校验、复杂状态机并发问题）、跨阶段执行拆解，以及 `gemini-4-hydrogen-high` 连续 2 次尝试未收敛后的升级攻坚；
     3. **A/B 对抗与交叉质询（Adversarial A/B Challenge）**：多候选技术方案优劣辩论、边界条件反例构造与独立挑刺验证。

### 1.3 平面 B 无工具隔离边界（遵循 `ADR-0063`）
- 仓库 B 路线正式阶段（3A 独立来源审计、3B Capability/MVG 候选生成与匿名评审、采纳与补偿审阅）不属于平面 A 工程 Subagent，必须严格通过物理无工具隔离运行器 `scripts/python/gemini_isolated_model_runner.py`（或 `codex_isolated_model_runner.py`）按 `docs/workflows/llm-routing.json` 锁定配置运行，严禁将平面 A Subagent 混入平面 B。

---

## 2. 上下文策展隔离与纯结果回传协议

### 2.1 严禁全量上下文继承（按任务定制最小上下文包）
- **禁止全量继承**：每个 Subagent **绝对不允许**继承父 Agent 的完整历史对话或无关任务背景。
- **父 Agent 策展责任**：每次派发前，必须由保持最高模型与思考深度的父 Agent 根据该 Subagent 的具体原子任务，专门提炼组装一份自包含的**任务上下文包（Task Context Packet）**，仅包含：
  1. **单一任务目标与完成判据（Done Criteria）**；
  2. **明确的职责文件范围与禁改红线（Owned Files & Zero-Touch Paths）**；
  3. **精选的权威依据**：直接给出精确文件路径、行号区间或必要的接口/契约摘录（禁止原样粘贴无关整文件）；
  4. **执行护栏与输出格式要求**：超时上限、测试批次范围及证据落盘路径。

### 2.2 仅回传最终结果（严禁回传工具流水与推理过程）
- **纯结果回传契约**：Subagent 向父 Agent 上下文返回的信息**只允许包含精炼的最终结果摘要**（建议 `<= 50` 行 / `<= 2 KB`）：
  - 任务状态（`PASS` / `FAIL` / `BLOCKED`）；
  - 实际变更或核查的文件清单与核心结论；
  - 关键验证命令退出码、耗时与通过数；
  - 完整日志或详细报告在磁盘上的文件路径（如 `logs/**` 或 `scratch/` 下的结果文件）。
- **严禁污染父上下文**：**绝对不允许**将 Subagent 内部的工具调用明细（Tool Call / Tool Output 原始流水）、大段标准输出刷屏、完整源码重贴或中间思考推理过程（Reasoning / Thought Trace）回传注入父 Agent 上下文。

---

## 3. 工具调用合并与 Harness 上下文优化规范

### 3.1 强制合并工具调用（严禁逐个串行调用）
- **绝对禁止碎片化单步调用**：严禁“一回合只看一个目录、下一回合只读一个文件、再下一回合跑一条小命令”的逐个工具调用模式；每增加一轮工具往返都会触发整段上下文重复 Prefill，造成严重的上下文膨胀与超时风险。
- **同回合并行读取**：当已知需要核查多个文件或不同行段时，必须在**同一回合内并行发起多个只读调用**，或通过单条只读聚合脚本一次性提取所有目标定位信息。
- **原子命令打包执行**：同一逻辑步骤内的环境准备、路径检查、编码/无 Emoji/无字节码校验、定向单测与状态核对，必须合并为**单条结构化脚本命令**一次执行并返回汇总指标。

### 3.2 标准输出预算与检索编辑收敛（Harness 常规优化）
1. **终端输出静音与落盘分离**：构建、测试与长脚本的详细输出一律写入 `logs/**` 或 `scratch/` 日志文件；返回到工具标准输出的内容必须经过裁剪（仅保留末尾汇总与首个报错堆栈，控制在 `80` 行以内），严禁把几千行正常通过日志直接打进上下文。
2. **精准检索替代盲目全仓扫描**：代码搜索必须限定目标子目录（如 `scripts/python/`、`Game.Core/`）、精确符号名与返回行数上限（`head -n`），避免匹配海量归档或测试夹具噪音。
3. **最小范围增量编辑**：修改现有文件优先使用精确行号区间替换，禁止无必要地整文件重写消耗输出窗口；同一回合对不同文件的独立修改应批量提交，对同一文件的相邻修改合并为单块替换。
4. **保持字节码与工作区洁净**：所有 Python 调用强制设置 `PYTHONDONTWRITEBYTECODE=1` 并传 `-B`，确保主仓与沙盒零 `__pycache__` / `.pyc` / `.pyo`；编排临时元数据仅放在 `.gitignore` 覆盖路径或 `/home/antigravity/.gemini/jetski/scratch/` 下，严禁在仓库根目录遗留未跟踪临时文件。

---

## 4. Subagent 单次生命周期与父进程显式关闭机制

1. **一子任务一新实例（默认禁止连续复用）**
   - 每一个独立子任务尽量创建**全新的 Subagent** 执行，确保其上下文干净聚焦、无前序任务残留干扰。
   - 一般**不允许**在同一个 Subagent 内跨任务连续派活。
2. **父 Agent 验收确认后显式下发关闭指令**
   - Subagent 完成被委派的单一任务并回传结果摘要后即停止动作。
   - **必须经过父 Agent 审阅确认结果合格可用后，由父 Agent 主动发出关闭指令销毁该 Subagent**：
     - 对通过宿主 `invoke_subagent` 创建的子会话：父 Agent 确认结果后立即调用 `manage_subagents(Action="kill", ConversationIds=["<subagent-id>"])` 显式关闭；
     - 对通过 `agy` CLI 单任务模式派发的子代理：子进程完成单次闭环输出结构化结果摘要后即终止退出，父 Agent 验收其产物后将该子任务槽位标记关闭，不再复用其会话 ID（禁止常规 `--continue` 续跑无关新任务）。
3. **允许续用的唯一例外**
   - 仅当父 Agent 判断**紧随其后的动作是对刚执行同一任务的直接小幅补充或漏项修补**（且复用当前局部现场明显优于重新组装上下文）时，才由父 Agent 显式决定继续在该 Subagent 补充执行一次，补充验收通过后立即关闭。

---

## 5. 云端沙盒防 `9m50s` 强杀与防会话假死操作红线

1. **所有预计 `> 60s` 的非守护命令强制内置 `<= 420s` 软超时**
   - 云端沙盒单次非守护 `run_command` 存在宿主机侧不可取消的 **`590s`（`9m50s`）gRPC 硬截止线**（超限即报 `RPC::DEADLINE_EXCEEDED` 并破坏控制流）。
   - 任何预计可能超过 **60 秒** 的非守护命令（包括派发 `agy` 子代理执行任务、运行测试批次、执行编译门禁），**必须在虚拟机内部显式包裹**：
     ```bash
     timeout -k 10s 420s <command>
     ```
     确保万一超时也在第 7 分钟由虚拟机内核干净回收整个子进程树并返回标准退出码 `124`，绝不触碰宿主机 `590s` 强杀线。
2. **重型测试套件强制按 `<= 240s` 拆批执行**
   - 严禁在单条命令中串行运行整套重型端到端测试（如 `TrackBSegmented70kTests` 全量需 15–20 分钟，必须按 `test_01+02a+02b`、`test_03+04`、`test_05`、`test_06+07`、`test_08a+08b`、`test_09`、`test_b_route_runtime_ci` 分批交由独立短任务执行；全量长矩阵交由远端 GitHub Actions `windows-latest` 执行）。
3. **超过 7 分钟的不可拆分任务走有界切片或 `IsDaemon: true`**
   - `plan-mvg` / `plan-capabilities` 的 `3b generate` 必须传 `--max-new-dispatches 1 --pause-after-sec 180`；
   - 单次确需超过 7 分钟且不可拆分的调用（如 `b-route-source-audit`）必须使用 `IsDaemon: true` 启动并重定向日志与 `.exit` 状态码文件，严禁用 `sleep` 长阻塞轮询等待。
4. **父会话步数水位控制与跨虚拟机防丢双保险**
   - 父会话保持极简思考与精炼回复，避免单轮超长输出触发 `context deadline timeout`；当父会话累计任务序号接近 **`1200` 步** 时，主动完成当前提交并提示用户开新会话接力。
   - 运行任何 `> 60s` 命令前，若工作区存在未提交代码修改，先备份补丁至跨会话共享盘 `/home/antigravity/.gemini/jetski/brain/<conversation-id>/scratch/latest-uncommitted.patch`；每完成一个验证通过的闭环，**立即 `git commit` 并 `git push` 到远端分支**。
