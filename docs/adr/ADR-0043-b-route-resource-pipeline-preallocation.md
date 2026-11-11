# ADR-0043：B 路线全链资源预检与共享计量

- Status: Proposed
- Date: 2026-11-07
- Scope: Story 2.5 审核回环 2，R26，等待 Root 定向验证与决策
- References: [ADR-0041](ADR-0041-b-route-review-hardening-resource-and-metadata-boundaries.md)、[ADR-0040](ADR-0040-b-route-stages-authority-and-activation.md)、[当前 spec](../../_bmad-output/implementation-artifacts/b-route/spec-2-5-independent-admission-bounded-selection.md)

## 问题与决定

R2-B3/B4/B5/B6 确认原资源边界执行得过晚：完整 AST 已构建后才数节点；compact sharing 已反复渲染子树后才建立 v3 工作计数；内层 lossless marker 是另一命名空间，外层 compact 计量不能限制其 DAG 展开；wire 入口先因子化、恢复和完整序列化再进入 compact。

资源政策版本改为 `newrouge.b-route-resource-pipeline.v2`。这扩展了 ADR-0041 的**计量范围与预分配边界**，不改变 wire v1/v2/v3、lossless v1 语法或字段，也不提高阈值：编码正文 8 MiB UTF-8、保守展开 64 MiB、1,000,000 节点、深度 128、共享工作量 100,000,000。模型/token/输出/调用/时间和 campaign 额度均不变。旧资源政策与原 producer 的通过证据保留，不重签为新全链政策资格；默认 B 未启用。

## 执行边界

1. compact 在 `ast.parse` 前单遍扫描受限数据 token，按 AST 节点上界及括号深度拒绝；字符串内部括号和 escape 不当语法节点。连续 unary/operator、调用/下标等非数据表达式先拒绝。原严格 AST 解析、数据 grammar、摘要和精确规范重编码仍继续执行。wire 的 plain/v1 JSON 在完整 JSON 树构造前使用同一受限扫描；不执行任何输入。
2. compact 的输入度量不创建宽 pending 列表；先检查廉价长度/节点/深度，保留类型、键序和全部值。一个调用者工作计数器穿过 input/copy/keysets/pack/share/phrase/render/digest/output 验证及 decoder 的 canonical 重编码，不能在 helper 中重新发放预算。`_literal` 和 atom 渲染在 repr 与 join 前收费；sharing 为每次实际完整子树渲染、字符比较和 key lookup 付费，不用缓存摘要替代选取算式。
3. wire 在原 lossless 因子化前计算输入、变换、潜在缓存和工作预留。原 `_mvg_lossless_context.py` 不修改。原 `restore_lossless_context` 的两步被显式分开：先对 marker DAG 做饱和计量，再调用原 `_restore`；在对恢复值再次前检后调用原 `lossless_context`，并由原 `wire` helper 逐字比较原 canonical 编码，调用前计量。原 schema/content hash、精确整数引用、向后/unused/reserved 检查和 canonical 比较全部保留。
4. 内层预检只解释当前 envelope 的 `$mvg_ref`、concat、lines、source、escaped-object。缓存与最终逻辑值合计受 64 MiB/1m 限制，依赖深度也受限。字符串拼接在 join 前度量；CRLF 跨片边界及 splitlines 的 Unicode 分行字符参与行数核算，阻止巨大辅助分行数组。escaped-object 的键是字面数据；嵌套旧 envelope 的本地引用不会被拿到外层 namespace 解析。
5. `render`/`read_prompt`/`encode`/`decode`/文本与摘要序列化共享传入预算。正文 UTF-8 字节数在解析前检查；实际序列化、UTF-8/hash 和完整往返都在原始数据上执行，不截断、投影、换 codec 或修改摘要。

## 工作单位与可审查预留

这是确定性的**政策计量**，不是墙钟、CPU 指令、进程 RSS 或“实际已经耗尽”的声明。直接控制的代码按节点/槽位、字符访问、比较、repr 输出和 join 字符数收费；排序按实际比较收费。工作计数也包含前检本身。拒绝报告 `phase`、`charged`、`reserve`、`remaining`；尺寸拒绝报告 `bytes_bound`、`nodes_bound`、`depth_bound`。

未修改的 legacy helper 只能在调用前预留。令 `S` 为一次根 JSON 序列化的 UTF-8 上界，`T` 为所有原节点完整子树序列化上界之和，`P` 为实际候选 span 区间长度之和。普通 ASCII 和 escape 的序列化长度逐字符计算，整数用保守位数上界，不先构造巨大十进制字符串。`T` 对应实际 `count`/`encode` 中逐 node 的 `wire(node)`，并非字符串与任意字典长度的笛卡尔乘积。

- 每次 legacy factor 预留 `9T + 9S + 44P + L + E`：两遍 `wire(node)`，至多六份对应 string-key hash/比较和一份潜在 subtree copy；两次 digest 的序列化/UTF-8/hash、两份 roundtrip serialization 和最终 copy；实际 span 的切片/查找/引用键（含最坏 JSON escape）；`L` 是分行、fragment 和地址查找上界，`E` 是编码结构节点上界。
- span 的 quoted-token 规则按原正则的互斥分支逐步检查，包括反斜线后的 LF 失败；按实际尝试区间另预留原 token 扫描和数值区间排序。昂贵失败 quote 的检查自身也会在同一预算中停止，不先执行原正则。
- 行结构按容器和字段逐项计算：numbered string 上界为 `6N + 68 + 39R`、`2 + 3R` 节点；source 上界为 `6N + 74 + 348F + 39R`、`2 + 8F + 3R` 节点，其中 `F` 不超过可选互不重叠区间数的两倍加一。引用对象按至多 88 加权字节预留；固定 envelope frame 用同一度量器计算，不用任意固定 header 常数。
- 潜在缓存按所有原子树和真实候选 source fragment 的上界核算。它可能比实际选中的共享项严格，拒绝只能叫**预留上界拒绝**，不能称量出了真实 heap/CPU 消耗。该保守性已作为 v2 政策显式提出，不暗中解释旧 producer。

上述系数对应现有调用树与表示上界；它们没有放大任何模型预算，也不证明所有历史大输入能通过新的全链预算。Root 应保存精确阶段、计量与拒绝，不以较小夹具或旧政策成功替代当前结果。

## 验证与交付限制

实现者只做 AST、方法清单和哈希，不运行测试、项目导入、helper、子进程、native、模型或 Git。新测试自建小数据，包含 AST/JSON 前哨兵、重复渲染与共享计数、内层 DAG/concat/source/lines、字面 marker/嵌套 namespace、原 schema/digest/canonical 拒绝，以及 all-version 和旧 wire 字节对照；Root 负责实际执行。

原 329024 字节 selector 提示 SHA256 `91784631802598c780450d2178d3297b0757ade18749adda76abdbeab5df1190` 和旧 codec `67e714f...` 的 canonical PASS17 保持原件。实现者没有读取该提示。新完整资源链的实际测量/接受或预留拒绝仍待 Root，不能据原 PASS17 声称新 current qualifier。资源模块/source identity 改变后仍须原 owner 的 current/source 守卫，不新增生产模块或放宽 allowlist；正式 Story、采纳、readiness 和运行权限均未授予。
