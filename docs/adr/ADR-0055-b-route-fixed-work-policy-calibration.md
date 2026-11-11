# ADR-0055：B 路线固定工作政策的实测校准

- Status: Accepted
- Date: 2026-11-11
- Scope: 当前共享 codec owner 的本地确定性工作计数；不授模型、采纳或默认 B 资格。
- Partially supersedes: ADR-0041 第 5 项及 ADR-0050 对当前 100M 工作界的继承；只替代该数值和资源政策版本。

## 决定与依据

当前固定政策为 `newrouge.b-route-resource-pipeline.v4`，同一 final-request 工作账户上限为 **170,000,000**。不添加调用方参数、环境变量或按包自动扩容。共享 owner 的当前消费者采用这一固定政策，不能把影响范围说成只改一个请求。

原 100M 是已接受的本地防耗尽策略，不是 Story 2.8 原始 AC、官方模型窗口、实测 CPU 指令数或付费额度。原 prepare10 与后续 Task v4 E 的真实 100M 拒绝保持不变。精确结构键已解决缓存容量回退，但完整 E、D、语义与精确检查仍需更多累计工作；继续多个已证明不足的小优化不作为交付前置。

干净独立 Astra max 在 Task `night-handoff/story28-local-work-policy-scope-Astra-20261111/assessment.md` 同意一次固定 300M／180 秒 DATA 校准。Root 在 Task `logs/ci/2026-11-11/story28-v4-work-calibration-01/{result,unit}.json` 取得完整组件正常 OS0／Job 静止：沿原已耗 **49,333,580**，同账户完成 E、完整 D、实际纯语义验证、双 ordered/type-exact 及 frame 检查，总量 **166,927,907**，耗时约 **6.86 秒**，frame **313,176 bytes**。因此取下一档 10M 得到 170M，余量 3,072,093；300M 调查上界不是生产值。

组件只用原 `encoder-entry.json`／`render-live-1.json` 的实际保留量标量，没有伪造 `Derived` 或 private graph。它不证明原 owner render、RSS、native prepare 或最终 1MiB／70k 门。Task 额外保存的本地 component frame 是诊断产物，不是外发或发布。正式原生 prepare 尚须使用固定新源码按原合同取得真实结果；失败不自动增加这个固定值。

## 保持的边界

- 每次真实扫描、比较、构造和检查继续原预付单位；现有工作账户在所有 helper 之间传递，不重置、不退还原占用，不把独立 E／D 账户拼接为资格。
- 8MiB encoded、64MiB expanded／retained、1,000,000 nodes、depth 128 及全部分配前检查保持。不存在新的“不必校验”参数、缓存、registry 或指纹门。
- 完整材料、语义分母、冷路径 canonical、warm 完整 D、原像／当前双 exact、原 unknown 与真实退出证据保持。wire／语义／证明版本不因这项本地政策决定而重签。
- 原真实请求 1MiB、配置 70k／默认 96k 输入、输出预留、32MiB transcript，以及 4200 秒 prepare／3600 秒历史 reader 上限保持，分别由原 owner 检查。
- 本次决定时账本为 83 paid-or-unknown、181 重叠 guard、cap 290、released 0；不是 83+181。这项本地政策不改变账本、不授模型执行资格，不释放 unknown 或扩大模型预算。high、关闭 Fast、不合并 main 的边界保持。

## 验证与回滚

复用仍适用的结构键、canonical 和历史资源证据；只对固定默认值、同账无重置、charged／charged-1、完整 roundtrip／类型／顺序／signed-zero、未变 byte-memory 拒绝与不发布半 prompt 做必要定向验证。定向通过不是 Story 验收；原 source／policy 绑定自然记录新源码，不加额外指纹体系或重跑无关全套。

算法检查点 `9743893b` 与本政策分开提交，可以独立回滚。回滚仅恢复当前源码，不改写旧失败、原证明或已生成的新 policy 证据；旧证明仍由原 producer／policy 验证，不借 reader 兼容混用。此技术决定不取消 Story 2.8 的真实 prepare、受审阅补偿、恢复与正式收口要求。

当前受影响验证记录：16项定向中的15项通过；1项测试观察钩子失败保留，修正直接调用后单独1项通过。证据为 Task `story28-r62-policy-targeted-01` 与 `story28-r62-policy-singleton-02`。没有重复全套或将原失败改签为通过。原生 prepare、最终请求及 Story 正式收口仍待完成。
