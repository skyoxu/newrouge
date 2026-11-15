# ADR-0063: 双平面多模型路由架构与 Gemini CLI 物理无工具隔离运行器契约

- Status: Accepted
- Date: 2026-11-14
- Scope: 平面 A（`scripts/sc/_llm_backend.py`）与平面 B（`scripts/python/_isolated_runner_registry.py`、`codex_isolated_model_runner.py`、`gemini_isolated_model_runner.py`）多模型路由、物理沙盒隔离与离线协议重放治理
- Related:
  - `docs/adr/ADR-0038-semantic-delivery-topology.md`
  - `docs/adr/ADR-0038-mvg-candidate-admission.md`
  - `docs/adr/ADR-0040-b-route-stages-authority-and-activation.md`
  - `docs/adr/ADR-0062-3b-deterministic-70k-segmented-runtime.md`

## Context

仓库模型调用分为两个职责与证明强度截然不同的执行平面：
- **平面 A（Chapter 5–7 日常辅助与评审后台，`scripts/sc/_llm_backend.py`）**：服务于语义对齐、单任务代码评审与辅助分析，不承担 B 路线 3A/3B 零工具独立隔离证明。
- **平面 B（B 路线 3A 独立来源审计、3B Capability/MVG 候选生成与独立匿名评审、采纳与补偿审阅）**：按 `docs/adr/ADR-0038-semantic-delivery-topology.md`、`docs/adr/ADR-0038-mvg-candidate-admission.md` 与 `docs/adr/ADR-0040-b-route-stages-authority-and-activation.md` 要求，每次调用必须是全新会话、零工具、仅可见受控工作区快照、绑定精确模型身份与高推理强度，并具备原始协议流冷启动重放证据。

为支持在 Windows 与 Linux 环境下统一使用官方免费 OAuth 订阅 CLI 通道，同时 100% 保留既有 Codex App Server 证据链并硬阻断未显式授权的按量付费 API 调用，需要正式确立双平面路由与 `gemini_isolated_model_runner.py` 物理无工具隔离契约。

## Decision

1. **双平面职责边界与受控路由配置（`docs/workflows/llm-routing.json`）**
   - **平面 A（`scripts/sc/_llm_backend.py`）**：默认回退保持 `"codex-cli"`（100% 兼容既有链路，可通过 `SC_LLM_BACKEND=gemini-cli` 或 `NEWROGUE_PLANE_A_BACKEND=gemini-cli` 显式切换），同时注册 `"gemini-cli"`、可选主机辅助 `"agy-subagent"`（如实标记 `host_subagent_with_read_tools`，严禁进入平面 B）、`"openai-api"` 及 `"gemini-api"`。
   - **平面 B（`scripts/python/_isolated_runner_registry.py`）**：仅注册官方物理无工具隔离运行器 `codex_isolated_model_runner.py`（协议 `"codex-app-server-stdio"`）与 `gemini_isolated_model_runner.py`（协议 `"gemini-cli-stream-json"`，统一兼容官方 Google Antigravity CLI `agy` 与 Gemini CLI `gemini` 流式传输）。`resolve_plane_b_runner` 将 `"auto"` 视作未显式固定并依次回退至 `NEWROGUE_PLANE_B_RUNNER` 与 `docs/workflows/llm-routing.json` 的 `plane_b.default_runner`（默认保持 `"scripts/python/codex_isolated_model_runner.py"` 以确保 100% 兼容，同时支持 `"codex-cli" -> "codex"` 与 `"gemini-cli" -> "gemini"` 归一化），并在 `plane_b.runners.gemini.model` 锁定精确旗舰模型 ID（`"gemini-4-carbon-high"`，严禁 `"auto"` 或 `"default"` 动态模型别名）。

2. **`gemini_isolated_model_runner.py` 物理级零工具沙盒契约**
   - **一次性沙盒 `HOME` / `GEMINI_CLI_HOME` 认证最小化隔离**：每次调用新建独立临时沙盒目录作为 `HOME`、`USERPROFILE` 与 `GEMINI_CLI_HOME`，仅以 `0600` 权限从真实宿主用户目录最小化拷贝认证令牌文件（`antigravity-cli/antigravity-oauth-token`、`oauth_creds.json`、`google_accounts.json`）以支持官方 OAuth 会话；物理隔绝宿主 `~/.gemini/settings.json`、全局 `GEMINI.md`、历史会话记忆、扩展与 MCP 配置，同时剥离宿主按量计费与云端凭据环境变量（`GEMINI_API_KEY`、`GOOGLE_API_KEY`、`GOOGLE_GENAI_USE_VERTEXAI`、`GOOGLE_GENAI_USE_GCA`、`GOOGLE_APPLICATION_CREDENTIALS`、`GOOGLE_CLOUD_PROJECT`、`GOOGLE_CLOUD_LOCATION`、`GEMINI_CLI_SYSTEM_DEFAULTS_PATH`、`NODE_OPTIONS` 等），且严禁在任何日志或证明中记录凭据路径或内容。
   - **系统级设置与沙盒锁死零工具**：对 `gemini` 入口通过 `GEMINI_CLI_SYSTEM_SETTINGS_PATH` 与沙盒 `settings.json` 强制锁定 `tools.core = []`、`tools.allowed = []`、`mcpServers = {}`、`security.auth.selectedType = "oauth-personal"`；对 `agy` 入口启用 `--sandbox --disable-slash-commands` 并在隔离配置中锁定 `toolPermission = "request-review"`（非交互单轮无审批通道下任何工具请求无法自动获批）。
   - **受控最小中性系统提示词与空工作目录**：注入受控最小中性系统提示词（要求仅依据输入快照输出严格符合 Schema 的原始 JSON，禁止代码块围栏与额外解释），并将其字节 SHA-256 纳入协议回执与 3A `tool_identity`；子进程在新建空目录（empty CWD）中启动，并在子进程树终止且管道句柄关闭后再清理临时沙盒目录。
   - **文件级精确 `stdin` 传参与流式原始输出**：复用 `workspace_payload` 组装完整提示词与受控文件快照，通过文件背书的 `stdin` 精确传入（不使用命令行 `-p` 传大文本，彻底规避 Windows 32,767 字符命令行上限，且直接调用可执行文件而不经由 `cmd.exe /d /s /c`）：`agy` 使用 `--sandbox --disable-slash-commands --model <exact_model> --input-format stream-json --output-format stream-json [--json-schema ../schema.json]`，`gemini` 使用 `-m <exact_model> --output-format stream-json --raw-output --accept-raw-output-risk --skip-trust`。
   - **零工具调用 Fail-Closed 铁律**：运行期与重放期同时强校验零工具调用（`gemini` 流统计 `tool_calls == 0` 且零 `tool_use` / `tool_result` 事件；`agy` 流 `num_turns == 1` 且所有 `step_update.step_type` 严格属于纯文本推理集合 `{"user_input", "agent_response", "finish", "thinking", "thought"}`）；一旦出现任何工具调用步骤、未知事件、Markdown 代码围栏、非零退出或 JSON Schema 违例，立即 Fail-Closed 阻断。

3. **`.gemini-stream.jsonl` 冷启动离线重放与 3A 工具身份绑定**
   - 每次调用将原始 `stream-json` 事件流落盘为 `<output.name>.<32hex>.gemini-stream.jsonl` 并配对落盘 `<output.name>.<32hex>.gemini-stream.stderr.txt`（即使 0 字节或异常超时也强制落盘，且绝不污染 `workspace/`）。
   - `_gemini_cli_protocol.replay()` 从真实 `init` 事件提取真实会话标识（`session_id` 或 `conversation_id`，严禁合成随机 UUID 冒充会话 ID），冷启动复验启动参数（`command == gemini_command(...)`）、零工具隔离配置摘要（独立重算 `build_isolated_settings(runtime_reasoning_effort)` 校验 `isolated_settings_sha256` 与 `system_settings_sha256`）、完整单轮事件序列、零工具调用、精确模型 ID、高推理配置、系统提示词摘要、输入提示词字节摘要及输出 JSON Schema 一致性。
   - 3A `_b_route_source_audit.tool_identity` 在使用 `gemini_isolated_model_runner.py` 时，增量绑定 `gemini_isolated_model_runner.py`、`_gemini_cli_protocol.py`、`_isolated_runner_registry.py`、`docs/workflows/llm-routing.json`、官方 CLI 可执行文件（`agy` 或 `@google/gemini-cli` + `node`）SHA-256、系统提示词摘要及高推理期望。

4. **100% 保留 Codex 隔离链路与按量付费 API 显式 Opt-in 门禁**
   - `codex_isolated_model_runner.py` 与 `_codex_app_server.py` 的全部既有协议字段、3A `tool_identity` 闭包及历史 `.app-server.jsonl` 证据 100% 原样保留。
   - `"openai-api"` 与 `"gemini-api"` 在路由配置与 CLI 入口层强制标记为 `opt_in_only = true`；未显式传入 `--allow-paid-api`（或设置 `NEWROGUE_ALLOW_PAID_API=1` / `SC_ALLOW_PAID_API=1`）时一律拒绝派发，防止误触按量计费通道。平面 A `gemini-cli` 在给定 `output_schema` 时同样严禁静默剥离 Markdown 代码围栏，并强制执行严格 JSON 解析与 JSON Schema 校验。

## Consequences

- **Positive**：在 Windows 与 Linux 上实现与 Codex App Server 同等物理隔离强度的官方 Gemini CLI 平面 B 运行器，消除跨环境订阅 CLI 差异，同时保证所有确定性单测可通过本地离线 Fake Gemini CLI 零配额验证。
- **Negative / Trade-offs**：平面 B 调用方需通过 `_isolated_runner_registry.py` 统一识别双官方运行器及双原始协议后缀（`.app-server.jsonl` 与 `.gemini-stream.jsonl`），并在代码冻结屏障下维护新增模块摘要绑定。
- **Governance Boundary**：本 ADR 确立双平面路由与平面 B 隔离运行器治理契约（`Accepted`），不改变 `docs/adr/ADR-0040-b-route-stages-authority-and-activation.md` 规定的阶段准入与默认 A 路线状态。
