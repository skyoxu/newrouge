---
ADR-ID: ADR-0031
title: 构建可复现性与版本锁定（Godot 4.5.1 + NuGet Lock）
status: Accepted
decision-time: '2026-01-22'
deciders: [架构团队]
archRefs: [CH07, CH09]
verification:
  - path: Directory.Build.props
    assert: RestorePackagesWithLockFile=true（生成并提交 packages.lock.json）
  - path: scripts/ci/quality_gate.ps1
    assert: 运行门禁时写入环境取证到 logs/ci/<YYYY-MM-DD>/
impact-scope:
  - Directory.Build.props
  - '**/packages.lock.json'
  - scripts/ci/**
  - scripts/python/**
  - .github/workflows/**
  - logs/ci/**
tech-tags: [reproducibility, version-pinning, godot, dotnet, nuget, windows, sqlite, evidence]
depends-on: [ADR-0001, ADR-0005, ADR-0011, ADR-0015, ADR-0019, ADR-0025]
supersedes: []
---

# ADR-0031: 构建可复现性与版本锁定（Godot 4.5.1 + NuGet Lock）

## Context

本项目是 Windows-only 的 Godot + C# 模板。引擎二进制、导出模板、.NET SDK 与 NuGet 依赖解析的任何漂移，都可能导致：

- “同仓不同机不可复现”（CI 与本地结果不一致）
- 门禁波动（偶发失败、无法定位）
- 导出链路不稳定（模板不匹配、native 依赖差异）

团队明确不使用 `global.json` 锁定 .NET SDK，因此必须用“依赖锁 + 取证日志”来弥补可复现性缺口。

## Decision

### 1) Godot 版本锁死

- 引擎锁死 Godot .NET `4.5.1`。
- v1 不升级 Godot；如需升级必须先新增/更新 ADR 并提供 `logs/**` 取证证明“可构建/可导出/门禁全绿”。
- `GODOT_BIN`：headless/CI 统一使用 Godot .NET 4.5.1 的 console 版本二进制（用于稳定采集输出）。

### 2) 导出模板版本一致

- Godot export templates 必须与 `4.5.1` 匹配；缺失/不匹配视为硬失败。

### 3) NuGet 依赖锁定（packages.lock.json）

- 启用并提交 `packages.lock.json`（通过 `RestorePackagesWithLockFile=true`）。
- 升级依赖必须同步更新 lock 文件，并跑门禁产出取证日志。

### 4) 环境取证（logs/）

每次运行门禁必须把环境证据写入 `logs/ci/<YYYY-MM-DD>/...`，用于定位“到底是代码变了，还是环境变了”：

- `godot --version`
- `dotnet --info`
- `dotnet --list-sdks`
- `py -3 --version`
- `GODOT_BIN` 绝对路径（建议同时记录文件 hash）

### 5) SQLite 变更约束

- v1 保持当前 SQLite provider/打包方式不变。
- 如需替换（provider、native bundling、加载方式），必须先新增/更新 ADR，并补齐 headless 冒烟与 `logs/**` 取证。

## Consequences

- 正向：门禁与导出链路更稳定；排障更可追溯；降低“玄学红”成本。
- 代价：依赖升级流程更严格；需要维护 lock 文件与取证输出。

## Alternatives

- 不锁版本、不写取证：短期省事，长期不可复现成本极高。
- 使用 `global.json` 锁 SDK：可复现更强，但不符合当前团队选择。
