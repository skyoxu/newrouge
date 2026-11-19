
- source_spec: `_bmad-output/implementation-artifacts/b-route/spec-2-2-independent-cumulative-source-audit.md`
  summary: 恢复的既有BMAD架构lint_spine以子串代替显式字段标签，可能漏报Binds/Prevents缺失。
  evidence: `_bmad/bmm/plan/bmad-architecture/scripts/lint_spine.py:142` 对正文做 `f in low`；只有Rule且含unbinds/prevents的正文即可通过。来源为58b7d6e恢复的运行时资产，当前Story未修改该linter；需后续工具维护中补显式标签识别及负例，避免架构Reviewer Gate错误放行。

- source_spec: `_bmad-output/implementation-artifacts/b-route/spec-2-3-task-independent-planning-workspace.md`
  summary: 补充合格真实3A proof通过只读验证、正式3B准备及当前load重验的阳性集成证据。
  evidence: 原始真实audit04均有blocking findings且当前工具身份已漂移；成功单测显式使用assembly seam。用户目前暂停新的真实模型调用，不得伪造real资格；待有当前合格原始proof后补测。

- source_spec: `_bmad-output/implementation-artifacts/b-route/spec-2-7-public-commit.md`
  summary: B1：defer：原有中断消歧边界，交 2.8
  evidence: 硬退出可留下原子临时文件，严格 inventory 会安全阻断。原 AC 明确自动 recover 属于 2.8；不忽略或删除残留，不宣称该窗口已恢复。独立 Astra 范围评判确认不新增 2.7 自动恢复前置。

- source_spec: `_bmad-output/implementation-artifacts/b-route/spec-2-7-public-commit.md`
  summary: B8：defer：原有配置风险，未证实 medium
  evidence: 基线已使用同一 git status，未取得本工作实际 fsmonitor 配置或执行证据；需实际配置和可达调用证据才能判断影响。本轮不修改 Git 或主机安全配置。

- source_spec: `_bmad-output/implementation-artifacts/b-route/spec-2-7-public-commit.md`
  summary: G2：defer：历史 v3 维护覆盖限制
  evidence: 旧公开 v3 正向渲染接线缺直接维护断言，原 26 方法只按实际覆盖复用。独立 Astra 确认当前默认 2.7 已拒绝 fresh v3，此历史消费属于 2.8，不能倒加为当前 2.7 前置；真实 proof3 仍待完成。

- source_spec: `_bmad-output/implementation-artifacts/b-route/spec-2-7-public-commit.md`
  summary: G3：defer：历史 OP03 维护覆盖限制
  evidence: 原七方法确实执行过，但不能宣称全部验证成功 binding 构造。当前 2.8 历史消费者不重构旧 binding；不移植旧实现或改冻结 R56。当前 15 方法 DATA/接口适配器已注册并通过，但不充当真实恢复验收。

- source_spec: `spec-2-9-completed-planning-reuse.md`
  summary: 闭包外新增实际Requirement分母后的自动完成项重基尚未证明属于当前无关元数据复用合同，不新增交付阻塞。
  evidence: B3为maybe-false/medium；当前完整分母不兼容明确miss/fresh。若扩展，须证明治理闭包、原单项语义和全部验证分母的相容性；不伪称已支持。

## Deferred from: code review of Epic 1 Stories 1.1-1.6 (2026-11-19)

- source_spec: `_bmad-output/implementation-artifacts/b-route/spec-1-1-*.md` .. `spec-1-6-*.md`
  summary: Inventory 与 codec 的路径规范化设计边界：inventory 观测层与 codec 内容身份层各自规范化，统一需跨 Story 1.1/1.3 的合同修订，非本轮引入。
  evidence: `logs/ci/2026-11-19/epic1-review/`；既有跨 Story 设计边界，非本轮引入，不新增 Epic 1 交付阻塞。

- source_spec: `_bmad-output/implementation-artifacts/b-route/spec-1-1-*.md` .. `spec-1-6-*.md`
  summary: 载体文件删除的表示：当前以缺失诊断阻断而非显式删除记录，属跨 Story 载体合同设计，留待后续 Epic 定义。
  evidence: `logs/ci/2026-11-19/epic1-review/`；既有跨 Story 设计边界，非本轮引入，不新增 Epic 1 交付阻塞。

- source_spec: `_bmad-output/implementation-artifacts/b-route/spec-1-1-*.md` .. `spec-1-6-*.md`
  summary: 非 UTF-8 二进制登记来源：当前按 raw bytes 绑定并在文本解码处阻断，二进制来源的正式支持需新合同。
  evidence: `logs/ci/2026-11-19/epic1-review/`；既有跨 Story 设计边界，非本轮引入，不新增 Epic 1 交付阻塞。

- source_spec: `_bmad-output/implementation-artifacts/b-route/spec-1-1-*.md` .. `spec-1-6-*.md`
  summary: 历史带日期 `story-1-*-windows.yml` 分支触发器：持续 Windows 回归已由 `scripts/python/run_gate_bundle.py` 登记五个 B 路线 suite 取代，旧 workflow 清理另行处理。
  evidence: `logs/ci/2026-11-19/epic1-review/`；既有跨 Story 设计边界，非本轮引入，不新增 Epic 1 交付阻塞。

- source_spec: `_bmad-output/implementation-artifacts/b-route/spec-1-1-*.md` .. `spec-1-6-*.md`
  summary: `protection-input.v1.json` 与 `epic1-handoff.v1.json` 中原环境 `logs/ci/2026-11-03..04` 路径：属历史证据引用，按原字节保留，不在本轮重写。
  evidence: `logs/ci/2026-11-19/epic1-review/`；既有跨 Story 设计边界，非本轮引入，不新增 Epic 1 交付阻塞。

## Deferred from: code review of Epic 2 Stories 2.1-2.7 (2026-11-19)

- source_spec: `_bmad-output/implementation-artifacts/b-route/spec-2-1-*.md` .. `spec-2-7-*.md`
  summary: Story 25 AST/字节锁保护文件（`_b_route_planning_input.py`、`_b_route_planning_runtime.py`、`_b_route_execution_transition.py`、`_b_route_issue_accounts.py`、`_planning_skill_common.py`、`_codex_app_server.py`、`_mvg_worker_lifetime.py`、`_b_route_frozen_native_reader.py`）中的非阻塞历史边界留待专门 source-epoch 过渡升级处理。
  evidence: `logs/ci/2026-11-19/epic2-review/epic2-verification-summary.json`；受 `test_01_story25_ast_and_semantic_lock_guard` 锁护，本轮严禁改动锁护文件，不新增 Epic 2 交付阻塞。

- source_spec: `_bmad-output/implementation-artifacts/b-route/spec-2-1-*.md` .. `spec-2-7-*.md`
  summary: CI `push` 快速子集与旧 `story-2-1-windows.yml` 工作流后续统一清理。
  evidence: `.github/workflows/b-route-runtime-deterministic.yml` 与 `logs/ci/2026-11-19/epic2-review/`；当前确定性回归已由 `run_gate_bundle.py` 与 `b-route-runtime-deterministic.yml` 覆盖，历史分支触发器清理另行排期。

- source_spec: `_bmad-output/implementation-artifacts/b-route/spec-2-6-frozen-adoption-operation.md`
  summary: `origin_profile` v2 扩展负向单测增强。
  evidence: `logs/ci/2026-11-19/epic2-review/`；当前 `origin-prepare` 与默认 profile 路径已覆盖，v2 扩展字段与更多异常组合负向用例列为后续测试增强项。
