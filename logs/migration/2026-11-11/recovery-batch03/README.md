# NewRogue 一次性恢复数据交接（第三批）

此目录包含筛查后的原始目标状态、NativeV15Origin03 及其实际引用证据、nx/m4 的原 run/handoff/admission/执行与恢复数据、历史 Host1/2/3 配置和完整账本前缀，以及原配置实际指向的 TEMP 证据。所有原始文件保持原字节，逐文件来源、大小与 SHA-256 见 FILE_INDEX.json。

先读 MANIFEST.json、MISSING_AND_SCOPE.json。按 MANIFEST 列表取得归档；若有分片，按顺序拼回 recovery-data.zip。仅解压到全新隔离目录。归档 target/、nx/、task/、temp/ 是数据命名空间，原 Windows 根路径映射在 FILE_INDEX；不是应立即执行的工作区或授权环境。不要运行原 driver 或重放 unknown。

原 operation 内嵌请求9e98ad…、binding 指向的现存请求b9ebaf…、补偿请求7dea03…是三个不同版本。derived/ 内的第一份请求是对原 operation 字段的精确解码，非补造原始磁盘文件。

包含个人联系信息的诊断/历史支持原件未公开，只报告类别和数量；原引用保留，不以去敏文本冒充原证明。可选历史指纹、软件依赖清单、目录观测、测试夹具等不作为当前状态恢复输入；可选历史条目只列元数据。

实际 Unit Root-02 canonical 配置与账本目录仍不存在；不要用 Host1/2/3 历史记录替代它。旧 R50 prepared-locator 和一份 Host2 结果引用缺失；缺件与历史未完成状态原样记录。旧未知占用、STOP、R50保留99与当前记录83/181/290/0均未释放或重算。此包不代表恢复运行、完整证明链准入或 Story 验收通过。

本轮只做资料静态迁移，没有执行模型、driver、账务或测试，不开发、不合并 main、不启用 Fast，也未操作 S2 或流量监控。
