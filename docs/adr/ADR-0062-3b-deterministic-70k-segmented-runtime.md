# ADR-0062: 3B 原生协调器全 6 阶段 70,000 字节 CLI 确定性分段运行时契约

- Status: Accepted
- Date: 2026-11-14
- Scope: B 路线正式 3B 原生规划入口（`plan-capabilities --input-stage 3b` / `plan-mvg --input-stage 3b`）、首次采纳审阅（`b-route-adoption --stage review-*`）与分段补偿审阅的确定性 CLI 分段及无损重组契约
- Related:
  - `docs/adr/ADR-0038-semantic-delivery-topology.md`
  - `docs/adr/ADR-0038-mvg-candidate-admission.md`
  - `docs/adr/ADR-0039-mvg-completed-capability-recovery.md`
  - `docs/adr/ADR-0040-b-route-stages-authority-and-activation.md`
  - `docs/adr/ADR-0042-shared-segmented-planning-protocol.md`

## Context

在 B 路线正式 3B 无 Task 规划链路中，单文件单轮完整输入模式在面对真实业务规格与完整 3A 独立来源审计证据（例如 `sc25` 单能力准备原件）时，因宿主机原始协议帧与重复依赖拷贝叠加，超出单次模型调用的输入字节与 token 容量门限而触发容量拒绝阻断。同时，历史 `story25` 独立分段实验路径绑定于旧特定活动目录并输出 `segmented-unselected`，不能直接充当直通 `b-route-adoption` 的正式 3B 协调器产物。

为在不放宽 `96,000` 上下文安全硬顶、不删减独立来源证据、不改动受锁 `_b_route_planning_input.py` 原始组装契约的前提下彻底解除容量拒绝阻塞，需要为正式 3B 原生协调器及配套采纳审阅确立统一的 CLI 确定性分段契约。

## Decision

1. **全 6 阶段统一 `<= 70,000` UTF-8 字节每调用分段契约**
   - 每次模型调用的完整可见负载（含系统提示词、任务指令、输出 Schema 与当前分段输入包络）严格满足 `utf8_byte_upper_bound <= 70,000`。
   - 保持 `96,000` token 总安全顶（`<= 70,000` 输入预算 + `26,000` 输出预留，`input + reserve <= 96,000`），绝不通过放大上下文上限或降低推理强度绕过门禁。
   - 该上限统一覆盖全部 6 个语义与审阅阶段：
     1. 阶段 1–4（`plan-capabilities --input-stage 3b` 与 `plan-mvg --input-stage 3b` 原生规划协调器内的候选批次生成 `batch generation`、跨段合成与一致性修复 `synthesis / repair`、先准入 `independent_admission`、后择优 `selection`）；
     2. 阶段 5（`b-route-adoption --stage review-prepare` / `review-complete` 对超过 `70,000` UTF-8 字节的非机械首次 `adoption-request.v1` 执行确定性分段审阅与汇聚）；
     3. 阶段 6（`b-route-adoption --stage review-segmented-*` 分段补偿审阅与汇聚）。

2. **纯 CLI 结构化确定性切分，零 LLM 边界猜测**
   - 所有分段边界完全由宿主 CLI 按结构化条目边界（`global_proof`、`constraints`、`contexts`、`evidence` 及目标差异集）确定性计算并冻结为有向执行计划。
   - 严禁截断单个结构化条目、严禁以摘要替代原文、严禁由 LLM 自行判断切分边界或决定是否继续下一段。
   - 在每个生成与修复分段中完整保留 `dependencies.files` 精确引用摘要表（确保模型填写 `OwnedRef` `raw_digest` 零偏差），将宿主机原始协议大帧留在宿主 `raw-index.json` 做字节级强校验。

3. **无损重组与原生 `b-route-adoption` 直通兼容**
   - 原生 3B 协调器继续调用 `_b_route_planning_input.assemble()` 冻结完整无损 `inputs` 与 `raw-index.json`，各分段响应经严格 JSON Schema 校验后由宿主执行无损确定性重组，产出标准 `newrouge.b-route-planning-run.v1`（`selection_status == "selected"`）与 `handoff.json`。
   - 产物 100% 直通 `_b_route_completed_reuse.py` 完成项恢复及 `b-route-adoption` 正式首次采纳流（严禁对首次 `adoption-request.v1` 误用仅限补偿请求的 `review-segmented-*` 子命令）。
   - 分段工作区子目录采用短定长路径（如 `s/001/w/o.json`），严格遵守 Windows `259` 字符最大路径长度预算。

4. **100% 保留历史非分段产物与既有证据**
   - 所有已落盘的历史非分段运行产物、失败容量原件、已提交正式记录（`docs/planning/b-route/**`）及 `story25` 历史分段归档原样保留、零回写、零篡改；只读复验器同时保持对历史非分段证据与新确定性分段证据的精确校验能力。

## Consequences

- **Positive**：彻底消除正式 3B 与首次采纳审阅的单次输入容量瓶颈，无需外部网络下载分词表即可在离线与跨平台环境下提供确定性 `<= 70,000` UTF-8 字节上界保证。
- **Negative / Trade-offs**：大规格输入会拆分为多次独立无工具模型调用，因此真实执行前必须先运行零调用 `prepare` 阶段精确核算总调用次数并受持久化预算许可约束。
- **Governance Boundary**：本 ADR 确立 3B 分段运行时技术契约（`Accepted`），不单独授予业务 Story 签收或默认切换至 B 路线；默认路由切换仍严格遵循 `docs/adr/ADR-0040-b-route-stages-authority-and-activation.md`。
