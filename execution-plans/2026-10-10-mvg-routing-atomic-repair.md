# MVG 路由与原子修复执行计划

用户已批准 `_bmad-output/implementation-artifacts/spec-mvg-routing-atomic-repair.md` 的范围。

1. 自包含 fixture 复现分配扩散、补丁污染和投影失配，保存 RED。
2. 候选级 LLM 路由与 CLI schema 强制分段边界。
3. 最终结构投影前置，原子接纳受限修复，统一修复计数。
4. 即时独立补位及硬调用预算，保存定向 GREEN 并审查。

当前阶段：已复现路由遗漏、重复、越界与旧哈希补丁问题，实施候选级路由及原子接纳；四处 owning 文档已同步，等待代码回归与独立审查。按 ADR-0005 和 run-protocol 保存证据到 `logs/ci/2026-10-10/mvg-routing-repair/`。

不执行完整模型工作流；不更改任何上游权威或运行时状态；不提交、不重启服务。
