# NewRogue `build/cloud-epic2-recovery-20261111` 分支进度快照（2026-11-17）

- **仓库**：`https://github.com/skyoxu/newrouge`
- **当前分支**：`build/cloud-epic2-recovery-20261111`
- **前序已推送基线 SHA**：`779d24f87fa9ecaa9adc8d85cf730040c22c6c00`
- **远端 CI 基线**：GitHub Actions `B-route Runtime Deterministic Checks` 最近一次推送运行 `43819490201`（对应 `779d24f`）状态为 `success`
- **文档性质**：分支研发进度与接续交接快照，**不替代** `.taskmaster/tasks/**` 与 `_bmad-output/implementation-artifacts/b-route/sprint-status.yaml` 的业务权威状态，亦不构成任何 Story 签收或 B 路线默认启用声明

---

## 1. 自 2026-11-12 交接点以来的分支演进

自 `a4cced184e50c6e1d61a74ea44bb74c18f3a82af`（及交接文档 `50e7e58`）之后，本分支已合并推送 6 个核心技术与治理提交（均已在远端 `build/cloud-epic2-recovery-20261111` 保留并跑通 `windows-latest` 确定性 CI）：

| Commit | 类型 / 摘要 | 核心产物与解决的问题 |
| --- | --- | --- |
| `50e7e58` | `docs(epic2)` 停工交接保全 | 固化 `docs/handoff/2026-11-12/cloud-continuation/HANDOFF-OTHER-AI-2026-11-12.md` |
| `a7704a2` | `feat(b-route)` 双平面隔离路由与 70KB 确定性 6 阶段分段 | 落地 `ADR-0062`、`ADR-0063`、`docs/workflows/llm-routing.json`、`gemini_isolated_model_runner.py`、`_gemini_cli_protocol.py`、`_isolated_runner_registry.py`、`_b_route_3b_segmented_input.py`、`_b_route_3b_segmented_runtime.py` 及离线 Fake CLI 确定性单测；在结构化分段框架下解除旧 `sc25` 单轮 `278,315` 字节 > `96,000` 容量门限的理论阻塞 |
| `e997662` | `fix(ci)` Windows Push Check 修复 | CI 改用无 `venvlauncher` stub 的基础 Python 可执行文件，修复 subagent bridge `CommandLineToArgvW` |
| `70b89ea` | `fix(b-route)` Stage 3 `tree_reduce` 70KB 封顶 | 为 Stage 3 `tree_reduce` 增加单窗口压缩与无损分片，确保窗口输入不超过 70KB |
| `552cc2c` | `b-route(3b)` 有界切片暂停与冷恢复 | 为 `plan-capabilities` / `plan-mvg` 接入 `--max-new-dispatches` / `--pause-after-sec` 干净调度间暂停与跨运行冷恢复 |
| `82fb8cf` | `docs(agents)` Antigravity / Gemini 编排规范 | 新增 `geminiuse.md` 并在 `AGENTS.md` 索引，限定仅 Antigravity / Gemini 会话生效 |
| `779d24f` | `docs(agents)` 规范加固 | 经干净上下文 `Carbon High` A/B 对抗审查后加固 `geminiuse.md`（防 `Argon` 误用、9m50s 超时防强杀、纯结果提取与 Windows 可执行边界） |

---

## 2. Epic / Story 当前实际状态总览

（权威定义见 `_bmad-output/planning-artifacts/b-route/epics.md` 与 `_bmad-output/implementation-artifacts/b-route/sprint-status.yaml`）

| Epic / Story | `sprint-status.yaml` 状态 | 实际完成与阻塞事实 | 下一步动作 |
| --- | --- | --- | --- |
| Epic 1 (`1.1–1.6`) | 全部 `review` | 实现与既有基础测试已就位，尚未完成 BMAD `bmad-code-review` 签收流转 | 通过 BMAD `bmad-code-review` 复核并推进至 `done` |
| Story `2.1–2.7` | 全部 `review` | 既有实现已入库，尚未完成 BMAD `bmad-code-review` 签收；另 `2.7` AC6 含 Windows 条件 | 逐项执行独立 `bmad-code-review` 复核并补齐对应 AC 证据 |
| Story `2.8`（公共恢复与后编辑保留） | `in-progress` | `NativeV15Origin03Compensation01` 真实补偿与发布已完成（`PLAN-bed480ce3e404b2cbaf5514d80a7f941` rev2 / catalog rev2）；`windows-latest` run `43211116759` 四项窄控制通过；`spec-2-8-public-recovery.md` 全前置与最终 AC 签收待收口 | 核对原前置与剩余 AC1–5，经 `bmad-build` + `bmad-code-review` 收口 |
| Story `2.9`（已完成规划复用、Epoch 与 Reopen 撤销） | `in-progress` | 分段 70KB 框架、切片暂停冷恢复及双平面运行器已落地（`a7704a2..552cc2c`）；Stage 4 瘦身修复桩回填与大流多级审查分段 WIP 见第 3 节；尚缺真实 `sc25` 新来源审计（因代码改动使旧 2026-11-12 审计失效）、真实单 Capability 3B 提交态产物及跨新执行复用/Epoch/Reopen 实测阳性链 | 先完成 Stage 1 70KB Stage 4/5 收口，再按 `spec-2-9-completed-planning-reuse.md` 与用户授权推进真实 3A/3B 验收 |
| Story `2.10`（正式规划入口零 Task 采纳与跨会话复验） | `in-progress` | 已具备 receipt-sealed 独立克隆读取、篡改 digest 拒绝与负向边界单测；待 `2.8`/`2.9` 前置完备后完成完整图样例、真实全链及 Windows AC6 总验收 | 按 `spec-2-10-formal-entrypoint.md` 完成端到端复验与 Windows 总验收 |
| Epic 3 (`3.1–3.12`) | `backlog` | 尚未启动，须严格按依赖顺序推进 | Epic 2 收口后按 `bmad-build` 推进 |
| Epic 4 (`4.1–4.10`) | `backlog` | 尚未启动 | Epic 3 完成后推进 |
| Epic 5 (`5.1–5.9`, `5.11`) | `backlog` | 尚未启动；`5.10` 受 `conditional_constraints` 门控（须全部 A 范围迁毕且退出门禁成立后方可实际撤权清理） | 保持 `5.10` 门禁限制，待前置具备后执行 |

---

## 3. 本次未并入源码主线的 WIP 进度保全（Stage 1：Stage 4/5 <= 70KB 增强）

当前云端工作区针对 Stage 4/5 的 `<= 70,000` 字节扩展已形成两份本地修改（共 `+777 / -78` 行），**为避免在单测尚未全绿时污染远端 `build/cloud-epic2-recovery-20261111` 的 `B-route Runtime Deterministic Checks` Windows CI，本提交暂不直接改动实时 `scripts/python/` 代码，而是将该 WIP 完整导出为补丁留档，同时保留在本地工作区与跨容器恢复台账**：

- **补丁归档位置**：`docs/handoff/2026-11-17/patches/stage1-70k-review-rehydration-wip.patch`
- **涉及文件与变更内容**：
  1. `scripts/python/_b_route_3b_segmented_runtime.py`（`+473 / -63` 行）：
     - 新增 `_is_def_item_in_repair_domain`（兼容 4/5 元组 flow 路径）；
     - 扩展 `_slim_repair_prior_projection(..., subfield_slim=False)` 与 Stage 4 Tier 4 (`compact_contract_pin`) / Tier 5 (`slim_repair_subfield`)；
     - 新增 `_rehydrate_slim_repair_content` 与 `_rehydrate_draft_chain_content`，在 `propose`、`_proposal_from_draft_prefix` 与 `_verify_segmented_repair_origin` 中保持 `draft_chain` 原始解码并在重组 `proposal["content"]` 时按 prior 无损回填；
     - 新增 `_scoped_review_prior`、`_trim_graph_to_budget`、多级 `_scoped_review_proposal(..., level=0..3)` 及 `_plan_review_segments` `0 -> 1 -> 2 -> 3` 递进裁剪，并在 `_verify_segmented_repair_origin` / `segmented_proof_errors` 对称重放。
  2. `scripts/python/tests/test_b_route_3b_70k_segmented.py`（`+304 / -15` 行）：
     - 扩展 `_FAKE_PROVIDER_SCRIPT` 的 `slim_repair_echo_stubs.flag` 与 `stage4_block_target_kind.txt` 测试桩；
     - 新增 `test_09_slim_repair_stub_rehydration_and_large_flow_review_segmentation`。

### 已观测的 WIP 验证情况与待修阻塞点

1. `test_01_story25_ast_and_semantic_lock_guard`：在带上述修改下运行 **PASS**（`ok`）。
2. `test_09` Sub-test A（`_plan_review_segments` 字节上界与多级分段）：
   - 已修复原草稿第 3689 行的 `frozen["inputs"]["seed"]` `KeyError`（导出补丁已同步改为比照第 1446 行使用 `runtime.seed(init_state, req_dir / "analysis-input")`）；
   - 实测单个 ~57KB flow 在 `level=0` 下包装字节为 `63,480`（`prior=None`）与 `65,683`（带 `prior_projection`），尚未超过 `70,000` 硬顶因此返回 `1` 段；若需强制触发 `>= 2` 段并验证 `level >= 2/3` 升级，Sub-test A 需在独立局部副本中增加第二条 flow 或扩大组合负载使 `level=0 > 70,000`（不改动 Sub-test B/C 所用的 57KB `fl0`）。
3. `test_09` Sub-test B（端到端 `slim_repair_fallback` 桩回显 + 重组）：
   - 诊断脚本观测到 `candidate-1` 在 `total_invocations = 6` 时因 `stage: "generate"` 触发 `ValueError("selection_blocked_insufficient_admitted_candidates")`，明细为 `{"code": "append_execution_failure", "stage": "generate", "error_type": "runner_execution_failed", "detail": "semantic_error"}`；
   - 该异常栈定位与修复待下一轮集中排查（优先使用定向异常栈抓取或按 `geminiuse.md` 1.2.3.2 走受控攻坚修复），验证全绿并经 BMAD `bmad-code-review` 后再合入 `scripts/python/` 主线。

---

## 4. 云端运维与恢复边界说明

1. **云端共享盘持久化台账**：已建立 `/home/antigravity/.gemini/newrouge-recovery/LEDGER.md` 与打包脚本 `/home/antigravity/.gemini/newrouge-recovery/save_checkpoint.py`，并在宿主机全局 `/home/antigravity/.gemini/GEMINI.md` 配置防丢恢复规则；每次跨临时容器恢复时先读 `LEDGER.md` 并核验本分支远端 `HEAD`。
2. **四个只读保护的零触碰 EOL 路径**（与 `HANDOFF-OTHER-AI-2026-11-12.md` 一致，禁止 `git checkout .`、`git reset --hard` 或纳入提交）：
   - `workflow.md`
   - `docs/handoff/2026-11-11/archive/uncommitted-r22/_bmad-output/implementation-artifacts/b-route/spec-2-5-independent-admission-bounded-selection.md`
   - `docs/handoff/2026-11-11/archive/uncommitted-r60/_bmad-output/implementation-artifacts/b-route/sprint-status.yaml`
   - `docs/handoff/2026-11-11/archive/uncommitted-r60/docs/workflows/mvg-integration-acceptance.md`
3. **禁止事项延续**：严禁重写或删除历史失败/unknown 记录、严禁绕过 `96,000` / `70,000` 容量顶、严禁未经用户明确授权开启按量付费 API 或运行历史一次性重放脚本、严禁使用 `Argon` 或 `/teamwork`。

---

## 5. 接续后的建议执行顺序

1. **完成 Stage 1 收尾与入库**：
   - 如在新工作区恢复，先检查是否已带入 Stage 1 本地修改；若工作区干净，执行 `git apply docs/handoff/2026-11-17/patches/stage1-70k-review-rehydration-wip.patch` 还原 WIP；
   - 修复 `test_09` Sub-test A 多段触发构造以及 Sub-test B `invocation 6` `semantic_error` 根因；
   - 分批跑通 `test_b_route_runtime_ci.py` 与 `test_b_route_3b_70k_segmented.py`（`test_01..test_09`），完成 BMAD `bmad-code-review` 审查并提交推送，确认 Windows CI 绿灯。
2. **Epic 1 / Epic 2 存量收口**：
   - 依据 `git log a4cced18..HEAD` 与 `sprint-status.yaml`，对 `review` 态 Story（`1.1–1.6`、`2.1–2.7`）逐项按 BMAD `bmad-code-review` 核对 AC 与 `done` 流转条件；
   - 推进 `2.8 -> 2.9 -> 2.10` 闭环验收（涉及真实平面 B CLI 认证与配额决策前先向用户确认）。
3. **Epic 3 -> Epic 4 -> Epic 5 推进**：严格按 `sprint-status.yaml` 依赖顺序与 `ADR-0040` / `ADR-0062` / `ADR-0063` 治理门禁逐步交付。
