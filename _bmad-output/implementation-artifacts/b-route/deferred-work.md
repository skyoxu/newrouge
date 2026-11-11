
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
