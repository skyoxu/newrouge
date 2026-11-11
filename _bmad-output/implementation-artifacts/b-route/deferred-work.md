
- source_spec: `_bmad-output/implementation-artifacts/b-route/spec-2-2-independent-cumulative-source-audit.md`
  summary: 恢复的既有BMAD架构lint_spine以子串代替显式字段标签，可能漏报Binds/Prevents缺失。
  evidence: `_bmad/bmm/plan/bmad-architecture/scripts/lint_spine.py:142` 对正文做 `f in low`；只有Rule且含unbinds/prevents的正文即可通过。来源为58b7d6e恢复的运行时资产，当前Story未修改该linter；需后续工具维护中补显式标签识别及负例，避免架构Reviewer Gate错误放行。

- source_spec: `_bmad-output/implementation-artifacts/b-route/spec-2-3-task-independent-planning-workspace.md`
  summary: 补充合格真实3A proof通过只读验证、正式3B准备及当前load重验的阳性集成证据。
  evidence: 原始真实audit04均有blocking findings且当前工具身份已漂移；成功单测显式使用assembly seam。用户目前暂停新的真实模型调用，不得伪造real资格；待有当前合格原始proof后补测。

- source_spec: `_bmad-output/implementation-artifacts/b-route/spec-2-6-frozen-adoption-operation.md`
  summary: 锁路径检查与实际取得句柄之间的替换风险为 medium 未验证项，当前没有新增准入门禁。
  evidence: helper 明确要求目录稳定；需 Windows 原 managed acquisition 中的受支持替换证据与实际句柄偏离，才能判定是否超出现有信任边界。源自本轮 B9，仅保留调查，不声称已修复或实际发生。
