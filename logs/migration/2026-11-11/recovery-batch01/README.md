# NewRogue 恢复日志第一批（已授权公开）

第一批迁移提交在 r62 公开源码快照上仅增加 4 份原始日志、本清单与缺件说明。原日志位于 `logs/ci/2026-11-11/story28-r62-public-prepare-11/`，未脱敏或改写；逐文件大小和 SHA-256 见同目录 `MANIFEST.json`。

- `result.json`：原进程自然退出 OS2，passed=false、formal_story28_acceptance=false。
- `unit.json`：原始诊断、异常链及执行时间，new_project_model_calls=0。
- `traceback.txt`：真实调用栈及容量失败：101371 输入估算 + 2000 输出预留超过当时 70000 门禁。
- `genuine-render-complete.json`：原渲染实际完成，本地工作量166939774/170000000；并不表示最终请求准入或 Story 验收通过。

原执行源码为 b24e1dfd35901389dc6297683cd1fe4b52ce3b58。父快照已含后续 2a40ec535e57e94dd7bbc8721f06a45e676db048 诊断修复；这些回执不是修复后的重跑结果。

**缺件：**原 Task 根下 `story29-unit-profile-allocation-Root-02` 目录及其 config.json、ledger 目录、ledger/000001.json、ledger/STOP.json 均不存在。无法提供账本文件名/大小/SHA256 清单，未发布任何账本正文。不能据此推断账本为空、费用为零，或初始化替代账本、释放 unknown。

按用户本次授权保留了必要历史路径、进程号和诊断；4 份日志审查未发现密码、令牌、密钥或认证记录。未发布 Library 信息及无关私人资料。历史 Windows 路径不代表云端路径或运行准入。本次仅迁移资料，不启动测试、模型调用或新开发，不修改原件，不合并 main。

后续静态定位材料见 `../recovery-batch02/MANIFEST.json`：driver 定义摘录与现存请求文件；未重跑 driver。
