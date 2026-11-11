# ADR-0047：保留累计修复进展、完整原子路径预检与确定性 CI

- Status: Proposed
- Date: 2026-11-07
- Scope: Story 2.5 审核回环2；等待 Root 定向执行及统一集成

R25 把“修复后必须立刻消除当前语义 issue”加到共用 append，误影响原 legacy callback。原冻结合同只要求同一稳定 issue 的三次预算与最终完整语义准入，没有要求每次合法局部修复必须立刻完成全部义务。本次直接移除两行额外拒绝，不增加公共开关或新生命周期；保留相关修复域检查、原计费、稳定 issue/counter、无进展/无关改动拒绝及最终所有 finding 清空门槛。3B 的宿主修复域、真实原问题绑定和最终独立执行 proof 不弱化，不修改已签历史账本。

fresh run 仍使用原 Windows 259 字符门禁，但按 UTF-16 单元核算真实固定 producer 路径：原子 integrity/schema/binding/host 文件包含 PID、线程ID和 nonce；协议日志、实际 stderr 与失败专属 host-cleanup 旁件也检查。scope/call/attempt 沿原192/64上限作保守路径预算。恢复 owner 对各自额外 namespace 另行预检；不修改注册表、安全设置或既有路径。超限在创建新run前拒绝，可选择更短root或run ID。

新增维护的 Windows 确定性 CI 入口覆盖 3B；原 legacy gate bundle 与 real-model workflow 保持原样，不扩它们的触发路径，也不为了测试列表改动放宽生产源码迁移门禁。新 job 不取模型密钥、不安装模型 CLI、不调用模型服务；只使用独立 venv、官方 PyPI 固定顶层依赖及 OpenAI tokenizer 公开编码数据，保存 pip 下载哈希报告。测试响应为明确合成数据，不能当真实模型语义资格。该文件只是可审阅配置，本地未触发 GitHub job、推送或合并。

必要控制是实际 legacy scope callback 下的两步合法累计修复、无关 Flow 修改仍拒绝、公开 run_location 对实际临时名的支持/拒绝及无写入。CI 选择范围和执行结果分别记录，不以静态配置冒称托管 CI 已通过。Root 串行验证后决定本方案接受及正式 Story 收口。
